//! Search request and AI Agent response contracts.

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use unicode_normalization::UnicodeNormalization;

use crate::{Result, SearchError};

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
pub struct QueryHashInput {
    pub query: String,
    pub mode: SearchMode,
    pub scope_mode: ScopeSelectionMode,
    pub scopes: Vec<String>,
    pub diversify: DiversifyRequest,
    pub rrf_k: u64,
    pub rrf_candidate_depth: u64,
    pub rrf_w_text: f64,
    pub rrf_w_vector: f64,
    pub at: Option<String>,
    pub all_history: bool,
    pub include_deleted: bool,
    pub since: Option<String>,
}

pub fn query_hash(input: &QueryHashInput) -> Result<String> {
    let mut scopes = input.scopes.clone();
    scopes.sort();
    let mut time_travel = Map::new();
    if let Some(at) = &input.at {
        time_travel.insert("at".to_owned(), json!(at));
    }
    if input.all_history {
        time_travel.insert("all_history".to_owned(), json!(true));
    }
    if input.include_deleted {
        time_travel.insert("include_deleted".to_owned(), json!(true));
    }
    if let Some(since) = &input.since {
        time_travel.insert("since".to_owned(), json!(since));
    }
    let value = json!({
        "diversify": {
            "enabled": input.diversify.strategy != DiversifyStrategy::Off,
            "max_per_raw_hash": input.diversify.max_per_raw_hash.unwrap_or(3),
            "mmr_depth": input.diversify.mmr_depth.unwrap_or(100),
            "mmr_lambda": input.diversify.mmr_lambda.unwrap_or(0.7),
            "strategy": strategy_name(input.diversify.strategy),
        },
        "mode": search_mode_name(input.mode),
        "query": input.query.nfc().collect::<String>(),
        "rrf": {
            "candidate_depth": input.rrf_candidate_depth,
            "k": input.rrf_k,
            "w_text": input.rrf_w_text,
            "w_vector": input.rrf_w_vector,
        },
        "scope_mode": scope_mode_name(input.scope_mode),
        "scopes": scopes,
        "time_travel": Value::Object(time_travel),
    });
    let bytes = serde_jcs::to_vec(&value).map_err(|err| SearchError::Contract(err.to_string()))?;
    Ok(hash_bytes(&bytes))
}

pub fn search_mode_name(mode: SearchMode) -> &'static str {
    match mode {
        SearchMode::Auto => "auto",
        SearchMode::Text => "text",
        SearchMode::Vector => "vector",
        SearchMode::Hybrid => "hybrid",
    }
}

pub fn scope_mode_name(mode: ScopeSelectionMode) -> &'static str {
    match mode {
        ScopeSelectionMode::All => "all",
        ScopeSelectionMode::Scope => "scope",
        ScopeSelectionMode::Descendants => "descendants",
    }
}

pub fn strategy_name(strategy: DiversifyStrategy) -> &'static str {
    match strategy {
        DiversifyStrategy::Mmr => "mmr",
        DiversifyStrategy::GroupByRawHash => "group_by_raw_hash",
        DiversifyStrategy::Off => "off",
    }
}

fn hash_bytes(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    format!("sha256:{}", lower_hex(&digest))
}

fn lower_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ct3_cursor_003_query_hash_vector() {
        let hash = query_hash(&QueryHashInput {
            query: "認証仕様".to_owned(),
            mode: SearchMode::Hybrid,
            scope_mode: ScopeSelectionMode::All,
            scopes: vec![
                "scope_01K3ABCDEFGHJKMNPQRSTV".to_owned(),
                "scope_01J8ZQABCDEFGHJKMNPQRS".to_owned(),
            ],
            diversify: DiversifyRequest {
                strategy: DiversifyStrategy::Mmr,
                mmr_lambda: Some(0.7),
                max_per_raw_hash: Some(3),
                mmr_depth: Some(100),
            },
            rrf_k: 60,
            rrf_candidate_depth: 200,
            rrf_w_text: 1.0,
            rrf_w_vector: 1.0,
            at: None,
            all_history: false,
            include_deleted: false,
            since: None,
        })
        .unwrap();
        assert_eq!(
            hash,
            "sha256:08820fbe38f26821717a56fde4cc1db4e104c5ff1221f62477127c070503d773"
        );
    }
}
