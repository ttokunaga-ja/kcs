//! Adapter trait groups.

use crate::types::{
    AdapterProfile, ClassificationRequest, ClassificationResponse, EmbeddingRequest,
    EmbeddingResponse, MarkdownizeRequest, MarkdownizeResponse, PrepareRequest, PrepareResponse,
    RerankRequest, RerankResponse, SummaryRequest, SummaryResponse,
};
use crate::Result;

pub trait PrepareAdapter {
    fn profile(&self) -> AdapterProfile;

    fn prepare(&self, request: PrepareRequest) -> Result<PrepareResponse>;
}

pub trait MarkdownizeAdapter {
    fn profile(&self) -> AdapterProfile;

    fn markdownize(&self, request: MarkdownizeRequest) -> Result<MarkdownizeResponse>;
}

pub trait EmbeddingAdapter {
    fn profile(&self) -> AdapterProfile;

    fn embed(&self, request: EmbeddingRequest) -> Result<EmbeddingResponse>;
}

pub trait SummaryAdapter {
    fn profile(&self) -> AdapterProfile;

    fn summarize(&self, request: SummaryRequest) -> Result<SummaryResponse>;
}

pub trait ClassificationAdapter {
    fn profile(&self) -> AdapterProfile;

    fn classify(&self, request: ClassificationRequest) -> Result<ClassificationResponse>;
}

pub trait RerankAdapter {
    fn profile(&self) -> AdapterProfile;

    fn rerank(&self, request: RerankRequest) -> Result<RerankResponse>;
}

#[cfg(test)]
mod tests {
    use crate::deterministic::DeterministicAdapter;
    use crate::types::{AdapterKind, ExecutionMode};

    use super::PrepareAdapter;

    #[test]
    fn placeholder_prepare_trait_exposes_profile() {
        let adapter = DeterministicAdapter;
        let profile = PrepareAdapter::profile(&adapter);

        assert_eq!(profile.adapter_kind, AdapterKind::Prepare);
        assert_eq!(profile.execution_mode, ExecutionMode::DeterministicLibrary);
    }
}
