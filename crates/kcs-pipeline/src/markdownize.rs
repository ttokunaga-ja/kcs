//! Markdownize and normalized-unit contracts.

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use kcs_adapter::types as adapter_types;
use kcs_core::scope::{new_ulid, now_utc_seconds};
use serde::{Deserialize, Serialize};

use crate::prepare::{
    hash_bytes, unit_ref as prepared_unit_ref, PreparedUnit, UnitFingerprint, UnitType,
};
use crate::store_path::{ensure_store_directory_path, resolve_existing_store_path, StorePathKind};
use crate::{IoResultExt, PipelineError, Result};

static ATOMIC_WRITE_SEQUENCE: AtomicU64 = AtomicU64::new(0);
const MAX_NORMALIZED_MANIFEST_BYTES: u64 = 8 * 1024 * 1024;
const MAX_NORMALIZED_UNIT_BYTES: u64 = 128 * 1024 * 1024;
const MAX_NORMALIZED_INSTANCE_BYTES: u64 = 256 * 1024 * 1024;

#[derive(Debug, Clone, Copy)]
struct NormalizedSizeLimits {
    manifest_bytes: u64,
    unit_bytes: u64,
    instance_bytes: u64,
}

const NORMALIZED_SIZE_LIMITS: NormalizedSizeLimits = NormalizedSizeLimits {
    manifest_bytes: MAX_NORMALIZED_MANIFEST_BYTES,
    unit_bytes: MAX_NORMALIZED_UNIT_BYTES,
    instance_bytes: MAX_NORMALIZED_INSTANCE_BYTES,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MarkdownizeMode {
    Full,
    Incremental,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UnitStatus {
    Done,
    Failed,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UnitRef {
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub unit_key: String,
    pub unit_ref: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReusedFrom {
    pub raw_hash: String,
    pub gen: u64,
    pub unit_key: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NormalizedUnitObject {
    pub unit_key: String,
    pub unit_type: UnitType,
    pub raw_hash: String,
    pub prepared_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub mode: MarkdownizeMode,
    pub markdown: String,
    pub reused_from: Option<ReusedFrom>,
    pub generated_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct NormalizedUnitManifestEntry {
    pub order: u64,
    pub unit_key: String,
    pub unit_ref: String,
    pub unit_type: UnitType,
    pub status: UnitStatus,
    pub prepared_hash: String,
    pub error_kind: Option<String>,
}

#[derive(Deserialize)]
struct UncheckedNormalizedUnitManifestEntry {
    order: u64,
    unit_key: String,
    unit_ref: String,
    unit_type: UnitType,
    status: UnitStatus,
    prepared_hash: String,
    error_kind: Option<String>,
}

impl<'de> Deserialize<'de> for NormalizedUnitManifestEntry {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let entry = UncheckedNormalizedUnitManifestEntry::deserialize(deserializer)?;
        let expected = prepared_unit_ref(&entry.unit_key);
        let canonical_shape = entry.unit_ref.len() == 16
            && entry
                .unit_ref
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase());
        if entry.unit_key.is_empty() || !canonical_shape || entry.unit_ref != expected {
            return Err(serde::de::Error::custom(format!(
                "manifest unit_ref is not derived from unit_key {:?}",
                entry.unit_key
            )));
        }
        Ok(Self {
            order: entry.order,
            unit_key: entry.unit_key,
            unit_ref: entry.unit_ref,
            unit_type: entry.unit_type,
            status: entry.status,
            prepared_hash: entry.prepared_hash,
            error_kind: entry.error_kind,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NormalizedInstanceManifest {
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub parent_gen: Option<u64>,
    pub run_id: String,
    pub units: Vec<NormalizedUnitManifestEntry>,
    pub generated_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NormalizedInstanceIdentity {
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValidatedNormalizedInstance {
    pub manifest: NormalizedInstanceManifest,
    pub units: Vec<NormalizedUnitObject>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawRef {
    pub path: String,
    pub raw_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreviousNormalization {
    pub raw: RawRef,
    pub normalized_units: Vec<NormalizedUnitObject>,
    pub tool_profile_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IncrementalHints {
    pub changed_unit_keys: Vec<String>,
    pub added_unit_keys: Vec<String>,
    pub removed_unit_keys: Vec<String>,
    pub page_fingerprints: BTreeMap<String, UnitFingerprint>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NormalizationRun {
    pub run_id: String,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub mode: MarkdownizeMode,
    pub status: NormalizationRunStatus,
    pub changed_unit_keys: Vec<String>,
    pub output_ref: String,
    pub fallback_reason: Option<String>,
    pub created_at: String,
    pub finished_at: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NormalizationRunStatus {
    Pending,
    Running,
    Done,
    Partial,
    Failed,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarkdownizeStageRequest {
    pub mode: MarkdownizeMode,
    pub new_raw: RawRef,
    pub previous: Option<PreviousNormalization>,
    pub hints: Option<IncrementalHints>,
    pub tool_profile_hash: String,
    pub spec_version: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MarkdownizeStageOutput {
    pub run: NormalizationRun,
    pub manifest: NormalizedInstanceManifest,
    pub updated_units: Vec<NormalizedUnitObject>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct IncrementalModeInput {
    pub has_previous_done_run: bool,
    pub raw_hash_only_changed: bool,
    pub adapter_capabilities: Vec<String>,
    pub change_rate: f64,
    pub threshold: f64,
    pub consecutive_incremental_count: u32,
    pub max_consecutive_incremental: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IncrementalModeDecision {
    pub mode: MarkdownizeMode,
    pub reason: Option<String>,
}

pub fn markdownize_units(request: MarkdownizeStageRequest) -> Result<MarkdownizeStageOutput> {
    let generated_at = now_utc_seconds();
    let unit_key = "doc:1".to_owned();
    let prepared_hash = request.new_raw.raw_hash.clone();
    let unit_ref = prepared_unit_ref(&unit_key);
    let unit = NormalizedUnitObject {
        unit_key: unit_key.clone(),
        unit_type: UnitType::File,
        raw_hash: request.new_raw.raw_hash.clone(),
        prepared_hash: prepared_hash.clone(),
        tool_profile_hash: request.tool_profile_hash.clone(),
        gen: 0,
        mode: request.mode,
        markdown: format!(
            "<!-- KCS deterministic baseline {} {} -->\n",
            unit_key, request.new_raw.raw_hash
        ),
        reused_from: None,
        generated_at: generated_at.clone(),
    };
    let manifest = NormalizedInstanceManifest {
        raw_hash: request.new_raw.raw_hash.clone(),
        tool_profile_hash: request.tool_profile_hash.clone(),
        gen: 0,
        parent_gen: None,
        run_id: format!("run_{}", new_ulid(Path::new("."))),
        units: vec![NormalizedUnitManifestEntry {
            order: 0,
            unit_key,
            unit_ref,
            unit_type: UnitType::File,
            status: UnitStatus::Done,
            prepared_hash,
            error_kind: None,
        }],
        generated_at: generated_at.clone(),
    };
    Ok(MarkdownizeStageOutput {
        run: NormalizationRun {
            run_id: manifest.run_id.clone(),
            raw_hash: request.new_raw.raw_hash,
            tool_profile_hash: request.tool_profile_hash,
            gen: 0,
            mode: request.mode,
            status: NormalizationRunStatus::Done,
            changed_unit_keys: vec!["doc:1".to_owned()],
            output_ref: "objects/normalized_units".to_owned(),
            fallback_reason: None,
            created_at: generated_at.clone(),
            finished_at: Some(generated_at),
        },
        manifest,
        updated_units: vec![unit],
    })
}

#[must_use]
pub fn choose_markdownize_mode(input: &IncrementalModeInput) -> IncrementalModeDecision {
    let full = |reason: &str| IncrementalModeDecision {
        mode: MarkdownizeMode::Full,
        reason: Some(reason.to_owned()),
    };
    if !input.has_previous_done_run {
        return full("no_previous_done_run");
    }
    if !input.raw_hash_only_changed {
        return full("identity_changed");
    }
    if !input
        .adapter_capabilities
        .iter()
        .any(|capability| capability == "incremental_update")
    {
        return full("adapter_lacks_incremental_update");
    }
    if input.change_rate >= input.threshold {
        return full("change_rate_threshold");
    }
    if input.consecutive_incremental_count >= input.max_consecutive_incremental {
        return full("max_consecutive_incremental");
    }
    IncrementalModeDecision {
        mode: MarkdownizeMode::Incremental,
        reason: None,
    }
}

pub fn validate_markdownize_response(
    response: &adapter_types::MarkdownizeResponse,
    hints: &IncrementalHints,
    prepared_units: &[PreparedUnit],
) -> Result<()> {
    if response.fallback_to_full {
        return Err(contract_violation("adapter_requested_full_fallback"));
    }
    if response.mode_used == adapter_types::MarkdownizeMode::Full {
        return validate_full_response(response, prepared_units);
    }

    let new_keys = prepared_units
        .iter()
        .map(|unit| unit.unit_key.clone())
        .collect::<BTreeSet<_>>();
    let updated_keys = unit_keys(&response.updated_units);
    let added_keys = unit_keys(&response.added_units);
    let unchanged_keys = response
        .unchanged_unit_keys
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();

    let union = updated_keys
        .union(&added_keys)
        .cloned()
        .collect::<BTreeSet<_>>()
        .union(&unchanged_keys)
        .cloned()
        .collect::<BTreeSet<_>>();
    if union != new_keys
        || !updated_keys.is_disjoint(&added_keys)
        || !updated_keys.is_disjoint(&unchanged_keys)
        || !added_keys.is_disjoint(&unchanged_keys)
    {
        return Err(contract_violation(
            "incremental coverage/exclusivity violation",
        ));
    }

    if set_from(&response.removed_unit_keys) != set_from(&hints.removed_unit_keys) {
        return Err(contract_violation("removed_unit_keys do not match hints"));
    }
    if !updated_keys.is_subset(&set_from(&hints.changed_unit_keys)) {
        return Err(contract_violation(
            "updated unit is outside changed_unit_keys",
        ));
    }
    if added_keys != set_from(&hints.added_unit_keys) {
        return Err(contract_violation("added units do not match hints"));
    }
    validate_unit_shapes(&response.updated_units, prepared_units)?;
    validate_unit_shapes(&response.added_units, prepared_units)
}

#[must_use]
pub fn normalized_instance_dir(
    kcs_dir: impl AsRef<Path>,
    raw_hash: &str,
    tool_profile_hash: &str,
    gen: u64,
) -> PathBuf {
    kcs_dir.as_ref().join(normalized_instance_relative_path(
        raw_hash,
        tool_profile_hash,
        gen,
    ))
}

fn normalized_instance_relative_path(raw_hash: &str, tool_profile_hash: &str, gen: u64) -> PathBuf {
    let digest = raw_hash.strip_prefix("sha256:").unwrap_or(raw_hash);
    // Q6 (defense in depth): never slice-panic on a malformed short digest. The
    // authoritative validation lives at `TaskStore::all` (`is_hash`); this keeps
    // any other caller from aborting with exit 101 on a stray hash.
    let fanout_a = digest.get(0..2).unwrap_or(digest);
    let fanout_b = digest.get(2..4).unwrap_or("");
    Path::new("objects/normalized_units")
        .join(fanout_a)
        .join(fanout_b)
        .join(format!("{raw_hash}.{tool_profile_hash}.g{gen}"))
}

#[must_use]
pub fn normalized_view_path(
    kcs_dir: impl AsRef<Path>,
    raw_hash: &str,
    tool_profile_hash: &str,
    gen: u64,
) -> PathBuf {
    kcs_dir.as_ref().join(normalized_view_relative_path(
        raw_hash,
        tool_profile_hash,
        gen,
    ))
}

fn normalized_view_relative_path(raw_hash: &str, tool_profile_hash: &str, gen: u64) -> PathBuf {
    let digest = raw_hash.strip_prefix("sha256:").unwrap_or(raw_hash);
    Path::new("objects/normalized")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(format!("{raw_hash}.{tool_profile_hash}.g{gen}.md"))
}

/// Load a normalized instance through one mandatory provenance boundary. The
/// requested tuple selects the directory, and every manifest/unit field is rebound
/// to that tuple before any markdown leaves this function.
pub fn load_validated_normalized_instance(
    kcs_dir: impl AsRef<Path>,
    raw_hash: &str,
    tool_profile_hash: &str,
    gen: u64,
) -> Result<ValidatedNormalizedInstance> {
    if !kcs_core::cas::is_hash(raw_hash) || !kcs_core::cas::is_hash(tool_profile_hash) {
        return Err(PipelineError::corrupt(
            kcs_dir.as_ref().display().to_string(),
            "requested normalized instance has an invalid hash identity".to_owned(),
        ));
    }
    let identity = NormalizedInstanceIdentity {
        raw_hash: raw_hash.to_owned(),
        tool_profile_hash: tool_profile_hash.to_owned(),
        gen,
    };
    let relative_dir = normalized_instance_relative_path(raw_hash, tool_profile_hash, gen);
    let dir = kcs_dir.as_ref().join(&relative_dir);
    let canonical_dir =
        resolve_existing_store_path(kcs_dir.as_ref(), &relative_dir, StorePathKind::Directory)?
            .ok_or_else(|| missing_normalized_object(&dir, "normalized instance does not exist"))?;

    let manifest_path = dir.join("manifest.json");
    let manifest_bytes = read_contained_normalized_file(
        kcs_dir.as_ref(),
        &canonical_dir,
        &manifest_path,
        MAX_NORMALIZED_MANIFEST_BYTES,
    )?;
    let manifest: NormalizedInstanceManifest =
        serde_json::from_slice(&manifest_bytes).map_err(|err| {
            PipelineError::corrupt(manifest_path.display().to_string(), err.to_string())
        })?;
    validate_manifest_identity(&manifest_path, &identity, &manifest)?;

    let mut units = Vec::new();
    let mut total_bytes = manifest_bytes.len() as u64;
    for entry in &manifest.units {
        if entry.status != UnitStatus::Done {
            continue;
        }
        let expected_ref = prepared_unit_ref(&entry.unit_key);
        let unit_path = dir.join(format!("{expected_ref}.json"));
        let bytes = read_contained_normalized_file(
            kcs_dir.as_ref(),
            &canonical_dir,
            &unit_path,
            MAX_NORMALIZED_UNIT_BYTES,
        )?;
        total_bytes = total_bytes.saturating_add(bytes.len() as u64);
        if total_bytes > MAX_NORMALIZED_INSTANCE_BYTES {
            return Err(PipelineError::corrupt(
                dir.display().to_string(),
                format!("normalized instance exceeds {MAX_NORMALIZED_INSTANCE_BYTES} byte limit"),
            ));
        }
        let unit: NormalizedUnitObject = serde_json::from_slice(&bytes).map_err(|err| {
            PipelineError::corrupt(unit_path.display().to_string(), err.to_string())
        })?;
        units.push(unit);
    }
    validate_normalized_instance(&manifest_path, &identity, &manifest, &units)?;
    Ok(ValidatedNormalizedInstance { manifest, units })
}

/// Validate already-deserialized normalized state. This is also used by the
/// writer so invalid internal state cannot be persisted under a trusted tuple.
pub fn validate_normalized_instance(
    source_path: impl AsRef<Path>,
    identity: &NormalizedInstanceIdentity,
    manifest: &NormalizedInstanceManifest,
    units: &[NormalizedUnitObject],
) -> Result<()> {
    let source_path = source_path.as_ref();
    validate_manifest_identity(source_path, identity, manifest)?;

    let mut manifest_keys = BTreeSet::new();
    let mut manifest_refs = BTreeSet::new();
    let done_by_key = manifest
        .units
        .iter()
        .filter(|entry| entry.status == UnitStatus::Done)
        .map(|entry| (entry.unit_key.as_str(), entry))
        .collect::<BTreeMap<_, _>>();
    for entry in &manifest.units {
        if entry.unit_key.is_empty()
            || !manifest_keys.insert(entry.unit_key.as_str())
            || !manifest_refs.insert(entry.unit_ref.as_str())
            || entry.unit_ref != prepared_unit_ref(&entry.unit_key)
        {
            return Err(normalized_corrupt(
                source_path,
                "manifest contains a duplicate or non-derived unit reference",
            ));
        }
        if !kcs_core::cas::is_hash(&entry.prepared_hash) {
            return Err(normalized_corrupt(
                source_path,
                "manifest entry prepared_hash is invalid",
            ));
        }
    }

    if units.len() != done_by_key.len() {
        return Err(normalized_corrupt(
            source_path,
            "done manifest entries and normalized unit objects are not one-to-one",
        ));
    }
    let mut seen_units = BTreeSet::new();
    for unit in units {
        let Some(entry) = done_by_key.get(unit.unit_key.as_str()) else {
            return Err(normalized_corrupt(
                source_path,
                "normalized unit does not have a matching done manifest entry",
            ));
        };
        if !seen_units.insert(unit.unit_key.as_str())
            || unit.raw_hash != identity.raw_hash
            || unit.tool_profile_hash != identity.tool_profile_hash
            || unit.gen != identity.gen
            || unit.unit_key != entry.unit_key
            || unit.unit_type != entry.unit_type
            || unit.prepared_hash != entry.prepared_hash
            || unit.markdown.is_empty()
        {
            return Err(normalized_corrupt(
                source_path,
                "normalized unit identity does not match the requested manifest tuple",
            ));
        }
    }
    Ok(())
}

fn validate_manifest_identity(
    source_path: &Path,
    identity: &NormalizedInstanceIdentity,
    manifest: &NormalizedInstanceManifest,
) -> Result<()> {
    if !kcs_core::cas::is_hash(&identity.raw_hash)
        || !kcs_core::cas::is_hash(&identity.tool_profile_hash)
        || manifest.raw_hash != identity.raw_hash
        || manifest.tool_profile_hash != identity.tool_profile_hash
        || manifest.gen != identity.gen
    {
        return Err(normalized_corrupt(
            source_path,
            "normalized manifest identity does not match the requested instance",
        ));
    }
    Ok(())
}

fn read_contained_normalized_file(
    kcs_dir: &Path,
    canonical_dir: &Path,
    path: &Path,
    max_bytes: u64,
) -> Result<Vec<u8>> {
    let relative = path
        .strip_prefix(kcs_dir)
        .map_err(|_| normalized_corrupt(path, "normalized object is outside the KCS directory"))?;
    let canonical = resolve_existing_store_path(kcs_dir, relative, StorePathKind::RegularFile)?
        .ok_or_else(|| missing_normalized_object(path, "normalized object does not exist"))?;
    if canonical.parent() != Some(canonical_dir) {
        return Err(normalized_corrupt(
            path,
            "normalized object is not a direct regular-file child of its instance",
        ));
    }
    let file = fs::File::open(&canonical).pipeline_io(&canonical)?;
    let metadata = file.metadata().pipeline_io(&canonical)?;
    if metadata.len() > max_bytes {
        return Err(normalized_corrupt(
            path,
            "normalized object exceeds its byte limit",
        ));
    }
    let mut bytes = Vec::with_capacity(usize::try_from(metadata.len()).unwrap_or(0));
    let mut limited = file.take(max_bytes.saturating_add(1));
    limited.read_to_end(&mut bytes).pipeline_io(&canonical)?;
    if bytes.len() as u64 > max_bytes {
        return Err(normalized_corrupt(
            path,
            "normalized object grew beyond its byte limit",
        ));
    }
    Ok(bytes)
}

fn normalized_corrupt(path: &Path, message: impl Into<String>) -> PipelineError {
    PipelineError::corrupt(path.display().to_string(), message)
}

fn missing_normalized_object(path: &Path, message: impl Into<String>) -> PipelineError {
    PipelineError::Io {
        path: path.display().to_string(),
        message: message.into(),
    }
}

fn checked_manifest_size(path: &Path, bytes: u64, limits: NormalizedSizeLimits) -> Result<u64> {
    if bytes > limits.manifest_bytes {
        return Err(normalized_corrupt(
            path,
            format!(
                "normalized manifest exceeds {} byte limit",
                limits.manifest_bytes
            ),
        ));
    }
    if bytes > limits.instance_bytes {
        return Err(normalized_corrupt(
            path,
            format!(
                "normalized instance exceeds {} byte limit",
                limits.instance_bytes
            ),
        ));
    }
    Ok(bytes)
}

fn checked_unit_size(
    instance_dir: &Path,
    unit_path: &Path,
    current_total: u64,
    bytes: u64,
    limits: NormalizedSizeLimits,
) -> Result<u64> {
    if bytes > limits.unit_bytes {
        return Err(normalized_corrupt(
            unit_path,
            format!("normalized object exceeds {} byte limit", limits.unit_bytes),
        ));
    }
    let total = current_total.saturating_add(bytes);
    if total > limits.instance_bytes {
        return Err(normalized_corrupt(
            instance_dir,
            format!(
                "normalized instance exceeds {} byte limit",
                limits.instance_bytes
            ),
        ));
    }
    Ok(total)
}

pub fn persist_normalized_instance(
    kcs_dir: impl AsRef<Path>,
    manifest: &NormalizedInstanceManifest,
    units: &[NormalizedUnitObject],
) -> Result<()> {
    let identity = NormalizedInstanceIdentity {
        raw_hash: manifest.raw_hash.clone(),
        tool_profile_hash: manifest.tool_profile_hash.clone(),
        gen: manifest.gen,
    };
    validate_normalized_instance(
        kcs_dir.as_ref().join("manifest.json"),
        &identity,
        manifest,
        units,
    )?;
    let dir = normalized_instance_dir(
        &kcs_dir,
        &manifest.raw_hash,
        &manifest.tool_profile_hash,
        manifest.gen,
    );
    let instance_relative = normalized_instance_relative_path(
        &manifest.raw_hash,
        &manifest.tool_profile_hash,
        manifest.gen,
    );
    let instance_parent_relative = instance_relative
        .parent()
        .ok_or_else(|| PipelineError::Io {
            path: dir.display().to_string(),
            message: "normalized instance path has no parent".to_owned(),
        })?;
    let view_relative = normalized_view_relative_path(
        &manifest.raw_hash,
        &manifest.tool_profile_hash,
        manifest.gen,
    );
    let view_path = kcs_dir.as_ref().join(&view_relative);
    let view_parent_relative = view_relative.parent().ok_or_else(|| PipelineError::Io {
        path: view_path.display().to_string(),
        message: "normalized view path has no parent".to_owned(),
    })?;
    let manifest_path = dir.join("manifest.json");
    let manifest_bytes = serde_json::to_vec_pretty(manifest)
        .map_err(|err| PipelineError::Schema(err.to_string()))?;
    let mut total_bytes = checked_manifest_size(
        &manifest_path,
        manifest_bytes.len() as u64,
        NORMALIZED_SIZE_LIMITS,
    )?;
    let mut serialized_units = Vec::with_capacity(units.len());
    for unit in units {
        let name = format!("{}.json", prepared_unit_ref(&unit.unit_key));
        let unit_path = dir.join(&name);
        let bytes = serde_json::to_vec_pretty(unit)
            .map_err(|err| PipelineError::Schema(err.to_string()))?;
        total_bytes = checked_unit_size(
            &dir,
            &unit_path,
            total_bytes,
            bytes.len() as u64,
            NORMALIZED_SIZE_LIMITS,
        )?;
        serialized_units.push((name, bytes));
    }

    // Preflight both stores before creating either one. A poisoned view root
    // must not allow the instance writer to make partial progress, or vice versa.
    resolve_existing_store_path(
        kcs_dir.as_ref(),
        instance_parent_relative,
        StorePathKind::Directory,
    )?;
    resolve_existing_store_path(
        kcs_dir.as_ref(),
        view_parent_relative,
        StorePathKind::Directory,
    )?;
    resolve_existing_store_path(
        kcs_dir.as_ref(),
        &instance_relative,
        StorePathKind::Directory,
    )?;
    resolve_existing_store_path(kcs_dir.as_ref(), &view_relative, StorePathKind::RegularFile)?;

    ensure_store_directory_path(kcs_dir.as_ref(), instance_parent_relative)?;
    ensure_store_directory_path(kcs_dir.as_ref(), view_parent_relative)?;
    let tmp_dir = atomic_temp_path(&dir);
    let tmp_relative = tmp_dir.strip_prefix(kcs_dir.as_ref()).map_err(|_| {
        normalized_corrupt(
            &tmp_dir,
            "normalized temp path is outside the KCS directory",
        )
    })?;
    let result = (|| -> Result<()> {
        fs::create_dir(&tmp_dir).pipeline_io(&tmp_dir)?;
        write_synced_file(&tmp_dir.join("manifest.json"), &manifest_bytes)?;
        for (name, bytes) in &serialized_units {
            write_synced_file(&tmp_dir.join(name), bytes)?;
        }
        Ok(())
    })();
    if let Err(err) = result {
        let _ = fs::remove_dir_all(&tmp_dir);
        return Err(err);
    }
    let publish_result = (|| -> Result<()> {
        ensure_store_directory_path(kcs_dir.as_ref(), instance_parent_relative)?;
        resolve_existing_store_path(
            kcs_dir.as_ref(),
            view_parent_relative,
            StorePathKind::Directory,
        )?
        .ok_or_else(|| normalized_corrupt(&view_path, "normalized view parent disappeared"))?;
        resolve_existing_store_path(kcs_dir.as_ref(), &view_relative, StorePathKind::RegularFile)?;
        resolve_existing_store_path(kcs_dir.as_ref(), tmp_relative, StorePathKind::Directory)?
            .ok_or_else(|| normalized_corrupt(&tmp_dir, "normalized temp directory disappeared"))?;
        if let Some(existing) = resolve_existing_store_path(
            kcs_dir.as_ref(),
            &instance_relative,
            StorePathKind::Directory,
        )? {
            fs::remove_dir_all(&existing).pipeline_io(&existing)?;
        }
        ensure_store_directory_path(kcs_dir.as_ref(), instance_parent_relative)?;
        fs::rename(&tmp_dir, &dir).pipeline_io(&dir)
    })();
    if let Err(err) = publish_result {
        let _ = fs::remove_dir_all(&tmp_dir);
        return Err(err);
    }
    let view = build_normalized_view(manifest, units);
    atomic_overwrite_store_file(kcs_dir.as_ref(), &view_relative, view.as_bytes())
}

fn atomic_temp_path(path: &Path) -> PathBuf {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("normalized");
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    let seq = ATOMIC_WRITE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    parent.join(format!(".{name}.tmp-{}-{now}-{seq}", std::process::id()))
}

fn write_synced_file(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .pipeline_io(path)?;
    file.write_all(bytes).pipeline_io(path)?;
    file.sync_all().pipeline_io(path)
}

fn atomic_overwrite_store_file(kcs_dir: &Path, relative: &Path, bytes: &[u8]) -> Result<()> {
    let path = kcs_dir.join(relative);
    let parent_relative = relative
        .parent()
        .ok_or_else(|| normalized_corrupt(&path, "normalized view path has no parent"))?;
    resolve_existing_store_path(kcs_dir, parent_relative, StorePathKind::Directory)?
        .ok_or_else(|| normalized_corrupt(&path, "normalized view parent does not exist"))?;
    resolve_existing_store_path(kcs_dir, relative, StorePathKind::RegularFile)?;

    let tmp = atomic_temp_path(&path);
    let tmp_relative = tmp.strip_prefix(kcs_dir).map_err(|_| {
        normalized_corrupt(
            &tmp,
            "normalized view temp path is outside the KCS directory",
        )
    })?;
    let result = write_synced_file(&tmp, bytes).and_then(|_| {
        resolve_existing_store_path(kcs_dir, parent_relative, StorePathKind::Directory)?
            .ok_or_else(|| normalized_corrupt(&path, "normalized view parent disappeared"))?;
        resolve_existing_store_path(kcs_dir, tmp_relative, StorePathKind::RegularFile)?
            .ok_or_else(|| normalized_corrupt(&tmp, "normalized view temp file disappeared"))?;
        resolve_existing_store_path(kcs_dir, relative, StorePathKind::RegularFile)?;
        fs::rename(&tmp, &path).pipeline_io(&path)
    });
    if let Err(err) = result {
        let _ = fs::remove_file(&tmp);
        return Err(err);
    }
    Ok(())
}

#[must_use]
pub fn build_normalized_view(
    manifest: &NormalizedInstanceManifest,
    units: &[NormalizedUnitObject],
) -> String {
    let by_key = units
        .iter()
        .map(|unit| (unit.unit_key.as_str(), unit))
        .collect::<BTreeMap<_, _>>();
    let mut parts = Vec::new();
    for entry in &manifest.units {
        match entry.status {
            UnitStatus::Done => {
                let markdown = by_key
                    .get(entry.unit_key.as_str())
                    .map(|unit| unit.markdown.trim_end_matches('\n').to_owned())
                    .unwrap_or_default();
                parts.push(markdown);
            }
            UnitStatus::Failed => parts.push(format!(
                "<!-- KCS-MISSING-UNIT {} {} -->",
                entry.unit_key,
                entry.error_kind.as_deref().unwrap_or("unknown")
            )),
        }
    }
    format!(
        "<!-- KCS-NORMALIZED-VIEW raw_hash={} tool_profile_hash={} gen={} -->\n{}\n",
        manifest.raw_hash,
        manifest.tool_profile_hash,
        manifest.gen,
        parts.join("\n\n")
    )
}

#[must_use]
pub fn normalized_identity(raw_hash: &str, tool_profile_hash: &str) -> String {
    hash_bytes(format!("{raw_hash}\0{tool_profile_hash}").as_bytes())
}

fn validate_full_response(
    response: &adapter_types::MarkdownizeResponse,
    prepared_units: &[PreparedUnit],
) -> Result<()> {
    let expected = prepared_units
        .iter()
        .map(|unit| unit.unit_key.clone())
        .collect::<BTreeSet<_>>();
    let actual = unit_keys(&response.updated_units);
    if actual != expected {
        return Err(contract_violation(
            "full response does not cover all prepared units",
        ));
    }
    validate_unit_shapes(&response.updated_units, prepared_units)
}

fn validate_unit_shapes(
    units: &[adapter_types::MarkdownUnit],
    prepared_units: &[PreparedUnit],
) -> Result<()> {
    let prepared = prepared_units
        .iter()
        .map(|unit| (unit.unit_key.as_str(), unit.unit_type))
        .collect::<BTreeMap<_, _>>();
    for unit in units {
        if unit.markdown.is_empty() {
            return Err(contract_violation("markdown must be non-empty"));
        }
        let Some(expected_type) = prepared.get(unit.unit_key.as_str()) else {
            return Err(contract_violation("unit_key is not a prepared unit"));
        };
        if adapter_unit_type(unit.unit_type) != *expected_type {
            return Err(contract_violation("unit_type does not match prepared unit"));
        }
    }
    Ok(())
}

fn adapter_unit_type(unit_type: adapter_types::UnitKind) -> UnitType {
    match unit_type {
        adapter_types::UnitKind::Page => UnitType::Page,
        adapter_types::UnitKind::Slide => UnitType::Slide,
        adapter_types::UnitKind::HeadingSection => UnitType::HeadingSection,
        adapter_types::UnitKind::Sheet => UnitType::Sheet,
        adapter_types::UnitKind::Image => UnitType::Image,
        adapter_types::UnitKind::File => UnitType::File,
        adapter_types::UnitKind::Symbol => UnitType::Symbol,
    }
}

fn unit_keys(units: &[adapter_types::MarkdownUnit]) -> BTreeSet<String> {
    units.iter().map(|unit| unit.unit_key.clone()).collect()
}

fn set_from(values: &[String]) -> BTreeSet<String> {
    values.iter().cloned().collect()
}

fn contract_violation(message: &str) -> PipelineError {
    PipelineError::contract("KCS-E-ADAPTER-CONTRACT-001", message)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn normalized_fixture() -> (
        NormalizedInstanceIdentity,
        NormalizedInstanceManifest,
        Vec<NormalizedUnitObject>,
    ) {
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_profile_hash = format!("sha256:{}", "b".repeat(64));
        let prepared_hash = format!("sha256:{}", "c".repeat(64));
        let unit_key = "page:1".to_owned();
        let identity = NormalizedInstanceIdentity {
            raw_hash: raw_hash.clone(),
            tool_profile_hash: tool_profile_hash.clone(),
            gen: 7,
        };
        let manifest = NormalizedInstanceManifest {
            raw_hash: raw_hash.clone(),
            tool_profile_hash: tool_profile_hash.clone(),
            gen: 7,
            parent_gen: Some(6),
            run_id: "run_test".to_owned(),
            units: vec![NormalizedUnitManifestEntry {
                order: 0,
                unit_key: unit_key.clone(),
                unit_ref: prepared_unit_ref(&unit_key),
                unit_type: UnitType::Page,
                status: UnitStatus::Done,
                prepared_hash: prepared_hash.clone(),
                error_kind: None,
            }],
            generated_at: "2026-07-12T00:00:00Z".to_owned(),
        };
        let units = vec![NormalizedUnitObject {
            unit_key,
            unit_type: UnitType::Page,
            raw_hash,
            prepared_hash,
            tool_profile_hash,
            gen: 7,
            mode: MarkdownizeMode::Full,
            markdown: "trusted markdown".to_owned(),
            reused_from: None,
            generated_at: "2026-07-12T00:00:00Z".to_owned(),
        }];
        (identity, manifest, units)
    }

    #[test]
    fn placeholder_unit_ref_serializes_gen() {
        let unit_ref = UnitRef {
            raw_hash: "sha256:raw".to_owned(),
            tool_profile_hash: "sha256:tool".to_owned(),
            gen: 2,
            unit_key: "page:1".to_owned(),
            unit_ref: "3f2a9c0d1b4e5f60".to_owned(),
        };

        let value = serde_json::to_value(unit_ref).expect("serialize unit ref");
        assert_eq!(value["gen"], 2);
    }

    #[test]
    fn normalized_layout_matches_step2a_vector() {
        let raw = "sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59";
        let tool = "sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed";
        let dir = normalized_instance_dir(".kcs", raw, tool, 0);
        assert_eq!(
            dir,
            PathBuf::from(".kcs/objects/normalized_units/bb/e1/sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59.sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed.g0")
        );
        assert_eq!(
            normalized_view_path(".kcs", raw, tool, 0),
            PathBuf::from(".kcs/objects/normalized/bb/e1/sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59.sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed.g0.md")
        );
    }

    #[test]
    fn q6_normalized_instance_dir_does_not_panic_on_short_digest() {
        // Defense in depth: a stray short hash must degrade to a deterministic path
        // instead of a `digest[0..2]` slice panic (exit 101). Authoritative
        // validation is at `TaskStore::all`; this only guarantees no panic here.
        let dir = normalized_instance_dir(".kcs", "sha256:ab", "sha256:tool", 0);
        assert!(dir.to_string_lossy().contains("objects/normalized_units"));
    }

    #[test]
    fn incremental_mode_requires_all_five_conditions() {
        let ok = IncrementalModeInput {
            has_previous_done_run: true,
            raw_hash_only_changed: true,
            adapter_capabilities: vec!["incremental_update".to_owned()],
            change_rate: 0.09,
            threshold: 0.30,
            consecutive_incremental_count: 4,
            max_consecutive_incremental: 5,
        };
        assert_eq!(
            choose_markdownize_mode(&ok).mode,
            MarkdownizeMode::Incremental
        );

        let mut no_previous = ok.clone();
        no_previous.has_previous_done_run = false;
        assert_eq!(
            choose_markdownize_mode(&no_previous).mode,
            MarkdownizeMode::Full
        );
        let mut tool_changed = ok.clone();
        tool_changed.raw_hash_only_changed = false;
        assert_eq!(
            choose_markdownize_mode(&tool_changed).mode,
            MarkdownizeMode::Full
        );
        let mut no_capability = ok.clone();
        no_capability.adapter_capabilities.clear();
        assert_eq!(
            choose_markdownize_mode(&no_capability).mode,
            MarkdownizeMode::Full
        );
        let mut too_much_change = ok.clone();
        too_much_change.change_rate = 0.40;
        assert_eq!(
            choose_markdownize_mode(&too_much_change).mode,
            MarkdownizeMode::Full
        );
        let mut max_consecutive = ok;
        max_consecutive.consecutive_incremental_count = 5;
        assert_eq!(
            choose_markdownize_mode(&max_consecutive).mode,
            MarkdownizeMode::Full
        );
    }

    #[test]
    fn acceptance_validation_rejects_bad_incremental_shapes() {
        let prepared = vec![
            PreparedUnit {
                order: 0,
                unit_key: "page:1".to_owned(),
                unit_type: UnitType::Page,
                prepared_hash:
                    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                        .to_owned(),
                fingerprint: UnitFingerprint {
                    perceptual_hash: "p1".to_owned(),
                    text_hash: "t1".to_owned(),
                    visual_hash: "v1".to_owned(),
                },
                mime: None,
                page_number: Some(1),
            },
            PreparedUnit {
                order: 1,
                unit_key: "page:2".to_owned(),
                unit_type: UnitType::Page,
                prepared_hash:
                    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                        .to_owned(),
                fingerprint: UnitFingerprint {
                    perceptual_hash: "p2".to_owned(),
                    text_hash: "t2".to_owned(),
                    visual_hash: "v2".to_owned(),
                },
                mime: None,
                page_number: Some(2),
            },
        ];
        let hints = IncrementalHints {
            changed_unit_keys: vec!["page:1".to_owned()],
            added_unit_keys: Vec::new(),
            removed_unit_keys: Vec::new(),
            page_fingerprints: BTreeMap::new(),
        };
        let good = adapter_types::MarkdownizeResponse {
            mode_used: adapter_types::MarkdownizeMode::Incremental,
            updated_units: vec![adapter_types::MarkdownUnit {
                unit_key: "page:1".to_owned(),
                unit_type: adapter_types::UnitKind::Page,
                markdown: "updated".to_owned(),
                metadata: BTreeMap::new(),
            }],
            unchanged_unit_keys: vec!["page:2".to_owned()],
            added_units: Vec::new(),
            removed_unit_keys: Vec::new(),
            evidence_pointers: Vec::new(),
            fallback_to_full: false,
            reason: None,
        };
        validate_markdownize_response(&good, &hints, &prepared).unwrap();

        let mut bad = good;
        bad.updated_units[0].unit_key = "page:2".to_owned();
        assert!(validate_markdownize_response(&bad, &hints, &prepared).is_err());
    }

    #[test]
    fn cand_049_manifest_deserialization_rejects_path_like_or_mismatched_unit_refs() {
        let unit_key = "page:1";
        let canonical = prepared_unit_ref(unit_key);
        let entry = |unit_ref: &str| {
            serde_json::json!({
                "order": 0,
                "unit_key": unit_key,
                "unit_ref": unit_ref,
                "unit_type": "page",
                "status": "done",
                "prepared_hash": format!("sha256:{}", "c".repeat(64)),
                "error_kind": null
            })
        };
        let parsed: NormalizedUnitManifestEntry =
            serde_json::from_value(entry(&canonical)).unwrap();
        assert_eq!(parsed.unit_ref, canonical);

        for bad in [
            "/tmp/foreign-unit".to_owned(),
            "../../foreign-unit".to_owned(),
            canonical.to_ascii_uppercase(),
            "0000000000000000".to_owned(),
            format!("{canonical}/child"),
        ] {
            assert!(
                serde_json::from_value::<NormalizedUnitManifestEntry>(entry(&bad)).is_err(),
                "should reject {bad:?}"
            );
        }
    }

    #[test]
    fn cand_061_provenance_validator_rebinds_complete_tuple() {
        let (identity, manifest, units) = normalized_fixture();
        validate_normalized_instance("manifest.json", &identity, &manifest, &units).unwrap();

        let mut bad_manifest = manifest.clone();
        bad_manifest.raw_hash = format!("sha256:{}", "d".repeat(64));
        assert!(
            validate_normalized_instance("manifest.json", &identity, &bad_manifest, &units)
                .is_err()
        );
        bad_manifest = manifest.clone();
        bad_manifest.tool_profile_hash = format!("sha256:{}", "d".repeat(64));
        assert!(
            validate_normalized_instance("manifest.json", &identity, &bad_manifest, &units)
                .is_err()
        );
        bad_manifest = manifest.clone();
        bad_manifest.gen = 8;
        assert!(
            validate_normalized_instance("manifest.json", &identity, &bad_manifest, &units)
                .is_err()
        );

        let mut bad_unit = units.clone();
        bad_unit[0].raw_hash = format!("sha256:{}", "d".repeat(64));
        assert!(
            validate_normalized_instance("manifest.json", &identity, &manifest, &bad_unit).is_err()
        );
        let mut bad_unit = units.clone();
        bad_unit[0].tool_profile_hash = format!("sha256:{}", "d".repeat(64));
        assert!(
            validate_normalized_instance("manifest.json", &identity, &manifest, &bad_unit).is_err()
        );
        let mut bad_unit = units.clone();
        bad_unit[0].gen = 8;
        assert!(
            validate_normalized_instance("manifest.json", &identity, &manifest, &bad_unit).is_err()
        );
        let mut bad_unit = units.clone();
        bad_unit[0].unit_key = "page:2".to_owned();
        assert!(
            validate_normalized_instance("manifest.json", &identity, &manifest, &bad_unit).is_err()
        );
        let mut bad_unit = units.clone();
        bad_unit[0].unit_type = UnitType::Image;
        assert!(
            validate_normalized_instance("manifest.json", &identity, &manifest, &bad_unit).is_err()
        );
        let mut bad_unit = units;
        bad_unit[0].prepared_hash = format!("sha256:{}", "d".repeat(64));
        assert!(
            validate_normalized_instance("manifest.json", &identity, &manifest, &bad_unit).is_err()
        );
    }

    #[test]
    fn cand_049_061_validated_loader_accepts_control_and_rejects_poisoned_unit() {
        let dir = tempfile::tempdir().unwrap();
        let (identity, manifest, units) = normalized_fixture();
        persist_normalized_instance(dir.path(), &manifest, &units).unwrap();
        let loaded = load_validated_normalized_instance(
            dir.path(),
            &identity.raw_hash,
            &identity.tool_profile_hash,
            identity.gen,
        )
        .unwrap();
        assert_eq!(loaded.manifest, manifest);
        assert_eq!(loaded.units, units);

        let instance_dir = normalized_instance_dir(
            dir.path(),
            &identity.raw_hash,
            &identity.tool_profile_hash,
            identity.gen,
        );
        let unit_path = instance_dir.join(format!(
            "{}.json",
            prepared_unit_ref(&manifest.units[0].unit_key)
        ));
        let mut poisoned = units[0].clone();
        poisoned.prepared_hash = format!("sha256:{}", "d".repeat(64));
        fs::write(&unit_path, serde_json::to_vec(&poisoned).unwrap()).unwrap();
        assert!(load_validated_normalized_instance(
            dir.path(),
            &identity.raw_hash,
            &identity.tool_profile_hash,
            identity.gen,
        )
        .is_err());
    }

    #[test]
    fn cand_061_writer_enforces_loader_size_boundaries_before_publish() {
        let dir = tempfile::tempdir().unwrap();
        let manifest_path = dir.path().join("manifest.json");
        let unit_path = dir.path().join("unit.json");
        let limits = NormalizedSizeLimits {
            manifest_bytes: 4,
            unit_bytes: 5,
            instance_bytes: 9,
        };

        let total = checked_manifest_size(&manifest_path, 4, limits).unwrap();
        assert_eq!(
            checked_unit_size(dir.path(), &unit_path, total, 5, limits).unwrap(),
            9
        );
        assert!(checked_manifest_size(&manifest_path, 5, limits).is_err());
        assert!(checked_unit_size(dir.path(), &unit_path, total, 6, limits).is_err());
        assert!(checked_unit_size(dir.path(), &unit_path, 9, 1, limits).is_err());

        let (identity, mut manifest, mut units) = normalized_fixture();
        let oversized_key = "x".repeat(MAX_NORMALIZED_MANIFEST_BYTES as usize);
        manifest.units[0].unit_key = oversized_key.clone();
        manifest.units[0].unit_ref = prepared_unit_ref(&oversized_key);
        units[0].unit_key = oversized_key;
        let expected_dir = normalized_instance_dir(
            dir.path(),
            &identity.raw_hash,
            &identity.tool_profile_hash,
            identity.gen,
        );
        let err = persist_normalized_instance(dir.path(), &manifest, &units).unwrap_err();
        assert!(err.to_string().contains("normalized manifest exceeds"));
        assert!(!expected_dir.exists());
    }

    #[cfg(unix)]
    #[test]
    fn cand_047_061_writer_rejects_both_symlinked_roots_before_mutation() {
        use std::os::unix::fs::symlink;

        let (_, manifest, units) = normalized_fixture();
        for (poisoned_root, untouched_root) in [
            ("normalized_units", "normalized"),
            ("normalized", "normalized_units"),
        ] {
            let kcs = tempfile::tempdir().unwrap();
            let outside = tempfile::tempdir().unwrap();
            fs::create_dir_all(kcs.path().join("objects")).unwrap();
            fs::write(outside.path().join("marker"), b"unchanged").unwrap();
            symlink(
                outside.path(),
                kcs.path().join("objects").join(poisoned_root),
            )
            .unwrap();

            assert!(persist_normalized_instance(kcs.path(), &manifest, &units).is_err());
            assert_eq!(
                fs::read(outside.path().join("marker")).unwrap(),
                b"unchanged"
            );
            assert_eq!(fs::read_dir(outside.path()).unwrap().count(), 1);
            assert!(
                fs::symlink_metadata(kcs.path().join("objects").join(poisoned_root))
                    .unwrap()
                    .file_type()
                    .is_symlink()
            );
            assert!(!kcs.path().join("objects").join(untouched_root).exists());
        }
    }

    #[cfg(unix)]
    #[test]
    fn cand_047_061_validated_loader_rejects_normalized_units_root_symlink() {
        use std::os::unix::fs::symlink;

        let trusted = tempfile::tempdir().unwrap();
        let poisoned = tempfile::tempdir().unwrap();
        let (identity, manifest, units) = normalized_fixture();
        persist_normalized_instance(trusted.path(), &manifest, &units).unwrap();
        assert!(load_validated_normalized_instance(
            trusted.path(),
            &identity.raw_hash,
            &identity.tool_profile_hash,
            identity.gen,
        )
        .is_ok());

        fs::create_dir_all(poisoned.path().join("objects")).unwrap();
        symlink(
            trusted.path().join("objects/normalized_units"),
            poisoned.path().join("objects/normalized_units"),
        )
        .unwrap();
        assert!(load_validated_normalized_instance(
            poisoned.path(),
            &identity.raw_hash,
            &identity.tool_profile_hash,
            identity.gen,
        )
        .is_err());
    }

    #[cfg(unix)]
    #[test]
    fn cand_049_validated_loader_rejects_symlinked_unit() {
        use std::os::unix::fs::symlink;

        let dir = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let (identity, manifest, units) = normalized_fixture();
        persist_normalized_instance(dir.path(), &manifest, &units).unwrap();
        let instance_dir = normalized_instance_dir(
            dir.path(),
            &identity.raw_hash,
            &identity.tool_profile_hash,
            identity.gen,
        );
        let name = format!("{}.json", prepared_unit_ref(&manifest.units[0].unit_key));
        let unit_path = instance_dir.join(&name);
        let outside_path = outside.path().join(&name);
        fs::write(&outside_path, serde_json::to_vec(&units[0]).unwrap()).unwrap();
        fs::remove_file(&unit_path).unwrap();
        symlink(&outside_path, &unit_path).unwrap();
        assert!(load_validated_normalized_instance(
            dir.path(),
            &identity.raw_hash,
            &identity.tool_profile_hash,
            identity.gen,
        )
        .is_err());
    }

    #[test]
    fn cand_061_missing_manifest_bound_unit_remains_an_io_error() {
        let dir = tempfile::tempdir().unwrap();
        let (identity, manifest, units) = normalized_fixture();
        persist_normalized_instance(dir.path(), &manifest, &units).unwrap();
        let instance_dir = normalized_instance_dir(
            dir.path(),
            &identity.raw_hash,
            &identity.tool_profile_hash,
            identity.gen,
        );
        let name = format!("{}.json", prepared_unit_ref(&manifest.units[0].unit_key));
        fs::remove_file(instance_dir.join(name)).unwrap();

        assert!(matches!(
            load_validated_normalized_instance(
                dir.path(),
                &identity.raw_hash,
                &identity.tool_profile_hash,
                identity.gen,
            ),
            Err(PipelineError::Io { .. })
        ));
    }
}
