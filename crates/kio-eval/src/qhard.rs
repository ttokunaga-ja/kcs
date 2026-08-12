//! Closed-world Q_hard measurement lane.
//!
//! Q_hard is deliberately not a portable synthetic fixture.  Its source
//! documents contain the raster/vector evidence which makes the questions
//! meaningful, so absence of an explicitly attested local fixture is a
//! blocked measurement, never a zero-cost passing result.

use std::{
    collections::BTreeSet,
    env,
    ffi::OsString,
    fs, io,
    path::{Component, Path, PathBuf},
    process::Command,
    sync::atomic::AtomicU64,
};

use cap_primitives::{ambient_authority, fs as cap_fs};
use kio_core::cas::hash_bytes;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

use crate::runner::{run_bounded_command, BoundedProcessOptions};

pub const FROZEN_GOLDEN_SHA256: &str =
    "sha256:d5c30eccc664e6bd4d96e1068970e225d209d04bde34c50eab300d6245d4e163";
pub const FROZEN_SYNTHETIC_M3_1_GOLDEN_SHA256: &str =
    "sha256:b7183fa3586383883ec522256696268eab8e607c1a032020e09223158a5bf08d";
const MAX_GOLDEN_BYTES: u64 = 64 * 1024;
const MAX_ATTESTATION_BYTES: u64 = 1024 * 1024;
const MAX_BINARY_BYTES: u64 = 512 * 1024 * 1024;
const MAX_LIVE_FIXTURE_FILE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_LIVE_FIXTURE_BYTES: u64 = 128 * 1024 * 1024;
const MAX_LIVE_FIXTURE_FILES: usize = 16_384;
const MAX_SCOPES: usize = 64;
const MAX_WALK_DIRECTORIES: usize = 8_192;
/// Bound entries before sorting or retaining them.  Directory entries are
/// attacker-controlled fixture input, including entries we later reject.
const MAX_DIRECTORY_ENTRIES: usize = MAX_LIVE_FIXTURE_FILES + MAX_WALK_DIRECTORIES;
const RESULT_K: usize = 10;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug)]
struct ControlledEnvironment {
    fixed: Vec<(OsString, OsString)>,
    directories: Vec<(OsString, fs::File)>,
}

impl ControlledEnvironment {
    fn apply(&self, command: &mut Command) -> Result<(), QhardError> {
        command.env_clear().envs(self.fixed.iter().cloned());
        #[cfg(unix)]
        {
            use std::os::{fd::AsRawFd, unix::process::CommandExt};
            let retained = self
                .directories
                .iter()
                .map(|(name, handle)| {
                    handle
                        .try_clone()
                        .map(|handle| (name.clone(), handle))
                        .map_err(|e| {
                            QhardError::Input(format!(
                                "cannot retain controlled environment directory: {e}"
                            ))
                        })
                })
                .collect::<Result<Vec<_>, _>>()?;
            for (name, handle) in &retained {
                command.env(name, format!("/dev/fd/{}", handle.as_raw_fd()));
            }
            unsafe {
                command.pre_exec(move || {
                    for (_, handle) in &retained {
                        let flags = libc::fcntl(handle.as_raw_fd(), libc::F_GETFD);
                        if flags < 0
                            || libc::fcntl(
                                handle.as_raw_fd(),
                                libc::F_SETFD,
                                flags & !libc::FD_CLOEXEC,
                            ) != 0
                        {
                            return Err(io::Error::last_os_error());
                        }
                    }
                    Ok(())
                });
            }
            Ok(())
        }
        #[cfg(windows)]
        {
            let _ = command;
            Err(QhardError::Input(
                "Q_hard controlled fixture environments require descriptor-bound directories on this platform".into(),
            ))
        }
    }
}

#[derive(Debug, Clone)]
pub struct QhardOptions {
    pub golden: PathBuf,
    pub fixture_root: PathBuf,
    pub tree: String,
    pub env_name: String,
    pub attestation: Option<PathBuf>,
    pub bin: PathBuf,
    pub k: usize,
    pub online_query: bool,
}

#[derive(Debug, Error)]
pub enum QhardError {
    #[error("invalid Q_hard benchmark input: {0}")]
    Input(String),
    #[error("Q_hard benchmark process failed: {0}")]
    Process(#[from] crate::runner::BoundedProcessError),
    #[error("could not serialize Q_hard benchmark report: {0}")]
    Serialize(#[from] serde_json::Error),
}

#[derive(Debug, Serialize)]
pub struct QhardReport {
    schema_version: u64,
    benchmark: &'static str,
    measurement_class: &'static str,
    acceptance_eligible: bool,
    blocked_reason: Option<String>,
    fixture: FixtureBinding,
    binary: FileBinding,
    golden: FileBinding,
    configuration: Configuration,
    rows: Vec<Row>,
    hits: usize,
    total: usize,
    recall_at_10: f64,
    synthetic_m3_1: Option<SyntheticBinding>,
    combined_hits: Option<usize>,
    combined_total: Option<usize>,
}

impl QhardReport {
    /// Q_hard alone is an external-fixture evidence lane, not a complete
    /// M3-1 acceptance run.  The CLI may only return success for a combined,
    /// cryptographically run-bound synthetic + Q_hard result supplied by a
    /// future orchestrator API.
    #[must_use]
    pub fn acceptance_passed(&self) -> bool {
        self.acceptance_eligible
            && self.combined_total == Some(26)
            && self.combined_hits.unwrap_or(0) >= 21
    }

    pub fn combine_synthetic_m3_1(
        &mut self,
        golden_path: &Path,
        hits: usize,
        total: usize,
    ) -> Result<(), QhardError> {
        let (_, golden) = binding(golden_path, MAX_GOLDEN_BYTES, "synthetic M3-1 golden")?;
        if golden.sha256 != FROZEN_SYNTHETIC_M3_1_GOLDEN_SHA256 || total != 18 || hits > total {
            return Err(QhardError::Input(
                "synthetic M3-1 measurement differs from the frozen 18-query contract".into(),
            ));
        }
        self.acceptance_eligible = true;
        self.blocked_reason = None;
        self.combined_hits = Some(self.hits + hits);
        self.combined_total = Some(self.total + total);
        self.synthetic_m3_1 = Some(SyntheticBinding {
            golden,
            hits,
            total,
        });
        Ok(())
    }
}

#[derive(Debug, Serialize)]
struct FileBinding {
    path: String,
    sha256: String,
    bytes: usize,
}
#[derive(Debug, Serialize)]
struct FixtureBinding {
    root: String,
    tree: String,
    env_name: String,
    attestation: FileBinding,
    live_sha256: String,
    scopes: Vec<String>,
}
#[derive(Debug, Serialize)]
struct Configuration {
    k: usize,
    online_query: bool,
    forwarded_credential_names: Vec<&'static str>,
}
#[derive(Debug, Serialize)]
struct SyntheticBinding {
    golden: FileBinding,
    hits: usize,
    total: usize,
}
#[derive(Debug, Serialize)]
struct Row {
    query_id: String,
    class: String,
    hit: bool,
    expected_paths: Vec<String>,
    returned_paths: Vec<String>,
    returncode: i32,
    duration_ms: f64,
}

#[derive(Debug)]
struct Fixture {
    root: RetainedDirectory,
    tree: String,
    env_name: String,
    scope_relatives: Vec<String>,
    attestation: FileBinding,
    live_sha256: String,
}

/// An evaluator-owned, immutable-for-the-duration-of-this-process copy of the
/// attested fixture.  `kio search` still uses path APIs internally, so retained
/// source directory handles alone cannot protect its descendant `.kio` and XDG
/// accesses from a same-UID rename-and-restore race.
struct FixtureSnapshot {
    _temp: tempfile::TempDir,
    root: RetainedDirectory,
    scopes: Vec<RetainedDirectory>,
}

/// A bounded private copy of a regular-file tree, retaining the source handle
/// and its digest so callers can prove the public input did not change while a
/// path-based child process was running against the copy.
pub struct PrivateTreeSnapshot {
    _temp: tempfile::TempDir,
    path: PathBuf,
    source: RetainedDirectory,
    source_digest: String,
}

impl PrivateTreeSnapshot {
    #[must_use]
    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn verify_source_unchanged(&self) -> Result<(), QhardError> {
        if fixture_live_digest(&self.source)? != self.source_digest {
            return Err(QhardError::Input(
                "synthetic corpus changed during combined measurement".into(),
            ));
        }
        Ok(())
    }
}

#[derive(Debug)]
struct RetainedDirectory {
    public_path: PathBuf,
    handle: fs::File,
}

impl RetainedDirectory {
    fn open(path: &Path, label: &str) -> Result<Self, QhardError> {
        let listed = fs::symlink_metadata(path).map_err(|e| {
            QhardError::Input(format!("{label} is missing: {}: {e}", path.display()))
        })?;
        if listed.file_type().is_symlink() || !listed.is_dir() {
            return Err(QhardError::Input(format!(
                "{label} must be a real directory"
            )));
        }
        let canonical = fs::canonicalize(path)
            .map_err(|e| QhardError::Input(format!("cannot canonicalize {label}: {e}")))?;
        let parent = canonical
            .parent()
            .ok_or_else(|| QhardError::Input(format!("{label} has no parent")))?;
        let leaf = canonical
            .file_name()
            .ok_or_else(|| QhardError::Input(format!("{label} has no final component")))?;
        let parent_handle = cap_fs::open_ambient_dir(parent, ambient_authority())
            .map_err(|e| QhardError::Input(format!("cannot open {label} parent: {e}")))?;
        let handle = cap_fs::open_dir_nofollow(&parent_handle, Path::new(leaf)).map_err(|_| {
            QhardError::Input(format!("{label} must be a real non-reparse directory"))
        })?;
        let opened = handle
            .metadata()
            .map_err(|e| QhardError::Input(format!("cannot inspect {label}: {e}")))?;
        if !same_directory(&listed, &opened) {
            return Err(QhardError::Input(format!("{label} changed while binding")));
        }
        Ok(Self {
            public_path: canonical,
            handle,
        })
    }

    fn child(&self, name: &str, label: &str) -> Result<Self, QhardError> {
        let handle = cap_fs::open_dir_nofollow(&self.handle, Path::new(name)).map_err(|_| {
            QhardError::Input(format!("{label} must be a real non-reparse directory"))
        })?;
        Ok(Self {
            public_path: self.public_path.join(name),
            handle,
        })
    }

    #[cfg(unix)]
    fn configure_command_cwd(&self, command: &mut Command) -> Result<(), QhardError> {
        use std::os::{fd::AsRawFd, unix::process::CommandExt};
        let cwd = self
            .handle
            .try_clone()
            .map_err(|e| QhardError::Input(format!("cannot retain fixture scope cwd: {e}")))?;
        unsafe {
            command.pre_exec(move || {
                if libc::fchdir(cwd.as_raw_fd()) == 0 {
                    Ok(())
                } else {
                    Err(io::Error::last_os_error())
                }
            });
        }
        Ok(())
    }

    #[cfg(windows)]
    fn configure_command_cwd(&self, command: &mut Command) -> Result<(), QhardError> {
        command.current_dir(&self.public_path);
        Ok(())
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Attestation {
    schema_version: u64,
    fixture_id: String,
    tree: String,
    env_name: String,
    golden_sha256: String,
    fixture_content_sha256: String,
    scopes: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct GoldenRow {
    query_id: String,
    scenario: String,
    class: String,
    query: String,
    expected: Vec<Expected>,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Expected {
    path: String,
    format: String,
    unit_prefix: String,
    section_hint: String,
}

fn regular(path: &Path, maximum: u64, label: &str) -> Result<Vec<u8>, QhardError> {
    let parent = path
        .parent()
        .ok_or_else(|| QhardError::Input(format!("{label} has no parent")))?;
    let name = path
        .file_name()
        .ok_or_else(|| QhardError::Input(format!("{label} has no filename")))?;
    let parent = RetainedDirectory::open(parent, &format!("{label} parent"))?;
    regular_at(&parent.handle, Path::new(name), maximum, label)
}

fn regular_at(
    root: &fs::File,
    name: &Path,
    maximum: u64,
    label: &str,
) -> Result<Vec<u8>, QhardError> {
    let before = cap_fs::stat(root, name, cap_fs::FollowSymlinks::No)
        .map_err(|e| QhardError::Input(format!("{label} is missing: {e}")))?;
    if !before.file_type().is_file() || before.len() > maximum {
        return Err(QhardError::Input(format!(
            "{label} must be a bounded regular file"
        )));
    }
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let file = cap_fs::open(root, name, &options).map_err(|e| {
        QhardError::Input(format!("cannot open {label} without following links: {e}"))
    })?;
    let opened = cap_fs::Metadata::from_file(&file)
        .map_err(|e| QhardError::Input(format!("cannot inspect {label}: {e}")))?;
    let after = cap_fs::stat(root, name, cap_fs::FollowSymlinks::No)
        .map_err(|e| QhardError::Input(format!("cannot recheck {label}: {e}")))?;
    if !opened.file_type().is_file()
        || opened.len() > maximum
        || !same_file(&before, &opened)
        || !same_file(&opened, &after)
    {
        return Err(QhardError::Input(format!("{label} changed while opening")));
    }
    let mut bytes = Vec::with_capacity(opened.len() as usize);
    use io::Read;
    file.take(maximum + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| QhardError::Input(format!("cannot read {label}: {e}")))?;
    if bytes.len() as u64 != opened.len() {
        return Err(QhardError::Input(format!("{label} changed while reading")));
    }
    Ok(bytes)
}

fn binding(path: &Path, maximum: u64, label: &str) -> Result<(Vec<u8>, FileBinding), QhardError> {
    let bytes = regular(path, maximum, label)?;
    Ok((
        bytes.clone(),
        FileBinding {
            path: path.display().to_string(),
            sha256: hash_bytes(&bytes),
            bytes: bytes.len(),
        },
    ))
}

fn binding_at(
    root: &RetainedDirectory,
    name: &str,
    maximum: u64,
    label: &str,
) -> Result<(Vec<u8>, FileBinding), QhardError> {
    let bytes = regular_at(&root.handle, Path::new(name), maximum, label)?;
    Ok((
        bytes.clone(),
        FileBinding {
            path: root.public_path.join(name).display().to_string(),
            sha256: hash_bytes(&bytes),
            bytes: bytes.len(),
        },
    ))
}

/// Snapshot a verified executable into an evaluator-owned directory before
/// running it. `Command::new(path)` cannot retain an already-open executable
/// descriptor, so executing the public path after a check would otherwise
/// retain a path-swap race.
pub fn snapshot_binary(path: &Path) -> Result<(tempfile::TempDir, PathBuf), QhardError> {
    let (bytes, _) = binding(path, MAX_BINARY_BYTES, "kio binary")?;
    let temp = tempfile::Builder::new()
        .prefix("kio-qhard-bin-")
        .tempdir()
        .map_err(|e| QhardError::Input(format!("cannot create private binary snapshot: {e}")))?;
    let snapshot = temp.path().join("kio");
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&snapshot)
        .map_err(|e| QhardError::Input(format!("cannot create private binary snapshot: {e}")))?;
    use io::Write;
    file.write_all(&bytes)
        .and_then(|_| file.sync_all())
        .map_err(|e| QhardError::Input(format!("cannot write private binary snapshot: {e}")))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&snapshot, fs::Permissions::from_mode(0o700)).map_err(|e| {
            QhardError::Input(format!(
                "cannot mark private binary snapshot executable: {e}"
            ))
        })?;
    }
    Ok((temp, snapshot))
}

fn bound_executable(path: &Path) -> Result<(tempfile::TempDir, PathBuf, FileBinding), QhardError> {
    let (temp, snapshot) = snapshot_binary(path)?;
    let (_, binding) = binding(&snapshot, MAX_BINARY_BYTES, "private kio binary")?;
    Ok((temp, snapshot, binding))
}

fn safe_name(name: &str, label: &str) -> Result<(), QhardError> {
    let mut components = Path::new(name).components();
    if name.is_empty()
        || !matches!(components.next(), Some(Component::Normal(_)))
        || components.next().is_some()
    {
        return Err(QhardError::Input(format!(
            "{label} must be one normal path component"
        )));
    }
    Ok(())
}

fn safe_relative(value: &str) -> Result<PathBuf, QhardError> {
    let path = Path::new(value);
    if value.is_empty()
        || path.is_absolute()
        || path
            .components()
            .any(|c| !matches!(c, Component::Normal(_)))
    {
        return Err(QhardError::Input(
            "attestation scope is not a normalized relative path".into(),
        ));
    }
    Ok(path.to_path_buf())
}

fn same_file(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    #[cfg(unix)]
    {
        use cap_primitives::fs::MetadataExt;
        return left.dev() == right.dev() && left.ino() == right.ino();
    }
    #[cfg(windows)]
    {
        use cap_primitives::fs::MetadataExt;
        left.volume_serial_number() == right.volume_serial_number()
            && left.file_index() == right.file_index()
    }
    #[allow(unreachable_code)]
    false
}

fn same_directory(left: &fs::Metadata, right: &fs::Metadata) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        return left.dev() == right.dev() && left.ino() == right.ino();
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        left.volume_serial_number() == right.volume_serial_number()
            && left.file_index() == right.file_index()
    }
    #[allow(unreachable_code)]
    false
}

fn discover_scopes(tree: RetainedDirectory) -> Result<Vec<RetainedDirectory>, QhardError> {
    let mut todo = vec![tree];
    let mut found = Vec::new();
    let mut seen = 0usize;
    while let Some(directory) = todo.pop() {
        seen += 1;
        if seen > MAX_WALK_DIRECTORIES {
            return Err(QhardError::Input(
                "fixture tree exceeds directory traversal bound".into(),
            ));
        }
        let mut entries = Vec::new();
        for entry in cap_fs::read_dir(&directory.handle, Path::new("."))
            .map_err(|e| QhardError::Input(format!("cannot read fixture tree: {e}")))?
        {
            entries.push(
                entry.map_err(|e| {
                    QhardError::Input(format!("cannot enumerate fixture tree: {e}"))
                })?,
            );
            if entries.len() > MAX_DIRECTORY_ENTRIES {
                return Err(QhardError::Input(
                    "fixture directory exceeds entry-count bound".into(),
                ));
            }
        }
        entries.sort_by_key(|entry| entry.file_name());
        let mut has_kio = false;
        for entry in entries {
            let ty = entry
                .file_type()
                .map_err(|e| QhardError::Input(format!("cannot inspect fixture entry: {e}")))?;
            if ty.is_symlink() {
                continue;
            }
            if ty.is_dir() {
                if entry.file_name() == ".kio" {
                    has_kio = true;
                } else {
                    todo.push(
                        directory
                            .child(&entry.file_name().to_string_lossy(), "fixture tree entry")?,
                    );
                }
            }
        }
        if has_kio {
            found.push(directory);
            if found.len() > MAX_SCOPES {
                return Err(QhardError::Input(
                    "fixture has too many registered scopes".into(),
                ));
            }
        }
    }
    found.sort_by(|left, right| left.public_path.cmp(&right.public_path));
    if found.is_empty() {
        return Err(QhardError::Input("fixture has no registered scope".into()));
    }
    Ok(found)
}

/// Digest every regular fixture file through retained directory handles.  The
/// digest is deliberately over file names, types, and individual content
/// digests, so it catches replacement, addition, deletion, and content races
/// without retaining an unbounded fixture in memory.
fn fixture_live_digest(root: &RetainedDirectory) -> Result<String, QhardError> {
    let mut records = Vec::new();
    let mut budget = FixtureDigestBudget::default();
    fingerprint_directory(&root.handle, Path::new(""), &mut records, &mut budget)?;
    Ok(hash_bytes(records.join("\n").as_bytes()))
}

/// Stable fixture content digest excludes the root attestation file, avoiding
/// a self-referential digest when the attestation is stored in the fixture.
fn fixture_content_digest(root: &RetainedDirectory) -> Result<String, QhardError> {
    let mut records = Vec::new();
    let mut budget = FixtureDigestBudget::default();
    fingerprint_directory_excluding(
        &root.handle,
        Path::new(""),
        &mut records,
        &mut budget,
        Path::new("qhard-attestation.json"),
    )?;
    Ok(hash_bytes(records.join("\n").as_bytes()))
}

fn fingerprint_directory_excluding(
    directory: &fs::File,
    prefix: &Path,
    records: &mut Vec<String>,
    _budget: &mut FixtureDigestBudget,
    excluded: &Path,
) -> Result<(), QhardError> {
    // Reuse the normal bounded walk when no exclusion is encountered; remove
    // only the deterministic root attestation record from its canonical input.
    if prefix.as_os_str().is_empty() {
        let temp = tempfile::tempdir().map_err(|e| QhardError::Input(e.to_string()))?;
        copy_fixture_directory(
            directory,
            &temp.path().join("copy"),
            &mut FixtureDigestBudget::default(),
        )?;
        let copy = RetainedDirectory::open(&temp.path().join("copy"), "digest copy")?;
        let _ = fs::remove_file(temp.path().join(excluded));
        return fingerprint_directory(
            &copy.handle,
            Path::new(""),
            records,
            &mut FixtureDigestBudget::default(),
        );
    }
    fingerprint_directory(directory, prefix, records, _budget)
}

fn copy_fixture_directory(
    source: &fs::File,
    destination: &Path,
    budget: &mut FixtureDigestBudget,
) -> Result<(), QhardError> {
    budget.directories += 1;
    if budget.directories > MAX_WALK_DIRECTORIES {
        return Err(QhardError::Input(
            "fixture snapshot exceeds directory traversal bound".into(),
        ));
    }
    fs::create_dir(destination)
        .map_err(|e| QhardError::Input(format!("cannot create private fixture directory: {e}")))?;
    let mut seen = 0usize;
    for entry in cap_fs::read_dir(source, Path::new("."))
        .map_err(|e| QhardError::Input(format!("cannot enumerate fixture snapshot source: {e}")))?
    {
        seen += 1;
        if seen > MAX_DIRECTORY_ENTRIES {
            return Err(QhardError::Input(
                "fixture directory exceeds entry-count bound".into(),
            ));
        }
        let entry = entry.map_err(|e| {
            QhardError::Input(format!("cannot enumerate fixture snapshot source: {e}"))
        })?;
        let name = entry.file_name();
        let name = name
            .to_str()
            .ok_or_else(|| QhardError::Input("fixture contains non-UTF-8 entry".into()))?;
        let ty = entry.file_type().map_err(|e| {
            QhardError::Input(format!("cannot inspect fixture snapshot source: {e}"))
        })?;
        let output = destination.join(name);
        if ty.is_symlink() {
            return Err(QhardError::Input(format!(
                "fixture contains symlink: {name}"
            )));
        }
        if ty.is_dir() {
            let child = cap_fs::open_dir_nofollow(source, Path::new(name)).map_err(|_| {
                QhardError::Input(format!(
                    "fixture directory changed while snapshotting: {name}"
                ))
            })?;
            copy_fixture_directory(&child, &output, budget)?;
        } else if ty.is_file() {
            budget.files += 1;
            if budget.files > MAX_LIVE_FIXTURE_FILES {
                return Err(QhardError::Input(
                    "fixture snapshot exceeds file-count bound".into(),
                ));
            }
            let bytes = regular_at(
                source,
                Path::new(name),
                MAX_LIVE_FIXTURE_FILE_BYTES,
                "fixture snapshot file",
            )?;
            budget.bytes = budget
                .bytes
                .checked_add(bytes.len() as u64)
                .ok_or_else(|| {
                    QhardError::Input("fixture snapshot byte counter overflow".into())
                })?;
            if budget.bytes > MAX_LIVE_FIXTURE_BYTES {
                return Err(QhardError::Input(
                    "fixture snapshot exceeds aggregate byte bound".into(),
                ));
            }
            fs::write(&output, bytes).map_err(|e| {
                QhardError::Input(format!("cannot write private fixture snapshot: {e}"))
            })?;
        } else {
            return Err(QhardError::Input(format!(
                "fixture contains unsupported entry: {name}"
            )));
        }
    }
    Ok(())
}

fn rewrite_snapshot_registry(
    snapshot: &Path,
    source_root: &Path,
    env_name: &str,
) -> Result<(), QhardError> {
    let registry = snapshot
        .join("env")
        .join(env_name)
        .join("xdg-data/kio/scope-registry.sqlite");
    if !registry.exists() {
        return Err(QhardError::Input(
            "fixture snapshot has no scope registry".into(),
        ));
    }
    let source = source_root.to_string_lossy();
    let replacement = snapshot.to_string_lossy();
    let connection = Connection::open(&registry)
        .map_err(|e| QhardError::Input(format!("cannot open snapshot scope registry: {e}")))?;
    let changed = connection
        .execute(
            "UPDATE scopes SET kio_path = replace(kio_path, ?1, ?2), root_path = replace(root_path, ?1, ?2) WHERE kio_path LIKE (?1 || '/%') AND root_path LIKE (?1 || '/%')",
            rusqlite::params![source.as_ref(), replacement.as_ref()],
        )
        .map_err(|e| QhardError::Input(format!("cannot rewrite snapshot scope registry: {e}")))?;
    if changed == 0 {
        return Err(QhardError::Input(
            "snapshot scope registry has no fixture-bound scope paths".into(),
        ));
    }
    Ok(())
}

fn snapshot_fixture(fixture: &Fixture) -> Result<FixtureSnapshot, QhardError> {
    let temp = tempfile::Builder::new()
        .prefix("kio-qhard-fixture-")
        .tempdir()
        .map_err(|e| QhardError::Input(format!("cannot create private fixture snapshot: {e}")))?;
    let root_path = temp.path().join("fixture");
    copy_fixture_directory(
        &fixture.root.handle,
        &root_path,
        &mut FixtureDigestBudget::default(),
    )?;
    let copied_root = RetainedDirectory::open(&root_path, "private fixture snapshot")?;
    if fixture_live_digest(&copied_root)? != fixture.live_sha256 {
        return Err(QhardError::Input(
            "fixture changed while creating private snapshot".into(),
        ));
    }
    rewrite_snapshot_registry(&root_path, &fixture.root.public_path, &fixture.env_name)?;
    let root = copied_root;
    let scopes = fixture
        .scope_relatives
        .iter()
        .map(|relative| RetainedDirectory::open(&root_path.join(relative), "private fixture scope"))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(FixtureSnapshot {
        _temp: temp,
        root,
        scopes,
    })
}

/// Snapshot a synthetic corpus before running its normal evaluator. This is
/// intentionally shared with Q_hard rather than trusting `BoundCorpus` alone:
/// Kio's child search resolves descendant `.kio` and XDG paths by name.
pub fn snapshot_regular_tree(source: &Path) -> Result<PrivateTreeSnapshot, QhardError> {
    let source = RetainedDirectory::open(source, "synthetic corpus")?;
    let source_digest = fixture_live_digest(&source)?;
    let temp = tempfile::Builder::new()
        .prefix("kio-eval-synthetic-")
        .tempdir()
        .map_err(|e| QhardError::Input(format!("cannot create private synthetic snapshot: {e}")))?;
    let path = temp.path().join("corpus");
    copy_fixture_directory(&source.handle, &path, &mut FixtureDigestBudget::default())?;
    let copied = RetainedDirectory::open(&path, "private synthetic snapshot")?;
    if fixture_live_digest(&copied)? != source_digest {
        return Err(QhardError::Input(
            "synthetic corpus changed while creating private snapshot".into(),
        ));
    }
    Ok(PrivateTreeSnapshot {
        _temp: temp,
        path,
        source,
        source_digest,
    })
}

#[derive(Default)]
struct FixtureDigestBudget {
    directories: usize,
    files: usize,
    bytes: u64,
}

fn fingerprint_directory(
    directory: &fs::File,
    prefix: &Path,
    records: &mut Vec<String>,
    budget: &mut FixtureDigestBudget,
) -> Result<(), QhardError> {
    budget.directories += 1;
    if budget.directories > MAX_WALK_DIRECTORIES {
        return Err(QhardError::Input(
            "fixture attestation exceeds directory traversal bound".into(),
        ));
    }
    let mut entries = Vec::new();
    for entry in cap_fs::read_dir(directory, Path::new("."))
        .map_err(|e| QhardError::Input(format!("cannot enumerate live fixture: {e}")))?
    {
        entries.push(
            entry.map_err(|e| QhardError::Input(format!("cannot enumerate live fixture: {e}")))?,
        );
        if entries.len() > MAX_DIRECTORY_ENTRIES {
            return Err(QhardError::Input(
                "fixture directory exceeds entry-count bound".into(),
            ));
        }
    }
    entries.sort_by_key(|entry| entry.file_name());
    for entry in entries {
        let name = entry.file_name();
        let name = name
            .to_str()
            .ok_or_else(|| QhardError::Input("fixture contains non-UTF-8 entry".into()))?;
        let relative = prefix.join(name);
        let ty = entry
            .file_type()
            .map_err(|e| QhardError::Input(format!("cannot inspect live fixture: {e}")))?;
        if ty.is_symlink() {
            return Err(QhardError::Input(format!(
                "fixture contains symlink: {}",
                relative.display()
            )));
        }
        if ty.is_dir() {
            records.push(format!("D:{}", relative.display()));
            let child = cap_fs::open_dir_nofollow(directory, Path::new(name)).map_err(|_| {
                QhardError::Input(format!(
                    "fixture directory changed while opening: {}",
                    relative.display()
                ))
            })?;
            fingerprint_directory(&child, &relative, records, budget)?;
        } else if ty.is_file() {
            budget.files += 1;
            if budget.files > MAX_LIVE_FIXTURE_FILES {
                return Err(QhardError::Input(
                    "fixture attestation exceeds file-count bound".into(),
                ));
            }
            let listed = cap_fs::stat(directory, Path::new(name), cap_fs::FollowSymlinks::No)
                .map_err(|e| QhardError::Input(format!("cannot inspect live fixture file: {e}")))?;
            let remaining = MAX_LIVE_FIXTURE_BYTES.saturating_sub(budget.bytes);
            if listed.len() > MAX_LIVE_FIXTURE_FILE_BYTES || listed.len() > remaining {
                return Err(QhardError::Input(
                    "fixture attestation exceeds aggregate byte bound".into(),
                ));
            }
            let bytes = regular_at(
                directory,
                Path::new(name),
                MAX_LIVE_FIXTURE_FILE_BYTES,
                "live fixture file",
            )?;
            budget.bytes = budget
                .bytes
                .checked_add(bytes.len() as u64)
                .ok_or_else(|| {
                    QhardError::Input("fixture attestation byte counter overflow".into())
                })?;
            if budget.bytes > MAX_LIVE_FIXTURE_BYTES {
                return Err(QhardError::Input(
                    "fixture attestation exceeds aggregate byte bound".into(),
                ));
            }
            records.push(format!("F:{}:{}", relative.display(), hash_bytes(&bytes)));
        } else {
            return Err(QhardError::Input(format!(
                "fixture contains unsupported entry: {}",
                relative.display()
            )));
        }
    }
    Ok(())
}

fn load_golden(path: &Path) -> Result<(Vec<GoldenRow>, FileBinding), QhardError> {
    let (bytes, binding) = binding(path, MAX_GOLDEN_BYTES, "Q_hard golden")?;
    if binding.sha256 != FROZEN_GOLDEN_SHA256 {
        return Err(QhardError::Input(
            "Q_hard golden digest does not match the frozen 8-query contract".into(),
        ));
    }
    let text = std::str::from_utf8(&bytes)
        .map_err(|_| QhardError::Input("Q_hard golden is not UTF-8".into()))?;
    let rows = text
        .lines()
        .map(|line| {
            serde_json::from_str::<GoldenRow>(line)
                .map_err(|e| QhardError::Input(format!("invalid Q_hard golden row: {e}")))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let ids = [
        "qa01", "qa02", "qa03", "qa04", "qa05", "qa06", "qa07", "qa08",
    ];
    let classes = [
        "hard1", "hard1", "hard1", "hard1", "hard3", "hard3", "hard3", "hard3",
    ];
    if rows.len() != ids.len() {
        return Err(QhardError::Input(
            "Q_hard golden must contain exactly 8 rows".into(),
        ));
    }
    for (index, row) in rows.iter().enumerate() {
        if row.query_id != ids[index]
            || row.class != classes[index]
            || row.scenario != "M3-1"
            || row.query.is_empty()
            || row.expected.len() != 1
        {
            return Err(QhardError::Input(
                "Q_hard golden IDs/order/classes/scenarios differ from frozen contract".into(),
            ));
        }
        let expected = &row.expected[0];
        if expected.path.is_empty()
            || !matches!(
                expected.format.as_str(),
                "pdf_rasterized" | "pptx" | "png" | "jpeg"
            )
            || !matches!(expected.unit_prefix.as_str(), "page" | "slide" | "image")
            || expected.section_hint.is_empty()
        {
            return Err(QhardError::Input(
                "Q_hard expected record differs from frozen shape".into(),
            ));
        }
    }
    Ok((rows, binding))
}

fn load_fixture(options: &QhardOptions) -> Result<Fixture, QhardError> {
    safe_name(&options.tree, "--tree")?;
    safe_name(&options.env_name, "--env-name")?;
    let root = RetainedDirectory::open(&options.fixture_root, "--fixture-root")?;
    let tree = root.child(&options.tree, "fixture tree")?;
    let env_root = root.child("env", "fixture env directory")?;
    let _device = env_root.child(&options.env_name, "fixture environment")?;
    let (bytes, attestation_binding) = match &options.attestation {
        Some(path) => binding(path, MAX_ATTESTATION_BYTES, "Q_hard attestation")?,
        None => binding_at(
            &root,
            "qhard-attestation.json",
            MAX_ATTESTATION_BYTES,
            "Q_hard attestation",
        )?,
    };
    let attestation: Attestation = serde_json::from_slice(&bytes)
        .map_err(|e| QhardError::Input(format!("invalid Q_hard attestation: {e}")))?;
    if attestation.schema_version != 1
        || attestation.fixture_id != "kio-qhard-v1"
        || attestation.tree != options.tree
        || attestation.env_name != options.env_name
        || attestation.golden_sha256 != FROZEN_GOLDEN_SHA256
        || attestation.scopes.is_empty()
        || attestation.scopes.len() > MAX_SCOPES
    {
        return Err(QhardError::Input(
            "Q_hard attestation does not bind this frozen fixture".into(),
        ));
    }
    let mut expected = BTreeSet::new();
    for relative in &attestation.scopes {
        expected.insert(safe_relative(relative)?);
    }
    if expected.len() != attestation.scopes.len() {
        return Err(QhardError::Input(
            "Q_hard attestation has duplicate scopes".into(),
        ));
    }
    let scopes = discover_scopes(tree)?;
    let actual = scopes
        .iter()
        .map(|scope| {
            scope
                .public_path
                .strip_prefix(&root.public_path)
                .map(Path::to_path_buf)
                .map_err(|_| QhardError::Input("fixture scope escaped root".into()))
        })
        .collect::<Result<BTreeSet<_>, _>>()?;
    if actual != expected {
        return Err(QhardError::Input(
            "registered fixture scopes differ from attestation".into(),
        ));
    }
    let relatives = actual
        .iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect();
    let live_sha256 = fixture_live_digest(&root)?;
    if attestation.fixture_content_sha256 != fixture_content_digest(&root)? {
        return Err(QhardError::Input(
            "Q_hard attestation fixture_content_sha256 does not match fixture content".into(),
        ));
    }
    Ok(Fixture {
        root,
        tree: options.tree.clone(),
        env_name: options.env_name.clone(),
        scope_relatives: relatives,
        attestation: attestation_binding,
        live_sha256,
    })
}

fn qhard_env(
    root: &RetainedDirectory,
    env_name: &str,
    online: bool,
) -> Result<(ControlledEnvironment, Vec<&'static str>), QhardError> {
    let env_root = root.child("env", "fixture env directory")?;
    let base = env_root.child(env_name, "fixture environment")?;
    let mut fixed = vec![
        (
            OsString::from("PATH"),
            env::var_os("PATH").unwrap_or_else(|| OsString::from("/usr/bin:/bin")),
        ),
        (OsString::from("LANG"), OsString::from("C.UTF-8")),
        (OsString::from("LC_ALL"), OsString::from("C.UTF-8")),
        (OsString::from("TZ"), OsString::from("UTC")),
    ];
    let mut directories = Vec::new();
    for (key, directory) in [
        ("XDG_CONFIG_HOME", "xdg-config"),
        ("XDG_DATA_HOME", "xdg-data"),
        ("XDG_CACHE_HOME", "xdg-cache"),
    ] {
        let path = base.child(directory, "fixture XDG directory")?;
        directories.push((OsString::from(key), path.handle));
    }
    let home = base.child("home", "fixture home directory")?;
    directories.push((OsString::from("HOME"), home.handle));
    let mut forwarded = Vec::new();
    if online {
        for name in ["GEMINI_API_KEY", "MISTRAL_API_KEY"] {
            if let Some(value) = env::var_os(name) {
                fixed.push((OsString::from(name), value));
                forwarded.push(name);
            }
        }
    }
    Ok((ControlledEnvironment { fixed, directories }, forwarded))
}

fn result_paths(stdout: &str, k: usize) -> Result<Vec<String>, QhardError> {
    let value: Value = serde_json::from_str(stdout.trim())
        .map_err(|e| QhardError::Input(format!("Q_hard search emitted invalid JSON: {e}")))?;
    let results = value
        .as_object()
        .and_then(|o| o.get("results"))
        .and_then(Value::as_array)
        .ok_or_else(|| QhardError::Input("Q_hard search response has no results array".into()))?;
    if results.len() > k {
        return Err(QhardError::Input(
            "Q_hard search returned more than requested k".into(),
        ));
    }
    results
        .iter()
        .enumerate()
        .map(|(i, result)| {
            result
                .as_object()
                .and_then(|o| o.get("evidence_pointer"))
                .and_then(Value::as_object)
                .and_then(|pointer| {
                    Some((
                        pointer.get("scope_id")?.as_str()?,
                        pointer.get("path_at_commit")?.as_str()?,
                    ))
                })
                .filter(|(scope, path)| !scope.is_empty() && !path.is_empty())
                .map(|(scope, path)| format!("{scope}:{path}"))
                .ok_or_else(|| QhardError::Input(format!("Q_hard result[{i}] has no pointer path")))
        })
        .collect()
}

fn expected_pointer_keys(
    expected: &[Expected],
    fixture: &Fixture,
    snapshot: &FixtureSnapshot,
) -> Result<Vec<String>, QhardError> {
    expected
        .iter()
        .map(|value| {
            // Golden paths name their fixture pack (for example `qhard-a`),
            // while the registered tree name is configurable (`qhard` by
            // default). Match the remaining scope suffix structurally rather
            // than treating those independent roots as interchangeable.
            let mut expected_components = Path::new(&value.path).components();
            if !matches!(expected_components.next(), Some(Component::Normal(_))) {
                return Err(QhardError::Input(
                    "Q_hard expected path has no fixture-pack component".into(),
                ));
            }
            let relative = expected_components.as_path().to_string_lossy().into_owned();
            let candidates = fixture
                .scope_relatives
                .iter()
                .enumerate()
                .filter_map(|(i, scope)| {
                    let scope = scope.strip_prefix(&format!("{}/", fixture.tree))?;
                    relative
                        .strip_prefix(&format!("{scope}/"))
                        .map(|path| (i, (scope, path)))
                })
                .collect::<Vec<_>>();
            if candidates.len() != 1 {
                return Err(QhardError::Input(
                    "Q_hard expected path must resolve to exactly one attested scope file".into(),
                ));
            }
            let (index, scope) = candidates.into_iter().next().expect("checked exactly one");
            let kio = snapshot.scopes[index].child(".kio", "private fixture .kio")?;
            let bytes = regular_at(
                &kio.handle,
                Path::new("scope.json"),
                MAX_GOLDEN_BYTES,
                "private fixture scope identity",
            )?;
            let scope_id = serde_json::from_slice::<Value>(&bytes)
                .ok()
                .and_then(|v| {
                    v.get("scope_id")
                        .and_then(Value::as_str)
                        .map(ToOwned::to_owned)
                })
                .filter(|id| !id.is_empty())
                .ok_or_else(|| {
                    QhardError::Input("private fixture scope.json has no scope_id".into())
                })?;
            Ok(format!("{scope_id}:{}", scope.1))
        })
        .collect()
}

pub fn run(options: QhardOptions) -> Result<QhardReport, QhardError> {
    if options.k != RESULT_K {
        return Err(QhardError::Input("Q_hard only permits --k 10".into()));
    }
    let (golden, golden_binding) = load_golden(&options.golden)?;
    let fixture = load_fixture(&options)?;
    let bin = options.bin.clone();
    let metadata = fs::symlink_metadata(&bin)
        .map_err(|e| QhardError::Input(format!("cannot inspect --bin: {e}")))?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_file() {
        return Err(QhardError::Input(
            "--bin must be a regular executable file".into(),
        ));
    }
    let (_binary_snapshot_dir, bound_bin, binary) = bound_executable(&bin)?;
    let snapshot = snapshot_fixture(&fixture)?;
    let (environment, forwarded) =
        qhard_env(&snapshot.root, &fixture.env_name, options.online_query)?;
    let cwd = snapshot.scopes.first().expect("validated nonempty scopes");
    let mut rows = Vec::with_capacity(golden.len());
    for query in &golden {
        let mut command = Command::new(&bound_bin);
        command.args([
            "--json",
            "search",
            &query.query,
            "--all-scopes",
            "--limit",
            "10",
        ]);
        environment.apply(&mut command)?;
        cwd.configure_command_cwd(&mut command)?;
        let output = run_bounded_command(&mut command, BoundedProcessOptions::default())?;
        let titles = if output.status.success() {
            result_paths(&output.stdout, options.k)?
        } else {
            Vec::new()
        };
        let expected_paths = expected_pointer_keys(&query.expected, &fixture, &snapshot)?;
        let hit = titles
            .iter()
            .any(|returned| expected_paths.iter().any(|expected| expected == returned));
        rows.push(Row {
            query_id: query.query_id.clone(),
            class: query.class.clone(),
            hit,
            expected_paths,
            returned_paths: titles,
            returncode: output.status.code().unwrap_or(-1),
            duration_ms: output.duration.as_secs_f64() * 1_000.0,
        });
    }
    let (_, attestation_after) = match &options.attestation {
        Some(path) => binding(path, MAX_ATTESTATION_BYTES, "Q_hard attestation")?,
        None => binding_at(
            &fixture.root,
            "qhard-attestation.json",
            MAX_ATTESTATION_BYTES,
            "Q_hard attestation",
        )?,
    };
    let (_, golden_after) = binding(&options.golden, MAX_GOLDEN_BYTES, "Q_hard golden")?;
    let (_, binary_after) = binding(&bin, MAX_BINARY_BYTES, "kio binary")?;
    let live_after = fixture_live_digest(&fixture.root)?;
    if attestation_after.sha256 != fixture.attestation.sha256
        || golden_after.sha256 != golden_binding.sha256
        || binary_after.sha256 != binary.sha256
        || live_after != fixture.live_sha256
    {
        return Err(QhardError::Input(
            "Q_hard input artifact changed during measurement".into(),
        ));
    }
    let hits = rows.iter().filter(|row| row.hit).count();
    Ok(QhardReport {
        schema_version: 1,
        benchmark: "kio-qhard-search",
        measurement_class: "attested_external_fixture",
        acceptance_eligible: false,
        blocked_reason: Some("Q_hard-only lane cannot claim combined M3-1 acceptance".into()),
        fixture: FixtureBinding {
            root: fixture.root.public_path.display().to_string(),
            tree: fixture.tree,
            env_name: fixture.env_name,
            attestation: fixture.attestation,
            live_sha256: fixture.live_sha256,
            scopes: fixture.scope_relatives,
        },
        binary,
        golden: golden_binding,
        configuration: Configuration {
            k: options.k,
            online_query: options.online_query,
            forwarded_credential_names: forwarded,
        },
        rows,
        hits,
        total: golden.len(),
        recall_at_10: hits as f64 / golden.len() as f64,
        synthetic_m3_1: None,
        combined_hits: None,
        combined_total: None,
    })
}

/// Serialize a report without allowing a fixture-owned path to become an
/// evaluator output sink. Reports are evidence *about* the fixture, never
/// part of it; writing inside it would make a later attestation ambiguous.
pub fn write_report(
    path: &Path,
    fixture_root: &Path,
    report: &QhardReport,
) -> Result<(), QhardError> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|e| QhardError::Input(format!("cannot resolve report path: {e}")))?
            .join(path)
    };
    let root = RetainedDirectory::open(fixture_root, "fixture root")?.public_path;
    if absolute.starts_with(&root) {
        return Err(QhardError::Input(
            "Q_hard report must be outside fixture root".into(),
        ));
    }
    let parent_path = absolute
        .parent()
        .ok_or_else(|| QhardError::Input("Q_hard report has no parent directory".into()))?;
    let name = absolute
        .file_name()
        .ok_or_else(|| QhardError::Input("Q_hard report has no filename".into()))?;
    let parent = RetainedDirectory::open(parent_path, "Q_hard report parent")?;
    if parent.public_path.starts_with(&root) {
        return Err(QhardError::Input(
            "Q_hard report must be outside fixture root".into(),
        ));
    }
    let bytes = serde_json::to_vec_pretty(report)?;
    publish_report(&parent.handle, Path::new(name), &bytes)?;
    Ok(())
}

fn publish_report(parent: &fs::File, name: &Path, bytes: &[u8]) -> Result<(), QhardError> {
    match cap_fs::stat(parent, name, cap_fs::FollowSymlinks::No) {
        Ok(metadata) if !metadata.file_type().is_file() || metadata.file_type().is_symlink() => {
            return Err(QhardError::Input(
                "Q_hard report target must be a regular non-symlink file".into(),
            ));
        }
        Ok(_) | Err(_) => {}
    }
    let mut created = None;
    let mut file = None;
    for _ in 0..16 {
        let temp = format!(
            ".kio-qhard-{}-{}",
            std::process::id(),
            TEMP_SEQUENCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        );
        let mut options = cap_fs::OpenOptions::new();
        options.write(true).create_new(true);
        match cap_fs::open(parent, Path::new(&temp), &options) {
            Ok(opened) => {
                created = Some(temp);
                file = Some(opened);
                break;
            }
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => {}
            Err(e) => {
                return Err(QhardError::Input(format!(
                    "cannot create Q_hard report: {e}"
                )))
            }
        }
    }
    let temp = created
        .ok_or_else(|| QhardError::Input("cannot reserve Q_hard report temporary file".into()))?;
    let mut file = file.expect("reserved Q_hard temporary has a handle");
    use io::Write;
    if let Err(e) = file.write_all(bytes).and_then(|_| file.sync_all()) {
        let _ = cap_fs::remove_file(parent, Path::new(&temp));
        return Err(QhardError::Input(format!(
            "cannot write Q_hard report: {e}"
        )));
    }
    if let Err(e) = cap_fs::rename(parent, Path::new(&temp), parent, name) {
        let _ = cap_fs::remove_file(parent, Path::new(&temp));
        return Err(QhardError::Input(format!(
            "cannot atomically install Q_hard report: {e}"
        )));
    }
    #[cfg(unix)]
    parent
        .sync_all()
        .map_err(|e| QhardError::Input(format!("cannot sync Q_hard report directory: {e}")))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    #[test]
    fn strict_golden_digest_rejects_non_frozen_input() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("golden.jsonl");
        fs::write(&path, b"{}\n").unwrap();
        assert!(load_golden(&path).is_err());
    }
    #[test]
    fn scope_discovery_skips_symlink_and_is_bounded() {
        let dir = tempfile::tempdir().unwrap();
        fs::create_dir_all(dir.path().join("a/.kio")).unwrap();
        let outside = tempfile::tempdir().unwrap();
        symlink(outside.path(), dir.path().join("escape")).unwrap();
        assert_eq!(
            discover_scopes(RetainedDirectory::open(dir.path(), "test tree").unwrap())
                .unwrap()
                .into_iter()
                .map(|scope| scope.public_path)
                .collect::<Vec<_>>(),
            vec![fs::canonicalize(dir.path().join("a")).unwrap()]
        );
    }
    #[test]
    fn live_fixture_digest_detects_content_mutation() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("evidence.txt"), b"before").unwrap();
        let bound = RetainedDirectory::open(dir.path(), "fixture").unwrap();
        let before = fixture_live_digest(&bound).unwrap();
        fs::write(dir.path().join("evidence.txt"), b"after").unwrap();
        assert_ne!(before, fixture_live_digest(&bound).unwrap());
    }
    #[test]
    fn live_fixture_digest_rejects_aggregate_byte_overflow_before_reading() {
        let dir = tempfile::tempdir().unwrap();
        let file = fs::File::create(dir.path().join("oversized.bin")).unwrap();
        file.set_len(MAX_LIVE_FIXTURE_FILE_BYTES + 1).unwrap();
        let bound = RetainedDirectory::open(dir.path(), "fixture").unwrap();
        assert!(fixture_live_digest(&bound).is_err());
    }
    #[test]
    fn snapshot_registry_paths_are_private() {
        let source = tempfile::tempdir().unwrap();
        let snapshot = tempfile::tempdir().unwrap();
        let registry = snapshot
            .path()
            .join("env/qhard/xdg-data/kio/scope-registry.sqlite");
        fs::create_dir_all(registry.parent().unwrap()).unwrap();
        let connection = Connection::open(&registry).unwrap();
        connection
            .execute_batch("CREATE TABLE scopes (kio_path TEXT, root_path TEXT);")
            .unwrap();
        connection
            .execute(
                "INSERT INTO scopes VALUES (?1, ?2)",
                rusqlite::params![
                    source.path().join("qhard/a/.kio").to_string_lossy(),
                    source.path().join("qhard/a").to_string_lossy()
                ],
            )
            .unwrap();
        drop(connection);
        rewrite_snapshot_registry(snapshot.path(), source.path(), "qhard").unwrap();
        let connection = Connection::open(registry).unwrap();
        let path: String = connection
            .query_row("SELECT kio_path FROM scopes", [], |row| row.get(0))
            .unwrap();
        assert!(path.starts_with(&snapshot.path().to_string_lossy().to_string()));
        assert!(!path.starts_with(&source.path().to_string_lossy().to_string()));
    }
    #[test]
    fn regular_tree_snapshot_rejects_changed_copy() {
        let source = tempfile::tempdir().unwrap();
        fs::write(source.path().join("evidence.txt"), b"before").unwrap();
        let snapshot = snapshot_regular_tree(source.path()).unwrap();
        fs::write(source.path().join("evidence.txt"), b"after").unwrap();
        assert!(snapshot.verify_source_unchanged().is_err());
    }
    #[cfg(unix)]
    #[test]
    fn controlled_environment_uses_retained_directory_fd() {
        let dir = tempfile::tempdir().unwrap();
        let bound = RetainedDirectory::open(dir.path(), "environment").unwrap();
        let environment = ControlledEnvironment {
            fixed: vec![],
            directories: vec![(OsString::from("HOME"), bound.handle)],
        };
        let mut command = Command::new("/bin/sh");
        command.args(["-c", "test -d \"$HOME\""]);
        environment.apply(&mut command).unwrap();
        assert!(command.status().unwrap().success());
    }
    #[test]
    fn report_rejects_symlinked_parent() {
        let fixture = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let root = tempfile::tempdir().unwrap();
        symlink(outside.path(), root.path().join("escape")).unwrap();
        let report = QhardReport {
            schema_version: 1,
            benchmark: "test",
            measurement_class: "test",
            acceptance_eligible: false,
            blocked_reason: Some("test".into()),
            fixture: FixtureBinding {
                root: fixture.path().display().to_string(),
                tree: "t".into(),
                env_name: "e".into(),
                attestation: FileBinding {
                    path: "a".into(),
                    sha256: "b".into(),
                    bytes: 0,
                },
                live_sha256: "x".into(),
                scopes: vec![],
            },
            binary: FileBinding {
                path: "b".into(),
                sha256: "c".into(),
                bytes: 0,
            },
            golden: FileBinding {
                path: "g".into(),
                sha256: "h".into(),
                bytes: 0,
            },
            configuration: Configuration {
                k: 10,
                online_query: false,
                forwarded_credential_names: vec![],
            },
            rows: vec![],
            hits: 0,
            total: 8,
            recall_at_10: 0.0,
            synthetic_m3_1: None,
            combined_hits: None,
            combined_total: None,
        };
        assert!(write_report(
            &root.path().join("escape/report.json"),
            fixture.path(),
            &report
        )
        .is_err());
    }
    #[test]
    fn missing_fixture_attestation_is_not_a_measurement() {
        let dir = tempfile::tempdir().unwrap();
        let options = QhardOptions {
            golden: dir.path().join("golden.jsonl"),
            fixture_root: dir.path().to_path_buf(),
            tree: "qhard".into(),
            env_name: "qhard".into(),
            attestation: None,
            bin: PathBuf::from("kio"),
            k: 10,
            online_query: false,
        };
        assert!(load_fixture(&options).is_err());
    }
    #[test]
    fn result_response_requires_evidence_pointer_and_k_bound() {
        assert_eq!(
            result_paths(
                r#"{"results":[{"evidence_pointer":{"scope_id":"scope-1","path_at_commit":"nested/doc.pdf"}}]}"#,
                10,
            )
            .unwrap(),
            vec!["scope-1:nested/doc.pdf"]
        );
        assert!(result_paths(r#"{"results":[{}]}"#, 10).is_err());
        let many = format!(
            r#"{{"results":[{}]}}"#,
            (0..11)
                .map(|_| r#"{"title":"x"}"#)
                .collect::<Vec<_>>()
                .join(",")
        );
        assert!(result_paths(&many, 10).is_err());
    }
}
