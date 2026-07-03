//! Built-in deterministic adapter skeleton.

use crate::traits::{MarkdownizeAdapter, PrepareAdapter};
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownUnit, MarkdownizeMode, MarkdownizeRequest,
    MarkdownizeResponse, PrepareRequest, PrepareResponse, PreparedUnitHint, PreparedUnitMetadata,
    UnitFingerprint, UnitKind,
};
use crate::Result;
use serde_json::json;

#[derive(Debug, Clone, Default)]
pub struct DeterministicAdapter;

impl DeterministicAdapter {
    fn profile_for(adapter_kind: AdapterKind) -> AdapterProfile {
        let (profile_input, capability_flags) = match adapter_kind {
            AdapterKind::Prepare => (deterministic_prepare_profile_value(), Vec::new()),
            AdapterKind::Markdownize => (
                deterministic_markdown_profile_value(),
                vec!["baseline".to_owned(), "text_passthrough".to_owned()],
            ),
            _ => (
                json!({
                    "adapter_kind": "markdownize",
                    "adapter_role": "text",
                    "model_or_tool_family": "kcs-deterministic-text",
                    "model_version_pin": "1.0.0",
                    "output_schema": "kcs-markdown-v1",
                    "runtime_kind": "local",
                    "spec_version": 1
                }),
                Vec::new(),
            ),
        };
        let tool_profile_hash = crate::identity::tool_profile_hash(&profile_input)
            .expect("built-in deterministic profile is valid");
        AdapterProfile {
            adapter_kind,
            adapter_id: "deterministic_builtin".to_owned(),
            execution_mode: ExecutionMode::DeterministicLibrary,
            tool_profile_hash,
            version: env!("CARGO_PKG_VERSION").to_owned(),
            capability_flags,
            allow_network: false,
        }
    }
}

pub fn deterministic_markdown_profile_value() -> serde_json::Value {
    json!({
        "adapter_kind": "markdownize",
        "adapter_role": "text",
        "model_or_tool_family": "kcs-deterministic-text",
        "model_version_pin": "1.0.0",
        "output_schema": "kcs-markdown-v1",
        "runtime_kind": "local",
        "spec_version": 1
    })
}

pub fn deterministic_prepare_profile_value() -> serde_json::Value {
    json!({
        "adapter_kind": "prepare",
        "adapter_role": "text",
        "model_or_tool_family": "kcs-deterministic-prepare",
        "model_version_pin": "1.0.0",
        "runtime_kind": "local",
        "spec_version": 1
    })
}

impl PrepareAdapter for DeterministicAdapter {
    fn profile(&self) -> AdapterProfile {
        Self::profile_for(AdapterKind::Prepare)
    }

    fn prepare(&self, request: PrepareRequest) -> Result<PrepareResponse> {
        let unit_kind = unit_kind_for_media_type(&request.media_type);
        let unit_key = match unit_kind {
            UnitKind::Page => "page:1",
            UnitKind::Image => "image:0",
            UnitKind::Sheet => "sheet:Sheet1",
            UnitKind::Slide => "slide:1",
            UnitKind::File | UnitKind::HeadingSection | UnitKind::Symbol => "doc:1",
        }
        .to_owned();
        let fingerprint = UnitFingerprint {
            perceptual_hash: request.raw_hash.clone(),
            text_hash: request.raw_hash.clone(),
            visual_hash: request.raw_hash.clone(),
        };
        Ok(PrepareResponse {
            prepared_object_hashes: vec![request.raw_hash.clone()],
            prepared_unit_hashes: vec![request.raw_hash.clone()],
            image_object_hashes: Vec::new(),
            metadata: vec![PreparedUnitMetadata {
                unit_key,
                unit_kind,
                page_number: matches!(unit_kind, UnitKind::Page).then_some(1),
                mime: Some(request.media_type),
                fingerprint,
            }],
        })
    }
}

impl MarkdownizeAdapter for DeterministicAdapter {
    fn profile(&self) -> AdapterProfile {
        Self::profile_for(AdapterKind::Markdownize)
    }

    fn markdownize(&self, request: MarkdownizeRequest) -> Result<MarkdownizeResponse> {
        let hints = request
            .prepared_unit_hint
            .clone()
            .unwrap_or_else(|| vec![default_hint(&request.raw.raw_hash)]);
        let source_text = read_source_text(&request);
        if request.mode == MarkdownizeMode::Incremental {
            let incremental = request.hints.clone();
            let changed = incremental
                .as_ref()
                .map(|hints| hints.changed_unit_keys.as_slice())
                .unwrap_or(&[]);
            let added = incremental
                .as_ref()
                .map(|hints| hints.added_unit_keys.as_slice())
                .unwrap_or(&[]);
            return Ok(MarkdownizeResponse {
                mode_used: MarkdownizeMode::Incremental,
                updated_units: hints
                    .iter()
                    .filter(|hint| changed.contains(&hint.unit_key))
                    .map(|hint| markdown_unit_from_hint(hint, &request, source_text.as_deref()))
                    .collect(),
                unchanged_unit_keys: Vec::new(),
                added_units: hints
                    .iter()
                    .filter(|hint| added.contains(&hint.unit_key))
                    .map(|hint| markdown_unit_from_hint(hint, &request, source_text.as_deref()))
                    .collect(),
                removed_unit_keys: incremental
                    .map(|hints| hints.removed_unit_keys)
                    .unwrap_or_default(),
                evidence_pointers: Vec::new(),
                fallback_to_full: false,
                reason: None,
            });
        }

        Ok(MarkdownizeResponse {
            mode_used: MarkdownizeMode::Full,
            updated_units: hints
                .iter()
                .map(|hint| markdown_unit_from_hint(hint, &request, source_text.as_deref()))
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

fn unit_kind_for_media_type(media_type: &str) -> UnitKind {
    match media_type {
        "application/pdf" => UnitKind::Page,
        "image/png" | "image/jpeg" | "image/webp" | "image/gif" => UnitKind::Image,
        "application/vnd.ms-excel"
        | "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" => UnitKind::Sheet,
        "application/vnd.ms-powerpoint"
        | "application/vnd.openxmlformats-officedocument.presentationml.presentation" => {
            UnitKind::Slide
        }
        _ => UnitKind::File,
    }
}

fn default_hint(raw_hash: &str) -> PreparedUnitHint {
    PreparedUnitHint {
        unit_key: "doc:1".to_owned(),
        prepared_hash: raw_hash.to_owned(),
        unit_kind: UnitKind::File,
        order: 0,
    }
}

fn markdown_unit_from_hint(
    hint: &PreparedUnitHint,
    request: &MarkdownizeRequest,
    source_text: Option<&str>,
) -> MarkdownUnit {
    let markdown = match source_text {
        Some(text) if request.media_type == "text/markdown" => text.to_owned(),
        Some(text) if request.media_type == "text/x-code" => {
            fence_code(text, request.raw.path.as_deref())
        }
        Some(text) if request.media_type == "application/pdf" => {
            format!("{}\n", text.trim())
        }
        Some(text) => text.to_owned(),
        None => format!(
            "<!-- KCS deterministic baseline {} {} -->\n",
            hint.unit_key, hint.prepared_hash
        ),
    };
    MarkdownUnit {
        unit_key: hint.unit_key.clone(),
        unit_type: hint.unit_kind,
        markdown: if markdown.trim().is_empty() {
            format!(
                "<!-- KCS deterministic baseline {} {} -->\n",
                hint.unit_key, hint.prepared_hash
            )
        } else {
            markdown
        },
        metadata: Default::default(),
    }
}

fn read_source_text(request: &MarkdownizeRequest) -> Option<String> {
    let path = request.raw.path.as_ref()?;
    let bytes = std::fs::read(path).ok()?;
    if request.media_type == "application/pdf" {
        return Some(extract_pdf_text_layer(&bytes));
    }
    Some(String::from_utf8_lossy(&bytes).into_owned())
}

fn fence_code(text: &str, path: Option<&str>) -> String {
    let lang = path
        .and_then(|path| std::path::Path::new(path).extension())
        .and_then(|extension| extension.to_str())
        .unwrap_or("");
    format!("```{lang}\n{}\n```\n", text.trim_end())
}

fn extract_pdf_text_layer(bytes: &[u8]) -> String {
    let text = String::from_utf8_lossy(bytes);
    let mut out = String::new();
    let mut rest = text.as_ref();
    while let Some(start) = rest.find('(') {
        rest = &rest[start + 1..];
        let Some(end) = rest.find(')') else {
            break;
        };
        let candidate = &rest[..end];
        if candidate
            .chars()
            .any(|char| char.is_alphanumeric() || !char.is_ascii())
        {
            if !out.is_empty() {
                out.push('\n');
            }
            out.push_str(candidate);
        }
        rest = &rest[end + 1..];
    }
    if out.is_empty() {
        text.lines()
            .filter(|line| !line.trim_start().starts_with('%'))
            .collect::<Vec<_>>()
            .join("\n")
    } else {
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::traits::MarkdownizeAdapter;

    #[test]
    fn placeholder_deterministic_profile_disallows_network() {
        let adapter = DeterministicAdapter;
        let profile = MarkdownizeAdapter::profile(&adapter);

        assert!(!profile.allow_network);
        assert_eq!(profile.adapter_id, "deterministic_builtin");
    }
}
