//! Built-in deterministic adapter skeleton.

use crate::traits::{MarkdownizeAdapter, PrepareAdapter};
use crate::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownUnit, MarkdownizeMode, MarkdownizeRequest,
    MarkdownizeResponse, PrepareRequest, PrepareResponse, PreparedUnitHint, PreparedUnitMetadata,
    UnitFingerprint, UnitKind,
};
use crate::Result;
use serde_json::json;

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
        let hints = request
            .prepared_unit_hint
            .clone()
            .unwrap_or_else(|| vec![default_hint(&request.raw.raw_hash)]);
        let source_text = read_source_text(&request);
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
                    .map(|hint| markdown_unit_from_hint(hint, &request, source_text.as_deref()))
                    .collect(),
                unchanged_unit_keys: Vec::new(),
                added_units: hints
                    .iter()
                    .filter(|hint| added.contains(&hint.unit_key))
                    .map(|hint| markdown_unit_from_hint(hint, &request, source_text.as_deref()))
                    .collect(),
                removed_unit_keys: incremental
                    .map(|hints| hints.removed_unit_keys)
                    .unwrap_or_default(),
                evidence_pointers: Vec::new(),
                fallback_to_full: false,
                reason: None,
            });
        }

        Ok(MarkdownizeResponse {
            mode_used: MarkdownizeMode::Full,
            updated_units: hints
                .iter()
                .map(|hint| markdown_unit_from_hint(hint, &request, source_text.as_deref()))
                .collect(),
            unchanged_unit_keys: Vec::new(),
            added_units: Vec::new(),
            removed_unit_keys: Vec::new(),
            evidence_pointers: Vec::new(),
            fallback_to_full: false,
            reason: None,
        })
    }
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

fn markdown_unit_from_hint(
    hint: &PreparedUnitHint,
    request: &MarkdownizeRequest,
    source_text: Option<&str>,
) -> MarkdownUnit {
    let markdown = match source_text {
        Some(text) if request.media_type == "text/markdown" => text.to_owned(),
        Some(text) if request.media_type == "text/x-code" => {
            fence_code(text, request.raw.path.as_deref())
        }
        Some(text) if request.media_type == "application/pdf" => {
            let page_text = read_pdf_page_text(request, hint).unwrap_or_else(|| text.to_owned());
            format!("{}\n", page_text.trim())
        }
        Some(text) => text.to_owned(),
        None => format!(
            "<!-- KCS deterministic baseline {} {} -->\n",
            hint.unit_key, hint.prepared_hash
        ),
    };
    MarkdownUnit {
        unit_key: hint.unit_key.clone(),
        unit_type: hint.unit_kind,
        markdown: if markdown.trim().is_empty() {
            format!(
                "<!-- KCS deterministic baseline {} {} -->\n",
                hint.unit_key, hint.prepared_hash
            )
        } else {
            markdown
        },
        metadata: Default::default(),
    }
}

fn read_source_text(request: &MarkdownizeRequest) -> Option<String> {
    let path = request.raw.path.as_ref()?;
    let bytes = std::fs::read(path).ok()?;
    if request.media_type == "application/pdf" {
        return Some(extract_pdf_text_pages(&bytes).join("\n\n"));
    }
    Some(String::from_utf8_lossy(&bytes).into_owned())
}

fn read_pdf_page_text(request: &MarkdownizeRequest, hint: &PreparedUnitHint) -> Option<String> {
    let path = request.raw.path.as_ref()?;
    let bytes = std::fs::read(path).ok()?;
    let pages = extract_pdf_text_pages(&bytes);
    let page_index = page_index_from_unit_key(&hint.unit_key).unwrap_or(hint.order as usize);
    pages.get(page_index).cloned()
}

fn fence_code(text: &str, path: Option<&str>) -> String {
    let lang = path
        .and_then(|path| std::path::Path::new(path).extension())
        .and_then(|extension| extension.to_str())
        .unwrap_or("");
    format!("```{lang}\n{}\n```\n", text.trim_end())
}

fn extract_pdf_text_pages(bytes: &[u8]) -> Vec<String> {
    if !bytes.starts_with(b"%PDF") {
        return vec![String::from_utf8_lossy(bytes).into_owned()];
    }
    let page_count = pdf_page_count(bytes).max(1);
    let stream_pages = pdf_stream_text_pages(bytes);
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

/// Split a PDF's content streams into per-page text.
///
/// Canonical implementation shared with `kcs-pipeline` (which depends on this
/// crate). The stream terminator is located with [`find_endstream_boundary`] so
/// that a literal occurrence of the word "endstream" inside page text — e.g. a
/// document that discusses PDF internals — is not mistaken for the real stream
/// boundary and does not truncate the page to empty markdown (Step2c I3).
#[must_use]
pub fn pdf_stream_text_pages(bytes: &[u8]) -> Vec<String> {
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
        rest = &after_stream[stream_end + "endstream".len()..];
    }
    pages
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
        // MSRV 1.80: `Option::is_none_or` is 1.82+, so use `map_or(true, …)`.
        let terminated = bytes
            .get(index + TOKEN.len())
            .map_or(true, |byte| byte.is_ascii_whitespace());
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

fn pdf_page_count(bytes: &[u8]) -> usize {
    pdf_page_count_in_text(&String::from_utf8_lossy(bytes))
}

/// Count PDF page objects from the (lossy-decoded) file text. Shared by the
/// pipeline crate so the char-boundary-safe lookahead lives in one place (O4).
pub fn pdf_page_count_in_text(text: &str) -> usize {
    let pages = text
        .match_indices("/Type")
        .filter(|(index, _)| {
            let tail = bounded_str_window(text, *index, 32);
            tail.contains("/Page") && !tail.contains("/Pages")
        })
        .count();
    pages.max(
        text.match_indices("/Page")
            .filter(|(index, _)| {
                let tail = bounded_str_window(text, *index, 8);
                !tail.starts_with("/Pages")
            })
            .count(),
    )
}

/// A `start..start+max_len` byte-slice of `text` clamped so it never splits a
/// multibyte UTF-8 character (O4). `start` is always a char boundary here (it
/// comes from `match_indices`); the end is clamped to `text.len()` and walked
/// back to the nearest boundary, so a crafted multibyte char straddling the
/// lookahead window can never trigger a `char boundary` slice panic (which used
/// to abort `kcs index` with exit 101 and dump the body to stderr).
fn bounded_str_window(text: &str, start: usize, max_len: usize) -> &str {
    let mut end = start.saturating_add(max_len).min(text.len());
    while end > start && !text.is_char_boundary(end) {
        end -= 1;
    }
    text.get(start..end).unwrap_or("")
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
        // "あ" occupies the +8 byte window measured from "/Page".
        assert_eq!(
            pdf_page_count_in_text("/PageXあ padding to extend length"),
            1
        );
        // "あ" straddles the +32 byte window measured from "/Type" (no panic).
        let type_case = format!("/Type{}あ/Pages", "y".repeat(26));
        let _ = pdf_page_count_in_text(&type_case);
        // Genuine /Pages still suppresses the count.
        assert_eq!(pdf_page_count_in_text("/Type /Pages catalog"), 0);
    }
}
