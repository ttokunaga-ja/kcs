//! SQLite row contracts for the Step 3 index acceleration layer.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChunkRow {
    pub chunk_id: String,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub unit_key: String,
    pub chunking_config_hash: String,
    pub raw_path: String,
    pub heading_path: Option<Vec<String>>,
    pub section_id: Option<String>,
    /// Unit-local UTF-8 byte offset, 0-based half-open (03 §8.1). Always
    /// present — part of the chunk identity tuple, not an optional field.
    pub byte_start: u64,
    pub byte_end: u64,
    pub text_hash: String,
    pub text: String,
    pub first_seen_commit: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EmbeddingTargetType {
    Chunk,
    Image,
    Node,
    QueryCache,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EmbeddingModality {
    Text,
    Image,
    Multimodal,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EmbeddingDistance {
    Cosine,
    L2,
    InnerProduct,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EmbeddingRow {
    pub id: String,
    pub target_type: EmbeddingTargetType,
    pub target_id: String,
    pub modality: EmbeddingModality,
    pub vector: Vec<u8>,
    pub dimensions: u64,
    pub distance: EmbeddingDistance,
    pub profile_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TreeEntryRow {
    pub commit_hash: String,
    pub path: String,
    pub raw_hash: String,
    pub tool_profile_hash: Option<String>,
    pub gen: u64,
}
