//! Cursor token contracts for deterministic paging.

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use serde::{Deserialize, Serialize};

use crate::{Result, SearchError};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScopeMode {
    All,
    Scope,
    Descendants,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScopeCursor {
    pub scope_id: String,
    pub snapshot_commit: String,
    pub max_rowid: u64,
    pub consumed: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CursorToken {
    #[serde(rename = "v")]
    pub version: u64,
    pub scope_mode: ScopeMode,
    pub query_hash: String,
    pub scopes: Vec<ScopeCursor>,
}

pub fn encode_cursor_token(token: &CursorToken) -> Result<String> {
    let value = serde_json::to_value(token).map_err(|err| SearchError::Cursor(err.to_string()))?;
    let bytes = serde_jcs::to_vec(&value).map_err(|err| SearchError::Cursor(err.to_string()))?;
    Ok(URL_SAFE_NO_PAD.encode(bytes))
}

pub fn decode_cursor_token(token: &str) -> Result<CursorToken> {
    let bytes = URL_SAFE_NO_PAD
        .decode(token)
        .map_err(|err| SearchError::Cursor(err.to_string()))?;
    serde_json::from_slice(&bytes).map_err(|err| SearchError::Cursor(err.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ct3_cursor_004_cursor_is_base64url_jcs_json() {
        let token = CursorToken {
            version: 1,
            scope_mode: ScopeMode::All,
            query_hash: "sha256:query".to_owned(),
            scopes: vec![ScopeCursor {
                scope_id: "scope_01".to_owned(),
                snapshot_commit: "sha256:commit".to_owned(),
                max_rowid: 42,
                consumed: 20,
            }],
        };
        let encoded = encode_cursor_token(&token).unwrap();
        assert_eq!(decode_cursor_token(&encoded).unwrap(), token);
        assert!(!encoded.contains('='));
    }
}
