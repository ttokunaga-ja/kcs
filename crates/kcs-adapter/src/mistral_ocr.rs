//! Mistral OCR markdownize adapter.

use crate::identity::hash_bytes;
use crate::traits::MarkdownizeAdapter;
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownUnit, MarkdownizeMode, MarkdownizeRequest,
    MarkdownizeResponse, PreparedUnitHint,
};
use crate::{AdapterError, Result};
use base64::Engine;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OcrImage {
    pub bytes: Vec<u8>,
    pub media_type: String,
    pub bbox: Option<[i64; 4]>,
    pub confidence: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OcrPage {
    pub index: usize,
    pub markdown: String,
    pub images: Vec<OcrImage>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OcrResponse {
    pub pages: Vec<OcrPage>,
    pub model_version_pin: String,
}

pub trait MistralOcrClient: Clone {
    fn resolve_model_pin(&self, configured_model: &str) -> Result<String>;

    fn ocr_markdown(&self, request: &MarkdownizeRequest, model_pin: &str) -> Result<OcrResponse>;
}

#[derive(Debug, Clone, Default)]
pub struct EnvMistralOcrClient {
    base_url: Option<String>,
}

impl EnvMistralOcrClient {
    #[must_use]
    pub fn new() -> Self {
        Self { base_url: None }
    }

    #[allow(dead_code)]
    #[must_use]
    pub fn with_base_url(base_url: impl Into<String>) -> Self {
        Self {
            base_url: Some(base_url.into()),
        }
    }

    fn base_url(&self) -> String {
        self.base_url
            .clone()
            .or_else(|| std::env::var("MISTRAL_API_BASE").ok())
            .unwrap_or_else(|| "https://api.mistral.ai".to_owned())
            .trim_end_matches('/')
            .to_owned()
    }

    fn api_key() -> Result<String> {
        // R13-2: honor a declared `tools.toml` `[markdown] auth` (env:/plain:, with
        // keychain: a loud not-implemented error) instead of the previous hard-coded
        // `MISTRAL_API_KEY`; fall back to that env var when nothing is declared.
        crate::tool_lock::resolve_role_api_key("markdown", "MISTRAL_API_KEY")?.ok_or_else(|| {
            AdapterError::Auth(
                "no Mistral OCR API key: set MISTRAL_API_KEY or a tools.toml `[markdown] auth`"
                    .to_owned(),
            )
        })
    }
}

impl MistralOcrClient for EnvMistralOcrClient {
    fn resolve_model_pin(&self, configured_model: &str) -> Result<String> {
        if !configured_model.ends_with("-latest") {
            return Ok(configured_model.to_owned());
        }
        let api_key = Self::api_key()?;
        let value: Value = ureq::get(&format!("{}/v1/models", self.base_url()))
            .set("Authorization", &format!("Bearer {api_key}"))
            .call()
            .map_err(http_error)?
            .into_json()
            .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
        let family = configured_model.trim_end_matches("-latest");
        value
            .get("data")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(|model| model.get("id").and_then(Value::as_str))
            .filter(|id| id.starts_with(family) && !id.ends_with("-latest"))
            .max()
            .map(str::to_owned)
            .ok_or_else(|| {
                AdapterError::ContractViolation(format!(
                    "no versioned model found for {configured_model}"
                ))
            })
    }

    fn ocr_markdown(&self, request: &MarkdownizeRequest, model_pin: &str) -> Result<OcrResponse> {
        let api_key = Self::api_key()?;
        let path = request.raw.path.as_deref().ok_or_else(|| {
            AdapterError::ContractViolation("Mistral OCR requires a local raw path".to_owned())
        })?;
        let bytes = std::fs::read(path).map_err(|err| AdapterError::Io {
            path: path.to_owned(),
            message: err.to_string(),
        })?;
        // R14-4: in incremental mode, restrict the OCR request to the changed+added
        // pages via the `pages` parameter (built from `prepared_unit_hint`), instead of
        // silently sending — and re-billing — the whole document every revision. Full
        // mode sends no `pages` (process the entire document).
        let pages = request_pages(request);
        let value: Value = ureq::post(&format!("{}/v1/ocr", self.base_url()))
            .set("Authorization", &format!("Bearer {api_key}"))
            .set("Content-Type", "application/json")
            .send_json(ocr_request_body(
                &request.media_type,
                &bytes,
                model_pin,
                pages.as_deref(),
            ))
            .map_err(http_error)?
            .into_json()
            .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
        parse_ocr_response(value, model_pin)
    }
}

#[derive(Debug, Clone)]
pub struct MistralOcrMarkdownizeAdapter<C = EnvMistralOcrClient> {
    client: C,
    configured_model: String,
    scope_id: String,
    image_store_dir: Option<PathBuf>,
}

impl Default for MistralOcrMarkdownizeAdapter<EnvMistralOcrClient> {
    fn default() -> Self {
        Self::new(EnvMistralOcrClient::new(), "mistral-ocr-latest", "unknown")
    }
}

impl<C> MistralOcrMarkdownizeAdapter<C> {
    pub fn new(
        client: C,
        configured_model: impl Into<String>,
        scope_id: impl Into<String>,
    ) -> Self {
        Self {
            client,
            configured_model: configured_model.into(),
            scope_id: scope_id.into(),
            image_store_dir: None,
        }
    }

    #[must_use]
    pub fn with_image_store(mut self, kcs_dir: impl Into<PathBuf>) -> Self {
        self.image_store_dir = Some(kcs_dir.into());
        self
    }
}

impl<C: MistralOcrClient> MarkdownizeAdapter for MistralOcrMarkdownizeAdapter<C> {
    fn profile(&self) -> AdapterProfile {
        // Network-free: `profile()` never resolves the model pin over HTTP
        // (Step2c I5). The pin is resolved exactly once at execution time and
        // the resolved value is passed in as `configured_model`, so the profile
        // reflects the resolved pin without a second `GET /v1/models`. If the
        // adapter still holds an unresolved `*-latest` alias (e.g. the `Default`
        // used in unit tests), fall back to a deterministic immutable
        // placeholder rather than contacting the network — the identity layer
        // rejects a mutable alias as a `model_version_pin`.
        let model_pin = if crate::identity::is_mutable_model_alias(&self.configured_model) {
            format!(
                "{}-unresolved",
                self.configured_model.trim_end_matches("-latest")
            )
        } else {
            self.configured_model.clone()
        };
        let profile = json!({
            "adapter_kind": "markdownize",
            "adapter_role": "multimodal",
            "model_or_tool_family": "mistral-ocr",
            "model_version_pin": model_pin,
            "output_schema": "kcs-markdown-v1",
            "runtime_kind": "cloud",
            "spec_version": 1
        });
        AdapterProfile {
            adapter_kind: AdapterKind::Markdownize,
            adapter_id: "mistral_ocr_markdownize".to_owned(),
            execution_mode: ExecutionMode::OnlineApi,
            tool_profile_hash: crate::identity::tool_profile_hash(&profile)
                .expect("built-in Mistral profile is valid"),
            version: env!("CARGO_PKG_VERSION").to_owned(),
            capability_flags: vec![
                "ocr".to_owned(),
                "layout_detection".to_owned(),
                "table_extraction".to_owned(),
                // R13-1: the standard document-processing adapter DOES support
                // incremental Markdownize — via unit (page) fingerprint reuse
                // (docs/04 §2.2, docs/07 §8 note), not the generative-LLM prompt
                // path. Declaring it lets `choose_markdownize_mode` reach the
                // incremental gate on the online route (previously it always fell
                // to `full("adapter_lacks_incremental_update")`). capability_flags
                // is NOT a `tool_profile_hash` input (see identity::PROFILE_FIELDS),
                // so this does not change any adapter identity / fixture hash.
                "incremental_update".to_owned(),
            ],
            allow_network: true,
        }
    }

    fn markdownize(&self, request: MarkdownizeRequest) -> Result<MarkdownizeResponse> {
        let model_pin = self.client.resolve_model_pin(&self.configured_model)?;
        let ocr = self.client.ocr_markdown(&request, &model_pin)?;
        if let Some(kcs_dir) = &self.image_store_dir {
            for page in &ocr.pages {
                persist_images(kcs_dir, &page.images)?;
            }
        }
        let hints = request
            .prepared_unit_hint
            .as_ref()
            .cloned()
            .unwrap_or_else(|| {
                vec![PreparedUnitHint {
                    unit_key: "page:1".to_owned(),
                    prepared_hash: request.raw.raw_hash.clone(),
                    unit_kind: crate::types::UnitKind::Page,
                    order: 0,
                }]
            });
        let pages_by_index = ocr
            .pages
            .iter()
            .map(|page| (page.index, page))
            .collect::<BTreeMap<_, _>>();
        Ok(MarkdownizeResponse {
            mode_used: request.mode,
            updated_units: hints
                .iter()
                .filter_map(|hint| {
                    let page_index = hint.order as usize;
                    let page = pages_by_index
                        .get(&page_index)
                        .copied()
                        .or_else(|| ocr.pages.get(page_index))?;
                    let markdown =
                        replace_image_placeholders(&page.markdown, &self.scope_id, &page.images);
                    Some(MarkdownUnit {
                        unit_key: hint.unit_key.clone(),
                        unit_type: hint.unit_kind,
                        markdown,
                        metadata: page_metadata(
                            &ocr.model_version_pin,
                            Some(page.images.as_slice()),
                        ),
                    })
                })
                .collect(),
            unchanged_unit_keys: Vec::new(),
            added_units: Vec::new(),
            removed_unit_keys: Vec::new(),
            evidence_pointers: Vec::new(),
            fallback_to_full: false,
            reason: None,
        })
    }
}

fn document_payload(media_type: &str, bytes: &[u8]) -> Value {
    let encoded = base64::engine::general_purpose::STANDARD.encode(bytes);
    let data_uri = format!("{media_type};base64,{encoded}");
    if media_type == "application/pdf" {
        json!({
            "type": "document_url",
            "document_url": format!("data:{data_uri}")
        })
    } else {
        json!({
            "type": "image_url",
            "image_url": format!("data:{data_uri}")
        })
    }
}

/// R14-4: the 0-indexed pages an OCR request should process. Incremental mode restricts
/// the OCR to the changed+added units carried in `prepared_unit_hint` (each unit's
/// `order`, which `prepare` assigns 0-based — page:1 → 0, page:2 → 1, …); Full mode
/// returns `None` (process every page). Before R14-4 the real client ignored the hint
/// and always sent the whole document, so a light revision re-OCR'd/re-billed all pages.
fn request_pages(request: &MarkdownizeRequest) -> Option<Vec<usize>> {
    if request.mode != MarkdownizeMode::Incremental {
        return None;
    }
    Some(
        request
            .prepared_unit_hint
            .as_deref()
            .unwrap_or(&[])
            .iter()
            .map(|hint| hint.order as usize)
            .collect(),
    )
}

/// R14-4: build the Mistral `/v1/ocr` request body. `pages = Some(..)` scopes the OCR to
/// exactly those 0-indexed pages (the incremental cost fix, docs/07 §8: KCS re-processes
/// only the changed+added units and reuses the rest); `pages = None` processes the whole
/// document (Full send). Pure + HTTP-free so the page scoping is unit-testable.
///
/// NOTE: whether Mistral's `pages` parameter actually reduces billing is confirmed only
/// by real-API verification (a user-gated step, as with the prior Mistral/Gemini checks).
/// The code-side defect this closes is definite: incremental previously ignored the hint
/// and sent every page. The `pages` indices are 0-based to stay consistent with the
/// adapter's page indexing everywhere else (the mock and `parse_ocr_response` map pages by
/// the same 0-based `order`); if real-API verification shows Mistral expects 1-based
/// indices, this is the single place to add `+ 1`.
fn ocr_request_body(
    media_type: &str,
    bytes: &[u8],
    model_pin: &str,
    pages: Option<&[usize]>,
) -> Value {
    let mut body = json!({
        "model": model_pin,
        "document": document_payload(media_type, bytes),
        "include_image_base64": true,
    });
    if let (Some(pages), Some(object)) = (pages, body.as_object_mut()) {
        object.insert("pages".to_owned(), json!(pages));
    }
    body
}

fn parse_ocr_response(value: Value, model_pin: &str) -> Result<OcrResponse> {
    let pages = value
        .get("pages")
        .and_then(Value::as_array)
        .ok_or_else(|| AdapterError::ContractViolation("OCR response missing pages".to_owned()))?
        .iter()
        .enumerate()
        .map(|(fallback_index, page)| parse_ocr_page(page, fallback_index))
        .collect::<Result<Vec<_>>>()?;
    Ok(OcrResponse {
        pages,
        model_version_pin: value
            .get("model")
            .and_then(Value::as_str)
            .unwrap_or(model_pin)
            .to_owned(),
    })
}

fn parse_ocr_page(value: &Value, fallback_index: usize) -> Result<OcrPage> {
    let images = value
        .get("images")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .map(parse_ocr_image)
        .collect::<Result<Vec<_>>>()?;
    Ok(OcrPage {
        index: value
            .get("index")
            .and_then(Value::as_u64)
            .map(|index| index as usize)
            .unwrap_or(fallback_index),
        markdown: value
            .get("markdown")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned(),
        images,
    })
}

fn parse_ocr_image(value: &Value) -> Result<OcrImage> {
    let raw_base64 = value
        .get("image_base64")
        .or_else(|| value.get("base64"))
        .and_then(Value::as_str)
        .unwrap_or_default();
    let (media_type, data) = split_data_uri(raw_base64);
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(data)
        .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
    Ok(OcrImage {
        bytes,
        media_type: value
            .get("media_type")
            .and_then(Value::as_str)
            .unwrap_or(media_type)
            .to_owned(),
        bbox: parse_bbox(value.get("bbox").unwrap_or(value)),
        confidence: value.get("confidence").map(|confidence| {
            confidence
                .as_str()
                .map(str::to_owned)
                .unwrap_or_else(|| confidence.to_string())
        }),
    })
}

fn split_data_uri(value: &str) -> (&str, &str) {
    if let Some(rest) = value.strip_prefix("data:") {
        if let Some((media, data)) = rest.split_once(";base64,") {
            return (media, data);
        }
    }
    ("image/png", value)
}

fn parse_bbox(value: &Value) -> Option<[i64; 4]> {
    if let Some(array) = value.as_array() {
        if array.len() == 4 {
            return Some([
                array[0].as_i64()?,
                array[1].as_i64()?,
                array[2].as_i64()?,
                array[3].as_i64()?,
            ]);
        }
    }
    let x1 = value
        .get("top_left_x")
        .or_else(|| value.get("x"))
        .and_then(Value::as_i64)?;
    let y1 = value
        .get("top_left_y")
        .or_else(|| value.get("y"))
        .and_then(Value::as_i64)?;
    let x2 = value
        .get("bottom_right_x")
        .or_else(|| value.get("x2"))
        .and_then(Value::as_i64)
        .or_else(|| value.get("w").and_then(Value::as_i64).map(|w| x1 + w))?;
    let y2 = value
        .get("bottom_right_y")
        .or_else(|| value.get("y2"))
        .and_then(Value::as_i64)
        .or_else(|| value.get("h").and_then(Value::as_i64).map(|h| y1 + h))?;
    Some([x1, y1, x2, y2])
}

fn page_metadata(model_version_pin: &str, images: Option<&[OcrImage]>) -> BTreeMap<String, Value> {
    let mut metadata = BTreeMap::new();
    metadata.insert("model_version_pin".to_owned(), json!(model_version_pin));
    let image_values = images
        .unwrap_or(&[])
        .iter()
        .map(|image| {
            json!({
                "hash": image_hash(&image.bytes),
                "media_type": image.media_type,
                "bbox": image.bbox,
                "confidence": image.confidence,
            })
        })
        .collect::<Vec<_>>();
    if !image_values.is_empty() {
        metadata.insert("images".to_owned(), json!(image_values));
    }
    metadata
}

fn http_error(error: ureq::Error) -> AdapterError {
    match error {
        ureq::Error::Status(401 | 403, response) => {
            AdapterError::Auth(format!("Mistral OCR HTTP auth: {}", response.status_text()))
        }
        ureq::Error::Status(429, response) => {
            AdapterError::RateLimit(format!("Mistral OCR HTTP 429: {}", response.status_text()))
        }
        ureq::Error::Status(402, response) => AdapterError::QuotaExceeded(format!(
            "Mistral OCR HTTP quota: {}",
            response.status_text()
        )),
        ureq::Error::Status(code, response) => AdapterError::Network(format!(
            "Mistral OCR HTTP {code}: {}",
            response.status_text()
        )),
        ureq::Error::Transport(transport) => AdapterError::Network(transport.to_string()),
    }
}

#[must_use]
pub fn image_object_uri(scope_id: &str, image_hash: &str) -> String {
    format!("kcs://{scope_id}/object/image/{image_hash}")
}

#[must_use]
pub fn image_hash(bytes: &[u8]) -> String {
    hash_bytes(bytes)
}

/// Q2: crash-atomic write of an image CAS object. Writes to a uniquely-named temp
/// file in the destination directory, fsyncs it, then renames into place, so a
/// crash / ENOSPC mid-write can never leave a partial file under the final
/// `sha256:` name (which `if !path.exists()` would then adopt forever). The CLI's
/// `open`/`view` serve path verifies the object hash before serving, but the CAS
/// object itself must be written atomically so it is never partial in the first
/// place.
fn atomic_write_image_object(path: &Path, bytes: &[u8]) -> Result<()> {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let parent = path.parent().ok_or_else(|| AdapterError::Io {
        path: path.display().to_string(),
        message: "path has no parent".to_owned(),
    })?;
    std::fs::create_dir_all(parent).map_err(|err| AdapterError::Io {
        path: parent.display().to_string(),
        message: err.to_string(),
    })?;
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or_default();
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let temp = parent.join(format!(".tmp-{}-{}-{}", std::process::id(), nanos, seq));
    // R9-8: remove the temp on any write/sync/rename failure so a torn write does
    // not leave an orphan `.tmp-*` in the image CAS fanout dir (no GC before Step
    // 4). Same cleanup idiom as the core CAS writers.
    let result = (|| -> Result<()> {
        use std::io::Write as _;
        let mut file = std::fs::File::create(&temp).map_err(|err| AdapterError::Io {
            path: temp.display().to_string(),
            message: err.to_string(),
        })?;
        file.write_all(bytes).map_err(|err| AdapterError::Io {
            path: temp.display().to_string(),
            message: err.to_string(),
        })?;
        file.sync_all().map_err(|err| AdapterError::Io {
            path: temp.display().to_string(),
            message: err.to_string(),
        })?;
        drop(file);
        std::fs::rename(&temp, path).map_err(|err| AdapterError::Io {
            path: path.display().to_string(),
            message: err.to_string(),
        })
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&temp);
    }
    result
}

pub fn persist_images(kcs_dir: impl AsRef<Path>, images: &[OcrImage]) -> Result<Vec<String>> {
    let mut hashes = Vec::new();
    for image in images {
        let hash = image_hash(&image.bytes);
        let digest = hash.strip_prefix("sha256:").unwrap_or(&hash);
        let path = kcs_dir
            .as_ref()
            .join("objects/images")
            .join(&digest[0..2])
            .join(&digest[2..4])
            .join(&hash);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|err| AdapterError::Io {
                path: parent.display().to_string(),
                message: err.to_string(),
            })?;
        }
        if !path.exists() {
            // Q2: crash-atomic (temp + fsync + rename) so a torn write cannot leave
            // a partial image object under the final `sha256:` name.
            atomic_write_image_object(&path, &image.bytes)?;
        }
        hashes.push(hash);
    }
    Ok(hashes)
}

pub fn replace_image_placeholders(markdown: &str, scope_id: &str, images: &[OcrImage]) -> String {
    let mut output = String::with_capacity(markdown.len());
    let mut cursor = 0;
    for image in images {
        let uri = image_object_uri(scope_id, &image_hash(&image.bytes));
        let Some((target_start, target_end)) = next_markdown_image_target(markdown, cursor) else {
            break;
        };
        output.push_str(&markdown[cursor..target_start]);
        output.push_str(&uri);
        cursor = target_end;
    }
    output.push_str(&markdown[cursor..]);
    output
}

fn next_markdown_image_target(markdown: &str, cursor: usize) -> Option<(usize, usize)> {
    let image_start = markdown[cursor..].find("![")? + cursor;
    let label_end = markdown[image_start + 2..].find("](")? + image_start + 2;
    let target_start = label_end + 2;
    let relative_end = markdown[target_start..].find(')')?;
    let target_end = target_start + relative_end;
    Some((target_start, target_end))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::identity::{canonical_profile_value, jcs_bytes, tool_profile_hash};
    use serde_json::Value;
    use std::path::PathBuf;

    fn frozen_profile_value() -> Value {
        json!({
            "adapter_kind": "markdownize",
            "adapter_role": "multimodal",
            "model_or_tool_family": "mistral-ocr",
            "model_version_pin": "mistral-ocr-2505",
            "output_schema": "kcs-markdown-v1",
            "runtime_kind": "cloud",
            "spec_version": 1
        })
    }

    #[test]
    fn ct2_profile_001_tool_profile_hash_mistral() {
        assert_eq!(
            jcs_bytes(&canonical_profile_value(&frozen_profile_value()).unwrap()).unwrap(),
            br#"{"adapter_kind":"markdownize","adapter_role":"multimodal","model_or_tool_family":"mistral-ocr","model_version_pin":"mistral-ocr-2505","output_schema":"kcs-markdown-v1","runtime_kind":"cloud","spec_version":1}"#
        );
        assert_eq!(
            tool_profile_hash(&frozen_profile_value()).unwrap(),
            "sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed"
        );
    }

    #[test]
    fn r9_8_atomic_write_image_object_removes_temp_on_failure() {
        // R9-8: a torn image-object write must not leave an orphan `.tmp-*` in the
        // image CAS fanout dir. Force the rename to fail deterministically by
        // making the destination an existing directory (`rename(file, dir)` errors)
        // after the temp is created + fsynced.
        let dir = tempfile::tempdir().unwrap();
        let dest = dir.path().join("obj");
        std::fs::create_dir(&dest).unwrap();
        let result = atomic_write_image_object(&dest, b"image-bytes");
        assert!(result.is_err(), "write onto a directory must fail");
        let stray: Vec<_> = std::fs::read_dir(dir.path())
            .unwrap()
            .filter_map(std::result::Result::ok)
            .map(|entry| entry.file_name().to_string_lossy().into_owned())
            .filter(|name| name.starts_with(".tmp-"))
            .collect();
        assert!(
            stray.is_empty(),
            "temp not cleaned up on failure: {stray:?}"
        );
    }

    #[test]
    fn ct2_profile_003_null_fields_are_omitted() {
        let mut with_nulls = frozen_profile_value();
        for key in [
            "prompt_template_id",
            "prompt_template_hash",
            "sampling",
            "dimensions",
            "distance",
            "modality",
        ] {
            with_nulls[key] = Value::Null;
        }
        assert_eq!(
            tool_profile_hash(&with_nulls).unwrap(),
            tool_profile_hash(&frozen_profile_value()).unwrap()
        );
    }

    #[test]
    fn placeholder_mistral_profile_declares_ocr() {
        let adapter = MistralOcrMarkdownizeAdapter::default();
        let profile = adapter.profile();

        assert!(profile.capability_flags.iter().any(|flag| flag == "ocr"));
        assert_eq!(profile.adapter_id, "mistral_ocr_markdownize");
    }

    #[test]
    fn image_placeholders_become_object_uris_in_order() {
        let markdown = "![a](placeholder-1)\n\n![b](placeholder-2)\n";
        let replaced = replace_image_placeholders(
            markdown,
            "01H00000000000000000000000",
            &[
                OcrImage {
                    bytes: b"one".to_vec(),
                    media_type: "image/png".to_owned(),
                    bbox: None,
                    confidence: None,
                },
                OcrImage {
                    bytes: b"two".to_vec(),
                    media_type: "image/png".to_owned(),
                    bbox: None,
                    confidence: None,
                },
            ],
        );
        assert!(replaced.contains("kcs://01H00000000000000000000000/object/image/sha256:"));
        assert!(!replaced.contains("placeholder-1"));
        assert!(!replaced.contains("placeholder-2"));
    }

    #[test]
    fn ct2_image_001_embedded_image_hash_and_fanout() {
        let hash = image_hash(b"image bytes");
        assert!(hash.starts_with("sha256:"));
        let digest = hash.strip_prefix("sha256:").unwrap();
        let path = PathBuf::from(".kcs/objects/images")
            .join(&digest[0..2])
            .join(&digest[2..4])
            .join(&hash);
        assert!(path.ends_with(&hash));
    }

    // Q2: `persist_images` must write the image CAS object atomically so its bytes
    // always hash back to its `sha256:` filename (no torn / partial object under a
    // correct name).
    #[test]
    fn q2_persist_images_writes_hash_consistent_object() {
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        let images = vec![OcrImage {
            bytes: b"\x89PNG image payload bytes".to_vec(),
            media_type: "image/png".to_owned(),
            bbox: None,
            confidence: None,
        }];
        let hashes = persist_images(&kcs_dir, &images).unwrap();
        assert_eq!(hashes.len(), 1);
        let digest = hashes[0].strip_prefix("sha256:").unwrap();
        let path = kcs_dir
            .join("objects/images")
            .join(&digest[0..2])
            .join(&digest[2..4])
            .join(&hashes[0]);
        let written = std::fs::read(&path).unwrap();
        assert_eq!(written, images[0].bytes, "object bytes must be complete");
        assert_eq!(
            image_hash(&written),
            hashes[0],
            "object must hash back to its filename"
        );
    }

    // R14-4: incremental must restrict the OCR request to the changed+added pages (the
    // 0-based `order` from `prepared_unit_hint`) via the `pages` parameter, so only those
    // pages are processed/billed. Full sends no `pages` (whole document). Before R14-4 the
    // real client ignored the hint and always sent every page (the mock seam hid it).
    use crate::types::{RawInput, UnitKind};

    fn hint(unit_key: &str, order: u64) -> PreparedUnitHint {
        PreparedUnitHint {
            unit_key: unit_key.to_owned(),
            prepared_hash: format!("sha256:{order:0>64}"),
            unit_kind: UnitKind::Page,
            order,
        }
    }

    fn markdownize_request(
        mode: MarkdownizeMode,
        hints: Vec<PreparedUnitHint>,
    ) -> MarkdownizeRequest {
        MarkdownizeRequest {
            raw: RawInput {
                raw_hash: "sha256:raw".to_owned(),
                path: Some("/tmp/doc.pdf".to_owned()),
            },
            media_type: "application/pdf".to_owned(),
            prepared_unit_hint: Some(hints),
            mode,
            previous: None,
            hints: None,
            tool_profile_hash: String::new(),
            spec_version: 1,
        }
    }

    #[test]
    fn r14_4_incremental_scopes_pages_to_changed_units() {
        // Changed+added units are page:2 (order 1) and page:4 (order 3).
        let request = markdownize_request(
            MarkdownizeMode::Incremental,
            vec![hint("page:2", 1), hint("page:4", 3)],
        );
        let pages = request_pages(&request);
        assert_eq!(
            pages,
            Some(vec![1, 3]),
            "incremental must scope the OCR to the hinted 0-based page orders"
        );
        let body = ocr_request_body(
            "application/pdf",
            b"pdf-bytes",
            "mistral-ocr-2505",
            pages.as_deref(),
        );
        assert_eq!(
            body["pages"],
            json!([1, 3]),
            "the request body must carry exactly the scoped pages"
        );
        assert_eq!(body["model"], "mistral-ocr-2505");
        assert!(
            body.get("document").is_some(),
            "the document payload is always present"
        );
    }

    #[test]
    fn r14_4_full_send_has_no_pages_parameter() {
        let request = markdownize_request(
            MarkdownizeMode::Full,
            vec![hint("page:1", 0), hint("page:2", 1)],
        );
        assert_eq!(
            request_pages(&request),
            None,
            "Full must not restrict the pages"
        );
        let body = ocr_request_body("application/pdf", b"pdf-bytes", "mistral-ocr-2505", None);
        assert!(
            body.get("pages").is_none(),
            "Full must send no `pages` parameter (process the whole document)"
        );
    }
}
