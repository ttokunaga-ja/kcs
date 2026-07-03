//! Mistral OCR markdownize adapter.

use crate::identity::hash_bytes;
use crate::traits::MarkdownizeAdapter;
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownUnit, MarkdownizeRequest,
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
        std::env::var("MISTRAL_API_KEY")
            .map_err(|_| AdapterError::ContractViolation("MISTRAL_API_KEY is not set".to_owned()))
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
        let document = document_payload(&request.media_type, &bytes);
        let value: Value = ureq::post(&format!("{}/v1/ocr", self.base_url()))
            .set("Authorization", &format!("Bearer {api_key}"))
            .set("Content-Type", "application/json")
            .send_json(json!({
                "model": model_pin,
                "document": document,
                "include_image_base64": true,
            }))
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
        let model_pin = self
            .client
            .resolve_model_pin(&self.configured_model)
            .unwrap_or_else(|_| {
                format!(
                    "{}-unresolved",
                    self.configured_model.trim_end_matches("-latest")
                )
            });
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
                .map(|hint| {
                    let page_index = hint.order as usize;
                    let page = pages_by_index
                        .get(&page_index)
                        .copied()
                        .or_else(|| ocr.pages.get(page_index))
                        .or_else(|| ocr.pages.first());
                    let markdown = page
                        .map(|page| {
                            replace_image_placeholders(&page.markdown, &self.scope_id, &page.images)
                        })
                        .unwrap_or_else(|| "<!-- KCS OCR returned no page -->\n".to_owned());
                    MarkdownUnit {
                        unit_key: hint.unit_key.clone(),
                        unit_type: hint.unit_kind,
                        markdown,
                        metadata: page_metadata(
                            &ocr.model_version_pin,
                            page.map(|page| page.images.as_slice()),
                        ),
                    }
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
        ureq::Error::Status(code, response) => AdapterError::ContractViolation(format!(
            "Mistral OCR HTTP {code}: {}",
            response.status_text()
        )),
        ureq::Error::Transport(transport) => AdapterError::ContractViolation(transport.to_string()),
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
            std::fs::write(&path, &image.bytes).map_err(|err| AdapterError::Io {
                path: path.display().to_string(),
                message: err.to_string(),
            })?;
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
    let start = markdown[cursor..].find("](")? + cursor;
    let target_start = start + 2;
    let relative_end = markdown[target_start..].find(')')?;
    let target_end = target_start + relative_end;
    Some((target_start, target_end))
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
