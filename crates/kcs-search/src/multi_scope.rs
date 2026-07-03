//! Multi-scope search planning and merge contracts.

use serde::{Deserialize, Serialize};

use crate::cursor::ScopeMode;
use crate::query::{SearchRequest, SearchResponse};
use crate::{Result, SearchError};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MultiScopeConfig {
    pub parallelism: u64,
    pub per_scope_timeout_seconds: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScopeSearchTarget {
    pub scope_id: String,
    pub scope_path: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScopeSearchFailure {
    pub scope_id: Option<String>,
    pub scope_path: String,
    pub reason: String,
}

pub trait ScopeRegistry {
    fn search_targets(
        &self,
        scope_mode: ScopeMode,
        root_path: Option<&str>,
    ) -> Result<Vec<ScopeSearchTarget>>;
}

pub trait MultiScopeSearchEngine {
    fn search_multi_scope(
        &self,
        request: SearchRequest,
        config: MultiScopeConfig,
    ) -> Result<SearchResponse>;
}

pub fn search_multi_scope(
    _request: SearchRequest,
    _config: MultiScopeConfig,
) -> Result<SearchResponse> {
    Err(SearchError::Contract(
        "multi-scope search engine backend must be supplied by the CLI".to_owned(),
    ))
}
