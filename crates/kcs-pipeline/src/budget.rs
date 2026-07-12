//! Cost guardrail and budget contracts.

use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, Read, Write};
use std::path::{Path, PathBuf};

use kcs_core::scope::StoreLock;
use serde::{Deserialize, Serialize};

use crate::task::{is_valid_reservation_id, TaskReservationClaim, TaskType};
use crate::{IoResultExt, PipelineError, Result};

pub const DEFAULT_DEVICE_MONTHLY_USD_CAP: f64 = 50.0;

/// F5 defaults (docs/04 §5.4). When `[budget]` omits these keys the behavior is
/// the historical one: a hard pause at the cap, warning once spend reaches 80% of
/// a cap.
pub const DEFAULT_WARN_AT_PERCENT: u8 = 80;
pub const DEFAULT_HARD_STOP: bool = true;
const MAX_RESERVATION_LEDGER_BYTES: u64 = 64 * 1024 * 1024;
const MAX_RESERVATION_EVENT_BYTES: u64 = 64 * 1024;
const MAX_RESERVATION_EVENTS: usize = 1_000_000;

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
pub struct ReservationRecord {
    pub reservation_id: String,
    pub task_id: String,
    pub month: String,
    pub scope_id: String,
    pub adapter_kind: String,
    pub usd: f64,
}

impl ReservationRecord {
    #[must_use]
    pub fn claim(&self) -> TaskReservationClaim<'_> {
        TaskReservationClaim {
            reservation_id: &self.reservation_id,
            task_id: &self.task_id,
            usd: self.usd,
            month: &self.month,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "event", content = "reservation", rename_all = "snake_case")]
enum ReservationLedgerEvent {
    Issued(ReservationRecord),
    Reclaimable { reservation_id: String },
    Activated { reservation_id: String },
    Closed { reservation_id: String },
    Consumed { reservation_id: String },
}

#[derive(Debug, Clone)]
struct ReservationState {
    record: ReservationRecord,
    status: ReservationStatus,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ReservationStatus {
    Active,
    Reclaimable,
    Closed,
    Consumed,
}

/// Device-global authority for budget reservations. Scope-local task fields are
/// only claims; a reclaim is valid after this ledger atomically consumes the
/// matching, previously unconsumed reservation identity.
#[derive(Debug, Clone)]
pub struct ReservationLedger {
    path: PathBuf,
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
                && scope_id.is_none_or(|scope| scope == entry.scope_id)
                && adapter_kind.is_none_or(|kind| kind == entry.adapter_kind)
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

    #[must_use]
    pub fn reservation_ledger(&self) -> ReservationLedger {
        ReservationLedger::new(self.path.with_file_name("cost-ledger-reservations.jsonl"))
    }
}

impl ReservationLedger {
    #[must_use]
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }

    /// Persist a newly issued reservation under an exclusive ledger lock. IDs
    /// are never reusable, including after consumption.
    pub fn issue(&self, reservation: &ReservationRecord) -> Result<()> {
        self.issue_all(std::slice::from_ref(reservation))
    }

    /// Batch form used by one charged adapter request. Validation and duplicate
    /// checks happen for the entire set before the first event is appended.
    pub fn issue_all(&self, reservations: &[ReservationRecord]) -> Result<()> {
        if reservations.is_empty() {
            return Ok(());
        }
        for reservation in reservations {
            validate_reservation_record(&self.path, reservation)?;
        }
        let _lock = self.acquire_lock()?;
        let state = self.load_state()?;
        let mut ids = state
            .keys()
            .cloned()
            .collect::<std::collections::BTreeSet<_>>();
        for reservation in reservations {
            if !ids.insert(reservation.reservation_id.clone()) {
                return Err(PipelineError::corrupt(
                    self.path.display().to_string(),
                    format!(
                        "duplicate reservation identity: {}",
                        reservation.reservation_id
                    ),
                ));
            }
        }
        for reservation in reservations {
            self.append_event(&ReservationLedgerEvent::Issued(reservation.clone()))?;
        }
        Ok(())
    }

    /// Consume a scope-local task claim exactly once and return a reclaim row
    /// derived entirely from the trusted reservation. Unknown, copied, already
    /// consumed, or mismatched claims produce no credit.
    pub fn consume(
        &self,
        claim: TaskReservationClaim<'_>,
        expected_scope_id: &str,
        expected_adapter_kind: &str,
    ) -> Result<Option<MonthlyCostLedgerEntry>> {
        if !is_valid_reservation_id(claim.reservation_id) {
            return Ok(None);
        }
        let _lock = self.acquire_lock()?;
        let state = self.load_state()?;
        let Some(reservation) = matching_reservation(
            &state,
            claim,
            expected_scope_id,
            expected_adapter_kind,
            ReservationStatus::Reclaimable,
        ) else {
            return Ok(None);
        };
        self.append_event(&ReservationLedgerEvent::Consumed {
            reservation_id: reservation.reservation_id.clone(),
        })?;
        Ok(Some(MonthlyCostLedgerEntry {
            month: reservation.month.clone(),
            scope_id: reservation.scope_id.clone(),
            adapter_kind: reservation.adapter_kind.clone(),
            usd: reservation.usd,
        }))
    }

    /// Verify that a claim is backed by a trusted non-billable outcome that has
    /// not yet been retried or reclaimed.
    pub fn matches_unconsumed(
        &self,
        claim: TaskReservationClaim<'_>,
        expected_scope_id: &str,
        expected_adapter_kind: &str,
    ) -> Result<bool> {
        if !is_valid_reservation_id(claim.reservation_id) {
            return Ok(false);
        }
        let _lock = self.acquire_lock()?;
        let state = self.load_state()?;
        Ok(matching_reservation(
            &state,
            claim,
            expected_scope_id,
            expected_adapter_kind,
            ReservationStatus::Reclaimable,
        )
        .is_some())
    }

    /// Mark an active reservation reclaimable after a trusted non-billable
    /// provider outcome (RateLimit, QuotaExceeded, or AuthError).
    pub fn mark_reclaimable(
        &self,
        claim: TaskReservationClaim<'_>,
        expected_scope_id: &str,
        expected_adapter_kind: &str,
    ) -> Result<bool> {
        self.transition_claim(
            claim,
            expected_scope_id,
            expected_adapter_kind,
            &[ReservationStatus::Active],
            |reservation_id| ReservationLedgerEvent::Reclaimable { reservation_id },
        )
    }

    /// Atomically take a reclaimable reservation back into active use before a
    /// retry send. A crash after this transition cannot later reclaim a request
    /// whose billing outcome is unknown.
    pub fn activate_for_retry(
        &self,
        claim: TaskReservationClaim<'_>,
        expected_scope_id: &str,
        expected_adapter_kind: &str,
    ) -> Result<bool> {
        self.transition_claim(
            claim,
            expected_scope_id,
            expected_adapter_kind,
            &[ReservationStatus::Reclaimable],
            |reservation_id| ReservationLedgerEvent::Activated { reservation_id },
        )
    }

    /// Close a reservation after a successful or potentially billable outcome.
    /// Closed identities can never authorize a reclaim.
    pub fn close(
        &self,
        claim: TaskReservationClaim<'_>,
        expected_scope_id: &str,
        expected_adapter_kind: &str,
    ) -> Result<bool> {
        self.transition_claim(
            claim,
            expected_scope_id,
            expected_adapter_kind,
            &[ReservationStatus::Active, ReservationStatus::Reclaimable],
            |reservation_id| ReservationLedgerEvent::Closed { reservation_id },
        )
    }

    #[must_use]
    pub fn path(&self) -> &Path {
        &self.path
    }

    fn acquire_lock(&self) -> Result<StoreLock> {
        let lock_path = self.path.with_extension("jsonl.lock");
        // Use the repository lock primitive so a process crash cannot strand this
        // device-global ledger forever. Callers may already hold cost-ledger.lock;
        // reservation operations never acquire that outer lock, preserving order.
        StoreLock::acquire_path(lock_path.clone()).map_err(|err| {
            if err.error_code() == "KCS-E-STORE-LOCKED-001" {
                PipelineError::locked(lock_path.display().to_string())
            } else {
                PipelineError::Io {
                    path: lock_path.display().to_string(),
                    message: err.to_string(),
                }
            }
        })
    }

    fn append_event(&self, event: &ReservationLedgerEvent) -> Result<()> {
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent).pipeline_io(parent)?;
        }
        let mut line =
            serde_json::to_vec(event).map_err(|err| PipelineError::Schema(err.to_string()))?;
        if line.len() as u64 > MAX_RESERVATION_EVENT_BYTES {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                "reservation event exceeds its byte limit".to_owned(),
            ));
        }
        line.push(b'\n');
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .pipeline_io(&self.path)?;
        let existing = file.metadata().pipeline_io(&self.path)?.len();
        if existing.saturating_add(line.len() as u64) > MAX_RESERVATION_LEDGER_BYTES {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                "reservation ledger exceeds its byte limit".to_owned(),
            ));
        }
        file.write_all(&line).pipeline_io(&self.path)?;
        file.sync_all().pipeline_io(&self.path)
    }

    fn load_state(&self) -> Result<BTreeMap<String, ReservationState>> {
        let file = match fs::File::open(&self.path) {
            Ok(file) => file,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(BTreeMap::new()),
            Err(err) => {
                return Err(PipelineError::Io {
                    path: self.path.display().to_string(),
                    message: err.to_string(),
                })
            }
        };
        let len = file.metadata().pipeline_io(&self.path)?.len();
        if len > MAX_RESERVATION_LEDGER_BYTES {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                "reservation ledger exceeds its byte limit".to_owned(),
            ));
        }
        let mut reader = std::io::BufReader::new(file);
        let mut line = Vec::new();
        let mut state: BTreeMap<String, ReservationState> = BTreeMap::new();
        let mut events = 0usize;
        let mut total_read = 0u64;
        loop {
            line.clear();
            let read = reader
                .by_ref()
                .take(MAX_RESERVATION_EVENT_BYTES.saturating_add(1))
                .read_until(b'\n', &mut line)
                .pipeline_io(&self.path)?;
            if read == 0 {
                break;
            }
            total_read = total_read.saturating_add(read as u64);
            if total_read > MAX_RESERVATION_LEDGER_BYTES {
                return Err(PipelineError::corrupt(
                    self.path.display().to_string(),
                    "reservation ledger exceeds its byte limit".to_owned(),
                ));
            }
            if read as u64 > MAX_RESERVATION_EVENT_BYTES {
                return Err(PipelineError::corrupt(
                    self.path.display().to_string(),
                    "reservation event exceeds its byte limit".to_owned(),
                ));
            }
            if line.iter().all(u8::is_ascii_whitespace) {
                continue;
            }
            events = events.saturating_add(1);
            if events > MAX_RESERVATION_EVENTS {
                return Err(PipelineError::corrupt(
                    self.path.display().to_string(),
                    "reservation ledger exceeds its event limit".to_owned(),
                ));
            }
            let event: ReservationLedgerEvent = serde_json::from_slice(&line).map_err(|err| {
                PipelineError::corrupt(self.path.display().to_string(), err.to_string())
            })?;
            match event {
                ReservationLedgerEvent::Issued(record) => {
                    validate_reservation_record(&self.path, &record)?;
                    let reservation_id = record.reservation_id.clone();
                    if state
                        .insert(
                            reservation_id.clone(),
                            ReservationState {
                                record,
                                status: ReservationStatus::Active,
                            },
                        )
                        .is_some()
                    {
                        return Err(PipelineError::corrupt(
                            self.path.display().to_string(),
                            format!("duplicate reservation identity: {reservation_id}"),
                        ));
                    }
                }
                ReservationLedgerEvent::Reclaimable { reservation_id } => {
                    transition_loaded_state(
                        &self.path,
                        &mut state,
                        &reservation_id,
                        ReservationStatus::Active,
                        ReservationStatus::Reclaimable,
                    )?;
                }
                ReservationLedgerEvent::Activated { reservation_id } => {
                    transition_loaded_state(
                        &self.path,
                        &mut state,
                        &reservation_id,
                        ReservationStatus::Reclaimable,
                        ReservationStatus::Active,
                    )?;
                }
                ReservationLedgerEvent::Closed { reservation_id } => {
                    let Some(reservation) = state.get_mut(&reservation_id) else {
                        return Err(unknown_reservation_transition(&self.path, &reservation_id));
                    };
                    if !matches!(
                        reservation.status,
                        ReservationStatus::Active | ReservationStatus::Reclaimable
                    ) {
                        return Err(invalid_reservation_transition(&self.path, &reservation_id));
                    }
                    reservation.status = ReservationStatus::Closed;
                }
                ReservationLedgerEvent::Consumed { reservation_id } => {
                    transition_loaded_state(
                        &self.path,
                        &mut state,
                        &reservation_id,
                        ReservationStatus::Reclaimable,
                        ReservationStatus::Consumed,
                    )?;
                }
            }
        }
        Ok(state)
    }

    fn transition_claim(
        &self,
        claim: TaskReservationClaim<'_>,
        expected_scope_id: &str,
        expected_adapter_kind: &str,
        allowed_statuses: &[ReservationStatus],
        event: impl FnOnce(String) -> ReservationLedgerEvent,
    ) -> Result<bool> {
        if !is_valid_reservation_id(claim.reservation_id) {
            return Ok(false);
        }
        let _lock = self.acquire_lock()?;
        let state = self.load_state()?;
        let Some(state_entry) = state.get(claim.reservation_id) else {
            return Ok(false);
        };
        if !allowed_statuses.contains(&state_entry.status)
            || !reservation_binding_matches(
                &state_entry.record,
                claim,
                expected_scope_id,
                expected_adapter_kind,
            )
        {
            return Ok(false);
        }
        self.append_event(&event(state_entry.record.reservation_id.clone()))?;
        Ok(true)
    }
}

fn matching_reservation<'a>(
    state: &'a BTreeMap<String, ReservationState>,
    claim: TaskReservationClaim<'_>,
    expected_scope_id: &str,
    expected_adapter_kind: &str,
    required_status: ReservationStatus,
) -> Option<&'a ReservationRecord> {
    let state = state.get(claim.reservation_id)?;
    let reservation = &state.record;
    (state.status == required_status
        && reservation_binding_matches(
            reservation,
            claim,
            expected_scope_id,
            expected_adapter_kind,
        ))
    .then_some(reservation)
}

fn reservation_binding_matches(
    reservation: &ReservationRecord,
    claim: TaskReservationClaim<'_>,
    expected_scope_id: &str,
    expected_adapter_kind: &str,
) -> bool {
    reservation.task_id == claim.task_id
        && reservation.scope_id == expected_scope_id
        && reservation.adapter_kind == expected_adapter_kind
        && reservation.month == claim.month
        && reservation.usd.to_bits() == claim.usd.to_bits()
}

fn transition_loaded_state(
    path: &Path,
    state: &mut BTreeMap<String, ReservationState>,
    reservation_id: &str,
    expected: ReservationStatus,
    next: ReservationStatus,
) -> Result<()> {
    let Some(reservation) = state.get_mut(reservation_id) else {
        return Err(unknown_reservation_transition(path, reservation_id));
    };
    if reservation.status != expected {
        return Err(invalid_reservation_transition(path, reservation_id));
    }
    reservation.status = next;
    Ok(())
}

fn unknown_reservation_transition(path: &Path, reservation_id: &str) -> PipelineError {
    PipelineError::corrupt(
        path.display().to_string(),
        format!("transition references unknown reservation: {reservation_id}"),
    )
}

fn invalid_reservation_transition(path: &Path, reservation_id: &str) -> PipelineError {
    PipelineError::corrupt(
        path.display().to_string(),
        format!("invalid reservation state transition: {reservation_id}"),
    )
}

fn validate_reservation_record(path: &Path, reservation: &ReservationRecord) -> Result<()> {
    if !is_valid_reservation_id(&reservation.reservation_id)
        || reservation.task_id.is_empty()
        || reservation.task_id.len() > 256
        || reservation.scope_id.is_empty()
        || reservation.scope_id.len() > 512
        || reservation.adapter_kind.is_empty()
        || reservation.adapter_kind.len() > 256
        || !reservation.usd.is_finite()
        || reservation.usd < 0.0
        || !valid_utc_month(&reservation.month)
    {
        return Err(PipelineError::corrupt(
            path.display().to_string(),
            "invalid trusted reservation record".to_owned(),
        ));
    }
    Ok(())
}

fn valid_utc_month(value: &str) -> bool {
    if value.len() != 7 || value.as_bytes()[4] != b'-' {
        return false;
    }
    let year = &value.as_bytes()[0..4];
    let month = &value.as_bytes()[5..7];
    year.iter().all(u8::is_ascii_digit)
        && month.iter().all(u8::is_ascii_digit)
        && matches!(
            month,
            b"01"
                | b"02"
                | b"03"
                | b"04"
                | b"05"
                | b"06"
                | b"07"
                | b"08"
                | b"09"
                | b"10"
                | b"11"
                | b"12"
        )
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
            if pct >= threshold && worst.is_none_or(|(best, _)| pct > best) {
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

    #[test]
    fn cand_048_reservation_claim_is_bound_and_consumed_once() {
        let dir = tempfile::tempdir().unwrap();
        let ledger = ReservationLedger::new(dir.path().join("reservations.jsonl"));
        let record = ReservationRecord {
            reservation_id: "res_01JBOUND".to_owned(),
            task_id: "task_01JBOUND".to_owned(),
            month: "2026-07".to_owned(),
            scope_id: "scope-a".to_owned(),
            adapter_kind: "embedding".to_owned(),
            usd: 1.25,
        };
        ledger.issue(&record).unwrap();

        let claim = TaskReservationClaim {
            reservation_id: &record.reservation_id,
            task_id: &record.task_id,
            usd: record.usd,
            month: &record.month,
        };
        assert!(!ledger
            .matches_unconsumed(claim, &record.scope_id, &record.adapter_kind)
            .unwrap());
        assert!(ledger
            .consume(claim, &record.scope_id, &record.adapter_kind)
            .unwrap()
            .is_none());
        assert!(ledger
            .mark_reclaimable(claim, &record.scope_id, &record.adapter_kind)
            .unwrap());
        assert!(ledger
            .consume(claim, "scope-b", &record.adapter_kind)
            .unwrap()
            .is_none());
        assert!(ledger
            .matches_unconsumed(claim, &record.scope_id, &record.adapter_kind)
            .unwrap());
        let reclaimed = ledger
            .consume(claim, &record.scope_id, &record.adapter_kind)
            .unwrap()
            .unwrap();
        assert_eq!(reclaimed.month, record.month);
        assert_eq!(reclaimed.scope_id, record.scope_id);
        assert_eq!(reclaimed.adapter_kind, record.adapter_kind);
        assert_eq!(reclaimed.usd, record.usd);
        assert!(ledger
            .consume(claim, &record.scope_id, &record.adapter_kind)
            .unwrap()
            .is_none());
        assert!(!ledger
            .matches_unconsumed(claim, &record.scope_id, &record.adapter_kind)
            .unwrap());
    }

    #[test]
    fn cand_048_forged_or_mismatched_reservation_claim_never_mints_credit() {
        let dir = tempfile::tempdir().unwrap();
        let ledger = ReservationLedger::new(dir.path().join("reservations.jsonl"));
        let unknown = TaskReservationClaim {
            reservation_id: "res_01JFORGED",
            task_id: "task_forged",
            usd: 9.75,
            month: "2026-07",
        };
        assert!(ledger
            .consume(unknown, "victim-scope", "markdown")
            .unwrap()
            .is_none());

        let record = ReservationRecord {
            reservation_id: "res_01JREAL".to_owned(),
            task_id: "task_real".to_owned(),
            month: "2026-07".to_owned(),
            scope_id: "victim-scope".to_owned(),
            adapter_kind: "markdown".to_owned(),
            usd: 2.0,
        };
        ledger.issue(&record).unwrap();
        let wrong_amount = TaskReservationClaim {
            reservation_id: &record.reservation_id,
            task_id: &record.task_id,
            usd: 9.75,
            month: &record.month,
        };
        assert!(!ledger
            .mark_reclaimable(wrong_amount, &record.scope_id, &record.adapter_kind)
            .unwrap());
        let correct = TaskReservationClaim {
            reservation_id: &record.reservation_id,
            task_id: &record.task_id,
            usd: record.usd,
            month: &record.month,
        };
        assert!(ledger
            .mark_reclaimable(correct, &record.scope_id, &record.adapter_kind)
            .unwrap());
        assert!(ledger
            .consume(wrong_amount, &record.scope_id, &record.adapter_kind)
            .unwrap()
            .is_none());
        assert!(ledger
            .activate_for_retry(correct, &record.scope_id, &record.adapter_kind)
            .unwrap());
        assert!(ledger
            .consume(correct, &record.scope_id, &record.adapter_kind)
            .unwrap()
            .is_none());
        assert!(ledger
            .mark_reclaimable(correct, &record.scope_id, &record.adapter_kind)
            .unwrap());
        assert!(ledger
            .consume(correct, &record.scope_id, &record.adapter_kind)
            .unwrap()
            .is_some());
        assert!(
            ledger.issue(&record).is_err(),
            "reservation IDs are never reusable"
        );
    }

    #[test]
    fn cand_048_successful_or_unknown_outcome_reservation_cannot_be_reclaimed() {
        let dir = tempfile::tempdir().unwrap();
        let ledger = ReservationLedger::new(dir.path().join("reservations.jsonl"));
        let record = ReservationRecord {
            reservation_id: "res_01JCLOSED".to_owned(),
            task_id: "task_closed".to_owned(),
            month: "2026-07".to_owned(),
            scope_id: "scope-a".to_owned(),
            adapter_kind: "markdown".to_owned(),
            usd: 2.0,
        };
        ledger.issue(&record).unwrap();
        let claim = TaskReservationClaim {
            reservation_id: &record.reservation_id,
            task_id: &record.task_id,
            usd: record.usd,
            month: &record.month,
        };
        assert!(ledger
            .close(claim, &record.scope_id, &record.adapter_kind)
            .unwrap());
        assert!(!ledger
            .mark_reclaimable(claim, &record.scope_id, &record.adapter_kind)
            .unwrap());
        assert!(ledger
            .consume(claim, &record.scope_id, &record.adapter_kind)
            .unwrap()
            .is_none());
    }

    #[test]
    fn reservation_ledger_recovers_lock_left_by_crashed_process() {
        let dir = tempfile::tempdir().unwrap();
        let ledger_path = dir.path().join("reservations.jsonl");
        let lock_path = ledger_path.with_extension("jsonl.lock");
        std::fs::write(
            &lock_path,
            r#"{"pid":4294967295,"token":"crashed-owner","created_at":"2026-07-12T00:00:00Z"}"#,
        )
        .unwrap();

        let ledger = ReservationLedger::new(&ledger_path);
        let record = ReservationRecord {
            reservation_id: "res_crash_recovery".to_owned(),
            task_id: "task_crash_recovery".to_owned(),
            month: "2026-07".to_owned(),
            scope_id: "scope-a".to_owned(),
            adapter_kind: "embedding".to_owned(),
            usd: 0.25,
        };
        ledger.issue(&record).unwrap();

        assert!(!lock_path.exists(), "recovered lock must release normally");
        assert_eq!(ledger.load_state().unwrap().len(), 1);
    }

    #[test]
    fn reservation_ledger_excludes_a_live_lock_owner() {
        let dir = tempfile::tempdir().unwrap();
        let ledger_path = dir.path().join("reservations.jsonl");
        let lock_path = ledger_path.with_extension("jsonl.lock");
        let held_path = lock_path.clone();
        let (ready_tx, ready_rx) = std::sync::mpsc::channel();
        let (release_tx, release_rx) = std::sync::mpsc::channel();
        let holder = std::thread::spawn(move || {
            let _guard = StoreLock::acquire_path(held_path).unwrap();
            ready_tx.send(()).unwrap();
            release_rx.recv().unwrap();
        });
        ready_rx.recv().unwrap();

        let ledger = ReservationLedger::new(&ledger_path);
        let record = ReservationRecord {
            reservation_id: "res_live_owner".to_owned(),
            task_id: "task_live_owner".to_owned(),
            month: "2026-07".to_owned(),
            scope_id: "scope-a".to_owned(),
            adapter_kind: "markdown".to_owned(),
            usd: 0.5,
        };
        let err = ledger.issue(&record).unwrap_err();
        assert!(
            matches!(&err, PipelineError::Locked { path } if path == &lock_path.display().to_string()),
            "got {err:?}"
        );
        assert!(
            err.to_string().starts_with("KCS-E-STORE-LOCKED-001:"),
            "live contention must fail as a held lock: {err}"
        );
        assert!(
            !ledger_path.exists(),
            "contending writer must not append an event"
        );

        release_tx.send(()).unwrap();
        holder.join().unwrap();
        assert!(!lock_path.exists(), "live owner must release its own lock");
    }

    #[test]
    fn reservation_ledger_allows_sequential_legitimate_writers() {
        let dir = tempfile::tempdir().unwrap();
        let ledger_path = dir.path().join("reservations.jsonl");
        let ledger = ReservationLedger::new(&ledger_path);
        for suffix in ["first", "second"] {
            ledger
                .issue(&ReservationRecord {
                    reservation_id: format!("res_{suffix}"),
                    task_id: format!("task_{suffix}"),
                    month: "2026-07".to_owned(),
                    scope_id: "scope-a".to_owned(),
                    adapter_kind: "embedding".to_owned(),
                    usd: 0.25,
                })
                .unwrap();
        }

        assert_eq!(ledger.load_state().unwrap().len(), 2);
        assert!(
            !ledger_path.with_extension("jsonl.lock").exists(),
            "a completed writer must not strand the lock"
        );
    }
}
