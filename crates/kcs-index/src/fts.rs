//! FTS5 external-content index contracts.

use serde::{Deserialize, Serialize};

use crate::{ChunkRow, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FtsTokenizer {
    Trigram,
    Unicode61RemoveDiacritics2,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FtsSchemaConfig {
    pub tokenizer: FtsTokenizer,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FtsMatch {
    pub chunk_id: String,
    pub rank: u64,
    pub bm25_score: f64,
}

pub trait FtsIndex {
    fn ensure_schema(&mut self, config: FtsSchemaConfig) -> Result<()>;

    fn index_chunk(&mut self, row: &ChunkRow) -> Result<()>;

    fn delete_chunk(&mut self, chunk_id: &str) -> Result<()>;

    fn search(&self, query: &str, limit: u64) -> Result<Vec<FtsMatch>>;
}

pub fn ensure_fts_external_content_schema(_config: FtsSchemaConfig) -> Result<()> {
    todo!("Step 3c will create FTS5 external-content schema and triggers")
}
