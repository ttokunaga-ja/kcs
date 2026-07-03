//! Scan preview contracts.

use serde::{Deserialize, Serialize};

use crate::Result;

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

pub fn build_scan_preview(_request: ScanPreviewRequest) -> Result<ScanPreview> {
    todo!("implement initial scan preview and .kcsignore handling in Step 2");
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScanPreviewRequest {
    pub scope_path: String,
    pub include_raw_hashes: bool,
    pub require_network_approval: bool,
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
}
