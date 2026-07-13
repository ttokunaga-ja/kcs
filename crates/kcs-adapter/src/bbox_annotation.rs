//! Contract-frozen Mistral bbox annotation primitives.
//!
//! This module is the sole owner of the provider schema, profile identity,
//! response bounds, and the escaping used by both structured unit metadata and
//! searchable Markdown projection.

use serde::Deserialize;
use serde_json::{json, Value};
use unicode_normalization::UnicodeNormalization;

use crate::{AdapterError, Result};

pub const BBOX_ANNOTATION_PROMPT_TEMPLATE_ID: &str = "kcs-mistral-bbox-annotation-v1";
pub const BBOX_ANNOTATION_OUTPUT_SCHEMA: &str = "kcs-markdown+bbox-annotation-v1";
pub const BBOX_ANNOTATION_FORMAT_HASH: &str =
    "sha256:9404f8ffe2983113f082d255a61817ad0798e74aeb82cb5063a391fbcbea9ca8";
pub const MAX_ANNOTATION_IMAGES_PER_PAGE: usize = 256;
pub const MAX_ANNOTATION_IMAGES_PER_RESPONSE: usize = 4_096;
pub const MAX_SHORT_DESCRIPTION_BYTES: usize = 4 * 1024;
pub const MAX_TRANSCRIBED_TEXT_BYTES: usize = 64 * 1024;
pub const MAX_ANNOTATION_BYTES_PER_RESPONSE: usize = 16 * 1024 * 1024;
pub const MAX_BBOX_COORDINATE: i64 = 1_000_000_000;

/// Exact A.2 value sent as Mistral's single `bbox_annotation_format` field.
#[must_use]
pub fn bbox_annotation_format() -> Value {
    json!({
        "type": "json_schema",
        "json_schema": {
            "name": "kcs_bbox_annotation_v1",
            "strict": true,
            "schema": {
                "type": "object",
                "additionalProperties": false,
                "properties": {
                    "short_description": {
                        "type": "string",
                        "description": "Describe the figure briefly in plain text. Do not use Markdown or HTML."
                    },
                    "transcribed_text": {
                        "type": "string",
                        "description": "Transcribe all visible text verbatim in plain text. Do not use Markdown or HTML."
                    }
                },
                "required": ["short_description", "transcribed_text"]
            }
        }
    })
}

/// Frozen profile input for the resolved immutable Mistral model pin.
#[must_use]
pub fn mistral_markdownize_profile(model_version_pin: &str, enabled: bool) -> Value {
    if enabled {
        json!({
            "adapter_kind": "markdownize",
            "adapter_role": "multimodal",
            "model_or_tool_family": "mistral-ocr",
            "model_version_pin": model_version_pin,
            "output_schema": BBOX_ANNOTATION_OUTPUT_SCHEMA,
            "prompt_template_hash": BBOX_ANNOTATION_FORMAT_HASH,
            "prompt_template_id": BBOX_ANNOTATION_PROMPT_TEMPLATE_ID,
            "runtime_kind": "cloud",
            "spec_version": 1
        })
    } else {
        json!({
            "adapter_kind": "markdownize",
            "adapter_role": "multimodal",
            "model_or_tool_family": "mistral-ocr",
            "model_version_pin": model_version_pin,
            "output_schema": "kcs-markdown-v1",
            "runtime_kind": "cloud",
            "spec_version": 1
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BboxAnnotation {
    /// Post-normalization and post-escape text persisted into unit metadata.
    pub short_description: String,
    /// Post-normalization and post-escape text persisted into unit metadata.
    pub transcribed_text: String,
}

impl BboxAnnotation {
    #[must_use]
    pub fn metadata_value(&self, image_hash: &str, bbox: [i64; 4]) -> Value {
        json!({
            "image_hash": image_hash,
            "bbox": bbox,
            "short_description": self.short_description,
            "transcribed_text": self.transcribed_text,
        })
    }

    /// Trusted blockquote projection inserted immediately after the image URI.
    #[must_use]
    pub fn markdown_block(&self) -> String {
        let description = prefixed_lines(
            "> KCS figure description: ",
            self.short_description.as_str(),
        );
        let transcription = prefixed_lines("> KCS figure text: ", self.transcribed_text.as_str());
        format!("{description}\n{transcription}")
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct AnnotationTotals {
    pub images: usize,
    pub decoded_bytes: usize,
    pub escaped_bytes: usize,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ProviderAnnotation {
    short_description: String,
    transcribed_text: String,
}

/// Decode one exact provider `image_annotation` JSON string, validate its bbox,
/// enforce decoded and escaped bounds, and return the canonical persisted text.
pub fn decode_image_annotation(
    raw_json: &str,
    bbox: [i64; 4],
    totals: &mut AnnotationTotals,
) -> Result<BboxAnnotation> {
    validate_bbox(bbox)?;
    let provider: ProviderAnnotation = serde_json::from_str(raw_json).map_err(|error| {
        AdapterError::ContractViolation(format!("invalid bbox image_annotation: {error}"))
    })?;
    check_string_bound(
        "short_description",
        provider.short_description.len(),
        MAX_SHORT_DESCRIPTION_BYTES,
        "decoded",
    )?;
    check_string_bound(
        "transcribed_text",
        provider.transcribed_text.len(),
        MAX_TRANSCRIBED_TEXT_BYTES,
        "decoded",
    )?;
    let decoded_increment = provider
        .short_description
        .len()
        .checked_add(provider.transcribed_text.len())
        .ok_or_else(|| annotation_violation("decoded annotation byte count overflow"))?;

    let short_description = canonical_source_escape(&provider.short_description);
    let transcribed_text = canonical_source_escape(&provider.transcribed_text);
    check_string_bound(
        "short_description",
        short_description.len(),
        MAX_SHORT_DESCRIPTION_BYTES,
        "escaped",
    )?;
    check_string_bound(
        "transcribed_text",
        transcribed_text.len(),
        MAX_TRANSCRIBED_TEXT_BYTES,
        "escaped",
    )?;
    let escaped_increment = short_description
        .len()
        .checked_add(transcribed_text.len())
        .ok_or_else(|| annotation_violation("escaped annotation byte count overflow"))?;

    let images = totals
        .images
        .checked_add(1)
        .ok_or_else(|| annotation_violation("annotation image count overflow"))?;
    if images > MAX_ANNOTATION_IMAGES_PER_RESPONSE {
        return Err(annotation_violation(
            "annotation image count exceeds response limit",
        ));
    }
    let decoded_bytes = totals
        .decoded_bytes
        .checked_add(decoded_increment)
        .ok_or_else(|| annotation_violation("decoded annotation byte count overflow"))?;
    if decoded_bytes > MAX_ANNOTATION_BYTES_PER_RESPONSE {
        return Err(annotation_violation(
            "decoded annotations exceed aggregate limit",
        ));
    }
    let escaped_bytes = totals
        .escaped_bytes
        .checked_add(escaped_increment)
        .ok_or_else(|| annotation_violation("escaped annotation byte count overflow"))?;
    if escaped_bytes > MAX_ANNOTATION_BYTES_PER_RESPONSE {
        return Err(annotation_violation(
            "escaped annotations exceed aggregate limit",
        ));
    }
    *totals = AnnotationTotals {
        images,
        decoded_bytes,
        escaped_bytes,
    };

    Ok(BboxAnnotation {
        short_description,
        transcribed_text,
    })
}

/// Exact newline/NFC/control normalization and per-scalar CommonMark escaping.
#[must_use]
pub fn canonical_source_escape(input: &str) -> String {
    let normalized_newlines = input.replace("\r\n", "\n").replace('\r', "\n");
    let normalized = normalized_newlines.nfc().collect::<String>();
    let mut escaped = String::with_capacity(normalized.len());
    for scalar in normalized.chars() {
        if scalar != '\n' && scalar.is_control() {
            continue;
        }
        match scalar {
            '&' => escaped.push_str("&amp;"),
            '<' => escaped.push_str("&lt;"),
            '>' => escaped.push_str("&gt;"),
            value if value.is_ascii_punctuation() => {
                escaped.push('\\');
                escaped.push(value);
            }
            value => escaped.push(value),
        }
    }
    escaped
}

pub fn validate_bbox([x1, y1, x2, y2]: [i64; 4]) -> Result<()> {
    if !(0 <= x1
        && x1 < x2
        && x2 <= MAX_BBOX_COORDINATE
        && 0 <= y1
        && y1 < y2
        && y2 <= MAX_BBOX_COORDINATE)
    {
        return Err(annotation_violation(
            "bbox coordinates must have positive bounded geometry",
        ));
    }
    Ok(())
}

fn check_string_bound(field: &str, actual: usize, limit: usize, phase: &str) -> Result<()> {
    if actual > limit {
        return Err(annotation_violation(format!(
            "bbox {field} exceeds {phase} byte limit of {limit}"
        )));
    }
    Ok(())
}

fn prefixed_lines(prefix: &str, value: &str) -> String {
    value
        .split('\n')
        .map(|line| format!("{prefix}{line}"))
        .collect::<Vec<_>>()
        .join("\n")
}

fn annotation_violation(message: impl Into<String>) -> AdapterError {
    AdapterError::ContractViolation(message.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::identity::{jcs_bytes, jcs_hash, tool_profile_hash};

    #[test]
    fn ct4_bbox_001_and_002_exact_schema_and_profile_vectors() {
        let format = bbox_annotation_format();
        assert_eq!(
            jcs_bytes(&format).unwrap(),
            br#"{"json_schema":{"name":"kcs_bbox_annotation_v1","schema":{"additionalProperties":false,"properties":{"short_description":{"description":"Describe the figure briefly in plain text. Do not use Markdown or HTML.","type":"string"},"transcribed_text":{"description":"Transcribe all visible text verbatim in plain text. Do not use Markdown or HTML.","type":"string"}},"required":["short_description","transcribed_text"],"type":"object"},"strict":true},"type":"json_schema"}"#
        );
        assert_eq!(jcs_hash(&format).unwrap(), BBOX_ANNOTATION_FORMAT_HASH);

        let enabled = mistral_markdownize_profile("mistral-ocr-2505", true);
        assert_eq!(
            jcs_bytes(&enabled).unwrap(),
            br#"{"adapter_kind":"markdownize","adapter_role":"multimodal","model_or_tool_family":"mistral-ocr","model_version_pin":"mistral-ocr-2505","output_schema":"kcs-markdown+bbox-annotation-v1","prompt_template_hash":"sha256:9404f8ffe2983113f082d255a61817ad0798e74aeb82cb5063a391fbcbea9ca8","prompt_template_id":"kcs-mistral-bbox-annotation-v1","runtime_kind":"cloud","spec_version":1}"#
        );
        assert_eq!(
            tool_profile_hash(&enabled).unwrap(),
            "sha256:830c45cada7e9ea8c6f6816579fa0493645208626201181f3763b4bc6bddda3e"
        );
        assert_eq!(
            tool_profile_hash(&mistral_markdownize_profile("mistral-ocr-2505", false)).unwrap(),
            "sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed"
        );
    }

    #[test]
    fn ct4_bbox_004_normalizes_and_escapes_every_provider_scalar() {
        let raw = serde_json::json!({
            "short_description": "Cafe\u{301}\r\n# [x](kcs://fake) <img> &amp; `fence`\u{0000}",
            "transcribed_text": "![x](https://example.test/x)\n<kcs://evil>"
        })
        .to_string();
        let mut totals = AnnotationTotals::default();
        let annotation = decode_image_annotation(&raw, [0, 1, 2, 3], &mut totals).unwrap();
        assert_eq!(
            annotation.short_description,
            "Café\n\\# \\[x\\]\\(kcs\\:\\/\\/fake\\) &lt;img&gt; &amp;amp\\; \\`fence\\`"
        );
        assert_eq!(
            annotation.transcribed_text,
            "\\!\\[x\\]\\(https\\:\\/\\/example\\.test\\/x\\)\n&lt;kcs\\:\\/\\/evil&gt;"
        );
        assert_eq!(
            annotation.markdown_block(),
            "> KCS figure description: Café\n> KCS figure description: \\# \\[x\\]\\(kcs\\:\\/\\/fake\\) &lt;img&gt; &amp;amp\\; \\`fence\\`\n> KCS figure text: \\!\\[x\\]\\(https\\:\\/\\/example\\.test\\/x\\)\n> KCS figure text: &lt;kcs\\:\\/\\/evil&gt;"
        );
        assert_eq!(totals.images, 1);
    }

    #[test]
    fn ct4_bbox_004_rejects_schema_geometry_and_escape_expansion_bounds() {
        for invalid in [
            r#"{"short_description":"only"}"#,
            r#"{"short_description":"x","transcribed_text":"y","extra":true}"#,
            r#"{"short_description":1,"transcribed_text":"y"}"#,
            r#"{"short_description":"a","short_description":"b","transcribed_text":"y"}"#,
        ] {
            assert!(decode_image_annotation(
                invalid,
                [0, 0, 1, 1],
                &mut AnnotationTotals::default()
            )
            .is_err());
        }
        for bbox in [
            [-1, 0, 1, 1],
            [0, 0, 0, 1],
            [0, 0, 1, 0],
            [0, 0, MAX_BBOX_COORDINATE + 1, 1],
        ] {
            assert!(validate_bbox(bbox).is_err());
        }

        let expansion = serde_json::json!({
            "short_description": "&".repeat(MAX_SHORT_DESCRIPTION_BYTES),
            "transcribed_text": ""
        })
        .to_string();
        assert!(decode_image_annotation(
            &expansion,
            [0, 0, 1, 1],
            &mut AnnotationTotals::default()
        )
        .is_err());
    }

    #[test]
    fn ct4_bbox_004_enforces_exact_string_count_and_aggregate_limits() {
        let exact = serde_json::json!({
            "short_description": "a".repeat(MAX_SHORT_DESCRIPTION_BYTES),
            "transcribed_text": "b".repeat(MAX_TRANSCRIBED_TEXT_BYTES),
        })
        .to_string();
        assert!(
            decode_image_annotation(&exact, [0, 0, 1, 1], &mut AnnotationTotals::default()).is_ok()
        );

        for oversized in [
            serde_json::json!({
                "short_description": "a".repeat(MAX_SHORT_DESCRIPTION_BYTES + 1),
                "transcribed_text": ""
            })
            .to_string(),
            serde_json::json!({
                "short_description": "",
                "transcribed_text": "b".repeat(MAX_TRANSCRIBED_TEXT_BYTES + 1)
            })
            .to_string(),
        ] {
            assert!(decode_image_annotation(
                &oversized,
                [0, 0, 1, 1],
                &mut AnnotationTotals::default()
            )
            .is_err());
        }

        let minimal = r#"{"short_description":"a","transcribed_text":""}"#;
        for mut totals in [
            AnnotationTotals {
                images: MAX_ANNOTATION_IMAGES_PER_RESPONSE,
                ..AnnotationTotals::default()
            },
            AnnotationTotals {
                decoded_bytes: MAX_ANNOTATION_BYTES_PER_RESPONSE,
                ..AnnotationTotals::default()
            },
            AnnotationTotals {
                escaped_bytes: MAX_ANNOTATION_BYTES_PER_RESPONSE,
                ..AnnotationTotals::default()
            },
        ] {
            assert!(decode_image_annotation(minimal, [0, 0, 1, 1], &mut totals).is_err());
        }
    }
}
