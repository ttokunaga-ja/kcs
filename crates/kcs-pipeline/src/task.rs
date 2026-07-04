//! Batch task descriptor contracts.

use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};
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

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
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
        for descriptor in descriptors {
            serde_json::to_writer(&mut file, descriptor)
                .map_err(|err| PipelineError::Schema(err.to_string()))?;
            file.write_all(b"\n").pipeline_io(&temp_path)?;
        }
        drop(file);
        fs::rename(&temp_path, &self.path).pipeline_io(&self.path)
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
        };

        let value = serde_json::to_value(descriptor).expect("serialize task descriptor");
        assert_eq!(value["type"], "markdownize");
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
