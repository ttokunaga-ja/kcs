//! Deterministic, deliberately small release-candidate packaging boundary.
//!
//! This module is dev tooling.  It does not publish, tag, upload, sign, or
//! mutate a repository.  Its inputs are an already-built, bound `kio` binary
//! and the checked-out candidate tree; its outputs are create-only archives.

use std::{
    collections::{BTreeMap, BTreeSet},
    env,
    ffi::OsStr,
    fs::{self, File, OpenOptions},
    io::{self, Cursor, Read, Write},
    path::{Path, PathBuf},
    process::Command,
};

use flate2::{Compression, GzBuilder, read::GzDecoder};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tar::{Archive, Builder, Header};
use tempfile::TempDir;
use thiserror::Error;

/// Package metadata is the sole version authority; this tool never carries a
/// second release-version literal.
pub const RC_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const CARGO_SBOM_VERSION: &str = "0.10.0";
pub const CARGO_DENY_VERSION: &str = "0.20.2";
const MARKER_START: &[u8] = b"KIO_RC_BINDING_V1\n";
const MARKER_END: &[u8] = b"\nKIO_RC_BINDING_END_V1";
const MAX_INPUT: u64 = 512 * 1024 * 1024;
const MAX_ARCHIVE: u64 = 768 * 1024 * 1024;
const MAX_JSON: u64 = 16 * 1024 * 1024;
const MAX_ENTRY: u64 = 512 * 1024 * 1024;
const MAX_ARCHIVE_ENTRIES: usize = 16;
const MAX_UNPACKED: u64 = 640 * 1024 * 1024;
const MAX_CANDIDATE_OUTPUTS: usize = 16;
const MAX_JSON_DIFF_FIELDS: usize = 64;
const MAX_DIAGNOSTIC_PATH_BYTES: usize = 512;
const MAX_PE_SECTIONS: usize = 96;
const MAX_PE_DEBUG_ENTRIES: usize = 32;

#[derive(Debug, Error)]
pub enum ReleaseError {
    #[error("release input is invalid: {0}")]
    Invalid(String),
    #[error("release candidate is not bound: {0}")]
    Unbound(String),
    #[error("release artifact verification failed: {0}")]
    Verify(String),
    #[error("I/O: {0}")]
    Io(#[from] io::Error),
    #[error("JSON: {0}")]
    Json(#[from] serde_json::Error),
}

#[derive(Debug, Clone)]
pub struct PrepareToolsOptions {
    pub output_dir: PathBuf,
}

#[derive(Debug, Clone)]
pub struct BuildCandidateOptions {
    pub repo: PathBuf,
    pub candidate_sha: String,
    pub target: String,
    pub target_dir: PathBuf,
}

#[derive(Debug, Clone)]
pub struct PackageCandidateOptions {
    pub repo: PathBuf,
    pub binary: PathBuf,
    pub target: String,
    pub output_dir: PathBuf,
    /// Root produced by [`prepare_tools`].  Tool binaries are never resolved
    /// from PATH, which prevents an ambient cargo subcommand substitution.
    pub tools_dir: PathBuf,
}

#[derive(Debug, Clone, Default)]
pub struct VerifyCandidateOptions {
    pub archive: PathBuf,
    pub checksum: Option<PathBuf>,
    /// Digest retained independently from the downloaded archive/sidecar pair.
    pub expected_archive_sha256: String,
    /// Optional clean checkout used to independently rederive every source binding.
    pub expected_repo: Option<PathBuf>,
    pub expected_commit: Option<String>,
    pub expected_lock_sha256: Option<String>,
}

#[derive(Debug, Clone)]
pub struct SmokeCandidateOptions {
    pub verify: VerifyCandidateOptions,
    pub work_dir: PathBuf,
    /// Optional create-only machine-readable smoke receipt.
    pub receipt: Option<PathBuf>,
}

#[derive(Debug, Clone, Serialize)]
pub struct BuildSummary {
    pub binary: PathBuf,
    pub binding: Binding,
}

#[derive(Debug, Clone, Serialize)]
pub struct PackageSummary {
    pub archive: PathBuf,
    pub checksum: PathBuf,
    pub archive_sha256: String,
    pub binding: Binding,
}

#[derive(Debug, Clone, Serialize)]
pub struct VerifySummary {
    pub root: String,
    pub archive_sha256: String,
    pub binding: Binding,
    pub support: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SmokeSummary {
    pub schema: String,
    pub status: String,
    pub archive_sha256: String,
    pub version: String,
    pub commit: String,
    pub target: String,
    pub support: String,
    pub operations: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub version: String,
    pub commit: String,
    pub tree: String,
    pub cargo_lock_sha256: String,
    pub toolchain_sha256: String,
    pub rust_version: String,
    pub target: String,
    pub features: String,
    pub profile: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ChecksumSidecar {
    schema: String,
    archive: String,
    archive_sha256: String,
    binary_sha256: String,
    provenance_sha256: String,
    sbom_sha256: String,
    checksums_sha256: String,
}

#[derive(Serialize)]
struct CompareDiagnostic {
    schema: &'static str,
    outputs: Vec<OutputDiagnostic>,
}

#[derive(Serialize)]
struct OutputDiagnostic {
    name: String,
    matches: bool,
    left: Option<ContentDigest>,
    right: Option<ContentDigest>,
    difference: Option<OutputDifference>,
}

#[derive(Serialize)]
struct ContentDigest {
    size: usize,
    sha256: String,
}

#[derive(Serialize)]
struct OutputDifference {
    classification: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    json_fields: Option<JsonFieldDifferences>,
    #[serde(skip_serializing_if = "Option::is_none")]
    archive_entries: Option<Vec<ArchiveEntryDiagnostic>>,
}

#[derive(Serialize)]
struct JsonFieldDifferences {
    truncated: bool,
    fields: Vec<JsonFieldDiagnostic>,
}

#[derive(Serialize)]
struct JsonFieldDiagnostic {
    path: String,
    left_kind: Option<&'static str>,
    right_kind: Option<&'static str>,
    left_canonical_sha256: Option<String>,
    right_canonical_sha256: Option<String>,
}

#[derive(Serialize)]
struct ArchiveEntryDiagnostic {
    path: String,
    matches: bool,
    left: Option<ContentDigest>,
    right: Option<ContentDigest>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pe32_plus: Option<PeDifferenceDiagnostic>,
}

#[derive(Serialize)]
struct PeDifferenceDiagnostic {
    left: PeDiagnostic,
    right: PeDiagnostic,
}

#[derive(Serialize)]
struct PeDiagnostic {
    #[serde(skip_serializing_if = "Option::is_none")]
    metadata: Option<Pe32PlusMetadata>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<&'static str>,
}

#[derive(Serialize)]
struct Pe32PlusMetadata {
    machine: u16,
    coff_timestamp: u32,
    checksum: u32,
    reproducible: bool,
    sections: Vec<PeSectionDiagnostic>,
    debug_entries: Vec<PeDebugEntryDiagnostic>,
}

#[derive(Serialize)]
struct PeSectionDiagnostic {
    name_hex: String,
    rva: u32,
    virtual_size: u32,
    raw_size: u32,
    raw_offset: u32,
    raw_sha256: String,
}

#[derive(Serialize)]
struct PeDebugEntryDiagnostic {
    kind: u32,
    timestamp: u32,
    size: u32,
    raw_sha256: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    codeview_rsds: Option<CodeViewRsdsDiagnostic>,
}

#[derive(Serialize)]
struct CodeViewRsdsDiagnostic {
    guid_hex: String,
    age: u32,
    pdb_path_bytes: usize,
    pdb_path_sha256: String,
    pdb_path_class: &'static str,
}

struct ParsedPeSection {
    name: [u8; 8],
    rva: u32,
    virtual_size: u32,
    raw_size: u32,
    raw_offset: u32,
}

pub fn prepare_tools(options: &PrepareToolsOptions) -> Result<(), ReleaseError> {
    create_empty_dir(&options.output_dir)?;
    let root = options.output_dir.canonicalize()?;
    for (crate_name, version) in [
        ("cargo-sbom", CARGO_SBOM_VERSION),
        ("cargo-deny", CARGO_DENY_VERSION),
    ] {
        let status = Command::new("cargo")
            .args([
                "+1.98.0",
                "install",
                "--locked",
                "--version",
                version,
                "--root",
            ])
            .arg(&root)
            .arg(crate_name)
            .status()?;
        if !status.success() {
            return Err(ReleaseError::Invalid(format!(
                "installing {crate_name} {version} failed: {status}"
            )));
        }
    }
    for (exe, version) in [
        ("cargo-sbom", CARGO_SBOM_VERSION),
        ("cargo-deny", CARGO_DENY_VERSION),
    ] {
        let path = root.join("bin").join(executable_name(exe));
        let output = Command::new(&path).arg("--version").output()?;
        if !output.status.success() || !String::from_utf8_lossy(&output.stdout).contains(version) {
            return Err(ReleaseError::Invalid(format!(
                "{exe} does not report pinned version {version}"
            )));
        }
    }
    Ok(())
}

/// Return the native Rust target used for an RC candidate build.
pub fn native_target() -> Result<String, ReleaseError> {
    rust_host()
}

/// Hash the locked dependency graph from a clean canonical checkout.
pub fn candidate_lock_sha256(repo: &Path) -> Result<String, ReleaseError> {
    let repo = canonical_repo(repo)?;
    reject_dirty(&repo)?;
    Ok(digest(&bounded_bytes(&repo.join("Cargo.lock"), MAX_JSON)?))
}

/// Compute the archive identity that a trusted run receipt must retain outside
/// the downloaded archive and checksum sidecar.
pub fn candidate_archive_sha256(archive: &Path) -> Result<String, ReleaseError> {
    require_regular(archive, MAX_ARCHIVE)?;
    Ok(digest(&bounded_bytes(archive, MAX_ARCHIVE)?))
}

pub fn build_candidate(options: &BuildCandidateOptions) -> Result<BuildSummary, ReleaseError> {
    let repo = canonical_repo(&options.repo)?;
    let binding = repo_binding(&repo, &options.candidate_sha, &options.target)?;
    let host = rust_host()?;
    if host != options.target {
        return Err(ReleaseError::Invalid(format!(
            "candidate target {} is not native host {host}",
            options.target
        )));
    }
    require_output_outside_repo(&repo, &options.target_dir)?;
    create_empty_dir(&options.target_dir)?;
    let mut cargo = cargo_command(&repo, &binding, &options.target_dir)?;
    let status = cargo.status()?;
    if !status.success() {
        return Err(ReleaseError::Invalid(format!(
            "candidate cargo build failed: {status}"
        )));
    }
    let binary = options
        .target_dir
        .join(&options.target)
        .join("release")
        .join(binary_name());
    require_regular(&binary, MAX_INPUT)?;
    let embedded = read_binding(&binary)?;
    require_binding(&binding, &embedded)?;
    Ok(BuildSummary { binary, binding })
}

pub fn package_candidate(
    options: &PackageCandidateOptions,
) -> Result<PackageSummary, ReleaseError> {
    let repo = canonical_repo(&options.repo)?;
    let binding = repo_binding(&repo, &git(&repo, &["rev-parse", "HEAD"])?, &options.target)?;
    require_regular(&options.binary, MAX_INPUT)?;
    require_binding(&binding, &read_binding(&options.binary)?)?;
    require_output_outside_repo(&repo, &options.output_dir)?;
    create_empty_dir(&options.output_dir)?;

    let generated = TempDir::new()?;
    let sbom_path = generate_sbom(&repo, &options.tools_dir, generated.path())?;
    let inventory_path =
        generate_inventory(&repo, &options.tools_dir, generated.path(), &binding.target)?;
    let audit_path = generate_audit(&repo, &options.tools_dir, generated.path(), &binding.target)?;
    let sbom = canonical_sbom(&sbom_path, Some(&repo))?;
    let inventory = canonical_inventory(&inventory_path, &repo)?;
    let audit = canonical_json_file(&audit_path)?;
    let support = support_for_target(&options.target)?;
    let binary_bytes = bounded_bytes(&options.binary, MAX_INPUT)?;
    let binary_sha = digest(&binary_bytes);
    let root = format!("kio-{}-{}", binding.version, binding.target);

    let provenance = canonical_json(&json!({
        "schema": "kio-rc-provenance-v1",
        "binding": binding,
        "support": support,
        "signing": signing_status(&binding.target)?,
        "tools": {"cargo_sbom": CARGO_SBOM_VERSION, "cargo_deny": CARGO_DENY_VERSION, "advisory_database": Value::Null},
        "digests": {"binary_sha256": binary_sha, "sbom_sha256": digest(&sbom), "dependency_inventory_sha256": digest(&inventory), "dependency_audit_sha256": digest(&audit)},
    }))?;
    let license = bounded_bytes(&repo.join("LICENSE.md"), MAX_JSON)?;
    let notice = bounded_bytes(&repo.join("NOTICE.txt"), MAX_JSON)?;
    let trademarks = bounded_bytes(&repo.join("TRADEMARKS.md"), MAX_JSON)?;
    let operations = bounded_bytes(&repo.join("docs/10-operations.md"), MAX_JSON)?;
    let mut payload = BTreeMap::new();
    payload.insert(
        format!("{root}/bin/{}", binary_name_for_target(&binding.target)),
        (binary_bytes, 0o755),
    );
    payload.insert(format!("{root}/LICENSE.md"), (license, 0o644));
    payload.insert(format!("{root}/NOTICE.txt"), (notice, 0o644));
    payload.insert(format!("{root}/OPERATIONS.md"), (operations, 0o644));
    payload.insert(format!("{root}/TRADEMARKS.md"), (trademarks, 0o644));
    payload.insert(
        format!("{root}/release/dependencies.json"),
        (inventory, 0o644),
    );
    payload.insert(
        format!("{root}/release/dependency-audit.json"),
        (audit, 0o644),
    );
    payload.insert(
        format!("{root}/release/provenance.json"),
        (provenance, 0o644),
    );
    payload.insert(format!("{root}/release/sbom.cdx.json"), (sbom, 0o644));
    let internal = internal_checksums(&payload)?;
    payload.insert(format!("{root}/release/checksums.json"), (internal, 0o644));
    let archive = options.output_dir.join(format!("{root}.tar.gz"));
    write_archive(&archive, &payload)?;
    let archive_sha = digest(&bounded_bytes(&archive, MAX_ARCHIVE)?);
    let checksums_name = archive
        .file_name()
        .and_then(OsStr::to_str)
        .ok_or_else(|| ReleaseError::Invalid("non-UTF8 archive name".into()))?
        .to_owned();
    let sidecar = ChecksumSidecar {
        schema: "kio-rc-checksums-v1".into(),
        archive: checksums_name,
        archive_sha256: archive_sha.clone(),
        binary_sha256: binary_sha,
        provenance_sha256: digest(
            payload
                .get(&format!("{root}/release/provenance.json"))
                .unwrap()
                .0
                .as_slice(),
        ),
        sbom_sha256: digest(
            payload
                .get(&format!("{root}/release/sbom.cdx.json"))
                .unwrap()
                .0
                .as_slice(),
        ),
        checksums_sha256: digest(
            payload
                .get(&format!("{root}/release/checksums.json"))
                .unwrap()
                .0
                .as_slice(),
        ),
    };
    let checksum = options.output_dir.join(format!("{root}.checksums.json"));
    create_new_bytes(&checksum, &canonical_json(&sidecar)?)?;
    Ok(PackageSummary {
        archive,
        checksum,
        archive_sha256: archive_sha,
        binding,
    })
}

pub fn verify_candidate(options: &VerifyCandidateOptions) -> Result<VerifySummary, ReleaseError> {
    require_regular(&options.archive, MAX_ARCHIVE)?;
    let bytes = bounded_bytes(&options.archive, MAX_ARCHIVE)?;
    let archive_sha = digest(&bytes);
    if !valid_digest(&options.expected_archive_sha256)
        || options.expected_archive_sha256 != archive_sha
    {
        return Err(ReleaseError::Verify(
            "archive differs from the independently retained digest".into(),
        ));
    }
    let sidecar_path = options
        .checksum
        .clone()
        .unwrap_or_else(|| default_sidecar(&options.archive));
    let sidecar: ChecksumSidecar = canonical_parse(&bounded_bytes(&sidecar_path, MAX_JSON)?)?;
    let archive_name = options
        .archive
        .file_name()
        .and_then(OsStr::to_str)
        .ok_or_else(|| ReleaseError::Verify("archive filename was not UTF-8".into()))?;
    if sidecar.schema != "kio-rc-checksums-v1"
        || sidecar.archive != archive_name
        || sidecar.archive_sha256 != archive_sha
    {
        return Err(ReleaseError::Verify(
            "external checksum does not bind archive".into(),
        ));
    }
    let files = read_archive(&bytes)?;
    let root = archive_root(&files)?;
    let provenance_path = format!("{root}/release/provenance.json");
    let provenance: Value = canonical_parse(
        files
            .get(&provenance_path)
            .ok_or_else(|| ReleaseError::Verify("missing provenance".into()))?,
    )?;
    let binding: Binding = serde_json::from_value(
        provenance
            .get("binding")
            .cloned()
            .ok_or_else(|| ReleaseError::Verify("missing provenance binding".into()))?,
    )?;
    validate_binding(&binding)?;
    if root != format!("kio-{}-{}", binding.version, binding.target) {
        return Err(ReleaseError::Verify(
            "archive root does not bind version and target".into(),
        ));
    }
    let expected = expected_names(&root, binary_name_for_target(&binding.target));
    if files.keys().collect::<Vec<_>>() != expected.iter().collect::<Vec<_>>() {
        return Err(ReleaseError::Verify(
            "archive entries are not the fixed canonical layout".into(),
        ));
    }
    if let Some(expected) = &options.expected_commit
        && &binding.commit != expected
    {
        return Err(ReleaseError::Verify("unexpected commit".into()));
    }
    if let Some(expected) = &options.expected_lock_sha256
        && &binding.cargo_lock_sha256 != expected
    {
        return Err(ReleaseError::Verify("unexpected Cargo.lock digest".into()));
    }
    if let Some(expected_repo) = &options.expected_repo {
        verify_source_binding(expected_repo, &binding)?;
    }
    let support = provenance
        .get("support")
        .and_then(Value::as_str)
        .ok_or_else(|| ReleaseError::Verify("missing support".into()))?;
    if support != support_for_target(&binding.target)? {
        return Err(ReleaseError::Verify("support policy mismatch".into()));
    }
    if provenance.get("schema").and_then(Value::as_str) != Some("kio-rc-provenance-v1") {
        return Err(ReleaseError::Verify("wrong provenance schema".into()));
    }
    if provenance.as_object().map(serde_json::Map::len) != Some(6) {
        return Err(ReleaseError::Verify(
            "provenance has missing or unknown fields".into(),
        ));
    }
    let tools = provenance
        .get("tools")
        .and_then(Value::as_object)
        .ok_or_else(|| ReleaseError::Verify("missing provenance tools".into()))?;
    if tools.get("cargo_sbom").and_then(Value::as_str) != Some(CARGO_SBOM_VERSION)
        || tools.get("cargo_deny").and_then(Value::as_str) != Some(CARGO_DENY_VERSION)
        || !tools.get("advisory_database").is_some_and(Value::is_null)
        || tools.len() != 3
    {
        return Err(ReleaseError::Verify(
            "provenance tool policy mismatch".into(),
        ));
    }
    // Every JSON payload has a byte-level canonical representation.  This is
    // intentionally checked before interpreting any audit/SBOM fields.
    let sbom: Value =
        canonical_parse(files.get(&format!("{root}/release/sbom.cdx.json")).unwrap())?;
    verify_sbom(&sbom, &binding)?;
    let inventory: Value = canonical_parse(
        files
            .get(&format!("{root}/release/dependencies.json"))
            .unwrap(),
    )?;
    verify_inventory(&inventory, &binding)?;
    let _: Value = canonical_parse(
        files
            .get(&format!("{root}/release/dependency-audit.json"))
            .unwrap(),
    )?;
    let audit: Value = canonical_parse(
        files
            .get(&format!("{root}/release/dependency-audit.json"))
            .unwrap(),
    )?;
    if audit.get("schema").and_then(Value::as_str) != Some("cargo-deny-receipt-v1")
        || audit.get("tool").and_then(Value::as_str) != Some("cargo-deny")
        || audit.get("version").and_then(Value::as_str) != Some(CARGO_DENY_VERSION)
        || audit.get("status").and_then(Value::as_str) != Some("passed")
        || !audit.get("advisory_database").is_some_and(Value::is_null)
        || audit.get("checks") != Some(&json!(["bans", "licenses", "sources"]))
        || audit.as_object().map(serde_json::Map::len) != Some(6)
    {
        return Err(ReleaseError::Verify(
            "dependency audit receipt mismatch".into(),
        ));
    }
    let bin = files
        .get(&format!(
            "{root}/bin/{}",
            binary_name_for_target(&binding.target)
        ))
        .ok_or_else(|| ReleaseError::Verify("missing binary".into()))?;
    require_binding(&binding, &read_binding_bytes(bin)?)?;
    let checksums: Value = canonical_parse(
        files
            .get(&format!("{root}/release/checksums.json"))
            .ok_or_else(|| ReleaseError::Verify("missing internal checksums".into()))?,
    )?;
    check_internal_digests(&files, &root, &checksums)?;
    let provenance_digests = provenance
        .get("digests")
        .and_then(Value::as_object)
        .ok_or_else(|| ReleaseError::Verify("missing provenance digests".into()))?;
    if provenance_digests.len() != 4 {
        return Err(ReleaseError::Verify(
            "provenance digests have missing or unknown fields".into(),
        ));
    }
    for (name, actual) in [
        ("binary_sha256", digest(bin)),
        (
            "sbom_sha256",
            digest(files.get(&format!("{root}/release/sbom.cdx.json")).unwrap()),
        ),
        (
            "dependency_inventory_sha256",
            digest(
                files
                    .get(&format!("{root}/release/dependencies.json"))
                    .unwrap(),
            ),
        ),
        (
            "dependency_audit_sha256",
            digest(
                files
                    .get(&format!("{root}/release/dependency-audit.json"))
                    .unwrap(),
            ),
        ),
    ] {
        if provenance_digests.get(name).and_then(Value::as_str) != Some(actual.as_str()) {
            return Err(ReleaseError::Verify(
                "provenance payload digest mismatch".into(),
            ));
        }
    }
    if provenance.get("signing") != Some(&signing_status(&binding.target)?) {
        return Err(ReleaseError::Verify("ambiguous signing status".into()));
    }
    if sidecar.binary_sha256 != digest(bin)
        || sidecar.provenance_sha256 != digest(files.get(&provenance_path).unwrap())
        || sidecar.sbom_sha256
            != digest(files.get(&format!("{root}/release/sbom.cdx.json")).unwrap())
        || sidecar.checksums_sha256
            != digest(
                files
                    .get(&format!("{root}/release/checksums.json"))
                    .unwrap(),
            )
    {
        return Err(ReleaseError::Verify(
            "sidecar payload digest mismatch".into(),
        ));
    }
    Ok(VerifySummary {
        root,
        archive_sha256: archive_sha,
        binding,
        support: support.into(),
    })
}

pub fn smoke_candidate(options: &SmokeCandidateOptions) -> Result<SmokeSummary, ReleaseError> {
    let verified = verify_candidate(&options.verify)?;
    create_empty_dir(&options.work_dir)?;
    let archive = bounded_bytes(&options.verify.archive, MAX_ARCHIVE)?;
    let files = read_archive(&archive)?;
    for (name, bytes) in &files {
        let relative = Path::new(name);
        let destination = options.work_dir.join(relative);
        if !destination.starts_with(&options.work_dir) {
            return Err(ReleaseError::Verify(
                "extraction escaped destination".into(),
            ));
        }
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)?;
        }
        create_new_bytes(&destination, bytes)?;
        if name.ends_with(&format!(
            "/bin/{}",
            binary_name_for_target(&verified.binding.target)
        )) {
            set_executable(&destination)?;
        }
    }
    let binary = options
        .work_dir
        .join(&verified.root)
        .join("bin")
        .join(binary_name_for_target(&verified.binding.target));
    let isolated = options.work_dir.join("isolated");
    fs::create_dir_all(&isolated)?;
    for name in ["xdg-config", "xdg-cache", "tmp", "appdata", "localappdata"] {
        fs::create_dir_all(isolated.join(name))?;
    }
    let scope = isolated.join("manual-scope");
    fs::create_dir_all(&scope)?;
    fs::write(scope.join("release-smoke.txt"), b"release smoke marker\n")?;
    let mut base = Command::new(&binary);
    base.env("HOME", &isolated)
        .env("XDG_CONFIG_HOME", isolated.join("xdg-config"))
        .env("XDG_CACHE_HOME", isolated.join("xdg-cache"))
        .env("TMPDIR", isolated.join("tmp"));
    let version = base.arg("--version").output()?;
    if !version.status.success()
        || !String::from_utf8_lossy(&version.stdout).contains(&verified.binding.version)
    {
        return Err(ReleaseError::Verify(
            "extracted binary version failed".into(),
        ));
    }
    run_smoke(
        &binary,
        &isolated,
        &[
            "--json",
            "init",
            scope
                .to_str()
                .ok_or_else(|| ReleaseError::Invalid("non-UTF8 scope".into()))?,
        ],
    )?;
    run_smoke_in(
        &binary,
        &isolated,
        &scope,
        &["--json", "index", "--approve", "--offline"],
    )?;
    let search = run_smoke_in(
        &binary,
        &isolated,
        &scope,
        &[
            "--json",
            "search",
            "release smoke marker",
            "--mode",
            "text",
            "--offline",
        ],
    )?;
    let result: Value = serde_json::from_slice(&search)?;
    let pointer = result
        .pointer("/results/0/evidence_pointer")
        .or_else(|| result.pointer("/result/0/evidence_pointer"))
        .ok_or_else(|| ReleaseError::Verify("smoke search returned no evidence pointer".into()))?;
    let pointer = serde_json::to_string(pointer)?;
    run_smoke_in(&binary, &isolated, &scope, &["--json", "open", &pointer])?;
    let summary = SmokeSummary {
        schema: "kio-rc-smoke-v1".into(),
        status: "passed".into(),
        archive_sha256: verified.archive_sha256,
        version: verified.binding.version,
        commit: verified.binding.commit,
        target: verified.binding.target.clone(),
        support: support_for_target(&verified.binding.target)?.into(),
        operations: vec![
            "version".into(),
            "init".into(),
            "index".into(),
            "search".into(),
            "open".into(),
        ],
    };
    if let Some(receipt) = &options.receipt {
        create_new_bytes(receipt, &canonical_json(&summary)?)?;
    }
    Ok(summary)
}

pub fn compare_candidate_dirs(left: &Path, right: &Path) -> Result<(), ReleaseError> {
    let left = canonical_dir_files(left)?;
    let right = canonical_dir_files(right)?;
    if left == right {
        return Ok(());
    }
    let diagnostic = compare_diagnostic(&left, &right)?;
    Err(ReleaseError::Verify(
        String::from_utf8(canonical_json(&diagnostic)?)
            .map_err(|_| ReleaseError::Verify("comparison diagnostic is not UTF-8".into()))?,
    ))
}

fn compare_diagnostic(
    left: &BTreeMap<String, Vec<u8>>,
    right: &BTreeMap<String, Vec<u8>>,
) -> Result<CompareDiagnostic, ReleaseError> {
    let names = left
        .keys()
        .chain(right.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut outputs = Vec::with_capacity(names.len());
    for name in names {
        let left_bytes = left.get(&name);
        let right_bytes = right.get(&name);
        let matches = left_bytes == right_bytes;
        let difference = (!matches)
            .then(|| {
                output_difference(
                    &name,
                    left_bytes.map(Vec::as_slice),
                    right_bytes.map(Vec::as_slice),
                )
            })
            .transpose()?;
        outputs.push(OutputDiagnostic {
            name: diagnostic_label(&name),
            matches,
            left: left_bytes.map(|bytes| content_digest(bytes)),
            right: right_bytes.map(|bytes| content_digest(bytes)),
            difference,
        });
    }
    Ok(CompareDiagnostic {
        schema: "kio-rc-compare-diagnostic-v1",
        outputs,
    })
}

fn content_digest(bytes: &[u8]) -> ContentDigest {
    ContentDigest {
        size: bytes.len(),
        sha256: digest(bytes),
    }
}

fn output_difference(
    name: &str,
    left: Option<&[u8]>,
    right: Option<&[u8]>,
) -> Result<OutputDifference, ReleaseError> {
    let (Some(left), Some(right)) = (left, right) else {
        return Ok(OutputDifference {
            classification: "missing_output",
            json_fields: None,
            archive_entries: None,
        });
    };
    if name.ends_with(".json") {
        return Ok(
            match (canonical_json_value(left), canonical_json_value(right)) {
                (Ok(left), Ok(right)) => OutputDifference {
                    classification: "canonical_json",
                    json_fields: Some(json_field_differences(&left, &right)?),
                    archive_entries: None,
                },
                _ => OutputDifference {
                    classification: "malformed_or_noncanonical_json",
                    json_fields: None,
                    archive_entries: None,
                },
            },
        );
    }
    if name.ends_with(".tar.gz") {
        return Ok(match (read_archive(left), read_archive(right)) {
            (Ok(left), Ok(right)) => OutputDifference {
                classification: "canonical_archive",
                json_fields: None,
                archive_entries: Some(archive_entry_diagnostics(&left, &right)),
            },
            _ => OutputDifference {
                classification: "malformed_or_noncanonical_archive",
                json_fields: None,
                archive_entries: None,
            },
        });
    }
    Ok(OutputDifference {
        classification: "byte_payload",
        json_fields: None,
        archive_entries: None,
    })
}

fn canonical_json_value(bytes: &[u8]) -> Result<Value, ReleaseError> {
    canonical_parse(bytes)
}

fn json_field_differences(
    left: &Value,
    right: &Value,
) -> Result<JsonFieldDifferences, ReleaseError> {
    let mut fields = Vec::new();
    collect_json_field_differences(left, right, "", &mut fields)?;
    let truncated = fields.len() > MAX_JSON_DIFF_FIELDS;
    fields.truncate(MAX_JSON_DIFF_FIELDS);
    Ok(JsonFieldDifferences { truncated, fields })
}

fn collect_json_field_differences(
    left: &Value,
    right: &Value,
    path: &str,
    fields: &mut Vec<JsonFieldDiagnostic>,
) -> Result<(), ReleaseError> {
    if left == right {
        return Ok(());
    }
    if fields.len() > MAX_JSON_DIFF_FIELDS {
        return Ok(());
    }
    match (left, right) {
        (Value::Object(left), Value::Object(right)) => {
            let keys = left
                .keys()
                .chain(right.keys())
                .cloned()
                .collect::<BTreeSet<_>>();
            for key in keys {
                if fields.len() > MAX_JSON_DIFF_FIELDS {
                    break;
                }
                let child = format!("{path}/{}", json_pointer_segment(&key));
                match (left.get(&key), right.get(&key)) {
                    (Some(left), Some(right)) => {
                        collect_json_field_differences(left, right, &child, fields)?
                    }
                    (left, right) => fields.push(json_field_diagnostic(&child, left, right)?),
                }
            }
        }
        (Value::Array(left), Value::Array(right)) => {
            for index in 0..left.len().max(right.len()) {
                if fields.len() > MAX_JSON_DIFF_FIELDS {
                    break;
                }
                let child = format!("{path}/{index}");
                match (left.get(index), right.get(index)) {
                    (Some(left), Some(right)) => {
                        collect_json_field_differences(left, right, &child, fields)?
                    }
                    (left, right) => fields.push(json_field_diagnostic(&child, left, right)?),
                }
            }
        }
        _ => fields.push(json_field_diagnostic(path, Some(left), Some(right))?),
    }
    Ok(())
}

fn json_field_diagnostic(
    path: &str,
    left: Option<&Value>,
    right: Option<&Value>,
) -> Result<JsonFieldDiagnostic, ReleaseError> {
    Ok(JsonFieldDiagnostic {
        path: bounded_diagnostic_path(path),
        left_kind: left.map(json_kind),
        right_kind: right.map(json_kind),
        left_canonical_sha256: left.map(canonical_value_digest).transpose()?,
        right_canonical_sha256: right.map(canonical_value_digest).transpose()?,
    })
}

fn bounded_diagnostic_path(path: &str) -> String {
    if path.len() <= MAX_DIAGNOSTIC_PATH_BYTES {
        path.into()
    } else {
        format!("sha256:{}", digest(path.as_bytes()))
    }
}

fn canonical_value_digest(value: &Value) -> Result<String, ReleaseError> {
    Ok(digest(&canonical_json(value)?))
}

fn json_kind(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "boolean",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

fn archive_entry_diagnostics(
    left: &BTreeMap<String, Vec<u8>>,
    right: &BTreeMap<String, Vec<u8>>,
) -> Vec<ArchiveEntryDiagnostic> {
    left.keys()
        .chain(right.keys())
        .cloned()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .map(|path| {
            let left_bytes = left.get(&path);
            let right_bytes = right.get(&path);
            let pe32_plus =
                (left_bytes != right_bytes && path.ends_with("/bin/kio.exe")).then(|| {
                    PeDifferenceDiagnostic {
                        left: pe_diagnostic(left_bytes.map(Vec::as_slice)),
                        right: pe_diagnostic(right_bytes.map(Vec::as_slice)),
                    }
                });
            ArchiveEntryDiagnostic {
                path: diagnostic_label(&path),
                matches: left_bytes == right_bytes,
                left: left_bytes.map(|bytes| content_digest(bytes)),
                right: right_bytes.map(|bytes| content_digest(bytes)),
                pe32_plus,
            }
        })
        .collect()
}

fn pe_diagnostic(bytes: Option<&[u8]>) -> PeDiagnostic {
    match bytes {
        Some(bytes) => match parse_pe32_plus(bytes) {
            Ok(metadata) => PeDiagnostic {
                metadata: Some(metadata),
                reason: None,
            },
            Err(reason) => PeDiagnostic {
                metadata: None,
                reason: Some(reason),
            },
        },
        None => PeDiagnostic {
            metadata: None,
            reason: Some("missing_payload"),
        },
    }
}

fn parse_pe32_plus(bytes: &[u8]) -> Result<Pe32PlusMetadata, &'static str> {
    let dos = bytes.get(..64).ok_or("truncated_header")?;
    if dos.get(..2) != Some(b"MZ") {
        return Err("invalid_signature");
    }
    let pe_offset = usize::try_from(pe_u32(dos, 0x3c).ok_or("truncated_header")?)
        .map_err(|_| "truncated_header")?;
    let coff = bytes
        .get(pe_offset..pe_offset.checked_add(24).ok_or("truncated_header")?)
        .ok_or("truncated_header")?;
    if coff.get(..4) != Some(b"PE\0\0") {
        return Err("invalid_signature");
    }
    let machine = pe_u16(coff, 4).ok_or("truncated_header")?;
    let section_count = usize::from(pe_u16(coff, 6).ok_or("truncated_header")?);
    if section_count > MAX_PE_SECTIONS {
        return Err("excessive_sections");
    }
    let coff_timestamp = pe_u32(coff, 8).ok_or("truncated_header")?;
    let optional_size = usize::from(pe_u16(coff, 20).ok_or("truncated_header")?);
    let optional_offset = pe_offset.checked_add(24).ok_or("truncated_header")?;
    let optional = bytes
        .get(
            optional_offset
                ..optional_offset
                    .checked_add(optional_size)
                    .ok_or("truncated_header")?,
        )
        .ok_or("truncated_header")?;
    if pe_u16(optional, 0) != Some(0x20b) {
        return Err("unsupported_optional_magic");
    }
    let checksum = pe_u32(optional, 64).ok_or("truncated_header")?;
    let rva_count = usize::try_from(pe_u32(optional, 108).ok_or("truncated_header")?)
        .map_err(|_| "truncated_header")?;
    if rva_count <= 6 {
        return Err("invalid_debug_directory");
    }
    let debug_directory = 112usize
        .checked_add(6usize.checked_mul(8).ok_or("truncated_header")?)
        .ok_or("truncated_header")?;
    let debug_rva = pe_u32(optional, debug_directory).ok_or("truncated_header")?;
    let debug_size = pe_u32(optional, debug_directory + 4).ok_or("truncated_header")?;
    let section_offset = optional_offset
        .checked_add(optional_size)
        .ok_or("truncated_header")?;
    let section_table_size = section_count.checked_mul(40).ok_or("invalid_section")?;
    let table = bytes
        .get(
            section_offset
                ..section_offset
                    .checked_add(section_table_size)
                    .ok_or("invalid_section")?,
        )
        .ok_or("invalid_section")?;
    let mut parsed_sections = Vec::with_capacity(section_count);
    let mut section_ranges = Vec::with_capacity(section_count);
    for index in 0..section_count {
        let record = table
            .get(index.checked_mul(40).ok_or("invalid_section")?..)
            .and_then(|tail| tail.get(..40))
            .ok_or("invalid_section")?;
        let virtual_size = pe_u32(record, 8).ok_or("invalid_section")?;
        let rva = pe_u32(record, 12).ok_or("invalid_section")?;
        let raw_size = pe_u32(record, 16).ok_or("invalid_section")?;
        let raw_offset = pe_u32(record, 20).ok_or("invalid_section")?;
        let raw_end = usize::try_from(raw_offset)
            .ok()
            .and_then(|start| {
                usize::try_from(raw_size)
                    .ok()
                    .and_then(|size| start.checked_add(size))
            })
            .ok_or("invalid_section")?;
        let raw_start = usize::try_from(raw_offset).map_err(|_| "invalid_section")?;
        bytes.get(raw_start..raw_end).ok_or("invalid_section")?;
        if raw_size != 0 {
            section_ranges.push((
                raw_offset,
                raw_offset.checked_add(raw_size).ok_or("invalid_section")?,
            ));
        }
        parsed_sections.push(ParsedPeSection {
            name: record[..8].try_into().map_err(|_| "invalid_section")?,
            rva,
            virtual_size,
            raw_size,
            raw_offset,
        });
    }
    if !non_overlapping_nonempty_ranges(&mut section_ranges) {
        return Err("invalid_section");
    }
    let mut sections = Vec::with_capacity(section_count);
    for section in &parsed_sections {
        let raw_start = usize::try_from(section.raw_offset).map_err(|_| "invalid_section")?;
        let raw_end = raw_start
            .checked_add(usize::try_from(section.raw_size).map_err(|_| "invalid_section")?)
            .ok_or("invalid_section")?;
        let raw = bytes.get(raw_start..raw_end).ok_or("invalid_section")?;
        sections.push(PeSectionDiagnostic {
            name_hex: hex_bytes(&section.name),
            rva: section.rva,
            virtual_size: section.virtual_size,
            raw_size: section.raw_size,
            raw_offset: section.raw_offset,
            raw_sha256: digest(raw),
        });
    }

    let debug_entries = if debug_rva == 0 && debug_size == 0 {
        Vec::new()
    } else {
        if debug_rva == 0 || debug_size == 0 || debug_size % 28 != 0 {
            return Err("invalid_debug_directory");
        }
        let count = usize::try_from(debug_size / 28).map_err(|_| "invalid_debug_directory")?;
        if count > MAX_PE_DEBUG_ENTRIES {
            return Err("excessive_debug_entries");
        }
        let debug = pe_rva_slice(bytes, &parsed_sections, debug_rva, debug_size)
            .ok_or("invalid_debug_directory")?;
        let mut entries = Vec::with_capacity(count);
        let mut debug_payload_ranges = Vec::with_capacity(count);
        for index in 0..count {
            let entry = debug
                .get(index.checked_mul(28).ok_or("invalid_debug_directory")?..)
                .and_then(|tail| tail.get(..28))
                .ok_or("invalid_debug_directory")?;
            let timestamp = pe_u32(entry, 4).ok_or("invalid_debug_directory")?;
            let kind = pe_u32(entry, 12).ok_or("invalid_debug_directory")?;
            let size = pe_u32(entry, 16).ok_or("invalid_debug_directory")?;
            let payload_rva = pe_u32(entry, 20).ok_or("invalid_debug_directory")?;
            let payload_offset = pe_u32(entry, 24).ok_or("invalid_debug_directory")?;
            let (payload, payload_range) =
                pe_debug_payload(bytes, &parsed_sections, payload_rva, payload_offset, size)?;
            if size != 0 {
                debug_payload_ranges.push(payload_range);
                if !non_overlapping_nonempty_ranges(&mut debug_payload_ranges) {
                    return Err("invalid_debug_payload");
                }
            }
            let codeview_rsds = if kind == 2 && payload.get(..4) == Some(b"RSDS") {
                Some(parse_codeview_rsds(payload)?)
            } else {
                None
            };
            entries.push(PeDebugEntryDiagnostic {
                kind,
                timestamp,
                size,
                raw_sha256: digest(payload),
                codeview_rsds,
            });
        }
        entries
    };
    Ok(Pe32PlusMetadata {
        machine,
        coff_timestamp,
        checksum,
        reproducible: debug_entries.iter().any(|entry| entry.kind == 16),
        sections,
        debug_entries,
    })
}

fn pe_u16(bytes: &[u8], offset: usize) -> Option<u16> {
    bytes
        .get(offset..offset.checked_add(2)?)
        .map(|value| u16::from_le_bytes([value[0], value[1]]))
}

fn pe_u32(bytes: &[u8], offset: usize) -> Option<u32> {
    bytes
        .get(offset..offset.checked_add(4)?)
        .map(|value| u32::from_le_bytes([value[0], value[1], value[2], value[3]]))
}

fn pe_rva_slice<'a>(
    bytes: &'a [u8],
    sections: &[ParsedPeSection],
    rva: u32,
    size: u32,
) -> Option<&'a [u8]> {
    let (raw_start, raw_end) = pe_rva_raw_range(sections, rva, size)?;
    bytes.get(raw_start..raw_end)
}

fn pe_rva_raw_range(sections: &[ParsedPeSection], rva: u32, size: u32) -> Option<(usize, usize)> {
    let end = rva.checked_add(size)?;
    let section = sections.iter().find(|section| {
        let span = section.virtual_size.max(section.raw_size);
        section
            .rva
            .checked_add(span)
            .is_some_and(|section_end| rva >= section.rva && end <= section_end)
    })?;
    let relative = rva.checked_sub(section.rva)?;
    let raw_start = section.raw_offset.checked_add(relative)?;
    let raw_end = raw_start.checked_add(size)?;
    if raw_end > section.raw_offset.checked_add(section.raw_size)? {
        return None;
    }
    Some((
        usize::try_from(raw_start).ok()?,
        usize::try_from(raw_end).ok()?,
    ))
}

fn pe_debug_payload<'a>(
    bytes: &'a [u8],
    sections: &[ParsedPeSection],
    rva: u32,
    offset: u32,
    size: u32,
) -> Result<(&'a [u8], (u32, u32)), &'static str> {
    if size == 0 {
        return if rva == 0 && offset == 0 {
            Ok((&bytes[..0], (0, 0)))
        } else {
            Err("invalid_debug_payload")
        };
    }
    let (mapped_start, mapped_end) =
        pe_rva_raw_range(sections, rva, size).ok_or("invalid_debug_payload")?;
    let expected_offset = u32::try_from(mapped_start).map_err(|_| "invalid_debug_payload")?;
    if offset != expected_offset {
        return Err("invalid_debug_payload");
    }
    let raw = bytes
        .get(mapped_start..mapped_end)
        .ok_or("invalid_debug_payload")?;
    let raw_end = offset.checked_add(size).ok_or("invalid_debug_payload")?;
    Ok((raw, (offset, raw_end)))
}

fn non_overlapping_nonempty_ranges(ranges: &mut [(u32, u32)]) -> bool {
    ranges.sort_unstable();
    ranges.windows(2).all(|pair| pair[0].1 <= pair[1].0)
}

fn parse_codeview_rsds(bytes: &[u8]) -> Result<CodeViewRsdsDiagnostic, &'static str> {
    let fixed = bytes.get(..24).ok_or("invalid_codeview")?;
    let path_and_nul = bytes.get(24..).ok_or("invalid_codeview")?;
    let nul = path_and_nul
        .iter()
        .position(|byte| *byte == 0)
        .ok_or("invalid_codeview")?;
    let path = &path_and_nul[..nul];
    if path.is_empty() {
        return Err("invalid_codeview");
    }
    Ok(CodeViewRsdsDiagnostic {
        guid_hex: hex_bytes(&fixed[4..20]),
        age: pe_u32(fixed, 20).ok_or("invalid_codeview")?,
        pdb_path_bytes: path.len(),
        pdb_path_sha256: digest(path),
        pdb_path_class: if is_absolute_pdb_path(path) {
            "absolute"
        } else {
            "relative"
        },
    })
}

fn is_absolute_pdb_path(path: &[u8]) -> bool {
    path.starts_with(b"/")
        || path.starts_with(b"\\\\")
        || path.starts_with(b"//")
        || matches!(path, [drive, b':', slash, ..] if drive.is_ascii_alphabetic() && matches!(slash, b'\\' | b'/'))
}

fn hex_bytes(bytes: &[u8]) -> String {
    let mut result = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        use std::fmt::Write as _;
        let _ = write!(result, "{byte:02x}");
    }
    result
}

fn diagnostic_label(value: &str) -> String {
    if value.len() <= 96
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-' | b'/'))
        && !value.starts_with('/')
        && !value
            .split('/')
            .any(|segment| segment == ".." || segment.is_empty())
    {
        value.into()
    } else {
        format!("sha256:{}", digest(value.as_bytes()))
    }
}

fn json_pointer_segment(key: &str) -> String {
    if key.len() > 96 || key.bytes().any(|byte| byte.is_ascii_control()) {
        format!("sha256:{}", digest(key.as_bytes()))
    } else {
        key.replace('~', "~0").replace('/', "~1")
    }
}

fn canonical_repo(input: &Path) -> Result<PathBuf, ReleaseError> {
    let repo = input.canonicalize()?;
    if !repo.join(".git").exists() {
        return Err(ReleaseError::Invalid("repo has no .git".into()));
    }
    Ok(repo)
}
fn repo_binding(repo: &Path, candidate: &str, target: &str) -> Result<Binding, ReleaseError> {
    reject_dirty(repo)?;
    let head = git(repo, &["rev-parse", "HEAD"])?;
    if candidate.len() != 40 || candidate != head {
        return Err(ReleaseError::Invalid(
            "candidate SHA must exactly equal checked-out full HEAD".into(),
        ));
    }
    let version = workspace_version(repo)?;
    if version != RC_VERSION {
        return Err(ReleaseError::Invalid(format!(
            "workspace version {version} is not {RC_VERSION}"
        )));
    }
    let rust_version = rust_version()?;
    if !rust_version.starts_with("rustc 1.98.0 ") {
        return Err(ReleaseError::Invalid(format!(
            "Rust 1.98.0 required, got {rust_version}"
        )));
    }
    let binding = Binding {
        version,
        commit: head,
        tree: git(repo, &["rev-parse", "HEAD^{tree}"])?,
        cargo_lock_sha256: digest(&bounded_bytes(&repo.join("Cargo.lock"), MAX_JSON)?),
        toolchain_sha256: digest(&bounded_bytes(&repo.join("rust-toolchain.toml"), MAX_JSON)?),
        rust_version,
        target: target.to_owned(),
        features: "all-features".into(),
        profile: "release".into(),
    };
    validate_binding(&binding)?;
    Ok(binding)
}
fn reject_dirty(repo: &Path) -> Result<(), ReleaseError> {
    if !git(repo, &["status", "--porcelain=v1", "--untracked-files=no"])?.is_empty() {
        Err(ReleaseError::Invalid(
            "tracked worktree or index is dirty".into(),
        ))
    } else {
        Ok(())
    }
}
fn workspace_version(repo: &Path) -> Result<String, ReleaseError> {
    let s = fs::read_to_string(repo.join("Cargo.toml"))?;
    let value: toml::Value =
        toml::from_str(&s).map_err(|e| ReleaseError::Invalid(format!("Cargo.toml: {e}")))?;
    value
        .get("workspace")
        .and_then(|v| v.get("package"))
        .and_then(|v| v.get("version"))
        .and_then(toml::Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| ReleaseError::Invalid("workspace.package.version missing".into()))
}
fn cargo_command(repo: &Path, b: &Binding, target_dir: &Path) -> Result<Command, ReleaseError> {
    let mut cmd = Command::new("cargo");
    cmd.current_dir(repo)
        .args([
            "+1.98.0",
            "build",
            "--release",
            "--locked",
            "--all-features",
            "-p",
            "kio-cli",
            "--bin",
            "kio",
            "--target",
            &b.target,
            "--target-dir",
        ])
        .arg(target_dir);
    cmd.env_remove("RUSTFLAGS")
        .env_remove("CARGO_BUILD_RUSTFLAGS")
        .env_remove("CARGO_ENCODED_RUSTFLAGS")
        .env_remove(format!(
            "CARGO_TARGET_{}_RUSTFLAGS",
            b.target.to_ascii_uppercase().replace('-', "_")
        ));
    if let Some(flags) = candidate_rustflags(&b.target)? {
        cmd.env("CARGO_ENCODED_RUSTFLAGS", flags);
    }
    if b.target.ends_with("-apple-darwin") {
        // Match Rust's supported macOS floor for every C/assembly dependency;
        // otherwise the host SDK can silently stamp objects with the host OS.
        cmd.env("MACOSX_DEPLOYMENT_TARGET", "11.0");
    }
    for (key, value) in binding_env(b) {
        cmd.env(key, value);
    }
    Ok(cmd)
}
fn candidate_rustflags(target: &str) -> Result<Option<String>, ReleaseError> {
    if !target.ends_with("-apple-darwin") {
        return Ok(None);
    }
    let linker = pinned_rust_lld(target)?;
    let linker = linker
        .to_str()
        .ok_or_else(|| ReleaseError::Invalid("rust-lld path was not UTF-8".into()))?;
    if linker.contains(['\n', '\r', '\0', '\u{1f}']) {
        return Err(ReleaseError::Invalid(
            "rust-lld path contains an unsafe flag separator".into(),
        ));
    }
    Ok(Some(encoded_macos_linker_flags(linker)))
}
fn encoded_macos_linker_flags(linker: &str) -> String {
    // LLD 22 computes LC_UUID before filling its linker-generated ad-hoc
    // signature hashes, so fresh output buffers can otherwise perturb the UUID
    // and the signature that covers it. LC_UUID is optional for execution;
    // retaining LLD's ad-hoc envelope keeps arm64 binaries executable without
    // invoking codesign or using a signing identity.
    format!(
        "-C\u{1f}linker={linker}\u{1f}-C\u{1f}linker-flavor=ld64.lld\u{1f}-C\u{1f}link-arg=-no_uuid"
    )
}
fn pinned_rust_lld(target: &str) -> Result<PathBuf, ReleaseError> {
    let output = Command::new("rustc")
        .args(["+1.98.0", "--print", "sysroot"])
        .output()?;
    if !output.status.success() {
        return Err(ReleaseError::Invalid(
            "rustc +1.98.0 --print sysroot failed".into(),
        ));
    }
    let sysroot = String::from_utf8(output.stdout)
        .map_err(|_| ReleaseError::Invalid("rustc sysroot was not UTF-8".into()))?;
    let linker = PathBuf::from(sysroot.trim())
        .join("lib")
        .join("rustlib")
        .join(target)
        .join("bin")
        .join("rust-lld");
    require_regular(&linker, MAX_INPUT)?;
    Ok(linker)
}
fn binding_env(b: &Binding) -> [(&'static str, String); 10] {
    [
        ("KIO_RC_BUILD", "1".into()),
        ("KIO_RC_VERSION", b.version.clone()),
        ("KIO_RC_COMMIT_SHA", b.commit.clone()),
        ("KIO_RC_GIT_TREE", b.tree.clone()),
        ("KIO_RC_CARGO_LOCK_SHA256", b.cargo_lock_sha256.clone()),
        ("KIO_RC_TOOLCHAIN_SHA256", b.toolchain_sha256.clone()),
        ("KIO_RC_RUSTC_VERSION", b.rust_version.clone()),
        ("KIO_RC_TARGET", b.target.clone()),
        ("KIO_RC_FEATURES", b.features.clone()),
        ("KIO_RC_PROFILE", b.profile.clone()),
    ]
}
fn git(repo: &Path, args: &[&str]) -> Result<String, ReleaseError> {
    let output = Command::new("git").current_dir(repo).args(args).output()?;
    if !output.status.success() {
        return Err(ReleaseError::Invalid(format!(
            "git {} failed",
            args.join(" ")
        )));
    }
    String::from_utf8(output.stdout)
        .map(|s| s.trim().to_owned())
        .map_err(|_| ReleaseError::Invalid("git output was not UTF-8".into()))
}
fn rust_version() -> Result<String, ReleaseError> {
    let out = Command::new("rustc")
        .arg("+1.98.0")
        .arg("--version")
        .output()?;
    if !out.status.success() {
        return Err(ReleaseError::Invalid(
            "rustc +1.98.0 --version failed".into(),
        ));
    }
    String::from_utf8(out.stdout)
        .map(|s| s.trim().to_owned())
        .map_err(|_| ReleaseError::Invalid("rust version was not UTF-8".into()))
}
fn rust_host() -> Result<String, ReleaseError> {
    let out = Command::new("rustc").arg("+1.98.0").arg("-vV").output()?;
    if !out.status.success() {
        return Err(ReleaseError::Invalid("rustc +1.98.0 -vV failed".into()));
    }
    let text = String::from_utf8(out.stdout)
        .map_err(|_| ReleaseError::Invalid("rustc host not UTF-8".into()))?;
    text.lines()
        .find_map(|line| line.strip_prefix("host: "))
        .map(str::to_owned)
        .ok_or_else(|| ReleaseError::Invalid("rustc host missing".into()))
}
fn binary_name() -> &'static str {
    if cfg!(windows) { "kio.exe" } else { "kio" }
}
fn binary_name_for_target(target: &str) -> &'static str {
    if target.ends_with("-pc-windows-msvc") || target.ends_with("-pc-windows-gnu") {
        "kio.exe"
    } else {
        "kio"
    }
}
fn support_for_target(target: &str) -> Result<&'static str, ReleaseError> {
    if target.ends_with("-pc-windows-msvc") || target.ends_with("-pc-windows-gnu") {
        Ok("experimental")
    } else if target.ends_with("-apple-darwin") || target.ends_with("-unknown-linux-gnu") {
        Ok("supported")
    } else {
        Err(ReleaseError::Invalid(format!(
            "unsupported RC target {target}"
        )))
    }
}
fn signing_status(target: &str) -> Result<Value, ReleaseError> {
    support_for_target(target)?;
    let (macos_adhoc_signature, apple_notarization, windows_authenticode) =
        if target.ends_with("-apple-darwin") {
            ("linker-generated", "not-notarized", "not-applicable")
        } else if target.ends_with("-pc-windows-msvc") || target.ends_with("-pc-windows-gnu") {
            ("not-applicable", "not-applicable", "unsigned")
        } else {
            ("not-applicable", "not-applicable", "not-applicable")
        };
    Ok(json!({
        "publisher_identity_signature": "absent",
        "macos_adhoc_signature": macos_adhoc_signature,
        "apple_notarization": apple_notarization,
        "windows_authenticode": windows_authenticode,
        "detached_signature": "absent"
    }))
}
fn validate_binding(b: &Binding) -> Result<(), ReleaseError> {
    if b.version != RC_VERSION
        || b.commit.len() != 40
        || b.tree.len() != 40
        || !is_lowercase_hex(&b.commit)
        || !is_lowercase_hex(&b.tree)
        || !valid_digest(&b.cargo_lock_sha256)
        || !valid_digest(&b.toolchain_sha256)
        || !b.rust_version.starts_with("rustc 1.98.0 ")
        || b.features != "all-features"
        || b.profile != "release"
        || b.target.is_empty()
        || !b
            .target
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"-_".contains(&byte))
        || support_for_target(&b.target).is_err()
        || b.rust_version.is_empty()
    {
        return Err(ReleaseError::Unbound(
            "binding fields are incomplete or non-canonical".into(),
        ));
    }
    Ok(())
}
fn read_binding(path: &Path) -> Result<Binding, ReleaseError> {
    read_binding_bytes(&bounded_bytes(path, MAX_INPUT)?)
}
fn read_binding_bytes(bytes: &[u8]) -> Result<Binding, ReleaseError> {
    let start = bytes
        .windows(MARKER_START.len())
        .position(|w| w == MARKER_START)
        .ok_or_else(|| ReleaseError::Unbound("binary has no release binding marker".into()))?
        + MARKER_START.len();
    let end = bytes[start..]
        .windows(MARKER_END.len())
        .position(|w| w == MARKER_END)
        .ok_or_else(|| {
            ReleaseError::Unbound("binary release binding marker is incomplete".into())
        })?
        + start;
    if bytes[end + MARKER_END.len()..]
        .windows(MARKER_START.len())
        .any(|w| w == MARKER_START)
    {
        return Err(ReleaseError::Unbound(
            "binary has multiple binding markers".into(),
        ));
    }
    let text = std::str::from_utf8(&bytes[start..end])
        .map_err(|_| ReleaseError::Unbound("binding marker was not UTF-8".into()))?;
    let mut values = BTreeMap::new();
    for line in text.lines() {
        let (key, value) = line
            .split_once('=')
            .ok_or_else(|| ReleaseError::Unbound("binding line lacks '='".into()))?;
        if values.insert(key, value).is_some() {
            return Err(ReleaseError::Unbound(
                "binding contains duplicate key".into(),
            ));
        }
    }
    let expected = BTreeSet::from([
        "schema",
        "bound",
        "version",
        "commit",
        "git_tree",
        "cargo_lock_sha256",
        "rust_toolchain_sha256",
        "rustc_version",
        "target",
        "features",
        "profile",
    ]);
    if values.keys().copied().collect::<BTreeSet<_>>() != expected {
        return Err(ReleaseError::Unbound(
            "binding has missing or unknown keys".into(),
        ));
    }
    if values.get("schema") != Some(&"1") || values.get("bound") != Some(&"1") {
        return Err(ReleaseError::Unbound(
            "binding is development or unknown schema".into(),
        ));
    }
    let b = Binding {
        version: values["version"].to_owned(),
        commit: values["commit"].to_owned(),
        tree: values["git_tree"].to_owned(),
        cargo_lock_sha256: values["cargo_lock_sha256"].to_owned(),
        toolchain_sha256: values["rust_toolchain_sha256"].to_owned(),
        rust_version: values["rustc_version"].to_owned(),
        target: values["target"].to_owned(),
        features: values["features"].to_owned(),
        profile: values["profile"].to_owned(),
    };
    validate_binding(&b)?;
    Ok(b)
}
fn require_binding(expected: &Binding, actual: &Binding) -> Result<(), ReleaseError> {
    if expected != actual {
        Err(ReleaseError::Unbound(
            "binary binding differs from candidate identity".into(),
        ))
    } else {
        Ok(())
    }
}
fn verify_sbom(value: &Value, binding: &Binding) -> Result<(), ReleaseError> {
    if value.get("bomFormat").and_then(Value::as_str) != Some("CycloneDX")
        || value.get("specVersion").and_then(Value::as_str) != Some("1.6")
        || value.get("version").and_then(Value::as_u64) != Some(1)
        || value
            .get("components")
            .and_then(Value::as_array)
            .is_none_or(Vec::is_empty)
        || value
            .get("dependencies")
            .and_then(Value::as_array)
            .is_none_or(Vec::is_empty)
    {
        return Err(ReleaseError::Verify(
            "SBOM is not a populated CycloneDX 1.6 document".into(),
        ));
    }
    let metadata = value
        .get("metadata")
        .and_then(Value::as_object)
        .ok_or_else(|| ReleaseError::Verify("SBOM metadata is missing".into()))?;
    let tool_is_pinned = metadata
        .get("tools")
        .and_then(Value::as_array)
        .is_some_and(|tools| {
            tools.iter().any(|tool| {
                tool.get("name").and_then(Value::as_str) == Some("cargo-sbom")
                    && tool.get("version").and_then(Value::as_str) == Some(CARGO_SBOM_VERSION)
            })
        });
    let root_is_bound = value
        .pointer("/metadata/component/components")
        .and_then(Value::as_array)
        .is_some_and(|components| {
            components.iter().any(|component| {
                component.get("name").and_then(Value::as_str) == Some("kio-cli")
                    && component.get("version").and_then(Value::as_str)
                        == Some(binding.version.as_str())
                    && component.get("licenses")
                        == Some(&json!([{"expression":"LicenseRef-PolyForm-Shield-1.0.0"}]))
            })
        });
    if !tool_is_pinned || !root_is_bound {
        return Err(ReleaseError::Verify(
            "SBOM tool or root component is not bound to the candidate".into(),
        ));
    }
    Ok(())
}
fn verify_inventory(value: &Value, binding: &Binding) -> Result<(), ReleaseError> {
    let inventory = value
        .as_object()
        .ok_or_else(|| ReleaseError::Verify("dependency inventory is not an object".into()))?;
    if inventory.is_empty()
        || inventory.keys().any(|name| name.contains("file://"))
        || ["adapter", "cli", "core", "index", "pipeline", "search"]
            .iter()
            .any(|name| {
                let key = format!("kio-{name} {} workspace", binding.version);
                inventory
                    .get(&key)
                    .and_then(|package| package.get("licenses"))
                    != Some(&json!(["LicenseRef-PolyForm-Shield-1.0.0"]))
            })
    {
        return Err(ReleaseError::Verify(
            "dependency/license inventory is incomplete or noncanonical".into(),
        ));
    }
    Ok(())
}
fn verify_source_binding(repo: &Path, binding: &Binding) -> Result<(), ReleaseError> {
    let repo = canonical_repo(repo)?;
    reject_dirty(&repo)?;
    let expected = Binding {
        version: workspace_version(&repo)?,
        commit: git(&repo, &["rev-parse", "HEAD"])?,
        tree: git(&repo, &["rev-parse", "HEAD^{tree}"])?,
        cargo_lock_sha256: digest(&bounded_bytes(&repo.join("Cargo.lock"), MAX_JSON)?),
        toolchain_sha256: digest(&bounded_bytes(&repo.join("rust-toolchain.toml"), MAX_JSON)?),
        rust_version: rust_version()?,
        target: binding.target.clone(),
        features: "all-features".into(),
        profile: "release".into(),
    };
    require_binding(&expected, binding).map_err(|_| {
        ReleaseError::Verify(
            "archive source binding differs from the expected clean checkout".into(),
        )
    })
}
fn canonical_sbom(path: &Path, repo: Option<&Path>) -> Result<Vec<u8>, ReleaseError> {
    let mut value: Value = serde_json::from_slice(&bounded_bytes(path, MAX_JSON)?)?;
    if let Some(obj) = value.as_object_mut() {
        obj.remove("serialNumber");
        if let Some(metadata) = obj.get_mut("metadata").and_then(Value::as_object_mut)
            && metadata.contains_key("timestamp")
        {
            metadata.insert(
                "timestamp".into(),
                Value::String("1970-01-01T00:00:00Z".into()),
            );
        }
    }
    normalize_sbom_licenses(&mut value);
    normalize_json_arrays(&mut value)?;
    reject_source_root_leak(&value, repo)?;
    canonical_json(&value)
}
fn canonical_json_file(path: &Path) -> Result<Vec<u8>, ReleaseError> {
    let value: Value = serde_json::from_slice(&bounded_bytes(path, MAX_JSON)?)?;
    reject_source_root_leak(&value, None)?;
    canonical_json(&value)
}
fn canonical_inventory(path: &Path, repo: &Path) -> Result<Vec<u8>, ReleaseError> {
    let mut value: Value = serde_json::from_slice(&bounded_bytes(path, MAX_JSON)?)?;
    normalize_inventory(&mut value);
    normalize_json_arrays(&mut value)?;
    reject_source_root_leak(&value, Some(repo))?;
    canonical_json(&value)
}
fn normalize_inventory(value: &mut Value) {
    match value {
        Value::Object(object) => {
            let keys = object.keys().cloned().collect::<Vec<_>>();
            for key in keys {
                let mut child = object.remove(&key).expect("key exists");
                normalize_inventory(&mut child);
                let workspace = key.starts_with("kio-") && key.contains(" path+file://");
                if workspace && let Value::Object(package) = &mut child {
                    package.insert(
                        "licenses".into(),
                        json!(["LicenseRef-PolyForm-Shield-1.0.0"]),
                    );
                }
                let replacement = if workspace {
                    key.split(" path+file://").next().unwrap().to_owned() + " workspace"
                } else {
                    key
                };
                object.insert(replacement, child);
            }
        }
        Value::Array(values) => values.iter_mut().for_each(normalize_inventory),
        _ => {}
    }
}
fn normalize_sbom_licenses(value: &mut Value) {
    match value {
        Value::Object(object) => {
            let kio = object
                .get("name")
                .and_then(Value::as_str)
                .is_some_and(|name| name.starts_with("kio-"));
            if kio {
                replace_noassertion(object);
            }
            for child in object.values_mut() {
                normalize_sbom_licenses(child);
            }
        }
        Value::Array(values) => values.iter_mut().for_each(normalize_sbom_licenses),
        _ => {}
    }
}
fn replace_noassertion(object: &mut serde_json::Map<String, Value>) {
    match object.get_mut("licenses") {
        Some(Value::Array(licenses))
            if licenses
                .iter()
                .any(|v| v.to_string().contains("NOASSERTION")) =>
        {
            *licenses = vec![json!({"expression":"LicenseRef-PolyForm-Shield-1.0.0"})];
        }
        _ => {}
    }
}
fn reject_source_root_leak(value: &Value, repo: Option<&Path>) -> Result<(), ReleaseError> {
    let repo_text = repo.map(|p| p.to_string_lossy().into_owned());
    fn walk(value: &Value, repo: Option<&str>) -> bool {
        match value {
            Value::String(s) => s.contains("file://") || repo.is_some_and(|r| s.contains(r)),
            Value::Array(a) => a.iter().any(|v| walk(v, repo)),
            Value::Object(o) => o.values().any(|v| walk(v, repo)),
            _ => false,
        }
    }
    if walk(value, repo_text.as_deref()) {
        Err(ReleaseError::Invalid(
            "generated metadata leaks a source-root path".into(),
        ))
    } else {
        Ok(())
    }
}
fn normalize_json_arrays(value: &mut Value) -> Result<(), ReleaseError> {
    match value {
        Value::Object(object) => {
            for child in object.values_mut() {
                normalize_json_arrays(child)?;
            }
        }
        Value::Array(values) => {
            for child in values.iter_mut() {
                normalize_json_arrays(child)?;
            }
            let mut keyed = values
                .drain(..)
                .map(|item| {
                    let key = serde_jcs::to_vec(&item)
                        .map_err(|e| ReleaseError::Invalid(format!("JCS array item: {e}")))?;
                    Ok((key, item))
                })
                .collect::<Result<Vec<_>, ReleaseError>>()?;
            keyed.sort_by(|a, b| a.0.cmp(&b.0));
            if keyed.windows(2).any(|pair| pair[0].0 == pair[1].0) {
                return Err(ReleaseError::Invalid(
                    "generated metadata has duplicate semantic array entries".into(),
                ));
            }
            *values = keyed.into_iter().map(|(_, item)| item).collect();
        }
        _ => {}
    }
    Ok(())
}
fn canonical_json<T: Serialize>(value: &T) -> Result<Vec<u8>, ReleaseError> {
    let mut bytes =
        serde_jcs::to_vec(value).map_err(|e| ReleaseError::Invalid(format!("JCS: {e}")))?;
    bytes.push(b'\n');
    Ok(bytes)
}
fn canonical_parse<T: for<'a> Deserialize<'a> + Serialize>(
    bytes: &[u8],
) -> Result<T, ReleaseError> {
    if bytes.len() as u64 > MAX_JSON {
        return Err(ReleaseError::Verify("JSON exceeds limit".into()));
    }
    let value: T = serde_json::from_slice(bytes)?;
    let canonical = canonical_json(&value)?;
    if canonical != bytes {
        return Err(ReleaseError::Verify(
            "JSON is not JCS-canonical LF-terminated bytes".into(),
        ));
    }
    Ok(value)
}
fn generate_sbom(repo: &Path, tools: &Path, out: &Path) -> Result<PathBuf, ReleaseError> {
    let tool = pinned_tool(tools, "cargo-sbom", CARGO_SBOM_VERSION)?;
    let output = Command::new(tool)
        .current_dir(repo)
        .env("CARGO_NET_OFFLINE", "true")
        .args([
            "--cargo-package",
            "kio-cli",
            "--output-format",
            "cyclone_dx_json_1_6",
            "--project-directory",
        ])
        .arg(repo)
        .output()?;
    if !output.status.success() {
        return Err(ReleaseError::Invalid(format!(
            "cargo-sbom failed: {}",
            String::from_utf8_lossy(&output.stderr)
        )));
    }
    let path = out.join("sbom.cdx.json");
    create_new_bytes(&path, &output.stdout)?;
    Ok(path)
}
fn generate_inventory(
    repo: &Path,
    tools: &Path,
    out: &Path,
    target: &str,
) -> Result<PathBuf, ReleaseError> {
    let tool = pinned_tool(tools, "cargo-deny", CARGO_DENY_VERSION)?;
    let output = Command::new(tool)
        .current_dir(repo)
        .env("CARGO_NET_OFFLINE", "true")
        .args([
            "--manifest-path",
            "Cargo.toml",
            "--config",
            "deny.toml",
            "--all-features",
            "--locked",
            "--offline",
            "--exclude-dev",
            "--exclude",
            "kio-eval",
            "--target",
            target,
            "list",
            "--format",
            "json",
            "--layout",
            "crate",
        ])
        .output()?;
    if !output.status.success() {
        return Err(ReleaseError::Invalid(format!(
            "cargo-deny dependency inventory failed: {}",
            String::from_utf8_lossy(&output.stderr)
        )));
    }
    let path = out.join("dependencies.json");
    create_new_bytes(&path, &output.stdout)?;
    Ok(path)
}
fn generate_audit(
    repo: &Path,
    tools: &Path,
    out: &Path,
    target: &str,
) -> Result<PathBuf, ReleaseError> {
    let tool = pinned_tool(tools, "cargo-deny", CARGO_DENY_VERSION)?;
    let output = Command::new(tool)
        .current_dir(repo)
        .env("CARGO_NET_OFFLINE", "true")
        .args([
            "--manifest-path",
            "Cargo.toml",
            "--config",
            "deny.toml",
            "--all-features",
            "--locked",
            "--offline",
            "--exclude-dev",
            "--exclude",
            "kio-eval",
            "--target",
            target,
            "check",
            "bans",
            "licenses",
            "sources",
        ])
        .output()?;
    if !output.status.success() {
        return Err(ReleaseError::Invalid(format!(
            "cargo-deny audit failed: {}",
            String::from_utf8_lossy(&output.stderr)
        )));
    }
    let path = out.join("dependency-audit.json");
    create_new_bytes(
        &path,
        &canonical_json(
            &json!({"schema":"cargo-deny-receipt-v1", "tool":"cargo-deny", "version":CARGO_DENY_VERSION, "advisory_database":Value::Null, "checks":["bans","licenses","sources"], "status":"passed"}),
        )?,
    )?;
    Ok(path)
}
fn pinned_tool(tools: &Path, name: &str, version: &str) -> Result<PathBuf, ReleaseError> {
    let path = tools.join("bin").join(executable_name(name));
    require_regular(&path, MAX_INPUT)?;
    let output = Command::new(&path).arg("--version").output()?;
    if !output.status.success() || !String::from_utf8_lossy(&output.stdout).contains(version) {
        return Err(ReleaseError::Invalid(format!(
            "{name} is not pinned version {version}"
        )));
    }
    Ok(path)
}
fn executable_name(name: &str) -> String {
    if cfg!(windows) {
        format!("{name}.exe")
    } else {
        name.to_owned()
    }
}
fn internal_checksums(payload: &BTreeMap<String, (Vec<u8>, u32)>) -> Result<Vec<u8>, ReleaseError> {
    let mut map = BTreeMap::new();
    for (name, (bytes, _)) in payload {
        map.insert(name.clone(), digest(bytes));
    }
    canonical_json(&json!({"schema":"kio-rc-internal-checksums-v1","entries":map}))
}
fn write_archive(
    path: &Path,
    payload: &BTreeMap<String, (Vec<u8>, u32)>,
) -> Result<(), ReleaseError> {
    let file = OpenOptions::new().write(true).create_new(true).open(path)?;
    let encoder = GzBuilder::new()
        .mtime(0)
        .operating_system(255)
        .write(file, Compression::default());
    let mut tar = Builder::new(encoder);
    for (name, (bytes, mode)) in payload {
        let header = canonical_tar_header(name, bytes.len() as u64, *mode)?;
        tar.append(&header, Cursor::new(bytes))?;
    }
    let encoder = tar.into_inner()?;
    encoder.finish()?;
    Ok(())
}
fn read_archive(bytes: &[u8]) -> Result<BTreeMap<String, Vec<u8>>, ReleaseError> {
    let decoder = GzDecoder::new(Cursor::new(bytes));
    let mut archive = Archive::new(decoder);
    let mut files = BTreeMap::new();
    let mut prior = None;
    let mut total_unpacked = 0_u64;
    for entry in archive
        .entries()
        .map_err(|e| ReleaseError::Verify(format!("tar entries: {e}")))?
    {
        if files.len() >= MAX_ARCHIVE_ENTRIES {
            return Err(ReleaseError::Verify(
                "archive entry count exceeds limit".into(),
            ));
        }
        let entry = entry.map_err(|e| ReleaseError::Verify(format!("tar entry: {e}")))?;
        let header = entry.header();
        let entry_size = header.size().unwrap_or(MAX_ENTRY + 1);
        if !header.entry_type().is_file()
            || entry_size > MAX_ENTRY
            || header.mtime().unwrap_or(1) != 0
            || header.uid().unwrap_or(1) != 0
            || header.gid().unwrap_or(1) != 0
        {
            return Err(ReleaseError::Verify(
                "non-canonical tar entry metadata".into(),
            ));
        }
        total_unpacked = total_unpacked
            .checked_add(entry_size)
            .filter(|total| *total <= MAX_UNPACKED)
            .ok_or_else(|| ReleaseError::Verify("archive expands beyond limit".into()))?;
        let mode = header.mode().unwrap_or(0);
        let raw_path = entry
            .path()
            .map_err(|_| ReleaseError::Verify("invalid tar path".into()))?;
        let path = raw_path
            .to_str()
            .ok_or_else(|| ReleaseError::Verify("tar path is not UTF-8".into()))?
            .to_owned();
        valid_archive_name(&path)?;
        if prior.as_deref() >= Some(path.as_str()) {
            return Err(ReleaseError::Verify(
                "duplicate or unsorted archive entry".into(),
            ));
        }
        if (path.contains("/bin/") && mode != 0o755) || (!path.contains("/bin/") && mode != 0o644) {
            return Err(ReleaseError::Verify(
                "tar entry mode is not canonical".into(),
            ));
        }
        let expected_header = canonical_tar_header(&path, entry_size, mode)?;
        if header.as_bytes() != expected_header.as_bytes() {
            return Err(ReleaseError::Verify(
                "tar entry header is not the fixed canonical form".into(),
            ));
        }
        let mut value = Vec::new();
        entry.take(MAX_ENTRY + 1).read_to_end(&mut value)?;
        if value.len() as u64 > MAX_ENTRY {
            return Err(ReleaseError::Verify("tar entry exceeds limit".into()));
        }
        if files.insert(path.clone(), value).is_some() {
            return Err(ReleaseError::Verify("duplicate archive entry".into()));
        }
        prior = Some(path);
    }
    Ok(files)
}
fn canonical_tar_header(name: &str, size: u64, mode: u32) -> Result<Header, ReleaseError> {
    let mut header = Header::new_ustar();
    header.set_path(name)?;
    header.set_size(size);
    header.set_mode(mode);
    header.set_mtime(0);
    header.set_uid(0);
    header.set_gid(0);
    header.set_username("")?;
    header.set_groupname("")?;
    header.set_cksum();
    Ok(header)
}
fn valid_archive_name(name: &str) -> Result<(), ReleaseError> {
    if name.is_empty()
        || name.starts_with('/')
        || name.contains('\\')
        || name
            .split('/')
            .any(|s| s.is_empty() || s == "." || s == "..")
    {
        Err(ReleaseError::Verify("unsafe archive path".into()))
    } else {
        Ok(())
    }
}
fn archive_root(files: &BTreeMap<String, Vec<u8>>) -> Result<String, ReleaseError> {
    let first = files
        .keys()
        .next()
        .ok_or_else(|| ReleaseError::Verify("empty archive".into()))?;
    let root = first.split('/').next().unwrap();
    if !root.starts_with("kio-") || files.keys().any(|n| !n.starts_with(&format!("{root}/"))) {
        return Err(ReleaseError::Verify("archive has inconsistent root".into()));
    }
    Ok(root.into())
}
fn expected_names(root: &str, binary: &str) -> BTreeSet<String> {
    let mut s = BTreeSet::new();
    for suffix in [
        format!("bin/{binary}"),
        "LICENSE.md".into(),
        "NOTICE.txt".into(),
        "OPERATIONS.md".into(),
        "TRADEMARKS.md".into(),
        "release/checksums.json".into(),
        "release/dependencies.json".into(),
        "release/dependency-audit.json".into(),
        "release/provenance.json".into(),
        "release/sbom.cdx.json".into(),
    ] {
        s.insert(format!("{root}/{suffix}"));
    }
    s
}
fn check_internal_digests(
    files: &BTreeMap<String, Vec<u8>>,
    root: &str,
    value: &Value,
) -> Result<(), ReleaseError> {
    if value.get("schema").and_then(Value::as_str) != Some("kio-rc-internal-checksums-v1") {
        return Err(ReleaseError::Verify(
            "wrong internal checksum schema".into(),
        ));
    }
    if value.as_object().map(serde_json::Map::len) != Some(2) {
        return Err(ReleaseError::Verify(
            "internal checksum manifest has missing or unknown fields".into(),
        ));
    }
    let map = value
        .get("entries")
        .and_then(Value::as_object)
        .ok_or_else(|| ReleaseError::Verify("missing internal checksum entries".into()))?;
    for (name, expected) in map {
        let actual = files
            .get(name)
            .ok_or_else(|| ReleaseError::Verify("checksum names unknown entry".into()))?;
        if expected.as_str() != Some(digest(actual).as_str()) {
            return Err(ReleaseError::Verify(
                "internal payload digest mismatch".into(),
            ));
        }
    }
    if map.len() + 1 != files.len() || map.contains_key(&format!("{root}/release/checksums.json")) {
        return Err(ReleaseError::Verify(
            "internal checksum coverage mismatch".into(),
        ));
    }
    Ok(())
}
fn bounded_bytes(path: &Path, max: u64) -> Result<Vec<u8>, ReleaseError> {
    require_regular(path, max)?;
    let file = File::open(path)?;
    let mut bytes = Vec::new();
    file.take(max + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > max {
        return Err(ReleaseError::Invalid(format!(
            "{} exceeds bound",
            path.display()
        )));
    }
    Ok(bytes)
}
fn require_regular(path: &Path, max: u64) -> Result<(), ReleaseError> {
    let md = fs::symlink_metadata(path)?;
    if !md.file_type().is_file() || md.file_type().is_symlink() || md.len() > max {
        return Err(ReleaseError::Invalid(format!(
            "{} must be bounded regular file",
            path.display()
        )));
    }
    Ok(())
}
fn create_empty_dir(path: &Path) -> Result<(), ReleaseError> {
    if path.exists() {
        let metadata = fs::symlink_metadata(path)?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(ReleaseError::Invalid(format!(
                "output path is not a real directory: {}",
                path.display()
            )));
        }
        if fs::read_dir(path)?.next().is_some() {
            return Err(ReleaseError::Invalid(format!(
                "output directory exists and is nonempty: {}",
                path.display()
            )));
        }
    } else {
        fs::create_dir_all(path)?;
        let metadata = fs::symlink_metadata(path)?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(ReleaseError::Invalid(format!(
                "created output path is not a real directory: {}",
                path.display()
            )));
        }
    }
    Ok(())
}
fn require_output_outside_repo(repo: &Path, output: &Path) -> Result<(), ReleaseError> {
    let absolute = if output.is_absolute() {
        output.to_path_buf()
    } else {
        env::current_dir()?.join(output)
    };
    let parent = absolute
        .parent()
        .ok_or_else(|| ReleaseError::Invalid("output has no parent".into()))?;
    let parent = parent.canonicalize()?;
    let candidate = if absolute.exists() {
        absolute.canonicalize()?
    } else {
        parent.join(
            absolute
                .file_name()
                .ok_or_else(|| ReleaseError::Invalid("output has no name".into()))?,
        )
    };
    if candidate.starts_with(repo) {
        return Err(ReleaseError::Invalid(
            "release output must be outside the repository".into(),
        ));
    }
    Ok(())
}
fn create_new_bytes(path: &Path, bytes: &[u8]) -> Result<(), ReleaseError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}
fn default_sidecar(archive: &Path) -> PathBuf {
    let name = archive
        .file_name()
        .and_then(OsStr::to_str)
        .unwrap_or("candidate.tar.gz");
    let stem = name.strip_suffix(".tar.gz").unwrap_or(name);
    archive.with_file_name(format!("{stem}.checksums.json"))
}
fn canonical_dir_files(path: &Path) -> Result<BTreeMap<String, Vec<u8>>, ReleaseError> {
    let metadata = fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(ReleaseError::Invalid(
            "candidate output is not a real directory".into(),
        ));
    }
    let mut result = BTreeMap::new();
    for entry in fs::read_dir(path)? {
        if result.len() == MAX_CANDIDATE_OUTPUTS {
            return Err(ReleaseError::Verify(
                "candidate output count exceeds comparison limit".into(),
            ));
        }
        let entry = entry?;
        if entry.file_type()?.is_symlink() || !entry.file_type()?.is_file() {
            return Err(ReleaseError::Invalid(
                "candidate directory contains nonregular entry".into(),
            ));
        }
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| ReleaseError::Invalid("candidate filename is not UTF-8".into()))?;
        result.insert(name, bounded_bytes(&entry.path(), MAX_ARCHIVE)?);
    }
    Ok(result)
}
fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
fn valid_digest(v: &str) -> bool {
    v.len() == 64 && is_lowercase_hex(v)
}
fn is_lowercase_hex(v: &str) -> bool {
    v.bytes()
        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn set_executable(path: &Path) -> Result<(), ReleaseError> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut p = fs::metadata(path)?.permissions();
        p.set_mode(0o755);
        fs::set_permissions(path, p)?;
    }
    Ok(())
}
fn smoke_env(cmd: &mut Command, home: &Path) {
    cmd.env("HOME", home)
        .env("XDG_CONFIG_HOME", home.join("xdg-config"))
        .env("XDG_CACHE_HOME", home.join("xdg-cache"))
        .env("TMPDIR", home.join("tmp"))
        .env("TEMP", home.join("tmp"))
        .env("TMP", home.join("tmp"))
        .env("APPDATA", home.join("appdata"))
        .env("LOCALAPPDATA", home.join("localappdata"));
}
fn run_smoke(binary: &Path, home: &Path, args: &[&str]) -> Result<Vec<u8>, ReleaseError> {
    let mut cmd = Command::new(binary);
    cmd.args(args);
    smoke_env(&mut cmd, home);
    let out = cmd.output()?;
    if !out.status.success() {
        return Err(ReleaseError::Verify(format!(
            "smoke {} failed: {}",
            args.join(" "),
            out.status
        )));
    }
    Ok(out.stdout)
}
fn run_smoke_in(
    binary: &Path,
    home: &Path,
    cwd: &Path,
    args: &[&str],
) -> Result<Vec<u8>, ReleaseError> {
    let mut cmd = Command::new(binary);
    cmd.current_dir(cwd).args(args);
    smoke_env(&mut cmd, home);
    let out = cmd.output()?;
    if !out.status.success() {
        return Err(ReleaseError::Verify(format!(
            "smoke {} failed: {}",
            args.join(" "),
            out.status
        )));
    }
    Ok(out.stdout)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn binding() -> Binding {
        Binding {
            version: RC_VERSION.into(),
            commit: "a".repeat(40),
            tree: "b".repeat(40),
            cargo_lock_sha256: "c".repeat(64),
            toolchain_sha256: "d".repeat(64),
            rust_version: "rustc 1.98.0 (test)".into(),
            target: "x86_64-unknown-linux-gnu".into(),
            features: "all-features".into(),
            profile: "release".into(),
        }
    }
    fn binary() -> Vec<u8> {
        let mut v = MARKER_START.to_vec();
        let b = binding();
        v.extend(format!("schema=1\nbound=1\nversion={}\ncommit={}\ngit_tree={}\ncargo_lock_sha256={}\nrust_toolchain_sha256={}\nrustc_version={}\ntarget={}\nfeatures={}\nprofile={}", b.version, b.commit, b.tree, b.cargo_lock_sha256, b.toolchain_sha256, b.rust_version, b.target, b.features, b.profile).into_bytes());
        v.extend(MARKER_END);
        v
    }
    fn root() -> String {
        format!("kio-{RC_VERSION}-x86_64-unknown-linux-gnu")
    }
    fn test_sbom() -> Value {
        json!({
            "bomFormat":"CycloneDX",
            "specVersion":"1.6",
            "version":1,
            "components":[{"name":"dependency"}],
            "dependencies":[{"dependsOn":[],"ref":"root"}],
            "metadata":{
                "tools":[{"name":"cargo-sbom","version":CARGO_SBOM_VERSION}],
                "component":{"components":[{
                    "licenses":[{"expression":"LicenseRef-PolyForm-Shield-1.0.0"}],
                    "name":"kio-cli",
                    "type":"application",
                    "version":RC_VERSION
                }]}
            }
        })
    }
    fn test_inventory() -> Value {
        let mut inventory = serde_json::Map::new();
        for name in ["adapter", "cli", "core", "index", "pipeline", "search"] {
            inventory.insert(
                format!("kio-{name} {RC_VERSION} workspace"),
                json!({"licenses":["LicenseRef-PolyForm-Shield-1.0.0"]}),
            );
        }
        Value::Object(inventory)
    }
    fn payload() -> BTreeMap<String, (Vec<u8>, u32)> {
        let root = root();
        let mut p = BTreeMap::new();
        for name in expected_names(&root, binary_name_for_target("x86_64-unknown-linux-gnu")) {
            if name.ends_with("/release/checksums.json") {
                continue;
            }
            let bytes = if name.ends_with("/bin/kio") {
                binary()
            } else if name.ends_with("provenance.json") {
                canonical_json(&json!({"binding":binding(),"support":"supported"})).unwrap()
            } else if name.ends_with("checksums.json") {
                Vec::new()
            } else if name.ends_with("dependency-audit.json") {
                canonical_json(&json!({"schema":"cargo-deny-receipt-v1","tool":"cargo-deny","version":CARGO_DENY_VERSION,"status":"passed","advisory_database":Value::Null,"checks":["bans","licenses","sources"]})).unwrap()
            } else if name.ends_with("sbom.cdx.json") {
                canonical_json(&test_sbom()).unwrap()
            } else if name.ends_with("dependencies.json") {
                canonical_json(&test_inventory()).unwrap()
            } else {
                canonical_json(&json!({"x":name})).unwrap()
            };
            let mode = if name.contains("/bin/") { 0o755 } else { 0o644 };
            p.insert(name, (bytes, mode));
        }
        let provenance = format!("{root}/release/provenance.json");
        let binary = digest(&p[&format!("{root}/bin/kio")].0);
        let sbom = digest(&p[&format!("{root}/release/sbom.cdx.json")].0);
        let inventory = digest(&p[&format!("{root}/release/dependencies.json")].0);
        let audit = digest(&p[&format!("{root}/release/dependency-audit.json")].0);
        p.insert(provenance, (canonical_json(&json!({"schema":"kio-rc-provenance-v1","binding":binding(),"support":"supported","tools":{"cargo_sbom":CARGO_SBOM_VERSION,"cargo_deny":CARGO_DENY_VERSION,"advisory_database":Value::Null},"signing":signing_status("x86_64-unknown-linux-gnu").unwrap(),"digests":{"binary_sha256":binary,"sbom_sha256":sbom,"dependency_inventory_sha256":inventory,"dependency_audit_sha256":audit}})).unwrap(),0o644));
        let checks = internal_checksums(&p).unwrap();
        p.insert(format!("{root}/release/checksums.json"), (checks, 0o644));
        p
    }
    fn archive_pair_from_payload(
        p: BTreeMap<String, (Vec<u8>, u32)>,
    ) -> (TempDir, PathBuf, PathBuf) {
        let t = tempfile::tempdir().unwrap();
        let archive = t.path().join("candidate.tar.gz");
        write_archive(&archive, &p).unwrap();
        let root = root();
        let side = ChecksumSidecar {
            schema: "kio-rc-checksums-v1".into(),
            archive: "candidate.tar.gz".into(),
            archive_sha256: digest(&fs::read(&archive).unwrap()),
            binary_sha256: digest(&p[&format!("{root}/bin/kio")].0),
            provenance_sha256: digest(&p[&format!("{root}/release/provenance.json")].0),
            sbom_sha256: digest(&p[&format!("{root}/release/sbom.cdx.json")].0),
            checksums_sha256: digest(&p[&format!("{root}/release/checksums.json")].0),
        };
        let checksum = t.path().join("candidate.checksums.json");
        create_new_bytes(&checksum, &canonical_json(&side).unwrap()).unwrap();
        (t, archive, checksum)
    }
    fn archive_pair() -> (TempDir, PathBuf, PathBuf) {
        archive_pair_from_payload(payload())
    }
    fn verify_options(archive: PathBuf, checksum: Option<PathBuf>) -> VerifyCandidateOptions {
        VerifyCandidateOptions {
            expected_archive_sha256: digest(&fs::read(&archive).unwrap()),
            archive,
            checksum,
            ..Default::default()
        }
    }
    #[test]
    fn deterministic_archive_and_binding() {
        let t = tempfile::tempdir().unwrap();
        let a = t.path().join("a.tar.gz");
        let b = t.path().join("b.tar.gz");
        let p = payload();
        write_archive(&a, &p).unwrap();
        write_archive(&b, &p).unwrap();
        assert_eq!(fs::read(a).unwrap(), fs::read(b).unwrap());
        assert_eq!(read_binding_bytes(&binary()).unwrap(), binding());
    }
    #[test]
    fn release_tool_name_matches_the_native_platform() {
        let expected = if cfg!(windows) {
            "cargo-sbom.exe"
        } else {
            "cargo-sbom"
        };
        assert_eq!(executable_name("cargo-sbom"), expected);
    }
    #[test]
    fn candidate_build_uses_only_the_pinned_macos_linker() {
        assert_eq!(
            encoded_macos_linker_flags("/toolchain/rust-lld"),
            "-C\u{1f}linker=/toolchain/rust-lld\u{1f}-C\u{1f}linker-flavor=ld64.lld\u{1f}-C\u{1f}link-arg=-no_uuid"
        );
        assert!(
            candidate_rustflags("x86_64-unknown-linux-gnu")
                .unwrap()
                .is_none()
        );
        assert!(
            candidate_rustflags("x86_64-pc-windows-msvc")
                .unwrap()
                .is_none()
        );
        #[cfg(target_os = "macos")]
        {
            let target = native_target().unwrap();
            let flags = candidate_rustflags(&target).unwrap().unwrap();
            assert!(flags.ends_with(
                "rust-lld\u{1f}-C\u{1f}linker-flavor=ld64.lld\u{1f}-C\u{1f}link-arg=-no_uuid"
            ));
        }
    }
    #[test]
    fn verifier_accepts_bound_archive_and_rejects_tamper_or_substitution() {
        let (_t, archive, checksum) = archive_pair();
        let archive_sha256 = digest(&fs::read(&archive).unwrap());
        assert!(
            verify_candidate(&VerifyCandidateOptions {
                archive: archive.clone(),
                checksum: Some(checksum.clone()),
                expected_archive_sha256: archive_sha256.clone(),
                expected_repo: None,
                expected_commit: Some("a".repeat(40)),
                expected_lock_sha256: Some("c".repeat(64))
            })
            .is_ok()
        );
        assert!(
            verify_candidate(&VerifyCandidateOptions {
                archive: archive.clone(),
                checksum: Some(checksum.clone()),
                expected_archive_sha256: archive_sha256.clone(),
                expected_repo: None,
                expected_commit: Some("e".repeat(40)),
                expected_lock_sha256: Some("c".repeat(64)),
            })
            .is_err()
        );
        assert!(
            verify_candidate(&VerifyCandidateOptions {
                archive: archive.clone(),
                checksum: Some(checksum.clone()),
                expected_archive_sha256: archive_sha256,
                expected_repo: None,
                expected_commit: Some("a".repeat(40)),
                expected_lock_sha256: Some("f".repeat(64)),
            })
            .is_err()
        );
        let mut side: Value = serde_json::from_slice(&fs::read(&checksum).unwrap()).unwrap();
        side["binary_sha256"] = Value::String("0".repeat(64));
        fs::write(&checksum, canonical_json(&side).unwrap()).unwrap();
        assert!(verify_candidate(&verify_options(archive.clone(), Some(checksum))).is_err());
        let mut bytes = fs::read(&archive).unwrap();
        bytes[0] ^= 1;
        let tampered = archive.with_file_name("tampered.tar.gz");
        fs::write(&tampered, bytes).unwrap();
        assert!(verify_candidate(&verify_options(tampered, None)).is_err());
    }
    #[test]
    fn retained_archive_digest_rejects_coordinated_evidence_substitution() {
        let (_trusted_dir, trusted_archive, _trusted_checksum) = archive_pair();
        let trusted_sha256 = digest(&fs::read(trusted_archive).unwrap());
        let root = root();
        let inventory_path = format!("{root}/release/dependencies.json");
        let provenance_path = format!("{root}/release/provenance.json");
        let checksums_path = format!("{root}/release/checksums.json");
        let mut replacement = payload();
        let mut inventory: Value = serde_json::from_slice(&replacement[&inventory_path].0).unwrap();
        inventory.as_object_mut().unwrap().insert(
            "forged-package 1.0.0 registry".into(),
            json!({"licenses":["MIT"]}),
        );
        replacement.insert(
            inventory_path.clone(),
            (canonical_json(&inventory).unwrap(), 0o644),
        );
        let mut provenance: Value =
            serde_json::from_slice(&replacement[&provenance_path].0).unwrap();
        provenance["digests"]["dependency_inventory_sha256"] =
            Value::String(digest(&replacement[&inventory_path].0));
        replacement.insert(
            provenance_path,
            (canonical_json(&provenance).unwrap(), 0o644),
        );
        replacement.remove(&checksums_path);
        let internal = internal_checksums(&replacement).unwrap();
        replacement.insert(checksums_path, (internal, 0o644));
        let (_replacement_dir, archive, checksum) = archive_pair_from_payload(replacement);
        assert!(verify_candidate(&verify_options(archive.clone(), Some(checksum.clone()))).is_ok());
        let mut options = verify_options(archive, Some(checksum));
        options.expected_archive_sha256 = trusted_sha256;
        assert!(verify_candidate(&options).is_err());
    }
    #[test]
    fn rejects_unbound_marker() {
        assert!(read_binding_bytes(b"no marker").is_err());
        let mut development = MARKER_START.to_vec();
        development.extend_from_slice(
            format!(
                "schema=1\nbound=0\nversion={RC_VERSION}\ntarget=x86_64-unknown-linux-gnu\nprofile=debug"
            )
            .as_bytes(),
        );
        development.extend_from_slice(MARKER_END);
        assert!(read_binding_bytes(&development).is_err());
    }
    #[test]
    fn rejects_noncanonical_json() {
        assert!(canonical_parse::<Value>(b"{\"b\":1,\"a\":2}\n").is_err());
    }
    #[test]
    fn verifier_rejects_noncanonical_json_member() {
        let root = root();
        let provenance = format!("{root}/release/provenance.json");
        let checksums = format!("{root}/release/checksums.json");
        let mut p = payload();
        let value: Value = serde_json::from_slice(&p[&provenance].0).unwrap();
        let mut noncanonical = serde_json::to_vec_pretty(&value).unwrap();
        noncanonical.push(b'\n');
        assert_ne!(noncanonical, canonical_json(&value).unwrap());
        p.insert(provenance, (noncanonical, 0o644));
        p.remove(&checksums);
        let internal = internal_checksums(&p).unwrap();
        p.insert(checksums, (internal, 0o644));
        let (_t, archive, checksum) = archive_pair_from_payload(p);
        assert!(verify_candidate(&verify_options(archive, Some(checksum))).is_err());
    }
    #[test]
    fn normalizes_permuted_sbom_arrays() {
        let t = tempfile::tempdir().unwrap();
        let a = t.path().join("a.json");
        let b = t.path().join("b.json");
        fs::write(
            &a,
            br#"{"components":[{"name":"z"},{"name":"a"}],"serialNumber":"x"}"#,
        )
        .unwrap();
        fs::write(
            &b,
            br#"{"serialNumber":"y","components":[{"name":"a"},{"name":"z"}]}"#,
        )
        .unwrap();
        assert_eq!(
            canonical_sbom(&a, None).unwrap(),
            canonical_sbom(&b, None).unwrap()
        );
    }
    fn malformed_pair(names: &[&str]) -> (TempDir, PathBuf, PathBuf) {
        let t = tempfile::tempdir().unwrap();
        let archive = t.path().join("candidate.tar.gz");
        let file = File::create(&archive).unwrap();
        let gz = GzBuilder::new()
            .mtime(0)
            .operating_system(255)
            .write(file, Compression::default());
        let mut tar = Builder::new(gz);
        for name in names {
            let mut header = Header::new_ustar();
            header.set_size(1);
            header.set_mode(0o644);
            header.set_mtime(0);
            header.set_uid(0);
            header.set_gid(0);
            if name.contains("..") {
                header.set_path("safe").unwrap();
                header.as_mut_bytes()[..100].fill(0);
                header.as_mut_bytes()[..name.len()].copy_from_slice(name.as_bytes());
            } else {
                header.set_path(name).unwrap();
            }
            header.set_cksum();
            tar.append(&header, Cursor::new(b"x")).unwrap();
        }
        tar.into_inner().unwrap().finish().unwrap();
        let side = ChecksumSidecar {
            schema: "kio-rc-checksums-v1".into(),
            archive: "candidate.tar.gz".into(),
            archive_sha256: digest(&fs::read(&archive).unwrap()),
            binary_sha256: "0".repeat(64),
            provenance_sha256: "0".repeat(64),
            sbom_sha256: "0".repeat(64),
            checksums_sha256: "0".repeat(64),
        };
        let checksum = t.path().join("candidate.checksums.json");
        create_new_bytes(&checksum, &canonical_json(&side).unwrap()).unwrap();
        (t, archive, checksum)
    }
    #[test]
    fn verifier_rejects_duplicate_and_traversal_tar_entries() {
        let (_t, archive, checksum) = malformed_pair(&["kio-x/LICENSE.md", "kio-x/LICENSE.md"]);
        assert!(verify_candidate(&verify_options(archive, Some(checksum))).is_err());
        let (_t, archive, checksum) = malformed_pair(&["kio-x/LICENSE.md", "../escape"]);
        assert!(verify_candidate(&verify_options(archive, Some(checksum))).is_err());
    }
    #[test]
    fn verifier_rejects_noncanonical_tar_identity_fields() {
        let t = tempfile::tempdir().unwrap();
        let archive = t.path().join("noncanonical.tar.gz");
        let file = File::create(&archive).unwrap();
        let gz = GzBuilder::new()
            .mtime(0)
            .operating_system(255)
            .write(file, Compression::default());
        let mut tar = Builder::new(gz);
        let mut header = canonical_tar_header("kio-x/LICENSE.md", 1, 0o644).unwrap();
        header.set_username("builder").unwrap();
        header.set_cksum();
        tar.append(&header, Cursor::new(b"x")).unwrap();
        tar.into_inner().unwrap().finish().unwrap();
        assert!(read_archive(&fs::read(archive).unwrap()).is_err());
    }
    #[test]
    fn rejects_traversal_and_duplicate_names() {
        assert!(valid_archive_name("../evil").is_err());
        assert!(valid_archive_name("root\\evil").is_err());
    }

    fn compare_error(left: &Path, right: &Path) -> Value {
        let error = compare_candidate_dirs(left, right).unwrap_err();
        let ReleaseError::Verify(detail) = error else {
            panic!("comparison did not fail verification")
        };
        serde_json::from_str(&detail).unwrap()
    }

    fn write_output(dir: &Path, name: &str, bytes: &[u8]) {
        fs::write(dir.join(name), bytes).unwrap();
    }

    fn put_u16(bytes: &mut [u8], offset: usize, value: u16) {
        bytes[offset..offset + 2].copy_from_slice(&value.to_le_bytes());
    }

    fn put_u32(bytes: &mut [u8], offset: usize, value: u32) {
        bytes[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
    }

    fn synthetic_pe32_plus(timestamp: u32, guid: [u8; 16], pdb_path: &[u8]) -> Vec<u8> {
        let pe_offset = 0x80;
        let optional_offset = pe_offset + 24;
        let section_offset = optional_offset + 0xf0;
        let mut bytes = vec![0; 0x400];
        bytes[..2].copy_from_slice(b"MZ");
        put_u32(&mut bytes, 0x3c, pe_offset as u32);
        bytes[pe_offset..pe_offset + 4].copy_from_slice(b"PE\0\0");
        put_u16(&mut bytes, pe_offset + 4, 0x8664);
        put_u16(&mut bytes, pe_offset + 6, 1);
        put_u32(&mut bytes, pe_offset + 8, timestamp);
        put_u16(&mut bytes, pe_offset + 20, 0xf0);
        put_u16(&mut bytes, optional_offset, 0x20b);
        put_u32(&mut bytes, optional_offset + 64, 0x1234_5678);
        put_u32(&mut bytes, optional_offset + 108, 16);
        put_u32(&mut bytes, optional_offset + 160, 0x1000);
        put_u32(&mut bytes, optional_offset + 164, 56);
        bytes[section_offset..section_offset + 8].copy_from_slice(b".rdata\0\0");
        put_u32(&mut bytes, section_offset + 8, 0x200);
        put_u32(&mut bytes, section_offset + 12, 0x1000);
        put_u32(&mut bytes, section_offset + 16, 0x200);
        put_u32(&mut bytes, section_offset + 20, 0x200);

        let debug = 0x200;
        put_u32(&mut bytes, debug + 4, timestamp);
        put_u32(&mut bytes, debug + 12, 2);
        put_u32(&mut bytes, debug + 16, (24 + pdb_path.len() + 1) as u32);
        put_u32(&mut bytes, debug + 20, 0x1100);
        put_u32(&mut bytes, debug + 24, 0x300);
        let repro = debug + 28;
        put_u32(&mut bytes, repro + 4, timestamp);
        put_u32(&mut bytes, repro + 12, 16);

        bytes[0x300..0x304].copy_from_slice(b"RSDS");
        bytes[0x304..0x314].copy_from_slice(&guid);
        put_u32(&mut bytes, 0x314, 7);
        let path_start = 0x318;
        bytes[path_start..path_start + pdb_path.len()].copy_from_slice(pdb_path);
        bytes[path_start + pdb_path.len()] = 0;
        bytes
    }

    fn windows_archive_payload(binary: Vec<u8>) -> BTreeMap<String, (Vec<u8>, u32)> {
        BTreeMap::from([
            (
                "kio-0.1.0-rc.1-x86_64-pc-windows-msvc/bin/kio.exe".into(),
                (binary, 0o755),
            ),
            (
                "kio-0.1.0-rc.1-x86_64-pc-windows-msvc/LICENSE.md".into(),
                (b"license".to_vec(), 0o644),
            ),
        ])
    }

    #[test]
    fn candidate_directory_comparison_accepts_exact_outputs() {
        let t = tempfile::tempdir().unwrap();
        let left = t.path().join("left");
        let right = t.path().join("right");
        fs::create_dir(&left).unwrap();
        fs::create_dir(&right).unwrap();
        for dir in [&left, &right] {
            write_output(dir, "candidate.tar.gz", b"archive");
            write_output(dir, "candidate.checksums.json", br#"{"schema":"v1"}"#);
        }
        assert!(compare_candidate_dirs(&left, &right).is_ok());
    }

    #[test]
    fn candidate_directory_comparison_is_fail_closed_and_summarizes_all_outputs() {
        let t = tempfile::tempdir().unwrap();
        let left = t.path().join("left");
        let right = t.path().join("right");
        fs::create_dir(&left).unwrap();
        fs::create_dir(&right).unwrap();
        let left_archive = b"archive";
        let mut right_archive = left_archive.to_vec();
        right_archive[3] ^= 1;
        write_output(&left, "candidate.tar.gz", left_archive);
        write_output(&right, "candidate.tar.gz", &right_archive);
        write_output(&left, "candidate.checksums.json", br#"{"schema":"v1"}"#);
        write_output(&right, "candidate.checksums.json", br#"{"schema":"v1"}"#);
        let diagnostic = compare_error(&left, &right);
        assert_eq!(diagnostic["schema"], "kio-rc-compare-diagnostic-v1");
        let outputs = diagnostic["outputs"].as_array().unwrap();
        assert_eq!(outputs.len(), 2);
        assert_eq!(outputs[0]["name"], "candidate.checksums.json");
        assert_eq!(outputs[0]["matches"], true);
        assert_eq!(outputs[1]["name"], "candidate.tar.gz");
        assert_eq!(outputs[1]["matches"], false);
        assert_eq!(
            outputs[1]["difference"]["classification"],
            "malformed_or_noncanonical_archive"
        );
        assert_eq!(outputs[1]["left"]["size"], left_archive.len());
        assert_eq!(outputs[1]["right"]["size"], left_archive.len());
        assert!(outputs[1]["left"]["sha256"].as_str().unwrap().len() == 64);
    }

    #[test]
    fn candidate_directory_comparison_reports_canonical_json_without_values() {
        let t = tempfile::tempdir().unwrap();
        let left = t.path().join("left");
        let right = t.path().join("right");
        fs::create_dir(&left).unwrap();
        fs::create_dir(&right).unwrap();
        write_output(
            &left,
            "candidate.checksums.json",
            &canonical_json(&json!({"safe":"left-secret","unsafe key!":"same"})).unwrap(),
        );
        write_output(
            &right,
            "candidate.checksums.json",
            &canonical_json(&json!({"safe":"right-secret","unsafe key!":"same"})).unwrap(),
        );
        let diagnostic = compare_error(&left, &right);
        let field = &diagnostic["outputs"][0]["difference"]["json_fields"]["fields"][0];
        assert_eq!(field["path"], "/safe");
        assert_eq!(field["left_kind"], "string");
        assert_eq!(field["right_kind"], "string");
        assert!(field["left_canonical_sha256"].as_str().unwrap().len() == 64);
        let serialized = serde_json::to_string(&diagnostic).unwrap();
        assert!(!serialized.contains("left-secret"));
        assert!(!serialized.contains("right-secret"));
        assert!(!serialized.contains("unsafe key!"));
    }

    #[test]
    fn candidate_directory_comparison_reports_archive_entries() {
        let t = tempfile::tempdir().unwrap();
        let left = t.path().join("left");
        let right = t.path().join("right");
        fs::create_dir(&left).unwrap();
        fs::create_dir(&right).unwrap();
        let mut left_payload = BTreeMap::new();
        left_payload.insert("kio-x/LICENSE.md".into(), (b"left".to_vec(), 0o644));
        let mut right_payload = left_payload.clone();
        right_payload.insert("kio-x/LICENSE.md".into(), (b"right".to_vec(), 0o644));
        write_archive(&left.join("candidate.tar.gz"), &left_payload).unwrap();
        write_archive(&right.join("candidate.tar.gz"), &right_payload).unwrap();
        let diagnostic = compare_error(&left, &right);
        let entry = &diagnostic["outputs"][0]["difference"]["archive_entries"][0];
        assert_eq!(entry["path"], "kio-x/LICENSE.md");
        assert_eq!(entry["matches"], false);
        assert_eq!(entry["left"]["size"], 4);
        assert_eq!(entry["right"]["size"], 5);
    }

    #[test]
    fn candidate_directory_comparison_reports_safe_pe32_plus_differences() {
        let t = tempfile::tempdir().unwrap();
        let left = t.path().join("left");
        let right = t.path().join("right");
        fs::create_dir(&left).unwrap();
        fs::create_dir(&right).unwrap();
        let pdb = br"C:\\build\\secret\\kio.pdb";
        let left_binary = synthetic_pe32_plus(1, [1; 16], pdb);
        let right_binary = synthetic_pe32_plus(2, [2; 16], pdb);
        write_archive(
            &left.join("candidate.tar.gz"),
            &windows_archive_payload(left_binary),
        )
        .unwrap();
        write_archive(
            &right.join("candidate.tar.gz"),
            &windows_archive_payload(right_binary),
        )
        .unwrap();
        let diagnostic = compare_error(&left, &right);
        let entries = diagnostic["outputs"][0]["difference"]["archive_entries"]
            .as_array()
            .unwrap();
        let entry = entries
            .iter()
            .find(|entry| entry["path"].as_str().unwrap().ends_with("/bin/kio.exe"))
            .unwrap();
        let pe = &entry["pe32_plus"];
        assert_eq!(pe["left"]["metadata"]["machine"], 0x8664);
        assert_eq!(pe["left"]["metadata"]["coff_timestamp"], 1);
        assert_eq!(pe["right"]["metadata"]["coff_timestamp"], 2);
        assert_eq!(pe["left"]["metadata"]["reproducible"], true);
        assert_eq!(
            pe["left"]["metadata"]["debug_entries"][0]["codeview_rsds"]["guid_hex"],
            "01010101010101010101010101010101"
        );
        assert_eq!(
            pe["right"]["metadata"]["debug_entries"][0]["codeview_rsds"]["guid_hex"],
            "02020202020202020202020202020202"
        );
        assert_eq!(
            pe["left"]["metadata"]["debug_entries"][0]["codeview_rsds"]["pdb_path_class"],
            "absolute"
        );
        assert_eq!(
            pe["left"]["metadata"]["sections"][0]["raw_sha256"],
            digest(&synthetic_pe32_plus(1, [1; 16], pdb)[0x200..0x400])
        );
        let rendered = serde_json::to_string(&diagnostic).unwrap();
        assert!(!rendered.contains("C:\\\\build\\\\secret\\\\kio.pdb"));
        assert!(!rendered.contains("secret"));
    }

    #[test]
    fn pe32_plus_diagnostics_are_bounded_and_fail_closed() {
        assert_eq!(pe_diagnostic(Some(b"MZ")).reason, Some("truncated_header"));
        let mut excessive_sections = synthetic_pe32_plus(1, [1; 16], b"relative.pdb");
        put_u16(
            &mut excessive_sections,
            0x80 + 6,
            (MAX_PE_SECTIONS + 1) as u16,
        );
        assert_eq!(
            pe_diagnostic(Some(&excessive_sections)).reason,
            Some("excessive_sections")
        );
        let mut excessive_debug = synthetic_pe32_plus(1, [1; 16], b"relative.pdb");
        put_u32(
            &mut excessive_debug,
            0x80 + 24 + 112 + 6 * 8 + 4,
            ((MAX_PE_DEBUG_ENTRIES + 1) * 28) as u32,
        );
        assert_eq!(
            pe_diagnostic(Some(&excessive_debug)).reason,
            Some("excessive_debug_entries")
        );
        let mut redirected_pointer = synthetic_pe32_plus(1, [1; 16], b"relative.pdb");
        let payload_size = 24 + b"relative.pdb".len() + 1;
        let duplicate = redirected_pointer[0x300..0x300 + payload_size].to_vec();
        redirected_pointer[0x340..0x340 + payload_size].copy_from_slice(&duplicate);
        put_u32(&mut redirected_pointer, 0x200 + 24, 0x340);
        assert_eq!(
            pe_diagnostic(Some(&redirected_pointer)).reason,
            Some("invalid_debug_payload")
        );
        let mut overlapping_debug = synthetic_pe32_plus(1, [1; 16], b"relative.pdb");
        put_u32(&mut overlapping_debug, 0x200 + 28 + 16, 1);
        put_u32(&mut overlapping_debug, 0x200 + 28 + 20, 0x1100);
        put_u32(&mut overlapping_debug, 0x200 + 28 + 24, 0x300);
        assert_eq!(
            pe_diagnostic(Some(&overlapping_debug)).reason,
            Some("invalid_debug_payload")
        );
        let mut overlapping_sections = synthetic_pe32_plus(1, [1; 16], b"relative.pdb");
        put_u16(&mut overlapping_sections, 0x80 + 6, 2);
        let section_offset = 0x80 + 24 + 0xf0;
        let section = overlapping_sections[section_offset..section_offset + 40].to_vec();
        overlapping_sections[section_offset + 40..section_offset + 80].copy_from_slice(&section);
        assert_eq!(
            pe_diagnostic(Some(&overlapping_sections)).reason,
            Some("invalid_section")
        );
        let mut malformed_codeview = synthetic_pe32_plus(1, [1; 16], b"relative.pdb");
        malformed_codeview[0x318] = 0;
        assert_eq!(
            pe_diagnostic(Some(&malformed_codeview)).reason,
            Some("invalid_codeview")
        );
        let first = pe_diagnostic(Some(&excessive_debug));
        let second = pe_diagnostic(Some(&excessive_debug));
        assert_eq!(
            canonical_json(&first).unwrap(),
            canonical_json(&second).unwrap()
        );
    }

    #[test]
    fn candidate_directory_comparison_uses_unambiguous_json_pointers() {
        let t = tempfile::tempdir().unwrap();
        let left = t.path().join("left");
        let right = t.path().join("right");
        fs::create_dir(&left).unwrap();
        fs::create_dir(&right).unwrap();
        let left_value = json!({
            "a.b": {"[0]": 1},
            "a": {"b": 2},
            "slash/key": 3,
            "tilde~key": 4,
            "[x]": 5,
        });
        let right_value = json!({
            "a.b": {"[0]": 11},
            "a": {"b": 12},
            "slash/key": 13,
            "tilde~key": 14,
            "[x]": 15,
        });
        write_output(
            &left,
            "candidate.checksums.json",
            &canonical_json(&left_value).unwrap(),
        );
        write_output(
            &right,
            "candidate.checksums.json",
            &canonical_json(&right_value).unwrap(),
        );
        let diagnostic = compare_error(&left, &right);
        let paths = diagnostic["outputs"][0]["difference"]["json_fields"]["fields"]
            .as_array()
            .unwrap()
            .iter()
            .map(|field| field["path"].as_str().unwrap())
            .collect::<BTreeSet<_>>();
        assert_eq!(
            paths,
            BTreeSet::from(["/[x]", "/a.b/[0]", "/a/b", "/slash~1key", "/tilde~0key"])
        );

        let root = json_field_differences(&json!(1), &json!(2)).unwrap();
        assert_eq!(root.fields[0].path, "");
        let array = json_field_differences(&json!([1]), &json!([2])).unwrap();
        assert_eq!(array.fields[0].path, "/0");
    }

    #[test]
    fn candidate_directory_comparison_reports_missing_output_and_caps_diagnostics() {
        let t = tempfile::tempdir().unwrap();
        let left = t.path().join("left");
        let right = t.path().join("right");
        fs::create_dir(&left).unwrap();
        fs::create_dir(&right).unwrap();
        write_output(&left, "candidate.tar.gz", b"present");
        write_output(&right, "candidate.checksums.json", br#"{"x":1}"#);
        let diagnostic = compare_error(&left, &right);
        let outputs = diagnostic["outputs"].as_array().unwrap();
        assert_eq!(outputs.len(), 2);
        assert_eq!(outputs[0]["difference"]["classification"], "missing_output");
        assert_eq!(outputs[1]["difference"]["classification"], "missing_output");

        let overflowing = t.path().join("overflowing");
        fs::create_dir(&overflowing).unwrap();
        for index in 0..=MAX_CANDIDATE_OUTPUTS {
            write_output(&overflowing, &format!("output-{index:02}"), b"x");
        }
        assert!(matches!(
            compare_candidate_dirs(&overflowing, &right),
            Err(ReleaseError::Verify(detail)) if detail == "candidate output count exceeds comparison limit"
        ));
    }

    #[test]
    fn candidate_directory_comparison_bounds_json_fields_deterministically() {
        let t = tempfile::tempdir().unwrap();
        let left = t.path().join("left");
        let right = t.path().join("right");
        fs::create_dir(&left).unwrap();
        fs::create_dir(&right).unwrap();
        let left_value = Value::Array((0..100).map(Value::from).collect());
        let right_value = Value::Array((100..200).map(Value::from).collect());
        write_output(
            &left,
            "candidate.checksums.json",
            &canonical_json(&left_value).unwrap(),
        );
        write_output(
            &right,
            "candidate.checksums.json",
            &canonical_json(&right_value).unwrap(),
        );
        let first = compare_error(&left, &right);
        let second = compare_error(&left, &right);
        assert_eq!(first, second);
        let fields = first["outputs"][0]["difference"]["json_fields"]["fields"]
            .as_array()
            .unwrap();
        assert_eq!(fields.len(), MAX_JSON_DIFF_FIELDS);
        assert_eq!(
            first["outputs"][0]["difference"]["json_fields"]["truncated"],
            true
        );
    }

    #[test]
    fn json_diff_bounds_missing_object_keys_and_array_items() {
        let missing_object = Value::Object(
            (0..100)
                .map(|index| (format!("key-{index:03}"), Value::from(index)))
                .collect(),
        );
        let missing_array = Value::Array((0..100).map(Value::from).collect());
        for (left, right) in [
            (Value::Object(serde_json::Map::new()), missing_object),
            (Value::Array(Vec::new()), missing_array),
        ] {
            let first = json_field_differences(&left, &right).unwrap();
            let second = json_field_differences(&left, &right).unwrap();
            assert_eq!(first.fields.len(), MAX_JSON_DIFF_FIELDS);
            assert!(first.truncated);
            assert_eq!(
                canonical_json(&first).unwrap(),
                canonical_json(&second).unwrap()
            );
        }
    }
}
