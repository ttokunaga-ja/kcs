//! `tool-lock.json` identity contracts.

use serde::{Deserialize, Serialize};

use crate::types::ExecutionMode;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ToolLock {
    pub spec_version: u64,
    pub prepare: Option<PrepareToolLockEntry>,
    pub markdown: Option<MarkdownToolLockEntry>,
    pub embedding: Option<EmbeddingToolLockEntry>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareToolLockEntry {
    pub tool_id: String,
    pub kind: ExecutionMode,
    pub profile_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarkdownToolLockEntry {
    pub tool_id: String,
    pub kind: ExecutionMode,
    pub profile_hash: String,
    pub capabilities: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EmbeddingToolLockEntry {
    pub tool_id: String,
    pub kind: ExecutionMode,
    pub mode: String,
    pub dimensions: u32,
    pub distance: String,
    pub modality: String,
    pub profile_hash: String,
}

pub fn load_tool_lock(_bytes: &[u8]) -> crate::Result<ToolLock> {
    todo!("implement tool-lock parsing and validation in Step 2");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_tool_lock_serializes_spec_version() {
        let lock = ToolLock {
            spec_version: 1,
            prepare: None,
            markdown: None,
            embedding: None,
        };

        let value = serde_json::to_value(lock).expect("serialize tool lock");
        assert_eq!(value["spec_version"], 1);
    }
}
