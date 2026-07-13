//! Step 4 destination-only restore.

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::fs::{self, File};
use std::io::{BufRead, IsTerminal, Read, Seek, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use cap_primitives::fs as cap_fs;
use kcs_core::cas::{hash_bytes, is_hash, ObjectKind, ObjectStore, MAX_RAW_OBJECT_BYTES};
use kcs_core::dag::{CommitType, TreeEntry};
use kcs_core::history::HistoryReader;
use kcs_core::portable::portable_collision_key;
use kcs_core::purge::PurgeState;
use kcs_core::scope::{Repository, StoreLock};
use kcs_core::{ExitCode, KcsError, Result};
use serde_json::{json, Value};
use sha2::Digest;

use super::{RestoreArgs, ScopeTarget};

const MAX_POINTER_INPUT_BYTES: u64 = 1024 * 1024;
const MAX_RESTORE_TOTAL_BYTES: u64 = 4 * 1024 * 1024 * 1024;
const MAX_DESTINATION_ENTRIES: usize = 100_000;
const MAX_DESTINATION_NAME_BYTES: u64 = 16 * 1024 * 1024;

#[derive(Debug, Clone)]
struct RestoreItem {
    path_at_commit: String,
    raw_hash: String,
}

#[derive(Debug, Clone)]
struct RestoreSource {
    source_kind: &'static str,
    source_commit: String,
    target: ScopeTarget,
    files: Vec<RestoreItem>,
}

#[derive(Debug, Clone)]
struct PreflightFile {
    source: RestoreItem,
    destination: PathBuf,
    size_bytes: u64,
    overwritten: bool,
}

#[derive(Debug)]
struct StagedFile {
    preflight: PreflightFile,
    temp: OsString,
    temp_file: File,
}

#[derive(Debug)]
struct DestinationDir {
    path: PathBuf,
    handle: File,
}

pub(super) fn run(args: RestoreArgs) -> Result<Value> {
    if args.yes && !args.force {
        return Err(KcsError::invalid_usage(
            "restore --yes is valid only together with --force",
        ));
    }

    let source = resolve_source(&args.source)?;
    let destination = validate_destination(&args.to, &source.target)?;
    let _initial_preflight = preflight(&source, &destination, args.force)?;

    if args.force && !args.yes {
        confirm_force()?;
    }

    let destination_dir = open_destination_dir(&destination, true)?;
    // Capability-directory handles close destination path races but do not
    // serialize source authorization against purge. Restore intentionally stays
    // off `.kcs/.lock`; instead it shares this narrow publication lock with
    // purge, acquiring it only after confirmation and destination opening. Purge
    // takes store -> publication, while restore takes publication only, so no
    // reverse lock order exists. Keep it across the authoritative recheck,
    // private staging, and every final publication.
    let _purge_publication_lock = StoreLock::acquire_path(
        super::purge::purge_publication_lock_path(&source.target.kcs_dir),
    )?;
    // The directory may have appeared between the first preflight and creation.
    // Re-run the complete leaf check before staging any content.
    let preflight_files = preflight_in_dir(&source, &destination_dir, args.force)?;
    let staged = stage_all(&source, preflight_files, &destination_dir)?;
    publish_all(&source, &destination_dir, staged)
}

fn resolve_source(operand: &str) -> Result<RestoreSource> {
    if operand == "-" || operand.starts_with("kcs://") {
        return resolve_evidence_source(operand);
    }
    if operand.trim_start().starts_with('{') {
        return resolve_evidence_source(operand.trim());
    }
    resolve_local_source(operand)
}

fn resolve_evidence_source(operand: &str) -> Result<RestoreSource> {
    let text = read_pointer_operand(operand)?;
    let pointer = super::parse_pointer_text(&text)?;
    let target = super::resolve_scope_target(&pointer.scope_id, pointer.scope_path.as_deref())?;
    let repo = Repository::open(&target.repo_root)?;
    super::validate_repo_tool_lock(&repo)?;

    let commit = match repo.read_commit(&pointer.commit) {
        Ok(commit) => commit,
        Err(error) if super::is_store_not_found(&error) => {
            return Err(super::unresolvable_commit_pointer_error(&pointer));
        }
        Err(error) => return Err(error),
    };
    reject_purged_commit(&pointer.commit, commit.commit_type)?;
    if pointer
        .tree
        .as_deref()
        .is_some_and(|tree| tree != commit.tree)
    {
        return Err(super::invalid_pointer_identity_error(&pointer));
    }
    let tree = match repo.read_tree(&commit.tree) {
        Ok(tree) => tree,
        Err(error) if super::is_store_not_found(&error) => {
            return Err(KcsError::commit_shallow(
                "restore requires the complete evidence commit tree; the tree object is missing or shallow",
                pointer.commit.clone(),
            ));
        }
        Err(error) => return Err(error),
    };
    // Dead-source visibility wins over derivative availability/corruption.
    // The evidence pointer's exact raw identity is known before any normalized
    // chunk is read, so apply the purge gates at this point.
    check_purge_state(&target, &pointer.raw_hash)?;
    let store = ObjectStore::new(&target.kcs_dir);
    match store.inspect_object(ObjectKind::Raw, &pointer.raw_hash) {
        Ok(_) => {}
        Err(error) if super::is_store_not_found(&error) => {
            return Err(missing_live_raw_error(&target, &pointer.raw_hash));
        }
        Err(error) => return Err(error),
    }
    let chunk = match store.read_chunk(&pointer.chunk_hash) {
        Ok(chunk) => chunk,
        Err(error) if super::is_store_not_found(&error) => {
            return Err(KcsError::new(
                "KCS-E-EVIDENCE-RETARGET-REQUIRED-001",
                "chunk not materialized for this tool_profile_hash; retarget required",
                json!({
                    "chunk_hash": pointer.chunk_hash,
                    "tool_profile_hash": pointer.tool_profile_hash,
                    "raw_hash": pointer.raw_hash,
                }),
                ExitCode::IncompatibleProfile,
            ));
        }
        Err(error) => return Err(error),
    };
    if chunk.raw_hash != pointer.raw_hash || chunk.tool_profile_hash != pointer.tool_profile_hash {
        return Err(super::invalid_pointer_identity_error(&pointer));
    }
    let mut matching_entries = tree.entries.iter().filter(|entry| {
        entry.raw_hash == pointer.raw_hash
            && entry.normalize.as_ref().is_some_and(|normalize| {
                normalize.tool_profile_hash == pointer.tool_profile_hash
                    && normalize.gen == chunk.gen
            })
    });
    let entry = match pointer.path_at_commit.as_deref() {
        Some(path) => matching_entries
            .find(|entry| entry.path == path)
            .ok_or_else(|| super::invalid_pointer_identity_error(&pointer))?,
        None => matching_entries
            .next()
            .ok_or_else(|| super::invalid_pointer_identity_error(&pointer))?,
    };

    Ok(RestoreSource {
        source_kind: "evidence",
        source_commit: pointer.commit,
        target,
        files: vec![RestoreItem {
            path_at_commit: entry.path.clone(),
            raw_hash: entry.raw_hash.clone(),
        }],
    })
}

fn read_pointer_operand(operand: &str) -> Result<String> {
    if operand != "-" {
        if operand.len() as u64 > MAX_POINTER_INPUT_BYTES {
            return Err(KcsError::invalid_usage(
                "evidence pointer input exceeds the 1 MiB limit",
            ));
        }
        return Ok(operand.to_owned());
    }

    let stdin = std::io::stdin();
    let mut input = Vec::new();
    stdin
        .lock()
        .take(MAX_POINTER_INPUT_BYTES + 1)
        .read_to_end(&mut input)
        .map_err(|error| KcsError::io(error.to_string(), "stdin"))?;
    if input.len() as u64 > MAX_POINTER_INPUT_BYTES {
        return Err(KcsError::invalid_usage(
            "evidence pointer input exceeds the 1 MiB limit",
        ));
    }
    String::from_utf8(input)
        .map(|input| input.trim().to_owned())
        .map_err(|_| KcsError::invalid_usage("evidence pointer input must be UTF-8"))
}

fn resolve_local_source(operand: &str) -> Result<RestoreSource> {
    let repo = Repository::open_current()?;
    super::validate_repo_tool_lock(&repo)?;
    let target = super::scope_target(repo.root())?;

    if operand == "HEAD" {
        let commit_hash = repo
            .head_commit_hash()?
            .ok_or_else(|| restore_source_not_found("HEAD"))?;
        repo.read_commit(&commit_hash).map_err(|error| {
            if super::is_store_not_found(&error) {
                restore_source_not_found(&commit_hash)
            } else {
                error
            }
        })?;
        return resolve_commit_source(target, commit_hash);
    }

    if is_hash(operand) {
        let store = ObjectStore::new(repo.kcs_dir());
        match store.inspect_object(ObjectKind::Commit, operand) {
            Ok(_) => return resolve_commit_source(target, operand.to_owned()),
            Err(error) if super::is_store_not_found(&error) => {}
            Err(error) => return Err(error),
        }
        if store.inspect_object(ObjectKind::Raw, operand).is_ok() {
            return Err(KcsError::invalid_usage(
                "raw-hash shorthand is not a restore source; use evidence, path, or commit",
            ));
        }
        return Err(restore_source_not_found(operand));
    }

    match repo.resolve_commit(operand) {
        Ok(commit_hash) => resolve_commit_source(target, commit_hash),
        Err(error) if super::is_store_not_found(&error) => resolve_path_source(target, operand),
        Err(error) => Err(error),
    }
}

fn resolve_commit_source(target: ScopeTarget, commit_hash: String) -> Result<RestoreSource> {
    let reader = HistoryReader::new(&target.kcs_dir);
    let snapshot = reader.snapshot(&commit_hash)?;
    reject_purged_commit(&commit_hash, snapshot.commit.commit_type)?;
    let files = snapshot
        .tree
        .entries
        .iter()
        .map(|entry| RestoreItem {
            path_at_commit: entry.path.clone(),
            raw_hash: entry.raw_hash.clone(),
        })
        .collect();
    Ok(RestoreSource {
        source_kind: "commit",
        source_commit: commit_hash,
        target,
        files,
    })
}

fn resolve_path_source(target: ScopeTarget, path: &str) -> Result<RestoreSource> {
    validate_restore_name(path, &hash_bytes(b"restore-path-validation"))?;
    let repo = Repository::open(&target.repo_root)?;
    let head = repo
        .head_commit_hash()?
        .ok_or_else(|| restore_source_not_found(path))?;
    let history = HistoryReader::new(&target.kcs_dir).first_parent(&head)?;
    let binding = history
        .newest_binding_for_path(path)
        .ok_or_else(|| restore_source_not_found(path))?;
    let node = history
        .node(&binding.commit_hash)
        .expect("binding commit belongs to first-parent history");
    reject_purged_commit(&binding.commit_hash, node.commit.commit_type)?;
    Ok(RestoreSource {
        source_kind: "path",
        source_commit: binding.commit_hash,
        target,
        files: vec![RestoreItem {
            path_at_commit: binding.binding.path,
            raw_hash: binding.binding.raw_hash,
        }],
    })
}

fn reject_purged_commit(commit_hash: &str, commit_type: CommitType) -> Result<()> {
    if commit_type == CommitType::Purged {
        return Err(KcsError::new(
            "KCS-E-PURGE-NOT-FOUND-001",
            "restore source is a purged commit",
            json!({ "source_commit": commit_hash }),
            ExitCode::PermanentFailure,
        ));
    }
    Ok(())
}

fn restore_source_not_found(source: &str) -> KcsError {
    KcsError::new(
        "KCS-E-COMMIT-RESTORE-SOURCE-NOT-FOUND-001",
        "restore source is not reachable",
        json!({ "source": source }),
        ExitCode::PermanentFailure,
    )
}

fn preflight(
    source: &RestoreSource,
    destination: &Path,
    force: bool,
) -> Result<Vec<PreflightFile>> {
    validate_source_names(&source.files)?;
    let existing = if destination.exists() {
        scan_destination(destination)?
    } else {
        BTreeMap::new()
    };
    let store = ObjectStore::new(&source.target.kcs_dir);
    let mut total_bytes = 0_u64;
    let mut verified_raws = BTreeMap::<String, u64>::new();
    let mut files = Vec::with_capacity(source.files.len());

    for item in &source.files {
        check_purge_state(&source.target, &item.raw_hash)?;
        let size_bytes = match verified_raws.get(&item.raw_hash) {
            Some(size) => *size,
            None => match store.inspect_object(ObjectKind::Raw, &item.raw_hash) {
                Ok(metadata) => {
                    verified_raws.insert(item.raw_hash.clone(), metadata.size_bytes);
                    metadata.size_bytes
                }
                Err(error) if super::is_store_not_found(&error) => {
                    return Err(missing_live_raw_error(&source.target, &item.raw_hash));
                }
                Err(error) => return Err(error),
            },
        };
        total_bytes = total_bytes.saturating_add(size_bytes);
        if total_bytes > MAX_RESTORE_TOTAL_BYTES {
            return Err(KcsError::new(
                "KCS-E-COMMIT-RESTORE-LIMIT-001",
                "restore source bytes exceed the 4 GiB aggregate limit",
                json!({
                    "max_bytes": MAX_RESTORE_TOTAL_BYTES,
                    "attempted_bytes": total_bytes,
                }),
                ExitCode::PermanentFailure,
            ));
        }

        let collision_key = portable_collision_key(&item.path_at_commit);
        let existing_names = existing.get(&collision_key);
        if existing_names
            .is_some_and(|names| names.len() != 1 || names.first() != Some(&item.path_at_commit))
        {
            return Err(unsafe_restore_error(
                destination,
                "destination contains a case/normalization-colliding leaf",
            ));
        }
        let target = destination.join(&item.path_at_commit);
        let overwritten = match fs::symlink_metadata(&target) {
            Ok(_) => {
                validate_replaceable_file(&target)?;
                if !force {
                    return Err(KcsError::new(
                        "KCS-E-COMMIT-RESTORE-CONFLICT-001",
                        "destination file already exists; use --force to replace it",
                        json!({ "path": target }),
                        ExitCode::Failure,
                    ));
                }
                true
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
            Err(error) => {
                return Err(KcsError::io(
                    error.to_string(),
                    target.display().to_string(),
                ));
            }
        };
        files.push(PreflightFile {
            source: item.clone(),
            destination: target,
            size_bytes,
            overwritten,
        });
    }
    Ok(files)
}

fn preflight_in_dir(
    source: &RestoreSource,
    destination: &DestinationDir,
    force: bool,
) -> Result<Vec<PreflightFile>> {
    validate_source_names(&source.files)?;
    let existing = scan_destination_handle(destination)?;
    let store = ObjectStore::new(&source.target.kcs_dir);
    let mut total_bytes = 0_u64;
    let mut verified_raws = BTreeMap::<String, u64>::new();
    let mut files = Vec::with_capacity(source.files.len());

    for item in &source.files {
        check_purge_state(&source.target, &item.raw_hash)?;
        let size_bytes = match verified_raws.get(&item.raw_hash) {
            Some(size) => *size,
            None => match store.inspect_object(ObjectKind::Raw, &item.raw_hash) {
                Ok(metadata) => {
                    verified_raws.insert(item.raw_hash.clone(), metadata.size_bytes);
                    metadata.size_bytes
                }
                Err(error) if super::is_store_not_found(&error) => {
                    return Err(missing_live_raw_error(&source.target, &item.raw_hash));
                }
                Err(error) => return Err(error),
            },
        };
        total_bytes = total_bytes.saturating_add(size_bytes);
        if total_bytes > MAX_RESTORE_TOTAL_BYTES {
            return Err(KcsError::new(
                "KCS-E-COMMIT-RESTORE-LIMIT-001",
                "restore source bytes exceed the 4 GiB aggregate limit",
                json!({
                    "max_bytes": MAX_RESTORE_TOTAL_BYTES,
                    "attempted_bytes": total_bytes,
                }),
                ExitCode::PermanentFailure,
            ));
        }

        let collision_key = portable_collision_key(&item.path_at_commit);
        let existing_names = existing.get(&collision_key);
        if existing_names
            .is_some_and(|names| names.len() != 1 || names.first() != Some(&item.path_at_commit))
        {
            return Err(unsafe_restore_error(
                &destination.path,
                "destination contains a case/normalization-colliding leaf",
            ));
        }
        let target = destination.path.join(&item.path_at_commit);
        let overwritten = match cap_fs::stat(
            &destination.handle,
            Path::new(&item.path_at_commit),
            cap_fs::FollowSymlinks::No,
        ) {
            Ok(metadata) => {
                validate_replaceable_metadata(&target, &metadata)?;
                if !force {
                    return Err(KcsError::new(
                        "KCS-E-COMMIT-RESTORE-CONFLICT-001",
                        "destination file already exists; use --force to replace it",
                        json!({ "path": target }),
                        ExitCode::Failure,
                    ));
                }
                true
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
            Err(error) => {
                return Err(KcsError::io(
                    error.to_string(),
                    target.display().to_string(),
                ));
            }
        };
        files.push(PreflightFile {
            source: item.clone(),
            destination: target,
            size_bytes,
            overwritten,
        });
    }
    Ok(files)
}

fn validate_source_names(files: &[RestoreItem]) -> Result<()> {
    let mut collision_keys = BTreeSet::new();
    for item in files {
        validate_restore_name(&item.path_at_commit, &item.raw_hash)?;
        if !collision_keys.insert(portable_collision_key(&item.path_at_commit)) {
            return Err(KcsError::new(
                "KCS-E-COMMIT-RESTORE-UNSAFE-001",
                "restore source contains case/normalization-colliding paths",
                json!({ "path_at_commit": item.path_at_commit }),
                ExitCode::Failure,
            ));
        }
    }
    Ok(())
}

fn validate_restore_name(path: &str, raw_hash: &str) -> Result<()> {
    let entry = TreeEntry {
        path: path.to_owned(),
        entry_type: "file".to_owned(),
        raw_hash: raw_hash.to_owned(),
        normalize: None,
    };
    entry.validate_materialization_path().map_err(|_| {
        KcsError::new(
            "KCS-E-COMMIT-RESTORE-UNSAFE-001",
            "historical path cannot be materialized safely on this platform",
            json!({ "path_at_commit": path }),
            ExitCode::Failure,
        )
    })
}

fn validate_destination(input: &Path, target: &ScopeTarget) -> Result<PathBuf> {
    let destination = normalize_absolute(input)?;
    verify_destination_input_chain(&destination, target)?;
    let destination = effective_destination(&destination)?;
    verify_existing_directory_chain(&destination)?;
    let scope_root = target
        .repo_root
        .canonicalize()
        .map_err(|error| KcsError::io(error.to_string(), target.repo_root.display().to_string()))?;
    let kcs_dir = target
        .kcs_dir
        .canonicalize()
        .map_err(|error| KcsError::io(error.to_string(), target.kcs_dir.display().to_string()))?;
    if destination == scope_root || destination == kcs_dir || destination.starts_with(&kcs_dir) {
        return Err(unsafe_restore_error(
            &destination,
            "restore destination must not be the scope root, .kcs, or a .kcs descendant",
        ));
    }
    Ok(destination)
}

/// macOS commonly exposes a canonical scope under `/private/var/...` through
/// the system `/var` alias. When an existing ancestor resolves exactly to the
/// already-validated source scope root, use that real directory as the trust
/// anchor and reject reparse components below it. Destinations without such an
/// anchor retain the strict full-chain check.
fn verify_destination_input_chain(path: &Path, target: &ScopeTarget) -> Result<()> {
    let anchor = path.ancestors().find(|ancestor| {
        fs::symlink_metadata(ancestor).is_ok()
            && ancestor
                .canonicalize()
                .is_ok_and(|canonical| canonical == target.repo_root)
    });
    let Some(anchor) = anchor else {
        return verify_existing_directory_chain(path);
    };
    validate_real_directory(anchor)?;
    let relative = path.strip_prefix(anchor).map_err(|_| {
        unsafe_restore_error(
            path,
            "destination cannot be made relative to its scope anchor",
        )
    })?;
    let mut current = anchor.to_path_buf();
    let mut missing = false;
    for component in relative.components() {
        let Component::Normal(component) = component else {
            return Err(unsafe_restore_error(
                path,
                "destination contains a non-local component below its scope anchor",
            ));
        };
        current.push(component);
        match fs::symlink_metadata(&current) {
            Ok(_) if missing => {
                return Err(unsafe_restore_error(
                    &current,
                    "destination ancestry changed while it was inspected",
                ));
            }
            Ok(_) => validate_real_directory(&current)?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => missing = true,
            Err(error) => {
                return Err(KcsError::io(
                    error.to_string(),
                    current.display().to_string(),
                ));
            }
        }
    }
    Ok(())
}

fn normalize_absolute(path: &Path) -> Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| KcsError::io(error.to_string(), "."))?
            .join(path)
    };
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                let _ = normalized.pop();
            }
            Component::Normal(value) => normalized.push(value),
        }
    }
    if !normalized.is_absolute() {
        return Err(KcsError::invalid_usage(
            "restore destination must resolve to an absolute path",
        ));
    }
    Ok(normalized)
}

fn verify_existing_directory_chain(path: &Path) -> Result<()> {
    let mut current = PathBuf::new();
    let mut missing = false;
    for component in path.components() {
        current.push(component.as_os_str());
        if matches!(component, Component::Prefix(_)) {
            continue;
        }
        match fs::symlink_metadata(&current) {
            Ok(_) if is_platform_root_alias(&current) => {}
            Ok(_) if missing => {
                return Err(unsafe_restore_error(
                    &current,
                    "destination ancestry changed while it was inspected",
                ));
            }
            Ok(_) => validate_real_directory(&current)?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => missing = true,
            Err(error) => {
                return Err(KcsError::io(
                    error.to_string(),
                    current.display().to_string(),
                ));
            }
        }
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn is_platform_root_alias(path: &Path) -> bool {
    matches!(path.to_str(), Some("/var" | "/tmp" | "/etc"))
        && path
            .canonicalize()
            .is_ok_and(|canonical| canonical.starts_with("/private"))
}

#[cfg(not(target_os = "macos"))]
fn is_platform_root_alias(_path: &Path) -> bool {
    false
}

fn effective_destination(path: &Path) -> Result<PathBuf> {
    let mut existing = path.to_path_buf();
    let mut suffix = Vec::<OsString>::new();
    loop {
        match fs::symlink_metadata(&existing) {
            Ok(_) => break,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                let leaf = existing.file_name().ok_or_else(|| {
                    unsafe_restore_error(path, "destination has no existing root")
                })?;
                suffix.push(leaf.to_os_string());
                if !existing.pop() {
                    return Err(unsafe_restore_error(
                        path,
                        "destination has no existing root",
                    ));
                }
            }
            Err(error) => {
                return Err(KcsError::io(
                    error.to_string(),
                    existing.display().to_string(),
                ));
            }
        }
    }
    let mut canonical = existing
        .canonicalize()
        .map_err(|error| KcsError::io(error.to_string(), existing.display().to_string()))?;
    for component in suffix.into_iter().rev() {
        canonical.push(component);
    }
    Ok(canonical)
}

fn open_destination_dir(path: &Path, create_missing: bool) -> Result<DestinationDir> {
    let mut root = PathBuf::new();
    let mut descendants = Vec::<OsString>::new();
    let mut saw_root = false;
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => root.push(prefix.as_os_str()),
            Component::RootDir => {
                root.push(component.as_os_str());
                saw_root = true;
            }
            Component::Normal(name) if saw_root => descendants.push(name.to_os_string()),
            Component::CurDir => {}
            Component::ParentDir | Component::Normal(_) => {
                return Err(unsafe_restore_error(
                    path,
                    "restore destination does not have a stable filesystem root",
                ));
            }
        }
    }
    if !saw_root {
        return Err(unsafe_restore_error(
            path,
            "restore destination does not have a stable filesystem root",
        ));
    }

    let mut current = cap_fs::open_ambient_dir(&root, cap_primitives::ambient_authority())
        .map_err(|error| KcsError::io(error.to_string(), root.display().to_string()))?;
    let mut display = root;
    for component in descendants {
        display.push(&component);
        match cap_fs::open_dir_nofollow(&current, Path::new(&component)) {
            Ok(next) => current = next,
            Err(error) if create_missing && error.kind() == std::io::ErrorKind::NotFound => {
                let mut options = cap_fs::DirOptions::new();
                #[cfg(unix)]
                {
                    use cap_fs::DirBuilderExt;
                    options.mode(0o700);
                }
                match cap_fs::create_dir(&current, Path::new(&component), &options) {
                    Ok(()) => {}
                    Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
                    Err(error) => {
                        return Err(KcsError::io(
                            error.to_string(),
                            display.display().to_string(),
                        ));
                    }
                }
                current =
                    cap_fs::open_dir_nofollow(&current, Path::new(&component)).map_err(|_| {
                        unsafe_restore_error(
                            &display,
                            "destination ancestor is not a real non-reparse directory",
                        )
                    })?;
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                return Err(KcsError::io(
                    error.to_string(),
                    display.display().to_string(),
                ));
            }
            Err(_) => {
                return Err(unsafe_restore_error(
                    &display,
                    "destination ancestor is not a real non-reparse directory",
                ));
            }
        }
    }
    let metadata = current
        .metadata()
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    if !metadata.is_dir() {
        return Err(unsafe_restore_error(
            path,
            "destination ancestor is not a real non-reparse directory",
        ));
    }
    Ok(DestinationDir {
        path: path.to_path_buf(),
        handle: current,
    })
}

fn validate_real_directory(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(unsafe_restore_error(
            path,
            "destination ancestor is not a real non-reparse directory",
        ));
    }
    #[cfg(windows)]
    if !kcs_core::cas::windows_directory_is_real(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?
    {
        return Err(unsafe_restore_error(
            path,
            "destination ancestor is a reparse point",
        ));
    }
    Ok(())
}

fn scan_destination(path: &Path) -> Result<BTreeMap<String, Vec<String>>> {
    validate_real_directory(path)?;
    let mut entries = BTreeMap::new();
    let mut count = 0_usize;
    let mut name_bytes = 0_u64;
    for entry in fs::read_dir(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?
    {
        let entry =
            entry.map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
        count += 1;
        if count > MAX_DESTINATION_ENTRIES {
            return Err(unsafe_restore_error(
                path,
                "destination directory exceeds the 100000-entry inspection limit",
            ));
        }
        let name = entry.file_name();
        name_bytes = name_bytes.saturating_add(name.as_encoded_bytes().len() as u64);
        if name_bytes > MAX_DESTINATION_NAME_BYTES {
            return Err(unsafe_restore_error(
                path,
                "destination names exceed the 16 MiB inspection limit",
            ));
        }
        if let Some(name) = name.to_str() {
            entries
                .entry(portable_collision_key(name))
                .or_insert_with(Vec::new)
                .push(name.to_owned());
        }
    }
    Ok(entries)
}

fn scan_destination_handle(destination: &DestinationDir) -> Result<BTreeMap<String, Vec<String>>> {
    let mut entries = BTreeMap::new();
    let mut count = 0_usize;
    let mut name_bytes = 0_u64;
    for entry in cap_fs::read_base_dir(&destination.handle)
        .map_err(|error| KcsError::io(error.to_string(), destination.path.display().to_string()))?
    {
        let entry = entry.map_err(|error| {
            KcsError::io(error.to_string(), destination.path.display().to_string())
        })?;
        count += 1;
        if count > MAX_DESTINATION_ENTRIES {
            return Err(unsafe_restore_error(
                &destination.path,
                "destination directory exceeds the 100000-entry inspection limit",
            ));
        }
        let name = entry.file_name();
        name_bytes = name_bytes.saturating_add(name.as_encoded_bytes().len() as u64);
        if name_bytes > MAX_DESTINATION_NAME_BYTES {
            return Err(unsafe_restore_error(
                &destination.path,
                "destination names exceed the 16 MiB inspection limit",
            ));
        }
        if let Some(name) = name.to_str() {
            entries
                .entry(portable_collision_key(name))
                .or_insert_with(Vec::new)
                .push(name.to_owned());
        }
    }
    Ok(entries)
}

fn validate_replaceable_file(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(unsafe_restore_error(
            path,
            "restore may replace only a real regular file",
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.nlink() != 1 {
            return Err(unsafe_restore_error(
                path,
                "restore refuses a hard-linked destination file",
            ));
        }
    }
    #[cfg(windows)]
    if !kcs_core::cas::windows_regular_file_is_safe(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?
    {
        return Err(unsafe_restore_error(
            path,
            "restore refuses a reparse or hard-linked destination file",
        ));
    }
    Ok(())
}

fn validate_replaceable_metadata(path: &Path, metadata: &cap_fs::Metadata) -> Result<()> {
    if !metadata.is_file() || metadata.is_symlink() {
        return Err(unsafe_restore_error(
            path,
            "restore may replace only a real regular file",
        ));
    }
    #[cfg(unix)]
    {
        use cap_fs::MetadataExt;
        if metadata.nlink() != 1 {
            return Err(unsafe_restore_error(
                path,
                "restore refuses a hard-linked destination file",
            ));
        }
    }
    #[cfg(windows)]
    {
        use cap_fs::_WindowsByHandle;
        use windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT;

        if metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
            || metadata.number_of_links() != Some(1)
        {
            return Err(unsafe_restore_error(
                path,
                "restore refuses a reparse or hard-linked destination file",
            ));
        }
    }
    Ok(())
}

fn unsafe_restore_error(path: &Path, message: &str) -> KcsError {
    KcsError::new(
        "KCS-E-COMMIT-RESTORE-UNSAFE-001",
        message,
        json!({ "path": path }),
        ExitCode::Failure,
    )
}

fn confirm_force() -> Result<()> {
    if !std::io::stdin().is_terminal() || !std::io::stderr().is_terminal() {
        return Err(confirmation_rejected(
            "restore --force requires --yes in non-interactive mode",
        ));
    }
    eprint!("Restore may replace existing files. Continue? [y/N] ");
    std::io::stderr()
        .flush()
        .map_err(|error| KcsError::io(error.to_string(), "stderr"))?;
    let stdin = std::io::stdin();
    let mut response = String::new();
    stdin
        .lock()
        .take(64)
        .read_line(&mut response)
        .map_err(|error| KcsError::io(error.to_string(), "stdin"))?;
    if matches!(response.trim().to_ascii_lowercase().as_str(), "y" | "yes") {
        Ok(())
    } else {
        Err(confirmation_rejected("restore confirmation was rejected"))
    }
}

fn confirmation_rejected(message: &str) -> KcsError {
    KcsError::new(
        "KCS-E-CONFIRM-REJECTED-001",
        message,
        json!({}),
        ExitCode::ConfirmationRejected,
    )
}

fn missing_live_raw_error(target: &ScopeTarget, raw_hash: &str) -> KcsError {
    KcsError::new(
        "KCS-E-PURGE-NOT-FOUND-001",
        "restore source is no longer available",
        json!({
            "raw_hash": raw_hash,
            "scope_path": target.kcs_dir,
        }),
        ExitCode::PermanentFailure,
    )
}

fn check_purge_state(target: &ScopeTarget, raw_hash: &str) -> Result<()> {
    let state = PurgeState::new(&target.kcs_dir);
    if let Some(record) = state.read_tombstone(raw_hash)? {
        let mut tombstone =
            serde_json::to_value(record).map_err(|error| KcsError::schema(error.to_string()))?;
        tombstone
            .as_object_mut()
            .expect("tombstone record serializes as an object")
            .insert(
                "scope_path".to_owned(),
                json!(target.kcs_dir.display().to_string()),
            );
        return Err(super::tombstone_error(tombstone));
    }
    if state.barrier_blocks(raw_hash)? {
        return Err(KcsError::new(
            "KCS-E-PURGE-NOT-FOUND-001",
            "restore source is hidden by an in-progress purge barrier",
            json!({
                "raw_hash": raw_hash,
                "scope_path": target.kcs_dir,
                "purge_state": "in_progress",
            }),
            ExitCode::PermanentFailure,
        ));
    }
    Ok(())
}

fn stage_all(
    source: &RestoreSource,
    files: Vec<PreflightFile>,
    destination: &DestinationDir,
) -> Result<Vec<StagedFile>> {
    let store = ObjectStore::new(&source.target.kcs_dir);
    let mut staged = Vec::with_capacity(files.len());
    let result = (|| -> Result<()> {
        for file in files {
            validate_destination_handle(destination)?;
            check_purge_state(&source.target, &file.source.raw_hash)?;
            let (temp, mut output) = create_private_temp(destination)?;
            let copied =
                match store.copy_object_to(ObjectKind::Raw, &file.source.raw_hash, &mut output) {
                    Ok(metadata) => metadata,
                    Err(error) if super::is_store_not_found(&error) => {
                        cleanup_one(destination, &temp);
                        return Err(missing_live_raw_error(
                            &source.target,
                            &file.source.raw_hash,
                        ));
                    }
                    Err(error) => {
                        cleanup_one(destination, &temp);
                        return Err(error);
                    }
                };
            if copied.size_bytes != file.size_bytes {
                cleanup_one(destination, &temp);
                return Err(KcsError::new(
                    "KCS-E-STORE-CORRUPT-001",
                    "raw object changed after restore preflight",
                    json!({ "raw_hash": file.source.raw_hash }),
                    ExitCode::PermanentFailure,
                ));
            }
            if let Err(error) = output.sync_all() {
                cleanup_one(destination, &temp);
                return Err(KcsError::io(
                    error.to_string(),
                    destination.path.join(&temp).display().to_string(),
                ));
            }
            staged.push(StagedFile {
                preflight: file,
                temp,
                temp_file: output,
            });
        }
        Ok(())
    })();
    if let Err(error) = result {
        cleanup_staged(destination, &staged);
        return Err(error);
    }

    // A race that creates a conflicting case variant or changes a target after
    // staging is rejected before the first final publication.
    let rescanned = match preflight_in_dir(source, destination, true) {
        Ok(rescanned) => rescanned,
        Err(error) => {
            cleanup_staged(destination, &staged);
            return Err(error);
        }
    };
    if rescanned.len() != staged.len()
        || rescanned.iter().zip(&staged).any(|(fresh, staged)| {
            fresh.destination != staged.preflight.destination
                || fresh.overwritten != staged.preflight.overwritten
                || fresh.size_bytes != staged.preflight.size_bytes
        })
    {
        cleanup_staged(destination, &staged);
        return Err(unsafe_restore_error(
            &destination.path,
            "destination changed after restore staging",
        ));
    }
    Ok(staged)
}

fn create_private_temp(destination: &DestinationDir) -> Result<(OsString, File)> {
    static SEQUENCE: AtomicU64 = AtomicU64::new(0);
    for attempt in 0..32_u8 {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or_default();
        let sequence = SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let name = OsString::from(format!(
            ".kcs-restore-tmp-{}-{nanos}-{sequence}-{attempt}",
            std::process::id()
        ));
        let mut options = cap_fs::OpenOptions::new();
        options.read(true).write(true).create_new(true);
        #[cfg(unix)]
        {
            use cap_fs::OpenOptionsExt;
            options.mode(0o600);
        }
        #[cfg(windows)]
        {
            use cap_fs::OpenOptionsExt;
            use windows_sys::Win32::Foundation::GENERIC_READ;
            use windows_sys::Win32::Storage::FileSystem::{DELETE, FILE_GENERIC_WRITE};
            options.access_mode(GENERIC_READ | FILE_GENERIC_WRITE | DELETE);
        }
        match cap_fs::open(&destination.handle, Path::new(&name), &options) {
            Ok(file) => return Ok((name, file)),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(KcsError::io(
                    error.to_string(),
                    destination.path.join(&name).display().to_string(),
                ));
            }
        }
    }
    Err(KcsError::io(
        "could not allocate a unique restore staging file",
        destination.path.display().to_string(),
    ))
}

fn publish_all(
    source: &RestoreSource,
    destination: &DestinationDir,
    staged: Vec<StagedFile>,
) -> Result<Value> {
    let mut published = Vec::new();
    let mut overwritten_count = 0_u64;
    let mut remaining = staged.into_iter();
    while let Some(file) = remaining.next() {
        if let Err(error) = check_purge_state(&source.target, &file.preflight.source.raw_hash) {
            cleanup_one(destination, &file.temp);
            for pending in remaining {
                cleanup_one(destination, &pending.temp);
            }
            if published.is_empty() {
                return Err(error);
            }
            return Ok(partial_output(
                source,
                &destination.path,
                published,
                overwritten_count,
                &file.preflight,
                error,
            ));
        }
        match publish_one(destination, &file) {
            Ok(()) => {
                overwritten_count += u64::from(file.preflight.overwritten);
                published.push(file.preflight);
            }
            Err((error, destination_may_have_changed)) => {
                cleanup_one(destination, &file.temp);
                for pending in remaining {
                    cleanup_one(destination, &pending.temp);
                }
                if published.is_empty() && !destination_may_have_changed {
                    return Err(error);
                }
                return Ok(partial_output(
                    source,
                    &destination.path,
                    published,
                    overwritten_count,
                    &file.preflight,
                    error,
                ));
            }
        }
    }
    if let Err(error) = sync_directory_handle(destination) {
        if published.is_empty() {
            return Err(error);
        }
        let failed = published
            .last()
            .expect("non-empty publications checked above")
            .clone();
        return Ok(partial_output(
            source,
            &destination.path,
            published,
            overwritten_count,
            &failed,
            error,
        ));
    }
    Ok(success_output(
        source,
        &destination.path,
        published,
        overwritten_count,
    ))
}

fn publish_one(
    destination: &DestinationDir,
    file: &StagedFile,
) -> std::result::Result<(), (KcsError, bool)> {
    verify_open_file(
        &file.temp_file,
        &destination.path.join(&file.temp),
        &file.preflight.source.raw_hash,
        file.preflight.size_bytes,
    )
    .map_err(|error| (error, false))?;
    if file.preflight.overwritten {
        let metadata = cap_fs::stat(
            &destination.handle,
            Path::new(&file.preflight.source.path_at_commit),
            cap_fs::FollowSymlinks::No,
        )
        .map_err(|error| {
            (
                KcsError::io(
                    error.to_string(),
                    file.preflight.destination.display().to_string(),
                ),
                false,
            )
        })?;
        validate_replaceable_metadata(&file.preflight.destination, &metadata)
            .map_err(|error| (error, false))?;
        atomic_replace_handle(
            destination,
            &file.temp,
            &file.temp_file,
            Path::new(&file.preflight.source.path_at_commit),
        )
        .map_err(|error| (error, false))?;
    } else {
        match cap_fs::hard_link(
            &destination.handle,
            Path::new(&file.temp),
            &destination.handle,
            Path::new(&file.preflight.source.path_at_commit),
        ) {
            Ok(()) => {
                cap_fs::remove_file(&destination.handle, Path::new(&file.temp)).map_err(
                    |error| {
                        (
                            KcsError::io(
                                error.to_string(),
                                destination.path.join(&file.temp).display().to_string(),
                            ),
                            true,
                        )
                    },
                )?;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                return Err((
                    KcsError::new(
                        "KCS-E-COMMIT-RESTORE-CONFLICT-001",
                        "destination file appeared during restore publication",
                        json!({ "path": file.preflight.destination }),
                        ExitCode::Failure,
                    ),
                    false,
                ));
            }
            Err(error) => {
                return Err((
                    KcsError::io(
                        error.to_string(),
                        file.preflight.destination.display().to_string(),
                    ),
                    false,
                ));
            }
        }
    }
    verify_restored_entry(
        destination,
        Path::new(&file.preflight.source.path_at_commit),
        &file.temp_file,
        &file.preflight.source.raw_hash,
        file.preflight.size_bytes,
    )
    .map_err(|error| (error, true))?;
    Ok(())
}

#[cfg(not(windows))]
fn atomic_replace_handle(
    destination: &DestinationDir,
    source: &OsString,
    _source_file: &File,
    destination_name: &Path,
) -> Result<()> {
    cap_fs::rename(
        &destination.handle,
        Path::new(source),
        &destination.handle,
        destination_name,
    )
    .map_err(|error| {
        KcsError::io(
            error.to_string(),
            destination
                .path
                .join(destination_name)
                .display()
                .to_string(),
        )
    })
}

#[cfg(windows)]
fn atomic_replace_handle(
    destination: &DestinationDir,
    _source: &OsString,
    source_file: &File,
    destination_name: &Path,
) -> Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::AsRawHandle;
    use std::ptr;
    use windows_sys::Win32::Storage::FileSystem::{
        FileRenameInfo, SetFileInformationByHandle, FILE_RENAME_INFO,
    };

    let name = destination_name
        .as_os_str()
        .encode_wide()
        .collect::<Vec<_>>();
    let offset = std::mem::offset_of!(FILE_RENAME_INFO, FileName);
    let bytes = offset + name.len() * std::mem::size_of::<u16>();
    let words = bytes.div_ceil(std::mem::size_of::<usize>());
    let mut storage = vec![0_usize; words];
    let info = storage.as_mut_ptr().cast::<FILE_RENAME_INFO>();
    unsafe {
        (*info).Anonymous.ReplaceIfExists = true;
        (*info).RootDirectory = destination.handle.as_raw_handle();
        (*info).FileNameLength = (name.len() * std::mem::size_of::<u16>()) as u32;
        ptr::copy_nonoverlapping(name.as_ptr(), (*info).FileName.as_mut_ptr(), name.len());
    }
    if unsafe {
        SetFileInformationByHandle(
            source_file.as_raw_handle(),
            FileRenameInfo,
            info.cast(),
            bytes as u32,
        )
    } == 0
    {
        return Err(KcsError::io(
            std::io::Error::last_os_error().to_string(),
            destination
                .path
                .join(destination_name)
                .display()
                .to_string(),
        ));
    }
    Ok(())
}

fn validate_destination_handle(destination: &DestinationDir) -> Result<()> {
    let metadata = cap_fs::Metadata::from_file(&destination.handle)
        .map_err(|error| KcsError::io(error.to_string(), destination.path.display().to_string()))?;
    if !metadata.is_dir() || metadata.is_symlink() {
        return Err(unsafe_restore_error(
            &destination.path,
            "destination ancestor is not a real non-reparse directory",
        ));
    }
    #[cfg(windows)]
    {
        use cap_fs::_WindowsByHandle;
        use windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT;

        if metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
            return Err(unsafe_restore_error(
                &destination.path,
                "destination ancestor is a reparse point",
            ));
        }
    }
    Ok(())
}

fn verify_restored_entry(
    destination: &DestinationDir,
    name: &Path,
    expected_file: &File,
    expected_hash: &str,
    expected_size: u64,
) -> Result<()> {
    let display = destination.path.join(name);
    let listed = cap_fs::stat(&destination.handle, name, cap_fs::FollowSymlinks::No)
        .map_err(|error| KcsError::io(error.to_string(), display.display().to_string()))?;
    validate_replaceable_metadata(&display, &listed)?;

    let mut options = cap_fs::OpenOptions::new();
    options.read(true);
    configure_cap_no_follow(&mut options);
    let file = cap_fs::open(&destination.handle, name, &options)
        .map_err(|error| KcsError::io(error.to_string(), display.display().to_string()))?;
    let opened = cap_fs::Metadata::from_file(&file)
        .map_err(|error| KcsError::io(error.to_string(), display.display().to_string()))?;
    let expected = cap_fs::Metadata::from_file(expected_file)
        .map_err(|error| KcsError::io(error.to_string(), display.display().to_string()))?;
    let after = cap_fs::stat(&destination.handle, name, cap_fs::FollowSymlinks::No)
        .map_err(|error| KcsError::io(error.to_string(), display.display().to_string()))?;
    if !same_cap_file_identity(&listed, &opened)
        || !same_cap_file_identity(&opened, &after)
        || !same_cap_file_identity(&opened, &expected)
    {
        return Err(unsafe_restore_error(
            &display,
            "restored file changed identity while it was verified",
        ));
    }
    verify_open_file(&file, &display, expected_hash, expected_size)
}

fn verify_open_file(
    file: &File,
    display: &Path,
    expected_hash: &str,
    expected_size: u64,
) -> Result<()> {
    let metadata = cap_fs::Metadata::from_file(file)
        .map_err(|error| KcsError::io(error.to_string(), display.display().to_string()))?;
    validate_replaceable_metadata(display, &metadata)?;
    if metadata.len() != expected_size || metadata.len() > MAX_RAW_OBJECT_BYTES {
        return Err(KcsError::new(
            "KCS-E-STORE-CORRUPT-001",
            "restored file size does not match its raw identity",
            json!({ "path": display, "raw_hash": expected_hash }),
            ExitCode::PermanentFailure,
        ));
    }

    let mut reader = file
        .try_clone()
        .map_err(|error| KcsError::io(error.to_string(), display.display().to_string()))?;
    reader
        .seek(std::io::SeekFrom::Start(0))
        .map_err(|error| KcsError::io(error.to_string(), display.display().to_string()))?;
    let mut hasher = sha2::Sha256::new();
    let mut total = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = reader
            .read(&mut buffer)
            .map_err(|error| KcsError::io(error.to_string(), display.display().to_string()))?;
        if count == 0 {
            break;
        }
        total = total.saturating_add(count as u64);
        if total > MAX_RAW_OBJECT_BYTES {
            return Err(KcsError::new(
                "KCS-E-STORE-CORRUPT-001",
                "restored file exceeds the raw object limit",
                json!({ "path": display }),
                ExitCode::PermanentFailure,
            ));
        }
        hasher.update(&buffer[..count]);
    }
    let actual = format!("sha256:{:x}", hasher.finalize());
    if actual != expected_hash {
        return Err(KcsError::new(
            "KCS-E-STORE-CORRUPT-001",
            "restored file bytes do not match their raw identity",
            json!({ "path": display, "expected": expected_hash, "actual": actual }),
            ExitCode::PermanentFailure,
        ));
    }
    Ok(())
}

#[cfg(unix)]
fn same_cap_file_identity(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    use cap_fs::MetadataExt;
    left.dev() == right.dev() && left.ino() == right.ino()
}

#[cfg(windows)]
fn same_cap_file_identity(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    use cap_fs::_WindowsByHandle;
    left.volume_serial_number() == right.volume_serial_number()
        && left.file_index() == right.file_index()
}

#[cfg(not(any(unix, windows)))]
fn same_cap_file_identity(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    left.len() == right.len() && left.modified().ok() == right.modified().ok()
}

#[cfg(unix)]
fn configure_cap_no_follow(options: &mut cap_fs::OpenOptions) {
    use cap_fs::OpenOptionsExt;

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
fn configure_cap_no_follow(options: &mut cap_fs::OpenOptions) {
    use cap_fs::OpenOptionsExt;
    use windows_sys::Win32::Storage::FileSystem::FILE_FLAG_OPEN_REPARSE_POINT;
    options.custom_flags(FILE_FLAG_OPEN_REPARSE_POINT);
}

#[cfg(not(any(unix, windows)))]
fn configure_cap_no_follow(_options: &mut cap_fs::OpenOptions) {}

#[cfg(unix)]
fn sync_directory_handle(destination: &DestinationDir) -> Result<()> {
    // `cap_primitives` deliberately opens capability directories with
    // `O_PATH` on Linux. That descriptor is suitable for the relative
    // operations above, but `fsync(O_PATH)` fails with `EBADF`. Re-open `.`
    // relative to the held capability so durability is requested for the
    // same directory without falling back to its ambient pathname.
    let mut options = cap_fs::OpenOptions::new();
    options.read(true);
    let syncable = cap_fs::open(&destination.handle, Path::new("."), &options)
        .map_err(|error| KcsError::io(error.to_string(), destination.path.display().to_string()))?;
    syncable
        .sync_all()
        .map_err(|error| KcsError::io(error.to_string(), destination.path.display().to_string()))
}

#[cfg(not(unix))]
fn sync_directory_handle(_destination: &DestinationDir) -> Result<()> {
    Ok(())
}

fn cleanup_staged(destination: &DestinationDir, staged: &[StagedFile]) {
    for file in staged {
        cleanup_one(destination, &file.temp);
    }
}

fn cleanup_one(destination: &DestinationDir, name: &OsString) {
    let _ = cap_fs::remove_file(&destination.handle, Path::new(name));
}

fn success_output(
    source: &RestoreSource,
    destination: &Path,
    files: Vec<PreflightFile>,
    overwritten_count: u64,
) -> Value {
    json!({
        "status": "restored",
        "source_kind": source.source_kind,
        "source_commit": source.source_commit,
        "destination": destination,
        "restored_count": files.len(),
        "overwritten_count": overwritten_count,
        "files": files.iter().map(restored_file_json).collect::<Vec<_>>(),
    })
}

fn partial_output(
    source: &RestoreSource,
    destination: &Path,
    files: Vec<PreflightFile>,
    overwritten_count: u64,
    failed: &PreflightFile,
    error: KcsError,
) -> Value {
    let mut output = json!({
        "status": "partial",
        "error_code": "KCS-E-COMMIT-RESTORE-PARTIAL-001",
        "source_kind": source.source_kind,
        "source_commit": source.source_commit,
        "destination": destination,
        "restored_count": files.len(),
        "overwritten_count": overwritten_count,
        "files": files.iter().map(restored_file_json).collect::<Vec<_>>(),
        "failed": [{
            "path": failed.destination,
            "path_at_commit": failed.source.path_at_commit,
            "raw_hash": failed.source.raw_hash,
            "error_code": error.error_code(),
            "message": error.message(),
        }],
    });
    super::set_exit_override(&mut output, ExitCode::PartialFailure);
    output
}

fn restored_file_json(file: &PreflightFile) -> Value {
    json!({
        "path": file.destination,
        "path_at_commit": file.source.path_at_commit,
        "raw_hash": file.source.raw_hash,
        "overwritten": file.overwritten,
    })
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::io::Write;

    use super::{
        atomic_replace_handle, check_purge_state, create_private_temp, missing_live_raw_error,
        normalize_absolute, open_destination_dir, sync_directory_handle, validate_source_names,
        RestoreItem, ScopeTarget,
    };

    #[test]
    fn source_name_collision_is_case_and_normalization_insensitive() {
        let raw_hash = kcs_core::cas::hash_bytes(b"same");
        let error = validate_source_names(&[
            RestoreItem {
                path_at_commit: "Report.md".to_owned(),
                raw_hash: raw_hash.clone(),
            },
            RestoreItem {
                path_at_commit: "report.md".to_owned(),
                raw_hash,
            },
        ])
        .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-COMMIT-RESTORE-UNSAFE-001");
    }

    #[test]
    fn destination_normalization_removes_parent_components() {
        let cwd = std::env::current_dir().unwrap();
        assert_eq!(
            normalize_absolute(std::path::Path::new("a/../b")).unwrap(),
            cwd.join("b")
        );
    }

    #[cfg(unix)]
    #[test]
    fn destination_directory_sync_uses_a_syncable_capability_descriptor() {
        let temp = tempfile::TempDir::new().unwrap();
        let destination =
            open_destination_dir(&temp.path().canonicalize().unwrap(), false).unwrap();

        sync_directory_handle(&destination).unwrap();
    }

    #[test]
    fn missing_raw_is_dead_source_without_receipt_disclosure() {
        let temp = tempfile::TempDir::new().unwrap();
        let kcs_dir = temp.path().join(".kcs");
        fs::create_dir_all(&kcs_dir).unwrap();
        let raw_hash = kcs_core::cas::hash_bytes(b"erased");
        let state = kcs_core::purge::PurgeState::new(&kcs_dir);
        let receipt = state.erase_receipt_path(&raw_hash).unwrap();
        fs::create_dir_all(receipt.parent().unwrap()).unwrap();
        // Deliberately invalid: restore must not parse this fsck-only record.
        fs::write(&receipt, b"private receipt contents").unwrap();
        let target = ScopeTarget {
            repo_root: temp.path().to_path_buf(),
            kcs_dir,
            scope_id: "scope-test".to_owned(),
        };

        check_purge_state(&target, &raw_hash).unwrap();
        let error = missing_live_raw_error(&target, &raw_hash);
        assert_eq!(error.error_code(), "KCS-E-PURGE-NOT-FOUND-001");
        assert_eq!(error.exit_code(), kcs_core::ExitCode::PermanentFailure);
        assert!(!error.context().to_string().contains("receipt"));
    }

    #[cfg(unix)]
    #[test]
    fn held_destination_directory_prevents_parent_symlink_swap_escape() {
        use std::os::unix::fs::symlink;

        let temp = tempfile::TempDir::new().unwrap();
        let root = temp.path().canonicalize().unwrap();
        let destination_path = root.join("destination");
        let moved_path = root.join("moved-destination");
        let outside_path = root.join("outside");
        fs::create_dir(&destination_path).unwrap();
        fs::create_dir(&outside_path).unwrap();
        fs::write(destination_path.join("doc.md"), b"old destination").unwrap();
        fs::write(outside_path.join("doc.md"), b"outside sentinel").unwrap();

        let destination = open_destination_dir(&destination_path, false).unwrap();
        fs::rename(&destination_path, &moved_path).unwrap();
        symlink(&outside_path, &destination_path).unwrap();

        let (temp_name, mut staged) = create_private_temp(&destination).unwrap();
        staged.write_all(b"restored bytes").unwrap();
        staged.sync_all().unwrap();
        atomic_replace_handle(
            &destination,
            &temp_name,
            &staged,
            std::path::Path::new("doc.md"),
        )
        .unwrap();

        assert_eq!(
            fs::read(moved_path.join("doc.md")).unwrap(),
            b"restored bytes"
        );
        assert_eq!(
            fs::read(outside_path.join("doc.md")).unwrap(),
            b"outside sentinel"
        );
    }
}
