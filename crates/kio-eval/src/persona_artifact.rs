//! Strict, create-only publication and consumption of persona artifacts.
//!
//! This module deliberately retains the directory descriptor used to bind an
//! artifact.  Public paths are rechecked as diagnostics only; all file I/O is
//! descriptor-relative and no-follow.

use cap_primitives::{ambient_authority, fs as cap_fs};
use kio_core::cas::hash_bytes;
use std::{
    fs,
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};
use thiserror::Error;

const TEMP_PREFIX: &str = ".kio-persona-artifact-";
const MAX_PATH_COMPONENTS: usize = 64;
const MAX_PATH_COMPONENT_BYTES: usize = 255;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Error)]
pub enum PersonaArtifactError {
    #[error("unsafe persona artifact: {0}")]
    Unsafe(String),
    #[error("persona artifact I/O: {0}")]
    Io(#[from] std::io::Error),
    #[error("persona artifact publication is indeterminate: {0}")]
    Indeterminate(String),
    #[error("persona artifact output already exists: {0}")]
    AlreadyExists(PathBuf),
}

#[derive(Debug)]
struct BoundParent {
    handle: fs::File,
    identity: cap_fs::Metadata,
    public: PathBuf,
    leaf: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Observation {
    identity: FileIdentity,
    len: u64,
    hash: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct FileIdentity {
    #[cfg(unix)]
    dev: u64,
    #[cfg(unix)]
    ino: u64,
    #[cfg(windows)]
    volume: u32,
    #[cfg(windows)]
    index: u64,
}

/// Read a bounded, single-link UTF-8 regular artifact through a retained,
/// no-follow path walk.  Inputs must be absolute and lexically normalized.
pub fn read_strict(path: &Path, maximum: usize) -> Result<Vec<u8>, PersonaArtifactError> {
    let parent = bind_parent(path)?;
    recheck_parent(&parent)?;
    let (bytes, _) = observe_regular(&parent.handle, &parent.leaf, maximum, path)?;
    recheck_parent(&parent)?;
    Ok(bytes)
}

/// Publish canonical bytes once.  The destination is never overwritten and
/// success is returned only after an exact descriptor-bound readback.
pub fn publish_create_only(
    path: &Path,
    bytes: &[u8],
    maximum: usize,
) -> Result<PathBuf, PersonaArtifactError> {
    if bytes.len() > maximum {
        return unsafe_state("artifact exceeds byte limit");
    }
    let parent = bind_parent(path)?;
    recheck_parent(&parent)?;
    absent(&parent.handle, &parent.leaf)?;

    let temp_name = temporary_name(&parent.leaf)?;
    let mut temp = TempArtifact::create(&parent, temp_name)?;
    temp.file.write_all(bytes)?;
    temp.file.sync_all()?;
    let (_, staged) = observe_regular(&parent.handle, &temp.name, maximum, path)?;
    if staged.len != bytes.len() as u64 || staged.hash != hash_bytes(bytes) {
        return unsafe_state("staged artifact differs from requested bytes");
    }
    recheck_parent(&parent)?;
    crate::scale_fixture::rename_noreplace(
        &parent.handle,
        &temp.name,
        &parent.handle,
        &parent.leaf,
    )
    .map_err(|error| {
        match cap_fs::stat(
            &parent.handle,
            Path::new(&parent.leaf),
            cap_fs::FollowSymlinks::No,
        ) {
            Ok(_) => PersonaArtifactError::AlreadyExists(parent.public.join(&parent.leaf)),
            Err(check) if check.kind() == std::io::ErrorKind::NotFound => {
                PersonaArtifactError::Indeterminate(error.to_string())
            }
            Err(_) => PersonaArtifactError::Indeterminate(error.to_string()),
        }
    })?;
    temp.published = true;

    let verification = (|| {
        sync_parent(&parent)?;
        let (readback, published) = observe_regular(&parent.handle, &parent.leaf, maximum, path)?;
        if published != staged || readback != bytes {
            return unsafe_state("published artifact differs from staged artifact");
        }
        recheck_parent(&parent)?;
        let (again, repeated) = observe_regular(&parent.handle, &parent.leaf, maximum, path)?;
        if repeated != published || again != readback {
            return unsafe_state("published artifact changed after readback");
        }
        Ok(parent.public.join(&parent.leaf))
    })();
    verification.map_err(|error| PersonaArtifactError::Indeterminate(error.to_string()))
}

#[derive(Debug)]
struct TempArtifact {
    parent: fs::File,
    name: String,
    identity: cap_fs::Metadata,
    file: fs::File,
    published: bool,
}

impl TempArtifact {
    fn create(parent: &BoundParent, name: String) -> Result<Self, PersonaArtifactError> {
        let mut options = cap_fs::OpenOptions::new();
        options.write(true).create_new(true);
        let file = cap_fs::open(&parent.handle, Path::new(&name), &options)?;
        let identity = cap_fs::Metadata::from_file(&file)?;
        if !regular(&identity, usize::MAX) {
            return unsafe_state("temporary artifact is not a single-link regular file");
        }
        Ok(Self {
            parent: parent.handle.try_clone()?,
            name,
            identity,
            file,
            published: false,
        })
    }
}

impl Drop for TempArtifact {
    fn drop(&mut self) {
        if self.published {
            return;
        }
        let Ok(current) = cap_fs::stat(
            &self.parent,
            Path::new(&self.name),
            cap_fs::FollowSymlinks::No,
        ) else {
            return;
        };
        if regular(&current, usize::MAX) && same(&current, &self.identity) {
            let _ = cap_fs::remove_file(&self.parent, Path::new(&self.name));
        }
    }
}

fn bind_parent(path: &Path) -> Result<BoundParent, PersonaArtifactError> {
    if !path.is_absolute()
        || path.as_os_str().is_empty()
        || path
            .components()
            .any(|component| matches!(component, Component::CurDir | Component::ParentDir))
    {
        return unsafe_state("path must be absolute and lexically normalized");
    }
    #[cfg(not(windows))]
    if path
        .components()
        .any(|component| matches!(component, Component::Prefix(_)))
    {
        return unsafe_state("path must be absolute and lexically normalized");
    }
    let components = path.components().count();
    if components > MAX_PATH_COMPONENTS
        || path.components().any(|component| match component {
            Component::Normal(part) => part.len() > MAX_PATH_COMPONENT_BYTES,
            _ => false,
        })
    {
        return unsafe_state("path exceeds component bounds");
    }
    let path = normalize_alias(path)?;
    let leaf = path
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| safe_leaf(name))
        .ok_or_else(|| PersonaArtifactError::Unsafe("path has an unsafe final component".into()))?
        .to_owned();
    let public = path
        .parent()
        .ok_or_else(|| PersonaArtifactError::Unsafe("path has no parent directory".into()))?
        .to_owned();
    let mut components = public.components().peekable();
    let mut root = PathBuf::new();
    #[cfg(windows)]
    if let Some(Component::Prefix(prefix)) = components.peek().copied() {
        if !matches!(prefix.kind(), std::path::Prefix::Disk(_)) {
            return unsafe_state("path must use an ordinary drive prefix");
        }
        root.push(prefix.as_os_str());
        components.next();
    }
    if !matches!(components.next(), Some(Component::RootDir)) {
        return unsafe_state("path must have an absolute root");
    }
    root.push(std::path::MAIN_SEPARATOR_STR);
    let mut handle = cap_fs::open_ambient_dir(&root, ambient_authority())?;
    for component in components {
        let Component::Normal(part) = component else {
            return unsafe_state("path must be lexically normalized");
        };
        handle = cap_fs::open_dir_nofollow(&handle, Path::new(part))?;
        let metadata = cap_fs::Metadata::from_file(&handle)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return unsafe_state("parent component is not a real directory");
        }
    }
    let identity = cap_fs::Metadata::from_file(&handle)?;
    if !identity.is_dir() || identity.file_type().is_symlink() {
        return unsafe_state("artifact parent is not a real directory");
    }
    Ok(BoundParent {
        handle,
        identity,
        public,
        leaf,
    })
}

fn recheck_parent(parent: &BoundParent) -> Result<(), PersonaArtifactError> {
    let retained = cap_fs::Metadata::from_file(&parent.handle)?;
    let public = fs::symlink_metadata(&parent.public)?;
    #[cfg(unix)]
    let public_identity_matches = same_std(&parent.identity, &public);
    #[cfg(windows)]
    let public_identity_matches = matches!(
        (
            kio_core::cas::windows_directory_handle_identity(&parent.handle),
            kio_core::cas::windows_real_directory_identity(&parent.public)?,
        ),
        (Some(handle), Some(path)) if handle == path
    );
    #[cfg(not(any(unix, windows)))]
    let public_identity_matches = false;
    if !retained.is_dir()
        || retained.file_type().is_symlink()
        || public.file_type().is_symlink()
        || !public.is_dir()
        || !same(&parent.identity, &retained)
        || !public_identity_matches
    {
        return unsafe_state("artifact parent identity changed");
    }
    Ok(())
}

fn absent(parent: &fs::File, leaf: &str) -> Result<(), PersonaArtifactError> {
    match cap_fs::stat(parent, Path::new(leaf), cap_fs::FollowSymlinks::No) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Ok(_) => unsafe_state("artifact output already exists; never overwrite"),
        Err(error) => Err(error.into()),
    }
}

fn observe_regular(
    parent: &fs::File,
    leaf: &str,
    maximum: usize,
    label: &Path,
) -> Result<(Vec<u8>, Observation), PersonaArtifactError> {
    let before = cap_fs::stat(parent, Path::new(leaf), cap_fs::FollowSymlinks::No)?;
    if !regular(&before, maximum) {
        return unsafe_state(format!(
            "{} must be a bounded single-link regular file",
            label.display()
        ));
    }
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let mut file = cap_fs::open(parent, Path::new(leaf), &options)?;
    let opened = cap_fs::Metadata::from_file(&file)?;
    let after = cap_fs::stat(parent, Path::new(leaf), cap_fs::FollowSymlinks::No)?;
    if !regular(&opened, maximum)
        || !regular(&after, maximum)
        || !same(&before, &opened)
        || !same(&opened, &after)
    {
        return unsafe_state("artifact changed while opening");
    }
    let mut bytes = Vec::with_capacity(opened.len() as usize);
    let read_limit = u64::try_from(maximum)
        .ok()
        .and_then(|value| value.checked_add(1))
        .ok_or_else(|| PersonaArtifactError::Unsafe("artifact byte limit is unsupported".into()))?;
    (&mut file).take(read_limit).read_to_end(&mut bytes)?;
    let final_metadata = cap_fs::Metadata::from_file(&file)?;
    let named = cap_fs::stat(parent, Path::new(leaf), cap_fs::FollowSymlinks::No)?;
    if bytes.len() as u64 != opened.len()
        || !regular(&final_metadata, maximum)
        || !regular(&named, maximum)
        || !same(&opened, &final_metadata)
        || !same(&final_metadata, &named)
    {
        return unsafe_state("artifact changed while reading");
    }
    std::str::from_utf8(&bytes)
        .map_err(|_| PersonaArtifactError::Unsafe("artifact is not UTF-8".into()))?;
    let observation = Observation {
        identity: identity(&opened),
        len: opened.len(),
        hash: hash_bytes(&bytes),
    };
    Ok((bytes, observation))
}

fn sync_parent(parent: &BoundParent) -> Result<(), PersonaArtifactError> {
    recheck_parent(parent)?;
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let syncable = cap_fs::open(&parent.handle, Path::new("."), &options)?;
    let opened = cap_fs::Metadata::from_file(&syncable)?;
    if !opened.is_dir() || opened.file_type().is_symlink() || !same(&parent.identity, &opened) {
        return unsafe_state("artifact parent changed while reopening for fsync");
    }
    syncable.sync_all()?;
    recheck_parent(parent)
}

fn regular(metadata: &cap_fs::Metadata, maximum: usize) -> bool {
    metadata.file_type().is_file()
        && !metadata.file_type().is_symlink()
        && metadata.len() <= maximum as u64
        && links(metadata) == 1
}

fn safe_leaf(name: &str) -> bool {
    !name.is_empty() && Path::new(name).components().count() == 1 && !name.contains('\0')
}

fn temporary_name(leaf: &str) -> Result<String, PersonaArtifactError> {
    let name = format!(
        "{TEMP_PREFIX}{leaf}.{}.{}",
        std::process::id(),
        TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
    );
    if safe_leaf(&name) {
        Ok(name)
    } else {
        unsafe_state("unsafe temporary artifact name")
    }
}

#[cfg(target_os = "macos")]
fn normalize_alias(path: &Path) -> Result<PathBuf, PersonaArtifactError> {
    let text = path
        .to_str()
        .ok_or_else(|| PersonaArtifactError::Unsafe("path is not UTF-8".into()))?;
    if text == "/tmp" || text.starts_with("/tmp/") || text == "/var" || text.starts_with("/var/") {
        Ok(PathBuf::from(format!("/private{text}")))
    } else {
        Ok(path.to_owned())
    }
}

#[cfg(not(target_os = "macos"))]
fn normalize_alias(path: &Path) -> Result<PathBuf, PersonaArtifactError> {
    Ok(path.to_owned())
}

fn unsafe_state<T>(message: impl Into<String>) -> Result<T, PersonaArtifactError> {
    Err(PersonaArtifactError::Unsafe(message.into()))
}

fn links(metadata: &cap_fs::Metadata) -> u64 {
    #[cfg(unix)]
    {
        use cap_fs::MetadataExt;
        return metadata.nlink();
    }
    #[cfg(windows)]
    {
        use cap_fs::MetadataExt;
        return metadata.number_of_links().unwrap_or(0);
    }
    #[allow(unreachable_code)]
    0
}

fn identity(metadata: &cap_fs::Metadata) -> FileIdentity {
    #[cfg(unix)]
    {
        use cap_fs::MetadataExt;
        FileIdentity {
            dev: metadata.dev(),
            ino: metadata.ino(),
        }
    }
    #[cfg(windows)]
    {
        use cap_fs::MetadataExt;
        FileIdentity {
            volume: metadata.volume_serial_number().unwrap_or(0),
            index: metadata.file_index().unwrap_or(0),
        }
    }
    #[cfg(not(any(unix, windows)))]
    unreachable!()
}

fn same(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    identity(left) == identity(right)
}

#[cfg(unix)]
fn same_std(left: &cap_fs::Metadata, right: &fs::Metadata) -> bool {
    use {cap_fs::MetadataExt as _, std::os::unix::fs::MetadataExt as _};
    left.dev() == right.dev() && left.ino() == right.ino()
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn absolute(path: &Path) -> PathBuf {
        fs::canonicalize(path).unwrap()
    }

    #[test]
    fn creates_once_and_reads_exact_bytes() {
        let root = tempdir().unwrap();
        let output = absolute(root.path()).join("plan.json");
        let bytes = br#"{\"ok\":true}\n"#;
        assert_eq!(publish_create_only(&output, bytes, 64).unwrap(), output);
        assert_eq!(read_strict(&output, 64).unwrap(), bytes);
        assert!(publish_create_only(&output, bytes, 64).is_err());
    }

    #[test]
    fn rejects_relative_and_traversal_paths() {
        let root = tempdir().unwrap();
        assert!(read_strict(Path::new("plan.json"), 64).is_err());
        let unsafe_path = absolute(root.path())
            .join("nested")
            .join("..")
            .join("plan.json");
        assert!(publish_create_only(&unsafe_path, b"{}", 64).is_err());
        let long = absolute(root.path()).join("x".repeat(256));
        assert!(publish_create_only(&long, b"{}", 64).is_err());
    }

    #[test]
    fn rejects_an_unrepresentable_read_cap_without_overflow() {
        let root = tempdir().unwrap();
        let output = absolute(root.path()).join("plan.json");
        fs::write(&output, b"{}\n").unwrap();
        assert!(read_strict(&output, usize::MAX).is_err());
    }

    #[cfg(windows)]
    #[test]
    fn windows_cap_and_public_directory_identity_match() {
        let root = tempdir().unwrap();
        let target = root.path().join("artifact.json");
        assert!(matches!(
            target.components().next(),
            Some(Component::Prefix(prefix)) if matches!(prefix.kind(), std::path::Prefix::Disk(_))
        ));
        assert!(bind_parent(&target).is_ok());
        let directory = fs::File::open(root.path()).unwrap();
        let public = kio_core::cas::windows_real_directory_identity(root.path()).unwrap();
        assert_eq!(
            kio_core::cas::windows_directory_handle_identity(&directory),
            public
        );
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symlink_and_hardlink_artifacts() {
        use std::os::unix::fs::symlink;
        let root = tempdir().unwrap();
        let base = absolute(root.path());
        let source = base.join("source");
        fs::write(&source, b"{}\n").unwrap();
        let link = base.join("link");
        symlink(&source, &link).unwrap();
        assert!(read_strict(&link, 64).is_err());
        let hard = base.join("hard");
        fs::hard_link(&source, &hard).unwrap();
        assert!(read_strict(&hard, 64).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn rejects_replaced_parent_before_publication() {
        let root = tempdir().unwrap();
        let base = absolute(root.path());
        let parent = base.join("out");
        fs::create_dir(&parent).unwrap();
        let target = parent.join("plan.json");
        // Binding is internal, but this exercises the retained-identity check
        // directly before any public leaf is created.
        let bound = bind_parent(&target).unwrap();
        fs::rename(&parent, base.join("old")).unwrap();
        fs::create_dir(&parent).unwrap();
        assert!(recheck_parent(&bound).is_err());
    }
}
