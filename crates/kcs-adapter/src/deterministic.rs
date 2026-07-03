//! Built-in deterministic adapter skeleton.

use crate::traits::{MarkdownizeAdapter, PrepareAdapter};
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownizeRequest, MarkdownizeResponse,
    PrepareRequest, PrepareResponse,
};
use crate::Result;

#[derive(Debug, Clone, Default)]
pub struct DeterministicAdapter;

impl DeterministicAdapter {
    fn profile_for(adapter_kind: AdapterKind) -> AdapterProfile {
        AdapterProfile {
            adapter_kind,
            adapter_id: "deterministic_builtin".to_owned(),
            execution_mode: ExecutionMode::DeterministicLibrary,
            tool_profile_hash:
                "sha256:0000000000000000000000000000000000000000000000000000000000000001".to_owned(),
            version: env!("CARGO_PKG_VERSION").to_owned(),
            capability_flags: Vec::new(),
            allow_network: false,
        }
    }
}

impl PrepareAdapter for DeterministicAdapter {
    fn profile(&self) -> AdapterProfile {
        Self::profile_for(AdapterKind::Prepare)
    }

    fn prepare(&self, _request: PrepareRequest) -> Result<PrepareResponse> {
        todo!("implement deterministic Prepare adapter in Step 2");
    }
}

impl MarkdownizeAdapter for DeterministicAdapter {
    fn profile(&self) -> AdapterProfile {
        Self::profile_for(AdapterKind::Markdownize)
    }

    fn markdownize(&self, _request: MarkdownizeRequest) -> Result<MarkdownizeResponse> {
        todo!("implement deterministic Markdownize adapter in Step 2");
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
