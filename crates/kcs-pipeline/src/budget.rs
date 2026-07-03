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

pub fn evaluate_budget(_estimate: BudgetEstimate) -> Result<BudgetDecision> {
    todo!("implement device and folder budget guardrail in Step 2");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_budget_cap_kind_serializes() {
        let value = serde_json::to_value(BudgetCapKind::Folder).expect("serialize cap kind");
        assert_eq!(value, "folder");
    }
}
