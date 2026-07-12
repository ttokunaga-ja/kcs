//! Folder-scope repository operations for Step 1.

use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
#[cfg(not(windows))]
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

use crate::cas::{
    append_jsonl, atomic_overwrite, atomic_write, hash_json, is_hash, ObjectKind, ObjectStore,
    CAS_STREAM_BUFFER_BYTES, MAX_RAW_OBJECT_BYTES,
};
use crate::dag::{
    build_tree, CommitObject, CommitStats, CommitType, NormalizeRef, TreeEntry, TreeObject,
};
use crate::error::{IoResultExt, KcsError, Result};
use crate::schema::{validate_json_schema, SchemaKind};
use crate::ExitCode;

const FORMAT_VERSION: &str = "0.1.0";
pub const DEFAULT_MAX_ARCHIVE_FILE_BYTES: u64 = MAX_RAW_OBJECT_BYTES;
pub const DEFAULT_MAX_ARCHIVE_SCOPE_BYTES: u64 = 4 * 1024 * 1024 * 1024;
pub const MAX_TREE_ENTRIES: usize = 10_000;
pub const MAX_COMMIT_PARENTS: usize = 64;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ArchiveLimits {
    pub max_file_bytes: u64,
    pub max_scope_bytes: u64,
}

impl ArchiveLimits {
    #[must_use]
    pub const fn new(max_file_bytes: u64, max_scope_bytes: u64) -> Self {
        Self {
            max_file_bytes,
            max_scope_bytes,
        }
    }
}

impl Default for ArchiveLimits {
    fn default() -> Self {
        Self::new(
            DEFAULT_MAX_ARCHIVE_FILE_BYTES,
            DEFAULT_MAX_ARCHIVE_SCOPE_BYTES,
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ScopeIdentity {
    pub scope_id: String,
    pub canonical_root: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PendingNormalizeRef {
    pub expected_raw_hash: String,
    pub normalize: NormalizeRef,
}

#[derive(Debug)]
struct WorkingFileCandidate {
    path: PathBuf,
    file_name: String,
}

#[derive(Debug, Clone)]
pub struct Repository {
    root: PathBuf,
    kcs_dir: PathBuf,
    store: ObjectStore,
}

#[derive(Debug, Clone)]
pub struct WorkingTree {
    pub tree: TreeObject,
}

#[derive(Debug, Clone, Serialize)]
pub struct FileStatus {
    pub path: PathBuf,
    pub relative_path: String,
    /// The working-tree-vs-HEAD classification (`new`/`modified`/`deleted`/
    /// `unchanged`). R15-4: `None` (field omitted) when HEAD is shallow — the prior
    /// tree needed to classify is gone, so a pure `kcs status` degrades to listing
    /// current files without a classification rather than dying.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub raw_hash: Option<String>,
}

/// The result of [`Repository::status`]: the per-file statuses plus a degradation
/// flag. R15-4: when HEAD names a commit whose tree object is gone (shallow), the
/// per-file `status` classification cannot be computed — `head_shallow` is `true`,
/// each file's `status` is omitted, and the command still succeeds (exit 0) so the
/// scope stays inspectable instead of bricking on a raw `KCS-E-STORE-NOT-FOUND-001`.
#[derive(Debug, Clone, Serialize)]
pub struct StatusReport {
    pub files: Vec<FileStatus>,
    pub head_shallow: bool,
}

/// R15-4: the availability of the HEAD commit's tree object.
enum HeadTreeState {
    /// No HEAD commit — an unborn branch (a first snapshot creates the root).
    Unborn,
    /// HEAD names a commit whose TREE object is gone, OR whose COMMIT object itself
    /// is gone (shallow: GC'd / manually deleted / corrupt CAS). R16-1 folds the
    /// missing-commit case in here too: it is the same corruption class as a missing
    /// tree, with the same policy — pure reads degrade; writes must fail loudly. (The
    /// write paths carry their own HEAD hash for the error context, so this variant
    /// needs no payload.)
    Shallow,
    /// HEAD's commit and tree object are both present.
    Present(TreeObject),
}

#[derive(Debug, Clone)]
pub struct SnapshotOutcome {
    pub noop: bool,
    pub message: String,
    pub tree_hash: String,
    pub commit_hash: Option<String>,
    pub commit: Option<CommitObject>,
    pub stats: CommitStats,
}

#[derive(Debug, Clone, Serialize)]
pub struct LogEntry {
    pub commit_hash: String,
    #[serde(flatten)]
    pub commit: CommitObject,
}

/// The result of [`Repository::log`]: the reachable history plus a truncation flag.
/// R16-1: when an ancestor commit object is gone (shallow / external corruption),
/// history traversal stops at that point and returns the healthy prefix from HEAD
/// with `truncated = true`, rather than bricking the whole `log` on a raw
/// `KCS-E-STORE-NOT-FOUND-001`. The omission is always explicit, never silent.
#[derive(Debug, Clone, Serialize)]
pub struct LogReport {
    pub entries: Vec<LogEntry>,
    pub truncated: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct DiffEntry {
    pub path: PathBuf,
    pub relative_path: String,
    pub change: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub old_raw_hash: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub new_raw_hash: Option<String>,
}

#[derive(Debug, Clone)]
pub enum InspectedObject {
    Tree(TreeObject),
    Commit(CommitObject),
    Raw { raw_hash: String, size_bytes: u64 },
}

impl Repository {
    pub fn init(path: impl AsRef<Path>) -> Result<Self> {
        let root = path.as_ref();
        if !root.exists() {
            return Err(KcsError::invalid_usage("init path does not exist"));
        }
        if !root.is_dir() {
            return Err(KcsError::invalid_usage("init path must be a directory"));
        }

        let root = root.canonicalize().kcs_io(root)?;
        let kcs_dir = root.join(".kcs");
        match fs::symlink_metadata(&kcs_dir) {
            Ok(_) => return Self::open(root),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(KcsError::io(
                    error.to_string(),
                    kcs_dir.display().to_string(),
                ))
            }
        }

        for dir in [
            kcs_dir.join("objects/raw"),
            kcs_dir.join("objects/trees"),
            kcs_dir.join("objects/commits"),
            kcs_dir.join("refs/heads"),
            kcs_dir.join("refs/tags"),
            kcs_dir.join("logs"),
        ] {
            fs::create_dir_all(&dir).kcs_io(&dir)?;
        }

        // P2: restrict the `.kcs` tree to the owner (0700). objects/raw holds the
        // verbatim document bytes (secrets included, even unclassified ones), and
        // approvals/tasks/quarantine logs plus sqlite.db carry actor names and
        // usage patterns — none of it should be world/group-readable on a
        // multi-user host (07 §1 secrecy posture). A 0700 parent blocks traversal
        // into the whole subtree regardless of child file modes; no-op on non-unix.
        restrict_dir_to_owner(&kcs_dir)?;

        atomic_write(&kcs_dir.join("HEAD"), b"")?;
        atomic_write(&kcs_dir.join("refs/heads/main"), b"")?;
        atomic_write(
            &kcs_dir.join("config.toml"),
            format!("kcs_format_version = \"{FORMAT_VERSION}\"\n").as_bytes(),
        )?;
        atomic_write(
            &kcs_dir.join("scope.json"),
            serde_json::to_string_pretty(&json!({
                "kcs_format_version": FORMAT_VERSION,
                "scope_id": new_ulid(&root),
                "scope_path": root,
            }))
            .map_err(|err| KcsError::schema(err.to_string()))?
            .as_bytes(),
        )?;
        atomic_write(
            &kcs_dir.join("manifest.json"),
            b"{\n  \"schema_version\": 1,\n  \"files\": []\n}\n",
        )?;
        atomic_write(
            &kcs_dir.join("tool-lock.json"),
            b"{\n  \"spec_version\": 1\n}\n",
        )?;

        Self::open(root)
    }

    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let root = path.as_ref().canonicalize().kcs_io(path.as_ref())?;
        let kcs_dir = root.join(".kcs");
        validate_store_directory(&kcs_dir)?;

        let repo = Self {
            root,
            kcs_dir: kcs_dir.clone(),
            store: ObjectStore::new(kcs_dir),
        };
        repo.validate()?;
        // R13-4: repair a corrupt (empty/missing) HEAD from refs/heads/main before
        // any command reads or advances HEAD. Done on every `open` so `log`/`status`
        // display the real history and `snapshot` extends it (rather than orphaning
        // it under a fresh root commit). A healthy HEAD is an untouched no-op.
        repo.self_heal_head()?;
        Ok(repo)
    }

    pub fn open_current() -> Result<Self> {
        let cwd = std::env::current_dir().map_err(|err| KcsError::io(err.to_string(), "."))?;
        Self::open(cwd)
    }

    #[must_use]
    pub fn root(&self) -> &Path {
        &self.root
    }

    #[must_use]
    pub fn kcs_dir(&self) -> &Path {
        &self.kcs_dir
    }

    /// Return the portable scope ID together with the canonical local root.
    /// Authorization callers must bind both values to protected device-local
    /// state; `scope.json` alone is portable audit data, not active consent.
    pub fn scope_identity(&self) -> Result<ScopeIdentity> {
        validate_store_directory(&self.kcs_dir)?;
        Ok(ScopeIdentity {
            scope_id: self.validated_scope_id()?,
            canonical_root: self.root.clone(),
        })
    }

    /// Acquire the exclusive `.kcs/.lock` store lock (05 §6) and return an RAII
    /// guard held for the caller's lifetime. Used to serialize whole mutating
    /// commands (`kcs index` / `repair` / `reindex`) end-to-end, not just their
    /// snapshot sub-step. The lock is reentrant within a single process, so a
    /// held guard does not deadlock when `snapshot` re-acquires it internally.
    /// The loser of a concurrent acquisition gets `KCS-E-STORE-LOCKED-001`
    /// (exit 3), the same contract as `snapshot` / `tag`.
    pub fn lock_store(&self) -> Result<StoreLock> {
        StoreLock::acquire(&self.kcs_dir)
    }

    pub fn validate(&self) -> Result<()> {
        validate_store_directory(&self.kcs_dir)?;
        self.validate_config()?;
        self.validate_scope()?;
        self.validate_manifest()?;
        Ok(())
    }

    pub fn build_working_tree(&self, store_raw: bool) -> Result<WorkingTree> {
        self.build_working_tree_filtered(store_raw, &BTreeSet::new())
    }

    pub fn build_working_tree_filtered(
        &self,
        store_raw: bool,
        excluded_paths: &BTreeSet<String>,
    ) -> Result<WorkingTree> {
        self.build_working_tree_with_normalize(store_raw, excluded_paths, &BTreeMap::new())
    }

    pub fn build_working_tree_with_normalize(
        &self,
        store_raw: bool,
        excluded_paths: &BTreeSet<String>,
        normalize_by_path: &BTreeMap<String, NormalizeRef>,
    ) -> Result<WorkingTree> {
        if !normalize_by_path.is_empty() {
            return Err(KcsError::invalid_usage(
                "normalization metadata must include its expected raw hash",
            ));
        }
        self.build_working_tree_with_limits(
            store_raw,
            excluded_paths,
            normalize_by_path,
            ArchiveLimits::default(),
        )
    }

    pub fn build_working_tree_with_limits(
        &self,
        store_raw: bool,
        excluded_paths: &BTreeSet<String>,
        normalize_by_path: &BTreeMap<String, NormalizeRef>,
        limits: ArchiveLimits,
    ) -> Result<WorkingTree> {
        if !normalize_by_path.is_empty() {
            return Err(KcsError::invalid_usage(
                "normalization metadata must include its expected raw hash",
            ));
        }
        self.build_working_tree_with_bound_normalize_and_limits(
            store_raw,
            excluded_paths,
            &BTreeMap::new(),
            &BTreeSet::new(),
            limits,
        )
    }

    pub fn build_working_tree_with_bound_normalize_and_limits(
        &self,
        store_raw: bool,
        excluded_paths: &BTreeSet<String>,
        normalize_by_path: &BTreeMap<String, PendingNormalizeRef>,
        explicitly_allowed_tier_a_paths: &BTreeSet<String>,
        limits: ArchiveLimits,
    ) -> Result<WorkingTree> {
        if limits.max_file_bytes > MAX_RAW_OBJECT_BYTES {
            return Err(KcsError::invalid_usage(
                "archive max_file_bytes exceeds the raw CAS object limit",
            ));
        }

        let candidates = self.working_file_candidates(
            excluded_paths,
            explicitly_allowed_tier_a_paths,
            store_raw,
            limits,
        )?;
        let mut entries = Vec::new();
        let mut consumed_scope_bytes = 0_u64;
        for candidate in candidates {
            let mut file = open_scope_file_nofollow(&candidate.path)?;
            let metadata = file.metadata().kcs_io(&candidate.path)?;
            let remaining = limits
                .max_scope_bytes
                .checked_sub(consumed_scope_bytes)
                .ok_or_else(|| scope_input_oversized(&candidate.file_name, limits, u64::MAX))?;
            let allowed = limits.max_file_bytes.min(remaining);
            if metadata.len() > allowed {
                return Err(scope_input_oversized(
                    &candidate.file_name,
                    limits,
                    metadata.len(),
                ));
            }
            let (raw_hash, consumed) = if store_raw {
                match self.store.write_raw_reader(&mut file, allowed) {
                    Ok(result) => result,
                    Err(error) if error.error_code() == "KCS-E-STORE-OBJECT-OVERSIZED-001" => {
                        return Err(scope_input_oversized(
                            &candidate.file_name,
                            limits,
                            allowed.saturating_add(1),
                        ))
                    }
                    Err(error) => return Err(error),
                }
            } else {
                hash_scope_file(
                    &mut file,
                    &candidate.path,
                    &candidate.file_name,
                    allowed,
                    limits,
                )?
            };
            if file.metadata().kcs_io(&candidate.path)?.len() != consumed {
                return Err(scope_file_changed(&candidate.file_name));
            }
            consumed_scope_bytes = consumed_scope_bytes
                .checked_add(consumed)
                .ok_or_else(|| scope_input_oversized(&candidate.file_name, limits, u64::MAX))?;
            let mut tree_entry = TreeEntry::raw_file(candidate.file_name.clone(), raw_hash)?;
            if let Some(pending) = normalize_by_path.get(&candidate.file_name) {
                if pending.expected_raw_hash == tree_entry.raw_hash {
                    tree_entry.normalize = Some(pending.normalize.clone());
                } else {
                    eprintln!(
                        "warning: normalization metadata not attached because {} changed after normalization",
                        candidate.file_name
                    );
                }
            }
            tree_entry.validate()?;
            entries.push(tree_entry);
        }
        Ok(WorkingTree {
            tree: build_tree(entries)?,
        })
    }

    fn working_file_candidates(
        &self,
        excluded_paths: &BTreeSet<String>,
        explicitly_allowed_tier_a_paths: &BTreeSet<String>,
        enforce_tier_a: bool,
        limits: ArchiveLimits,
    ) -> Result<Vec<WorkingFileCandidate>> {
        let mut candidates = Vec::new();
        let mut declared_scope_bytes = 0_u64;
        for entry in fs::read_dir(&self.root).kcs_io(&self.root)? {
            let entry = entry.kcs_io(&self.root)?;
            if entry.file_name() == ".kcs" {
                continue;
            }
            let path = entry.path();
            let file_type = entry.file_type().kcs_io(&path)?;
            if file_type.is_dir() {
                continue;
            }
            if !file_type.is_file() {
                eprintln!("warning: skipping non-regular file: {}", path.display());
                continue;
            }
            let file_name = match entry.file_name().into_string() {
                Ok(name) => name,
                Err(_) => {
                    eprintln!("warning: skipping non-UTF-8 file name: {}", path.display());
                    continue;
                }
            };
            if excluded_paths.contains(&file_name) {
                continue;
            }
            if enforce_tier_a
                && is_tier_a_secret_name(&file_name)
                && !explicitly_allowed_tier_a_paths.contains(&file_name)
            {
                eprintln!("warning: skipping Tier-A secret file: {file_name}");
                continue;
            }
            if candidates.len() == MAX_TREE_ENTRIES {
                return Err(scope_tree_entries_oversized(
                    candidates.len().saturating_add(1),
                ));
            }
            let file = open_scope_file_nofollow(&path)?;
            let metadata = file.metadata().kcs_io(&path)?;
            if metadata.len() > limits.max_file_bytes {
                return Err(scope_input_oversized(&file_name, limits, metadata.len()));
            }
            declared_scope_bytes = declared_scope_bytes
                .checked_add(metadata.len())
                .ok_or_else(|| scope_input_oversized(&file_name, limits, u64::MAX))?;
            if declared_scope_bytes > limits.max_scope_bytes {
                return Err(scope_input_oversized(
                    &file_name,
                    limits,
                    declared_scope_bytes,
                ));
            }
            candidates.push(WorkingFileCandidate { path, file_name });
        }
        Ok(candidates)
    }

    pub fn status(&self) -> Result<StatusReport> {
        self.validate()?;
        let current = self.build_working_tree(false)?.tree;
        let current_map = tree_map(&current);
        // R15-4: a shallow HEAD (tree object discarded) must NOT brick a pure read.
        // Degrade to listing the current files without a classification instead of
        // propagating the raw KCS-E-STORE-NOT-FOUND-001 from `read_tree`.
        let (head_map, head_shallow) = match self.head_tree_state()? {
            HeadTreeState::Unborn => (BTreeMap::new(), false),
            HeadTreeState::Present(tree) => (tree_map(&tree), false),
            HeadTreeState::Shallow => (BTreeMap::new(), true),
        };

        let mut paths = BTreeSet::new();
        paths.extend(current_map.keys().cloned());
        paths.extend(head_map.keys().cloned());

        let mut statuses = Vec::new();
        for path in paths {
            // Omit the tree-derived classification when HEAD is shallow — the prior
            // tree needed to compute it is gone.
            let status = if head_shallow {
                if !current_map.contains_key(&path) {
                    continue;
                }
                None
            } else {
                Some(
                    match (head_map.get(&path), current_map.get(&path)) {
                        (None, Some(_)) => "new",
                        (Some(old), Some(new)) if old == new => "unchanged",
                        (Some(_), Some(_)) => "modified",
                        (Some(_), None) => "deleted",
                        (None, None) => continue,
                    }
                    .to_owned(),
                )
            };
            statuses.push(FileStatus {
                path: self.root.join(&path),
                relative_path: path.clone(),
                status,
                raw_hash: current_map
                    .get(&path)
                    .or_else(|| head_map.get(&path))
                    .cloned(),
            });
        }
        Ok(StatusReport {
            files: statuses,
            head_shallow,
        })
    }

    pub fn snapshot(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
    ) -> Result<SnapshotOutcome> {
        self.snapshot_filtered(message, fixed_now, &BTreeSet::new())
    }

    /// Manual snapshot that honors preview exclusions and reclassifies Tier-A
    /// names at the final read boundary. The policy-aware variant preserves an
    /// explicit local-only Tier-A unignore from the same preview.
    pub fn snapshot_filtered(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        excluded_paths: &BTreeSet<String>,
    ) -> Result<SnapshotOutcome> {
        self.snapshot_filtered_with_policy(message, fixed_now, excluded_paths, &BTreeSet::new())
    }

    pub fn snapshot_filtered_with_policy(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        excluded_paths: &BTreeSet<String>,
        explicitly_allowed_tier_a_paths: &BTreeSet<String>,
    ) -> Result<SnapshotOutcome> {
        self.snapshot_with_type(
            message,
            fixed_now,
            CommitType::Manual,
            excluded_paths,
            &BTreeMap::new(),
            explicitly_allowed_tier_a_paths,
        )
    }

    pub fn auto_snapshot(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        excluded_paths: &BTreeSet<String>,
    ) -> Result<SnapshotOutcome> {
        self.snapshot_with_type(
            message,
            fixed_now,
            CommitType::Auto,
            excluded_paths,
            &BTreeMap::new(),
            &BTreeSet::new(),
        )
    }

    pub fn auto_snapshot_with_normalize(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        excluded_paths: &BTreeSet<String>,
        normalize_by_path: &BTreeMap<String, NormalizeRef>,
    ) -> Result<SnapshotOutcome> {
        if !normalize_by_path.is_empty() {
            return Err(KcsError::invalid_usage(
                "normalization metadata must include its expected raw hash",
            ));
        }
        self.auto_snapshot_with_bound_normalize(
            message,
            fixed_now,
            excluded_paths,
            &BTreeMap::new(),
            &BTreeSet::new(),
        )
    }

    pub fn auto_snapshot_with_bound_normalize(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        excluded_paths: &BTreeSet<String>,
        normalize_by_path: &BTreeMap<String, PendingNormalizeRef>,
        explicitly_allowed_tier_a_paths: &BTreeSet<String>,
    ) -> Result<SnapshotOutcome> {
        self.snapshot_with_type(
            message,
            fixed_now,
            CommitType::Auto,
            excluded_paths,
            normalize_by_path,
            explicitly_allowed_tier_a_paths,
        )
    }

    fn snapshot_with_type(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        commit_type: CommitType,
        excluded_paths: &BTreeSet<String>,
        normalize_by_path: &BTreeMap<String, PendingNormalizeRef>,
        explicitly_allowed_tier_a_paths: &BTreeSet<String>,
    ) -> Result<SnapshotOutcome> {
        self.validate()?;
        let _lock = StoreLock::acquire(&self.kcs_dir)?;
        maybe_hold_lock_for_tests();

        let working = self
            .build_working_tree_with_bound_normalize_and_limits(
                true,
                excluded_paths,
                normalize_by_path,
                explicitly_allowed_tier_a_paths,
                ArchiveLimits::default(),
            )?
            .tree;
        let tree_value =
            serde_json::to_value(&working).map_err(|err| KcsError::schema(err.to_string()))?;
        let (tree_hash, _) = self.store.write_json(ObjectKind::Tree, &tree_value)?;
        let head_hash = self.head_commit_hash()?;
        // R16-1: a missing HEAD *commit* object is the same shallow-corruption class
        // as a missing tree (handled just below) — a write must fail loudly with
        // KCS-E-COMMIT-SHALLOW-001 and never advance refs onto an unverifiable base,
        // rather than surface a raw, opaque KCS-E-STORE-NOT-FOUND-001. Was an
        // unconditional `?` that only the tree case was guarded against.
        let head_tree_hash = match head_hash.as_deref() {
            None => None,
            Some(hash) => match self.read_commit(hash) {
                Ok(commit) => Some(commit.tree),
                Err(error) if is_store_not_found(&error) => {
                    return Err(KcsError::commit_shallow(
                        "HEAD commit object is missing (shallow: discarded / corrupt); \
                         restore the commit object or re-create the scope before snapshotting",
                        hash.to_owned(),
                    ));
                }
                Err(error) => return Err(error),
            },
        };
        // Snapshot the prior HEAD tree now — after the ref updates below,
        // head_tree_state() would return the NEW tree (useless as "previous").
        // R15-4: if HEAD names a commit whose tree object is gone (shallow: GC'd /
        // deleted / corrupt), fail loudly with KCS-E-COMMIT-SHALLOW-001 rather than a
        // raw KCS-E-STORE-NOT-FOUND-001, and never advance refs onto an unverifiable
        // base (05 §2.2: snapshot/index need the full prior tree).
        let prior_tree = match head_tree_hash.as_deref() {
            None => None,
            Some(hash) => match self.read_tree(hash) {
                Ok(tree) => Some(tree),
                Err(error) if is_store_not_found(&error) => {
                    return Err(KcsError::commit_shallow(
                        "HEAD commit is shallow (tree object discarded); \
                         restore the tree object or re-create the scope before snapshotting",
                        head_hash.clone().unwrap_or_default(),
                    ));
                }
                Err(error) => return Err(error),
            },
        };
        let stats = commit_stats(prior_tree.as_ref(), &working);

        if head_tree_hash.as_deref() == Some(tree_hash.as_str()) {
            return Ok(SnapshotOutcome {
                noop: true,
                message: "snapshot noop: tree unchanged".to_owned(),
                tree_hash,
                commit_hash: None,
                commit: None,
                stats,
            });
        }

        let created_at = fixed_now
            .map(str::to_owned)
            .or_else(fixed_now_override)
            .unwrap_or_else(now_utc_seconds);
        let message = message
            .map(str::to_owned)
            .unwrap_or_else(|| match commit_type {
                CommitType::Auto => format!("index auto snapshot at {created_at}"),
                _ => format!("snapshot at {created_at}"),
            });
        let parents = head_hash.into_iter().collect::<Vec<_>>();
        let commit = CommitObject::new(
            tree_hash.clone(),
            parents,
            created_at,
            message,
            self.tool_lock_hash()?,
            stats.clone(),
            commit_type,
        )?;
        let commit_value =
            serde_json::to_value(&commit).map_err(|err| KcsError::schema(err.to_string()))?;
        let (commit_hash, _) = self.store.write_json(ObjectKind::Commit, &commit_value)?;

        // Known limitation (WS1c S6, 2026-07-03): refs/heads/main and HEAD are
        // advanced by two separate atomic renames. Each rename is individually
        // crash-safe (temp file + rename, never a torn value), but a power loss
        // *between* them can leave refs/heads/main advanced while HEAD still
        // points at the parent. The commit object is already durable in the CAS,
        // so recovery is a matter of re-pointing HEAD; no data is lost. A single
        // atomic multi-ref transaction is deferred (single-user Step 1 scope).
        atomic_overwrite(
            &self.kcs_dir.join("refs/heads/main"),
            commit_hash.as_bytes(),
        )?;
        atomic_overwrite(&self.kcs_dir.join("HEAD"), commit_hash.as_bytes())?;
        self.write_manifest(&working, prior_tree.as_ref())?;

        Ok(SnapshotOutcome {
            noop: false,
            message: "snapshot created".to_owned(),
            tree_hash,
            commit_hash: Some(commit_hash),
            commit: Some(commit),
            stats,
        })
    }

    pub fn log(&self) -> Result<LogReport> {
        self.validate()?;
        let mut entries = Vec::new();
        let mut next = self.head_commit_hash()?;
        let mut truncated = false;
        while let Some(hash) = next {
            // R16-1: a missing ancestor commit object (shallow / external corruption)
            // truncates the history at that point instead of bricking the whole `log`
            // on a raw KCS-E-STORE-NOT-FOUND-001. The healthy prefix from HEAD is
            // returned with `truncated = true` so the loss is explicit — Sonnet-B's
            // repro (a missing root commit swallowing the healthy recent commits too)
            // is exactly what this prevents.
            let commit = match self.read_commit(&hash) {
                Ok(commit) => commit,
                Err(error) if is_store_not_found(&error) => {
                    truncated = true;
                    break;
                }
                Err(error) => return Err(error),
            };
            next = commit.parents.first().cloned();
            entries.push(LogEntry {
                commit_hash: hash,
                commit,
            });
        }
        Ok(LogReport { entries, truncated })
    }

    pub fn diff(&self, a: &str, b: &str) -> Result<Vec<DiffEntry>> {
        self.validate()?;
        let a_hash = self.resolve_commit(a)?;
        let b_hash = self.resolve_commit(b)?;
        // R16-5: if either side's commit or tree object is gone (shallow), a
        // full-file diff is impossible — surface a clear KCS-E-COMMIT-SHALLOW-001
        // that names WHICH side (a/b) is shallow, not a raw opaque
        // KCS-E-STORE-NOT-FOUND-001 whose hash the user cannot map to an operand
        // (docs/05 §3.4.1: "片方が shallow なら全ファイル差分は不能と明示").
        let a_tree = self.diff_side_tree("a", &a_hash)?;
        let b_tree = self.diff_side_tree("b", &b_hash)?;
        let a_map = tree_map(&a_tree);
        let b_map = tree_map(&b_tree);

        let mut paths = BTreeSet::new();
        paths.extend(a_map.keys().cloned());
        paths.extend(b_map.keys().cloned());

        let mut changes = Vec::new();
        for path in paths {
            let change = match (a_map.get(&path), b_map.get(&path)) {
                (None, Some(_)) => "added",
                (Some(_), None) => "deleted",
                (Some(old), Some(new)) if old != new => "modified",
                _ => continue,
            };
            changes.push(DiffEntry {
                path: self.root.join(&path),
                relative_path: path.clone(),
                change: change.to_owned(),
                old_raw_hash: a_map.get(&path).cloned(),
                new_raw_hash: b_map.get(&path).cloned(),
            });
        }
        Ok(changes)
    }

    /// R16-5: read one `diff` side's tree, folding a missing commit OR tree object
    /// (shallow: discarded / corrupt) into a KCS-E-COMMIT-SHALLOW-001 that names
    /// which side (`side` = "a"/"b") is shallow. The rationale for reusing
    /// COMMIT-SHALLOW rather than minting a diff-specific code: the recovery
    /// (restore the object or diff a non-shallow pair) and semantics are identical
    /// to every other shallow-commit site (R16-1). `resolve_commit` already ran, so
    /// a genuinely absent operand is a distinct not_found — only a resolved commit
    /// whose backing objects are gone reaches here.
    fn diff_side_tree(&self, side: &str, commit_hash: &str) -> Result<TreeObject> {
        let commit = match self.read_commit(commit_hash) {
            Ok(commit) => commit,
            Err(error) if is_store_not_found(&error) => {
                return Err(diff_side_shallow_error(side, commit_hash));
            }
            Err(error) => return Err(error),
        };
        match self.read_tree(&commit.tree) {
            Ok(tree) => Ok(tree),
            Err(error) if is_store_not_found(&error) => {
                Err(diff_side_shallow_error(side, commit_hash))
            }
            Err(error) => Err(error),
        }
    }

    pub fn inspect(&self, hash: &str) -> Result<InspectedObject> {
        self.validate()?;
        let object = self.store.inspect_by_hash(hash)?;
        match object.kind {
            ObjectKind::Tree => self.read_tree(hash).map(InspectedObject::Tree),
            ObjectKind::Commit => self.read_commit(hash).map(InspectedObject::Commit),
            ObjectKind::Raw => Ok(InspectedObject::Raw {
                raw_hash: object.hash,
                size_bytes: object.size_bytes,
            }),
        }
    }

    pub fn tag(&self, name: &str, commit: Option<&str>) -> Result<String> {
        self.validate()?;
        validate_ref_operand(name)?;
        // F4: `resolve_commit` resolves the literal `HEAD` and any `sha256:` hash
        // form BEFORE it ever consults `refs/tags` (see below), so a tag created
        // under such a name is written to disk but permanently shadowed — a dead
        // ref that `diff`/`log` can never reach. Reject it at creation rather than
        // returning a success that silently does nothing. (This check is specific
        // to tag *names*; `validate_ref_operand` stays shared with `resolve_commit`,
        // which must still accept `HEAD`/hash as commit operands.)
        if name == "HEAD" || is_hash(name) {
            return Err(KcsError::invalid_usage(
                "tag name must not be `HEAD` or a commit hash (it would be unreachable)",
            ));
        }
        let _lock = StoreLock::acquire(&self.kcs_dir)?;
        let commit_hash = match commit {
            Some(value) => self.resolve_commit(value)?,
            None => self
                .head_commit_hash()?
                .ok_or_else(|| KcsError::not_found("HEAD"))?,
        };
        // R17-5: with no explicit operand the implicit HEAD is resolved via
        // head_commit_hash() (which never reads the commit object), so this is the
        // first existence check. A shallow (missing / corrupt) HEAD commit folds into
        // KCS-E-COMMIT-SHALLOW-001 with tag-write context, matching every other
        // shallow-commit site (R16-1), not a raw, opaque KCS-E-STORE-NOT-FOUND-001.
        // (When `commit_hash` came from `resolve_commit`, existence was already
        // verified there, so this read only surfaces the implicit-HEAD case.)
        match self.read_commit(&commit_hash) {
            Ok(_) => {}
            Err(error) if is_store_not_found(&error) => {
                return Err(KcsError::commit_shallow(
                    "cannot create a tag on a shallow commit: the HEAD commit object is \
                     missing (discarded / corrupt); restore the commit object or tag a \
                     non-shallow commit",
                    commit_hash.clone(),
                ));
            }
            Err(error) => return Err(error),
        }
        let path = self.kcs_dir.join("refs/tags").join(name);
        if path.exists() {
            return Err(KcsError::new(
                "KCS-E-COMMIT-TAG-001",
                "tag already exists",
                json!({ "tag": name }),
                ExitCode::InvalidUsage,
            ));
        }
        atomic_write(&path, commit_hash.as_bytes())?;
        Ok(commit_hash)
    }

    pub fn resolve_commit(&self, value: &str) -> Result<String> {
        // N4 (03 §3 scope boundary): a commit-ref operand is only ever `HEAD`, a
        // hash, or a tag name — none legitimately carry a path separator or a
        // `.`/`..` component. Without this guard `refs/tags`.join(value) treats
        // `../../..` as a filesystem escape, turning `kcs diff`/`kcs tag <commit>`
        // into an out-of-scope file-existence oracle. Validate before any join.
        validate_ref_operand(value)?;
        if value == "HEAD" {
            return self
                .head_commit_hash()?
                .ok_or_else(|| KcsError::not_found("HEAD"));
        }
        if is_hash(value) {
            // R17-5: `resolve_commit` runs before `diff_side_tree`'s R16-5 shallow
            // absorption (and before `tag`'s own verification read), so a hash-literal
            // shallow commit (commit object discarded / corrupt) must fold into
            // KCS-E-COMMIT-SHALLOW-001 HERE — otherwise it escapes as a raw, opaque
            // KCS-E-STORE-NOT-FOUND-001 while the `HEAD` operand (which skips
            // read_commit) correctly reaches COMMIT-SHALLOW. Matches the other 8
            // read_commit sites hardened in R16-1.
            match self.read_commit(value) {
                Ok(_) => {}
                Err(error) if is_store_not_found(&error) => {
                    return Err(resolve_commit_shallow_error(value));
                }
                Err(error) => return Err(error),
            }
            return Ok(value.to_owned());
        }
        let tag = self.kcs_dir.join("refs/tags").join(value);
        if tag.is_file() {
            let hash = fs::read_to_string(&tag).kcs_io(&tag)?;
            let hash = hash.trim().to_owned();
            // R17-5: a tag whose target commit object is shallow (discarded / corrupt)
            // folds into COMMIT-SHALLOW too, for the same reason as the hash-literal
            // branch above.
            match self.read_commit(&hash) {
                Ok(_) => {}
                Err(error) if is_store_not_found(&error) => {
                    return Err(resolve_commit_shallow_error(&hash));
                }
                Err(error) => return Err(error),
            }
            return Ok(hash);
        }
        Err(KcsError::not_found(value))
    }

    pub fn read_commit(&self, hash: &str) -> Result<CommitObject> {
        let object = self.store.read_by_hash(hash)?;
        if object.kind != ObjectKind::Commit {
            return Err(KcsError::schema("hash does not identify a commit"));
        }
        let commit: CommitObject = serde_json::from_slice(&object.bytes)
            .map_err(|err| KcsError::schema(err.to_string()))?;
        if commit.parents.len() > MAX_COMMIT_PARENTS {
            return Err(KcsError::schema(format!(
                "commit parents exceed the limit of {MAX_COMMIT_PARENTS}"
            )));
        }
        commit.validate()?;
        Ok(commit)
    }

    pub fn read_tree(&self, hash: &str) -> Result<TreeObject> {
        let object = self.store.read_by_hash(hash)?;
        if object.kind != ObjectKind::Tree {
            return Err(KcsError::schema("hash does not identify a tree"));
        }
        let tree: TreeObject = serde_json::from_slice(&object.bytes)
            .map_err(|err| KcsError::schema(err.to_string()))?;
        if tree.entries.len() > MAX_TREE_ENTRIES {
            return Err(KcsError::schema(format!(
                "tree entries exceed the limit of {MAX_TREE_ENTRIES}"
            )));
        }
        tree.validate()?;
        Ok(tree)
    }

    pub fn head_commit_hash(&self) -> Result<Option<String>> {
        let path = self.kcs_dir.join("HEAD");
        let value = fs::read_to_string(&path).kcs_io(&path)?;
        let value = value.trim();
        if value.is_empty() {
            // R15-1 / R15-1b: an empty HEAD is EITHER a corrupt HEAD (a crash
            // truncated it while `refs/heads/main` still names a real commit) OR a
            // genuinely unborn branch (both HEAD and refs empty). Recover the commit
            // from refs in the corrupt case so a `snapshot` extends the real history
            // instead of orphaning it under a fresh `parents=[]` root (R15-1), and so
            // a pure read (`log`/`status`/`search`) does not misreport an indexed
            // scope as unindexed (R15-1b). `empty_head_recovery_hash` is side-effect-
            // free — it only reads and validates the ref against the store — so it is
            // safe to call while holding the store lock (e.g. inside `snapshot`) and
            // on a read-only `.kcs`. A genuinely unborn branch still returns `None`
            // (refs empty too), preserving the first-`snapshot`-creates-root path.
            empty_head_recovery_hash(&self.kcs_dir)
        } else if is_hash(value) {
            Ok(Some(value.to_owned()))
        } else {
            Err(KcsError::schema("HEAD must contain a commit_hash"))
        }
    }

    /// R13-4 / R13-5: restore an empty or missing `HEAD` from a healthy
    /// `refs/heads/main`, recording the repair to `events.jsonl` (never silent).
    /// HEAD is the durable truth and refs is derived, so the *only* time this
    /// fires is the corruption asymmetry Opus found: `head_commit_hash` returns
    /// `None` for an empty HEAD, which `snapshot` reads as "unborn" and then
    /// orphans all history under a fresh `parents=[]` root commit. When refs still
    /// names a real commit, HEAD is corrupt (not unborn) and is repaired from it.
    /// Idempotent no-op when HEAD is populated or the branch is genuinely unborn
    /// (HEAD and refs both empty). Returns the restored commit hash on a repair.
    pub fn self_heal_head(&self) -> Result<Option<String>> {
        // Fast path (no lock, no side effect): nothing to repair. Reads succeed on a
        // read-only `.kcs`, so a healthy scope is completely unaffected below.
        if empty_head_recovery_hash(&self.kcs_dir)?.is_none() {
            return Ok(None);
        }
        // R14-3: the repair below is a best-effort *write* on the common `open()`
        // entrypoint. A read-only `.kcs` (archive / forensic mount) cannot take the
        // store lock or overwrite HEAD; before R14-3 those permission errors propagated
        // out of `open()` (the `?`) and bricked even pure-read commands
        // (status/log/search/inspect) on a scope with a corrupt (empty) HEAD — an R13-4
        // regression. Follow the R12-5/R13-3 rule that observation/repair writes are
        // non-fatal: if we cannot take the lock (read-only permission, or a live
        // concurrent holder), defer the heal (warn + `Ok(None)`) so reads still run; a
        // later *writable* open completes it. R13-4's guarantee is preserved because a
        // writable scope still heals here — before any `snapshot` advances HEAD — so no
        // snapshot can orphan history under a fresh `parents=[]` root.
        let Ok(_lock) = StoreLock::acquire(&self.kcs_dir) else {
            let _ = append_warn_log(
                "KCS-W-STORE-HEAD-HEAL-DEFERRED-001",
                "corrupt HEAD detected but the store lock is unavailable (read-only scope or a \
                 concurrent holder); deferring self-heal so read-only commands still run",
                json!({ "kcs_dir": self.kcs_dir.display().to_string() }),
            );
            return Ok(None);
        };
        // Re-check under the lock in case another process healed it first.
        let Some(hash) = empty_head_recovery_hash(&self.kcs_dir)? else {
            return Ok(None);
        };
        // R14-3: a read-only scope can hold the lock (it existed before the mount went
        // read-only, or the `.lock` create raced) yet still reject the HEAD overwrite.
        // Treat a write failure the same way — defer, do not brick reads.
        if atomic_overwrite(&self.kcs_dir.join("HEAD"), hash.as_bytes()).is_err() {
            let _ = append_warn_log(
                "KCS-W-STORE-HEAD-HEAL-DEFERRED-001",
                "corrupt HEAD detected but HEAD is not writable (read-only scope); deferring \
                 self-heal so read-only commands still run",
                json!({ "kcs_dir": self.kcs_dir.display().to_string() }),
            );
            return Ok(None);
        }
        // A successful repair is never silent (R13-4): record it to events.jsonl. The
        // record is itself best-effort — a logging failure must not undo a completed
        // HEAD repair.
        let _ = append_event_log(
            "KCS-I-STORE-HEAD-REPAIRED-001",
            "restored empty/missing HEAD from refs/heads/main (corrupt HEAD, not unborn)",
            json!({ "commit_hash": hash }),
        );
        Ok(Some(hash))
    }

    /// R15-4: read the HEAD commit's tree object, distinguishing an unborn branch
    /// (no HEAD) from a shallow HEAD (tree object gone) from a present tree. A raw
    /// `KCS-E-STORE-NOT-FOUND-001` from the tree read is folded into the `Shallow`
    /// variant so callers decide the policy: pure reads degrade, writes fail loudly.
    fn head_tree_state(&self) -> Result<HeadTreeState> {
        let Some(commit_hash) = self.head_commit_hash()? else {
            return Ok(HeadTreeState::Unborn);
        };
        // R16-1: fold a missing *commit* object into `Shallow` too (was an
        // unconditional `?` that bricked pure reads on a raw KCS-E-STORE-NOT-FOUND-001
        // when the commit — not just its tree — was gone). Same corruption class, same
        // degrade-vs-fail-loudly policy the tree case already had.
        let tree_hash = match self.read_commit(&commit_hash) {
            Ok(commit) => commit.tree,
            Err(error) if is_store_not_found(&error) => return Ok(HeadTreeState::Shallow),
            Err(error) => return Err(error),
        };
        match self.read_tree(&tree_hash) {
            Ok(tree) => Ok(HeadTreeState::Present(tree)),
            Err(error) if is_store_not_found(&error) => Ok(HeadTreeState::Shallow),
            Err(error) => Err(error),
        }
    }

    fn validate_config(&self) -> Result<()> {
        let path = self.kcs_dir.join("config.toml");
        let value = fs::read_to_string(&path).kcs_io(&path)?;
        let toml: toml::Value =
            toml::from_str(&value).map_err(|err| KcsError::schema(err.to_string()))?;
        let json_value =
            serde_json::to_value(&toml).map_err(|err| KcsError::schema(err.to_string()))?;
        validate_json_schema(SchemaKind::Config, &json_value)?;
        // R12-2 / R12-1: reject documented-but-unwired values the schema can only
        // type-check (e.g. `allowed_scope != "."`) LOUDLY, so a scope config never
        // silently ignores a policy the user set.
        enforce_config_semantics(&json_value)?;
        let version = match json_value.get("kcs_format_version") {
            Some(value) => value
                .as_str()
                .ok_or_else(|| KcsError::schema("kcs_format_version must be a string"))?,
            None => FORMAT_VERSION,
        };
        validate_format_version(version)
    }

    fn validate_scope(&self) -> Result<()> {
        self.validated_scope_id().map(|_| ())
    }

    fn validated_scope_id(&self) -> Result<String> {
        let path = self.kcs_dir.join("scope.json");
        let value: Value = serde_json::from_str(&fs::read_to_string(&path).kcs_io(&path)?)
            .map_err(|err| KcsError::schema(err.to_string()))?;
        validate_json_schema(SchemaKind::Scope, &value)?;
        let Some(scope_id) = value.get("scope_id").and_then(Value::as_str) else {
            return Err(KcsError::schema("scope.json missing scope_id"));
        };
        if scope_id.is_empty() {
            return Err(KcsError::schema("scope_id is empty"));
        }
        if !is_ulid(scope_id) {
            return Err(KcsError::schema("scope_id must be a ULID"));
        }
        if let Some(version) = value.get("kcs_format_version") {
            let version = version
                .as_str()
                .ok_or_else(|| KcsError::schema("kcs_format_version must be a string"))?;
            validate_format_version(version)?;
        }
        Ok(scope_id.to_owned())
    }

    fn validate_manifest(&self) -> Result<()> {
        let path = self.kcs_dir.join("manifest.json");
        let value: Value = serde_json::from_str(&fs::read_to_string(&path).kcs_io(&path)?)
            .map_err(|err| KcsError::schema(err.to_string()))?;
        validate_json_schema(SchemaKind::Manifest, &value)?;
        if !value.is_object() {
            return Err(KcsError::schema("manifest.json must be an object"));
        }
        let Some(files) = value.get("files") else {
            return Err(KcsError::schema("manifest.json missing files"));
        };
        let files = files
            .as_array()
            .ok_or_else(|| KcsError::schema("manifest.files must be an array"))?;
        for file in files {
            let object = file
                .as_object()
                .ok_or_else(|| KcsError::schema("manifest file entry must be an object"))?;
            let path = object
                .get("path")
                .and_then(Value::as_str)
                .ok_or_else(|| KcsError::schema("manifest file entry missing path"))?;
            if path.is_empty() || path.contains('/') {
                return Err(KcsError::path(
                    "manifest file path must be a direct child file name",
                    path.to_owned(),
                ));
            }
            let raw_hash = object
                .get("raw_hash")
                .and_then(Value::as_str)
                .ok_or_else(|| KcsError::schema("manifest file entry missing raw_hash"))?;
            if !is_hash(raw_hash) {
                return Err(KcsError::schema("manifest raw_hash must be a hash"));
            }
            let status = object
                .get("status")
                .and_then(Value::as_str)
                .ok_or_else(|| KcsError::schema("manifest file entry missing status"))?;
            if !matches!(status, "new" | "modified" | "deleted" | "unchanged") {
                return Err(KcsError::schema("manifest status has invalid value"));
            }
        }
        Ok(())
    }

    /// Merge the current working tree into `manifest.json`, preserving rows for
    /// paths that vanished (`03 §8`: never DELETE a files row; set
    /// `status="deleted"` and keep the last observed `raw_hash`). A path that
    /// reappears recovers from `deleted` to `modified`/`unchanged`
    /// (ws1a CT-STATE-003/004).
    ///
    /// The previous state is sourced from the prior HEAD tree (the durable
    /// truth, `03 §2`) merged with the prior manifest's `deleted` rows (older
    /// deletions that no tree carries). The manifest's live rows are never
    /// trusted: a stale or hand-edited manifest cannot lose a deletion this way
    /// (WS1d cross-review ruling).
    fn write_manifest(&self, tree: &TreeObject, prior_tree: Option<&TreeObject>) -> Result<()> {
        let mut previous: BTreeMap<String, String> = prior_tree
            .map(|prior| {
                prior
                    .entries
                    .iter()
                    .map(|entry| (entry.path.clone(), entry.raw_hash.clone()))
                    .collect()
            })
            .unwrap_or_default();
        for (path, raw_hash) in self.read_manifest_deleted_hashes()? {
            previous.entry(path).or_insert(raw_hash);
        }
        let current: BTreeMap<&str, &str> = tree
            .entries
            .iter()
            .map(|entry| (entry.path.as_str(), entry.raw_hash.as_str()))
            .collect();

        // BTreeMap keyed by path gives a deterministic, path-sorted file list.
        let mut rows: BTreeMap<String, Value> = BTreeMap::new();

        for entry in &tree.entries {
            let status = match previous.get(&entry.path) {
                None => "new",
                Some(prev) if *prev != entry.raw_hash => "modified",
                Some(_) => "unchanged",
            };
            rows.insert(
                entry.path.clone(),
                json!({ "path": entry.path, "raw_hash": entry.raw_hash, "status": status }),
            );
        }

        // Retain vanished paths as deleted rows carrying their last raw_hash.
        for (path, raw_hash) in &previous {
            if !current.contains_key(path.as_str()) {
                rows.insert(
                    path.clone(),
                    json!({ "path": path, "raw_hash": raw_hash, "status": "deleted" }),
                );
            }
        }

        let files = rows.into_values().collect::<Vec<_>>();
        let value = json!({
            "schema_version": 1,
            "files": files,
            "updated_at": now_utc_seconds(),
        });
        let bytes =
            serde_json::to_vec_pretty(&value).map_err(|err| KcsError::schema(err.to_string()))?;
        atomic_overwrite(&self.kcs_dir.join("manifest.json"), &bytes)
    }

    /// Read the current `manifest.json` `deleted` rows as a
    /// `path -> last raw_hash` map. Live rows are intentionally excluded — the
    /// prior HEAD tree is the authoritative source for those (see
    /// `write_manifest`).
    /// Returns an empty map when the manifest is absent. The manifest is schema
    /// validated before `snapshot` runs, so entries are well formed here.
    fn read_manifest_deleted_hashes(&self) -> Result<BTreeMap<String, String>> {
        let path = self.kcs_dir.join("manifest.json");
        let mut map = BTreeMap::new();
        if !path.is_file() {
            return Ok(map);
        }
        let value: Value = serde_json::from_str(&fs::read_to_string(&path).kcs_io(&path)?)
            .map_err(|err| KcsError::schema(err.to_string()))?;
        if let Some(files) = value.get("files").and_then(Value::as_array) {
            for file in files {
                if file.get("status").and_then(Value::as_str) != Some("deleted") {
                    continue;
                }
                if let (Some(entry_path), Some(raw_hash)) = (
                    file.get("path").and_then(Value::as_str),
                    file.get("raw_hash").and_then(Value::as_str),
                ) {
                    map.insert(entry_path.to_owned(), raw_hash.to_owned());
                }
            }
        }
        Ok(map)
    }

    fn tool_lock_hash(&self) -> Result<String> {
        let path = self.kcs_dir.join("tool-lock.json");
        if path.is_file() {
            let value: Value = serde_json::from_str(&fs::read_to_string(&path).kcs_io(&path)?)
                .map_err(|err| KcsError::schema(err.to_string()))?;
            hash_json(&canonical_tool_lock_value(&value)?)
        } else {
            hash_json(&json!({ "spec_version": 1 }))
        }
    }
}

fn canonical_tool_lock_value(value: &Value) -> Result<Value> {
    let object = value
        .as_object()
        .ok_or_else(|| KcsError::schema("tool-lock.json must be an object"))?;
    let spec_version = object
        .get("spec_version")
        .and_then(Value::as_u64)
        .ok_or_else(|| KcsError::schema("tool-lock.json missing spec_version"))?;
    if spec_version != 1 {
        return Err(KcsError::schema(format!(
            "unsupported tool-lock spec_version: {spec_version}"
        )));
    }
    let mut canonical = Map::new();
    canonical.insert("spec_version".to_owned(), Value::from(spec_version));
    for key in ["prepare", "markdown", "summary", "classification", "rerank"] {
        if let Some(entry) = canonical_tool_entry(object, key, false)? {
            canonical.insert(key.to_owned(), entry);
        }
    }
    if let Some(entry) = canonical_tool_entry(object, "embedding", true)? {
        canonical.insert("embedding".to_owned(), entry);
    }
    Ok(Value::Object(canonical))
}

fn canonical_tool_entry(
    object: &Map<String, Value>,
    key: &str,
    embedding: bool,
) -> Result<Option<Value>> {
    let Some(entry) = object.get(key) else {
        return Ok(None);
    };
    if entry.is_null() {
        return Ok(None);
    }
    let entry = entry
        .as_object()
        .ok_or_else(|| KcsError::schema(format!("{key} must be an object")))?;
    let mut canonical = Map::new();
    if embedding {
        canonical.insert(
            "dimensions".to_owned(),
            required_lock_integer(entry, key, "dimensions")?,
        );
        canonical.insert(
            "distance".to_owned(),
            required_lock_string(entry, key, "distance")?,
        );
        canonical.insert(
            "modality".to_owned(),
            required_lock_string(entry, key, "modality")?,
        );
    }
    canonical.insert(
        "profile_hash".to_owned(),
        required_lock_string(entry, key, "profile_hash")?,
    );
    canonical.insert(
        "tool_id".to_owned(),
        required_lock_string(entry, key, "tool_id")?,
    );
    Ok(Some(Value::Object(canonical)))
}

fn required_lock_string(object: &Map<String, Value>, key: &str, field: &str) -> Result<Value> {
    object
        .get(field)
        .and_then(Value::as_str)
        .map(|value| Value::String(value.to_owned()))
        .ok_or_else(|| KcsError::schema(format!("{key}.{field} must be a string")))
}

fn required_lock_integer(object: &Map<String, Value>, key: &str, field: &str) -> Result<Value> {
    object
        .get(field)
        .and_then(Value::as_u64)
        .map(Value::from)
        .ok_or_else(|| KcsError::schema(format!("{key}.{field} must be an integer")))
}

/// R13-4: the commit hash an empty/missing `HEAD` should be restored to, or
/// `None` when there is nothing to repair. Returns `Some(hash)` only when HEAD is
/// empty/missing AND `refs/heads/main` names a commit object that actually exists
/// in the store — never adopts a dangling ref (that would move corruption into
/// HEAD instead of fixing it). Both HEAD and refs empty = a legitimately unborn
/// branch (fresh `init`), which stays `None` so a first `snapshot` still creates
/// the root commit. Shared by `Repository::self_heal_head` (the repair) and the
/// CLI re-`init` path (R13-5 damage detection before the repair runs).
pub fn empty_head_recovery_hash(kcs_dir: &Path) -> Result<Option<String>> {
    let head_path = kcs_dir.join("HEAD");
    let head_present_nonempty = match fs::read_to_string(&head_path) {
        Ok(value) => !value.trim().is_empty(),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => false,
        Err(err) => {
            return Err(KcsError::io(
                err.to_string(),
                head_path.display().to_string(),
            ))
        }
    };
    if head_present_nonempty {
        return Ok(None);
    }
    let refs_path = kcs_dir.join("refs/heads/main");
    let refs_value = match fs::read_to_string(&refs_path) {
        Ok(value) => value.trim().to_owned(),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(err) => {
            return Err(KcsError::io(
                err.to_string(),
                refs_path.display().to_string(),
            ))
        }
    };
    if refs_value.is_empty() || !is_hash(&refs_value) {
        return Ok(None);
    }
    // Only restore from a ref that resolves to a real commit object.
    let store = ObjectStore::new(kcs_dir.to_path_buf());
    match store.read_by_hash(&refs_value) {
        Ok(object) if object.kind == ObjectKind::Commit => Ok(Some(refs_value)),
        _ => Ok(None),
    }
}

/// R13-3: default log retention when `[logs] retention_days` is unset (docs/06
/// §13 / docs/10 §12.6: "保持 30 日 (config 上書き可)").
pub const DEFAULT_LOG_RETENTION_DAYS: u32 = 30;

/// R13-3: read `[logs] retention_days` (integer ≥ 1) from a `config.toml`.
/// `None` when the file/key is absent or malformed, so the caller applies the
/// 30-day default. The key is schema-validated (`config.schema.json`) at startup,
/// so a bad value would already have been rejected; this read is defensive.
#[must_use]
pub fn read_logs_retention_days(config_toml_path: &Path) -> Option<u32> {
    let text = fs::read_to_string(config_toml_path).ok()?;
    let value: toml::Value = toml::from_str(&text).ok()?;
    value
        .get("logs")
        .and_then(|logs| logs.get("retention_days"))
        .and_then(toml::Value::as_integer)
        .and_then(|days| u32::try_from(days).ok())
        .filter(|days| *days >= 1)
}

/// R13-3: append `value` to the fixed-name JSONL at `path`, first performing a
/// best-effort daily rotation + retention prune (docs/06 §13 / docs/10 §12.6:
/// "日次ローテーション、保持 30 日 (config 上書き可)"). logrotate style: when the
/// live file's last-written day differs from today it is renamed to
/// `<stem>-YYYY-MM-DD.jsonl` and a fresh fixed-name file starts, so the documented
/// fixed names (events.jsonl / errors.jsonl / metrics.jsonl / access.jsonl) stay
/// current. Dated files older than `retention_days` are pruned. Rotation/prune
/// failures are non-fatal (R12-5 / R13-3 ruling): only the final append can fail
/// the caller, so a read-only log dir never kills the command it belongs to. A
/// concurrent process's `O_APPEND` handle on the renamed inode loses no lines —
/// rename is atomic and its bytes land in the dated file.
pub fn append_jsonl_rotating(path: &Path, value: &Value, retention_days: u32) -> Result<()> {
    let today = today_utc_date();
    // R22-8: `rotate_stale_log` is a check-then-rename (`!dated.exists()` then `fs::rename`),
    // which two processes crossing the first append after midnight can both enter. P1 renames
    // yesterday's live file to the dated name and appends a line to the fresh live file; P2
    // then renames THAT file over the same dated name, and since `rename(2)` replaces its
    // destination, yesterday's entire history is unlinked. Hold a per-log lock across the
    // `exists()` check and the rename so they are one critical section. Only taken on the day
    // a rotation is actually due — every other append stays lock-free. `acquire_path` never
    // blocks (a contended lock is an immediate `Err`), so the loser simply skips this
    // rotation and the next append performs it; the lock is best-effort like the rotation
    // itself (R12-5/R13-3: a read-only log dir must never kill the command), and only the
    // final append can fail the caller.
    if rotation_due(path, &today) {
        if let Ok(_rotate_lock) = StoreLock::acquire_path(rotate_lock_path(path)) {
            let _ = rotate_stale_log(path, &today);
        }
    }
    let _ = prune_rotated_logs(path, &today, retention_days);
    append_jsonl(path, value)
}

/// Cheap pre-check for [`append_jsonl_rotating`]: is the live log's last-written day older
/// than today? `rotate_stale_log` re-checks this under the lock, so this is only a hint that
/// keeps the common (same-day) append off the lock path.
fn rotation_due(path: &Path, today: &str) -> bool {
    let Ok(metadata) = fs::metadata(path) else {
        return false;
    };
    let Ok(modified) = metadata.modified() else {
        return false;
    };
    let file_date = date_of_system_time(modified);
    !file_date.is_empty() && file_date.as_str() < today
}

/// Per-log rotation lock, e.g. `.../logs/events.jsonl` → `.../logs/events.rotate.lock`.
fn rotate_lock_path(path: &Path) -> PathBuf {
    let stem = path
        .file_stem()
        .map(|stem| stem.to_string_lossy().into_owned())
        .unwrap_or_else(|| "log".to_owned());
    path.with_file_name(format!("{stem}.rotate.lock"))
}

fn today_utc_date() -> String {
    now_utc_seconds().get(..10).unwrap_or_default().to_owned()
}

fn rotate_stale_log(path: &Path, today: &str) -> Result<()> {
    let Ok(metadata) = fs::metadata(path) else {
        // No live file yet → nothing to rotate.
        return Ok(());
    };
    let modified = metadata.modified().kcs_io(path)?;
    let file_date = date_of_system_time(modified);
    // Same day (or a backwards clock) → keep appending to the live file.
    if file_date.is_empty() || file_date.as_str() >= today {
        return Ok(());
    }
    let dated = dated_log_path(path, &file_date);
    // Never clobber an already-rotated dated file (rename is skipped, the live
    // file keeps growing until the next distinct day — harmless).
    if !dated.exists() {
        fs::rename(path, &dated).kcs_io(&dated)?;
    }
    Ok(())
}

fn prune_rotated_logs(path: &Path, today: &str, retention_days: u32) -> Result<()> {
    let (Some(stem), Some(ext), Some(parent)) = (
        path.file_stem().and_then(|s| s.to_str()),
        path.extension().and_then(|s| s.to_str()),
        path.parent(),
    ) else {
        return Ok(());
    };
    let Some(today_days) = date_to_days(today) else {
        return Ok(());
    };
    let prefix = format!("{stem}-");
    let suffix = format!(".{ext}");
    for entry in fs::read_dir(parent).kcs_io(parent)? {
        let entry = entry.kcs_io(parent)?;
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        let Some(date) = name
            .strip_prefix(&prefix)
            .and_then(|rest| rest.strip_suffix(&suffix))
        else {
            continue;
        };
        let Some(file_days) = date_to_days(date) else {
            continue;
        };
        if today_days - file_days > i64::from(retention_days) {
            let _ = fs::remove_file(entry.path());
        }
    }
    Ok(())
}

/// `events.jsonl` + `2026-07-05` → `events-2026-07-05.jsonl`.
fn dated_log_path(path: &Path, date: &str) -> PathBuf {
    let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("log");
    let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("jsonl");
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    parent.join(format!("{stem}-{date}.{ext}"))
}

fn date_of_system_time(time: SystemTime) -> String {
    let secs = time
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or_default();
    format_unix_seconds(secs)
        .get(..10)
        .unwrap_or_default()
        .to_owned()
}

/// Parse a `YYYY-MM-DD` date into days since the Unix epoch, or `None` when the
/// shape is malformed. Reuses the civil-date algorithm the timestamp formatter uses.
fn date_to_days(date: &str) -> Option<i64> {
    let bytes = date.as_bytes();
    if bytes.len() != 10 || bytes[4] != b'-' || bytes[7] != b'-' {
        return None;
    }
    let year = date.get(0..4)?.parse::<i64>().ok()?;
    let month = date.get(5..7)?.parse::<i64>().ok()?;
    let day = date.get(8..10)?.parse::<i64>().ok()?;
    if !(1..=12).contains(&month) || !(1..=31).contains(&day) {
        return None;
    }
    Some(days_from_civil(year, month, day))
}

pub fn append_event_log(code: &str, message: &str, context: Value) -> Result<()> {
    append_observation("events.jsonl", "info", code, message, context)
}

pub fn append_error_log(error: &KcsError) -> Result<()> {
    append_observation(
        "errors.jsonl",
        "error",
        error.error_code(),
        error.message(),
        error.context().clone(),
    )
}

/// Record a `level=warn` observation to `errors.jsonl` (P3, CT2-ADAPTER-010).
/// Non-fatal: callers use it for warnings that must be observable but must not
/// stop startup (e.g. a world-readable plaintext `plain:` API key in tools.toml).
pub fn append_warn_log(code: &str, message: &str, context: Value) -> Result<()> {
    append_observation("errors.jsonl", "warn", code, message, context)
}

fn append_observation(
    file_name: &str,
    level: &str,
    code: &str,
    message: &str,
    mut context: Value,
) -> Result<()> {
    // R13-6: never write the device-global log under a CWD-relative path. When
    // neither an absolute `XDG_DATA_HOME` nor an absolute `HOME` resolves,
    // `data_home()` degrades to `"."`; the CLI's startup guard rejects such an
    // invocation, but its OWN error would still be logged here first and scatter
    // `./kcs/logs/errors.jsonl` under the working directory. Skip silently (logging
    // is best-effort) rather than create it.
    let log_dir = data_home().join("kcs/logs");
    if !log_dir.is_absolute() {
        return Ok(());
    }
    // N3: honor `redact_logs` (06 §8 / 10 §12.6, default true) before writing. The
    // KcsError context routinely carries a `path` (and search/adapter contexts a
    // `query`/`prompt`); writing them verbatim both violates the redaction policy
    // and defeats purge, whose scrubber assumes "path is never recorded". Mask the
    // sensitive keys recursively so nested contexts (e.g. an index partial-failure
    // `output`) are covered too.
    let redact = redact_logs_enabled();
    if redact {
        redact_context(&mut context);
    }
    // P4: several error Displays embed an absolute path in their *message*
    // (`io error at {path}`, `corrupt store file at {path}`), which N3's
    // context-only masking missed — the path then landed verbatim in
    // errors.jsonl, breaking the "path is never recorded" premise (10 §12.6) and,
    // combined with a group-readable errors.jsonl, leaking scope paths to other
    // local users. Mask absolute-path tokens in the message too under redact_logs.
    let message: Value = if redact {
        Value::String(redact_message_paths(message))
    } else {
        Value::String(message.to_owned())
    };
    let path = log_dir.join(file_name);
    // R13-3: the device-global logs (events/errors/metrics) are governed by the
    // device-level `[logs] retention_days` (default 30). Rotation/prune is
    // best-effort inside `append_jsonl_rotating`.
    let retention = read_logs_retention_days(&config_home().join("kcs/config.toml"))
        .unwrap_or(DEFAULT_LOG_RETENTION_DAYS);
    append_jsonl_rotating(
        &path,
        &json!({
            "ts": now_utc_seconds(),
            "level": level,
            "code": code,
            "component": "kcs-cli",
            "message": message,
            "context": context,
        }),
        retention,
    )
}

/// Replace every absolute-path-looking token (a whitespace-delimited run that
/// starts with `/`) in a log message with `[redacted]` (P4). Whitespace is
/// preserved exactly. This is deliberately conservative: relative tokens are
/// left alone; the leak sources all emit absolute paths via `path.display()`.
fn redact_message_paths(message: &str) -> String {
    let mut out = String::with_capacity(message.len());
    let mut token = String::new();
    for ch in message.chars() {
        if ch.is_whitespace() {
            push_redacted_token(&token, &mut out);
            token.clear();
            out.push(ch);
        } else {
            token.push(ch);
        }
    }
    push_redacted_token(&token, &mut out);
    out
}

fn push_redacted_token(token: &str, out: &mut String) {
    if token.starts_with('/') && token.len() > 1 {
        out.push_str("[redacted]");
    } else {
        out.push_str(token);
    }
}

/// Whether `redact_logs` is in effect (06 §8 default true). Read from the user
/// config's `[adapter.policy]`; the observation logs are device-global so the
/// device-level config governs them. Absent config / key -> the secure default.
fn redact_logs_enabled() -> bool {
    let path = config_home().join("kcs/config.toml");
    let Ok(text) = fs::read_to_string(&path) else {
        return true;
    };
    let Ok(value) = toml::from_str::<toml::Value>(&text) else {
        return true;
    };
    value
        .get("adapter")
        .and_then(|adapter| adapter.get("policy"))
        .and_then(|policy| policy.get("redact_logs"))
        .and_then(toml::Value::as_bool)
        .unwrap_or(true)
}

/// Recursively replace the values of sensitive keys with `[redacted]` anywhere
/// they appear in a log `context` object/array (N3). The allowlist covers the
/// path-carrying keys other error contexts use: `scope_path`
/// (`purge_not_found_error`), `candidates` (`scope_ambiguous_error`, an array of
/// absolute paths), and `root_path`/`kcs_path` (registry/scope contexts) — P4.
fn redact_context(value: &mut Value) {
    match value {
        Value::Object(map) => {
            for (key, entry) in map.iter_mut() {
                if matches!(
                    key.as_str(),
                    "path"
                        | "query"
                        | "prompt"
                        | "scope_path"
                        | "candidates"
                        | "root_path"
                        | "kcs_path"
                ) {
                    *entry = Value::String("[redacted]".to_owned());
                } else {
                    redact_context(entry);
                }
            }
        }
        Value::Array(items) => {
            for item in items.iter_mut() {
                redact_context(item);
            }
        }
        _ => {}
    }
}

fn config_home() -> PathBuf {
    // R12-6 / R13-6: empty/relative `XDG_CONFIG_HOME` AND empty/relative `HOME` are
    // both invalid — fall back to `$HOME/.config` only for an absolute `HOME`,
    // never to a CWD-relative dir. The CLI startup guard rejects the no-absolute-
    // base case loudly before we reach the `"."` last resort.
    crate::xdg::xdg_dir("XDG_CONFIG_HOME")
        .or_else(|| crate::xdg::home_dir().map(|home| home.join(".config")))
        .unwrap_or_else(|| PathBuf::from("."))
}

/// R12-2 / R12-1: enforce the *semantics* of documented config keys that the JSON
/// Schema can only type-check. A key whose value selects behavior KCS has not
/// implemented is rejected LOUDLY (`KCS-E-CONFIG-NOT-IMPLEMENTED-001`, exit 1 —
/// R9-6 convention) rather than silently ignored, but the documented DEFAULT value
/// is always accepted as a harmless no-op so pasting the docs/07 §7 `[adapter.policy]`
/// block (all defaults) never bricks a scope (the R12-2 failure mode). Called on
/// every scope-config load (`validate_config`) and on the user-config load.
///
/// Wired keys (`allow_network`, `redact_logs`, `max_input_bytes`, the
/// `markdownize.incremental` enabled/threshold/max_consecutive, and the whole
/// `[search]` block) are NOT checked here — they change behavior, they are not
/// rejected.
pub fn enforce_config_semantics(config: &Value) -> Result<()> {
    if let Some(policy) = config
        .get("adapter")
        .and_then(|adapter| adapter.get("policy"))
    {
        // allowed_scope: only "." (scope containment, 07 §7.1.2 P1) is implemented.
        if let Some(scope) = policy.get("allowed_scope").and_then(Value::as_str) {
            if scope != "." {
                return Err(KcsError::not_implemented(
                    "adapter.policy.allowed_scope other than \".\"",
                ));
            }
        }
        // Request/response body persistence is never done (07 §7 "ログ本文禁止" —
        // only hashes are logged), so a `true` request is unimplemented.
        if policy.get("store_request_body").and_then(Value::as_bool) == Some(true) {
            return Err(KcsError::not_implemented(
                "adapter.policy.store_request_body = true",
            ));
        }
        if policy.get("store_response_body").and_then(Value::as_bool) == Some(true) {
            return Err(KcsError::not_implemented(
                "adapter.policy.store_response_body = true",
            ));
        }
        // The first-run command/URL approval flow (07 §7) is mandatory and cannot
        // be turned off.
        if policy
            .get("require_command_confirmation")
            .and_then(Value::as_bool)
            == Some(false)
        {
            return Err(KcsError::not_implemented(
                "adapter.policy.require_command_confirmation = false",
            ));
        }
        // timeout_seconds: a per-adapter execution timeout is not threaded through
        // the adapter HTTP path (it would touch every adapter's transport). Accept
        // the documented default (300); reject any other value loudly rather than
        // silently ignore it. (R12-2 decision: real wiring is a large change.)
        if let Some(timeout) = policy.get("timeout_seconds").and_then(Value::as_i64) {
            if timeout != 300 {
                return Err(KcsError::not_implemented(
                    "adapter.policy.timeout_seconds other than 300",
                ));
            }
        }
    }
    // markdownize.incremental.include_neighbors has no implementation concept
    // (R12-1); only the documented default (1) is a no-op — anything else is
    // rejected loudly. `enabled`/`threshold`/`max_consecutive` ARE wired at index
    // time, so they are not checked here.
    if let Some(incremental) = config
        .get("markdownize")
        .and_then(|markdownize| markdownize.get("incremental"))
    {
        if let Some(neighbors) = incremental.get("include_neighbors").and_then(Value::as_i64) {
            if neighbors != 1 {
                return Err(KcsError::not_implemented(
                    "markdownize.incremental.include_neighbors other than 1",
                ));
            }
        }
    }
    Ok(())
}

/// Reject a tag-name / commit-ref operand that could escape `refs/tags` when
/// joined onto the store path (N4, 03 §3 scope boundary). A ref is only ever
/// `HEAD`, a hash, or a tag name, so a path separator (`/` or `\`), `.`/`..`,
/// an absolute path, or any `ParentDir`/`RootDir`/`Prefix` component is always
/// a traversal attempt. Shared by `tag()` and `resolve_commit()`.
fn validate_ref_operand(value: &str) -> Result<()> {
    let traversal = value.is_empty()
        || value == "."
        || value == ".."
        || value.contains('/')
        || value.contains('\\')
        || Path::new(value).is_absolute()
        || Path::new(value).components().any(|component| {
            matches!(
                component,
                std::path::Component::ParentDir
                    | std::path::Component::RootDir
                    | std::path::Component::Prefix(_)
            )
        });
    if traversal {
        return Err(KcsError::invalid_usage(
            "commit reference must not contain path separators or `.`/`..` traversal",
        ));
    }
    Ok(())
}

fn data_home() -> PathBuf {
    // R12-6 / R13-6: empty/relative `XDG_DATA_HOME` AND empty/relative `HOME` are
    // both invalid — fall back to `$HOME/.local/share` only for an absolute `HOME`,
    // never to a CWD-relative dir. The CLI startup guard rejects the no-absolute-
    // base case loudly before we reach the `"."` last resort.
    crate::xdg::xdg_dir("XDG_DATA_HOME")
        .or_else(|| crate::xdg::home_dir().map(|home| home.join(".local/share")))
        .unwrap_or_else(|| PathBuf::from("."))
}

/// Built-in Tier-A name policy applied again at the closing archive read.
/// Keep this predicate aligned with `kcs_pipeline::scan::classify_secret`;
/// callers pass explicitly unignored Tier-A paths separately.
#[must_use]
pub fn is_tier_a_secret_name(path: &str) -> bool {
    let normalized = path.trim_start_matches('/').replace('\\', "/");
    let name = normalized.rsplit('/').next().unwrap_or(&normalized);
    let lower = name.to_ascii_lowercase();
    let lower_path = normalized.to_ascii_lowercase();
    let tier_a_path = lower_path == ".kube/config"
        || lower_path == ".docker/config.json"
        || lower_path.starts_with(".ssh/")
        || lower_path.starts_with(".gnupg/")
        || lower_path.starts_with(".aws/")
        || lower_path.starts_with(".kube/")
        || lower_path.starts_with(".docker/");
    lower == ".env"
        || lower.starts_with(".env.")
        || lower == ".ssh"
        || lower == ".gnupg"
        || lower == ".aws"
        || lower == ".kube"
        || lower == ".docker"
        || lower.ends_with(".pem")
        || lower.ends_with(".key")
        || lower.ends_with(".p12")
        || lower.ends_with(".pfx")
        || lower.starts_with("id_rsa")
        || lower.starts_with("id_ecdsa")
        || lower.starts_with("id_ed25519")
        || lower.ends_with(".keystore")
        || lower == ".netrc"
        || lower == ".npmrc"
        || lower == ".pypirc"
        || lower.ends_with(".tfstate")
        || lower.contains(".tfstate.")
        || tier_a_path
}

fn validate_store_directory(kcs_dir: &Path) -> Result<()> {
    let metadata = match fs::symlink_metadata(kcs_dir) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Err(KcsError::invalid_usage("not a kcs scope"))
        }
        Err(error) => {
            return Err(KcsError::io(
                error.to_string(),
                kcs_dir.display().to_string(),
            ))
        }
    };
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(unsafe_store_error(
            kcs_dir,
            ".kcs must be a real directory inside the selected scope root",
        ));
    }
    let resolved = kcs_dir.canonicalize().kcs_io(kcs_dir)?;
    if resolved != kcs_dir {
        return Err(unsafe_store_error(
            kcs_dir,
            ".kcs resolves outside the selected scope root",
        ));
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::{MetadataExt, PermissionsExt};

        if metadata.permissions().mode() & 0o077 != 0 {
            return Err(unsafe_store_error(
                kcs_dir,
                ".kcs must not be accessible to group or other principals",
            ));
        }
        if metadata.uid() != effective_uid() {
            return Err(unsafe_store_error(
                kcs_dir,
                ".kcs must be owned by the current effective user",
            ));
        }
    }
    Ok(())
}

#[cfg(unix)]
fn effective_uid() -> u32 {
    extern "C" {
        fn geteuid() -> u32;
    }
    // SAFETY: geteuid has no preconditions and only returns process metadata.
    unsafe { geteuid() }
}

fn unsafe_store_error(path: &Path, message: &str) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-UNSAFE-001",
        message,
        json!({ "kcs_path": path }),
        ExitCode::PermanentFailure,
    )
}

fn open_scope_file_nofollow(path: &Path) -> Result<File> {
    let before = fs::symlink_metadata(path).kcs_io(path)?;
    if before.file_type().is_symlink() || !before.file_type().is_file() {
        return Err(scope_file_changed_path(path));
    }

    let mut options = OpenOptions::new();
    options.read(true);
    configure_scope_no_follow(&mut options);
    let file = options.open(path).kcs_io(path)?;
    let opened = file.metadata().kcs_io(path)?;
    let after = fs::symlink_metadata(path).kcs_io(path)?;
    #[cfg(windows)]
    let same_identity = {
        let mut verification_options = OpenOptions::new();
        verification_options.read(true);
        configure_scope_no_follow(&mut verification_options);
        let verification = verification_options.open(path).kcs_io(path)?;
        verification.metadata().kcs_io(path)?.is_file()
            && same_scope_file_identity(&file, &verification)
    };
    #[cfg(not(windows))]
    let same_identity = same_scope_file_identity(&opened, &after);
    if !opened.is_file()
        || after.file_type().is_symlink()
        || !after.file_type().is_file()
        || !same_identity
    {
        return Err(scope_file_changed_path(path));
    }
    Ok(file)
}

#[cfg(unix)]
fn configure_scope_no_follow(options: &mut OpenOptions) {
    use std::os::unix::fs::OpenOptionsExt;

    #[cfg(any(target_os = "linux", target_os = "android"))]
    options.custom_flags(0x20_800);
    #[cfg(any(
        target_os = "macos",
        target_os = "ios",
        target_os = "freebsd",
        target_os = "openbsd",
        target_os = "netbsd",
        target_os = "dragonfly"
    ))]
    options.custom_flags(0x104);
    let _ = options;
}

#[cfg(windows)]
fn configure_scope_no_follow(options: &mut OpenOptions) {
    use std::os::windows::fs::OpenOptionsExt;
    options.custom_flags(0x0020_0000);
}

#[cfg(not(any(unix, windows)))]
fn configure_scope_no_follow(_options: &mut OpenOptions) {}

#[cfg(unix)]
fn same_scope_file_identity(opened: &fs::Metadata, path: &fs::Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    opened.dev() == path.dev() && opened.ino() == path.ino()
}

#[cfg(windows)]
fn same_scope_file_identity(opened: &File, path: &File) -> bool {
    crate::cas::same_windows_regular_file(opened, path)
}

#[cfg(not(any(unix, windows)))]
fn same_scope_file_identity(opened: &fs::Metadata, path: &fs::Metadata) -> bool {
    opened.len() == path.len() && opened.modified().ok() == path.modified().ok()
}

fn hash_scope_file(
    file: &mut File,
    path: &Path,
    file_name: &str,
    allowed: u64,
    limits: ArchiveLimits,
) -> Result<(String, u64)> {
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
    let mut total = 0_u64;
    loop {
        let read_cap = allowed
            .saturating_sub(total)
            .saturating_add(1)
            .min(buffer.len() as u64) as usize;
        let count = file.read(&mut buffer[..read_cap]).kcs_io(path)?;
        if count == 0 {
            break;
        }
        total = total
            .checked_add(count as u64)
            .ok_or_else(|| scope_input_oversized(file_name, limits, u64::MAX))?;
        if total > allowed {
            return Err(scope_input_oversized(file_name, limits, total));
        }
        hasher.update(&buffer[..count]);
    }
    Ok((format!("sha256:{}", hex_digest(&hasher.finalize())), total))
}

fn hex_digest(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

fn scope_input_oversized(file_name: &str, limits: ArchiveLimits, actual: u64) -> KcsError {
    KcsError::new(
        "KCS-E-SCOPE-INPUT-OVERSIZED-001",
        "scope input exceeds the core archive byte budget",
        json!({
            "path": file_name,
            "actual_bytes": actual,
            "max_file_bytes": limits.max_file_bytes,
            "max_scope_bytes": limits.max_scope_bytes,
        }),
        ExitCode::PermanentFailure,
    )
}

fn scope_tree_entries_oversized(observed: usize) -> KcsError {
    KcsError::new(
        "KCS-E-SCOPE-INPUT-OVERSIZED-001",
        "scope tree entry count exceeds the persisted tree limit",
        json!({
            "observed_entries": observed,
            "max_tree_entries": MAX_TREE_ENTRIES,
        }),
        ExitCode::PermanentFailure,
    )
}

fn scope_file_changed(file_name: &str) -> KcsError {
    KcsError::new(
        "KCS-E-SCOPE-FILE-CHANGED-001",
        "scope file changed while it was being archived",
        json!({ "path": file_name }),
        ExitCode::Failure,
    )
}

fn scope_file_changed_path(path: &Path) -> KcsError {
    KcsError::new(
        "KCS-E-SCOPE-FILE-CHANGED-001",
        "scope path no longer identifies the checked regular file",
        json!({ "path": path }),
        ExitCode::Failure,
    )
}

/// Restrict a directory that may hold document bytes / secrets / usage data to
/// owner-only access (0700) on unix (P2). Applied to the `.kcs` tree and the
/// device data dir (`~/.local/share/kcs`) at creation so a multi-user host
/// cannot read another user's archive. A 0700 parent blocks traversal into the
/// whole subtree regardless of child modes. No-op on non-unix.
pub fn restrict_dir_to_owner(dir: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(dir, fs::Permissions::from_mode(0o700)).kcs_io(dir)?;
    }
    #[cfg(not(unix))]
    {
        let _ = dir;
    }
    Ok(())
}

fn tree_map(tree: &TreeObject) -> BTreeMap<String, String> {
    tree.entries
        .iter()
        .map(|entry| (entry.path.clone(), entry.raw_hash.clone()))
        .collect()
}

/// Commit stats of `working` against an optional prior tree (`None` = unborn: all
/// files count as added). R15-4: pure (no I/O) — the caller reads the prior tree
/// once (and rejects a shallow HEAD) rather than re-reading it here.
fn commit_stats(prior: Option<&TreeObject>, working: &TreeObject) -> CommitStats {
    let current = tree_map(working);
    let old = prior.map(tree_map).unwrap_or_default();
    let mut added = 0;
    let mut modified = 0;
    let mut deleted = 0;

    let mut paths = BTreeSet::new();
    paths.extend(current.keys().cloned());
    paths.extend(old.keys().cloned());
    for path in paths {
        match (old.get(&path), current.get(&path)) {
            (None, Some(_)) => added += 1,
            (Some(_), None) => deleted += 1,
            (Some(a), Some(b)) if a != b => modified += 1,
            _ => {}
        }
    }

    CommitStats {
        files_added: added,
        files_modified: modified,
        files_deleted: deleted,
    }
}

/// R15-4: is `error` a raw missing-CAS-object error? Used to fold a missing tree
/// object into the shallow-commit policy (degrade reads / fail writes loudly).
fn is_store_not_found(error: &KcsError) -> bool {
    error.error_code() == "KCS-E-STORE-NOT-FOUND-001"
}

/// R17-5: a commit operand (`diff`/`tag` hash literal, or a tag-name target) whose
/// commit object is gone (shallow: discarded / corrupt) folds into
/// KCS-E-COMMIT-SHALLOW-001 — the same class every other shallow-commit site raises
/// (R16-1 / R16-5) — instead of a raw, opaque KCS-E-STORE-NOT-FOUND-001. Used by
/// `resolve_commit`, which runs before `diff_side_tree`'s R16-5 absorption, so
/// without this a hash-literal / tag-name shallow commit would bypass the
/// COMMIT-SHALLOW contract that the `HEAD` operand already reaches. Kept generic (no
/// diff side) because `resolve_commit` is shared by `diff` and `tag`; the diff side
/// is still named for the tree-GC case that reaches `diff_side_tree`.
fn resolve_commit_shallow_error(commit_hash: &str) -> KcsError {
    KcsError::commit_shallow(
        "referenced commit object is missing (shallow: discarded / corrupt); \
         restore the commit object or reference a non-shallow commit",
        commit_hash.to_owned(),
    )
}

/// R16-5: the `diff` shallow-side error, naming which operand (`a`/`b`) is shallow.
fn diff_side_shallow_error(side: &str, commit_hash: &str) -> KcsError {
    KcsError::new(
        "KCS-E-COMMIT-SHALLOW-001",
        format!(
            "diff side `{side}` is shallow (its commit or tree object is discarded); \
             a full-file diff is not possible when either side is shallow — diff a \
             non-shallow commit pair or restore the missing object"
        ),
        json!({ "commit_hash": commit_hash, "side": side }),
        ExitCode::Failure,
    )
}

fn validate_format_version(version: &str) -> Result<()> {
    let major = version
        .split('.')
        .next()
        .and_then(|value| value.parse::<u64>().ok())
        .ok_or_else(|| KcsError::schema("invalid kcs_format_version"))?;
    if major > 0 {
        Err(KcsError::incompatible_format(version))
    } else {
        Ok(())
    }
}

thread_local! {
    /// Reentrancy depth per `.lock` path for the current thread. A whole-command
    /// lock held by `kcs index`/`repair`/`reindex` must not deadlock against the
    /// `snapshot` sub-step re-acquiring the same lock inside the same process.
    static LOCK_DEPTH: RefCell<HashMap<PathBuf, u32>> = RefCell::new(HashMap::new());
}

/// RAII guard over the `.kcs/.lock` store lock (05 §6). Reentrant within a
/// process/thread: nested acquisitions increment a depth counter instead of
/// contending on the same `O_EXCL` file; the on-disk lock is removed only when
/// the outermost guard drops.
pub struct StoreLock {
    path: PathBuf,
    pid: u32,
    token: String,
    /// A nested (reentrant) acquisition owns no on-disk lock and must not remove
    /// the file on drop.
    reentrant: bool,
}

impl StoreLock {
    pub fn acquire(kcs_dir: &Path) -> Result<Self> {
        Self::acquire_path(kcs_dir.join(".lock"))
    }

    /// Acquire a lock at an explicit file path. Used for device-global locks that
    /// live outside any single `.kcs` store — notably the cost-ledger lock
    /// (`$XDG_DATA_HOME/kcs/cost-ledger.lock`, F8), which must serialize the
    /// budget read-check-append across every scope on the device. Same reentrancy
    /// (thread-local depth, keyed by the lock path) and stale-reclaim semantics as
    /// [`acquire`]; the parent directory is created if missing.
    pub fn acquire_path(path: PathBuf) -> Result<Self> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).kcs_io(parent)?;
        }
        let pid = std::process::id();

        // Reentrant fast path: this thread already holds the lock for `path`.
        let already_held = LOCK_DEPTH.with(|depth| {
            let mut depth = depth.borrow_mut();
            if let Some(count) = depth.get_mut(&path) {
                *count += 1;
                true
            } else {
                false
            }
        });
        if already_held {
            return Ok(Self {
                path,
                pid,
                token: String::new(),
                reentrant: true,
            });
        }

        let token = new_lock_token(pid);
        for _ in 0..2 {
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => {
                    write_lock_file(&path, &mut file, pid, &token)?;
                    LOCK_DEPTH.with(|depth| depth.borrow_mut().insert(path.clone(), 1));
                    return Ok(Self {
                        path,
                        pid,
                        token,
                        reentrant: false,
                    });
                }
                Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {
                    if reclaim_stale_lock(&path)? {
                        continue;
                    }
                    return Err(KcsError::locked(path.display().to_string()));
                }
                Err(err) => return Err(KcsError::io(err.to_string(), path.display().to_string())),
            }
        }

        Err(KcsError::locked(path.display().to_string()))
    }
}

impl Drop for StoreLock {
    fn drop(&mut self) {
        let released = LOCK_DEPTH.with(|depth| {
            let mut depth = depth.borrow_mut();
            if let Some(count) = depth.get_mut(&self.path) {
                *count -= 1;
                if *count == 0 {
                    depth.remove(&self.path);
                    return true;
                }
            }
            false
        });
        // Only the outermost (non-reentrant) guard owns the on-disk lock; remove
        // it exactly once, and only if it is still ours (token match).
        if released
            && !self.reentrant
            && lock_file_matches(&self.path, self.pid, &self.token).unwrap_or(false)
        {
            let _ = fs::remove_file(&self.path);
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
struct LockFile {
    pid: u32,
    token: String,
    created_at: String,
}

fn write_lock_file(path: &Path, file: &mut File, pid: u32, token: &str) -> Result<()> {
    let lock = LockFile {
        pid,
        token: token.to_owned(),
        created_at: now_utc_seconds(),
    };
    let body = serde_json::to_vec(&lock)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    file.write_all(&body).kcs_io(path)?;
    file.sync_all().kcs_io(path)
}

fn reclaim_stale_lock(path: &Path) -> Result<bool> {
    let Some(lock) = read_lock_file(path)? else {
        return Ok(true);
    };
    if process_is_alive(lock.pid) {
        return Ok(false);
    }

    let Some(current) = read_lock_file(path)? else {
        return Ok(true);
    };
    if current != lock || process_is_alive(current.pid) {
        return Ok(false);
    }
    match fs::remove_file(path) {
        Ok(()) => Ok(true),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(true),
        Err(err) => Err(KcsError::io(err.to_string(), path.display().to_string())),
    }
}

fn read_lock_file(path: &Path) -> Result<Option<LockFile>> {
    match fs::read_to_string(path) {
        Ok(value) => serde_json::from_str(&value)
            .map(Some)
            .map_err(|_| KcsError::locked(path.display().to_string())),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(err) => Err(KcsError::io(err.to_string(), path.display().to_string())),
    }
}

fn lock_file_matches(path: &Path, pid: u32, token: &str) -> Result<bool> {
    Ok(read_lock_file(path)?.is_some_and(|lock| lock.pid == pid && lock.token == token))
}

#[cfg(windows)]
fn process_is_alive(pid: u32) -> bool {
    if pid == std::process::id() {
        return true;
    }

    use windows_sys::Win32::Foundation::{
        CloseHandle, GetLastError, ERROR_INVALID_PARAMETER, STILL_ACTIVE,
    };
    use windows_sys::Win32::System::Threading::{
        GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
    };

    // SAFETY: `OpenProcess` is called with a PID read from the lock file and no
    // inheritable handle. A null handle is never passed to the query/close calls.
    let process = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
    if process.is_null() {
        // Windows documents ERROR_INVALID_PARAMETER for a PID that does not name
        // a process (including PID 0). Access denial and every other query error
        // are ambiguous, so keep the lock rather than reclaiming a live owner's.
        return unsafe { GetLastError() } != ERROR_INVALID_PARAMETER;
    }

    let mut exit_code = 0_u32;
    // SAFETY: `process` is a valid handle returned by `OpenProcess`, and
    // `exit_code` points to writable storage for the duration of the call.
    let queried = unsafe { GetExitCodeProcess(process, &mut exit_code) } != 0;
    // SAFETY: this function owns the process handle and closes it exactly once.
    let _ = unsafe { CloseHandle(process) };

    // A query failure is ambiguous. Conservatively retain the lock; otherwise,
    // STILL_ACTIVE is the documented marker for a process that has not exited.
    !queried || exit_code == STILL_ACTIVE as u32
}

#[cfg(not(windows))]
fn process_is_alive(pid: u32) -> bool {
    if pid == std::process::id() {
        return true;
    }
    // `kill -0` は EPERM (他ユーザ所有の生存プロセス) と ESRCH (不在) を exit code で
    // 区別できず、生存 lock を stale 回収する誤判定側に倒れる。`ps -p` は所有者に
    // 関係なく存在を確認できる。spawn 失敗時は保守的に「生存」と見なし回収しない。
    match Command::new("ps")
        .arg("-p")
        .arg(pid.to_string())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
    {
        Ok(status) => status.success(),
        Err(_) => true,
    }
}

fn new_lock_token(pid: u32) -> String {
    let seed = format!(
        "{pid}:{}:{}",
        unix_nanos(),
        std::thread::current().name().unwrap_or("")
    );
    let digest = Sha256::digest(seed.as_bytes());
    hex_prefix(&digest, 32)
}

#[cfg(debug_assertions)]
fn maybe_hold_lock_for_tests() {
    if let Ok(value) = std::env::var("KCS_TEST_HOLD_LOCK_MS") {
        if let Ok(ms) = value.parse::<u64>() {
            std::thread::sleep(std::time::Duration::from_millis(ms));
        }
    }
}

#[cfg(not(debug_assertions))]
fn maybe_hold_lock_for_tests() {}

fn unix_nanos() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default()
}

pub fn new_ulid(path: &Path) -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let timestamp_ms = now.as_millis() as u64;
    let mut bytes = [0_u8; 16];
    bytes[0] = ((timestamp_ms >> 40) & 0xff) as u8;
    bytes[1] = ((timestamp_ms >> 32) & 0xff) as u8;
    bytes[2] = ((timestamp_ms >> 24) & 0xff) as u8;
    bytes[3] = ((timestamp_ms >> 16) & 0xff) as u8;
    bytes[4] = ((timestamp_ms >> 8) & 0xff) as u8;
    bytes[5] = (timestamp_ms & 0xff) as u8;

    let seed = format!(
        "{}:{}:{}",
        path.display(),
        std::process::id(),
        now.as_nanos()
    );
    let digest = Sha256::digest(seed.as_bytes());
    bytes[6..].copy_from_slice(&digest[..10]);
    encode_crockford_base32(&bytes)
}

fn encode_crockford_base32(bytes: &[u8; 16]) -> String {
    const ALPHABET: &[u8; 32] = b"0123456789ABCDEFGHJKMNPQRSTVWXYZ";
    let mut value = u128::from_be_bytes(*bytes);
    let mut chars = [b'0'; 26];
    for index in (0..26).rev() {
        chars[index] = ALPHABET[(value & 0x1f) as usize];
        value >>= 5;
    }
    String::from_utf8(chars.to_vec()).expect("base32 alphabet is UTF-8")
}

fn hex_prefix(bytes: &[u8], chars: usize) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(chars);
    for byte in bytes {
        if out.len() >= chars {
            break;
        }
        out.push(HEX[(byte >> 4) as usize] as char);
        if out.len() < chars {
            out.push(HEX[(byte & 0x0f) as usize] as char);
        }
    }
    out
}

fn is_ulid(value: &str) -> bool {
    value.len() == 26
        && value
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'A'..=b'H' | b'J'..=b'K' | b'M'..=b'N' | b'P'..=b'T' | b'V'..=b'Z'))
}

pub fn now_utc_seconds() -> String {
    if let Some(value) = fixed_now_override() {
        return value;
    }
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;
    format_unix_seconds(secs)
}

/// Debug-only override for the current time via `KCS_FIXED_NOW`. The contract
/// tests (which build in debug) use it to pin `created_at`. It is compiled out
/// of release binaries so a production timestamp cannot be forged through the
/// environment (WS1c S4).
#[cfg(debug_assertions)]
fn fixed_now_override() -> Option<String> {
    std::env::var("KCS_FIXED_NOW").ok()
}

#[cfg(not(debug_assertions))]
fn fixed_now_override() -> Option<String> {
    None
}

fn format_unix_seconds(secs: i64) -> String {
    let days = secs.div_euclid(86_400);
    let second_of_day = secs.rem_euclid(86_400);
    let (year, month, day) = civil_from_days(days);
    let hour = second_of_day / 3_600;
    let minute = (second_of_day % 3_600) / 60;
    let second = second_of_day % 60;
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z")
}

fn civil_from_days(days: i64) -> (i64, i64, i64) {
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 }.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096).div_euclid(365);
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2).div_euclid(153);
    let day = doy - (153 * mp + 2).div_euclid(5) + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    let year = y + if month <= 2 { 1 } else { 0 };
    (year, month, day)
}

/// Inverse of [`civil_from_days`]: days since the Unix epoch for a civil date
/// (Howard Hinnant's algorithm).
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let y = if month <= 2 { year - 1 } else { year };
    let era = if y >= 0 { y } else { y - 399 }.div_euclid(400);
    let yoe = y - era * 400;
    let mp = if month > 2 { month - 3 } else { month + 9 };
    let doy = (153 * mp + 2).div_euclid(5) + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

/// Format Unix seconds as an RFC3339 UTC-seconds timestamp (`YYYY-MM-DDTHH:MM:SSZ`),
/// the shape produced by [`now_utc_seconds`].
#[must_use]
pub fn format_utc_seconds(secs: i64) -> String {
    format_unix_seconds(secs)
}

/// Parse an RFC3339 UTC-seconds timestamp (`YYYY-MM-DDTHH:MM:SSZ`, the shape
/// produced by [`now_utc_seconds`]) into Unix seconds. Returns `None` when the
/// input does not match that fixed-width shape. Used to schedule retry backoff
/// deadlines relative to the current (possibly `KCS_FIXED_NOW`) time.
#[must_use]
pub fn parse_utc_seconds(value: &str) -> Option<i64> {
    let bytes = value.as_bytes();
    if bytes.len() != 20
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[19] != b'Z'
    {
        return None;
    }
    let field = |start: usize, end: usize| value.get(start..end)?.parse::<i64>().ok();
    let year = field(0, 4)?;
    let month = field(5, 7)?;
    let day = field(8, 10)?;
    let hour = field(11, 13)?;
    let minute = field(14, 16)?;
    let second = field(17, 19)?;
    if !(1..=12).contains(&month)
        || !(1..=31).contains(&day)
        || hour > 23
        || minute > 59
        || second > 59
    {
        return None;
    }
    Some(days_from_civil(year, month, day) * 86_400 + hour * 3_600 + minute * 60 + second)
}

#[cfg(test)]
mod tests {
    use super::{
        append_jsonl_rotating, civil_from_days, format_unix_seconds, format_utc_seconds,
        open_scope_file_nofollow, parse_utc_seconds, process_is_alive, prune_rotated_logs,
        read_logs_retention_days, redact_context, redact_message_paths, rotate_stale_log,
        ArchiveLimits, PendingNormalizeRef, Repository, StoreLock, DEFAULT_MAX_ARCHIVE_FILE_BYTES,
        MAX_COMMIT_PARENTS, MAX_TREE_ENTRIES,
    };
    use crate::cas::{hash_bytes, ObjectKind, ObjectStore};
    use crate::dag::NormalizeRef;
    use serde_json::json;
    use std::collections::{BTreeMap, BTreeSet};
    use std::fs;

    #[test]
    fn process_liveness_recognizes_current_process() {
        assert!(process_is_alive(std::process::id()));
    }

    #[cfg(windows)]
    #[test]
    fn windows_process_liveness_rejects_reserved_pid_zero() {
        assert!(!process_is_alive(0));
    }

    // F8: the device-global cost-ledger lock is acquired via `acquire_path` at an
    // arbitrary path outside any `.kcs`. It must create the parent dir, remove the
    // lock on drop, and refuse to acquire while a lock file already holds the path.
    #[test]
    fn f8_acquire_path_is_device_global_and_excludes_a_held_lock() {
        let dir = tempfile::tempdir().unwrap();
        // Nested path whose parent does not exist yet — acquire_path must create it.
        let lock_path = dir.path().join("kcs/cost-ledger.lock");
        {
            let _guard = StoreLock::acquire_path(lock_path.clone()).unwrap();
            assert!(
                lock_path.exists(),
                "lock file must be created under a fresh dir"
            );
        }
        assert!(
            !lock_path.exists(),
            "lock file must be removed when the guard drops"
        );

        // A pre-existing lock file at the path blocks a fresh acquisition with
        // STORE-LOCKED, proving acquire_path honors a held device-global lock.
        fs::write(&lock_path, b"held by another charge").unwrap();
        match StoreLock::acquire_path(lock_path.clone()) {
            Ok(_) => panic!("a held device-global lock must block acquisition"),
            Err(err) => assert_eq!(err.error_code(), "KCS-E-STORE-LOCKED-001"),
        }
    }

    #[test]
    fn redact_message_paths_masks_absolute_paths_only() {
        // P4: the exact leak shapes — `io error at {path}` and
        // `corrupt store file at {path}` — must lose the absolute path.
        assert_eq!(
            redact_message_paths("io error at /private/var/x/.kcs/tasks.jsonl: Permission denied"),
            "io error at [redacted] Permission denied"
        );
        assert_eq!(
            redact_message_paths(
                "corrupt store file at /home/u/.kcs/tasks.jsonl: expected value at line 1"
            ),
            "corrupt store file at [redacted] expected value at line 1"
        );
        // Relative tokens and plain prose are untouched (no false positives).
        assert_eq!(
            redact_message_paths("scope registry write failed (recover with index)"),
            "scope registry write failed (recover with index)"
        );
        assert!(!redact_message_paths("read /etc/hosts now").contains("/etc/hosts"));
    }

    #[test]
    fn redact_context_masks_scope_path_and_candidates() {
        // P4: the extended allowlist covers the path-bearing keys used by the
        // purge / scope-ambiguous / registry error contexts.
        let mut context = json!({
            "scope_path": "/private/var/x/.kcs",
            "candidates": ["/a/.kcs", "/b/.kcs"],
            "root_path": "/private/var/x",
            "kcs_path": "/private/var/x/.kcs",
            "raw_hash": "sha256:abc",
        });
        redact_context(&mut context);
        assert_eq!(context["scope_path"], "[redacted]");
        assert_eq!(context["candidates"], "[redacted]");
        assert_eq!(context["root_path"], "[redacted]");
        assert_eq!(context["kcs_path"], "[redacted]");
        // Non-sensitive keys are preserved.
        assert_eq!(context["raw_hash"], "sha256:abc");
    }

    #[test]
    fn format_unix_seconds_known_vectors() {
        // Epoch and known Unix timestamps.
        assert_eq!(format_unix_seconds(0), "1970-01-01T00:00:00Z");
        assert_eq!(format_unix_seconds(1_700_000_000), "2023-11-14T22:13:20Z");
        assert_eq!(format_unix_seconds(1_777_464_000), "2026-04-29T12:00:00Z");
        // 2024 is a leap year: 02-29 exists and spans a full day.
        assert_eq!(format_unix_seconds(1_709_164_800), "2024-02-29T00:00:00Z");
        assert_eq!(format_unix_seconds(1_709_251_199), "2024-02-29T23:59:59Z");
        // 2100 is NOT a leap year (÷100, not ÷400): 02-28 rolls to 03-01.
        assert_eq!(format_unix_seconds(4_107_542_399), "2100-02-28T23:59:59Z");
        assert_eq!(format_unix_seconds(4_107_542_400), "2100-03-01T00:00:00Z");
        // Month / year boundary.
        assert_eq!(format_unix_seconds(1_704_067_199), "2023-12-31T23:59:59Z");
        assert_eq!(format_unix_seconds(1_704_067_200), "2024-01-01T00:00:00Z");
    }

    #[test]
    fn parse_utc_seconds_round_trips_and_rejects_bad_shapes() {
        // Round-trips against the known format vectors.
        for secs in [
            0,
            1_700_000_000,
            1_709_251_199,
            4_107_542_400,
            1_704_067_200,
        ] {
            assert_eq!(parse_utc_seconds(&format_utc_seconds(secs)), Some(secs));
        }
        // Offset arithmetic used by retry backoff scheduling.
        let base = parse_utc_seconds("2026-07-03T00:00:00Z").unwrap();
        assert_eq!(format_utc_seconds(base + 2), "2026-07-03T00:00:02Z");
        assert_eq!(format_utc_seconds(base + 60), "2026-07-03T00:01:00Z");
        // Malformed inputs are rejected rather than silently misparsed.
        assert_eq!(parse_utc_seconds("2026-07-03T00:00:00"), None);
        assert_eq!(parse_utc_seconds("2026-13-03T00:00:00Z"), None);
        assert_eq!(parse_utc_seconds("not-a-timestamp"), None);
    }

    // R13-3: a live log whose last-written day differs from "today" is rotated to
    // a dated name and the fixed name starts fresh (logrotate style); dated files
    // older than retention_days are pruned.
    #[test]
    fn r13_3_rotate_renames_stale_log_and_prune_drops_old_dated_files() {
        let dir = tempfile::tempdir().unwrap();
        let log = dir.path().join("events.jsonl");
        fs::write(&log, "line1\n").unwrap(); // mtime = real today

        // A far-future "today" makes the live file stale → rotate it away.
        rotate_stale_log(&log, "2099-01-02").unwrap();
        assert!(!log.exists(), "the stale live file must be renamed away");
        let dated: Vec<String> = fs::read_dir(dir.path())
            .unwrap()
            .filter_map(std::result::Result::ok)
            .map(|entry| entry.file_name().to_string_lossy().into_owned())
            .filter(|name| name.starts_with("events-") && name.ends_with(".jsonl"))
            .collect();
        assert_eq!(dated.len(), 1, "exactly one dated file created: {dated:?}");

        // Prune: a dated file older than retention_days goes; a recent one stays.
        fs::write(dir.path().join("events-2000-01-01.jsonl"), "old\n").unwrap();
        fs::write(dir.path().join("events-2099-01-01.jsonl"), "recent\n").unwrap();
        prune_rotated_logs(&log, "2099-01-02", 30).unwrap();
        assert!(
            !dir.path().join("events-2000-01-01.jsonl").exists(),
            "a dated file older than retention_days must be pruned"
        );
        assert!(
            dir.path().join("events-2099-01-01.jsonl").exists(),
            "a dated file within retention_days must be kept"
        );
    }

    #[test]
    fn r13_3_append_rotating_keeps_same_day_writes_in_the_live_file() {
        let dir = tempfile::tempdir().unwrap();
        let log = dir.path().join("events.jsonl");
        append_jsonl_rotating(&log, &json!({ "a": 1 }), 30).unwrap();
        append_jsonl_rotating(&log, &json!({ "a": 2 }), 30).unwrap();
        let content = fs::read_to_string(&log).unwrap();
        assert_eq!(
            content.lines().count(),
            2,
            "same-day appends stay in the live fixed-name file"
        );
        let rotated = fs::read_dir(dir.path())
            .unwrap()
            .filter_map(std::result::Result::ok)
            .any(|entry| entry.file_name().to_string_lossy().starts_with("events-"));
        assert!(!rotated, "no rotation may happen within the same day");
    }

    #[test]
    fn r13_3_prune_skips_unparseable_dated_files_and_append_still_lands() {
        // R13-3 / R12-5: rotation/prune are best-effort — a garbage file that looks
        // like a dated log but has no parseable date must be skipped (not error),
        // and the append must still succeed regardless.
        let dir = tempfile::tempdir().unwrap();
        let log = dir.path().join("events.jsonl");
        fs::write(dir.path().join("events-not-a-date.jsonl"), "junk\n").unwrap();
        prune_rotated_logs(&log, "2099-01-02", 30).unwrap();
        assert!(
            dir.path().join("events-not-a-date.jsonl").exists(),
            "an unparseable dated name must be skipped, not deleted or errored"
        );
        append_jsonl_rotating(&log, &json!({ "b": 2 }), 30).unwrap();
        assert!(log.exists(), "the append must land in the live file");
    }

    #[test]
    fn r13_3_read_logs_retention_days_parses_and_rejects_out_of_range() {
        let dir = tempfile::tempdir().unwrap();
        let cfg = dir.path().join("config.toml");
        fs::write(&cfg, "[logs]\nretention_days = 7\n").unwrap();
        assert_eq!(read_logs_retention_days(&cfg), Some(7));
        // < 1 is rejected by the schema too; the reader falls back to the default.
        fs::write(&cfg, "[logs]\nretention_days = 0\n").unwrap();
        assert_eq!(read_logs_retention_days(&cfg), None);
        assert_eq!(
            read_logs_retention_days(&dir.path().join("missing.toml")),
            None
        );
    }

    #[test]
    fn civil_from_days_boundaries() {
        assert_eq!(civil_from_days(0), (1970, 1, 1));
        assert_eq!(civil_from_days(19_782), (2024, 2, 29));
        assert_eq!(civil_from_days(19_783), (2024, 3, 1));
        assert_eq!(civil_from_days(47_540), (2100, 2, 28));
        assert_eq!(civil_from_days(47_541), (2100, 3, 1));
        // Negative day index -> proleptic pre-epoch date.
        assert_eq!(civil_from_days(-1), (1969, 12, 31));
    }

    #[cfg(unix)]
    #[test]
    fn cand_008_symlinked_kcs_store_is_rejected() {
        use std::os::unix::fs::symlink;

        let victim = tempfile::tempdir().unwrap();
        let victim_repo = Repository::init(victim.path()).unwrap();
        let lure = tempfile::tempdir().unwrap();
        symlink(victim_repo.kcs_dir(), lure.path().join(".kcs")).unwrap();

        let error = Repository::open(lure.path()).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-UNSAFE-001");
    }

    #[cfg(unix)]
    #[test]
    fn cand_024_existing_store_requires_private_owner_mode() {
        use std::os::unix::fs::{MetadataExt, PermissionsExt};

        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let kcs_dir = repo.kcs_dir().to_path_buf();
        assert_eq!(
            fs::metadata(&kcs_dir).unwrap().uid(),
            super::effective_uid()
        );

        fs::set_permissions(&kcs_dir, fs::Permissions::from_mode(0o755)).unwrap();
        let error = Repository::open(dir.path()).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-UNSAFE-001");

        fs::set_permissions(&kcs_dir, fs::Permissions::from_mode(0o700)).unwrap();
        Repository::open(dir.path()).unwrap();
        fs::set_permissions(&kcs_dir, fs::Permissions::from_mode(0o500)).unwrap();
        Repository::open(dir.path()).unwrap();
        fs::set_permissions(&kcs_dir, fs::Permissions::from_mode(0o700)).unwrap();
    }

    #[test]
    fn cand_025_scope_identity_binds_portable_id_to_canonical_root() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let identity = repo.scope_identity().unwrap();
        assert_eq!(identity.canonical_root, dir.path().canonicalize().unwrap());
        assert!(!identity.scope_id.is_empty());
    }

    #[cfg(unix)]
    #[test]
    fn cand_018_checked_regular_replaced_by_symlink_is_never_opened() {
        use std::os::unix::fs::symlink;

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("report.txt");
        fs::write(&path, b"benign").unwrap();
        let entry = fs::read_dir(dir.path()).unwrap().next().unwrap().unwrap();
        assert!(entry.file_type().unwrap().is_file());

        let original = dir.path().join("original.txt");
        let outside = dir.path().join("outside.txt");
        fs::rename(&path, &original).unwrap();
        fs::write(&outside, b"outside marker").unwrap();
        symlink(&outside, &path).unwrap();

        assert!(open_scope_file_nofollow(&path).is_err());
    }

    #[cfg(windows)]
    #[test]
    fn cand_018_windows_scope_identity_rejects_distinct_equal_sized_files() {
        let dir = tempfile::tempdir().unwrap();
        let first = dir.path().join("first.txt");
        let second = dir.path().join("second.txt");
        fs::write(&first, b"same-size").unwrap();
        fs::write(&second, b"same-size").unwrap();
        let first_handle = fs::File::open(&first).unwrap();
        let same_handle = fs::File::open(&first).unwrap();
        let second_handle = fs::File::open(&second).unwrap();

        assert!(super::same_scope_file_identity(&first_handle, &same_handle));
        assert!(!super::same_scope_file_identity(
            &first_handle,
            &second_handle
        ));
        assert!(open_scope_file_nofollow(&first).is_ok());
    }

    #[cfg(unix)]
    #[test]
    fn cand_018_stable_symlink_remains_skipped() {
        use std::os::unix::fs::symlink;

        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let outside = dir.path().join("outside-source");
        fs::write(&outside, b"outside marker").unwrap();
        symlink(&outside, dir.path().join("linked.txt")).unwrap();
        let tree = repo.build_working_tree(false).unwrap().tree;
        assert!(tree.entries.iter().all(|entry| entry.path != "linked.txt"));
    }

    #[test]
    fn cand_019_archive_limits_accept_exact_and_reject_plus_one_and_aggregate() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let empty_paths = BTreeSet::new();
        let empty_normalize = BTreeMap::new();
        let limit = 64 * 1024;
        fs::write(dir.path().join("exact.bin"), vec![b'x'; limit]).unwrap();
        repo.build_working_tree_with_limits(
            false,
            &empty_paths,
            &empty_normalize,
            ArchiveLimits::new(limit as u64, limit as u64),
        )
        .unwrap();

        fs::write(dir.path().join("exact.bin"), vec![b'x'; limit + 1]).unwrap();
        let error = repo
            .build_working_tree_with_limits(
                false,
                &empty_paths,
                &empty_normalize,
                ArchiveLimits::new(limit as u64, (2 * limit) as u64),
            )
            .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-SCOPE-INPUT-OVERSIZED-001");

        fs::write(dir.path().join("exact.bin"), vec![b'x'; 40 * 1024]).unwrap();
        fs::write(dir.path().join("second.bin"), vec![b'y'; 40 * 1024]).unwrap();
        let error = repo
            .build_working_tree_with_limits(
                false,
                &empty_paths,
                &empty_normalize,
                ArchiveLimits::new(limit as u64, limit as u64),
            )
            .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-SCOPE-INPUT-OVERSIZED-001");
    }

    #[test]
    fn cand_019_oversized_sparse_snapshot_does_not_advance_head_or_write_raw() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let path = dir.path().join("oversized.bin");
        let file = fs::File::create(&path).unwrap();
        file.set_len(DEFAULT_MAX_ARCHIVE_FILE_BYTES + 1).unwrap();
        let head_before = fs::read(repo.kcs_dir().join("HEAD")).unwrap();

        let error = repo.snapshot(Some("oversized"), None).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-SCOPE-INPUT-OVERSIZED-001");
        assert_eq!(fs::read(repo.kcs_dir().join("HEAD")).unwrap(), head_before);
        assert_eq!(
            fs::read_dir(repo.kcs_dir().join("objects/raw"))
                .unwrap()
                .count(),
            0
        );
    }

    #[test]
    fn cand_041_closing_snapshot_reclassifies_new_tier_a_names() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        fs::write(dir.path().join("notes.md"), b"notes").unwrap();
        fs::write(dir.path().join(".env"), b"synthetic=value").unwrap();

        let outcome = repo
            .snapshot_filtered(Some("closing"), None, &BTreeSet::new())
            .unwrap();
        let tree = repo.read_tree(&outcome.tree_hash).unwrap();
        assert_eq!(tree.entries.len(), 1);
        assert_eq!(tree.entries[0].path, "notes.md");

        let allowed = BTreeSet::from([".env".to_owned()]);
        let outcome = repo
            .snapshot_filtered_with_policy(Some("explicit lift"), None, &BTreeSet::new(), &allowed)
            .unwrap();
        let tree = repo.read_tree(&outcome.tree_hash).unwrap();
        assert!(tree.entries.iter().any(|entry| entry.path == ".env"));
    }

    #[test]
    fn cand_042_normalize_ref_attaches_only_to_its_expected_raw_hash() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let path = dir.path().join("doc.txt");
        fs::write(&path, b"old bytes").unwrap();
        let normalize = NormalizeRef {
            tool_profile_hash: hash_bytes(b"profile"),
            gen: 0,
        };
        let pending = BTreeMap::from([(
            "doc.txt".to_owned(),
            PendingNormalizeRef {
                expected_raw_hash: hash_bytes(b"old bytes"),
                normalize: normalize.clone(),
            },
        )]);
        let limits = ArchiveLimits::new(1024, 1024);
        let tree = repo
            .build_working_tree_with_bound_normalize_and_limits(
                false,
                &BTreeSet::new(),
                &pending,
                &BTreeSet::new(),
                limits,
            )
            .unwrap()
            .tree;
        assert_eq!(tree.entries[0].normalize, Some(normalize));

        fs::write(&path, b"new bytes").unwrap();
        let tree = repo
            .build_working_tree_with_bound_normalize_and_limits(
                false,
                &BTreeSet::new(),
                &pending,
                &BTreeSet::new(),
                limits,
            )
            .unwrap()
            .tree;
        assert_eq!(tree.entries[0].raw_hash, hash_bytes(b"new bytes"));
        assert!(tree.entries[0].normalize.is_none());
    }

    #[test]
    fn cand_043_poisoned_raw_slot_prevents_snapshot_publication() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        fs::write(dir.path().join("doc.txt"), b"expected bytes").unwrap();
        let hash = hash_bytes(b"expected bytes");
        let store = ObjectStore::new(repo.kcs_dir());
        let object_path = store.object_path(ObjectKind::Raw, &hash).unwrap();
        fs::create_dir_all(object_path.parent().unwrap()).unwrap();
        fs::write(&object_path, b"poisoned").unwrap();
        let head_before = fs::read(repo.kcs_dir().join("HEAD")).unwrap();

        let error = repo.snapshot(Some("poisoned"), None).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
        assert_eq!(fs::read(repo.kcs_dir().join("HEAD")).unwrap(), head_before);
    }

    #[test]
    fn cand_036_persisted_dag_objects_are_semantically_validated() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let store = ObjectStore::new(repo.kcs_dir());
        let invalid_tree = json!({
            "entries": [{"path":"sub/file", "type":"file", "raw_hash":hash_bytes(b"raw")}],
            "object_type":"tree"
        });
        let (hash, _) = store.write_json(ObjectKind::Tree, &invalid_tree).unwrap();
        assert!(repo.read_tree(&hash).is_err());
    }

    #[test]
    fn cand_046_dag_cardinality_limits_apply_after_bounded_deserialization() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let store = ObjectStore::new(repo.kcs_dir());
        let parent = hash_bytes(b"parent");
        let commit = json!({
            "commit_type":"manual",
            "created_at":"2026-07-12T00:00:00Z",
            "message":"bounded",
            "object_type":"commit",
            "parents":vec![parent; MAX_COMMIT_PARENTS + 1],
            "stats":{"files_added":0,"files_modified":0,"files_deleted":0},
            "tool_lock_hash":hash_bytes(b"tool"),
            "tree":hash_bytes(b"tree")
        });
        let (commit_hash, _) = store.write_json(ObjectKind::Commit, &commit).unwrap();
        assert!(repo.read_commit(&commit_hash).is_err());

        let entry = json!({"path":"a", "type":"file", "raw_hash":hash_bytes(b"raw")});
        let tree = json!({
            "entries":vec![entry; MAX_TREE_ENTRIES + 1],
            "object_type":"tree"
        });
        let (tree_hash, _) = store.write_json(ObjectKind::Tree, &tree).unwrap();
        assert!(repo.read_tree(&tree_hash).is_err());
    }

    #[test]
    fn cand_046_snapshot_rejects_tree_entry_overflow_before_publication() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        for index in 0..=MAX_TREE_ENTRIES {
            fs::File::create(dir.path().join(format!("entry-{index:05}.txt"))).unwrap();
        }

        let head_before = fs::read(repo.kcs_dir().join("HEAD")).unwrap();
        let branch_before = fs::read(repo.kcs_dir().join("refs/heads/main")).unwrap();
        let error = repo.snapshot(Some("over-limit"), None).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-SCOPE-INPUT-OVERSIZED-001");
        assert_eq!(
            error.context()["observed_entries"],
            json!(MAX_TREE_ENTRIES + 1)
        );
        assert_eq!(error.context()["max_tree_entries"], json!(MAX_TREE_ENTRIES));
        assert_eq!(fs::read(repo.kcs_dir().join("HEAD")).unwrap(), head_before);
        assert_eq!(
            fs::read(repo.kcs_dir().join("refs/heads/main")).unwrap(),
            branch_before
        );
        for kind in ["raw", "trees", "commits"] {
            assert_eq!(
                fs::read_dir(repo.kcs_dir().join("objects").join(kind))
                    .unwrap()
                    .count(),
                0,
                "over-limit snapshot published a {kind} CAS object"
            );
        }

        fs::remove_file(
            dir.path()
                .join(format!("entry-{:05}.txt", MAX_TREE_ENTRIES)),
        )
        .unwrap();
        let boundary = repo.build_working_tree(false).unwrap();
        assert_eq!(boundary.tree.entries.len(), MAX_TREE_ENTRIES);
    }

    // R15-1 / R15-1b: an empty HEAD whose `refs/heads/main` still names a real commit
    // is CORRUPT, not unborn. `head_commit_hash` must recover the commit from refs
    // (side-effect-free) so a `snapshot` extends real history instead of orphaning it
    // under a fresh `parents=[]` root, and so a pure read does not misreport. This
    // exercises the fallback DIRECTLY, without `open()` (whose `self_heal_head` would
    // otherwise repair HEAD first) — i.e. the exact window R15-1 found (heal deferred).
    #[test]
    fn r15_1_empty_head_recovers_from_refs_and_snapshot_does_not_orphan() {
        use super::Repository;
        use crate::cas::ObjectStore;

        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let kcs_dir = repo.kcs_dir().to_path_buf();
        let root = repo.root().to_path_buf();

        fs::write(root.join("doc.txt"), "v1").unwrap();
        let c1_hash = repo
            .snapshot(Some("c1"), None)
            .unwrap()
            .commit_hash
            .unwrap();

        // Corrupt HEAD to empty (crash truncation); refs still names C1.
        fs::write(kcs_dir.join("HEAD"), "").unwrap();

        // A Repository built WITHOUT `open()` (so `self_heal_head` never runs) still
        // recovers the real HEAD from refs.
        let direct = Repository {
            root: root.clone(),
            kcs_dir: kcs_dir.clone(),
            store: ObjectStore::new(kcs_dir.clone()),
        };
        assert_eq!(
            direct.head_commit_hash().unwrap(),
            Some(c1_hash.clone()),
            "empty HEAD + healthy refs must recover the refs commit"
        );

        // A snapshot taken while HEAD is still physically empty must PARENT on C1,
        // not orphan under a fresh root.
        fs::write(root.join("doc.txt"), "v2").unwrap();
        let c2_hash = direct
            .snapshot(Some("c2"), None)
            .unwrap()
            .commit_hash
            .unwrap();
        assert_eq!(
            direct.read_commit(&c2_hash).unwrap().parents,
            vec![c1_hash],
            "snapshot under a corrupt (empty) HEAD must extend the recovered history"
        );

        // Genuinely unborn (HEAD and refs both empty) still returns None.
        fs::write(kcs_dir.join("HEAD"), "").unwrap();
        fs::write(kcs_dir.join("refs/heads/main"), "").unwrap();
        assert_eq!(
            direct.head_commit_hash().unwrap(),
            None,
            "both HEAD and refs empty is a genuinely unborn branch"
        );
    }
}
