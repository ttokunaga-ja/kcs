//! Prepare stage contracts.

use std::io::Read;
use std::path::Path;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::{IoResultExt, Result};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UnitType {
    Page,
    Slide,
    HeadingSection,
    Sheet,
    Image,
    File,
    Symbol,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UnitFingerprint {
    pub perceptual_hash: String,
    pub text_hash: String,
    pub visual_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreparedUnit {
    pub order: u64,
    pub unit_key: String,
    pub unit_type: UnitType,
    pub prepared_hash: String,
    pub fingerprint: UnitFingerprint,
    pub mime: Option<String>,
    pub page_number: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareStageRequest {
    pub raw_hash: String,
    pub media_type: String,
    pub input_path: String,
    pub tool_profile_hash: String,
}

/// Prepare from a caller-verified byte buffer. `input_path` is display/provenance
/// metadata only and is never reopened by this API.
#[derive(Debug, Clone, Copy)]
pub struct PrepareStageBytesRequest<'a> {
    pub raw_hash: &'a str,
    pub media_type: &'a str,
    pub input_path: &'a str,
    pub tool_profile_hash: &'a str,
    pub bytes: &'a [u8],
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepareStageOutput {
    pub prepared_object_hashes: Vec<String>,
    pub prepared_units: Vec<PreparedUnit>,
    pub image_object_hashes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UnitMapping {
    pub unchanged: Vec<UnitReuse>,
    pub changed_unit_keys: Vec<String>,
    pub added_unit_keys: Vec<String>,
    pub removed_unit_keys: Vec<String>,
    pub change_rate: f64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UnitReuse {
    pub old_unit_key: String,
    pub new_unit_key: String,
    pub confidence: String,
    pub reason: String,
}

/// Maximum number of dynamic-programming cells used for exact unit alignment.
/// At 8 bytes per `usize`, this caps cell storage at about 16 MiB before row
/// overhead. Larger comparisons take the deterministic full-change fallback.
pub const MAX_UNIT_LCS_CELLS: usize = 2_000_000;

pub fn prepare_units(request: PrepareStageRequest) -> Result<PrepareStageOutput> {
    // R20-6: the local deterministic adapter only parses text (Markdown / plain text /
    // code) and PDF text layers (docs/07 §7.1). A RECOGNIZED non-text-native binary (image
    // / OOXML office document) is never locally parseable — a raw-bytes "passthrough" unit
    // evidences its bytes (a ZIP's PK header, an image's pixels) as searchable garbage.
    // Route it to online OCR (empty prepared_units → the R20-5 path). `octet-stream`
    // (unrecognized extension) is content-sniffed below: it may be a TEXT file with an
    // unknown extension (`.env`, `.cfg`) — still passthrough'd locally — or a binary blob.
    let media_type = request.media_type.as_str();
    let is_text_native = matches!(media_type, "text/markdown" | "text/plain" | "text/x-code");
    let is_pdf = media_type == "application/pdf";
    if !is_text_native && !is_pdf && media_type != "application/octet-stream" {
        return Ok(empty_prepare_output());
    }
    let bytes = std::fs::read(&request.input_path).pipeline_io(Path::new(&request.input_path))?;
    prepare_units_from_bytes(PrepareStageBytesRequest {
        raw_hash: &request.raw_hash,
        media_type: &request.media_type,
        input_path: &request.input_path,
        tool_profile_hash: &request.tool_profile_hash,
        bytes: &bytes,
    })
}

/// Prepare logical units from exactly the byte buffer whose identity the caller
/// supplied. This closes path-reopen races between raw hashing and preparation.
pub fn prepare_units_from_bytes(
    request: PrepareStageBytesRequest<'_>,
) -> Result<PrepareStageOutput> {
    let media_type = request.media_type;
    let is_text_native = matches!(media_type, "text/markdown" | "text/plain" | "text/x-code");
    let is_pdf = media_type == "application/pdf";
    if !is_text_native && !is_pdf && media_type != "application/octet-stream" {
        return Ok(empty_prepare_output());
    }
    let bytes = request.bytes;
    let prepared_hash = hash_bytes(bytes);
    if prepared_hash != request.raw_hash {
        return Err(crate::PipelineError::contract(
            "KCS-E-PREPARE-IDENTITY-001",
            format!(
                "prepare bytes do not match the declared raw hash for {}",
                request.input_path
            ),
        ));
    }
    if !is_text_native && !is_pdf && !bytes_are_text(bytes) {
        // Binary octet-stream (a DOCX-as-unknown-ext, a compiled blob): do NOT evidence its
        // raw bytes as text — route to OCR like the other non-text-native media above.
        return Ok(empty_prepare_output());
    }
    let unit_type = unit_type_for_media_type(request.media_type);
    let pdf_pages = if request.media_type == "application/pdf" {
        let pages = pdf_text_pages_bounded(bytes)?;
        // R20-4: `pdf_has_text_layer` and the stream/literal extractors match on raw
        // (undecompressed) bytes, so a scanned PDF's compressed image streams yield garbage
        // "text" (a chance `BT` plus random `(...)` literals). If every recovered page is
        // empty or mostly non-printable, there is no real text layer — treat it as scanned
        // and route to OCR rather than persisting the garbage as a searchable unit. (An
        // empty `pages` — the honest no-text-layer result — also lands here vacuously.)
        if pages.iter().all(|page| !is_probably_real_text(page)) {
            return Ok(empty_prepare_output());
        }
        // R21-5: for a MIXED PDF (a real text page + a scanned image page) the per-page
        // suppression of a scanned page's garbage is applied in the deterministic
        // markdownize adapter (`read_pdf_page_text`), which is what actually produces the
        // page markdown / chunk text — `prepare_units` only builds the unit skeleton.
        pages
    } else {
        Vec::new()
    };
    let unit_count = if unit_type == UnitType::Page {
        pdf_pages.len().max(1)
    } else {
        1
    };
    let mut prepared_units = Vec::new();
    for index in 0..unit_count {
        let selector = match unit_type {
            UnitType::Page | UnitType::Slide => (index + 1).to_string(),
            UnitType::Sheet => "Sheet1".to_owned(),
            UnitType::Image => index.to_string(),
            UnitType::File | UnitType::HeadingSection | UnitType::Symbol => "1".to_owned(),
        };
        let unit_key = canonical_unit_key(unit_type, &selector);
        let page_bytes = pdf_pages
            .get(index)
            .map(|page| page.as_bytes())
            .unwrap_or(bytes);
        let unit_prepared_hash = if unit_type == UnitType::Page {
            hash_bytes(page_bytes)
        } else if unit_count == 1 {
            prepared_hash.clone()
        } else {
            hash_bytes(format!("{prepared_hash}\0{unit_key}").as_bytes())
        };
        let fingerprint = if unit_type == UnitType::Page {
            fingerprint_for_bytes(page_bytes, page_bytes)
        } else {
            fingerprint_for_bytes(bytes, unit_prepared_hash.as_bytes())
        };
        prepared_units.push(PreparedUnit {
            order: index as u64,
            unit_key,
            unit_type,
            prepared_hash: unit_prepared_hash,
            fingerprint,
            mime: Some(request.media_type.to_owned()),
            page_number: (unit_type == UnitType::Page).then_some(index as u64 + 1),
        });
    }
    Ok(PrepareStageOutput {
        prepared_object_hashes: prepared_units
            .iter()
            .map(|unit| unit.prepared_hash.clone())
            .collect(),
        prepared_units,
        image_object_hashes: Vec::new(),
    })
}

fn empty_prepare_output() -> PrepareStageOutput {
    PrepareStageOutput {
        prepared_object_hashes: Vec::new(),
        prepared_units: Vec::new(),
        image_object_hashes: Vec::new(),
    }
}

#[must_use]
pub fn unit_ref(unit_key: &str) -> String {
    let digest = Sha256::digest(unit_key.as_bytes());
    lower_hex(&digest)[..16].to_owned()
}

#[must_use]
pub fn canonical_unit_key(unit_type: UnitType, selector: &str) -> String {
    match unit_type {
        UnitType::Page => format!("page:{}", selector.trim_start_matches('0').max("1")),
        UnitType::Slide => format!("slide:{}", selector.trim_start_matches('0').max("1")),
        UnitType::Sheet => format!("sheet:{selector}"),
        UnitType::Image => format!("image:{selector}"),
        UnitType::File | UnitType::HeadingSection | UnitType::Symbol => "doc:1".to_owned(),
    }
}

#[must_use]
pub fn fingerprint_for_bytes(text_layer_bytes: &[u8], prepared_bytes: &[u8]) -> UnitFingerprint {
    let text_hash = hash_bytes(text_layer_bytes);
    let perceptual_hash = hash_bytes(prepared_bytes);
    UnitFingerprint {
        perceptual_hash: perceptual_hash.clone(),
        text_hash,
        visual_hash: perceptual_hash,
    }
}

#[must_use]
pub fn change_rate(changed: usize, added: usize, removed: usize, new_unit_count: usize) -> f64 {
    (changed + added + removed) as f64 / std::cmp::max(new_unit_count, 1) as f64
}

#[must_use]
pub fn map_units(old_units: &[PreparedUnit], new_units: &[PreparedUnit]) -> UnitMapping {
    if !unit_mapping_within_budget(old_units.len(), new_units.len()) {
        return full_changed_mapping(old_units, new_units);
    }
    let pairs = lcs_fingerprint_pairs(old_units, new_units);
    let mut unchanged = Vec::new();
    let mut changed_unit_keys = Vec::new();
    let mut added_unit_keys = Vec::new();
    let mut removed_unit_keys = Vec::new();
    let mut old_cursor = 0;
    let mut new_cursor = 0;

    for (old_anchor, new_anchor) in pairs
        .iter()
        .copied()
        .chain(std::iter::once((old_units.len(), new_units.len())))
    {
        align_changed_interval(
            &old_units[old_cursor..old_anchor],
            &new_units[new_cursor..new_anchor],
            &mut changed_unit_keys,
            &mut added_unit_keys,
            &mut removed_unit_keys,
        );
        if old_anchor < old_units.len() && new_anchor < new_units.len() {
            unchanged.push(UnitReuse {
                old_unit_key: old_units[old_anchor].unit_key.clone(),
                new_unit_key: new_units[new_anchor].unit_key.clone(),
                confidence: "1.0".to_owned(),
                reason: "fingerprint_exact".to_owned(),
            });
        }
        old_cursor = old_anchor.saturating_add(1);
        new_cursor = new_anchor.saturating_add(1);
    }

    UnitMapping {
        change_rate: change_rate(
            changed_unit_keys.len(),
            added_unit_keys.len(),
            removed_unit_keys.len(),
            new_units.len(),
        ),
        unchanged,
        changed_unit_keys,
        added_unit_keys,
        removed_unit_keys,
    }
}

#[must_use]
pub fn unit_mapping_within_budget(old_len: usize, new_len: usize) -> bool {
    old_len
        .checked_add(1)
        .and_then(|old| new_len.checked_add(1).and_then(|new| old.checked_mul(new)))
        .is_some_and(|cells| cells <= MAX_UNIT_LCS_CELLS)
}

fn full_changed_mapping(old_units: &[PreparedUnit], new_units: &[PreparedUnit]) -> UnitMapping {
    let mut changed_unit_keys = Vec::new();
    let mut added_unit_keys = Vec::new();
    let mut removed_unit_keys = Vec::new();
    align_changed_interval(
        old_units,
        new_units,
        &mut changed_unit_keys,
        &mut added_unit_keys,
        &mut removed_unit_keys,
    );
    UnitMapping {
        change_rate: change_rate(
            changed_unit_keys.len(),
            added_unit_keys.len(),
            removed_unit_keys.len(),
            new_units.len(),
        ),
        unchanged: Vec::new(),
        changed_unit_keys,
        added_unit_keys,
        removed_unit_keys,
    }
}

#[must_use]
pub fn hash_bytes(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    format!("sha256:{}", lower_hex(&digest))
}

/// Compute the same content hash as [`hash_bytes`] with fixed working memory.
pub fn hash_reader<R: Read>(mut reader: R) -> std::io::Result<String> {
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = reader.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(format!("sha256:{}", lower_hex(&digest.finalize())))
}

fn unit_type_for_media_type(media_type: &str) -> UnitType {
    match media_type {
        "application/pdf" => UnitType::Page,
        "image/png" | "image/jpeg" | "image/webp" | "image/gif" => UnitType::Image,
        "application/vnd.ms-excel"
        | "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" => UnitType::Sheet,
        "application/vnd.ms-powerpoint"
        | "application/vnd.openxmlformats-officedocument.presentationml.presentation" => {
            UnitType::Slide
        }
        _ => UnitType::File,
    }
}

fn pdf_has_text_layer(bytes: &[u8]) -> bool {
    !bytes.starts_with(b"%PDF") || bytes.windows(2).any(|window| window == b"BT")
}

/// R20-4: heuristic for whether extracted PDF text is REAL text vs binary garbage
/// lossy-decoded from a scanned PDF's compressed streams. Real text is overwhelmingly
/// printable; garbage is dense with U+FFFD replacement characters and control bytes.
/// Requires a strong printable majority (non-control-or-whitespace, non-replacement) over
/// a non-empty length. Legitimate text extracted from real `(text)` literals passes; the
/// random-`(...)` / whole-binary fallback of a scanned page does not.
fn is_probably_real_text(text: &str) -> bool {
    let trimmed = text.trim();
    let total = trimmed.chars().count();
    if total == 0 {
        return false;
    }
    let printable = trimmed
        .chars()
        .filter(|ch| *ch != '\u{fffd}' && (!ch.is_control() || ch.is_whitespace()))
        .count();
    printable * 100 >= total * 85
}

/// R20-6: whether an `application/octet-stream` (unrecognized-extension) file is TEXT that
/// the local adapter should passthrough (a `.env` / `.cfg` / extensionless text file),
/// versus a binary blob (a DOCX ZIP, a compiled artifact) that must route to OCR rather
/// than have its raw bytes evidenced as searchable text. Text decodes as UTF-8, has no NUL
/// byte, and is overwhelmingly printable.
fn bytes_are_text(bytes: &[u8]) -> bool {
    if bytes.contains(&0) {
        return false;
    }
    match std::str::from_utf8(bytes) {
        Ok(text) => is_probably_real_text(text),
        Err(_) => false,
    }
}

#[must_use]
pub fn pdf_text_pages(bytes: &[u8]) -> Vec<String> {
    // Compatibility for callers that cannot surface a prepare error. The primary
    // prepare path uses the fallible API below and reports an oversized PDF.
    pdf_text_pages_bounded(bytes).unwrap_or_default()
}

pub fn pdf_text_pages_bounded(bytes: &[u8]) -> Result<Vec<String>> {
    if !bytes.starts_with(b"%PDF") {
        return Ok(vec![String::from_utf8_lossy(bytes).into_owned()]);
    }
    if !pdf_has_text_layer(bytes) {
        return Ok(Vec::new());
    }
    kcs_adapter::deterministic::extract_pdf_text_pages_bounded(
        bytes,
        kcs_adapter::deterministic::MAX_DETERMINISTIC_PDF_PAGES,
    )
    .map_err(|err| crate::PipelineError::contract("KCS-E-PREPARE-PDF-LIMIT-001", err.to_string()))
}

fn align_changed_interval(
    old_units: &[PreparedUnit],
    new_units: &[PreparedUnit],
    changed_unit_keys: &mut Vec<String>,
    added_unit_keys: &mut Vec<String>,
    removed_unit_keys: &mut Vec<String>,
) {
    let paired = std::cmp::min(old_units.len(), new_units.len());
    for unit in &new_units[..paired] {
        changed_unit_keys.push(unit.unit_key.clone());
    }
    for unit in &new_units[paired..] {
        added_unit_keys.push(unit.unit_key.clone());
    }
    for unit in &old_units[paired..] {
        removed_unit_keys.push(unit.unit_key.clone());
    }
}

fn lcs_fingerprint_pairs(
    old_units: &[PreparedUnit],
    new_units: &[PreparedUnit],
) -> Vec<(usize, usize)> {
    let m = old_units.len();
    let n = new_units.len();
    let mut dp = vec![vec![0usize; n + 1]; m + 1];
    for i in (0..m).rev() {
        for j in (0..n).rev() {
            dp[i][j] = if old_units[i].fingerprint == new_units[j].fingerprint {
                1 + dp[i + 1][j + 1]
            } else {
                dp[i + 1][j].max(dp[i][j + 1])
            };
        }
    }
    let mut pairs = Vec::new();
    let (mut i, mut j) = (0, 0);
    while i < m && j < n {
        if old_units[i].fingerprint == new_units[j].fingerprint {
            pairs.push((i, j));
            i += 1;
            j += 1;
        } else if dp[i + 1][j] >= dp[i][j + 1] {
            i += 1;
        } else {
            j += 1;
        }
    }
    pairs
}

fn lower_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn prepared_page(order: u64, key: &str, fp: &str) -> PreparedUnit {
        PreparedUnit {
            order,
            unit_key: key.to_owned(),
            unit_type: UnitType::Page,
            prepared_hash: format!("sha256:{fp:0<64}"),
            fingerprint: UnitFingerprint {
                perceptual_hash: fp.to_owned(),
                text_hash: fp.to_owned(),
                visual_hash: fp.to_owned(),
            },
            mime: None,
            page_number: Some(order + 1),
        }
    }

    #[test]
    fn placeholder_unit_type_uses_snake_case() {
        let value = serde_json::to_value(UnitType::HeadingSection).expect("serialize unit type");
        assert_eq!(value, "heading_section");
    }

    #[test]
    fn unit_ref_vectors_match_step2a() {
        assert_eq!(unit_ref("page:12"), "3c2fa650872d5484");
        assert_eq!(unit_ref("page:1"), "00f081779b832543");
        assert_eq!(unit_ref("page:57"), "d2255263b6d52dc8");
        assert_eq!(unit_ref("slide:3"), "22814b0d608d29b9");
        assert_eq!(unit_ref("sheet:Sheet1"), "fae07767a7986381");
        assert_eq!(unit_ref("image:0"), "beadc43287ae0d1a");
    }

    #[test]
    fn change_rate_vectors_match_step2a() {
        assert!((change_rate(0, 1, 0, 11) - 1.0 / 11.0).abs() < f64::EPSILON);
        assert_eq!(change_rate(4, 0, 0, 10), 0.4);
        assert_eq!(change_rate(0, 0, 2, 8), 0.25);
        assert_eq!(change_rate(0, 0, 3, 0), 3.0);
    }

    #[test]
    fn mapping_uses_fingerprint_lcs_for_insertions() {
        let old = (0..10)
            .map(|i| prepared_page(i, &format!("page:{}", i + 1), &format!("fp{i}")))
            .collect::<Vec<_>>();
        let mut new = vec![prepared_page(0, "page:1", "inserted")];
        new.extend(
            (0..10).map(|i| prepared_page(i + 1, &format!("page:{}", i + 2), &format!("fp{i}"))),
        );
        let mapping = map_units(&old, &new);
        assert_eq!(mapping.unchanged.len(), 10);
        assert_eq!(mapping.added_unit_keys, vec!["page:1"]);
        assert!(mapping.changed_unit_keys.is_empty());
        assert!(mapping.removed_unit_keys.is_empty());
    }

    #[test]
    fn r23_cand_007_lcs_budget_uses_checked_cell_count() {
        assert!(unit_mapping_within_budget(999, 1_999));
        assert!(!unit_mapping_within_budget(1_000, 1_999));
        assert!(!unit_mapping_within_budget(usize::MAX, 1));
        assert!(!unit_mapping_within_budget(1, usize::MAX));
    }

    #[test]
    fn r23_cand_007_over_budget_mapping_falls_back_to_full_change() {
        let count = 1_414_u64;
        let old = (0..count)
            .map(|i| prepared_page(i, &format!("page:{}", i + 1), &format!("old-{i}")))
            .collect::<Vec<_>>();
        let new = (0..count)
            .map(|i| prepared_page(i, &format!("page:{}", i + 1), &format!("new-{i}")))
            .collect::<Vec<_>>();
        assert!(!unit_mapping_within_budget(old.len(), new.len()));

        let mapping = map_units(&old, &new);
        assert!(mapping.unchanged.is_empty());
        assert_eq!(mapping.changed_unit_keys.len(), count as usize);
        assert!(mapping.added_unit_keys.is_empty());
        assert!(mapping.removed_unit_keys.is_empty());
        assert_eq!(mapping.change_rate, 1.0);
    }

    #[test]
    fn r23_cand_031_prepare_from_verified_bytes_binds_raw_hash() {
        let bytes = b"# trusted\n";
        let raw_hash = hash_bytes(bytes);
        let prepared = prepare_units_from_bytes(PrepareStageBytesRequest {
            raw_hash: &raw_hash,
            media_type: "text/markdown",
            input_path: "trusted.md",
            tool_profile_hash: "sha256:test",
            bytes,
        })
        .unwrap();
        assert_eq!(prepared.prepared_units.len(), 1);
        assert_eq!(prepared.prepared_units[0].prepared_hash, raw_hash);

        let error = prepare_units_from_bytes(PrepareStageBytesRequest {
            raw_hash: &hash_bytes(b"different"),
            media_type: "text/markdown",
            input_path: "trusted.md",
            tool_profile_hash: "sha256:test",
            bytes,
        })
        .unwrap_err();
        assert!(error.to_string().contains("KCS-E-PREPARE-IDENTITY-001"));
    }

    #[test]
    fn r23_cand_006_prepare_rejects_pdf_page_count_over_limit() {
        let mut pdf = b"%PDF-1.4\nBT\n".to_vec();
        for id in 1..=kcs_adapter::deterministic::MAX_DETERMINISTIC_PDF_PAGES + 1 {
            pdf.extend_from_slice(format!("{id} 0 obj << /Type /Page >> endobj\n").as_bytes());
        }
        let raw_hash = hash_bytes(&pdf);
        let error = prepare_units_from_bytes(PrepareStageBytesRequest {
            raw_hash: &raw_hash,
            media_type: "application/pdf",
            input_path: "oversized.pdf",
            tool_profile_hash: "sha256:test",
            bytes: &pdf,
        })
        .unwrap_err();
        assert!(error.to_string().contains("KCS-E-PREPARE-PDF-LIMIT-001"));
    }

    #[test]
    fn r23_cand_031_path_wrapper_rejects_bytes_different_from_declared_hash() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("mutable.md");
        std::fs::write(&path, b"version-b").unwrap();

        let error = prepare_units(PrepareStageRequest {
            raw_hash: hash_bytes(b"version-a"),
            media_type: "text/markdown".to_owned(),
            input_path: path.display().to_string(),
            tool_profile_hash: "sha256:test".to_owned(),
        })
        .unwrap_err();
        assert!(error.to_string().contains("KCS-E-PREPARE-IDENTITY-001"));
    }

    #[test]
    fn r23_cand_032_stream_hash_matches_in_memory_hash() {
        let bytes = vec![0xa5; 256 * 1024 + 17];
        let streamed = hash_reader(std::io::Cursor::new(&bytes)).unwrap();
        assert_eq!(streamed, hash_bytes(&bytes));
    }
}
