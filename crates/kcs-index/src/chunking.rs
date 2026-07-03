//! Chunking contracts for normalized unit instances.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use unicode_normalization::UnicodeNormalization;

use crate::{ChunkRow, IndexError, Result};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChunkingConfig {
    pub chunking_config_hash: String,
    /// 03 §11 `[chunking] strategy` (MVP は "heading" のみ)
    pub strategy: String,
    /// 03 §11 `[chunking] max_chars` (04 §4.1 の分割規則の閾値)
    pub max_chars: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NormalizedUnitInput {
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub unit_key: String,
    pub markdown: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChunkingInput {
    pub raw_path: String,
    pub units: Vec<NormalizedUnitInput>,
    pub config: ChunkingConfig,
    pub created_at: String,
}

pub trait Chunker {
    fn chunk(&self, input: ChunkingInput) -> Result<Vec<ChunkRow>>;
}

pub fn default_chunking_config() -> Result<ChunkingConfig> {
    let hash = chunking_config_hash("heading", 6000)?;
    Ok(ChunkingConfig {
        chunking_config_hash: hash,
        strategy: "heading".to_owned(),
        max_chars: 6000,
    })
}

pub fn chunking_config_hash(strategy: &str, max_chars: u64) -> Result<String> {
    let value = json!({
        "max_chars": max_chars,
        "spec_version": 1,
        "strategy": strategy,
    });
    hash_jcs(&value)
}

pub fn chunk_hash(row: &ChunkRow) -> Result<String> {
    let mut map = Map::new();
    map.insert("char_end".to_owned(), json!(row.char_end.unwrap_or(0)));
    map.insert("char_start".to_owned(), json!(row.char_start.unwrap_or(0)));
    map.insert("gen".to_owned(), json!(row.gen));
    map.insert(
        "heading_path".to_owned(),
        json!(row.heading_path.clone().unwrap_or_default()),
    );
    map.insert("raw_hash".to_owned(), json!(row.raw_hash));
    if let Some(section_id) = row.section_id.as_ref().filter(|value| !value.is_empty()) {
        map.insert("section_id".to_owned(), json!(section_id));
    }
    map.insert("spec_version".to_owned(), json!(1));
    map.insert("tool_profile_hash".to_owned(), json!(row.tool_profile_hash));
    map.insert("unit_key".to_owned(), json!(row.unit_key));
    hash_jcs(&Value::Object(map))
}

pub fn slugify_heading(text: &str) -> String {
    let normalized: String = text.nfc().collect();
    let mut out = String::with_capacity(normalized.len());
    let mut last_dash = false;
    for ch in normalized.chars() {
        let mapped = if ch.is_ascii_uppercase() {
            Some(ch.to_ascii_lowercase())
        } else if ch.is_ascii_alphanumeric() || ch == '_' || is_japanese(ch) {
            Some(ch)
        } else if ch.is_whitespace() || ch == '-' {
            Some('-')
        } else {
            None
        };
        if let Some(ch) = mapped {
            if ch == '-' {
                if !last_dash {
                    out.push(ch);
                    last_dash = true;
                }
            } else {
                out.push(ch);
                last_dash = false;
            }
        }
    }
    out.trim_matches('-').to_owned()
}

pub fn chunk_normalized_instance(input: ChunkingInput) -> Result<Vec<ChunkRow>> {
    if input.config.strategy != "heading" {
        return Err(IndexError::Contract(format!(
            "unsupported chunking strategy: {}",
            input.config.strategy
        )));
    }
    if input.config.max_chars == 0 {
        return Err(IndexError::Contract(
            "chunking max_chars must be greater than zero".to_owned(),
        ));
    }

    let mut rows = Vec::new();
    for unit in &input.units {
        let sections = section_ranges(&unit.markdown);
        let mut duplicate_counts = BTreeMap::<String, u64>::new();
        for section in sections {
            let base_section_id = if section.heading_path.is_empty() {
                None
            } else {
                let joined = section
                    .heading_path
                    .iter()
                    .map(|heading| slugify_heading(heading))
                    .filter(|slug| !slug.is_empty())
                    .collect::<Vec<_>>()
                    .join("/");
                if joined.is_empty() {
                    None
                } else {
                    Some(joined)
                }
            };
            let section_id = base_section_id.map(|base| {
                let count = duplicate_counts.entry(base.clone()).or_insert(0);
                *count += 1;
                if *count == 1 {
                    base
                } else {
                    format!("{base}#{}", *count)
                }
            });
            for (start, end) in split_range_by_max_chars(
                &unit.markdown,
                section.start,
                section.end,
                input.config.max_chars as usize,
            ) {
                if start >= end {
                    continue;
                }
                let text = slice_chars(&unit.markdown, start, end);
                let mut row = ChunkRow {
                    chunk_id: String::new(),
                    raw_hash: unit.raw_hash.clone(),
                    tool_profile_hash: unit.tool_profile_hash.clone(),
                    gen: unit.gen,
                    unit_key: unit.unit_key.clone(),
                    chunking_config_hash: input.config.chunking_config_hash.clone(),
                    raw_path: input.raw_path.clone(),
                    heading_path: Some(section.heading_path.clone()),
                    section_id: section_id.clone(),
                    char_start: Some(start as u64),
                    char_end: Some(end as u64),
                    text_hash: hash_bytes(text.as_bytes()),
                    text,
                    first_seen_commit: None,
                    created_at: input.created_at.clone(),
                };
                row.chunk_id = chunk_hash(&row)?;
                rows.push(row);
            }
        }
    }
    Ok(rows)
}

#[derive(Debug, Clone)]
struct SectionRange {
    start: usize,
    end: usize,
    heading_path: Vec<String>,
}

#[derive(Debug, Clone)]
struct HeadingEvent {
    start: usize,
    level: usize,
    text: String,
}

fn section_ranges(markdown: &str) -> Vec<SectionRange> {
    let headings = heading_events(markdown);
    let total = markdown.chars().count();
    if headings.is_empty() {
        return vec![SectionRange {
            start: 0,
            end: total,
            heading_path: Vec::new(),
        }];
    }

    let mut ranges = Vec::new();
    if headings[0].start > 0 {
        ranges.push(SectionRange {
            start: 0,
            end: headings[0].start,
            heading_path: Vec::new(),
        });
    }

    let mut stack: Vec<String> = Vec::new();
    for (index, event) in headings.iter().enumerate() {
        stack.truncate(event.level.saturating_sub(1));
        stack.push(event.text.clone());
        let end = headings
            .get(index + 1)
            .map(|next| next.start)
            .unwrap_or(total);
        ranges.push(SectionRange {
            start: event.start,
            end,
            heading_path: stack.clone(),
        });
    }
    ranges
}

fn heading_events(markdown: &str) -> Vec<HeadingEvent> {
    let mut events = Vec::new();
    let mut char_offset = 0usize;
    let mut in_fence = false;
    for line in markdown.split_inclusive('\n') {
        let trimmed = line.trim_start();
        if trimmed.starts_with("```") || trimmed.starts_with("~~~") {
            in_fence = !in_fence;
        }
        if !in_fence {
            if let Some((level, text)) = parse_atx_heading(line) {
                events.push(HeadingEvent {
                    start: char_offset,
                    level,
                    text,
                });
            }
        }
        char_offset += line.chars().count();
    }
    events
}

fn parse_atx_heading(line: &str) -> Option<(usize, String)> {
    let trimmed = line.strip_suffix('\n').unwrap_or(line);
    let trimmed = trimmed.strip_suffix('\r').unwrap_or(trimmed);
    let mut chars = trimmed.chars();
    let mut level = 0usize;
    while matches!(chars.clone().next(), Some('#')) {
        level += 1;
        chars.next();
    }
    if !(1..=6).contains(&level) {
        return None;
    }
    if !matches!(chars.next(), Some(ch) if ch.is_whitespace()) {
        return None;
    }
    let text = chars.as_str().trim();
    let text = text.trim_end_matches('#').trim().to_owned();
    (!text.is_empty()).then_some((level, text))
}

fn split_range_by_max_chars(
    text: &str,
    start: usize,
    end: usize,
    max_chars: usize,
) -> Vec<(usize, usize)> {
    if end.saturating_sub(start) <= max_chars {
        return vec![(start, end)];
    }
    let mut ranges = Vec::new();
    let mut cursor = start;
    while cursor < end {
        let limit = (cursor + max_chars).min(end);
        if limit == end {
            ranges.push((cursor, end));
            break;
        }
        let window = slice_chars(text, cursor, limit);
        let split_at = last_paragraph_boundary(&window)
            .filter(|boundary| *boundary > 0)
            .map(|boundary| cursor + boundary)
            .unwrap_or(limit);
        ranges.push((cursor, split_at));
        cursor = split_at;
        while cursor < end {
            let ch = slice_chars(text, cursor, cursor + 1);
            if ch.trim().is_empty() {
                cursor += 1;
            } else {
                break;
            }
        }
    }
    ranges
}

fn last_paragraph_boundary(window: &str) -> Option<usize> {
    let mut prev_newline = false;
    let mut last = None;
    let mut offset = 0usize;
    for ch in window.chars() {
        offset += 1;
        if ch == '\n' {
            if prev_newline {
                last = Some(offset);
            }
            prev_newline = true;
        } else if !ch.is_whitespace() {
            prev_newline = false;
        }
    }
    last
}

fn slice_chars(text: &str, start: usize, end: usize) -> String {
    text.chars().skip(start).take(end - start).collect()
}

fn hash_jcs(value: &Value) -> Result<String> {
    serde_jcs::to_vec(value)
        .map(|bytes| hash_bytes(&bytes))
        .map_err(|err| IndexError::Schema(err.to_string()))
}

fn hash_bytes(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    format!("sha256:{}", lower_hex(&digest))
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

fn is_japanese(ch: char) -> bool {
    matches!(
        ch as u32,
        0x3040..=0x309f | 0x30a0..=0x30ff | 0x4e00..=0x9fff
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    const RAW: &str = "sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a";
    const TOOL: &str = "sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0";

    fn fixture_row(gen: u64, section_id: Option<&str>, heading_path: Vec<&str>) -> ChunkRow {
        ChunkRow {
            chunk_id: String::new(),
            raw_hash: RAW.to_owned(),
            tool_profile_hash: TOOL.to_owned(),
            gen,
            unit_key: "page:12".to_owned(),
            chunking_config_hash: "sha256:cfg".to_owned(),
            raw_path: "report.pdf".to_owned(),
            heading_path: Some(heading_path.into_iter().map(str::to_owned).collect()),
            section_id: section_id.map(str::to_owned),
            char_start: Some(1200),
            char_end: Some(1500),
            text_hash: "sha256:text".to_owned(),
            text: String::new(),
            first_seen_commit: None,
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        }
    }

    #[test]
    fn ct3_chunk_001_hash_vector_gen0_section_id() {
        let row = fixture_row(0, Some("認証仕様/api-token"), vec!["認証仕様", "API Token"]);
        assert_eq!(
            chunk_hash(&row).unwrap(),
            "sha256:c5e31f10da04b722769bdbbd60a55b94c177b5f3bf9c64e5341be7281d115c3d"
        );
    }

    #[test]
    fn ct3_chunk_002_hash_vector_gen_changes_identity() {
        let row = fixture_row(3, Some("認証仕様/api-token"), vec!["認証仕様", "API Token"]);
        assert_eq!(
            chunk_hash(&row).unwrap(),
            "sha256:688cc82734bed7cb37ff1e40674dfdf4e48670bfde263962aabaac4f88d75e54"
        );
    }

    #[test]
    fn ct3_chunk_003_null_section_id_is_omitted_heading_path_empty_stays() {
        let mut row = ChunkRow {
            chunk_id: String::new(),
            raw_hash: RAW.to_owned(),
            tool_profile_hash: TOOL.to_owned(),
            gen: 0,
            unit_key: "doc:1".to_owned(),
            chunking_config_hash: "sha256:cfg".to_owned(),
            raw_path: "report.pdf".to_owned(),
            heading_path: Some(Vec::new()),
            section_id: None,
            char_start: Some(0),
            char_end: Some(600),
            text_hash: "sha256:text".to_owned(),
            text: String::new(),
            first_seen_commit: None,
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        };
        let omitted = chunk_hash(&row).unwrap();
        row.section_id = Some(String::new());
        assert_eq!(chunk_hash(&row).unwrap(), omitted);
        assert_eq!(
            omitted,
            "sha256:d1fe73cef624a76949293ca550ae305ce8a2c46517a83e7d52b2bcc700b2c8d6"
        );
    }

    #[test]
    fn ct3_chunk_004_heading_chunking_slug_code_fence_and_max_chars() {
        let config = ChunkingConfig {
            chunking_config_hash: chunking_config_hash("heading", 40).unwrap(),
            strategy: "heading".to_owned(),
            max_chars: 40,
        };
        let input = ChunkingInput {
            raw_path: "a.md".to_owned(),
            units: vec![NormalizedUnitInput {
                raw_hash: RAW.to_owned(),
                tool_profile_hash: TOOL.to_owned(),
                gen: 0,
                unit_key: "doc:1".to_owned(),
                markdown: "intro\n```text\n# not heading\n```\n# 認証仕様\npara one\n\npara two\n## API Token\nbody".to_owned(),
            }],
            config,
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        };
        let rows = chunk_normalized_instance(input).unwrap();
        assert!(rows.iter().any(|row| row.heading_path == Some(Vec::new())));
        assert!(rows
            .iter()
            .any(|row| row.section_id.as_deref() == Some("認証仕様")));
        assert!(rows
            .iter()
            .any(|row| row.section_id.as_deref() == Some("認証仕様/api-token")));
        assert!(!rows
            .iter()
            .any(|row| row.section_id.as_deref() == Some("not-heading")));
    }

    #[test]
    fn ct3_chunk_005_spans_are_unit_local() {
        let config = default_chunking_config().unwrap();
        let input = ChunkingInput {
            raw_path: "a.md".to_owned(),
            units: vec![NormalizedUnitInput {
                raw_hash: RAW.to_owned(),
                tool_profile_hash: TOOL.to_owned(),
                gen: 0,
                unit_key: "doc:1".to_owned(),
                markdown: "abc\n# H\nbody".to_owned(),
            }],
            config,
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        };
        let rows = chunk_normalized_instance(input).unwrap();
        assert_eq!(rows[0].char_start, Some(0));
        assert_eq!(rows[0].char_end, Some(4));
        assert_eq!(rows[1].char_start, Some(4));
    }

    // CT3-CHUNK-005 (gap fill): the spec's Given is explicitly a unit "combined at
    // the tail side of a full-text view" — a single-unit fixture can't distinguish
    // "span is unit-local" from "span happens to start at 0 because there's only
    // one unit". A second, later unit must restart char_start at 0 rather than
    // continuing from the first unit's end, and its heading stack must not inherit
    // the first unit's headings (chunk does not cross the unit boundary, 04 §4.1
    // rule 1 / A.1 offset independence).
    #[test]
    fn ct3_chunk_005_second_unit_span_and_heading_path_do_not_inherit_from_first() {
        let config = default_chunking_config().unwrap();
        let input = ChunkingInput {
            raw_path: "a.md".to_owned(),
            units: vec![
                NormalizedUnitInput {
                    raw_hash: RAW.to_owned(),
                    tool_profile_hash: TOOL.to_owned(),
                    gen: 0,
                    unit_key: "doc:1".to_owned(),
                    markdown: "# First\nfirst body of some length".to_owned(),
                },
                NormalizedUnitInput {
                    raw_hash: RAW.to_owned(),
                    tool_profile_hash: TOOL.to_owned(),
                    gen: 0,
                    unit_key: "doc:2".to_owned(),
                    markdown: "second body, no heading here".to_owned(),
                },
            ],
            config,
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        };
        let rows = chunk_normalized_instance(input).unwrap();
        let second_unit_row = rows
            .iter()
            .find(|row| row.unit_key == "doc:2")
            .expect("second unit must produce a chunk");
        // Restarted at 0, not continuing from the first unit's ~34-char length.
        assert_eq!(second_unit_row.char_start, Some(0));
        // No heading appears before it in doc:2, so heading_path must be empty —
        // not `["First"]` leaked across the unit boundary.
        assert_eq!(second_unit_row.heading_path, Some(Vec::new()));
        assert_eq!(second_unit_row.section_id, None);
    }

    // CT3-CHUNK-004 (gap fill): the existing ct3_chunk_004 test never exceeds
    // max_chars, so rule 5 (paragraph-boundary greedy split, single-paragraph-only
    // falls back to a hard character split; split pieces share heading_path /
    // section_id and are distinguished by unit-local span) was unverified.
    #[test]
    fn ct3_chunk_004_max_chars_splits_at_paragraph_boundary_and_shares_section() {
        let config = ChunkingConfig {
            chunking_config_hash: chunking_config_hash("heading", 20).unwrap(),
            strategy: "heading".to_owned(),
            max_chars: 20,
        };
        let input = ChunkingInput {
            raw_path: "a.md".to_owned(),
            units: vec![NormalizedUnitInput {
                raw_hash: RAW.to_owned(),
                tool_profile_hash: TOOL.to_owned(),
                gen: 0,
                unit_key: "doc:1".to_owned(),
                // Section body ("paragraph one long enough\n\nparagraph two also
                // long enough") is well over max_chars=20 and has a paragraph
                // boundary (blank line) to split on.
                markdown: "# Heading\nparagraph one long enough\n\nparagraph two also long enough"
                    .to_owned(),
            }],
            config,
            created_at: "2026-07-03T00:00:00Z".to_owned(),
        };
        let rows = chunk_normalized_instance(input).unwrap();
        let section_rows = rows
            .iter()
            .filter(|row| row.section_id.as_deref() == Some("heading"))
            .collect::<Vec<_>>();
        // The over-long section must be split into more than one chunk.
        assert!(
            section_rows.len() > 1,
            "expected max_chars to force a split, got {} chunk(s)",
            section_rows.len()
        );
        // Every char span stays within max_chars, and split pieces share
        // heading_path / section_id but are distinguished by span.
        for row in &section_rows {
            let span = row.char_end.unwrap() - row.char_start.unwrap();
            assert!(span <= 20, "split chunk exceeds max_chars: {span}");
            assert_eq!(row.heading_path, Some(vec!["Heading".to_owned()]));
        }
        let mut spans = section_rows
            .iter()
            .map(|row| (row.char_start.unwrap(), row.char_end.unwrap()))
            .collect::<Vec<_>>();
        spans.sort_unstable();
        // Contiguous, non-overlapping coverage (greedy split, no gaps beyond the
        // whitespace consumed between pieces).
        assert_eq!(spans[0].0, 0);
        assert!(spans.windows(2).all(|pair| pair[0].1 <= pair[1].0));
    }

    #[test]
    fn ct3_chunk_006_chunking_config_hash_vector() {
        assert_eq!(
            chunking_config_hash("heading", 6000).unwrap(),
            "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea"
        );
    }
}
