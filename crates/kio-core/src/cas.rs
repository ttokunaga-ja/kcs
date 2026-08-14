//! Content-addressed storage primitives.

use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, Write};
use std::path::{Path, PathBuf};
#[cfg(unix)]
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::error::{IoResultExt, KioError, Result};
use crate::purge::sync_directory;

pub const CAS_STREAM_BUFFER_BYTES: usize = 64 * 1024;
pub const MAX_RAW_OBJECT_BYTES: u64 = 512 * 1024 * 1024;
pub const MAX_TREE_OBJECT_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_COMMIT_OBJECT_BYTES: u64 = 1024 * 1024;
/// Semantic chunk objects contain bounded normalized text, never raw file bytes.
pub const MAX_CHUNK_OBJECT_BYTES: u64 = 128 * 1024 * 1024;
/// Normalized-unit objects are canonical JSON representations of a single
/// markdownized prepared unit. They share the existing normalized unit size
/// ceiling and are read as one bounded immutable CAS body.
pub const MAX_NORMALIZED_UNIT_OBJECT_BYTES: u64 = 128 * 1024 * 1024;

/// An embedding object is an identity header plus one base64 vector line.
/// The adopted profile is 768 f32 (03 §7), so a real object runs ~4.4 KB; the
/// cap is generous enough for any plausible future width and still small enough
/// that a corrupt length is rejected before it is read.
pub const MAX_EMBEDDING_OBJECT_BYTES: u64 = 1024 * 1024;
/// A normalized-instance manifest is deliberately much smaller than a raw or
/// prepared object. Keeping the limit at the CAS boundary prevents inventory
/// and fsck from hashing a pathologically large object before the semantic
/// manifest reader can apply its own bound.
pub const MAX_MANIFEST_OBJECT_BYTES: u64 = 8 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContentObjectKind {
    Prepared,
    Image,
    /// PB01/PB02 (step4b-contract-tests-p2b.md §A/§B, 10-operations.md
    /// §7.5.1 L489): content-addressed embedding object (vector + declared
    /// dimensions), stored under `objects/embeddings/`.
    Embedding,
    /// PB02 (10 §7.5.1 L489): content-addressed manifest object, stored
    /// under `objects/manifests/`.
    Manifest,
    /// PB02 (10 §7.5.1 L489): content-addressed tool-lock object (canonical
    /// JCS bytes content hash — 03 §5.2), stored under `objects/toollocks/`.
    Toollock,
    /// Immutable normalized-unit JSON object, stored under
    /// `objects/normalized_unit_objects/`.
    NormalizedUnit,
}

impl ContentObjectKind {
    #[must_use]
    pub const fn directory(self) -> &'static str {
        match self {
            Self::Prepared => "prepared",
            Self::Image => "image",
            Self::Embedding => "embeddings",
            Self::Manifest => "manifests",
            Self::Toollock => "toollocks",
            Self::NormalizedUnit => "normalized_unit_objects",
        }
    }

    #[must_use]
    pub const fn object_type(self) -> &'static str {
        match self {
            Self::Prepared => "prepared",
            Self::Image => "image",
            Self::Embedding => "embedding",
            Self::Manifest => "manifest",
            Self::Toollock => "toollock",
            Self::NormalizedUnit => "normalized_unit",
        }
    }

    #[must_use]
    const fn max_bytes(self) -> u64 {
        match self {
            Self::Embedding => MAX_EMBEDDING_OBJECT_BYTES,
            Self::Manifest => MAX_MANIFEST_OBJECT_BYTES,
            Self::NormalizedUnit => MAX_NORMALIZED_UNIT_OBJECT_BYTES,
            Self::Prepared | Self::Image | Self::Toollock => MAX_RAW_OBJECT_BYTES,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoredContentObjectMetadata {
    pub kind: ContentObjectKind,
    pub hash: String,
    pub size_bytes: u64,
}

/// Durable Step 4 chunk object (03-data-model §8.1).
///
/// Its storage key is the semantic identity hash computed from the first eight
/// fields, not the content hash of this JSON payload. Keeping this type in core
/// prevents SQLite/JSONL acceleration rows from becoming Evidence truth.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ChunkObject {
    pub spec_version: u64,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub r#gen: u64,
    pub unit_key: String,
    /// Hash of the exact normalized Markdown bytes. This is the stable content
    /// axis in chunk identity: a same-gen body correction gets a new chunk,
    /// while a byte-identical resurrection retains the old pointer identity.
    pub unit_content_hash: String,
    pub heading_path: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub section_id: Option<String>,
    /// Unit-local UTF-8 byte offset, 0-based half-open (03 §8.1). Always
    /// present in a valid chunk object — part of the identity tuple, not an
    /// optional field like `section_id`.
    pub byte_start: u64,
    pub byte_end: u64,
    pub text_hash: String,
    pub text: String,
}

/// One embedding vector as CAS truth (03 §8.1, 04 §4.3).
///
/// The `embeddings` SQLite table and `chunk_vec` are an acceleration layer over
/// this — "真実は `objects/` にある", and `kio repair rebuild-db` rebuilds in the
/// order `objects/` → `embeddings` → `chunk_vec`. Until R25-6 the object did not
/// exist: `rebuild-db` snapshotted vectors out of the very database it was about
/// to replace, so losing `sqlite.db` meant buying every vector again from the
/// API. The user's knowledge was never at risk (that lives in
/// `objects/normalized`), but the money and the wall-clock were.
///
/// The stored bytes are fixed by 03 §8.1 as
/// `JCS(identity fields) + LF + base64(vector) + LF + lower_hex64(sha256(vector bytes))`
/// — a text header a human can read next to a compact body, plus a digest of the
/// body alone. The trailing digest is not redundant with the storage key: the key
/// is the hash of the IDENTITY (what this vector is OF), so nothing else would
/// notice a bit flip inside the vector itself.
#[derive(Debug, Clone, PartialEq)]
pub struct EmbeddingObject {
    pub spec_version: u64,
    pub target_type: String,
    pub target_hash: String,
    pub profile_hash: String,
    pub modality: String,
    pub dimensions: u64,
    pub distance: String,
    /// 07 §5.3's contextual-embedding addendum (2026-07-24): the humanized
    /// filename prefix folded into the adapter INPUT, and therefore into the
    /// identity. `None` omits the key entirely rather than writing a JSON null,
    /// so a non-chunk target hashes byte-for-byte as it did before the addendum.
    pub context: Option<String>,
    pub vector: Vec<f32>,
}

impl EmbeddingObject {
    /// The identity fields alone, as the JSON whose JCS hash is the storage key.
    ///
    /// Split out from [`Self::identity_hash`] so a caller that has no vector yet
    /// — the embedding lane deciding whether it already owns this vector — can
    /// address the object without inventing one.
    #[must_use]
    pub fn identity_value(
        target_type: &str,
        target_hash: &str,
        profile_hash: &str,
        modality: &str,
        dimensions: u64,
        distance: &str,
        context: Option<&str>,
    ) -> Value {
        let mut value = Map::new();
        value.insert("dimensions".to_owned(), Value::from(dimensions));
        value.insert("distance".to_owned(), Value::from(distance));
        value.insert("modality".to_owned(), Value::from(modality));
        value.insert("profile_hash".to_owned(), Value::from(profile_hash));
        value.insert("spec_version".to_owned(), Value::from(1));
        value.insert("target_hash".to_owned(), Value::from(target_hash));
        value.insert("target_type".to_owned(), Value::from(target_type));
        if let Some(context) = context {
            value.insert("context".to_owned(), Value::from(context));
        }
        Value::Object(value)
    }

    /// The storage key: `"sha256:" + base16(sha256(JCS(identity fields)))`.
    pub fn identity_hash(&self) -> Result<String> {
        self.validate()?;
        hash_json(&Self::identity_value(
            &self.target_type,
            &self.target_hash,
            &self.profile_hash,
            &self.modality,
            self.dimensions,
            &self.distance,
            self.context.as_deref(),
        ))
    }

    /// The canonical stored bytes (03 §8.1).
    pub fn to_bytes(&self) -> Result<Vec<u8>> {
        self.validate()?;
        let header = canonical_json_bytes(&Self::identity_value(
            &self.target_type,
            &self.target_hash,
            &self.profile_hash,
            &self.modality,
            self.dimensions,
            &self.distance,
            self.context.as_deref(),
        ))?;
        let vector_bytes = vector_to_le_bytes(&self.vector);
        let mut out = header;
        out.push(b'\n');
        out.extend_from_slice(base64_encode(&vector_bytes).as_bytes());
        out.push(b'\n');
        out.extend_from_slice(lower_hex(&Sha256::digest(&vector_bytes)).as_bytes());
        Ok(out)
    }

    /// Parse and fully verify stored bytes.
    ///
    /// Every check 10 §7.5.1 asks `fsck` for lives here rather than in the
    /// caller, so a read through any path gets all of them: the vector's length
    /// matches the declared `dimensions`, no component is NaN or infinite, and
    /// the trailing digest matches the body.
    pub fn from_bytes(bytes: &[u8]) -> Result<Self> {
        let text = std::str::from_utf8(bytes)
            .map_err(|_| embedding_corrupt_error("embedding object is not UTF-8", None))?;
        let mut lines = text.split('\n');
        let (Some(header), Some(body), Some(digest)) = (lines.next(), lines.next(), lines.next())
        else {
            return Err(embedding_corrupt_error(
                "embedding object must be header, vector and digest on three lines",
                None,
            ));
        };
        if lines.next().is_some() {
            return Err(embedding_corrupt_error(
                "embedding object has trailing content after the digest",
                None,
            ));
        }
        let value: Value = serde_json::from_str(header)
            .map_err(|error| embedding_corrupt_error(&error.to_string(), None))?;
        let object = value.as_object().ok_or_else(|| {
            embedding_corrupt_error("embedding object header must be a JSON object", None)
        })?;
        let string = |key: &str| -> Result<String> {
            object
                .get(key)
                .and_then(Value::as_str)
                .map(str::to_owned)
                .ok_or_else(|| {
                    embedding_corrupt_error(&format!("embedding header lacks {key}"), None)
                })
        };
        let dimensions = object
            .get("dimensions")
            .and_then(Value::as_u64)
            .ok_or_else(|| embedding_corrupt_error("embedding header lacks dimensions", None))?;
        let vector_bytes = base64_decode(body)?;
        if lower_hex(&Sha256::digest(&vector_bytes)) != digest {
            return Err(embedding_corrupt_error(
                "embedding vector digest does not match its bytes",
                None,
            ));
        }
        if vector_bytes.len() as u64 != dimensions.saturating_mul(4) {
            return Err(embedding_corrupt_error(
                "embedding vector length does not match declared dimensions",
                None,
            ));
        }
        let vector = vector_from_le_bytes(&vector_bytes);
        if vector.iter().any(|component| !component.is_finite()) {
            return Err(embedding_corrupt_error(
                "embedding vector holds a NaN or infinite component",
                None,
            ));
        }
        let parsed = Self {
            spec_version: object
                .get("spec_version")
                .and_then(Value::as_u64)
                .unwrap_or_default(),
            target_type: string("target_type")?,
            target_hash: string("target_hash")?,
            profile_hash: string("profile_hash")?,
            modality: string("modality")?,
            dimensions,
            distance: string("distance")?,
            context: object
                .get("context")
                .and_then(Value::as_str)
                .map(str::to_owned),
            vector,
        };
        parsed.validate()?;
        Ok(parsed)
    }

    pub fn validate(&self) -> Result<()> {
        if self.spec_version != 1 {
            return Err(embedding_corrupt_error(
                "embedding spec_version must be exactly 1",
                None,
            ));
        }
        for (name, value) in [
            ("target_type", &self.target_type),
            ("target_hash", &self.target_hash),
            ("profile_hash", &self.profile_hash),
            ("modality", &self.modality),
            ("distance", &self.distance),
        ] {
            if value.is_empty() {
                return Err(embedding_corrupt_error(
                    &format!("embedding {name} must not be empty"),
                    None,
                ));
            }
        }
        if self.dimensions == 0 || self.vector.len() as u64 != self.dimensions {
            return Err(embedding_corrupt_error(
                "embedding vector length must equal its declared dimensions",
                None,
            ));
        }
        if self.vector.iter().any(|component| !component.is_finite()) {
            return Err(embedding_corrupt_error(
                "embedding vector holds a NaN or infinite component",
                None,
            ));
        }
        Ok(())
    }
}

impl ChunkObject {
    /// Recompute the path-independent semantic identity frozen in docs/03 §8.1.
    pub fn identity_hash(&self) -> Result<String> {
        self.validate()?;
        let mut value = Map::new();
        value.insert("byte_end".to_owned(), Value::from(self.byte_end));
        value.insert("byte_start".to_owned(), Value::from(self.byte_start));
        value.insert("gen".to_owned(), Value::from(self.r#gen));
        value.insert(
            "heading_path".to_owned(),
            serde_json::to_value(&self.heading_path)
                .map_err(|error| KioError::schema(error.to_string()))?,
        );
        value.insert("raw_hash".to_owned(), Value::from(self.raw_hash.clone()));
        if let Some(section_id) = self.section_id.as_ref().filter(|value| !value.is_empty()) {
            value.insert("section_id".to_owned(), Value::from(section_id.clone()));
        }
        value.insert("spec_version".to_owned(), Value::from(1));
        value.insert(
            "tool_profile_hash".to_owned(),
            Value::from(self.tool_profile_hash.clone()),
        );
        value.insert("unit_key".to_owned(), Value::from(self.unit_key.clone()));
        value.insert(
            "unit_content_hash".to_owned(),
            Value::from(self.unit_content_hash.clone()),
        );
        // Null / absent fields are omitted from the identity object.
        value.retain(|_, value| !value.is_null());
        hash_json(&Value::Object(value))
    }

    pub fn validate(&self) -> Result<()> {
        if self.spec_version != 1 {
            return Err(chunk_corrupt_error(
                "chunk spec_version must be exactly 1",
                None,
            ));
        }
        if !is_hash(&self.raw_hash)
            || !is_hash(&self.tool_profile_hash)
            || !is_hash(&self.unit_content_hash)
            || !is_hash(&self.text_hash)
        {
            return Err(chunk_corrupt_error(
                "chunk contains an invalid logical hash",
                None,
            ));
        }
        if self.unit_key.is_empty() {
            return Err(chunk_corrupt_error(
                "chunk unit_key must not be empty",
                None,
            ));
        }
        if self.byte_start > self.byte_end {
            return Err(chunk_corrupt_error(
                "chunk byte_start/byte_end must be an ordered pair",
                None,
            ));
        }
        if hash_bytes(self.text.as_bytes()) != self.text_hash {
            return Err(chunk_corrupt_error(
                "chunk text_hash does not match exact text",
                None,
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ObjectKind {
    Raw,
    Tree,
    Commit,
}

impl ObjectKind {
    #[must_use]
    pub const fn directory(self) -> &'static str {
        match self {
            Self::Raw => "raw",
            Self::Tree => "trees",
            Self::Commit => "commits",
        }
    }

    #[must_use]
    pub const fn object_type(self) -> &'static str {
        match self {
            Self::Raw => "raw",
            Self::Tree => "tree",
            Self::Commit => "commit",
        }
    }

    #[must_use]
    pub const fn max_bytes(self) -> u64 {
        match self {
            Self::Raw => MAX_RAW_OBJECT_BYTES,
            Self::Tree => MAX_TREE_OBJECT_BYTES,
            Self::Commit => MAX_COMMIT_OBJECT_BYTES,
        }
    }
}

#[derive(Debug, Clone)]
pub struct StoredObject {
    pub kind: ObjectKind,
    pub hash: String,
    pub bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoredObjectMetadata {
    pub kind: ObjectKind,
    pub hash: String,
    pub size_bytes: u64,
}

#[derive(Debug)]
pub struct AccountedReadError {
    pub error: KioError,
    pub consumed_bytes: u64,
}

#[derive(Debug, Clone)]
pub struct ObjectStore {
    kio_dir: PathBuf,
    /// Scheduled writers retain these handles before taking their writer
    /// boundary.  The ambient `.kio/objects` pathname is deliberately never
    /// consulted by the bound read/write subset below.
    #[cfg(unix)]
    bound: Option<BoundObjectDirs>,
}

#[cfg(unix)]
#[derive(Debug, Clone)]
struct BoundObjectDirs {
    kio: Arc<File>,
    objects: Arc<File>,
    raw: Arc<File>,
    trees: Arc<File>,
    commits: Arc<File>,
}

#[cfg(unix)]
#[derive(Debug)]
pub struct BoundRawStage {
    parent: Arc<File>,
    name: String,
    file: File,
    raw_hash: String,
    size_bytes: u64,
}
#[cfg(unix)]
impl BoundRawStage {
    #[must_use]
    pub fn raw_hash(&self) -> &str {
        &self.raw_hash
    }
    #[must_use]
    pub const fn size_bytes(&self) -> u64 {
        self.size_bytes
    }
}
#[cfg(unix)]
impl Drop for BoundRawStage {
    fn drop(&mut self) {
        if !self.name.is_empty() {
            let _ = bound_remove(&self.parent, &self.name);
        }
    }
}

impl ObjectStore {
    #[must_use]
    pub fn new(kio_dir: impl Into<PathBuf>) -> Self {
        Self {
            kio_dir: kio_dir.into(),
            #[cfg(unix)]
            bound: None,
        }
    }

    /// Construct a CAS capability rooted in an already retained `.kio`
    /// directory.  This is intentionally narrow: it binds precisely the
    /// namespaces used by the scheduled snapshot writer, and refuses a
    /// missing/replaced/symlinked object namespace rather than recovering via
    /// the public pathname.
    #[cfg(unix)]
    pub fn from_bound_kio(kio: &File) -> Result<Self> {
        let objects = bound_open_dir(kio, "objects")?;
        let raw = bound_open_dir(&objects, ObjectKind::Raw.directory())?;
        let trees = bound_open_dir(&objects, ObjectKind::Tree.directory())?;
        let commits = bound_open_dir(&objects, ObjectKind::Commit.directory())?;
        Ok(Self {
            kio_dir: PathBuf::from("."),
            bound: Some(BoundObjectDirs {
                kio: Arc::new(
                    kio.try_clone()
                        .map_err(|e| KioError::io(e.to_string(), ".kio"))?,
                ),
                objects: Arc::new(objects),
                raw: Arc::new(raw),
                trees: Arc::new(trees),
                commits: Arc::new(commits),
            }),
        })
    }

    pub fn write_raw(&self, bytes: &[u8]) -> Result<String> {
        let hash = hash_bytes(bytes);
        self.write_object_bytes(ObjectKind::Raw, &hash, bytes)?;
        Ok(hash)
    }

    #[cfg(unix)]
    pub fn stage_raw_from_reader<R: Read>(
        &self,
        reader: &mut R,
        max_bytes: u64,
    ) -> Result<BoundRawStage> {
        self.bound
            .as_ref()
            .ok_or_else(|| {
                KioError::invalid_usage("bound raw staging requires a retained ObjectStore")
            })?
            .stage_raw_from_reader(reader, max_bytes)
    }

    #[cfg(unix)]
    pub fn cleanup_bound_raw_stages(&self) -> Result<()> {
        self.bound
            .as_ref()
            .ok_or_else(|| {
                KioError::invalid_usage("bound raw cleanup requires a retained ObjectStore")
            })?
            .cleanup_raw_ingest_orphans()
    }

    #[cfg(unix)]
    pub fn validate_bound_layout(&self) -> Result<()> {
        self.bound
            .as_ref()
            .ok_or_else(|| {
                KioError::invalid_usage("bound layout validation requires a retained ObjectStore")
            })?
            .validate_layout()
    }

    #[cfg(not(unix))]
    pub fn validate_bound_layout(&self) -> Result<()> {
        Err(KioError::new(
            "KIO-E-SNAPSHOT-PLATFORM-UNSUPPORTED-001",
            "scheduled snapshot publication requires retained filesystem capabilities",
            serde_json::json!({}),
            crate::error::ExitCode::PermanentFailure,
        ))
    }

    #[cfg(unix)]
    pub fn publish_bound_raw_stage(&self, stage: BoundRawStage) -> Result<(String, u64)> {
        self.bound
            .as_ref()
            .ok_or_else(|| {
                KioError::invalid_usage(
                    "bound raw stage publication requires a retained ObjectStore",
                )
            })?
            .publish_raw_stage(stage)
    }

    /// Repair one corrupt, single-representation raw CAS slot with verified
    /// working bytes. The destination is derived only from `expected_hash`; a
    /// canonical/legacy dual representation remains fail-closed. The caller must
    /// hold the scope store lock for the entire operation.
    pub fn repair_raw(&self, expected_hash: &str, bytes: &[u8]) -> Result<bool> {
        if !is_hash(expected_hash) || hash_bytes(bytes) != expected_hash {
            return Err(KioError::invalid_usage(
                "raw repair bytes do not match the expected hash",
            ));
        }
        if bytes.len() as u64 > ObjectKind::Raw.max_bytes() {
            return Err(object_size_error(
                ObjectKind::Raw,
                ObjectKind::Raw.max_bytes(),
                bytes.len() as u64,
            ));
        }
        self.ensure_object_parent(ObjectKind::Raw, expected_hash)?;
        let Some(path) = self.existing_object_path(ObjectKind::Raw, expected_hash)? else {
            self.write_object_bytes(ObjectKind::Raw, expected_hash, bytes)?;
            return Ok(true);
        };
        let path = path.as_path();
        if read_verified_object(path, ObjectKind::Raw, expected_hash, false).is_ok() {
            return Ok(false);
        }

        // Re-open through the hardened no-follow/single-link boundary and consume
        // the complete corrupt body before authorizing replacement. Unsafe links
        // and path swaps fail before any namespace mutation.
        let mut corrupt = open_regular_nofollow(path)?;
        let metadata = corrupt.metadata().kio_io(path)?;
        if metadata.len() > ObjectKind::Raw.max_bytes() {
            return Err(object_size_error(
                ObjectKind::Raw,
                ObjectKind::Raw.max_bytes(),
                metadata.len(),
            ));
        }
        let mut actual_hasher = Sha256::new();
        let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
        loop {
            let count = corrupt.read(&mut buffer).kio_io(path)?;
            if count == 0 {
                break;
            }
            actual_hasher.update(&buffer[..count]);
        }
        let actual = format!("sha256:{}", lower_hex(&actual_hasher.finalize()));
        if actual == expected_hash {
            return Err(corrupt_object_error(
                path,
                "raw repair observed an unstable CAS slot",
                expected_hash,
                Some(&actual),
            ));
        }

        let parent = path
            .parent()
            .ok_or_else(|| KioError::io("CAS path has no parent", path.display().to_string()))?;
        let (temp_path, mut temp) = create_private_temp(parent)?;
        let result = (|| -> Result<()> {
            temp.write_all(bytes).kio_io(&temp_path)?;
            temp.sync_all().kio_io(&temp_path)?;
            drop(temp);

            let quarantine = create_repair_quarantine(path, &corrupt)?;
            // MoveFileEx requires both path operands to be closed on Windows.
            // The verified quarantine hard link now pins the exact corrupt
            // object for rollback, so the original read handle can be released
            // without reopening or trusting its pathname.
            #[cfg(windows)]
            drop(corrupt);
            if let Err(error) = replace_file(&temp_path, path) {
                let _ = fs::remove_file(&quarantine);
                return Err(error);
            }
            if let Err(error) = read_verified_object(path, ObjectKind::Raw, expected_hash, false) {
                let _ = replace_file(&quarantine, path);
                return Err(error);
            }
            fs::remove_file(&quarantine).kio_io(&quarantine)?;
            // R23-07: propagate. The rename that published the repaired bytes
            // and the quarantine unlink above are both only as durable as this
            // entry, and the unlink already fails the repair loudly — swallowing
            // the sync that backs it let `repair_raw` answer `true` for a repair
            // that a crash could still undo. Retry is idempotent: a slot that
            // already verifies returns `false` before any mutation.
            sync_directory(parent).kio_io(parent)?;
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result.map(|()| true)
    }

    pub fn write_json(&self, kind: ObjectKind, value: &Value) -> Result<(String, Vec<u8>)> {
        let bytes = canonical_json_bytes(value)?;
        let hash = hash_bytes(&bytes);
        self.write_object_bytes(kind, &hash, &bytes)?;
        Ok((hash, bytes))
    }

    /// Atomically publish a semantic chunk object under its identity hash.
    pub fn write_chunk(&self, chunk: &ChunkObject) -> Result<String> {
        let hash = chunk.identity_hash()?;
        let value =
            serde_json::to_value(chunk).map_err(|error| KioError::schema(error.to_string()))?;
        let bytes = canonical_json_bytes(&value)?;
        if bytes.len() as u64 > MAX_CHUNK_OBJECT_BYTES {
            return Err(chunk_size_error(bytes.len() as u64));
        }
        self.ensure_chunk_parent(&hash)?;
        if let Some(existing) = self.existing_chunk_path(&hash)? {
            verify_existing_bytes(&existing, &hash, &bytes)?;
            read_chunk_path(&existing, &hash)?;
            return Ok(hash);
        }

        let path = self.chunk_path(&hash)?;
        let (temp_path, mut temp) = create_private_temp(
            path.parent()
                .ok_or_else(|| KioError::io("path has no parent", path.display().to_string()))?,
        )?;
        let result = (|| -> Result<()> {
            temp.write_all(&bytes).kio_io(&temp_path)?;
            temp.sync_all().kio_io(&temp_path)?;
            drop(temp);
            publish_temp_object(&temp_path, &path, &hash, bytes.len() as u64, Some(&bytes))?;
            let Some(published_path) = self.existing_chunk_path(&hash)? else {
                return Err(KioError::not_found(&hash));
            };
            let (object, _) = read_chunk_path(&published_path, &hash)?;
            if &object != chunk {
                return Err(chunk_corrupt_error(
                    "published chunk object changed identity or text",
                    Some(&published_path),
                ));
            }
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result.map(|()| hash)
    }

    /// Read one required chunk namespace and verify semantic identity, exact
    /// schema, text hash, bounded bytes, and canonical/legacy agreement.
    pub fn read_chunk(&self, hash: &str) -> Result<ChunkObject> {
        self.read_chunk_with_size(hash).map(|(chunk, _)| chunk)
    }

    /// Read a semantic chunk and return the exact logical object byte count.
    pub fn read_chunk_with_size(&self, hash: &str) -> Result<(ChunkObject, u64)> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid chunk hash"));
        }
        if !self.validate_chunk_parent(hash)? {
            return Err(KioError::not_found(hash));
        }
        let Some(path) = self.existing_chunk_path(hash)? else {
            return Err(KioError::not_found(hash));
        };
        let (object, bytes) = read_chunk_path(&path, hash)?;
        Ok((object, bytes.len() as u64))
    }

    pub fn read_chunk_accounted(
        &self,
        hash: &str,
    ) -> std::result::Result<(ChunkObject, u64), AccountedReadError> {
        let path = (|| -> Result<PathBuf> {
            if !is_hash(hash) {
                return Err(KioError::invalid_usage("invalid chunk hash"));
            }
            if !self.validate_chunk_parent(hash)? {
                return Err(KioError::not_found(hash));
            }
            self.existing_chunk_path(hash)?
                .ok_or_else(|| KioError::not_found(hash))
        })()
        .map_err(|error| AccountedReadError {
            error,
            consumed_bytes: 0,
        })?;
        let (result, consumed_bytes) = read_chunk_path_accounted(&path, hash);
        let (object, _) = result.map_err(|error| AccountedReadError {
            error,
            consumed_bytes,
        })?;
        Ok((object, consumed_bytes))
    }

    /// Stream-verify a referenced prepared/image content object without
    /// materializing its body.
    pub fn inspect_content_object(
        &self,
        kind: ContentObjectKind,
        hash: &str,
    ) -> Result<StoredContentObjectMetadata> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid content object hash"));
        }
        if !self.validate_content_parent(kind, hash)? {
            return Err(KioError::not_found(hash));
        }
        let Some(path) = self.existing_content_path(kind, hash)? else {
            return Err(KioError::not_found(hash));
        };
        let size_bytes = verify_content_object_path(&path, kind, hash)?;
        Ok(StoredContentObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes,
        })
    }

    pub fn inspect_content_accounted(
        &self,
        kind: ContentObjectKind,
        hash: &str,
    ) -> std::result::Result<StoredContentObjectMetadata, AccountedReadError> {
        let path = (|| -> Result<PathBuf> {
            if !is_hash(hash) {
                return Err(KioError::invalid_usage("invalid content object hash"));
            }
            if !self.validate_content_parent(kind, hash)? {
                return Err(KioError::not_found(hash));
            }
            self.existing_content_path(kind, hash)?
                .ok_or_else(|| KioError::not_found(hash))
        })()
        .map_err(|error| AccountedReadError {
            error,
            consumed_bytes: 0,
        })?;
        let (result, consumed_bytes) = verify_content_object_path_accounted(&path, kind, hash);
        result.map_err(|error| AccountedReadError {
            error,
            consumed_bytes,
        })?;
        Ok(StoredContentObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes: consumed_bytes,
        })
    }

    pub fn embedding_path(&self, hash: &str) -> Result<PathBuf> {
        fanout_path(self.kio_dir.join("objects/embeddings"), hash)
    }

    /// Publish one embedding vector under its identity hash (03 §8.1).
    ///
    /// Idempotent by content: the same vector for the same identity re-verifies
    /// and returns. A DIFFERENT vector under the same identity is corruption,
    /// not an update — the identity names the profile, the target text and the
    /// context, so a deterministic adapter cannot legitimately produce two.
    pub fn write_embedding(&self, embedding: &EmbeddingObject) -> Result<String> {
        let hash = embedding.identity_hash()?;
        let bytes = embedding.to_bytes()?;
        if bytes.len() as u64 > MAX_EMBEDDING_OBJECT_BYTES {
            return Err(KioError::new(
                "KIO-E-STORE-OBJECT-OVERSIZED-001",
                "embedding object exceeds its byte limit",
                serde_json::json!({
                    "object_type": "embedding",
                    "max_bytes": MAX_EMBEDDING_OBJECT_BYTES,
                    "actual_bytes": bytes.len() as u64,
                }),
                crate::ExitCode::PermanentFailure,
            ));
        }
        self.ensure_embedding_parent(&hash)?;
        let path = self.embedding_path(&hash)?;
        if fs::symlink_metadata(&path).is_ok() {
            verify_existing_bytes(&path, &hash, &bytes)?;
            return Ok(hash);
        }
        let (temp_path, mut temp) = create_private_temp(
            path.parent()
                .ok_or_else(|| KioError::io("path has no parent", path.display().to_string()))?,
        )?;
        let result = (|| -> Result<()> {
            temp.write_all(&bytes).kio_io(&temp_path)?;
            temp.sync_all().kio_io(&temp_path)?;
            drop(temp);
            publish_temp_object(&temp_path, &path, &hash, bytes.len() as u64, Some(&bytes))?;
            // Read back through the same parser a rebuild will use, so a
            // publish that somehow lands unreadable fails HERE rather than in
            // the `repair rebuild-db` that was counting on it.
            let published = self.read_embedding(&hash)?;
            if &published != embedding {
                return Err(embedding_corrupt_error(
                    "published embedding object changed identity or vector",
                    Some(&path),
                ));
            }
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result.map(|()| hash)
    }

    /// Read and fully verify one embedding object, including that its identity
    /// hashes back to the name it is stored under.
    pub fn read_embedding(&self, hash: &str) -> Result<EmbeddingObject> {
        read_embedding_path(&self.embedding_path(hash)?, hash)
    }

    /// Remove one embedding object after identity verification.
    ///
    /// The embeddings namespace is keyed by [`EmbeddingObject::identity_hash`]
    /// — what the vector is OF — and NOT by the hash of the stored bytes, which
    /// also carry the vector body. [`Self::remove_content`] re-hashes the file
    /// and compares that against the key, so it can never verify an embedding
    /// (every call reports `KIO-E-STORE-CORRUPT-001` on a perfectly healthy
    /// object); this is the correct primitive for the `Embedding` kind, exactly
    /// as [`Self::remove_chunk`] is for the identity-keyed chunk namespace.
    /// Missing is an idempotent `false`.
    pub fn remove_embedding(&self, hash: &str) -> Result<bool> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid embedding hash"));
        }
        if !self.validate_content_parent(ContentObjectKind::Embedding, hash)? {
            return Ok(false);
        }
        let Some(path) = occupied_slot(self.embedding_path(hash)?)? else {
            return Ok(false);
        };
        // Verify before the first destructive step.
        read_embedding_path(&path, hash)?;
        remove_verified_cas_path(&path, |candidate| {
            read_embedding_path(candidate, hash).map(|_| ())
        })?;
        Ok(true)
    }

    /// Every embedding object this scope holds, by storage key.
    ///
    /// The rebuild source: `kio repair rebuild-db` replays these into
    /// `embeddings` and derives `chunk_vec` from that (04 §4.3). Returns an
    /// empty list when the namespace does not exist, which is the ordinary
    /// state of a scope nothing has embedded yet.
    pub fn embedding_hashes(&self) -> Result<Vec<String>> {
        let base = self.kio_dir.join("objects/embeddings");
        let mut hashes = Vec::new();
        let Ok(first_level) = fs::read_dir(&base) else {
            return Ok(hashes);
        };
        for first in first_level {
            let first = first.kio_io(&base)?;
            let Ok(second_level) = fs::read_dir(first.path()) else {
                continue;
            };
            for second in second_level {
                let second = second.kio_io(&first.path())?;
                let Ok(leaves) = fs::read_dir(second.path()) else {
                    continue;
                };
                for leaf in leaves {
                    let leaf = leaf.kio_io(&second.path())?;
                    if !leaf.file_type().is_ok_and(|kind| kind.is_file()) {
                        continue;
                    }
                    // The fanout dirs are a PREFIX of the digest, which the
                    // leaf then repeats in full (`fanout_path`), so the leaf
                    // name alone is the digest.
                    let Some(digest) = leaf.file_name().to_str().map(str::to_owned) else {
                        continue;
                    };
                    hashes.push(format!("sha256:{digest}"));
                }
            }
        }
        hashes.sort();
        Ok(hashes)
    }

    fn ensure_embedding_parent(&self, hash: &str) -> Result<()> {
        ensure_real_directory(&self.kio_dir, false)?;
        ensure_real_directory(&self.kio_dir.join("objects"), true)?;
        let base = self.kio_dir.join("objects/embeddings");
        ensure_real_directory(&base, true)?;
        let digest = hash_path_component(hash)?;
        let first = base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        ensure_real_directory(&first, true)?;
        ensure_real_directory(&second, true)
    }

    pub fn chunk_path(&self, hash: &str) -> Result<PathBuf> {
        fanout_path(self.kio_dir.join("objects/chunks"), hash)
    }

    fn existing_chunk_path(&self, hash: &str) -> Result<Option<PathBuf>> {
        occupied_slot(self.chunk_path(hash)?)
    }

    /// Canonical fan-out path for a content object. `pub` (widened from the
    /// original prepared/image-only usage) so fsck-side verification (PB01/
    /// PB02) can locate `objects/embeddings|manifests|toollocks/<hash>` for a
    /// bounded semantic read, not just the byte-hash check
    /// [`Self::inspect_content_accounted`] already provides generically.
    pub fn content_path(&self, kind: ContentObjectKind, hash: &str) -> Result<PathBuf> {
        fanout_path(self.kio_dir.join("objects").join(kind.directory()), hash)
    }

    fn existing_content_path(
        &self,
        kind: ContentObjectKind,
        hash: &str,
    ) -> Result<Option<PathBuf>> {
        occupied_slot(self.content_path(kind, hash)?)
    }

    fn validate_content_parent(&self, kind: ContentObjectKind, hash: &str) -> Result<bool> {
        let digest = hash_path_component(hash)?;
        let objects = self.kio_dir.join("objects");
        let kind_base = objects.join(kind.directory());
        let first = kind_base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        for directory in [&self.kio_dir, &objects, &kind_base, &first, &second] {
            match fs::symlink_metadata(directory) {
                Ok(metadata)
                    if metadata.file_type().is_dir() && !metadata.file_type().is_symlink() => {}
                Ok(_) => return Err(non_regular_object_error(directory)),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
                Err(error) => {
                    return Err(KioError::io(
                        error.to_string(),
                        directory.display().to_string(),
                    ));
                }
            }
        }
        Ok(true)
    }

    fn ensure_chunk_parent(&self, hash: &str) -> Result<()> {
        ensure_real_directory(&self.kio_dir, false)?;
        ensure_real_directory(&self.kio_dir.join("objects"), true)?;
        let base = self.kio_dir.join("objects/chunks");
        ensure_real_directory(&base, true)?;
        let digest = hash_path_component(hash)?;
        let first = base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        ensure_real_directory(&first, true)?;
        ensure_real_directory(&second, true)
    }

    fn validate_chunk_parent(&self, hash: &str) -> Result<bool> {
        let digest = hash_path_component(hash)?;
        let objects = self.kio_dir.join("objects");
        let base = objects.join("chunks");
        let first = base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        for directory in [&self.kio_dir, &objects, &base, &first, &second] {
            match fs::symlink_metadata(directory) {
                Ok(metadata)
                    if metadata.file_type().is_dir() && !metadata.file_type().is_symlink() => {}
                Ok(_) => return Err(non_regular_object_error(directory)),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
                Err(error) => {
                    return Err(KioError::io(
                        error.to_string(),
                        directory.display().to_string(),
                    ));
                }
            }
        }
        Ok(true)
    }

    pub fn write_object_bytes(&self, kind: ObjectKind, hash: &str, bytes: &[u8]) -> Result<()> {
        #[cfg(unix)]
        if let Some(bound) = &self.bound {
            return bound.write_object_bytes(kind, hash, bytes);
        }
        if bytes.len() as u64 > kind.max_bytes() {
            return Err(object_size_error(
                kind,
                kind.max_bytes(),
                bytes.len() as u64,
            ));
        }
        if hash_bytes(bytes) != hash {
            return Err(KioError::invalid_usage(
                "CAS object hash does not match the supplied bytes",
            ));
        }
        self.ensure_object_parent(kind, hash)?;
        if let Some(existing) = self.existing_object_path(kind, hash)? {
            return verify_existing_bytes(&existing, hash, bytes);
        }

        let path = self.object_path(kind, hash)?;
        let (temp_path, mut temp) = create_private_temp(
            path.parent()
                .ok_or_else(|| KioError::io("path has no parent", path.display().to_string()))?,
        )?;
        let result = (|| -> Result<()> {
            temp.write_all(bytes).kio_io(&temp_path)?;
            temp.sync_all().kio_io(&temp_path)?;
            drop(temp);
            publish_temp_object(&temp_path, &path, hash, bytes.len() as u64, Some(bytes))?;

            let Some(published) = self.existing_object_path(kind, hash)? else {
                return Err(KioError::not_found(hash));
            };
            verify_existing_bytes(&published, hash, bytes)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result
    }

    /// Stream a raw object from an already-authorized handle. At most
    /// `max_bytes + 1` bytes are consumed, and the payload is never materialized
    /// as one attacker-sized allocation.
    pub fn write_raw_reader<R: Read>(
        &self,
        reader: &mut R,
        max_bytes: u64,
    ) -> Result<(String, u64)> {
        #[cfg(unix)]
        if let Some(bound) = &self.bound {
            return bound.write_raw_reader(reader, max_bytes);
        }
        let max_bytes = max_bytes.min(MAX_RAW_OBJECT_BYTES);
        let raw_base = self
            .kio_dir
            .join("objects")
            .join(ObjectKind::Raw.directory());
        self.ensure_kind_base(ObjectKind::Raw)?;
        let (temp_path, mut temp) = create_private_temp(&raw_base)?;
        let result = (|| -> Result<(String, u64)> {
            let mut hasher = Sha256::new();
            let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
            let mut total = 0_u64;
            loop {
                let read_cap = max_bytes
                    .saturating_sub(total)
                    .saturating_add(1)
                    .min(buffer.len() as u64) as usize;
                let count = reader.read(&mut buffer[..read_cap]).kio_io(&temp_path)?;
                if count == 0 {
                    break;
                }
                total = total
                    .checked_add(count as u64)
                    .ok_or_else(|| object_size_error(ObjectKind::Raw, max_bytes, u64::MAX))?;
                if total > max_bytes {
                    return Err(object_size_error(ObjectKind::Raw, max_bytes, total));
                }
                hasher.update(&buffer[..count]);
                temp.write_all(&buffer[..count]).kio_io(&temp_path)?;
            }
            temp.sync_all().kio_io(&temp_path)?;
            drop(temp);

            let hash = format!("sha256:{}", lower_hex(&hasher.finalize()));
            let path = self.object_path(ObjectKind::Raw, &hash)?;
            self.ensure_object_parent(ObjectKind::Raw, &hash)?;
            if let Some(existing) = self.existing_object_path(ObjectKind::Raw, &hash)? {
                verify_existing_matches_file(&existing, &temp_path, &hash, total)?;
                fs::remove_file(&temp_path).kio_io(&temp_path)?;
                return Ok((hash, total));
            }

            publish_temp_object(&temp_path, &path, &hash, total, None)?;
            let Some(published) = self.existing_object_path(ObjectKind::Raw, &hash)? else {
                return Err(KioError::not_found(&hash));
            };
            read_verified_object(&published, ObjectKind::Raw, &hash, false)?;
            Ok((hash, total))
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result
    }

    pub fn read_by_hash(&self, hash: &str) -> Result<StoredObject> {
        #[cfg(unix)]
        if let Some(bound) = &self.bound {
            return bound.read_by_hash(hash);
        }
        let (kind, path) = self.locate_object(hash)?;
        let (_, bytes) = read_verified_object(&path, kind, hash, true)?;
        Ok(StoredObject {
            kind,
            hash: hash.to_owned(),
            bytes,
        })
    }

    /// Verify every portable/legacy raw representation, then physically remove
    /// it. This destructive primitive is intentionally raw-only and is consumed
    /// by the purge transaction while its visibility barrier and store lock are
    /// held. Missing is an idempotent `false`; malformed links or bytes fail
    /// closed before unlink.
    pub fn remove_raw(&self, hash: &str) -> Result<bool> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid raw hash"));
        }
        if !self.validate_object_parent(ObjectKind::Raw, hash)? {
            return Ok(false);
        }
        let Some(path) = self.existing_object_path(ObjectKind::Raw, hash)? else {
            return Ok(false);
        };
        read_verified_object(&path, ObjectKind::Raw, hash, false)?;
        remove_verified_cas_path(&path, |candidate| {
            read_verified_object(candidate, ObjectKind::Raw, hash, false).map(|_| ())
        })?;
        Ok(true)
    }

    /// Remove one semantic chunk object after identity/text verification.
    pub fn remove_chunk(&self, hash: &str) -> Result<bool> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid chunk hash"));
        }
        if !self.validate_chunk_parent(hash)? {
            return Ok(false);
        }
        let Some(path) = self.existing_chunk_path(hash)? else {
            return Ok(false);
        };
        // Verify before the first destructive step.
        self.read_chunk(hash)?;
        remove_verified_cas_path(&path, |candidate| {
            read_chunk_path(candidate, hash).map(|_| ())
        })?;
        Ok(true)
    }

    /// Verify every portable/legacy prepared or image representation, then
    /// physically remove it. Purge callers must first prove that no surviving
    /// normalized instance references the content hash. Missing is an idempotent
    /// `false`; malformed links, bytes, or duplicate representations fail closed
    /// before the first unlink.
    pub fn remove_content(&self, kind: ContentObjectKind, hash: &str) -> Result<bool> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid content object hash"));
        }
        if !self.validate_content_parent(kind, hash)? {
            return Ok(false);
        }
        let Some(path) = self.existing_content_path(kind, hash)? else {
            return Ok(false);
        };
        verify_content_object_path(&path, kind, hash)?;
        remove_verified_cas_path(&path, |candidate| {
            verify_content_object_path(candidate, kind, hash).map(|_| ())
        })?;
        Ok(true)
    }

    fn ensure_content_kind_base(&self, kind: ContentObjectKind) -> Result<()> {
        ensure_real_directory(&self.kio_dir, false)?;
        ensure_real_directory(&self.kio_dir.join("objects"), true)?;
        ensure_real_directory(&self.kio_dir.join("objects").join(kind.directory()), true)
    }

    fn ensure_content_parent(&self, kind: ContentObjectKind, hash: &str) -> Result<()> {
        self.ensure_content_kind_base(kind)?;
        let digest = hash_path_component(hash)?;
        let kind_base = self.kio_dir.join("objects").join(kind.directory());
        let first = kind_base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        ensure_real_directory(&first, true)?;
        ensure_real_directory(&second, true)
    }

    /// PB01/PB02: write a content-addressed embedding/manifest/toollock/
    /// normalized-unit
    /// object, keyed by `hash_bytes(bytes)`. Idempotent (matching
    /// [`Self::write_object_bytes`]'s "verify existing, don't overwrite"
    /// contract) — used by tests to construct fsck fixtures directly, and is
    /// the storage primitive a future write-path integration would call.
    pub fn write_content_object(&self, kind: ContentObjectKind, bytes: &[u8]) -> Result<String> {
        if bytes.len() as u64 > kind.max_bytes() {
            return Err(content_object_size_error(
                kind,
                kind.max_bytes(),
                bytes.len() as u64,
            ));
        }
        let hash = hash_bytes(bytes);
        self.ensure_content_parent(kind, &hash)?;
        if let Some(existing) = self.existing_content_path(kind, &hash)? {
            verify_existing_bytes(&existing, &hash, bytes)?;
            return Ok(hash);
        }
        let path = self.content_path(kind, &hash)?;
        let (temp_path, mut temp) = create_private_temp(
            path.parent()
                .ok_or_else(|| KioError::io("path has no parent", path.display().to_string()))?,
        )?;
        let result = (|| -> Result<()> {
            temp.write_all(bytes).kio_io(&temp_path)?;
            temp.sync_all().kio_io(&temp_path)?;
            drop(temp);
            publish_temp_object(&temp_path, &path, &hash, bytes.len() as u64, Some(bytes))?;
            let Some(published) = self.existing_content_path(kind, &hash)? else {
                return Err(KioError::not_found(&hash));
            };
            verify_existing_bytes(&published, &hash, bytes)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result.map(|()| hash)
    }

    /// PB01/PB02: bounded read of a content object's raw bytes for semantic
    /// (JSON) parsing — [`Self::inspect_content_accounted`] verifies the
    /// byte-hash but deliberately never retains the body (it streams
    /// arbitrarily large prepared/image blobs). Embedding/manifest/toollock
    /// objects are small structured JSON, so a full bounded read is
    /// appropriate here. Does not itself verify the digest; callers that need
    /// the digest check should also call `inspect_content_accounted` (PB01
    /// (f)/(g)) or compare the returned bytes' hash directly.
    pub fn read_content_object_bytes(
        &self,
        kind: ContentObjectKind,
        hash: &str,
        max_bytes: u64,
    ) -> Result<Vec<u8>> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid content object hash"));
        }
        if !self.validate_content_parent(kind, hash)? {
            return Err(KioError::not_found(hash));
        }
        let Some(path) = self.existing_content_path(kind, hash)? else {
            return Err(KioError::not_found(hash));
        };
        read_bounded_regular_file(&path, max_bytes)
    }

    /// Read and verify a hash from one required CAS namespace. Unlike
    /// [`Self::read_by_hash`], this never accepts an object with the same digest
    /// from a different kind as a substitute for the requested object.
    pub fn read_object(&self, kind: ObjectKind, hash: &str) -> Result<StoredObject> {
        self.read_object_with_size(kind, hash)
            .map(|(object, _)| object)
    }

    /// Exact-kind read plus the total bytes verified across canonical/legacy
    /// physical representations.
    pub fn read_object_with_size(
        &self,
        kind: ObjectKind,
        hash: &str,
    ) -> Result<(StoredObject, u64)> {
        #[cfg(unix)]
        if let Some(bound) = &self.bound {
            return bound.read_object_with_size(kind, hash);
        }
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid hash"));
        }
        if !self.validate_object_parent(kind, hash)? {
            return Err(KioError::not_found(hash));
        }
        let Some(path) = self.existing_object_path(kind, hash)? else {
            return Err(KioError::not_found(hash));
        };
        let (size_bytes, bytes) = read_verified_object(&path, kind, hash, true)?;
        Ok((
            StoredObject {
                kind,
                hash: hash.to_owned(),
                bytes,
            },
            size_bytes,
        ))
    }

    /// Verify and count an object through a fixed-size buffer. This is the
    /// metadata-only path used by raw `inspect`; it does not retain the body.
    pub fn inspect_by_hash(&self, hash: &str) -> Result<StoredObjectMetadata> {
        let (kind, path) = self.locate_object(hash)?;
        let (size_bytes, _) = read_verified_object(&path, kind, hash, false)?;
        Ok(StoredObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes,
        })
    }

    /// Stream-verify metadata from one required CAS namespace without accepting
    /// a same-digest object from another namespace as a substitute.
    pub fn inspect_object(&self, kind: ObjectKind, hash: &str) -> Result<StoredObjectMetadata> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid hash"));
        }
        if !self.validate_object_parent(kind, hash)? {
            return Err(KioError::not_found(hash));
        }
        let Some(path) = self.existing_object_path(kind, hash)? else {
            return Err(KioError::not_found(hash));
        };
        let (size_bytes, _) = read_verified_object(&path, kind, hash, false)?;
        Ok(StoredObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes,
        })
    }

    /// Fsck-only exact-kind verification that reports bytes consumed even when
    /// verification fails. This lets a single aggregate budget bound adversarial
    /// corrupt objects rather than charging successful reads only.
    pub fn inspect_object_accounted(
        &self,
        kind: ObjectKind,
        hash: &str,
    ) -> std::result::Result<StoredObjectMetadata, AccountedReadError> {
        let path = (|| -> Result<PathBuf> {
            if !is_hash(hash) {
                return Err(KioError::invalid_usage("invalid hash"));
            }
            if !self.validate_object_parent(kind, hash)? {
                return Err(KioError::not_found(hash));
            }
            self.existing_object_path(kind, hash)?
                .ok_or_else(|| KioError::not_found(hash))
        })()
        .map_err(|error| AccountedReadError {
            error,
            consumed_bytes: 0,
        })?;
        let (result, consumed_bytes) = read_verified_object_accounted(&path, kind, hash, false);
        result.map_err(|error| AccountedReadError {
            error,
            consumed_bytes,
        })?;
        Ok(StoredObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes: consumed_bytes,
        })
    }

    /// Accounted materializing read used by fsck for tree/commit schema checks.
    pub fn read_object_accounted(
        &self,
        kind: ObjectKind,
        hash: &str,
    ) -> std::result::Result<(StoredObject, u64), AccountedReadError> {
        let path = (|| -> Result<PathBuf> {
            if !is_hash(hash) {
                return Err(KioError::invalid_usage("invalid hash"));
            }
            if !self.validate_object_parent(kind, hash)? {
                return Err(KioError::not_found(hash));
            }
            self.existing_object_path(kind, hash)?
                .ok_or_else(|| KioError::not_found(hash))
        })()
        .map_err(|error| AccountedReadError {
            error,
            consumed_bytes: 0,
        })?;
        let (result, consumed_bytes) = read_verified_object_accounted(&path, kind, hash, true);
        let (_, bytes) = result.map_err(|error| AccountedReadError {
            error,
            consumed_bytes,
        })?;
        Ok((
            StoredObject {
                kind,
                hash: hash.to_owned(),
                bytes,
            },
            consumed_bytes,
        ))
    }

    /// Stream one exact-kind CAS object into `writer` while verifying its
    /// bounded size and content identity. Bytes are never collected into an
    /// object-sized allocation. A caller must discard its private output if
    /// this method reports an error because hash verification completes only
    /// after the last byte has been written.
    pub fn copy_object_to<W: Write>(
        &self,
        kind: ObjectKind,
        hash: &str,
        writer: &mut W,
    ) -> Result<StoredObjectMetadata> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid hash"));
        }
        if !self.validate_object_parent(kind, hash)? {
            return Err(KioError::not_found(hash));
        }
        let path = self
            .existing_object_path(kind, hash)?
            .ok_or_else(|| KioError::not_found(hash))?;
        let size_bytes = copy_verified_object(&path, kind, hash, writer)?;
        Ok(StoredObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes,
        })
    }

    pub fn object_path(&self, kind: ObjectKind, hash: &str) -> Result<PathBuf> {
        let base = self.kio_dir.join("objects").join(kind.directory());
        fanout_path(base, hash)
    }

    fn locate_object(&self, hash: &str) -> Result<(ObjectKind, PathBuf)> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid hash"));
        }
        for kind in [ObjectKind::Tree, ObjectKind::Commit, ObjectKind::Raw] {
            if !self.validate_object_parent(kind, hash)? {
                continue;
            }
            if let Some(path) = self.existing_object_path(kind, hash)? {
                return Ok((kind, path));
            }
        }
        Err(KioError::not_found(hash))
    }

    fn existing_object_path(&self, kind: ObjectKind, hash: &str) -> Result<Option<PathBuf>> {
        occupied_slot(self.object_path(kind, hash)?)
    }

    fn ensure_kind_base(&self, kind: ObjectKind) -> Result<()> {
        ensure_real_directory(&self.kio_dir, false)?;
        ensure_real_directory(&self.kio_dir.join("objects"), true)?;
        ensure_real_directory(&self.kio_dir.join("objects").join(kind.directory()), true)
    }

    fn ensure_object_parent(&self, kind: ObjectKind, hash: &str) -> Result<()> {
        self.ensure_kind_base(kind)?;
        let digest = hash_path_component(hash)?;
        let kind_base = self.kio_dir.join("objects").join(kind.directory());
        let first = kind_base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        ensure_real_directory(&first, true)?;
        ensure_real_directory(&second, true)
    }

    fn validate_object_parent(&self, kind: ObjectKind, hash: &str) -> Result<bool> {
        let digest = hash_path_component(hash)?;
        let objects = self.kio_dir.join("objects");
        let kind_base = objects.join(kind.directory());
        let first = kind_base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        for directory in [&self.kio_dir, &objects, &kind_base, &first, &second] {
            match fs::symlink_metadata(directory) {
                Ok(metadata)
                    if metadata.file_type().is_dir() && !metadata.file_type().is_symlink() => {}
                Ok(_) => return Err(non_regular_object_error(directory)),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
                Err(error) => {
                    return Err(KioError::io(
                        error.to_string(),
                        directory.display().to_string(),
                    ));
                }
            }
        }
        Ok(true)
    }
}

#[cfg(unix)]
impl BoundObjectDirs {
    fn validate_layout(&self) -> Result<()> {
        use std::os::unix::fs::MetadataExt;
        let changed = || {
            KioError::new(
                "KIO-E-SNAPSHOT-AUTHORITY-CHANGED-001",
                "public object layout changed after scheduled snapshot binding",
                serde_json::json!({}),
                crate::ExitCode::PartialFailure,
            )
        };
        let objects = bound_open_dir(&self.kio, "objects").map_err(|_| changed())?;
        let raw = bound_open_dir(&objects, ObjectKind::Raw.directory()).map_err(|_| changed())?;
        let trees =
            bound_open_dir(&objects, ObjectKind::Tree.directory()).map_err(|_| changed())?;
        let commits =
            bound_open_dir(&objects, ObjectKind::Commit.directory()).map_err(|_| changed())?;
        for (current, retained) in [
            (&objects, &self.objects),
            (&raw, &self.raw),
            (&trees, &self.trees),
            (&commits, &self.commits),
        ] {
            let current = current
                .metadata()
                .kio_io(Path::new("bound object layout"))?;
            let retained = retained
                .metadata()
                .kio_io(Path::new("retained object layout"))?;
            if current.dev() != retained.dev() || current.ino() != retained.ino() {
                return Err(changed());
            }
        }
        Ok(())
    }

    fn stage_raw_from_reader<R: Read>(
        &self,
        reader: &mut R,
        max_bytes: u64,
    ) -> Result<BoundRawStage> {
        let max_bytes = max_bytes.min(MAX_RAW_OBJECT_BYTES);
        let (name, mut file) = bound_create_ingest_temp(&self.raw)?;
        let result = (|| {
            let mut hasher = Sha256::new();
            let mut total = 0_u64;
            let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
            loop {
                let cap = max_bytes
                    .saturating_sub(total)
                    .saturating_add(1)
                    .min(buffer.len() as u64) as usize;
                let count = reader.read(&mut buffer[..cap]).kio_io(Path::new(&name))?;
                if count == 0 {
                    break;
                }
                total = total
                    .checked_add(count as u64)
                    .ok_or_else(|| object_size_error(ObjectKind::Raw, max_bytes, u64::MAX))?;
                if total > max_bytes {
                    return Err(object_size_error(ObjectKind::Raw, max_bytes, total));
                }
                hasher.update(&buffer[..count]);
                file.write_all(&buffer[..count]).kio_io(Path::new(&name))?;
            }
            file.sync_all().kio_io(Path::new(&name))?;
            file.seek(std::io::SeekFrom::Start(0))
                .kio_io(Path::new(&name))?;
            Ok((format!("sha256:{}", lower_hex(&hasher.finalize())), total))
        })();
        match result {
            Ok((raw_hash, size_bytes)) => Ok(BoundRawStage {
                parent: Arc::clone(&self.raw),
                name,
                file,
                raw_hash,
                size_bytes,
            }),
            Err(error) => {
                drop(file);
                let _ = bound_remove(&self.raw, &name);
                Err(error)
            }
        }
    }

    fn publish_raw_stage(&self, mut stage: BoundRawStage) -> Result<(String, u64)> {
        if !Arc::ptr_eq(&stage.parent, &self.raw) {
            return Err(KioError::invalid_usage(
                "bound raw stage belongs to another ObjectStore",
            ));
        }
        let opened = stage.file.metadata().kio_io(Path::new(&stage.name))?;
        if !opened.is_file() || opened.len() != stage.size_bytes {
            return Err(corrupt_object_error(
                Path::new(&stage.name),
                "bound raw stage changed before publication",
                &stage.raw_hash,
                None,
            ));
        }
        let hash = stage.raw_hash.clone();
        let size = stage.size_bytes;
        let (parent, leaf) = self.fanout(ObjectKind::Raw, &hash, true)?;
        match bound_read_verified(&parent, &leaf, ObjectKind::Raw, &hash, true) {
            Ok((existing_size, existing)) => {
                let (_, staged) = bound_read_regular(&self.raw, &stage.name, MAX_RAW_OBJECT_BYTES)?;
                if existing_size != size || existing != staged {
                    return Err(corrupt_object_error(
                        Path::new(&leaf),
                        "CAS object bytes do not match existing object",
                        &hash,
                        Some(&hash_bytes(&existing)),
                    ));
                }
                bound_remove(&self.raw, &stage.name)?;
            }
            Err(error) if error.error_code() == "KIO-E-STORE-NOT-FOUND-001" => {
                bound_publish_between(
                    &self.raw,
                    &stage.name,
                    &parent,
                    &leaf,
                    ObjectKind::Raw,
                    &hash,
                    size,
                    None,
                )?
            }
            Err(error) => return Err(error),
        }
        stage.name.clear();
        Ok((hash, size))
    }

    fn cleanup_raw_ingest_orphans(&self) -> Result<()> {
        use std::os::unix::ffi::OsStrExt;
        const MAX_ENTRIES: usize = 100_000;
        let mut total = 0_u64;
        let entries = cap_primitives::fs::read_base_dir(&self.raw)
            .map_err(|e| KioError::io(e.to_string(), "bound raw stage directory"))?;
        for (n, entry) in entries.enumerate() {
            if n >= MAX_ENTRIES {
                return Err(bound_stage_corrupt(
                    "bound raw stage directory exceeds entry limit",
                ));
            }
            let entry =
                entry.map_err(|e| KioError::io(e.to_string(), "bound raw stage directory"))?;
            let file_name = entry.file_name();
            let bytes = file_name.as_bytes();
            if !bytes.starts_with(b".ingest-") {
                continue;
            }
            let name = std::str::from_utf8(bytes)
                .map_err(|_| bound_stage_corrupt("bound raw stage name is not UTF-8"))?;
            if !bound_ingest_name(name) {
                return Err(bound_stage_corrupt("bound raw stage name is malformed"));
            }
            let (size, _) = bound_read_regular(&self.raw, name, MAX_RAW_OBJECT_BYTES)?;
            total = total
                .checked_add(size)
                .ok_or_else(|| bound_stage_corrupt("bound raw stage byte count overflow"))?;
            if total > MAX_RAW_OBJECT_BYTES {
                return Err(bound_stage_corrupt(
                    "bound raw stage cleanup exceeds byte limit",
                ));
            }
            bound_remove(&self.raw, name)?;
        }
        sync_bound_directory(&self.raw, Path::new("bound raw stage directory"))
    }

    fn dir(&self, kind: ObjectKind) -> &File {
        match kind {
            ObjectKind::Raw => &self.raw,
            ObjectKind::Tree => &self.trees,
            ObjectKind::Commit => &self.commits,
        }
    }

    fn fanout(&self, kind: ObjectKind, hash: &str, create: bool) -> Result<(File, String)> {
        let digest = hash_path_component(hash)?;
        let first = &digest[..2];
        let second = &digest[2..4];
        let base = self.dir(kind);
        let first_dir = bound_open_or_create_dir(base, first, create)?;
        let second_dir = bound_open_or_create_dir(&first_dir, second, create)?;
        Ok((second_dir, digest.to_owned()))
    }

    fn read_object_with_size(&self, kind: ObjectKind, hash: &str) -> Result<(StoredObject, u64)> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid hash"));
        }
        let (parent, leaf) = self.fanout(kind, hash, false)?;
        let (size_bytes, bytes) = bound_read_verified(&parent, &leaf, kind, hash, true)?;
        Ok((
            StoredObject {
                kind,
                hash: hash.to_owned(),
                bytes,
            },
            size_bytes,
        ))
    }

    fn read_by_hash(&self, hash: &str) -> Result<StoredObject> {
        if !is_hash(hash) {
            return Err(KioError::invalid_usage("invalid hash"));
        }
        for kind in [ObjectKind::Tree, ObjectKind::Commit, ObjectKind::Raw] {
            match self.read_object_with_size(kind, hash) {
                Ok((object, _)) => return Ok(object),
                Err(error) if error.error_code() == "KIO-E-STORE-NOT-FOUND-001" => continue,
                Err(error) => return Err(error),
            }
        }
        Err(KioError::not_found(hash))
    }

    fn write_object_bytes(&self, kind: ObjectKind, hash: &str, bytes: &[u8]) -> Result<()> {
        if bytes.len() as u64 > kind.max_bytes() {
            return Err(object_size_error(
                kind,
                kind.max_bytes(),
                bytes.len() as u64,
            ));
        }
        if hash_bytes(bytes) != hash {
            return Err(KioError::invalid_usage(
                "CAS object hash does not match the supplied bytes",
            ));
        }
        let (parent, leaf) = self.fanout(kind, hash, true)?;
        match bound_read_verified(&parent, &leaf, kind, hash, true) {
            Ok((_, existing)) => {
                if existing == bytes {
                    return Ok(());
                }
                return Err(corrupt_object_error(
                    Path::new(&leaf),
                    "CAS object bytes do not match existing object",
                    hash,
                    Some(&hash_bytes(&existing)),
                ));
            }
            Err(error) if error.error_code() == "KIO-E-STORE-NOT-FOUND-001" => {}
            Err(error) => return Err(error),
        }
        let (temp_name, mut temp) = bound_create_temp(&parent)?;
        let result = (|| {
            temp.write_all(bytes).kio_io(Path::new(&temp_name))?;
            temp.sync_all().kio_io(Path::new(&temp_name))?;
            drop(temp);
            bound_publish(
                &parent,
                &temp_name,
                &leaf,
                kind,
                hash,
                bytes.len() as u64,
                Some(bytes),
            )
        })();
        if result.is_err() {
            let _ = bound_remove(&parent, &temp_name);
        }
        result
    }

    fn write_raw_reader<R: Read>(&self, reader: &mut R, max_bytes: u64) -> Result<(String, u64)> {
        let max_bytes = max_bytes.min(MAX_RAW_OBJECT_BYTES);
        let (temp_name, mut temp) = bound_create_temp(&self.raw)?;
        let result = (|| {
            let mut hasher = Sha256::new();
            let mut total = 0_u64;
            let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
            loop {
                let cap = max_bytes
                    .saturating_sub(total)
                    .saturating_add(1)
                    .min(buffer.len() as u64) as usize;
                let count = reader
                    .read(&mut buffer[..cap])
                    .kio_io(Path::new(&temp_name))?;
                if count == 0 {
                    break;
                }
                total = total
                    .checked_add(count as u64)
                    .ok_or_else(|| object_size_error(ObjectKind::Raw, max_bytes, u64::MAX))?;
                if total > max_bytes {
                    return Err(object_size_error(ObjectKind::Raw, max_bytes, total));
                }
                hasher.update(&buffer[..count]);
                temp.write_all(&buffer[..count])
                    .kio_io(Path::new(&temp_name))?;
            }
            temp.sync_all().kio_io(Path::new(&temp_name))?;
            drop(temp);
            let hash = format!("sha256:{}", lower_hex(&hasher.finalize()));
            let (parent, leaf) = self.fanout(ObjectKind::Raw, &hash, true)?;
            // A temp in raw's base cannot be linked across a fanout directory
            // by a path-based fallback; linkat keeps both endpoints capability-bound.
            match bound_read_verified(&parent, &leaf, ObjectKind::Raw, &hash, true) {
                Ok((_, existing)) => {
                    let (_, staged) =
                        bound_read_regular(&self.raw, &temp_name, ObjectKind::Raw.max_bytes())?;
                    if existing != staged {
                        return Err(corrupt_object_error(
                            Path::new(&leaf),
                            "CAS object bytes do not match existing object",
                            &hash,
                            Some(&hash_bytes(&existing)),
                        ));
                    }
                    bound_remove(&self.raw, &temp_name)?;
                }
                Err(error) if error.error_code() == "KIO-E-STORE-NOT-FOUND-001" => {
                    bound_publish_between(
                        &self.raw,
                        &temp_name,
                        &parent,
                        &leaf,
                        ObjectKind::Raw,
                        &hash,
                        total,
                        None,
                    )?;
                }
                Err(error) => return Err(error),
            }
            Ok((hash, total))
        })();
        if result.is_err() {
            let _ = bound_remove(&self.raw, &temp_name);
        }
        result
    }
}

#[cfg(unix)]
fn sync_bound_directory(directory: &File, label: &Path) -> Result<()> {
    use cap_primitives::fs::{self as cap_fs, MetadataExt};

    let expected = cap_fs::Metadata::from_file(directory).kio_io(label)?;
    if !expected.is_dir() {
        return Err(KioError::io(
            "bound CAS directory changed type",
            label.display().to_string(),
        ));
    }
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let syncable = cap_fs::open(directory, Path::new("."), &options).kio_io(label)?;
    let observed = cap_fs::Metadata::from_file(&syncable).kio_io(label)?;
    if !observed.is_dir() || observed.dev() != expected.dev() || observed.ino() != expected.ino() {
        return Err(KioError::io(
            "bound CAS directory changed while reopening for fsync",
            label.display().to_string(),
        ));
    }
    syncable.sync_all().kio_io(label)
}

#[cfg(unix)]
fn bound_open_dir(parent: &File, leaf: &str) -> Result<File> {
    use std::ffi::CString;
    use std::os::fd::{AsRawFd, FromRawFd};
    let leaf = CString::new(leaf)
        .map_err(|_| KioError::invalid_usage("invalid bound CAS directory name"))?;
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            leaf.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        let io = std::io::Error::last_os_error();
        if io.kind() == std::io::ErrorKind::NotFound {
            return Err(KioError::not_found(leaf.to_string_lossy().to_string()));
        }
        return Err(KioError::io(
            io.to_string(),
            leaf.to_string_lossy().to_string(),
        ));
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}

#[cfg(unix)]
fn bound_ingest_name(name: &str) -> bool {
    let Some(rest) = name.strip_prefix(".ingest-") else {
        return false;
    };
    let mut fields = rest.split('-');
    (0..3).all(|_| {
        fields.next().is_some_and(|field| {
            !field.is_empty() && field.bytes().all(|byte| byte.is_ascii_digit())
        })
    }) && fields.next().is_none()
}

#[cfg(unix)]
fn bound_stage_corrupt(message: &str) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        message,
        serde_json::json!({}),
        crate::ExitCode::PermanentFailure,
    )
}

#[cfg(unix)]
fn bound_open_or_create_dir(parent: &File, leaf: &str, create: bool) -> Result<File> {
    match bound_open_dir(parent, leaf) {
        Ok(dir) => Ok(dir),
        Err(error) if create && error.error_code() == "KIO-E-STORE-NOT-FOUND-001" => {
            use std::ffi::CString;
            use std::os::fd::AsRawFd;
            let name = CString::new(leaf)
                .map_err(|_| KioError::invalid_usage("invalid bound CAS directory name"))?;
            if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
                let io = std::io::Error::last_os_error();
                if io.kind() != std::io::ErrorKind::AlreadyExists {
                    return Err(KioError::io(io.to_string(), leaf));
                }
            }
            bound_open_dir(parent, leaf)
        }
        Err(error) => Err(error),
    }
}

#[cfg(unix)]
fn bound_read_regular(parent: &File, leaf: &str, max: u64) -> Result<(u64, Vec<u8>)> {
    use std::ffi::CString;
    use std::os::fd::{AsRawFd, FromRawFd};
    use std::os::unix::fs::MetadataExt;
    let name = CString::new(leaf).map_err(|_| KioError::invalid_usage("invalid bound CAS leaf"))?;
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        let io = std::io::Error::last_os_error();
        if io.kind() == std::io::ErrorKind::NotFound {
            return Err(KioError::not_found(leaf));
        }
        return Err(KioError::io(io.to_string(), leaf));
    }
    let mut file = unsafe { File::from_raw_fd(fd) };
    let meta = file.metadata().kio_io(Path::new(leaf))?;
    if !meta.is_file() || meta.nlink() != 1 {
        return Err(non_regular_object_error(Path::new(leaf)));
    }
    if meta.len() > max {
        return Err(KioError::new(
            "KIO-E-STORE-OBJECT-OVERSIZED-001",
            "CAS object exceeds its byte limit",
            serde_json::json!({"max_bytes": max, "actual_bytes": meta.len()}),
            crate::ExitCode::PermanentFailure,
        ));
    }
    let mut bytes = Vec::with_capacity(meta.len() as usize);
    file.read_to_end(&mut bytes).kio_io(Path::new(leaf))?;
    if bytes.len() as u64 != meta.len() {
        return Err(corrupt_object_error(
            Path::new(leaf),
            "CAS object changed while reading",
            "stable",
            None,
        ));
    }
    Ok((meta.len(), bytes))
}

#[cfg(unix)]
fn bound_read_verified(
    parent: &File,
    leaf: &str,
    kind: ObjectKind,
    hash: &str,
    materialize: bool,
) -> Result<(u64, Vec<u8>)> {
    let (size, bytes) = bound_read_regular(parent, leaf, kind.max_bytes())?;
    let actual = hash_bytes(&bytes);
    if actual != hash {
        return Err(corrupt_object_error(
            Path::new(leaf),
            "CAS object hash does not match filename",
            hash,
            Some(&actual),
        ));
    }
    Ok((size, if materialize { bytes } else { Vec::new() }))
}

#[cfg(unix)]
fn bound_create_temp(parent: &File) -> Result<(String, File)> {
    use std::ffi::CString;
    use std::os::fd::{AsRawFd, FromRawFd};
    for attempt in 0..128_u32 {
        let name = format!(
            ".kio-cas-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_or(0, |d| d.as_nanos()),
            attempt
        );
        let c = CString::new(name.as_str())
            .map_err(|_| KioError::invalid_usage("invalid bound CAS temp name"))?;
        let fd = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                c.as_ptr(),
                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0o600,
            )
        };
        if fd >= 0 {
            return Ok((name, unsafe { File::from_raw_fd(fd) }));
        }
        if std::io::Error::last_os_error().kind() != std::io::ErrorKind::AlreadyExists {
            return Err(KioError::io(
                std::io::Error::last_os_error().to_string(),
                "bound CAS temp",
            ));
        }
    }
    Err(KioError::io(
        "unable to allocate private bound CAS temp",
        "bound CAS temp",
    ))
}

#[cfg(unix)]
fn bound_create_ingest_temp(parent: &File) -> Result<(String, File)> {
    use std::ffi::CString;
    use std::os::fd::{AsRawFd, FromRawFd};
    for attempt in 0..128_u32 {
        let name = format!(
            ".ingest-{}-{}-{attempt}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_or(0, |d| d.as_nanos())
        );
        let c = CString::new(name.as_str())
            .map_err(|_| KioError::invalid_usage("invalid bound raw stage name"))?;
        let fd = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                c.as_ptr(),
                libc::O_RDWR | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0o600,
            )
        };
        if fd >= 0 {
            return Ok((name, unsafe { File::from_raw_fd(fd) }));
        }
        if std::io::Error::last_os_error().kind() != std::io::ErrorKind::AlreadyExists {
            return Err(KioError::io(
                std::io::Error::last_os_error().to_string(),
                "bound raw stage",
            ));
        }
    }
    Err(KioError::io(
        "could not allocate a private bound raw stage",
        "bound raw stage",
    ))
}

#[cfg(unix)]
fn bound_remove(parent: &File, leaf: &str) -> Result<()> {
    cap_primitives::fs::remove_file(parent, Path::new(leaf))
        .map_err(|error| KioError::io(error.to_string(), leaf))
}

#[cfg(unix)]
fn bound_publish(
    parent: &File,
    temp: &str,
    leaf: &str,
    kind: ObjectKind,
    hash: &str,
    size: u64,
    expected: Option<&[u8]>,
) -> Result<()> {
    bound_publish_between(parent, temp, parent, leaf, kind, hash, size, expected)
}

#[cfg(unix)]
#[allow(clippy::too_many_arguments)]
fn bound_publish_between(
    from: &File,
    temp: &str,
    to: &File,
    leaf: &str,
    kind: ObjectKind,
    hash: &str,
    size: u64,
    expected: Option<&[u8]>,
) -> Result<()> {
    match cap_primitives::fs::hard_link(from, Path::new(temp), to, Path::new(leaf)) {
        Ok(()) => {
            bound_remove(from, temp)?;
            sync_bound_directory(to, Path::new(leaf))?;
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            let (_, existing) = bound_read_verified(to, leaf, kind, hash, true)?;
            if existing.len() as u64 != size || expected.is_some_and(|bytes| bytes != existing) {
                return Err(corrupt_object_error(
                    Path::new(leaf),
                    "CAS object bytes do not match existing object",
                    hash,
                    Some(&hash_bytes(&existing)),
                ));
            }
            bound_remove(from, temp)?;
        }
        Err(error) => return Err(KioError::io(error.to_string(), leaf)),
    }
    let (actual_size, actual) = bound_read_verified(to, leaf, kind, hash, true)?;
    if actual_size != size || expected.is_some_and(|bytes| bytes != actual) {
        return Err(corrupt_object_error(
            Path::new(leaf),
            "published CAS object changed",
            hash,
            Some(&hash_bytes(&actual)),
        ));
    }
    Ok(())
}

fn read_verified_object(
    path: &Path,
    kind: ObjectKind,
    expected_hash: &str,
    materialize: bool,
) -> Result<(u64, Vec<u8>)> {
    read_verified_object_accounted(path, kind, expected_hash, materialize).0
}

fn read_verified_object_accounted(
    path: &Path,
    kind: ObjectKind,
    expected_hash: &str,
    materialize: bool,
) -> (Result<(u64, Vec<u8>)>, u64) {
    let mut consumed = 0_u64;
    let result = (|| -> Result<(u64, Vec<u8>)> {
        let mut file = open_regular_nofollow(path)?;
        let metadata = file.metadata().kio_io(path)?;
        let limit = kind.max_bytes();
        if metadata.len() > limit {
            return Err(object_size_error(kind, limit, metadata.len()));
        }

        let mut bytes = Vec::new();
        let mut hasher = Sha256::new();
        let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
        loop {
            let read_cap = limit
                .saturating_sub(consumed)
                .saturating_add(1)
                .min(buffer.len() as u64) as usize;
            let count = file.read(&mut buffer[..read_cap]).kio_io(path)?;
            if count == 0 {
                break;
            }
            consumed = consumed
                .checked_add(count as u64)
                .ok_or_else(|| object_size_error(kind, limit, u64::MAX))?;
            if consumed > limit {
                return Err(object_size_error(kind, limit, consumed));
            }
            hasher.update(&buffer[..count]);
            if materialize {
                bytes.extend_from_slice(&buffer[..count]);
            }
        }
        let actual = format!("sha256:{}", lower_hex(&hasher.finalize()));
        if actual != expected_hash {
            return Err(corrupt_object_error(
                path,
                "CAS object hash mismatch",
                expected_hash,
                Some(&actual),
            ));
        }
        Ok((consumed, bytes))
    })();
    (result, consumed)
}

fn verify_content_object_path(
    path: &Path,
    kind: ContentObjectKind,
    expected_hash: &str,
) -> Result<u64> {
    verify_content_object_path_accounted(path, kind, expected_hash).0
}

fn verify_content_object_path_accounted(
    path: &Path,
    kind: ContentObjectKind,
    expected_hash: &str,
) -> (Result<u64>, u64) {
    let mut consumed = 0_u64;
    let result = (|| -> Result<u64> {
        let mut file = open_regular_nofollow(path)?;
        let metadata = file.metadata().kio_io(path)?;
        let limit = kind.max_bytes();
        if metadata.len() > limit {
            return Err(content_object_size_error(kind, limit, metadata.len()));
        }
        let mut hasher = Sha256::new();
        let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
        loop {
            let read_cap = limit
                .saturating_sub(consumed)
                .saturating_add(1)
                .min(buffer.len() as u64) as usize;
            let count = file.read(&mut buffer[..read_cap]).kio_io(path)?;
            if count == 0 {
                break;
            }
            consumed = consumed.saturating_add(count as u64);
            if consumed > limit {
                return Err(KioError::new(
                    "KIO-E-STORE-OBJECT-OVERSIZED-001",
                    "content object exceeds its byte limit",
                    serde_json::json!({
                        "object_type": kind.object_type(),
                        "max_bytes": limit,
                        "actual_bytes": consumed,
                    }),
                    crate::ExitCode::PermanentFailure,
                ));
            }
            hasher.update(&buffer[..count]);
        }
        let actual = format!("sha256:{}", lower_hex(&hasher.finalize()));
        if actual != expected_hash {
            return Err(corrupt_object_error(
                path,
                "content object hash mismatch",
                expected_hash,
                Some(&actual),
            ));
        }
        Ok(consumed)
    })();
    (result, consumed)
}

fn content_object_size_error(
    kind: ContentObjectKind,
    max_bytes: u64,
    actual_bytes: u64,
) -> KioError {
    KioError::new(
        "KIO-E-STORE-OBJECT-OVERSIZED-001",
        "content object exceeds its byte limit",
        serde_json::json!({
            "object_type": kind.object_type(),
            "max_bytes": max_bytes,
            "actual_bytes": actual_bytes,
        }),
        crate::ExitCode::PermanentFailure,
    )
}

fn copy_verified_object<W: Write>(
    path: &Path,
    kind: ObjectKind,
    expected_hash: &str,
    writer: &mut W,
) -> Result<u64> {
    let mut file = open_regular_nofollow(path)?;
    let metadata = file.metadata().kio_io(path)?;
    let limit = kind.max_bytes();
    if metadata.len() > limit {
        return Err(object_size_error(kind, limit, metadata.len()));
    }

    let mut hasher = Sha256::new();
    let mut total = 0_u64;
    let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
    loop {
        let read_cap = limit
            .saturating_sub(total)
            .saturating_add(1)
            .min(buffer.len() as u64) as usize;
        let count = file.read(&mut buffer[..read_cap]).kio_io(path)?;
        if count == 0 {
            break;
        }
        total = total
            .checked_add(count as u64)
            .ok_or_else(|| object_size_error(kind, limit, u64::MAX))?;
        if total > limit {
            return Err(object_size_error(kind, limit, total));
        }
        hasher.update(&buffer[..count]);
        writer
            .write_all(&buffer[..count])
            .map_err(|error| KioError::io(error.to_string(), "CAS stream target"))?;
    }
    let actual = format!("sha256:{}", lower_hex(&hasher.finalize()));
    if actual != expected_hash {
        return Err(corrupt_object_error(
            path,
            "CAS object hash mismatch",
            expected_hash,
            Some(&actual),
        ));
    }
    Ok(total)
}

fn verify_existing_bytes(path: &Path, expected_hash: &str, expected: &[u8]) -> Result<()> {
    let mut file = open_regular_nofollow(path)?;
    let metadata = file.metadata().kio_io(path)?;
    if metadata.len() != expected.len() as u64 {
        return Err(corrupt_object_error(
            path,
            "existing CAS object does not match expected bytes",
            expected_hash,
            None,
        ));
    }
    let mut offset = 0_usize;
    let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
    loop {
        let count = file.read(&mut buffer).kio_io(path)?;
        if count == 0 {
            break;
        }
        let end = offset.checked_add(count).ok_or_else(|| {
            corrupt_object_error(
                path,
                "existing CAS object length overflow",
                expected_hash,
                None,
            )
        })?;
        if expected.get(offset..end) != Some(&buffer[..count]) {
            return Err(corrupt_object_error(
                path,
                "existing CAS object does not match expected bytes",
                expected_hash,
                None,
            ));
        }
        offset = end;
    }
    if offset != expected.len() {
        return Err(corrupt_object_error(
            path,
            "existing CAS object does not match expected bytes",
            expected_hash,
            None,
        ));
    }
    Ok(())
}

fn publish_temp_object(
    temp_path: &Path,
    destination: &Path,
    expected_hash: &str,
    expected_len: u64,
    expected_bytes: Option<&[u8]>,
) -> Result<()> {
    match fs::hard_link(temp_path, destination) {
        Ok(()) => {
            fs::remove_file(temp_path).kio_io(temp_path)?;
            Ok(())
        }
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            let result = match expected_bytes {
                Some(bytes) => verify_existing_bytes(destination, expected_hash, bytes),
                None => verify_existing_matches_file(
                    destination,
                    temp_path,
                    expected_hash,
                    expected_len,
                ),
            };
            let _ = fs::remove_file(temp_path);
            result
        }
        Err(error) => Err(KioError::io(
            error.to_string(),
            destination.display().to_string(),
        )),
    }
}

fn create_repair_quarantine(path: &Path, opened: &File) -> Result<PathBuf> {
    let parent = path
        .parent()
        .ok_or_else(|| KioError::io("CAS path has no parent", path.display().to_string()))?;
    for attempt in 0..32_u8 {
        let candidate = parent.join(format!(
            ".repair-quarantine-{}-{}-{attempt}",
            std::process::id(),
            unix_nanos()
        ));
        match fs::hard_link(path, &candidate) {
            Ok(()) => {
                let mut options = OpenOptions::new();
                options.read(true);
                configure_no_follow(&mut options);
                let linked = options.open(&candidate).kio_io(&candidate)?;
                if !same_open_file(opened, &linked)? {
                    let _ = fs::remove_file(&candidate);
                    return Err(non_regular_object_error(path));
                }
                return Ok(candidate);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
        }
    }
    Err(KioError::io(
        "could not allocate raw repair quarantine",
        path.display().to_string(),
    ))
}

#[cfg(unix)]
fn same_open_file(left: &File, right: &File) -> Result<bool> {
    Ok(same_file_identity(
        &left
            .metadata()
            .map_err(|error| KioError::io(error.to_string(), "raw repair source"))?,
        &right
            .metadata()
            .map_err(|error| KioError::io(error.to_string(), "raw repair quarantine"))?,
    ))
}

#[cfg(windows)]
fn same_open_file(left: &File, right: &File) -> Result<bool> {
    Ok(same_windows_repair_quarantine_file_components(
        windows_file_information(left),
        windows_file_information(right),
    ))
}

#[cfg(not(any(unix, windows)))]
fn same_open_file(left: &File, right: &File) -> Result<bool> {
    Ok(left
        .metadata()
        .map_err(|error| KioError::io(error.to_string(), "raw repair source"))?
        .len()
        == right
            .metadata()
            .map_err(|error| KioError::io(error.to_string(), "raw repair quarantine"))?
            .len())
}

#[cfg(not(windows))]
fn replace_file(source: &Path, destination: &Path) -> Result<()> {
    fs::rename(source, destination)
        .map_err(|error| KioError::io(error.to_string(), destination.display().to_string()))
}

#[cfg(windows)]
fn replace_file(source: &Path, destination: &Path) -> Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
    };

    let source = source
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let destination = destination
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    // SAFETY: both UTF-16 buffers are NUL-terminated and live for the call.
    let moved = unsafe {
        MoveFileExW(
            source.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if moved == 0 {
        Err(KioError::io(
            std::io::Error::last_os_error().to_string(),
            "raw repair destination",
        ))
    } else {
        Ok(())
    }
}

/// Remove one already-authorized CAS leaf without ever overwriting a quarantine
/// name. Linking before unlink keeps a recoverable handle in the same directory;
/// the post-unlink verification detects a source swap before final deletion.
fn remove_verified_cas_path<F>(path: &Path, verify: F) -> Result<()>
where
    F: Fn(&Path) -> Result<()>,
{
    verify(path)?;
    let parent = path
        .parent()
        .ok_or_else(|| KioError::io("CAS path has no parent", path.display().to_string()))?;
    let mut quarantine = None;
    for attempt in 0..32_u8 {
        let candidate = parent.join(format!(
            ".purge-remove-{}-{}-{attempt}",
            std::process::id(),
            unix_nanos()
        ));
        match fs::hard_link(path, &candidate) {
            Ok(()) => {
                quarantine = Some(candidate);
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
        }
    }
    let quarantine = quarantine.ok_or_else(|| {
        KioError::io(
            "could not allocate CAS removal quarantine",
            path.display().to_string(),
        )
    })?;
    if let Err(error) = fs::remove_file(path) {
        let _ = fs::remove_file(&quarantine);
        return Err(KioError::io(error.to_string(), path.display().to_string()));
    }
    // Leave quarantined bytes in place on failure for retry/forensics. The
    // logical leaf is already absent and the purge barrier keeps reads closed.
    verify(&quarantine)?;
    fs::remove_file(&quarantine).kio_io(&quarantine)?;
    // R23-07: propagate. The leaf's *absence* is the result this function
    // reports, and it is durable only once the parent entry is. Swallowing the
    // failure let every `remove_*` caller answer `true` for a removal a crash
    // could resurrect — the "markerless absence" window §3.5 exists to close,
    // here in the object store rather than the purge journal. Retry is
    // idempotent: an already-absent slot returns `false` before any mutation.
    sync_directory(parent).kio_io(parent)?;
    Ok(())
}

fn verify_existing_matches_file(
    destination: &Path,
    source: &Path,
    expected_hash: &str,
    expected_len: u64,
) -> Result<()> {
    let mut existing = open_regular_nofollow(destination)?;
    if existing.metadata().kio_io(destination)?.len() != expected_len {
        return Err(corrupt_object_error(
            destination,
            "existing CAS object does not match expected bytes",
            expected_hash,
            None,
        ));
    }
    let mut source_file = open_regular_nofollow(source)?;
    let mut existing_buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
    let mut source_buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
    loop {
        let existing_count = existing.read(&mut existing_buffer).kio_io(destination)?;
        let source_count = source_file.read(&mut source_buffer).kio_io(source)?;
        if existing_count != source_count
            || existing_buffer[..existing_count] != source_buffer[..source_count]
        {
            return Err(corrupt_object_error(
                destination,
                "existing CAS object does not match expected bytes",
                expected_hash,
                None,
            ));
        }
        if existing_count == 0 {
            return Ok(());
        }
    }
}

/// Read and fully verify the embedding object at one exact path. Path-scoped
/// (rather than hash-scoped) so removal can re-verify the hard-linked
/// quarantine copy `remove_verified_cas_path` makes, which lives beside the
/// canonical leaf rather than at it.
fn read_embedding_path(path: &Path, expected_hash: &str) -> Result<EmbeddingObject> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|_| KioError::not_found(expected_hash))
        .and_then(|metadata| {
            if metadata.file_type().is_file() {
                Ok(metadata)
            } else {
                Err(non_regular_object_error(path))
            }
        })?;
    if metadata.len() > MAX_EMBEDDING_OBJECT_BYTES {
        return Err(embedding_corrupt_error(
            "embedding object exceeds its byte limit",
            Some(path),
        ));
    }
    let bytes = fs::read(path).kio_io(path)?;
    let object = EmbeddingObject::from_bytes(&bytes)
        .map_err(|error| embedding_corrupt_error(error.message(), Some(path)))?;
    if object.identity_hash()? != expected_hash {
        return Err(embedding_corrupt_error(
            "embedding object identity does not match its storage key",
            Some(path),
        ));
    }
    Ok(object)
}

fn read_chunk_path(path: &Path, expected_hash: &str) -> Result<(ChunkObject, Vec<u8>)> {
    read_chunk_path_accounted(path, expected_hash).0
}

fn read_chunk_path_accounted(
    path: &Path,
    expected_hash: &str,
) -> (Result<(ChunkObject, Vec<u8>)>, u64) {
    let mut consumed = 0_u64;
    let result = (|| -> Result<(ChunkObject, Vec<u8>)> {
        let file = open_regular_nofollow(path)?;
        let metadata = file.metadata().kio_io(path)?;
        if metadata.len() > MAX_CHUNK_OBJECT_BYTES {
            return Err(chunk_size_error(metadata.len()));
        }
        let mut bytes = Vec::with_capacity(metadata.len() as usize);
        file.take(MAX_CHUNK_OBJECT_BYTES.saturating_add(1))
            .read_to_end(&mut bytes)
            .kio_io(path)?;
        consumed = bytes.len() as u64;
        if consumed > MAX_CHUNK_OBJECT_BYTES {
            return Err(chunk_size_error(consumed));
        }
        let object: ChunkObject = serde_json::from_slice(&bytes)
            .map_err(|_| chunk_corrupt_error("chunk object schema is invalid", Some(path)))?;
        object
            .validate()
            .map_err(|_| chunk_corrupt_error("chunk object semantics are invalid", Some(path)))?;
        if object.identity_hash()? != expected_hash {
            return Err(chunk_corrupt_error(
                "chunk semantic identity does not match its fan-out key",
                Some(path),
            ));
        }
        let canonical = canonical_json_bytes(
            &serde_json::to_value(&object).map_err(|error| KioError::schema(error.to_string()))?,
        )?;
        if canonical != bytes {
            return Err(chunk_corrupt_error(
                "chunk object is not canonical JSON",
                Some(path),
            ));
        }
        Ok((object, bytes))
    })();
    (result, consumed)
}

fn create_private_temp(parent: &Path) -> Result<(PathBuf, File)> {
    for attempt in 0..16_u8 {
        let path = parent.join(format!(
            ".tmp-{}-{}-{attempt}",
            std::process::id(),
            unix_nanos()
        ));
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
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
        "could not allocate a unique CAS temporary file",
        parent.display().to_string(),
    ))
}

/// Require a real directory at `path`, optionally creating that one missing
/// component.  Callers creating a nested path must validate every component
/// independently; `create_dir_all` would otherwise follow a hostile link.
pub fn ensure_real_directory(path: &Path, create: bool) -> Result<()> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_dir() && !metadata.file_type().is_symlink() => {
            Ok(())
        }
        Ok(_) => Err(non_regular_object_error(path)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound && create => {
            match fs::create_dir(path) {
                Ok(()) => Ok(()),
                Err(create_error) if create_error.kind() == std::io::ErrorKind::AlreadyExists => {
                    ensure_real_directory(path, false)
                }
                Err(create_error) => Err(KioError::io(
                    create_error.to_string(),
                    path.display().to_string(),
                )),
            }
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            Err(KioError::not_found(path.display().to_string()))
        }
        Err(error) => Err(KioError::io(error.to_string(), path.display().to_string())),
    }
}

/// Open a real, single-link regular file without following its final symlink
/// or reparse point, and bind the returned handle to the verified path entry.
pub fn open_regular_nofollow(path: &Path) -> Result<File> {
    let before = fs::symlink_metadata(path).kio_io(path)?;
    if !before.file_type().is_file() || before.file_type().is_symlink() {
        return Err(non_regular_object_error(path));
    }

    let mut options = OpenOptions::new();
    options.read(true);
    configure_no_follow(&mut options);
    let file = options.open(path).kio_io(path)?;
    let opened = file.metadata().kio_io(path)?;
    let after = fs::symlink_metadata(path).kio_io(path)?;
    #[cfg(windows)]
    let same_identity = {
        let mut verification_options = OpenOptions::new();
        verification_options.read(true);
        configure_no_follow(&mut verification_options);
        let verification = verification_options.open(path).kio_io(path)?;
        verification.metadata().kio_io(path)?.is_file()
            && same_windows_cas_file(&file, &verification)
    };
    #[cfg(not(windows))]
    let same_identity = same_file_identity(&opened, &after);
    if !opened.is_file()
        || !after.file_type().is_file()
        || after.file_type().is_symlink()
        || !same_identity
    {
        return Err(non_regular_object_error(path));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if opened.nlink() != 1 {
            return Err(non_regular_object_error(path));
        }
    }
    Ok(file)
}

/// Open an existing metadata file for reading and mutation through the same
/// no-follow, single-link, identity-checked boundary as [`open_regular_nofollow`].
pub fn open_regular_nofollow_read_write(path: &Path) -> Result<File> {
    let before = fs::symlink_metadata(path).kio_io(path)?;
    if !before.file_type().is_file() || before.file_type().is_symlink() {
        return Err(non_regular_object_error(path));
    }

    let mut options = OpenOptions::new();
    options.read(true).write(true);
    configure_no_follow(&mut options);
    let file = options.open(path).kio_io(path)?;
    validate_open_regular_nofollow(path, &file)?;
    Ok(file)
}

/// Open an existing ledger for append, or atomically create a new real regular
/// single-link ledger.  In particular, a dangling symlink is an existing path,
/// not a missing ledger to be created through.
pub fn open_or_create_regular_nofollow_append(path: &Path) -> Result<File> {
    for _ in 0..4 {
        match fs::symlink_metadata(path) {
            Ok(metadata) => {
                if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
                    return Err(non_regular_object_error(path));
                }
                let mut options = OpenOptions::new();
                options.append(true);
                configure_no_follow(&mut options);
                let file = options.open(path).kio_io(path)?;
                validate_open_regular_nofollow(path, &file)?;
                return Ok(file);
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let mut options = OpenOptions::new();
                options.write(true).append(true).create_new(true);
                configure_no_follow(&mut options);
                match options.open(path) {
                    Ok(file) => {
                        validate_open_regular_nofollow(path, &file)?;
                        return Ok(file);
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                    Err(error) => return Err(error).kio_io(path),
                }
            }
            Err(error) => return Err(error).kio_io(path),
        }
    }
    Err(KioError::io(
        "could not safely create ledger file after concurrent path changes",
        path.display().to_string(),
    ))
}

fn validate_open_regular_nofollow(path: &Path, file: &File) -> Result<()> {
    let opened = file.metadata().kio_io(path)?;
    let after = fs::symlink_metadata(path).kio_io(path)?;
    #[cfg(windows)]
    let same_identity = {
        let mut verification_options = OpenOptions::new();
        verification_options.read(true);
        configure_no_follow(&mut verification_options);
        let verification = verification_options.open(path).kio_io(path)?;
        verification.metadata().kio_io(path)?.is_file()
            && same_windows_cas_file(file, &verification)
    };
    #[cfg(not(windows))]
    let same_identity = same_file_identity(&opened, &after);
    if !opened.is_file()
        || !after.file_type().is_file()
        || after.file_type().is_symlink()
        || !same_identity
    {
        return Err(non_regular_object_error(path));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if opened.nlink() != 1 {
            return Err(non_regular_object_error(path));
        }
    }
    Ok(())
}

#[cfg(unix)]
fn configure_no_follow(options: &mut OpenOptions) {
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
fn configure_no_follow(options: &mut OpenOptions) {
    use std::os::windows::fs::OpenOptionsExt;
    options.custom_flags(0x0020_0000);
}

#[cfg(not(any(unix, windows)))]
fn configure_no_follow(_options: &mut OpenOptions) {}

#[cfg(unix)]
fn same_file_identity(opened: &fs::Metadata, path: &fs::Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    opened.dev() == path.dev() && opened.ino() == path.ino()
}

#[cfg(windows)]
pub(crate) fn same_windows_regular_file(opened: &File, path: &File) -> bool {
    same_windows_regular_file_components(
        windows_file_information(opened),
        windows_file_information(path),
    )
}

#[cfg(not(any(unix, windows)))]
fn same_file_identity(opened: &fs::Metadata, path: &fs::Metadata) -> bool {
    opened.len() == path.len() && opened.modified().ok() == path.modified().ok()
}

#[cfg(any(test, windows))]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct WindowsFileInformation {
    volume_serial_number: u32,
    file_index: u64,
    number_of_links: u32,
    file_attributes: u32,
}

#[cfg(any(test, windows))]
impl WindowsFileInformation {
    const DIRECTORY_ATTRIBUTE: u32 = 0x10;
    const REPARSE_POINT_ATTRIBUTE: u32 = 0x400;

    const fn new(
        volume_serial_number: u32,
        file_index: u64,
        number_of_links: u32,
        file_attributes: u32,
    ) -> Self {
        Self {
            volume_serial_number,
            file_index,
            number_of_links,
            file_attributes,
        }
    }

    fn same_identity(self, other: Self) -> bool {
        self.volume_serial_number == other.volume_serial_number
            && self.file_index == other.file_index
    }

    fn is_single_link(self) -> bool {
        self.number_of_links == 1
    }

    fn is_regular_file(self) -> bool {
        self.file_attributes & (Self::DIRECTORY_ATTRIBUTE | Self::REPARSE_POINT_ATTRIBUTE) == 0
    }

    fn is_real_directory(self) -> bool {
        self.file_attributes & Self::DIRECTORY_ATTRIBUTE != 0
            && self.file_attributes & Self::REPARSE_POINT_ATTRIBUTE == 0
    }

    #[cfg(windows)]
    fn directory_identity(self) -> Option<WindowsDirectoryIdentity> {
        self.is_real_directory()
            .then_some(WindowsDirectoryIdentity {
                volume_serial_number: self.volume_serial_number,
                file_index: self.file_index,
            })
    }

    #[cfg(windows)]
    fn regular_file_identity(self) -> Option<WindowsRegularFileIdentity> {
        (self.is_regular_file() && self.is_single_link()).then_some(WindowsRegularFileIdentity {
            volume_serial_number: self.volume_serial_number,
            file_index: self.file_index,
        })
    }
}

/// Stable identity of a real, non-reparse Windows directory.
///
/// Unlike directory metadata timestamps, this remains unchanged when children
/// are created or removed.  Its fields stay private so callers can compare
/// identities without treating their representation as a persistence format.
#[cfg(windows)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WindowsDirectoryIdentity {
    volume_serial_number: u32,
    file_index: u64,
}

/// Stable identity of a real, non-reparse, single-link Windows regular file.
///
/// The representation is intentionally opaque so it is only used for
/// within-operation path binding, never as a persisted identifier.
#[cfg(windows)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WindowsRegularFileIdentity {
    volume_serial_number: u32,
    file_index: u64,
}

#[cfg(test)]
pub(crate) fn same_windows_file_identity_components(
    left: Option<WindowsFileInformation>,
    right: Option<WindowsFileInformation>,
) -> bool {
    matches!((left, right), (Some(left), Some(right)) if left.same_identity(right))
}

#[cfg(any(test, windows))]
fn same_windows_regular_file_components(
    left: Option<WindowsFileInformation>,
    right: Option<WindowsFileInformation>,
) -> bool {
    matches!(
        (left, right),
        (Some(left), Some(right))
            if left.same_identity(right) && left.is_regular_file() && right.is_regular_file()
    )
}

#[cfg(windows)]
fn same_windows_cas_file(opened: &File, path: &File) -> bool {
    same_windows_cas_file_components(
        windows_file_information(opened),
        windows_file_information(path),
    )
}

#[cfg(any(test, windows))]
fn same_windows_cas_file_components(
    left: Option<WindowsFileInformation>,
    right: Option<WindowsFileInformation>,
) -> bool {
    matches!(
        (left, right),
        (Some(left), Some(right))
            if left.same_identity(right)
                && left.is_regular_file()
                && right.is_regular_file()
                && left.is_single_link()
                && right.is_single_link()
    )
}

#[cfg(any(test, windows))]
fn same_windows_repair_quarantine_file_components(
    left: Option<WindowsFileInformation>,
    right: Option<WindowsFileInformation>,
) -> bool {
    matches!(
        (left, right),
        (Some(left), Some(right))
            if left.same_identity(right)
                && left.is_regular_file()
                && right.is_regular_file()
                && left.number_of_links == 2
                && right.number_of_links == 2
    )
}

#[cfg(windows)]
fn windows_file_information(file: &File) -> Option<WindowsFileInformation> {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        BY_HANDLE_FILE_INFORMATION, GetFileInformationByHandle,
    };

    let mut information = BY_HANDLE_FILE_INFORMATION::default();
    // SAFETY: `file` owns a valid handle for the duration of the call, and
    // `information` points to writable storage of the required Win32 layout.
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut information) } == 0 {
        return None;
    }
    let file_index =
        (u64::from(information.nFileIndexHigh) << 32) | u64::from(information.nFileIndexLow);
    Some(WindowsFileInformation::new(
        information.dwVolumeSerialNumber,
        file_index,
        information.nNumberOfLinks,
        information.dwFileAttributes,
    ))
}

/// Open a Windows directory without traversing its final reparse point and
/// verify its handle attributes. `symlink_metadata().is_symlink()` alone does
/// not cover every directory reparse-point kind (notably junctions).
#[cfg(windows)]
pub fn windows_real_directory_identity(
    path: &Path,
) -> std::io::Result<Option<WindowsDirectoryIdentity>> {
    use std::os::windows::fs::OpenOptionsExt;
    use windows_sys::Win32::Storage::FileSystem::{
        FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT, FILE_READ_ATTRIBUTES,
        FILE_SHARE_DELETE, FILE_SHARE_READ, FILE_SHARE_WRITE,
    };

    let mut options = OpenOptions::new();
    options
        .read(true)
        .access_mode(FILE_READ_ATTRIBUTES)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS);
    let directory = options.open(path)?;
    Ok(windows_file_information(&directory).and_then(WindowsFileInformation::directory_identity))
}

/// Open a Windows path without following its final reparse point and return a
/// stable identity only for a real, single-link regular file.
#[cfg(windows)]
pub fn windows_real_regular_file_identity(
    path: &Path,
) -> std::io::Result<Option<WindowsRegularFileIdentity>> {
    use std::os::windows::fs::OpenOptionsExt;
    use windows_sys::Win32::Storage::FileSystem::{
        FILE_FLAG_OPEN_REPARSE_POINT, FILE_READ_ATTRIBUTES, FILE_SHARE_DELETE, FILE_SHARE_READ,
        FILE_SHARE_WRITE,
    };

    let mut options = OpenOptions::new();
    options
        .read(true)
        .access_mode(FILE_READ_ATTRIBUTES)
        .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
        .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT);
    let file = options.open(path)?;
    Ok(windows_file_information(&file).and_then(WindowsFileInformation::regular_file_identity))
}

/// Return the stable identity of an already-opened Windows directory.
///
/// This is the by-handle counterpart of [`windows_real_directory_identity`]:
/// callers that already hold the handle they intend to use must compare against
/// the handle itself, never re-open the path, or a component swapped between
/// the two opens would simply be re-observed and accepted.
#[cfg(windows)]
#[must_use]
pub fn windows_directory_handle_identity(file: &File) -> Option<WindowsDirectoryIdentity> {
    windows_file_information(file).and_then(WindowsFileInformation::directory_identity)
}

/// Return the stable identity of an already-opened Windows regular file.
#[cfg(windows)]
#[must_use]
pub fn windows_regular_file_handle_identity(file: &File) -> Option<WindowsRegularFileIdentity> {
    windows_file_information(file).and_then(WindowsFileInformation::regular_file_identity)
}

/// Return whether a Windows path is a real directory rather than any reparse
/// point, including junction kinds not reported by `is_symlink()`.
#[cfg(windows)]
pub fn windows_directory_is_real(path: &Path) -> std::io::Result<bool> {
    windows_real_directory_identity(path).map(|identity| identity.is_some())
}

/// Open a Windows leaf without following a reparse point and require a real,
/// single-link regular file. Restore uses this before replacing a destination.
#[cfg(windows)]
pub fn windows_regular_file_is_safe(path: &Path) -> std::io::Result<bool> {
    windows_real_regular_file_identity(path).map(|identity| identity.is_some())
}

fn corrupt_object_error(
    path: &Path,
    message: &str,
    expected: &str,
    actual: Option<&str>,
) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        message,
        serde_json::json!({
            "path": path,
            "expected": expected,
            "actual": actual,
        }),
        crate::ExitCode::PermanentFailure,
    )
}

fn chunk_corrupt_error(message: &str, path: Option<&Path>) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        message,
        serde_json::json!({ "path": path }),
        crate::ExitCode::PermanentFailure,
    )
}

fn embedding_corrupt_error(message: &str, path: Option<&Path>) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        message,
        serde_json::json!({ "path": path }),
        crate::ExitCode::PermanentFailure,
    )
}

/// f32 little-endian, the same representation the `embeddings` BLOB and the
/// replica use — so a vector round-trips between object, table and cache
/// without a conversion step anyone could get wrong.
fn vector_to_le_bytes(vector: &[f32]) -> Vec<u8> {
    let mut out = Vec::with_capacity(vector.len() * 4);
    for component in vector {
        out.extend_from_slice(&component.to_le_bytes());
    }
    out
}

fn vector_from_le_bytes(bytes: &[u8]) -> Vec<f32> {
    bytes
        .chunks_exact(4)
        .map(|word| f32::from_le_bytes([word[0], word[1], word[2], word[3]]))
        .collect()
}

/// Standard base64 with padding. Hand-rolled rather than pulled in as a
/// dependency: this is the only base64 in `kio-core`, and the alphabet is part
/// of a frozen on-disk format (03 §8.1) that should not move with a crate.
fn base64_encode(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for group in bytes.chunks(3) {
        let bits = (u32::from(group[0]) << 16)
            | (u32::from(group.get(1).copied().unwrap_or(0)) << 8)
            | u32::from(group.get(2).copied().unwrap_or(0));
        out.push(ALPHABET[(bits >> 18) as usize & 0x3f] as char);
        out.push(ALPHABET[(bits >> 12) as usize & 0x3f] as char);
        out.push(if group.len() > 1 {
            ALPHABET[(bits >> 6) as usize & 0x3f] as char
        } else {
            '='
        });
        out.push(if group.len() > 2 {
            ALPHABET[bits as usize & 0x3f] as char
        } else {
            '='
        });
    }
    out
}

fn base64_decode(text: &str) -> Result<Vec<u8>> {
    let decode = |byte: u8| -> Option<u32> {
        match byte {
            b'A'..=b'Z' => Some(u32::from(byte - b'A')),
            b'a'..=b'z' => Some(u32::from(byte - b'a') + 26),
            b'0'..=b'9' => Some(u32::from(byte - b'0') + 52),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    };
    let bytes = text.as_bytes();
    if !bytes.len().is_multiple_of(4) {
        return Err(embedding_corrupt_error(
            "embedding vector is not padded base64",
            None,
        ));
    }
    let mut out = Vec::with_capacity(bytes.len() / 4 * 3);
    for group in bytes.chunks(4) {
        let padding = group.iter().rev().take_while(|byte| **byte == b'=').count();
        if padding > 2 || (padding > 0 && !std::ptr::eq(group, &bytes[bytes.len() - 4..])) {
            return Err(embedding_corrupt_error(
                "embedding vector has base64 padding before its final group",
                None,
            ));
        }
        let mut bits = 0u32;
        for (index, byte) in group.iter().enumerate() {
            let sextet = if *byte == b'=' {
                0
            } else {
                decode(*byte).ok_or_else(|| {
                    embedding_corrupt_error("embedding vector holds a non-base64 byte", None)
                })?
            };
            bits |= sextet << (18 - 6 * index);
        }
        out.push((bits >> 16) as u8);
        if padding < 2 {
            out.push((bits >> 8) as u8);
        }
        if padding < 1 {
            out.push(bits as u8);
        }
    }
    Ok(out)
}

fn chunk_size_error(actual: u64) -> KioError {
    KioError::new(
        "KIO-E-STORE-OBJECT-OVERSIZED-001",
        "chunk object exceeds its byte limit",
        serde_json::json!({
            "object_type": "chunk",
            "max_bytes": MAX_CHUNK_OBJECT_BYTES,
            "actual_bytes": actual,
        }),
        crate::ExitCode::PermanentFailure,
    )
}

fn non_regular_object_error(path: &Path) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        "CAS path is not a real regular file or directory",
        serde_json::json!({ "path": path }),
        crate::ExitCode::PermanentFailure,
    )
}

fn object_size_error(kind: ObjectKind, limit: u64, actual: u64) -> KioError {
    KioError::new(
        "KIO-E-STORE-OBJECT-OVERSIZED-001",
        "CAS object exceeds its byte limit",
        serde_json::json!({
            "object_type": kind.object_type(),
            "max_bytes": limit,
            "actual_bytes": actual,
        }),
        crate::ExitCode::PermanentFailure,
    )
}

#[must_use]
pub fn hash_bytes(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    format!("sha256:{}", lower_hex(&digest))
}

pub fn hash_json(value: &Value) -> Result<String> {
    canonical_json_bytes(value).map(|bytes| hash_bytes(&bytes))
}

/// Serialize `value` to RFC 8785 (JCS) canonical JSON bytes.
///
/// Backed by the `serde_jcs` crate so the byte output matches RFC 8785
/// exactly (the object hash contract in `docs/03-data-model.md` §8.1).
pub fn canonical_json_bytes(value: &Value) -> Result<Vec<u8>> {
    serde_jcs::to_vec(value).map_err(|err| KioError::schema(err.to_string()))
}

#[must_use]
pub fn is_hash(value: &str) -> bool {
    let Some(hex) = value.strip_prefix("sha256:") else {
        return false;
    };
    hex.len() == 64
        && hex
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

/// Map a logical `sha256:<hex>` identifier to its portable digest-only leaf.
pub fn hash_path_component(hash: &str) -> Result<&str> {
    if !is_hash(hash) {
        return Err(KioError::invalid_usage("invalid hash"));
    }
    Ok(&hash["sha256:".len()..])
}

pub fn fanout_path(base: impl AsRef<Path>, hash: &str) -> Result<PathBuf> {
    let digest = hash_path_component(hash)?;
    Ok(base
        .as_ref()
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(digest))
}

/// Read a non-CAS metadata record through the same no-follow/single-link boundary
/// as CAS objects while enforcing a caller-selected byte limit.
pub fn read_bounded_regular_file(path: &Path, max_bytes: u64) -> Result<Vec<u8>> {
    let file = open_regular_nofollow(path)?;
    let metadata = file.metadata().kio_io(path)?;
    if metadata.len() > max_bytes {
        return Err(KioError::new(
            "KIO-E-STORE-OBJECT-OVERSIZED-001",
            "metadata record exceeds its byte limit",
            serde_json::json!({
                "path": path,
                "max_bytes": max_bytes,
                "actual_bytes": metadata.len(),
            }),
            crate::ExitCode::PermanentFailure,
        ));
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    file.take(max_bytes.saturating_add(1))
        .read_to_end(&mut bytes)
        .kio_io(path)?;
    if bytes.len() as u64 > max_bytes {
        return Err(KioError::new(
            "KIO-E-STORE-OBJECT-OVERSIZED-001",
            "metadata record exceeds its byte limit",
            serde_json::json!({ "path": path, "max_bytes": max_bytes }),
            crate::ExitCode::PermanentFailure,
        ));
    }
    Ok(bytes)
}

/// `Some(path)` when the CAS slot is occupied by anything at all — a symlink or
/// a directory counts, so the per-kind verification below is what rejects it,
/// not a silent "not found".
fn occupied_slot(path: PathBuf) -> Result<Option<PathBuf>> {
    match fs::symlink_metadata(&path) {
        Ok(_) => Ok(Some(path)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(KioError::io(error.to_string(), path.display().to_string())),
    }
}

pub(crate) fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KioError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kio_io(parent)?;

    if path.exists() {
        return Ok(());
    }

    let temp = parent.join(format!(".tmp-{}-{}", std::process::id(), unix_nanos()));
    // R9-8: drop the temp on any write/sync/rename failure so an ENOSPC/EIO error
    // never leaves an orphan `.tmp-*` in the CAS fanout dir (there is no GC before
    // Step 4, and such residue also feeds R9-5's junk-in-gen-dir failure). Same
    // cleanup idiom as `atomic_overwrite` below and the `markdownize.rs`/`main.rs`
    // writers.
    let result = (|| -> Result<()> {
        let mut file = File::create(&temp).kio_io(&temp)?;
        file.write_all(bytes).kio_io(&temp)?;
        file.sync_all().kio_io(&temp)?;
        drop(file);
        fs::rename(&temp, path).kio_io(path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

pub(crate) fn atomic_overwrite(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KioError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kio_io(parent)?;
    let temp = parent.join(format!(".tmp-{}-{}", std::process::id(), unix_nanos()));
    // R9-8: see `atomic_write` — remove the temp on any failure so a torn write
    // does not leave an orphan `.tmp-*` behind.
    let result = (|| -> Result<()> {
        let mut file = File::create(&temp).kio_io(&temp)?;
        file.write_all(bytes).kio_io(&temp)?;
        file.sync_all().kio_io(&temp)?;
        drop(file);
        fs::rename(&temp, path).kio_io(path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

pub(crate) fn append_jsonl(path: &Path, value: &Value) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KioError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kio_io(parent)?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .kio_io(path)?;
    // Serialize the whole record (line + newline) into one buffer and emit it in a
    // single `write_all` on the O_APPEND handle. A multi-write sequence
    // (`to_writer` then a separate newline write) can interleave byte-wise with a
    // concurrent process's record even under O_APPEND, corrupting the JSONL
    // (M1(b)). One `write_all` of the framed record is atomic per append.
    let mut line = serde_json::to_string(value)
        .map_err(|err| KioError::io(err.to_string(), path.display().to_string()))?;
    line.push('\n');
    file.write_all(line.as_bytes()).kio_io(path)?;
    Ok(())
}

/// Encode bytes as canonical lowercase hexadecimal text.
#[must_use]
pub fn lower_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

fn unix_nanos() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn object_store() -> (tempfile::TempDir, ObjectStore) {
        let dir = tempfile::tempdir().unwrap();
        let kio_dir = dir.path().join(".kio");
        fs::create_dir(&kio_dir).unwrap();
        let store = ObjectStore::new(kio_dir);
        (dir, store)
    }

    fn embedding_object(vector: Vec<f32>) -> EmbeddingObject {
        EmbeddingObject {
            spec_version: 1,
            target_type: "chunk".to_owned(),
            target_hash: "sha256:text".to_owned(),
            profile_hash: "sha256:profile".to_owned(),
            modality: "multimodal".to_owned(),
            dimensions: vector.len() as u64,
            distance: "cosine".to_owned(),
            context: Some("recovery window".to_owned()),
            vector,
        }
    }

    #[test]
    fn an_embedding_object_round_trips_through_its_stored_bytes() {
        let object = embedding_object(vec![0.5, -0.25, 0.125]);
        let bytes = object.to_bytes().unwrap();
        assert_eq!(EmbeddingObject::from_bytes(&bytes).unwrap(), object);
        // 03 §8.1's shape: header, vector, digest — three lines, no more.
        let text = String::from_utf8(bytes).unwrap();
        let lines = text.split('\n').collect::<Vec<_>>();
        assert_eq!(lines.len(), 3, "{text}");
        assert!(lines[0].starts_with('{') && lines[0].ends_with('}'));
    }

    #[test]
    fn an_embedding_identity_ignores_the_vector_and_follows_the_context() {
        // The storage key names what the vector is OF. Two different vectors
        // for the same target collide by design (that is how a re-send is
        // idempotent); two different contexts must not (07 §5.3's addendum —
        // else two chunks with identical bodies in differently named files
        // share one wrong vector).
        let base = embedding_object(vec![1.0, 0.0]);
        let mut other_vector = base.clone();
        other_vector.vector = vec![0.0, 1.0];
        assert_eq!(
            base.identity_hash().unwrap(),
            other_vector.identity_hash().unwrap()
        );

        let mut other_context = base.clone();
        other_context.context = Some("control coverage".to_owned());
        assert_ne!(
            base.identity_hash().unwrap(),
            other_context.identity_hash().unwrap()
        );

        let mut no_context = base.clone();
        no_context.context = None;
        assert_ne!(
            base.identity_hash().unwrap(),
            no_context.identity_hash().unwrap()
        );
    }

    #[test]
    fn a_bit_flip_inside_the_vector_is_caught_by_the_trailing_digest() {
        // The storage key cannot catch this: it hashes the identity, not the
        // body. Without the digest a corrupted vector would rebuild silently
        // and quietly degrade every search that touched it.
        let object = embedding_object(vec![0.5, -0.25]);
        let mut bytes = object.to_bytes().unwrap();
        let body_start = bytes.iter().position(|byte| *byte == b'\n').unwrap() + 1;
        bytes[body_start] = if bytes[body_start] == b'A' {
            b'B'
        } else {
            b'A'
        };
        let error = EmbeddingObject::from_bytes(&bytes).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
    }

    #[test]
    fn an_embedding_object_rejects_a_length_or_finiteness_violation() {
        let mut short = embedding_object(vec![0.5, 0.5]);
        short.dimensions = 3;
        assert!(short.to_bytes().is_err());

        let nan = embedding_object(vec![f32::NAN, 0.5]);
        assert!(nan.to_bytes().is_err());
    }

    #[test]
    fn writing_an_embedding_publishes_it_under_its_identity_and_reads_back() {
        let (_dir, store) = object_store();
        let object = embedding_object(vec![0.5, -0.25, 0.125]);
        let hash = store.write_embedding(&object).unwrap();
        assert_eq!(hash, object.identity_hash().unwrap());
        assert_eq!(store.read_embedding(&hash).unwrap(), object);
        assert_eq!(store.embedding_hashes().unwrap(), vec![hash.clone()]);
        // Idempotent: the same vector re-published verifies rather than errors.
        assert_eq!(store.write_embedding(&object).unwrap(), hash);
    }

    #[test]
    fn reading_an_embedding_rejects_bytes_filed_under_the_wrong_identity() {
        let (_dir, store) = object_store();
        let object = embedding_object(vec![1.0, 0.0]);
        let hash = store.write_embedding(&object).unwrap();

        let mut impostor = object.clone();
        impostor.target_hash = "sha256:someone-else".to_owned();
        fs::write(
            store.embedding_path(&hash).unwrap(),
            impostor.to_bytes().unwrap(),
        )
        .unwrap();

        let error = store.read_embedding(&hash).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
    }

    fn stray_temp_files(dir: &Path) -> Vec<String> {
        fs::read_dir(dir)
            .unwrap()
            .filter_map(std::result::Result::ok)
            .map(|entry| entry.file_name().to_string_lossy().into_owned())
            .filter(|name| name.starts_with(".tmp-"))
            .collect()
    }

    #[test]
    fn windows_identity_components_require_complete_exact_match() {
        let identity = WindowsFileInformation::new(7, 11, 1, 0);
        assert!(same_windows_file_identity_components(
            Some(identity),
            Some(identity)
        ));
        assert!(!same_windows_file_identity_components(
            Some(identity),
            Some(WindowsFileInformation::new(7, 12, 1, 0))
        ));
        assert!(!same_windows_file_identity_components(
            Some(identity),
            Some(WindowsFileInformation::new(8, 11, 1, 0))
        ));
        assert!(!same_windows_file_identity_components(Some(identity), None));
        assert!(!same_windows_file_identity_components(None, None));
    }

    #[test]
    fn windows_cas_components_require_regular_single_link_handles() {
        let single_link = WindowsFileInformation::new(7, 11, 1, 0);
        let hard_linked = WindowsFileInformation::new(7, 11, 2, 0);
        let extra_link = WindowsFileInformation::new(7, 11, 3, 0);
        let directory =
            WindowsFileInformation::new(7, 11, 1, WindowsFileInformation::DIRECTORY_ATTRIBUTE);
        let reparse_point =
            WindowsFileInformation::new(7, 11, 1, WindowsFileInformation::REPARSE_POINT_ATTRIBUTE);

        assert!(same_windows_file_identity_components(
            Some(single_link),
            Some(hard_linked)
        ));
        assert!(same_windows_regular_file_components(
            Some(single_link),
            Some(hard_linked)
        ));
        assert!(!same_windows_regular_file_components(
            Some(single_link),
            Some(directory)
        ));
        assert!(!same_windows_regular_file_components(
            Some(single_link),
            Some(reparse_point)
        ));
        assert!(same_windows_cas_file_components(
            Some(single_link),
            Some(single_link)
        ));
        assert!(!same_windows_cas_file_components(
            Some(single_link),
            Some(hard_linked)
        ));
        assert!(!same_windows_cas_file_components(
            Some(hard_linked),
            Some(hard_linked)
        ));
        assert!(!same_windows_cas_file_components(
            Some(directory),
            Some(directory)
        ));
        assert!(!same_windows_cas_file_components(
            Some(reparse_point),
            Some(reparse_point)
        ));
        assert!(!same_windows_cas_file_components(Some(single_link), None));
        assert!(same_windows_repair_quarantine_file_components(
            Some(hard_linked),
            Some(hard_linked)
        ));
        assert!(!same_windows_repair_quarantine_file_components(
            Some(single_link),
            Some(single_link)
        ));
        assert!(!same_windows_repair_quarantine_file_components(
            Some(hard_linked),
            Some(extra_link)
        ));
        assert!(!same_windows_repair_quarantine_file_components(
            Some(directory),
            Some(directory)
        ));
        assert!(directory.is_real_directory());
        assert!(!reparse_point.is_real_directory());
        assert!(!single_link.is_real_directory());
    }

    #[cfg(windows)]
    #[test]
    fn windows_handle_identity_distinguishes_distinct_equal_sized_files() {
        let dir = tempfile::tempdir().unwrap();
        let first = dir.path().join("first.bin");
        let second = dir.path().join("second.bin");
        fs::write(&first, b"same-size").unwrap();
        fs::write(&second, b"same-size").unwrap();
        let first_handle = File::open(&first).unwrap();
        let same_handle = File::open(&first).unwrap();
        let second_handle = File::open(&second).unwrap();

        let information = windows_file_information(&first_handle).unwrap();
        assert!(information.is_regular_file());
        assert!(information.is_single_link());
        assert_eq!(
            windows_real_regular_file_identity(&first).unwrap(),
            windows_regular_file_handle_identity(&first_handle)
        );
        assert_ne!(
            windows_real_regular_file_identity(&first).unwrap(),
            windows_real_regular_file_identity(&second).unwrap()
        );
        assert!(same_windows_regular_file(&first_handle, &same_handle));
        assert!(!same_windows_regular_file(&first_handle, &second_handle));
        assert!(open_regular_nofollow(&first).is_ok());
    }

    /// The property restore's PA18 destination binding rests on: an identity
    /// captured from a path must still match a handle later opened on that same
    /// directory, and must NOT match once a different real directory has taken
    /// over the name.
    #[cfg(windows)]
    #[test]
    fn windows_directory_handle_identity_matches_its_path_and_detects_a_swap() {
        use std::os::windows::fs::OpenOptionsExt;
        use windows_sys::Win32::Storage::FileSystem::{
            FILE_FLAG_BACKUP_SEMANTICS, FILE_FLAG_OPEN_REPARSE_POINT, FILE_READ_ATTRIBUTES,
            FILE_SHARE_DELETE, FILE_SHARE_READ, FILE_SHARE_WRITE,
        };

        fn open_directory(path: &Path) -> File {
            let mut options = OpenOptions::new();
            options
                .read(true)
                .access_mode(FILE_READ_ATTRIBUTES)
                .share_mode(FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE)
                .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS);
            options.open(path).unwrap()
        }

        let root = tempfile::tempdir().unwrap();
        let destination = root.path().join("destination");
        let decoy = root.path().join("decoy");
        fs::create_dir(&destination).unwrap();
        fs::create_dir(&decoy).unwrap();

        let captured = windows_real_directory_identity(&destination)
            .unwrap()
            .unwrap();
        {
            let opened = open_directory(&destination);
            assert_eq!(windows_directory_handle_identity(&opened), Some(captured));
        }

        // The swap PA18 exists to catch: the validated name now resolves to a
        // different real directory.
        fs::rename(&destination, root.path().join("moved")).unwrap();
        fs::rename(&decoy, &destination).unwrap();
        let swapped = open_directory(&destination);
        assert_ne!(windows_directory_handle_identity(&swapped), Some(captured));

        // A non-directory carries no directory identity, so callers comparing
        // against `Some(expected)` fail closed rather than matching.
        let regular = root.path().join("regular.bin");
        fs::write(&regular, b"payload").unwrap();
        assert_eq!(
            windows_directory_handle_identity(&File::open(&regular).unwrap()),
            None
        );
    }

    #[test]
    fn atomic_overwrite_removes_temp_on_rename_failure() {
        // R9-8: `atomic_overwrite` (and its twin `atomic_write`, which shares this
        // cleanup idiom) must remove its temp on any failure so an ENOSPC/EIO error
        // never leaves an orphan `.tmp-*` in the CAS fanout dir. Force the rename to
        // fail deterministically by making the destination an existing directory
        // (`rename(file, dir)` → EISDIR) after the temp is created + fsynced.
        let dir = tempfile::tempdir().unwrap();
        let dest = dir.path().join("target");
        fs::create_dir(&dest).unwrap();
        let result = atomic_overwrite(&dest, b"payload");
        assert!(result.is_err(), "overwrite onto a directory must fail");
        assert!(
            stray_temp_files(dir.path()).is_empty(),
            "R9-8: temp must be cleaned up on failure, found {:?}",
            stray_temp_files(dir.path())
        );
    }

    #[test]
    fn atomic_overwrite_succeeds_and_leaves_no_temp() {
        let dir = tempfile::tempdir().unwrap();
        let dest = dir.path().join("obj");
        atomic_overwrite(&dest, b"hello").unwrap();
        assert_eq!(fs::read(&dest).unwrap(), b"hello");
        assert!(stray_temp_files(dir.path()).is_empty());
    }

    #[test]
    fn cand_043_existing_cas_slot_must_match_exact_bytes() {
        let (_dir, store) = object_store();
        let expected = b"expected payload";
        let hash = store.write_raw(expected).unwrap();
        let path = store.object_path(ObjectKind::Raw, &hash).unwrap();

        store.write_raw(expected).unwrap();
        fs::write(&path, b"poisoned payload").unwrap();
        let error = store.write_raw(expected).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
        assert_eq!(fs::read(&path).unwrap(), b"poisoned payload");
    }

    #[test]
    fn cand_043_existing_directory_is_not_an_idempotent_cas_write() {
        let (_dir, store) = object_store();
        let expected = b"expected payload";
        let hash = hash_bytes(expected);
        store.ensure_object_parent(ObjectKind::Tree, &hash).unwrap();
        let path = store.object_path(ObjectKind::Tree, &hash).unwrap();
        fs::create_dir(&path).unwrap();

        let error = store
            .write_object_bytes(ObjectKind::Tree, &hash, expected)
            .unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
    }

    #[cfg(unix)]
    #[test]
    fn cand_043_existing_symlink_is_not_an_idempotent_cas_write() {
        use std::os::unix::fs::symlink;

        let (dir, store) = object_store();
        let expected = b"expected payload";
        let hash = hash_bytes(expected);
        store.ensure_object_parent(ObjectKind::Raw, &hash).unwrap();
        let path = store.object_path(ObjectKind::Raw, &hash).unwrap();
        let outside = dir.path().join("outside");
        fs::write(&outside, expected).unwrap();
        symlink(&outside, &path).unwrap();

        let error = store.write_raw(expected).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
    }

    #[cfg(any(unix, windows))]
    #[test]
    fn cand_043_existing_hardlink_is_not_an_immutable_cas_slot() {
        let (dir, store) = object_store();
        let expected = b"expected payload";
        let hash = hash_bytes(expected);
        store.ensure_object_parent(ObjectKind::Raw, &hash).unwrap();
        let path = store.object_path(ObjectKind::Raw, &hash).unwrap();
        let outside = dir.path().join("outside-hardlink");
        fs::write(&outside, expected).unwrap();
        fs::hard_link(&outside, &path).unwrap();

        #[cfg(windows)]
        {
            let information = windows_file_information(&File::open(&path).unwrap()).unwrap();
            assert!(information.is_regular_file());
            assert!(!information.is_single_link());
        }

        let error = store.write_raw(expected).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
    }

    #[test]
    fn cand_019_streaming_raw_writer_enforces_exact_limit_and_cleans_temp() {
        let (_dir, store) = object_store();
        let bytes = vec![b'x'; CAS_STREAM_BUFFER_BYTES];
        let (hash, consumed) = store
            .write_raw_reader(&mut Cursor::new(&bytes), bytes.len() as u64)
            .unwrap();
        assert_eq!(consumed, bytes.len() as u64);
        assert_eq!(hash, hash_bytes(&bytes));

        let error = store
            .write_raw_reader(
                &mut Cursor::new(vec![b'y'; CAS_STREAM_BUFFER_BYTES + 1]),
                CAS_STREAM_BUFFER_BYTES as u64,
            )
            .unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-OBJECT-OVERSIZED-001");
        let raw_base = store.kio_dir.join("objects/raw");
        assert!(stray_temp_files(&raw_base).is_empty());
    }

    #[test]
    fn cand_046_raw_inspect_streams_verified_size_without_returning_body() {
        let (_dir, store) = object_store();
        let bytes = vec![b'z'; 2 * CAS_STREAM_BUFFER_BYTES + 17];
        let hash = store.write_raw(&bytes).unwrap();
        let metadata = store.inspect_by_hash(&hash).unwrap();
        assert_eq!(metadata.kind, ObjectKind::Raw);
        assert_eq!(metadata.hash, hash);
        assert_eq!(metadata.size_bytes, bytes.len() as u64);
    }

    #[test]
    fn cand_046_structured_object_above_limit_is_rejected_before_materialization() {
        let (_dir, store) = object_store();
        let hash = hash_bytes(b"placeholder");
        store
            .ensure_object_parent(ObjectKind::Commit, &hash)
            .unwrap();
        let path = store.object_path(ObjectKind::Commit, &hash).unwrap();
        let file = File::create(&path).unwrap();
        file.set_len(MAX_COMMIT_OBJECT_BYTES + 1).unwrap();

        let error = store.read_by_hash(&hash).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-OBJECT-OVERSIZED-001");
    }

    #[test]
    fn cand_046_digest_mismatch_still_reports_store_corruption() {
        let (_dir, store) = object_store();
        let hash = hash_bytes(b"expected");
        store.ensure_object_parent(ObjectKind::Raw, &hash).unwrap();
        let path = store.object_path(ObjectKind::Raw, &hash).unwrap();
        fs::write(&path, b"different").unwrap();

        let error = store.inspect_by_hash(&hash).unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
    }

    #[test]
    fn purge_remove_raw_is_verified_and_idempotent() {
        let (_dir, store) = object_store();
        let bytes = b"purge target";
        let hash = store.write_raw(bytes).unwrap();
        assert!(store.remove_raw(&hash).unwrap());
        assert!(!store.object_path(ObjectKind::Raw, &hash).unwrap().exists());
        assert!(!store.remove_raw(&hash).unwrap());
    }

    #[cfg(unix)]
    #[test]
    fn purge_remove_raw_rejects_hardlink_without_unlinking_either_name() {
        let (dir, store) = object_store();
        let bytes = b"hardlinked purge target";
        let hash = store.write_raw(bytes).unwrap();
        let canonical = store.object_path(ObjectKind::Raw, &hash).unwrap();
        let outside = dir.path().join("outside-hardlink");
        fs::hard_link(&canonical, &outside).unwrap();
        assert_eq!(
            store.remove_raw(&hash).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&canonical).unwrap(), bytes);
        assert_eq!(fs::read(&outside).unwrap(), bytes);
    }

    fn chunk_object(text: &str) -> ChunkObject {
        ChunkObject {
            spec_version: 1,
            raw_hash: format!("sha256:{}", "a".repeat(64)),
            tool_profile_hash: format!("sha256:{}", "b".repeat(64)),
            r#gen: 3,
            unit_key: "page:12".to_owned(),
            unit_content_hash: format!("sha256:{}", "c".repeat(64)),
            heading_path: vec!["Auth".to_owned()],
            section_id: Some("auth".to_owned()),
            byte_start: 0,
            byte_end: text.len() as u64,
            text_hash: hash_bytes(text.as_bytes()),
            text: text.to_owned(),
        }
    }

    #[test]
    fn ct4_chunk_cas_round_trips_semantic_identity() {
        let (_dir, store) = object_store();
        let chunk = chunk_object("TTL is 3600 seconds.");
        let expected = chunk.identity_hash().unwrap();
        assert_eq!(store.write_chunk(&chunk).unwrap(), expected);
        assert_eq!(store.read_chunk(&expected).unwrap(), chunk);
        assert!(
            !fs::read(store.chunk_path(&expected).unwrap())
                .unwrap()
                .windows(b"chunk_hash".len())
                .any(|window| window == b"chunk_hash")
        );
    }

    #[test]
    fn chunk_identity_binds_normalized_unit_content() {
        let chunk = chunk_object("stable text");
        let original = chunk.identity_hash().unwrap();

        let mut retargeted = chunk.clone();
        retargeted.unit_content_hash = format!("sha256:{}", "d".repeat(64));
        assert_ne!(retargeted.identity_hash().unwrap(), original);

        let mut changed_body = chunk.clone();
        changed_body.text.push('!');
        changed_body.text_hash = hash_bytes(changed_body.text.as_bytes());
        assert_eq!(changed_body.identity_hash().unwrap(), original);
    }

    #[test]
    fn chunk_object_rejects_legacy_missing_unit_content_hash() {
        let mut value = serde_json::to_value(chunk_object("stable text")).unwrap();
        value.as_object_mut().unwrap().remove("unit_content_hash");
        assert!(serde_json::from_value::<ChunkObject>(value).is_err());
    }

    /// A corrupt content object is charged for every byte it made fsck read,
    /// so one aggregate budget still bounds an adversarial store.
    #[test]
    fn ct4_fsck_content_read_reports_consumed_bytes_even_when_it_fails() {
        let (_dir, store) = object_store();
        let chunk = chunk_object("single representation");
        let chunk_hash = store.write_chunk(&chunk).unwrap();
        let chunk_bytes = fs::read(store.chunk_path(&chunk_hash).unwrap()).unwrap();
        assert_eq!(
            store.read_chunk_with_size(&chunk_hash).unwrap().1,
            chunk_bytes.len() as u64
        );

        let image_bytes = b"image-object";
        let image_hash = hash_bytes(image_bytes);
        let image_path = store
            .content_path(ContentObjectKind::Image, &image_hash)
            .unwrap();
        fs::create_dir_all(image_path.parent().unwrap()).unwrap();
        fs::write(&image_path, image_bytes).unwrap();
        assert_eq!(
            store
                .inspect_content_object(ContentObjectKind::Image, &image_hash)
                .unwrap()
                .size_bytes,
            image_bytes.len() as u64
        );

        let poisoned = b"poisoned-img";
        fs::write(&image_path, poisoned).unwrap();
        let accounted = store
            .inspect_content_accounted(ContentObjectKind::Image, &image_hash)
            .unwrap_err();
        assert_eq!(accounted.consumed_bytes, poisoned.len() as u64);
        assert_eq!(
            store
                .inspect_content_object(ContentObjectKind::Image, &image_hash)
                .unwrap_err()
                .error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
    }

    #[test]
    fn normalized_unit_content_objects_use_the_dedicated_immutable_namespace() {
        let (_dir, store) = object_store();
        let bytes = br#"{"markdown":"immutable normalized unit"}"#;
        let hash = store
            .write_content_object(ContentObjectKind::NormalizedUnit, bytes)
            .unwrap();
        assert_eq!(
            store
                .read_content_object_bytes(ContentObjectKind::NormalizedUnit, &hash, 1024)
                .unwrap(),
            bytes
        );
        assert!(
            store
                .content_path(ContentObjectKind::NormalizedUnit, &hash)
                .unwrap()
                .to_string_lossy()
                .contains("objects/normalized_unit_objects")
        );
    }

    #[test]
    fn manifest_content_objects_enforce_the_semantic_read_limit_at_cas_boundary() {
        let (_dir, store) = object_store();
        let hash = hash_bytes(b"manifest-size-fixture");
        let path = store
            .content_path(ContentObjectKind::Manifest, &hash)
            .unwrap();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        let file = fs::File::create(&path).unwrap();
        file.set_len(MAX_MANIFEST_OBJECT_BYTES + 1).unwrap();

        let error = store
            .inspect_content_accounted(ContentObjectKind::Manifest, &hash)
            .unwrap_err();
        assert_eq!(error.error.error_code(), "KIO-E-STORE-OBJECT-OVERSIZED-001");
        assert_eq!(error.consumed_bytes, 0);
    }

    #[test]
    fn ct4_fsck_repair_raw_atomically_replaces_one_corrupt_slot() {
        let (_dir, store) = object_store();
        let expected = b"recoverable raw body";
        let hash = store.write_raw(expected).unwrap();
        let path = store.object_path(ObjectKind::Raw, &hash).unwrap();
        fs::write(&path, b"poisoned raw bytes").unwrap();

        assert!(store.repair_raw(&hash, expected).unwrap());
        assert_eq!(fs::read(&path).unwrap(), expected);
        assert_eq!(
            store.inspect_object(ObjectKind::Raw, &hash).unwrap().hash,
            hash
        );
        assert!(fs::read_dir(path.parent().unwrap()).unwrap().all(|entry| {
            !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with(".repair-quarantine-")
        }));
    }

    #[test]
    fn ct4_fsck_failed_raw_read_reports_exact_consumed_bytes() {
        let (_dir, store) = object_store();
        let expected = b"expected accounted bytes";
        let hash = store.write_raw(expected).unwrap();
        let path = store.object_path(ObjectKind::Raw, &hash).unwrap();
        let poisoned = vec![b'x'; expected.len()];
        fs::write(&path, &poisoned).unwrap();

        let failure = store
            .inspect_object_accounted(ObjectKind::Raw, &hash)
            .unwrap_err();
        assert_eq!(failure.error.error_code(), "KIO-E-STORE-CORRUPT-001");
        assert_eq!(failure.consumed_bytes, poisoned.len() as u64);
    }

    #[cfg(any(unix, windows))]
    #[test]
    fn ct4_fsck_repair_raw_rejects_hardlink_without_external_unlink() {
        let (dir, store) = object_store();
        let expected = b"hardlink repair bytes";
        let hash = store.write_raw(expected).unwrap();
        let path = store.object_path(ObjectKind::Raw, &hash).unwrap();
        let outside = dir.path().join("outside-repair-link");
        fs::hard_link(&path, &outside).unwrap();
        fs::write(&path, b"linked corrupt bytes").unwrap();

        assert_eq!(
            store.repair_raw(&hash, expected).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
        assert!(path.exists());
        assert!(outside.exists());
        assert_eq!(fs::read(&outside).unwrap(), b"linked corrupt bytes");
    }

    #[test]
    fn ct4_chunk_cas_rejects_text_hash_and_fanout_mismatch() {
        let (_dir, store) = object_store();
        let chunk = chunk_object("trusted");
        let hash = store.write_chunk(&chunk).unwrap();
        let path = store.chunk_path(&hash).unwrap();
        let mut value: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        value["text"] = Value::from("poisoned");
        fs::write(&path, canonical_json_bytes(&value).unwrap()).unwrap();
        let poisoned_len = fs::metadata(&path).unwrap().len();
        assert_eq!(
            store
                .read_chunk_accounted(&hash)
                .unwrap_err()
                .consumed_bytes,
            poisoned_len
        );
        assert_eq!(
            store.read_chunk(&hash).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
    }

    #[test]
    fn purge_remove_chunk_verifies_identity_and_is_idempotent() {
        let (_dir, store) = object_store();
        let chunk = chunk_object("purge semantic chunk");
        let hash = store.write_chunk(&chunk).unwrap();
        assert!(store.remove_chunk(&hash).unwrap());
        assert!(!store.chunk_path(&hash).unwrap().exists());
        assert!(!store.remove_chunk(&hash).unwrap());
    }

    /// The embeddings namespace is keyed by identity, not by the bytes, so it
    /// needs its own removal primitive: `remove_content` re-hashes the leaf and
    /// so calls a healthy embedding object corrupt (the purge defect this
    /// method fixes — purge deleted the orphan SQLite row, then aborted the
    /// whole phase on the CAS object it was supposed to delete alongside it).
    #[test]
    fn purge_remove_embedding_verifies_identity_and_is_idempotent() {
        let (_dir, store) = object_store();
        let hash = store
            .write_embedding(&embedding_object(vec![0.5, -0.25, 0.125]))
            .unwrap();
        let path = store.embedding_path(&hash).unwrap();
        assert_eq!(
            store
                .remove_content(ContentObjectKind::Embedding, &hash)
                .unwrap_err()
                .error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
        assert!(path.exists());

        assert!(store.remove_embedding(&hash).unwrap());
        assert!(!path.exists());
        assert!(!store.remove_embedding(&hash).unwrap());
    }

    #[test]
    fn purge_remove_content_verifies_bytes_and_is_idempotent() {
        let (_dir, store) = object_store();
        let bytes = b"purge image content";
        let hash = hash_bytes(bytes);
        let path = store.content_path(ContentObjectKind::Image, &hash).unwrap();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, bytes).unwrap();
        assert!(
            store
                .remove_content(ContentObjectKind::Image, &hash)
                .unwrap()
        );
        assert!(!path.exists());
        assert!(
            !store
                .remove_content(ContentObjectKind::Image, &hash)
                .unwrap()
        );
    }

    #[cfg(unix)]
    #[test]
    fn purge_remove_content_rejects_hardlink_without_unlinking() {
        let (dir, store) = object_store();
        let bytes = b"hardlinked purge image";
        let hash = hash_bytes(bytes);
        let path = store.content_path(ContentObjectKind::Image, &hash).unwrap();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, bytes).unwrap();
        let outside = dir.path().join("outside-image-hardlink");
        fs::hard_link(&path, &outside).unwrap();
        assert_eq!(
            store
                .remove_content(ContentObjectKind::Image, &hash)
                .unwrap_err()
                .error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&path).unwrap(), bytes);
        assert_eq!(fs::read(&outside).unwrap(), bytes);
    }

    #[cfg(unix)]
    #[test]
    fn bound_store_keeps_raw_publication_inside_retained_namespace_after_path_swap() {
        use std::os::unix::fs::symlink;

        let dir = tempfile::tempdir().unwrap();
        let kio = dir.path().join(".kio");
        let objects = kio.join("objects");
        for kind in ["raw", "trees", "commits"] {
            fs::create_dir_all(objects.join(kind)).unwrap();
        }
        let kio_handle = File::open(&kio).unwrap();
        let store = ObjectStore::from_bound_kio(&kio_handle).unwrap();
        let retained_raw = objects.join("raw-retained");
        fs::rename(objects.join("raw"), &retained_raw).unwrap();
        let victim = tempfile::tempdir().unwrap();
        symlink(victim.path(), objects.join("raw")).unwrap();

        for (kind, bytes) in [
            (ObjectKind::Tree, b"bound tree publication".as_slice()),
            (ObjectKind::Commit, b"bound commit publication".as_slice()),
        ] {
            let hash = hash_bytes(bytes);
            store.write_object_bytes(kind, &hash, bytes).unwrap();
            assert_eq!(store.read_object(kind, &hash).unwrap().bytes, bytes);
        }
        let bytes = b"bound raw publication";
        let hash = store.write_raw(bytes).unwrap();
        let digest = hash_path_component(&hash).unwrap();
        let retained_leaf = retained_raw
            .join(&digest[..2])
            .join(&digest[2..4])
            .join(digest);
        assert_eq!(fs::read(retained_leaf).unwrap(), bytes);
        assert!(fs::read_dir(victim.path()).unwrap().next().is_none());
        assert_eq!(
            store.read_object(ObjectKind::Raw, &hash).unwrap().bytes,
            bytes
        );
    }
}
