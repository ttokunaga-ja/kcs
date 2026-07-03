//! Markdownize and normalized-unit contracts.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use kcs_adapter::types as adapter_types;
use serde::{Deserialize, Serialize};

use crate::prepare::{
    hash_bytes, unit_ref as prepared_unit_ref, PreparedUnit, UnitFingerprint, UnitType,
};
use crate::{IoResultExt, PipelineError, Result};

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

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NormalizedUnitManifestEntry {
    pub order: u64,
    pub unit_key: String,
    pub unit_ref: String,
    pub unit_type: UnitType,
    pub status: UnitStatus,
    pub prepared_hash: String,
    pub error_kind: Option<String>,
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
    let generated_at = "2026-04-25T12:00:00Z".to_owned();
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
        run_id: "run_00000000000000000000000000".to_owned(),
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
    let digest = raw_hash.strip_prefix("sha256:").unwrap_or(raw_hash);
    kcs_dir
        .as_ref()
        .join("objects/normalized_units")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(format!("{raw_hash}.{tool_profile_hash}.g{gen}"))
}

#[must_use]
pub fn normalized_view_path(
    kcs_dir: impl AsRef<Path>,
    raw_hash: &str,
    tool_profile_hash: &str,
    gen: u64,
) -> PathBuf {
    let digest = raw_hash.strip_prefix("sha256:").unwrap_or(raw_hash);
    kcs_dir
        .as_ref()
        .join("objects/normalized")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(format!("{raw_hash}.{tool_profile_hash}.g{gen}.md"))
}

pub fn persist_normalized_instance(
    kcs_dir: impl AsRef<Path>,
    manifest: &NormalizedInstanceManifest,
    units: &[NormalizedUnitObject],
) -> Result<()> {
    let dir = normalized_instance_dir(
        &kcs_dir,
        &manifest.raw_hash,
        &manifest.tool_profile_hash,
        manifest.gen,
    );
    std::fs::create_dir_all(&dir).pipeline_io(&dir)?;
    let manifest_bytes = serde_json::to_vec_pretty(manifest)
        .map_err(|err| PipelineError::Schema(err.to_string()))?;
    std::fs::write(dir.join("manifest.json"), manifest_bytes).pipeline_io(&dir)?;
    for unit in units {
        let path = dir.join(format!("{}.json", prepared_unit_ref(&unit.unit_key)));
        let bytes = serde_json::to_vec_pretty(unit)
            .map_err(|err| PipelineError::Schema(err.to_string()))?;
        std::fs::write(&path, bytes).pipeline_io(&path)?;
    }
    let view_path = normalized_view_path(
        kcs_dir,
        &manifest.raw_hash,
        &manifest.tool_profile_hash,
        manifest.gen,
    );
    if let Some(parent) = view_path.parent() {
        std::fs::create_dir_all(parent).pipeline_io(parent)?;
    }
    std::fs::write(&view_path, build_normalized_view(manifest, units)).pipeline_io(&view_path)
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
}
