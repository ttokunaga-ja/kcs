//! Content-addressed storage primitives.

use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::error::{IoResultExt, KcsError, Result};

pub const CAS_STREAM_BUFFER_BYTES: usize = 64 * 1024;
pub const MAX_RAW_OBJECT_BYTES: u64 = 512 * 1024 * 1024;
pub const MAX_TREE_OBJECT_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_COMMIT_OBJECT_BYTES: u64 = 1024 * 1024;
/// Semantic chunk objects contain bounded normalized text, never raw file bytes.
pub const MAX_CHUNK_OBJECT_BYTES: u64 = 128 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContentObjectKind {
    Prepared,
    Image,
}

impl ContentObjectKind {
    #[must_use]
    pub const fn directory(self) -> &'static str {
        match self {
            Self::Prepared => "prepared",
            Self::Image => "images",
        }
    }

    #[must_use]
    pub const fn object_type(self) -> &'static str {
        match self {
            Self::Prepared => "prepared",
            Self::Image => "image",
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
    pub gen: u64,
    pub unit_key: String,
    pub heading_path: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub section_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub char_start: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub char_end: Option<u64>,
    pub text_hash: String,
    pub text: String,
}

impl ChunkObject {
    /// Recompute the path-independent semantic identity frozen in docs/03 §8.1.
    pub fn identity_hash(&self) -> Result<String> {
        self.validate()?;
        let mut value = Map::new();
        value.insert(
            "char_end".to_owned(),
            self.char_end.map_or(Value::Null, Value::from),
        );
        value.insert(
            "char_start".to_owned(),
            self.char_start.map_or(Value::Null, Value::from),
        );
        value.insert("gen".to_owned(), Value::from(self.gen));
        value.insert(
            "heading_path".to_owned(),
            serde_json::to_value(&self.heading_path)
                .map_err(|error| KcsError::schema(error.to_string()))?,
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
        match (self.char_start, self.char_end) {
            (Some(start), Some(end)) if start <= end => {}
            (None, None) => {}
            _ => {
                return Err(chunk_corrupt_error(
                    "chunk char_start/char_end must be an ordered pair",
                    None,
                ))
            }
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
    pub error: KcsError,
    pub consumed_bytes: u64,
}

#[derive(Debug, Clone)]
pub struct ObjectStore {
    kcs_dir: PathBuf,
}

impl ObjectStore {
    #[must_use]
    pub fn new(kcs_dir: impl Into<PathBuf>) -> Self {
        Self {
            kcs_dir: kcs_dir.into(),
        }
    }

    pub fn write_raw(&self, bytes: &[u8]) -> Result<String> {
        let hash = hash_bytes(bytes);
        self.write_object_bytes(ObjectKind::Raw, &hash, bytes)?;
        Ok(hash)
    }

    /// Repair one corrupt, single-representation raw CAS slot with verified
    /// working bytes. The destination is derived only from `expected_hash`; a
    /// canonical/legacy dual representation remains fail-closed. The caller must
    /// hold the scope store lock for the entire operation.
    pub fn repair_raw(&self, expected_hash: &str, bytes: &[u8]) -> Result<bool> {
        if !is_hash(expected_hash) || hash_bytes(bytes) != expected_hash {
            return Err(KcsError::invalid_usage(
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
        let paths = self.existing_object_paths(ObjectKind::Raw, expected_hash)?;
        if paths.is_empty() {
            self.write_object_bytes(ObjectKind::Raw, expected_hash, bytes)?;
            return Ok(true);
        }
        if paths.len() != 1 {
            // Never choose a winner when canonical and legacy physical state
            // coexist. Healthy duplicates are already complete; any disagreement
            // is corruption that requires operator intervention.
            verify_object_path_variants(&paths, ObjectKind::Raw, expected_hash, false)?;
            return Ok(false);
        }
        let path = &paths[0];
        if read_verified_object(path, ObjectKind::Raw, expected_hash, false).is_ok() {
            return Ok(false);
        }

        // Re-open through the hardened no-follow/single-link boundary and consume
        // the complete corrupt body before authorizing replacement. Unsafe links
        // and path swaps fail before any namespace mutation.
        let mut corrupt = open_regular_nofollow(path)?;
        let metadata = corrupt.metadata().kcs_io(path)?;
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
            let count = corrupt.read(&mut buffer).kcs_io(path)?;
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
            .ok_or_else(|| KcsError::io("CAS path has no parent", path.display().to_string()))?;
        let (temp_path, mut temp) = create_private_temp(parent)?;
        let result = (|| -> Result<()> {
            temp.write_all(bytes).kcs_io(&temp_path)?;
            temp.sync_all().kcs_io(&temp_path)?;
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
            fs::remove_file(&quarantine).kcs_io(&quarantine)?;
            if let Ok(directory) = File::open(parent) {
                let _ = directory.sync_all();
            }
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
            serde_json::to_value(chunk).map_err(|error| KcsError::schema(error.to_string()))?;
        let bytes = canonical_json_bytes(&value)?;
        if bytes.len() as u64 > MAX_CHUNK_OBJECT_BYTES {
            return Err(chunk_size_error(bytes.len() as u64));
        }
        self.ensure_chunk_parent(&hash)?;
        let existing = self.existing_chunk_paths(&hash)?;
        if !existing.is_empty() {
            for path in existing {
                verify_existing_bytes(&path, &hash, &bytes)?;
                read_chunk_path(&path, &hash)?;
            }
            return Ok(hash);
        }

        let path = self.chunk_path(&hash)?;
        let (temp_path, mut temp) = create_private_temp(
            path.parent()
                .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?,
        )?;
        let result = (|| -> Result<()> {
            temp.write_all(&bytes).kcs_io(&temp_path)?;
            temp.sync_all().kcs_io(&temp_path)?;
            drop(temp);
            publish_temp_object(&temp_path, &path, &hash, bytes.len() as u64, Some(&bytes))?;
            let published = self.existing_chunk_paths(&hash)?;
            if published.is_empty() {
                return Err(KcsError::not_found(&hash));
            }
            let mut first = None;
            for published_path in published {
                let (object, published_bytes) = read_chunk_path(&published_path, &hash)?;
                if let Some(expected) = &first {
                    if expected != &published_bytes {
                        return Err(chunk_corrupt_error(
                            "portable and legacy chunk objects disagree",
                            Some(&published_path),
                        ));
                    }
                } else {
                    first = Some(published_bytes);
                }
                if &object != chunk {
                    return Err(chunk_corrupt_error(
                        "published chunk object changed identity or text",
                        Some(&published_path),
                    ));
                }
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
            return Err(KcsError::invalid_usage("invalid chunk hash"));
        }
        if !self.validate_chunk_parent(hash)? {
            return Err(KcsError::not_found(hash));
        }
        let paths = self.existing_chunk_paths(hash)?;
        if paths.is_empty() {
            return Err(KcsError::not_found(hash));
        }
        let mut resolved = None::<(ChunkObject, Vec<u8>)>;
        let mut verified_bytes = 0_u64;
        for path in paths {
            let current = read_chunk_path(&path, hash)?;
            verified_bytes = verified_bytes.saturating_add(current.1.len() as u64);
            if let Some((expected_object, expected_bytes)) = &resolved {
                if expected_object != &current.0 || expected_bytes != &current.1 {
                    return Err(chunk_corrupt_error(
                        "portable and legacy chunk objects disagree",
                        Some(&path),
                    ));
                }
            } else {
                resolved = Some(current);
            }
        }
        resolved
            .map(|(object, _)| (object, verified_bytes))
            .ok_or_else(|| KcsError::not_found(hash))
    }

    pub fn read_chunk_accounted(
        &self,
        hash: &str,
    ) -> std::result::Result<(ChunkObject, u64), AccountedReadError> {
        let paths = (|| -> Result<Vec<PathBuf>> {
            if !is_hash(hash) {
                return Err(KcsError::invalid_usage("invalid chunk hash"));
            }
            if !self.validate_chunk_parent(hash)? {
                return Err(KcsError::not_found(hash));
            }
            let paths = self.existing_chunk_paths(hash)?;
            if paths.is_empty() {
                return Err(KcsError::not_found(hash));
            }
            Ok(paths)
        })()
        .map_err(|error| AccountedReadError {
            error,
            consumed_bytes: 0,
        })?;
        let mut resolved = None::<(ChunkObject, Vec<u8>)>;
        let mut consumed_bytes = 0_u64;
        for path in paths {
            let (result, consumed) = read_chunk_path_accounted(&path, hash);
            consumed_bytes = consumed_bytes.saturating_add(consumed);
            let current = result.map_err(|error| AccountedReadError {
                error,
                consumed_bytes,
            })?;
            if let Some((expected_object, expected_bytes)) = &resolved {
                if expected_object != &current.0 || expected_bytes != &current.1 {
                    return Err(AccountedReadError {
                        error: chunk_corrupt_error(
                            "portable and legacy chunk objects disagree",
                            Some(&path),
                        ),
                        consumed_bytes,
                    });
                }
            } else {
                resolved = Some(current);
            }
        }
        resolved
            .map(|(object, _)| (object, consumed_bytes))
            .ok_or_else(|| AccountedReadError {
                error: KcsError::not_found(hash),
                consumed_bytes,
            })
    }

    /// Stream-verify a referenced prepared/image content object without
    /// materializing its body.
    pub fn inspect_content_object(
        &self,
        kind: ContentObjectKind,
        hash: &str,
    ) -> Result<StoredContentObjectMetadata> {
        if !is_hash(hash) {
            return Err(KcsError::invalid_usage("invalid content object hash"));
        }
        if !self.validate_content_parent(kind, hash)? {
            return Err(KcsError::not_found(hash));
        }
        let paths = self.existing_content_paths(kind, hash)?;
        if paths.is_empty() {
            return Err(KcsError::not_found(hash));
        }
        let primary = paths.first().expect("checked non-empty");
        let size_bytes = verify_content_object_path(primary, kind, hash)?;
        let mut verified_bytes = size_bytes;
        for duplicate in &paths[1..] {
            let duplicate_size = verify_content_object_path(duplicate, kind, hash)?;
            if duplicate_size != size_bytes {
                return Err(corrupt_object_error(
                    duplicate,
                    "portable and legacy content objects disagree",
                    hash,
                    None,
                ));
            }
            verified_bytes = verified_bytes.saturating_add(duplicate_size);
        }
        Ok(StoredContentObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes: verified_bytes,
        })
    }

    pub fn inspect_content_accounted(
        &self,
        kind: ContentObjectKind,
        hash: &str,
    ) -> std::result::Result<StoredContentObjectMetadata, AccountedReadError> {
        let paths = (|| -> Result<Vec<PathBuf>> {
            if !is_hash(hash) {
                return Err(KcsError::invalid_usage("invalid content object hash"));
            }
            if !self.validate_content_parent(kind, hash)? {
                return Err(KcsError::not_found(hash));
            }
            let paths = self.existing_content_paths(kind, hash)?;
            if paths.is_empty() {
                return Err(KcsError::not_found(hash));
            }
            Ok(paths)
        })()
        .map_err(|error| AccountedReadError {
            error,
            consumed_bytes: 0,
        })?;
        let mut consumed_bytes = 0_u64;
        let mut primary_size = None;
        for path in paths {
            let (result, consumed) = verify_content_object_path_accounted(&path, kind, hash);
            consumed_bytes = consumed_bytes.saturating_add(consumed);
            let size = result.map_err(|error| AccountedReadError {
                error,
                consumed_bytes,
            })?;
            if primary_size.is_some_and(|expected| expected != size) {
                return Err(AccountedReadError {
                    error: corrupt_object_error(
                        &path,
                        "portable and legacy content objects disagree",
                        hash,
                        None,
                    ),
                    consumed_bytes,
                });
            }
            primary_size = Some(size);
        }
        Ok(StoredContentObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes: consumed_bytes,
        })
    }

    pub fn chunk_path(&self, hash: &str) -> Result<PathBuf> {
        fanout_path(self.kcs_dir.join("objects/chunks"), hash)
    }

    fn chunk_path_candidates(&self, hash: &str) -> Result<Vec<PathBuf>> {
        let canonical = self.chunk_path(hash)?;
        #[cfg(windows)]
        {
            Ok(vec![canonical])
        }
        #[cfg(not(windows))]
        {
            Ok(vec![
                canonical,
                legacy_fanout_path(self.kcs_dir.join("objects/chunks"), hash)?,
            ])
        }
    }

    fn existing_chunk_paths(&self, hash: &str) -> Result<Vec<PathBuf>> {
        let mut existing = Vec::new();
        for path in self.chunk_path_candidates(hash)? {
            match fs::symlink_metadata(&path) {
                Ok(_) => existing.push(path),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => {
                    return Err(KcsError::io(error.to_string(), path.display().to_string()))
                }
            }
        }
        Ok(existing)
    }

    fn content_path(&self, kind: ContentObjectKind, hash: &str) -> Result<PathBuf> {
        fanout_path(self.kcs_dir.join("objects").join(kind.directory()), hash)
    }

    fn content_path_candidates(&self, kind: ContentObjectKind, hash: &str) -> Result<Vec<PathBuf>> {
        let canonical = self.content_path(kind, hash)?;
        #[cfg(windows)]
        {
            Ok(vec![canonical])
        }
        #[cfg(not(windows))]
        {
            let base = self.kcs_dir.join("objects").join(kind.directory());
            Ok(vec![canonical, legacy_fanout_path(base, hash)?])
        }
    }

    fn existing_content_paths(&self, kind: ContentObjectKind, hash: &str) -> Result<Vec<PathBuf>> {
        let mut existing = Vec::new();
        for path in self.content_path_candidates(kind, hash)? {
            match fs::symlink_metadata(&path) {
                Ok(_) => existing.push(path),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => {
                    return Err(KcsError::io(error.to_string(), path.display().to_string()))
                }
            }
        }
        Ok(existing)
    }

    fn validate_content_parent(&self, kind: ContentObjectKind, hash: &str) -> Result<bool> {
        let digest = hash_path_component(hash)?;
        let objects = self.kcs_dir.join("objects");
        let kind_base = objects.join(kind.directory());
        let first = kind_base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        for directory in [&self.kcs_dir, &objects, &kind_base, &first, &second] {
            match fs::symlink_metadata(directory) {
                Ok(metadata)
                    if metadata.file_type().is_dir() && !metadata.file_type().is_symlink() => {}
                Ok(_) => return Err(non_regular_object_error(directory)),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
                Err(error) => {
                    return Err(KcsError::io(
                        error.to_string(),
                        directory.display().to_string(),
                    ))
                }
            }
        }
        Ok(true)
    }

    fn ensure_chunk_parent(&self, hash: &str) -> Result<()> {
        ensure_real_directory(&self.kcs_dir, false)?;
        ensure_real_directory(&self.kcs_dir.join("objects"), true)?;
        let base = self.kcs_dir.join("objects/chunks");
        ensure_real_directory(&base, true)?;
        let digest = hash_path_component(hash)?;
        let first = base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        ensure_real_directory(&first, true)?;
        ensure_real_directory(&second, true)
    }

    fn validate_chunk_parent(&self, hash: &str) -> Result<bool> {
        let digest = hash_path_component(hash)?;
        let objects = self.kcs_dir.join("objects");
        let base = objects.join("chunks");
        let first = base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        for directory in [&self.kcs_dir, &objects, &base, &first, &second] {
            match fs::symlink_metadata(directory) {
                Ok(metadata)
                    if metadata.file_type().is_dir() && !metadata.file_type().is_symlink() => {}
                Ok(_) => return Err(non_regular_object_error(directory)),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
                Err(error) => {
                    return Err(KcsError::io(
                        error.to_string(),
                        directory.display().to_string(),
                    ))
                }
            }
        }
        Ok(true)
    }

    pub fn write_object_bytes(&self, kind: ObjectKind, hash: &str, bytes: &[u8]) -> Result<()> {
        if bytes.len() as u64 > kind.max_bytes() {
            return Err(object_size_error(
                kind,
                kind.max_bytes(),
                bytes.len() as u64,
            ));
        }
        if hash_bytes(bytes) != hash {
            return Err(KcsError::invalid_usage(
                "CAS object hash does not match the supplied bytes",
            ));
        }
        self.ensure_object_parent(kind, hash)?;
        let existing = self.existing_object_paths(kind, hash)?;
        if !existing.is_empty() {
            for path in existing {
                verify_existing_bytes(&path, hash, bytes)?;
            }
            return Ok(());
        }

        let path = self.object_path(kind, hash)?;
        let (temp_path, mut temp) = create_private_temp(
            path.parent()
                .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?,
        )?;
        let result = (|| -> Result<()> {
            temp.write_all(bytes).kcs_io(&temp_path)?;
            temp.sync_all().kcs_io(&temp_path)?;
            drop(temp);
            publish_temp_object(&temp_path, &path, hash, bytes.len() as u64, Some(bytes))?;

            // A legacy writer can race the portable publication. Verify every
            // representation that exists before reporting success so a conflicting
            // prefixed leaf never becomes an ignored shadow object.
            let published = self.existing_object_paths(kind, hash)?;
            if published.is_empty() {
                return Err(KcsError::not_found(hash));
            }
            for published_path in published {
                verify_existing_bytes(&published_path, hash, bytes)?;
            }
            Ok(())
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
        let max_bytes = max_bytes.min(MAX_RAW_OBJECT_BYTES);
        let raw_base = self
            .kcs_dir
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
                let count = reader.read(&mut buffer[..read_cap]).kcs_io(&temp_path)?;
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
                temp.write_all(&buffer[..count]).kcs_io(&temp_path)?;
            }
            temp.sync_all().kcs_io(&temp_path)?;
            drop(temp);

            let hash = format!("sha256:{}", lower_hex(&hasher.finalize()));
            let path = self.object_path(ObjectKind::Raw, &hash)?;
            self.ensure_object_parent(ObjectKind::Raw, &hash)?;
            let existing = self.existing_object_paths(ObjectKind::Raw, &hash)?;
            if !existing.is_empty() {
                for existing_path in existing {
                    verify_existing_matches_file(&existing_path, &temp_path, &hash, total)?;
                }
                fs::remove_file(&temp_path).kcs_io(&temp_path)?;
                return Ok((hash, total));
            }

            publish_temp_object(&temp_path, &path, &hash, total, None)?;
            let published = self.existing_object_paths(ObjectKind::Raw, &hash)?;
            if published.is_empty() {
                return Err(KcsError::not_found(&hash));
            }
            verify_object_path_variants(&published, ObjectKind::Raw, &hash, false)?;
            Ok((hash, total))
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result
    }

    pub fn read_by_hash(&self, hash: &str) -> Result<StoredObject> {
        let (kind, paths) = self.locate_object(hash)?;
        let (_, bytes) = verify_object_path_variants(&paths, kind, hash, true)?;
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
            return Err(KcsError::invalid_usage("invalid raw hash"));
        }
        if !self.validate_object_parent(ObjectKind::Raw, hash)? {
            return Ok(false);
        }
        let paths = self.existing_object_paths(ObjectKind::Raw, hash)?;
        if paths.is_empty() {
            return Ok(false);
        }
        verify_object_path_variants(&paths, ObjectKind::Raw, hash, false)?;
        for path in paths {
            remove_verified_cas_path(&path, |candidate| {
                read_verified_object(candidate, ObjectKind::Raw, hash, false).map(|_| ())
            })?;
        }
        Ok(true)
    }

    /// Remove one semantic chunk object after identity/text verification.
    pub fn remove_chunk(&self, hash: &str) -> Result<bool> {
        if !is_hash(hash) {
            return Err(KcsError::invalid_usage("invalid chunk hash"));
        }
        if !self.validate_chunk_parent(hash)? {
            return Ok(false);
        }
        let paths = self.existing_chunk_paths(hash)?;
        if paths.is_empty() {
            return Ok(false);
        }
        // Verify all variants before the first destructive step.
        self.read_chunk(hash)?;
        for path in paths {
            remove_verified_cas_path(&path, |candidate| {
                read_chunk_path(candidate, hash).map(|_| ())
            })?;
        }
        Ok(true)
    }

    /// Verify every portable/legacy prepared or image representation, then
    /// physically remove it. Purge callers must first prove that no surviving
    /// normalized instance references the content hash. Missing is an idempotent
    /// `false`; malformed links, bytes, or duplicate representations fail closed
    /// before the first unlink.
    pub fn remove_content(&self, kind: ContentObjectKind, hash: &str) -> Result<bool> {
        if !is_hash(hash) {
            return Err(KcsError::invalid_usage("invalid content object hash"));
        }
        if !self.validate_content_parent(kind, hash)? {
            return Ok(false);
        }
        let paths = self.existing_content_paths(kind, hash)?;
        if paths.is_empty() {
            return Ok(false);
        }
        for path in &paths {
            verify_content_object_path(path, kind, hash)?;
        }
        for path in paths {
            remove_verified_cas_path(&path, |candidate| {
                verify_content_object_path(candidate, kind, hash).map(|_| ())
            })?;
        }
        Ok(true)
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
        if !is_hash(hash) {
            return Err(KcsError::invalid_usage("invalid hash"));
        }
        if !self.validate_object_parent(kind, hash)? {
            return Err(KcsError::not_found(hash));
        }
        let paths = self.existing_object_paths(kind, hash)?;
        if paths.is_empty() {
            return Err(KcsError::not_found(hash));
        }
        let primary = paths.first().expect("checked non-empty");
        let (primary_size, bytes) = read_verified_object(primary, kind, hash, true)?;
        let mut verified_bytes = primary_size;
        for duplicate in &paths[1..] {
            let (duplicate_size, _) = read_verified_object(duplicate, kind, hash, false)?;
            verified_bytes = verified_bytes.saturating_add(duplicate_size);
        }
        Ok((
            StoredObject {
                kind,
                hash: hash.to_owned(),
                bytes,
            },
            verified_bytes,
        ))
    }

    /// Verify and count an object through a fixed-size buffer. This is the
    /// metadata-only path used by raw `inspect`; it does not retain the body.
    pub fn inspect_by_hash(&self, hash: &str) -> Result<StoredObjectMetadata> {
        let (kind, paths) = self.locate_object(hash)?;
        let (size_bytes, _) = verify_object_path_variants(&paths, kind, hash, false)?;
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
            return Err(KcsError::invalid_usage("invalid hash"));
        }
        if !self.validate_object_parent(kind, hash)? {
            return Err(KcsError::not_found(hash));
        }
        let paths = self.existing_object_paths(kind, hash)?;
        if paths.is_empty() {
            return Err(KcsError::not_found(hash));
        }
        let (size_bytes, _) = verify_object_path_variants(&paths, kind, hash, false)?;
        Ok(StoredObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes,
        })
    }

    /// Metadata-only exact-kind verification that reports total physical bytes
    /// across matching canonical and legacy representations.
    pub fn inspect_object_physical(
        &self,
        kind: ObjectKind,
        hash: &str,
    ) -> Result<StoredObjectMetadata> {
        if !is_hash(hash) {
            return Err(KcsError::invalid_usage("invalid hash"));
        }
        if !self.validate_object_parent(kind, hash)? {
            return Err(KcsError::not_found(hash));
        }
        let paths = self.existing_object_paths(kind, hash)?;
        if paths.is_empty() {
            return Err(KcsError::not_found(hash));
        }
        let mut size_bytes = 0_u64;
        for path in paths {
            let (verified, _) = read_verified_object(&path, kind, hash, false)?;
            size_bytes = size_bytes.saturating_add(verified);
        }
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
        let result = (|| -> Result<Vec<PathBuf>> {
            if !is_hash(hash) {
                return Err(KcsError::invalid_usage("invalid hash"));
            }
            if !self.validate_object_parent(kind, hash)? {
                return Err(KcsError::not_found(hash));
            }
            let paths = self.existing_object_paths(kind, hash)?;
            if paths.is_empty() {
                return Err(KcsError::not_found(hash));
            }
            Ok(paths)
        })();
        let paths = result.map_err(|error| AccountedReadError {
            error,
            consumed_bytes: 0,
        })?;
        let mut consumed_bytes = 0_u64;
        for path in paths {
            let (result, consumed) = read_verified_object_accounted(&path, kind, hash, false);
            consumed_bytes = consumed_bytes.saturating_add(consumed);
            if let Err(error) = result {
                return Err(AccountedReadError {
                    error,
                    consumed_bytes,
                });
            }
        }
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
        let paths = (|| -> Result<Vec<PathBuf>> {
            if !is_hash(hash) {
                return Err(KcsError::invalid_usage("invalid hash"));
            }
            if !self.validate_object_parent(kind, hash)? {
                return Err(KcsError::not_found(hash));
            }
            let paths = self.existing_object_paths(kind, hash)?;
            if paths.is_empty() {
                return Err(KcsError::not_found(hash));
            }
            Ok(paths)
        })()
        .map_err(|error| AccountedReadError {
            error,
            consumed_bytes: 0,
        })?;
        let mut consumed_bytes = 0_u64;
        let mut bytes = Vec::new();
        for (index, path) in paths.iter().enumerate() {
            let (result, consumed) = read_verified_object_accounted(path, kind, hash, index == 0);
            consumed_bytes = consumed_bytes.saturating_add(consumed);
            match result {
                Ok((_, value)) if index == 0 => bytes = value,
                Ok(_) => {}
                Err(error) => {
                    return Err(AccountedReadError {
                        error,
                        consumed_bytes,
                    })
                }
            }
        }
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
            return Err(KcsError::invalid_usage("invalid hash"));
        }
        if !self.validate_object_parent(kind, hash)? {
            return Err(KcsError::not_found(hash));
        }
        let paths = self.existing_object_paths(kind, hash)?;
        let primary = paths.first().ok_or_else(|| KcsError::not_found(hash))?;
        let size_bytes = copy_verified_object(primary, kind, hash, writer)?;
        for duplicate in &paths[1..] {
            read_verified_object(duplicate, kind, hash, false)?;
        }
        Ok(StoredObjectMetadata {
            kind,
            hash: hash.to_owned(),
            size_bytes,
        })
    }

    pub fn object_path(&self, kind: ObjectKind, hash: &str) -> Result<PathBuf> {
        let base = self.kcs_dir.join("objects").join(kind.directory());
        fanout_path(base, hash)
    }

    fn locate_object(&self, hash: &str) -> Result<(ObjectKind, Vec<PathBuf>)> {
        if !is_hash(hash) {
            return Err(KcsError::invalid_usage("invalid hash"));
        }
        for kind in [ObjectKind::Tree, ObjectKind::Commit, ObjectKind::Raw] {
            if !self.validate_object_parent(kind, hash)? {
                continue;
            }
            let paths = self.existing_object_paths(kind, hash)?;
            if !paths.is_empty() {
                return Ok((kind, paths));
            }
        }
        Err(KcsError::not_found(hash))
    }

    fn object_path_candidates(&self, kind: ObjectKind, hash: &str) -> Result<Vec<PathBuf>> {
        let canonical = self.object_path(kind, hash)?;
        #[cfg(windows)]
        {
            Ok(vec![canonical])
        }
        #[cfg(not(windows))]
        {
            let base = self.kcs_dir.join("objects").join(kind.directory());
            Ok(vec![canonical, legacy_fanout_path(base, hash)?])
        }
    }

    fn existing_object_paths(&self, kind: ObjectKind, hash: &str) -> Result<Vec<PathBuf>> {
        let mut existing = Vec::new();
        for path in self.object_path_candidates(kind, hash)? {
            match fs::symlink_metadata(&path) {
                Ok(_) => existing.push(path),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(error) => {
                    return Err(KcsError::io(error.to_string(), path.display().to_string()))
                }
            }
        }
        Ok(existing)
    }

    fn ensure_kind_base(&self, kind: ObjectKind) -> Result<()> {
        ensure_real_directory(&self.kcs_dir, false)?;
        ensure_real_directory(&self.kcs_dir.join("objects"), true)?;
        ensure_real_directory(&self.kcs_dir.join("objects").join(kind.directory()), true)
    }

    fn ensure_object_parent(&self, kind: ObjectKind, hash: &str) -> Result<()> {
        self.ensure_kind_base(kind)?;
        let digest = hash_path_component(hash)?;
        let kind_base = self.kcs_dir.join("objects").join(kind.directory());
        let first = kind_base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        ensure_real_directory(&first, true)?;
        ensure_real_directory(&second, true)
    }

    fn validate_object_parent(&self, kind: ObjectKind, hash: &str) -> Result<bool> {
        let digest = hash_path_component(hash)?;
        let objects = self.kcs_dir.join("objects");
        let kind_base = objects.join(kind.directory());
        let first = kind_base.join(&digest[0..2]);
        let second = first.join(&digest[2..4]);
        for directory in [&self.kcs_dir, &objects, &kind_base, &first, &second] {
            match fs::symlink_metadata(directory) {
                Ok(metadata)
                    if metadata.file_type().is_dir() && !metadata.file_type().is_symlink() => {}
                Ok(_) => return Err(non_regular_object_error(directory)),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
                Err(error) => {
                    return Err(KcsError::io(
                        error.to_string(),
                        directory.display().to_string(),
                    ))
                }
            }
        }
        Ok(true)
    }
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
        let metadata = file.metadata().kcs_io(path)?;
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
            let count = file.read(&mut buffer[..read_cap]).kcs_io(path)?;
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
        let metadata = file.metadata().kcs_io(path)?;
        let limit = MAX_RAW_OBJECT_BYTES;
        if metadata.len() > limit {
            return Err(KcsError::new(
                "KCS-E-STORE-OBJECT-OVERSIZED-001",
                "content object exceeds its byte limit",
                serde_json::json!({
                    "object_type": kind.object_type(),
                    "max_bytes": limit,
                    "actual_bytes": metadata.len(),
                }),
                crate::ExitCode::PermanentFailure,
            ));
        }
        let mut hasher = Sha256::new();
        let mut buffer = [0_u8; CAS_STREAM_BUFFER_BYTES];
        loop {
            let read_cap = limit
                .saturating_sub(consumed)
                .saturating_add(1)
                .min(buffer.len() as u64) as usize;
            let count = file.read(&mut buffer[..read_cap]).kcs_io(path)?;
            if count == 0 {
                break;
            }
            consumed = consumed.saturating_add(count as u64);
            if consumed > limit {
                return Err(KcsError::new(
                    "KCS-E-STORE-OBJECT-OVERSIZED-001",
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

fn copy_verified_object<W: Write>(
    path: &Path,
    kind: ObjectKind,
    expected_hash: &str,
    writer: &mut W,
) -> Result<u64> {
    let mut file = open_regular_nofollow(path)?;
    let metadata = file.metadata().kcs_io(path)?;
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
        let count = file.read(&mut buffer[..read_cap]).kcs_io(path)?;
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
            .map_err(|error| KcsError::io(error.to_string(), "CAS stream target"))?;
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

fn verify_object_path_variants(
    paths: &[PathBuf],
    kind: ObjectKind,
    expected_hash: &str,
    materialize: bool,
) -> Result<(u64, Vec<u8>)> {
    let primary = paths
        .first()
        .ok_or_else(|| KcsError::not_found(expected_hash))?;
    let (size_bytes, bytes) = read_verified_object(primary, kind, expected_hash, materialize)?;
    for duplicate in &paths[1..] {
        read_verified_object(duplicate, kind, expected_hash, false)?;
    }
    Ok((size_bytes, bytes))
}

fn verify_existing_bytes(path: &Path, expected_hash: &str, expected: &[u8]) -> Result<()> {
    let mut file = open_regular_nofollow(path)?;
    let metadata = file.metadata().kcs_io(path)?;
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
        let count = file.read(&mut buffer).kcs_io(path)?;
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
            fs::remove_file(temp_path).kcs_io(temp_path)?;
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
        Err(error) => Err(KcsError::io(
            error.to_string(),
            destination.display().to_string(),
        )),
    }
}

fn create_repair_quarantine(path: &Path, opened: &File) -> Result<PathBuf> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("CAS path has no parent", path.display().to_string()))?;
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
                let linked = options.open(&candidate).kcs_io(&candidate)?;
                if !same_open_file(opened, &linked)? {
                    let _ = fs::remove_file(&candidate);
                    return Err(non_regular_object_error(path));
                }
                return Ok(candidate);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(KcsError::io(error.to_string(), path.display().to_string())),
        }
    }
    Err(KcsError::io(
        "could not allocate raw repair quarantine",
        path.display().to_string(),
    ))
}

#[cfg(unix)]
fn same_open_file(left: &File, right: &File) -> Result<bool> {
    Ok(same_file_identity(
        &left
            .metadata()
            .map_err(|error| KcsError::io(error.to_string(), "raw repair source"))?,
        &right
            .metadata()
            .map_err(|error| KcsError::io(error.to_string(), "raw repair quarantine"))?,
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
        .map_err(|error| KcsError::io(error.to_string(), "raw repair source"))?
        .len()
        == right
            .metadata()
            .map_err(|error| KcsError::io(error.to_string(), "raw repair quarantine"))?
            .len())
}

#[cfg(not(windows))]
fn replace_file(source: &Path, destination: &Path) -> Result<()> {
    fs::rename(source, destination)
        .map_err(|error| KcsError::io(error.to_string(), destination.display().to_string()))
}

#[cfg(windows)]
fn replace_file(source: &Path, destination: &Path) -> Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
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
        Err(KcsError::io(
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
        .ok_or_else(|| KcsError::io("CAS path has no parent", path.display().to_string()))?;
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
            Err(error) => return Err(KcsError::io(error.to_string(), path.display().to_string())),
        }
    }
    let quarantine = quarantine.ok_or_else(|| {
        KcsError::io(
            "could not allocate CAS removal quarantine",
            path.display().to_string(),
        )
    })?;
    if let Err(error) = fs::remove_file(path) {
        let _ = fs::remove_file(&quarantine);
        return Err(KcsError::io(error.to_string(), path.display().to_string()));
    }
    // Leave quarantined bytes in place on failure for retry/forensics. The
    // logical leaf is already absent and the purge barrier keeps reads closed.
    verify(&quarantine)?;
    fs::remove_file(&quarantine).kcs_io(&quarantine)?;
    if let Ok(directory) = File::open(parent) {
        let _ = directory.sync_all();
    }
    Ok(())
}

fn verify_existing_matches_file(
    destination: &Path,
    source: &Path,
    expected_hash: &str,
    expected_len: u64,
) -> Result<()> {
    let mut existing = open_regular_nofollow(destination)?;
    if existing.metadata().kcs_io(destination)?.len() != expected_len {
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
        let existing_count = existing.read(&mut existing_buffer).kcs_io(destination)?;
        let source_count = source_file.read(&mut source_buffer).kcs_io(source)?;
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
        let metadata = file.metadata().kcs_io(path)?;
        if metadata.len() > MAX_CHUNK_OBJECT_BYTES {
            return Err(chunk_size_error(metadata.len()));
        }
        let mut bytes = Vec::with_capacity(metadata.len() as usize);
        file.take(MAX_CHUNK_OBJECT_BYTES.saturating_add(1))
            .read_to_end(&mut bytes)
            .kcs_io(path)?;
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
            &serde_json::to_value(&object).map_err(|error| KcsError::schema(error.to_string()))?,
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
            Err(error) => return Err(KcsError::io(error.to_string(), path.display().to_string())),
        }
    }
    Err(KcsError::io(
        "could not allocate a unique CAS temporary file",
        parent.display().to_string(),
    ))
}

fn ensure_real_directory(path: &Path, create: bool) -> Result<()> {
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
                Err(create_error) => Err(KcsError::io(
                    create_error.to_string(),
                    path.display().to_string(),
                )),
            }
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            Err(KcsError::not_found(path.display().to_string()))
        }
        Err(error) => Err(KcsError::io(error.to_string(), path.display().to_string())),
    }
}

/// Open a real, single-link regular file without following its final symlink
/// or reparse point, and bind the returned handle to the verified path entry.
pub fn open_regular_nofollow(path: &Path) -> Result<File> {
    let before = fs::symlink_metadata(path).kcs_io(path)?;
    if !before.file_type().is_file() || before.file_type().is_symlink() {
        return Err(non_regular_object_error(path));
    }

    let mut options = OpenOptions::new();
    options.read(true);
    configure_no_follow(&mut options);
    let file = options.open(path).kcs_io(path)?;
    let opened = file.metadata().kcs_io(path)?;
    let after = fs::symlink_metadata(path).kcs_io(path)?;
    #[cfg(windows)]
    let same_identity = {
        let mut verification_options = OpenOptions::new();
        verification_options.read(true);
        configure_no_follow(&mut verification_options);
        let verification = verification_options.open(path).kcs_io(path)?;
        verification.metadata().kcs_io(path)?.is_file()
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
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION,
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
) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-CORRUPT-001",
        message,
        serde_json::json!({
            "path": path,
            "expected": expected,
            "actual": actual,
        }),
        crate::ExitCode::PermanentFailure,
    )
}

fn chunk_corrupt_error(message: &str, path: Option<&Path>) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-CORRUPT-001",
        message,
        serde_json::json!({ "path": path }),
        crate::ExitCode::PermanentFailure,
    )
}

fn chunk_size_error(actual: u64) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-OBJECT-OVERSIZED-001",
        "chunk object exceeds its byte limit",
        serde_json::json!({
            "object_type": "chunk",
            "max_bytes": MAX_CHUNK_OBJECT_BYTES,
            "actual_bytes": actual,
        }),
        crate::ExitCode::PermanentFailure,
    )
}

fn non_regular_object_error(path: &Path) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-CORRUPT-001",
        "CAS path is not a real regular file or directory",
        serde_json::json!({ "path": path }),
        crate::ExitCode::PermanentFailure,
    )
}

fn object_size_error(kind: ObjectKind, limit: u64, actual: u64) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-OBJECT-OVERSIZED-001",
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
    serde_jcs::to_vec(value).map_err(|err| KcsError::schema(err.to_string()))
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
        return Err(KcsError::invalid_usage("invalid hash"));
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
    let metadata = file.metadata().kcs_io(path)?;
    if metadata.len() > max_bytes {
        return Err(KcsError::new(
            "KCS-E-STORE-OBJECT-OVERSIZED-001",
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
        .kcs_io(path)?;
    if bytes.len() as u64 > max_bytes {
        return Err(KcsError::new(
            "KCS-E-STORE-OBJECT-OVERSIZED-001",
            "metadata record exceeds its byte limit",
            serde_json::json!({ "path": path, "max_bytes": max_bytes }),
            crate::ExitCode::PermanentFailure,
        ));
    }
    Ok(bytes)
}

#[cfg(not(windows))]
fn legacy_fanout_path(base: impl AsRef<Path>, hash: &str) -> Result<PathBuf> {
    let digest = hash_path_component(hash)?;
    Ok(base
        .as_ref()
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(hash))
}

pub(crate) fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kcs_io(parent)?;

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
        let mut file = File::create(&temp).kcs_io(&temp)?;
        file.write_all(bytes).kcs_io(&temp)?;
        file.sync_all().kcs_io(&temp)?;
        drop(file);
        fs::rename(&temp, path).kcs_io(path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

pub(crate) fn atomic_overwrite(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kcs_io(parent)?;
    let temp = parent.join(format!(".tmp-{}-{}", std::process::id(), unix_nanos()));
    // R9-8: see `atomic_write` — remove the temp on any failure so a torn write
    // does not leave an orphan `.tmp-*` behind.
    let result = (|| -> Result<()> {
        let mut file = File::create(&temp).kcs_io(&temp)?;
        file.write_all(bytes).kcs_io(&temp)?;
        file.sync_all().kcs_io(&temp)?;
        drop(file);
        fs::rename(&temp, path).kcs_io(path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

pub(crate) fn append_jsonl(path: &Path, value: &Value) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kcs_io(parent)?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .kcs_io(path)?;
    // Serialize the whole record (line + newline) into one buffer and emit it in a
    // single `write_all` on the O_APPEND handle. A multi-write sequence
    // (`to_writer` then a separate newline write) can interleave byte-wise with a
    // concurrent process's record even under O_APPEND, corrupting the JSONL
    // (M1(b)). One `write_all` of the framed record is atomic per append.
    let mut line = serde_json::to_string(value)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    line.push('\n');
    file.write_all(line.as_bytes()).kcs_io(path)?;
    Ok(())
}

fn lower_hex(bytes: &[u8]) -> String {
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
        let kcs_dir = dir.path().join(".kcs");
        fs::create_dir(&kcs_dir).unwrap();
        let store = ObjectStore::new(kcs_dir);
        (dir, store)
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
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
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
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
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
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
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
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
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
        assert_eq!(error.error_code(), "KCS-E-STORE-OBJECT-OVERSIZED-001");
        let raw_base = store.kcs_dir.join("objects/raw");
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
        assert_eq!(error.error_code(), "KCS-E-STORE-OBJECT-OVERSIZED-001");
    }

    #[test]
    fn cand_046_digest_mismatch_still_reports_store_corruption() {
        let (_dir, store) = object_store();
        let hash = hash_bytes(b"expected");
        store.ensure_object_parent(ObjectKind::Raw, &hash).unwrap();
        let path = store.object_path(ObjectKind::Raw, &hash).unwrap();
        fs::write(&path, b"different").unwrap();

        let error = store.inspect_by_hash(&hash).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
    }

    #[cfg(not(windows))]
    #[test]
    fn legacy_prefixed_leaf_remains_readable_and_idempotent() {
        let (_dir, store) = object_store();
        let expected = b"legacy payload";
        let hash = hash_bytes(expected);
        store.ensure_object_parent(ObjectKind::Raw, &hash).unwrap();
        let candidates = store
            .object_path_candidates(ObjectKind::Raw, &hash)
            .unwrap();
        let canonical = &candidates[0];
        let legacy = &candidates[1];
        fs::write(legacy, expected).unwrap();

        let read = store.read_by_hash(&hash).unwrap();
        assert_eq!(read.bytes, expected);
        let inspected = store.inspect_by_hash(&hash).unwrap();
        assert_eq!(inspected.size_bytes, expected.len() as u64);

        assert_eq!(store.write_raw(expected).unwrap(), hash);
        let (streamed_hash, streamed_size) = store
            .write_raw_reader(&mut Cursor::new(expected), expected.len() as u64)
            .unwrap();
        assert_eq!(streamed_hash, hash);
        assert_eq!(streamed_size, expected.len() as u64);
        assert!(!canonical.exists());
        assert_eq!(fs::read(legacy).unwrap(), expected);
    }

    #[cfg(not(windows))]
    #[test]
    fn legacy_prefixed_leaves_resolve_for_every_object_kind() {
        let (_dir, store) = object_store();
        let cases: [(ObjectKind, &[u8]); 3] = [
            (ObjectKind::Raw, b"legacy raw"),
            (ObjectKind::Tree, b"legacy tree"),
            (ObjectKind::Commit, b"legacy commit"),
        ];

        for (kind, expected) in cases {
            let hash = hash_bytes(expected);
            store.ensure_object_parent(kind, &hash).unwrap();
            let candidates = store.object_path_candidates(kind, &hash).unwrap();
            fs::write(&candidates[1], expected).unwrap();

            let read = store.read_by_hash(&hash).unwrap();
            assert_eq!(read.kind, kind);
            assert_eq!(read.bytes, expected);
            store.write_object_bytes(kind, &hash, expected).unwrap();
            assert!(!candidates[0].exists());
        }
    }

    #[cfg(not(windows))]
    #[test]
    fn matching_portable_and_legacy_leaves_are_accepted() {
        let (_dir, store) = object_store();
        let expected = b"duplicate payload";
        let hash = hash_bytes(expected);
        store.ensure_object_parent(ObjectKind::Raw, &hash).unwrap();
        let candidates = store
            .object_path_candidates(ObjectKind::Raw, &hash)
            .unwrap();
        fs::write(&candidates[0], expected).unwrap();
        fs::write(&candidates[1], expected).unwrap();

        assert_eq!(store.read_by_hash(&hash).unwrap().bytes, expected);
        assert_eq!(
            store.inspect_by_hash(&hash).unwrap().size_bytes,
            expected.len() as u64
        );
        store.write_raw(expected).unwrap();
        store
            .write_raw_reader(&mut Cursor::new(expected), expected.len() as u64)
            .unwrap();
    }

    #[cfg(not(windows))]
    #[test]
    fn conflicting_portable_and_legacy_leaves_fail_closed() {
        let (_dir, store) = object_store();
        let expected = b"expected";
        let hash = hash_bytes(expected);
        store.ensure_object_parent(ObjectKind::Raw, &hash).unwrap();
        let candidates = store
            .object_path_candidates(ObjectKind::Raw, &hash)
            .unwrap();
        fs::write(&candidates[0], expected).unwrap();
        fs::write(&candidates[1], b"poisoned").unwrap();

        for error in [
            store.read_by_hash(&hash).unwrap_err(),
            store.inspect_by_hash(&hash).unwrap_err(),
            store.write_raw(expected).unwrap_err(),
            store
                .write_raw_reader(&mut Cursor::new(expected), expected.len() as u64)
                .unwrap_err(),
        ] {
            assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
        }
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

    #[cfg(not(windows))]
    #[test]
    fn purge_remove_raw_deletes_matching_portable_and_legacy_variants() {
        let (_dir, store) = object_store();
        let bytes = b"matching raw variants";
        let hash = store.write_raw(bytes).unwrap();
        let candidates = store
            .object_path_candidates(ObjectKind::Raw, &hash)
            .unwrap();
        fs::write(&candidates[1], bytes).unwrap();
        assert!(store.remove_raw(&hash).unwrap());
        assert!(candidates.iter().all(|path| !path.exists()));
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
            "KCS-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&canonical).unwrap(), bytes);
        assert_eq!(fs::read(&outside).unwrap(), bytes);
    }

    fn chunk_object(text: &str) -> ChunkObject {
        ChunkObject {
            spec_version: 1,
            raw_hash: format!("sha256:{}", "a".repeat(64)),
            tool_profile_hash: format!("sha256:{}", "b".repeat(64)),
            gen: 3,
            unit_key: "page:12".to_owned(),
            heading_path: vec!["Auth".to_owned()],
            section_id: Some("auth".to_owned()),
            char_start: Some(0),
            char_end: Some(text.chars().count() as u64),
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
        assert!(!fs::read(store.chunk_path(&expected).unwrap())
            .unwrap()
            .windows(b"chunk_hash".len())
            .any(|window| window == b"chunk_hash"));
    }

    #[cfg(not(windows))]
    #[test]
    fn ct4_fsck_byte_counts_include_dual_chunk_and_content_representations() {
        let (_dir, store) = object_store();
        let chunk = chunk_object("dual representation");
        let chunk_hash = store.write_chunk(&chunk).unwrap();
        let chunk_paths = store.chunk_path_candidates(&chunk_hash).unwrap();
        let chunk_bytes = fs::read(&chunk_paths[0]).unwrap();
        fs::write(&chunk_paths[1], &chunk_bytes).unwrap();
        assert_eq!(
            store.read_chunk_with_size(&chunk_hash).unwrap().1,
            (chunk_bytes.len() * 2) as u64
        );

        let image_bytes = b"image-object";
        let image_hash = hash_bytes(image_bytes);
        let image_paths = store
            .content_path_candidates(ContentObjectKind::Image, &image_hash)
            .unwrap();
        fs::create_dir_all(image_paths[0].parent().unwrap()).unwrap();
        fs::write(&image_paths[0], image_bytes).unwrap();
        fs::write(&image_paths[1], image_bytes).unwrap();
        assert_eq!(
            store
                .inspect_content_object(ContentObjectKind::Image, &image_hash)
                .unwrap()
                .size_bytes,
            (image_bytes.len() * 2) as u64
        );
        fs::write(&image_paths[1], b"poisoned-img").unwrap();
        let accounted = store
            .inspect_content_accounted(ContentObjectKind::Image, &image_hash)
            .unwrap_err();
        assert_eq!(
            accounted.consumed_bytes,
            (image_bytes.len() + b"poisoned-img".len()) as u64
        );
        assert_eq!(
            store
                .inspect_content_object(ContentObjectKind::Image, &image_hash)
                .unwrap_err()
                .error_code(),
            "KCS-E-STORE-CORRUPT-001"
        );
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
        assert_eq!(failure.error.error_code(), "KCS-E-STORE-CORRUPT-001");
        assert_eq!(failure.consumed_bytes, poisoned.len() as u64);
    }

    #[cfg(not(windows))]
    #[test]
    fn ct4_fsck_repair_raw_keeps_dual_disagreement_fail_closed() {
        let (_dir, store) = object_store();
        let expected = b"dual repair bytes";
        let hash = store.write_raw(expected).unwrap();
        let paths = store
            .object_path_candidates(ObjectKind::Raw, &hash)
            .unwrap();
        fs::write(&paths[1], expected).unwrap();
        fs::write(&paths[0], b"corrupt canonical").unwrap();

        assert_eq!(
            store.repair_raw(&hash, expected).unwrap_err().error_code(),
            "KCS-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&paths[0]).unwrap(), b"corrupt canonical");
        assert_eq!(fs::read(&paths[1]).unwrap(), expected);
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
            "KCS-E-STORE-CORRUPT-001"
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
            "KCS-E-STORE-CORRUPT-001"
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

    #[test]
    fn purge_remove_content_verifies_bytes_and_is_idempotent() {
        let (_dir, store) = object_store();
        let bytes = b"purge image content";
        let hash = hash_bytes(bytes);
        let path = store.content_path(ContentObjectKind::Image, &hash).unwrap();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, bytes).unwrap();
        assert!(store
            .remove_content(ContentObjectKind::Image, &hash)
            .unwrap());
        assert!(!path.exists());
        assert!(!store
            .remove_content(ContentObjectKind::Image, &hash)
            .unwrap());
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
            "KCS-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&path).unwrap(), bytes);
        assert_eq!(fs::read(&outside).unwrap(), bytes);
    }
}
