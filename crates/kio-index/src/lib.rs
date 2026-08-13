//! Step 3 index crate contracts.
//!
//! This crate intentionally contains only types and trait skeletons for the
//! chunking, FTS, embedding, tree projection, and rebuild layers.

pub mod aggregator;
pub mod chunking;
pub mod embedding_store;
pub mod fts;
pub mod registry;
pub mod rows;
mod search_projection;
pub mod vec;

use rusqlite::Error as SqliteError;
use thiserror::Error;

pub use rows::{
    ChunkRow, EmbeddingDistance, EmbeddingModality, EmbeddingRow, EmbeddingTargetType, TreeEntryRow,
};

pub type Result<T> = std::result::Result<T, IndexError>;

#[derive(Debug, Error)]
pub enum IndexError {
    #[error("index contract error: {0}")]
    Contract(String),
    #[error("index schema error: {0}")]
    Schema(String),
    #[error("index sqlite error: {0}")]
    Sqlite(#[from] SqliteError),
}

impl From<serde_json::Error> for IndexError {
    fn from(value: serde_json::Error) -> Self {
        Self::Schema(value.to_string())
    }
}
