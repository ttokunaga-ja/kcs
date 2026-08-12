//! Durable purge-state contracts shared by the CLI, readers, and fsck.
//!
//! This module deliberately owns only the visibility barrier and the durable
//! lifecycle records (tombstone / erase receipt) plus the two epoch counters
//! that gate them. Physical artifact deletion and CLI orchestration live above
//! it. Callers that mutate this state must already hold the scope store lock.
//!
//! Step4b (`tasks/step4b-contract-tests-lifecycle.md`, LC1-LC60) rewrote the
//! tombstone / erase-receipt records from a flat single-purge shape to an
//! append-only `events[]` lifecycle (`purged`/`erased`/`retired`), added the
//! purge-epoch (`purge/epoch`) and lifecycle-epoch
//! (`tombstones/lifecycle-epoch`) monotonic counters, and reversed the old
//! "public tombstone permanently blocks re-ingest" rule into a resurrection
//! flow: re-publication is allowed and retires the marker in the same locked
//! mutation as the republication's snapshot finalize (05-runtime.md §3.5).

use std::collections::BTreeSet;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::cas::{canonical_json_bytes, fanout_path, is_hash};
use crate::{ExitCode, KioError, Result};

pub const MAX_PURGE_TARGETS: usize = 100_000;
/// Bound on one tombstone/erase-receipt record. Bumped from the flat-schema
/// era's 16 KiB to accommodate an append-only `events[]` array that grows by
/// one element per retire/re-purge/legacy-conversion (LC4).
pub const MAX_PURGE_RECORD_BYTES: u64 = 64 * 1024;
pub const MAX_PURGE_JOURNAL_BYTES: u64 = 8 * 1024 * 1024;
/// Bound on the `.kio/purge/journal-closure` sidecar (step4b-contract-tests-p2a.md
/// PA43-46, §R ruling #2). Kept separate from and larger than
/// `MAX_PURGE_JOURNAL_BYTES` — a scope with a large fan-out of chunk/prepared/
/// image objects destined for deletion can have a closure item enumeration far
/// bigger than the journal's own fixed-size fields, but this is still a
/// torn/DoS defense bound, not an unbounded allocation.
pub const MAX_PURGE_CLOSURE_BYTES: u64 = 64 * 1024 * 1024;
/// Bound on the two single-line monotonic counter files (LC39/LC41).
pub const MAX_EPOCH_COUNTER_BYTES: u64 = 64;

// v3 (PA43-46, §R ruling #2): `closure: Vec<ClosureItem>` replaced by
// `closure_hash: String`, a content-hash reference to the new
// `.kio/purge/journal-closure` sidecar ([`PurgeClosure`]).
const JOURNAL_SCHEMA_VERSION: u64 = 3;
const RECEIPT_SCHEMA_VERSION: u64 = 2;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PurgeReason {
    Legal,
    Privacy,
    Misingest,
    Copyright,
    Other,
}

impl FromStr for PurgeReason {
    type Err = KioError;

    fn from_str(value: &str) -> Result<Self> {
        match value {
            "legal" => Ok(Self::Legal),
            "privacy" => Ok(Self::Privacy),
            "misingest" => Ok(Self::Misingest),
            "copyright" => Ok(Self::Copyright),
            "other" => Ok(Self::Other),
            _ => Err(KioError::invalid_usage(
                "purge reason must be legal, privacy, misingest, copyright, or other",
            )),
        }
    }
}

impl std::fmt::Display for PurgeReason {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::Legal => "legal",
            Self::Privacy => "privacy",
            Self::Misingest => "misingest",
            Self::Copyright => "copyright",
            Self::Other => "other",
        })
    }
}

/// Which durable marker a lifecycle record/event belongs to. `Default` is the
/// public tombstone; `Erase` is the fsck-only, non-public erase receipt
/// (08-evidence-pointer-spec.md §4.2's usage enumeration). Reused (rather than
/// introducing a parallel "MarkerKind") as both "which purge mode was
/// requested" and "which marker a canonical final event was drawn from."
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TombstoneMode {
    Default,
    Erase,
}

/// LC1/LC2: the closed 3-value event-kind enum. Which two are valid for a
/// given marker is enforced by [`LifecycleEvent::validate_fields`], not by the
/// type system, because the wire representation is marker-agnostic JSON.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EventKind {
    Purged,
    Erased,
    Retired,
}

/// One `events[]` element (05-runtime.md §3.5, 10-operations.md §7.5.1). Field
/// presence follows the LC3/10§7.5.1 L557-562 "complete enumeration" table:
/// `at`/`in_commit`/`actor` are always required; `reason` is always required
/// on `purged`/`erased`; `resurrection_commit` is always required on
/// `retired`; `lifecycle_epoch` is required on every event, and `epoch` on
/// every `purged`/`erased` one.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LifecycleEvent {
    pub kind: EventKind,
    pub at: String,
    pub in_commit: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub actor: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<PurgeReason>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub epoch: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lifecycle_epoch: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resurrection_commit: Option<String>,
}

impl LifecycleEvent {
    /// Build a new `purged` event. `lifecycle_epoch` is left unset;
    /// [`PurgeState::append_tombstone_event`] stamps it from the
    /// pre-incremented counter (LC26).
    #[must_use]
    pub fn purged(
        at: impl Into<String>,
        in_commit: impl Into<String>,
        reason: PurgeReason,
        actor: impl Into<String>,
        epoch: u64,
    ) -> Self {
        Self {
            kind: EventKind::Purged,
            at: at.into(),
            in_commit: in_commit.into(),
            actor: Some(actor.into()),
            reason: Some(reason),
            epoch: Some(epoch),
            lifecycle_epoch: None,
            resurrection_commit: None,
        }
    }

    /// Build a new `erased` event. See [`Self::purged`].
    #[must_use]
    pub fn erased(
        at: impl Into<String>,
        in_commit: impl Into<String>,
        reason: PurgeReason,
        actor: impl Into<String>,
        epoch: u64,
    ) -> Self {
        Self {
            kind: EventKind::Erased,
            at: at.into(),
            in_commit: in_commit.into(),
            actor: Some(actor.into()),
            reason: Some(reason),
            epoch: Some(epoch),
            lifecycle_epoch: None,
            resurrection_commit: None,
        }
    }

    /// Build a `retired` event. `in_commit` and `resurrection_commit` are the
    /// same republication commit (05-runtime.md §3.5's JSON example carries
    /// identical values for both; `in_commit` is the "current" commit field
    /// every kind carries, `resurrection_commit` is the alive-again link 08
    /// §3.1 step 6b follows).
    #[must_use]
    pub fn retired(
        at: impl Into<String>,
        resurrection_commit: impl Into<String>,
        actor: impl Into<String>,
    ) -> Self {
        let commit = resurrection_commit.into();
        Self {
            kind: EventKind::Retired,
            at: at.into(),
            in_commit: commit.clone(),
            actor: Some(actor.into()),
            reason: None,
            epoch: None,
            lifecycle_epoch: None,
            resurrection_commit: Some(commit),
        }
    }

    /// Structural (schema-level) validation: kind closure per marker (LC1/LC2)
    /// and the LC3/LC16 required-field matrix. This does NOT perform the semantic,
    /// CAS/ref-bound checks of LC17/LC18/LC20 (`in_commit` ref-reachability,
    /// `purged_raws` membership, `at`==commit.created_at, resurrection
    /// ancestry) — those require DAG access this module does not have and are
    /// implemented by callers that do (verify_objects.rs, the resolver).
    fn validate_fields(&self, marker_kind: TombstoneMode) -> Result<()> {
        match (marker_kind, self.kind) {
            (TombstoneMode::Default, EventKind::Purged | EventKind::Retired)
            | (TombstoneMode::Erase, EventKind::Erased | EventKind::Retired) => {}
            _ => {
                return Err(corrupt_state(
                    "lifecycle event kind is not valid for this marker kind",
                ))
            }
        }
        validate_timestamp("lifecycle event at", &self.at)?;
        validate_hash("lifecycle event in_commit", &self.in_commit)?;
        if self.actor.as_deref().is_none_or(str::is_empty) {
            return Err(corrupt_state("lifecycle event is missing its actor"));
        }

        match self.kind {
            EventKind::Purged | EventKind::Erased => {
                if self.reason.is_none() {
                    return Err(corrupt_state("purged/erased event is missing its reason"));
                }
                if self.resurrection_commit.is_some() {
                    return Err(corrupt_state(
                        "purged/erased event must not carry resurrection_commit",
                    ));
                }
                if self.epoch.is_none() {
                    return Err(corrupt_state("purged/erased event is missing its epoch"));
                }
            }
            EventKind::Retired => {
                if self.reason.is_some() {
                    return Err(corrupt_state("retired event must not carry reason"));
                }
                if self.epoch.is_some() {
                    return Err(corrupt_state("retired event must not carry epoch"));
                }
                let Some(resurrection_commit) = self.resurrection_commit.as_deref() else {
                    return Err(corrupt_state(
                        "retired event is missing its resurrection_commit",
                    ));
                };
                validate_hash("lifecycle event resurrection_commit", resurrection_commit)?;
                if self.resurrection_commit.as_deref() != Some(self.in_commit.as_str()) {
                    return Err(corrupt_state(
                        "retired event in_commit must equal resurrection_commit",
                    ));
                }
            }
        }
        if self.lifecycle_epoch.is_none() {
            return Err(corrupt_state(
                "lifecycle event is missing its lifecycle_epoch",
            ));
        }
        Ok(())
    }
}

/// Two events are the "same operation" if replaying it would append an
/// identical entry. [`PurgeState::append_tombstone_event`] /
/// `append_erase_receipt_event` use this to make crash-resume retries of the
/// same journal-driven append idempotent (no duplicate `events[]` entry, no
/// extra lifecycle-epoch consumption) rather than re-validating on
/// server-assigned fields (`epoch`/`lifecycle_epoch`) that a retry cannot know
/// in advance.
fn events_are_equivalent(existing: &LifecycleEvent, proposed: &LifecycleEvent) -> bool {
    existing.kind == proposed.kind
        && existing.in_commit == proposed.in_commit
        && existing.at == proposed.at
        && existing.reason == proposed.reason
        && existing.resurrection_commit == proposed.resurrection_commit
}

/// LC1/LC2/LC19: non-empty, starts with the marker's opening kind, and
/// strictly alternates with `retired` thereafter (no repeated kind, no
/// foreign kind). Runs [`LifecycleEvent::validate_fields`] on every element.
fn validate_event_sequence(events: &[LifecycleEvent], marker_kind: TombstoneMode) -> Result<()> {
    if events.is_empty() {
        return Err(corrupt_state("lifecycle events must not be empty"));
    }
    let opening = match marker_kind {
        TombstoneMode::Default => EventKind::Purged,
        TombstoneMode::Erase => EventKind::Erased,
    };
    for (index, event) in events.iter().enumerate() {
        event.validate_fields(marker_kind)?;
        let expected = if index % 2 == 0 {
            opening
        } else {
            EventKind::Retired
        };
        if event.kind != expected {
            return Err(corrupt_state(
                "lifecycle events must alternate strictly from their marker's opening kind",
            ));
        }
    }
    Ok(())
}

/// Public dead-pointer lifecycle record (v2 `events[]`; LC1/LC13). CAS-adjacent
/// but not a CAS object — lives outside `objects/` (05-runtime.md §3.5).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TombstoneRecord {
    pub raw_hash: String,
    pub events: Vec<LifecycleEvent>,
}

impl TombstoneRecord {
    fn validate_structure(&self) -> Result<()> {
        validate_hash("tombstone raw_hash", &self.raw_hash)?;
        validate_event_sequence(&self.events, TombstoneMode::Default)
    }

    /// The current-state event (LC1: active iff its `kind` is `purged`).
    #[must_use]
    pub fn tail(&self) -> &LifecycleEvent {
        self.events.last().expect("validated: events is non-empty")
    }

    #[must_use]
    pub fn is_active(&self) -> bool {
        self.tail().kind == EventKind::Purged
    }
}

/// Fsck-only non-content record for `--erase-tombstone` (v2 `events[]`; LC2).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EraseReceipt {
    pub schema_version: u64,
    pub raw_hash: String,
    pub events: Vec<LifecycleEvent>,
}

impl EraseReceipt {
    fn validate_structure(&self) -> Result<()> {
        if self.schema_version != RECEIPT_SCHEMA_VERSION {
            return Err(corrupt_state("erase receipt schema_version is invalid"));
        }
        validate_hash("erase receipt raw_hash", &self.raw_hash)?;
        validate_event_sequence(&self.events, TombstoneMode::Erase)
    }

    #[must_use]
    pub fn tail(&self) -> &LifecycleEvent {
        self.events.last().expect("validated: events is non-empty")
    }

    #[must_use]
    pub fn is_active(&self) -> bool {
        self.tail().kind == EventKind::Erased
    }
}

fn parse_tombstone_bytes(bytes: &[u8], expected_raw_hash: &str) -> Result<TombstoneRecord> {
    // Syntax and schema stay separate diagnostics: a torn write and a
    // well-formed record of the wrong shape need different operator responses.
    let generic: Value =
        serde_json::from_slice(bytes).map_err(|_| corrupt_state("tombstone has invalid JSON"))?;
    let record: TombstoneRecord = serde_json::from_value(generic)
        .map_err(|_| corrupt_state("tombstone has an invalid strict schema"))?;
    record.validate_structure()?;
    if record.raw_hash != expected_raw_hash {
        return Err(corrupt_state("tombstone identity does not match leaf"));
    }
    Ok(record)
}

fn parse_erase_receipt_bytes(bytes: &[u8], expected_raw_hash: &str) -> Result<EraseReceipt> {
    let generic: Value = serde_json::from_slice(bytes)
        .map_err(|_| corrupt_state("erase receipt has invalid JSON"))?;
    let receipt: EraseReceipt = serde_json::from_value(generic)
        .map_err(|_| corrupt_state("erase receipt has an invalid strict schema"))?;
    receipt.validate_structure()?;
    if receipt.raw_hash != expected_raw_hash {
        return Err(corrupt_state("erase receipt identity does not match leaf"));
    }
    Ok(receipt)
}

/// LC8-LC10: the resolver's single source of truth for "what is this raw_hash
/// right now," aggregated across both markers. A pure function over
/// already-validated tail events — callers (the resolver, fsck) are
/// responsible for LC9's "only validated markers participate" gate before
/// calling this.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CanonicalFinalEvent {
    pub marker_kind: TombstoneMode,
    pub event: LifecycleEvent,
}

/// LC8: canonical final event = the tail event with the greatest
/// `lifecycle_epoch`; on a tie the tombstone wins deterministically. A tail
/// missing its required lifecycle epoch is rejected fail-closed, even if a
/// caller bypasses marker-record structural validation.
#[must_use]
pub fn canonical_final_event(
    tombstone_tail: Option<&LifecycleEvent>,
    receipt_tail: Option<&LifecycleEvent>,
) -> Result<Option<CanonicalFinalEvent>> {
    // Durable-marker reads reject this during structural validation. Keep the
    // pure resolver defensive as well: callers cannot accidentally authorize
    // a malformed event by supplying it directly.
    if tombstone_tail.is_some_and(|event| event.lifecycle_epoch.is_none())
        || receipt_tail.is_some_and(|event| event.lifecycle_epoch.is_none())
    {
        return Err(corrupt_state(
            "canonical lifecycle event is missing its lifecycle_epoch",
        ));
    }

    match (tombstone_tail, receipt_tail) {
        (Some(tombstone), Some(receipt)) => {
            let (Some(tombstone_epoch), Some(receipt_epoch)) =
                (tombstone.lifecycle_epoch, receipt.lifecycle_epoch)
            else {
                return Err(corrupt_state(
                    "canonical lifecycle event is missing its lifecycle_epoch",
                ));
            };
            if receipt_epoch > tombstone_epoch {
                Ok(Some(CanonicalFinalEvent {
                    marker_kind: TombstoneMode::Erase,
                    event: receipt.clone(),
                }))
            } else {
                Ok(Some(CanonicalFinalEvent {
                    marker_kind: TombstoneMode::Default,
                    event: tombstone.clone(),
                }))
            }
        }
        (Some(tombstone), None) => Ok(Some(CanonicalFinalEvent {
            marker_kind: TombstoneMode::Default,
            event: tombstone.clone(),
        })),
        (None, Some(receipt)) => Ok(Some(CanonicalFinalEvent {
            marker_kind: TombstoneMode::Erase,
            event: receipt.clone(),
        })),
        (None, None) => Ok(None),
    }
}

/// LC46/PA43's `closure` item: one `(object_type, hash)` deletion target.
/// `object_type` is one of `"raw"`, `"prepared"`, `"image"`, or `"chunk"`
/// (`hash` is a `chunk_id`, which is itself a canonical `sha256:` hash — see
/// `crate::cas::is_hash`). The full enumeration — including the
/// shared-derived live-reference resolution result for `prepared`/`image` —
/// lives in the [`PurgeClosure`] sidecar (step4b-contract-tests-p2a.md
/// PA43-46, §R ruling #2), not inline in the journal.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ClosureItem {
    pub object_type: String,
    pub hash: String,
}

/// PA43-46 (§R ruling #2): the durable `.kio/purge/journal-closure` sidecar.
/// Holds the full "every object type × hash destined for deletion" enumeration
/// — including the *result* of the shared-derived (`prepared`/`image`)
/// live-reference judgment — computed once, durably written *before* the
/// journal that references it (by content hash, [`PurgeJournal::closure_hash`])
/// is created. A resumed purge reads this sidecar back and reuses its
/// contents verbatim; it never recomputes the live-reference judgment (the
/// same "fixed at `prepared`, never recomputed on resume" principle LC48
/// established for `planned_commit`). Bound to its journal by `purge_id` (an
/// independent check from the content-hash binding — belt and suspenders
/// against a sidecar left by an unrelated purge_id somehow surviving a
/// non-atomic step).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PurgeClosure {
    pub schema_version: u64,
    pub purge_id: String,
    pub items: Vec<ClosureItem>,
    /// Shared-derived (`prepared`/`image`) objects the same live-reference
    /// judgment (fixed here, at `prepared`) decided to *preserve* rather than
    /// delete (a surviving reference from a non-target raw). Kept separate
    /// from `items` — which PA45 requires be exactly the deletion set, no
    /// more and no less — purely so a resumed purge can still report an
    /// accurate `shared_artifacts_preserved` count without a live rescan.
    #[serde(default)]
    pub preserved: Vec<ClosureItem>,
}

const CLOSURE_SCHEMA_VERSION: u64 = 1;

impl PurgeClosure {
    /// Construct and validate a fresh closure for `purge_id`. `items`/
    /// `preserved` need not be pre-sorted; this normalizes (sorts + dedups)
    /// them the same way `PurgeJournal::new` used to normalize the raw-only
    /// closure.
    pub fn new(
        purge_id: impl Into<String>,
        mut items: Vec<ClosureItem>,
        mut preserved: Vec<ClosureItem>,
    ) -> Result<Self> {
        let sort_key = |item: &ClosureItem| (item.object_type.clone(), item.hash.clone());
        items.sort_by_key(sort_key);
        items.dedup();
        preserved.sort_by_key(sort_key);
        preserved.dedup();
        let closure = Self {
            schema_version: CLOSURE_SCHEMA_VERSION,
            purge_id: purge_id.into(),
            items,
            preserved,
        };
        closure.validate()?;
        Ok(closure)
    }

    fn validate(&self) -> Result<()> {
        if self.schema_version != CLOSURE_SCHEMA_VERSION {
            return Err(corrupt_state("purge closure schema_version is invalid"));
        }
        if !crate::scope::is_ulid(&self.purge_id) {
            return Err(corrupt_state("purge closure purge_id must be a ULID"));
        }
        let cap = MAX_PURGE_TARGETS.saturating_mul(8);
        if self.items.len() > cap || self.preserved.len() > cap {
            return Err(corrupt_state("purge closure item count is invalid"));
        }
        Self::validate_sorted_items(&self.items, "purge closure item")?;
        Self::validate_sorted_items(&self.preserved, "purge closure preserved item")?;
        Ok(())
    }

    fn validate_sorted_items(items: &[ClosureItem], label: &str) -> Result<()> {
        let mut previous: Option<(&str, &str)> = None;
        for item in items {
            if item.object_type.is_empty() {
                return Err(corrupt_state(format!("{label} type is empty")));
            }
            validate_hash(&format!("{label} hash"), &item.hash)?;
            let key = (item.object_type.as_str(), item.hash.as_str());
            if previous.is_some_and(|value| value >= key) {
                return Err(corrupt_state(format!(
                    "{label}s must be strictly sorted and de-duplicated"
                )));
            }
            previous = Some(key);
        }
        Ok(())
    }

    /// The subset of `items` for one `object_type` ("raw" / "prepared" /
    /// "image" / "chunk"), as an owned set of hashes/ids.
    #[must_use]
    pub fn hashes_for(&self, object_type: &str) -> BTreeSet<String> {
        Self::hashes_for_in(&self.items, object_type)
    }

    /// The subset of `preserved` for one `object_type` ("prepared" / "image").
    #[must_use]
    pub fn preserved_hashes_for(&self, object_type: &str) -> BTreeSet<String> {
        Self::hashes_for_in(&self.preserved, object_type)
    }

    fn hashes_for_in(items: &[ClosureItem], object_type: &str) -> BTreeSet<String> {
        items
            .iter()
            .filter(|item| item.object_type == object_type)
            .map(|item| item.hash.clone())
            .collect()
    }
}

/// Content hash of a closure's canonical-JSON bytes (RFC 8785, matching
/// `crate::cas::canonical_json_bytes`'s object-hash contract). The journal
/// stores only this hash ([`PurgeJournal::closure_hash`]); the full
/// enumeration lives solely in the sidecar file, read back and verified
/// against this hash before every consumer trusts its contents.
pub fn closure_content_hash(closure: &PurgeClosure) -> Result<String> {
    Ok(crate::cas::hash_bytes(&record_bytes(closure)?))
}

/// LC47: `prepared -> tombstoned -> deleted -> committed`, then `done` (the
/// journal is removed rather than stored as a fifth phase value).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PurgePhase {
    Prepared,
    Tombstoned,
    Deleted,
    Committed,
}

impl PurgePhase {
    const fn next(self) -> Option<Self> {
        match self {
            Self::Prepared => Some(Self::Tombstoned),
            Self::Tombstoned => Some(Self::Deleted),
            Self::Deleted => Some(Self::Committed),
            Self::Committed => None,
        }
    }

    #[must_use]
    pub const fn is_barrier_visible(self) -> bool {
        !matches!(self, Self::Prepared)
    }
}

/// Owner-private resumable transaction state (LC46/LC48). Target hashes are
/// strictly sorted so a retry cannot silently change the aggregate operation.
/// `planned_commit` and `closure_hash` are fixed once, in `prepared`
/// (`PurgeState::begin`), and never recomputed on resume (LC48/LC50). The
/// journal itself carries only `closure_hash` — a content-hash reference to
/// the `.kio/purge/journal-closure` sidecar ([`PurgeClosure`],
/// [`closure_content_hash`]) that holds the actual full enumeration (§R
/// ruling #2). The sidecar is written durably *before* the journal that
/// references it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PurgeJournal {
    pub schema_version: u64,
    pub purge_id: String,
    pub target_raw_hashes: Vec<String>,
    pub reason: PurgeReason,
    pub tombstone_mode: TombstoneMode,
    pub actor: String,
    pub started_at: String,
    pub target_epoch: u64,
    pub closure_hash: String,
    pub planned_commit: String,
    pub phase: PurgePhase,
}

impl PurgeJournal {
    #[allow(clippy::too_many_arguments)]
    fn new(
        mut target_raw_hashes: Vec<String>,
        reason: PurgeReason,
        tombstone_mode: TombstoneMode,
        actor: String,
        started_at: String,
        target_epoch: u64,
        planned_commit: String,
        closure_hash: String,
        purge_id: String,
    ) -> Result<Self> {
        target_raw_hashes.sort();
        target_raw_hashes.dedup();
        let journal = Self {
            schema_version: JOURNAL_SCHEMA_VERSION,
            purge_id,
            target_raw_hashes,
            reason,
            tombstone_mode,
            actor,
            started_at,
            target_epoch,
            closure_hash,
            planned_commit,
            phase: PurgePhase::Prepared,
        };
        journal.validate()?;
        Ok(journal)
    }

    fn validate(&self) -> Result<()> {
        if self.schema_version != JOURNAL_SCHEMA_VERSION {
            return Err(corrupt_state("purge journal schema_version is invalid"));
        }
        if !crate::scope::is_ulid(&self.purge_id) {
            return Err(corrupt_state("purge journal purge_id must be a ULID"));
        }
        if self.actor.is_empty() {
            return Err(corrupt_state("purge journal actor must not be empty"));
        }
        if self.target_raw_hashes.is_empty() || self.target_raw_hashes.len() > MAX_PURGE_TARGETS {
            return Err(corrupt_state("purge journal target count is invalid"));
        }
        let mut previous: Option<&str> = None;
        for raw_hash in &self.target_raw_hashes {
            validate_hash("purge journal target", raw_hash)?;
            if previous.is_some_and(|value| value >= raw_hash.as_str()) {
                return Err(corrupt_state(
                    "purge journal targets must be strictly sorted",
                ));
            }
            previous = Some(raw_hash);
        }
        validate_timestamp("purge journal started_at", &self.started_at)?;
        validate_hash("purge journal planned_commit", &self.planned_commit)?;
        validate_hash("purge journal closure_hash", &self.closure_hash)?;
        Ok(())
    }

    #[must_use]
    pub fn blocks(&self, raw_hash: &str) -> bool {
        self.phase.is_barrier_visible()
            && self
                .target_raw_hashes
                .binary_search_by(|candidate| candidate.as_str().cmp(raw_hash))
                .is_ok()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BeginOutcome {
    Started(PurgeJournal),
    Resumed(PurgeJournal),
    AlreadyComplete(Vec<TombstoneRecord>),
}

#[derive(Debug, Clone)]
pub struct PurgeState {
    kio_dir: PathBuf,
}

/// Result of [`PurgeState::recover_lifecycle_epoch`] (LC43/LC44).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LifecycleEpochRecovery {
    pub value: u64,
    /// `true` when a rollback was detected and the counter was recreated at
    /// `max(...) + 1` — the caller must unconditionally rotate
    /// `index_generation` (LC44).
    pub rotated: bool,
}

impl PurgeState {
    #[must_use]
    pub fn new(kio_dir: impl Into<PathBuf>) -> Self {
        Self {
            kio_dir: kio_dir.into(),
        }
    }

    #[must_use]
    pub fn journal_path(&self) -> PathBuf {
        self.kio_dir.join("purge/in-progress.json")
    }

    /// PA43-46 (§R ruling #2): the `.kio/purge/journal-closure` sidecar path —
    /// a single JSON file, same temp+rename+fsync discipline as the journal
    /// (`write_private_replace`), holding the full closure enumeration that
    /// `PurgeJournal::closure_hash` references by content hash.
    #[must_use]
    pub fn closure_path(&self) -> PathBuf {
        self.kio_dir.join("purge/journal-closure")
    }

    /// Durably write the closure sidecar. The caller must do this *before*
    /// calling [`Self::begin`] on a fresh start, so the journal never
    /// references a closure_hash whose sidecar is not yet durable.
    pub fn write_closure(&self, closure: &PurgeClosure) -> Result<()> {
        closure.validate()?;
        write_private_replace(
            &self.kio_dir,
            &self.closure_path(),
            &closure_bytes(closure)?,
            MAX_PURGE_CLOSURE_BYTES,
        )
    }

    /// Read back the closure sidecar. Callers that trust its contents for a
    /// destructive decision must additionally compare
    /// [`closure_content_hash`] of the result against the active journal's
    /// `closure_hash` (this method only enforces internal structural
    /// validity, not the binding to any particular journal).
    pub fn read_closure(&self) -> Result<Option<PurgeClosure>> {
        let Some(bytes) = read_bounded_regular(&self.closure_path(), MAX_PURGE_CLOSURE_BYTES)?
        else {
            return Ok(None);
        };
        ensure_owner_private(&self.closure_path())?;
        let closure: PurgeClosure = parse_record(&bytes, "purge closure")?;
        closure.validate()?;
        Ok(Some(closure))
    }

    pub fn tombstone_path(&self, raw_hash: &str) -> Result<PathBuf> {
        fanout_path(self.kio_dir.join("tombstones"), raw_hash)
    }

    pub fn erase_receipt_path(&self, raw_hash: &str) -> Result<PathBuf> {
        fanout_path(self.kio_dir.join("purge/erase-receipts"), raw_hash)
    }

    /// `.kio/purge/epoch` (LC39/LC120): the ABA barrier's monotonic counter.
    #[must_use]
    pub fn purge_epoch_path(&self) -> PathBuf {
        self.kio_dir.join("purge/epoch")
    }

    /// `.kio/tombstones/lifecycle-epoch` (LC41/LC120): the lifecycle-event
    /// rotation-detection counter. A distinct file and a distinct counter from
    /// `purge/epoch` (LC41's note: the two must never share storage).
    #[must_use]
    pub fn lifecycle_epoch_path(&self) -> PathBuf {
        self.kio_dir.join("tombstones/lifecycle-epoch")
    }

    /// Start, resume, or recognize an already-completed default purge. The
    /// caller must hold the scope store lock for this and all mutation methods
    /// below. `planned_commit` must already be computed by the caller (LC48:
    /// fixed once, in `prepared`) — this module has no DAG/CAS access.
    /// `closure_hash` (PA43-46, §R ruling #2) must be the content hash
    /// ([`closure_content_hash`]) of a [`PurgeClosure`] the caller has
    /// *already durably written* via [`Self::write_closure`] before calling
    /// this — on a fresh start the sidecar must exist before the journal that
    /// references it can be considered durable; on resume the value is
    /// ignored in favor of the existing journal's own `closure_hash` (the
    /// `Resumed`/`AlreadyComplete` outcomes never look at this parameter).
    #[allow(clippy::too_many_arguments)]
    pub fn begin(
        &self,
        target_raw_hashes: Vec<String>,
        reason: PurgeReason,
        tombstone_mode: TombstoneMode,
        actor: impl Into<String>,
        started_at: impl Into<String>,
        target_epoch: u64,
        planned_commit: impl Into<String>,
        closure_hash: impl Into<String>,
        purge_id: impl Into<String>,
    ) -> Result<BeginOutcome> {
        let desired = PurgeJournal::new(
            target_raw_hashes,
            reason,
            tombstone_mode,
            actor.into(),
            started_at.into(),
            target_epoch,
            planned_commit.into(),
            closure_hash.into(),
            purge_id.into(),
        )?;
        if let Some(existing) = self.read_journal()? {
            if existing.target_raw_hashes == desired.target_raw_hashes
                && existing.reason == desired.reason
                && existing.tombstone_mode == desired.tombstone_mode
            {
                return Ok(BeginOutcome::Resumed(existing));
            }
            return Err(incomplete_state(
                "another purge journal is active for a different target",
            ));
        }

        // LC58/LC59 vs LC1 tension (recorded here since it is a real spec
        // tension, not a coding choice made silently): LC1's structural
        // invariant is that `events[]` alternates strictly with no repeated
        // kind, and LC59's own precondition establishes "already active" via
        // this exact self-tail check. LC58/LC59's prose reads as if
        // re-purging a tombstone that is *already* active (never retired)
        // should still append a second, directly-consecutive `purged` event —
        // but that would violate LC1's alternation invariant for the very
        // same record. This module resolves the tension in favor of LC1 (the
        // invariant many other contracts — canonical-final-event computation,
        // fsck, the resolver — depend on structurally): re-purging a raw_hash
        // that is already actively tombstoned is `AlreadyComplete` (no new
        // event; M-ruling #2's "no reason-match requirement" is honored by
        // *not rejecting* on a different reason here, short of literally
        // recording it). A re-purge of a *retired* tombstone (LC58's
        // unambiguous, alternation-safe case: retired -> purged) does append
        // (`append_tombstone_event` below, called by the CLI orchestration
        // layer once the journal reaches its terminal-publish phase).
        let mut existing_tombstones = Vec::new();
        for raw_hash in &desired.target_raw_hashes {
            if let Some(record) = self.read_tombstone(raw_hash)? {
                if record.is_active() {
                    existing_tombstones.push(record);
                }
            }
        }
        if !existing_tombstones.is_empty()
            && existing_tombstones.len() == desired.target_raw_hashes.len()
        {
            // R23-11 (05-runtime.md §3.5 L942, "検証失敗の marker は入口を
            // 問わず (fsck・resolver・再 purge) ... corruption とする"): a
            // re-purge that is about to short-circuit as `AlreadyComplete` --
            // reporting success without appending anything -- must not trust
            // each active tombstone's `purged` claim blindly. Bounded (O(1)
            // per marker, no ref-reachability walk -- matching the resolver-
            // weight contract, since this is a per-invocation check, not
            // fsck's own bulk scan).
            for record in &existing_tombstones {
                verify_marker_binding_bounded(
                    &self.kio_dir,
                    &record.raw_hash,
                    record.tail(),
                    &desired.started_at,
                )?;
            }
            return Ok(BeginOutcome::AlreadyComplete(existing_tombstones));
        }

        write_private_replace(
            &self.kio_dir,
            &self.journal_path(),
            &journal_bytes(&desired)?,
            MAX_PURGE_JOURNAL_BYTES,
        )?;
        Ok(BeginOutcome::Started(desired))
    }

    pub fn read_journal(&self) -> Result<Option<PurgeJournal>> {
        let Some(bytes) = read_bounded_regular(&self.journal_path(), MAX_PURGE_JOURNAL_BYTES)?
        else {
            return Ok(None);
        };
        ensure_owner_private(&self.journal_path())?;
        let journal: PurgeJournal = parse_record(&bytes, "purge journal")?;
        journal.validate()?;
        Ok(Some(journal))
    }

    pub fn advance_phase(&self, expected: &PurgeJournal, next: PurgePhase) -> Result<PurgeJournal> {
        let current = self.require_current(expected)?;
        if current.phase == next {
            return Ok(current);
        }
        if current.phase.next() != Some(next) {
            return Err(corrupt_state("purge journal phase transition is invalid"));
        }
        let mut updated = current;
        updated.phase = next;
        updated.validate()?;
        write_private_replace(
            &self.kio_dir,
            &self.journal_path(),
            &journal_bytes(&updated)?,
            MAX_PURGE_JOURNAL_BYTES,
        )?;
        Ok(updated)
    }

    pub fn barrier_blocks(&self, raw_hash: &str) -> Result<bool> {
        validate_hash("purge barrier lookup", raw_hash)?;
        Ok(self
            .read_journal()?
            .is_some_and(|journal| journal.blocks(raw_hash)))
    }

    /// §I read barrier (LC52-57): does an active journal exist at all, without
    /// regard to which raw_hash it targets. Distinct from
    /// [`Self::barrier_blocks`], which is the narrower per-raw_hash ingest gate.
    pub fn read_barrier_active(&self) -> Result<bool> {
        Ok(self.read_journal()?.is_some())
    }

    pub fn read_tombstone(&self, raw_hash: &str) -> Result<Option<TombstoneRecord>> {
        validate_hash("tombstone lookup", raw_hash)?;
        read_bounded_regular(&self.tombstone_path(raw_hash)?, MAX_PURGE_RECORD_BYTES)?
            .map(|bytes| parse_tombstone_bytes(&bytes, raw_hash))
            .transpose()
    }

    pub fn read_erase_receipt(&self, raw_hash: &str) -> Result<Option<EraseReceipt>> {
        validate_hash("erase receipt lookup", raw_hash)?;
        let path = self.erase_receipt_path(raw_hash)?;
        let Some(bytes) = read_bounded_regular(&path, MAX_PURGE_RECORD_BYTES)? else {
            return Ok(None);
        };
        Ok(Some(parse_erase_receipt_bytes(&bytes, raw_hash)?))
    }

    /// Append one lifecycle event to `raw_hash`'s tombstone, creating the
    /// record if absent (the initial `purged` case) or appending to it
    /// (retire, re-purge — LC58). Performs the LC5 one-shot legacy migration
    /// as a side effect of the read-modify-write. Idempotent for a retried
    /// operation that already landed (`events_are_equivalent`), so a
    /// crash-resumed journal replay never double-appends. `event.epoch` must
    /// already be set by the caller for `purged`; `event.lifecycle_epoch` is
    /// always stamped here from the pre-incremented counter (LC26).
    pub fn append_tombstone_event(
        &self,
        raw_hash: &str,
        mut event: LifecycleEvent,
    ) -> Result<TombstoneRecord> {
        validate_hash("tombstone lookup", raw_hash)?;
        let mut record = match self.read_tombstone(raw_hash)? {
            Some(existing) => existing,
            None => TombstoneRecord {
                raw_hash: raw_hash.to_owned(),
                events: Vec::new(),
            },
        };
        if record
            .events
            .last()
            .is_some_and(|tail| events_are_equivalent(tail, &event))
        {
            return Ok(record);
        }
        event.lifecycle_epoch = Some(self.increment_lifecycle_epoch()?);
        record.events.push(event);
        record.validate_structure()?;
        write_private_replace(
            &self.kio_dir,
            &self.tombstone_path(raw_hash)?,
            &record_bytes(&record)?,
            MAX_PURGE_RECORD_BYTES,
        )?;
        Ok(record)
    }

    /// Append one lifecycle event to `raw_hash`'s erase receipt. See
    /// [`Self::append_tombstone_event`].
    pub fn append_erase_receipt_event(
        &self,
        raw_hash: &str,
        mut event: LifecycleEvent,
    ) -> Result<EraseReceipt> {
        validate_hash("erase receipt lookup", raw_hash)?;
        let mut receipt = match self.read_erase_receipt(raw_hash)? {
            Some(existing) => existing,
            None => EraseReceipt {
                schema_version: RECEIPT_SCHEMA_VERSION,
                raw_hash: raw_hash.to_owned(),
                events: Vec::new(),
            },
        };
        if receipt
            .events
            .last()
            .is_some_and(|tail| events_are_equivalent(tail, &event))
        {
            return Ok(receipt);
        }
        event.lifecycle_epoch = Some(self.increment_lifecycle_epoch()?);
        receipt.events.push(event);
        receipt.validate_structure()?;
        write_private_replace(
            &self.kio_dir,
            &self.erase_receipt_path(raw_hash)?,
            &record_bytes(&receipt)?,
            MAX_PURGE_RECORD_BYTES,
        )?;
        Ok(receipt)
    }

    /// LC22-LC26/LC33: retire an active tombstone by appending `retired`. A
    /// no-op (returns the record unchanged) if the tombstone does not exist or
    /// is not currently active — this makes the resurrection-scan caller free
    /// to call it speculatively for every candidate raw_hash.
    pub fn retire_tombstone(
        &self,
        raw_hash: &str,
        resurrection_commit: &str,
        at: &str,
        actor: &str,
    ) -> Result<Option<TombstoneRecord>> {
        let Some(existing) = self.read_tombstone(raw_hash)? else {
            return Ok(None);
        };
        if !existing.is_active() {
            return Ok(Some(existing));
        }
        let event = LifecycleEvent::retired(at, resurrection_commit, actor);
        Ok(Some(self.append_tombstone_event(raw_hash, event)?))
    }

    /// LC33: the erase-receipt analogue of [`Self::retire_tombstone`]. The
    /// receipt file is never removed — only appended to (U14's reversal of the
    /// old "remove on republish" rule).
    pub fn retire_erase_receipt(
        &self,
        raw_hash: &str,
        resurrection_commit: &str,
        at: &str,
        actor: &str,
    ) -> Result<Option<EraseReceipt>> {
        let Some(existing) = self.read_erase_receipt(raw_hash)? else {
            return Ok(None);
        };
        if !existing.is_active() {
            return Ok(Some(existing));
        }
        let event = LifecycleEvent::retired(at, resurrection_commit, actor);
        Ok(Some(self.append_erase_receipt_event(raw_hash, event)?))
    }

    /// LC22-LC26: retire every active tombstone/erase-receipt among
    /// `raw_hashes` against the same `resurrection_commit`, as one
    /// locked-mutation batch. Returns the raw hashes that were actually
    /// retired (empty = nothing to do, no lifecycle-epoch/counter churn).
    pub fn retire_resurrected(
        &self,
        raw_hashes: &BTreeSet<String>,
        resurrection_commit: &str,
        at: &str,
        actor: &str,
    ) -> Result<BTreeSet<String>> {
        let mut retired = BTreeSet::new();
        for raw_hash in raw_hashes {
            if self
                .read_tombstone(raw_hash)?
                .is_some_and(|record| record.is_active())
            {
                self.retire_tombstone(raw_hash, resurrection_commit, at, actor)?;
                retired.insert(raw_hash.clone());
            }
            if self
                .read_erase_receipt(raw_hash)?
                .is_some_and(|receipt| receipt.is_active())
            {
                self.retire_erase_receipt(raw_hash, resurrection_commit, at, actor)?;
                retired.insert(raw_hash.clone());
            }
        }
        Ok(retired)
    }

    pub fn abort_before_barrier(&self, expected: &PurgeJournal) -> Result<()> {
        let current = self.require_current(expected)?;
        if current.phase != PurgePhase::Prepared {
            return Err(incomplete_state(
                "a visible purge barrier cannot be aborted",
            ));
        }
        quarantine_then_unlink(&self.journal_path(), MAX_PURGE_JOURNAL_BYTES)
    }

    /// `done` (LC51): fixed order — (1) advance `.kio/purge/epoch` to
    /// `target_epoch`, (2) only then remove the journal. The caller must have
    /// already reached `PurgePhase::Committed` (marker + deletion + commit/ref
    /// publish all durable).
    pub fn finish(&self, expected: &PurgeJournal) -> Result<()> {
        let current = self.require_current(expected)?;
        if current.phase != PurgePhase::Committed {
            return Err(incomplete_state(
                "purge cannot finish before the commit phase completes",
            ));
        }
        self.write_purge_epoch(current.target_epoch)?;
        quarantine_then_unlink(&self.journal_path(), MAX_PURGE_JOURNAL_BYTES)
    }

    fn require_current(&self, expected: &PurgeJournal) -> Result<PurgeJournal> {
        let current = self
            .read_journal()?
            .ok_or_else(|| incomplete_state("purge journal is missing"))?;
        if &current != expected {
            return Err(incomplete_state("purge journal changed since it was read"));
        }
        Ok(current)
    }

    // -- purge/epoch (ABA barrier counter; LC39/LC40/LC51) --------------------

    /// LC39: fail-closed read for read-barrier callers. Missing or malformed
    /// content is always an error — never a silently-assumed default.
    pub fn read_purge_epoch(&self) -> Result<u64> {
        self.read_purge_epoch_lenient()?
            .ok_or_else(purge_epoch_fail_closed)
    }

    fn read_purge_epoch_lenient(&self) -> Result<Option<u64>> {
        let Some(bytes) = read_bounded_regular(&self.purge_epoch_path(), MAX_EPOCH_COUNTER_BYTES)?
        else {
            return Ok(None);
        };
        Ok(parse_counter(&bytes))
    }

    fn write_purge_epoch(&self, value: u64) -> Result<()> {
        write_private_replace(
            &self.kio_dir,
            &self.purge_epoch_path(),
            value.to_string().as_bytes(),
            MAX_EPOCH_COUNTER_BYTES,
        )
    }

    /// LC40: writer-side recovery. A healthy existing counter is returned
    /// unchanged; otherwise the counter is recreated at `recovery_target`
    /// (the caller has already computed the priority order: active journal's
    /// `target_epoch`, else `max_recorded_purge_epoch() + 1`, else `1`).
    pub fn ensure_purge_epoch(&self, recovery_target: u64) -> Result<u64> {
        if let Some(value) = self.read_purge_epoch_lenient()? {
            return Ok(value);
        }
        self.write_purge_epoch(recovery_target)?;
        Ok(recovery_target)
    }

    /// LC40(b): scan every tombstone/erase-receipt event for the greatest
    /// recorded `epoch` (legacy rows, which never record one, are skipped —
    /// not treated as 0, since they must not participate in this max).
    pub fn max_recorded_purge_epoch(&self) -> Result<Option<u64>> {
        let mut max_epoch = None;
        self.scan_all_events(|event| {
            if let Some(epoch) = event.epoch {
                max_epoch = Some(max_epoch.map_or(epoch, |current: u64| current.max(epoch)));
            }
        })?;
        Ok(max_epoch)
    }

    // -- tombstones/lifecycle-epoch (rotation-detection counter; LC41-45) -----

    fn read_lifecycle_epoch_lenient(&self) -> Result<Option<u64>> {
        let Some(bytes) =
            read_bounded_regular(&self.lifecycle_epoch_path(), MAX_EPOCH_COUNTER_BYTES)?
        else {
            return Ok(None);
        };
        Ok(parse_counter(&bytes))
    }

    fn write_lifecycle_epoch(&self, value: u64) -> Result<()> {
        write_private_replace(
            &self.kio_dir,
            &self.lifecycle_epoch_path(),
            value.to_string().as_bytes(),
            MAX_EPOCH_COUNTER_BYTES,
        )
    }

    /// LC26: increment-and-fsync the counter, returning the new value that the
    /// event about to be appended must stamp as its `lifecycle_epoch`. The
    /// counter update happens first (durably) so a crash between the two
    /// leaves `counter > last_lifecycle_epoch`, which write-side recovery
    /// (`recover_lifecycle_epoch`) detects.
    fn increment_lifecycle_epoch(&self) -> Result<u64> {
        let current = self.read_lifecycle_epoch_lenient()?.unwrap_or(0);
        let next = current
            .checked_add(1)
            .ok_or_else(|| corrupt_state("lifecycle epoch counter overflow"))?;
        self.write_lifecycle_epoch(next)?;
        Ok(next)
    }

    /// §I checkpoint 1 (LC53): the current `.kio/tombstones/lifecycle-epoch`
    /// counter value, captured as the read barrier's baseline for the later
    /// checkpoint-2 comparison (LC54, via [`Self::lifecycle_epoch_matches`]
    /// called with the value this returns). A missing file reads as 0 (LC41:
    /// never-created means zero lifecycle events have ever been recorded —
    /// this is the same lenient-default semantics `lifecycle_epoch_matches`
    /// and `recover_lifecycle_epoch` already use, not the fail-closed rule
    /// LC39 requires of `purge/epoch`).
    pub fn read_lifecycle_epoch(&self) -> Result<u64> {
        Ok(self.read_lifecycle_epoch_lenient()?.unwrap_or(0))
    }

    /// LC45/LC54: read-side check. `last_lifecycle_epoch` is either the
    /// caller's `index_metadata` value (owned by kio-index, outside this
    /// crate — LC45's read-command rollback check) or a §I checkpoint-1
    /// baseline this same struct captured via [`Self::read_lifecycle_epoch`]
    /// (LC54's checkpoint-2 unchanged-since-start check) — both are "does the
    /// counter still equal X" and share this one comparison. Any mismatch is
    /// retryable (`KIO-E-INDEX-REBUILDING-001`-class for LC45,
    /// `KIO-E-PURGE-JOURNAL-ACTIVE-001` for LC54 — same numeric check, two
    /// different callers/error codes; see docs/05-runtime.md §3.5's own note
    /// not to conflate the two).
    pub fn lifecycle_epoch_matches(&self, last_lifecycle_epoch: u64) -> Result<bool> {
        Ok(self.read_lifecycle_epoch_lenient()?.unwrap_or(0) == last_lifecycle_epoch)
    }

    /// LC43/LC44: writer-side rollback detection + recovery.
    /// `last_lifecycle_epoch` and `max_event_lifecycle_epoch` are the two
    /// comparands of the spec's `max(...)` term — the former lives in SQLite
    /// (supplied by the caller), the latter is available in this crate via
    /// [`Self::max_recorded_lifecycle_epoch`].
    pub fn recover_lifecycle_epoch(
        &self,
        last_lifecycle_epoch: u64,
        max_event_lifecycle_epoch: u64,
    ) -> Result<LifecycleEpochRecovery> {
        let current = self.read_lifecycle_epoch_lenient()?.unwrap_or(0);
        let baseline = last_lifecycle_epoch.max(max_event_lifecycle_epoch);
        if current < baseline {
            let recreated = baseline
                .checked_add(1)
                .ok_or_else(|| corrupt_state("lifecycle epoch counter overflow"))?;
            self.write_lifecycle_epoch(recreated)?;
            Ok(LifecycleEpochRecovery {
                value: recreated,
                rotated: true,
            })
        } else {
            Ok(LifecycleEpochRecovery {
                value: current,
                rotated: false,
            })
        }
    }

    /// LC43(b): scan every tombstone/erase-receipt event for the greatest
    /// recorded `lifecycle_epoch` (0 if no marker has any event at all).
    pub fn max_recorded_lifecycle_epoch(&self) -> Result<u64> {
        let mut max_value = 0_u64;
        self.scan_all_events(|event| {
            if let Some(value) = event.lifecycle_epoch {
                max_value = max_value.max(value);
            }
        })?;
        Ok(max_value)
    }

    /// Walk every tombstone and erase-receipt marker under this scope and
    /// visit each of their events. Used by the epoch-recovery max-scans. A
    /// malformed marker aborts the scan (fail-closed: undercounting a max used
    /// for monotonic-recreation could reissue an epoch value).
    fn scan_all_events(&self, mut visit: impl FnMut(&LifecycleEvent)) -> Result<()> {
        for path in walk_fanout_leaves(&self.kio_dir.join("tombstones"))? {
            if let Some(bytes) = read_bounded_regular(&path, MAX_PURGE_RECORD_BYTES)? {
                let raw_hash = leaf_raw_hash(&path);
                let record = parse_tombstone_bytes(&bytes, &raw_hash)?;
                record.events.iter().for_each(&mut visit);
            }
        }
        for path in walk_fanout_leaves(&self.kio_dir.join("purge/erase-receipts"))? {
            if let Some(bytes) = read_bounded_regular(&path, MAX_PURGE_RECORD_BYTES)? {
                let raw_hash = leaf_raw_hash(&path);
                let receipt = parse_erase_receipt_bytes(&bytes, &raw_hash)?;
                receipt.events.iter().for_each(&mut visit);
            }
        }
        Ok(())
    }
}

/// Reconstruct the canonical `sha256:<64hex>` raw_hash from a fanout leaf
/// path's file name (03-data-model.md §2: the physical leaf is the bare
/// 64-hex digest, so the logical hash is that name single-prefixed).
fn leaf_raw_hash(path: &Path) -> String {
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("");
    format!("sha256:{name}")
}

/// Enumerate every leaf file under a two-level fanout directory
/// (`base/xx/yy/<leaf>`), tolerating a missing `base` (nothing recorded yet)
/// or non-directory siblings (e.g. `tombstones/lifecycle-epoch`, a flat file
/// directly under `tombstones/`, is skipped by the top-level directory
/// check). R23-23: only `NotFound` is tolerated at every level — any other
/// `read_dir` error (permission denied, I/O error, a path component that
/// changed into a non-directory mid-walk) is propagated fail-closed rather
/// than silently treated as "nothing here." A silently-skipped fanout bucket
/// previously caused the epoch-recovery max-scans
/// ([`PurgeState::max_recorded_purge_epoch`]/[`PurgeState::max_recorded_lifecycle_epoch`])
/// to undercount, letting a rollback-recovery step reissue an already-used
/// epoch value (an ABA collision) instead of surfacing the I/O failure.
fn walk_fanout_leaves(base: &Path) -> Result<Vec<PathBuf>> {
    let mut leaves = Vec::new();
    let top_entries = match fs::read_dir(base) {
        Ok(entries) => entries,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(leaves),
        Err(error) => return Err(state_io(error)),
    };
    for top in top_entries {
        let top = top.map_err(state_io)?;
        if !top.file_type().map_err(state_io)?.is_dir() {
            continue;
        }
        let mid_entries = match fs::read_dir(top.path()) {
            Ok(entries) => entries,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => return Err(state_io(error)),
        };
        for mid in mid_entries {
            let mid = mid.map_err(state_io)?;
            if !mid.file_type().map_err(state_io)?.is_dir() {
                continue;
            }
            let leaf_entries = match fs::read_dir(mid.path()) {
                Ok(entries) => entries,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                Err(error) => return Err(state_io(error)),
            };
            for leaf in leaf_entries {
                let leaf = leaf.map_err(state_io)?;
                if leaf.file_type().map_err(state_io)?.is_file() {
                    leaves.push(leaf.path());
                }
            }
        }
    }
    Ok(leaves)
}

/// R23-11 (05-runtime.md §3.5 L934/L942, 10-operations.md §7.5.1): the pure
/// half of the marker "semantic validity" contract shared by every consumer
/// that trusts a `purged`/`erased` tail event to hide content -- fsck,
/// re-purge, and the resolver. A structurally well-formed
/// ([`LifecycleEvent::validate_fields`]) but semantically fabricated marker
/// (an `in_commit` that is not `commit_type=purged`, does not list this
/// raw_hash in `purged_raws`, or whose `at` disagrees with the commit's
/// `created_at` / is from the future) must not be trusted to hide genuine
/// content.
///
/// Given an already-resolved `commit`, this performs every check that does
/// not require a DAG walk. Full ref-reachability against the scope's refs --
/// the remaining piece of 05 §934's contract -- is intentionally NOT here:
/// fsck (`verify_objects.rs`) already has a bounded all-parent walk built
/// for its own purposes and checks reachability itself, on top of this
/// function (via its own pre-scanned commit map), rather than this crate
/// (which deliberately has no DAG-walk machinery of its own -- see this
/// module's top doc comment) re-deriving one. [`verify_marker_binding_bounded`]
/// is the resolver/re-purge-weight wrapper that fetches `commit` with a
/// single verified CAS read (no walk) and calls this.
pub fn verify_marker_binding(
    raw_hash: &str,
    event: &LifecycleEvent,
    commit: &crate::dag::CommitObject,
    now: &str,
) -> Result<()> {
    if commit.commit_type != crate::dag::CommitType::Purged {
        return Err(corrupt_state(
            "lifecycle event in_commit commit_type is not purged",
        ));
    }
    if !commit.purged_raws.iter().any(|hash| hash == raw_hash) {
        return Err(corrupt_state(
            "lifecycle event in_commit purged_raws does not include this raw_hash",
        ));
    }
    if commit.created_at != event.at {
        return Err(corrupt_state(
            "lifecycle event at does not equal commit created_at",
        ));
    }
    if timestamp_is_after(&event.at, now)? {
        return Err(corrupt_state("lifecycle event at is in the future"));
    }
    Ok(())
}

/// R23-11: resolver/re-purge weight wrapper -- one verified CAS read of
/// `event.in_commit` (bounded, O(1); no ref-reachability walk, see
/// [`verify_marker_binding`]'s doc comment), then the shared checks. A
/// no-op for `retired` (it re-affirms the marker inactive; its own
/// `resurrection_commit` ancestry/tree-leaf check is fsck's
/// `validate_retired_event`, gated on "tree 存置時に限り" -- not an O(1)
/// resolver-weight check, so it is out of scope here). Callers: the
/// resolver's `read_tombstone` wrapper (`main.rs`) and [`PurgeState::begin`]'s
/// `AlreadyComplete` short-circuit (a re-purge target whose tombstone is
/// already active).
pub fn verify_marker_binding_bounded(
    kio_dir: &Path,
    raw_hash: &str,
    event: &LifecycleEvent,
    now: &str,
) -> Result<()> {
    if !matches!(event.kind, EventKind::Purged | EventKind::Erased) {
        return Ok(());
    }
    let object = crate::cas::ObjectStore::new(kio_dir)
        .read_by_hash(&event.in_commit)
        .map_err(|_| {
            corrupt_state("lifecycle event in_commit does not resolve to a verified commit object")
        })?;
    if object.kind != crate::cas::ObjectKind::Commit {
        return Err(corrupt_state(
            "lifecycle event in_commit does not identify a commit object",
        ));
    }
    let commit: crate::dag::CommitObject = serde_json::from_slice(&object.bytes)
        .map_err(|_| corrupt_state("lifecycle event in_commit is not a valid commit object"))?;
    commit
        .validate()
        .map_err(|_| corrupt_state("lifecycle event in_commit is not a valid commit object"))?;
    verify_marker_binding(raw_hash, event, &commit, now)
}

/// Digit-exact fractional-second "is `left` after `right`" comparison,
/// shared with fsck's own `in_commit`/`at` semantic checks
/// (`verify_objects.rs`'s `validate_purge_or_erase_in_commit`, which calls
/// this as `kio_core::purge::timestamp_is_after` instead of keeping its own
/// copy). Naive string comparison is wrong here: `"...T00:00:00.5Z"` and
/// `"...T00:00:00.50Z"` denote the same instant but differ as strings, and
/// `"...T00:00:01Z"` (no fraction) sorts *before* `"...T00:00:00.999999Z"`
/// under plain `str` `Ord` (`.` < `Z` in ASCII) even though it is later.
/// Comparing the whole-second part numerically (via
/// [`crate::scope::parse_utc_seconds`]) and the fractional part digit-by-
/// digit (zero-padded on the shorter side) avoids both traps.
pub fn timestamp_is_after(left: &str, right: &str) -> Result<bool> {
    let (left_seconds, left_fraction) = timestamp_parts(left)?;
    let (right_seconds, right_fraction) = timestamp_parts(right)?;
    if left_seconds != right_seconds {
        return Ok(left_seconds > right_seconds);
    }
    let width = left_fraction.len().max(right_fraction.len());
    for index in 0..width {
        let left_digit = left_fraction.as_bytes().get(index).copied().unwrap_or(b'0');
        let right_digit = right_fraction
            .as_bytes()
            .get(index)
            .copied()
            .unwrap_or(b'0');
        if left_digit != right_digit {
            return Ok(left_digit > right_digit);
        }
    }
    Ok(false)
}

fn timestamp_parts(value: &str) -> Result<(i64, &str)> {
    let Some(body) = value.strip_suffix('Z') else {
        return Err(corrupt_state("timestamp is not canonical UTC"));
    };
    let (seconds_form, fraction) = match body.split_once('.') {
        Some((seconds, fraction))
            if !fraction.is_empty() && fraction.bytes().all(|byte| byte.is_ascii_digit()) =>
        {
            (format!("{seconds}Z"), fraction)
        }
        Some(_) => return Err(corrupt_state("timestamp fractional seconds are invalid")),
        None => (value.to_owned(), ""),
    };
    let seconds = crate::scope::parse_utc_seconds(&seconds_form)
        .ok_or_else(|| corrupt_state("timestamp is not canonical UTC"))?;
    Ok((seconds, fraction))
}

fn parse_counter(bytes: &[u8]) -> Option<u64> {
    std::str::from_utf8(bytes).ok()?.trim().parse::<u64>().ok()
}

fn journal_bytes(journal: &PurgeJournal) -> Result<Vec<u8>> {
    let bytes = record_bytes(journal)?;
    if bytes.len() as u64 > MAX_PURGE_JOURNAL_BYTES {
        return Err(corrupt_state("purge journal exceeds its size limit"));
    }
    Ok(bytes)
}

fn closure_bytes(closure: &PurgeClosure) -> Result<Vec<u8>> {
    let bytes = record_bytes(closure)?;
    if bytes.len() as u64 > MAX_PURGE_CLOSURE_BYTES {
        return Err(corrupt_state("purge closure exceeds its size limit"));
    }
    Ok(bytes)
}

fn record_bytes<T: Serialize>(record: &T) -> Result<Vec<u8>> {
    canonical_json_bytes(
        &serde_json::to_value(record).map_err(|error| corrupt_state(error.to_string()))?,
    )
}

fn parse_record<T: DeserializeOwned>(bytes: &[u8], label: &str) -> Result<T> {
    serde_json::from_slice(bytes)
        .map_err(|_| corrupt_state(format!("{label} has an invalid strict schema")))
}

fn validate_hash(label: &str, value: &str) -> Result<()> {
    if is_hash(value) {
        Ok(())
    } else {
        Err(corrupt_state(format!("{label} is not a canonical hash")))
    }
}

fn validate_timestamp(label: &str, value: &str) -> Result<()> {
    if is_valid_utc(value) {
        Ok(())
    } else {
        Err(corrupt_state(format!("{label} is not canonical UTC")))
    }
}

fn is_valid_utc(value: &str) -> bool {
    let Some(body) = value.strip_suffix('Z') else {
        return false;
    };
    let datetime = match body.split_once('.') {
        Some((head, fraction))
            if !fraction.is_empty() && fraction.bytes().all(|byte| byte.is_ascii_digit()) =>
        {
            head
        }
        Some(_) => return false,
        None => body,
    };
    let bytes = datetime.as_bytes();
    if bytes.len() != 19
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
    {
        return false;
    }
    for index in [0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18] {
        if !bytes[index].is_ascii_digit() {
            return false;
        }
    }
    let field = |start: usize, end: usize| datetime[start..end].parse::<u32>().unwrap_or(u32::MAX);
    let year = field(0, 4);
    let month = field(5, 7);
    let day = field(8, 10);
    let hour = field(11, 13);
    let minute = field(14, 16);
    let second = field(17, 19);
    if !(1..=12).contains(&month) {
        return false;
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let max_day = match month {
        4 | 6 | 9 | 11 => 30,
        2 if leap => 29,
        2 => 28,
        _ => 31,
    };
    (1..=max_day).contains(&day) && hour <= 23 && minute <= 59 && second <= 59
}

fn read_bounded_regular(path: &Path, max_bytes: u64) -> Result<Option<Vec<u8>>> {
    let before = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) if error.kind() == std::io::ErrorKind::NotADirectory => {
            return Err(corrupt_state("purge state ancestor is not a directory"));
        }
        Err(error) => return Err(state_io(error)),
    };
    if before.file_type().is_symlink() || !before.file_type().is_file() || before.len() > max_bytes
    {
        return Err(corrupt_state("purge state is not a bounded regular file"));
    }
    reject_multiple_links(&before)?;

    let mut options = OpenOptions::new();
    options.read(true);
    configure_no_follow(&mut options);
    let mut file = options.open(path).map_err(state_io)?;
    let opened = file.metadata().map_err(state_io)?;
    let after = fs::symlink_metadata(path).map_err(state_io)?;
    #[cfg(windows)]
    let same_identity = {
        let mut verification_options = OpenOptions::new();
        verification_options.read(true);
        configure_no_follow(&mut verification_options);
        let verification = verification_options.open(path).map_err(state_io)?;
        same_windows_private_file(&file, &verification)
    };
    #[cfg(not(windows))]
    let same_identity = same_file_identity(&opened, &after);
    if after.file_type().is_symlink() || !after.file_type().is_file() || !same_identity {
        return Err(corrupt_state("purge state identity changed during open"));
    }
    reject_multiple_links(&opened)?;
    let mut bytes = Vec::new();
    std::io::Read::by_ref(&mut file)
        .take(max_bytes.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(state_io)?;
    if bytes.len() as u64 > max_bytes {
        return Err(corrupt_state("purge state exceeds its size limit"));
    }
    Ok(Some(bytes))
}

/// Durable full-file replace: temp write -> fsync -> atomic rename -> parent
/// directory fsync (LC4's primitive, [04-pipeline.md §1.1]-equivalent). Used
/// for the journal and, since Step4b, for tombstone/erase-receipt records too
/// (their `events[]` grows over the record's lifetime, unlike the old
/// write-once-then-immutable terminal record).
fn write_private_replace(kio_dir: &Path, path: &Path, bytes: &[u8], max_bytes: u64) -> Result<()> {
    if bytes.len() as u64 > max_bytes {
        return Err(corrupt_state("purge record exceeds its size limit"));
    }
    let parent = ensure_secure_parent(kio_dir, path)?;
    if path.exists() {
        read_bounded_regular(path, max_bytes)?
            .ok_or_else(|| corrupt_state("purge state disappeared"))?;
    }
    let (temp_path, mut temp) = create_private_temp(&parent)?;
    let result = (|| -> Result<()> {
        temp.write_all(bytes).map_err(state_io)?;
        temp.sync_all().map_err(state_io)?;
        drop(temp);
        replace_file(&temp_path, path)?;
        // R23-07: propagate a failed parent-directory fsync instead of
        // treating it as success -- callers (marker append, epoch-counter
        // write, journal phase advance) must not proceed to the next phase
        // (object deletion, journal removal) on an unconfirmed rename.
        sync_directory(&parent).map_err(state_io)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp_path);
    }
    result
}

fn ensure_secure_parent(kio_dir: &Path, path: &Path) -> Result<PathBuf> {
    let root_metadata = fs::symlink_metadata(kio_dir).map_err(state_io)?;
    if !directory_is_real(kio_dir, &root_metadata)? {
        return Err(corrupt_state("Kio root is not a real directory"));
    }
    let root = kio_dir.canonicalize().map_err(state_io)?;
    let parent = path
        .parent()
        .ok_or_else(|| corrupt_state("purge state path has no parent"))?;
    let relative = parent
        .strip_prefix(kio_dir)
        .map_err(|_| corrupt_state("purge state path escapes Kio root"))?;
    let mut current = kio_dir.to_path_buf();
    for component in relative.components() {
        let Component::Normal(component) = component else {
            return Err(corrupt_state("purge state path is not normalized"));
        };
        current.push(component);
        match fs::create_dir(&current) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(state_io(error)),
        }
        let metadata = fs::symlink_metadata(&current).map_err(state_io)?;
        if !directory_is_real(&current, &metadata)? {
            return Err(corrupt_state(
                "purge state ancestor is not a real directory",
            ));
        }
        let canonical = current.canonicalize().map_err(state_io)?;
        if !canonical.starts_with(&root) {
            return Err(corrupt_state("purge state ancestor escapes Kio root"));
        }
    }
    Ok(parent.to_path_buf())
}

fn directory_is_real(path: &Path, metadata: &fs::Metadata) -> Result<bool> {
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Ok(false);
    }
    #[cfg(windows)]
    {
        return crate::cas::windows_directory_is_real(path).map_err(state_io);
    }
    #[cfg(not(windows))]
    {
        let _ = path;
        Ok(true)
    }
}

#[cfg(not(windows))]
fn replace_file(source: &Path, destination: &Path) -> Result<()> {
    fs::rename(source, destination).map_err(state_io)
}

#[cfg(windows)]
fn replace_file(source: &Path, destination: &Path) -> Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
    };

    let source = source
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let destination = destination
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    // SAFETY: both UTF-16 buffers are NUL-terminated and remain alive for the call.
    let moved = unsafe {
        MoveFileExW(
            source.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if moved == 0 {
        Err(state_io(std::io::Error::last_os_error()))
    } else {
        Ok(())
    }
}

fn create_private_temp(parent: &Path) -> Result<(PathBuf, File)> {
    for _ in 0..32 {
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let path = parent.join(format!(
            ".purge-tmp-{}-{nanos}-{sequence}",
            std::process::id()
        ));
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match options.open(&path) {
            Ok(file) => return Ok((path, file)),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(state_io(error)),
        }
    }
    Err(state_io(std::io::Error::new(
        std::io::ErrorKind::AlreadyExists,
        "could not allocate purge temp file",
    )))
}

fn quarantine_then_unlink(path: &Path, max_bytes: u64) -> Result<()> {
    let Some(expected_bytes) = read_bounded_regular(path, max_bytes)? else {
        return Ok(());
    };
    let parent = path
        .parent()
        .ok_or_else(|| corrupt_state("purge state path has no parent"))?;
    let quarantine = parent.join(format!(
        ".purge-remove-{}-{}",
        std::process::id(),
        TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::rename(path, &quarantine).map_err(state_io)?;
    match read_bounded_regular(&quarantine, max_bytes) {
        Ok(Some(actual_bytes)) if actual_bytes == expected_bytes => {}
        Ok(_) => {
            restore_private_no_clobber(parent, path, &expected_bytes);
            return Err(corrupt_state("purge state changed before removal"));
        }
        Err(error) => {
            restore_private_no_clobber(parent, path, &expected_bytes);
            return Err(error);
        }
    }
    fs::remove_file(&quarantine).map_err(state_io)?;
    // R23-07: an unpropagated fsync failure here previously let `finish()`
    // (05 §3.5's `done` step: epoch bump then journal removal) and
    // `abort_before_barrier()` report success while the journal's removal
    // was not yet durable -- exactly the "journal 不在 × 旧 epoch" ABA
    // window §3.5's fixed `done` ordering exists to close.
    sync_directory(parent).map_err(state_io)?;
    Ok(())
}

/// Best-effort fail-closed recovery for a remove race. Never overwrites a path
/// another actor published while the state file was quarantined. R23-07:
/// `sync_directory` now returns a `Result`; this function's own contract
/// (best-effort, caller already discards `result`) is unchanged, but the
/// call itself must use `?` rather than the old bare void call so a failed
/// fsync is at least captured in `result` (still discarded below) instead of
/// silently type-checking as success.
fn restore_private_no_clobber(parent: &Path, path: &Path, expected_bytes: &[u8]) {
    let Ok((temp_path, mut temp)) = create_private_temp(parent) else {
        return;
    };
    let result = (|| -> std::io::Result<()> {
        temp.write_all(expected_bytes)?;
        temp.sync_all()?;
        drop(temp);
        match fs::hard_link(&temp_path, path) {
            Ok(()) => sync_directory(parent)?,
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error),
        }
        Ok(())
    })();
    let _ = fs::remove_file(&temp_path);
    let _ = result;
}

fn ensure_owner_private(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = fs::metadata(path).map_err(state_io)?.permissions().mode();
        if mode & 0o077 != 0 {
            return Err(corrupt_state("purge journal is not owner-private"));
        }
    }
    let _ = path;
    Ok(())
}

#[cfg(unix)]
fn reject_multiple_links(metadata: &fs::Metadata) -> Result<()> {
    use std::os::unix::fs::MetadataExt;
    if metadata.nlink() == 1 {
        Ok(())
    } else {
        Err(corrupt_state("purge state has an unexpected hardlink"))
    }
}

#[cfg(windows)]
fn reject_multiple_links(_metadata: &fs::Metadata) -> Result<()> {
    // File-handle identity and link count are checked together below.
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn reject_multiple_links(_metadata: &fs::Metadata) -> Result<()> {
    Ok(())
}

#[cfg(unix)]
fn configure_no_follow(options: &mut OpenOptions) {
    use std::os::unix::fs::OpenOptionsExt;
    #[cfg(any(target_os = "linux", target_os = "android"))]
    options.custom_flags(0x20_800);
    #[cfg(any(
        target_os = "macos",
        target_os = "ios",
        target_os = "freebsd",
        target_os = "openbsd",
        target_os = "netbsd",
        target_os = "dragonfly"
    ))]
    options.custom_flags(0x104);
    let _ = options;
}

#[cfg(windows)]
fn configure_no_follow(options: &mut OpenOptions) {
    use std::os::windows::fs::OpenOptionsExt;
    options.custom_flags(0x0020_0000);
}

#[cfg(not(any(unix, windows)))]
fn configure_no_follow(_options: &mut OpenOptions) {}

#[cfg(unix)]
fn same_file_identity(left: &fs::Metadata, right: &fs::Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    left.dev() == right.dev() && left.ino() == right.ino()
}

#[cfg(not(any(unix, windows)))]
fn same_file_identity(left: &fs::Metadata, right: &fs::Metadata) -> bool {
    left.len() == right.len() && left.modified().ok() == right.modified().ok()
}

#[cfg(windows)]
fn same_windows_private_file(left: &File, right: &File) -> bool {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION,
    };

    fn information(file: &File) -> Option<BY_HANDLE_FILE_INFORMATION> {
        let mut information = BY_HANDLE_FILE_INFORMATION::default();
        // SAFETY: `file` owns a valid handle and the output pointer is writable.
        let ok = unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut information) };
        (ok != 0).then_some(information)
    }

    let (Some(left), Some(right)) = (information(left), information(right)) else {
        return false;
    };
    let left_index = (u64::from(left.nFileIndexHigh) << 32) | u64::from(left.nFileIndexLow);
    let right_index = (u64::from(right.nFileIndexHigh) << 32) | u64::from(right.nFileIndexLow);
    const FILE_ATTRIBUTE_DIRECTORY: u32 = 0x10;
    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
    let forbidden = FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT;
    left.dwVolumeSerialNumber == right.dwVolumeSerialNumber
        && left_index == right_index
        && left.nNumberOfLinks == 1
        && right.nNumberOfLinks == 1
        && left.dwFileAttributes & forbidden == 0
        && right.dwFileAttributes & forbidden == 0
}

/// Fsync a directory so a prior rename/unlink within it is durable (R23-07,
/// 05-runtime.md §3.5 L834-836 "temp 書込 → file fsync → atomic rename →
/// 親 directory fsync" and L843-845 "journal を除去 + directory fsync").
/// Must propagate failure to its caller: silently swallowing a failed
/// open/fsync here let [`write_private_replace`] report success for a
/// tombstone/erase-receipt marker append whose directory entry was never
/// actually made durable, and let [`quarantine_then_unlink`] report success
/// for a journal removal with the same gap — either opens exactly the
/// "markerless absence" / "journal reappears after crash" window §3.5
/// exists to close (LC49's ordering guarantee already depended on this
/// being durable; only the failure path was silently discarded).
///
/// `pub(crate)` because the object store needs the identical guarantee for its
/// own post-`remove_file` entries: [`crate::cas`] carried two hand-rolled
/// copies of the pre-R23-07 `if let Ok(dir) = File::open(parent)` shape, which
/// reproduced both defects one layer down — the discarded POSIX fsync, and the
/// permanent Windows no-op. They now call this, so the two arms have exactly
/// one definition to keep correct.
#[cfg(not(windows))]
pub(crate) fn sync_directory(path: &Path) -> std::io::Result<()> {
    File::open(path)?.sync_all()
}

/// Windows counterpart. **Windows has no directory fsync**, so this arm cannot
/// make the same durability promise as the POSIX one above.
///
/// The POSIX body does not merely degrade here -- it fails outright, every
/// time. `File::open` on a directory returns ERROR_ACCESS_DENIED (os error 5)
/// because Rust does not pass `FILE_FLAG_BACKUP_SEMANTICS`, which is what
/// getting a directory handle requires. Opening one by hand does not rescue
/// it: `sync_all` calls `FlushFileBuffers`, which wants write access that a
/// directory handle cannot carry. So the three purge call sites
/// (`write_private_replace`, `quarantine_then_unlink`,
/// `restore_private_no_clobber`) turned every purge-journal write on Windows
/// into `KIO-E-STORE-IO-001`, which is what four tests were failing on.
/// The ordering §3.5 buys from the POSIX fsync comes from NTFS's own metadata
/// journalling instead; that is a weaker promise and is recorded as such in
/// 05-runtime.md §3.5.
///
/// The [`crate::cas`] callers would have hit that same wall the moment their
/// swallowed `let _ =` became a propagated `?` — on Windows the old block was
/// not merely lossy but a permanent no-op — which is why they must adopt this
/// arm and not just the POSIX one.
///
/// What survives is the *fail-closed* half of R23-07: a parent that is missing
/// or is not a directory still surfaces to the caller rather than
/// type-checking as success. That is the failure this arm can actually see.
#[cfg(windows)]
pub(crate) fn sync_directory(path: &Path) -> std::io::Result<()> {
    if fs::metadata(path)?.is_dir() {
        Ok(())
    } else {
        Err(std::io::Error::new(
            std::io::ErrorKind::NotADirectory,
            "sync_directory expects a directory",
        ))
    }
}

fn corrupt_state(message: impl Into<String>) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        message,
        json!({ "component": "purge_state" }),
        ExitCode::Failure,
    )
}

fn incomplete_state(message: impl Into<String>) -> KioError {
    KioError::new(
        "KIO-E-PURGE-INCOMPLETE-001",
        message,
        json!({ "component": "purge_state" }),
        ExitCode::PartialFailure,
    )
}

fn purge_epoch_fail_closed() -> KioError {
    KioError::new(
        "KIO-E-PURGE-JOURNAL-ACTIVE-001",
        "purge epoch counter is missing or invalid",
        json!({ "component": "purge_epoch" }),
        ExitCode::PartialFailure,
    )
}

fn state_io(error: std::io::Error) -> KioError {
    KioError::new(
        "KIO-E-STORE-IO-001",
        error.to_string(),
        json!({ "component": "purge_state" }),
        ExitCode::Failure,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cas::hash_bytes;

    const NOW: &str = "2026-07-13T00:00:00Z";
    const LATER: &str = "2026-07-14T00:00:00Z";

    fn setup() -> (tempfile::TempDir, PurgeState) {
        let dir = tempfile::tempdir().unwrap();
        let kio_dir = dir.path().join(".kio");
        fs::create_dir(&kio_dir).unwrap();
        (dir, PurgeState::new(kio_dir))
    }

    fn raw() -> String {
        hash_bytes(b"private raw")
    }

    fn commit() -> String {
        hash_bytes(b"purged commit")
    }

    fn other_commit() -> String {
        hash_bytes(b"republication commit")
    }

    fn purge_id() -> String {
        crate::scope::new_ulid(Path::new("/tmp/purge-id-seed"))
    }

    /// PA43-46 test helper: build+validate a single-raw closure, durably write
    /// it as the sidecar (mirroring the real CLI orchestration's "write the
    /// sidecar, THEN begin() referencing its hash" order), and return its
    /// content hash.
    fn test_closure_hash(state: &PurgeState, purge_id: &str, raw_hash: &str) -> String {
        let closure = PurgeClosure::new(
            purge_id.to_owned(),
            vec![ClosureItem {
                object_type: "raw".to_owned(),
                hash: raw_hash.to_owned(),
            }],
            Vec::new(),
        )
        .unwrap();
        state.write_closure(&closure).unwrap();
        closure_content_hash(&closure).unwrap()
    }

    fn started(state: &PurgeState) -> PurgeJournal {
        let id = purge_id();
        let closure_hash = test_closure_hash(state, &id, &raw());
        match state
            .begin(
                vec![raw()],
                PurgeReason::Legal,
                TombstoneMode::Default,
                "user",
                NOW,
                1,
                commit(),
                closure_hash,
                id,
            )
            .unwrap()
        {
            BeginOutcome::Started(journal) => journal,
            other => panic!("unexpected begin outcome: {other:?}"),
        }
    }

    /// R23-11 test helper: a non-purged commit object (this module's tests
    /// otherwise never construct real `dag::CommitObject` values -- they
    /// exercise only the marker/journal storage layer, which is
    /// deliberately CAS/DAG-agnostic; see the module's top doc comment).
    fn test_commit(kind: crate::dag::CommitType, created_at: &str) -> crate::dag::CommitObject {
        crate::dag::CommitObject::new(
            hash_bytes(b"tree"),
            Vec::new(),
            created_at.to_owned(),
            "marker test".to_owned(),
            hash_bytes(b"toollock"),
            crate::dag::CommitStats {
                files_added: 0,
                files_modified: 0,
                files_deleted: 0,
            },
            kind,
        )
        .unwrap()
    }

    /// R23-11 test helper: a `commit_type=purged` commit object naming
    /// `purged_raws`.
    fn test_purged_commit(created_at: &str, purged_raws: Vec<String>) -> crate::dag::CommitObject {
        crate::dag::CommitObject::new_purged(
            hash_bytes(b"tree"),
            Vec::new(),
            created_at.to_owned(),
            "marker test".to_owned(),
            hash_bytes(b"toollock"),
            crate::dag::CommitStats {
                files_added: 0,
                files_modified: 0,
                files_deleted: 0,
            },
            purged_raws,
        )
        .unwrap()
    }

    /// R23-11 test helper: durably write [`test_purged_commit`]'s output as a
    /// real CAS commit object and return its hash, for exercising
    /// [`verify_marker_binding_bounded`]'s single verified CAS read.
    fn write_purged_commit_object(
        kio_dir: &Path,
        created_at: &str,
        raw_hashes: Vec<String>,
    ) -> String {
        let commit = test_purged_commit(created_at, raw_hashes);
        let bytes = canonical_json_bytes(&serde_json::to_value(&commit).unwrap()).unwrap();
        let hash = hash_bytes(&bytes);
        crate::cas::ObjectStore::new(kio_dir)
            .write_object_bytes(crate::cas::ObjectKind::Commit, &hash, &bytes)
            .unwrap();
        hash
    }

    #[test]
    fn lc1_tombstone_events_are_closed_kind_and_active_iff_tail_purged() {
        let (_dir, state) = setup();
        let event = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        let record = state.append_tombstone_event(&raw(), event).unwrap();
        assert!(record.is_active());
        assert_eq!(record.tail().kind, EventKind::Purged);

        let retired = state
            .retire_tombstone(&raw(), &other_commit(), LATER, "user")
            .unwrap()
            .unwrap();
        assert!(!retired.is_active());
        assert_eq!(retired.tail().kind, EventKind::Retired);
        assert_eq!(retired.events.len(), 2);
    }

    #[test]
    fn lc2_erase_receipt_events_start_erased_and_are_schema_version_2() {
        let (_dir, state) = setup();
        let event = LifecycleEvent::erased(NOW, commit(), PurgeReason::Privacy, "user", 1);
        let receipt = state.append_erase_receipt_event(&raw(), event).unwrap();
        assert_eq!(receipt.schema_version, 2);
        assert!(receipt.is_active());
        assert_eq!(receipt.tail().kind, EventKind::Erased);
    }

    #[test]
    fn lc3_required_field_matrix_rejects_missing_reason_and_resurrection_commit() {
        let mut event = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        event.reason = None;
        assert_eq!(
            event
                .validate_fields(TombstoneMode::Default)
                .unwrap_err()
                .error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );

        let mut retired = LifecycleEvent::retired(NOW, commit(), "user");
        retired.resurrection_commit = None;
        assert!(retired.validate_fields(TombstoneMode::Default).is_err());
    }

    #[test]
    fn lifecycle_marker_reads_reject_events_missing_required_epochs() {
        let (_dir, state) = setup();
        let raw_hash = raw();
        let path = state.tombstone_path(&raw_hash).unwrap();
        fs::create_dir_all(path.parent().unwrap()).unwrap();

        // Older records that omit `lifecycle_epoch` are malformed rather than
        // being ordered as epoch zero by the resolver.
        let missing_lifecycle_epoch = TombstoneRecord {
            raw_hash: raw_hash.clone(),
            events: vec![LifecycleEvent::purged(
                NOW,
                commit(),
                PurgeReason::Legal,
                "user",
                1,
            )],
        };
        fs::write(&path, record_bytes(&missing_lifecycle_epoch).unwrap()).unwrap();
        assert_eq!(
            state.read_tombstone(&raw_hash).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );

        // The purge event's own epoch is independently required.
        let missing_purge_epoch = TombstoneRecord {
            raw_hash: raw_hash.clone(),
            events: vec![LifecycleEvent {
                epoch: None,
                lifecycle_epoch: Some(1),
                ..LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1)
            }],
        };
        fs::write(&path, record_bytes(&missing_purge_epoch).unwrap()).unwrap();
        assert_eq!(
            state.read_tombstone(&raw_hash).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
    }

    #[test]
    fn lc4_torn_json_is_store_corrupt_fail_closed() {
        let (_dir, state) = setup();
        let event = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        let record = state.append_tombstone_event(&raw(), event).unwrap();
        let path = state.tombstone_path(&record.raw_hash).unwrap();
        let mut bytes = fs::read(&path).unwrap();
        bytes.truncate(bytes.len() / 2);
        fs::write(&path, bytes).unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
    }

    #[test]
    fn lc8_lc9_lc10_canonical_final_event_picks_max_lifecycle_epoch_tombstone_tie_break() {
        let purged10 = LifecycleEvent {
            lifecycle_epoch: Some(10),
            ..LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1)
        };
        let retired11 = LifecycleEvent {
            lifecycle_epoch: Some(11),
            ..LifecycleEvent::retired(LATER, other_commit(), "user")
        };
        let canonical = canonical_final_event(Some(&purged10), Some(&retired11))
            .unwrap()
            .unwrap();
        assert_eq!(canonical.marker_kind, TombstoneMode::Erase);
        assert_eq!(canonical.event.kind, EventKind::Retired);

        // Equal valid lifecycle epochs deterministically choose the tombstone.
        let tied_tombstone = LifecycleEvent {
            lifecycle_epoch: Some(12),
            ..LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1)
        };
        let tied_receipt = LifecycleEvent {
            lifecycle_epoch: Some(12),
            ..LifecycleEvent::erased(NOW, commit(), PurgeReason::Legal, "user", 1)
        };
        let canonical = canonical_final_event(Some(&tied_tombstone), Some(&tied_receipt))
            .unwrap()
            .unwrap();
        assert_eq!(canonical.marker_kind, TombstoneMode::Default);

        // Direct callers cannot authorize a malformed tail either: the
        // resolver fail-closes before considering one-marker or two-marker
        // ordering.
        let missing_tombstone_epoch =
            LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        assert!(canonical_final_event(Some(&missing_tombstone_epoch), None).is_err());

        let missing_receipt_epoch =
            LifecycleEvent::erased(NOW, commit(), PurgeReason::Legal, "user", 1);
        assert!(canonical_final_event(None, Some(&missing_receipt_epoch)).is_err());

        let valid_receipt = LifecycleEvent {
            lifecycle_epoch: Some(13),
            ..LifecycleEvent::erased(NOW, commit(), PurgeReason::Legal, "user", 1)
        };
        assert!(
            canonical_final_event(Some(&missing_tombstone_epoch), Some(&valid_receipt)).is_err()
        );

        assert!(canonical_final_event(None, None).unwrap().is_none());
    }

    #[test]
    fn lc15_lc19_v1_and_v2_share_one_validator_and_enforce_transition_grammar() {
        // Foreign kind: an `erased` event cannot appear in a tombstone.
        let events = vec![LifecycleEvent::erased(
            NOW,
            commit(),
            PurgeReason::Legal,
            "user",
            1,
        )];
        assert!(validate_event_sequence(&events, TombstoneMode::Default).is_err());

        // Two purged in a row (no interleaved retired).
        let events = vec![
            LifecycleEvent {
                lifecycle_epoch: Some(1),
                ..LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1)
            },
            LifecycleEvent {
                lifecycle_epoch: Some(2),
                ..LifecycleEvent::purged(LATER, other_commit(), PurgeReason::Legal, "user", 2)
            },
        ];
        assert!(validate_event_sequence(&events, TombstoneMode::Default).is_err());
    }

    #[test]
    fn lc22_lc23_resurrection_retires_and_lc24_crash_leaves_tombstone_active() {
        let (_dir, state) = setup();
        let event = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        state.append_tombstone_event(&raw(), event).unwrap();

        // "Crash before retire": tombstone stays active, safe-side resolution.
        assert!(state.read_tombstone(&raw()).unwrap().unwrap().is_active());

        let retired = state
            .retire_resurrected(&BTreeSet::from([raw()]), &other_commit(), LATER, "user")
            .unwrap();
        assert_eq!(retired, BTreeSet::from([raw()]));
        let record = state.read_tombstone(&raw()).unwrap().unwrap();
        assert!(!record.is_active());
        assert_eq!(
            record.tail().resurrection_commit.as_deref(),
            Some(other_commit().as_str())
        );
    }

    #[test]
    fn lc25_lc26_retire_stamps_strictly_increasing_lifecycle_epoch() {
        let (_dir, state) = setup();
        let event = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        let record = state.append_tombstone_event(&raw(), event).unwrap();
        let first_epoch = record.tail().lifecycle_epoch.unwrap();

        let retired = state
            .retire_tombstone(&raw(), &other_commit(), LATER, "user")
            .unwrap()
            .unwrap();
        let second_epoch = retired.tail().lifecycle_epoch.unwrap();
        assert!(second_epoch > first_epoch);
        assert_eq!(
            state.read_lifecycle_epoch_lenient().unwrap(),
            Some(second_epoch)
        );
    }

    #[test]
    fn lc33_retire_erase_receipt_appends_and_never_deletes_the_file() {
        let (_dir, state) = setup();
        let event = LifecycleEvent::erased(NOW, commit(), PurgeReason::Privacy, "user", 1);
        state.append_erase_receipt_event(&raw(), event).unwrap();
        assert!(state.erase_receipt_path(&raw()).unwrap().exists());

        state
            .retire_erase_receipt(&raw(), &other_commit(), LATER, "user")
            .unwrap();
        assert!(state.erase_receipt_path(&raw()).unwrap().exists());
        let receipt = state.read_erase_receipt(&raw()).unwrap().unwrap();
        assert_eq!(receipt.events.len(), 2);
        assert!(!receipt.is_active());
    }

    #[test]
    fn lc39_lc40_purge_epoch_is_fail_closed_and_recovers_by_priority() {
        let (_dir, state) = setup();
        assert_eq!(
            state.read_purge_epoch().unwrap_err().error_code(),
            "KIO-E-PURGE-JOURNAL-ACTIVE-001"
        );
        let recovered = state.ensure_purge_epoch(7).unwrap();
        assert_eq!(recovered, 7);
        assert_eq!(state.read_purge_epoch().unwrap(), 7);
        // A healthy existing counter is untouched by a later recovery call.
        assert_eq!(state.ensure_purge_epoch(99).unwrap(), 7);
    }

    #[test]
    fn lc41_purge_epoch_and_lifecycle_epoch_are_independent_counters() {
        let (_dir, state) = setup();
        state.write_purge_epoch(5).unwrap();
        let event = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        state.append_tombstone_event(&raw(), event).unwrap();
        state
            .retire_tombstone(&raw(), &other_commit(), LATER, "user")
            .unwrap();
        state
            .retire_tombstone(&raw(), &other_commit(), LATER, "user")
            .unwrap(); // no-op: already retired
        assert_eq!(state.read_purge_epoch().unwrap(), 5);
        assert!(state.read_lifecycle_epoch_lenient().unwrap().unwrap() > 0);
    }

    #[test]
    fn lc42_index_metadata_shape_is_the_caller_side_concern() {
        // Structural placeholder: index_metadata/index_generation live in
        // kio-index (see crates/kio-index/src/fts.rs), which this crate cannot
        // depend on. This test only documents the boundary.
    }

    #[test]
    fn lc43_lc44_lifecycle_epoch_rollback_recreates_at_max_plus_one() {
        let (_dir, state) = setup();
        state.write_lifecycle_epoch(3).unwrap();
        let outcome = state.recover_lifecycle_epoch(5, 4).unwrap();
        assert!(outcome.rotated);
        assert_eq!(outcome.value, 6);
        assert_eq!(state.read_lifecycle_epoch_lenient().unwrap(), Some(6));

        // No rollback: counter already at/above the baseline.
        let outcome = state.recover_lifecycle_epoch(6, 6).unwrap();
        assert!(!outcome.rotated);
        assert_eq!(outcome.value, 6);
    }

    #[test]
    fn lc45_read_side_lifecycle_epoch_mismatch_is_detected_both_directions() {
        let (_dir, state) = setup();
        state.write_lifecycle_epoch(5).unwrap();
        assert!(state.lifecycle_epoch_matches(5).unwrap());
        assert!(!state.lifecycle_epoch_matches(4).unwrap());
        assert!(!state.lifecycle_epoch_matches(6).unwrap());
    }

    #[test]
    fn lc46_lc47_journal_carries_new_fields_and_phases_advance_in_order() {
        let (_dir, state) = setup();
        let journal = started(&state);
        assert_eq!(journal.phase, PurgePhase::Prepared);
        assert!(!journal.purge_id.is_empty());
        assert_eq!(journal.actor, "user");
        assert_eq!(journal.target_epoch, 1);
        assert!(is_hash(&journal.closure_hash));
        assert_eq!(journal.planned_commit, commit());

        let tombstoned = state
            .advance_phase(&journal, PurgePhase::Tombstoned)
            .unwrap();
        assert_eq!(
            state
                .advance_phase(&tombstoned, PurgePhase::Committed)
                .unwrap_err()
                .error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
        let deleted = state
            .advance_phase(&tombstoned, PurgePhase::Deleted)
            .unwrap();
        let committed = state
            .advance_phase(&deleted, PurgePhase::Committed)
            .unwrap();
        assert_eq!(committed.phase, PurgePhase::Committed);
    }

    #[test]
    fn lc48_closure_and_planned_commit_are_fixed_at_prepared_and_unchanged_on_resume() {
        let (_dir, state) = setup();
        let journal = started(&state);
        // A resumed `begin` call is deliberately fed a DIFFERENT (bogus, never
        // written) closure_hash — proving the resumed outcome ignores it
        // entirely and returns the original journal's own closure_hash
        // unchanged (LC48's "fixed once, never recomputed on resume"
        // extended to the closure reference).
        let bogus_closure_hash = hash_bytes(b"a closure_hash that was never written");
        let resumed = match state
            .begin(
                vec![raw()],
                PurgeReason::Legal,
                TombstoneMode::Default,
                "user",
                NOW,
                1,
                commit(),
                bogus_closure_hash,
                journal.purge_id.clone(),
            )
            .unwrap()
        {
            BeginOutcome::Resumed(resumed) => resumed,
            other => panic!("unexpected begin outcome: {other:?}"),
        };
        assert_eq!(resumed.closure_hash, journal.closure_hash);
        assert_eq!(resumed.planned_commit, journal.planned_commit);

        // The sidecar the original `started()` wrote is still there, still
        // matches the journal's closure_hash, and its contents (the single
        // raw target) are exactly what PA43 requires be enumerated.
        let closure = state.read_closure().unwrap().unwrap();
        assert_eq!(
            closure_content_hash(&closure).unwrap(),
            journal.closure_hash
        );
        assert_eq!(closure.hashes_for("raw"), BTreeSet::from([raw()]));
    }

    #[test]
    fn lc49_marker_is_durable_before_journal_reaches_deleted() {
        let (_dir, state) = setup();
        let journal = started(&state);
        let tombstoned = state
            .advance_phase(&journal, PurgePhase::Tombstoned)
            .unwrap();
        let event = LifecycleEvent::purged(
            &journal.started_at,
            &journal.planned_commit,
            journal.reason,
            &journal.actor,
            journal.target_epoch,
        );
        state.append_tombstone_event(&raw(), event).unwrap();
        assert!(state.read_tombstone(&raw()).unwrap().unwrap().is_active());
        // Deletion (out of this module's scope) would happen only after this
        // point in the CLI orchestration layer.
        let _ = state
            .advance_phase(&tombstoned, PurgePhase::Deleted)
            .unwrap();
    }

    #[test]
    fn lc51_done_updates_epoch_before_removing_the_journal() {
        let (_dir, state) = setup();
        let journal = started(&state);
        assert_eq!(
            state.finish(&journal).unwrap_err().error_code(),
            "KIO-E-PURGE-INCOMPLETE-001"
        );
        let tombstoned = state
            .advance_phase(&journal, PurgePhase::Tombstoned)
            .unwrap();
        let deleted = state
            .advance_phase(&tombstoned, PurgePhase::Deleted)
            .unwrap();
        let committed = state
            .advance_phase(&deleted, PurgePhase::Committed)
            .unwrap();
        state.finish(&committed).unwrap();
        assert!(!state.journal_path().exists());
        assert_eq!(state.read_purge_epoch().unwrap(), 1);
    }

    #[test]
    fn lc58_lc59_re_purge_of_a_retired_tombstone_appends_a_new_purged_event_regardless_of_reason() {
        let (_dir, state) = setup();
        let first = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        state.append_tombstone_event(&raw(), first).unwrap();
        state
            .retire_tombstone(&raw(), &other_commit(), LATER, "user")
            .unwrap();

        // §M ruling #2: no reason-match requirement for re-purge. This is the
        // alternation-safe case (LC1: retired -> purged); see `begin()`'s
        // doc comment for the separate "still active" sub-case this module
        // resolves in favor of LC1's structural invariant.
        let third = LifecycleEvent::purged(LATER, other_commit(), PurgeReason::Privacy, "user", 2);
        let record = state.append_tombstone_event(&raw(), third).unwrap();
        assert_eq!(record.events.len(), 3);
        assert_eq!(record.events[0].reason, Some(PurgeReason::Legal));
        assert_eq!(record.events[2].reason, Some(PurgeReason::Privacy));
        assert!(record.is_active());
    }

    #[test]
    fn lc59_re_purging_a_still_active_tombstone_is_already_complete_not_a_second_purged_event() {
        let (dir, state) = setup();
        let kio_dir = dir.path().join(".kio");
        // R23-11: `begin()`'s `AlreadyComplete` short-circuit now
        // semantically validates the active tombstone's tail before
        // trusting it, so `in_commit` must resolve to a real
        // `commit_type=purged` commit naming this raw_hash (unlike every
        // other test in this module, which uses the bare, unbacked
        // `commit()`/`other_commit()` hash literals since they never reach
        // this check).
        let purge_commit = write_purged_commit_object(&kio_dir, NOW, vec![raw()]);
        let first = LifecycleEvent::purged(NOW, &purge_commit, PurgeReason::Legal, "user", 1);
        state.append_tombstone_event(&raw(), first).unwrap();

        // Judgment uses the tombstone's own tail (still `purged`), not a
        // cross-marker canonical final event (§C) — LC59's stated basis.
        // `AlreadyComplete` never touches the closure sidecar, so this
        // closure_hash is deliberately never written anywhere.
        let outcome = state
            .begin(
                vec![raw()],
                PurgeReason::Privacy,
                TombstoneMode::Default,
                "user",
                LATER,
                2,
                other_commit(),
                hash_bytes(b"unused closure_hash: already-complete short-circuits first"),
                purge_id(),
            )
            .unwrap();
        assert!(matches!(outcome, BeginOutcome::AlreadyComplete(_)));
        // No new event was appended — LC1's alternation invariant holds.
        assert_eq!(
            state.read_tombstone(&raw()).unwrap().unwrap().events.len(),
            1
        );
    }

    #[test]
    fn r23_11_begin_already_complete_rejects_a_semantically_fabricated_tombstone() {
        let (_dir, state) = setup();
        // The tombstone's `in_commit` (`commit()`) is a bare hash literal
        // that was never durably written as a CAS commit object at all —
        // AUD-09/A-07's "structurally valid but semantically fabricated
        // marker" scenario. Before R23-11, `begin()`'s `AlreadyComplete`
        // short-circuit trusted the tail event's `is_active()` alone and
        // reported success without ever checking whether `in_commit` names
        // a real, matching `commit_type=purged` commit.
        let first = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        state.append_tombstone_event(&raw(), first).unwrap();

        let error = state
            .begin(
                vec![raw()],
                PurgeReason::Privacy,
                TombstoneMode::Default,
                "user",
                LATER,
                2,
                other_commit(),
                hash_bytes(b"unused closure_hash: rejected before it would matter"),
                purge_id(),
            )
            .unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
    }

    #[test]
    fn r23_11_verify_marker_binding_checks_type_membership_at_and_future() {
        let target_raw = raw();
        let purged = test_purged_commit(NOW, vec![target_raw.clone()]);
        let event = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        assert!(verify_marker_binding(&target_raw, &event, &purged, LATER).is_ok());

        // Wrong commit_type: not commit_type=purged.
        let manual = test_commit(crate::dag::CommitType::Manual, NOW);
        assert!(verify_marker_binding(&target_raw, &event, &manual, LATER).is_err());

        // purged_raws does not include this raw_hash (forged-in_commit
        // defense — 03-data-model.md §8).
        let unrelated_raw = hash_bytes(b"unrelated raw");
        let other_raw_only = test_purged_commit(NOW, vec![unrelated_raw]);
        assert!(verify_marker_binding(&target_raw, &event, &other_raw_only, LATER).is_err());

        // `at` does not equal commit.created_at.
        let mismatched_at = LifecycleEvent::purged(LATER, commit(), PurgeReason::Legal, "user", 1);
        assert!(verify_marker_binding(&target_raw, &mismatched_at, &purged, LATER).is_err());

        // `at` is in the future relative to the fixed invocation `now`.
        assert!(
            verify_marker_binding(&target_raw, &event, &purged, "2026-07-12T23:59:59Z").is_err()
        );
    }

    #[test]
    fn r23_11_verify_marker_binding_bounded_reads_cas_and_skips_retired() {
        let (dir, _state) = setup();
        let kio_dir = dir.path().join(".kio");
        let target_raw = raw();
        let real_commit = write_purged_commit_object(&kio_dir, NOW, vec![target_raw.clone()]);

        let valid = LifecycleEvent::purged(NOW, &real_commit, PurgeReason::Legal, "user", 1);
        assert!(verify_marker_binding_bounded(&kio_dir, &target_raw, &valid, LATER).is_ok());

        // `in_commit` names a hash with no CAS object at all.
        let dangling = LifecycleEvent::purged(NOW, commit(), PurgeReason::Legal, "user", 1);
        assert_eq!(
            verify_marker_binding_bounded(&kio_dir, &target_raw, &dangling, LATER)
                .unwrap_err()
                .error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );

        // `retired` is out of scope for this bounded check (its own
        // resurrection_commit/tree-leaf validation is fsck-only) — proven
        // with a dangling `resurrection_commit` hash: if the kind guard did
        // not skip the CAS read entirely, this would fail the same way
        // `dangling` does above.
        let retired = LifecycleEvent::retired(NOW, commit(), "user");
        assert!(verify_marker_binding_bounded(&kio_dir, &target_raw, &retired, LATER).is_ok());
    }

    #[test]
    fn r23_11_timestamp_is_after_compares_fractional_seconds_numerically() {
        // Naive string comparison would get both of these backwards: "01Z"
        // (no fraction) vs ".999999Z" sorts '.'  < 'Z' in plain `str` `Ord`,
        // and "0.5" vs "0.50" differ as strings despite being equal.
        assert!(timestamp_is_after("2026-07-13T00:00:01Z", "2026-07-13T00:00:00.999999Z").unwrap());
        assert!(
            !timestamp_is_after("2026-07-13T00:00:00.999999Z", "2026-07-13T00:00:01Z").unwrap()
        );
        assert!(!timestamp_is_after("2026-07-13T00:00:00.5Z", "2026-07-13T00:00:00.50Z").unwrap());
        assert!(timestamp_is_after("2026-07-13T00:00:00.51Z", "2026-07-13T00:00:00.50Z").unwrap());
    }

    #[test]
    fn malformed_extra_field_wrong_leaf_and_oversize_fail_closed() {
        let (_dir, state) = setup();
        let path = state.tombstone_path(&raw()).unwrap();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(
            &path,
            serde_json::to_vec(&json!({
                "raw_hash": raw(),
                "purged_at": NOW,
                "purged_reason": "legal",
                "purged_in_commit": commit(),
                "extra": true,
            }))
            .unwrap(),
        )
        .unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );

        fs::remove_file(&path).unwrap();
        let other = hash_bytes(b"other");
        let mismatched = TombstoneRecord {
            raw_hash: other,
            events: vec![LifecycleEvent::purged(
                NOW,
                commit(),
                PurgeReason::Legal,
                "user",
                1,
            )],
        };
        fs::write(&path, record_bytes(&mismatched).unwrap()).unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );

        fs::remove_file(&path).unwrap();
        fs::write(&path, vec![b'x'; MAX_PURGE_RECORD_BYTES as usize + 1]).unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
    }

    #[cfg(unix)]
    #[test]
    fn symlink_hardlink_and_ancestor_replacement_are_rejected() {
        use std::os::unix::fs::symlink;

        let (dir, state) = setup();
        let path = state.tombstone_path(&raw()).unwrap();
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        let outside = dir.path().join("outside");
        fs::write(&outside, b"outside").unwrap();
        symlink(&outside, &path).unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&outside).unwrap(), b"outside");

        fs::remove_file(&path).unwrap();
        fs::hard_link(&outside, &path).unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&outside).unwrap(), b"outside");
    }

    #[test]
    fn journal_is_monotonic_resumable_and_blocks_only_after_prepared() {
        let (_dir, state) = setup();
        let journal = started(&state);
        assert!(!state.barrier_blocks(&raw()).unwrap());
        assert!(matches!(
            state
                .begin(
                    vec![raw()],
                    PurgeReason::Legal,
                    TombstoneMode::Default,
                    "user",
                    NOW,
                    1,
                    commit(),
                    // `Resumed` ignores this parameter (the existing journal's
                    // own closure_hash wins) — deliberately bogus.
                    hash_bytes(b"unused closure_hash: resume keeps the original"),
                    journal.purge_id.clone(),
                )
                .unwrap(),
            BeginOutcome::Resumed(ref value) if value == &journal
        ));
        let tombstoned = state
            .advance_phase(&journal, PurgePhase::Tombstoned)
            .unwrap();
        assert!(state.barrier_blocks(&raw()).unwrap());
        assert_eq!(
            state
                .advance_phase(&tombstoned, PurgePhase::Prepared)
                .unwrap_err()
                .error_code(),
            "KIO-E-STORE-CORRUPT-001"
        );
        assert_eq!(
            state
                .abort_before_barrier(&tombstoned)
                .unwrap_err()
                .error_code(),
            "KIO-E-PURGE-INCOMPLETE-001"
        );
    }

    #[test]
    fn r23_07_sync_directory_propagates_a_failed_open() {
        // A path that does not exist -- `File::open` fails, and unlike the
        // pre-fix version (`if let Ok(directory) = File::open(path) { let _
        // = directory.sync_all(); }`, which silently no-oped on either an
        // open OR a sync failure), the failure must now surface to callers
        // (`write_private_replace`/`quarantine_then_unlink`).
        let (dir, _state) = setup();
        let missing = dir.path().join("does-not-exist");
        assert!(sync_directory(&missing).is_err());
        // The success path is unaffected: an existing directory syncs fine.
        assert!(sync_directory(dir.path()).is_ok());
    }

    /// The Windows arm keeps R23-07's fail-closed half without a real fsync,
    /// so the one case that distinguishes it from a bare `Ok(())` is worth
    /// holding: a path that exists but is a file must still be an error.
    /// On POSIX this is not a failure at all -- `File::open` + `sync_all` on a
    /// regular file succeeds -- so the assertion is genuinely platform-local.
    #[cfg(windows)]
    #[test]
    fn r23_07_sync_directory_rejects_a_file_on_windows() {
        let (dir, _state) = setup();
        let file = dir.path().join("not-a-directory");
        fs::write(&file, b"x").unwrap();
        assert!(sync_directory(&file).is_err());
    }

    #[test]
    fn leaf_raw_hash_prefixes_the_bare_digest_leaf() {
        let digest = "c".repeat(64);
        assert_eq!(
            leaf_raw_hash(Path::new(&digest)),
            format!("sha256:{digest}")
        );
    }

    #[test]
    fn r23_23_walk_fanout_leaves_fails_closed_on_non_notfound_errors() {
        let (dir, state) = setup();
        let kio_dir = dir.path().join(".kio");
        // `tombstones` exists but is a regular file, not a directory --
        // `read_dir` fails with something other than `NotFound`, which must
        // propagate (fail-closed) instead of being silently treated as
        // "nothing recorded yet" (the pre-fix `let Ok(top_entries) =
        // fs::read_dir(base) else { return Ok(leaves) }` pattern swallowed
        // every error, not just `NotFound` -- an undercounted epoch-recovery
        // max-scan can reissue an already-used epoch value).
        fs::write(kio_dir.join("tombstones"), b"not a directory").unwrap();
        let error = state.max_recorded_lifecycle_epoch().unwrap_err();
        assert_eq!(error.error_code(), "KIO-E-STORE-IO-001");
    }
}
