use serde_json::{Value, json};
use thiserror::Error;

use crate::ExitCode;

pub type Result<T> = std::result::Result<T, KioError>;

#[derive(Debug, Error)]
#[error("{error_code}: {message}")]
pub struct KioError {
    error_code: String,
    message: String,
    context: Value,
    exit_code: ExitCode,
}

impl KioError {
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
            "KIO-E-CONFIG-SCHEMA-001",
            message,
            json!({}),
            ExitCode::InvalidUsage,
        )
    }

    /// Path schema violation: a tree/pointer `path` that contains the path
    /// separator `/` (`docs/03-data-model.md` §3, `docs/06-cli-spec.md` §8).
    #[must_use]
    pub fn path(message: impl Into<String>, path: impl Into<String>) -> Self {
        Self::new(
            "KIO-E-STORE-PATH-001",
            message,
            json!({ "path": path.into() }),
            ExitCode::InvalidUsage,
        )
    }

    /// Duplicate `path` among the entries of a single tree
    /// (`docs/03-data-model.md` §8.1). Kept distinct from the `/`-in-path
    /// violation (`KIO-E-STORE-PATH-001`).
    #[must_use]
    pub fn duplicate_path(path: impl Into<String>) -> Self {
        Self::new(
            "KIO-E-STORE-DUP-001",
            "duplicate tree entry path",
            json!({ "path": path.into() }),
            ExitCode::InvalidUsage,
        )
    }

    #[must_use]
    pub fn not_found(hash: impl Into<String>) -> Self {
        Self::new(
            "KIO-E-STORE-NOT-FOUND-001",
            "object not found",
            json!({ "hash": hash.into() }),
            ExitCode::PermanentFailure,
        )
    }

    /// R15-4: the HEAD (or a named) commit is shallow — its tree object has been
    /// discarded (GC / manual deletion / corruption), so an operation that needs the
    /// full prior tree (snapshot / index / reindex, or a cursor replay) cannot
    /// proceed. Distinct from a raw `KIO-E-STORE-NOT-FOUND-001` so the caller gets a
    /// clear "shallow commit" signal plus recovery guidance instead of an opaque
    /// missing-object error (`docs/05-runtime.md` §2.2, `docs/06-cli-spec.md` §8).
    #[must_use]
    pub fn commit_shallow(message: impl Into<String>, commit_hash: impl Into<String>) -> Self {
        Self::new(
            "KIO-E-COMMIT-SHALLOW-001",
            message,
            json!({ "commit_hash": commit_hash.into() }),
            ExitCode::Failure,
        )
    }

    #[must_use]
    pub fn locked(path: impl Into<String>) -> Self {
        Self::new(
            "KIO-E-STORE-LOCKED-001",
            ".kio store is locked",
            json!({ "path": path.into() }),
            ExitCode::PartialFailure,
        )
    }

    #[must_use]
    pub fn io(message: impl Into<String>, path: impl Into<String>) -> Self {
        Self::new(
            "KIO-E-STORE-IO-001",
            message,
            json!({ "path": path.into() }),
            ExitCode::Failure,
        )
    }

    /// Invalid CLI usage / operand: a nonexistent `init` path, a directory that
    /// is not a `.kio` scope, a malformed hash argument, etc. Distinct from a
    /// JSON Schema violation (`KIO-E-CONFIG-SCHEMA-001`). Exit code stays 2.
    #[must_use]
    pub fn invalid_usage(message: impl Into<String>) -> Self {
        Self::new(
            "KIO-E-CONFIG-USAGE-001",
            message,
            json!({}),
            ExitCode::InvalidUsage,
        )
    }

    /// QB8/QB9 (step4b-contract-tests-p3b.md §A, 06 §8 / 10 §12.5): the
    /// canonical, spec-listed error code for an incompatible
    /// `kio_format_version` is `KIO-E-STORE-VERSION-001` (exit 8), not a
    /// bespoke `KIO-E-CONFIG-FORMAT-001` — the latter never appeared in the
    /// error code namespace tables and was only recognized by one internal
    /// caller (`search_one_scope_inner`'s per-scope translation), which is
    /// now redundant and has been removed.
    #[must_use]
    pub fn incompatible_format(found: impl Into<String>) -> Self {
        Self::new(
            "KIO-E-STORE-VERSION-001",
            "incompatible kio_format_version",
            json!({ "found": found.into() }),
            ExitCode::IncompatibleProfile,
        )
    }

    #[must_use]
    pub fn not_implemented(feature: impl Into<String>) -> Self {
        Self::new(
            "KIO-E-CONFIG-NOT-IMPLEMENTED-001",
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
    fn kio_io(self, path: &std::path::Path) -> Result<T>;
}

impl<T> IoResultExt<T> for std::io::Result<T> {
    fn kio_io(self, path: &std::path::Path) -> Result<T> {
        self.map_err(|err| KioError::io(err.to_string(), path.display().to_string()))
    }
}
