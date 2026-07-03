//! Adapter request and response contracts.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AdapterKind {
    Prepare,
    Markdownize,
    Embedding,
    Summary,
    Classification,
    Rerank,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionMode {
    OnlineApi,
    OfflineApi,
    DeterministicLibrary,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AdapterRunStatus {
    Pending,
    Running,
    Done,
    Partial,
    Failed,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AdapterProfile {
    pub adapter_kind: AdapterKind,
    pub adapter_id: String,
    pub execution_mode: ExecutionMode,
    pub tool_profile_hash: String,
    pub version: String,
    pub capability_flags: Vec<String>,
    pub allow_network: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AdapterRun {
    pub task_id: String,
    pub input_hashes: Vec<String>,
    pub output_hashes: Vec<String>,
    pub status: AdapterRunStatus,
    pub error_kind: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "adapter_kind", content = "payload", rename_all = "snake_case")]
pub enum AdapterRequest {
    Prepare(Box<PrepareRequest>),
    Markdownize(Box<MarkdownizeRequest>),
    Embedding(Box<EmbeddingRequest>),
    Summary(Box<SummaryRequest>),
    Classification(Box<ClassificationRequest>),
    Rerank(Box<RerankRequest>),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "adapter_kind", content = "payload", rename_all = "snake_case")]
pub enum AdapterResponse {
    Prepare(Box<PrepareResponse>),
    Markdownize(Box<MarkdownizeResponse>),
    Embedding(Box<EmbeddingResponse>),
    Summary(Box<SummaryResponse>),
    Classification(Box<ClassificationResponse>),
    Rerank(Box<RerankResponse>),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawInput {
    pub raw_hash: String,
    pub path: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UnitKind {
    Page,
    Slide,
    HeadingSection,
    Sheet,
    Image,
    File,
    Symbol,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UnitFingerprint {
    pub perceptual_hash: String,
    pub text_hash: String,
    pub visual_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreparedUnitMetadata {
    pub unit_key: String,
    pub unit_kind: UnitKind,
    pub page_number: Option<u64>,
    pub mime: Option<String>,
    pub fingerprint: UnitFingerprint,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareRequest {
    pub raw_hash: String,
    pub media_type: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareResponse {
    pub prepared_object_hashes: Vec<String>,
    pub prepared_unit_hashes: Vec<String>,
    pub image_object_hashes: Vec<String>,
    pub metadata: Vec<PreparedUnitMetadata>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MarkdownizeMode {
    Full,
    Incremental,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreparedUnitHint {
    pub unit_key: String,
    pub prepared_hash: String,
    pub unit_kind: UnitKind,
    pub order: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarkdownUnit {
    pub unit_key: String,
    pub unit_type: UnitKind,
    pub markdown: String,
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreviousMarkdownizeContext {
    pub raw: RawInput,
    pub normalized_units: Vec<MarkdownUnit>,
    pub tool_profile_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IncrementalHints {
    pub changed_unit_keys: Vec<String>,
    pub added_unit_keys: Vec<String>,
    pub removed_unit_keys: Vec<String>,
    pub page_fingerprints: BTreeMap<String, UnitFingerprint>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarkdownizeRequest {
    pub raw: RawInput,
    pub media_type: String,
    pub prepared_unit_hint: Option<Vec<PreparedUnitHint>>,
    pub mode: MarkdownizeMode,
    pub previous: Option<PreviousMarkdownizeContext>,
    pub hints: Option<IncrementalHints>,
    pub tool_profile_hash: String,
    pub spec_version: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarkdownizeResponse {
    pub mode_used: MarkdownizeMode,
    pub updated_units: Vec<MarkdownUnit>,
    pub unchanged_unit_keys: Vec<String>,
    pub added_units: Vec<MarkdownUnit>,
    pub removed_unit_keys: Vec<String>,
    pub evidence_pointers: Vec<Value>,
    pub fallback_to_full: bool,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EmbeddingInputType {
    Text,
    Image,
    MarkdownChunk,
    ImageObject,
    Query,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmbeddingItem {
    pub id: String,
    pub text: Option<String>,
    pub path: Option<String>,
    pub mime: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmbeddingRequest {
    pub input_type: EmbeddingInputType,
    pub items: Vec<EmbeddingItem>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmbeddingVector {
    pub id: String,
    pub vector: Vec<f32>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EmbeddingResponse {
    pub vectors: Vec<EmbeddingVector>,
    pub dimensions: u32,
    pub distance: String,
    pub modality: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SummaryRequest {
    pub normalized_refs: Vec<String>,
    pub chunk_hashes: Vec<String>,
    pub search_result_ids: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SummaryResponse {
    pub summary_hash: String,
    pub source_hashes: Vec<String>,
    pub summary_kind: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ClassificationRequest {
    pub raw_hashes: Vec<String>,
    pub normalized_refs: Vec<String>,
    pub chunk_hashes: Vec<String>,
    pub image_object_hashes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ClassificationResponse {
    pub labels: Vec<String>,
    pub categories: Vec<String>,
    pub confidence: f64,
    pub routing_metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RerankRequest {
    pub query: String,
    pub candidate_result_ids: Vec<String>,
    pub candidate_features: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RerankResponse {
    pub reranked_result_ids: Vec<String>,
    pub scores: BTreeMap<String, f64>,
    pub searched_scopes: Vec<String>,
    pub fallback_reason: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_markdownize_request_uses_spec_mode() {
        let request = MarkdownizeRequest {
            raw: RawInput {
                raw_hash: "sha256:abc".to_owned(),
                path: Some("report.pdf".to_owned()),
            },
            media_type: "application/pdf".to_owned(),
            prepared_unit_hint: None,
            mode: MarkdownizeMode::Incremental,
            previous: None,
            hints: None,
            tool_profile_hash: "sha256:tool".to_owned(),
            spec_version: 1,
        };

        let value = serde_json::to_value(request).expect("serialize markdownize request");
        assert_eq!(value["mode"], "incremental");
    }

    #[test]
    fn placeholder_adapter_request_is_tagged() {
        let request = AdapterRequest::Prepare(Box::new(PrepareRequest {
            raw_hash: "sha256:abc".to_owned(),
            media_type: "text/plain".to_owned(),
        }));

        let value = serde_json::to_value(request).expect("serialize adapter request");
        assert_eq!(value["adapter_kind"], "prepare");
    }
}
