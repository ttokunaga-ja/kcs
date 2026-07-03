//! Mistral OCR markdownize adapter.

use crate::identity::hash_bytes;
use crate::traits::MarkdownizeAdapter;
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownUnit, MarkdownizeRequest,
    MarkdownizeResponse, PreparedUnitHint,
};
use crate::{AdapterError, Result};
use serde_json::json;
use std::collections::BTreeMap;
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OcrImage {
    pub bytes: Vec<u8>,
    pub media_type: String,
    pub bbox: Option<[i64; 4]>,
    pub confidence: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OcrResponse {
    pub markdown: String,
    pub images: Vec<OcrImage>,
    pub model_version_pin: String,
}

pub trait MistralOcrClient: Clone {
    fn resolve_model_pin(&self, configured_model: &str) -> Result<String>;

    fn ocr_markdown(&self, request: &MarkdownizeRequest, model_pin: &str) -> Result<OcrResponse>;
}

#[derive(Debug, Clone, Default)]
pub struct EnvMistralOcrClient;

impl MistralOcrClient for EnvMistralOcrClient {
    fn resolve_model_pin(&self, configured_model: &str) -> Result<String> {
        if configured_model.ends_with("-latest") {
            Ok("mistral-ocr-2505".to_owned())
        } else {
            Ok(configured_model.to_owned())
        }
    }

    fn ocr_markdown(&self, _request: &MarkdownizeRequest, _model_pin: &str) -> Result<OcrResponse> {
        let _api_key = std::env::var("MISTRAL_API_KEY").map_err(|_| {
            AdapterError::ContractViolation("MISTRAL_API_KEY is not set".to_owned())
        })?;
        Err(AdapterError::ContractViolation(
            "live Mistral OCR HTTP execution is intentionally disabled unless a client is injected"
                .to_owned(),
        ))
    }
}

#[derive(Debug, Clone)]
pub struct MistralOcrMarkdownizeAdapter<C = EnvMistralOcrClient> {
    client: C,
    configured_model: String,
    scope_id: String,
}

impl Default for MistralOcrMarkdownizeAdapter<EnvMistralOcrClient> {
    fn default() -> Self {
        Self::new(EnvMistralOcrClient, "mistral-ocr-latest", "unknown")
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
        }
    }
}

impl<C: MistralOcrClient> MarkdownizeAdapter for MistralOcrMarkdownizeAdapter<C> {
    fn profile(&self) -> AdapterProfile {
        let model_pin = self
            .client
            .resolve_model_pin(&self.configured_model)
            .unwrap_or_else(|_| "mistral-ocr-2505".to_owned());
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
        let markdown = replace_image_placeholders(&ocr.markdown, &self.scope_id, &ocr.images);
        let hint = request
            .prepared_unit_hint
            .as_ref()
            .and_then(|hints| hints.first())
            .cloned()
            .unwrap_or_else(|| PreparedUnitHint {
                unit_key: "page:1".to_owned(),
                prepared_hash: request.raw.raw_hash.clone(),
                unit_kind: crate::types::UnitKind::Page,
                order: 0,
            });
        let mut metadata = BTreeMap::new();
        metadata.insert("model_version_pin".to_owned(), json!(ocr.model_version_pin));
        if let Some(first_image) = ocr.images.first() {
            metadata.insert("image_media_type".to_owned(), json!(first_image.media_type));
            if let Some(bbox) = first_image.bbox {
                metadata.insert("bbox".to_owned(), json!(bbox));
            }
            if let Some(confidence) = &first_image.confidence {
                metadata.insert("confidence".to_owned(), json!(confidence));
            }
        }
        Ok(MarkdownizeResponse {
            mode_used: request.mode,
            updated_units: vec![MarkdownUnit {
                unit_key: hint.unit_key,
                unit_type: hint.unit_kind,
                markdown,
                metadata,
            }],
            unchanged_unit_keys: Vec::new(),
            added_units: Vec::new(),
            removed_unit_keys: Vec::new(),
            evidence_pointers: Vec::new(),
            fallback_to_full: false,
            reason: None,
        })
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
