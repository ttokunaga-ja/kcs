//! Cost guardrail and budget contracts.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::task::TaskType;
use crate::Result;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BudgetConfig {
    pub monthly_usd_cap: f64,
    pub warn_at_percent: u8,
    pub hard_stop: bool,
    pub per_adapter: BTreeMap<String, f64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BudgetCapKind {
    Device,
    Folder,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BudgetEstimate {
    pub scope_id: String,
    pub task_type: TaskType,
    pub estimated_usd: f64,
    pub adapter_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BudgetDecision {
    pub allowed: bool,
    pub cap_kind: Option<BudgetCapKind>,
    pub remaining_usd: f64,
    pub warning: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CostLedgerEntry {
    pub scope_id: String,
    pub task_id: String,
    pub adapter_id: String,
    pub task_type: TaskType,
    pub cost_usd: f64,
    pub recorded_at: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MonthlyCostLedgerEntry {
    pub month: String,
    pub scope_id: String,
    pub adapter_kind: String,
    pub usd: f64,
}

pub fn evaluate_budget(estimate: BudgetEstimate) -> Result<BudgetDecision> {
    Ok(BudgetDecision {
        allowed: true,
        cap_kind: None,
        remaining_usd: f64::INFINITY,
        warning: (estimate.estimated_usd > 0.0)
            .then(|| "budget caps are not configured".to_owned()),
    })
}

#[must_use]
pub fn evaluate_budget_with_caps(
    estimate: &BudgetEstimate,
    device_remaining_usd: f64,
    folder_remaining_usd: Option<f64>,
    override_budget: bool,
) -> BudgetDecision {
    if override_budget {
        return BudgetDecision {
            allowed: true,
            cap_kind: None,
            remaining_usd: f64::INFINITY,
            warning: Some("budget override active".to_owned()),
        };
    }
    let (effective_remaining, cap_kind) = match folder_remaining_usd {
        Some(folder) if folder <= device_remaining_usd => (folder, Some(BudgetCapKind::Folder)),
        _ => (device_remaining_usd, Some(BudgetCapKind::Device)),
    };
    let allowed = estimate.estimated_usd <= effective_remaining;
    BudgetDecision {
        allowed,
        cap_kind: if allowed { None } else { cap_kind },
        remaining_usd: effective_remaining,
        warning: (!allowed).then(|| "budget cap exceeded; new tasks are paused".to_owned()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_budget_cap_kind_serializes() {
        let value = serde_json::to_value(BudgetCapKind::Folder).expect("serialize cap kind");
        assert_eq!(value, "folder");
    }

    #[test]
    fn two_layer_budget_uses_min_remaining_and_override() {
        let estimate = BudgetEstimate {
            scope_id: "scope".to_owned(),
            task_type: TaskType::Markdownize,
            estimated_usd: 12.0,
            adapter_id: Some("mistral".to_owned()),
        };
        let denied = evaluate_budget_with_caps(&estimate, 50.0, Some(10.0), false);
        assert!(!denied.allowed);
        assert_eq!(denied.cap_kind, Some(BudgetCapKind::Folder));
        assert_eq!(denied.remaining_usd, 10.0);

        let allowed = evaluate_budget_with_caps(&estimate, 50.0, Some(10.0), true);
        assert!(allowed.allowed);
        assert_eq!(allowed.cap_kind, None);
    }
}
