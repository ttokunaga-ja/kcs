//! Pipeline type skeletons for Step 2.
//!
//! This crate intentionally contains no pipeline logic yet. It only maps the
//! Step 2 pipeline contracts to Rust types and exposes explicit stubs for the
//! later implementation work.

pub mod budget;
pub mod markdownize;
pub mod prepare;
pub mod scan;
pub mod task;

use thiserror::Error;

pub type Result<T> = std::result::Result<T, PipelineError>;

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("not implemented: {0}")]
    NotImplemented(&'static str),
}
