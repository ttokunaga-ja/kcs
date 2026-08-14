//! Capability-bound materialization of the frozen deterministic corpus.

use std::{
    collections::{BTreeMap, HashSet},
    env, fs, io,
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

use cap_primitives::{ambient_authority, fs as cap_fs};
use kio_core::cas::hash_bytes;
use serde::Deserialize;
use thiserror::Error;

use crate::manifest::{
    CORPUS_ANCHOR_COUNT, CORPUS_FILE_COUNT, CorpusManifest, SCOPES, validate_corpus_manifest,
};

const FIXTURE: &str = include_str!("../../../eval/corpus-fixture.json");
const MANIFEST_NAME: &str = "corpus-manifest.json";
const FIXTURE_MANIFEST_SHA256: &str =
    "10a2d87520dea212b4f3c7cdbb530b85158dbb9978f185fc343df2eefb02ec72";
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Error)]
pub enum GeneratorError {
    #[error("invalid frozen corpus fixture: {0}")]
    Fixture(String),
    #[error("output directory is not empty: {0}")]
    NonEmpty(PathBuf),
    #[error("unsafe corpus output boundary at {path}: {message}")]
    Boundary { path: PathBuf, message: String },
    #[error("corpus generation I/O error at {path}: {source}")]
    Io {
        path: PathBuf,
        #[source]
        source: io::Error,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GenerationSummary {
    pub output: PathBuf,
    pub file_count: usize,
    pub anchor_count: usize,
    pub scope_count: usize,
    pub per_scope: Vec<(String, usize)>,
    pub manifest_path: PathBuf,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixture {
    schema_version: u64,
    manifest_sha256: String,
    manifest: CorpusManifest,
    contents: Vec<FixtureContent>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct FixtureContent {
    scope: String,
    file: String,
    content: String,
}

/// Materialize the frozen corpus under `out` without following attacker-owned
/// output components. Existing unlisted files are deliberately retained when
/// `force` is set, preserving the stable generator contract.
pub fn generate_corpus(out: &Path, force: bool) -> Result<GenerationSummary, GeneratorError> {
    let fixture = fixture()?;
    let manifest_bytes = frozen_manifest_bytes(&fixture.manifest)?;
    let output = absolute(out)?;
    let (parent_handle, leaf) = safe_parent_and_leaf(&output)?;
    let (root, root_created) = open_or_create_root(&parent_handle, &leaf, &output)?;
    if root_created {
        sync_dir(&parent_handle, output.parent().unwrap_or(&output))?;
    }

    if !force && !is_empty(&root, &output)? {
        return Err(GeneratorError::NonEmpty(output));
    }

    let mut scope_handles = BTreeMap::new();
    for scope in SCOPES {
        let (scope_handle, created) = create_or_open_dir(&root, scope, &output.join(scope))?;
        if created {
            sync_dir(&root, &output)?;
        }
        scope_handles.insert(scope, scope_handle);
    }

    for entry in &fixture.contents {
        let scope = scope_handles
            .get(entry.scope.as_str())
            .expect("fixture validation binds known scopes");
        replace_regular(
            scope,
            &entry.file,
            entry.content.as_bytes(),
            &output.join(&entry.scope).join(&entry.file),
        )?;
    }

    // The manifest is the commit record: it is only replaced after every
    // expected content file was fully synced and renamed.
    replace_regular(
        &root,
        MANIFEST_NAME,
        &manifest_bytes,
        &output.join(MANIFEST_NAME),
    )?;
    sync_dir(&root, &output)?;

    let per_scope = fixture
        .manifest
        .scopes
        .iter()
        .map(|scope| {
            (
                scope.clone(),
                fixture
                    .manifest
                    .files
                    .iter()
                    .filter(|file| file.scope == *scope)
                    .count(),
            )
        })
        .collect();
    Ok(GenerationSummary {
        output: output.clone(),
        file_count: fixture.manifest.file_count,
        anchor_count: fixture.manifest.anchor_count,
        scope_count: fixture.manifest.scopes.len(),
        per_scope,
        manifest_path: output.join(MANIFEST_NAME),
    })
}

fn fixture() -> Result<Fixture, GeneratorError> {
    let fixture: Fixture = serde_json::from_str(FIXTURE)
        .map_err(|error| GeneratorError::Fixture(error.to_string()))?;
    if fixture.schema_version != 1 {
        return Err(GeneratorError::Fixture("schema_version mismatch".into()));
    }
    if fixture.manifest_sha256 != FIXTURE_MANIFEST_SHA256 {
        return Err(GeneratorError::Fixture(
            "manifest digest identity mismatch".into(),
        ));
    }
    validate_corpus_manifest(&fixture.manifest)
        .map_err(|error| GeneratorError::Fixture(error.to_string()))?;
    if fixture.manifest.files.len() != CORPUS_FILE_COUNT
        || fixture.manifest.anchor_count != CORPUS_ANCHOR_COUNT
    {
        return Err(GeneratorError::Fixture(
            "frozen corpus counts mismatch".into(),
        ));
    }
    let bytes = frozen_manifest_bytes(&fixture.manifest)?;
    if hash_hex(&bytes) != fixture.manifest_sha256 {
        return Err(GeneratorError::Fixture(format!(
            "manifest bytes digest mismatch: {}",
            hash_hex(&bytes)
        )));
    }
    if fixture.contents.len() != fixture.manifest.files.len() {
        return Err(GeneratorError::Fixture("content count mismatch".into()));
    }
    let mut expected = HashSet::new();
    for file in &fixture.manifest.files {
        expected.insert((
            file.scope.clone(),
            file.file.clone(),
            file.raw_sha256.clone(),
        ));
    }
    let mut actual = HashSet::new();
    let mut previous: Option<(&str, &str)> = None;
    for content in &fixture.contents {
        let key = (content.scope.as_str(), content.file.as_str());
        if previous.is_some_and(|prior| prior >= key) {
            return Err(GeneratorError::Fixture(
                "contents are not unique scope/file order".into(),
            ));
        }
        previous = Some(key);
        let digest = hash_hex(content.content.as_bytes());
        if !expected.remove(&(key.0.to_owned(), key.1.to_owned(), digest)) {
            return Err(GeneratorError::Fixture(format!(
                "content does not match manifest: {}/{}",
                key.0, key.1
            )));
        }
        if !actual.insert(key) {
            return Err(GeneratorError::Fixture("duplicate contents entry".into()));
        }
    }
    if !expected.is_empty() {
        return Err(GeneratorError::Fixture(
            "manifest entries missing content".into(),
        ));
    }
    Ok(fixture)
}

// `serde_json::Map` is ordered without the preserve_order feature. Converting
// through Value therefore gives the frozen manifest a deterministic key order.
fn frozen_manifest_bytes(manifest: &CorpusManifest) -> Result<Vec<u8>, GeneratorError> {
    let value = serde_json::to_value(manifest)
        .map_err(|error| GeneratorError::Fixture(error.to_string()))?;
    let mut text = serde_json::to_string_pretty(&value)
        .map_err(|error| GeneratorError::Fixture(error.to_string()))?;
    text.push('\n');
    Ok(text.into_bytes())
}

fn absolute(path: &Path) -> Result<PathBuf, GeneratorError> {
    let joined = if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        env::current_dir()
            .map(|cwd| cwd.join(path))
            .map_err(|source| io_error(path, source))
    }?;
    lexical_absolute(&joined)
}

/// Normalize only `.` and `..` components. This deliberately does not call
/// `canonicalize`, which would follow a caller-controlled symlink before the
/// capability-bound nofollow walk.
fn lexical_absolute(path: &Path) -> Result<PathBuf, GeneratorError> {
    if !path.is_absolute() {
        return Err(boundary(path, "output must be absolute"));
    }
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(component.as_os_str()),
            Component::Normal(part) => normalized.push(part),
            Component::CurDir => {}
            Component::ParentDir => {
                // `PathBuf::pop` leaves a rooted path at its root. A Prefix
                // without RootDir cannot occur after `is_absolute`.
                let _ = normalized.pop();
            }
        }
    }
    Ok(normalized)
}

fn safe_parent_and_leaf(output: &Path) -> Result<(fs::File, String), GeneratorError> {
    let parent = output
        .parent()
        .ok_or_else(|| boundary(output, "output has no parent"))?;
    let leaf = output
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| boundary(output, "output has no valid final component"))?;
    if leaf.is_empty() || Path::new(leaf).components().count() != 1 {
        return Err(boundary(output, "output has invalid final component"));
    }
    // Darwin exposes its temporary hierarchy through the platform aliases
    // `/tmp` and `/var`. Rewrite only those known root aliases; never
    // canonicalize caller-controlled components before the nofollow walk.
    let normalized_parent = normalize_platform_root_alias(parent);
    let mut components = normalized_parent.components().peekable();
    let mut root = PathBuf::new();
    #[cfg(windows)]
    if let Some(Component::Prefix(prefix)) = components.peek().copied() {
        root.push(prefix.as_os_str());
        components.next();
    }
    if !matches!(components.next(), Some(Component::RootDir)) {
        return Err(boundary(output, "output must be absolute"));
    }
    root.push(std::path::MAIN_SEPARATOR_STR);
    let mut handle = cap_fs::open_ambient_dir(&root, ambient_authority())
        .map_err(|source| io_error(&root, source))?;
    for component in components {
        let Component::Normal(part) = component else {
            return Err(boundary(output, "output path must be normalized"));
        };
        match cap_fs::open_dir_nofollow(&handle, Path::new(part)) {
            Ok(child) => handle = child,
            Err(_) => match cap_fs::stat(&handle, Path::new(part), cap_fs::FollowSymlinks::No) {
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    cap_fs::create_dir(&handle, Path::new(part), &cap_fs::DirOptions::new())
                        .map_err(|source| io_error(output, source))?;
                    sync_dir(&handle, output)?;
                    handle = cap_fs::open_dir_nofollow(&handle, Path::new(part))
                        .map_err(|_| boundary(output, "created parent was not a real directory"))?;
                }
                Ok(_) => {
                    return Err(boundary(
                        output,
                        "parent component must be a real directory",
                    ));
                }
                Err(source) => return Err(io_error(output, source)),
            },
        }
    }
    Ok((handle, leaf.to_owned()))
}

fn normalize_platform_root_alias(path: &Path) -> PathBuf {
    #[cfg(target_os = "macos")]
    {
        let mut parts = path.components();
        if !matches!(parts.next(), Some(Component::RootDir)) {
            return path.to_path_buf();
        }
        let Some(Component::Normal(first)) = parts.next() else {
            return path.to_path_buf();
        };
        if first != "tmp" && first != "var" {
            return path.to_path_buf();
        }
        let mut normalized = PathBuf::from("/private");
        normalized.push(first);
        for part in parts {
            normalized.push(part.as_os_str());
        }
        normalized
    }
    #[cfg(not(target_os = "macos"))]
    {
        path.to_path_buf()
    }
}

fn open_or_create_root(
    parent: &fs::File,
    leaf: &str,
    output: &Path,
) -> Result<(fs::File, bool), GeneratorError> {
    match cap_fs::open_dir_nofollow(parent, Path::new(leaf)) {
        Ok(dir) => Ok((dir, false)),
        Err(_) => match cap_fs::stat(parent, Path::new(leaf), cap_fs::FollowSymlinks::No) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                cap_fs::create_dir(parent, Path::new(leaf), &cap_fs::DirOptions::new())
                    .map_err(|source| io_error(output, source))?;
                cap_fs::open_dir_nofollow(parent, Path::new(leaf))
                    .map(|dir| (dir, true))
                    .map_err(|source| io_error(output, source))
            }
            Ok(_) => Err(boundary(
                output,
                "output must be a real non-reparse directory",
            )),
            Err(source) => Err(io_error(output, source)),
        },
    }
}

fn create_or_open_dir(
    parent: &fs::File,
    name: &str,
    path: &Path,
) -> Result<(fs::File, bool), GeneratorError> {
    open_or_create_root(parent, name, path)
}

fn is_empty(dir: &fs::File, path: &Path) -> Result<bool, GeneratorError> {
    let entries = cap_fs::read_dir(dir, Path::new(".")).map_err(|source| io_error(path, source))?;
    Ok(entries.count() == 0)
}

fn replace_regular(
    dir: &fs::File,
    name: &str,
    bytes: &[u8],
    path: &Path,
) -> Result<(), GeneratorError> {
    reject_unsafe_target(dir, name, path)?;
    let mut options = cap_fs::OpenOptions::new();
    options.write(true).create_new(true);
    let mut temp = None;
    let mut file = None;
    for _ in 0..16 {
        let candidate = format!(
            ".kio-eval-tmp-{}-{}",
            std::process::id(),
            TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        );
        match cap_fs::open(dir, Path::new(&candidate), &options) {
            Ok(opened) => {
                temp = Some(candidate);
                file = Some(opened);
                break;
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(source) => return Err(io_error(path, source)),
        }
    }
    let temp = temp.ok_or_else(|| boundary(path, "unable to reserve unique temporary file"))?;
    let mut file = file.expect("temporary filename and handle are paired");
    use io::Write;
    if let Err(source) = file.write_all(bytes).and_then(|_| file.sync_all()) {
        let _ = cap_fs::remove_file(dir, Path::new(&temp));
        return Err(io_error(path, source));
    }
    if let Err(source) = cap_fs::rename(dir, Path::new(&temp), dir, Path::new(name)) {
        let _ = cap_fs::remove_file(dir, Path::new(&temp));
        return Err(io_error(path, source));
    }
    sync_dir(dir, path)
}

fn reject_unsafe_target(dir: &fs::File, name: &str, path: &Path) -> Result<(), GeneratorError> {
    match cap_fs::stat(dir, Path::new(name), cap_fs::FollowSymlinks::No) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(source) => Err(io_error(path, source)),
        Ok(metadata) => {
            if !metadata.is_file() || metadata.file_type().is_symlink() {
                return Err(boundary(
                    path,
                    "existing target must be a regular non-symlink file",
                ));
            }
            #[cfg(unix)]
            {
                use cap_primitives::fs::MetadataExt;
                if metadata.nlink() != 1 {
                    return Err(boundary(
                        path,
                        "existing target must not have multiple links",
                    ));
                }
            }
            Ok(())
        }
    }
}

fn sync_dir(dir: &fs::File, path: &Path) -> Result<(), GeneratorError> {
    #[cfg(unix)]
    dir.sync_all().map_err(|source| io_error(path, source))?;
    #[cfg(windows)]
    {
        let metadata = dir.metadata().map_err(|source| io_error(path, source))?;
        if !metadata.is_dir() {
            return Err(boundary(path, "directory handle changed type"));
        }
    }
    Ok(())
}

fn boundary(path: &Path, message: impl Into<String>) -> GeneratorError {
    GeneratorError::Boundary {
        path: path.to_path_buf(),
        message: message.into(),
    }
}
fn io_error(path: &Path, source: io::Error) -> GeneratorError {
    GeneratorError::Io {
        path: path.to_path_buf(),
        source,
    }
}

fn hash_hex(bytes: &[u8]) -> String {
    hash_bytes(bytes)
        .strip_prefix("sha256:")
        .unwrap_or_default()
        .to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixture_is_complete_and_has_frozen_manifest_bytes() {
        let fixture = fixture().unwrap();
        assert_eq!(
            hash_hex(&frozen_manifest_bytes(&fixture.manifest).unwrap()),
            FIXTURE_MANIFEST_SHA256
        );
    }

    #[test]
    fn fresh_generation_is_deterministic() {
        let first = tempfile::tempdir().unwrap();
        let second = tempfile::tempdir().unwrap();
        let a = generate_corpus(&first.path().join("corpus"), false).unwrap();
        let b = generate_corpus(&second.path().join("corpus"), false).unwrap();
        assert_eq!(a.file_count, 305);
        assert_eq!(a.anchor_count, 31);
        assert_eq!(a.scope_count, 7);
        assert_eq!(
            fs::read(a.manifest_path).unwrap(),
            fs::read(b.manifest_path).unwrap()
        );
        let fixture = fixture().unwrap();
        for item in fixture.contents {
            assert_eq!(
                fs::read(first.path().join("corpus").join(item.scope).join(item.file)).unwrap(),
                item.content.as_bytes()
            );
        }
    }

    #[test]
    fn nonempty_requires_force_and_force_retains_stale_file() {
        let temp = tempfile::tempdir().unwrap();
        let out = temp.path().join("corpus");
        generate_corpus(&out, false).unwrap();
        fs::write(out.join("stale.txt"), "keep").unwrap();
        assert!(matches!(
            generate_corpus(&out, false),
            Err(GeneratorError::NonEmpty(_))
        ));
        generate_corpus(&out, true).unwrap();
        assert_eq!(fs::read_to_string(out.join("stale.txt")).unwrap(), "keep");
    }

    #[test]
    fn creates_missing_parent_hierarchy() {
        let temp = tempfile::tempdir().unwrap();
        let out = temp.path().join("missing/parent/corpus");
        generate_corpus(&out, false).unwrap();
        assert!(out.join(MANIFEST_NAME).is_file());
    }

    #[test]
    fn accepts_lexically_normalized_parent_components() {
        let temp = tempfile::tempdir().unwrap();
        generate_corpus(&temp.path().join("working/../nested/corpus"), false).unwrap();
        assert!(
            temp.path()
                .join("nested/corpus")
                .join(MANIFEST_NAME)
                .is_file()
        );
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symlinked_root_scope_and_target_without_touching_victim() {
        use std::os::unix::fs::symlink;
        let temp = tempfile::tempdir().unwrap();
        let victim = temp.path().join("victim");
        fs::write(&victim, "victim").unwrap();
        let root_link = temp.path().join("root-link");
        let outside = tempfile::tempdir().unwrap();
        symlink(outside.path(), &root_link).unwrap();
        assert!(generate_corpus(&root_link, true).is_err());
        assert!(fs::read_dir(outside.path()).unwrap().next().is_none());
        assert_eq!(fs::read_to_string(&victim).unwrap(), "victim");

        let parent_link = temp.path().join("parent-link");
        symlink(outside.path(), &parent_link).unwrap();
        assert!(generate_corpus(&parent_link.join("corpus"), true).is_err());
        assert!(fs::read_dir(outside.path()).unwrap().next().is_none());

        let out = temp.path().join("corpus");
        fs::create_dir(&out).unwrap();
        symlink(&victim, out.join("research")).unwrap();
        assert!(generate_corpus(&out, true).is_err());
        assert_eq!(fs::read_to_string(&victim).unwrap(), "victim");

        fs::remove_file(out.join("research")).unwrap();
        generate_corpus(&out, true).unwrap();
        let target = out.join("research/auth-spec.md");
        fs::remove_file(&target).unwrap();
        symlink(&victim, &target).unwrap();
        assert!(generate_corpus(&out, true).is_err());
        assert_eq!(fs::read_to_string(&victim).unwrap(), "victim");
    }

    #[cfg(unix)]
    #[test]
    fn rejects_hardlinked_target_without_touching_victim() {
        let temp = tempfile::tempdir().unwrap();
        let out = temp.path().join("corpus");
        generate_corpus(&out, false).unwrap();
        let victim = temp.path().join("victim");
        fs::write(&victim, "victim").unwrap();
        let target = out.join("research/auth-spec.md");
        fs::remove_file(&target).unwrap();
        fs::hard_link(&victim, &target).unwrap();
        assert!(generate_corpus(&out, true).is_err());
        assert_eq!(fs::read_to_string(&victim).unwrap(), "victim");
    }
}
