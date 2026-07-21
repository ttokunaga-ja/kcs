//! Cross-platform physical-leaf rules shared by refs and disposable caches.

use sha2::{Digest, Sha256};
use unicode_normalization::UnicodeNormalization;

const MAX_PORTABLE_LEAF_UTF16_UNITS: usize = 255;

/// Versioned directory below `.kcs/refs` for canonical portable tag refs.
///
/// Keeping canonical hashed refs outside the legacy `refs/tags/<logical-name>`
/// directory prevents an old raw tag that happens to look like `tag-<digest>`
/// from being mistaken for another logical tag's canonical representation.
pub const PORTABLE_TAGS_DIRECTORY: &str = "tags-v1";

/// Return a stable, case-insensitive key for a logical tag name.
///
/// NFC normalization plus Unicode lowercase is deliberately stricter than the
/// host filesystem. It prevents a tag pair from becoming ambiguous after a
/// store is copied between a case-sensitive Unix filesystem and Windows/macOS.
#[must_use]
pub fn portable_collision_key(value: &str) -> String {
    value.nfc().flat_map(char::to_lowercase).collect()
}

/// Explain why `value` cannot be used as a portable direct-child leaf.
///
/// The rule is independent of the current host and covers the Win32 reserved
/// device namespace, ADS/path punctuation, control characters, trailing dot or
/// space normalization, and the common 255 UTF-16-unit component bound.
#[must_use]
pub fn portable_leaf_error(value: &str) -> Option<&'static str> {
    if value.is_empty() || value == "." || value == ".." {
        return Some("leaf must not be empty, `.` or `..`");
    }
    if value.encode_utf16().count() > MAX_PORTABLE_LEAF_UTF16_UNITS {
        return Some("leaf exceeds the portable 255 UTF-16-unit limit");
    }
    if value.ends_with(['.', ' ']) {
        return Some("leaf must not end with a dot or space");
    }
    if value.chars().any(|ch| {
        ch <= '\u{1f}'
            || ch == '\u{7f}'
            || matches!(ch, '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*')
    }) {
        return Some("leaf contains a control, path, ADS, or platform-forbidden character");
    }

    let stem = value
        .split('.')
        .next()
        .unwrap_or(value)
        .trim_end_matches(['.', ' ']);
    let upper = stem.to_ascii_uppercase();
    let reserved = matches!(upper.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || upper.strip_prefix("COM").is_some_and(|suffix| {
            matches!(suffix, "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9")
        })
        || upper.strip_prefix("LPT").is_some_and(|suffix| {
            matches!(suffix, "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9")
        })
        || matches!(
            upper.as_str(),
            "COM¹" | "COM²" | "COM³" | "LPT¹" | "LPT²" | "LPT³"
        );
    reserved.then_some("leaf uses a Windows reserved device name")
}

/// Canonical physical tag leaf. Logical names never become filesystem names.
/// Case-equivalent names intentionally map to the same slot.
#[must_use]
pub fn portable_tag_leaf(logical_name: &str) -> String {
    format!("tag-{}", portable_tag_digest64(logical_name))
}

/// The bare 64-hex-character digest half of [`portable_tag_leaf`] (without
/// the `tag-` prefix) — the `digest64` value `names.jsonl` records alongside
/// `logical_name` (03-data-model.md §2 L140-152, step4b-contract-tests-p2b.md
/// PB07). Shared by the tag-creation writer and fsck's names.jsonl reader so
/// the two can never independently drift on the hash construction.
#[must_use]
pub fn portable_tag_digest64(logical_name: &str) -> String {
    let key = portable_collision_key(logical_name);
    format!("{:x}", Sha256::digest(key.as_bytes()))
}

/// Derive a portable open/view cache leaf without reusing the source basename.
///
/// A separately validated short ASCII extension is retained only so the OS can
/// still select a suitable viewer. All identity-bearing material is a fixed
/// ASCII prefix plus SHA-256 of the logical basename.
#[must_use]
pub fn portable_cache_leaf(logical_name: &str) -> String {
    let basename = logical_name
        .rsplit(['/', '\\'])
        .next()
        .unwrap_or(logical_name);
    let mut leaf = format!("open-{:x}", Sha256::digest(basename.as_bytes()));
    if let Some((_, extension)) = basename.rsplit_once('.') {
        if !extension.is_empty()
            && extension.len() <= 16
            && extension.bytes().all(|byte| byte.is_ascii_alphanumeric())
        {
            leaf.push('.');
            leaf.push_str(&extension.to_ascii_lowercase());
        }
    }
    leaf
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn portable_leaf_rejects_windows_and_cross_platform_hazards() {
        for invalid in [
            "",
            ".",
            "..",
            "CON",
            "con.txt",
            "AUX",
            "NUL.md",
            "COM1",
            "LPT9.log",
            "COM¹",
            "com².txt",
            "LPT³",
            "lpt¹.log",
            "has?mark",
            "has:ads",
            "has/slash",
            r"has\slash",
            "trail.",
            "trail ",
            "quote\"",
            "star*",
            "pipe|",
            "less<than",
        ] {
            assert!(portable_leaf_error(invalid).is_some(), "{invalid:?}");
        }
        for valid in ["v1", "release-2026.07", "研究メモ", "auxiliary.txt"] {
            assert_eq!(portable_leaf_error(valid), None, "{valid:?}");
        }
    }

    #[test]
    fn tag_leaf_is_case_and_normalization_insensitive() {
        assert_eq!(portable_tag_leaf("Release"), portable_tag_leaf("release"));
        assert_eq!(
            portable_tag_leaf("Cafe\u{301}"),
            portable_tag_leaf("Caf\u{e9}")
        );
        assert_eq!(portable_leaf_error(&portable_tag_leaf("CON")), None);
    }

    #[test]
    fn cache_leaf_never_reuses_the_logical_basename() {
        for basename in [
            "CON",
            "AUX.txt",
            "chart?.PNG",
            "file.txt:secret",
            "trail.",
            "trail ",
        ] {
            let leaf = portable_cache_leaf(basename);
            assert_ne!(leaf, basename);
            assert_eq!(portable_leaf_error(&leaf), None, "{basename:?} -> {leaf:?}");
        }
        assert!(portable_cache_leaf("report.PDF").ends_with(".pdf"));
    }
}
