//! Office (DOCX/PPTX) → converted-PDF intermediate
//! ([07-adapter-spec.md §5.1](../../../docs/07-adapter-spec.md), "Office
//! intermediate の変換機構" — 2026-07-23 addendum).
//!
//! DOCX/PPTX unit-ize through an external renderer (LibreOffice headless
//! `soffice --convert-to pdf`) rather than being parsed locally: DOCX pages
//! become `page:N`, PPTX slides become `slide:N` (1 slide = 1 converted
//! page). The renderer's raw PDF output embeds several genuinely volatile
//! fields (wall-clock timestamps, a document ID, LibreOffice's own content
//! checksum) that differ across otherwise-identical conversions;
//! [`normalize_converted_pdf`] rewrites them to fixed, SAME-LENGTH values so
//! byte length — and every xref offset — survives, keeping `prepared_hash`
//! stable within one renderer version (03 §2.1's prepare-profile/renderer
//! driven gen+1 path absorbs an actual renderer version bump). The
//! renderer's own name/version (`/Producer`) is deliberately left untouched
//! — it is provenance, not identity, and SHOULD vary when the renderer
//! changes (07 §5.1: "renderer の名称・版は provenance として記録し、hash 入力には
//! しない").

use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

use crate::{AdapterError, Result};

/// Test seam env var: its value is a path to a fixture PDF returned
/// VERBATIM for any input — already deterministic, so
/// [`OfficeConverter::convert_to_pdf`] skips normalization for this backend.
/// `version()` reports `"test-converter"`. Checked before
/// [`OFFICE_CONVERTER_ENV`].
pub const TEST_OFFICE_CONVERT_ENV: &str = "KIO_TEST_OFFICE_CONVERT";
/// Explicit converter binary path, checked before the `soffice` PATH lookup.
pub const OFFICE_CONVERTER_ENV: &str = "KIO_OFFICE_CONVERTER";
/// The PATH-resolved program name probed as the last resolution step.
const DEFAULT_OFFICE_CONVERTER_PROGRAM: &str = "soffice";

const DOCX_MEDIA_TYPE: &str =
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const PPTX_MEDIA_TYPE: &str =
    "application/vnd.openxmlformats-officedocument.presentationml.presentation";

/// True exactly for the DOCX and PPTX OOXML mimes (07 §5.1's 2026-07-23
/// addendum). XLSX is deliberately excluded — its conversion machinery is
/// "本追記の対象外 (未定義のまま — 将来ラウンド)".
#[must_use]
pub fn is_office_media(media_type: &str) -> bool {
    matches!(media_type, DOCX_MEDIA_TYPE | PPTX_MEDIA_TYPE)
}

#[derive(Debug, Clone)]
enum ConverterBackend {
    /// Test seam: [`OfficeConverter::convert_to_pdf`] returns this file's
    /// bytes verbatim for ANY input.
    Seam { fixture_path: PathBuf },
    /// A real `soffice`-compatible binary invoked via [`Command`].
    Real { program: PathBuf },
}

/// A resolved Office → PDF converter (07 §5.1). Obtain one via
/// [`resolve_office_converter`].
#[derive(Debug, Clone)]
pub struct OfficeConverter {
    backend: ConverterBackend,
    version: String,
}

impl OfficeConverter {
    /// The renderer's self-reported version (provenance-only — never a hash
    /// input, 07 §5.1). `"test-converter"` for the test seam.
    #[must_use]
    pub fn version(&self) -> &str {
        &self.version
    }

    /// Convert `input` (DOCX or PPTX bytes, per `media_type`) to
    /// deterministically-normalized PDF bytes. The seam backend returns its
    /// fixture file verbatim (already deterministic, so normalization is
    /// skipped) regardless of `input`/`media_type`. The real backend invokes
    /// the external renderer and then normalizes its output — see
    /// [`normalize_converted_pdf`].
    ///
    /// # Errors
    /// `AdapterError::ContractViolation` on any conversion failure (missing
    /// binary at call time, non-zero renderer exit, missing/invalid output,
    /// or an unreadable seam fixture) — 07 §5.1: a runtime conversion
    /// failure "joins" contract_violation semantics at the pipeline layer
    /// (04 §5.3: retried once for the same input).
    pub fn convert_to_pdf(&self, input: &[u8], media_type: &str) -> Result<Vec<u8>> {
        match &self.backend {
            ConverterBackend::Seam { fixture_path } => std::fs::read(fixture_path).map_err(|err| {
                AdapterError::ContractViolation(format!(
                    "office converter test seam fixture unreadable at {}: {err}",
                    fixture_path.display()
                ))
            }),
            ConverterBackend::Real { program } => {
                let pdf = convert_with_real_binary(program, input, media_type)?;
                Ok(normalize_converted_pdf(&pdf))
            }
        }
    }
}

/// Resolve an Office converter (07 §5.1). Resolution order:
/// [`TEST_OFFICE_CONVERT_ENV`] (test seam) → [`OFFICE_CONVERTER_ENV`]
/// (explicit binary path) → `soffice` on PATH — the first of these that is
/// SET wins outright (a set-but-broken explicit override does not fall
/// through to PATH; that would silently substitute a different converter
/// than the one named). `None` means unavailable — a probe/version failure
/// counts as unavailable, NEVER an `Err` (07 §5.1: "renderer が環境に存在しない
/// 場合...doomed task を作らない" — the caller must be able to silently skip
/// enqueueing rather than crash).
#[must_use]
pub fn resolve_office_converter() -> Option<OfficeConverter> {
    if let Ok(fixture_path) = std::env::var(TEST_OFFICE_CONVERT_ENV) {
        if fixture_path.is_empty() {
            return None;
        }
        return Some(OfficeConverter {
            backend: ConverterBackend::Seam {
                fixture_path: PathBuf::from(fixture_path),
            },
            version: "test-converter".to_owned(),
        });
    }
    if let Ok(explicit) = std::env::var(OFFICE_CONVERTER_ENV) {
        if explicit.is_empty() {
            return None;
        }
        return probe_real_converter(PathBuf::from(explicit));
    }
    probe_real_converter(PathBuf::from(DEFAULT_OFFICE_CONVERTER_PROGRAM))
}

/// Probe a candidate converter binary via `--version`. ANY failure (spawn
/// error / missing binary, non-zero exit, empty stdout) resolves to `None`
/// — never an `Err`, per [`resolve_office_converter`]'s contract.
fn probe_real_converter(program: PathBuf) -> Option<OfficeConverter> {
    let output = Command::new(&program).arg("--version").output().ok()?;
    if !output.status.success() {
        return None;
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let version = stdout.lines().next()?.trim();
    if version.is_empty() {
        return None;
    }
    Some(OfficeConverter {
        backend: ConverterBackend::Real { program },
        version: version.to_owned(),
    })
}

fn office_extension(media_type: &str) -> Option<&'static str> {
    match media_type {
        DOCX_MEDIA_TYPE => Some("docx"),
        PPTX_MEDIA_TYPE => Some("pptx"),
        _ => None,
    }
}

/// RAII cleanup for the per-conversion scratch directory (staged input,
/// output dir, LibreOffice user-profile dir) — removed best-effort on every
/// exit path, including an early `?` return from [`convert_with_real_binary`].
struct TempDirGuard(PathBuf);

impl Drop for TempDirGuard {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// A process-unique scratch directory under the OS temp dir. `tempfile` (the
/// crate used elsewhere in this workspace for this) is a dev-dependency
/// only in every crate's `Cargo.toml` — unavailable to non-test runtime code
/// — so this hand-rolls the same PID + monotonic-counter + nanosecond-
/// timestamp uniqueness strategy rather than promoting a new dependency.
fn unique_temp_dir(label: &str) -> Result<PathBuf> {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    let counter = COUNTER.fetch_add(1, Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!(
        "kio-office-{label}-{}-{nanos}-{counter}",
        std::process::id()
    ));
    std::fs::create_dir_all(&dir).map_err(|err| {
        AdapterError::ContractViolation(format!(
            "failed to create office-convert scratch dir at {}: {err}",
            dir.display()
        ))
    })?;
    Ok(dir)
}

/// Run the real renderer: stage `input` under the correct extension, convert
/// via `--headless --convert-to pdf --outdir`, and read back the produced
/// PDF. `-env:UserInstallation` points at a private, per-invocation profile
/// dir — LibreOffice refuses to start a second instance against a shared
/// profile (which would otherwise serialize or deadlock concurrent prepare
/// calls); verified against the real `/opt/homebrew/bin/soffice` 26.2.4.2 on
/// the implementing machine. Any failure (spawn, non-zero exit, missing or
/// non-PDF output) is `AdapterError::ContractViolation`.
fn convert_with_real_binary(program: &Path, input: &[u8], media_type: &str) -> Result<Vec<u8>> {
    let extension = office_extension(media_type).ok_or_else(|| {
        AdapterError::ContractViolation(format!(
            "office converter invoked for a non-office media type: {media_type}"
        ))
    })?;
    let workdir = unique_temp_dir("convert")?;
    let _cleanup = TempDirGuard(workdir.clone());

    let input_path = workdir.join(format!("input.{extension}"));
    std::fs::write(&input_path, input).map_err(|err| {
        AdapterError::ContractViolation(format!(
            "failed to stage office input at {}: {err}",
            input_path.display()
        ))
    })?;

    let outdir = workdir.join("out");
    std::fs::create_dir_all(&outdir).map_err(|err| {
        AdapterError::ContractViolation(format!(
            "failed to create office-convert output dir at {}: {err}",
            outdir.display()
        ))
    })?;
    let profile_dir = workdir.join("lo-profile");

    let output = Command::new(program)
        .arg("--headless")
        .arg(format!(
            "-env:UserInstallation=file://{}",
            profile_dir.display()
        ))
        .arg("--convert-to")
        .arg("pdf")
        .arg("--outdir")
        .arg(&outdir)
        .arg(&input_path)
        .output()
        .map_err(|err| {
            AdapterError::ContractViolation(format!(
                "failed to spawn office converter {}: {err}",
                program.display()
            ))
        })?;
    if !output.status.success() {
        return Err(AdapterError::ContractViolation(format!(
            "office converter {} exited with {}: {}",
            program.display(),
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }

    let produced_pdf = outdir.join("input.pdf");
    let pdf_bytes = std::fs::read(&produced_pdf).map_err(|err| {
        AdapterError::ContractViolation(format!(
            "office converter did not produce {}: {err}",
            produced_pdf.display()
        ))
    })?;
    if !pdf_bytes.starts_with(b"%PDF") {
        return Err(AdapterError::ContractViolation(format!(
            "office converter output at {} is not a PDF (missing %PDF magic)",
            produced_pdf.display()
        )));
    }
    Ok(pdf_bytes)
}

/// Deterministically normalize a converter's raw PDF output (07 §5.1):
/// rewrite every volatile-metadata occurrence found by a conservative
/// literal-pattern scan to a FIXED value of the SAME byte length, so total
/// length — and every xref offset — is unchanged. This is not a PDF parser:
/// it recognizes only the exact textual shapes below and leaves everything
/// else untouched, including the renderer's own `/Producer` string (07
/// §5.1 — that string SHOULD vary across renderer versions, so it is
/// deliberately not among the fields normalized here).
///
/// Covers the two constructs 07 §5.1 names explicitly:
///   - `/CreationDate (…)` / `/ModDate (…)` — Info-dict literal-string dates.
///   - `/ID [<…><…>]` — the trailer's two hex-string document IDs.
///
/// Plus two more volatility sources confirmed empirically against the real
/// `/opt/homebrew/bin/soffice` (LibreOffice 26.2.4.2) binary: converting the
/// SAME input twice is NOT byte-identical after normalizing only the two
/// constructs above.
///   - `/DocChecksum /<hex>` — a LibreOffice PDF-export trailer extension (a
///     bare PDF *name* token, not a literal string or hex string).
///   - the XMP metadata packet's `<xmp:CreateDate>`, `<xmp:ModifyDate>`,
///     `<xmp:MetadataDate>` elements — LibreOffice duplicates the same
///     timestamps as plain (uncompressed) XML inside the PDF's
///     `/Type/Metadata/Subtype/XML` stream; the Info-dict fix alone does not
///     reach this second copy.
///
/// Idempotent: normalizing already-normalized bytes is a no-op (the second
/// pass finds the same fixed-length values already in place and rewrites
/// them to themselves).
fn normalize_converted_pdf(pdf: &[u8]) -> Vec<u8> {
    let mut bytes = pdf.to_vec();
    overwrite_paren_value(&mut bytes, b"/CreationDate");
    overwrite_paren_value(&mut bytes, b"/ModDate");
    overwrite_id_hex_strings(&mut bytes);
    overwrite_name_value(&mut bytes, b"/DocChecksum");
    for tag in ["xmp:CreateDate", "xmp:ModifyDate", "xmp:MetadataDate"] {
        overwrite_xml_element_text(&mut bytes, tag);
    }
    bytes
}

/// Rewrite every occurrence of `key`'s parenthesized VALUE (`key(…)` /
/// `key (…)`) to a fixed value of the SAME byte length. Handles backslash
/// escapes and balanced nested parens (a PDF literal string may itself
/// contain unescaped, balanced parens) via [`find_literal_string_end`], the
/// same conservative-but-correct spirit as `skip_pdf_literal_string` in
/// `deterministic.rs`. An unterminated literal (malformed input) stops the
/// scan rather than risk corrupting the buffer.
fn overwrite_paren_value(bytes: &mut [u8], key: &[u8]) {
    let mut search_from = 0usize;
    while let Some(offset) = find_subslice(&bytes[search_from..], key) {
        let key_start = search_from + offset;
        let mut cursor = key_start + key.len();
        while bytes
            .get(cursor)
            .is_some_and(|byte| byte.is_ascii_whitespace())
        {
            cursor += 1;
        }
        if bytes.get(cursor) != Some(&b'(') {
            search_from = key_start + key.len();
            continue;
        }
        let value_start = cursor + 1;
        match find_literal_string_end(bytes, value_start) {
            Some(value_end) => {
                let filler = fixed_length_pdf_date_filler(value_end - value_start);
                bytes[value_start..value_end].copy_from_slice(&filler);
                search_from = value_end + 1;
            }
            None => break,
        }
    }
}

/// The index of the unescaped `)` that closes the literal string starting
/// right after its opening `(` (i.e. `start` is the byte AFTER `(`).
/// Balanced nested parens are tracked so an embedded, unescaped `(…)` pair
/// does not terminate the scan early.
fn find_literal_string_end(bytes: &[u8], start: usize) -> Option<usize> {
    let mut index = start;
    let mut depth = 1usize;
    while index < bytes.len() {
        match bytes[index] {
            b'\\' => index = (index + 2).min(bytes.len()),
            b'(' => {
                depth += 1;
                index += 1;
            }
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return Some(index);
                }
                index += 1;
            }
            _ => index += 1,
        }
    }
    None
}

/// A deterministic, same-length filler for a PDF date literal-string VALUE,
/// built from the canonical zero-date `D:19700101000000Z` (17 bytes),
/// truncated or zero-padded to match. No paren/backslash bytes ever occur in
/// it, so it is always safe to splice back into a `(...)` literal.
fn fixed_length_pdf_date_filler(length: usize) -> Vec<u8> {
    const CANONICAL: &[u8] = b"D:19700101000000Z";
    if length <= CANONICAL.len() {
        CANONICAL[..length].to_vec()
    } else {
        let mut filler = CANONICAL.to_vec();
        filler.resize(length, b'0');
        filler
    }
}

/// Rewrite the two hex strings of every `/ID [<…><…>]` occurrence to
/// same-length all-zero hex. Handles whitespace/newline between the two hex
/// strings (LibreOffice wraps the line there) since [`find_hex_string`]
/// simply seeks the next `<`.
fn overwrite_id_hex_strings(bytes: &mut [u8]) {
    let mut search_from = 0usize;
    while let Some(offset) = find_subslice(&bytes[search_from..], b"/ID") {
        let key_start = search_from + offset;
        let mut cursor = key_start + 3;
        while bytes
            .get(cursor)
            .is_some_and(|byte| byte.is_ascii_whitespace())
        {
            cursor += 1;
        }
        if bytes.get(cursor) != Some(&b'[') {
            search_from = key_start + 3;
            continue;
        }
        let Some((first_start, first_end)) = find_hex_string(bytes, cursor + 1) else {
            search_from = key_start + 3;
            continue;
        };
        let Some((second_start, second_end)) = find_hex_string(bytes, first_end + 1) else {
            search_from = key_start + 3;
            continue;
        };
        for byte in &mut bytes[first_start..first_end] {
            *byte = b'0';
        }
        for byte in &mut bytes[second_start..second_end] {
            *byte = b'0';
        }
        search_from = second_end + 1;
    }
}

/// The `(content_start, content_end)` byte range (EXCLUDING the angle
/// brackets) of the next `<…>` string at or after `from`.
fn find_hex_string(bytes: &[u8], from: usize) -> Option<(usize, usize)> {
    let open = find_byte(bytes, from, b'<')?;
    let close = find_byte(bytes, open + 1, b'>')?;
    Some((open + 1, close))
}

/// Rewrite the PDF *name* value that follows `key` (`key /VALUE`, e.g.
/// LibreOffice's `/DocChecksum /F9B8AED3…`) to a fixed all-zero value of the
/// SAME byte length. A PDF name token ends at the next delimiter
/// (whitespace or one of `()<>[]{}/%`), mirroring `is_pdf_delimiter` in
/// `deterministic.rs`.
fn overwrite_name_value(bytes: &mut [u8], key: &[u8]) {
    let mut search_from = 0usize;
    while let Some(offset) = find_subslice(&bytes[search_from..], key) {
        let key_start = search_from + offset;
        let mut cursor = key_start + key.len();
        while bytes
            .get(cursor)
            .is_some_and(|byte| byte.is_ascii_whitespace())
        {
            cursor += 1;
        }
        if bytes.get(cursor) != Some(&b'/') {
            search_from = key_start + key.len();
            continue;
        }
        let value_start = cursor + 1;
        let mut value_end = value_start;
        while bytes
            .get(value_end)
            .is_some_and(|byte| !is_pdf_name_delimiter(*byte))
        {
            value_end += 1;
        }
        for byte in &mut bytes[value_start..value_end] {
            *byte = b'0';
        }
        search_from = value_end;
    }
}

fn is_pdf_name_delimiter(byte: u8) -> bool {
    byte.is_ascii_whitespace()
        || matches!(
            byte,
            b'(' | b')' | b'<' | b'>' | b'[' | b']' | b'{' | b'}' | b'/' | b'%'
        )
}

/// Rewrite the text content of every `<tag>…</tag>` occurrence to a fixed
/// value of the SAME byte length. `tag` carries no `<`/`>` — both are added
/// internally. Used for the XMP packet's date elements, which LibreOffice
/// emits as plain (uncompressed) XML inside the PDF's `/Metadata` stream.
fn overwrite_xml_element_text(bytes: &mut [u8], tag: &str) {
    let open_tag = format!("<{tag}>").into_bytes();
    let close_tag = format!("</{tag}>").into_bytes();
    let mut search_from = 0usize;
    while let Some(offset) = find_subslice(&bytes[search_from..], &open_tag) {
        let value_start = search_from + offset + open_tag.len();
        match find_subslice(&bytes[value_start..], &close_tag) {
            Some(rel_end) => {
                let value_end = value_start + rel_end;
                let filler = fixed_length_xml_date_filler(value_end - value_start);
                bytes[value_start..value_end].copy_from_slice(&filler);
                search_from = value_end + close_tag.len();
            }
            None => break,
        }
    }
}

/// A deterministic, same-length filler for an XMP date ELEMENT text value,
/// built from the canonical zero-date `1970-01-01T00:00:00+00:00` (25
/// bytes), truncated or zero-padded to match. Contains no `<`/`>`, so it can
/// never be mistaken for XML markup once spliced back in.
fn fixed_length_xml_date_filler(length: usize) -> Vec<u8> {
    const CANONICAL: &[u8] = b"1970-01-01T00:00:00+00:00";
    if length <= CANONICAL.len() {
        CANONICAL[..length].to_vec()
    } else {
        let mut filler = CANONICAL.to_vec();
        filler.resize(length, b'0');
        filler
    }
}

fn find_byte(bytes: &[u8], from: usize, target: u8) -> Option<usize> {
    bytes
        .get(from..)?
        .iter()
        .position(|&byte| byte == target)
        .map(|offset| from + offset)
}

fn find_subslice(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.is_empty() || haystack.len() < needle.len() {
        return None;
    }
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine;

    static OFFICE_ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    /// RAII helper: temporarily set/remove a process env var for the
    /// duration of a test, restoring the PRIOR value (or absence) on drop —
    /// including on panic, so one failing test cannot corrupt env state for
    /// whichever other test in this process happens to run next. Env vars
    /// are process-global; `OFFICE_ENV_LOCK` above serializes this file's
    /// own env-touching tests against EACH OTHER (nothing else in this
    /// crate touches `PATH` or the office-converter env vars, confirmed
    /// before adding this).
    struct EnvVarGuard {
        key: &'static str,
        previous: Option<String>,
    }

    impl EnvVarGuard {
        fn set(key: &'static str, value: &str) -> Self {
            let previous = std::env::var(key).ok();
            std::env::set_var(key, value);
            Self { key, previous }
        }

        fn remove(key: &'static str) -> Self {
            let previous = std::env::var(key).ok();
            std::env::remove_var(key);
            Self { key, previous }
        }
    }

    impl Drop for EnvVarGuard {
        fn drop(&mut self) {
            match &self.previous {
                Some(value) => std::env::set_var(self.key, value),
                None => std::env::remove_var(self.key),
            }
        }
    }

    // ---- is_office_media -------------------------------------------------

    #[test]
    fn is_office_media_truth_table() {
        assert!(is_office_media(DOCX_MEDIA_TYPE));
        assert!(is_office_media(PPTX_MEDIA_TYPE));
        assert!(!is_office_media(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ));
        assert!(!is_office_media("application/pdf"));
        assert!(!is_office_media("text/plain"));
        assert!(!is_office_media("text/markdown"));
        assert!(!is_office_media("application/octet-stream"));
        assert!(!is_office_media("image/png"));
        assert!(!is_office_media(""));
    }

    // ---- resolution / seam -------------------------------------------------

    #[test]
    fn seam_converter_returns_fixture_bytes_verbatim_for_any_input() {
        let _lock = OFFICE_ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        let fixture_path = dir.path().join("fixture.pdf");
        let fixture_bytes = b"%PDF-1.4\nfixture content\n%%EOF";
        std::fs::write(&fixture_path, fixture_bytes).unwrap();

        let _seam = EnvVarGuard::set(TEST_OFFICE_CONVERT_ENV, &fixture_path.display().to_string());
        let converter = resolve_office_converter().expect("seam converter resolves");
        assert_eq!(converter.version(), "test-converter");

        // "returned verbatim for ANY input" — arbitrary bytes/media type.
        let out = converter
            .convert_to_pdf(b"not actually a docx", DOCX_MEDIA_TYPE)
            .unwrap();
        assert_eq!(out, fixture_bytes);

        let out2 = converter.convert_to_pdf(b"", "text/plain").unwrap();
        assert_eq!(out2, fixture_bytes);
    }

    #[test]
    fn resolution_order_prefers_seam_over_explicit_path() {
        let _lock = OFFICE_ENV_LOCK.lock().unwrap();
        let dir = tempfile::tempdir().unwrap();
        let fixture_path = dir.path().join("fixture.pdf");
        std::fs::write(&fixture_path, b"seam-bytes").unwrap();

        let _explicit = EnvVarGuard::set(OFFICE_CONVERTER_ENV, "/does/not/matter/for/this/case");
        let _seam = EnvVarGuard::set(TEST_OFFICE_CONVERT_ENV, &fixture_path.display().to_string());
        let converter = resolve_office_converter().expect("seam must win over explicit");
        assert_eq!(converter.version(), "test-converter");
    }

    #[test]
    fn no_converter_available_resolves_to_none() {
        let _lock = OFFICE_ENV_LOCK.lock().unwrap();
        let _clear_seam = EnvVarGuard::remove(TEST_OFFICE_CONVERT_ENV);
        let _clear_explicit = EnvVarGuard::remove(OFFICE_CONVERTER_ENV);
        let _scrub_path = EnvVarGuard::set("PATH", "/nonexistent-kio-test-path");
        assert!(resolve_office_converter().is_none());
    }

    #[test]
    fn explicit_converter_pointing_at_missing_binary_resolves_to_none() {
        let _lock = OFFICE_ENV_LOCK.lock().unwrap();
        let _clear_seam = EnvVarGuard::remove(TEST_OFFICE_CONVERT_ENV);
        let _explicit = EnvVarGuard::set(
            OFFICE_CONVERTER_ENV,
            "/definitely/not/a/real/kio-office-converter-binary",
        );
        assert!(
            resolve_office_converter().is_none(),
            "a probe failure on an explicit override must resolve to None, not fall through to PATH"
        );
    }

    // ---- normalization -----------------------------------------------------

    fn build_fixture_pdf_with_metadata(
        creation_date: &str,
        mod_date: &str,
        id1: &str,
        id2: &str,
    ) -> Vec<u8> {
        format!(
            "%PDF-1.4\n\
             1 0 obj << /Type /Catalog >> endobj\n\
             2 0 obj << /CreationDate({creation_date}) /ModDate({mod_date}) >> endobj\n\
             trailer\n\
             <</Size 3/Root 1 0 R/Info 2 0 R/ID [ <{id1}>\n<{id2}> ]>>\n\
             startxref\n0\n%%EOF\n"
        )
        .into_bytes()
    }

    #[test]
    fn normalize_rewrites_creationdate_moddate_id_preserving_length_and_is_idempotent() {
        let pdf = build_fixture_pdf_with_metadata(
            "D:20260101120000+09'00'",
            "D:20260102130000+09'00'",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        );
        let normalized = normalize_converted_pdf(&pdf);

        // (b) byte length unchanged.
        assert_eq!(normalized.len(), pdf.len());

        // (a) values rewritten.
        let text = String::from_utf8_lossy(&normalized);
        assert!(!text.contains("20260101120000"));
        assert!(!text.contains("20260102130000"));
        assert!(!text.contains("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"));
        assert!(!text.contains("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"));
        // The fixture's 23-byte date values (with a `'09'00'` tz suffix, matching
        // real LibreOffice output) are longer than the 17-byte canonical filler,
        // so the filler is zero-padded out to the original length.
        assert!(text.contains("/CreationDate(D:19700101000000Z000000)"));
        assert!(text.contains("/ModDate(D:19700101000000Z000000)"));
        let id_needle = "/ID [ <";
        let id_pos = text.find(id_needle).expect("ID present");
        let id1_value = &text[id_pos + id_needle.len()..id_pos + id_needle.len() + 32];
        assert!(id1_value.chars().all(|ch| ch == '0'));

        // (c) idempotent.
        let twice = normalize_converted_pdf(&normalized);
        assert_eq!(twice, normalized);
    }

    #[test]
    fn normalize_handles_multiple_occurrences_docchecksum_and_xmp_dates() {
        let mut pdf = build_fixture_pdf_with_metadata(
            "D:20260101120000+09'00'",
            "D:20260102130000+09'00'",
            "1111111111111111111111111111aa",
            "2222222222222222222222222222bb",
        );
        pdf.extend_from_slice(
            b"\n15 0 obj <</Type/Metadata/Subtype/XML>>\nstream\n\
              <x:xmpmeta><rdf:RDF><rdf:Description xmlns:xmp=\"http://ns.adobe.com/xap/1.0/\">\
              <xmp:CreateDate>2026-01-01T12:00:00+09:00</xmp:CreateDate>\
              <xmp:ModifyDate>2026-01-02T13:00:00+09:00</xmp:ModifyDate>\
              <xmp:MetadataDate>2026-01-02T13:00:00+09:00</xmp:MetadataDate>\
              </rdf:Description></rdf:RDF></x:xmpmeta>\nendstream\nendobj\n\
              16 0 obj << /DocChecksum /F9B8AED31B45B7E5448225558F0F91DC >> endobj\n\
              17 0 obj << /CreationDate(D:20260101120000+09'00') >> endobj\n",
        );

        let normalized = normalize_converted_pdf(&pdf);
        assert_eq!(normalized.len(), pdf.len());

        let text = String::from_utf8_lossy(&normalized);
        assert!(!text.contains("2026-01-01T12:00:00"));
        assert!(!text.contains("2026-01-02T13:00:00"));
        assert!(!text.contains("F9B8AED31B45B7E5448225558F0F91DC"));
        // Both /CreationDate occurrences (multiple-occurrence handling); see
        // the padding note in the test above for why the filler is 23 bytes.
        assert_eq!(
            text.matches("/CreationDate(D:19700101000000Z000000)")
                .count(),
            2
        );
        assert!(text.contains("<xmp:CreateDate>1970-01-01T00:00:00+00:00</xmp:CreateDate>"));
        assert!(text.contains("<xmp:ModifyDate>1970-01-01T00:00:00+00:00</xmp:ModifyDate>"));
        assert!(text.contains("<xmp:MetadataDate>1970-01-01T00:00:00+00:00</xmp:MetadataDate>"));

        let checksum_needle = "/DocChecksum /";
        let pos = text.find(checksum_needle).expect("DocChecksum present");
        let value = &text[pos + checksum_needle.len()..pos + checksum_needle.len() + 32];
        assert!(value.chars().all(|ch| ch == '0'));

        let twice = normalize_converted_pdf(&normalized);
        assert_eq!(twice, normalized, "normalization must be idempotent");
    }

    #[test]
    fn normalize_is_a_no_op_when_no_volatile_fields_are_present() {
        let pdf = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n".to_vec();
        let normalized = normalize_converted_pdf(&pdf);
        assert_eq!(normalized, pdf);
    }

    // ---- real soffice integration (env-gated) ------------------------------
    //
    // Helper script used ONCE to produce the embedded *_FIXTURE_B64 constants
    // below (python3 stdlib only — `zip` is not a dependency anywhere in this
    // workspace's Cargo.toml files, confirmed before writing this). Fixed ZIP
    // entry timestamps (1980-01-01) make the script's OWN output reproducible
    // run to run. DOCX:
    //
    // ```python
    // import zipfile, base64
    // def w(zf, name, data):
    //     info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    //     info.compress_type = zipfile.ZIP_STORED
    //     zf.writestr(info, data)
    // CONTENT_TYPES = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    // <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    // <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    // <Default Extension="xml" ContentType="application/xml"/>
    // <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    // </Types>'''
    // RELS = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    // <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    // <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    // </Relationships>'''
    // DOCUMENT = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    // <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    // <w:body><w:p><w:r><w:t>Kio office convert test</w:t></w:r></w:p></w:body>
    // </w:document>'''
    // with zipfile.ZipFile("minimal.docx", "w", zipfile.ZIP_STORED) as zf:
    //     w(zf, "[Content_Types].xml", CONTENT_TYPES)
    //     w(zf, "_rels/.rels", RELS)
    //     w(zf, "word/document.xml", DOCUMENT)
    // print(base64.b64encode(open("minimal.docx", "rb").read()).decode())
    // ```
    //
    // PPTX needs the fuller OOXML presentation skeleton (presentation.xml +
    // one slide + one slideLayout + one slideMaster + one theme, each with
    // its own `_rels`) — same `w()` helper, additional parts:
    //
    // ```python
    // PRESENTATION = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    // <p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
    // <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
    // <p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>
    // <p:sldSz cx="9144000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/>
    // </p:presentation>'''
    // # ... slide1.xml / slideLayout1.xml / slideMaster1.xml / theme1.xml and
    // # their _rels, and [Content_Types].xml Overrides for all five parts —
    // # full text lives in this crate's git history / task notes for
    // # office_convert.rs; omitted here for brevity.
    // ```

    fn decode_fixture(b64: &str) -> Vec<u8> {
        base64::engine::general_purpose::STANDARD
            .decode(b64)
            .expect("embedded fixture base64 decodes")
    }

    const DOCX_FIXTURE_B64: &str = "UEsDBBQAAAAAAAAAIQDMg9OxswEAALMBAAATAAAAW0NvbnRlbnRfVHlwZXNdLnhtbDw/eG1sIHZlcnNpb249IjEuMCIgZW5jb2Rpbmc9IlVURi04IiBzdGFuZGFsb25lPSJ5ZXMiPz4KPFR5cGVzIHhtbG5zPSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvcGFja2FnZS8yMDA2L2NvbnRlbnQtdHlwZXMiPgo8RGVmYXVsdCBFeHRlbnNpb249InJlbHMiIENvbnRlbnRUeXBlPSJhcHBsaWNhdGlvbi92bmQub3BlbnhtbGZvcm1hdHMtcGFja2FnZS5yZWxhdGlvbnNoaXBzK3htbCIvPgo8RGVmYXVsdCBFeHRlbnNpb249InhtbCIgQ29udGVudFR5cGU9ImFwcGxpY2F0aW9uL3htbCIvPgo8T3ZlcnJpZGUgUGFydE5hbWU9Ii93b3JkL2RvY3VtZW50LnhtbCIgQ29udGVudFR5cGU9ImFwcGxpY2F0aW9uL3ZuZC5vcGVueG1sZm9ybWF0cy1vZmZpY2Vkb2N1bWVudC53b3JkcHJvY2Vzc2luZ21sLmRvY3VtZW50Lm1haW4reG1sIi8+CjwvVHlwZXM+ClBLAwQUAAAAAAAAACEAA9VLhC0BAAAtAQAACwAAAF9yZWxzLy5yZWxzPD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9InllcyI/Pgo8UmVsYXRpb25zaGlwcyB4bWxucz0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL3BhY2thZ2UvMjAwNi9yZWxhdGlvbnNoaXBzIj4KPFJlbGF0aW9uc2hpcCBJZD0icklkMSIgVHlwZT0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL29mZmljZURvY3VtZW50LzIwMDYvcmVsYXRpb25zaGlwcy9vZmZpY2VEb2N1bWVudCIgVGFyZ2V0PSJ3b3JkL2RvY3VtZW50LnhtbCIvPgo8L1JlbGF0aW9uc2hpcHM+ClBLAwQUAAAAAAAAACEAjUhHZOYAAADmAAAAEQAAAHdvcmQvZG9jdW1lbnQueG1sPD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9InllcyI/Pgo8dzpkb2N1bWVudCB4bWxuczp3PSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvd29yZHByb2Nlc3NpbmdtbC8yMDA2L21haW4iPgo8dzpib2R5Pgo8dzpwPjx3OnI+PHc6dD5LQ1Mgb2ZmaWNlIGNvbnZlcnQgdGVzdDwvdzp0PjwvdzpyPjwvdzpwPgo8L3c6Ym9keT4KPC93OmRvY3VtZW50PgpQSwECFAMUAAAAAAAAACEAzIPTsbMBAACzAQAAEwAAAAAAAAAAAAAAgAEAAAAAW0NvbnRlbnRfVHlwZXNdLnhtbFBLAQIUAxQAAAAAAAAAIQAD1UuELQEAAC0BAAALAAAAAAAAAAAAAACAAeQBAABfcmVscy8ucmVsc1BLAQIUAxQAAAAAAAAAIQCNSEdk5gAAAOYAAAARAAAAAAAAAAAAAACAAToDAAB3b3JkL2RvY3VtZW50LnhtbFBLBQYAAAAAAwADALkAAABPBAAAAAA=";
    const PPTX_FIXTURE_B64: &str = "UEsDBBQAAAAAAAAAIQCMwBYR2AMAANgDAAATAAAAW0NvbnRlbnRfVHlwZXNdLnhtbDw/eG1sIHZlcnNpb249IjEuMCIgZW5jb2Rpbmc9IlVURi04IiBzdGFuZGFsb25lPSJ5ZXMiPz4KPFR5cGVzIHhtbG5zPSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvcGFja2FnZS8yMDA2L2NvbnRlbnQtdHlwZXMiPgo8RGVmYXVsdCBFeHRlbnNpb249InJlbHMiIENvbnRlbnRUeXBlPSJhcHBsaWNhdGlvbi92bmQub3BlbnhtbGZvcm1hdHMtcGFja2FnZS5yZWxhdGlvbnNoaXBzK3htbCIvPgo8RGVmYXVsdCBFeHRlbnNpb249InhtbCIgQ29udGVudFR5cGU9ImFwcGxpY2F0aW9uL3htbCIvPgo8T3ZlcnJpZGUgUGFydE5hbWU9Ii9wcHQvcHJlc2VudGF0aW9uLnhtbCIgQ29udGVudFR5cGU9ImFwcGxpY2F0aW9uL3ZuZC5vcGVueG1sZm9ybWF0cy1vZmZpY2Vkb2N1bWVudC5wcmVzZW50YXRpb25tbC5wcmVzZW50YXRpb24ubWFpbit4bWwiLz4KPE92ZXJyaWRlIFBhcnROYW1lPSIvcHB0L3NsaWRlcy9zbGlkZTEueG1sIiBDb250ZW50VHlwZT0iYXBwbGljYXRpb24vdm5kLm9wZW54bWxmb3JtYXRzLW9mZmljZWRvY3VtZW50LnByZXNlbnRhdGlvbm1sLnNsaWRlK3htbCIvPgo8T3ZlcnJpZGUgUGFydE5hbWU9Ii9wcHQvc2xpZGVMYXlvdXRzL3NsaWRlTGF5b3V0MS54bWwiIENvbnRlbnRUeXBlPSJhcHBsaWNhdGlvbi92bmQub3BlbnhtbGZvcm1hdHMtb2ZmaWNlZG9jdW1lbnQucHJlc2VudGF0aW9ubWwuc2xpZGVMYXlvdXQreG1sIi8+CjxPdmVycmlkZSBQYXJ0TmFtZT0iL3BwdC9zbGlkZU1hc3RlcnMvc2xpZGVNYXN0ZXIxLnhtbCIgQ29udGVudFR5cGU9ImFwcGxpY2F0aW9uL3ZuZC5vcGVueG1sZm9ybWF0cy1vZmZpY2Vkb2N1bWVudC5wcmVzZW50YXRpb25tbC5zbGlkZU1hc3Rlcit4bWwiLz4KPE92ZXJyaWRlIFBhcnROYW1lPSIvcHB0L3RoZW1lL3RoZW1lMS54bWwiIENvbnRlbnRUeXBlPSJhcHBsaWNhdGlvbi92bmQub3BlbnhtbGZvcm1hdHMtb2ZmaWNlZG9jdW1lbnQudGhlbWUreG1sIi8+CjwvVHlwZXM+ClBLAwQUAAAAAAAAACEACaoHxzABAAAwAQAACwAAAF9yZWxzLy5yZWxzPD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9InllcyI/Pgo8UmVsYXRpb25zaGlwcyB4bWxucz0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL3BhY2thZ2UvMjAwNi9yZWxhdGlvbnNoaXBzIj4KPFJlbGF0aW9uc2hpcCBJZD0icklkMSIgVHlwZT0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL29mZmljZURvY3VtZW50LzIwMDYvcmVsYXRpb25zaGlwcy9vZmZpY2VEb2N1bWVudCIgVGFyZ2V0PSJwcHQvcHJlc2VudGF0aW9uLnhtbCIvPgo8L1JlbGF0aW9uc2hpcHM+ClBLAwQUAAAAAAAAACEATomFuAUCAAAFAgAAFAAAAHBwdC9wcmVzZW50YXRpb24ueG1sPD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9InllcyI/Pgo8cDpwcmVzZW50YXRpb24geG1sbnM6YT0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL2RyYXdpbmdtbC8yMDA2L21haW4iIHhtbG5zOnI9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9vZmZpY2VEb2N1bWVudC8yMDA2L3JlbGF0aW9uc2hpcHMiIHhtbG5zOnA9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9wcmVzZW50YXRpb25tbC8yMDA2L21haW4iPgo8cDpzbGRNYXN0ZXJJZExzdD48cDpzbGRNYXN0ZXJJZCBpZD0iMjE0NzQ4MzY0OCIgcjppZD0icklkMSIvPjwvcDpzbGRNYXN0ZXJJZExzdD4KPHA6c2xkSWRMc3Q+PHA6c2xkSWQgaWQ9IjI1NiIgcjppZD0icklkMiIvPjwvcDpzbGRJZExzdD4KPHA6c2xkU3ogY3g9IjkxNDQwMDAiIGN5PSI2ODU4MDAwIi8+CjxwOm5vdGVzU3ogY3g9IjY4NTgwMDAiIGN5PSI5MTQ0MDAwIi8+CjwvcDpwcmVzZW50YXRpb24+ClBLAwQUAAAAAAAAACEAFMCPq7wBAAC8AQAAHwAAAHBwdC9fcmVscy9wcmVzZW50YXRpb24ueG1sLnJlbHM8P3htbCB2ZXJzaW9uPSIxLjAiIGVuY29kaW5nPSJVVEYtOCIgc3RhbmRhbG9uZT0ieWVzIj8+CjxSZWxhdGlvbnNoaXBzIHhtbG5zPSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvcGFja2FnZS8yMDA2L3JlbGF0aW9uc2hpcHMiPgo8UmVsYXRpb25zaGlwIElkPSJySWQxIiBUeXBlPSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvb2ZmaWNlRG9jdW1lbnQvMjAwNi9yZWxhdGlvbnNoaXBzL3NsaWRlTWFzdGVyIiBUYXJnZXQ9InNsaWRlTWFzdGVycy9zbGlkZU1hc3RlcjEueG1sIi8+CjxSZWxhdGlvbnNoaXAgSWQ9InJJZDIiIFR5cGU9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9vZmZpY2VEb2N1bWVudC8yMDA2L3JlbGF0aW9uc2hpcHMvc2xpZGUiIFRhcmdldD0ic2xpZGVzL3NsaWRlMS54bWwiLz4KPC9SZWxhdGlvbnNoaXBzPgpQSwMEFAAAAAAAAAAhAFyz5RdbAgAAWwIAABUAAABwcHQvc2xpZGVzL3NsaWRlMS54bWw8P3htbCB2ZXJzaW9uPSIxLjAiIGVuY29kaW5nPSJVVEYtOCIgc3RhbmRhbG9uZT0ieWVzIj8+CjxwOnNsZCB4bWxuczphPSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvZHJhd2luZ21sLzIwMDYvbWFpbiIgeG1sbnM6cj0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL29mZmljZURvY3VtZW50LzIwMDYvcmVsYXRpb25zaGlwcyIgeG1sbnM6cD0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL3ByZXNlbnRhdGlvbm1sLzIwMDYvbWFpbiI+CjxwOmNTbGQ+CjxwOnNwVHJlZT4KPHA6bnZHcnBTcFByPjxwOmNOdlByIGlkPSIxIiBuYW1lPSIiLz48cDpjTnZHcnBTcFByLz48cDpudlByLz48L3A6bnZHcnBTcFByPgo8cDpncnBTcFByLz4KPHA6c3A+CjxwOm52U3BQcj48cDpjTnZQciBpZD0iMiIgbmFtZT0iVGl0bGUiLz48cDpjTnZTcFByLz48cDpudlByLz48L3A6bnZTcFByPgo8cDpzcFByLz4KPHA6dHhCb2R5PjxhOmJvZHlQci8+PGE6cD48YTpyPjxhOnQ+S0NTIG9mZmljZSBjb252ZXJ0IHRlc3Q8L2E6dD48L2E6cj48L2E6cD48L3A6dHhCb2R5Pgo8L3A6c3A+CjwvcDpzcFRyZWU+CjwvcDpjU2xkPgo8L3A6c2xkPgpQSwMEFAAAAAAAAAAhADTsLLQ5AQAAOQEAACAAAABwcHQvc2xpZGVzL19yZWxzL3NsaWRlMS54bWwucmVsczw/eG1sIHZlcnNpb249IjEuMCIgZW5jb2Rpbmc9IlVURi04IiBzdGFuZGFsb25lPSJ5ZXMiPz4KPFJlbGF0aW9uc2hpcHMgeG1sbnM9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9wYWNrYWdlLzIwMDYvcmVsYXRpb25zaGlwcyI+CjxSZWxhdGlvbnNoaXAgSWQ9InJJZDEiIFR5cGU9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9vZmZpY2VEb2N1bWVudC8yMDA2L3JlbGF0aW9uc2hpcHMvc2xpZGVMYXlvdXQiIFRhcmdldD0iLi4vc2xpZGVMYXlvdXRzL3NsaWRlTGF5b3V0MS54bWwiLz4KPC9SZWxhdGlvbnNoaXBzPgpQSwMEFAAAAAAAAAAhADYpqHbGAQAAxgEAACEAAABwcHQvc2xpZGVMYXlvdXRzL3NsaWRlTGF5b3V0MS54bWw8P3htbCB2ZXJzaW9uPSIxLjAiIGVuY29kaW5nPSJVVEYtOCIgc3RhbmRhbG9uZT0ieWVzIj8+CjxwOnNsZExheW91dCB4bWxuczphPSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvZHJhd2luZ21sLzIwMDYvbWFpbiIgeG1sbnM6cj0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL29mZmljZURvY3VtZW50LzIwMDYvcmVsYXRpb25zaGlwcyIgeG1sbnM6cD0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL3ByZXNlbnRhdGlvbm1sLzIwMDYvbWFpbiIgdHlwZT0iYmxhbmsiIHByZXNlcnZlPSIxIj4KPHA6Y1NsZD4KPHA6c3BUcmVlPgo8cDpudkdycFNwUHI+PHA6Y052UHIgaWQ9IjEiIG5hbWU9IiIvPjxwOmNOdkdycFNwUHIvPjxwOm52UHIvPjwvcDpudkdycFNwUHI+CjxwOmdycFNwUHIvPgo8L3A6c3BUcmVlPgo8L3A6Y1NsZD4KPC9wOnNsZExheW91dD4KUEsDBBQAAAAAAAAAIQAmX7qVOQEAADkBAAAsAAAAcHB0L3NsaWRlTGF5b3V0cy9fcmVscy9zbGlkZUxheW91dDEueG1sLnJlbHM8P3htbCB2ZXJzaW9uPSIxLjAiIGVuY29kaW5nPSJVVEYtOCIgc3RhbmRhbG9uZT0ieWVzIj8+CjxSZWxhdGlvbnNoaXBzIHhtbG5zPSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvcGFja2FnZS8yMDA2L3JlbGF0aW9uc2hpcHMiPgo8UmVsYXRpb25zaGlwIElkPSJySWQxIiBUeXBlPSJodHRwOi8vc2NoZW1hcy5vcGVueG1sZm9ybWF0cy5vcmcvb2ZmaWNlRG9jdW1lbnQvMjAwNi9yZWxhdGlvbnNoaXBzL3NsaWRlTWFzdGVyIiBUYXJnZXQ9Ii4uL3NsaWRlTWFzdGVycy9zbGlkZU1hc3RlcjEueG1sIi8+CjwvUmVsYXRpb25zaGlwcz4KUEsDBBQAAAAAAAAAIQBB3XZ8wAIAAMACAAAhAAAAcHB0L3NsaWRlTWFzdGVycy9zbGlkZU1hc3RlcjEueG1sPD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9InllcyI/Pgo8cDpzbGRNYXN0ZXIgeG1sbnM6YT0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL2RyYXdpbmdtbC8yMDA2L21haW4iIHhtbG5zOnI9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9vZmZpY2VEb2N1bWVudC8yMDA2L3JlbGF0aW9uc2hpcHMiIHhtbG5zOnA9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9wcmVzZW50YXRpb25tbC8yMDA2L21haW4iPgo8cDpjU2xkPgo8cDpzcFRyZWU+CjxwOm52R3JwU3BQcj48cDpjTnZQciBpZD0iMSIgbmFtZT0iIi8+PHA6Y052R3JwU3BQci8+PHA6bnZQci8+PC9wOm52R3JwU3BQcj4KPHA6Z3JwU3BQci8+CjwvcDpzcFRyZWU+CjwvcDpjU2xkPgo8cDpjbHJNYXAgYmcxPSJsdDEiIHR4MT0iZGsxIiBiZzI9Imx0MiIgdHgyPSJkazIiIGFjY2VudDE9ImFjY2VudDEiIGFjY2VudDI9ImFjY2VudDIiIGFjY2VudDM9ImFjY2VudDMiIGFjY2VudDQ9ImFjY2VudDQiIGFjY2VudDU9ImFjY2VudDUiIGFjY2VudDY9ImFjY2VudDYiIGhsaW5rPSJobGluayIgZm9sSGxpbms9ImZvbEhsaW5rIi8+CjxwOnNsZExheW91dElkTHN0PjxwOnNsZExheW91dElkIGlkPSIyMTQ3NDgzNjQ5IiByOmlkPSJySWQxIi8+PC9wOnNsZExheW91dElkTHN0Pgo8L3A6c2xkTWFzdGVyPgpQSwMEFAAAAAAAAAAhAFIh0dPBAQAAwQEAACwAAABwcHQvc2xpZGVNYXN0ZXJzL19yZWxzL3NsaWRlTWFzdGVyMS54bWwucmVsczw/eG1sIHZlcnNpb249IjEuMCIgZW5jb2Rpbmc9IlVURi04IiBzdGFuZGFsb25lPSJ5ZXMiPz4KPFJlbGF0aW9uc2hpcHMgeG1sbnM9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9wYWNrYWdlLzIwMDYvcmVsYXRpb25zaGlwcyI+CjxSZWxhdGlvbnNoaXAgSWQ9InJJZDEiIFR5cGU9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9vZmZpY2VEb2N1bWVudC8yMDA2L3JlbGF0aW9uc2hpcHMvc2xpZGVMYXlvdXQiIFRhcmdldD0iLi4vc2xpZGVMYXlvdXRzL3NsaWRlTGF5b3V0MS54bWwiLz4KPFJlbGF0aW9uc2hpcCBJZD0icklkMiIgVHlwZT0iaHR0cDovL3NjaGVtYXMub3BlbnhtbGZvcm1hdHMub3JnL29mZmljZURvY3VtZW50LzIwMDYvcmVsYXRpb25zaGlwcy90aGVtZSIgVGFyZ2V0PSIuLi90aGVtZS90aGVtZTEueG1sIi8+CjwvUmVsYXRpb25zaGlwcz4KUEsDBBQAAAAAAAAAIQANajFPDgcAAA4HAAAUAAAAcHB0L3RoZW1lL3RoZW1lMS54bWw8P3htbCB2ZXJzaW9uPSIxLjAiIGVuY29kaW5nPSJVVEYtOCIgc3RhbmRhbG9uZT0ieWVzIj8+CjxhOnRoZW1lIHhtbG5zOmE9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9kcmF3aW5nbWwvMjAwNi9tYWluIiBuYW1lPSJLQ1MiPgo8YTp0aGVtZUVsZW1lbnRzPgo8YTpjbHJTY2hlbWUgbmFtZT0iS0NTIj4KPGE6ZGsxPjxhOnN5c0NsciB2YWw9IndpbmRvd1RleHQiIGxhc3RDbHI9IjAwMDAwMCIvPjwvYTpkazE+CjxhOmx0MT48YTpzeXNDbHIgdmFsPSJ3aW5kb3ciIGxhc3RDbHI9IkZGRkZGRiIvPjwvYTpsdDE+CjxhOmRrMj48YTpzcmdiQ2xyIHZhbD0iMUY0OTdEIi8+PC9hOmRrMj4KPGE6bHQyPjxhOnNyZ2JDbHIgdmFsPSJFRUVDRTEiLz48L2E6bHQyPgo8YTphY2NlbnQxPjxhOnNyZ2JDbHIgdmFsPSI0RjgxQkQiLz48L2E6YWNjZW50MT4KPGE6YWNjZW50Mj48YTpzcmdiQ2xyIHZhbD0iQzA1MDREIi8+PC9hOmFjY2VudDI+CjxhOmFjY2VudDM+PGE6c3JnYkNsciB2YWw9IjlCQkI1OSIvPjwvYTphY2NlbnQzPgo8YTphY2NlbnQ0PjxhOnNyZ2JDbHIgdmFsPSI4MDY0QTIiLz48L2E6YWNjZW50ND4KPGE6YWNjZW50NT48YTpzcmdiQ2xyIHZhbD0iNEJBQ0M2Ii8+PC9hOmFjY2VudDU+CjxhOmFjY2VudDY+PGE6c3JnYkNsciB2YWw9IkY3OTY0NiIvPjwvYTphY2NlbnQ2Pgo8YTpobGluaz48YTpzcmdiQ2xyIHZhbD0iMDAwMEZGIi8+PC9hOmhsaW5rPgo8YTpmb2xIbGluaz48YTpzcmdiQ2xyIHZhbD0iODAwMDgwIi8+PC9hOmZvbEhsaW5rPgo8L2E6Y2xyU2NoZW1lPgo8YTpmb250U2NoZW1lIG5hbWU9IktDUyI+CjxhOm1ham9yRm9udD48YTpsYXRpbiB0eXBlZmFjZT0iQ2FsaWJyaSIvPjwvYTptYWpvckZvbnQ+CjxhOm1pbm9yRm9udD48YTpsYXRpbiB0eXBlZmFjZT0iQ2FsaWJyaSIvPjwvYTptaW5vckZvbnQ+CjwvYTpmb250U2NoZW1lPgo8YTpmbXRTY2hlbWUgbmFtZT0iS0NTIj4KPGE6ZmlsbFN0eWxlTHN0PjxhOnNvbGlkRmlsbD48YTpzY2hlbWVDbHIgdmFsPSJwaENsciIvPjwvYTpzb2xpZEZpbGw+PGE6c29saWRGaWxsPjxhOnNjaGVtZUNsciB2YWw9InBoQ2xyIi8+PC9hOnNvbGlkRmlsbD48YTpzb2xpZEZpbGw+PGE6c2NoZW1lQ2xyIHZhbD0icGhDbHIiLz48L2E6c29saWRGaWxsPjwvYTpmaWxsU3R5bGVMc3Q+CjxhOmxuU3R5bGVMc3Q+PGE6bG4+PGE6c29saWRGaWxsPjxhOnNjaGVtZUNsciB2YWw9InBoQ2xyIi8+PC9hOnNvbGlkRmlsbD48L2E6bG4+PGE6bG4+PGE6c29saWRGaWxsPjxhOnNjaGVtZUNsciB2YWw9InBoQ2xyIi8+PC9hOnNvbGlkRmlsbD48L2E6bG4+PGE6bG4+PGE6c29saWRGaWxsPjxhOnNjaGVtZUNsciB2YWw9InBoQ2xyIi8+PC9hOnNvbGlkRmlsbD48L2E6bG4+PC9hOmxuU3R5bGVMc3Q+CjxhOmVmZmVjdFN0eWxlTHN0PjxhOmVmZmVjdFN0eWxlPjxhOmVmZmVjdExzdC8+PC9hOmVmZmVjdFN0eWxlPjxhOmVmZmVjdFN0eWxlPjxhOmVmZmVjdExzdC8+PC9hOmVmZmVjdFN0eWxlPjxhOmVmZmVjdFN0eWxlPjxhOmVmZmVjdExzdC8+PC9hOmVmZmVjdFN0eWxlPjwvYTplZmZlY3RTdHlsZUxzdD4KPGE6YmdGaWxsU3R5bGVMc3Q+PGE6c29saWRGaWxsPjxhOnNjaGVtZUNsciB2YWw9InBoQ2xyIi8+PC9hOnNvbGlkRmlsbD48YTpzb2xpZEZpbGw+PGE6c2NoZW1lQ2xyIHZhbD0icGhDbHIiLz48L2E6c29saWRGaWxsPjxhOnNvbGlkRmlsbD48YTpzY2hlbWVDbHIgdmFsPSJwaENsciIvPjwvYTpzb2xpZEZpbGw+PC9hOmJnRmlsbFN0eWxlTHN0Pgo8L2E6Zm10U2NoZW1lPgo8L2E6dGhlbWVFbGVtZW50cz4KPC9hOnRoZW1lPgpQSwECFAMUAAAAAAAAACEAjMAWEdgDAADYAwAAEwAAAAAAAAAAAAAAgAEAAAAAW0NvbnRlbnRfVHlwZXNdLnhtbFBLAQIUAxQAAAAAAAAAIQAJqgfHMAEAADABAAALAAAAAAAAAAAAAACAAQkEAABfcmVscy8ucmVsc1BLAQIUAxQAAAAAAAAAIQBOiYW4BQIAAAUCAAAUAAAAAAAAAAAAAACAAWIFAABwcHQvcHJlc2VudGF0aW9uLnhtbFBLAQIUAxQAAAAAAAAAIQAUwI+rvAEAALwBAAAfAAAAAAAAAAAAAACAAZkHAABwcHQvX3JlbHMvcHJlc2VudGF0aW9uLnhtbC5yZWxzUEsBAhQDFAAAAAAAAAAhAFyz5RdbAgAAWwIAABUAAAAAAAAAAAAAAIABkgkAAHBwdC9zbGlkZXMvc2xpZGUxLnhtbFBLAQIUAxQAAAAAAAAAIQA07Cy0OQEAADkBAAAgAAAAAAAAAAAAAACAASAMAABwcHQvc2xpZGVzL19yZWxzL3NsaWRlMS54bWwucmVsc1BLAQIUAxQAAAAAAAAAIQA2Kah2xgEAAMYBAAAhAAAAAAAAAAAAAACAAZcNAABwcHQvc2xpZGVMYXlvdXRzL3NsaWRlTGF5b3V0MS54bWxQSwECFAMUAAAAAAAAACEAJl+6lTkBAAA5AQAALAAAAAAAAAAAAAAAgAGcDwAAcHB0L3NsaWRlTGF5b3V0cy9fcmVscy9zbGlkZUxheW91dDEueG1sLnJlbHNQSwECFAMUAAAAAAAAACEAQd12fMACAADAAgAAIQAAAAAAAAAAAAAAgAEfEQAAcHB0L3NsaWRlTWFzdGVycy9zbGlkZU1hc3RlcjEueG1sUEsBAhQDFAAAAAAAAAAhAFIh0dPBAQAAwQEAACwAAAAAAAAAAAAAAIABHhQAAHBwdC9zbGlkZU1hc3RlcnMvX3JlbHMvc2xpZGVNYXN0ZXIxLnhtbC5yZWxzUEsBAhQDFAAAAAAAAAAhAA1qMU8OBwAADgcAABQAAAAAAAAAAAAAAIABKRYAAHBwdC90aGVtZS90aGVtZTEueG1sUEsFBgAAAAALAAsALgMAAGkdAAAAAA==";

    /// Skips (returns early) unless a REAL renderer resolves — i.e. the seam
    /// env var is unset and a real `soffice`-compatible binary is reachable
    /// (explicit `KIO_OFFICE_CONVERTER` or `soffice` on PATH; left as
    /// whatever the ambient environment provides). On the implementing
    /// machine that real binary is `/opt/homebrew/bin/soffice` (LibreOffice
    /// 26.2.4.2).
    #[test]
    fn office_real_soffice_docx_converts_deterministically() {
        let _lock = OFFICE_ENV_LOCK.lock().unwrap();
        let _clear_seam = EnvVarGuard::remove(TEST_OFFICE_CONVERT_ENV);
        let Some(converter) = resolve_office_converter() else {
            eprintln!(
                "skipping office_real_soffice_docx_converts_deterministically: \
                 no real office converter available (install soffice on PATH \
                 or set KIO_OFFICE_CONVERTER to exercise this test)"
            );
            return;
        };
        assert_ne!(converter.version(), "test-converter");

        let docx = decode_fixture(DOCX_FIXTURE_B64);
        let first = converter
            .convert_to_pdf(&docx, DOCX_MEDIA_TYPE)
            .expect("first conversion");
        let second = converter
            .convert_to_pdf(&docx, DOCX_MEDIA_TYPE)
            .expect("second conversion");
        assert!(first.starts_with(b"%PDF"), "converted output must be a PDF");
        assert_eq!(
            first, second,
            "normalized converted-PDF bytes must be identical across \
             independent conversions of the same input"
        );

        // FlateDecode round (07 §2.1, 2026-07-23 addendum): a real soffice
        // PDF carries its text as FlateDecode-compressed CID glyph runs.
        // The graph decoder must recover the body text offline — this is
        // the acceptance property the round exists for, and it was NOT
        // covered before (only byte determinism was asserted).
        let pages = crate::deterministic::extract_pdf_text_pages_bounded(
            &first,
            crate::deterministic::MAX_DETERMINISTIC_PDF_PAGES,
        )
        .expect("extract converted-PDF text layer");
        let joined = pages.join("\n");
        assert!(
            joined.contains("office") && joined.contains("convert"),
            "converted-PDF compressed text layer must decode offline; got {joined:?}"
        );
    }

    /// Same determinism property as the DOCX test above, for PPTX. The
    /// minimal-pptx skeleton (presentation + slide + layout + master +
    /// theme) converts cleanly with the real `soffice` on the implementing
    /// machine, so this is included rather than falling back to docx-only.
    #[test]
    fn office_real_soffice_pptx_converts_deterministically() {
        let _lock = OFFICE_ENV_LOCK.lock().unwrap();
        let _clear_seam = EnvVarGuard::remove(TEST_OFFICE_CONVERT_ENV);
        let Some(converter) = resolve_office_converter() else {
            eprintln!(
                "skipping office_real_soffice_pptx_converts_deterministically: \
                 no real office converter available (install soffice on PATH \
                 or set KIO_OFFICE_CONVERTER to exercise this test)"
            );
            return;
        };

        let pptx = decode_fixture(PPTX_FIXTURE_B64);
        let first = converter
            .convert_to_pdf(&pptx, PPTX_MEDIA_TYPE)
            .expect("first conversion");
        let second = converter
            .convert_to_pdf(&pptx, PPTX_MEDIA_TYPE)
            .expect("second conversion");
        assert!(first.starts_with(b"%PDF"), "converted output must be a PDF");
        assert_eq!(
            first, second,
            "normalized converted-PDF bytes must be identical across \
             independent conversions of the same input"
        );
    }
}
