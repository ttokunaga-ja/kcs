```rs
//! Review helpers for comparing the branch state named in a handoff.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReviewTarget {
    pub repository: String,
    pub branch: String,
    pub revision: String,
}

pub fn display_target(target: &ReviewTarget) -> String {
    format!("{}/{}@{}", target.repository, target.branch, target.revision)
}

pub fn is_release_branch(target: &ReviewTarget) -> bool {
    target.branch.starts_with("release/")
}
```
