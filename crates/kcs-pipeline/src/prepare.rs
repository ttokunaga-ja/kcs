//! Prepare stage contracts.

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
        return Ok(PrepareStageOutput {
            prepared_object_hashes: Vec::new(),
            prepared_units: Vec::new(),
            image_object_hashes: Vec::new(),
        });
    }
    let bytes = std::fs::read(&request.input_path).pipeline_io(Path::new(&request.input_path))?;
    if !is_text_native && !is_pdf && !bytes_are_text(&bytes) {
        // Binary octet-stream (a DOCX-as-unknown-ext, a compiled blob): do NOT evidence its
        // raw bytes as text — route to OCR like the other non-text-native media above.
        return Ok(PrepareStageOutput {
            prepared_object_hashes: Vec::new(),
            prepared_units: Vec::new(),
            image_object_hashes: Vec::new(),
        });
    }
    let prepared_hash = hash_bytes(&bytes);
    let unit_type = unit_type_for_media_type(&request.media_type);
    let pdf_pages = if request.media_type == "application/pdf" {
        let pages = pdf_text_pages(&bytes);
        // R20-4: `pdf_has_text_layer` and the stream/literal extractors match on raw
        // (undecompressed) bytes, so a scanned PDF's compressed image streams yield garbage
        // "text" (a chance `BT` plus random `(...)` literals). If every recovered page is
        // empty or mostly non-printable, there is no real text layer — treat it as scanned
        // and route to OCR rather than persisting the garbage as a searchable unit. (An
        // empty `pages` — the honest no-text-layer result — also lands here vacuously.)
        if pages.iter().all(|page| !is_probably_real_text(page)) {
            return Ok(PrepareStageOutput {
                prepared_object_hashes: Vec::new(),
                prepared_units: Vec::new(),
                image_object_hashes: Vec::new(),
            });
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
            .unwrap_or(bytes.as_slice());
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
            fingerprint_for_bytes(&bytes, unit_prepared_hash.as_bytes())
        };
        prepared_units.push(PreparedUnit {
            order: index as u64,
            unit_key,
            unit_type,
            prepared_hash: unit_prepared_hash,
            fingerprint,
            mime: Some(request.media_type.clone()),
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
pub fn hash_bytes(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    format!("sha256:{}", lower_hex(&digest))
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
    if !bytes.starts_with(b"%PDF") {
        return vec![String::from_utf8_lossy(bytes).into_owned()];
    }
    if !pdf_has_text_layer(bytes) {
        return Vec::new();
    }
    let page_count =
        kcs_adapter::deterministic::pdf_page_count_in_text(&String::from_utf8_lossy(bytes)).max(1);
    let stream_pages = kcs_adapter::deterministic::pdf_stream_text_pages(bytes);
    if !stream_pages.is_empty() {
        return normalize_pdf_page_count(stream_pages, page_count);
    }
    let strings = pdf_literal_strings(bytes);
    if strings.is_empty() {
        return vec![pdf_text_fallback(bytes)];
    }
    if strings.len() == page_count {
        return strings;
    }
    let mut pages = strings;
    while pages.len() < page_count {
        pages.push(String::new());
    }
    pages.truncate(page_count);
    pages
}

fn normalize_pdf_page_count(mut pages: Vec<String>, page_count: usize) -> Vec<String> {
    while pages.len() < page_count {
        pages.push(String::new());
    }
    pages.truncate(page_count);
    pages
}

// The PDF stream/literal-string extraction helpers live in `kcs-adapter`
// (`kcs_adapter::deterministic`), the lower crate that this crate already
// depends on. They were previously duplicated here; unifying on the adapter
// copy keeps the endstream-boundary logic in one place (Step2c I3).
fn pdf_literal_strings(bytes: &[u8]) -> Vec<String> {
    let text = String::from_utf8_lossy(bytes);
    kcs_adapter::deterministic::pdf_literal_strings_in_text(&text)
}

fn pdf_text_fallback(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes)
        .lines()
        .filter(|line| !line.trim_start().starts_with('%'))
        .collect::<Vec<_>>()
        .join("\n")
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
        let mk = |order, key: &str, fp: &str| PreparedUnit {
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
        };
        let old = (0..10)
            .map(|i| mk(i, &format!("page:{}", i + 1), &format!("fp{i}")))
            .collect::<Vec<_>>();
        let mut new = vec![mk(0, "page:1", "inserted")];
        new.extend((0..10).map(|i| mk(i + 1, &format!("page:{}", i + 2), &format!("fp{i}"))));
        let mapping = map_units(&old, &new);
        assert_eq!(mapping.unchanged.len(), 10);
        assert_eq!(mapping.added_unit_keys, vec!["page:1"]);
        assert!(mapping.changed_unit_keys.is_empty());
        assert!(mapping.removed_unit_keys.is_empty());
    }
}
