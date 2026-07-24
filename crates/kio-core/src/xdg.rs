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
/// cursor-signing key (secret material) — into a CWD-relative `kio/` directory
/// that a subsequent `kio index` could then ingest into the archive.
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

/// R13-6: the `$HOME`-based fallback base dir, honoring the same absolute-path
/// rule `xdg_dir` applies to `XDG_*`. R12-6 closed the XDG side; the `$HOME`
/// fallback at every call site still passed a raw `var_os("HOME")` into
/// `PathBuf::from`, so an unset/empty/relative `HOME` (with no `XDG_*` override)
/// resolved device-global state — the scope registry, cost ledger, logs and the
/// 0600 cursor-signing key — against the current working directory (`./kio/…`),
/// breaking device-global isolation and the device budget cap. Returns
/// `Some(abs_path)` only for a set, non-empty, absolute value; callers append
/// their conventional suffix (`.local/share`, `.config`, `.cache`).
#[must_use]
pub fn home_dir() -> Option<PathBuf> {
    let home = home_dir_from(std::env::var_os("HOME"));
    if home.is_some() {
        home
    } else {
        windows_profile_dir()
    }
}

#[cfg(test)]
fn home_dir_from_sources(
    home: Option<OsString>,
    platform_profile: Option<PathBuf>,
) -> Option<PathBuf> {
    home_dir_from(home).or_else(|| platform_profile.filter(|path| path.is_absolute()))
}

/// Pure core of [`home_dir`], unit-testable without mutating the environment.
#[must_use]
fn home_dir_from(value: Option<OsString>) -> Option<PathBuf> {
    let value = value?;
    if value.is_empty() {
        return None;
    }
    let path = PathBuf::from(value);
    path.is_absolute().then_some(path)
}

/// On Windows, `$HOME` is optional and frequently absent. Resolve the current
/// user's profile through the OS Known Folder API instead of degrading to CWD or
/// trusting a relative environment variable. Non-Windows builds deliberately
/// return `None`, preserving the existing fail-closed HOME/XDG contract.
#[cfg(windows)]
fn windows_profile_dir() -> Option<PathBuf> {
    use std::os::windows::ffi::OsStringExt;
    use std::ptr::{null_mut, NonNull};

    use windows_sys::Win32::System::Com::CoTaskMemFree;
    use windows_sys::Win32::UI::Shell::{FOLDERID_Profile, SHGetKnownFolderPath, KF_FLAG_DEFAULT};

    #[cfg(debug_assertions)]
    if let Some(profile) = home_dir_from(std::env::var_os("KIO_TEST_WINDOWS_PROFILE")) {
        return Some(profile);
    }

    let mut raw = null_mut();
    let status = unsafe {
        SHGetKnownFolderPath(
            &FOLDERID_Profile,
            KF_FLAG_DEFAULT as u32,
            null_mut(),
            &mut raw,
        )
    };
    let raw = NonNull::new(raw)?;
    if status < 0 {
        unsafe { CoTaskMemFree(raw.as_ptr().cast()) };
        return None;
    }
    let mut length = 0usize;
    unsafe {
        while *raw.as_ptr().add(length) != 0 {
            length = length.checked_add(1)?;
        }
    }
    let value = unsafe { OsString::from_wide(std::slice::from_raw_parts(raw.as_ptr(), length)) };
    unsafe { CoTaskMemFree(raw.as_ptr().cast()) };
    let path = PathBuf::from(value);
    path.is_absolute().then_some(path)
}

#[cfg(not(windows))]
fn windows_profile_dir() -> Option<PathBuf> {
    None
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
        assert_eq!(xdg_dir_from(Some(OsString::from("kio"))), None);
        assert_eq!(xdg_dir_from(Some(OsString::from("./relative/dir"))), None);
        assert_eq!(xdg_dir_from(Some(OsString::from("relative/dir"))), None);
    }

    #[test]
    fn absolute_is_kept() {
        let absolute = std::env::temp_dir().join("kio-xdg-absolute");
        assert!(absolute.is_absolute());
        assert_eq!(
            xdg_dir_from(Some(absolute.clone().into_os_string())),
            Some(absolute)
        );
    }

    #[test]
    fn home_dir_applies_the_same_absolute_rule() {
        // R13-6: unset / empty / relative HOME must all yield None (no CWD-relative
        // device-global state); only an absolute HOME is kept.
        assert_eq!(home_dir_from(None), None);
        assert_eq!(home_dir_from(Some(OsString::from(""))), None);
        assert_eq!(home_dir_from(Some(OsString::from("rel/home"))), None);
        assert_eq!(home_dir_from(Some(OsString::from("./rel"))), None);
        let absolute = std::env::temp_dir().join("kio-home-absolute");
        assert!(absolute.is_absolute());
        assert_eq!(
            home_dir_from(Some(absolute.clone().into_os_string())),
            Some(absolute)
        );
    }

    #[test]
    fn windows_style_profile_fallback_is_absolute_and_never_cwd_relative() {
        let absolute = std::env::temp_dir().join("kio-windows-profile");
        assert_eq!(
            home_dir_from_sources(None, Some(absolute.clone())),
            Some(absolute)
        );
        assert_eq!(
            home_dir_from_sources(None, Some(PathBuf::from("relative-profile"))),
            None
        );
    }

    #[cfg(windows)]
    #[test]
    fn windows_known_profile_is_an_absolute_fallback() {
        let profile = windows_profile_dir().expect("Windows profile known folder");
        assert!(profile.is_absolute());
    }
}
