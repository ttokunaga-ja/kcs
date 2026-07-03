//! Commit tree projection contracts for time-travel search liveness.

use serde::{Deserialize, Serialize};

use crate::{Result, TreeEntryRow};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TreeProjectionInput {
    pub commit_hash: String,
    pub entries: Vec<TreeEntryRow>,
}

pub trait TreeEntryProjector {
    fn project_tree_entries(&mut self, input: TreeProjectionInput) -> Result<Vec<TreeEntryRow>>;

    fn entries_for_commit(&self, commit_hash: &str) -> Result<Vec<TreeEntryRow>>;
}

pub fn project_commit_tree(_input: TreeProjectionInput) -> Result<Vec<TreeEntryRow>> {
    todo!("Step 3c will project tree objects into tree_entries")
}
