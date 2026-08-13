//! FTS5 external-content index contracts.

use std::collections::BTreeSet;
#[cfg(unix)]
use std::ffi::CStr;
use std::path::{Path, PathBuf};
#[cfg(unix)]
use std::sync::{Once, OnceLock};

use cap_primitives::fs as cap_fs;
use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use serde::{Deserialize, Serialize};
use unicode_normalization::UnicodeNormalization;

use crate::search_projection::resolve_markdown_escapes;
use crate::{chunking::validate_unit_hash, ChunkRow, IndexError, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FtsTokenizer {
    Trigram,
    Unicode61RemoveDiacritics2,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FtsSchemaConfig {
    pub tokenizer: FtsTokenizer,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FtsMatch {
    pub chunk_id: String,
    pub rank: u64,
    pub bm25_score: f64,
}

/// Rows removed from the derived index for one purged raw object.
///
/// `chunk_ids` is sorted so callers can deterministically remove the matching
/// chunk CAS objects and durable-ledger records after this transaction commits.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct PurgeRawIndexReport {
    pub chunk_ids: Vec<String>,
    pub deleted_chunks: u64,
    pub deleted_associations: u64,
    pub deleted_chunk_vectors: u64,
    /// `image_vec` rows removed (05 §3.5). Separate from
    /// `deleted_chunk_vectors` because the two are decided by different rules:
    /// a chunk vector goes with its chunk, an image vector only when no
    /// surviving chunk still references the image.
    pub deleted_image_vectors: u64,
    pub deleted_orphan_embeddings: u64,
    /// The `embeddings.id` of every orphan row just deleted — the CAS objects
    /// purge must remove alongside them (05 §3.5). A count cannot name a file,
    /// and the rows are gone by the time the caller could ask.
    pub deleted_embedding_ids: Vec<String>,
}

pub struct SqliteFtsIndex {
    conn: Connection,
    _source: Option<BoundSourceIndex>,
}

pub struct SourceIndexConnection {
    conn: Connection,
    _source: BoundSourceIndex,
}
impl std::ops::Deref for SourceIndexConnection {
    type Target = Connection;
    fn deref(&self) -> &Self::Target {
        &self.conn
    }
}
impl std::ops::DerefMut for SourceIndexConnection {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.conn
    }
}
impl std::fmt::Debug for SourceIndexConnection {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SourceIndexConnection")
            .finish_non_exhaustive()
    }
}

/// Access mode for [`open_existing_source_index_connection`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExistingSourceIndexOpenMode {
    ReadOnly,
    ReadWrite,
}

/// Resolve an index parent before passing the untrusted leaf to SQLite.
///
/// `SQLITE_OPEN_NOFOLLOW` applies to every component SQLite receives.  The
/// parent therefore needs to be resolved separately: Kio must accept an
/// OS-owned ancestor symlink, but it must never follow a link installed at the
/// final `sqlite.db` component.
fn source_index_path_in_resolved_parent(path: &std::path::Path) -> Result<std::path::PathBuf> {
    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| std::path::Path::new("."));
    // The immediate `.kio/index` parent is repository-controlled. Do not
    // canonicalize through a replacement symlink here: unlike an OS-owned
    // ancestor such as `/var`, that would redirect a fresh sqlite.db bootstrap
    // into an attacker-selected directory.
    let parent_metadata = std::fs::symlink_metadata(parent).map_err(|error| {
        IndexError::Schema(format!(
            "inspect source index parent {}: {error}",
            parent.display()
        ))
    })?;
    if parent_metadata.file_type().is_symlink() || !parent_metadata.is_dir() {
        return Err(IndexError::Schema(format!(
            "source index parent must be a real directory, not a symlink: {}",
            parent.display()
        )));
    }
    let file_name = path.file_name().ok_or_else(|| {
        IndexError::Schema(format!(
            "source index path has no file name: {}",
            path.display()
        ))
    })?;
    Ok(parent.join(file_name))
}

struct BoundSourceIndex {
    // Keep the repository-owned root (normally `.kio`) as well as `index`.
    // Opening `index` relative to this descriptor is what keeps a concurrent
    // replacement of `.kio` from changing the authority used for SQLite.
    _root: std::fs::File,
    _parent: std::fs::File,
    file: std::fs::File,
    public_path: PathBuf,
}

fn bind_source_index(
    path: &Path,
    writable: bool,
    create_missing: bool,
) -> Result<BoundSourceIndex> {
    let path = source_index_path_in_resolved_parent(path)?;
    let parent = path.parent().expect("source index has a parent");
    let root = parent.parent().filter(|root| !root.as_os_str().is_empty());
    let (root_handle, parent_handle) = if let Some(root) = root {
        // A descriptor-bound child index has already changed cwd to the
        // retained `.kio` directory, which is represented as `.`. Treat that
        // current directory as the root capability directly instead of trying
        // to split `.` into a public parent/leaf path.
        if root == Path::new(".") {
            let root_handle =
                cap_fs::open_ambient_dir(Path::new("."), cap_primitives::ambient_authority())
                    .map_err(|e| {
                        IndexError::Schema(format!("open descriptor-bound source index root: {e}"))
                    })?;
            let parent_leaf = parent.file_name().expect("source index parent has a leaf");
            let parent_handle = cap_fs::open_dir_nofollow(&root_handle, Path::new(parent_leaf))
                .map_err(|e| {
                    IndexError::Schema(format!(
                        "open source index parent {}: {e}",
                        parent.display()
                    ))
                })?;
            (root_handle, parent_handle)
        } else {
            let root_leaf = root.file_name().ok_or_else(|| {
                IndexError::Schema(format!(
                    "source index parent has no repository root component: {}",
                    parent.display()
                ))
            })?;
            let outer = root
                .parent()
                .filter(|outer| !outer.as_os_str().is_empty())
                .unwrap_or_else(|| Path::new("."));
            let before_root = std::fs::symlink_metadata(root).map_err(|e| {
                IndexError::Schema(format!("inspect source index root {}: {e}", root.display()))
            })?;
            if before_root.file_type().is_symlink() || !before_root.is_dir() {
                return Err(IndexError::Schema(format!(
                    "source index root must be a real directory, not a symlink: {}",
                    root.display()
                )));
            }
            let outer_handle = cap_fs::open_ambient_dir(outer, cap_primitives::ambient_authority())
                .map_err(|e| {
                    IndexError::Schema(format!(
                        "open source index root ancestor {}: {e}",
                        outer.display()
                    ))
                })?;
            let root_handle = cap_fs::open_dir_nofollow(&outer_handle, Path::new(root_leaf))
                .map_err(|e| {
                    IndexError::Schema(format!("open source index root {}: {e}", root.display()))
                })?;
            let opened_root = root_handle.metadata().map_err(|e| {
                IndexError::Schema(format!(
                    "inspect opened source index root {}: {e}",
                    root.display()
                ))
            })?;
            if !same_std_and_cap_directory(&before_root, &opened_root) {
                return Err(IndexError::Schema(format!(
                    "source index root changed while opening: {}",
                    root.display()
                )));
            }
            let parent_leaf = parent.file_name().expect("source index parent has a leaf");
            let parent_handle = cap_fs::open_dir_nofollow(&root_handle, Path::new(parent_leaf))
                .map_err(|e| {
                    IndexError::Schema(format!(
                        "open source index parent {}: {e}",
                        parent.display()
                    ))
                })?;
            (root_handle, parent_handle)
        }
    } else {
        // A bare relative path has no repository-root component to bind. Keep
        // the old lstat/open/identity check for that API convenience case.
        let before = std::fs::symlink_metadata(parent).map_err(|e| {
            IndexError::Schema(format!(
                "inspect source index parent {}: {e}",
                parent.display()
            ))
        })?;
        let handle = cap_fs::open_ambient_dir(parent, cap_primitives::ambient_authority())
            .map_err(|e| {
                IndexError::Schema(format!(
                    "open source index parent {}: {e}",
                    parent.display()
                ))
            })?;
        let after = handle.metadata().map_err(|e| {
            IndexError::Schema(format!(
                "inspect opened source index parent {}: {e}",
                parent.display()
            ))
        })?;
        if !same_std_and_cap_directory(&before, &after) {
            return Err(IndexError::Schema(format!(
                "source index parent changed while opening: {}",
                parent.display()
            )));
        }
        (
            handle.try_clone().map_err(|e| {
                IndexError::Schema(format!(
                    "retain source index parent {}: {e}",
                    parent.display()
                ))
            })?,
            handle,
        )
    };
    let before = parent_handle.metadata().map_err(|e| {
        IndexError::Schema(format!(
            "inspect opened source index parent {}: {e}",
            parent.display()
        ))
    })?;
    if !before.is_dir() {
        return Err(IndexError::Schema(format!(
            "source index parent is not a directory: {}",
            parent.display()
        )));
    }
    let leaf = path.file_name().expect("source index has a leaf");
    let before_leaf = cap_source_leaf_identity(&parent_handle, Path::new(leaf))?;
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        .write(writable)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    #[cfg(windows)]
    {
        // SQLite's public-path open below cannot be passed this capability
        // handle. Keep this leaf handle open without FILE_SHARE_DELETE so a
        // concurrent rename/delete (and therefore path replacement) is denied
        // until SQLite has completed its own open and the connection closes.
        // cap-primitives gives directory handles this policy by default, but
        // ordinary file OpenOptions intentionally default to allowing delete.
        use cap_fs::OpenOptionsExt;
        use windows_sys::Win32::Storage::FileSystem::{FILE_SHARE_READ, FILE_SHARE_WRITE};
        options.share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE);
    }
    if create_missing && before_leaf.is_none() {
        options.create_new(true);
    }
    let file = cap_fs::open(&parent_handle, Path::new(leaf), &options)
        .map_err(|e| IndexError::Schema(format!("inspect source index {}: {e}", path.display())))?;
    validate_bound_source_file(&file, &path)?;
    if let Some(before_leaf) = before_leaf {
        if source_file_identity(&file)? != before_leaf {
            return Err(IndexError::Schema(format!(
                "source index leaf changed while opening: {}",
                path.display()
            )));
        }
    }
    Ok(BoundSourceIndex {
        _root: root_handle,
        _parent: parent_handle,
        file,
        public_path: path,
    })
}

#[derive(Clone, Copy, PartialEq, Eq)]
struct SourceFileIdentity {
    #[cfg(unix)]
    dev: u64,
    #[cfg(unix)]
    ino: u64,
    #[cfg(windows)]
    volume_serial_number: Option<u32>,
    #[cfg(windows)]
    file_index: Option<u64>,
}
#[cfg(unix)]
fn cap_source_leaf_identity(
    parent: &std::fs::File,
    leaf: &Path,
) -> Result<Option<SourceFileIdentity>> {
    use cap_fs::MetadataExt;
    match cap_fs::stat(parent, leaf, cap_fs::FollowSymlinks::No) {
        Ok(metadata) if metadata.is_file() && metadata.nlink() == 1 => {
            Ok(Some(SourceFileIdentity {
                dev: metadata.dev(),
                ino: metadata.ino(),
            }))
        }
        Ok(metadata) if metadata.is_file() => Err(IndexError::Schema(format!(
            "source index target must have exactly one hard link (found {}): {}",
            metadata.nlink(),
            leaf.display()
        ))),
        Ok(_) => Err(IndexError::Schema(format!(
            "source index target is not a regular file: {}",
            leaf.display()
        ))),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(IndexError::Schema(format!(
            "inspect source index {}: {error}",
            leaf.display()
        ))),
    }
}
#[cfg(windows)]
fn cap_source_leaf_identity(
    parent: &std::fs::File,
    leaf: &Path,
) -> Result<Option<SourceFileIdentity>> {
    use cap_fs::MetadataExt;
    match cap_fs::stat(parent, leaf, cap_fs::FollowSymlinks::No) {
        Ok(metadata) if metadata.is_file() => Ok(Some(SourceFileIdentity {
            volume_serial_number: metadata.volume_serial_number(),
            file_index: metadata.file_index(),
        })),
        Ok(_) => Err(IndexError::Schema(format!(
            "source index target is not a regular file: {}",
            leaf.display()
        ))),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(IndexError::Schema(format!(
            "inspect source index {}: {error}",
            leaf.display()
        ))),
    }
}
#[cfg(not(any(unix, windows)))]
fn cap_source_leaf_identity(
    _parent: &std::fs::File,
    _leaf: &Path,
) -> Result<Option<SourceFileIdentity>> {
    Err(IndexError::Schema(
        "source SQLite capability binding is unsupported on this platform".to_owned(),
    ))
}
#[cfg(unix)]
fn source_file_identity(file: &std::fs::File) -> Result<SourceFileIdentity> {
    use std::os::unix::fs::MetadataExt;
    let m = file
        .metadata()
        .map_err(|e| IndexError::Schema(format!("inspect opened source index: {e}")))?;
    Ok(SourceFileIdentity {
        dev: m.dev(),
        ino: m.ino(),
    })
}
#[cfg(not(any(unix, windows)))]
fn source_file_identity(_: &std::fs::File) -> Result<SourceFileIdentity> {
    Ok(SourceFileIdentity {})
}
#[cfg(windows)]
fn source_file_identity(file: &std::fs::File) -> Result<SourceFileIdentity> {
    use std::os::windows::fs::MetadataExt;
    let metadata = file
        .metadata()
        .map_err(|e| IndexError::Schema(format!("inspect opened source index: {e}")))?;
    Ok(SourceFileIdentity {
        volume_serial_number: metadata.volume_serial_number(),
        file_index: metadata.file_index(),
    })
}

#[cfg(unix)]
fn same_std_and_cap_directory(before: &std::fs::Metadata, after: &std::fs::Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    before.dev() == after.dev() && before.ino() == after.ino()
}
#[cfg(windows)]
fn same_std_and_cap_directory(before: &std::fs::Metadata, after: &std::fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    before.volume_serial_number() == after.volume_serial_number()
        && before.file_index() == after.file_index()
}
#[cfg(not(any(unix, windows)))]
fn same_std_and_cap_directory(_: &std::fs::Metadata, _: &std::fs::Metadata) -> bool {
    false
}

fn validate_bound_source_file(file: &std::fs::File, path: &Path) -> Result<()> {
    let metadata = file.metadata().map_err(|e| {
        IndexError::Schema(format!(
            "inspect opened source index {}: {e}",
            path.display()
        ))
    })?;
    if !metadata.is_file() {
        return Err(IndexError::Schema(format!(
            "source index target is not a regular file: {}",
            path.display()
        )));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.nlink() != 1 {
            return Err(IndexError::Schema(format!(
                "source index target must have exactly one hard link (found {}): {}",
                metadata.nlink(),
                path.display()
            )));
        }
    }
    Ok(())
}
impl BoundSourceIndex {
    #[cfg(unix)]
    fn sqlite_path(&self) -> PathBuf {
        use std::os::fd::AsRawFd;
        PathBuf::from(format!("/dev/fd/{}", self.file.as_raw_fd()))
    }
    #[cfg(not(unix))]
    fn sqlite_path(&self) -> PathBuf {
        self.public_path.clone()
    }
}

#[cfg(unix)]
const BOUND_SOURCE_VFS_NAME: &CStr = c"kio-bound-source-unix";
#[cfg(unix)]
static BOUND_SOURCE_VFS_INIT: Once = Once::new();
#[cfg(unix)]
static BOUND_SOURCE_VFS_RESULT: OnceLock<std::result::Result<(), String>> = OnceLock::new();
#[cfg(unix)]
static BOUND_SOURCE_DEFAULT_VFS: OnceLock<usize> = OnceLock::new();

#[cfg(unix)]
fn open_bound_source_connection(path: &Path, flags: OpenFlags) -> Result<Connection> {
    BOUND_SOURCE_VFS_INIT.call_once(|| {
        let result = unsafe {
            let original = rusqlite::ffi::sqlite3_vfs_find(std::ptr::null());
            if original.is_null() {
                Err("SQLite has no default VFS".to_owned())
            } else {
                let _ = BOUND_SOURCE_DEFAULT_VFS.set(original as usize);
                let mut wrapped = Box::new(*original);
                wrapped.zName = BOUND_SOURCE_VFS_NAME.as_ptr();
                wrapped.xFullPathname = Some(bound_source_x_full_pathname);
                let code = rusqlite::ffi::sqlite3_vfs_register(Box::into_raw(wrapped), 0);
                if code == rusqlite::ffi::SQLITE_OK {
                    Ok(())
                } else {
                    Err(format!(
                        "register bound source SQLite VFS: SQLite error {code}"
                    ))
                }
            }
        };
        let _ = BOUND_SOURCE_VFS_RESULT.set(result);
    });
    BOUND_SOURCE_VFS_RESULT
        .get()
        .expect("VFS initializer sets result")
        .as_ref()
        .map_err(|e| IndexError::Schema(e.clone()))?;
    Ok(Connection::open_with_flags_and_vfs(
        path,
        flags,
        "kio-bound-source-unix",
    )?)
}
#[cfg(not(unix))]
fn open_bound_source_connection(path: &Path, flags: OpenFlags) -> Result<Connection> {
    Ok(Connection::open_with_flags(path, flags)?)
}

#[cfg(unix)]
unsafe extern "C" fn bound_source_x_full_pathname(
    _: *mut rusqlite::ffi::sqlite3_vfs,
    name: *const std::ffi::c_char,
    output_len: std::ffi::c_int,
    output: *mut std::ffi::c_char,
) -> std::ffi::c_int {
    if name.is_null() || output.is_null() || output_len <= 0 {
        return rusqlite::ffi::SQLITE_CANTOPEN;
    }
    let bytes = unsafe { CStr::from_ptr(name).to_bytes() };
    if is_bound_source_fd_name(bytes) {
        if bytes.len() + 1 > output_len as usize {
            return rusqlite::ffi::SQLITE_CANTOPEN;
        }
        unsafe {
            std::ptr::copy_nonoverlapping(
                bytes.as_ptr().cast::<std::ffi::c_char>(),
                output,
                bytes.len(),
            );
            *output.add(bytes.len()) = 0;
        }
        return rusqlite::ffi::SQLITE_OK;
    }
    let Some(default_vfs) = BOUND_SOURCE_DEFAULT_VFS.get() else {
        return rusqlite::ffi::SQLITE_CANTOPEN;
    };
    let default_vfs = *default_vfs as *mut rusqlite::ffi::sqlite3_vfs;
    let Some(callback) = (unsafe { (*default_vfs).xFullPathname }) else {
        return rusqlite::ffi::SQLITE_CANTOPEN;
    };
    unsafe { callback(default_vfs, name, output_len, output) }
}
#[cfg(unix)]
fn is_bound_source_fd_name(value: &[u8]) -> bool {
    value
        .strip_prefix(b"/dev/fd/")
        .is_some_and(|fd| !fd.is_empty() && fd.iter().all(u8::is_ascii_digit))
}

/// Open an existing, current source index without following its final path
/// component or creating a missing database.
///
/// This is for callers that need the raw SQLite connection rather than the FTS
/// wrapper. It validates the complete public schema before returning, so it
/// cannot accidentally adopt an empty, partial, or legacy `sqlite.db`.
pub fn open_existing_source_index_connection(
    path: impl AsRef<std::path::Path>,
    mode: ExistingSourceIndexOpenMode,
    config: &FtsSchemaConfig,
) -> Result<SourceIndexConnection> {
    crate::vec::ensure_registered();
    let source = bind_source_index(
        path.as_ref(),
        mode == ExistingSourceIndexOpenMode::ReadWrite,
        false,
    )?;

    let flags = match mode {
        ExistingSourceIndexOpenMode::ReadOnly => {
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NOFOLLOW
        }
        ExistingSourceIndexOpenMode::ReadWrite => {
            OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NOFOLLOW
        }
    };
    let conn = open_bound_source_connection(&source.sqlite_path(), flags)?;
    // The pre-open metadata check is not a lock. Recheck the visible leaf
    // after SQLite's NOFOLLOW lookup to catch the common replacement races
    // without making unsafe assumptions about raw file descriptors.
    validate_bound_source_file(&source.file, &source.public_path)?;
    if mode == ExistingSourceIndexOpenMode::ReadWrite {
        // Keep mutable raw-connection users subject to the same sidecar policy
        // as `SqliteFtsIndex::open`.
        conn.pragma_update(None, "journal_mode", "MEMORY")?;
    }
    if !validate_current_schema(&conn, config)? {
        return Err(schema_rebuild_error(
            "source index has no current index schema".to_owned(),
        ));
    }
    Ok(SourceIndexConnection {
        conn,
        _source: source,
    })
}

impl SqliteFtsIndex {
    pub fn open(path: impl AsRef<std::path::Path>, config: FtsSchemaConfig) -> Result<Self> {
        // The `vec0` module must be registered before the connection opens, else
        // the `chunk_vec` virtual table cannot be created or queried (04 §4.3).
        crate::vec::ensure_registered();
        let source = bind_source_index(path.as_ref(), true, true)?;
        // The source index is durable, but its SQLite journal is not an
        // independently validated Kio artifact.  Keep the rollback journal in
        // memory so SQLite never opens a `-journal`, `-wal`, or `-shm` sidecar
        // through a pathname that is not protected by this primary-file
        // `NOFOLLOW` open.  This is a derived database and can be rebuilt from
        // Kio's durable commit/tree/CAS sources if a process or power failure
        // interrupts a write; it deliberately does not promise crash recovery
        // from an on-disk SQLite journal.
        //
        // Resolve the parent first (rather than rejecting every ancestor
        // symlink): OS-owned directories such as `/var` can legitimately be
        // symlinked.  SQLite then performs the security-sensitive final lookup
        // with `SQLITE_OPEN_NOFOLLOW`, closing the validation/open race.
        let conn = open_bound_source_connection(
            &source.sqlite_path(),
            OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )?;
        validate_bound_source_file(&source.file, &source.public_path)?;
        conn.pragma_update(None, "journal_mode", "MEMORY")?;
        ensure_schema_on_connection(&conn, config)?;
        Ok(Self {
            conn,
            _source: Some(source),
        })
    }

    pub fn in_memory(config: FtsSchemaConfig) -> Result<Self> {
        crate::vec::ensure_registered();
        let conn = Connection::open_in_memory()?;
        ensure_schema_on_connection(&conn, config)?;
        Ok(Self {
            conn,
            _source: None,
        })
    }

    #[must_use]
    pub fn connection(&self) -> &Connection {
        &self.conn
    }

    pub fn ensure_schema(&mut self, config: FtsSchemaConfig) -> Result<()> {
        ensure_schema_on_connection(&self.conn, config)
    }

    pub fn index_chunk(&mut self, row: &ChunkRow) -> Result<()> {
        self.index_chunk_with_association_rowid(row, None)
            .map(|_| ())
    }

    /// Insert an immutable chunk row and append its chunking-config generation.
    ///
    /// Fresh indexing passes `None` and lets SQLite allocate the monotonically
    /// increasing association rowid. Durable-ledger replay may pass the recorded
    /// rowid so a rebuilt database preserves cursor ordering exactly.
    /// `row.chunking_config_introduction_commit` (PC40) is recorded exactly as
    /// [`Self::index_chunk_with_rowids`] does — the caller must provide it.
    pub fn index_chunk_with_association_rowid(
        &mut self,
        row: &ChunkRow,
        association_rowid: Option<u64>,
    ) -> Result<u64> {
        self.index_chunk_with_rowids(row, None, association_rowid)
            .map(|(_, association_rowid)| association_rowid)
    }

    /// Replay one durable chunk/config ledger record with stable rowids.
    ///
    /// `chunk_rowid` is shared by every association record for the immutable
    /// chunk. Both explicit rowids are collision-checked inside one savepoint so
    /// a malformed ledger cannot partially publish either side of the relation.
    ///
    /// `row.chunking_config_introduction_commit` (PC40, 05 §1.6 L266) is the
    /// commit at which THIS `(chunk_id, chunking_config_hash, introduction_commit)` association
    /// was created — read from the row rather than taken as a separate parameter
    /// so a rebuild replaying an already-durable `chunks.jsonl` record cannot
    /// accidentally re-stamp it with "today's HEAD" (it is stamped only when
    /// the association triple is genuinely new, matching
    /// `record_chunk_config_association`'s existing-row branch, which never
    /// touches an already-existing triple's immutable columns). Chunk-level
    /// publication events (PC37, potentially several per chunk) are a
    /// separate, caller-driven concern — see [`record_chunk_publication`].
    pub fn index_chunk_with_rowids(
        &mut self,
        row: &ChunkRow,
        chunk_rowid: Option<u64>,
        association_rowid: Option<u64>,
    ) -> Result<(u64, u64)> {
        validate_unit_hash("unit_content_hash", &row.unit_content_hash)?;
        if row.chunking_config_introduction_commit.is_empty() {
            return Err(IndexError::Contract(
                "chunk/config association introduction commit is required".to_owned(),
            ));
        }
        let association_introduction_commit = row.chunking_config_introduction_commit.as_str();
        if chunk_rowid == Some(0) {
            return Err(IndexError::Contract(
                "chunk rowid must be positive".to_owned(),
            ));
        }
        // Q4: the trigram tokenizer stops at a NUL byte, so any text after a
        // U+0000 (e.g. a UTF-16-LE `.txt` decoded lossily keeps interleaved NULs)
        // would be silently unsearchable even though `index` reported success.
        // Strip NULs from the value bound into the external-content `text` column
        // (which feeds `chunk_fts`) so the whole chunk is tokenizable. Identity /
        // evidence are untouched: `chunk_id`, `text_hash`, `byte_start/end` and the
        // persisted `chunks.jsonl` / normalized markdown all still carry the
        // original bytes — only this derived search index projection is sanitized.
        //
        // F2: normalize the projection to NFC first. The trigram tokenizer is not
        // Unicode-normalizing, so NFD content (common on macOS/APFS, some IMEs, and
        // OCR/PDF extraction) would be silently unsearchable by an NFC query and
        // vice versa. The CLI query path is normalized to the same NFC form, so
        // canonically-equivalent content and queries match regardless of input
        // form. This is a derived-index projection only; the char offsets that
        // evidence resolves against remain over the original `row.text`.
        //
        // F3: resolve Markdown escapes last, over text that is already NFC and
        // already free of NULs so that neither can sit between a backslash and
        // the character it escapes. 07 §5.2.1 has provider raw text escaped
        // maximally on the way in, which puts a backslash in front of every
        // ASCII punctuation character, so a recovered `期限 7/10` is stored as
        // `期限 7\/10` and the query `7/10` never even becomes a candidate. See
        // `search_projection` for why code is exempted rather than unescaped
        // along with everything else.
        let indexed_text =
            resolve_markdown_escapes(&row.text.nfc().collect::<String>().replace('\u{0}', ""));
        with_savepoint(&self.conn, "kio_index_chunk", || {
            let requested_chunk_rowid = chunk_rowid.map(sql_rowid).transpose()?;
            let existing_chunk_rowid = self
                .conn
                .query_row(
                    "SELECT rowid FROM chunks WHERE chunk_id = ?1",
                    params![row.chunk_id],
                    |result| result.get::<_, i64>(0),
                )
                .optional()?;
            let actual_chunk_rowid = match existing_chunk_rowid {
                Some(existing) => {
                    if requested_chunk_rowid.is_some_and(|requested| requested != existing) {
                        return Err(IndexError::Contract(format!(
                            "chunk {} has rowid {existing}, not requested rowid {}",
                            row.chunk_id,
                            requested_chunk_rowid.expect("checked as some")
                        )));
                    }
                    existing
                }
                None => {
                    let heading_path =
                        serde_json::to_string(&row.heading_path.clone().unwrap_or_default())?;
                    if let Some(requested) = requested_chunk_rowid {
                        let occupied = self
                            .conn
                            .query_row(
                                "SELECT chunk_id FROM chunks WHERE rowid = ?1",
                                params![requested],
                                |result| result.get::<_, String>(0),
                            )
                            .optional()?;
                        if let Some(occupied) = occupied {
                            return Err(IndexError::Contract(format!(
                                "chunk rowid {requested} is already occupied by {occupied}"
                            )));
                        }
                        self.conn.execute(
                            "INSERT INTO chunks(
                                rowid, chunk_id, raw_hash, tool_profile_hash, gen, unit_key,
                                unit_content_hash,
                                raw_path, heading_path, section_id, byte_start, byte_end,
                                text_hash, text, first_seen_commit, created_at
                             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)",
                            params![
                                requested,
                                row.chunk_id,
                                row.raw_hash,
                                row.tool_profile_hash,
                                row.gen,
                                row.unit_key,
                                row.unit_content_hash,
                                row.raw_path,
                                heading_path,
                                row.section_id,
                                row.byte_start,
                                row.byte_end,
                                row.text_hash,
                                indexed_text,
                                row.first_seen_commit,
                                row.created_at,
                            ],
                        )?;
                        requested
                    } else {
                        self.conn.execute(
                            "INSERT INTO chunks(
                                chunk_id, raw_hash, tool_profile_hash, gen, unit_key,
                                unit_content_hash,
                                raw_path, heading_path, section_id, byte_start, byte_end,
                                text_hash, text, first_seen_commit, created_at
                             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)",
                            params![
                                row.chunk_id,
                                row.raw_hash,
                                row.tool_profile_hash,
                                row.gen,
                                row.unit_key,
                                row.unit_content_hash,
                                row.raw_path,
                                heading_path,
                                row.section_id,
                                row.byte_start,
                                row.byte_end,
                                row.text_hash,
                                indexed_text,
                                row.first_seen_commit,
                                row.created_at,
                            ],
                        )?;
                        self.conn.last_insert_rowid()
                    }
                }
            };
            let association_rowid = record_chunk_config_association(
                &self.conn,
                &row.chunk_id,
                &row.chunking_config_hash,
                &row.created_at,
                association_rowid,
                association_introduction_commit,
            )?;
            Ok((sql_u64_rowid(actual_chunk_rowid)?, association_rowid))
        })
    }

    /// Transactionally remove every derived-index row owned by `raw_hash`.
    ///
    /// Embeddings are keyed by normalized text rather than raw objects, so an
    /// embedding is removed only when no surviving chunk references its text
    /// hash. `tree_entries` is intentionally untouched: immutable commit/tree
    /// history is governed by the purge tombstone/barrier rather than rewritten.
    pub fn purge_raw(
        &mut self,
        raw_hash: &str,
        orphaned_image_hashes: &BTreeSet<String>,
    ) -> Result<PurgeRawIndexReport> {
        with_savepoint(&self.conn, "kio_purge_raw", || {
            let targets = {
                let mut statement = self.conn.prepare(
                    "SELECT chunk_id, text_hash
                     FROM chunks
                     WHERE raw_hash = ?1
                     ORDER BY chunk_id",
                )?;
                let rows = statement.query_map(params![raw_hash], |row| {
                    Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
                })?;
                rows.collect::<std::result::Result<Vec<_>, _>>()?
            };

            let mut report = PurgeRawIndexReport {
                chunk_ids: targets
                    .iter()
                    .map(|(chunk_id, _)| chunk_id.clone())
                    .collect(),
                ..PurgeRawIndexReport::default()
            };
            let text_hashes = targets
                .iter()
                .map(|(_, text_hash)| text_hash.clone())
                .collect::<BTreeSet<_>>();

            for (chunk_id, _) in &targets {
                report.deleted_chunk_vectors += u64::try_from(self.conn.execute(
                    "DELETE FROM chunk_vec WHERE chunk_id = ?1",
                    params![chunk_id],
                )?)
                .map_err(|_| IndexError::Contract("deleted row count exceeds u64".to_owned()))?;
                report.deleted_associations += u64::try_from(self.conn.execute(
                    "DELETE FROM chunk_config_generations WHERE chunk_id = ?1",
                    params![chunk_id],
                )?)
                .map_err(|_| IndexError::Contract("deleted row count exceeds u64".to_owned()))?;
            }

            report.deleted_chunks = u64::try_from(
                self.conn
                    .execute("DELETE FROM chunks WHERE raw_hash = ?1", params![raw_hash])?,
            )
            .map_err(|_| IndexError::Contract("deleted row count exceeds u64".to_owned()))?;

            for text_hash in text_hashes {
                // RETURNING the ids rather than only counting them: the CAS
                // object under `objects/embeddings/<id>` is the same vector and
                // purge has to take it too, but nothing can enumerate the rows
                // once they are deleted.
                let mut orphans = self.conn.prepare(
                    "DELETE FROM embeddings
                     WHERE target_type = 'chunk'
                       AND target_id = ?1
                       AND NOT EXISTS (
                           SELECT 1 FROM chunks WHERE text_hash = ?1 LIMIT 1
                       )
                     RETURNING id",
                )?;
                let ids = orphans.query_map(params![text_hash], |row| row.get::<_, String>(0))?;
                for id in ids {
                    report.deleted_embedding_ids.push(id?);
                    report.deleted_orphan_embeddings += 1;
                }
            }

            // 05 §3.5: image vectors go the same way, on the same
            // live-reference-0 rule. Which images are orphaned is decided by
            // the CALLER, because the answer lives in the Markdown image
            // grammar (`kio://…/object/image/…`) and that parser belongs to
            // kio-search — a second copy of it here is the kind of duplicate
            // liveness rule that drifts. The caller computes
            // "referenced by the purge target, and by nothing that survives"
            // before any row is deleted, and this deletes them inside the same
            // savepoint so the two halves cannot land apart.
            for image_hash in orphaned_image_hashes {
                report.deleted_image_vectors += u64::try_from(self.conn.execute(
                    "DELETE FROM image_vec WHERE image_id = ?1",
                    params![image_hash],
                )?)
                .map_err(|_| IndexError::Contract("deleted row count exceeds u64".to_owned()))?;
                let mut orphans = self.conn.prepare(
                    "DELETE FROM embeddings
                     WHERE target_type = 'image' AND target_id = ?1
                     RETURNING id",
                )?;
                let ids = orphans.query_map(params![image_hash], |row| row.get::<_, String>(0))?;
                for id in ids {
                    report.deleted_embedding_ids.push(id?);
                    report.deleted_orphan_embeddings += 1;
                }
            }

            Ok(report)
        })
    }

    /// Schema/tokenizer contract probe: a bare `chunk_fts MATCH` over the whole
    /// table, used by the CT3-FTS unit tests to pin the external-content
    /// trigger sync and trigram behavior. The production query path is
    /// kio-cli's `execute_fts_tier`, which layers the liveness filters
    /// (tree_entries join, current chunking_config_hash, `rowid <= max_rowid`)
    /// and column-weighted BM25 on the same index.
    pub fn search(&self, query: &str, limit: u64) -> Result<Vec<FtsMatch>> {
        if query.chars().count() < 2 {
            return Ok(Vec::new());
        }
        let sql = "SELECT c.chunk_id, rank
                   FROM chunk_fts f
                   JOIN chunks c ON c.rowid = f.rowid
                   WHERE chunk_fts MATCH ?1
                   ORDER BY rank, c.chunk_id
                   LIMIT ?2";
        let mut stmt = self.conn.prepare(sql)?;
        let rows = stmt.query_map(params![query, limit], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, f64>(1)?))
        })?;
        let mut matches = Vec::new();
        for (index, row) in rows.enumerate() {
            let (chunk_id, bm25_score) = row?;
            matches.push(FtsMatch {
                chunk_id,
                rank: index as u64 + 1,
                bm25_score,
            });
        }
        Ok(matches)
    }
}

/// Append a chunk/config generation association and return its stable rowid.
///
/// The `(chunk_id, chunking_config_hash, introduction_commit)` relation is
/// idempotent. A config may be introduced for the same chunk more than once on
/// incomparable histories, and each introduction remains independently visible
/// to time-bounded search. When an explicit rowid is supplied (during
/// durable-ledger rebuild), the complete triple and rowid must agree with an
/// existing record; a collision is a contract error rather than a silent
/// renumbering that could invalidate signed cursors.
///
/// `introduction_commit` (PC40, 05 §1.6 L266) is stamped only on a genuinely
/// new association row — an already-existing triple's immutable fields never
/// change on replay.
pub fn record_chunk_config_association(
    conn: &Connection,
    chunk_id: &str,
    chunking_config_hash: &str,
    created_at: &str,
    association_rowid: Option<u64>,
    introduction_commit: &str,
) -> Result<u64> {
    if association_rowid == Some(0) {
        return Err(IndexError::Contract(
            "chunk/config association rowid must be positive".to_owned(),
        ));
    }
    if introduction_commit.is_empty() {
        return Err(IndexError::Contract(
            "chunk/config association introduction commit is required".to_owned(),
        ));
    }
    let chunk_exists = conn
        .query_row(
            "SELECT 1 FROM chunks WHERE chunk_id = ?1 LIMIT 1",
            params![chunk_id],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    if !chunk_exists {
        return Err(IndexError::Contract(format!(
            "cannot associate missing chunk {chunk_id}"
        )));
    }

    let requested_rowid = association_rowid.map(sql_rowid).transpose()?;
    let existing_for_triple = conn
        .query_row(
            "SELECT association_rowid
             FROM chunk_config_generations
             WHERE chunk_id = ?1
               AND chunking_config_hash = ?2
               AND introduction_commit = ?3",
            params![chunk_id, chunking_config_hash, introduction_commit],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;

    if let Some(existing_rowid) = existing_for_triple {
        if let Some(requested_rowid) = requested_rowid {
            if existing_rowid != requested_rowid {
                return Err(IndexError::Contract(format!(
                    "chunk/config association {chunk_id}/{chunking_config_hash}/{introduction_commit} \
                     has rowid {existing_rowid}, not requested rowid {requested_rowid}"
                )));
            }
        }
        return sql_u64_rowid(existing_rowid);
    }

    if let Some(requested_rowid) = requested_rowid {
        let occupied = conn
            .query_row(
                "SELECT chunk_id, chunking_config_hash, introduction_commit
                 FROM chunk_config_generations
                 WHERE association_rowid = ?1",
                params![requested_rowid],
                |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                    ))
                },
            )
            .optional()?;
        if let Some((occupied_chunk, occupied_config, occupied_introduction)) = occupied {
            return Err(IndexError::Contract(format!(
                "chunk/config association rowid {requested_rowid} is already occupied by \
                 {occupied_chunk}/{occupied_config}/{occupied_introduction}"
            )));
        }
        conn.execute(
            "INSERT INTO chunk_config_generations(
                association_rowid, chunk_id, chunking_config_hash, created_at, introduction_commit
             ) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                requested_rowid,
                chunk_id,
                chunking_config_hash,
                created_at,
                introduction_commit
            ],
        )?;
        return sql_u64_rowid(requested_rowid);
    }

    conn.execute(
        "INSERT INTO chunk_config_generations(
            chunk_id, chunking_config_hash, created_at, introduction_commit
         ) VALUES (?1, ?2, ?3, ?4)",
        params![
            chunk_id,
            chunking_config_hash,
            created_at,
            introduction_commit
        ],
    )?;
    sql_u64_rowid(conn.last_insert_rowid())
}

/// Maximum generation-association rowid frozen into a page-1 cursor.
/// Empty databases use zero, which cannot name an AUTOINCREMENT row.
pub fn max_chunk_config_association_rowid(conn: &Connection) -> Result<u64> {
    let maximum = conn.query_row(
        "SELECT COALESCE(MAX(association_rowid), 0) FROM chunk_config_generations",
        [],
        |row| row.get::<_, i64>(0),
    )?;
    sql_u64_rowid(maximum)
}

/// Whether a chunk had an association with the effective config at the frozen
/// association maximum.
pub fn chunk_has_current_config_association(
    conn: &Connection,
    chunk_id: &str,
    chunking_config_hash: &str,
    max_association_rowid: u64,
) -> Result<bool> {
    let max_association_rowid = sql_rowid(max_association_rowid)?;
    Ok(conn
        .query_row(
            "SELECT 1
             FROM chunk_config_generations
             WHERE chunk_id = ?1
               AND chunking_config_hash = ?2
               AND association_rowid <= ?3
             LIMIT 1",
            params![chunk_id, chunking_config_hash, max_association_rowid],
            |_| Ok(()),
        )
        .optional()?
        .is_some())
}

/// Return chunks satisfying the shared row/config cursor eligibility filter.
/// Snapshot/tree liveness is intentionally layered on by the caller because it
/// differs between default, `--at`, all-history, and include-deleted modes.
pub fn current_config_eligible_chunk_ids(
    conn: &Connection,
    chunking_config_hash: &str,
    max_chunk_rowid: u64,
    max_association_rowid: u64,
) -> Result<BTreeSet<String>> {
    let max_chunk_rowid = sql_rowid(max_chunk_rowid)?;
    let max_association_rowid = sql_rowid(max_association_rowid)?;
    let mut stmt = conn.prepare(
        "SELECT c.chunk_id
         FROM chunks c
         JOIN chunk_config_generations g ON g.chunk_id = c.chunk_id
         WHERE c.first_seen_commit IS NOT NULL
           AND c.rowid <= ?1
           AND g.chunking_config_hash = ?2
           AND g.association_rowid <= ?3
           AND EXISTS (
               SELECT 1 FROM chunk_publications p
               WHERE p.chunk_id = c.chunk_id
           )
         ORDER BY c.chunk_id",
    )?;
    let rows = stmt.query_map(
        params![max_chunk_rowid, chunking_config_hash, max_association_rowid],
        |row| row.get::<_, String>(0),
    )?;
    rows.collect::<std::result::Result<BTreeSet<_>, _>>()
        .map_err(IndexError::from)
}

/// PC37 (04 §4.1 / 05 §1.6): append one `(chunk_id, introduction_commit)` row —
/// idempotent (`INSERT OR IGNORE`, `UNIQUE(chunk_id, introduction_commit)`), so
/// re-publishing the same chunk at the same commit (a resurrection, a repeated
/// rebuild pass) never duplicates a row. Distinct commits for the same
/// `chunk_id` accumulate (the multi-introduction case — merge side branches,
/// independent imports — a single `chunks.first_seen_commit` cannot represent).
pub fn record_chunk_publication(
    conn: &Connection,
    chunk_id: &str,
    introduction_commit: &str,
) -> Result<()> {
    conn.execute(
        "INSERT OR IGNORE INTO chunk_publications(chunk_id, introduction_commit)
         VALUES (?1, ?2)",
        params![chunk_id, introduction_commit],
    )?;
    Ok(())
}

/// Every recorded introduction commit for `chunk_id`, in byte order (PC32's
/// deterministic tie-break for a "no directly-matching current value"
/// fallback selects the byte-order-minimum among these). Empty when the chunk
/// has no `chunk_publications` row yet. Such a chunk is ineligible for search;
/// callers must not fall back to the single-valued `chunks.first_seen_commit`.
pub fn chunk_publication_introductions(conn: &Connection, chunk_id: &str) -> Result<Vec<String>> {
    let mut stmt = conn.prepare(
        "SELECT introduction_commit FROM chunk_publications
         WHERE chunk_id = ?1 ORDER BY introduction_commit",
    )?;
    let rows = stmt.query_map(params![chunk_id], |row| row.get::<_, String>(0))?;
    rows.collect::<std::result::Result<Vec<_>, _>>()
        .map_err(IndexError::from)
}

pub fn ensure_schema_on_connection(conn: &Connection, config: FtsSchemaConfig) -> Result<()> {
    // A derived database is disposable, but it is not a migration target.  Do
    // this read-only fingerprint before *any* DDL: a partial or older sqlite.db
    // must be rebuilt from the durable commit/tree/CAS sources, never repaired
    // in place.  Besides making the boundary explicit, this keeps the failed
    // open byte-for-byte non-mutating for `kio repair rebuild-db` to replace.
    let has_current_objects = validate_current_schema(conn, &config)?;
    if has_current_objects {
        return Ok(());
    }
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS chunks (
            -- QB29 (step4b-contract-tests-p3b.md §C, 04 §4.1 L385-386 /
            -- 03-data-model.md §8, U98): a rowid table's `TEXT PRIMARY KEY`
            -- does NOT imply NOT NULL by itself — spelled out explicitly.
            chunk_id TEXT NOT NULL PRIMARY KEY,
            raw_hash TEXT NOT NULL,
            tool_profile_hash TEXT NOT NULL,
            gen INTEGER NOT NULL,
            unit_key TEXT NOT NULL,
            unit_content_hash TEXT NOT NULL CHECK (
                length(unit_content_hash) = 71
                AND substr(unit_content_hash, 1, 7) = 'sha256:'
                AND substr(unit_content_hash, 8) NOT GLOB '*[^0-9a-f]*'
            ),
            raw_path TEXT NOT NULL,
            heading_path TEXT NOT NULL,
            section_id TEXT,
            byte_start INTEGER NOT NULL,
            byte_end INTEGER NOT NULL,
            text_hash TEXT NOT NULL,
            text TEXT NOT NULL,
            first_seen_commit TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_ident
            ON chunks(raw_hash, tool_profile_hash, gen, unit_key, unit_content_hash);
        CREATE TABLE IF NOT EXISTS chunk_config_generations (
            association_rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL,
            chunking_config_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            introduction_commit TEXT NOT NULL,
            UNIQUE(chunk_id, chunking_config_hash, introduction_commit)
        );
        CREATE TABLE IF NOT EXISTS chunk_publications (
            publication_rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL,
            introduction_commit TEXT NOT NULL,
            UNIQUE(chunk_id, introduction_commit)
        );
        CREATE INDEX IF NOT EXISTS idx_chunk_publications_chunk_id
            ON chunk_publications(chunk_id);
        CREATE TABLE IF NOT EXISTS embeddings (
            -- QB29: see the `chunks.chunk_id` comment above — same rowid-table
            -- TEXT PRIMARY KEY nullability gap, closed explicitly.
            id TEXT NOT NULL PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            modality TEXT NOT NULL,
            vector BLOB NOT NULL,
            dimensions INTEGER NOT NULL,
            distance TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            -- 2026-07-24 (07 §5.3 contextual-embedding addendum): the humanized
            -- filename context a chunk vector was embedded with, so a rebuild
            -- can disambiguate several rows sharing one `target_id` (text_hash).
            -- NULL for non-contextual (legacy / symbolic-name) chunk embeddings.
            context_key TEXT
        );
        -- QB32 (step4b-contract-tests-p3b.md §C, 04 §4.3 L534-536): so the
        -- query_cache 256-row prune/enumerate (once wired, QB33/34) does not
        -- SCAN the full corpus-sized `embeddings` table to find its rows.
        CREATE INDEX IF NOT EXISTS idx_embeddings_type ON embeddings(target_type);
        CREATE TABLE IF NOT EXISTS tree_entries (
            commit_hash TEXT NOT NULL,
            path TEXT NOT NULL,
            raw_hash TEXT NOT NULL,
            tool_profile_hash TEXT,
            gen INTEGER,
            manifest_hash TEXT,
            PRIMARY KEY (commit_hash, path)
        );
        CREATE INDEX IF NOT EXISTS idx_tree_entries_ident
            ON tree_entries(commit_hash, raw_hash, tool_profile_hash, gen);
        CREATE TABLE IF NOT EXISTS index_metadata (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            index_generation TEXT NOT NULL,
            last_lifecycle_epoch INTEGER NOT NULL DEFAULT 0
        );
        "#,
    )?;

    let tokenizer = match config.tokenizer {
        FtsTokenizer::Trigram => "trigram",
        FtsTokenizer::Unicode61RemoveDiacritics2 => "unicode61 remove_diacritics 2",
    };
    conn.execute_batch(&format!(
        r#"
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts
        USING fts5(text, heading_path, content='chunks', content_rowid='rowid', tokenize='{tokenizer}');

        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunk_fts(rowid, text, heading_path)
            VALUES (new.rowid, new.text, new.heading_path);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
            VALUES ('delete', old.rowid, old.text, old.heading_path);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE OF text, heading_path ON chunks BEGIN
            INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
            VALUES ('delete', old.rowid, old.text, old.heading_path);
            INSERT INTO chunk_fts(rowid, text, heading_path)
            VALUES (new.rowid, new.text, new.heading_path);
        END;
        "#
    ))?;
    conn.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')", [])?;

    // `chunk_vec` is a sqlite-vec `vec0` virtual table (04 §4.3): the KNN
    // acceleration layer derived from the `embeddings` table. Fixed at the adopted
    // profile's 768 dimensions / cosine distance (07 §5.3). Since our stored and
    // query vectors are L2-normalized, cosine distance ordering is exact.
    crate::vec::ensure_registered();
    conn.execute_batch(&format!(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec USING vec0(
            chunk_id TEXT PRIMARY KEY,
            embedding float[{CHUNK_VEC_DIMENSIONS}] distance_metric=cosine
        );"
    ))?;
    // `image_vec` is `chunk_vec`'s counterpart for image objects (04 §4.3).
    // `embeddings.target_type` has admitted `'image'` since it was written, but
    // with no vec0 table to hold them there was no way to search one.
    //
    // Same width and metric on purpose: 03 §7 fixes ONE multimodal vector
    // space, so image and chunk vectors are directly comparable and the split
    // is only sqlite-vec's one-primary-key-type-per-table constraint, not a
    // semantic boundary. `image_id` is the `objects/image/` content hash.
    conn.execute_batch(&format!(
        "CREATE VIRTUAL TABLE IF NOT EXISTS image_vec USING vec0(
            image_id TEXT PRIMARY KEY,
            embedding float[{CHUNK_VEC_DIMENSIONS}] distance_metric=cosine
        );"
    ))?;
    Ok(())
}

/// Verify a pre-existing public derived-index schema without modifying it.
///
/// `Ok(false)` means this connection contains no Kio index objects and can be
/// initialized as a fresh store. `Ok(true)` means every required current object
/// matches the public fingerprint. Any partial, legacy, or incompatible Kio
/// shape returns [`IndexError::Schema`] with rebuild guidance. Callers that
/// intentionally open SQLite directly (notably repair) can use this check
/// before selecting from the database.
pub fn validate_current_schema(conn: &Connection, config: &FtsSchemaConfig) -> Result<bool> {
    const REQUIRED_OBJECTS: &[&str] = &[
        "chunks",
        "chunk_config_generations",
        "chunk_publications",
        "embeddings",
        "tree_entries",
        "index_metadata",
        "chunk_fts",
        "chunk_vec",
        "image_vec",
        "idx_chunks_ident",
        "idx_chunk_publications_chunk_id",
        "idx_embeddings_type",
        "idx_tree_entries_ident",
        "chunks_ai",
        "chunks_ad",
        "chunks_au",
    ];
    let present = REQUIRED_OBJECTS
        .iter()
        .map(|name| object_exists(conn, name))
        .collect::<Result<Vec<_>>>()?;
    if present.iter().all(|present| !present) {
        if has_non_internal_user_objects(conn)? {
            return Err(schema_rebuild_error(
                "sqlite.db contains unknown user objects rather than a fresh index",
            ));
        }
        return Ok(false);
    }
    if present.iter().any(|present| !present) {
        return Err(schema_rebuild_error(
            "missing required current index object",
        ));
    }
    validate_no_unknown_user_objects(conn, REQUIRED_OBJECTS)?;

    validate_table(
        conn,
        "chunks",
        &[
            ("chunk_id", "TEXT", true, 1),
            ("raw_hash", "TEXT", true, 0),
            ("tool_profile_hash", "TEXT", true, 0),
            ("gen", "INTEGER", true, 0),
            ("unit_key", "TEXT", true, 0),
            ("unit_content_hash", "TEXT", true, 0),
            ("raw_path", "TEXT", true, 0),
            ("heading_path", "TEXT", true, 0),
            ("section_id", "TEXT", false, 0),
            ("byte_start", "INTEGER", true, 0),
            ("byte_end", "INTEGER", true, 0),
            ("text_hash", "TEXT", true, 0),
            ("text", "TEXT", true, 0),
            ("first_seen_commit", "TEXT", false, 0),
            ("created_at", "TEXT", true, 0),
        ],
    )?;
    validate_exact_schema_sql(conn, "table", "chunks", CURRENT_CHUNKS_SQL)?;
    validate_table(
        conn,
        "chunk_config_generations",
        &[
            ("association_rowid", "INTEGER", false, 1),
            ("chunk_id", "TEXT", true, 0),
            ("chunking_config_hash", "TEXT", true, 0),
            ("created_at", "TEXT", true, 0),
            ("introduction_commit", "TEXT", true, 0),
        ],
    )?;
    validate_exact_schema_sql(
        conn,
        "table",
        "chunk_config_generations",
        CURRENT_CHUNK_CONFIG_GENERATIONS_SQL,
    )?;
    validate_table(
        conn,
        "chunk_publications",
        &[
            ("publication_rowid", "INTEGER", false, 1),
            ("chunk_id", "TEXT", true, 0),
            ("introduction_commit", "TEXT", true, 0),
        ],
    )?;
    validate_exact_schema_sql(
        conn,
        "table",
        "chunk_publications",
        CURRENT_CHUNK_PUBLICATIONS_SQL,
    )?;
    validate_table(
        conn,
        "embeddings",
        &[
            ("id", "TEXT", true, 1),
            ("target_type", "TEXT", true, 0),
            ("target_id", "TEXT", true, 0),
            ("modality", "TEXT", true, 0),
            ("vector", "BLOB", true, 0),
            ("dimensions", "INTEGER", true, 0),
            ("distance", "TEXT", true, 0),
            ("profile_hash", "TEXT", true, 0),
            ("context_key", "TEXT", false, 0),
        ],
    )?;
    validate_exact_schema_sql(conn, "table", "embeddings", CURRENT_EMBEDDINGS_SQL)?;
    validate_table(
        conn,
        "tree_entries",
        &[
            ("commit_hash", "TEXT", true, 1),
            ("path", "TEXT", true, 2),
            ("raw_hash", "TEXT", true, 0),
            ("tool_profile_hash", "TEXT", false, 0),
            ("gen", "INTEGER", false, 0),
            ("manifest_hash", "TEXT", false, 0),
        ],
    )?;
    validate_exact_schema_sql(conn, "table", "tree_entries", CURRENT_TREE_ENTRIES_SQL)?;
    let partial_tree_entry: bool = conn.query_row(
        "SELECT EXISTS(
             SELECT 1 FROM tree_entries
             WHERE NOT (
                 tool_profile_hash IS NULL AND gen IS NULL AND manifest_hash IS NULL
                 OR tool_profile_hash IS NOT NULL AND gen IS NOT NULL AND manifest_hash IS NOT NULL
             )
         )",
        [],
        |row| row.get(0),
    )?;
    if partial_tree_entry {
        return Err(schema_rebuild_error(
            "tree_entries has a partial normalize projection",
        ));
    }
    validate_table(
        conn,
        "index_metadata",
        &[
            ("id", "INTEGER", false, 1),
            ("index_generation", "TEXT", true, 0),
            ("last_lifecycle_epoch", "INTEGER", true, 0),
        ],
    )?;
    validate_exact_schema_sql(conn, "table", "index_metadata", CURRENT_INDEX_METADATA_SQL)?;
    validate_index(
        conn,
        "idx_chunks_ident",
        "chunks",
        &[
            "raw_hash",
            "tool_profile_hash",
            "gen",
            "unit_key",
            "unit_content_hash",
        ],
    )?;
    validate_exact_schema_sql(
        conn,
        "index",
        "idx_chunks_ident",
        CURRENT_IDX_CHUNKS_IDENT_SQL,
    )?;
    validate_index(
        conn,
        "idx_chunk_publications_chunk_id",
        "chunk_publications",
        &["chunk_id"],
    )?;
    validate_exact_schema_sql(
        conn,
        "index",
        "idx_chunk_publications_chunk_id",
        CURRENT_IDX_CHUNK_PUBLICATIONS_SQL,
    )?;
    validate_index(conn, "idx_embeddings_type", "embeddings", &["target_type"])?;
    validate_exact_schema_sql(
        conn,
        "index",
        "idx_embeddings_type",
        CURRENT_IDX_EMBEDDINGS_TYPE_SQL,
    )?;
    validate_index(
        conn,
        "idx_tree_entries_ident",
        "tree_entries",
        &["commit_hash", "raw_hash", "tool_profile_hash", "gen"],
    )?;
    validate_exact_schema_sql(
        conn,
        "index",
        "idx_tree_entries_ident",
        CURRENT_IDX_TREE_ENTRIES_IDENT_SQL,
    )?;
    let vector_column = format!("embedding float[{CHUNK_VEC_DIMENSIONS}] distance_metric=cosine");
    validate_virtual_table(
        conn,
        "chunk_fts",
        "fts5",
        &[
            "text",
            "heading_path",
            "content='chunks'",
            "content_rowid='rowid'",
            tokenizer_sql(config),
        ],
    )?;
    validate_exact_schema_sql(conn, "table", "chunk_fts", &current_chunk_fts_sql(config))?;
    validate_virtual_table(
        conn,
        "chunk_vec",
        "vec0",
        &["chunk_id text primary key", &vector_column],
    )?;
    validate_exact_schema_sql(
        conn,
        "table",
        "chunk_vec",
        &current_chunk_vec_sql("chunk_id"),
    )?;
    validate_virtual_table(
        conn,
        "image_vec",
        "vec0",
        &["image_id text primary key", &vector_column],
    )?;
    validate_exact_schema_sql(
        conn,
        "table",
        "image_vec",
        &current_chunk_vec_sql("image_id"),
    )?;
    validate_trigger(
        conn,
        "chunks_ai",
        &[
            "after insert on chunks",
            "insert into chunk_fts",
            "new.rowid",
            "new.text",
            "new.heading_path",
        ],
    )?;
    validate_exact_schema_sql(conn, "trigger", "chunks_ai", CURRENT_CHUNKS_AI_SQL)?;
    validate_trigger(
        conn,
        "chunks_ad",
        &[
            "after delete on chunks",
            "insert into chunk_fts",
            "'delete'",
            "old.rowid",
            "old.text",
            "old.heading_path",
        ],
    )?;
    validate_exact_schema_sql(conn, "trigger", "chunks_ad", CURRENT_CHUNKS_AD_SQL)?;
    validate_trigger(
        conn,
        "chunks_au",
        &[
            "after update of text, heading_path on chunks",
            "'delete'",
            "old.rowid",
            "new.rowid",
            "new.text",
            "new.heading_path",
        ],
    )?;
    validate_exact_schema_sql(conn, "trigger", "chunks_au", CURRENT_CHUNKS_AU_SQL)?;
    Ok(true)
}

/// `index_metadata`'s single row (04-pipeline.md §4.1 / Step4b LC42-45): the
/// search-cursor-generation ULID and the lifecycle-epoch value this row was
/// last synchronized against. `kio_core::purge` owns the counter files this
/// mirrors; this crate only stores the caller-supplied snapshot.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IndexMetadata {
    pub index_generation: String,
    pub last_lifecycle_epoch: u64,
}

/// The one `index_metadata` row, or `None` on a store that predates this
/// table (LC42) — the table only ever holds zero or one row (`id=1`), never
/// a partial one. Tolerates the table itself being absent (an
/// un-schema'd connection, or a pre-Step4b `sqlite.db`) the same way as a
/// present-but-empty table, so callers do not each need their own
/// `table_exists` probe before this call.
pub fn read_index_metadata(conn: &Connection) -> Result<Option<IndexMetadata>> {
    if !table_exists(conn, "index_metadata")? {
        return Ok(None);
    }
    Ok(conn
        .query_row(
            "SELECT index_generation, last_lifecycle_epoch FROM index_metadata WHERE id = 1",
            [],
            |row| {
                let last_lifecycle_epoch: i64 = row.get(1)?;
                Ok(IndexMetadata {
                    index_generation: row.get(0)?,
                    last_lifecycle_epoch: u64::try_from(last_lifecycle_epoch).unwrap_or(0),
                })
            },
        )
        .optional()?)
}

/// LC42: create the single `index_metadata` row only if absent — never
/// overwrites an existing row (a fresh store's first write-command visit, or
/// a pre-Step4b store's first encounter with this table). `generation` is
/// the caller-minted ULID; `last_lifecycle_epoch` must be the *current*
/// `.kio/tombstones/lifecycle-epoch` counter value at the moment of this
/// call — never the column's own `DEFAULT 0`, which LC42 explicitly warns
/// would falsely read as a permanent rollback on every subsequent LC45
/// read-side check.
pub fn ensure_index_metadata(
    conn: &Connection,
    generation: &str,
    last_lifecycle_epoch: u64,
) -> Result<()> {
    conn.execute(
        "INSERT OR IGNORE INTO index_metadata (id, index_generation, last_lifecycle_epoch)
         VALUES (1, ?1, ?2)",
        params![
            generation,
            i64::try_from(last_lifecycle_epoch).unwrap_or(i64::MAX)
        ],
    )?;
    Ok(())
}

/// LC25/LC44: unconditionally replace `index_metadata`'s row — a fresh
/// `index_generation` ULID (retiring every outstanding search cursor, LC25)
/// paired with the lifecycle-epoch value this rotation is now synchronized
/// to (LC44's post-rollback-recovery write). Callers hold `.kio/.lock` (a
/// write command) when calling this; never called from a read-only path.
pub fn rotate_index_generation(
    conn: &Connection,
    generation: &str,
    last_lifecycle_epoch: u64,
) -> Result<()> {
    conn.execute(
        "INSERT INTO index_metadata (id, index_generation, last_lifecycle_epoch)
         VALUES (1, ?1, ?2)
         ON CONFLICT (id) DO UPDATE SET
             index_generation = excluded.index_generation,
             last_lifecycle_epoch = excluded.last_lifecycle_epoch",
        params![
            generation,
            i64::try_from(last_lifecycle_epoch).unwrap_or(i64::MAX)
        ],
    )?;
    Ok(())
}

fn table_exists(conn: &Connection, table_name: &str) -> Result<bool> {
    Ok(conn
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?1 LIMIT 1",
            params![table_name],
            |_| Ok(()),
        )
        .optional()?
        .is_some())
}

fn object_exists(conn: &Connection, name: &str) -> Result<bool> {
    Ok(conn
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE name = ?1 LIMIT 1",
            params![name],
            |_| Ok(()),
        )
        .optional()?
        .is_some())
}

fn has_non_internal_user_objects(conn: &Connection) -> Result<bool> {
    Ok(conn
        .query_row(
            "SELECT 1 FROM sqlite_master
             WHERE type IN ('table', 'index', 'trigger', 'view')
               AND name NOT LIKE 'sqlite_%'
             LIMIT 1",
            [],
            |_| Ok(()),
        )
        .optional()?
        .is_some())
}

fn validate_no_unknown_user_objects(conn: &Connection, required: &[&str]) -> Result<()> {
    let mut statement = conn.prepare(
        "SELECT type, name FROM sqlite_master
         WHERE name NOT LIKE 'sqlite_%' ORDER BY name",
    )?;
    let objects = statement
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    for (object_type, name) in objects {
        if required.contains(&name.as_str()) {
            continue;
        }
        let recognized_shadow = object_type == "table" && is_current_virtual_shadow(&name);
        if !recognized_shadow {
            return Err(schema_rebuild_error(format!(
                "unknown user object {name} is present in sqlite.db"
            )));
        }
    }
    Ok(())
}

fn is_current_virtual_shadow(name: &str) -> bool {
    [
        "chunk_fts_data",
        "chunk_fts_idx",
        "chunk_fts_docsize",
        "chunk_fts_config",
    ]
    .contains(&name)
        || ["chunk_vec", "image_vec"].iter().any(|base| {
            name == format!("{base}_info")
                || name == format!("{base}_rowids")
                || name == format!("{base}_chunks")
                || name == format!("{base}_vector_chunks00")
        })
}

fn schema_rebuild_error(detail: impl std::fmt::Display) -> IndexError {
    IndexError::Schema(format!(
        "incompatible derived sqlite.db ({detail}); run `kio repair rebuild-db`"
    ))
}

// `PRAGMA table_info` cannot observe AUTOINCREMENT, CHECK, UNIQUE, trigger
// WHEN clauses, or virtual-table options. These public definitions therefore
// form the compatibility fingerprint; canonicalization below intentionally
// ignores only case, whitespace, and SQL comments.
const CURRENT_CHUNKS_SQL: &str = "CREATE TABLE chunks (chunk_id TEXT NOT NULL PRIMARY KEY, raw_hash TEXT NOT NULL, tool_profile_hash TEXT NOT NULL, gen INTEGER NOT NULL, unit_key TEXT NOT NULL, unit_content_hash TEXT NOT NULL CHECK (length(unit_content_hash) = 71 AND substr(unit_content_hash, 1, 7) = 'sha256:' AND substr(unit_content_hash, 8) NOT GLOB '*[^0-9a-f]*'), raw_path TEXT NOT NULL, heading_path TEXT NOT NULL, section_id TEXT, byte_start INTEGER NOT NULL, byte_end INTEGER NOT NULL, text_hash TEXT NOT NULL, text TEXT NOT NULL, first_seen_commit TEXT, created_at TEXT NOT NULL)";
const CURRENT_CHUNK_CONFIG_GENERATIONS_SQL: &str = "CREATE TABLE chunk_config_generations (association_rowid INTEGER PRIMARY KEY AUTOINCREMENT, chunk_id TEXT NOT NULL, chunking_config_hash TEXT NOT NULL, created_at TEXT NOT NULL, introduction_commit TEXT NOT NULL, UNIQUE(chunk_id, chunking_config_hash, introduction_commit))";
const CURRENT_CHUNK_PUBLICATIONS_SQL: &str = "CREATE TABLE chunk_publications (publication_rowid INTEGER PRIMARY KEY AUTOINCREMENT, chunk_id TEXT NOT NULL, introduction_commit TEXT NOT NULL, UNIQUE(chunk_id, introduction_commit))";
const CURRENT_EMBEDDINGS_SQL: &str = "CREATE TABLE embeddings (id TEXT NOT NULL PRIMARY KEY, target_type TEXT NOT NULL, target_id TEXT NOT NULL, modality TEXT NOT NULL, vector BLOB NOT NULL, dimensions INTEGER NOT NULL, distance TEXT NOT NULL, profile_hash TEXT NOT NULL, context_key TEXT)";
const CURRENT_TREE_ENTRIES_SQL: &str = "CREATE TABLE tree_entries (commit_hash TEXT NOT NULL, path TEXT NOT NULL, raw_hash TEXT NOT NULL, tool_profile_hash TEXT, gen INTEGER, manifest_hash TEXT, PRIMARY KEY (commit_hash, path))";
const CURRENT_INDEX_METADATA_SQL: &str = "CREATE TABLE index_metadata (id INTEGER PRIMARY KEY CHECK (id = 1), index_generation TEXT NOT NULL, last_lifecycle_epoch INTEGER NOT NULL DEFAULT 0)";
const CURRENT_IDX_CHUNKS_IDENT_SQL: &str =
    "CREATE INDEX idx_chunks_ident ON chunks(raw_hash, tool_profile_hash, gen, unit_key, unit_content_hash)";
const CURRENT_IDX_CHUNK_PUBLICATIONS_SQL: &str =
    "CREATE INDEX idx_chunk_publications_chunk_id ON chunk_publications(chunk_id)";
const CURRENT_IDX_EMBEDDINGS_TYPE_SQL: &str =
    "CREATE INDEX idx_embeddings_type ON embeddings(target_type)";
const CURRENT_IDX_TREE_ENTRIES_IDENT_SQL: &str = "CREATE INDEX idx_tree_entries_ident ON tree_entries(commit_hash, raw_hash, tool_profile_hash, gen)";
const CURRENT_CHUNKS_AI_SQL: &str = "CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN INSERT INTO chunk_fts(rowid, text, heading_path) VALUES (new.rowid, new.text, new.heading_path); END";
const CURRENT_CHUNKS_AD_SQL: &str = "CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path) VALUES ('delete', old.rowid, old.text, old.heading_path); END";
const CURRENT_CHUNKS_AU_SQL: &str = "CREATE TRIGGER chunks_au AFTER UPDATE OF text, heading_path ON chunks BEGIN INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path) VALUES ('delete', old.rowid, old.text, old.heading_path); INSERT INTO chunk_fts(rowid, text, heading_path) VALUES (new.rowid, new.text, new.heading_path); END";

fn current_chunk_fts_sql(config: &FtsSchemaConfig) -> String {
    format!(
        "CREATE VIRTUAL TABLE chunk_fts USING fts5(text, heading_path, content='chunks', content_rowid='rowid', tokenize='{}')",
        match config.tokenizer {
            FtsTokenizer::Trigram => "trigram",
            FtsTokenizer::Unicode61RemoveDiacritics2 => "unicode61 remove_diacritics 2",
        }
    )
}

fn current_chunk_vec_sql(id_column: &str) -> String {
    format!(
        "CREATE VIRTUAL TABLE {} USING vec0({id_column} TEXT PRIMARY KEY, embedding float[{CHUNK_VEC_DIMENSIONS}] distance_metric=cosine)",
        if id_column == "chunk_id" { "chunk_vec" } else { "image_vec" }
    )
}

fn validate_exact_schema_sql(
    conn: &Connection,
    object_type: &str,
    name: &str,
    expected: &str,
) -> Result<()> {
    let actual: Option<String> = conn
        .query_row(
            "SELECT sql FROM sqlite_master WHERE type = ?1 AND name = ?2",
            params![object_type, name],
            |row| row.get(0),
        )
        .optional()?;
    if actual
        .as_deref()
        .is_none_or(|actual| canonical_sql(actual) != canonical_sql(expected))
    {
        return Err(schema_rebuild_error(format!(
            "{object_type} {name} definition does not match current schema"
        )));
    }
    Ok(())
}

fn validate_table(
    conn: &Connection,
    table: &str,
    expected: &[(&str, &str, bool, i64)],
) -> Result<()> {
    let quoted = format!("'{}'", table.replace('\'', "''"));
    let mut statement = conn.prepare(&format!("PRAGMA table_info({quoted})"))?;
    let rows = statement.query_map([], |row| {
        Ok((
            row.get::<_, i64>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?.to_ascii_uppercase(),
            row.get::<_, i64>(3)? != 0,
            row.get::<_, i64>(5)?,
        ))
    })?;
    let actual = rows.collect::<std::result::Result<Vec<_>, _>>()?;
    if actual.len() != expected.len()
        || actual
            .iter()
            .zip(expected)
            .enumerate()
            .any(|(index, (actual, expected))| {
                actual.0 != index as i64
                    || actual.1 != expected.0
                    || actual.2 != expected.1
                    || actual.3 != expected.2
                    || actual.4 != expected.3
            })
    {
        return Err(schema_rebuild_error(format!(
            "{table} columns do not match current schema"
        )));
    }
    Ok(())
}

fn validate_index(conn: &Connection, index: &str, table: &str, columns: &[&str]) -> Result<()> {
    let actual_table: Option<String> = conn
        .query_row(
            "SELECT tbl_name FROM sqlite_master WHERE type = 'index' AND name = ?1",
            params![index],
            |row| row.get(0),
        )
        .optional()?;
    if actual_table.as_deref() != Some(table) {
        return Err(schema_rebuild_error(format!(
            "missing required index {index}"
        )));
    }
    let quoted = format!("'{}'", index.replace('\'', "''"));
    let mut statement = conn.prepare(&format!("PRAGMA index_info({quoted})"))?;
    let actual = statement
        .query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(2)?))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if actual.len() != columns.len()
        || actual
            .iter()
            .zip(columns)
            .enumerate()
            .any(|(position, (actual, expected))| {
                actual.0 != position as i64 || actual.1 != *expected
            })
    {
        return Err(schema_rebuild_error(format!(
            "index {index} does not match current schema"
        )));
    }
    Ok(())
}

fn validate_virtual_table(
    conn: &Connection,
    table: &str,
    module: &str,
    fragments: &[&str],
) -> Result<()> {
    let sql: Option<String> = conn
        .query_row(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?1",
            params![table],
            |row| row.get(0),
        )
        .optional()?;
    let sql = sql
        .map(|sql| canonical_sql(&sql))
        .ok_or_else(|| schema_rebuild_error(format!("missing virtual table {table}")))?;
    if !sql.contains(&canonical_sql(&format!(
        "create virtual table {table} using {module}"
    ))) || fragments
        .iter()
        .any(|fragment| !sql.contains(&canonical_sql(fragment)))
    {
        return Err(schema_rebuild_error(format!(
            "virtual table {table} does not match current schema"
        )));
    }
    Ok(())
}

fn validate_trigger(conn: &Connection, trigger: &str, fragments: &[&str]) -> Result<()> {
    let sql: Option<String> = conn
        .query_row(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?1",
            params![trigger],
            |row| row.get(0),
        )
        .optional()?;
    let sql = sql
        .map(|sql| canonical_sql(&sql))
        .ok_or_else(|| schema_rebuild_error(format!("missing required trigger {trigger}")))?;
    if fragments
        .iter()
        .any(|fragment| !sql.contains(&canonical_sql(fragment)))
    {
        return Err(schema_rebuild_error(format!(
            "trigger {trigger} does not match current schema"
        )));
    }
    Ok(())
}

fn canonical_sql(sql: &str) -> String {
    sql.lines()
        .map(|line| line.split_once("--").map_or(line, |(before, _)| before))
        .collect::<String>()
        .to_ascii_lowercase()
        .split_whitespace()
        .collect::<String>()
}

#[cfg(test)]
fn table_has_column(conn: &Connection, table_name: &str, column_name: &str) -> Result<bool> {
    let quoted = format!("'{}'", table_name.replace('\'', "''"));
    let mut statement = conn.prepare(&format!("PRAGMA table_info({quoted})"))?;
    let columns = statement.query_map([], |row| row.get::<_, String>(1))?;
    Ok(columns
        .collect::<std::result::Result<Vec<_>, _>>()?
        .iter()
        .any(|name| name == column_name))
}

fn tokenizer_sql(config: &FtsSchemaConfig) -> &'static str {
    match config.tokenizer {
        FtsTokenizer::Trigram => "tokenize='trigram'",
        FtsTokenizer::Unicode61RemoveDiacritics2 => "tokenize='unicode61 remove_diacritics 2'",
    }
}

fn with_savepoint<T>(
    conn: &Connection,
    name: &str,
    operation: impl FnOnce() -> Result<T>,
) -> Result<T> {
    conn.execute_batch(&format!("SAVEPOINT {name}"))?;
    match operation() {
        Ok(value) => {
            conn.execute_batch(&format!("RELEASE SAVEPOINT {name}"))?;
            Ok(value)
        }
        Err(error) => {
            let _ = conn.execute_batch(&format!(
                "ROLLBACK TO SAVEPOINT {name}; RELEASE SAVEPOINT {name}"
            ));
            Err(error)
        }
    }
}

fn sql_rowid(value: u64) -> Result<i64> {
    i64::try_from(value).map_err(|_| {
        IndexError::Contract(format!(
            "SQLite rowid must not exceed {} (received {value})",
            i64::MAX
        ))
    })
}

fn sql_u64_rowid(value: i64) -> Result<u64> {
    u64::try_from(value)
        .map_err(|_| IndexError::Schema(format!("SQLite returned a negative rowid: {value}")))
}

/// Adopted embedding dimensionality (07 §5.3 / 03 §7). `chunk_vec` is fixed to
/// this width; incompatible-width embeddings never reach vector search.
pub const CHUNK_VEC_DIMENSIONS: usize = 768;

#[cfg(test)]
mod tests {
    use super::*;

    fn row(chunk_id: &str, text: &str) -> ChunkRow {
        ChunkRow {
            chunk_id: chunk_id.to_owned(),
            raw_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                .to_owned(),
            tool_profile_hash:
                "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_owned(),
            gen: 0,
            unit_key: "doc:1".to_owned(),
            unit_content_hash:
                "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd".to_owned(),
            chunking_config_hash:
                "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc".to_owned(),
            raw_path: "a.md".to_owned(),
            heading_path: Some(vec!["認証仕様".to_owned()]),
            section_id: Some("認証仕様".to_owned()),
            byte_start: 0,
            byte_end: text.len() as u64,
            text_hash: "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
                .to_owned(),
            text: text.to_owned(),
            first_seen_commit: None,
            chunking_config_introduction_commit: "sha256:commit".to_owned(),
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        }
    }

    fn basis_vector_bytes(axis: usize) -> Vec<u8> {
        let mut vector = vec![0.0_f32; CHUNK_VEC_DIMENSIONS];
        vector[axis] = 1.0;
        vector.into_iter().flat_map(f32::to_le_bytes).collect()
    }

    #[test]
    fn ct3_fts_001_external_content_triggers_sync_insert_delete() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk(&row("c1", "認証仕様の更新")).unwrap();
        assert_eq!(fts.search("認証仕様", 10).unwrap()[0].chunk_id, "c1");
        fts.purge_raw(&row("c1", "認証仕様の更新").raw_hash, &BTreeSet::new())
            .unwrap();
        assert!(fts.search("認証仕様", 10).unwrap().is_empty());
    }

    /// PC37 (04 §4.1): `chunk_publications` accepts multiple distinct
    /// introduction commits per `chunk_id` (the multi-introduction case), is
    /// idempotent on a repeated `(chunk_id, introduction_commit)` pair, and
    /// reads back in byte order (PC32's deterministic tie-break input).
    #[test]
    fn pc37_chunk_publications_records_multiple_introductions_idempotently() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk(&row("c1", "merge introduction test"))
            .unwrap();
        let conn = fts.connection();
        record_chunk_publication(conn, "c1", "sha256:cccccccc").unwrap();
        record_chunk_publication(conn, "c1", "sha256:aaaaaaaa").unwrap();
        // Re-publishing the same (chunk_id, introduction_commit) pair (a
        // resurrection or a repeated rebuild pass) does not duplicate the row.
        record_chunk_publication(conn, "c1", "sha256:aaaaaaaa").unwrap();

        let introductions = chunk_publication_introductions(conn, "c1").unwrap();
        assert_eq!(
            introductions,
            vec!["sha256:aaaaaaaa".to_owned(), "sha256:cccccccc".to_owned()]
        );
        assert!(chunk_publication_introductions(conn, "c-never-published")
            .unwrap()
            .is_empty());
    }

    #[test]
    fn purge_raw_is_atomic_and_preserves_shared_content_embeddings() {
        const RAW_TARGET: &str =
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        const RAW_SURVIVOR: &str =
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        const TEXT_SHARED: &str =
            "sha256:1111111111111111111111111111111111111111111111111111111111111111";
        const TEXT_UNIQUE: &str =
            "sha256:2222222222222222222222222222222222222222222222222222222222222222";

        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let mut target_shared = row("c-target-shared", "shared searchable phrase");
        target_shared.raw_hash = RAW_TARGET.to_owned();
        target_shared.text_hash = TEXT_SHARED.to_owned();
        let mut survivor = row("c-survivor", "shared searchable phrase");
        survivor.raw_hash = RAW_SURVIVOR.to_owned();
        survivor.text_hash = TEXT_SHARED.to_owned();
        let mut target_unique = row("c-target-unique", "unique purge phrase");
        target_unique.raw_hash = RAW_TARGET.to_owned();
        target_unique.text_hash = TEXT_UNIQUE.to_owned();

        fts.index_chunk(&target_shared).unwrap();
        fts.index_chunk(&survivor).unwrap();
        fts.index_chunk(&target_unique).unwrap();
        crate::embedding_store::write_chunk_embedding(
            fts.connection(),
            "sha256:embedding-shared",
            TEXT_SHARED,
            &target_shared.chunk_id,
            &basis_vector_bytes(0),
            CHUNK_VEC_DIMENSIONS as u64,
            "cosine",
            "multimodal",
            "sha256:profile",
            None,
        )
        .unwrap();
        crate::embedding_store::write_chunk_embedding(
            fts.connection(),
            "sha256:embedding-shared",
            TEXT_SHARED,
            &survivor.chunk_id,
            &basis_vector_bytes(0),
            CHUNK_VEC_DIMENSIONS as u64,
            "cosine",
            "multimodal",
            "sha256:profile",
            None,
        )
        .unwrap();
        crate::embedding_store::write_chunk_embedding(
            fts.connection(),
            "sha256:embedding-unique",
            TEXT_UNIQUE,
            &target_unique.chunk_id,
            &basis_vector_bytes(1),
            CHUNK_VEC_DIMENSIONS as u64,
            "cosine",
            "multimodal",
            "sha256:profile",
            None,
        )
        .unwrap();

        let report = fts.purge_raw(RAW_TARGET, &BTreeSet::new()).unwrap();
        assert_eq!(
            report,
            PurgeRawIndexReport {
                chunk_ids: vec!["c-target-shared".to_owned(), "c-target-unique".to_owned()],
                deleted_chunks: 2,
                deleted_associations: 2,
                deleted_chunk_vectors: 2,
                deleted_image_vectors: 0,
                deleted_orphan_embeddings: 1,
                // The unique chunk's own embedding; the shared one survives
                // because another chunk still carries its `text_hash`.
                deleted_embedding_ids: vec!["sha256:embedding-unique".to_owned()],
            }
        );
        assert_eq!(
            fts.search("shared searchable", 10)
                .unwrap()
                .into_iter()
                .map(|hit| hit.chunk_id)
                .collect::<Vec<_>>(),
            vec!["c-survivor"]
        );
        assert!(fts.search("unique purge", 10).unwrap().is_empty());
        assert!(crate::embedding_store::read_chunk_vector(
            fts.connection(),
            &target_shared.chunk_id
        )
        .unwrap()
        .is_none());
        assert!(crate::embedding_store::read_chunk_vector(
            fts.connection(),
            &target_unique.chunk_id
        )
        .unwrap()
        .is_none());
        assert!(
            crate::embedding_store::read_chunk_vector(fts.connection(), &survivor.chunk_id)
                .unwrap()
                .is_some()
        );
        assert_eq!(
            fts.connection()
                .query_row(
                    "SELECT COUNT(*) FROM embeddings WHERE target_id = ?1",
                    params![TEXT_SHARED],
                    |row| row.get::<_, u64>(0)
                )
                .unwrap(),
            1
        );
        assert_eq!(
            fts.connection()
                .query_row(
                    "SELECT COUNT(*) FROM embeddings WHERE target_id = ?1",
                    params![TEXT_UNIQUE],
                    |row| row.get::<_, u64>(0)
                )
                .unwrap(),
            0
        );

        assert_eq!(
            fts.purge_raw(RAW_TARGET, &BTreeSet::new()).unwrap(),
            PurgeRawIndexReport::default(),
            "replay after a completed purge is idempotent"
        );
    }

    /// 05 §3.5: an image vector left behind is the purged figure still
    /// rankable by vector search. Which images are orphaned is the caller's
    /// judgement (the rule needs the Markdown image grammar); this pins that
    /// what it names is deleted, and that an image it does NOT name — one a
    /// surviving document still shows — is preserved.
    #[test]
    fn purge_raw_deletes_the_image_vectors_the_caller_named_and_no_others() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        const ORPHANED: &str =
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        const SHARED: &str =
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        let target = row("c-target", "target body");
        fts.index_chunk(&target).unwrap();
        for (index, image_hash) in [ORPHANED, SHARED].iter().enumerate() {
            crate::embedding_store::write_image_embedding(
                fts.connection(),
                &format!("sha256:embedding-image-{index}"),
                image_hash,
                &basis_vector_bytes(index),
                CHUNK_VEC_DIMENSIONS as u64,
                "cosine",
                "multimodal",
                "sha256:profile",
            )
            .unwrap();
        }

        let orphaned = BTreeSet::from([ORPHANED.to_owned()]);
        let report = fts.purge_raw(&target.raw_hash, &orphaned).unwrap();
        assert_eq!(report.deleted_image_vectors, 1);
        assert!(report
            .deleted_embedding_ids
            .contains(&"sha256:embedding-image-0".to_owned()));

        assert!(
            crate::embedding_store::read_image_vector(fts.connection(), ORPHANED)
                .unwrap()
                .is_none(),
            "an image only the purged document referenced must lose its vector"
        );
        assert!(
            crate::embedding_store::read_image_vector(fts.connection(), SHARED)
                .unwrap()
                .is_some(),
            "an image a surviving document still shows has not stopped existing"
        );
    }

    #[test]
    fn purge_raw_rolls_back_all_index_layers_when_chunk_delete_fails() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let target = row("c-target", "rollback searchable phrase");
        fts.index_chunk(&target).unwrap();
        crate::embedding_store::write_chunk_embedding(
            fts.connection(),
            "sha256:embedding-rollback",
            &target.text_hash,
            &target.chunk_id,
            &basis_vector_bytes(0),
            CHUNK_VEC_DIMENSIONS as u64,
            "cosine",
            "multimodal",
            "sha256:profile",
            None,
        )
        .unwrap();
        fts.connection()
            .execute_batch(
                "CREATE TRIGGER reject_purge BEFORE DELETE ON chunks BEGIN
                     SELECT RAISE(ABORT, 'synthetic purge failure');
                 END;",
            )
            .unwrap();

        let error = fts
            .purge_raw(&target.raw_hash, &BTreeSet::new())
            .unwrap_err();
        assert!(error.to_string().contains("synthetic purge failure"));
        assert_eq!(fts.search("rollback searchable", 10).unwrap().len(), 1);
        assert!(
            crate::embedding_store::read_chunk_vector(fts.connection(), &target.chunk_id)
                .unwrap()
                .is_some()
        );
        assert_eq!(
            fts.connection()
                .query_row("SELECT COUNT(*) FROM chunk_config_generations", [], |row| {
                    row.get::<_, u64>(0)
                })
                .unwrap(),
            1,
            "config association deletion must roll back with the chunk"
        );
    }

    #[test]
    fn ct3_fts_002_first_seen_commit_update_does_not_rewrite_fts() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk(&row("c1", "認証仕様の更新")).unwrap();
        fts.connection()
            .execute(
                "UPDATE chunks SET first_seen_commit = ?1 WHERE chunk_id = ?2",
                params!["sha256:commit", "c1"],
            )
            .unwrap();
        assert_eq!(fts.search("認証仕様", 10).unwrap()[0].chunk_id, "c1");
    }

    #[test]
    fn ct3_fts_003_trigram_matches_cjk_substrings_and_short_query_skips() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk(&row("c1", "認証仕様の更新")).unwrap();
        assert_eq!(fts.search("認証仕様", 10).unwrap().len(), 1);
        assert!(fts.search("認", 10).unwrap().is_empty());
    }

    #[test]
    fn ct3_fts_004_schema_can_be_rebuilt_from_chunks() {
        let conn = Connection::open_in_memory().unwrap();
        ensure_schema_on_connection(
            &conn,
            FtsSchemaConfig {
                tokenizer: FtsTokenizer::Trigram,
            },
        )
        .unwrap();
    }

    #[test]
    fn current_file_schema_reopens_without_mutation() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        drop(SqliteFtsIndex::open(&path, config.clone()).unwrap());
        let before = std::fs::read(&path).unwrap();
        let reopened = SqliteFtsIndex::open(&path, config).unwrap();
        assert!(validate_current_schema(
            reopened.connection(),
            &FtsSchemaConfig {
                tokenizer: FtsTokenizer::Trigram
            }
        )
        .unwrap());
        drop(reopened);
        assert_eq!(std::fs::read(&path).unwrap(), before);
    }

    #[test]
    fn existing_source_connection_opens_only_a_current_real_database() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        drop(SqliteFtsIndex::open(&path, config.clone()).unwrap());

        let conn = open_existing_source_index_connection(
            &path,
            ExistingSourceIndexOpenMode::ReadOnly,
            &config,
        )
        .expect("current source index must open read-only");
        assert!(validate_current_schema(&conn, &config).unwrap());
        drop(conn);

        let missing = directory.path().join("missing.sqlite");
        let error = open_existing_source_index_connection(
            &missing,
            ExistingSourceIndexOpenMode::ReadOnly,
            &config,
        )
        .expect_err("helper must never create a missing source index");
        assert!(error.to_string().contains("inspect source index"));
        assert!(!missing.exists());
    }

    #[cfg(unix)]
    #[test]
    fn open_refuses_a_symlink_source_index_without_touching_its_destination() {
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().unwrap();
        let target = directory.path().join("target.sqlite");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        drop(SqliteFtsIndex::open(&target, config.clone()).unwrap());
        let before = std::fs::read(&target).unwrap();
        let path = directory.path().join("sqlite.db");
        symlink(&target, &path).unwrap();

        let error = SqliteFtsIndex::open(&path, config)
            .err()
            .expect("source index symlink must be rejected");
        assert!(error.to_string().contains("not a regular file"));
        assert_eq!(std::fs::read(&target).unwrap(), before);
        assert!(std::fs::symlink_metadata(&path)
            .unwrap()
            .file_type()
            .is_symlink());
    }

    #[cfg(unix)]
    #[test]
    fn source_index_hardlinks_are_rejected_without_touching_the_other_path() {
        use std::os::unix::fs::MetadataExt;

        let directory = tempfile::tempdir().unwrap();
        let target = directory.path().join("target.sqlite");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        drop(SqliteFtsIndex::open(&target, config.clone()).unwrap());
        let before = std::fs::read(&target).unwrap();
        let path = directory.path().join("sqlite.db");
        std::fs::hard_link(&target, &path).unwrap();

        let error = SqliteFtsIndex::open(&path, config.clone())
            .err()
            .expect("hardlinked source index must be rejected");
        assert!(error.to_string().contains("exactly one hard link"));
        assert_eq!(std::fs::read(&target).unwrap(), before);

        let error = open_existing_source_index_connection(
            &path,
            ExistingSourceIndexOpenMode::ReadWrite,
            &config,
        )
        .expect_err("helper must reject a hardlinked source index");
        assert!(error.to_string().contains("exactly one hard link"));
        assert_eq!(std::fs::read(&target).unwrap(), before);
        assert_eq!(std::fs::metadata(&target).unwrap().nlink(), 2);
        assert_eq!(std::fs::metadata(&path).unwrap().nlink(), 2);
    }

    #[cfg(unix)]
    #[test]
    fn open_refuses_a_symlink_source_index_parent_without_creating_a_victim_database() {
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().unwrap();
        let victim = tempfile::tempdir().unwrap();
        let parent = directory.path().join("index");
        symlink(victim.path(), &parent).unwrap();
        let path = parent.join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };

        let error = SqliteFtsIndex::open(&path, config.clone())
            .err()
            .expect("source index parent symlink must be rejected");
        assert!(error
            .to_string()
            .contains("parent must be a real directory"));
        assert!(
            !victim.path().join("sqlite.db").exists(),
            "fresh source-index bootstrap must not create a database through a parent symlink"
        );

        let error = open_existing_source_index_connection(
            &path,
            ExistingSourceIndexOpenMode::ReadOnly,
            &config,
        )
        .expect_err("existing-source helper must reject a symlink parent too");
        assert!(error
            .to_string()
            .contains("parent must be a real directory"));
    }

    #[cfg(unix)]
    #[test]
    fn bound_source_fd_survives_parent_replacement_without_touching_victim() {
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().unwrap();
        let victim = tempfile::tempdir().unwrap();
        let index = directory.path().join("index");
        std::fs::create_dir(&index).unwrap();
        let path = index.join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        let index_connection = SqliteFtsIndex::open(&path, config).unwrap();

        let original = directory.path().join("index-original");
        std::fs::rename(&index, &original).unwrap();
        symlink(victim.path(), &index).unwrap();
        index_connection
            .connection()
            .execute("CREATE TABLE post_parent_replace (id INTEGER)", [])
            .unwrap();
        drop(index_connection);

        assert!(!victim.path().join("sqlite.db").exists());
        let original_db = original.join("sqlite.db");
        let reopened = Connection::open(&original_db).unwrap();
        assert!(table_exists(&reopened, "post_parent_replace").unwrap());
    }

    #[cfg(unix)]
    #[test]
    fn bound_source_fd_survives_repository_root_replacement_without_touching_victim() {
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().unwrap();
        let victim = tempfile::tempdir().unwrap();
        let kio = directory.path().join(".kio");
        let index = kio.join("index");
        std::fs::create_dir_all(&index).unwrap();
        let path = index.join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        let index_connection = SqliteFtsIndex::open(&path, config).unwrap();

        let original = directory.path().join(".kio-original");
        std::fs::rename(&kio, &original).unwrap();
        symlink(victim.path(), &kio).unwrap();
        index_connection
            .connection()
            .execute("CREATE TABLE post_root_replace (id INTEGER)", [])
            .unwrap();
        drop(index_connection);

        assert!(!victim.path().join("index/sqlite.db").exists());
        let reopened = Connection::open(original.join("index/sqlite.db")).unwrap();
        assert!(table_exists(&reopened, "post_root_replace").unwrap());
    }

    #[cfg(windows)]
    #[test]
    fn bound_source_leaf_blocks_rename_and_delete_until_connection_drops() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        let index = SqliteFtsIndex::open(&path, config).unwrap();
        let moved = directory.path().join("sqlite-moved.db");

        let rename_error = std::fs::rename(&path, &moved)
            .expect_err("the retained no-delete-share leaf must block rename");
        assert_eq!(rename_error.kind(), std::io::ErrorKind::PermissionDenied);
        let delete_error = std::fs::remove_file(&path)
            .expect_err("the retained no-delete-share leaf must block deletion");
        assert_eq!(delete_error.kind(), std::io::ErrorKind::PermissionDenied);

        drop(index);
        std::fs::rename(&path, &moved)
            .expect("rename must succeed after the bound SQLite connection drops");
        std::fs::remove_file(&moved)
            .expect("deletion must succeed after the bound SQLite connection drops");
    }

    #[cfg(unix)]
    #[test]
    fn existing_source_connection_refuses_a_symlink_without_touching_target() {
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().unwrap();
        let target = directory.path().join("target.sqlite");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        drop(SqliteFtsIndex::open(&target, config.clone()).unwrap());
        let before = std::fs::read(&target).unwrap();
        let path = directory.path().join("sqlite.db");
        symlink(&target, &path).unwrap();

        let error = open_existing_source_index_connection(
            &path,
            ExistingSourceIndexOpenMode::ReadWrite,
            &config,
        )
        .expect_err("source index symlink must be rejected");
        assert!(error.to_string().contains("not a regular file"));
        assert_eq!(std::fs::read(&target).unwrap(), before);
        assert!(std::fs::symlink_metadata(&path)
            .unwrap()
            .file_type()
            .is_symlink());
    }

    #[test]
    fn existing_writable_source_connection_uses_memory_journal_without_sidecars() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        drop(SqliteFtsIndex::open(&path, config.clone()).unwrap());
        let conn = open_existing_source_index_connection(
            &path,
            ExistingSourceIndexOpenMode::ReadWrite,
            &config,
        )
        .unwrap();
        assert_eq!(
            conn.query_row("PRAGMA journal_mode", [], |row| row.get::<_, String>(0))
                .unwrap()
                .to_ascii_lowercase(),
            "memory"
        );
        conn.execute(
            "INSERT INTO index_metadata (id, index_generation, last_lifecycle_epoch)
             VALUES (1, 'test-generation', 0)
             ON CONFLICT(id) DO UPDATE SET index_generation = excluded.index_generation",
            [],
        )
        .unwrap();
        drop(conn);
        for suffix in ["-journal", "-wal", "-shm"] {
            assert!(
                !std::path::PathBuf::from(format!("{}{}", path.display(), suffix)).exists(),
                "memory journal must not leave a {suffix} sidecar"
            );
        }
    }

    #[test]
    fn unknown_user_object_is_rejected_without_writing() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        let conn = Connection::open(&path).unwrap();
        conn.execute_batch("CREATE TABLE unrelated_application_state (id INTEGER PRIMARY KEY);")
            .unwrap();
        drop(conn);
        let before = std::fs::read(&path).unwrap();

        let error = SqliteFtsIndex::open(
            &path,
            FtsSchemaConfig {
                tokenizer: FtsTokenizer::Trigram,
            },
        )
        .err()
        .expect("unknown sqlite objects must not be adopted as a Kio index");
        assert!(error.to_string().contains("kio repair rebuild-db"));
        assert_eq!(std::fs::read(&path).unwrap(), before);
    }

    #[test]
    fn current_schema_with_extra_user_object_is_rejected_without_writing() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        drop(SqliteFtsIndex::open(&path, config.clone()).unwrap());
        let conn = Connection::open(&path).unwrap();
        conn.execute_batch("CREATE TABLE obsolete_cache (id INTEGER PRIMARY KEY);")
            .unwrap();
        drop(conn);
        let before = std::fs::read(&path).unwrap();

        let error = SqliteFtsIndex::open(&path, config)
            .err()
            .expect("a complete schema must not conceal legacy objects");
        assert!(
            error
                .to_string()
                .contains("unknown user object obsolete_cache"),
            "{error}"
        );
        assert_eq!(std::fs::read(&path).unwrap(), before);
    }

    #[test]
    fn missing_unique_constraint_is_rejected_without_writing() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        drop(SqliteFtsIndex::open(&path, config.clone()).unwrap());
        let conn = Connection::open(&path).unwrap();
        conn.execute_batch("PRAGMA writable_schema = ON;").unwrap();
        conn.execute(
            "UPDATE sqlite_master
             SET sql = replace(sql, 'UNIQUE(chunk_id, chunking_config_hash, introduction_commit)', 'UNIQUE(chunk_id, chunking_config_hash)')
             WHERE type = 'table' AND name = 'chunk_config_generations'",
            [],
        )
        .unwrap();
        let schema_version: i64 = conn
            .query_row("PRAGMA schema_version", [], |row| row.get(0))
            .unwrap();
        conn.pragma_update(None, "schema_version", schema_version + 1)
            .unwrap();
        conn.execute_batch("PRAGMA writable_schema = OFF;").unwrap();
        drop(conn);
        let before = std::fs::read(&path).unwrap();

        let error = SqliteFtsIndex::open(&path, config)
            .err()
            .expect("weakened table constraint must be rejected");
        assert!(error
            .to_string()
            .contains("chunk_config_generations definition"));
        assert_eq!(std::fs::read(&path).unwrap(), before);
    }

    #[test]
    fn disabled_trigger_is_rejected_without_writing() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        let config = FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        };
        drop(SqliteFtsIndex::open(&path, config.clone()).unwrap());
        let conn = Connection::open(&path).unwrap();
        conn.execute_batch("PRAGMA writable_schema = ON;").unwrap();
        conn.execute(
            "UPDATE sqlite_master
             SET sql = replace(sql, 'AFTER INSERT ON chunks', 'AFTER INSERT ON chunks WHEN 0')
             WHERE type = 'trigger' AND name = 'chunks_ai'",
            [],
        )
        .unwrap();
        conn.execute_batch("PRAGMA writable_schema = OFF;").unwrap();
        drop(conn);
        let before = std::fs::read(&path).unwrap();

        let error = SqliteFtsIndex::open(&path, config)
            .err()
            .expect("disabled trigger must be rejected");
        assert!(error.to_string().contains("chunks_ai definition"));
        assert_eq!(std::fs::read(&path).unwrap(), before);
    }

    #[test]
    fn tree_entries_distinguish_raw_only_from_normalized_entries() {
        let fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let conn = fts.connection();
        conn.execute(
            "INSERT INTO tree_entries(
                 commit_hash, path, raw_hash, tool_profile_hash, gen, manifest_hash
             ) VALUES ('c1', 'raw-only.md', 'sha256:raw', NULL, NULL, NULL)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO tree_entries(
                 commit_hash, path, raw_hash, tool_profile_hash, gen, manifest_hash
             ) VALUES ('c1', 'normalized.md', 'sha256:normalized', 'sha256:tool', 4, 'sha256:manifest')",
            [],
        )
        .unwrap();
        let rows = conn
            .prepare(
                "SELECT path, tool_profile_hash, gen, manifest_hash
                 FROM tree_entries ORDER BY path",
            )
            .unwrap()
            .query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, Option<String>>(1)?,
                    row.get::<_, Option<i64>>(2)?,
                    row.get::<_, Option<String>>(3)?,
                ))
            })
            .unwrap()
            .collect::<std::result::Result<Vec<_>, _>>()
            .unwrap();
        assert_eq!(
            rows[0],
            (
                "normalized.md".to_owned(),
                Some("sha256:tool".to_owned()),
                Some(4),
                Some("sha256:manifest".to_owned())
            )
        );
        assert_eq!(rows[1], ("raw-only.md".to_owned(), None, None, None));
        assert!(validate_current_schema(
            conn,
            &FtsSchemaConfig {
                tokenizer: FtsTokenizer::Trigram
            }
        )
        .unwrap());

        conn.execute(
            "INSERT INTO tree_entries(
                 commit_hash, path, raw_hash, tool_profile_hash, gen, manifest_hash
             ) VALUES ('c1', 'partial.md', 'sha256:partial', 'sha256:tool', 5, NULL)",
            [],
        )
        .unwrap();
        let error = validate_current_schema(
            conn,
            &FtsSchemaConfig {
                tokenizer: FtsTokenizer::Trigram,
            },
        )
        .expect_err("partial normalize projection must be rejected");
        assert!(error.to_string().contains("partial normalize projection"));
    }

    #[test]
    fn ct4_chunk_config_schema_is_an_append_only_association() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let conn = fts.connection();
        assert!(!table_has_column(conn, "chunks", "chunking_config_hash").unwrap());
        assert!(table_has_column(conn, "chunk_config_generations", "association_rowid").unwrap());
        assert_eq!(max_chunk_config_association_rowid(conn).unwrap(), 0);

        let mut first = row("c1", "認証仕様の更新");
        first.first_seen_commit = Some("sha256:commit".to_owned());
        fts.index_chunk_with_association_rowid(&first, Some(17))
            .unwrap();
        record_chunk_publication(fts.connection(), "c1", "sha256:commit").unwrap();
        // Replaying the same durable association triple is idempotent and does
        // not burn another AUTOINCREMENT value.
        fts.index_chunk_with_association_rowid(&first, Some(17))
            .unwrap();

        let mut next_generation = first.clone();
        next_generation.chunking_config_hash = "sha256:next-config".to_owned();
        fts.index_chunk(&next_generation).unwrap();

        let conn = fts.connection();
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM chunks", [], |row| row
                .get::<_, u64>(0))
                .unwrap(),
            1,
            "one immutable chunk row is shared by both configs"
        );
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM chunk_config_generations", [], |row| {
                row.get::<_, u64>(0)
            })
            .unwrap(),
            2
        );
        assert_eq!(max_chunk_config_association_rowid(conn).unwrap(), 18);
        assert!(
            chunk_has_current_config_association(conn, "c1", &first.chunking_config_hash, 17)
                .unwrap()
        );
        assert!(!chunk_has_current_config_association(
            conn,
            "c1",
            &next_generation.chunking_config_hash,
            17
        )
        .unwrap());
        assert_eq!(
            current_config_eligible_chunk_ids(conn, &next_generation.chunking_config_hash, 1, 17)
                .unwrap(),
            BTreeSet::new(),
            "a page-1 association maximum excludes a later generation"
        );
        assert_eq!(
            current_config_eligible_chunk_ids(conn, &next_generation.chunking_config_hash, 1, 18)
                .unwrap(),
            BTreeSet::from(["c1".to_owned()])
        );
    }

    #[test]
    fn ct4_explicit_association_rowid_conflicts_roll_back_the_chunk() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        fts.index_chunk_with_association_rowid(&row("c1", "first chunk"), Some(9))
            .unwrap();

        let error = fts
            .index_chunk_with_association_rowid(&row("c2", "second chunk"), Some(9))
            .unwrap_err();
        assert!(error.to_string().contains("already occupied"));
        assert_eq!(
            fts.connection()
                .query_row(
                    "SELECT COUNT(*) FROM chunks WHERE chunk_id = 'c2'",
                    [],
                    |row| row.get::<_, u64>(0)
                )
                .unwrap(),
            0,
            "chunk and association publication are atomic"
        );

        let error = fts
            .index_chunk_with_association_rowid(&row("c1", "first chunk"), Some(10))
            .unwrap_err();
        assert!(error.to_string().contains("not requested rowid"));
        assert_eq!(
            max_chunk_config_association_rowid(fts.connection()).unwrap(),
            9
        );
    }

    #[test]
    fn config_associations_preserve_incomparable_same_config_introductions() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let mut first = row("c1", "same config on two branches");
        first.chunking_config_introduction_commit = "sha256:introduction-a".to_owned();
        assert_eq!(
            fts.index_chunk_with_association_rowid(&first, Some(17))
                .unwrap(),
            17
        );

        let mut incomparable = first.clone();
        incomparable.chunking_config_introduction_commit = "sha256:introduction-b".to_owned();
        assert_eq!(
            fts.index_chunk_with_association_rowid(&incomparable, None)
                .unwrap(),
            18,
            "a distinct introduction of the same config gets its own association row"
        );
        assert_eq!(
            fts.index_chunk_with_association_rowid(&incomparable, None)
                .unwrap(),
            18,
            "an automatic replay of the exact triple does not append another row"
        );
        assert_eq!(
            fts.index_chunk_with_association_rowid(&incomparable, Some(18))
                .unwrap(),
            18,
            "replaying the exact triple remains idempotent"
        );
        let error = fts
            .index_chunk_with_association_rowid(&incomparable, Some(17))
            .unwrap_err();
        assert!(error.to_string().contains("not requested rowid"));
        assert_eq!(
            fts.connection()
                .query_row("SELECT COUNT(*) FROM chunk_config_generations", [], |row| {
                    row.get::<_, u64>(0)
                })
                .unwrap(),
            2
        );
    }

    #[test]
    fn ct4_durable_replay_preserves_chunk_and_association_rowids() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        let first = row("c1", "first chunk");
        assert_eq!(
            fts.index_chunk_with_rowids(&first, Some(41), Some(101))
                .unwrap(),
            (41, 101)
        );

        let mut second_config = first.clone();
        second_config.chunking_config_hash = "sha256:next-config".to_owned();
        assert_eq!(
            fts.index_chunk_with_rowids(&second_config, Some(41), Some(205))
                .unwrap(),
            (41, 205)
        );
        assert_eq!(
            fts.connection()
                .query_row("SELECT COUNT(*) FROM chunks", [], |row| row
                    .get::<_, u64>(0))
                .unwrap(),
            1
        );

        let error = fts
            .index_chunk_with_rowids(&row("c2", "collision"), Some(41), Some(206))
            .unwrap_err();
        assert!(error.to_string().contains("already occupied"));
        assert_eq!(
            max_chunk_config_association_rowid(fts.connection()).unwrap(),
            205
        );
    }

    #[test]
    fn ct4_legacy_chunk_config_column_is_rejected_without_writing() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("sqlite.db");
        {
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch(
                r#"
                CREATE TABLE chunks (
                    chunk_id TEXT PRIMARY KEY,
                    raw_hash TEXT NOT NULL,
                    tool_profile_hash TEXT NOT NULL,
                    gen INTEGER NOT NULL,
                    unit_key TEXT NOT NULL,
                    chunking_config_hash TEXT NOT NULL,
                    raw_path TEXT NOT NULL,
                    heading_path TEXT NOT NULL,
                    section_id TEXT,
                    byte_start INTEGER NOT NULL,
                    byte_end INTEGER NOT NULL,
                    text_hash TEXT NOT NULL,
                    text TEXT NOT NULL,
                    first_seen_commit TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE chunk_fts
                USING fts5(
                    text,
                    heading_path,
                    content='chunks',
                    content_rowid='rowid',
                    tokenize='trigram'
                );
                CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunk_fts(rowid, text, heading_path)
                    VALUES (new.rowid, new.text, new.heading_path);
                END;
                CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
                    VALUES ('delete', old.rowid, old.text, old.heading_path);
                END;
                CREATE TRIGGER chunks_au AFTER UPDATE OF text, heading_path ON chunks BEGIN
                    INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
                    VALUES ('delete', old.rowid, old.text, old.heading_path);
                    INSERT INTO chunk_fts(rowid, text, heading_path)
                    VALUES (new.rowid, new.text, new.heading_path);
                END;
                INSERT INTO chunks(
                    rowid, chunk_id, raw_hash, tool_profile_hash, gen, unit_key,
                    chunking_config_hash, raw_path, heading_path, section_id,
                    byte_start, byte_end, text_hash, text, first_seen_commit, created_at
                ) VALUES
                    (7, 'c7', 'sha256:raw7', 'sha256:profile', 0, 'doc:7',
                     'sha256:cfg7', 'seven.md', '[]', NULL, 0, 16,
                     'sha256:text7', '認証仕様の更新', 'sha256:commit7', '2026-07-01T00:00:00Z'),
                    (42, 'c42', 'sha256:raw42', 'sha256:profile', 0, 'doc:42',
                     'sha256:cfg42', 'forty-two.md', '[]', NULL, 0, 18,
                     'sha256:text42', '検索インデックス', 'sha256:commit42', '2026-07-02T00:00:00Z');
                "#,
            )
            .unwrap();
        }

        let before = std::fs::read(&path).unwrap();
        let error = SqliteFtsIndex::open(
            &path,
            FtsSchemaConfig {
                tokenizer: FtsTokenizer::Trigram,
            },
        )
        .err()
        .expect("legacy schema must be rejected");
        assert!(error.to_string().contains("kio repair rebuild-db"));
        assert_eq!(std::fs::read(&path).unwrap(), before);
    }

    #[test]
    fn q4_nul_bytes_are_stripped_from_the_fts_index() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        // A UTF-16-LE ".txt" decoded lossily keeps a NUL after every ASCII char.
        // The trigram tokenizer stops at the first NUL, so before the fix every
        // word after the leading `d` ("distinctword") was silently unsearchable
        // even though `index` reported success.
        let nul_text = "d\u{0}i\u{0}s\u{0}t\u{0}i\u{0}n\u{0}c\u{0}t\u{0}w\u{0}o\u{0}r\u{0}d\u{0}";
        fts.index_chunk(&row("c1", nul_text)).unwrap();
        let hits = fts.search("distinct", 10).unwrap();
        assert_eq!(hits.len(), 1, "NUL-suffixed word must be searchable");
        assert_eq!(hits[0].chunk_id, "c1");
    }

    #[test]
    fn f2_nfd_content_is_searchable_by_nfc_query() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        // Body carries the DECOMPOSED (NFD) form: "cafe" + U+0301 COMBINING ACUTE.
        // The index projection normalizes it to NFC, so the trigram tokenizer sees
        // the same bytes a composed query produces.
        let nfd_body = "cafe\u{301} latte menu";
        assert!(nfd_body.contains('\u{301}'), "test body must be NFD");
        fts.index_chunk(&row("c1", nfd_body)).unwrap();
        // Composed (NFC) query "café" must hit the NFD-stored content.
        let hits = fts.search("caf\u{e9}", 10).unwrap();
        assert_eq!(hits.len(), 1, "NFC query must match NFD-stored content");
        assert_eq!(hits[0].chunk_id, "c1");
    }

    fn indexed_text_of(fts: &SqliteFtsIndex, chunk_id: &str) -> String {
        fts.conn
            .query_row(
                "SELECT text FROM chunks WHERE chunk_id = ?1",
                params![chunk_id],
                |row| row.get::<_, String>(0),
            )
            .unwrap()
    }

    #[test]
    fn f3_escaped_punctuation_is_searchable_by_the_plain_query() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        // What a recovered `number` block actually looks like once 07 §5.2.1's
        // escaping has been applied to the text the service read as `期限 7/10`.
        fts.index_chunk(&row("c1", "\u{671f}\u{9650} 7\\/10"))
            .unwrap();
        let hits = fts.search("\"7/10\"", 10).unwrap();
        assert_eq!(hits.len(), 1, "the plain query must match escaped content");
        assert_eq!(hits[0].chunk_id, "c1");
        // The same column is what `snippet` is taken from, so the Agent is shown
        // `期限 7/10` rather than the backslash the storage layer needed.
        assert_eq!(indexed_text_of(&fts, "c1"), "\u{671f}\u{9650} 7/10");
        // And the escaped spelling is deliberately no longer in the index: the
        // projection holds one rendering of the text, the one a reader sees.
        assert!(
            fts.search("\"7\\/10\"", 10).unwrap().is_empty(),
            "the escaped spelling must not survive in the projection"
        );
    }

    #[test]
    fn f3_fenced_code_keeps_the_backslashes_a_reader_sees() {
        let mut fts = SqliteFtsIndex::in_memory(FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        })
        .unwrap();
        // The shape that dominates the eval corpus: a shell fence whose
        // backslashes are content, not escaping. Unescaping these would rewrite
        // the corpus the eval suite searches.
        let fenced = "```sh\nfind . -type f -exec shasum {} \\;\n```\n";
        fts.index_chunk(&row("c1", fenced)).unwrap();
        assert_eq!(indexed_text_of(&fts, "c1"), fenced);
        let hits = fts.search("\"shasum {} \\;\"", 10).unwrap();
        assert_eq!(hits.len(), 1, "code must stay searchable as written");
        assert_eq!(hits[0].chunk_id, "c1");
    }
}
