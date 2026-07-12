//! Adapter trait, identity helpers, and built-in Step 2 adapters.

pub mod catalog;
pub mod deterministic;
mod gemini_embedding;
mod http_policy;
pub mod identity;
mod mistral_ocr;
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
    #[error("adapter rate limited: {0}")]
    RateLimit(String),
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

pub use traits::{
    ClassificationAdapter, EmbeddingAdapter, MarkdownizeAdapter, PrepareAdapter, RerankAdapter,
    SummaryAdapter,
};
