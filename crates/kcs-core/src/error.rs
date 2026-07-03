use serde_json::{json, Value};
use thiserror::Error;

use crate::ExitCode;

pub type Result<T> = std::result::Result<T, KcsError>;

#[derive(Debug, Error)]
#[error("{error_code}: {message}")]
pub struct KcsError {
    error_code: String,
    message: String,
    context: Value,
    exit_code: ExitCode,
}

impl KcsError {
    #[must_use]
    pub fn new(
        error_code: impl Into<String>,
        message: impl Into<String>,
        context: Value,
        exit_code: ExitCode,
    ) -> Self {
        Self {
            error_code: error_code.into(),
            message: message.into(),
            context,
            exit_code,
        }
    }

    #[must_use]
    pub fn schema(message: impl Into<String>) -> Self {
        Self::new(
            "KCS-E-CONFIG-SCHEMA-001",
            message,
            json!({}),
            ExitCode::InvalidUsage,
        )
    }

    #[must_use]
    pub fn path(message: impl Into<String>, path: impl Into<String>) -> Self {
        Self::new(
            "KCS-E-STORE-PATH-001",
            message,
            json!({ "path": path.into() }),
            ExitCode::InvalidUsage,
        )
    }

    #[must_use]
    pub fn not_found(hash: impl Into<String>) -> Self {
        Self::new(
            "KCS-E-STORE-NOT-FOUND-001",
            "object not found",
            json!({ "hash": hash.into() }),
            ExitCode::PermanentFailure,
        )
    }

    #[must_use]
    pub fn locked(path: impl Into<String>) -> Self {
        Self::new(
            "KCS-E-STORE-LOCKED-001",
            ".kcs store is locked",
            json!({ "path": path.into() }),
            ExitCode::PartialFailure,
        )
    }

    #[must_use]
    pub fn io(message: impl Into<String>, path: impl Into<String>) -> Self {
        Self::new(
            "KCS-E-STORE-IO-001",
            message,
            json!({ "path": path.into() }),
            ExitCode::Failure,
        )
    }

    #[must_use]
    pub fn invalid_usage(message: impl Into<String>) -> Self {
        Self::new(
            "KCS-E-CONFIG-SCHEMA-001",
            message,
            json!({}),
            ExitCode::InvalidUsage,
        )
    }

    #[must_use]
    pub fn incompatible_format(found: impl Into<String>) -> Self {
        Self::new(
            "KCS-E-CONFIG-FORMAT-001",
            "incompatible kcs_format_version",
            json!({ "found": found.into() }),
            ExitCode::IncompatibleProfile,
        )
    }

    #[must_use]
    pub fn not_implemented(feature: impl Into<String>) -> Self {
        Self::new(
            "KCS-E-CONFIG-NOT-IMPLEMENTED-001",
            "not implemented",
            json!({ "feature": feature.into() }),
            ExitCode::Failure,
        )
    }

    #[must_use]
    pub fn error_code(&self) -> &str {
        &self.error_code
    }

    #[must_use]
    pub fn message(&self) -> &str {
        &self.message
    }

    #[must_use]
    pub const fn exit_code(&self) -> ExitCode {
        self.exit_code
    }

    #[must_use]
    pub fn context(&self) -> &Value {
        &self.context
    }

    #[must_use]
    pub fn to_error_json(&self) -> Value {
        json!({
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context,
        })
    }
}

pub trait IoResultExt<T> {
    fn kcs_io(self, path: &std::path::Path) -> Result<T>;
}

impl<T> IoResultExt<T> for std::io::Result<T> {
    fn kcs_io(self, path: &std::path::Path) -> Result<T> {
        self.map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
    }
}
