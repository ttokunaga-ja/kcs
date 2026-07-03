//! Adapter trait, identity helpers, and built-in Step 2 adapters.

pub mod deterministic;
pub mod identity;
pub mod mistral_ocr;
pub mod tool_lock;
pub mod traits;
pub mod types;

use thiserror::Error;

pub type Result<T> = std::result::Result<T, AdapterError>;

#[derive(Debug, Error)]
pub enum AdapterError {
    #[error("not implemented: {0}")]
    NotImplemented(&'static str),
    #[error("adapter contract violation: {0}")]
    ContractViolation(String),
    #[error("schema validation failed: {0}")]
    ConfigSchema(String),
    #[error("io error at {path}: {message}")]
    Io { path: String, message: String },
}

pub use traits::{
    ClassificationAdapter, EmbeddingAdapter, MarkdownizeAdapter, PrepareAdapter, RerankAdapter,
    SummaryAdapter,
};
