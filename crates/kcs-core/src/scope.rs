//! Folder-scope repository operations for Step 1.

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::cas::{
    append_jsonl, atomic_overwrite, atomic_write, hash_bytes, hash_json, is_hash, ObjectKind,
    ObjectStore,
};
use crate::dag::{build_tree, CommitObject, CommitStats, CommitType, TreeEntry, TreeObject};
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

    pub fn validate(&self) -> Result<()> {
        self.validate_config()?;
        self.validate_scope()?;
        self.validate_manifest()?;
        Ok(())
    }

    pub fn build_working_tree(&self, store_raw: bool) -> Result<WorkingTree> {
        let mut entries = Vec::new();
        for entry in fs::read_dir(&self.root).kcs_io(&self.root)? {
            let entry = entry.kcs_io(&self.root)?;
            if entry.file_name() == ".kcs" {
                continue;
            }
            if !entry.file_type().kcs_io(&entry.path())?.is_file() {
                continue;
            }
            let path = entry.path();
            let file_name = entry.file_name().into_string().map_err(|_| {
                KcsError::path("file name must be UTF-8", path.display().to_string())
            })?;
            let bytes = fs::read(&path).kcs_io(&path)?;
            let raw_hash = if store_raw {
                self.store.write_raw(&bytes)?
            } else {
                hash_bytes(&bytes)
            };
            entries.push(TreeEntry::raw_file(file_name, raw_hash)?);
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
        self.validate()?;
        let _lock = StoreLock::acquire(&self.kcs_dir)?;
        maybe_hold_lock_for_tests();

        let working = self.build_working_tree(true)?.tree;
        let tree_value =
            serde_json::to_value(&working).map_err(|err| KcsError::schema(err.to_string()))?;
        let (tree_hash, _) = self.store.write_json(ObjectKind::Tree, &tree_value)?;
        let head_hash = self.head_commit_hash()?;
        let head_tree_hash = head_hash
            .as_deref()
            .map(|hash| self.read_commit(hash).map(|commit| commit.tree))
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
            .or_else(|| std::env::var("KCS_FIXED_NOW").ok())
            .unwrap_or_else(now_utc_seconds);
        let message = message
            .map(str::to_owned)
            .unwrap_or_else(|| format!("snapshot at {created_at}"));
        let parents = head_hash.into_iter().collect::<Vec<_>>();
        let commit = CommitObject::new(
            tree_hash.clone(),
            parents,
            created_at,
            message,
            self.tool_lock_hash()?,
            stats.clone(),
            CommitType::Manual,
        )?;
        let commit_value =
            serde_json::to_value(&commit).map_err(|err| KcsError::schema(err.to_string()))?;
        let (commit_hash, _) = self.store.write_json(ObjectKind::Commit, &commit_value)?;

        atomic_overwrite(
            &self.kcs_dir.join("refs/heads/main"),
            commit_hash.as_bytes(),
        )?;
        atomic_overwrite(&self.kcs_dir.join("HEAD"), commit_hash.as_bytes())?;
        self.write_manifest(&working)?;

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
        if name.is_empty() || name.contains('/') {
            return Err(KcsError::invalid_usage("tag name must not contain /"));
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

    fn write_manifest(&self, tree: &TreeObject) -> Result<()> {
        let files = tree
            .entries
            .iter()
            .map(|entry| {
                json!({
                    "path": entry.path,
                    "raw_hash": entry.raw_hash,
                    "status": "unchanged",
                })
            })
            .collect::<Vec<_>>();
        let value = json!({
            "schema_version": 1,
            "files": files,
            "updated_at": now_utc_seconds(),
        });
        let bytes =
            serde_json::to_vec_pretty(&value).map_err(|err| KcsError::schema(err.to_string()))?;
        atomic_overwrite(&self.kcs_dir.join("manifest.json"), &bytes)
    }

    fn tool_lock_hash(&self) -> Result<String> {
        let path = self.kcs_dir.join("tool-lock.json");
        if path.is_file() {
            let value: Value = serde_json::from_str(&fs::read_to_string(&path).kcs_io(&path)?)
                .map_err(|err| KcsError::schema(err.to_string()))?;
            hash_json(&value)
        } else {
            hash_json(&json!({ "spec_version": 1 }))
        }
    }
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

fn append_observation(
    file_name: &str,
    level: &str,
    code: &str,
    message: &str,
    context: Value,
) -> Result<()> {
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

fn data_home() -> PathBuf {
    if let Some(path) = std::env::var_os("XDG_DATA_HOME") {
        return PathBuf::from(path);
    }
    if let Some(home) = std::env::var_os("HOME") {
        return PathBuf::from(home).join(".local/share");
    }
    PathBuf::from(".")
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

struct StoreLock {
    path: PathBuf,
    pid: u32,
    token: String,
}

impl StoreLock {
    fn acquire(kcs_dir: &Path) -> Result<Self> {
        let path = kcs_dir.join(".lock");
        let pid = std::process::id();
        let token = new_lock_token(pid);

        for _ in 0..2 {
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => {
                    write_lock_file(&path, &mut file, pid, &token)?;
                    return Ok(Self { path, pid, token });
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
        if lock_file_matches(&self.path, self.pid, &self.token).unwrap_or(false) {
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
            std::thread::sleep(Duration::from_millis(ms));
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

fn new_ulid(path: &Path) -> String {
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

fn now_utc_seconds() -> String {
    if let Ok(value) = std::env::var("KCS_FIXED_NOW") {
        return value;
    }
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;
    format_unix_seconds(secs)
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
