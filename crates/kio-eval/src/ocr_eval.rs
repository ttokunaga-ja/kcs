//! Typed, bounded OCR evaluation primitives.
//!
//! Python is deliberately not an evaluation authority.  It may provide a
//! model response through the narrow JSONL adapter protocol below, while this
//! module owns parsing, metrics, thresholds, verdicts, and report data.

use std::{
    collections::BTreeMap,
    ffi::{OsStr, OsString},
    fs,
    io::{self, Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;
use unicode_normalization::UnicodeNormalization;

pub const GROUND_TRUTH_SCHEMA: &str = "kio.ocr.ground-truth/v1";
pub const RESPONSE_SCHEMA: &str = "kio.ocr.response/v1";
pub const PROVIDER_REQUEST_SCHEMA: &str = "kio.ocr.provider-request/v1";
pub const PROVIDER_RESPONSE_SCHEMA: &str = "kio.ocr.provider-response/v1";
pub const TABLE_RECALL_THRESHOLD: f64 = 0.95;
pub const JAPANESE_CER_THRESHOLD: f64 = 0.02;
pub const MAX_JSON_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_PAGES: usize = 10_000;
pub const MAX_MARKDOWN_BYTES: usize = 4 * 1024 * 1024;
pub const MAX_DOCUMENT_BYTES: u64 = 256 * 1024 * 1024;
/// Provider documents travel in the bounded JSONL request, not by a pathname
/// that a credentialed child could reopen after validation.
pub const MAX_PROVIDER_DOCUMENT_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_PROVIDER_REQUEST_BYTES: usize = 24 * 1024 * 1024;
pub const MAX_RENDER_INPUT_IMAGES: usize = 10_000;
pub const MAX_RENDER_IMAGE_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_RENDER_TOTAL_BYTES: u64 = 64 * 1024 * 1024;
pub const MAX_RENDER_IMAGE_PIXELS: u64 = 32 * 1024 * 1024;
pub const MAX_RENDER_TOTAL_PIXELS: u64 = 96 * 1024 * 1024;
pub const MAX_RENDER_OUTPUT_BYTES: u64 = 64 * 1024 * 1024;

#[derive(Debug, Error)]
pub enum OcrEvalError {
    #[error("OCR JSON exceeds the {limit}-byte bound")]
    InputTooLarge { limit: usize },
    #[error("invalid OCR JSON: {0}")]
    Json(#[from] serde_json::Error),
    #[error("invalid OCR data: {0}")]
    Invalid(&'static str),
    #[error("OCR adapter path must be absolute: {0}")]
    AdapterPath(PathBuf),
    #[error("OCR document binding is invalid: {0}")]
    DocumentBinding(&'static str),
    #[error("OCR report path already exists: {0}")]
    ReportAlreadyExists(PathBuf),
    #[error("OCR adapter request exceeds the {limit}-byte bound")]
    RequestTooLarge { limit: usize },
    #[error("OCR adapter timed out after {0:?}")]
    Timeout(Duration),
    #[error("OCR adapter {stream} exceeded the {limit}-byte bound")]
    OutputTooLarge { stream: &'static str, limit: usize },
    #[error("OCR adapter failed with status {status}: {stderr}")]
    AdapterFailed { status: String, stderr: String },
    #[error("OCR adapter I/O: {0}")]
    Io(#[from] io::Error),
    #[error("OCR artifact publication: {0}")]
    Artifact(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GroundTruth {
    pub schema: String,
    pub table: TableTruth,
    pub japanese: JapaneseTruth,
    pub images: ImageTruth,
    pub formula: FormulaTruth,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TableTruth {
    pub page_index: u32,
    pub expected_cell_texts: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct JapaneseTruth {
    pub page_index: u32,
    pub full_text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ImageTruth {
    pub page_index: u32,
    pub expected_count: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FormulaTruth {
    pub page_index: u32,
    pub expected_tokens: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OcrResponse {
    pub schema: String,
    pub pages: Vec<OcrPage>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OcrPage {
    pub index: u32,
    #[serde(default)]
    pub markdown: String,
    /// Provider image payloads are not interpreted by evaluation; their count
    /// is the contract.  The bounded JSON parser still owns their shape.
    #[serde(default)]
    pub images: Vec<serde_json::Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct EvaluationReport {
    pub schema: &'static str,
    pub verdict: Verdict,
    pub criteria: Criteria,
    pub table: TableMetric,
    pub japanese: JapaneseMetric,
    pub images: ImageMetric,
    pub formula: FormulaMetric,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Verdict {
    Passed,
    Rejected,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Criteria {
    pub table_recall_at_least: f64,
    pub japanese_cer_at_most: f64,
    pub image_count_exact: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct TableMetric {
    pub matched_cells: usize,
    pub total_cells: usize,
    pub recall: f64,
    pub passed: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct JapaneseMetric {
    pub expected_chars: usize,
    pub observed_chars: usize,
    pub edit_distance: usize,
    pub cer: f64,
    pub passed: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ImageMetric {
    pub expected_count: u32,
    pub observed_count: usize,
    pub passed: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct FormulaMetric {
    pub expected_tokens: Vec<String>,
    pub matched_tokens: Vec<String>,
    pub classification: FormulaClassification,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FormulaClassification {
    Textized,
    ImageFallback,
    Missing,
}

pub fn parse_ground_truth(bytes: &[u8]) -> Result<GroundTruth, OcrEvalError> {
    if bytes.len() > MAX_JSON_BYTES {
        return Err(OcrEvalError::InputTooLarge {
            limit: MAX_JSON_BYTES,
        });
    }
    let truth: GroundTruth = serde_json::from_slice(bytes)?;
    if truth.schema != GROUND_TRUTH_SCHEMA {
        return Err(OcrEvalError::Invalid("unsupported ground-truth schema"));
    }
    if truth.table.expected_cell_texts.len() > 100_000
        || truth.formula.expected_tokens.len() > 100_000
    {
        return Err(OcrEvalError::Invalid(
            "ground truth collection exceeds bound",
        ));
    }
    Ok(truth)
}

pub fn parse_response(bytes: &[u8]) -> Result<OcrResponse, OcrEvalError> {
    if bytes.len() > MAX_JSON_BYTES {
        return Err(OcrEvalError::InputTooLarge {
            limit: MAX_JSON_BYTES,
        });
    }
    let response: OcrResponse = serde_json::from_slice(bytes)?;
    if response.schema != RESPONSE_SCHEMA {
        return Err(OcrEvalError::Invalid("unsupported OCR response schema"));
    }
    if response.pages.len() > MAX_PAGES
        || response
            .pages
            .iter()
            .any(|page| page.markdown.len() > MAX_MARKDOWN_BYTES)
    {
        return Err(OcrEvalError::Invalid(
            "OCR response exceeds page or markdown bound",
        ));
    }
    let mut seen = std::collections::BTreeSet::new();
    if response.pages.iter().any(|page| !seen.insert(page.index)) {
        return Err(OcrEvalError::Invalid(
            "OCR response has duplicate page index",
        ));
    }
    Ok(response)
}

pub fn evaluate(
    truth: &GroundTruth,
    response: &OcrResponse,
) -> Result<EvaluationReport, OcrEvalError> {
    let table_page = page(response, truth.table.page_index)?;
    let table_haystack = normalize_cell(&table_page.markdown);
    let matched_cells: Vec<_> = truth
        .table
        .expected_cell_texts
        .iter()
        .filter(|cell| table_haystack.contains(&normalize_cell(cell)))
        .cloned()
        .collect();
    let table_recall = ratio(matched_cells.len(), truth.table.expected_cell_texts.len());
    let table = TableMetric {
        matched_cells: matched_cells.len(),
        total_cells: truth.table.expected_cell_texts.len(),
        recall: table_recall,
        passed: table_recall >= TABLE_RECALL_THRESHOLD,
    };

    let japanese_page = page(response, truth.japanese.page_index)?;
    let expected = normalize_japanese(&truth.japanese.full_text);
    let observed = normalize_japanese(&japanese_page.markdown);
    let distance = best_window_distance(&expected, &observed);
    let cer = ratio(distance, expected.chars().count());
    let japanese = JapaneseMetric {
        expected_chars: expected.chars().count(),
        observed_chars: observed.chars().count(),
        edit_distance: distance,
        cer,
        passed: cer <= JAPANESE_CER_THRESHOLD,
    };

    let image_page = page(response, truth.images.page_index)?;
    let images = ImageMetric {
        expected_count: truth.images.expected_count,
        observed_count: image_page.images.len(),
        passed: image_page.images.len() == truth.images.expected_count as usize,
    };

    let formula_page = page(response, truth.formula.page_index)?;
    let normalized = normalize_formula(&formula_page.markdown);
    let matched_tokens: Vec<_> = truth
        .formula
        .expected_tokens
        .iter()
        .filter(|token| normalized.contains(&normalize_formula(token)))
        .cloned()
        .collect();
    let classification = if matched_tokens.len() == truth.formula.expected_tokens.len() {
        FormulaClassification::Textized
    } else if !formula_page.images.is_empty() || formula_page.markdown.contains("![") {
        FormulaClassification::ImageFallback
    } else {
        FormulaClassification::Missing
    };
    let formula = FormulaMetric {
        expected_tokens: truth.formula.expected_tokens.clone(),
        matched_tokens,
        classification,
    };
    let verdict = if table.passed && japanese.passed && images.passed {
        Verdict::Passed
    } else {
        Verdict::Rejected
    };
    Ok(EvaluationReport {
        schema: "kio.ocr.evaluation-report/v1",
        verdict,
        criteria: Criteria {
            table_recall_at_least: TABLE_RECALL_THRESHOLD,
            japanese_cer_at_most: JAPANESE_CER_THRESHOLD,
            image_count_exact: true,
        },
        table,
        japanese,
        images,
        formula,
    })
}

fn page(response: &OcrResponse, index: u32) -> Result<&OcrPage, OcrEvalError> {
    response
        .pages
        .iter()
        .find(|page| page.index == index)
        .ok_or(OcrEvalError::Invalid(
            "ground truth refers to absent OCR page",
        ))
}
fn ratio(numerator: usize, denominator: usize) -> f64 {
    if denominator == 0 {
        1.0
    } else {
        numerator as f64 / denominator as f64
    }
}
fn normalize_cell(value: &str) -> String {
    value
        .nfc()
        .flat_map(char::to_lowercase)
        .filter(|ch| !ch.is_whitespace())
        .collect()
}
fn normalize_japanese(value: &str) -> String {
    value.nfc().filter(|ch| !ch.is_whitespace()).collect()
}
fn normalize_formula(value: &str) -> String {
    value.nfc().filter(|ch| !ch.is_whitespace()).collect()
}

fn best_window_distance(expected: &str, observed: &str) -> usize {
    let expected: Vec<_> = expected.chars().collect();
    let observed: Vec<_> = observed.chars().collect();
    if expected.is_empty() {
        return 0;
    }
    if observed.len() <= expected.len() {
        return levenshtein(&expected, &observed);
    }
    observed
        .windows(expected.len())
        .map(|window| levenshtein(&expected, window))
        .min()
        .unwrap_or(expected.len())
}
fn levenshtein(left: &[char], right: &[char]) -> usize {
    let mut row: Vec<usize> = (0..=right.len()).collect();
    for (i, lhs) in left.iter().enumerate() {
        let mut diagonal = row[0];
        row[0] = i + 1;
        for (j, rhs) in right.iter().enumerate() {
            let old = row[j + 1];
            row[j + 1] = (row[j + 1] + 1)
                .min(row[j] + 1)
                .min(diagonal + usize::from(lhs != rhs));
            diagonal = old;
        }
    }
    row[right.len()]
}

/// Request issued to the Python-only Mistral adapter.  All paths are explicit;
/// the adapter must not discover fixtures or choose outputs.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProviderRequest {
    pub schema: String,
    pub request_id: String,
    pub model: String,
    pub media_type: String,
    pub document_bytes: u64,
    pub document_sha256: String,
    pub document_base64: String,
    pub include_image_base64: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProviderResponse {
    pub schema: String,
    pub request_id: String,
    pub document_sha256: String,
    pub response: serde_json::Value,
}

/// Convert the provider's deliberately opaque SDK payload into Kio's closed
/// response schema.  The Python adapter never gets to decide this shape.
pub fn normalize_provider_response(
    provider: &ProviderResponse,
) -> Result<OcrResponse, OcrEvalError> {
    #[derive(Deserialize)]
    struct RawPage {
        index: u32,
        #[serde(default)]
        markdown: String,
        #[serde(default)]
        images: Vec<serde_json::Value>,
    }
    #[derive(Deserialize)]
    struct RawResponse {
        pages: Vec<RawPage>,
    }
    let raw: RawResponse = serde_json::from_value(provider.response.clone())?;
    let response = OcrResponse {
        schema: RESPONSE_SCHEMA.into(),
        pages: raw
            .pages
            .into_iter()
            .map(|page| OcrPage {
                index: page.index,
                markdown: page.markdown,
                images: page.images,
            })
            .collect(),
    };
    // Reparse the canonical serialization so every response invariant remains
    // centralized in `parse_response`.
    parse_response(&serde_json::to_vec(&response)?)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RenderRequest {
    pub schema: String,
    pub request_id: String,
    pub output_pdf: String,
    pub input_images: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RenderResponse {
    pub schema: String,
    pub request_id: String,
    pub output_pdf: String,
    pub output_bytes: u64,
    pub output_sha256: String,
    pub page_count: u32,
}

pub const RENDER_REQUEST_SCHEMA: &str = "kio.ocr.fixture-render.request/v1";
pub const RENDER_RESPONSE_SCHEMA: &str = "kio.ocr.fixture-render.response/v1";

/// Explicit interpreter plus explicit adapter script.  The child has no
/// inherited environment; callers must opt in to every variable.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AdapterCommand {
    pub python: PathBuf,
    pub adapter: PathBuf,
    pub environment: BTreeMap<OsString, OsString>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DocumentBinding {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
}

/// Bind an explicitly named PDF through the descriptor-retained artifact
/// boundary. The Python provider receives only the resulting byte snapshot.
pub fn bind_document(path: &Path) -> Result<DocumentBinding, OcrEvalError> {
    let artifact = bind_strict_input(path, MAX_DOCUMENT_BYTES)?;
    let bytes = artifact.bytes();
    artifact
        .recheck()
        .map_err(|_| OcrEvalError::DocumentBinding("document changed while being bound"))?;
    Ok(DocumentBinding {
        path: path.to_owned(),
        bytes: bytes.len() as u64,
        sha256: hex_sha256(bytes),
    })
}

/// Construct a provider request from a retained, bounded document snapshot.
/// The provider adapter receives these bytes only; it never receives a file
/// path to rediscover or reopen.
pub fn provider_request_from_document(
    request_id: String,
    model: String,
    path: &Path,
    include_image_base64: bool,
) -> Result<ProviderRequest, OcrEvalError> {
    if request_id.is_empty() || request_id.len() > 256 || model.is_empty() || model.len() > 256 {
        return Err(OcrEvalError::Invalid(
            "provider request id or model is out of bounds",
        ));
    }
    let artifact = bind_strict_input(path, MAX_PROVIDER_DOCUMENT_BYTES)?;
    let bytes = artifact.bytes();
    let binding = DocumentBinding {
        path: path.to_owned(),
        bytes: bytes.len() as u64,
        sha256: hex_sha256(bytes),
    };
    artifact.recheck().map_err(|_| {
        OcrEvalError::DocumentBinding("document changed while preparing provider payload")
    })?;
    Ok(ProviderRequest {
        schema: PROVIDER_REQUEST_SCHEMA.into(),
        request_id,
        model,
        media_type: "application/pdf".into(),
        document_bytes: binding.bytes,
        document_sha256: binding.sha256,
        document_base64: base64_encode(bytes),
        include_image_base64,
    })
}

pub fn bind_provider_request(request: &ProviderRequest) -> Result<DocumentBinding, OcrEvalError> {
    if request.schema != PROVIDER_REQUEST_SCHEMA
        || request.request_id.is_empty()
        || request.request_id.len() > 256
        || request.model.is_empty()
        || request.model.len() > 256
        || request.media_type != "application/pdf"
        || !valid_sha256(&request.document_sha256)
        || request.document_bytes > MAX_PROVIDER_DOCUMENT_BYTES
        || request.document_base64.len() > MAX_PROVIDER_REQUEST_BYTES
    {
        return Err(OcrEvalError::DocumentBinding(
            "invalid provider request binding",
        ));
    }
    let bytes = base64_decode(&request.document_base64)?;
    if bytes.len() as u64 != request.document_bytes || hex_sha256(&bytes) != request.document_sha256
    {
        return Err(OcrEvalError::DocumentBinding(
            "provider payload identity mismatch",
        ));
    }
    Ok(DocumentBinding {
        path: PathBuf::new(),
        bytes: request.document_bytes,
        sha256: request.document_sha256.clone(),
    })
}

/// Create a canonical evaluation report once. Existing artifact archives are
/// never overwritten or treated as current evidence.
pub fn write_report_create_only(
    path: &Path,
    report: &EvaluationReport,
) -> Result<(), OcrEvalError> {
    if !path.is_absolute() {
        return Err(OcrEvalError::AdapterPath(path.to_owned()));
    }
    let bytes =
        serde_jcs::to_vec(report).map_err(|error| OcrEvalError::Artifact(error.to_string()))?;
    let mut canonical = bytes;
    canonical.push(b'\n');
    match crate::persona_artifact::publish_create_only(path, &canonical, MAX_JSON_BYTES) {
        Ok(_) => Ok(()),
        Err(crate::persona_artifact::PersonaArtifactError::AlreadyExists(_)) => {
            Err(OcrEvalError::ReportAlreadyExists(path.to_owned()))
        }
        Err(error) => Err(OcrEvalError::Artifact(error.to_string())),
    }
}

/// Publish the normalized closed OCR response once.  Provider payloads are
/// intentionally never archived as authority; only this Rust-owned schema is.
pub fn write_response_create_only(path: &Path, response: &OcrResponse) -> Result<(), OcrEvalError> {
    if !path.is_absolute() {
        return Err(OcrEvalError::AdapterPath(path.to_owned()));
    }
    let parsed = parse_response(&serde_json::to_vec(response)?)?;
    let mut canonical =
        serde_jcs::to_vec(&parsed).map_err(|error| OcrEvalError::Artifact(error.to_string()))?;
    canonical.push(b'\n');
    match crate::persona_artifact::publish_create_only(path, &canonical, MAX_JSON_BYTES) {
        Ok(_) => Ok(()),
        Err(crate::persona_artifact::PersonaArtifactError::AlreadyExists(_)) => {
            Err(OcrEvalError::ReportAlreadyExists(path.to_owned()))
        }
        Err(error) => Err(OcrEvalError::Artifact(error.to_string())),
    }
}

#[derive(Debug, Clone)]
pub struct AdapterLimits {
    pub timeout: Duration,
    pub max_stdin_bytes: usize,
    pub max_stdout_bytes: usize,
    pub max_stderr_bytes: usize,
}
impl Default for AdapterLimits {
    fn default() -> Self {
        Self {
            timeout: Duration::from_secs(60),
            max_stdin_bytes: MAX_PROVIDER_REQUEST_BYTES,
            max_stdout_bytes: MAX_JSON_BYTES,
            max_stderr_bytes: 64 * 1024,
        }
    }
}

pub fn invoke_provider(
    command: &AdapterCommand,
    request: &ProviderRequest,
    limits: &AdapterLimits,
) -> Result<ProviderResponse, OcrEvalError> {
    if command
        .environment
        .get(OsStr::new("MISTRAL_API_KEY"))
        .is_none_or(|value| value.is_empty())
    {
        return Err(OcrEvalError::Invalid(
            "provider adapter requires explicit MISTRAL_API_KEY",
        ));
    }
    if request.schema != PROVIDER_REQUEST_SCHEMA {
        return Err(OcrEvalError::Invalid("unsupported provider request schema"));
    }
    let binding = bind_provider_request(request)?;
    let output = invoke_adapter(command, request, limits)?;
    parse_provider_line(&output.0, request, &binding)
}

/// Run the narrow renderer with explicit absolute inputs and a create-only
/// output. The response is verified against the inode-independent bytes Rust
/// observes after the child exits.
pub fn invoke_renderer(
    command: &AdapterCommand,
    request: &RenderRequest,
    limits: &AdapterLimits,
) -> Result<RenderResponse, OcrEvalError> {
    if !command.environment.is_empty() {
        return Err(OcrEvalError::Invalid(
            "renderer adapter must have an empty environment",
        ));
    }
    validate_render_request(request)?;
    let output_path = PathBuf::from(&request.output_pdf);
    let mut aggregate_bytes = 0_u64;
    let mut aggregate_pixels = 0_u64;
    let mut input_bindings = Vec::with_capacity(request.input_images.len());
    for value in &request.input_images {
        let binding = bind_strict_input(Path::new(value), MAX_RENDER_IMAGE_BYTES)?;
        let bytes = binding.bytes();
        aggregate_bytes = aggregate_bytes
            .checked_add(bytes.len() as u64)
            .ok_or(OcrEvalError::Invalid("renderer input byte count overflow"))?;
        if aggregate_bytes > MAX_RENDER_TOTAL_BYTES {
            return Err(OcrEvalError::DocumentBinding(
                "renderer inputs exceed aggregate byte bound",
            ));
        }
        let pixels = png_pixels(bytes)?;
        if pixels > MAX_RENDER_IMAGE_PIXELS {
            return Err(OcrEvalError::DocumentBinding(
                "renderer input exceeds per-image pixel bound",
            ));
        }
        aggregate_pixels = aggregate_pixels
            .checked_add(pixels)
            .ok_or(OcrEvalError::Invalid("renderer input pixel count overflow"))?;
        if aggregate_pixels > MAX_RENDER_TOTAL_PIXELS {
            return Err(OcrEvalError::DocumentBinding(
                "renderer inputs exceed aggregate pixel bound",
            ));
        }
        input_bindings.push(binding);
    }
    // The Python-native renderer receives only private immutable snapshots.
    // It never reopens the caller-controlled input names after Rust validates
    // them, closing the stat/open and mid-render replacement seams.
    let snapshots = tempfile::tempdir()?;
    let mut adapter_request = request.clone();
    adapter_request.input_images.clear();
    for (index, binding) in input_bindings.iter().enumerate() {
        let snapshot = snapshots.path().join(format!("input-{index:05}.png"));
        fs::write(&snapshot, binding.bytes())?;
        adapter_request
            .input_images
            .push(snapshot.to_string_lossy().into_owned());
    }
    let output = invoke_adapter(command, &adapter_request, limits)?;
    for binding in &input_bindings {
        binding.recheck().map_err(|_| {
            OcrEvalError::DocumentBinding("renderer input changed during adapter execution")
        })?;
    }
    let response = parse_render_line(&output.0, request)?;
    let final_binding = bind_strict_input(&output_path, MAX_RENDER_OUTPUT_BYTES)?;
    let output_bytes = final_binding.bytes();
    let output_sha256 = hex_sha256(output_bytes);
    if output_bytes.is_empty()
        || output_bytes.len() as u64 != response.output_bytes
        || output_sha256 != response.output_sha256
    {
        return Err(OcrEvalError::DocumentBinding(
            "renderer output identity mismatch",
        ));
    }
    if pdf_page_count(output_bytes)? != response.page_count {
        return Err(OcrEvalError::DocumentBinding(
            "renderer output bytes or page count changed during verification",
        ));
    }
    final_binding.recheck().map_err(|_| {
        OcrEvalError::DocumentBinding("renderer output changed during verification")
    })?;
    Ok(response)
}

/// PNG headers are inexpensive to inspect before spawning Pillow. Other image
/// formats remain bounded by raw bytes and are checked by Pillow in the
/// adapter; an unknown signature fails closed rather than selecting a decoder.
fn png_pixels(bytes: &[u8]) -> Result<u64, OcrEvalError> {
    let header = bytes.get(..24).ok_or(OcrEvalError::Invalid(
        "renderer input lacks a PNG IHDR header",
    ))?;
    if &header[..8] != b"\x89PNG\r\n\x1a\n" || &header[12..16] != b"IHDR" {
        return Err(OcrEvalError::Invalid("renderer only accepts PNG inputs"));
    }
    let width = u32::from_be_bytes(header[16..20].try_into().unwrap());
    let height = u32::from_be_bytes(header[20..24].try_into().unwrap());
    if width == 0 || height == 0 {
        return Err(OcrEvalError::Invalid(
            "renderer PNG dimensions must be nonzero",
        ));
    }
    u64::from(width)
        .checked_mul(u64::from(height))
        .ok_or(OcrEvalError::Invalid("renderer PNG pixel count overflow"))
}

fn pdf_page_count(bytes: &[u8]) -> Result<u32, OcrEvalError> {
    if !bytes.starts_with(b"%PDF-") {
        return Err(OcrEvalError::Invalid("renderer output is not a PDF"));
    }
    let needle = b"/Type /Page";
    if bytes.len() < needle.len() {
        return Ok(0);
    }
    // `/Type /Pages` must not be counted as a page object. The bytes following
    // the singular token are a delimiter in canonical reportlab output.
    let mut pages = 0_u32;
    for offset in 0..=bytes.len() - needle.len() {
        if &bytes[offset..offset + needle.len()] == needle
            && bytes
                .get(offset + needle.len())
                .is_none_or(|byte| *byte != b's')
        {
            pages = pages
                .checked_add(1)
                .ok_or(OcrEvalError::Invalid("PDF page count overflow"))?;
        }
    }
    Ok(pages)
}

fn bind_strict_input(
    path: &Path,
    maximum: u64,
) -> Result<crate::persona_artifact::StrictArtifact, OcrEvalError> {
    if !path.is_absolute() {
        return Err(OcrEvalError::AdapterPath(path.to_owned()));
    }
    let maximum = usize::try_from(maximum)
        .map_err(|_| OcrEvalError::DocumentBinding("input byte bound is unsupported"))?;
    crate::persona_artifact::bind_strict(path, maximum).map_err(|_| {
        OcrEvalError::DocumentBinding("input is not a stable bounded single-link regular file")
    })
}
fn validate_render_request(request: &RenderRequest) -> Result<(), OcrEvalError> {
    if request.schema != RENDER_REQUEST_SCHEMA
        || request.request_id.is_empty()
        || request.input_images.is_empty()
        || request.input_images.len() > MAX_RENDER_INPUT_IMAGES
        || !Path::new(&request.output_pdf).is_absolute()
    {
        return Err(OcrEvalError::Invalid("invalid renderer request"));
    }
    let mut unique = std::collections::BTreeSet::new();
    for image in &request.input_images {
        if !Path::new(image).is_absolute() || !unique.insert(image) {
            return Err(OcrEvalError::Invalid(
                "renderer inputs must be unique absolute paths",
            ));
        }
    }
    let output = Path::new(&request.output_pdf);
    let parent = output
        .parent()
        .ok_or(OcrEvalError::Invalid("renderer output has no parent"))?;
    if !fs::symlink_metadata(parent)?.file_type().is_dir() {
        return Err(OcrEvalError::Invalid(
            "renderer output parent must be an existing directory",
        ));
    }
    if fs::symlink_metadata(&request.output_pdf).is_ok() {
        return Err(OcrEvalError::ReportAlreadyExists(PathBuf::from(
            &request.output_pdf,
        )));
    }
    Ok(())
}

fn invoke_adapter<T: Serialize>(
    command: &AdapterCommand,
    request: &T,
    limits: &AdapterLimits,
) -> Result<(Vec<u8>, Vec<u8>), OcrEvalError> {
    validate_adapter_command(command)?;
    let started = Instant::now();
    let mut input = serde_json::to_vec(request)?;
    input.push(b'\n');
    if input.len() > limits.max_stdin_bytes {
        return Err(OcrEvalError::RequestTooLarge {
            limit: limits.max_stdin_bytes,
        });
    }
    let mut process = Command::new(&command.python);
    process
        .arg(&command.adapter)
        .env_clear()
        .env("PYTHONHASHSEED", "0")
        .env("PYTHONNOUSERSITE", "1");
    // MISTRAL_API_KEY is the only useful credential and only the provider
    // caller can explicitly put it into the otherwise empty environment.
    for (key, value) in &command.environment {
        if key == OsStr::new("MISTRAL_API_KEY") {
            process.env(key, value);
        }
    }
    process
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    configure_process_group(&mut process);
    let mut child = process.spawn()?;
    let stdout = child
        .stdout
        .take()
        .ok_or(OcrEvalError::Invalid("adapter stdout unavailable"))?;
    let stderr = child
        .stderr
        .take()
        .ok_or(OcrEvalError::Invalid("adapter stderr unavailable"))?;
    let out_limit = limits.max_stdout_bytes;
    let err_limit = limits.max_stderr_bytes;
    let (overflow_tx, overflow_rx) = mpsc::channel();
    let stdout_tx = overflow_tx.clone();
    let out_reader = thread::spawn(move || read_bounded(stdout, out_limit, "stdout", stdout_tx));
    let err_reader = thread::spawn(move || read_bounded(stderr, err_limit, "stderr", overflow_tx));
    let mut stdin = child
        .stdin
        .take()
        .ok_or(OcrEvalError::Invalid("adapter stdin unavailable"))?;
    let writer = thread::spawn(move || stdin.write_all(&input));
    loop {
        if let Ok(stream) = overflow_rx.try_recv() {
            terminate_process_group(&mut child);
            let _ = child.wait();
            let _ = writer.join();
            let _ = out_reader.join();
            let _ = err_reader.join();
            return Err(OcrEvalError::OutputTooLarge {
                stream,
                limit: if stream == "stdout" {
                    out_limit
                } else {
                    err_limit
                },
            });
        }
        match child.try_wait()? {
            Some(status) => {
                let writer_result = writer
                    .join()
                    .map_err(|_| OcrEvalError::Invalid("adapter stdin writer panicked"))?;
                if let Err(error) = writer_result {
                    return Err(OcrEvalError::Io(error));
                }
                let stdout = join_reader(out_reader)?;
                let stderr = join_reader(err_reader)?;
                if let Ok(stream) = overflow_rx.try_recv() {
                    return Err(OcrEvalError::OutputTooLarge {
                        stream,
                        limit: if stream == "stdout" {
                            out_limit
                        } else {
                            err_limit
                        },
                    });
                }
                if !status.success() {
                    return Err(OcrEvalError::AdapterFailed {
                        status: status.to_string(),
                        stderr: String::from_utf8_lossy(&stderr).into_owned(),
                    });
                }
                return Ok((stdout, stderr));
            }
            None if started.elapsed() >= limits.timeout => {
                terminate_process_group(&mut child);
                let _ = child.wait();
                let _ = writer.join();
                let _ = out_reader.join();
                let _ = err_reader.join();
                return Err(OcrEvalError::Timeout(limits.timeout));
            }
            None => thread::sleep(Duration::from_millis(5)),
        }
    }
}
fn read_bounded(
    mut stream: impl Read,
    limit: usize,
    label: &'static str,
    overflow: mpsc::Sender<&'static str>,
) -> Result<Vec<u8>, OcrEvalError> {
    let mut bytes = Vec::new();
    let mut overflowed = false;
    let mut chunk = [0_u8; 8192];
    loop {
        let count = stream.read(&mut chunk)?;
        if count == 0 {
            return Ok(bytes);
        }
        if bytes.len().saturating_add(count) > limit {
            if !overflowed {
                overflowed = true;
                let _ = overflow.send(label);
            }
            // Keep draining until the parent has killed and reaped the child;
            // returning here closes the pipe and can leave it blocked forever.
            continue;
        }
        if !overflowed {
            bytes.extend_from_slice(&chunk[..count]);
        }
    }
}
fn join_reader(
    reader: thread::JoinHandle<Result<Vec<u8>, OcrEvalError>>,
) -> Result<Vec<u8>, OcrEvalError> {
    reader
        .join()
        .map_err(|_| OcrEvalError::Invalid("adapter stream reader panicked"))?
}
fn parse_provider_line(
    bytes: &[u8],
    request: &ProviderRequest,
    binding: &DocumentBinding,
) -> Result<ProviderResponse, OcrEvalError> {
    if bytes.is_empty()
        || bytes.ends_with(b"\n\n")
        || bytes[..bytes.len().saturating_sub(1)].contains(&b'\n')
    {
        return Err(OcrEvalError::Invalid(
            "adapter must emit exactly one JSONL response",
        ));
    }
    let response: ProviderResponse =
        serde_json::from_slice(bytes.strip_suffix(b"\n").unwrap_or(bytes))?;
    if response.schema != PROVIDER_RESPONSE_SCHEMA
        || response.request_id != request.request_id
        || response.document_sha256 != binding.sha256
    {
        return Err(OcrEvalError::Invalid(
            "adapter response schema or request identity mismatch",
        ));
    }
    Ok(response)
}

fn parse_render_line(
    bytes: &[u8],
    request: &RenderRequest,
) -> Result<RenderResponse, OcrEvalError> {
    if bytes.is_empty()
        || bytes.ends_with(b"\n\n")
        || bytes[..bytes.len().saturating_sub(1)].contains(&b'\n')
    {
        return Err(OcrEvalError::Invalid(
            "adapter must emit exactly one JSONL response",
        ));
    }
    let response: RenderResponse =
        serde_json::from_slice(bytes.strip_suffix(b"\n").unwrap_or(bytes))?;
    if response.schema != RENDER_RESPONSE_SCHEMA
        || response.request_id != request.request_id
        || response.output_pdf != request.output_pdf
        || response.page_count != request.input_images.len() as u32
        || !valid_sha256(&response.output_sha256)
    {
        return Err(OcrEvalError::Invalid(
            "renderer response schema or identity mismatch",
        ));
    }
    Ok(response)
}

fn validate_adapter_command(command: &AdapterCommand) -> Result<(), OcrEvalError> {
    if command
        .environment
        .keys()
        .any(|key| key != OsStr::new("MISTRAL_API_KEY"))
    {
        return Err(OcrEvalError::Invalid(
            "adapter environment may only contain MISTRAL_API_KEY",
        ));
    }
    for path in [&command.python, &command.adapter] {
        if !path.is_absolute() {
            return Err(OcrEvalError::AdapterPath(path.to_owned()));
        }
        if fs::canonicalize(path)? != *path {
            return Err(OcrEvalError::Invalid(
                "adapter command paths must be canonical absolute paths",
            ));
        }
        let meta = fs::symlink_metadata(path)?;
        if !meta.file_type().is_file() {
            return Err(OcrEvalError::Invalid(
                "adapter command must use regular non-symlink files",
            ));
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if path == &command.python && meta.permissions().mode() & 0o111 == 0 {
                return Err(OcrEvalError::Invalid("python executable is not executable"));
            }
        }
    }
    Ok(())
}

#[cfg(unix)]
fn configure_process_group(command: &mut Command) {
    use std::os::unix::process::CommandExt;
    unsafe {
        command.pre_exec(|| {
            if libc::setsid() == -1 {
                Err(io::Error::last_os_error())
            } else {
                Ok(())
            }
        });
    }
}
#[cfg(not(unix))]
fn configure_process_group(_: &mut Command) {}
#[cfg(unix)]
fn terminate_process_group(child: &mut std::process::Child) {
    unsafe {
        libc::kill(-(child.id() as i32), libc::SIGKILL);
    }
    let _ = child.kill();
}
#[cfg(not(unix))]
fn terminate_process_group(child: &mut std::process::Child) {
    let _ = child.kill();
}

fn hex_sha256(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}
fn base64_encode(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut output = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let value = (u32::from(chunk[0]) << 16)
            | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8)
            | u32::from(*chunk.get(2).unwrap_or(&0));
        output.push(TABLE[((value >> 18) & 63) as usize] as char);
        output.push(TABLE[((value >> 12) & 63) as usize] as char);
        output.push(if chunk.len() > 1 {
            TABLE[((value >> 6) & 63) as usize] as char
        } else {
            '='
        });
        output.push(if chunk.len() > 2 {
            TABLE[(value & 63) as usize] as char
        } else {
            '='
        });
    }
    output
}
fn base64_decode(value: &str) -> Result<Vec<u8>, OcrEvalError> {
    if !value.len().is_multiple_of(4) {
        return Err(OcrEvalError::Invalid("invalid provider base64 payload"));
    }
    let mut output = Vec::with_capacity(value.len() / 4 * 3);
    for (position, chunk) in value.as_bytes().as_chunks::<4>().0.iter().enumerate() {
        let padding = usize::from(chunk[2] == b'=') + usize::from(chunk[3] == b'=');
        if padding > 0 && position + 1 != value.len() / 4 {
            return Err(OcrEvalError::Invalid("invalid provider base64 padding"));
        }
        let decode = |byte: u8| -> Option<u8> {
            match byte {
                b'A'..=b'Z' => Some(byte - b'A'),
                b'a'..=b'z' => Some(byte - b'a' + 26),
                b'0'..=b'9' => Some(byte - b'0' + 52),
                b'+' => Some(62),
                b'/' => Some(63),
                _ => None,
            }
        };
        if (chunk[2] == b'=' && chunk[3] != b'=') || chunk[0] == b'=' || chunk[1] == b'=' {
            return Err(OcrEvalError::Invalid("invalid provider base64 padding"));
        }
        let a = decode(chunk[0]).ok_or(OcrEvalError::Invalid("invalid provider base64 payload"))?;
        let b = decode(chunk[1]).ok_or(OcrEvalError::Invalid("invalid provider base64 payload"))?;
        let c = if chunk[2] == b'=' {
            0
        } else {
            decode(chunk[2]).ok_or(OcrEvalError::Invalid("invalid provider base64 payload"))?
        };
        let d = if chunk[3] == b'=' {
            0
        } else {
            decode(chunk[3]).ok_or(OcrEvalError::Invalid("invalid provider base64 payload"))?
        };
        output.push((a << 2) | (b >> 4));
        if padding < 2 {
            output.push((b << 4) | (c >> 2));
        }
        if padding == 0 {
            output.push((c << 6) | d);
        }
    }
    Ok(output)
}
fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn truth() -> GroundTruth {
        parse_ground_truth(r#"{"schema":"kio.ocr.ground-truth/v1","table":{"page_index":0,"expected_cell_texts":["Alpha","Beta"]},"japanese":{"page_index":1,"full_text":"日本 語"},"images":{"page_index":2,"expected_count":2},"formula":{"page_index":3,"expected_tokens":["E=mc^2"]}}"#.as_bytes()).unwrap()
    }
    fn response() -> OcrResponse {
        parse_response(r#"{"schema":"kio.ocr.response/v1","pages":[{"index":0,"markdown":"| alpha | BETA |"},{"index":1,"markdown":"xx日本語yy"},{"index":2,"markdown":"","images":[{},{}]},{"index":3,"markdown":"E = mc^2"}]}"#.as_bytes()).unwrap()
    }
    #[test]
    fn vectors_cover_metrics_and_verdict() {
        let report = evaluate(&truth(), &response()).unwrap();
        assert_eq!(report.verdict, Verdict::Passed);
        assert_eq!(report.table.recall, 1.0);
        assert_eq!(report.japanese.cer, 0.0);
        assert_eq!(
            report.formula.classification,
            FormulaClassification::Textized
        );
    }
    #[test]
    fn image_fallback_is_classified_without_changing_core_verdict() {
        let mut response = response();
        response.pages[3].markdown.clear();
        response.pages[3].images.push(serde_json::json!({}));
        let report = evaluate(&truth(), &response).unwrap();
        assert_eq!(
            report.formula.classification,
            FormulaClassification::ImageFallback
        );
        assert_eq!(report.verdict, Verdict::Passed);
    }
    #[test]
    fn malformed_and_duplicate_pages_are_rejected() {
        assert!(
            parse_response(
                br#"{"schema":"kio.ocr.response/v1","pages":[{"index":0},{"index":0}]}"#
            )
            .is_err()
        );
        assert!(parse_ground_truth(br#"{"schema":"v0"}"#).is_err());
    }
    #[test]
    fn adapter_schema_is_one_line_and_identity_bound() {
        let request = ProviderRequest {
            schema: PROVIDER_REQUEST_SCHEMA.into(),
            request_id: "r1".into(),
            model: "mistral-ocr-latest".into(),
            media_type: "application/pdf".into(),
            document_bytes: 3,
            document_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                .into(),
            document_base64: "YWJj".into(),
            include_image_base64: true,
        };
        let binding = DocumentBinding {
            path: PathBuf::from("/tmp/a.pdf"),
            bytes: 3,
            sha256: request.document_sha256.clone(),
        };
        let parsed = parse_provider_line(
            b"{\"schema\":\"kio.ocr.provider-response/v1\",\"request_id\":\"r1\",\"document_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"response\":{}}\n",
            &request,
            &binding,
        )
        .unwrap();
        assert_eq!(parsed.request_id, "r1");
        assert!(parse_provider_line(b"{}\n{}\n", &request, &binding).is_err());
    }
    #[test]
    fn explicit_document_binding_and_create_only_report_are_enforced() {
        let directory = tempfile::tempdir().unwrap();
        let document = directory.path().join("fixture.pdf");
        fs::write(&document, b"fixture-pdf").unwrap();
        let binding = bind_document(&document).unwrap();
        assert_eq!(binding.bytes, 11);
        let request = ProviderRequest {
            schema: PROVIDER_REQUEST_SCHEMA.into(),
            request_id: "r2".into(),
            model: "mistral-ocr-latest".into(),
            media_type: "application/pdf".into(),
            document_bytes: binding.bytes,
            document_sha256: binding.sha256.clone(),
            document_base64: base64_encode(b"fixture-pdf"),
            include_image_base64: false,
        };
        let request_binding = bind_provider_request(&request).unwrap();
        assert_eq!(request_binding.bytes, binding.bytes);
        assert_eq!(request_binding.sha256, binding.sha256);
        let report = evaluate(&truth(), &response()).unwrap();
        let report_path = directory.path().join("report.json");
        write_report_create_only(&report_path, &report).unwrap();
        assert!(matches!(
            write_report_create_only(&report_path, &report),
            Err(OcrEvalError::ReportAlreadyExists(_))
        ));
        let response_path = directory.path().join("response.json");
        write_response_create_only(&response_path, &response()).unwrap();
        let response_bytes = fs::read(&response_path).unwrap();
        assert!(response_bytes.ends_with(b"\n"));
        assert_eq!(
            parse_response(&response_bytes).unwrap().schema,
            RESPONSE_SCHEMA
        );
    }

    #[cfg(unix)]
    #[test]
    fn document_binding_rejects_symlink_and_hardlink_aliases() {
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().unwrap();
        let document = directory.path().join("fixture.pdf");
        fs::write(&document, b"fixture-pdf").unwrap();
        let symlink_path = directory.path().join("symlink.pdf");
        symlink(&document, &symlink_path).unwrap();
        assert!(bind_document(&symlink_path).is_err());

        let hardlink_path = directory.path().join("hardlink.pdf");
        fs::hard_link(&document, &hardlink_path).unwrap();
        assert!(bind_document(&document).is_err());
        assert!(bind_document(&hardlink_path).is_err());
    }

    #[test]
    fn provider_payload_is_normalized_into_the_closed_response_schema() {
        let provider = ProviderResponse {
            schema: PROVIDER_RESPONSE_SCHEMA.into(),
            request_id: "r3".into(),
            document_sha256: "a".repeat(64),
            response: serde_json::json!({
                "pages": [{"index": 0, "markdown": "ok", "images": [], "provider_extra": true}],
                "model": "mistral-ocr-latest"
            }),
        };
        let normalized = normalize_provider_response(&provider).unwrap();
        assert_eq!(normalized.schema, RESPONSE_SCHEMA);
        assert_eq!(normalized.pages[0].markdown, "ok");
        assert!(
            normalize_provider_response(&ProviderResponse {
                response: serde_json::json!({"pages": [{"index": 0, "markdown": 2}]}),
                ..provider
            })
            .is_err()
        );
    }

    #[test]
    fn renderer_response_is_identity_bound_and_create_only() {
        let directory = tempfile::tempdir().unwrap();
        let output = directory.path().join("out.pdf");
        let image = directory.path().join("one.png");
        fs::write(&image, b"image").unwrap();
        let request = RenderRequest {
            schema: RENDER_REQUEST_SCHEMA.into(),
            request_id: "render-1".into(),
            output_pdf: output.to_string_lossy().into_owned(),
            input_images: vec![image.to_string_lossy().into_owned()],
        };
        validate_render_request(&request).unwrap();
        let response = format!(
            "{{\"schema\":\"{RENDER_RESPONSE_SCHEMA}\",\"request_id\":\"render-1\",\"output_pdf\":\"{}\",\"output_bytes\":1,\"output_sha256\":\"{}\",\"page_count\":1}}\n",
            output.display(),
            "a".repeat(64)
        );
        assert_eq!(
            parse_render_line(response.as_bytes(), &request)
                .unwrap()
                .page_count,
            1
        );
        fs::write(&output, b"existing").unwrap();
        assert!(validate_render_request(&request).is_err());
    }

    #[test]
    fn oversized_png_header_is_rejected_without_a_decoder() {
        let directory = tempfile::tempdir().unwrap();
        let image = directory.path().join("bomb.png");
        let mut header = Vec::from(&b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR"[..]);
        header.extend_from_slice(&100_000_u32.to_be_bytes());
        header.extend_from_slice(&100_000_u32.to_be_bytes());
        fs::write(&image, header).unwrap();
        assert!(png_pixels(&fs::read(&image).unwrap()).unwrap() > MAX_RENDER_IMAGE_PIXELS);
    }

    #[test]
    fn overflowing_pipe_signals_before_drain_completes() {
        let (sender, receiver) = mpsc::channel();
        let bytes = vec![b'x'; 32];
        let drained = read_bounded(std::io::Cursor::new(bytes), 8, "stdout", sender).unwrap();
        assert!(drained.is_empty());
        assert_eq!(receiver.try_recv().unwrap(), "stdout");
    }
}
