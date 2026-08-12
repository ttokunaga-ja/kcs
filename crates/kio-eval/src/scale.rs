//! Bounded scale-measurement lane for the independently attested fixture.
//!
//! This deliberately consumes, rather than regenerates, the Python fixture.
//! The constants below are the frozen `scale_fixture_spec.py` contract.

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::{
    collections::BTreeSet,
    env,
    ffi::OsString,
    fs,
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
};

use cap_primitives::fs::MetadataExt;
use cap_primitives::{ambient_authority, fs as cap_fs};
use kio_core::cas::hash_bytes;
use rusqlite::{Connection, OpenFlags};
use serde::Serialize;
use serde_json::{Map, Value};
use thiserror::Error;

use crate::runner::{run_bounded_command, BoundedProcessOptions};

const SCHEMA_VERSION: u64 = 1;
const FIXTURE_ID: &str = "kio-scale-120k-v1";
const WORKLOAD_ID: &str = "exact-reference-v1";
const SCOPES: [(&str, &str, &str); 20] = [
    (
        "engineering-architecture",
        "software-engineer",
        "architecture-and-adr",
    ),
    (
        "engineering-api-specs",
        "software-engineer",
        "api-contracts",
    ),
    (
        "engineering-incidents",
        "site-reliability-engineer",
        "incident-response",
    ),
    (
        "engineering-runbooks",
        "site-reliability-engineer",
        "operations-runbooks",
    ),
    (
        "engineering-releases",
        "release-engineer",
        "release-and-migration-notes",
    ),
    ("research-papers", "academic-researcher", "paper-library"),
    (
        "research-lab-notes",
        "academic-researcher",
        "laboratory-notebook",
    ),
    (
        "research-experiments",
        "academic-researcher",
        "experiment-results",
    ),
    (
        "research-grants",
        "principal-investigator",
        "grant-and-budget-records",
    ),
    (
        "research-literature",
        "graduate-student",
        "literature-notes",
    ),
    (
        "ml-model-evaluations",
        "machine-learning-engineer",
        "model-evaluation",
    ),
    ("data-dictionaries", "data-engineer", "data-dictionary"),
    (
        "data-dashboard-reports",
        "data-analyst",
        "dashboard-reports",
    ),
    (
        "ml-notebook-exports",
        "machine-learning-engineer",
        "notebook-exports",
    ),
    ("product-meetings", "product-manager", "meeting-decisions"),
    (
        "product-requirements",
        "product-manager",
        "requirements-and-research",
    ),
    (
        "product-roadmaps",
        "engineering-manager",
        "roadmap-and-planning",
    ),
    (
        "security-compliance",
        "security-engineer",
        "security-and-compliance",
    ),
    ("client-deliverables", "consultant", "client-deliverables"),
    ("downloads-inbox", "knowledge-worker", "downloads-and-inbox"),
];
const MAX_MANIFEST_BYTES: u64 = 16 * 1024 * 1024;
const MAX_ATTESTATION_BYTES: u64 = 16 * 1024 * 1024;
const MAX_BINARY_BYTES: u64 = 512 * 1024 * 1024;
const MAX_METRICS_LOG_BYTES: u64 = 64 * 1024 * 1024;
const MAX_METRICS_DELTA_BYTES: u64 = 64 * 1024;
const MAX_METRIC_LINE_BYTES: u64 = 32 * 1024;
const MAX_REPORT_BYTES: usize = 16 * 1024 * 1024;
const MAX_OWNER_BYTES: u64 = 64 * 1024;
const MAX_SNAPSHOT_FILE_BYTES: u64 = 1024 * 1024 * 1024;
const MAX_SNAPSHOT_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const MAX_SNAPSHOT_ENTRIES: usize = 250_000;
const MAX_WARMUPS: usize = 5;
const MAX_SAMPLES: usize = 100;
const RESULT_LIMIT: usize = 10;
const SCENARIOS: [(&str, Option<&str>, f64); 3] = [
    ("M3-1", None, 5_000.0),
    ("M3-2", Some("--all-history"), 7_000.0),
    ("M3-3", Some("--include-deleted"), 7_000.0),
];
static REPORT_SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn expected_shape(profile: &str) -> Option<(u64, u64, u64, u64, u64)> {
    match profile {
        // files/scope, sections/file, body chars, total chunks, minimum chunks
        "tiny" => Some((1, 3, 420, 60, 60)),
        "full" => Some((200, 30, 1_800, 120_000, 100_001)),
        _ => None,
    }
}

fn frozen_manifest_sha256(profile: &str) -> Option<&'static str> {
    // Exact pretty-JSON bytes produced by the frozen Python generator.  This
    // prevents a forged owner marker from authorizing a self-consistent but
    // different manifest (including arbitrary file hashes/content roots).
    match profile {
        "tiny" => Some("f0b5674560bec23efada56b22caea40d2a812b09c02593c8c567297304d7715a"),
        "full" => Some("ded91cec7211ae5249587173485e3d0b24e1478ca2b6780f04c3d9bbad9ab030"),
        _ => None,
    }
}

#[derive(Debug, Clone)]
pub struct ScaleOptions {
    pub corpus: PathBuf,
    pub manifest: Option<PathBuf>,
    pub attestation: Option<PathBuf>,
    pub bin: PathBuf,
    pub warmups: usize,
    pub samples: usize,
}

#[derive(Debug, Error)]
pub enum ScaleError {
    #[error("invalid scale benchmark input: {0}")]
    Input(String),
    #[error("scale benchmark process failed: {0}")]
    Process(#[from] crate::runner::BoundedProcessError),
    #[error("could not serialize scale benchmark report: {0}")]
    Serialize(#[from] serde_json::Error),
}

#[derive(Debug, Serialize)]
pub struct ScaleReport {
    schema_version: u64,
    benchmark: &'static str,
    measurement_class: &'static str,
    acceptance_eligible: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    passed_p95_thresholds: Option<bool>,
    fixture: FixtureBinding,
    binary: FileBinding,
    platform: Platform,
    configuration: Configuration,
    scenarios: Vec<ScenarioReport>,
}

impl ScaleReport {
    pub fn acceptance_failed(&self) -> bool {
        self.acceptance_eligible && self.passed_p95_thresholds != Some(true)
    }
}

#[derive(Debug, Serialize)]
struct FixtureBinding {
    manifest: FileBinding,
    attestation: FileBinding,
    profile: String,
    current_eligible_chunks: u64,
}
#[derive(Debug, Serialize, PartialEq, Eq)]
struct FileBinding {
    path: String,
    sha256: String,
    bytes: usize,
}
#[derive(Debug, Serialize)]
struct Platform {
    os: String,
    arch: String,
    family: String,
}
#[derive(Debug, Serialize)]
struct Configuration {
    warmups: usize,
    samples: usize,
    query_schedule: &'static str,
    result_limit: usize,
}
#[derive(Debug, Serialize)]
struct ScenarioReport {
    name: &'static str,
    selector_flag: Option<&'static str>,
    raw_samples: Vec<Sample>,
    process_wall_statistics_ms: Statistics,
    metric_statistics_ms: Option<Statistics>,
    #[serde(skip_serializing_if = "Option::is_none")]
    p95_threshold_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    passed_p95_threshold: Option<bool>,
}
#[derive(Debug, Serialize)]
struct Sample {
    sequence: usize,
    query_index: usize,
    process_wall_duration_ms: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    kio_search_latency_ms: Option<f64>,
}
#[derive(Debug, Serialize)]
struct Statistics {
    p50: f64,
    p95: f64,
    p99: f64,
    min: f64,
    max: f64,
}

struct Fixture {
    corpus: PathBuf,
    root: fs::File,
    manifest: Value,
    attestation: Value,
    manifest_binding: FileBinding,
    attestation_binding: FileBinding,
    profile: String,
    chunks: u64,
    scope_ids: BTreeSet<String>,
    scope_ids_ordered: Vec<String>,
}

/// Private, immutable-by-construction measurement inputs.  The production CLI
/// is pathname based, so retained descriptors alone cannot stop a same-UID
/// rename from changing `.kio` or XDG descendants between attest and search.
struct MeasurementSnapshot {
    _temp: tempfile::TempDir,
    corpus: PathBuf,
    bin: PathBuf,
}

struct BoundBinary {
    parent: fs::File,
    name: String,
    bytes: Vec<u8>,
    binding: FileBinding,
}

#[derive(Default)]
struct SnapshotBudget {
    entries: usize,
    bytes: u64,
}

fn read_regular(path: &Path, maximum: u64, label: &str) -> Result<Vec<u8>, ScaleError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|e| ScaleError::Input(format!("{label} is missing: {}: {e}", path.display())))?;
    if !metadata.file_type().is_file() || metadata.len() > maximum {
        return Err(ScaleError::Input(format!(
            "{label} must be a bounded regular file: {}",
            path.display()
        )));
    }
    fs::read(path).map_err(|e| ScaleError::Input(format!("cannot read {label}: {e}")))
}

fn open_dir_at(parent: &fs::File, name: &str, label: &str) -> Result<fs::File, ScaleError> {
    cap_fs::open_dir_nofollow(parent, Path::new(name))
        .map_err(|e| ScaleError::Input(format!("cannot open {label} without following links: {e}")))
}

fn read_regular_at(
    parent: &fs::File,
    name: &str,
    maximum: u64,
    label: &str,
) -> Result<Vec<u8>, ScaleError> {
    let before = cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No)
        .map_err(|e| ScaleError::Input(format!("{label} is missing: {e}")))?;
    if !before.file_type().is_file() || before.len() > maximum {
        return Err(ScaleError::Input(format!(
            "{label} must be a bounded regular file"
        )));
    }
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let file = cap_fs::open(parent, Path::new(name), &options).map_err(|e| {
        ScaleError::Input(format!("cannot open {label} without following links: {e}"))
    })?;
    let opened = cap_fs::Metadata::from_file(&file)
        .map_err(|e| ScaleError::Input(format!("cannot inspect {label}: {e}")))?;
    let after = cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No)
        .map_err(|e| ScaleError::Input(format!("cannot recheck {label}: {e}")))?;
    if !opened.file_type().is_file()
        || opened.len() > maximum
        || !same_file(&before, &opened)
        || !same_file(&opened, &after)
    {
        return Err(ScaleError::Input(format!("{label} changed while opening")));
    }
    let mut bytes = Vec::with_capacity(opened.len() as usize);
    file.take(maximum + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| ScaleError::Input(format!("cannot read {label}: {e}")))?;
    if bytes.len() as u64 != opened.len() {
        return Err(ScaleError::Input(format!("{label} changed while reading")));
    }
    Ok(bytes)
}

#[cfg(unix)]
fn open_sqlite_at(
    parent: &fs::File,
    name: &str,
    label: &str,
) -> Result<(Connection, tempfile::TempDir), ScaleError> {
    // SQLite's WAL VFS reopens `-wal` and `-shm` beside the database.  A
    // `/dev/fd/N` main path therefore fails (or ignores committed WAL pages).
    // Copy the descriptor-verified sibling set into a private directory first;
    // SQLite subsequently receives no public fixture pathname.
    let temp = tempfile::Builder::new()
        .prefix("kio-scale-sqlite-")
        .tempdir()
        .map_err(|e| ScaleError::Input(format!("cannot create private SQLite snapshot: {e}")))?;
    // Do not copy `-shm`: it contains process-local lock/index state and can
    // make a copied WAL report I/O errors.  The private connection may rebuild
    // it safely; no source file is ever opened writable.
    for suffix in ["", "-wal"] {
        let source = format!("{name}{suffix}");
        match cap_fs::stat(parent, Path::new(&source), cap_fs::FollowSymlinks::No) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound && !suffix.is_empty() => {
                continue
            }
            Err(error) => {
                return Err(ScaleError::Input(format!(
                    "cannot inspect {label}: {error}"
                )))
            }
            Ok(metadata) if !metadata.file_type().is_file() => {
                return Err(ScaleError::Input(format!(
                    "{label} sidecar must be a regular file"
                )))
            }
            Ok(_) => {
                let bytes = read_regular_at(parent, &source, MAX_SNAPSHOT_FILE_BYTES, label)?;
                fs::write(temp.path().join(&source), bytes).map_err(|e| {
                    ScaleError::Input(format!("cannot write private {label} snapshot: {e}"))
                })?;
            }
        }
    }
    let connection = Connection::open_with_flags(
        temp.path().join(name),
        OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(|e| ScaleError::Input(format!("cannot open private {label} snapshot: {e}")))?;
    Ok((connection, temp))
}

#[cfg(not(unix))]
fn open_sqlite_at(
    _: &fs::File,
    _: &str,
    label: &str,
) -> Result<(Connection, tempfile::TempDir), ScaleError> {
    Err(ScaleError::Input(format!(
        "{label} requires descriptor-bound SQLite support on this platform"
    )))
}

fn file_binding(
    path: &Path,
    maximum: u64,
    label: &str,
) -> Result<(Vec<u8>, FileBinding), ScaleError> {
    let bytes = read_regular(path, maximum, label)?;
    Ok((
        bytes.clone(),
        FileBinding {
            path: path.display().to_string(),
            sha256: hash_bytes(&bytes),
            bytes: bytes.len(),
        },
    ))
}

fn bind_binary(path: &Path) -> Result<BoundBinary, ScaleError> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|e| ScaleError::Input(format!("cannot resolve --bin: {e}")))?
            .join(path)
    };
    let parent_path = absolute
        .parent()
        .ok_or_else(|| ScaleError::Input("--bin has no parent".into()))?;
    let name = absolute
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| ScaleError::Input("--bin has no UTF-8 filename".into()))?
        .to_owned();
    let canonical_parent = fs::canonicalize(parent_path)
        .map_err(|e| ScaleError::Input(format!("cannot canonicalize --bin parent: {e}")))?;
    let parent = cap_fs::open_ambient_dir(&canonical_parent, ambient_authority())
        .map_err(|e| ScaleError::Input(format!("cannot retain --bin parent: {e}")))?;
    let bytes = read_regular_at(&parent, &name, MAX_BINARY_BYTES, "kio binary")?;
    let binding = FileBinding {
        path: canonical_parent.join(&name).display().to_string(),
        sha256: hash_bytes(&bytes),
        bytes: bytes.len(),
    };
    Ok(BoundBinary {
        parent,
        name,
        bytes,
        binding,
    })
}

fn recheck_bound_binary(binary: &BoundBinary) -> Result<(), ScaleError> {
    let bytes = read_regular_at(&binary.parent, &binary.name, MAX_BINARY_BYTES, "kio binary")?;
    if bytes != binary.bytes {
        return Err(ScaleError::Input(
            "kio binary changed while being measured".into(),
        ));
    }
    Ok(())
}

fn copy_snapshot_tree(
    source: &fs::File,
    destination: &Path,
    budget: &mut SnapshotBudget,
) -> Result<(), ScaleError> {
    fs::create_dir(destination)
        .map_err(|e| ScaleError::Input(format!("cannot create private fixture snapshot: {e}")))?;
    #[cfg(unix)]
    fs::set_permissions(destination, fs::Permissions::from_mode(0o700)).map_err(|e| {
        ScaleError::Input(format!(
            "cannot secure private fixture snapshot directory: {e}"
        ))
    })?;
    let mut entries = Vec::new();
    for entry in cap_fs::read_dir(source, Path::new("."))
        .map_err(|e| ScaleError::Input(format!("cannot enumerate retained fixture: {e}")))?
    {
        let entry = entry
            .map_err(|e| ScaleError::Input(format!("cannot enumerate retained fixture: {e}")))?;
        budget.entries += 1;
        if budget.entries > MAX_SNAPSHOT_ENTRIES {
            return Err(ScaleError::Input(
                "fixture snapshot exceeds entry bound".into(),
            ));
        }
        entries.push(entry);
    }
    entries.sort_by_key(|entry| entry.file_name());
    for entry in entries {
        let name = entry
            .file_name()
            .to_str()
            .ok_or_else(|| ScaleError::Input("fixture contains non-UTF-8 entry".into()))?
            .to_owned();
        let ty = entry
            .file_type()
            .map_err(|e| ScaleError::Input(format!("cannot inspect retained fixture: {e}")))?;
        let target = destination.join(&name);
        if ty.is_dir() {
            let child = open_dir_at(source, &name, "fixture snapshot directory")?;
            copy_snapshot_tree(&child, &target, budget)?;
        } else if ty.is_file() {
            let data = read_regular_at(
                source,
                &name,
                MAX_SNAPSHOT_FILE_BYTES,
                "fixture snapshot file",
            )?;
            budget.bytes = budget.bytes.checked_add(data.len() as u64).ok_or_else(|| {
                ScaleError::Input("fixture snapshot byte counter overflow".into())
            })?;
            if budget.bytes > MAX_SNAPSHOT_BYTES {
                return Err(ScaleError::Input(
                    "fixture snapshot exceeds byte bound".into(),
                ));
            }
            fs::write(&target, data).map_err(|e| {
                ScaleError::Input(format!("cannot write private fixture snapshot: {e}"))
            })?;
            #[cfg(unix)]
            fs::set_permissions(&target, fs::Permissions::from_mode(0o600)).map_err(|e| {
                ScaleError::Input(format!("cannot secure private fixture snapshot file: {e}"))
            })?;
        } else {
            return Err(ScaleError::Input(
                "fixture snapshot rejects links and special files".into(),
            ));
        }
    }
    Ok(())
}

/// Digest the complete retained fixture tree in stable lexical order.  This
/// intentionally covers the SQLite files/WAL, registry, device state, and
/// every source byte, rather than only manifest-declared documents.
fn snapshot_tree_digest(source: &fs::File) -> Result<String, ScaleError> {
    fn walk(
        directory: &fs::File,
        prefix: &Path,
        records: &mut Vec<String>,
        budget: &mut SnapshotBudget,
    ) -> Result<(), ScaleError> {
        let mut entries = Vec::new();
        for entry in cap_fs::read_dir(directory, Path::new("."))
            .map_err(|e| ScaleError::Input(format!("cannot enumerate retained fixture: {e}")))?
        {
            let entry = entry.map_err(|e| {
                ScaleError::Input(format!("cannot enumerate retained fixture: {e}"))
            })?;
            budget.entries += 1;
            if budget.entries > MAX_SNAPSHOT_ENTRIES {
                return Err(ScaleError::Input(
                    "fixture digest exceeds entry bound".into(),
                ));
            }
            entries.push(entry);
        }
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            let name = entry
                .file_name()
                .to_str()
                .ok_or_else(|| ScaleError::Input("fixture contains non-UTF-8 entry".into()))?
                .to_owned();
            let relative = prefix.join(&name);
            let ty = entry
                .file_type()
                .map_err(|e| ScaleError::Input(format!("cannot inspect retained fixture: {e}")))?;
            if ty.is_dir() {
                records.push(format!("D:{}", relative.display()));
                walk(
                    &open_dir_at(directory, &name, "fixture digest directory")?,
                    &relative,
                    records,
                    budget,
                )?;
            } else if ty.is_file() {
                let data = read_regular_at(
                    directory,
                    &name,
                    MAX_SNAPSHOT_FILE_BYTES,
                    "fixture digest file",
                )?;
                budget.bytes = budget.bytes.checked_add(data.len() as u64).ok_or_else(|| {
                    ScaleError::Input("fixture digest byte counter overflow".into())
                })?;
                if budget.bytes > MAX_SNAPSHOT_BYTES {
                    return Err(ScaleError::Input(
                        "fixture digest exceeds byte bound".into(),
                    ));
                }
                records.push(format!("F:{}:{}", relative.display(), hash_bytes(&data)));
            } else {
                return Err(ScaleError::Input(
                    "fixture digest rejects links and special files".into(),
                ));
            }
        }
        Ok(())
    }
    let mut records = Vec::new();
    walk(
        source,
        Path::new(""),
        &mut records,
        &mut SnapshotBudget::default(),
    )?;
    Ok(hash_bytes(records.join("\n").as_bytes()))
}

fn snapshot_measurement_inputs(
    root: &fs::File,
    binary_bytes: &[u8],
    binary: &FileBinding,
) -> Result<MeasurementSnapshot, ScaleError> {
    let expected_tree = snapshot_tree_digest(root)?;
    let temp = tempfile::Builder::new()
        .prefix("kio-scale-measurement-")
        .tempdir()
        .map_err(|e| {
            ScaleError::Input(format!("cannot create private measurement snapshot: {e}"))
        })?;
    let snapshot_corpus = temp.path().join("corpus");
    copy_snapshot_tree(root, &snapshot_corpus, &mut SnapshotBudget::default())?;
    let snapshot_handle = cap_fs::open_ambient_dir(&snapshot_corpus, ambient_authority())
        .map_err(|e| ScaleError::Input(format!("cannot retain private fixture snapshot: {e}")))?;
    if snapshot_tree_digest(&snapshot_handle)? != expected_tree {
        return Err(ScaleError::Input(
            "private fixture snapshot differs from retained attested tree".into(),
        ));
    }
    let snapshot_bin = temp.path().join("kio");
    fs::write(&snapshot_bin, binary_bytes)
        .map_err(|e| ScaleError::Input(format!("cannot write private binary snapshot: {e}")))?;
    #[cfg(unix)]
    fs::set_permissions(&snapshot_bin, fs::Permissions::from_mode(0o700)).map_err(|e| {
        ScaleError::Input(format!(
            "cannot mark private binary snapshot executable: {e}"
        ))
    })?;
    let (_, copied) = file_binding(
        &snapshot_bin,
        MAX_BINARY_BYTES,
        "private kio binary snapshot",
    )?;
    if copied.sha256 != binary.sha256 || copied.bytes != binary.bytes {
        return Err(ScaleError::Input(
            "private binary snapshot differs from verified binary".into(),
        ));
    }
    Ok(MeasurementSnapshot {
        _temp: temp,
        corpus: snapshot_corpus,
        bin: snapshot_bin,
    })
}

fn rewrite_snapshot_registry(snapshot_corpus: &Path, corpus: &Path) -> Result<(), ScaleError> {
    let registry = snapshot_corpus.join(".kio-eval-device/data/kio/scope-registry.sqlite");
    let connection = Connection::open(&registry)
        .map_err(|e| ScaleError::Input(format!("cannot open private snapshot registry: {e}")))?;
    let changed = connection.execute(
        "UPDATE scopes SET kio_path = replace(kio_path, ?1, ?2), root_path = replace(root_path, ?1, ?2) WHERE kio_path LIKE (?1 || '/%') AND root_path LIKE (?1 || '/%')",
        rusqlite::params![corpus.to_string_lossy(), snapshot_corpus.to_string_lossy()],
    ).map_err(|e| ScaleError::Input(format!("cannot rewrite private snapshot registry: {e}")))?;
    if changed != SCOPES.len() {
        return Err(ScaleError::Input(
            "private snapshot registry lacks exactly the attested scopes".into(),
        ));
    }
    drop(connection);
    Ok(())
}

fn object<'a>(value: &'a Value, label: &str) -> Result<&'a Map<String, Value>, ScaleError> {
    value
        .as_object()
        .ok_or_else(|| ScaleError::Input(format!("{label} must be an object")))
}
fn exact_keys(object: &Map<String, Value>, keys: &[&str], label: &str) -> Result<(), ScaleError> {
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = keys.iter().copied().collect::<BTreeSet<_>>();
    if actual != expected {
        return Err(ScaleError::Input(format!("{label} field set mismatch")));
    }
    Ok(())
}
fn string(object: &Map<String, Value>, key: &str, label: &str) -> Result<String, ScaleError> {
    object
        .get(key)
        .and_then(Value::as_str)
        .filter(|v| !v.is_empty())
        .map(ToOwned::to_owned)
        .ok_or_else(|| ScaleError::Input(format!("{label}.{key} must be a nonempty string")))
}
fn uint(object: &Map<String, Value>, key: &str, label: &str) -> Result<u64, ScaleError> {
    object
        .get(key)
        .and_then(Value::as_u64)
        .ok_or_else(|| ScaleError::Input(format!("{label}.{key} must be an unsigned integer")))
}
fn uint_or_null(
    object: &Map<String, Value>,
    key: &str,
    label: &str,
) -> Result<Option<u64>, ScaleError> {
    match object.get(key) {
        Some(Value::Null) => Ok(None),
        Some(value) => value.as_u64().map(Some).ok_or_else(|| {
            ScaleError::Input(format!("{label}.{key} must be an unsigned integer or null"))
        }),
        None => Err(ScaleError::Input(format!("{label}.{key} is missing"))),
    }
}

fn sha256_hex(value: &str, label: &str) -> Result<(), ScaleError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(ScaleError::Input(format!(
            "{label} must be a lowercase SHA-256 hex digest"
        )));
    }
    Ok(())
}

fn manifest_content_root(scopes: &[Value]) -> Result<String, ScaleError> {
    let mut rows = Vec::new();
    for scope in scopes {
        let scope = object(scope, "manifest scope")?;
        let scope_name = string(scope, "name", "manifest scope")?;
        let files = scope
            .get("files")
            .and_then(Value::as_array)
            .ok_or_else(|| ScaleError::Input("manifest scope files must be an array".into()))?;
        for entry in files {
            let entry = object(entry, "manifest source")?;
            let mut row = Map::new();
            row.insert("scope".into(), Value::String(scope_name.clone()));
            for key in ["path", "raw_sha256", "bytes", "expected_chunks"] {
                row.insert(
                    key.into(),
                    entry.get(key).cloned().ok_or_else(|| {
                        ScaleError::Input(format!("manifest source.{key} missing"))
                    })?,
                );
            }
            rows.push(Value::Object(row));
        }
    }
    rows.sort_by(|left, right| {
        let left = left.as_object().expect("constructed");
        let right = right.as_object().expect("constructed");
        (left["scope"].as_str(), left["path"].as_str())
            .cmp(&(right["scope"].as_str(), right["path"].as_str()))
    });
    let bytes = serde_jcs::to_vec(&rows).map_err(|e| {
        ScaleError::Input(format!("cannot canonicalize manifest content root: {e}"))
    })?;
    Ok(hash_bytes(&bytes).trim_start_matches("sha256:").to_owned())
}

fn validate_owner(
    root: &fs::File,
    manifest_binding: &FileBinding,
    profile: &str,
) -> Result<(), ScaleError> {
    let raw = read_regular_at(
        root,
        ".kio-scale-owner.json",
        MAX_OWNER_BYTES,
        "scale owner marker",
    )?;
    let owner: Value = serde_json::from_slice(&raw)
        .map_err(|e| ScaleError::Input(format!("scale owner marker is invalid JSON: {e}")))?;
    let owner = object(&owner, "scale owner marker")?;
    let required = [
        "schema_version",
        "owner",
        "fixture_id",
        "profile",
        "state",
        "manifest_sha256",
    ];
    exact_keys(owner, &required, "scale owner marker")?;
    if uint(owner, "schema_version", "scale owner marker")? != SCHEMA_VERSION
        || string(owner, "owner", "scale owner marker")? != "eval/generate_scale_corpus.py"
        || string(owner, "fixture_id", "scale owner marker")? != FIXTURE_ID
        || string(owner, "profile", "scale owner marker")? != profile
        || string(owner, "state", "scale owner marker")? != "ready"
        || string(owner, "manifest_sha256", "scale owner marker")?
            != manifest_binding.sha256.trim_start_matches("sha256:")
    {
        return Err(ScaleError::Input(
            "scale owner marker does not bind a ready frozen manifest".into(),
        ));
    }
    Ok(())
}

fn load_fixture(options: &ScaleOptions) -> Result<Fixture, ScaleError> {
    let requested_corpus = fs::symlink_metadata(&options.corpus)
        .map_err(|e| ScaleError::Input(format!("cannot inspect --corpus: {e}")))?;
    if requested_corpus.file_type().is_symlink() || !requested_corpus.is_dir() {
        return Err(ScaleError::Input(
            "--corpus must be a real directory, not a symlink".into(),
        ));
    }
    let corpus = fs::canonicalize(&options.corpus)
        .map_err(|e| ScaleError::Input(format!("cannot open corpus: {e}")))?;
    if !corpus.is_dir() {
        return Err(ScaleError::Input("--corpus must be a directory".into()));
    }
    let official_manifest = corpus.join("scale-corpus-manifest.json");
    let official_attestation = corpus.join("scale-attestation.json");
    // Overrides are only spelling overrides for the owned artifacts: allowing
    // an arbitrary external JSON file would bypass the owner marker binding.
    let manifest_path = options
        .manifest
        .clone()
        .unwrap_or_else(|| official_manifest.clone());
    let attestation_path = options
        .attestation
        .clone()
        .unwrap_or_else(|| official_attestation.clone());
    if fs::canonicalize(&manifest_path).ok().as_deref() != Some(official_manifest.as_path())
        || fs::canonicalize(&attestation_path).ok().as_deref()
            != Some(official_attestation.as_path())
    {
        return Err(ScaleError::Input(
            "--manifest and --attestation must resolve to the owned corpus artifacts".into(),
        ));
    }
    let root = cap_fs::open_ambient_dir(&corpus, ambient_authority())
        .map_err(|e| ScaleError::Input(format!("cannot retain corpus root: {e}")))?;
    let opened_root = cap_fs::Metadata::from_file(&root)
        .map_err(|e| ScaleError::Input(format!("cannot inspect retained corpus root: {e}")))?;
    if !opened_root.file_type().is_dir()
        || !same_file(
            &cap_fs::Metadata::from_just_metadata(requested_corpus),
            &opened_root,
        )
    {
        return Err(ScaleError::Input(
            "--corpus changed while being retained".into(),
        ));
    }
    let manifest_raw = read_regular_at(
        &root,
        "scale-corpus-manifest.json",
        MAX_MANIFEST_BYTES,
        "scale manifest",
    )?;
    let manifest_binding = FileBinding {
        path: official_manifest.display().to_string(),
        sha256: hash_bytes(&manifest_raw),
        bytes: manifest_raw.len(),
    };
    let attestation_raw = read_regular_at(
        &root,
        "scale-attestation.json",
        MAX_ATTESTATION_BYTES,
        "scale attestation",
    )?;
    let attestation_binding = FileBinding {
        path: official_attestation.display().to_string(),
        sha256: hash_bytes(&attestation_raw),
        bytes: attestation_raw.len(),
    };
    let manifest: Value = serde_json::from_slice(&manifest_raw)
        .map_err(|e| ScaleError::Input(format!("scale manifest is invalid JSON: {e}")))?;
    let attestation: Value = serde_json::from_slice(&attestation_raw)
        .map_err(|e| ScaleError::Input(format!("scale attestation is invalid JSON: {e}")))?;
    let m = object(&manifest, "scale manifest")?;
    exact_keys(
        m,
        &[
            "schema_version",
            "fixture_id",
            "generator",
            "seed",
            "profile",
            "query_workload_id",
            "chunking",
            "shape",
            "scopes",
            "needles",
            "content_root_sha256",
        ],
        "scale manifest",
    )?;
    if uint(m, "schema_version", "manifest")? != SCHEMA_VERSION
        || string(m, "fixture_id", "manifest")? != FIXTURE_ID
        || string(m, "query_workload_id", "manifest")? != WORKLOAD_ID
        || string(m, "generator", "manifest")? != "eval/generate_scale_corpus.py"
        || uint(m, "seed", "manifest")? != 20260713
    {
        return Err(ScaleError::Input(
            "scale manifest frozen identity mismatch".into(),
        ));
    }
    let profile = string(m, "profile", "manifest")?;
    let Some((files_per_scope, sections_per_file, body_chars, expected_chunks, minimum_chunks)) =
        expected_shape(&profile)
    else {
        return Err(ScaleError::Input(
            "scale manifest profile is invalid".into(),
        ));
    };
    if manifest_binding.sha256.trim_start_matches("sha256:")
        != frozen_manifest_sha256(&profile).expect("profile validated")
    {
        return Err(ScaleError::Input(
            "scale manifest bytes differ from frozen generator output".into(),
        ));
    }
    validate_owner(&root, &manifest_binding, &profile)?;
    let chunking = object(
        m.get("chunking")
            .ok_or_else(|| ScaleError::Input("manifest.chunking missing".into()))?,
        "manifest.chunking",
    )?;
    exact_keys(
        chunking,
        &["strategy", "max_chars", "chunking_config_hash"],
        "manifest.chunking",
    )?;
    if string(chunking, "strategy", "manifest.chunking")? != "heading"
        || uint(chunking, "max_chars", "manifest.chunking")? != 6000
        || string(chunking, "chunking_config_hash", "manifest.chunking")?
            != "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea"
    {
        return Err(ScaleError::Input(
            "scale manifest chunking contract mismatch".into(),
        ));
    }
    let shape = object(
        m.get("shape")
            .ok_or_else(|| ScaleError::Input("manifest.shape missing".into()))?,
        "manifest.shape",
    )?;
    exact_keys(
        shape,
        &[
            "scope_count",
            "files_per_scope",
            "sections_per_file",
            "expected_files",
            "expected_current_chunks",
            "minimum_current_chunks",
            "body_chars",
        ],
        "manifest.shape",
    )?;
    if uint(shape, "scope_count", "manifest.shape")? != 20 {
        return Err(ScaleError::Input(
            "scale manifest must declare 20 scopes".into(),
        ));
    }
    if uint(shape, "files_per_scope", "manifest.shape")? != files_per_scope
        || uint(shape, "sections_per_file", "manifest.shape")? != sections_per_file
        || uint(shape, "body_chars", "manifest.shape")? != body_chars
        || uint(shape, "expected_files", "manifest.shape")? != files_per_scope * 20
        || uint(shape, "expected_current_chunks", "manifest.shape")? != expected_chunks
        || uint(shape, "minimum_current_chunks", "manifest.shape")? != minimum_chunks
    {
        return Err(ScaleError::Input(
            "scale manifest shape differs from frozen profile".into(),
        ));
    }
    let chunks = expected_chunks;
    let scopes = m
        .get("scopes")
        .and_then(Value::as_array)
        .ok_or_else(|| ScaleError::Input("manifest.scopes must be an array".into()))?;
    let needles = m
        .get("needles")
        .and_then(Value::as_array)
        .ok_or_else(|| ScaleError::Input("manifest.needles must be an array".into()))?;
    if scopes.len() != 20 || needles.len() != 20 {
        return Err(ScaleError::Input(
            "scale manifest must have exactly 20 scopes and needles".into(),
        ));
    }
    for (index, (expected_name, expected_persona, expected_use_case)) in SCOPES.iter().enumerate() {
        let scope = object(&scopes[index], "manifest scope")?;
        exact_keys(
            scope,
            &[
                "name",
                "persona",
                "use_case",
                "expected_files",
                "expected_current_chunks",
                "files",
            ],
            "manifest scope",
        )?;
        if string(scope, "name", "manifest scope")? != *expected_name
            || string(scope, "persona", "manifest scope")? != *expected_persona
            || string(scope, "use_case", "manifest scope")? != *expected_use_case
        {
            return Err(ScaleError::Input(
                "scale manifest scope ordering differs from frozen spec".into(),
            ));
        }
        if uint(scope, "expected_files", "manifest scope")? != files_per_scope
            || uint(scope, "expected_current_chunks", "manifest scope")?
                != files_per_scope * sections_per_file
        {
            return Err(ScaleError::Input(
                "scale manifest scope shape differs from frozen profile".into(),
            ));
        }
        let files = scope
            .get("files")
            .and_then(Value::as_array)
            .ok_or_else(|| ScaleError::Input("manifest scope files must be an array".into()))?;
        if files.len() != files_per_scope as usize {
            return Err(ScaleError::Input(
                "manifest scope file cardinality differs from frozen profile".into(),
            ));
        }
        for (file_index, entry) in files.iter().enumerate() {
            let entry = object(entry, "manifest source")?;
            exact_keys(
                entry,
                &["path", "raw_sha256", "bytes", "expected_chunks"],
                "manifest source",
            )?;
            if string(entry, "path", "manifest source")? != format!("document-{file_index:04}.md")
                || uint(entry, "expected_chunks", "manifest source")? != sections_per_file
            {
                return Err(ScaleError::Input(
                    "manifest source path/chunk contract differs from frozen profile".into(),
                ));
            }
            sha256_hex(
                &string(entry, "raw_sha256", "manifest source")?,
                "manifest source.raw_sha256",
            )?;
            if uint(entry, "bytes", "manifest source")? == 0 {
                return Err(ScaleError::Input(
                    "manifest source bytes must be positive".into(),
                ));
            }
        }
        let needle = object(&needles[index], "manifest needle")?;
        exact_keys(
            needle,
            &["query", "scope", "file", "heading"],
            "manifest needle",
        )?;
        let expected_query_hash = hash_bytes(format!("20260713:{index}:0:0:0").as_bytes());
        let expected_query = expected_query_hash
            .get(7..19)
            .expect("SHA-256 digest has fixed length");
        if string(needle, "scope", "manifest needle")? != *expected_name
            || string(needle, "file", "manifest needle")? != "document-0000.md"
            || string(needle, "heading", "manifest needle")?
                != format!("Scale record S{index:02} F0000 C00")
            || string(needle, "query", "manifest needle")? != expected_query
        {
            return Err(ScaleError::Input(
                "scale manifest needle differs from frozen spec".into(),
            ));
        }
    }
    if string(m, "content_root_sha256", "manifest")? != manifest_content_root(scopes)? {
        return Err(ScaleError::Input(
            "scale manifest content_root_sha256 mismatch".into(),
        ));
    }
    let a = object(&attestation, "scale attestation")?;
    exact_keys(
        a,
        &[
            "schema_version",
            "passed",
            "fixture_id",
            "query_workload_id",
            "profile",
            "manifest_sha256",
            "content_root_sha256",
            "totals",
            "registry",
            "scopes",
        ],
        "scale attestation",
    )?;
    if uint(a, "schema_version", "attestation")? != SCHEMA_VERSION
        || a.get("passed") != Some(&Value::Bool(true))
        || string(a, "fixture_id", "attestation")? != FIXTURE_ID
        || string(a, "query_workload_id", "attestation")? != WORKLOAD_ID
        || string(a, "profile", "attestation")? != profile
    {
        return Err(ScaleError::Input(
            "scale attestation identity mismatch".into(),
        ));
    }
    if string(a, "content_root_sha256", "attestation")?
        != string(m, "content_root_sha256", "manifest")?
    {
        return Err(ScaleError::Input(
            "attestation does not bind manifest content root".into(),
        ));
    }
    if string(a, "manifest_sha256", "attestation")?
        != manifest_binding
            .sha256
            .strip_prefix("sha256:")
            .unwrap_or(&manifest_binding.sha256)
    {
        return Err(ScaleError::Input(
            "attestation does not bind manifest bytes".into(),
        ));
    }
    let totals = object(
        a.get("totals")
            .ok_or_else(|| ScaleError::Input("attestation.totals missing".into()))?,
        "attestation.totals",
    )?;
    exact_keys(
        totals,
        &[
            "scopes",
            "source_files",
            "physical_chunks",
            "current_eligible_chunks",
            "fts_matched_current_chunks",
            "embedded_current_chunks",
            "minimum_current_chunks",
        ],
        "attestation.totals",
    )?;
    if uint(totals, "scopes", "attestation.totals")? != 20
        || uint(totals, "current_eligible_chunks", "attestation.totals")? != chunks
        || uint(totals, "physical_chunks", "attestation.totals")? != chunks
        || uint(totals, "fts_matched_current_chunks", "attestation.totals")? != chunks
        || uint(totals, "minimum_current_chunks", "attestation.totals")? != minimum_chunks
        || uint(totals, "source_files", "attestation.totals")? != files_per_scope * 20
    {
        return Err(ScaleError::Input(
            "attestation chunk totals mismatch".into(),
        ));
    }
    let attest_scopes = a
        .get("scopes")
        .and_then(Value::as_array)
        .ok_or_else(|| ScaleError::Input("attestation.scopes must be an array".into()))?;
    if attest_scopes.len() != 20 {
        return Err(ScaleError::Input(
            "attestation must contain 20 scope reports".into(),
        ));
    }
    let mut scope_ids = BTreeSet::new();
    let mut scope_ids_ordered = Vec::with_capacity(SCOPES.len());
    for (index, scope) in attest_scopes.iter().enumerate() {
        let scope = object(scope, "attestation scope")?;
        exact_keys(
            scope,
            &[
                "name",
                "scope_id",
                "root_path",
                "head",
                "chunking",
                "source_files",
                "head_tree_entries",
                "physical_chunks",
                "current_eligible_chunks",
                "historical_or_ineligible_chunks",
                "fts_match_sentinel",
                "fts_matched_current_chunks",
                "fts_docsize_current_chunks",
                "embedded_current_chunks",
                "chunk_vec_shadow_rows",
                "max_chunk_rowid",
                "max_association_rowid",
            ],
            "attestation scope",
        )?;
        if string(scope, "name", "attestation scope")? != SCOPES[index].0
            || uint(
                scope,
                "historical_or_ineligible_chunks",
                "attestation scope",
            )? != 0
        {
            return Err(ScaleError::Input(
                "attestation scope does not describe the current-only frozen fixture".into(),
            ));
        }
        let scope_id = string(scope, "scope_id", "attestation scope")?;
        let chunking = object(
            scope
                .get("chunking")
                .ok_or_else(|| ScaleError::Input("attestation scope chunking missing".into()))?,
            "attestation scope chunking",
        )?;
        exact_keys(
            chunking,
            &["strategy", "max_chars", "chunking_config_hash"],
            "attestation scope chunking",
        )?;
        if string(chunking, "strategy", "attestation scope chunking")? != "heading"
            || uint(chunking, "max_chars", "attestation scope chunking")? != 6000
            || string(
                chunking,
                "chunking_config_hash",
                "attestation scope chunking",
            )? != "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea"
        {
            return Err(ScaleError::Input(
                "attestation scope chunking contract mismatch".into(),
            ));
        }
        for key in [
            "source_files",
            "head_tree_entries",
            "physical_chunks",
            "current_eligible_chunks",
            "fts_matched_current_chunks",
            "fts_docsize_current_chunks",
            "embedded_current_chunks",
            "max_chunk_rowid",
            "max_association_rowid",
        ] {
            let _ = uint(scope, key, "attestation scope")?;
        }
        let _ = uint_or_null(scope, "chunk_vec_shadow_rows", "attestation scope")?;
        if !scope_ids.insert(scope_id.clone()) {
            return Err(ScaleError::Input(
                "attestation scope IDs are not unique".into(),
            ));
        }
        scope_ids_ordered.push(scope_id);
    }
    let registry = object(
        a.get("registry")
            .ok_or_else(|| ScaleError::Input("attestation registry missing".into()))?,
        "attestation registry",
    )?;
    exact_keys(
        registry,
        &["path", "rows", "indexed_global_participants"],
        "attestation registry",
    )?;
    let _ = string(registry, "path", "attestation registry")?;
    if uint(registry, "rows", "attestation registry")? != 20
        || uint(
            registry,
            "indexed_global_participants",
            "attestation registry",
        )? != 20
    {
        return Err(ScaleError::Input(
            "attestation registry cardinality mismatch".into(),
        ));
    }
    Ok(Fixture {
        corpus,
        root,
        manifest,
        attestation,
        manifest_binding,
        attestation_binding,
        profile,
        chunks,
        scope_ids,
        scope_ids_ordered,
    })
}

/// Re-attest the fixture bytes and the indexed current-chunk cardinality while
/// the fixture lock is held.  This is intentionally independent of the
/// saved JSON: the saved attestation supplies the frozen expected values, but
/// every source file, scope identity, HEAD, and searchable current-chunk
/// count is observed again from the live corpus.
fn attest_live_corpus(
    expected_corpus: &Path,
    corpus_handle: &fs::File,
    fixture: &Fixture,
) -> Result<(), ScaleError> {
    let scopes = fixture.manifest["scopes"].as_array().expect("validated");
    if fixture.attestation.get("content_root_sha256") != fixture.manifest.get("content_root_sha256")
    {
        return Err(ScaleError::Input(
            "stored attestation does not bind manifest content root".into(),
        ));
    }
    let mut source_total = 0u64;
    let mut physical_total = 0u64;
    let mut current_total = 0u64;
    let mut fts_total = 0u64;
    let mut embedded_total = 0u64;
    // The manifest identity is already checked against the stored attestation
    // in load_fixture; source hashes prove the live corpus still realizes it.
    for (index, manifest_scope) in scopes.iter().enumerate() {
        let scope = object(manifest_scope, "manifest scope")?;
        let name = string(scope, "name", "manifest scope")?;
        let scope_handle = open_dir_at(corpus_handle, &name, "live scope")?;
        let files = scope
            .get("files")
            .and_then(Value::as_array)
            .ok_or_else(|| ScaleError::Input("manifest scope files missing".into()))?;
        let expected_names = files
            .iter()
            .map(|entry| {
                object(entry, "manifest source")
                    .and_then(|entry| string(entry, "path", "manifest source"))
            })
            .collect::<Result<BTreeSet<_>, _>>()?;
        let actual_names = cap_fs::read_dir(&scope_handle, Path::new("."))
            .map_err(|e| ScaleError::Input(format!("cannot enumerate live scope: {e}")))?
            .take(expected_names.len() + 2)
            .map(|entry| {
                entry
                    .map_err(|e| ScaleError::Input(format!("cannot enumerate live scope: {e}")))
                    .map(|entry| entry.file_name().to_string_lossy().into_owned())
            })
            .collect::<Result<BTreeSet<_>, _>>()?;
        let mut allowed_names = expected_names.clone();
        allowed_names.insert(".kio".into());
        if actual_names != allowed_names {
            return Err(ScaleError::Input(
                "live scope has unmanifested or missing entries".into(),
            ));
        }
        for entry in files {
            let entry = object(entry, "manifest source")?;
            let name = string(entry, "path", "manifest source")?;
            let expected = string(entry, "raw_sha256", "manifest source")?;
            let bytes = uint(entry, "bytes", "manifest source")?;
            let data = read_regular_at(&scope_handle, &name, bytes, "live scale source")?;
            if data.len() as u64 != bytes
                || hash_bytes(&data).trim_start_matches("sha256:")
                    != expected.trim_start_matches("sha256:")
            {
                return Err(ScaleError::Input(
                    "live scale source differs from manifest".into(),
                ));
            }
            source_total += 1;
        }
        let kio_handle = open_dir_at(&scope_handle, ".kio", "live scope .kio")?;
        // A fresh scale corpus cannot measure through incomplete destructive
        // maintenance state or retained deletion receipts.
        for runtime in ["tombstones", "purge/erase-receipts"] {
            let mut current = kio_handle
                .try_clone()
                .map_err(|e| ScaleError::Input(format!("cannot retain runtime directory: {e}")))?;
            let mut exists = true;
            for component in runtime.split('/') {
                match cap_fs::stat(&current, Path::new(component), cap_fs::FollowSymlinks::No) {
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                        exists = false;
                        break;
                    }
                    Err(error) => {
                        return Err(ScaleError::Input(format!(
                            "cannot inspect scope runtime directory: {error}"
                        )))
                    }
                    Ok(metadata) if !metadata.file_type().is_dir() => {
                        return Err(ScaleError::Input(
                            "scope runtime path must be a real directory".into(),
                        ))
                    }
                    Ok(_) => current = open_dir_at(&current, component, "scope runtime directory")?,
                }
            }
            if exists
                && cap_fs::read_dir(&current, Path::new("."))
                    .map_err(|e| {
                        ScaleError::Input(format!("cannot enumerate scope runtime directory: {e}"))
                    })?
                    .next()
                    .is_some()
            {
                return Err(ScaleError::Input(
                    "fresh scale scope has runtime deletion state".into(),
                ));
            }
        }
        if let Ok(purge) = open_dir_at(&kio_handle, "purge", "scope purge directory") {
            if cap_fs::stat(
                &purge,
                Path::new("in-progress.json"),
                cap_fs::FollowSymlinks::No,
            )
            .is_ok()
            {
                return Err(ScaleError::Input("scope has an in-progress purge".into()));
            }
        }
        let config_raw =
            read_regular_at(&kio_handle, "config.toml", 1024 * 1024, "live scope config")?;
        let config: toml::Value = toml::from_str(
            std::str::from_utf8(&config_raw)
                .map_err(|_| ScaleError::Input("live scope config is not UTF-8".into()))?,
        )
        .map_err(|e| ScaleError::Input(format!("live scope config is invalid TOML: {e}")))?;
        let (strategy, max_chars) = match config.get("chunking") {
            Some(value) => {
                let configured = value.as_table().ok_or_else(|| {
                    ScaleError::Input("live scope [chunking] must be a table".into())
                })?;
                (
                    configured
                        .get("strategy")
                        .and_then(toml::Value::as_str)
                        .unwrap_or("heading"),
                    configured
                        .get("max_chars")
                        .and_then(toml::Value::as_integer)
                        .unwrap_or(6000),
                )
            }
            None => ("heading", 6000),
        };
        if strategy != "heading" || max_chars != 6000 {
            return Err(ScaleError::Input(
                "live scope chunking config differs from frozen contract".into(),
            ));
        }
        let head = String::from_utf8(read_regular_at(
            &kio_handle,
            "HEAD",
            256,
            "live scope HEAD",
        )?)
        .map_err(|_| ScaleError::Input("live scope HEAD is not UTF-8".into()))?;
        let stored_scope = object(
            &fixture.attestation["scopes"][index],
            "stored attestation scope",
        )?;
        let scope_identity: Value = serde_json::from_slice(&read_regular_at(
            &kio_handle,
            "scope.json",
            64 * 1024,
            "live scope identity",
        )?)
        .map_err(|_| ScaleError::Input("live scope identity is invalid JSON".into()))?;
        if stored_scope.get("head").and_then(Value::as_str) != Some(head.trim())
            || scope_identity.get("scope_id").and_then(Value::as_str)
                != Some(fixture.scope_ids_ordered[index].as_str())
        {
            return Err(ScaleError::Input(
                "live scope identity differs from stored attestation".into(),
            ));
        }
        let index_handle = open_dir_at(&kio_handle, "index", "live scope index")?;
        let (db, _db_snapshot) =
            open_sqlite_at(&index_handle, "sqlite.db", "live scope SQLite index")?;
        let tables = db.prepare("SELECT name FROM sqlite_schema WHERE type IN ('table', 'view') AND name IN ('chunks', 'chunk_config_generations', 'embeddings', 'tree_entries', 'chunk_fts', 'chunk_fts_docsize', 'chunk_vec_rowids')")
            .map_err(|e| ScaleError::Input(format!("cannot inspect live index schema: {e}")))?
            .query_map([], |row| row.get::<_, String>(0)).map_err(|e| ScaleError::Input(format!("cannot inspect live index schema: {e}")))?
            .collect::<Result<BTreeSet<_>, _>>().map_err(|e| ScaleError::Input(format!("cannot inspect live index schema: {e}")))?;
        for required in [
            "chunks",
            "chunk_config_generations",
            "embeddings",
            "tree_entries",
            "chunk_fts",
            "chunk_fts_docsize",
        ] {
            if !tables.contains(required) {
                return Err(ScaleError::Input(format!(
                    "live scope index is missing required table {required}"
                )));
            }
        }
        let vector_shadow = if tables.contains("chunk_vec_rowids") {
            Some(
                db.query_row("SELECT COUNT(*) FROM chunk_vec_rowids", [], |row| {
                    row.get::<_, u64>(0)
                })
                .map_err(|e| {
                    ScaleError::Input(format!("cannot count live vector shadow rows: {e}"))
                })?,
            )
        } else {
            None
        };
        let physical: u64 = db
            .query_row("SELECT COUNT(*) FROM chunks", [], |row| row.get(0))
            .map_err(|e| ScaleError::Input(format!("cannot count live chunks: {e}")))?;
        let max_chunk: u64 = db
            .query_row("SELECT COALESCE(MAX(rowid), 0) FROM chunks", [], |row| {
                row.get(0)
            })
            .map_err(|e| ScaleError::Input(format!("cannot inspect live chunks: {e}")))?;
        let max_association: u64 = db
            .query_row(
                "SELECT COALESCE(MAX(association_rowid), 0) FROM chunk_config_generations",
                [],
                |row| row.get(0),
            )
            .map_err(|e| ScaleError::Input(format!("cannot inspect live associations: {e}")))?;
        let current: u64 = db.query_row(
            "SELECT COUNT(*) FROM chunks c WHERE c.first_seen_commit IS NOT NULL AND c.rowid <= ?1 AND EXISTS (SELECT 1 FROM chunk_config_generations cg WHERE cg.chunk_id = c.chunk_id AND cg.chunking_config_hash = ?2 AND cg.association_rowid <= ?3) AND EXISTS (SELECT 1 FROM tree_entries te WHERE te.commit_hash = ?4 AND te.raw_hash = c.raw_hash AND te.tool_profile_hash = c.tool_profile_hash AND te.gen = c.gen)",
            rusqlite::params![max_chunk, "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea", max_association, head.trim()], |row| row.get(0))
            .map_err(|e| ScaleError::Input(format!("cannot attest live current chunks: {e}")))?;
        let fts: u64 = db.query_row(
            "SELECT COUNT(*) FROM chunk_fts f JOIN chunks c ON c.rowid = f.rowid WHERE c.first_seen_commit IS NOT NULL AND c.rowid <= ?1 AND EXISTS (SELECT 1 FROM chunk_config_generations cg WHERE cg.chunk_id = c.chunk_id AND cg.chunking_config_hash = ?2 AND cg.association_rowid <= ?3) AND EXISTS (SELECT 1 FROM tree_entries te WHERE te.commit_hash = ?4 AND te.raw_hash = c.raw_hash AND te.tool_profile_hash = c.tool_profile_hash AND te.gen = c.gen) AND chunk_fts MATCH 'scale'",
            rusqlite::params![max_chunk, "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea", max_association, head.trim()], |row| row.get(0))
            .map_err(|e| ScaleError::Input(format!("cannot attest live FTS chunks: {e}")))?;
        let docsize: u64 = db.query_row(
            "SELECT COUNT(*) FROM chunk_fts_docsize d JOIN chunks c ON c.rowid = d.id WHERE c.first_seen_commit IS NOT NULL AND c.rowid <= ?1 AND EXISTS (SELECT 1 FROM chunk_config_generations cg WHERE cg.chunk_id = c.chunk_id AND cg.chunking_config_hash = ?2 AND cg.association_rowid <= ?3) AND EXISTS (SELECT 1 FROM tree_entries te WHERE te.commit_hash = ?4 AND te.raw_hash = c.raw_hash AND te.tool_profile_hash = c.tool_profile_hash AND te.gen = c.gen)",
            rusqlite::params![max_chunk, "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea", max_association, head.trim()], |row| row.get(0))
            .map_err(|e| ScaleError::Input(format!("cannot attest live FTS docsize: {e}")))?;
        let embedded: u64 = db.query_row(
            "SELECT COUNT(*) FROM chunks c WHERE c.first_seen_commit IS NOT NULL AND c.rowid <= ?1 AND EXISTS (SELECT 1 FROM chunk_config_generations cg WHERE cg.chunk_id = c.chunk_id AND cg.chunking_config_hash = ?2 AND cg.association_rowid <= ?3) AND EXISTS (SELECT 1 FROM tree_entries te WHERE te.commit_hash = ?4 AND te.raw_hash = c.raw_hash AND te.tool_profile_hash = c.tool_profile_hash AND te.gen = c.gen) AND EXISTS (SELECT 1 FROM embeddings e WHERE e.target_type = 'chunk' AND e.target_id = c.text_hash)",
            rusqlite::params![max_chunk, "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea", max_association, head.trim()], |row| row.get(0))
            .map_err(|e| ScaleError::Input(format!("cannot attest live embeddings: {e}")))?;
        let head_entries: u64 = db
            .query_row(
                "SELECT COUNT(*) FROM tree_entries WHERE commit_hash = ?1",
                [head.trim()],
                |row| row.get(0),
            )
            .map_err(|e| ScaleError::Input(format!("cannot attest live HEAD tree: {e}")))?;
        let expected_tree = files
            .iter()
            .map(|entry| {
                let entry = object(entry, "manifest source")?;
                Ok((
                    string(entry, "path", "manifest source")?,
                    format!("sha256:{}", string(entry, "raw_sha256", "manifest source")?),
                    uint(entry, "expected_chunks", "manifest source")?,
                ))
            })
            .collect::<Result<Vec<_>, ScaleError>>()?;
        let mut tree_statement = db
            .prepare("SELECT path, raw_hash FROM tree_entries WHERE commit_hash = ?1 ORDER BY path")
            .map_err(|e| {
                ScaleError::Input(format!("cannot inspect live HEAD tree mapping: {e}"))
            })?;
        let actual_tree = tree_statement
            .query_map([head.trim()], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
            })
            .map_err(|e| ScaleError::Input(format!("cannot inspect live HEAD tree mapping: {e}")))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| {
                ScaleError::Input(format!("cannot inspect live HEAD tree mapping: {e}"))
            })?;
        if actual_tree.len() != expected_tree.len()
            || actual_tree.iter().zip(expected_tree.iter()).any(
                |((path, raw), (expected_path, expected_raw, _))| {
                    path != expected_path || raw != expected_raw
                },
            )
        {
            return Err(ScaleError::Input(
                "live HEAD tree does not map exactly to manifest sources".into(),
            ));
        }
        for (_, raw_hash, expected_count) in &expected_tree {
            let count: u64 = db.query_row(
                "SELECT COUNT(*) FROM chunks c WHERE c.raw_hash = ?1 AND c.first_seen_commit IS NOT NULL AND c.rowid <= ?2 AND EXISTS (SELECT 1 FROM chunk_config_generations cg WHERE cg.chunk_id = c.chunk_id AND cg.chunking_config_hash = ?3 AND cg.association_rowid <= ?4) AND EXISTS (SELECT 1 FROM tree_entries te WHERE te.commit_hash = ?5 AND te.raw_hash = c.raw_hash AND te.tool_profile_hash = c.tool_profile_hash AND te.gen = c.gen)",
                rusqlite::params![raw_hash, max_chunk, "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea", max_association, head.trim()],
                |row| row.get(0),
            ).map_err(|e| ScaleError::Input(format!("cannot attest per-source eligible chunks: {e}")))?;
            if count != *expected_count {
                return Err(ScaleError::Input(
                    "per-source eligible chunk contract differs from manifest".into(),
                ));
            }
        }
        let expected_chunks = uint(scope, "expected_current_chunks", "manifest scope")?;
        let same_u64 = |key, value| stored_scope.get(key).and_then(Value::as_u64) == Some(value);
        // `corpus` was canonicalized before retaining the root, and the scope
        // leaf was opened nofollow above; constructing this expected spelling
        // avoids re-resolving a public path during attestation.
        let canonical_scope = expected_corpus.join(&name);
        if stored_scope.get("name").and_then(Value::as_str) != Some(name.as_str())
            || stored_scope.get("root_path").and_then(Value::as_str)
                != Some(canonical_scope.to_string_lossy().as_ref())
            || stored_scope
                .get("fts_match_sentinel")
                .and_then(Value::as_str)
                != Some("scale")
            || !same_u64("source_files", files.len() as u64)
            || !same_u64("head_tree_entries", head_entries)
            || !same_u64("physical_chunks", physical)
            || !same_u64("current_eligible_chunks", current)
            || !same_u64(
                "historical_or_ineligible_chunks",
                physical.saturating_sub(current),
            )
            || !same_u64("fts_matched_current_chunks", fts)
            || !same_u64("fts_docsize_current_chunks", docsize)
            || !same_u64("embedded_current_chunks", embedded)
            || uint_or_null(
                stored_scope,
                "chunk_vec_shadow_rows",
                "stored attestation scope",
            )? != vector_shadow
            || stored_scope.get("chunking")
                != Some(
                    &serde_json::json!({"strategy":"heading","max_chars":6000,"chunking_config_hash":"sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea"}),
                )
            || !same_u64("max_chunk_rowid", max_chunk)
            || !same_u64("max_association_rowid", max_association)
            || current != expected_chunks
            || fts != expected_chunks
            || docsize != expected_chunks
        {
            return Err(ScaleError::Input(
                "live scope attestation differs from stored attestation".into(),
            ));
        }
        if head.trim().is_empty() {
            return Err(ScaleError::Input("live scope HEAD is empty".into()));
        }
        physical_total += physical;
        current_total += current;
        fts_total += fts;
        embedded_total += embedded;
    }
    let totals = object(
        fixture
            .attestation
            .get("totals")
            .ok_or_else(|| ScaleError::Input("stored attestation totals missing".into()))?,
        "stored attestation totals",
    )?;
    if totals.get("source_files").and_then(Value::as_u64) != Some(source_total)
        || totals.get("scopes").and_then(Value::as_u64) != Some(SCOPES.len() as u64)
        || totals
            .get("current_eligible_chunks")
            .and_then(Value::as_u64)
            != Some(fixture.chunks)
        || totals.get("physical_chunks").and_then(Value::as_u64) != Some(physical_total)
        || totals
            .get("fts_matched_current_chunks")
            .and_then(Value::as_u64)
            != Some(fts_total)
        || totals
            .get("current_eligible_chunks")
            .and_then(Value::as_u64)
            != Some(current_total)
        || totals
            .get("embedded_current_chunks")
            .and_then(Value::as_u64)
            != Some(embedded_total)
        || totals.get("minimum_current_chunks").and_then(Value::as_u64)
            != fixture.manifest["shape"]["minimum_current_chunks"].as_u64()
        || current_total
            < fixture.manifest["shape"]["minimum_current_chunks"]
                .as_u64()
                .unwrap_or(u64::MAX)
    {
        return Err(ScaleError::Input(
            "live attestation totals differ from stored attestation".into(),
        ));
    }
    let registry = object(
        fixture
            .attestation
            .get("registry")
            .ok_or_else(|| ScaleError::Input("stored attestation registry missing".into()))?,
        "stored attestation registry",
    )?;
    let device = open_dir_at(corpus_handle, ".kio-eval-device", "isolated device")?;
    let data = open_dir_at(&device, "data", "isolated device data")?;
    let kio_data = open_dir_at(&data, "kio", "isolated device Kio data")?;
    let (registry_db, _registry_snapshot) =
        open_sqlite_at(&kio_data, "scope-registry.sqlite", "live scope registry")?;
    let mut rows = registry_db
        .prepare("SELECT scope_id, kio_path, root_path, participates_in_global_search, indexed FROM scopes ORDER BY scope_id LIMIT 21")
        .map_err(|e| ScaleError::Input(format!("cannot attest live scope registry: {e}")))?;
    let actual = rows
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, i64>(3)?,
                row.get::<_, i64>(4)?,
            ))
        })
        .map_err(|e| ScaleError::Input(format!("cannot read live scope registry: {e}")))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| ScaleError::Input(format!("cannot read live scope registry: {e}")))?;
    let expected_registry_path = expected_corpus
        .join(".kio-eval-device/data/kio/scope-registry.sqlite")
        .to_string_lossy()
        .into_owned();
    if actual.len() != SCOPES.len()
        || registry.get("path").and_then(Value::as_str) != Some(expected_registry_path.as_str())
        || registry.get("rows").and_then(Value::as_u64) != Some(actual.len() as u64)
        || registry
            .get("indexed_global_participants")
            .and_then(Value::as_u64)
            != Some(actual.len() as u64)
        || actual
            .iter()
            .any(|(_, _, _, participates, indexed)| *participates != 1 || *indexed != 1)
    {
        return Err(ScaleError::Input(
            "live scope registry differs from stored attestation".into(),
        ));
    }
    for (index, scope_id) in fixture.scope_ids_ordered.iter().enumerate() {
        let scope_root = expected_corpus.join(SCOPES[index].0);
        let expected_kio = scope_root.join(".kio");
        if !actual.iter().any(|(id, kio, root, _, _)| {
            id == scope_id
                && kio == expected_kio.to_string_lossy().as_ref()
                && root == scope_root.to_string_lossy().as_ref()
        }) {
            return Err(ScaleError::Input(
                "live scope registry scope binding differs from stored attestation".into(),
            ));
        }
    }
    Ok(())
}

#[cfg(unix)]
struct FixtureLock {
    file: fs::File,
    root: fs::File,
}
#[cfg(unix)]
impl FixtureLock {
    fn acquire(root: &fs::File) -> Result<Self, ScaleError> {
        let parent = root
            .try_clone()
            .map_err(|e| ScaleError::Input(format!("cannot retain scale fixture root: {e}")))?;
        let metadata = cap_fs::stat(
            &parent,
            Path::new(".kio-scale.lock"),
            cap_fs::FollowSymlinks::No,
        )
        .map_err(|e| ScaleError::Input(format!("scale fixture lock is missing: {e}")))?;
        if !metadata.file_type().is_file() || metadata.len() > 4096 {
            return Err(ScaleError::Input(
                "scale fixture lock must be a bounded regular file".into(),
            ));
        }
        let mut options = cap_fs::OpenOptions::new();
        options
            .read(true)
            .write(true)
            ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
        let file = cap_fs::open(&parent, Path::new(".kio-scale.lock"), &options).map_err(|e| {
            ScaleError::Input(format!(
                "cannot open scale fixture lock without following links: {e}"
            ))
        })?;
        let opened = cap_fs::Metadata::from_file(&file)
            .map_err(|e| ScaleError::Input(format!("cannot inspect scale fixture lock: {e}")))?;
        let named = cap_fs::stat(
            &parent,
            Path::new(".kio-scale.lock"),
            cap_fs::FollowSymlinks::No,
        )
        .map_err(|e| ScaleError::Input(format!("cannot recheck scale fixture lock: {e}")))?;
        if !opened.file_type().is_file() || !same_file(&opened, &named) {
            return Err(ScaleError::Input(
                "scale fixture lock changed while opening".into(),
            ));
        }
        if unsafe { libc::flock(std::os::fd::AsRawFd::as_raw_fd(&file), libc::LOCK_EX) } != 0 {
            return Err(ScaleError::Input(format!(
                "cannot acquire scale fixture lock: {}",
                std::io::Error::last_os_error()
            )));
        }
        Ok(Self { file, root: parent })
    }
}
#[cfg(unix)]
impl Drop for FixtureLock {
    fn drop(&mut self) {
        let _ = unsafe { libc::flock(std::os::fd::AsRawFd::as_raw_fd(&self.file), libc::LOCK_UN) };
    }
}

#[cfg(not(unix))]
struct FixtureLock;
#[cfg(not(unix))]
impl FixtureLock {
    fn acquire(_: &fs::File) -> Result<Self, ScaleError> {
        Err(ScaleError::Input(
            "scale measurement requires a portable fixture lock implementation on this platform"
                .into(),
        ))
    }
}

struct MetricsSnapshot {
    parent: fs::File,
    before: Option<cap_fs::Metadata>,
    offset: u64,
}

fn open_metrics(parent: &fs::File) -> Result<(fs::File, cap_fs::Metadata), ScaleError> {
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let file = cap_fs::open(parent, Path::new("metrics.jsonl"), &options).map_err(|e| {
        ScaleError::Input(format!(
            "cannot open metrics log without following links: {e}"
        ))
    })?;
    let metadata = cap_fs::Metadata::from_file(&file)
        .map_err(|e| ScaleError::Input(format!("cannot inspect metrics log: {e}")))?;
    if !metadata.file_type().is_file() || metadata.len() > MAX_METRICS_LOG_BYTES {
        return Err(ScaleError::Input(
            "metrics log must be a bounded regular file".into(),
        ));
    }
    Ok((file, metadata))
}

fn same_file(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    left.dev() == right.dev() && left.ino() == right.ino()
}

fn snapshot_metrics_log(parent: &fs::File) -> Result<MetricsSnapshot, ScaleError> {
    if matches!(cap_fs::stat(parent, Path::new("metrics.jsonl"), cap_fs::FollowSymlinks::No), Err(error) if error.kind() == std::io::ErrorKind::NotFound)
    {
        return Ok(MetricsSnapshot {
            parent: parent
                .try_clone()
                .map_err(|e| ScaleError::Input(format!("cannot retain metrics parent: {e}")))?,
            offset: 0,
            before: None,
        });
    }
    match open_metrics(parent) {
        Ok((mut file, metadata)) => {
            if metadata.len() > 0 {
                file.seek(SeekFrom::End(-1))
                    .map_err(|e| ScaleError::Input(format!("cannot seek metrics log: {e}")))?;
                let mut byte = [0];
                file.read_exact(&mut byte)
                    .map_err(|e| ScaleError::Input(format!("cannot read metrics log: {e}")))?;
                if byte != *b"\n" {
                    return Err(ScaleError::Input(
                        "existing metrics log lacks a final newline".into(),
                    ));
                }
            }
            Ok(MetricsSnapshot {
                parent: parent
                    .try_clone()
                    .map_err(|e| ScaleError::Input(format!("cannot retain metrics parent: {e}")))?,
                offset: metadata.len(),
                before: Some(metadata),
            })
        }
        Err(error) => Err(error),
    }
}

/// Read exactly one newline-terminated log delta via a nofollow descriptor.
/// A rotation is allowed only when the new live file contains this one line.
fn appended_search_metric(
    snapshot: MetricsSnapshot,
    result_count: usize,
) -> Result<f64, ScaleError> {
    let (mut file, current) = open_metrics(&snapshot.parent)?;
    let start = match snapshot.before.as_ref() {
        Some(before) if same_file(before, &current) => snapshot.offset,
        Some(_) => {
            return Err(ScaleError::Input(
                "metrics log was replaced during a search".into(),
            ))
        }
        None => 0,
    };
    if current.len() < start {
        return Err(ScaleError::Input(
            "metrics log shrank during a search".into(),
        ));
    }
    let delta = current.len() - start;
    if delta == 0 || delta > MAX_METRICS_DELTA_BYTES || delta > MAX_METRIC_LINE_BYTES {
        return Err(ScaleError::Input(
            "search must append one bounded metrics line".into(),
        ));
    }
    file.seek(SeekFrom::Start(start))
        .map_err(|e| ScaleError::Input(format!("cannot seek metrics delta: {e}")))?;
    let mut raw = vec![0; delta as usize];
    file.read_exact(&mut raw)
        .map_err(|e| ScaleError::Input(format!("cannot read metrics delta: {e}")))?;
    let after = cap_fs::Metadata::from_file(&file)
        .map_err(|e| ScaleError::Input(format!("cannot recheck metrics log: {e}")))?;
    let (_, named) = open_metrics(&snapshot.parent)?;
    if !same_file(&current, &after) || !same_file(&current, &named) || after.len() != current.len()
    {
        return Err(ScaleError::Input(
            "metrics log changed while reading its append".into(),
        ));
    }
    if !raw.ends_with(b"\n") || raw.iter().filter(|byte| **byte == b'\n').count() != 1 {
        return Err(ScaleError::Input(
            "search must append exactly one newline-terminated metrics line".into(),
        ));
    }
    let metric: Value = serde_json::from_slice(&raw)
        .map_err(|_| ScaleError::Input("appended metrics line is invalid JSON".into()))?;
    let metric = object(&metric, "search metric")?;
    exact_keys(
        metric,
        &[
            "ts",
            "level",
            "code",
            "component",
            "message",
            "metric",
            "value",
            "context",
        ],
        "search metric",
    )?;
    if metric
        .get("ts")
        .and_then(Value::as_str)
        .is_none_or(str::is_empty)
        || metric.get("level").and_then(Value::as_str) != Some("info")
        || metric.get("code").and_then(Value::as_str) != Some("KIO-M-SEARCH-001")
        || metric.get("component").and_then(Value::as_str) != Some("search")
        || metric.get("message").and_then(Value::as_str) != Some("search completed")
        || metric.get("metric").and_then(Value::as_str) != Some("search.latency_ms")
    {
        return Err(ScaleError::Input(
            "KIO-M-SEARCH-001 envelope is invalid".into(),
        ));
    }
    let context = object(
        metric
            .get("context")
            .ok_or_else(|| ScaleError::Input("search metric context missing".into()))?,
        "search metric context",
    )?;
    exact_keys(
        context,
        &["mode", "scope_count", "result_count"],
        "search metric context",
    )?;
    if context.get("mode").and_then(Value::as_str) != Some("text")
        || context.get("scope_count").and_then(Value::as_u64) != Some(20)
        || context.get("result_count").and_then(Value::as_u64) != Some(result_count as u64)
    {
        return Err(ScaleError::Input(
            "search metric context disagrees with response".into(),
        ));
    }
    metric
        .get("value")
        .and_then(Value::as_f64)
        .filter(|v| v.is_finite() && *v >= 0.0)
        .ok_or_else(|| ScaleError::Input("KIO-M-SEARCH-001 has invalid latency".into()))
}

fn stats(values: &[f64]) -> Result<Statistics, ScaleError> {
    if values.is_empty() || values.iter().any(|v| !v.is_finite() || *v < 0.0) {
        return Err(ScaleError::Input(
            "latency samples must be nonempty finite values".into(),
        ));
    }
    let percentile = |p: f64| {
        let mut sorted = values.to_vec();
        sorted.sort_by(f64::total_cmp);
        sorted[((p * sorted.len() as f64).ceil() as usize).saturating_sub(1)]
    };
    Ok(Statistics {
        p50: percentile(0.5),
        p95: percentile(0.95),
        p99: percentile(0.99),
        min: values.iter().copied().fold(f64::INFINITY, f64::min),
        max: values.iter().copied().fold(f64::NEG_INFINITY, f64::max),
    })
}

fn acceptance_eligible(profile: &str, chunks: u64, warmups: usize, samples: usize) -> bool {
    profile == "full" && chunks >= 100_001 && warmups == MAX_WARMUPS && samples == MAX_SAMPLES
}

fn acceptance_passed(acceptance_eligible: bool, reports: &[ScenarioReport]) -> Option<bool> {
    acceptance_eligible.then(|| {
        reports.len() == SCENARIOS.len()
            && reports
                .iter()
                .all(|report| report.passed_p95_threshold == Some(true))
    })
}

fn parse_response(
    stdout: &str,
    query: &str,
    expected_scope_id: &str,
    expected_path: &str,
    scope_ids: &BTreeSet<String>,
) -> Result<usize, ScaleError> {
    let v: Value = serde_json::from_str(stdout)
        .map_err(|_| ScaleError::Input("search returned invalid JSON".into()))?;
    let o = object(&v, "search response")?;
    if o.get("query").and_then(Value::as_str) != Some(query)
        || o.get("requested_mode").and_then(Value::as_str) != Some("auto")
        || o.get("resolved_mode").and_then(Value::as_str) != Some("text")
        || o.get("fallback") != Some(&Value::Bool(true))
        || o.get("fallback_reason").and_then(Value::as_str)
            != Some("embedding_endpoint_not_configured")
    {
        return Err(ScaleError::Input(
            "scale search did not use auto text fallback".into(),
        ));
    }
    let searched = o
        .get("searched_scopes")
        .and_then(Value::as_array)
        .ok_or_else(|| ScaleError::Input("scale search has no searched_scopes".into()))?;
    if searched.len() != SCOPES.len() || o.get("excluded_scopes") != Some(&Value::Array(Vec::new()))
    {
        return Err(ScaleError::Input(
            "search did not report exactly 20 included scopes".into(),
        ));
    }
    let ids = searched
        .iter()
        .map(|scope| {
            object(scope, "searched scope")?
                .get("scope_id")
                .and_then(Value::as_str)
                .map(ToOwned::to_owned)
                .ok_or_else(|| ScaleError::Input("searched scope has no scope_id".into()))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let got = ids.iter().cloned().collect::<BTreeSet<_>>();
    if got != *scope_ids || got.len() != SCOPES.len() {
        return Err(ScaleError::Input(
            "search scope identities differ from attestation".into(),
        ));
    }
    let results = o
        .get("results")
        .and_then(Value::as_array)
        .filter(|r| !r.is_empty() && r.len() <= RESULT_LIMIT)
        .ok_or_else(|| ScaleError::Input("scale search returned invalid results".into()))?;
    let hit = results.iter().any(|result| {
        result
            .get("evidence_pointer")
            .and_then(Value::as_object)
            .is_some_and(|pointer| {
                pointer.get("scope_id").and_then(Value::as_str) == Some(expected_scope_id)
                    && pointer.get("path_at_commit").and_then(Value::as_str) == Some(expected_path)
            })
    });
    if !hit {
        return Err(ScaleError::Input(
            "scale search did not return the scheduled needle evidence pointer".into(),
        ));
    }
    Ok(results.len())
}

pub fn run(options: ScaleOptions) -> Result<ScaleReport, ScaleError> {
    if options.warmups == 0
        || options.warmups > MAX_WARMUPS
        || options.samples == 0
        || options.samples > MAX_SAMPLES
    {
        return Err(ScaleError::Input(format!(
            "warmups must be 1..={MAX_WARMUPS} and samples must be 1..={MAX_SAMPLES}"
        )));
    }
    let fixture = load_fixture(&options)?;
    let corpus = fixture.corpus.clone();
    let _lock = FixtureLock::acquire(&fixture.root)?;
    attest_live_corpus(&corpus, &_lock.root, &fixture)?;
    let binary = bind_binary(&options.bin)?;
    let snapshot = snapshot_measurement_inputs(&_lock.root, &binary.bytes, &binary.binding)?;
    let snapshot_root = cap_fs::open_ambient_dir(&snapshot.corpus, ambient_authority())
        .map_err(|e| ScaleError::Input(format!("cannot retain private fixture snapshot: {e}")))?;
    attest_live_corpus(&corpus, &snapshot_root, &fixture)?;
    rewrite_snapshot_registry(&snapshot.corpus, &corpus)?;
    let cwd = snapshot.corpus.join(SCOPES[0].0);
    let device = snapshot.corpus.join(".kio-eval-device");
    let logs_handle = cap_fs::open_ambient_dir(&device.join("data/kio/logs"), ambient_authority())
        .map_err(|e| ScaleError::Input(format!("cannot retain private metrics directory: {e}")))?;
    let path = env::var_os("PATH").unwrap_or_else(|| OsString::from("/usr/bin:/bin"));
    let environment = [
        ("PATH", path),
        ("LANG", OsString::from("C.UTF-8")),
        ("LC_ALL", OsString::from("C.UTF-8")),
        ("TZ", OsString::from("UTC")),
        ("HOME", device.join("home").into_os_string()),
        ("XDG_CONFIG_HOME", device.join("config").into_os_string()),
        ("XDG_CACHE_HOME", device.join("cache").into_os_string()),
        ("XDG_DATA_HOME", device.join("data").into_os_string()),
        ("XDG_STATE_HOME", device.join("state").into_os_string()),
        ("XDG_RUNTIME_DIR", device.join("runtime").into_os_string()),
    ];
    let needles = fixture.manifest["needles"].as_array().expect("validated");
    let mut raw_samples = [Vec::new(), Vec::new(), Vec::new()];
    let mut walls = [Vec::new(), Vec::new(), Vec::new()];
    let mut metrics = [Vec::new(), Vec::new(), Vec::new()];
    for (is_sample, count) in [(false, options.warmups), (true, options.samples)] {
        for sequence in 0..count {
            let needle = needles[sequence % needles.len()]
                .as_object()
                .expect("validated");
            let query = needle["query"].as_str().expect("validated");
            let needle_index = sequence % needles.len();
            for (scenario_index, (name, flag, _)) in SCENARIOS.iter().enumerate() {
                let metrics_snapshot = snapshot_metrics_log(&logs_handle)?;
                let mut command = Command::new(&snapshot.bin);
                command.args(["--json", "search", query, "--limit", "10"]);
                if let Some(flag) = flag {
                    command.arg(flag);
                }
                command
                    .current_dir(&cwd)
                    .env_clear()
                    .envs(environment.iter().map(|(k, v)| (*k, v)));
                let output = run_bounded_command(&mut command, BoundedProcessOptions::default())?;
                if !output.status.success() {
                    return Err(ScaleError::Input(format!(
                        "search failed for {name}: {}",
                        output.stderr.trim()
                    )));
                }
                // `scope_ids` is a set only for membership validation.  The
                // scheduled needle itself binds to the attestation's ordered
                // scope record, retained below in `Fixture`.
                let expected_scope_id = fixture.scope_ids_ordered[needle_index].as_str();
                let result_count = parse_response(
                    &output.stdout,
                    query,
                    expected_scope_id,
                    needle["file"].as_str().expect("validated"),
                    &fixture.scope_ids,
                )?;
                let metric = appended_search_metric(metrics_snapshot, result_count)?;
                if is_sample {
                    let wall = output.duration.as_secs_f64() * 1000.0;
                    walls[scenario_index].push(wall);
                    metrics[scenario_index].push(metric);
                    raw_samples[scenario_index].push(Sample {
                        sequence,
                        query_index: sequence % needles.len(),
                        process_wall_duration_ms: wall,
                        kio_search_latency_ms: Some(metric),
                    });
                }
            }
        }
    }
    let mut reports = Vec::new();
    let acceptance_eligible = acceptance_eligible(
        &fixture.profile,
        fixture.chunks,
        options.warmups,
        options.samples,
    );
    for (index, (name, flag, threshold_ms)) in SCENARIOS.iter().enumerate() {
        let wall_stats = stats(&walls[index])?;
        let metric_stats = stats(&metrics[index])?;
        reports.push(ScenarioReport {
            name,
            selector_flag: *flag,
            raw_samples: std::mem::take(&mut raw_samples[index]),
            p95_threshold_ms: acceptance_eligible.then_some(*threshold_ms),
            passed_p95_threshold: acceptance_eligible.then_some(metric_stats.p95 < *threshold_ms),
            process_wall_statistics_ms: wall_stats,
            metric_statistics_ms: Some(metric_stats),
        });
    }
    // Bind the report to the exact artifacts measured, rather than merely the
    // artifacts that happened to be present before the first subprocess.
    let manifest_after_raw = read_regular_at(
        &_lock.root,
        "scale-corpus-manifest.json",
        MAX_MANIFEST_BYTES,
        "scale manifest",
    )?;
    let manifest_after = FileBinding {
        path: corpus
            .join("scale-corpus-manifest.json")
            .display()
            .to_string(),
        sha256: hash_bytes(&manifest_after_raw),
        bytes: manifest_after_raw.len(),
    };
    let attestation_after_raw = read_regular_at(
        &_lock.root,
        "scale-attestation.json",
        MAX_ATTESTATION_BYTES,
        "scale attestation",
    )?;
    let attestation_after = FileBinding {
        path: corpus.join("scale-attestation.json").display().to_string(),
        sha256: hash_bytes(&attestation_after_raw),
        bytes: attestation_after_raw.len(),
    };
    if manifest_after != fixture.manifest_binding
        || attestation_after != fixture.attestation_binding
    {
        return Err(ScaleError::Input(
            "scale input artifact changed during measurement".into(),
        ));
    }
    recheck_bound_binary(&binary)?;
    attest_live_corpus(&corpus, &_lock.root, &fixture)?;
    let passed = acceptance_passed(acceptance_eligible, &reports);
    Ok(ScaleReport {
        schema_version: 1,
        benchmark: "kio-scale-search",
        measurement_class: if acceptance_eligible {
            "full_100k_acceptance"
        } else {
            "tiny_smoke"
        },
        acceptance_eligible,
        passed_p95_thresholds: passed,
        fixture: FixtureBinding {
            manifest: fixture.manifest_binding,
            attestation: fixture.attestation_binding,
            profile: fixture.profile,
            current_eligible_chunks: fixture.chunks,
        },
        binary: binary.binding,
        platform: Platform {
            os: env::consts::OS.into(),
            arch: env::consts::ARCH.into(),
            family: env::consts::FAMILY.into(),
        },
        configuration: Configuration {
            warmups: options.warmups,
            samples: options.samples,
            query_schedule: "manifest-order round-robin, scenarios interleaved",
            result_limit: RESULT_LIMIT,
        },
        scenarios: reports,
    })
}

/// Publish evidence outside the owned corpus.  The report is size-bounded,
/// written through a sibling temporary file, synced, then atomically renamed.
pub fn write_report(path: &Path, corpus: &Path, report: &ScaleReport) -> Result<(), ScaleError> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|e| ScaleError::Input(format!("cannot resolve report path: {e}")))?
            .join(path)
    };
    let root = fs::canonicalize(corpus)
        .map_err(|e| ScaleError::Input(format!("cannot resolve corpus root: {e}")))?;
    let parent = absolute
        .parent()
        .ok_or_else(|| ScaleError::Input("scale report has no parent directory".into()))?;
    let canonical_parent = fs::canonicalize(parent).map_err(|e| {
        ScaleError::Input(format!(
            "scale report parent must already exist and be real: {e}"
        ))
    })?;
    if !canonical_parent.is_dir() || canonical_parent.starts_with(&root) {
        return Err(ScaleError::Input(
            "scale report must resolve outside the owned corpus".into(),
        ));
    }
    let name = absolute.file_name().expect("checked");
    let parent_handle = cap_fs::open_ambient_dir(&canonical_parent, ambient_authority())
        .map_err(|e| ScaleError::Input(format!("cannot retain scale report parent: {e}")))?;
    let retained_parent = cap_fs::Metadata::from_file(&parent_handle).map_err(|e| {
        ScaleError::Input(format!("cannot inspect retained scale report parent: {e}"))
    })?;
    let named_parent = cap_fs::stat(&parent_handle, Path::new("."), cap_fs::FollowSymlinks::No)
        .map_err(|e| ScaleError::Input(format!("cannot recheck scale report parent: {e}")))?;
    if !retained_parent.file_type().is_dir() || !same_file(&retained_parent, &named_parent) {
        return Err(ScaleError::Input(
            "scale report parent changed while retaining it".into(),
        ));
    }
    if let Ok(metadata) = cap_fs::stat(&parent_handle, Path::new(name), cap_fs::FollowSymlinks::No)
    {
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(ScaleError::Input(
                "scale report destination is not a regular file".into(),
            ));
        }
    }
    let bytes = serde_json::to_vec_pretty(report)?;
    if bytes.len() > MAX_REPORT_BYTES {
        return Err(ScaleError::Input("scale report exceeds byte limit".into()));
    }
    let mut temporary = None;
    let mut file = None;
    for _ in 0..16 {
        let candidate = format!(
            ".kio-scale-report-{}-{}",
            std::process::id(),
            REPORT_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        );
        let mut options = cap_fs::OpenOptions::new();
        options.write(true).create_new(true);
        match cap_fs::open(&parent_handle, Path::new(&candidate), &options) {
            Ok(opened) => {
                temporary = Some(candidate);
                file = Some(opened);
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(ScaleError::Input(format!(
                    "cannot create scale report: {error}"
                )))
            }
        }
    }
    let temporary = temporary
        .ok_or_else(|| ScaleError::Input("cannot reserve scale report temporary file".into()))?;
    let mut file = file.expect("reserved temporary file is paired with a handle");
    if let Err(error) = file.write_all(&bytes).and_then(|_| file.sync_all()) {
        let _ = cap_fs::remove_file(&parent_handle, Path::new(&temporary));
        return Err(ScaleError::Input(format!(
            "cannot write scale report: {error}"
        )));
    }
    if let Err(error) = cap_fs::rename(
        &parent_handle,
        Path::new(&temporary),
        &parent_handle,
        Path::new(name),
    ) {
        let _ = cap_fs::remove_file(&parent_handle, Path::new(&temporary));
        return Err(ScaleError::Input(format!(
            "cannot atomically install scale report: {error}"
        )));
    }
    #[cfg(unix)]
    parent_handle
        .sync_all()
        .map_err(|e| ScaleError::Input(format!("cannot sync scale report directory: {e}")))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scenario(name: &'static str, passed_p95_threshold: Option<bool>) -> ScenarioReport {
        ScenarioReport {
            name,
            selector_flag: None,
            raw_samples: Vec::new(),
            process_wall_statistics_ms: stats(&[1.0]).unwrap(),
            metric_statistics_ms: Some(stats(&[1.0]).unwrap()),
            p95_threshold_ms: passed_p95_threshold.map(|_| 5_000.0),
            passed_p95_threshold,
        }
    }

    fn test_report(acceptance_eligible: bool, passed_p95_thresholds: Option<bool>) -> ScaleReport {
        ScaleReport {
            schema_version: 1,
            benchmark: "test",
            measurement_class: "test",
            acceptance_eligible,
            passed_p95_thresholds,
            fixture: FixtureBinding {
                manifest: FileBinding {
                    path: "test".into(),
                    sha256: "test".into(),
                    bytes: 0,
                },
                attestation: FileBinding {
                    path: "test".into(),
                    sha256: "test".into(),
                    bytes: 0,
                },
                profile: "test".into(),
                current_eligible_chunks: 0,
            },
            binary: FileBinding {
                path: "test".into(),
                sha256: "test".into(),
                bytes: 0,
            },
            platform: Platform {
                os: "test".into(),
                arch: "test".into(),
                family: "test".into(),
            },
            configuration: Configuration {
                warmups: 1,
                samples: 1,
                query_schedule: "test",
                result_limit: 1,
            },
            scenarios: Vec::new(),
        }
    }

    #[test]
    fn nearest_rank_statistics_are_stable() {
        let s = stats(&[1.0, 2.0, 3.0, 4.0, 5.0]).unwrap();
        assert_eq!(s.p50, 3.0);
        assert_eq!(s.p95, 5.0);
        assert_eq!(s.p99, 5.0);
    }
    #[test]
    fn bounds_are_strict() {
        let o = ScaleOptions {
            corpus: PathBuf::new(),
            manifest: None,
            attestation: None,
            bin: PathBuf::new(),
            warmups: 6,
            samples: 1,
        };
        assert!(run(o).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn binary_binding_rejects_final_symlink() {
        let root = tempfile::tempdir().unwrap();
        fs::write(root.path().join("real-kio"), b"binary").unwrap();
        std::os::unix::fs::symlink(root.path().join("real-kio"), root.path().join("kio")).unwrap();
        assert!(bind_binary(&root.path().join("kio")).is_err());
    }

    #[test]
    fn only_full_default_measurements_are_acceptance_eligible() {
        assert!(!acceptance_eligible("tiny", 60, 5, 100));
        assert!(!acceptance_eligible("full", 100_000, 5, 100));
        assert!(!acceptance_eligible("full", 120_000, 1, 1));
        assert!(acceptance_eligible("full", 120_000, 5, 100));
    }

    #[test]
    fn acceptance_aggregates_each_scenario_threshold_result() {
        let passing = SCENARIOS
            .iter()
            .map(|(name, _, _)| scenario(name, Some(true)))
            .collect::<Vec<_>>();
        assert_eq!(acceptance_passed(true, &passing), Some(true));

        let failing = vec![
            scenario("M3-1", Some(true)),
            scenario("M3-2", Some(false)),
            scenario("M3-3", Some(true)),
        ];
        assert_eq!(acceptance_passed(true, &failing), Some(false));
        assert_eq!(acceptance_passed(false, &failing), None);
        assert_eq!(acceptance_passed(true, &passing[..2]), Some(false));
    }

    #[test]
    fn tiny_scenario_omits_performance_threshold_fields() {
        let value = serde_json::to_value(scenario("M3-1", None)).unwrap();
        assert!(value.get("p95_threshold_ms").is_none());
        assert!(value.get("passed_p95_threshold").is_none());
    }

    #[test]
    fn acceptance_failure_follows_the_aggregate_and_tiny_omits_it() {
        assert!(test_report(true, Some(false)).acceptance_failed());
        assert!(!test_report(true, Some(true)).acceptance_failed());
        let tiny = test_report(false, None);
        assert!(!tiny.acceptance_failed());
        assert!(serde_json::to_value(tiny)
            .unwrap()
            .get("passed_p95_thresholds")
            .is_none());
    }

    #[test]
    fn strict_schema_field_sets_reject_extra_fields() {
        let mut value = Map::new();
        value.insert("known".into(), Value::Null);
        value.insert("unexpected".into(), Value::Null);
        assert!(exact_keys(&value, &["known"], "fixture").is_err());
    }

    #[test]
    fn frozen_manifest_digest_rejects_self_consistent_forgery() {
        assert!(frozen_manifest_sha256("tiny").is_some());
        assert_ne!(
            frozen_manifest_sha256("tiny"),
            Some("0000000000000000000000000000000000000000000000000000000000000000")
        );
        assert!(frozen_manifest_sha256("forged-profile").is_none());
    }

    #[test]
    fn owner_marker_requires_exact_ready_binding() {
        let root = tempfile::tempdir().unwrap();
        let binding = FileBinding {
            path: "manifest".into(),
            sha256: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                .into(),
            bytes: 1,
        };
        fs::write(
            root.path().join(".kio-scale-owner.json"),
            r#"{"schema_version":1,"owner":"eval/generate_scale_corpus.py","fixture_id":"kio-scale-120k-v1","profile":"tiny","state":"ready","manifest_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}"#,
        )
        .unwrap();
        let handle = cap_fs::open_ambient_dir(root.path(), ambient_authority()).unwrap();
        assert!(validate_owner(&handle, &binding, "tiny").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn private_snapshot_uses_retained_tree_after_public_directory_swap() {
        let parent = tempfile::tempdir().unwrap();
        let public = parent.path().join("fixture");
        fs::create_dir(&public).unwrap();
        fs::write(public.join("payload"), b"attested").unwrap();
        let retained = cap_fs::open_ambient_dir(&public, ambient_authority()).unwrap();
        let moved = parent.path().join("fixture-attested");
        fs::rename(&public, &moved).unwrap();
        fs::create_dir(&public).unwrap();
        fs::write(public.join("payload"), b"substituted").unwrap();
        let snapshot = tempfile::tempdir().unwrap();
        let copied = snapshot.path().join("fixture");
        copy_snapshot_tree(&retained, &copied, &mut SnapshotBudget::default()).unwrap();
        assert_eq!(fs::read(copied.join("payload")).unwrap(), b"attested");
    }

    #[test]
    fn retained_tree_digest_detects_mutation_before_snapshot() {
        let root = tempfile::tempdir().unwrap();
        fs::write(root.path().join("payload"), b"before").unwrap();
        let handle = cap_fs::open_ambient_dir(root.path(), ambient_authority()).unwrap();
        let before = snapshot_tree_digest(&handle).unwrap();
        fs::write(root.path().join("payload"), b"after").unwrap();
        assert_ne!(before, snapshot_tree_digest(&handle).unwrap());
    }

    #[test]
    fn metrics_replacement_is_not_an_append() {
        let root = tempfile::tempdir().unwrap();
        fs::write(root.path().join("metrics.jsonl"), b"{}\n").unwrap();
        let handle = cap_fs::open_ambient_dir(root.path(), ambient_authority()).unwrap();
        let snapshot = snapshot_metrics_log(&handle).unwrap();
        fs::rename(
            root.path().join("metrics.jsonl"),
            root.path().join("metrics.previous"),
        )
        .unwrap();
        fs::write(root.path().join("metrics.jsonl"), b"{}\n").unwrap();
        assert!(appended_search_metric(snapshot, 0).is_err());
    }

    #[test]
    fn response_requires_exact_scope_count_and_scheduled_evidence() {
        let mut ids = BTreeSet::new();
        for index in 0..20 {
            ids.insert(format!("scope-{index}"));
        }
        let searched = (0..20)
            .map(|index| serde_json::json!({"scope_id": format!("scope-{index}")}))
            .collect::<Vec<_>>();
        let response = serde_json::json!({
            "query": "needle", "requested_mode": "auto", "resolved_mode": "text",
            "fallback": true, "fallback_reason": "embedding_endpoint_not_configured",
            "searched_scopes": searched, "excluded_scopes": [],
            "results": [{"evidence_pointer":{"scope_id":"scope-0","path_at_commit":"document-0000.md"}}]
        });
        assert_eq!(
            parse_response(
                &response.to_string(),
                "needle",
                "scope-0",
                "document-0000.md",
                &ids
            )
            .unwrap(),
            1
        );
        let duplicate = response.to_string().replace("scope-19", "scope-18");
        assert!(parse_response(&duplicate, "needle", "scope-0", "document-0000.md", &ids).is_err());
    }

    #[test]
    fn report_rejects_corpus_and_symlink_parent() {
        let corpus = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let report = ScaleReport {
            schema_version: 1,
            benchmark: "x",
            measurement_class: "tiny_smoke",
            acceptance_eligible: false,
            passed_p95_thresholds: None,
            fixture: FixtureBinding {
                manifest: FileBinding {
                    path: "x".into(),
                    sha256: "x".into(),
                    bytes: 0,
                },
                attestation: FileBinding {
                    path: "x".into(),
                    sha256: "x".into(),
                    bytes: 0,
                },
                profile: "tiny".into(),
                current_eligible_chunks: 0,
            },
            binary: FileBinding {
                path: "x".into(),
                sha256: "x".into(),
                bytes: 0,
            },
            platform: Platform {
                os: "x".into(),
                arch: "x".into(),
                family: "x".into(),
            },
            configuration: Configuration {
                warmups: 1,
                samples: 1,
                query_schedule: "x",
                result_limit: 1,
            },
            scenarios: vec![],
        };
        assert!(write_report(&corpus.path().join("report.json"), corpus.path(), &report).is_err());
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(corpus.path(), outside.path().join("escape")).unwrap();
            assert!(write_report(
                &outside.path().join("escape/report.json"),
                corpus.path(),
                &report
            )
            .is_err());
        }
    }

    #[test]
    fn report_accepts_canonicalized_system_temp_parent() {
        let corpus = tempfile::tempdir().unwrap();
        let destination =
            std::env::temp_dir().join(format!("kio-scale-report-test-{}.json", std::process::id()));
        let report = ScaleReport {
            schema_version: 1,
            benchmark: "x",
            measurement_class: "tiny_smoke",
            acceptance_eligible: false,
            passed_p95_thresholds: None,
            fixture: FixtureBinding {
                manifest: FileBinding {
                    path: "x".into(),
                    sha256: "x".into(),
                    bytes: 0,
                },
                attestation: FileBinding {
                    path: "x".into(),
                    sha256: "x".into(),
                    bytes: 0,
                },
                profile: "tiny".into(),
                current_eligible_chunks: 0,
            },
            binary: FileBinding {
                path: "x".into(),
                sha256: "x".into(),
                bytes: 0,
            },
            platform: Platform {
                os: "x".into(),
                arch: "x".into(),
                family: "x".into(),
            },
            configuration: Configuration {
                warmups: 1,
                samples: 1,
                query_schedule: "x",
                result_limit: 1,
            },
            scenarios: vec![],
        };
        write_report(&destination, corpus.path(), &report).unwrap();
        fs::remove_file(destination).unwrap();
    }
}
