use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{IsTerminal, Write};
use std::path::{Path, PathBuf};
use std::process;

use clap::{Args, Parser, Subcommand};
use kcs_adapter::deterministic::{deterministic_prepare_profile_value, DeterministicAdapter};
use kcs_adapter::identity::tool_profile_hash;
use kcs_adapter::mistral_ocr::{
    EnvMistralOcrClient, MistralOcrClient, MistralOcrMarkdownizeAdapter, OcrImage, OcrPage,
    OcrResponse,
};
use kcs_adapter::tool_lock::{load_tool_lock, validate_tools_toml};
use kcs_adapter::traits::MarkdownizeAdapter;
use kcs_adapter::types::{
    AdapterKind, AdapterProfile, ExecutionMode, MarkdownUnit,
    MarkdownizeMode as AdapterMarkdownizeMode, MarkdownizeRequest, PreparedUnitHint,
    PreviousMarkdownizeContext, RawInput, UnitKind,
};
use kcs_core::dag::NormalizeRef;
use kcs_core::scope::{
    append_error_log, append_event_log, new_ulid, now_utc_seconds, InspectedObject, Repository,
};
use kcs_core::{ExitCode, KcsError, Result};
use kcs_pipeline::budget::{
    estimate_local_baseline_cost, evaluate_budget_with_caps, read_budget_policy, utc_month,
    BudgetCapKind, BudgetCaps, BudgetEstimate, CostLedger, MonthlyCostLedgerEntry,
};
use kcs_pipeline::markdownize::{
    choose_markdownize_mode, persist_normalized_instance, validate_markdownize_response,
    IncrementalHints, IncrementalModeInput, MarkdownizeMode, NormalizedInstanceManifest,
    NormalizedUnitManifestEntry, NormalizedUnitObject, UnitStatus,
};
use kcs_pipeline::prepare::{
    hash_bytes, map_units, pdf_text_pages, prepare_units, unit_ref, PrepareStageRequest,
    PreparedUnit, UnitFingerprint, UnitType,
};
use kcs_pipeline::scan::{build_scan_preview, ScanCandidate, ScanPreview, ScanPreviewRequest};
use kcs_pipeline::task::{retry_policy, task_status_from_unit_counts, RetryErrorKind};
use kcs_pipeline::task::{TaskDescriptor, TaskStatus, TaskStore, TaskType};
use serde_json::{json, Value};

// clap のパースエラーは exit code 2 で終了する。これは docs/06-cli-spec.md §7 の
// invalid usage (= 2) と一致するため、そのまま採用する。
#[derive(Debug, Parser)]
#[command(name = "kcs", version, about = "Local-first knowledge archive CLI")]
struct Cli {
    /// Emit machine-readable JSON (docs/06-cli-spec.md §4).
    #[arg(long, global = true)]
    json: bool,

    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Create a .kcs directory for the current folder.
    Init(InitArgs),
    /// Show file state, pending tasks, and budget.
    Status,
    /// Create a snapshot. The `commit` alias maps here (docs/06-cli-spec.md §1).
    #[command(alias = "commit")]
    Snapshot(SnapshotArgs),
    /// Show snapshot history.
    Log(LogArgs),
    /// Compare two snapshots.
    Diff(DiffArgs),
    /// Inspect an object by hash.
    Inspect(InspectArgs),
    /// Create or show a tag.
    Tag(TagArgs),
    /// Ingest and normalize files in the current scope.
    Index(IndexArgs),
    /// Resume or retry batch tasks.
    Batch(BatchArgs),
    /// Step 4 command placeholder.
    Repair(UnsupportedArgs),
    /// Step 3 command placeholder.
    Search(UnsupportedArgs),
    /// Step 3 command placeholder.
    Open(UnsupportedArgs),
    /// Step 3 command placeholder.
    View(UnsupportedArgs),
    /// Step 4 command placeholder.
    Restore(UnsupportedArgs),
    /// Phase 4+ command placeholder.
    Gc(UnsupportedArgs),
    /// Step 4 command placeholder.
    Purge(UnsupportedArgs),
    /// Step 3 command placeholder.
    Reindex(UnsupportedArgs),
    /// Phase 4+ command placeholder.
    Move(UnsupportedArgs),
    /// Step 4 command placeholder.
    Evidence(UnsupportedArgs),
}

#[derive(Debug, Args)]
struct InitArgs {
    path: Option<PathBuf>,
}

#[derive(Debug, Args)]
struct SnapshotArgs {
    /// 正規形 `kcs snapshot create` の受け口 (省略可)。
    #[arg(value_parser = ["create"])]
    action: Option<String>,

    #[arg(short, long)]
    message: Option<String>,
}

#[derive(Debug, Args)]
struct LogArgs {
    #[arg(long)]
    at: Option<String>,
    #[arg(long)]
    since: Option<String>,
}

#[derive(Debug, Args)]
struct DiffArgs {
    a: String,
    b: String,
}

#[derive(Debug, Args)]
struct InspectArgs {
    hash: String,
}

#[derive(Debug, Args)]
struct TagArgs {
    name: String,
    commit: Option<String>,
}

#[derive(Debug, Args)]
struct IndexArgs {
    #[arg(long)]
    preview: bool,
    #[arg(long)]
    approve: bool,
    #[arg(long)]
    yes: bool,
    #[arg(long)]
    online: bool,
    #[arg(long)]
    offline: bool,
    #[arg(long)]
    revoke_network: bool,
}

#[derive(Debug, Args)]
struct BatchArgs {
    #[command(subcommand)]
    command: Option<BatchCommand>,
}

#[derive(Debug, Subcommand)]
enum BatchCommand {
    Resume(ResumeArgs),
    Retry,
}

#[derive(Debug, Args)]
struct ResumeArgs {
    #[arg(long)]
    override_budget: bool,
}

#[derive(Debug, Args)]
struct UnsupportedArgs {
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    args: Vec<String>,
}

fn main() {
    let cli = Cli::parse();
    let json = cli.json || command_captured_json_flag(&cli.command);
    let exit_code = match run(cli) {
        Ok(output) => {
            print_output(output, json);
            ExitCode::Success
        }
        Err(error) => {
            let _ = append_error_log(&error);
            print_error(&error, json);
            error.exit_code()
        }
    };
    process::exit(exit_code.code());
}

fn command_captured_json_flag(command: &Command) -> bool {
    match command {
        Command::Repair(args)
        | Command::Search(args)
        | Command::Open(args)
        | Command::View(args)
        | Command::Restore(args)
        | Command::Gc(args)
        | Command::Purge(args)
        | Command::Reindex(args)
        | Command::Move(args)
        | Command::Evidence(args) => args.args.iter().any(|arg| arg == "--json"),
        Command::Index(_) | Command::Batch(_) => false,
        Command::Init(_)
        | Command::Status
        | Command::Snapshot(_)
        | Command::Log(_)
        | Command::Diff(_)
        | Command::Inspect(_)
        | Command::Tag(_) => false,
    }
}

fn run(cli: Cli) -> Result<Value> {
    validate_user_tools_config()?;
    match cli.command {
        Command::Init(args) => {
            let path = args.path.unwrap_or_else(|| PathBuf::from("."));
            let existed = path.join(".kcs").exists();
            let repo = Repository::init(&path)?;
            Ok(json!({
                "status": if existed { "already initialized" } else { "initialized" },
                "path": repo.root(),
                "kcs_path": repo.kcs_dir(),
            }))
        }
        Command::Status => {
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            let task_store = TaskStore::new(repo.kcs_dir());
            Ok(json!({
                "scope_path": repo.kcs_dir(),
                "files": repo.status()?,
                "tasks": task_store.all().map_err(pipeline_to_kcs)?,
                "quarantine": read_quarantine_records(&repo)?,
                "budget": budget_status_json(&repo)?,
            }))
        }
        Command::Snapshot(args) => {
            let _action = args.action;
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            let outcome = repo.snapshot(args.message.as_deref(), None)?;
            if let Some(commit_hash) = &outcome.commit_hash {
                append_event_log(
                    "KCS-I-COMMIT-CREATED-001",
                    "commit created",
                    json!({
                        "commit_hash": commit_hash,
                        "tree_hash": outcome.tree_hash,
                    }),
                )?;
            }
            Ok(json!({
                "status": if outcome.noop { "noop" } else { "created" },
                "message": outcome.message,
                "tree_hash": outcome.tree_hash,
                "commit_hash": outcome.commit_hash,
                "commit": outcome.commit,
                "stats": {
                    "files_added": outcome.stats.files_added,
                    "files_modified": outcome.stats.files_modified,
                    "files_deleted": outcome.stats.files_deleted,
                }
            }))
        }
        Command::Log(args) => {
            if args.at.is_some() || args.since.is_some() {
                return Err(KcsError::not_implemented("log --at/--since"));
            }
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            Ok(json!({ "commits": repo.log()? }))
        }
        Command::Diff(args) => {
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            Ok(json!({ "changes": repo.diff(&args.a, &args.b)? }))
        }
        Command::Inspect(args) => {
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            match repo.inspect(&args.hash)? {
                InspectedObject::Tree(tree) => {
                    serde_json::to_value(tree).map_err(|err| KcsError::schema(err.to_string()))
                }
                InspectedObject::Commit(commit) => {
                    serde_json::to_value(commit).map_err(|err| KcsError::schema(err.to_string()))
                }
                InspectedObject::Raw {
                    raw_hash,
                    size_bytes,
                } => Ok(json!({
                    "object_type": "raw",
                    "raw_hash": raw_hash,
                    "size_bytes": size_bytes,
                })),
            }
        }
        Command::Tag(args) => {
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            let commit_hash = repo.tag(&args.name, args.commit.as_deref())?;
            Ok(json!({
                "tag": args.name,
                "commit_hash": commit_hash,
                "path": repo.kcs_dir().join("refs/tags").join(args.name),
            }))
        }
        Command::Index(args) => run_index(args),
        Command::Batch(args) => run_batch(args),
        Command::Repair(_)
        | Command::Search(_)
        | Command::Open(_)
        | Command::View(_)
        | Command::Restore(_)
        | Command::Gc(_)
        | Command::Purge(_)
        | Command::Reindex(_)
        | Command::Move(_)
        | Command::Evidence(_) => Err(KcsError::not_implemented("command")),
    }
}

fn run_index(args: IndexArgs) -> Result<Value> {
    if args.online && args.offline {
        return Err(KcsError::invalid_usage(
            "--online and --offline are mutually exclusive",
        ));
    }
    let repo = Repository::open_current()?;
    validate_repo_tool_lock(&repo)?;
    if args.revoke_network {
        write_network_revoke_record(&repo)?;
        return Ok(json!({ "status": "network revoked" }));
    }
    let preview = build_scan_preview(ScanPreviewRequest {
        scope_path: repo.root().display().to_string(),
        include_raw_hashes: !args.preview,
        require_network_approval: !args.offline,
    })
    .map_err(pipeline_to_kcs)?;

    if args.preview {
        return Ok(index_preview_json(repo.root(), &preview));
    }

    let approved = approval_exists(&repo)?;
    if !approved && !args.approve && !args.yes {
        if !std::io::stdin().is_terminal() {
            return Err(KcsError::invalid_usage(
                "index requires --preview, --approve, or --yes in non-interactive mode",
            ));
        }
        return Err(KcsError::invalid_usage(
            "interactive approval is unavailable in this build; use --approve or --yes",
        ));
    }

    if args.approve || args.yes {
        write_approval_record(
            &repo,
            &preview,
            if args.approve {
                "approve"
            } else if args.yes {
                "yes"
            } else {
                "interactive"
            },
            args.approve,
        )?;
    }
    record_quarantine_candidates(&repo, &preview)?;

    materialize_tool_lock(&repo)?;
    let index_result = run_index_pipeline(&repo, &preview, &args)?;
    let excluded = preview
        .candidates
        .iter()
        .filter(|candidate| candidate.ignored)
        .map(|candidate| candidate.input_path.clone())
        .collect::<BTreeSet<_>>();
    let outcome = repo.auto_snapshot_with_normalize(
        Some("kcs index auto snapshot"),
        None,
        &excluded,
        &index_result.normalize_by_path,
    )?;
    if let Some(commit_hash) = &outcome.commit_hash {
        append_event_log(
            "KCS-I-COMMIT-CREATED-001",
            "auto commit created",
            json!({
                "commit_hash": commit_hash,
                "tree_hash": outcome.tree_hash,
                "commit_type": "auto",
            }),
        )?;
    }
    let output = json!({
        "status": if outcome.noop { "noop" } else { "indexed" },
        "approval_method": if args.approve { "approve" } else if args.yes { "yes" } else { "existing" },
        "network_allowed": index_result.network_allowed,
        "network_opt_in": persistent_network_allowed(&repo)?,
        "pending_online_tasks": index_result.pending_online_tasks,
        "paused_tasks": index_result.paused_tasks,
        "failed_files": index_result.failed_files,
        "normalized_files": index_result.normalized_files,
        "pending_files": index_result.pending_files,
        "tree_hash": outcome.tree_hash,
        "commit_hash": outcome.commit_hash,
        "commit": outcome.commit,
    });
    if index_result.failed_files > 0 {
        return Err(KcsError::new(
            "KCS-E-INDEX-PARTIAL-001",
            "index completed with failed candidates",
            json!({
                "failed_files": index_result.failed_files,
                "output": output.clone(),
            }),
            ExitCode::PartialFailure,
        ));
    }
    Ok(output)
}

fn run_batch(args: BatchArgs) -> Result<Value> {
    let repo = Repository::open_current()?;
    let store = TaskStore::new(repo.kcs_dir());
    match args.command {
        Some(BatchCommand::Resume(resume)) => {
            let changed = store
                .update_matching(|task| {
                    if task.status == TaskStatus::Paused
                        && (resume.override_budget
                            || task.fallback_reason.as_deref() != Some("budget_exceeded"))
                    {
                        task.status = TaskStatus::Pending;
                        task.fallback_reason = None;
                        true
                    } else {
                        false
                    }
                })
                .map_err(pipeline_to_kcs)?;
            let executed = execute_pending_tasks(&repo, &store)?;
            Ok(json!({
                "status": "resumed",
                "override_budget": resume.override_budget,
                "tasks_updated": changed,
                "tasks_executed": executed,
            }))
        }
        Some(BatchCommand::Retry) => {
            let changed = store
                .update_matching(|task| {
                    if task.status == TaskStatus::Failed
                        && task_retry_allowed(task)
                        && task_retry_due(task)
                    {
                        task.status = TaskStatus::Pending;
                        task.next_retry_at = None;
                        true
                    } else {
                        false
                    }
                })
                .map_err(pipeline_to_kcs)?;
            let executed = execute_pending_tasks(&repo, &store)?;
            Ok(
                json!({ "status": "retry scheduled", "tasks_updated": changed, "tasks_executed": executed }),
            )
        }
        None => Err(KcsError::not_implemented("batch command")),
    }
}

fn execute_pending_tasks(repo: &Repository, store: &TaskStore) -> Result<usize> {
    if !persistent_network_allowed(repo)? {
        return Ok(0);
    }
    let budget_caps =
        read_budget_policy(user_config_toml_path(), repo.kcs_dir().join("config.toml"))
            .map_err(pipeline_to_kcs)?;
    let cost_ledger = CostLedger::new(cost_ledger_path());
    let month = utc_month(&now_utc_seconds());
    let scope_id = repo.scope_id_for_adapter();
    let tasks = store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.status == TaskStatus::Pending
                && task.task_type == TaskType::Markdownize
                && task.output_ref == "online:mistral_ocr_markdownize"
                // Honor an unelapsed retry backoff even for a Pending task
                // (Step2c I2); `batch retry` already gates on this, so this is
                // a defensive belt-and-braces guard.
                && task_retry_due(task)
        })
        .collect::<Vec<_>>();
    let mut executed = 0usize;
    for task in tasks {
        let task_id = task.task_id.clone();
        let file_size = repo
            .root()
            .join(&task.input_path)
            .metadata()
            .map(|metadata| metadata.len())
            .unwrap_or(0);
        let estimate = BudgetEstimate {
            scope_id: scope_id.clone(),
            task_type: TaskType::Markdownize,
            estimated_usd: estimate_online_markdownize_cost(file_size),
            adapter_id: Some("mistral_ocr_markdownize".to_owned()),
        };
        let (device_remaining, folder_remaining) = budget_remaining_for_adapter(
            &cost_ledger,
            &budget_caps,
            &month,
            &scope_id,
            adapter_kind_for_budget(estimate.adapter_id.as_deref()),
        )?;
        let budget =
            evaluate_budget_with_caps(&estimate, device_remaining, folder_remaining, false);
        if !budget.allowed {
            store
                .update_matching(|candidate| {
                    if candidate.task_id == task_id {
                        candidate.status = TaskStatus::Paused;
                        candidate.fallback_reason = Some("budget_exceeded".to_owned());
                        true
                    } else {
                        false
                    }
                })
                .map_err(pipeline_to_kcs)?;
            continue;
        }
        store
            .update_matching(|candidate| {
                if candidate.task_id == task_id {
                    candidate.status = TaskStatus::Running;
                    candidate.heartbeat_at = Some(now_utc_seconds());
                    true
                } else {
                    false
                }
            })
            .map_err(pipeline_to_kcs)?;
        match execute_online_markdownize_task(repo, &task) {
            Ok(outcome) => {
                cost_ledger
                    .append_monthly(&MonthlyCostLedgerEntry {
                        month: month.clone(),
                        scope_id: scope_id.clone(),
                        adapter_kind: outcome.adapter_kind.clone(),
                        usd: outcome.cost_usd,
                    })
                    .map_err(pipeline_to_kcs)?;
                store
                    .update_matching(|candidate| {
                        if candidate.task_id == task_id {
                            candidate.status = outcome.status;
                            candidate.output_ref = outcome.output_ref.clone();
                            candidate.fallback_reason = Some("online_adapter_done".to_owned());
                            candidate.heartbeat_at = None;
                            true
                        } else {
                            false
                        }
                    })
                    .map_err(pipeline_to_kcs)?;
                executed += 1;
            }
            Err(error) => {
                let policy = retry_policy(error.retry_kind);
                let attempts_after = task.attempts.saturating_add(1);
                let next_retry_at = (policy.retryable
                    && policy
                        .max_attempts
                        .map(|max| attempts_after < max)
                        .unwrap_or(true))
                .then(|| scheduled_retry_at(&now_utc_seconds(), &policy.backoff, attempts_after));
                let reason = retry_reason(error.retry_kind).to_owned();
                store
                    .update_matching(|candidate| {
                        if candidate.task_id == task_id {
                            candidate.status = TaskStatus::Failed;
                            candidate.fallback_reason = Some(reason.clone());
                            candidate.heartbeat_at = None;
                            candidate.attempts = candidate.attempts.saturating_add(1);
                            candidate.next_retry_at = next_retry_at.clone();
                            true
                        } else {
                            false
                        }
                    })
                    .map_err(pipeline_to_kcs)?;
            }
        }
    }
    Ok(executed)
}

fn persistent_network_allowed(repo: &Repository) -> Result<bool> {
    if network_revoked(repo)? {
        return Ok(false);
    }
    if read_allow_network_config(&repo.kcs_dir().join("config.toml"))? == Some(true)
        || read_allow_network_config(&user_config_toml_path())? == Some(true)
    {
        return Ok(true);
    }
    let path = repo.kcs_dir().join("approvals.jsonl");
    let Ok(text) = fs::read_to_string(&path) else {
        return Ok(false);
    };
    Ok(text
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .any(|value| {
            value.get("tool_id").and_then(Value::as_str) == Some("mistral_ocr_markdownize")
                && value.get("execution_mode").and_then(Value::as_str) == Some("online_api")
                && value.get("network_opt_in").and_then(Value::as_bool) == Some(true)
        }))
}

#[derive(Debug, Clone)]
struct OnlineExecutionOutcome {
    output_ref: String,
    status: TaskStatus,
    cost_usd: f64,
    adapter_kind: String,
}

#[derive(Debug, Clone)]
struct TaskExecutionFailure {
    retry_kind: RetryErrorKind,
}

fn execute_online_markdownize_task(
    repo: &Repository,
    task: &TaskDescriptor,
) -> std::result::Result<OnlineExecutionOutcome, TaskExecutionFailure> {
    let path = repo.root().join(&task.input_path);
    let media_type = media_type_for_cli_path(&path).to_owned();
    let prepare_profile_hash = tool_profile_hash(&deterministic_prepare_profile_value())
        .map_err(task_failure_from_adapter)?;
    let prepare = prepare_units(PrepareStageRequest {
        raw_hash: task.input_hash.clone(),
        media_type: media_type.clone(),
        input_path: path.display().to_string(),
        tool_profile_hash: prepare_profile_hash,
    })
    .map_err(|_| TaskExecutionFailure {
        retry_kind: RetryErrorKind::InvalidInput,
    })?;
    if prepare.prepared_units.is_empty() {
        return Err(TaskExecutionFailure {
            retry_kind: RetryErrorKind::InvalidInput,
        });
    }
    let (profile, response) =
        run_mistral_adapter(repo, &task.input_hash, &path, &media_type, &prepare)?;
    let hints = all_changed_hints(&prepare.prepared_units);
    let strict_valid =
        validate_markdownize_response(&response, &hints, &prepare.prepared_units).is_ok();
    let generated_at = now_utc_seconds();
    let units = normalized_units_from_response(
        &response,
        &prepare.prepared_units,
        None,
        &task.input_hash,
        &profile.tool_profile_hash,
        MarkdownizeMode::Full,
        &generated_at,
    )
    .map_err(|_| TaskExecutionFailure {
        retry_kind: RetryErrorKind::ContractViolation,
    })?;
    if units.is_empty() {
        return Err(TaskExecutionFailure {
            retry_kind: RetryErrorKind::ContractViolation,
        });
    }
    let done = units.len();
    let failed = prepare.prepared_units.len().saturating_sub(done);
    let status = if strict_valid {
        TaskStatus::Done
    } else {
        task_status_from_unit_counts(done, failed, false)
    };
    let run_id = format!("run_{}", new_ulid(repo.root()));
    let manifest = manifest_from_units(
        &prepare.prepared_units,
        &units,
        &task.input_hash,
        &profile.tool_profile_hash,
        None,
        &run_id,
        &generated_at,
    );
    persist_normalized_instance(repo.kcs_dir(), &manifest, &units).map_err(|_| {
        TaskExecutionFailure {
            retry_kind: RetryErrorKind::InvalidInput,
        }
    })?;
    Ok(OnlineExecutionOutcome {
        output_ref: normalized_output_ref(repo, &task.input_hash, &profile.tool_profile_hash, 0),
        status,
        cost_usd: estimate_online_markdownize_cost(
            path.metadata().map(|metadata| metadata.len()).unwrap_or(0),
        ),
        adapter_kind: "markdown".to_owned(),
    })
}

fn run_mistral_adapter(
    repo: &Repository,
    raw_hash: &str,
    path: &Path,
    media_type: &str,
    prepare: &kcs_pipeline::prepare::PrepareStageOutput,
) -> std::result::Result<
    (AdapterProfile, kcs_adapter::types::MarkdownizeResponse),
    TaskExecutionFailure,
> {
    let request = MarkdownizeRequest {
        raw: RawInput {
            raw_hash: raw_hash.to_owned(),
            path: Some(path.display().to_string()),
        },
        media_type: media_type.to_owned(),
        prepared_unit_hint: Some(prepared_unit_hints(&prepare.prepared_units)),
        mode: AdapterMarkdownizeMode::Full,
        previous: None,
        hints: None,
        tool_profile_hash: String::new(),
        spec_version: 1,
    };
    match std::env::var("KCS_TEST_MISTRAL_OCR").ok().as_deref() {
        Some("auth_error") => {
            return Err(TaskExecutionFailure {
                retry_kind: RetryErrorKind::AuthError,
            });
        }
        Some("rate_limit") => {
            // Retryable failure injection for backoff scheduling tests (I2).
            return Err(TaskExecutionFailure {
                retry_kind: RetryErrorKind::RateLimit,
            });
        }
        Some("mock") | Some("partial") | Some("mock_link_image") => {
            // Mirror the production path: resolve the pin once up front so the
            // profile (and its tool_profile_hash) reflect the resolved pin,
            // now that `profile()` no longer resolves internally (Step2c I5).
            let client = MockMistralClient;
            let model_pin = client
                .resolve_model_pin("mistral-ocr-latest")
                .map_err(task_failure_from_adapter)?;
            let adapter =
                MistralOcrMarkdownizeAdapter::new(client, model_pin, repo.scope_id_for_adapter())
                    .with_image_store(repo.kcs_dir());
            let profile = adapter.profile();
            let mut request = request;
            request.tool_profile_hash = profile.tool_profile_hash.clone();
            return Ok((
                profile,
                adapter
                    .markdownize(request)
                    .map_err(task_failure_from_adapter)?,
            ));
        }
        _ => {}
    }
    let client = EnvMistralOcrClient::new();
    let model_pin = client
        .resolve_model_pin("mistral-ocr-latest")
        .map_err(task_failure_from_adapter)?;
    let adapter = MistralOcrMarkdownizeAdapter::new(client, model_pin, repo.scope_id_for_adapter())
        .with_image_store(repo.kcs_dir());
    let profile = adapter.profile();
    let mut request = request;
    request.tool_profile_hash = profile.tool_profile_hash.clone();
    Ok((
        profile,
        adapter
            .markdownize(request)
            .map_err(task_failure_from_adapter)?,
    ))
}

trait RepositoryScopeId {
    fn scope_id_for_adapter(&self) -> String;
}

impl RepositoryScopeId for Repository {
    fn scope_id_for_adapter(&self) -> String {
        fs::read_to_string(self.kcs_dir().join("scope.json"))
            .ok()
            .and_then(|text| serde_json::from_str::<Value>(&text).ok())
            .and_then(|value| {
                value
                    .get("scope_id")
                    .and_then(Value::as_str)
                    .map(str::to_owned)
            })
            .unwrap_or_else(|| "unknown".to_owned())
    }
}

#[derive(Debug, Clone)]
struct MockMistralClient;

impl MistralOcrClient for MockMistralClient {
    fn resolve_model_pin(&self, _configured_model: &str) -> kcs_adapter::Result<String> {
        Ok("mistral-ocr-2505".to_owned())
    }

    fn ocr_markdown(
        &self,
        request: &MarkdownizeRequest,
        model_pin: &str,
    ) -> kcs_adapter::Result<OcrResponse> {
        let mut pages: Vec<OcrPage> = request
            .prepared_unit_hint
            .as_deref()
            .unwrap_or(&[])
            .iter()
            .enumerate()
            .map(|(index, hint)| OcrPage {
                index,
                markdown: if std::env::var("KCS_TEST_MISTRAL_OCR").ok().as_deref()
                    == Some("mock_link_image")
                {
                    format!(
                        "[source](https://example.com/{index}) mock ocr {} ![img-{index}](img-{index}.png)\n",
                        hint.unit_key
                    )
                } else {
                    format!(
                        "mock ocr {} ![img-{index}](img-{index}.png)\n",
                        hint.unit_key
                    )
                },
                images: vec![OcrImage {
                    bytes: format!("image-{}", hint.unit_key).into_bytes(),
                    media_type: "image/png".to_owned(),
                    bbox: Some([index as i64, 0, index as i64 + 1, 1]),
                    confidence: Some("0.99".to_owned()),
                }],
            })
            .collect();
        if std::env::var("KCS_TEST_MISTRAL_OCR").ok().as_deref() == Some("partial") {
            pages.pop();
        }
        Ok(OcrResponse {
            pages,
            model_version_pin: model_pin.to_owned(),
        })
    }
}

fn task_failure_from_adapter(error: kcs_adapter::AdapterError) -> TaskExecutionFailure {
    let retry_kind = match error {
        kcs_adapter::AdapterError::Auth(_) => RetryErrorKind::AuthError,
        kcs_adapter::AdapterError::RateLimit(_) => RetryErrorKind::RateLimit,
        kcs_adapter::AdapterError::QuotaExceeded(_) => RetryErrorKind::QuotaExceeded,
        kcs_adapter::AdapterError::Network(_) | kcs_adapter::AdapterError::Io { .. } => {
            RetryErrorKind::NetworkError
        }
        kcs_adapter::AdapterError::ContractViolation(_)
        | kcs_adapter::AdapterError::ConfigSchema(_) => RetryErrorKind::ContractViolation,
    };
    TaskExecutionFailure { retry_kind }
}

fn retry_reason(kind: RetryErrorKind) -> &'static str {
    match kind {
        RetryErrorKind::NetworkError => "network_error",
        RetryErrorKind::RateLimit => "rate_limit",
        RetryErrorKind::AuthError => "auth_error",
        RetryErrorKind::QuotaExceeded => "quota_exceeded",
        RetryErrorKind::InvalidInput => "invalid_input",
        RetryErrorKind::ContractViolation => "contract_violation",
        RetryErrorKind::BudgetExceeded => "budget_exceeded",
    }
}

fn retry_kind_from_reason(reason: Option<&str>) -> RetryErrorKind {
    match reason {
        Some("network_error") => RetryErrorKind::NetworkError,
        Some("rate_limit") => RetryErrorKind::RateLimit,
        Some("auth_error") => RetryErrorKind::AuthError,
        Some("quota_exceeded") => RetryErrorKind::QuotaExceeded,
        Some("invalid_input") => RetryErrorKind::InvalidInput,
        Some("budget_exceeded") => RetryErrorKind::BudgetExceeded,
        _ => RetryErrorKind::ContractViolation,
    }
}

fn task_retry_allowed(task: &TaskDescriptor) -> bool {
    let kind = retry_kind_from_reason(task.fallback_reason.as_deref());
    let policy = retry_policy(kind);
    policy.retryable
        && policy
            .max_attempts
            .map(|max| task.attempts < max)
            .unwrap_or(true)
}

fn task_retry_due(task: &TaskDescriptor) -> bool {
    task.next_retry_at
        .as_deref()
        .map(|retry_at| retry_at <= now_utc_seconds().as_str())
        .unwrap_or(true)
}

/// Absolute time a failed task becomes eligible for retry: `now` plus the
/// backoff derived from its `RetryPolicy.backoff` descriptor (Step2c I2).
/// `attempts` is the post-increment attempt count (>= 1). Falls back to `now`
/// when the clock string cannot be parsed.
fn scheduled_retry_at(now: &str, backoff: &str, attempts: u32) -> String {
    let delay = retry_backoff_seconds(backoff, attempts);
    kcs_core::scope::parse_utc_seconds(now)
        .map(|secs| kcs_core::scope::format_utc_seconds(secs + delay))
        .unwrap_or_else(|| now.to_owned())
}

/// Backoff delay (seconds) for a failed task's next retry, derived from the
/// `RetryPolicy.backoff` descriptor in `crates/kcs-pipeline/src/task.rs`.
/// Jitter is intentionally omitted for deterministic scheduling / testing
/// (see `tasks/ws1c-decisions.md` #29). `attempts` is the post-increment
/// attempt count (>= 1).
fn retry_backoff_seconds(backoff: &str, attempts: u32) -> i64 {
    // exp(base=Ns,cap=Ms,...): min(base * 2^(attempts-1), cap).
    let exponential = |base: i64, cap: i64| {
        let exponent = attempts.saturating_sub(1).min(16);
        base.saturating_mul(1_i64 << exponent).clamp(0, cap)
    };
    if let Some(inner) = backoff
        .strip_prefix("exp(")
        .and_then(|s| s.strip_suffix(')'))
    {
        let base = duration_secs_field(inner, "base").unwrap_or(2);
        let cap = duration_secs_field(inner, "cap").unwrap_or(60);
        return exponential(base, cap);
    }
    if let Some(inner) = backoff
        .strip_prefix("fixed(")
        .and_then(|s| s.strip_suffix(')'))
    {
        return parse_duration_secs(inner).unwrap_or(3_600);
    }
    // "retry_after": the local placeholder has no server `Retry-After` header,
    // so reuse the exponential schedule (base 2s, cap 60s).
    if backoff == "retry_after" {
        return exponential(2, 60);
    }
    0
}

/// Parse a compact duration such as `2s`, `30m`, or `1h` into seconds.
fn parse_duration_secs(text: &str) -> Option<i64> {
    let text = text.trim();
    let split = text.find(|ch: char| !ch.is_ascii_digit())?;
    let (digits, unit) = text.split_at(split);
    let value = digits.parse::<i64>().ok()?;
    let multiplier = match unit {
        "s" => 1,
        "m" => 60,
        "h" => 3_600,
        _ => return None,
    };
    Some(value * multiplier)
}

/// Extract a `key=<duration>` field (e.g. `base=2s`) from a comma-separated
/// backoff descriptor body.
fn duration_secs_field(inner: &str, key: &str) -> Option<i64> {
    inner.split(',').find_map(|part| {
        let rest = part.trim().strip_prefix(key)?.strip_prefix('=')?;
        parse_duration_secs(rest)
    })
}

fn estimate_online_markdownize_cost(size_bytes: u64) -> f64 {
    estimate_local_baseline_cost(size_bytes) * 10.0
}

fn media_type_for_cli_path(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or_default()
    {
        "md" | "markdown" => "text/markdown",
        "txt" => "text/plain",
        "rs" | "py" | "js" | "ts" | "go" | "java" | "c" | "h" | "cpp" => "text/x-code",
        "pdf" => "application/pdf",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        _ => "application/octet-stream",
    }
}

fn budget_status_json(repo: &Repository) -> Result<Value> {
    let caps = read_budget_policy(user_config_toml_path(), repo.kcs_dir().join("config.toml"))
        .map_err(pipeline_to_kcs)?;
    let now = now_utc_seconds();
    let month = utc_month(&now);
    let ledger = CostLedger::new(cost_ledger_path());
    let scope_id = repo.scope_id_for_adapter();
    let device_spent = ledger
        .monthly_total(&month, None)
        .map_err(pipeline_to_kcs)?;
    let folder_spent = ledger
        .monthly_total(&month, Some(&scope_id))
        .map_err(pipeline_to_kcs)?;
    let device_remaining = caps.device_monthly_usd_cap - device_spent;
    let folder_remaining = caps.folder_monthly_usd_cap.map(|cap| cap - folder_spent);
    let cap_kind = match folder_remaining {
        Some(folder) if folder <= device_remaining => BudgetCapKind::Folder,
        _ => BudgetCapKind::Device,
    };
    Ok(json!({
        "month": month,
        "device_monthly_usd_cap": caps.device_monthly_usd_cap,
        "folder_monthly_usd_cap": caps.folder_monthly_usd_cap,
        "device_spent_usd": device_spent,
        "folder_spent_usd": folder_spent,
        "device_remaining_usd": device_remaining,
        "folder_remaining_usd": folder_remaining,
        "cap_kind": match cap_kind {
            BudgetCapKind::Device => "device",
            BudgetCapKind::Folder => "folder",
        },
        "device_per_adapter": caps.device_per_adapter,
        "folder_per_adapter": caps.folder_per_adapter,
    }))
}

fn index_preview_json(root: &Path, preview: &ScanPreview) -> Value {
    let included = preview
        .candidates
        .iter()
        .filter(|candidate| !candidate.ignored)
        .collect::<Vec<_>>();
    let estimated_size_bytes = included
        .iter()
        .map(|candidate| candidate.size_bytes)
        .sum::<u64>();
    let excluded_candidates = preview
        .candidates
        .iter()
        .filter(|candidate| candidate.ignored)
        .map(|candidate| candidate.input_path.clone())
        .collect::<Vec<_>>();
    let sensitive_candidates = preview
        .candidates
        .iter()
        .filter(|candidate| candidate.quarantine_reason.is_some())
        .map(|candidate| {
            json!({
                "path": candidate.input_path,
                "reason": candidate.quarantine_reason,
                "ignored": candidate.ignored,
            })
        })
        .collect::<Vec<_>>();
    let large_files = preview
        .candidates
        .iter()
        .filter(|candidate| candidate.size_bytes >= 10 * 1024 * 1024)
        .map(|candidate| {
            json!({
                "path": candidate.input_path,
                "size_bytes": candidate.size_bytes,
            })
        })
        .collect::<Vec<_>>();
    json!({
        "status": "preview",
        "root": root,
        "scope": preview.scope_id,
        "estimated_file_count": included.len(),
        "estimated_size_bytes": estimated_size_bytes,
        "large_files": large_files,
        "effective_ignore": ".kcsignore + built-in secrets Tier A",
        "excluded_candidates": excluded_candidates,
        "sensitive_candidates": sensitive_candidates,
        "network_transmission_policy": {
            "default": "disabled until --approve or --online",
            "yes_grants_network": false,
        },
        "adapter_execution_mode": {
            "markdownize": "deterministic_library baseline",
            "embedding": "not generated without online opt-in",
        },
        "estimated_cost": preview.estimated_cost,
        "budget_cap": preview.estimated_cost.as_ref().and_then(|cost| cost.budget_cap_usd),
        "estimated_completion": "baseline completes in this run; online enhancement depends on budget and opt-in",
        "candidates": preview.candidates,
    })
}

#[derive(Debug, Default)]
struct IndexPipelineResult {
    normalize_by_path: BTreeMap<String, NormalizeRef>,
    network_allowed: bool,
    pending_online_tasks: usize,
    paused_tasks: usize,
    normalized_files: usize,
    pending_files: usize,
    failed_files: usize,
}

fn active_markdown_adapter(_repo: &Repository) -> Box<dyn MarkdownizeAdapter> {
    match std::env::var("KCS_TEST_MARKDOWNIZE_ADAPTER")
        .ok()
        .as_deref()
    {
        Some("incremental") => Box::new(TestIncrementalMarkdownizeAdapter {
            reject_incremental: false,
            reject_full: false,
        }),
        Some("reject_incremental") => Box::new(TestIncrementalMarkdownizeAdapter {
            reject_incremental: true,
            reject_full: false,
        }),
        Some("reject_incremental_and_full") => Box::new(TestIncrementalMarkdownizeAdapter {
            reject_incremental: true,
            reject_full: true,
        }),
        _ => Box::new(DeterministicAdapter),
    }
}

#[derive(Debug, Clone)]
struct TestIncrementalMarkdownizeAdapter {
    reject_incremental: bool,
    reject_full: bool,
}

impl MarkdownizeAdapter for TestIncrementalMarkdownizeAdapter {
    fn profile(&self) -> AdapterProfile {
        let profile = json!({
            "adapter_kind": "markdownize",
            "adapter_role": "text",
            "model_or_tool_family": "kcs-test-incremental",
            "model_version_pin": "1.0.0",
            "output_schema": "kcs-markdown-v1",
            "runtime_kind": "local",
            "spec_version": 1
        });
        AdapterProfile {
            adapter_kind: AdapterKind::Markdownize,
            adapter_id: "test_incremental_markdownize".to_owned(),
            execution_mode: ExecutionMode::DeterministicLibrary,
            tool_profile_hash: tool_profile_hash(&profile)
                .expect("built-in test profile should hash"),
            version: env!("CARGO_PKG_VERSION").to_owned(),
            capability_flags: vec!["incremental_update".to_owned()],
            allow_network: false,
        }
    }

    fn markdownize(
        &self,
        request: MarkdownizeRequest,
    ) -> kcs_adapter::Result<kcs_adapter::types::MarkdownizeResponse> {
        let hints = request.prepared_unit_hint.clone().unwrap_or_default();
        if request.mode == AdapterMarkdownizeMode::Incremental {
            let incremental =
                request
                    .hints
                    .clone()
                    .unwrap_or(kcs_adapter::types::IncrementalHints {
                        changed_unit_keys: hints.iter().map(|hint| hint.unit_key.clone()).collect(),
                        added_unit_keys: Vec::new(),
                        removed_unit_keys: Vec::new(),
                        page_fingerprints: BTreeMap::new(),
                    });
            let changed = incremental.changed_unit_keys;
            let added = incremental.added_unit_keys;
            let unchanged = hints
                .iter()
                .filter(|hint| !changed.contains(&hint.unit_key) && !added.contains(&hint.unit_key))
                .map(|hint| hint.unit_key.clone())
                .collect::<Vec<_>>();
            return Ok(kcs_adapter::types::MarkdownizeResponse {
                mode_used: AdapterMarkdownizeMode::Incremental,
                updated_units: hints
                    .iter()
                    .filter(|hint| changed.contains(&hint.unit_key))
                    .map(|hint| test_markdown_unit(hint, "incremental"))
                    .collect(),
                unchanged_unit_keys: if self.reject_incremental {
                    Vec::new()
                } else {
                    unchanged
                },
                added_units: hints
                    .iter()
                    .filter(|hint| added.contains(&hint.unit_key))
                    .map(|hint| test_markdown_unit(hint, "incremental-added"))
                    .collect(),
                removed_unit_keys: incremental.removed_unit_keys,
                evidence_pointers: Vec::new(),
                fallback_to_full: false,
                reason: None,
            });
        }
        Ok(kcs_adapter::types::MarkdownizeResponse {
            mode_used: AdapterMarkdownizeMode::Full,
            updated_units: if self.reject_full {
                Vec::new()
            } else {
                hints
                    .iter()
                    .map(|hint| test_markdown_unit(hint, "full"))
                    .collect()
            },
            unchanged_unit_keys: Vec::new(),
            added_units: Vec::new(),
            removed_unit_keys: Vec::new(),
            evidence_pointers: Vec::new(),
            fallback_to_full: false,
            reason: None,
        })
    }
}

fn test_markdown_unit(hint: &PreparedUnitHint, prefix: &str) -> MarkdownUnit {
    MarkdownUnit {
        unit_key: hint.unit_key.clone(),
        unit_type: hint.unit_kind,
        markdown: format!("{prefix} {}\n", hint.unit_key),
        metadata: BTreeMap::new(),
    }
}

fn run_index_pipeline(
    repo: &Repository,
    preview: &ScanPreview,
    args: &IndexArgs,
) -> Result<IndexPipelineResult> {
    let task_store = TaskStore::new(repo.kcs_dir());
    let now = now_utc_seconds();
    let scope_id = preview.scope_id.clone();
    let prepare_profile_hash =
        tool_profile_hash(&deterministic_prepare_profile_value()).map_err(adapter_to_kcs)?;
    let markdown_adapter = active_markdown_adapter(repo);
    let markdown_profile = markdown_adapter.profile();
    let markdown_profile_hash = markdown_profile.tool_profile_hash.clone();
    let network_allowed = network_allowed(repo, args)?;
    let cost_ledger = CostLedger::new(cost_ledger_path());
    let budget_caps =
        read_budget_policy(user_config_toml_path(), repo.kcs_dir().join("config.toml"))
            .map_err(pipeline_to_kcs)?;
    let month = utc_month(&now);

    let mut result = IndexPipelineResult {
        network_allowed,
        ..IndexPipelineResult::default()
    };

    for candidate in preview
        .candidates
        .iter()
        .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
    {
        let path = repo.root().join(&candidate.input_path);
        let bytes = fs::read(&path)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        let raw_hash = candidate
            .raw_hash
            .clone()
            .unwrap_or_else(|| hash_bytes(&bytes));
        let prepare = prepare_units(PrepareStageRequest {
            raw_hash: raw_hash.clone(),
            media_type: candidate.media_type.clone(),
            input_path: path.display().to_string(),
            tool_profile_hash: prepare_profile_hash.clone(),
        })
        .map_err(pipeline_to_kcs)?;

        write_prepared_objects(
            repo,
            &prepare.prepared_units,
            &prepare.prepared_object_hashes,
            &bytes,
            &candidate.media_type,
        )?;

        if prepare.prepared_units.is_empty() {
            let task = task_descriptor(
                repo,
                TaskType::Markdownize,
                Some(MarkdownizeMode::Full),
                candidate,
                &raw_hash,
                "pending:scanned_pdf_without_text_layer",
                TaskStatus::Pending,
                Some("ai_enhancement_required"),
                &now,
            );
            task_store.append(&task).map_err(pipeline_to_kcs)?;
            result.pending_files += 1;
            continue;
        }

        let output_ref = normalized_output_ref(repo, &raw_hash, &markdown_profile_hash, 0);
        if task_store
            .done_output_for(&raw_hash, &output_ref)
            .map_err(pipeline_to_kcs)?
            .is_some()
        {
            result.normalize_by_path.insert(
                candidate.input_path.clone(),
                NormalizeRef {
                    tool_profile_hash: markdown_profile_hash.clone(),
                    gen: 0,
                },
            );
            result.normalized_files += 1;
            enqueue_online_placeholder_task(
                repo,
                &task_store,
                candidate,
                &raw_hash,
                &scope_id,
                network_allowed,
                args,
                &now,
                &mut result,
                &cost_ledger,
                &budget_caps,
                &month,
            )?;
            continue;
        }

        let previous =
            previous_instance_for_path(&task_store, &candidate.input_path, &markdown_profile_hash)?;
        let mapping = previous
            .as_ref()
            .map(|previous| map_units(&previous.prepared_units, &prepare.prepared_units));
        let incremental_hints = mapping
            .as_ref()
            .map(|mapping| incremental_hints_from_mapping(mapping, &prepare.prepared_units))
            .unwrap_or_else(|| all_changed_hints(&prepare.prepared_units));
        let mode_decision = choose_markdownize_mode(&IncrementalModeInput {
            has_previous_done_run: previous.is_some(),
            raw_hash_only_changed: true,
            adapter_capabilities: markdown_profile.capability_flags.clone(),
            change_rate: mapping
                .as_ref()
                .map(|mapping| mapping.change_rate)
                .unwrap_or(1.0),
            threshold: 0.30,
            consecutive_incremental_count: consecutive_incremental_count(
                &task_store,
                &candidate.input_path,
            )?,
            max_consecutive_incremental: 5,
        });
        let mode = mode_decision.mode;
        let hints = prepared_unit_hints(&prepare.prepared_units);
        let adapter_previous = previous
            .as_ref()
            .map(|previous| PreviousMarkdownizeContext {
                raw: RawInput {
                    raw_hash: previous.manifest.raw_hash.clone(),
                    path: Some(
                        repo.root()
                            .join(&candidate.input_path)
                            .display()
                            .to_string(),
                    ),
                },
                normalized_units: previous
                    .units
                    .iter()
                    .map(normalized_unit_to_adapter_unit)
                    .collect(),
                tool_profile_hash: previous.manifest.tool_profile_hash.clone(),
            });
        let request = MarkdownizeRequest {
            raw: RawInput {
                raw_hash: raw_hash.clone(),
                path: Some(path.display().to_string()),
            },
            media_type: candidate.media_type.clone(),
            prepared_unit_hint: Some(hints),
            mode: adapter_mode(mode),
            previous: (mode == MarkdownizeMode::Incremental)
                .then_some(adapter_previous)
                .flatten(),
            hints: (mode == MarkdownizeMode::Incremental)
                .then(|| adapter_hints(&incremental_hints)),
            tool_profile_hash: markdown_profile_hash.clone(),
            spec_version: 1,
        };

        let mut response = markdown_adapter
            .markdownize(request.clone())
            .map_err(adapter_to_kcs)?;
        let mut final_mode = mode;
        let mut fallback_reason = mode_decision.reason.clone();
        let validation = if response.fallback_to_full {
            Err(kcs_pipeline::PipelineError::contract(
                "KCS-E-ADAPTER-CONTRACT-001",
                "adapter_requested_full_fallback",
            ))
        } else {
            validate_markdownize_response(&response, &incremental_hints, &prepare.prepared_units)
        };
        if let Err(error) = validation {
            if mode != MarkdownizeMode::Incremental {
                append_failed_markdownize_task(
                    repo,
                    &task_store,
                    candidate,
                    &raw_hash,
                    &output_ref,
                    "contract_violation",
                    &now,
                )?;
                result.failed_files += 1;
                let _ = error;
                continue;
            }
            let mut full_request = request;
            full_request.mode = AdapterMarkdownizeMode::Full;
            full_request.previous = None;
            full_request.hints = None;
            let fallback_response = markdown_adapter
                .markdownize(full_request)
                .map_err(adapter_to_kcs)
                .and_then(|response| {
                    validate_markdownize_response(
                        &response,
                        &incremental_hints,
                        &prepare.prepared_units,
                    )
                    .map_err(pipeline_to_kcs)?;
                    Ok(response)
                });
            let Ok(fallback_response) = fallback_response else {
                append_failed_markdownize_task(
                    repo,
                    &task_store,
                    candidate,
                    &raw_hash,
                    &output_ref,
                    "full_fallback_failed",
                    &now,
                )?;
                result.failed_files += 1;
                continue;
            };
            response = fallback_response;
            final_mode = MarkdownizeMode::Full;
            fallback_reason = Some("full_fallback_after_incremental_reject".to_owned());
        }

        let generated_at = now_utc_seconds();
        let run_id = format!("run_{}", new_ulid(repo.root()));
        let units = normalized_units_from_response(
            &response,
            &prepare.prepared_units,
            previous.as_ref(),
            &raw_hash,
            &markdown_profile_hash,
            final_mode,
            &generated_at,
        )?;
        let manifest = manifest_from_units(
            &prepare.prepared_units,
            &units,
            &raw_hash,
            &markdown_profile_hash,
            previous.as_ref().map(|previous| previous.manifest.gen),
            &run_id,
            &generated_at,
        );
        persist_normalized_instance(repo.kcs_dir(), &manifest, &units).map_err(pipeline_to_kcs)?;
        let task = task_descriptor(
            repo,
            TaskType::Markdownize,
            Some(mode),
            candidate,
            &raw_hash,
            &output_ref,
            TaskStatus::Done,
            fallback_reason.as_deref(),
            &generated_at,
        );
        let mut task = task;
        task.mode = Some(final_mode);
        task.previous_raw_hash = previous
            .as_ref()
            .map(|previous| previous.manifest.raw_hash.clone());
        task.parent_run_id = previous
            .as_ref()
            .map(|previous| previous.manifest.run_id.clone());
        task.changed_unit_keys = incremental_hints.changed_unit_keys.clone();
        task.unit_keys = Some(
            prepare
                .prepared_units
                .iter()
                .map(|unit| unit.unit_key.clone())
                .collect(),
        );
        task_store.append(&task).map_err(pipeline_to_kcs)?;
        result.normalize_by_path.insert(
            candidate.input_path.clone(),
            NormalizeRef {
                tool_profile_hash: markdown_profile_hash.clone(),
                gen: 0,
            },
        );
        result.normalized_files += 1;
        cost_ledger
            .append_monthly(&MonthlyCostLedgerEntry {
                month: month.clone(),
                scope_id: scope_id.clone(),
                adapter_kind: "deterministic_baseline".to_owned(),
                usd: estimate_local_baseline_cost(candidate.size_bytes),
            })
            .map_err(pipeline_to_kcs)?;
        enqueue_online_placeholder_task(
            repo,
            &task_store,
            candidate,
            &raw_hash,
            &scope_id,
            network_allowed,
            args,
            &now,
            &mut result,
            &cost_ledger,
            &budget_caps,
            &month,
        )?;
    }
    Ok(result)
}

fn write_prepared_objects(
    repo: &Repository,
    prepared_units: &[PreparedUnit],
    prepared_hashes: &[String],
    bytes: &[u8],
    media_type: &str,
) -> Result<()> {
    let pdf_pages = (media_type == "application/pdf").then(|| pdf_text_pages(bytes));
    for (index, prepared_hash) in prepared_hashes.iter().enumerate() {
        let digest = prepared_hash
            .strip_prefix("sha256:")
            .ok_or_else(|| KcsError::schema("prepared hash must use sha256 prefix"))?;
        let path = repo
            .kcs_dir()
            .join("objects/prepared")
            .join(&digest[0..2])
            .join(&digest[2..4])
            .join(prepared_hash);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)
                .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
        }
        if !path.exists() {
            let object_bytes = pdf_pages
                .as_ref()
                .and_then(|pages| pages.get(index))
                .map(|page| page.as_bytes())
                .or_else(|| {
                    prepared_units
                        .get(index)
                        .and_then(|unit| (unit.unit_type == UnitType::Page).then_some(b"" as &[u8]))
                })
                .unwrap_or(bytes);
            fs::write(&path, object_bytes)
                .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        }
    }
    Ok(())
}

fn normalized_output_ref(
    repo: &Repository,
    raw_hash: &str,
    tool_profile_hash: &str,
    gen: u64,
) -> String {
    kcs_pipeline::markdownize::normalized_instance_dir(
        repo.kcs_dir(),
        raw_hash,
        tool_profile_hash,
        gen,
    )
    .display()
    .to_string()
}

#[allow(clippy::too_many_arguments)]
fn task_descriptor(
    repo: &Repository,
    task_type: TaskType,
    mode: Option<MarkdownizeMode>,
    candidate: &ScanCandidate,
    input_hash: &str,
    output_ref: &str,
    status: TaskStatus,
    fallback_reason: Option<&str>,
    created_at: &str,
) -> TaskDescriptor {
    TaskDescriptor {
        task_id: format!("task_{}", new_ulid(repo.root())),
        task_type,
        mode,
        input_path: candidate.input_path.clone(),
        input_hash: input_hash.to_owned(),
        previous_raw_hash: None,
        parent_run_id: None,
        changed_unit_keys: Vec::new(),
        output_ref: output_ref.to_owned(),
        unit_keys: None,
        status,
        attempts: 0,
        next_retry_at: None,
        deadline: None,
        heartbeat_at: None,
        fallback_reason: fallback_reason.map(str::to_owned),
        created_at: created_at.to_owned(),
    }
}

fn append_failed_markdownize_task(
    repo: &Repository,
    task_store: &TaskStore,
    candidate: &ScanCandidate,
    input_hash: &str,
    output_ref: &str,
    fallback_reason: &str,
    created_at: &str,
) -> Result<()> {
    let task = task_descriptor(
        repo,
        TaskType::Markdownize,
        Some(MarkdownizeMode::Full),
        candidate,
        input_hash,
        output_ref,
        TaskStatus::Failed,
        Some(fallback_reason),
        created_at,
    );
    task_store.append(&task).map_err(pipeline_to_kcs)
}

fn prepared_unit_hints(prepared_units: &[PreparedUnit]) -> Vec<PreparedUnitHint> {
    prepared_units
        .iter()
        .map(|unit| PreparedUnitHint {
            unit_key: unit.unit_key.clone(),
            prepared_hash: unit.prepared_hash.clone(),
            unit_kind: adapter_unit_kind(unit.unit_type),
            order: unit.order,
        })
        .collect()
}

fn adapter_unit_kind(unit_type: UnitType) -> UnitKind {
    match unit_type {
        UnitType::Page => UnitKind::Page,
        UnitType::Slide => UnitKind::Slide,
        UnitType::HeadingSection => UnitKind::HeadingSection,
        UnitType::Sheet => UnitKind::Sheet,
        UnitType::Image => UnitKind::Image,
        UnitType::File => UnitKind::File,
        UnitType::Symbol => UnitKind::Symbol,
    }
}

fn adapter_mode(mode: MarkdownizeMode) -> AdapterMarkdownizeMode {
    match mode {
        MarkdownizeMode::Full => AdapterMarkdownizeMode::Full,
        MarkdownizeMode::Incremental => AdapterMarkdownizeMode::Incremental,
    }
}

#[derive(Debug, Clone)]
struct PreviousInstance {
    manifest: NormalizedInstanceManifest,
    units: Vec<NormalizedUnitObject>,
    prepared_units: Vec<PreparedUnit>,
}

fn previous_instance_for_path(
    task_store: &TaskStore,
    input_path: &str,
    tool_profile_hash: &str,
) -> Result<Option<PreviousInstance>> {
    let mut tasks = task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.input_path == input_path
                && matches!(task.status, TaskStatus::Done | TaskStatus::Partial)
                && !task.output_ref.starts_with("online:")
        })
        .collect::<Vec<_>>();
    tasks.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    for task in tasks {
        let Some(previous) = load_previous_instance(&task.output_ref)? else {
            continue;
        };
        if previous.manifest.tool_profile_hash == tool_profile_hash {
            return Ok(Some(previous));
        }
    }
    Ok(None)
}

fn load_previous_instance(output_ref: &str) -> Result<Option<PreviousInstance>> {
    let dir = PathBuf::from(output_ref);
    let manifest_path = dir.join("manifest.json");
    let Ok(bytes) = fs::read(&manifest_path) else {
        return Ok(None);
    };
    let manifest: NormalizedInstanceManifest =
        serde_json::from_slice(&bytes).map_err(|err| KcsError::schema(err.to_string()))?;
    let mut units = Vec::new();
    for entry in &manifest.units {
        if entry.status != UnitStatus::Done {
            continue;
        }
        let unit_path = dir.join(format!("{}.json", entry.unit_ref));
        let bytes = fs::read(&unit_path)
            .map_err(|err| KcsError::io(err.to_string(), unit_path.display().to_string()))?;
        let unit: NormalizedUnitObject =
            serde_json::from_slice(&bytes).map_err(|err| KcsError::schema(err.to_string()))?;
        units.push(unit);
    }
    let prepared_units = manifest
        .units
        .iter()
        .map(|entry| PreparedUnit {
            order: entry.order,
            unit_key: entry.unit_key.clone(),
            unit_type: entry.unit_type,
            prepared_hash: entry.prepared_hash.clone(),
            fingerprint: UnitFingerprint {
                perceptual_hash: entry.prepared_hash.clone(),
                text_hash: entry.prepared_hash.clone(),
                visual_hash: entry.prepared_hash.clone(),
            },
            mime: None,
            page_number: (entry.unit_type == UnitType::Page).then_some(entry.order + 1),
        })
        .collect();
    Ok(Some(PreviousInstance {
        manifest,
        units,
        prepared_units,
    }))
}

fn incremental_hints_from_mapping(
    mapping: &kcs_pipeline::prepare::UnitMapping,
    prepared_units: &[PreparedUnit],
) -> IncrementalHints {
    IncrementalHints {
        changed_unit_keys: mapping.changed_unit_keys.clone(),
        added_unit_keys: mapping.added_unit_keys.clone(),
        removed_unit_keys: mapping.removed_unit_keys.clone(),
        page_fingerprints: prepared_units
            .iter()
            .map(|unit| (unit.unit_key.clone(), unit.fingerprint.clone()))
            .collect(),
    }
}

fn all_changed_hints(prepared_units: &[PreparedUnit]) -> IncrementalHints {
    IncrementalHints {
        changed_unit_keys: prepared_units
            .iter()
            .map(|unit| unit.unit_key.clone())
            .collect(),
        added_unit_keys: Vec::new(),
        removed_unit_keys: Vec::new(),
        page_fingerprints: prepared_units
            .iter()
            .map(|unit| (unit.unit_key.clone(), unit.fingerprint.clone()))
            .collect(),
    }
}

fn adapter_hints(hints: &IncrementalHints) -> kcs_adapter::types::IncrementalHints {
    kcs_adapter::types::IncrementalHints {
        changed_unit_keys: hints.changed_unit_keys.clone(),
        added_unit_keys: hints.added_unit_keys.clone(),
        removed_unit_keys: hints.removed_unit_keys.clone(),
        page_fingerprints: hints
            .page_fingerprints
            .iter()
            .map(|(key, fingerprint)| {
                (
                    key.clone(),
                    kcs_adapter::types::UnitFingerprint {
                        perceptual_hash: fingerprint.perceptual_hash.clone(),
                        text_hash: fingerprint.text_hash.clone(),
                        visual_hash: fingerprint.visual_hash.clone(),
                    },
                )
            })
            .collect(),
    }
}

fn normalized_unit_to_adapter_unit(unit: &NormalizedUnitObject) -> MarkdownUnit {
    MarkdownUnit {
        unit_key: unit.unit_key.clone(),
        unit_type: adapter_unit_kind(unit.unit_type),
        markdown: unit.markdown.clone(),
        metadata: BTreeMap::new(),
    }
}

fn consecutive_incremental_count(task_store: &TaskStore, input_path: &str) -> Result<u32> {
    let mut tasks = task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| task.input_path == input_path && task.status == TaskStatus::Done)
        .collect::<Vec<_>>();
    tasks.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    let mut count = 0u32;
    for task in tasks {
        if task.mode == Some(MarkdownizeMode::Incremental) {
            count = count.saturating_add(1);
        } else {
            break;
        }
    }
    Ok(count)
}

fn normalized_units_from_response(
    response: &kcs_adapter::types::MarkdownizeResponse,
    prepared_units: &[PreparedUnit],
    previous: Option<&PreviousInstance>,
    raw_hash: &str,
    tool_profile_hash: &str,
    mode: MarkdownizeMode,
    generated_at: &str,
) -> Result<Vec<NormalizedUnitObject>> {
    let prepared = prepared_units
        .iter()
        .map(|unit| (unit.unit_key.as_str(), unit))
        .collect::<BTreeMap<_, _>>();
    let previous_units = previous
        .map(|previous| {
            previous
                .units
                .iter()
                .map(|unit| (unit.unit_key.as_str(), unit))
                .collect::<BTreeMap<_, _>>()
        })
        .unwrap_or_default();
    let mut units = response
        .updated_units
        .iter()
        .chain(response.added_units.iter())
        .map(|unit| {
            let prepared = prepared
                .get(unit.unit_key.as_str())
                .ok_or_else(|| KcsError::schema("adapter returned unknown unit"))?;
            Ok(NormalizedUnitObject {
                unit_key: unit.unit_key.clone(),
                unit_type: prepared.unit_type,
                raw_hash: raw_hash.to_owned(),
                prepared_hash: prepared.prepared_hash.clone(),
                tool_profile_hash: tool_profile_hash.to_owned(),
                gen: 0,
                mode,
                markdown: unit.markdown.clone(),
                reused_from: None,
                generated_at: generated_at.to_owned(),
            })
        })
        .collect::<Result<Vec<_>>>()?;
    for unit_key in &response.unchanged_unit_keys {
        let prepared = prepared
            .get(unit_key.as_str())
            .ok_or_else(|| KcsError::schema("adapter returned unknown unchanged unit"))?;
        let previous_unit = previous_units
            .get(unit_key.as_str())
            .ok_or_else(|| KcsError::schema("unchanged unit has no previous normalized unit"))?;
        units.push(NormalizedUnitObject {
            unit_key: unit_key.clone(),
            unit_type: prepared.unit_type,
            raw_hash: raw_hash.to_owned(),
            prepared_hash: prepared.prepared_hash.clone(),
            tool_profile_hash: tool_profile_hash.to_owned(),
            gen: 0,
            mode,
            markdown: previous_unit.markdown.clone(),
            reused_from: Some(kcs_pipeline::markdownize::ReusedFrom {
                raw_hash: previous_unit.raw_hash.clone(),
                gen: previous_unit.gen,
                unit_key: previous_unit.unit_key.clone(),
            }),
            generated_at: generated_at.to_owned(),
        });
    }
    units.sort_by_key(|unit| {
        prepared
            .get(unit.unit_key.as_str())
            .map(|unit| unit.order)
            .unwrap_or(u64::MAX)
    });
    Ok(units)
}

fn manifest_from_units(
    prepared_units: &[PreparedUnit],
    units: &[NormalizedUnitObject],
    raw_hash: &str,
    tool_profile_hash: &str,
    parent_gen: Option<u64>,
    run_id: &str,
    generated_at: &str,
) -> NormalizedInstanceManifest {
    let done = units
        .iter()
        .map(|unit| unit.unit_key.as_str())
        .collect::<BTreeSet<_>>();
    NormalizedInstanceManifest {
        raw_hash: raw_hash.to_owned(),
        tool_profile_hash: tool_profile_hash.to_owned(),
        gen: 0,
        parent_gen,
        run_id: run_id.to_owned(),
        units: prepared_units
            .iter()
            .map(|unit| NormalizedUnitManifestEntry {
                order: unit.order,
                unit_key: unit.unit_key.clone(),
                unit_ref: unit_ref(&unit.unit_key),
                unit_type: unit.unit_type,
                status: if done.contains(unit.unit_key.as_str()) {
                    UnitStatus::Done
                } else {
                    UnitStatus::Failed
                },
                prepared_hash: unit.prepared_hash.clone(),
                error_kind: (!done.contains(unit.unit_key.as_str()))
                    .then(|| "missing_output".to_owned()),
            })
            .collect(),
        generated_at: generated_at.to_owned(),
    }
}

#[allow(clippy::too_many_arguments)]
fn enqueue_online_placeholder_task(
    repo: &Repository,
    task_store: &TaskStore,
    candidate: &ScanCandidate,
    raw_hash: &str,
    scope_id: &str,
    network_allowed: bool,
    args: &IndexArgs,
    created_at: &str,
    result: &mut IndexPipelineResult,
    cost_ledger: &CostLedger,
    budget_caps: &BudgetCaps,
    month: &str,
) -> Result<()> {
    let output_ref = "online:mistral_ocr_markdownize";
    // Idempotency (Step2c I1, 04 §5.5): never enqueue a second online task for an
    // identity `(input_path, input_hash)` that already has an online task in any
    // live lifecycle state. Without the completed-state check, every unchanged
    // re-index appended a fresh task, and a later `batch resume` re-sent it to
    // the API and double-charged the ledger. A changed file produces a new
    // `input_hash`, so it still enqueues.
    //
    // The online task is identified differently across its lifecycle:
    //   * Pending/Paused (not yet executed) still carries the placeholder
    //     `output_ref`.
    //   * Done/Partial (executed) has had its `output_ref` rewritten to the
    //     normalized-instance path, but `execute_online_markdownize_task`
    //     stamps `fallback_reason = "online_adapter_done"`.
    //   * Failed/Running are also deduped: re-enqueueing a fresh Pending task
    //     (next_retry_at = None) would bypass the retry backoff gate and cause
    //     an extra API call. Failed tasks are owned by `kcs batch retry`, which
    //     honors `next_retry_at` and the per-error retry budget.
    if let Some(existing) = task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .find(|task| {
            if task.input_path != candidate.input_path || task.input_hash != raw_hash {
                return false;
            }
            match task.status {
                TaskStatus::Pending | TaskStatus::Paused => task.output_ref == output_ref,
                TaskStatus::Done | TaskStatus::Partial => {
                    task.fallback_reason.as_deref() == Some("online_adapter_done")
                }
                TaskStatus::Failed | TaskStatus::Running => task.output_ref == output_ref,
            }
        })
    {
        match existing.status {
            TaskStatus::Paused => result.paused_tasks += 1,
            TaskStatus::Pending => result.pending_online_tasks += 1,
            _ => {}
        }
        return Ok(());
    }

    let estimate = BudgetEstimate {
        scope_id: scope_id.to_owned(),
        task_type: TaskType::Markdownize,
        estimated_usd: estimate_online_markdownize_cost(candidate.size_bytes),
        adapter_id: Some("mistral_ocr_markdownize".to_owned()),
    };
    let (device_remaining, folder_remaining) = budget_remaining_for_adapter(
        cost_ledger,
        budget_caps,
        month,
        scope_id,
        adapter_kind_for_budget(estimate.adapter_id.as_deref()),
    )?;
    let budget = evaluate_budget_with_caps(
        &estimate,
        device_remaining,
        folder_remaining,
        matches_batch_override(args),
    );
    let (status, reason) = if !budget.allowed {
        (TaskStatus::Paused, Some("budget_exceeded"))
    } else if !network_allowed {
        (TaskStatus::Pending, Some("network_opt_in_required"))
    } else {
        (TaskStatus::Pending, Some("ready_for_online_adapter"))
    };
    let task = task_descriptor(
        repo,
        TaskType::Markdownize,
        Some(MarkdownizeMode::Full),
        candidate,
        raw_hash,
        output_ref,
        status,
        reason,
        created_at,
    );
    task_store.append(&task).map_err(pipeline_to_kcs)?;
    match status {
        TaskStatus::Paused => result.paused_tasks += 1,
        TaskStatus::Pending => result.pending_online_tasks += 1,
        _ => {}
    }
    Ok(())
}

fn matches_batch_override(_args: &IndexArgs) -> bool {
    false
}

fn budget_remaining_for_adapter(
    cost_ledger: &CostLedger,
    budget_caps: &BudgetCaps,
    month: &str,
    scope_id: &str,
    adapter_kind: &str,
) -> Result<(f64, Option<f64>)> {
    let device_spent = cost_ledger
        .monthly_total(month, None)
        .map_err(pipeline_to_kcs)?;
    let folder_spent = cost_ledger
        .monthly_total(month, Some(scope_id))
        .map_err(pipeline_to_kcs)?;
    let device_adapter_spent = cost_ledger
        .monthly_total_for_adapter(month, None, Some(adapter_kind))
        .map_err(pipeline_to_kcs)?;
    let folder_adapter_spent = cost_ledger
        .monthly_total_for_adapter(month, Some(scope_id), Some(adapter_kind))
        .map_err(pipeline_to_kcs)?;
    let mut device_remaining = budget_caps.device_monthly_usd_cap - device_spent;
    if let Some(adapter_cap) = budget_caps.device_per_adapter.get(adapter_kind) {
        device_remaining = device_remaining.min(adapter_cap - device_adapter_spent);
    }
    let mut folder_remaining = budget_caps
        .folder_monthly_usd_cap
        .map(|cap| cap - folder_spent);
    if let Some(adapter_cap) = budget_caps.folder_per_adapter.get(adapter_kind) {
        let adapter_remaining = adapter_cap - folder_adapter_spent;
        folder_remaining = Some(
            folder_remaining
                .map(|remaining| remaining.min(adapter_remaining))
                .unwrap_or(adapter_remaining),
        );
    }
    Ok((device_remaining, folder_remaining))
}

fn adapter_kind_for_budget(adapter_id: Option<&str>) -> &'static str {
    match adapter_id {
        Some("mistral_ocr_markdownize") | Some("deterministic_builtin") => "markdown",
        Some("gemini_multimodal_embedding") => "embedding",
        _ => "markdown",
    }
}

fn materialize_tool_lock(repo: &Repository) -> Result<()> {
    let prepare_hash =
        tool_profile_hash(&deterministic_prepare_profile_value()).map_err(adapter_to_kcs)?;
    let markdown_profile = active_markdown_adapter(repo).profile();
    let value = json!({
        "spec_version": 1,
        "prepare": {
            "tool_id": "prepare_default",
            "profile_hash": prepare_hash,
            "kind": "deterministic_library"
        },
        "markdown": {
            "tool_id": markdown_profile.adapter_id,
            "profile_hash": markdown_profile.tool_profile_hash,
            "kind": execution_mode_name(markdown_profile.execution_mode),
            "capabilities": markdown_profile.capability_flags
        }
    });
    let path = repo.kcs_dir().join("tool-lock.json");
    let bytes =
        serde_json::to_vec_pretty(&value).map_err(|err| KcsError::schema(err.to_string()))?;
    fs::write(&path, bytes).map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
}

fn execution_mode_name(mode: ExecutionMode) -> &'static str {
    match mode {
        ExecutionMode::OnlineApi => "online_api",
        ExecutionMode::OfflineApi => "offline_api",
        ExecutionMode::DeterministicLibrary => "deterministic_library",
    }
}

fn approval_exists(repo: &Repository) -> Result<bool> {
    Ok(repo.kcs_dir().join("approvals.jsonl").is_file())
}

fn network_allowed(repo: &Repository, args: &IndexArgs) -> Result<bool> {
    if args.offline {
        return Ok(false);
    }
    if network_revoked(repo)? {
        return Ok(false);
    }
    if args.online {
        return approval_exists(repo);
    }
    if args.approve {
        return Ok(true);
    }
    if read_allow_network_config(&repo.kcs_dir().join("config.toml"))? == Some(true)
        || read_allow_network_config(&user_config_toml_path())? == Some(true)
    {
        return Ok(true);
    }
    let path = repo.kcs_dir().join("approvals.jsonl");
    let Ok(text) = fs::read_to_string(&path) else {
        return Ok(false);
    };
    Ok(text
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .any(|value| {
            value.get("tool_id").and_then(Value::as_str) == Some("mistral_ocr_markdownize")
                && value.get("execution_mode").and_then(Value::as_str) == Some("online_api")
                && value.get("network_opt_in").and_then(Value::as_bool) == Some(true)
        }))
}

fn network_revoked(repo: &Repository) -> Result<bool> {
    // Revocation is persisted as `allow_network = false` in config.toml by
    // `write_network_revoke_record`; the audit trail lives in
    // `network-revoked.jsonl`. There is no extensionless `network-revoked`
    // sentinel file, so no such probe here (Step2c I5).
    Ok(read_allow_network_config(&repo.kcs_dir().join("config.toml"))? == Some(false))
}

fn read_allow_network_config(path: &Path) -> Result<Option<bool>> {
    let Ok(text) = fs::read_to_string(path) else {
        return Ok(None);
    };
    let value: toml::Value =
        toml::from_str(&text).map_err(|err| KcsError::schema(err.to_string()))?;
    Ok(value
        .get("adapter")
        .and_then(|adapter| adapter.get("policy"))
        .and_then(|policy| policy.get("allow_network"))
        .and_then(toml::Value::as_bool))
}

fn write_network_revoke_record(repo: &Repository) -> Result<()> {
    let config_path = repo.kcs_dir().join("config.toml");
    let mut value = match fs::read_to_string(&config_path) {
        Ok(text) => {
            toml::from_str::<toml::Value>(&text).map_err(|err| KcsError::schema(err.to_string()))?
        }
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {
            toml::Value::Table(toml::map::Map::new())
        }
        Err(err) => {
            return Err(KcsError::io(
                err.to_string(),
                config_path.display().to_string(),
            ));
        }
    };
    set_allow_network_false(&mut value);
    let text = toml::to_string_pretty(&value).map_err(|err| KcsError::schema(err.to_string()))?;
    fs::write(&config_path, text)
        .map_err(|err| KcsError::io(err.to_string(), config_path.display().to_string()))?;
    let path = repo.kcs_dir().join("network-revoked.jsonl");
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    serde_json::to_writer(
        &mut file,
        &json!({
            "recorded_at": now_utc_seconds(),
            "tool_id": "mistral_ocr_markdownize",
            "execution_mode": "online_api",
            "allow_network": false,
        }),
    )
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    file.write_all(b"\n")
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
}

fn set_allow_network_false(value: &mut toml::Value) {
    if !value.is_table() {
        *value = toml::Value::Table(toml::map::Map::new());
    }
    let root = value.as_table_mut().expect("value was normalized to table");
    let adapter = root
        .entry("adapter".to_owned())
        .or_insert_with(|| toml::Value::Table(toml::map::Map::new()));
    if !adapter.is_table() {
        *adapter = toml::Value::Table(toml::map::Map::new());
    }
    let adapter = adapter.as_table_mut().expect("adapter table");
    let policy = adapter
        .entry("policy".to_owned())
        .or_insert_with(|| toml::Value::Table(toml::map::Map::new()));
    if !policy.is_table() {
        *policy = toml::Value::Table(toml::map::Map::new());
    }
    policy
        .as_table_mut()
        .expect("policy table")
        .insert("allow_network".to_owned(), toml::Value::Boolean(false));
}

fn record_quarantine_candidates(repo: &Repository, preview: &ScanPreview) -> Result<()> {
    let path = repo.kcs_dir().join("quarantine.jsonl");
    let existing = read_quarantine_records(repo)?
        .into_iter()
        .filter_map(|entry| entry.get("path").and_then(Value::as_str).map(str::to_owned))
        .collect::<BTreeSet<_>>();
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    for candidate in &preview.candidates {
        if candidate.ignored
            && candidate.quarantine_reason.as_deref() == Some("secrets_tier_a_excluded")
            && !existing.contains(&candidate.input_path)
        {
            let record = json!({
                "path": candidate.input_path,
                "reason": "secrets_tier_a",
                "recorded_at": now_utc_seconds(),
                "approval_method": "quarantine",
            });
            serde_json::to_writer(&mut file, &record)
                .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
            file.write_all(b"\n")
                .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        }
    }
    Ok(())
}

fn read_quarantine_records(repo: &Repository) -> Result<Vec<Value>> {
    let path = repo.kcs_dir().join("quarantine.jsonl");
    let Ok(text) = fs::read_to_string(&path) else {
        return Ok(Vec::new());
    };
    Ok(text
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .collect())
}

fn write_approval_record(
    repo: &Repository,
    preview: &ScanPreview,
    approval_method: &str,
    network_opt_in: bool,
) -> Result<()> {
    let path = repo.kcs_dir().join("approvals.jsonl");
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    let record = json!({
        "scope_id": preview.scope_id,
        "root_path": repo.root(),
        "approved_at": now_utc_seconds(),
        "actor": std::env::var("USER").unwrap_or_else(|_| "unknown".to_owned()),
        "approval_method": approval_method,
        "kcs_version": env!("CARGO_PKG_VERSION"),
        "effective_ignore_hash": hash_bytes(b"built-in-tier-a-v1"),
        "estimated_file_count": preview.candidates.iter().filter(|candidate| !candidate.ignored).count(),
        "estimated_size_bytes": preview.candidates.iter().filter(|candidate| !candidate.ignored).map(|candidate| candidate.size_bytes).sum::<u64>(),
        "network_opt_in": network_opt_in,
        "tool_id": "mistral_ocr_markdownize",
        "execution_mode": "online_api",
    });
    serde_json::to_writer(&mut file, &record)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    file.write_all(b"\n")
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
}

fn validate_user_tools_config() -> Result<()> {
    let Some(path) = user_tools_toml_path() else {
        return Ok(());
    };
    if !path.is_file() {
        return Ok(());
    }
    let bytes =
        fs::read(&path).map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    validate_tools_toml(&bytes).map_err(adapter_to_kcs)
}

fn validate_repo_tool_lock(repo: &Repository) -> Result<()> {
    let path = repo.kcs_dir().join("tool-lock.json");
    if !path.is_file() {
        return Ok(());
    }
    let bytes =
        fs::read(&path).map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    load_tool_lock(&bytes).map(|_| ()).map_err(adapter_to_kcs)
}

fn user_tools_toml_path() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("XDG_CONFIG_HOME") {
        return Some(PathBuf::from(path).join("kcs/tools.toml"));
    }
    std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".config/kcs/tools.toml"))
}

fn user_config_toml_path() -> PathBuf {
    if let Some(path) = std::env::var_os("XDG_CONFIG_HOME") {
        return PathBuf::from(path).join("kcs/config.toml");
    }
    std::env::var_os("HOME")
        .map(|home| PathBuf::from(home).join(".config/kcs/config.toml"))
        .unwrap_or_else(|| PathBuf::from(".config/kcs/config.toml"))
}

fn data_home() -> PathBuf {
    if let Some(path) = std::env::var_os("XDG_DATA_HOME") {
        return PathBuf::from(path);
    }
    if let Some(home) = std::env::var_os("HOME") {
        return PathBuf::from(home).join(".local/share");
    }
    PathBuf::from(".")
}

fn cost_ledger_path() -> PathBuf {
    data_home().join("kcs/cost-ledger.jsonl")
}

fn adapter_to_kcs(error: kcs_adapter::AdapterError) -> KcsError {
    KcsError::schema(error.to_string())
}

fn pipeline_to_kcs(error: kcs_pipeline::PipelineError) -> KcsError {
    KcsError::schema(error.to_string())
}

fn print_output(value: Value, json_mode: bool) {
    if json_mode {
        println!(
            "{}",
            serde_json::to_string(&value).expect("serializing command output cannot fail")
        );
        return;
    }

    if let Some(status) = value.get("status").and_then(Value::as_str) {
        println!("{status}");
    } else if let Some(commits) = value.get("commits").and_then(Value::as_array) {
        for commit in commits {
            println!(
                "{} {} {}",
                commit["commit_hash"].as_str().unwrap_or_default(),
                commit["created_at"].as_str().unwrap_or_default(),
                commit["message"].as_str().unwrap_or_default()
            );
        }
    } else if let Some(changes) = value.get("changes").and_then(Value::as_array) {
        for change in changes {
            println!(
                "{} {}",
                change["change"].as_str().unwrap_or_default(),
                change["relative_path"].as_str().unwrap_or_default()
            );
        }
    } else if let Some(files) = value.get("files").and_then(Value::as_array) {
        for file in files {
            println!(
                "{} {}",
                file["status"].as_str().unwrap_or_default(),
                file["relative_path"].as_str().unwrap_or_default()
            );
        }
    } else {
        println!(
            "{}",
            serde_json::to_string_pretty(&value).expect("serializing command output cannot fail")
        );
    }
}

fn print_error(error: &KcsError, json_mode: bool) {
    if json_mode {
        eprintln!(
            "{}",
            serde_json::to_string(&error.to_error_json())
                .expect("serializing command error cannot fail")
        );
    } else {
        eprintln!("{}: {}", error.error_code(), error.message());
    }
}

#[cfg(test)]
mod tests {
    use clap::Parser;

    use super::{command_captured_json_flag, Cli, Command};

    #[test]
    fn parses_global_json_after_command() {
        let cli = Cli::try_parse_from(["kcs", "status", "--json"]).unwrap();

        assert!(cli.json);
        assert!(matches!(cli.command, Command::Status));
    }

    #[test]
    fn parses_commit_alias_as_snapshot() {
        let cli = Cli::try_parse_from(["kcs", "commit", "-m", "initial"]).unwrap();

        let Command::Snapshot(args) = cli.command else {
            panic!("expected snapshot command");
        };
        assert_eq!(args.message.as_deref(), Some("initial"));
    }

    #[test]
    fn parses_snapshot_create_canonical_form() {
        let cli = Cli::try_parse_from(["kcs", "snapshot", "create", "-m", "x"]).unwrap();

        let Command::Snapshot(args) = cli.command else {
            panic!("expected snapshot command");
        };
        assert_eq!(args.action.as_deref(), Some("create"));
    }

    #[test]
    fn rejects_invalid_usage() {
        assert!(Cli::try_parse_from(["kcs", "diff", "a"]).is_err());
        assert!(Cli::try_parse_from(["kcs", "nonsense"]).is_err());
    }

    #[test]
    fn parses_out_of_scope_commands_as_placeholders() {
        let cli = Cli::try_parse_from(["kcs", "search", "query", "--json"]).unwrap();
        assert!(command_captured_json_flag(&cli.command));
        assert!(Cli::try_parse_from(["kcs", "index", "--preview"]).is_ok());
    }
}
