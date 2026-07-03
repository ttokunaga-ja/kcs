//! Cost guardrail and budget contracts.

use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::task::TaskType;
use crate::{IoResultExt, PipelineError, Result};

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

#[derive(Debug, Clone)]
pub struct CostLedger {
    path: PathBuf,
}

impl CostLedger {
    #[must_use]
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }

    pub fn append_monthly(&self, entry: &MonthlyCostLedgerEntry) -> Result<()> {
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent).pipeline_io(parent)?;
        }
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .pipeline_io(&self.path)?;
        serde_json::to_writer(&mut file, entry)
            .map_err(|err| PipelineError::Schema(err.to_string()))?;
        file.write_all(b"\n").pipeline_io(&self.path)
    }

    pub fn monthly_total(&self, month: &str, scope_id: Option<&str>) -> Result<f64> {
        let file = match fs::File::open(&self.path) {
            Ok(file) => file,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(0.0),
            Err(err) => {
                return Err(PipelineError::Io {
                    path: self.path.display().to_string(),
                    message: err.to_string(),
                });
            }
        };
        let mut total = 0.0;
        for line in std::io::BufReader::new(file).lines() {
            let line = line.pipeline_io(&self.path)?;
            if line.trim().is_empty() {
                continue;
            }
            let entry: MonthlyCostLedgerEntry = serde_json::from_str(&line)
                .map_err(|err| PipelineError::Schema(err.to_string()))?;
            if entry.month == month && scope_id.map_or(true, |scope| scope == entry.scope_id) {
                total += entry.usd;
            }
        }
        Ok(total)
    }
}

pub fn evaluate_budget(estimate: BudgetEstimate) -> Result<BudgetDecision> {
    Ok(evaluate_budget_with_caps(
        &estimate,
        f64::INFINITY,
        None,
        false,
    ))
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

#[must_use]
pub fn utc_month(timestamp: &str) -> String {
    timestamp.get(0..7).unwrap_or("1970-01").to_owned()
}

#[must_use]
pub fn estimate_local_baseline_cost(size_bytes: u64) -> f64 {
    if size_bytes == 0 {
        0.0
    } else {
        size_bytes as f64 / 1_000_000.0 * 0.01
    }
}

pub fn read_budget_caps(
    device_config_path: impl AsRef<Path>,
    folder_config_path: impl AsRef<Path>,
) -> Result<(Option<f64>, Option<f64>)> {
    Ok((
        read_monthly_cap(device_config_path)?,
        read_monthly_cap(folder_config_path)?,
    ))
}

fn read_monthly_cap(config_path: impl AsRef<Path>) -> Result<Option<f64>> {
    let path = config_path.as_ref();
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(err) => {
            return Err(PipelineError::Io {
                path: path.display().to_string(),
                message: err.to_string(),
            });
        }
    };
    let value: toml::Value =
        toml::from_str(&text).map_err(|err| PipelineError::Schema(err.to_string()))?;
    let budget = value.get("budget");
    Ok(budget
        .and_then(|value| value.get("monthly_usd_cap"))
        .and_then(toml::Value::as_float)
        .or_else(|| {
            budget
                .and_then(|value| value.get("monthly_usd_cap"))
                .and_then(toml::Value::as_integer)
                .map(|value| value as f64)
        }))
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
