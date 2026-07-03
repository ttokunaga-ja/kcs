//! Mistral OCR markdownize adapter skeleton.

use crate::identity::hash_bytes;
use crate::traits::MarkdownizeAdapter;
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownizeRequest, MarkdownizeResponse,
};
use crate::{AdapterError, Result};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OcrImage {
    pub bytes: Vec<u8>,
    pub media_type: String,
}

#[derive(Debug, Clone, Default)]
pub struct MistralOcrMarkdownizeAdapter;

impl MarkdownizeAdapter for MistralOcrMarkdownizeAdapter {
    fn profile(&self) -> AdapterProfile {
        AdapterProfile {
            adapter_kind: AdapterKind::Markdownize,
            adapter_id: "mistral_ocr_markdownize".to_owned(),
            execution_mode: ExecutionMode::OnlineApi,
            tool_profile_hash:
                "sha256:0000000000000000000000000000000000000000000000000000000000000002".to_owned(),
            version: env!("CARGO_PKG_VERSION").to_owned(),
            capability_flags: vec![
                "ocr".to_owned(),
                "layout_detection".to_owned(),
                "table_extraction".to_owned(),
            ],
            allow_network: true,
        }
    }

    fn markdownize(&self, _request: MarkdownizeRequest) -> Result<MarkdownizeResponse> {
        Err(AdapterError::NotImplemented(
            "mistral_ocr_markdownize HTTP execution requires an injected client",
        ))
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
        let adapter = MistralOcrMarkdownizeAdapter;
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
                },
                OcrImage {
                    bytes: b"two".to_vec(),
                    media_type: "image/png".to_owned(),
                },
            ],
        );
        assert!(replaced.contains("kcs://01H00000000000000000000000/object/image/sha256:"));
        assert!(!replaced.contains("placeholder-1"));
        assert!(!replaced.contains("placeholder-2"));
    }
}
