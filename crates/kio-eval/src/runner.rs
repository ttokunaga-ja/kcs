//! Process execution, scoring, and deterministic reporting for `kio-eval`.
//!
//! Manifest parsing and CAS attestation deliberately live in sibling modules.
//! This module only accepts already-resolved expected identities and typed
//! history references, so the CLI can keep all untrusted-input validation at
//! its boundary.

use std::{
    collections::{BTreeMap, BTreeSet, HashMap, HashSet},
    ffi::{OsStr, OsString},
    fs,
    io::Read,
    path::Path,
    process::{Child, Command, ExitStatus, Stdio},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

use crate::{
    RecallResult, ResultKey,
    manifest::{HistoryOperation, frozen_history_plan},
    recall_at_k,
};
use kio_search::EvidencePointer;

pub const RECALL_K: usize = 10;
pub const HISTORY_QUERY_COUNT: usize = 16;
pub const DEFAULT_RECALL_TARGET: f64 = 0.8;
pub const DEFAULT_PROCESS_TIMEOUT: Duration = Duration::from_secs(30);
pub const DEFAULT_PROCESS_OUTPUT_LIMIT: usize = 1024 * 1024;

#[must_use]
pub fn latency_target_ms(scenario: &str) -> Option<f64> {
    match scenario {
        "M3-1" => Some(5_000.0),
        "M3-2" | "M3-3" => Some(7_000.0),
        _ => None,
    }
}

/// Floating-point counterpart to the shared integer golden-vector primitive.
/// Durations originate from a monotonic clock; reject non-finite test/caller
/// values rather than allowing `total_cmp` to make an invalid metric pass.
fn percentile_duration_ms(values: &[f64], percentile: f64) -> Option<f64> {
    if values.is_empty() || !(0.0 < percentile && percentile <= 1.0) {
        return None;
    }
    let mut ordered = values.to_vec();
    if ordered
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
    {
        return None;
    }
    ordered.sort_by(|left, right| left.total_cmp(right));
    let rank = (percentile * ordered.len() as f64).ceil().max(1.0) as usize;
    ordered.get(rank.saturating_sub(1)).copied()
}

#[derive(Debug, Error)]
pub enum RunnerError {
    #[error(transparent)]
    Process(#[from] BoundedProcessError),
    #[error("invalid evaluator input: {0}")]
    Input(String),
    #[error("could not write evaluation artifact: {0}")]
    Write(#[source] std::io::Error),
    #[error("could not serialize evaluation artifact: {0}")]
    Serialize(#[from] serde_json::Error),
}

/// Limits applied to evaluator subprocesses.  Both output limits are measured
/// in bytes before UTF-8 decoding, so a malicious process cannot make decoding
/// itself an unbounded allocation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BoundedProcessOptions {
    pub timeout: Duration,
    pub max_stdout_bytes: usize,
    pub max_stderr_bytes: usize,
}

impl Default for BoundedProcessOptions {
    fn default() -> Self {
        Self {
            timeout: DEFAULT_PROCESS_TIMEOUT,
            max_stdout_bytes: DEFAULT_PROCESS_OUTPUT_LIMIT,
            max_stderr_bytes: DEFAULT_PROCESS_OUTPUT_LIMIT,
        }
    }
}

/// A fully collected subprocess result. Output is strictly decoded as UTF-8.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BoundedProcessOutput {
    pub status: ExitStatus,
    pub stdout: String,
    pub stderr: String,
    pub duration: Duration,
}

#[derive(Debug, Error)]
pub enum BoundedProcessError {
    #[error("could not start evaluator subprocess: {0}")]
    Spawn(#[source] std::io::Error),
    #[error("could not configure evaluator subprocess isolation: {0}")]
    Isolation(#[source] std::io::Error),
    #[error("could not read evaluator subprocess {stream}: {source}")]
    Read {
        stream: &'static str,
        #[source]
        source: std::io::Error,
    },
    #[error("could not wait for evaluator subprocess: {0}")]
    Wait(#[source] std::io::Error),
    #[error("evaluator subprocess exceeded timeout of {timeout_ms} ms")]
    Timeout { timeout_ms: u128 },
    #[error("evaluator subprocess {stream} exceeded output limit of {limit} bytes")]
    OutputLimit { stream: &'static str, limit: usize },
    #[error("evaluator subprocess emitted non-UTF-8 {stream}")]
    NonUtf8 { stream: &'static str },
}

enum StreamEvent {
    Data(&'static str, Vec<u8>),
    End,
    ReadError(&'static str, std::io::Error),
    OutputLimit(&'static str, usize),
}

#[cfg(unix)]
fn read_stream<R: Read + std::os::fd::AsRawFd + Send + 'static>(
    mut reader: R,
    stream: &'static str,
    limit: usize,
    sender: mpsc::Sender<StreamEvent>,
    cancelled: Arc<AtomicBool>,
) {
    let mut bytes = Vec::new();
    let mut chunk = [0_u8; 8192];
    loop {
        if cancelled.load(Ordering::Acquire) {
            return;
        }
        let mut descriptor = libc::pollfd {
            fd: reader.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        // Poll rather than blocking in `read` so cancellation can also release
        // readers whose pipe write end escaped the evaluator process group.
        let polled = unsafe { libc::poll(&mut descriptor, 1, 10) };
        if polled == 0 {
            continue;
        }
        if polled < 0 {
            let error = std::io::Error::last_os_error();
            if error.kind() == std::io::ErrorKind::Interrupted {
                continue;
            }
            let _ = sender.send(StreamEvent::ReadError(stream, error));
            return;
        }
        match reader.read(&mut chunk) {
            Ok(0) => {
                let _ = sender.send(StreamEvent::Data(stream, bytes));
                let _ = sender.send(StreamEvent::End);
                return;
            }
            Ok(count) => {
                let Some(total) = bytes.len().checked_add(count) else {
                    let _ = sender.send(StreamEvent::OutputLimit(stream, limit));
                    return;
                };
                if total > limit {
                    let _ = sender.send(StreamEvent::OutputLimit(stream, limit));
                    return;
                }
                bytes.extend_from_slice(&chunk[..count]);
            }
            Err(error) => {
                let _ = sender.send(StreamEvent::ReadError(stream, error));
                return;
            }
        }
    }
}

// Windows kills the complete Job Object on cancellation, closing inherited
// output handles. Keep the platform's existing blocking reader: it avoids
// changing its pipe semantics while the Job Object provides the cancellation
// boundary that Unix process groups cannot enforce after `setsid`.
#[cfg(not(unix))]
fn read_stream<R: Read + Send + 'static>(
    mut reader: R,
    stream: &'static str,
    limit: usize,
    sender: mpsc::Sender<StreamEvent>,
    _cancelled: Arc<AtomicBool>,
) {
    let mut bytes = Vec::new();
    let mut chunk = [0_u8; 8192];
    loop {
        match reader.read(&mut chunk) {
            Ok(0) => {
                let _ = sender.send(StreamEvent::Data(stream, bytes));
                let _ = sender.send(StreamEvent::End);
                return;
            }
            Ok(count) => {
                let Some(total) = bytes.len().checked_add(count) else {
                    let _ = sender.send(StreamEvent::OutputLimit(stream, limit));
                    return;
                };
                if total > limit {
                    let _ = sender.send(StreamEvent::OutputLimit(stream, limit));
                    return;
                }
                bytes.extend_from_slice(&chunk[..count]);
            }
            Err(error) => {
                let _ = sender.send(StreamEvent::ReadError(stream, error));
                return;
            }
        }
    }
}

fn terminate_process_tree(child: &mut Child) {
    #[cfg(unix)]
    unsafe {
        // `configure_process_group` makes the child the process-group leader;
        // a negative PID targets every descendant in that group.
        libc::kill(-(child.id() as i32), libc::SIGKILL);
    }
    #[cfg(not(unix))]
    {
        let _ = child.kill();
    }
}

#[cfg(unix)]
fn configure_process_group(command: &mut Command) {
    use std::os::unix::process::CommandExt;

    unsafe {
        command.pre_exec(|| {
            if libc::setpgid(0, 0) == 0 {
                Ok(())
            } else {
                Err(std::io::Error::last_os_error())
            }
        });
    }
}

#[cfg(not(unix))]
fn configure_process_group(_command: &mut Command) {}

#[cfg(windows)]
struct WindowsJob(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
impl WindowsJob {
    fn attach(child: &Child) -> Result<Self, std::io::Error> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::{
            Foundation::CloseHandle,
            System::JobObjects::{
                AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
                SetInformationJobObject,
            },
        };

        unsafe {
            let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if handle.is_null() {
                return Err(std::io::Error::last_os_error());
            }
            let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                (&raw const limits).cast(),
                std::mem::size_of_val(&limits) as u32,
            ) == 0
                || AssignProcessToJobObject(handle, child.as_raw_handle() as _) == 0
            {
                let error = std::io::Error::last_os_error();
                CloseHandle(handle);
                return Err(error);
            }
            Ok(Self(handle))
        }
    }

    fn terminate(&self) {
        unsafe {
            windows_sys::Win32::System::JobObjects::TerminateJobObject(self.0, 1);
        }
    }
}

#[cfg(windows)]
impl Drop for WindowsJob {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

#[cfg(windows)]
fn attach_process_tree(child: &Child) -> Result<Option<WindowsJob>, std::io::Error> {
    WindowsJob::attach(child).map(Some)
}

#[cfg(not(windows))]
fn attach_process_tree(_child: &Child) -> Result<Option<()>, std::io::Error> {
    Ok(None)
}

#[cfg(windows)]
fn terminate_attached_tree(job: &Option<WindowsJob>) {
    if let Some(job) = job {
        job.terminate();
    }
}

#[cfg(not(windows))]
fn terminate_attached_tree(_job: &Option<()>) {}

/// Run a trusted Kio-under-test command under evaluator resource bounds.
///
/// On Unix the child gets its own process group; on Windows it is assigned to
/// a kill-on-close Job Object. A timeout, output overflow, or stream failure
/// kills the ordinary child tree before returning. This is a guard against
/// product bugs, not an operating-system sandbox for a hostile executable.
pub fn run_bounded_command(
    command: &mut Command,
    options: BoundedProcessOptions,
) -> Result<BoundedProcessOutput, BoundedProcessError> {
    configure_process_group(command);
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    let started = Instant::now();
    let mut child = command.spawn().map_err(BoundedProcessError::Spawn)?;
    let process_tree = match attach_process_tree(&child) {
        Ok(process_tree) => process_tree,
        Err(error) => {
            terminate_process_tree(&mut child);
            let _ = child.wait();
            return Err(BoundedProcessError::Isolation(error));
        }
    };
    let stdout = child.stdout.take().expect("stdout was configured as piped");
    let stderr = child.stderr.take().expect("stderr was configured as piped");
    let (sender, receiver) = mpsc::channel();
    let cancelled = Arc::new(AtomicBool::new(false));
    let stdout_reader = thread::spawn({
        let sender = sender.clone();
        let cancelled = Arc::clone(&cancelled);
        move || {
            read_stream(
                stdout,
                "stdout",
                options.max_stdout_bytes,
                sender,
                cancelled,
            )
        }
    });
    let stderr_reader = thread::spawn({
        let cancelled = Arc::clone(&cancelled);
        move || {
            read_stream(
                stderr,
                "stderr",
                options.max_stderr_bytes,
                sender,
                cancelled,
            )
        }
    });

    let deadline = started + options.timeout;
    let mut status = None;
    let mut stdout = None;
    let mut stderr = None;
    let mut finished_streams = 0;
    let result = loop {
        if status.is_none() {
            status = child.try_wait().map_err(BoundedProcessError::Wait)?;
        }
        if status.is_some() && finished_streams == 2 {
            break Ok(());
        }
        let now = Instant::now();
        if now >= deadline {
            break Err(BoundedProcessError::Timeout {
                timeout_ms: options.timeout.as_millis(),
            });
        }
        match receiver.recv_timeout((deadline - now).min(Duration::from_millis(10))) {
            Ok(StreamEvent::Data("stdout", bytes)) => stdout = Some(bytes),
            Ok(StreamEvent::Data("stderr", bytes)) => stderr = Some(bytes),
            Ok(StreamEvent::Data(_, _)) => unreachable!("only stdout and stderr are configured"),
            Ok(StreamEvent::End) => finished_streams += 1,
            Ok(StreamEvent::ReadError(stream, source)) => {
                break Err(BoundedProcessError::Read { stream, source });
            }
            Ok(StreamEvent::OutputLimit(stream, limit)) => {
                break Err(BoundedProcessError::OutputLimit { stream, limit });
            }
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            Err(mpsc::RecvTimeoutError::Disconnected) if finished_streams == 2 => break Ok(()),
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                break Err(BoundedProcessError::Read {
                    stream: "output",
                    source: std::io::Error::new(
                        std::io::ErrorKind::BrokenPipe,
                        "output reader disconnected",
                    ),
                });
            }
        }
    };
    if result.is_err() {
        // Readers wake within their short poll interval even when a descendant
        // has escaped the Unix process group and retains a pipe write end.
        cancelled.store(true, Ordering::Release);
        terminate_attached_tree(&process_tree);
        terminate_process_tree(&mut child);
    }
    let waited = child.wait().map_err(BoundedProcessError::Wait);
    let _ = stdout_reader.join();
    let _ = stderr_reader.join();
    result?;
    let status = waited?;
    let stdout = String::from_utf8(stdout.expect("stdout reader completed"))
        .map_err(|_| BoundedProcessError::NonUtf8 { stream: "stdout" })?;
    let stderr = String::from_utf8(stderr.expect("stderr reader completed"))
        .map_err(|_| BoundedProcessError::NonUtf8 { stream: "stderr" })?;
    Ok(BoundedProcessOutput {
        status,
        stdout,
        stderr,
        duration: started.elapsed(),
    })
}

/// An unmodified, UTF-8 decoded subprocess outcome.
#[derive(Debug, Clone, PartialEq)]
pub struct SearchOutcome {
    pub returncode: i32,
    pub stdout: String,
    pub stderr: String,
    pub duration_ms: f64,
}

pub fn run_search(
    binary: impl AsRef<OsStr>,
    cwd: &Path,
    query: &str,
    flags: &[String],
) -> Result<SearchOutcome, RunnerError> {
    run_search_with_env(binary, cwd, query, flags, None)
}

pub fn run_search_with_env(
    binary: impl AsRef<OsStr>,
    cwd: &Path,
    query: &str,
    flags: &[String],
    environment: Option<&[(OsString, OsString)]>,
) -> Result<SearchOutcome, RunnerError> {
    let mut command = Command::new(binary);
    command
        .arg("--json")
        .arg("search")
        .arg(query)
        .arg("--all-scopes")
        .args(flags)
        .current_dir(cwd);
    if let Some(environment) = environment {
        command.env_clear().envs(environment.iter().cloned());
    }
    let output = run_bounded_command(&mut command, BoundedProcessOptions::default())?;
    Ok(SearchOutcome {
        returncode: output.status.code().unwrap_or(-1),
        stdout: output.stdout,
        stderr: output.stderr,
        duration_ms: output.duration.as_secs_f64() * 1_000.0,
    })
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvidencePointerRecord {
    pub raw_hash: String,
    pub section_id: Option<String>,
    pub heading_path: Option<Vec<String>>,
    pub path_at_commit: Option<String>,
    pub scope_id: String,
    pub commit: String,
    pub tree: Option<String>,
    pub tool_profile_hash: String,
    pub chunk_hash: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SearchHit {
    pub pointer: EvidencePointerRecord,
    /// Exact returned pointer JSON used by CAS attestation and restore.
    pub pointer_value: Value,
    pub current_paths: Option<Vec<String>>,
    pub current_path: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SearchResponse {
    pub results: Vec<SearchHit>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ClassifiedOutcome {
    Scored {
        response: SearchResponse,
        error_code: Option<String>,
        detail: Option<String>,
    },
    Unimplemented {
        error_code: String,
    },
    Failed {
        error_code: Option<String>,
        detail: String,
    },
}

fn parse_json(text: &str) -> Option<Value> {
    let text = text.trim();
    (!text.is_empty())
        .then(|| serde_json::from_str(text).ok())
        .flatten()
}

fn error_code(value: &Option<Value>) -> Option<String> {
    value
        .as_ref()?
        .as_object()?
        .get("error_code")?
        .as_str()
        .map(ToOwned::to_owned)
}

fn is_not_implemented(error_code: &str) -> bool {
    error_code.starts_with("KIO-E-") && error_code.contains("NOT-IMPLEMENTED")
}

fn nonempty_string(value: &Value, field: &str) -> Result<String, String> {
    value
        .as_str()
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .ok_or_else(|| format!("invalid Evidence field: {field}"))
}

fn optional_string(value: Option<&Value>, field: &str) -> Result<Option<String>, String> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(value) => nonempty_string(value, field).map(Some),
    }
}

fn parse_pointer(value: &Value) -> Result<EvidencePointerRecord, String> {
    let pointer: EvidencePointer = serde_json::from_value(value.clone())
        .map_err(|error| format!("invalid evidence_pointer: {error}"))?;
    pointer
        .validate()
        .map_err(|error| format!("invalid evidence_pointer: {error}"))?;
    let object = value
        .as_object()
        .ok_or_else(|| "evidence_pointer is not an object".to_owned())?;
    let schema_version = object
        .get("schema_version")
        .and_then(Value::as_u64)
        .ok_or_else(|| "missing or invalid Evidence schema_version".to_owned())?;
    if schema_version != 1 {
        return Err("invalid Evidence schema_version".to_owned());
    }
    let heading_path = match object.get("heading_path") {
        None | Some(Value::Null) => None,
        Some(Value::Array(values)) => Some(
            values
                .iter()
                .map(|value| nonempty_string(value, "heading_path"))
                .collect::<Result<Vec<_>, _>>()?,
        ),
        Some(_) => return Err("invalid Evidence field: heading_path".to_owned()),
    };
    Ok(EvidencePointerRecord {
        commit: nonempty_string(
            object
                .get("commit")
                .ok_or_else(|| "missing Evidence field: commit".to_owned())?,
            "commit",
        )?,
        tree: optional_string(object.get("tree"), "tree")?,
        raw_hash: nonempty_string(
            object
                .get("raw_hash")
                .ok_or_else(|| "missing Evidence field: raw_hash".to_owned())?,
            "raw_hash",
        )?,
        tool_profile_hash: nonempty_string(
            object
                .get("tool_profile_hash")
                .ok_or_else(|| "missing Evidence field: tool_profile_hash".to_owned())?,
            "tool_profile_hash",
        )?,
        chunk_hash: nonempty_string(
            object
                .get("chunk_hash")
                .ok_or_else(|| "missing Evidence field: chunk_hash".to_owned())?,
            "chunk_hash",
        )?,
        path_at_commit: optional_string(object.get("path_at_commit"), "path_at_commit")?,
        section_id: optional_string(object.get("section_id"), "section_id")?,
        heading_path,
        scope_id: nonempty_string(
            object
                .get("scope_id")
                .ok_or_else(|| "missing Evidence field: scope_id".to_owned())?,
            "scope_id",
        )?,
    })
}

fn parse_response(value: Value) -> Result<SearchResponse, String> {
    let object = value
        .as_object()
        .ok_or_else(|| "stdout JSON response is not an object".to_owned())?;
    let results = object
        .get("results")
        .and_then(Value::as_array)
        .ok_or_else(|| "stdout JSON response has no results array".to_owned())?;
    results
        .iter()
        .enumerate()
        .map(|(index, result)| {
            let object = result
                .as_object()
                .ok_or_else(|| format!("result[{index}] is not an object"))?;
            let pointer = parse_pointer(
                object
                    .get("evidence_pointer")
                    .ok_or_else(|| format!("result[{index}] has no evidence_pointer"))?,
            )
            .map_err(|error| format!("result[{index}] {error}"))?;
            let current_paths = match object.get("current_paths") {
                None | Some(Value::Null) => None,
                Some(Value::Array(paths)) => Some(
                    paths
                        .iter()
                        .map(|path| nonempty_string(path, "current_paths"))
                        .collect::<Result<Vec<_>, _>>()?,
                ),
                Some(_) => return Err(format!("result[{index}] invalid current_paths")),
            };
            Ok(SearchHit {
                pointer,
                pointer_value: object
                    .get("evidence_pointer")
                    .expect("pointer was checked above")
                    .clone(),
                current_paths,
                current_path: optional_string(object.get("current_path"), "current_path")?,
            })
        })
        .collect::<Result<Vec<_>, _>>()
        .map(|results| SearchResponse { results })
}

/// Apply the specified `0/3` result policy without conflating malformed output
/// with an honest `NOT-IMPLEMENTED` product response.
#[must_use]
pub fn classify_outcome(outcome: &SearchOutcome) -> ClassifiedOutcome {
    let stdout = parse_json(&outcome.stdout);
    let stderr = parse_json(&outcome.stderr);
    let code = error_code(&stdout).or_else(|| error_code(&stderr));
    if let Some(code) = code.as_deref().filter(|code| is_not_implemented(code)) {
        return ClassifiedOutcome::Unimplemented {
            error_code: code.to_owned(),
        };
    }
    if matches!(outcome.returncode, 0 | 3) {
        return match stdout.and_then(|value| parse_response(value).ok()) {
            Some(response) => ClassifiedOutcome::Scored {
                response,
                error_code: code,
                detail: (outcome.returncode == 3).then(|| "partial(exit 3)".to_owned()),
            },
            None => ClassifiedOutcome::Failed {
                error_code: code,
                detail: match outcome.returncode {
                    0 => "exit 0 だが stdout が JSON レスポンスでない".to_owned(),
                    3 => "exit 3 だが stdout が JSON レスポンスでない".to_owned(),
                    _ => unreachable!("only exit 0 and 3 are handled here"),
                },
            },
        };
    }
    let detail = stderr
        .as_ref()
        .and_then(Value::as_object)
        .and_then(|object| object.get("message"))
        .and_then(Value::as_str)
        .filter(|message| !message.is_empty())
        .unwrap_or_else(|| {
            if outcome.stderr.trim().is_empty() {
                outcome.stdout.trim()
            } else {
                outcome.stderr.trim()
            }
        });
    ClassifiedOutcome::Failed {
        error_code: code,
        detail: format!("exit={}: {detail}", outcome.returncode),
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct QueryResult {
    pub scenario: String,
    pub query: String,
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recall_at_10: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
    pub duration_ms: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pointer_attested: Option<usize>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScenarioSummary {
    pub n_queries: usize,
    pub n_scored: usize,
    pub recall_at_10: Option<f64>,
    pub passes_target: bool,
    pub p95_ms: Option<f64>,
    pub latency_target_ms: f64,
    pub passes_latency: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct RenameFailure {
    pub scope: String,
    pub raw_hash: String,
    pub paths: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct HistoryCoverage {
    pub edited_old_required: usize,
    pub edited_old_missing: Vec<String>,
    pub rename_required: usize,
    pub rename_failures: Vec<RenameFailure>,
    pub deleted_required: usize,
    pub deleted_missing: Vec<String>,
    pub passes_m3_2: bool,
    pub passes_m3_3: bool,
    pub restore_problems: Vec<String>,
    pub passes_restore: bool,
    pub pointer_attested: usize,
    pub pointer_attestation_failures: usize,
    pub passes_pointer_attestation: bool,
}

impl Default for HistoryCoverage {
    fn default() -> Self {
        Self {
            edited_old_required: 0,
            edited_old_missing: Vec::new(),
            rename_required: 0,
            rename_failures: Vec::new(),
            deleted_required: 0,
            deleted_missing: Vec::new(),
            passes_m3_2: true,
            passes_m3_3: true,
            restore_problems: Vec::new(),
            passes_restore: true,
            pointer_attested: 0,
            pointer_attestation_failures: 0,
            passes_pointer_attestation: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct Counts {
    pub n_queries: usize,
    pub n_unimplemented: usize,
    pub n_failed: usize,
    pub n_scored: usize,
    pub n_pointer_attested: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EvaluationResults {
    pub target_recall_at_10: f64,
    pub scenarios: BTreeMap<String, ScenarioSummary>,
    pub queries: Vec<QueryResult>,
    pub history_coverage: HistoryCoverage,
    pub counts: Counts,
}

#[derive(Debug, Clone)]
pub struct ResolvedQuery {
    pub scenario: String,
    pub query: String,
    pub expected: HashSet<ResultKey>,
    /// Fixture-resolution failures remain per-query evaluator results. Search
    /// is still run first so a NOT-IMPLEMENTED response keeps its higher-priority
    /// exit-2 classification.
    pub resolution_error: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ScoredRecord {
    pub scenario: String,
    pub expected: HashSet<ResultKey>,
    pub response: SearchResponse,
}

fn full_hash(hex: &str) -> String {
    format!("sha256:{hex}")
}

fn result_key(pointer: &EvidencePointerRecord) -> ResultKey {
    RecallResult {
        raw_hash: pointer.raw_hash.clone(),
        section_id: pointer.section_id.clone(),
        heading_path: pointer.heading_path.clone(),
        path_at_commit: pointer.path_at_commit.clone(),
    }
    .key()
}

impl SearchHit {
    #[must_use]
    pub fn result_key(&self) -> ResultKey {
        result_key(&self.pointer)
    }
}

fn recalled_hits<'a>(records: &'a [ScoredRecord], scenario: &str) -> Vec<&'a SearchHit> {
    records
        .iter()
        .filter(|record| record.scenario == scenario)
        .flat_map(|record| {
            record
                .response
                .results
                .iter()
                .take(RECALL_K)
                .filter(move |hit| record.expected.contains(&result_key(&hit.pointer)))
        })
        .collect()
}

/// History-specific structural gates. Restore validation is performed by the
/// caller, then recorded with [`HistoryCoverage::set_restore_problems`].
#[must_use]
pub fn assess_history_coverage(records: &[ScoredRecord]) -> HistoryCoverage {
    let plan = frozen_history_plan().expect("bundled history plan is validated at build time");
    let m32_hits = recalled_hits(records, "M3-2");
    let m33_hits = recalled_hits(records, "M3-3");
    let m32_raws: HashSet<_> = m32_hits
        .iter()
        .map(|hit| hit.pointer.raw_hash.as_str())
        .collect();
    let mut edited_old_missing = plan
        .operations
        .iter()
        .filter_map(|operation| match operation {
            HistoryOperation::Edit {
                before_raw_sha256, ..
            } => Some(full_hash(before_raw_sha256)),
            _ => None,
        })
        .filter(|hash| !m32_raws.contains(hash.as_str()))
        .collect::<Vec<_>>();
    edited_old_missing.sort();

    let mut rename_failures = Vec::new();
    for rename in plan
        .operations
        .iter()
        .filter_map(|operation| match operation {
            HistoryOperation::Rename {
                scope,
                old_file,
                new_file,
                before_raw_sha256,
                ..
            } => Some((scope, old_file, new_file, before_raw_sha256)),
            _ => None,
        })
    {
        let (scope, old_file, new_file, before_raw_sha256) = rename;
        let raw_hash = full_hash(before_raw_sha256);
        let mut paths = BTreeSet::new();
        let mut aliases_valid = true;
        let mut saw_old = false;
        for record in records.iter().filter(|record| record.scenario == "M3-2") {
            let twin_identities = record
                .expected
                .iter()
                .filter(|(raw, _, path)| {
                    raw == &raw_hash && path.as_deref() == Some(old_file.as_str())
                })
                .map(|(raw, section, _)| (raw.clone(), section.clone(), Some(new_file.clone())))
                .collect::<HashSet<_>>();
            if twin_identities.is_empty() {
                continue;
            }
            for hit in record.response.results.iter().take(RECALL_K) {
                if hit.pointer.raw_hash != raw_hash {
                    continue;
                }
                let identity = result_key(&hit.pointer);
                if record.expected.contains(&identity) || twin_identities.contains(&identity) {
                    if hit.pointer.path_at_commit.as_deref() == Some(old_file.as_str()) {
                        saw_old = true;
                    }
                    if let Some(path) = &hit.pointer.path_at_commit {
                        paths.insert(path.clone());
                    }
                    aliases_valid &= hit.current_paths.as_deref()
                        == Some(std::slice::from_ref(new_file))
                        && hit.current_path.as_deref() == Some(new_file.as_str());
                }
            }
        }
        if !saw_old || !paths.contains(old_file) || !paths.contains(new_file) || !aliases_valid {
            rename_failures.push(RenameFailure {
                scope: scope.clone(),
                raw_hash,
                paths: paths.into_iter().collect(),
            });
        }
    }
    let m33_raws: HashSet<_> = m33_hits
        .iter()
        .map(|hit| hit.pointer.raw_hash.as_str())
        .collect();
    let mut deleted_missing = plan
        .operations
        .iter()
        .filter_map(|operation| match operation {
            HistoryOperation::Delete {
                before_raw_sha256, ..
            } => Some(full_hash(before_raw_sha256)),
            _ => None,
        })
        .filter(|hash| !m33_raws.contains(hash.as_str()))
        .collect::<Vec<_>>();
    deleted_missing.sort();
    HistoryCoverage {
        edited_old_required: plan
            .operations
            .iter()
            .filter(|operation| matches!(operation, HistoryOperation::Edit { .. }))
            .count(),
        passes_m3_2: edited_old_missing.is_empty() && rename_failures.is_empty(),
        edited_old_missing,
        rename_required: plan
            .operations
            .iter()
            .filter(|operation| matches!(operation, HistoryOperation::Rename { .. }))
            .count(),
        rename_failures,
        deleted_required: plan
            .operations
            .iter()
            .filter(|operation| matches!(operation, HistoryOperation::Delete { .. }))
            .count(),
        passes_m3_3: deleted_missing.is_empty(),
        deleted_missing,
        ..HistoryCoverage::default()
    }
}

impl HistoryCoverage {
    pub fn set_restore_problems(&mut self, problems: Vec<String>) {
        self.passes_restore = problems.is_empty();
        self.restore_problems = problems;
    }
}

/// Score already-resolved queries and return records needed for history gates.
///
/// The validator runs after strict response decoding but before a response can
/// contribute recall. It is the integration point for M3-2 CAS attestation.
pub fn evaluate_queries_with_validator<F, V>(
    queries: &[ResolvedQuery],
    recall_target: f64,
    mut search: F,
    mut validate: V,
) -> Result<(EvaluationResults, Vec<ScoredRecord>), RunnerError>
where
    F: FnMut(&ResolvedQuery) -> Result<SearchOutcome, RunnerError>,
    V: FnMut(&ResolvedQuery, &SearchResponse) -> Result<Option<usize>, String>,
{
    if !(0.0..=1.0).contains(&recall_target) {
        return Err(RunnerError::Input(
            "recall target must be in [0, 1]".to_owned(),
        ));
    }
    let mut scores: HashMap<&str, Vec<f64>> = HashMap::new();
    let mut latencies: HashMap<&str, Vec<f64>> = HashMap::new();
    let mut results = EvaluationResults {
        target_recall_at_10: recall_target,
        scenarios: BTreeMap::new(),
        queries: Vec::new(),
        history_coverage: HistoryCoverage::default(),
        counts: Counts {
            n_queries: queries.len(),
            ..Counts::default()
        },
    };
    let mut records = Vec::new();
    for query in queries {
        let outcome = search(query)?;
        let duration_ms = outcome.duration_ms;
        match classify_outcome(&outcome) {
            ClassifiedOutcome::Unimplemented { error_code } => {
                results.counts.n_unimplemented += 1;
                results.queries.push(QueryResult {
                    scenario: query.scenario.clone(),
                    query: query.query.clone(),
                    status: "unimplemented".to_owned(),
                    recall_at_10: None,
                    error_code: Some(error_code),
                    detail: Some("search 未実装 (NOT-IMPLEMENTED)".to_owned()),
                    duration_ms,
                    pointer_attested: None,
                });
            }
            classified if query.resolution_error.is_some() => {
                let error_code = match classified {
                    ClassifiedOutcome::Failed { error_code, .. } => error_code,
                    ClassifiedOutcome::Scored { error_code, .. } => error_code,
                    ClassifiedOutcome::Unimplemented { .. } => unreachable!("handled above"),
                };
                results.counts.n_failed += 1;
                results.counts.n_scored += 1;
                scores.entry(&query.scenario).or_default().push(0.0);
                latencies
                    .entry(&query.scenario)
                    .or_default()
                    .push(duration_ms);
                results.queries.push(QueryResult {
                    scenario: query.scenario.clone(),
                    query: query.query.clone(),
                    status: "failed".to_owned(),
                    recall_at_10: Some(0.0),
                    error_code,
                    detail: query.resolution_error.clone(),
                    duration_ms,
                    pointer_attested: None,
                });
            }
            ClassifiedOutcome::Failed { error_code, detail } => {
                results.counts.n_failed += 1;
                results.counts.n_scored += 1;
                scores.entry(&query.scenario).or_default().push(0.0);
                latencies
                    .entry(&query.scenario)
                    .or_default()
                    .push(duration_ms);
                results.queries.push(QueryResult {
                    scenario: query.scenario.clone(),
                    query: query.query.clone(),
                    status: "failed".to_owned(),
                    recall_at_10: Some(0.0),
                    error_code,
                    detail: Some(detail),
                    duration_ms,
                    pointer_attested: None,
                });
            }
            ClassifiedOutcome::Scored {
                response, detail, ..
            } => {
                let pointer_attested = match validate(query, &response) {
                    Ok(pointer_attested) => pointer_attested,
                    Err(validation_error) => {
                        results.counts.n_failed += 1;
                        results.counts.n_scored += 1;
                        scores.entry(&query.scenario).or_default().push(0.0);
                        latencies
                            .entry(&query.scenario)
                            .or_default()
                            .push(duration_ms);
                        results.queries.push(QueryResult {
                            scenario: query.scenario.clone(),
                            query: query.query.clone(),
                            status: "failed".to_owned(),
                            recall_at_10: Some(0.0),
                            error_code: None,
                            detail: Some(validation_error),
                            duration_ms,
                            pointer_attested: None,
                        });
                        continue;
                    }
                };
                let recall = recall_at_k(
                    &response
                        .results
                        .iter()
                        .map(|hit| RecallResult {
                            raw_hash: hit.pointer.raw_hash.clone(),
                            section_id: hit.pointer.section_id.clone(),
                            heading_path: hit.pointer.heading_path.clone(),
                            path_at_commit: hit.pointer.path_at_commit.clone(),
                        })
                        .collect::<Vec<_>>(),
                    &query.expected,
                    RECALL_K,
                );
                scores.entry(&query.scenario).or_default().push(recall);
                latencies
                    .entry(&query.scenario)
                    .or_default()
                    .push(duration_ms);
                results.counts.n_scored += 1;
                results.counts.n_pointer_attested += pointer_attested.unwrap_or(0);
                results.queries.push(QueryResult {
                    scenario: query.scenario.clone(),
                    query: query.query.clone(),
                    status: "scored".to_owned(),
                    recall_at_10: Some(recall),
                    error_code: None,
                    detail,
                    duration_ms,
                    pointer_attested,
                });
                records.push(ScoredRecord {
                    scenario: query.scenario.clone(),
                    expected: query.expected.clone(),
                    response,
                });
            }
        }
    }
    let scenario_names = queries
        .iter()
        .map(|query| query.scenario.as_str())
        .collect::<BTreeSet<_>>();
    for scenario in scenario_names {
        let latency_target_ms = latency_target_ms(scenario)
            .ok_or_else(|| RunnerError::Input(format!("unknown scenario: {scenario}")))?;
        let scenario_scores = scores.get(scenario).cloned().unwrap_or_default();
        let scenario_latencies = latencies.get(scenario).cloned().unwrap_or_default();
        let average = (!scenario_scores.is_empty())
            .then(|| scenario_scores.iter().sum::<f64>() / scenario_scores.len() as f64);
        let p95_ms = percentile_duration_ms(&scenario_latencies, 0.95);
        results.scenarios.insert(
            scenario.to_owned(),
            ScenarioSummary {
                n_queries: queries
                    .iter()
                    .filter(|query| query.scenario == scenario)
                    .count(),
                n_scored: scenario_scores.len(),
                recall_at_10: average,
                passes_target: average.is_some_and(|value| value >= recall_target),
                p95_ms,
                latency_target_ms,
                passes_latency: p95_ms.is_some_and(|value| value < latency_target_ms),
            },
        );
    }
    Ok((results, records))
}

pub fn evaluate_queries<F>(
    queries: &[ResolvedQuery],
    recall_target: f64,
    search: F,
) -> Result<(EvaluationResults, Vec<ScoredRecord>), RunnerError>
where
    F: FnMut(&ResolvedQuery) -> Result<SearchOutcome, RunnerError>,
{
    evaluate_queries_with_validator(queries, recall_target, search, |_, _| Ok(None))
}

/// Final policy: 2 wins for any unfinished search, otherwise 1 for every
/// failed metric/coverage gate, otherwise 0.
#[must_use]
pub fn final_exit_code(results: &EvaluationResults, active: &[String]) -> i32 {
    if results.counts.n_unimplemented > 0 {
        return 2;
    }
    if results.counts.n_failed > 0 {
        return 1;
    }
    for scenario in active {
        let Some(summary) = results.scenarios.get(scenario) else {
            return 1;
        };
        if !summary.passes_target
            || !summary.passes_latency
            || summary.n_scored != summary.n_queries
        {
            return 1;
        }
        if matches!(scenario.as_str(), "M3-2" | "M3-3") && summary.n_queries != HISTORY_QUERY_COUNT
        {
            return 1;
        }
    }
    if active.iter().any(|scenario| scenario == "M3-2")
        && (!results.history_coverage.passes_m3_2
            || !results.history_coverage.passes_pointer_attestation)
    {
        return 1;
    }
    if active.iter().any(|scenario| scenario == "M3-3")
        && (!results.history_coverage.passes_m3_3 || !results.history_coverage.passes_restore)
    {
        return 1;
    }
    0
}

pub fn write_results(path: &Path, results: &EvaluationResults) -> Result<(), RunnerError> {
    // Serialize through `Value`: serde_json's map ordering is deterministic and
    // matches Python's `sort_keys=True` evaluator artifact contract.
    let value = serde_json::to_value(results)?;
    let mut bytes = serde_json::to_vec_pretty(&value)?;
    bytes.push(b'\n');
    fs::write(path, bytes).map_err(RunnerError::Write)
}

/// Stable Markdown report; its row order follows the caller's active scenario
/// order rather than hash-map iteration.
pub fn write_report(
    path: &Path,
    results: &EvaluationResults,
    active: &[String],
) -> Result<(), RunnerError> {
    let counts = &results.counts;
    let mut lines = vec![
        "# Kio 検索評価レポート (synthetic)".to_owned(),
        String::new(),
    ];
    lines.push(format!(
        "- 目標: 各シナリオ Recall@10 >= {} (docs/09 §4.3)",
        results.target_recall_at_10
    ));
    lines.push(format!(
        "- クエリ数: {} (scored={} / failed={} / unimplemented={})",
        counts.n_queries, counts.n_scored, counts.n_failed, counts.n_unimplemented
    ));
    if counts.n_unimplemented > 0 {
        lines.push("- 状態: **kio search 未実装のクエリあり (NOT-IMPLEMENTED)**。Recall 判定は無効 (exit 2)。".to_owned());
    }
    lines.extend([
        String::new(),
        "| シナリオ | クエリ数 | scored | Recall@10 | p95 ms | 目標 ms | 判定 |".to_owned(),
        "| --- | --- | --- | --- | --- | --- | --- |".to_owned(),
    ]);
    for scenario in active {
        let Some(summary) = results.scenarios.get(scenario) else {
            continue;
        };
        let recall = summary
            .recall_at_10
            .map_or_else(|| "-".to_owned(), |value| format!("{value:.3}"));
        let p95 = summary
            .p95_ms
            .map_or_else(|| "-".to_owned(), |value| format!("{value:.1}"));
        let verdict = if summary.n_scored == 0 {
            "n/a"
        } else if summary.passes_target && summary.passes_latency {
            "PASS"
        } else {
            "FAIL"
        };
        lines.push(format!(
            "| {scenario} | {} | {} | {recall} | {p95} | <{:.0} | {verdict} |",
            summary.n_queries, summary.n_scored, summary.latency_target_ms
        ));
    }
    if active.iter().any(|scenario| scenario == "M3-2") {
        lines.extend([
            String::new(),
            format!(
                "- M3-2 edited/rename structural coverage: {}",
                if results.history_coverage.passes_m3_2 {
                    "PASS"
                } else {
                    "FAIL"
                }
            ),
            format!(
                "- M3-2 pointer CAS attestation: {} ({} pointers)",
                if results.history_coverage.passes_pointer_attestation {
                    "PASS"
                } else {
                    "FAIL"
                },
                results.history_coverage.pointer_attested
            ),
        ]);
    }
    if active.iter().any(|scenario| scenario == "M3-3") {
        lines.extend([
            format!(
                "- M3-3 deleted coverage: {}",
                if results.history_coverage.passes_m3_3 {
                    "PASS"
                } else {
                    "FAIL"
                }
            ),
            format!(
                "- M3-3 restore verification: {}",
                if results.history_coverage.passes_restore {
                    "PASS"
                } else {
                    "FAIL"
                }
            ),
        ]);
    }
    lines.push(String::new());
    // Python writes `"\n".join(lines) + "\n"`; because `lines` ends with an
    // empty element this deliberately preserves two terminal LF bytes.
    fs::write(path, format!("{}\n", lines.join("\n"))).map_err(RunnerError::Write)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pointer() -> Value {
        let hash = |byte: char| format!("sha256:{}", byte.to_string().repeat(64));
        serde_json::json!({"schema_version":1,"commit":hash('c'),"raw_hash":hash('a'),"tool_profile_hash":hash('b'),"chunk_hash":hash('d'),"scope_id":"scope","path_at_commit":"a.md","section_id":"heading"})
    }
    fn outcome(code: i32, stdout: Value) -> SearchOutcome {
        SearchOutcome {
            returncode: code,
            stdout: stdout.to_string(),
            stderr: String::new(),
            duration_ms: 12.5,
        }
    }

    #[cfg(unix)]
    fn shell(command: &str) -> Command {
        let mut process = Command::new("sh");
        process.arg("-c").arg(command);
        process
    }

    #[cfg(unix)]
    #[test]
    fn bounded_process_times_out_and_reports_the_configured_limit() {
        let mut command = shell("sleep 5");
        let error = run_bounded_command(
            &mut command,
            BoundedProcessOptions {
                timeout: Duration::from_millis(100),
                max_stdout_bytes: 1024,
                max_stderr_bytes: 1024,
            },
        )
        .unwrap_err();
        assert!(matches!(
            error,
            BoundedProcessError::Timeout { timeout_ms: 100 }
        ));
    }

    /// This is invoked in a separate test binary by
    /// `bounded_process_timeout_does_not_wait_for_escaped_pipe_holders`.
    /// The direct child remains in the evaluator process group while its forked
    /// child creates a new session and keeps both inherited output pipes open.
    #[cfg(unix)]
    #[test]
    fn escaped_pipe_holder_helper() {
        use std::{ffi::CString, os::unix::ffi::OsStrExt};

        let Some(path) = std::env::var_os("KIO_EVAL_ESCAPED_PIPE_HOLDER") else {
            return;
        };
        let path = CString::new(path.as_os_str().as_bytes()).expect("marker path has no NUL");
        let child = unsafe { libc::fork() };
        assert!(
            child >= 0,
            "fork failed: {}",
            std::io::Error::last_os_error()
        );
        if child == 0 {
            if unsafe { libc::setsid() } < 0 {
                unsafe { libc::_exit(127) };
            }
            let descriptor = unsafe {
                libc::open(
                    path.as_ptr(),
                    libc::O_WRONLY | libc::O_TRUNC | libc::O_CLOEXEC,
                )
            };
            if descriptor < 0 {
                unsafe { libc::_exit(127) };
            }
            let mut digits = [0_u8; 20];
            let mut number = unsafe { libc::getpid() as u64 };
            let mut start = digits.len();
            loop {
                start -= 1;
                digits[start] = b'0' + (number % 10) as u8;
                number /= 10;
                if number == 0 {
                    break;
                }
            }
            let _ = unsafe {
                libc::write(
                    descriptor,
                    digits[start..].as_ptr().cast(),
                    digits.len() - start,
                )
            };
            unsafe {
                libc::close(descriptor);
                loop {
                    libc::pause();
                }
            }
        }
        unsafe {
            loop {
                libc::pause();
            }
        }
    }

    #[cfg(unix)]
    struct EscapedPipeHolder {
        marker: tempfile::TempPath,
    }

    #[cfg(unix)]
    impl Drop for EscapedPipeHolder {
        fn drop(&mut self) {
            let Ok(pid) = fs::read_to_string(&self.marker) else {
                return;
            };
            let Ok(pid) = pid.trim().parse::<i32>() else {
                return;
            };
            unsafe {
                libc::kill(pid, libc::SIGKILL);
            }
        }
    }

    #[cfg(unix)]
    #[test]
    fn bounded_process_timeout_does_not_wait_for_escaped_pipe_holders() {
        let marker = tempfile::NamedTempFile::new()
            .expect("create marker")
            .into_temp_path();
        let _holder = EscapedPipeHolder { marker };
        let mut command = Command::new(std::env::current_exe().expect("current test binary"));
        command
            .arg("--exact")
            .arg("runner::tests::escaped_pipe_holder_helper")
            .arg("--nocapture")
            .env("KIO_EVAL_ESCAPED_PIPE_HOLDER", &_holder.marker);
        let started = Instant::now();
        let error = run_bounded_command(
            &mut command,
            BoundedProcessOptions {
                timeout: Duration::from_millis(100),
                max_stdout_bytes: 1024,
                max_stderr_bytes: 1024,
            },
        )
        .unwrap_err();
        assert!(matches!(
            error,
            BoundedProcessError::Timeout { timeout_ms: 100 }
        ));
        assert!(
            started.elapsed() < Duration::from_secs(2),
            "timeout waited for an escaped pipe holder"
        );
        for _ in 0..20 {
            if fs::metadata(&_holder.marker)
                .ok()
                .is_some_and(|metadata| metadata.len() > 0)
            {
                return;
            }
            thread::sleep(Duration::from_millis(10));
        }
        panic!("escaped pipe holder did not record its pid");
    }

    #[cfg(unix)]
    #[test]
    fn bounded_process_stops_on_stdout_overflow() {
        let mut command = shell("while :; do printf x; done");
        let error = run_bounded_command(
            &mut command,
            BoundedProcessOptions {
                timeout: Duration::from_secs(2),
                max_stdout_bytes: 1024,
                max_stderr_bytes: 1024,
            },
        )
        .unwrap_err();
        assert!(matches!(
            error,
            BoundedProcessError::OutputLimit {
                stream: "stdout",
                limit: 1024
            }
        ));
    }

    #[cfg(unix)]
    #[test]
    fn bounded_process_rejects_non_utf8_stdout() {
        let mut command = shell("printf '\\377'");
        let error =
            run_bounded_command(&mut command, BoundedProcessOptions::default()).unwrap_err();
        assert!(matches!(
            error,
            BoundedProcessError::NonUtf8 { stream: "stdout" }
        ));
    }

    #[cfg(unix)]
    #[test]
    fn bounded_process_collects_both_terminal_stream_events_repeatedly() {
        for _ in 0..64 {
            let mut command = shell("printf stdout; printf stderr >&2");
            let output = run_bounded_command(&mut command, BoundedProcessOptions::default())
                .expect("both reader threads must deliver their terminal event");
            assert_eq!(output.stdout, "stdout");
            assert_eq!(output.stderr, "stderr");
        }
    }

    #[test]
    fn classifies_zero_and_partial_json_as_scored() {
        for code in [0, 3] {
            let classified = classify_outcome(&outcome(
                code,
                serde_json::json!({"results":[{"evidence_pointer":pointer()}]}),
            ));
            assert!(matches!(classified, ClassifiedOutcome::Scored { .. }));
        }
    }
    #[test]
    fn not_implemented_wins_over_exit_code() {
        let classified = classify_outcome(&outcome(
            1,
            serde_json::json!({"error_code":"KIO-E-SEARCH-NOT-IMPLEMENTED"}),
        ));
        assert!(matches!(
            classified,
            ClassifiedOutcome::Unimplemented { .. }
        ));
    }
    #[test]
    fn malformed_or_incomplete_success_is_failed() {
        let zero = classify_outcome(&outcome(0, serde_json::json!({"results":"bad"})));
        assert!(matches!(
            zero,
            ClassifiedOutcome::Failed { ref detail, .. }
                if detail == "exit 0 だが stdout が JSON レスポンスでない"
        ));
        let partial = classify_outcome(&outcome(
            3,
            serde_json::json!({"results":[{"evidence_pointer":{"schema_version":1}}]}),
        ));
        assert!(matches!(
            partial,
            ClassifiedOutcome::Failed { ref detail, .. }
                if detail == "exit 3 だが stdout が JSON レスポンスでない"
        ));
    }

    #[test]
    fn failure_artifact_omits_missing_error_code_and_preserves_detail() {
        let query = ResolvedQuery {
            scenario: "M3-1".to_owned(),
            query: "fixture query".to_owned(),
            expected: HashSet::new(),
            resolution_error: None,
        };
        let (results, _) = evaluate_queries(std::slice::from_ref(&query), 0.8, |_| {
            Ok(SearchOutcome {
                returncode: 1,
                stdout: String::new(),
                stderr: "plain failure".to_owned(),
                duration_ms: 1.0,
            })
        })
        .unwrap();
        let value = serde_json::to_value(&results).unwrap();
        let result = &value["queries"][0];
        assert!(result.get("error_code").is_none());
        assert_eq!(result["detail"], "exit=1: plain failure");

        let mut unresolved = query.clone();
        unresolved.resolution_error = Some("fixture cannot resolve".to_owned());
        let (results, _) = evaluate_queries(&[unresolved], 0.8, |_| {
            Ok(outcome(
                0,
                serde_json::json!({
                    "results": [],
                    "error_code": "KIO-E-SEARCH-BOOM-001"
                }),
            ))
        })
        .unwrap();
        let value = serde_json::to_value(&results).unwrap();
        assert_eq!(value["queries"][0]["error_code"], "KIO-E-SEARCH-BOOM-001");

        let (results, _) = evaluate_queries_with_validator(
            &[query],
            0.8,
            |_| Ok(outcome(0, serde_json::json!({"results":[]}))),
            |_, _| Err("pointer validation failed".to_owned()),
        )
        .unwrap();
        let value = serde_json::to_value(&results).unwrap();
        assert!(value["queries"][0].get("error_code").is_none());
    }
    #[test]
    fn report_is_deterministic_and_exit_policy_prioritizes_unimplemented() {
        let mut results = EvaluationResults {
            target_recall_at_10: 0.8,
            scenarios: BTreeMap::new(),
            queries: Vec::new(),
            history_coverage: HistoryCoverage::default(),
            counts: Counts {
                n_queries: 1,
                n_unimplemented: 1,
                ..Counts::default()
            },
        };
        results.scenarios.insert(
            "M3-1".to_owned(),
            ScenarioSummary {
                n_queries: 1,
                n_scored: 0,
                recall_at_10: None,
                passes_target: false,
                p95_ms: None,
                latency_target_ms: 5000.0,
                passes_latency: false,
            },
        );
        assert_eq!(final_exit_code(&results, &["M3-1".to_owned()]), 2);
        let path = std::env::temp_dir().join(format!("kio-eval-report-{}", std::process::id()));
        write_report(&path, &results, &["M3-1".to_owned()]).unwrap();
        let first = fs::read(&path).unwrap();
        write_report(&path, &results, &["M3-1".to_owned()]).unwrap();
        assert_eq!(first, fs::read(&path).unwrap());
        assert!(first.ends_with(b"\n\n"));
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn resolution_error_is_a_failed_zero_after_search_but_not_after_not_implemented() {
        let query = ResolvedQuery {
            scenario: "M3-1".to_owned(),
            query: "fixture query".to_owned(),
            expected: HashSet::new(),
            resolution_error: Some("missing fixture identity".to_owned()),
        };
        let (results, records) = evaluate_queries(std::slice::from_ref(&query), 0.8, |_| {
            Ok(outcome(0, serde_json::json!({"results":[]})))
        })
        .unwrap();
        assert!(records.is_empty());
        assert_eq!(results.counts.n_failed, 1);
        assert_eq!(results.queries[0].recall_at_10, Some(0.0));
        assert_eq!(
            results.queries[0].detail.as_deref(),
            Some("missing fixture identity")
        );
        assert_eq!(final_exit_code(&results, &["M3-1".to_owned()]), 1);

        let (results, _) = evaluate_queries(&[query], 0.8, |_| {
            Ok(outcome(
                1,
                serde_json::json!({"error_code":"KIO-E-SEARCH-NOT-IMPLEMENTED"}),
            ))
        })
        .unwrap();
        assert_eq!(results.counts.n_unimplemented, 1);
        assert_eq!(results.counts.n_failed, 0);
        assert_eq!(final_exit_code(&results, &["M3-1".to_owned()]), 2);
    }

    #[test]
    fn results_json_has_a_single_terminal_newline() {
        let results = EvaluationResults {
            target_recall_at_10: 0.8,
            scenarios: BTreeMap::new(),
            queries: Vec::new(),
            history_coverage: HistoryCoverage::default(),
            counts: Counts::default(),
        };
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("results.json");
        write_results(&path, &results).unwrap();
        let bytes = fs::read(path).unwrap();
        assert!(bytes.ends_with(b"\n"));
        assert!(!bytes.ends_with(b"\n\n"));
    }
}
