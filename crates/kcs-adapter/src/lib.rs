//! Adapter trait and wire-type skeletons for Step 2.
//!
//! The crate defines contracts only. Built-in adapters expose empty
//! implementations whose methods remain explicit `todo!()` stubs until the
//! Step 2 implementation work starts.

pub mod deterministic;
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
}

pub use traits::{
    ClassificationAdapter, EmbeddingAdapter, MarkdownizeAdapter, PrepareAdapter, RerankAdapter,
    SummaryAdapter,
};
