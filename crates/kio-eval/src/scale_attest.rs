//! Independent, descriptor-bound attestation for a prepared scale-v2 corpus.
//!
//! This deliberately does not call `ScopeRepository` or the product verifier:
//! mutable projections are evidence only after the immutable CAS graph and the
//! frozen fixture have been checked here.

use crate::{
    scale_fixture::ValidatedFixture,
    scale_spec::{self, SCOPES, ScaleScope},
};
#[cfg(unix)]
use cap_primitives::fs::MetadataExt;
use cap_primitives::{ambient_authority, fs as cap_fs};
use kio_core::cas::{canonical_json_bytes, hash_bytes, is_hash};
use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    str,
};
use thiserror::Error;

const MAX_METADATA: u64 = 1 << 20;
const MAX_CAS: u64 = 64 << 20;
const MAX_LEDGER: u64 = 256 << 20;
const MAX_SQLITE_LEAF: u64 = 512 << 20;
const MAX_SQLITE_TOTAL: u64 = 1024 << 20;
const MAX_ROWS: u64 = 250_000;
const MAX_REGISTRY_ROWS: usize = SCOPES.len() + 1;
const MAX_REPORT_BYTES: usize = 1024 * 1024;
const REPORT_TEMP_PREFIX: &str = ".kio-scale-attest-v2.tmp-";

const INDEX_SQL_FINGERPRINTS: &[(&str, &str)] = &[
    (
        "idx_chunk_publications_chunk_id",
        "CREATE INDEX idx_chunk_publications_chunk_id ON chunk_publications(chunk_id)",
    ),
    (
        "idx_chunks_ident",
        "CREATE INDEX idx_chunks_ident ON chunks(raw_hash, tool_profile_hash, gen, unit_key, unit_content_hash)",
    ),
    (
        "idx_embeddings_type",
        "CREATE INDEX idx_embeddings_type ON embeddings(target_type)",
    ),
    (
        "idx_tree_entries_ident",
        "CREATE INDEX idx_tree_entries_ident ON tree_entries(commit_hash, raw_hash, tool_profile_hash, gen)",
    ),
    (
        "chunks_ai",
        "CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN INSERT INTO chunk_fts(rowid, text, heading_path) VALUES (new.rowid, new.text, new.heading_path); END",
    ),
    (
        "chunks_ad",
        "CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path) VALUES ('delete', old.rowid, old.text, old.heading_path); END",
    ),
    (
        "chunks_au",
        "CREATE TRIGGER chunks_au AFTER UPDATE OF text, heading_path ON chunks BEGIN INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path) VALUES ('delete', old.rowid, old.text, old.heading_path); INSERT INTO chunk_fts(rowid, text, heading_path) VALUES (new.rowid, new.text, new.heading_path); END",
    ),
    (
        "chunk_fts",
        "CREATE VIRTUAL TABLE chunk_fts USING fts5(text, heading_path, content='chunks', content_rowid='rowid', tokenize='trigram')",
    ),
    (
        "chunk_vec",
        "CREATE VIRTUAL TABLE chunk_vec USING vec0(chunk_id TEXT PRIMARY KEY, embedding float[768] distance_metric=cosine)",
    ),
    (
        "image_vec",
        "CREATE VIRTUAL TABLE image_vec USING vec0(image_id TEXT PRIMARY KEY, embedding float[768] distance_metric=cosine)",
    ),
];
const TABLE_SQL_FINGERPRINTS: &[(&str, &str)] = &[
    (
        "chunks",
        "CREATE TABLE chunks (chunk_id TEXT NOT NULL PRIMARY KEY, raw_hash TEXT NOT NULL, tool_profile_hash TEXT NOT NULL, gen INTEGER NOT NULL, unit_key TEXT NOT NULL, unit_content_hash TEXT NOT NULL CHECK (length(unit_content_hash) = 71 AND substr(unit_content_hash, 1, 7) = 'sha256:' AND substr(unit_content_hash, 8) NOT GLOB '*[^0-9a-f]*'), raw_path TEXT NOT NULL, heading_path TEXT NOT NULL, section_id TEXT, byte_start INTEGER NOT NULL, byte_end INTEGER NOT NULL, text_hash TEXT NOT NULL, text TEXT NOT NULL, first_seen_commit TEXT, created_at TEXT NOT NULL)",
    ),
    (
        "chunk_config_generations",
        "CREATE TABLE chunk_config_generations (association_rowid INTEGER PRIMARY KEY AUTOINCREMENT, chunk_id TEXT NOT NULL, chunking_config_hash TEXT NOT NULL, created_at TEXT NOT NULL, introduction_commit TEXT NOT NULL, UNIQUE(chunk_id, chunking_config_hash, introduction_commit))",
    ),
    (
        "chunk_publications",
        "CREATE TABLE chunk_publications (publication_rowid INTEGER PRIMARY KEY AUTOINCREMENT, chunk_id TEXT NOT NULL, introduction_commit TEXT NOT NULL, UNIQUE(chunk_id, introduction_commit))",
    ),
    (
        "embeddings",
        "CREATE TABLE embeddings (id TEXT NOT NULL PRIMARY KEY, target_type TEXT NOT NULL, target_id TEXT NOT NULL, modality TEXT NOT NULL, vector BLOB NOT NULL, dimensions INTEGER NOT NULL, distance TEXT NOT NULL, profile_hash TEXT NOT NULL, context_key TEXT)",
    ),
    (
        "tree_entries",
        "CREATE TABLE tree_entries (commit_hash TEXT NOT NULL, path TEXT NOT NULL, raw_hash TEXT NOT NULL, tool_profile_hash TEXT, gen INTEGER, manifest_hash TEXT, PRIMARY KEY (commit_hash, path))",
    ),
    (
        "index_metadata",
        "CREATE TABLE index_metadata (id INTEGER PRIMARY KEY CHECK (id = 1), index_generation TEXT NOT NULL, last_lifecycle_epoch INTEGER NOT NULL DEFAULT 0)",
    ),
];
const REGISTRY_SCOPES_SQL: &str = "CREATE TABLE scopes (scope_id TEXT NOT NULL, kio_path TEXT NOT NULL, root_path TEXT NOT NULL, participates_in_global_search INTEGER NOT NULL DEFAULT 1, indexed INTEGER NOT NULL DEFAULT 0, last_seen_at TEXT NOT NULL, PRIMARY KEY (scope_id, kio_path))";

#[derive(Debug, Clone)]
struct SqliteSource {
    name: String,
    observation: FileObservation,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct LeafIdentity {
    #[cfg(unix)]
    dev: u64,
    #[cfg(unix)]
    ino: u64,
    #[cfg(windows)]
    volume: Option<u32>,
    #[cfg(windows)]
    index: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FileObservation {
    identity: LeafIdentity,
    bytes: u64,
    sha256: String,
}

#[derive(Debug)]
struct BoundRegular {
    parent: fs::File,
    name: String,
    max: u64,
    label: String,
    observation: FileObservation,
}

impl BoundRegular {
    fn recheck(&self) -> Result<(), AttestError> {
        let (_, current) = observed_regular(&self.parent, &self.name, self.max, &self.label)
            .map_err(corruption)?;
        if current != self.observation {
            return Err(unsafe_state(format!(
                "{} changed during attestation",
                self.label
            )));
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
struct CasBinding {
    kind: String,
    hash: String,
    observation: FileObservation,
}

#[derive(Debug, Error)]
pub enum AttestError {
    /// The fixture is valid but has not yet been completely prepared.  Callers
    /// may resume preparation, but must never treat this as a no-op.
    #[error("scale corpus is incomplete: {0}")]
    Incomplete(String),
    /// Existing state is unsafe/corrupt and must not be repaired implicitly.
    #[error("scale corpus is unsafe or corrupt: {0}")]
    Unsafe(String),
    #[error("scale fixture binding failed: {0}")]
    Fixture(#[from] crate::scale_fixture::ScaleFixtureError),
    #[error("scale attestation publication outcome is indeterminate: {0}")]
    Indeterminate(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScopeEvidence {
    pub name: String,
    pub scope_id: String,
    pub head: String,
    pub source_files: usize,
    pub current_chunks: u64,
    pub physical_chunks: u64,
    pub embedded_chunks: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CorpusEvidence {
    pub scopes: Vec<ScopeEvidence>,
    pub registry_rows: usize,
    pub current_chunks: u64,
}

/// The only public product of the independent scale attestor.  It is an
/// exact, current-v2 receipt rather than a compatibility envelope.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AttestationReport {
    pub schema_version: u64,
    pub attestor: String,
    pub fixture_id: String,
    pub profile: scale_spec::ScaleProfile,
    pub manifest_hash: String,
    pub content_root_hash: String,
    pub corpus: String,
    pub scopes: Vec<ScopeEvidence>,
    pub registry_rows: usize,
    pub current_chunks: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AttestationSummary {
    pub corpus: PathBuf,
    pub report: PathBuf,
    pub scopes: usize,
    pub current_chunks: u64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ScopeIdentity {
    kio_format_version: String,
    scope_id: String,
    scope_path: String,
    scan_approval: ScanApproval,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ScanApproval {
    scope_id: String,
    root_path: String,
    approved_at: String,
    actor: String,
    approval_method: String,
    kio_version: String,
    effective_ignore_hash: String,
    estimated_file_count: usize,
    estimated_total_bytes: usize,
    estimated_markdownize_usd: f64,
    estimated_embedding_usd: f64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct LedgerRow {
    rowid: u64,
    association_rowid: u64,
    #[serde(flatten)]
    row: LedgerChunk,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct LedgerChunk {
    chunk_id: String,
    raw_hash: String,
    tool_profile_hash: String,
    r#gen: u64,
    unit_key: String,
    unit_content_hash: String,
    chunking_config_hash: String,
    raw_path: String,
    heading_path: Option<Vec<String>>,
    section_id: Option<String>,
    byte_start: u64,
    byte_end: u64,
    text_hash: String,
    text: String,
    first_seen_commit: Option<String>,
    chunking_config_introduction_commit: String,
    created_at: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct PublicationEvent {
    event: String,
    chunk_id: String,
    chunking_config_hash: String,
    introduction_commit: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CommitWire {
    commit_type: String,
    created_at: String,
    message: String,
    object_type: String,
    parents: Vec<String>,
    stats: StatsWire,
    tool_lock_hash: String,
    tree: String,
    #[serde(default)]
    purged_raws: Vec<String>,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct StatsWire {
    files_added: u64,
    files_modified: u64,
    files_deleted: u64,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TreeWire {
    entries: Vec<TreeEntryWire>,
    object_type: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TreeEntryWire {
    path: String,
    #[serde(rename = "type")]
    entry_type: String,
    raw_hash: String,
    normalize: Option<NormalizeWire>,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NormalizeWire {
    tool_profile_hash: String,
    r#gen: u64,
    manifest_hash: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NormalizedManifestWire {
    raw_hash: String,
    tool_profile_hash: String,
    r#gen: u64,
    parent_gen: Option<u64>,
    run_id: String,
    units: Vec<NormalizedUnitEntryWire>,
    generated_at: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NormalizedUnitEntryWire {
    order: u64,
    unit_key: String,
    unit_ref: String,
    unit_type: String,
    status: String,
    prepared_hash: String,
    unit_object_hash: Option<String>,
    error_kind: Option<String>,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NormalizedUnitWire {
    unit_key: String,
    unit_type: String,
    raw_hash: String,
    prepared_hash: String,
    tool_profile_hash: String,
    r#gen: u64,
    mode: String,
    markdown: String,
    metadata: std::collections::BTreeMap<String, serde_json::Value>,
    reused_from: Option<ReusedWire>,
    generated_at: String,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ReusedWire {
    raw_hash: String,
    r#gen: u64,
    unit_key: String,
}

#[derive(Debug, Clone)]
struct NormalizedUnitEvidence {
    content_hash: String,
    markdown: String,
}

#[derive(Debug, Clone)]
struct NormalizedSourceEvidence {
    tool_profile_hash: String,
    r#gen: u64,
    manifest_hash: String,
    units: BTreeMap<String, NormalizedUnitEvidence>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct ChunkEvidence {
    rowid: u64,
    association_rowid: u64,
    chunk_id: String,
    raw_hash: String,
    tool_profile_hash: String,
    r#gen: u64,
    unit_key: String,
    unit_content_hash: String,
    raw_path: String,
    heading_path: Vec<String>,
    section_id: Option<String>,
    byte_start: u64,
    byte_end: u64,
    text_hash: String,
    text: String,
    first_seen_commit: String,
    created_at: String,
}

#[derive(Debug)]
struct DbChunkRow {
    rowid: u64,
    chunk_id: String,
    raw_hash: String,
    tool_profile_hash: String,
    r#gen: u64,
    unit_key: String,
    unit_content_hash: String,
    raw_path: String,
    heading_path: String,
    section_id: Option<String>,
    byte_start: u64,
    byte_end: u64,
    text_hash: String,
    text: String,
    first_seen_commit: Option<String>,
    created_at: String,
}

fn incomplete(msg: impl Into<String>) -> AttestError {
    AttestError::Incomplete(msg.into())
}
fn unsafe_state(msg: impl Into<String>) -> AttestError {
    AttestError::Unsafe(msg.into())
}
fn other<E: std::fmt::Display>(label: &str, e: E) -> AttestError {
    unsafe_state(format!("{label}: {e}"))
}

fn corruption(error: AttestError) -> AttestError {
    match error {
        AttestError::Incomplete(message) => AttestError::Unsafe(message),
        other => other,
    }
}

fn leaf_identity(metadata: &cap_fs::Metadata) -> LeafIdentity {
    #[cfg(unix)]
    {
        LeafIdentity {
            dev: metadata.dev(),
            ino: metadata.ino(),
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        LeafIdentity {
            volume: metadata.volume_serial_number(),
            index: metadata.file_index(),
        }
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = metadata;
        LeafIdentity {}
    }
}

fn same(a: &cap_fs::Metadata, b: &cap_fs::Metadata) -> bool {
    #[cfg(unix)]
    {
        return a.dev() == b.dev() && a.ino() == b.ino();
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        return a.volume_serial_number() == b.volume_serial_number()
            && a.file_index() == b.file_index();
    }
    #[allow(unreachable_code)]
    false
}

fn dir(parent: &fs::File, name: &str, label: &str) -> Result<fs::File, AttestError> {
    cap_fs::open_dir_nofollow(parent, Path::new(name))
        .map_err(|e| incomplete(format!("{label} missing: {e}")))
}

fn required_dir(parent: &fs::File, name: &str, label: &str) -> Result<fs::File, AttestError> {
    let m = cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No)
        .map_err(|e| incomplete(format!("{label} missing: {e}")))?;
    if !m.is_dir() || m.file_type().is_symlink() {
        return Err(unsafe_state(format!("{label} must be a real directory")));
    }
    let opened = dir(parent, name, label)?;
    let after = cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No)
        .map_err(|e| other(label, e))?;
    if !same(&m, &after) {
        return Err(unsafe_state(format!("{label} changed while opening")));
    }
    Ok(opened)
}

fn observed_regular(
    parent: &fs::File,
    name: &str,
    max: u64,
    label: &str,
) -> Result<(Vec<u8>, FileObservation), AttestError> {
    let before = cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No)
        .map_err(|e| incomplete(format!("{label} missing: {e}")))?;
    if !before.is_file() || before.file_type().is_symlink() || before.len() > max {
        return Err(unsafe_state(format!(
            "{label} must be a bounded regular file"
        )));
    }
    #[cfg(unix)]
    {
        if before.nlink() != 1 {
            return Err(unsafe_state(format!(
                "{label} must have exactly one hard link"
            )));
        }
    }
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let f = cap_fs::open(parent, Path::new(name), &options).map_err(|e| other(label, e))?;
    let opened = cap_fs::Metadata::from_file(&f).map_err(|e| other(label, e))?;
    let mut bytes = Vec::with_capacity(usize::try_from(opened.len()).unwrap_or(0));
    f.take(max + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| other(label, e))?;
    let after = cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No)
        .map_err(|e| other(label, e))?;
    if !opened.is_file()
        || opened.len() != bytes.len() as u64
        || !same(&before, &opened)
        || !same(&opened, &after)
    {
        return Err(unsafe_state(format!("{label} changed while reading")));
    }
    let observation = FileObservation {
        identity: leaf_identity(&opened),
        bytes: opened.len(),
        sha256: hash_bytes(&bytes),
    };
    Ok((bytes, observation))
}

fn regular(parent: &fs::File, name: &str, max: u64, label: &str) -> Result<Vec<u8>, AttestError> {
    observed_regular(parent, name, max, label).map(|(bytes, _)| bytes)
}

fn bind_regular(
    parent: &fs::File,
    name: &str,
    max: u64,
    label: &str,
) -> Result<(Vec<u8>, BoundRegular), AttestError> {
    let (bytes, observation) = observed_regular(parent, name, max, label)?;
    Ok((
        bytes,
        BoundRegular {
            parent: parent.try_clone().map_err(|error| other(label, error))?,
            name: name.to_owned(),
            max,
            label: label.to_owned(),
            observation,
        },
    ))
}

fn unchanged(
    parent: &fs::File,
    name: &str,
    before: &cap_fs::Metadata,
    label: &str,
) -> Result<(), AttestError> {
    let after = cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No)
        .map_err(|e| other(label, e))?;
    if !same(before, &after) {
        return Err(unsafe_state(format!("{label} changed during attestation")));
    }
    Ok(())
}

fn direct_names(
    parent: &fs::File,
    limit: usize,
    label: &str,
) -> Result<BTreeSet<String>, AttestError> {
    cap_fs::read_dir(parent, Path::new("."))
        .map_err(|error| other(label, error))?
        .take(limit + 1)
        .map(|entry| {
            let entry = entry.map_err(|error| other(label, error))?;
            entry
                .file_name()
                .to_str()
                .map(str::to_owned)
                .ok_or_else(|| unsafe_state(format!("{label} contains a non-UTF-8 entry")))
        })
        .collect()
}

fn exact_json<T: for<'a> Deserialize<'a>>(bytes: &[u8], label: &str) -> Result<T, AttestError> {
    let v: serde_json::Value = serde_json::from_slice(bytes)
        .map_err(|e| unsafe_state(format!("{label} invalid JSON: {e}")))?;
    let canonical = canonical_json_bytes(&v)
        .map_err(|e| unsafe_state(format!("{label} cannot canonicalize: {e}")))?;
    if bytes != canonical {
        return Err(unsafe_state(format!("{label} must be canonical JCS")));
    }
    serde_json::from_value(v).map_err(|e| unsafe_state(format!("{label} schema: {e}")))
}

fn typed_json<T: for<'a> Deserialize<'a>>(bytes: &[u8], label: &str) -> Result<T, AttestError> {
    serde_json::from_slice(bytes).map_err(|e| unsafe_state(format!("{label} schema: {e}")))
}

enum LedgerRecord {
    Creation(Box<LedgerRow>),
    Publication(PublicationEvent),
}

fn strict_ledger_row(bytes: &[u8]) -> Result<LedgerRecord, AttestError> {
    let value: serde_json::Value = serde_json::from_slice(bytes)
        .map_err(|e| unsafe_state(format!("chunks ledger row invalid JSON: {e}")))?;
    let object = value
        .as_object()
        .ok_or_else(|| unsafe_state("chunks ledger row must be an object"))?;
    if object.contains_key("event") {
        let expected: BTreeSet<&str> = [
            "event",
            "chunk_id",
            "chunking_config_hash",
            "introduction_commit",
        ]
        .into_iter()
        .collect();
        if object.len() != expected.len()
            || object.keys().any(|key| !expected.contains(key.as_str()))
        {
            return Err(unsafe_state(
                "publication event has unknown or missing fields",
            ));
        }
        let event: PublicationEvent = serde_json::from_value(value)
            .map_err(|e| unsafe_state(format!("publication event schema: {e}")))?;
        if event.event != "publication"
            || !is_hash(&event.chunk_id)
            || !is_hash(&event.chunking_config_hash)
            || !is_hash(&event.introduction_commit)
        {
            return Err(unsafe_state("invalid publication event"));
        }
        return Ok(LedgerRecord::Publication(event));
    }
    let expected: BTreeSet<&str> = [
        "rowid",
        "association_rowid",
        "chunk_id",
        "raw_hash",
        "tool_profile_hash",
        "gen",
        "unit_key",
        "unit_content_hash",
        "chunking_config_hash",
        "raw_path",
        "heading_path",
        "section_id",
        "byte_start",
        "byte_end",
        "text_hash",
        "text",
        "first_seen_commit",
        "chunking_config_introduction_commit",
        "created_at",
    ]
    .into_iter()
    .collect();
    if object.len() != expected.len() || object.keys().any(|key| !expected.contains(key.as_str())) {
        return Err(unsafe_state(
            "chunks ledger row has unknown or missing fields",
        ));
    }
    let row: LedgerRow = serde_json::from_value(value)
        .map_err(|e| unsafe_state(format!("chunks ledger row schema: {e}")))?;
    Ok(LedgerRecord::Creation(Box::new(row)))
}

fn hash_leaf(hash: &str) -> Result<(&str, &str, &str), AttestError> {
    if !is_hash(hash) {
        return Err(unsafe_state("invalid CAS hash"));
    }
    let digest = hash.strip_prefix("sha256:").expect("is_hash has prefix");
    Ok((&digest[..2], &digest[2..4], digest))
}

fn observe_cas(
    parent: &fs::File,
    kind: &str,
    hash: &str,
    label: &str,
) -> Result<(Vec<u8>, FileObservation), AttestError> {
    let (a, b, leaf) = hash_leaf(hash)?;
    let objects = required_dir(parent, "objects", "CAS objects")?;
    let kind = required_dir(&objects, kind, "CAS kind")?;
    let a = required_dir(&kind, a, "CAS fanout")?;
    let b = required_dir(&a, b, "CAS fanout")?;
    let (bytes, observation) = observed_regular(&b, leaf, MAX_CAS, label)?;
    if hash_bytes(&bytes) != hash {
        return Err(unsafe_state(format!("{label} hash mismatch")));
    }
    Ok((bytes, observation))
}

fn cas(
    parent: &fs::File,
    kind: &str,
    hash: &str,
    label: &str,
    bindings: &mut Vec<CasBinding>,
) -> Result<Vec<u8>, AttestError> {
    let (bytes, observation) = observe_cas(parent, kind, hash, label)?;
    bindings.push(CasBinding {
        kind: kind.to_owned(),
        hash: hash.to_owned(),
        observation,
    });
    Ok(bytes)
}

fn recheck_cas(parent: &fs::File, bindings: &[CasBinding]) -> Result<(), AttestError> {
    for binding in bindings {
        let (_, observation) =
            observe_cas(parent, &binding.kind, &binding.hash, "attested CAS object")
                .map_err(corruption)?;
        if observation != binding.observation {
            return Err(unsafe_state("CAS object changed during attestation"));
        }
    }
    Ok(())
}

fn no_runtime(kio: &fs::File) -> Result<(), AttestError> {
    for path in [
        ["tombstones"].as_slice(),
        ["purge", "erase-receipts"].as_slice(),
        ["purge", "in-progress.json"].as_slice(),
    ] {
        let mut at = kio.try_clone().map_err(|e| other("runtime", e))?;
        let mut present = true;
        for (i, part) in path.iter().enumerate() {
            let m = match cap_fs::stat(&at, Path::new(part), cap_fs::FollowSymlinks::No) {
                Ok(m) => m,
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                    present = false;
                    break;
                }
                Err(e) => return Err(other("runtime", e)),
            };
            if i + 1 == path.len() {
                if m.is_file() || m.is_dir() {
                    return Err(unsafe_state(
                        "prepared scope has purge/deletion runtime state",
                    ));
                }
            } else {
                if !m.is_dir() || m.file_type().is_symlink() {
                    return Err(unsafe_state("runtime path is unsafe"));
                }
                at = dir(&at, part, "runtime")?;
            }
        }
        if present {
            return Err(unsafe_state("prepared scope has destructive runtime state"));
        }
    }
    Ok(())
}

fn check_config(kio: &fs::File) -> Result<BoundRegular, AttestError> {
    let (raw, binding) = bind_regular(kio, "config.toml", MAX_METADATA, "scope config")?;
    if !raw.is_empty() {
        return Err(unsafe_state(
            "scale-v2 scope config.toml must be exactly empty",
        ));
    }
    Ok(binding)
}

fn attest_cas(
    kio: &fs::File,
    head: &str,
    scope: &ScaleScope,
    bindings: &mut Vec<CasBinding>,
) -> Result<BTreeMap<String, NormalizedSourceEvidence>, AttestError> {
    let commit_bytes = cas(kio, "commits", head, "HEAD commit", bindings)?;
    let commit: CommitWire = exact_json(&commit_bytes, "HEAD commit")?;
    if commit.object_type != "commit"
        || commit.commit_type != "auto"
        || !is_hash(&commit.tree)
        || !is_hash(&commit.tool_lock_hash)
        || commit.parents.len() > 64
        || commit.created_at.len() < 20
        || commit.message.is_empty()
        || !commit.purged_raws.is_empty()
        || commit.stats.files_added > 1_000_000
        || commit.stats.files_modified > 1_000_000
        || commit.stats.files_deleted > 1_000_000
        || commit.parents.iter().any(|h| !is_hash(h))
    {
        return Err(unsafe_state(
            "HEAD commit violates current auto-commit contract",
        ));
    }
    if commit.commit_type != "auto" {
        return Err(unsafe_state("scale commit_type must be auto"));
    }
    let tree_bytes = cas(kio, "trees", &commit.tree, "HEAD tree", bindings)?;
    let tree: TreeWire = exact_json(&tree_bytes, "HEAD tree")?;
    if tree.object_type != "tree"
        || tree.entries.len() > 10_000
        || tree
            .entries
            .windows(2)
            .any(|v| v[0].path.as_bytes() >= v[1].path.as_bytes())
    {
        return Err(unsafe_state("HEAD tree violates current tree contract"));
    }
    if tree.entries.len() != scope.files.len() {
        return Err(unsafe_state("HEAD tree cardinality differs from manifest"));
    }
    let mut normalized_sources = BTreeMap::new();
    for (entry, expected) in tree.entries.iter().zip(&scope.files) {
        if entry.path != expected.path
            || entry.entry_type != "file"
            || entry.path.is_empty()
            || entry.path.contains('/')
            || entry.path.contains('\0')
            || !is_hash(&entry.raw_hash)
            || entry.raw_hash != expected.raw_hash
            || entry.normalize.is_none()
        {
            return Err(unsafe_state(
                "HEAD tree differs from manifest or lacks normalize reference",
            ));
        }
        let normalize = entry.normalize.as_ref().expect("checked");
        let manifest = cas(
            kio,
            "manifests",
            &normalize.manifest_hash,
            "normalized-instance manifest",
            bindings,
        )?;
        let normalized: NormalizedManifestWire =
            exact_json(&manifest, "normalized-instance manifest")?;
        let normalized_evidence = attest_normalize(
            kio,
            &normalized,
            &entry.raw_hash,
            normalize,
            &entry.path,
            bindings,
        )?;
        if normalized_sources
            .insert(entry.raw_hash.clone(), normalized_evidence)
            .is_some()
        {
            return Err(unsafe_state("duplicate normalized source identity"));
        }
        let raw = cas(kio, "raw", &entry.raw_hash, "HEAD raw object", bindings)?;
        if raw.len() != expected.bytes || hash_bytes(&raw) != expected.raw_hash {
            return Err(unsafe_state("HEAD raw object differs from manifest"));
        }
    }
    Ok(normalized_sources)
}

fn attest_normalize(
    kio: &fs::File,
    manifest: &NormalizedManifestWire,
    raw_hash: &str,
    reference: &NormalizeWire,
    path: &str,
    bindings: &mut Vec<CasBinding>,
) -> Result<NormalizedSourceEvidence, AttestError> {
    if manifest.raw_hash != raw_hash
        || manifest.tool_profile_hash != reference.tool_profile_hash
        || manifest.r#gen != reference.r#gen
        || !is_hash(&manifest.raw_hash)
        || !is_hash(&manifest.tool_profile_hash)
        || manifest.run_id.is_empty()
        || manifest.generated_at.len() < 20
        || manifest.units.is_empty()
        || manifest
            .parent_gen
            .is_some_and(|parent| parent >= manifest.r#gen)
    {
        return Err(unsafe_state(
            "normalized manifest identity differs from tree reference",
        ));
    }
    let mut prior = None;
    let mut units = BTreeMap::new();
    for unit in &manifest.units {
        if prior.is_some_and(|last| last >= unit.order)
            || unit.unit_key.is_empty()
            || unit.unit_ref != unit_ref(&unit.unit_key)
            || !is_hash(&unit.prepared_hash)
            || unit.unit_type != "file"
            || !matches!(unit.status.as_str(), "done" | "failed")
            || unit.error_kind.as_ref().is_some_and(String::is_empty)
        {
            return Err(unsafe_state("normalized manifest unit schema is invalid"));
        }
        prior = Some(unit.order);
        match (&unit.status, &unit.unit_object_hash) {
            (status, Some(hash)) if status == "done" && is_hash(hash) => {
                let bytes = cas(
                    kio,
                    "normalized_unit_objects",
                    hash,
                    "normalized unit",
                    bindings,
                )?;
                let object: NormalizedUnitWire = exact_json(&bytes, "normalized unit")?;
                if object.unit_key != unit.unit_key
                    || object.unit_type != unit.unit_type
                    || object.raw_hash != *raw_hash
                    || object.prepared_hash != unit.prepared_hash
                    || object.tool_profile_hash != reference.tool_profile_hash
                    || object.r#gen != reference.r#gen
                {
                    return Err(unsafe_state(
                        "normalized unit identity differs from current normalized instance",
                    ));
                }
                if object.markdown.is_empty() {
                    return Err(unsafe_state("normalized unit markdown must not be empty"));
                }
                if object.generated_at.len() < 20
                    || object.mode != "full"
                    || object.metadata.len() > 256
                    || object.reused_from.as_ref().is_some_and(|r| {
                        !is_hash(&r.raw_hash) || r.unit_key.is_empty() || r.r#gen > object.r#gen
                    })
                {
                    return Err(unsafe_state(
                        "normalized unit metadata violates the current contract",
                    ));
                }
                if units
                    .insert(
                        object.unit_key,
                        NormalizedUnitEvidence {
                            content_hash: hash_bytes(object.markdown.as_bytes()),
                            markdown: object.markdown,
                        },
                    )
                    .is_some()
                {
                    return Err(unsafe_state("duplicate normalized unit key"));
                }
            }
            (status, None) if status == "failed" => {}
            _ => {
                return Err(unsafe_state(
                    "normalized manifest done/failed pin is invalid",
                ));
            }
        }
    }
    if !path.ends_with(".md") {
        return Err(unsafe_state(
            "normalized tree path is not a scale markdown source",
        ));
    }
    if units.len() != manifest.units.len() {
        return Err(unsafe_state(
            "scale normalized manifest contains a failed unit",
        ));
    }
    Ok(NormalizedSourceEvidence {
        tool_profile_hash: reference.tool_profile_hash.clone(),
        r#gen: reference.r#gen,
        manifest_hash: reference.manifest_hash.clone(),
        units,
    })
}

fn unit_ref(unit_key: &str) -> String {
    let digest = hash_bytes(unit_key.as_bytes());
    digest["sha256:".len()..][..16].to_owned()
}

fn attest_ledger(
    index: &fs::File,
    head: &str,
    scope: &ScaleScope,
    normalized: &BTreeMap<String, NormalizedSourceEvidence>,
) -> Result<(Vec<ChunkEvidence>, BoundRegular), AttestError> {
    let (bytes, binding) = bind_regular(index, "chunks.jsonl", MAX_LEDGER, "chunks ledger")?;
    if !bytes.ends_with(b"\n") {
        return Err(unsafe_state("chunks ledger is not newline terminated"));
    }
    let mut counts: BTreeMap<&str, u64> = scope
        .files
        .iter()
        .map(|f| (f.raw_hash.as_str(), 0))
        .collect();
    let mut rows = 0u64;
    let mut associations = BTreeSet::new();
    let mut publications = BTreeSet::new();
    let mut chunks = BTreeMap::new();
    for line in bytes.split_inclusive(|b| *b == b'\n') {
        let line = &line[..line.len() - 1];
        if line.is_empty() {
            return Err(unsafe_state("chunks ledger has empty record"));
        }
        match strict_ledger_row(line)? {
            LedgerRecord::Publication(event) => {
                if !publications.insert((
                    event.chunk_id,
                    event.chunking_config_hash,
                    event.introduction_commit,
                )) {
                    return Err(unsafe_state("duplicate publication event"));
                }
            }
            LedgerRecord::Creation(row) => {
                let expected_source = scope
                    .files
                    .iter()
                    .find(|source| source.path == row.row.raw_path);
                let normalized_source = normalized.get(&row.row.raw_hash);
                let normalized_unit =
                    normalized_source.and_then(|source| source.units.get(&row.row.unit_key));
                let text_range = usize::try_from(row.row.byte_start)
                    .ok()
                    .zip(usize::try_from(row.row.byte_end).ok());
                let text_matches_normalized =
                    text_range
                        .zip(normalized_unit)
                        .is_some_and(|((start, end), unit)| {
                            start <= end
                                && end <= unit.markdown.len()
                                && unit.markdown.is_char_boundary(start)
                                && unit.markdown.is_char_boundary(end)
                                && unit.markdown.get(start..end) == Some(row.row.text.as_str())
                        });
                if row.rowid == 0
                    || row.association_rowid == 0
                    || !is_hash(&row.row.chunk_id)
                    || !is_hash(&row.row.raw_hash)
                    || !is_hash(&row.row.tool_profile_hash)
                    || !is_hash(&row.row.unit_content_hash)
                    || !is_hash(&row.row.text_hash)
                    || !is_hash(&row.row.chunking_config_introduction_commit)
                    || row.row.chunking_config_hash != scale_spec::CHUNKING_CONFIG_HASH
                    || row.row.first_seen_commit.as_deref() != Some(head)
                    || row.row.chunking_config_introduction_commit != head
                    || row.row.unit_key.is_empty()
                    || row.row.raw_path.is_empty()
                    || row.row.r#gen != 0
                    || row.row.heading_path.as_ref().is_some_and(|headings| {
                        headings.is_empty()
                            || headings.len() > 64
                            || headings.iter().any(String::is_empty)
                    })
                    || row.row.section_id.as_ref().is_some_and(String::is_empty)
                    || row.row.created_at.len() < 20
                    || row.row.byte_start > row.row.byte_end
                    || hash_bytes(row.row.text.as_bytes()) != row.row.text_hash
                    || !counts.contains_key(row.row.raw_hash.as_str())
                    || expected_source.is_none_or(|source| source.raw_hash != row.row.raw_hash)
                    || normalized_source.is_none_or(|source| {
                        source.tool_profile_hash != row.row.tool_profile_hash
                            || source.r#gen != row.row.r#gen
                    })
                    || normalized_unit
                        .is_none_or(|unit| unit.content_hash != row.row.unit_content_hash)
                    || !text_matches_normalized
                    || chunk_identity(&row.row)? != row.row.chunk_id
                {
                    return Err(unsafe_state(
                        "chunks ledger record is not a current scale chunk",
                    ));
                }
                if !associations.insert((
                    row.row.chunk_id.clone(),
                    row.row.chunking_config_hash.clone(),
                )) {
                    return Err(unsafe_state("duplicate chunk/config association"));
                }
                *counts.get_mut(row.row.raw_hash.as_str()).expect("checked") += 1;
                let evidence = ChunkEvidence {
                    rowid: row.rowid,
                    association_rowid: row.association_rowid,
                    chunk_id: row.row.chunk_id.clone(),
                    raw_hash: row.row.raw_hash.clone(),
                    tool_profile_hash: row.row.tool_profile_hash.clone(),
                    r#gen: row.row.r#gen,
                    unit_key: row.row.unit_key.clone(),
                    unit_content_hash: row.row.unit_content_hash.clone(),
                    raw_path: row.row.raw_path.clone(),
                    heading_path: row.row.heading_path.clone().unwrap_or_default(),
                    section_id: row.row.section_id.clone(),
                    byte_start: row.row.byte_start,
                    byte_end: row.row.byte_end,
                    text_hash: row.row.text_hash.clone(),
                    text: row.row.text.clone(),
                    first_seen_commit: head.to_owned(),
                    created_at: row.row.created_at.clone(),
                };
                if chunks.insert(evidence.chunk_id.clone(), evidence).is_some() {
                    return Err(unsafe_state("duplicate chunk identity"));
                }
                rows += 1;
                if rows > MAX_ROWS {
                    return Err(unsafe_state("chunks ledger row bound exceeded"));
                }
            }
        }
    }
    if publications.len() != associations.len()
        || publications.iter().any(|(chunk, config, introduction)| {
            !associations.contains(&(chunk.clone(), config.clone())) || introduction != head
        })
    {
        return Err(unsafe_state(
            "publication event lacks a current creation association",
        ));
    }
    if rows != scope.expected_current_chunks as u64
        || counts.iter().any(|(raw, n)| {
            scope
                .files
                .iter()
                .find(|f| f.raw_hash == **raw)
                .is_none_or(|f| *n != f.expected_chunks as u64)
        })
    {
        return Err(unsafe_state(
            "chunks ledger does not exactly cover manifest chunks",
        ));
    }
    Ok((chunks.into_values().collect(), binding))
}

fn chunk_identity(row: &LedgerChunk) -> Result<String, AttestError> {
    let mut identity = serde_json::Map::new();
    identity.insert("byte_end".into(), row.byte_end.into());
    identity.insert("byte_start".into(), row.byte_start.into());
    identity.insert("gen".into(), row.r#gen.into());
    identity.insert(
        "heading_path".into(),
        serde_json::to_value(row.heading_path.clone().unwrap_or_default())
            .map_err(|error| other("chunk identity", error))?,
    );
    identity.insert("raw_hash".into(), row.raw_hash.clone().into());
    if let Some(section) = row.section_id.as_ref().filter(|value| !value.is_empty()) {
        identity.insert("section_id".into(), section.clone().into());
    }
    identity.insert("spec_version".into(), 1u64.into());
    identity.insert(
        "tool_profile_hash".into(),
        row.tool_profile_hash.clone().into(),
    );
    identity.insert("unit_key".into(), row.unit_key.clone().into());
    identity.insert(
        "unit_content_hash".into(),
        row.unit_content_hash.clone().into(),
    );
    let bytes = canonical_json_bytes(&serde_json::Value::Object(identity))
        .map_err(|error| other("chunk identity", error))?;
    Ok(hash_bytes(&bytes))
}

fn sqlite_snapshot(
    parent: &fs::File,
    name: &str,
    label: &str,
) -> Result<(Connection, tempfile::TempDir, Vec<SqliteSource>), AttestError> {
    kio_index::vec::ensure_registered();
    let temp = tempfile::Builder::new()
        .prefix("kio-scale-attest-")
        .tempdir()
        .map_err(|e| other(label, e))?;
    let mut sources = Vec::new();
    let mut total = 0u64;
    for suffix in ["", "-wal", "-shm"] {
        let source = format!("{name}{suffix}");
        match cap_fs::stat(parent, Path::new(&source), cap_fs::FollowSymlinks::No) {
            Err(e) if !suffix.is_empty() && e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(e) => return Err(incomplete(format!("{label} missing: {e}"))),
            Ok(m) if !m.is_file() || m.file_type().is_symlink() || m.len() > MAX_SQLITE_LEAF => {
                return Err(unsafe_state(format!("{label} sidecar unsafe")));
            }
            Ok(_) => {
                let (bytes, observation) =
                    observed_regular(parent, &source, MAX_SQLITE_LEAF, label)?;
                total = total
                    .checked_add(bytes.len() as u64)
                    .ok_or_else(|| unsafe_state("SQLite snapshot byte counter overflow"))?;
                if total > MAX_SQLITE_TOTAL {
                    return Err(unsafe_state(
                        "SQLite snapshot aggregate byte bound exceeded",
                    ));
                }
                sources.push(SqliteSource {
                    name: source.clone(),
                    observation,
                });
                if suffix != "-shm" {
                    let mut out = fs::OpenOptions::new()
                        .write(true)
                        .create_new(true)
                        .open(temp.path().join(&source))
                        .map_err(|e| other(label, e))?;
                    out.write_all(&bytes).map_err(|e| other(label, e))?;
                }
            }
        }
    }
    let db = Connection::open_with_flags(
        temp.path().join(name),
        OpenFlags::SQLITE_OPEN_READ_ONLY
            | OpenFlags::SQLITE_OPEN_NO_MUTEX
            | OpenFlags::SQLITE_OPEN_URI,
    )
    .map_err(|e| unsafe_state(format!("{label} cannot open snapshot: {e}")))?;
    db.pragma_update(None, "query_only", "ON")
        .map_err(|e| other(label, e))?;
    Ok((db, temp, sources))
}

fn recheck_sqlite(
    parent: &fs::File,
    sources: &[SqliteSource],
    label: &str,
) -> Result<(), AttestError> {
    for source in sources {
        let (_, observation) =
            observed_regular(parent, &source.name, MAX_SQLITE_LEAF, label).map_err(corruption)?;
        if observation != source.observation {
            return Err(unsafe_state(format!(
                "{label} changed during SQLite attestation"
            )));
        }
    }
    Ok(())
}

fn attest_index(
    index: &fs::File,
    head: &str,
    scope: &ScaleScope,
    chunks: &[ChunkEvidence],
    normalized: &BTreeMap<String, NormalizedSourceEvidence>,
) -> Result<(u64, u64, u64), AttestError> {
    let (db, _snapshot, sources) = sqlite_snapshot(index, "sqlite.db", "scope index")?;
    attest_index_schema(&db)?;
    let schema: BTreeSet<(String, String)> = db
        .prepare("SELECT type,name FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'")
        .map_err(|e| other("index schema", e))?
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))
        .map_err(|e| other("index schema", e))?
        .collect::<Result<_, _>>()
        .map_err(|e| other("index schema", e))?;
    let expected_schema: BTreeSet<(String, String)> = [
        ("table", "chunks"),
        ("table", "chunk_config_generations"),
        ("table", "chunk_publications"),
        ("table", "embeddings"),
        ("table", "tree_entries"),
        ("table", "index_metadata"),
        ("table", "chunk_fts"),
        ("table", "chunk_fts_data"),
        ("table", "chunk_fts_idx"),
        ("table", "chunk_fts_docsize"),
        ("table", "chunk_fts_config"),
        ("table", "chunk_vec"),
        ("table", "chunk_vec_info"),
        ("table", "chunk_vec_rowids"),
        ("table", "chunk_vec_chunks"),
        ("table", "chunk_vec_vector_chunks00"),
        ("table", "image_vec"),
        ("table", "image_vec_info"),
        ("table", "image_vec_rowids"),
        ("table", "image_vec_chunks"),
        ("table", "image_vec_vector_chunks00"),
        ("index", "idx_chunks_ident"),
        ("index", "idx_chunk_publications_chunk_id"),
        ("index", "idx_embeddings_type"),
        ("index", "idx_tree_entries_ident"),
        ("trigger", "chunks_ai"),
        ("trigger", "chunks_ad"),
        ("trigger", "chunks_au"),
    ]
    .into_iter()
    .map(|(kind, name)| (kind.to_owned(), name.to_owned()))
    .collect();
    if schema != expected_schema {
        return Err(unsafe_state(
            "index schema object fingerprint differs from current contract",
        ));
    }
    let physical: u64 = db
        .query_row("SELECT COUNT(*) FROM chunks", [], |r| r.get(0))
        .map_err(|e| other("index chunks", e))?;
    if physical > MAX_ROWS {
        return Err(unsafe_state("index row bound exceeded"));
    }
    let db_rows = db
        .prepare("SELECT rowid,chunk_id,raw_hash,tool_profile_hash,gen,unit_key,unit_content_hash,raw_path,heading_path,section_id,byte_start,byte_end,text_hash,text,first_seen_commit,created_at FROM chunks WHERE first_seen_commit=?1 ORDER BY chunk_id LIMIT ?2")
        .map_err(|error| other("index chunks", error))?
        .query_map(rusqlite::params![head, MAX_ROWS + 1], |row| {
            Ok(DbChunkRow {
                rowid: row.get(0)?,
                chunk_id: row.get(1)?,
                raw_hash: row.get(2)?,
                tool_profile_hash: row.get(3)?,
                r#gen: row.get(4)?,
                unit_key: row.get(5)?,
                unit_content_hash: row.get(6)?,
                raw_path: row.get(7)?,
                heading_path: row.get(8)?,
                section_id: row.get(9)?,
                byte_start: row.get(10)?,
                byte_end: row.get(11)?,
                text_hash: row.get(12)?,
                text: row.get(13)?,
                first_seen_commit: row.get(14)?,
                created_at: row.get(15)?,
            })
        })
        .map_err(|error| other("index chunks", error))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| other("index chunks", error))?;
    let association_rows = db
        .prepare("SELECT chunk_id,association_rowid FROM chunk_config_generations WHERE chunking_config_hash=?1 AND introduction_commit=?2 ORDER BY chunk_id LIMIT ?3")
        .map_err(|error| other("index chunk associations", error))?
        .query_map(
            rusqlite::params![scale_spec::CHUNKING_CONFIG_HASH, head, MAX_ROWS + 1],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .map_err(|error| other("index chunk associations", error))?
        .collect::<Result<Vec<(String, u64)>, _>>()
        .map_err(|error| other("index chunk associations", error))?;
    let mut associations = BTreeMap::new();
    for (chunk_id, association_rowid) in association_rows {
        if associations.insert(chunk_id, association_rowid).is_some() {
            return Err(unsafe_state(
                "index has duplicate current chunk/config association",
            ));
        }
    }
    let mut actual_chunks = Vec::with_capacity(db_rows.len());
    for row in db_rows {
        let heading_path: Vec<String> = serde_json::from_str(&row.heading_path)
            .map_err(|error| unsafe_state(format!("index heading_path schema: {error}")))?;
        let association_rowid = associations
            .get(&row.chunk_id)
            .copied()
            .ok_or_else(|| unsafe_state("index chunk lacks current config association"))?;
        actual_chunks.push(ChunkEvidence {
            rowid: row.rowid,
            association_rowid,
            chunk_id: row.chunk_id,
            raw_hash: row.raw_hash,
            tool_profile_hash: row.tool_profile_hash,
            r#gen: row.r#gen,
            unit_key: row.unit_key,
            unit_content_hash: row.unit_content_hash,
            raw_path: row.raw_path,
            heading_path,
            section_id: row.section_id,
            byte_start: row.byte_start,
            byte_end: row.byte_end,
            text_hash: row.text_hash,
            text: row.text,
            first_seen_commit: row
                .first_seen_commit
                .ok_or_else(|| unsafe_state("index chunk lacks first_seen_commit"))?,
            created_at: row.created_at,
        });
    }
    if associations.len() != chunks.len() || actual_chunks != chunks {
        return Err(unsafe_state(
            "index chunks/config associations differ from the chunks ledger",
        ));
    }
    let fts_chunk_ids: BTreeSet<String> = db
        .prepare("SELECT c.chunk_id FROM chunk_fts_docsize d JOIN chunks c ON c.rowid=d.id WHERE c.first_seen_commit=?1 ORDER BY c.chunk_id LIMIT ?2")
        .map_err(|error| other("index FTS", error))?
        .query_map(rusqlite::params![head, MAX_ROWS + 1], |row| row.get(0))
        .map_err(|error| other("index FTS", error))?
        .collect::<Result<_, _>>()
        .map_err(|error| other("index FTS", error))?;
    let expected_chunk_ids: BTreeSet<String> =
        chunks.iter().map(|chunk| chunk.chunk_id.clone()).collect();
    if fts_chunk_ids != expected_chunk_ids {
        return Err(unsafe_state(
            "index current chunks/FTS differ from manifest",
        ));
    }
    // The synthetic corpus renders `scale` into every generated section.  A
    // bounded MATCH probe checks the virtual table's query semantics rather
    // than merely trusting its shadow/docsize rows.
    let match_ids: BTreeSet<String> = db
        .prepare("SELECT c.chunk_id FROM chunk_fts f JOIN chunks c ON c.rowid=f.rowid WHERE chunk_fts MATCH 'scale' AND c.first_seen_commit=?1 ORDER BY c.chunk_id LIMIT ?2")
        .map_err(|error| other("index FTS MATCH", error))?
        .query_map(rusqlite::params![head, MAX_ROWS + 1], |row| row.get(0))
        .map_err(|error| other("index FTS MATCH", error))?
        .collect::<Result<_, _>>()
        .map_err(|error| other("index FTS MATCH", error))?;
    if match_ids != expected_chunk_ids {
        return Err(unsafe_state(
            "index FTS MATCH does not cover current scale chunks",
        ));
    }
    let tree_rows = db
        .prepare("SELECT path,raw_hash,tool_profile_hash,gen,manifest_hash FROM tree_entries WHERE commit_hash=?1 ORDER BY path LIMIT ?2")
        .map_err(|error| other("index tree entries", error))?
        .query_map(rusqlite::params![head, scope.files.len() as u64 + 1], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Option<String>>(2)?,
                row.get::<_, Option<u64>>(3)?,
                row.get::<_, Option<String>>(4)?,
            ))
        })
        .map_err(|error| other("index tree entries", error))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| other("index tree entries", error))?;
    if tree_rows.len() != scope.files.len()
        || tree_rows.iter().zip(&scope.files).any(
            |((path, raw, tool, generation, manifest), expected)| {
                let normalized = normalized.get(raw);
                path != &expected.path
                    || raw != &expected.raw_hash
                    || normalized.is_none_or(|evidence| {
                        tool.as_deref() != Some(evidence.tool_profile_hash.as_str())
                            || *generation != Some(evidence.r#gen)
                            || manifest.as_deref() != Some(evidence.manifest_hash.as_str())
                    })
            },
        )
    {
        return Err(unsafe_state(
            "index tree projection differs from immutable HEAD tree",
        ));
    }
    let embedded: u64 = db
        .query_row("SELECT COUNT(*) FROM embeddings", [], |row| row.get(0))
        .map_err(|error| other("index embeddings", error))?;
    let chunk_vectors: u64 = db
        .query_row("SELECT COUNT(*) FROM chunk_vec", [], |row| row.get(0))
        .map_err(|error| other("index chunk vectors", error))?;
    let image_vectors: u64 = db
        .query_row("SELECT COUNT(*) FROM image_vec", [], |row| row.get(0))
        .map_err(|error| other("index image vectors", error))?;
    if embedded != 0 || chunk_vectors != 0 || image_vectors != 0 {
        return Err(unsafe_state(
            "offline scale index contains embedding/vector rows",
        ));
    }
    recheck_sqlite(index, &sources, "scope index")?;
    Ok((physical, chunks.len() as u64, embedded))
}

fn canonical_sql(sql: &str) -> String {
    let mut output = String::new();
    let mut chars = sql.chars().peekable();
    let mut quote = None;
    while let Some(character) = chars.next() {
        if let Some(delimiter) = quote {
            output.extend(character.to_lowercase());
            if character == delimiter {
                if chars.peek() == Some(&delimiter) {
                    output.extend(chars.next().expect("peeked").to_lowercase());
                } else {
                    quote = None;
                }
            }
            continue;
        }
        if matches!(character, '\'' | '"') {
            quote = Some(character);
            output.extend(character.to_lowercase());
            continue;
        }
        if character == '-' && chars.peek() == Some(&'-') {
            chars.next();
            for comment in chars.by_ref() {
                if comment == '\n' {
                    break;
                }
            }
            continue;
        }
        if !character.is_whitespace() {
            output.extend(character.to_lowercase());
        }
    }
    output
}

fn attest_index_schema(db: &Connection) -> Result<(), AttestError> {
    for (object_type, fingerprints) in [
        ("table", TABLE_SQL_FINGERPRINTS),
        ("index", &INDEX_SQL_FINGERPRINTS[..4]),
        ("trigger", &INDEX_SQL_FINGERPRINTS[4..7]),
        ("table", &INDEX_SQL_FINGERPRINTS[7..]),
    ] {
        for (name, expected) in fingerprints {
            let actual: (String, String) = db
                .query_row(
                    "SELECT type,sql FROM sqlite_schema WHERE type=?1 AND name=?2",
                    [object_type, *name],
                    |row| Ok((row.get(0)?, row.get(1)?)),
                )
                .map_err(|error| other("index schema SQL", error))?;
            if actual.0 != object_type || canonical_sql(&actual.1) != canonical_sql(expected) {
                return Err(unsafe_state(format!("index schema SQL differs for {name}")));
            }
        }
    }
    Ok(())
}

fn attest_registry_schema(db: &Connection) -> Result<(), AttestError> {
    let actual: (String, String) = db
        .query_row(
            "SELECT type,sql FROM sqlite_schema WHERE name='scopes'",
            [],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .map_err(|error| other("registry schema SQL", error))?;
    if actual.0 != "table" || canonical_sql(&actual.1) != canonical_sql(REGISTRY_SCOPES_SQL) {
        return Err(unsafe_state(
            "registry scopes SQL differs from current contract",
        ));
    }
    Ok(())
}

/// Attest all per-scope immutable and index evidence.  The fixture must stay
/// locked by the caller for a skip decision; this function still rechecks it
/// before and after every scope to reject replacement races.
fn attest_scope_inner(
    fixture: &ValidatedFixture,
    root: &fs::File,
    scope: &ScaleScope,
) -> Result<ScopeEvidence, AttestError> {
    fixture.recheck()?;
    let scope_before = cap_fs::stat(root, Path::new(&scope.name), cap_fs::FollowSymlinks::No)
        .map_err(|e| incomplete(format!("scope missing: {e}")))?;
    let scope_dir = required_dir(root, &scope.name, "scope")?;
    let names = direct_names(&scope_dir, scope.files.len() + 1, "scope enumeration")?;
    let source_names: BTreeSet<String> = scope.files.iter().map(|f| f.path.clone()).collect();
    if names == source_names {
        return Err(incomplete("scope is not initialized"));
    }
    let allowed: BTreeSet<String> = source_names
        .into_iter()
        .chain(std::iter::once(".kio".into()))
        .collect();
    if names != allowed {
        return Err(unsafe_state("scope has missing or unmanifested entries"));
    }
    for source in &scope.files {
        let bytes = regular(
            &scope_dir,
            &source.path,
            scale_spec::MAX_SOURCE_BYTES as u64,
            "source",
        )?;
        if bytes.len() != source.bytes || hash_bytes(&bytes) != source.raw_hash {
            return Err(unsafe_state("source differs from manifest"));
        }
    }
    let kio = required_dir(&scope_dir, ".kio", "scope .kio")?;
    let kio_before = cap_fs::stat(&scope_dir, Path::new(".kio"), cap_fs::FollowSymlinks::No)
        .map_err(|e| other("scope .kio", e))?;
    no_runtime(&kio)?;
    let (head_bytes, head_binding) = bind_regular(&kio, "HEAD", 256, "HEAD")?;
    let head = str::from_utf8(&head_bytes)
        .map_err(|_| unsafe_state("HEAD is not UTF-8"))?
        .trim()
        .to_owned();
    if head.is_empty() {
        return Err(incomplete("scope has no HEAD"));
    }
    let config_binding = check_config(&kio).map_err(corruption)?;
    let refs = required_dir(&kio, "refs", "refs").map_err(corruption)?;
    let refs_before = cap_fs::stat(&kio, Path::new("refs"), cap_fs::FollowSymlinks::No)
        .map_err(|error| other("refs", error))?;
    let heads = required_dir(&refs, "heads", "heads").map_err(corruption)?;
    let heads_before = cap_fs::stat(&refs, Path::new("heads"), cap_fs::FollowSymlinks::No)
        .map_err(|error| other("refs/heads", error))?;
    let (branch_bytes, branch_binding) =
        bind_regular(&heads, "main", 256, "refs/heads/main").map_err(corruption)?;
    let branch = str::from_utf8(&branch_bytes)
        .map_err(|_| unsafe_state("branch is not UTF-8"))?
        .trim()
        .to_owned();
    if head != branch {
        return Err(unsafe_state("HEAD and refs/heads/main differ"));
    }
    let (identity_bytes, identity_binding) =
        bind_regular(&kio, "scope.json", MAX_METADATA, "scope identity").map_err(corruption)?;
    let identity: ScopeIdentity = typed_json(&identity_bytes, "scope identity")?;
    let expected_scope_path = fixture.root().join(&scope.name);
    let expected_scope_path = expected_scope_path.to_string_lossy();
    let expected_source_bytes = scope.files.iter().map(|source| source.bytes).sum::<usize>();
    let approval = &identity.scan_approval;
    if identity.scope_id.is_empty()
        || identity.kio_format_version != env!("CARGO_PKG_VERSION")
        || identity.scope_path != expected_scope_path
        || approval.scope_id != identity.scope_id
        || approval.root_path != expected_scope_path
        || approval.approved_at.is_empty()
        || approval.actor.is_empty()
        || approval.approval_method != "yes"
        || approval.kio_version != env!("CARGO_PKG_VERSION")
        || !is_hash(&approval.effective_ignore_hash)
        || approval.estimated_file_count != scope.files.len()
        || approval.estimated_total_bytes != expected_source_bytes
        || approval.estimated_markdownize_usd != 0.0
        || approval.estimated_embedding_usd != 0.0
    {
        return Err(unsafe_state("scope identity does not bind this corpus"));
    }
    let mut cas_bindings = Vec::with_capacity(scope.files.len().saturating_mul(3) + 2);
    let normalized = attest_cas(&kio, &head, scope, &mut cas_bindings).map_err(corruption)?;
    let index = required_dir(&kio, "index", "scope index").map_err(corruption)?;
    let index_before = cap_fs::stat(&kio, Path::new("index"), cap_fs::FollowSymlinks::No)
        .map_err(|e| other("scope index", e))?;
    let (chunks, ledger_binding) =
        attest_ledger(&index, &head, scope, &normalized).map_err(corruption)?;
    let (physical, current, embedded) =
        attest_index(&index, &head, scope, &chunks, &normalized).map_err(corruption)?;
    no_runtime(&kio)?;
    config_binding.recheck()?;
    head_binding.recheck()?;
    branch_binding.recheck()?;
    identity_binding.recheck()?;
    ledger_binding.recheck()?;
    recheck_cas(&kio, &cas_bindings)?;
    unchanged(&refs, "heads", &heads_before, "refs/heads")?;
    unchanged(&kio, "refs", &refs_before, "refs")?;
    unchanged(&kio, "index", &index_before, "scope index")?;
    unchanged(&scope_dir, ".kio", &kio_before, "scope .kio")?;
    unchanged(root, &scope.name, &scope_before, "scope")?;
    if direct_names(&scope_dir, allowed.len(), "scope enumeration")? != allowed {
        return Err(unsafe_state("scope entries changed during attestation"));
    }
    fixture.recheck()?;
    Ok(ScopeEvidence {
        name: scope.name.clone(),
        scope_id: identity.scope_id,
        head,
        source_files: scope.files.len(),
        current_chunks: current,
        physical_chunks: physical,
        embedded_chunks: embedded,
    })
}

/// Attest one named canonical scope, permitting preparers to resume only the
/// scopes that are genuinely incomplete.
pub fn attest_scope(
    fixture: &ValidatedFixture,
    scope_name: &str,
) -> Result<ScopeEvidence, AttestError> {
    let scope = fixture
        .manifest()
        .scopes
        .iter()
        .find(|scope| scope.name == scope_name)
        .ok_or_else(|| unsafe_state("scope name is not in the frozen fixture manifest"))?;
    let root = fixture.try_clone_root()?;
    attest_scope_inner(fixture, &root, scope)
}

pub fn attest_scopes(fixture: &ValidatedFixture) -> Result<Vec<ScopeEvidence>, AttestError> {
    if fixture.manifest().scopes.len() != SCOPES.len() {
        return Err(unsafe_state(
            "manifest scope count differs from frozen contract",
        ));
    }
    let root = fixture.try_clone_root()?;
    fixture
        .manifest()
        .scopes
        .iter()
        .map(|scope| attest_scope_inner(fixture, &root, scope))
        .collect()
}

/// Attest the isolated global registry exactly against retained scope evidence.
pub fn attest_registry(
    fixture: &ValidatedFixture,
    scopes: &[ScopeEvidence],
) -> Result<usize, AttestError> {
    fixture.recheck()?;
    if scopes.len() != SCOPES.len() {
        return Err(unsafe_state(
            "registry called with incomplete scope evidence",
        ));
    }
    let root = fixture.try_clone_root()?;
    let device_before = cap_fs::stat(
        &root,
        Path::new(scale_spec::DEVICE_DIR_NAME),
        cap_fs::FollowSymlinks::No,
    )
    .map_err(|e| incomplete(format!("device missing: {e}")))?;
    let device = required_dir(&root, scale_spec::DEVICE_DIR_NAME, "device")?;
    let expected_device_names: BTreeSet<String> =
        ["home", "config", "cache", "data", "state", "runtime"]
            .into_iter()
            .map(str::to_owned)
            .collect();
    if direct_names(&device, expected_device_names.len(), "device")? != expected_device_names {
        return Err(unsafe_state("device layout differs from current contract"));
    }
    let data_before = cap_fs::stat(&device, Path::new("data"), cap_fs::FollowSymlinks::No)
        .map_err(|error| other("device data", error))?;
    let data = required_dir(&device, "data", "device data")?;
    let kio_before = cap_fs::stat(&data, Path::new("kio"), cap_fs::FollowSymlinks::No)
        .map_err(|error| other("device kio data", error))?;
    let kio = required_dir(&data, "kio", "device kio data")?;
    let (db, _snapshot, sources) =
        sqlite_snapshot(&kio, "scope-registry.sqlite", "scope registry")?;
    attest_registry_schema(&db)?;
    let tables: BTreeSet<String> = db
        .prepare("SELECT name FROM sqlite_schema WHERE type='table'")
        .map_err(|e| other("registry schema", e))?
        .query_map([], |r| r.get(0))
        .map_err(|e| other("registry schema", e))?
        .collect::<Result<_, _>>()
        .map_err(|e| other("registry schema", e))?;
    if tables != BTreeSet::from(["scopes".to_owned()]) {
        return Err(unsafe_state("registry has missing or unexpected tables"));
    }
    let columns = db
        .prepare("PRAGMA table_info(scopes)")
        .map_err(|e| other("registry schema", e))?
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, i64>(3)?,
                row.get::<_, i64>(5)?,
            ))
        })
        .map_err(|e| other("registry schema", e))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| other("registry schema", e))?;
    let expected_columns = vec![
        ("scope_id".to_owned(), "TEXT".to_owned(), 1, 1),
        ("kio_path".to_owned(), "TEXT".to_owned(), 1, 2),
        ("root_path".to_owned(), "TEXT".to_owned(), 1, 0),
        (
            "participates_in_global_search".to_owned(),
            "INTEGER".to_owned(),
            1,
            0,
        ),
        ("indexed".to_owned(), "INTEGER".to_owned(), 1, 0),
        ("last_seen_at".to_owned(), "TEXT".to_owned(), 1, 0),
    ];
    if columns != expected_columns {
        return Err(unsafe_state(
            "registry scopes schema differs from current contract",
        ));
    }
    let mut stmt=db.prepare("SELECT scope_id,kio_path,root_path,participates_in_global_search,indexed FROM scopes ORDER BY scope_id LIMIT ?1").map_err(|e|other("registry",e))?;
    let rows = stmt
        .query_map([MAX_REGISTRY_ROWS as i64], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, i64>(3)?,
                r.get::<_, i64>(4)?,
            ))
        })
        .map_err(|e| other("registry", e))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| other("registry", e))?;
    if rows.len() != scopes.len() {
        return Err(unsafe_state("registry row count differs from scopes"));
    }
    for evidence in scopes {
        let root_path = fixture.root().join(&evidence.name);
        let kio_path = root_path.join(".kio");
        if !rows.iter().any(|(id, kio, root, participates, indexed)| {
            id == &evidence.scope_id
                && kio == kio_path.to_string_lossy().as_ref()
                && root == root_path.to_string_lossy().as_ref()
                && *participates == 1
                && *indexed == 1
        }) {
            return Err(unsafe_state("registry binding differs from scope evidence"));
        }
    }
    recheck_sqlite(&kio, &sources, "scope registry")?;
    unchanged(&data, "kio", &kio_before, "device kio data")?;
    unchanged(&device, "data", &data_before, "device data")?;
    if direct_names(&device, expected_device_names.len(), "device")? != expected_device_names {
        return Err(unsafe_state("device layout changed during attestation"));
    }
    unchanged(&root, scale_spec::DEVICE_DIR_NAME, &device_before, "device")?;
    fixture.recheck()?;
    Ok(rows.len())
}

/// A prepared corpus is ready only if both independent passes succeed.
pub fn attest_ready(fixture: &ValidatedFixture) -> Result<CorpusEvidence, AttestError> {
    let scopes = attest_scopes(fixture)?;
    let registry_rows = attest_registry(fixture, &scopes)?;
    let current_chunks = scopes.iter().map(|s| s.current_chunks).sum();
    if current_chunks < fixture.profile().minimum_current_chunks() as u64 {
        return Err(unsafe_state(
            "prepared corpus is below the frozen workload threshold",
        ));
    }
    Ok(CorpusEvidence {
        scopes,
        registry_rows,
        current_chunks,
    })
}

/// Bind a ready Rust-v2 fixture, independently re-attest it under the fixture
/// lock, and create one canonical receipt.  Publication is intentionally
/// create-only: an existing (including old-format) receipt is never adopted.
pub fn attest_and_publish(
    corpus: &Path,
    requested_out: Option<&Path>,
) -> Result<AttestationSummary, AttestError> {
    let fixture = crate::scale_fixture::bind_ready(corpus)?;
    let _lock = fixture.lock()?;
    fixture.recheck()?;
    let evidence = attest_ready(&fixture)?;
    let report = AttestationReport {
        schema_version: scale_spec::SCHEMA_VERSION,
        attestor: scale_spec::ATTESTOR_ID.to_owned(),
        fixture_id: scale_spec::FIXTURE_ID.to_owned(),
        profile: fixture.profile(),
        manifest_hash: scale_spec::manifest_hash(fixture.manifest())
            .map_err(|error| unsafe_state(format!("cannot bind manifest: {error}")))?,
        content_root_hash: fixture.manifest().content_root_hash.clone(),
        corpus: fixture.root().to_string_lossy().into_owned(),
        scopes: evidence.scopes.clone(),
        registry_rows: evidence.registry_rows,
        current_chunks: evidence.current_chunks,
    };
    let mut bytes = canonical_json_bytes(
        &serde_json::to_value(&report)
            .map_err(|error| unsafe_state(format!("cannot serialize attestation: {error}")))?,
    )
    .map_err(|error| unsafe_state(format!("cannot canonicalize attestation: {error}")))?;
    bytes.push(b'\n');
    verify_report(&bytes, &report)?;
    let official = fixture.root().join(scale_spec::ATTESTATION_NAME);
    let public_report = match requested_out {
        None => publish_official(&fixture, &bytes)?,
        Some(path) if !path.is_absolute() => {
            return Err(unsafe_state("explicit attestation output must be absolute"));
        }
        Some(path) if exact_clean_path(path, &official)? && is_official_output(path, &fixture)? => {
            publish_official(&fixture, &bytes)?
        }
        Some(path) => publish_external(path, &fixture, &bytes)?,
    };
    fixture.recheck()?;
    Ok(AttestationSummary {
        corpus: fixture.root().to_owned(),
        report: public_report,
        scopes: evidence.scopes.len(),
        current_chunks: evidence.current_chunks,
    })
}

fn verify_report(bytes: &[u8], expected: &AttestationReport) -> Result<(), AttestError> {
    if bytes.len() > MAX_REPORT_BYTES || !bytes.ends_with(b"\n") {
        return Err(unsafe_state("attestation is not bounded LF JSON"));
    }
    let value: serde_json::Value = serde_json::from_slice(bytes)
        .map_err(|error| unsafe_state(format!("attestation is invalid JSON: {error}")))?;
    let mut canonical = canonical_json_bytes(&value)
        .map_err(|error| unsafe_state(format!("cannot recanonicalize attestation: {error}")))?;
    canonical.push(b'\n');
    if canonical != bytes {
        return Err(unsafe_state("attestation is not canonical JCS plus LF"));
    }
    let actual: AttestationReport = serde_json::from_slice(bytes)
        .map_err(|error| unsafe_state(format!("attestation violates v2 schema: {error}")))?;
    if &actual != expected {
        return Err(unsafe_state("attestation does not bind current evidence"));
    }
    Ok(())
}

fn exact_clean_path(path: &Path, official: &Path) -> Result<bool, AttestError> {
    let absolute = absolute_clean(path)?;
    Ok(absolute == absolute_clean(official)?)
}

fn is_official_output(path: &Path, fixture: &ValidatedFixture) -> Result<bool, AttestError> {
    let absolute = absolute_clean(path)?;
    let Some(parent) = absolute.parent() else {
        return Ok(false);
    };
    let parent_metadata = fs::symlink_metadata(parent)
        .map_err(|error| unsafe_state(format!("cannot inspect official output parent: {error}")))?;
    let root_metadata = fixture
        .try_clone_root()?
        .metadata()
        .map_err(|error| unsafe_state(format!("cannot inspect fixture root: {error}")))?;
    Ok(!parent_metadata.file_type().is_symlink()
        && crate::boundary::same_directory_identity(&parent_metadata, &root_metadata)
        && absolute.file_name() == Some(std::ffi::OsStr::new(scale_spec::ATTESTATION_NAME)))
}

fn absolute_clean(path: &Path) -> Result<PathBuf, AttestError> {
    let absolute = path.to_owned();
    if !path.is_absolute()
        || absolute.components().any(|component| {
            matches!(
                component,
                Component::CurDir | Component::ParentDir | Component::Prefix(_)
            )
        })
    {
        return Err(unsafe_state(
            "output path must be a clean absolute lexical path",
        ));
    }
    #[cfg(target_os = "macos")]
    let absolute = {
        let text = absolute
            .to_str()
            .ok_or_else(|| unsafe_state("output path is not UTF-8"))?;
        if text == "/tmp"
            || text.starts_with("/tmp/")
            || text == "/var"
            || text.starts_with("/var/")
        {
            PathBuf::from(format!("/private{text}"))
        } else {
            absolute
        }
    };
    Ok(absolute)
}

fn publish_official(fixture: &ValidatedFixture, bytes: &[u8]) -> Result<PathBuf, AttestError> {
    let root = fixture.try_clone_root()?;
    let metadata = root
        .metadata()
        .map_err(|error| other("fixture root", error))?;
    let device = cap_fs::open_dir_nofollow(&root, Path::new(scale_spec::DEVICE_DIR_NAME))
        .map_err(|error| other("fixture device", error))?;
    let state = cap_fs::open_dir_nofollow(&device, Path::new("state"))
        .map_err(|error| other("fixture device state", error))?;
    let state_metadata = state
        .metadata()
        .map_err(|error| other("fixture device state", error))?;
    publish_in_parent(
        &state,
        &state_metadata,
        &fixture
            .root()
            .join(scale_spec::DEVICE_DIR_NAME)
            .join("state"),
        &root,
        &metadata,
        fixture.root(),
        scale_spec::ATTESTATION_NAME,
        bytes,
    )?;
    Ok(fixture.root().join(scale_spec::ATTESTATION_NAME))
}

fn publish_external(
    path: &Path,
    fixture: &ValidatedFixture,
    bytes: &[u8],
) -> Result<PathBuf, AttestError> {
    if !path.is_absolute() {
        return Err(unsafe_state("external attestation output must be absolute"));
    }
    let absolute = absolute_clean(path)?;
    let parent = absolute
        .parent()
        .ok_or_else(|| unsafe_state("external output has no parent"))?;
    let name = absolute
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty() && *name != "." && *name != "..")
        .ok_or_else(|| unsafe_state("external output has an unsafe leaf"))?;
    let corpus_identity = fixture
        .try_clone_root()?
        .metadata()
        .map_err(|error| other("corpus", error))?;
    let mut handle = cap_fs::open_ambient_dir(Path::new("/"), ambient_authority())
        .map_err(|error| other("external output root", error))?;
    let mut retained_path = PathBuf::from("/");
    for component in parent.components() {
        if let Component::Normal(part) = component {
            handle = cap_fs::open_dir_nofollow(&handle, Path::new(part))
                .map_err(|error| other("external output parent", error))?;
            retained_path.push(part);
            let retained = handle
                .metadata()
                .map_err(|error| other("external output parent", error))?;
            let public = fs::symlink_metadata(&retained_path)
                .map_err(|error| other("external output parent", error))?;
            if !retained.is_dir()
                || public.file_type().is_symlink()
                || !crate::boundary::same_directory_identity(&retained, &public)
            {
                return Err(unsafe_state("external output parent changed while binding"));
            }
            if crate::boundary::same_directory_identity(&retained, &corpus_identity) {
                return Err(unsafe_state(
                    "external attestation output aliases the corpus",
                ));
            }
        }
    }
    let metadata = handle
        .metadata()
        .map_err(|error| other("external output parent", error))?;
    publish_in_parent(
        &handle,
        &metadata,
        &retained_path,
        &handle,
        &metadata,
        &retained_path,
        name,
        bytes,
    )?;
    Ok(retained_path.join(name))
}

#[allow(clippy::too_many_arguments)]
fn publish_in_parent(
    staging_parent: &fs::File,
    staging_metadata: &fs::Metadata,
    staging_path: &Path,
    target_parent: &fs::File,
    target_metadata: &fs::Metadata,
    target_path: &Path,
    leaf: &str,
    bytes: &[u8],
) -> Result<(), AttestError> {
    if bytes.len() > MAX_REPORT_BYTES {
        return Err(unsafe_state("attestation exceeds output bound"));
    }
    match cap_fs::stat(target_parent, Path::new(leaf), cap_fs::FollowSymlinks::No) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Ok(_) => {
            return Err(unsafe_state(
                "attestation output already exists; never overwrite",
            ));
        }
        Err(error) => return Err(other("attestation output", error)),
    }
    let temp = format!("{REPORT_TEMP_PREFIX}{leaf}");
    match cap_fs::stat(staging_parent, Path::new(&temp), cap_fs::FollowSymlinks::No) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Ok(_) => {}
        Err(error) => return Err(other("attestation staging", error)),
    }
    if cap_fs::stat(staging_parent, Path::new(&temp), cap_fs::FollowSymlinks::No)
        .is_err_and(|error| error.kind() == std::io::ErrorKind::NotFound)
    {
        let mut options = cap_fs::OpenOptions::new();
        options.write(true).create_new(true);
        let mut staged = cap_fs::open(staging_parent, Path::new(&temp), &options)
            .map_err(|error| other("attestation staging", error))?;
        staged
            .write_all(bytes)
            .and_then(|_| staged.sync_all())
            .map_err(|error| other("attestation staging", error))?;
    }
    let (_, staged_observation) = observed_regular(
        staging_parent,
        &temp,
        MAX_REPORT_BYTES as u64,
        "attestation staging",
    )?;
    if staged_observation.sha256 != hash_bytes(bytes)
        || staged_observation.bytes != bytes.len() as u64
    {
        return Err(unsafe_state("attestation staging bytes differ from report"));
    }
    recheck_public_parent(target_path, target_metadata)?;
    crate::scale_fixture::rename_noreplace(staging_parent, &temp, target_parent, leaf)
        .map_err(AttestError::Fixture)?;
    let verification = (|| -> Result<(), AttestError> {
        crate::boundary::sync_retained_directory(staging_parent, staging_metadata, staging_path)
            .map_err(|error| {
                unsafe_state(format!("cannot sync attestation staging parent: {error}"))
            })?;
        crate::boundary::sync_retained_directory(target_parent, target_metadata, target_path)
            .map_err(|error| unsafe_state(format!("cannot sync attestation parent: {error}")))?;
        let (_, published) = observed_regular(
            target_parent,
            leaf,
            MAX_REPORT_BYTES as u64,
            "published attestation",
        )?;
        if published != staged_observation {
            return Err(unsafe_state(
                "published attestation differs from staged binding",
            ));
        }
        recheck_public_parent(target_path, target_metadata)?;
        let reread = observed_regular(
            target_parent,
            leaf,
            MAX_REPORT_BYTES as u64,
            "published attestation",
        )?
        .1;
        if reread != published {
            return Err(unsafe_state(
                "published attestation changed after verification",
            ));
        }
        Ok(())
    })();
    verification.map_err(|error| AttestError::Indeterminate(error.to_string()))
}

fn recheck_public_parent(path: &Path, expected: &fs::Metadata) -> Result<(), AttestError> {
    let public = fs::symlink_metadata(path)
        .map_err(|error| unsafe_state(format!("cannot recheck public output parent: {error}")))?;
    if public.file_type().is_symlink()
        || !public.is_dir()
        || !crate::boundary::same_directory_identity(expected, &public)
    {
        return Err(unsafe_state(
            "public output parent changed during publication",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod publication_tests {
    use super::*;

    fn report() -> AttestationReport {
        AttestationReport {
            schema_version: 2,
            attestor: scale_spec::ATTESTOR_ID.to_owned(),
            fixture_id: scale_spec::FIXTURE_ID.to_owned(),
            profile: scale_spec::ScaleProfile::Tiny,
            manifest_hash: format!("sha256:{}", "a".repeat(64)),
            content_root_hash: format!("sha256:{}", "b".repeat(64)),
            corpus: "/tmp/fixture".to_owned(),
            scopes: vec![ScopeEvidence {
                name: "research-papers".to_owned(),
                scope_id: "scope".to_owned(),
                head: format!("sha256:{}", "c".repeat(64)),
                source_files: 1,
                current_chunks: 3,
                physical_chunks: 3,
                embedded_chunks: 0,
            }],
            registry_rows: 1,
            current_chunks: 3,
        }
    }

    fn canonical(report: &AttestationReport) -> Vec<u8> {
        let mut bytes = canonical_json_bytes(&serde_json::to_value(report).unwrap()).unwrap();
        bytes.push(b'\n');
        bytes
    }

    #[test]
    fn report_is_strict_canonical_lf_v2() {
        let receipt = report();
        let bytes = canonical(&receipt);
        verify_report(&bytes, &receipt).unwrap();
        let mut value: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        value["unexpected"] = serde_json::json!(true);
        let mut malformed = canonical_json_bytes(&value).unwrap();
        malformed.push(b'\n');
        assert!(verify_report(&malformed, &receipt).is_err());
        assert!(verify_report(&bytes[..bytes.len() - 1], &receipt).is_err());
    }

    #[test]
    fn publication_is_create_only_and_recovers_exact_staging() {
        let temp = tempfile::tempdir().unwrap();
        let handle = cap_fs::open_ambient_dir(temp.path(), ambient_authority()).unwrap();
        let metadata = handle.metadata().unwrap();
        let bytes = canonical(&report());
        publish_in_parent(
            &handle,
            &metadata,
            temp.path(),
            &handle,
            &metadata,
            temp.path(),
            "receipt.json",
            &bytes,
        )
        .unwrap();
        assert_eq!(fs::read(temp.path().join("receipt.json")).unwrap(), bytes);
        assert!(
            publish_in_parent(
                &handle,
                &metadata,
                temp.path(),
                &handle,
                &metadata,
                temp.path(),
                "receipt.json",
                &bytes,
            )
            .is_err()
        );
    }

    #[test]
    fn output_paths_must_be_absolute_and_lexically_clean() {
        assert!(absolute_clean(Path::new("relative.json")).is_err());
        let dirty = Path::new("/tmp/../tmp/receipt.json");
        assert!(absolute_clean(dirty).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn external_output_rejects_corpus_and_symlink_aliases() {
        use std::os::unix::fs::symlink;

        let temp = tempfile::tempdir().unwrap();
        let base = fs::canonicalize(temp.path()).unwrap();
        let corpus = base.join("corpus");
        crate::scale_fixture::generate(&corpus, scale_spec::ScaleProfile::Tiny, false).unwrap();
        let fixture = crate::scale_fixture::bind_ready(&corpus).unwrap();
        let bytes = canonical(&report());
        assert!(publish_external(&corpus.join("unexpected.json"), &fixture, &bytes).is_err());
        let alias = base.join("alias");
        symlink(&corpus, &alias).unwrap();
        assert!(publish_external(&alias.join("receipt.json"), &fixture, &bytes).is_err());
        assert!(!corpus.join("unexpected.json").exists());
        assert!(!corpus.join("receipt.json").exists());
    }

    #[cfg(unix)]
    #[test]
    fn publication_rejects_existing_symlink_and_hardlink_targets() {
        use std::os::unix::fs::symlink;

        let temp = tempfile::tempdir().unwrap();
        let handle = cap_fs::open_ambient_dir(temp.path(), ambient_authority()).unwrap();
        let metadata = handle.metadata().unwrap();
        let bytes = canonical(&report());
        let victim = temp.path().join("victim.json");
        fs::write(&victim, b"victim").unwrap();
        symlink(&victim, temp.path().join("receipt.json")).unwrap();
        assert!(
            publish_in_parent(
                &handle,
                &metadata,
                temp.path(),
                &handle,
                &metadata,
                temp.path(),
                "receipt.json",
                &bytes,
            )
            .is_err()
        );
        assert_eq!(fs::read(&victim).unwrap(), b"victim");
        fs::remove_file(temp.path().join("receipt.json")).unwrap();
        fs::hard_link(&victim, temp.path().join("receipt.json")).unwrap();
        assert!(
            publish_in_parent(
                &handle,
                &metadata,
                temp.path(),
                &handle,
                &metadata,
                temp.path(),
                "receipt.json",
                &bytes,
            )
            .is_err()
        );
        assert_eq!(fs::read(&victim).unwrap(), b"victim");
    }

    #[cfg(unix)]
    #[test]
    fn public_parent_replacement_is_rejected() {
        let temp = tempfile::tempdir().unwrap();
        let parent = temp.path().join("output");
        let displaced = temp.path().join("displaced");
        fs::create_dir(&parent).unwrap();
        let expected = fs::metadata(&parent).unwrap();
        fs::rename(&parent, &displaced).unwrap();
        fs::create_dir(&parent).unwrap();
        assert!(recheck_public_parent(&parent, &expected).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn bound_regular_rejects_unsafe_leaves_and_replacement() {
        use std::os::unix::fs::symlink;

        let temp = tempfile::tempdir().unwrap();
        let handle = cap_fs::open_ambient_dir(temp.path(), ambient_authority()).unwrap();
        fs::write(temp.path().join("file"), b"same").unwrap();
        let (_, binding) = bind_regular(&handle, "file", 16, "test").unwrap();
        fs::rename(temp.path().join("file"), temp.path().join("old")).unwrap();
        fs::write(temp.path().join("file"), b"same").unwrap();
        assert!(binding.recheck().is_err());
        fs::remove_file(temp.path().join("file")).unwrap();
        symlink(temp.path().join("old"), temp.path().join("file")).unwrap();
        assert!(observed_regular(&handle, "file", 16, "test").is_err());
        fs::remove_file(temp.path().join("file")).unwrap();
        fs::hard_link(temp.path().join("old"), temp.path().join("file")).unwrap();
        assert!(observed_regular(&handle, "file", 16, "test").is_err());
        fs::remove_file(temp.path().join("file")).unwrap();
        fs::write(temp.path().join("file"), b"too-large").unwrap();
        assert!(observed_regular(&handle, "file", 3, "test").is_err());
    }

    #[test]
    fn config_must_be_exactly_empty() {
        let temp = tempfile::tempdir().unwrap();
        let handle = cap_fs::open_ambient_dir(temp.path(), ambient_authority()).unwrap();
        fs::write(temp.path().join("config.toml"), b"x=1\n").unwrap();
        assert!(check_config(&handle).is_err());
        fs::write(temp.path().join("config.toml"), b"").unwrap();
        assert!(check_config(&handle).is_ok());
    }

    fn current_schema(db: &Connection, changed_chunks: bool, ordinary_fts: bool) {
        kio_index::vec::ensure_registered();
        for (name, ddl) in TABLE_SQL_FINGERPRINTS {
            let ddl = if changed_chunks && *name == "chunks" {
                ddl.replace(
                    "CHECK (length(unit_content_hash) = 71 AND substr(unit_content_hash, 1, 7) = 'sha256:' AND substr(unit_content_hash, 8) NOT GLOB '*[^0-9a-f]*')",
                    "CHECK (1)",
                )
            } else {
                (*ddl).to_owned()
            };
            db.execute_batch(&ddl).unwrap();
        }
        for (_, ddl) in &INDEX_SQL_FINGERPRINTS[..4] {
            db.execute_batch(ddl).unwrap();
        }
        if ordinary_fts {
            db.execute_batch("CREATE TABLE chunk_fts (text TEXT, heading_path TEXT)")
                .unwrap();
        } else {
            db.execute_batch(INDEX_SQL_FINGERPRINTS[7].1).unwrap();
        }
        db.execute_batch(INDEX_SQL_FINGERPRINTS[8].1).unwrap();
        db.execute_batch(INDEX_SQL_FINGERPRINTS[9].1).unwrap();
        for (_, ddl) in &INDEX_SQL_FINGERPRINTS[4..7] {
            db.execute_batch(ddl).unwrap();
        }
    }

    #[test]
    fn exact_index_schema_rejects_virtual_and_principal_constraint_drift() {
        kio_index::vec::ensure_registered();
        let db = Connection::open_in_memory().unwrap();
        current_schema(&db, false, false);
        assert!(attest_index_schema(&db).is_ok());
        let fts_replaced = Connection::open_in_memory().unwrap();
        current_schema(&fts_replaced, false, true);
        assert!(attest_index_schema(&fts_replaced).is_err());
        let changed_constraint = Connection::open_in_memory().unwrap();
        current_schema(&changed_constraint, true, false);
        assert!(attest_index_schema(&changed_constraint).is_err());
    }

    #[test]
    fn exact_registry_schema_rejects_default_and_key_drift() {
        let current = Connection::open_in_memory().unwrap();
        current.execute_batch(REGISTRY_SCOPES_SQL).unwrap();
        assert!(attest_registry_schema(&current).is_ok());

        let changed_default = Connection::open_in_memory().unwrap();
        changed_default
            .execute_batch(&REGISTRY_SCOPES_SQL.replace("DEFAULT 1", "DEFAULT 0"))
            .unwrap();
        assert!(attest_registry_schema(&changed_default).is_err());

        let changed_key = Connection::open_in_memory().unwrap();
        changed_key
            .execute_batch(
                &REGISTRY_SCOPES_SQL
                    .replace("PRIMARY KEY (scope_id, kio_path)", "PRIMARY KEY (scope_id)"),
            )
            .unwrap();
        assert!(attest_registry_schema(&changed_key).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn sqlite_snapshot_rejects_hardlinked_sidecar() {
        let temp = tempfile::tempdir().unwrap();
        let db_path = temp.path().join("index.sqlite");
        Connection::open(&db_path)
            .unwrap()
            .execute_batch("CREATE TABLE t (id INTEGER)")
            .unwrap();
        fs::hard_link(&db_path, temp.path().join("index-copy.sqlite")).unwrap();
        let handle = cap_fs::open_ambient_dir(temp.path(), ambient_authority()).unwrap();
        assert!(sqlite_snapshot(&handle, "index.sqlite", "test sqlite").is_err());
    }
}
