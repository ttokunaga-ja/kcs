//! Step 3 search crate contracts.
//!
//! This crate intentionally contains only request/response types and trait
//! skeletons for query execution, RRF, MMR, cursor handling, multi-scope merge,
//! and Evidence Pointer issue/resolve flows.

pub mod cursor;
pub mod evidence;
pub mod mmr;
pub mod multi_scope;
pub mod query;
pub mod rrf;

use thiserror::Error;

pub use cursor::{CursorToken, ScopeCursor, ScopeMode};
pub use evidence::EvidencePointer;
pub use query::{SearchRequest, SearchResponse, SearchResult};

pub type Result<T> = std::result::Result<T, SearchError>;

#[derive(Debug, Error)]
pub enum SearchError {
    #[error("search contract error: {0}")]
    Contract(String),
    #[error("invalid search cursor: {0}")]
    Cursor(String),
    #[error("evidence error: {0}")]
    Evidence(String),
    #[error("search feature not implemented: {0}")]
    NotImplemented(&'static str),
}

#[cfg(test)]
mod tests {
    use super::evidence::EvidencePointer;
    use super::query::{
        DiversifyStrategy, DiversifySummary, IndexStatus, Paging, ScopeSelection,
        ScopeSelectionMode, SearchMode, SearchRequest, SearchResponse, SearchResult, SearchedScope,
    };

    #[test]
    fn placeholder_response_exposes_agent_contract_fields() {
        let pointer = EvidencePointer {
            schema_version: 1,
            commit: "sha256:commit".to_owned(),
            tree: None,
            raw_hash: "sha256:raw".to_owned(),
            tool_profile_hash: "sha256:tool".to_owned(),
            chunk_hash: "sha256:chunk".to_owned(),
            path_at_commit: Some("report.pdf".to_owned()),
            heading_path: Some(vec!["Auth".to_owned()]),
            section_id: None,
            char_start: Some(0),
            char_end: Some(10),
            scope_id: "scope_01".to_owned(),
            scope_path: Some("/tmp/.kcs".to_owned()),
        };
        let response = SearchResponse {
            query: "auth".to_owned(),
            requested_mode: SearchMode::Auto,
            resolved_mode: SearchMode::Text,
            fallback: true,
            fallback_reason: Some("embedding_endpoint_not_configured".to_owned()),
            error_code: Some("KCS-E-SEARCH-VEC-UNAVAIL-001".to_owned()),
            diversify: DiversifySummary {
                strategy: DiversifyStrategy::Mmr,
                mmr_lambda: Some(0.7),
            },
            paging: Paging {
                limit: 20,
                next_cursor: Some("cursor".to_owned()),
            },
            searched_scopes: vec![SearchedScope {
                scope_id: "scope_01".to_owned(),
                scope_path: "/tmp/.kcs".to_owned(),
                snapshot_at: "sha256:commit".to_owned(),
            }],
            excluded_scopes: Vec::new(),
            index_status: Some(IndexStatus {
                enriched_ratio: 0.42,
                pending_enrichment_tasks: 3_120,
                budget_paused: true,
            }),
            results: vec![SearchResult {
                chunk_hash: "sha256:chunk".to_owned(),
                evidence_pointer: pointer,
                evidence_uri: "kcs://scope_01/sha256:commit/sha256:raw/sha256:tool/sha256:chunk"
                    .to_owned(),
                score: 0.87,
                scope_path: "/tmp/.kcs".to_owned(),
            }],
        };
        let request = SearchRequest {
            query: "auth".to_owned(),
            requested_mode: SearchMode::Auto,
            scope: ScopeSelection {
                mode: ScopeSelectionMode::All,
                root_path: None,
            },
            limit: 20,
            offset: None,
            cursor: None,
            at: None,
            all_history: false,
            include_deleted: false,
            since: None,
            diversify: None,
        };

        assert_eq!(request.requested_mode, SearchMode::Auto);
        assert_eq!(response.next_cursor(), Some("cursor"));
        assert_eq!(response.results[0].evidence_pointer.scope_id, "scope_01");
    }
}
