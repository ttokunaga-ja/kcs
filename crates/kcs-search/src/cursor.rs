//! Cursor token contracts for deterministic paging.

use serde::{Deserialize, Serialize};

use crate::Result;

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

pub fn encode_cursor_token(_token: &CursorToken) -> Result<String> {
    todo!("Step 3c will JCS-serialize and base64url-encode cursor tokens")
}

pub fn decode_cursor_token(_token: &str) -> Result<CursorToken> {
    todo!("Step 3c will decode opaque cursor tokens")
}
