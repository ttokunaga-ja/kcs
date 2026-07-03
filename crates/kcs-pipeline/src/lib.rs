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
    #[error("not implemented: {0}")]
    NotImplemented(&'static str),
    #[error("{code}: {message}")]
    Contract { code: &'static str, message: String },
    #[error("io error at {path}: {message}")]
    Io { path: String, message: String },
    #[error("schema error: {0}")]
    Schema(String),
}

impl PipelineError {
    #[must_use]
    pub fn contract(code: &'static str, message: impl Into<String>) -> Self {
        Self::Contract {
            code,
            message: message.into(),
        }
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
