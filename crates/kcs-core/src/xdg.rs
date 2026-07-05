//! XDG Base Directory resolution honoring the spec's validity rules.

use std::ffi::OsString;
use std::path::PathBuf;

/// Read an `XDG_*` base-directory environment variable per the XDG Base Directory
/// Specification's validity rules: an **unset, empty, or relative** value must be
/// treated as *unset* — the spec requires these paths to be absolute and states
/// that a relative path "should be considered invalid and ignored". Returns
/// `Some(abs_path)` only for a set, non-empty, absolute value; `None` otherwise,
/// so every call site falls back to the `$HOME`-based default.
///
/// R12-6: previously all seven call sites passed `var_os("XDG_*")` straight into
/// `PathBuf::from`, so `XDG_DATA_HOME=""` or a relative value scattered
/// device-global state — the scope registry, cost ledger, logs and the 0600
/// cursor-signing key (secret material) — into a CWD-relative `kcs/` directory
/// that a subsequent `kcs index` could then ingest into the archive.
#[must_use]
pub fn xdg_dir(var_name: &str) -> Option<PathBuf> {
    xdg_dir_from(std::env::var_os(var_name))
}

/// Pure core of [`xdg_dir`], split out so the validity rules are unit-testable
/// without mutating process-global environment variables (which would race with
/// other threads in the test harness).
#[must_use]
fn xdg_dir_from(value: Option<OsString>) -> Option<PathBuf> {
    let value = value?;
    if value.is_empty() {
        return None;
    }
    let path = PathBuf::from(value);
    // A relative XDG path is invalid per the spec and must be ignored (treated as
    // unset) rather than resolved against the current working directory.
    path.is_absolute().then_some(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unset_is_none() {
        assert_eq!(xdg_dir_from(None), None);
    }

    #[test]
    fn empty_is_none() {
        assert_eq!(xdg_dir_from(Some(OsString::from(""))), None);
    }

    #[test]
    fn relative_is_none() {
        // A bare name and a `./`-prefixed relative path are both invalid.
        assert_eq!(xdg_dir_from(Some(OsString::from("kcs"))), None);
        assert_eq!(xdg_dir_from(Some(OsString::from("./relative/dir"))), None);
        assert_eq!(xdg_dir_from(Some(OsString::from("relative/dir"))), None);
    }

    #[test]
    fn absolute_is_kept() {
        assert_eq!(
            xdg_dir_from(Some(OsString::from("/abs/data"))),
            Some(PathBuf::from("/abs/data"))
        );
    }
}
