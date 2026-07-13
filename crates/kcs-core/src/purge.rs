//! Durable purge-state contracts shared by the CLI, readers, and fsck.
//!
//! This module deliberately owns only the visibility barrier and the two durable
//! terminal records. Physical artifact deletion and CLI orchestration live above
//! it. Callers that mutate this state must already hold the scope store lock.

use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::cas::{canonical_json_bytes, fanout_path, is_hash};
use crate::{ExitCode, KcsError, Result};

pub const MAX_PURGE_TARGETS: usize = 100_000;
pub const MAX_PURGE_RECORD_BYTES: u64 = 16 * 1024;
pub const MAX_PURGE_JOURNAL_BYTES: u64 = 8 * 1024 * 1024;

const JOURNAL_SCHEMA_VERSION: u64 = 1;
const RECEIPT_SCHEMA_VERSION: u64 = 1;
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
    type Err = KcsError;

    fn from_str(value: &str) -> Result<Self> {
        match value {
            "legal" => Ok(Self::Legal),
            "privacy" => Ok(Self::Privacy),
            "misingest" => Ok(Self::Misingest),
            "copyright" => Ok(Self::Copyright),
            "other" => Ok(Self::Other),
            _ => Err(KcsError::invalid_usage(
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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TombstoneMode {
    Default,
    Erase,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PurgePhase {
    Prepared,
    BarrierPublished,
    PurgedCommitCreated,
    ContentDeleted,
    DerivedDeleted,
    LogsScrubbed,
}

impl PurgePhase {
    const fn next(self) -> Option<Self> {
        match self {
            Self::Prepared => Some(Self::BarrierPublished),
            Self::BarrierPublished => Some(Self::PurgedCommitCreated),
            Self::PurgedCommitCreated => Some(Self::ContentDeleted),
            Self::ContentDeleted => Some(Self::DerivedDeleted),
            Self::DerivedDeleted => Some(Self::LogsScrubbed),
            Self::LogsScrubbed => None,
        }
    }

    #[must_use]
    pub const fn is_barrier_visible(self) -> bool {
        !matches!(self, Self::Prepared)
    }
}

/// Public dead-pointer record. Its serialized field set is contract-frozen.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TombstoneRecord {
    pub raw_hash: String,
    pub purged_at: String,
    pub purged_reason: PurgeReason,
    pub purged_in_commit: String,
}

impl TombstoneRecord {
    pub fn new(
        raw_hash: impl Into<String>,
        purged_at: impl Into<String>,
        purged_reason: PurgeReason,
        purged_in_commit: impl Into<String>,
    ) -> Result<Self> {
        let record = Self {
            raw_hash: raw_hash.into(),
            purged_at: purged_at.into(),
            purged_reason,
            purged_in_commit: purged_in_commit.into(),
        };
        record.validate()?;
        Ok(record)
    }

    fn validate(&self) -> Result<()> {
        validate_hash("tombstone raw_hash", &self.raw_hash)?;
        validate_hash("tombstone purged_in_commit", &self.purged_in_commit)?;
        validate_timestamp("tombstone purged_at", &self.purged_at)
    }
}

/// Fsck-only non-content record for `--erase-tombstone`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EraseReceipt {
    pub schema_version: u64,
    pub raw_hash: String,
    pub purged_in_commit: String,
    pub erased_at: String,
}

impl EraseReceipt {
    pub fn new(
        raw_hash: impl Into<String>,
        purged_in_commit: impl Into<String>,
        erased_at: impl Into<String>,
    ) -> Result<Self> {
        let receipt = Self {
            schema_version: RECEIPT_SCHEMA_VERSION,
            raw_hash: raw_hash.into(),
            purged_in_commit: purged_in_commit.into(),
            erased_at: erased_at.into(),
        };
        receipt.validate()?;
        Ok(receipt)
    }

    fn validate(&self) -> Result<()> {
        if self.schema_version != RECEIPT_SCHEMA_VERSION {
            return Err(corrupt_state("erase receipt schema_version is invalid"));
        }
        validate_hash("erase receipt raw_hash", &self.raw_hash)?;
        validate_hash("erase receipt purged_in_commit", &self.purged_in_commit)?;
        validate_timestamp("erase receipt erased_at", &self.erased_at)
    }
}

/// Owner-private resumable transaction state. Target hashes are strictly sorted
/// so a retry cannot silently change the aggregate operation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PurgeJournal {
    pub schema_version: u64,
    pub target_raw_hashes: Vec<String>,
    pub reason: PurgeReason,
    pub tombstone_mode: TombstoneMode,
    pub started_at: String,
    pub phase: PurgePhase,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub purged_in_commit: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub purged_at: Option<String>,
}

impl PurgeJournal {
    fn new(
        mut target_raw_hashes: Vec<String>,
        reason: PurgeReason,
        tombstone_mode: TombstoneMode,
        started_at: String,
    ) -> Result<Self> {
        target_raw_hashes.sort();
        target_raw_hashes.dedup();
        let journal = Self {
            schema_version: JOURNAL_SCHEMA_VERSION,
            target_raw_hashes,
            reason,
            tombstone_mode,
            started_at,
            phase: PurgePhase::Prepared,
            purged_in_commit: None,
            purged_at: None,
        };
        journal.validate()?;
        Ok(journal)
    }

    fn validate(&self) -> Result<()> {
        if self.schema_version != JOURNAL_SCHEMA_VERSION {
            return Err(corrupt_state("purge journal schema_version is invalid"));
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
        match (
            self.phase >= PurgePhase::PurgedCommitCreated,
            &self.purged_in_commit,
            &self.purged_at,
        ) {
            (true, Some(commit), Some(purged_at)) => {
                validate_hash("purge journal commit", commit)?;
                validate_timestamp("purge journal purged_at", purged_at)
            }
            (true, _, _) => Err(corrupt_state(
                "purge journal commit phase requires commit and timestamp",
            )),
            (false, None, None) => Ok(()),
            (false, _, _) => Err(corrupt_state(
                "purge journal terminal data appears before commit phase",
            )),
        }
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
    kcs_dir: PathBuf,
}

impl PurgeState {
    #[must_use]
    pub fn new(kcs_dir: impl Into<PathBuf>) -> Self {
        Self {
            kcs_dir: kcs_dir.into(),
        }
    }

    #[must_use]
    pub fn journal_path(&self) -> PathBuf {
        self.kcs_dir.join("purge/in-progress.json")
    }

    pub fn tombstone_path(&self, raw_hash: &str) -> Result<PathBuf> {
        fanout_path(self.kcs_dir.join("tombstones"), raw_hash)
    }

    pub fn erase_receipt_path(&self, raw_hash: &str) -> Result<PathBuf> {
        fanout_path(self.kcs_dir.join("purge/erase-receipts"), raw_hash)
    }

    /// Start, resume, or recognize an already-completed default purge. The caller
    /// must hold the scope store lock for this and all mutation methods below.
    pub fn begin(
        &self,
        target_raw_hashes: Vec<String>,
        reason: PurgeReason,
        tombstone_mode: TombstoneMode,
        started_at: impl Into<String>,
    ) -> Result<BeginOutcome> {
        let desired =
            PurgeJournal::new(target_raw_hashes, reason, tombstone_mode, started_at.into())?;
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

        let mut existing_tombstones = Vec::new();
        for raw_hash in &desired.target_raw_hashes {
            if let Some(record) = self.read_tombstone(raw_hash)? {
                if tombstone_mode == TombstoneMode::Erase {
                    return Err(KcsError::invalid_usage(
                        "converting an existing tombstone to erase mode is not supported",
                    ));
                }
                if record.purged_reason != reason {
                    return Err(KcsError::invalid_usage(
                        "an existing tombstone has a different purge reason",
                    ));
                }
                existing_tombstones.push(record);
            }
        }
        if existing_tombstones.len() == desired.target_raw_hashes.len() {
            return Ok(BeginOutcome::AlreadyComplete(existing_tombstones));
        }
        if !existing_tombstones.is_empty() {
            return Err(incomplete_state(
                "only part of the requested purge target is already tombstoned",
            ));
        }

        write_private_replace(
            &self.kcs_dir,
            &self.journal_path(),
            &journal_bytes(&desired)?,
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
        if current.phase.next() != Some(next) || next == PurgePhase::PurgedCommitCreated {
            return Err(corrupt_state("purge journal phase transition is invalid"));
        }
        let mut updated = current;
        updated.phase = next;
        updated.validate()?;
        write_private_replace(
            &self.kcs_dir,
            &self.journal_path(),
            &journal_bytes(&updated)?,
        )?;
        Ok(updated)
    }

    pub fn bind_purged_commit(
        &self,
        expected: &PurgeJournal,
        purged_in_commit: impl Into<String>,
        purged_at: impl Into<String>,
    ) -> Result<PurgeJournal> {
        let current = self.require_current(expected)?;
        let commit = purged_in_commit.into();
        let purged_at = purged_at.into();
        validate_hash("purged commit", &commit)?;
        validate_timestamp("purged commit timestamp", &purged_at)?;
        if current.phase == PurgePhase::PurgedCommitCreated {
            if current.purged_in_commit.as_deref() == Some(commit.as_str())
                && current.purged_at.as_deref() == Some(purged_at.as_str())
            {
                return Ok(current);
            }
            return Err(corrupt_state("purge journal commit changed on retry"));
        }
        if current.phase != PurgePhase::BarrierPublished {
            return Err(corrupt_state(
                "purged commit can only follow the visibility barrier",
            ));
        }
        let mut updated = current;
        updated.phase = PurgePhase::PurgedCommitCreated;
        updated.purged_in_commit = Some(commit);
        updated.purged_at = Some(purged_at);
        updated.validate()?;
        write_private_replace(
            &self.kcs_dir,
            &self.journal_path(),
            &journal_bytes(&updated)?,
        )?;
        Ok(updated)
    }

    pub fn barrier_blocks(&self, raw_hash: &str) -> Result<bool> {
        validate_hash("purge barrier lookup", raw_hash)?;
        Ok(self
            .read_journal()?
            .is_some_and(|journal| journal.blocks(raw_hash)))
    }

    pub fn publish_tombstone(
        &self,
        expected: &PurgeJournal,
        record: &TombstoneRecord,
    ) -> Result<()> {
        record.validate()?;
        self.authorize_terminal(
            expected,
            &record.raw_hash,
            &record.purged_in_commit,
            &record.purged_at,
            TombstoneMode::Default,
        )?;
        let canonical = self.tombstone_path(&record.raw_hash)?;
        let legacy = legacy_tombstone_path(&self.kcs_dir, &record.raw_hash)?;
        let bytes = record_bytes(record)?;

        let canonical_existing = read_bounded_regular(&canonical, MAX_PURGE_RECORD_BYTES)?;
        let legacy_existing = match &legacy {
            Some(path) => read_bounded_regular(path, MAX_PURGE_RECORD_BYTES)?,
            None => None,
        };
        for existing in [canonical_existing.as_deref(), legacy_existing.as_deref()]
            .into_iter()
            .flatten()
        {
            let parsed: TombstoneRecord = parse_record(existing, "tombstone")?;
            parsed.validate()?;
            if parsed != *record {
                return Err(corrupt_state("conflicting tombstone record"));
            }
        }
        write_private_immutable(&self.kcs_dir, &canonical, &bytes)?;
        if let Some(path) = legacy.filter(|path| path.exists()) {
            quarantine_then_unlink(&path, MAX_PURGE_RECORD_BYTES)?;
        }
        Ok(())
    }

    pub fn publish_erase_receipt(
        &self,
        expected: &PurgeJournal,
        receipt: &EraseReceipt,
    ) -> Result<()> {
        receipt.validate()?;
        self.authorize_terminal(
            expected,
            &receipt.raw_hash,
            &receipt.purged_in_commit,
            &receipt.erased_at,
            TombstoneMode::Erase,
        )?;
        if self.read_tombstone(&receipt.raw_hash)?.is_some() {
            return Err(KcsError::invalid_usage(
                "erase mode cannot replace an existing public tombstone",
            ));
        }
        let path = self.erase_receipt_path(&receipt.raw_hash)?;
        write_private_immutable(&self.kcs_dir, &path, &record_bytes(receipt)?)
    }

    pub fn read_tombstone(&self, raw_hash: &str) -> Result<Option<TombstoneRecord>> {
        validate_hash("tombstone lookup", raw_hash)?;
        let canonical = self.tombstone_path(raw_hash)?;
        let legacy = legacy_tombstone_path(&self.kcs_dir, raw_hash)?;
        let canonical = read_bounded_regular(&canonical, MAX_PURGE_RECORD_BYTES)?
            .map(|bytes| parse_tombstone(&bytes, raw_hash))
            .transpose()?;
        let legacy = match legacy {
            Some(path) => read_bounded_regular(&path, MAX_PURGE_RECORD_BYTES)?
                .map(|bytes| parse_tombstone(&bytes, raw_hash))
                .transpose()?,
            None => None,
        };
        match (canonical, legacy) {
            (Some(left), Some(right)) if left != right => {
                Err(corrupt_state("portable and legacy tombstones disagree"))
            }
            (Some(record), _) | (_, Some(record)) => Ok(Some(record)),
            (None, None) => Ok(None),
        }
    }

    pub fn read_erase_receipt(&self, raw_hash: &str) -> Result<Option<EraseReceipt>> {
        validate_hash("erase receipt lookup", raw_hash)?;
        let path = self.erase_receipt_path(raw_hash)?;
        let Some(bytes) = read_bounded_regular(&path, MAX_PURGE_RECORD_BYTES)? else {
            return Ok(None);
        };
        let receipt: EraseReceipt = parse_record(&bytes, "erase receipt")?;
        receipt.validate()?;
        if receipt.raw_hash != raw_hash {
            return Err(corrupt_state("erase receipt identity does not match leaf"));
        }
        Ok(Some(receipt))
    }

    /// Retire an erase receipt after verified raw publication. This record is not
    /// a resurrection barrier and must not outlive newly authoritative raw bytes.
    pub fn retire_erase_receipt(&self, raw_hash: &str) -> Result<bool> {
        let path = self.erase_receipt_path(raw_hash)?;
        if read_bounded_regular(&path, MAX_PURGE_RECORD_BYTES)?.is_none() {
            return Ok(false);
        }
        quarantine_then_unlink(&path, MAX_PURGE_RECORD_BYTES)?;
        Ok(true)
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

    pub fn finish(&self, expected: &PurgeJournal) -> Result<()> {
        let current = self.require_current(expected)?;
        if current.phase != PurgePhase::LogsScrubbed {
            return Err(incomplete_state(
                "purge cannot finish before the final log scrub",
            ));
        }
        let commit = current
            .purged_in_commit
            .as_deref()
            .ok_or_else(|| corrupt_state("purge journal is missing its commit"))?;
        let purged_at = current
            .purged_at
            .as_deref()
            .ok_or_else(|| corrupt_state("purge journal is missing its timestamp"))?;
        for raw_hash in &current.target_raw_hashes {
            match current.tombstone_mode {
                TombstoneMode::Default => {
                    let record = self
                        .read_tombstone(raw_hash)?
                        .ok_or_else(|| incomplete_state("purge tombstone is missing"))?;
                    if record.purged_in_commit != commit
                        || record.purged_at != purged_at
                        || record.purged_reason != current.reason
                    {
                        return Err(corrupt_state("purge tombstone does not match journal"));
                    }
                }
                TombstoneMode::Erase => {
                    if self.read_tombstone(raw_hash)?.is_some() {
                        return Err(corrupt_state("erase purge left a public tombstone"));
                    }
                    let receipt = self
                        .read_erase_receipt(raw_hash)?
                        .ok_or_else(|| incomplete_state("purge erase receipt is missing"))?;
                    if receipt.purged_in_commit != commit || receipt.erased_at != purged_at {
                        return Err(corrupt_state("erase receipt does not match journal"));
                    }
                }
            }
        }
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

    fn authorize_terminal(
        &self,
        expected: &PurgeJournal,
        raw_hash: &str,
        purged_in_commit: &str,
        purged_at: &str,
        mode: TombstoneMode,
    ) -> Result<()> {
        let current = self.require_current(expected)?;
        if current.phase < PurgePhase::PurgedCommitCreated
            || current.tombstone_mode != mode
            || !current
                .target_raw_hashes
                .iter()
                .any(|hash| hash == raw_hash)
            || current.purged_in_commit.as_deref() != Some(purged_in_commit)
            || current.purged_at.as_deref() != Some(purged_at)
        {
            return Err(corrupt_state(
                "terminal purge record is not authorized by the journal",
            ));
        }
        Ok(())
    }
}

fn parse_tombstone(bytes: &[u8], expected_raw_hash: &str) -> Result<TombstoneRecord> {
    let record: TombstoneRecord = parse_record(bytes, "tombstone")?;
    record.validate()?;
    if record.raw_hash != expected_raw_hash {
        return Err(corrupt_state("tombstone identity does not match leaf"));
    }
    Ok(record)
}

fn journal_bytes(journal: &PurgeJournal) -> Result<Vec<u8>> {
    let bytes = record_bytes(journal)?;
    if bytes.len() as u64 > MAX_PURGE_JOURNAL_BYTES {
        return Err(corrupt_state("purge journal exceeds its size limit"));
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

fn legacy_tombstone_path(kcs_dir: &Path, raw_hash: &str) -> Result<Option<PathBuf>> {
    #[cfg(not(windows))]
    {
        let digest = raw_hash
            .strip_prefix("sha256:")
            .filter(|digest| digest.len() == 64)
            .ok_or_else(|| corrupt_state("invalid legacy tombstone hash"))?;
        Ok(Some(
            kcs_dir
                .join("tombstones")
                .join(&digest[0..2])
                .join(&digest[2..4])
                .join(raw_hash),
        ))
    }
    #[cfg(windows)]
    {
        let _ = (kcs_dir, raw_hash);
        Ok(None)
    }
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

fn write_private_immutable(kcs_dir: &Path, path: &Path, bytes: &[u8]) -> Result<()> {
    if bytes.len() as u64 > MAX_PURGE_RECORD_BYTES {
        return Err(corrupt_state("purge record exceeds its size limit"));
    }
    let parent = ensure_secure_parent(kcs_dir, path)?;
    if let Some(existing) = read_bounded_regular(path, MAX_PURGE_RECORD_BYTES)? {
        if existing == bytes {
            return Ok(());
        }
        return Err(corrupt_state("immutable purge record conflicts"));
    }
    let (temp_path, mut temp) = create_private_temp(&parent)?;
    let result = (|| -> Result<()> {
        temp.write_all(bytes).map_err(state_io)?;
        temp.sync_all().map_err(state_io)?;
        drop(temp);
        match fs::hard_link(&temp_path, path) {
            Ok(()) => {
                fs::remove_file(&temp_path).map_err(state_io)?;
                sync_directory(&parent);
                Ok(())
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                let existing = read_bounded_regular(path, MAX_PURGE_RECORD_BYTES)?
                    .ok_or_else(|| corrupt_state("purge record disappeared"))?;
                if existing != bytes {
                    return Err(corrupt_state("immutable purge record conflicts"));
                }
                fs::remove_file(&temp_path).map_err(state_io)
            }
            Err(error) => Err(state_io(error)),
        }
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp_path);
    }
    result
}

fn write_private_replace(kcs_dir: &Path, path: &Path, bytes: &[u8]) -> Result<()> {
    if bytes.len() as u64 > MAX_PURGE_JOURNAL_BYTES {
        return Err(corrupt_state("purge journal exceeds its size limit"));
    }
    let parent = ensure_secure_parent(kcs_dir, path)?;
    if path.exists() {
        read_bounded_regular(path, MAX_PURGE_JOURNAL_BYTES)?
            .ok_or_else(|| corrupt_state("purge journal disappeared"))?;
    }
    let (temp_path, mut temp) = create_private_temp(&parent)?;
    let result = (|| -> Result<()> {
        temp.write_all(bytes).map_err(state_io)?;
        temp.sync_all().map_err(state_io)?;
        drop(temp);
        replace_file(&temp_path, path)?;
        sync_directory(&parent);
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp_path);
    }
    result
}

fn ensure_secure_parent(kcs_dir: &Path, path: &Path) -> Result<PathBuf> {
    let root_metadata = fs::symlink_metadata(kcs_dir).map_err(state_io)?;
    if !directory_is_real(kcs_dir, &root_metadata)? {
        return Err(corrupt_state("KCS root is not a real directory"));
    }
    let root = kcs_dir.canonicalize().map_err(state_io)?;
    let parent = path
        .parent()
        .ok_or_else(|| corrupt_state("purge state path has no parent"))?;
    let relative = parent
        .strip_prefix(kcs_dir)
        .map_err(|_| corrupt_state("purge state path escapes KCS root"))?;
    let mut current = kcs_dir.to_path_buf();
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
            return Err(corrupt_state("purge state ancestor escapes KCS root"));
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
    sync_directory(parent);
    Ok(())
}

/// Best-effort fail-closed recovery for a remove race. Never overwrites a path
/// another actor published while the state file was quarantined.
fn restore_private_no_clobber(parent: &Path, path: &Path, expected_bytes: &[u8]) {
    let Ok((temp_path, mut temp)) = create_private_temp(parent) else {
        return;
    };
    let result = (|| -> std::io::Result<()> {
        temp.write_all(expected_bytes)?;
        temp.sync_all()?;
        drop(temp);
        match fs::hard_link(&temp_path, path) {
            Ok(()) => sync_directory(parent),
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

fn sync_directory(path: &Path) {
    if let Ok(directory) = File::open(path) {
        let _ = directory.sync_all();
    }
}

fn corrupt_state(message: impl Into<String>) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-CORRUPT-001",
        message,
        json!({ "component": "purge_state" }),
        ExitCode::Failure,
    )
}

fn incomplete_state(message: impl Into<String>) -> KcsError {
    KcsError::new(
        "KCS-E-PURGE-INCOMPLETE-001",
        message,
        json!({ "component": "purge_state" }),
        ExitCode::PartialFailure,
    )
}

fn state_io(error: std::io::Error) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-IO-001",
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

    fn setup() -> (tempfile::TempDir, PurgeState) {
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        fs::create_dir(&kcs_dir).unwrap();
        (dir, PurgeState::new(kcs_dir))
    }

    fn raw() -> String {
        hash_bytes(b"private raw")
    }

    fn commit() -> String {
        hash_bytes(b"purged commit")
    }

    fn started(state: &PurgeState, mode: TombstoneMode) -> PurgeJournal {
        match state
            .begin(vec![raw()], PurgeReason::Legal, mode, NOW)
            .unwrap()
        {
            BeginOutcome::Started(journal) => journal,
            other => panic!("unexpected begin outcome: {other:?}"),
        }
    }

    fn committed(state: &PurgeState, mode: TombstoneMode) -> PurgeJournal {
        let prepared = started(state, mode);
        let barrier = state
            .advance_phase(&prepared, PurgePhase::BarrierPublished)
            .unwrap();
        state.bind_purged_commit(&barrier, commit(), NOW).unwrap()
    }

    #[test]
    fn exact_tombstone_path_schema_and_idempotent_publication() {
        let (_dir, state) = setup();
        let journal = committed(&state, TombstoneMode::Default);
        let record = TombstoneRecord::new(raw(), NOW, PurgeReason::Legal, commit()).unwrap();
        state.publish_tombstone(&journal, &record).unwrap();
        state.publish_tombstone(&journal, &record).unwrap();

        let digest = raw().strip_prefix("sha256:").unwrap().to_owned();
        assert!(state.tombstone_path(&raw()).unwrap().ends_with(format!(
            "{}/{}/{}",
            &digest[0..2],
            &digest[2..4],
            digest
        )));
        let value: serde_json::Value =
            serde_json::from_slice(&fs::read(state.tombstone_path(&raw()).unwrap()).unwrap())
                .unwrap();
        assert_eq!(
            value,
            json!({
                "raw_hash": raw(),
                "purged_at": NOW,
                "purged_reason": "legal",
                "purged_in_commit": commit(),
            })
        );
        assert_eq!(state.read_tombstone(&raw()).unwrap(), Some(record));

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = fs::metadata(state.tombstone_path(&raw()).unwrap())
                .unwrap()
                .permissions()
                .mode();
            assert_eq!(mode & 0o077, 0);
        }
    }

    #[test]
    fn erase_receipt_is_exact_private_non_content_state() {
        let (_dir, state) = setup();
        let journal = committed(&state, TombstoneMode::Erase);
        let receipt = EraseReceipt::new(raw(), commit(), NOW).unwrap();
        state.publish_erase_receipt(&journal, &receipt).unwrap();
        assert!(state.read_tombstone(&raw()).unwrap().is_none());
        assert_eq!(state.read_erase_receipt(&raw()).unwrap(), Some(receipt));

        let value: serde_json::Value =
            serde_json::from_slice(&fs::read(state.erase_receipt_path(&raw()).unwrap()).unwrap())
                .unwrap();
        assert_eq!(
            value,
            json!({
                "schema_version": 1,
                "raw_hash": raw(),
                "purged_in_commit": commit(),
                "erased_at": NOW,
            })
        );
        for forbidden in ["reason", "actor", "path", "query", "prompt", "content"] {
            assert!(value.get(forbidden).is_none());
        }
        assert!(state.retire_erase_receipt(&raw()).unwrap());
        assert!(!state.retire_erase_receipt(&raw()).unwrap());
    }

    #[test]
    fn journal_is_monotonic_resumable_and_blocks_only_after_barrier() {
        let (_dir, state) = setup();
        let prepared = started(&state, TombstoneMode::Default);
        assert!(!state.barrier_blocks(&raw()).unwrap());
        assert!(matches!(
            state
                .begin(
                    vec![raw()],
                    PurgeReason::Legal,
                    TombstoneMode::Default,
                    NOW,
                )
                .unwrap(),
            BeginOutcome::Resumed(ref value) if value == &prepared
        ));
        let barrier = state
            .advance_phase(&prepared, PurgePhase::BarrierPublished)
            .unwrap();
        assert!(state.barrier_blocks(&raw()).unwrap());
        assert_eq!(
            state
                .advance_phase(&barrier, PurgePhase::DerivedDeleted)
                .unwrap_err()
                .error_code(),
            "KCS-E-STORE-CORRUPT-001"
        );
        assert_eq!(
            state
                .abort_before_barrier(&barrier)
                .unwrap_err()
                .error_code(),
            "KCS-E-PURGE-INCOMPLETE-001"
        );
    }

    #[test]
    fn default_transaction_finishes_only_after_terminal_and_final_scrub() {
        let (_dir, state) = setup();
        let committed = committed(&state, TombstoneMode::Default);
        assert_eq!(
            state.finish(&committed).unwrap_err().error_code(),
            "KCS-E-PURGE-INCOMPLETE-001"
        );
        let record = TombstoneRecord::new(raw(), NOW, PurgeReason::Legal, commit()).unwrap();
        state.publish_tombstone(&committed, &record).unwrap();
        let content = state
            .advance_phase(&committed, PurgePhase::ContentDeleted)
            .unwrap();
        let derived = state
            .advance_phase(&content, PurgePhase::DerivedDeleted)
            .unwrap();
        let scrubbed = state
            .advance_phase(&derived, PurgePhase::LogsScrubbed)
            .unwrap();
        state.finish(&scrubbed).unwrap();
        assert!(!state.journal_path().exists());
        assert!(!state.barrier_blocks(&raw()).unwrap());
        assert!(matches!(
            state
                .begin(
                    vec![raw()],
                    PurgeReason::Legal,
                    TombstoneMode::Default,
                    NOW,
                )
                .unwrap(),
            BeginOutcome::AlreadyComplete(records) if records == vec![record]
        ));
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
            "KCS-E-STORE-CORRUPT-001"
        );

        fs::remove_file(&path).unwrap();
        let other = hash_bytes(b"other");
        fs::write(
            &path,
            record_bytes(&TombstoneRecord::new(other, NOW, PurgeReason::Legal, commit()).unwrap())
                .unwrap(),
        )
        .unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KCS-E-STORE-CORRUPT-001"
        );

        fs::remove_file(&path).unwrap();
        fs::write(&path, vec![b'x'; MAX_PURGE_RECORD_BYTES as usize + 1]).unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KCS-E-STORE-CORRUPT-001"
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
            "KCS-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&outside).unwrap(), b"outside");

        fs::remove_file(&path).unwrap();
        fs::hard_link(&outside, &path).unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KCS-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&outside).unwrap(), b"outside");

        fs::remove_file(&path).unwrap();
        let journal = committed(&state, TombstoneMode::Default);
        let tombstones = state.kcs_dir.join("tombstones");
        fs::remove_dir_all(&tombstones).unwrap();
        symlink(&outside, &tombstones).unwrap();
        let record = TombstoneRecord::new(raw(), NOW, PurgeReason::Legal, commit()).unwrap();
        assert_eq!(
            state
                .publish_tombstone(&journal, &record)
                .unwrap_err()
                .error_code(),
            "KCS-E-STORE-CORRUPT-001"
        );
        assert_eq!(fs::read(&outside).unwrap(), b"outside");
    }

    #[cfg(not(windows))]
    #[test]
    fn matching_legacy_tombstone_is_migrated_and_conflict_fails_closed() {
        let (_dir, state) = setup();
        let journal = committed(&state, TombstoneMode::Default);
        let record = TombstoneRecord::new(raw(), NOW, PurgeReason::Legal, commit()).unwrap();
        let legacy = legacy_tombstone_path(&state.kcs_dir, &raw())
            .unwrap()
            .unwrap();
        fs::create_dir_all(legacy.parent().unwrap()).unwrap();
        fs::write(&legacy, record_bytes(&record).unwrap()).unwrap();
        state.publish_tombstone(&journal, &record).unwrap();
        assert!(!legacy.exists());
        assert_eq!(state.read_tombstone(&raw()).unwrap(), Some(record.clone()));

        let conflicting =
            TombstoneRecord::new(raw(), "2026-07-13T00:00:01Z", PurgeReason::Legal, commit())
                .unwrap();
        fs::write(&legacy, record_bytes(&conflicting).unwrap()).unwrap();
        assert_eq!(
            state.read_tombstone(&raw()).unwrap_err().error_code(),
            "KCS-E-STORE-CORRUPT-001"
        );
    }

    #[test]
    fn erase_cannot_convert_an_existing_default_tombstone() {
        let (_dir, state) = setup();
        let journal = committed(&state, TombstoneMode::Default);
        let record = TombstoneRecord::new(raw(), NOW, PurgeReason::Legal, commit()).unwrap();
        state.publish_tombstone(&journal, &record).unwrap();
        let content = state
            .advance_phase(&journal, PurgePhase::ContentDeleted)
            .unwrap();
        let derived = state
            .advance_phase(&content, PurgePhase::DerivedDeleted)
            .unwrap();
        let scrubbed = state
            .advance_phase(&derived, PurgePhase::LogsScrubbed)
            .unwrap();
        state.finish(&scrubbed).unwrap();
        assert_eq!(
            state
                .begin(vec![raw()], PurgeReason::Legal, TombstoneMode::Erase, NOW,)
                .unwrap_err()
                .error_code(),
            "KCS-E-CONFIG-USAGE-001"
        );
    }
}
