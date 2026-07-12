//! Content-addressed storage primitives.

use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::error::{IoResultExt, KcsError, Result};

pub const CAS_STREAM_BUFFER_BYTES: usize = 64 * 1024;
pub const MAX_RAW_OBJECT_BYTES: u64 = 512 * 1024 * 1024;
pub const MAX_TREE_OBJECT_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_COMMIT_OBJECT_BYTES: u64 = 1024 * 1024;

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
    let mut file = open_regular_nofollow(path)?;
    let metadata = file.metadata().kcs_io(path)?;
    let limit = kind.max_bytes();
    if metadata.len() > limit {
        return Err(object_size_error(kind, limit, metadata.len()));
    }

    let mut bytes = Vec::new();
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
    Ok((total, bytes))
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

fn open_regular_nofollow(path: &Path) -> Result<File> {
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
pub(crate) fn windows_directory_is_real(path: &Path) -> std::io::Result<bool> {
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
    Ok(windows_file_information(&directory).is_some_and(WindowsFileInformation::is_real_directory))
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
}
