//! Folder-scope repository operations for Step 1.

use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
#[cfg(any(unix, windows))]
use std::path::Component;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use unicode_normalization::UnicodeNormalization;

use crate::ExitCode;
#[cfg(unix)]
use crate::cas::lower_hex;
use crate::cas::{
    CAS_STREAM_BUFFER_BYTES, ContentObjectKind, MAX_RAW_OBJECT_BYTES, ObjectKind, ObjectStore,
    append_jsonl, atomic_overwrite, atomic_write, canonical_json_bytes, is_hash,
};
use crate::dag::{
    CommitObject, CommitStats, CommitType, DEFAULT_CHUNKING_MAX_CHARS, DEFAULT_CHUNKING_STRATEGY,
    NormalizeRef, TreeEntry, TreeObject, build_tree_with_chunking_config, chunking_config_hash,
    is_materializable_direct_child,
};
use crate::error::{IoResultExt, KioError, Result};
use crate::gc::{SnapshotAutoBinding, SnapshotAutoStateBinding};
use crate::portable::{
    PORTABLE_TAGS_DIRECTORY, portable_collision_key, portable_leaf_error, portable_tag_digest64,
    portable_tag_leaf,
};
use crate::purge::PurgeState;
use crate::schema::{SchemaKind, validate_json_schema};

/// Exact on-disk scope format understood by this pre-stable reader.
pub const KIO_FORMAT_VERSION: &str = "0.1.0";
pub const DEFAULT_MAX_ARCHIVE_FILE_BYTES: u64 = MAX_RAW_OBJECT_BYTES;
pub const DEFAULT_MAX_ARCHIVE_SCOPE_BYTES: u64 = 4 * 1024 * 1024 * 1024;
pub use crate::dag::{MAX_COMMIT_PARENTS, MAX_TREE_ENTRIES};
const MAX_TAG_REF_BYTES: u64 = 128;
/// The bound-child bootstrap accepts a complete config document only long
/// enough to preserve normal scope policy while it adds the generated parent
/// envelope.  Keeping this finite prevents a retained descriptor from turning
/// into an unbounded parser/allocation sink before regular repository limits
/// take over.
#[cfg(unix)]
const MAX_BOUND_CONFIG_BYTES: u64 = 1024 * 1024;

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
    /// Bound-child candidates are re-opened relative to this retained scope
    /// directory. `path` remains diagnostic-only in that mode.
    #[cfg(unix)]
    bound_root: Option<Arc<File>>,
}

#[derive(Debug)]
struct StagedWorkingFile {
    candidate: WorkingFileCandidate,
    temp_path: PathBuf,
    file: File,
    raw_hash: String,
    size_bytes: u64,
}

impl Drop for StagedWorkingFile {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.temp_path);
    }
}

#[derive(Debug, Clone)]
pub struct Repository {
    root: PathBuf,
    /// Stable public scope identity. Ordinary repositories use the same path
    /// as `root`; bound child indexing keeps it separate from operational I/O.
    canonical_root: PathBuf,
    kio_dir: PathBuf,
    store: ObjectStore,
    /// Retained descriptors used only by an internal child-index process.
    ///
    /// A bound child changes cwd to `bound_kio`, so every operational store
    /// path is relative to the opened directory rather than the replaceable
    /// public `.kio` entry.  Source-file operations use `bound_root` through
    /// capability APIs; callers must not reconstruct a public parent path.
    bound_root: Option<Arc<File>>,
    bound_kio: Option<Arc<File>>,
}

#[derive(Debug, Clone)]
pub struct WorkingTree {
    pub tree: TreeObject,
}

#[derive(Debug, Clone, Serialize)]
pub struct FileStatus {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<PathBuf>,
    pub relative_path: String,
    /// The working-tree-vs-HEAD classification (`new`/`modified`/`deleted`/
    /// `unchanged`). R15-4: `None` (field omitted) when HEAD is shallow — the prior
    /// tree needed to classify is gone, so a pure `kio status` degrades to listing
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
/// scope stays inspectable instead of bricking on a raw `KIO-E-STORE-NOT-FOUND-001`.
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
/// `KIO-E-STORE-NOT-FOUND-001`. The omission is always explicit, never silent.
#[derive(Debug, Clone, Serialize)]
pub struct LogReport {
    pub entries: Vec<LogEntry>,
    pub truncated: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct DiffEntry {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<PathBuf>,
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
            return Err(KioError::invalid_usage("init path does not exist"));
        }
        if !root.is_dir() {
            return Err(KioError::invalid_usage("init path must be a directory"));
        }

        let root = root.canonicalize().kio_io(root)?;
        let kio_dir = root.join(".kio");
        match fs::symlink_metadata(&kio_dir) {
            Ok(_) => return Self::open(root),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(KioError::io(
                    error.to_string(),
                    kio_dir.display().to_string(),
                ));
            }
        }

        for dir in [
            kio_dir.join("objects/raw"),
            kio_dir.join("objects/trees"),
            kio_dir.join("objects/commits"),
            kio_dir.join("refs/heads"),
            kio_dir.join("refs").join(PORTABLE_TAGS_DIRECTORY),
            kio_dir.join("logs"),
        ] {
            fs::create_dir_all(&dir).kio_io(&dir)?;
        }

        // P2: restrict the `.kio` tree to the owner (0700). objects/raw holds the
        // verbatim document bytes (secrets included, even unclassified ones), and
        // approvals/tasks/quarantine logs plus sqlite.db carry actor names and
        // usage patterns — none of it should be world/group-readable on a
        // multi-user host (07 §1 secrecy posture). A 0700 parent blocks traversal
        // into the whole subtree regardless of child file modes; no-op on non-unix.
        restrict_dir_to_owner(&kio_dir)?;

        atomic_write(&kio_dir.join("HEAD"), b"")?;
        atomic_write(&kio_dir.join("refs/heads/main"), b"")?;
        // 裁定2 (step4b-contract-tests-p3b.md §Z2): `kio_format_version` is a
        // scope.json-only concept (03 §2 L154) — config.toml no longer
        // carries a redundant copy. An empty config.toml is a valid, fully
        // default configuration under `config.schema.json` (no required
        // keys).
        atomic_write(&kio_dir.join("config.toml"), b"")?;
        atomic_write(
            &kio_dir.join("scope.json"),
            serde_json::to_string_pretty(&json!({
                "kio_format_version": KIO_FORMAT_VERSION,
                "scope_id": new_ulid(&root),
                "scope_path": root,
            }))
            .map_err(|err| KioError::schema(err.to_string()))?
            .as_bytes(),
        )?;
        atomic_write(
            &kio_dir.join("manifest.json"),
            b"{\n  \"schema_version\": 1,\n  \"files\": []\n}\n",
        )?;
        atomic_write(
            &kio_dir.join("tool-lock.json"),
            b"{\n  \"spec_version\": 1\n}\n",
        )?;

        Self::open(root)
    }

    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let repo = Self::open_without_head_repair(path)?;
        // R13-4: repair a corrupt (empty/missing) HEAD from refs/heads/main before
        // any command reads or advances HEAD. Done on every ordinary `open` so
        // `log`/`status` display the real history and `snapshot` extends it.
        repo.self_heal_head()?;
        Ok(repo)
    }

    /// Validate and open a repository without performing HEAD self-healing.
    /// Mutating repair commands use this to acquire `.kio/.lock` before invoking
    /// [`Self::self_heal_head_for_repair`].
    pub fn open_without_head_repair(path: impl AsRef<Path>) -> Result<Self> {
        let root = path.as_ref().canonicalize().kio_io(path.as_ref())?;
        let kio_dir = root.join(".kio");
        validate_store_directory(&kio_dir)?;

        let repo = Self {
            canonical_root: root.clone(),
            root,
            kio_dir: kio_dir.clone(),
            store: ObjectStore::new(kio_dir),
            bound_root: None,
            bound_kio: None,
        };
        repo.validate()?;
        Ok(repo)
    }

    pub fn open_current() -> Result<Self> {
        let cwd = std::env::current_dir().map_err(|err| KioError::io(err.to_string(), "."))?;
        Self::open(cwd)
    }

    pub fn open_current_without_head_repair() -> Result<Self> {
        let cwd = std::env::current_dir().map_err(|err| KioError::io(err.to_string(), "."))?;
        Self::open_without_head_repair(cwd)
    }

    /// Initialize/open a child scope after the caller bound this process cwd to
    /// a retained child descriptor. Public child paths are intentionally not
    /// consulted for operational I/O. The process remains in the retained
    /// child directory: operational paths are `.` / `.kio`, never `..`.
    #[cfg(unix)]
    pub fn init_bound_current(canonical_root: PathBuf) -> Result<Self> {
        Self::init_bound_current_with_generated_parent_policy(canonical_root, None)
    }

    /// Initialize/open a descriptor-bound child scope and persist the strict
    /// parent policy while the `.kio` directory is still addressed solely by
    /// its retained no-follow handle.  The caller must have parsed the policy
    /// before crossing the process boundary; this method deliberately accepts
    /// a generic TOML value to keep `kio-core` independent of pipeline types.
    #[cfg(unix)]
    pub fn init_bound_current_with_generated_parent_policy(
        canonical_root: PathBuf,
        generated_parent_policy: Option<toml::Value>,
    ) -> Result<Self> {
        use cap_primitives::{ambient_authority, fs as cap_fs};
        let scope = cap_fs::open_ambient_dir(Path::new("."), ambient_authority())
            .map_err(|err| KioError::io(err.to_string(), "."))?;
        let (kio, newly_created) = match cap_fs::open_dir_nofollow(&scope, Path::new(".kio")) {
            Ok(handle) => (handle, false),
            Err(_) => match cap_fs::stat(&scope, Path::new(".kio"), cap_fs::FollowSymlinks::No) {
                Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
                    let mut options = cap_fs::DirOptions::new();
                    use cap_fs::DirBuilderExt;
                    options.mode(0o700);
                    match cap_fs::create_dir(&scope, Path::new(".kio"), &options) {
                        Ok(()) => {}
                        Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {}
                        Err(err) => return Err(KioError::io(err.to_string(), ".kio")),
                    }
                    (
                        cap_fs::open_dir_nofollow(&scope, Path::new(".kio"))
                            .map_err(|err| KioError::io(err.to_string(), ".kio"))?,
                        true,
                    )
                }
                Ok(_) => return Err(KioError::invalid_usage(".kio must be a real directory")),
                Err(err) => return Err(KioError::io(err.to_string(), ".kio")),
            },
        };
        if newly_created {
            initialize_bound_kio_layout(&kio, &canonical_root)?;
        }
        if let Some(policy) = generated_parent_policy {
            persist_bound_generated_parent_policy(&kio, policy)?;
        }
        // `.kio` was opened with no-follow immediately above. Move the child
        // process into that retained directory *before* constructing the
        // repository. All existing store operations then address `.` and stay
        // on the opened inode even if a same-UID process replaces the public
        // `.kio` entry. Source access is kept separate through `bound_root`.
        use std::os::fd::AsRawFd;
        let kio_cwd = open_bound_directory_for_io(&kio, Path::new(".kio"))?;
        if unsafe { libc::fchdir(kio_cwd.as_raw_fd()) } != 0 {
            return Err(KioError::io(
                std::io::Error::last_os_error().to_string(),
                ".kio",
            ));
        }
        let repo = Self {
            root: PathBuf::from("."),
            canonical_root,
            kio_dir: PathBuf::from("."),
            store: ObjectStore::from_bound_kio(&kio)?,
            bound_root: Some(Arc::new(scope)),
            bound_kio: Some(Arc::new(kio)),
        };
        // Do not flatten schema/version/store errors into generic I/O here:
        // the parent must retain the child error's typed exit semantics.
        repo.validate()?;
        repo.self_heal_head()?;
        Ok(repo)
    }

    #[cfg(windows)]
    pub fn init_bound_current(canonical_root: PathBuf) -> Result<Self> {
        let mut repo = Self::init(Path::new("."))?;
        repo.canonical_root = canonical_root;
        Ok(repo)
    }

    /// Enter an already-initialized repository through retained scope and
    /// `.kio` capabilities. This is the scheduler counterpart to the bound
    /// child-index constructor: after the caller owns the descriptor-relative
    /// store lock, every store path is resolved from the retained `.kio`
    /// directory and every working-file read is resolved from `scope`.
    ///
    /// This changes the process working directory and is therefore intended
    /// only for a dedicated CLI process immediately before its terminal
    /// publication phase.
    #[cfg(unix)]
    pub fn open_bound_existing(canonical_root: PathBuf, scope: File, kio: File) -> Result<Self> {
        use cap_primitives::fs as cap_fs;
        use cap_primitives::fs::MetadataExt;
        use std::os::fd::AsRawFd;

        let named = cap_fs::stat(&scope, Path::new(".kio"), cap_fs::FollowSymlinks::No)
            .map_err(|error| KioError::io(error.to_string(), ".kio"))?;
        let retained = cap_fs::Metadata::from_file(&kio)
            .map_err(|error| KioError::io(error.to_string(), ".kio"))?;
        if !named.is_dir()
            || !retained.is_dir()
            || named.dev() != retained.dev()
            || named.ino() != retained.ino()
        {
            return Err(unsafe_store_error(
                Path::new(".kio"),
                "retained .kio capability no longer matches the selected scope",
            ));
        }
        // SAFETY: `kio` is a retained, no-follow directory descriptor verified
        // above and remains owned by the repository for its full lifetime.
        let kio_cwd = open_bound_directory_for_io(&kio, Path::new(".kio"))?;
        if unsafe { libc::fchdir(kio_cwd.as_raw_fd()) } != 0 {
            return Err(KioError::io(
                std::io::Error::last_os_error().to_string(),
                ".kio",
            ));
        }
        let repo = Self {
            root: PathBuf::from("."),
            canonical_root,
            kio_dir: PathBuf::from("."),
            store: ObjectStore::from_bound_kio(&kio)?,
            bound_root: Some(Arc::new(scope)),
            bound_kio: Some(Arc::new(kio)),
        };
        // Test-only seam: at this point ObjectStore has retained no-follow
        // handles for objects/{raw,trees,commits}, while no scheduled source
        // staging or CAS write has started.  A replacement of the public
        // descendants here must not redirect this repository.
        wait_at_bound_snapshot_auto_layout_barrier();
        repo.validate()?;
        Ok(repo)
    }

    #[cfg(not(unix))]
    pub fn open_bound_existing(_: PathBuf, _: File, _: File) -> Result<Self> {
        Err(KioError::new(
            "KIO-E-SNAPSHOT-PLATFORM-UNSUPPORTED-001",
            "scheduled snapshot mutation requires retained repository capabilities",
            json!({}),
            ExitCode::PermanentFailure,
        ))
    }

    /// Perform the established HEAD self-heal after a repair command has
    /// acquired the scope store lock. The lock is process-reentrant.
    pub fn self_heal_head_for_repair(&self) -> Result<()> {
        self.self_heal_head().map(|_| ())
    }

    /// Open a scope for immutable CAS/index search while treating
    /// `manifest.json` as a derived acceleration artifact. Search history is
    /// committed tree truth, so a malformed mutable manifest must not invalidate a
    /// signed cursor replay. Config, scope identity, store directory, and HEAD are
    /// validated exactly as in [`Self::open`].
    pub fn open_for_search(path: impl AsRef<Path>) -> Result<Self> {
        let root = path.as_ref().canonicalize().kio_io(path.as_ref())?;
        let kio_dir = root.join(".kio");
        validate_store_directory(&kio_dir)?;
        let repo = Self {
            canonical_root: root.clone(),
            root,
            kio_dir: kio_dir.clone(),
            store: ObjectStore::new(kio_dir),
            bound_root: None,
            bound_kio: None,
        };
        repo.validate_config()?;
        repo.validate_scope()?;
        repo.self_heal_head()?;
        Ok(repo)
    }

    /// The read-only counterpart to [`Self::open_for_search`]. It validates the
    /// same immutable store and scope state but never repairs HEAD or refs.
    pub fn open_for_search_without_head_repair(path: impl AsRef<Path>) -> Result<Self> {
        let root = path.as_ref().canonicalize().kio_io(path.as_ref())?;
        let kio_dir = root.join(".kio");
        validate_store_directory(&kio_dir)?;
        let repo = Self {
            canonical_root: root.clone(),
            root,
            kio_dir: kio_dir.clone(),
            store: ObjectStore::new(kio_dir),
            bound_root: None,
            bound_kio: None,
        };
        repo.validate_config()?;
        repo.validate_scope()?;
        Ok(repo)
    }

    pub fn open_current_for_search() -> Result<Self> {
        let cwd = std::env::current_dir().map_err(|err| KioError::io(err.to_string(), "."))?;
        Self::open_for_search(cwd)
    }

    #[must_use]
    pub fn root(&self) -> &Path {
        &self.root
    }

    #[must_use]
    pub fn canonical_root(&self) -> &Path {
        &self.canonical_root
    }

    #[must_use]
    pub fn kio_dir(&self) -> &Path {
        &self.kio_dir
    }

    /// Retained scope-root descriptor for an internal descriptor-bound child
    /// index process. It is deliberately absent for ordinary public-path
    /// repositories.
    #[cfg(unix)]
    #[must_use]
    pub fn bound_root_handle(&self) -> Option<&File> {
        self.bound_root.as_deref()
    }

    /// Retained `.kio` descriptor for an internal descriptor-bound child index
    /// process. Operational store paths are relative to this directory.
    #[cfg(unix)]
    #[must_use]
    pub fn bound_kio_handle(&self) -> Option<&File> {
        self.bound_kio.as_deref()
    }

    /// Enumerate the commit targets named by every current on-disk ref.
    ///
    /// This is deliberately a filesystem-validation boundary rather than a
    /// convenience wrapper around `HEAD`: repair must be able to reconstruct
    /// projections for history retained solely by a branch or a tag.  The
    /// returned hashes are not dereferenced here; [`HistoryReader`] owns the
    /// subsequent strict commit/tree walk and reports a shallow object with its
    /// precise object cause.
    pub fn current_ref_targets(&self) -> Result<BTreeSet<String>> {
        let mut targets = BTreeSet::new();
        let head = read_commit_ref(&self.kio_dir.join("HEAD"), true)?;
        if let Some(hash) = head {
            targets.insert(hash);
        }

        let refs = self.kio_dir.join("refs");
        collect_branch_ref_targets(&refs.join("heads"), &mut targets)?;
        collect_tag_ref_targets(&refs.join(PORTABLE_TAGS_DIRECTORY), &mut targets)?;
        Ok(targets)
    }

    /// QA5 (step4b-contract-tests-p3a.md §B, 10 §1 L97-113): record the
    /// one-time scope-level scan approval into `.kio/scope.json`'s
    /// `scan_approval` key — distinct from the adapter-level network opt-in
    /// (`approvals.jsonl`/`consents.jsonl`, 07 §3). Idempotent: a scope is
    /// approved once, so an existing `scan_approval` key is left untouched
    /// (`Ok(false)`); the first call materializes it (`Ok(true)`). `fields`
    /// must be a JSON object shaped per 10 §1 L101-113 (scope_id / root_path /
    /// approved_at / actor / approval_method / kio_version /
    /// effective_ignore_hash / estimated_file_count / estimated_total_bytes /
    /// estimated_markdownize_usd / estimated_embedding_usd).
    pub fn record_scan_approval(&self, fields: Value) -> Result<bool> {
        let path = self.kio_dir.join("scope.json");
        let mut value: Value = serde_json::from_str(&fs::read_to_string(&path).kio_io(&path)?)
            .map_err(|err| KioError::schema(err.to_string()))?;
        let Some(object) = value.as_object_mut() else {
            return Err(KioError::schema("scope.json must be an object"));
        };
        if object.contains_key("scan_approval") {
            return Ok(false);
        }
        object.insert("scan_approval".to_owned(), fields);
        validate_json_schema(SchemaKind::Scope, &value)?;
        // `atomic_write` is CAS-only semantics (a no-op when `path` already
        // exists, R9-8) — wrong here since `scope.json` already exists from
        // `Repository::init` and this call must actually replace its
        // content. `atomic_overwrite` is the mutable-file primitive already
        // used for HEAD/manifest.json elsewhere in this file.
        atomic_overwrite(
            &path,
            serde_json::to_string_pretty(&value)
                .map_err(|err| KioError::schema(err.to_string()))?
                .as_bytes(),
        )?;
        Ok(true)
    }

    /// Return the portable scope ID together with the canonical local root.
    /// Authorization callers must bind both values to protected device-local
    /// state; `scope.json` alone is portable audit data, not active consent.
    pub fn scope_identity(&self) -> Result<ScopeIdentity> {
        validate_store_directory(&self.kio_dir)?;
        Ok(ScopeIdentity {
            scope_id: self.validated_scope_id()?,
            canonical_root: self.canonical_root.clone(),
        })
    }

    /// Acquire the exclusive `.kio/.lock` store lock (05 §6) and return an RAII
    /// guard held for the caller's lifetime. Used to serialize whole mutating
    /// commands (`kio index` / `repair` / `reindex`) end-to-end, not just their
    /// snapshot sub-step. The lock is reentrant within a single process, so a
    /// held guard does not deadlock when `snapshot` re-acquires it internally.
    /// The loser of a concurrent acquisition gets `KIO-E-STORE-LOCKED-001`
    /// (exit 3), the same contract as `snapshot` / `tag`.
    pub fn lock_store(&self) -> Result<StoreLock> {
        StoreLock::acquire(&self.kio_dir)
    }

    pub fn validate(&self) -> Result<()> {
        validate_store_directory(&self.kio_dir)?;
        self.validate_config()?;
        self.validate_scope()?;
        self.validate_manifest()?;
        Ok(())
    }

    /// Replace the scope configuration only after the same schema and semantic
    /// checks used by [`Self::validate`].  Internal child indexing uses this to
    /// persist the ancestor-derived ignore policy before any scan or task can
    /// observe the child scope.  Callers must provide the complete document so
    /// unrelated child-local configuration is retained deliberately.
    pub fn replace_config_value(&self, value: toml::Value) -> Result<()> {
        let json_value =
            serde_json::to_value(&value).map_err(|err| KioError::schema(err.to_string()))?;
        validate_json_schema(SchemaKind::Config, &json_value)?;
        enforce_config_semantics(&json_value)?;
        let text = toml::to_string(&value).map_err(|err| KioError::schema(err.to_string()))?;
        #[cfg(unix)]
        if let Some(kio) = self.bound_kio.as_deref() {
            return replace_bound_regular_file(kio, "config.toml", text.as_bytes());
        }
        atomic_overwrite(&self.kio_dir.join("config.toml"), text.as_bytes())
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
            return Err(KioError::invalid_usage(
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
            return Err(KioError::invalid_usage(
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
            return Err(KioError::invalid_usage(
                "archive max_file_bytes exceeds the raw CAS object limit",
            ));
        }
        let chunking_config_hash = self.effective_chunking_config_hash()?;

        let candidates = self.working_file_candidates(
            excluded_paths,
            explicitly_allowed_tier_a_paths,
            store_raw,
            limits,
        )?;
        if store_raw {
            // Raw publication and erase-receipt retirement are one store-locked
            // operation even for direct callers of this public builder. Snapshot
            // callers already hold this reentrant lock.
            let _lock = StoreLock::acquire(&self.kio_dir)?;
            // Every caller of this public builder except `snapshot_with_type`'s
            // purge path is a non-purge write (`purge_self_targets` empty —
            // see `archive_staged_working_tree`'s doc comment): the barrier
            // applies unconditionally here, as it always has.
            return self.archive_staged_working_tree(
                candidates,
                normalize_by_path,
                limits,
                &BTreeSet::new(),
                None,
                None,
                None,
                &chunking_config_hash,
            );
        }
        let mut entries = Vec::new();
        let mut consumed_scope_bytes = 0_u64;
        for candidate in candidates {
            let mut file = open_working_file_candidate(&candidate)?;
            let metadata = file.metadata().kio_io(&candidate.path)?;
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
            let (raw_hash, consumed) = hash_scope_file(
                &mut file,
                &candidate.path,
                &candidate.file_name,
                allowed,
                limits,
            )?;
            if file.metadata().kio_io(&candidate.path)?.len() != consumed {
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
            tree: build_tree_with_chunking_config(entries, chunking_config_hash)?,
        })
    }

    #[allow(clippy::too_many_arguments)]
    fn archive_staged_working_tree(
        &self,
        candidates: Vec<WorkingFileCandidate>,
        normalize_by_path: &BTreeMap<String, PendingNormalizeRef>,
        limits: ArchiveLimits,
        purge_self_targets: &BTreeSet<String>,
        expected_raw_by_path: Option<&BTreeMap<String, String>>,
        expected_direct_entries: Option<&BTreeSet<String>>,
        expected_snapshot_policy: Option<&SnapshotAutoBinding>,
        chunking_config_hash: &str,
    ) -> Result<WorkingTree> {
        #[cfg(not(unix))]
        let _ = expected_snapshot_policy;
        let scheduled_bound = expected_raw_by_path.is_some() && {
            #[cfg(unix)]
            {
                self.bound_kio.is_some()
            }
            #[cfg(not(unix))]
            {
                false
            }
        };
        #[cfg(unix)]
        if scheduled_bound {
            // Recover only canonical private stages through the retained raw
            // descriptor before allocating new ones.  This is bounded and
            // validates every recognized residue; no public descendant path
            // is followed.
            self.store.cleanup_bound_raw_stages()?;
            let mut staged = Vec::with_capacity(candidates.len());
            let mut consumed_scope_bytes = 0_u64;
            for candidate in candidates {
                let remaining = limits
                    .max_scope_bytes
                    .checked_sub(consumed_scope_bytes)
                    .ok_or_else(|| scope_input_oversized(&candidate.file_name, limits, u64::MAX))?;
                let allowed = limits.max_file_bytes.min(remaining);
                let mut source = open_working_file_candidate(&candidate)?;
                let before = source.metadata().kio_io(&candidate.path)?;
                if before.len() > allowed {
                    return Err(scope_input_oversized(
                        &candidate.file_name,
                        limits,
                        before.len(),
                    ));
                }
                let stage = self.store.stage_raw_from_reader(&mut source, allowed)?;
                let after = source.metadata().kio_io(&candidate.path)?;
                use std::os::unix::fs::MetadataExt as _;
                if after.len() != stage.size_bytes()
                    || before.len() != after.len()
                    || before.dev() != after.dev()
                    || before.ino() != after.ino()
                {
                    return Err(scope_file_changed(&candidate.file_name));
                }
                consumed_scope_bytes = consumed_scope_bytes
                    .checked_add(stage.size_bytes())
                    .ok_or_else(|| scope_input_oversized(&candidate.file_name, limits, u64::MAX))?;
                staged.push((candidate, source, before, stage));
            }
            let actual = staged
                .iter()
                .map(|(file, _, _, stage)| (file.file_name.clone(), stage.raw_hash().to_owned()))
                .collect::<BTreeMap<_, _>>();
            if Some(&actual) != expected_raw_by_path {
                return Err(snapshot_authority_changed(
                    "scheduled snapshot inputs changed before publication",
                ));
            }
            if self.bound_snapshot_auto_direct_entries()?
                != *expected_direct_entries.expect("scheduled expected entries")
            {
                return Err(snapshot_authority_changed(
                    "scheduled snapshot direct entries changed before CAS publication",
                ));
            }
            // Identity and length are insufficient for an in-place same-size
            // edit. Re-hash each still-open, no-follow source descriptor after
            // the final namespace check and before the first CAS publication.
            for (candidate, source, before, stage) in &mut staged {
                source.seek(SeekFrom::Start(0)).kio_io(&candidate.path)?;
                let (rehash, size) = hash_scope_file(
                    source,
                    &candidate.path,
                    &candidate.file_name,
                    limits.max_file_bytes,
                    limits,
                )?;
                let after = source.metadata().kio_io(&candidate.path)?;
                use std::os::unix::fs::MetadataExt as _;
                if rehash != stage.raw_hash()
                    || size != stage.size_bytes()
                    || after.len() != before.len()
                    || after.dev() != before.dev()
                    || after.ino() != before.ino()
                {
                    return Err(snapshot_authority_changed(
                        "scheduled snapshot source bytes changed before CAS publication",
                    ));
                }
            }
            self.store.validate_bound_layout()?;
            if let Some(policy) = expected_snapshot_policy {
                let scope = self.bound_root.as_deref().expect("scheduled bound root");
                let kio = self.bound_kio.as_deref().expect("scheduled bound kio");
                policy.recheck(scope, kio)?;
            }
            self.reject_scheduled_bound_purge_state()?;
            self.reject_scheduled_marker_targets(actual.values())?;
            let mut entries = Vec::with_capacity(staged.len());
            for (candidate, _, _, stage) in staged {
                let (published_hash, published_size) = self.store.publish_bound_raw_stage(stage)?;
                if published_size > limits.max_file_bytes {
                    return Err(scope_input_oversized(
                        &candidate.file_name,
                        limits,
                        published_size,
                    ));
                }
                let mut tree_entry =
                    TreeEntry::raw_file(candidate.file_name.clone(), published_hash)?;
                attach_pending_normalize(&mut tree_entry, &candidate.file_name, normalize_by_path);
                tree_entry.validate()?;
                entries.push(tree_entry);
            }
            return Ok(WorkingTree {
                tree: build_tree_with_chunking_config(entries, chunking_config_hash.to_owned())?,
            });
        }
        // The caller holds `.kio/.lock`, so no live Kio writer can own an
        // `.ingest-*` leaf. Remove crash-orphaned raw bytes before creating any
        // new staging file; otherwise a tombstoned re-ingest killed before its
        // authorization check could remain in KIO-managed storage indefinitely.
        // Scheduled publication has retained object descriptors but must not
        // follow the ordinary path-based crash-temp scavenger: a same-UID
        // descendant replacement must be a fail-closed no-op, never a cleanup
        // of the replacement target. Its bound ObjectStore owns raw CAS writes.
        if !scheduled_bound {
            cleanup_orphan_raw_ingest_temps(&self.kio_dir)?;
        }
        let mut staged = Vec::with_capacity(candidates.len());
        let mut consumed_scope_bytes = 0_u64;
        for candidate in candidates {
            let remaining = limits
                .max_scope_bytes
                .checked_sub(consumed_scope_bytes)
                .ok_or_else(|| scope_input_oversized(&candidate.file_name, limits, u64::MAX))?;
            let allowed = limits.max_file_bytes.min(remaining);
            let staged_file = stage_scope_file(&self.kio_dir, candidate, allowed, limits)?;
            consumed_scope_bytes = consumed_scope_bytes
                .checked_add(staged_file.size_bytes)
                .ok_or_else(|| {
                    scope_input_oversized(&staged_file.candidate.file_name, limits, u64::MAX)
                })?;
            staged.push(staged_file);
        }

        // A scheduled decision is authorized by a descriptor-bound raw-hash
        // preview.  Compare that exact path/hash set after every source has
        // been copied into private staging files but before the first CAS
        // publication.  An editor changing, adding, deleting, or renaming a
        // file in the final observation-to-publication window therefore
        // causes a retryable failure instead of a commit with a stale report.
        if let Some(expected) = expected_raw_by_path {
            let actual = staged
                .iter()
                .map(|file| (file.candidate.file_name.clone(), file.raw_hash.clone()))
                .collect::<BTreeMap<_, _>>();
            if &actual != expected {
                drop(staged);
                if !scheduled_bound {
                    let raw_dir = self.kio_dir.join("objects/raw");
                    crate::purge::sync_directory(&raw_dir).kio_io(&raw_dir)?;
                }
                return Err(KioError::new(
                    "KIO-E-SNAPSHOT-AUTHORITY-CHANGED-001",
                    "scheduled snapshot inputs changed before publication",
                    json!({}),
                    ExitCode::PartialFailure,
                ));
            }
        }
        if let Some(expected) = expected_direct_entries
            && self.bound_snapshot_auto_direct_entries()? != *expected
        {
            drop(staged);
            if !scheduled_bound {
                let raw_dir = self.kio_dir.join("objects/raw");
                crate::purge::sync_directory(&raw_dir).kio_io(&raw_dir)?;
            }
            return Err(snapshot_authority_changed(
                "scheduled snapshot direct entries changed before CAS publication",
            ));
        }

        // Discover every candidate barrier before the first raw CAS publication.
        // Thus a later path carrying an incomplete-purge identity cannot leave
        // earlier, otherwise-valid candidates partially archived. A public
        // tombstone or fsck-only erase receipt no longer blocks publication
        // (U19/LC22: the permanent re-ingest rejection is reversed into a
        // resurrection flow) — only an active purge journal barrier
        // (incomplete purge in progress) still gates ingest here.
        //
        // P2-A finding / 05 §3.5 L741 ("working tree の原本には触れない"):
        // `purge_self_targets` is non-empty ONLY when this call is itself
        // `Repository::purged_snapshot`'s own working-tree rebuild (the sole
        // producer — see its call site in `snapshot_with_type`), and its
        // members are exactly THIS journal's own `target_raw_hashes`. A
        // single `.kio` scope holds at most one active purge journal at a
        // time (the store lock this method's caller already holds
        // serializes purge with every other write), so any raw_hash this
        // barrier would block during a purge's own snapshot is necessarily
        // this same purge's own journal — never a foreign one. Purge
        // deliberately never deletes the working-tree original (05 §3.5),
        // so a residual copy of a purge target's exact bytes legitimately
        // reappears here on the SAME pass that is finalizing that target's
        // removal; treating it as a blocked *ingest* would wrongly fail the
        // purge's own completing commit. It is excluded below instead —
        // neither re-published to CAS nor added to the resulting tree — so
        // `commit_type=purged`'s tree never carries the entry it is purging
        // (matching `verify_purged_commit`'s postcondition), while every
        // OTHER (non-self) raw_hash still gets the barrier's full
        // protection. Re-ingestion of a residual original is deferred to
        // the next ordinary `kio index` (05 §3.5 L743), once no journal
        // remains to block it.
        if !scheduled_bound {
            let purge = PurgeState::new(&self.kio_dir);
            for file in &staged {
                if purge_self_targets.contains(&file.raw_hash) {
                    continue;
                }
                ensure_raw_publication_allowed(&purge, &file.raw_hash)?;
            }
        }

        let mut entries = Vec::with_capacity(staged.len());
        for mut staged_file in staged {
            if purge_self_targets.contains(&staged_file.raw_hash) {
                continue;
            }
            staged_file
                .file
                .seek(SeekFrom::Start(0))
                .kio_io(&staged_file.temp_path)?;
            let (published_hash, published_size) = self
                .store
                .write_raw_reader(&mut staged_file.file, staged_file.size_bytes)?;
            if published_hash != staged_file.raw_hash || published_size != staged_file.size_bytes {
                return Err(scope_file_changed(&staged_file.candidate.file_name));
            }
            let mut tree_entry =
                TreeEntry::raw_file(staged_file.candidate.file_name.clone(), published_hash)?;
            attach_pending_normalize(
                &mut tree_entry,
                &staged_file.candidate.file_name,
                normalize_by_path,
            );
            tree_entry.validate()?;
            entries.push(tree_entry);
        }
        Ok(WorkingTree {
            tree: build_tree_with_chunking_config(entries, chunking_config_hash.to_owned())?,
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
        #[cfg(unix)]
        if let Some(root) = &self.bound_root {
            use cap_primitives::fs as cap_fs;

            let entries = cap_fs::read_base_dir(root).map_err(|error| {
                KioError::io(error.to_string(), self.canonical_root.display().to_string())
            })?;
            for entry in entries {
                let entry = entry.map_err(|error| {
                    KioError::io(error.to_string(), self.canonical_root.display().to_string())
                })?;
                let file_name = match entry.file_name().into_string() {
                    Ok(name) => name,
                    Err(_) => continue,
                };
                if file_name == ".kio" {
                    continue;
                }
                let path = self.canonical_root.join(&file_name);
                let file_type = entry
                    .file_type()
                    .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?;
                if file_type.is_dir() {
                    continue;
                }
                if !file_type.is_file() {
                    eprintln!("warning: skipping non-regular file: {}", path.display());
                    continue;
                }
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
                let file = open_bound_scope_file_nofollow(root, &file_name, &path)?;
                let metadata = file.metadata().kio_io(&path)?;
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
                candidates.push(WorkingFileCandidate {
                    path,
                    file_name,
                    bound_root: Some(Arc::clone(root)),
                });
            }
            return Ok(candidates);
        }
        for entry in fs::read_dir(&self.root).kio_io(&self.root)? {
            let entry = entry.kio_io(&self.root)?;
            if entry.file_name() == ".kio" {
                continue;
            }
            let path = entry.path();
            let file_type = entry.file_type().kio_io(&path)?;
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
            let metadata = file.metadata().kio_io(&path)?;
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
            candidates.push(WorkingFileCandidate {
                path,
                file_name,
                #[cfg(unix)]
                bound_root: None,
            });
        }
        Ok(candidates)
    }

    pub fn status(&self) -> Result<StatusReport> {
        self.validate()?;
        let current = self.build_working_tree(false)?.tree;
        let current_map = tree_map(&current);
        // R15-4: a shallow HEAD (tree object discarded) must NOT brick a pure read.
        // Degrade to listing the current files without a classification instead of
        // propagating the raw KIO-E-STORE-NOT-FOUND-001 from `read_tree`.
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
                path: is_materializable_direct_child(&path).then(|| self.root.join(&path)),
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
            false,
            &[],
            true,
            None,
            None,
            None,
            None,
            None,
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
            return Err(KioError::invalid_usage(
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
            false,
            &[],
            true,
            None,
            None,
            None,
            None,
            None,
        )
    }

    #[cfg(unix)]
    fn bound_snapshot_auto_direct_entries(&self) -> Result<BTreeSet<String>> {
        let root = self.bound_root.as_deref().ok_or_else(|| {
            KioError::invalid_usage(
                "scheduled snapshot publication requires a retained scope capability",
            )
        })?;
        crate::gc::validated_snapshot_auto_direct_entries(root)
    }

    /// Validate the scheduler's immutable writer inputs through the retained
    /// `.kio` directory.  This deliberately has stricter semantics than the
    /// ordinary open path: an empty HEAD with a populated branch ref is
    /// corruption here, not an opportunity for automatic repair.
    #[cfg(unix)]
    fn validate_scheduled_auto_prerequisites(&self) -> Result<ScheduledSnapshotAuthority> {
        if self.bound_kio.is_none() {
            return Err(KioError::invalid_usage(
                "scheduled snapshot publication requires a retained .kio capability",
            ));
        }
        if self.bound_root.is_none() {
            return Err(KioError::invalid_usage(
                "scheduled snapshot publication requires a retained scope capability",
            ));
        }
        let authority = self.capture_scheduled_snapshot_authority()?;
        let head = authority.head.trim();
        let branch = authority.branch.trim();
        match (head.is_empty(), branch.is_empty()) {
            (true, true) => {}
            (true, false) => {
                return Err(snapshot_authority_changed(
                    "scheduled snapshot rejects an empty HEAD with a populated refs/heads/main",
                ));
            }
            (false, true) => {
                return Err(snapshot_authority_changed(
                    "scheduled snapshot rejects a populated HEAD with an empty refs/heads/main",
                ));
            }
            (false, false) if head != branch => {
                return Err(snapshot_authority_changed(
                    "scheduled snapshot rejects a HEAD/ref mismatch",
                ));
            }
            (false, false) => {}
        }
        if !head.is_empty() {
            if !is_hash(head) {
                return Err(KioError::schema("HEAD must contain a commit_hash"));
            }
            // Both objects are CAS-bound in this repository.  Do not permit a
            // scheduled writer to extend a shallow/corrupt history.
            let commit = self.read_commit(head)?;
            self.read_tree(&commit.tree)?;
        }
        self.reject_scheduled_bound_purge_state()?;
        Ok(authority)
    }

    /// Capture every mutable metadata leaf that selects the scheduled
    /// snapshot's parent and tool identity.  Values alone are not enough: a
    /// same-byte inode replacement is an authority change too.
    #[cfg(unix)]
    fn capture_scheduled_snapshot_authority(&self) -> Result<ScheduledSnapshotAuthority> {
        let kio = self.bound_kio.as_deref().ok_or_else(|| {
            KioError::invalid_usage("scheduled snapshot requires retained .kio capability")
        })?;
        let (head, head_observation) =
            read_bound_regular_text_observed_at(kio, "HEAD", MAX_BOUND_CONFIG_BYTES)?;
        wait_at_bound_snapshot_auto_barrier("KIO_TEST_SNAPSHOT_AUTO_AUTHORITY_CAPTURE_READY");
        let (branch, branch_observation) =
            read_bound_regular_text_observed_at(kio, "refs/heads/main", MAX_BOUND_CONFIG_BYTES)?;
        let (tool_lock, tool_lock_observation) =
            read_bound_regular_text_observed_at(kio, "tool-lock.json", MAX_BOUND_CONFIG_BYTES)?;
        let tool_lock_value: Value = serde_json::from_str(&tool_lock)
            .map_err(|error| KioError::schema(error.to_string()))?;
        canonical_tool_lock_value(&tool_lock_value)?;
        Ok(ScheduledSnapshotAuthority {
            head,
            branch,
            tool_lock,
            head_observation,
            branch_observation,
            tool_lock_observation,
        })
    }

    #[cfg(unix)]
    fn recheck_scheduled_snapshot_authority(
        &self,
        expected: &ScheduledSnapshotAuthority,
    ) -> Result<()> {
        let actual = self.capture_scheduled_snapshot_authority().map_err(|_| {
            snapshot_authority_changed("scheduled snapshot metadata authority changed")
        })?;
        if actual != *expected {
            return Err(snapshot_authority_changed(
                "scheduled snapshot HEAD, branch ref, or tool lock changed",
            ));
        }
        Ok(())
    }

    #[cfg(unix)]
    fn recheck_scheduled_published_authority(
        &self,
        expected: &ScheduledSnapshotAuthority,
        published: &ScheduledSnapshotAuthority,
        commit_hash: &str,
    ) -> Result<()> {
        let actual = self.capture_scheduled_snapshot_authority().map_err(|_| {
            snapshot_authority_changed("scheduled snapshot metadata authority changed")
        })?;
        if actual.head.trim() != commit_hash
            || actual.branch.trim() != commit_hash
            || actual.head_observation != published.head_observation
            || actual.branch_observation != published.branch_observation
            || actual.tool_lock != expected.tool_lock
            || actual.tool_lock_observation != expected.tool_lock_observation
        {
            return Err(snapshot_authority_changed(
                "scheduled snapshot refs or tool lock changed after publication",
            ));
        }
        Ok(())
    }

    #[cfg(not(unix))]
    fn capture_scheduled_snapshot_authority(&self) -> Result<ScheduledSnapshotAuthority> {
        Err(KioError::new(
            "KIO-E-SNAPSHOT-PLATFORM-UNSUPPORTED-001",
            "scheduled snapshot publication requires retained filesystem capabilities",
            json!({}),
            ExitCode::PermanentFailure,
        ))
    }

    #[cfg(not(unix))]
    fn recheck_scheduled_snapshot_authority(&self, _: &ScheduledSnapshotAuthority) -> Result<()> {
        unreachable!("scheduled snapshots are unsupported without descriptor capabilities")
    }

    #[cfg(not(unix))]
    fn recheck_scheduled_published_authority(
        &self,
        _: &ScheduledSnapshotAuthority,
        _: &ScheduledSnapshotAuthority,
        _: &str,
    ) -> Result<()> {
        unreachable!("scheduled snapshots are unsupported without descriptor capabilities")
    }

    #[cfg(not(unix))]
    fn validate_scheduled_auto_prerequisites(&self) -> Result<ScheduledSnapshotAuthority> {
        Err(KioError::new(
            "KIO-E-SNAPSHOT-PLATFORM-UNSUPPORTED-001",
            "scheduled snapshot publication requires retained filesystem capabilities",
            json!({}),
            ExitCode::PermanentFailure,
        ))
    }

    #[cfg(unix)]
    fn reject_scheduled_bound_purge_state(&self) -> Result<()> {
        use cap_primitives::fs as cap_fs;

        let kio = self.bound_kio.as_deref().expect("validated above");
        // A scheduled writer never drives purge recovery or marker retirement.
        // The parent directory may legitimately remain after completed recovery
        // because it contains the monotonic epoch; only the active journal is
        // the writer barrier.
        match cap_fs::open_dir_nofollow(kio, Path::new("purge")) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(KioError::io(error.to_string(), "purge")),
            Ok(purge) => match cap_fs::stat(
                &purge,
                Path::new("in-progress.json"),
                cap_fs::FollowSymlinks::No,
            ) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Ok(metadata) if metadata.is_file() => {
                    return Err(KioError::new(
                        "KIO-E-PURGE-INCOMPLETE-001",
                        "scheduled snapshot is blocked by an active purge journal",
                        json!({ "component": "snapshot_auto" }),
                        ExitCode::PartialFailure,
                    ));
                }
                Ok(_) => {
                    return Err(unsafe_store_error(
                        Path::new("purge/in-progress.json"),
                        "purge journal is not a regular file",
                    ));
                }
                Err(error) => {
                    return Err(KioError::io(error.to_string(), "purge/in-progress.json"));
                }
            },
        }
        Ok(())
    }

    #[cfg(not(unix))]
    fn reject_scheduled_bound_purge_state(&self) -> Result<()> {
        // Scheduled snapshots require descriptor-relative inspection of the
        // purge journal before any publication can occur. Do not emulate that
        // check with path-based operations on platforms without the retained
        // capability boundary.
        Err(KioError::new(
            "KIO-E-SNAPSHOT-PLATFORM-UNSUPPORTED-001",
            "scheduled snapshot publication requires retained filesystem capabilities",
            json!({}),
            ExitCode::PermanentFailure,
        ))
    }

    #[cfg(unix)]
    fn reject_scheduled_marker_targets<'a>(
        &self,
        raw_hashes: impl IntoIterator<Item = &'a String>,
    ) -> Result<()> {
        let kio = self.bound_kio.as_deref().ok_or_else(|| {
            KioError::invalid_usage("scheduled snapshot requires retained .kio capability")
        })?;
        for raw_hash in raw_hashes {
            for namespace in ["tombstones", "purge/erase-receipts"] {
                if bound_marker_exists(kio, namespace, raw_hash)? {
                    return Err(KioError::new(
                        "KIO-E-PURGE-INCOMPLETE-001",
                        "scheduled snapshot refuses a raw identity with an existing purge marker",
                        json!({ "component": "snapshot_auto" }),
                        ExitCode::PartialFailure,
                    ));
                }
            }
        }
        Ok(())
    }

    #[cfg(not(unix))]
    fn reject_scheduled_marker_targets<'a>(
        &self,
        _: impl IntoIterator<Item = &'a String>,
    ) -> Result<()> {
        Ok(())
    }

    #[cfg(unix)]
    fn publish_scheduled_bound_refs(&self, commit_hash: &str) -> Result<()> {
        let kio = self.bound_kio.as_deref().ok_or_else(|| {
            KioError::invalid_usage("scheduled snapshot requires retained .kio capability")
        })?;
        replace_bound_regular_file_at(kio, "refs/heads/main", commit_hash.as_bytes())?;
        replace_bound_regular_file_at(kio, "HEAD", commit_hash.as_bytes())
    }

    #[cfg(not(unix))]
    fn publish_scheduled_bound_refs(&self, _: &str) -> Result<()> {
        unreachable!("scheduled snapshots are unsupported without descriptor capabilities")
    }

    #[cfg(not(unix))]
    fn bound_snapshot_auto_direct_entries(&self) -> Result<BTreeSet<String>> {
        Err(KioError::new(
            "KIO-E-SNAPSHOT-PLATFORM-UNSUPPORTED-001",
            "scheduled snapshot publication requires retained filesystem capabilities",
            json!({}),
            ExitCode::PermanentFailure,
        ))
    }

    /// Scheduler-only auto snapshot. Historical normalization is carried only
    /// through a raw-hash-bound reference, never from a mutable cache.
    #[allow(clippy::too_many_arguments)]
    pub fn scheduled_auto_snapshot(
        &self,
        fixed_now: &str,
        excluded_paths: &BTreeSet<String>,
        explicitly_allowed_tier_a_paths: &BTreeSet<String>,
        expected_raw_by_path: &BTreeMap<String, String>,
        expected_direct_entries: &BTreeSet<String>,
        expected_snapshot_policy: &SnapshotAutoBinding,
        before_ref_publication: &mut dyn FnMut() -> Result<SnapshotAutoStateBinding>,
    ) -> Result<SnapshotOutcome> {
        // Freeze HEAD and its normalization references in the same writer
        // critical section as the eventual snapshot. Otherwise a concurrent
        // promotion on unchanged raw bytes could be replaced by the older
        // reference captured just before the nested snapshot lock.
        let _lock = StoreLock::acquire(&self.kio_dir)?;
        // This entrypoint is only valid for the retained-descriptor repository
        // constructed by the scheduler handoff.  In particular, do not apply
        // the ordinary empty-HEAD recovery here: a scheduled writer must never
        // turn a replaceable mutable ref into a new authority for publication.
        let scheduled_authority = self.validate_scheduled_auto_prerequisites()?;
        self.store.validate_bound_layout()?;
        expected_snapshot_policy.recheck(
            self.bound_root.as_deref().expect("scheduled bound root"),
            self.bound_kio.as_deref().expect("scheduled bound kio"),
        )?;
        self.reject_scheduled_marker_targets(expected_raw_by_path.values())?;
        if self.bound_snapshot_auto_direct_entries()? != *expected_direct_entries {
            return Err(snapshot_authority_changed(
                "scheduled snapshot direct entries changed before publication",
            ));
        }
        let mut normalize_by_path = BTreeMap::new();
        if !scheduled_authority.head.trim().is_empty() {
            let head = scheduled_authority.head.trim();
            let tree = self.read_tree(&self.read_commit(head)?.tree)?;
            for entry in tree.entries {
                if let Some(normalize) = entry.normalize {
                    normalize_by_path.insert(
                        entry.path.clone(),
                        PendingNormalizeRef {
                            expected_raw_hash: entry.raw_hash,
                            normalize,
                        },
                    );
                }
            }
        }
        self.snapshot_with_type(
            Some("scheduled auto snapshot"),
            Some(fixed_now),
            CommitType::Auto,
            excluded_paths,
            &normalize_by_path,
            explicitly_allowed_tier_a_paths,
            false,
            &[],
            true,
            Some(expected_raw_by_path),
            Some(expected_direct_entries),
            Some(expected_snapshot_policy),
            Some(&scheduled_authority),
            Some(before_ref_publication),
        )
    }

    /// Promote verified normalized identities on existing HEAD entries without
    /// snapshotting unrelated working-tree edits.
    ///
    /// The caller supplies content-bound references after validating the online
    /// result and current policy.  This boundary independently hashes the current
    /// working tree while holding the store lock and applies a reference only when
    /// both HEAD and the current file still equal `expected_raw_hash`.  A changed,
    /// deleted, or newly-created path is ignored.  Every unrelated HEAD entry is
    /// retained byte-for-byte, so one accepted online task cannot accidentally
    /// commit a sibling edit that happened while the task was deferred.
    pub fn promote_normalize_refs(
        &self,
        message: Option<&str>,
        normalize_by_path: &BTreeMap<String, PendingNormalizeRef>,
    ) -> Result<SnapshotOutcome> {
        self.promote_normalize_refs_with_tool_lock_hash(message, normalize_by_path, None)
    }

    /// Promotion variant used by a caller that has durably staged the next
    /// tool-lock and therefore needs the commit to attest that staged identity
    /// before the mutable live projection is published.
    pub fn promote_normalize_refs_with_staged_tool_lock(
        &self,
        message: Option<&str>,
        normalize_by_path: &BTreeMap<String, PendingNormalizeRef>,
        tool_lock_hash: &str,
    ) -> Result<SnapshotOutcome> {
        if !is_hash(tool_lock_hash) {
            return Err(KioError::schema(
                "staged promotion tool_lock_hash must be sha256 lowercase hex",
            ));
        }
        self.store
            .inspect_content_object(ContentObjectKind::Toollock, tool_lock_hash)
            .map_err(|_| {
                KioError::schema(
                    "staged promotion tool_lock_hash must name a published immutable tool-lock",
                )
            })?;
        self.promote_normalize_refs_with_tool_lock_hash(
            message,
            normalize_by_path,
            Some(tool_lock_hash),
        )
    }

    fn promote_normalize_refs_with_tool_lock_hash(
        &self,
        message: Option<&str>,
        normalize_by_path: &BTreeMap<String, PendingNormalizeRef>,
        staged_tool_lock_hash: Option<&str>,
    ) -> Result<SnapshotOutcome> {
        self.validate()?;
        let _lock = StoreLock::acquire(&self.kio_dir)?;
        let head_hash = self
            .head_commit_hash()?
            .ok_or_else(|| KioError::invalid_usage("cannot promote in an unborn scope"))?;
        let head_commit = self.read_commit(&head_hash).map_err(|error| {
            if is_store_not_found(&error) {
                KioError::commit_shallow(
                    "HEAD commit object is missing; online output was not promoted",
                    head_hash.clone(),
                )
            } else {
                error
            }
        })?;
        let prior_tree = match self.read_tree(&head_commit.tree) {
            Ok(tree) => tree,
            Err(error) if is_store_not_found(&error) => {
                crate::gc::validate_final_shallow_tree(
                    &self.kio_dir,
                    &head_hash,
                    &head_commit.tree,
                )?;
                return Err(KioError::commit_shallow(
                    "HEAD tree object is missing; online output was not promoted",
                    head_hash.clone(),
                ));
            }
            Err(error) => return Err(error),
        };
        let current = self.build_working_tree(false)?.tree;
        let current_raw = tree_map(&current);
        let purge = PurgeState::new(&self.kio_dir);
        let mut promoted_tree = prior_tree.clone();
        let mut changed = false;
        for entry in &mut promoted_tree.entries {
            let Some(pending) = normalize_by_path.get(&entry.path) else {
                continue;
            };
            let exact_current = current_raw
                .get(&entry.path)
                .is_some_and(|raw_hash| raw_hash == &pending.expected_raw_hash);
            if !exact_current || entry.raw_hash != pending.expected_raw_hash {
                continue;
            }
            ensure_raw_publication_allowed(&purge, &pending.expected_raw_hash)?;
            if entry.normalize.as_ref() != Some(&pending.normalize) {
                entry.normalize = Some(pending.normalize.clone());
                changed = true;
            }
        }
        promoted_tree.validate()?;
        let stats = commit_stats(Some(&prior_tree), &promoted_tree);
        if !changed {
            return Ok(SnapshotOutcome {
                noop: true,
                message: "promotion noop: bindings unchanged".to_owned(),
                tree_hash: head_commit.tree,
                commit_hash: None,
                commit: None,
                stats,
            });
        }

        let tree_value = serde_json::to_value(&promoted_tree)
            .map_err(|error| KioError::schema(error.to_string()))?;
        let (tree_hash, _) = self.store.write_json(ObjectKind::Tree, &tree_value)?;
        let created_at = fixed_now_override().unwrap_or_else(now_utc_seconds);
        let commit = CommitObject::new(
            tree_hash.clone(),
            vec![head_hash],
            created_at.clone(),
            message
                .map(str::to_owned)
                .unwrap_or_else(|| format!("online Markdownize promotion at {created_at}")),
            match staged_tool_lock_hash {
                Some(hash) => hash.to_owned(),
                None => self.publish_tool_lock()?,
            },
            stats.clone(),
            CommitType::Auto,
        )?;
        let commit_value =
            serde_json::to_value(&commit).map_err(|error| KioError::schema(error.to_string()))?;
        let (commit_hash, _) = self.store.write_json(ObjectKind::Commit, &commit_value)?;
        atomic_overwrite(
            &self.kio_dir.join("refs/heads/main"),
            commit_hash.as_bytes(),
        )?;
        atomic_overwrite(&self.kio_dir.join("HEAD"), commit_hash.as_bytes())?;
        self.write_manifest(&promoted_tree, Some(&prior_tree))?;
        Ok(SnapshotOutcome {
            noop: false,
            message: "online Markdownize promotion created".to_owned(),
            tree_hash,
            commit_hash: Some(commit_hash),
            commit: Some(commit),
            stats,
        })
    }

    /// Capture the purge-time working tree and force exactly one protected
    /// `commit_type=purged` child even when the tree equals HEAD. Unchanged
    /// files retain their existing normalize bindings; changed/new files do not
    /// inherit stale normalization metadata.
    ///
    /// `publish_ref=false` (05-runtime.md §3.5's `prepared` phase, LC48)
    /// computes and durably CAS-writes the commit object — fixing its hash as
    /// `planned_commit` — without publishing `refs/heads/main`/`HEAD` or
    /// running the resurrection-retire scan; the purge orchestration (this
    /// journal's `prepared` step) uses this to fix `planned_commit` before any
    /// tombstone/erase-receipt is durable. `publish_ref=true` (the journal's
    /// `committed` phase) re-derives the identical commit (deterministic,
    /// content-addressed — the store lock has been held across the whole
    /// operation so the working tree cannot have changed) and publishes it for
    /// real.
    pub fn purged_snapshot(
        &self,
        reason: &str,
        fixed_now: Option<&str>,
        purged_raws: &[String],
        publish_ref: bool,
    ) -> Result<SnapshotOutcome> {
        self.validate()?;
        let _lock = StoreLock::acquire(&self.kio_dir)?;
        let head = self
            .head_commit_hash()?
            .ok_or_else(|| KioError::invalid_usage("cannot purge an unborn scope"))?;
        let head_commit = self.read_commit(&head)?;
        let head_tree = self.read_tree(&head_commit.tree)?;
        let normalize_by_path = head_tree
            .entries
            .iter()
            .filter_map(|entry| {
                entry.normalize.clone().map(|normalize| {
                    (
                        entry.path.clone(),
                        PendingNormalizeRef {
                            expected_raw_hash: entry.raw_hash.clone(),
                            normalize,
                        },
                    )
                })
            })
            .collect::<BTreeMap<_, _>>();
        self.snapshot_with_type(
            Some(reason),
            fixed_now,
            CommitType::Purged,
            &BTreeSet::new(),
            &normalize_by_path,
            &BTreeSet::new(),
            true,
            purged_raws,
            publish_ref,
            None,
            None,
            None,
            None,
            None,
        )
    }

    /// Record a successful object repair without rescanning or changing the
    /// snapshot tree. The caller holds the store lock while restoring verified
    /// bytes; this method is reentrant and advances refs only after the repaired
    /// commit object is durable.
    pub fn record_repaired_commit(&self, message: Option<&str>) -> Result<String> {
        self.validate()?;
        let _lock = StoreLock::acquire(&self.kio_dir)?;
        let head = self
            .head_commit_hash()?
            .ok_or_else(|| KioError::invalid_usage("cannot record repair in an unborn scope"))?;
        let head_commit = self.read_commit(&head)?;
        // The tree itself must still be verified before a new commit refers to it.
        self.read_tree(&head_commit.tree)?;
        let created_at = now_utc_seconds();
        let commit = CommitObject::new(
            head_commit.tree,
            vec![head],
            created_at.clone(),
            message
                .map(str::to_owned)
                .unwrap_or_else(|| format!("object repair at {created_at}")),
            self.publish_tool_lock()?,
            CommitStats {
                files_added: 0,
                files_modified: 0,
                files_deleted: 0,
            },
            CommitType::Repaired,
        )?;
        let commit_value =
            serde_json::to_value(&commit).map_err(|error| KioError::schema(error.to_string()))?;
        let (commit_hash, _) = self.store.write_json(ObjectKind::Commit, &commit_value)?;
        atomic_overwrite(
            &self.kio_dir.join("refs/heads/main"),
            commit_hash.as_bytes(),
        )?;
        atomic_overwrite(&self.kio_dir.join("HEAD"), commit_hash.as_bytes())?;
        Ok(commit_hash)
    }

    #[allow(clippy::too_many_arguments)]
    fn snapshot_with_type(
        &self,
        message: Option<&str>,
        fixed_now: Option<&str>,
        commit_type: CommitType,
        excluded_paths: &BTreeSet<String>,
        normalize_by_path: &BTreeMap<String, PendingNormalizeRef>,
        explicitly_allowed_tier_a_paths: &BTreeSet<String>,
        force_commit: bool,
        purged_raws: &[String],
        publish_ref: bool,
        expected_raw_by_path: Option<&BTreeMap<String, String>>,
        expected_direct_entries: Option<&BTreeSet<String>>,
        expected_snapshot_policy: Option<&SnapshotAutoBinding>,
        expected_scheduled_authority: Option<&ScheduledSnapshotAuthority>,
        before_ref_publication: Option<&mut dyn FnMut() -> Result<SnapshotAutoStateBinding>>,
    ) -> Result<SnapshotOutcome> {
        // A retained repository is also used by the existing child-index
        // subprocess.  Bound descriptors plus `commit_type=auto` therefore do
        // not identify a scheduled publication by themselves.  The scheduler
        // is the only caller that supplies its validated authority binding.
        let scheduled_bound = expected_scheduled_authority.is_some();
        self.validate()?;
        let _lock = StoreLock::acquire(&self.kio_dir)?;
        maybe_hold_lock_for_tests();
        let chunking_config_hash = self.effective_chunking_config_hash()?;

        // Validate the base before archiving any working-tree bytes.  A normal
        // snapshot needs its parent tree to compute stats and write a coherent
        // manifest, so a missing tree is only acceptable when it is a *final*
        // receipt-backed shallow boundary.  Even then a new snapshot cannot
        // extend it.  Doing this before `archive_staged_working_tree` is
        // important: that routine writes raw/tree CAS objects as it captures
        // the working tree, and a rejected shallow base must not leave those
        // newly published objects behind.
        let head_hash = if let Some(authority) = expected_scheduled_authority {
            let head = authority.head.trim();
            if head.is_empty() {
                None
            } else {
                Some(head.to_owned())
            }
        } else {
            self.head_commit_hash()?
        };
        let head_commit = match head_hash.as_deref() {
            None => None,
            Some(hash) => match self.read_commit(hash) {
                Ok(commit) => Some(commit),
                Err(error) if is_store_not_found(&error) => {
                    return Err(KioError::commit_shallow(
                        "HEAD commit object is missing (shallow: discarded / corrupt); \
                         restore the commit object or re-create the scope before snapshotting",
                        hash.to_owned(),
                    ));
                }
                Err(error) => return Err(error),
            },
        };
        let head_tree_hash = head_commit.as_ref().map(|commit| commit.tree.clone());
        // Snapshot the prior HEAD tree before writing the candidate working
        // tree.  `validate_final_shallow_tree` distinguishes a canonical
        // final shallow boundary from a receiptless, mismatched, manual, or
        // currently-referenced missing tree (all corruption).  A valid final
        // boundary still cannot be used as a snapshot parent.
        let prior_tree = match head_tree_hash.as_deref() {
            None => None,
            Some(hash) => match self.read_tree(hash) {
                Ok(tree) => Some(tree),
                Err(error) if is_store_not_found(&error) => {
                    crate::gc::validate_final_shallow_tree(
                        &self.kio_dir,
                        head_hash.as_deref().unwrap_or_default(),
                        hash,
                    )?;
                    return Err(KioError::commit_shallow(
                        "HEAD commit is shallow (tree object discarded); \
                         restore the tree object or re-create the scope before snapshotting",
                        head_hash.clone().unwrap_or_default(),
                    ));
                }
                Err(error) => return Err(error),
            },
        };

        // P2-A finding (05 §3.5 L741, `archive_staged_working_tree`'s doc
        // comment): a `commit_type=purged` snapshot's own `purged_raws` are
        // self-owned targets, not a foreign barrier to respect — bypass the
        // public `build_working_tree_with_bound_normalize_and_limits`
        // wrapper (which always applies the barrier unconditionally) and
        // call the two lower-level steps directly so `purge_self_targets`
        // can be threaded through. Every other `commit_type` gets an empty
        // set here and this is exactly equivalent to the wrapper call it
        // replaces.
        let purge_self_targets: BTreeSet<String> = if commit_type == CommitType::Purged {
            purged_raws.iter().cloned().collect()
        } else {
            BTreeSet::new()
        };
        let working_candidates = self.working_file_candidates(
            excluded_paths,
            explicitly_allowed_tier_a_paths,
            true,
            ArchiveLimits::default(),
        )?;
        let working = {
            let _archive_lock = StoreLock::acquire(&self.kio_dir)?;
            self.archive_staged_working_tree(
                working_candidates,
                normalize_by_path,
                ArchiveLimits::default(),
                &purge_self_targets,
                expected_raw_by_path,
                expected_direct_entries,
                expected_snapshot_policy,
                &chunking_config_hash,
            )?
        }
        .tree;

        // U19/LC22-LC26: a raw_hash that is both (a) present in the tree we are
        // about to commit and (b) currently the target of an *active*
        // tombstone/erase-receipt is a resurrection candidate — raw CAS bytes
        // were just (re)published for it above (`build_working_tree_...`'s
        // `archive_staged_working_tree`, content-addressed and therefore
        // idempotent whether or not the object already existed). This purge
        // commit's own snapshot (`commit_type == Purged`) is excluded: its
        // own targets never even reach `working.entries` any more (the
        // `purge_self_targets` exclusion just above), so there is nothing of
        // this purge's own making to treat as resurrected, and no tombstone
        // for it exists yet at this point in the purge orchestration (the
        // `prepared`-phase dry run runs before either is durable) — the guard
        // stays defensive (keeps a mid-purge re-run of this method, e.g.
        // re-purge, from ever retiring the marker it is itself about to
        // create).
        let resurrection_candidates = if scheduled_bound || commit_type == CommitType::Purged {
            BTreeSet::new()
        } else {
            let purge = PurgeState::new(&self.kio_dir);
            let mut candidates = BTreeSet::new();
            for entry in &working.entries {
                let tombstoned = purge
                    .read_tombstone(&entry.raw_hash)?
                    .is_some_and(|record| record.is_active());
                let erased = purge
                    .read_erase_receipt(&entry.raw_hash)?
                    .is_some_and(|receipt| receipt.is_active());
                if tombstoned || erased {
                    candidates.insert(entry.raw_hash.clone());
                }
            }
            candidates
        };

        let tree_value =
            serde_json::to_value(&working).map_err(|err| KioError::schema(err.to_string()))?;
        let (tree_hash, _) = self.store.write_json(ObjectKind::Tree, &tree_value)?;
        let stats = commit_stats(prior_tree.as_ref(), &working);

        // A resurrection candidate forces a real commit even when the tree is
        // byte-identical to HEAD's (LC22-26): otherwise the raw bytes we just
        // republished into CAS above would have no distinguishing
        // `resurrection_commit` to retire the marker against, and the
        // tombstone/receipt would stay active indefinitely despite the raw
        // object being alive again.
        let (current_tool_lock_hash, current_tool_lock_bytes) = self.tool_lock_identity()?;
        if !force_commit
            && resurrection_candidates.is_empty()
            && head_tree_hash.as_deref() == Some(tree_hash.as_str())
            && head_commit
                .as_ref()
                .is_some_and(|commit| commit.tool_lock_hash == current_tool_lock_hash)
        {
            // Eligible no-ops have completed all immutable preparation at
            // this point. Publish their scheduler checkpoint before returning
            // so a failed state CAS can never follow an already-advanced ref.
            if scheduled_bound {
                wait_at_bound_snapshot_auto_pre_checkpoint_barrier();
                self.store.validate_bound_layout()?;
                if let Some(authority) = expected_scheduled_authority {
                    self.recheck_scheduled_snapshot_authority(authority)?;
                }
                if let Some(policy) = expected_snapshot_policy {
                    policy.recheck(
                        self.bound_root.as_deref().expect("scheduled bound root"),
                        self.bound_kio.as_deref().expect("scheduled bound kio"),
                    )?;
                }
                self.reject_scheduled_bound_purge_state()?;
                self.reject_scheduled_marker_targets(
                    working.entries.iter().map(|entry| &entry.raw_hash),
                )?;
            }
            if let Some(publish) = before_ref_publication {
                let checkpoint = publish()?;
                if scheduled_bound {
                    self.store.validate_bound_layout()?;
                    if let Some(policy) = expected_snapshot_policy {
                        policy.recheck(
                            self.bound_root.as_deref().expect("scheduled bound root"),
                            self.bound_kio.as_deref().expect("scheduled bound kio"),
                        )?;
                    }
                    checkpoint.recheck(self.bound_kio.as_deref().expect("scheduled bound kio"))?;
                    wait_at_bound_snapshot_auto_after_state_write_barrier();
                    self.store.validate_bound_layout()?;
                    if let Some(authority) = expected_scheduled_authority {
                        self.recheck_scheduled_snapshot_authority(authority)?;
                    }
                    if let Some(policy) = expected_snapshot_policy {
                        policy.recheck(
                            self.bound_root.as_deref().expect("scheduled bound root"),
                            self.bound_kio.as_deref().expect("scheduled bound kio"),
                        )?;
                    }
                    checkpoint.recheck(self.bound_kio.as_deref().expect("scheduled bound kio"))?;
                    self.reject_scheduled_bound_purge_state()?;
                    self.reject_scheduled_marker_targets(
                        working.entries.iter().map(|entry| &entry.raw_hash),
                    )?;
                }
            }
            return Ok(SnapshotOutcome {
                noop: true,
                message: "snapshot noop: tree unchanged".to_owned(),
                tree_hash,
                commit_hash: None,
                commit: None,
                stats,
            });
        }

        let published_tool_lock_hash = self
            .store
            .write_content_object(ContentObjectKind::Toollock, &current_tool_lock_bytes)?;
        if published_tool_lock_hash != current_tool_lock_hash {
            return Err(KioError::schema(
                "published immutable tool-lock hash differs from snapshot authority",
            ));
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
        let commit = if commit_type == CommitType::Purged {
            CommitObject::new_purged(
                tree_hash.clone(),
                parents,
                created_at,
                message,
                current_tool_lock_hash,
                stats.clone(),
                purged_raws.to_vec(),
            )?
        } else {
            CommitObject::new(
                tree_hash.clone(),
                parents,
                created_at,
                message,
                current_tool_lock_hash,
                stats.clone(),
                commit_type,
            )?
        };
        let commit_value =
            serde_json::to_value(&commit).map_err(|err| KioError::schema(err.to_string()))?;
        // Content-addressed and therefore harmless/idempotent even when
        // `publish_ref` is false: the object becomes durable in the CAS but is
        // not yet reachable from any ref (05-runtime.md §3.5's `planned_commit`
        // — LC48 — computed and fixed once at the purge journal's `prepared`
        // phase, published for real later at `committed`).
        let (commit_hash, _) = self.store.write_json(ObjectKind::Commit, &commit_value)?;

        if !publish_ref {
            return Ok(SnapshotOutcome {
                noop: false,
                message: "snapshot computed (ref not published)".to_owned(),
                tree_hash,
                commit_hash: Some(commit_hash),
                commit: Some(commit),
                stats,
            });
        }

        // A scheduled checkpoint is a prepared eligible-attempt record.  The
        // commit object is already immutable and durable, but no ref/manifest
        // has moved yet.  If its conditional state publication fails, return
        // without making the object reachable.
        if scheduled_bound {
            wait_at_bound_snapshot_auto_pre_checkpoint_barrier();
            self.store.validate_bound_layout()?;
            if let Some(authority) = expected_scheduled_authority {
                self.recheck_scheduled_snapshot_authority(authority)?;
            }
            if let Some(policy) = expected_snapshot_policy {
                policy.recheck(
                    self.bound_root.as_deref().expect("scheduled bound root"),
                    self.bound_kio.as_deref().expect("scheduled bound kio"),
                )?;
            }
            self.reject_scheduled_bound_purge_state()?;
            self.reject_scheduled_marker_targets(
                working.entries.iter().map(|entry| &entry.raw_hash),
            )?;
        }
        let checkpoint = match before_ref_publication {
            Some(publish) => Some(publish()?),
            None => None,
        };

        // Known limitation (WS1c S6, 2026-07-03): refs/heads/main and HEAD are
        // advanced by two separate atomic renames. Each rename is individually
        // crash-safe (temp file + rename, never a torn value), but a power loss
        // *between* them can leave refs/heads/main advanced while HEAD still
        // points at the parent. The commit object is already durable in the CAS,
        // so recovery is a matter of re-pointing HEAD; no data is lost. A single
        // atomic multi-ref transaction is deferred (single-user Step 1 scope).
        let published_authority = if scheduled_bound {
            self.store.validate_bound_layout()?;
            if let Some(authority) = expected_scheduled_authority {
                self.recheck_scheduled_snapshot_authority(authority)?;
            }
            if let Some(policy) = expected_snapshot_policy {
                policy.recheck(
                    self.bound_root.as_deref().expect("scheduled bound root"),
                    self.bound_kio.as_deref().expect("scheduled bound kio"),
                )?;
            }
            if let Some(checkpoint) = checkpoint.as_ref() {
                checkpoint.recheck(self.bound_kio.as_deref().expect("scheduled bound kio"))?;
            }
            wait_at_bound_snapshot_auto_after_state_write_barrier();
            self.store.validate_bound_layout()?;
            if let Some(authority) = expected_scheduled_authority {
                self.recheck_scheduled_snapshot_authority(authority)?;
            }
            if let Some(policy) = expected_snapshot_policy {
                policy.recheck(
                    self.bound_root.as_deref().expect("scheduled bound root"),
                    self.bound_kio.as_deref().expect("scheduled bound kio"),
                )?;
            }
            if let Some(checkpoint) = checkpoint.as_ref() {
                checkpoint.recheck(self.bound_kio.as_deref().expect("scheduled bound kio"))?;
            }
            self.reject_scheduled_bound_purge_state()?;
            self.reject_scheduled_marker_targets(
                working.entries.iter().map(|entry| &entry.raw_hash),
            )?;
            self.publish_scheduled_bound_refs(&commit_hash)?;
            Some(self.capture_scheduled_snapshot_authority()?)
        } else {
            atomic_overwrite(
                &self.kio_dir.join("refs/heads/main"),
                commit_hash.as_bytes(),
            )?;
            atomic_overwrite(&self.kio_dir.join("HEAD"), commit_hash.as_bytes())?;
            None
        };
        self.write_manifest(&working, prior_tree.as_ref())?;
        if scheduled_bound {
            self.store.validate_bound_layout()?;
            if let Some(authority) = expected_scheduled_authority {
                self.recheck_scheduled_published_authority(
                    authority,
                    published_authority
                        .as_ref()
                        .expect("scheduled published authority binding"),
                    &commit_hash,
                )?;
            }
            if let Some(policy) = expected_snapshot_policy {
                policy.recheck(
                    self.bound_root.as_deref().expect("scheduled bound root"),
                    self.bound_kio.as_deref().expect("scheduled bound kio"),
                )?;
            }
            if let Some(checkpoint) = checkpoint.as_ref() {
                checkpoint.recheck(self.bound_kio.as_deref().expect("scheduled bound kio"))?;
            }
        }

        // U19/LC23-LC25: retire is appended only *after* this snapshot's
        // finalize (commit + ref publish + manifest, all now durable above) —
        // "same locked mutation" is satisfied because `_lock` (reentrant) is
        // still held. A crash before this point leaves the tombstone/receipt
        // active (LC24, safe side); the next locked mutation touching this
        // raw_hash (this same code path, naturally re-run) or an explicit
        // `kio repair verify-objects` backfill (LC27) completes it later.
        if !resurrection_candidates.is_empty() {
            let purge = PurgeState::new(&self.kio_dir);
            let actor = std::env::var("USER").unwrap_or_else(|_| "local-user".to_owned());
            purge.retire_resurrected(
                &resurrection_candidates,
                &commit_hash,
                &commit.created_at,
                &actor,
            )?;
        }

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
        self.log_from(None)
    }

    /// QB50 (step4b-contract-tests-p3b.md §D, 06 §1 L61 + 裁定5's adopted
    /// analogy to `--at`'s established "resolve the operand, then treat it
    /// as the walk's basis" semantics elsewhere — search 06 §3 L226 /
    /// 05-runtime.md §1.6 L214): `kio log --at <commit>` walks from an
    /// explicit, already-`resolve_commit`-resolved starting commit instead
    /// of HEAD. `start = None` (plain `kio log`) is exactly the prior `log`
    /// behavior (QB53's non-breaking regression requirement) — first-parent
    /// walk from HEAD, truncating (not failing) on a missing ancestor.
    pub fn log_from(&self, start: Option<String>) -> Result<LogReport> {
        self.log_from_with_limit(start, crate::history::DEFAULT_MAX_HISTORY_COMMITS)
    }

    /// [`Self::log_from`]'s implementation, parameterized on the
    /// first-parent walk's aggregate commit-count cap (R23-29,
    /// 05-runtime.md §1.6 L304-313) so tests can exercise the exact
    /// boundary without materializing `DEFAULT_MAX_HISTORY_COMMITS`
    /// (100,000) real commits. Shares `history::DEFAULT_MAX_HISTORY_COMMITS`
    /// with the `HistoryReader`-based all-parent/first-parent walks
    /// (`crate::history`) so the bound is exact and identically sized
    /// everywhere it is named, not a locally re-guessed constant. Unlike
    /// those walks, this one never reads tree objects at all -- only commit
    /// objects -- so the aggregate bound's other two components (tree
    /// entries / verified bytes) do not independently apply: a commit
    /// object holds only metadata (tree hash, parents, timestamp, message,
    /// stats), so reaching the 4 GiB byte bound from `commits.len()` commit
    /// objects alone would require an implausible ~40 KiB average commit
    /// size -- the commit-count cap below always fires first.
    fn log_from_with_limit(&self, start: Option<String>, max_commits: u64) -> Result<LogReport> {
        self.validate()?;
        let mut entries = Vec::new();
        let mut next = match start {
            Some(hash) => Some(hash),
            None => self.head_commit_hash()?,
        };
        let mut truncated = false;
        let mut commit_count: u64 = 0;
        while let Some(hash) = next {
            commit_count += 1;
            if commit_count > max_commits {
                return Err(KioError::new(
                    "KIO-E-COMMIT-HISTORY-LIMIT-001",
                    "history walk aggregate limit exceeded",
                    json!({
                        "exceeded": "commits",
                        "attempted": commit_count,
                        "max_commits": max_commits,
                    }),
                    ExitCode::PermanentFailure,
                ));
            }
            // R16-1: a missing ancestor commit object (shallow / external corruption)
            // truncates the history at that point instead of bricking the whole `log`
            // on a raw KIO-E-STORE-NOT-FOUND-001. The healthy prefix from HEAD is
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
        // full-file diff is impossible — surface a clear KIO-E-COMMIT-SHALLOW-001
        // that names WHICH side (a/b) is shallow, not a raw opaque
        // KIO-E-STORE-NOT-FOUND-001 whose hash the user cannot map to an operand
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
                path: is_materializable_direct_child(&path).then(|| self.root.join(&path)),
                relative_path: path.clone(),
                change: change.to_owned(),
                old_raw_hash: a_map.get(&path).cloned(),
                new_raw_hash: b_map.get(&path).cloned(),
            });
        }
        Ok(changes)
    }

    /// R16-5: read one `diff` side's tree, folding a missing commit OR tree object
    /// (shallow: discarded / corrupt) into a KIO-E-COMMIT-SHALLOW-001 that names
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
                crate::gc::validate_final_shallow_tree(&self.kio_dir, commit_hash, &commit.tree)?;
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
        // form BEFORE it ever consults the canonical tag refs (see below), so a tag created
        // under such a name is written to disk but permanently shadowed — a dead
        // ref that `diff`/`log` can never reach. Reject it at creation rather than
        // returning a success that silently does nothing. (This check is specific
        // to tag *names*; `validate_ref_operand` stays shared with `resolve_commit`,
        // which must still accept `HEAD`/hash as commit operands.)
        let collision_key = portable_collision_key(name);
        if collision_key == "head" || is_hash(&collision_key) {
            return Err(KioError::invalid_usage(
                "tag name collides with `HEAD` or a commit hash",
            ));
        }
        if let Some(reason) = portable_leaf_error(name) {
            return Err(KioError::invalid_usage(format!(
                "tag name is not a portable filesystem leaf: {reason}"
            )));
        }
        let _lock = StoreLock::acquire(&self.kio_dir)?;
        let commit_hash = match commit {
            Some(value) => self.resolve_commit(value)?,
            None => self
                .head_commit_hash()?
                .ok_or_else(|| KioError::not_found("HEAD"))?,
        };
        // R17-5: with no explicit operand the implicit HEAD is resolved via
        // head_commit_hash() (which never reads the commit object), so this is the
        // first existence check. A shallow (missing / corrupt) HEAD commit folds into
        // KIO-E-COMMIT-SHALLOW-001 with tag-write context, matching every other
        // shallow-commit site (R16-1), not a raw, opaque KIO-E-STORE-NOT-FOUND-001.
        // (When `commit_hash` came from `resolve_commit`, existence was already
        // verified there, so this read only surfaces the implicit-HEAD case.)
        let tagged_commit = match self.read_commit(&commit_hash) {
            Ok(commit) => commit,
            Err(error) if is_store_not_found(&error) => {
                return Err(KioError::commit_shallow(
                    "cannot create a tag on a shallow commit: the HEAD commit object is \
                     missing (discarded / corrupt); restore the commit object or tag a \
                     non-shallow commit",
                    commit_hash.clone(),
                ));
            }
            Err(error) => return Err(error),
        };
        // A final shallow receipt is an explicit history boundary; publishing a
        // new ref to that commit would make it a live tip with no tree.  Route
        // *every* missing target tree through the shared strict classifier:
        // a canonical final boundary returns COMMIT-SHALLOW, while a missing
        // receipt, a mismatch, a manual/purged commit, an active sweep, or an
        // already-live ref tip is store corruption.  If the tree is present,
        // an extant receipt is likewise corruption (a receipt cannot be a
        // best-effort hint).
        match self.read_tree(&tagged_commit.tree) {
            Err(error) if is_store_not_found(&error) => {
                crate::gc::validate_final_shallow_tree(
                    &self.kio_dir,
                    &commit_hash,
                    &tagged_commit.tree,
                )?;
                return Err(KioError::commit_shallow(
                    "cannot create a tag on a final shallow commit; restore a non-shallow commit first",
                    commit_hash.clone(),
                ));
            }
            Ok(_)
                if crate::gc::read_shallow_receipts(&self.kio_dir)?.contains_key(&commit_hash) =>
            {
                return Err(KioError::new(
                    "KIO-E-STORE-CORRUPT-001",
                    "shallow receipt coexists with the tagged tree object",
                    json!({"commit_hash": commit_hash}),
                    ExitCode::PermanentFailure,
                ));
            }
            Ok(_) => {}
            Err(error) => return Err(error),
        }
        let canonical_tags_dir = ensure_portable_tags_directory(&self.kio_dir)?;
        if matching_tag_ref_path(&canonical_tags_dir, name)?.is_some() {
            return Err(KioError::new(
                "KIO-E-COMMIT-TAG-001",
                "tag already exists (tag names collide case-insensitively)",
                json!({ "tag": name }),
                ExitCode::InvalidUsage,
            ));
        }
        // §Z ruling 1 (step4b-contract-tests-p2b.md PB07, 03-data-model.md §2
        // L140-152): names.jsonl is the truth for the digest -> logical_name
        // mapping (the canonical ref's hashed leaf is one-way). Write order is
        // fixed: names row append (fsync'd by `append_jsonl`'s single
        // `write_all` on an O_APPEND handle) BEFORE the ref — the reverse
        // order would let a crash publish a ref with no names row to explain
        // it (fsck reports that as corruption, PB09).
        append_jsonl(
            &names_jsonl_path(&self.kio_dir),
            &json!({
                "digest64": portable_tag_digest64(name),
                "logical_name": name.nfc().collect::<String>(),
                "recorded_at": now_utc_seconds(),
            }),
        )?;
        let path = canonical_tags_dir.join(portable_tag_leaf(name));
        atomic_write(&path, commit_hash.as_bytes())?;
        Ok(commit_hash)
    }

    pub fn resolve_commit(&self, value: &str) -> Result<String> {
        // N4 (03 §3 scope boundary): a commit-ref operand is only ever `HEAD`, a
        // hash, or a tag name — none legitimately carry a path separator or a
        // `.`/`..` component. Without this guard, constructing a tag-ref path from
        // an unchecked operand would treat
        // `../../..` as a filesystem escape, turning `kio diff`/`kio tag <commit>`
        // into an out-of-scope file-existence oracle. Validate before any join.
        validate_ref_operand(value)?;
        if value == "HEAD" {
            return self
                .head_commit_hash()?
                .ok_or_else(|| KioError::not_found("HEAD"));
        }
        if is_hash(value) {
            // R17-5: `resolve_commit` runs before `diff_side_tree`'s R16-5 shallow
            // absorption (and before `tag`'s own verification read), so a hash-literal
            // shallow commit (commit object discarded / corrupt) must fold into
            // KIO-E-COMMIT-SHALLOW-001 HERE — otherwise it escapes as a raw, opaque
            // KIO-E-STORE-NOT-FOUND-001 while the `HEAD` operand (which skips
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
        let normalized_operand = portable_collision_key(value);
        if normalized_operand == "head" || is_hash(&normalized_operand) {
            return Err(KioError::invalid_usage(
                "commit reference collides with a reserved operand",
            ));
        }
        let canonical_tags_dir = self.kio_dir.join("refs").join(PORTABLE_TAGS_DIRECTORY);
        if let Some(tag) = matching_tag_ref_path(&canonical_tags_dir, value)? {
            let hash = read_tag_ref(&tag)?;
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
        Err(KioError::not_found(value))
    }

    pub fn read_commit(&self, hash: &str) -> Result<CommitObject> {
        let object = self.store.read_by_hash(hash)?;
        if object.kind != ObjectKind::Commit {
            return Err(KioError::schema("hash does not identify a commit"));
        }
        let commit: CommitObject = serde_json::from_slice(&object.bytes)
            .map_err(|err| KioError::schema(err.to_string()))?;
        if commit.parents.len() > MAX_COMMIT_PARENTS {
            return Err(KioError::schema(format!(
                "commit parents exceed the limit of {MAX_COMMIT_PARENTS}"
            )));
        }
        commit.validate()?;
        Ok(commit)
    }

    pub fn read_tree(&self, hash: &str) -> Result<TreeObject> {
        let object = self.store.read_by_hash(hash)?;
        if object.kind != ObjectKind::Tree {
            return Err(KioError::schema("hash does not identify a tree"));
        }
        let tree: TreeObject = serde_json::from_slice(&object.bytes)
            .map_err(|err| KioError::schema(err.to_string()))?;
        if tree.entries.len() > MAX_TREE_ENTRIES {
            return Err(KioError::schema(format!(
                "tree entries exceed the limit of {MAX_TREE_ENTRIES}"
            )));
        }
        tree.validate()?;
        Ok(tree)
    }

    pub fn head_commit_hash(&self) -> Result<Option<String>> {
        let path = self.kio_dir.join("HEAD");
        let value = fs::read_to_string(&path).kio_io(&path)?;
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
            // on a read-only `.kio`. A genuinely unborn branch still returns `None`
            // (refs empty too), preserving the first-`snapshot`-creates-root path.
            empty_head_recovery_hash(&self.kio_dir)
        } else if is_hash(value) {
            Ok(Some(value.to_owned()))
        } else {
            Err(KioError::schema("HEAD must contain a commit_hash"))
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
        // read-only `.kio`, so a healthy scope is completely unaffected below.
        if empty_head_recovery_hash(&self.kio_dir)?.is_none() {
            return Ok(None);
        }
        // R14-3: the repair below is a best-effort *write* on the common `open()`
        // entrypoint. A read-only `.kio` (archive / forensic mount) cannot take the
        // store lock or overwrite HEAD; before R14-3 those permission errors propagated
        // out of `open()` (the `?`) and bricked even pure-read commands
        // (status/log/search/inspect) on a scope with a corrupt (empty) HEAD — an R13-4
        // regression. Follow the R12-5/R13-3 rule that observation/repair writes are
        // non-fatal: if we cannot take the lock (read-only permission, or a live
        // concurrent holder), defer the heal (warn + `Ok(None)`) so reads still run; a
        // later *writable* open completes it. R13-4's guarantee is preserved because a
        // writable scope still heals here — before any `snapshot` advances HEAD — so no
        // snapshot can orphan history under a fresh `parents=[]` root.
        let Ok(_lock) = StoreLock::acquire(&self.kio_dir) else {
            let _ = append_warn_log(
                "KIO-W-STORE-HEAD-HEAL-DEFERRED-001",
                "corrupt HEAD detected but the store lock is unavailable (read-only scope or a \
                 concurrent holder); deferring self-heal so read-only commands still run",
                json!({ "kio_dir": self.kio_dir.display().to_string() }),
            );
            return Ok(None);
        };
        // Re-check under the lock in case another process healed it first.
        let Some(hash) = empty_head_recovery_hash(&self.kio_dir)? else {
            return Ok(None);
        };
        // R14-3: a read-only scope can hold the lock (it existed before the mount went
        // read-only, or the `.lock` create raced) yet still reject the HEAD overwrite.
        // Treat a write failure the same way — defer, do not brick reads.
        if atomic_overwrite(&self.kio_dir.join("HEAD"), hash.as_bytes()).is_err() {
            let _ = append_warn_log(
                "KIO-W-STORE-HEAD-HEAL-DEFERRED-001",
                "corrupt HEAD detected but HEAD is not writable (read-only scope); deferring \
                 self-heal so read-only commands still run",
                json!({ "kio_dir": self.kio_dir.display().to_string() }),
            );
            return Ok(None);
        }
        // A successful repair is never silent (R13-4): record it to events.jsonl. The
        // record is itself best-effort — a logging failure must not undo a completed
        // HEAD repair.
        let _ = append_event_log(
            "KIO-I-STORE-HEAD-REPAIRED-001",
            "restored empty/missing HEAD from refs/heads/main (corrupt HEAD, not unborn)",
            json!({ "commit_hash": hash }),
        );
        Ok(Some(hash))
    }

    /// R15-4: read the HEAD commit's tree object, distinguishing an unborn branch
    /// (no HEAD) from a shallow HEAD (tree object gone) from a present tree. A raw
    /// `KIO-E-STORE-NOT-FOUND-001` from the tree read is folded into the `Shallow`
    /// variant so callers decide the policy: pure reads degrade, writes fail loudly.
    fn head_tree_state(&self) -> Result<HeadTreeState> {
        let Some(commit_hash) = self.head_commit_hash()? else {
            return Ok(HeadTreeState::Unborn);
        };
        // R16-1: fold a missing *commit* object into `Shallow` too (was an
        // unconditional `?` that bricked pure reads on a raw KIO-E-STORE-NOT-FOUND-001
        // when the commit — not just its tree — was gone). Same corruption class, same
        // degrade-vs-fail-loudly policy the tree case already had.
        let tree_hash = match self.read_commit(&commit_hash) {
            Ok(commit) => commit.tree,
            Err(error) if is_store_not_found(&error) => return Ok(HeadTreeState::Shallow),
            Err(error) => return Err(error),
        };
        match self.read_tree(&tree_hash) {
            Ok(tree) => Ok(HeadTreeState::Present(tree)),
            Err(error) if is_store_not_found(&error) => {
                crate::gc::validate_final_shallow_tree(&self.kio_dir, &commit_hash, &tree_hash)?;
                Ok(HeadTreeState::Shallow)
            }
            Err(error) => Err(error),
        }
    }

    /// `kio_format_version` is a `.kio/scope.json`-only concept. A config file
    /// carrying that retired key is rejected by the strict config schema.
    fn validate_config(&self) -> Result<()> {
        self.validated_config_value()?;
        Ok(())
    }

    fn validated_config_value(&self) -> Result<Value> {
        #[cfg(unix)]
        let text = if let Some(kio) = self.bound_kio.as_deref() {
            read_bound_regular_text_at(kio, "config.toml", MAX_BOUND_CONFIG_BYTES)?
        } else {
            let path = self.kio_dir.join("config.toml");
            fs::read_to_string(&path).kio_io(&path)?
        };
        #[cfg(not(unix))]
        let text = {
            let path = self.kio_dir.join("config.toml");
            fs::read_to_string(&path).kio_io(&path)?
        };
        let toml: toml::Value =
            toml::from_str(&text).map_err(|error| KioError::schema(error.to_string()))?;
        let value =
            serde_json::to_value(&toml).map_err(|error| KioError::schema(error.to_string()))?;
        validate_json_schema(SchemaKind::Config, &value)?;
        // R12-2 / R12-1: reject documented-but-unwired values the schema can only
        // type-check (e.g. `allowed_scope != "."`) LOUDLY, so a scope config never
        // silently ignores a policy the user set.
        enforce_config_semantics(&value)?;
        Ok(value)
    }

    /// Read, validate, and freeze the chunking configuration used to construct
    /// one tree. The returned hash is derived from the exact parsed
    /// descriptor-bound `config.toml` bytes, never a later mutable lookup.
    fn effective_chunking_config_hash(&self) -> Result<String> {
        let value = self.validated_config_value()?;

        let chunking = value.get("chunking").and_then(Value::as_object);
        let strategy = chunking
            .and_then(|chunking| chunking.get("strategy"))
            .and_then(Value::as_str)
            .unwrap_or(DEFAULT_CHUNKING_STRATEGY);
        let max_chars = match chunking.and_then(|chunking| chunking.get("max_chars")) {
            None => DEFAULT_CHUNKING_MAX_CHARS,
            Some(number) => number
                .as_u64()
                .filter(|value| *value > 0)
                .and_then(|value| usize::try_from(value).ok().map(|_| value))
                .ok_or_else(|| {
                    KioError::schema(
                        "chunking.max_chars must be a positive integer representable on this platform",
                    )
                })?,
        };
        chunking_config_hash(strategy, max_chars)
    }

    fn validate_scope(&self) -> Result<()> {
        self.validated_scope_id().map(|_| ())
    }

    /// The exact `kio_format_version` judgment runs before current JSON Schema
    /// validation. Missing, malformed, older, and newer versions all fail with
    /// `KIO-E-STORE-VERSION-001` / exit 8; this ordering supplies a stable
    /// rejection code and does not permit read-only degradation.
    fn validated_scope_id(&self) -> Result<String> {
        #[cfg(unix)]
        let text = if let Some(kio) = self.bound_kio.as_deref() {
            read_bound_regular_text_at(kio, "scope.json", MAX_BOUND_CONFIG_BYTES)?
        } else {
            let path = self.kio_dir.join("scope.json");
            fs::read_to_string(&path).kio_io(&path)?
        };
        #[cfg(not(unix))]
        let text = {
            let path = self.kio_dir.join("scope.json");
            fs::read_to_string(&path).kio_io(&path)?
        };
        let value: Value =
            serde_json::from_str(&text).map_err(|err| KioError::schema(err.to_string()))?;
        validate_scope_json_value(&value)?;
        let Some(scope_id) = value.get("scope_id").and_then(Value::as_str) else {
            return Err(KioError::schema("scope.json missing scope_id"));
        };
        if scope_id.is_empty() {
            return Err(KioError::schema("scope_id is empty"));
        }
        if !is_ulid(scope_id) {
            return Err(KioError::schema("scope_id must be a ULID"));
        }
        Ok(scope_id.to_owned())
    }

    fn validate_manifest(&self) -> Result<()> {
        #[cfg(unix)]
        let text = if let Some(kio) = self.bound_kio.as_deref() {
            read_bound_regular_text_at(kio, "manifest.json", MAX_BOUND_CONFIG_BYTES)?
        } else {
            let path = self.kio_dir.join("manifest.json");
            fs::read_to_string(&path).kio_io(&path)?
        };
        #[cfg(not(unix))]
        let text = {
            let path = self.kio_dir.join("manifest.json");
            fs::read_to_string(&path).kio_io(&path)?
        };
        let value: Value =
            serde_json::from_str(&text).map_err(|err| KioError::schema(err.to_string()))?;
        validate_json_schema(SchemaKind::Manifest, &value)?;
        if !value.is_object() {
            return Err(KioError::schema("manifest.json must be an object"));
        }
        let Some(files) = value.get("files") else {
            return Err(KioError::schema("manifest.json missing files"));
        };
        let files = files
            .as_array()
            .ok_or_else(|| KioError::schema("manifest.files must be an array"))?;
        for file in files {
            let object = file
                .as_object()
                .ok_or_else(|| KioError::schema("manifest file entry must be an object"))?;
            let path = object
                .get("path")
                .and_then(Value::as_str)
                .ok_or_else(|| KioError::schema("manifest file entry missing path"))?;
            if path.is_empty() || path.contains('/') {
                return Err(KioError::path(
                    "manifest file path must be a direct child file name",
                    path.to_owned(),
                ));
            }
            let raw_hash = object
                .get("raw_hash")
                .and_then(Value::as_str)
                .ok_or_else(|| KioError::schema("manifest file entry missing raw_hash"))?;
            if !is_hash(raw_hash) {
                return Err(KioError::schema("manifest raw_hash must be a hash"));
            }
            let status = object
                .get("status")
                .and_then(Value::as_str)
                .ok_or_else(|| KioError::schema("manifest file entry missing status"))?;
            if !matches!(status, "new" | "modified" | "deleted" | "unchanged") {
                return Err(KioError::schema("manifest status has invalid value"));
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
            serde_json::to_vec_pretty(&value).map_err(|err| KioError::schema(err.to_string()))?;
        #[cfg(unix)]
        if let Some(kio) = self.bound_kio.as_deref() {
            return replace_bound_regular_file_at(kio, "manifest.json", &bytes);
        }
        atomic_overwrite(&self.kio_dir.join("manifest.json"), &bytes)
    }

    /// Read the current `manifest.json` `deleted` rows as a
    /// `path -> last raw_hash` map. Live rows are intentionally excluded — the
    /// prior HEAD tree is the authoritative source for those (see
    /// `write_manifest`).
    /// Returns an empty map when the manifest is absent. The manifest is schema
    /// validated before `snapshot` runs, so entries are well formed here.
    fn read_manifest_deleted_hashes(&self) -> Result<BTreeMap<String, String>> {
        let mut map = BTreeMap::new();
        #[cfg(unix)]
        let text = if let Some(kio) = self.bound_kio.as_deref() {
            read_bound_regular_text_at(kio, "manifest.json", MAX_BOUND_CONFIG_BYTES)?
        } else {
            let path = self.kio_dir.join("manifest.json");
            if !path.is_file() {
                return Ok(map);
            }
            fs::read_to_string(&path).kio_io(&path)?
        };
        #[cfg(not(unix))]
        let text = {
            let path = self.kio_dir.join("manifest.json");
            if !path.is_file() {
                return Ok(map);
            }
            fs::read_to_string(&path).kio_io(&path)?
        };
        let value: Value =
            serde_json::from_str(&text).map_err(|err| KioError::schema(err.to_string()))?;
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

    fn publish_tool_lock(&self) -> Result<String> {
        let (expected_hash, bytes) = self.tool_lock_identity()?;
        let published_hash = self
            .store
            .write_content_object(ContentObjectKind::Toollock, &bytes)?;
        if published_hash != expected_hash {
            return Err(KioError::schema(
                "published immutable tool-lock hash differs from mutable authority",
            ));
        }
        Ok(published_hash)
    }

    fn tool_lock_identity(&self) -> Result<(String, Vec<u8>)> {
        #[cfg(unix)]
        if let Some(kio) = self.bound_kio.as_deref() {
            let text = read_bound_regular_text_at(kio, "tool-lock.json", MAX_BOUND_CONFIG_BYTES)?;
            let value: Value =
                serde_json::from_str(&text).map_err(|err| KioError::schema(err.to_string()))?;
            let canonical = canonical_tool_lock_value(&value)?;
            let bytes = canonical_json_bytes(&canonical)?;
            return Ok((crate::cas::hash_bytes(&bytes), bytes));
        }
        let path = self.kio_dir.join("tool-lock.json");
        let value: Value = serde_json::from_str(&fs::read_to_string(&path).kio_io(&path)?)
            .map_err(|err| KioError::schema(err.to_string()))?;
        let canonical = canonical_tool_lock_value(&value)?;
        let bytes = canonical_json_bytes(&canonical)?;
        Ok((crate::cas::hash_bytes(&bytes), bytes))
    }
}

/// Create the first `.kio` tree through the already no-follow-opened directory
/// handle. This is intentionally separate from [`Repository::init`]: a bound
/// child must not use `create_dir_all` or any public child path while its name
/// can be replaced by another same-UID process.
#[cfg(unix)]
fn initialize_bound_kio_layout(kio: &File, canonical_root: &Path) -> Result<()> {
    for relative in [
        "objects/raw",
        "objects/trees",
        "objects/commits",
        "refs/heads",
        "logs",
    ] {
        create_bound_dir_all(kio, relative)?;
    }
    create_bound_dir_all(kio, &format!("refs/{PORTABLE_TAGS_DIRECTORY}"))?;
    write_bound_new(kio, "HEAD", b"")?;
    write_bound_new(kio, "refs/heads/main", b"")?;
    write_bound_new(kio, "config.toml", b"")?;
    write_bound_new(
        kio,
        "scope.json",
        serde_json::to_string_pretty(&json!({
            "kio_format_version": KIO_FORMAT_VERSION,
            "scope_id": new_ulid(canonical_root),
            "scope_path": canonical_root,
        }))
        .map_err(|err| KioError::schema(err.to_string()))?
        .as_bytes(),
    )?;
    write_bound_new(
        kio,
        "manifest.json",
        b"{\n  \"schema_version\": 1,\n  \"files\": []\n}\n",
    )?;
    write_bound_new(kio, "tool-lock.json", b"{\n  \"spec_version\": 1\n}\n")?;
    Ok(())
}

#[cfg(unix)]
fn create_bound_dir_all(root: &File, relative: &str) -> Result<()> {
    use cap_primitives::fs as cap_fs;
    let mut current = root
        .try_clone()
        .map_err(|err| KioError::io(err.to_string(), relative))?;
    for component in Path::new(relative).components() {
        let Component::Normal(component) = component else {
            continue;
        };
        current = match cap_fs::open_dir_nofollow(&current, Path::new(component)) {
            Ok(handle) => handle,
            Err(_) => {
                match cap_fs::stat(&current, Path::new(component), cap_fs::FollowSymlinks::No) {
                    Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
                        let mut options = cap_fs::DirOptions::new();
                        use cap_fs::DirBuilderExt;
                        options.mode(0o700);
                        match cap_fs::create_dir(&current, Path::new(component), &options) {
                            Ok(()) => {}
                            Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {}
                            Err(err) => return Err(KioError::io(err.to_string(), relative)),
                        }
                        cap_fs::open_dir_nofollow(&current, Path::new(component))
                            .map_err(|err| KioError::io(err.to_string(), relative))?
                    }
                    Ok(_) => {
                        return Err(KioError::invalid_usage(
                            ".kio layout component must be a directory",
                        ));
                    }
                    Err(err) => return Err(KioError::io(err.to_string(), relative)),
                }
            }
        };
    }
    Ok(())
}

#[cfg(unix)]
fn write_bound_new(root: &File, relative: &str, contents: &[u8]) -> Result<()> {
    use cap_primitives::fs as cap_fs;
    let path = Path::new(relative);
    let parent = path.parent().unwrap_or_else(|| Path::new(""));
    let leaf = path
        .file_name()
        .ok_or_else(|| KioError::invalid_usage("bound layout file must have a name"))?;
    let mut directory = root
        .try_clone()
        .map_err(|err| KioError::io(err.to_string(), relative))?;
    for component in parent.components() {
        let Component::Normal(component) = component else {
            continue;
        };
        directory = cap_fs::open_dir_nofollow(&directory, Path::new(component))
            .map_err(|err| KioError::io(err.to_string(), relative))?;
    }
    let mut options = cap_fs::OpenOptions::new();
    options.write(true).create_new(true);
    let mut file = cap_fs::open(&directory, Path::new(leaf), &options)
        .map_err(|err| KioError::io(err.to_string(), relative))?;
    file.write_all(contents)
        .map_err(|err| KioError::io(err.to_string(), relative))?;
    file.sync_all()
        .map_err(|err| KioError::io(err.to_string(), relative))?;
    Ok(())
}

/// Merge a generated parent policy into `config.toml` through the retained
/// no-follow `.kio` descriptor.  This is intentionally done before a bound
/// child returns a path-backed [`Repository`]: a same-UID rename of the public
/// `.kio` entry therefore cannot redirect the inherited-policy read or write.
#[cfg(unix)]
fn persist_bound_generated_parent_policy(kio: &File, policy: toml::Value) -> Result<()> {
    let text = read_bound_regular_text_at(kio, "config.toml", MAX_BOUND_CONFIG_BYTES)?;
    let mut config: toml::Value =
        toml::from_str(&text).map_err(|error| KioError::schema(error.to_string()))?;
    let table = config
        .as_table_mut()
        .ok_or_else(|| KioError::schema("config.toml must be a table"))?;
    table.insert("generated_parent_policy".to_owned(), policy);

    let json_value =
        serde_json::to_value(&config).map_err(|error| KioError::schema(error.to_string()))?;
    validate_json_schema(SchemaKind::Config, &json_value)?;
    enforce_config_semantics(&json_value)?;
    let text = toml::to_string(&config).map_err(|error| KioError::schema(error.to_string()))?;
    replace_bound_regular_file(kio, "config.toml", text.as_bytes())
}

/// Read a regular `.kio` metadata leaf through a retained directory
/// descriptor.  Every component is opened no-follow, so replacing a
/// descendant directory after the scheduler has acquired its capability
/// cannot redirect the read.
#[cfg(unix)]
fn read_bound_regular_text_at(kio: &File, relative: &str, max_bytes: u64) -> Result<String> {
    use cap_primitives::fs as cap_fs;

    let path = Path::new(relative);
    if path
        .components()
        .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(KioError::invalid_usage(
            "bound metadata path must contain only normal components",
        ));
    }
    let parent = path.parent().unwrap_or_else(|| Path::new(""));
    let leaf = path
        .file_name()
        .ok_or_else(|| KioError::invalid_usage("bound metadata path must name a regular file"))?;
    let mut directory = kio
        .try_clone()
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    for component in parent.components() {
        let Component::Normal(component) = component else {
            continue;
        };
        directory = cap_fs::open_dir_nofollow(&directory, Path::new(component))
            .map_err(|error| KioError::io(error.to_string(), relative))?;
    }
    let listed = cap_fs::stat(&directory, Path::new(leaf), cap_fs::FollowSymlinks::No)
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    if !listed.is_file() || listed.len() > max_bytes {
        return Err(KioError::schema(
            "bound metadata must be a bounded regular file",
        ));
    }
    let mut options = cap_fs::OpenOptions::new();
    options.read(true);
    options._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let mut file = cap_fs::open(&directory, Path::new(leaf), &options)
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    let opened = cap_fs::Metadata::from_file(&file)
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    if !opened.is_file() || opened.len() != listed.len() || opened.len() > max_bytes {
        return Err(KioError::schema("bound metadata changed while opening"));
    }
    let mut text = String::with_capacity(usize::try_from(opened.len()).unwrap_or(0));
    file.read_to_string(&mut text)
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    if text.len() as u64 != opened.len() {
        return Err(KioError::schema("bound metadata changed while reading"));
    }
    Ok(text)
}

/// Exact identity and content observation for a descriptor-relative metadata
/// read. This is deliberately separate from the GC observation types: the
/// scheduler's ref/tool handoff needs only regular-file authority binding.
#[derive(Debug, Clone, PartialEq, Eq)]
struct BoundMetadataObservation {
    dev: u64,
    ino: u64,
    len: u64,
    nlink: u64,
    digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ScheduledSnapshotAuthority {
    head: String,
    branch: String,
    tool_lock: String,
    head_observation: BoundMetadataObservation,
    branch_observation: BoundMetadataObservation,
    tool_lock_observation: BoundMetadataObservation,
}

/// Read a bounded regular metadata leaf without following any public path and
/// retain enough evidence to reject same-byte replacement at a later writer
/// boundary.
#[cfg(unix)]
fn read_bound_regular_text_observed_at(
    kio: &File,
    relative: &str,
    max_bytes: u64,
) -> Result<(String, BoundMetadataObservation)> {
    use cap_primitives::fs::{self as cap_fs, MetadataExt};

    let path = Path::new(relative);
    if path
        .components()
        .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(KioError::invalid_usage(
            "bound metadata path must contain only normal components",
        ));
    }
    let parent = path.parent().unwrap_or_else(|| Path::new(""));
    let leaf = path
        .file_name()
        .ok_or_else(|| KioError::invalid_usage("bound metadata path must name a regular file"))?;
    let mut directory = kio
        .try_clone()
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    for component in parent.components() {
        let Component::Normal(component) = component else {
            continue;
        };
        directory = cap_fs::open_dir_nofollow(&directory, Path::new(component))
            .map_err(|error| KioError::io(error.to_string(), relative))?;
    }
    let before = cap_fs::stat(&directory, Path::new(leaf), cap_fs::FollowSymlinks::No)
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    if !before.is_file() || before.nlink() != 1 || before.len() > max_bytes {
        return Err(KioError::schema(
            "bound metadata must be a bounded single-link regular file",
        ));
    }
    let mut options = cap_fs::OpenOptions::new();
    options.read(true);
    options._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let mut file = cap_fs::open(&directory, Path::new(leaf), &options)
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    let opened = cap_fs::Metadata::from_file(&file)
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    if !opened.is_file()
        || opened.nlink() != 1
        || opened.len() > max_bytes
        || opened.dev() != before.dev()
        || opened.ino() != before.ino()
        || opened.len() != before.len()
    {
        return Err(KioError::schema("bound metadata changed while opening"));
    }
    let mut bytes = Vec::with_capacity(usize::try_from(opened.len()).unwrap_or(0));
    (&mut file)
        .take(max_bytes.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    let after = cap_fs::stat(&directory, Path::new(leaf), cap_fs::FollowSymlinks::No)
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    if bytes.len() as u64 != opened.len()
        || after.dev() != opened.dev()
        || after.ino() != opened.ino()
        || after.nlink() != opened.nlink()
        || after.len() != opened.len()
    {
        return Err(KioError::schema("bound metadata changed while reading"));
    }
    let text =
        String::from_utf8(bytes.clone()).map_err(|error| KioError::schema(error.to_string()))?;
    Ok((
        text,
        BoundMetadataObservation {
            dev: opened.dev(),
            ino: opened.ino(),
            len: opened.len(),
            nlink: opened.nlink(),
            digest: lower_hex(&Sha256::digest(&bytes)),
        },
    ))
}

#[cfg(unix)]
fn replace_bound_regular_file(kio: &File, relative: &str, contents: &[u8]) -> Result<()> {
    replace_bound_regular_file_at(kio, relative, contents)
}

#[cfg(unix)]
fn replace_bound_regular_file_at(kio: &File, relative: &str, contents: &[u8]) -> Result<()> {
    use cap_primitives::fs as cap_fs;

    let path = Path::new(relative);
    if path
        .components()
        .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(KioError::invalid_usage(
            "bound metadata path must contain only normal components",
        ));
    }
    if contents.len() as u64 > MAX_BOUND_CONFIG_BYTES {
        return Err(KioError::schema(
            "bound config.toml exceeds the bootstrap byte limit",
        ));
    }

    let parent = path.parent().unwrap_or_else(|| Path::new(""));
    let leaf = path
        .file_name()
        .ok_or_else(|| KioError::invalid_usage("bound metadata path must name a regular file"))?;
    let mut directory = kio
        .try_clone()
        .map_err(|error| KioError::io(error.to_string(), relative))?;
    for component in parent.components() {
        let Component::Normal(component) = component else {
            continue;
        };
        directory = cap_fs::open_dir_nofollow(&directory, Path::new(component))
            .map_err(|error| KioError::io(error.to_string(), relative))?;
    }

    for attempt in 0..8_u8 {
        let temporary = format!(
            ".kio-config-{}-{}-{attempt}",
            std::process::id(),
            unix_nanos()
        );
        let temporary_path = Path::new(&temporary);
        let mut options = cap_fs::OpenOptions::new();
        options.write(true).create_new(true);
        let mut file = match cap_fs::open(&directory, temporary_path, &options) {
            Ok(file) => file,
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(KioError::io(error.to_string(), relative)),
        };
        let write_result = (|| -> Result<()> {
            file.write_all(contents)
                .map_err(|error| KioError::io(error.to_string(), relative))?;
            file.sync_all()
                .map_err(|error| KioError::io(error.to_string(), relative))?;
            Ok(())
        })();
        drop(file);
        if let Err(error) = write_result {
            let _ = cap_fs::remove_file(&directory, temporary_path);
            return Err(error);
        }
        if let Err(error) = cap_fs::rename(&directory, temporary_path, &directory, Path::new(leaf))
        {
            let _ = cap_fs::remove_file(&directory, temporary_path);
            return Err(KioError::io(error.to_string(), relative));
        }
        // The directory that directly contains the renamed leaf is the
        // durability boundary.  Syncing only the retained `.kio` ancestor is
        // insufficient for nested metadata such as `refs/heads/main`.
        sync_bound_directory(&directory, relative)?;
        return Ok(());
    }
    Err(KioError::io(
        "unable to allocate a unique bound config temporary file",
        relative,
    ))
}

pub(crate) fn canonical_tool_lock_value(value: &Value) -> Result<Value> {
    let object = value
        .as_object()
        .ok_or_else(|| KioError::schema("tool-lock.json must be an object"))?;
    let spec_version = object
        .get("spec_version")
        .and_then(Value::as_u64)
        .ok_or_else(|| KioError::schema("tool-lock.json missing spec_version"))?;
    if spec_version != 1 {
        return Err(KioError::schema(format!(
            "unsupported tool-lock spec_version: {spec_version}"
        )));
    }
    for key in object.keys() {
        if key != "spec_version" && !["prepare", "markdown", "embedding"].contains(&key.as_str()) {
            return Err(KioError::schema(format!(
                "unknown tool-lock.json role `{key}`"
            )));
        }
    }
    let mut canonical = Map::new();
    canonical.insert("spec_version".to_owned(), Value::from(spec_version));
    for key in ["prepare", "markdown"] {
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
        .ok_or_else(|| KioError::schema(format!("{key} must be an object")))?;
    let allowed_fields: &[&str] = match key {
        "prepare" => &["tool_id", "profile_hash", "kind"],
        "markdown" => &["tool_id", "profile_hash", "kind", "capabilities"],
        "embedding" => &[
            "tool_id",
            "dimensions",
            "distance",
            "modality",
            "profile_hash",
            "kind",
            "mode",
        ],
        _ => unreachable!("tool-lock entry role was validated"),
    };
    for field in entry.keys() {
        if !allowed_fields.contains(&field.as_str()) {
            return Err(KioError::schema(format!(
                "unknown field `{key}.{field}` in tool-lock.json"
            )));
        }
    }
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
        .ok_or_else(|| KioError::schema(format!("{key}.{field} must be a string")))
}

fn required_lock_integer(object: &Map<String, Value>, key: &str, field: &str) -> Result<Value> {
    object
        .get(field)
        .and_then(Value::as_u64)
        .map(Value::from)
        .ok_or_else(|| KioError::schema(format!("{key}.{field} must be an integer")))
}

/// R13-4: the commit hash an empty/missing `HEAD` should be restored to, or
/// `None` when there is nothing to repair. Returns `Some(hash)` only when HEAD is
/// empty/missing AND `refs/heads/main` names a commit object that actually exists
/// in the store — never adopts a dangling ref (that would move corruption into
/// HEAD instead of fixing it). Both HEAD and refs empty = a legitimately unborn
/// branch (fresh `init`), which stays `None` so a first `snapshot` still creates
/// the root commit. Shared by `Repository::self_heal_head` (the repair) and the
/// CLI re-`init` path (R13-5 damage detection before the repair runs).
pub fn empty_head_recovery_hash(kio_dir: &Path) -> Result<Option<String>> {
    let head_path = kio_dir.join("HEAD");
    let head_present_nonempty = match fs::read_to_string(&head_path) {
        Ok(value) => !value.trim().is_empty(),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => false,
        Err(err) => {
            return Err(KioError::io(
                err.to_string(),
                head_path.display().to_string(),
            ));
        }
    };
    if head_present_nonempty {
        return Ok(None);
    }
    let refs_path = kio_dir.join("refs/heads/main");
    let refs_value = match fs::read_to_string(&refs_path) {
        Ok(value) => value.trim().to_owned(),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(err) => {
            return Err(KioError::io(
                err.to_string(),
                refs_path.display().to_string(),
            ));
        }
    };
    if refs_value.is_empty() || !is_hash(&refs_value) {
        return Ok(None);
    }
    // Only restore from a ref that resolves to a real commit object.
    let store = ObjectStore::new(kio_dir.to_path_buf());
    match store.read_by_hash(&refs_value) {
        Ok(object) if object.kind == ObjectKind::Commit => Ok(Some(refs_value)),
        _ => Ok(None),
    }
}

/// Default log retention when `[observability] retention_days` is unset
/// (docs/06 §12 / docs/10 §11.6: "保持 30 日 (config 上書き可)").
pub const DEFAULT_LOG_RETENTION_DAYS: u32 = 30;

/// Read `[observability] retention_days` (integer 1..=3650) from a
/// `config.toml`.
/// `None` when the file/key is absent or malformed, so the caller applies the
/// 30-day default. The key is schema-validated (`config.schema.json`) at startup,
/// so a bad value would already have been rejected; this read is defensive.
#[must_use]
pub fn read_logs_retention_days(config_toml_path: &Path) -> Option<u32> {
    let text = fs::read_to_string(config_toml_path).ok()?;
    let value: toml::Value = toml::from_str(&text).ok()?;
    value
        .get("observability")
        .and_then(|section| section.get("retention_days"))
        .and_then(toml::Value::as_integer)
        .and_then(|days| u32::try_from(days).ok())
        .filter(|days| (1..=3650).contains(days))
}

/// `[adapter] lane` — the online send lane this config prefers, as a raw
/// string (`"batch"` | `"realtime"`; the schema constrains the enum, so this
/// read is defensive). `None` when the key is absent or unreadable, which
/// leaves the caller on its own default.
///
/// One key governs BOTH online adapters by ruling (07 §5.3, 2026-07-24): a
/// run never splits markdownize onto one lane and embedding onto the other,
/// so there is deliberately no per-adapter form of this key.
#[must_use]
pub fn read_adapter_lane(config_toml_path: &Path) -> Option<String> {
    let text = fs::read_to_string(config_toml_path).ok()?;
    let value: toml::Value = toml::from_str(&text).ok()?;
    value
        .get("adapter")
        .and_then(|adapter| adapter.get("lane"))
        .and_then(toml::Value::as_str)
        .map(str::to_owned)
        .filter(|lane| lane == "batch" || lane == "realtime")
}

/// R13-3: append `value` to the fixed-name JSONL at `path`, first performing a
/// best-effort daily rotation + retention prune (docs/06 §12 / docs/10 §11.6:
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
    // CT4-PURGE-008: every current-log append is serialized against purge's
    // current+rotated scrub. A contended nonblocking lock makes this best-effort
    // append fail without landing a post-scrub row; existing observability callers
    // already downgrade log failures so user operations remain unaffected.
    let _scrub_lock = scrub_lock_path(path)
        .map(StoreLock::acquire_path)
        .transpose()?;
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
    if rotation_due(path, &today)
        && let Ok(_rotate_lock) = StoreLock::acquire_path(rotate_lock_path(path))
    {
        let _ = rotate_stale_log(path, &today);
    }
    let _ = prune_rotated_logs(path, &today, retention_days);
    append_jsonl(path, value)
}

fn scrub_lock_path(path: &Path) -> Option<PathBuf> {
    let name = path.file_name()?.to_str()?;
    let parent = path.parent()?;
    if matches!(name, "events.jsonl" | "errors.jsonl" | "metrics.jsonl") {
        Some(parent.join("scrub.lock"))
    } else if name == "access.jsonl" {
        Some(parent.join("access.scrub.lock"))
    } else {
        None
    }
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
    let modified = metadata.modified().kio_io(path)?;
    let file_date = date_of_system_time(modified);
    // Same day (or a backwards clock) → keep appending to the live file.
    if file_date.is_empty() || file_date.as_str() >= today {
        return Ok(());
    }
    let dated = dated_log_path(path, &file_date);
    // Never clobber an already-rotated dated file (rename is skipped, the live
    // file keeps growing until the next distinct day — harmless).
    if !dated.exists() {
        fs::rename(path, &dated).kio_io(&dated)?;
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
    for entry in fs::read_dir(parent).kio_io(parent)? {
        let entry = entry.kio_io(parent)?;
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

pub fn append_error_log(error: &KioError) -> Result<()> {
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
    // `./kio/logs/errors.jsonl` under the working directory. Skip silently (logging
    // is best-effort) rather than create it.
    let log_dir = data_home().join("kio/logs");
    if !log_dir.is_absolute() {
        return Ok(());
    }
    // N3: honor `redact_logs` (06 §8 / 10 §11.6, default true) before writing. The
    // KioError context routinely carries a `path` (and search/adapter contexts a
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
    // errors.jsonl, breaking the "path is never recorded" premise (10 §11.6) and,
    // combined with a group-readable errors.jsonl, leaking scope paths to other
    // local users. Mask absolute-path tokens in the message too under redact_logs.
    let message: Value = if redact {
        Value::String(redact_message_paths(message))
    } else {
        Value::String(message.to_owned())
    };
    let path = log_dir.join(file_name);
    // R13-3: the device-global logs (events/errors/metrics) are governed by the
    // device-level `[observability] retention_days` (default 30). Rotation/prune is
    // best-effort inside `append_jsonl_rotating`.
    let retention = read_logs_retention_days(&config_home().join("kio/config.toml"))
        .unwrap_or(DEFAULT_LOG_RETENTION_DAYS);
    append_jsonl_rotating(
        &path,
        &json!({
            "ts": now_utc_seconds(),
            "level": level,
            "code": code,
            "component": "kio-cli",
            "message": message,
            "context": context,
        }),
        retention,
    )
}

/// Replace every absolute-path-looking token (a whitespace-delimited run) in a
/// log message with `[redacted]` (P4). Whitespace is preserved exactly. This is
/// deliberately conservative: relative tokens are left alone; the leak sources
/// all emit absolute paths via `path.display()`.
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
    if looks_like_absolute_path_token(token) {
        out.push_str("[redacted]");
    } else {
        out.push_str(token);
    }
}

fn looks_like_absolute_path_token(token: &str) -> bool {
    let bytes = token.as_bytes();
    let windows_drive_absolute = bytes.len() >= 3
        && bytes[0].is_ascii_alphabetic()
        && bytes[1] == b':'
        && matches!(bytes[2], b'\\' | b'/');
    let windows_unc_absolute = token.len() > 2 && token.starts_with(r"\\");

    (token.len() > 1 && token.starts_with('/')) || windows_drive_absolute || windows_unc_absolute
}

/// Whether `redact_logs` is in effect (06 §8 default true). Read from the user
/// config's `[adapter.policy]`; the observation logs are device-global so the
/// device-level config governs them. Absent config / key -> the secure default.
fn redact_logs_enabled() -> bool {
    let path = config_home().join("kio/config.toml");
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
/// absolute paths), and `root_path`/`kio_path` (registry/scope contexts) — P4.
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
                        | "kio_path"
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
/// Schema can only type-check. A key whose value selects behavior Kio has not
/// implemented is rejected LOUDLY (`KIO-E-CONFIG-NOT-IMPLEMENTED-001`, exit 1 —
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
    // Child scopes persist the parent's rules through a bounded, strict
    // generated-policy envelope. Reject source config that cannot make that
    // transition before a later child discovery can turn it into a partial
    // index result. JSON Schema enforces the structural maximums; this closes
    // the byte-length and bare-negation gaps JSON Schema cannot express here.
    if let Some(ignore) = config
        .get("scope")
        .and_then(|scope| scope.get("ignore"))
        .and_then(Value::as_array)
    {
        for value in ignore {
            let pattern = value
                .as_str()
                .ok_or_else(|| KioError::schema("scope.ignore entries must be strings"))?;
            let effective = pattern.trim_start_matches('!');
            if effective.is_empty() || effective.len() > 4_096 {
                return Err(KioError::schema(
                    "scope.ignore entries must contain a bounded pattern",
                ));
            }
        }
    }
    if let Some(policy) = config
        .get("adapter")
        .and_then(|adapter| adapter.get("policy"))
    {
        // allowed_scope: only "." (scope containment, 07 §7.1.2 P1) is implemented.
        if let Some(scope) = policy.get("allowed_scope").and_then(Value::as_str)
            && scope != "."
        {
            return Err(KioError::not_implemented(
                "adapter.policy.allowed_scope other than \".\"",
            ));
        }
        // Request/response body persistence is never done (07 §7 "ログ本文禁止" —
        // only hashes are logged), so a `true` request is unimplemented.
        if policy.get("store_request_body").and_then(Value::as_bool) == Some(true) {
            return Err(KioError::not_implemented(
                "adapter.policy.store_request_body = true",
            ));
        }
        if policy.get("store_response_body").and_then(Value::as_bool) == Some(true) {
            return Err(KioError::not_implemented(
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
            return Err(KioError::not_implemented(
                "adapter.policy.require_command_confirmation = false",
            ));
        }
        // timeout_seconds: a per-adapter execution timeout is not threaded through
        // the adapter HTTP path (it would touch every adapter's transport). Accept
        // the documented default (300); reject any other value loudly rather than
        // silently ignore it. (R12-2 decision: real wiring is a large change.)
        if let Some(timeout) = policy.get("timeout_seconds").and_then(Value::as_i64)
            && timeout != 300
        {
            return Err(KioError::not_implemented(
                "adapter.policy.timeout_seconds other than 300",
            ));
        }
        // D7 (07 §7): `[adapter.policy.<execution_mode>]` overrides the parent
        // for that mode. Only `offline_api` is wired -- the CLI reads it into
        // the execution-timeout registry and the offline embedding client is
        // built under it. The other two modes are rejected here rather than
        // accepted, because a value nothing honours is worse than a value
        // refused: today's loud error would become a silent no-op, and the
        // operator would believe a timeout is in force that is not.
        for mode in ["online_api", "deterministic_library"] {
            if policy.get(mode).is_some() {
                return Err(KioError::not_implemented(format!(
                    "adapter.policy.{mode} (only offline_api is wired)"
                )));
            }
        }
    }
    // QA61 (step4b-contract-tests-p3a.md §R, arbitration #7): `include_neighbors`
    // was removed from `config.schema.json` entirely (it disappeared from the
    // documented config example with no implementation concept, R12-1) — an
    // unknown key is now a schema error at the JSON-schema layer
    // (`additionalProperties: false`), so this function no longer needs a
    // dedicated NOT-IMPLEMENTED check for it.
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
        return Err(KioError::invalid_usage(
            "commit reference must not contain path separators or `.`/`..` traversal",
        ));
    }
    Ok(())
}

/// The canonical hashed ref is the only physical representation of a tag. The
/// leaf is `sha256` over the NFC + simple-case-folded logical name, so
/// case-insensitive collision is decided by the leaf itself — there is nothing
/// to enumerate and no second namespace that could alias it.
fn matching_tag_ref_path(canonical_tags_dir: &Path, logical_name: &str) -> Result<Option<PathBuf>> {
    if !validate_tag_refs_directory(canonical_tags_dir, true)? {
        return Ok(None);
    }
    let path = canonical_tags_dir.join(portable_tag_leaf(logical_name));
    match fs::symlink_metadata(&path) {
        Ok(_) => Ok(Some(path)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(KioError::io(error.to_string(), path.display().to_string())),
    }
}

/// `.kio/refs/tags-v1/names.jsonl` (03-data-model.md §2 L80/141): the
/// append-only logical-tag-name ledger, co-located with the canonical
/// `tags-v1/` ref directory it describes. Public so fsck (verify_objects.rs,
/// PB07-09) can locate the same path without re-deriving the convention.
#[must_use]
pub fn names_jsonl_path(kio_dir: &Path) -> PathBuf {
    kio_dir
        .join("refs")
        .join(PORTABLE_TAGS_DIRECTORY)
        .join("names.jsonl")
}

fn ensure_portable_tags_directory(kio_dir: &Path) -> Result<PathBuf> {
    let refs_dir = kio_dir.join("refs");
    validate_tag_refs_directory(&refs_dir, false)?;
    let canonical_tags_dir = refs_dir.join(PORTABLE_TAGS_DIRECTORY);
    if !validate_tag_refs_directory(&canonical_tags_dir, true)? {
        match fs::create_dir(&canonical_tags_dir) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => {
                return Err(KioError::io(
                    error.to_string(),
                    canonical_tags_dir.display().to_string(),
                ));
            }
        }
        validate_tag_refs_directory(&canonical_tags_dir, false)?;
    }
    Ok(canonical_tags_dir)
}

/// Validate a store-owned tag directory without following a symlink/junction.
/// `allow_missing` supports opening pre-portability stores that do not yet have
/// the versioned canonical directory; the first tag write creates it under the
/// store lock and validates it again.
fn validate_tag_refs_directory(path: &Path, allow_missing: bool) -> Result<bool> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound && allow_missing => {
            return Ok(false);
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Err(tag_ref_corrupt(path, "tag refs directory is missing"));
        }
        Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
    };
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(unsafe_store_error(
            path,
            "tag refs path must be a real directory inside the store",
        ));
    }
    #[cfg(windows)]
    if !crate::cas::windows_directory_is_real(path)
        .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?
    {
        return Err(unsafe_store_error(
            path,
            "tag refs path must not be a Windows reparse point",
        ));
    }
    let resolved = path.canonicalize().kio_io(path)?;
    let expected = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?
            .join(path)
    };
    if resolved != expected {
        return Err(unsafe_store_error(
            path,
            "tag refs directory resolves outside its store path",
        ));
    }
    Ok(true)
}

/// `refs/heads/` is intentionally flat: branch names are not a second path
/// namespace.  Ref enumeration treats every unexpected entry as corruption so
/// a repair never quietly omits history because a symlink, directory, or bad
/// leaf was planted beneath `.kio/refs`.
fn collect_branch_ref_targets(path: &Path, targets: &mut BTreeSet<String>) -> Result<()> {
    if !validate_tag_refs_directory(path, true)? {
        return Ok(());
    }
    for entry in fs::read_dir(path).kio_io(path)? {
        let entry = entry.kio_io(path)?;
        let leaf = entry.file_name();
        let leaf = leaf
            .to_str()
            .ok_or_else(|| tag_ref_corrupt(&entry.path(), "branch ref leaf is not UTF-8"))?;
        if leaf.is_empty() || leaf == "." || leaf == ".." {
            return Err(tag_ref_corrupt(&entry.path(), "branch ref leaf is invalid"));
        }
        let value = read_commit_ref(&entry.path(), leaf == "main")?;
        if let Some(hash) = value {
            targets.insert(hash);
        }
    }
    Ok(())
}

/// Add canonical tag targets while excluding the adjacent logical-name ledger.
fn collect_tag_ref_targets(path: &Path, targets: &mut BTreeSet<String>) -> Result<()> {
    if !validate_tag_refs_directory(path, true)? {
        return Ok(());
    }
    for entry in fs::read_dir(path).kio_io(path)? {
        let entry = entry.kio_io(path)?;
        let leaf = entry.file_name();
        let leaf = leaf
            .to_str()
            .ok_or_else(|| tag_ref_corrupt(&entry.path(), "tag ref leaf is not UTF-8"))?;
        if leaf == "names.jsonl" {
            continue;
        }
        let valid = leaf.strip_prefix("tag-").is_some_and(|digest| {
            digest.len() == 64
                && digest
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        });
        if !valid {
            return Err(tag_ref_corrupt(
                &entry.path(),
                "canonical tag leaf is invalid",
            ));
        }
        // Keep the existing single-link/no-follow reader as the sole parser
        // for tag contents, including its bounded-size and canonical-hash
        // checks.
        targets.insert(read_tag_ref(&entry.path())?);
    }
    Ok(())
}

/// Read one bounded, regular, single-link commit ref without following it.
/// `HEAD` and the unborn `main` branch are the only refs permitted to be empty.
fn read_commit_ref(path: &Path, allow_empty: bool) -> Result<Option<String>> {
    let listed = fs::symlink_metadata(path).kio_io(path)?;
    if !listed.file_type().is_file() || listed.len() > MAX_TAG_REF_BYTES {
        return Err(tag_ref_corrupt(
            path,
            "commit ref is not a bounded regular file",
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if listed.nlink() != 1 {
            return Err(tag_ref_corrupt(
                path,
                "commit ref has an unexpected hard-link count",
            ));
        }
    }
    let file = open_scope_file_nofollow(path)?;
    let opened = file.metadata().kio_io(path)?;
    if !opened.is_file() || opened.len() != listed.len() || opened.len() > MAX_TAG_REF_BYTES {
        return Err(tag_ref_corrupt(path, "commit ref changed while opening"));
    }
    let mut bytes = Vec::new();
    file.take(MAX_TAG_REF_BYTES + 1)
        .read_to_end(&mut bytes)
        .kio_io(path)?;
    if bytes.len() as u64 > MAX_TAG_REF_BYTES {
        return Err(tag_ref_corrupt(
            path,
            "commit ref exceeds the bounded size limit",
        ));
    }
    let text = std::str::from_utf8(&bytes)
        .map_err(|_| tag_ref_corrupt(path, "commit ref is not UTF-8"))?;
    let hash = text.trim();
    if hash.is_empty() && allow_empty {
        return Ok(None);
    }
    if !is_hash(hash) {
        return Err(tag_ref_corrupt(
            path,
            "commit ref target is not a canonical commit hash",
        ));
    }
    Ok(Some(hash.to_owned()))
}

fn read_tag_ref(path: &Path) -> Result<String> {
    read_commit_ref(path, false)?.ok_or_else(|| tag_ref_corrupt(path, "tag ref is empty"))
}

fn tag_ref_corrupt(path: &Path, message: &str) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        message,
        json!({ "path": path }),
        ExitCode::PermanentFailure,
    )
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

/// QA7 (step4b-contract-tests-p3a.md §B, arbitration #1): the built-in Tier A
/// pattern set as data, not just imperative comparisons — the single source
/// both [`is_tier_a_secret_name`] and [`tier_a_template_text`] (10 §1.1's
/// `effective_ignore_hash` input) consult, so a pattern-list edit is
/// mechanically guaranteed to change the hash instead of relying on someone
/// remembering to bump a version literal.
const TIER_A_EXACT_PATHS: &[&str] = &[".kube/config", ".docker/config.json"];
const TIER_A_PATH_PREFIXES: &[&str] = &[".ssh/", ".gnupg/", ".aws/", ".kube/", ".docker/"];
const TIER_A_EXACT_NAMES: &[&str] = &[
    ".env", ".ssh", ".gnupg", ".aws", ".kube", ".docker", ".netrc", ".npmrc", ".pypirc",
];
const TIER_A_NAME_PREFIXES: &[&str] = &[".env.", "id_rsa", "id_ecdsa", "id_ed25519"];
const TIER_A_NAME_SUFFIXES: &[&str] = &[".pem", ".key", ".p12", ".pfx", ".keystore", ".tfstate"];
const TIER_A_NAME_CONTAINS: &[&str] = &[".tfstate."];

/// Built-in Tier-A name policy applied again at the closing archive read.
/// Keep this predicate aligned with `kio_pipeline::scan::classify_secret`;
/// callers pass explicitly unignored Tier-A paths separately.
#[must_use]
pub fn is_tier_a_secret_name(path: &str) -> bool {
    let normalized = path.trim_start_matches('/').replace('\\', "/");
    let name = normalized.rsplit('/').next().unwrap_or(&normalized);
    let lower = name.to_ascii_lowercase();
    let lower_path = normalized.to_ascii_lowercase();
    TIER_A_EXACT_PATHS.contains(&lower_path.as_str())
        || TIER_A_PATH_PREFIXES
            .iter()
            .any(|prefix| lower_path.starts_with(prefix))
        || TIER_A_EXACT_NAMES.contains(&lower.as_str())
        || TIER_A_NAME_PREFIXES
            .iter()
            .any(|prefix| lower.starts_with(prefix))
        || TIER_A_NAME_SUFFIXES
            .iter()
            .any(|suffix| lower.ends_with(suffix))
        || TIER_A_NAME_CONTAINS
            .iter()
            .any(|needle| lower.contains(needle))
}

/// QA7: a canonical, deterministic text rendering of every built-in Tier
/// A/B pattern (this module's Tier A arrays plus
/// `kio_pipeline::scan::TIER_B_NEEDLES`) — the input to 10 §1.1's
/// `effective_ignore_hash` (`hash_bytes(tier_a_template_text().as_bytes())`
/// at the call site). A pattern addition/removal/edit in any of these arrays
/// changes this text, so it changes the hash — the property 10 §1.1
/// requires ("パターン更新が承認記録の同一性判定に反映される") that a fixed
/// version-string literal could not guarantee.
#[must_use]
pub fn tier_a_template_text(tier_b_needles: &[&str]) -> String {
    let mut text = String::new();
    for (label, patterns) in [
        ("exact_paths", TIER_A_EXACT_PATHS),
        ("path_prefixes", TIER_A_PATH_PREFIXES),
        ("exact_names", TIER_A_EXACT_NAMES),
        ("name_prefixes", TIER_A_NAME_PREFIXES),
        ("name_suffixes", TIER_A_NAME_SUFFIXES),
        ("name_contains", TIER_A_NAME_CONTAINS),
    ] {
        text.push_str(label);
        text.push(':');
        text.push_str(&patterns.join(","));
        text.push('\n');
    }
    text.push_str("tier_b_needles:");
    text.push_str(&tier_b_needles.join(","));
    text.push('\n');
    text
}

fn validate_store_directory(kio_dir: &Path) -> Result<()> {
    let metadata = match fs::symlink_metadata(kio_dir) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Err(KioError::invalid_usage("not a kio scope"));
        }
        Err(error) => {
            return Err(KioError::io(
                error.to_string(),
                kio_dir.display().to_string(),
            ));
        }
    };
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(unsafe_store_error(
            kio_dir,
            ".kio must be a real directory inside the selected scope root",
        ));
    }
    let resolved = kio_dir.canonicalize().kio_io(kio_dir)?;
    // Bound child indexing intentionally operates with the relative `.kio`
    // path below a retained cwd. Compare canonical paths in the same form;
    // ordinary callers already pass an absolute root-derived path.
    let declared = if kio_dir.is_absolute() {
        kio_dir.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|err| KioError::io(err.to_string(), "."))?
            .join(kio_dir)
    };
    if resolved != declared {
        return Err(unsafe_store_error(
            kio_dir,
            ".kio resolves outside the selected scope root",
        ));
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::{MetadataExt, PermissionsExt};

        if metadata.permissions().mode() & 0o077 != 0 {
            return Err(unsafe_store_error(
                kio_dir,
                ".kio must not be accessible to group or other principals",
            ));
        }
        if metadata.uid() != effective_uid() {
            return Err(unsafe_store_error(
                kio_dir,
                ".kio must be owned by the current effective user",
            ));
        }
    }
    Ok(())
}

#[cfg(unix)]
fn effective_uid() -> u32 {
    unsafe extern "C" {
        fn geteuid() -> u32;
    }
    // SAFETY: geteuid has no preconditions and only returns process metadata.
    unsafe { geteuid() }
}

fn unsafe_store_error(path: &Path, message: &str) -> KioError {
    KioError::new(
        "KIO-E-STORE-UNSAFE-001",
        message,
        json!({ "kio_path": path }),
        ExitCode::PermanentFailure,
    )
}

fn open_working_file_candidate(candidate: &WorkingFileCandidate) -> Result<File> {
    #[cfg(unix)]
    if let Some(root) = candidate.bound_root.as_deref() {
        return open_bound_scope_file_nofollow(root, &candidate.file_name, &candidate.path);
    }
    open_scope_file_nofollow(&candidate.path)
}

/// Open one direct source child using the scope descriptor retained by an
/// internal child index. The public path is diagnostic-only and never used for
/// lookup, so a post-bind rename cannot redirect a source read.
#[cfg(unix)]
fn open_bound_scope_file_nofollow(
    root: &File,
    file_name: &str,
    display_path: &Path,
) -> Result<File> {
    use cap_fs::MetadataExt;
    use cap_primitives::fs as cap_fs;

    let name = Path::new(file_name);
    if name.components().count() != 1
        || !matches!(name.components().next(), Some(Component::Normal(_)))
    {
        return Err(scope_file_changed_path(display_path));
    }
    let before = cap_fs::stat(root, name, cap_fs::FollowSymlinks::No)
        .map_err(|error| KioError::io(error.to_string(), display_path.display().to_string()))?;
    if !before.is_file() {
        return Err(scope_file_changed_path(display_path));
    }
    let mut options = cap_fs::OpenOptions::new();
    options.read(true);
    options._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let file = cap_fs::open(root, name, &options)
        .map_err(|error| KioError::io(error.to_string(), display_path.display().to_string()))?;
    let opened = cap_fs::Metadata::from_file(&file)
        .map_err(|error| KioError::io(error.to_string(), display_path.display().to_string()))?;
    let after = cap_fs::stat(root, name, cap_fs::FollowSymlinks::No)
        .map_err(|error| KioError::io(error.to_string(), display_path.display().to_string()))?;
    if !opened.is_file()
        || !after.is_file()
        || opened.dev() != before.dev()
        || opened.ino() != before.ino()
        || opened.dev() != after.dev()
        || opened.ino() != after.ino()
    {
        return Err(scope_file_changed_path(display_path));
    }
    Ok(file)
}

fn open_scope_file_nofollow(path: &Path) -> Result<File> {
    let before = fs::symlink_metadata(path).kio_io(path)?;
    if before.file_type().is_symlink() || !before.file_type().is_file() {
        return Err(scope_file_changed_path(path));
    }

    let mut options = OpenOptions::new();
    options.read(true);
    configure_scope_no_follow(&mut options);
    let file = options.open(path).kio_io(path)?;
    let opened = file.metadata().kio_io(path)?;
    let after = fs::symlink_metadata(path).kio_io(path)?;
    #[cfg(windows)]
    let same_identity = {
        let mut verification_options = OpenOptions::new();
        verification_options.read(true);
        configure_scope_no_follow(&mut verification_options);
        let verification = verification_options.open(path).kio_io(path)?;
        verification.metadata().kio_io(path)?.is_file()
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
        let count = file.read(&mut buffer[..read_cap]).kio_io(path)?;
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

fn stage_scope_file(
    kio_dir: &Path,
    candidate: WorkingFileCandidate,
    allowed: u64,
    limits: ArchiveLimits,
) -> Result<StagedWorkingFile> {
    let mut source = open_working_file_candidate(&candidate)?;
    let metadata = source.metadata().kio_io(&candidate.path)?;
    if metadata.len() > allowed {
        return Err(scope_input_oversized(
            &candidate.file_name,
            limits,
            metadata.len(),
        ));
    }
    let raw_base = kio_dir.join("objects/raw");
    let (temp_path, mut staged) = create_raw_staging_file(&raw_base)?;
    let result = (|| -> Result<(String, u64)> {
        let mut hasher = Sha256::new();
        let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
        let mut total = 0_u64;
        loop {
            let read_cap = allowed
                .saturating_sub(total)
                .saturating_add(1)
                .min(buffer.len() as u64) as usize;
            let count = source
                .read(&mut buffer[..read_cap])
                .kio_io(&candidate.path)?;
            if count == 0 {
                break;
            }
            total = total
                .checked_add(count as u64)
                .ok_or_else(|| scope_input_oversized(&candidate.file_name, limits, u64::MAX))?;
            if total > allowed {
                return Err(scope_input_oversized(&candidate.file_name, limits, total));
            }
            hasher.update(&buffer[..count]);
            staged.write_all(&buffer[..count]).kio_io(&temp_path)?;
        }
        if source.metadata().kio_io(&candidate.path)?.len() != total {
            return Err(scope_file_changed(&candidate.file_name));
        }
        staged.sync_all().kio_io(&temp_path)?;
        Ok((format!("sha256:{}", hex_digest(&hasher.finalize())), total))
    })();
    match result {
        Ok((raw_hash, size_bytes)) => Ok(StagedWorkingFile {
            candidate,
            temp_path,
            file: staged,
            raw_hash,
            size_bytes,
        }),
        Err(error) => {
            drop(staged);
            let _ = fs::remove_file(&temp_path);
            Err(error)
        }
    }
}

fn create_raw_staging_file(parent: &Path) -> Result<(PathBuf, File)> {
    for attempt in 0..16_u8 {
        let path = parent.join(format!(
            ".ingest-{}-{}-{attempt}",
            std::process::id(),
            unix_nanos()
        ));
        let mut options = OpenOptions::new();
        options.write(true).read(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match options.open(&path) {
            Ok(file) => return Ok((path, file)),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
        }
    }
    Err(KioError::io(
        "could not allocate a unique raw-ingest staging file",
        parent.display().to_string(),
    ))
}

/// Remove crash-orphaned raw-ingest transaction files while the caller holds
/// the scope store lock. The namespace walk and aggregate physical bytes are
/// bounded; every candidate is opened no-follow and must be a single-link,
/// bounded regular file before unlinking.
pub fn cleanup_orphan_raw_ingest_temps(kio_dir: &Path) -> Result<u64> {
    const MAX_RAW_DIRECTORY_ENTRIES: usize = 100_000;
    const MAX_ORPHAN_BYTES: u64 = DEFAULT_MAX_ARCHIVE_SCOPE_BYTES;

    validate_store_directory(kio_dir)?;
    let objects = kio_dir.join("objects");
    let raw_base = objects.join("raw");
    for directory in [&objects, &raw_base] {
        validate_ingest_directory(directory)?;
    }

    let mut visited = 0_usize;
    let mut total_bytes = 0_u64;
    let mut removed = 0_u64;
    let entries = fs::read_dir(&raw_base).kio_io(&raw_base)?;
    for entry in entries {
        let entry = entry.kio_io(&raw_base)?;
        visited = visited.saturating_add(1);
        if visited > MAX_RAW_DIRECTORY_ENTRIES {
            return Err(orphan_raw_ingest_error(
                &raw_base,
                "raw object directory exceeds the orphan-cleanup entry limit",
            ));
        }
        if !entry
            .file_name()
            .as_encoded_bytes()
            .starts_with(b".ingest-")
        {
            continue;
        }

        let path = entry.path();
        let listed = fs::symlink_metadata(&path).kio_io(&path)?;
        if listed.file_type().is_symlink()
            || !listed.file_type().is_file()
            || listed.len() > MAX_RAW_OBJECT_BYTES
        {
            return Err(orphan_raw_ingest_error(
                &path,
                "raw-ingest orphan is not a bounded regular file",
            ));
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            if listed.nlink() != 1 {
                return Err(orphan_raw_ingest_error(
                    &path,
                    "raw-ingest orphan has an unexpected hard-link count",
                ));
            }
        }
        #[cfg(windows)]
        if !crate::cas::windows_regular_file_is_safe(&path).kio_io(&path)? {
            return Err(orphan_raw_ingest_error(
                &path,
                "raw-ingest orphan is a reparse point or hard link",
            ));
        }

        let opened = open_scope_file_nofollow(&path)?;
        let opened_metadata = opened.metadata().kio_io(&path)?;
        if opened_metadata.len() != listed.len() || opened_metadata.len() > MAX_RAW_OBJECT_BYTES {
            return Err(orphan_raw_ingest_error(
                &path,
                "raw-ingest orphan changed while it was opened",
            ));
        }
        total_bytes = total_bytes
            .checked_add(opened_metadata.len())
            .ok_or_else(|| {
                orphan_raw_ingest_error(&raw_base, "raw-ingest orphan byte count overflow")
            })?;
        if total_bytes > MAX_ORPHAN_BYTES {
            return Err(orphan_raw_ingest_error(
                &raw_base,
                "raw-ingest orphans exceed the aggregate cleanup byte limit",
            ));
        }
        drop(opened);
        fs::remove_file(&path).kio_io(&path)?;
        removed = removed.saturating_add(1);
    }
    if removed > 0
        && let Ok(directory) = File::open(&raw_base)
    {
        let _ = directory.sync_all();
    }
    Ok(removed)
}

fn validate_ingest_directory(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path).kio_io(path)?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(orphan_raw_ingest_error(
            path,
            "raw-ingest namespace ancestor is not a real directory",
        ));
    }
    #[cfg(windows)]
    if !crate::cas::windows_directory_is_real(path).kio_io(path)? {
        return Err(orphan_raw_ingest_error(
            path,
            "raw-ingest namespace ancestor is a reparse point",
        ));
    }
    Ok(())
}

fn orphan_raw_ingest_error(path: &Path, message: &str) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        message,
        json!({ "path": path }),
        ExitCode::PermanentFailure,
    )
}

/// U19/LC22: a public tombstone (or fsck-only erase receipt) no longer
/// permanently rejects identical-byte re-ingest — that block is reversed into
/// the resurrection flow (retire-on-republish, see
/// [`Repository::retire_resurrected_after_publish`]). Only an active
/// post-`prepared` purge journal barrier for this exact raw_hash (an
/// in-progress, not-yet-complete purge) still gates publication.
fn ensure_raw_publication_allowed(purge: &PurgeState, raw_hash: &str) -> Result<()> {
    if purge.barrier_blocks(raw_hash)? {
        return Err(KioError::new(
            "KIO-E-PURGE-INCOMPLETE-001",
            "raw publication is blocked by an active purge transaction",
            json!({ "component": "raw_ingest" }),
            ExitCode::PartialFailure,
        ));
    }
    Ok(())
}

#[cfg(unix)]
fn bound_marker_exists(kio: &File, namespace: &str, raw_hash: &str) -> Result<bool> {
    use cap_primitives::fs as cap_fs;

    let digest = raw_hash
        .strip_prefix("sha256:")
        .ok_or_else(|| KioError::schema("scheduled marker lookup requires a sha256 raw hash"))?;
    if digest.len() != 64 || !digest.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(KioError::schema(
            "scheduled marker lookup requires a sha256 raw hash",
        ));
    }
    let mut directory = kio
        .try_clone()
        .map_err(|error| KioError::io(error.to_string(), namespace))?;
    for component in Path::new(namespace).components().chain([
        Component::Normal(std::ffi::OsStr::new(&digest[..2])),
        Component::Normal(std::ffi::OsStr::new(&digest[2..4])),
    ]) {
        let Component::Normal(component) = component else {
            continue;
        };
        directory = match cap_fs::open_dir_nofollow(&directory, Path::new(component)) {
            Ok(next) => next,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
            Err(error) => return Err(KioError::io(error.to_string(), namespace)),
        };
    }
    match cap_fs::stat(&directory, Path::new(digest), cap_fs::FollowSymlinks::No) {
        Ok(metadata) if metadata.is_file() => Ok(true),
        Ok(_) => Err(unsafe_store_error(
            Path::new(namespace),
            "purge marker leaf is not a regular file",
        )),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(KioError::io(error.to_string(), namespace)),
    }
}

/// Debug-only synchronization seam for descriptor-replacement integration
/// tests. Production builds never inspect the environment or wait.
#[cfg(unix)]
fn wait_at_bound_snapshot_auto_layout_barrier() {
    wait_at_bound_snapshot_auto_barrier("KIO_TEST_SNAPSHOT_AUTO_BOUND_LAYOUT_READY");
}

/// Debug-only synchronization seams for scheduled-writer race tests.  The
/// ready/release protocol is intentionally identical across seams so tests can
/// mutate one authority input at a precisely named boundary.
fn wait_at_bound_snapshot_auto_pre_checkpoint_barrier() {
    wait_at_bound_snapshot_auto_barrier("KIO_TEST_SNAPSHOT_AUTO_PRE_CHECKPOINT_READY");
}

fn wait_at_bound_snapshot_auto_after_state_write_barrier() {
    wait_at_bound_snapshot_auto_barrier("KIO_TEST_SNAPSHOT_AUTO_AFTER_STATE_WRITE_READY");
}

fn wait_at_bound_snapshot_auto_barrier(variable: &str) {
    if !cfg!(debug_assertions) {
        return;
    }
    let Some(ready_path) = std::env::var_os(variable) else {
        return;
    };
    let ready_path = PathBuf::from(ready_path);
    if fs::write(&ready_path, b"ready").is_err() {
        return;
    }
    let release_path = ready_path.with_extension("release");
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
    while !release_path.exists() && std::time::Instant::now() < deadline {
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
}

fn attach_pending_normalize(
    tree_entry: &mut TreeEntry,
    file_name: &str,
    normalize_by_path: &BTreeMap<String, PendingNormalizeRef>,
) {
    if let Some(pending) = normalize_by_path.get(file_name) {
        if pending.expected_raw_hash == tree_entry.raw_hash {
            tree_entry.normalize = Some(pending.normalize.clone());
        } else {
            eprintln!(
                "warning: normalization metadata not attached because {file_name} changed after normalization"
            );
        }
    }
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

fn scope_input_oversized(file_name: &str, limits: ArchiveLimits, actual: u64) -> KioError {
    KioError::new(
        "KIO-E-SCOPE-INPUT-OVERSIZED-001",
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

fn scope_tree_entries_oversized(observed: usize) -> KioError {
    KioError::new(
        "KIO-E-SCOPE-INPUT-OVERSIZED-001",
        "scope tree entry count exceeds the persisted tree limit",
        json!({
            "observed_entries": observed,
            "max_tree_entries": MAX_TREE_ENTRIES,
        }),
        ExitCode::PermanentFailure,
    )
}

fn scope_file_changed(file_name: &str) -> KioError {
    KioError::new(
        "KIO-E-SCOPE-FILE-CHANGED-001",
        "scope file changed while it was being archived",
        json!({ "path": file_name }),
        ExitCode::Failure,
    )
}

fn scope_file_changed_path(path: &Path) -> KioError {
    KioError::new(
        "KIO-E-SCOPE-FILE-CHANGED-001",
        "scope path no longer identifies the checked regular file",
        json!({ "path": path }),
        ExitCode::Failure,
    )
}

fn snapshot_authority_changed(message: &str) -> KioError {
    KioError::new(
        "KIO-E-SNAPSHOT-AUTHORITY-CHANGED-001",
        message,
        json!({}),
        ExitCode::PartialFailure,
    )
}

/// Restrict a directory that may hold document bytes / secrets / usage data to
/// owner-only access (0700) on unix (P2). Applied to the `.kio` tree and the
/// device data dir (`~/.local/share/kio`) at creation so a multi-user host
/// cannot read another user's archive. A 0700 parent blocks traversal into the
/// whole subtree regardless of child modes. No-op on non-unix.
pub fn restrict_dir_to_owner(dir: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(dir, fs::Permissions::from_mode(0o700)).kio_io(dir)?;
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
fn is_store_not_found(error: &KioError) -> bool {
    error.error_code() == "KIO-E-STORE-NOT-FOUND-001"
}

/// R17-5: a commit operand (`diff`/`tag` hash literal, or a tag-name target) whose
/// commit object is gone (shallow: discarded / corrupt) folds into
/// KIO-E-COMMIT-SHALLOW-001 — the same class every other shallow-commit site raises
/// (R16-1 / R16-5) — instead of a raw, opaque KIO-E-STORE-NOT-FOUND-001. Used by
/// `resolve_commit`, which runs before `diff_side_tree`'s R16-5 absorption, so
/// without this a hash-literal / tag-name shallow commit would bypass the
/// COMMIT-SHALLOW contract that the `HEAD` operand already reaches. Kept generic (no
/// diff side) because `resolve_commit` is shared by `diff` and `tag`; the diff side
/// is still named for the tree-GC case that reaches `diff_side_tree`.
fn resolve_commit_shallow_error(commit_hash: &str) -> KioError {
    KioError::commit_shallow(
        "referenced commit object is missing (shallow: discarded / corrupt); \
         restore the commit object or reference a non-shallow commit",
        commit_hash.to_owned(),
    )
}

/// R16-5: the `diff` shallow-side error, naming which operand (`a`/`b`) is shallow.
fn diff_side_shallow_error(side: &str, commit_hash: &str) -> KioError {
    KioError::new(
        "KIO-E-COMMIT-SHALLOW-001",
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
    // This is a pre-stable store format, not the package's semver
    // compatibility range.  The current reader understands exactly the
    // current on-disk format; every different string is either older,
    // malformed, or newer and must take the version-specific fail-closed
    // path before current-schema validation.
    if version == KIO_FORMAT_VERSION {
        Ok(())
    } else {
        Err(KioError::incompatible_format(version))
    }
}

thread_local! {
    /// Reentrancy depth per `.lock` path for the current thread. A whole-command
    /// lock held by `kio index`/`repair`/`reindex` must not deadlock against the
    /// `snapshot` sub-step re-acquiring the same lock inside the same process.
    static LOCK_DEPTH: RefCell<HashMap<PathBuf, u32>> = RefCell::new(HashMap::new());
    /// Distinct lock names in one directory (notably `.lock` followed by
    /// `purge-publication.lock`) share the same directory-flock open file
    /// description within a thread. This keeps the crash-released gate
    /// reentrant without weakening cross-process serialization.
    static LOCK_GATE_POOL: RefCell<HashMap<PathBuf, (u32, File)>> = RefCell::new(HashMap::new());
}

#[cfg(unix)]
struct LockGate {
    key: PathBuf,
    _file: File,
}

#[cfg(unix)]
fn unlock_flock(file: &File) {
    use std::os::fd::AsRawFd;

    // Closing the local descriptor is normally sufficient, but a concurrent
    // fork may retain the same open-file description until its exec boundary.
    // Explicit unlock releases that shared kernel lock at the logical guard
    // boundary instead of extending it into the child process transiently.
    let _ = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_UN) };
}

#[cfg(unix)]
impl Drop for LockGate {
    fn drop(&mut self) {
        let final_owner = LOCK_GATE_POOL.with(|pool| {
            let mut pool = pool.borrow_mut();
            let Some((count, _)) = pool.get_mut(&self.key) else {
                return false;
            };
            *count -= 1;
            if *count == 0 {
                pool.remove(&self.key);
                true
            } else {
                false
            }
        });
        if final_owner {
            unlock_flock(&self._file);
        }
    }
}

#[cfg(unix)]
struct BoundLockGate {
    file: File,
}

#[cfg(unix)]
impl Drop for BoundLockGate {
    fn drop(&mut self) {
        unlock_flock(&self.file);
    }
}

/// RAII guard over the `.kio/.lock` store lock (05 §6). Reentrant within a
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
    /// Kernel-held, crash-released serialization gate for the complete
    /// acquire/reclaim/release interval. The public `.lock` remains the
    /// interoperable on-disk protocol; this descriptor gate closes the final
    /// double-read-to-exchange race between cooperating Kio writers.
    #[cfg(unix)]
    _gate: Option<LockGate>,
    /// Windows retains both handles. The parent is resolved component-by-
    /// component without following reparses; the owner handle denies write,
    /// delete, and rename sharing until the guard is released.
    #[cfg(windows)]
    _windows_parent: Option<File>,
    #[cfg(windows)]
    _windows_owner: Option<File>,
}

impl StoreLock {
    pub fn acquire(kio_dir: &Path) -> Result<Self> {
        let lock = Self::acquire_path(kio_dir.join(".lock"))?;
        // The outer acquisition already performed this check while it owned
        // the real lock.  Besides avoiding redundant work, skipping the
        // ambient-path read for a nested acquisition lets a descriptor-bound
        // automatic writer safely reuse this ordinary API.
        if lock.reentrant {
            return Ok(lock);
        }
        // Acquire first, then inspect through the strict GC parser. This closes
        // the marker-publication race for every ordinary writer sharing this
        // central lock entrypoint; GC uses its retained-descriptor counterpart.
        if let Err(error) = crate::gc::ensure_no_active_sweep(kio_dir) {
            drop(lock);
            return Err(error);
        }
        Ok(lock)
    }

    /// Acquire a lock at an explicit file path. Used for device-global locks that
    /// live outside any single `.kio` store (F8) — e.g. serializing a
    /// budget/cost read-check-append across every scope on the device (the
    /// pre-2026-07-18 JSONL cost ledger used this for exactly that; the current
    /// `cost-ledger.sqlite`, `kio_pipeline::ledger`, instead serializes writers via
    /// its own `BEGIN IMMEDIATE` transactions — 04-pipeline.md §5.4/§5.8 — so this
    /// primitive no longer has a live device-global caller, but remains available
    /// for any future one). Same reentrancy (thread-local depth, keyed by the lock
    /// path) and stale-reclaim semantics as [`acquire`]; the parent directory is
    /// created if missing.
    pub fn acquire_path(path: PathBuf) -> Result<Self> {
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
                #[cfg(unix)]
                _gate: None,
                #[cfg(windows)]
                _windows_parent: None,
                #[cfg(windows)]
                _windows_owner: None,
            });
        }

        #[cfg(windows)]
        {
            return Self::acquire_path_windows(path, pid);
        }

        #[cfg(not(windows))]
        {
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent).kio_io(parent)?;
            }

            #[cfg(unix)]
            let gate = acquire_lock_gate(&path)?;

            let token = new_lock_token(pid);
            let canonical = canonical_lock_bytes(pid, &token)?;
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => {
                    file.write_all(&canonical).kio_io(&path)?;
                    file.sync_all().kio_io(&path)?;
                }
                Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {
                    if !reclaim_stale_lock(&path, &canonical)? {
                        return Err(KioError::locked(path.display().to_string()));
                    }
                }
                Err(err) => return Err(KioError::io(err.to_string(), path.display().to_string())),
            }
            LOCK_DEPTH.with(|depth| depth.borrow_mut().insert(path.clone(), 1));
            Ok(Self {
                path,
                pid,
                token,
                reentrant: false,
                #[cfg(unix)]
                _gate: Some(gate),
                #[cfg(windows)]
                _windows_parent: None,
                #[cfg(windows)]
                _windows_owner: None,
            })
        }
    }

    /// Windows ordinary writers use retained capability-relative handles rather
    /// than the path-based token-checked fallback. A live owner shares READ
    /// only, so a second writer cannot open it for DELETE or replace it.
    #[cfg(windows)]
    fn acquire_path_windows(path: PathBuf, pid: u32) -> Result<Self> {
        let parent = open_windows_lock_parent(&path)?;
        let leaf = windows_lock_leaf(&path)?;
        let token = new_lock_token(pid);
        let canonical = canonical_lock_bytes(pid, &token)?;
        let owner = match create_windows_lock(&parent, leaf, &canonical) {
            Ok(owner) => owner,
            Err(error)
                if matches!(
                    error.kind(),
                    std::io::ErrorKind::AlreadyExists | std::io::ErrorKind::PermissionDenied
                ) =>
            {
                reclaim_windows_stale_lock(&parent, leaf, &canonical)
                    .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?
                    .ok_or_else(|| KioError::locked(path.display().to_string()))?
            }
            Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
        };
        LOCK_DEPTH.with(|depth| depth.borrow_mut().insert(path.clone(), 1));
        Ok(Self {
            path,
            pid,
            token,
            reentrant: false,
            _windows_parent: Some(parent),
            _windows_owner: Some(owner),
        })
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
        // macOS/Linux exchange rather than check-then-unlink. Windows validates
        // and deletes only the retained owned handle; it never unlinks a path.
        if released && !self.reentrant {
            #[cfg(windows)]
            if let Some(owner) = self._windows_owner.as_ref() {
                let _ = release_windows_owned_lock(owner, self.pid, &self.token);
            }
            #[cfg(not(windows))]
            let _ = release_ordinary_lock(&self.path, self.pid, &self.token);
        }
        // `gate` drops after the on-disk release operation, and the kernel
        // automatically releases it after a process crash.
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
struct LockFile {
    pid: u32,
    token: String,
    created_at: String,
}

/// Reserved owner written by the lock-release exchange protocol. No supported
/// platform can assign this value to a Kio process; treating it as dead is part
/// of the on-disk protocol and must not depend on spawning a liveness probe.
const RELEASED_LOCK_PID: u32 = u32::MAX;

/// The lock record is deliberately tiny; reject an oversized leaf before
/// deserializing so a hostile lock path cannot become an unbounded allocation.
#[cfg(windows)]
const MAX_WINDOWS_LOCK_BYTES: u64 = 4096;

/// Resolve/create a lock parent from a filesystem root without re-resolving
/// ambient parents afterwards. `open_dir_nofollow` rejects symlink/reparse
/// components; the by-handle identity check also rejects junctions.
#[cfg(windows)]
fn open_windows_lock_parent(path: &Path) -> Result<File> {
    use cap_primitives::{ambient_authority, fs as cap_fs};

    if path
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(KioError::invalid_usage(
            "lock path must not contain parent traversal",
        ));
    }
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?
            .join(path)
    };
    let parent = absolute
        .parent()
        .ok_or_else(|| KioError::invalid_usage("lock path has no parent"))?;
    let mut root = PathBuf::new();
    let mut components = Vec::new();
    for component in parent.components() {
        match component {
            Component::Prefix(prefix) => root.push(prefix.as_os_str()),
            Component::RootDir => root.push(component.as_os_str()),
            Component::CurDir => {}
            Component::Normal(component) => components.push(component.to_os_string()),
            Component::ParentDir => {
                return Err(KioError::invalid_usage(
                    "lock path must not contain parent traversal",
                ));
            }
        }
    }
    if root.as_os_str().is_empty() {
        return Err(KioError::invalid_usage("lock path must be rooted"));
    }
    let mut directory = cap_fs::open_ambient_dir(&root, ambient_authority())
        .map_err(|error| KioError::io(error.to_string(), root.display().to_string()))?;
    if crate::cas::windows_directory_handle_identity(&directory).is_none() {
        return Err(KioError::locked(path.display().to_string()));
    }
    for component in components {
        directory = match cap_fs::open_dir_nofollow(&directory, Path::new(&component)) {
            Ok(directory) => directory,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let options = cap_fs::DirOptions::new();
                match cap_fs::create_dir(&directory, Path::new(&component), &options) {
                    Ok(()) => {}
                    Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                    Err(error) => {
                        return Err(KioError::io(error.to_string(), path.display().to_string()));
                    }
                }
                cap_fs::open_dir_nofollow(&directory, Path::new(&component))
                    .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?
            }
            Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
        };
        if crate::cas::windows_directory_handle_identity(&directory).is_none() {
            return Err(KioError::locked(path.display().to_string()));
        }
    }
    Ok(directory)
}

#[cfg(windows)]
fn windows_lock_leaf(path: &Path) -> Result<&Path> {
    let leaf = path
        .file_name()
        .filter(|leaf| !leaf.is_empty())
        .map(Path::new)
        .ok_or_else(|| KioError::invalid_usage("lock path must name a leaf"))?;
    Ok(leaf)
}

#[cfg(windows)]
fn windows_lock_open_options(
    create_new: bool,
    access_mode: u32,
) -> cap_primitives::fs::OpenOptions {
    use cap_primitives::fs::{FollowSymlinks, OpenOptionsExt};
    use windows_sys::Win32::Storage::FileSystem::{FILE_FLAG_OPEN_REPARSE_POINT, FILE_SHARE_READ};

    let mut options = cap_primitives::fs::OpenOptions::new();
    options
        .read(true)
        .write(create_new)
        .create_new(create_new)
        .access_mode(access_mode)
        .share_mode(FILE_SHARE_READ)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
        ._cap_fs_ext_follow(FollowSymlinks::No);
    options
}

#[cfg(windows)]
fn create_windows_lock(parent: &File, leaf: &Path, bytes: &[u8]) -> std::io::Result<File> {
    use cap_primitives::fs as cap_fs;
    use windows_sys::Win32::Foundation::{GENERIC_READ, GENERIC_WRITE};
    use windows_sys::Win32::Storage::FileSystem::{DELETE, SYNCHRONIZE};

    let options =
        windows_lock_open_options(true, GENERIC_READ | GENERIC_WRITE | DELETE | SYNCHRONIZE);
    let mut file = cap_fs::open(parent, leaf, &options)?;
    let published = (|| -> std::io::Result<()> {
        file.write_all(bytes)?;
        file.sync_all()?;
        let (record, _) = read_windows_lock(&file).map_err(|error| {
            std::io::Error::new(std::io::ErrorKind::InvalidData, error.to_string())
        })?;
        if canonical_lock_bytes_for(&record).map_err(|error| {
            std::io::Error::new(std::io::ErrorKind::InvalidData, error.to_string())
        })? != bytes
        {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "new Windows lock record differs from its canonical bytes",
            ));
        }
        Ok(())
    })();
    if let Err(error) = published {
        // The create_new handle is the exact object we just created. Do not
        // unlink a path here: a partial record must not wedge future writers,
        // and a competing replacement must never be removed.
        let _ = delete_windows_lock_handle(&file);
        return Err(error);
    }
    Ok(file)
}

#[cfg(windows)]
fn read_windows_lock(file: &File) -> Result<(LockFile, crate::cas::WindowsRegularFileIdentity)> {
    let identity = crate::cas::windows_regular_file_handle_identity(file)
        .ok_or_else(|| KioError::locked("Windows lock leaf is not a single-link regular file"))?;
    let length = file
        .metadata()
        .map_err(|error| KioError::io(error.to_string(), ".lock"))?
        .len();
    if length > MAX_WINDOWS_LOCK_BYTES {
        return Err(KioError::locked(
            "Windows lock leaf exceeds the bounded record size",
        ));
    }
    let mut reader = file
        .try_clone()
        .map_err(|error| KioError::io(error.to_string(), ".lock"))?;
    reader
        .seek(SeekFrom::Start(0))
        .map_err(|error| KioError::io(error.to_string(), ".lock"))?;
    let mut bytes = Vec::with_capacity(length as usize);
    reader
        .read_to_end(&mut bytes)
        .map_err(|error| KioError::io(error.to_string(), ".lock"))?;
    if bytes.len() as u64 != length || bytes.len() as u64 > MAX_WINDOWS_LOCK_BYTES {
        return Err(KioError::locked(
            "Windows lock leaf changed while being read",
        ));
    }
    let lock: LockFile = serde_json::from_slice(&bytes)
        .map_err(|_| KioError::locked("Windows lock is malformed"))?;
    if canonical_lock_bytes_for(&lock)? != bytes
        || crate::cas::windows_regular_file_handle_identity(file) != Some(identity)
    {
        return Err(KioError::locked(
            "Windows lock is not canonical or changed identity",
        ));
    }
    Ok((lock, identity))
}

#[cfg(windows)]
fn delete_windows_lock_handle(file: &File) -> std::io::Result<()> {
    use std::mem::size_of;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        FILE_DISPOSITION_FLAG_DELETE, FILE_DISPOSITION_FLAG_POSIX_SEMANTICS,
        FILE_DISPOSITION_INFO_EX, FileDispositionInfoEx, SetFileInformationByHandle,
    };

    let info = FILE_DISPOSITION_INFO_EX {
        Flags: FILE_DISPOSITION_FLAG_DELETE | FILE_DISPOSITION_FLAG_POSIX_SEMANTICS,
    };
    // SAFETY: `info` has the exact Win32 layout and `file` retains DELETE access.
    if unsafe {
        SetFileInformationByHandle(
            file.as_raw_handle(),
            FileDispositionInfoEx,
            std::ptr::addr_of!(info).cast(),
            size_of::<FILE_DISPOSITION_INFO_EX>() as u32,
        )
    } == 0
    {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(())
    }
}

/// Return a newly owned lock only after deleting the exact retained stale
/// handle. If a competing writer creates the leaf in the absent interval, it
/// wins and this caller reports contention without deleting the new object.
#[cfg(windows)]
fn reclaim_windows_stale_lock(
    parent: &File,
    leaf: &Path,
    replacement: &[u8],
) -> Result<Option<File>> {
    use cap_primitives::fs as cap_fs;
    use windows_sys::Win32::Foundation::GENERIC_READ;
    use windows_sys::Win32::Storage::FileSystem::{DELETE, SYNCHRONIZE};

    let options = windows_lock_open_options(false, GENERIC_READ | DELETE | SYNCHRONIZE);
    let stale = match cap_fs::open(parent, leaf, &options) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) if error.kind() == std::io::ErrorKind::PermissionDenied => return Ok(None),
        Err(error) => return Err(KioError::io(error.to_string(), ".lock")),
    };
    let (old, identity) = read_windows_lock(&stale)?;
    if process_is_alive(old.pid) {
        return Ok(None);
    }
    if crate::cas::windows_regular_file_handle_identity(&stale) != Some(identity) {
        return Err(KioError::locked("Windows stale lock changed identity"));
    }
    delete_windows_lock_handle(&stale).map_err(|error| KioError::io(error.to_string(), ".lock"))?;
    drop(stale);
    match create_windows_lock(parent, leaf, replacement) {
        Ok(file) => Ok(Some(file)),
        Err(error)
            if matches!(
                error.kind(),
                std::io::ErrorKind::AlreadyExists | std::io::ErrorKind::PermissionDenied
            ) =>
        {
            Ok(None)
        }
        Err(error) => Err(KioError::io(error.to_string(), ".lock")),
    }
}

#[cfg(windows)]
fn release_windows_owned_lock(file: &File, pid: u32, token: &str) -> Result<()> {
    let (owned, _) = read_windows_lock(file)?;
    if owned.pid != pid || owned.token != token {
        return Ok(());
    }
    delete_windows_lock_handle(file).map_err(|error| KioError::io(error.to_string(), ".lock"))
}

#[cfg(unix)]
fn reclaim_stale_lock(path: &Path, replacement: &[u8]) -> Result<bool> {
    #[cfg(not(any(target_os = "macos", target_os = "linux")))]
    {
        return reclaim_stale_lock_token_checked(path, replacement);
    }
    #[cfg(any(target_os = "macos", target_os = "linux"))]
    {
        let Some(old) = read_lock_snapshot(path)? else {
            return Ok(false);
        };
        if process_is_alive(old.lock.pid) {
            return Ok(false);
        }
        let Some(again) = read_lock_snapshot(path)? else {
            return Ok(false);
        };
        if old != again || process_is_alive(again.lock.pid) {
            return Ok(false);
        }
        let parent = path
            .parent()
            .ok_or_else(|| KioError::io("lock path has no parent", path.display().to_string()))?;
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(|| KioError::locked(path.display().to_string()))?;
        let temp_name = format!(".{name}.reclaimed-{}-{}", std::process::id(), unix_nanos());
        let temp = parent.join(&temp_name);
        let mut temp_file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .kio_io(&temp)?;
        temp_file.write_all(replacement).kio_io(&temp)?;
        temp_file.sync_all().kio_io(&temp)?;
        drop(temp_file);
        let Some(current) = read_lock_snapshot(path)? else {
            return Ok(false);
        };
        if current != old {
            return Ok(false);
        }
        let directory = File::open(parent).kio_io(parent)?;
        exchange_bound_lock(&directory, name, &directory, &temp_name)?;
        let expected_replacement = parse_canonical_lock(replacement)?;
        let active_ok = read_lock_snapshot(path).is_ok_and(|snapshot| {
            snapshot.is_some_and(|snapshot| {
                snapshot.bytes == replacement && snapshot.lock == expected_replacement
            })
        });
        let stale_ok =
            read_lock_snapshot(&temp).is_ok_and(|snapshot| snapshot == Some(old.clone()));
        if !active_ok || !stale_ok {
            // Both postconditions must hold before a compensating exchange could
            // be safe. Retain the names instead: no concurrent replacement is
            // removed or overwritten by a cleanup attempt.
            return Err(bound_lock_corrupt(
                "ordinary stale lock exchange validation failed",
            ));
        }
        fs::remove_file(&temp).kio_io(&temp)?;
        directory.sync_all().kio_io(parent)?;
        Ok(true)
    }
}

#[cfg(not(any(unix, windows)))]
fn reclaim_stale_lock(path: &Path, replacement: &[u8]) -> Result<bool> {
    // GC itself is rejected before marker publication on platforms without a
    // descriptor-relative sweep lock.  Ordinary StoreLock remains a supported
    // writer primitive there, so retain its established create/read/reclaim
    // behavior instead of leaving every released lock permanently live.
    reclaim_stale_lock_token_checked(path, replacement)
}

#[cfg(unix)]
fn release_ordinary_lock(path: &Path, pid: u32, token: &str) -> Result<()> {
    #[cfg(not(any(target_os = "macos", target_os = "linux")))]
    {
        return release_ordinary_lock_token_checked(path, pid, token);
    }
    #[cfg(any(target_os = "macos", target_os = "linux"))]
    {
        let Some(owned) = read_lock_snapshot(path)? else {
            return Ok(());
        };
        if owned.lock.pid != pid || owned.lock.token != token {
            return Ok(());
        }
        let parent = path
            .parent()
            .ok_or_else(|| KioError::io("lock path has no parent", path.display().to_string()))?;
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(|| KioError::locked(path.display().to_string()))?;
        let temp_name = format!(".{name}.released-{}-{}", std::process::id(), unix_nanos());
        let temp = parent.join(&temp_name);
        let sentinel = canonical_lock_bytes(RELEASED_LOCK_PID, &new_lock_token(RELEASED_LOCK_PID))?;
        let mut temp_file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .kio_io(&temp)?;
        temp_file.write_all(&sentinel).kio_io(&temp)?;
        temp_file.sync_all().kio_io(&temp)?;
        drop(temp_file);
        if read_lock_snapshot(path)? != Some(owned.clone()) {
            return Ok(());
        }
        let directory = File::open(parent).kio_io(parent)?;
        exchange_bound_lock(&directory, name, &directory, &temp_name)?;
        let sentinel_lock = parse_canonical_lock(&sentinel)?;
        let active_ok = read_lock_snapshot(path).is_ok_and(|snapshot| {
            snapshot.is_some_and(|snapshot| {
                snapshot.bytes == sentinel && snapshot.lock == sentinel_lock
            })
        });
        let archived_ok = read_lock_snapshot(&temp).is_ok_and(|snapshot| snapshot == Some(owned));
        if !active_ok || !archived_ok {
            return Err(bound_lock_corrupt(
                "ordinary lock release exchange validation failed",
            ));
        }
        fs::remove_file(&temp).kio_io(&temp)?;
        directory.sync_all().kio_io(parent)
    }
}

#[cfg(not(any(unix, windows)))]
fn release_ordinary_lock(path: &Path, pid: u32, token: &str) -> Result<()> {
    release_ordinary_lock_token_checked(path, pid, token)
}

/// Token-checked ordinary-lock handling on platforms without the macOS/Linux
/// exchange primitive. GC refuses to start there before marker publication;
/// normal writers retain this bounded stale/release behavior so they cannot
/// wedge after one command.
#[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
fn reclaim_stale_lock_token_checked(path: &Path, replacement: &[u8]) -> Result<bool> {
    let Some(old) = read_lock_file_token_checked(path)? else {
        return Ok(false);
    };
    if process_is_alive(old.pid) {
        return Ok(false);
    }
    let Some(current) = read_lock_file_token_checked(path)? else {
        return Ok(false);
    };
    if current != old || process_is_alive(current.pid) {
        return Ok(false);
    }
    match fs::remove_file(path) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
    }
    let mut file = match OpenOptions::new().write(true).create_new(true).open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => return Ok(false),
        Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
    };
    file.write_all(replacement).kio_io(path)?;
    file.sync_all().kio_io(path)?;
    Ok(true)
}

#[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
fn release_ordinary_lock_token_checked(path: &Path, pid: u32, token: &str) -> Result<()> {
    let Some(owned) = read_lock_file_token_checked(path)? else {
        return Ok(());
    };
    if owned.pid != pid || owned.token != token {
        return Ok(());
    }
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(KioError::io(error.to_string(), path.display().to_string())),
    }
}

#[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
fn read_lock_file_token_checked(path: &Path) -> Result<Option<LockFile>> {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
    };
    let lock: LockFile =
        serde_json::from_slice(&bytes).map_err(|_| KioError::locked(path.display().to_string()))?;
    if canonical_lock_bytes_for(&lock)? != bytes {
        return Err(KioError::locked(path.display().to_string()));
    }
    Ok(Some(lock))
}

#[cfg(windows)]
fn process_is_alive(pid: u32) -> bool {
    if pid == RELEASED_LOCK_PID {
        return false;
    }
    if pid == std::process::id() {
        return true;
    }

    use windows_sys::Win32::Foundation::{
        CloseHandle, ERROR_INVALID_PARAMETER, GetLastError, STILL_ACTIVE,
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

#[cfg(unix)]
fn process_is_alive(pid: u32) -> bool {
    if pid == RELEASED_LOCK_PID {
        return false;
    }
    if pid == std::process::id() {
        return true;
    }

    // PID zero names a process group rather than a process, and values above
    // pid_t's positive range cannot name a Unix process.
    if pid == 0 || pid > libc::pid_t::MAX as u32 {
        return false;
    }
    // SAFETY: signal zero performs no delivery. ESRCH is the sole definite
    // absence result; EPERM and every other error are conservatively live.
    if unsafe { libc::kill(pid as libc::pid_t, 0) } == 0 {
        true
    } else {
        std::io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
    }
}

#[cfg(all(not(unix), not(windows)))]
fn process_is_alive(pid: u32) -> bool {
    pid != RELEASED_LOCK_PID
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

#[cfg(unix)]
fn acquire_lock_gate(lock_path: &Path) -> Result<LockGate> {
    use std::os::fd::AsRawFd;

    let parent = lock_path
        .parent()
        .ok_or_else(|| KioError::io("lock path has no parent", lock_path.display().to_string()))?;
    let key = parent.to_path_buf();
    if let Some(cloned) = LOCK_GATE_POOL.with(|pool| {
        let mut pool = pool.borrow_mut();
        let (count, file) = pool.get_mut(&key)?;
        let cloned = file.try_clone().ok()?;
        *count += 1;
        Some(cloned)
    }) {
        return Ok(LockGate { key, _file: cloned });
    }
    let gate = File::open(parent).kio_io(parent)?;
    // SAFETY: `gate` stays owned by the returned File until the lock guard is
    // dropped. LOCK_NB prevents a path operation from waiting while another
    // writer owns the same store protocol.
    if unsafe { libc::flock(gate.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        let error = std::io::Error::last_os_error();
        if matches!(error.raw_os_error(), Some(libc::EWOULDBLOCK)) {
            return Err(KioError::locked(lock_path.display().to_string()));
        }
        return Err(KioError::io(
            error.to_string(),
            lock_path.display().to_string(),
        ));
    }
    let pooled = gate.try_clone().kio_io(parent)?;
    LOCK_GATE_POOL.with(|pool| {
        pool.borrow_mut().insert(key.clone(), (1, pooled));
    });
    Ok(LockGate { key, _file: gate })
}

#[cfg(unix)]
fn bound_lock_corrupt(message: impl Into<String>) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        message,
        json!({}),
        ExitCode::PermanentFailure,
    )
}

#[cfg(unix)]
fn bound_lock_io(error: std::io::Error, path: impl Into<String>) -> KioError {
    let kind = match error.kind() {
        std::io::ErrorKind::AlreadyExists => "already_exists",
        std::io::ErrorKind::NotFound => "not_found",
        _ => "other",
    };
    KioError::new(
        "KIO-E-STORE-IO-001",
        error.to_string(),
        json!({"path": path.into(), "io_error_kind": kind}),
        ExitCode::Failure,
    )
}

/// A descriptor-relative owner of the ordinary `.kio/.lock` protocol.
///
/// This is intentionally separate from [`StoreLock`]'s path/reentrancy
/// convenience wrapper: GC has already retained the `.kio` directory and must
/// never re-resolve that public path while it obtains or releases its writer
/// barrier.  The bytes are nevertheless exactly the same `LockFile` JSON, so
/// ordinary writers and a recovered GC process contend on one lock leaf.
#[cfg(unix)]
pub struct BoundStoreLock {
    kio: File,
    _gate: BoundLockGate,
    locks: File,
    pid: u32,
    token: String,
    owned: BoundLockObservation,
    bytes: Vec<u8>,
}

/// A mutation-free reader barrier over the same retained `.kio` directory
/// gate used by every cooperating writer. Unlike [`BoundStoreLock`], this
/// guard never creates, reclaims, exchanges, or removes `.kio/.lock`.
#[cfg(unix)]
pub(crate) struct BoundStoreReadGuard {
    kio: File,
    _gate: BoundLockGate,
    initial_lock: Option<(Vec<u8>, BoundLockObservation)>,
}

#[cfg(not(unix))]
pub(crate) struct BoundStoreReadGuard {
    _private: (),
}

#[cfg(unix)]
impl BoundStoreReadGuard {
    /// Recheck the public lock leaf while the shared kernel gate remains held.
    /// A byte-identical dead release sentinel is harmless; a live owner or any
    /// replacement is an uncertain writer boundary and therefore retryable.
    pub(crate) fn recheck_idle(&self) -> Result<()> {
        let current = match read_bound_lock(&self.kio, ".lock") {
            Ok((bytes, observation)) => {
                let lock =
                    parse_canonical_lock(&bytes).map_err(|_| KioError::locked(".kio/.lock"))?;
                if lock.pid != RELEASED_LOCK_PID {
                    return Err(KioError::locked(".kio/.lock"));
                }
                Some((bytes, observation))
            }
            Err(error) if bound_is_not_found(&error) => None,
            Err(error) => return Err(error),
        };
        if current != self.initial_lock {
            return Err(KioError::locked(".kio/.lock"));
        }
        Ok(())
    }
}

#[cfg(not(unix))]
impl BoundStoreReadGuard {
    pub(crate) fn recheck_idle(&self) -> Result<()> {
        Err(KioError::new(
            "KIO-E-STORE-CORRUPT-001",
            "platform lacks a verified descriptor-relative read-only writer barrier",
            json!({}),
            ExitCode::PermanentFailure,
        ))
    }
}

/// Acquire a shared, non-blocking reader gate on the retained `.kio`
/// capability. This is the read-only counterpart of the writers' exclusive
/// directory `flock`; it deliberately has no pathname or lock-file mutation.
#[cfg(unix)]
pub(crate) fn acquire_bound_store_read_guard(kio: &File) -> Result<BoundStoreReadGuard> {
    use std::os::fd::AsRawFd;

    let gate = open_bound_directory_for_io(kio, Path::new(".kio"))?;
    // SAFETY: `gate` is owned by the returned guard, names the retained `.kio`
    // directory, and outlives every inventory read protected by this lock.
    if unsafe { libc::flock(gate.as_raw_fd(), libc::LOCK_SH | libc::LOCK_NB) } != 0 {
        let error = std::io::Error::last_os_error();
        if matches!(error.raw_os_error(), Some(libc::EWOULDBLOCK)) {
            return Err(KioError::locked(".kio/.lock"));
        }
        return Err(KioError::io(error.to_string(), ".kio"));
    }
    let gate = BoundLockGate { file: gate };
    let initial_lock = match read_bound_lock(kio, ".lock") {
        Ok((bytes, observation)) => {
            let lock = parse_canonical_lock(&bytes).map_err(|_| KioError::locked(".kio/.lock"))?;
            if lock.pid != RELEASED_LOCK_PID {
                return Err(KioError::locked(".kio/.lock"));
            }
            Some((bytes, observation))
        }
        Err(error) if bound_is_not_found(&error) => None,
        Err(error) => return Err(error),
    };
    Ok(BoundStoreReadGuard {
        kio: kio
            .try_clone()
            .map_err(|error| KioError::io(error.to_string(), ".kio"))?,
        _gate: gate,
        initial_lock,
    })
}

#[cfg(not(unix))]
pub(crate) fn acquire_bound_store_read_guard(_kio: &File) -> Result<BoundStoreReadGuard> {
    Err(KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        "platform lacks a verified descriptor-relative read-only writer barrier",
        json!({}),
        ExitCode::PermanentFailure,
    ))
}

/// Windows and other non-Unix platforms deliberately expose the same type so
/// the GC state machine remains portable, but do not provide a path-based
/// substitute for descriptor-relative no-follow locking.
#[cfg(not(unix))]
pub struct BoundStoreLock {
    _private: (),
}

/// Bridges a descriptor-bound writer lock to [`StoreLock`]'s existing
/// thread-local reentrancy protocol.  Automatic snapshot operations first
/// acquire the public `.lock` leaf relative to a retained `.kio` descriptor;
/// repository helpers may then call `StoreLock::acquire` without reopening or
/// replacing that lock through a public path.
///
/// The caller must supply exactly the public `.kio/.lock` path that ordinary
/// repository operations use as their `LOCK_DEPTH` key.  The path is never
/// opened by this type.
pub struct BoundReentrantStoreLock {
    paths: Vec<PathBuf>,
    inner: Option<BoundStoreLock>,
}

/// Acquire the retained-descriptor lock protocol and register it as the outer
/// owner in the current thread's ordinary lock-depth table.  On platforms
/// without a descriptor-relative primitive, `acquire_bound_store_lock` fails
/// closed rather than falling back to an ambient lock path.
#[cfg(any(target_os = "macos", target_os = "linux"))]
pub(crate) fn acquire_bound_reentrant_store_lock(
    kio: &File,
    ordinary_lock_paths: Vec<PathBuf>,
) -> Result<BoundReentrantStoreLock> {
    let mut paths = ordinary_lock_paths;
    paths.sort();
    paths.dedup();
    if paths.is_empty() {
        return Err(KioError::invalid_usage(
            "bound reentrant store lock requires at least one lock key",
        ));
    }
    let already_held = LOCK_DEPTH.with(|depth| {
        let depth = depth.borrow();
        paths.iter().any(|path| depth.contains_key(path))
    });
    if already_held {
        return Err(KioError::locked(paths[0].display().to_string()));
    }

    let inner = acquire_bound_store_lock(kio)?;
    LOCK_DEPTH.with(|depth| {
        let mut depth = depth.borrow_mut();
        for path in &paths {
            depth.insert(path.clone(), 1);
        }
    });
    Ok(BoundReentrantStoreLock {
        paths,
        inner: Some(inner),
    })
}

impl Drop for BoundReentrantStoreLock {
    fn drop(&mut self) {
        // Remove only this outer registration.  Well-scoped Rust callers drop
        // all nested StoreLock guards first; decrementing defensively avoids
        // corrupting the depth accounting if a caller intentionally leaks one.
        LOCK_DEPTH.with(|depth| {
            let mut depth = depth.borrow_mut();
            for path in &self.paths {
                let Some(count) = depth.get_mut(path) else {
                    continue;
                };
                *count -= 1;
                if *count == 0 {
                    depth.remove(path);
                }
            }
        });
        // Drop after unpublishing the synthetic reentrancy owner.  The bound
        // guard releases only the descriptor-relative entry it originally
        // acquired; it never resolves `self.path`.
        drop(self.inner.take());
    }
}

#[cfg(unix)]
#[derive(Debug, Clone, PartialEq, Eq)]
struct BoundLockObservation {
    dev: u64,
    ino: u64,
    len: u64,
    digest: String,
}

#[cfg(unix)]
const MAX_BOUND_LOCK_BYTES: u64 = 4096;

#[cfg(unix)]
pub(crate) fn acquire_bound_store_lock(kio: &File) -> Result<BoundStoreLock> {
    let gate = acquire_bound_lock_gate(kio)?;
    let pid = std::process::id();
    let token = new_lock_token(pid);
    let bytes = canonical_lock_bytes(pid, &token)?;
    // Every fallible resource needed by `BoundStoreLock::drop` is prepared
    // before the authoritative lock is published.  In particular, a broken
    // `gc/internal/locks` must not turn a failed acquisition into a live lock
    // that no guard owns to release.  Inspect the current entry first so a
    // live ordinary writer sees no GC-internal directory creation.
    preflight_bound_lock_entry(kio)?;
    let retained_kio = kio
        .try_clone()
        .map_err(|e| KioError::io(e.to_string(), ".kio"))?;
    let locks = bound_lock_archive_dir(kio)?;

    match create_bound_lock(kio, ".lock", &bytes) {
        Ok(owned) => Ok(BoundStoreLock {
            kio: retained_kio,
            _gate: gate,
            locks,
            pid,
            token,
            owned,
            bytes,
        }),
        Err(error) if bound_is_exists(&error) => {
            if let Some(owned) = reclaim_stale_bound_lock(kio, &locks, &bytes)? {
                Ok(BoundStoreLock {
                    kio: retained_kio,
                    _gate: gate,
                    locks,
                    pid,
                    token,
                    owned,
                    bytes,
                })
            } else {
                Err(KioError::locked(".kio/.lock"))
            }
        }
        Err(error) => Err(error),
    }
}

#[cfg(not(unix))]
pub(crate) fn acquire_bound_store_lock(_kio: &File) -> Result<BoundStoreLock> {
    Err(KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        "platform lacks a verified descriptor-relative GC lock primitive",
        json!({}),
        ExitCode::PermanentFailure,
    ))
}

#[cfg(unix)]
fn preflight_bound_lock_entry(kio: &File) -> Result<()> {
    match read_bound_lock(kio, ".lock") {
        Ok((bytes, _)) => {
            let lock = parse_canonical_lock(&bytes).map_err(|_| KioError::locked(".kio/.lock"))?;
            if process_is_alive(lock.pid) {
                return Err(KioError::locked(".kio/.lock"));
            }
            // A dead, exact entry is re-read by the reclaim routine below
            // before it is exchanged.  Its presence authorizes preparing the
            // private archive capability; it does not authorize deletion.
            Ok(())
        }
        Err(error) if bound_is_not_found(&error) => Ok(()),
        Err(error) => Err(error),
    }
}

#[cfg(unix)]
fn acquire_bound_lock_gate(kio: &File) -> Result<BoundLockGate> {
    use std::os::fd::AsRawFd;

    // `try_clone` shares an open-file description with the caller on Unix;
    // that would keep flock held by the retained session FD after this guard
    // drops. Re-open `.` capability-relatively to obtain an independent
    // description while staying inside the already-bound `.kio` directory.
    let gate = open_bound_directory_for_io(kio, Path::new(".kio"))?;
    // SAFETY: this retained descriptor names the same `.kio` directory used
    // for every later capability-relative operation and outlives the lock.
    if unsafe { libc::flock(gate.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        let error = std::io::Error::last_os_error();
        if matches!(error.raw_os_error(), Some(libc::EWOULDBLOCK)) {
            return Err(KioError::locked(".kio/.lock"));
        }
        return Err(KioError::io(error.to_string(), ".kio"));
    }
    Ok(BoundLockGate { file: gate })
}

#[cfg(unix)]
impl Drop for BoundStoreLock {
    fn drop(&mut self) {
        let Ok((bytes, observed)) = read_bound_lock(&self.kio, ".lock") else {
            return;
        };
        if bytes != self.bytes
            || observed != self.owned
            || !parse_canonical_lock(&bytes)
                .map(|lock| lock.pid == self.pid && lock.token == self.token)
                .unwrap_or(false)
        {
            return;
        }
        // Never create an absent-lock window and never move an entry that may
        // have replaced ours after the check above. Exchange our lock with a
        // canonical, deliberately dead release sentinel, then verify both
        // sides. The next writer reclaims that sentinel through the ordinary
        // stale-lock protocol. This is conservative (the lock may outlive this
        // guard briefly) but cannot remove a concurrent owner's replacement.
        let archive = bound_lock_name("released");
        let released_pid = RELEASED_LOCK_PID;
        let released_token = new_lock_token(released_pid);
        let Ok(released_bytes) = canonical_lock_bytes(released_pid, &released_token) else {
            return;
        };
        let Ok(released) = create_bound_lock(&self.locks, &archive, &released_bytes) else {
            return;
        };
        if !read_bound_lock(&self.kio, ".lock")
            .is_ok_and(|(actual, state)| actual == self.bytes && state == self.owned)
        {
            return;
        }
        if exchange_bound_lock(&self.kio, ".lock", &self.locks, &archive).is_err() {
            return;
        }
        let old_ok = read_bound_lock(&self.locks, &archive)
            .is_ok_and(|(actual, state)| actual == self.bytes && state == self.owned);
        let released_ok = read_bound_lock(&self.kio, ".lock")
            .is_ok_and(|(actual, state)| actual == released_bytes && state == released);
        if !old_ok || !released_ok {
            // Do not attempt a compensating exchange unless both entries are
            // still exact; in the mismatch branch that is intentionally never
            // true. Leaving a lock entry is fail-closed.
            return;
        }
        if cap_primitives::fs::remove_file(&self.locks, Path::new(&archive)).is_err() {
            return;
        }
        let _ = sync_bound_directory(&self.kio, ".lock");
        let _ = sync_bound_directory(&self.locks, &archive);
    }
}

fn canonical_lock_bytes(pid: u32, token: &str) -> Result<Vec<u8>> {
    let lock = LockFile {
        pid,
        token: token.to_owned(),
        created_at: now_utc_seconds(),
    };
    serde_json::to_vec(&lock).map_err(|error| KioError::io(error.to_string(), ".kio/.lock"))
}

#[cfg(unix)]
fn parse_canonical_lock(bytes: &[u8]) -> Result<LockFile> {
    let lock: LockFile =
        serde_json::from_slice(bytes).map_err(|_| KioError::locked(".kio/.lock"))?;
    if canonical_lock_bytes_for(&lock)? != bytes {
        return Err(KioError::locked(".kio/.lock"));
    }
    Ok(lock)
}

fn canonical_lock_bytes_for(lock: &LockFile) -> Result<Vec<u8>> {
    serde_json::to_vec(lock).map_err(|error| KioError::io(error.to_string(), ".kio/.lock"))
}

#[cfg(unix)]
#[derive(Debug, Clone, PartialEq, Eq)]
struct LockSnapshot {
    lock: LockFile,
    bytes: Vec<u8>,
    dev: u64,
    ino: u64,
    len: u64,
    digest: String,
}

/// Strict ordinary-lock read used solely by stale recovery. The path based
/// API needs this one retained file descriptor check before its atomic
/// exchange; it never unlinks a name after a best-effort string comparison.
#[cfg(unix)]
fn read_lock_snapshot(path: &Path) -> Result<Option<LockSnapshot>> {
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt};

    let before = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
    };
    if !before.file_type().is_file() || before.nlink() != 1 || before.len() > MAX_BOUND_LOCK_BYTES {
        return Err(KioError::locked(path.display().to_string()));
    }
    let mut file = match OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
    {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
    };
    let opened = file.metadata().kio_io(path)?;
    if opened.dev() != before.dev() || opened.ino() != before.ino() || opened.len() != before.len()
    {
        return Err(bound_lock_corrupt("ordinary lock changed while opening"));
    }
    let mut bytes = Vec::with_capacity(opened.len() as usize);
    (&mut file)
        .take(MAX_BOUND_LOCK_BYTES.saturating_add(1))
        .read_to_end(&mut bytes)
        .kio_io(path)?;
    let after = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
    };
    if bytes.len() as u64 != opened.len()
        || after.dev() != opened.dev()
        || after.ino() != opened.ino()
        || after.len() != opened.len()
    {
        return Err(bound_lock_corrupt("ordinary lock changed while reading"));
    }
    let lock = parse_canonical_lock(&bytes)?;
    Ok(Some(LockSnapshot {
        lock,
        digest: lower_hex(&Sha256::digest(&bytes)),
        bytes,
        dev: opened.dev(),
        ino: opened.ino(),
        len: opened.len(),
    }))
}

#[cfg(unix)]
fn open_bound_directory_for_io(directory: &File, label: impl AsRef<Path>) -> Result<File> {
    use cap_primitives::fs::{self as cap_fs, MetadataExt};

    let label = label.as_ref();
    let expected = cap_fs::Metadata::from_file(directory)
        .map_err(|error| KioError::io(error.to_string(), label.display().to_string()))?;
    if !expected.is_dir() {
        return Err(unsafe_store_error(label, "retained directory changed type"));
    }
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let syncable = cap_fs::open(directory, Path::new("."), &options)
        .map_err(|error| KioError::io(error.to_string(), label.display().to_string()))?;
    let observed = cap_fs::Metadata::from_file(&syncable)
        .map_err(|error| KioError::io(error.to_string(), label.display().to_string()))?;
    if !observed.is_dir() || observed.dev() != expected.dev() || observed.ino() != expected.ino() {
        return Err(unsafe_store_error(
            label,
            "retained directory changed while reopening",
        ));
    }
    Ok(syncable)
}

#[cfg(unix)]
fn sync_bound_directory(directory: &File, label: impl AsRef<Path>) -> Result<()> {
    let label = label.as_ref();
    open_bound_directory_for_io(directory, label)?
        .sync_all()
        .map_err(|error| KioError::io(error.to_string(), label.display().to_string()))
}

#[cfg(unix)]
fn bound_lock_archive_dir(kio: &File) -> Result<File> {
    use cap_primitives::fs as cap_fs;
    fn ensure(parent: &File, leaf: &str) -> Result<File> {
        use cap_primitives::fs as cap_fs;
        match cap_fs::open_dir_nofollow(parent, Path::new(leaf)) {
            Ok(dir) => Ok(dir),
            Err(_) => {
                cap_fs::create_dir(parent, Path::new(leaf), &cap_fs::DirOptions::new())
                    .map_err(|e| KioError::io(e.to_string(), leaf))?;
                let dir = cap_fs::open_dir_nofollow(parent, Path::new(leaf))
                    .map_err(|e| KioError::io(e.to_string(), leaf))?;
                sync_bound_directory(parent, leaf)?;
                Ok(dir)
            }
        }
    }
    let gc = ensure(kio, "gc")?;
    let internal = ensure(&gc, "internal")?;
    let locks = ensure(&internal, "locks")?;
    // Re-open validation is descriptor-relative; `ensure` never follows a
    // public path and refuses a non-directory/reparse child.
    let _ = cap_fs::read_base_dir(&locks).map_err(|e| KioError::io(e.to_string(), "locks"))?;
    Ok(locks)
}

#[cfg(unix)]
fn create_bound_lock(kio: &File, leaf: &str, bytes: &[u8]) -> Result<BoundLockObservation> {
    use cap_primitives::fs as cap_fs;
    let mut options = cap_fs::OpenOptions::new();
    options.write(true).create_new(true);
    options._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let mut file =
        cap_fs::open(kio, Path::new(leaf), &options).map_err(|e| bound_lock_io(e, leaf))?;
    file.write_all(bytes)
        .map_err(|e| KioError::io(e.to_string(), leaf))?;
    file.sync_all()
        .map_err(|e| KioError::io(e.to_string(), leaf))?;
    drop(file);
    let (actual, observed) = read_bound_lock(kio, leaf)?;
    if actual != bytes || parse_canonical_lock(&actual).is_err() {
        return Err(bound_lock_corrupt("GC lock changed after creation"));
    }
    sync_bound_directory(kio, leaf)?;
    Ok(observed)
}

#[cfg(unix)]
fn read_bound_lock(kio: &File, leaf: &str) -> Result<(Vec<u8>, BoundLockObservation)> {
    use cap_primitives::fs::{self as cap_fs, MetadataExt};
    let path = Path::new(leaf);
    let before =
        cap_fs::stat(kio, path, cap_fs::FollowSymlinks::No).map_err(|e| bound_lock_io(e, leaf))?;
    validate_bound_lock_meta(&before)?;
    let mut options = cap_fs::OpenOptions::new();
    options.read(true);
    options._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let mut file = cap_fs::open(kio, path, &options).map_err(|e| bound_lock_io(e, leaf))?;
    let opened =
        cap_fs::Metadata::from_file(&file).map_err(|e| KioError::io(e.to_string(), leaf))?;
    validate_bound_lock_meta(&opened)?;
    if before.dev() != opened.dev() || before.ino() != opened.ino() || before.len() != opened.len()
    {
        return Err(bound_lock_corrupt("GC lock changed while opening"));
    }
    let mut bytes = Vec::with_capacity(opened.len() as usize);
    (&mut file)
        .take(MAX_BOUND_LOCK_BYTES.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|e| KioError::io(e.to_string(), leaf))?;
    let after =
        cap_fs::stat(kio, path, cap_fs::FollowSymlinks::No).map_err(|e| bound_lock_io(e, leaf))?;
    validate_bound_lock_meta(&after)?;
    if bytes.len() as u64 != opened.len()
        || after.dev() != opened.dev()
        || after.ino() != opened.ino()
        || after.len() != opened.len()
    {
        return Err(bound_lock_corrupt("GC lock changed while reading"));
    }
    Ok((
        bytes.clone(),
        BoundLockObservation {
            dev: opened.dev(),
            ino: opened.ino(),
            len: opened.len(),
            digest: lower_hex(&Sha256::digest(&bytes)),
        },
    ))
}

#[cfg(unix)]
fn validate_bound_lock_meta(metadata: &cap_primitives::fs::Metadata) -> Result<()> {
    use cap_primitives::fs::MetadataExt;
    if !metadata.is_file() || metadata.len() > MAX_BOUND_LOCK_BYTES || metadata.nlink() != 1 {
        return Err(bound_lock_corrupt("invalid GC lock entry"));
    }
    Ok(())
}

#[cfg(unix)]
fn reclaim_stale_bound_lock(
    kio: &File,
    locks: &File,
    own_bytes: &[u8],
) -> Result<Option<BoundLockObservation>> {
    let (old_bytes, old) = match read_bound_lock(kio, ".lock") {
        Ok(value) => value,
        Err(error) if error.error_code() == "KIO-E-STORE-IO-001" => return Ok(None),
        Err(error) => return Err(error),
    };
    let old_lock = match parse_canonical_lock(&old_bytes) {
        Ok(lock) => lock,
        Err(_) => return Ok(None),
    };
    if process_is_alive(old_lock.pid) {
        return Ok(None);
    }
    // Read it twice before publishing a replacement. A same-content rename is
    // observable through identity and never reclaimed as our stale lock.
    let (again_bytes, again) = read_bound_lock(kio, ".lock")?;
    if again_bytes != old_bytes || again != old || process_is_alive(old_lock.pid) {
        return Ok(None);
    }
    let archive = bound_lock_name("stale");
    let new = create_bound_lock(locks, &archive, own_bytes)?;
    let source_unchanged = read_bound_lock(kio, ".lock")
        .is_ok_and(|(bytes, observed)| bytes == old_bytes && observed == old);
    if !source_unchanged {
        // The unpublished temporary is retained rather than check-then-unlinking
        // a name which a hostile writer could replace in the final gap.
        return Ok(None);
    }
    exchange_bound_lock(kio, ".lock", locks, &archive)?;
    let old_ok = read_bound_lock(locks, &archive)
        .is_ok_and(|(bytes, observed)| bytes == old_bytes && observed == old);
    let new_ok = read_bound_lock(kio, ".lock")
        .is_ok_and(|(bytes, observed)| bytes == own_bytes && observed == new);
    if !old_ok || !new_ok {
        // Never exchange back after a failed postcondition: at least one name
        // no longer designates the expected object, so rollback could move a
        // concurrent owner's entry. The canonical lock remains fail-closed.
        return Err(bound_lock_corrupt(
            "GC stale lock exchange validation failed",
        ));
    }
    cap_primitives::fs::remove_file(locks, Path::new(&archive))
        .map_err(|e| KioError::io(e.to_string(), &archive))?;
    sync_bound_directory(kio, ".lock")?;
    sync_bound_directory(locks, &archive)?;
    Ok(Some(new))
}

#[cfg(unix)]
fn bound_lock_name(prefix: &str) -> String {
    format!("{prefix}-{}-{}", std::process::id(), unix_nanos())
}

#[cfg(unix)]
fn bound_is_exists(error: &KioError) -> bool {
    error.error_code() == "KIO-E-STORE-IO-001"
        && error
            .context()
            .get("io_error_kind")
            .and_then(serde_json::Value::as_str)
            == Some("already_exists")
}

#[cfg(unix)]
fn bound_is_not_found(error: &KioError) -> bool {
    error.error_code() == "KIO-E-STORE-IO-001"
        && error
            .context()
            .get("io_error_kind")
            .and_then(serde_json::Value::as_str)
            == Some("not_found")
}

#[cfg(target_os = "macos")]
fn exchange_bound_lock(left_dir: &File, left: &str, right_dir: &File, right: &str) -> Result<()> {
    use std::ffi::CString;
    use std::os::fd::AsRawFd;
    let left = CString::new(left).map_err(|_| bound_lock_corrupt("invalid GC lock name"))?;
    let right = CString::new(right).map_err(|_| bound_lock_corrupt("invalid GC lock name"))?;
    unsafe extern "C" {
        fn renameatx_np(
            a: libc::c_int,
            b: *const libc::c_char,
            c: libc::c_int,
            d: *const libc::c_char,
            flags: libc::c_uint,
        ) -> libc::c_int;
    }
    if unsafe {
        renameatx_np(
            left_dir.as_raw_fd(),
            left.as_ptr(),
            right_dir.as_raw_fd(),
            right.as_ptr(),
            0x0000_0002,
        )
    } == 0
    {
        Ok(())
    } else {
        Err(KioError::io(
            std::io::Error::last_os_error().to_string(),
            ".lock",
        ))
    }
}

#[cfg(target_os = "linux")]
fn exchange_bound_lock(left_dir: &File, left: &str, right_dir: &File, right: &str) -> Result<()> {
    use std::ffi::CString;
    use std::os::fd::AsRawFd;
    let left = CString::new(left).map_err(|_| bound_lock_corrupt("invalid GC lock name"))?;
    let right = CString::new(right).map_err(|_| bound_lock_corrupt("invalid GC lock name"))?;
    if unsafe {
        libc::syscall(
            libc::SYS_renameat2,
            left_dir.as_raw_fd(),
            left.as_ptr(),
            right_dir.as_raw_fd(),
            right.as_ptr(),
            2_u32,
        )
    } == 0
    {
        Ok(())
    } else {
        Err(KioError::io(
            std::io::Error::last_os_error().to_string(),
            ".lock",
        ))
    }
}

#[cfg(all(unix, not(any(target_os = "macos", target_os = "linux"))))]
fn exchange_bound_lock(
    _left_dir: &File,
    _left: &str,
    _right_dir: &File,
    _right: &str,
) -> Result<()> {
    Err(bound_lock_corrupt("platform lacks atomic GC lock exchange"))
}

#[cfg(debug_assertions)]
fn maybe_hold_lock_for_tests() {
    if let Ok(value) = std::env::var("KIO_TEST_HOLD_LOCK_MS")
        && let Ok(ms) = value.parse::<u64>()
    {
        std::thread::sleep(std::time::Duration::from_millis(ms));
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

pub(crate) fn is_ulid(value: &str) -> bool {
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

/// Debug-only override for the current time via `KIO_FIXED_NOW`. The contract
/// tests (which build in debug) use it to pin `created_at`. It is compiled out
/// of release binaries so a production timestamp cannot be forged through the
/// environment (WS1c S4).
#[cfg(debug_assertions)]
fn fixed_now_override() -> Option<String> {
    std::env::var("KIO_FIXED_NOW").ok()
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

/// Parse an RFC3339 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`, the shape produced
/// by [`now_utc_seconds`], or `YYYY-MM-DDTHH:MM:SS.<digits>Z` with an
/// optional fractional-seconds suffix -- `docs/06-cli-spec.md` §12's other
/// persisted-timestamp shape, e.g. commit `created_at`) into Unix seconds.
/// Returns `None` when the input matches neither shape. Sub-second digits are
/// validated but discarded: this function's return unit is whole seconds
/// (unchanged by R23-16 -- only the accepted input shape widened).
#[must_use]
pub fn parse_utc_seconds(value: &str) -> Option<i64> {
    let bytes = value.as_bytes();
    if bytes.len() < 20
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[bytes.len() - 1] != b'Z'
    {
        return None;
    }
    // R23-16 (06 §11 L513, "正: 2026-04-25T12:00:00.123456Z"): byte 19 is
    // either the terminating `Z` (the original fixed 20-byte shape, already
    // confirmed by the trailing-byte check above) or the start of `.` + >=1
    // ASCII digit + the same trailing `Z`. A parser that rejected the
    // fractional shape outright silently dropped every persisted timestamp
    // that happened to carry sub-second precision (e.g. `--since` filtering
    // commit `created_at`).
    if bytes.len() > 20 {
        let digits = &bytes[20..bytes.len() - 1];
        if bytes[19] != b'.' || digits.is_empty() || !digits.iter().all(u8::is_ascii_digit) {
            return None;
        }
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

// ===========================================================================
// QA21/22/23/24/25/26/27 (step4b-contract-tests-p3a.md §G/§H, 07-adapter-spec.md
// §3 L85-249, 10-operations.md §11.3): the adapter-level network opt-in gate's
// persistent storage — `.kio/scope.json`'s `approvals[]` / `approval_pending` /
// `approvals_initialized`. This is the sole persistent source of truth the
// send gate reads (QA22 — device-global `consents.jsonl` is untouched by this
// module and is no longer consulted for the send decision). Free functions
// (not `Repository` methods) so a multi-scope caller (e.g. the query-embedding
// consent OR-across-scopes check) can evaluate a scope it has not opened as a
// full `Repository` for.
// ===========================================================================

/// `07 §3`'s single execution mode every currently-gate-relevant online
/// adapter (the built-in `mistral_ocr_markdownize` / `gemini_embedding_2`
/// targets, `07 §1`) declares. Kept as a named constant (rather than
/// threading `kio_adapter::types::ExecutionMode` into this crate) because
/// `approvals[]` rows store it as the plain string `AdapterProfile` already
/// serializes it to.
pub const NETWORK_APPROVAL_EXECUTION_MODE: &str = "online_api";

fn read_scope_json_value(kio_dir: &Path) -> Result<Value> {
    let path = kio_dir.join("scope.json");
    let value = serde_json::from_str(&fs::read_to_string(&path).kio_io(&path)?)
        .map_err(|err| KioError::schema(err.to_string()))?;
    validate_scope_json_value(&value)?;
    Ok(value)
}

/// Validate a persisted scope before any public reader exposes its approval
/// state. Exact-version rejection intentionally precedes current-schema
/// validation so every non-current version has the stable store-version error
/// rather than being interpreted through unknown keys.
fn validate_scope_json_value(value: &Value) -> Result<()> {
    let version = match value.get("kio_format_version") {
        Some(Value::String(version)) => version.as_str(),
        Some(_) => return Err(KioError::incompatible_format("<non-string>")),
        None => return Err(KioError::incompatible_format("<missing>")),
    };
    validate_format_version(version)?;
    validate_json_schema(SchemaKind::Scope, value)
}

fn overwrite_scope_json_value(kio_dir: &Path, value: &Value) -> Result<()> {
    let path = kio_dir.join("scope.json");
    atomic_overwrite(
        &path,
        serde_json::to_string_pretty(value)
            .map_err(|err| KioError::schema(err.to_string()))?
            .as_bytes(),
    )
}

/// Current `.kio/scope.json` `approvals[]` rows. Empty when the key is
/// absent — no adapter has ever been approved for this scope (10 §11.3).
pub fn read_network_approvals(kio_dir: &Path) -> Result<Vec<Value>> {
    Ok(read_scope_json_value(kio_dir)?
        .get("approvals")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default())
}

/// The `approvals_initialized` consumed-marker (07 §3 L176-205): true once
/// this scope's initial approval — explicit or the one-time "materialize"
/// exception — has been recorded, independent of whether any row currently
/// remains (a subsequent revoke or a lost/restored backup must not
/// resurrect the initial-materialize exception).
pub fn network_approvals_initialized(kio_dir: &Path) -> Result<bool> {
    Ok(read_scope_json_value(kio_dir)?
        .get("approvals_initialized")
        .and_then(Value::as_bool)
        .unwrap_or(false))
}

/// Whether an `active` `approvals[]` row exists for `tool_id` whose
/// `scope_id`/`execution_mode`/`tool_profile_hash` match the CURRENT values
/// exactly (07 §3's send-gate AND condition: "現在の execution_mode/
/// tool_profile_hash に一致する status=active 行が存在する" — a profile
/// change invalidates the row until re-approval, QA23).
pub fn network_approval_active(
    kio_dir: &Path,
    tool_id: &str,
    execution_mode: &str,
    tool_profile_hash: &str,
) -> Result<bool> {
    let value = read_scope_json_value(kio_dir)?;
    let Some(scope_id) = value.get("scope_id").and_then(Value::as_str) else {
        return Ok(false);
    };
    let Some(approvals) = value.get("approvals").and_then(Value::as_array) else {
        return Ok(false);
    };
    Ok(approvals.iter().any(|row| {
        row.get("scope_id").and_then(Value::as_str) == Some(scope_id)
            && row.get("tool_id").and_then(Value::as_str) == Some(tool_id)
            && row.get("execution_mode").and_then(Value::as_str) == Some(execution_mode)
            && row.get("tool_profile_hash").and_then(Value::as_str) == Some(tool_profile_hash)
            && row.get("status").and_then(Value::as_str) == Some("active")
    }))
}

/// Whether ANY `active` `approvals[]` row currently exists for `tool_id` in
/// this scope, regardless of `execution_mode`/`tool_profile_hash` — the
/// coarser presence check `--online`'s one-shot branch uses to "trust an
/// existing row for one more send" even across a profile change (07 §3),
/// distinct from [`network_approval_active`]'s strict steady-state match.
pub fn network_approval_row_present(kio_dir: &Path, tool_id: &str) -> Result<bool> {
    let value = read_scope_json_value(kio_dir)?;
    let Some(scope_id) = value.get("scope_id").and_then(Value::as_str) else {
        return Ok(false);
    };
    let Some(approvals) = value.get("approvals").and_then(Value::as_array) else {
        return Ok(false);
    };
    Ok(approvals.iter().any(|row| {
        row.get("scope_id").and_then(Value::as_str) == Some(scope_id)
            && row.get("tool_id").and_then(Value::as_str) == Some(tool_id)
            && row.get("status").and_then(Value::as_str) == Some("active")
    }))
}

/// The single in-flight `approval_pending` object, or `None` when absent (07
/// §3 L191-205: the write-order's step (0) pending intent — a
/// single object, never an array, since approval operations are serialized
/// under `.kio/.lock`). Persisted scopes are fully version- and schema-validated
/// before this value is returned.
pub fn read_network_approval_pending(kio_dir: &Path) -> Result<Option<Value>> {
    Ok(read_scope_json_value(kio_dir)?
        .get("approval_pending")
        .cloned())
}

/// 07 §3 step (0) of the approval write-order: durably record the pending
/// approval intent BEFORE `config.toml` is touched, so a crash between
/// steps leaves a recoverable trail and a concurrent `kio adapter revoke`
/// has something to detect/remove (QA26/27).
pub fn write_network_approval_pending(kio_dir: &Path, pending: Value) -> Result<()> {
    let mut value = read_scope_json_value(kio_dir)?;
    let Some(object) = value.as_object_mut() else {
        return Err(KioError::schema("scope.json must be an object"));
    };
    object.insert("approval_pending".to_owned(), pending);
    validate_json_schema(SchemaKind::Scope, &value)?;
    overwrite_scope_json_value(kio_dir, &value)
}

/// 07 §3 step (2) (QA21/23/26/27): publish the `approvals[]` row — upserted
/// by `(scope_id, tool_id)` (existing rows are updated in place, never
/// deleted, matching "行は削除しない — 監査保全"), set the
/// `approvals_initialized` marker, and remove `approval_pending` in the SAME
/// atomic write.
///
/// `expected_pending` is the exact pending payload the caller durably wrote
/// in step (0) via [`write_network_approval_pending`] (or `None` when
/// materializing with no separate pending step — QA21's initial-materialize
/// exception publishes directly). This function re-reads scope.json and
/// requires the CURRENTLY-persisted `approval_pending` to equal
/// `expected_pending` exactly (CAS) before publishing — a mismatch means a
/// concurrent `kio adapter revoke` already removed/changed it, and the
/// publish must not resurrect a stale intent. Returns
/// `KIO-E-ADAPTER-APPROVAL-CONFLICT-001` (exit 5, QA26) on mismatch without
/// writing anything.
pub fn publish_network_approval(
    kio_dir: &Path,
    row: Value,
    expected_pending: Option<&Value>,
) -> Result<()> {
    let mut value = read_scope_json_value(kio_dir)?;
    let Some(object) = value.as_object_mut() else {
        return Err(KioError::schema("scope.json must be an object"));
    };
    let current_pending = object.get("approval_pending").cloned();
    if current_pending.as_ref() != expected_pending {
        return Err(KioError::new(
            "KIO-E-ADAPTER-APPROVAL-CONFLICT-001",
            "approval_pending changed or was removed by a concurrent kio adapter revoke; re-approval is required",
            json!({}),
            ExitCode::AuthError,
        ));
    }
    let row_scope_id = row
        .get("scope_id")
        .and_then(Value::as_str)
        .map(str::to_owned);
    let row_tool_id = row
        .get("tool_id")
        .and_then(Value::as_str)
        .map(str::to_owned);
    let mut approvals = object
        .get("approvals")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut replaced = false;
    for existing in &mut approvals {
        let existing_scope_id = existing
            .get("scope_id")
            .and_then(Value::as_str)
            .map(str::to_owned);
        let existing_tool_id = existing
            .get("tool_id")
            .and_then(Value::as_str)
            .map(str::to_owned);
        if existing_scope_id == row_scope_id && existing_tool_id == row_tool_id {
            *existing = row.clone();
            replaced = true;
            break;
        }
    }
    if !replaced {
        approvals.push(row);
    }
    object.insert("approvals".to_owned(), Value::Array(approvals));
    object.insert("approvals_initialized".to_owned(), Value::Bool(true));
    object.remove("approval_pending");
    validate_json_schema(SchemaKind::Scope, &value)?;
    overwrite_scope_json_value(kio_dir, &value)
}

/// QA25/26/27: the outcome of a `kio adapter revoke` scope.json mutation.
#[derive(Debug, Clone, Default, Serialize)]
pub struct NetworkRevokeOutcome {
    /// `tool_id`s whose `approvals[]` row was flipped `status=revoked` by
    /// this call (already-revoked rows are left alone and not repeated
    /// here).
    pub revoked_tool_ids: Vec<String>,
    /// Whether a matching `approval_pending` was removed by this call.
    pub pending_removed: bool,
    /// Whether this call wrote the `approvals_initialized` marker (only
    /// happens when it was previously absent AND this call actually
    /// changed something — 07 §3: a no-op revoke never writes it).
    pub marker_written: bool,
}

impl NetworkRevokeOutcome {
    /// Whether this call changed anything at all — the idempotent
    /// "no target" case (07 §3: "対象なし...は冪等成功") is `false`.
    #[must_use]
    pub fn changed(&self) -> bool {
        !self.revoked_tool_ids.is_empty() || self.pending_removed
    }
}

/// QA25/26/27 (step4b-contract-tests-p3a.md §H, 07 §3 L118-211): `kio adapter
/// revoke (<tool_id> | --all)`'s scope.json mutation. `tool_id = None` means
/// `--all`.
///
/// - Revoke updates the matching `active` `approvals[]` row(s) to
///   `status="revoked"` + `revoked_at` (rows are never deleted).
/// - Pending removal is `(scope_id, tool_id)`-only — `execution_mode`/
///   `tool_profile_hash` are UNQUESTIONED (07 §3 L123-130, QA27): a 4-tuple
///   -exact match would miss a pending left behind by a since-changed
///   profile, letting a later self-heal resurrect the very approval this
///   revoke meant to stop. `--all` (`tool_id = None`) removes any pending
///   regardless of which tool it names.
/// - Idempotent: when nothing actually changes (no matching active row, no
///   matching pending), returns a `changed() == false` outcome and does
///   **not** write the `approvals_initialized` marker (07 §3: "対象なしの
///   冪等成功では書かない" — an unused scope's initial-materialize
///   exception must not be consumed by a no-op revoke).
/// - When something DID change, the marker is set in the SAME atomic write
///   if it was not already (07 §3's initial-materialize-exception
///   consumption, shared with the approval-publish path).
pub fn revoke_network_approval(
    kio_dir: &Path,
    tool_id: Option<&str>,
    revoked_at: &str,
) -> Result<NetworkRevokeOutcome> {
    let mut value = read_scope_json_value(kio_dir)?;
    let Some(scope_id) = value
        .get("scope_id")
        .and_then(Value::as_str)
        .map(str::to_owned)
    else {
        return Err(KioError::schema("scope.json missing scope_id"));
    };
    let Some(object) = value.as_object_mut() else {
        return Err(KioError::schema("scope.json must be an object"));
    };
    let mut outcome = NetworkRevokeOutcome::default();
    if let Some(Value::Array(approvals)) = object.get_mut("approvals") {
        for row in approvals.iter_mut() {
            let row_scope_id = row.get("scope_id").and_then(Value::as_str);
            let row_tool_id = row
                .get("tool_id")
                .and_then(Value::as_str)
                .map(str::to_owned);
            let is_active = row.get("status").and_then(Value::as_str) == Some("active");
            let matches_target = match tool_id {
                Some(target) => row_tool_id.as_deref() == Some(target),
                None => true,
            };
            if row_scope_id == Some(scope_id.as_str()) && is_active && matches_target {
                if let Some(row_object) = row.as_object_mut() {
                    row_object.insert("status".to_owned(), json!("revoked"));
                    row_object.insert("revoked_at".to_owned(), json!(revoked_at));
                }
                if let Some(row_tool_id) = row_tool_id {
                    outcome.revoked_tool_ids.push(row_tool_id);
                }
            }
        }
    }
    if let Some(pending) = object.get("approval_pending").cloned() {
        let pending_scope_id = pending.get("scope_id").and_then(Value::as_str);
        let pending_tool_id = pending.get("tool_id").and_then(Value::as_str);
        let matches_target = match tool_id {
            Some(target) => pending_tool_id == Some(target),
            None => true,
        };
        if pending_scope_id == Some(scope_id.as_str()) && matches_target {
            object.remove("approval_pending");
            outcome.pending_removed = true;
        }
    }
    if !outcome.changed() {
        return Ok(outcome);
    }
    let already_initialized = object
        .get("approvals_initialized")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if !already_initialized {
        object.insert("approvals_initialized".to_owned(), json!(true));
        outcome.marker_written = true;
    }
    validate_json_schema(SchemaKind::Scope, &value)?;
    overwrite_scope_json_value(kio_dir, &value)?;
    Ok(outcome)
}

#[cfg(test)]
mod tests {
    use super::enforce_config_semantics;
    use super::{
        ArchiveLimits, DEFAULT_MAX_ARCHIVE_FILE_BYTES, MAX_COMMIT_PARENTS, MAX_TREE_ENTRIES,
        PendingNormalizeRef, RELEASED_LOCK_PID, Repository, StoreLock, append_jsonl_rotating,
        civil_from_days, format_unix_seconds, format_utc_seconds, open_scope_file_nofollow,
        parse_utc_seconds, process_is_alive, prune_rotated_logs, read_adapter_lane,
        read_logs_retention_days, read_network_approval_pending, read_network_approvals,
        redact_context, redact_message_paths, rotate_stale_log, write_network_approval_pending,
    };
    #[cfg(windows)]
    use super::{
        canonical_lock_bytes, create_windows_lock, open_windows_lock_parent, read_windows_lock,
        release_windows_owned_lock, windows_lock_leaf,
    };
    #[cfg(windows)]
    use std::path::PathBuf;

    #[cfg(unix)]
    #[test]
    fn bound_lock_directory_sync_reopens_linux_o_path_capability() {
        use cap_primitives::{ambient_authority, fs as cap_fs};

        let scope = tempfile::tempdir().unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        let retained = cap_fs::open_ambient_dir(repo.kio_dir(), ambient_authority()).unwrap();
        super::sync_bound_directory(&retained, repo.kio_dir()).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn bound_gc_lock_contends_with_ordinary_lock_and_recovers_canonical_stale_lock() {
        use cap_primitives::{ambient_authority, fs as cap_fs};

        let scope = tempfile::tempdir().unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        let retained = cap_fs::open_ambient_dir(repo.kio_dir(), ambient_authority()).unwrap();

        let held = super::acquire_bound_store_lock(&retained).unwrap();
        match StoreLock::acquire(repo.kio_dir()) {
            Err(error) => assert_eq!(error.error_code(), "KIO-E-STORE-LOCKED-001"),
            Ok(_) => panic!("ordinary writer acquired a bound GC lock"),
        }
        drop(held);
        match StoreLock::acquire(repo.kio_dir()) {
            Ok(_) => {}
            Err(error) => panic!("ordinary recovery after GC release failed: {error:?}"),
        }

        let stale = super::LockFile {
            pid: 999_999_999,
            token: "dead-owner".into(),
            created_at: "2026-01-01T00:00:00Z".into(),
        };
        assert!(!super::process_is_alive(stale.pid));
        let stale_bytes = serde_json::to_vec(&stale).unwrap();
        std::fs::write(repo.kio_dir().join(".lock"), &stale_bytes).unwrap();
        let recovered = super::acquire_bound_store_lock(&retained).unwrap();
        let active: serde_json::Value =
            serde_json::from_slice(&std::fs::read(repo.kio_dir().join(".lock")).unwrap()).unwrap();
        assert!(active.get("pid").is_some());
        assert!(active.get("token").is_some());
        assert!(active.get("created_at").is_some());
        let lock_archive = repo.kio_dir().join("gc/internal/locks");
        assert_eq!(std::fs::read_dir(lock_archive).unwrap().count(), 0);
        drop(recovered);
        // A normal writer can parse the GC lock after the GC process crashed
        // and reclaimed it; no private GC-only lock encoding exists.
        assert!(StoreLock::acquire(repo.kio_dir()).is_ok());
    }

    #[cfg(any(target_os = "macos", target_os = "linux"))]
    #[test]
    fn bound_reentrant_lock_allows_nested_repository_store_lock() {
        use cap_primitives::{ambient_authority, fs as cap_fs};

        let scope = tempfile::tempdir().unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        let retained = cap_fs::open_ambient_dir(repo.kio_dir(), ambient_authority()).unwrap();
        let path = repo.kio_dir().join(".lock");

        let outer = super::acquire_bound_reentrant_store_lock(&retained, vec![path]).unwrap();
        // Model the descriptor inherited across a concurrent fork before its
        // exec closes CLOEXEC handles. The logical guard must explicitly
        // unlock the shared open-file description even while this duplicate
        // remains open.
        let inherited_gate = outer
            .inner
            .as_ref()
            .unwrap()
            ._gate
            .file
            .try_clone()
            .unwrap();
        let nested = repo.lock_store().unwrap();
        drop(nested);
        drop(outer);

        // The descriptor-bound owner released its own entry, and no synthetic
        // depth remains to make a later ordinary writer spuriously reentrant.
        assert!(StoreLock::acquire(repo.kio_dir()).is_ok());
        drop(inherited_gate);
    }

    #[cfg(unix)]
    #[test]
    fn bound_gc_lock_never_creates_a_lock_in_a_public_path_replacement() {
        use cap_primitives::{ambient_authority, fs as cap_fs};

        let original_scope = tempfile::tempdir().unwrap();
        let original = Repository::init(original_scope.path()).unwrap();
        let retained = cap_fs::open_ambient_dir(original.kio_dir(), ambient_authority()).unwrap();
        let victim_scope = tempfile::tempdir().unwrap();
        let victim = Repository::init(victim_scope.path()).unwrap();
        let saved = original_scope.path().join(".kio-retained");
        std::fs::rename(original.kio_dir(), &saved).unwrap();
        std::fs::rename(victim.kio_dir(), original_scope.path().join(".kio")).unwrap();

        let held = super::acquire_bound_store_lock(&retained).unwrap();
        assert!(!original_scope.path().join(".kio/.lock").exists());
        assert!(saved.join(".lock").exists());
        drop(held);
    }

    #[cfg(unix)]
    #[test]
    fn bound_gc_live_lock_rejection_does_not_create_gc_internal_state() {
        use cap_primitives::{ambient_authority, fs as cap_fs};

        let scope = tempfile::tempdir().unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        let retained = cap_fs::open_ambient_dir(repo.kio_dir(), ambient_authority()).unwrap();
        let live = StoreLock::acquire(repo.kio_dir()).unwrap();
        let before_lock = std::fs::read(repo.kio_dir().join(".lock")).unwrap();
        assert!(!repo.kio_dir().join("gc").exists());

        match super::acquire_bound_store_lock(&retained) {
            Err(error) => assert_eq!(error.error_code(), "KIO-E-STORE-LOCKED-001"),
            Ok(_) => panic!("bound GC acquired a live ordinary lock"),
        }
        assert_eq!(
            std::fs::read(repo.kio_dir().join(".lock")).unwrap(),
            before_lock
        );
        assert!(!repo.kio_dir().join("gc").exists());
        drop(live);
    }

    #[cfg(unix)]
    #[test]
    fn bound_gc_lock_setup_failure_does_not_publish_an_unowned_live_lock() {
        use cap_primitives::{ambient_authority, fs as cap_fs};

        let scope = tempfile::tempdir().unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        let retained = cap_fs::open_ambient_dir(repo.kio_dir(), ambient_authority()).unwrap();
        std::fs::write(repo.kio_dir().join("gc"), b"not a directory").unwrap();

        assert!(super::acquire_bound_store_lock(&retained).is_err());
        assert!(
            !repo.kio_dir().join(".lock").exists(),
            "failed archive setup must not strand a live lock"
        );

        std::fs::remove_file(repo.kio_dir().join("gc")).unwrap();
        assert!(super::acquire_bound_store_lock(&retained).is_ok());
    }

    #[test]
    fn tag_refuses_mismatched_or_coexisting_shallow_receipts() {
        use std::collections::{BTreeMap, BTreeSet};

        let scope = tempfile::tempdir().unwrap();
        std::fs::write(scope.path().join("note.txt"), b"fixture").unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        let commit = repo
            .snapshot(Some("fixture"), Some("2026-01-01T00:00:00Z"))
            .unwrap()
            .commit_hash
            .expect("snapshot must create a commit");
        let tree = repo.read_commit(&commit).unwrap().tree;
        let shallow = repo.kio_dir().join("gc/shallowed");
        std::fs::create_dir_all(&shallow).unwrap();
        let leaf = &commit["sha256:".len()..];

        let wrong_tree = format!("sha256:{}", "f".repeat(64));
        std::fs::write(
            shallow.join(leaf),
            crate::gc::ShallowReceipt::new(
                commit.clone(),
                wrong_tree,
                "2026-01-01T00:00:01Z".into(),
            )
            .unwrap()
            .canonical_bytes()
            .unwrap(),
        )
        .unwrap();
        let mismatch = repo.tag("mismatched", Some(&commit)).unwrap_err();
        assert_eq!(mismatch.error_code(), "KIO-E-STORE-CORRUPT-001");

        std::fs::write(
            shallow.join(leaf),
            crate::gc::ShallowReceipt::new(
                commit.clone(),
                tree.clone(),
                "2026-01-01T00:00:01Z".into(),
            )
            .unwrap()
            .canonical_bytes()
            .unwrap(),
        )
        .unwrap();
        let coexistence = repo.tag("coexisting", Some(&commit)).unwrap_err();
        assert_eq!(coexistence.error_code(), "KIO-E-STORE-CORRUPT-001");
        std::fs::remove_file(shallow.join(leaf)).unwrap();

        let store = crate::cas::ObjectStore::new(repo.kio_dir());
        // A real final shallow boundary is an Auto commit that is no longer a
        // ref tip.  It remains in history through the current Manual child,
        // but a tag must not revive it as a live tip.
        std::fs::write(scope.path().join("note.txt"), b"auto fixture").unwrap();
        let auto = repo
            .auto_snapshot_with_normalize(
                Some("auto fixture"),
                Some("2026-01-01T00:00:02Z"),
                &BTreeSet::new(),
                &BTreeMap::new(),
            )
            .unwrap()
            .commit_hash
            .expect("auto snapshot must create a commit");
        let auto_tree = repo.read_commit(&auto).unwrap().tree;
        std::fs::write(scope.path().join("note.txt"), b"manual child").unwrap();
        repo.snapshot(Some("manual child"), Some("2026-01-01T00:00:03Z"))
            .unwrap();
        let auto_leaf = &auto["sha256:".len()..];
        std::fs::write(
            shallow.join(auto_leaf),
            crate::gc::ShallowReceipt::new(
                auto.clone(),
                auto_tree.clone(),
                "2026-01-01T00:00:04Z".into(),
            )
            .unwrap()
            .canonical_bytes()
            .unwrap(),
        )
        .unwrap();
        std::fs::remove_file(
            store
                .object_path(crate::cas::ObjectKind::Tree, &auto_tree)
                .unwrap(),
        )
        .unwrap();
        let canonical_final = repo.tag("canonical-final", Some(&auto)).unwrap_err();
        assert_eq!(canonical_final.error_code(), "KIO-E-COMMIT-SHALLOW-001");
    }

    #[test]
    fn snapshot_rejects_invalid_shallow_base_before_archiving_working_bytes() {
        let scope = tempfile::tempdir().unwrap();
        std::fs::write(scope.path().join("note.txt"), b"base bytes").unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        let base = repo
            .snapshot(Some("base"), Some("2026-01-01T00:00:00Z"))
            .unwrap()
            .commit_hash
            .expect("snapshot must create a commit");
        let base_tree = repo.read_commit(&base).unwrap().tree;
        let store = crate::cas::ObjectStore::new(repo.kio_dir());
        std::fs::remove_file(
            store
                .object_path(crate::cas::ObjectKind::Tree, &base_tree)
                .unwrap(),
        )
        .unwrap();

        let new_bytes = b"must not be archived";
        std::fs::write(scope.path().join("new.txt"), new_bytes).unwrap();
        let new_raw = crate::cas::hash_bytes(new_bytes);
        let error = repo
            .snapshot(Some("must fail"), Some("2026-01-01T00:00:01Z"))
            .unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
        assert!(
            !store
                .object_path(crate::cas::ObjectKind::Raw, &new_raw)
                .unwrap()
                .exists(),
            "a rejected base must not archive a newly discovered working file"
        );
        assert_eq!(repo.head_commit_hash().unwrap(), Some(base));
    }

    #[cfg(unix)]
    #[test]
    fn bound_parent_policy_write_stays_on_the_retained_kio_handle() {
        use cap_primitives::{ambient_authority, fs as cap_fs};
        use std::os::unix::fs::symlink;

        let scope = tempfile::tempdir().unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        let retained = cap_fs::open_ambient_dir(repo.kio_dir(), ambient_authority()).unwrap();
        let victim = tempfile::tempdir().unwrap();
        std::fs::write(victim.path().join("config.toml"), "sentinel = true\n").unwrap();

        // Model a same-UID public-name replacement after the parent retained
        // its no-follow child store descriptor. The helper must update the
        // original inode, never the replacement target.
        let original = scope.path().join(".kio-original");
        std::fs::rename(repo.kio_dir(), &original).unwrap();
        symlink(victim.path(), scope.path().join(".kio")).unwrap();
        let policy = toml::Value::try_from(serde_json::json!({
            "rules": [{
                "pattern": "child/private.md",
                "negated": false,
                "scope_prefix": "child"
            }]
        }))
        .unwrap();

        super::persist_bound_generated_parent_policy(&retained, policy).unwrap();

        assert_eq!(
            std::fs::read_to_string(victim.path().join("config.toml")).unwrap(),
            "sentinel = true\n",
            "a public .kio replacement must not receive the generated policy"
        );
        let original_config = std::fs::read_to_string(original.join("config.toml")).unwrap();
        assert!(original_config.contains("generated_parent_policy"));
    }

    #[cfg(unix)]
    #[test]
    fn bound_parent_policy_write_preserves_schema_error_identity() {
        use cap_primitives::{ambient_authority, fs as cap_fs};

        let scope = tempfile::tempdir().unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        std::fs::write(repo.kio_dir().join("config.toml"), "unknown = true\n").unwrap();
        let retained = cap_fs::open_ambient_dir(repo.kio_dir(), ambient_authority()).unwrap();
        let policy = toml::Value::try_from(serde_json::json!({ "rules": [] })).unwrap();

        let error = super::persist_bound_generated_parent_policy(&retained, policy).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-CONFIG-SCHEMA-001");
    }

    #[test]
    fn config_rejects_retired_format_version_key() {
        let scope = tempfile::tempdir().unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        std::fs::write(
            repo.kio_dir().join("config.toml"),
            "kio_format_version = \"0.1.0\"\n",
        )
        .unwrap();

        let error = Repository::open(scope.path()).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-CONFIG-SCHEMA-001");
    }

    #[test]
    fn working_tree_pins_the_validated_chunking_config() {
        let scope = tempfile::tempdir().unwrap();
        let repo = Repository::init(scope.path()).unwrap();
        fs::write(scope.path().join("note.md"), b"body").unwrap();

        let default_tree = repo.build_working_tree(false).unwrap().tree;
        assert_eq!(
            default_tree.chunking_config_hash,
            super::chunking_config_hash("heading", 6_000).unwrap()
        );

        fs::write(
            repo.kio_dir().join("config.toml"),
            "[chunking]\nstrategy = \"heading\"\nmax_chars = 40\n",
        )
        .unwrap();
        let configured_tree = repo.build_working_tree(false).unwrap().tree;
        assert_eq!(
            configured_tree.chunking_config_hash,
            super::chunking_config_hash("heading", 40).unwrap()
        );
        assert_ne!(
            configured_tree.chunking_config_hash,
            default_tree.chunking_config_hash
        );

        fs::write(
            repo.kio_dir().join("config.toml"),
            "[chunking]\nmax_chars = 0\n",
        )
        .unwrap();
        assert_eq!(
            repo.build_working_tree(false).unwrap_err().error_code(),
            "KIO-E-CONFIG-SCHEMA-001"
        );
        fs::write(
            repo.kio_dir().join("config.toml"),
            "[chunking]\nmax_chars = \"40\"\n",
        )
        .unwrap();
        assert_eq!(
            repo.build_working_tree(false).unwrap_err().error_code(),
            "KIO-E-CONFIG-SCHEMA-001"
        );
    }

    #[test]
    fn current_ref_targets_reads_head_branch_and_canonical_tags_without_names_ledger() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let head = format!("sha256:{}", "a".repeat(64));
        let branch = format!("sha256:{}", "b".repeat(64));
        let tag = format!("sha256:{}", "c".repeat(64));
        fs::write(repo.kio_dir().join("HEAD"), &head).unwrap();
        fs::write(repo.kio_dir().join("refs/heads/main"), &branch).unwrap();
        let tags = repo.kio_dir().join("refs/tags-v1");
        fs::create_dir_all(&tags).unwrap();
        fs::write(tags.join(format!("tag-{}", "d".repeat(64))), &tag).unwrap();
        fs::write(tags.join("names.jsonl"), b"not a ref\n").unwrap();

        let expected = BTreeSet::from([head, branch, tag]);
        assert_eq!(repo.current_ref_targets().unwrap(), expected);
    }

    #[test]
    fn current_ref_targets_rejects_invalid_tag_leaf_instead_of_omitting_it() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let tags = repo.kio_dir().join("refs/tags-v1");
        fs::create_dir_all(&tags).unwrap();
        fs::write(tags.join("old-tag"), format!("sha256:{}", "a".repeat(64))).unwrap();

        assert!(repo.current_ref_targets().is_err());
    }

    /// D7 (07 §7): the `offline_api` sub-table is wired, so a non-default
    /// timeout there is accepted rather than rejected.
    #[test]
    fn d7_offline_api_timeout_override_is_accepted() {
        let config = serde_json::json!({
            "adapter": { "policy": { "offline_api": { "timeout_seconds": 1800 } } }
        });
        assert!(enforce_config_semantics(&config).is_ok());
    }

    /// The parent value is untouched by D7 — still only the documented default.
    /// Widening it would change every online adapter's behaviour, including the
    /// billed ones, which D7 does not ask for.
    #[test]
    fn d7_leaves_the_parent_timeout_rejection_alone() {
        let config = serde_json::json!({
            "adapter": { "policy": { "timeout_seconds": 600 } }
        });
        assert!(enforce_config_semantics(&config).is_err());
        let documented_default = serde_json::json!({
            "adapter": { "policy": { "timeout_seconds": 300 } }
        });
        assert!(enforce_config_semantics(&documented_default).is_ok());
    }

    /// The other two modes are refused, not ignored. Nothing honours them yet,
    /// and accepting a timeout that never takes effect is worse than refusing
    /// it: the operator would believe a limit is in force that is not.
    #[test]
    fn d7_refuses_the_execution_modes_that_are_not_wired() {
        for mode in ["online_api", "deterministic_library"] {
            let config = serde_json::json!({
                "adapter": { "policy": { mode: { "timeout_seconds": 600 } } }
            });
            let error = enforce_config_semantics(&config).expect_err(mode);
            assert_eq!(
                error.error_code(),
                "KIO-E-CONFIG-NOT-IMPLEMENTED-001",
                "{mode}"
            );
        }
    }
    use crate::cas::{ContentObjectKind, ObjectKind, ObjectStore, hash_bytes};
    use crate::dag::{CommitType, NormalizeRef};
    use crate::purge::PurgeState;
    use serde_json::json;
    use std::collections::{BTreeMap, BTreeSet};
    use std::fs;

    #[test]
    fn read_network_approval_pending_returns_none_when_absent() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        assert_eq!(read_network_approval_pending(repo.kio_dir()).unwrap(), None);
    }

    #[test]
    fn read_network_approval_pending_returns_the_stored_object_verbatim() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let scope_id = repo.scope_identity().unwrap().scope_id;
        let pending = json!({
            "scope_id": scope_id,
            "tool_id": "mistral_ocr_markdownize",
            "execution_mode": "online_api",
            "tool_profile_hash": format!("sha256:{}", "a".repeat(64)),
            "approved_at": "2026-07-22T00:00:00Z",
            "approval_method": "approve",
        });
        write_network_approval_pending(repo.kio_dir(), pending.clone()).unwrap();
        assert_eq!(
            read_network_approval_pending(repo.kio_dir()).unwrap(),
            Some(pending)
        );
    }

    #[test]
    fn scope_validation_rejects_missing_or_non_string_version_as_incompatible() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let scope_path = repo.kio_dir().join("scope.json");

        for invalid_version in [None, Some(json!(1))] {
            let mut scope: serde_json::Value =
                serde_json::from_str(&fs::read_to_string(&scope_path).unwrap()).unwrap();
            match invalid_version {
                Some(version) => scope["kio_format_version"] = version,
                None => {
                    scope.as_object_mut().unwrap().remove("kio_format_version");
                }
            }
            fs::write(&scope_path, serde_json::to_vec_pretty(&scope).unwrap()).unwrap();
            let error = repo.scope_identity().unwrap_err();
            assert_eq!(error.error_code(), "KIO-E-STORE-VERSION-001");
        }
    }

    #[test]
    fn incompatible_scope_versions_precede_current_schema_validation() {
        for version in ["0.0.0", "0.1.1", "0.2.0", "1.0.0", "malformed"] {
            let dir = tempfile::tempdir().unwrap();
            let repo = Repository::init(dir.path()).unwrap();
            let scope_path = repo.kio_dir().join("scope.json");
            let mut scope: serde_json::Value =
                serde_json::from_str(&fs::read_to_string(&scope_path).unwrap()).unwrap();
            scope["kio_format_version"] = json!(version);
            scope["future_only_key"] = json!(true);
            fs::write(&scope_path, serde_json::to_vec_pretty(&scope).unwrap()).unwrap();

            let error = repo.scope_identity().unwrap_err();
            assert_eq!(error.error_code(), "KIO-E-STORE-VERSION-001");
            assert_eq!(error.context()["found"], version);
        }
    }

    #[test]
    fn approval_readers_reject_malformed_current_scope_shapes() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let scope_path = repo.kio_dir().join("scope.json");
        let scope_id = repo.scope_identity().unwrap().scope_id;
        let row = |status: &str| {
            json!({
                "scope_id": scope_id,
                "tool_id": "mistral_ocr_markdownize",
                "execution_mode": "online_api",
                "tool_profile_hash": format!("sha256:{}", "a".repeat(64)),
                "approved_at": "2026-07-22T00:00:00Z",
                "approval_method": "approve",
                "status": status,
            })
        };

        let cases = [
            json!({ "approvals": [{
                "scope_id": scope_id,
                "tool_id": "mistral_ocr_markdownize",
                "execution_mode": "online_api",
                "tool_profile_hash": format!("sha256:{}", "a".repeat(64)),
                "approved_at": "2026-07-22T00:00:00Z",
                "approval_method": "approve"
            }]}),
            json!({ "approvals": [row("revoked")] }),
            json!({ "approval_pending": {
                "scope_id": scope_id,
                "tool_id": "mistral_ocr_markdownize",
                "execution_mode": "online_api",
                "tool_profile_hash": format!("sha256:{}", "a".repeat(64))
            }}),
        ];

        for patch in cases {
            let mut scope: serde_json::Value =
                serde_json::from_str(&fs::read_to_string(&scope_path).unwrap()).unwrap();
            for (key, value) in patch.as_object().unwrap() {
                scope[key] = value.clone();
            }
            fs::write(&scope_path, serde_json::to_vec_pretty(&scope).unwrap()).unwrap();
            assert!(read_network_approvals(repo.kio_dir()).is_err());

            let mut current: serde_json::Value =
                serde_json::from_str(&fs::read_to_string(&scope_path).unwrap()).unwrap();
            current.as_object_mut().unwrap().remove("approvals");
            current.as_object_mut().unwrap().remove("approval_pending");
            fs::write(&scope_path, serde_json::to_vec_pretty(&current).unwrap()).unwrap();
        }
    }

    #[test]
    fn process_liveness_recognizes_current_process_and_released_sentinel() {
        assert!(process_is_alive(std::process::id()));
        assert!(!process_is_alive(RELEASED_LOCK_PID));
    }

    #[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
    #[test]
    fn token_checked_lock_handling_requires_canonical_bytes_and_exact_owner() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("ordinary.lock");
        let pid = 4242;
        let token = "token-checked-owner";
        let bytes = canonical_lock_bytes(pid, token).unwrap();
        fs::write(&path, &bytes).unwrap();

        let parsed = read_lock_file_token_checked(&path).unwrap().unwrap();
        assert_eq!(parsed.pid, pid);
        assert_eq!(parsed.token, token);

        release_ordinary_lock_token_checked(&path, pid, "different-token").unwrap();
        assert_eq!(
            fs::read(&path).unwrap(),
            bytes,
            "wrong owner must not remove"
        );

        release_ordinary_lock_token_checked(&path, pid, token).unwrap();
        assert!(!path.exists(), "exact owner removes its own lock");

        fs::write(&path, b"{\"pid\":4242}").unwrap();
        assert!(read_lock_file_token_checked(&path).is_err());
    }

    #[cfg(windows)]
    #[test]
    fn windows_lock_leaf_rejects_parent_traversal_and_preserves_foreign_token() {
        let traversal = PathBuf::from("safe").join("..").join("ordinary.lock");
        assert!(open_windows_lock_parent(&traversal).is_err());

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("ordinary.lock");
        let parent = open_windows_lock_parent(&path).unwrap();
        let token = "foreign-token";
        let bytes = canonical_lock_bytes(4242, token).unwrap();
        let owner =
            create_windows_lock(&parent, windows_lock_leaf(&path).unwrap(), &bytes).unwrap();
        release_windows_owned_lock(&owner, 4242, "different-token").unwrap();
        assert_eq!(read_windows_lock(&owner).unwrap().0.token, token);
        release_windows_owned_lock(&owner, 4242, token).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn windows_lock_rejects_hardlinked_stale_leaf_without_touching_either_name() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("ordinary.lock");
        let alias = dir.path().join("ordinary.alias");
        let bytes = canonical_lock_bytes(RELEASED_LOCK_PID, "retired-owner").unwrap();
        fs::write(&path, &bytes).unwrap();
        fs::hard_link(&path, &alias).unwrap();

        assert!(StoreLock::acquire_path(path.clone()).is_err());
        assert_eq!(fs::read(&path).unwrap(), bytes);
        assert_eq!(fs::read(&alias).unwrap(), bytes);
    }

    #[cfg(windows)]
    #[test]
    fn windows_concurrent_stale_reclaim_has_exactly_one_owner() {
        use std::sync::{Arc, Barrier, Condvar, Mutex};

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("contended.lock");
        fs::write(
            &path,
            canonical_lock_bytes(RELEASED_LOCK_PID, "retired-owner").unwrap(),
        )
        .unwrap();
        let start = Arc::new(Barrier::new(3));
        // The successful owner remains live until the other worker has made
        // its attempt, so the assertion measures overlap rather than timing.
        let state = Arc::new((Mutex::new((0_usize, false)), Condvar::new()));
        let mut workers = Vec::new();
        for _ in 0..2 {
            let start = Arc::clone(&start);
            let state = Arc::clone(&state);
            let path = path.clone();
            workers.push(std::thread::spawn(move || {
                start.wait();
                match StoreLock::acquire_path(path) {
                    Ok(lock) => {
                        let (mutex, wake) = &*state;
                        let mut state = mutex.lock().unwrap();
                        state.0 += 1;
                        wake.notify_all();
                        while !state.1 {
                            state = wake.wait(state).unwrap();
                        }
                        drop(lock);
                        Ok(true)
                    }
                    Err(error) => {
                        let (mutex, wake) = &*state;
                        let mut state = mutex.lock().unwrap();
                        state.0 += 1;
                        wake.notify_all();
                        Err(error.error_code().to_owned())
                    }
                }
            }));
        }
        start.wait();
        let timed_out = {
            let (mutex, wake) = &*state;
            let mut state = mutex.lock().unwrap();
            let mut timed_out = false;
            while state.0 != 2 {
                let (next, timeout) = wake
                    .wait_timeout(state, std::time::Duration::from_secs(5))
                    .unwrap();
                state = next;
                if timeout.timed_out() {
                    timed_out = true;
                    break;
                }
            }
            state.1 = true;
            wake.notify_all();
            timed_out
        };
        let outcomes: Vec<Result<bool, String>> = workers
            .into_iter()
            .map(|worker| worker.join().expect("worker must not panic"))
            .collect();
        assert!(!timed_out, "both workers must report their attempt");
        assert_eq!(
            outcomes
                .iter()
                .filter(|outcome| matches!(outcome, Ok(true)))
                .count(),
            1
        );
        for outcome in outcomes {
            if let Err(error_code) = outcome {
                assert_eq!(error_code, "KIO-E-STORE-LOCKED-001");
            }
        }
    }

    #[cfg(windows)]
    #[test]
    fn windows_lock_rejects_junction_parent_without_touching_external_target() {
        let root = tempfile::tempdir().unwrap();
        let external = root.path().join("external");
        let junction = root.path().join("junction");
        fs::create_dir(&external).unwrap();
        let status = std::process::Command::new("cmd")
            .args(["/D", "/C", "mklink", "/J"])
            .arg(&junction)
            .arg(&external)
            .status()
            .expect("create Windows junction fixture");
        assert!(status.success(), "mklink /J must create the test junction");

        let path = junction.join("nested/ordinary.lock");
        assert!(StoreLock::acquire_path(path).is_err());
        assert!(
            !external.join("nested/ordinary.lock").exists(),
            "a junction must not receive a lock parent or leaf"
        );
        fs::remove_dir(&junction).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn unix_process_liveness_rejects_values_outside_the_pid_range() {
        assert!(!process_is_alive(0));
        assert!(!process_is_alive(RELEASED_LOCK_PID - 1));
    }

    #[cfg(windows)]
    #[test]
    fn windows_process_liveness_rejects_reserved_pid_zero() {
        assert!(!process_is_alive(0));
    }

    // F8: a device-global lock (e.g. the pre-2026-07-18 JSONL cost ledger's) is
    // acquired via `acquire_path` at an arbitrary path outside any `.kio`. It
    // creates the parent dir, then uses the verified exchange on macOS/Linux,
    // retained-handle deletion on Windows, or the token-checked fallback only
    // on other unsupported platforms; it refuses an independently held lock.
    #[test]
    fn f8_acquire_path_is_device_global_and_excludes_a_held_lock() {
        let dir = tempfile::tempdir().unwrap();
        // Nested path whose parent does not exist yet — acquire_path must create it.
        let lock_path = dir.path().join("kio/device-example.lock");
        {
            let _guard = StoreLock::acquire_path(lock_path.clone()).unwrap();
            assert!(
                lock_path.exists(),
                "lock file must be created under a fresh dir"
            );
        }
        #[cfg(any(target_os = "macos", target_os = "linux"))]
        assert!(
            lock_path.exists(),
            "macOS/Linux drop leaves an atomic release sentinel"
        );
        #[cfg(windows)]
        assert!(
            !lock_path.exists(),
            "Windows releases only its retained owned handle"
        );
        #[cfg(not(any(target_os = "macos", target_os = "linux", windows)))]
        assert!(
            !lock_path.exists(),
            "platforms without verified exchange use token-checked deletion"
        );

        let reacquired = StoreLock::acquire_path(lock_path.clone())
            .expect("next writer reacquires after release");
        assert!(lock_path.exists(), "reacquired writer owns the lock path");
        drop(reacquired);

        // A pre-existing lock file at the path blocks a fresh acquisition with
        // STORE-LOCKED, proving acquire_path honors a held device-global lock.
        fs::write(&lock_path, b"held by another charge").unwrap();
        // Keep the acquisition result (and a hypothetical successful guard)
        // alive across the assertion, matching Rust 2021's tail-expression
        // drop order even though this branch is expected to be an error.
        let contested_acquisition = StoreLock::acquire_path(lock_path.clone());
        match contested_acquisition {
            Ok(_) => panic!("a held device-global lock must block acquisition"),
            Err(err) => assert_eq!(err.error_code(), "KIO-E-STORE-LOCKED-001"),
        }
    }

    #[cfg(unix)]
    #[test]
    fn ordinary_lock_drop_unlocks_an_inherited_open_file_description() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("inherited.lock");
        let held = StoreLock::acquire_path(path.clone()).unwrap();
        let inherited_gate = held._gate.as_ref().unwrap()._file.try_clone().unwrap();

        drop(held);
        assert!(StoreLock::acquire_path(path).is_ok());
        drop(inherited_gate);
    }

    #[cfg(unix)]
    #[test]
    fn concurrent_reclaim_of_release_sentinel_has_one_owner() {
        use std::sync::{Arc, Barrier};

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("contended.lock");
        drop(StoreLock::acquire_path(path.clone()).unwrap());
        let start = Arc::new(Barrier::new(3));
        let mut workers = Vec::new();
        for _ in 0..2 {
            let start = Arc::clone(&start);
            let path = path.clone();
            workers.push(std::thread::spawn(move || {
                start.wait();
                match StoreLock::acquire_path(path) {
                    Ok(lock) => {
                        std::thread::sleep(std::time::Duration::from_millis(100));
                        drop(lock);
                        true
                    }
                    Err(error) => {
                        assert_eq!(error.error_code(), "KIO-E-STORE-LOCKED-001");
                        false
                    }
                }
            }));
        }
        start.wait();
        let outcomes: Vec<_> = workers
            .into_iter()
            .map(|worker| worker.join().unwrap())
            .collect();
        assert_eq!(outcomes.into_iter().filter(|outcome| *outcome).count(), 1);
    }

    #[test]
    fn redact_message_paths_masks_absolute_paths_only() {
        // P4: the exact leak shapes — `io error at {path}` and
        // `corrupt store file at {path}` — must lose the absolute path.
        assert_eq!(
            redact_message_paths("io error at /private/var/x/.kio/tasks.jsonl: Permission denied"),
            "io error at [redacted] Permission denied"
        );
        assert_eq!(
            redact_message_paths(
                "corrupt store file at /home/u/.kio/tasks.jsonl: expected value at line 1"
            ),
            "corrupt store file at [redacted] expected value at line 1"
        );
        // Relative tokens and plain prose are untouched (no false positives).
        assert_eq!(
            redact_message_paths("scope registry write failed (recover with index)"),
            "scope registry write failed (recover with index)"
        );
        assert!(!redact_message_paths("read /etc/hosts now").contains("/etc/hosts"));
        assert_eq!(
            redact_message_paths(
                r"corrupt store file at C:\Users\runner\.kio\tasks.jsonl: expected value"
            ),
            "corrupt store file at [redacted] expected value"
        );
        assert_eq!(
            redact_message_paths("read C:/Users/runner/.kio/tasks.jsonl now"),
            "read [redacted] now"
        );
        assert_eq!(
            redact_message_paths(r"io error at \\server\share\scope\.kio\tasks.jsonl: denied"),
            "io error at [redacted] denied"
        );
        assert_eq!(
            redact_message_paths(r"read \\?\C:\scope\.kio\tasks.jsonl now"),
            "read [redacted] now"
        );
        assert_eq!(
            redact_message_paths(r"relative C:scope\.kio\tasks.jsonl is unchanged"),
            r"relative C:scope\.kio\tasks.jsonl is unchanged"
        );
    }

    #[test]
    fn redact_context_masks_scope_path_and_candidates() {
        // P4: the extended allowlist covers the path-bearing keys used by the
        // purge / scope-ambiguous / registry error contexts.
        let mut context = json!({
            "scope_path": "/private/var/x/.kio",
            "candidates": ["/a/.kio", "/b/.kio"],
            "root_path": "/private/var/x",
            "kio_path": "/private/var/x/.kio",
            "raw_hash": "sha256:abc",
        });
        redact_context(&mut context);
        assert_eq!(context["scope_path"], "[redacted]");
        assert_eq!(context["candidates"], "[redacted]");
        assert_eq!(context["root_path"], "[redacted]");
        assert_eq!(context["kio_path"], "[redacted]");
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

    /// R23-16 (06 §11 L513): a fractional-seconds suffix is a valid persisted
    /// timestamp shape ("正: 2026-04-25T12:00:00.123456Z") that the parser
    /// used to reject outright (exact 20-byte match only) -- silently
    /// excluding any record whose `created_at` carried sub-second precision
    /// from callers like `kio log --since`.
    #[test]
    fn r23_16_parse_utc_seconds_accepts_fractional_suffix() {
        let whole = parse_utc_seconds("2026-07-03T00:00:00Z").unwrap();
        // Sub-second digits parse to the SAME whole-second value regardless of
        // digit count -- the return unit stays whole seconds.
        assert_eq!(
            parse_utc_seconds("2026-07-03T00:00:00.123456Z"),
            Some(whole)
        );
        assert_eq!(parse_utc_seconds("2026-07-03T00:00:00.1Z"), Some(whole));
        assert_eq!(
            parse_utc_seconds("2026-07-03T00:00:00.000000001Z"),
            Some(whole)
        );
        // Still rejects shapes that only superficially resemble the
        // fractional form.
        assert_eq!(parse_utc_seconds("2026-07-03T00:00:00.Z"), None); // no digits
        assert_eq!(parse_utc_seconds("2026-07-03T00:00:00.123456"), None); // no trailing Z
        assert_eq!(parse_utc_seconds("2026-07-03T00:00:00.12x456Z"), None); // non-digit
        assert_eq!(parse_utc_seconds("2026-07-03T00:00:00,123456Z"), None); // wrong separator
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
    fn ct4_purge_log_appenders_honor_device_and_scope_scrub_locks() {
        for (file_name, lock_name) in [
            ("events.jsonl", "scrub.lock"),
            ("access.jsonl", "access.scrub.lock"),
        ] {
            let dir = tempfile::tempdir().unwrap();
            let log = dir.path().join(file_name);
            let lock = dir.path().join(lock_name);
            let (ready_tx, ready_rx) = std::sync::mpsc::channel();
            let (release_tx, release_rx) = std::sync::mpsc::channel();
            let holder = std::thread::spawn(move || {
                let _guard = StoreLock::acquire_path(lock).unwrap();
                ready_tx.send(()).unwrap();
                release_rx.recv().unwrap();
            });
            ready_rx.recv().unwrap();
            let error = append_jsonl_rotating(&log, &json!({ "target": "late" }), 30).unwrap_err();
            assert_eq!(error.error_code(), "KIO-E-STORE-LOCKED-001");
            assert!(!log.exists(), "a contended post-scrub append must not land");
            release_tx.send(()).unwrap();
            holder.join().unwrap();

            append_jsonl_rotating(&log, &json!({ "target": "after" }), 30).unwrap();
            assert_eq!(fs::read_to_string(&log).unwrap().lines().count(), 1);
        }
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
    fn read_logs_retention_days_uses_only_observability_key() {
        let dir = tempfile::tempdir().unwrap();
        let cfg = dir.path().join("config.toml");
        fs::write(&cfg, "[observability]\nretention_days = 7\n").unwrap();
        assert_eq!(read_logs_retention_days(&cfg), Some(7));
        fs::write(&cfg, "[observability]\nretention_days = 0\n").unwrap();
        assert_eq!(read_logs_retention_days(&cfg), None);
        fs::write(&cfg, "[observability]\nretention_days = 3651\n").unwrap();
        assert_eq!(read_logs_retention_days(&cfg), None);
        fs::write(&cfg, "[logs]\nretention_days = 7\n").unwrap();
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
    fn cand_008_symlinked_kio_store_is_rejected() {
        use std::os::unix::fs::symlink;

        let victim = tempfile::tempdir().unwrap();
        let victim_repo = Repository::init(victim.path()).unwrap();
        let lure = tempfile::tempdir().unwrap();
        symlink(victim_repo.kio_dir(), lure.path().join(".kio")).unwrap();

        let error = Repository::open(lure.path()).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-UNSAFE-001");
    }

    #[cfg(unix)]
    #[test]
    fn cand_024_existing_store_requires_private_owner_mode() {
        use std::os::unix::fs::{MetadataExt, PermissionsExt};

        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let kio_dir = repo.kio_dir().to_path_buf();
        assert_eq!(
            fs::metadata(&kio_dir).unwrap().uid(),
            super::effective_uid()
        );

        fs::set_permissions(&kio_dir, fs::Permissions::from_mode(0o755)).unwrap();
        let error = Repository::open(dir.path()).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-UNSAFE-001");

        fs::set_permissions(&kio_dir, fs::Permissions::from_mode(0o700)).unwrap();
        Repository::open(dir.path()).unwrap();
        fs::set_permissions(&kio_dir, fs::Permissions::from_mode(0o500)).unwrap();
        Repository::open(dir.path()).unwrap();
        fs::set_permissions(&kio_dir, fs::Permissions::from_mode(0o700)).unwrap();
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
        assert_eq!(error.error_code(), "KIO-E-SCOPE-INPUT-OVERSIZED-001");

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
        assert_eq!(error.error_code(), "KIO-E-SCOPE-INPUT-OVERSIZED-001");
    }

    #[test]
    fn cand_019_oversized_sparse_snapshot_does_not_advance_head_or_write_raw() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let path = dir.path().join("oversized.bin");
        let file = fs::File::create(&path).unwrap();
        file.set_len(DEFAULT_MAX_ARCHIVE_FILE_BYTES + 1).unwrap();
        let head_before = fs::read(repo.kio_dir().join("HEAD")).unwrap();

        let error = repo.snapshot(Some("oversized"), None).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-SCOPE-INPUT-OVERSIZED-001");
        assert_eq!(fs::read(repo.kio_dir().join("HEAD")).unwrap(), head_before);
        assert_eq!(
            fs::read_dir(repo.kio_dir().join("objects/raw"))
                .unwrap()
                .count(),
            0
        );
    }

    #[test]
    fn ct4_raw_archive_removes_crash_orphans_before_new_staging() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let orphan = repo.kio_dir().join("objects/raw/.ingest-crashed-writer");
        fs::write(&orphan, b"stale private transaction bytes").unwrap();
        fs::write(dir.path().join("doc.md"), b"new authoritative bytes").unwrap();

        let outcome = repo.snapshot(Some("cleanup and archive"), None).unwrap();
        assert!(!orphan.exists());
        let tree = repo.read_tree(&outcome.tree_hash).unwrap();
        let raw_hash = tree
            .entries
            .iter()
            .find(|entry| entry.path == "doc.md")
            .unwrap()
            .raw_hash
            .clone();
        ObjectStore::new(repo.kio_dir())
            .inspect_object(ObjectKind::Raw, &raw_hash)
            .unwrap();
    }

    #[test]
    fn ct4_raw_archive_rejects_oversized_orphan_before_publication() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let orphan = repo.kio_dir().join("objects/raw/.ingest-oversized");
        fs::File::create(&orphan)
            .unwrap()
            .set_len(crate::cas::MAX_RAW_OBJECT_BYTES + 1)
            .unwrap();
        fs::write(dir.path().join("doc.md"), b"must not publish").unwrap();
        let head_before = fs::read(repo.kio_dir().join("HEAD")).unwrap();

        let error = repo.snapshot(Some("blocked cleanup"), None).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
        assert!(orphan.exists());
        assert_eq!(fs::read(repo.kio_dir().join("HEAD")).unwrap(), head_before);
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
            r#gen: 0,
            manifest_hash: hash_bytes(b"manifest"),
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
    fn scheduled_snapshot_rejects_raw_map_drift_before_cas_publication() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let path = dir.path().join("doc.txt");
        fs::write(&path, b"observed bytes").unwrap();
        repo.snapshot(Some("initial"), Some("2026-08-14T00:00:00Z"))
            .unwrap();
        let head_before = repo.head_commit_hash().unwrap();
        let expected = BTreeMap::from([("doc.txt".to_owned(), hash_bytes(b"observed bytes"))]);

        let changed = b"changed after the scheduled preview";
        fs::write(&path, changed).unwrap();
        let changed_raw = ObjectStore::new(repo.kio_dir())
            .object_path(ObjectKind::Raw, &hash_bytes(changed))
            .unwrap();
        assert!(!changed_raw.exists());

        let error = repo
            .snapshot_with_type(
                Some("scheduled test"),
                Some("2026-08-14T00:01:00Z"),
                CommitType::Auto,
                &BTreeSet::new(),
                &BTreeMap::new(),
                &BTreeSet::new(),
                false,
                &[],
                true,
                Some(&expected),
                None,
                None,
                None,
                None,
            )
            .unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-SNAPSHOT-AUTHORITY-CHANGED-001");
        assert_eq!(repo.head_commit_hash().unwrap(), head_before);
        assert!(!changed_raw.exists());
        assert!(
            fs::read_dir(repo.kio_dir().join("objects/raw"))
                .unwrap()
                .all(|entry| !entry
                    .unwrap()
                    .file_name()
                    .to_string_lossy()
                    .starts_with(".ingest-"))
        );
    }

    #[test]
    fn cand_043_poisoned_raw_slot_prevents_snapshot_publication() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        fs::write(dir.path().join("doc.txt"), b"expected bytes").unwrap();
        let hash = hash_bytes(b"expected bytes");
        let store = ObjectStore::new(repo.kio_dir());
        let object_path = store.object_path(ObjectKind::Raw, &hash).unwrap();
        fs::create_dir_all(object_path.parent().unwrap()).unwrap();
        fs::write(&object_path, b"poisoned").unwrap();
        let head_before = fs::read(repo.kio_dir().join("HEAD")).unwrap();

        let error = repo.snapshot(Some("poisoned"), None).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
        assert_eq!(fs::read(repo.kio_dir().join("HEAD")).unwrap(), head_before);
    }

    #[test]
    fn cand_036_persisted_dag_objects_are_semantically_validated() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        let store = ObjectStore::new(repo.kio_dir());
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
        let store = ObjectStore::new(repo.kio_dir());
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

        let head_before = fs::read(repo.kio_dir().join("HEAD")).unwrap();
        let branch_before = fs::read(repo.kio_dir().join("refs/heads/main")).unwrap();
        let error = repo.snapshot(Some("over-limit"), None).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-SCOPE-INPUT-OVERSIZED-001");
        assert_eq!(
            error.context()["observed_entries"],
            json!(MAX_TREE_ENTRIES + 1)
        );
        assert_eq!(error.context()["max_tree_entries"], json!(MAX_TREE_ENTRIES));
        assert_eq!(fs::read(repo.kio_dir().join("HEAD")).unwrap(), head_before);
        assert_eq!(
            fs::read(repo.kio_dir().join("refs/heads/main")).unwrap(),
            branch_before
        );
        for kind in ["raw", "trees", "commits"] {
            assert_eq!(
                fs::read_dir(repo.kio_dir().join("objects").join(kind))
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
        let kio_dir = repo.kio_dir().to_path_buf();
        let root = repo.root().to_path_buf();

        fs::write(root.join("doc.txt"), "v1").unwrap();
        let c1_hash = repo
            .snapshot(Some("c1"), None)
            .unwrap()
            .commit_hash
            .unwrap();

        // Corrupt HEAD to empty (crash truncation); refs still names C1.
        fs::write(kio_dir.join("HEAD"), "").unwrap();

        // A Repository built WITHOUT `open()` (so `self_heal_head` never runs) still
        // recovers the real HEAD from refs.
        let direct = Repository {
            root: root.clone(),
            canonical_root: root.clone(),
            kio_dir: kio_dir.clone(),
            store: ObjectStore::new(kio_dir.clone()),
            bound_root: None,
            bound_kio: None,
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
        fs::write(kio_dir.join("HEAD"), "").unwrap();
        fs::write(kio_dir.join("refs/heads/main"), "").unwrap();
        assert_eq!(
            direct.head_commit_hash().unwrap(),
            None,
            "both HEAD and refs empty is a genuinely unborn branch"
        );
    }

    #[test]
    fn purge_snapshot_forces_protected_child_when_tree_is_unchanged() {
        // P2-A / journal-barrier fix: purging a raw_hash that HEAD's tree no
        // longer references at all (superseded by a later edit) is the
        // "tree genuinely unchanged" case — `doc.txt` currently holds
        // "version two", so the working-tree scan never stages a "version
        // one" candidate and `purge_self_targets`' exclusion has nothing to
        // do. This is also the realistic shape of this scenario: purging an
        // old historical version while today's content is untouched.
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        fs::write(dir.path().join("doc.txt"), b"version one").unwrap();
        repo.snapshot(Some("v1"), Some("2026-07-11T00:00:00Z"))
            .unwrap();
        fs::write(dir.path().join("doc.txt"), b"version two").unwrap();
        let parent = repo
            .snapshot(Some("v2"), Some("2026-07-12T00:00:00Z"))
            .unwrap()
            .commit_hash
            .unwrap();
        let parent_tree = repo.read_commit(&parent).unwrap().tree;

        let outcome = repo
            .purged_snapshot(
                "legal",
                Some("2026-07-13T00:00:00Z"),
                &[hash_bytes(b"version one")],
                true,
            )
            .unwrap();
        assert!(!outcome.noop);
        let commit_hash = outcome.commit_hash.unwrap();
        let commit = repo.read_commit(&commit_hash).unwrap();
        assert_eq!(commit.commit_type, CommitType::Purged);
        assert_eq!(commit.message, "legal");
        assert_eq!(commit.parents, vec![parent]);
        assert_eq!(commit.tree, parent_tree);
        assert_eq!(commit.created_at, "2026-07-13T00:00:00Z");
        assert_eq!(commit.purged_raws, vec![hash_bytes(b"version one")]);
    }

    /// P2-A finding fix (05 §3.5 L741; `archive_staged_working_tree`'s doc
    /// comment): purge's own final `publish_ref=true` snapshot must succeed
    /// — and its tree must NOT carry the purged entry — even while the
    /// purge target's exact bytes are still physically present in the
    /// working tree (Kio never deletes the working-tree original). Before
    /// the fix, this raw publication attempt hit `archive_staged_working_tree`'s
    /// barrier check (an active journal targeting this same raw_hash) and the
    /// whole snapshot failed with `KIO-E-PURGE-INCOMPLETE-001` — reachable any
    /// time a real purge orchestration republishes its planned commit after
    /// the tombstone/journal phase has advanced past `prepared`, i.e. every
    /// ordinary purge whose target's working-tree residual was never deleted.
    #[test]
    fn purge_snapshot_succeeds_and_excludes_the_entry_while_journal_barrier_is_active() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        fs::write(dir.path().join("keep.txt"), b"keep").unwrap();
        fs::write(dir.path().join("residual.txt"), b"purge target bytes").unwrap();
        let raw_hash = hash_bytes(b"purge target bytes");
        repo.snapshot(Some("initial"), Some("2026-07-12T00:00:00Z"))
            .unwrap();

        // Simulate the real orchestration's post-`prepared` state: an active
        // purge journal whose barrier now covers this raw_hash (05 §3.5's
        // `tombstoned`/`deleted` phases), WITHOUT deleting the working-tree
        // original (purge never does — this is the residual).
        let purge = PurgeState::new(repo.kio_dir());
        let closure = crate::purge::PurgeClosure::new(
            "01ARZ3NDEKTSV4RRFFQ69G5FAV".to_owned(),
            vec![crate::purge::ClosureItem {
                object_type: "raw".to_owned(),
                hash: raw_hash.clone(),
            }],
            Vec::new(),
        )
        .unwrap();
        purge.write_closure(&closure).unwrap();
        let closure_hash = crate::purge::closure_content_hash(&closure).unwrap();
        let (journal, _) = match purge
            .begin(
                vec![raw_hash.clone()],
                crate::purge::PurgeReason::Legal,
                crate::purge::TombstoneMode::Default,
                "test-actor".to_owned(),
                "2026-07-13T00:00:00Z".to_owned(),
                1,
                // `planned_commit` only needs to be a well-formed hash here —
                // this test does not exercise `publish_planned_commit`'s
                // cross-check against it (that belongs to the CLI-level
                // orchestration tests).
                hash_bytes(b"planned"),
                closure_hash,
                "01ARZ3NDEKTSV4RRFFQ69G5FAW".to_owned(),
            )
            .unwrap()
        {
            crate::purge::BeginOutcome::Started(journal) => (journal, true),
            other => panic!("expected a fresh journal start, got {other:?}"),
        };
        let journal = purge
            .advance_phase(&journal, crate::purge::PurgePhase::Tombstoned)
            .unwrap();
        purge
            .advance_phase(&journal, crate::purge::PurgePhase::Deleted)
            .unwrap();
        assert!(purge.barrier_blocks(&raw_hash).unwrap());

        let outcome = repo
            .purged_snapshot(
                "legal",
                Some("2026-07-13T00:00:00Z"),
                std::slice::from_ref(&raw_hash),
                true,
            )
            .expect("purge's own snapshot must not trip its own journal barrier");
        let commit = outcome.commit.unwrap();
        assert_eq!(commit.commit_type, CommitType::Purged);
        let tree = repo.read_tree(&commit.tree).unwrap();
        assert_eq!(
            tree.entries
                .iter()
                .map(|entry| entry.path.as_str())
                .collect::<Vec<_>>(),
            vec!["keep.txt"],
            "the purge target's entry must be excluded even though its working-tree \
             bytes are still physically present"
        );
        // The residual original is untouched — 05 §3.5's "working tree の
        // 原本には触れない" — re-ingestion is deferred to the next `kio index`.
        assert_eq!(
            fs::read(dir.path().join("residual.txt")).unwrap(),
            b"purge target bytes"
        );
    }

    #[test]
    fn lc48_purged_snapshot_dry_run_computes_planned_commit_without_publishing_ref() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        fs::write(dir.path().join("doc.txt"), b"retained").unwrap();
        let parent = repo
            .snapshot(Some("initial"), Some("2026-07-12T00:00:00Z"))
            .unwrap()
            .commit_hash
            .unwrap();

        let dry = repo
            .purged_snapshot(
                "legal",
                Some("2026-07-13T00:00:00Z"),
                &[hash_bytes(b"retained")],
                false,
            )
            .unwrap();
        let planned_commit = dry.commit_hash.clone().unwrap();
        // The commit object is durably content-addressed (readable by hash)...
        let commit = repo.read_commit(&planned_commit).unwrap();
        assert_eq!(commit.commit_type, CommitType::Purged);
        // ...but HEAD/refs were not advanced onto it.
        assert_eq!(repo.head_commit_hash().unwrap(), Some(parent.clone()));

        // Publishing for real re-derives the identical hash (deterministic,
        // content-addressed) and advances HEAD.
        let real = repo
            .purged_snapshot(
                "legal",
                Some("2026-07-13T00:00:00Z"),
                &[hash_bytes(b"retained")],
                true,
            )
            .unwrap();
        assert_eq!(real.commit_hash, Some(planned_commit.clone()));
        assert_eq!(repo.head_commit_hash().unwrap(), Some(planned_commit));
    }

    #[test]
    fn purge_snapshot_captures_the_current_working_tree() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        fs::write(dir.path().join("keep.txt"), b"keep").unwrap();
        fs::write(dir.path().join("removed.txt"), b"remove before purge").unwrap();
        let parent = repo
            .snapshot(Some("initial"), Some("2026-07-12T00:00:00Z"))
            .unwrap()
            .commit_hash
            .unwrap();
        fs::remove_file(dir.path().join("removed.txt")).unwrap();

        let outcome = repo
            .purged_snapshot(
                "privacy",
                Some("2026-07-13T00:00:00Z"),
                &[hash_bytes(b"remove before purge")],
                true,
            )
            .unwrap();
        let commit = outcome.commit.unwrap();
        let tree = repo.read_tree(&commit.tree).unwrap();
        assert_eq!(commit.commit_type, CommitType::Purged);
        assert_eq!(commit.parents, vec![parent]);
        assert_eq!(outcome.stats.files_deleted, 1);
        assert_eq!(
            tree.entries
                .iter()
                .map(|entry| entry.path.as_str())
                .collect::<Vec<_>>(),
            vec!["keep.txt"]
        );
    }

    #[test]
    fn r23_29_log_from_stops_before_exceeding_the_first_parent_commit_cap() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        for index in 0..4 {
            fs::write(dir.path().join("file.txt"), format!("v{index}")).unwrap();
            repo.snapshot(Some(&format!("commit {index}")), None)
                .unwrap();
        }

        let report = repo.log_from_with_limit(None, 1_000).unwrap();
        assert!(!report.truncated);
        let total = report.entries.len() as u64;
        assert!(total >= 4);

        // One below the actual first-parent chain length: R23-29 stops
        // BEFORE crossing (05-runtime.md §1.6 L313's "次の object/entry で
        // 1 つでも超える前に停止する"), never returning a partial log.
        let error = repo.log_from_with_limit(None, total - 1).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-COMMIT-HISTORY-LIMIT-001");
        assert_eq!(error.context()["exceeded"], json!("commits"));

        // Exactly at the true chain length still succeeds.
        let exact = repo.log_from_with_limit(None, total).unwrap();
        assert_eq!(exact.entries.len() as u64, total);
        assert!(!exact.truncated);

        // The public `log_from`/`log` entry points thread the real default
        // (100,000 -- `history::DEFAULT_MAX_HISTORY_COMMITS`), confirmed not
        // to trip for this tiny chain.
        assert!(!repo.log().unwrap().truncated);
    }
    #[test]
    fn adapter_lane_reads_only_the_two_declared_values() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        // Absent key / absent file → the caller keeps its own default.
        assert_eq!(read_adapter_lane(&path), None);
        std::fs::write(&path, "[chunking]\nstrategy = \"heading\"\n").unwrap();
        assert_eq!(read_adapter_lane(&path), None);
        // Both declared values round-trip.
        std::fs::write(&path, "[adapter]\nlane = \"batch\"\n").unwrap();
        assert_eq!(read_adapter_lane(&path).as_deref(), Some("batch"));
        std::fs::write(&path, "[adapter]\nlane = \"realtime\"\n").unwrap();
        assert_eq!(read_adapter_lane(&path).as_deref(), Some("realtime"));
        // Anything else is ignored here; the JSON schema is what rejects it
        // loudly at startup, and this defensive read must not invent a lane.
        std::fs::write(&path, "[adapter]\nlane = \"sometimes\"\n").unwrap();
        assert_eq!(read_adapter_lane(&path), None);
        std::fs::write(&path, "[adapter]\nlane = 3\n").unwrap();
        assert_eq!(read_adapter_lane(&path), None);
    }

    #[test]
    fn tool_lock_canonicalization_rejects_unknown_inner_fields() {
        let value = serde_json::json!({
            "spec_version": 1,
            "markdown": {
                "tool_id": "mistral_ocr_markdownize",
                "profile_hash": "sha256:test",
                "auth": "plain:shared-secret"
            }
        });
        let error = super::canonical_tool_lock_value(&value).unwrap_err();
        assert!(error.to_string().contains("markdown.auth"));
    }

    #[test]
    fn unchanged_snapshot_does_not_repair_or_publish_a_missing_tool_lock() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        fs::write(dir.path().join("doc.txt"), b"stable").unwrap();
        let first = repo
            .snapshot(Some("initial"), Some("2026-08-20T00:00:00Z"))
            .unwrap();
        let commit = first.commit.unwrap();
        let tool_lock_path = ObjectStore::new(repo.kio_dir())
            .content_path(ContentObjectKind::Toollock, &commit.tool_lock_hash)
            .unwrap();
        fs::remove_file(&tool_lock_path).unwrap();

        let second = repo
            .snapshot(Some("unchanged"), Some("2026-08-20T00:00:01Z"))
            .unwrap();
        assert!(second.noop);
        assert!(!tool_lock_path.exists());
    }
}
