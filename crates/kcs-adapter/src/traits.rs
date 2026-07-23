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

    /// Which request lane this adapter's online sends should take (07 §5.7).
    /// Default = Sync (single request/response round trip). The built-in
    /// Mistral OCR adapter overrides this to Batch: the 2026-07-23 user
    /// ruling permits OCR spending on the Batch lane only ($2/1,000 pages),
    /// so its production sends must never take the sync lane. A trait
    /// default (not an `AdapterProfile` field) keeps the lane OUT of
    /// identity — same posture as `ProviderIdempotency` (QA13).
    fn preferred_request_kind(&self) -> PreferredRequestKind {
        PreferredRequestKind::Sync
    }
}

/// Online send lane selector (07 §5.7; ledger `batch_requests.request_kind`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PreferredRequestKind {
    Sync,
    Batch,
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
