//! Chunking contracts for normalized unit instances.

use serde::{Deserialize, Serialize};

use crate::{ChunkRow, Result};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChunkingConfig {
    pub chunking_config_hash: String,
    pub target_chars: u64,
    pub overlap_chars: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NormalizedUnitInput {
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub unit_key: String,
    pub markdown: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChunkingInput {
    pub raw_path: String,
    pub units: Vec<NormalizedUnitInput>,
    pub config: ChunkingConfig,
    pub created_at: String,
}

pub trait Chunker {
    fn chunk(&self, input: ChunkingInput) -> Result<Vec<ChunkRow>>;
}

pub fn chunk_normalized_instance(_input: ChunkingInput) -> Result<Vec<ChunkRow>> {
    todo!("Step 3c will implement chunk extraction")
}
