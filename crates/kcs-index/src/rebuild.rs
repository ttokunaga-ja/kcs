//! Rebuild contracts for regenerating the SQLite acceleration layer.

use serde::{Deserialize, Serialize};

use crate::Result;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RebuildTarget {
    Chunks,
    Embeddings,
    Fts,
    ChunkVec,
    TreeEntries,
    All,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RebuildPlan {
    pub targets: Vec<RebuildTarget>,
    pub head_only_tree_entries: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RebuildReport {
    pub rebuilt_chunks: u64,
    pub rebuilt_embeddings: u64,
    pub rebuilt_tree_entries: u64,
}

pub trait IndexRebuilder {
    fn rebuild(&mut self, plan: RebuildPlan) -> Result<RebuildReport>;
}

pub fn rebuild_index(_plan: RebuildPlan) -> Result<RebuildReport> {
    todo!("Step 3c will rebuild index acceleration tables from objects")
}
