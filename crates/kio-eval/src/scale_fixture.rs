//! Capability-safe materialization of the frozen Rust-owned scale corpus.
//!
//! The output parent is bound once by a lexical no-follow walk.  All later
//! operations are descriptor-relative; public paths are diagnostics only.

use crate::{
    boundary::sync_retained_directory,
    scale_spec::{
        self, MANIFEST_NAME, OWNER_MARKER_NAME, OwnerMarker, OwnerState, SCOPES, ScaleProfile,
    },
};
use cap_primitives::{ambient_authority, fs as cap_fs};
use kio_core::cas::hash_bytes;
use std::{
    collections::BTreeSet,
    fs,
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};
use thiserror::Error;

const TEMP_PREFIX: &str = ".kio-scale-v2.tmp-";
const MAX_TOTAL_BYTES: u64 = 2 * 1024 * 1024 * 1024;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Error)]
pub enum ScaleFixtureError {
    #[error("invalid scale fixture output: {0}")]
    Input(String),
    #[error("scale fixture filesystem operation failed: {0}")]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Spec(#[from] scale_spec::ScaleSpecError),
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GenerateOutcome {
    Created,
    ReadyNoop,
    Recovered,
    Reset,
}
#[derive(Debug)]
struct BoundParent {
    handle: fs::File,
    identity: cap_fs::Metadata,
    public: PathBuf,
    leaf: String,
}
#[derive(Debug, Clone, PartialEq, Eq)]
struct ImmutableFile {
    identity: FileIdentity,
    len: u64,
    hash: String,
}
#[derive(Debug, Clone, PartialEq, Eq)]
struct ImmutableScope {
    identity: FileIdentity,
    sources: Vec<ImmutableFile>,
}
#[derive(Debug, Clone, PartialEq, Eq)]
struct ImmutableFixture {
    owner: ImmutableFile,
    manifest: ImmutableFile,
    lock: ImmutableFile,
    scopes: Vec<ImmutableScope>,
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
#[derive(Debug)]
pub struct ValidatedFixture {
    root: PathBuf,
    root_handle: fs::File,
    root_identity: cap_fs::Metadata,
    parent_handle: fs::File,
    parent_identity: cap_fs::Metadata,
    parent_public: PathBuf,
    root_leaf: String,
    profile: ScaleProfile,
    manifest: scale_spec::ScaleManifest,
    owner: OwnerMarker,
    immutable: ImmutableFixture,
}
impl ValidatedFixture {
    #[must_use]
    pub fn root(&self) -> &Path {
        &self.root
    }
    #[must_use]
    pub fn profile(&self) -> ScaleProfile {
        self.profile
    }
    #[must_use]
    pub fn manifest(&self) -> &scale_spec::ScaleManifest {
        &self.manifest
    }
    #[must_use]
    pub fn owner(&self) -> &OwnerMarker {
        &self.owner
    }
    #[allow(dead_code)]
    pub(crate) fn try_clone_root(&self) -> Result<fs::File, ScaleFixtureError> {
        Ok(self.root_handle.try_clone()?)
    }
    /// Retain one declared scope for descriptor-bound consumers.  Callers
    /// cannot turn this into authority for an undeclared path.
    pub(crate) fn try_clone_scope(&self, name: &str) -> Result<fs::File, ScaleFixtureError> {
        if !self.manifest.scopes.iter().any(|scope| scope.name == name) {
            return bad("benchmark scope is not declared by the fixture manifest");
        }
        open_dir(&self.root_handle, name, &self.root)
    }
    pub fn recheck(&self) -> Result<(), ScaleFixtureError> {
        let visible_parent = bind_parent(&self.root)?;
        if visible_parent.public != self.parent_public
            || !same(&visible_parent.identity, &self.parent_identity)
        {
            return bad("public fixture parent changed after binding");
        }
        named_identity(
            &visible_parent.handle,
            &visible_parent.leaf,
            &self.root_identity,
        )?;
        ensure_dir(&self.parent_handle, &self.parent_identity, &self.root)?;
        ensure_dir(&self.root_handle, &self.root_identity, &self.root)?;
        named_identity(&self.parent_handle, &self.root_leaf, &self.root_identity)?;
        let (o, m) = inspect(&self.root_handle, &self.root, self.profile, true)?;
        if o != self.owner || m != self.manifest {
            return bad("fixture changed after binding");
        }
        if observe_immutable(&self.root_handle, &self.root, self.profile)? != self.immutable {
            return bad("immutable fixture authority changed after binding");
        }
        Ok(())
    }
    pub fn lock(&self) -> Result<FixtureLock, ScaleFixtureError> {
        self.recheck()?;
        let guard = lock(&self.root_handle, &self.root)?;
        self.recheck()?;
        guard.recheck()?;
        Ok(guard)
    }
}
#[derive(Debug)]
pub struct FixtureLock {
    file: fs::File,
    root: fs::File,
    label: PathBuf,
    binding: ImmutableFile,
}
impl FixtureLock {
    fn recheck(&self) -> Result<(), ScaleFixtureError> {
        if observed_regular(&self.root, scale_spec::LOCK_NAME, 64, &self.label)? != self.binding {
            return bad("fixture lock changed after acquisition");
        }
        Ok(())
    }
}
impl Drop for FixtureLock {
    fn drop(&mut self) {
        #[cfg(unix)]
        {
            use std::os::fd::AsRawFd;
            let _ = unsafe { libc::flock(self.file.as_raw_fd(), libc::LOCK_UN) };
        }
    }
}

pub fn bind_ready(root: &Path) -> Result<ValidatedFixture, ScaleFixtureError> {
    bind_ready_expected(root, None)
}

pub(crate) fn bind_ready_expected(
    root: &Path,
    expected_profile: Option<ScaleProfile>,
) -> Result<ValidatedFixture, ScaleFixtureError> {
    let p = bind_parent(root)?;
    let h = open_dir(&p.handle, &p.leaf, root)?;
    let i = meta_file(&h, root)?;
    let owner = scale_spec::parse_owner(&read_regular(
        &h,
        OWNER_MARKER_NAME,
        scale_spec::MAX_OWNER_BYTES,
        root,
    )?)?;
    match expected_profile {
        Some(expected) if owner.profile != expected => {
            return bad("fixture owner profile differs from requested profile");
        }
        _ => {}
    }
    let profile = owner.profile;
    let (owner, manifest) = inspect(&h, root, profile, true)?;
    let immutable = observe_immutable(&h, root, profile)?;
    let parent_handle = p.handle.try_clone()?;
    Ok(ValidatedFixture {
        root: root.to_path_buf(),
        root_handle: h,
        root_identity: i,
        parent_handle,
        parent_identity: p.identity,
        parent_public: p.public,
        root_leaf: p.leaf,
        profile,
        manifest,
        owner,
        immutable,
    })
}

pub fn generate(
    out: &Path,
    profile: ScaleProfile,
    reset_owned: bool,
) -> Result<GenerateOutcome, ScaleFixtureError> {
    ensure_atomic_rename_supported()?;
    let parent = bind_parent(out)?;
    ensure_public_parent(&parent)?;
    let temp = format!("{TEMP_PREFIX}{}", profile_name(profile));
    recover_interrupted_reset(&parent, &temp, profile, out)?;
    match cap_fs::stat(
        &parent.handle,
        Path::new(&parent.leaf),
        cap_fs::FollowSymlinks::No,
    ) {
        Ok(m) if m.is_dir() && !m.file_type().is_symlink() => {
            let root = open_dir(&parent.handle, &parent.leaf, out)?;
            match inspect(&root, out, profile, true) {
                Ok(_) if !reset_owned => {
                    let guard = lock(&root, out)?;
                    inspect(&root, out, profile, true)?;
                    guard.recheck()?;
                    let identity = meta_file(&root, out)?;
                    named_identity(&parent.handle, &parent.leaf, &identity)?;
                    drop(guard);
                    return Ok(GenerateOutcome::ReadyNoop);
                }
                Ok(_) => {
                    let guard = lock(&root, out)?;
                    inspect(&root, out, profile, false)?;
                    let immutable = observe_immutable(&root, out, profile)?;
                    guard.recheck()?;
                    let reset = reset_slot(profile);
                    capture_and_remove(&parent, &root, reset, profile, &immutable, out)?;
                    drop(guard);
                    materialize(&parent, &temp, profile, out, true)?;
                    return Ok(GenerateOutcome::Reset);
                }
                Err(e) => {
                    return bad(format!(
                        "existing output is not an exact current ready fixture: {e}"
                    ));
                }
            }
        }
        Ok(_) => return bad("output must be a real directory or absent"),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
        Err(e) => return Err(e.into()),
    }
    match cap_fs::stat(&parent.handle, Path::new(&temp), cap_fs::FollowSymlinks::No) {
        Ok(m) if m.is_dir() && !m.file_type().is_symlink() => {
            let h = open_dir(&parent.handle, &temp, out)?;
            let temp_identity = meta_file(&h, out)?;
            let guard = lock(&h, out)?;
            inspect(&h, out, profile, false).map_err(|e| {
                ScaleFixtureError::Input(format!(
                    "current generator temporary fixture is not recoverable: {e}"
                ))
            })?;
            let immutable = observe_immutable(&h, out, profile)?;
            ensure_public_parent(&parent)?;
            named_identity(&parent.handle, &temp, &temp_identity)?;
            if observe_immutable(&h, out, profile)? != immutable {
                return bad("temporary fixture changed before recovery publication");
            }
            guard.recheck()?;
            rename_noreplace(&parent.handle, &temp, &parent.handle, &parent.leaf)?;
            sync_parent(&parent)?;
            let h = open_dir(&parent.handle, &parent.leaf, out)?;
            if !same(&meta_file(&h, out)?, &temp_identity) {
                return bad("recovered output identity differs from temporary fixture");
            }
            inspect(&h, out, profile, false)?;
            if observe_immutable(&h, out, profile)? != immutable {
                return bad("recovered output immutable authority differs from temporary fixture");
            }
            drop(guard);
            Ok(GenerateOutcome::Recovered)
        }
        Ok(_) => bad("temporary fixture is unsafe or not a directory"),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            materialize(&parent, &temp, profile, out, false)?;
            Ok(GenerateOutcome::Created)
        }
        Err(e) => Err(e.into()),
    }
}

fn recover_interrupted_reset(
    parent: &BoundParent,
    build_slot: &str,
    profile: ScaleProfile,
    label: &Path,
) -> Result<(), ScaleFixtureError> {
    let root = match open_dir(&parent.handle, &parent.leaf, label) {
        Ok(root) => root,
        Err(_) => return Ok(()),
    };
    if !names(&root, SCOPES.len() + 8, label)?.is_empty() {
        return Ok(());
    }
    // An empty public root is only recoverable when one of the two fixed,
    // current-schema slots independently proves a complete ready fixture.
    for slot in [reset_slot(profile), build_slot] {
        let candidate = match open_dir(&parent.handle, slot, label) {
            Ok(candidate) => candidate,
            Err(_) => continue,
        };
        if inspect(&candidate, label, profile, false).is_ok() {
            // A ready-looking slot can belong to a live reset.  The exact
            // persistent fixture lock is the writer barrier: recovery may
            // exchange it only after the owner has died and released it.
            let guard = lock(&candidate, label)?;
            inspect(&candidate, label, profile, false)?;
            let immutable = observe_immutable(&candidate, label, profile)?;
            guard.recheck()?;
            let root_identity = meta_file(&root, label)?;
            let candidate_identity = meta_file(&candidate, label)?;
            named_identity(&parent.handle, &parent.leaf, &root_identity)?;
            named_identity(&parent.handle, slot, &candidate_identity)?;
            rename_exchange(&parent.handle, &parent.leaf, slot)?;
            sync_parent(parent)?;
            let restored = open_dir(&parent.handle, &parent.leaf, label)?;
            if !same(&meta_file(&restored, label)?, &candidate_identity) {
                return bad("reset recovery output identity differs from ready slot");
            }
            inspect(&restored, label, profile, false)?;
            if observe_immutable(&restored, label, profile)? != immutable {
                return bad("reset recovery output immutable authority differs from ready slot");
            }
            guard.recheck()?;
            drop(guard);
            return Ok(());
        }
    }
    bad("interrupted reset has no current-schema ready recovery slot")
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn ensure_atomic_rename_supported() -> Result<(), ScaleFixtureError> {
    Ok(())
}
#[cfg(not(any(target_os = "linux", target_os = "macos")))]
fn ensure_atomic_rename_supported() -> Result<(), ScaleFixtureError> {
    bad("atomic no-replace publication unsupported")
}

fn materialize(
    parent: &BoundParent,
    temp_name: &str,
    profile: ScaleProfile,
    label: &Path,
    exchange_publish: bool,
) -> Result<(), ScaleFixtureError> {
    ensure_public_parent(parent)?;
    if exchange_publish {
        ensure_empty_slot(&parent.handle, temp_name, label)?;
    } else {
        create_dir(&parent.handle, temp_name, label)?;
    }
    let temp = open_dir(&parent.handle, temp_name, label)?;
    let temp_identity = meta_file(&temp, label)?;
    (|| {
        write_new(
            &temp,
            OWNER_MARKER_NAME,
            &scale_spec::serialize_owner(&OwnerMarker {
                schema_version: scale_spec::SCHEMA_VERSION,
                fixture_id: scale_spec::FIXTURE_ID.into(),
                generator: scale_spec::GENERATOR_ID.into(),
                profile,
                state: OwnerState::Building,
                manifest_hash: None,
            })?,
            label,
        )?;
        write_new(&temp, scale_spec::LOCK_NAME, b"locked\n", label)?;
        let guard = lock(&temp, label)?;
        let mut total = 0u64;
        for (si, scope) in SCOPES.iter().enumerate() {
            create_dir(&temp, scope.name, label)?;
            let s = open_dir(&temp, scope.name, label)?;
            for fi in 0..profile.files_per_scope() {
                let text = scale_spec::render_document(si, fi, profile)?;
                total = total.checked_add(text.len() as u64).ok_or_else(|| {
                    ScaleFixtureError::Input("generated byte accounting overflow".into())
                })?;
                if text.len() > scale_spec::MAX_SOURCE_BYTES || total > MAX_TOTAL_BYTES {
                    return bad("generated source exceeds bound");
                }
                write_new(&s, &scale_spec::document_path(fi), text.as_bytes(), label)?;
            }
            sync_dir(&s, label)?;
        }
        let manifest = scale_spec::frozen_manifest(profile)?;
        write_new(
            &temp,
            MANIFEST_NAME,
            &scale_spec::serialize_manifest(&manifest)?,
            label,
        )?;
        replace_regular(
            &temp,
            OWNER_MARKER_NAME,
            &scale_spec::serialize_owner(&OwnerMarker {
                schema_version: scale_spec::SCHEMA_VERSION,
                fixture_id: scale_spec::FIXTURE_ID.into(),
                generator: scale_spec::GENERATOR_ID.into(),
                profile,
                state: OwnerState::Ready,
                manifest_hash: Some(scale_spec::manifest_hash(&manifest)?),
            })?,
            label,
        )?;
        inspect(&temp, label, profile, false)?;
        let immutable = observe_immutable(&temp, label, profile)?;
        sync_dir(&temp, label)?;
        ensure_public_parent(parent)?;
        named_identity(&parent.handle, temp_name, &temp_identity)?;
        if observe_immutable(&temp, label, profile)? != immutable {
            return bad("temporary fixture changed before publication");
        }
        guard.recheck()?;
        if exchange_publish {
            rename_exchange(&parent.handle, temp_name, &parent.leaf)?;
        } else {
            rename_noreplace(&parent.handle, temp_name, &parent.handle, &parent.leaf)?;
        }
        sync_parent(parent)?;
        let h = open_dir(&parent.handle, &parent.leaf, label)?;
        if !same(&meta_file(&h, label)?, &temp_identity) {
            return bad("published output identity differs from temporary fixture");
        }
        inspect(&h, label, profile, false)?;
        if observe_immutable(&h, label, profile)? != immutable {
            return bad("published output immutable authority differs from temporary fixture");
        }
        if exchange_publish {
            let empty = open_dir(&parent.handle, temp_name, label)?;
            if !names(&empty, 0, label)?.is_empty() {
                return bad("build slot is not empty after publication exchange");
            }
        }
        drop(guard);
        Ok(())
    })()
}

fn inspect(
    root: &fs::File,
    label: &Path,
    profile: ScaleProfile,
    allow_runtime: bool,
) -> Result<(OwnerMarker, scale_spec::ScaleManifest), ScaleFixtureError> {
    if !meta_file(root, label)?.is_dir() {
        return bad("fixture root is not a real directory");
    }
    let owner = scale_spec::parse_owner(&read_regular(
        root,
        OWNER_MARKER_NAME,
        scale_spec::MAX_OWNER_BYTES,
        label,
    )?)?;
    let manifest = scale_spec::parse_manifest(&read_regular(
        root,
        MANIFEST_NAME,
        scale_spec::MAX_MANIFEST_BYTES,
        label,
    )?)?;
    if owner.profile != profile || owner.state != OwnerState::Ready || manifest.profile != profile {
        return bad("fixture owner or manifest profile is not ready");
    }
    if read_regular(root, scale_spec::LOCK_NAME, 64, label)? != b"locked\n" {
        return bad("fixture lock is invalid");
    }
    let mut expected = BTreeSet::from([
        OWNER_MARKER_NAME.to_owned(),
        MANIFEST_NAME.to_owned(),
        scale_spec::LOCK_NAME.to_owned(),
    ]);
    let mut total = 0u64;
    for (si, spec) in SCOPES.iter().enumerate() {
        expected.insert(spec.name.into());
        let scope = open_dir(root, spec.name, label)?;
        let got = names(
            &scope,
            profile.files_per_scope() + usize::from(allow_runtime),
            label,
        )?;
        let wanted: BTreeSet<String> = (0..profile.files_per_scope())
            .map(scale_spec::document_path)
            .collect();
        if got != wanted
            && (!allow_runtime
                || !wanted.is_subset(&got)
                || !got.difference(&wanted).all(|name| name == ".kio"))
        {
            return bad("scope contains unknown or missing entries");
        }
        for fi in 0..profile.files_per_scope() {
            let actual = read_regular(
                &scope,
                &scale_spec::document_path(fi),
                scale_spec::MAX_SOURCE_BYTES,
                label,
            )?;
            total = total.checked_add(actual.len() as u64).ok_or_else(|| {
                ScaleFixtureError::Input("source byte accounting overflow".into())
            })?;
            if total > MAX_TOTAL_BYTES {
                return bad("source aggregate exceeds bound");
            }
            if actual != scale_spec::render_document(si, fi, profile)?.as_bytes() {
                return bad("source differs from frozen renderer");
            }
        }
        let scope_identity = meta_file(&scope, label)?;
        named_identity(root, spec.name, &scope_identity)?;
    }
    let actual_root = names(
        root,
        SCOPES.len() + 3 + if allow_runtime { 3 } else { 0 },
        label,
    )?;
    let allowed_runtime = BTreeSet::from([
        scale_spec::DEVICE_DIR_NAME.to_owned(),
        scale_spec::ATTESTATION_NAME.to_owned(),
        scale_spec::PREPARE_REPORT_NAME.to_owned(),
    ]);
    if actual_root != expected
        && (!allow_runtime
            || !expected.is_subset(&actual_root)
            || !actual_root
                .difference(&expected)
                .all(|name| allowed_runtime.contains(name)))
    {
        return bad("fixture contains unknown or missing entries");
    }
    if allow_runtime {
        validate_runtime_leaves(root, label)?;
    }
    Ok((owner, manifest))
}

fn validate_runtime_leaves(root: &fs::File, label: &Path) -> Result<(), ScaleFixtureError> {
    for name in [
        scale_spec::ATTESTATION_NAME,
        scale_spec::PREPARE_REPORT_NAME,
    ] {
        match cap_fs::stat(root, Path::new(name), cap_fs::FollowSymlinks::No) {
            Ok(metadata) if regular(&metadata, scale_spec::MAX_MANIFEST_BYTES) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Ok(_) => return bad("runtime report is not a bounded single-link regular file"),
            Err(error) => return Err(error.into()),
        }
    }
    match cap_fs::stat(
        root,
        Path::new(scale_spec::DEVICE_DIR_NAME),
        cap_fs::FollowSymlinks::No,
    ) {
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Ok(_) => return bad("runtime device is not a real directory"),
        Err(error) => return Err(error.into()),
    }
    for scope in SCOPES {
        let scope_handle = open_dir(root, scope.name, label)?;
        match cap_fs::stat(&scope_handle, Path::new(".kio"), cap_fs::FollowSymlinks::No) {
            Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Ok(_) => return bad("runtime .kio is not a real directory"),
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

fn capture_and_remove(
    parent: &BoundParent,
    root: &fs::File,
    reset_name: &str,
    profile: ScaleProfile,
    immutable: &ImmutableFixture,
    label: &Path,
) -> Result<(), ScaleFixtureError> {
    ensure_public_parent(parent)?;
    let root_identity = meta_file(root, label)?;
    named_identity(&parent.handle, &parent.leaf, &root_identity)?;
    ensure_empty_slot(&parent.handle, reset_name, label)?;
    let reset = open_dir(&parent.handle, reset_name, label)?;
    let reset_identity = meta_file(&reset, label)?;
    rename_exchange(&parent.handle, &parent.leaf, reset_name)?;
    sync_parent(parent)?;
    named_identity(&parent.handle, reset_name, &root_identity)?;
    named_identity(&parent.handle, &parent.leaf, &reset_identity)?;
    if observe_immutable(root, label, profile)? != *immutable {
        return bad("immutable fixture changed before reset capture");
    }
    remove_captured(parent, root, reset_name, profile, label)
}

fn remove_captured(
    parent: &BoundParent,
    root: &fs::File,
    reset_name: &str,
    profile: ScaleProfile,
    label: &Path,
) -> Result<(), ScaleFixtureError> {
    inspect(root, label, profile, false)?;
    for scope in SCOPES {
        let h = open_dir(root, scope.name, label)?;
        for i in 0..profile.files_per_scope() {
            remove_regular(&h, &scale_spec::document_path(i), label)?;
        }
        if !names(&h, 0, label)?.is_empty() {
            return bad("scope changed before reset");
        }
        let scope_identity = meta_file(&h, label)?;
        named_identity(root, scope.name, &scope_identity)?;
        cap_fs::remove_dir(root, Path::new(scope.name))?;
    }
    for name in [OWNER_MARKER_NAME, MANIFEST_NAME, scale_spec::LOCK_NAME] {
        remove_regular(root, name, label)?;
    }
    if !names(root, 0, label)?.is_empty() {
        return bad("fixture changed before reset");
    }
    ensure_dir(&parent.handle, &parent.identity, &parent.public)?;
    let root_identity = meta_file(root, label)?;
    named_identity(&parent.handle, reset_name, &root_identity)?;
    sync_parent(parent)
}

fn lock(root: &fs::File, label: &Path) -> Result<FixtureLock, ScaleFixtureError> {
    let (file, binding) = open_lock(root, label)?;
    #[cfg(unix)]
    {
        use std::os::fd::AsRawFd;
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return bad("fixture lock is already held");
        }
    }
    #[cfg(not(unix))]
    {
        return bad("safe fixture locks unsupported");
    }
    let guard = FixtureLock {
        file,
        root: root.try_clone()?,
        label: label.to_path_buf(),
        binding,
    };
    guard.recheck()?;
    Ok(guard)
}
fn open_lock(
    root: &fs::File,
    label: &Path,
) -> Result<(fs::File, ImmutableFile), ScaleFixtureError> {
    let mut file = open_regular(root, scale_spec::LOCK_NAME, 64, label)?;
    let before = meta_file(&file, label)?;
    let mut bytes = Vec::with_capacity(before.len() as usize);
    (&mut file).take(65).read_to_end(&mut bytes)?;
    let opened = meta_file(&file, label)?;
    let named = cap_fs::stat(
        root,
        Path::new(scale_spec::LOCK_NAME),
        cap_fs::FollowSymlinks::No,
    )?;
    if bytes != b"locked\n" || !same(&before, &opened) || !same(&opened, &named) {
        return bad("fixture lock changed while opening");
    }
    Ok((
        file,
        ImmutableFile {
            identity: file_identity(&opened),
            len: opened.len(),
            hash: hash_bytes(&bytes),
        },
    ))
}
fn names(dir: &fs::File, limit: usize, _: &Path) -> Result<BTreeSet<String>, ScaleFixtureError> {
    let mut r = BTreeSet::new();
    for entry in cap_fs::read_dir(dir, Path::new("."))? {
        let entry = entry?;
        if r.len() >= limit {
            return bad("directory entry count exceeds bound");
        }
        let name = entry
            .file_name()
            .to_str()
            .ok_or_else(|| ScaleFixtureError::Input("entry name is not UTF-8".into()))?
            .to_owned();
        if !leaf(&name) {
            return bad("directory entry is not a safe leaf");
        }
        let m = cap_fs::stat(dir, Path::new(&name), cap_fs::FollowSymlinks::No)?;
        if (!m.is_file() && !m.is_dir()) || m.file_type().is_symlink() {
            return bad("directory contains symlink or nonregular entry");
        }
        r.insert(name);
    }
    Ok(r)
}
fn observe_immutable(
    root: &fs::File,
    label: &Path,
    profile: ScaleProfile,
) -> Result<ImmutableFixture, ScaleFixtureError> {
    let owner = observed_regular(root, OWNER_MARKER_NAME, scale_spec::MAX_OWNER_BYTES, label)?;
    let manifest = observed_regular(root, MANIFEST_NAME, scale_spec::MAX_MANIFEST_BYTES, label)?;
    let lock = observed_regular(root, scale_spec::LOCK_NAME, 64, label)?;
    let mut scopes = Vec::with_capacity(SCOPES.len());
    for scope in SCOPES {
        let handle = open_dir(root, scope.name, label)?;
        let identity = file_identity(&meta_file(&handle, label)?);
        let mut sources = Vec::with_capacity(profile.files_per_scope());
        for index in 0..profile.files_per_scope() {
            sources.push(observed_regular(
                &handle,
                &scale_spec::document_path(index),
                scale_spec::MAX_SOURCE_BYTES,
                label,
            )?);
        }
        named_identity(root, scope.name, &meta_file(&handle, label)?)?;
        scopes.push(ImmutableScope { identity, sources });
    }
    Ok(ImmutableFixture {
        owner,
        manifest,
        lock,
        scopes,
    })
}
fn observed_regular(
    dir: &fs::File,
    name: &str,
    max: usize,
    label: &Path,
) -> Result<ImmutableFile, ScaleFixtureError> {
    let mut f = open_regular(dir, name, max, label)?;
    let before = meta_file(&f, label)?;
    let mut bytes = Vec::with_capacity(before.len() as usize);
    (&mut f).take(max as u64 + 1).read_to_end(&mut bytes)?;
    let opened = meta_file(&f, label)?;
    let named = cap_fs::stat(dir, Path::new(name), cap_fs::FollowSymlinks::No)?;
    if bytes.len() > max
        || bytes.len() as u64 != before.len()
        || !same(&before, &opened)
        || !same(&opened, &named)
    {
        return bad("file changed during read");
    }
    Ok(ImmutableFile {
        identity: file_identity(&opened),
        len: opened.len(),
        hash: hash_bytes(&bytes),
    })
}
fn read_regular(
    dir: &fs::File,
    name: &str,
    max: usize,
    label: &Path,
) -> Result<Vec<u8>, ScaleFixtureError> {
    let mut f = open_regular(dir, name, max, label)?;
    let before = meta_file(&f, label)?;
    let mut b = Vec::with_capacity(before.len() as usize);
    (&mut f).take(max as u64 + 1).read_to_end(&mut b)?;
    let opened = meta_file(&f, label)?;
    let named = cap_fs::stat(dir, Path::new(name), cap_fs::FollowSymlinks::No)?;
    if b.len() > max
        || b.len() as u64 != before.len()
        || !same(&before, &opened)
        || !same(&opened, &named)
    {
        return bad("file changed during read");
    }
    Ok(b)
}
fn open_regular(
    dir: &fs::File,
    name: &str,
    max: usize,
    label: &Path,
) -> Result<fs::File, ScaleFixtureError> {
    if !leaf(name) {
        return bad("unsafe file name");
    }
    let before = cap_fs::stat(dir, Path::new(name), cap_fs::FollowSymlinks::No)?;
    let mut o = cap_fs::OpenOptions::new();
    o.read(true)._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let f = cap_fs::open(dir, Path::new(name), &o)?;
    let opened = meta_file(&f, label)?;
    let after = cap_fs::stat(dir, Path::new(name), cap_fs::FollowSymlinks::No)?;
    if !regular(&before, max)
        || !regular(&opened, max)
        || !regular(&after, max)
        || !same(&before, &opened)
        || !same(&opened, &after)
    {
        return bad("not a stable bounded single-link regular file");
    }
    Ok(f)
}
fn write_new(dir: &fs::File, name: &str, b: &[u8], label: &Path) -> Result<(), ScaleFixtureError> {
    if !leaf(name) || b.len() > scale_spec::MAX_SOURCE_BYTES {
        return bad("unsafe generated write");
    }
    let mut o = cap_fs::OpenOptions::new();
    o.write(true).create_new(true);
    let mut f = cap_fs::open(dir, Path::new(name), &o)?;
    f.write_all(b)?;
    f.sync_all()?;
    drop(f);
    let _ = open_regular(dir, name, b.len(), label)?;
    Ok(())
}
fn replace_regular(
    dir: &fs::File,
    name: &str,
    b: &[u8],
    label: &Path,
) -> Result<(), ScaleFixtureError> {
    let old = read_regular(dir, name, scale_spec::MAX_OWNER_BYTES, label)?;
    let tmp = temp_leaf(name)?;
    write_new(dir, &tmp, b, label)?;
    rename_exchange(dir, &tmp, name)?;
    if read_regular(dir, &tmp, scale_spec::MAX_OWNER_BYTES, label)? != old {
        return bad("replacement target changed before exchange");
    }
    cap_fs::remove_file(dir, Path::new(&tmp))?;
    sync_dir(dir, label)
}
fn remove_regular(dir: &fs::File, name: &str, label: &Path) -> Result<(), ScaleFixtureError> {
    let _ = open_regular(dir, name, scale_spec::MAX_SOURCE_BYTES, label)?;
    cap_fs::remove_file(dir, Path::new(name))?;
    Ok(())
}
fn create_dir(parent: &fs::File, name: &str, label: &Path) -> Result<(), ScaleFixtureError> {
    if !leaf(name) {
        return bad("unsafe directory name");
    }
    cap_fs::create_dir(parent, Path::new(name), &cap_fs::DirOptions::new())?;
    let h = open_dir(parent, name, label)?;
    sync_dir(&h, label)
}
fn ensure_empty_slot(parent: &fs::File, name: &str, label: &Path) -> Result<(), ScaleFixtureError> {
    match cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            create_dir(parent, name, label)
        }
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
            let slot = open_dir(parent, name, label)?;
            if names(&slot, 0, label)?.is_empty() {
                Ok(())
            } else {
                bad("current reset/build slot is not empty")
            }
        }
        Ok(_) => bad("current reset/build slot is unsafe"),
        Err(error) => Err(error.into()),
    }
}
fn open_dir(parent: &fs::File, name: &str, label: &Path) -> Result<fs::File, ScaleFixtureError> {
    if !leaf(name) {
        return bad("unsafe directory name");
    }
    let before = cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No)?;
    let h = cap_fs::open_dir_nofollow(parent, Path::new(name))?;
    let opened = meta_file(&h, label)?;
    let after = cap_fs::stat(parent, Path::new(name), cap_fs::FollowSymlinks::No)?;
    if !before.is_dir()
        || before.file_type().is_symlink()
        || !same(&before, &opened)
        || !same(&opened, &after)
    {
        return bad("directory changed while opening");
    }
    Ok(h)
}
fn bind_parent(output: &Path) -> Result<BoundParent, ScaleFixtureError> {
    if !output.is_absolute()
        || output.as_os_str().is_empty()
        || output
            .components()
            .any(|c| matches!(c, Component::ParentDir | Component::CurDir))
    {
        return bad("output must be an absolute normalized path");
    }
    let output = normalize_alias(output)?;
    let leaf_name = output
        .file_name()
        .and_then(|x| x.to_str())
        .filter(|x| leaf(x))
        .ok_or_else(|| ScaleFixtureError::Input("output has no safe final component".into()))?
        .to_owned();
    let path = output
        .parent()
        .ok_or_else(|| ScaleFixtureError::Input("output has no parent".into()))?;
    let mut h = cap_fs::open_ambient_dir(Path::new("/"), ambient_authority())?;
    for c in path.components() {
        match c {
            Component::RootDir => {}
            Component::Normal(n) => h = cap_fs::open_dir_nofollow(&h, Path::new(n))?,
            _ => return bad("unsafe parent component"),
        }
    }
    let identity = meta_file(&h, path)?;
    if !identity.is_dir() {
        return bad("output parent is not a real directory");
    }
    Ok(BoundParent {
        handle: h,
        identity,
        public: path.to_path_buf(),
        leaf: leaf_name,
    })
}
fn ensure_dir(
    h: &fs::File,
    expect: &cap_fs::Metadata,
    label: &Path,
) -> Result<(), ScaleFixtureError> {
    let actual = meta_file(h, label)?;
    if !actual.is_dir() || !same(expect, &actual) {
        return bad("retained directory identity changed");
    }
    Ok(())
}
fn ensure_public_parent(parent: &BoundParent) -> Result<(), ScaleFixtureError> {
    ensure_dir(&parent.handle, &parent.identity, &parent.public)?;
    let public_output = parent.public.join(&parent.leaf);
    let current = bind_parent(&public_output)?;
    if current.public != parent.public || !same(&current.identity, &parent.identity) {
        return bad("public output parent changed after binding");
    }
    Ok(())
}
fn named_identity(
    parent: &fs::File,
    leaf: &str,
    expected: &cap_fs::Metadata,
) -> Result<(), ScaleFixtureError> {
    let named = cap_fs::stat(parent, Path::new(leaf), cap_fs::FollowSymlinks::No)?;
    if !named.is_dir() || named.file_type().is_symlink() || !same(&named, expected) {
        return bad("fixture root changed after binding");
    }
    Ok(())
}
fn sync_dir(h: &fs::File, label: &Path) -> Result<(), ScaleFixtureError> {
    let m = h.metadata()?;
    sync_retained_directory(h, &m, label).map_err(|e| ScaleFixtureError::Input(e.to_string()))
}
fn sync_parent(p: &BoundParent) -> Result<(), ScaleFixtureError> {
    let identity = p.handle.metadata()?;
    sync_retained_directory(&p.handle, &identity, &p.public)
        .map_err(|e| ScaleFixtureError::Input(e.to_string()))
}
fn meta_file(f: &fs::File, label: &Path) -> Result<cap_fs::Metadata, ScaleFixtureError> {
    cap_fs::Metadata::from_file(f)
        .map_err(|e| ScaleFixtureError::Input(format!("{}: {e}", label.display())))
}
fn regular(m: &cap_fs::Metadata, max: usize) -> bool {
    m.file_type().is_file() && !m.file_type().is_symlink() && m.len() <= max as u64 && links(m) == 1
}
fn links(m: &cap_fs::Metadata) -> u64 {
    #[cfg(unix)]
    {
        use cap_fs::MetadataExt;
        return m.nlink();
    }
    #[cfg(windows)]
    {
        use cap_fs::MetadataExt;
        return m.number_of_links().unwrap_or(0);
    }
    #[allow(unreachable_code)]
    0
}
fn same(a: &cap_fs::Metadata, b: &cap_fs::Metadata) -> bool {
    #[cfg(unix)]
    {
        use cap_fs::MetadataExt;
        return a.dev() == b.dev() && a.ino() == b.ino();
    }
    #[cfg(windows)]
    {
        use cap_fs::MetadataExt;
        return a.volume_serial_number() == b.volume_serial_number()
            && a.file_index() == b.file_index();
    }
    #[allow(unreachable_code)]
    false
}
#[cfg(unix)]
fn file_identity(metadata: &cap_fs::Metadata) -> FileIdentity {
    use cap_fs::MetadataExt;
    FileIdentity {
        dev: metadata.dev(),
        ino: metadata.ino(),
    }
}
#[cfg(windows)]
fn file_identity(metadata: &cap_fs::Metadata) -> FileIdentity {
    use cap_fs::MetadataExt;
    FileIdentity {
        volume: metadata.volume_serial_number().unwrap_or(0),
        index: metadata.file_index().unwrap_or(0),
    }
}
fn leaf(n: &str) -> bool {
    !n.is_empty() && Path::new(n).components().count() == 1 && !n.contains('\0')
}
fn bad<T>(s: impl Into<String>) -> Result<T, ScaleFixtureError> {
    Err(ScaleFixtureError::Input(s.into()))
}
fn temp_leaf(n: &str) -> Result<String, ScaleFixtureError> {
    let r = format!(
        ".{n}.{}.{}.tmp",
        std::process::id(),
        TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
    );
    if leaf(&r) {
        Ok(r)
    } else {
        bad("unsafe temporary name")
    }
}
fn reset_slot(profile: ScaleProfile) -> &'static str {
    match profile {
        ScaleProfile::Tiny => ".kio-scale-v2.reset-tiny",
        ScaleProfile::Full => ".kio-scale-v2.reset-full",
    }
}
const fn profile_name(p: ScaleProfile) -> &'static str {
    match p {
        ScaleProfile::Tiny => "tiny",
        ScaleProfile::Full => "full",
    }
}
#[cfg(target_os = "macos")]
fn normalize_alias(p: &Path) -> Result<PathBuf, ScaleFixtureError> {
    let s = p
        .to_str()
        .ok_or_else(|| ScaleFixtureError::Input("path is not UTF-8".into()))?;
    if s == "/tmp" || s.starts_with("/tmp/") || s == "/var" || s.starts_with("/var/") {
        Ok(PathBuf::from(format!("/private{s}")))
    } else {
        Ok(p.to_path_buf())
    }
}
#[cfg(not(target_os = "macos"))]
fn normalize_alias(p: &Path) -> Result<PathBuf, ScaleFixtureError> {
    Ok(p.to_path_buf())
}
#[cfg(target_os = "linux")]
pub(crate) fn rename_noreplace(
    a: &fs::File,
    x: &str,
    b: &fs::File,
    y: &str,
) -> Result<(), ScaleFixtureError> {
    rename_at(a, x, b, y, 1)
}
#[cfg(target_os = "macos")]
pub(crate) fn rename_noreplace(
    a: &fs::File,
    x: &str,
    b: &fs::File,
    y: &str,
) -> Result<(), ScaleFixtureError> {
    rename_at(a, x, b, y, 4)
}
#[cfg(not(any(target_os = "linux", target_os = "macos")))]
pub(crate) fn rename_noreplace(
    _: &fs::File,
    _: &str,
    _: &fs::File,
    _: &str,
) -> Result<(), ScaleFixtureError> {
    bad("atomic no-replace publication unsupported")
}
#[cfg(target_os = "linux")]
fn rename_exchange(a: &fs::File, x: &str, y: &str) -> Result<(), ScaleFixtureError> {
    rename_at(a, x, a, y, 2)
}
#[cfg(target_os = "macos")]
fn rename_exchange(a: &fs::File, x: &str, y: &str) -> Result<(), ScaleFixtureError> {
    rename_at(a, x, a, y, 2)
}
#[cfg(not(any(target_os = "linux", target_os = "macos")))]
fn rename_exchange(_: &fs::File, _: &str, _: &str) -> Result<(), ScaleFixtureError> {
    bad("atomic exchange unsupported")
}
#[cfg(target_os = "linux")]
fn rename_at(
    a: &fs::File,
    x: &str,
    b: &fs::File,
    y: &str,
    f: u32,
) -> Result<(), ScaleFixtureError> {
    use std::{ffi::CString, os::fd::AsRawFd};
    let x = CString::new(x).map_err(|_| ScaleFixtureError::Input("NUL source".into()))?;
    let y = CString::new(y).map_err(|_| ScaleFixtureError::Input("NUL destination".into()))?;
    if unsafe {
        libc::syscall(
            libc::SYS_renameat2,
            a.as_raw_fd(),
            x.as_ptr(),
            b.as_raw_fd(),
            y.as_ptr(),
            f,
        )
    } == 0
    {
        Ok(())
    } else {
        Err(std::io::Error::last_os_error().into())
    }
}
#[cfg(target_os = "macos")]
fn rename_at(
    a: &fs::File,
    x: &str,
    b: &fs::File,
    y: &str,
    f: u32,
) -> Result<(), ScaleFixtureError> {
    use std::{
        ffi::CString,
        os::{fd::AsRawFd, raw::c_char},
    };
    unsafe extern "C" {
        fn renameatx_np(a: i32, x: *const c_char, b: i32, y: *const c_char, f: u32) -> i32;
    }
    let x = CString::new(x).map_err(|_| ScaleFixtureError::Input("NUL source".into()))?;
    let y = CString::new(y).map_err(|_| ScaleFixtureError::Input("NUL destination".into()))?;
    if unsafe { renameatx_np(a.as_raw_fd(), x.as_ptr(), b.as_raw_fd(), y.as_ptr(), f) } == 0 {
        Ok(())
    } else {
        Err(std::io::Error::last_os_error().into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;
    fn rt(t: &tempfile::TempDir) -> PathBuf {
        fs::canonicalize(t.path()).unwrap()
    }
    #[test]
    fn ready_noop_reset_recovery() {
        let t = tempdir().unwrap();
        let r = rt(&t);
        let o = r.join("scale");
        assert_eq!(
            generate(&o, ScaleProfile::Tiny, false).unwrap(),
            GenerateOutcome::Created
        );
        assert_eq!(
            generate(&o, ScaleProfile::Tiny, false).unwrap(),
            GenerateOutcome::ReadyNoop
        );
        let x = r.join(".kio-scale-v2.tmp-tiny");
        fs::rename(&o, &x).unwrap();
        assert_eq!(
            generate(&o, ScaleProfile::Tiny, false).unwrap(),
            GenerateOutcome::Recovered
        );
        assert_eq!(
            generate(&o, ScaleProfile::Tiny, true).unwrap(),
            GenerateOutcome::Reset
        );
        assert_eq!(
            generate(&o, ScaleProfile::Tiny, true).unwrap(),
            GenerateOutcome::Reset
        );
    }

    #[cfg(unix)]
    #[test]
    fn unsafe_leaf_and_replaced_root_fail_closed_without_touching_victim() {
        use std::os::unix::fs::symlink;

        let temp = tempdir().unwrap();
        let root = rt(&temp);
        let out = root.join("scale");
        generate(&out, ScaleProfile::Tiny, false).unwrap();
        let source = out.join(SCOPES[0].name).join("document-0000.md");
        let original = fs::read(&source).unwrap();
        let saved = root.join("saved.md");
        fs::rename(&source, &saved).unwrap();
        symlink(&saved, &source).unwrap();
        assert!(generate(&out, ScaleProfile::Tiny, false).is_err());
        assert_eq!(fs::read(&saved).unwrap(), original);

        fs::remove_file(&source).unwrap();
        fs::rename(&saved, &source).unwrap();
        let second = out.join(SCOPES[1].name).join("document-0000.md");
        fs::remove_file(&second).unwrap();
        fs::hard_link(&source, &second).unwrap();
        assert!(generate(&out, ScaleProfile::Tiny, false).is_err());

        // The retained ready handle must not silently accept a pathname swap.
        fs::remove_file(&second).unwrap();
        fs::write(
            &second,
            scale_spec::render_document(1, 0, ScaleProfile::Tiny).unwrap(),
        )
        .unwrap();
        let bound = bind_ready(&out).unwrap();
        let displaced = root.join("displaced");
        fs::rename(&out, &displaced).unwrap();
        fs::create_dir(&out).unwrap();
        fs::write(out.join("victim"), b"keep").unwrap();
        assert!(bound.recheck().is_err());
        assert_eq!(fs::read(out.join("victim")).unwrap(), b"keep");
    }

    #[test]
    fn prepared_runtime_is_bindable_but_reset_refuses_to_delete_it() {
        let temp = tempdir().unwrap();
        let out = rt(&temp).join("scale");
        generate(&out, ScaleProfile::Tiny, false).unwrap();
        fs::create_dir(out.join(scale_spec::DEVICE_DIR_NAME)).unwrap();
        fs::write(out.join(scale_spec::PREPARE_REPORT_NAME), b"{}\n").unwrap();
        for scope in SCOPES {
            fs::create_dir(out.join(scope.name).join(".kio")).unwrap();
        }
        let bound = bind_ready(&out).unwrap();
        assert_eq!(bound.profile(), ScaleProfile::Tiny);
        assert_eq!(
            generate(&out, ScaleProfile::Tiny, false).unwrap(),
            GenerateOutcome::ReadyNoop
        );
        assert!(generate(&out, ScaleProfile::Tiny, true).is_err());
        assert!(out.join(scale_spec::DEVICE_DIR_NAME).exists());
        assert!(out.join(scale_spec::PREPARE_REPORT_NAME).exists());
    }

    #[test]
    fn public_parent_and_scope_replacement_preserve_victims() {
        let temp = tempdir().unwrap();
        let root = rt(&temp);
        let container = root.join("container");
        fs::create_dir(&container).unwrap();
        let out = container.join("scale");
        generate(&out, ScaleProfile::Tiny, false).unwrap();
        let bound = bind_ready(&out).unwrap();
        let moved = root.join("moved-container");
        fs::rename(&container, &moved).unwrap();
        fs::create_dir(&container).unwrap();
        fs::write(container.join("victim"), b"keep-parent").unwrap();
        assert!(bound.recheck().is_err());
        assert_eq!(fs::read(container.join("victim")).unwrap(), b"keep-parent");

        let out = moved.join("scale");
        let bound = bind_ready(&out).unwrap();
        let scope = out.join(SCOPES[0].name);
        let displaced = out.join("displaced-scope");
        fs::rename(&scope, &displaced).unwrap();
        fs::create_dir(&scope).unwrap();
        fs::write(scope.join("victim"), b"keep-scope").unwrap();
        assert!(bound.recheck().is_err());
        assert_eq!(fs::read(scope.join("victim")).unwrap(), b"keep-scope");
    }

    #[test]
    fn same_content_immutable_replacements_are_rejected() {
        let temp = tempdir().unwrap();
        let root = rt(&temp);
        let out = root.join("scale");
        generate(&out, ScaleProfile::Tiny, false).unwrap();
        let bound = bind_ready(&out).unwrap();
        let source = out.join(SCOPES[0].name).join("document-0000.md");
        let bytes = fs::read(&source).unwrap();
        let replacement = root.join("same-source");
        fs::write(&replacement, &bytes).unwrap();
        fs::rename(&replacement, &source).unwrap();
        assert!(bound.recheck().is_err());

        generate(&out, ScaleProfile::Tiny, true).unwrap();
        let bound = bind_ready(&out).unwrap();
        let manifest = out.join(MANIFEST_NAME);
        let bytes = fs::read(&manifest).unwrap();
        let replacement = root.join("same-manifest");
        fs::write(&replacement, &bytes).unwrap();
        fs::rename(&replacement, &manifest).unwrap();
        assert!(bound.recheck().is_err());

        generate(&out, ScaleProfile::Tiny, true).unwrap();
        let bound = bind_ready(&out).unwrap();
        let owner = out.join(OWNER_MARKER_NAME);
        let bytes = fs::read(&owner).unwrap();
        let replacement = root.join("same-owner");
        fs::write(&replacement, &bytes).unwrap();
        fs::rename(&replacement, &owner).unwrap();
        assert!(bound.recheck().is_err());

        generate(&out, ScaleProfile::Tiny, true).unwrap();
        let bound = bind_ready(&out).unwrap();
        let lock = out.join(scale_spec::LOCK_NAME);
        let replacement = root.join("same-lock");
        fs::write(&replacement, fs::read(&lock).unwrap()).unwrap();
        fs::rename(&replacement, &lock).unwrap();
        assert!(bound.recheck().is_err());

        generate(&out, ScaleProfile::Tiny, true).unwrap();
        let bound = bind_ready(&out).unwrap();
        let scope = out.join(SCOPES[0].name);
        let replacement = root.join("same-scope");
        fs::create_dir(&replacement).unwrap();
        fs::write(
            replacement.join("document-0000.md"),
            fs::read(scope.join("document-0000.md")).unwrap(),
        )
        .unwrap();
        fs::rename(&scope, root.join("old-scope")).unwrap();
        fs::rename(&replacement, &scope).unwrap();
        assert!(bound.recheck().is_err());
    }

    #[test]
    fn dirty_partial_and_unowned_outputs_fail_closed() {
        let temp = tempdir().unwrap();
        let root = rt(&temp);
        let out = root.join("scale");
        fs::create_dir(&out).unwrap();
        assert!(generate(&out, ScaleProfile::Tiny, false).is_err());
        fs::remove_dir(&out).unwrap();
        fs::create_dir(&out).unwrap();
        fs::write(out.join("foreign"), b"x").unwrap();
        assert!(generate(&out, ScaleProfile::Tiny, false).is_err());
        fs::remove_dir_all(&out).unwrap();
        fs::create_dir(root.join(".kio-scale-v2.tmp-tiny")).unwrap();
        assert!(generate(&out, ScaleProfile::Tiny, false).is_err());
    }

    #[test]
    fn post_capture_reset_recovery_restores_current_ready_slot() {
        let temp = tempdir().unwrap();
        let out = rt(&temp).join("scale");
        generate(&out, ScaleProfile::Tiny, false).unwrap();
        let parent = bind_parent(&out).unwrap();
        let slot = reset_slot(ScaleProfile::Tiny);
        ensure_empty_slot(&parent.handle, slot, &out).unwrap();
        rename_exchange(&parent.handle, &parent.leaf, slot).unwrap();
        assert_eq!(
            generate(&out, ScaleProfile::Tiny, false).unwrap(),
            GenerateOutcome::ReadyNoop
        );
    }

    #[test]
    fn held_lock_rejects_named_lock_replacement() {
        let temp = tempdir().unwrap();
        let root = rt(&temp);
        let out = root.join("scale");
        generate(&out, ScaleProfile::Tiny, false).unwrap();
        let bound = bind_ready(&out).unwrap();
        let guard = bound.lock().unwrap();
        let replacement = root.join("replacement-lock");
        fs::write(
            &replacement,
            fs::read(out.join(scale_spec::LOCK_NAME)).unwrap(),
        )
        .unwrap();
        fs::rename(&replacement, out.join(scale_spec::LOCK_NAME)).unwrap();
        assert!(guard.recheck().is_err());
    }

    #[test]
    fn interrupted_reset_recovery_respects_live_candidate_writer_lock() {
        let temp = tempdir().unwrap();
        let out = rt(&temp).join("scale");
        generate(&out, ScaleProfile::Tiny, false).unwrap();
        let parent = bind_parent(&out).unwrap();
        let slot = reset_slot(ScaleProfile::Tiny);
        ensure_empty_slot(&parent.handle, slot, &out).unwrap();
        rename_exchange(&parent.handle, &parent.leaf, slot).unwrap();
        let candidate = open_dir(&parent.handle, slot, &out).unwrap();
        let guard = lock(&candidate, &out).unwrap();
        assert!(generate(&out, ScaleProfile::Tiny, false).is_err());
        drop(guard);
        assert_eq!(
            generate(&out, ScaleProfile::Tiny, false).unwrap(),
            GenerateOutcome::ReadyNoop
        );
    }
}
