//! Folder-scope repository operations for Step 1.

use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

use crate::cas::{
    append_jsonl, atomic_overwrite, atomic_write, hash_bytes, hash_json, is_hash, ObjectKind,
    ObjectStore,
};
use crate::dag::{
    build_tree, CommitObject, CommitStats, CommitType, NormalizeRef, TreeEntry, TreeObject,
};
use crate::error::{IoResultExt, KcsError, Result};
use crate::schema::{validate_json_schema, SchemaKind};
use crate::ExitCode;

const FORMAT_VERSION: &str = "0.1.0";
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
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub raw_hash: Option<String>,
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
        if kcs_dir.exists() {
            return Self::open(root);
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
        if !kcs_dir.is_dir() {
            return Err(KcsError::invalid_usage("not a kcs scope"));
        }

        let repo = Self {
            root,
            kcs_dir: kcs_dir.clone(),
            store: ObjectStore::new(kcs_dir),
        };
        repo.validate()?;
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
        let mut entries = Vec::new();
        for entry in fs::read_dir(&self.root).kcs_io(&self.root)? {
            let entry = entry.kcs_io(&self.root)?;
            if entry.file_name() == ".kcs" {
                continue;
            }
            let path = entry.path();
            let file_type = entry.file_type().kcs_io(&path)?;
            // Subfolders are out of scope (03 §3: direct children only) and are
            // skipped silently. Symlinks / other non-regular files are skipped
            // with a warning so the omission is visible (WS1c S5, 10 §4).
            if file_type.is_dir() {
                continue;
            }
            if !file_type.is_file() {
                eprintln!("warning: skipping non-regular file: {}", path.display());
                continue;
            }
            // A non-UTF-8 file name cannot be a tree entry path; warn and skip
            // rather than failing the whole snapshot (WS1c S6).
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
            let bytes = fs::read(&path).kcs_io(&path)?;
            let raw_hash = if store_raw {
                self.store.write_raw(&bytes)?
            } else {
                hash_bytes(&bytes)
            };
            let mut tree_entry = TreeEntry::raw_file(file_name.clone(), raw_hash)?;
            tree_entry.normalize = normalize_by_path.get(&file_name).cloned();
            tree_entry.validate()?;
            entries.push(tree_entry);
        }
        Ok(WorkingTree {
            tree: build_tree(entries)?,
        })
    }

    pub fn status(&self) -> Result<Vec<FileStatus>> {
        self.validate()?;
        let current = self.build_working_tree(false)?.tree;
        let current_map = tree_map(&current);
        let head_tree = self.head_tree()?;
        let head_map = head_tree.as_ref().map(tree_map).unwrap_or_default();

        let mut paths = BTreeSet::new();
        paths.extend(current_map.keys().cloned());
        paths.extend(head_map.keys().cloned());

        let mut statuses = Vec::new();
        for path in paths {
            let status = match (head_map.get(&path), current_map.get(&path)) {
                (None, Some(_)) => "new",
                (Some(old), Some(new)) if old == new => "unchanged",
                (Some(_), Some(_)) => "modified",
                (Some(_), None) => "deleted",
                (None, None) => continue,
            };
            statuses.push(FileStatus {
                path: self.root.join(&path),
                relative_path: path.clone(),
                status: status.to_owned(),
                raw_hash: current_map
                    .get(&path)
                    .or_else(|| head_map.get(&path))
                    .cloned(),
            });
        }
        Ok(statuses)
    }

    pub fn snapshot(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
    ) -> Result<SnapshotOutcome> {
        self.snapshot_filtered(message, fixed_now, &BTreeSet::new())
    }

    /// Manual snapshot that honors an `excluded_paths` filter (N2). `kcs core`
    /// has no notion of secrets; the CLI computes the Tier A exclusion set from
    /// `build_scan_preview` and passes it here so a manual `kcs snapshot` cannot
    /// bake `.env`/`*.pem` plaintext into the CAS + tree (10 §1.1 "CAS 保存・
    /// snapshot 取り込みを行わない"). Same exclusion channel `kcs index` uses.
    pub fn snapshot_filtered(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        excluded_paths: &BTreeSet<String>,
    ) -> Result<SnapshotOutcome> {
        self.snapshot_with_type(
            message,
            fixed_now,
            CommitType::Manual,
            excluded_paths,
            &BTreeMap::new(),
        )
    }

    pub fn auto_snapshot(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        excluded_paths: &BTreeSet<String>,
    ) -> Result<SnapshotOutcome> {
        self.auto_snapshot_with_normalize(message, fixed_now, excluded_paths, &BTreeMap::new())
    }

    pub fn auto_snapshot_with_normalize(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        excluded_paths: &BTreeSet<String>,
        normalize_by_path: &BTreeMap<String, NormalizeRef>,
    ) -> Result<SnapshotOutcome> {
        self.snapshot_with_type(
            message,
            fixed_now,
            CommitType::Auto,
            excluded_paths,
            normalize_by_path,
        )
    }

    fn snapshot_with_type(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        commit_type: CommitType,
        excluded_paths: &BTreeSet<String>,
        normalize_by_path: &BTreeMap<String, NormalizeRef>,
    ) -> Result<SnapshotOutcome> {
        self.validate()?;
        let _lock = StoreLock::acquire(&self.kcs_dir)?;
        maybe_hold_lock_for_tests();

        let working = self
            .build_working_tree_with_normalize(true, excluded_paths, normalize_by_path)?
            .tree;
        let tree_value =
            serde_json::to_value(&working).map_err(|err| KcsError::schema(err.to_string()))?;
        let (tree_hash, _) = self.store.write_json(ObjectKind::Tree, &tree_value)?;
        let head_hash = self.head_commit_hash()?;
        let head_tree_hash = head_hash
            .as_deref()
            .map(|hash| self.read_commit(hash).map(|commit| commit.tree))
            .transpose()?;
        // Snapshot the prior HEAD tree now — after the ref updates below,
        // head_tree() would return the NEW tree (useless as "previous").
        let prior_tree = head_tree_hash
            .as_deref()
            .map(|hash| self.read_tree(hash))
            .transpose()?;
        let stats = self.stats_against_head(&working)?;

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

    pub fn log(&self) -> Result<Vec<LogEntry>> {
        self.validate()?;
        let mut entries = Vec::new();
        let mut next = self.head_commit_hash()?;
        while let Some(hash) = next {
            let commit = self.read_commit(&hash)?;
            next = commit.parents.first().cloned();
            entries.push(LogEntry {
                commit_hash: hash,
                commit,
            });
        }
        Ok(entries)
    }

    pub fn diff(&self, a: &str, b: &str) -> Result<Vec<DiffEntry>> {
        self.validate()?;
        let a_hash = self.resolve_commit(a)?;
        let b_hash = self.resolve_commit(b)?;
        let a_tree = self.read_tree(&self.read_commit(&a_hash)?.tree)?;
        let b_tree = self.read_tree(&self.read_commit(&b_hash)?.tree)?;
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

    pub fn inspect(&self, hash: &str) -> Result<InspectedObject> {
        self.validate()?;
        let object = self.store.read_by_hash(hash)?;
        match object.kind {
            ObjectKind::Tree => serde_json::from_slice(&object.bytes)
                .map(InspectedObject::Tree)
                .map_err(|err| KcsError::schema(err.to_string())),
            ObjectKind::Commit => serde_json::from_slice(&object.bytes)
                .map(InspectedObject::Commit)
                .map_err(|err| KcsError::schema(err.to_string())),
            ObjectKind::Raw => Ok(InspectedObject::Raw {
                raw_hash: object.hash,
                size_bytes: object.bytes.len() as u64,
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
        self.read_commit(&commit_hash)?;
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
            self.read_commit(value)?;
            return Ok(value.to_owned());
        }
        let tag = self.kcs_dir.join("refs/tags").join(value);
        if tag.is_file() {
            let hash = fs::read_to_string(&tag).kcs_io(&tag)?;
            let hash = hash.trim().to_owned();
            self.read_commit(&hash)?;
            return Ok(hash);
        }
        Err(KcsError::not_found(value))
    }

    pub fn read_commit(&self, hash: &str) -> Result<CommitObject> {
        let object = self.store.read_by_hash(hash)?;
        if object.kind != ObjectKind::Commit {
            return Err(KcsError::schema("hash does not identify a commit"));
        }
        serde_json::from_slice(&object.bytes).map_err(|err| KcsError::schema(err.to_string()))
    }

    pub fn read_tree(&self, hash: &str) -> Result<TreeObject> {
        let object = self.store.read_by_hash(hash)?;
        if object.kind != ObjectKind::Tree {
            return Err(KcsError::schema("hash does not identify a tree"));
        }
        serde_json::from_slice(&object.bytes).map_err(|err| KcsError::schema(err.to_string()))
    }

    pub fn head_commit_hash(&self) -> Result<Option<String>> {
        let path = self.kcs_dir.join("HEAD");
        let value = fs::read_to_string(&path).kcs_io(&path)?;
        let value = value.trim();
        if value.is_empty() {
            Ok(None)
        } else if is_hash(value) {
            Ok(Some(value.to_owned()))
        } else {
            Err(KcsError::schema("HEAD must contain a commit_hash"))
        }
    }

    fn head_tree(&self) -> Result<Option<TreeObject>> {
        self.head_commit_hash()?
            .map(|hash| {
                self.read_commit(&hash)
                    .and_then(|commit| self.read_tree(&commit.tree))
            })
            .transpose()
    }

    fn stats_against_head(&self, working: &TreeObject) -> Result<CommitStats> {
        let current = tree_map(working);
        let head = self.head_tree()?;
        let old = head.as_ref().map(tree_map).unwrap_or_default();
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

        Ok(CommitStats {
            files_added: added,
            files_modified: modified,
            files_deleted: deleted,
        })
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
        Ok(())
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
    let path = data_home().join("kcs/logs").join(file_name);
    append_jsonl(
        &path,
        &json!({
            "ts": now_utc_seconds(),
            "level": level,
            "code": code,
            "component": "kcs-cli",
            "message": message,
            "context": context,
        }),
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
    // R12-6: empty/relative `XDG_CONFIG_HOME` is invalid per the XDG spec — fall
    // back to `$HOME/.config` rather than a CWD-relative dir.
    crate::xdg::xdg_dir("XDG_CONFIG_HOME")
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".config")))
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
    // R12-6: empty/relative `XDG_DATA_HOME` is invalid per the XDG spec — fall
    // back to `$HOME/.local/share` rather than a CWD-relative dir.
    crate::xdg::xdg_dir("XDG_DATA_HOME")
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".local/share")))
        .unwrap_or_else(|| PathBuf::from("."))
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
        civil_from_days, format_unix_seconds, format_utc_seconds, parse_utc_seconds,
        redact_context, redact_message_paths, StoreLock,
    };
    use serde_json::json;
    use std::fs;

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
}
