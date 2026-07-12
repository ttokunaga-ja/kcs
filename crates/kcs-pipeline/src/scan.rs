//! Scan preview contracts.

use std::fs::File;
#[cfg(not(windows))]
use std::fs::Metadata;
use std::io::Read;
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use unicode_normalization::UnicodeNormalization;

use crate::prepare::{hash_bytes, hash_reader};
use crate::{IoResultExt, Result};

const MAX_GLOB_STATES: usize = 100_000;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScanCandidate {
    pub input_path: String,
    pub media_type: String,
    pub size_bytes: u64,
    pub raw_hash: Option<String>,
    pub ignored: bool,
    pub quarantine_reason: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScanPreview {
    pub scope_id: String,
    pub candidates: Vec<ScanCandidate>,
    pub estimated_cost: Option<CostPreview>,
    pub approval_required: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CostPreview {
    pub estimated_usd: f64,
    pub budget_cap_usd: Option<f64>,
    pub budget_warning: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScanPreviewRequest {
    pub scope_path: String,
    pub include_raw_hashes: bool,
    pub require_network_approval: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SecretTier {
    TierA,
    TierB,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IgnoreRule {
    pub pattern: String,
    pub negated: bool,
}

pub fn build_scan_preview(request: ScanPreviewRequest) -> Result<ScanPreview> {
    let scope_path = PathBuf::from(&request.scope_path);
    // R10-3: probe the scope volume's case sensitivity ONCE per scan (git
    // `core.ignorecase` equivalent) so ignore matching can fold case on a
    // case-insensitive FS (APFS default) without folding on a case-sensitive one.
    let case_insensitive = probe_case_insensitive(&scope_path);
    let mut ignore_rules = load_config_ignore(&scope_path)?;
    ignore_rules.extend(load_kcsignore(&scope_path)?);
    let mut candidates = Vec::new();
    collect_direct_candidates(
        &scope_path,
        &ignore_rules,
        request.include_raw_hashes,
        case_insensitive,
        &mut candidates,
    )?;
    candidates.sort_by(|a, b| a.input_path.cmp(&b.input_path));
    let estimated_usd = candidates
        .iter()
        .filter(|candidate| !candidate.ignored)
        .map(|candidate| candidate.size_bytes as f64 / 1_000_000.0 * 0.01)
        .sum::<f64>();
    Ok(ScanPreview {
        scope_id: scope_id_from_scope_json(&scope_path).unwrap_or_else(|| "unknown".to_owned()),
        candidates,
        estimated_cost: Some(CostPreview {
            estimated_usd,
            budget_cap_usd: None,
            budget_warning: None,
        }),
        approval_required: request.require_network_approval,
    })
}

fn collect_direct_candidates(
    scope_path: &Path,
    ignore_rules: &[IgnoreRule],
    include_raw_hashes: bool,
    case_insensitive: bool,
    candidates: &mut Vec<ScanCandidate>,
) -> Result<()> {
    for entry in std::fs::read_dir(scope_path).pipeline_io(scope_path)? {
        let entry = entry.pipeline_io(scope_path)?;
        let name = match entry.file_name().into_string() {
            Ok(name) => name,
            Err(_) => continue,
        };
        if name == ".kcs" || name == ".kcsignore" {
            continue;
        }
        let path = entry.path();
        if is_xdg_state_inside_scope(scope_path, &path) {
            continue;
        }
        let file_type = entry.file_type().pipeline_io(&path)?;
        if !file_type.is_file() {
            continue;
        }
        let relative = path
            .strip_prefix(scope_path)
            .unwrap_or(&path)
            .to_string_lossy()
            .replace('\\', "/");
        if relative == ".kcsignore" {
            continue;
        }
        let mut size_bytes = entry.metadata().pipeline_io(&path)?.len();
        let secret = classify_secret(&relative);
        let ignored = try_ignored_by_rules(
            &relative,
            file_type.is_dir(),
            ignore_rules,
            case_insensitive,
        )? || secret == Some(SecretTier::TierA)
            && !try_explicitly_unignored(
                &relative,
                file_type.is_dir(),
                ignore_rules,
                case_insensitive,
            )?;
        let quarantine_reason = match secret {
            Some(SecretTier::TierA) if ignored => Some("secrets_tier_a_excluded".to_owned()),
            // R19-1: a Tier A secret explicitly un-ignored (`!pattern`) is ingested
            // locally but MUST still be held from online send like Tier B — the lift
            // approves local management, not cloud upload (10 §1.1: the mechanism
            // prevents "オンライン送信事故"). This marker drives the audit record; the
            // send-blocking gates key on `classify_secret` directly.
            Some(SecretTier::TierA) => Some("secrets_tier_a_online_hold".to_owned()),
            Some(SecretTier::TierB) => Some("secrets_tier_b_warning".to_owned()),
            _ => None,
        };
        let raw_hash = if include_raw_hashes && !ignored {
            let (mut file, metadata) = open_verified_regular_file(&path)?;
            size_bytes = metadata.len();
            let read_limit = metadata.len().checked_add(1).ok_or_else(|| {
                crate::PipelineError::contract(
                    "KCS-E-SCAN-INPUT-OVERSIZED-001",
                    format!("scan candidate is too large to hash: {}", path.display()),
                )
            })?;
            let mut reader = (&mut file).take(read_limit);
            let raw_hash = hash_reader(&mut reader).pipeline_io(&path)?;
            if reader.limit() == 0 {
                return Err(crate::PipelineError::contract(
                    "KCS-E-SCAN-INPUT-CHANGED-001",
                    format!(
                        "scan candidate grew while it was being hashed: {}",
                        path.display()
                    ),
                ));
            }
            ensure_file_unchanged(&file, &metadata, &path)?;
            Some(raw_hash)
        } else {
            None
        };
        candidates.push(ScanCandidate {
            input_path: relative.clone(),
            media_type: media_type_for_path(&path).to_owned(),
            size_bytes,
            raw_hash,
            ignored,
            quarantine_reason,
        });
    }
    Ok(())
}

/// A direct-child input read through one verified file handle and bounded before
/// allocation. The returned hash always identifies the returned bytes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedScanInput {
    pub bytes: Vec<u8>,
    pub raw_hash: String,
    pub size_bytes: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedScanIdentity {
    pub raw_hash: String,
    pub size_bytes: u64,
}

/// Open and read a scope-local direct child without trusting a pathname check for
/// a later pathname read. The metadata size is checked before allocation, and a
/// bounded reader catches growth after that check.
pub fn read_verified_scan_input(
    scope_path: &Path,
    input_path: &str,
    max_bytes: u64,
) -> Result<VerifiedScanInput> {
    let path = direct_child_path(scope_path, input_path)?;
    let (mut file, metadata) = open_verified_regular_file(&path)?;
    if metadata.len() > max_bytes {
        return Err(crate::PipelineError::contract(
            "KCS-E-SCAN-INPUT-OVERSIZED-001",
            format!(
                "input {} is {} bytes, above the {} byte limit",
                path.display(),
                metadata.len(),
                max_bytes
            ),
        ));
    }

    let initial_capacity = usize::try_from(metadata.len()).map_err(|_| {
        crate::PipelineError::contract(
            "KCS-E-SCAN-INPUT-OVERSIZED-001",
            format!("input {} cannot fit in process memory", path.display()),
        )
    })?;
    let mut bytes = Vec::new();
    bytes.try_reserve_exact(initial_capacity).map_err(|_| {
        crate::PipelineError::contract(
            "KCS-E-SCAN-INPUT-OVERSIZED-001",
            format!("input {} cannot fit in process memory", path.display()),
        )
    })?;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let remaining = max_bytes.saturating_sub(bytes.len() as u64);
        let read_cap = std::cmp::min(buffer.len() as u64, remaining.saturating_add(1)) as usize;
        let read = file.read(&mut buffer[..read_cap]).pipeline_io(&path)?;
        if read == 0 {
            break;
        }
        if read as u64 > remaining {
            return Err(crate::PipelineError::contract(
                "KCS-E-SCAN-INPUT-OVERSIZED-001",
                format!(
                    "input {} grew beyond the {} byte limit",
                    path.display(),
                    max_bytes
                ),
            ));
        }
        bytes.try_reserve_exact(read).map_err(|_| {
            crate::PipelineError::contract(
                "KCS-E-SCAN-INPUT-OVERSIZED-001",
                format!("input {} cannot fit in process memory", path.display()),
            )
        })?;
        bytes.extend_from_slice(&buffer[..read]);
    }
    ensure_file_unchanged(&file, &metadata, &path)?;

    Ok(VerifiedScanInput {
        size_bytes: bytes.len() as u64,
        raw_hash: hash_bytes(&bytes),
        bytes,
    })
}

/// Hash a direct-child input with fixed working memory through the same verified
/// file handle used for metadata checks. The `max + 1` reader bounds growth while
/// hashing, so callers can scan for an identity without materializing file bytes.
pub fn hash_verified_scan_input(
    scope_path: &Path,
    input_path: &str,
    max_bytes: u64,
) -> Result<VerifiedScanIdentity> {
    let path = direct_child_path(scope_path, input_path)?;
    let (mut file, metadata) = open_verified_regular_file(&path)?;
    if metadata.len() > max_bytes {
        return Err(crate::PipelineError::contract(
            "KCS-E-SCAN-INPUT-OVERSIZED-001",
            format!(
                "input {} is {} bytes, above the {} byte limit",
                path.display(),
                metadata.len(),
                max_bytes
            ),
        ));
    }
    let raw_hash = {
        let mut limited = (&mut file).take(max_bytes.saturating_add(1));
        let raw_hash = hash_reader(&mut limited).pipeline_io(&path)?;
        if limited.limit() == 0 {
            return Err(crate::PipelineError::contract(
                "KCS-E-SCAN-INPUT-OVERSIZED-001",
                format!(
                    "input {} grew beyond the {} byte limit",
                    path.display(),
                    max_bytes
                ),
            ));
        }
        raw_hash
    };
    ensure_file_unchanged(&file, &metadata, &path)?;
    Ok(VerifiedScanIdentity {
        raw_hash,
        size_bytes: metadata.len(),
    })
}

/// Re-evaluate current ignore authorization and byte identity for a durable task.
/// Errors are intentionally distinct from `false` so callers can fail closed while
/// retaining an audit reason.
pub fn current_scan_allows_file(
    scope_path: &Path,
    input_path: &str,
    expected_raw_hash: &str,
    max_bytes: u64,
) -> Result<bool> {
    if !current_scan_policy_allows_file(scope_path, input_path)? {
        return Ok(false);
    }
    let identity = hash_verified_scan_input(scope_path, input_path, max_bytes)?;
    Ok(identity.raw_hash == expected_raw_hash)
}

/// Re-evaluate path classification without reopening input bytes. Callers that
/// already hold a verified buffer can bind its hash separately and use this check
/// immediately before a sink without creating a second pathname-read race.
pub fn current_scan_policy_allows_file(scope_path: &Path, input_path: &str) -> Result<bool> {
    let path = direct_child_path(scope_path, input_path)?;
    if input_path == ".kcs" || input_path == ".kcsignore" {
        return Ok(false);
    }
    if is_xdg_state_inside_scope(scope_path, &path) {
        return Ok(false);
    }
    let listed = match std::fs::symlink_metadata(&path) {
        Ok(metadata) => metadata,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(err) => {
            return Err(crate::PipelineError::Io {
                path: path.display().to_string(),
                message: err.to_string(),
            })
        }
    };
    if !listed.file_type().is_file() {
        return Ok(false);
    }

    let case_insensitive = probe_case_insensitive(scope_path);
    let mut ignore_rules = load_config_ignore(scope_path)?;
    ignore_rules.extend(load_kcsignore(scope_path)?);
    let secret = classify_secret(input_path);
    let ignored = try_ignored_by_rules(input_path, false, &ignore_rules, case_insensitive)?
        || secret == Some(SecretTier::TierA)
            && !try_explicitly_unignored(input_path, false, &ignore_rules, case_insensitive)?;
    if ignored {
        return Ok(false);
    }

    Ok(true)
}

fn direct_child_path(scope_path: &Path, input_path: &str) -> Result<PathBuf> {
    let relative = Path::new(input_path);
    let mut components = relative.components();
    let valid = !input_path.is_empty()
        && !input_path.contains('/')
        && !input_path.contains('\\')
        && matches!(components.next(), Some(Component::Normal(_)))
        && components.next().is_none();
    if !valid {
        return Err(crate::PipelineError::path(input_path));
    }
    Ok(scope_path.join(relative))
}

#[derive(Debug)]
struct OpenedFileState {
    #[cfg(not(windows))]
    metadata: Metadata,
    #[cfg(windows)]
    information: crate::windows_file::WindowsFileInformation,
}

impl OpenedFileState {
    fn len(&self) -> u64 {
        #[cfg(windows)]
        {
            self.information.file_size()
        }
        #[cfg(not(windows))]
        {
            self.metadata.len()
        }
    }
}

fn open_verified_regular_file(path: &Path) -> Result<(File, OpenedFileState)> {
    #[cfg(windows)]
    {
        let listed = crate::windows_file::open_path_no_follow(path).pipeline_io(path)?;
        let listed_information = crate::windows_file::information(&listed).pipeline_io(path)?;
        if !listed_information.is_regular_file() {
            return Err(crate::PipelineError::contract(
                "KCS-E-SCAN-FILE-IDENTITY-001",
                format!("scan candidate is not a regular file: {}", path.display()),
            ));
        }
        let file = File::open(path).pipeline_io(path)?;
        verify_opened_regular_file(path, listed_information, file)
    }

    #[cfg(not(windows))]
    {
        // `symlink_metadata` does not follow the final component. Comparing its identity
        // with the opened handle closes the swap-to-symlink interval without requiring a
        // later pathname read.
        let listed = std::fs::symlink_metadata(path).pipeline_io(path)?;
        if !listed.file_type().is_file() {
            return Err(crate::PipelineError::contract(
                "KCS-E-SCAN-FILE-IDENTITY-001",
                format!("scan candidate is not a regular file: {}", path.display()),
            ));
        }
        let file = File::open(path).pipeline_io(path)?;
        verify_opened_regular_file(path, listed, file)
    }
}

#[cfg(not(windows))]
fn verify_opened_regular_file(
    path: &Path,
    listed: Metadata,
    file: File,
) -> Result<(File, OpenedFileState)> {
    let opened = file.metadata().pipeline_io(path)?;
    if !opened.is_file() || !same_file_identity(&listed, &opened) {
        return Err(crate::PipelineError::contract(
            "KCS-E-SCAN-FILE-IDENTITY-001",
            format!(
                "scan candidate changed while it was being opened: {}",
                path.display()
            ),
        ));
    }
    Ok((file, OpenedFileState { metadata: opened }))
}

#[cfg(windows)]
fn verify_opened_regular_file(
    path: &Path,
    listed: crate::windows_file::WindowsFileInformation,
    file: File,
) -> Result<(File, OpenedFileState)> {
    let opened = file.metadata().pipeline_io(path)?;
    let information = crate::windows_file::information(&file).pipeline_io(path)?;
    if !opened.is_file() || !information.is_regular_file() || !listed.same_identity(information) {
        return Err(crate::PipelineError::contract(
            "KCS-E-SCAN-FILE-IDENTITY-001",
            format!(
                "scan candidate changed while it was being opened: {}",
                path.display()
            ),
        ));
    }
    Ok((file, OpenedFileState { information }))
}

fn ensure_file_unchanged(file: &File, before: &OpenedFileState, path: &Path) -> Result<()> {
    #[cfg(windows)]
    let unchanged = {
        let after = crate::windows_file::information(file).pipeline_io(path)?;
        after.is_regular_file() && before.information.same_file_state(after)
    };
    #[cfg(not(windows))]
    let unchanged = {
        let after = file.metadata().pipeline_io(path)?;
        same_file_state(&before.metadata, &after)
    };
    if !unchanged {
        return Err(crate::PipelineError::contract(
            "KCS-E-SCAN-INPUT-CHANGED-001",
            format!(
                "scan candidate changed while it was being read: {}",
                path.display()
            ),
        ));
    }
    Ok(())
}

#[cfg(unix)]
fn same_file_identity(left: &Metadata, right: &Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    left.dev() == right.dev() && left.ino() == right.ino()
}

#[cfg(not(any(unix, windows)))]
fn same_file_identity(left: &Metadata, right: &Metadata) -> bool {
    left.file_type() == right.file_type()
        && left.len() == right.len()
        && left.modified().ok() == right.modified().ok()
}

#[cfg(unix)]
fn same_file_state(left: &Metadata, right: &Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    same_file_identity(left, right)
        && left.len() == right.len()
        && left.mtime() == right.mtime()
        && left.mtime_nsec() == right.mtime_nsec()
        && left.ctime() == right.ctime()
        && left.ctime_nsec() == right.ctime_nsec()
}

#[cfg(not(any(unix, windows)))]
fn same_file_state(left: &Metadata, right: &Metadata) -> bool {
    same_file_identity(left, right)
}

fn is_xdg_state_inside_scope(scope_path: &Path, path: &Path) -> bool {
    let scope_path = scope_path
        .canonicalize()
        .unwrap_or_else(|_| scope_path.to_path_buf());
    let path = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    ["XDG_CONFIG_HOME", "XDG_DATA_HOME"]
        .iter()
        .filter_map(std::env::var_os)
        .map(PathBuf::from)
        .map(|path| path.canonicalize().unwrap_or(path))
        .filter(|xdg| xdg.starts_with(&scope_path))
        .any(|xdg| path == xdg || path.starts_with(&xdg))
}

pub fn load_kcsignore(scope_path: &Path) -> Result<Vec<IgnoreRule>> {
    let path = scope_path.join(".kcsignore");
    if !path.is_file() {
        return Ok(Vec::new());
    }
    let content = std::fs::read_to_string(&path).pipeline_io(&path)?;
    Ok(content
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                return None;
            }
            let (negated, pattern) = trimmed
                .strip_prefix('!')
                .map(|pattern| (true, pattern))
                .unwrap_or((false, trimmed));
            Some(IgnoreRule {
                pattern: pattern.to_owned(),
                negated,
            })
        })
        .collect())
}

pub fn load_config_ignore(scope_path: &Path) -> Result<Vec<IgnoreRule>> {
    let path = scope_path.join(".kcs/config.toml");
    let text = match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(err) => {
            return Err(crate::PipelineError::Io {
                path: path.display().to_string(),
                message: err.to_string(),
            });
        }
    };
    let value: toml::Value =
        toml::from_str(&text).map_err(|err| crate::PipelineError::Schema(err.to_string()))?;
    let Some(ignore) = value
        .get("scope")
        .and_then(|scope| scope.get("ignore"))
        .and_then(toml::Value::as_array)
    else {
        return Ok(Vec::new());
    };
    Ok(ignore
        .iter()
        .filter_map(toml::Value::as_str)
        .map(|pattern| IgnoreRule {
            pattern: pattern.trim_start_matches('!').to_owned(),
            negated: pattern.starts_with('!'),
        })
        .collect())
}

#[must_use]
pub fn classify_secret(path: &str) -> Option<SecretTier> {
    let normalized = path.trim_start_matches('/').replace('\\', "/");
    let name = normalized.rsplit('/').next().unwrap_or(&normalized);
    let lower = name.to_ascii_lowercase();
    if kcs_core::scope::is_tier_a_secret_name(path) {
        return Some(SecretTier::TierA);
    }
    let tier_b = ["credentials", "secret", "token", "apikey", "password"]
        .iter()
        .any(|needle| lower.contains(needle));
    tier_b.then_some(SecretTier::TierB)
}

/// R10-3: probe whether `scope_path`'s volume treats names case-insensitively
/// (APFS default, exFAT, NTFS) — the moral equivalent of git's `core.ignorecase`.
/// Writes a unique probe file and checks whether a name differing only in case
/// resolves to it. Best-effort: any I/O failure returns `false` (assume
/// case-sensitive) so two genuinely distinct names on a case-sensitive volume are
/// never folded together (which would be its own silent data loss). The probe
/// file(s) are always removed.
fn probe_case_insensitive(scope_path: &Path) -> bool {
    // Probe inside `.kcs` (present for an initialized scope and itself skipped by the
    // scanner) so the probe file never appears among the user's candidates; fall back
    // to the scope root if `.kcs` is somehow absent.
    let dir = {
        let kcs = scope_path.join(".kcs");
        if kcs.is_dir() {
            kcs
        } else {
            scope_path.to_path_buf()
        }
    };
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or_default();
    let stem = format!(".kcs-caseprobe-{}-{}", std::process::id(), nanos);
    let lower = dir.join(format!("{stem}-a"));
    let upper = dir.join(format!("{stem}-A"));
    if std::fs::write(&lower, b"").is_err() {
        return false;
    }
    let insensitive = upper.exists();
    // On an insensitive FS `lower` and `upper` are the same inode, so removing `lower`
    // clears both; on a sensitive FS `upper` was never created.
    let _ = std::fs::remove_file(&lower);
    let _ = std::fs::remove_file(&upper);
    insensitive
}

#[must_use]
pub fn ignored_by_rules(
    path: &str,
    is_dir: bool,
    rules: &[IgnoreRule],
    case_insensitive: bool,
) -> bool {
    // This compatibility API cannot surface a malformed/over-budget rule. Fail
    // closed; scan construction uses the fallible variant below and reports it.
    try_ignored_by_rules(path, is_dir, rules, case_insensitive).unwrap_or(true)
}

fn try_ignored_by_rules(
    path: &str,
    is_dir: bool,
    rules: &[IgnoreRule],
    case_insensitive: bool,
) -> Result<bool> {
    let mut ignored = false;
    for rule in rules {
        if matches_ignore_pattern(path, is_dir, &rule.pattern, case_insensitive)? {
            ignored = !rule.negated;
        }
    }
    Ok(ignored)
}

fn try_explicitly_unignored(
    path: &str,
    is_dir: bool,
    rules: &[IgnoreRule],
    case_insensitive: bool,
) -> Result<bool> {
    for rule in rules.iter().filter(|rule| rule.negated) {
        if matches_ignore_pattern(path, is_dir, &rule.pattern, case_insensitive)? {
            return Ok(true);
        }
    }
    Ok(false)
}

fn matches_ignore_pattern(
    path: &str,
    is_dir: bool,
    pattern: &str,
    case_insensitive: bool,
) -> Result<bool> {
    // R9-1: match on the NFC projection of BOTH sides so a Unicode canonically
    // equivalent `.kcsignore` / `[scope] ignore` pattern reliably excludes a file
    // whose on-disk name uses a different normal form (NFD names are routine on
    // macOS/APFS via Finder/iCloud/zip/IME). This normalizes only the *matching*
    // projection — `ScanCandidate.input_path` and the CAS/identity raw bytes stay
    // the original bytes (R8 F2: normalize the comparison, never the identity).
    let mut path = path.nfc().collect::<String>();
    let mut pattern = pattern.nfc().collect::<String>();
    // R10-3: on a case-insensitive volume, fold BOTH sides to lowercase (Unicode
    // aware) after NFC so a pattern whose case differs from the on-disk name still
    // excludes it — matching git's `core.ignorecase` behavior. The glob metacharacters
    // (`*`, `?`, `/`, `**`) are ASCII and unaffected by lowercasing. On a
    // case-sensitive volume we do NOT fold (folding would wrongly exclude a distinct
    // file, another silent data loss).
    if case_insensitive {
        path = path.to_lowercase();
        pattern = pattern.to_lowercase();
    }
    let directory_only = pattern.ends_with('/');
    if directory_only && !is_dir {
        return Ok(false);
    }
    let rooted = pattern.starts_with('/');
    let pattern = pattern.trim_start_matches('/').trim_end_matches('/');
    let normalized_path = path.trim_start_matches('/').replace('\\', "/");
    if !rooted && !pattern.contains('/') {
        return wildcard_match(
            pattern,
            normalized_path
                .rsplit('/')
                .next()
                .unwrap_or(&normalized_path),
        );
    }
    wildcard_match(pattern, &normalized_path)
}

fn wildcard_match(pattern: &str, value: &str) -> Result<bool> {
    // Match Unicode scalar values: `?` consumes one scalar, never one UTF-8 byte.
    // The bottom-up state table visits each (pattern, value) pair at most once,
    // replacing recursive backtracking with explicitly bounded work.
    let pattern = pattern.chars().collect::<Vec<_>>();
    let value = value.chars().collect::<Vec<_>>();
    let width = value.len().checked_add(1).ok_or_else(glob_budget_error)?;
    let states = pattern
        .len()
        .checked_add(1)
        .and_then(|height| height.checked_mul(width))
        .filter(|states| *states <= MAX_GLOB_STATES)
        .ok_or_else(glob_budget_error)?;
    let mut matched = vec![false; states];
    let at = |pi: usize, vi: usize| pi * width + vi;
    let mut next_slash = vec![None; width];
    let mut nearest = None;
    for vi in (0..value.len()).rev() {
        if value[vi] == '/' {
            nearest = Some(vi);
        }
        next_slash[vi] = nearest;
    }
    matched[at(pattern.len(), value.len())] = true;

    for pi in (0..pattern.len()).rev() {
        for vi in (0..=value.len()).rev() {
            let is_terminal_double_star =
                pi + 2 == pattern.len() && pattern[pi] == '*' && pattern[pi + 1] == '*';
            let is_double_star_directory = pi + 2 < pattern.len()
                && pattern[pi] == '*'
                && pattern[pi + 1] == '*'
                && pattern[pi + 2] == '/';
            matched[at(pi, vi)] = if is_terminal_double_star {
                true
            } else if is_double_star_directory {
                matched[at(pi + 3, vi)]
                    || next_slash[vi].is_some_and(|slash| matched[at(pi, slash + 1)])
            } else {
                match pattern[pi] {
                    '*' => {
                        matched[at(pi + 1, vi)]
                            || vi < value.len() && value[vi] != '/' && matched[at(pi, vi + 1)]
                    }
                    '?' => vi < value.len() && value[vi] != '/' && matched[at(pi + 1, vi + 1)],
                    ch => vi < value.len() && ch == value[vi] && matched[at(pi + 1, vi + 1)],
                }
            };
        }
    }
    Ok(matched[0])
}

fn glob_budget_error() -> crate::PipelineError {
    crate::PipelineError::contract(
        "KCS-E-SCAN-IGNORE-BUDGET-001",
        format!("ignore pattern exceeds the {MAX_GLOB_STATES} state matching budget"),
    )
}

fn media_type_for_path(path: &Path) -> &'static str {
    // R21-4: lowercase the extension so an uppercase-extension text-native file
    // (`README.MD`, `NOTE.TXT`, `MAIN.RS`) is recognized as text/markdown/plain/code and
    // handled locally — not folded to octet-stream and shipped to online OCR (R9-2).
    match path
        .extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "md" | "markdown" => "text/markdown",
        "txt" => "text/plain",
        "rs" | "py" | "js" | "ts" | "go" | "java" | "c" | "h" | "cpp" => "text/x-code",
        "pdf" => "application/pdf",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        // R20-6: recognize OOXML office documents by their real MIME so they are treated as
        // non-text-native (routed to online OCR), not folded into octet-stream and given a
        // raw-bytes local passthrough that evidences the ZIP bytes as searchable text.
        "docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx" => "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        _ => "application/octet-stream",
    }
}

fn scope_id_from_scope_json(scope_path: &Path) -> Option<String> {
    let value = std::fs::read_to_string(scope_path.join(".kcs/scope.json")).ok()?;
    let value = serde_json::from_str::<serde_json::Value>(&value).ok()?;
    value.get("scope_id")?.as_str().map(str::to_owned)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_scan_candidate_serializes() {
        let candidate = ScanCandidate {
            input_path: "report.pdf".to_owned(),
            media_type: "application/pdf".to_owned(),
            size_bytes: 42,
            raw_hash: None,
            ignored: false,
            quarantine_reason: None,
        };

        let value = serde_json::to_value(candidate).expect("serialize scan candidate");
        assert_eq!(value["input_path"], "report.pdf");
    }

    #[test]
    fn secrets_and_ignore_rules_are_applied_in_order() {
        let rules = vec![
            IgnoreRule {
                pattern: "*.log".to_owned(),
                negated: false,
            },
            IgnoreRule {
                pattern: "keep.log".to_owned(),
                negated: true,
            },
        ];
        assert_eq!(classify_secret(".env"), Some(SecretTier::TierA));
        assert_eq!(classify_secret("api_token.txt"), Some(SecretTier::TierB));
        assert!(ignored_by_rules("debug.log", false, &rules, false));
        assert!(!ignored_by_rules("keep.log", false, &rules, false));
    }

    #[test]
    fn r9_1_ignore_matches_across_unicode_normal_forms() {
        // R9-1: a canonically-equivalent ignore pattern must exclude a file whose
        // on-disk name uses a different Unicode normal form. Pre-fix the byte-wise
        // comparison missed this, so an NFD file name (routine on macOS/APFS)
        // slipped past an NFC `.kcsignore` pattern and was indexed / sent online.
        let nfc_name = "café.md"; // é = U+00E9 (precomposed)
        let nfd_name = "cafe\u{0301}.md"; // e + U+0301 combining acute
        assert_ne!(
            nfc_name.as_bytes(),
            nfd_name.as_bytes(),
            "the two normal forms must differ byte-wise"
        );

        let nfc_rule = vec![IgnoreRule {
            pattern: nfc_name.to_owned(),
            negated: false,
        }];
        let nfd_rule = vec![IgnoreRule {
            pattern: nfd_name.to_owned(),
            negated: false,
        }];

        // NFC pattern excludes an NFD on-disk name, and vice versa.
        assert!(ignored_by_rules(nfd_name, false, &nfc_rule, false));
        assert!(ignored_by_rules(nfc_name, false, &nfd_rule, false));
        // The same-form case still works.
        assert!(ignored_by_rules(nfc_name, false, &nfc_rule, false));
        // A genuinely different name is still not excluded.
        assert!(!ignored_by_rules("other.md", false, &nfc_rule, false));
    }

    #[test]
    fn r10_3_case_insensitive_volume_folds_ignore_pattern() {
        // R10-3: a lowercase ignore pattern must exclude a differently-cased on-disk
        // name on a case-insensitive volume (where both names are the SAME file), and
        // must NOT fold on a case-sensitive volume (folding would wrongly exclude a
        // distinct file — silent data loss).
        let rule = vec![IgnoreRule {
            pattern: "casefixture.md".to_owned(),
            negated: false,
        }];
        // Insensitive volume: case-different name is excluded.
        assert!(ignored_by_rules("CaseFixture.md", false, &rule, true));
        // Sensitive volume: case-different name is NOT excluded.
        assert!(!ignored_by_rules("CaseFixture.md", false, &rule, false));
        // Exact-case name is excluded on either volume.
        assert!(ignored_by_rules("casefixture.md", false, &rule, false));
        assert!(ignored_by_rules("casefixture.md", false, &rule, true));
        // A genuinely different name is never excluded, even when folding.
        assert!(!ignored_by_rules("other.md", false, &rule, true));
        // Unicode-aware fold: an uppercase-É (U+00C9) pattern folds to match an é name.
        let unicode_rule = vec![IgnoreRule {
            pattern: "CAF\u{00c9}.md".to_owned(),
            negated: false,
        }];
        assert!(ignored_by_rules(
            "caf\u{00e9}.md",
            false,
            &unicode_rule,
            true
        ));
        assert!(!ignored_by_rules(
            "caf\u{00e9}.md",
            false,
            &unicode_rule,
            false
        ));
        // Negation (`!keep`) unignores across case on an insensitive volume too.
        let negation = vec![
            IgnoreRule {
                pattern: "*.log".to_owned(),
                negated: false,
            },
            IgnoreRule {
                pattern: "KEEP.log".to_owned(),
                negated: true,
            },
        ];
        assert!(try_explicitly_unignored("keep.log", false, &negation, true).unwrap());
        assert!(!try_explicitly_unignored("keep.log", false, &negation, false).unwrap());
    }

    #[test]
    fn r10_3_probe_matches_actual_fs_case_behavior_and_cleans_up() {
        // The probe result must equal an independent ground-truth check on the SAME
        // volume, and the probe must never leave its files behind.
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("groundtruth-a"), b"").unwrap();
        let fs_insensitive = dir.path().join("GROUNDTRUTH-A").exists();
        std::fs::remove_file(dir.path().join("groundtruth-a")).unwrap();
        assert_eq!(probe_case_insensitive(dir.path()), fs_insensitive);
        let leftovers: Vec<_> = std::fs::read_dir(dir.path())
            .unwrap()
            .filter_map(std::result::Result::ok)
            .filter(|entry| {
                entry
                    .file_name()
                    .to_string_lossy()
                    .contains("kcs-caseprobe")
            })
            .collect();
        assert!(
            leftovers.is_empty(),
            "probe must remove its files: {leftovers:?}"
        );
    }

    #[test]
    fn r23_cand_005_question_matches_one_unicode_scalar() {
        let rules = vec![IgnoreRule {
            pattern: "?.txt".to_owned(),
            negated: false,
        }];
        for name in ["a.txt", "é.txt", "e\u{301}.txt", "😀.txt"] {
            assert!(
                ignored_by_rules(name, false, &rules, false),
                "one-scalar name should be ignored: {name:?}"
            );
        }
        assert!(!ignored_by_rules("ab.txt", false, &rules, false));
        assert!(!wildcard_match("?", "/").unwrap());
    }

    #[test]
    fn r23_cand_005_unicode_rule_applies_through_scan_preview() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join(".kcsignore"), "?.txt\n").unwrap();
        std::fs::write(dir.path().join("é.txt"), b"excluded").unwrap();
        std::fs::write(dir.path().join("ab.txt"), b"included").unwrap();

        let preview = build_scan_preview(ScanPreviewRequest {
            scope_path: dir.path().display().to_string(),
            include_raw_hashes: false,
            require_network_approval: false,
        })
        .unwrap();
        assert!(
            preview
                .candidates
                .iter()
                .find(|candidate| candidate.input_path == "é.txt")
                .unwrap()
                .ignored
        );
        assert!(
            !preview
                .candidates
                .iter()
                .find(|candidate| candidate.input_path == "ab.txt")
                .unwrap()
                .ignored
        );
    }

    #[test]
    fn r23_cand_017_adversarial_glob_visits_bounded_states() {
        let mut pattern = "*a".repeat(64);
        pattern.push('b');
        let value = "a".repeat(64);
        assert!(!wildcard_match(&pattern, &value).unwrap());

        let over_budget = "a".repeat(MAX_GLOB_STATES);
        let error = wildcard_match(&over_budget, "").unwrap_err();
        assert!(error.to_string().contains("KCS-E-SCAN-IGNORE-BUDGET-001"));
    }

    #[test]
    fn r23_cand_017_star_and_double_star_semantics_remain_intact() {
        assert!(wildcard_match("*.md", "notes.md").unwrap());
        assert!(!wildcard_match("*.md", "dir/notes.md").unwrap());
        assert!(wildcard_match("**/notes.md", "notes.md").unwrap());
        assert!(wildcard_match("**/notes.md", "a/b/notes.md").unwrap());
        assert!(!wildcard_match("**/notes.md", "a/b/notes.txt").unwrap());
    }

    #[test]
    fn r23_cand_032_scan_hash_streams_from_verified_handle() {
        let dir = tempfile::tempdir().unwrap();
        let bytes = vec![0x5a; 256 * 1024];
        std::fs::write(dir.path().join("large.bin"), &bytes).unwrap();

        let preview = build_scan_preview(ScanPreviewRequest {
            scope_path: dir.path().display().to_string(),
            include_raw_hashes: true,
            require_network_approval: false,
        })
        .unwrap();
        let candidate = preview
            .candidates
            .iter()
            .find(|candidate| candidate.input_path == "large.bin")
            .unwrap();
        assert_eq!(candidate.size_bytes, bytes.len() as u64);
        assert_eq!(
            candidate.raw_hash.as_deref(),
            Some(hash_bytes(&bytes).as_str())
        );
    }

    #[test]
    fn r23_cand_027_verified_read_is_bounded_and_scope_local() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("small.txt"), b"hello").unwrap();

        let input = read_verified_scan_input(dir.path(), "small.txt", 5).unwrap();
        assert_eq!(input.bytes, b"hello");
        assert_eq!(input.raw_hash, hash_bytes(b"hello"));
        assert!(read_verified_scan_input(dir.path(), "small.txt", 4).is_err());
        assert!(read_verified_scan_input(dir.path(), "../small.txt", 5).is_err());
    }

    #[test]
    fn r23_cand_057_streaming_identity_honors_exact_limit() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("bounded.bin"), b"12345").unwrap();

        let identity = hash_verified_scan_input(dir.path(), "bounded.bin", 5).unwrap();
        assert_eq!(identity.size_bytes, 5);
        assert_eq!(identity.raw_hash, hash_bytes(b"12345"));
        assert!(hash_verified_scan_input(dir.path(), "bounded.bin", 4).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn r23_cand_027_verified_read_rejects_symlink_target() {
        use std::os::unix::fs::symlink;

        let dir = tempfile::tempdir().unwrap();
        let outside = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(outside.path(), b"outside").unwrap();
        symlink(outside.path(), dir.path().join("inside.txt")).unwrap();

        let error = read_verified_scan_input(dir.path(), "inside.txt", 1024).unwrap_err();
        assert!(error.to_string().contains("KCS-E-SCAN-FILE-IDENTITY-001"));
    }

    #[cfg(unix)]
    #[test]
    fn r23_cand_027_replacement_after_listing_rejects_outside_handle() {
        use std::os::unix::fs::symlink;

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("inside.txt");
        std::fs::write(&path, b"inside").unwrap();
        let listed = std::fs::symlink_metadata(&path).unwrap();

        let outside = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(outside.path(), b"outside").unwrap();
        std::fs::remove_file(&path).unwrap();
        symlink(outside.path(), &path).unwrap();
        let outside_handle = File::open(&path).unwrap();

        let error = verify_opened_regular_file(&path, listed, outside_handle).unwrap_err();
        assert!(error.to_string().contains("KCS-E-SCAN-FILE-IDENTITY-001"));
    }

    #[test]
    fn r23_cand_067_current_ignore_policy_reauthorizes_durable_input() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("private.pdf"), b"%PDF BT (text)").unwrap();
        let raw_hash = hash_bytes(b"%PDF BT (text)");

        assert!(current_scan_allows_file(dir.path(), "private.pdf", &raw_hash, 64).unwrap());
        assert!(
            !current_scan_allows_file(dir.path(), "private.pdf", &hash_bytes(b"other"), 64)
                .unwrap()
        );
        std::fs::write(dir.path().join(".kcsignore"), "private.pdf\n").unwrap();
        assert!(!current_scan_allows_file(dir.path(), "private.pdf", &raw_hash, 64).unwrap());

        std::fs::write(dir.path().join(".kcsignore"), "").unwrap();
        assert!(current_scan_allows_file(dir.path(), "private.pdf", &raw_hash, 13).is_err());
    }
}
