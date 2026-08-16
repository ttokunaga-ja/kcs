//! Mistral OCR Batch client contract (07 §5.7) and its hermetic mock seam.
//!
//! The ledger state machine for batch submissions (04 §5.8 — phase 1 intent,
//! phase 2a upload, phase 2b job-create, phase 3 collect, sweep/recovery)
//! has been fully normed and implemented since QA13-15; what was missing is
//! the SEND LANE itself. This module fixes the client-side contract the lane
//! is written against. Verified request/response shapes come from the
//! 2026-07-03 live verification harness (`experiments/ocr-verification`,
//! 07 §5.2 末尾):
//!
//! - batch input JSONL line: `{"custom_id": …, "body": {"document": {…data
//!   URI…}, "include_image_base64": true, …}}` (model rides the JOB, not the
//!   line body)
//! - job object: in-flight `status` ∈ {QUEUED, RUNNING}; terminal success =
//!   SUCCESS; the result file id is `output_file`
//! - output JSONL line: `{"id": …, "custom_id": …, "response":
//!   {"status_code": 200, "body": {…standard OCR response…}}}`
//!
//! `KIO_TEST_MISTRAL_BATCH` carries an inline JSON script for hermetic
//! tests. Because one CLI invocation = one process, the script's poll
//! progression persists in an explicit `state_path` file, so a submit run
//! and a later collect run see a coherent QUEUED → … → SUCCESS sequence.

use std::io::Write;

use serde::Deserialize;
use serde_json::Value;

use crate::http_policy::{
    HttpPolicy, OCR_RESPONSE_MAX_BYTES, authenticated_agent, read_bytes_bounded, read_json_bounded,
    require_success,
};
use crate::mistral_ocr::{http_error, http_status_error};
use crate::{AdapterError, Result};

/// Inline-JSON mock script env var (per-Command in tests; see
/// `catalog::TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV` for the house style).
pub const TEST_MISTRAL_BATCH_ENV: &str = "KIO_TEST_MISTRAL_BATCH";

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BatchJobStatus {
    Queued,
    Running,
    Success,
    Failed,
    TimeoutExceeded,
    Cancelled,
    Other(String),
}

impl BatchJobStatus {
    #[must_use]
    pub fn parse(raw: &str) -> Self {
        match raw.trim().to_ascii_uppercase().as_str() {
            "QUEUED" => Self::Queued,
            "RUNNING" => Self::Running,
            "SUCCESS" | "SUCCEEDED" | "COMPLETED" => Self::Success,
            "FAILED" => Self::Failed,
            "TIMEOUT_EXCEEDED" => Self::TimeoutExceeded,
            "CANCELLED" | "CANCELLATION_REQUESTED" => Self::Cancelled,
            other => Self::Other(other.to_owned()),
        }
    }

    /// Whether the provider may still transition this job (poll again later).
    #[must_use]
    pub fn is_in_flight(&self) -> bool {
        matches!(self, Self::Queued | Self::Running)
    }
}

#[derive(Debug, Clone)]
pub struct BatchJobRecord {
    pub job_id: String,
    pub status: BatchJobStatus,
    /// Provider file id of the result JSONL once `status` is `Success`.
    pub output_file_id: Option<String>,
    /// Job metadata exactly as the provider returns it (07 §5.7: create_job
    /// metadata must round-trip完全・不変 — the intent_token and the task
    /// key 4 組 ride here for recovery attribution, 10 §7.5.2).
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone)]
pub struct BatchUploadRecord {
    pub upload_id: String,
    /// Client-chosen filename (the intent_token embedding is the ONLY
    /// attribution an upload carries — 04 §5.8 発見キー).
    pub filename: String,
}

#[derive(Debug, Clone)]
pub struct BatchOutputLine {
    pub custom_id: String,
    pub status_code: u16,
    pub body: serde_json::Value,
}

/// 07 §5.7 client operations. One provider job carries ONE task's input in
/// this lane's v1 (1 job = 1 task) so the per-task-key `batch_job_id` column
/// keys the recovery walk without job↔task fan-out bookkeeping.
pub trait MistralBatchClient {
    fn provider_scope_id(&self) -> Result<String>;
    /// Upload a batch-input JSONL; returns the provider file id.
    fn upload_batch_input(&self, jsonl: &[u8], filename: &str) -> Result<String>;
    fn create_job(
        &self,
        input_file_id: &str,
        model: &str,
        metadata: &serde_json::Value,
    ) -> Result<BatchJobRecord>;
    fn get_job(&self, job_id: &str) -> Result<BatchJobRecord>;
    fn list_jobs(&self) -> Result<Vec<BatchJobRecord>>;
    fn list_uploads(&self) -> Result<Vec<BatchUploadRecord>>;
    /// Provider 404 (already gone) reports as success (07 §5.7).
    fn delete_upload(&self, upload_id: &str) -> Result<()>;
    fn fetch_output(&self, output_file_id: &str) -> Result<Vec<BatchOutputLine>>;
}

/// One batch-input JSONL line (custom_id + the same request body the sync
/// lane sends, minus the model — the model rides the job).
#[must_use]
pub fn batch_input_line(custom_id: &str, body: &serde_json::Value) -> String {
    serde_json::json!({ "custom_id": custom_id, "body": body }).to_string()
}

/// The batch-input request body for one OCR task (verified shape: the sync
/// lane's document payload + `include_image_base64`, WITHOUT the model —
/// the model rides the job). `pages` carries the incremental page subset
/// exactly like the sync lane's `pages` field; `None` = mode=Full.
/// `bbox_annotation` attaches the same A.2 `bbox_annotation_format` value
/// the sync lane sends — bbox-enabled tasks MUST stay on the batch lane
/// (2026-07-23 ruling: OCR spending is batch-only), and bbox defaults to ON
/// (`effective_bbox_annotation_policy`), so the batch body has to carry it.
#[must_use]
pub fn ocr_batch_body(
    media_type: &str,
    bytes: &[u8],
    pages: Option<&[u32]>,
    bbox_annotation: bool,
) -> serde_json::Value {
    use base64::Engine as _;
    let encoded = base64::engine::general_purpose::STANDARD.encode(bytes);
    let data_uri = format!("data:{media_type};base64,{encoded}");
    let document = if media_type.starts_with("image/") {
        serde_json::json!({ "type": "image_url", "image_url": data_uri })
    } else {
        serde_json::json!({ "type": "document_url", "document_url": data_uri })
    };
    let mut body = serde_json::json!({
        "document": document,
        "include_image_base64": true,
    });
    if let Some(pages) = pages {
        body["pages"] = serde_json::json!(pages);
    }
    if bbox_annotation {
        body["bbox_annotation_format"] = crate::bbox_annotation::bbox_annotation_format();
    }
    body
}

/// Upload filename convention: the intent_token embedding is the ONLY
/// attribution an upload carries (04 §5.8 発見キー / 10 §7.5.2 — an upload
/// whose filename token cannot be parsed is unknown, report-only).
#[must_use]
pub fn batch_upload_filename(intent_token: &str) -> String {
    format!("kio-{intent_token}.jsonl")
}

/// Inverse of [`batch_upload_filename`].
#[must_use]
pub fn filename_intent_token(filename: &str) -> Option<&str> {
    filename.strip_prefix("kio-")?.strip_suffix(".jsonl")
}

// ---------------------------------------------------------------------------
// Real client (EnvMistralBatchClient)
// ---------------------------------------------------------------------------

/// Workspace/provider-scope override for [`MistralBatchClient::provider_scope_id`]
/// (v1 裁定: trimmed env value when set, else [`DEFAULT_PROVIDER_SCOPE_ID`]).
pub const MISTRAL_WORKSPACE_ID_ENV: &str = "KIO_MISTRAL_WORKSPACE_ID";

/// The provider scope recorded when no workspace id is configured. Mistral's
/// API key is itself workspace-scoped, so one constant scope per client
/// configuration is a faithful v1 identity.
pub const DEFAULT_PROVIDER_SCOPE_ID: &str = "mistral:default";

/// Metadata-class responses (upload object, job object, one listing page) are
/// small; 1 MiB is the same ceiling class as
/// `http_policy::MODEL_CATALOG_MAX_BYTES`. Only `fetch_output` reads a
/// document-scale payload (`OCR_RESPONSE_MAX_BYTES`).
const BATCH_METADATA_MAX_BYTES: usize = 1024 * 1024;

/// Listing pagination page size (`page_size` query parameter).
const BATCH_LIST_PAGE_SIZE: usize = 100;

/// Hard bound on the pagination walk: 50 pages × 100 entries = 5,000 provider
/// objects — far beyond a single-user MVP workspace. The walk STOPS at the
/// bound (a bounded, report-only inventory scan, 10 §7.5.2), it does not
/// error; the pending real-API contract round (07 §5.2) revisits the bound.
const BATCH_LIST_MAX_PAGES: usize = 50;

/// Real Mistral Batch REST client (07 §5.7). Auth, base-url, and redirect/
/// encoding posture mirror `mistral_ocr::EnvMistralOcrClient` exactly: the
/// R13-2 `tools.toml [markdown] auth` resolution (fallback `MISTRAL_API_KEY`),
/// `MISTRAL_API_BASE` honored only when no `[markdown]` adapter is declared,
/// `authenticated_agent` (redirects(0), strict timeouts), forced identity
/// encoding, and bounded reads. Request/response shapes are the 2026-07-03
/// archived 2026-07-03 live-verification record (07 §5.2 末尾).
#[derive(Debug, Clone, Default)]
pub struct EnvMistralBatchClient {
    base_url: Option<String>,
    http_policy: HttpPolicy,
}

impl EnvMistralBatchClient {
    #[must_use]
    pub fn new() -> Self {
        Self {
            base_url: None,
            http_policy: HttpPolicy::default(),
        }
    }

    #[allow(dead_code)]
    #[must_use]
    pub fn with_base_url(base_url: impl Into<String>) -> Self {
        Self {
            base_url: Some(base_url.into()),
            http_policy: HttpPolicy::default(),
        }
    }

    /// Mirror of `EnvMistralOcrClient::base_url` — the `MISTRAL_API_BASE`
    /// override is honored only when no `tools.toml` `[markdown]` adapter is
    /// declared.
    fn base_url(&self) -> String {
        self.base_url
            .clone()
            .or_else(|| {
                crate::tool_lock::registered_declared_adapter("markdown")
                    .is_none()
                    .then(|| std::env::var("MISTRAL_API_BASE").ok())
                    .flatten()
            })
            .unwrap_or_else(|| "https://api.mistral.ai".to_owned())
            .trim_end_matches('/')
            .to_owned()
    }

    /// Mirror of `EnvMistralOcrClient::api_key` (R13-2: a declared
    /// `tools.toml [markdown] auth` wins; legacy `MISTRAL_API_KEY` fallback).
    fn api_key() -> Result<String> {
        crate::tool_lock::resolve_role_api_key("markdown", "MISTRAL_API_KEY")?.ok_or_else(|| {
            AdapterError::Auth(
                "no Mistral OCR API key: set MISTRAL_API_KEY or a tools.toml `[markdown] auth`"
                    .to_owned(),
            )
        })
    }

    /// Authenticated GET returning a bounded metadata-class JSON body.
    fn get_json(&self, url: &str, context: &str) -> Result<Value> {
        let api_key = Self::api_key()?;
        let response = authenticated_agent(self.http_policy)
            .get(url)
            .header("Authorization", &format!("Bearer {api_key}"))
            .header("Accept-Encoding", "identity")
            .call()
            .map_err(http_error)
            .and_then(|response| require_success(response, http_status_error))?;
        read_json_bounded(response, BATCH_METADATA_MAX_BYTES, context)
    }

    /// Bounded pagination walk over `{url_prefix}&page=N` (N = 0, 1, …).
    /// Stops on an empty `data` page, on `total` coverage, or at
    /// [`BATCH_LIST_MAX_PAGES`].
    fn list_walk(&self, url_prefix: &str, context: &str) -> Result<Vec<Value>> {
        let mut entries: Vec<Value> = Vec::new();
        for page in 0..BATCH_LIST_MAX_PAGES {
            let value = self.get_json(&format!("{url_prefix}&page={page}"), context)?;
            let data = value.get("data").and_then(Value::as_array).ok_or_else(|| {
                AdapterError::ContractViolation(format!("{context} missing data array"))
            })?;
            if data.is_empty() {
                break;
            }
            entries.extend(data.iter().cloned());
            let total = value.get("total").and_then(Value::as_u64);
            if total.is_some_and(|total| entries.len() as u64 >= total) {
                break;
            }
        }
        Ok(entries)
    }
}

impl MistralBatchClient for EnvMistralBatchClient {
    /// v1 裁定: `KIO_MISTRAL_WORKSPACE_ID` (env/config), trimmed, when
    /// non-empty; else the constant [`DEFAULT_PROVIDER_SCOPE_ID`].
    ///
    /// 07 §5.2 の未実施契約試験 (list_uploads / provider_scope_id /
    /// pagination) は実 API 実測ラウンドで置換予定 — until that round, this
    /// identity is config-derived, never fetched from the provider.
    fn provider_scope_id(&self) -> Result<String> {
        match std::env::var(MISTRAL_WORKSPACE_ID_ENV) {
            Ok(raw) if !raw.trim().is_empty() => Ok(raw.trim().to_owned()),
            _ => Ok(DEFAULT_PROVIDER_SCOPE_ID.to_owned()),
        }
    }

    /// `POST {base}/v1/files` — multipart/form-data with `purpose="batch"`
    /// and `file=(filename, JSONL bytes)`; returns the provider file `id`.
    fn upload_batch_input(&self, jsonl: &[u8], filename: &str) -> Result<String> {
        validate_multipart_filename(filename)?;
        let api_key = Self::api_key()?;
        let boundary = multipart_boundary(jsonl)?;
        let body = multipart_form_body(&boundary, filename, jsonl);
        let response = authenticated_agent(self.http_policy)
            .post(&format!("{}/v1/files", self.base_url()))
            .header("Authorization", &format!("Bearer {api_key}"))
            .header("Accept-Encoding", "identity")
            .header(
                "Content-Type",
                &format!("multipart/form-data; boundary={boundary}"),
            )
            .send(&body)
            .map_err(http_error)
            .and_then(|response| require_success(response, http_status_error))?;
        let value = read_json_bounded(
            response,
            BATCH_METADATA_MAX_BYTES,
            "Mistral file upload response",
        )?;
        value
            .get("id")
            .and_then(Value::as_str)
            .filter(|id| !id.is_empty())
            .map(str::to_owned)
            .ok_or_else(|| {
                AdapterError::ContractViolation(
                    "Mistral file upload response missing id".to_owned(),
                )
            })
    }

    /// `POST {base}/v1/batch/jobs` — the verified job-create body: the model
    /// rides the JOB (`input_files` carries the uploaded file id), and
    /// `metadata` is sent verbatim (07 §5.7: it must round-trip 完全・不変;
    /// the intent_token + task key 4 組 ride here, 10 §7.5.2).
    fn create_job(
        &self,
        input_file_id: &str,
        model: &str,
        metadata: &serde_json::Value,
    ) -> Result<BatchJobRecord> {
        let api_key = Self::api_key()?;
        let response = authenticated_agent(self.http_policy)
            .post(&format!("{}/v1/batch/jobs", self.base_url()))
            .header("Authorization", &format!("Bearer {api_key}"))
            .header("Accept-Encoding", "identity")
            .send_json(serde_json::json!({
                "input_files": [input_file_id],
                "endpoint": "/v1/ocr",
                "model": model,
                "metadata": metadata,
            }))
            .map_err(http_error)
            .and_then(|response| require_success(response, http_status_error))?;
        let value = read_json_bounded(
            response,
            BATCH_METADATA_MAX_BYTES,
            "Mistral batch job response",
        )?;
        parse_job_record(&value)
    }

    fn get_job(&self, job_id: &str) -> Result<BatchJobRecord> {
        let value = self.get_json(
            &format!("{}/v1/batch/jobs/{job_id}", self.base_url()),
            "Mistral batch job response",
        )?;
        parse_job_record(&value)
    }

    fn list_jobs(&self) -> Result<Vec<BatchJobRecord>> {
        let base = self.base_url();
        self.list_walk(
            &format!("{base}/v1/batch/jobs?page_size={BATCH_LIST_PAGE_SIZE}"),
            "Mistral batch jobs listing",
        )?
        .iter()
        .map(parse_job_record)
        .collect()
    }

    fn list_uploads(&self) -> Result<Vec<BatchUploadRecord>> {
        let base = self.base_url();
        self.list_walk(
            &format!("{base}/v1/files?purpose=batch&page_size={BATCH_LIST_PAGE_SIZE}"),
            "Mistral batch files listing",
        )?
        .iter()
        .map(parse_upload_record)
        .collect()
    }

    /// `DELETE {base}/v1/files/{id}` — provider 404 (already gone) reports as
    /// success (07 §5.7): the sweep's delete is idempotent by contract.
    fn delete_upload(&self, upload_id: &str) -> Result<()> {
        let api_key = Self::api_key()?;
        let response = authenticated_agent(self.http_policy)
            .delete(&format!("{}/v1/files/{upload_id}", self.base_url()))
            .header("Authorization", &format!("Bearer {api_key}"))
            .header("Accept-Encoding", "identity")
            .call()
            .map_err(http_error)?;
        if response.status().as_u16() == 404 {
            Ok(())
        } else {
            require_success(response, http_status_error).map(|_| ())
        }
    }

    /// `GET {base}/v1/files/{id}/content` — the result JSONL, one
    /// `{"custom_id", "response": {"status_code", "body"}}` envelope per line
    /// (the verified `out-batch/batch_results.jsonl` shape). Read under the
    /// document-scale `OCR_RESPONSE_MAX_BYTES` ceiling.
    fn fetch_output(&self, output_file_id: &str) -> Result<Vec<BatchOutputLine>> {
        let api_key = Self::api_key()?;
        let response = authenticated_agent(self.http_policy)
            .get(&format!(
                "{}/v1/files/{output_file_id}/content",
                self.base_url()
            ))
            .header("Authorization", &format!("Bearer {api_key}"))
            .header("Accept-Encoding", "identity")
            .call()
            .map_err(http_error)
            .and_then(|response| require_success(response, http_status_error))?;
        let body = read_bytes_bounded(
            response,
            OCR_RESPONSE_MAX_BYTES,
            "Mistral batch output file",
        )?;
        parse_output_jsonl(&body)
    }
}

fn parse_job_record(value: &Value) -> Result<BatchJobRecord> {
    let job_id = value
        .get("id")
        .and_then(Value::as_str)
        .filter(|id| !id.is_empty())
        .ok_or_else(|| {
            AdapterError::ContractViolation("Mistral batch job object missing id".to_owned())
        })?;
    let status_raw = value.get("status").and_then(Value::as_str).ok_or_else(|| {
        AdapterError::ContractViolation(format!("Mistral batch job {job_id} missing status"))
    })?;
    Ok(BatchJobRecord {
        job_id: job_id.to_owned(),
        status: BatchJobStatus::parse(status_raw),
        output_file_id: value
            .get("output_file")
            .and_then(Value::as_str)
            .map(str::to_owned),
        // 07 §5.7: metadata is whatever the provider returned — verbatim.
        metadata: value.get("metadata").cloned().unwrap_or(Value::Null),
    })
}

fn parse_upload_record(value: &Value) -> Result<BatchUploadRecord> {
    let upload_id = value
        .get("id")
        .and_then(Value::as_str)
        .filter(|id| !id.is_empty())
        .ok_or_else(|| {
            AdapterError::ContractViolation("Mistral file object missing id".to_owned())
        })?;
    Ok(BatchUploadRecord {
        upload_id: upload_id.to_owned(),
        // A missing/null filename yields no intent token downstream — the
        // upload is then `unknown`, report-only (10 §7.5.2), never an error.
        filename: value
            .get("filename")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned(),
    })
}

fn parse_output_jsonl(body: &[u8]) -> Result<Vec<BatchOutputLine>> {
    let text = std::str::from_utf8(body).map_err(|_| {
        AdapterError::ContractViolation("Mistral batch output file is not valid UTF-8".to_owned())
    })?;
    let mut lines = Vec::new();
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let line_no = index + 1;
        let value: Value = serde_json::from_str(line).map_err(|error| {
            AdapterError::ContractViolation(format!("Mistral batch output line {line_no}: {error}"))
        })?;
        let custom_id = value
            .get("custom_id")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                AdapterError::ContractViolation(format!(
                    "Mistral batch output line {line_no} missing custom_id"
                ))
            })?;
        let status_code = value
            .get("response")
            .and_then(|response| response.get("status_code"))
            .and_then(Value::as_u64)
            .and_then(|code| u16::try_from(code).ok())
            .ok_or_else(|| {
                AdapterError::ContractViolation(format!(
                    "Mistral batch output line {line_no} missing response.status_code"
                ))
            })?;
        lines.push(BatchOutputLine {
            custom_id: custom_id.to_owned(),
            status_code,
            body: value
                .get("response")
                .and_then(|response| response.get("body"))
                .cloned()
                .unwrap_or(Value::Null),
        });
    }
    Ok(lines)
}

/// The upload filename crosses into a multipart header line; refuse anything
/// that could break out of the quoted `filename="…"` token. Real callers pass
/// [`batch_upload_filename`] output (`kio-<intent_token>.jsonl`), which is
/// always ASCII-graphic and quote-free.
fn validate_multipart_filename(filename: &str) -> Result<()> {
    let safe = !filename.is_empty()
        && filename
            .bytes()
            .all(|byte| byte.is_ascii_graphic() && byte != b'"' && byte != b'\\');
    if safe {
        Ok(())
    } else {
        Err(AdapterError::ContractViolation(
            "batch upload filename contains characters unsafe for a multipart header".to_owned(),
        ))
    }
}

/// OS-entropy multipart boundary, re-drawn (bounded) if the 128-bit value
/// ever appears in the payload (RFC 2046: a boundary must not occur in the
/// enclosed data).
fn multipart_boundary(payload: &[u8]) -> Result<String> {
    for _ in 0..4 {
        let mut raw = [0_u8; 16];
        getrandom::fill(&mut raw).map_err(|error| AdapterError::Io {
            path: "os:getrandom".to_owned(),
            message: error.to_string(),
        })?;
        let mut boundary = String::with_capacity(10 + raw.len() * 2);
        boundary.push_str("kio-batch-");
        for byte in raw {
            use std::fmt::Write as _;
            let _ = write!(boundary, "{byte:02x}");
        }
        if find_subslice(payload, boundary.as_bytes()).is_none() {
            return Ok(boundary);
        }
    }
    Err(AdapterError::ContractViolation(
        "could not derive a multipart boundary absent from the upload payload".to_owned(),
    ))
}

/// The two-part `multipart/form-data` body the upload endpoint expects:
/// field `purpose` = `batch`, then field `file` = (filename, JSONL bytes).
fn multipart_form_body(boundary: &str, filename: &str, jsonl: &[u8]) -> Vec<u8> {
    let mut body = Vec::with_capacity(jsonl.len() + 512);
    body.extend_from_slice(
        format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n"
        )
        .as_bytes(),
    );
    body.extend_from_slice(
        format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; \
             filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
        )
        .as_bytes(),
    );
    body.extend_from_slice(jsonl);
    body.extend_from_slice(format!("\r\n--{boundary}--\r\n").as_bytes());
    body
}

fn find_subslice(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.is_empty() || haystack.len() < needle.len() {
        return None;
    }
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

// ---------------------------------------------------------------------------
// Hermetic mock (KIO_TEST_MISTRAL_BATCH)
// ---------------------------------------------------------------------------

/// Inline mock script. Every field has a test-friendly default so scripts
/// stay small. `status_sequence` advances one step per `get_job` call,
/// persisted in `state_path` (REQUIRED when the sequence has more than one
/// entry — separate CLI invocations must observe the progression).
#[derive(Debug, Clone, Deserialize)]
pub struct MockBatchScript {
    #[serde(default = "default_scope")]
    pub provider_scope_id: String,
    #[serde(default = "default_upload")]
    pub upload_id: String,
    #[serde(default = "default_job")]
    pub job_id: String,
    #[serde(default = "default_sequence")]
    pub status_sequence: Vec<String>,
    #[serde(default)]
    pub output: Vec<serde_json::Value>,
    /// Fail the NEXT phase after this one completes: "upload" fails
    /// create_job, "create_job" fails get_job, … (crash-window emulation).
    #[serde(default)]
    pub fail_phase: Option<String>,
    #[serde(default)]
    pub jobs_listing: Vec<serde_json::Value>,
    #[serde(default)]
    pub uploads_listing: Vec<serde_json::Value>,
    /// Poll-progression counter file (see struct docs).
    #[serde(default)]
    pub state_path: Option<String>,
    /// When set, every client call appends one JSON line here so contract
    /// tests can assert call order and payloads (upload bytes included as
    /// UTF-8 where valid).
    #[serde(default)]
    pub capture_path: Option<String>,
}

fn default_scope() -> String {
    "mock-workspace".to_owned()
}
fn default_upload() -> String {
    "file-mock-upload-1".to_owned()
}
fn default_job() -> String {
    "batch-mock-job-1".to_owned()
}
fn default_sequence() -> Vec<String> {
    vec!["SUCCESS".to_owned()]
}

pub struct MockBatchClient {
    script: MockBatchScript,
}

impl MockBatchClient {
    pub fn from_env_value(raw: &str) -> Result<Self> {
        let script: MockBatchScript = serde_json::from_str(raw).map_err(|error| {
            AdapterError::ConfigSchema(format!("{TEST_MISTRAL_BATCH_ENV} script: {error}"))
        })?;
        Ok(Self { script })
    }

    fn capture(&self, event: serde_json::Value) {
        let Some(path) = self.script.capture_path.as_deref() else {
            return;
        };
        if let Ok(mut file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
        {
            let _ = writeln!(file, "{event}");
        }
    }

    fn fail_if_scripted(&self, phase: &str) -> Result<()> {
        if self.script.fail_phase.as_deref() == Some(phase) {
            return Err(AdapterError::Network(format!(
                "scripted {phase} failure (mock crash window)"
            )));
        }
        Ok(())
    }

    /// Current poll step (0-based), advanced by one per call when a
    /// state_path is configured; single-entry sequences are stateless.
    fn poll_step(&self) -> usize {
        let Some(path) = self.script.state_path.as_deref() else {
            return self.script.status_sequence.len().saturating_sub(1);
        };
        let current: usize = std::fs::read_to_string(path)
            .ok()
            .and_then(|raw| raw.trim().parse().ok())
            .unwrap_or(0);
        let _ = std::fs::write(path, (current + 1).to_string());
        current.min(self.script.status_sequence.len().saturating_sub(1))
    }

    fn job_record(&self, status_raw: &str) -> BatchJobRecord {
        let status = BatchJobStatus::parse(status_raw);
        BatchJobRecord {
            job_id: self.script.job_id.clone(),
            output_file_id: matches!(status, BatchJobStatus::Success)
                .then(|| format!("{}-output", self.script.job_id)),
            status,
            metadata: serde_json::Value::Null,
        }
    }
}

impl MistralBatchClient for MockBatchClient {
    fn provider_scope_id(&self) -> Result<String> {
        Ok(self.script.provider_scope_id.clone())
    }

    fn upload_batch_input(&self, jsonl: &[u8], filename: &str) -> Result<String> {
        self.capture(serde_json::json!({
            "call": "upload",
            "filename": filename,
            "jsonl": String::from_utf8_lossy(jsonl),
        }));
        self.fail_if_scripted("upload")?;
        Ok(self.script.upload_id.clone())
    }

    fn create_job(
        &self,
        input_file_id: &str,
        model: &str,
        metadata: &serde_json::Value,
    ) -> Result<BatchJobRecord> {
        self.capture(serde_json::json!({
            "call": "create_job",
            "input_file_id": input_file_id,
            "model": model,
            "metadata": metadata,
        }));
        self.fail_if_scripted("create_job")?;
        let mut record = self.job_record(
            self.script
                .status_sequence
                .first()
                .map(String::as_str)
                .unwrap_or("QUEUED"),
        );
        record.metadata = metadata.clone();
        Ok(record)
    }

    fn get_job(&self, job_id: &str) -> Result<BatchJobRecord> {
        self.capture(serde_json::json!({ "call": "get_job", "job_id": job_id }));
        self.fail_if_scripted("get_job")?;
        let step = self.poll_step();
        let status = self
            .script
            .status_sequence
            .get(step)
            .map(String::as_str)
            .unwrap_or("SUCCESS");
        Ok(self.job_record(status))
    }

    fn list_jobs(&self) -> Result<Vec<BatchJobRecord>> {
        self.capture(serde_json::json!({ "call": "list_jobs" }));
        self.script
            .jobs_listing
            .iter()
            .map(|entry| {
                Ok(BatchJobRecord {
                    job_id: entry["job_id"].as_str().unwrap_or_default().to_owned(),
                    status: BatchJobStatus::parse(entry["status"].as_str().unwrap_or("QUEUED")),
                    output_file_id: entry["output_file_id"].as_str().map(str::to_owned),
                    metadata: entry["metadata"].clone(),
                })
            })
            .collect()
    }

    fn list_uploads(&self) -> Result<Vec<BatchUploadRecord>> {
        self.capture(serde_json::json!({ "call": "list_uploads" }));
        Ok(self
            .script
            .uploads_listing
            .iter()
            .map(|entry| BatchUploadRecord {
                upload_id: entry["upload_id"].as_str().unwrap_or_default().to_owned(),
                filename: entry["filename"].as_str().unwrap_or_default().to_owned(),
            })
            .collect())
    }

    fn delete_upload(&self, upload_id: &str) -> Result<()> {
        self.capture(serde_json::json!({ "call": "delete_upload", "upload_id": upload_id }));
        self.fail_if_scripted("delete_upload")?;
        Ok(())
    }

    fn fetch_output(&self, output_file_id: &str) -> Result<Vec<BatchOutputLine>> {
        self.capture(serde_json::json!({ "call": "fetch_output", "file_id": output_file_id }));
        self.fail_if_scripted("fetch_output")?;
        self.script
            .output
            .iter()
            .map(|line| {
                Ok(BatchOutputLine {
                    custom_id: line["custom_id"].as_str().unwrap_or_default().to_owned(),
                    status_code: line["response"]["status_code"].as_u64().unwrap_or(200) as u16,
                    body: line["response"]["body"].clone(),
                })
            })
            .collect()
    }
}

/// The configured batch client, if any. Resolution order mirrors the other
/// adapter seams: the inline mock script wins; otherwise the real
/// [`EnvMistralBatchClient`] when the Mistral OCR adapter is configured —
/// the SAME condition the sync send path resolves its credential under
/// (`EnvMistralOcrClient::api_key`: a declared `tools.toml [markdown] auth`
/// wins, else the legacy `MISTRAL_API_KEY` env var); otherwise `None`.
/// A declared-but-broken credential (`keychain:` / invalid runtime target)
/// stays a loud error here, exactly as it is on the sync path.
pub fn configured_mistral_batch_client() -> Result<Option<Box<dyn MistralBatchClient>>> {
    if let Ok(raw) = std::env::var(TEST_MISTRAL_BATCH_ENV)
        && !raw.trim().is_empty()
    {
        return Ok(Some(Box::new(MockBatchClient::from_env_value(&raw)?)));
    }
    if crate::tool_lock::resolve_role_api_key("markdown", "MISTRAL_API_KEY")?.is_some() {
        return Ok(Some(Box::new(EnvMistralBatchClient::new())));
    }
    Ok(None)
}

/// Crate-wide test-only env lock. `std::env::set_var`/`remove_var` are
/// process-global and `cargo test` is multi-threaded; every test that touches
/// `MISTRAL_API_KEY` / [`TEST_MISTRAL_BATCH_ENV`] / [`MISTRAL_WORKSPACE_ID_ENV`]
/// / `batch_inventory::TEST_BATCH_INVENTORY_ENV` must hold THIS lock (a
/// module-local lock cannot serialize against another module's tests over the
/// same variables — batch_client and batch_inventory share all four).
#[cfg(test)]
pub(crate) fn test_env_lock() -> &'static std::sync::Mutex<()> {
    static LOCK: std::sync::OnceLock<std::sync::Mutex<()>> = std::sync::OnceLock::new();
    LOCK.get_or_init(|| std::sync::Mutex::new(()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn status_parse_covers_verified_values() {
        assert!(BatchJobStatus::parse("QUEUED").is_in_flight());
        assert!(BatchJobStatus::parse("running").is_in_flight());
        assert_eq!(BatchJobStatus::parse("SUCCESS"), BatchJobStatus::Success);
        assert_eq!(BatchJobStatus::parse("FAILED"), BatchJobStatus::Failed);
        assert!(!BatchJobStatus::parse("TIMEOUT_EXCEEDED").is_in_flight());
    }

    #[test]
    fn ocr_batch_body_carries_bbox_annotation_format_when_enabled() {
        let with = ocr_batch_body("application/pdf", b"%PDF", None, true);
        assert_eq!(
            with["bbox_annotation_format"],
            crate::bbox_annotation::bbox_annotation_format(),
            "bbox-enabled batch bodies must carry the exact sync-lane format"
        );
        let without = ocr_batch_body("application/pdf", b"%PDF", None, false);
        assert!(without.get("bbox_annotation_format").is_none());
    }

    #[test]
    fn batch_input_line_matches_verified_envelope() {
        let line = batch_input_line("task-1", &serde_json::json!({"document": {"type": "d"}}));
        let parsed: serde_json::Value = serde_json::from_str(&line).unwrap();
        assert_eq!(parsed["custom_id"], "task-1");
        assert!(parsed["body"]["document"].is_object());
    }

    #[test]
    fn mock_sequence_advances_across_instances_via_state_path() {
        let dir = tempfile::tempdir().unwrap();
        let state = dir.path().join("poll-state");
        let script = serde_json::json!({
            "status_sequence": ["QUEUED", "RUNNING", "SUCCESS"],
            "state_path": state.display().to_string(),
        });
        let make = || MockBatchClient::from_env_value(&script.to_string()).unwrap();
        assert!(make().get_job("j").unwrap().status.is_in_flight());
        assert!(make().get_job("j").unwrap().status.is_in_flight());
        assert_eq!(make().get_job("j").unwrap().status, BatchJobStatus::Success);
        // Sequence saturates at its terminal entry.
        assert_eq!(make().get_job("j").unwrap().status, BatchJobStatus::Success);
    }

    #[test]
    fn upload_filename_roundtrip_embeds_and_recovers_the_intent_token() {
        let filename = batch_upload_filename("01HTOKEN123");
        assert_eq!(filename, "kio-01HTOKEN123.jsonl");
        assert_eq!(filename_intent_token(&filename), Some("01HTOKEN123"));
        // Foreign filenames carry no token — unknown attribution (10 §7.5.2).
        assert_eq!(filename_intent_token("notes.bin"), None);
        assert_eq!(filename_intent_token("kio-01HTOKEN123.txt"), None);
        assert_eq!(filename_intent_token("01HTOKEN123.jsonl"), None);
    }

    // -----------------------------------------------------------------------
    // EnvMistralBatchClient — hermetic real-HTTP tests. Same posture as
    // http_policy.rs: a local TcpListener writes synthetic responses; no
    // network leaves the process.
    // -----------------------------------------------------------------------

    struct ReceivedRequest {
        head: String,
        body: Vec<u8>,
    }

    impl ReceivedRequest {
        fn request_line(&self) -> &str {
            self.head.lines().next().unwrap_or_default()
        }

        fn header(&self, name: &str) -> Option<String> {
            self.head.lines().find_map(|line| {
                let (key, value) = line.split_once(':')?;
                key.eq_ignore_ascii_case(name)
                    .then(|| value.trim().to_owned())
            })
        }
    }

    fn http_response(status_line: &str, extra_headers: &[(&str, &str)], body: &str) -> String {
        let mut response = format!("HTTP/1.1 {status_line}\r\n");
        for (name, value) in extra_headers {
            response.push_str(&format!("{name}: {value}\r\n"));
        }
        response.push_str(&format!(
            "Content-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
            body.len()
        ));
        response
    }

    /// Serve exactly `responses.len()` connections (one scripted response
    /// each), returning every received request for shape assertions. The
    /// listener drops afterwards, so an over-eager client (e.g. an unbounded
    /// pagination walk) fails loudly on connection refused.
    fn spawn_scripted_server(
        responses: Vec<String>,
    ) -> (String, std::thread::JoinHandle<Vec<ReceivedRequest>>) {
        use std::io::Read as _;
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let handle = std::thread::spawn(move || {
            let mut received = Vec::new();
            for response in responses {
                let (mut stream, _) = listener.accept().unwrap();
                stream
                    .set_read_timeout(Some(std::time::Duration::from_secs(10)))
                    .unwrap();
                let mut buffer = Vec::new();
                let mut chunk = [0_u8; 4096];
                let header_end = loop {
                    if let Some(position) = find_subslice(&buffer, b"\r\n\r\n") {
                        break position + 4;
                    }
                    let count = stream.read(&mut chunk).unwrap();
                    assert!(count > 0, "connection closed before request head completed");
                    buffer.extend_from_slice(&chunk[..count]);
                };
                let head = String::from_utf8_lossy(&buffer[..header_end]).into_owned();
                let content_length: usize = head
                    .lines()
                    .find_map(|line| {
                        let (name, value) = line.split_once(':')?;
                        name.eq_ignore_ascii_case("content-length")
                            .then(|| value.trim().parse().ok())
                            .flatten()
                    })
                    .unwrap_or(0);
                let mut body = buffer[header_end..].to_vec();
                while body.len() < content_length {
                    let count = stream.read(&mut chunk).unwrap();
                    assert!(count > 0, "connection closed before request body completed");
                    body.extend_from_slice(&chunk[..count]);
                }
                stream.write_all(response.as_bytes()).unwrap();
                received.push(ReceivedRequest { head, body });
            }
            received
        });
        (format!("http://{address}"), handle)
    }

    #[test]
    fn env_upload_sends_multipart_purpose_and_file_and_returns_id() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var("MISTRAL_API_KEY", "test-key") };
        let (base, server) = spawn_scripted_server(vec![http_response(
            "200 OK",
            &[],
            r#"{"id":"file-verified-1","object":"file","purpose":"batch"}"#,
        )]);
        let client = EnvMistralBatchClient::with_base_url(&base);
        let jsonl = batch_input_line(
            "task-1",
            &serde_json::json!({"document": {"type": "document_url"}}),
        );
        let filename = batch_upload_filename("01HTESTTOKEN");
        let uploaded = client
            .upload_batch_input(jsonl.as_bytes(), &filename)
            .unwrap();
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };
        assert_eq!(uploaded, "file-verified-1");

        let requests = server.join().unwrap();
        assert_eq!(requests.len(), 1);
        let request = &requests[0];
        assert!(
            request
                .request_line()
                .starts_with("POST /v1/files HTTP/1.1")
        );
        assert_eq!(
            request.header("Authorization").as_deref(),
            Some("Bearer test-key")
        );
        assert_eq!(
            request.header("Accept-Encoding").as_deref(),
            Some("identity")
        );
        assert_eq!(
            request
                .header("Content-Length")
                .and_then(|value| value.parse::<usize>().ok()),
            Some(request.body.len()),
        );
        let content_type = request.header("Content-Type").unwrap();
        let boundary = content_type
            .strip_prefix("multipart/form-data; boundary=")
            .expect("multipart content type carries the boundary")
            .to_owned();
        let body = String::from_utf8(request.body.clone()).unwrap();
        assert!(body.contains(&format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n"
        )));
        assert!(body.contains(&format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; \
             filename=\"kio-01HTESTTOKEN.jsonl\"\r\nContent-Type: application/octet-stream\r\n\r\n"
        )));
        assert!(
            body.contains(&jsonl),
            "the JSONL bytes ride the file part verbatim"
        );
        assert!(body.ends_with(&format!("\r\n--{boundary}--\r\n")));
    }

    #[test]
    fn env_upload_rejects_a_header_breaking_filename_before_any_send() {
        // No server, no env: validation fails before credential resolution
        // or any request is attempted.
        let client = EnvMistralBatchClient::with_base_url("http://127.0.0.1:9");
        let error = client
            .upload_batch_input(b"{}", "kio-\"evil\r\n.jsonl")
            .unwrap_err();
        assert!(matches!(error, AdapterError::ContractViolation(_)));
    }

    #[test]
    fn env_create_job_sends_verified_body_and_maps_the_job_record() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var("MISTRAL_API_KEY", "test-key") };
        let (base, server) = spawn_scripted_server(vec![http_response(
            "200 OK",
            &[],
            r#"{"id":"batch-verified-1","object":"batch","status":"QUEUED","output_file":null,"metadata":{"intent_token":"echoed-by-provider"}}"#,
        )]);
        let client = EnvMistralBatchClient::with_base_url(&base);
        let sent_metadata = serde_json::json!({
            "intent_token": "01HINTENT",
            "scope_id": "01HSCOPE",
            "adapter_kind": "markdownize",
            "input_hash": "sha256:aaaa",
            "tool_profile_hash": "sha256:bbbb",
        });
        let record = client
            .create_job("file-verified-1", "mistral-ocr-2505", &sent_metadata)
            .unwrap();
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };

        assert_eq!(record.job_id, "batch-verified-1");
        assert_eq!(record.status, BatchJobStatus::Queued);
        assert_eq!(record.output_file_id, None);
        // The record's metadata is the PROVIDER's returned value (07 §5.7
        // round-trip contract observes what came back, never an input echo).
        assert_eq!(
            record.metadata,
            serde_json::json!({"intent_token": "echoed-by-provider"})
        );

        let requests = server.join().unwrap();
        let request = &requests[0];
        assert!(
            request
                .request_line()
                .starts_with("POST /v1/batch/jobs HTTP/1.1")
        );
        assert!(
            request
                .header("Content-Type")
                .unwrap()
                .starts_with("application/json")
        );
        let sent: serde_json::Value = serde_json::from_slice(&request.body).unwrap();
        assert_eq!(
            sent,
            serde_json::json!({
                "input_files": ["file-verified-1"],
                "endpoint": "/v1/ocr",
                "model": "mistral-ocr-2505",
                "metadata": sent_metadata,
            })
        );
    }

    #[test]
    fn env_delete_upload_treats_http_404_as_success() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var("MISTRAL_API_KEY", "test-key") };
        let (base, server) = spawn_scripted_server(vec![http_response(
            "404 Not Found",
            &[],
            r#"{"detail":"file already deleted"}"#,
        )]);
        let client = EnvMistralBatchClient::with_base_url(&base);
        // 07 §5.7: already-gone reports as success.
        client.delete_upload("file-gone").unwrap();
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };
        let requests = server.join().unwrap();
        assert!(
            requests[0]
                .request_line()
                .starts_with("DELETE /v1/files/file-gone HTTP/1.1")
        );
    }

    #[test]
    fn env_list_jobs_combines_pages_and_stops_at_total() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var("MISTRAL_API_KEY", "test-key") };
        let page0 = serde_json::json!({
            "total": 3,
            "data": [
                {
                    "id": "batch-1",
                    "status": "SUCCESS",
                    "output_file": "file-out-1",
                    "metadata": {"intent_token": "01HAAA"}
                },
                {"id": "batch-2", "status": "RUNNING"},
            ],
        });
        let page1 = serde_json::json!({
            "total": 3,
            "data": [{"id": "batch-3", "status": "FAILED"}],
        });
        let (base, server) = spawn_scripted_server(vec![
            http_response("200 OK", &[], &page0.to_string()),
            http_response("200 OK", &[], &page1.to_string()),
        ]);
        let client = EnvMistralBatchClient::with_base_url(&base);
        let jobs = client.list_jobs().unwrap();
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };

        assert_eq!(jobs.len(), 3);
        assert_eq!(jobs[0].job_id, "batch-1");
        assert_eq!(jobs[0].status, BatchJobStatus::Success);
        assert_eq!(jobs[0].output_file_id.as_deref(), Some("file-out-1"));
        assert_eq!(jobs[0].metadata["intent_token"], "01HAAA");
        assert_eq!(jobs[1].metadata, serde_json::Value::Null);
        assert_eq!(jobs[2].status, BatchJobStatus::Failed);

        let requests = server.join().unwrap();
        assert!(
            requests[0]
                .request_line()
                .starts_with("GET /v1/batch/jobs?page_size=100&page=0 ")
        );
        assert!(
            requests[1]
                .request_line()
                .starts_with("GET /v1/batch/jobs?page_size=100&page=1 ")
        );
    }

    #[test]
    fn env_list_uploads_walks_the_batch_purpose_listing() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var("MISTRAL_API_KEY", "test-key") };
        let page0 = serde_json::json!({
            "total": 2,
            "data": [
                {"id": "file-a", "filename": "kio-01HTOK.jsonl"},
                {"id": "file-b", "filename": null},
            ],
        });
        let (base, server) =
            spawn_scripted_server(vec![http_response("200 OK", &[], &page0.to_string())]);
        let client = EnvMistralBatchClient::with_base_url(&base);
        let uploads = client.list_uploads().unwrap();
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };

        assert_eq!(uploads.len(), 2);
        assert_eq!(uploads[0].upload_id, "file-a");
        assert_eq!(uploads[0].filename, "kio-01HTOK.jsonl");
        assert_eq!(
            filename_intent_token(&uploads[0].filename),
            Some("01HTOK"),
            "the filename token stays recoverable through the listing"
        );
        assert_eq!(uploads[1].filename, "");

        let requests = server.join().unwrap();
        assert!(
            requests[0]
                .request_line()
                .starts_with("GET /v1/files?purpose=batch&page_size=100&page=0 ")
        );
    }

    #[test]
    fn env_list_jobs_pagination_is_bounded_at_50_pages() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var("MISTRAL_API_KEY", "test-key") };
        // Every page is non-empty and no `total` is reported: only the
        // 50-page bound can stop this walk. The server accepts exactly 50
        // connections, so a 51st request would fail loudly (refused).
        let responses = (0..BATCH_LIST_MAX_PAGES)
            .map(|page| {
                http_response(
                    "200 OK",
                    &[],
                    &serde_json::json!({
                        "data": [{"id": format!("batch-{page}"), "status": "QUEUED"}],
                    })
                    .to_string(),
                )
            })
            .collect();
        let (base, server) = spawn_scripted_server(responses);
        let client = EnvMistralBatchClient::with_base_url(&base);
        let jobs = client.list_jobs().unwrap();
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };

        assert_eq!(jobs.len(), BATCH_LIST_MAX_PAGES);
        let requests = server.join().unwrap();
        assert_eq!(requests.len(), BATCH_LIST_MAX_PAGES);
        assert!(
            requests[BATCH_LIST_MAX_PAGES - 1]
                .request_line()
                .starts_with("GET /v1/batch/jobs?page_size=100&page=49 ")
        );
    }

    #[test]
    fn env_fetch_output_parses_the_batch_results_envelope() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var("MISTRAL_API_KEY", "test-key") };
        // The verified out-batch/batch_results.jsonl envelope: one JSON object
        // per line, `{"id", "custom_id", "response": {"status_code", "body"}}`.
        let payload = concat!(
            r#"{"id":"batch-1-0","custom_id":"task-a","response":{"status_code":200,"body":{"pages":[{"index":0,"markdown":"page one"}]}}}"#,
            "\n\n",
            r#"{"id":"batch-1-1","custom_id":"task-b","response":{"status_code":429,"body":{"error":"rate limited"}}}"#,
            "\n",
        );
        let (base, server) = spawn_scripted_server(vec![http_response("200 OK", &[], payload)]);
        let client = EnvMistralBatchClient::with_base_url(&base);
        let lines = client.fetch_output("file-out-1").unwrap();
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };

        assert_eq!(lines.len(), 2, "blank lines are skipped, not errors");
        assert_eq!(lines[0].custom_id, "task-a");
        assert_eq!(lines[0].status_code, 200);
        assert_eq!(lines[0].body["pages"][0]["markdown"], "page one");
        assert_eq!(lines[1].custom_id, "task-b");
        assert_eq!(lines[1].status_code, 429);
        assert_eq!(lines[1].body["error"], "rate limited");

        let requests = server.join().unwrap();
        assert!(
            requests[0]
                .request_line()
                .starts_with("GET /v1/files/file-out-1/content HTTP/1.1")
        );
    }

    #[test]
    fn env_http_429_maps_to_rate_limit_with_the_real_retry_after() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var("MISTRAL_API_KEY", "test-key") };
        let (base, server) = spawn_scripted_server(vec![http_response(
            "429 Too Many Requests",
            &[("Retry-After", "7")],
            r#"{"detail":"slow down"}"#,
        )]);
        let client = EnvMistralBatchClient::with_base_url(&base);
        let error = client.get_job("batch-1").unwrap_err();
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };
        server.join().unwrap();

        match error {
            AdapterError::RateLimit { retry_after_ms, .. } => {
                assert_eq!(retry_after_ms, Some(7_000));
            }
            other => panic!("expected RateLimit with Retry-After, got {other:?}"),
        }
    }

    #[test]
    fn provider_scope_id_prefers_workspace_env_and_falls_back_to_default() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        let client = EnvMistralBatchClient::with_base_url("http://127.0.0.1:9");
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var(MISTRAL_WORKSPACE_ID_ENV, "  ws-team-a  ") };
        assert_eq!(client.provider_scope_id().unwrap(), "ws-team-a");
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var(MISTRAL_WORKSPACE_ID_ENV, "   ") };
        assert_eq!(
            client.provider_scope_id().unwrap(),
            DEFAULT_PROVIDER_SCOPE_ID,
            "a whitespace-only value degrades to the default scope"
        );
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(MISTRAL_WORKSPACE_ID_ENV) };
        assert_eq!(
            client.provider_scope_id().unwrap(),
            DEFAULT_PROVIDER_SCOPE_ID
        );
    }

    #[test]
    fn configured_client_resolution_order_is_mock_then_real_then_none() {
        let _guard = test_env_lock()
            .lock()
            .unwrap_or_else(|err| err.into_inner());
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(MISTRAL_WORKSPACE_ID_ENV) };
        assert!(
            configured_mistral_batch_client().unwrap().is_none(),
            "no mock script and no credential → no batch client"
        );

        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var("MISTRAL_API_KEY", "test-key") };
        let real = configured_mistral_batch_client()
            .unwrap()
            .expect("the sync path's credential condition also configures the batch lane");
        assert_eq!(real.provider_scope_id().unwrap(), DEFAULT_PROVIDER_SCOPE_ID);

        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::set_var(TEST_MISTRAL_BATCH_ENV, r#"{"provider_scope_id":"mock-ws"}"#) };
        let mock = configured_mistral_batch_client()
            .unwrap()
            .expect("the inline mock script stays first-priority");
        assert_eq!(mock.provider_scope_id().unwrap(), "mock-ws");
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var(TEST_MISTRAL_BATCH_ENV) };
        // FIXME: Audit that the environment access only happens in single-threaded code.
        unsafe { std::env::remove_var("MISTRAL_API_KEY") };
    }
}
