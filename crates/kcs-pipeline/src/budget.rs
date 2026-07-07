//! Cost guardrail and budget contracts.

use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::task::TaskType;
use crate::{IoResultExt, PipelineError, Result};

pub const DEFAULT_DEVICE_MONTHLY_USD_CAP: f64 = 50.0;

/// F5 defaults (docs/04 §5.4). When `[budget]` omits these keys the behavior is
/// the historical one: a hard pause at the cap, warning once spend reaches 80% of
/// a cap.
pub const DEFAULT_WARN_AT_PERCENT: u8 = 80;
pub const DEFAULT_HARD_STOP: bool = true;

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

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BudgetCaps {
    pub device_monthly_usd_cap: f64,
    pub folder_monthly_usd_cap: Option<f64>,
    pub device_per_adapter: BTreeMap<String, f64>,
    pub folder_per_adapter: BTreeMap<String, f64>,
    /// F5: `false` = soft-stop (record the charge and continue over cap); `true`
    /// (default) = hard pause at the cap. The folder `.kcs/config.toml` value
    /// overrides the device value when present.
    pub hard_stop: bool,
    /// F5: emit a non-blocking warning once device or folder spend reaches this
    /// percentage of its cap. Default 80. Folder overrides device when present.
    pub warn_at_percent: u8,
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
        // F3: a non-finite or negative charge would, once persisted, poison
        // `monthly_total_for_adapter` — a negative `usd` lowers `spent` (raising
        // `remaining = cap - spent`), and NaN/inf makes the whole sum non-finite,
        // both of which fail-open the budget cap. Reject it before it reaches the
        // durable device-global ledger (KCS-E-STORE-CORRUPT-001).
        if !entry.usd.is_finite() || entry.usd < 0.0 {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                format!(
                    "cost-ledger usd must be finite and non-negative: {}",
                    entry.usd
                ),
            ));
        }
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent).pipeline_io(parent)?;
        }
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .pipeline_io(&self.path)?;
        // M1(b): frame the record and emit it with one write_all. This is the
        // device-global cost-ledger.jsonl, appended cross-scope, so byte-wise
        // interleaving under O_APPEND is the acute case (M1(b)).
        let mut line =
            serde_json::to_string(entry).map_err(|err| PipelineError::Schema(err.to_string()))?;
        line.push('\n');
        file.write_all(line.as_bytes()).pipeline_io(&self.path)
    }

    pub fn monthly_total(&self, month: &str, scope_id: Option<&str>) -> Result<f64> {
        self.monthly_total_for_adapter(month, scope_id, None)
    }

    pub fn monthly_total_for_adapter(
        &self,
        month: &str,
        scope_id: Option<&str>,
        adapter_kind: Option<&str>,
    ) -> Result<f64> {
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
            // M1(c): a malformed ledger line is a corrupt store file, not a
            // schema/config error — classify it as KCS-E-STORE-CORRUPT-001.
            let entry: MonthlyCostLedgerEntry = serde_json::from_str(&line).map_err(|err| {
                PipelineError::corrupt(self.path.display().to_string(), err.to_string())
            })?;
            // F3: a JSON-valid but semantically-invalid charge (negative or
            // non-finite `usd`) would lower `spent` and fail-open the budget cap.
            // Treat it as a corrupt store record (KCS-E-STORE-CORRUPT-001), the
            // same class as a malformed line, rather than summing it into the
            // total. Validated for every row so a poisoned ledger can never
            // silently defeat the cap on any query.
            if !entry.usd.is_finite() || entry.usd < 0.0 {
                return Err(PipelineError::corrupt(
                    self.path.display().to_string(),
                    format!(
                        "cost-ledger usd must be finite and non-negative: {}",
                        entry.usd
                    ),
                ));
            }
            if entry.month == month
                && scope_id.map_or(true, |scope| scope == entry.scope_id)
                && adapter_kind.map_or(true, |kind| kind == entry.adapter_kind)
            {
                total += entry.usd;
            }
        }
        Ok(total)
    }

    /// R17-3: the device-global phantom-reservation RECLAIM ledger — a sibling of
    /// the charge ledger (`cost-ledger-reclaimed.jsonl`). When a stale online task
    /// whose F8 reservation was a NON-billable rejection (RateLimit / Quota, which
    /// R16-7 established never bills) is superseded at re-index, its exact reserved
    /// amount is appended here and SUBTRACTED from spend in
    /// `budget_remaining_for_adapter`. It is a SEPARATE, positive-only file on
    /// purpose: F3 forbids a negative compensating row in the charge ledger (a
    /// negative `usd` would fail-open the cap), so instead of poisoning the charge
    /// ledger we record the reclaim positively elsewhere and net it at read time.
    /// Reuses the same `MonthlyCostLedgerEntry` schema, so `append_monthly` /
    /// `monthly_total*` here inherit the identical F3 finite-and-non-negative guard.
    /// The cap-safe invariant (`effective_spent = charges - reclaimed >= real
    /// spend`) holds because only true phantoms are reclaimed, each by at most its
    /// own reservation.
    #[must_use]
    pub fn reclaim_ledger(&self) -> CostLedger {
        CostLedger::new(self.path.with_file_name("cost-ledger-reclaimed.jsonl"))
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
    let policy = read_budget_policy(device_config_path, folder_config_path)?;
    Ok((
        Some(policy.device_monthly_usd_cap),
        policy.folder_monthly_usd_cap,
    ))
}

pub fn read_budget_policy(
    device_config_path: impl AsRef<Path>,
    folder_config_path: impl AsRef<Path>,
) -> Result<BudgetCaps> {
    let device = read_budget_config(device_config_path)?;
    let folder = read_budget_config(folder_config_path)?;
    Ok(BudgetCaps {
        device_monthly_usd_cap: device
            .monthly_usd_cap
            .unwrap_or(DEFAULT_DEVICE_MONTHLY_USD_CAP),
        folder_monthly_usd_cap: folder.monthly_usd_cap,
        device_per_adapter: device.per_adapter,
        folder_per_adapter: folder.per_adapter,
        // F5: the more specific folder config overrides the device config; absent
        // both, the historical default (hard pause / warn at 80%).
        hard_stop: folder
            .hard_stop
            .or(device.hard_stop)
            .unwrap_or(DEFAULT_HARD_STOP),
        warn_at_percent: folder
            .warn_at_percent
            .or(device.warn_at_percent)
            .unwrap_or(DEFAULT_WARN_AT_PERCENT),
    })
}

/// F5: the non-blocking budget warning, or `None` when neither cap has crossed
/// `warn_at_percent`. Reports the layer (`device`/`folder`) at the higher
/// percentage. A zero or absent cap is skipped (a zero cap already hard-pauses).
#[must_use]
pub fn budget_warning(caps: &BudgetCaps, device_spent: f64, folder_spent: f64) -> Option<String> {
    let threshold = f64::from(caps.warn_at_percent);
    let mut worst: Option<(f64, &'static str)> = None;
    let mut consider = |spent: f64, cap: f64, layer: &'static str| {
        if cap > 0.0 {
            let pct = spent / cap * 100.0;
            if pct >= threshold && worst.map_or(true, |(best, _)| pct > best) {
                worst = Some((pct, layer));
            }
        }
    };
    consider(device_spent, caps.device_monthly_usd_cap, "device");
    if let Some(folder_cap) = caps.folder_monthly_usd_cap {
        consider(folder_spent, folder_cap, "folder");
    }
    worst.map(|(pct, layer)| format!("{layer} budget at {}% of cap", pct.round() as u64))
}

#[derive(Debug, Default)]
struct ParsedBudgetConfig {
    monthly_usd_cap: Option<f64>,
    per_adapter: BTreeMap<String, f64>,
    hard_stop: Option<bool>,
    warn_at_percent: Option<u8>,
}

fn read_budget_config(config_path: impl AsRef<Path>) -> Result<ParsedBudgetConfig> {
    let path = config_path.as_ref();
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
            return Ok(ParsedBudgetConfig::default())
        }
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
    let per_adapter: BTreeMap<String, f64> = budget
        .and_then(|value| value.get("per_adapter"))
        .and_then(toml::Value::as_table)
        .map(|table| {
            table
                .iter()
                .filter_map(|(key, value)| {
                    value
                        .as_float()
                        .or_else(|| value.as_integer().map(|value| value as f64))
                        .map(|cap| (key.clone(), cap))
                })
                .collect()
        })
        .unwrap_or_default();
    let monthly_usd_cap = budget
        .and_then(|value| value.get("monthly_usd_cap"))
        .and_then(toml::Value::as_float)
        .or_else(|| {
            budget
                .and_then(|value| value.get("monthly_usd_cap"))
                .and_then(toml::Value::as_integer)
                .map(|value| value as f64)
        });
    // M8: non-negative guard on budget caps (defense-in-depth behind the
    // config.schema.json `minimum: 0` constraint, 10 §12 / 06 §11). A negative cap
    // is nonsensical and would silently invert the budget arithmetic; reject it
    // (exit 2 KCS-E-CONFIG-SCHEMA-001 via `pipeline_to_kcs`).
    if let Some(cap) = monthly_usd_cap {
        if cap < 0.0 {
            return Err(PipelineError::Schema(format!(
                "budget.monthly_usd_cap must be non-negative at {}: {cap}",
                path.display()
            )));
        }
    }
    for (adapter, cap) in &per_adapter {
        if *cap < 0.0 {
            return Err(PipelineError::Schema(format!(
                "budget.per_adapter.{adapter} must be non-negative at {}: {cap}",
                path.display()
            )));
        }
    }
    // F5: `hard_stop` (bool) and `warn_at_percent` (0..=100) are documented in
    // docs/04 §5.4. `None` = key absent → the caller applies the default.
    let hard_stop = budget
        .and_then(|value| value.get("hard_stop"))
        .and_then(toml::Value::as_bool);
    let warn_at_percent = match budget
        .and_then(|value| value.get("warn_at_percent"))
        .and_then(toml::Value::as_integer)
    {
        Some(percent) => {
            if !(0..=100).contains(&percent) {
                return Err(PipelineError::Schema(format!(
                    "budget.warn_at_percent must be between 0 and 100 at {}: {percent}",
                    path.display()
                )));
            }
            Some(percent as u8)
        }
        None => None,
    };
    Ok(ParsedBudgetConfig {
        monthly_usd_cap,
        per_adapter,
        hard_stop,
        warn_at_percent,
    })
}

pub fn read_budget_caps_legacy(
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

    // F5: the pure warning crosses at `warn_at_percent` of whichever cap is higher;
    // below the threshold it is silent.
    #[test]
    fn f5_budget_warning_crosses_threshold_and_reports_worst_layer() {
        let caps = BudgetCaps {
            device_monthly_usd_cap: 100.0,
            folder_monthly_usd_cap: Some(10.0),
            device_per_adapter: BTreeMap::new(),
            folder_per_adapter: BTreeMap::new(),
            hard_stop: true,
            warn_at_percent: 80,
        };
        // Both below 80% → no warning.
        assert_eq!(budget_warning(&caps, 50.0, 5.0), None);
        // Device at 85% → warn device.
        assert_eq!(
            budget_warning(&caps, 85.0, 5.0).as_deref(),
            Some("device budget at 85% of cap")
        );
        // Folder at 95% while device at 85% → report the higher (folder).
        assert_eq!(
            budget_warning(&caps, 85.0, 9.5).as_deref(),
            Some("folder budget at 95% of cap")
        );
    }

    // F5: absent keys resolve to the historical default (hard pause / warn 80), and
    // the more specific folder config overrides the device config.
    #[test]
    fn f5_hard_stop_and_warn_at_percent_parse_and_default() {
        let dir = tempfile::tempdir().unwrap();
        let device = dir.path().join("device.toml");
        let folder = dir.path().join("folder.toml");

        // Both files absent → defaults.
        let defaults = read_budget_policy(&device, &folder).unwrap();
        assert!(defaults.hard_stop);
        assert_eq!(defaults.warn_at_percent, DEFAULT_WARN_AT_PERCENT);

        // Device sets soft-stop + warn 70; folder overrides warn to 90.
        std::fs::write(
            &device,
            "[budget]\nhard_stop = false\nwarn_at_percent = 70\n",
        )
        .unwrap();
        std::fs::write(&folder, "[budget]\nwarn_at_percent = 90\n").unwrap();
        let resolved = read_budget_policy(&device, &folder).unwrap();
        assert!(!resolved.hard_stop, "device hard_stop=false must apply");
        assert_eq!(resolved.warn_at_percent, 90, "folder overrides device");
    }

    #[test]
    fn f5_warn_at_percent_out_of_range_is_rejected() {
        let dir = tempfile::tempdir().unwrap();
        let device = dir.path().join("device.toml");
        let folder = dir.path().join("folder.toml");
        std::fs::write(&device, "[budget]\nwarn_at_percent = 150\n").unwrap();
        let err = read_budget_policy(&device, &folder).unwrap_err();
        assert!(matches!(err, PipelineError::Schema(_)), "got {err:?}");
    }

    // F3: a negative `usd` row must not lower `spent` (which would raise the
    // budget remaining and fail-open the cap). Reading it is a corrupt store, and
    // appending one is rejected outright.
    #[test]
    fn f3_negative_usd_ledger_row_is_store_corrupt_and_does_not_lower_spent() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.jsonl");
        let ledger = CostLedger::new(&path);
        // A legitimate charge, then a hand-injected negative charge.
        ledger
            .append_monthly(&MonthlyCostLedgerEntry {
                month: "2026-07".to_owned(),
                scope_id: "scope".to_owned(),
                adapter_kind: "embedding".to_owned(),
                usd: 5.0,
            })
            .unwrap();
        let negative = serde_json::to_string(&MonthlyCostLedgerEntry {
            month: "2026-07".to_owned(),
            scope_id: "scope".to_owned(),
            adapter_kind: "embedding".to_owned(),
            usd: -1000.0,
        })
        .unwrap();
        let mut with_newline = negative;
        with_newline.push('\n');
        {
            use std::io::Write as _;
            let mut file = OpenOptions::new().append(true).open(&path).unwrap();
            file.write_all(with_newline.as_bytes()).unwrap();
        }
        // Read must NOT sum the negative row down; it is classified corrupt.
        let err = ledger.monthly_total("2026-07", None).unwrap_err();
        assert!(
            matches!(err, PipelineError::Corrupt { .. }),
            "expected STORE-CORRUPT, got {err:?}"
        );
    }

    #[test]
    fn f3_append_rejects_negative_and_non_finite_usd() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("cost-ledger.jsonl");
        let ledger = CostLedger::new(&path);
        for bad in [-0.01, f64::NAN, f64::INFINITY] {
            let err = ledger
                .append_monthly(&MonthlyCostLedgerEntry {
                    month: "2026-07".to_owned(),
                    scope_id: "scope".to_owned(),
                    adapter_kind: "embedding".to_owned(),
                    usd: bad,
                })
                .unwrap_err();
            assert!(
                matches!(err, PipelineError::Corrupt { .. }),
                "expected STORE-CORRUPT for usd={bad}, got {err:?}"
            );
        }
        // The rejected appends must not have created any summable spend.
        assert_eq!(ledger.monthly_total("2026-07", None).unwrap(), 0.0);
    }
}
