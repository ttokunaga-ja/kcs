//! Strict, bounded readers for the deterministic evaluation fixtures.
//!
//! The Rust generator is the source of fixture materialization, and its public
//! contract is deliberately duplicated here so an evaluator never treats a
//! stale manifest as authority.

use std::{
    collections::{BTreeSet, HashSet},
    fmt,
    path::Path,
    sync::OnceLock,
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
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

const HISTORY_OPERATION_COUNT: usize = 19;
const HISTORY_RENAME_COUNT: usize = 7;
const HISTORY_EDIT_COUNT: usize = 3;
const HISTORY_DELETE_COUNT: usize = 9;
const HISTORY_COMMIT_COUNT: usize = 48;
pub const HISTORY_PLAN_SCHEMA_VERSION: u64 = 1;
pub const HISTORY_MANIFEST_SCHEMA_VERSION: u64 = 1;
pub const HISTORY_PLAN_GENERATOR: &str = "kio-eval history-plan/v1";
pub const HISTORY_MANIFEST_GENERATOR: &str = "kio-eval replay-history/v1";
pub const CORPUS_MANIFEST_SHA256: &str =
    "sha256:10a2d87520dea212b4f3c7cdbb530b85158dbb9978f185fc343df2eefb02ec72";
/// SHA-256 of the bundled JCS JSON history plan plus exactly one LF byte.
pub const HISTORY_PLAN_SHA256: &str =
    "sha256:0e05db2483aa5de3773b9623fceb55986f28962e68c41941f3a7a132faf28370";

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

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
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

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct VerifiedHistory {
    pub steps: Vec<String>,
    pub commit_count: usize,
    pub messages: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct HistoryManifest {
    pub schema_version: u64,
    pub generator: String,
    pub plan_sha256: String,
    pub corpus_manifest_sha256: String,
    pub seed: u64,
    pub scopes: Vec<String>,
    pub verified: std::collections::BTreeMap<String, VerifiedHistory>,
}

/// The immutable, bundled source of the replay scenario.  This tagged enum is
/// intentionally closed: an unrecognized operation is a schema error rather
/// than an instruction the replay executor could silently ignore.
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum HistoryOperation {
    Edit {
        scope: String,
        file: String,
        old_value: String,
        new_value: String,
        before_raw_sha256: String,
        after_raw_sha256: String,
        sections: Vec<Section>,
    },
    Rename {
        scope: String,
        old_file: String,
        new_file: String,
        before_raw_sha256: String,
        after_raw_sha256: String,
        sections: Vec<Section>,
    },
    Delete {
        scope: String,
        file: String,
        before_raw_sha256: String,
        sections: Vec<Section>,
    },
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct HistoryPlan {
    pub corpus_manifest_sha256: String,
    pub generator: String,
    pub operations: Vec<HistoryOperation>,
    pub schema_version: u64,
    pub scopes: Vec<String>,
    pub seed: u64,
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
    parse_corpus_manifest_bytes(text.as_bytes())
}

pub fn load_history_manifest(
    path: &Path,
    corpus: &CorpusManifest,
) -> Result<HistoryManifest, ManifestError> {
    let text = bounded_utf8(path, "history manifest", MAX_MANIFEST_BYTES)?;
    parse_history_manifest_bytes(text.as_bytes(), corpus)
}

/// Parse independently acquired descriptor-bound corpus bytes.  The caller is
/// responsible for its filesystem boundary; this routine supplies only strict
/// UTF-8/JSON/schema validation.
pub fn parse_corpus_manifest_bytes(bytes: &[u8]) -> Result<CorpusManifest, ManifestError> {
    if bytes.len() as u64 > MAX_MANIFEST_BYTES {
        return Err(invalid("corpus manifest", "byte limit exceeded"));
    }
    let text = std::str::from_utf8(bytes)
        .map_err(|error| invalid("corpus manifest", format!("invalid UTF-8: {error}")))?;
    let manifest = serde_json::from_str(text)
        .map_err(|source| invalid("corpus manifest", format!("invalid JSON: {source}")))?;
    validate_corpus_manifest(&manifest)?;
    Ok(manifest)
}

/// Parse independently acquired descriptor-bound history bytes.
pub fn parse_history_manifest_bytes(
    bytes: &[u8],
    corpus: &CorpusManifest,
) -> Result<HistoryManifest, ManifestError> {
    if bytes.len() as u64 > MAX_MANIFEST_BYTES {
        return Err(invalid("history manifest", "byte limit exceeded"));
    }
    let text = std::str::from_utf8(bytes)
        .map_err(|error| invalid("history manifest", format!("invalid UTF-8: {error}")))?;
    let manifest = serde_json::from_str(text)
        .map_err(|source| invalid("history manifest", format!("invalid JSON: {source}")))?;
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
    if manifest.generator != "kio-eval generate-corpus" {
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
    if manifest.schema_version != HISTORY_MANIFEST_SCHEMA_VERSION {
        return Err(invalid("history manifest", "schema_version mismatch"));
    }
    if manifest.generator != HISTORY_MANIFEST_GENERATOR {
        return Err(invalid("history manifest", "generator identity mismatch"));
    }
    if manifest.plan_sha256 != HISTORY_PLAN_SHA256
        || manifest.corpus_manifest_sha256 != CORPUS_MANIFEST_SHA256
    {
        return Err(invalid(
            "history manifest",
            "plan or corpus digest mismatch",
        ));
    }
    let corpus_digest = format!("sha256:{}", sha256_hex(&serialize_corpus_manifest(corpus)?));
    if corpus_digest != CORPUS_MANIFEST_SHA256 {
        return Err(invalid(
            "history manifest",
            "supplied corpus manifest digest mismatch",
        ));
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
    let plan = frozen_history_plan()?;
    validate_verified_history(&manifest.verified, &plan)
}

fn validate_verified_history(
    verified: &std::collections::BTreeMap<String, VerifiedHistory>,
    plan: &HistoryPlan,
) -> Result<(), ManifestError> {
    if verified.len() != SCOPES.len()
        || verified.keys().map(String::as_str).collect::<BTreeSet<_>>()
            != SCOPES.into_iter().collect()
    {
        return Err(invalid(
            "history manifest",
            "verified scope set/order mismatch",
        ));
    }
    for scope in SCOPES {
        let value = verified.get(scope).expect("checked above");
        let steps = expected_steps(plan, scope);
        if value.steps != steps
            || value.commit_count != 2 * value.steps.len()
            || value.messages != expected_messages(plan, scope)
        {
            return Err(invalid(
                "history manifest",
                format!("verified replay mismatch: {scope}"),
            ));
        }
    }
    if verified
        .values()
        .map(|entry| entry.commit_count)
        .sum::<usize>()
        != HISTORY_COMMIT_COUNT
    {
        return Err(invalid("history manifest", "total commit count mismatch"));
    }
    Ok(())
}

/// Construct the only accepted history-manifest shape from the frozen plan and
/// execution evidence.  Callers cannot choose an identity or operation set.
pub fn build_history_manifest(
    verified: std::collections::BTreeMap<String, VerifiedHistory>,
) -> Result<HistoryManifest, ManifestError> {
    let plan = frozen_history_plan()?;
    validate_verified_history(&verified, &plan)?;
    Ok(HistoryManifest {
        schema_version: HISTORY_MANIFEST_SCHEMA_VERSION,
        generator: HISTORY_MANIFEST_GENERATOR.to_owned(),
        plan_sha256: HISTORY_PLAN_SHA256.to_owned(),
        corpus_manifest_sha256: CORPUS_MANIFEST_SHA256.to_owned(),
        seed: plan.seed,
        scopes: plan.scopes,
        verified,
    })
}

pub fn serialize_history_manifest(manifest: &HistoryManifest) -> Result<Vec<u8>, ManifestError> {
    let value = serde_json::to_value(manifest)
        .map_err(|error| invalid("history manifest", error.to_string()))?;
    let mut bytes = serde_json::to_vec_pretty(&value)
        .map_err(|error| invalid("history manifest", error.to_string()))?;
    bytes.push(b'\n');
    Ok(bytes)
}

/// Serialize a corpus manifest in the sole frozen wire representation: the
/// default sorted `serde_json::Value` map order, pretty formatting, and one LF.
pub fn serialize_corpus_manifest(manifest: &CorpusManifest) -> Result<Vec<u8>, ManifestError> {
    let value = serde_json::to_value(manifest)
        .map_err(|error| invalid("corpus manifest", error.to_string()))?;
    let mut bytes = serde_json::to_vec_pretty(&value)
        .map_err(|error| invalid("corpus manifest", error.to_string()))?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn expected_steps(plan: &HistoryPlan, scope: &str) -> Vec<String> {
    let mut steps = vec!["baseline".to_owned()];
    if plan.operations.iter().any(|operation| {
        matches!(operation, HistoryOperation::Edit { scope: operation_scope, .. } if operation_scope == scope)
    }) {
        steps.push("edit".to_owned());
    }
    if plan.operations.iter().any(|operation| {
        matches!(operation, HistoryOperation::Rename { scope: operation_scope, .. } if operation_scope == scope)
    }) {
        steps.push("rename".to_owned());
    }
    if plan.operations.iter().any(|operation| {
        matches!(operation, HistoryOperation::Delete { scope: operation_scope, .. } if operation_scope == scope)
    }) {
        steps.push("delete".to_owned());
    }
    steps
}

fn expected_messages(plan: &HistoryPlan, scope: &str) -> Vec<String> {
    let mut messages = Vec::new();
    let deleted: Vec<_> = plan
        .operations
        .iter()
        .filter_map(|operation| match operation {
            HistoryOperation::Delete {
                scope: operation_scope,
                file,
                ..
            } if operation_scope == scope => Some(file.as_str()),
            _ => None,
        })
        .collect();
    if !deleted.is_empty() {
        messages.extend([
            format!("delete: {}", deleted.join(", ")),
            "kio index auto snapshot".to_owned(),
        ]);
    }
    let renamed: Vec<_> = plan
        .operations
        .iter()
        .filter_map(|operation| match operation {
            HistoryOperation::Rename {
                scope: operation_scope,
                old_file,
                new_file,
                ..
            } if operation_scope == scope => Some(format!("{old_file}->{new_file}")),
            _ => None,
        })
        .collect();
    if !renamed.is_empty() {
        messages.extend([
            format!("rename: {}", renamed.join(", ")),
            "kio index auto snapshot".to_owned(),
        ]);
    }
    let edited: Vec<_> = plan
        .operations
        .iter()
        .filter_map(|operation| match operation {
            HistoryOperation::Edit {
                scope: operation_scope,
                file,
                ..
            } if operation_scope == scope => Some(file.as_str()),
            _ => None,
        })
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
            return Err(format!("required flag missing: {flag}"));
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

impl fmt::Display for Scenario {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Load and validate the bundled, JCS-plus-LF plan.  Its digest is a Rust
/// constant rather than a mutable fixture field, so a coordinated edit to a
/// plan and a manifest cannot grant itself authority.
pub fn frozen_history_plan() -> Result<HistoryPlan, ManifestError> {
    static FROZEN: OnceLock<Result<HistoryPlan, String>> = OnceLock::new();
    FROZEN
        .get_or_init(|| {
            let bytes = include_bytes!("../../../eval/history-plan.json");
            let digest = format!(
                "sha256:{}",
                Sha256::digest(bytes)
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect::<String>()
            );
            if digest != HISTORY_PLAN_SHA256 {
                return Err(format!("frozen history plan digest mismatch: {digest}"));
            }
            let plan: HistoryPlan = serde_json::from_slice(bytes)
                .map_err(|error| format!("invalid frozen history plan JSON: {error}"))?;
            validate_history_plan(&plan).map_err(|error| error.to_string())?;
            validate_frozen_edit_hashes(&plan).map_err(|error| error.to_string())?;
            let encoded = canonical_history_plan_bytes(&plan).map_err(|error| error.to_string())?;
            if encoded != bytes {
                return Err("frozen history plan is not canonical JCS+LF".to_owned());
            }
            Ok(plan)
        })
        .clone()
        .map_err(|message| invalid("history plan", message))
}

fn validate_frozen_edit_hashes(plan: &HistoryPlan) -> Result<(), ManifestError> {
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct FixtureContent {
        scope: String,
        file: String,
        content: String,
    }
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Fixture {
        contents: Vec<FixtureContent>,
        manifest: CorpusManifest,
        manifest_sha256: String,
        schema_version: u64,
    }

    let fixture: Fixture = serde_json::from_str(include_str!("../../../eval/corpus-fixture.json"))
        .map_err(|error| {
            invalid(
                "history plan",
                format!("invalid frozen corpus fixture: {error}"),
            )
        })?;
    if fixture.schema_version != 1
        || fixture.manifest_sha256 != CORPUS_MANIFEST_SHA256.trim_start_matches("sha256:")
    {
        return Err(invalid(
            "history plan",
            "frozen corpus fixture identity mismatch",
        ));
    }
    validate_corpus_manifest(&fixture.manifest)?;
    for operation in &plan.operations {
        let HistoryOperation::Edit {
            scope,
            file,
            old_value,
            new_value,
            before_raw_sha256,
            after_raw_sha256,
            ..
        } = operation
        else {
            continue;
        };
        let source = fixture
            .contents
            .iter()
            .find(|entry| entry.scope == *scope && entry.file == *file)
            .ok_or_else(|| {
                invalid(
                    "history plan",
                    format!("edit source absent: {scope}/{file}"),
                )
            })?;
        if sha256_hex(source.content.as_bytes()) != *before_raw_sha256
            || source.content.matches(old_value).count() != 1
        {
            return Err(invalid(
                "history plan",
                format!("edit precondition mismatch: {scope}/{file}"),
            ));
        }
        let replaced = source.content.replacen(old_value, new_value, 1);
        if sha256_hex(replaced.as_bytes()) != *after_raw_sha256 {
            return Err(invalid(
                "history plan",
                format!("edit after hash mismatch: {scope}/{file}"),
            ));
        }
    }
    Ok(())
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub fn validate_history_plan(plan: &HistoryPlan) -> Result<(), ManifestError> {
    if plan.schema_version != HISTORY_PLAN_SCHEMA_VERSION
        || plan.generator != HISTORY_PLAN_GENERATOR
    {
        return Err(invalid(
            "history plan",
            "schema_version or generator mismatch",
        ));
    }
    if plan.corpus_manifest_sha256 != CORPUS_MANIFEST_SHA256 || plan.seed != SEED {
        return Err(invalid("history plan", "corpus digest or seed mismatch"));
    }
    if plan.scopes.iter().map(String::as_str).collect::<Vec<_>>() != SCOPES {
        return Err(invalid("history plan", "scope order/set mismatch"));
    }
    if plan.operations.len() != HISTORY_OPERATION_COUNT {
        return Err(invalid("history plan", "operation count mismatch"));
    }
    let mut edit_count = 0;
    let mut rename_count = 0;
    let mut delete_count = 0;
    let mut seen = HashSet::new();
    let mut order = Vec::new();
    for operation in &plan.operations {
        match operation {
            HistoryOperation::Edit {
                scope,
                file,
                old_value,
                new_value,
                before_raw_sha256,
                after_raw_sha256,
                sections,
            } => {
                edit_count += 1;
                validate_history_operation(scope, file, before_raw_sha256, sections)?;
                validate_hash(after_raw_sha256, "history plan")?;
                if old_value.is_empty() || new_value.is_empty() || old_value == new_value {
                    return Err(invalid("history plan", "invalid edit values"));
                }
                if !seen.insert(("edit", scope, file)) {
                    return Err(invalid("history plan", "duplicate operation"));
                }
                order.push((scope_rank(scope)?, 0_u8, file.as_str()));
            }
            HistoryOperation::Rename {
                scope,
                old_file,
                new_file,
                before_raw_sha256,
                after_raw_sha256,
                sections,
            } => {
                rename_count += 1;
                validate_history_operation(scope, old_file, before_raw_sha256, sections)?;
                validate_flat_file(new_file, "history plan")?;
                validate_hash(after_raw_sha256, "history plan")?;
                if before_raw_sha256 != after_raw_sha256
                    || old_file == new_file
                    || !seen.insert(("rename", scope, old_file))
                {
                    return Err(invalid("history plan", "invalid rename operation"));
                }
                order.push((scope_rank(scope)?, 1_u8, old_file.as_str()));
            }
            HistoryOperation::Delete {
                scope,
                file,
                before_raw_sha256,
                sections,
            } => {
                delete_count += 1;
                validate_history_operation(scope, file, before_raw_sha256, sections)?;
                if !seen.insert(("delete", scope, file)) {
                    return Err(invalid("history plan", "duplicate operation"));
                }
                order.push((scope_rank(scope)?, 2_u8, file.as_str()));
            }
        }
    }
    if (edit_count, rename_count, delete_count)
        != (
            HISTORY_EDIT_COUNT,
            HISTORY_RENAME_COUNT,
            HISTORY_DELETE_COUNT,
        )
    {
        return Err(invalid("history plan", "operation type count mismatch"));
    }
    // The canonical byte digest fixes the exact list order.  The rank check
    // below additionally rejects cross-scope or cross-operation reordering
    // before an executor observes the plan.
    let mut previous: Option<(usize, u8, &str)> = None;
    for item in order {
        if previous.is_some_and(|prior| prior.0 > item.0 || (prior.0 == item.0 && prior.1 > item.1))
        {
            return Err(invalid("history plan", "operation order mismatch"));
        }
        previous = Some(item);
    }
    Ok(())
}

fn scope_rank(scope: &str) -> Result<usize, ManifestError> {
    SCOPES
        .iter()
        .position(|candidate| *candidate == scope)
        .ok_or_else(|| invalid("history plan", "unknown scope"))
}

fn validate_history_operation(
    scope: &str,
    file: &str,
    hash: &str,
    sections: &[Section],
) -> Result<(), ManifestError> {
    if !SCOPES.contains(&scope) {
        return Err(invalid("history plan", "unknown scope"));
    }
    validate_flat_file(file, "history plan")?;
    validate_hash(hash, "history plan")?;
    validate_sections(sections, "history plan")
}

/// Serialize a plan as its frozen JCS object form with a terminating LF.
pub fn canonical_history_plan_bytes(plan: &HistoryPlan) -> Result<Vec<u8>, ManifestError> {
    let mut bytes = serde_jcs::to_vec(plan).map_err(|e| invalid("history plan", e.to_string()))?;
    bytes.push(b'\n');
    Ok(bytes)
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::{
        HistoryManifest, HistoryOperation, HistoryPlan, MAX_GOLDEN_QUERIES, build_history_manifest,
        frozen_history_plan, load_golden_queries, parse_corpus_manifest_bytes,
        parse_history_manifest_bytes, serialize_history_manifest, validate_history_plan,
    };

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

    #[test]
    fn bundled_history_plan_is_frozen_canonical_and_complete() {
        let plan = frozen_history_plan().unwrap();
        assert_eq!(plan.operations.len(), 19);
        assert_eq!(plan.scopes.len(), 7);
    }

    #[test]
    fn history_plan_rejects_duplicate_operation_and_traversal() {
        let mut plan = frozen_history_plan().unwrap();
        plan.operations.push(plan.operations[0].clone());
        assert!(validate_history_plan(&plan).is_err());
        let mut plan: HistoryPlan = frozen_history_plan().unwrap();
        if let super::HistoryOperation::Edit { file, .. } = &mut plan.operations[0] {
            *file = "../escape.md".to_owned();
        }
        assert!(validate_history_plan(&plan).is_err());
    }

    #[test]
    fn checked_history_manifest_is_the_exact_current_serialization() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../eval/corpus-fixture.json")).unwrap();
        let corpus =
            parse_corpus_manifest_bytes(&serde_json::to_vec(&fixture["manifest"]).unwrap())
                .unwrap();
        let bytes = include_bytes!("../../../eval/history-manifest.json");
        let manifest = parse_history_manifest_bytes(bytes, &corpus).unwrap();
        let encoded = serialize_history_manifest(&manifest).unwrap();
        assert_eq!(encoded, bytes);
    }

    #[test]
    fn history_manifest_rejects_a_different_supplied_corpus() {
        let (mut corpus, manifest) = checked_manifest();
        corpus.files[0].raw_sha256 = "0".repeat(64);
        assert!(
            parse_history_manifest_bytes(&serialize_history_manifest(&manifest).unwrap(), &corpus,)
                .is_err()
        );
    }

    fn checked_manifest() -> (super::CorpusManifest, HistoryManifest) {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../eval/corpus-fixture.json")).unwrap();
        let corpus =
            parse_corpus_manifest_bytes(&serde_json::to_vec(&fixture["manifest"]).unwrap())
                .unwrap();
        let manifest = parse_history_manifest_bytes(
            include_bytes!("../../../eval/history-manifest.json"),
            &corpus,
        )
        .unwrap();
        (corpus, manifest)
    }

    #[test]
    fn history_manifest_rejects_old_identity_unknown_and_operation_fields() {
        let (corpus, manifest) = checked_manifest();
        for mutator in [
            |value: &mut serde_json::Value| {
                value["generator"] = serde_json::json!("legacy-python-replay/v0")
            },
            |value: &mut serde_json::Value| value["schema_version"] = serde_json::json!(0),
            |value: &mut serde_json::Value| value["plan_sha256"] = serde_json::json!("sha256:00"),
            |value: &mut serde_json::Value| {
                value["corpus_manifest_sha256"] = serde_json::json!("sha256:00")
            },
            |value: &mut serde_json::Value| {
                value["unknown"] = serde_json::json!(true);
            },
            |value: &mut serde_json::Value| {
                value["deleted"] = serde_json::json!([]);
            },
        ] {
            let mut value = serde_json::to_value(&manifest).unwrap();
            mutator(&mut value);
            assert!(
                parse_history_manifest_bytes(&serde_json::to_vec(&value).unwrap(), &corpus)
                    .is_err()
            );
        }
    }

    #[test]
    fn history_plan_rejects_absolute_duplicate_and_reordered_operations() {
        let plan = frozen_history_plan().unwrap();
        let mut absolute = plan.clone();
        if let HistoryOperation::Edit { file, .. } = &mut absolute.operations[0] {
            *file = "/escape.md".into();
        }
        assert!(validate_history_plan(&absolute).is_err());
        let mut duplicate = plan.clone();
        duplicate.operations[1] = duplicate.operations[0].clone();
        assert!(validate_history_plan(&duplicate).is_err());
        let mut reordered = plan;
        reordered.operations.swap(0, 3);
        assert!(validate_history_plan(&reordered).is_err());
    }

    #[test]
    fn builder_rejects_incomplete_or_forged_evidence() {
        let (_, manifest) = checked_manifest();
        let mut missing = manifest.verified.clone();
        missing.remove("journal");
        assert!(build_history_manifest(missing).is_err());
        let mut wrong = manifest.verified.clone();
        wrong.get_mut("research").unwrap().messages[0] = "forged".into();
        assert!(build_history_manifest(wrong).is_err());
        let mut wrong_steps = manifest.verified.clone();
        wrong_steps.get_mut("research").unwrap().steps.pop();
        assert!(build_history_manifest(wrong_steps).is_err());
        let mut wrong_total = manifest.verified.clone();
        wrong_total.get_mut("research").unwrap().commit_count = 7;
        assert!(build_history_manifest(wrong_total).is_err());
        assert!(build_history_manifest(manifest.verified).is_ok());
    }
}
