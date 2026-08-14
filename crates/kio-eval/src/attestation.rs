//! Bounded immutable-CAS attestation for evaluator evidence pointers.
//!
//! This module deliberately resolves only the caller-supplied corpus scopes.
//! An untrusted `scope_id` never becomes a filesystem path or a discovery
//! request. CAS reads walk only retained capability handles, preserving the
//! core CAS fanout, hash, and representation checks without reopening paths.

use std::{collections::HashMap, fs, io::Read, path::Path};

use cap_primitives::fs as cap_fs;
use kio_core::{
    cas::{
        ChunkObject, MAX_CHUNK_OBJECT_BYTES, MAX_COMMIT_OBJECT_BYTES, MAX_TREE_OBJECT_BYTES,
        ObjectKind, canonical_json_bytes, hash_bytes, is_hash,
    },
    dag::{CommitObject, MAX_TREE_ENTRIES, TreeObject},
    scope::KIO_FORMAT_VERSION,
};
use kio_search::EvidencePointer;
use serde_json::Value;
use thiserror::Error;

use crate::boundary::BoundCorpus;

/// Maximum bytes verified across one evaluator invocation.
pub const MAX_POINTER_ATTESTATION_BYTES: u64 = 512 * 1024 * 1024;
/// Maximum number of returned pointers checked for one query.
pub const MAX_POINTER_ATTESTATIONS_PER_QUERY: usize = 10;
const MAX_SCOPE_RECORD_BYTES: u64 = 64 * 1024;

#[derive(Debug, Clone, Error, PartialEq, Eq)]
#[error("{message}")]
pub struct PointerAttestationError {
    message: String,
}

impl PointerAttestationError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

type AttestationResult<T> = std::result::Result<T, PointerAttestationError>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum AttestedObjectKind {
    Commit,
    Tree,
    Chunk,
}

impl AttestedObjectKind {
    const fn max_bytes(self) -> u64 {
        match self {
            Self::Commit => MAX_COMMIT_OBJECT_BYTES,
            Self::Tree => MAX_TREE_OBJECT_BYTES,
            Self::Chunk => MAX_CHUNK_OBJECT_BYTES,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct ObjectKey {
    scope_id: String,
    kind: AttestedObjectKind,
    hash: String,
}

#[derive(Debug, Clone)]
enum CachedObject {
    Commit(CommitObject),
    Tree(TreeObject),
    Chunk(ChunkObject),
    Failure(PointerAttestationError),
}

/// A fixed-map, byte-bounded attestor for the evaluator's historical hits.
#[derive(Debug)]
pub struct PointerAttestor {
    /// Retained capability handles, indexed only after reading each bound
    /// scope's `scope.json` through its own `.kio` handle.
    scope_kio_dirs: HashMap<String, fs::File>,
    object_cache: HashMap<ObjectKey, CachedObject>,
    verified_bytes: u64,
}

impl PointerAttestor {
    /// Bind exactly `scopes` below `corpus_dir`; no descendants are discovered.
    ///
    /// A bad scope record fails construction: callers must not silently run a
    /// history attestation with only a subset of their declared corpus.
    pub fn new(corpus_dir: &Path, scopes: &[String]) -> AttestationResult<Self> {
        let corpus = BoundCorpus::bind(corpus_dir, scopes)
            .map_err(|_| PointerAttestationError::new("invalid evaluator corpus boundary"))?;
        Self::from_bound_corpus(&corpus)
    }

    /// Construct an attestor from an already-bound corpus. Public paths are
    /// deliberately not consulted after this point.
    pub fn from_bound_corpus(corpus: &BoundCorpus) -> AttestationResult<Self> {
        let mut scope_kio_dirs = HashMap::new();
        for scope in corpus.scopes() {
            let kio = scope
                .try_clone_kio_handle()
                .map_err(|_| PointerAttestationError::new("scope capability unavailable"))?;
            let scope_id = read_scope_id(&kio)?;
            if scope_kio_dirs.insert(scope_id, kio).is_some() {
                return Err(PointerAttestationError::new(
                    "duplicate scope_id in evaluator corpus",
                ));
            }
        }
        Ok(Self {
            scope_kio_dirs,
            object_cache: HashMap::new(),
            verified_bytes: 0,
        })
    }

    #[must_use]
    pub const fn verified_bytes(&self) -> u64 {
        self.verified_bytes
    }

    /// Attest one JSON evidence-pointer value.
    pub fn attest(&mut self, value: &Value) -> AttestationResult<()> {
        let pointer: EvidencePointer = serde_json::from_value(value.clone())
            .map_err(|_| PointerAttestationError::new("result has invalid evidence_pointer"))?;
        let validated = pointer
            .validate()
            .map_err(|error| PointerAttestationError::new(error.to_string()))?;
        let pointer = validated.as_pointer();
        let path = pointer
            .path_at_commit
            .as_deref()
            .filter(|path| !path.is_empty())
            .ok_or_else(|| PointerAttestationError::new("pointer has invalid path_at_commit"))?;

        let commit = self.read_commit(&pointer.scope_id, &pointer.commit)?;
        if pointer
            .tree
            .as_deref()
            .is_some_and(|tree| tree != commit.tree)
        {
            return Err(PointerAttestationError::new(
                "pointer tree does not match commit",
            ));
        }
        let tree = self.read_tree(&pointer.scope_id, &commit.tree)?;
        let entry = tree
            .entries
            .iter()
            .find(|entry| entry.path == path)
            .ok_or_else(|| PointerAttestationError::new("tree does not contain pointer path"))?;
        if entry.raw_hash != pointer.raw_hash {
            return Err(PointerAttestationError::new(
                "tree path raw_hash does not match pointer",
            ));
        }
        let normalize = entry
            .normalize
            .as_ref()
            .ok_or_else(|| PointerAttestationError::new("tree path has no normalized identity"))?;
        if normalize.tool_profile_hash != pointer.tool_profile_hash {
            return Err(PointerAttestationError::new(
                "tree path profile does not match pointer",
            ));
        }

        let chunk = self.read_chunk(&pointer.scope_id, &pointer.chunk_hash)?;
        if chunk.raw_hash != pointer.raw_hash {
            return Err(PointerAttestationError::new(
                "chunk raw_hash does not match pointer",
            ));
        }
        if chunk.tool_profile_hash != pointer.tool_profile_hash {
            return Err(PointerAttestationError::new(
                "chunk profile does not match pointer",
            ));
        }
        if chunk.r#gen != normalize.r#gen {
            return Err(PointerAttestationError::new(
                "chunk generation does not match tree path",
            ));
        }
        Ok(())
    }

    /// Attest direct pointer values, bounded to the supplied top `k`.
    pub fn attest_top_k(&mut self, pointers: &[Value], k: usize) -> Vec<AttestationResult<()>> {
        pointers
            .iter()
            .take(k.min(MAX_POINTER_ATTESTATIONS_PER_QUERY))
            .map(|value| self.attest(value))
            .collect()
    }

    /// Attest `response.results[*].evidence_pointer`, bounded to the top `k`.
    pub fn attest_response_top_k(
        &mut self,
        response: &Value,
        k: usize,
    ) -> Vec<AttestationResult<()>> {
        let Some(results) = response.get("results").and_then(Value::as_array) else {
            return vec![Err(PointerAttestationError::new("results is not an array"))];
        };
        results
            .iter()
            .take(k.min(MAX_POINTER_ATTESTATIONS_PER_QUERY))
            .map(|result| match result.as_object() {
                Some(result) => match result.get("evidence_pointer") {
                    Some(pointer) => self.attest(pointer),
                    None => Err(PointerAttestationError::new(
                        "result has no evidence_pointer",
                    )),
                },
                None => Err(PointerAttestationError::new("result is not an object")),
            })
            .collect()
    }

    fn read_commit(&mut self, scope_id: &str, hash: &str) -> AttestationResult<CommitObject> {
        match self.read_object(scope_id, AttestedObjectKind::Commit, hash)? {
            CachedObject::Commit(commit) => Ok(commit),
            _ => Err(PointerAttestationError::new("commit cache type mismatch")),
        }
    }

    fn read_tree(&mut self, scope_id: &str, hash: &str) -> AttestationResult<TreeObject> {
        match self.read_object(scope_id, AttestedObjectKind::Tree, hash)? {
            CachedObject::Tree(tree) => Ok(tree),
            _ => Err(PointerAttestationError::new("tree cache type mismatch")),
        }
    }

    fn read_chunk(&mut self, scope_id: &str, hash: &str) -> AttestationResult<ChunkObject> {
        match self.read_object(scope_id, AttestedObjectKind::Chunk, hash)? {
            CachedObject::Chunk(chunk) => Ok(chunk),
            _ => Err(PointerAttestationError::new("chunk cache type mismatch")),
        }
    }

    fn read_object(
        &mut self,
        scope_id: &str,
        kind: AttestedObjectKind,
        hash: &str,
    ) -> AttestationResult<CachedObject> {
        let key = ObjectKey {
            scope_id: scope_id.to_owned(),
            kind,
            hash: hash.to_owned(),
        };
        if let Some(cached) = self.object_cache.get(&key) {
            return match cached {
                CachedObject::Failure(error) => Err(error.clone()),
                object => Ok(object.clone()),
            };
        }
        let result = self.read_uncached(scope_id, kind, hash);
        let cached = match &result {
            Ok(object) => object.clone(),
            Err(error) => CachedObject::Failure(error.clone()),
        };
        self.object_cache.insert(key, cached);
        result
    }

    fn read_uncached(
        &mut self,
        scope_id: &str,
        kind: AttestedObjectKind,
        hash: &str,
    ) -> AttestationResult<CachedObject> {
        let kio_dir = self
            .scope_kio_dirs
            .get(scope_id)
            .ok_or_else(|| {
                PointerAttestationError::new("pointer scope_id is not in the synthetic corpus")
            })?
            .try_clone()
            .map_err(|_| PointerAttestationError::new("scope capability unavailable"))?;
        // `ObjectStore` owns exact object-size enforcement but does not accept a
        // caller budget. Reserve the maximum before opening so a failed/corrupt
        // object can never push this global evaluator bound past its limit.
        if self.verified_bytes > MAX_POINTER_ATTESTATION_BYTES - kind.max_bytes() {
            return Err(PointerAttestationError::new(
                "pointer attestation byte bound exhausted",
            ));
        }
        match kind {
            AttestedObjectKind::Commit | AttestedObjectKind::Tree => {
                let object_kind = match kind {
                    AttestedObjectKind::Commit => ObjectKind::Commit,
                    AttestedObjectKind::Tree => ObjectKind::Tree,
                    AttestedObjectKind::Chunk => unreachable!(),
                };
                let bytes = self.read_cas_object(&kio_dir, object_kind, hash)?;
                match kind {
                    AttestedObjectKind::Commit => {
                        let commit: CommitObject =
                            serde_json::from_slice(&bytes).map_err(|_| {
                                PointerAttestationError::new("commit object is not valid JSON")
                            })?;
                        commit.validate().map_err(core_error)?;
                        Ok(CachedObject::Commit(commit))
                    }
                    AttestedObjectKind::Tree => {
                        let tree: TreeObject = serde_json::from_slice(&bytes).map_err(|_| {
                            PointerAttestationError::new("tree object is not valid JSON")
                        })?;
                        tree.validate().map_err(core_error)?;
                        if tree.entries.len() > MAX_TREE_ENTRIES {
                            return Err(PointerAttestationError::new(
                                "tree entries exceed attestation bound",
                            ));
                        }
                        Ok(CachedObject::Tree(tree))
                    }
                    AttestedObjectKind::Chunk => unreachable!(),
                }
            }
            AttestedObjectKind::Chunk => {
                let chunk = self.read_chunk_object(&kio_dir, hash)?;
                Ok(CachedObject::Chunk(chunk))
            }
        }
    }

    fn read_cas_object(
        &mut self,
        kio_dir: &fs::File,
        object_kind: ObjectKind,
        hash: &str,
    ) -> AttestationResult<Vec<u8>> {
        let result = read_cap_cas_file(
            kio_dir,
            object_kind.directory(),
            hash,
            object_kind.max_bytes(),
        );
        let (bytes, consumed) = match result {
            Ok(value) => value,
            Err(error) => {
                self.charge(error.consumed)?;
                return Err(error.error);
            }
        };
        self.charge(consumed)?;
        if hash_bytes(&bytes) != hash {
            return Err(PointerAttestationError::new("CAS object hash mismatch"));
        }
        Ok(bytes)
    }

    fn read_chunk_object(
        &mut self,
        kio_dir: &fs::File,
        hash: &str,
    ) -> AttestationResult<ChunkObject> {
        let result = read_cap_cas_file(kio_dir, "chunks", hash, MAX_CHUNK_OBJECT_BYTES);
        let (bytes, consumed) = match result {
            Ok(value) => value,
            Err(error) => {
                self.charge(error.consumed)?;
                return Err(error.error);
            }
        };
        self.charge(consumed)?;
        let chunk: ChunkObject = serde_json::from_slice(&bytes)
            .map_err(|_| PointerAttestationError::new("chunk object schema is invalid"))?;
        chunk.validate().map_err(core_error)?;
        if chunk.identity_hash().map_err(core_error)? != hash {
            return Err(PointerAttestationError::new(
                "chunk semantic identity does not match its fan-out key",
            ));
        }
        let canonical = canonical_json_bytes(
            &serde_json::to_value(&chunk)
                .map_err(|_| PointerAttestationError::new("chunk object schema is invalid"))?,
        )
        .map_err(core_error)?;
        if canonical != bytes {
            return Err(PointerAttestationError::new(
                "chunk object is not canonical JSON",
            ));
        }
        Ok(chunk)
    }

    fn charge(&mut self, bytes: u64) -> AttestationResult<()> {
        self.verified_bytes = self
            .verified_bytes
            .checked_add(bytes)
            .ok_or_else(|| PointerAttestationError::new("pointer attestation byte overflow"))?;
        if self.verified_bytes > MAX_POINTER_ATTESTATION_BYTES {
            return Err(PointerAttestationError::new(
                "pointer attestation byte bound exhausted",
            ));
        }
        Ok(())
    }
}

fn core_error(error: kio_core::KioError) -> PointerAttestationError {
    PointerAttestationError::new(error.to_string())
}

fn read_scope_id(kio_dir: &fs::File) -> AttestationResult<String> {
    let bytes = read_cap_regular_file(kio_dir, "scope.json", MAX_SCOPE_RECORD_BYTES)
        .map_err(|_| PointerAttestationError::new("scope record unavailable"))?;
    let value: Value = serde_json::from_slice(&bytes)
        .map_err(|_| PointerAttestationError::new("scope record is not valid JSON"))?;
    let object = value
        .as_object()
        .ok_or_else(|| PointerAttestationError::new("scope record is not a JSON object"))?;
    if object.get("kio_format_version").and_then(Value::as_str) != Some(KIO_FORMAT_VERSION) {
        return Err(PointerAttestationError::new(
            "scope record has incompatible format version",
        ));
    }
    let scope_id = object
        .get("scope_id")
        .and_then(Value::as_str)
        .filter(|value| is_ulid(value))
        .ok_or_else(|| PointerAttestationError::new("scope record has invalid scope_id"))?;
    Ok(scope_id.to_owned())
}

#[derive(Debug)]
struct CapReadError {
    error: PointerAttestationError,
    consumed: u64,
}

/// Read the exact portable CAS slot by walking every fan-out component from
/// the retained `.kio` handle. Every directory and the final regular file is
/// opened no-follow; no public pathname is reconstructed.
fn read_cap_cas_file(
    kio_dir: &fs::File,
    kind_dir: &str,
    hash: &str,
    max_bytes: u64,
) -> Result<(Vec<u8>, u64), CapReadError> {
    if !is_hash(hash) {
        return Err(CapReadError {
            error: PointerAttestationError::new("invalid CAS object hash"),
            consumed: 0,
        });
    }
    let digest = &hash["sha256:".len()..];
    let mut directory = kio_dir.try_clone().map_err(|_| CapReadError {
        error: PointerAttestationError::new("CAS object unavailable"),
        consumed: 0,
    })?;
    for component in ["objects", kind_dir, &digest[..2], &digest[2..4]] {
        directory = cap_fs::open_dir_nofollow(&directory, Path::new(component)).map_err(|_| {
            CapReadError {
                error: PointerAttestationError::new("CAS object unavailable"),
                consumed: 0,
            }
        })?;
    }
    read_cap_regular_file_accounted(&directory, digest, max_bytes)
}

fn read_cap_regular_file(
    directory: &fs::File,
    name: &str,
    max_bytes: u64,
) -> AttestationResult<Vec<u8>> {
    read_cap_regular_file_accounted(directory, name, max_bytes)
        .map(|(bytes, _)| bytes)
        .map_err(|error| error.error)
}

fn read_cap_regular_file_accounted(
    directory: &fs::File,
    name: &str,
    max_bytes: u64,
) -> Result<(Vec<u8>, u64), CapReadError> {
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let mut file =
        cap_fs::open(directory, Path::new(name), &options).map_err(|_| CapReadError {
            error: PointerAttestationError::new("CAS object unavailable"),
            consumed: 0,
        })?;
    let metadata = file.metadata().map_err(|_| CapReadError {
        error: PointerAttestationError::new("CAS object unavailable"),
        consumed: 0,
    })?;
    if !metadata.is_file() {
        return Err(CapReadError {
            error: PointerAttestationError::new("CAS object unavailable"),
            consumed: 0,
        });
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.nlink() != 1 {
            return Err(CapReadError {
                error: PointerAttestationError::new("CAS object unavailable"),
                consumed: 0,
            });
        }
    }
    if metadata.len() > max_bytes {
        return Err(CapReadError {
            error: PointerAttestationError::new("CAS object exceeds its byte limit"),
            consumed: 0,
        });
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    let mut limited = file.by_ref().take(max_bytes.saturating_add(1));
    match limited.read_to_end(&mut bytes) {
        Ok(_) if bytes.len() as u64 <= max_bytes => {
            let consumed = bytes.len() as u64;
            Ok((bytes, consumed))
        }
        Ok(_) => Err(CapReadError {
            error: PointerAttestationError::new("CAS object exceeds its byte limit"),
            consumed: bytes.len() as u64,
        }),
        Err(_) => Err(CapReadError {
            error: PointerAttestationError::new("CAS object unavailable"),
            consumed: bytes.len() as u64,
        }),
    }
}

fn is_ulid(value: &str) -> bool {
    value.len() == 26
        && value.bytes().all(|byte| {
            matches!(byte, b'0'..=b'9' | b'A'..=b'H' | b'J'..=b'K' | b'M'..=b'N' | b'P'..=b'T' | b'V'..=b'Z')
        })
}

#[cfg(test)]
mod tests {
    use std::fs;

    use kio_core::{
        cas::{ObjectKind, ObjectStore, hash_bytes},
        dag::{CommitObject, CommitStats, CommitType, NormalizeRef, TreeEntry, build_tree},
        scope::Repository,
    };
    use serde_json::{Value, json};
    use tempfile::TempDir;

    use crate::boundary::BoundCorpus;

    use super::PointerAttestor;

    const RAW_HASH: &str =
        "sha256:1111111111111111111111111111111111111111111111111111111111111111";
    const PROFILE_HASH: &str =
        "sha256:2222222222222222222222222222222222222222222222222222222222222222";
    const MANIFEST_HASH: &str =
        "sha256:3333333333333333333333333333333333333333333333333333333333333333";
    const TOOL_LOCK_HASH: &str =
        "sha256:4444444444444444444444444444444444444444444444444444444444444444";

    struct Fixture {
        root: TempDir,
        scope: String,
        pointer: Value,
    }

    fn fixture() -> Fixture {
        let root = tempfile::tempdir().unwrap();
        let scope = "research".to_owned();
        let scope_root = root.path().join(&scope);
        fs::create_dir(&scope_root).unwrap();
        let repo = Repository::init(&scope_root).unwrap();
        let scope_id = repo.scope_identity().unwrap().scope_id;
        let store = ObjectStore::new(repo.kio_dir());

        let text = "historical pointer attestation";
        let text_hash = hash_bytes(text.as_bytes());
        let chunk = kio_core::cas::ChunkObject {
            spec_version: 1,
            raw_hash: RAW_HASH.to_owned(),
            tool_profile_hash: PROFILE_HASH.to_owned(),
            r#gen: 3,
            unit_key: "section:old".to_owned(),
            unit_content_hash: text_hash.clone(),
            heading_path: vec!["Old Document".to_owned(), "Historical".to_owned()],
            section_id: Some("old-document/historical".to_owned()),
            byte_start: 0,
            byte_end: text.len() as u64,
            text_hash,
            text: text.to_owned(),
        };
        let chunk_hash = store.write_chunk(&chunk).unwrap();
        let tree = build_tree(vec![TreeEntry {
            path: "old-name.md".to_owned(),
            entry_type: "file".to_owned(),
            raw_hash: RAW_HASH.to_owned(),
            normalize: Some(NormalizeRef {
                tool_profile_hash: PROFILE_HASH.to_owned(),
                r#gen: 3,
                manifest_hash: MANIFEST_HASH.to_owned(),
            }),
        }])
        .unwrap();
        let (tree_hash, _) = store
            .write_json(ObjectKind::Tree, &serde_json::to_value(&tree).unwrap())
            .unwrap();
        let commit = CommitObject::new(
            tree_hash.clone(),
            vec![],
            "2026-07-13T00:00:00Z".to_owned(),
            "synthetic attestation".to_owned(),
            TOOL_LOCK_HASH.to_owned(),
            CommitStats {
                files_added: 1,
                files_modified: 0,
                files_deleted: 0,
            },
            CommitType::Manual,
        )
        .unwrap();
        let (commit_hash, _) = store
            .write_json(ObjectKind::Commit, &serde_json::to_value(&commit).unwrap())
            .unwrap();
        Fixture {
            root,
            scope,
            pointer: json!({
                "schema_version": 1,
                "scope_id": scope_id,
                "commit": commit_hash,
                "tree": tree_hash,
                "raw_hash": RAW_HASH,
                "tool_profile_hash": PROFILE_HASH,
                "chunk_hash": chunk_hash,
                "path_at_commit": "old-name.md",
            }),
        }
    }

    #[test]
    fn attests_valid_pointer_and_caches_all_cas_reads() {
        let fixture = fixture();
        let mut attestor =
            PointerAttestor::new(fixture.root.path(), std::slice::from_ref(&fixture.scope))
                .unwrap();
        attestor.attest(&fixture.pointer).unwrap();
        let verified = attestor.verified_bytes();
        attestor.attest(&fixture.pointer).unwrap();
        assert_eq!(attestor.verified_bytes(), verified);
    }

    #[test]
    fn rejects_tree_path_hash_and_identity_tuple_mismatches() {
        let fixture = fixture();
        let mut attestor =
            PointerAttestor::new(fixture.root.path(), std::slice::from_ref(&fixture.scope))
                .unwrap();
        let mut wrong_path = fixture.pointer.clone();
        wrong_path["path_at_commit"] = json!("current-name.md");
        assert!(attestor.attest(&wrong_path).is_err());

        let mut wrong_tree = fixture.pointer.clone();
        wrong_tree["tree"] =
            json!("sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
        assert!(attestor.attest(&wrong_tree).is_err());

        let mut wrong_raw = fixture.pointer.clone();
        wrong_raw["raw_hash"] =
            json!("sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
        assert!(attestor.attest(&wrong_raw).is_err());

        let mut wrong_profile = fixture.pointer.clone();
        wrong_profile["tool_profile_hash"] =
            json!("sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc");
        assert!(attestor.attest(&wrong_profile).is_err());
    }

    #[test]
    fn rejects_scope_not_declared_by_fixed_corpus_map() {
        let fixture = fixture();
        let mut attestor =
            PointerAttestor::new(fixture.root.path(), std::slice::from_ref(&fixture.scope))
                .unwrap();
        let mut pointer = fixture.pointer.clone();
        pointer["scope_id"] = json!("01ARZ3NDEKTSV4RRFFQ69G5FAV");
        assert!(attestor.attest(&pointer).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn bound_attestor_keeps_original_scope_after_public_path_is_replaced() {
        use std::os::unix::fs::symlink;

        let fixture = fixture();
        let corpus =
            BoundCorpus::bind(fixture.root.path(), std::slice::from_ref(&fixture.scope)).unwrap();
        let mut attestor = PointerAttestor::from_bound_corpus(&corpus).unwrap();

        let public_scope = fixture.root.path().join(&fixture.scope);
        let retained_scope = fixture.root.path().join("retained-research");
        let victim = fixture.root.path().join("victim");
        fs::create_dir(&victim).unwrap();
        fs::rename(&public_scope, &retained_scope).unwrap();
        symlink(&victim, &public_scope).unwrap();

        // A pathname-based attestor would now read the replacement (or follow
        // its link). The retained `.kio` capability can only reach the scope
        // that was bound before the replacement.
        attestor.attest(&fixture.pointer).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symlinked_scope_record() {
        use std::os::unix::fs::symlink;

        let fixture = fixture();
        let scope_json = fixture
            .root
            .path()
            .join(&fixture.scope)
            .join(".kio/scope.json");
        let target = fixture.root.path().join("outside.json");
        fs::write(
            &target,
            br#"{"kio_format_version":"0.1.0","scope_id":"01ARZ3NDEKTSV4RRFFQ69G5FAV"}"#,
        )
        .unwrap();
        fs::remove_file(&scope_json).unwrap();
        symlink(&target, &scope_json).unwrap();
        assert!(
            PointerAttestor::new(fixture.root.path(), std::slice::from_ref(&fixture.scope))
                .is_err()
        );
    }
}
