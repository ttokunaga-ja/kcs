use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{IsTerminal, Write};
use std::path::{Path, PathBuf};
use std::process;

use clap::{Args, Parser, Subcommand};
use kcs_adapter::deterministic::{
    deterministic_markdown_profile_value, deterministic_prepare_profile_value, DeterministicAdapter,
};
use kcs_adapter::identity::tool_profile_hash;
use kcs_adapter::tool_lock::{load_tool_lock, validate_tools_toml};
use kcs_adapter::traits::MarkdownizeAdapter;
use kcs_adapter::types::{
    MarkdownizeMode as AdapterMarkdownizeMode, MarkdownizeRequest, PreparedUnitHint, RawInput,
    UnitKind,
};
use kcs_core::dag::NormalizeRef;
use kcs_core::scope::{
    append_error_log, append_event_log, new_ulid, now_utc_seconds, InspectedObject, Repository,
};
use kcs_core::{ExitCode, KcsError, Result};
use kcs_pipeline::budget::{
    estimate_local_baseline_cost, evaluate_budget_with_caps, read_budget_caps, utc_month,
    BudgetEstimate, CostLedger, MonthlyCostLedgerEntry,
};
use kcs_pipeline::markdownize::{
    choose_markdownize_mode, persist_normalized_instance, validate_markdownize_response,
    IncrementalHints, IncrementalModeInput, MarkdownizeMode, NormalizedInstanceManifest,
    NormalizedUnitManifestEntry, NormalizedUnitObject, UnitStatus,
};
use kcs_pipeline::prepare::{
    hash_bytes, prepare_units, unit_ref, PrepareStageRequest, PreparedUnit, UnitType,
};
use kcs_pipeline::scan::{build_scan_preview, ScanCandidate, ScanPreview, ScanPreviewRequest};
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
    if !approved && !args.approve && !args.yes && !args.online {
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
            args.approve || args.online,
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
    Ok(json!({
        "status": if outcome.noop { "noop" } else { "indexed" },
        "approval_method": if args.approve { "approve" } else if args.yes { "yes" } else { "existing" },
        "network_opt_in": index_result.network_allowed,
        "pending_online_tasks": index_result.pending_online_tasks,
        "paused_tasks": index_result.paused_tasks,
        "normalized_files": index_result.normalized_files,
        "pending_files": index_result.pending_files,
        "tree_hash": outcome.tree_hash,
        "commit_hash": outcome.commit_hash,
        "commit": outcome.commit,
    }))
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
            Ok(json!({
                "status": "resumed",
                "override_budget": resume.override_budget,
                "tasks_updated": changed,
            }))
        }
        Some(BatchCommand::Retry) => {
            let changed = store
                .update_matching(|task| {
                    if task.status == TaskStatus::Failed {
                        task.status = TaskStatus::Pending;
                        task.attempts = task.attempts.saturating_add(1);
                        true
                    } else {
                        false
                    }
                })
                .map_err(pipeline_to_kcs)?;
            Ok(json!({ "status": "retry scheduled", "tasks_updated": changed }))
        }
        None => Err(KcsError::not_implemented("batch command")),
    }
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
    let markdown_profile_hash =
        tool_profile_hash(&deterministic_markdown_profile_value()).map_err(adapter_to_kcs)?;
    let markdown_adapter = DeterministicAdapter;
    let markdown_profile = markdown_adapter.profile();
    let network_allowed = network_allowed(repo, args)?;
    let cost_ledger = CostLedger::new(data_home().join("kcs/cost-ledger.jsonl"));
    let (device_cap, folder_cap) =
        read_budget_caps(repo.kcs_dir().join("config.toml")).map_err(pipeline_to_kcs)?;
    let month = utc_month(&now);
    let device_spent = cost_ledger
        .monthly_total(&month, None)
        .map_err(pipeline_to_kcs)?;
    let folder_spent = cost_ledger
        .monthly_total(&month, Some(&scope_id))
        .map_err(pipeline_to_kcs)?;

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

        write_prepared_objects(repo, &prepare.prepared_object_hashes, &bytes)?;

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
                device_cap,
                folder_cap,
                device_spent,
                folder_spent,
            )?;
            continue;
        }

        let mode_decision = choose_markdownize_mode(&IncrementalModeInput {
            has_previous_done_run: has_previous_done_task(&task_store, &candidate.input_path)?,
            raw_hash_only_changed: true,
            adapter_capabilities: markdown_profile.capability_flags.clone(),
            change_rate: 0.0,
            threshold: 0.30,
            consecutive_incremental_count: 0,
            max_consecutive_incremental: 5,
        });
        let mode = mode_decision.mode;
        let hints = prepared_unit_hints(&prepare.prepared_units);
        let request = MarkdownizeRequest {
            raw: RawInput {
                raw_hash: raw_hash.clone(),
                path: Some(path.display().to_string()),
            },
            media_type: candidate.media_type.clone(),
            prepared_unit_hint: Some(hints),
            mode: adapter_mode(mode),
            previous: None,
            hints: None,
            tool_profile_hash: markdown_profile_hash.clone(),
            spec_version: 1,
        };

        let mut response = markdown_adapter
            .markdownize(request.clone())
            .map_err(adapter_to_kcs)?;
        if response.fallback_to_full {
            let mut full_request = request;
            full_request.mode = AdapterMarkdownizeMode::Full;
            response = markdown_adapter
                .markdownize(full_request)
                .map_err(adapter_to_kcs)?;
        }
        let empty_hints = IncrementalHints {
            changed_unit_keys: prepare
                .prepared_units
                .iter()
                .map(|unit| unit.unit_key.clone())
                .collect(),
            added_unit_keys: Vec::new(),
            removed_unit_keys: Vec::new(),
            page_fingerprints: BTreeMap::new(),
        };
        validate_markdownize_response(&response, &empty_hints, &prepare.prepared_units)
            .map_err(pipeline_to_kcs)?;

        let generated_at = now_utc_seconds();
        let run_id = format!("run_{}", new_ulid(repo.root()));
        let units = normalized_units_from_response(
            &response,
            &prepare.prepared_units,
            &raw_hash,
            &markdown_profile_hash,
            mode,
            &generated_at,
        )?;
        let manifest = manifest_from_units(
            &prepare.prepared_units,
            &units,
            &raw_hash,
            &markdown_profile_hash,
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
            mode_decision.reason.as_deref(),
            &generated_at,
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
            device_cap,
            folder_cap,
            device_spent,
            folder_spent,
        )?;
    }
    Ok(result)
}

fn write_prepared_objects(
    repo: &Repository,
    prepared_hashes: &[String],
    bytes: &[u8],
) -> Result<()> {
    for prepared_hash in prepared_hashes {
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
            fs::write(&path, bytes)
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

fn normalized_units_from_response(
    response: &kcs_adapter::types::MarkdownizeResponse,
    prepared_units: &[PreparedUnit],
    raw_hash: &str,
    tool_profile_hash: &str,
    mode: MarkdownizeMode,
    generated_at: &str,
) -> Result<Vec<NormalizedUnitObject>> {
    let prepared = prepared_units
        .iter()
        .map(|unit| (unit.unit_key.as_str(), unit))
        .collect::<BTreeMap<_, _>>();
    response
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
        .collect()
}

fn manifest_from_units(
    prepared_units: &[PreparedUnit],
    units: &[NormalizedUnitObject],
    raw_hash: &str,
    tool_profile_hash: &str,
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
        parent_gen: None,
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

fn has_previous_done_task(task_store: &TaskStore, input_path: &str) -> Result<bool> {
    Ok(task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .iter()
        .any(|task| task.input_path == input_path && task.status == TaskStatus::Done))
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
    device_cap: Option<f64>,
    folder_cap: Option<f64>,
    device_spent: f64,
    folder_spent: f64,
) -> Result<()> {
    let output_ref = "online:mistral_ocr_markdownize";
    if let Some(existing) = task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .find(|task| {
            task.input_path == candidate.input_path
                && task.input_hash == raw_hash
                && task.output_ref == output_ref
                && matches!(task.status, TaskStatus::Pending | TaskStatus::Paused)
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
        estimated_usd: estimate_local_baseline_cost(candidate.size_bytes) * 10.0,
        adapter_id: Some("mistral_ocr_markdownize".to_owned()),
    };
    let device_remaining = device_cap.map_or(f64::INFINITY, |cap| cap - device_spent);
    let folder_remaining = folder_cap.map(|cap| cap - folder_spent);
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

fn materialize_tool_lock(repo: &Repository) -> Result<()> {
    let prepare_hash =
        tool_profile_hash(&deterministic_prepare_profile_value()).map_err(adapter_to_kcs)?;
    let markdown_hash =
        tool_profile_hash(&deterministic_markdown_profile_value()).map_err(adapter_to_kcs)?;
    let value = json!({
        "spec_version": 1,
        "prepare": {
            "tool_id": "prepare_default",
            "profile_hash": prepare_hash,
            "kind": "deterministic_library"
        },
        "markdown": {
            "tool_id": "deterministic_builtin",
            "profile_hash": markdown_hash,
            "kind": "deterministic_library",
            "capabilities": ["baseline", "text_passthrough"]
        }
    });
    let path = repo.kcs_dir().join("tool-lock.json");
    let bytes =
        serde_json::to_vec_pretty(&value).map_err(|err| KcsError::schema(err.to_string()))?;
    fs::write(&path, bytes).map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
}

fn approval_exists(repo: &Repository) -> Result<bool> {
    Ok(repo.kcs_dir().join("approvals.jsonl").is_file())
}

fn network_allowed(repo: &Repository, args: &IndexArgs) -> Result<bool> {
    if args.offline {
        return Ok(false);
    }
    if args.online || args.approve {
        return Ok(true);
    }
    if network_revoked(repo)? {
        return Ok(false);
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
    Ok(repo.kcs_dir().join("network-revoked").is_file())
}

fn write_network_revoke_record(repo: &Repository) -> Result<()> {
    let path = repo.kcs_dir().join("network-revoked");
    fs::write(&path, now_utc_seconds())
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
}

fn record_quarantine_candidates(repo: &Repository, preview: &ScanPreview) -> Result<()> {
    let path = repo.kcs_dir().join("quarantine.jsonl");
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    for candidate in &preview.candidates {
        if candidate.ignored
            && candidate.quarantine_reason.as_deref() == Some("secrets_tier_a_excluded")
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

fn data_home() -> PathBuf {
    if let Some(path) = std::env::var_os("XDG_DATA_HOME") {
        return PathBuf::from(path);
    }
    if let Some(home) = std::env::var_os("HOME") {
        return PathBuf::from(home).join(".local/share");
    }
    PathBuf::from(".")
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
