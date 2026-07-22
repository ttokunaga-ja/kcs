//! Adapter trait, identity helpers, and built-in Step 2 adapters.

pub mod batch_inventory;
pub mod bbox_annotation;
pub mod catalog;
pub mod deterministic;
mod gemini_embedding;
mod http_policy;
pub mod identity;
mod mistral_ocr;
pub mod office_convert;
pub mod tool_lock;
pub mod traits;
pub mod types;

use thiserror::Error;

pub type Result<T> = std::result::Result<T, AdapterError>;

#[derive(Debug, Error)]
pub enum AdapterError {
    #[error("adapter contract violation: {0}")]
    ContractViolation(String),
    #[error("adapter auth error: {0}")]
    Auth(String),
    /// QA16 (step4b-contract-tests-p3a.md §F, 07 §4 L290): carries the
    /// provider's `Retry-After` in milliseconds when the HTTP response
    /// included one (`http_policy::parse_retry_after_ms`). `None` when the
    /// header was absent or unparseable — never a fabricated value. Use
    /// [`AdapterError::rate_limit`] for the common no-header case (mock/test
    /// seams).
    #[error("adapter rate limited: {message}")]
    RateLimit {
        message: String,
        retry_after_ms: Option<u64>,
    },
    #[error("adapter quota exceeded: {0}")]
    QuotaExceeded(String),
    #[error("adapter network error: {0}")]
    Network(String),
    #[error("schema validation failed: {0}")]
    ConfigSchema(String),
    /// R13-2: a documented-but-unimplemented capability (currently `keychain:`
    /// auth resolution) surfaced LOUDLY rather than silently ignored.
    #[error("not implemented: {0}")]
    NotImplemented(String),
    #[error("io error at {path}: {message}")]
    Io { path: String, message: String },
}

impl AdapterError {
    /// Construct a `RateLimit` with no known `Retry-After` — the common case
    /// for a mock/test seam or a provider 429 response that omitted the
    /// header. Real HTTP call sites that DO have a parsed header value
    /// (`mistral_ocr`/`gemini_embedding`'s `http_error`) build the variant
    /// directly instead.
    #[must_use]
    pub fn rate_limit(message: impl Into<String>) -> Self {
        Self::RateLimit {
            message: message.into(),
            retry_after_ms: None,
        }
    }

    /// QA16 (step4b-contract-tests-p3a.md §F, 07 §4 L286 / 06 §8): the
    /// machine-judgeable error code this error maps to. Mirrors exactly the
    /// code `kcs_pipeline::task::retry_policy` assigns to the corresponding
    /// `RetryErrorKind` (`kcs-adapter` cannot depend on `kcs-pipeline`, so the
    /// two tables are independently maintained and cross-checked by
    /// `kcs-pipeline`'s `qa16_adapter_error_code_matches_retry_policy` test —
    /// see that test before editing either table).
    #[must_use]
    pub fn error_code(&self) -> &'static str {
        match self {
            Self::Auth(_) => "KCS-E-BATCH-AUTH-001",
            Self::RateLimit { .. } => "KCS-E-BATCH-RATE-001",
            Self::QuotaExceeded(_) => "KCS-E-BATCH-QUOTA-001",
            Self::Network(_) | Self::Io { .. } => "KCS-E-BATCH-NET-001",
            Self::ContractViolation(_) | Self::ConfigSchema(_) => "KCS-E-ADAPTER-CONTRACT-001",
            // R13-2: mirrors `task_failure_from_adapter`'s NotImplemented ->
            // InvalidInput mapping (a permanent config gap, never retried).
            Self::NotImplemented(_) => "KCS-E-BATCH-INPUT-001",
        }
    }

    /// QA16: `transient | permanent | rate_limit` (07 §4 L287) — the coarse
    /// bucket 04 §5.3's table rolls up to for aggregation/reporting. Retry
    /// DECISIONS stay keyed by `error_code`/`RetryErrorKind` (07 §4: "retry
    /// 対応は 04 §5.3 の表が error_code 基準で優先する") — this classification
    /// mirrors `retry_policy(...).retryable` (permanent = non-retryable)
    /// without changing which table drives scheduling.
    #[must_use]
    pub fn error_category(&self) -> crate::types::ErrorCategory {
        use crate::types::ErrorCategory;
        match self {
            Self::RateLimit { .. } => ErrorCategory::RateLimit,
            // Non-retryable in 04 §5.3's table (auth_error/invalid_input both
            // have max_attempts=0).
            Self::Auth(_) | Self::NotImplemented(_) => ErrorCategory::Permanent,
            // Retryable in 04 §5.3's table (network_error/quota_exceeded/
            // contract_violation all have max_attempts >= 1).
            Self::QuotaExceeded(_)
            | Self::Network(_)
            | Self::Io { .. }
            | Self::ContractViolation(_)
            | Self::ConfigSchema(_) => ErrorCategory::Transient,
        }
    }

    /// QA16: provider `Retry-After`, in milliseconds, when this is a
    /// rate-limit error and the header was present/parseable (07 §4 L290).
    #[must_use]
    pub fn retry_after_ms(&self) -> Option<u64> {
        match self {
            Self::RateLimit { retry_after_ms, .. } => *retry_after_ms,
            _ => None,
        }
    }

    /// QA16: render this error as the terminal `AdapterRun` a real Adapter
    /// trait boundary would report for it (07 §4 L278-307) — `error_kind`
    /// keeps the legacy free-text `Display` message (orchestrator ruling:
    /// "既存 error_kind は当面残す — 消すのは別ラウンド"); `error_code`/
    /// `error_category`/`retry_after_ms` are the new machine-readable fields,
    /// individually queryable instead of folded into one free-text string.
    #[must_use]
    pub fn as_adapter_run(&self, task_id: impl Into<String>) -> crate::types::AdapterRun {
        crate::types::AdapterRun {
            task_id: task_id.into(),
            input_hashes: Vec::new(),
            output_hashes: Vec::new(),
            status: crate::types::AdapterRunStatus::Failed,
            error_kind: Some(self.to_string()),
            error_code: Some(self.error_code().to_owned()),
            error_category: Some(self.error_category()),
            retry_after_ms: self.retry_after_ms(),
            usage: None,
        }
    }
}

pub use traits::{
    ClassificationAdapter, EmbeddingAdapter, MarkdownizeAdapter, PrepareAdapter, RerankAdapter,
    SummaryAdapter,
};

#[cfg(test)]
mod adapter_error_tests {
    use super::*;
    use crate::types::{AdapterRunStatus, ErrorCategory};

    /// QA16: every variant's `error_code`/`error_category` pairing matches the
    /// 07 §4 L287 contract (`error_category` is the coarse rollup of the fine
    /// `error_code`) and stays internally consistent (RateLimit <-> RateLimit
    /// category exclusively).
    #[test]
    fn error_code_and_category_cover_every_variant() {
        let cases: &[(AdapterError, &str, ErrorCategory)] = &[
            (
                AdapterError::Auth("x".to_owned()),
                "KCS-E-BATCH-AUTH-001",
                ErrorCategory::Permanent,
            ),
            (
                AdapterError::rate_limit("x"),
                "KCS-E-BATCH-RATE-001",
                ErrorCategory::RateLimit,
            ),
            (
                AdapterError::QuotaExceeded("x".to_owned()),
                "KCS-E-BATCH-QUOTA-001",
                ErrorCategory::Transient,
            ),
            (
                AdapterError::Network("x".to_owned()),
                "KCS-E-BATCH-NET-001",
                ErrorCategory::Transient,
            ),
            (
                AdapterError::Io {
                    path: "p".to_owned(),
                    message: "m".to_owned(),
                },
                "KCS-E-BATCH-NET-001",
                ErrorCategory::Transient,
            ),
            (
                AdapterError::ContractViolation("x".to_owned()),
                "KCS-E-ADAPTER-CONTRACT-001",
                ErrorCategory::Transient,
            ),
            (
                AdapterError::ConfigSchema("x".to_owned()),
                "KCS-E-ADAPTER-CONTRACT-001",
                ErrorCategory::Transient,
            ),
            (
                AdapterError::NotImplemented("x".to_owned()),
                "KCS-E-BATCH-INPUT-001",
                ErrorCategory::Permanent,
            ),
        ];
        for (error, expected_code, expected_category) in cases {
            assert_eq!(error.error_code(), *expected_code, "{error:?}");
            assert_eq!(error.error_category(), *expected_category, "{error:?}");
        }
    }

    /// QA16: `retry_after_ms` is `Some` only for `RateLimit`, and only when a
    /// value was actually supplied — never fabricated for other variants or
    /// for a `RateLimit` built via [`AdapterError::rate_limit`] (no header).
    #[test]
    fn retry_after_ms_is_rate_limit_exclusive() {
        assert_eq!(AdapterError::rate_limit("no header").retry_after_ms(), None);
        assert_eq!(
            AdapterError::RateLimit {
                message: "with header".to_owned(),
                retry_after_ms: Some(30_000),
            }
            .retry_after_ms(),
            Some(30_000)
        );
        assert_eq!(
            AdapterError::Auth("x".to_owned()).retry_after_ms(),
            None,
            "retry_after_ms must not leak onto unrelated variants"
        );
    }

    /// QA16 operation scenario (step4b-contract-tests-p3a.md §F): "online
    /// Adapter 呼出が transient エラー (429相当、Retry-After ヘッダ付き) で失敗する"
    /// — the resulting `AdapterRun` carries `error_code`, `error_category` =
    /// `rate_limit`, and `retry_after_ms` as individually-queryable fields
    /// (not folded into one free-text `error_kind` string).
    #[test]
    fn rate_limit_with_retry_after_becomes_a_failed_adapter_run_with_all_three_fields() {
        let error = AdapterError::RateLimit {
            message: "Mistral OCR HTTP 429: Too Many Requests".to_owned(),
            retry_after_ms: Some(30_000),
        };
        let run = error.as_adapter_run("task_01H_example");
        assert_eq!(run.task_id, "task_01H_example");
        assert_eq!(run.status, AdapterRunStatus::Failed);
        assert_eq!(run.error_code.as_deref(), Some("KCS-E-BATCH-RATE-001"));
        assert_eq!(run.error_category, Some(ErrorCategory::RateLimit));
        assert_eq!(run.retry_after_ms, Some(30_000));
        // error_kind stays populated too (backward compatibility, orchestrator
        // ruling: "既存 error_kind は当面残す").
        assert!(run.error_kind.is_some());
        assert_eq!(run.usage, None);
    }
}
