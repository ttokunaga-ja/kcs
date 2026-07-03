//! Prepare stage contracts.

use serde::{Deserialize, Serialize};

use crate::Result;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UnitType {
    Page,
    Slide,
    HeadingSection,
    Sheet,
    Image,
    File,
    Symbol,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UnitFingerprint {
    pub perceptual_hash: String,
    pub text_hash: String,
    pub visual_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreparedUnit {
    pub order: u64,
    pub unit_key: String,
    pub unit_type: UnitType,
    pub prepared_hash: String,
    pub fingerprint: UnitFingerprint,
    pub mime: Option<String>,
    pub page_number: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareStageRequest {
    pub raw_hash: String,
    pub media_type: String,
    pub input_path: String,
    pub tool_profile_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareStageOutput {
    pub prepared_object_hashes: Vec<String>,
    pub prepared_units: Vec<PreparedUnit>,
    pub image_object_hashes: Vec<String>,
}

pub fn prepare_units(_request: PrepareStageRequest) -> Result<PrepareStageOutput> {
    todo!("implement Prepare stage dispatch in Step 2");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_unit_type_uses_snake_case() {
        let value = serde_json::to_value(UnitType::HeadingSection).expect("serialize unit type");
        assert_eq!(value, "heading_section");
    }
}
