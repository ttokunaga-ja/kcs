//! Pipeline contracts and deterministic Step 2 helpers.

pub mod budget;
pub mod markdownize;
pub mod prepare;
pub mod scan;
pub mod task;

use thiserror::Error;

pub type Result<T> = std::result::Result<T, PipelineError>;

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("{code}: {message}")]
    Contract { code: &'static str, message: String },
    #[error("io error at {path}: {message}")]
    Io { path: String, message: String },
    #[error("schema error: {0}")]
    Schema(String),
    /// A persisted store file (tasks.jsonl / cost-ledger.jsonl) could not be
    /// parsed — the on-disk record is corrupt, not a config/schema error
    /// (M1(c)). Surfaced as `KCS-E-STORE-CORRUPT-001` (exit 4), carrying the
    /// offending file path.
    #[error("KCS-E-STORE-CORRUPT-001: corrupt store file at {path}: {message}")]
    Corrupt { path: String, message: String },
    /// A persisted task's `input_path` escapes the scope: it is absolute, carries
    /// a path separator, or contains a `..`/`.` traversal component rather than
    /// naming a direct child of the scope root (03 §3.3; the same rule dag.rs
    /// enforces for tree entries). Surfaced as `KCS-E-STORE-PATH-001` (exit 2).
    /// A poisoned / shared `tasks.jsonl` must not let a resume read an arbitrary
    /// file and send it to an online adapter (P1).
    #[error("KCS-E-STORE-PATH-001: task input_path is not a scope-local file name: {path}")]
    Path { path: String },
}

impl PipelineError {
    #[must_use]
    pub fn contract(code: &'static str, message: impl Into<String>) -> Self {
        Self::Contract {
            code,
            message: message.into(),
        }
    }

    #[must_use]
    pub fn corrupt(path: impl Into<String>, message: impl Into<String>) -> Self {
        Self::Corrupt {
            path: path.into(),
            message: message.into(),
        }
    }

    #[must_use]
    pub fn path(path: impl Into<String>) -> Self {
        Self::Path { path: path.into() }
    }
}

pub(crate) trait IoResultExt<T> {
    fn pipeline_io(self, path: &std::path::Path) -> Result<T>;
}

impl<T> IoResultExt<T> for std::io::Result<T> {
    fn pipeline_io(self, path: &std::path::Path) -> Result<T> {
        self.map_err(|err| PipelineError::Io {
            path: path.display().to_string(),
            message: err.to_string(),
        })
    }
}
