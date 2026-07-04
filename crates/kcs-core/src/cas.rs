//! Content-addressed storage primitives.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::error::{IoResultExt, KcsError, Result};

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
}

#[derive(Debug, Clone)]
pub struct StoredObject {
    pub kind: ObjectKind,
    pub hash: String,
    pub bytes: Vec<u8>,
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

    pub fn write_json(&self, kind: ObjectKind, value: &Value) -> Result<(String, Vec<u8>)> {
        let bytes = canonical_json_bytes(value)?;
        let hash = hash_bytes(&bytes);
        self.write_object_bytes(kind, &hash, &bytes)?;
        Ok((hash, bytes))
    }

    pub fn write_object_bytes(&self, kind: ObjectKind, hash: &str, bytes: &[u8]) -> Result<()> {
        let path = self.object_path(kind, hash)?;
        atomic_write(&path, bytes)
    }

    pub fn read_by_hash(&self, hash: &str) -> Result<StoredObject> {
        if !is_hash(hash) {
            return Err(KcsError::invalid_usage("invalid hash"));
        }

        for kind in [ObjectKind::Tree, ObjectKind::Commit, ObjectKind::Raw] {
            let path = self.object_path(kind, hash)?;
            if path.exists() {
                let bytes = fs::read(&path).kcs_io(&path)?;
                let actual = hash_bytes(&bytes);
                if actual != hash {
                    return Err(KcsError::new(
                        "KCS-E-STORE-CORRUPT-001",
                        "CAS object hash mismatch",
                        serde_json::json!({ "path": path, "expected": hash, "actual": actual }),
                        crate::ExitCode::PermanentFailure,
                    ));
                }
                return Ok(StoredObject {
                    kind,
                    hash: hash.to_owned(),
                    bytes,
                });
            }
        }

        Err(KcsError::not_found(hash))
    }

    pub fn object_path(&self, kind: ObjectKind, hash: &str) -> Result<PathBuf> {
        let base = self.kcs_dir.join("objects").join(kind.directory());
        fanout_path(base, hash)
    }
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

pub fn fanout_path(base: impl AsRef<Path>, hash: &str) -> Result<PathBuf> {
    if !is_hash(hash) {
        return Err(KcsError::invalid_usage("invalid hash"));
    }

    let digest = &hash["sha256:".len()..];
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
    {
        let mut file = File::create(&temp).kcs_io(&temp)?;
        file.write_all(bytes).kcs_io(&temp)?;
        file.sync_all().kcs_io(&temp)?;
    }
    fs::rename(&temp, path).kcs_io(path)?;
    Ok(())
}

pub(crate) fn atomic_overwrite(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kcs_io(parent)?;
    let temp = parent.join(format!(".tmp-{}-{}", std::process::id(), unix_nanos()));
    {
        let mut file = File::create(&temp).kcs_io(&temp)?;
        file.write_all(bytes).kcs_io(&temp)?;
        file.sync_all().kcs_io(&temp)?;
    }
    fs::rename(&temp, path).kcs_io(path)?;
    Ok(())
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
