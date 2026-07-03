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

pub fn project_commit_tree(input: TreeProjectionInput) -> Result<Vec<TreeEntryRow>> {
    let mut entries = input
        .entries
        .into_iter()
        .map(|mut entry| {
            entry.commit_hash = input.commit_hash.clone();
            entry
        })
        .collect::<Vec<_>>();
    entries.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(entries)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ct3_chunk_010_tree_entries_project_head_commit_with_gen() {
        let rows = project_commit_tree(TreeProjectionInput {
            commit_hash: "sha256:commit".to_owned(),
            entries: vec![TreeEntryRow {
                commit_hash: String::new(),
                path: "b.md".to_owned(),
                raw_hash: "sha256:raw".to_owned(),
                tool_profile_hash: Some("sha256:tool".to_owned()),
                gen: 3,
            }],
        })
        .unwrap();
        assert_eq!(rows[0].commit_hash, "sha256:commit");
        assert_eq!(rows[0].gen, 3);
    }
}
