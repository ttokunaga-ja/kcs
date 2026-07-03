//! Embedding metadata and chunk_vec store contracts.

use serde::{Deserialize, Serialize};

use crate::{EmbeddingRow, EmbeddingTargetType, Result};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EmbeddingLookup {
    pub target_type: EmbeddingTargetType,
    pub target_id: String,
    pub profile_hash: String,
}

pub trait EmbeddingStore {
    fn upsert_embedding(&mut self, row: EmbeddingRow) -> Result<()>;

    fn get_embedding(&self, lookup: EmbeddingLookup) -> Result<Option<EmbeddingRow>>;

    fn rebuild_chunk_vec(&mut self) -> Result<()>;
}

pub fn rebuild_chunk_vec_from_embeddings(_store: &mut dyn EmbeddingStore) -> Result<()> {
    todo!("Step 3c will rebuild sqlite-vec from embeddings")
}
