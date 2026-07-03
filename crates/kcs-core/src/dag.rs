//! Snapshot DAG object types.

use std::fmt;
use std::str::FromStr;

use serde::{Deserialize, Serialize};

use crate::cas::{hash_json, is_hash};
use crate::error::{KcsError, Result};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NormalizeRef {
    pub tool_profile_hash: String,
    #[serde(default)]
    pub gen: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TreeEntry {
    pub path: String,
    #[serde(rename = "type")]
    pub entry_type: String,
    pub raw_hash: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub normalize: Option<NormalizeRef>,
}

impl TreeEntry {
    pub fn raw_file(path: impl Into<String>, raw_hash: impl Into<String>) -> Result<Self> {
        let entry = Self {
            path: path.into(),
            entry_type: "file".to_owned(),
            raw_hash: raw_hash.into(),
            normalize: None,
        };
        entry.validate()?;
        Ok(entry)
    }

    pub fn validate(&self) -> Result<()> {
        if self.path.contains('/') {
            return Err(KcsError::path(
                "tree entry path must be a direct child file name",
                self.path.clone(),
            ));
        }
        if self.path.is_empty() {
            return Err(KcsError::path(
                "tree entry path is empty",
                self.path.clone(),
            ));
        }
        if self.entry_type != "file" {
            return Err(KcsError::schema("Step 1 tree entry type must be file"));
        }
        if !is_hash(&self.raw_hash) {
            return Err(KcsError::schema("raw_hash must be sha256 lowercase hex"));
        }
        if let Some(normalize) = &self.normalize {
            if !is_hash(&normalize.tool_profile_hash) {
                return Err(KcsError::schema(
                    "tool_profile_hash must be sha256 lowercase hex",
                ));
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TreeObject {
    pub entries: Vec<TreeEntry>,
    pub object_type: String,
}

pub fn build_tree(mut entries: Vec<TreeEntry>) -> Result<TreeObject> {
    for entry in &entries {
        entry.validate()?;
    }

    entries.sort_by(|a, b| a.path.as_bytes().cmp(b.path.as_bytes()));
    for pair in entries.windows(2) {
        if pair[0].path == pair[1].path {
            return Err(KcsError::path(
                "duplicate tree entry path",
                pair[0].path.clone(),
            ));
        }
    }

    Ok(TreeObject {
        entries,
        object_type: "tree".to_owned(),
    })
}

pub fn tree_hash(tree: &TreeObject) -> Result<String> {
    hash_json(&serde_json::to_value(tree).map_err(|err| KcsError::schema(err.to_string()))?)
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CommitStats {
    pub files_added: u64,
    pub files_modified: u64,
    pub files_deleted: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CommitObject {
    pub commit_type: CommitType,
    pub created_at: String,
    pub message: String,
    pub object_type: String,
    pub parents: Vec<String>,
    pub stats: CommitStats,
    pub tool_lock_hash: String,
    pub tree: String,
}

impl CommitObject {
    pub fn new(
        tree: String,
        parents: Vec<String>,
        created_at: String,
        message: String,
        tool_lock_hash: String,
        stats: CommitStats,
        commit_type: CommitType,
    ) -> Result<Self> {
        if !is_hash(&tree) {
            return Err(KcsError::schema("tree must be sha256 lowercase hex"));
        }
        if !is_hash(&tool_lock_hash) {
            return Err(KcsError::schema(
                "tool_lock_hash must be sha256 lowercase hex",
            ));
        }
        for parent in &parents {
            if !is_hash(parent) {
                return Err(KcsError::schema("parent must be sha256 lowercase hex"));
            }
        }
        if !created_at.ends_with('Z') || !created_at.contains('T') {
            return Err(KcsError::schema("created_at must be UTC ISO8601 with Z"));
        }

        Ok(Self {
            commit_type,
            created_at,
            message,
            object_type: "commit".to_owned(),
            parents,
            stats,
            tool_lock_hash,
            tree,
        })
    }
}

pub fn commit_hash(commit: &CommitObject) -> Result<String> {
    hash_json(&serde_json::to_value(commit).map_err(|err| KcsError::schema(err.to_string()))?)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CommitType {
    Manual,
    Auto,
    Imported,
    Migrated,
    Repaired,
    Merged,
    Purged,
}

impl FromStr for CommitType {
    type Err = KcsError;

    fn from_str(value: &str) -> Result<Self> {
        match value {
            "manual" => Ok(Self::Manual),
            "auto" => Ok(Self::Auto),
            "imported" => Ok(Self::Imported),
            "migrated" => Ok(Self::Migrated),
            "repaired" => Ok(Self::Repaired),
            "merged" => Ok(Self::Merged),
            "purged" => Ok(Self::Purged),
            _ => Err(KcsError::schema("invalid commit_type")),
        }
    }
}

impl fmt::Display for CommitType {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Manual => "manual",
            Self::Auto => "auto",
            Self::Imported => "imported",
            Self::Migrated => "migrated",
            Self::Repaired => "repaired",
            Self::Merged => "merged",
            Self::Purged => "purged",
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GcPolicy {
    None,
    Shallow,
    Full,
}

#[must_use]
pub const fn gc_policy(commit_type: CommitType) -> GcPolicy {
    match commit_type {
        CommitType::Auto | CommitType::Migrated | CommitType::Repaired => GcPolicy::Shallow,
        CommitType::Manual | CommitType::Imported | CommitType::Merged | CommitType::Purged => {
            GcPolicy::None
        }
    }
}

#[must_use]
pub const fn protected(commit_type: CommitType) -> bool {
    match commit_type {
        CommitType::Manual | CommitType::Imported | CommitType::Merged | CommitType::Purged => true,
        CommitType::Auto | CommitType::Migrated | CommitType::Repaired => false,
    }
}
