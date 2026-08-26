//! Frozen, typed contract for the Rust-owned scale fixture.
//!
//! This module deliberately describes the fixture rather than inspecting a
//! fixture supplied by a caller.  A parsed manifest must be byte-canonical and
//! equal to the one rebuilt here; a self-consistent but reordered manifest is
//! therefore not authority.

use serde::{Deserialize, Serialize};
use thiserror::Error;

use kio_core::cas::{canonical_json_bytes, hash_bytes};

pub const SCHEMA_VERSION: u64 = 3;
pub const FIXTURE_ID: &str = "kio-scale-v3";
pub const GENERATOR_ID: &str = "kio-eval scale generate/v3";
pub const PREPARER_ID: &str = "kio-eval scale prepare/v3";
pub const ATTESTOR_ID: &str = "kio-eval scale attest/v3";
pub const SEED: u64 = 20_260_713;
pub const WORKLOAD: &str = "exact-reference-v1";
pub const MANIFEST_NAME: &str = "scale-corpus-manifest.json";
pub const OWNER_MARKER_NAME: &str = ".kio-scale-owner.json";
pub const LOCK_NAME: &str = ".kio-scale.lock";
pub const ATTESTATION_NAME: &str = "scale-attestation.json";
pub const PREPARE_REPORT_NAME: &str = "scale-prepare-report.json";
pub const DEVICE_DIR_NAME: &str = ".kio-eval-device";
pub const CHUNKING_STRATEGY: &str = "heading";
pub const CHUNKING_MAX_CHARS: usize = 6_000;
pub const CHUNKING_CONFIG_HASH: &str =
    "sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea";
pub const SCOPE_COUNT: usize = 20;
pub const MAX_FILES: usize = 4_000;
pub const MAX_CHUNKS: usize = 120_000;
pub const MAX_SOURCE_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_MANIFEST_BYTES: usize = 4 * 1024 * 1024;
pub const MAX_OWNER_BYTES: usize = 64 * 1024;

/// SHA-256 of the exact JCS-plus-LF frozen manifest for [`ScaleProfile::Tiny`].
pub const TINY_CURRENT_TEXT_MANIFEST_HASH: &str =
    "sha256:c616b93da1bfbecdfb50a5abd703bb1bc756fbc9f65e2d139df7170c008d0a24";
pub const TINY_HISTORY_OVERLAY_MANIFEST_HASH: &str =
    "sha256:1148f3f4717959f8227e99443d06551e909379db2be684771f61a841f407a695";
/// SHA-256 of the exact JCS-plus-LF frozen manifest for [`ScaleProfile::Full`].
pub const FULL_CURRENT_TEXT_MANIFEST_HASH: &str =
    "sha256:c39b4575f92b857d628b8d426894e02beee73801cba80948984de167632ae69f";
pub const FULL_HISTORY_OVERLAY_MANIFEST_HASH: &str =
    "sha256:0f34f7fd93900df459a978bdcb78b6e30341994c72c2e719a3e4b380b9288360";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, clap::ValueEnum)]
#[serde(rename_all = "lowercase")]
pub enum ScaleProfile {
    Tiny,
    Full,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, clap::ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum ScaleLane {
    CurrentText,
    HistoryOverlay,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceState {
    Base,
    Overlay,
}

impl ScaleProfile {
    #[must_use]
    pub const fn files_per_scope(self) -> usize {
        match self {
            Self::Tiny => 3,
            Self::Full => 200,
        }
    }

    #[must_use]
    pub const fn sections_per_file(self) -> usize {
        match self {
            Self::Tiny => 3,
            Self::Full => 30,
        }
    }

    #[must_use]
    pub const fn body_chars(self) -> usize {
        match self {
            Self::Tiny => 420,
            Self::Full => 1_800,
        }
    }

    #[must_use]
    pub const fn expected_files(self) -> usize {
        SCOPE_COUNT * self.files_per_scope()
    }

    #[must_use]
    pub const fn expected_chunks(self) -> usize {
        self.expected_files() * self.sections_per_file()
    }

    #[must_use]
    pub const fn minimum_current_chunks(self) -> usize {
        match self {
            Self::Tiny => self.expected_chunks(),
            Self::Full => 100_001,
        }
    }

    #[must_use]
    pub const fn frozen_manifest_hash(self, lane: ScaleLane) -> &'static str {
        match (self, lane) {
            (Self::Tiny, ScaleLane::CurrentText) => TINY_CURRENT_TEXT_MANIFEST_HASH,
            (Self::Tiny, ScaleLane::HistoryOverlay) => TINY_HISTORY_OVERLAY_MANIFEST_HASH,
            (Self::Full, ScaleLane::CurrentText) => FULL_CURRENT_TEXT_MANIFEST_HASH,
            (Self::Full, ScaleLane::HistoryOverlay) => FULL_HISTORY_OVERLAY_MANIFEST_HASH,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct ScopeDefinition {
    pub name: &'static str,
    pub persona: &'static str,
    pub use_case: &'static str,
    pub terms: [&'static str; 4],
}

pub const SCOPES: [ScopeDefinition; SCOPE_COUNT] = [
    ScopeDefinition {
        name: "engineering-architecture",
        persona: "software-engineer",
        use_case: "architecture-and-adr",
        terms: ["architecture", "decision", "dependency", "migration"],
    },
    ScopeDefinition {
        name: "engineering-api-specs",
        persona: "software-engineer",
        use_case: "api-contracts",
        terms: ["endpoint", "schema", "pagination", "compatibility"],
    },
    ScopeDefinition {
        name: "engineering-incidents",
        persona: "site-reliability-engineer",
        use_case: "incident-response",
        terms: ["incident", "latency", "mitigation", "timeline"],
    },
    ScopeDefinition {
        name: "engineering-runbooks",
        persona: "site-reliability-engineer",
        use_case: "operations-runbooks",
        terms: ["runbook", "alert", "rollback", "verification"],
    },
    ScopeDefinition {
        name: "engineering-releases",
        persona: "release-engineer",
        use_case: "release-and-migration-notes",
        terms: ["release", "version", "upgrade", "deprecation"],
    },
    ScopeDefinition {
        name: "research-papers",
        persona: "academic-researcher",
        use_case: "paper-library",
        terms: ["method", "dataset", "result", "limitation"],
    },
    ScopeDefinition {
        name: "research-lab-notes",
        persona: "academic-researcher",
        use_case: "laboratory-notebook",
        terms: ["observation", "protocol", "sample", "calibration"],
    },
    ScopeDefinition {
        name: "research-experiments",
        persona: "academic-researcher",
        use_case: "experiment-results",
        terms: ["experiment", "baseline", "metric", "variance"],
    },
    ScopeDefinition {
        name: "research-grants",
        persona: "principal-investigator",
        use_case: "grant-and-budget-records",
        terms: ["milestone", "budget", "deliverable", "review"],
    },
    ScopeDefinition {
        name: "research-literature",
        persona: "graduate-student",
        use_case: "literature-notes",
        terms: ["citation", "hypothesis", "evidence", "comparison"],
    },
    ScopeDefinition {
        name: "ml-model-evaluations",
        persona: "machine-learning-engineer",
        use_case: "model-evaluation",
        terms: ["model", "recall", "precision", "benchmark"],
    },
    ScopeDefinition {
        name: "data-dictionaries",
        persona: "data-engineer",
        use_case: "data-dictionary",
        terms: ["column", "type", "constraint", "lineage"],
    },
    ScopeDefinition {
        name: "data-dashboard-reports",
        persona: "data-analyst",
        use_case: "dashboard-reports",
        terms: ["dashboard", "segment", "trend", "forecast"],
    },
    ScopeDefinition {
        name: "ml-notebook-exports",
        persona: "machine-learning-engineer",
        use_case: "notebook-exports",
        terms: ["notebook", "feature", "training", "validation"],
    },
    ScopeDefinition {
        name: "product-meetings",
        persona: "product-manager",
        use_case: "meeting-decisions",
        terms: ["meeting", "decision", "owner", "deadline"],
    },
    ScopeDefinition {
        name: "product-requirements",
        persona: "product-manager",
        use_case: "requirements-and-research",
        terms: ["requirement", "customer", "workflow", "acceptance"],
    },
    ScopeDefinition {
        name: "product-roadmaps",
        persona: "engineering-manager",
        use_case: "roadmap-and-planning",
        terms: ["roadmap", "priority", "capacity", "risk"],
    },
    ScopeDefinition {
        name: "security-compliance",
        persona: "security-engineer",
        use_case: "security-and-compliance",
        terms: ["control", "audit", "threat", "remediation"],
    },
    ScopeDefinition {
        name: "client-deliverables",
        persona: "consultant",
        use_case: "client-deliverables",
        terms: ["client", "finding", "recommendation", "outcome"],
    },
    ScopeDefinition {
        name: "downloads-inbox",
        persona: "knowledge-worker",
        use_case: "downloads-and-inbox",
        terms: ["download", "reference", "summary", "followup"],
    },
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ChunkingContract {
    pub strategy: String,
    pub max_chars: usize,
    pub config_hash: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScaleShape {
    pub scope_count: usize,
    pub files_per_scope: usize,
    pub sections_per_file: usize,
    pub expected_files: usize,
    pub expected_current_chunks: usize,
    pub minimum_current_chunks: usize,
    pub body_chars: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExpectedPopulation {
    pub base_chunks: usize,
    pub current_chunks: usize,
    pub historical_only_chunks: usize,
    pub deleted_chunks: usize,
    pub physical_cas_chunks: usize,
    pub edit_operations: usize,
    pub rename_operations: usize,
    pub delete_operations: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScaleFile {
    pub path: String,
    pub raw_hash: String,
    pub bytes: usize,
    pub expected_chunks: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScaleScope {
    pub name: String,
    pub persona: String,
    pub use_case: String,
    pub expected_files: usize,
    pub expected_base_chunks: usize,
    pub expected_current_chunks: usize,
    pub files: Vec<ScaleFile>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum HistoryOperationKind {
    Edit,
    Rename,
    Delete,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HistoryOperation {
    pub scope: String,
    pub kind: HistoryOperationKind,
    pub source: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub destination: Option<String>,
    pub before_raw_hash: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub after_raw_hash: Option<String>,
    pub before_chunks: usize,
    pub after_chunks: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScaleQuery {
    pub query: String,
    pub scope: String,
    pub file: String,
    pub heading: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScaleManifest {
    pub schema_version: u64,
    pub fixture_id: String,
    pub generator: String,
    pub seed: u64,
    pub workload: String,
    pub profile: ScaleProfile,
    pub lane: ScaleLane,
    pub chunking: ChunkingContract,
    pub shape: ScaleShape,
    pub scopes: Vec<ScaleScope>,
    pub queries: Vec<ScaleQuery>,
    pub base_content_root_hash: String,
    pub overlay_content_root_hash: String,
    pub expected_population: ExpectedPopulation,
    pub history_operations: Vec<HistoryOperation>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OwnerState {
    Building,
    Ready,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OwnerMarker {
    pub schema_version: u64,
    pub fixture_id: String,
    pub generator: String,
    pub profile: ScaleProfile,
    pub lane: ScaleLane,
    pub state: OwnerState,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub manifest_hash: Option<String>,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ScaleSpecError {
    #[error("scale spec serialization failed: {0}")]
    Serialize(String),
    #[error("scale manifest exceeds byte bound")]
    TooLarge,
    #[error("scale manifest is not UTF-8: {0}")]
    Utf8(String),
    #[error("scale manifest JSON is invalid: {0}")]
    Json(String),
    #[error("scale manifest must be canonical JCS JSON followed by one LF")]
    NonCanonical,
    #[error("scale owner marker exceeds byte bound")]
    OwnerTooLarge,
    #[error("scale owner marker is not UTF-8: {0}")]
    OwnerUtf8(String),
    #[error("scale owner marker JSON is invalid: {0}")]
    OwnerJson(String),
    #[error("scale owner marker must be canonical JCS JSON followed by one LF")]
    OwnerNonCanonical,
    #[error("scale manifest does not match the frozen v3 contract")]
    FrozenMismatch,
    #[error("scale owner marker does not match the frozen v3 contract")]
    OwnerMismatch,
    #[error("invalid scale render input")]
    RenderInput,
}

pub fn document_path(file_index: usize) -> String {
    format!("document-{file_index:04}.md")
}

/// Accept exactly a real Gregorian UTC instant rendered to whole seconds.
///
/// The scale attestor intentionally validates this independently of the
/// production commit type. A digit-shaped but impossible date must not become
/// trusted evidence merely because its canonical JSON hash is self-consistent.
#[must_use]
pub fn is_canonical_utc_second(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 20
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[19] != b'Z'
        || bytes.iter().enumerate().any(|(index, byte)| {
            !matches!(index, 4 | 7 | 10 | 13 | 16 | 19) && !byte.is_ascii_digit()
        })
    {
        return false;
    }
    let number = |start: usize, end: usize| -> Option<u32> {
        std::str::from_utf8(&bytes[start..end]).ok()?.parse().ok()
    };
    let (Some(year), Some(month), Some(day), Some(hour), Some(minute), Some(second)) = (
        number(0, 4),
        number(5, 7),
        number(8, 10),
        number(11, 13),
        number(14, 16),
        number(17, 19),
    ) else {
        return false;
    };
    let leap = year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400));
    let days = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap => 29,
        2 => 28,
        _ => return false,
    };
    year != 0 && (1..=days).contains(&day) && hour < 24 && minute < 60 && second < 60
}
pub fn section_heading(scope: usize, file: usize, section: usize) -> String {
    format!("Scale record S{scope:02} F{file:04} C{section:02}")
}
pub fn section_needle(scope: usize, file: usize, section: usize) -> String {
    format!("scale needle s{scope:02} f{file:04} c{section:02}")
}

fn reference_token(scope: usize, file: usize, section: usize, sentence: usize) -> String {
    let input = format!("{SEED}:{scope}:{file}:{section}:{sentence}");
    hash_bytes(input.as_bytes())["sha256:".len()..][..12].to_owned()
}

pub fn section_query(scope: usize, file: usize, section: usize) -> String {
    reference_token(scope, file, section, 0)
}

pub fn render_document(
    scope_index: usize,
    file_index: usize,
    profile: ScaleProfile,
) -> Result<String, ScaleSpecError> {
    let Some(scope) = SCOPES.get(scope_index) else {
        return Err(ScaleSpecError::RenderInput);
    };
    if file_index >= profile.files_per_scope() {
        return Err(ScaleSpecError::RenderInput);
    }
    let mut document = String::new();
    for section_index in 0..profile.sections_per_file() {
        let mut paragraphs = vec![format!(
            "{}. This synthetic {} section belongs to {} and is safe to publish.",
            section_needle(scope_index, file_index, section_index),
            scope.use_case,
            scope.name
        )];
        let mut sentence_index = 0;
        while paragraphs.iter().map(String::len).sum::<usize>() < profile.body_chars() {
            let mut group = Vec::with_capacity(3);
            for _ in 0..3 {
                let first = scope.terms[sentence_index % scope.terms.len()];
                let second = scope.terms[(sentence_index + 1) % scope.terms.len()];
                let measure = 100
                    + ((scope_index * 7919
                        + file_index * 101
                        + section_index * 17
                        + sentence_index)
                        % 9_800);
                group.push(format!(
                    "The {} {} record links {} evidence to measure {} under deterministic reference {}.",
                    scope.persona, first, second, measure, reference_token(scope_index, file_index, section_index, sentence_index)
                ));
                sentence_index += 1;
            }
            paragraphs.push(group.join(" "));
        }
        let section = format!(
            "## {}\n\n{}\n\n",
            section_heading(scope_index, file_index, section_index),
            paragraphs.join("\n\n")
        );
        if section.len() >= CHUNKING_MAX_CHARS {
            return Err(ScaleSpecError::RenderInput);
        }
        document.push_str(&section);
    }
    Ok(document)
}

/// Render the frozen post-edit source.  It preserves every heading and changes
/// only the first section's text, so heading chunking remains one chunk per
/// section while the edited content receives a distinct raw hash.
pub fn render_history_edited_document(
    scope_index: usize,
    file_index: usize,
    profile: ScaleProfile,
) -> Result<String, ScaleSpecError> {
    let source = render_document(scope_index, file_index, profile)?;
    let needle = format!("{}\n\n", section_heading(scope_index, file_index, 0));
    let replacement = format!(
        "{}history overlay edit {}\n\n",
        needle,
        reference_token(scope_index, file_index, 0, usize::MAX)
    );
    Ok(source.replacen(&needle, &replacement, 1))
}

#[must_use]
pub fn shape(profile: ScaleProfile) -> ScaleShape {
    ScaleShape {
        scope_count: SCOPE_COUNT,
        files_per_scope: profile.files_per_scope(),
        sections_per_file: profile.sections_per_file(),
        expected_files: profile.expected_files(),
        expected_current_chunks: profile.expected_chunks(),
        minimum_current_chunks: profile.minimum_current_chunks(),
        body_chars: profile.body_chars(),
    }
}

fn content_root_hash(scopes: &[ScaleScope]) -> Result<String, ScaleSpecError> {
    let rows = scopes
        .iter()
        .flat_map(|scope| {
            scope.files.iter().map(move |file| {
                serde_json::json!({
                    "scope": scope.name, "path": file.path, "raw_hash": file.raw_hash,
                    "bytes": file.bytes, "expected_chunks": file.expected_chunks,
                })
            })
        })
        .collect::<Vec<_>>();
    let bytes = canonical_json_bytes(&serde_json::Value::Array(rows))
        .map_err(|e| ScaleSpecError::Serialize(e.to_string()))?;
    Ok(hash_bytes(&bytes))
}

pub fn frozen_manifest(
    profile: ScaleProfile,
    lane: ScaleLane,
) -> Result<ScaleManifest, ScaleSpecError> {
    let mut scopes = Vec::with_capacity(SCOPE_COUNT);
    let mut queries = Vec::with_capacity(SCOPE_COUNT);
    for (scope_index, scope) in SCOPES.iter().enumerate() {
        let mut files = Vec::with_capacity(profile.files_per_scope());
        for file_index in 0..profile.files_per_scope() {
            let data = render_document(scope_index, file_index, profile)?;
            files.push(ScaleFile {
                path: document_path(file_index),
                raw_hash: hash_bytes(data.as_bytes()),
                bytes: data.len(),
                expected_chunks: profile.sections_per_file(),
            });
        }
        scopes.push(ScaleScope {
            name: scope.name.to_owned(),
            persona: scope.persona.to_owned(),
            use_case: scope.use_case.to_owned(),
            expected_files: profile.files_per_scope(),
            expected_base_chunks: profile.files_per_scope() * profile.sections_per_file(),
            expected_current_chunks: profile.files_per_scope() * profile.sections_per_file(),
            files,
        });
        queries.push(ScaleQuery {
            query: section_query(scope_index, 0, 0),
            scope: scope.name.to_owned(),
            file: document_path(0),
            heading: section_heading(scope_index, 0, 0),
        });
    }
    let base_content_root_hash = content_root_hash(&scopes)?;
    let mut overlay_scopes = scopes.clone();
    let mut history_operations = Vec::new();
    if lane == ScaleLane::HistoryOverlay {
        for (scope_index, scope) in overlay_scopes.iter_mut().enumerate() {
            let before = scope.files[0].clone();
            let after = render_history_edited_document(scope_index, 0, profile)?;
            scope.files[0].raw_hash = hash_bytes(after.as_bytes());
            scope.files[0].bytes = after.len();
            history_operations.push(HistoryOperation {
                scope: scope.name.clone(),
                kind: HistoryOperationKind::Edit,
                source: document_path(0),
                destination: None,
                before_raw_hash: before.raw_hash,
                after_raw_hash: Some(scope.files[0].raw_hash.clone()),
                before_chunks: profile.sections_per_file(),
                after_chunks: profile.sections_per_file(),
            });
            let before = scope.files[1].clone();
            scope.files[1].path = "renamed-document-0001.md".into();
            history_operations.push(HistoryOperation {
                scope: scope.name.clone(),
                kind: HistoryOperationKind::Rename,
                source: document_path(1),
                destination: Some(scope.files[1].path.clone()),
                before_raw_hash: before.raw_hash.clone(),
                after_raw_hash: Some(before.raw_hash),
                before_chunks: profile.sections_per_file(),
                after_chunks: profile.sections_per_file(),
            });
            let before = scope.files[2].clone();
            scope.files.remove(2);
            history_operations.push(HistoryOperation {
                scope: scope.name.clone(),
                kind: HistoryOperationKind::Delete,
                source: document_path(2),
                destination: None,
                before_raw_hash: before.raw_hash,
                after_raw_hash: None,
                before_chunks: profile.sections_per_file(),
                after_chunks: 0,
            });
            scope.expected_current_chunks =
                (profile.files_per_scope() - 1) * profile.sections_per_file();
            scope.expected_files = profile.files_per_scope() - 1;
        }
    }
    let overlay_content_root_hash = content_root_hash(&overlay_scopes)?;
    let sections = profile.sections_per_file();
    let expected_population = match lane {
        ScaleLane::CurrentText => ExpectedPopulation {
            base_chunks: profile.expected_chunks(),
            current_chunks: profile.expected_chunks(),
            historical_only_chunks: 0,
            deleted_chunks: 0,
            physical_cas_chunks: profile.expected_chunks(),
            edit_operations: 0,
            rename_operations: 0,
            delete_operations: 0,
        },
        ScaleLane::HistoryOverlay => ExpectedPopulation {
            base_chunks: profile.expected_chunks(),
            current_chunks: (profile.files_per_scope() - 1) * sections * SCOPE_COUNT,
            // Chunk identity includes the whole-file raw hash. Editing one
            // section therefore replaces every chunk identity from that file;
            // the deleted file contributes the second historical-only set.
            historical_only_chunks: 2 * sections * SCOPE_COUNT,
            deleted_chunks: sections * SCOPE_COUNT,
            physical_cas_chunks: (profile.files_per_scope() + 1) * sections * SCOPE_COUNT,
            edit_operations: SCOPE_COUNT,
            rename_operations: SCOPE_COUNT,
            delete_operations: SCOPE_COUNT,
        },
    };
    Ok(ScaleManifest {
        schema_version: SCHEMA_VERSION,
        fixture_id: FIXTURE_ID.to_owned(),
        generator: GENERATOR_ID.to_owned(),
        seed: SEED,
        workload: WORKLOAD.to_owned(),
        profile,
        lane,
        chunking: ChunkingContract {
            strategy: CHUNKING_STRATEGY.to_owned(),
            max_chars: CHUNKING_MAX_CHARS,
            config_hash: CHUNKING_CONFIG_HASH.to_owned(),
        },
        shape: shape(profile),
        // The public scope inventory describes the lane's final searchable
        // tree. The separately pinned base root and each operation's before
        // identity remain the authority for preparing the parent snapshot.
        scopes: overlay_scopes,
        queries,
        base_content_root_hash,
        overlay_content_root_hash,
        expected_population,
        history_operations,
    })
}

pub fn serialize_manifest(manifest: &ScaleManifest) -> Result<Vec<u8>, ScaleSpecError> {
    let value =
        serde_json::to_value(manifest).map_err(|e| ScaleSpecError::Serialize(e.to_string()))?;
    let mut bytes =
        canonical_json_bytes(&value).map_err(|e| ScaleSpecError::Serialize(e.to_string()))?;
    bytes.push(b'\n');
    Ok(bytes)
}

pub fn manifest_hash(manifest: &ScaleManifest) -> Result<String, ScaleSpecError> {
    Ok(hash_bytes(&serialize_manifest(manifest)?))
}

pub fn parse_manifest(bytes: &[u8]) -> Result<ScaleManifest, ScaleSpecError> {
    if bytes.len() > MAX_MANIFEST_BYTES {
        return Err(ScaleSpecError::TooLarge);
    }
    let text = std::str::from_utf8(bytes).map_err(|e| ScaleSpecError::Utf8(e.to_string()))?;
    let manifest: ScaleManifest =
        serde_json::from_str(text).map_err(|e| ScaleSpecError::Json(e.to_string()))?;
    if serialize_manifest(&manifest)? != bytes {
        return Err(ScaleSpecError::NonCanonical);
    }
    let frozen = frozen_manifest(manifest.profile, manifest.lane)?;
    if manifest != frozen {
        return Err(ScaleSpecError::FrozenMismatch);
    }
    if manifest_hash(&manifest)? != manifest.profile.frozen_manifest_hash(manifest.lane) {
        return Err(ScaleSpecError::FrozenMismatch);
    }
    Ok(manifest)
}

pub fn validate_owner(owner: &OwnerMarker) -> Result<(), ScaleSpecError> {
    let valid_identity = owner.schema_version == SCHEMA_VERSION
        && owner.fixture_id == FIXTURE_ID
        && owner.generator == GENERATOR_ID;
    let valid_state = match owner.state {
        OwnerState::Building => owner.manifest_hash.is_none(),
        OwnerState::Ready => {
            owner.manifest_hash.as_deref() == Some(owner.profile.frozen_manifest_hash(owner.lane))
        }
    };
    if valid_identity && valid_state {
        Ok(())
    } else {
        Err(ScaleSpecError::OwnerMismatch)
    }
}

pub fn serialize_owner(owner: &OwnerMarker) -> Result<Vec<u8>, ScaleSpecError> {
    validate_owner(owner)?;
    let value =
        serde_json::to_value(owner).map_err(|e| ScaleSpecError::Serialize(e.to_string()))?;
    let mut bytes =
        canonical_json_bytes(&value).map_err(|e| ScaleSpecError::Serialize(e.to_string()))?;
    bytes.push(b'\n');
    Ok(bytes)
}

pub fn parse_owner(bytes: &[u8]) -> Result<OwnerMarker, ScaleSpecError> {
    if bytes.len() > MAX_OWNER_BYTES {
        return Err(ScaleSpecError::OwnerTooLarge);
    }
    let text = std::str::from_utf8(bytes).map_err(|e| ScaleSpecError::OwnerUtf8(e.to_string()))?;
    let owner: OwnerMarker =
        serde_json::from_str(text).map_err(|e| ScaleSpecError::OwnerJson(e.to_string()))?;
    validate_owner(&owner)?;
    if serialize_owner(&owner)? != bytes {
        return Err(ScaleSpecError::OwnerNonCanonical);
    }
    Ok(owner)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frozen_shapes_and_rendering_are_bounded() {
        assert_eq!(shape(ScaleProfile::Tiny).expected_files, 60);
        assert_eq!(shape(ScaleProfile::Tiny).expected_current_chunks, 180);
        assert_eq!(shape(ScaleProfile::Full).expected_files, 4_000);
        assert_eq!(shape(ScaleProfile::Full).expected_current_chunks, 120_000);
        for (index, _) in SCOPES.iter().enumerate() {
            assert!(
                render_document(index, 0, ScaleProfile::Full)
                    .unwrap()
                    .is_ascii()
            );
        }
    }

    #[test]
    fn frozen_manifest_is_canonical_and_has_pinned_digest() {
        for (profile, lane) in [ScaleProfile::Tiny, ScaleProfile::Full]
            .into_iter()
            .flat_map(|profile| {
                [ScaleLane::CurrentText, ScaleLane::HistoryOverlay].map(move |lane| (profile, lane))
            })
        {
            let manifest = frozen_manifest(profile, lane).unwrap();
            let bytes = serialize_manifest(&manifest).unwrap();
            assert_eq!(
                manifest_hash(&manifest).unwrap(),
                profile.frozen_manifest_hash(lane)
            );
            assert_eq!(parse_manifest(&bytes).unwrap(), manifest);
        }
    }

    #[test]
    fn history_manifest_separates_base_shape_from_final_inventory() {
        let manifest = frozen_manifest(ScaleProfile::Tiny, ScaleLane::HistoryOverlay).unwrap();
        assert_eq!(manifest.shape.expected_files, 60);
        assert_eq!(manifest.expected_population.base_chunks, 180);
        assert!(manifest.scopes.iter().all(|scope| {
            scope.expected_files == 2
                && scope.expected_base_chunks == 9
                && scope.expected_current_chunks == 6
                && scope.files.len() == 2
        }));
    }

    #[test]
    fn manifest_rejects_noncanonical_and_self_consistent_mutation() {
        let manifest = frozen_manifest(ScaleProfile::Tiny, ScaleLane::CurrentText).unwrap();
        let mut bytes = serde_json::to_vec_pretty(&manifest).unwrap();
        bytes.push(b'\n');
        assert_eq!(parse_manifest(&bytes), Err(ScaleSpecError::NonCanonical));
        let mut forged = manifest;
        forged.scopes.swap(0, 1);
        let bytes = serialize_manifest(&forged).unwrap();
        assert_eq!(parse_manifest(&bytes), Err(ScaleSpecError::FrozenMismatch));
    }

    #[test]
    fn owner_is_strict_for_building_and_ready_states() {
        let ready = OwnerMarker {
            schema_version: SCHEMA_VERSION,
            fixture_id: FIXTURE_ID.into(),
            generator: GENERATOR_ID.into(),
            profile: ScaleProfile::Tiny,
            lane: ScaleLane::CurrentText,
            state: OwnerState::Ready,
            manifest_hash: Some(TINY_CURRENT_TEXT_MANIFEST_HASH.into()),
        };
        assert!(validate_owner(&ready).is_ok());
        let bytes = serialize_owner(&ready).unwrap();
        assert_eq!(parse_owner(&bytes).unwrap(), ready);
        let mut bad = ready;
        bad.manifest_hash = None;
        assert_eq!(validate_owner(&bad), Err(ScaleSpecError::OwnerMismatch));
        let wrong_version = br#"{"fixture_id":"kio-scale-v3","generator":"kio-eval scale generate/v3","manifest_hash":"sha256:00","profile":"tiny","schema_version":1,"state":"ready"}
"#;
        assert!(parse_owner(wrong_version).is_err());
    }
}
