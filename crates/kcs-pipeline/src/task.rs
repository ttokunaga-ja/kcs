//! Batch task descriptor contracts.

use serde::{Deserialize, Serialize};

use crate::markdownize::MarkdownizeMode;
use crate::Result;

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

pub fn enqueue_task(_descriptor: TaskDescriptor) -> Result<()> {
    todo!("implement task persistence and scheduling in Step 2");
}

pub fn pull_next_task(_scope_id: &str) -> Result<Option<TaskDescriptor>> {
    todo!("implement task leasing in Step 2");
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
}
