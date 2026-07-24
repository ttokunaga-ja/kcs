/// Process exit codes defined by `docs/06-cli-spec.md` section 7.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(i32)]
pub enum ExitCode {
    /// Success / all up to date.
    Success = 0,
    /// Generic failure with no more specific category.
    Failure = 1,
    /// Invalid usage, invalid config, or schema validation failure.
    InvalidUsage = 2,
    /// Partial failure with retryable work remaining.
    PartialFailure = 3,
    /// All work failed permanently.
    PermanentFailure = 4,
    /// Authentication or authorization error requiring user action.
    AuthError = 5,
    /// Work paused because the configured budget was exceeded.
    BudgetExceeded = 6,
    /// User interruption such as SIGINT or SIGTERM.
    Interrupted = 7,
    /// Incompatible profile or format version.
    IncompatibleProfile = 8,
    /// User rejected a confirmation prompt.
    ConfirmationRejected = 9,
}

impl ExitCode {
    #[must_use]
    pub const fn code(self) -> i32 {
        self as i32
    }
}

#[cfg(test)]
mod tests {
    use super::ExitCode;

    #[test]
    fn exit_codes_match_cli_spec_section_7() {
        let codes = [
            ExitCode::Success,
            ExitCode::Failure,
            ExitCode::InvalidUsage,
            ExitCode::PartialFailure,
            ExitCode::PermanentFailure,
            ExitCode::AuthError,
            ExitCode::BudgetExceeded,
            ExitCode::Interrupted,
            ExitCode::IncompatibleProfile,
            ExitCode::ConfirmationRejected,
        ];

        let values: Vec<i32> = codes.into_iter().map(ExitCode::code).collect();
        assert_eq!(values, (0..=9).collect::<Vec<_>>());
    }
}
