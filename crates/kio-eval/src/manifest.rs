//! Strict, bounded readers for the deterministic evaluation fixtures.
//!
//! The Python generators remain the source of fixture bytes during the
//! transition, but their public contract is deliberately duplicated here so
//! an evaluator never treats a stale manifest as authority.

use std::{
    collections::{BTreeSet, HashSet},
    fmt,
    path::Path,
    sync::OnceLock,
};

use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const SEED: u64 = 20_260_703;
pub const SCOPES: [&str; 7] = [
    "research",
    "notes",
    "downloads",
    "projects-a",
    "projects-b",
    "specs",
    "journal",
];
pub const CORPUS_FILE_COUNT: usize = 305;
pub const CORPUS_ANCHOR_COUNT: usize = 31;
pub const MAX_MANIFEST_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_GOLDEN_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_GOLDEN_LINE_BYTES: usize = 1024 * 1024;
/// The frozen M3 suite has 50 records; smaller scenario subsets are allowed.
pub const MAX_GOLDEN_QUERIES: usize = 50;

const RENAMES: [(&str, &str, &str); 7] = [
    ("research", "auth-spec.md", "authentication-guide.md"),
    ("notes", "vendor-eval.md", "supplier-assessment.md"),
    ("downloads", "rag-pipeline.md", "retrieval-pipeline.md"),
    (
        "projects-a",
        "falcon-migration.md",
        "falcon-cutover-plan.md",
    ),
    (
        "projects-b",
        "kestrel-security.md",
        "kestrel-threat-model.md",
    ),
    (
        "specs",
        "evidence-pointer-spec.md",
        "evidence-pointer-contract.md",
    ),
    ("journal", "interview-notes.md", "user-research-summary.md"),
];
const EDITS: [(&str, &str, &str, &str); 3] = [
    (
        "research",
        "model-selection.md",
        "一次選定では Harrier を採用、暫定スコア 0.71 とした。",
        "最終選定では Condor を採用、確定スコア 0.79 とした。",
    ),
    (
        "notes",
        "budget-review.md",
        "レビュー時点の合計予算は 750万円 と報告された。",
        "改定後の合計予算は 920万円 と報告された。",
    ),
    (
        "downloads",
        "benchmark-draft.md",
        "Tsubame 構成の暫定スコアは 0.71 だった。",
        "Tsubame 構成の確定スコアは 0.79 だった。",
    ),
];
const DELETES: [(&str, &str); 9] = [
    ("research", "deprecated-approach.md"),
    ("notes", "cancelled-project-osprey.md"),
    ("downloads", "old-api-limits.md"),
    ("downloads", "leaked-draft-pricing.md"),
    ("projects-a", "falcon-incident-0421.md"),
    ("projects-a", "falcon-old-schema.md"),
    ("projects-b", "kestrel-poc-metrics.md"),
    ("specs", "legacy-format-v0.md"),
    ("journal", "scratch-numbers.md"),
];

#[derive(Debug, Error)]
pub enum ManifestError {
    #[error("{label} exceeds the {limit} byte limit: {path}")]
    TooLarge {
        label: &'static str,
        limit: u64,
        path: String,
    },
    #[error("cannot read {label} {path}: {source}")]
    Read {
        label: &'static str,
        path: String,
        source: std::io::Error,
    },
    #[error("invalid UTF-8 in {label} {path}: {source}")]
    Utf8 {
        label: &'static str,
        path: String,
        source: std::string::FromUtf8Error,
    },
    #[error("invalid {label} JSON in {path}: {source}")]
    Json {
        label: &'static str,
        path: String,
        source: serde_json::Error,
    },
    #[error("invalid {0}: {1}")]
    Invalid(&'static str, String),
}

fn bounded_utf8(path: &Path, label: &'static str, limit: u64) -> Result<String, ManifestError> {
    let bytes = kio_core::cas::read_bounded_regular_file(path, limit)
        .map_err(|error| invalid(label, format!("cannot read {}: {error}", path.display())))?;
    String::from_utf8(bytes).map_err(|source| ManifestError::Utf8 {
        label,
        path: path.display().to_string(),
        source,
    })
}

fn invalid(kind: &'static str, message: impl Into<String>) -> ManifestError {
    ManifestError::Invalid(kind, message.into())
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Section {
    pub slug: String,
    pub heading: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CorpusFile {
    pub scope: String,
    pub file: String,
    pub kind: String,
    pub anchor: bool,
    pub role: String,
    pub sections: Vec<Section>,
    pub raw_sha256: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CorpusManifest {
    pub generator: String,
    pub seed: u64,
    pub scopes: Vec<String>,
    pub file_count: usize,
    pub anchor_count: usize,
    pub files: Vec<CorpusFile>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Renamed {
    pub scope: String,
    pub old_file: String,
    pub new_file: String,
    pub raw_sha256: String,
    pub sections: Vec<Section>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Edited {
    pub scope: String,
    pub file: String,
    pub old_value: String,
    pub new_value: String,
    pub raw_sha256: String,
    pub sections: Vec<Section>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Deleted {
    pub scope: String,
    pub file: String,
    pub raw_sha256: String,
    pub sections: Vec<Section>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VerifiedHistory {
    pub steps: Vec<String>,
    pub commit_count: usize,
    pub messages: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HistoryManifest {
    pub replay: String,
    pub seed: u64,
    pub scopes: Vec<String>,
    pub renamed: Vec<Renamed>,
    pub edited: Vec<Edited>,
    pub deleted: Vec<Deleted>,
    pub verified: std::collections::BTreeMap<String, VerifiedHistory>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum Scenario {
    #[serde(rename = "M3-1")]
    M3_1,
    #[serde(rename = "M3-2")]
    M3_2,
    #[serde(rename = "M3-3")]
    M3_3,
}

impl Scenario {
    pub const ALL: [Self; 3] = [Self::M3_1, Self::M3_2, Self::M3_3];

    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::M3_1 => "M3-1",
            Self::M3_2 => "M3-2",
            Self::M3_3 => "M3-3",
        }
    }

    #[must_use]
    pub const fn required_flag(self) -> Option<&'static str> {
        match self {
            Self::M3_1 => None,
            Self::M3_2 => Some("--all-history"),
            Self::M3_3 => Some("--include-deleted"),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Expected {
    pub scope: String,
    pub file: String,
    pub section: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GoldenQuery {
    pub scenario: Scenario,
    pub query: String,
    #[serde(default)]
    pub flags: Vec<String>,
    pub expected: Vec<Expected>,
}

pub fn load_corpus_manifest(path: &Path) -> Result<CorpusManifest, ManifestError> {
    let text = bounded_utf8(path, "corpus manifest", MAX_MANIFEST_BYTES)?;
    let manifest = serde_json::from_str(&text).map_err(|source| ManifestError::Json {
        label: "corpus manifest",
        path: path.display().to_string(),
        source,
    })?;
    validate_corpus_manifest(&manifest)?;
    Ok(manifest)
}

pub fn load_history_manifest(
    path: &Path,
    corpus: &CorpusManifest,
) -> Result<HistoryManifest, ManifestError> {
    let text = bounded_utf8(path, "history manifest", MAX_MANIFEST_BYTES)?;
    let manifest = serde_json::from_str(&text).map_err(|source| ManifestError::Json {
        label: "history manifest",
        path: path.display().to_string(),
        source,
    })?;
    validate_history_manifest(&manifest, corpus)?;
    Ok(manifest)
}

pub fn load_golden_queries(path: &Path) -> Result<Vec<GoldenQuery>, ManifestError> {
    let text = bounded_utf8(path, "golden queries", MAX_GOLDEN_BYTES)?;
    let mut queries = Vec::new();
    for (index, raw) in text.lines().enumerate() {
        if raw.trim().is_empty() {
            continue;
        }
        if raw.len() > MAX_GOLDEN_LINE_BYTES {
            return Err(invalid(
                "golden queries",
                format!("line {} exceeds byte limit", index + 1),
            ));
        }
        let query = serde_json::from_str(raw).map_err(|source| ManifestError::Json {
            label: "golden query",
            path: format!("{}:{}", path.display(), index + 1),
            source,
        })?;
        validate_golden_shape(&query)
            .map_err(|message| invalid("golden query", format!("line {}: {message}", index + 1)))?;
        queries.push(query);
        if queries.len() > MAX_GOLDEN_QUERIES {
            return Err(invalid(
                "golden queries",
                format!("record count exceeds {MAX_GOLDEN_QUERIES}"),
            ));
        }
    }
    if queries.is_empty() {
        return Err(invalid("golden queries", "no query records"));
    }
    Ok(queries)
}

pub fn validate_corpus_manifest(manifest: &CorpusManifest) -> Result<(), ManifestError> {
    if manifest.generator != "eval/generate_corpus.py" {
        return Err(invalid("corpus manifest", "generator identity mismatch"));
    }
    if manifest.seed != SEED {
        return Err(invalid("corpus manifest", "seed mismatch"));
    }
    if manifest
        .scopes
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>()
        != SCOPES
    {
        return Err(invalid("corpus manifest", "scope order/set mismatch"));
    }
    if manifest.file_count != CORPUS_FILE_COUNT || manifest.anchor_count != CORPUS_ANCHOR_COUNT {
        return Err(invalid(
            "corpus manifest",
            "frozen file or anchor count mismatch",
        ));
    }
    if manifest.files.len() != manifest.file_count {
        return Err(invalid(
            "corpus manifest",
            "file_count does not match files length",
        ));
    }
    if manifest.files.iter().filter(|entry| entry.anchor).count() != manifest.anchor_count {
        return Err(invalid(
            "corpus manifest",
            "anchor_count does not match files",
        ));
    }
    let mut keys = HashSet::new();
    for entry in &manifest.files {
        validate_file(entry)?;
        if !keys.insert((&entry.scope, &entry.file)) {
            return Err(invalid(
                "corpus manifest",
                format!("duplicate file: {}/{}", entry.scope, entry.file),
            ));
        }
    }
    Ok(())
}

fn validate_file(entry: &CorpusFile) -> Result<(), ManifestError> {
    if !SCOPES.contains(&entry.scope.as_str()) {
        return Err(invalid(
            "corpus manifest",
            format!("unknown scope: {}", entry.scope),
        ));
    }
    validate_flat_file(&entry.file, "corpus manifest")?;
    if !matches!(entry.kind.as_str(), "md" | "txt" | "pdf") {
        return Err(invalid(
            "corpus manifest",
            format!("unsupported kind: {}", entry.kind),
        ));
    }
    if entry.anchor && !entry.role.starts_with("m3_") {
        return Err(invalid(
            "corpus manifest",
            format!("anchor role mismatch: {}", entry.role),
        ));
    }
    if !entry.anchor && entry.role != "filler" {
        return Err(invalid(
            "corpus manifest",
            format!("filler role mismatch: {}", entry.role),
        ));
    }
    validate_hash(&entry.raw_sha256, "corpus manifest")?;
    validate_sections(&entry.sections, "corpus manifest")
}

fn validate_history_manifest(
    manifest: &HistoryManifest,
    corpus: &CorpusManifest,
) -> Result<(), ManifestError> {
    if manifest.replay != "eval/replay_history.py" {
        return Err(invalid("history manifest", "replay identity mismatch"));
    }
    if manifest.seed != SEED {
        return Err(invalid("history manifest", "seed mismatch"));
    }
    if manifest
        .scopes
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>()
        != SCOPES
    {
        return Err(invalid("history manifest", "scope order/set mismatch"));
    }
    if manifest.renamed.len() != RENAMES.len()
        || manifest.edited.len() != EDITS.len()
        || manifest.deleted.len() != DELETES.len()
    {
        return Err(invalid("history manifest", "operation count mismatch"));
    }
    let frozen = frozen_history();
    let original: std::collections::HashMap<_, _> = corpus
        .files
        .iter()
        .map(|entry| ((entry.scope.as_str(), entry.file.as_str()), entry))
        .collect();
    for ((actual, expected), frozen) in manifest.renamed.iter().zip(RENAMES).zip(&frozen.renamed) {
        if (
            actual.scope.as_str(),
            actual.old_file.as_str(),
            actual.new_file.as_str(),
        ) != expected
        {
            return Err(invalid(
                "history manifest",
                "renamed operation order mismatch",
            ));
        }
        validate_history_material(
            &original,
            &actual.scope,
            &actual.old_file,
            &actual.raw_sha256,
            &actual.sections,
        )?;
        validate_flat_file(&actual.new_file, "history manifest")?;
        if actual.raw_sha256 != frozen.raw_sha256
            || !same_sections(&actual.sections, &frozen.sections)
        {
            return Err(invalid(
                "history manifest",
                format!(
                    "frozen renamed material mismatch: {}/{}",
                    actual.scope, actual.old_file
                ),
            ));
        }
    }
    for ((actual, expected), frozen) in manifest.edited.iter().zip(EDITS).zip(&frozen.edited) {
        if (
            actual.scope.as_str(),
            actual.file.as_str(),
            actual.old_value.as_str(),
            actual.new_value.as_str(),
        ) != expected
        {
            return Err(invalid(
                "history manifest",
                "edited operation order mismatch",
            ));
        }
        validate_history_material(
            &original,
            &actual.scope,
            &actual.file,
            &actual.raw_sha256,
            &actual.sections,
        )?;
        if actual.raw_sha256 != frozen.raw_sha256
            || !same_sections(&actual.sections, &frozen.sections)
        {
            return Err(invalid(
                "history manifest",
                format!(
                    "frozen edited material mismatch: {}/{}",
                    actual.scope, actual.file
                ),
            ));
        }
    }
    for ((actual, expected), frozen) in manifest.deleted.iter().zip(DELETES).zip(&frozen.deleted) {
        if (actual.scope.as_str(), actual.file.as_str()) != expected {
            return Err(invalid(
                "history manifest",
                "deleted operation order mismatch",
            ));
        }
        validate_history_material(
            &original,
            &actual.scope,
            &actual.file,
            &actual.raw_sha256,
            &actual.sections,
        )?;
        if actual.raw_sha256 != frozen.raw_sha256
            || !same_sections(&actual.sections, &frozen.sections)
        {
            return Err(invalid(
                "history manifest",
                format!(
                    "frozen deleted material mismatch: {}/{}",
                    actual.scope, actual.file
                ),
            ));
        }
    }
    if manifest.verified.len() != SCOPES.len()
        || manifest
            .verified
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            != SCOPES.into_iter().collect()
    {
        return Err(invalid(
            "history manifest",
            "verified scope set/order mismatch",
        ));
    }
    for scope in SCOPES {
        let value = manifest.verified.get(scope).expect("checked above");
        let steps = expected_steps(scope);
        if value.steps != steps
            || value.commit_count != 2 * value.steps.len()
            || value.messages != expected_messages(scope)
        {
            return Err(invalid(
                "history manifest",
                format!("verified replay mismatch: {scope}"),
            ));
        }
        if value.steps != frozen.verified[scope].steps
            || value.commit_count != frozen.verified[scope].commit_count
            || value.messages != frozen.verified[scope].messages
        {
            return Err(invalid(
                "history manifest",
                format!("frozen verified mismatch: {scope}"),
            ));
        }
    }
    Ok(())
}

fn validate_history_material<'a>(
    original: &std::collections::HashMap<(&'a str, &'a str), &'a CorpusFile>,
    scope: &str,
    file: &str,
    hash: &str,
    sections: &[Section],
) -> Result<(), ManifestError> {
    let Some(source) = original.get(&(scope, file)) else {
        return Err(invalid(
            "history manifest",
            format!("history source absent from corpus: {scope}/{file}"),
        ));
    };
    if !source.anchor || source.raw_sha256 != hash || !same_sections(&source.sections, sections) {
        return Err(invalid(
            "history manifest",
            format!("stale old content: {scope}/{file}"),
        ));
    }
    Ok(())
}

fn expected_steps(scope: &str) -> Vec<String> {
    let mut steps = vec!["baseline".to_owned()];
    if EDITS.iter().any(|item| item.0 == scope) {
        steps.push("edit".to_owned());
    }
    if RENAMES.iter().any(|item| item.0 == scope) {
        steps.push("rename".to_owned());
    }
    if DELETES.iter().any(|item| item.0 == scope) {
        steps.push("delete".to_owned());
    }
    steps
}

fn expected_messages(scope: &str) -> Vec<String> {
    let mut messages = Vec::new();
    let deleted: Vec<_> = DELETES
        .iter()
        .filter(|item| item.0 == scope)
        .map(|item| item.1)
        .collect();
    if !deleted.is_empty() {
        messages.extend([
            format!("delete: {}", deleted.join(", ")),
            "kio index auto snapshot".to_owned(),
        ]);
    }
    let renamed: Vec<_> = RENAMES
        .iter()
        .filter(|item| item.0 == scope)
        .map(|item| format!("{}->{}", item.1, item.2))
        .collect();
    if !renamed.is_empty() {
        messages.extend([
            format!("rename: {}", renamed.join(", ")),
            "kio index auto snapshot".to_owned(),
        ]);
    }
    let edited: Vec<_> = EDITS
        .iter()
        .filter(|item| item.0 == scope)
        .map(|item| item.1)
        .collect();
    if !edited.is_empty() {
        messages.extend([
            format!("edit: {}", edited.join(", ")),
            "kio index auto snapshot".to_owned(),
        ]);
    }
    messages.extend(["baseline".to_owned(), "kio index auto snapshot".to_owned()]);
    messages
}

fn validate_golden_shape(query: &GoldenQuery) -> Result<(), String> {
    if query.query.trim().is_empty() {
        return Err("query is empty".to_owned());
    }
    if query.expected.is_empty() {
        return Err("expected is empty".to_owned());
    }
    match query.scenario.required_flag() {
        None if !query.flags.is_empty() => return Err("M3-1 must have no flags".to_owned()),
        Some(flag) if !query.flags.iter().any(|actual| actual == flag) => {
            return Err(format!("required flag missing: {flag}"))
        }
        _ => {}
    }
    if query
        .flags
        .iter()
        .any(|flag| !matches!(flag.as_str(), "--all-history" | "--include-deleted"))
    {
        return Err("unknown flag".to_owned());
    }
    if query.flags.iter().collect::<HashSet<_>>().len() != query.flags.len() {
        return Err("duplicate flag".to_owned());
    }
    for expected in &query.expected {
        if !SCOPES.contains(&expected.scope.as_str()) {
            return Err(format!("unknown scope: {}", expected.scope));
        }
        validate_flat_file(&expected.file, "golden query").map_err(|error| error.to_string())?;
        if expected.section.is_empty() {
            return Err("empty section mnemonic".to_owned());
        }
    }
    Ok(())
}

fn validate_flat_file(file: &str, kind: &'static str) -> Result<(), ManifestError> {
    if file.is_empty()
        || file == "."
        || file == ".."
        || file.contains(['/', '\\'])
        || file.contains("..")
    {
        return Err(invalid(kind, format!("not a flat file name: {file}")));
    }
    Ok(())
}

fn validate_hash(hash: &str, kind: &'static str) -> Result<(), ManifestError> {
    if hash.len() != 64
        || !hash
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(invalid(kind, "raw_sha256 is not lowercase hex"));
    }
    Ok(())
}

fn validate_sections(sections: &[Section], kind: &'static str) -> Result<(), ManifestError> {
    let mut slugs = HashSet::new();
    for section in sections {
        if section.slug.is_empty() || section.heading.is_empty() || !slugs.insert(&section.slug) {
            return Err(invalid(kind, "invalid or duplicate section"));
        }
    }
    Ok(())
}

fn same_sections(left: &[Section], right: &[Section]) -> bool {
    left.len() == right.len()
        && left
            .iter()
            .zip(right)
            .all(|(a, b)| a.slug == b.slug && a.heading == b.heading)
}

impl fmt::Display for Scenario {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// A checked-in generator output is an independent, reviewable freeze of the
/// rendered historical bytes. It prevents a corpus manifest and a supplied
/// history manifest from authorizing one another after a coordinated edit.
fn frozen_history() -> &'static HistoryManifest {
    static FROZEN: OnceLock<HistoryManifest> = OnceLock::new();
    FROZEN.get_or_init(|| {
        serde_json::from_str(include_str!("../../../eval/history-manifest.json"))
            .expect("checked-in history manifest must match its strict Rust schema")
    })
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::{load_golden_queries, MAX_GOLDEN_QUERIES};

    #[test]
    fn golden_query_count_is_bounded_before_execution() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("golden.jsonl");
        let record = r#"{"scenario":"M3-1","query":"bounded","flags":[],"expected":[{"scope":"research","file":"a.md","section":"fact"}]}"#;
        fs::write(
            &path,
            std::iter::repeat_n(record, MAX_GOLDEN_QUERIES + 1)
                .collect::<Vec<_>>()
                .join("\n"),
        )
        .unwrap();
        let error = load_golden_queries(&path).unwrap_err().to_string();
        assert!(error.contains("record count exceeds 50"));
    }
}
