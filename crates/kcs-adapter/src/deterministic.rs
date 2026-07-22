//! Built-in deterministic adapter skeleton.

use crate::traits::{MarkdownizeAdapter, PrepareAdapter};
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownUnit, MarkdownizeMode, MarkdownizeRequest,
    MarkdownizeResponse, PrepareRequest, PrepareResponse, PreparedUnitHint, PreparedUnitMetadata,
    UnitFingerprint, UnitKind,
};
use crate::{AdapterError, Result};
use serde_json::json;
use unicode_normalization::UnicodeNormalization;

pub const MAX_DETERMINISTIC_PDF_PAGES: usize = 256;

#[derive(Debug, Clone, Default)]
pub struct DeterministicAdapter;

impl DeterministicAdapter {
    fn profile_for(adapter_kind: AdapterKind) -> AdapterProfile {
        let (profile_input, capability_flags) = match adapter_kind {
            AdapterKind::Prepare => (deterministic_prepare_profile_value(), Vec::new()),
            AdapterKind::Markdownize => (
                deterministic_markdown_profile_value(),
                vec!["baseline".to_owned(), "text_passthrough".to_owned()],
            ),
            _ => (
                json!({
                    "adapter_kind": "markdownize",
                    "adapter_role": "text",
                    "model_or_tool_family": "kcs-deterministic-text",
                    "model_version_pin": "1.0.0",
                    "output_schema": "kcs-markdown-v1",
                    "runtime_kind": "local",
                    "spec_version": 1
                }),
                Vec::new(),
            ),
        };
        let tool_profile_hash = crate::identity::tool_profile_hash(&profile_input)
            .expect("built-in deterministic profile is valid");
        AdapterProfile {
            adapter_kind,
            adapter_id: "deterministic_builtin".to_owned(),
            execution_mode: ExecutionMode::DeterministicLibrary,
            tool_profile_hash,
            version: env!("CARGO_PKG_VERSION").to_owned(),
            capability_flags,
            allow_network: false,
            // The built-in deterministic adapter never bills (local, no
            // network) — QA18's `billable_kinds`/`reject_billing` are only
            // REQUIRED for a billable adapter (07 §5.7 condition 6). Per the
            // QA18 ruling, a non-billable adapter still states its billing
            // posture explicitly (`Nonbillable`) rather than leaving
            // `reject_billing` at `None` — `None` is reserved for a legacy
            // profile predating this field, which a consumer must fail-closed
            // interpret as "billable" (07 §4: "legacy/未知値は fail-closed =
            // billable として扱う"). This adapter is not legacy; it declares.
            billable_kinds: Vec::new(),
            reject_billing: Some(crate::types::BillingDeclaration::Nonbillable),
        }
    }
}

pub fn deterministic_markdown_profile_value() -> serde_json::Value {
    json!({
        "adapter_kind": "markdownize",
        "adapter_role": "text",
        "model_or_tool_family": "kcs-deterministic-text",
        "model_version_pin": "1.0.0",
        "output_schema": "kcs-markdown-v1",
        "runtime_kind": "local",
        "spec_version": 1
    })
}

pub fn deterministic_prepare_profile_value() -> serde_json::Value {
    json!({
        "adapter_kind": "prepare",
        "adapter_role": "text",
        "model_or_tool_family": "kcs-deterministic-prepare",
        "model_version_pin": "1.0.0",
        "runtime_kind": "local",
        "spec_version": 1
    })
}

impl PrepareAdapter for DeterministicAdapter {
    fn profile(&self) -> AdapterProfile {
        Self::profile_for(AdapterKind::Prepare)
    }

    fn prepare(&self, request: PrepareRequest) -> Result<PrepareResponse> {
        let unit_kind = unit_kind_for_media_type(&request.media_type);
        let unit_key = match unit_kind {
            UnitKind::Page => "page:1",
            UnitKind::Image => "image:0",
            UnitKind::Sheet => "sheet:Sheet1",
            UnitKind::Slide => "slide:1",
            UnitKind::File | UnitKind::HeadingSection | UnitKind::Symbol => "doc:1",
        }
        .to_owned();
        let fingerprint = UnitFingerprint {
            perceptual_hash: request.raw_hash.clone(),
            text_hash: request.raw_hash.clone(),
            visual_hash: request.raw_hash.clone(),
        };
        Ok(PrepareResponse {
            prepared_object_hashes: vec![request.raw_hash.clone()],
            prepared_unit_hashes: vec![request.raw_hash.clone()],
            image_object_hashes: Vec::new(),
            metadata: vec![PreparedUnitMetadata {
                unit_key,
                unit_kind,
                page_number: matches!(unit_kind, UnitKind::Page).then_some(1),
                mime: Some(request.media_type),
                fingerprint,
            }],
        })
    }
}

impl MarkdownizeAdapter for DeterministicAdapter {
    fn profile(&self) -> AdapterProfile {
        Self::profile_for(AdapterKind::Markdownize)
    }

    fn markdownize(&self, request: MarkdownizeRequest) -> Result<MarkdownizeResponse> {
        let source = match request.raw.path.as_deref() {
            Some(path) => {
                let bytes = std::fs::read(path).map_err(|err| AdapterError::Io {
                    path: path.to_owned(),
                    message: err.to_string(),
                })?;
                Some(source_document_from_verified_bytes(&request, &bytes)?)
            }
            None => None,
        };
        markdownize_with_source(request, source.as_ref())
    }
}

/// Markdownize caller-owned bytes without reopening a pathname. This is the
/// deterministic counterpart to the online verified-bytes API.
pub fn markdownize_from_bytes(
    request: MarkdownizeRequest,
    verified_raw_bytes: &[u8],
) -> Result<MarkdownizeResponse> {
    let source = source_document_from_verified_bytes(&request, verified_raw_bytes)?;
    markdownize_with_source(request, Some(&source))
}

#[derive(Debug, Clone)]
enum SourceDocument {
    Text(String),
    PdfPages(Vec<String>),
}

fn source_document_from_verified_bytes(
    request: &MarkdownizeRequest,
    bytes: &[u8],
) -> Result<SourceDocument> {
    let actual_hash = crate::identity::hash_bytes(bytes);
    if actual_hash != request.raw.raw_hash {
        return Err(AdapterError::ContractViolation(format!(
            "deterministic input identity changed: expected {}, got {actual_hash}",
            request.raw.raw_hash
        )));
    }
    if request.media_type == "application/pdf" {
        return extract_pdf_text_pages_bounded(bytes, MAX_DETERMINISTIC_PDF_PAGES)
            .map(SourceDocument::PdfPages);
    }
    let text = String::from_utf8_lossy(bytes).into_owned();
    let text = text
        .strip_prefix('\u{feff}')
        .map(str::to_owned)
        .unwrap_or(text);
    Ok(SourceDocument::Text(text))
}

fn markdownize_with_source(
    request: MarkdownizeRequest,
    source: Option<&SourceDocument>,
) -> Result<MarkdownizeResponse> {
    let hints = request
        .prepared_unit_hint
        .clone()
        .unwrap_or_else(|| vec![default_hint(&request.raw.raw_hash)]);
    if request.mode == MarkdownizeMode::Incremental {
        let incremental = request.hints.clone();
        let changed = incremental
            .as_ref()
            .map(|hints| hints.changed_unit_keys.as_slice())
            .unwrap_or(&[]);
        let added = incremental
            .as_ref()
            .map(|hints| hints.added_unit_keys.as_slice())
            .unwrap_or(&[]);
        return Ok(MarkdownizeResponse {
            mode_used: MarkdownizeMode::Incremental,
            updated_units: hints
                .iter()
                .filter(|hint| changed.contains(&hint.unit_key))
                .map(|hint| markdown_unit_from_hint(hint, &request, source))
                .collect(),
            unchanged_unit_keys: Vec::new(),
            added_units: hints
                .iter()
                .filter(|hint| added.contains(&hint.unit_key))
                .map(|hint| markdown_unit_from_hint(hint, &request, source))
                .collect(),
            removed_unit_keys: incremental
                .map(|hints| hints.removed_unit_keys)
                .unwrap_or_default(),
            failed_units: Vec::new(),
            fallback_to_full: false,
            reason: None,
            // QA17: the deterministic adapter never bills (local, no
            // network) — it settles via `record_free_local_charge`'s
            // `nonbillable_charge()`, not this codepath's `usage` field.
            usage: None,
        });
    }

    Ok(MarkdownizeResponse {
        mode_used: MarkdownizeMode::Full,
        updated_units: hints
            .iter()
            .map(|hint| markdown_unit_from_hint(hint, &request, source))
            .collect(),
        unchanged_unit_keys: Vec::new(),
        added_units: Vec::new(),
        removed_unit_keys: Vec::new(),
        failed_units: Vec::new(),
        fallback_to_full: false,
        reason: None,
        // QA17: see the Incremental branch above — this adapter never bills.
        usage: None,
    })
}

fn unit_kind_for_media_type(media_type: &str) -> UnitKind {
    match media_type {
        "application/pdf" => UnitKind::Page,
        "image/png" | "image/jpeg" | "image/webp" | "image/gif" => UnitKind::Image,
        "application/vnd.ms-excel"
        | "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" => UnitKind::Sheet,
        "application/vnd.ms-powerpoint"
        | "application/vnd.openxmlformats-officedocument.presentationml.presentation" => {
            UnitKind::Slide
        }
        _ => UnitKind::File,
    }
}

fn default_hint(raw_hash: &str) -> PreparedUnitHint {
    PreparedUnitHint {
        unit_key: "doc:1".to_owned(),
        prepared_hash: raw_hash.to_owned(),
        unit_kind: UnitKind::File,
        order: 0,
    }
}

/// QA41/QA42 (step4b-contract-tests-p3a.md §L): the sentinel used when there is
/// nothing to extract for a unit (no source, or extracted text is empty/not
/// real text). Deliberately plain text, not an HTML comment — an HTML
/// comment is a raw-HTML block under Normalized Markdown v1 (07 §5.2.1) and
/// would be rejected by the same v1 structural check this baseline must
/// satisfy (04 §3.2 V5).
fn baseline_placeholder(unit_key: &str, prepared_hash: &str) -> String {
    format!("KCS deterministic baseline: {unit_key} {prepared_hash}\n")
}

fn markdown_unit_from_hint(
    hint: &PreparedUnitHint,
    request: &MarkdownizeRequest,
    source: Option<&SourceDocument>,
) -> MarkdownUnit {
    let markdown = match source {
        Some(SourceDocument::Text(text)) if request.media_type == "text/markdown" => {
            text.to_owned()
        }
        Some(SourceDocument::Text(text)) if request.media_type == "text/x-code" => {
            fence_code(text, request.raw.path.as_deref())
        }
        Some(SourceDocument::PdfPages(pages)) => {
            let page_index =
                page_index_from_unit_key(&hint.unit_key).unwrap_or(hint.order as usize);
            let page_text = pages.get(page_index).cloned().unwrap_or_default();
            let page_text = if is_probably_real_text(&page_text) {
                page_text
            } else {
                String::new()
            };
            format!("{}\n", page_text.trim())
        }
        Some(SourceDocument::Text(text)) => text.to_owned(),
        None => baseline_placeholder(&hint.unit_key, &hint.prepared_hash),
    };
    let markdown = if markdown.trim().is_empty() {
        baseline_placeholder(&hint.unit_key, &hint.prepared_hash)
    } else {
        markdown
    };
    MarkdownUnit {
        unit_key: hint.unit_key.clone(),
        unit_type: hint.unit_kind,
        // QA42: decisive normalization to Normalized Markdown v1 (07 §5.2.1),
        // not passthrough — at minimum Setext -> ATX plus the encoding rules
        // (BOM/CRLF/NFC/trailing-space/final-LF), applied as the last step so
        // every branch above (raw passthrough, fenced code, PDF-extracted
        // text, the baseline sentinel) is covered uniformly.
        markdown: normalize_to_markdown_v1(&markdown),
        metadata: Default::default(),
    }
}

/// QA42: decisive normalization to Normalized Markdown v1 (07 §5.2.1) —
/// BOM strip, CRLF/CR -> LF, Unicode NFC, per-line trailing-space strip
/// (applied inside a fenced code block too — encoding rules are not
/// fence-exempt, only *syntactic* transforms like the Setext rewrite are),
/// exactly one trailing LF, and Setext heading -> ATX heading conversion
/// (skipped inside a fenced code block, where a `---`/`===` line is data,
/// not a heading underline).
fn normalize_to_markdown_v1(text: &str) -> String {
    let no_bom = text.strip_prefix('\u{feff}').unwrap_or(text);
    let lf_only = no_bom.replace("\r\n", "\n").replace('\r', "\n");
    let nfc: String = lf_only.nfc().collect();
    let source_lines: Vec<&str> = nfc.split('\n').collect();
    let mut lines: Vec<String> = Vec::with_capacity(source_lines.len());
    let mut in_fence = false;
    let mut index = 0;
    while index < source_lines.len() {
        let line = source_lines[index];
        if line.trim_start_matches(' ').starts_with("```") {
            in_fence = !in_fence;
            lines.push(strip_trailing_space(line));
            index += 1;
            continue;
        }
        if !in_fence && !line.trim().is_empty() {
            if let Some(next) = source_lines.get(index + 1) {
                if let Some(level) = setext_level(next) {
                    lines.push(format!("{} {}", "#".repeat(level), line.trim()));
                    index += 2;
                    continue;
                }
            }
        }
        lines.push(strip_trailing_space(line));
        index += 1;
    }
    let mut result = lines.join("\n");
    while result.ends_with('\n') {
        result.pop();
    }
    result.push('\n');
    result
}

fn strip_trailing_space(line: &str) -> String {
    line.trim_end_matches([' ', '\t']).to_owned()
}

/// The Setext heading level (1 = `=`, 2 = `-`) for an underline candidate
/// line, or `None`. A `-` underline requires 2+ characters so a lone `-`
/// (ambiguous with other single-dash usage) is never reclassified.
fn setext_level(line: &str) -> Option<usize> {
    let trimmed = line.trim_start_matches(' ').trim_end_matches([' ', '\t']);
    if !trimmed.is_empty() && trimmed.bytes().all(|byte| byte == b'=') {
        Some(1)
    } else if trimmed.len() >= 2 && trimmed.bytes().all(|byte| byte == b'-') {
        Some(2)
    } else {
        None
    }
}

/// R21-5: whether extracted PDF page text is REAL text vs binary garbage lossy-decoded
/// from a scanned page's compressed stream. Real text is overwhelmingly printable; garbage
/// is dense with U+FFFD replacement characters and control bytes. Mirrors the pipeline's
/// `prepare::is_probably_real_text` (kept local to avoid a kcs-pipeline dependency).
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

fn fence_code(text: &str, path: Option<&str>) -> String {
    let lang = path
        .and_then(|path| std::path::Path::new(path).extension())
        .and_then(|extension| extension.to_str())
        .unwrap_or("");
    format!("```{lang}\n{}\n```\n", text.trim_end())
}

pub fn extract_pdf_text_pages_bounded(bytes: &[u8], max_pages: usize) -> Result<Vec<String>> {
    if max_pages == 0 {
        return Err(AdapterError::ContractViolation(
            "deterministic PDF page limit must be positive".to_owned(),
        ));
    }
    if !bytes.starts_with(b"%PDF") {
        return Ok(vec![String::from_utf8_lossy(bytes).into_owned()]);
    }
    let structural_count = structural_pdf_page_count(bytes, max_pages)?;
    let stream_pages = pdf_stream_text_pages_bounded(bytes, max_pages)?;
    // A missing structural page tree is malformed/ambiguous. Keep a single
    // conservative document unit instead of letting arbitrary stream count
    // become derived page authority.
    let page_count = structural_count.max(1);
    if !stream_pages.is_empty() {
        return Ok(normalize_pdf_page_count(stream_pages, page_count));
    }
    let strings = pdf_literal_strings(bytes);
    if strings.is_empty() {
        return Ok(vec![pdf_text_fallback(bytes)]);
    }
    if strings.len() == page_count {
        return Ok(strings);
    }
    let mut pages = strings;
    while pages.len() < page_count {
        pages.push(String::new());
    }
    pages.truncate(page_count);
    Ok(pages)
}

fn normalize_pdf_page_count(mut pages: Vec<String>, page_count: usize) -> Vec<String> {
    while pages.len() < page_count {
        pages.push(String::new());
    }
    pages.truncate(page_count);
    pages
}

/// Split a PDF's content streams into per-page text.
///
/// Canonical implementation shared with `kcs-pipeline` (which depends on this
/// crate). The stream terminator is located with [`find_endstream_boundary`] so
/// that a literal occurrence of the word "endstream" inside page text — e.g. a
/// document that discusses PDF internals — is not mistaken for the real stream
/// boundary and does not truncate the page to empty markdown (Step2c I3).
#[must_use]
pub fn pdf_stream_text_pages(bytes: &[u8]) -> Vec<String> {
    pdf_stream_text_pages_bounded(bytes, MAX_DETERMINISTIC_PDF_PAGES).unwrap_or_default()
}

pub fn pdf_stream_text_pages_bounded(bytes: &[u8], max_pages: usize) -> Result<Vec<String>> {
    let text = String::from_utf8_lossy(bytes);
    let mut rest = text.as_ref();
    let mut pages = Vec::new();
    while let Some(stream_start) = rest.find("stream") {
        let mut after_stream = &rest[stream_start + "stream".len()..];
        after_stream = after_stream
            .strip_prefix("\r\n")
            .or_else(|| after_stream.strip_prefix('\n'))
            .or_else(|| after_stream.strip_prefix('\r'))
            .unwrap_or(after_stream);
        let Some(stream_end) = find_endstream_boundary(after_stream) else {
            break;
        };
        let stream = &after_stream[..stream_end];
        let strings = pdf_literal_strings_in_text(stream);
        if !strings.is_empty() {
            pages.push(strings.join("\n"));
        } else if stream.contains("BT") {
            pages.push(String::new());
        }
        if pages.len() > max_pages {
            return Err(AdapterError::ContractViolation(format!(
                "deterministic PDF has more than {max_pages} text streams"
            )));
        }
        rest = &after_stream[stream_end + "endstream".len()..];
    }
    Ok(pages)
}

/// Offset of the next `endstream` keyword that terminates a PDF content stream:
/// it must begin a line (immediately preceded by `\n`/`\r`, or sit at the very
/// start of the slice for an empty stream) and be followed by whitespace or the
/// end of input. A mid-line "endstream" inside page text is ignored (Step2c I3).
fn find_endstream_boundary(text: &str) -> Option<usize> {
    const TOKEN: &str = "endstream";
    let bytes = text.as_bytes();
    let mut from = 0;
    while let Some(offset) = text[from..].find(TOKEN) {
        let index = from + offset;
        let at_line_start = index == 0 || matches!(bytes[index - 1], b'\n' | b'\r');
        let terminated = bytes
            .get(index + TOKEN.len())
            .is_none_or(|byte| byte.is_ascii_whitespace());
        if at_line_start && terminated {
            return Some(index);
        }
        from = index + TOKEN.len();
    }
    None
}

fn pdf_literal_strings(bytes: &[u8]) -> Vec<String> {
    let text = String::from_utf8_lossy(bytes);
    pdf_literal_strings_in_text(&text)
}

/// Extract PDF literal `( … )` strings from a text slice. Canonical
/// implementation shared with `kcs-pipeline` (Step2c I3).
#[must_use]
pub fn pdf_literal_strings_in_text(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut rest = text;
    while let Some(start) = rest.find('(') {
        rest = &rest[start + 1..];
        let Some(end) = rest.find(')') else {
            break;
        };
        let candidate = rest[..end]
            .replace("\\(", "(")
            .replace("\\)", ")")
            .replace("\\n", "\n");
        if candidate
            .chars()
            .any(|char| char.is_alphanumeric() || !char.is_ascii())
        {
            out.push(candidate);
        }
        rest = &rest[end + 1..];
    }
    out
}

fn pdf_text_fallback(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes)
        .lines()
        .filter(|line| !line.trim_start().starts_with('%'))
        .collect::<Vec<_>>()
        .join("\n")
}

/// Conservative compatibility helper for the pipeline. It counts exact
/// `/Type /Page` name pairs, ignores strings and streams, and saturates at one
/// over the deterministic limit. New callers should use
/// [`extract_pdf_text_pages_bounded`] so excess cardinality is an error.
pub fn pdf_page_count_in_text(text: &str) -> usize {
    structural_pdf_page_count(text.as_bytes(), MAX_DETERMINISTIC_PDF_PAGES)
        .unwrap_or(MAX_DETERMINISTIC_PDF_PAGES + 1)
}

fn structural_pdf_page_count(bytes: &[u8], max_pages: usize) -> Result<usize> {
    let mut index = 0_usize;
    let mut page_count = 0_usize;
    let mut dictionary_depth = 0_usize;
    while index < bytes.len() {
        match bytes[index] {
            b'%' => {
                index = bytes[index..]
                    .iter()
                    .position(|byte| matches!(byte, b'\n' | b'\r'))
                    .map(|offset| index + offset + 1)
                    .unwrap_or(bytes.len());
            }
            b'(' => index = skip_pdf_literal_string(bytes, index),
            b'<' if bytes.get(index + 1) == Some(&b'<') => {
                dictionary_depth = dictionary_depth.saturating_add(1);
                index += 2;
            }
            b'<' if bytes.get(index + 1) != Some(&b'<') => {
                index = bytes[index + 1..]
                    .iter()
                    .position(|byte| *byte == b'>')
                    .map(|offset| index + offset + 2)
                    .unwrap_or(bytes.len());
            }
            b'>' if bytes.get(index + 1) == Some(&b'>') => {
                dictionary_depth = dictionary_depth.saturating_sub(1);
                index += 2;
            }
            b's' if pdf_keyword_at(bytes, index, b"stream") => {
                index = find_endstream_bytes(bytes, index + b"stream".len()).unwrap_or(bytes.len());
            }
            b'/' if dictionary_depth > 0 && pdf_name_at(bytes, index, b"Type") => {
                let next = skip_pdf_space_and_comments(bytes, index + b"/Type".len());
                if pdf_name_at(bytes, next, b"Page") {
                    page_count = page_count.checked_add(1).ok_or_else(|| {
                        AdapterError::ContractViolation("PDF page count overflow".to_owned())
                    })?;
                    if page_count > max_pages {
                        return Err(AdapterError::ContractViolation(format!(
                            "deterministic PDF page count exceeds {max_pages}"
                        )));
                    }
                }
                index = next.saturating_add(1);
            }
            _ => index += 1,
        }
    }
    Ok(page_count)
}

fn skip_pdf_literal_string(bytes: &[u8], start: usize) -> usize {
    let mut index = start + 1;
    let mut depth = 1_usize;
    while index < bytes.len() {
        match bytes[index] {
            b'\\' => index = (index + 2).min(bytes.len()),
            b'(' => {
                depth += 1;
                index += 1;
            }
            b')' => {
                depth -= 1;
                index += 1;
                if depth == 0 {
                    break;
                }
            }
            _ => index += 1,
        }
    }
    index
}

fn skip_pdf_space_and_comments(bytes: &[u8], mut index: usize) -> usize {
    loop {
        while bytes
            .get(index)
            .is_some_and(|byte| byte.is_ascii_whitespace())
        {
            index += 1;
        }
        if bytes.get(index) != Some(&b'%') {
            return index;
        }
        index = bytes[index..]
            .iter()
            .position(|byte| matches!(byte, b'\n' | b'\r'))
            .map(|offset| index + offset + 1)
            .unwrap_or(bytes.len());
    }
}

fn pdf_name_at(bytes: &[u8], index: usize, name: &[u8]) -> bool {
    bytes.get(index) == Some(&b'/')
        && bytes.get(index + 1..index + 1 + name.len()) == Some(name)
        && bytes
            .get(index + 1 + name.len())
            .is_none_or(|byte| is_pdf_delimiter(*byte))
}

fn pdf_keyword_at(bytes: &[u8], index: usize, keyword: &[u8]) -> bool {
    bytes.get(index..index + keyword.len()) == Some(keyword)
        && (index == 0 || is_pdf_delimiter(bytes[index - 1]))
        && bytes
            .get(index + keyword.len())
            .is_none_or(|byte| is_pdf_delimiter(*byte))
}

fn is_pdf_delimiter(byte: u8) -> bool {
    byte.is_ascii_whitespace()
        || matches!(
            byte,
            b'(' | b')' | b'<' | b'>' | b'[' | b']' | b'{' | b'}' | b'/' | b'%'
        )
}

fn find_endstream_bytes(bytes: &[u8], from: usize) -> Option<usize> {
    const TOKEN: &[u8] = b"endstream";
    let mut index = from;
    while index + TOKEN.len() <= bytes.len() {
        if bytes.get(index..index + TOKEN.len()) == Some(TOKEN)
            && (index == 0 || matches!(bytes[index - 1], b'\n' | b'\r'))
            && bytes
                .get(index + TOKEN.len())
                .is_none_or(u8::is_ascii_whitespace)
        {
            return Some(index + TOKEN.len());
        }
        index += 1;
    }
    None
}

fn page_index_from_unit_key(unit_key: &str) -> Option<usize> {
    unit_key
        .strip_prefix("page:")?
        .parse::<usize>()
        .ok()
        .and_then(|page| page.checked_sub(1))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::traits::MarkdownizeAdapter;

    // R21-5: a mixed PDF's real text page passes `is_probably_real_text`; a scanned page's
    // lossy-decoded binary (dense with U+FFFD / control bytes) does not. Page selection
    // uses this to suppress the garbage page so it is never persisted as a searchable chunk,
    // while the R20-4 all-pages-garbage gate keeps routing a wholly-scanned doc to OCR.
    #[test]
    fn r21_5_is_probably_real_text_rejects_binary_garbage_page() {
        assert!(is_probably_real_text(
            "This is a genuine first page paragraph with real readable words."
        ));
        assert!(is_probably_real_text(
            "日本語のテキストレイヤーも本物として扱う。"
        ));
        let garbage: String = (0u32..600)
            .map(|i| {
                if i % 2 == 0 {
                    '\u{fffd}'
                } else {
                    char::from_u32(i % 0x1f + 1).unwrap_or('\u{1}')
                }
            })
            .collect();
        assert!(!is_probably_real_text(&garbage));
        assert!(!is_probably_real_text(""));
    }

    // QA42 (step4b-contract-tests-p3a.md §L): the built-in deterministic
    // adapter converts a Setext H1/H2 to ATX (04 §3.2 V5 / 07 §5.2.1) instead
    // of a straight passthrough.
    #[test]
    fn qa42_setext_headings_are_converted_to_atx() {
        assert_eq!(
            normalize_to_markdown_v1("Title\n=====\n\nBody text\n"),
            "# Title\n\nBody text\n"
        );
        assert_eq!(
            normalize_to_markdown_v1("Subtitle\n--------\n"),
            "## Subtitle\n"
        );
        // A lone `-` is never reclassified (ambiguous with other single-dash
        // usage — the underline heuristic requires 2+ characters).
        assert_eq!(normalize_to_markdown_v1("Line\n-\n"), "Line\n-\n");
        // A `---`/`===` line inside a fenced code block is data, not a
        // heading underline.
        assert_eq!(
            normalize_to_markdown_v1("```\nTitle\n=====\n```\n"),
            "```\nTitle\n=====\n```\n"
        );
    }

    // QA41/QA42: the encoding-level Normalized Markdown v1 rules (07 §5.2.1)
    // are applied unconditionally — BOM strip, CRLF -> LF, NFC, per-line
    // trailing-space strip (including inside a fence — only syntactic
    // transforms like Setext are fence-exempt), and exactly one trailing LF.
    #[test]
    fn qa41_encoding_rules_are_normalized_even_inside_a_fence() {
        assert_eq!(
            normalize_to_markdown_v1("\u{feff}# Heading\r\n\r\nBody\r\n"),
            "# Heading\n\nBody\n"
        );
        assert_eq!(
            normalize_to_markdown_v1("Trailing space here   \nNext line\t\n"),
            "Trailing space here\nNext line\n"
        );
        assert_eq!(
            normalize_to_markdown_v1("```\nlet x = 1;   \n```"),
            "```\nlet x = 1;\n```\n"
        );
        // NFD combining sequence (e already knows the Step2a fixture: e +
        // U+0301) normalizes to the precomposed NFC form.
        assert_eq!(normalize_to_markdown_v1("cafe\u{0301}\n"), "caf\u{e9}\n");
        // Multiple trailing blank lines collapse to exactly one trailing LF.
        assert_eq!(normalize_to_markdown_v1("Body\n\n\n"), "Body\n");
    }

    // QA41: the offline baseline placeholder itself must satisfy Normalized
    // Markdown v1 (07 §5.2.1) — plain text, not an HTML comment (an HTML
    // comment is a raw-HTML block, forbidden by 04 §3.2 V5).
    #[test]
    fn qa41_baseline_placeholder_is_plain_text_not_raw_html() {
        let placeholder = baseline_placeholder("page:1", "sha256:abc");
        assert!(!placeholder.contains('<'));
        assert!(!placeholder.contains('>'));
        assert_eq!(normalize_to_markdown_v1(&placeholder), placeholder);
    }

    #[test]
    fn placeholder_deterministic_profile_disallows_network() {
        let adapter = DeterministicAdapter;
        let profile = MarkdownizeAdapter::profile(&adapter);

        assert!(!profile.allow_network);
        assert_eq!(profile.adapter_id, "deterministic_builtin");
    }

    // O4: a multibyte char straddling the fixed lookahead window from a `/Page`
    // or `/Type` token used to panic on the str slice's char boundary (aborting
    // `kcs index` with exit 101 and dumping the body to stderr). It must now be
    // counted cleanly without panicking.
    #[test]
    fn o4_pdf_page_count_survives_multibyte_char_boundary() {
        // Prefixes such as `/PageX` are not structural page names.
        assert_eq!(
            pdf_page_count_in_text("/PageXあ padding to extend length"),
            0
        );
        // "あ" straddles the +32 byte window measured from "/Type" (no panic).
        let type_case = format!("/Type{}あ/Pages", "y".repeat(26));
        let _ = pdf_page_count_in_text(&type_case);
        // Genuine /Pages still suppresses the count.
        assert_eq!(pdf_page_count_in_text("/Type /Pages catalog"), 0);
    }

    // Q5: a leading UTF-8 BOM (Windows Notepad / Excel / PowerShell default) used
    // to sit in front of the first ATX heading's `#`, so the chunker dropped that
    // heading. Deterministic source decoding must strip one leading BOM so the produced
    // markdown starts at the heading.
    #[test]
    fn q5_leading_bom_does_not_hide_first_heading() {
        use crate::types::{MarkdownizeMode, MarkdownizeRequest, RawInput};
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("bom.md");
        let bytes = b"\xef\xbb\xbf# Heading One\n\nbody\n";
        std::fs::write(&path, bytes).unwrap();
        let request = MarkdownizeRequest {
            raw: RawInput {
                raw_hash: crate::identity::hash_bytes(bytes),
                path: Some(path.display().to_string()),
            },
            media_type: "text/markdown".to_owned(),
            prepared_unit_hint: None,
            mode: MarkdownizeMode::Full,
            previous: None,
            hints: None,
            restrict_to_hint_pages: false,
            bbox_annotation_enabled: false,
            tool_profile_hash: format!("sha256:{}", "1".repeat(64)),
            spec_version: 1,
        };
        let response = MarkdownizeAdapter::markdownize(&DeterministicAdapter, request).unwrap();
        let markdown = &response.updated_units[0].markdown;
        assert!(
            markdown.starts_with("# Heading One"),
            "BOM must be stripped so the heading sits at column 0: {markdown:?}"
        );
        assert!(!markdown.contains('\u{feff}'), "no BOM should remain");
    }

    #[test]
    fn structural_pdf_count_ignores_markers_in_strings_and_streams() {
        let pdf = b"%PDF-1.4\n\
1 0 obj << /Type /Pages /Count 1 >> endobj\n\
2 0 obj << /Type /Page /Parent 1 0 R /Note (/Type /Page /PageX) >>\n\
stream\nBT (/Type /Page and /PageX) Tj ET\nendstream\nendobj\n";
        assert_eq!(structural_pdf_page_count(pdf, 8).unwrap(), 1);
        assert_eq!(extract_pdf_text_pages_bounded(pdf, 8).unwrap().len(), 1);
        assert_eq!(
            structural_pdf_page_count(b"%PDF-1.4\n/Type /Page\n", 8).unwrap(),
            0
        );
    }

    #[test]
    fn structural_pdf_page_limit_rejects_before_padding() {
        let mut pdf = b"%PDF-1.4\n".to_vec();
        for id in 1..=4 {
            pdf.extend_from_slice(format!("{id} 0 obj << /Type /Page >> endobj\n").as_bytes());
        }
        let err = extract_pdf_text_pages_bounded(&pdf, 3).unwrap_err();
        assert!(err.to_string().contains("page count exceeds 3"));
    }

    #[test]
    fn verified_pdf_bytes_are_reused_for_all_hints() {
        use crate::types::{MarkdownizeMode, MarkdownizeRequest, RawInput};

        let pdf = b"%PDF-1.4\n\
1 0 obj << /Type /Pages /Count 2 >> endobj\n\
2 0 obj << /Type /Page >> stream\nBT (First page) Tj ET\nendstream\nendobj\n\
3 0 obj << /Type /Page >> stream\nBT (Second page) Tj ET\nendstream\nendobj\n";
        let request = MarkdownizeRequest {
            raw: RawInput {
                raw_hash: crate::identity::hash_bytes(pdf),
                path: Some("/path/that/must/not/be/opened.pdf".to_owned()),
            },
            media_type: "application/pdf".to_owned(),
            prepared_unit_hint: Some(vec![
                PreparedUnitHint {
                    unit_key: "page:1".to_owned(),
                    prepared_hash: "sha256:first".to_owned(),
                    unit_kind: UnitKind::Page,
                    order: 0,
                },
                PreparedUnitHint {
                    unit_key: "page:2".to_owned(),
                    prepared_hash: "sha256:second".to_owned(),
                    unit_kind: UnitKind::Page,
                    order: 1,
                },
            ]),
            mode: MarkdownizeMode::Full,
            previous: None,
            hints: None,
            restrict_to_hint_pages: false,
            bbox_annotation_enabled: false,
            tool_profile_hash: "sha256:tool".to_owned(),
            spec_version: 1,
        };
        let response = markdownize_from_bytes(request, pdf).unwrap();
        assert_eq!(response.updated_units.len(), 2);
        assert!(response.updated_units[0].markdown.contains("First page"));
        assert!(response.updated_units[1].markdown.contains("Second page"));
    }
}
