//! Batch task descriptor contracts.

use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};

use crate::markdownize::MarkdownizeMode;
use crate::{IoResultExt, PipelineError, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskType {
    Prepare,
    Markdownize,
    Embedding,
    Summary,
    Classification,
    Rerank,
    Index,
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
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
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
    // R17-3: the exact F8 reservation this task currently holds (amount + the
    // ledger `month` it landed in), stamped when a FRESH charge is reserved in the
    // batch send path and left untouched on the RateLimit/Quota re-reservation-skip
    // (R16-7) so it always names the single live reservation the skip gate relies
    // on. When a stale task is superseded at re-index, a non-billable (RateLimit/
    // Quota) reservation is reclaimed by exactly this (usd, month) into the sibling
    // reclaim ledger — canceling the phantom precisely even though the edited file
    // is gone. Absent (None) on fresh/legacy tasks and after a reclaim (cleared, so
    // it can never be reclaimed twice). Serialized only when present so untouched
    // tasks stay byte-identical to pre-R17-3 records.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reserved_usd: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reserved_month: Option<String>,
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
    pub fn new(kcs_dir: impl AsRef<Path>) -> Self {
        Self {
            path: kcs_dir.as_ref().join("tasks.jsonl"),
        }
    }

    pub fn append(&self, descriptor: &TaskDescriptor) -> Result<()> {
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
        let mut line = serde_json::to_string(descriptor)
            .map_err(|err| PipelineError::Schema(err.to_string()))?;
        line.push('\n');
        file.write_all(line.as_bytes()).pipeline_io(&self.path)
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
        let mut by_id = BTreeMap::new();
        for line in std::io::BufReader::new(file).lines() {
            let line = line.pipeline_io(&self.path)?;
            if line.trim().is_empty() {
                continue;
            }
            // M1(c): a malformed line is a corrupt store file, not a schema/config
            // error — classify it as KCS-E-STORE-CORRUPT-001 with the file path.
            let descriptor: TaskDescriptor = serde_json::from_str(&line).map_err(|err| {
                PipelineError::corrupt(self.path.display().to_string(), err.to_string())
            })?;
            // P1: reject any task whose `input_path` escapes the scope before any
            // consumer joins it onto the scope root and reads / sends the file.
            // Validating here (the single read path) guards every consumer at once
            // (`batch resume`, `status`, enrichment) so a poisoned / shared
            // tasks.jsonl cannot exfiltrate `/etc/*` or `../../id_rsa` to an online
            // adapter (03 §3.3, same rule dag.rs enforces for tree entries).
            if !is_scope_local_file_name(&descriptor.input_path) {
                return Err(PipelineError::path(descriptor.input_path));
            }
            // Q6: validate every hash-shaped ref has the CAS hash form before any
            // consumer slices its digest. A poisoned tasks.jsonl with a short
            // `input_hash` (e.g. "sha256:ab") would otherwise panic (slice out of
            // bounds) deep in the online markdownize path
            // (`normalized_instance_dir` does `digest[0..2]` / `[2..4]`). Reject it
            // here at the single read choke point as STORE-CORRUPT — same guard,
            // same place P1 rejects an out-of-scope input_path.
            if !kcs_core::cas::is_hash(&descriptor.input_hash) {
                return Err(PipelineError::corrupt(
                    self.path.display().to_string(),
                    format!(
                        "task input_hash is not a valid hash: {}",
                        descriptor.input_hash
                    ),
                ));
            }
            if let Some(previous) = &descriptor.previous_raw_hash {
                if !kcs_core::cas::is_hash(previous) {
                    return Err(PipelineError::corrupt(
                        self.path.display().to_string(),
                        format!("task previous_raw_hash is not a valid hash: {previous}"),
                    ));
                }
            }
            by_id.insert(descriptor.task_id.clone(), descriptor);
        }
        Ok(by_id.into_values().collect())
    }

    pub fn replace_all(&self, descriptors: &[TaskDescriptor]) -> Result<()> {
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
            for descriptor in descriptors {
                serde_json::to_writer(&mut file, descriptor)
                    .map_err(|err| PipelineError::Schema(err.to_string()))?;
                file.write_all(b"\n").pipeline_io(&temp_path)?;
            }
            drop(file);
            fs::rename(&temp_path, &self.path).pipeline_io(&self.path)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp_path);
        }
        result
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
                    })
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

    pub fn pending_count(&self) -> Result<usize> {
        Ok(self
            .all()?
            .iter()
            .filter(|task| task.status == TaskStatus::Pending)
            .count())
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
            error_code: "KCS-E-BATCH-NET-001".to_owned(),
            paused: false,
        },
        RetryErrorKind::RateLimit => RetryPolicy {
            error_kind,
            retryable: true,
            max_attempts: None,
            backoff: "retry_after".to_owned(),
            error_code: "KCS-E-BATCH-RATE-001".to_owned(),
            paused: false,
        },
        RetryErrorKind::AuthError => RetryPolicy {
            error_kind,
            retryable: false,
            max_attempts: Some(0),
            backoff: "user_action".to_owned(),
            error_code: "KCS-E-BATCH-AUTH-001".to_owned(),
            paused: false,
        },
        RetryErrorKind::QuotaExceeded => RetryPolicy {
            error_kind,
            retryable: true,
            max_attempts: Some(3),
            backoff: "fixed(1h)".to_owned(),
            error_code: "KCS-E-BATCH-QUOTA-001".to_owned(),
            paused: false,
        },
        RetryErrorKind::InvalidInput => RetryPolicy {
            error_kind,
            retryable: false,
            max_attempts: Some(0),
            backoff: "none".to_owned(),
            error_code: "KCS-E-BATCH-INPUT-001".to_owned(),
            paused: false,
        },
        RetryErrorKind::ContractViolation => RetryPolicy {
            error_kind,
            retryable: false,
            max_attempts: Some(0),
            backoff: "full_fallback_once".to_owned(),
            error_code: "KCS-E-ADAPTER-CONTRACT-001".to_owned(),
            paused: false,
        },
        RetryErrorKind::BudgetExceeded => RetryPolicy {
            error_kind,
            retryable: false,
            max_attempts: Some(0),
            backoff: "override_budget_required".to_owned(),
            error_code: "KCS-E-BATCH-BUDGET-001".to_owned(),
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
            output_ref: ".kcs/objects/normalized_units/ab/cd/abc.tool.g0/".to_owned(),
            unit_keys: None,
            status: TaskStatus::Pending,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: None,
            created_at: "2026-04-25T12:00:00Z".to_owned(),
            reserved_usd: None,
            reserved_month: None,
        };

        let value = serde_json::to_value(descriptor).expect("serialize task descriptor");
        assert_eq!(value["type"], "markdownize");
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
        // rejected at read time with KCS-E-STORE-PATH-001, before any consumer can
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
            reserved_usd: None,
            reserved_month: None,
        };
        store.append(&task).unwrap();
        // A bare-name task reads back fine.
        assert_eq!(store.all().unwrap().len(), 1);
        // Append a poison line with an absolute input_path.
        task.task_id = "task_02H".to_owned();
        task.input_path = "/etc/hosts".to_owned();
        store.append(&task).unwrap();
        let err = store.all().unwrap_err();
        assert!(
            matches!(err, PipelineError::Path { .. }),
            "expected KCS-E-STORE-PATH-001, got {err:?}"
        );
        assert!(err.to_string().contains("KCS-E-STORE-PATH-001"));
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
            reserved_usd: None,
            reserved_month: None,
        };
        store.append(&task).unwrap();
        let err = store.all().unwrap_err();
        assert!(
            matches!(err, PipelineError::Corrupt { .. }),
            "expected KCS-E-STORE-CORRUPT-001, got {err:?}"
        );
        assert!(err.to_string().contains("KCS-E-STORE-CORRUPT-001"));
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
            "KCS-E-BATCH-NET-001"
        );
        assert_eq!(
            retry_policy(RetryErrorKind::NetworkError).max_attempts,
            Some(5)
        );
        assert_eq!(retry_policy(RetryErrorKind::RateLimit).max_attempts, None);
        assert!(retry_policy(RetryErrorKind::BudgetExceeded).paused);
        assert_eq!(
            retry_policy(RetryErrorKind::ContractViolation).error_code,
            "KCS-E-ADAPTER-CONTRACT-001"
        );
    }
}
