//! Markdownize and normalized-unit contracts.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::prepare::{UnitFingerprint, UnitType};
use crate::Result;

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

pub fn markdownize_units(_request: MarkdownizeStageRequest) -> Result<MarkdownizeStageOutput> {
    todo!("implement Markdownize stage dispatch and validation in Step 2");
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
}
