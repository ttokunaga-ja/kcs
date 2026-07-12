//! Mistral OCR markdownize adapter.

use crate::http_policy::{
    authenticated_agent, read_json_bounded, HttpPolicy, MODEL_CATALOG_MAX_BYTES,
    OCR_RESPONSE_MAX_BYTES,
};
use crate::identity::hash_bytes;
use crate::traits::MarkdownizeAdapter;
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownUnit, MarkdownizeMode, MarkdownizeRequest,
    MarkdownizeResponse, PreparedUnitHint,
};
use crate::{AdapterError, Result};
use base64::Engine;
use serde_json::{json, Value};
use std::borrow::Cow;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

const MISTRAL_API_ORIGIN: &str = "https://api.mistral.ai";

#[derive(Debug, Clone, Copy)]
struct OcrResponsePolicy {
    max_pages: usize,
    max_markdown_bytes_per_page: usize,
    max_markdown_bytes_total: usize,
    max_images_per_page: usize,
    max_images_total: usize,
    max_encoded_image_bytes: usize,
    max_decoded_image_bytes: usize,
    max_decoded_image_bytes_total: usize,
    max_persisted_image_bytes: usize,
}

impl Default for OcrResponsePolicy {
    fn default() -> Self {
        Self {
            max_pages: 10_000,
            max_markdown_bytes_per_page: 4 * 1024 * 1024,
            max_markdown_bytes_total: 32 * 1024 * 1024,
            max_images_per_page: 256,
            max_images_total: 4_096,
            max_encoded_image_bytes: 16 * 1024 * 1024,
            max_decoded_image_bytes: 12 * 1024 * 1024,
            max_decoded_image_bytes_total: 48 * 1024 * 1024,
            max_persisted_image_bytes: 48 * 1024 * 1024,
        }
    }
}

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

    fn ocr_markdown(
        &self,
        request: &MarkdownizeRequest,
        model_pin: &str,
        verified_raw_bytes: &[u8],
    ) -> Result<OcrResponse>;
}

#[derive(Debug, Clone, Default)]
pub struct EnvMistralOcrClient {
    base_url: Option<String>,
    http_policy: HttpPolicy,
    response_policy: OcrResponsePolicy,
}

impl EnvMistralOcrClient {
    #[must_use]
    pub fn new() -> Self {
        Self {
            base_url: None,
            http_policy: HttpPolicy::default(),
            response_policy: OcrResponsePolicy::default(),
        }
    }

    #[allow(dead_code)]
    #[must_use]
    pub fn with_base_url(base_url: impl Into<String>) -> Self {
        Self {
            base_url: Some(base_url.into()),
            http_policy: HttpPolicy::default(),
            response_policy: OcrResponsePolicy::default(),
        }
    }

    fn base_url(&self) -> String {
        self.base_url
            .clone()
            .or_else(|| {
                crate::tool_lock::registered_declared_adapter("markdown")
                    .is_none()
                    .then(|| std::env::var("MISTRAL_API_BASE").ok())
                    .flatten()
            })
            .unwrap_or_else(|| MISTRAL_API_ORIGIN.to_owned())
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
        let response = authenticated_agent(self.http_policy)
            .get(&format!("{}/v1/models", self.base_url()))
            .set("Authorization", &format!("Bearer {api_key}"))
            .set("Accept-Encoding", "identity")
            .call()
            .map_err(http_error)?;
        let value = read_json_bounded(
            response,
            MODEL_CATALOG_MAX_BYTES,
            "Mistral model catalog response",
        )?;
        let family = configured_model.trim_end_matches("-latest");
        let models = value.get("data").and_then(Value::as_array).ok_or_else(|| {
            AdapterError::ContractViolation("Mistral model catalog missing data".to_owned())
        })?;
        if models.len() > 10_000 {
            return Err(AdapterError::ContractViolation(
                "Mistral model catalog has too many entries".to_owned(),
            ));
        }
        if models.iter().any(|model| {
            model
                .get("id")
                .and_then(Value::as_str)
                .is_some_and(|id| id.len() > 512)
        }) {
            return Err(AdapterError::ContractViolation(
                "Mistral model identifier exceeds 512 bytes".to_owned(),
            ));
        }
        models
            .iter()
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

    fn ocr_markdown(
        &self,
        request: &MarkdownizeRequest,
        model_pin: &str,
        verified_raw_bytes: &[u8],
    ) -> Result<OcrResponse> {
        let api_key = Self::api_key()?;
        // R14-4: in incremental mode, restrict the OCR request to the changed+added
        // pages via the `pages` parameter (built from `prepared_unit_hint`), instead of
        // silently sending — and re-billing — the whole document every revision. Full
        // mode sends no `pages` (process the entire document).
        let pages = request_pages(request)?;
        let expected_pages = expected_page_indices(request)?;
        let response = authenticated_agent(self.http_policy)
            .post(&format!("{}/v1/ocr", self.base_url()))
            .set("Authorization", &format!("Bearer {api_key}"))
            .set("Content-Type", "application/json")
            .set("Accept-Encoding", "identity")
            .send_json(ocr_request_body(
                &request.media_type,
                verified_raw_bytes,
                model_pin,
                pages.as_deref(),
            ))
            .map_err(http_error)?;
        let value = read_json_bounded(response, OCR_RESPONSE_MAX_BYTES, "Mistral OCR response")?;
        parse_ocr_response(
            value,
            model_pin,
            expected_pages.as_deref(),
            self.response_policy,
        )
    }
}

#[derive(Debug, Clone)]
pub struct MistralOcrMarkdownizeAdapter<C = EnvMistralOcrClient> {
    client: C,
    configured_model: String,
    scope_id: String,
    image_store_dir: Option<PathBuf>,
    verified_raw_bytes: Option<Vec<u8>>,
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
            verified_raw_bytes: None,
        }
    }

    #[must_use]
    pub fn with_image_store(mut self, kcs_dir: impl Into<PathBuf>) -> Self {
        self.image_store_dir = Some(kcs_dir.into());
        self
    }

    #[must_use]
    pub fn with_verified_raw_bytes(mut self, bytes: impl Into<Vec<u8>>) -> Self {
        self.verified_raw_bytes = Some(bytes.into());
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
        let raw_bytes: Cow<'_, [u8]> = if let Some(bytes) = self.verified_raw_bytes.as_deref() {
            Cow::Borrowed(bytes)
        } else {
            let path = request.raw.path.as_deref().ok_or_else(|| {
                AdapterError::ContractViolation(
                    "Mistral OCR requires verified raw bytes or a local raw path".to_owned(),
                )
            })?;
            let owned_bytes = std::fs::read(path).map_err(|err| AdapterError::Io {
                path: path.to_owned(),
                message: err.to_string(),
            })?;
            Cow::Owned(owned_bytes)
        };
        let actual_hash = hash_bytes(raw_bytes.as_ref());
        if actual_hash != request.raw.raw_hash {
            return Err(AdapterError::ContractViolation(format!(
                "OCR input identity changed: expected {}, got {actual_hash}",
                request.raw.raw_hash
            )));
        }
        let model_pin = self.client.resolve_model_pin(&self.configured_model)?;
        let ocr = self
            .client
            .ocr_markdown(&request, &model_pin, raw_bytes.as_ref())?;
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
        let pages_by_index = verified_pages_by_index(&ocr.pages, &hints)?;
        if let Some(kcs_dir) = &self.image_store_dir {
            let images = ocr
                .pages
                .iter()
                .flat_map(|page| page.images.iter())
                .collect::<Vec<_>>();
            persist_image_refs_bounded(
                kcs_dir,
                &images,
                OcrResponsePolicy::default().max_persisted_image_bytes,
            )?;
        }
        Ok(MarkdownizeResponse {
            mode_used: request.mode,
            updated_units: hints
                .iter()
                .map(|hint| {
                    let page_index = usize::try_from(hint.order).map_err(|_| {
                        AdapterError::ContractViolation(
                            "prepared page order exceeds platform range".to_owned(),
                        )
                    })?;
                    let page = pages_by_index.get(&page_index).copied().ok_or_else(|| {
                        AdapterError::ContractViolation(format!(
                            "OCR response missing page index {page_index}"
                        ))
                    })?;
                    let markdown =
                        replace_image_placeholders(&page.markdown, &self.scope_id, &page.images);
                    Ok(MarkdownUnit {
                        unit_key: hint.unit_key.clone(),
                        unit_type: hint.unit_kind,
                        markdown,
                        metadata: page_metadata(
                            &ocr.model_version_pin,
                            Some(page.images.as_slice()),
                        ),
                    })
                })
                .collect::<Result<Vec<_>>>()?,
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

/// R14-4 / R15-5: the 0-indexed pages an OCR request should process. Page scoping
/// applies when EITHER the mode is `Incremental` (changed+added units, R14-4) OR
/// `restrict_to_hint_pages` is set (a unit-scoped retry re-sending only the failed
/// subset with `mode = Full`, R15-5). In both cases the pages are the `order`s carried
/// in `prepared_unit_hint` (`prepare` assigns them 0-based — page:1 → 0, page:2 → 1, …).
/// A FRESH full send (neither flag) returns `None` = process every page. Before R14-4
/// the real client ignored the hint and always sent the whole document; before R15-5 a
/// unit-scoped retry did too (its `mode` is `Full`), so the ledger's prorated reserve
/// diverged from the real all-pages bill.
fn request_pages(request: &MarkdownizeRequest) -> Result<Option<Vec<usize>>> {
    if request.mode != MarkdownizeMode::Incremental && !request.restrict_to_hint_pages {
        return Ok(None);
    }
    request
        .prepared_unit_hint
        .as_deref()
        .unwrap_or(&[])
        .iter()
        .map(|hint| {
            usize::try_from(hint.order).map_err(|_| {
                AdapterError::ContractViolation(
                    "prepared page order exceeds platform range".to_owned(),
                )
            })
        })
        .collect::<Result<Vec<_>>>()
        .map(Some)
}

fn expected_page_indices(request: &MarkdownizeRequest) -> Result<Option<Vec<usize>>> {
    let Some(hints) = request.prepared_unit_hint.as_deref() else {
        return Ok(None);
    };
    if hints.is_empty() {
        return Ok(None);
    }
    hints
        .iter()
        .map(|hint| {
            usize::try_from(hint.order).map_err(|_| {
                AdapterError::ContractViolation(
                    "prepared page order exceeds platform range".to_owned(),
                )
            })
        })
        .collect::<Result<Vec<_>>>()
        .map(Some)
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

fn parse_ocr_response(
    value: Value,
    model_pin: &str,
    expected_page_indices: Option<&[usize]>,
    policy: OcrResponsePolicy,
) -> Result<OcrResponse> {
    let page_values = value
        .get("pages")
        .and_then(Value::as_array)
        .ok_or_else(|| AdapterError::ContractViolation("OCR response missing pages".to_owned()))?;
    if page_values.len() > policy.max_pages {
        return Err(AdapterError::ContractViolation(format!(
            "OCR response has more than {} pages",
            policy.max_pages
        )));
    }
    if let Some(expected) = expected_page_indices {
        if page_values.len() != expected.len() {
            return Err(AdapterError::ContractViolation(
                "OCR response page count does not match requested pages".to_owned(),
            ));
        }
    }

    let explicit_count = page_values
        .iter()
        .filter(|page| page.get("index").is_some())
        .count();
    if explicit_count != 0 && explicit_count != page_values.len() {
        return Err(AdapterError::ContractViolation(
            "OCR response mixes explicit and omitted page indices".to_owned(),
        ));
    }
    let all_indices_omitted = explicit_count == 0;
    let mut markdown_total = 0_usize;
    let mut image_total = 0_usize;
    let mut decoded_total = 0_usize;
    let mut seen_indices = BTreeSet::new();
    let mut pages = Vec::with_capacity(page_values.len());
    for (position, page) in page_values.iter().enumerate() {
        let fallback_index = if all_indices_omitted {
            expected_page_indices
                .and_then(|expected| expected.get(position).copied())
                .unwrap_or(position)
        } else {
            position
        };
        let parsed = parse_ocr_page(
            page,
            fallback_index,
            policy,
            &mut markdown_total,
            &mut image_total,
            &mut decoded_total,
        )?;
        if !seen_indices.insert(parsed.index) {
            return Err(AdapterError::ContractViolation(format!(
                "duplicate OCR page index {}",
                parsed.index
            )));
        }
        pages.push(parsed);
    }
    if let Some(expected) = expected_page_indices {
        let expected = expected.iter().copied().collect::<BTreeSet<_>>();
        if seen_indices != expected {
            return Err(AdapterError::ContractViolation(
                "OCR page indices do not exactly match requested pages".to_owned(),
            ));
        }
    }
    Ok(OcrResponse {
        pages,
        model_version_pin: value
            .get("model")
            .and_then(Value::as_str)
            .unwrap_or(model_pin)
            .to_owned(),
    })
}

fn parse_ocr_page(
    value: &Value,
    fallback_index: usize,
    policy: OcrResponsePolicy,
    markdown_total: &mut usize,
    image_total: &mut usize,
    decoded_total: &mut usize,
) -> Result<OcrPage> {
    let markdown = value
        .get("markdown")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if markdown.len() > policy.max_markdown_bytes_per_page {
        return Err(AdapterError::ContractViolation(
            "OCR page markdown exceeds per-page limit".to_owned(),
        ));
    }
    *markdown_total = markdown_total.checked_add(markdown.len()).ok_or_else(|| {
        AdapterError::ContractViolation("OCR markdown byte count overflow".to_owned())
    })?;
    if *markdown_total > policy.max_markdown_bytes_total {
        return Err(AdapterError::ContractViolation(
            "OCR markdown exceeds aggregate limit".to_owned(),
        ));
    }

    let image_values = value
        .get("images")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
    if image_values.len() > policy.max_images_per_page {
        return Err(AdapterError::ContractViolation(
            "OCR image count exceeds per-page limit".to_owned(),
        ));
    }
    *image_total = image_total
        .checked_add(image_values.len())
        .ok_or_else(|| AdapterError::ContractViolation("OCR image count overflow".to_owned()))?;
    if *image_total > policy.max_images_total {
        return Err(AdapterError::ContractViolation(
            "OCR image count exceeds aggregate limit".to_owned(),
        ));
    }
    let images = image_values
        .into_iter()
        .map(|image| parse_ocr_image(image, policy, decoded_total))
        .collect::<Result<Vec<_>>>()?;
    let index = match value.get("index") {
        Some(index) => {
            let raw = index.as_u64().ok_or_else(|| {
                AdapterError::ContractViolation(
                    "OCR page index must be a non-negative integer".to_owned(),
                )
            })?;
            usize::try_from(raw).map_err(|_| {
                AdapterError::ContractViolation("OCR page index exceeds platform range".to_owned())
            })?
        }
        None => fallback_index,
    };
    Ok(OcrPage {
        index,
        markdown: markdown.to_owned(),
        images,
    })
}

fn parse_ocr_image(
    value: &Value,
    policy: OcrResponsePolicy,
    decoded_total: &mut usize,
) -> Result<OcrImage> {
    let raw_base64 = value
        .get("image_base64")
        .or_else(|| value.get("base64"))
        .and_then(Value::as_str)
        .unwrap_or_default();
    let (media_type, data) = split_data_uri(raw_base64);
    if data.len() > policy.max_encoded_image_bytes {
        return Err(AdapterError::ContractViolation(
            "OCR encoded image exceeds per-image limit".to_owned(),
        ));
    }
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(data)
        .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
    if bytes.len() > policy.max_decoded_image_bytes {
        return Err(AdapterError::ContractViolation(
            "OCR decoded image exceeds per-image limit".to_owned(),
        ));
    }
    *decoded_total = decoded_total.checked_add(bytes.len()).ok_or_else(|| {
        AdapterError::ContractViolation("OCR decoded image byte count overflow".to_owned())
    })?;
    if *decoded_total > policy.max_decoded_image_bytes_total {
        return Err(AdapterError::ContractViolation(
            "OCR decoded images exceed aggregate limit".to_owned(),
        ));
    }
    let bbox_value = value
        .get("bbox")
        .filter(|bbox| !bbox.is_null())
        .or_else(|| {
            [
                "top_left_x",
                "x",
                "top_left_y",
                "y",
                "bottom_right_x",
                "x2",
                "w",
                "bottom_right_y",
                "y2",
                "h",
            ]
            .iter()
            .any(|field| value.get(*field).is_some())
            .then_some(value)
        });
    Ok(OcrImage {
        bytes,
        media_type: value
            .get("media_type")
            .and_then(Value::as_str)
            .unwrap_or(media_type)
            .to_owned(),
        bbox: bbox_value.map(parse_bbox).transpose()?.flatten(),
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

fn parse_bbox(value: &Value) -> Result<Option<[i64; 4]>> {
    if let Some(array) = value.as_array() {
        if array.len() != 4 {
            return Err(AdapterError::ContractViolation(
                "OCR bounding box array must have four coordinates".to_owned(),
            ));
        }
        let bbox = [
            bbox_integer(&array[0])?,
            bbox_integer(&array[1])?,
            bbox_integer(&array[2])?,
            bbox_integer(&array[3])?,
        ];
        return valid_bbox(bbox).map(Some);
    }
    let x1 = value
        .get("top_left_x")
        .or_else(|| value.get("x"))
        .ok_or_else(|| AdapterError::ContractViolation("OCR bbox missing x".to_owned()))
        .and_then(bbox_integer)?;
    let y1 = value
        .get("top_left_y")
        .or_else(|| value.get("y"))
        .ok_or_else(|| AdapterError::ContractViolation("OCR bbox missing y".to_owned()))
        .and_then(bbox_integer)?;
    let x2 = match value.get("bottom_right_x").or_else(|| value.get("x2")) {
        Some(value) => bbox_integer(value)?,
        None => checked_extent(x1, value.get("w"), "width")?,
    };
    let y2 = match value.get("bottom_right_y").or_else(|| value.get("y2")) {
        Some(value) => bbox_integer(value)?,
        None => checked_extent(y1, value.get("h"), "height")?,
    };
    valid_bbox([x1, y1, x2, y2]).map(Some)
}

fn bbox_integer(value: &Value) -> Result<i64> {
    value.as_i64().ok_or_else(|| {
        AdapterError::ContractViolation("OCR bbox coordinates must be integers".to_owned())
    })
}

fn checked_extent(start: i64, value: Option<&Value>, label: &str) -> Result<i64> {
    let extent = value
        .ok_or_else(|| AdapterError::ContractViolation(format!("OCR bbox missing {label}")))
        .and_then(bbox_integer)?;
    if extent < 0 {
        return Err(AdapterError::ContractViolation(format!(
            "OCR bbox {label} must be non-negative"
        )));
    }
    start.checked_add(extent).ok_or_else(|| {
        AdapterError::ContractViolation(format!("OCR bbox {label} overflows coordinate range"))
    })
}

fn valid_bbox([x1, y1, x2, y2]: [i64; 4]) -> Result<[i64; 4]> {
    if x2 < x1 || y2 < y1 {
        return Err(AdapterError::ContractViolation(
            "OCR bounding box has inverted geometry".to_owned(),
        ));
    }
    Ok([x1, y1, x2, y2])
}

fn verified_pages_by_index<'a>(
    pages: &'a [OcrPage],
    hints: &[PreparedUnitHint],
) -> Result<BTreeMap<usize, &'a OcrPage>> {
    let mut expected = BTreeSet::new();
    for hint in hints {
        let index = usize::try_from(hint.order).map_err(|_| {
            AdapterError::ContractViolation("prepared page order exceeds platform range".to_owned())
        })?;
        if !expected.insert(index) {
            return Err(AdapterError::ContractViolation(format!(
                "duplicate prepared page order {index}"
            )));
        }
    }
    let mut by_index = BTreeMap::new();
    for page in pages {
        if by_index.insert(page.index, page).is_some() {
            return Err(AdapterError::ContractViolation(format!(
                "duplicate OCR page index {}",
                page.index
            )));
        }
    }
    if by_index.keys().copied().collect::<BTreeSet<_>>() != expected {
        return Err(AdapterError::ContractViolation(
            "OCR response page indices do not exactly match prepared units".to_owned(),
        ));
    }
    Ok(by_index)
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
/// digest leaf (which an existence check would then adopt forever). The CLI's
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

#[cfg(test)]
fn persist_images(kcs_dir: impl AsRef<Path>, images: &[OcrImage]) -> Result<Vec<String>> {
    let image_refs = images.iter().collect::<Vec<_>>();
    persist_image_refs_bounded(
        kcs_dir,
        &image_refs,
        OcrResponsePolicy::default().max_persisted_image_bytes,
    )
}

fn image_hash_digest(hash: &str) -> Result<&str> {
    let digest = hash
        .strip_prefix("sha256:")
        .ok_or_else(|| AdapterError::ContractViolation("image hash must use sha256".to_owned()))?;
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(AdapterError::ContractViolation(
            "image hash must contain a complete SHA-256 digest".to_owned(),
        ));
    }
    Ok(digest)
}

fn image_object_path(kcs_dir: &Path, hash: &str) -> Result<PathBuf> {
    let digest = image_hash_digest(hash)?;
    Ok(kcs_dir
        .join("objects/images")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(digest))
}

#[cfg(not(windows))]
fn legacy_image_object_path(kcs_dir: &Path, hash: &str) -> Result<PathBuf> {
    let digest = image_hash_digest(hash)?;
    Ok(kcs_dir
        .join("objects/images")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(hash))
}

fn image_object_slot_exists(path: &Path) -> Result<bool> {
    match std::fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(err) => Err(AdapterError::Io {
            path: path.display().to_string(),
            message: err.to_string(),
        }),
    }
}

fn existing_image_object_paths(kcs_dir: &Path, hash: &str) -> Result<Vec<PathBuf>> {
    let canonical = image_object_path(kcs_dir, hash)?;
    let mut paths = Vec::with_capacity(2);
    if image_object_slot_exists(&canonical)? {
        paths.push(canonical);
    }
    #[cfg(not(windows))]
    {
        let legacy = legacy_image_object_path(kcs_dir, hash)?;
        if image_object_slot_exists(&legacy)? {
            paths.push(legacy);
        }
    }
    Ok(paths)
}

fn verify_existing_image_object(path: &Path, hash: &str, max_bytes: usize) -> Result<()> {
    use std::io::Read as _;

    let listed = std::fs::symlink_metadata(path).map_err(|err| AdapterError::Io {
        path: path.display().to_string(),
        message: err.to_string(),
    })?;
    if !listed.file_type().is_file() {
        return Err(AdapterError::ContractViolation(format!(
            "existing image object is not a regular file: {}",
            path.display()
        )));
    }
    let max_bytes_u64 = u64::try_from(max_bytes).unwrap_or(u64::MAX);
    if listed.len() > max_bytes_u64 {
        return Err(AdapterError::ContractViolation(format!(
            "existing image object exceeds verification limit: {}",
            path.display()
        )));
    }

    let mut file = std::fs::File::open(path).map_err(|err| AdapterError::Io {
        path: path.display().to_string(),
        message: err.to_string(),
    })?;
    let opened = file.metadata().map_err(|err| AdapterError::Io {
        path: path.display().to_string(),
        message: err.to_string(),
    })?;
    if !opened.is_file() {
        return Err(AdapterError::ContractViolation(format!(
            "existing image object is not a regular file: {}",
            path.display()
        )));
    }
    if opened.len() > max_bytes_u64 {
        return Err(AdapterError::ContractViolation(format!(
            "existing image object exceeds verification limit: {}",
            path.display()
        )));
    }

    let mut existing = Vec::new();
    (&mut file)
        .take(max_bytes_u64.saturating_add(1))
        .read_to_end(&mut existing)
        .map_err(|err| AdapterError::Io {
            path: path.display().to_string(),
            message: err.to_string(),
        })?;
    if existing.len() > max_bytes {
        return Err(AdapterError::ContractViolation(format!(
            "existing image object exceeds verification limit: {}",
            path.display()
        )));
    }
    if image_hash(&existing) != hash {
        return Err(AdapterError::ContractViolation(format!(
            "existing image object does not match its hash: {}",
            path.display()
        )));
    }
    Ok(())
}

fn persist_image_refs_bounded(
    kcs_dir: impl AsRef<Path>,
    images: &[&OcrImage],
    max_new_bytes: usize,
) -> Result<Vec<String>> {
    let kcs_dir = kcs_dir.as_ref();
    let mut unique = BTreeMap::<String, &[u8]>::new();
    for image in images {
        let hash = image_hash(&image.bytes);
        unique.entry(hash).or_insert(image.bytes.as_slice());
    }

    let mut new_bytes = 0_usize;
    let mut hashes_to_write = BTreeSet::new();
    for (hash, bytes) in &unique {
        let existing_paths = existing_image_object_paths(kcs_dir, hash)?;
        if existing_paths.is_empty() {
            new_bytes = new_bytes.checked_add(bytes.len()).ok_or_else(|| {
                AdapterError::ContractViolation("image persistence byte count overflow".to_owned())
            })?;
            if new_bytes > max_new_bytes {
                return Err(AdapterError::QuotaExceeded(format!(
                    "OCR images require {new_bytes} new bytes, limit is {max_new_bytes}"
                )));
            }
            hashes_to_write.insert(hash.clone());
        } else {
            // Verify every occupied representation. A valid canonical object must not
            // shadow a corrupt legacy object, or vice versa.
            for path in existing_paths {
                verify_existing_image_object(&path, hash, max_new_bytes)?;
            }
        }
    }

    for (hash, bytes) in unique {
        if !hashes_to_write.contains(&hash) {
            continue;
        }
        let raced_paths = existing_image_object_paths(kcs_dir, &hash)?;
        if !raced_paths.is_empty() {
            for path in raced_paths {
                verify_existing_image_object(&path, &hash, max_new_bytes)?;
            }
            continue;
        }
        let path = image_object_path(kcs_dir, &hash)?;
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|err| AdapterError::Io {
                path: parent.display().to_string(),
                message: err.to_string(),
            })?;
        }
        // Q2: crash-atomic (temp + fsync + rename) so a torn write cannot leave
        // a partial image object under the final digest leaf.
        atomic_write_image_object(&path, bytes)?;
        let published_paths = existing_image_object_paths(kcs_dir, &hash)?;
        if published_paths.is_empty() {
            return Err(AdapterError::ContractViolation(format!(
                "published image object is missing: {}",
                path.display()
            )));
        }
        for published_path in published_paths {
            verify_existing_image_object(&published_path, &hash, max_new_bytes)?;
        }
    }
    Ok(images
        .iter()
        .map(|image| image_hash(&image.bytes))
        .collect())
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
        let path = image_object_path(Path::new(".kcs"), &hash).unwrap();
        assert_eq!(
            path,
            PathBuf::from(".kcs/objects/images")
                .join(&digest[0..2])
                .join(&digest[2..4])
                .join(digest)
        );
        assert!(!path.file_name().unwrap().to_string_lossy().contains(':'));
        assert!(
            image_object_path(Path::new(".kcs"), &format!("sha256:{}", "A".repeat(64))).is_err()
        );
    }

    // Q2: `persist_images` must write the image CAS object atomically so its bytes
    // always hash back to the logical `sha256:` identity encoded by its digest leaf
    // (no torn / partial object under a correct name).
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
        let path = image_object_path(&kcs_dir, &hashes[0]).unwrap();
        assert_eq!(path.file_name().unwrap(), digest);
        let written = std::fs::read(&path).unwrap();
        assert_eq!(written, images[0].bytes, "object bytes must be complete");
        assert_eq!(
            image_hash(&written),
            hashes[0],
            "object must hash back to its filename"
        );
    }

    #[cfg(not(windows))]
    #[test]
    fn legacy_image_object_is_verified_and_reused() {
        let dir = tempfile::tempdir().unwrap();
        let image = OcrImage {
            bytes: b"legacy image bytes".to_vec(),
            media_type: "image/png".to_owned(),
            bbox: None,
            confidence: None,
        };
        let hash = image_hash(&image.bytes);
        let canonical = image_object_path(dir.path(), &hash).unwrap();
        let legacy = legacy_image_object_path(dir.path(), &hash).unwrap();
        std::fs::create_dir_all(legacy.parent().unwrap()).unwrap();
        std::fs::write(&legacy, &image.bytes).unwrap();

        let hashes = persist_image_refs_bounded(dir.path(), &[&image], 1024).unwrap();
        assert_eq!(hashes, vec![hash]);
        assert_eq!(std::fs::read(&legacy).unwrap(), image.bytes);
        assert!(
            !canonical.exists(),
            "a verified legacy object must be reused without an unbudgeted migration write"
        );
    }

    #[cfg(not(windows))]
    #[test]
    fn canonical_and_legacy_image_objects_must_both_verify() {
        let image = OcrImage {
            bytes: b"authentic image bytes".to_vec(),
            media_type: "image/png".to_owned(),
            bbox: None,
            confidence: None,
        };
        let hash = image_hash(&image.bytes);

        let valid_dir = tempfile::tempdir().unwrap();
        let valid_canonical = image_object_path(valid_dir.path(), &hash).unwrap();
        let valid_legacy = legacy_image_object_path(valid_dir.path(), &hash).unwrap();
        std::fs::create_dir_all(valid_canonical.parent().unwrap()).unwrap();
        std::fs::write(&valid_canonical, &image.bytes).unwrap();
        std::fs::write(&valid_legacy, &image.bytes).unwrap();
        assert_eq!(
            persist_image_refs_bounded(valid_dir.path(), &[&image], image.bytes.len()).unwrap(),
            vec![hash.clone()]
        );

        for corrupt_canonical in [false, true] {
            let dir = tempfile::tempdir().unwrap();
            let canonical = image_object_path(dir.path(), &hash).unwrap();
            let legacy = legacy_image_object_path(dir.path(), &hash).unwrap();
            std::fs::create_dir_all(canonical.parent().unwrap()).unwrap();
            let canonical_bytes: &[u8] = if corrupt_canonical {
                b"corrupt canonical"
            } else {
                image.bytes.as_slice()
            };
            let legacy_bytes: &[u8] = if corrupt_canonical {
                image.bytes.as_slice()
            } else {
                b"corrupt legacy"
            };
            std::fs::write(&canonical, canonical_bytes).unwrap();
            std::fs::write(&legacy, legacy_bytes).unwrap();

            let error = persist_image_refs_bounded(dir.path(), &[&image], 1024).unwrap_err();
            assert!(matches!(error, AdapterError::ContractViolation(message)
                if message.contains("does not match its hash")));
        }
    }

    #[test]
    fn existing_image_object_type_and_size_are_checked_before_hashing() {
        let image = OcrImage {
            bytes: b"eight123".to_vec(),
            media_type: "image/png".to_owned(),
            bbox: None,
            confidence: None,
        };
        let hash = image_hash(&image.bytes);

        let type_dir = tempfile::tempdir().unwrap();
        let type_path = image_object_path(type_dir.path(), &hash).unwrap();
        std::fs::create_dir_all(&type_path).unwrap();
        let type_error = persist_image_refs_bounded(type_dir.path(), &[&image], 1024).unwrap_err();
        assert!(
            matches!(type_error, AdapterError::ContractViolation(message)
            if message.contains("not a regular file"))
        );

        let size_dir = tempfile::tempdir().unwrap();
        let size_path = image_object_path(size_dir.path(), &hash).unwrap();
        std::fs::create_dir_all(size_path.parent().unwrap()).unwrap();
        std::fs::write(&size_path, &image.bytes).unwrap();
        let size_error = persist_image_refs_bounded(size_dir.path(), &[&image], 7).unwrap_err();
        assert!(
            matches!(size_error, AdapterError::ContractViolation(message)
            if message.contains("exceeds verification limit"))
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
            restrict_to_hint_pages: false,
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
        let pages = request_pages(&request).unwrap();
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
            request_pages(&request).unwrap(),
            None,
            "Full must not restrict the pages"
        );
        let body = ocr_request_body("application/pdf", b"pdf-bytes", "mistral-ocr-2505", None);
        assert!(
            body.get("pages").is_none(),
            "Full must send no `pages` parameter (process the whole document)"
        );
    }

    // R15-5: a unit-scoped retry re-sends ONLY the failed subset (here page:3, order 2)
    // but with `mode = Full` (previous/hints are None). Keying page scoping on
    // Incremental alone (R14-4) let the real client send NO `pages` → whole-document
    // OCR/billing while the ledger reserved just the subset. `restrict_to_hint_pages`
    // scopes the real send to the hinted orders regardless of mode. A FRESH full send
    // (the test above) leaves the flag false and still sends no `pages`.
    #[test]
    fn r15_5_unit_scoped_retry_scopes_pages_despite_full_mode() {
        let mut request = markdownize_request(MarkdownizeMode::Full, vec![hint("page:3", 2)]);
        request.restrict_to_hint_pages = true;
        let pages = request_pages(&request).unwrap();
        assert_eq!(
            pages,
            Some(vec![2]),
            "a restricted retry must scope pages to the failed subset even in Full mode"
        );
        let body = ocr_request_body(
            "application/pdf",
            b"pdf-bytes",
            "mistral-ocr-2505",
            pages.as_deref(),
        );
        assert_eq!(
            body["pages"],
            json!([2]),
            "the retry request body must carry exactly the failed subset's pages"
        );
    }

    #[test]
    fn bbox_arithmetic_and_geometry_are_checked() {
        assert!(parse_bbox(&json!({"x": i64::MAX, "y": 0, "w": 1, "h": 1})).is_err());
        assert!(parse_bbox(&json!({"x": 10, "y": 5, "w": -1, "h": 7})).is_err());
        assert!(parse_bbox(&json!([10, 5, 9, 12])).is_err());
        assert_eq!(
            parse_bbox(&json!({"x": 10, "y": 5, "w": 20, "h": 7})).unwrap(),
            Some([10, 5, 30, 12])
        );
        let mut total = 0;
        let image = parse_ocr_image(
            &json!({"image_base64": "", "bbox": null}),
            OcrResponsePolicy::default(),
            &mut total,
        )
        .unwrap();
        assert_eq!(image.bbox, None);
    }

    #[test]
    fn duplicate_or_incomplete_ocr_page_indices_are_rejected() {
        let duplicate = json!({
            "pages": [
                {"index": 0, "markdown": "a"},
                {"index": 0, "markdown": "b"}
            ]
        });
        assert!(parse_ocr_response(
            duplicate,
            "mistral-ocr-2505",
            Some(&[0, 1]),
            OcrResponsePolicy::default()
        )
        .is_err());

        let mixed = json!({
            "pages": [
                {"index": 0, "markdown": "a"},
                {"markdown": "b"}
            ]
        });
        assert!(parse_ocr_response(
            mixed,
            "mistral-ocr-2505",
            Some(&[0, 1]),
            OcrResponsePolicy::default()
        )
        .is_err());

        let omitted = json!({
            "pages": [
                {"markdown": "a"},
                {"markdown": "b"}
            ]
        });
        let parsed = parse_ocr_response(
            omitted,
            "mistral-ocr-2505",
            Some(&[2, 4]),
            OcrResponsePolicy::default(),
        )
        .unwrap();
        assert_eq!(
            parsed
                .pages
                .iter()
                .map(|page| page.index)
                .collect::<Vec<_>>(),
            vec![2, 4]
        );
    }

    #[test]
    fn ocr_response_cardinality_and_content_budgets_fail_closed() {
        let policy = OcrResponsePolicy {
            max_pages: 1,
            max_markdown_bytes_per_page: 3,
            max_markdown_bytes_total: 3,
            max_images_per_page: 1,
            max_images_total: 1,
            max_encoded_image_bytes: 3,
            max_decoded_image_bytes: 3,
            max_decoded_image_bytes_total: 3,
            max_persisted_image_bytes: 3,
        };
        assert!(parse_ocr_response(
            json!({"pages": [{"index": 0, "markdown": "1234"}]}),
            "pin",
            Some(&[0]),
            policy
        )
        .is_err());
        assert!(parse_ocr_response(
            json!({
                "pages": [{
                    "index": 0,
                    "markdown": "ok",
                    "images": [{"image_base64": "AAAA"}]
                }]
            }),
            "pin",
            Some(&[0]),
            policy
        )
        .is_err());
    }

    #[test]
    fn image_quota_failure_leaves_cas_unchanged() {
        let dir = tempfile::tempdir().unwrap();
        let first = OcrImage {
            bytes: b"four".to_vec(),
            media_type: "image/png".to_owned(),
            bbox: None,
            confidence: None,
        };
        let second = OcrImage {
            bytes: b"more".to_vec(),
            media_type: "image/png".to_owned(),
            bbox: None,
            confidence: None,
        };
        let err = persist_image_refs_bounded(dir.path(), &[&first, &second], 7).unwrap_err();
        assert!(matches!(err, AdapterError::QuotaExceeded(_)));
        assert!(!dir.path().join("objects/images").exists());
    }

    #[derive(Debug, Clone)]
    struct CaptureBytesClient(std::sync::Arc<std::sync::Mutex<Vec<Vec<u8>>>>);

    impl MistralOcrClient for CaptureBytesClient {
        fn resolve_model_pin(&self, _configured_model: &str) -> Result<String> {
            Ok("mistral-ocr-2505".to_owned())
        }

        fn ocr_markdown(
            &self,
            _request: &MarkdownizeRequest,
            model_pin: &str,
            verified_raw_bytes: &[u8],
        ) -> Result<OcrResponse> {
            self.0.lock().unwrap().push(verified_raw_bytes.to_vec());
            Ok(OcrResponse {
                pages: vec![OcrPage {
                    index: 0,
                    markdown: "verified".to_owned(),
                    images: Vec::new(),
                }],
                model_version_pin: model_pin.to_owned(),
            })
        }
    }

    #[test]
    fn exact_verified_bytes_cross_the_ocr_client_boundary() {
        let approved = b"%PDF approved bytes";
        let captured = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        let client = CaptureBytesClient(captured.clone());
        let mut request = markdownize_request(MarkdownizeMode::Full, vec![hint("page:1", 0)]);
        request.raw.raw_hash = crate::identity::hash_bytes(approved);
        request.raw.path = Some("/path/that/must/not/be/reopened.pdf".to_owned());
        let adapter = MistralOcrMarkdownizeAdapter::new(client, "mistral-ocr-2505", "scope")
            .with_verified_raw_bytes(approved.to_vec());
        let response = adapter.markdownize(request).unwrap();
        assert_eq!(response.updated_units[0].markdown, "verified");
        assert_eq!(captured.lock().unwrap().as_slice(), &[approved.to_vec()]);
    }

    #[test]
    fn identity_mismatch_stops_before_ocr_client() {
        let approved = b"%PDF approved bytes";
        let replacement = b"%PDF replacement bytes";
        let captured = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        let client = CaptureBytesClient(captured.clone());
        let mut request = markdownize_request(MarkdownizeMode::Full, vec![hint("page:1", 0)]);
        request.raw.raw_hash = crate::identity::hash_bytes(approved);
        let adapter = MistralOcrMarkdownizeAdapter::new(client, "mistral-ocr-2505", "scope")
            .with_verified_raw_bytes(replacement.to_vec());
        assert!(adapter.markdownize(request).is_err());
        assert!(captured.lock().unwrap().is_empty());
    }
}
