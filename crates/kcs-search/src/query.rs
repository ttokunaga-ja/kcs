//! Search request and AI Agent response contracts.

use serde::{Deserialize, Serialize};

use crate::evidence::EvidencePointer;
use crate::Result;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SearchMode {
    Auto,
    Text,
    Vector,
    Hybrid,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScopeSelectionMode {
    All,
    Scope,
    Descendants,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScopeSelection {
    pub mode: ScopeSelectionMode,
    pub root_path: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DiversifyStrategy {
    Mmr,
    GroupByRawHash,
    Off,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DiversifyRequest {
    pub strategy: DiversifyStrategy,
    pub mmr_lambda: Option<f64>,
    pub max_per_raw_hash: Option<u64>,
    pub mmr_depth: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SearchRequest {
    pub query: String,
    pub requested_mode: SearchMode,
    pub scope: ScopeSelection,
    pub limit: u64,
    pub offset: Option<u64>,
    pub cursor: Option<String>,
    pub at: Option<String>,
    pub all_history: bool,
    pub include_deleted: bool,
    pub since: Option<String>,
    pub diversify: Option<DiversifyRequest>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DiversifySummary {
    pub strategy: DiversifyStrategy,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mmr_lambda: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Paging {
    pub limit: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_cursor: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct IndexStatus {
    pub enriched_ratio: f64,
    pub pending_enrichment_tasks: u64,
    pub budget_paused: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SearchedScope {
    pub scope_id: String,
    pub scope_path: String,
    pub snapshot_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExcludedScope {
    pub scope_id: Option<String>,
    pub scope_path: String,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SearchResult {
    pub chunk_hash: String,
    pub evidence_pointer: EvidencePointer,
    pub evidence_uri: String,
    pub score: f64,
    pub scope_path: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SearchResponse {
    pub query: String,
    pub requested_mode: SearchMode,
    pub resolved_mode: SearchMode,
    pub fallback: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fallback_reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_code: Option<String>,
    pub diversify: DiversifySummary,
    pub paging: Paging,
    pub searched_scopes: Vec<SearchedScope>,
    pub excluded_scopes: Vec<ExcludedScope>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub index_status: Option<IndexStatus>,
    pub results: Vec<SearchResult>,
}

impl SearchResponse {
    #[must_use]
    pub fn next_cursor(&self) -> Option<&str> {
        self.paging.next_cursor.as_deref()
    }
}

pub trait SearchEngine {
    fn search(&self, request: SearchRequest) -> Result<SearchResponse>;
}

pub fn search(_request: SearchRequest) -> Result<SearchResponse> {
    todo!("Step 3c will execute search requests")
}
