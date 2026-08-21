//! Batch task descriptor contracts.

use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use cap_primitives::{ambient_authority, fs as cap_fs};
use serde::{Deserialize, Deserializer, Serialize};

use crate::markdownize::MarkdownizeMode;
use crate::store_path::{StorePathKind, resolve_existing_store_path};
use crate::{IoResultExt, PipelineError, Result};

/// Hard limits for persisted task state. They are deliberately above the normal
/// batch sizes, but finite so an adopted `tasks.jsonl` cannot make Kio allocate
/// attacker-selected amounts before it reaches semantic validation.
pub const MAX_TASK_STORE_BYTES: u64 = 64 * 1024 * 1024;
pub const MAX_TASK_RECORD_BYTES: u64 = 256 * 1024;
pub const MAX_TASK_RECORDS: usize = 100_000;
pub const MAX_TASK_UNIT_KEYS: usize = 4_096;
const MAX_TASK_ID_BYTES: usize = 256;
const MAX_TASK_PATH_BYTES: usize = 4_096;
const MAX_TASK_REASON_BYTES: usize = 256;
const MAX_TASK_TIMESTAMP_BYTES: usize = 128;

pub const BUDGET_EXCEEDED_REASON: &str = "budget_exceeded";
pub const SECRETS_TIER_B_HOLD_REASON: &str = "secrets_tier_b_hold";
pub const RETIRED_NON_LIVE_REASON: &str = "retired_non_live";

/// step4b-contract-tests-p3a.md QA1: the closed `hold_reason` enum for a
/// `Paused` task (04 §5.2 L679-683: `hold_reason = budget | auth |
/// tier_b_approval`), distinct from `fallback_reason`'s `RetryErrorKind`
/// classification for `Failed` tasks.
///
/// QA2/QA3 (step4b-contract-tests-p3a.md §A, 04 §5.2/§5.3, implemented): the
/// status-machine transitions this enum enables are wired at every send site
/// (markdownize's online-send failure handler and the embedding batch-send
/// handler in `kio-cli`'s `main.rs`):
///
/// - QA2 `auth_error`: lands `Paused` with `hold_reason = Some(Auth)` (never
///   `Failed`) — `retry_policy(AuthError).paused == true` now truthfully
///   describes this. `attempts` is left UNCHANGED (a pause is not a
///   retry-budget event — `max_attempts=0` means "no retry", not "budget
///   already spent"), so a later revival via `batch resume` (or the
///   dedicated markdownize auth-revive pre-pass, `task_auth_revival_allowed`
///   below) does not find the budget exhausted. `batch retry` remains a
///   no-op for it (its Failed-only task selection naturally skips a Paused
///   row — CT2-TASK-005).
/// - QA3 `rate_limit`: stays `Pending` (never `Paused`, never `Failed` — 04
///   §5.2 L682-683 says explicitly "paused ではなく pending + next_retry_at
///   で表現する") with `next_retry_at` derived from the provider's
///   `Retry-After` header when present (`AdapterError::RateLimit`'s
///   `retry_after_ms`), else a synthetic +2s backoff. `attempts` is likewise
///   UNCHANGED (`max_attempts=None` = unbounded retries, 04 §5.3), and a
///   Pending task's send-eligibility now additionally honors this
///   `next_retry_at` (`task_retry_due`) so an unelapsed backoff is not
///   bypassed just because the task never became `Failed`.
///
/// This flipped >20 existing regression tests (`r16_7_*`, `r17_3_*`,
/// `r19_*`, `ct2_task_00[5-9]`, etc.) that used to assert `status=Failed` for
/// `rate_limit`/`auth_error` sends — see `step2_p0_contract.rs`/
/// `step3_p0_contract.rs` for the updated assertions.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HoldReason {
    Budget,
    Auth,
    TierBApproval,
}

impl HoldReason {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Budget => "budget",
            Self::Auth => "auth",
            Self::TierBApproval => "tier_b_approval",
        }
    }
}

/// Map a `fallback_reason` string to the [`HoldReason`] it represents when the
/// task is (or is about to become) `Paused`. `None` for any reason that does
/// not correspond to a hold (e.g. a `RetryErrorKind` reason on a `Failed`
/// task).
#[must_use]
pub fn hold_reason_for_reason(reason: &str) -> Option<HoldReason> {
    match reason {
        BUDGET_EXCEEDED_REASON => Some(HoldReason::Budget),
        SECRETS_TIER_B_HOLD_REASON => Some(HoldReason::TierBApproval),
        "auth_error" => Some(HoldReason::Auth),
        _ => None,
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskType {
    Markdownize,
    Embedding,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskStatus {
    Pending,
    Running,
    Done,
    Partial,
    Failed,
    Paused,
}

// R17-3: `Eq` is intentionally NOT derived — `reserved_usd` is an `f64`, which
// only implements `PartialEq`. Nothing uses `TaskDescriptor` in an `Eq`-bound
// context (no Hash/BTreeSet/HashMap key, no `Eq`-deriving container holds it), so
// dropping it is inert; `PartialEq` (`==` in tests and dedup) is retained.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct TaskDescriptor {
    pub task_id: String,
    #[serde(rename = "type")]
    pub task_type: TaskType,
    pub mode: Option<MarkdownizeMode>,
    pub input_path: String,
    pub input_hash: String,
    pub previous_raw_hash: Option<String>,
    pub parent_run_id: Option<String>,
    pub changed_unit_keys: Vec<String>,
    pub output_ref: String,
    pub unit_keys: Option<Vec<String>>,
    pub status: TaskStatus,
    pub attempts: u32,
    pub next_retry_at: Option<String>,
    pub deadline: Option<String>,
    pub heartbeat_at: Option<String>,
    pub fallback_reason: Option<String>,
    pub created_at: String,
    /// Frozen bbox-annotation policy for online Markdownize task identity.
    /// Non-Markdownize tasks persist an explicit JSON null.
    pub bbox_annotation_enabled: Option<bool>,
    /// QA1 (step4b-contract-tests-p3a.md §A): the closed hold reason for a
    /// `Paused` task (04 §5.2). Non-paused tasks persist an explicit JSON null.
    pub hold_reason: Option<HoldReason>,
    // R17-3: the exact F8 reservation this task currently holds (amount + the
    // ledger `month` it landed in), stamped when a FRESH charge is reserved in the
    // batch send path and left untouched on the RateLimit/Quota re-reservation-skip
    // (R16-7) so it always names the single live reservation the skip gate relies
    // on. When a stale task is superseded at re-index, a non-billable (RateLimit/
    // Quota) reservation is reclaimed by exactly this (usd, month) into the sibling
    // reclaim ledger — canceling the phantom precisely even though the edited file
    // is gone. A reclaim clears the stamp so it can never be reclaimed twice.
    // Absence is represented as an explicit JSON null.
    pub reserved_usd: Option<f64>,
    /// Reservation month, or an explicit JSON null when no reservation exists.
    pub reserved_month: Option<String>,
    /// Identity of the matching record in the trusted device reservation ledger.
    /// An absent reservation is represented as an explicit JSON null.
    pub reservation_id: Option<String>,
}

/// A persisted nullable field that still must be present in every current task row.
/// `Option<T>` alone would accept an omitted key during deserialization, which would
/// silently turn an obsolete task row into current state.
#[derive(Debug, Deserialize)]
struct RequiredNullable<T>(Option<T>);

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TaskDescriptorWire {
    task_id: String,
    #[serde(rename = "type")]
    task_type: TaskType,
    mode: RequiredNullable<MarkdownizeMode>,
    input_path: String,
    input_hash: String,
    previous_raw_hash: RequiredNullable<String>,
    parent_run_id: RequiredNullable<String>,
    changed_unit_keys: Vec<String>,
    output_ref: String,
    unit_keys: RequiredNullable<Vec<String>>,
    status: TaskStatus,
    attempts: u32,
    next_retry_at: RequiredNullable<String>,
    deadline: RequiredNullable<String>,
    heartbeat_at: RequiredNullable<String>,
    fallback_reason: RequiredNullable<String>,
    created_at: String,
    bbox_annotation_enabled: RequiredNullable<bool>,
    hold_reason: RequiredNullable<HoldReason>,
    reserved_usd: RequiredNullable<f64>,
    reserved_month: RequiredNullable<String>,
    reservation_id: RequiredNullable<String>,
}

impl<'de> Deserialize<'de> for TaskDescriptor {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let wire = TaskDescriptorWire::deserialize(deserializer)?;
        Ok(Self {
            task_id: wire.task_id,
            task_type: wire.task_type,
            mode: wire.mode.0,
            input_path: wire.input_path,
            input_hash: wire.input_hash,
            previous_raw_hash: wire.previous_raw_hash.0,
            parent_run_id: wire.parent_run_id.0,
            changed_unit_keys: wire.changed_unit_keys,
            output_ref: wire.output_ref,
            unit_keys: wire.unit_keys.0,
            status: wire.status,
            attempts: wire.attempts,
            next_retry_at: wire.next_retry_at.0,
            deadline: wire.deadline.0,
            heartbeat_at: wire.heartbeat_at.0,
            fallback_reason: wire.fallback_reason.0,
            created_at: wire.created_at,
            bbox_annotation_enabled: wire.bbox_annotation_enabled.0,
            hold_reason: wire.hold_reason.0,
            reserved_usd: wire.reserved_usd.0,
            reserved_month: wire.reserved_month.0,
            reservation_id: wire.reservation_id.0,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaskRecoveryMode {
    Resume,
    Retry,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TaskOutputRef {
    Online {
        adapter_id: String,
    },
    /// An `offline_api` adapter's enrichment task (Stage 3).
    ///
    /// A separate variant rather than reusing `Online` with a local adapter id,
    /// because `output_ref` is a durable record: calling a loopback pipeline
    /// "online" in the task journal would assert something untrue about where
    /// the document went, and every gate that keys off `Online` — the network
    /// opt-in, the ledger, the batch lane — would then have to special-case its
    /// way back out. The prefix is the distinction those gates read.
    Offline {
        adapter_id: String,
    },
    Embedding {
        chunk_id: String,
    },
    NormalizedInstance {
        path: PathBuf,
        raw_hash: String,
        tool_profile_hash: String,
        r#gen: u64,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CappedTaskInput {
    Bytes(Vec<u8>),
    Unavailable,
    NotRegular,
    TooLarge,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct TaskReservationClaim<'a> {
    pub reservation_id: &'a str,
    pub task_id: &'a str,
    pub usd: f64,
    pub month: &'a str,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RetryErrorKind {
    NetworkError,
    RateLimit,
    AuthError,
    QuotaExceeded,
    InvalidInput,
    ContractViolation,
    BudgetExceeded,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RetryPolicy {
    pub error_kind: RetryErrorKind,
    pub retryable: bool,
    pub max_attempts: Option<u32>,
    pub backoff: String,
    pub error_code: String,
    pub paused: bool,
}

#[derive(Debug, Clone)]
pub struct TaskStore {
    path: PathBuf,
}

impl TaskStore {
    #[must_use]
    pub fn new(kio_dir: impl AsRef<Path>) -> Self {
        Self {
            path: kio_dir.as_ref().join("tasks.jsonl"),
        }
    }

    pub fn append(&self, descriptor: &TaskDescriptor) -> Result<()> {
        let line = self.framed_record(descriptor)?;
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent).pipeline_io(parent)?;
        }
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .pipeline_io(&self.path)?;
        // M1(b): frame the record and emit it with one write_all so concurrent
        // appends cannot interleave byte-wise under O_APPEND.
        let existing_len = file.metadata().pipeline_io(&self.path)?.len();
        if existing_len.saturating_add(line.len() as u64) > MAX_TASK_STORE_BYTES {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                format!("tasks.jsonl exceeds {MAX_TASK_STORE_BYTES} byte limit"),
            ));
        }
        file.write_all(&line).pipeline_io(&self.path)
    }

    pub fn all(&self) -> Result<Vec<TaskDescriptor>> {
        let file = match fs::File::open(&self.path) {
            Ok(file) => file,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(err) => {
                return Err(PipelineError::Io {
                    path: self.path.display().to_string(),
                    message: err.to_string(),
                });
            }
        };
        self.read_descriptors(file, |descriptor| {
            validate_task_descriptor(self.kio_dir(), descriptor)
        })
    }

    fn read_descriptors(
        &self,
        file: fs::File,
        mut validate: impl FnMut(&TaskDescriptor) -> Result<()>,
    ) -> Result<Vec<TaskDescriptor>> {
        let file_len = file.metadata().pipeline_io(&self.path)?.len();
        if file_len > MAX_TASK_STORE_BYTES {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                format!("tasks.jsonl exceeds {MAX_TASK_STORE_BYTES} byte limit: {file_len}"),
            ));
        }
        let mut by_id = BTreeMap::new();
        let mut reader = std::io::BufReader::new(file);
        let mut line = Vec::new();
        let mut record_count = 0usize;
        let mut total_read = 0u64;
        loop {
            line.clear();
            let read = reader
                .by_ref()
                .take(MAX_TASK_RECORD_BYTES.saturating_add(1))
                .read_until(b'\n', &mut line)
                .pipeline_io(&self.path)?;
            if read == 0 {
                break;
            }
            total_read = total_read.saturating_add(read as u64);
            if total_read > MAX_TASK_STORE_BYTES {
                return Err(PipelineError::corrupt(
                    self.path.display().to_string(),
                    format!("tasks.jsonl exceeds {MAX_TASK_STORE_BYTES} byte limit"),
                ));
            }
            if read as u64 > MAX_TASK_RECORD_BYTES {
                return Err(PipelineError::corrupt(
                    self.path.display().to_string(),
                    format!("task record exceeds {MAX_TASK_RECORD_BYTES} byte limit"),
                ));
            }
            if line.iter().all(u8::is_ascii_whitespace) {
                continue;
            }
            record_count = record_count.saturating_add(1);
            if record_count > MAX_TASK_RECORDS {
                return Err(PipelineError::corrupt(
                    self.path.display().to_string(),
                    format!("tasks.jsonl exceeds {MAX_TASK_RECORDS} record limit"),
                ));
            }
            // M1(c): a malformed line is a corrupt store file, not a schema/config
            // error — classify it as KIO-E-STORE-CORRUPT-001 with the file path.
            let descriptor: TaskDescriptor = serde_json::from_slice(&line).map_err(|err| {
                PipelineError::corrupt(self.path.display().to_string(), err.to_string())
            })?;
            validate(&descriptor)?;
            by_id.insert(descriptor.task_id.clone(), descriptor);
        }
        Ok(by_id.into_values().collect())
    }

    pub fn replace_all(&self, descriptors: &[TaskDescriptor]) -> Result<()> {
        if descriptors.len() > MAX_TASK_RECORDS {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                format!("tasks.jsonl exceeds {MAX_TASK_RECORDS} record limit"),
            ));
        }
        for descriptor in descriptors {
            validate_task_descriptor(self.kio_dir(), descriptor)?;
        }
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent).pipeline_io(parent)?;
        }
        // O3: write through a unique, exclusively-created temp file instead of the
        // fixed `tasks.jsonl.tmp`, so two concurrent writers can never share one
        // temp and clobber each other's half-written content before the rename.
        // (The `batch` folder store lock is the primary serialization guard; this
        // is defense in depth for any other `replace_all` caller.)
        let (mut file, temp_path) = self.create_unique_temp()?;
        // R9-8: remove the temp on any serialize/write/rename failure so an
        // ENOSPC/EIO error does not leave an orphan `.tasks.jsonl.*.tmp` in the
        // tasks dir (no GC before Step 4). Same cleanup idiom as the CAS /
        // normalized-instance writers.
        let result = (|| -> Result<()> {
            let mut total_bytes = 0u64;
            for descriptor in descriptors {
                let line = self.framed_record(descriptor)?;
                total_bytes = total_bytes.saturating_add(line.len() as u64);
                if total_bytes > MAX_TASK_STORE_BYTES {
                    return Err(PipelineError::corrupt(
                        self.path.display().to_string(),
                        format!("tasks.jsonl exceeds {MAX_TASK_STORE_BYTES} byte limit"),
                    ));
                }
                file.write_all(&line).pipeline_io(&temp_path)?;
            }
            drop(file);
            fs::rename(&temp_path, &self.path).pipeline_io(&self.path)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result
    }

    fn framed_record(&self, descriptor: &TaskDescriptor) -> Result<Vec<u8>> {
        // Keep the write boundary as strict as the read boundary.  In particular,
        // an obsolete online task without its frozen policy stamp must never be
        // appended and then discovered only by a later reader.
        validate_task_descriptor(self.kio_dir(), descriptor)?;
        let mut line =
            serde_json::to_vec(descriptor).map_err(|err| PipelineError::Schema(err.to_string()))?;
        line.push(b'\n');
        if line.len() as u64 > MAX_TASK_RECORD_BYTES {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                format!("task record exceeds {MAX_TASK_RECORD_BYTES} byte limit"),
            ));
        }
        Ok(line)
    }

    /// Create (`O_CREAT | O_EXCL`) a uniquely-named temp file next to the store
    /// and return it with its path. The pid + monotonic-nanos + per-process
    /// sequence make collisions vanishingly unlikely; `create_new` turns any
    /// residual clash into a hard error rather than a silent overwrite.
    fn create_unique_temp(&self) -> Result<(fs::File, PathBuf)> {
        static SEQ: AtomicU64 = AtomicU64::new(0);
        let parent = self.path.parent().unwrap_or_else(|| Path::new("."));
        let stem = self
            .path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("tasks.jsonl");
        for _ in 0..8 {
            let nanos = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|elapsed| elapsed.as_nanos())
                .unwrap_or(0);
            let seq = SEQ.fetch_add(1, Ordering::Relaxed);
            let temp = parent.join(format!(".{stem}.{}.{nanos}.{seq}.tmp", std::process::id()));
            match OpenOptions::new().write(true).create_new(true).open(&temp) {
                Ok(file) => return Ok((file, temp)),
                Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(err) => {
                    return Err(PipelineError::Io {
                        path: temp.display().to_string(),
                        message: err.to_string(),
                    });
                }
            }
        }
        Err(PipelineError::Io {
            path: parent.display().to_string(),
            message: "could not create a unique temp file for tasks.jsonl".to_owned(),
        })
    }

    pub fn update_matching(
        &self,
        mut update: impl FnMut(&mut TaskDescriptor) -> bool,
    ) -> Result<usize> {
        let mut descriptors = self.all()?;
        let mut changed = 0;
        for descriptor in &mut descriptors {
            if update(descriptor) {
                changed += 1;
            }
        }
        self.replace_all(&descriptors)?;
        Ok(changed)
    }

    pub fn done_output_for(
        &self,
        input_hash: &str,
        output_ref: &str,
    ) -> Result<Option<TaskDescriptor>> {
        Ok(self.all()?.into_iter().find(|task| {
            task.input_hash == input_hash
                && task.output_ref == output_ref
                && matches!(task.status, TaskStatus::Done | TaskStatus::Partial)
        }))
    }

    #[must_use]
    pub fn kio_dir(&self) -> &Path {
        self.path.parent().unwrap_or_else(|| Path::new("."))
    }
}

/// Rebase normalized-instance task references after a private task-store copy.
///
/// `source_kio` is an already-canonical, lexical source identity; it is never
/// opened. The destination store is read only after a bounded, no-follow store
/// path check. If its task journal is absent, this is a no-op and does not
/// create one.
pub fn rebase_normalized_output_refs_for_relocated_store(
    source_kio: &Path,
    destination_kio: &Path,
) -> Result<()> {
    let destination_store = TaskStore::new(destination_kio);
    // Retain this descriptor through the complete read/validate/replace
    // sequence. A same-UID actor can rename the public `.kio` pathname after
    // validation; resolving the journal through that pathname again would
    // otherwise target a different store.
    let destination_dir = open_checked_store_dir(destination_kio)?;
    let task_name = Path::new("tasks.jsonl");
    let listed = match cap_fs::stat(&destination_dir, task_name, cap_fs::FollowSymlinks::No) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error).pipeline_io(&destination_store.path),
    };
    if !listed.file_type().is_file() {
        return Err(PipelineError::corrupt(
            destination_store.path.display().to_string(),
            "store object has an unexpected filesystem type",
        ));
    }
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let file =
        cap_fs::open(&destination_dir, task_name, &options).pipeline_io(&destination_store.path)?;
    let opened = cap_fs::Metadata::from_file(&file).pipeline_io(&destination_store.path)?;
    if !opened.file_type().is_file() || !same_cap_file_identity(&listed, &opened) {
        return Err(PipelineError::corrupt(
            destination_store.path.display().to_string(),
            "task journal changed while it was being opened",
        ));
    }
    // Keep a descriptor for the post-read state check.  Reading by a clone
    // shares the underlying immutable file identity without reopening its
    // pathname.
    let reader = file.try_clone().pipeline_io(&destination_store.path)?;
    let mut tasks = destination_store.read_descriptors(reader, |descriptor| {
        validate_task_descriptor_fields(destination_kio, descriptor)?;
        let mut rebased = descriptor.clone();
        rebase_task_output_ref(source_kio, destination_kio, &mut rebased)
    })?;
    let after_read = cap_fs::Metadata::from_file(&file).pipeline_io(&destination_store.path)?;
    if !same_cap_file_state(&opened, &after_read) {
        return Err(PipelineError::corrupt(
            destination_store.path.display().to_string(),
            "task journal changed while it was being read",
        ));
    }

    for task in &mut tasks {
        rebase_task_output_ref(source_kio, destination_kio, task)?;
    }
    replace_relocated_task_journal(&destination_dir, &destination_store, &opened, &tasks)
}

/// Bind the destination store once, without retaining its public pathname as
/// authority for its children.
fn open_checked_store_dir(destination_kio: &Path) -> Result<fs::File> {
    let listed = fs::symlink_metadata(destination_kio).pipeline_io(destination_kio)?;
    if listed.file_type().is_symlink() || !listed.file_type().is_dir() {
        return Err(PipelineError::corrupt(
            destination_kio.display().to_string(),
            "Kio store root is not a real directory",
        ));
    }
    let canonical = destination_kio
        .canonicalize()
        .pipeline_io(destination_kio)?;
    let directory =
        cap_fs::open_ambient_dir(&canonical, ambient_authority()).pipeline_io(destination_kio)?;
    let opened = cap_fs::Metadata::from_file(&directory).pipeline_io(destination_kio)?;
    if !opened.file_type().is_dir() || !same_store_directory_identity(&listed, &opened) {
        return Err(PipelineError::corrupt(
            destination_kio.display().to_string(),
            "Kio store root changed while it was being opened",
        ));
    }
    Ok(directory)
}

fn replace_relocated_task_journal(
    destination_dir: &fs::File,
    destination_store: &TaskStore,
    expected_journal: &cap_fs::Metadata,
    descriptors: &[TaskDescriptor],
) -> Result<()> {
    if descriptors.len() > MAX_TASK_RECORDS {
        return Err(PipelineError::corrupt(
            destination_store.path.display().to_string(),
            format!("tasks.jsonl exceeds {MAX_TASK_RECORDS} record limit"),
        ));
    }
    for descriptor in descriptors {
        validate_task_descriptor(destination_store.kio_dir(), descriptor)?;
    }
    let (mut file, temporary_name) =
        create_relocated_task_temp(destination_dir, destination_store)?;
    let result = (|| -> Result<()> {
        let mut total_bytes = 0u64;
        for descriptor in descriptors {
            let line = destination_store.framed_record(descriptor)?;
            total_bytes = total_bytes.saturating_add(line.len() as u64);
            if total_bytes > MAX_TASK_STORE_BYTES {
                return Err(PipelineError::corrupt(
                    destination_store.path.display().to_string(),
                    format!("tasks.jsonl exceeds {MAX_TASK_STORE_BYTES} byte limit"),
                ));
            }
            file.write_all(&line).pipeline_io(&destination_store.path)?;
        }
        file.sync_all().pipeline_io(&destination_store.path)?;
        drop(file);
        let current = cap_fs::stat(
            destination_dir,
            Path::new("tasks.jsonl"),
            cap_fs::FollowSymlinks::No,
        )
        .pipeline_io(&destination_store.path)?;
        if !current.file_type().is_file() || !same_cap_file_state(expected_journal, &current) {
            return Err(PipelineError::corrupt(
                destination_store.path.display().to_string(),
                "task journal changed while it was being rebased",
            ));
        }
        cap_fs::rename(
            destination_dir,
            Path::new(&temporary_name),
            destination_dir,
            Path::new("tasks.jsonl"),
        )
        .pipeline_io(&destination_store.path)?;
        destination_dir
            .sync_all()
            .pipeline_io(&destination_store.path)
    })();
    if result.is_err() {
        let _ = cap_fs::remove_file(destination_dir, Path::new(&temporary_name));
    }
    result
}

fn create_relocated_task_temp(
    destination_dir: &fs::File,
    destination_store: &TaskStore,
) -> Result<(fs::File, String)> {
    static SEQ: AtomicU64 = AtomicU64::new(0);
    for _ in 0..8 {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|elapsed| elapsed.as_nanos())
            .unwrap_or(0);
        let sequence = SEQ.fetch_add(1, Ordering::Relaxed);
        let name = format!(".tasks.jsonl.{}.{nanos}.{sequence}.tmp", std::process::id());
        let mut options = cap_fs::OpenOptions::new();
        options
            .write(true)
            .create_new(true)
            ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
        match cap_fs::open(destination_dir, Path::new(&name), &options) {
            Ok(file) => return Ok((file, name)),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error).pipeline_io(&destination_store.path),
        }
    }
    Err(PipelineError::Io {
        path: destination_store.path.display().to_string(),
        message: "could not create a unique temp file for tasks.jsonl".to_owned(),
    })
}

#[cfg(unix)]
fn same_store_directory_identity(listed: &fs::Metadata, opened: &cap_fs::Metadata) -> bool {
    use cap_fs::MetadataExt as CapMetadataExt;
    use std::os::unix::fs::MetadataExt as StdMetadataExt;
    listed.dev() == opened.dev() && listed.ino() == opened.ino()
}

#[cfg(windows)]
fn same_store_directory_identity(listed: &fs::Metadata, opened: &cap_fs::Metadata) -> bool {
    use cap_fs::MetadataExt as CapMetadataExt;
    use std::os::windows::fs::MetadataExt as StdMetadataExt;
    listed.volume_serial_number() == opened.volume_serial_number()
        && listed.file_index() == opened.file_index()
}

#[cfg(not(any(unix, windows)))]
fn same_store_directory_identity(_listed: &fs::Metadata, opened: &cap_fs::Metadata) -> bool {
    opened.file_type().is_dir()
}

#[cfg(unix)]
fn same_cap_file_identity(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    use cap_fs::MetadataExt;
    left.dev() == right.dev() && left.ino() == right.ino()
}

#[cfg(unix)]
fn same_cap_file_state(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    use cap_fs::MetadataExt;
    same_cap_file_identity(left, right)
        && left.len() == right.len()
        && left.mtime() == right.mtime()
        && left.mtime_nsec() == right.mtime_nsec()
        && left.ctime() == right.ctime()
        && left.ctime_nsec() == right.ctime_nsec()
}

#[cfg(not(unix))]
fn same_cap_file_state(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    same_cap_file_identity(left, right) && left.len() == right.len()
}

#[cfg(windows)]
fn same_cap_file_identity(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    use cap_fs::MetadataExt;
    left.volume_serial_number() == right.volume_serial_number()
        && left.file_index() == right.file_index()
}

#[cfg(not(any(unix, windows)))]
fn same_cap_file_identity(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    left.len() == right.len() && left.modified().ok() == right.modified().ok()
}

fn rebase_task_output_ref(
    source_kio: &Path,
    destination_kio: &Path,
    descriptor: &mut TaskDescriptor,
) -> Result<()> {
    if descriptor.output_ref.starts_with("online:")
        || descriptor.output_ref.starts_with("offline:")
        || descriptor.output_ref.starts_with("embedding:")
    {
        validate_task_output_ref(destination_kio, descriptor)?;
        return Ok(());
    }

    if descriptor.task_type != TaskType::Markdownize {
        return Err(invalid_output_ref(destination_kio, &descriptor.output_ref));
    }
    let source_root = source_kio.join("objects/normalized_units");
    let persisted = Path::new(&descriptor.output_ref);
    let relative = persisted
        .strip_prefix(&source_root)
        .map_err(|_| invalid_output_ref(destination_kio, &descriptor.output_ref))?;
    let components = relative
        .components()
        .map(|component| match component {
            Component::Normal(value) => value.to_str().map(str::to_owned),
            _ => None,
        })
        .collect::<Option<Vec<_>>>()
        .ok_or_else(|| invalid_output_ref(destination_kio, &descriptor.output_ref))?;
    if components.len() != 3 {
        return Err(invalid_output_ref(destination_kio, &descriptor.output_ref));
    }
    let digest = descriptor
        .input_hash
        .strip_prefix("sha256:")
        .ok_or_else(|| invalid_output_ref(destination_kio, &descriptor.output_ref))?;
    if components[0] != digest[0..2] || components[1] != digest[2..4] {
        return Err(invalid_output_ref(destination_kio, &descriptor.output_ref));
    }
    let (tool_profile_hash, r#gen) =
        parse_normalized_output_basename(&descriptor.input_hash, &components[2])
            .ok_or_else(|| invalid_output_ref(destination_kio, &descriptor.output_ref))?;
    let expected_source = crate::markdownize::normalized_instance_dir(
        source_kio,
        &descriptor.input_hash,
        &tool_profile_hash,
        r#gen,
    );
    if expected_source.to_str() != Some(descriptor.output_ref.as_str()) {
        return Err(invalid_output_ref(destination_kio, &descriptor.output_ref));
    }
    descriptor.output_ref = crate::markdownize::normalized_instance_dir(
        destination_kio,
        &descriptor.input_hash,
        &tool_profile_hash,
        r#gen,
    )
    .to_str()
    .ok_or_else(|| invalid_output_ref(destination_kio, &descriptor.output_ref))?
    .to_owned();
    validate_task_output_ref(destination_kio, descriptor)?;
    Ok(())
}

/// Whether `input_path` names a direct child of the scope root: a single
/// `Component::Normal` — not absolute, no path separator, no `.`/`..` traversal
/// (03 §3.3). Rejects `""`, `/etc/hosts`, `../x`, `a/b`, `.`, `..` (P1).
#[must_use]
pub fn is_scope_local_file_name(input_path: &str) -> bool {
    if input_path.is_empty() || input_path.contains('/') || input_path.contains('\\') {
        return false;
    }
    let mut components = Path::new(input_path).components();
    matches!(components.next(), Some(Component::Normal(_))) && components.next().is_none()
}

fn parse_normalized_output_basename(input_hash: &str, name: &str) -> Option<(String, u64)> {
    let raw_digest = input_hash.strip_prefix("sha256:")?;
    let canonical_suffix = name.strip_prefix(&format!("{raw_digest}."));
    if let Some(suffix) = canonical_suffix {
        let (tool_digest, gen_text) = suffix.rsplit_once(".g")?;
        if is_lower_sha256_digest(tool_digest) && is_canonical_generation(gen_text) {
            let r#gen = gen_text.parse::<u64>().ok()?;
            return Some((format!("sha256:{tool_digest}"), r#gen));
        }
        return None;
    }

    None
}

fn is_lower_sha256_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn is_canonical_generation(value: &str) -> bool {
    !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit())
}

/// Validate and classify a persisted task output reference before any consumer
/// turns it into a filesystem path.
pub fn validate_task_output_ref(
    kio_dir: impl AsRef<Path>,
    descriptor: &TaskDescriptor,
) -> Result<TaskOutputRef> {
    if !kio_core::cas::is_hash(&descriptor.input_hash) {
        return Err(invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref));
    }
    if let Some(adapter_id) = descriptor.output_ref.strip_prefix("online:") {
        if descriptor.task_type != TaskType::Markdownize || !is_safe_logical_id(adapter_id) {
            return Err(invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref));
        }
        return Ok(TaskOutputRef::Online {
            adapter_id: adapter_id.to_owned(),
        });
    }
    if let Some(adapter_id) = descriptor.output_ref.strip_prefix("offline:") {
        if descriptor.task_type != TaskType::Markdownize || !is_safe_logical_id(adapter_id) {
            return Err(invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref));
        }
        return Ok(TaskOutputRef::Offline {
            adapter_id: adapter_id.to_owned(),
        });
    }
    if let Some(chunk_id) = descriptor.output_ref.strip_prefix("embedding:") {
        if descriptor.task_type != TaskType::Embedding || !kio_core::cas::is_hash(chunk_id) {
            return Err(invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref));
        }
        return Ok(TaskOutputRef::Embedding {
            chunk_id: chunk_id.to_owned(),
        });
    }
    if descriptor.task_type != TaskType::Markdownize {
        return Err(invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref));
    }

    let persisted = Path::new(&descriptor.output_ref);
    let has_parent_component = persisted
        .components()
        .any(|component| matches!(component, Component::ParentDir));
    let has_current_component = persisted
        .components()
        .any(|component| matches!(component, Component::CurDir));
    let has_prefix = persisted
        .components()
        .any(|component| matches!(component, Component::Prefix(_)));
    let has_root = persisted
        .components()
        .any(|component| matches!(component, Component::RootDir));
    // Descriptor-bound child indexing deliberately addresses the retained
    // `.kio` directory as `.`. Its canonical normalized-instance spelling is
    // therefore `./objects/...`; accept that one relative spelling only when
    // the task store itself is descriptor-bound to `.`. Ordinary repositories
    // still require an absolute canonical output reference, and `..` remains
    // forbidden in every mode.
    let bound_relative_root = kio_dir.as_ref() == Path::new(".");
    if has_parent_component
        || (has_current_component && !bound_relative_root)
        || ((has_prefix || has_root) && !persisted.is_absolute())
    {
        return Err(invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref));
    }
    let current_dir = std::env::current_dir().map_err(|err| PipelineError::Io {
        path: descriptor.output_ref.clone(),
        message: err.to_string(),
    })?;
    let absolute = if persisted.is_absolute() {
        persisted.to_path_buf()
    } else {
        current_dir.join(persisted)
    };
    let normalized_root = kio_dir.as_ref().join("objects/normalized_units");
    let absolute_root = if normalized_root.is_absolute() {
        normalized_root.clone()
    } else {
        current_dir.join(&normalized_root)
    };
    let relative = absolute
        .strip_prefix(&absolute_root)
        .map_err(|_| invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref))?;
    let components = relative
        .components()
        .filter_map(|component| match component {
            Component::Normal(value) => value.to_str().map(str::to_owned),
            _ => None,
        })
        .collect::<Vec<_>>();
    if components.len() != 3 {
        return Err(invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref));
    }
    let digest = descriptor
        .input_hash
        .strip_prefix("sha256:")
        .ok_or_else(|| invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref))?;
    if components[0] != digest[0..2] || components[1] != digest[2..4] {
        return Err(invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref));
    }
    let (tool_profile_hash, r#gen) =
        parse_normalized_output_basename(&descriptor.input_hash, &components[2])
            .ok_or_else(|| invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref))?;
    // `output_ref` is a durable identity, not merely a path that resolves to
    // the generated instance. Reconstruct its sole canonical spelling so
    // aliases such as trailing separators, doubled separators, or cwd-relative
    // paths cannot make a completed task invisible to `done_output_for`.
    // Ordinary stores retain the exact absolute spelling as their durable
    // identity. A descriptor-bound child deliberately persists the
    // discovery-time canonical `.kio` path instead of its operational `.`
    // path; the structural checks above prove that it names the same retained
    // `objects/normalized_units` subtree, while comparing it to
    // `normalized_instance_dir(".", ..)` would falsely reject it as an alias.
    if !bound_relative_root {
        let canonical = crate::markdownize::normalized_instance_dir(
            kio_dir.as_ref(),
            &descriptor.input_hash,
            &tool_profile_hash,
            r#gen,
        );
        if canonical.to_str() != Some(descriptor.output_ref.as_str()) {
            return Err(invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref));
        }
    }

    // Validate every existing component from `.kio` downward. In particular,
    // `normalized_units` cannot become a second trust root by being a symlink.
    let store_relative = Path::new("objects").join("normalized_units").join(relative);
    resolve_existing_store_path(kio_dir.as_ref(), &store_relative, StorePathKind::Directory)
        .map_err(|_| invalid_output_ref(kio_dir.as_ref(), &descriptor.output_ref))?;

    Ok(TaskOutputRef::NormalizedInstance {
        path: absolute,
        raw_hash: descriptor.input_hash.clone(),
        tool_profile_hash,
        r#gen,
    })
}

/// Open a deferred task input once and enforce the byte cap on that same file
/// handle. Metadata rejects the common oversized case before allocation; the
/// `max + 1` streaming guard also contains growth after the metadata read.
#[must_use]
pub fn read_capped_task_input(path: impl AsRef<Path>, max_bytes: u64) -> CappedTaskInput {
    let Ok(file) = fs::File::open(path.as_ref()) else {
        return CappedTaskInput::Unavailable;
    };
    let Ok(metadata) = file.metadata() else {
        return CappedTaskInput::Unavailable;
    };
    if !metadata.is_file() {
        return CappedTaskInput::NotRegular;
    }
    if metadata.len() > max_bytes {
        return CappedTaskInput::TooLarge;
    }
    let capacity = usize::try_from(metadata.len().min(max_bytes)).unwrap_or(0);
    let mut bytes = Vec::with_capacity(capacity);
    let mut limited = file.take(max_bytes.saturating_add(1));
    if limited.read_to_end(&mut bytes).is_err() {
        return CappedTaskInput::Unavailable;
    }
    if bytes.len() as u64 > max_bytes {
        CappedTaskInput::TooLarge
    } else {
        CappedTaskInput::Bytes(bytes)
    }
}

/// Map the durable failure reason to the retry contract. Unknown or absent
/// reasons fail closed as a contract violation.
#[must_use]
pub fn task_retry_kind(task: &TaskDescriptor) -> RetryErrorKind {
    match task.fallback_reason.as_deref() {
        Some("network_error") => RetryErrorKind::NetworkError,
        Some("rate_limit") => RetryErrorKind::RateLimit,
        Some("auth_error") => RetryErrorKind::AuthError,
        Some("quota_exceeded") => RetryErrorKind::QuotaExceeded,
        Some("invalid_input") | Some(RETIRED_NON_LIVE_REASON) => RetryErrorKind::InvalidInput,
        Some(BUDGET_EXCEEDED_REASON) => RetryErrorKind::BudgetExceeded,
        _ => RetryErrorKind::ContractViolation,
    }
}

#[must_use]
pub fn task_retry_allowed(task: &TaskDescriptor) -> bool {
    let policy = retry_policy(task_retry_kind(task));
    policy.retryable
        && policy
            .max_attempts
            .map(|max| task.attempts < max)
            .unwrap_or(true)
}

#[must_use]
pub fn task_failure_is_terminal(task: &TaskDescriptor) -> bool {
    task.status == TaskStatus::Failed && !task_retry_allowed(task)
}

/// A destructive secret-hold transition is safe only for fresh pending work.
/// Failed tasks retain their retry/backoff state; classification still keeps the
/// corresponding content out of the sendable partition.
#[must_use]
pub fn task_can_enter_secret_hold(task: &TaskDescriptor) -> bool {
    task.task_type == TaskType::Embedding && task.status == TaskStatus::Pending
}

/// Materialized output can converge ordinary work, budget pauses, AND (QA2,
/// step4b-contract-tests-p3a.md §A) auth pauses to `Done` — a chunk/unit
/// whose vector or normalized output already exists (e.g. via a
/// content-identity twin) satisfies an auth-paused task the same way it
/// satisfies a budget-paused one, since the auth hold never blocked anything
/// but THIS task's own send. Secret and unknown holds remain sticky because
/// they may represent an unsatisfied authorization boundary.
#[must_use]
pub fn task_can_complete_from_materialized_output(task: &TaskDescriptor) -> bool {
    match task.status {
        TaskStatus::Pending | TaskStatus::Running | TaskStatus::Failed => true,
        TaskStatus::Paused => matches!(
            task.fallback_reason.as_deref(),
            Some(BUDGET_EXCEEDED_REASON) | Some("auth_error")
        ),
        TaskStatus::Done | TaskStatus::Partial => false,
    }
}

/// QA2 (step4b-contract-tests-p3a.md §A, 04 §5.2): an auth failure now lands
/// `Paused` (never `Failed`), so revival on `batch resume` is Paused-based.
#[must_use]
pub fn task_auth_revival_allowed(task: &TaskDescriptor, mode: TaskRecoveryMode) -> bool {
    mode == TaskRecoveryMode::Resume
        && task.status == TaskStatus::Paused
        && task_retry_kind(task) == RetryErrorKind::AuthError
}

impl TaskDescriptor {
    #[must_use]
    pub fn reservation_claim(&self) -> Option<TaskReservationClaim<'_>> {
        match (
            self.reservation_id.as_deref(),
            self.reserved_usd,
            self.reserved_month.as_deref(),
        ) {
            (Some(reservation_id), Some(usd), Some(month)) => Some(TaskReservationClaim {
                reservation_id,
                task_id: &self.task_id,
                usd,
                month,
            }),
            _ => None,
        }
    }

    pub fn clear_reservation(&mut self) {
        self.reservation_id = None;
        self.reserved_usd = None;
        self.reserved_month = None;
    }
}

fn validate_task_descriptor(kio_dir: &Path, descriptor: &TaskDescriptor) -> Result<()> {
    validate_task_descriptor_fields(kio_dir, descriptor)?;
    let output = validate_task_output_ref(kio_dir, descriptor)?;
    if matches!(output, TaskOutputRef::Online { .. })
        && descriptor.bbox_annotation_enabled.is_none()
    {
        return Err(PipelineError::corrupt(
            kio_dir.join("tasks.jsonl").display().to_string(),
            "online Markdownize task is missing bbox_annotation_enabled policy stamp".to_owned(),
        ));
    }
    Ok(())
}

fn validate_task_descriptor_fields(kio_dir: &Path, descriptor: &TaskDescriptor) -> Result<()> {
    let corrupt = |message: String| {
        PipelineError::corrupt(kio_dir.join("tasks.jsonl").display().to_string(), message)
    };
    if descriptor.task_id.is_empty()
        || descriptor.task_id.len() > MAX_TASK_ID_BYTES
        || !is_safe_logical_id(&descriptor.task_id)
    {
        return Err(corrupt(
            "task_id is not a bounded logical identifier".to_owned(),
        ));
    }
    if descriptor.input_path.len() > MAX_TASK_PATH_BYTES
        || !is_scope_local_file_name(&descriptor.input_path)
    {
        return Err(PipelineError::path(descriptor.input_path.clone()));
    }
    if !kio_core::cas::is_hash(&descriptor.input_hash) {
        return Err(corrupt(format!(
            "task input_hash is not a valid hash: {}",
            descriptor.input_hash
        )));
    }
    if let Some(previous) = &descriptor.previous_raw_hash
        && !kio_core::cas::is_hash(previous)
    {
        return Err(corrupt(format!(
            "task previous_raw_hash is not a valid hash: {previous}"
        )));
    }
    if descriptor.changed_unit_keys.len() > MAX_TASK_UNIT_KEYS
        || descriptor
            .unit_keys
            .as_ref()
            .is_some_and(|keys| keys.len() > MAX_TASK_UNIT_KEYS)
    {
        return Err(corrupt(format!(
            "task unit key count exceeds {MAX_TASK_UNIT_KEYS}"
        )));
    }
    if descriptor
        .changed_unit_keys
        .iter()
        .chain(descriptor.unit_keys.iter().flatten())
        .any(|key| key.is_empty() || key.len() > MAX_TASK_PATH_BYTES || has_control(key))
    {
        return Err(corrupt(
            "task unit key is empty, oversized, or contains controls".to_owned(),
        ));
    }
    if descriptor.output_ref.len() > MAX_TASK_PATH_BYTES {
        return Err(corrupt("task output_ref is oversized".to_owned()));
    }
    match (descriptor.status, descriptor.hold_reason) {
        (TaskStatus::Paused, Some(hold_reason))
            if descriptor
                .fallback_reason
                .as_deref()
                .and_then(hold_reason_for_reason)
                == Some(hold_reason) => {}
        (TaskStatus::Paused, _) => {
            return Err(corrupt(
                "paused task requires a hold_reason matching its fallback_reason".to_owned(),
            ));
        }
        (_, Some(_)) => {
            return Err(corrupt(
                "non-paused task must not carry a hold_reason".to_owned(),
            ));
        }
        (_, None) => {}
    }
    if descriptor
        .fallback_reason
        .as_ref()
        .is_some_and(|value| value.len() > MAX_TASK_REASON_BYTES || has_control(value))
    {
        return Err(corrupt(
            "task fallback_reason is oversized or contains controls".to_owned(),
        ));
    }
    for timestamp in [
        descriptor.next_retry_at.as_deref(),
        descriptor.deadline.as_deref(),
        descriptor.heartbeat_at.as_deref(),
        Some(descriptor.created_at.as_str()),
    ]
    .into_iter()
    .flatten()
    {
        if timestamp.len() > MAX_TASK_TIMESTAMP_BYTES || has_control(timestamp) {
            return Err(corrupt(
                "task timestamp is oversized or contains controls".to_owned(),
            ));
        }
    }
    match (
        descriptor.reserved_usd,
        descriptor.reserved_month.as_deref(),
        descriptor.reservation_id.as_deref(),
    ) {
        (None, None, None) => {}
        (Some(usd), Some(month), Some(reservation_id))
            if usd.is_finite()
                && usd >= 0.0
                && is_utc_month(month)
                && is_valid_reservation_id(reservation_id) => {}
        _ => {
            return Err(corrupt(
                "task reservation stamp must be an all-null or valid complete triple".to_owned(),
            ));
        }
    }
    Ok(())
}

fn invalid_output_ref(kio_dir: &Path, output_ref: &str) -> PipelineError {
    PipelineError::corrupt(
        kio_dir.join("tasks.jsonl").display().to_string(),
        format!("task output_ref is not a scoped typed reference: {output_ref}"),
    )
}

fn is_safe_logical_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= MAX_TASK_ID_BYTES
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
}

#[must_use]
pub fn is_valid_reservation_id(value: &str) -> bool {
    is_uuid_shaped(value)
}

/// Whether `value` is a canonical hyphenated UUID (`8-4-4-4-12` lowercase hex).
/// Accepts any UUID version. `cost-ledger.sqlite`'s `intent_token` (a UUIDv7,
/// `kio_pipeline::ledger::ops::new_intent_token`) is stored in
/// `TaskDescriptor::reservation_id` as the durable ledger row selector.
#[must_use]
fn is_uuid_shaped(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 36
        && bytes[8] == b'-'
        && bytes[13] == b'-'
        && bytes[18] == b'-'
        && bytes[23] == b'-'
        && bytes.iter().enumerate().all(|(index, byte)| {
            matches!(index, 8 | 13 | 18 | 23)
                || byte.is_ascii_digit()
                || matches!(byte, b'a'..=b'f')
        })
}

fn is_utc_month(value: &str) -> bool {
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

fn has_control(value: &str) -> bool {
    value.chars().any(char::is_control)
}

#[must_use]
pub fn task_status_from_unit_counts(
    done: usize,
    failed: usize,
    precondition_failed: bool,
) -> TaskStatus {
    if precondition_failed || done == 0 && failed > 0 {
        TaskStatus::Failed
    } else if done > 0 && failed > 0 {
        TaskStatus::Partial
    } else if done > 0 {
        TaskStatus::Done
    } else {
        TaskStatus::Pending
    }
}

#[must_use]
pub fn retry_policy(error_kind: RetryErrorKind) -> RetryPolicy {
    match error_kind {
        RetryErrorKind::NetworkError => RetryPolicy {
            error_kind,
            retryable: true,
            max_attempts: Some(5),
            backoff: "exp(base=2s,cap=60s,full_jitter)".to_owned(),
            error_code: "KIO-E-BATCH-NET-001".to_owned(),
            paused: false,
        },
        RetryErrorKind::RateLimit => RetryPolicy {
            error_kind,
            retryable: true,
            max_attempts: None,
            backoff: "retry_after".to_owned(),
            error_code: "KIO-E-BATCH-RATE-001".to_owned(),
            paused: false,
        },
        // QA2 (step4b-contract-tests-p3a.md §A, 04 §5.2 L679): `paused: true`
        // now truthfully describes the wired transition — an auth failure
        // lands `Paused(hold_reason=auth)`, not `Failed`. The send handlers
        // (kio-cli `main.rs`) branch on `error.retry_kind` directly rather
        // than reading this field, but it is no longer a dead abstraction.
        RetryErrorKind::AuthError => RetryPolicy {
            error_kind,
            retryable: false,
            max_attempts: Some(0),
            backoff: "user_action".to_owned(),
            error_code: "KIO-E-BATCH-AUTH-001".to_owned(),
            paused: true,
        },
        RetryErrorKind::QuotaExceeded => RetryPolicy {
            error_kind,
            retryable: true,
            max_attempts: Some(3),
            backoff: "fixed(1h)".to_owned(),
            error_code: "KIO-E-BATCH-QUOTA-001".to_owned(),
            paused: false,
        },
        RetryErrorKind::InvalidInput => RetryPolicy {
            error_kind,
            retryable: false,
            max_attempts: Some(0),
            backoff: "none".to_owned(),
            error_code: "KIO-E-BATCH-INPUT-001".to_owned(),
            paused: false,
        },
        // QA45 (step4b-contract-tests-p3a.md §M): 04 §5.3 L738-740 —
        // `retryable, max_attempts=1` (one same-mode retry for output jitter;
        // a repeat violation is failed permanent — an Adapter bug, not a
        // transient condition). No automatic fallback to `full` here (that
        // is only for incremental-capability incompatibility, 07 §8.1). This
        // is the LOCAL/offline display value; the durable "1 回のみ" judge
        // for the online/Batch path is `batch_requests.contract_violation_count`
        // (04 §5.2 L723, CL21 — already correct, untouched by this change).
        RetryErrorKind::ContractViolation => RetryPolicy {
            error_kind,
            retryable: true,
            max_attempts: Some(1),
            backoff: "immediate".to_owned(),
            error_code: "KIO-E-ADAPTER-CONTRACT-001".to_owned(),
            paused: false,
        },
        RetryErrorKind::BudgetExceeded => RetryPolicy {
            error_kind,
            retryable: false,
            max_attempts: Some(0),
            backoff: "override_budget_required".to_owned(),
            error_code: "KIO-E-BATCH-BUDGET-001".to_owned(),
            paused: true,
        },
    }
}

#[must_use]
pub fn idempotency_key(input_hash: &str, tool_profile_hash: &str) -> String {
    crate::prepare::hash_bytes(format!("{input_hash}\0{tool_profile_hash}").as_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_task() -> TaskDescriptor {
        TaskDescriptor {
            task_id: "task_01H".to_owned(),
            task_type: TaskType::Markdownize,
            mode: Some(MarkdownizeMode::Full),
            input_path: "report.pdf".to_owned(),
            input_hash: format!("sha256:{}", "a".repeat(64)),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: Vec::new(),
            output_ref: "online:test_markdownize".to_owned(),
            unit_keys: None,
            status: TaskStatus::Pending,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: None,
            created_at: "2026-04-25T12:00:00Z".to_owned(),
            bbox_annotation_enabled: Some(true),
            hold_reason: None,
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        }
    }

    #[test]
    fn placeholder_task_type_field_is_named_type() {
        let descriptor = TaskDescriptor {
            task_id: "task_01H".to_owned(),
            task_type: TaskType::Markdownize,
            mode: Some(MarkdownizeMode::Full),
            input_path: "report.pdf".to_owned(),
            input_hash: "sha256:abc".to_owned(),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: Vec::new(),
            output_ref: ".kio/objects/normalized_units/ab/cd/abc.tool.g0/".to_owned(),
            unit_keys: None,
            status: TaskStatus::Pending,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: None,
            created_at: "2026-04-25T12:00:00Z".to_owned(),
            bbox_annotation_enabled: Some(true),
            hold_reason: None,
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        };

        let value = serde_json::to_value(descriptor).expect("serialize task descriptor");
        assert_eq!(value["type"], "markdownize");
    }

    #[test]
    fn ct4_bbox_006_task_pins_policy_and_requires_current_fields() {
        let mut descriptor = valid_task();
        descriptor.bbox_annotation_enabled = Some(true);

        let value = serde_json::to_value(&descriptor).expect("serialize task descriptor");
        assert_eq!(value["bbox_annotation_enabled"], true);
        assert_eq!(
            serde_json::from_value::<TaskDescriptor>(value.clone())
                .expect("deserialize current task descriptor")
                .bbox_annotation_enabled,
            Some(true)
        );

        for field in [
            "mode",
            "previous_raw_hash",
            "parent_run_id",
            "unit_keys",
            "next_retry_at",
            "deadline",
            "heartbeat_at",
            "fallback_reason",
            "bbox_annotation_enabled",
            "hold_reason",
            "reserved_usd",
            "reserved_month",
            "reservation_id",
        ] {
            let mut missing = value.clone();
            missing
                .as_object_mut()
                .expect("task descriptor serializes as an object")
                .remove(field);
            assert!(
                serde_json::from_value::<TaskDescriptor>(missing).is_err(),
                "current task descriptor must require {field}"
            );
        }

        let mut unknown = value.clone();
        unknown
            .as_object_mut()
            .expect("task descriptor serializes as an object")
            .insert("retired_field".to_owned(), serde_json::Value::Null);
        assert!(
            serde_json::from_value::<TaskDescriptor>(unknown).is_err(),
            "current task descriptor must reject unknown fields"
        );

        let mut unstamped_non_online = valid_task();
        unstamped_non_online.output_ref = "offline:test_markdownize".to_owned();
        unstamped_non_online.bbox_annotation_enabled = None;
        let current = serde_json::to_value(unstamped_non_online).unwrap();
        assert_eq!(current["bbox_annotation_enabled"], serde_json::Value::Null);
        assert_eq!(current["hold_reason"], serde_json::Value::Null);
        assert_eq!(current["reserved_usd"], serde_json::Value::Null);
        assert_eq!(current["reserved_month"], serde_json::Value::Null);
        assert_eq!(current["reservation_id"], serde_json::Value::Null);
    }

    #[test]
    fn is_scope_local_file_name_rejects_traversal_and_absolute() {
        // P1: bare direct-child file names are accepted.
        assert!(is_scope_local_file_name("report.pdf"));
        assert!(is_scope_local_file_name("認証仕様.md"));
        // Absolute paths, separators, and `..`/`.` traversal are rejected.
        for bad in [
            "",
            "/etc/hosts",
            "../../../../etc/hosts",
            "a/b.pdf",
            "sub/report.pdf",
            "..",
            ".",
            "./report.pdf",
            "dir\\report.pdf",
        ] {
            assert!(!is_scope_local_file_name(bad), "should reject {bad:?}");
        }
    }

    #[test]
    fn all_rejects_task_with_out_of_scope_input_path() {
        // P1: a poisoned tasks.jsonl line whose input_path escapes the scope is
        // rejected at read time with KIO-E-STORE-PATH-001, before any consumer can
        // read/send the file.
        let dir = tempfile::tempdir().unwrap();
        let store = TaskStore::new(dir.path());
        let mut task = TaskDescriptor {
            task_id: "task_01H".to_owned(),
            task_type: TaskType::Markdownize,
            mode: Some(MarkdownizeMode::Full),
            input_path: "report.pdf".to_owned(),
            // Q6: a valid CAS-shaped hash so this test exercises the input_path
            // guard (P1), not the input_hash guard added in Q6.
            input_hash: format!("sha256:{}", "a".repeat(64)),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: Vec::new(),
            output_ref: "online:test_markdownize".to_owned(),
            unit_keys: None,
            status: TaskStatus::Pending,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: None,
            created_at: "2026-04-25T12:00:00Z".to_owned(),
            bbox_annotation_enabled: Some(true),
            hold_reason: None,
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        };
        store.append(&task).unwrap();
        // A bare-name task reads back fine.
        assert_eq!(store.all().unwrap().len(), 1);
        // Append a poison line with an absolute input_path.
        task.task_id = "task_02H".to_owned();
        task.input_path = "/etc/hosts".to_owned();
        let mut encoded = serde_json::to_vec(&task).unwrap();
        encoded.push(b'\n');
        OpenOptions::new()
            .append(true)
            .open(dir.path().join("tasks.jsonl"))
            .unwrap()
            .write_all(&encoded)
            .unwrap();
        let err = store.all().unwrap_err();
        assert!(
            matches!(err, PipelineError::Path { .. }),
            "expected KIO-E-STORE-PATH-001, got {err:?}"
        );
        assert!(err.to_string().contains("KIO-E-STORE-PATH-001"));
    }

    #[test]
    fn q6_all_rejects_task_with_malformed_input_hash() {
        // Q6: a poisoned tasks.jsonl whose input_hash is not a CAS hash (here a
        // short "sha256:ab", digest length 2) must be rejected at the single read
        // choke point as STORE-CORRUPT — not slice-panic later in
        // `normalized_instance_dir` (`digest[0..2]` / `[2..4]`, exit 101).
        let dir = tempfile::tempdir().unwrap();
        let store = TaskStore::new(dir.path());
        let task = TaskDescriptor {
            task_id: "task_01H".to_owned(),
            task_type: TaskType::Markdownize,
            mode: Some(MarkdownizeMode::Full),
            input_path: "report.pdf".to_owned(),
            input_hash: "sha256:ab".to_owned(),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: Vec::new(),
            output_ref: "online:test_markdownize".to_owned(),
            unit_keys: None,
            status: TaskStatus::Pending,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: None,
            created_at: "2026-04-25T12:00:00Z".to_owned(),
            bbox_annotation_enabled: None,
            hold_reason: None,
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        };
        let mut encoded = serde_json::to_vec(&task).unwrap();
        encoded.push(b'\n');
        fs::write(dir.path().join("tasks.jsonl"), encoded).unwrap();
        let err = store.all().unwrap_err();
        assert!(
            matches!(err, PipelineError::Corrupt { .. }),
            "expected KIO-E-STORE-CORRUPT-001, got {err:?}"
        );
        assert!(err.to_string().contains("KIO-E-STORE-CORRUPT-001"));
    }

    #[test]
    fn r9_8_replace_all_removes_temp_on_rename_failure() {
        // R9-8: a failed `replace_all` must not leave an orphan
        // `.tasks.jsonl.*.tmp` in the tasks dir. Force the final rename to fail
        // deterministically by making the destination `tasks.jsonl` a directory
        // (`rename(temp_file, dir)` errors) after the temp is created.
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("tasks.jsonl")).unwrap();
        let store = TaskStore::new(dir.path());
        let result = store.replace_all(&[]);
        assert!(result.is_err(), "rename onto a directory must fail");
        let stray: Vec<_> = std::fs::read_dir(dir.path())
            .unwrap()
            .filter_map(std::result::Result::ok)
            .map(|entry| entry.file_name().to_string_lossy().into_owned())
            .filter(|name| name.starts_with(".tasks.jsonl.") && name.ends_with(".tmp"))
            .collect();
        assert!(
            stray.is_empty(),
            "R9-8: temp not cleaned up on failure: {stray:?}"
        );
    }

    /// QA1 (step4b-contract-tests-p3a.md §A): the closed `hold_reason` enum
    /// round-trips the 3 spec values, and all 3 reasons
    /// (`budget_exceeded`/`secrets_tier_b_hold`/`auth_error`) map onto it —
    /// QA2 wires the `auth_error` -> `Paused` transition itself (see the
    /// `HoldReason` doc comment).
    #[test]
    fn qa1_hold_reason_closed_enum_serializes_and_maps_from_fallback_reason() {
        assert_eq!(serde_json::to_value(HoldReason::Budget).unwrap(), "budget");
        assert_eq!(serde_json::to_value(HoldReason::Auth).unwrap(), "auth");
        assert_eq!(
            serde_json::to_value(HoldReason::TierBApproval).unwrap(),
            "tier_b_approval"
        );
        assert_eq!(
            hold_reason_for_reason(BUDGET_EXCEEDED_REASON),
            Some(HoldReason::Budget)
        );
        assert_eq!(
            hold_reason_for_reason(SECRETS_TIER_B_HOLD_REASON),
            Some(HoldReason::TierBApproval)
        );
        assert_eq!(hold_reason_for_reason("auth_error"), Some(HoldReason::Auth));
        assert_eq!(hold_reason_for_reason("network_error"), None);
        assert_eq!(hold_reason_for_reason("rate_limit"), None);

        // `hold_reason` is explicitly null on a current row when it is absent.
        let mut task = valid_task();
        task.status = TaskStatus::Paused;
        task.fallback_reason = Some(BUDGET_EXCEEDED_REASON.to_owned());
        task.hold_reason = Some(HoldReason::Budget);
        let value = serde_json::to_value(&task).unwrap();
        assert_eq!(value["hold_reason"], "budget");
        let current: TaskDescriptor = serde_json::from_value(value).unwrap();
        assert_eq!(current.hold_reason, Some(HoldReason::Budget));
    }

    #[test]
    fn task_state_and_retry_policies_match_p0_contract() {
        assert_eq!(task_status_from_unit_counts(2, 0, false), TaskStatus::Done);
        assert_eq!(
            task_status_from_unit_counts(1, 1, false),
            TaskStatus::Partial
        );
        assert_eq!(
            task_status_from_unit_counts(0, 2, false),
            TaskStatus::Failed
        );
        assert_eq!(
            retry_policy(RetryErrorKind::NetworkError).error_code,
            "KIO-E-BATCH-NET-001"
        );
        assert_eq!(
            retry_policy(RetryErrorKind::NetworkError).max_attempts,
            Some(5)
        );
        assert_eq!(retry_policy(RetryErrorKind::RateLimit).max_attempts, None);
        assert!(retry_policy(RetryErrorKind::BudgetExceeded).paused);
        assert_eq!(
            retry_policy(RetryErrorKind::ContractViolation).error_code,
            "KIO-E-ADAPTER-CONTRACT-001"
        );
    }

    /// QA16 (step4b-contract-tests-p3a.md §F, 07 §4 L286-290): `AdapterError`
    /// lives in `kio-adapter`, which cannot depend on `kio-pipeline`, so
    /// `AdapterError::error_code`/`error_category` independently duplicate
    /// this crate's `retry_policy`/`RetryErrorKind` classification instead of
    /// deriving from it. This is the "接続" (connection) proof: every
    /// `AdapterError` variant's `error_code()` matches the `error_code` this
    /// crate's `retry_policy` assigns to the `RetryErrorKind`
    /// `task_failure_from_adapter` (kio-cli) maps it to — the two tables
    /// cannot silently drift apart without failing this test. `error_category`
    /// is cross-checked against `retry_policy(...).retryable`: `Permanent`
    /// <-> non-retryable, `RateLimit`/`Transient` <-> retryable (07 §4 L287:
    /// error_category is the coarse rollup, not an independent classifier).
    #[test]
    fn qa16_adapter_error_code_matches_retry_policy() {
        use kio_adapter::AdapterError;
        use kio_adapter::types::ErrorCategory;

        // (AdapterError, the RetryErrorKind `task_failure_from_adapter` maps
        // it to in crates/kio-cli/src/main.rs).
        let cases: &[(AdapterError, RetryErrorKind)] = &[
            (
                AdapterError::Auth("x".to_owned()),
                RetryErrorKind::AuthError,
            ),
            (AdapterError::rate_limit("x"), RetryErrorKind::RateLimit),
            (
                AdapterError::QuotaExceeded("x".to_owned()),
                RetryErrorKind::QuotaExceeded,
            ),
            (
                AdapterError::Network("x".to_owned()),
                RetryErrorKind::NetworkError,
            ),
            (
                AdapterError::Io {
                    path: "p".to_owned(),
                    message: "m".to_owned(),
                },
                RetryErrorKind::NetworkError,
            ),
            (
                AdapterError::ContractViolation("x".to_owned()),
                RetryErrorKind::ContractViolation,
            ),
            (
                AdapterError::ConfigSchema("x".to_owned()),
                RetryErrorKind::ContractViolation,
            ),
            // Carrying an operator-facing code does not change what the
            // AdapterRun path sees: still a contract violation.
            (
                AdapterError::ConfigSchemaCoded {
                    code: "KIO-E-EMBED-MODALITY-001",
                    message: "x".to_owned(),
                },
                RetryErrorKind::ContractViolation,
            ),
        ];
        for (error, retry_kind) in cases {
            let policy = retry_policy(*retry_kind);
            assert_eq!(
                error.error_code(),
                policy.error_code,
                "{error:?} <-> {retry_kind:?}: error_code must match retry_policy's"
            );
            match error.error_category() {
                ErrorCategory::Permanent => assert!(
                    !policy.retryable,
                    "{error:?}: Permanent must mean retry_policy says non-retryable"
                ),
                ErrorCategory::Transient | ErrorCategory::RateLimit => assert!(
                    policy.retryable,
                    "{error:?}: Transient/RateLimit must mean retry_policy says retryable"
                ),
            }
        }
    }

    #[test]
    fn cand_050_task_store_rejects_oversized_file_before_reading() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("tasks.jsonl");
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        file.set_len(MAX_TASK_STORE_BYTES + 1).unwrap();
        let err = TaskStore::new(dir.path()).all().unwrap_err();
        assert!(matches!(err, PipelineError::Corrupt { .. }));
        assert!(err.to_string().contains("exceeds"));
    }

    #[test]
    fn cand_050_task_store_rejects_record_before_unbounded_line_allocation() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("tasks.jsonl");
        let mut bytes = vec![b' '; MAX_TASK_RECORD_BYTES as usize + 1];
        bytes.push(b'\n');
        fs::write(path, bytes).unwrap();
        let err = TaskStore::new(dir.path()).all().unwrap_err();
        assert!(matches!(err, PipelineError::Corrupt { .. }));
        assert!(err.to_string().contains("task record exceeds"));
    }

    #[test]
    fn cand_050_task_writer_and_reader_share_the_framed_record_boundary() {
        let mut task = valid_task();
        task.changed_unit_keys = vec!["x".repeat(MAX_TASK_PATH_BYTES); 63];
        let current_len = serde_json::to_vec(&task).unwrap().len();
        let target_json_len = MAX_TASK_RECORD_BYTES as usize - 1;
        let added_json_overhead = 3;
        let padding_len = target_json_len
            .checked_sub(current_len + added_json_overhead)
            .unwrap();
        assert!(padding_len <= MAX_TASK_PATH_BYTES);
        task.changed_unit_keys.push("y".repeat(padding_len));
        assert_eq!(
            serde_json::to_vec(&task).unwrap().len() + 1,
            MAX_TASK_RECORD_BYTES as usize
        );

        let append_dir = tempfile::tempdir().unwrap();
        let append_store = TaskStore::new(append_dir.path());
        append_store.append(&task).unwrap();
        assert_eq!(append_store.all().unwrap(), vec![task.clone()]);

        let replace_dir = tempfile::tempdir().unwrap();
        let replace_store = TaskStore::new(replace_dir.path());
        replace_store.replace_all(&[task.clone()]).unwrap();
        assert_eq!(replace_store.all().unwrap(), vec![task.clone()]);

        let last = task.changed_unit_keys.last_mut().unwrap();
        last.push('z');
        assert!(append_store.append(&task).is_err());
        assert!(replace_store.replace_all(&[task]).is_err());
    }

    #[test]
    fn cand_050_task_store_bounds_collection_cardinality_and_keeps_valid_control() {
        let dir = tempfile::tempdir().unwrap();
        let store = TaskStore::new(dir.path());
        store.append(&valid_task()).unwrap();
        assert_eq!(store.all().unwrap(), vec![valid_task()]);

        let mut oversized = valid_task();
        oversized.task_id = "task_02H".to_owned();
        oversized.changed_unit_keys = (0..=MAX_TASK_UNIT_KEYS)
            .map(|index| format!("page:{index}"))
            .collect();
        let err = store.append(&oversized).unwrap_err();
        assert!(matches!(err, PipelineError::Corrupt { .. }));
        assert!(err.to_string().contains("unit key count"));
        assert_eq!(store.all().unwrap(), vec![valid_task()]);
    }

    #[test]
    fn cand_047_output_ref_is_typed_and_bound_to_the_task_store() {
        let dir = tempfile::tempdir().unwrap();
        let foreign_dir = tempfile::tempdir().unwrap();
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_hash = format!("sha256:{}", "b".repeat(64));
        let mut task = valid_task();
        task.input_hash = raw_hash.clone();
        task.output_ref =
            crate::markdownize::normalized_instance_dir(dir.path(), &raw_hash, &tool_hash, 7)
                .display()
                .to_string();
        fs::create_dir_all(&task.output_ref).unwrap();
        assert!(matches!(
            validate_task_output_ref(dir.path(), &task).unwrap(),
            TaskOutputRef::NormalizedInstance { r#gen: 7, .. }
        ));

        for foreign in [
            "/tmp/foreign/manifest-parent".to_owned(),
            "../foreign/normalized-instance".to_owned(),
            crate::markdownize::normalized_instance_dir(
                foreign_dir.path(),
                &raw_hash,
                &tool_hash,
                7,
            )
            .display()
            .to_string(),
        ] {
            task.output_ref = foreign;
            assert!(validate_task_output_ref(dir.path(), &task).is_err());
        }

        let mut poisoned = valid_task();
        poisoned.input_hash = raw_hash.clone();
        poisoned.output_ref = crate::markdownize::normalized_instance_dir(
            foreign_dir.path(),
            &raw_hash,
            &tool_hash,
            7,
        )
        .display()
        .to_string();
        let store = TaskStore::new(dir.path());
        let mut encoded = serde_json::to_vec(&poisoned).unwrap();
        encoded.push(b'\n');
        fs::write(dir.path().join("tasks.jsonl"), encoded).unwrap();
        assert!(matches!(store.all(), Err(PipelineError::Corrupt { .. })));

        let mut embedding = valid_task();
        embedding.task_type = TaskType::Embedding;
        embedding.output_ref = format!("embedding:sha256:{}", "c".repeat(64));
        assert!(matches!(
            validate_task_output_ref(dir.path(), &embedding).unwrap(),
            TaskOutputRef::Embedding { .. }
        ));
    }

    #[test]
    fn canonical_output_ref_rejects_noncanonical_generation() {
        let dir = tempfile::tempdir().unwrap();
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_hash = format!("sha256:{}", "b".repeat(64));
        let canonical =
            crate::markdownize::normalized_instance_dir(dir.path(), &raw_hash, &tool_hash, 1);
        let malformed =
            canonical.with_file_name(format!("{}.{}.g+1", "a".repeat(64), "b".repeat(64)));
        let mut task = valid_task();
        task.input_hash = raw_hash;
        task.output_ref = malformed.display().to_string();
        assert!(validate_task_output_ref(dir.path(), &task).is_err());
    }

    #[test]
    fn normalized_output_ref_requires_canonical_basename_and_exact_persisted_ref() {
        let dir = tempfile::tempdir().unwrap();
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_hash = format!("sha256:{}", "b".repeat(64));
        let canonical =
            crate::markdownize::normalized_instance_dir(dir.path(), &raw_hash, &tool_hash, 7);
        let legacy = canonical.with_file_name(format!("{raw_hash}.{tool_hash}.g7"));
        fs::create_dir_all(&canonical).unwrap();

        let mut task = valid_task();
        task.input_hash = raw_hash.clone();
        task.output_ref = canonical.display().to_string();
        task.status = TaskStatus::Done;
        assert!(matches!(
            validate_task_output_ref(dir.path(), &task).unwrap(),
            TaskOutputRef::NormalizedInstance {
                tool_profile_hash,
                r#gen: 7,
                ..
            } if tool_profile_hash == tool_hash
        ));

        let store = TaskStore::new(dir.path());
        store.append(&task).unwrap();
        assert!(
            store
                .done_output_for(&raw_hash, &canonical.display().to_string())
                .unwrap()
                .is_some()
        );

        task.output_ref = legacy.display().to_string();
        assert!(validate_task_output_ref(dir.path(), &task).is_err());
        assert!(
            store
                .done_output_for(&raw_hash, &legacy.display().to_string())
                .unwrap()
                .is_none()
        );
    }

    #[test]
    fn normalized_output_ref_rejects_path_spelling_aliases() {
        let cwd = std::env::current_dir().unwrap();
        let dir = tempfile::Builder::new()
            .prefix("kio-task-output-ref-")
            .tempdir_in(&cwd)
            .unwrap();
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_hash = format!("sha256:{}", "b".repeat(64));
        let canonical =
            crate::markdownize::normalized_instance_dir(dir.path(), &raw_hash, &tool_hash, 7);
        fs::create_dir_all(&canonical).unwrap();

        let mut task = valid_task();
        task.input_hash = raw_hash;
        task.output_ref = canonical.display().to_string();
        assert!(validate_task_output_ref(dir.path(), &task).is_ok());

        let parent = canonical.parent().unwrap().display();
        let file_name = canonical.file_name().unwrap().to_str().unwrap();
        let relative = canonical.strip_prefix(&cwd).unwrap().display().to_string();
        for alias in [
            format!("{}{}", canonical.display(), std::path::MAIN_SEPARATOR),
            format!(
                "{parent}{separator}{separator}{file_name}",
                separator = std::path::MAIN_SEPARATOR
            ),
            relative,
        ] {
            task.output_ref = alias;
            assert!(validate_task_output_ref(dir.path(), &task).is_err());
        }
    }

    #[test]
    fn relocated_store_rebases_only_exact_normalized_refs() {
        let source = tempfile::tempdir().unwrap();
        let destination = tempfile::tempdir().unwrap();
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_hash = format!("sha256:{}", "b".repeat(64));
        let source_ref =
            crate::markdownize::normalized_instance_dir(source.path(), &raw_hash, &tool_hash, 7);
        let destination_ref = crate::markdownize::normalized_instance_dir(
            destination.path(),
            &raw_hash,
            &tool_hash,
            7,
        );
        fs::create_dir_all(&destination_ref).unwrap();

        let mut normalized = valid_task();
        normalized.input_hash = raw_hash;
        normalized.output_ref = source_ref.display().to_string();
        let mut typed = valid_task();
        typed.task_id = "task_02H".to_owned();
        let typed_ref = typed.output_ref.clone();
        let mut encoded = serde_json::to_vec(&normalized).unwrap();
        encoded.push(b'\n');
        encoded.extend(serde_json::to_vec(&typed).unwrap());
        encoded.push(b'\n');
        fs::write(destination.path().join("tasks.jsonl"), encoded).unwrap();

        rebase_normalized_output_refs_for_relocated_store(source.path(), destination.path())
            .unwrap();
        let tasks = TaskStore::new(destination.path()).all().unwrap();
        assert_eq!(tasks[0].output_ref, destination_ref.display().to_string());
        assert_eq!(tasks[1].output_ref, typed_ref);
    }

    #[test]
    fn relocated_store_rejects_malformed_or_foreign_refs_without_mutation() {
        let source = tempfile::tempdir().unwrap();
        let destination = tempfile::tempdir().unwrap();
        let foreign = tempfile::tempdir().unwrap();
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_hash = format!("sha256:{}", "b".repeat(64));
        let mut task = valid_task();
        task.input_hash = raw_hash.clone();
        task.output_ref =
            crate::markdownize::normalized_instance_dir(foreign.path(), &raw_hash, &tool_hash, 1)
                .display()
                .to_string();
        let path = destination.path().join("tasks.jsonl");
        let mut bytes = serde_json::to_vec(&task).unwrap();
        bytes.push(b'\n');
        fs::write(&path, &bytes).unwrap();
        assert!(
            rebase_normalized_output_refs_for_relocated_store(source.path(), destination.path())
                .is_err()
        );
        assert_eq!(fs::read(&path).unwrap(), bytes);

        fs::write(&path, b"{ malformed\n").unwrap();
        let malformed = fs::read(&path).unwrap();
        assert!(
            rebase_normalized_output_refs_for_relocated_store(source.path(), destination.path())
                .is_err()
        );
        assert_eq!(fs::read(&path).unwrap(), malformed);
    }

    #[cfg(unix)]
    #[test]
    fn relocated_store_never_follows_a_journal_symlink() {
        use std::os::unix::fs::symlink;

        let source = tempfile::tempdir().unwrap();
        let destination = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let outside_journal = outside.path().join("tasks.jsonl");
        let sentinel = b"must not be read or replaced";
        fs::write(&outside_journal, sentinel).unwrap();
        symlink(&outside_journal, destination.path().join("tasks.jsonl")).unwrap();

        assert!(
            rebase_normalized_output_refs_for_relocated_store(source.path(), destination.path())
                .is_err()
        );
        assert_eq!(fs::read(outside_journal).unwrap(), sentinel);
    }

    #[test]
    fn relocated_store_does_not_create_missing_task_journal() {
        let source = tempfile::tempdir().unwrap();
        let destination = tempfile::tempdir().unwrap();
        rebase_normalized_output_refs_for_relocated_store(source.path(), destination.path())
            .unwrap();
        assert!(!destination.path().join("tasks.jsonl").exists());
    }

    #[cfg(windows)]
    #[test]
    fn cand_047_canonical_windows_absolute_output_ref_is_supported() {
        let dir = tempfile::tempdir().unwrap();
        let foreign = tempfile::tempdir().unwrap();
        let kio_dir = dir.path().canonicalize().unwrap();
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_hash = format!("sha256:{}", "b".repeat(64));
        let path = crate::markdownize::normalized_instance_dir(&kio_dir, &raw_hash, &tool_hash, 2);
        fs::create_dir_all(&path).unwrap();
        assert!(
            path.components()
                .any(|component| matches!(component, Component::Prefix(_)))
        );

        let mut task = valid_task();
        task.input_hash = raw_hash.clone();
        task.output_ref = path.display().to_string();
        assert!(validate_task_output_ref(&kio_dir, &task).is_ok());

        task.output_ref = crate::markdownize::normalized_instance_dir(
            foreign.path().canonicalize().unwrap(),
            &raw_hash,
            &tool_hash,
            2,
        )
        .display()
        .to_string();
        assert!(validate_task_output_ref(&kio_dir, &task).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn cand_047_normalized_units_root_symlink_is_not_a_store_boundary() {
        use std::os::unix::fs::symlink;

        let dir = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_hash = format!("sha256:{}", "b".repeat(64));
        fs::create_dir_all(dir.path().join("objects")).unwrap();
        symlink(outside.path(), dir.path().join("objects/normalized_units")).unwrap();

        let mut task = valid_task();
        task.input_hash = raw_hash.clone();
        task.output_ref =
            crate::markdownize::normalized_instance_dir(dir.path(), &raw_hash, &tool_hash, 0)
                .display()
                .to_string();
        assert!(validate_task_output_ref(dir.path(), &task).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn cand_047_existing_normalized_ref_cannot_escape_through_symlink() {
        use std::os::unix::fs::symlink;

        let dir = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let raw_hash = format!("sha256:{}", "a".repeat(64));
        let tool_hash = format!("sha256:{}", "b".repeat(64));
        let path =
            crate::markdownize::normalized_instance_dir(dir.path(), &raw_hash, &tool_hash, 0);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        symlink(outside.path(), &path).unwrap();
        let mut task = valid_task();
        task.input_hash = raw_hash;
        task.output_ref = path.display().to_string();
        assert!(validate_task_output_ref(dir.path(), &task).is_err());
    }

    #[test]
    fn cand_033_capped_task_input_rejects_before_full_materialization() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("report.pdf");
        fs::write(&path, vec![b'x'; 16]).unwrap();
        assert_eq!(
            read_capped_task_input(&path, 16),
            CappedTaskInput::Bytes(vec![b'x'; 16])
        );
        assert_eq!(read_capped_task_input(&path, 15), CappedTaskInput::TooLarge);
        let directory = read_capped_task_input(dir.path(), 16);
        assert!(
            matches!(
                directory,
                CappedTaskInput::NotRegular | CappedTaskInput::Unavailable
            ),
            "a directory must be rejected before materialization: {directory:?}"
        );
    }

    #[test]
    fn cand_001_012_013_recovery_helpers_preserve_security_state() {
        let mut task = valid_task();
        task.task_type = TaskType::Embedding;
        task.output_ref = format!("embedding:sha256:{}", "c".repeat(64));
        assert!(task_can_enter_secret_hold(&task));

        task.status = TaskStatus::Failed;
        task.fallback_reason = Some("contract_violation".to_owned());
        task.attempts = 1;
        assert!(task_failure_is_terminal(&task));
        assert!(!task_can_enter_secret_hold(&task));

        task.fallback_reason = Some("network_error".to_owned());
        task.attempts = 5;
        assert!(task_failure_is_terminal(&task));
        assert!(!task_can_enter_secret_hold(&task));

        task.status = TaskStatus::Paused;
        task.fallback_reason = Some(BUDGET_EXCEEDED_REASON.to_owned());
        assert!(task_can_complete_from_materialized_output(&task));
        task.fallback_reason = Some(SECRETS_TIER_B_HOLD_REASON.to_owned());
        assert!(!task_can_complete_from_materialized_output(&task));

        // QA2: an auth failure lands Paused(hold_reason=auth), not Failed.
        task.status = TaskStatus::Paused;
        task.fallback_reason = Some("auth_error".to_owned());
        task.hold_reason = Some(HoldReason::Auth);
        assert!(!task_auth_revival_allowed(&task, TaskRecoveryMode::Retry));
        assert!(task_auth_revival_allowed(&task, TaskRecoveryMode::Resume));
        // QA2: a materialized twin output also satisfies an auth-paused task
        // (only secret/unknown holds stay sticky).
        assert!(task_can_complete_from_materialized_output(&task));
    }

    #[test]
    fn cand_048_only_complete_uuid_reservation_stamps_yield_claims() {
        let mut task = valid_task();
        task.reserved_usd = Some(1.25);
        task.reserved_month = Some("2026-07".to_owned());
        assert!(
            task.reservation_claim().is_none(),
            "an incomplete stamp cannot authorize a claim"
        );
        task.reservation_id = Some("018f47a4-3bb5-7cc0-8d6a-8b02452a5f7e".to_owned());
        let claim = task.reservation_claim().unwrap();
        assert_eq!(claim.reservation_id, "018f47a4-3bb5-7cc0-8d6a-8b02452a5f7e");
        assert_eq!(claim.usd, 1.25);
        task.clear_reservation();
        assert!(task.reservation_claim().is_none());
    }

    #[test]
    fn reservation_id_requires_canonical_lowercase_uuid() {
        assert!(is_valid_reservation_id(
            "018f47a4-3bb5-7cc0-8d6a-8b02452a5f7e"
        ));
        for invalid in [
            "res_01HVALID",
            "reservation_01HVALID",
            "018F47A4-3BB5-7CC0-8D6A-8B02452A5F7E",
            "018f47a4-3bb5-7cc0-8d6a-8b02452a5f7z",
        ] {
            assert!(!is_valid_reservation_id(invalid), "must reject {invalid}");
        }
    }

    #[test]
    fn task_store_requires_a_complete_reservation_stamp() {
        let dir = tempfile::tempdir().unwrap();
        let store = TaskStore::new(dir.path().join(".kio"));
        let mut task = valid_task();
        task.reserved_usd = Some(1.25);
        task.reserved_month = Some("2026-07".to_owned());
        assert!(store.append(&task).is_err());

        task.reservation_id = Some("018f47a4-3bb5-7cc0-8d6a-8b02452a5f7e".to_owned());
        store.append(&task).unwrap();
        assert_eq!(store.all().unwrap(), vec![task]);
    }

    #[test]
    fn task_store_rejects_unstamped_online_task() {
        let dir = tempfile::tempdir().unwrap();
        let store = TaskStore::new(dir.path().join(".kio"));
        let mut unstamped = valid_task();
        unstamped.bbox_annotation_enabled = None;
        let error = store.append(&unstamped).unwrap_err();
        assert!(
            error.to_string().contains("bbox_annotation_enabled"),
            "online task must not be persisted without policy stamp: {error}"
        );
        assert!(store.all().unwrap().is_empty());
    }

    #[test]
    fn task_store_requires_current_pause_state() {
        let dir = tempfile::tempdir().unwrap();
        let store = TaskStore::new(dir.path().join(".kio"));
        let mut paused = valid_task();
        paused.status = TaskStatus::Paused;
        paused.fallback_reason = Some(BUDGET_EXCEEDED_REASON.to_owned());
        paused.hold_reason = None;
        assert!(store.append(&paused).is_err());

        paused.hold_reason = Some(HoldReason::Auth);
        assert!(store.append(&paused).is_err());

        paused.hold_reason = Some(HoldReason::Budget);
        store.append(&paused).unwrap();
        assert_eq!(store.all().unwrap(), vec![paused]);
    }
}
