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
            return Err(KcsError::duplicate_path(pair[0].path.clone()));
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
        if !is_valid_created_at(&created_at) {
            return Err(KcsError::schema(
                "created_at must be UTC ISO8601 YYYY-MM-DDTHH:MM:SSZ",
            ));
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

/// Strictly validate a `created_at` timestamp as `YYYY-MM-DDTHH:MM:SSZ`
/// (UTC ISO8601, `06 §12`). An optional fractional-second suffix `.NNN…` before
/// the trailing `Z` is accepted (`06 §12` permits microsecond precision). Checks
/// digit positions, separators, and calendar validity (month-aware day count
/// including leap years). Leap seconds (`:60`) are rejected — KCS only emits
/// second-precision timestamps derived from Unix time, which never produce
/// `:60` (WS1d cross-review ruling).
fn is_valid_created_at(value: &str) -> bool {
    let Some(body) = value.strip_suffix('Z') else {
        return false;
    };
    // Split an optional fractional-second part; it must be all digits.
    let datetime = match body.split_once('.') {
        Some((head, frac)) => {
            if frac.is_empty() || !frac.bytes().all(|b| b.is_ascii_digit()) {
                return false;
            }
            head
        }
        None => body,
    };
    let bytes = datetime.as_bytes();
    if bytes.len() != 19 {
        return false;
    }
    if bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
    {
        return false;
    }
    for &index in &[0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18] {
        if !bytes[index].is_ascii_digit() {
            return false;
        }
    }
    let field = |lo: usize, hi: usize| datetime[lo..hi].parse::<u32>().unwrap_or(u32::MAX);
    let year = field(0, 4);
    let month = field(5, 7);
    let day = field(8, 10);
    let hour = field(11, 13);
    let minute = field(14, 16);
    let second = field(17, 19);
    if !(1..=12).contains(&month) {
        return false;
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let max_day = match month {
        4 | 6 | 9 | 11 => 30,
        2 => {
            if leap {
                29
            } else {
                28
            }
        }
        _ => 31,
    };
    (1..=max_day).contains(&day) && hour <= 23 && minute <= 59 && second <= 59
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

#[cfg(test)]
mod tests {
    use super::{is_valid_created_at, CommitObject, CommitStats, CommitType};
    use crate::error::Result;

    fn commit_with_created_at(created_at: &str) -> Result<CommitObject> {
        CommitObject::new(
            "sha256:eca8de0abaf2a27a1ea57feff4f44385bcfb3485274e73ddfa7c47144f383e1e".to_owned(),
            Vec::new(),
            created_at.to_owned(),
            "m".to_owned(),
            "sha256:8a32a740871b1dd9db1bda186dce07e8e6c60d2cd316f21683ea2bd857c16ffb".to_owned(),
            CommitStats {
                files_added: 0,
                files_modified: 0,
                files_deleted: 0,
            },
            CommitType::Manual,
        )
    }

    #[test]
    fn created_at_accepts_canonical_and_fractional() {
        assert!(is_valid_created_at("2026-04-29T12:00:00Z"));
        assert!(is_valid_created_at("1970-01-01T00:00:00Z"));
        assert!(is_valid_created_at("2026-04-29T12:00:00.123456Z"));
        assert!(is_valid_created_at("2024-02-29T00:00:00Z")); // leap day
        assert!(is_valid_created_at("2000-02-29T00:00:00Z")); // %400 leap
        assert!(commit_with_created_at("2026-04-29T12:00:00Z").is_ok());
    }

    #[test]
    fn created_at_rejects_malformed() {
        for bad in [
            "2026-04-29T12:00:00",   // missing Z
            "2026-04-29 12:00:00Z",  // space instead of T
            "2026-4-29T12:00:00Z",   // single-digit month
            "2026-13-01T00:00:00Z",  // month 13
            "2026-04-32T00:00:00Z",  // day 32
            "2026-04-29T24:00:00Z",  // hour 24
            "2026-04-29T12:60:00Z",  // minute 60
            "2026-04-29T12:00:60Z",  // leap second not emitted by KCS
            "2026-02-30T00:00:00Z",  // Feb 30
            "2026-04-31T00:00:00Z",  // Apr 31
            "2023-02-29T00:00:00Z",  // non-leap Feb 29
            "2100-02-29T00:00:00Z",  // %100 non-leap Feb 29
            "2026/04/29T12:00:00Z",  // wrong separators
            "2026-04-29T12:00:00.Z", // empty fraction
            "hello Z",               // garbage ending in Z
            "",                      // empty
        ] {
            assert!(!is_valid_created_at(bad), "should reject {bad:?}");
            assert!(
                commit_with_created_at(bad).is_err(),
                "commit should reject {bad:?}"
            );
        }
    }
}
