//! Mistral OCR markdownize adapter skeleton.

use crate::traits::MarkdownizeAdapter;
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownizeRequest, MarkdownizeResponse,
};
use crate::Result;

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
        todo!("implement Mistral OCR Markdownize adapter in Step 2");
    }
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
}
