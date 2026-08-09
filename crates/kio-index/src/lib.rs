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
    #[error("index feature not implemented: {0}")]
    NotImplemented(&'static str),
}

impl From<serde_json::Error> for IndexError {
    fn from(value: serde_json::Error) -> Self {
        Self::Schema(value.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::ChunkRow;

    #[test]
    fn placeholder_chunk_row_exposes_step3_schema_fields() {
        let row = ChunkRow {
            chunk_id: "sha256:chunk".to_owned(),
            raw_hash: "sha256:raw".to_owned(),
            tool_profile_hash: "sha256:tool".to_owned(),
            gen: 0,
            unit_key: "page:1".to_owned(),
            chunking_config_hash: "sha256:cfg".to_owned(),
            raw_path: "report.pdf".to_owned(),
            heading_path: Some(vec!["Auth".to_owned()]),
            section_id: None,
            byte_start: 0,
            byte_end: 10,
            text_hash: "sha256:text".to_owned(),
            text: "sample text".to_owned(),
            first_seen_commit: None,
            chunking_config_introduction_commit: None,
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        };

        assert_eq!(row.chunk_id, "sha256:chunk");
        assert_eq!(row.gen, 0);
        assert_eq!(row.heading_path.as_deref(), Some(&["Auth".to_owned()][..]));
    }
}
