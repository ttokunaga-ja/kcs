//! Command-line boundary for the internal evaluator.
//!
//! All fixture parsing and scoring remains in the library.  This module owns
//! only CLI defaults, the fixed synthetic-device process environment, and the
//! small amount of live-CAS orchestration that cannot be expressed as a pure
//! metric.

use std::{
    collections::HashMap,
    env,
    ffi::OsString,
    fs,
    io::Read,
    path::{Path, PathBuf},
    process::Command,
};

use cap_primitives::fs as cap_fs;
use clap::{Parser, Subcommand};
use kio_core::{
    cas::{hash_bytes, read_bounded_regular_file, MAX_RAW_OBJECT_BYTES},
    ExitCode,
};
use kio_eval::{
    attestation::{PointerAttestor, MAX_POINTER_ATTESTATIONS_PER_QUERY},
    boundary::{BoundCorpus, BoundDevice, BoundScope},
    manifest::{
        load_corpus_manifest, load_golden_queries, load_history_manifest, Scenario, SCOPES,
    },
    qhard::{self, BaselineAttestOptions, BaselineOptions, QhardOptions},
    resolver::{validate_query, CorpusModel, Resolver},
    runner::{
        assess_history_coverage, evaluate_queries_with_validator, final_exit_code,
        run_bounded_command, write_report, write_results, BoundedProcessOptions, HistoryEntryRef,
        HistoryManifestRef, RenameEntryRef, ResolvedQuery, ScoredRecord,
    },
    scale::{self, ScaleOptions},
};
use thiserror::Error;

const DEFAULT_BIN: &str = "target/release/kio";

#[derive(Debug, Parser)]
#[command(name = "kio-eval", about = "Kio synthetic search evaluator")]
pub struct Args {
    #[command(subcommand)]
    command: Option<Commands>,
    #[arg(long)]
    golden: Option<PathBuf>,
    #[arg(long)]
    corpus: Option<PathBuf>,
    #[arg(long)]
    corpus_manifest: Option<PathBuf>,
    #[arg(long)]
    history_manifest: Option<PathBuf>,
    /// Trusted local Kio executable under test. Resource bounds contain
    /// accidental hangs/output floods; they do not sandbox hostile code.
    #[arg(long, default_value = DEFAULT_BIN)]
    bin: PathBuf,
    #[arg(long)]
    out: Option<PathBuf>,
    #[arg(long)]
    report: Option<PathBuf>,
    #[arg(long, value_parser = parse_scenario)]
    scenario: Vec<String>,
    #[arg(long, default_value_t = 0.8, value_parser = parse_recall)]
    min_recall: f64,
    #[arg(long)]
    dry_run: bool,
}

#[derive(Debug, Subcommand)]
enum Commands {
    /// Materialize the frozen synthetic evaluation corpus.
    GenerateCorpus {
        #[arg(long)]
        out: PathBuf,
        #[arg(long)]
        force: bool,
    },
    /// Measure deterministic search latency on an attested scale corpus.
    Benchmark {
        #[command(subcommand)]
        command: BenchmarkCommands,
    },
}

#[derive(Debug, Subcommand)]
enum BenchmarkCommands {
    /// Attest matching indexed and pristine fixture-B trees before measurement.
    BaselineAttest {
        #[arg(long, default_value = "eval/golden-queries-fixture-b.jsonl")]
        golden: PathBuf,
        #[arg(long)]
        fixture_root: PathBuf,
        #[arg(long)]
        baseline_corpus: PathBuf,
        #[arg(long)]
        out: PathBuf,
    },
    /// Compare Kio with Spotlight and ripgrep-all on frozen fixture-B.
    Baseline {
        #[arg(long, default_value = "eval/golden-queries-fixture-b.jsonl")]
        golden: PathBuf,
        #[arg(long)]
        fixture_root: PathBuf,
        #[arg(long)]
        baseline_corpus: PathBuf,
        #[arg(long)]
        attestation: PathBuf,
        #[arg(long, default_value = DEFAULT_BIN)]
        bin: PathBuf,
        #[arg(long, default_value = "mdfind")]
        mdfind: PathBuf,
        #[arg(long, default_value = "rga")]
        rga: PathBuf,
        #[arg(long)]
        online_query: bool,
        #[arg(long)]
        out: Option<PathBuf>,
    },
    /// Run the 20-scope scale search measurement lane.
    Scale {
        #[arg(long)]
        corpus: PathBuf,
        #[arg(long)]
        manifest: Option<PathBuf>,
        #[arg(long)]
        attestation: Option<PathBuf>,
        #[arg(long, default_value = DEFAULT_BIN)]
        bin: PathBuf,
        #[arg(long)]
        out: Option<PathBuf>,
        #[arg(long, default_value_t = 5)]
        warmups: usize,
        #[arg(long, default_value_t = 100)]
        samples: usize,
    },
    /// Measure the frozen external raster/vector Q_hard fixture.
    Qhard {
        #[arg(long, default_value = "eval/golden-queries-qhard.jsonl")]
        golden: PathBuf,
        #[arg(long)]
        fixture_root: PathBuf,
        #[arg(long, default_value = "qhard")]
        tree: String,
        #[arg(long, default_value = "qhard")]
        env_name: String,
        #[arg(long)]
        attestation: Option<PathBuf>,
        #[arg(long, default_value = DEFAULT_BIN)]
        bin: PathBuf,
        #[arg(long)]
        out: Option<PathBuf>,
        #[arg(long, default_value_t = 10)]
        k: usize,
        /// Forward only the named query-embedding credentials, if present.
        #[arg(long)]
        online_query: bool,
        /// Generated synthetic corpus measured in this same evaluator invocation.
        #[arg(long)]
        synthetic_corpus: Option<PathBuf>,
    },
}

#[derive(Debug, Error)]
pub enum AppError {
    #[error("{0}")]
    Input(String),
    #[error(transparent)]
    Manifest(#[from] kio_eval::manifest::ManifestError),
    #[error(transparent)]
    Runner(#[from] kio_eval::runner::RunnerError),
    #[error(transparent)]
    Generator(#[from] kio_eval::generator::GeneratorError),
}

fn generate_corpus(out: PathBuf, force: bool) -> Result<ExitCode, AppError> {
    let summary = kio_eval::generator::generate_corpus(&out, force)?;
    println!("[ok] コーパス生成: {}", summary.output.display());
    println!(
        "     files={} anchors={} scopes={}",
        summary.file_count, summary.anchor_count, summary.scope_count
    );
    for (scope, count) in summary.per_scope {
        println!("       - {scope:12}: {count} files");
    }
    println!("     manifest: {}", summary.manifest_path.display());
    Ok(ExitCode::Success)
}

fn parse_scenario(value: &str) -> Result<String, String> {
    match value {
        "M3-1" | "M3-2" | "M3-3" => Ok(value.to_owned()),
        _ => Err("must be M3-1, M3-2, or M3-3".to_owned()),
    }
}

fn parse_recall(value: &str) -> Result<f64, String> {
    let value: f64 = value.parse().map_err(|_| "must be a number".to_owned())?;
    if value.is_finite() && (0.0..=1.0).contains(&value) {
        Ok(value)
    } else {
        Err("must be finite and in [0, 1]".to_owned())
    }
}

/// The hermetic fixture-only environment used by every evaluator subprocess.
///
/// Do not inherit a general ambient environment: credentials, agent sockets,
/// and adapter configuration are all evaluator inputs unless explicitly
/// excluded.  `PATH` is required for platform command helpers; the remaining
/// entries are fixed so output decoding and timestamps are deterministic.
fn device_env(device: &BoundDevice) -> Result<Vec<(OsString, OsString)>, AppError> {
    let path = env::var_os("PATH").unwrap_or_else(|| OsString::from("/usr/bin:/bin"));
    Ok(vec![
        (OsString::from("PATH"), path),
        (OsString::from("LANG"), OsString::from("C.UTF-8")),
        (OsString::from("LC_ALL"), OsString::from("C.UTF-8")),
        (OsString::from("TZ"), OsString::from("UTC")),
        (OsString::from("HOME"), device.home().as_os_str().to_owned()),
        (
            OsString::from("XDG_CONFIG_HOME"),
            device.config().as_os_str().to_owned(),
        ),
        (
            OsString::from("XDG_CACHE_HOME"),
            device.cache().as_os_str().to_owned(),
        ),
        (
            OsString::from("XDG_DATA_HOME"),
            device.data().as_os_str().to_owned(),
        ),
        (
            OsString::from("XDG_STATE_HOME"),
            device.state().as_os_str().to_owned(),
        ),
        (
            OsString::from("XDG_RUNTIME_DIR"),
            device.runtime().as_os_str().to_owned(),
        ),
    ])
}

fn bundled_eval_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../eval")
        .join(name)
}

fn output_is_within_input_root(output: &Path, root: &Path) -> Result<bool, AppError> {
    let absolute = if output.is_absolute() {
        output.to_path_buf()
    } else {
        env::current_dir()
            .map_err(|e| AppError::Input(format!("cannot resolve output path: {e}")))?
            .join(output)
    };
    let parent = absolute
        .parent()
        .ok_or_else(|| AppError::Input("output has no parent".into()))?;
    let parent = fs::canonicalize(parent)
        .map_err(|e| AppError::Input(format!("cannot canonicalize output parent: {e}")))?;
    let root = fs::canonicalize(root)
        .map_err(|e| AppError::Input(format!("cannot canonicalize synthetic corpus: {e}")))?;
    Ok(parent.starts_with(root))
}

fn scenario_name(value: Scenario) -> &'static str {
    match value {
        Scenario::M3_1 => "M3-1",
        Scenario::M3_2 => "M3-2",
        Scenario::M3_3 => "M3-3",
    }
}

fn expected_flags(query: &kio_eval::manifest::GoldenQuery) -> Vec<String> {
    let mut flags = query.flags.clone();
    if let Some(required) = query.scenario.required_flag() {
        if !flags.iter().any(|flag| flag == required) {
            flags.push(required.to_owned());
        }
    }
    flags
}

fn verify_logs(
    bin: &Path,
    corpus: &BoundCorpus,
    history: &kio_eval::manifest::HistoryManifest,
    environment: &[(OsString, OsString)],
) -> Vec<String> {
    let mut problems = Vec::new();
    for scope in SCOPES {
        let Some(bound_scope) = corpus.scope(scope) else {
            problems.push(format!("history log unavailable: {scope}"));
            continue;
        };
        let mut command = Command::new(bin);
        command
            .arg("--json")
            .arg("log")
            .env_clear()
            .envs(environment.iter().cloned());
        if bound_scope.configure_command_cwd(&mut command).is_err() {
            problems.push(format!("history log unavailable: {scope}"));
            continue;
        }
        let output = run_bounded_command(&mut command, BoundedProcessOptions::default());
        let Ok(output) = output else {
            problems.push(format!("history log unavailable: {scope}"));
            continue;
        };
        let response: Option<serde_json::Value> = serde_json::from_str(output.stdout.trim()).ok();
        let commits = response
            .as_ref()
            .and_then(|value| value.get("commits"))
            .and_then(serde_json::Value::as_array);
        let Some(commits) = commits else {
            problems.push(format!("history log unavailable: {scope}"));
            continue;
        };
        let messages = commits
            .iter()
            .map(|commit| commit.get("message").and_then(serde_json::Value::as_str))
            .collect::<Option<Vec<_>>>();
        let expected = &history.verified[scope];
        let expected_messages = expected
            .messages
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>();
        if !output.status.success()
            || commits.len() != expected.commit_count
            || messages.as_deref() != Some(expected_messages.as_slice())
        {
            problems.push(format!("history log is stale: {scope}"));
        }
    }
    problems
}

fn history_ref(history: &kio_eval::manifest::HistoryManifest) -> HistoryManifestRef {
    HistoryManifestRef {
        edited: history
            .edited
            .iter()
            .map(|entry| HistoryEntryRef {
                scope: entry.scope.clone(),
                file: entry.file.clone(),
                raw_sha256: entry.raw_sha256.clone(),
            })
            .collect(),
        renamed: history
            .renamed
            .iter()
            .map(|entry| RenameEntryRef {
                scope: entry.scope.clone(),
                old_file: entry.old_file.clone(),
                new_file: entry.new_file.clone(),
                raw_sha256: entry.raw_sha256.clone(),
            })
            .collect(),
        deleted: history
            .deleted
            .iter()
            .map(|entry| HistoryEntryRef {
                scope: entry.scope.clone(),
                file: entry.file.clone(),
                raw_sha256: entry.raw_sha256.clone(),
            })
            .collect(),
    }
}

fn read_bound_regular(scope: &BoundScope, name: &std::ffi::OsStr) -> Result<Vec<u8>, AppError> {
    let handle = scope
        .try_clone_handle()
        .map_err(|error| AppError::Input(error.to_string()))?;
    let mut options = cap_fs::OpenOptions::new();
    options
        .read(true)
        ._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let mut file = cap_fs::open(&handle, Path::new(name), &options)
        .map_err(|error| AppError::Input(error.to_string()))?;
    let metadata = file
        .metadata()
        .map_err(|error| AppError::Input(error.to_string()))?;
    if !metadata.is_file() || metadata.len() > MAX_RAW_OBJECT_BYTES {
        return Err(AppError::Input(format!(
            "unsafe or oversized corpus file: {}/{}",
            scope.name(),
            name.to_string_lossy()
        )));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.nlink() != 1 {
            return Err(AppError::Input(format!(
                "multiply-linked corpus file: {}/{}",
                scope.name(),
                name.to_string_lossy()
            )));
        }
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    file.by_ref()
        .take(MAX_RAW_OBJECT_BYTES.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| AppError::Input(error.to_string()))?;
    if bytes.len() as u64 > MAX_RAW_OBJECT_BYTES {
        return Err(AppError::Input(format!(
            "oversized corpus file: {}/{}",
            scope.name(),
            name.to_string_lossy()
        )));
    }
    Ok(bytes)
}

fn tree_fingerprint(corpus: &BoundCorpus) -> Result<Vec<(String, String, String)>, AppError> {
    let mut rows = Vec::new();
    for scope in corpus.scopes() {
        let handle = scope
            .try_clone_handle()
            .map_err(|error| AppError::Input(error.to_string()))?;
        let entries = cap_fs::read_base_dir(&handle)
            .map_err(|error| AppError::Input(format!("cannot list {}: {error}", scope.name())))?;
        let mut entries = entries
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| AppError::Input(format!("cannot list {}: {error}", scope.name())))?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            if entry.file_name() == ".kio"
                || !entry
                    .file_type()
                    .map_err(|error| AppError::Input(error.to_string()))?
                    .is_file()
            {
                continue;
            }
            let name = entry.file_name();
            let bytes = read_bound_regular(scope, &name)?;
            rows.push((
                scope.name().to_owned(),
                name.to_string_lossy().into_owned(),
                hash_bytes(&bytes),
            ));
        }
    }
    Ok(rows)
}

fn verify_restore(
    bin: &Path,
    corpus: &BoundCorpus,
    history: &kio_eval::manifest::HistoryManifest,
    records: &[ScoredRecord],
    environment: &[(OsString, OsString)],
) -> Vec<String> {
    let before = match tree_fingerprint(corpus) {
        Ok(value) => value,
        Err(error) => return vec![error.to_string()],
    };
    let mut pointers = HashMap::new();
    for record in records.iter().filter(|record| record.scenario == "M3-3") {
        for hit in record.response.results.iter().take(10) {
            if record.expected.contains(
                &kio_eval::RecallResult {
                    raw_hash: hit.pointer.raw_hash.clone(),
                    section_id: hit.pointer.section_id.clone(),
                    heading_path: hit.pointer.heading_path.clone(),
                    path_at_commit: hit.pointer.path_at_commit.clone(),
                }
                .key(),
            ) {
                pointers
                    .entry(hit.pointer.raw_hash.clone())
                    .or_insert_with(|| hit.pointer_value.clone());
            }
        }
    }
    let mut problems = Vec::new();
    for entry in &history.deleted {
        let raw = format!("sha256:{}", entry.raw_sha256);
        let Some(pointer) = pointers.get(&raw) else {
            problems.push(format!(
                "deleted result absent for restore: {}/{}",
                entry.scope, entry.file
            ));
            continue;
        };
        let destination = tempfile::tempdir();
        let Ok(destination) = destination else {
            problems.push("could not create restore destination".to_owned());
            continue;
        };
        let pointer = serde_json::to_string(pointer).expect("JSON value serializes");
        let Some(research) = corpus.scope("research") else {
            problems.push("research scope is unavailable for restore".to_owned());
            break;
        };
        let mut command = Command::new(bin);
        command
            .arg("--json")
            .arg("restore")
            .arg(pointer)
            .arg("--to")
            .arg(destination.path())
            .env_clear()
            .envs(environment.iter().cloned());
        if let Err(error) = research.configure_command_cwd(&mut command) {
            problems.push(format!(
                "restore failed for {}/{}: {error}",
                entry.scope, entry.file
            ));
            continue;
        }
        let output = run_bounded_command(&mut command, BoundedProcessOptions::default());
        let Ok(output) = output else {
            problems.push(format!(
                "restore failed for {}/{}: {}",
                entry.scope,
                entry.file,
                output.unwrap_err()
            ));
            continue;
        };
        if !output.status.success() {
            problems.push(format!(
                "restore failed for {}/{}: {}",
                entry.scope,
                entry.file,
                output.stderr.trim()
            ));
            continue;
        }
        let files = walk_regular_files(destination.path());
        if files.len() != 1 {
            problems.push(format!(
                "restore count mismatch for {}/{}",
                entry.scope, entry.file
            ));
            continue;
        }
        match read_bounded_regular_file(&files[0], MAX_RAW_OBJECT_BYTES)
            .map(|bytes| hash_bytes(&bytes))
        {
            Ok(actual) if actual == raw => {}
            _ => problems.push(format!(
                "restore hash mismatch for {}/{}",
                entry.scope, entry.file
            )),
        }
    }
    match tree_fingerprint(corpus) {
        Ok(after) if after == before => {}
        Ok(_) => problems.push("restore mutated the source corpus working tree".to_owned()),
        Err(error) => problems.push(error.to_string()),
    }
    problems
}

fn walk_regular_files(root: &Path) -> Vec<PathBuf> {
    let mut files = Vec::new();
    let Ok(entries) = fs::read_dir(root) else {
        return files;
    };
    for entry in entries.flatten() {
        if entry.file_type().is_ok_and(|kind| kind.is_file()) {
            files.push(entry.path());
        } else if entry.file_type().is_ok_and(|kind| kind.is_dir()) {
            files.extend(walk_regular_files(&entry.path()));
        }
    }
    files
}

pub fn run(args: Args) -> Result<ExitCode, AppError> {
    if let Some(command) = args.command.as_ref() {
        return match command {
            Commands::GenerateCorpus { out, force } => generate_corpus(out.clone(), *force),
            Commands::Benchmark { command } => match command {
                BenchmarkCommands::BaselineAttest {
                    golden,
                    fixture_root,
                    baseline_corpus,
                    out,
                } => {
                    let bytes = qhard::generate_baseline_attestation(BaselineAttestOptions {
                        golden: golden.clone(),
                        fixture_root: fixture_root.clone(),
                        baseline_corpus: baseline_corpus.clone(),
                    })
                    .map_err(|e| AppError::Input(e.to_string()))?;
                    qhard::write_baseline_attestation(out, fixture_root, baseline_corpus, &bytes)
                        .map_err(|e| AppError::Input(e.to_string()))?;
                    Ok(ExitCode::Success)
                }
                BenchmarkCommands::Baseline {
                    golden,
                    fixture_root,
                    baseline_corpus,
                    attestation,
                    bin,
                    mdfind,
                    rga,
                    online_query,
                    out,
                } => {
                    let report = qhard::run_baseline(BaselineOptions {
                        golden: golden.clone(),
                        fixture_root: fixture_root.clone(),
                        baseline_corpus: baseline_corpus.clone(),
                        attestation: Some(attestation.clone()),
                        bin: bin.clone(),
                        mdfind: mdfind.clone(),
                        rga: rga.clone(),
                        online_query: *online_query,
                    })
                    .map_err(|e| AppError::Input(e.to_string()))?;
                    let rendered = serde_json::to_vec_pretty(&report)
                        .map_err(|e| AppError::Input(e.to_string()))?;
                    if let Some(path) = out {
                        qhard::write_baseline_report(path, fixture_root, baseline_corpus, &report)
                            .map_err(|e| AppError::Input(e.to_string()))?;
                    } else {
                        println!("{}", String::from_utf8_lossy(&rendered));
                    }
                    Ok(if report.acceptance_passed() {
                        ExitCode::Success
                    } else {
                        ExitCode::Failure
                    })
                }
                BenchmarkCommands::Scale {
                    corpus,
                    manifest,
                    attestation,
                    bin,
                    out,
                    warmups,
                    samples,
                } => {
                    let report = scale::run(ScaleOptions {
                        corpus: corpus.clone(),
                        manifest: manifest.clone(),
                        attestation: attestation.clone(),
                        bin: bin.clone(),
                        warmups: *warmups,
                        samples: *samples,
                    })
                    .map_err(|error| AppError::Input(error.to_string()))?;
                    let rendered = serde_json::to_vec_pretty(&report).map_err(|error| {
                        AppError::Input(format!("cannot serialize scale report: {error}"))
                    })?;
                    if let Some(path) = out {
                        scale::write_report(path, corpus, &report)
                            .map_err(|error| AppError::Input(error.to_string()))?;
                    } else {
                        println!("{}", String::from_utf8_lossy(&rendered));
                        if report.acceptance_failed() {
                            let fallback = std::env::temp_dir()
                                .join(format!("kio-scale-failed-{}.json", std::process::id()));
                            scale::write_report(&fallback, corpus, &report)
                                .map_err(|error| AppError::Input(error.to_string()))?;
                            eprintln!("saved failed scale report: {}", fallback.display());
                        }
                    }
                    Ok(if report.acceptance_failed() {
                        ExitCode::Failure
                    } else {
                        ExitCode::Success
                    })
                }
                BenchmarkCommands::Qhard {
                    golden,
                    fixture_root,
                    tree,
                    env_name,
                    attestation,
                    bin,
                    out,
                    k,
                    online_query,
                    synthetic_corpus,
                } => {
                    // A combined acceptance run must use one immutable binary
                    // for both lanes; normal evaluation otherwise resolves
                    // its public `--bin` path immediately before each search.
                    let combined_binary = synthetic_corpus
                        .is_some()
                        .then(|| qhard::snapshot_binary(bin))
                        .transpose()
                        .map_err(|error| AppError::Input(error.to_string()))?;
                    let measurement_bin = combined_binary
                        .as_ref()
                        .map(|(_, path)| path)
                        .unwrap_or(bin);
                    let report = qhard::run(QhardOptions {
                        golden: golden.clone(),
                        fixture_root: fixture_root.clone(),
                        tree: tree.clone(),
                        env_name: env_name.clone(),
                        attestation: attestation.clone(),
                        bin: measurement_bin.to_path_buf(),
                        k: *k,
                        online_query: *online_query,
                    })
                    .map_err(|error| AppError::Input(error.to_string()))?;
                    let mut report = report;
                    let mut synthetic_input_root = None;
                    if let Some(corpus) = synthetic_corpus {
                        synthetic_input_root = Some(corpus.clone());
                        let synthetic_snapshot = qhard::snapshot_regular_tree(corpus)
                            .map_err(|error| AppError::Input(error.to_string()))?;
                        let temporary = tempfile::tempdir().map_err(|error| {
                            AppError::Input(format!(
                                "cannot create combined measurement workspace: {error}"
                            ))
                        })?;
                        let frozen_golden = bundled_eval_path("golden-queries.jsonl");
                        let golden_bytes = fs::read(&frozen_golden).map_err(|error| {
                            AppError::Input(format!("cannot read frozen synthetic golden: {error}"))
                        })?;
                        if golden_bytes.len() > 64 * 1024
                            || kio_core::cas::hash_bytes(&golden_bytes)
                                != qhard::FROZEN_SYNTHETIC_M3_1_GOLDEN_SHA256
                        {
                            return Err(AppError::Input(
                                "synthetic M3-1 golden differs from the frozen contract".into(),
                            ));
                        }
                        let synthetic_golden = temporary.path().join("golden-queries.jsonl");
                        fs::write(&synthetic_golden, golden_bytes).map_err(|error| {
                            AppError::Input(format!(
                                "cannot snapshot frozen synthetic golden: {error}"
                            ))
                        })?;
                        let synthetic_out = temporary.path().join("synthetic-results.json");
                        let synthetic_report = temporary.path().join("synthetic-report.md");
                        let outcome = run(Args {
                            command: None,
                            golden: Some(synthetic_golden.clone()),
                            corpus: Some(synthetic_snapshot.path().to_path_buf()),
                            corpus_manifest: None,
                            history_manifest: None,
                            bin: measurement_bin.to_path_buf(),
                            out: Some(synthetic_out.clone()),
                            report: Some(synthetic_report),
                            scenario: vec!["M3-1".to_owned()],
                            min_recall: 0.8,
                            dry_run: false,
                        })?;
                        if outcome != ExitCode::Success {
                            return Err(AppError::Input(
                                "same-invocation synthetic M3-1 measurement did not pass".into(),
                            ));
                        }
                        synthetic_snapshot
                            .verify_source_unchanged()
                            .map_err(|error| AppError::Input(error.to_string()))?;
                        let results: kio_eval::runner::EvaluationResults =
                            serde_json::from_slice(&fs::read(&synthetic_out).map_err(|error| {
                                AppError::Input(format!(
                                    "cannot read same-invocation synthetic result: {error}"
                                ))
                            })?)
                            .map_err(|error| {
                                AppError::Input(format!(
                                    "invalid same-invocation synthetic result: {error}"
                                ))
                            })?;
                        let m31 = results.scenarios.get("M3-1").ok_or_else(|| {
                            AppError::Input("same-invocation result omitted M3-1".into())
                        })?;
                        if m31.n_queries != 18 || m31.n_scored != 18 {
                            return Err(AppError::Input(
                                "same-invocation synthetic M3-1 did not measure exactly 18 queries"
                                    .into(),
                            ));
                        }
                        let hits = results
                            .queries
                            .iter()
                            .filter(|row| row.scenario == "M3-1" && row.recall_at_10 == Some(1.0))
                            .count();
                        report
                            .combine_synthetic_m3_1(&synthetic_golden, hits, 18)
                            .map_err(|error| AppError::Input(error.to_string()))?;
                    }
                    let rendered = serde_json::to_vec_pretty(&report).map_err(|error| {
                        AppError::Input(format!("cannot serialize Q_hard report: {error}"))
                    })?;
                    if let Some(path) = out {
                        if let Some(synthetic_root) = &synthetic_input_root {
                            if output_is_within_input_root(path, synthetic_root)? {
                                return Err(AppError::Input(
                                    "Q_hard report must be outside synthetic corpus input".into(),
                                ));
                            }
                        }
                        qhard::write_report(path, fixture_root, &report)
                            .map_err(|error| AppError::Input(error.to_string()))?;
                    } else {
                        println!("{}", String::from_utf8_lossy(&rendered));
                    }
                    // Q_hard-only reports are useful evidence, but they are
                    // explicitly not the combined 26-query M3-1 acceptance
                    // gate.  Never turn an ineligible measurement into a
                    // successful acceptance exit status.
                    Ok(if report.acceptance_passed() {
                        ExitCode::Success
                    } else {
                        ExitCode::Failure
                    })
                }
            },
        };
    }
    let golden = args
        .golden
        .unwrap_or_else(|| bundled_eval_path("golden-queries.jsonl"));
    let out = args
        .out
        .unwrap_or_else(|| bundled_eval_path("results.json"));
    let report = args
        .report
        .unwrap_or_else(|| bundled_eval_path("report.md"));
    let mut queries = load_golden_queries(&golden)?;
    if !args.scenario.is_empty() {
        queries.retain(|query| {
            args.scenario
                .iter()
                .any(|scenario| scenario == scenario_name(query.scenario))
        });
        if queries.is_empty() {
            return Err(AppError::Input(
                "--scenario に該当するクエリが無い".to_owned(),
            ));
        }
    }
    let corpus_manifest = args
        .corpus_manifest
        .clone()
        .or_else(|| {
            args.corpus
                .as_ref()
                .map(|path| path.join("corpus-manifest.json"))
        })
        .ok_or_else(|| {
            AppError::Input("--corpus か --corpus-manifest を指定すること".to_owned())
        })?;
    let history_manifest = args
        .history_manifest
        .clone()
        .or_else(|| {
            args.corpus
                .as_ref()
                .map(|path| path.join("history-manifest.json"))
        })
        .ok_or_else(|| {
            AppError::Input("--corpus か --history-manifest を指定すること".to_owned())
        })?;
    let corpus = load_corpus_manifest(&corpus_manifest)?;
    let history = load_history_manifest(&history_manifest, &corpus)?;
    let model = CorpusModel::new(&corpus, &history);
    let resolver = Resolver::new(&corpus, &history);
    let active = ["M3-1", "M3-2", "M3-3"]
        .iter()
        .filter(|scenario| {
            queries
                .iter()
                .any(|query| scenario_name(query.scenario) == **scenario)
        })
        .map(|value| (*value).to_owned())
        .collect::<Vec<_>>();
    let problems = queries
        .iter()
        .flat_map(|query| validate_query(query, &model, &resolver))
        .collect::<Vec<_>>();
    if args.dry_run {
        return Ok(if problems.is_empty() {
            ExitCode::Success
        } else {
            ExitCode::Failure
        });
    }
    let corpus_dir = args
        .corpus
        .as_ref()
        .ok_or_else(|| AppError::Input("実行モードには --corpus が必要".to_owned()))?
        .canonicalize()
        .map_err(|error| AppError::Input(format!("corpus を開けない: {error}")))?;
    if !corpus_dir.is_dir() {
        return Err(AppError::Input(format!(
            "corpus がディレクトリではない: {}",
            corpus_dir.display()
        )));
    }
    let bound_corpus = BoundCorpus::bind(&corpus_dir, &corpus.scopes)
        .map_err(|error| AppError::Input(error.to_string()))?;
    let bin = args
        .bin
        .canonicalize()
        .map_err(|_| AppError::Input(format!("kio バイナリ不在: {}", args.bin.display())))?;
    if !bin.is_file() {
        return Err(AppError::Input(format!(
            "kio バイナリ不在: {}",
            bin.display()
        )));
    }
    let environment = device_env(bound_corpus.device())?;
    let log_problems = verify_logs(&bin, &bound_corpus, &history, &environment);
    if !log_problems.is_empty() {
        return Err(AppError::Input(log_problems.join("; ")));
    }
    let resolved = queries
        .iter()
        .map(|query| {
            let (expected, _) = resolver.resolve_expected(&query.expected);
            let problems = validate_query(query, &model, &resolver);
            ResolvedQuery {
                scenario: scenario_name(query.scenario).to_owned(),
                query: query.query.clone(),
                expected,
                resolution_error: (!problems.is_empty()).then(|| problems.join("; ")),
            }
        })
        .collect::<Vec<_>>();
    let flags = queries.iter().map(expected_flags).collect::<Vec<_>>();
    let mut next = 0usize;
    let mut attestation_failures = 0usize;
    let mut attestor = active
        .iter()
        .any(|scenario| scenario == "M3-2")
        .then(|| PointerAttestor::from_bound_corpus(&bound_corpus))
        .transpose()
        .map_err(|error| AppError::Input(error.to_string()))?;
    let (mut results, records) = evaluate_queries_with_validator(
        &resolved,
        args.min_recall,
        |query| {
            let flags = flags.get(next).ok_or_else(|| {
                kio_eval::runner::RunnerError::Input("query/flags mismatch".to_owned())
            })?;
            next += 1;
            let research = bound_corpus.scope("research").ok_or_else(|| {
                kio_eval::runner::RunnerError::Input("research scope is unavailable".to_owned())
            })?;
            let mut command = Command::new(&bin);
            command
                .arg("--json")
                .arg("search")
                .arg(&query.query)
                .arg("--all-scopes")
                .args(flags)
                .env_clear()
                .envs(environment.iter().cloned());
            research
                .configure_command_cwd(&mut command)
                .map_err(|error| kio_eval::runner::RunnerError::Input(error.to_string()))?;
            let output = run_bounded_command(&mut command, BoundedProcessOptions::default())?;
            Ok(kio_eval::runner::SearchOutcome {
                returncode: output.status.code().unwrap_or(-1),
                stdout: output.stdout,
                stderr: output.stderr,
                duration_ms: output.duration.as_secs_f64() * 1_000.0,
            })
        },
        |query, response| {
            if query.scenario != "M3-2" {
                return Ok(None);
            }
            let attestor = attestor.as_mut().expect("M3-2 created an attestor");
            let mut problems = Vec::new();
            let mut attested = 0usize;
            for (index, hit) in response
                .results
                .iter()
                .take(MAX_POINTER_ATTESTATIONS_PER_QUERY)
                .enumerate()
            {
                match attestor.attest(&hit.pointer_value) {
                    Ok(()) => attested += 1,
                    Err(error) => problems.push(format!(
                        "result[{index}] pointer attestation failed: {error}"
                    )),
                }
            }
            if problems.is_empty() {
                Ok(Some(attested))
            } else {
                attestation_failures += 1;
                Err(problems.join("; "))
            }
        },
    )?;
    let mut coverage = assess_history_coverage(&records, &history_ref(&history));
    if active.iter().any(|scenario| scenario == "M3-2") {
        coverage.pointer_attested = results.counts.n_pointer_attested;
        coverage.pointer_attestation_failures = attestation_failures;
        coverage.passes_pointer_attestation = attestation_failures == 0;
    }
    if active.iter().any(|scenario| scenario == "M3-3") && coverage.passes_m3_3 {
        coverage.set_restore_problems(verify_restore(
            &bin,
            &bound_corpus,
            &history,
            &records,
            &environment,
        ));
    }
    results.history_coverage = coverage;
    write_results(&out, &results)?;
    write_report(&report, &results, &active)?;
    Ok(match final_exit_code(&results, &active) {
        0 => ExitCode::Success,
        2 => ExitCode::InvalidUsage,
        _ => ExitCode::Failure,
    })
}

#[cfg(test)]
mod tests {
    use std::{ffi::OsString, fs, path::Path};

    use kio_eval::boundary::BoundCorpus;

    use super::{
        bundled_eval_path, device_env, output_is_within_input_root, parse_recall, parse_scenario,
    };

    #[test]
    fn cli_value_parsers_are_strict() {
        assert_eq!(parse_scenario("M3-2").unwrap(), "M3-2");
        assert!(parse_scenario("m3-2").is_err());
        assert_eq!(parse_recall("0").unwrap(), 0.0);
        assert!(parse_recall("NaN").is_err());
        assert!(parse_recall("1.01").is_err());
    }

    #[test]
    fn bundled_artifacts_do_not_depend_on_the_current_directory() {
        let golden = bundled_eval_path("golden-queries.jsonl");
        assert!(golden.ends_with(Path::new("eval/golden-queries.jsonl")));
        assert!(golden.is_absolute());
    }

    #[test]
    fn output_inside_synthetic_input_is_rejected() {
        let corpus = tempfile::tempdir().unwrap();
        assert!(
            output_is_within_input_root(&corpus.path().join("report.json"), corpus.path()).unwrap()
        );
    }

    #[test]
    fn device_environment_is_an_explicit_allowlist() {
        let corpus = tempfile::tempdir().unwrap();
        fs::create_dir(corpus.path().join("research")).unwrap();
        fs::create_dir(corpus.path().join("research/.kio")).unwrap();
        let bound = BoundCorpus::bind(corpus.path(), &["research".to_owned()]).unwrap();
        let values = device_env(bound.device()).unwrap();
        assert!(values.iter().any(|(key, _)| key == "PATH"));
        assert!(values
            .iter()
            .any(|(key, value)| key == "TZ" && value == "UTC"));
        assert!(values.iter().any(|(key, value)| {
            key == "HOME" && value == &OsString::from(bound.device().home())
        }));
        assert!(!values.iter().any(|(key, _)| key == "SSH_AUTH_SOCK"));
        assert!(!values.iter().any(|(key, _)| key == "GEMINI_API_KEY"));
    }
}
