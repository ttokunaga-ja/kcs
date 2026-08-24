//! Current-v2, descriptor-bound scale benchmark.
//!
//! This intentionally consumes the receipts produced by `prepare` and
//! `attest`; it has no fixture generator, Python parser, or legacy fallback.

use std::{
    collections::BTreeSet,
    fs,
    io::{Read, Seek, SeekFrom},
    path::{Component, Path, PathBuf},
    time::Duration,
};

use cap_primitives::fs as cap_fs;
#[cfg(windows)]
use cap_primitives::fs::_WindowsByHandle;
#[cfg(unix)]
use cap_primitives::fs::MetadataExt;
use kio_index::chunking::slugify_heading;
use serde::Serialize;
use serde_json::{Map, Value};
use thiserror::Error;

use crate::{
    process_boundary::{
        DescriptorExecutable, ProcessBoundaryError, configure_descriptor_environment,
        configure_retained_cwd,
    },
    runner::{BoundedProcessOptions, run_bounded_command},
    scale_attest::{
        AttestError, attest_ready, publish_external_artifact, validate_benchmark_attestation,
    },
    scale_fixture::{ScaleFixtureError, bind_ready},
    scale_prepare::{BenchmarkDevice, ScalePrepareError, validate_benchmark_prepare_report},
    scale_spec::{self, ScaleProfile},
};

const MAX_WARMUPS: usize = 5;
const MAX_SAMPLES: usize = 100;
const MAX_METRICS_LOG_BYTES: u64 = 64 * 1024 * 1024;
const MAX_METRICS_DELTA_BYTES: u64 = 64 * 1024;
const MAX_METRIC_LINE_BYTES: u64 = 32 * 1024;
const RESULT_LIMIT: usize = 10;
const SCENARIOS: [(&str, Option<&str>, f64); 3] = [
    ("M3-1", None, 5_000.0),
    ("M3-2", Some("--all-history"), 7_000.0),
    ("M3-3", Some("--include-deleted"), 7_000.0),
];

#[derive(Debug, Error)]
pub enum ScaleBenchmarkError {
    #[error("invalid scale benchmark input: {0}")]
    Input(String),
    #[error(transparent)]
    Fixture(#[from] ScaleFixtureError),
    #[error(transparent)]
    Attest(#[from] AttestError),
    #[error(transparent)]
    Prepare(#[from] ScalePrepareError),
    #[error("unsafe scale benchmark process boundary: {0}")]
    Boundary(String),
    #[error(transparent)]
    Process(#[from] crate::runner::BoundedProcessError),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

#[derive(Debug)]
pub struct BenchmarkSummary {
    pub report: PathBuf,
    pub acceptance_failed: bool,
}

#[derive(Serialize)]
struct Report<'a> {
    schema_version: u64,
    benchmark: &'static str,
    fixture_id: &'static str,
    profile: ScaleProfile,
    manifest_hash: String,
    content_root_hash: &'a str,
    scope_count: usize,
    current_chunks: u64,
    registry_rows: usize,
    prepare_report_sha256: String,
    attestation_sha256: String,
    binary_sha256: String,
    binary_bytes: u64,
    warmups: usize,
    samples: usize,
    measurement_class: &'static str,
    acceptance_eligible: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    passed_p95_thresholds: Option<bool>,
    platform: Platform,
    configuration: Configuration,
    scenarios: Vec<Scenario>,
}
#[derive(Serialize)]
struct Scenario {
    name: &'static str,
    selector_flag: Option<&'static str>,
    raw_samples: Vec<Sample>,
    process_wall_statistics_ms: Statistics,
    metric_statistics_ms: Statistics,
    #[serde(skip_serializing_if = "Option::is_none")]
    p95_threshold_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    passed_p95_threshold: Option<bool>,
}
#[derive(Serialize)]
struct Sample {
    sequence: usize,
    query_index: usize,
    process_wall_duration_ms: f64,
    search_latency_ms: f64,
}
#[derive(Serialize)]
struct Statistics {
    p50: f64,
    p95: f64,
    p99: f64,
    min: f64,
    max: f64,
}
#[derive(Serialize)]
struct Platform {
    os: &'static str,
    arch: &'static str,
    family: &'static str,
}
#[derive(Serialize)]
struct Configuration {
    warmups: usize,
    samples: usize,
    query_schedule: &'static str,
    result_limit: usize,
}

fn boundary(e: ProcessBoundaryError) -> ScaleBenchmarkError {
    ScaleBenchmarkError::Boundary(e.to_string())
}
fn digest(bytes: &[u8]) -> String {
    kio_core::cas::hash_bytes(bytes)
}
fn formal_eligible(profile: ScaleProfile, chunks: u64, warmups: usize, samples: usize) -> bool {
    profile == ScaleProfile::Full && chunks >= 100_001 && warmups == 5 && samples == 100
}

fn measurement_class(profile: ScaleProfile, formal: bool) -> &'static str {
    match (profile, formal) {
        (ScaleProfile::Full, true) => "full_100k_acceptance",
        (ScaleProfile::Full, false) => "full_non_acceptance",
        (ScaleProfile::Tiny, _) => "tiny_smoke",
    }
}

fn passes_threshold(scenario: &Scenario, threshold: f64) -> bool {
    // The product metric remains the primary latency signal, while the
    // evaluator-owned wall clock is an independent upper-bound guard against
    // a target binary under-reporting its own instrumentation.
    scenario.metric_statistics_ms.p95 < threshold
        && scenario.process_wall_statistics_ms.p95 < threshold
}

fn object<'a>(
    value: &'a Value,
    label: &str,
) -> Result<&'a Map<String, Value>, ScaleBenchmarkError> {
    value
        .as_object()
        .ok_or_else(|| ScaleBenchmarkError::Input(format!("{label} must be an object")))
}

fn exact_keys(
    object: &Map<String, Value>,
    keys: &[&str],
    label: &str,
) -> Result<(), ScaleBenchmarkError> {
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = keys.iter().copied().collect::<BTreeSet<_>>();
    if actual != expected {
        return Err(ScaleBenchmarkError::Input(format!(
            "{label} field set mismatch"
        )));
    }
    Ok(())
}

fn validate_response(
    stdout: &str,
    query: &scale_spec::ScaleQuery,
    expected_scope_id: &str,
    scope_ids: &BTreeSet<String>,
) -> Result<usize, ScaleBenchmarkError> {
    let value: Value = serde_json::from_str(stdout)
        .map_err(|_| ScaleBenchmarkError::Input("search returned invalid JSON".into()))?;
    let response = object(&value, "search response")?;
    if response.get("query").and_then(Value::as_str) != Some(query.query.as_str())
        || response.get("requested_mode").and_then(Value::as_str) != Some("auto")
        || response.get("resolved_mode").and_then(Value::as_str) != Some("text")
        || response.get("fallback") != Some(&Value::Bool(true))
        || response.get("fallback_reason").and_then(Value::as_str)
            != Some("embedding_endpoint_not_configured")
    {
        return Err(ScaleBenchmarkError::Input(
            "scale search did not use the expected auto text fallback".into(),
        ));
    }
    let searched = response
        .get("searched_scopes")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            ScaleBenchmarkError::Input("search response has no searched scopes".into())
        })?;
    if searched.len() != scale_spec::SCOPE_COUNT
        || response.get("excluded_scopes") != Some(&Value::Array(Vec::new()))
    {
        return Err(ScaleBenchmarkError::Input(
            "search did not report exactly the frozen 20 scopes".into(),
        ));
    }
    let searched_ids = searched
        .iter()
        .map(|scope| {
            object(scope, "searched scope")?
                .get("scope_id")
                .and_then(Value::as_str)
                .map(ToOwned::to_owned)
                .ok_or_else(|| ScaleBenchmarkError::Input("searched scope lacks scope_id".into()))
        })
        .collect::<Result<BTreeSet<_>, _>>()?;
    if &searched_ids != scope_ids || searched_ids.len() != scale_spec::SCOPE_COUNT {
        return Err(ScaleBenchmarkError::Input(
            "search scope identities differ from attestation".into(),
        ));
    }
    let results = response
        .get("results")
        .and_then(Value::as_array)
        .filter(|results| !results.is_empty() && results.len() <= RESULT_LIMIT)
        .ok_or_else(|| ScaleBenchmarkError::Input("search returned invalid results".into()))?;
    let expected_section = slugify_heading(&query.heading);
    let found = results.iter().any(|result| {
        result
            .get("evidence_pointer")
            .and_then(Value::as_object)
            .is_some_and(|pointer| {
                pointer.get("scope_id").and_then(Value::as_str) == Some(expected_scope_id)
                    && pointer.get("path_at_commit").and_then(Value::as_str)
                        == Some(query.file.as_str())
                    && pointer.get("section_id").and_then(Value::as_str)
                        == Some(expected_section.as_str())
            })
    });
    if !found {
        return Err(ScaleBenchmarkError::Input(
            "search did not return the scheduled evidence pointer".into(),
        ));
    }
    Ok(results.len())
}

struct MetricsSnapshot {
    parent: fs::File,
    before: Option<cap_fs::Metadata>,
    offset: u64,
}

#[cfg(unix)]
fn same_file(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    left.dev() == right.dev() && left.ino() == right.ino()
}
#[cfg(windows)]
fn same_file(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> bool {
    matches!(
        (
            left.volume_serial_number(),
            left.file_index(),
            right.volume_serial_number(),
            right.file_index(),
        ),
        (Some(left_volume), Some(left_index), Some(right_volume), Some(right_index))
            if left_volume == right_volume && left_index == right_index
    )
}
#[cfg(not(any(unix, windows)))]
fn same_file(_: &cap_fs::Metadata, _: &cap_fs::Metadata) -> bool {
    false
}

fn open_metrics(parent: &fs::File) -> Result<(fs::File, cap_fs::Metadata), ScaleBenchmarkError> {
    let before = cap_fs::stat(
        parent,
        Path::new("metrics.jsonl"),
        cap_fs::FollowSymlinks::No,
    )
    .map_err(|error| ScaleBenchmarkError::Input(format!("cannot inspect metrics log: {error}")))?;
    #[cfg(unix)]
    let safe_links = before.nlink() == 1;
    #[cfg(windows)]
    let safe_links = before.number_of_links() == Some(1);
    #[cfg(not(any(unix, windows)))]
    let safe_links = false;
    if !before.is_file()
        || before.file_type().is_symlink()
        || !safe_links
        || before.len() > MAX_METRICS_LOG_BYTES
    {
        return Err(ScaleBenchmarkError::Input(
            "metrics log must be a bounded single-link regular file".into(),
        ));
    }
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let file = cap_fs::open(parent, Path::new("metrics.jsonl"), &options).map_err(|error| {
        ScaleBenchmarkError::Input(format!(
            "cannot open metrics log without following links: {error}"
        ))
    })?;
    let opened = cap_fs::Metadata::from_file(&file).map_err(|error| {
        ScaleBenchmarkError::Input(format!("cannot inspect metrics log: {error}"))
    })?;
    let after = cap_fs::stat(
        parent,
        Path::new("metrics.jsonl"),
        cap_fs::FollowSymlinks::No,
    )
    .map_err(|error| ScaleBenchmarkError::Input(format!("cannot recheck metrics log: {error}")))?;
    #[cfg(unix)]
    let opened_links_safe = opened.nlink() == 1 && after.nlink() == 1;
    #[cfg(windows)]
    let opened_links_safe =
        opened.number_of_links() == Some(1) && after.number_of_links() == Some(1);
    #[cfg(not(any(unix, windows)))]
    let opened_links_safe = false;
    if !opened.is_file()
        || !opened_links_safe
        || !same_file(&before, &opened)
        || !same_file(&opened, &after)
        || before.len() != opened.len()
        || opened.len() != after.len()
    {
        return Err(ScaleBenchmarkError::Input(
            "metrics log changed while opening".into(),
        ));
    }
    Ok((file, opened))
}

fn snapshot_metrics_log(parent: &fs::File) -> Result<MetricsSnapshot, ScaleBenchmarkError> {
    if matches!(cap_fs::stat(parent, Path::new("metrics.jsonl"), cap_fs::FollowSymlinks::No), Err(error) if error.kind() == std::io::ErrorKind::NotFound)
    {
        return Ok(MetricsSnapshot {
            parent: parent.try_clone()?,
            before: None,
            offset: 0,
        });
    }
    let (mut file, metadata) = open_metrics(parent)?;
    if metadata.len() > 0 {
        file.seek(SeekFrom::End(-1))?;
        let mut byte = [0];
        file.read_exact(&mut byte)?;
        if byte != *b"\n" {
            return Err(ScaleBenchmarkError::Input(
                "existing metrics log lacks a final newline".into(),
            ));
        }
    }
    Ok(MetricsSnapshot {
        parent: parent.try_clone()?,
        offset: metadata.len(),
        before: Some(metadata),
    })
}

fn appended_search_metric(
    snapshot: MetricsSnapshot,
    result_count: usize,
) -> Result<f64, ScaleBenchmarkError> {
    let (mut file, current) = open_metrics(&snapshot.parent)?;
    let start = match snapshot.before.as_ref() {
        Some(before) if same_file(before, &current) => snapshot.offset,
        Some(_) => {
            return Err(ScaleBenchmarkError::Input(
                "metrics log was replaced during search".into(),
            ));
        }
        None => 0,
    };
    let delta = current
        .len()
        .checked_sub(start)
        .ok_or_else(|| ScaleBenchmarkError::Input("metrics log shrank during search".into()))?;
    if delta == 0 || delta > MAX_METRICS_DELTA_BYTES || delta > MAX_METRIC_LINE_BYTES {
        return Err(ScaleBenchmarkError::Input(
            "search must append one bounded metrics line".into(),
        ));
    }
    file.seek(SeekFrom::Start(start))?;
    let mut raw = vec![0; delta as usize];
    file.read_exact(&mut raw)?;
    let opened_after = cap_fs::Metadata::from_file(&file)?;
    let (_, named_after) = open_metrics(&snapshot.parent)?;
    if !same_file(&current, &opened_after)
        || !same_file(&current, &named_after)
        || opened_after.len() != current.len()
    {
        return Err(ScaleBenchmarkError::Input(
            "metrics log changed while reading its append".into(),
        ));
    }
    if !raw.ends_with(b"\n") || raw.iter().filter(|byte| **byte == b'\n').count() != 1 {
        return Err(ScaleBenchmarkError::Input(
            "search must append exactly one LF-terminated metrics line".into(),
        ));
    }
    let metric: Value = serde_json::from_slice(&raw)
        .map_err(|_| ScaleBenchmarkError::Input("search metric is invalid JSON".into()))?;
    let metric = object(&metric, "search metric")?;
    exact_keys(
        metric,
        &[
            "ts",
            "level",
            "code",
            "component",
            "message",
            "metric",
            "value",
            "context",
        ],
        "search metric",
    )?;
    if metric
        .get("ts")
        .and_then(Value::as_str)
        .is_none_or(str::is_empty)
        || metric.get("level").and_then(Value::as_str) != Some("info")
        || metric.get("code").and_then(Value::as_str) != Some("KIO-M-SEARCH-001")
        || metric.get("component").and_then(Value::as_str) != Some("search")
        || metric.get("message").and_then(Value::as_str) != Some("search completed")
        || metric.get("metric").and_then(Value::as_str) != Some("search.latency_ms")
    {
        return Err(ScaleBenchmarkError::Input(
            "KIO-M-SEARCH-001 envelope is invalid".into(),
        ));
    }
    let context = object(
        metric
            .get("context")
            .ok_or_else(|| ScaleBenchmarkError::Input("search metric context missing".into()))?,
        "search metric context",
    )?;
    exact_keys(
        context,
        &["mode", "scope_count", "result_count"],
        "search metric context",
    )?;
    if context.get("mode").and_then(Value::as_str) != Some("text")
        || context.get("scope_count").and_then(Value::as_u64)
            != Some(scale_spec::SCOPE_COUNT as u64)
        || context.get("result_count").and_then(Value::as_u64) != Some(result_count as u64)
    {
        return Err(ScaleBenchmarkError::Input(
            "search metric context disagrees with response".into(),
        ));
    }
    metric
        .get("value")
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite() && *value >= 0.0)
        .ok_or_else(|| ScaleBenchmarkError::Input("KIO-M-SEARCH-001 has invalid latency".into()))
}

fn statistics(values: &[f64]) -> Result<Statistics, ScaleBenchmarkError> {
    if values.is_empty()
        || values
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
    {
        return Err(ScaleBenchmarkError::Input(
            "latency samples must be nonempty finite values".into(),
        ));
    }
    let percentile = |fraction: f64| {
        let mut sorted = values.to_vec();
        sorted.sort_by(f64::total_cmp);
        sorted[((fraction * sorted.len() as f64).ceil() as usize).saturating_sub(1)]
    };
    Ok(Statistics {
        p50: percentile(0.50),
        p95: percentile(0.95),
        p99: percentile(0.99),
        min: values.iter().copied().fold(f64::INFINITY, f64::min),
        max: values.iter().copied().fold(f64::NEG_INFINITY, f64::max),
    })
}

fn clean_absolute(path: &Path) -> Result<(), ScaleBenchmarkError> {
    if !path.is_absolute()
        || path.file_name().is_none()
        || path
            .components()
            .any(|c| matches!(c, Component::ParentDir | Component::CurDir))
    {
        return Err(ScaleBenchmarkError::Input(
            "benchmark output must be a clean absolute path".into(),
        ));
    }
    Ok(())
}

fn absolutize_binary(bin: &Path) -> Result<PathBuf, ScaleBenchmarkError> {
    if bin.is_absolute() {
        return Ok(bin.to_owned());
    }
    if bin
        .components()
        .any(|component| matches!(component, Component::CurDir | Component::ParentDir))
    {
        return Err(ScaleBenchmarkError::Input(
            "relative binary path must be lexical normal components".into(),
        ));
    }
    let cwd = std::env::current_dir().map_err(|error| {
        ScaleBenchmarkError::Input(format!("cannot resolve current directory: {error}"))
    })?;
    let absolute = cwd.join(bin);
    if !absolute.is_absolute() {
        return Err(ScaleBenchmarkError::Input(
            "binary path cannot be made absolute".into(),
        ));
    }
    Ok(absolute)
}

/// Execute exactly the requested bounded samples.  Full fixtures are formal
/// only at 5 warmups / 100 samples; tiny fixtures are intentionally smoke-only.
pub fn benchmark(
    corpus: &Path,
    bin: &Path,
    warmups: usize,
    samples: usize,
    out: &Path,
) -> Result<BenchmarkSummary, ScaleBenchmarkError> {
    if !(1..=MAX_WARMUPS).contains(&warmups) || !(1..=MAX_SAMPLES).contains(&samples) {
        return Err(ScaleBenchmarkError::Input(
            "warmups must be 1..=5 and samples must be 1..=100".into(),
        ));
    }
    DescriptorExecutable::preflight_platform().map_err(boundary)?;
    let bin = absolutize_binary(bin)?;
    let fixture = bind_ready(corpus)?;
    let _lock = fixture.lock()?;
    let before = attest_ready(&fixture)?;
    let exe = DescriptorExecutable::bind_build_artifact(&bin).map_err(boundary)?;
    let prepare =
        validate_benchmark_prepare_report(&fixture, &exe, &before.scopes, before.registry_rows)?;
    let attest_bytes = validate_benchmark_attestation(&fixture, &before)?;
    let binary_sha = format!("sha256:{}", exe.immutable_binding().sha256);
    let device = BenchmarkDevice::bind(&fixture)?;
    let scope = fixture.try_clone_scope(&fixture.manifest().scopes[0].name)?;
    let metrics = device.metrics_directory(fixture.root())?;
    let scope_ids = before
        .scopes
        .iter()
        .map(|scope| scope.scope_id.clone())
        .collect::<BTreeSet<_>>();
    let mut scenarios = Vec::new();
    for (name, flag, _) in SCENARIOS {
        let mut raw_samples = Vec::with_capacity(samples);
        let mut wall_samples = Vec::with_capacity(samples);
        let mut metric_samples = Vec::with_capacity(samples);
        for iteration in 0..warmups + samples {
            fixture.recheck()?;
            device.recheck(fixture.root())?;
            exe.recheck_original().map_err(boundary)?;
            let mut cmd = exe.command().map_err(boundary)?;
            let query_index = iteration % fixture.manifest().queries.len();
            let query = &fixture.manifest().queries[query_index];
            let expected_scope_id = before
                .scopes
                .iter()
                .find(|scope| scope.name == query.scope)
                .map(|scope| scope.scope_id.as_str())
                .ok_or_else(|| {
                    ScaleBenchmarkError::Input(
                        "manifest query scope is absent from attestation".into(),
                    )
                })?;
            cmd.arg("--json")
                .arg("search")
                .arg(&query.query)
                .arg("--all-scopes")
                .arg("--limit")
                .arg("10");
            if let Some(flag) = flag {
                cmd.arg(flag);
            }
            configure_descriptor_environment(&mut cmd, &device.environment()?).map_err(boundary)?;
            configure_retained_cwd(&mut cmd, &scope).map_err(boundary)?;
            let metrics_snapshot = snapshot_metrics_log(&metrics)?;
            let output = run_bounded_command(
                &mut cmd,
                BoundedProcessOptions {
                    timeout: Duration::from_secs(30),
                    max_stdout_bytes: 1024 * 1024,
                    max_stderr_bytes: 32 * 1024,
                },
                None,
            )?;
            if !output.status.success() {
                return Err(ScaleBenchmarkError::Input(format!(
                    "{name} search failed: {}",
                    output.stderr.trim()
                )));
            }
            fixture.recheck()?;
            device.recheck(fixture.root())?;
            exe.recheck_original().map_err(boundary)?;
            let result_count =
                validate_response(&output.stdout, query, expected_scope_id, &scope_ids)?;
            let metric = appended_search_metric(metrics_snapshot, result_count)?;
            if iteration >= warmups {
                let wall = output.duration.as_secs_f64() * 1000.0;
                wall_samples.push(wall);
                metric_samples.push(metric);
                raw_samples.push(Sample {
                    sequence: iteration - warmups,
                    query_index,
                    process_wall_duration_ms: wall,
                    search_latency_ms: metric,
                });
            }
        }
        let wall_statistics = statistics(&wall_samples)?;
        let metric_statistics = statistics(&metric_samples)?;
        scenarios.push(Scenario {
            name,
            selector_flag: flag,
            raw_samples,
            process_wall_statistics_ms: wall_statistics,
            p95_threshold_ms: None,
            passed_p95_threshold: None,
            metric_statistics_ms: metric_statistics,
        });
    }
    let after = attest_ready(&fixture)?;
    if before != after {
        return Err(ScaleBenchmarkError::Input(
            "fixture evidence changed during benchmark".into(),
        ));
    }
    fixture.recheck()?;
    device.recheck(fixture.root())?;
    exe.recheck_original().map_err(boundary)?;
    if validate_benchmark_prepare_report(&fixture, &exe, &after.scopes, after.registry_rows)?
        != prepare
        || validate_benchmark_attestation(&fixture, &after)? != attest_bytes
    {
        return Err(ScaleBenchmarkError::Input(
            "published receipt changed during benchmark".into(),
        ));
    }
    let formal = formal_eligible(fixture.profile(), before.current_chunks, warmups, samples);
    if formal {
        for (scenario, (_, _, threshold)) in scenarios.iter_mut().zip(SCENARIOS) {
            scenario.p95_threshold_ms = Some(threshold);
            scenario.passed_p95_threshold = Some(passes_threshold(scenario, threshold));
        }
    }
    let passed = formal.then(|| {
        scenarios
            .iter()
            .all(|scenario| scenario.passed_p95_threshold == Some(true))
    });
    let report = Report {
        schema_version: scale_spec::SCHEMA_VERSION,
        benchmark: "kio-eval scale benchmark/v2",
        fixture_id: scale_spec::FIXTURE_ID,
        profile: fixture.profile(),
        manifest_hash: scale_spec::manifest_hash(fixture.manifest())
            .map_err(|e| ScaleBenchmarkError::Input(e.to_string()))?,
        content_root_hash: &fixture.manifest().content_root_hash,
        scope_count: before.scopes.len(),
        current_chunks: before.current_chunks,
        registry_rows: before.registry_rows,
        prepare_report_sha256: digest(&prepare),
        attestation_sha256: digest(&attest_bytes),
        binary_sha256: binary_sha,
        binary_bytes: exe.immutable_binding().bytes,
        warmups,
        samples,
        measurement_class: measurement_class(fixture.profile(), formal),
        acceptance_eligible: formal,
        passed_p95_thresholds: passed,
        platform: Platform {
            os: std::env::consts::OS,
            arch: std::env::consts::ARCH,
            family: std::env::consts::FAMILY,
        },
        configuration: Configuration {
            warmups,
            samples,
            query_schedule: "manifest order round-robin; scenarios deterministic",
            result_limit: RESULT_LIMIT,
        },
        scenarios,
    };
    let mut bytes = kio_core::cas::canonical_json_bytes(&serde_json::to_value(report)?)
        .map_err(|e| ScaleBenchmarkError::Input(e.to_string()))?;
    bytes.push(b'\n');
    clean_absolute(out)?;
    publish_external_artifact(out, &fixture, &bytes)?;
    Ok(BenchmarkSummary {
        report: out.to_owned(),
        acceptance_failed: formal && passed != Some(true),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bounds_are_closed() {
        assert!(benchmark(Path::new("/x"), Path::new("/x"), 0, 1, Path::new("/x")).is_err());
    }

    #[test]
    fn relative_binary_is_lexically_absolutized() {
        let absolute = absolutize_binary(Path::new("target/release/kio")).unwrap();
        assert!(absolute.is_absolute());
        assert!(absolute.ends_with("target/release/kio"));
        assert!(absolutize_binary(Path::new("../target/release/kio")).is_err());
    }

    #[test]
    fn response_binds_query_scope_and_evidence() {
        let query = scale_spec::ScaleQuery {
            query: "needle".into(),
            scope: "scope-00".into(),
            file: "document-0000.md".into(),
            heading: "heading".into(),
        };
        let scope_ids = (0..scale_spec::SCOPE_COUNT)
            .map(|index| format!("scope-{index:02}"))
            .collect::<BTreeSet<_>>();
        let response = serde_json::json!({
            "query": "needle",
            "requested_mode": "auto",
            "resolved_mode": "text",
            "fallback": true,
            "fallback_reason": "embedding_endpoint_not_configured",
            "searched_scopes": scope_ids.iter().map(|id| serde_json::json!({"scope_id": id})).collect::<Vec<_>>(),
            "excluded_scopes": [],
            "results": [{"evidence_pointer": {"scope_id": "scope-00", "path_at_commit": "document-0000.md", "section_id": "heading"}}],
        });
        assert_eq!(
            validate_response(&response.to_string(), &query, "scope-00", &scope_ids).unwrap(),
            1
        );
        let mut missing = response;
        missing["results"] = Value::Array(Vec::new());
        assert!(validate_response(&missing.to_string(), &query, "scope-00", &scope_ids).is_err());
        assert!(validate_response("{}", &query, "scope-00", &scope_ids).is_err());
    }

    #[test]
    fn metrics_delta_is_one_strict_search_line() {
        let temp = tempfile::tempdir().unwrap();
        let parent =
            cap_fs::open_ambient_dir(temp.path(), cap_primitives::ambient_authority()).unwrap();
        let snapshot = snapshot_metrics_log(&parent).unwrap();
        let line = serde_json::json!({
            "ts": "2026-08-15T00:00:00Z",
            "level": "info",
            "code": "KIO-M-SEARCH-001",
            "component": "search",
            "message": "search completed",
            "metric": "search.latency_ms",
            "value": 12.5,
            "context": {"mode": "text", "scope_count": 20, "result_count": 1}
        });
        fs::write(temp.path().join("metrics.jsonl"), format!("{line}\n")).unwrap();
        assert_eq!(appended_search_metric(snapshot, 1).unwrap(), 12.5);

        let snapshot = snapshot_metrics_log(&parent).unwrap();
        let mut wrong = line;
        wrong["context"]["scope_count"] = Value::from(19);
        let mut file = fs::OpenOptions::new()
            .append(true)
            .open(temp.path().join("metrics.jsonl"))
            .unwrap();
        use std::io::Write as _;
        writeln!(file, "{wrong}").unwrap();
        assert!(appended_search_metric(snapshot, 1).is_err());
    }

    #[test]
    fn tiny_is_never_formal() {
        assert!(!formal_eligible(ScaleProfile::Tiny, 120_000, 5, 100));
        assert!(!formal_eligible(ScaleProfile::Full, 100_000, 5, 100));
        assert!(!formal_eligible(ScaleProfile::Full, 120_000, 4, 100));
        assert!(formal_eligible(ScaleProfile::Full, 120_000, 5, 100));
        assert_eq!(measurement_class(ScaleProfile::Tiny, false), "tiny_smoke");
        assert_eq!(
            measurement_class(ScaleProfile::Full, false),
            "full_non_acceptance"
        );
        assert_eq!(
            measurement_class(ScaleProfile::Full, true),
            "full_100k_acceptance"
        );
    }

    #[test]
    fn formal_threshold_requires_metric_and_evaluator_wall_clock() {
        let scenario = |metric: f64, wall: f64| Scenario {
            name: "M3-1",
            selector_flag: None,
            raw_samples: Vec::new(),
            process_wall_statistics_ms: statistics(&[wall]).unwrap(),
            metric_statistics_ms: statistics(&[metric]).unwrap(),
            p95_threshold_ms: Some(5_000.0),
            passed_p95_threshold: None,
        };
        assert!(passes_threshold(&scenario(10.0, 20.0), 5_000.0));
        assert!(!passes_threshold(&scenario(0.0, 5_001.0), 5_000.0));
        assert!(!passes_threshold(&scenario(5_001.0, 10.0), 5_000.0));
    }
}
