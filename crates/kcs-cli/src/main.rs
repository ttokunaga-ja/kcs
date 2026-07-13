mod historical_reindex;
mod ocr_discovery;
mod online_task;
mod promotion;
mod purge;
mod restore;
mod search_history;
mod search_time;
mod verify_objects;

use crate::historical_reindex::{retained_history_instances, RetainedNormalizedInstance};
use crate::ocr_discovery::{prepared_units_from_ocr_discovery, supports_ocr_from_scratch};
use crate::online_task::targets_standard_online_markdownize;

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{IsTerminal, Read, Write};
use std::path::{Path, PathBuf};
use std::process;
use std::time::Instant;

use clap::{Args, Parser, Subcommand};
use kcs_adapter::catalog::{
    active_adopted_embedding_execution, adopted_embedding_profile,
    builtin_offline_markdownize_adapter, builtin_prepare_profile,
    declared_adopted_embedding_profile, resolve_standard_online_markdownize_profile_with_bbox,
    run_adopted_embedding, run_standard_online_markdownize_with_bytes,
    standard_online_markdownize_profile, standard_online_markdownize_profile_with_bbox,
    AdoptedEmbeddingExecution, DeclaredEmbeddingProfile, StandardOnlineMarkdownizeRequest,
};
use kcs_adapter::identity::tool_profile_hash;
use kcs_adapter::tool_lock::{load_tool_lock, validate_tools_toml};
use kcs_adapter::traits::MarkdownizeAdapter;
use kcs_adapter::types::{
    AdapterKind, AdapterProfile, EmbeddingInputType, EmbeddingItem, ExecutionMode, MarkdownUnit,
    MarkdownizeMode as AdapterMarkdownizeMode, MarkdownizeRequest, PreparedUnitHint,
    PreviousMarkdownizeContext, RawInput, UnitKind,
};
use kcs_core::cas::{
    fanout_path, hash_path_component, is_hash, read_bounded_regular_file, ChunkObject, ObjectStore,
    MAX_RAW_OBJECT_BYTES,
};
use kcs_core::dag::{CommitType, NormalizeRef, TreeObject};
use kcs_core::history::{HistoryReader, TreeBinding};
use kcs_core::portable::{portable_cache_leaf, portable_tag_leaf, PORTABLE_TAGS_DIRECTORY};
use kcs_core::purge::PurgeState;
use kcs_core::schema::{validate_json_schema, SchemaKind};
use kcs_core::scope::{
    append_error_log, append_event_log, append_warn_log, new_ulid, now_utc_seconds,
    InspectedObject, PendingNormalizeRef, Repository, StoreLock, DEFAULT_MAX_ARCHIVE_SCOPE_BYTES,
};
use kcs_core::{ExitCode, KcsError, Result};
use kcs_index::chunking::{
    chunk_normalized_instance, ChunkingConfig, ChunkingInput, NormalizedUnitInput,
};
use kcs_index::embedding_store::{self, f32_to_le_bytes};
use kcs_index::fts::{FtsSchemaConfig, FtsTokenizer, SqliteFtsIndex, CHUNK_VEC_DIMENSIONS};
use kcs_index::registry::{RegistryDb, RegistryEntry};
use kcs_index::{
    ChunkRow, EmbeddingDistance, EmbeddingModality, EmbeddingTargetType, TreeEntryRow,
};
use kcs_pipeline::budget::{
    budget_warning, estimate_local_baseline_cost, evaluate_budget_with_caps, read_budget_policy,
    utc_month, BudgetCapKind, BudgetCaps, BudgetEstimate, CostLedger, MonthlyCostLedgerEntry,
    ReservationRecord,
};
use kcs_pipeline::markdownize::{
    choose_markdownize_mode, load_validated_normalized_instance, persist_normalized_instance,
    validate_markdownize_response, IncrementalHints, IncrementalModeDecision, IncrementalModeInput,
    MarkdownizeMode, NormalizedInstanceManifest, NormalizedUnitManifestEntry, NormalizedUnitObject,
    UnitStatus,
};
use kcs_pipeline::prepare::{
    hash_bytes, map_units, pdf_text_pages_bounded, prepare_units_from_bytes, unit_ref,
    PrepareStageBytesRequest, PreparedUnit, UnitFingerprint, UnitType,
};
use kcs_pipeline::scan::{
    build_scan_preview, classify_secret, current_scan_policy_allows_file, hash_verified_scan_input,
    read_verified_scan_input, ScanCandidate, ScanPreview, ScanPreviewRequest,
};
use kcs_pipeline::task::{
    retry_policy, task_can_complete_from_materialized_output, task_can_enter_secret_hold,
    task_status_from_unit_counts, RetryErrorKind,
};
use kcs_pipeline::task::{
    validate_task_output_ref, TaskDescriptor, TaskOutputRef, TaskReservationClaim, TaskStatus,
    TaskStore, TaskType,
};
use kcs_pipeline::unsupported::{
    UnsupportedInputDisposition, UnsupportedInputStore, UNSUPPORTED_REASON_RESOLVED,
    UNSUPPORTED_REASON_UNRECOGNIZED_BINARY,
};
use kcs_search::cursor::{
    decode_cursor_token, encode_cursor_token, CursorExcludedScope, CursorToken, ScopeCursor,
    ScopeMode,
};
use kcs_search::evidence::{
    evidence_pointer_to_uri, issue_evidence_pointer, parse_evidence_pointer_uri, EvidencePointer,
    EvidencePointerIssueRequest, EVIDENCE_POINTER_SCHEMA_VERSION,
};
use kcs_search::mmr::{diversify_candidates, MmrCandidate, MmrConfig};
use kcs_search::query::{
    query_hash, ChunkingConfigBinding, DiversifyRequest, DiversifyStrategy, QueryHashInput,
    ScopeSelectionMode, SearchMode, TimeTravelSelector,
};
use kcs_search::rrf::{fuse_rrf, BackendRank, RrfConfig};
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use unicode_normalization::UnicodeNormalization;

use crate::promotion::{
    apply_online_promotion_to_index, clear_promotion_state, finish_pending_online_promotion,
    maybe_inject_promotion_fault, promote_completed_online_markdownize,
    recover_pending_online_promotion,
};
use crate::search_history::{
    current_history_plan_from_cache, exact_project_snapshot, install_eligible_identities,
    plan_search_history, SearchContentKey, SearchHistoryBinding,
};
use crate::search_time::{
    reconcile_cursor_selector, since_cutoff_utc, validate_cursor_cutoff, TimeSelector,
    TimeSelectorFlags,
};

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
    /// Rebuild local acceleration tables.
    Repair(UnsupportedArgs),
    /// Search indexed chunks.
    Search(UnsupportedArgs),
    /// Open an Evidence Pointer target.
    Open(UnsupportedArgs),
    /// View an Evidence Pointer target.
    View(UnsupportedArgs),
    /// Restore historical raw bytes to an explicit destination.
    Restore(RestoreArgs),
    /// Phase 4+ command placeholder.
    Gc(UnsupportedArgs),
    /// Remove content from KCS-managed history after preview and confirmation.
    Purge(purge::PurgeArgs),
    /// Reindex normalized instances.
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
struct RestoreArgs {
    source: String,
    #[arg(long)]
    to: PathBuf,
    #[arg(long)]
    force: bool,
    #[arg(long)]
    yes: bool,
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
    /// N1: explicit approval to lift the Tier B (secrets_tier_b_warning) online
    /// hold for this scope, allowing candidate-secret files to be sent to online
    /// adapters (markdownize + embedding). Distinct from `--approve` (which is the
    /// scan/network opt-in) — sending a probable-secret file needs its own
    /// consent. Persisted so `batch resume` honors it (decisions #45).
    #[arg(long)]
    send_secrets: bool,
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
    // Register the sqlite-vec `vec0` module before any connection opens, so
    // `chunk_vec` is available process-wide (04 §4.3, K4).
    kcs_index::vec::ensure_registered();
    let cli = match Cli::try_parse() {
        Ok(cli) => cli,
        Err(err) => exit_from_clap_error(err),
    };
    let json = cli.json || command_captured_json_flag(&cli.command);
    let exit_code = match run(cli) {
        Ok(mut output) => {
            // A command may request a non-zero success exit code (e.g. multi-scope
            // search partial failure returns its result JSON on stdout with exit 3,
            // 05 §1.8). The private `__exit_code` marker is stripped before printing.
            let code = take_exit_override(&mut output).unwrap_or(ExitCode::Success);
            // R12-4: a non-success exit that still prints result JSON (index/search
            // partial exit 3, enrichment auth exit 5, budget pause exit 6) went
            // through this Ok arm and so bypassed the Err arm's append_error_log —
            // auth failures / budget stops / scope exclusions never reached
            // errors.jsonl (docs/05:573 "all errors"). Reconstruct the reason from
            // the output and append it (append_error_log redacts).
            if code != ExitCode::Success {
                append_exit_override_error(&output, code);
            }
            print_output(output, json);
            code
        }
        Err(error) => {
            let _ = append_error_log(&error);
            print_error(&error, json);
            error.exit_code()
        }
    };
    process::exit(exit_code.code());
}

/// R11-1: `clap::Parser::parse()` calls `process::exit()` itself on a usage error,
/// bypassing the `--json` contract (docs/06 §4: *every* CLI has `--json` and errors
/// return `{error_code, message, context}`). Roughly half the commands take the
/// derive path (index/batch/diff/tag/snapshot/log/inspect…), so `kcs diff --json`
/// emitted plaintext + exit 2 with an empty stdout — invisible to a machine caller.
/// Route clap errors through `try_parse` instead: preserve clap's own exit code
/// (usage = 2, matching docs/06 §7), but when the raw argv requested `--json`, wrap
/// the reason in the same `KCS-E-CONFIG-USAGE-001` envelope the manual-parse
/// commands (repair/search/open/view/reindex) already emit. `--help` / `--version`
/// are clap "errors" that must still render to stdout and exit 0, so defer to clap.
fn exit_from_clap_error(err: clap::Error) -> ! {
    use clap::error::ErrorKind;
    if matches!(
        err.kind(),
        ErrorKind::DisplayHelp | ErrorKind::DisplayVersion
    ) {
        err.exit();
    }
    // A genuine usage error. clap's exit code is 2 for every non-help/version kind.
    let exit_code = err.exit_code();
    // R12-4: a clap usage error is still an error (docs/05:573 "all errors" belong
    // in errors.jsonl). append_error_log writes to the device data_home directly, so
    // it works even though `run()` (and its repo) never started.
    let _ = append_error_log(&KcsError::invalid_usage(clap_error_reason(&err)));
    let wants_json = std::env::args().skip(1).any(|arg| arg == "--json");
    if wants_json {
        print_error(&KcsError::invalid_usage(clap_error_reason(&err)), true);
        process::exit(exit_code);
    }
    // No --json: keep clap's native plaintext-to-stderr behavior unchanged.
    err.exit();
}

/// Extract a concise one-line reason from a clap error for the JSON envelope's
/// `message` field. clap's full render appends the usage block and help hints,
/// which do not belong in a machine `message`; take the first non-empty line and
/// drop the leading `error: ` prefix so it reads like the manual-parse messages.
fn clap_error_reason(err: &clap::Error) -> String {
    let rendered = err.to_string();
    let first_line = rendered
        .lines()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .unwrap_or("invalid usage");
    first_line
        .strip_prefix("error: ")
        .unwrap_or(first_line)
        .to_string()
}

/// Remove and interpret the private `__exit_code` marker a command may embed in
/// its success output to request a non-zero process exit while still printing the
/// payload to stdout (multi-scope search partial failure, 05 §1.8).
fn take_exit_override(output: &mut Value) -> Option<ExitCode> {
    let code = output.as_object_mut()?.remove("__exit_code")?.as_u64()?;
    match code {
        3 => Some(ExitCode::PartialFailure),
        4 => Some(ExitCode::PermanentFailure),
        // R11-2: enrichment auth (5) / budget-pause (6) for index/repair/reindex/batch.
        5 => Some(ExitCode::AuthError),
        6 => Some(ExitCode::BudgetExceeded),
        _ => None,
    }
}

/// R12-4: append the errors.jsonl line for a command that printed result JSON yet
/// requested a non-success exit via `__exit_code`. Reconstruct the error_code from
/// the output (explicit `error_code` for index partial; otherwise mapped from the
/// exit class) and carry `excluded_scopes` in context. `append_error_log` applies
/// redaction, so scope paths inside `excluded_scopes` are masked by default.
fn append_exit_override_error(output: &Value, code: ExitCode) {
    let error_code = output
        .get("error_code")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .unwrap_or_else(|| exit_override_error_code(code).to_owned());
    let mut context = json!({ "exit_code": code.code() });
    if let Some(excluded) = output.get("excluded_scopes") {
        if excluded.as_array().is_some_and(|array| !array.is_empty()) {
            if let Some(object) = context.as_object_mut() {
                object.insert("excluded_scopes".to_owned(), excluded.clone());
            }
        }
    }
    let _ = append_error_log(&KcsError::new(
        error_code,
        "command completed with a non-success exit code",
        context,
        code,
    ));
}

/// The observability error_code for a non-success exit override that carries no
/// explicit `error_code` field (auth/budget/partial). Used only for the log line;
/// the exit code itself is the machine contract.
fn exit_override_error_code(code: ExitCode) -> &'static str {
    match code {
        ExitCode::AuthError => "KCS-E-ADAPTER-AUTH-001",
        ExitCode::BudgetExceeded => "KCS-E-BUDGET-EXCEEDED-001",
        ExitCode::PartialFailure => "KCS-E-SEARCH-PARTIAL-001",
        ExitCode::PermanentFailure => "KCS-E-SEARCH-SCOPE-ALL-FAILED-001",
        _ => "KCS-E-INTERNAL-001",
    }
}

fn command_captured_json_flag(command: &Command) -> bool {
    match command {
        Command::Repair(args)
        | Command::Search(args)
        | Command::Open(args)
        | Command::View(args)
        | Command::Gc(args)
        | Command::Reindex(args)
        | Command::Move(args)
        | Command::Evidence(args) => args.args.iter().any(|arg| arg == "--json"),
        Command::Index(_) | Command::Batch(_) | Command::Purge(_) => false,
        Command::Init(_)
        | Command::Status
        | Command::Snapshot(_)
        | Command::Log(_)
        | Command::Diff(_)
        | Command::Inspect(_)
        | Command::Tag(_)
        | Command::Restore(_) => false,
    }
}

fn run(cli: Cli) -> Result<Value> {
    // R13-6: refuse to run if device-global state cannot resolve to an absolute
    // base dir (no absolute $HOME and no absolute $XDG_*), before any command
    // reads or writes the registry / logs / cost ledger / cursor-key.
    ensure_device_dirs_resolvable()?;
    validate_user_tools_config()?;
    validate_user_config()?;
    // R13-2: publish the declared `tools.toml` adapters so the online clients
    // resolve the declared `auth`/`model` (rather than hard-coded env vars) at
    // execution time. Done once, after validation, before any command dispatch.
    register_declared_adapters_from_tools_config();
    match cli.command {
        Command::Init(args) => {
            let path = args.path.unwrap_or_else(|| PathBuf::from("."));
            let kcs_dir = path.join(".kcs");
            let existed = kcs_dir.exists();
            // R13-5: a re-`init` on a broken store used to short-circuit to a bare
            // "already initialized" exit 0 without verifying or repairing anything —
            // e.g. a missing `.kcs/HEAD` stayed missing and the very next command
            // failed. Detect the recoverable damage BEFORE `init`→`open` self-heals
            // it (R13-4) so the user's natural recovery action reports the repair.
            // Unrecoverable corruption (bad scope.json/config) is surfaced by
            // `open`'s `validate` as a non-zero exit that points at `kcs repair`.
            let repaired = if existed {
                kcs_core::scope::empty_head_recovery_hash(&kcs_dir)
                    .ok()
                    .flatten()
                    .map(|_| vec!["HEAD".to_owned()])
                    .unwrap_or_default()
            } else {
                Vec::new()
            };
            let repo = Repository::init(&path)?;
            // Register the scope in the device-local registry so multi-scope search
            // can enumerate it (05 §1.8). `indexed=false` until `kcs index` runs.
            // The registry is a cache, never truth (03 §4): a write failure is a
            // warning, never a hard error.
            register_scope(&repo, false);
            let status = if !existed {
                "initialized"
            } else if repaired.is_empty() {
                "already initialized"
            } else {
                "repaired"
            };
            Ok(json!({
                "status": status,
                "repaired": repaired,
                "path": repo.root(),
                "kcs_path": repo.kcs_dir(),
            }))
        }
        Command::Status => {
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            let task_store = TaskStore::new(repo.kcs_dir());
            // R15-4: `status` is a pure read — a shallow HEAD (tree object gone)
            // degrades to listing files without a classification (`head_shallow`)
            // instead of dying on a raw KCS-E-STORE-NOT-FOUND-001.
            let status = repo.status()?;
            let (unsupported_inputs, unsupported_inputs_complete) = if status.head_shallow {
                UnsupportedInputStore::new(repo.kcs_dir())
                    .latest_by_path()
                    .map_err(pipeline_to_kcs)?;
                (Vec::new(), false)
            } else {
                (current_unsupported_inputs(&repo)?, true)
            };
            Ok(json!({
                "scope_path": repo.kcs_dir(),
                "files": status.files,
                "head_shallow": status.head_shallow,
                "tasks": task_store.all().map_err(pipeline_to_kcs)?,
                "quarantine": quarantine_status_records(&repo)?,
                "unsupported_inputs": unsupported_inputs,
                "unsupported_inputs_complete": unsupported_inputs_complete,
                "budget": budget_status_json(&repo)?,
            }))
        }
        Command::Snapshot(args) => {
            let _action = args.action;
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            // N2: a manual snapshot must exclude the same Tier A secrets `kcs index`
            // does, or `.env`/`*.pem` plaintext lands irreversibly in objects/raw and
            // the latest tree. Compute the exclusion set from the scan preview (the
            // shared classifier) and pass it through the filtered snapshot path.
            let preview = build_scan_preview(ScanPreviewRequest {
                scope_path: repo.root().display().to_string(),
                include_raw_hashes: false,
                require_network_approval: false,
            })
            .map_err(pipeline_to_kcs)?;
            let excluded = preview
                .candidates
                .iter()
                .filter(|candidate| candidate.ignored)
                .map(|candidate| candidate.input_path.clone())
                .collect::<BTreeSet<_>>();
            let explicitly_allowed_tier_a = explicitly_allowed_tier_a_paths(&preview);
            let outcome = repo.snapshot_filtered_with_policy(
                args.message.as_deref(),
                None,
                &excluded,
                &explicitly_allowed_tier_a,
            )?;
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
            // R16-1: `log` degrades on a missing ancestor commit — it returns the
            // healthy prefix from HEAD plus `truncated` rather than dying on a raw
            // KCS-E-STORE-NOT-FOUND-001.
            let report = repo.log()?;
            Ok(json!({ "commits": report.entries, "truncated": report.truncated }))
        }
        Command::Diff(args) => {
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            Ok(json!({ "changes": repo.diff(&args.a, &args.b)? }))
        }
        Command::Inspect(args) => {
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            let target = scope_target(repo.root())?;
            enforce_purge_read_barrier(&target, &args.hash)?;
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
                } => {
                    // Recheck after the metadata read so a barrier published in
                    // the inspect window cannot leak even the raw object's size.
                    enforce_purge_read_barrier(&target, &raw_hash)?;
                    Ok(json!({
                        "object_type": "raw",
                        "raw_hash": raw_hash,
                        "size_bytes": size_bytes,
                    }))
                }
            }
        }
        Command::Tag(args) => {
            let repo = Repository::open_current()?;
            validate_repo_tool_lock(&repo)?;
            let commit_hash = repo.tag(&args.name, args.commit.as_deref())?;
            Ok(json!({
                "tag": args.name,
                "commit_hash": commit_hash,
                "path": repo.kcs_dir().join("refs").join(PORTABLE_TAGS_DIRECTORY).join(portable_tag_leaf(&args.name)),
            }))
        }
        Command::Index(args) => run_index(args),
        Command::Batch(args) => run_batch(args),
        Command::Repair(args) => run_repair(args),
        Command::Search(args) => run_search(args),
        Command::Open(args) => run_open(args),
        Command::View(args) => run_view(args),
        Command::Reindex(args) => run_reindex(args),
        Command::Evidence(args) => verify_objects::run_evidence(args),
        Command::Restore(args) => restore::run(args),
        Command::Purge(args) => purge::run(args),
        Command::Gc(_) | Command::Move(_) => Err(KcsError::not_implemented("command")),
    }
}

fn run_index(args: IndexArgs) -> Result<Value> {
    if args.online && args.offline {
        return Err(KcsError::invalid_usage(
            "--online and --offline are mutually exclusive",
        ));
    }
    let repo = Repository::open_current()?;
    // M1(a): serialize the whole index command against concurrent index/repair/
    // reindex (05 §6). Held end-to-end, not just across the snapshot sub-step, so
    // two processes cannot interleave chunk writes / sqlite rebuilds. The lock is
    // reentrant, so the internal auto-snapshot re-acquisition does not deadlock.
    let _lock = repo.lock_store()?;
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
    // N1c: `--send-secrets` records the explicit Tier B online approval and lifts
    // any existing hold. Recorded BEFORE the pipeline so this run's Tier B online
    // tasks/embeddings are enqueued ready rather than held.
    if args.send_secrets {
        write_secrets_approval(&repo, &preview)?;
        release_secret_holds(&repo)?;
    }
    let secrets_approved = secrets_send_approved(&repo);
    record_quarantine_candidates(&repo, &preview, secrets_approved)?;

    if recover_pending_online_promotion(&repo)? {
        finish_pending_online_promotion(&repo)?;
    }
    materialize_tool_lock(&repo)?;
    let mut index_result = run_index_pipeline(&repo, &preview, &args)?;
    // A prior batch may already have produced a complete accepted online
    // instance. Overlay it before the one normal index snapshot so an ordinary
    // index neither demotes the file to the deterministic baseline nor creates a
    // second promotion commit.
    apply_online_promotion_to_index(&repo, &mut index_result)?;
    let excluded = preview
        .candidates
        .iter()
        .filter(|candidate| candidate.ignored)
        .map(|candidate| candidate.input_path.clone())
        .collect::<BTreeSet<_>>();
    let explicitly_allowed_tier_a = explicitly_allowed_tier_a_paths(&preview);
    let outcome = repo.auto_snapshot_with_bound_normalize(
        Some("kcs index auto snapshot"),
        None,
        &excluded,
        &index_result.normalize_by_path,
        &explicitly_allowed_tier_a,
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
    let rebuild_report = rebuild_step3_index(&repo)?;
    // Generate chunk embeddings behind the online opt-in / budget / cost-ledger
    // guardrails (K4). No-op unless an embedding adapter is configured. R11-2: keep
    // the ExecOutcome (was discarded) so the embedding enrichment result is disclosed
    // and can raise the exit code (auth/budget) instead of a silent exit 0.
    let enrichment = generate_scope_embeddings(&repo, &args)?;
    // The scope now has a search index; register it as indexed so it participates
    // in default multi-scope search (05 §1.8, K3). Cache write, never fatal.
    register_scope(&repo, true);
    let mut output = json!({
        "status": if outcome.noop { "noop" } else { "indexed" },
        "approval_method": if args.approve { "approve" } else if args.yes { "yes" } else { "existing" },
        "network_allowed": index_result.network_allowed,
        "network_opt_in": persistent_network_allowed(&repo)?,
        "pending_online_tasks": index_result.pending_online_tasks,
        // R11-2: fold enrichment's budget pauses in with the enqueue-paused markdownize
        // tasks so `paused_tasks` reflects everything the run left paused.
        "paused_tasks": index_result.paused_tasks + enrichment.paused,
        "failed_files": index_result.failed_files,
        "normalized_files": index_result.normalized_files,
        "pending_files": index_result.pending_files,
        // R12-2: files skipped for adapter processing by the max_input_bytes gate.
        "skipped_oversized_files": index_result.skipped_oversized_files,
        // R22-4: archived binaries that no local pass and no online OCR can enrich.
        "skipped_unrecognized_binary_files": index_result.skipped_unrecognized_binary_files,
        // R11-2: disclose the inline embedding enrichment (was entirely absent, so an
        // auth/rate failure during index was invisible in the result JSON).
        "embedding_tasks_executed": enrichment.executed,
        "embedding_tasks_failed": enrichment.failed,
        "tree_hash": outcome.tree_hash,
        "commit_hash": outcome.commit_hash,
        "commit": outcome.commit,
        // F5: non-blocking budget warning (null unless a cap crossed warn_at_percent).
        "budget_warning": scope_budget_warning(&repo)?,
    });
    // R16-4: disclose any documents skipped for missing/corrupt units (empty on a
    // clean index — the units were just written, so this normally stays empty).
    attach_skipped_units(&mut output, &rebuild_report, repo.kcs_dir());
    // R11-3: an index that partially failed to normalize local files keeps its full
    // result JSON on stdout (commit_hash, tree_hash, …) with `error_code` +
    // `__exit_code:3`, matching search's "result + nonzero exit" shape — instead of
    // the old Err envelope that buried commit_hash inside a private `context.output`.
    if index_result.failed_files > 0 {
        output["error_code"] = json!("KCS-E-INDEX-PARTIAL-001");
    }
    // Exit priority (docs/04 §5.6 / §7): enrichment auth (5) > budget pause (6) >
    // local partial (3). All still print the full result JSON to stdout.
    let exit_override = enrichment_exit_override(&enrichment)
        .or_else(|| (index_result.failed_files > 0).then_some(ExitCode::PartialFailure));
    if let Some(code) = exit_override {
        set_exit_override(&mut output, code);
    }
    Ok(output)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct StoredChunk {
    rowid: u64,
    /// Stable rowid of this `(chunk_id, chunking_config_hash)` association.
    ///
    /// Step 3 ledgers predate the many-to-many config relation and omit this
    /// field. `read_stored_chunks` assigns those legacy records deterministic
    /// rowids in ledger order before any replay or append.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    association_rowid: Option<u64>,
    #[serde(flatten)]
    row: ChunkRow,
}

#[derive(Debug, Clone)]
struct ScopeTarget {
    repo_root: PathBuf,
    kcs_dir: PathBuf,
    scope_id: String,
}

/// A live chunk plus its scope/snapshot metadata. Used by the Evidence Pointer
/// resolution path (short-hash lookup). Search itself no longer materializes
/// these — it reads ranked chunks directly from `sqlite.db` (K2).
#[derive(Debug, Clone)]
struct SearchableChunk {
    row: ChunkRow,
    scope_id: String,
    scope_path: PathBuf,
    snapshot_at: String,
    path_at_commit: String,
}

#[derive(Debug, Clone)]
struct ParsedSearch {
    query: String,
    requested_mode: SearchMode,
    /// R11-7: whether a `--text`/`--vector`/`--hybrid` flag set `requested_mode`
    /// explicitly. When false, `[search].default_mode` supplies the mode instead.
    explicit_mode: bool,
    scope: Option<PathBuf>,
    descendants: bool,
    all_scopes: bool,
    limit: u64,
    offset: Option<u64>,
    cursor: Option<String>,
    time_selector_flags: TimeSelectorFlags,
}

fn run_repair(args: UnsupportedArgs) -> Result<Value> {
    let args = without_json(args.args);
    let mode = parse_repair_args(args)?;
    let repo = Repository::open_current_without_head_repair()?;
    // M1(a): serialize the DB rebuild against concurrent index/repair/reindex.
    let _lock = repo.lock_store()?;
    repo.self_heal_head_for_repair()?;
    validate_repo_tool_lock(&repo)?;
    if mode == RepairMode::VerifyObjects {
        let report = verify_objects::verify_objects(&repo)?;
        let has_findings = report.has_remaining_findings();
        let purge_incomplete = report
            .remaining_findings
            .iter()
            .any(|finding| finding.kind == "purge_incomplete");
        let mut output =
            serde_json::to_value(report).map_err(|error| KcsError::schema(error.to_string()))?;
        if has_findings {
            if let Some(object) = output.as_object_mut() {
                object.insert(
                    "error_code".to_owned(),
                    json!(if purge_incomplete {
                        "KCS-E-PURGE-INCOMPLETE-001"
                    } else {
                        "KCS-E-STORE-CORRUPT-001"
                    }),
                );
                object.insert("__exit_code".to_owned(), json!(3));
            }
        }
        return Ok(output);
    }
    let promotion_rebuild_pending = recover_pending_online_promotion(&repo)?;
    let db = repo.kcs_dir().join("index/sqlite.db");
    // `rebuild_sqlite_index` drops and rebuilds chunks/FTS/tree_entries in place
    // while preserving the `embeddings` rows and re-deriving `chunk_vec` from them
    // (04 §4.3). It is not pre-deleted here so vector search survives the rebuild.
    let report = rebuild_step3_index(&repo)?;
    if promotion_rebuild_pending {
        maybe_inject_promotion_fault("after_index_swap")?;
        clear_promotion_state(repo.kcs_dir())?;
    }
    // L1: after a DB rebuild, re-drive enrichment so any chunk lacking an
    // embedding (e.g. a rebuild that produced new chunk rows, or a scope whose
    // enrichment never ran) is enqueued/embedded rather than silently reported as
    // fully enriched. `rebuild_sqlite_index` already preserved existing
    // embeddings, so reuse keeps this near-free; offline it only enqueues.
    let embedding_online = embedding_online_allowed(&repo, false, false, false)?;
    // R11-2: keep the enrichment ExecOutcome (was discarded) — disclose it and let an
    // auth/budget-pause raise the exit while the rebuild JSON still prints to stdout.
    let enrichment = run_embedding_enrichment(&repo, embedding_online, false, false)?;
    let mut output = json!({
        "status": "rebuilt",
        "rebuilt_chunks": report.rebuilt_chunks,
        "rebuilt_tree_entries": report.rebuilt_tree_entries,
        "sqlite_db": db,
        "embedding_tasks_executed": enrichment.executed,
        "embedding_tasks_failed": enrichment.failed,
        "paused_tasks": enrichment.paused,
    });
    // R16-4: disclose any documents skipped for missing/corrupt units (partial recovery).
    attach_skipped_units(&mut output, &report, repo.kcs_dir());
    if let Some(code) = enrichment_exit_override(&enrichment) {
        set_exit_override(&mut output, code);
    }
    Ok(output)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RepairMode {
    RebuildDb,
    VerifyObjects,
}

fn parse_repair_args(args: Vec<String>) -> Result<RepairMode> {
    if args.is_empty() {
        return Err(KcsError::invalid_usage(
            "repair currently supports --rebuild-db",
        ));
    }
    let mut rebuild_db = false;
    let mut verify_objects = false;
    for arg in &args {
        // R12-7: accept `--flag=value` before matching so an existing flag is not
        // misreported as unknown. R16-6: every repair flag is boolean, so an inline
        // value is a usage error, NOT silently dropped — `--rebuild-db=false` must
        // not still rebuild the DB.
        let (flag, inline) = split_flag_value(arg);
        match flag {
            "--rebuild-db" if !rebuild_db => {
                reject_inline_value(flag, inline)?;
                rebuild_db = true;
            }
            "--rebuild-db" => {
                reject_inline_value(flag, inline)?;
                return Err(KcsError::invalid_usage(
                    "repair accepts --rebuild-db only once",
                ));
            }
            "--yes" => reject_inline_value(flag, inline)?,
            "--verify-objects" if !verify_objects => {
                reject_inline_value(flag, inline)?;
                verify_objects = true;
            }
            "--verify-objects" => {
                reject_inline_value(flag, inline)?;
                return Err(KcsError::invalid_usage(
                    "repair accepts --verify-objects only once",
                ));
            }
            value if value.starts_with('-') => {
                return Err(KcsError::invalid_usage(format!(
                    "unknown repair flag: {value}"
                )))
            }
            _ => {
                return Err(KcsError::invalid_usage(
                    "repair accepts no positional arguments",
                ))
            }
        }
    }
    if rebuild_db == verify_objects {
        return Err(KcsError::invalid_usage(
            "repair requires exactly one of --rebuild-db or --verify-objects",
        ));
    }
    Ok(if rebuild_db {
        RepairMode::RebuildDb
    } else {
        RepairMode::VerifyObjects
    })
}

/// Resolved search mode plus the honest fallback reporting fields (05 §1.1/§1.7).
struct ResolvedMode {
    requested: SearchMode,
    resolved: SearchMode,
    fallback: bool,
    fallback_reason: Option<String>,
    error_code: Option<String>,
    /// R11-7: a non-null human warning when `[search].fail_behavior = "warn"` turned
    /// an auto/--hybrid vector-unavailable case into a text fallback. `None` for the
    /// silent default (`fallback`) and when no fallback occurred.
    warning: Option<String>,
}

/// R11-7: `[search].fail_behavior` (config.schema.json §search) — what an auto or
/// `--hybrid` search does when no compatible vector backend is available.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SearchFailBehavior {
    /// Default (05 §1.7): silently fall back to text.
    Fallback,
    /// Fall back to text but surface a `warning` field in the response.
    Warn,
    /// Hard error, identical to the explicit `--vector` path (KCS-E-SEARCH-VEC-*).
    Error,
}

/// Vector backend availability across the searched scopes (the K4 embedding
/// seam, now live). Resolved from the actual per-scope embedding state and query
/// embedding availability (03 §7 / 05 §1.1).
enum VectorAvailability {
    /// Every searched scope has a compatible embedding index and a query
    /// embedding is obtainable → hybrid is offered.
    Available,
    /// No usable vector backend → text. `reason` names the actual cause
    /// (05 §1.7 fallback_reason): `embedding_endpoint_not_configured` (no
    /// adapter env/config at all), `embedding_index_missing` (endpoint
    /// configured but no searched scope carries chunk embeddings), or
    /// `query_embedding_unavailable` (endpoint + index fine, but the query
    /// embedding could not be computed — short query or adapter failure).
    Unavailable { reason: &'static str },
    /// Embedding present but the profile is incompatible, or scopes disagree on
    /// embedding profile (03 §7 / 05 §1.8(5)) → text fallback + fallback_reason.
    Incompatible,
}

/// One scope's chunk-embedding disposition (03 §7 compat).
enum ScopeEmbedState {
    Compatible,
    Incompatible,
    Absent,
}

fn adopted_embedding_profile_summary() -> embedding_store::EmbeddingProfileSummary {
    let profile = adopted_embedding_profile();
    embedding_store::EmbeddingProfileSummary {
        dimensions: CHUNK_VEC_DIMENSIONS as u64,
        distance: "cosine".to_owned(),
        modality: "multimodal".to_owned(),
        profile_hash: profile.tool_profile_hash,
    }
}

/// Inspect a scope's `sqlite.db` for compatible chunk embeddings (03 §7). A read
/// failure or missing DB is treated as `Absent` (never a vector-search error —
/// text is always available). The extension is registered in `main`.
fn scope_embedding_state(kcs_dir: &Path) -> ScopeEmbedState {
    let db = sqlite_path(kcs_dir);
    if !db.exists() {
        return ScopeEmbedState::Absent;
    }
    let Ok(conn) = Connection::open(&db) else {
        return ScopeEmbedState::Absent;
    };
    let Ok(profiles) = embedding_store::chunk_embedding_profiles(&conn) else {
        return ScopeEmbedState::Absent;
    };
    if profiles.is_empty() {
        return ScopeEmbedState::Absent;
    }
    let expected = adopted_embedding_profile_summary();
    if profiles
        .iter()
        .all(|profile| profile.matches_profile(&expected))
    {
        ScopeEmbedState::Compatible
    } else {
        ScopeEmbedState::Incompatible
    }
}

/// K4: aggregate embedding availability across the searched scopes. Vector search
/// is offered only when the endpoint is configured, every searched scope has a
/// compatible embedding index (03 §7), AND a query embedding is obtainable. Any
/// incompatible scope, or a mix of embedded and un-embedded scopes (cross-scope
/// inconsistency, 05 §1.8(5)), downgrades to a text fallback. The `Unavailable`
/// reason names the first structural cause in precedence order: endpoint →
/// scope index → query embedding.
fn resolve_vector_availability(
    exec_scopes: &[ExecScope],
    endpoint_configured: bool,
    embedding_opt_in: bool,
    query_embeddable: bool,
) -> VectorAvailability {
    if !endpoint_configured {
        return VectorAvailability::Unavailable {
            reason: "embedding_endpoint_not_configured",
        };
    }
    let mut any_compatible = false;
    let mut any_incompatible = false;
    let mut any_absent = false;
    for exec in exec_scopes {
        match scope_embedding_state(&exec.target.kcs_dir) {
            ScopeEmbedState::Compatible => any_compatible = true,
            ScopeEmbedState::Incompatible => any_incompatible = true,
            ScopeEmbedState::Absent => any_absent = true,
        }
    }
    if any_incompatible || (any_compatible && any_absent) {
        VectorAvailability::Incompatible
    } else if !any_compatible {
        VectorAvailability::Unavailable {
            reason: "embedding_index_missing",
        }
    } else if !embedding_opt_in {
        // O2: a compatible index exists, but sending the query embedding needs the
        // scope's embedding opt-in (07 §3). Without it, offer text, never a send.
        VectorAvailability::Unavailable {
            reason: "embedding_opt_in_required",
        }
    } else if !query_embeddable {
        VectorAvailability::Unavailable {
            reason: "query_embedding_unavailable",
        }
    } else {
        VectorAvailability::Available
    }
}

fn resolve_search_mode(
    requested: SearchMode,
    vector: &VectorAvailability,
    fail_behavior: SearchFailBehavior,
) -> Result<ResolvedMode> {
    let vector_ok = matches!(vector, VectorAvailability::Available);
    let (reason, error_code) = match vector {
        VectorAvailability::Available => (None, None),
        VectorAvailability::Unavailable { reason } => (
            Some((*reason).to_owned()),
            Some("KCS-E-SEARCH-VEC-UNAVAIL-001".to_owned()),
        ),
        VectorAvailability::Incompatible => (
            Some("embedding_profile_incompatible".to_owned()),
            Some("KCS-E-SEARCH-VEC-INCOMPAT-001".to_owned()),
        ),
    };
    // The hard-error envelope shared by explicit `--vector` and R11-7's
    // `fail_behavior = "error"` (same error_code taxonomy, 03 §7 / 05 §1.2).
    let vector_unavailable_error = || {
        KcsError::new(
            error_code
                .as_deref()
                .unwrap_or("KCS-E-SEARCH-VEC-UNAVAIL-001"),
            "vector search requested but no compatible embedding index is available",
            json!({ "fallback_reason": reason }),
            ExitCode::Failure,
        )
    };
    match requested {
        SearchMode::Text => Ok(ResolvedMode {
            requested,
            resolved: SearchMode::Text,
            fallback: false,
            fallback_reason: None,
            error_code: None,
            warning: None,
        }),
        SearchMode::Vector => {
            if vector_ok {
                Ok(ResolvedMode {
                    requested,
                    resolved: SearchMode::Vector,
                    fallback: false,
                    fallback_reason: None,
                    error_code: None,
                    warning: None,
                })
            } else {
                // --vector with no usable vector backend is a hard error (05 §1.2);
                // the code distinguishes "unavailable" from "incompatible" (03 §7).
                Err(vector_unavailable_error())
            }
        }
        SearchMode::Auto | SearchMode::Hybrid => {
            if vector_ok {
                Ok(ResolvedMode {
                    requested,
                    resolved: SearchMode::Hybrid,
                    fallback: false,
                    fallback_reason: None,
                    error_code: None,
                    warning: None,
                })
            } else {
                // R11-7: auto / --hybrid vector-unavailable behavior is governed by
                // `[search].fail_behavior` (default = silent text fallback).
                match fail_behavior {
                    // The user asked for vectors and declared "error on failure" — make
                    // it the same hard error the explicit --vector path already returns,
                    // instead of a silent exit-0 text result.
                    SearchFailBehavior::Error => Err(vector_unavailable_error()),
                    // Fall back to text but surface a loud warning field in the response.
                    SearchFailBehavior::Warn => {
                        let warning = Some(format!(
                            "vector search unavailable ({}); fell back to text",
                            reason.as_deref().unwrap_or("unknown")
                        ));
                        Ok(ResolvedMode {
                            requested,
                            resolved: SearchMode::Text,
                            fallback: true,
                            fallback_reason: reason,
                            error_code,
                            warning,
                        })
                    }
                    // Default: silent text fallback (05 §1.7), warning stays null.
                    SearchFailBehavior::Fallback => Ok(ResolvedMode {
                        requested,
                        resolved: SearchMode::Text,
                        fallback: true,
                        fallback_reason: reason,
                        error_code,
                        warning: None,
                    }),
                }
            }
        }
    }
}

/// One scope's live search state for a single page of a query.
struct ExecScope {
    target: ScopeTarget,
    /// Commit whose tree fixes the live chunk set (05 §1.5). HEAD on page 1,
    /// the frozen sub-cursor commit on later pages.
    snapshot_commit: Option<String>,
    /// `rowid <= max_rowid` freezes the chunk set across pages (CT3-CURSOR-002).
    max_rowid: Option<u64>,
    /// Association append boundary frozen by a v2 cursor.
    max_association_rowid: Option<u64>,
    /// Effective per-scope chunking config frozen by a v2 cursor.
    chunking_config_hash: Option<String>,
    from_cursor: bool,
}

/// A candidate that survived per-scope RRF, carried into the cross-scope merge.
struct ScoredCandidate {
    scope_index: usize,
    scope_id: String,
    scope_path: PathBuf,
    chunk_hash: String,
    rrf_score: f64,
    meta: ChunkMeta,
    /// Deterministic path/commit aliases expanded only after global diversify.
    bindings: Vec<SearchHistoryBinding>,
    /// The chunk's embedding (hybrid/vector mode only), fed into MMR (05 §1.4).
    /// `None` in text mode, which makes MMR skip and only the raw_hash dedup run.
    embedding: Option<Vec<f32>>,
}

#[derive(Clone)]
struct ChunkMeta {
    raw_hash: String,
    tool_profile_hash: String,
    gen: u64,
    heading_path: Option<Vec<String>>,
    section_id: Option<String>,
    char_start: Option<u64>,
    char_end: Option<u64>,
    text: String,
}

/// One final result hit after historical/deleted alias expansion.
struct ExpandedCandidate<'a> {
    candidate: &'a ScoredCandidate,
    binding: &'a SearchHistoryBinding,
}

struct SearchedScopeInfo {
    scope_id: String,
    scope_path: PathBuf,
    snapshot_at: String,
    max_rowid: u64,
    max_association_rowid: u64,
    chunking_config_hash: String,
}

fn run_search(args: UnsupportedArgs) -> Result<Value> {
    // R12-4: a FAILED search (cursor mismatch, all-scope-failed, …) returns before
    // `append_search_logs`, so it never wrote a per-search metrics line and dropped
    // out of the p50/p95/p99 latency population (docs/05:578). Emit that line here on
    // the error path (result_count 0 + error_code). The errors.jsonl line for a hard
    // Err is still written by main()'s Err arm.
    let started = Instant::now();
    let result = run_search_inner(args, started);
    if let Err(error) = &result {
        append_failed_search_metrics(started, error);
    }
    result
}

fn run_search_inner(args: UnsupportedArgs, started: Instant) -> Result<Value> {
    let parsed = parse_search_args(without_json(args.args))?;
    let repo = Repository::open_current_for_search()?;
    validate_repo_tool_lock(&repo)?;

    // R11-7: apply the `[search]` config (config.schema.json §search). `default_mode`
    // seeds the requested mode ONLY when no CLI `--text`/`--vector`/`--hybrid` was
    // given (the flag always wins); `fail_behavior` governs what auto/--hybrid does
    // when no vector backend is available. Both were schema-valid + documented but
    // entirely unwired before (the [search] version of the R10-2 config drift).
    let (config_default_mode, config_fail_behavior) = effective_search_config(&repo)?;
    // R12-1: effective `[search.rrf]` / `[search.diversify]` (05 §1.3/§1.4). These
    // were documented + schema-valid but hardcoded at every call site (RRF fuse,
    // diversify, query_hash) — the tuning keys were dead. Read them once and thread
    // them through so config actually changes ranking/dedup AND invalidates a stale
    // cursor via query_hash.
    let (rrf_config, diversify_request) = effective_search_tuning(&repo)?;
    let requested_mode = if parsed.explicit_mode {
        parsed.requested_mode
    } else {
        config_default_mode.unwrap_or(parsed.requested_mode)
    };
    let fail_behavior = config_fail_behavior.unwrap_or(SearchFailBehavior::Fallback);

    // Page 1 enumerates scopes (registry-based, K3); later pages replay the frozen
    // scope set stored in the cursor (05 §1.8 — the cursor scope set is truth).
    // The scope set must be known before mode resolution (K4), because vector
    // availability depends on the actual per-scope embedding indexes (03 §7).
    // O1(b): cursors are HMAC-signed with a device-local key; decode verifies the
    // signature, so a forged / tampered token is rejected (KCS-E-SEARCH-CURSOR-001)
    // before its frozen scope set is ever trusted.
    let cursor_key = cursor_signing_key()?;
    let decoded_cursor = match &parsed.cursor {
        Some(token) => Some(decode_cursor_token(token, &cursor_key).map_err(search_to_kcs)?),
        None => None,
    };
    let explicit_selector = parsed
        .time_selector_flags
        .is_explicit()
        .then(|| parsed.time_selector_flags.canonicalize())
        .transpose()?;
    let (time_selector, since_cutoff) = match &decoded_cursor {
        Some(cursor) => {
            let frozen = selector_from_cursor(&cursor.time_travel)?;
            validate_cursor_cutoff(&frozen, cursor.since_cutoff.as_deref())?;
            (
                reconcile_cursor_selector(explicit_selector.as_ref(), &frozen)?,
                cursor.since_cutoff.clone(),
            )
        }
        None => {
            let selector = explicit_selector.unwrap_or_default();
            let cutoff = since_cutoff_utc(&selector, &now_utc_seconds())?;
            (selector, cutoff)
        }
    };
    let (scope_mode, exec_scopes, cursor_excluded) = match &decoded_cursor {
        Some(cursor) => {
            let (exec, excluded) = resolve_cursor_exec_scopes(cursor)?;
            // O1(a): a cursor must not bypass the caller's --scope/--descendants
            // restriction. Compute the scopes this invocation is allowed to reach
            // and intersect the cursor's frozen scope set with it; a cursor scope
            // outside the allowed set is excluded (scope_restriction_mismatch),
            // never searched. For a plain page-2 replay (no --scope) the allowed
            // set is every registered scope, so this is a no-op.
            let (_allowed_mode, allowed_targets) = enumerate_scope_targets(&repo, &parsed)?;
            let allowed_ids: BTreeSet<String> = allowed_targets
                .iter()
                .map(|target| target.scope_id.clone())
                .collect();
            if let Some(restricted) = exec
                .iter()
                .find(|exec| !allowed_ids.contains(&exec.target.scope_id))
            {
                return Err(KcsError::new(
                    "KCS-E-SEARCH-CURSOR-001",
                    "search cursor active scope is outside the requested scope restriction",
                    json!({
                        "reason": "active_scope_unavailable",
                        "scope_id": restricted.target.scope_id,
                    }),
                    ExitCode::InvalidUsage,
                ));
            }
            (
                scope_selection_from_cursor(cursor.scope_mode),
                exec,
                excluded,
            )
        }
        None => {
            let (scope_mode, targets) = enumerate_scope_targets(&repo, &parsed)?;
            let exec = targets
                .into_iter()
                .map(|target| ExecScope {
                    target,
                    snapshot_commit: None,
                    max_rowid: None,
                    max_association_rowid: None,
                    chunking_config_hash: None,
                    from_cursor: false,
                })
                .collect::<Vec<_>>();
            (scope_mode, exec, Vec::new())
        }
    };

    // Mode resolution (05 §1.1). O2: the query embedding is SENT to the online
    // embedding endpoint, so it must not be computed until the resolved mode
    // actually uses vectors AND the scope's embedding opt-in (07 §3) is granted.
    // Judge vector availability from cheap predicates (endpoint + opt-in + query
    // length + per-scope compat) — never by eagerly calling the adapter.
    let embedding_opt_in = active_embedding_adapter_id()?
        .map(|adapter_id| embedding_opt_in_for_scopes(&exec_scopes, &adapter_id))
        .transpose()?
        .unwrap_or(false);
    let query_embeddable = parsed.query.chars().count() >= 2;
    let vector_precheck = resolve_vector_availability(
        &exec_scopes,
        embedding_execution().is_some(),
        embedding_opt_in,
        query_embeddable,
    );
    let precheck_mode = resolve_search_mode(requested_mode, &vector_precheck, fail_behavior)?;
    // Only now, and only when the pre-resolved mode uses vectors, compute (send)
    // the query embedding. In --text this branch is never taken, so the query is
    // never sent.
    let uses_vectors = matches!(
        precheck_mode.resolved,
        SearchMode::Hybrid | SearchMode::Vector
    );
    // F2: the FTS index projection is NFC-normalized (kcs-index `index_chunk`), so
    // the FTS query and the embedded query must use the same normal form or NFD
    // content is a silent false negative (and vice versa). `query_hash` already
    // normalizes internally, so the cursor hash is unaffected; only the MATCH /
    // vector inputs need this. Display fields keep the caller's original `query`.
    let query_nfc = parsed.query.nfc().collect::<String>();
    let query_embedding = if uses_vectors {
        compute_query_embedding(&query_nfc)?
    } else {
        None
    };
    // A live adapter failure (auth/rate) after the send still degrades vector→text
    // so `--vector` errors and auto/hybrid falls back, exactly as before O2.
    let vector = if uses_vectors && query_embedding.is_none() {
        VectorAvailability::Unavailable {
            reason: "query_embedding_unavailable",
        }
    } else {
        vector_precheck
    };
    let mode = resolve_search_mode(requested_mode, &vector, fail_behavior)?;

    // N8: the short-query short-circuit is NOT taken here — it must run after scope
    // resolution, the all-failed check, and index_status aggregation below, or a
    // 1-char query would mask a scope failure and pin index_status to a fixed 1.0.

    if exec_scopes.is_empty() {
        // Cursor replay where no frozen scope resolves any more → all failed
        // (exit 4) with the unresolvable scopes disclosed. Fresh search with an
        // empty registry keeps the guidance message.
        if !cursor_excluded.is_empty() {
            return Err(scope_all_failed_error(
                "no scope in the cursor is resolvable any more; re-run the search without a cursor",
                cursor_excluded,
            ));
        }
        return Err(scope_all_failed_error(
            "no indexed scopes are registered for search; run `kcs index` in a scope first",
            Vec::new(),
        ));
    }

    // A replay can validate its hash entirely from the signed active scopes and
    // their frozen config mappings. Page 1 defers hash construction until after
    // per-scope execution, so an unreadable sibling remains a normal partial
    // exclusion instead of aborting before the isolation boundary.
    let mut qhash = String::new();
    if let Some(cursor) = &decoded_cursor {
        let mut scope_ids = cursor
            .scopes
            .iter()
            .map(|scope| scope.scope_id.clone())
            .collect::<Vec<_>>();
        scope_ids.sort();
        let mut chunking_configs = cursor
            .scopes
            .iter()
            .map(|scope| ChunkingConfigBinding {
                scope_id: scope.scope_id.clone(),
                chunking_config_hash: scope.chunking_config_hash.clone(),
            })
            .collect::<Vec<_>>();
        chunking_configs.sort_by(|left, right| left.scope_id.cmp(&right.scope_id));
        qhash = query_hash(&QueryHashInput {
            query: parsed.query.clone(),
            mode: mode.resolved,
            scope_mode,
            scopes: scope_ids,
            diversify: diversify_request.clone(),
            rrf_k: rrf_config.k,
            rrf_candidate_depth: rrf_config.candidate_depth,
            rrf_w_text: rrf_config.w_text,
            rrf_w_vector: rrf_config.w_vector,
            chunking_configs,
            time_travel: selector_for_search(&time_selector),
        })
        .map_err(search_to_kcs)?;
        if cursor.query_hash != qhash {
            return Err(KcsError::new(
                "KCS-E-SEARCH-CURSOR-001",
                "search cursor query_hash mismatch",
                json!({ "expected": qhash, "actual": cursor.query_hash }),
                ExitCode::InvalidUsage,
            ));
        }
    }

    // Per-scope: FTS5 text ranks + chunk_vec KNN vector ranks -> RRF -> candidate
    // pool. Vector ranks are supplied only in hybrid/vector mode (K4). F2: build
    // the FTS tiers from the NFC-normalized query to match the NFC index
    // projection.
    let tiers = build_fts_tiers(&query_nfc);
    // Only feed vectors into the KNN when the resolved mode actually uses them;
    // a text fallback (incompatible/absent) must stay pure text.
    let scope_query_embedding = matches!(mode.resolved, SearchMode::Hybrid | SearchMode::Vector)
        .then_some(query_embedding.as_deref())
        .flatten();
    let mut searched = Vec::<SearchedScopeInfo>::new();
    // Scopes the cursor froze but the registry can no longer resolve are already
    // excluded (reason "unreachable") before per-scope execution starts.
    let mut excluded = cursor_excluded;
    let mut candidates = Vec::<ScoredCandidate>::new();

    for (idx, exec) in exec_scopes.iter().enumerate() {
        match search_one_scope(
            exec,
            idx,
            &tiers,
            mode.resolved,
            scope_query_embedding,
            rrf_config,
            ScopeTimeRequest {
                selector: &time_selector,
                since_cutoff: since_cutoff.as_deref(),
            },
        ) {
            Ok(outcome) => {
                searched.push(SearchedScopeInfo {
                    scope_id: exec.target.scope_id.clone(),
                    scope_path: exec.target.repo_root.clone(),
                    snapshot_at: outcome.snapshot_commit.clone(),
                    max_rowid: outcome.max_rowid,
                    max_association_rowid: outcome.max_association_rowid,
                    chunking_config_hash: outcome.chunking_config_hash.clone(),
                });
                candidates.extend(outcome.candidates);
            }
            Err(ScopeSearchError::Shallow) => {
                // Any shallow snapshot on a cursor replay is a hard failure
                // (05 §2.2 / CT3-CURSOR-005): the tree needed to reproduce the
                // page is gone. Only reachable on the cursor path.
                return Err(KcsError::new(
                    "KCS-E-COMMIT-SHALLOW-001",
                    "cursor snapshot commit is shallow (tree discarded); re-run the search without a cursor",
                    json!({ "scope_id": exec.target.scope_id }),
                    ExitCode::Failure,
                ));
            }
            Err(ScopeSearchError::Excluded(reason)) => {
                if exec.from_cursor {
                    return Err(KcsError::new(
                        "KCS-E-SEARCH-CURSOR-001",
                        "search cursor active scope is no longer available; re-run without a cursor",
                        json!({
                            "reason": "active_scope_unavailable",
                            "cause": reason,
                            "scope_id": exec.target.scope_id,
                        }),
                        ExitCode::InvalidUsage,
                    ));
                }
                // R18-4: attach the store-corruption recovery hint to THIS entry (not
                // only to the all-scopes-failed aggregate below), so a PARTIAL exclusion
                // (some scopes healthy → `searched` non-empty → the aggregate block is
                // skipped) is still agent-detectable.
                let mut entry = json!({
                    "scope_id": exec.target.scope_id,
                    "scope_path": exec.target.repo_root,
                    "reason": reason,
                });
                if let Some(hint) = store_corruption_recovery_hint(&reason) {
                    entry["recovery"] = json!(hint);
                }
                excluded.push(entry);
            }
            Err(ScopeSearchError::Fatal(error)) => {
                if exec.from_cursor {
                    return Err(error);
                }
                // R16-2: a store-corruption Fatal from ONE scope must not discard the
                // healthy scopes' already-collected results — that violated the 05 §1.8
                // per-scope isolation contract that `index_corrupt` / `index_missing` /
                // vector-capacity already honor. Downgrade the store-corruption class to
                // an `Excluded("store_corrupt")` so healthy scopes still return and the
                // "every scope failed → SCOPE-ALL-FAILED exit 4" aggregation still fires
                // only when EVERY scope failed. This is deliberately NOT a blanket
                // Fatal→Excluded generalization: a genuine programming error / unexpected
                // Fatal must stay fail-fast, so only the explicit store class is caught.
                if is_store_corrupt_class(&error) {
                    // R18-4: same per-entry recovery hint as the Excluded arm above.
                    let mut entry = json!({
                        "scope_id": exec.target.scope_id,
                        "scope_path": exec.target.repo_root,
                        "reason": "store_corrupt",
                    });
                    if let Some(hint) = store_corruption_recovery_hint("store_corrupt") {
                        entry["recovery"] = json!(hint);
                    }
                    excluded.push(entry);
                } else {
                    return Err(error);
                }
            }
        }
    }

    if searched.is_empty() {
        // P10: every enumerated scope is mid-reindex (HEAD advanced, rebuilt sqlite
        // not yet swapped in). This is transient — the complete result set returns
        // on retry once the atomic rename lands — so surface the honest
        // KCS-E-INDEX-REBUILDING-001 (docs/05:564) with the retryable exit 3
        // (05 §6, as KCS-E-STORE-LOCKED-001 does), never a false permanent
        // all-failed or a silent empty page.
        let all_rebuilding = !excluded.is_empty()
            && excluded.iter().all(|entry| {
                entry.get("reason").and_then(Value::as_str) == Some(INDEX_REBUILDING_REASON)
            });
        if all_rebuilding {
            return Err(KcsError::new(
                "KCS-E-INDEX-REBUILDING-001",
                "the search index is being rebuilt (reindex in progress); retry the search",
                json!({ "excluded_scopes": excluded }),
                ExitCode::PartialFailure,
            ));
        }
        // Every enumerated scope was excluded. When every exclusion reason is
        // "the scope's sqlite.db is unusable" (missing/corrupt), BOTH backends
        // are structurally gone — text and vector live in the same index file —
        // which is CT3-HYBRID-003's "両方不可": KCS-E-SEARCH-VEC-UNAVAIL-001,
        // exit 1 (05 §1.1). Any other reason (unreachable / not_indexed / stale /
        // timeout) keeps the multi-scope all-failed contract:
        // KCS-E-SEARCH-SCOPE-ALL-FAILED-001, exit 4 (05 §1.8 / CT3-MULTI-005(b)).
        let index_unusable = !excluded.is_empty()
            && excluded.iter().all(|entry| {
                matches!(
                    entry.get("reason").and_then(Value::as_str),
                    Some("index_missing") | Some("index_corrupt")
                )
            });
        if index_unusable {
            // R20-8: attach a top-level `context.recovery` (not only the per-entry hints),
            // so the exit-1 index-unusable response is structurally consistent with the
            // store-corruption aggregate below.
            return Err(KcsError::new(
                "KCS-E-SEARCH-VEC-UNAVAIL-001",
                "text and vector search are both unavailable: the search index (sqlite.db) is missing or corrupt in every scope; run `kcs repair --rebuild-db`",
                json!({ "excluded_scopes": excluded, "recovery": aggregate_store_recovery_hints(&excluded) }),
                ExitCode::Failure,
            ));
        }
        // R17-4: when every scope was excluded for a store-corruption class (R16-2's
        // `store_corrupt` — a tampered/corrupt commit-or-tree object — or R16-3's
        // `snapshot_shallow` — a discarded HEAD tree with no cached rows), the generic
        // SCOPE-ALL-FAILED (exit 4, no guidance) left the operator/agent with no
        // recovery path (the R16-2/R16-3 exclusion reasons were never taught to this
        // aggregation, unlike `index_missing`/`index_corrupt` above). Attach
        // class-specific recovery guidance to the SCOPE-ALL-FAILED response (message +
        // `context.recovery`); the error CODE stays the docs-registered
        // SCOPE-ALL-FAILED-001 (the code registry in docs/06 §8 / docs/10 §7.5 is
        // normative and docs are frozen — no new code). Deliberately NOT unified with
        // `index_missing`'s exit-1 + "run repair" push: `repair --rebuild-db` rebuilds
        // the sqlite index FROM the store, so it does not heal a corrupt/absent
        // commit-or-tree object (it re-hits the same corruption) — the real recovery is
        // restoring the object from objects/refs or re-indexing. Exit stays 4 (manual
        // intervention required), the honest current semantics; the `recovery` context
        // is what makes the path agent-detectable.
        let store_corruption = !excluded.is_empty()
            && excluded.iter().all(|entry| {
                matches!(
                    entry.get("reason").and_then(Value::as_str),
                    Some("store_corrupt") | Some("snapshot_shallow")
                )
            });
        if store_corruption {
            let reason_is = |want: &str| {
                excluded
                    .iter()
                    .any(|entry| entry.get("reason").and_then(Value::as_str) == Some(want))
            };
            // R18-4: the same hints the per-entry attachment uses, aggregated here for
            // the all-scopes-failed response (identical strings via the shared helper).
            let mut recovery = Vec::<&str>::new();
            if reason_is("store_corrupt") {
                recovery.push(store_corruption_recovery_hint("store_corrupt").unwrap());
            }
            if reason_is("snapshot_shallow") {
                recovery.push(store_corruption_recovery_hint("snapshot_shallow").unwrap());
            }
            return Err(KcsError::new(
                "KCS-E-SEARCH-SCOPE-ALL-FAILED-001",
                format!(
                    "every searched scope's store is corrupt or shallow, so search cannot \
                     run — {}",
                    recovery.join("; ")
                ),
                json!({ "excluded_scopes": excluded, "recovery": recovery }),
                ExitCode::PermanentFailure,
            ));
        }
        // R20-8: a HETEROGENEOUS all-failed mix (e.g. one index_corrupt + one store_corrupt)
        // matches neither homogeneous aggregation above, yet every scope has a known
        // recovery. R18-4 left it falling through to the bare "all searched scopes failed"
        // with no guidance. Attach aggregate recovery (message + context.recovery); the code
        // stays SCOPE-ALL-FAILED-001 (docs frozen — no new code) and exit 4 (a store_corrupt
        // member needs manual object restore, so not the exit-1 VEC-UNAVAIL rebuild path).
        let all_recoverable = !excluded.is_empty()
            && excluded.iter().all(|e| {
                matches!(
                    e.get("reason").and_then(Value::as_str),
                    Some(reason) if store_corruption_recovery_hint(reason).is_some()
                )
            });
        if all_recoverable {
            let recovery = aggregate_store_recovery_hints(&excluded);
            return Err(KcsError::new(
                "KCS-E-SEARCH-SCOPE-ALL-FAILED-001",
                format!(
                    "every searched scope failed with a recoverable store/index error, so \
                     search cannot run — {}",
                    recovery.join("; ")
                ),
                json!({ "excluded_scopes": excluded, "recovery": recovery }),
                ExitCode::PermanentFailure,
            ));
        }
        return Err(scope_all_failed_error(
            "all searched scopes failed",
            excluded,
        ));
    }

    // A fresh page-1 cursor binds only scopes that actually participated. Scopes
    // excluded during execution are signed separately and never enter the stream.
    if decoded_cursor.is_none() {
        let mut active_scope_ids = searched
            .iter()
            .map(|scope| scope.scope_id.clone())
            .collect::<Vec<_>>();
        active_scope_ids.sort();
        let mut active_configs = searched
            .iter()
            .map(|scope| ChunkingConfigBinding {
                scope_id: scope.scope_id.clone(),
                chunking_config_hash: scope.chunking_config_hash.clone(),
            })
            .collect::<Vec<_>>();
        active_configs.sort_by(|a, b| a.scope_id.cmp(&b.scope_id));
        qhash = query_hash(&QueryHashInput {
            query: parsed.query.clone(),
            mode: mode.resolved,
            scope_mode,
            scopes: active_scope_ids,
            diversify: diversify_request.clone(),
            rrf_k: rrf_config.k,
            rrf_candidate_depth: rrf_config.candidate_depth,
            rrf_w_text: rrf_config.w_text,
            rrf_w_vector: rrf_config.w_vector,
            chunking_configs: active_configs,
            time_travel: selector_for_search(&time_selector),
        })
        .map_err(search_to_kcs)?;
    }

    // N8: now that scope resolution, the all-failed check, and (below) index_status
    // are honored, a short (< 2 char) query — which produces no indexable token —
    // short-circuits the ranking/paging with an honest empty page that still
    // reports the real searched scopes and index_status.
    if parsed.query.chars().count() < 2 {
        return empty_search_response(&parsed, &repo, started, &mode, &searched, &excluded);
    }

    // Cross-scope merge is rank-based: RRF score desc, tie-break (scope_id,
    // chunk_hash) — never compare raw BM25 across corpora (05 §1.8 / CT3-MULTI-002).
    candidates.sort_by(|a, b| {
        b.rrf_score
            .total_cmp(&a.rrf_score)
            .then_with(|| a.scope_id.as_bytes().cmp(b.scope_id.as_bytes()))
            .then_with(|| a.chunk_hash.cmp(&b.chunk_hash))
    });

    // Diversify the merged pool once (05 §1.8 step 4). Text-only -> MMR is skipped;
    // only the raw_hash dedup runs (spanning scopes and pages, CT3-MULTI-003).
    // R12-1: the effective `[search.diversify]` request drives it (was a fixed literal).
    let (ordered, diversify_summary) =
        diversify_merged(&candidates, mode.resolved, &diversify_request)?;

    // Historical/deleted path aliases inherit their semantic parent's score and
    // are expanded only after global MMR/dedup. Group order is stable by
    // (scope_id, chunk_hash, path, pointer commit), then pagination sees the final
    // hit stream rather than semantic chunks.
    let mut expanded = Vec::<ExpandedCandidate<'_>>::new();
    for candidate in ordered {
        let mut bindings = candidate.bindings.iter().collect::<Vec<_>>();
        bindings.sort_by(|left, right| {
            left.path_at_commit
                .as_bytes()
                .cmp(right.path_at_commit.as_bytes())
                .then_with(|| {
                    left.pointer_commit
                        .as_bytes()
                        .cmp(right.pointer_commit.as_bytes())
                })
        });
        expanded.extend(
            bindings
                .into_iter()
                .map(|binding| ExpandedCandidate { candidate, binding }),
        );
    }

    // Global skip: cursor consumed (summed across scopes) or --offset (05 §1.5).
    let total_skip = match &decoded_cursor {
        Some(cursor) => cursor
            .scopes
            .iter()
            .map(|scope| scope.consumed)
            .sum::<u64>() as usize,
        None => parsed.offset.unwrap_or(0) as usize,
    };
    let limit = parsed.limit as usize;
    let slice_start = total_skip.min(expanded.len());
    let slice_end = slice_start.saturating_add(limit).min(expanded.len());
    let page = &expanded[slice_start..slice_end];

    // Per-scope consumed = candidates from that scope within the first `slice_end`
    // positions of the deterministic stream (uniform for cursor and --offset,
    // CT3-CURSOR-006). Preserves the frozen scope set even at 0 consumed.
    let mut signed_exclusions = excluded
        .iter()
        .filter_map(|entry| {
            Some(CursorExcludedScope {
                scope_id: entry.get("scope_id")?.as_str()?.to_owned(),
                reason: entry.get("reason")?.as_str()?.to_owned(),
            })
        })
        .collect::<Vec<_>>();
    signed_exclusions.sort_by(|a, b| a.scope_id.cmp(&b.scope_id));
    signed_exclusions.dedup_by(|a, b| a.scope_id == b.scope_id);
    let next_cursor = if slice_end < expanded.len() {
        let mut consumed = vec![0u64; exec_scopes.len()];
        for hit in &expanded[..slice_end] {
            consumed[hit.candidate.scope_index] += 1;
        }
        let mut sub_cursors = exec_scopes
            .iter()
            .enumerate()
            .filter_map(|(idx, exec)| {
                let searched_scope = searched
                    .iter()
                    .find(|scope| scope.scope_id == exec.target.scope_id)?;
                Some(ScopeCursor {
                    scope_id: exec.target.scope_id.clone(),
                    snapshot_commit: searched_scope.snapshot_at.clone(),
                    max_rowid: searched_scope.max_rowid,
                    max_association_rowid: searched_scope.max_association_rowid,
                    chunking_config_hash: searched_scope.chunking_config_hash.clone(),
                    consumed: consumed[idx],
                })
            })
            .collect::<Vec<_>>();
        sub_cursors.sort_by(|a, b| a.scope_id.cmp(&b.scope_id));
        Some(
            encode_cursor_token(
                &CursorToken {
                    version: CursorToken::VERSION,
                    scope_mode: cursor_mode_from_selection(scope_mode),
                    query_hash: qhash,
                    time_travel: selector_for_search(&time_selector),
                    since_cutoff: since_cutoff.clone(),
                    excluded_scopes: signed_exclusions,
                    scopes: sub_cursors,
                },
                &cursor_key,
            )
            .map_err(search_to_kcs)?,
        )
    } else {
        None
    };

    let mut results = Vec::new();
    for hit in page {
        let candidate = hit.candidate;
        let binding = hit.binding;
        let pointer = issue_evidence_pointer(EvidencePointerIssueRequest {
            scope_id: candidate.scope_id.clone(),
            scope_path: Some(candidate.scope_path.display().to_string()),
            commit: binding.pointer_commit.clone(),
            tree: None,
            raw_hash: candidate.meta.raw_hash.clone(),
            tool_profile_hash: candidate.meta.tool_profile_hash.clone(),
            chunk_hash: candidate.chunk_hash.clone(),
            path_at_commit: Some(binding.path_at_commit.clone()),
            heading_path: candidate.meta.heading_path.clone(),
            section_id: candidate.meta.section_id.clone(),
            char_start: candidate.meta.char_start,
            char_end: candidate.meta.char_end,
        })
        .map_err(search_to_kcs)?;
        let uri = evidence_pointer_to_uri(&pointer).map_err(search_to_kcs)?;
        let mut result = json!({
            "chunk_hash": candidate.chunk_hash,
            "evidence_pointer": pointer,
            "evidence_uri": uri,
            "score": candidate.rrf_score,
            "scope_path": candidate.scope_path,
            "title": binding.path_at_commit,
            "snippet": candidate.meta.text.chars().take(200).collect::<String>(),
        });
        if time_selector.all_history() && !binding.current_paths.is_empty() {
            result["current_paths"] = json!(binding.current_paths);
            if let Some(current_path) = binding.current_path() {
                result["current_path"] = json!(current_path);
            }
        }
        results.push(result);
    }

    let searched_scopes = searched
        .iter()
        .map(|scope| {
            json!({
                "scope_id": scope.scope_id,
                "scope_path": scope.scope_path,
                "snapshot_at": scope.snapshot_at,
            })
        })
        .collect::<Vec<_>>();
    let index_status = compute_index_status(&searched);
    let partial_failure = !excluded.is_empty();

    let mut response = json!({
        "query": parsed.query,
        "requested_mode": search_mode_json(mode.requested),
        "resolved_mode": search_mode_json(mode.resolved),
        "fallback": mode.fallback,
        "fallback_reason": mode.fallback_reason.clone().map(Value::from).unwrap_or(Value::Null),
        "error_code": mode.error_code.clone().map(Value::from).unwrap_or(Value::Null),
        // R11-7: non-null only under [search].fail_behavior = "warn" text fallback.
        "warning": mode.warning.clone().map(Value::from).unwrap_or(Value::Null),
        "diversify": diversify_summary,
        "paging": { "limit": parsed.limit, "next_cursor": next_cursor },
        "searched_scopes": searched_scopes,
        "excluded_scopes": excluded,
        "index_status": index_status,
        "results": results,
    });
    append_search_logs(&repo, &response, started);
    if partial_failure {
        // Some scopes were excluded but others succeeded: emit results on stdout
        // and exit 3 (05 §1.8 partial-failure row, CT3-MULTI-005).
        if let Some(object) = response.as_object_mut() {
            object.insert("__exit_code".to_owned(), json!(3));
        }
    }
    Ok(response)
}

/// Per-scope search failure disposition.
enum ScopeSearchError {
    /// Cursor snapshot's tree is gone (shallow) — hard fail the whole search.
    Shallow,
    /// Recorded in `excluded_scopes`; the overall search may still succeed.
    Excluded(String),
    /// An unexpected error that must abort the command.
    Fatal(KcsError),
}

/// Exclusion reason for a scope observed mid-reindex (P10): HEAD has advanced to a
/// new generation but the rebuilt sqlite is not yet swapped in, so not one chunk is
/// live. Surfaced as `KCS-E-INDEX-REBUILDING-001` when it is the sole failure mode.
const INDEX_REBUILDING_REASON: &str = "index_rebuilding";

struct ScopeOutcome {
    snapshot_commit: String,
    max_rowid: u64,
    max_association_rowid: u64,
    chunking_config_hash: String,
    candidates: Vec<ScoredCandidate>,
}

#[derive(Clone, Copy)]
struct ScopeTimeRequest<'a> {
    selector: &'a TimeSelector,
    since_cutoff: Option<&'a str>,
}

fn history_plan_error(error: KcsError, from_cursor: bool) -> ScopeSearchError {
    match error.error_code() {
        "KCS-E-COMMIT-SHALLOW-001" => ScopeSearchError::Shallow,
        "KCS-E-COMMIT-HISTORY-LIMIT-001" if !from_cursor => {
            ScopeSearchError::Excluded("history_limit_exceeded".to_owned())
        }
        _ => ScopeSearchError::Fatal(error),
    }
}

fn purge_blocks_raw(target: &ScopeTarget, raw_hash: &str) -> Result<bool> {
    // Public tombstones and an in-progress transaction after its visibility
    // barrier hide content. Fsck-only erase receipts intentionally do not.
    Ok(read_tombstone(target, raw_hash)?.is_some()
        || PurgeState::new(&target.kcs_dir).barrier_blocks(raw_hash)?)
}

/// Mutation-side purge gate. Public tombstones permanently reject identical-byte
/// re-ingest, while an active post-visibility journal is a retryable incomplete
/// purge. Fsck-only erase receipts deliberately do not block explicit ingest.
fn ensure_raw_ingest_allowed(repo: &Repository, raw_hash: &str) -> Result<()> {
    let purge = PurgeState::new(repo.kcs_dir());
    if purge.barrier_blocks(raw_hash)? {
        return Err(KcsError::new(
            "KCS-E-PURGE-INCOMPLETE-001",
            "raw ingest is blocked while purge remains incomplete",
            json!({ "component": "raw_ingest" }),
            ExitCode::PartialFailure,
        ));
    }
    if let Some(record) = purge.read_tombstone(raw_hash)? {
        let value =
            serde_json::to_value(record).map_err(|error| KcsError::schema(error.to_string()))?;
        return Err(tombstone_error(value));
    }
    // Read and validate a receipt, but do not treat it as a liveness decision.
    // The store-locked raw publication boundary retires it after verified write.
    let _ = purge.read_erase_receipt(raw_hash)?;
    Ok(())
}

fn raw_ingest_is_purge_blocked(repo: &Repository, raw_hash: &str) -> bool {
    ensure_raw_ingest_allowed(repo, raw_hash).is_err()
}

/// Rebuilders hold the scope store lock, so an already-visible purge journal
/// cannot make forward progress until they return. Refuse the rebuild before any
/// derived write instead of temporarily resurrecting its blocked rows.
fn ensure_no_visible_purge_journal(kcs_dir: &Path) -> Result<()> {
    if PurgeState::new(kcs_dir)
        .read_journal()?
        .is_some_and(|journal| journal.phase.is_barrier_visible())
    {
        return Err(KcsError::new(
            "KCS-E-PURGE-INCOMPLETE-001",
            "index rebuild is blocked while purge remains incomplete",
            json!({ "component": "index_rebuild" }),
            ExitCode::PartialFailure,
        ));
    }
    Ok(())
}

/// Persistent tombstones and the active visibility barrier are both authoritative
/// over append-only history/chunk ledgers. Derived rebuilds must omit either form.
fn purge_blocks_rebuild_raw(kcs_dir: &Path, raw_hash: &str) -> Result<bool> {
    let state = PurgeState::new(kcs_dir);
    Ok(state.read_tombstone(raw_hash)?.is_some() || state.barrier_blocks(raw_hash)?)
}

fn search_one_scope(
    exec: &ExecScope,
    scope_index: usize,
    tiers: &[String],
    resolved_mode: SearchMode,
    query_embedding: Option<&[f32]>,
    rrf_config: RrfConfig,
    time: ScopeTimeRequest<'_>,
) -> std::result::Result<ScopeOutcome, ScopeSearchError> {
    let repo = Repository::open_for_search(&exec.target.repo_root)
        .map_err(|_| ScopeSearchError::Excluded("unreachable".to_owned()))?;

    // Resolve the search snapshot independently per scope. Cursor replay always
    // uses the signed commit; a fresh `--at` resolves its operand in this scope;
    // every other selector freezes the scope's current HEAD.
    let snapshot_commit = match &exec.snapshot_commit {
        Some(commit) => commit.clone(),
        None => match time.selector.at() {
            Some(operand) => match repo.resolve_commit(operand) {
                Ok(commit) => commit,
                Err(error) if error.error_code() == "KCS-E-COMMIT-SHALLOW-001" => {
                    return Err(ScopeSearchError::Shallow);
                }
                Err(error) if error.error_code() == "KCS-E-STORE-NOT-FOUND-001" => {
                    return Err(ScopeSearchError::Excluded("commit_not_found".to_owned()));
                }
                Err(error) => return Err(ScopeSearchError::Fatal(error)),
            },
            None => repo
                .head_commit_hash()
                .map_err(|_| ScopeSearchError::Excluded("unreachable".to_owned()))?
                .ok_or_else(|| ScopeSearchError::Excluded("not_indexed".to_owned()))?,
        },
    };

    let db_path = sqlite_path(&exec.target.kcs_dir);
    if !db_path.exists() {
        return Err(ScopeSearchError::Excluded("index_missing".to_owned()));
    }
    let conn = Connection::open(&db_path)
        .map_err(|_| ScopeSearchError::Excluded("index_corrupt".to_owned()))?;

    // M4: `Connection::open` is lazy — it succeeds on an empty or garbage file and
    // only fails when the DB is first read. Probe the index eagerly so a corrupt
    // sqlite.db is classified as Excluded("index_corrupt") here (partial failure)
    // instead of exploding into a Fatal later that would exit 2 and drop the
    // healthy scopes' results too (05 §1.8 part-failure contract). An empty but
    // structurally-valid table (no rows) is healthy.
    match conn.query_row("SELECT 1 FROM tree_entries LIMIT 1", [], |_| Ok(())) {
        Ok(()) | Err(rusqlite::Error::QueryReturnedNoRows) => {}
        Err(_) => return Err(ScopeSearchError::Excluded("index_corrupt".to_owned())),
    }

    // Build the immutable eligible binding relation. Default search retains the
    // established shallow-cache read degradation; every explicit historical mode
    // reads verified commit/tree CAS and therefore rejects incomplete ancestry.
    let mut history_plan = match time.selector {
        TimeSelector::Current => {
            match ensure_snapshot_tree_entries(&repo, &conn, &snapshot_commit) {
                Ok(SnapshotTreeEntries::Projected) => {}
                Ok(SnapshotTreeEntries::ShallowCachedRows) if exec.from_cursor => {
                    return Err(ScopeSearchError::Shallow);
                }
                Ok(SnapshotTreeEntries::ShallowCachedRows) => {}
                Ok(SnapshotTreeEntries::ShallowNoRows) if exec.from_cursor => {
                    return Err(ScopeSearchError::Shallow);
                }
                Ok(SnapshotTreeEntries::ShallowNoRows) => {
                    return Err(ScopeSearchError::Excluded("snapshot_shallow".to_owned()));
                }
                Err(error) => return Err(ScopeSearchError::Fatal(error)),
            }
            current_history_plan_from_cache(&conn, &snapshot_commit)
                .map_err(ScopeSearchError::Fatal)?
        }
        TimeSelector::At(_) => {
            exact_project_snapshot(&repo, &conn, &snapshot_commit).map_err(|error| {
                if error.error_code() == "KCS-E-COMMIT-SHALLOW-001" {
                    ScopeSearchError::Shallow
                } else {
                    ScopeSearchError::Fatal(error)
                }
            })?;
            plan_search_history(&repo, &snapshot_commit, time.selector, time.since_cutoff)
                .map_err(|error| history_plan_error(error, exec.from_cursor))?
        }
        TimeSelector::AllHistory | TimeSelector::Since(_) | TimeSelector::IncludeDeleted => {
            plan_search_history(&repo, &snapshot_commit, time.selector, time.since_cutoff)
                .map_err(|error| history_plan_error(error, exec.from_cursor))?
        }
    };
    // A purge barrier becomes the universal visibility boundary before any
    // destructive deletion. Filter CAS-derived historical bindings as well as
    // current ones so stale SQLite rows cannot leak through text/vector/history
    // search or a signed cursor replay.
    let mut blocked_raws = BTreeMap::<String, bool>::new();
    for binding in &history_plan.bindings {
        if !blocked_raws.contains_key(&binding.raw_hash) {
            blocked_raws.insert(
                binding.raw_hash.clone(),
                purge_blocks_raw(&exec.target, &binding.raw_hash)
                    .map_err(ScopeSearchError::Fatal)?,
            );
        }
    }
    history_plan.bindings.retain(|binding| {
        !blocked_raws
            .get(&binding.raw_hash)
            .copied()
            .unwrap_or(false)
    });
    install_eligible_identities(&conn, &history_plan).map_err(ScopeSearchError::Fatal)?;

    // P10: `run_reindex` advances HEAD to a new generation and only afterwards
    // swaps in the rebuilt sqlite (P5's temp+rename). A concurrent search in that
    // window reads HEAD=C_new against the pre-swap db, whose chunks are all the
    // previous generation and join to none of C_new's freshly projected
    // `tree_entries` — every backend returns empty and the search would emit a
    // silent exit-0 no-hit indistinguishable from a genuine miss. Detect that
    // precise state and exclude the scope with `KCS-E-INDEX-REBUILDING-001`
    // (docs/05:564) so the honest transient surfaces instead. `kcs index` re-gens
    // only the changed docs (unchanged docs stay live → never fires); an empty or
    // text-less scope has no chunks (never fires); a genuine miss still has live
    // chunks (never fires) — see `index_is_rebuilding`. 05 §1.8 part-failure keeps
    // the other, healthy scopes' results.
    if matches!(time.selector, TimeSelector::Current)
        && index_is_rebuilding(&conn, &snapshot_commit).map_err(ScopeSearchError::Fatal)?
    {
        return Err(ScopeSearchError::Excluded(
            INDEX_REBUILDING_REASON.to_owned(),
        ));
    }

    let max_rowid = match exec.max_rowid {
        Some(value) => value,
        None => current_max_rowid(&conn).map_err(ScopeSearchError::Fatal)?,
    };

    let max_association_rowid = match exec.max_association_rowid {
        Some(value) => value,
        None => kcs_index::fts::max_chunk_config_association_rowid(&conn)
            .map_err(index_to_kcs)
            .map_err(ScopeSearchError::Fatal)?,
    };

    let chunking_config_hash = read_chunking_config(&repo)
        .map(|config| config.chunking_config_hash)
        .map_err(ScopeSearchError::Fatal)?;
    if exec
        .chunking_config_hash
        .as_deref()
        .is_some_and(|frozen| frozen != chunking_config_hash.as_str())
    {
        return Err(ScopeSearchError::Fatal(KcsError::new(
            "KCS-E-SEARCH-CURSOR-001",
            "search cursor chunking config changed",
            json!({ "scope_id": exec.target.scope_id }),
            ExitCode::InvalidUsage,
        )));
    }

    let want_vector = matches!(resolved_mode, SearchMode::Hybrid | SearchMode::Vector);

    // FTS5 text ranks (empty when the query has no indexable token). Vector-only
    // mode skips the text backend entirely (05 §1.3: no fusion, use vector order).
    let (text_ranks, mut meta) = if resolved_mode == SearchMode::Vector {
        (Vec::new(), BTreeMap::new())
    } else {
        fts_scope_search(
            &conn,
            tiers,
            &chunking_config_hash,
            max_rowid,
            max_association_rowid,
            history_plan.since_cutoff.as_deref(),
        )
        .map_err(ScopeSearchError::Fatal)?
    };

    // chunk_vec KNN vector ranks (hybrid/vector mode with a query embedding).
    let vector_ranks = if want_vector {
        if let Some(query_vec) = query_embedding {
            let (ranks, vmeta) = match vector_scope_search(
                &conn,
                query_vec,
                &chunking_config_hash,
                max_rowid,
                max_association_rowid,
                history_plan.since_cutoff.as_deref(),
            ) {
                Ok(result) => result,
                // R10-1(a): a sqlite-vec capacity limit degrades THIS scope's vector
                // backend to text-only (05 §1.8 per-scope isolation) instead of a
                // device-wide Fatal misreported as CONFIG-SCHEMA. The text ranks
                // computed above still stand; pure-vector mode simply contributes
                // nothing from this scope rather than aborting the whole search.
                Err(error) if error.error_code() == VECTOR_CAPACITY_ERROR_CODE => {
                    (Vec::new(), BTreeMap::new())
                }
                Err(error) => return Err(ScopeSearchError::Fatal(error)),
            };
            for (chunk_id, chunk_meta) in vmeta {
                meta.entry(chunk_id).or_insert(chunk_meta);
            }
            ranks
        } else {
            Vec::new()
        }
    } else {
        Vec::new()
    };

    // R12-1: fuse with the effective `[search.rrf]` (was hardcoded 60/1/1/200).
    let fused = fuse_rrf(&text_ranks, &vector_ranks, rrf_config)
        .map_err(search_to_kcs)
        .map_err(ScopeSearchError::Fatal)?;

    let grouped_bindings = history_plan.grouped_bindings();
    let mut candidates = Vec::new();
    for candidate in fused {
        let Some(chunk_meta) = meta.get(&candidate.chunk_hash) else {
            continue;
        };
        // In hybrid/vector mode, carry the chunk's embedding so MMR can run
        // (05 §1.4). Text mode leaves this `None` (MMR skips, dedup only).
        let embedding = if want_vector {
            embedding_store::read_chunk_vector(&conn, &candidate.chunk_hash)
                .ok()
                .flatten()
        } else {
            None
        };
        candidates.push(ScoredCandidate {
            scope_index,
            scope_id: exec.target.scope_id.clone(),
            scope_path: exec.target.repo_root.clone(),
            chunk_hash: candidate.chunk_hash,
            rrf_score: candidate.rrf_score,
            meta: chunk_meta.clone(),
            bindings: grouped_bindings
                .get(&SearchContentKey {
                    raw_hash: chunk_meta.raw_hash.clone(),
                    tool_profile_hash: chunk_meta.tool_profile_hash.clone(),
                    gen: chunk_meta.gen,
                })
                .cloned()
                .unwrap_or_default(),
            embedding,
        });
    }

    // Linearize the lock-free read after SQLite/vector metadata access. A purge
    // may publish its barrier while the query is running; candidates blocked in
    // that window must not cross the response boundary.
    let mut blocked_after_query = BTreeMap::<String, bool>::new();
    for candidate in &candidates {
        if !blocked_after_query.contains_key(&candidate.meta.raw_hash) {
            blocked_after_query.insert(
                candidate.meta.raw_hash.clone(),
                purge_blocks_raw(&exec.target, &candidate.meta.raw_hash)
                    .map_err(ScopeSearchError::Fatal)?,
            );
        }
    }
    candidates.retain(|candidate| {
        !blocked_after_query
            .get(&candidate.meta.raw_hash)
            .copied()
            .unwrap_or(false)
    });

    Ok(ScopeOutcome {
        snapshot_commit,
        max_rowid,
        max_association_rowid,
        chunking_config_hash,
        candidates,
    })
}

/// sqlite-vec's hard upper bound on a KNN `LIMIT ?` (`k`). A query above it fails
/// the whole statement; R10-1 caps the over-fetch here.
const VECTOR_KNN_MAX_K: u64 = 4096;

/// Error code for a per-scope vector-backend capacity limit (R10-1(a)). Never
/// surfaced to the user: `search_one_scope` intercepts it and degrades that scope
/// to text-only so one scope's limit can't abort the device-wide search.
const VECTOR_CAPACITY_ERROR_CODE: &str = "KCS-E-SEARCH-VEC-CAPACITY-001";

/// Whether an index error is a sqlite-vec / SQLite capacity limit (KNN `k` ceiling
/// or bound-variable ceiling) rather than a genuine schema/contract fault.
fn is_vector_capacity_error(error: &kcs_index::IndexError) -> bool {
    is_vector_capacity_message(&error.to_string())
}

/// Message classifier for [`is_vector_capacity_error`], split out for unit testing.
fn is_vector_capacity_message(message: &str) -> bool {
    // sqlite-vec: "k value in knn query too large, provided N and the limit is 4096".
    // SQLite:     "too many SQL variables".
    message.contains("knn query too large") || message.contains("too many SQL variables")
}

/// Internal marker error the vector backend returns on a capacity limit so the
/// caller can degrade the scope (R10-1(a)); its exit code is irrelevant because it
/// is always intercepted before it can surface.
fn vector_capacity_error() -> KcsError {
    KcsError::new(
        VECTOR_CAPACITY_ERROR_CODE,
        "vector backend capacity limit exceeded for this scope",
        json!({}),
        ExitCode::Failure,
    )
}

/// Per-scope vector backend: the query embedding's KNN over `chunk_vec`, filtered
/// to the same live chunk set as the text backend (current `chunking_config_hash`,
/// HEAD `tree_entries`, and `rowid <= max_rowid`). Because sqlite-vec applies the
/// KNN `LIMIT` before the liveness join, we over-fetch every `chunk_vec` row and
/// filter in Rust (correct at MVP scale; a future optimization is sqlite-vec
/// metadata partitioning). Ranks are 1-based over the surviving candidates ordered
/// by (cosine distance, chunk_id) and truncated to `candidate_depth` (05 §1.3).
fn vector_scope_search(
    conn: &Connection,
    query_embedding: &[f32],
    chunking_config_hash: &str,
    max_rowid: u64,
    max_association_rowid: u64,
    since_cutoff: Option<&str>,
) -> Result<(Vec<BackendRank>, BTreeMap<String, ChunkMeta>)> {
    let total = embedding_store::chunk_vec_count(conn).map_err(index_to_kcs)?;
    if total == 0 || query_embedding.len() != CHUNK_VEC_DIMENSIONS {
        return Ok((Vec::new(), BTreeMap::new()));
    }
    let query_bytes = f32_to_le_bytes(query_embedding);
    // R10-1: sqlite-vec rejects a KNN `k` above its hard 4096 ceiling, so a scope
    // that embedded >4096 chunks would explode the whole (multi-scope) search with a
    // spurious `KCS-E-CONFIG-SCHEMA-001` exit 2 — taking every healthy scope down
    // with it. Cap `k` at the ceiling: only `candidate_depth` (200) rows survive
    // downstream anyway, and the 4096 window keeps recall high even when stale-gen
    // rows pad the table (paging is the eventual real fix). `chunk_ids <= k <= 4096`
    // also keeps `fetch_live_meta` well under SQLite's 32 766 bound-variable limit.
    let k = total.min(VECTOR_KNN_MAX_K);
    let knn = match embedding_store::knn_chunk_distances(conn, &query_bytes, k) {
        Ok(knn) => knn,
        // R10-1(a): any residual sqlite-vec capacity limit (a corrupt vec index, a
        // future call path) is a per-scope degradation, not a device-wide Fatal —
        // surface a recognizable code the caller maps to a text-only fallback so the
        // 05 §1.8 isolation contract holds and no false CONFIG-SCHEMA is emitted.
        Err(err) if is_vector_capacity_error(&err) => return Err(vector_capacity_error()),
        Err(err) => return Err(index_to_kcs(err)),
    };
    let chunk_ids = knn.iter().map(|(id, _)| id.clone()).collect::<Vec<_>>();
    let meta = fetch_live_meta(
        conn,
        &chunk_ids,
        chunking_config_hash,
        max_rowid,
        max_association_rowid,
        since_cutoff,
    )?;
    let mut kept = knn
        .into_iter()
        .filter(|(id, _)| meta.contains_key(id))
        .collect::<Vec<_>>();
    kept.sort_by(|a, b| a.1.total_cmp(&b.1).then_with(|| a.0.cmp(&b.0)));
    kept.truncate(200);
    let ranks = kept
        .iter()
        .enumerate()
        .map(|(index, (chunk_id, _))| BackendRank {
            chunk_hash: chunk_id.clone(),
            rank: index as u64 + 1,
        })
        .collect();
    Ok((ranks, meta))
}

/// Fetch [`ChunkMeta`] for `chunk_ids` restricted to the live chunk set of
/// `snapshot_commit` (same predicates as [`execute_fts_tier`]). Chunk ids not in
/// the live set are simply absent from the result.
fn fetch_live_meta(
    conn: &Connection,
    chunk_ids: &[String],
    chunking_config_hash: &str,
    max_rowid: u64,
    max_association_rowid: u64,
    since_cutoff: Option<&str>,
) -> Result<BTreeMap<String, ChunkMeta>> {
    if chunk_ids.is_empty() {
        return Ok(BTreeMap::new());
    }
    let placeholders = chunk_ids.iter().map(|_| "?").collect::<Vec<_>>().join(",");
    let sql = format!(
        "SELECT c.chunk_id, c.raw_hash, c.tool_profile_hash, c.heading_path,
                c.section_id, c.char_start, c.char_end, c.text, c.gen
         FROM chunks c
         WHERE c.first_seen_commit IS NOT NULL
             AND c.rowid <= ?2
             AND EXISTS (
                 SELECT 1 FROM chunk_config_generations cg
                 WHERE cg.chunk_id = c.chunk_id
                   AND cg.chunking_config_hash = ?1
                   AND cg.association_rowid <= ?3
             )
             AND EXISTS (
                 SELECT 1 FROM kcs_eligible_identity eligible
                 WHERE eligible.raw_hash = c.raw_hash
                   AND eligible.tool_profile_hash = c.tool_profile_hash
                   AND eligible.gen = c.gen
             )
             AND (?4 IS NULL OR c.created_at >= ?4)
             AND c.chunk_id IN ({placeholders})"
    );
    let mut params: Vec<Box<dyn rusqlite::ToSql>> = vec![
        Box::new(chunking_config_hash.to_owned()),
        Box::new(max_rowid as i64),
        Box::new(max_association_rowid as i64),
        Box::new(since_cutoff.map(str::to_owned)),
    ];
    for chunk_id in chunk_ids {
        params.push(Box::new(chunk_id.clone()));
    }
    let param_refs = params
        .iter()
        .map(std::convert::AsRef::as_ref)
        .collect::<Vec<&dyn rusqlite::ToSql>>();
    let mut stmt = conn
        .prepare(&sql)
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let rows = stmt
        .query_map(param_refs.as_slice(), chunk_meta_row)
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let mut meta = BTreeMap::new();
    for row in rows {
        let (chunk_id, chunk_meta) = row.map_err(|err| KcsError::schema(err.to_string()))?;
        meta.insert(chunk_id, chunk_meta);
    }
    Ok(meta)
}

/// Parse the shared 9-column chunk-meta projection into `(chunk_id, ChunkMeta)`.
fn chunk_meta_row(row: &rusqlite::Row) -> rusqlite::Result<(String, ChunkMeta)> {
    let chunk_id = row.get::<_, String>(0)?;
    let heading_path_raw = row.get::<_, Option<String>>(3)?;
    Ok((
        chunk_id,
        ChunkMeta {
            raw_hash: row.get(1)?,
            tool_profile_hash: row.get(2)?,
            gen: row.get::<_, i64>(8)? as u64,
            heading_path: heading_path_raw
                .and_then(|value| serde_json::from_str::<Vec<String>>(&value).ok()),
            section_id: row
                .get::<_, Option<String>>(4)?
                .filter(|value| !value.is_empty()),
            char_start: row.get::<_, Option<i64>>(5)?.map(|value| value as u64),
            char_end: row.get::<_, Option<i64>>(6)?.map(|value| value as u64),
            text: row.get(7)?,
        },
    ))
}

/// Per-scope text backend: execute the tiered MATCH queries (see
/// [`build_fts_tiers`]) in order; the first tier returning any candidate is the
/// scope's text backend. The candidate list handed to RRF comes from exactly one
/// executed query, ranked purely by that query's BM25 (05 §1.3 / K2 ruling — no
/// post-hoc re-ordering by hand-computed features).
fn fts_scope_search(
    conn: &Connection,
    tiers: &[String],
    chunking_config_hash: &str,
    max_rowid: u64,
    max_association_rowid: u64,
    since_cutoff: Option<&str>,
) -> Result<(Vec<BackendRank>, BTreeMap<String, ChunkMeta>)> {
    for match_expr in tiers {
        let (ranks, meta) = execute_fts_tier(
            conn,
            match_expr,
            chunking_config_hash,
            max_rowid,
            max_association_rowid,
            since_cutoff,
        )?;
        if !ranks.is_empty() {
            return Ok((ranks, meta));
        }
    }
    Ok((Vec::new(), BTreeMap::new()))
}

/// One FTS5 MATCH restricted to the live chunk set of `snapshot_commit`: the
/// current `chunking_config_hash` (04 §4.6, K8b) joined to `tree_entries`
/// (05 §1.6) and frozen by `rowid <= max_rowid` (CT3-CURSOR-002). Rank order is
/// BM25 with column weighting `bm25(chunk_fts, 1.0, 0.3)` — `heading_path` is
/// down-weighted so a parent heading that propagates to every child chunk does
/// not dominate the chunk body (legitimate BM25 configuration per the K2 ruling).
/// Ties break on chunk_id.
fn execute_fts_tier(
    conn: &Connection,
    match_expr: &str,
    chunking_config_hash: &str,
    max_rowid: u64,
    max_association_rowid: u64,
    since_cutoff: Option<&str>,
) -> Result<(Vec<BackendRank>, BTreeMap<String, ChunkMeta>)> {
    let sql = "SELECT c.chunk_id, c.raw_hash, c.tool_profile_hash, c.heading_path,
                      c.section_id, c.char_start, c.char_end, c.text, c.gen,
                      bm25(chunk_fts, 1.0, 0.3) AS score
               FROM chunk_fts f
               JOIN chunks c ON c.rowid = f.rowid
               WHERE chunk_fts MATCH ?1
                   AND c.first_seen_commit IS NOT NULL
                   AND c.rowid <= ?3
                   AND EXISTS (
                       SELECT 1 FROM chunk_config_generations cg
                       WHERE cg.chunk_id = c.chunk_id
                         AND cg.chunking_config_hash = ?2
                         AND cg.association_rowid <= ?4
                   )
                   AND EXISTS (
                       SELECT 1 FROM kcs_eligible_identity eligible
                       WHERE eligible.raw_hash = c.raw_hash
                         AND eligible.tool_profile_hash = c.tool_profile_hash
                         AND eligible.gen = c.gen
                   )
                   AND (?5 IS NULL OR c.created_at >= ?5)
               ORDER BY score, c.chunk_id
               LIMIT 200";
    let mut stmt = conn
        .prepare(sql)
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let rows = stmt
        .query_map(
            rusqlite::params![
                match_expr,
                chunking_config_hash,
                max_rowid as i64,
                max_association_rowid as i64,
                since_cutoff,
            ],
            chunk_meta_row,
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;

    let mut ranks = Vec::new();
    let mut meta = BTreeMap::new();
    for (index, row) in rows.enumerate() {
        let (chunk_id, chunk_meta) = row.map_err(|err| KcsError::schema(err.to_string()))?;
        ranks.push(BackendRank {
            chunk_hash: chunk_id.clone(),
            rank: index as u64 + 1,
        });
        meta.insert(chunk_id, chunk_meta);
    }
    Ok((ranks, meta))
}

fn current_max_rowid(conn: &Connection) -> Result<u64> {
    let value: i64 = conn
        .query_row("SELECT COALESCE(MAX(rowid), 0) FROM chunks", [], |row| {
            row.get(0)
        })
        .map_err(|err| KcsError::schema(err.to_string()))?;
    Ok(value as u64)
}

/// R16-3: the tri-state disposition of a commit's `tree_entries` availability for a
/// search. Distinguishing "shallow but serviceable from cache" from "shallow with
/// nothing to serve" is what turns the former `bool` (which silently swallowed a
/// missing tree on the fresh path into an exit-0 empty page) into a loud, honest
/// exclusion. "Shallow" here covers BOTH a missing tree object AND a missing commit
/// object (R16-1): a *deleted* object (KCS-E-STORE-NOT-FOUND-001). A *corrupt*
/// object (hash mismatch, KCS-E-STORE-CORRUPT-001) is NOT folded in here — it
/// propagates as `Err` so the search loop's R16-2 per-scope isolation records it as
/// `store_corrupt` instead.
enum SnapshotTreeEntries {
    /// Rows are present (freshly projected or already cached) AND the backing commit
    /// and tree objects are present. A normal, healthy search proceeds.
    Projected,
    /// The commit or tree object is gone, BUT `tree_entries` rows are already cached
    /// in sqlite. A fresh search can still run against those rows — results are real
    /// and Evidence resolves via raw_hash/chunk_hash direct resolution (docs/05 §3.6:
    /// resolving a shallow-commit pointer never fails). A cursor replay still hard-fails.
    ShallowCachedRows,
    /// The commit or tree object is gone AND no `tree_entries` rows are cached — there
    /// is nothing to search. A fresh search excludes the scope (`snapshot_shallow`)
    /// rather than emitting a silent exit-0 empty page (R16-3); a cursor replay
    /// hard-fails (05 §2.2).
    ShallowNoRows,
}

/// Ensure `tree_entries` rows for `commit_hash` exist in `conn`, projecting them
/// from the commit's tree object when absent (04 §4.5). Returns the tri-state
/// [`SnapshotTreeEntries`] disposition: `Projected` when the snapshot is fully
/// backed, or a `Shallow*` variant when the commit/tree object is gone (the caller
/// decides fresh-vs-cursor policy). A *corrupt* (not merely missing) object still
/// propagates as `Err`.
fn ensure_snapshot_tree_entries(
    repo: &Repository,
    conn: &Connection,
    commit_hash: &str,
) -> Result<SnapshotTreeEntries> {
    // R11-11 (Spark): existence probe only — an EXISTS/LIMIT-1 stops at the first
    // matching row instead of a `COUNT(*)` PK-prefix scan over every tree_entries
    // row of the commit (wasteful for large commits). Functionally equivalent.
    let existing: bool = conn
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM tree_entries WHERE commit_hash = ?1)",
            rusqlite::params![commit_hash],
            |row| row.get(0),
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
    // The shallow disposition when the commit/tree object is gone depends on whether
    // rows are cached: with cache we can still serve (ShallowCachedRows), without it
    // there is nothing to serve (ShallowNoRows). R16-1: a missing *commit* object is
    // handled symmetrically to a missing tree — both are absorbed here (only when
    // STORE-NOT-FOUND; a corrupt object propagates as Err for R16-2).
    let shallow = if existing {
        SnapshotTreeEntries::ShallowCachedRows
    } else {
        SnapshotTreeEntries::ShallowNoRows
    };
    let commit = match repo.read_commit(commit_hash) {
        Ok(commit) => commit,
        Err(error) if is_store_not_found(&error) => return Ok(shallow),
        Err(error) => return Err(error),
    };
    if existing {
        // Cached — but a cursor replay still needs the tree object to prove the
        // snapshot is not shallow, so verify object presence regardless.
        return match repo.read_tree(&commit.tree) {
            Ok(_) => Ok(SnapshotTreeEntries::Projected),
            Err(error) if is_store_not_found(&error) => Ok(SnapshotTreeEntries::ShallowCachedRows),
            Err(error) => Err(error),
        };
    }
    let tree = match repo.read_tree(&commit.tree) {
        Ok(tree) => tree,
        Err(error) if is_store_not_found(&error) => return Ok(SnapshotTreeEntries::ShallowNoRows),
        Err(error) => return Err(error),
    };
    // Resolve every row first (the `latest_normalize_ref` lookups do file I/O) so the
    // insert transaction below stays tight and holds no I/O. Step 4 historical search
    // uses its own exact CAS planner and does not treat this compatibility cache as
    // truth.
    let mut rows: Vec<TreeEntryProjection> = Vec::new();
    for entry in &tree.entries {
        let normalize = match &entry.normalize {
            Some(normalize) => normalize.clone(),
            None => match latest_normalize_ref(repo.kcs_dir(), &entry.raw_hash)? {
                Some(normalize) => normalize,
                None => continue,
            },
        };
        rows.push(TreeEntryProjection {
            path: entry.path.clone(),
            raw_hash: entry.raw_hash.clone(),
            tool_profile_hash: Some(normalize.tool_profile_hash.clone()),
            gen: normalize.gen,
        });
    }
    insert_snapshot_tree_entries(conn, commit_hash, &rows)?;
    Ok(SnapshotTreeEntries::Projected)
}

/// One projected `tree_entries` row for [`insert_snapshot_tree_entries`].
struct TreeEntryProjection {
    path: String,
    raw_hash: String,
    tool_profile_hash: Option<String>,
    gen: u64,
}

/// R10-8: insert a commit's projected `tree_entries` rows in ONE transaction. The
/// lazy projection is read-triggered (search/cursor/short-hash), and the caller
/// short-circuits when `existing > 0`; a non-transactional loop that crashed
/// mid-way left a partial row set that `existing > 0` then refused to complete, so
/// some paths of that commit stayed unresolvable until the next full reindex.
/// Wrapping the inserts makes the projection all-or-nothing: an interruption rolls
/// every row back, keeping `existing = 0` so the next read reprojects cleanly.
fn insert_snapshot_tree_entries(
    conn: &Connection,
    commit_hash: &str,
    rows: &[TreeEntryProjection],
) -> Result<()> {
    let tx = conn
        .unchecked_transaction()
        .map_err(|err| KcsError::schema(err.to_string()))?;
    for row in rows {
        tx.execute(
            "INSERT OR REPLACE INTO tree_entries(commit_hash, path, raw_hash, tool_profile_hash, gen)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            rusqlite::params![
                commit_hash,
                row.path,
                row.raw_hash,
                row.tool_profile_hash,
                row.gen
            ],
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
    }
    tx.commit()
        .map_err(|err| KcsError::schema(err.to_string()))?;
    Ok(())
}

/// P10: is the search index caught in the reindex HEAD-advance window? `run_reindex`
/// advances HEAD to a new generation and only afterwards rebuilds sqlite (temp+
/// rename, P5). In that window a concurrent search reads HEAD=C_new against the
/// pre-swap db, whose chunks are all the *previous* generation and so join to none
/// of C_new's projected `tree_entries` — the search would return an exit-0 empty
/// page indistinguishable from a genuine no-hit. Detect it precisely: HEAD has
/// `tree_entries`, not one chunk is live for HEAD, yet the db still holds chunks (an
/// older generation). Three cases stay false, by construction:
/// - a genuine miss / any healthy search has a live chunk (fast-path return);
/// - an empty / text-less scope has no `tree_entries` for HEAD (or no chunks);
/// - `kcs index` re-gens only changed docs, so the unchanged docs' chunks stay live.
///
/// Only the all-docs re-gen of `reindex` empties the live set while chunks remain.
fn index_is_rebuilding(conn: &Connection, snapshot_commit: &str) -> Result<bool> {
    // Fast path (the common, healthy case): any chunk live for HEAD means the index
    // is serviceable, so it is not rebuilding — one EXISTS and we are done.
    let live_exists: i64 = conn
        .query_row(
            "SELECT EXISTS(
                 SELECT 1 FROM chunks c
                 JOIN tree_entries te ON te.commit_hash = ?1
                     AND te.raw_hash = c.raw_hash
                     AND te.tool_profile_hash = c.tool_profile_hash
                     AND te.gen = c.gen)",
            rusqlite::params![snapshot_commit],
            |row| row.get(0),
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
    if live_exists != 0 {
        return Ok(false);
    }
    // No live chunk. A legitimately empty or text-less scope has no `tree_entries`
    // for HEAD; an exit-0 empty page is correct there, not rebuilding.
    let head_has_tree_entries: i64 = conn
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM tree_entries WHERE commit_hash = ?1)",
            rusqlite::params![snapshot_commit],
            |row| row.get(0),
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
    if head_has_tree_entries == 0 {
        return Ok(false);
    }
    // HEAD has `tree_entries` yet not one live chunk. If the db still holds chunks
    // of an older generation, reindex advanced HEAD before swapping in the rebuilt
    // sqlite — the exact HEAD-vs-sqlite window. (A never-chunked scope has none.)
    let any_chunk: i64 = conn
        .query_row("SELECT EXISTS(SELECT 1 FROM chunks)", [], |row| row.get(0))
        .map_err(|err| KcsError::schema(err.to_string()))?;
    Ok(any_chunk != 0)
}

/// Apply diversify (05 §1.4/§1.8) to the merged candidate pool and report the
/// strategy actually applied. Text-only (no embeddings) means MMR is skipped and
/// only the `max_per_raw_hash` dedup runs — reported honestly as
/// `group_by_raw_hash`, never a phantom "mmr" (K2 fix for the false report).
fn diversify_merged<'a>(
    candidates: &'a [ScoredCandidate],
    resolved_mode: SearchMode,
    request: &DiversifyRequest,
) -> Result<(Vec<&'a ScoredCandidate>, Value)> {
    let mmr_candidates = candidates
        .iter()
        .enumerate()
        .map(|(index, candidate)| MmrCandidate {
            // Composite id keeps candidates distinct even if two scopes carry the
            // same chunk_hash; raw_hash stays real so cross-scope dedup counts them
            // together (CT3-MULTI-003).
            chunk_hash: format!("{index}\u{0}{}", candidate.chunk_hash),
            raw_hash: candidate.meta.raw_hash.clone(),
            relevance: candidate.rrf_score,
            // Real embedding in hybrid/vector mode (05 §1.4). If any candidate
            // lacks one, `diversify_candidates` skips MMR and only dedups.
            embedding: candidate.embedding.clone(),
            heading_path: candidate.meta.heading_path.clone(),
            section_id: candidate.meta.section_id.clone(),
        })
        .collect::<Vec<_>>();

    let diversified = diversify_candidates(
        &mmr_candidates,
        MmrConfig {
            strategy: request.strategy,
            mmr_lambda: request.mmr_lambda.unwrap_or(0.7),
            max_per_raw_hash: request.max_per_raw_hash.unwrap_or(3),
            mmr_depth: request.mmr_depth.unwrap_or(100),
        },
    )
    .map_err(search_to_kcs)?;

    let ordered = diversified
        .iter()
        .filter_map(|item| {
            item.chunk_hash
                .split_once('\u{0}')
                .and_then(|(index, _)| index.parse::<usize>().ok())
                .and_then(|index| candidates.get(index))
        })
        .collect::<Vec<_>>();

    // Report the strategy actually applied (05 §1.7). MMR needs an embedding for
    // *every* candidate (mmr.rs skips otherwise); text mode carries none, so only
    // the raw_hash dedup ran — reported honestly, never a phantom "mmr" (K2).
    let all_have_embeddings = !candidates.is_empty()
        && candidates
            .iter()
            .all(|candidate| candidate.embedding.is_some());
    let mmr_ran = matches!(resolved_mode, SearchMode::Hybrid | SearchMode::Vector)
        && request.strategy == DiversifyStrategy::Mmr
        && all_have_embeddings;
    let summary = match request.strategy {
        DiversifyStrategy::Off => json!({ "strategy": "off" }),
        DiversifyStrategy::Mmr if mmr_ran => {
            json!({ "strategy": "mmr", "mmr_lambda": request.mmr_lambda.unwrap_or(0.7) })
        }
        _ => json!({ "strategy": "group_by_raw_hash" }),
    };
    Ok((ordered, summary))
}

/// Aggregate `index_status` (05 §1.7, CT3-OBS-001) over the searched scopes.
/// `enriched_ratio` = done AI-enrichment tasks / all AI-enrichment tasks pooled
/// across scopes (count-weighted average). Enrichment tasks are Markdownize +
/// Embedding; "done" is `Done`/`Partial`. `budget_paused` is a budget-paused task or
/// an exhausted monthly budget (R22-7 — a secrets hold pauses work but not for budget).
fn compute_index_status(searched: &[SearchedScopeInfo]) -> Value {
    let mut total = 0u64;
    let mut done = 0u64;
    let mut pending = 0u64;
    let mut budget_paused = false;
    let mut unsupported_inputs = Vec::new();
    let mut unsupported_input_errors = Vec::new();
    let mut task_errors = Vec::new();

    for scope in searched {
        let kcs_dir = scope.scope_path.join(".kcs");
        let store = TaskStore::new(&kcs_dir);
        let tasks = match store.all() {
            Ok(tasks) => tasks,
            Err(error) => {
                let error = pipeline_to_kcs(error);
                task_errors.push(json!({
                    "scope_path": scope.scope_path,
                    "error_code": error.error_code(),
                    "message": error.message(),
                }));
                Vec::new()
            }
        };
        for task in tasks {
            if !matches!(task.task_type, TaskType::Markdownize | TaskType::Embedding) {
                continue;
            }
            // R20-7: a `retired_non_live` task's chunk went non-live (deleted / re-chunked /
            // superseded), so it is NOT an enrichment gap in the CURRENT corpus and must not
            // deflate enriched_ratio. R11-8 deliberately keeps a LIVE permanent-gap Failed
            // (invalid_input/contract) in the denominator; this excludes only the non-live
            // subset, which R19-3's dedicated reason makes unambiguous. Without this, a
            // deleted/reverted chunk left enriched_ratio < 1.0 with pending == 0 forever.
            if task.fallback_reason.as_deref() == Some(RETIRED_NON_LIVE) {
                continue;
            }
            total += 1;
            match task.status {
                TaskStatus::Done => done += 1,
                // R9-4: a Partial task has Failed units still awaiting completion —
                // count it as incomplete (pending), not done. Counting it as done
                // made `index_status` report enriched_ratio = 1.0 with
                // pending_enrichment_tasks = 0 while units were permanently missing
                // (a silent data gap on text-layer-less scans). `batch retry` now
                // drives it to Done (docs/04 §5.2).
                TaskStatus::Partial | TaskStatus::Pending | TaskStatus::Running => pending += 1,
                // R22-7: only a BUDGET pause may set `budget_paused`. docs/05-runtime.md:200
                // has agents render this flag as "(budget により一時停止中)", so a Tier B
                // `secrets_tier_b_hold` — which costs nothing and is cleared by
                // `--send-secrets`, never by raising a cap — was steering them to
                // `--override-budget` while `device_remaining_usd` sat untouched at its full
                // cap. It is still outstanding work, so it stays in `pending`.
                TaskStatus::Paused => {
                    pending += 1;
                    if task.fallback_reason.as_deref() == Some("budget_exceeded") {
                        budget_paused = true;
                    }
                }
                // R11-8: a RETRYABLE Failed enrichment task (rate_limit etc., holding
                // next_retry_at, recoverable by `batch retry`) is outstanding work —
                // count it as pending. Otherwise the scope reads enriched_ratio<1.0
                // with pending_enrichment_tasks=0 and budget_paused=false, an
                // impossible-looking dead end an Agent cannot act on (the dual of
                // R9-4). A NON-retryable Failed task (permanent gap) stays excluded:
                // it surfaces only as ratio<1.0, never as actionable pending work.
                TaskStatus::Failed if task_retry_allowed(&task) => pending += 1,
                TaskStatus::Failed => {}
            }
        }
        match Repository::open(&scope.scope_path) {
            Ok(repo) => {
                match current_unsupported_inputs(&repo) {
                    Ok(dispositions) => {
                        total = total.saturating_add(dispositions.len() as u64);
                        unsupported_inputs.extend(dispositions.into_iter().map(|disposition| {
                            json!({
                                "scope_path": scope.scope_path,
                                "path": disposition.path,
                                "raw_hash": disposition.raw_hash,
                                "media_type": disposition.media_type,
                                "size_bytes": disposition.size_bytes,
                                "reason": disposition.reason,
                            })
                        }));
                    }
                    Err(error) => unsupported_input_errors.push(json!({
                        "scope_path": scope.scope_path,
                        "error_code": error.error_code(),
                        "message": error.message(),
                    })),
                }
                if let Ok(budget) = budget_status_json(&repo) {
                    let device = budget
                        .get("device_remaining_usd")
                        .and_then(Value::as_f64)
                        .unwrap_or(f64::INFINITY);
                    let folder = budget
                        .get("folder_remaining_usd")
                        .and_then(Value::as_f64)
                        .unwrap_or(f64::INFINITY);
                    if device <= 0.0 || folder <= 0.0 {
                        budget_paused = true;
                    }
                }
            }
            Err(error) => {
                let error = json!({
                    "scope_path": scope.scope_path,
                    "error_code": error.error_code(),
                    "message": error.message(),
                });
                task_errors.push(error.clone());
                unsupported_input_errors.push(error);
            }
        }
    }

    let enriched_ratio = if total == 0 {
        1.0
    } else {
        done as f64 / total as f64
    };
    let unsupported_inputs_complete = unsupported_input_errors.is_empty();
    let tasks_complete = task_errors.is_empty();
    json!({
        "enriched_ratio": enriched_ratio,
        "pending_enrichment_tasks": pending,
        "budget_paused": budget_paused,
        "unsupported_inputs": unsupported_inputs,
        "unsupported_input_errors": unsupported_input_errors,
        "unsupported_inputs_complete": unsupported_inputs_complete,
        "task_errors": task_errors,
        "tasks_complete": tasks_complete,
    })
}

fn current_unsupported_inputs(repo: &Repository) -> Result<Vec<UnsupportedInputDisposition>> {
    let store = UnsupportedInputStore::new(repo.kcs_dir());
    let dispositions = store.latest_by_path().map_err(pipeline_to_kcs)?;
    let Some(head) = repo.head_commit_hash()? else {
        return Ok(Vec::new());
    };
    let commit = repo.read_commit(&head)?;
    let tree = repo.read_tree(&commit.tree)?;
    let live = tree
        .entries
        .into_iter()
        .map(|entry| (entry.path, entry.raw_hash))
        .collect::<BTreeMap<_, _>>();
    Ok(dispositions
        .into_iter()
        .filter(|disposition| {
            disposition.reason == UNSUPPORTED_REASON_UNRECOGNIZED_BINARY
                && live.get(&disposition.path) == Some(&disposition.raw_hash)
        })
        .collect())
}

fn record_unsupported_if_changed(
    store: &UnsupportedInputStore,
    latest_by_path: &mut BTreeMap<String, UnsupportedInputDisposition>,
    disposition: UnsupportedInputDisposition,
) -> Result<bool> {
    if latest_by_path.get(&disposition.path) == Some(&disposition) {
        return Ok(false);
    }
    store.record(&disposition).map_err(pipeline_to_kcs)?;
    latest_by_path.insert(disposition.path.clone(), disposition);
    Ok(true)
}

fn scope_all_failed_error(message: &str, excluded: Vec<Value>) -> KcsError {
    KcsError::new(
        "KCS-E-SEARCH-SCOPE-ALL-FAILED-001",
        message,
        json!({ "excluded_scopes": excluded }),
        ExitCode::PermanentFailure,
    )
}

/// R17-4/R18-4: the class-specific recovery hint for a store-corruption search
/// exclusion reason (`store_corrupt` / `snapshot_shallow`), or `None` for any other
/// reason (`index_missing`/`index_corrupt` recover via the exit-1 VEC-UNAVAIL path,
/// transient reasons need no guidance). Attached both to each individual
/// `excluded_scopes` entry (R18-4 — so a PARTIAL multi-scope exclusion, where healthy
/// scopes keep `searched` non-empty and skip the all-failed aggregate, is still
/// agent-recoverable) and aggregated into the all-scopes-failed SCOPE-ALL-FAILED
/// response (R17-4). The error CODE stays SCOPE-ALL-FAILED-001 (docs frozen — no new
/// code); only the `recovery` context is added.
fn store_corruption_recovery_hint(reason: &str) -> Option<&'static str> {
    match reason {
        "store_corrupt" => Some(
            "store_corrupt: try `kcs repair --rebuild-db`; if it still fails, restore \
             the corrupt commit/tree object from objects/refs",
        ),
        "snapshot_shallow" => Some(
            "snapshot_shallow: restore the discarded HEAD commit/tree object, or \
             re-run `kcs index` to rebuild the snapshot from the working tree",
        ),
        // R19-6: index_missing/index_corrupt (sqlite.db absent/damaged) are the most
        // common store-corruption class, yet R18-4 only wired the recovery hint for
        // store_corrupt/snapshot_shallow — so a partial exclusion (a healthy scope
        // survives) surfaced these reasons bare, and a heterogeneous all-failed mix
        // fell through both homogeneous aggregations to a hintless message. Same
        // repair path as the others.
        "index_missing" => Some(
            "index_missing: run `kcs repair --rebuild-db` to rebuild the search index \
             from the store",
        ),
        "index_corrupt" => Some(
            "index_corrupt: run `kcs repair --rebuild-db` to rebuild the search index \
             from the store",
        ),
        _ => None,
    }
}

/// R20-8: the deduplicated recovery hints for a set of excluded scopes, in a stable reason
/// order. Aggregates the per-entry `store_corruption_recovery_hint`s into the
/// all-scopes-failed response's top-level `context.recovery` — so the `index_unusable`
/// exit and a HETEROGENEOUS all-failed mix (which R18-4 left hintless) both surface
/// guidance, matching the homogeneous store-corruption branch.
fn aggregate_store_recovery_hints(excluded: &[Value]) -> Vec<&'static str> {
    let mut out: Vec<&'static str> = Vec::new();
    for reason in [
        "store_corrupt",
        "snapshot_shallow",
        "index_missing",
        "index_corrupt",
    ] {
        let present = excluded
            .iter()
            .any(|e| e.get("reason").and_then(Value::as_str) == Some(reason));
        if present {
            if let Some(hint) = store_corruption_recovery_hint(reason) {
                if !out.contains(&hint) {
                    out.push(hint);
                }
            }
        }
    }
    out
}

/// Whether `ch` is a CJK character KCS treats as space-less script (Hiragana,
/// Katakana, CJK Unified Ideographs) — the same ranges as the chunker's slug rule.
fn is_cjk(ch: char) -> bool {
    matches!(
        ch as u32,
        0x3040..=0x309f | 0x30a0..=0x30ff | 0x4e00..=0x9fff
    )
}

/// Split a query into its two kinds of indexable units (deterministic,
/// first-occurrence order, deduplicated; runs shorter than 3 chars are dropped
/// below the trigram floor):
///
/// * `cjk_trigrams` — character 3-grams of each maximal CJK run (>= 3 chars).
///   Japanese carries no whitespace, so substring trigrams are the only way the
///   trigram index can do partial matching.
/// * `keywords` — maximal ASCII/alphanumeric runs (>= 3 chars, edge `.-_`
///   trimmed) such as `Recall`, `0.83`, `TTL`, `Kestrel`. These are the
///   distinctive, high-IDF part of a query.
fn query_units(query: &str) -> (Vec<String>, Vec<String>) {
    let mut trigrams = Vec::<String>::new();
    let mut keywords = Vec::<String>::new();
    let mut seen_tri = std::collections::BTreeSet::<String>::new();
    let mut seen_kw = std::collections::BTreeSet::<String>::new();
    let is_word = |ch: char| !is_cjk(ch) && (ch.is_alphanumeric() || matches!(ch, '.' | '-' | '_'));
    let chars = query.chars().collect::<Vec<_>>();
    let mut i = 0;
    while i < chars.len() {
        if is_cjk(chars[i]) {
            let start = i;
            while i < chars.len() && is_cjk(chars[i]) {
                i += 1;
            }
            let run = &chars[start..i];
            if run.len() >= 3 {
                for window in run.windows(3) {
                    let gram = window.iter().collect::<String>();
                    if seen_tri.insert(gram.clone()) {
                        trigrams.push(gram);
                    }
                }
            }
        } else if is_word(chars[i]) {
            let start = i;
            while i < chars.len() && is_word(chars[i]) {
                i += 1;
            }
            let run = chars[start..i]
                .iter()
                .collect::<String>()
                .trim_matches(|ch| matches!(ch, '.' | '-' | '_'))
                .to_owned();
            if run.chars().count() >= 3 && seen_kw.insert(run.clone()) {
                keywords.push(run);
            }
        } else {
            i += 1;
        }
    }
    (trigrams, keywords)
}

/// Quote a unit as an FTS5 phrase (`"` doubled) so `=`, quotes, and operators in
/// user input are inert — arbitrary input can never raise an FTS5 syntax error
/// (brief-common #6).
fn quote_fts_phrase(unit: &str) -> String {
    format!("\"{}\"", unit.replace('"', "\"\""))
}

/// One keyword as an FTS5 phrase group. Pure-numeric keywords (>= 4 digits) are
/// expanded with their thousands-separator variant *inside the executed query*
/// (`3600` -> `("3600" OR "3,600")`): the same number under display formatting,
/// legitimate query expansion per the K2 ruling — never post-hoc scoring.
fn fts_keyword_group(keyword: &str) -> String {
    let quoted = quote_fts_phrase(keyword);
    if keyword.len() >= 4 && keyword.bytes().all(|b| b.is_ascii_digit()) {
        let variant = thousands_separated(keyword);
        format!("({quoted} OR {})", quote_fts_phrase(&variant))
    } else {
        quoted
    }
}

/// Small deterministic bilingual expansions for core retrieval vocabulary.
/// These are query-construction aliases (like the numeric display variant
/// above), never post-hoc score adjustments. They let an English query match the
/// Japanese technical term that KCS itself exposes throughout the CLI/docs while
/// preserving BM25 as the sole ranking function.
fn fts_keyword_expansions(keyword: &str) -> &'static [&'static str] {
    if keyword.eq_ignore_ascii_case("chunk") || keyword.eq_ignore_ascii_case("chunks") {
        &["チャンク"]
    } else if keyword.eq_ignore_ascii_case("token") || keyword.eq_ignore_ascii_case("tokens") {
        &["トークン"]
    } else if keyword.eq_ignore_ascii_case("pipeline") {
        &["パイプライン"]
    } else {
        &[]
    }
}

fn thousands_separated(digits: &str) -> String {
    let bytes = digits.as_bytes();
    let mut out = String::with_capacity(bytes.len() + bytes.len() / 3);
    for (index, byte) in bytes.iter().enumerate() {
        if index > 0 && (bytes.len() - index) % 3 == 0 {
            out.push(',');
        }
        out.push(*byte as char);
    }
    out
}

/// Build the tiered FTS5 MATCH queries for a natural-language query.
///
/// Query *construction* is adaptive/tiered (K2 coordinator ruling); *ranking* is
/// always the executed query's BM25 — see [`fts_scope_search`]. The shape of the
/// query decides tier 1 deterministically:
///
/// * `>= 2` keyword groups — tier 1 = OR of the keyword groups only. BM25's
///   per-term IDF then favors chunks matching several rare keywords over chunks
///   matching one common one.
/// * exactly 1 keyword group and >= 1 CJK trigram — tier 1 = the keyword group
///   AND an OR-group of the CJK trigrams. A single keyword alone (`6000`) has no
///   discriminating power; requiring co-occurring CJK query context filters the
///   numeric look-alikes.
/// * otherwise no tier 1.
///
/// Tier 2 (always, deduplicated against tier 1) = the relaxed OR of every
/// indexable unit (CJK trigrams + keyword groups). Japanese has no whitespace and
/// the trigram index does substring matching, so a strict AND of whole clauses
/// matches nothing (measured: recall collapses to 0) — the relaxed OR is the
/// floor that keeps natural-language queries answerable.
///
/// Per scope, tiers are executed in order and the first one returning any row is
/// the scope's text backend (fallback trigger: zero candidates — documented,
/// deterministic). The returned list is empty when nothing is indexable
/// (short/empty query -> empty result set).
fn build_fts_tiers(query: &str) -> Vec<String> {
    const MAX_TRIGRAMS: usize = 64;
    let (trigrams, keywords) = query_units(query);
    let trigram_phrases = trigrams
        .iter()
        .take(MAX_TRIGRAMS)
        .map(|trigram| quote_fts_phrase(trigram))
        .collect::<Vec<_>>();
    // R11-10: cap the keyword OR-groups at MAX_TRIGRAMS too (they were unbounded
    // while CJK trigrams were already capped — an asymmetric hardening). `keywords`
    // is dedup'd upstream (query_units), so this is "first 64 after dedup". A
    // multi-thousand-word query no longer builds a multi-thousand-clause OR (linear
    // FTS cost of seconds); SQLite FTS5 tolerates it, but the cost is pointless.
    let mut keyword_groups = Vec::new();
    for keyword in keywords.iter().take(MAX_TRIGRAMS) {
        if keyword_groups.len() >= MAX_TRIGRAMS {
            break;
        }
        keyword_groups.push(fts_keyword_group(keyword));
        for expansion in fts_keyword_expansions(keyword) {
            if keyword_groups.len() >= MAX_TRIGRAMS {
                break;
            }
            let group = fts_keyword_group(expansion);
            if !keyword_groups.contains(&group) {
                keyword_groups.push(group);
            }
        }
    }

    let strict = if keyword_groups.len() >= 2 {
        // Mixed-script queries must retain their CJK context. Dropping it here
        // made a title matching one ASCII acronym outrank a section matching the
        // user's complete Japanese phrase, and prevented the relaxed tier from
        // running because the acronym produced at least one hit.
        let mut units = trigram_phrases.clone();
        units.extend(keyword_groups.iter().cloned());
        Some(units.join(" OR "))
    } else if keyword_groups.len() == 1 && !trigram_phrases.is_empty() {
        Some(format!(
            "{} AND ({})",
            keyword_groups[0],
            trigram_phrases.join(" OR ")
        ))
    } else {
        None
    };
    let relaxed = {
        let mut units = trigram_phrases;
        units.extend(keyword_groups);
        (!units.is_empty()).then(|| units.join(" OR "))
    };

    let mut tiers = Vec::new();
    if let Some(strict) = strict {
        tiers.push(strict);
    }
    if let Some(relaxed) = relaxed {
        if tiers.last() != Some(&relaxed) {
            tiers.push(relaxed);
        }
    }
    tiers
}

fn scope_selection_from_cursor(mode: ScopeMode) -> ScopeSelectionMode {
    match mode {
        ScopeMode::All => ScopeSelectionMode::All,
        ScopeMode::Scope => ScopeSelectionMode::Scope,
        ScopeMode::Descendants => ScopeSelectionMode::Descendants,
    }
}

fn selector_from_cursor(selector: &TimeTravelSelector) -> Result<TimeSelector> {
    TimeSelectorFlags {
        at: selector.at.clone(),
        all_history: selector.all_history,
        include_deleted: selector.include_deleted,
        since: selector.since.clone(),
    }
    .canonicalize()
}

fn selector_for_search(selector: &TimeSelector) -> TimeTravelSelector {
    TimeTravelSelector {
        at: selector.at().map(str::to_owned),
        all_history: selector.all_history(),
        include_deleted: selector.include_deleted(),
        since: selector.since().map(|duration| duration.canonical()),
    }
}

fn cursor_mode_from_selection(mode: ScopeSelectionMode) -> ScopeMode {
    match mode {
        ScopeSelectionMode::All => ScopeMode::All,
        ScopeSelectionMode::Scope => ScopeMode::Scope,
        ScopeSelectionMode::Descendants => ScopeMode::Descendants,
    }
}

/// Resolve a cursor's frozen per-scope sub-cursors into execution scopes. The
/// cursor scope set is authoritative (05 §1.8): scope_id -> path is resolved via
/// the registry. A scope_id the registry can no longer resolve is returned as an
/// `excluded_scopes` entry (reason `unreachable`) rather than dropped silently —
/// the replay then follows partial-failure semantics (exit 3, CT3-MULTI-005),
/// never a misleading cursor-mismatch error.
fn resolve_cursor_exec_scopes(cursor: &CursorToken) -> Result<(Vec<ExecScope>, Vec<Value>)> {
    let mut exec = Vec::new();
    let excluded = cursor
        .excluded_scopes
        .iter()
        .map(|scope| {
            json!({
                "scope_id": scope.scope_id,
                "scope_path": Value::Null,
                "reason": scope.reason,
            })
        })
        .collect::<Vec<_>>();
    for sub in &cursor.scopes {
        // O7: resolve through the shared registry resolver so a scope_id that a
        // `.kcs` copy made ambiguous is reported KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001
        // (like Evidence), not silently pinned to whichever row sorted first.
        match resolve_scope_id_in_registry(&sub.scope_id)? {
            Some(target) => exec.push(ExecScope {
                target,
                snapshot_commit: Some(sub.snapshot_commit.clone()),
                max_rowid: Some(sub.max_rowid),
                max_association_rowid: Some(sub.max_association_rowid),
                chunking_config_hash: Some(sub.chunking_config_hash.clone()),
                from_cursor: true,
            }),
            None => {
                return Err(KcsError::new(
                    "KCS-E-SEARCH-CURSOR-001",
                    "search cursor active scope is no longer reachable; re-run without a cursor",
                    json!({
                        "reason": "active_scope_unavailable",
                        "scope_id": sub.scope_id,
                    }),
                    ExitCode::InvalidUsage,
                ));
            }
        }
    }
    Ok((exec, excluded))
}

fn run_open(args: UnsupportedArgs) -> Result<Value> {
    let raw = read_pointer_input(without_json(args.args))?;
    if let Some(object) = parse_object_uri(&raw)? {
        return resolve_object_uri(&object, false);
    }
    if raw.starts_with("sha256:") {
        return resolve_short_hash_command(&raw, false);
    }
    let pointer = parse_pointer_text(&raw)?;
    let resolved = resolve_pointer_for_cli(&pointer)?;
    Ok(json!({
        "status": "opened",
        "path": resolved.path,
        "raw_hash": pointer.raw_hash,
        "chunk_hash": pointer.chunk_hash,
        "temporary": resolved.temporary,
        "commit_shallow": resolved.commit_shallow,
    }))
}

fn run_view(args: UnsupportedArgs) -> Result<Value> {
    let raw = read_pointer_input(without_json(args.args))?;
    if let Some(object) = parse_object_uri(&raw)? {
        return resolve_object_uri(&object, true);
    }
    if raw.starts_with("sha256:") {
        return resolve_short_hash_command(&raw, true);
    }
    let pointer = parse_pointer_text(&raw)?;
    let resolved = resolve_pointer_for_cli(&pointer)?;
    Ok(json!({
        "status": "viewed",
        "raw_hash": pointer.raw_hash,
        "chunk_hash": pointer.chunk_hash,
        "text": resolved.text.unwrap_or_default(),
        "path": resolved.path,
        // R11-9: mirror `kcs open --json`, which exposes `temporary` from the same
        // resolved pointer — `view` resolves identically and Agents branch on it.
        "temporary": resolved.temporary,
        "commit_shallow": resolved.commit_shallow,
    }))
}

fn run_reindex(args: UnsupportedArgs) -> Result<Value> {
    let parsed = historical_reindex::parse_args(without_json(args.args))?;
    if parsed.at.is_some() && parsed.force {
        return Err(KcsError::invalid_usage(
            "reindex --force and --at are mutually exclusive",
        ));
    }
    let repo = Repository::open_current()?;
    // M1(a): serialize both HEAD reindex and historical enrichment against
    // concurrent index/repair/reindex. Historical enrichment is derived-state
    // only, but still appends to the chunk ledger and SQLite projection.
    let _lock = repo.lock_store()?;
    validate_repo_tool_lock(&repo)?;
    if let Some(at) = parsed.at.as_deref() {
        return historical_reindex::run(&repo, at);
    }
    if !parsed.force {
        return Err(KcsError::invalid_usage(
            "reindex requires --force in Step 3",
        ));
    }
    if !parsed.yes {
        return Err(KcsError::new(
            "KCS-E-CONFIRM-REJECTED-001",
            "reindex --force requires confirmation; pass --yes in non-interactive mode",
            json!({}),
            ExitCode::ConfirmationRejected,
        ));
    }
    let head = repo
        .head_commit_hash()?
        .ok_or_else(|| KcsError::not_found("HEAD"))?;
    // R15-4/R16-1: reindex re-normalizes the HEAD tree, so it needs the full commit
    // AND tree objects. If either is gone (shallow: GC'd / deleted / corrupt), fail
    // with a clear KCS-E-COMMIT-SHALLOW-001 + recovery guidance rather than a raw,
    // opaque KCS-E-STORE-NOT-FOUND-001. `read_head_tree_for_rebuild` folds both the
    // missing-commit and missing-tree cases (the same conversion the shared
    // `rebuild_step3_index` below applies, so reindex's two tree reads stay symmetric).
    let tree = read_head_tree_for_rebuild(&repo, &head)?;
    // Validate the complete selected identity set before copying any normalized
    // generation. A post-barrier reindex must not partially republish derived
    // state for entries encountered before the purged target.
    for entry in &tree.entries {
        ensure_raw_ingest_allowed(&repo, &entry.raw_hash)?;
    }
    let mut normalize_by_path = BTreeMap::new();
    let mut reindexed = 0u64;
    // R17-2: a single document's missing/corrupt normalized unit must not abort the
    // whole re-normalization — the same docs/10 §7.2 resilience R16-4 gave the shared
    // `rebuild_step3_index`, which this pre-rebuild copy loop never inherited (R16-4
    // shared only the *tree* read via `read_head_tree_for_rebuild`, not this per-unit
    // copy). A skippable failure keeps the document's PREVIOUS gen (so the snapshot
    // still points at its last-good normalized instance and search keeps serving that
    // gen's cached chunks) and is recorded; healthy documents still re-normalize.
    let mut reindex_skipped = Vec::<Value>::new();
    for entry in &tree.entries {
        let Some(normalize) = &entry.normalize else {
            continue;
        };
        let new_gen = normalize.gen + 1;
        match copy_normalized_instance_gen(
            repo.kcs_dir(),
            &entry.raw_hash,
            &normalize.tool_profile_hash,
            normalize.gen,
            new_gen,
        ) {
            Ok(()) => {
                normalize_by_path.insert(
                    entry.path.clone(),
                    PendingNormalizeRef {
                        expected_raw_hash: entry.raw_hash.clone(),
                        normalize: NormalizeRef {
                            tool_profile_hash: normalize.tool_profile_hash.clone(),
                            gen: new_gen,
                        },
                    },
                );
                reindexed += 1;
            }
            // STORE-IO (missing unit) / STORE-CORRUPT (malformed manifest/unit) are
            // localized to one document; keep the previous gen and continue. Any other
            // class is not a localized unit fault and still aborts (mirrors R16-4).
            Err(error) if is_rebuild_skippable_unit_error(&error) => {
                normalize_by_path.insert(
                    entry.path.clone(),
                    PendingNormalizeRef {
                        expected_raw_hash: entry.raw_hash.clone(),
                        normalize: NormalizeRef {
                            tool_profile_hash: normalize.tool_profile_hash.clone(),
                            gen: normalize.gen,
                        },
                    },
                );
                reindex_skipped.push(json!({
                    "raw_hash": entry.raw_hash,
                    "path": entry.path,
                    "gen": normalize.gen,
                    "reason": error.error_code(),
                }));
            }
            Err(error) => return Err(error),
        }
    }
    let closing_preview = build_scan_preview(ScanPreviewRequest {
        scope_path: repo.root().display().to_string(),
        include_raw_hashes: false,
        require_network_approval: false,
    })
    .map_err(pipeline_to_kcs)?;
    let excluded = closing_preview
        .candidates
        .iter()
        .filter(|candidate| candidate.ignored)
        .map(|candidate| candidate.input_path.clone())
        .collect::<BTreeSet<_>>();
    let explicitly_allowed_tier_a = explicitly_allowed_tier_a_paths(&closing_preview);
    let outcome = repo.auto_snapshot_with_bound_normalize(
        Some("kcs reindex --force"),
        None,
        &excluded,
        &normalize_by_path,
        &explicitly_allowed_tier_a,
    )?;
    let mut report = rebuild_step3_index(&repo)?;
    // R17-2: fold the re-normalization loop's skips into the rebuild report so the one
    // `attach_skipped_units` disclosure below covers both phases. Dedup by raw_hash: a
    // skipped document whose kept previous gen is ALSO unloadable is already reported by
    // the rebuild above; this appends only reindex-only skips (e.g. a corrupt non-`Done`
    // unit whose healthy `Done` units still let the rebuild serve the document).
    historical_reindex::merge_reindex_skips(&mut report, reindex_skipped);
    // L1: reindex = re-normalize + re-embedding (docs/06). The rebuild appends
    // fresh chunk rows; enrich them symmetrically with the `kcs index` path so
    // the embedding index tracks the new generation. Online only under the
    // embedding adapter's opt-in; offline this enqueues Embedding tasks so
    // `index_status` reports the pending enrichment instead of falsely showing
    // enriched_ratio = 1.0 (the tasks would otherwise never be created).
    let embedding_online = embedding_online_allowed(&repo, false, false, false)?;
    // R11-2: keep the enrichment ExecOutcome (was discarded) so a new-generation
    // embedding auth/budget-pause is disclosed and raises the exit (result on stdout).
    let enrichment = run_embedding_enrichment(&repo, embedding_online, false, false)?;
    let mut output = json!({
        "status": "reindexed",
        "reindexed_files": reindexed,
        "commit_hash": outcome.commit_hash,
        "rebuilt_chunks": report.rebuilt_chunks,
        "embedding_tasks_executed": enrichment.executed,
        "embedding_tasks_failed": enrichment.failed,
        "paused_tasks": enrichment.paused,
    });
    // R16-4: disclose any documents skipped for missing/corrupt units.
    attach_skipped_units(&mut output, &report, repo.kcs_dir());
    if let Some(code) = enrichment_exit_override(&enrichment) {
        set_exit_override(&mut output, code);
    }
    Ok(output)
}

/// R20-10: chunk_ids whose embedding task is currently on a secrets hold (Paused
/// `secrets_tier_b_hold`). `rebuild_chunk_vec` excludes them so a content-hash twin's
/// online embedding cannot expose a held file in vector search before `--send-secrets`.
fn held_secret_embedding_chunk_ids(kcs_dir: &Path) -> Result<BTreeSet<String>> {
    let task_store = TaskStore::new(kcs_dir);
    Ok(task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.task_type == TaskType::Embedding
                && task.status == TaskStatus::Paused
                && task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD)
        })
        .filter_map(|task| {
            task.output_ref
                .strip_prefix("embedding:")
                .map(str::to_owned)
        })
        .collect())
}

fn rebuild_step3_index(repo: &Repository) -> Result<Step3RebuildReport> {
    ensure_no_visible_purge_journal(repo.kcs_dir())?;
    let Some(head) = repo.head_commit_hash()? else {
        return Ok(Step3RebuildReport::default());
    };
    // R16-1/R16-4: `repair --rebuild-db` (the only implemented recovery command),
    // `index`, and `reindex` all rebuild through here. A shallow HEAD (commit OR tree
    // object gone) must fail with a clear KCS-E-COMMIT-SHALLOW-001 + recovery guidance
    // — NOT the raw KCS-E-STORE-NOT-FOUND-001 that let `repair` die on the very
    // corruption it exists to recover from (R15-4 fixed reindex but missed the shared
    // rebuilder that repair uses). Placing the conversion in this shared function
    // covers all three commands at once.
    let tree = read_head_tree_for_rebuild(repo, &head)?;
    let retained_instances = retained_history_instances(repo.kcs_dir(), &head)?;
    let retained_instance_keys = retained_instances
        .iter()
        .map(|instance| {
            (
                instance.raw_hash.clone(),
                instance.normalize.tool_profile_hash.clone(),
                instance.normalize.gen,
            )
        })
        .collect::<BTreeSet<_>>();
    let config = read_chunking_config(repo)?;
    let existing = read_stored_chunks(repo.kcs_dir())?;
    // Q1: physically remove any torn trailing record from `chunks.jsonl` before the
    // append below, so the new records land on a clean `'\n'`-terminated boundary
    // instead of being welded onto the torn bytes (which would create a
    // permanently-skipped malformed line and re-brick every later rebuild).
    // read/skip alone is not self-healing; this truncation is what makes it so.
    truncate_torn_chunk_tail(repo.kcs_dir())?;
    let mut known_associations = existing
        .iter()
        .map(|chunk| {
            (
                chunk.row.chunk_id.clone(),
                chunk.row.chunking_config_hash.clone(),
            )
        })
        .collect::<BTreeSet<_>>();
    let mut chunk_rowids = existing
        .iter()
        .map(|chunk| (chunk.row.chunk_id.clone(), chunk.rowid))
        .collect::<BTreeMap<_, _>>();
    let mut next_rowid = existing.iter().map(|chunk| chunk.rowid).max().unwrap_or(0) + 1;
    let mut next_association_rowid = existing
        .iter()
        .filter_map(|chunk| chunk.association_rowid)
        .max()
        .unwrap_or(0)
        + 1;
    let mut appended = Vec::<StoredChunk>::new();
    let mut tree_entries = Vec::<TreeEntryRow>::new();
    // R16-4: documents whose normalized units are missing/corrupt are skipped and
    // reported here rather than aborting the whole rebuild (docs/10 §7.2: "最悪
    // objects/ と refs/ が保全されていれば復旧できる" — one bad unit must not veto
    // the recovery of every healthy document). Never silent: the caller surfaces this.
    let mut skipped_units = Vec::<Value>::new();

    // A config change must regenerate chunks for normalized identities retained
    // anywhere in the reachable history, not only identities live at HEAD. Do
    // exact historical refs first so shared HEAD chunks retain their true
    // ancestor-most first-seen commit instead of being stamped as newly created.
    for retained in &retained_instances {
        let units = match load_normalized_units(
            repo.kcs_dir(),
            &retained.raw_hash,
            &retained.normalize.tool_profile_hash,
            retained.normalize.gen,
        ) {
            Ok(units) => units,
            Err(error) if is_rebuild_skippable_unit_error(&error) => {
                skipped_units.push(json!({
                    "raw_hash": retained.raw_hash,
                    "path": retained.raw_path,
                    "gen": retained.normalize.gen,
                    "reason": error.error_code(),
                }));
                continue;
            }
            Err(error) => return Err(error),
        };
        let input = ChunkingInput {
            raw_path: retained.raw_path.clone(),
            units,
            config: config.clone(),
            created_at: now_utc_seconds(),
        };
        for mut row in chunk_normalized_instance(input).map_err(index_to_kcs)? {
            row.first_seen_commit = Some(retained.first_seen_commit.clone());
            append_new_chunk_association(
                repo.kcs_dir(),
                row,
                &mut known_associations,
                &mut chunk_rowids,
                &mut next_rowid,
                &mut next_association_rowid,
                &mut appended,
            )?;
        }
    }

    for entry in &tree.entries {
        let normalize = match &entry.normalize {
            Some(normalize) => normalize.clone(),
            None => match latest_normalize_ref(repo.kcs_dir(), &entry.raw_hash)? {
                Some(normalize) => normalize,
                None => continue,
            },
        };
        tree_entries.push(TreeEntryRow {
            commit_hash: head.clone(),
            path: entry.path.clone(),
            raw_hash: entry.raw_hash.clone(),
            tool_profile_hash: Some(normalize.tool_profile_hash.clone()),
            gen: normalize.gen,
        });
        if retained_instance_keys.contains(&(
            entry.raw_hash.clone(),
            normalize.tool_profile_hash.clone(),
            normalize.gen,
        )) {
            continue;
        }
        let units = match load_normalized_units(
            repo.kcs_dir(),
            &entry.raw_hash,
            &normalize.tool_profile_hash,
            normalize.gen,
        ) {
            Ok(units) => units,
            // A single document's missing/corrupt normalized instance (STORE-IO /
            // STORE-CORRUPT) is skipped so the rest of the scope still rebuilds; its
            // tree_entries row is kept (the tree structure is faithful — the document
            // simply has no live chunks until re-normalized). Any other error class is
            // not a localized unit fault and still aborts.
            Err(error) if is_rebuild_skippable_unit_error(&error) => {
                skipped_units.push(json!({
                    "raw_hash": entry.raw_hash,
                    "path": entry.path,
                    // R17-6: carry the tree entry's gen so `attach_skipped_units` can
                    // tell a stale-but-searchable document (its cached chunks at this
                    // gen survive in chunks.jsonl) from a genuinely unserveable one.
                    "gen": normalize.gen,
                    "reason": error.error_code(),
                }));
                continue;
            }
            Err(error) => return Err(error),
        };
        let input = ChunkingInput {
            raw_path: entry.path.clone(),
            units,
            config: config.clone(),
            created_at: now_utc_seconds(),
        };
        for mut row in chunk_normalized_instance(input).map_err(index_to_kcs)? {
            row.first_seen_commit = Some(head.clone());
            append_new_chunk_association(
                repo.kcs_dir(),
                row,
                &mut known_associations,
                &mut chunk_rowids,
                &mut next_rowid,
                &mut next_association_rowid,
                &mut appended,
            )?;
        }
    }

    append_stored_chunks(repo.kcs_dir(), &appended)?;
    // The SQLite `tree_entries` table (below) is the single source of truth for
    // live-chunk resolution (search and short-hash resolution both read it via
    // `ensure_snapshot_tree_entries`). The former JSON projection went stale after
    // a bare snapshot and is no longer written (L3).
    rebuild_sqlite_index(
        repo.kcs_dir(),
        &tree_entries,
        &retained_instances,
        &config.chunking_config_hash,
    )?;
    Ok(Step3RebuildReport {
        rebuilt_chunks: appended.len() as u64,
        rebuilt_tree_entries: tree_entries.len() as u64,
        skipped_units,
    })
}

#[allow(clippy::too_many_arguments)]
fn append_new_chunk_association(
    kcs_dir: &Path,
    row: ChunkRow,
    known_associations: &mut BTreeSet<(String, String)>,
    chunk_rowids: &mut BTreeMap<String, u64>,
    next_rowid: &mut u64,
    next_association_rowid: &mut u64,
    appended: &mut Vec<StoredChunk>,
) -> Result<()> {
    if purge_blocks_rebuild_raw(kcs_dir, &row.raw_hash)? {
        return Ok(());
    }
    let association = (row.chunk_id.clone(), row.chunking_config_hash.clone());
    if !known_associations.insert(association) {
        return Ok(());
    }
    let rowid = match chunk_rowids.get(&row.chunk_id).copied() {
        Some(rowid) => rowid,
        None => {
            let rowid = *next_rowid;
            *next_rowid = next_rowid
                .checked_add(1)
                .ok_or_else(|| KcsError::schema("chunk rowid overflow"))?;
            chunk_rowids.insert(row.chunk_id.clone(), rowid);
            rowid
        }
    };
    persist_chunk_object(kcs_dir, &row)?;
    appended.push(StoredChunk {
        rowid,
        association_rowid: Some(*next_association_rowid),
        row,
    });
    *next_association_rowid = next_association_rowid
        .checked_add(1)
        .ok_or_else(|| KcsError::schema("chunk/config association rowid overflow"))?;
    Ok(())
}

/// R16-1/R16-4: read the HEAD commit's tree object for a *write* / rebuild path
/// (index / reindex / repair --rebuild-db), folding a missing commit OR tree object
/// (shallow: GC'd / deleted / corrupt CAS) into a clear KCS-E-COMMIT-SHALLOW-001 with
/// recovery guidance instead of a raw, opaque KCS-E-STORE-NOT-FOUND-001. Shared so
/// every rebuild caller gets the same conversion (rationale: the recovery — restore
/// the object or re-create the scope — and semantics are identical to every other
/// shallow-commit site, so no new error code is warranted).
fn read_head_tree_for_rebuild(repo: &Repository, head: &str) -> Result<TreeObject> {
    let commit = match repo.read_commit(head) {
        Ok(commit) => commit,
        Err(error) if is_store_not_found(&error) => return Err(commit_shallow_for_rebuild(head)),
        Err(error) => return Err(error),
    };
    match repo.read_tree(&commit.tree) {
        Ok(tree) => Ok(tree),
        Err(error) if is_store_not_found(&error) => Err(commit_shallow_for_rebuild(head)),
        Err(error) => Err(error),
    }
}

fn commit_shallow_for_rebuild(head: &str) -> KcsError {
    KcsError::commit_shallow(
        "HEAD commit is shallow (commit or tree object discarded); cannot rebuild the \
         index — restore the missing object or re-create the scope",
        head.to_owned(),
    )
}

/// R16-4: which `load_normalized_units` failures are per-document skippable during a
/// rebuild. A missing unit file surfaces as KCS-E-STORE-IO-001 and a malformed
/// manifest/unit as KCS-E-STORE-CORRUPT-001; both are localized to one document's
/// normalized instance, so the rebuild skips that raw_hash and recovers the rest.
fn is_rebuild_skippable_unit_error(error: &KcsError) -> bool {
    matches!(
        error.error_code(),
        "KCS-E-STORE-IO-001" | "KCS-E-STORE-CORRUPT-001"
    )
}

/// R16-4: disclose a rebuild's skipped documents on the command output. `skipped_units`
/// is always present (empty on a clean rebuild) so callers can rely on the field; when
/// non-empty it is accompanied by `skipped_units_guidance` pointing at the recovery
/// path. Rationale for keeping the exit code at 0 (rather than a partial-failure exit):
/// the rebuild genuinely succeeded for every recoverable document, the skip is loud in
/// the JSON (never a silent shrink, per R16-4), and there is no store-namespaced
/// partial code to reuse — inventing/borrowing one (a repeat of the R14-5 anti-pattern)
/// would be worse than a self-describing `skipped_units` array.
///
/// R17-6: a skipped normalized-unit does NOT imply the document is unsearchable.
/// `build_sqlite_index_at`/the rebuild re-serve any chunk rows already persisted in
/// `chunks.jsonl`, so a document whose live chunks survive stays fully searchable — only
/// its normalized *source* is stale. Matching each skip's `(raw_hash, gen)` against the
/// persisted chunks separates a stale-but-searchable document (a soft "re-normalize when
/// convenient" note) from one with no live chunks (the genuine "re-normalize now" push),
/// so the emergency guidance — which pointed users at the `reindex --force` R17-2 just
/// un-bricked — no longer false-alarms on a searchable document. Matching on gen too is
/// load-bearing: a reindex may advance a document's gen and then fail to chunk the new
/// gen, leaving only DEAD old-gen chunks that must NOT read as live.
fn attach_skipped_units(output: &mut Value, report: &Step3RebuildReport, kcs_dir: &Path) {
    let Some(object) = output.as_object_mut() else {
        return;
    };
    // Best-effort: if chunks.jsonl cannot be read, treat every skip as unsearchable
    // (the conservative "emergency" side) rather than falsely reassuring the user.
    let live: BTreeSet<(String, u64)> = read_stored_chunks(kcs_dir)
        .unwrap_or_default()
        .into_iter()
        .map(|chunk| (chunk.row.raw_hash, chunk.row.gen))
        .collect();
    let mut entries = report.skipped_units.clone();
    let mut any_unsearchable = false;
    for entry in &mut entries {
        let raw_hash = entry
            .get("raw_hash")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let gen = entry.get("gen").and_then(Value::as_u64);
        let searchable = gen.is_some_and(|gen| live.contains(&(raw_hash.clone(), gen)));
        if !searchable {
            any_unsearchable = true;
        }
        if let Some(object) = entry.as_object_mut() {
            object.insert("searchable".to_owned(), json!(searchable));
            object.insert(
                "guidance".to_owned(),
                json!(if searchable {
                    "re-serving cached chunks; the normalized source is stale — \
                     re-normalize with `kcs reindex --force` when convenient"
                } else {
                    "no live chunks remain for this document; run `kcs reindex --force` \
                     to re-normalize it from the raw objects"
                }),
            );
        }
    }
    let non_empty = !entries.is_empty();
    object.insert("skipped_units".to_owned(), json!(entries));
    if non_empty {
        object.insert(
            "skipped_units_guidance".to_owned(),
            json!(if any_unsearchable {
                "some documents' normalized units are missing or corrupt and have no live \
                 chunks; run `kcs reindex --force` to re-normalize them from the raw objects"
            } else {
                "some documents' normalized sources are stale but their cached chunks are \
                 still served; re-normalize with `kcs reindex --force` when convenient"
            }),
        );
    }
}

/// R17-2: merge the reindex copy-loop's per-document skips into the rebuild report,
/// deduplicated by raw_hash so a document reported by BOTH phases surfaces once.
fn latest_normalize_ref(kcs_dir: &Path, raw_hash: &str) -> Result<Option<NormalizeRef>> {
    let digest = hash_path_component(raw_hash)?;
    let dir = kcs_dir
        .join("objects/normalized_units")
        .join(&digest[0..2])
        .join(&digest[2..4]);
    let Ok(entries) = fs::read_dir(&dir) else {
        return Ok(None);
    };
    let mut best: Option<NormalizeRef> = None;
    for entry in entries {
        let entry =
            entry.map_err(|err| KcsError::io(err.to_string(), dir.display().to_string()))?;
        if !entry.file_type().map(|kind| kind.is_dir()).unwrap_or(false) {
            continue;
        }
        let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
            continue;
        };
        let parsed = name
            .strip_prefix(digest)
            .and_then(|value| value.strip_prefix('.'))
            .map(|rest| (rest, true))
            .or_else(|| {
                name.strip_prefix(raw_hash)
                    .and_then(|value| value.strip_prefix('.'))
                    .map(|rest| (rest, false))
            });
        let Some((rest, portable)) = parsed else {
            continue;
        };
        let Some((tool_component, gen_part)) = rest.rsplit_once(".g") else {
            continue;
        };
        let Ok(gen) = gen_part.parse::<u64>() else {
            continue;
        };
        let tool_profile_hash = if portable {
            format!("sha256:{tool_component}")
        } else {
            tool_component.to_owned()
        };
        if !is_hash(&tool_profile_hash) {
            continue;
        }
        if best
            .as_ref()
            .map(|current| gen > current.gen)
            .unwrap_or(true)
        {
            best = Some(NormalizeRef {
                tool_profile_hash,
                gen,
            });
        }
    }
    Ok(best)
}

#[derive(Debug, Default)]
struct Step3RebuildReport {
    rebuilt_chunks: u64,
    rebuilt_tree_entries: u64,
    /// R16-4: documents skipped because their normalized units are missing/corrupt,
    /// each `{raw_hash, path, reason}`. Empty on a clean rebuild.
    skipped_units: Vec<Value>,
}

fn read_chunking_config(repo: &Repository) -> Result<ChunkingConfig> {
    let path = repo.kcs_dir().join("config.toml");
    let text = fs::read_to_string(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    let value: toml::Value =
        toml::from_str(&text).map_err(|err| KcsError::schema(err.to_string()))?;
    let max_chars = value
        .get("chunking")
        .and_then(|chunking| chunking.get("max_chars"))
        .and_then(toml::Value::as_integer)
        .filter(|value| *value > 0)
        .map(|value| value as u64)
        .unwrap_or(6000);
    let strategy = value
        .get("chunking")
        .and_then(|chunking| chunking.get("strategy"))
        .and_then(toml::Value::as_str)
        .unwrap_or("heading");
    let hash =
        kcs_index::chunking::chunking_config_hash(strategy, max_chars).map_err(index_to_kcs)?;
    Ok(ChunkingConfig {
        chunking_config_hash: hash,
        strategy: strategy.to_owned(),
        max_chars,
    })
}

fn load_normalized_units(
    kcs_dir: &Path,
    raw_hash: &str,
    tool_profile_hash: &str,
    gen: u64,
) -> Result<Vec<NormalizedUnitInput>> {
    let instance = load_validated_normalized_instance(kcs_dir, raw_hash, tool_profile_hash, gen)
        .map_err(pipeline_to_kcs)?;
    Ok(instance
        .units
        .into_iter()
        .map(|unit| NormalizedUnitInput {
            raw_hash: unit.raw_hash,
            tool_profile_hash: unit.tool_profile_hash,
            gen: unit.gen,
            unit_key: unit.unit_key,
            markdown: unit.markdown,
        })
        .collect())
}

fn store_corrupt_error(path: &Path, message: impl Into<String>) -> KcsError {
    let path_string = path.display().to_string();
    KcsError::new(
        "KCS-E-STORE-CORRUPT-001",
        format!("corrupt store file at {path_string}: {}", message.into()),
        json!({ "path": path_string }),
        ExitCode::PermanentFailure,
    )
}

fn index_dir(kcs_dir: &Path) -> PathBuf {
    kcs_dir.join("index")
}

fn chunks_jsonl_path(kcs_dir: &Path) -> PathBuf {
    index_dir(kcs_dir).join("chunks.jsonl")
}

fn sqlite_path(kcs_dir: &Path) -> PathBuf {
    index_dir(kcs_dir).join("sqlite.db")
}

fn read_stored_chunks(kcs_dir: &Path) -> Result<Vec<StoredChunk>> {
    let path = chunks_jsonl_path(kcs_dir);
    let Ok(text) = fs::read_to_string(&path) else {
        return Ok(Vec::new());
    };
    // Q1: `chunks.jsonl` is append-only and never fsync'd (`append_stored_chunks`
    // / `cas::append_jsonl`), so a crash / ENOSPC mid-`write_all` can leave the
    // FINAL line torn. That chunk is regenerated from normalized_units /
    // tree_entries on the next rebuild, so tolerate a torn tail (skip it) and let
    // `index` / `reindex` / `repair --rebuild-db` self-heal — rather than bricking
    // every write path (and the sole recovery command) on exit 2.
    //
    // A corrupt NON-final line cannot be a torn tail, so the store file is
    // genuinely corrupt: classify it as `KCS-E-STORE-CORRUPT-001` (exit 4) with
    // the file path, matching `TaskStore::all` (M1(c)) / cost-ledger — not the
    // misleading `KCS-E-CONFIG-SCHEMA-001` (exit 2, no path) it used to emit.
    let lines: Vec<&str> = text
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect();
    let last_index = lines.len().saturating_sub(1);
    let mut chunks = Vec::with_capacity(lines.len());
    for (index, line) in lines.iter().enumerate() {
        match serde_json::from_str::<StoredChunk>(line) {
            Ok(chunk) => chunks.push((index + 1, chunk)),
            Err(_) if index == last_index => break,
            Err(err) => {
                return Err(KcsError::new(
                    "KCS-E-STORE-CORRUPT-001",
                    "corrupt chunks.jsonl record",
                    json!({
                        "path": path.display().to_string(),
                        "line": index + 1,
                        "message": err.to_string(),
                    }),
                    ExitCode::PermanentFailure,
                ));
            }
        }
    }

    // Legacy Step 3 records have no association rowid. Their one-config-per-
    // chunk layout was replayed in chunk-row order, so stored chunk rowid is the
    // deterministic migration order used by `migrate_legacy_chunk_config_column`.
    // Assign the missing prefix here and persist explicit ids on every new append;
    // this keeps a later SQLite rebuild from renumbering signed cursor bounds.
    let mut used_association_rowids = chunks
        .iter()
        .filter_map(|(_, chunk)| chunk.association_rowid)
        .collect::<BTreeSet<_>>();
    for (line, chunk) in &chunks {
        if chunk.rowid == 0 || chunk.association_rowid == Some(0) {
            return Err(corrupt_chunk_ledger_error(
                &path,
                *line,
                "chunk and association rowids must be positive",
            ));
        }
    }
    let mut legacy_indices = chunks
        .iter()
        .enumerate()
        .filter_map(|(index, (_, chunk))| chunk.association_rowid.is_none().then_some(index))
        .collect::<Vec<_>>();
    legacy_indices.sort_by_key(|index| (chunks[*index].1.rowid, chunks[*index].0));
    let mut next_legacy_association_rowid = 1_u64;
    for index in legacy_indices {
        while used_association_rowids.contains(&next_legacy_association_rowid) {
            next_legacy_association_rowid += 1;
        }
        chunks[index].1.association_rowid = Some(next_legacy_association_rowid);
        used_association_rowids.insert(next_legacy_association_rowid);
        next_legacy_association_rowid += 1;
    }

    let mut association_owners = BTreeMap::<u64, (String, String)>::new();
    let mut known_associations = BTreeSet::<(String, String)>::new();
    let mut chunk_rowid_owners = BTreeMap::<u64, String>::new();
    let mut rowid_for_chunk = BTreeMap::<String, u64>::new();
    for (line, chunk) in &chunks {
        let association = (
            chunk.row.chunk_id.clone(),
            chunk.row.chunking_config_hash.clone(),
        );
        if !known_associations.insert(association.clone()) {
            return Err(corrupt_chunk_ledger_error(
                &path,
                *line,
                "duplicate chunk/config association",
            ));
        }
        let association_rowid = chunk.association_rowid.expect("assigned above");
        if association_owners
            .insert(association_rowid, association.clone())
            .is_some()
        {
            return Err(corrupt_chunk_ledger_error(
                &path,
                *line,
                "association rowid is assigned more than once",
            ));
        }
        if chunk_rowid_owners
            .insert(chunk.rowid, chunk.row.chunk_id.clone())
            .is_some_and(|owner| owner != chunk.row.chunk_id)
        {
            return Err(corrupt_chunk_ledger_error(
                &path,
                *line,
                "chunk rowid is assigned to multiple chunk ids",
            ));
        }
        if rowid_for_chunk
            .insert(chunk.row.chunk_id.clone(), chunk.rowid)
            .is_some_and(|rowid| rowid != chunk.rowid)
        {
            return Err(corrupt_chunk_ledger_error(
                &path,
                *line,
                "one chunk id is assigned multiple chunk rowids",
            ));
        }
    }
    Ok(chunks.into_iter().map(|(_, chunk)| chunk).collect())
}

fn corrupt_chunk_ledger_error(path: &Path, line: usize, message: &str) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-CORRUPT-001",
        "corrupt chunks.jsonl record",
        json!({
            "path": path.display().to_string(),
            "line": line,
            "message": message,
        }),
        ExitCode::PermanentFailure,
    )
}

/// Publish the exact semantic chunk CAS object before the JSONL/SQLite
/// acceleration record can make the chunk discoverable.
fn persist_chunk_object(kcs_dir: &Path, row: &ChunkRow) -> Result<()> {
    let object = ChunkObject {
        spec_version: 1,
        raw_hash: row.raw_hash.clone(),
        tool_profile_hash: row.tool_profile_hash.clone(),
        gen: row.gen,
        unit_key: row.unit_key.clone(),
        heading_path: row.heading_path.clone().unwrap_or_default(),
        section_id: row.section_id.clone().filter(|value| !value.is_empty()),
        char_start: row.char_start,
        char_end: row.char_end,
        text_hash: row.text_hash.clone(),
        text: row.text.clone(),
    };
    let stored_hash = ObjectStore::new(kcs_dir).write_chunk(&object)?;
    if stored_hash != row.chunk_id {
        return Err(KcsError::new(
            "KCS-E-STORE-CORRUPT-001",
            "chunk ledger identity does not match the canonical chunk object",
            json!({
                "ledger_chunk_hash": row.chunk_id,
                "canonical_chunk_hash": stored_hash,
            }),
            ExitCode::PermanentFailure,
        ));
    }
    Ok(())
}

/// Q1: physically drop a torn trailing record from `chunks.jsonl` before the next
/// append. `read_stored_chunks` already tolerates a torn LAST line at read time,
/// but read-skip alone is not self-healing: a torn line has no trailing `'\n'`, so
/// the next `append_stored_chunks` welds its record onto the torn bytes, forming a
/// newline-terminated *malformed* line that is then skipped forever — its chunk
/// re-generated and re-appended on every rebuild, and reclassified as
/// `KCS-E-STORE-CORRUPT-001` the instant that welded line stops being last (which
/// re-bricks `index` / `reindex` / `repair`).
///
/// A well-formed `chunks.jsonl` always ends in `'\n'`, so "file exists and its last
/// byte is not `'\n'`" is a reliable torn-tail signal. Truncate to just after the
/// last `'\n'` (or to 0 when none exists) so the append lands on a clean record
/// boundary and the whole index / reindex / repair path fully self-heals.
///
/// Only reached after `read_stored_chunks` returned `Ok`: a genuinely corrupt
/// NON-final line surfaces as `KCS-E-STORE-CORRUPT-001` there and never reaches
/// here, so real corruption is never silently truncated (multi-layer defense).
fn truncate_torn_chunk_tail(kcs_dir: &Path) -> Result<()> {
    let path = chunks_jsonl_path(kcs_dir);
    let bytes = match fs::read(&path) {
        Ok(bytes) => bytes,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(err) => return Err(KcsError::io(err.to_string(), path.display().to_string())),
    };
    if bytes.is_empty() || bytes.last() == Some(&b'\n') {
        return Ok(());
    }
    // Keep everything up to and including the last newline (0 when none exists).
    let keep = bytes
        .iter()
        .rposition(|&byte| byte == b'\n')
        .map_or(0, |index| index + 1);
    let file = OpenOptions::new()
        .write(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    file.set_len(keep as u64)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    file.sync_all()
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    Ok(())
}

fn append_stored_chunks(kcs_dir: &Path, chunks: &[StoredChunk]) -> Result<()> {
    if chunks.is_empty() {
        return Ok(());
    }
    let path = chunks_jsonl_path(kcs_dir);
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent)
        .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    for chunk in chunks {
        // M1(b): one framed record per single write_all (no interleaving).
        let mut line = serde_json::to_string(chunk)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        line.push('\n');
        file.write_all(line.as_bytes())
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    }
    Ok(())
}

fn rebuild_sqlite_index(
    kcs_dir: &Path,
    tree_entries: &[TreeEntryRow],
    retained_instances: &[RetainedNormalizedInstance],
    chunking_config_hash: &str,
) -> Result<()> {
    ensure_no_visible_purge_journal(kcs_dir)?;
    let path = sqlite_path(kcs_dir);
    // O5: a 0-chunk scope (empty folder / secrets-only / text-less PDF) skips
    // `append_stored_chunks` and so never creates `.kcs/index/`, but the auto-
    // snapshot still advances HEAD. Create the index dir unconditionally here so
    // opening `sqlite.db` cannot fail with a half-initialized "commit, no index"
    // state that makes every re-index exit 2.
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    }
    // Embeddings live only in SQLite (objects/ holds no embedding objects in the
    // MVP), so snapshot them from the CURRENT db (without removing it) and replay
    // them into the fresh db, then rebuild chunk_vec from them (04 §4.3). This
    // keeps `kcs repair --rebuild-db` / reindex from wiping vector search.
    let (preserved, preserved_tree_entries) = if path.exists() {
        let existing = Connection::open(&path).map_err(|err| KcsError::schema(err.to_string()))?;
        let rows = embedding_store::snapshot_chunk_embeddings(&existing).map_err(index_to_kcs)?;
        let tree_rows = snapshot_tree_entries(&existing)?;
        drop(existing);
        (rows, tree_rows)
    } else {
        (Vec::new(), Vec::new())
    };
    // P5 (docs/05:564): build the new index in a unique temp db and atomically
    // rename it over sqlite.db. `kcs search` takes no store lock and opens
    // sqlite.db by path, so it must always see a complete db — the old one until
    // the rename, the new one after. The previous remove_file + in-place rebuild
    // exposed an empty/half-built window in which a concurrent search returned
    // exit 0 with 0 results (a silent false negative). The unique temp name also
    // stops two rebuilders from clobbering one shared `sqlite.db.tmp`.
    let temp_path = unique_sqlite_temp_path(&path);
    // A residual temp from a crashed rebuild would be reused (and corrupt the new
    // index) by `Connection::open`; start from a clean slate.
    if temp_path.exists() {
        fs::remove_file(&temp_path)
            .map_err(|err| KcsError::io(err.to_string(), temp_path.display().to_string()))?;
    }
    match build_sqlite_index_at(
        &temp_path,
        kcs_dir,
        &preserved_tree_entries,
        tree_entries,
        &preserved,
        retained_instances,
        chunking_config_hash,
    ) {
        Ok(()) => fs::rename(&temp_path, &path)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string())),
        Err(error) => {
            let _ = fs::remove_file(&temp_path);
            Err(error)
        }
    }
}

/// Preserve immutable historical tree projections across an atomic rebuild.
/// The current HEAD rows supplied by the caller are replayed afterward and win
/// on the `(commit_hash,path)` key. Retaining older cache rows is contract-safe;
/// history search still verifies commit/tree CAS before consulting a projection.
fn snapshot_tree_entries(conn: &Connection) -> Result<Vec<TreeEntryRow>> {
    let mut statement = conn
        .prepare(
            "SELECT commit_hash, path, raw_hash, tool_profile_hash, gen
             FROM tree_entries ORDER BY commit_hash, path",
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let rows = statement
        .query_map([], |row| {
            Ok(TreeEntryRow {
                commit_hash: row.get(0)?,
                path: row.get(1)?,
                raw_hash: row.get(2)?,
                tool_profile_hash: row.get(3)?,
                gen: row.get(4)?,
            })
        })
        .map_err(|err| KcsError::schema(err.to_string()))?;
    rows.collect::<std::result::Result<Vec<_>, _>>()
        .map_err(|err| KcsError::schema(err.to_string()))
}

/// A unique sibling temp path for the atomic sqlite rebuild
/// (`sqlite.db.<pid>-<nanos>.tmp`, P5). Unique per attempt so concurrent
/// rebuilders never share a temp.
fn unique_sqlite_temp_path(path: &Path) -> PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or_default();
    let file_name = format!("sqlite.db.{}-{nanos}.tmp", process::id());
    match path.parent() {
        Some(parent) => parent.join(file_name),
        None => PathBuf::from(file_name),
    }
}

/// Populate a fresh sqlite index at `temp_path` (chunks + FTS, tree_entries,
/// preserved embeddings, chunk_vec) and close it. The caller renames it over
/// sqlite.db (P5); the connection is dropped here so the rename sees no open
/// handle / leftover journal.
fn build_sqlite_index_at(
    temp_path: &Path,
    kcs_dir: &Path,
    preserved_tree_entries: &[TreeEntryRow],
    tree_entries: &[TreeEntryRow],
    preserved: &[embedding_store::ChunkEmbeddingSnapshotRow],
    retained_instances: &[RetainedNormalizedInstance],
    chunking_config_hash: &str,
) -> Result<()> {
    ensure_no_visible_purge_journal(kcs_dir)?;
    let mut fts = SqliteFtsIndex::open(
        temp_path,
        FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        },
    )
    .map_err(index_to_kcs)?;
    // R11-4 (sibling of R10-8's `insert_snapshot_tree_entries`): wrap the whole
    // rebuild — every stored chunk, every tree_entries row, and every preserved
    // embedding — in ONE transaction. Without it each INSERT autocommits with its
    // own fsync, so even a no-op reindex re-pays the full-corpus write cost, which
    // grows without bound because `chunks.jsonl` is append-only (docs/04:334, the
    // time-travel substrate). A manual BEGIN/COMMIT is used rather than an
    // `unchecked_transaction()` guard because `index_chunk` takes `&mut self`; a
    // held guard would keep `fts` immutably borrowed for its lifetime (E0502).
    // Crash safety is unchanged: the caller builds into a unique temp db and
    // removes it on ANY Err (P5, line ~2779), and dropping `fts` rolls back an
    // uncommitted transaction, so a partial/rolled-back temp is never renamed in.
    fts.connection()
        .execute_batch("BEGIN")
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let mut live_chunk_ids = BTreeSet::new();
    for chunk in read_stored_chunks(kcs_dir)? {
        if purge_blocks_rebuild_raw(kcs_dir, &chunk.row.raw_hash)? {
            continue;
        }
        live_chunk_ids.insert(chunk.row.chunk_id.clone());
        persist_chunk_object(kcs_dir, &chunk.row)?;
        fts.index_chunk_with_rowids(&chunk.row, Some(chunk.rowid), chunk.association_rowid)
            .map_err(index_to_kcs)?;
    }
    for entry in preserved_tree_entries.iter().chain(tree_entries) {
        if purge_blocks_rebuild_raw(kcs_dir, &entry.raw_hash)? {
            continue;
        }
        fts.connection()
            .execute(
                "INSERT OR REPLACE INTO tree_entries(commit_hash, path, raw_hash, tool_profile_hash, gen)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                rusqlite::params![
                    entry.commit_hash,
                    entry.path,
                    entry.raw_hash,
                    entry.tool_profile_hash,
                    entry.gen
                ],
            )
            .map_err(|err| KcsError::schema(err.to_string()))?;
    }
    // Replay preserved embeddings (source of truth) and re-derive chunk_vec.
    for row in preserved {
        if !live_chunk_ids.contains(&row.chunk_id) {
            continue;
        }
        embedding_store::write_chunk_embedding(
            fts.connection(),
            &row.embedding_hash,
            &row.text_hash,
            &row.chunk_id,
            &row.vector,
            row.dimensions,
            &row.distance,
            &row.modality,
            &row.profile_hash,
        )
        .map_err(index_to_kcs)?;
    }
    // R20-10: exclude secret-held chunks so the content-hash rebuild can't link a held
    // (Tier B) chunk to a non-secret content-twin's vector and expose it in vector search.
    let mut held_chunk_ids = held_secret_embedding_chunk_ids(kcs_dir)?;
    if !secrets_send_approved_in_kcs_dir(kcs_dir) {
        held_chunk_ids.extend(
            retained_history_chunks(
                fts.connection(),
                kcs_dir,
                retained_instances,
                chunking_config_hash,
            )?
            .into_iter()
            .filter(|chunk| chunk.requires_secret_approval)
            .map(|chunk| chunk.chunk_id),
        );
    }
    embedding_store::rebuild_chunk_vec(fts.connection(), &held_chunk_ids).map_err(index_to_kcs)?;
    fts.connection()
        .execute_batch("COMMIT")
        .map_err(|err| KcsError::schema(err.to_string()))?;
    drop(fts);
    Ok(())
}

/// R12-7: split a long option into `(flag, inline_value)`. `--limit=5` becomes
/// `("--limit", Some("5"))` — the `--flag=value` form clap-derive commands already
/// accept. Only `--`-prefixed tokens are split, so a positional operand containing
/// `=` (e.g. a query `key=value`) is returned intact and never mangled.
fn split_flag_value(arg: &str) -> (&str, Option<&str>) {
    if arg.starts_with("--") {
        if let Some((flag, value)) = arg.split_once('=') {
            return (flag, Some(value));
        }
    }
    (arg, None)
}

/// R16-6: a value-LESS (boolean / SetTrue) flag must reject an inline
/// `--flag=<value>` outright — including `--flag=false` and `--flag=true`. The
/// R12-7 `split_flag_value` rewrite made the hand-rolled parsers accept `--flag=x`
/// for EVERY flag, but the value-less arms then silently DROPPED the inline value
/// and set the flag `true`, so `reindex --force=false --yes=false` (an explicit
/// negation) bypassed the confirmation gate and ran a full reindex (exit 0). Reject
/// any inline value here so the manual parsers match clap's derived bool flags,
/// which already reject `--json=false` (KCS-E-CONFIG-USAGE-001, exit 2). Value-taking
/// flags (`--at` / `--scope` / `--limit` / `--offset` / `--cursor`) keep consuming the
/// inline value via `flag_value` and never call this.
fn reject_inline_value(flag: &str, inline: Option<&str>) -> Result<()> {
    if inline.is_some() {
        return Err(KcsError::invalid_usage(format!(
            "flag {flag} does not take a value"
        )));
    }
    Ok(())
}

/// R12-7: the value for a value-taking flag — the inline `--flag=value` value if
/// present, else the next argv token (advancing `i`).
fn flag_value(args: &[String], i: &mut usize, inline: Option<&str>, flag: &str) -> Result<String> {
    if let Some(value) = inline {
        return Ok(value.to_owned());
    }
    *i += 1;
    args.get(*i)
        .cloned()
        .ok_or_else(|| KcsError::invalid_usage(format!("{flag} requires a value")))
}

fn parse_search_args(args: Vec<String>) -> Result<ParsedSearch> {
    let mut query = None;
    let mut requested_mode = SearchMode::Auto;
    let mut explicit_mode = false;
    let mut scope = None;
    let mut descendants = false;
    let mut all_scopes = false;
    let mut limit = 20u64;
    let mut offset = None;
    let mut cursor = None;
    let mut time_selector_flags = TimeSelectorFlags::default();
    let mut i = 0usize;
    while i < args.len() {
        // R12-7: accept `--flag=value` before matching (the manual parser used to
        // reject it as "unknown flag" even though the flag exists).
        let (flag, inline) = split_flag_value(&args[i]);
        match flag {
            "--at" => {
                if time_selector_flags.at.is_some() {
                    return Err(KcsError::invalid_usage("--at may be specified once"));
                }
                time_selector_flags.at = Some(flag_value(args.as_slice(), &mut i, inline, "--at")?);
            }
            "--all-history" => {
                reject_inline_value(flag, inline)?;
                if time_selector_flags.all_history {
                    return Err(KcsError::invalid_usage(
                        "--all-history may be specified once",
                    ));
                }
                time_selector_flags.all_history = true;
            }
            "--include-deleted" => {
                reject_inline_value(flag, inline)?;
                if time_selector_flags.include_deleted {
                    return Err(KcsError::invalid_usage(
                        "--include-deleted may be specified once",
                    ));
                }
                time_selector_flags.include_deleted = true;
            }
            "--since" => {
                if time_selector_flags.since.is_some() {
                    return Err(KcsError::invalid_usage("--since may be specified once"));
                }
                time_selector_flags.since =
                    Some(flag_value(args.as_slice(), &mut i, inline, "--since")?);
            }
            "--text" | "--no-vector" => {
                // R16-6: these are value-less mode selectors — `--text=false` must be
                // a usage error, not a silent "text mode requested" (the inline value
                // was previously dropped and the flag set anyway).
                reject_inline_value(flag, inline)?;
                requested_mode = SearchMode::Text;
                explicit_mode = true;
            }
            "--vector" => {
                reject_inline_value(flag, inline)?;
                requested_mode = SearchMode::Vector;
                explicit_mode = true;
            }
            "--hybrid" => {
                reject_inline_value(flag, inline)?;
                requested_mode = SearchMode::Hybrid;
                explicit_mode = true;
            }
            "--all-scopes" => {
                reject_inline_value(flag, inline)?;
                all_scopes = true;
            }
            "--descendants" => {
                reject_inline_value(flag, inline)?;
                descendants = true;
            }
            "--scope" => {
                scope = Some(PathBuf::from(flag_value(&args, &mut i, inline, "--scope")?));
            }
            "--limit" => {
                let value = flag_value(&args, &mut i, inline, "--limit")?;
                let parsed = value
                    .parse::<u64>()
                    .map_err(|_| KcsError::invalid_usage("--limit must be an integer"))?;
                // R12-7: `--limit 0` is a meaningless value, not a silent clamp-to-1
                // (which faked success). The upper 100 cap is unchanged (docs-silent).
                if parsed == 0 {
                    return Err(KcsError::invalid_usage("--limit must be at least 1"));
                }
                limit = parsed.min(100);
            }
            "--offset" => {
                let value = flag_value(&args, &mut i, inline, "--offset")?;
                offset = Some(
                    value
                        .parse::<u64>()
                        .map_err(|_| KcsError::invalid_usage("--offset must be an integer"))?,
                );
            }
            "--cursor" => {
                cursor = Some(flag_value(&args, &mut i, inline, "--cursor")?);
            }
            value if value.starts_with('-') => {
                return Err(KcsError::invalid_usage(format!(
                    "unknown search flag: {value}"
                )));
            }
            _ => {
                if query.is_some() {
                    return Err(KcsError::invalid_usage("search accepts one query string"));
                }
                // A positional query is never split, so use the original token.
                query = Some(args[i].clone());
            }
        }
        i += 1;
    }
    // Validate selector exclusivity/duration before repository or DB access.
    time_selector_flags.canonicalize()?;
    Ok(ParsedSearch {
        query: query.ok_or_else(|| KcsError::invalid_usage("search query is required"))?,
        requested_mode,
        explicit_mode,
        scope,
        descendants,
        all_scopes,
        limit,
        offset,
        cursor,
        time_selector_flags,
    })
}

/// R11-7: `[search].default_mode` / `fail_behavior` from one config file
/// (config.schema.json §search). Both are independent and optional; an unknown or
/// absent value yields `None` (the config is schema-validated at startup, so an
/// out-of-enum value is already rejected before search runs).
fn read_search_config(path: &Path) -> Result<(Option<SearchMode>, Option<SearchFailBehavior>)> {
    let Ok(text) = fs::read_to_string(path) else {
        return Ok((None, None));
    };
    let value: toml::Value =
        toml::from_str(&text).map_err(|err| KcsError::schema(err.to_string()))?;
    let search = value.get("search");
    let default_mode = search
        .and_then(|section| section.get("default_mode"))
        .and_then(toml::Value::as_str)
        .and_then(parse_search_mode_name);
    let fail_behavior = search
        .and_then(|section| section.get("fail_behavior"))
        .and_then(toml::Value::as_str)
        .and_then(parse_fail_behavior_name);
    Ok((default_mode, fail_behavior))
}

/// R11-7: effective `[search]` settings — the scope config.toml takes precedence
/// over the user config.toml (same precedence direction the acceptance uses for
/// other scoped overrides). `[search.multi_scope]` is intentionally untouched
/// (R11-7 defer / MULTI-006).
fn effective_search_config(
    repo: &Repository,
) -> Result<(Option<SearchMode>, Option<SearchFailBehavior>)> {
    let (scope_mode, scope_fail) = read_search_config(&repo.kcs_dir().join("config.toml"))?;
    let (user_mode, user_fail) = read_search_config(&user_config_toml_path())?;
    Ok((scope_mode.or(user_mode), scope_fail.or(user_fail)))
}

fn parse_search_mode_name(name: &str) -> Option<SearchMode> {
    match name {
        "auto" => Some(SearchMode::Auto),
        "text" => Some(SearchMode::Text),
        "vector" => Some(SearchMode::Vector),
        "hybrid" => Some(SearchMode::Hybrid),
        _ => None,
    }
}

/// R12-1: the tuning half of `[search]` parsed from ONE config file. Every key is
/// independent and optional (schema-validated at repo open, so an out-of-range /
/// unknown key is already rejected). `None` means "not set in this file".
#[derive(Default)]
struct SearchTuning {
    rrf_k: Option<u64>,
    rrf_w_text: Option<f64>,
    rrf_w_vector: Option<f64>,
    rrf_candidate_depth: Option<u64>,
    div_enabled: Option<bool>,
    div_strategy: Option<DiversifyStrategy>,
    div_mmr_lambda: Option<f64>,
    div_max_per_raw_hash: Option<u64>,
    div_mmr_depth: Option<u64>,
}

fn toml_u64(value: Option<&toml::Value>) -> Option<u64> {
    value
        .and_then(toml::Value::as_integer)
        .and_then(|integer| u64::try_from(integer).ok())
}

/// TOML distinguishes `1` (integer) from `1.0` (float); the schema types these as
/// `number`, so accept either as f64.
fn toml_f64(value: Option<&toml::Value>) -> Option<f64> {
    value.and_then(|value| {
        value
            .as_float()
            .or_else(|| value.as_integer().map(|integer| integer as f64))
    })
}

fn parse_diversify_strategy(name: &str) -> Option<DiversifyStrategy> {
    match name {
        "mmr" => Some(DiversifyStrategy::Mmr),
        "group_by_raw_hash" => Some(DiversifyStrategy::GroupByRawHash),
        "off" => Some(DiversifyStrategy::Off),
        _ => None,
    }
}

fn read_search_tuning(path: &Path) -> Result<SearchTuning> {
    let Ok(text) = fs::read_to_string(path) else {
        return Ok(SearchTuning::default());
    };
    let value: toml::Value =
        toml::from_str(&text).map_err(|err| KcsError::schema(err.to_string()))?;
    let search = value.get("search");
    let rrf = search.and_then(|section| section.get("rrf"));
    let diversify = search.and_then(|section| section.get("diversify"));
    Ok(SearchTuning {
        rrf_k: toml_u64(rrf.and_then(|rrf| rrf.get("k"))),
        rrf_w_text: toml_f64(rrf.and_then(|rrf| rrf.get("w_text"))),
        rrf_w_vector: toml_f64(rrf.and_then(|rrf| rrf.get("w_vector"))),
        rrf_candidate_depth: toml_u64(rrf.and_then(|rrf| rrf.get("candidate_depth"))),
        div_enabled: diversify
            .and_then(|diversify| diversify.get("enabled"))
            .and_then(toml::Value::as_bool),
        div_strategy: diversify
            .and_then(|diversify| diversify.get("strategy"))
            .and_then(toml::Value::as_str)
            .and_then(parse_diversify_strategy),
        div_mmr_lambda: toml_f64(diversify.and_then(|diversify| diversify.get("mmr_lambda"))),
        div_max_per_raw_hash: toml_u64(
            diversify.and_then(|diversify| diversify.get("max_per_raw_hash")),
        ),
        div_mmr_depth: toml_u64(diversify.and_then(|diversify| diversify.get("mmr_depth"))),
    })
}

/// R12-1: effective `[search.rrf]` + `[search.diversify]` (05 §1.3/§1.4). Scope
/// config wins over user config per key (same precedence as `effective_search_config`),
/// each falling back to the documented default. These feed BOTH the ranking/dedup
/// call sites AND the cursor `query_hash` (05 §1.8 requires the effective values, so
/// a tuning change invalidates a stale cursor).
fn effective_search_tuning(repo: &Repository) -> Result<(RrfConfig, DiversifyRequest)> {
    let scope = read_search_tuning(&repo.kcs_dir().join("config.toml"))?;
    let user = read_search_tuning(&user_config_toml_path())?;
    let rrf = RrfConfig {
        k: scope.rrf_k.or(user.rrf_k).unwrap_or(60),
        w_text: scope.rrf_w_text.or(user.rrf_w_text).unwrap_or(1.0),
        w_vector: scope.rrf_w_vector.or(user.rrf_w_vector).unwrap_or(1.0),
        candidate_depth: scope
            .rrf_candidate_depth
            .or(user.rrf_candidate_depth)
            .unwrap_or(200),
    };
    // `enabled = false` means diversification is off entirely (05 §1.4); it maps to
    // the Off strategy, which is a TRUE no-op (no MMR, no dedup — R12-1). Otherwise
    // use the configured strategy, default MMR.
    let enabled = scope.div_enabled.or(user.div_enabled).unwrap_or(true);
    let strategy = if enabled {
        scope
            .div_strategy
            .or(user.div_strategy)
            .unwrap_or(DiversifyStrategy::Mmr)
    } else {
        DiversifyStrategy::Off
    };
    let diversify = DiversifyRequest {
        strategy,
        mmr_lambda: Some(scope.div_mmr_lambda.or(user.div_mmr_lambda).unwrap_or(0.7)),
        max_per_raw_hash: Some(
            scope
                .div_max_per_raw_hash
                .or(user.div_max_per_raw_hash)
                .unwrap_or(3),
        ),
        mmr_depth: Some(scope.div_mmr_depth.or(user.div_mmr_depth).unwrap_or(100)),
    };
    Ok((rrf, diversify))
}

fn parse_fail_behavior_name(name: &str) -> Option<SearchFailBehavior> {
    match name {
        "fallback" => Some(SearchFailBehavior::Fallback),
        "warn" => Some(SearchFailBehavior::Warn),
        "error" => Some(SearchFailBehavior::Error),
        _ => None,
    }
}

fn without_json(args: Vec<String>) -> Vec<String> {
    args.into_iter().filter(|arg| arg != "--json").collect()
}

/// Enumerate the scopes a search targets (K3, 05 §1.8). Default and `--all-scopes`
/// enumerate the device-local registry (all indexed, `participates_in_global_search`);
/// `--scope <path>` targets exactly that scope (filesystem, even if unregistered);
/// `--descendants` filters the registry by root-path prefix.
fn enumerate_scope_targets(
    repo: &Repository,
    parsed: &ParsedSearch,
) -> Result<(ScopeSelectionMode, Vec<ScopeTarget>)> {
    if let Some(scope) = &parsed.scope {
        let root = if scope.is_absolute() {
            scope.clone()
        } else {
            repo.root().join(scope)
        };
        if parsed.descendants {
            let root = root.canonicalize().unwrap_or(root);
            let targets = registry_targets_under(&root)?
                .unwrap_or_else(|| registry_unavailable_fallback(&root));
            return Ok((ScopeSelectionMode::Descendants, targets));
        }
        return Ok((ScopeSelectionMode::Scope, vec![scope_target(&root)?]));
    }
    if parsed.descendants {
        let targets = registry_targets_under(repo.root())?
            .unwrap_or_else(|| registry_unavailable_fallback(repo.root()));
        return Ok((ScopeSelectionMode::Descendants, targets));
    }
    // Default and `--all-scopes` share the same enumeration: every indexed,
    // participating scope in the registry (05 §1.8 / 06 §3, CT3-MULTI-008). The
    // difference between the two is spec-undefined (§C-8) and intentionally none.
    let _all_scopes = parsed.all_scopes;
    let targets =
        registry_all_targets()?.unwrap_or_else(|| registry_unavailable_fallback(repo.root()));
    Ok((ScopeSelectionMode::All, targets))
}

/// All indexed, participating scopes from the registry (deterministic order).
/// `Ok(None)` when the registry could not be *opened* (transient lock or real
/// error) — deliberately distinct from `Ok(Some(vec![]))` (registry opened, no
/// eligible scopes). The caller degrades an open failure to the current scope
/// instead of a misleading "no indexed scopes registered" that would erase the
/// healthy scope the user is standing in (P6, Opus F2); an empty registry keeps
/// the exit-4 guidance.
fn registry_all_targets() -> Result<Option<Vec<ScopeTarget>>> {
    let Ok(db) = RegistryDb::open_default() else {
        return Ok(None);
    };
    let entries = db.search_targets().map_err(index_to_kcs)?;
    Ok(Some(
        entries
            .into_iter()
            // R15-3 (defense in depth): a registry row is a valid search target only
            // when the on-disk `.kcs` still carries the SAME scope_id. `register_scope`
            // retires stale same-path rows on the next init/index, but a search that
            // runs BEFORE that re-registration must not trust them — otherwise a
            // deleted-then-re-init'd folder double-returns its doc via a dead scope_id.
            // Mirrors the on-disk verification `resolve_scope_id_in_registry` already
            // does on the Evidence-resolution side (removing the search/resolve
            // asymmetry).
            .filter(registry_entry_is_live)
            .map(registry_entry_target)
            .filter(|target| participates_in_global_search(&target.kcs_dir))
            .collect(),
    ))
}

/// R15-3: reject a registry row ONLY when the on-disk `.kcs` at `entry.root_path` opens
/// and carries a DIFFERENT `scope_id` — i.e. a delete-and-re-`init` minted a fresh
/// scope_id at the same path (the stale-duplicate case). An open/read failure
/// (unreadable/locked/absent `.kcs`) is deliberately KEPT as a target: it is not a
/// confirmed stale row, and silently dropping it would hide a genuinely unreachable
/// scope that the search must instead surface as an `excluded_scopes` partial failure
/// (05 §1.8). Only a positively-confirmed scope_id mismatch is filtered here.
fn registry_entry_is_live(entry: &RegistryEntry) -> bool {
    match scope_target(Path::new(&entry.root_path)) {
        Ok(target) => target.scope_id == entry.scope_id,
        Err(_) => true,
    }
}

/// Registered scopes whose root path is at or below `root` (05 §1.8 prefix
/// filter). `Ok(None)` propagates a registry open failure (see
/// [`registry_all_targets`]).
fn registry_targets_under(root: &Path) -> Result<Option<Vec<ScopeTarget>>> {
    Ok(registry_all_targets()?.map(|targets| {
        targets
            .into_iter()
            .filter(|target| target.repo_root.starts_with(root))
            .collect()
    }))
}

/// P6: when the registry cannot be opened (distinct from an empty registry),
/// degrade a default / `--all-scopes` / `--descendants` search to `root`'s own
/// scope — already held open and known reachable — rather than returning a
/// misleading KCS-E-SEARCH-SCOPE-ALL-FAILED-001. Empty when `root` is not itself
/// a scope (then the search is a genuine all-failed, exit 4, as before).
fn registry_unavailable_fallback(root: &Path) -> Vec<ScopeTarget> {
    eprintln!(
        "warning: scope registry unavailable (search cache; recover with `kcs index`); \
         searching the current scope only"
    );
    match scope_target(root) {
        Ok(target) => vec![target],
        Err(_) => Vec::new(),
    }
}

fn registry_entry_target(entry: RegistryEntry) -> ScopeTarget {
    ScopeTarget {
        repo_root: PathBuf::from(entry.root_path),
        kcs_dir: PathBuf::from(entry.kcs_path),
        scope_id: entry.scope_id,
    }
}

/// Upsert the scope into the device-local registry (03 §4 cache, K3). Best-effort:
/// a registry write never fails `init` / `index`.
fn register_scope(repo: &Repository, indexed: bool) {
    let Ok(scope_id) = scope_id(repo.kcs_dir()) else {
        return;
    };
    let entry = RegistryEntry {
        scope_id,
        kcs_path: repo.kcs_dir().display().to_string(),
        root_path: repo.root().display().to_string(),
        participates_in_global_search: participates_in_global_search(repo.kcs_dir()),
        indexed,
        last_seen_at: now_utc_seconds(),
    };
    if let Ok(db) = RegistryDb::open_default() {
        // R15-3: retire any stale registration for THIS `.kcs` path under a DIFFERENT
        // scope_id first. A deleted-then-re-`init`ed folder mints a fresh scope_id at
        // the same path; the composite PK `(scope_id, kcs_path)` would otherwise leave
        // the old row forever, double-returning the doc in multi-scope search with a
        // dead-pointer (unresolvable) scope_id. Best-effort like the upsert itself.
        if let Err(error) = db.retire_stale_kcs_path(&entry.kcs_path, &entry.scope_id) {
            eprintln!(
                "warning: scope registry cleanup failed (search cache; recover with `kcs index`): {}",
                terminal_safe_text(&error.to_string(), false)
            );
        }
        if let Err(error) = db.upsert(&entry) {
            eprintln!(
                "warning: scope registry write failed (search cache; recover with `kcs index`): {}",
                terminal_safe_text(&error.to_string(), false)
            );
        }
    }
}

/// `participates_in_global_search` (defaults to true, 05 §1.8). The config schema
/// (config.schema.json) puts this under `[scope]`; `[search]` is also accepted for
/// robustness. Either way, absence means "participates".
fn participates_in_global_search(kcs_dir: &Path) -> bool {
    let path = kcs_dir.join("config.toml");
    let Ok(text) = fs::read_to_string(&path) else {
        return true;
    };
    let Ok(value) = toml::from_str::<toml::Value>(&text) else {
        return true;
    };
    for section in ["scope", "search"] {
        if let Some(flag) = value
            .get(section)
            .and_then(|table| table.get("participates_in_global_search"))
            .and_then(toml::Value::as_bool)
        {
            return flag;
        }
    }
    true
}

fn scope_target(root: &Path) -> Result<ScopeTarget> {
    let repo = Repository::open_for_search(root)?;
    Ok(ScopeTarget {
        repo_root: repo.root().to_path_buf(),
        kcs_dir: repo.kcs_dir().to_path_buf(),
        scope_id: scope_id(repo.kcs_dir())?,
    })
}

fn scope_id(kcs_dir: &Path) -> Result<String> {
    let path = kcs_dir.join("scope.json");
    let value: Value = serde_json::from_slice(
        &fs::read(&path)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?,
    )
    .map_err(|err| KcsError::schema(err.to_string()))?;
    value
        .get("scope_id")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| KcsError::schema("scope.json missing scope_id"))
}

/// Materialize the live chunks of a scope with display metadata (Evidence Pointer
/// short-hash resolution). Not used for ranking (K2 — ranking reads `sqlite.db`).
fn load_searchable_chunks(target: &ScopeTarget) -> Result<Vec<SearchableChunk>> {
    let repo = Repository::open(&target.repo_root)?;
    let head = repo.head_commit_hash()?.unwrap_or_default();
    if head.is_empty() {
        return Ok(Vec::new());
    }
    // L3: short-hash / pointer resolution must survive a bare `kcs snapshot` that
    // advances HEAD without refreshing the JSON tree_entries projection. Read the
    // live entries from SQLite and project the current HEAD lazily, exactly as
    // search does (`ensure_snapshot_tree_entries`); the old JSON path went stale
    // right after a snapshot (search succeeded on the same input — the asymmetry).
    let db_path = sqlite_path(&target.kcs_dir);
    if !db_path.exists() {
        return Ok(Vec::new());
    }
    let conn = Connection::open(&db_path).map_err(|err| KcsError::schema(err.to_string()))?;
    ensure_snapshot_tree_entries(&repo, &conn, &head)?;
    let live = live_tree_entries_at(&conn, &head)?;
    Ok(read_stored_chunks(&target.kcs_dir)?
        .into_iter()
        .filter_map(|stored| {
            let key = (
                stored.row.raw_hash.clone(),
                stored.row.tool_profile_hash.clone(),
                stored.row.gen,
            );
            live.get(&key).map(|path| SearchableChunk {
                row: stored.row,
                scope_id: target.scope_id.clone(),
                scope_path: target.repo_root.clone(),
                snapshot_at: head.clone(),
                path_at_commit: path.clone(),
            })
        })
        .collect())
}

/// Live tree-entry map for `head` read from SQLite: (raw_hash, tool_profile_hash,
/// gen) -> path_at_commit. Rows without a `tool_profile_hash` (raw-only) carry no
/// chunk and are skipped.
fn live_tree_entries_at(
    conn: &Connection,
    head: &str,
) -> Result<BTreeMap<(String, String, u64), String>> {
    let mut stmt = conn
        .prepare(
            "SELECT raw_hash, tool_profile_hash, gen, path
             FROM tree_entries WHERE commit_hash = ?1",
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let rows = stmt
        .query_map(rusqlite::params![head], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Option<String>>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, String>(3)?,
            ))
        })
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let mut map = BTreeMap::new();
    for row in rows {
        let (raw_hash, tool_profile_hash, gen, path) =
            row.map_err(|err| KcsError::schema(err.to_string()))?;
        if let Some(tool) = tool_profile_hash {
            map.insert((raw_hash, tool, gen as u64), path);
        }
    }
    Ok(map)
}

fn search_mode_json(mode: SearchMode) -> &'static str {
    match mode {
        SearchMode::Auto => "auto",
        SearchMode::Text => "text",
        SearchMode::Vector => "vector",
        SearchMode::Hybrid => "hybrid",
    }
}

fn empty_search_response(
    parsed: &ParsedSearch,
    repo: &Repository,
    started: Instant,
    mode: &ResolvedMode,
    searched: &[SearchedScopeInfo],
    excluded_scopes: &[Value],
) -> Result<Value> {
    // Short queries still report the resolved mode honestly (auto -> text with the
    // vector-unavailable fallback). N8: index_status is now aggregated from the
    // actually-searched scopes (not a fixed 1.0), and a partial scope failure is
    // surfaced as exit 3 just like a ranked search.
    let searched_scopes = searched
        .iter()
        .map(|scope| {
            json!({
                "scope_id": scope.scope_id,
                "scope_path": scope.scope_path,
                "snapshot_at": scope.snapshot_at,
            })
        })
        .collect::<Vec<_>>();
    let mut response = json!({
        "query": parsed.query,
        "requested_mode": search_mode_json(mode.requested),
        "resolved_mode": search_mode_json(mode.resolved),
        "fallback": mode.fallback,
        "fallback_reason": mode.fallback_reason.clone().map(Value::from).unwrap_or(Value::Null),
        "error_code": mode.error_code.clone().map(Value::from).unwrap_or(Value::Null),
        // R11-7: non-null only under [search].fail_behavior = "warn" text fallback.
        "warning": mode.warning.clone().map(Value::from).unwrap_or(Value::Null),
        "diversify": { "strategy": "group_by_raw_hash" },
        "paging": { "limit": parsed.limit, "next_cursor": Value::Null },
        "searched_scopes": searched_scopes,
        "excluded_scopes": excluded_scopes,
        "index_status": compute_index_status(searched),
        "results": [],
    });
    append_search_logs(repo, &response, started);
    if !excluded_scopes.is_empty() {
        if let Some(object) = response.as_object_mut() {
            object.insert("__exit_code".to_owned(), json!(3));
        }
    }
    Ok(response)
}

/// R12-5: observability logging must never break the search result. A metrics.jsonl
/// or access.jsonl append failure (read-only file, disk full — both device-global,
/// so one bad file would otherwise stop EVERY scope's search with exit 1 and discard
/// the results it had already computed) is downgraded to a stderr warning; the
/// result still returns. This makes the search logs symmetric with errors.jsonl,
/// which already ignores its own write failure (`let _ =` in main()). Success and
/// failure of the append are otherwise identical, so this returns `()`.
fn append_search_logs(repo: &Repository, response: &Value, started: Instant) {
    let latency_ms = started.elapsed().as_secs_f64() * 1000.0;
    let scope_count = response
        .get("searched_scopes")
        .and_then(Value::as_array)
        .map(Vec::len)
        .unwrap_or(0);
    let result_count = response
        .get("results")
        .and_then(Value::as_array)
        .map(Vec::len)
        .unwrap_or(0);
    // Per-search latency record (05 §7, K8a): code KCS-M-SEARCH-001 / component
    // "search" / metric search.latency_ms. redact_logs default omits query & path.
    if let Err(error) = append_jsonl_cli(
        &data_home().join("kcs/logs/metrics.jsonl"),
        &json!({
            "ts": now_utc_seconds(),
            "level": "info",
            "code": "KCS-M-SEARCH-001",
            "component": "search",
            "message": "search completed",
            "metric": "search.latency_ms",
            "value": latency_ms,
            "context": {
                "mode": response.get("resolved_mode").and_then(Value::as_str).unwrap_or("text"),
                "scope_count": scope_count,
                "result_count": result_count,
            },
        }),
        device_logs_retention_days(),
    ) {
        eprintln!(
            "warning: failed to append search metrics log: {}",
            terminal_safe_text(&error.to_string(), false)
        );
    }
    // R12-2: access.jsonl is scope-local, so its redact_logs is governed by the
    // scope config first, falling back to the device-global user config, then the
    // secure default (true). Under redaction (the default) the query is masked;
    // with an explicit `redact_logs = false` the real query text is recorded.
    let query_field = if access_log_redact(repo) {
        json!("[redacted]")
    } else {
        response
            .get("query")
            .cloned()
            .unwrap_or_else(|| json!("[redacted]"))
    };
    if let Err(error) = append_jsonl_cli(
        &repo.kcs_dir().join("logs/access.jsonl"),
        &json!({
            "ts": now_utc_seconds(),
            "level": "info",
            "code": "KCS-I-SEARCH-ACCESS-001",
            "component": "kcs-cli",
            "message": "search access",
            "context": {
                "query": query_field,
                "mode": response.get("resolved_mode").and_then(Value::as_str).unwrap_or("text"),
                "result_count": result_count,
            },
        }),
        scope_logs_retention_days(repo),
    ) {
        eprintln!(
            "warning: failed to append search access log: {}",
            terminal_safe_text(&error.to_string(), false)
        );
    }
}

/// R12-4: the per-search metrics.jsonl line for a FAILED search (result_count 0 +
/// the failure's error_code). Best-effort — a metrics write failure must never turn
/// a search error into a different one (R12-5), so the result is discarded.
fn append_failed_search_metrics(started: Instant, error: &KcsError) {
    let latency_ms = started.elapsed().as_secs_f64() * 1000.0;
    let _ = append_jsonl_cli(
        &data_home().join("kcs/logs/metrics.jsonl"),
        &json!({
            "ts": now_utc_seconds(),
            "level": "info",
            "code": "KCS-M-SEARCH-001",
            "component": "search",
            "message": "search failed",
            "metric": "search.latency_ms",
            "value": latency_ms,
            "context": {
                "result_count": 0,
                "error_code": error.error_code(),
            },
        }),
        device_logs_retention_days(),
    );
}

/// R12-2: effective `redact_logs` for the scope-local `access.jsonl`. The scope
/// config wins over the user config (the log lives in `.kcs/`, and 07 §7 attributes
/// `[adapter.policy]` to `.kcs/config.toml`); the device-global events/metrics/
/// errors logs stay user-config-governed via `redact_logs_enabled` in kcs-core.
/// Absent everywhere → the secure default (true).
fn access_log_redact(repo: &Repository) -> bool {
    read_redact_logs_config(&repo.kcs_dir().join("config.toml"))
        .or_else(|| read_redact_logs_config(&user_config_toml_path()))
        .unwrap_or(true)
}

fn read_redact_logs_config(path: &Path) -> Option<bool> {
    let text = fs::read_to_string(path).ok()?;
    let value: toml::Value = toml::from_str(&text).ok()?;
    value
        .get("adapter")
        .and_then(|adapter| adapter.get("policy"))
        .and_then(|policy| policy.get("redact_logs"))
        .and_then(toml::Value::as_bool)
}

/// Documented default for `adapter.policy.max_input_bytes` (07 §7): 100 MB.
const DEFAULT_MAX_INPUT_BYTES: u64 = 104_857_600;

/// R12-2: effective `adapter.policy.max_input_bytes` — scope config wins over user
/// config, default 100 MB (07 §7). Enforced as an input gate in `run_index_pipeline`.
fn effective_max_input_bytes(repo: &Repository) -> u64 {
    read_max_input_bytes_config(&repo.kcs_dir().join("config.toml"))
        .or_else(|| read_max_input_bytes_config(&user_config_toml_path()))
        .unwrap_or(DEFAULT_MAX_INPUT_BYTES)
}

fn read_max_input_bytes_config(path: &Path) -> Option<u64> {
    let text = fs::read_to_string(path).ok()?;
    let value: toml::Value = toml::from_str(&text).ok()?;
    value
        .get("adapter")
        .and_then(|adapter| adapter.get("policy"))
        .and_then(|policy| policy.get("max_input_bytes"))
        .and_then(toml::Value::as_integer)
        .and_then(|bytes| u64::try_from(bytes).ok())
}

/// Effective Step 4 bbox-annotation policy. Scope config overrides user config;
/// absence at both levels is the frozen secure/searchable default `true`.
fn bbox_annotation_enabled(repo: &Repository) -> bool {
    effective_bbox_annotation_policy(
        &repo.kcs_dir().join("config.toml"),
        &user_config_toml_path(),
    )
}

fn effective_bbox_annotation_policy(scope_config: &Path, user_config: &Path) -> bool {
    read_bbox_annotation_config(scope_config)
        .or_else(|| read_bbox_annotation_config(user_config))
        .unwrap_or(true)
}

fn read_bbox_annotation_config(path: &Path) -> Option<bool> {
    let text = fs::read_to_string(path).ok()?;
    let value: toml::Value = toml::from_str(&text).ok()?;
    value
        .get("markdownize")
        .and_then(|markdownize| markdownize.get("bbox_annotation"))
        .and_then(|bbox| bbox.get("enabled"))
        .and_then(toml::Value::as_bool)
}

/// R12-1: effective `[markdownize.incremental]` (docs/10:537, docs/03:595). `enabled`
/// / `threshold` / `max_consecutive` were documented `.kcs/config.toml` overrides but
/// hardcoded (0.30 / 5) in the mode decision. `include_neighbors` is enforced
/// separately (no implementation concept → non-default rejected in
/// `enforce_config_semantics`).
struct IncrementalConfig {
    enabled: bool,
    threshold: f64,
    max_consecutive: u32,
}

fn effective_incremental_config(repo: &Repository) -> Result<IncrementalConfig> {
    let scope = read_incremental_tuning(&repo.kcs_dir().join("config.toml"))?;
    let user = read_incremental_tuning(&user_config_toml_path())?;
    Ok(IncrementalConfig {
        enabled: scope.0.or(user.0).unwrap_or(true),
        threshold: scope.1.or(user.1).unwrap_or(0.30),
        max_consecutive: scope.2.or(user.2).unwrap_or(5),
    })
}

fn read_incremental_tuning(path: &Path) -> Result<(Option<bool>, Option<f64>, Option<u32>)> {
    let Ok(text) = fs::read_to_string(path) else {
        return Ok((None, None, None));
    };
    let value: toml::Value =
        toml::from_str(&text).map_err(|err| KcsError::schema(err.to_string()))?;
    let incremental = value
        .get("markdownize")
        .and_then(|markdownize| markdownize.get("incremental"));
    let enabled = incremental
        .and_then(|incremental| incremental.get("enabled"))
        .and_then(toml::Value::as_bool);
    let threshold = toml_f64(incremental.and_then(|incremental| incremental.get("threshold")));
    let max_consecutive =
        toml_u64(incremental.and_then(|incremental| incremental.get("max_consecutive")))
            .and_then(|value| u32::try_from(value).ok());
    Ok((enabled, threshold, max_consecutive))
}

/// R13-3: the observability logs (metrics device-global, access scope-local) go
/// through the shared rotating writer so they get the documented daily rotation +
/// retention prune (docs/06 §13 / docs/10 §12.6), same as events/errors. Rotation
/// is best-effort; only the final append can fail (R12-5).
fn append_jsonl_cli(path: &Path, value: &Value, retention_days: u32) -> Result<()> {
    kcs_core::scope::append_jsonl_rotating(path, value, retention_days)
}

/// R13-3: `[logs] retention_days` for the device-global logs (metrics), read from
/// the user config, default 30.
fn device_logs_retention_days() -> u32 {
    kcs_core::scope::read_logs_retention_days(&user_config_toml_path())
        .unwrap_or(kcs_core::scope::DEFAULT_LOG_RETENTION_DAYS)
}

/// R13-3: `[logs] retention_days` for the scope-local `access.jsonl` — the scope
/// config wins over the user config (the log lives in `.kcs/`), then the 30-day
/// default. Mirrors `access_log_redact`'s precedence.
fn scope_logs_retention_days(repo: &Repository) -> u32 {
    kcs_core::scope::read_logs_retention_days(&repo.kcs_dir().join("config.toml"))
        .or_else(|| kcs_core::scope::read_logs_retention_days(&user_config_toml_path()))
        .unwrap_or(kcs_core::scope::DEFAULT_LOG_RETENTION_DAYS)
}

fn atomic_overwrite_file(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent)
        .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("file");
    let tmp = parent.join(format!(
        ".{name}.tmp-{}-{}",
        process::id(),
        new_ulid(parent)
    ));
    let result = (|| -> std::io::Result<()> {
        let mut file = OpenOptions::new().write(true).create_new(true).open(&tmp)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        fs::rename(&tmp, path)?;
        Ok(())
    })();
    if let Err(err) = result {
        let _ = fs::remove_file(&tmp);
        return Err(KcsError::io(err.to_string(), path.display().to_string()));
    }
    Ok(())
}

#[derive(Debug)]
/// Successful resolution of an Evidence Pointer (08 §3). Failure modes
/// (scope_unreachable / tombstoned / not_found) are surfaced as `Err(KcsError)`
/// with the exit-4 codes from 08 §3.2 / §4.
struct PointerResolution {
    path: Option<PathBuf>,
    text: Option<String>,
    temporary: bool,
    commit_shallow: bool,
}

/// Reads the raw `<pointer>` operand (08 §2.3), resolving `-` from stdin.
/// Branching into evidence-pointer vs `object` URI happens in the caller.
fn read_pointer_input(args: Vec<String>) -> Result<String> {
    const MAX_POINTER_INPUT_BYTES: u64 = 64 * 1024;
    let mut args = args.into_iter();
    let Some(pointer) = args.next() else {
        return Err(KcsError::invalid_usage("pointer argument is required"));
    };
    if let Some(extra) = args.next() {
        return Err(KcsError::invalid_usage(format!(
            "unexpected pointer argument: {extra}"
        )));
    }
    if pointer == "-" {
        let mut bytes = Vec::new();
        std::io::stdin()
            .take(MAX_POINTER_INPUT_BYTES + 1)
            .read_to_end(&mut bytes)
            .map_err(|err| KcsError::io(err.to_string(), "stdin"))?;
        if bytes.len() as u64 > MAX_POINTER_INPUT_BYTES {
            return Err(KcsError::invalid_usage(
                "pointer stdin exceeds the 64 KiB limit",
            ));
        }
        let input = String::from_utf8(bytes)
            .map_err(|_| KcsError::invalid_usage("pointer stdin must be UTF-8"))?;
        return Ok(input.trim().to_owned());
    }
    Ok(pointer)
}

/// Parses the non-short `<pointer>` operand forms (08 §2.3): a `kcs://` evidence
/// URI or inline JSON. The `sha256:` short form is resolved separately by
/// [`resolve_short_hash_command`] (it may be a raw *or* a chunk hash and needs
/// open/view context), and object URIs are handled before this is reached.
fn parse_pointer_text(pointer: &str) -> Result<EvidencePointer> {
    if pointer.starts_with("kcs://") {
        return parse_evidence_pointer_uri(pointer).map_err(search_to_kcs);
    }
    if pointer.trim_start().starts_with('{') {
        let pointer: EvidencePointer =
            serde_json::from_str(pointer).map_err(|err| KcsError::schema(err.to_string()))?;
        if pointer.schema_version != EVIDENCE_POINTER_SCHEMA_VERSION {
            return Err(KcsError::schema("unsupported evidence schema version"));
        }
        return Ok(pointer);
    }
    Err(KcsError::invalid_usage("invalid pointer argument"))
}

/// Resolution of a `sha256:` short-form operand (08 §2.3 rule 4).
enum ShortHash {
    /// The short hash is a `chunk_hash` — resolve as a full Evidence Pointer.
    Chunk(Box<EvidencePointer>),
    /// The short hash is a `raw_hash` — resolve the raw object directly. Multiple
    /// chunks sharing this raw_hash (a normal multi-heading file) are the *same*
    /// file, so this is unambiguous per rule 4 ("raw_hash 名前空間の一致は
    /// ファイル単位で一意なら OK").
    Raw {
        target: ScopeTarget,
        raw_hash: String,
        path_hint: Option<String>,
    },
}

/// Classify a `sha256:` short hash against the current `.kcs` + HEAD (08 §2.3
/// rule 4). Ambiguity is only *across kinds* (the hash is simultaneously a
/// chunk_hash and a raw_hash) — never among the several chunks of one file.
/// O6: a `sha256:` short-hash operand must carry a lowercase-hex digest of at
/// least 4 chars before it can reach `cas_object_path`'s `digest[0..2]`/`[2..4]`
/// slices (which panic out of range on `sha256:a`) or any lookup. A malformed
/// operand is a usage error (KCS-E-CONFIG-USAGE-001, exit 2), never a crash.
fn validate_short_hash_operand(hash: &str) -> Result<()> {
    let digest = hash.strip_prefix("sha256:").unwrap_or(hash);
    if digest.len() < 4
        || !digest
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    {
        return Err(KcsError::invalid_usage(
            "short hash must be `sha256:` followed by at least 4 lowercase hex characters",
        ));
    }
    Ok(())
}

fn classify_short_hash(hash: &str) -> Result<ShortHash> {
    validate_short_hash_operand(hash)?;
    let repo = Repository::open_current()?;
    let target = scope_target(repo.root())?;
    let chunks = load_searchable_chunks(&target)?;

    let chunk_match = chunks.iter().find(|chunk| chunk.row.chunk_id == hash);
    let raw_path_hint = chunks
        .iter()
        .find(|chunk| chunk.row.raw_hash == hash)
        .map(|chunk| chunk.path_at_commit.clone());
    // A raw_hash may name a file with no chunks (raw-only entry); fall back to the
    // working tree / CAS raw object for existence.
    let is_raw = raw_path_hint.is_some()
        || read_tombstone(&target, hash)?.is_some()
        || raw_object_present(&target, hash)?;
    let is_chunk = chunk_match.is_some();

    match (is_chunk, is_raw) {
        (true, true) => Err(KcsError::new(
            "KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001",
            "short hash matches both a chunk_hash and a raw_hash; disambiguate with a full pointer",
            json!({ "hash": hash, "kinds": ["chunk", "raw"] }),
            ExitCode::InvalidUsage,
        )),
        (true, false) => {
            let chunk = chunk_match.expect("chunk_match is Some");
            enforce_purge_read_barrier(&target, &chunk.row.raw_hash)?;
            let pointer = issue_evidence_pointer(EvidencePointerIssueRequest {
                scope_id: chunk.scope_id.clone(),
                scope_path: Some(chunk.scope_path.display().to_string()),
                commit: chunk.snapshot_at.clone(),
                tree: None,
                raw_hash: chunk.row.raw_hash.clone(),
                tool_profile_hash: chunk.row.tool_profile_hash.clone(),
                chunk_hash: chunk.row.chunk_id.clone(),
                path_at_commit: Some(chunk.path_at_commit.clone()),
                heading_path: chunk.row.heading_path.clone(),
                section_id: chunk.row.section_id.clone(),
                char_start: chunk.row.char_start,
                char_end: chunk.row.char_end,
            })
            .map_err(search_to_kcs)?;
            enforce_purge_read_barrier(&target, &chunk.row.raw_hash)?;
            Ok(ShortHash::Chunk(Box::new(pointer)))
        }
        (false, true) => {
            enforce_purge_read_barrier(&target, hash)?;
            Ok(ShortHash::Raw {
                target,
                raw_hash: hash.to_owned(),
                path_hint: raw_path_hint,
            })
        }
        (false, false) => Err(KcsError::invalid_usage(
            "short hash is not found in the current scope",
        )),
    }
}

/// True when a raw object with `raw_hash` is present in the working tree or the
/// CAS raw store (08 §2.3 rule 4 raw resolution). Used only for the raw-only
/// short-hash case (no chunk carries the raw_hash).
fn raw_object_present(target: &ScopeTarget, raw_hash: &str) -> Result<bool> {
    if cas_object_present(&target.kcs_dir, "raw", raw_hash, MAX_RAW_OBJECT_BYTES)? {
        return Ok(true);
    }
    Ok(find_working_tree_raw(&target.repo_root, raw_hash)?.is_some())
}

/// Resolve a `sha256:` short-form operand for `kcs open` / `kcs view`
/// (08 §2.3 rule 4). Handles both the chunk_hash and raw_hash kinds.
fn resolve_short_hash_command(hash: &str, as_view: bool) -> Result<Value> {
    match classify_short_hash(hash)? {
        ShortHash::Chunk(pointer) => {
            let resolved = resolve_pointer_for_cli(&pointer)?;
            if as_view {
                Ok(json!({
                    "status": "viewed",
                    "raw_hash": pointer.raw_hash,
                    "chunk_hash": pointer.chunk_hash,
                    "text": resolved.text.unwrap_or_default(),
                    "path": resolved.path,
                    "commit_shallow": resolved.commit_shallow,
                }))
            } else {
                Ok(json!({
                    "status": "opened",
                    "path": resolved.path,
                    "raw_hash": pointer.raw_hash,
                    "chunk_hash": pointer.chunk_hash,
                    "temporary": resolved.temporary,
                    "commit_shallow": resolved.commit_shallow,
                }))
            }
        }
        ShortHash::Raw {
            target,
            raw_hash,
            path_hint,
        } => match open_raw_object(&target, &raw_hash, path_hint.as_deref())? {
            // A raw object has no chunk text; open/view surface only its path.
            Some((path, temporary)) => {
                if let Err(error) = enforce_purge_read_barrier(&target, &raw_hash) {
                    if temporary {
                        let _ = fs::remove_file(&path);
                    }
                    return Err(error);
                }
                let status = if as_view { "viewed" } else { "opened" };
                Ok(json!({
                    "status": status,
                    "object_type": "raw",
                    "raw_hash": raw_hash,
                    "path": path,
                    "temporary": temporary,
                }))
            }
            None => Err(purge_not_found_error(&target, &raw_hash)),
        },
    }
}

fn resolve_pointer_for_cli(pointer: &EvidencePointer) -> Result<PointerResolution> {
    // 08 §3.1 step 1: two-stage scope resolution (scope_path hint -> registry).
    let target = resolve_scope_target(&pointer.scope_id, pointer.scope_path.as_deref())?;
    let repo = Repository::open(&target.repo_root)?;

    // 08 §3.1 step 2: fetch the commit object. R17-1: a MISSING commit object
    // (never existed / externally deleted — e.g. a `view`/`open` pointer whose
    // `commit` field is a forged hash) is an Evidence-resolution FAILURE, NOT a
    // shallow commit. docs/08 §3.2:150 makes commit-object *existence* the resolution
    // precondition ("shallow でもよい" tolerates tree GC precisely *because the commit
    // still exists*); docs/05 §3.6's "resolution never fails on a shallow commit"
    // guarantee is therefore scoped to a genuine shallow commit (commit present, tree
    // GC'd) and does NOT extend to a missing commit object. R16-1 best-effort'd this
    // read for status/log/search and that stays — those are pure reads with no
    // authenticity gate to bypass — but resolve_pointer_for_cli is the ONE Evidence-
    // authenticity entry point. Folding a missing commit into the shallow path sets
    // entry_gen=None, which skips BOTH the tree-membership check (raw_hash ∈
    // commit.tree) and the N5 gen binding below — letting a forged `commit` splice a
    // newer-generation chunk (post `reindex --force`) under a commit that never
    // normalized it. So a missing commit is rejected here, not resolved best-effort.
    let commit = match repo.read_commit(&pointer.commit) {
        Ok(commit) => commit,
        Err(error) if is_store_not_found(&error) => {
            return Err(unresolvable_commit_pointer_error(pointer));
        }
        Err(error) => return Err(error),
    };

    // 08 §3.1 step 2a/3-4: a genuine shallow commit (commit object present, its tree
    // object discarded/GC'd) skips the tree walk and resolves the chunk directly;
    // otherwise the raw_hash must appear in commit.tree for the pointer to resolve
    // against *this* commit's snapshot (not the working tree of some later commit).
    // A missing commit object never reaches here — R17-1 rejected it above.
    // `entry_gen` is the tree entry's normalization generation on a non-shallow
    // commit; `None` on the shallow path (no tree to read). It binds the chunk's
    // gen below (N5).
    let (commit_shallow, entry_gen) = match repo.read_tree(&commit.tree) {
        Ok(tree) => {
            let entry = tree
                .entries
                .iter()
                .find(|entry| entry.raw_hash == pointer.raw_hash);
            let Some(entry) = entry else {
                // step 5 (tombstone) is checked before declaring not_found.
                enforce_purge_read_barrier(&target, &pointer.raw_hash)?;
                return Err(purge_not_found_error(&target, &pointer.raw_hash));
            };
            // M6: the tree entry's normalization must bind to the pointer's
            // tool_profile_hash. N5: it must ALSO bind `gen` (checked below against
            // the resolved chunk), so a pointer that keeps an old commit but swaps
            // in a newer-generation chunk_hash produced by `reindex --force` cannot
            // resolve (the gen axis M6 missed, 08 §3). A tree entry with no explicit
            // normalization (e.g. a bare `kcs snapshot` that advanced HEAD without
            // re-recording normalize refs, L3) carries no gen to bind, so it keeps
            // the pre-existing behavior — the chunk (raw, tool) identity check below
            // is the available guard. `entry_gen` stays `None` there.
            let entry_gen = match &entry.normalize {
                Some(normalize) => {
                    if normalize.tool_profile_hash != pointer.tool_profile_hash {
                        return Err(invalid_pointer_identity_error(pointer));
                    }
                    Some(normalize.gen)
                }
                None => None,
            };
            (false, entry_gen)
        }
        // Tree object gone (genuine shallow: commit present, tree GC'd) — resolve the
        // chunk directly, with gen unbound.
        Err(error) if is_store_not_found(&error) => (true, None),
        Err(error) => return Err(error),
    };

    // 08 §3.1 step 5: purged raw_hash carrying a tombstone -> tombstone response.
    enforce_purge_read_barrier(&target, &pointer.raw_hash)?;

    // Erase-mode purge intentionally leaves no public marker. Resolve raw
    // liveness before chunk/profile availability so an old pointer whose raw and
    // derivatives were deleted reports the required purge not-found state rather
    // than the unrelated retarget-required profile error.
    if !raw_object_present(&target, &pointer.raw_hash)? {
        return Err(purge_not_found_error(&target, &pointer.raw_hash));
    }

    // 08 §3.1 step 6-7: chunk_hash -> durable semantic chunk CAS. SQLite and
    // chunks.jsonl are acceleration/rebuild inputs and cannot independently make
    // a pointer alive (Step 4 decision #69/#75).
    // A pointer whose chunk_hash has NO materialized chunk object in this scope
    // cannot be served under this tool_profile_hash — that is 08 §3.2's
    // "tool_profile_hash 不一致: chunk が存在しない場合は retarget が必要 (§5)",
    // exit 8 (06 §7). Applies on the shallow path too: chunk rows outlive tree
    // discard, so their absence means the profile mismatch, not GC.
    let chunk = match ObjectStore::new(&target.kcs_dir).read_chunk(&pointer.chunk_hash) {
        Ok(chunk) => chunk,
        Err(error) if is_store_not_found(&error) => {
            return Err(KcsError::new(
                "KCS-E-EVIDENCE-RETARGET-REQUIRED-001",
                "chunk not materialized for this tool_profile_hash; retarget required (08 §5)",
                json!({
                    "chunk_hash": pointer.chunk_hash,
                    "tool_profile_hash": pointer.tool_profile_hash,
                    "raw_hash": pointer.raw_hash,
                }),
                ExitCode::IncompatibleProfile,
            ));
        }
        Err(error) => return Err(error),
    };
    // M6: the resolved chunk row must bind to the pointer's (raw_hash,
    // tool_profile_hash). A chunk_hash that materializes under a *different* raw
    // or tool identity than the pointer claims is a tampered pointer — reject it
    // rather than serve inconsistent evidence (body from A, raw from B).
    if chunk.raw_hash != pointer.raw_hash || chunk.tool_profile_hash != pointer.tool_profile_hash {
        return Err(invalid_pointer_identity_error(pointer));
    }
    // N5: on a non-shallow commit, the chunk's generation must equal the tree
    // entry's normalize.gen. Otherwise a pointer to an old commit could resolve a
    // chunk_hash from a *newer* generation (post `reindex --force`), serving body
    // from gen N+1 under a commit that only ever normalized gen N. The shallow
    // path has no tree entry, so gen stays unbound there (chunk (raw, tool)
    // identity is the only available check).
    if let Some(entry_gen) = entry_gen {
        if chunk.gen != entry_gen {
            return Err(invalid_pointer_identity_error(pointer));
        }
    }
    let text = chunk.text;

    // Raw object resolution: working tree first (rename-tolerant), else CAS
    // read-only expansion. Absent from both with no tombstone -> not_found.
    match open_raw_object(
        &target,
        &pointer.raw_hash,
        pointer.path_at_commit.as_deref(),
    )? {
        Some((path, temporary)) => {
            if let Err(error) = enforce_purge_read_barrier(&target, &pointer.raw_hash) {
                if temporary {
                    let _ = fs::remove_file(&path);
                }
                return Err(error);
            }
            Ok(PointerResolution {
                path: Some(path),
                text: Some(text),
                temporary,
                commit_shallow,
            })
        }
        None => Err(purge_not_found_error(&target, &pointer.raw_hash)),
    }
}

/// Two-stage scope resolution (08 §3.1 step 1). Root trust is `scope_id`; the
/// `scope_path` hint and the scope-registry are both non-authoritative caches
/// (05 §1.7 truth vs cache).
/// Registry lookup of a `scope_id` with the same tie-detection the Evidence path
/// uses (08 §3.1 step 1b): the newest `last_seen_at` wins, but two distinct
/// `.kcs` sharing that newest timestamp are ambiguous
/// (KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001). `Ok(None)` when no registered `.kcs`
/// still resolves to this scope_id. Shared by `resolve_scope_target` (Evidence)
/// and `resolve_cursor_exec_scopes` (search cursor) so a `.kcs`-copy collision is
/// detected identically on both paths (O7).
fn resolve_scope_id_in_registry(scope_id: &str) -> Result<Option<ScopeTarget>> {
    let registry = match RegistryDb::open_default() {
        Ok(registry) => registry,
        // P6: a registry *open* failure is not "scope_id absent". Surface it (the
        // caller still falls back to the scope_path hint) instead of silently
        // conflating it with a genuine registry miss; WAL + busy_timeout makes the
        // transient case rare, and a real failure is now observable.
        Err(_) => {
            eprintln!(
                "warning: scope registry unavailable (search cache); \
                 resolving evidence scope via the scope_path hint only"
            );
            return Ok(None);
        }
    };
    let Ok(entries) = registry.lookup_scope_id(scope_id) else {
        return Ok(None);
    };
    let mut resolved: Vec<(String, ScopeTarget)> = Vec::new();
    for entry in &entries {
        if let Some(target) = open_scope_from_hint(&entry.root_path) {
            if target.scope_id == scope_id {
                resolved.push((entry.last_seen_at.clone(), target));
            }
        }
    }
    if resolved.is_empty() {
        return Ok(None);
    }
    // Entries arrive newest-first (ORDER BY last_seen_at DESC); a tie across
    // distinct .kcs at that newest timestamp is ambiguous.
    let newest = resolved[0].0.clone();
    let mut newest_dirs = resolved
        .iter()
        .filter(|(seen, _)| *seen == newest)
        .map(|(_, target)| target.kcs_dir.clone())
        .collect::<Vec<_>>();
    newest_dirs.sort();
    newest_dirs.dedup();
    if newest_dirs.len() > 1 {
        return Err(scope_ambiguous_error(scope_id, &newest_dirs));
    }
    Ok(Some(resolved.remove(0).1))
}

fn resolve_scope_target(scope_id: &str, scope_path_hint: Option<&str>) -> Result<ScopeTarget> {
    // 1a. scope_path hint whose .kcs/scope.json matches scope_id.
    if let Some(hint) = scope_path_hint {
        if let Some(target) = open_scope_from_hint(hint) {
            if target.scope_id == scope_id {
                return Ok(target);
            }
        }
    }
    // 1b. scope-registry lookup by scope_id (last_seen_at newest first).
    if let Some(target) = resolve_scope_id_in_registry(scope_id)? {
        return Ok(target);
    }
    // Pragmatic fallback: the current working directory when it *is* the scope.
    // Object URIs carry no scope_path hint, and a freshly-created scope may not
    // yet be listed in the registry. Still gated on scope_id equality.
    if let Ok(repo) = Repository::open_current() {
        if let Ok(target) = scope_target(repo.root()) {
            if target.scope_id == scope_id {
                return Ok(target);
            }
        }
    }
    Err(scope_unreachable_error(scope_id))
}

/// Opens a `ScopeTarget` from a hint that is either a scope root or a `.kcs`
/// directory (08 §2.2 permits scope_path to name either). `None` if neither
/// resolves to a valid scope.
fn open_scope_from_hint(hint: &str) -> Option<ScopeTarget> {
    let path = Path::new(hint);
    if let Ok(target) = scope_target(path) {
        return Some(target);
    }
    if path.file_name() == Some(std::ffi::OsStr::new(".kcs")) {
        if let Some(parent) = path.parent() {
            if let Ok(target) = scope_target(parent) {
                return Some(target);
            }
        }
    }
    None
}

/// Working tree first (rename-tolerant), else a read-only expansion of the CAS
/// raw object under `$XDG_CACHE_HOME/kcs/open` (05 §4.2 / 06 §1.1). Returns
/// `Ok(None)` when the raw object is absent from both.
fn open_raw_object(
    target: &ScopeTarget,
    raw_hash: &str,
    path_hint: Option<&str>,
) -> Result<Option<(PathBuf, bool)>> {
    open_cas_byte_object(target, "raw", true, raw_hash, path_hint)
}

/// Open a CAS byte object (03 §2: raw / prepared / image), expanding it read-only
/// under `$XDG_CACHE_HOME/kcs/open` when it lives only in the store. `subdir`
/// selects the CAS type directory ("raw" / "prepared" / "images"). For `raw` the
/// working tree is checked first (rename tolerant, 05 §4.2); derived byte objects
/// live only in the CAS. Returns `Ok(None)` when the object is absent.
fn open_cas_byte_object(
    target: &ScopeTarget,
    subdir: &str,
    scan_working_tree: bool,
    hash: &str,
    path_hint: Option<&str>,
) -> Result<Option<(PathBuf, bool)>> {
    if !is_hash(hash) {
        return Err(KcsError::invalid_usage("CAS object hash is invalid"));
    }
    if scan_working_tree {
        if let Some(path) = find_working_tree_raw(&target.repo_root, hash)? {
            return Ok(Some((path, false)));
        }
    }
    let Some((_object_path, bytes)) =
        read_cas_byte_object(&target.kcs_dir, subdir, hash, MAX_RAW_OBJECT_BYTES)?
    else {
        return Ok(None);
    };
    let basename = path_hint.unwrap_or("object");
    // P9 (06 §1.1): the read-only expansion cache belongs under $XDG_CACHE_HOME
    // (regenerable, safe to purge), not $XDG_DATA_HOME (durable truth/state).
    let cache = open_cache_path(basename, hash);
    // M5: the open cache is idempotent. A prior open already materialized this
    // object read-only; a second open must reuse it, not `fs::copy` onto a
    // read-only destination (EACCES). Reuse the cached file when it already
    // exists (the CAS object is immutable, so the content is identical).
    if cache.is_file() {
        // R9-3: a cache dir/file materialized by an earlier (world-readable) build
        // is corrected in place on reuse — harden the subtree to 0700 and the file
        // to 0400 so document bytes written before this fix stop leaking to
        // group/other on a multi-user host.
        if let Some(parent) = cache.parent() {
            harden_open_cache_subtree(parent);
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = fs::set_permissions(&cache, fs::Permissions::from_mode(0o400));
        }
        return Ok(Some((cache, true)));
    }
    // Q2: prepared / image CAS objects were historically written non-atomically
    // (`fs::write` straight to the final path), so a crash / ENOSPC could leave a
    // partial file under a correct `sha256:` name that `if !path.exists()` then
    // adopts forever. Verify the object's bytes hash to their filename before
    // serving — mirroring `ObjectStore::read_by_hash` (cas.rs) — so a torn /
    // corrupt object is rejected as STORE-CORRUPT instead of returned as authentic
    // evidence. The immutable object is verified once here at first
    // materialization; the read-only open cache is reused as-is thereafter (M5).
    if let Some(parent) = cache.parent() {
        fs::create_dir_all(parent)
            .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
        // R9-3: the open/view expansion cache holds document bytes / images /
        // pre-OCR raw data, so — like the CAS it mirrors (P2, 0600) — its whole
        // `$XDG_CACHE_HOME/kcs` subtree must be owner-only (0700), not the umask
        // default (0755, world-readable).
        harden_open_cache_subtree(parent);
    }
    // R10-6: write the cache file atomically (temp in the same dir -> fsync -> 0400
    // -> rename) so a crash / ENOSPC / SIGKILL mid-write can never leave a torn
    // partial under the final cache name that the M5 cache-hit path (which does NOT
    // re-verify bytes) would later serve as authentic Evidence.
    write_open_cache_atomic(&cache, &bytes)?;
    Ok(Some((cache, true)))
}

fn read_bounded_cas_object(path: &Path, expected_hash: &str, max_bytes: u64) -> Result<Vec<u8>> {
    read_or_verify_bounded_cas_object(path, expected_hash, max_bytes, true)
}

fn verify_bounded_cas_object(path: &Path, expected_hash: &str, max_bytes: u64) -> Result<()> {
    read_or_verify_bounded_cas_object(path, expected_hash, max_bytes, false).map(|_| ())
}

fn read_or_verify_bounded_cas_object(
    path: &Path,
    expected_hash: &str,
    max_bytes: u64,
    materialize: bool,
) -> Result<Vec<u8>> {
    let listed = fs::symlink_metadata(path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    if !listed.file_type().is_file() || listed.len() > max_bytes {
        return Err(store_corrupt_error(
            path,
            format!("CAS object is not a regular file within the {max_bytes} byte limit"),
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if listed.nlink() != 1 {
            return Err(store_corrupt_error(
                path,
                "CAS object has an unexpected hard-link count",
            ));
        }
    }
    let mut file = fs::File::open(path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    let opened = file
        .metadata()
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    if !opened.is_file() || opened.len() != listed.len() || opened.len() > max_bytes {
        return Err(store_corrupt_error(
            path,
            "CAS object changed while it was opened",
        ));
    }
    let mut bytes = Vec::new();
    if materialize {
        let capacity = usize::try_from(opened.len()).map_err(|_| {
            store_corrupt_error(
                path,
                "CAS object size cannot be represented by this process",
            )
        })?;
        bytes.try_reserve_exact(capacity).map_err(|_| {
            store_corrupt_error(
                path,
                "CAS object cannot fit within the process memory limit",
            )
        })?;
    }
    let mut hasher = Sha256::new();
    let mut total = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        if count == 0 {
            break;
        }
        total = total.saturating_add(count as u64);
        if total > max_bytes {
            return Err(store_corrupt_error(
                path,
                format!("CAS object exceeds the {max_bytes} byte limit while being read"),
            ));
        }
        hasher.update(&buffer[..count]);
        if materialize {
            bytes.extend_from_slice(&buffer[..count]);
        }
    }
    let actual_hash = format!("sha256:{:x}", hasher.finalize());
    if actual_hash != expected_hash {
        return Err(store_corrupt_error(path, "CAS object hash mismatch"));
    }
    Ok(bytes)
}

/// The read-only open/view expansion cache path for a CAS object. R10-6: the
/// per-object directory is the FULL `sha256` hex (not a 12-char/48-bit prefix), so
/// two objects that share a 12-hex prefix and a basename can no longer collide onto
/// one cache file.
fn open_cache_path(basename: &str, hash: &str) -> PathBuf {
    cache_home()
        .join("kcs/open")
        .join(hash.trim_start_matches("sha256:"))
        .join(portable_cache_leaf(basename))
}

/// R10-6: crash-atomic write of the open/view expansion cache file. Writes bytes to
/// a uniquely-named temp in the SAME directory (created 0600 so the body never
/// exists world-readable, R9-3), fsyncs, drops the temp to 0400 (read-only), then
/// renames into the final path. A crash before the rename leaves only the temp,
/// never a torn file at the served name; the temp is removed on any failure. Mirrors
/// `atomic_write_cas_object`.
fn write_open_cache_atomic(cache: &Path, bytes: &[u8]) -> Result<()> {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let parent = cache
        .parent()
        .ok_or_else(|| KcsError::io("cache path has no parent", cache.display().to_string()))?;
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or_default();
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let temp = parent.join(format!(".tmp-{}-{}-{}", process::id(), nanos, seq));
    let result = (|| -> Result<()> {
        let mut open_options = OpenOptions::new();
        open_options.write(true).create(true).truncate(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            open_options.mode(0o600);
        }
        let mut file = open_options
            .open(&temp)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        file.write_all(bytes)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        file.sync_all()
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        drop(file);
        // Drop the temp to read-only BEFORE publishing so the served file is never
        // writable (mirrors the pre-fix final-path 0400 hardening).
        let mut permissions = fs::metadata(&temp)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?
            .permissions();
        permissions.set_readonly(true);
        fs::set_permissions(&temp, permissions)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        fs::rename(&temp, cache)
            .map_err(|err| KcsError::io(err.to_string(), cache.display().to_string()))
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

/// R9-3: restrict the open/view expansion cache subtree to owner-only (0700) on
/// unix, walking from `leaf` up to `$XDG_CACHE_HOME/kcs` inclusive. The cache
/// materializes raw / prepared / image CAS bytes, so it must carry the same
/// 0700/0600 hardening as the CAS itself (P2) rather than inherit the umask
/// default (0755). Best-effort (the cache is regenerable); the `starts_with`
/// guard keeps the walk from ever chmod-ing anything above the cache root
/// (e.g. `$XDG_CACHE_HOME` itself). No-op on non-unix.
fn harden_open_cache_subtree(leaf: &Path) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let root = cache_home().join("kcs");
        if !leaf.starts_with(&root) {
            return;
        }
        let mut current = leaf.to_path_buf();
        loop {
            let _ = fs::set_permissions(&current, fs::Permissions::from_mode(0o700));
            if current == root {
                break;
            }
            match current.parent() {
                Some(parent) => current = parent.to_path_buf(),
                None => break,
            }
        }
    }
    #[cfg(not(unix))]
    {
        let _ = leaf;
    }
}

const MAX_WORKING_TREE_SCAN_ENTRIES: usize = 100_000;

#[derive(Debug)]
struct WorkingTreeScanBudget {
    remaining_bytes: u64,
    remaining_entries: usize,
}

#[derive(Debug)]
struct WorkingTreeScanAttempt {
    max_bytes: u64,
    reserved_bytes: u64,
}

impl WorkingTreeScanBudget {
    fn new() -> Self {
        Self {
            remaining_bytes: DEFAULT_MAX_ARCHIVE_SCOPE_BYTES,
            remaining_entries: MAX_WORKING_TREE_SCAN_ENTRIES,
        }
    }

    fn consume_entry(&mut self) -> bool {
        if self.remaining_entries == 0 {
            return false;
        }
        self.remaining_entries -= 1;
        true
    }

    fn reserve_file(&mut self, declared_size: u64) -> Option<WorkingTreeScanAttempt> {
        if self.remaining_bytes == 0 {
            return None;
        }
        let max_bytes = declared_size
            .min(MAX_RAW_OBJECT_BYTES)
            .min(self.remaining_bytes.saturating_sub(1));
        let reserved_bytes = max_bytes.saturating_add(1).min(self.remaining_bytes);
        self.remaining_bytes -= reserved_bytes;
        Some(WorkingTreeScanAttempt {
            max_bytes,
            reserved_bytes,
        })
    }

    fn finish_success(&mut self, attempt: &WorkingTreeScanAttempt, actual_size: u64) {
        let unused = attempt.reserved_bytes.saturating_sub(actual_size);
        self.remaining_bytes = self.remaining_bytes.saturating_add(unused);
    }
}

fn find_working_tree_raw(root: &Path, raw_hash: &str) -> Result<Option<PathBuf>> {
    let mut budget = WorkingTreeScanBudget::new();
    for entry in fs::read_dir(root)
        .map_err(|err| KcsError::io(err.to_string(), root.display().to_string()))?
    {
        let entry =
            entry.map_err(|err| KcsError::io(err.to_string(), root.display().to_string()))?;
        if !budget.consume_entry() {
            break;
        }
        if entry.file_name() == ".kcs" {
            continue;
        }
        if !entry
            .file_type()
            .map(|kind| kind.is_file())
            .unwrap_or(false)
        {
            continue;
        }
        let declared_size = entry.metadata().map(|metadata| metadata.len()).unwrap_or(0);
        let Some(attempt) = budget.reserve_file(declared_size) else {
            break;
        };
        let path = entry.path();
        let Some(input_path) = entry.file_name().to_str().map(str::to_owned) else {
            continue;
        };
        let identity = match hash_verified_scan_input(root, &input_path, attempt.max_bytes) {
            Ok(identity) => identity,
            Err(_) => continue,
        };
        budget.finish_success(&attempt, identity.size_bytes);
        if identity.raw_hash == raw_hash {
            return Ok(Some(path));
        }
    }
    Ok(None)
}

/// Portable fan-out path for a content-hashed byte object. Logical identities retain
/// `sha256:<digest>`; only the physical leaf omits the Windows-invalid colon.
fn cas_object_path(kcs_dir: &Path, subdir: &str, hash: &str) -> Result<PathBuf> {
    fanout_path(kcs_dir.join("objects").join(subdir), hash)
}

#[cfg(not(windows))]
fn legacy_cas_object_path(kcs_dir: &Path, subdir: &str, hash: &str) -> Result<PathBuf> {
    let digest = hash_path_component(hash)?;
    Ok(kcs_dir
        .join("objects")
        .join(subdir)
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(hash))
}

fn path_entry_exists(path: &Path) -> Result<bool> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(KcsError::io(error.to_string(), path.display().to_string())),
    }
}

fn existing_cas_object_paths(kcs_dir: &Path, subdir: &str, hash: &str) -> Result<Vec<PathBuf>> {
    let canonical = cas_object_path(kcs_dir, subdir, hash)?;
    let mut paths = Vec::with_capacity(2);
    if path_entry_exists(&canonical)? {
        paths.push(canonical);
    }
    #[cfg(not(windows))]
    {
        let legacy = legacy_cas_object_path(kcs_dir, subdir, hash)?;
        if path_entry_exists(&legacy)? {
            paths.push(legacy);
        }
    }
    Ok(paths)
}

fn cas_object_present(kcs_dir: &Path, subdir: &str, hash: &str, max_bytes: u64) -> Result<bool> {
    let canonical = cas_object_path(kcs_dir, subdir, hash)?;
    let canonical_present = path_entry_exists(&canonical)?;

    #[cfg(not(windows))]
    {
        let legacy = legacy_cas_object_path(kcs_dir, subdir, hash)?;
        let legacy_present = path_entry_exists(&legacy)?;
        if canonical_present && legacy_present {
            verify_bounded_cas_object(&canonical, hash, max_bytes)?;
            verify_bounded_cas_object(&legacy, hash, max_bytes)?;
        } else if canonical_present {
            verify_bounded_cas_object(&canonical, hash, max_bytes)?;
        } else if legacy_present {
            verify_bounded_cas_object(&legacy, hash, max_bytes)?;
        }
        Ok(canonical_present || legacy_present)
    }

    #[cfg(windows)]
    {
        if canonical_present {
            verify_bounded_cas_object(&canonical, hash, max_bytes)?;
        }
        Ok(canonical_present)
    }
}

fn read_cas_byte_object(
    kcs_dir: &Path,
    subdir: &str,
    hash: &str,
    max_bytes: u64,
) -> Result<Option<(PathBuf, Vec<u8>)>> {
    let canonical = cas_object_path(kcs_dir, subdir, hash)?;
    if path_entry_exists(&canonical)? {
        let bytes = read_bounded_cas_object(&canonical, hash, max_bytes)?;
        #[cfg(not(windows))]
        {
            let legacy = legacy_cas_object_path(kcs_dir, subdir, hash)?;
            if path_entry_exists(&legacy)? {
                verify_bounded_cas_object(&legacy, hash, max_bytes)?;
            }
        }
        return Ok(Some((canonical, bytes)));
    }

    #[cfg(not(windows))]
    {
        let legacy = legacy_cas_object_path(kcs_dir, subdir, hash)?;
        if path_entry_exists(&legacy)? {
            let bytes = read_bounded_cas_object(&legacy, hash, max_bytes)?;
            return Ok(Some((legacy, bytes)));
        }
    }
    Ok(None)
}

fn tombstone_path(kcs_dir: &Path, raw_hash: &str) -> Result<PathBuf> {
    fanout_path(kcs_dir.join("tombstones"), raw_hash)
}

#[cfg(not(windows))]
fn legacy_tombstone_path(kcs_dir: &Path, raw_hash: &str) -> Result<PathBuf> {
    let digest = hash_path_component(raw_hash)?;
    Ok(kcs_dir
        .join("tombstones")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(raw_hash))
}

fn read_optional_file(path: &Path) -> Result<Option<Vec<u8>>> {
    const MAX_TOMBSTONE_BYTES: u64 = 64 * 1024;
    match fs::symlink_metadata(path) {
        Ok(_) => read_bounded_regular_file(path, MAX_TOMBSTONE_BYTES).map(Some),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(KcsError::io(error.to_string(), path.display().to_string())),
    }
}

fn parse_tombstone(
    bytes: &[u8],
    path: &Path,
    raw_hash: &str,
    require_identity: bool,
) -> Result<Value> {
    let mut value: Value =
        serde_json::from_slice(bytes).map_err(|err| KcsError::schema(err.to_string()))?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| KcsError::schema("tombstone must be a JSON object"))?;
    match object.get("raw_hash") {
        Some(Value::String(stored)) if stored == raw_hash => {}
        Some(_) => {
            return Err(store_corrupt_error(
                path,
                "tombstone identity does not match its storage key",
            ))
        }
        None if require_identity => {
            return Err(store_corrupt_error(
                path,
                "legacy tombstone is missing its raw_hash identity",
            ))
        }
        None => {
            object.insert("raw_hash".to_owned(), json!(raw_hash));
        }
    }
    Ok(value)
}

/// `.kcs/tombstones/ab/cd/<raw-digest>` (05 §3.5). `Ok(None)` when no tombstone
/// exists. The returned value is the on-disk tombstone JSON augmented with the
/// resolved `scope_path` (08 §4.1 response shape).
fn read_tombstone(target: &ScopeTarget, raw_hash: &str) -> Result<Option<Value>> {
    let canonical = tombstone_path(&target.kcs_dir, raw_hash)?;
    let canonical_value = read_optional_file(&canonical)?
        .map(|bytes| parse_tombstone(&bytes, &canonical, raw_hash, false))
        .transpose()?;

    #[cfg(not(windows))]
    let legacy_value = {
        let legacy = legacy_tombstone_path(&target.kcs_dir, raw_hash)?;
        read_optional_file(&legacy)?
            .map(|bytes| parse_tombstone(&bytes, &legacy, raw_hash, true))
            .transpose()?
    };

    #[cfg(not(windows))]
    if let (Some(portable), Some(legacy)) = (&canonical_value, &legacy_value) {
        if portable != legacy {
            return Err(store_corrupt_error(
                &canonical,
                "portable and legacy tombstones disagree",
            ));
        }
    }

    #[cfg(not(windows))]
    let mut value = canonical_value.or(legacy_value);
    #[cfg(windows)]
    let mut value = canonical_value;
    let Some(value) = value.as_mut() else {
        return Ok(None);
    };
    value.as_object_mut().expect("validated above").insert(
        "scope_path".to_owned(),
        json!(target.kcs_dir.display().to_string()),
    );
    Ok(Some(value.take()))
}

/// Enforce the purge visibility boundary on every raw-derived read surface.
/// Erase receipts are deliberately absent here: they are fsck-only and must not
/// prevent a later verified re-ingest of identical bytes.
fn enforce_purge_read_barrier(target: &ScopeTarget, raw_hash: &str) -> Result<()> {
    if let Some(tombstone) = read_tombstone(target, raw_hash)? {
        return Err(tombstone_error(tombstone));
    }
    if PurgeState::new(&target.kcs_dir).barrier_blocks(raw_hash)? {
        return Err(purge_not_found_error(target, raw_hash));
    }
    Ok(())
}

/// 08 §4.1 tombstone response as an exit-4 error (open/view surface it as a
/// dead pointer). `context` carries the full `status="purged"` tombstone body.
fn tombstone_error(mut tombstone: Value) -> KcsError {
    if let Some(object) = tombstone.as_object_mut() {
        object.insert("status".to_owned(), json!("purged"));
    }
    KcsError::new(
        "KCS-E-PURGE-TOMBSTONED-001",
        "evidence target was purged (tombstone recorded)",
        tombstone,
        ExitCode::PermanentFailure,
    )
}

/// 08 §4.2 — raw object absent with no tombstone record.
fn purge_not_found_error(target: &ScopeTarget, raw_hash: &str) -> KcsError {
    KcsError::new(
        "KCS-E-PURGE-NOT-FOUND-001",
        "evidence target was purged without tombstone record",
        json!({
            "raw_hash": raw_hash,
            "scope_path": target.kcs_dir.display().to_string(),
        }),
        ExitCode::PermanentFailure,
    )
}

/// M6 — the Evidence Pointer's (raw_hash, tool_profile_hash, chunk_hash) do not
/// mutually bind: the chunk row or tree entry it resolves to carries a different
/// identity than the pointer claims. This is a tampered / internally inconsistent
/// pointer; refuse it rather than serve mismatched evidence. Exit 4 (a dead
/// pointer that will never resolve consistently, like the purge family).
fn invalid_pointer_identity_error(pointer: &EvidencePointer) -> KcsError {
    KcsError::new(
        "KCS-E-EVIDENCE-POINTER-INVALID-001",
        "evidence pointer identity mismatch: raw_hash / tool_profile_hash / chunk_hash do not bind to the same chunk",
        json!({
            "raw_hash": pointer.raw_hash,
            "tool_profile_hash": pointer.tool_profile_hash,
            "chunk_hash": pointer.chunk_hash,
        }),
        ExitCode::PermanentFailure,
    )
}

/// R17-1: the pointer's `commit` object cannot be resolved (missing / never existed
/// — e.g. a forged `commit` hash on a `view`/`open` operand). Distinct from a genuine
/// shallow commit (commit present, tree GC'd), whose resolution docs/05 §3.6
/// guarantees never fails; that guarantee is limited to commit *existence* (docs/08
/// §3.2:150) and does not extend to a missing commit. A pointer whose commit does not
/// exist cannot bind the raw_hash to a snapshot tree or the chunk to a normalization
/// generation (N5), so it is rejected as an invalid pointer rather than served
/// best-effort. Same code / exit as `invalid_pointer_identity_error`
/// (EVIDENCE-POINTER-INVALID, exit 4): both mean "this pointer does not name a
/// resolvable, self-consistent piece of evidence".
fn unresolvable_commit_pointer_error(pointer: &EvidencePointer) -> KcsError {
    KcsError::new(
        "KCS-E-EVIDENCE-POINTER-INVALID-001",
        "evidence pointer references a commit object that does not exist (missing or forged); \
         a resolvable commit is required to bind the raw_hash to its snapshot tree and the chunk \
         to its normalization generation",
        json!({
            "commit": pointer.commit,
            "raw_hash": pointer.raw_hash,
            "chunk_hash": pointer.chunk_hash,
        }),
        ExitCode::PermanentFailure,
    )
}

/// 08 §3.2 — scope `.kcs` unreachable (scope_path unreachable and scope_id not
/// registered).
fn scope_unreachable_error(scope_id: &str) -> KcsError {
    KcsError::new(
        "KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001",
        "evidence scope unreachable",
        json!({ "scope_id": scope_id }),
        ExitCode::PermanentFailure,
    )
}

/// 08 §3.1 step 1b — the scope_id maps to multiple registered scopes that share
/// the newest `last_seen_at`, so the winner is ambiguous.
fn scope_ambiguous_error(scope_id: &str, candidates: &[PathBuf]) -> KcsError {
    KcsError::new(
        "KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001",
        "evidence scope_id maps to multiple registered scopes",
        json!({
            "scope_id": scope_id,
            "candidates": candidates
                .iter()
                .map(|path| path.display().to_string())
                .collect::<Vec<_>>(),
        }),
        ExitCode::PermanentFailure,
    )
}

fn is_store_not_found(error: &KcsError) -> bool {
    error.error_code() == "KCS-E-STORE-NOT-FOUND-001"
}

/// R16-2: the store-corruption error classes that a single scope may raise mid-search
/// and that must NOT abort a multi-scope search (05 §1.8 per-scope isolation). A
/// missing object (STORE-NOT-FOUND), a corrupt object (STORE-CORRUPT, e.g. a CAS
/// hash mismatch), a store I/O failure (STORE-IO), and a shallow commit
/// (COMMIT-SHALLOW) are all localized to one scope's store; the search loop
/// downgrades them to `Excluded("store_corrupt")` so healthy scopes still return.
/// Deliberately narrow: it does not catch schema / programming errors, which stay
/// fail-fast.
fn is_store_corrupt_class(error: &KcsError) -> bool {
    matches!(
        error.error_code(),
        "KCS-E-STORE-NOT-FOUND-001"
            | "KCS-E-STORE-CORRUPT-001"
            | "KCS-E-STORE-IO-001"
            | "KCS-E-COMMIT-SHALLOW-001"
    )
}

struct ObjectUri {
    scope_id: String,
    object_type: String,
    hash: String,
}

/// Parses a `kcs://<scope_id>/object/<type>/<hash>` object-reference URI
/// (08 §2.3). Returns `Ok(None)` for non-object URIs (Evidence Pointer URIs,
/// whose second segment is always a `sha256:` commit, never the literal
/// `object`). A syntactically-`object` URI that is malformed is `Err` (exit 2).
fn parse_object_uri(input: &str) -> Result<Option<ObjectUri>> {
    let Some(rest) = input.strip_prefix("kcs://") else {
        return Ok(None);
    };
    let (path, _query) = rest.split_once('?').unwrap_or((rest, ""));
    let parts = path.split('/').collect::<Vec<_>>();
    if parts.get(1) != Some(&"object") {
        return Ok(None);
    }
    if parts.len() != 4 {
        return Err(KcsError::invalid_usage(
            "object URI must be kcs://<scope_id>/object/<type>/<hash>",
        ));
    }
    let (scope_id, object_type, hash) = (parts[0], parts[2], parts[3]);
    if scope_id.is_empty() {
        return Err(KcsError::invalid_usage("object URI is missing scope_id"));
    }
    const VALID_TYPES: [&str; 5] = ["raw", "image", "chunk", "normalized", "prepared"];
    if !VALID_TYPES.contains(&object_type) {
        return Err(KcsError::invalid_usage(format!(
            "unknown object type in URI: {object_type}"
        )));
    }
    if !is_hash(hash) {
        return Err(KcsError::invalid_usage(
            "object URI hash must be sha256 lowercase hex",
        ));
    }
    Ok(Some(ObjectUri {
        scope_id: scope_id.to_owned(),
        object_type: object_type.to_owned(),
        hash: hash.to_owned(),
    }))
}

/// Resolves an `object` reference URI (08 §2.3) for `kcs open` / `kcs view`.
/// This is a distinct path from Evidence Pointer resolution.
fn resolve_object_uri(object: &ObjectUri, as_view: bool) -> Result<Value> {
    let status = if as_view { "viewed" } else { "opened" };
    let target = resolve_scope_target(&object.scope_id, None)?;
    if object.object_type == "chunk" {
        let chunk = read_stored_chunks(&target.kcs_dir)?
            .into_iter()
            .find(|chunk| chunk.row.chunk_id == object.hash)
            .ok_or_else(|| KcsError::not_found(object.hash.clone()))?;
        enforce_purge_read_barrier(&target, &chunk.row.raw_hash)?;
        let text = chunk.row.text;
        enforce_purge_read_barrier(&target, &chunk.row.raw_hash)?;
        return Ok(json!({
            "status": status,
            "object_type": "chunk",
            "hash": object.hash,
            "text": text,
        }));
    }
    // M7: dispatch each object_type to its correct CAS directory (03 §2 / 07 §5.2)
    // instead of routing every byte object through objects/raw:
    //   raw      -> objects/raw       (working-tree-first, rename tolerant)
    //   image    -> objects/images    (embedded document images, 07 §5.2)
    //   prepared -> objects/prepared  (pre-Markdownize intermediate)
    // `normalized` is the full-text view, path-named by
    // `<raw_hash>.<tool_profile_hash>.g<gen>` (03 §2.1) and not addressable by a
    // single content hash, so it is not resolvable through an object URI.
    let (subdir, scan_working_tree) = match object.object_type.as_str() {
        "raw" => ("raw", true),
        "image" => ("images", false),
        "prepared" => ("prepared", false),
        other => {
            return Err(KcsError::invalid_usage(format!(
                "object type '{other}' is not resolvable by a single-hash object URI"
            )));
        }
    };
    if object.object_type == "raw" {
        enforce_purge_read_barrier(&target, &object.hash)?;
    } else if PurgeState::new(&target.kcs_dir)
        .read_journal()?
        .is_some_and(|journal| journal.phase.is_barrier_visible())
    {
        // Image/prepared object URIs carry only the derived-object hash, so no
        // trustworthy raw association can be recovered at this boundary. During
        // the short destructive window, fail the whole derived-object surface
        // closed; normal reads resume after terminal publication/deletion.
        return Err(KcsError::new(
            "KCS-E-PURGE-NOT-FOUND-001",
            "derived object access is hidden by an in-progress purge barrier",
            json!({
                "object_type": object.object_type,
                "hash": object.hash,
                "scope_path": target.kcs_dir.display().to_string(),
                "purge_state": "in_progress",
            }),
            ExitCode::PermanentFailure,
        ));
    }
    match open_cas_byte_object(&target, subdir, scan_working_tree, &object.hash, None)? {
        Some((path, temporary)) => {
            let blocked_after_open = if object.object_type == "raw" {
                enforce_purge_read_barrier(&target, &object.hash).err()
            } else if PurgeState::new(&target.kcs_dir)
                .read_journal()?
                .is_some_and(|journal| journal.phase.is_barrier_visible())
            {
                Some(KcsError::new(
                    "KCS-E-PURGE-NOT-FOUND-001",
                    "derived object access is hidden by an in-progress purge barrier",
                    json!({
                        "object_type": object.object_type,
                        "hash": object.hash,
                        "scope_path": target.kcs_dir.display().to_string(),
                        "purge_state": "in_progress",
                    }),
                    ExitCode::PermanentFailure,
                ))
            } else {
                None
            };
            if let Some(error) = blocked_after_open {
                if temporary {
                    let _ = fs::remove_file(&path);
                }
                return Err(error);
            }
            Ok(json!({
                "status": status,
                "object_type": object.object_type,
                "hash": object.hash,
                "path": path,
                "temporary": temporary,
            }))
        }
        None if object.object_type == "raw" => Err(purge_not_found_error(&target, &object.hash)),
        None => Err(KcsError::not_found(object.hash.clone())),
    }
}

fn copy_normalized_instance_gen(
    kcs_dir: &Path,
    raw_hash: &str,
    tool_profile_hash: &str,
    old_gen: u64,
    new_gen: u64,
) -> Result<()> {
    let old_dir = kcs_pipeline::markdownize::normalized_instance_dir(
        kcs_dir,
        raw_hash,
        tool_profile_hash,
        old_gen,
    );
    if let Ok(entries) = fs::read_dir(&old_dir) {
        for entry in entries.flatten() {
            let name = entry.file_name();
            if name.to_str().is_some_and(is_orphan_temp_name)
                && entry
                    .file_type()
                    .map(|file_type| file_type.is_file())
                    .unwrap_or(false)
            {
                let _ = fs::remove_file(entry.path());
            }
        }
    }
    let mut instance =
        load_validated_normalized_instance(kcs_dir, raw_hash, tool_profile_hash, old_gen)
            .map_err(pipeline_to_kcs)?;
    let generated_at = now_utc_seconds();
    instance.manifest.parent_gen = Some(old_gen);
    instance.manifest.gen = new_gen;
    instance.manifest.run_id = format!("run_{}", new_ulid(kcs_dir));
    instance.manifest.generated_at = generated_at.clone();
    for unit in &mut instance.units {
        unit.gen = new_gen;
        unit.generated_at.clone_from(&generated_at);
    }
    persist_normalized_instance(kcs_dir, &instance.manifest, &instance.units)
        .map_err(pipeline_to_kcs)
}

/// Whether `name` matches the normalized-unit file naming convention written by
/// `persist_normalized_instance`: a 16-hex-char `unit_ref` digest plus `.json`
/// (e.g. `1a2b3c4d5e6f7089.json`). Anything else in a gen dir is not store truth
/// (R9-5) — `manifest.json`, a crashed writer's `.tmp-*`, a `.DS_Store`.
#[cfg(test)]
fn is_normalized_unit_file(name: &str) -> bool {
    let Some(stem) = name.strip_suffix(".json") else {
        return false;
    };
    stem.len() == 16
        && stem
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

/// Whether `name` looks like one of KCS's own atomic-write temp files
/// (`.tmp-<pid>-...` or `.<name>.tmp-<pid>-...`). Used by R9-5 to GC a
/// crash-orphaned temp left inside a gen dir by a killed writer.
fn is_orphan_temp_name(name: &str) -> bool {
    name.starts_with('.') && name.contains(".tmp-")
}

fn index_to_kcs(error: kcs_index::IndexError) -> KcsError {
    KcsError::schema(error.to_string())
}

fn search_to_kcs(error: kcs_search::SearchError) -> KcsError {
    match error {
        kcs_search::SearchError::Cursor(message) => KcsError::new(
            "KCS-E-SEARCH-CURSOR-001",
            message,
            json!({}),
            ExitCode::InvalidUsage,
        ),
        kcs_search::SearchError::Evidence(message) => KcsError::schema(message),
        kcs_search::SearchError::Contract(message) => KcsError::schema(message),
        kcs_search::SearchError::NotImplemented(feature) => KcsError::not_implemented(feature),
    }
}

fn run_batch(args: BatchArgs) -> Result<Value> {
    let repo = Repository::open_current()?;
    // O3: `batch resume` / `batch retry` read-modify-write `tasks.jsonl` and drive
    // online sends, so hold the folder store lock end-to-end — the same guard M1
    // wired onto index/repair/reindex. Without it two concurrent `batch resume`
    // runs interleave the ledger and double-send held tasks. Reentrant with any
    // inner auto-snapshot; losers fail fast with KCS-E-STORE-LOCKED-001 (exit 3).
    let _lock = repo.lock_store()?;
    // Persisted recovery work is executable authority. Revalidate the repository's
    // current tool lock after acquiring the store lock and before reading or
    // mutating tasks, so resume/retry cannot bypass the same adapter policy used by
    // index and repair paths.
    require_repo_tool_lock(&repo)?;
    let store = TaskStore::new(repo.kcs_dir());
    // N1: a Tier B online hold is only lifted by an explicit `--send-secrets`
    // approval, never by a plain `batch resume`. Without this, resume's
    // Paused -> Pending flip would silently un-hold the candidate-secret task.
    let secrets_approved = secrets_send_approved(&repo);
    match args.command {
        Some(BatchCommand::Resume(resume)) => {
            let changed = store
                .update_matching(|task| {
                    let held_secret = task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD);
                    if task.status == TaskStatus::Paused
                        && (resume.override_budget
                            || task.fallback_reason.as_deref() != Some("budget_exceeded"))
                        && (!held_secret || secrets_approved)
                    {
                        task.status = TaskStatus::Pending;
                        task.fallback_reason = None;
                        true
                    } else {
                        false
                    }
                })
                .map_err(pipeline_to_kcs)?;
            let outcome = execute_pending_tasks(&repo, &store, resume.override_budget, true)?;
            let mut output = json!({
                "status": "resumed",
                "override_budget": resume.override_budget,
                "tasks_updated": changed,
                "tasks_executed": outcome.executed,
                // R9-7: surface driven online-send attempts and failures, not just
                // successes, so an orchestrator sees rate-limit / auth / charge
                // consumption even when nothing completed.
                "tasks_attempted": outcome.attempted(),
                "tasks_failed": outcome.failed,
                // R11-2: pauses this pass are a real state change (previously invisible
                // — `tasks_updated` reported 0 while the store flipped to paused).
                "tasks_paused": outcome.paused,
            });
            // R11-2: report the batch exit code (docs/04 §5.6) from what this pass did
            // — auth (5) / budget-paused (6) / partial (3) / all-permanent (4) — while
            // the full result JSON still prints to stdout. R14-5: with a batch-owned
            // error_code so errors.jsonl does not borrow a search code.
            apply_batch_exit_override(&mut output, &outcome);
            Ok(output)
        }
        Some(BatchCommand::Retry) => {
            // R9-4: `batch retry` also recovers Partial online markdownize tasks
            // (docs/04 §5.2 `partial -> done`). A Partial task has some Done and
            // some Failed units; re-drive it (Pending) with `unit_keys` scoped to
            // the still-Failed units and the placeholder output_ref restored so
            // execute_pending_markdownize_tasks selects it. On full success it
            // becomes Done, ending the silent data gap index_status showed as
            // fully enriched.
            let partial_reenqueued = reenqueue_partial_markdownize_tasks(&store)?;
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
            // `batch retry` never overrides the budget cap (retry re-schedules,
            // it does not bypass caps — `batch resume --override-budget` does), and never
            // revives an auth_error task (CT2-TASK-005: `max_attempts=0` is this command's
            // contract; `batch resume` is where repaired credentials take effect).
            let outcome = execute_pending_tasks(&repo, &store, false, false)?;
            let mut output = json!({
                "status": "retry scheduled",
                "tasks_updated": changed + partial_reenqueued,
                "tasks_executed": outcome.executed,
                // R9-7: surface driven online-send attempts and failures.
                "tasks_attempted": outcome.attempted(),
                "tasks_failed": outcome.failed,
                // R11-2: pause transitions this pass (docs/04 §5.6 visibility).
                "tasks_paused": outcome.paused,
            });
            // R14-5: batch-owned error_code on the Partial(3)/Permanent(4) override.
            apply_batch_exit_override(&mut output, &outcome);
            Ok(output)
        }
        None => Err(KcsError::not_implemented("batch command")),
    }
}

/// Q3: reclaim orphaned `Running` tasks back to `Pending`. A task is flipped to
/// `Running` only by `execute_pending_markdownize_tasks`, immediately before an
/// online send, and back to Done/Partial/Failed once it returns. KCS is
/// single-user and every executor (`batch resume` / `batch retry` / index
/// enrichment) holds the folder store lock end-to-end, so any `Running` task
/// observed while holding that lock is necessarily an orphan from a process that
/// died mid-send (`Running` had no outbound transition, an absorbing state).
/// Reclaim it to `Pending` — clearing the stale `heartbeat_at` — so it is retried
/// instead of being stuck forever and dragging `enriched_ratio` below 1.0.
fn reclaim_orphaned_running_tasks(store: &TaskStore) -> Result<usize> {
    store
        .update_matching(|task| {
            if task.status == TaskStatus::Running {
                task.status = TaskStatus::Pending;
                task.heartbeat_at = None;
                true
            } else {
                false
            }
        })
        .map_err(pipeline_to_kcs)
}

/// R9-4 / R10-4: convert Partial online-markdownize tasks back into retryable
/// Pending tasks so `batch retry` can complete their still-Failed units (docs/04
/// §5.2 `partial -> done`) — but ONLY the RETRYABLE ones, and only within the retry
/// budget. Reads each Partial task's manifest for its Failed units and their real
/// `error_kind` (R10-4). A unit whose kind is non-retryable (docs/04 §5.2 permanent:
/// invalid_input / contract_violation / ...) is never re-sent; a task whose Failed
/// units are ALL non-retryable, or whose `attempts` have reached the governing
/// `max_attempts`, is left Partial (static, still counted by `kcs status`). Each
/// re-enqueue increments `attempts` so an orchestrator can see the retry count and
/// the loop stops instead of re-sending & re-billing a permanently-failing unit
/// forever. Only touches task lifecycle — no HEAD/search promotion (F6, Step 4).
fn reenqueue_partial_markdownize_tasks(store: &TaskStore) -> Result<usize> {
    let online_ref = online_output_ref(&online_markdownize_profile().adapter_id);
    // Collect each Partial task's retry plan first — this needs manifest I/O, so it
    // is done outside the `update_matching` closure.
    let mut plan_by_id: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for task in store.all().map_err(pipeline_to_kcs)? {
        if task.status != TaskStatus::Partial
            || task.task_type != TaskType::Markdownize
            || !targets_standard_online_markdownize(store.kcs_dir(), &task, &online_ref)
        {
            continue;
        }
        let plan = partial_retry_plan_from_instance(store, &task)?;
        // Gate 1 (R10-4): no retryable Failed unit -> leave the task Partial.
        if plan.retryable_units.is_empty() {
            continue;
        }
        // Gate 2 (R10-4): the retry budget for the governing kind is spent -> leave
        // the task Partial (static). `None` means at least one retryable unit has an
        // unlimited budget, so the cap never trips.
        if plan.max_attempts.is_some_and(|max| task.attempts >= max) {
            continue;
        }
        plan_by_id.insert(task.task_id.clone(), plan.retryable_units);
    }
    if plan_by_id.is_empty() {
        return Ok(0);
    }
    store
        .update_matching(|task| {
            let Some(retryable) = plan_by_id.get(&task.task_id) else {
                return false;
            };
            task.status = TaskStatus::Pending;
            task.unit_keys = Some(retryable.clone());
            // Preserve the typed normalized-instance reference. The retry precondition
            // needs its complete manifest to recover every provider-discovered unit;
            // replacing this with the online placeholder made OCR-from-scratch partial
            // tasks impossible to resume.
            task.fallback_reason = None;
            task.next_retry_at = None;
            // R10-4/R19-5: the re-drive is charged against the retry budget in the
            // executor's result handling (a single accounting point) — on `Err` (full
            // send failure) OR `Ok(Partial)` (units still missing). Pre-incrementing here
            // double-counted with the `Err` path, exhausting `max_attempts` twice as fast.
            true
        })
        .map_err(pipeline_to_kcs)
}

/// The retryable subset of a Partial normalized instance's Failed units plus the
/// governing retry budget (R10-4). Used by `reenqueue_partial_markdownize_tasks`.
struct PartialRetryPlan {
    /// Failed unit_keys whose recorded `error_kind` is retryable (docs/04 §5.2).
    retryable_units: Vec<String>,
    /// The smallest finite `max_attempts` among those units' kinds, or `None` when at
    /// least one kind has an unlimited retry budget.
    max_attempts: Option<u32>,
}

/// Read a normalized instance's manifest (`output_ref/manifest.json`) and build its
/// [`PartialRetryPlan`]: the still-Failed units filtered to the retryable ones (by
/// their recorded `error_kind`) and the retry-budget cap. A missing manifest or a
/// fully-Done instance yields an empty plan.
fn partial_retry_plan_from_instance(
    task_store: &TaskStore,
    task: &TaskDescriptor,
) -> Result<PartialRetryPlan> {
    let empty = PartialRetryPlan {
        retryable_units: Vec::new(),
        max_attempts: Some(0),
    };
    let identity = validate_task_output_ref(task_store.kcs_dir(), task).map_err(pipeline_to_kcs)?;
    let TaskOutputRef::NormalizedInstance {
        raw_hash,
        tool_profile_hash,
        gen,
        ..
    } = identity
    else {
        return Ok(empty);
    };
    let manifest = load_validated_normalized_instance(
        task_store.kcs_dir(),
        &raw_hash,
        &tool_profile_hash,
        gen,
    )
    .map_err(pipeline_to_kcs)?
    .manifest;
    Ok(partial_retry_plan_from_manifest(&manifest))
}

fn partial_retry_plan_from_manifest(manifest: &NormalizedInstanceManifest) -> PartialRetryPlan {
    let mut retryable_units = Vec::new();
    let mut finite_max: Option<u32> = None;
    let mut saw_unlimited = false;
    for entry in &manifest.units {
        if entry.status == UnitStatus::Done {
            continue;
        }
        let policy = retry_policy(retry_kind_from_reason(entry.error_kind.as_deref()));
        if !policy.retryable {
            continue;
        }
        retryable_units.push(entry.unit_key.clone());
        match policy.max_attempts {
            None => saw_unlimited = true,
            Some(max) => finite_max = Some(finite_max.map_or(max, |current| current.min(max))),
        }
    }
    let max_attempts = if retryable_units.is_empty() {
        Some(0)
    } else if saw_unlimited {
        None
    } else {
        finite_max
    };
    PartialRetryPlan {
        retryable_units,
        max_attempts,
    }
}

/// R9-7: outcome counts from an enrichment pass. `batch retry`/`resume` need more
/// than the success count to be honest: a driven task can fail (an online send was
/// attempted, rate-limit / auth consumed) yet the old JSON reported only
/// `tasks_executed`, so an orchestrator could not see the attempt. `executed`
/// keeps its meaning (tasks completed OK == `tasks_executed`); `failed` is tasks
/// that transitioned to Failed this pass; `attempted()` = executed + failed
/// (budget-paused / held tasks that issued no adapter call are excluded).
#[derive(Debug, Default, Clone, Copy)]
struct ExecOutcome {
    executed: usize,
    failed: usize,
    /// R11-2: tasks whose online send this pass was halted by the budget cap
    /// (transitioned to Paused/budget_exceeded). Excluded from `attempted()` — no
    /// adapter call was issued. Drives docs/04 §5.6 exit 6.
    paused: usize,
    /// R11-2: subset of `failed` whose error was auth/authorization (docs/04 §5.6
    /// exit 5 — needs user re-auth, distinct from a retryable transient).
    auth_failed: usize,
    /// R11-2: subset of `failed` that is retry-eligible (retryable kind + attempts
    /// left). `failed - failed_retryable` is the permanently-failed remainder; the
    /// split drives the batch exit-code choice 3 (some retryable) vs 4 (all permanent).
    failed_retryable: usize,
}

impl ExecOutcome {
    fn attempted(self) -> usize {
        self.executed + self.failed
    }

    fn add(&mut self, other: ExecOutcome) {
        self.executed += other.executed;
        self.failed += other.failed;
        self.paused += other.paused;
        self.auth_failed += other.auth_failed;
        self.failed_retryable += other.failed_retryable;
    }
}

/// R11-2: the batch exit code (docs/04 §5.6 / docs/06 §7) a `batch resume`/`retry`
/// pass reports, computed from the tasks it TOUCHED this pass (its `ExecOutcome`,
/// not the whole store — a pass that leaves a pre-existing paused/failed task
/// untouched changed nothing and exits 0, preserving the L2 sticky-pause symmetry).
/// Priority, highest first: auth (5, user re-auth), then budget-paused (6, needs
/// `--override-budget`), then some-retryable-failed (3, `batch retry` can recover),
/// then all-permanent-failed (4). A clean pass returns `None` = exit 0.
fn batch_exit_override(outcome: &ExecOutcome) -> Option<ExitCode> {
    if outcome.auth_failed > 0 {
        Some(ExitCode::AuthError)
    } else if outcome.paused > 0 {
        Some(ExitCode::BudgetExceeded)
    } else if outcome.failed_retryable > 0 {
        Some(ExitCode::PartialFailure)
    } else if outcome.failed > 0 {
        Some(ExitCode::PermanentFailure)
    } else {
        None
    }
}

/// R14-5: the batch-owned observability `error_code` for a Partial(3)/Permanent(4) batch
/// exit, mirroring how `index` self-sets `KCS-E-INDEX-PARTIAL-001` on its partial exit.
/// Without it, `append_exit_override_error` fell back to `exit_override_error_code`, which
/// labels 3/4 with SEARCH codes (`KCS-E-SEARCH-PARTIAL-001` — not even in the catalog —
/// and `KCS-E-SEARCH-SCOPE-ALL-FAILED-001`, the multi-scope-search all-failed code), so a
/// batch task failure was mis-classified as a search failure in errors.jsonl. Auth(5) /
/// budget(6) keep their shared codes (`KCS-E-ADAPTER-AUTH-001` / `KCS-E-BUDGET-EXCEEDED-001`),
/// which are correct for batch too, so they return `None` and use the shared fallback.
fn batch_error_code(code: ExitCode) -> Option<&'static str> {
    match code {
        ExitCode::PartialFailure => Some("KCS-E-BATCH-PARTIAL-001"),
        ExitCode::PermanentFailure => Some("KCS-E-BATCH-TASK-FAILED-001"),
        _ => None,
    }
}

/// R14-5: apply the batch exit override to `output`, carrying a batch-owned `error_code`
/// (so errors.jsonl classifies the failure as batch, not search) before embedding the
/// `__exit_code` marker. Shared by `batch resume` and `batch retry`.
fn apply_batch_exit_override(output: &mut Value, outcome: &ExecOutcome) {
    if let Some(code) = batch_exit_override(outcome) {
        if let Some(error_code) = batch_error_code(code) {
            output["error_code"] = json!(error_code);
        }
        set_exit_override(output, code);
    }
}

/// R11-2: the exit code `index`/`repair`/`reindex` reports for its inline enrichment
/// (embedding) outcome. Unlike `batch`, a retryable/permanent embedding failure does
/// NOT override the exit — docs/05 says enrichment failure never aborts the local
/// index; it is disclosed in the result JSON and left for `batch resume` (exit 0).
/// Only the two states that need user intervention override the exit while the full
/// result JSON still prints to stdout (the search-exit-3 "result + nonzero" pattern):
/// auth (5) and budget-pause (6).
fn enrichment_exit_override(outcome: &ExecOutcome) -> Option<ExitCode> {
    if outcome.auth_failed > 0 {
        Some(ExitCode::AuthError)
    } else if outcome.paused > 0 {
        Some(ExitCode::BudgetExceeded)
    } else {
        None
    }
}

/// Embed the private `__exit_code` marker (stripped by `take_exit_override` before
/// printing) so a command prints its full result JSON to stdout yet exits non-zero
/// (05 §1.8 search pattern, extended by R11-2/R11-3 to index/repair/reindex/batch).
fn set_exit_override(output: &mut Value, code: ExitCode) {
    if let Some(object) = output.as_object_mut() {
        object.insert("__exit_code".to_owned(), json!(code.code()));
    }
}

fn execute_pending_tasks(
    repo: &Repository,
    store: &TaskStore,
    override_budget: bool,
    // R22-6(a): `batch resume` means "carry on with the work", so it may revive a task the
    // operator has since unblocked by fixing credentials. `batch retry` may NOT — CT2-TASK-005
    // (docs/04 §5.6, `auth_error: max_attempts=0`) makes non-retryability of an auth failure a
    // contract of that command specifically.
    allow_auth_revive: bool,
) -> Result<ExecOutcome> {
    let mut outcome = ExecOutcome::default();
    // Q3: under the folder store lock, any Running task is an orphan from a crashed
    // run — reclaim it to Pending so this pass re-executes it.
    reclaim_orphaned_running_tasks(store)?;
    if recover_pending_online_promotion(repo)? {
        finish_pending_online_promotion(repo)?;
    }
    // Markdownize and embedding opt-ins are per-adapter (07 §3, L4): gate each
    // adapter on its own approval rather than one blanket check.
    if persistent_network_allowed(repo)? {
        outcome.add(execute_pending_markdownize_tasks(
            repo,
            store,
            override_budget,
            allow_auth_revive,
        )?);
    }
    // Online Markdownize changes durable search truth only after the complete
    // output is rebound into one auto commit and SQLite is rebuilt. Do this before
    // embedding enrichment so the same batch pass can see/promote the new chunks.
    if promote_completed_online_markdownize(repo)? {
        finish_pending_online_promotion(repo)?;
    }
    // Embedding tasks are executed by the same enrichment pass `kcs index` uses;
    // without this, rate-limited Pending embedding tasks could never be completed
    // by `batch resume` / `batch retry`. `override_budget` reaches the budget
    // judgement (L2) and the embedding opt-in is the embedding adapter's own (L4).
    let embedding_online = embedding_online_allowed(repo, false, false, false)?;
    outcome.add(run_embedding_enrichment(
        repo,
        embedding_online,
        override_budget,
        allow_auth_revive,
    )?);
    Ok(outcome)
}

/// Execute Pending online markdownize tasks, honoring `override_budget` (L2 i).
/// R9-7: returns success + failure counts so `batch` JSON can report driven
/// attempts, not only successes.
fn execute_pending_markdownize_tasks(
    repo: &Repository,
    store: &TaskStore,
    override_budget: bool,
    allow_auth_revive: bool,
) -> Result<ExecOutcome> {
    let budget_caps =
        read_budget_policy(user_config_toml_path(), repo.kcs_dir().join("config.toml"))
            .map_err(pipeline_to_kcs)?;
    let cost_ledger = CostLedger::new(cost_ledger_path());
    let month = utc_month(&now_utc_seconds());
    let scope_id = repo.scope_id_for_adapter();
    // N1a (defense in depth): even a Pending online markdownize task must not be
    // sent when its input is a Tier B (candidate-secret) file and the scope is not
    // `--send-secrets`-approved — in case the hold was cleared by some other path.
    let secrets_approved = secrets_send_approved(repo);
    let online_profile = online_markdownize_profile_for(repo);
    let output_ref = online_output_ref(&online_profile.adapter_id);
    // R22-6(a): R21-6 gave the embedding pipeline a live-AuthError revive but never wired
    // the markdownize twin, so a 401/403 left its task Failed(`auth_error`) — non-retryable
    // (`max_attempts:0`), hence invisible to `batch retry` and to this Pending filter — with
    // its F8 phantom reservation eating the month's cap. Fixing the credentials resumed
    // nothing. Revive here, BEFORE the Pending set is built, so the repaired credentials are
    // used on this very pass. Only a task whose precondition is not `Retire` (file present,
    // unedited, within the cap) is revived; a genuinely stale one is retired by the loop
    // below as before. 401/403 is refused before billing (R20-3), so its reservation is a
    // reclaimable phantom.
    let markdown_adapter_kind = adapter_kind_budget_key(online_profile.adapter_kind);
    let auth_revivable = if allow_auth_revive {
        store
            .all()
            .map_err(pipeline_to_kcs)?
            .into_iter()
            .filter(|task| {
                task.task_type == TaskType::Markdownize
                    && targets_standard_online_markdownize(store.kcs_dir(), task, &output_ref)
                    && task.status == TaskStatus::Failed
                    && retry_kind_from_reason(task.fallback_reason.as_deref())
                        == RetryErrorKind::AuthError
                    && !matches!(
                        classify_online_markdownize_precondition(repo, task),
                        OnlineMarkdownizePrecondition::Retire
                    )
            })
            .map(|task| task.task_id)
            .collect::<BTreeSet<_>>()
    } else {
        BTreeSet::new()
    };
    if !auth_revivable.is_empty() {
        let mut reclaims: Vec<MonthlyCostLedgerEntry> = Vec::new();
        for task in store.all().map_err(pipeline_to_kcs)? {
            if auth_revivable.contains(&task.task_id) {
                if let Some(entry) =
                    settle_task_reservation(&cost_ledger, &task, &scope_id, markdown_adapter_kind)?
                {
                    reclaims.push(entry);
                }
            }
        }
        store
            .update_matching(|task| {
                if !auth_revivable.contains(&task.task_id) {
                    return false;
                }
                task.clear_reservation();
                task.status = TaskStatus::Pending;
                task.fallback_reason = Some("ready_for_online_adapter".to_owned());
                task.attempts = 0;
                task.next_retry_at = None;
                task.heartbeat_at = None;
                true
            })
            .map_err(pipeline_to_kcs)?;
        let reclaim_ledger = cost_ledger.reclaim_ledger();
        for entry in &reclaims {
            reclaim_ledger
                .append_monthly(entry)
                .map_err(pipeline_to_kcs)?;
        }
    }
    let tasks = store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.status == TaskStatus::Pending
                && task.task_type == TaskType::Markdownize
                && targets_standard_online_markdownize(store.kcs_dir(), task, &output_ref)
                // Honor an unelapsed retry backoff even for a Pending task
                // (Step2c I2); `batch retry` already gates on this, so this is
                // a defensive belt-and-braces guard.
                && task_retry_due(task)
                // R19-1: the send-time defensive re-check must exclude ANY unapproved
                // secret (Tier B or a lifted Tier A), not just Tier B.
                && (secrets_approved
                    || classify_secret(&task.input_path).is_none())
        })
        .collect::<Vec<_>>();
    let mut counts = ExecOutcome::default();
    for task in tasks {
        let task_id = task.task_id.clone();
        // R15-2: verify the network-free preconditions BEFORE reserving the cost. F8
        // charges under the device-global lock BEFORE the send, but a stale (edited-
        // after-enqueue), text-native, or unpreparable task is superseded by R14-2
        // inside the executor WITHOUT ever calling the adapter — so charging first is a
        // phantom charge that double-bills and can exhaust the markdownize cap, falsely
        // pausing the valid task. Fail the task here (non-retryable invalid_input; the
        // recovery is a re-index, not a retry) instead of charging + entering the
        // executor. This mirrors the executor's own R14-2/R9-2 guards, hoisted ahead of
        // the charge.
        let prepared_input = match classify_online_markdownize_precondition(repo, &task) {
            OnlineMarkdownizePrecondition::Send(prepared_input) => prepared_input,
            OnlineMarkdownizePrecondition::AwaitConversion => {
                // A live Office document remains honest Pending work until its bounded
                // local conversion contract exists. Nothing was sent or charged.
                continue;
            }
            OnlineMarkdownizePrecondition::Retire => {
                // R18-2: this task may carry a kept RateLimit/Quota phantom from a PRIOR
                // failed send (its file was deleted/edited after that attempt). Reclaim it
                // here — `batch retry` preserved `fallback_reason`, so the failure kind is
                // still intact — BEFORE the retirement overwrites the reason to
                // invalid_input; otherwise the R18-2 index sweep (which reads the failure
                // kind) can no longer tell it was a non-billable phantom. No NEW charge is
                // reserved this pass (the precondition failed before the charge).
                let markdown_adapter_kind = adapter_kind_budget_key(online_profile.adapter_kind);
                let reclaim =
                    settle_task_reservation(&cost_ledger, &task, &scope_id, markdown_adapter_kind)?;
                store
                    .update_matching(|candidate| {
                        if candidate.task_id == task_id {
                            retire_online_task(candidate);
                            candidate.attempts = candidate.attempts.saturating_add(1);
                            true
                        } else {
                            false
                        }
                    })
                    .map_err(pipeline_to_kcs)?;
                if let Some(entry) = reclaim {
                    cost_ledger
                        .reclaim_ledger()
                        .append_monthly(&entry)
                        .map_err(pipeline_to_kcs)?;
                }
                counts.failed += 1;
                continue;
            }
        };
        // R16-7: error-kind-aware re-reservation gate. When THIS task instance is a
        // re-send whose PREVIOUS recorded failure was a non-billable rejection
        // (RateLimit / QuotaExceeded — the backend refuses the request before it
        // processes or bills anything), skip the reservation: the prior attempt's F8
        // reservation (kept on failure) already covers this send. Without the gate a
        // RateLimit retry (task.rs `retry_policy`: max_attempts = None, unbounded)
        // re-reserves the FULL document cost on every attempt, so one logical operation
        // bills N times and can exhaust the device month cap — falsely pausing unrelated
        // tasks in other scopes (R15-2's harm, reproduced on the retry path).
        //
        // Only RateLimit/QuotaExceeded skip — deliberately NOT "reserve once for the
        // task's lifetime" (Opus's rejected `cost_reserved` proposal): a NetworkError
        // re-send may have been billed server-side (the request can reach the backend
        // before the socket drops), so it reserves afresh each attempt, bounded by
        // max_attempts = 5. Reserving once would let real spend exceed the reserved cap
        // on server-side-billed retries — the silent cap bypass R15-5 flagged as major,
        // the opposite failure. A crash mid-send (Q3 reclaim, Running -> Pending) also
        // re-reserves: the Running flip below clears `fallback_reason` so a reclaimed
        // task reaches the charge path here rather than inheriting this attempt's
        // "rate_limit" skip — its send's billing outcome is unknown after a crash, so we
        // stay conservative (bounded by the attempts policy).
        let previous_failure_kind = retry_kind_from_reason(task.fallback_reason.as_deref());
        let reservation_already_covers_resend = if matches!(
            previous_failure_kind,
            RetryErrorKind::RateLimit | RetryErrorKind::QuotaExceeded
        ) {
            match task.reservation_claim() {
                Some(claim) => cost_ledger
                    .reservation_ledger()
                    .activate_for_retry(claim, &scope_id, markdown_adapter_kind)
                    .map_err(pipeline_to_kcs)?,
                None => false,
            }
        } else {
            false
        };
        // R17-3: the exact amount of a FRESH reservation made this pass (None on the
        // RateLimit/Quota skip, which reuses the prior reservation). Stamped onto the
        // task below so that, if this task later fails RateLimit/Quota and is then
        // superseded by an edit, the supersede can reclaim precisely this phantom.
        let mut fresh_reserved: Option<ReservationRecord> = None;
        let charge = if reservation_already_covers_resend {
            // The previous attempt's reservation stands in for this send's charge.
            ChargeOutcome::Charged
        } else {
            let file_size = prepared_input.bytes.len() as u64;
            // R11-6: prorate the reserved (== billed, F8) cost of a UNIT-SCOPED retry by
            // the fraction of the document actually re-sent — `unit_keys` names the
            // still-failed units, and `execute_online_markdownize_task` requests only
            // those. A full send (`unit_keys == None`) still bills the whole document.
            // Without this, a 1-page retry of a 500-page PDF re-billed all 500 pages.
            let estimated_usd = prorated_markdownize_cost(
                &task,
                file_size,
                prepared_input.prepared_units.len(),
                task.bbox_annotation_enabled.unwrap_or(false),
            );
            let estimate = BudgetEstimate {
                scope_id: scope_id.clone(),
                task_type: TaskType::Markdownize,
                estimated_usd,
                adapter_id: Some(online_profile.adapter_id.clone()),
            };
            let adapter_kind = adapter_kind_budget_key(online_profile.adapter_kind);
            let reservation = ReservationRecord {
                reservation_id: format!("res_{}", new_ulid(repo.root())),
                task_id: task_id.clone(),
                month: month.clone(),
                scope_id: scope_id.clone(),
                adapter_kind: adapter_kind.to_owned(),
                usd: estimated_usd,
            };
            // F8: reserve the charge under the device-global cost-ledger lock BEFORE
            // execution, serializing the budget read-check-append against every other
            // scope. The executor bills exactly this estimate under the "markdown" key
            // (the previous post-execution append recomputed the same value), so the
            // reserved row is identical. The adapter call runs outside the lock; a
            // failure keeps the reservation (see helper docs).
            let outcome = charge_cost_ledger_under_lock(
                &cost_ledger,
                cost_ledger_lock_path(),
                &budget_caps,
                CostChargeRequest {
                    month: &month,
                    adapter_kind,
                    estimate: &estimate,
                    override_budget,
                    reservations: std::slice::from_ref(&reservation),
                },
            )?;
            // R17-3: record the fresh reservation amount ONLY when it actually landed
            // (a BudgetExceeded outcome appended nothing, so there is no phantom to
            // reclaim). Equals the exact `estimated_usd` row so the future reclaim
            // cancels it precisely.
            if matches!(outcome, ChargeOutcome::Charged) {
                fresh_reserved = Some(reservation);
            }
            outcome
        };
        if matches!(charge, ChargeOutcome::BudgetExceeded) {
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
            // R11-2: a Pending task budget-paused THIS pass → docs/04 §5.6 exit 6.
            counts.paused += 1;
            continue;
        }
        store
            .update_matching(|candidate| {
                if candidate.task_id == task_id {
                    candidate.status = TaskStatus::Running;
                    candidate.heartbeat_at = Some(now_utc_seconds());
                    // R16-7: entering the send clears the retry-kind marker so a crash
                    // mid-send (reclaimed by Q3 to Pending) re-reserves on the next pass
                    // rather than inheriting this attempt's "rate_limit"/"quota_exceeded"
                    // skip — a crashed send's billing outcome is unknown, so the earlier
                    // reservation may already be consumed and we must charge afresh. On a
                    // recorded failure the reason is re-set below, so the skip gate still
                    // sees it for a normal (non-crash) retry.
                    candidate.fallback_reason = None;
                    // R17-3: stamp the live reservation (amount + its ledger month) so a
                    // later supersede can reclaim this phantom if the send fails
                    // RateLimit/Quota. Only overwrite on a FRESH charge; the RateLimit/
                    // Quota skip keeps the original stamp (the single reservation the
                    // R16-7 skip gate still relies on). Persisted here, alongside the
                    // Running flip, so it survives the subsequent Failed transition.
                    if let Some(reservation) = &fresh_reserved {
                        candidate.reserved_usd = Some(reservation.usd);
                        candidate.reserved_month = Some(reservation.month.clone());
                        candidate.reservation_id = Some(reservation.reservation_id.clone());
                    }
                    true
                } else {
                    false
                }
            })
            .map_err(pipeline_to_kcs)?;
        let active_claim = fresh_reserved
            .as_ref()
            .map(ReservationRecord::claim)
            .or_else(|| task.reservation_claim())
            .ok_or_else(|| KcsError::schema("charged markdownize task has no reservation"))?;
        match execute_online_markdownize_task(repo, &task, prepared_input) {
            Ok(outcome) => {
                // Charge already reserved under the device-global lock above (F8).
                transition_reservation_after_outcome(
                    &cost_ledger,
                    active_claim,
                    &scope_id,
                    markdown_adapter_kind,
                    None,
                )?;
                store
                    .update_matching(|candidate| {
                        if candidate.task_id == task_id {
                            candidate.status = outcome.status;
                            candidate.output_ref = outcome.output_ref.clone();
                            candidate.fallback_reason = Some("online_adapter_done".to_owned());
                            candidate.heartbeat_at = None;
                            // R19-5: a unit-scoped retry that still returns Partial (units
                            // missing) consumed one re-drive of the retry budget — advance
                            // `attempts` HERE, the single accounting point, so it converges
                            // on `max_attempts` (the Err arm below does the same). Pre-R19-5
                            // this lived in `reenqueue_partial_markdownize_tasks` and
                            // double-counted with the Err arm.
                            if outcome.status == TaskStatus::Partial {
                                candidate.attempts = candidate.attempts.saturating_add(1);
                            }
                            // R13-1: record the normalization-run provenance
                            // (docs/04:474-479) so `status` and the next incremental
                            // decision (consecutive count) can see mode / previous /
                            // changed units. `Full` clears any prior incremental mark.
                            candidate.mode = Some(outcome.mode);
                            candidate.previous_raw_hash = outcome.previous_raw_hash.clone();
                            candidate.parent_run_id = outcome.parent_run_id.clone();
                            candidate.changed_unit_keys = outcome.changed_unit_keys.clone();
                            true
                        } else {
                            false
                        }
                    })
                    .map_err(pipeline_to_kcs)?;
                counts.executed += 1;
            }
            Err(error) => {
                transition_reservation_after_outcome(
                    &cost_ledger,
                    active_claim,
                    &scope_id,
                    markdown_adapter_kind,
                    Some(error.retry_kind),
                )?;
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
                // R9-7: a driven task that failed still attempted an online send
                // (rate-limit / auth / charge consumed) — count it so `batch` JSON
                // surfaces the attempt instead of reporting only successes.
                counts.failed += 1;
                // R11-2: classify the failure for the batch exit code. Auth needs
                // user action (exit 5); a scheduled `next_retry_at` marks the task
                // retry-eligible (exit 3, else it counts toward all-permanent = 4).
                if error.retry_kind == RetryErrorKind::AuthError {
                    counts.auth_failed += 1;
                }
                if next_retry_at.is_some() {
                    counts.failed_retryable += 1;
                }
            }
        }
    }
    Ok(counts)
}

fn persistent_network_allowed(repo: &Repository) -> Result<bool> {
    persistent_network_allowed_for(repo, &online_markdownize_profile().adapter_id)
}

/// Persistent (config / approvals.jsonl) network opt-in for one specific online
/// adapter, keyed by `tool_id` (07 §3: opt-in unit is scope × adapter). A global
/// `allow_network = true` covers every adapter; a network revocation gates every
/// adapter off. Otherwise the scope must carry an approval row for *this*
/// `tool_id` (L4). Backward compatibility: a scope approved before per-adapter
/// rows existed carries only the then-active markdownize row, so an embedding
/// adapter reads no matching row and stays enqueue-only (decision #35).
fn persistent_network_allowed_for(repo: &Repository, tool_id: &str) -> Result<bool> {
    persistent_network_allowed_for_kcs_dir(repo.kcs_dir(), tool_id)
}

fn persistent_network_allowed_for_kcs_dir(kcs_dir: &Path, tool_id: &str) -> Result<bool> {
    if network_revoked_kcs_dir(kcs_dir)? {
        return Ok(false);
    }
    // Scope-local config is portable content and therefore cannot grant network
    // authority. A device-local user config may intentionally grant it globally.
    if read_allow_network_config(&user_config_toml_path())? == Some(true) {
        return Ok(true);
    }
    approval_row_present_in_kcs_dir(kcs_dir, Some(tool_id))
}

/// True when `approvals.jsonl` carries an online opt-in row for `tool_id`.
fn approval_row_present(repo: &Repository, tool_id: &str) -> Result<bool> {
    approval_row_present_for_scope(repo, Some(tool_id))
}

fn approval_row_present_for_scope(repo: &Repository, tool_id: Option<&str>) -> Result<bool> {
    approval_row_present_in_kcs_dir(repo.kcs_dir(), tool_id)
}

fn approval_row_present_in_kcs_dir(kcs_dir: &Path, tool_id: Option<&str>) -> Result<bool> {
    trusted_consent_present(kcs_dir, tool_id, ConsentOperation::Network)
}

fn embedding_opt_in_for_scopes(exec_scopes: &[ExecScope], tool_id: &str) -> Result<bool> {
    for exec in exec_scopes {
        if !persistent_network_allowed_for_kcs_dir(&exec.target.kcs_dir, tool_id)? {
            return Ok(false);
        }
    }
    Ok(!exec_scopes.is_empty())
}

/// Whether the embedding adapter may call the network in this pass (L4). Gated
/// on the embedding adapter's own opt-in, not the markdownize approval it used
/// to ride on. `offline` forces it off regardless of any recorded approval.
fn embedding_online_allowed(
    repo: &Repository,
    offline: bool,
    online: bool,
    online_confirmed: bool,
) -> Result<bool> {
    // Precedence (N7): `--offline` forces enqueue-only; then the per-invocation
    // `--online` temporary opt-in; then the persistent embedding opt-in row. The
    // `online` arm was missing, so `index --online` left embedding Pending even
    // though markdownize honored the same flag. The caller rejects bare `--online`
    // before reaching this point unless the current scope already has a valid
    // approval row, so this branch represents an explicit one-shot send.
    if offline {
        return Ok(false);
    }
    let Some(adapter_id) = active_embedding_adapter_id()? else {
        return Ok(false);
    };
    if online {
        if network_revoked(repo)? {
            return Ok(false);
        }
        return if online_confirmed {
            Ok(true)
        } else {
            approval_row_present(repo, &adapter_id)
        };
    }
    persistent_network_allowed_for(repo, &adapter_id)
}

#[derive(Debug, Clone)]
struct OnlineExecutionOutcome {
    output_ref: String,
    status: TaskStatus,
    // R13-1: normalization-run provenance (docs/04:474-479) so the caller records
    // mode / previous_raw_hash / parent_run_id / changed_unit_keys on the task.
    // `Full` with empty/None for a full or unit-scoped-retry send.
    mode: MarkdownizeMode,
    previous_raw_hash: Option<String>,
    parent_run_id: Option<String>,
    changed_unit_keys: Vec<String>,
}

impl OnlineExecutionOutcome {
    /// A `Full`-mode outcome (full send or unit-scoped retry) with no incremental
    /// provenance.
    fn full(output_ref: String, status: TaskStatus) -> Self {
        Self {
            output_ref,
            status,
            mode: MarkdownizeMode::Full,
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: Vec::new(),
        }
    }
}

#[derive(Debug, Clone)]
struct TaskExecutionFailure {
    retry_kind: RetryErrorKind,
}

/// R11-6: the online-markdownize cost to reserve/bill for `task`. A full send bills
/// the whole document; a unit-scoped retry (`task.unit_keys` = the still-failed
/// units) bills only its share = full × (retried units / total prepared units),
/// with a floor of one unit's worth. `total` comes from the same verified buffer and
/// prepare result that is later sent, so charge and request cardinality cannot race.
fn prorated_markdownize_cost(
    task: &TaskDescriptor,
    file_size: u64,
    prepared_unit_count: usize,
    bbox_annotation_enabled: bool,
) -> f64 {
    let full = estimate_online_markdownize_cost(file_size, bbox_annotation_enabled);
    let Some(unit_keys) = task.unit_keys.as_ref().filter(|keys| !keys.is_empty()) else {
        return full;
    };
    if prepared_unit_count == 0 {
        return full;
    }
    let sent = unit_keys.len().min(prepared_unit_count).max(1);
    full * (sent as f64 / prepared_unit_count as f64)
}

/// R15-2 (+ R14-2 / R9-2): the NETWORK-FREE preconditions an online markdownize task
/// must satisfy before it is charged/executed. Returns `false` when the task can never
/// reach the adapter: the current file no longer hashes to `input_hash` (edited after
/// enqueue → superseded by R14-2 inside the executor), the file is text-native (R9-2
/// rejects it), or its input can't be prepared into any unit. In every case the adapter
/// is never called, so reserving the cost first (F8 charges before the send) would be a
/// phantom charge against a send that never happens — it double-bills and can exhaust the
/// markdownize cap, falsely pausing the valid task (R15-2). The executor re-checks the
/// same conditions as defense in depth; this is the loop's pre-charge gate.
/// R21-3: outcome of the send-time online-markdownize precondition check.
enum OnlineMarkdownizePrecondition {
    /// File present, unchanged, within the input cap, non-text-native, with locally
    /// extracted units to enhance — ready to send.
    Send(PreparedOnlineMarkdownizeInput),
    /// Genuine failure — retire the task (file gone / edited-since-enqueue / text-native /
    /// oversize). The recovery is a fresh re-index, not a retry.
    Retire,
    /// The file is live and recognized, but KCS does not yet have a bounded local
    /// conversion contract that can feed it to the OCR adapter. Keep it Pending without
    /// charging or sending; currently this is the Office-container path.
    AwaitConversion,
}

struct PreparedOnlineMarkdownizeInput {
    path: PathBuf,
    media_type: String,
    bytes: Vec<u8>,
    prepared_units: Vec<PreparedUnit>,
}

/// R22-5: whether a locally-preparable input is really a TEXT file that only landed in
/// `application/octet-stream` because its extension is absent from the MIME table
/// (`.yaml`, `.json`, `.toml`, `.sh`, `Dockerfile`, …). `prepare_units` sniffs the bytes and
/// emits exactly one `File` unit for such input (`prepare.rs:90`), whereas a true binary
/// yields no units at all. R21-4 stopped *enqueueing* these for online OCR, but the send
/// gates still classified them by canonical MIME only — so a task an older build had already
/// enqueued survived the upgrade and `batch resume` shipped the raw bytes to the OCR API and
/// billed for it. This is the send-side mirror of R21-4's enqueue guard.
fn is_local_passthrough_text(media_type: &str, prepared_units: &[PreparedUnit]) -> bool {
    media_type == "application/octet-stream"
        && prepared_units.len() == 1
        && prepared_units[0].unit_type == UnitType::File
}

fn retry_unit_subset_is_valid(task: &TaskDescriptor, prepared_units: &[PreparedUnit]) -> bool {
    let Some(unit_keys) = &task.unit_keys else {
        return true;
    };
    if unit_keys.is_empty() {
        return false;
    }
    let requested = unit_keys
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    if requested.len() != unit_keys.len() {
        return false;
    }
    let prepared = prepared_units
        .iter()
        .map(|unit| unit.unit_key.as_str())
        .collect::<BTreeSet<_>>();
    requested.is_subset(&prepared)
}

fn classify_online_markdownize_precondition(
    repo: &Repository,
    task: &TaskDescriptor,
) -> OnlineMarkdownizePrecondition {
    if raw_ingest_is_purge_blocked(repo, &task.input_hash) {
        return OnlineMarkdownizePrecondition::Retire;
    }
    let path = repo.root().join(&task.input_path);
    let media_type = media_type_for_cli_path(&path).to_owned();
    let Ok(verified) = read_verified_scan_input(
        repo.root(),
        &task.input_path,
        effective_max_input_bytes(repo),
    ) else {
        return OnlineMarkdownizePrecondition::Retire;
    };
    if verified.raw_hash != task.input_hash {
        return OnlineMarkdownizePrecondition::Retire;
    }
    // R19-8: honor a `max_input_bytes` cap that was tightened AFTER this task was
    // enqueued. The enqueue-time gate (run_index_pipeline) only checked the cap in effect
    // then; a Pending task must not be sent to the online adapter if the operator has
    // since lowered the cap below the file's size — the same live re-check the sibling
    // `[adapter.policy]` key `allow_network` already gets at send time.
    if !current_scan_policy_allows_file(repo.root(), &task.input_path).unwrap_or(false) {
        return OnlineMarkdownizePrecondition::Retire;
    }
    if is_text_native_media(&media_type) {
        return OnlineMarkdownizePrecondition::Retire;
    }
    let prepare_profile_hash = builtin_prepare_profile().tool_profile_hash;
    let input_path = path.display().to_string();
    let Ok(prepare) = prepare_units_from_bytes(PrepareStageBytesRequest {
        raw_hash: &task.input_hash,
        media_type: &media_type,
        input_path: &input_path,
        tool_profile_hash: &prepare_profile_hash,
        bytes: &verified.bytes,
    }) else {
        return OnlineMarkdownizePrecondition::Retire;
    };
    if prepare.prepared_units.is_empty() {
        // A supported non-text-native file reaches the provider without local unit
        // hints; the OCR response discovers its canonical page/image units.
        // A unit-scoped retry can recover those units from the previously-persisted
        // Partial manifest. Office containers still need a separate bounded conversion
        // contract, and unknown octet-stream binaries are never valid OCR inputs.
        if !supports_ocr_from_scratch(&media_type) {
            return if media_type == "application/octet-stream" {
                OnlineMarkdownizePrecondition::Retire
            } else {
                OnlineMarkdownizePrecondition::AwaitConversion
            };
        }
        let prepared_units = if task.unit_keys.is_some() {
            let store = TaskStore::new(repo.kcs_dir());
            let Ok(Some(previous)) = load_previous_instance_for_task(&store, task) else {
                return OnlineMarkdownizePrecondition::Retire;
            };
            previous.prepared_units
        } else {
            Vec::new()
        };
        if !retry_unit_subset_is_valid(task, &prepared_units) {
            return OnlineMarkdownizePrecondition::Retire;
        }
        return OnlineMarkdownizePrecondition::Send(PreparedOnlineMarkdownizeInput {
            path,
            media_type,
            bytes: verified.bytes,
            prepared_units,
        });
    }
    // R22-5: retire a legacy task for octet-stream TEXT. The recovery is a re-index (which
    // no longer enqueues it), not a retry — the deterministic pass already handled the file.
    if is_local_passthrough_text(&media_type, &prepare.prepared_units) {
        return OnlineMarkdownizePrecondition::Retire;
    }
    if !retry_unit_subset_is_valid(task, &prepare.prepared_units) {
        return OnlineMarkdownizePrecondition::Retire;
    }
    OnlineMarkdownizePrecondition::Send(PreparedOnlineMarkdownizeInput {
        path,
        media_type,
        bytes: verified.bytes,
        prepared_units: prepare.prepared_units,
    })
}

fn execute_online_markdownize_task(
    repo: &Repository,
    task: &TaskDescriptor,
    prepared_input: PreparedOnlineMarkdownizeInput,
) -> std::result::Result<OnlineExecutionOutcome, TaskExecutionFailure> {
    let PreparedOnlineMarkdownizeInput {
        path,
        media_type,
        bytes,
        mut prepared_units,
    } = prepared_input;
    // R14-2: an online markdownize task is always deferred — one pass enqueues it and
    // a later `batch resume` / `index --online` executes it — so the file may have been
    // edited in between. Executing a stale task reads the CURRENT bytes yet persists
    // them under the enqueue-time `input_hash` (identity = raw_hash), i.e. it stores v2
    // content under v1 identity. That breaks the content-addressing invariant, is
    // sticky (CAS idempotency never re-OCRs H(v1) again), mis-bills the v2 OCR under
    // v1, and poisons the next incremental's baseline (`latest_online_instance_for_path`
    // reads the tainted instance as "previous"). If the current file no longer hashes
    // to `task.input_hash`, supersede this task: do NOT execute or persist. The next
    // `index` enqueues a fresh task for the new content (the recovery is a re-index, not
    // a retry of this obsolete task — hence non-retryable InvalidInput; the task state
    // machine has no dedicated "superseded" state). Distinct from R14-1 (which degrades
    // an unreadable PREVIOUS instance to a Full re-send of the CURRENT content): here the
    // CURRENT content itself no longer matches the task, so there is nothing to send.
    if !current_scan_policy_allows_file(repo.root(), &task.input_path).unwrap_or(false) {
        return Err(TaskExecutionFailure {
            retry_kind: RetryErrorKind::InvalidInput,
        });
    }
    // R9-2 (defense in depth): never send a text-native file to online OCR even if
    // a task for it already exists (e.g. enqueued by a pre-fix build or a poisoned
    // tasks.jsonl). Fail fast as a non-retryable input error instead of a silent,
    // billed send.
    if is_text_native_media(&media_type) {
        return Err(TaskExecutionFailure {
            retry_kind: RetryErrorKind::InvalidInput,
        });
    }
    // R22-5 (defense in depth, mirroring the R9-2 guard above): never ship octet-stream TEXT
    // to online OCR even if a task for it exists (enqueued by a pre-R21-4 build, or a
    // poisoned tasks.jsonl). Fail fast as a non-retryable input error, never a billed send.
    if is_local_passthrough_text(&media_type, &prepared_units) {
        return Err(TaskExecutionFailure {
            retry_kind: RetryErrorKind::InvalidInput,
        });
    }
    let scope_id = repo.scope_id_for_adapter();
    // R11-6: on a UNIT-SCOPED retry, `task.unit_keys` names the still-failed units.
    // Request ONLY those from the adapter (re-OCR + re-bill just the failed subset,
    // not the whole document); the full prepared set still drives the manifest so
    // done/failed accounting covers every unit. `unit_keys == None` = a full send.
    let retry_units: Option<BTreeSet<String>> = task
        .unit_keys
        .as_ref()
        .map(|keys| keys.iter().cloned().collect());
    // R13-1: for a FRESH send (not a unit-scoped retry), try incremental Markdownize
    // first — re-OCR only the changed/added pages and reuse the unchanged pages'
    // markdown from the prior online instance (docs/04 §2.2/§3.1, docs/07 §8 note).
    // Returns Some on success; None when it doesn't apply or the acceptance check
    // fails (fall through to the Full send below); Err on an adapter auth/rate error
    // (a Full re-send would hit the same error, so propagate).
    if retry_units.is_none() && !prepared_units.is_empty() {
        if let Some(outcome) = try_online_incremental_markdownize(
            repo,
            task,
            &prepared_units,
            &scope_id,
            &media_type,
            &path,
            &bytes,
        )? {
            return Ok(outcome);
        }
    }
    let request_units: Vec<PreparedUnit> = match &retry_units {
        Some(keys) => prepared_units
            .iter()
            .filter(|unit| keys.contains(&unit.unit_key))
            .cloned()
            .collect(),
        None => prepared_units.clone(),
    };
    let outcome = run_standard_online_markdownize_with_bytes(
        StandardOnlineMarkdownizeRequest {
            scope_id: &scope_id,
            kcs_dir: repo.kcs_dir(),
            raw_hash: &task.input_hash,
            path: &path,
            media_type: &media_type,
            prepared_unit_hints: prepared_unit_hints(&request_units),
            // Full send (or unit-scoped retry): every requested unit, no previous/hints.
            mode: AdapterMarkdownizeMode::Full,
            previous: None,
            hints: None,
            // R15-5: a unit-scoped retry (`retry_units.is_some()`) re-sends ONLY the failed
            // subset — scope the real OCR send/bill to those pages instead of the whole
            // document (the ledger already prorated the reserve to the subset). A fresh full
            // send (`retry_units.is_none()`) leaves this false → whole document, no `pages`.
            restrict_to_hint_pages: retry_units.is_some(),
            bbox_annotation_enabled: task.bbox_annotation_enabled.unwrap_or(false),
        },
        &bytes,
    )
    .map_err(task_failure_from_adapter)?;
    if prepared_units.is_empty() {
        if retry_units.is_some() {
            return Err(TaskExecutionFailure {
                retry_kind: RetryErrorKind::ContractViolation,
            });
        }
        prepared_units = prepared_units_from_ocr_discovery(
            &outcome.effective_prepared_unit_hints,
            &media_type,
            &task.input_hash,
            &bytes,
        )
        .map_err(|_| TaskExecutionFailure {
            retry_kind: RetryErrorKind::ContractViolation,
        })?;
        // No page artifact exists before OCR for a scanned PDF. The already-verified
        // immutable raw object is the bounded prepared source shared by each discovered
        // unit; publish it under the same content hash before the manifest can refer to it.
        write_cas_object_or_reuse_legacy(repo.kcs_dir(), "prepared", &task.input_hash, &bytes)
            .map_err(|_| TaskExecutionFailure {
                retry_kind: persist_failure_retry_kind(),
            })?;
    }
    let profile = outcome.profile;
    let response = outcome.response;
    let hints = all_changed_hints(&prepared_units);
    let strict_valid = validate_markdownize_response(&response, &hints, &prepared_units).is_ok();
    let generated_at = now_utc_seconds();
    // R11-6: preserve previously-done units (first-instance-wins). Load the prior
    // instance this run overwrites (same raw_hash + resolved tool_profile_hash +
    // gen 0). Regenerating a done unit under Markdown non-determinism would churn its
    // fingerprint → needless re-embedding + Evidence churn (docs/04 §5.2).
    let previous = if retry_units.is_some() {
        load_previous_instance_identity(
            repo.kcs_dir(),
            &task.input_hash,
            &profile.tool_profile_hash,
            0,
        )
        .ok()
    } else {
        None
    };
    let mut units = normalized_units_from_response(
        &response,
        &prepared_units,
        previous.as_ref(),
        &task.input_hash,
        &profile.tool_profile_hash,
        MarkdownizeMode::Full,
        &generated_at,
    )
    .map_err(|_| TaskExecutionFailure {
        retry_kind: RetryErrorKind::ContractViolation,
    })?;
    // R11-6: merge in the previously-done units the retry did not target. The retry
    // request omitted them, so the adapter never returned them — keep the FIRST
    // instance's output verbatim (first-instance-wins).
    if let Some(prev) = &previous {
        let produced: BTreeSet<String> = units.iter().map(|unit| unit.unit_key.clone()).collect();
        for prev_unit in &prev.units {
            if !produced.contains(&prev_unit.unit_key) {
                units.push(prev_unit.clone());
            }
        }
        // Re-establish document order after appending the preserved units.
        let order_of: BTreeMap<&str, u64> = prepared_units
            .iter()
            .map(|unit| (unit.unit_key.as_str(), unit.order))
            .collect();
        units.sort_by_key(|unit| {
            order_of
                .get(unit.unit_key.as_str())
                .copied()
                .unwrap_or(u64::MAX)
        });
    }
    // A total coverage miss is retryable just like a partial coverage miss. The adapter
    // itself enforces the provider's exact page bijection, but a downstream transport
    // seam may still yield zero normalized outputs (notably a one-unit image). Preserve
    // the placeholder output_ref and let the ordinary NetworkError backoff/retry path
    // re-drive the whole document; there is no Done unit worth materializing yet.
    if units.is_empty() {
        return Err(TaskExecutionFailure {
            retry_kind: RetryErrorKind::NetworkError,
        });
    }
    let done = units.len();
    let failed = prepared_units.len().saturating_sub(done);
    // R11-6: a unit-scoped retry's status is a pure function of merged done vs total.
    // `strict_valid` checks the response covered ALL changed units, which a retry
    // deliberately does not — so only a full send takes the strict Done shortcut.
    let status = if retry_units.is_none() && strict_valid {
        TaskStatus::Done
    } else {
        task_status_from_unit_counts(done, failed, false)
    };
    let run_id = format!("run_{}", new_ulid(repo.root()));
    let manifest = manifest_from_units(
        &prepared_units,
        &units,
        &task.input_hash,
        &profile.tool_profile_hash,
        None,
        &run_id,
        &generated_at,
        // R10-4: a unit missing from an online OCR response is a retryable transient
        // (a healthy adapter returns it — see R9-4 partial->done recovery), so record
        // it as NetworkError. The re-enqueue path then respects the retry budget
        // (max_attempts) instead of re-sending & re-billing it forever.
        RetryErrorKind::NetworkError,
    );
    persist_normalized_instance(repo.kcs_dir(), &manifest, &units).map_err(|_| {
        TaskExecutionFailure {
            retry_kind: persist_failure_retry_kind(),
        }
    })?;
    Ok(OnlineExecutionOutcome::full(
        normalized_output_ref(repo, &task.input_hash, &profile.tool_profile_hash, 0),
        status,
    ))
}

/// R13-1: attempt incremental Markdownize on the online (Mistral OCR) route.
/// `Ok(Some(outcome))` = incremental fired and passed the KCS-side acceptance
/// check (docs/04 §3.2). `Ok(None)` = it does not apply (no prior online instance,
/// change too large / consecutive cap, or the prior tool_profile differs) OR the
/// incremental output failed acceptance — the caller then does a Full re-send.
/// `Err` = an adapter auth/rate/etc. error (a Full re-send would hit the same
/// error and re-bill, so propagate). Only the changed+added pages are sent to the
/// API; unchanged pages are reused from the prior instance (`reused_from`), which
/// is the cost fix (a light revision no longer re-sends/re-bills every page).
fn try_online_incremental_markdownize(
    repo: &Repository,
    task: &TaskDescriptor,
    prepared_units: &[PreparedUnit],
    scope_id: &str,
    media_type: &str,
    path: &Path,
    verified_raw_bytes: &[u8],
) -> std::result::Result<Option<OnlineExecutionOutcome>, TaskExecutionFailure> {
    let invalid = || TaskExecutionFailure {
        retry_kind: RetryErrorKind::InvalidInput,
    };
    let incremental_config = effective_incremental_config(repo).map_err(|_| invalid())?;
    if !incremental_config.enabled {
        return Ok(None);
    }
    let task_store = TaskStore::new(repo.kcs_dir());
    // The prior online instance for this path (its own resolved tool_profile_hash).
    let Some(previous) =
        latest_online_instance_for_path(&task_store, &task.input_path).map_err(|_| invalid())?
    else {
        return Ok(None);
    };
    // unit_mapping (docs/04 §2.2) between the prior and current prepared units, then
    // the documented 5-condition decision (R12-1's `choose_markdownize_mode`, which
    // now reaches the incremental gate because the adapter declares the capability).
    let mapping = map_units(&previous.prepared_units, prepared_units);
    // R14-6: resolve the online adapter's profile NOW (this resolves the model pin — a
    // `GET /v1/models` for a `*-latest` alias, never an OCR upload/bill) so the pin/profile
    // gate below runs BEFORE any incremental send. Previously the mismatch was only checked
    // AFTER the incremental request had been sent (and, post-R14-4, the whole document
    // uploaded), wasting a send + bill and then re-sending Full. `capability_flags` are
    // pin-independent, so the mode decision is unchanged.
    let resolved_profile = resolve_standard_online_markdownize_profile_with_bbox(
        scope_id,
        task.bbox_annotation_enabled.unwrap_or(false),
    )
    .map_err(task_failure_from_adapter)?;
    let decision = choose_markdownize_mode(&IncrementalModeInput {
        has_previous_done_run: true,
        raw_hash_only_changed: true,
        adapter_capabilities: resolved_profile.capability_flags.clone(),
        change_rate: mapping.change_rate,
        threshold: incremental_config.threshold,
        consecutive_incremental_count: consecutive_online_incremental_count(
            &task_store,
            &task.input_path,
        )
        .map_err(|_| invalid())?,
        max_consecutive_incremental: incremental_config.max_consecutive,
    });
    if decision.mode != MarkdownizeMode::Incremental {
        return Ok(None);
    }
    // R14-6 gate (docs/04 §3.1 condition 2): a changed resolved pin is a different
    // tool_profile → NOT an eligible incremental. Fall back to a Full send BEFORE sending
    // (and, post-R14-4, before uploading) anything. This replaces the former post-send
    // re-check.
    if resolved_profile.tool_profile_hash != previous.manifest.tool_profile_hash {
        return Ok(None);
    }
    let incremental_hints = incremental_hints_from_mapping(&mapping, prepared_units);
    // Send ONLY the changed+added units to the OCR API (the cost fix).
    let requested: Vec<PreparedUnit> = prepared_units
        .iter()
        .filter(|unit| {
            incremental_hints.changed_unit_keys.contains(&unit.unit_key)
                || incremental_hints.added_unit_keys.contains(&unit.unit_key)
        })
        .cloned()
        .collect();
    // R15-6: a 0-change incremental (`requested` empty — nothing changed or added; only
    // unchanged units, possibly with pure removals) must NOT touch the adapter. There is
    // no page to OCR, so reuse every current unit from the prior instance directly.
    // Before this, an empty `requested` still issued an Incremental request whose empty
    // `pages` the real Mistral client paired with the WHOLE base64 document (all-pages
    // OCR/bill), contradicting docs/04 §3.2 / 04-pipeline "unchanged units are reused
    // KCS-side, not sent". The resolved profile was gated equal to `previous` above, so
    // no send is needed to learn the tool_profile_hash.
    let (mut response, profile_tool_hash) = if requested.is_empty() {
        (
            kcs_adapter::types::MarkdownizeResponse {
                mode_used: AdapterMarkdownizeMode::Incremental,
                updated_units: Vec::new(),
                unchanged_unit_keys: Vec::new(),
                added_units: Vec::new(),
                removed_unit_keys: Vec::new(),
                evidence_pointers: Vec::new(),
                fallback_to_full: false,
                reason: None,
            },
            resolved_profile.tool_profile_hash.clone(),
        )
    } else {
        let adapter_previous = PreviousMarkdownizeContext {
            raw: RawInput {
                raw_hash: previous.manifest.raw_hash.clone(),
                path: Some(path.display().to_string()),
            },
            normalized_units: previous
                .units
                .iter()
                .map(normalized_unit_to_adapter_unit)
                .collect(),
            tool_profile_hash: previous.manifest.tool_profile_hash.clone(),
        };
        let outcome = run_standard_online_markdownize_with_bytes(
            StandardOnlineMarkdownizeRequest {
                scope_id,
                kcs_dir: repo.kcs_dir(),
                raw_hash: &task.input_hash,
                path,
                media_type,
                prepared_unit_hints: prepared_unit_hints(&requested),
                mode: AdapterMarkdownizeMode::Incremental,
                previous: Some(adapter_previous),
                hints: Some(adapter_hints(&incremental_hints)),
                // Incremental already scopes pages via `mode`; the retry-only signal stays off.
                restrict_to_hint_pages: false,
                bbox_annotation_enabled: task.bbox_annotation_enabled.unwrap_or(false),
            },
            verified_raw_bytes,
        )
        .map_err(task_failure_from_adapter)?;
        let response = outcome.response;
        // R14-6: the pin/profile mismatch was gated BEFORE the send above, so
        // `outcome.profile` matches `previous` here (same resolution) — no post-send
        // re-check is needed. Acceptance (docs/04 §3.2): the OCR response must cover
        // every requested (changed+added) unit, and the adapter must not have declined.
        // Otherwise fall back to a Full re-send (fallback_reason = contract/coverage).
        if response.fallback_to_full {
            return Ok(None);
        }
        let produced: BTreeSet<String> = response
            .updated_units
            .iter()
            .chain(response.added_units.iter())
            .map(|unit| unit.unit_key.clone())
            .collect();
        if !requested
            .iter()
            .all(|unit| produced.contains(&unit.unit_key))
        {
            return Ok(None);
        }
        (response, outcome.profile.tool_profile_hash)
    };
    // KCS orchestrates the unchanged reuse (docs/07 §8: the document-processing
    // route reuses unchanged units KCS-side rather than via the adapter). Inject the
    // unchanged new keys so `normalized_units_from_response` copies their markdown
    // from the prior instance with `reused_from` set. In the 0-change path this is
    // EVERY current unit.
    response.unchanged_unit_keys = mapping
        .unchanged
        .iter()
        .map(|reuse| reuse.new_unit_key.clone())
        .collect();
    let generated_at = now_utc_seconds();
    let units = match normalized_units_from_response(
        &response,
        prepared_units,
        Some(&previous),
        &task.input_hash,
        &profile_tool_hash,
        MarkdownizeMode::Incremental,
        &generated_at,
    ) {
        Ok(units) => units,
        // A unit mapping that shifts keys (page insert/delete) can leave an
        // unchanged new key without a prior unit — degrade to a Full re-send rather
        // than fail the task.
        Err(_) => return Ok(None),
    };
    let produced_all: BTreeSet<&str> = units.iter().map(|unit| unit.unit_key.as_str()).collect();
    if !prepared_units
        .iter()
        .all(|unit| produced_all.contains(unit.unit_key.as_str()))
    {
        return Ok(None);
    }
    let run_id = format!("run_{}", new_ulid(repo.root()));
    let manifest = manifest_from_units(
        prepared_units,
        &units,
        &task.input_hash,
        &profile_tool_hash,
        Some(previous.manifest.gen),
        &run_id,
        &generated_at,
        RetryErrorKind::NetworkError,
    );
    persist_normalized_instance(repo.kcs_dir(), &manifest, &units).map_err(|_| {
        TaskExecutionFailure {
            retry_kind: persist_failure_retry_kind(),
        }
    })?;
    Ok(Some(OnlineExecutionOutcome {
        output_ref: normalized_output_ref(repo, &task.input_hash, &profile_tool_hash, 0),
        status: TaskStatus::Done,
        mode: MarkdownizeMode::Incremental,
        previous_raw_hash: Some(previous.manifest.raw_hash.clone()),
        parent_run_id: Some(previous.manifest.run_id.clone()),
        changed_unit_keys: incremental_hints.changed_unit_keys.clone(),
    }))
}

/// R13-1: the latest prior online-markdownize instance for `input_path` (the DONE
/// online task carries `fallback_reason = "online_adapter_done"` and an output_ref
/// pointing at its normalized instance). Distinct from `previous_instance_for_path`
/// (which the offline route uses, filtering out online refs) — here we WANT the
/// online instance and its own resolved `tool_profile_hash`.
fn latest_online_instance_for_path(
    task_store: &TaskStore,
    input_path: &str,
) -> Result<Option<PreviousInstance>> {
    let mut tasks = task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.input_path == input_path
                && matches!(task.status, TaskStatus::Done | TaskStatus::Partial)
                && task.fallback_reason.as_deref() == Some("online_adapter_done")
        })
        .collect::<Vec<_>>();
    tasks.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    for task in tasks {
        if let Some(previous) = load_previous_instance_for_task(task_store, &task)? {
            return Ok(Some(previous));
        }
    }
    Ok(None)
}

/// R13-1: consecutive prior online incremental runs for `input_path` (docs/04
/// §3.1 condition 5 — force Full after N to bound style drift). Counts back from
/// the most recent DONE online task while it was `mode = Incremental`.
fn consecutive_online_incremental_count(task_store: &TaskStore, input_path: &str) -> Result<u32> {
    let mut tasks = task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.input_path == input_path
                && task.status == TaskStatus::Done
                && task.fallback_reason.as_deref() == Some("online_adapter_done")
        })
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

/// R10-5: a `persist_normalized_instance` failure occurs AFTER a successful (and
/// already-billed, F8) OCR call, so it is a write-side I/O fault (ENOSPC / EIO /
/// interrupted fsync / a transient permission glitch), never bad input. Classify it
/// as a retryable `NetworkError` (retryable I/O) so `batch retry` can re-drive it
/// once the disk condition clears, instead of a non-retryable `InvalidInput` that
/// strands the billed, normalized output forever (retry & re-index both refuse it).
fn persist_failure_retry_kind() -> RetryErrorKind {
    RetryErrorKind::NetworkError
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
        // R13-2: a `keychain:` not-implemented auth is a permanent config gap, not a
        // transient — never retry/re-bill it.
        kcs_adapter::AdapterError::NotImplemented(_) => RetryErrorKind::InvalidInput,
    };
    TaskExecutionFailure { retry_kind }
}

// ===========================================================================
// K4 — embedding catalog wiring (adapter selection, index generation, query
// embedding).
// ===========================================================================

const EMBEDDING_ADAPTER_KIND: &str = "embedding";
/// Chunks embedded per adapter batch. Task granularity is per-chunk; adapter
/// call granularity is this.
const EMBEDDING_BATCH_SIZE: usize = 32;

fn embedding_execution() -> Option<AdoptedEmbeddingExecution> {
    let execution = active_adopted_embedding_execution();
    // R13-2(4): a Real activation with no tools.toml `[embedding]` declaration is
    // env-only drift (GEMINI_API_KEY alone). Record it once per run. Test seams
    // (Mock/AuthError/…) are not Real, so hermetic tests never trip this.
    if execution == Some(AdoptedEmbeddingExecution::Real)
        && kcs_adapter::tool_lock::registered_declared_adapter("embedding").is_none()
    {
        warn_undeclared_adapter_once("embedding");
    }
    execution
}

fn declared_embedding_profile(execution: AdoptedEmbeddingExecution) -> DeclaredEmbeddingProfile {
    declared_adopted_embedding_profile(execution)
}

fn active_embedding_adapter_id() -> Result<Option<String>> {
    let Some(execution) = embedding_execution() else {
        return Ok(None);
    };
    Ok(Some(declared_embedding_profile(execution).tool_id))
}

/// Run the active embedding adapter over a batch of items, returning one vector
/// per item.
fn run_embedding_adapter(
    execution: AdoptedEmbeddingExecution,
    items: Vec<EmbeddingItem>,
    input_type: EmbeddingInputType,
) -> std::result::Result<Vec<kcs_adapter::types::EmbeddingVector>, TaskExecutionFailure> {
    run_adopted_embedding(execution, items, input_type).map_err(|error| {
        // R13-2(e): a `keychain:` (not-implemented) auth must be LOUD — the query
        // path degrades to text fallback and the index path only counts a failed
        // task, so without this the specific misconfig never reaches any log. Record
        // it to errors.jsonl (once per run) so it is never silently swallowed.
        if matches!(error, kcs_adapter::AdapterError::NotImplemented(_)) {
            log_embedding_not_implemented_once(&adapter_to_kcs(clone_adapter_error(&error)));
        }
        task_failure_from_adapter(error)
    })
}

/// R13-2(e): record a `keychain:` not-implemented embedding auth to errors.jsonl,
/// deduped to once per run (the same misconfig fails every batch).
fn log_embedding_not_implemented_once(error: &KcsError) {
    use std::sync::atomic::{AtomicBool, Ordering};
    static LOGGED: AtomicBool = AtomicBool::new(false);
    if LOGGED.swap(true, Ordering::Relaxed) {
        return;
    }
    let _ = append_error_log(error);
}

/// Clone the subset of `AdapterError` this path can see (only `NotImplemented`
/// reaches [`log_embedding_not_implemented_once`]; other variants keep their
/// message via `to_string`).
fn clone_adapter_error(error: &kcs_adapter::AdapterError) -> kcs_adapter::AdapterError {
    match error {
        kcs_adapter::AdapterError::NotImplemented(message) => {
            kcs_adapter::AdapterError::NotImplemented(message.clone())
        }
        other => kcs_adapter::AdapterError::ContractViolation(other.to_string()),
    }
}

/// Compute the query embedding once per search (05 §1.1). Returns `None` when no
/// adapter is configured or the query is too short to embed. A failing adapter
/// call (auth/rate) degrades to `None` → text fallback rather than erroring the
/// whole search. Query-embedding cost is not metered in the MVP (negligible; the
/// budget guardrails target bulk index enrichment).
fn compute_query_embedding(query: &str) -> Result<Option<Vec<f32>>> {
    if query.chars().count() < 2 {
        return Ok(None);
    }
    let Some(execution) = embedding_execution() else {
        return Ok(None);
    };
    // O2 regression seam: mark that the query is about to be SENT to the embedding
    // endpoint, so a test can prove `--text` never reaches this path. No-op unless
    // the env var is set (mirrors the KCS_TEST_* adapter seams).
    record_query_embed_trace(query);
    let items = vec![EmbeddingItem {
        id: "query".to_owned(),
        text: Some(query.to_owned()),
        path: None,
        mime: None,
    }];
    match run_embedding_adapter(execution, items, EmbeddingInputType::Query) {
        Ok(vectors) => Ok(vectors.into_iter().next().map(|vector| vector.vector)),
        Err(_) => Ok(None),
    }
}

/// Append the query to the file named by `KCS_TEST_QUERY_EMBED_TRACE`, if set, at
/// the point the query embedding is sent (O2 test seam only; no-op in production).
fn record_query_embed_trace(query: &str) {
    if let Some(path) = std::env::var_os("KCS_TEST_QUERY_EMBED_TRACE") {
        let mut line = query.to_owned();
        line.push('\n');
        let _ = OpenOptions::new()
            .create(true)
            .append(true)
            .open(PathBuf::from(path))
            .and_then(|mut file| file.write_all(line.as_bytes()));
    }
}

/// The tool-lock `embedding` entry (07 §6) for the active seam, or `None` when no
/// embedding adapter is configured.
fn embedding_tool_lock_entry() -> Result<Option<Value>> {
    let Some(execution) = embedding_execution() else {
        return Ok(None);
    };
    let profile = declared_embedding_profile(execution);
    Ok(Some(json!({
        "tool_id": profile.tool_id,
        "profile_hash": profile.profile_hash,
        "dimensions": profile.dimensions,
        "distance": profile.distance,
        "modality": profile.modality,
        "kind": "online_api",
        "mode": "online",
    })))
}

/// A retained-history chunk eligible for the effective current config.
struct EmbeddableChunk {
    chunk_id: String,
    text: String,
    text_hash: String,
    raw_path: String,
    requires_secret_approval: bool,
}

/// Materialize the current-config chunk set for every exact normalized identity
/// retained by the bounded CAS graph. Purge barriers are applied here, before
/// content-vector reuse or any adapter enqueue can observe the chunk text.
fn retained_history_chunks(
    conn: &Connection,
    kcs_dir: &Path,
    retained_instances: &[RetainedNormalizedInstance],
    chunking_config_hash: &str,
) -> Result<Vec<EmbeddableChunk>> {
    let purge = PurgeState::new(kcs_dir);
    let in_progress = purge
        .read_journal()?
        .map(|journal| {
            journal
                .target_raw_hashes
                .into_iter()
                .collect::<BTreeSet<_>>()
        })
        .unwrap_or_default();
    let mut blocked_raw_hashes = in_progress;
    let raw_hashes = retained_instances
        .iter()
        .map(|instance| instance.raw_hash.clone())
        .collect::<BTreeSet<_>>();
    for raw_hash in raw_hashes {
        let tombstoned = purge.read_tombstone(&raw_hash)?.is_some();
        if tombstoned {
            blocked_raw_hashes.insert(raw_hash);
        }
    }

    let identities = retained_instances
        .iter()
        .filter(|instance| !blocked_raw_hashes.contains(&instance.raw_hash))
        .map(|instance| {
            (
                (
                    instance.raw_hash.clone(),
                    instance.normalize.tool_profile_hash.clone(),
                    instance.normalize.gen,
                ),
                (
                    instance.embedding_path.clone(),
                    classify_secret(&instance.embedding_path).is_some(),
                ),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mut statement = conn
        .prepare(
            "SELECT c.chunk_id, c.text, c.text_hash,
                    c.raw_hash, c.tool_profile_hash, c.gen
             FROM chunks c
             WHERE c.first_seen_commit IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM chunk_config_generations cg
                   WHERE cg.chunk_id = c.chunk_id
                     AND cg.chunking_config_hash = ?1
               )
             ORDER BY c.rowid",
        )
        .map_err(|error| KcsError::schema(error.to_string()))?;
    let rows = statement
        .query_map(rusqlite::params![chunking_config_hash], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, u64>(5)?,
            ))
        })
        .map_err(|error| KcsError::schema(error.to_string()))?;
    let mut chunks = Vec::new();
    for row in rows {
        let (chunk_id, text, text_hash, raw_hash, tool_profile_hash, gen) =
            row.map_err(|error| KcsError::schema(error.to_string()))?;
        let Some((raw_path, requires_secret_approval)) =
            identities.get(&(raw_hash, tool_profile_hash, gen))
        else {
            continue;
        };
        chunks.push(EmbeddableChunk {
            chunk_id,
            text,
            text_hash,
            raw_path: raw_path.clone(),
            requires_secret_approval: *requires_secret_approval,
        });
    }
    Ok(chunks)
}

/// Generate chunk embeddings for the scope after the SQLite index is rebuilt
/// (04 §4.3 / 07 §5.3). Enqueues one `TaskType::Embedding` task per pending chunk,
/// then — if the online opt-in and budget allow — embeds them (batched), writing
/// the `embeddings` rows (source of truth) and `chunk_vec` (derived KNN copy),
/// charging the cost ledger under `adapter_kind="embedding"`. Offline leaves tasks
/// Pending (surfaced by `index_status`). No-op when no embedding adapter is
/// configured (keeps the default index path unchanged).
fn generate_scope_embeddings(repo: &Repository, args: &IndexArgs) -> Result<ExecOutcome> {
    // Embedding online opt-in is the embedding adapter's own (L4), not a
    // ride-along on the markdownize approval. `--offline` forces enqueue-only;
    // N7: `--online` now reaches the embedding adapter too (was ignored).
    let online =
        embedding_online_allowed(repo, args.offline, args.online, args.yes || args.approve)?;
    // R11-2: return the enrichment outcome (was discarded) so `run_index` can disclose
    // it and raise the exit code on auth/budget-pause.
    run_embedding_enrichment(repo, online, false, false)
}

/// Core enrichment pass shared by `kcs index` (inline) and `kcs batch
/// resume/retry`. Without the resume path, embedding tasks left Pending by a
/// rate limit could never complete (`batch resume` only executed Markdownize
/// tasks). Returns the chunks embedded (executed) and failed this pass (R9-7).
fn run_embedding_enrichment(
    repo: &Repository,
    online: bool,
    override_budget: bool,
    allow_auth_revive: bool,
) -> Result<ExecOutcome> {
    run_embedding_enrichment_for_instances(
        repo,
        online,
        override_budget,
        allow_auth_revive,
        None,
        true,
    )
}

/// Historical reindex drives only the selected snapshot's embedding work. In
/// particular it must not reconcile/retire task rows belonging to non-selected
/// history merely because they are absent from this deliberately narrow set.
fn run_historical_embedding_enrichment(
    repo: &Repository,
    online: bool,
    selected_instances: &[RetainedNormalizedInstance],
) -> Result<ExecOutcome> {
    run_embedding_enrichment_for_instances(
        repo,
        online,
        false,
        false,
        Some(selected_instances),
        false,
    )
}

fn run_embedding_enrichment_for_instances(
    repo: &Repository,
    online: bool,
    override_budget: bool,
    allow_auth_revive: bool,
    selected_instances: Option<&[RetainedNormalizedInstance]>,
    reconcile_scope_tasks: bool,
) -> Result<ExecOutcome> {
    let Some(execution) = embedding_execution() else {
        return Ok(ExecOutcome::default());
    };
    let profile = declared_embedding_profile(execution);
    // Non-multimodal is rejected at materialize_tool_lock; never reach embed here.
    if profile.modality != "multimodal" {
        return Ok(ExecOutcome::default());
    }
    let db_path = sqlite_path(repo.kcs_dir());
    if !db_path.exists() {
        return Ok(ExecOutcome::default());
    }
    let conn = Connection::open(&db_path).map_err(|err| KcsError::schema(err.to_string()))?;
    let chunking_config_hash = read_chunking_config(repo)?.chunking_config_hash;
    let retained_instances_owned;
    let retained_instances = if let Some(selected) = selected_instances {
        selected
    } else {
        let Some(head) = repo.head_commit_hash()? else {
            return Ok(ExecOutcome::default());
        };
        // `kcs snapshot` advances HEAD without projecting tree_entries (search
        // projects lazily); do the same here or the live-chunk JOIN silently
        // matches nothing for any scope whose last commit was a snapshot.
        ensure_snapshot_tree_entries(repo, &conn, &head)?;
        retained_instances_owned = retained_history_instances(repo.kcs_dir(), &head)?;
        &retained_instances_owned
    };
    let retained_chunks = retained_history_chunks(
        &conn,
        repo.kcs_dir(),
        retained_instances,
        &chunking_config_hash,
    )?;
    let active_chunk_ids = retained_chunks
        .iter()
        .map(|chunk| chunk.chunk_id.clone())
        .collect::<BTreeSet<_>>();
    let pending = retained_chunks_without_embedding(&conn, retained_chunks, &profile)?;

    let task_store = TaskStore::new(repo.kcs_dir());
    let now = now_utc_seconds();
    // R12-3: reconcile task accounting for chunks that ARE embedded but whose task a
    // crash stranded Pending/Running (chunk_vec committed per batch, the task Done
    // write-back deferred to after the loop — R11-5). Must run BEFORE the
    // empty-`pending` early return: the r12k crash left every chunk embedded with 64
    // tasks still Pending, so `pending` is empty yet index_status reported phantom
    // pending enrichment forever. Idempotent; no adapter call, no re-charge.
    if reconcile_scope_tasks {
        reconcile_committed_embedding_tasks(
            repo,
            &task_store,
            EmbeddingReconcileContext {
                active_chunk_ids: &active_chunk_ids,
                pending: &pending,
                now: &now,
                allow_auth_revive,
            },
        )?;
    }
    if pending.is_empty() {
        return Ok(ExecOutcome::default());
    }
    // N1a: partition off chunks whose raw file is a Tier B (candidate-secret)
    // document without a `--send-secrets` approval. Their embedding tasks are held
    // (Paused `secrets_tier_b_hold`, visible in `kcs status`) and never enter the
    // send pipeline, so `index --online` / `batch resume` cannot ship their text
    // to the embedding API. Approval moves them back into `sendable`.
    let secrets_approved = secrets_send_approved(repo);
    let (held, sendable): (Vec<EmbeddableChunk>, Vec<EmbeddableChunk>) =
        pending.into_iter().partition(|chunk| {
            // R19-1: hold ANY secret (Tier B, or a lifted Tier A) from the embedding
            // API unless `--send-secrets`. Non-lifted Tier A never produces chunks
            // (excluded at ingest), so `.is_some()` newly gates only lifted Tier A.
            !secrets_approved && chunk.requires_secret_approval
        });
    hold_secret_embedding_tasks(&task_store, repo, &held, &now)?;
    if sendable.is_empty() {
        return Ok(ExecOutcome::default());
    }
    enqueue_embedding_tasks(&task_store, repo, &sendable, online, &now)?;
    if !online {
        // Offline: tasks stay Pending; `index_status` reports them (05 §1.7).
        return Ok(ExecOutcome::default());
    }

    // L2(ii)/L7: skip chunks whose embedding task is sticky budget-Paused (unless
    // override) or a Failed task that is not retry-eligible (unelapsed backoff or
    // non-retryable) — the same lifecycle semantics markdownize already honors.
    let embeddable = filter_embeddable_by_task_state(&task_store, sendable, override_budget)?;
    if embeddable.is_empty() {
        return Ok(ExecOutcome::default());
    }

    let mut outcome = ExecOutcome::default();
    let cost_ledger = CostLedger::new(cost_ledger_path());
    let budget_caps =
        read_budget_policy(user_config_toml_path(), repo.kcs_dir().join("config.toml"))
            .map_err(pipeline_to_kcs)?;
    let month = utc_month(&now);
    let scope_id = repo.scope_id_for_adapter();

    // R11-5: accumulate every chunk's task-store transition in memory and write it
    // back in ONE `update_matching` after the loop, instead of a full all()+
    // replace_all per 32-chunk batch. The per-batch form cost O(T) each × T/32
    // batches = O(T²/32), turning a few-thousand-chunk initial embedding into a
    // multi-minute hang.
    //
    // R17-7: the reuse-based crash safety here is precise about WHICH crash window it
    // covers. A crash AFTER `send_embed_batch` COMPLETES but before this deferred
    // write-back is fully absorbed: `send_embed_batch` already wrote the embeddings
    // row + chunk_vec and F8 already reserved the charge, so re-driving the chunk hits
    // the free content-addressed reuse path (§5.5: text_hash hit → no API call, no
    // re-charge), no unrecorded completion is double-billed, and the per-chunk map
    // keeps a reuse "done" from being contaminated by a sibling send "failed" (L6).
    // This does NOT extend to a crash INTERNAL to `send_embed_batch`, in the narrow
    // window AFTER the API bills but BEFORE the embeddings row / chunk_vec commit:
    // there the embeddings are unwritten, so §5.5 reuse misses and the chunk re-enters
    // `to_send`, yet its stale RateLimit/Quota `fallback_reason` makes
    // `reservation_covers_resend` skip the re-charge — so the resend double-bills the
    // API while the reservation stays at 1× = a BOUNDED per-chunk under-charge. That is
    // exactly the triple-fault R16 DEFERRED (window = bill→chunk_vec commit; damage =
    // one chunk's cost), left standing on purpose: closing it would need a per-chunk
    // pre-send persisted marker, re-introducing R11-5's O(T²) full-tasks.jsonl write.
    // The asymmetry with markdownize is deliberate: markdownize persists status=Running
    // + `fallback_reason=None` BEFORE its send, so a crash makes it re-reserve; embedding
    // keeps the per-batch write-back (O(T²) avoidance) and instead absorbs the NORMAL
    // (post-completion) crash via content-addressed reuse. R11-2: the loop also tallies
    // paused / auth / failed outcomes.
    let mut transitions: BTreeMap<String, EmbeddingTransition> = BTreeMap::new();
    // R18-1: per-chunk FRESH F8 reservation `(usd, ledger_month)` for the freshly-charged
    // chunks this pass, stamped in the single end-of-pass write-back so a later non-live
    // reclaim (R18-1) can cancel the exact phantom.
    let mut reserved_by_ref: BTreeMap<String, (f64, String, String)> = BTreeMap::new();

    // R16-7: embedding tasks whose PREVIOUS recorded failure was a non-billable
    // rejection (RateLimit / QuotaExceeded — refused before the backend processes or
    // bills the request). Their earlier F8 reservation already covers this resend, so
    // the per-batch charge below excludes their chars. Without this a rate-limited
    // chunk (RateLimit = unbounded retries) re-reserves its chars on every `batch
    // retry`, and one logical enrichment bills N times, exhausting the device month cap
    // and falsely pausing unrelated tasks (R15-2's harm on the retry path). Loaded once
    // at pass start (transitions are written back only after the loop), so it reflects
    // the PREVIOUS pass's outcome — exactly the "prior failure" the gate needs.
    //
    // Fresh / NetworkError / crash-stranded chunks are absent from this set and charge
    // afresh: a NetworkError send may have been billed server-side, and a crash mid-send
    // leaves the task Pending with its embedding uncommitted, so re-driving re-reserves
    // conservatively (bounded by max_attempts; a succeeded-but-uncommitted chunk instead
    // re-drives through §5.5 content-addressed reuse with NO re-charge). Reserving once
    // for the task's lifetime is deliberately NOT done — it would let real spend exceed
    // the reserved cap on server-side-billed retries (the R15-5 silent cap bypass).
    let embedding_tasks_by_ref = task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .map(|task| (task.output_ref.clone(), task))
        .collect::<BTreeMap<_, _>>();

    for batch in embeddable.chunks(EMBEDDING_BATCH_SIZE) {
        // Split content-addressed reuse (no API call, free) from chunks that
        // require a live adapter call (CT3-EMBED-006).
        let plan = match plan_embed_batch(&conn, &profile, batch) {
            Ok(plan) => plan,
            Err(failure) => {
                record_embedding_transitions(
                    &mut transitions,
                    batch.iter(),
                    embedding_fail_transition(failure.retry_kind),
                );
                count_embedding_failure(&mut outcome, failure.retry_kind, batch.len());
                break;
            }
        };
        // L6: reuse links are free and always succeed → link + complete them up
        // front so an API failure on the *sent* portion can never contaminate an
        // already-materialized (chunk_vec written) chunk into a stuck Failed task.
        if !plan.reuse.is_empty() {
            match link_reused_chunks(&conn, &profile, &plan.reuse) {
                Ok(()) => {
                    record_embedding_transitions(
                        &mut transitions,
                        plan.reuse.iter().map(|(chunk, _)| *chunk),
                        embedding_done_transition(),
                    );
                    outcome.executed += plan.reuse.len();
                }
                Err(failure) => {
                    record_embedding_transitions(
                        &mut transitions,
                        plan.reuse.iter().map(|(chunk, _)| *chunk),
                        embedding_fail_transition(failure.retry_kind),
                    );
                    count_embedding_failure(&mut outcome, failure.retry_kind, plan.reuse.len());
                    break;
                }
            }
        }
        if plan.to_send.is_empty() {
            continue;
        }
        let reservation_ledger = cost_ledger.reservation_ledger();
        let mut covered_groups = BTreeSet::new();
        let mut activated_claims = Vec::<TaskReservationClaim<'_>>::new();
        for (group_index, group) in plan.to_send.iter().enumerate() {
            let mut covered = false;
            for chunk in &group.members {
                let output_ref = embedding_task_output_ref(&chunk.chunk_id);
                let Some(task) = embedding_tasks_by_ref.get(&output_ref) else {
                    continue;
                };
                if !matches!(
                    retry_kind_from_reason(task.fallback_reason.as_deref()),
                    RetryErrorKind::RateLimit | RetryErrorKind::QuotaExceeded
                ) {
                    continue;
                }
                let Some(claim) = task.reservation_claim() else {
                    continue;
                };
                if reservation_ledger
                    .activate_for_retry(claim, &scope_id, EMBEDDING_ADAPTER_KIND)
                    .map_err(pipeline_to_kcs)?
                {
                    activated_claims.push(claim);
                    covered = true;
                }
            }
            if covered {
                covered_groups.insert(group_index);
            }
        }

        // L5 + R16-7: bill only identities that do not carry a trusted, atomically
        // reactivated reservation from a prior non-billable response.
        let sent_chars: u64 = plan
            .to_send
            .iter()
            .enumerate()
            .filter(|(index, _)| !covered_groups.contains(index))
            .map(|(_, group)| group.representative.text.chars().count() as u64)
            .sum();
        let mut fresh_by_ref = BTreeMap::<String, ReservationRecord>::new();
        for (group_index, group) in plan.to_send.iter().enumerate() {
            if covered_groups.contains(&group_index) {
                continue;
            }
            let output_ref = embedding_task_output_ref(&group.representative.chunk_id);
            let task = embedding_tasks_by_ref.get(&output_ref).ok_or_else(|| {
                KcsError::schema("embedding send has no matching task reservation owner")
            })?;
            fresh_by_ref.insert(
                output_ref,
                ReservationRecord {
                    reservation_id: format!("res_{}", new_ulid(repo.root())),
                    task_id: task.task_id.clone(),
                    month: month.clone(),
                    scope_id: scope_id.clone(),
                    adapter_kind: EMBEDDING_ADAPTER_KIND.to_owned(),
                    usd: estimate_embedding_cost(group.representative.text.chars().count() as u64),
                },
            );
        }
        let fresh_reservations = fresh_by_ref.values().cloned().collect::<Vec<_>>();
        let charge = if sent_chars == 0 {
            // Every to-send chunk is a RateLimit/Quota resend already reserved by its
            // prior attempt — skip the reservation entirely (no $0 ledger row).
            ChargeOutcome::Charged
        } else {
            let estimate = BudgetEstimate {
                scope_id: scope_id.clone(),
                task_type: TaskType::Embedding,
                estimated_usd: estimate_embedding_cost(sent_chars),
                adapter_id: Some(profile.tool_id.clone()),
            };
            // F8: reserve the charge under the device-global cost-ledger lock BEFORE
            // sending, so a concurrent scope observes this spend and cannot also pass
            // the cap (TOCTOU). The adapter call stays outside the lock.
            charge_cost_ledger_under_lock(
                &cost_ledger,
                cost_ledger_lock_path(),
                &budget_caps,
                CostChargeRequest {
                    month: &month,
                    adapter_kind: EMBEDDING_ADAPTER_KIND,
                    estimate: &estimate,
                    override_budget,
                    reservations: &fresh_reservations,
                },
            )?
        };
        if matches!(charge, ChargeOutcome::BudgetExceeded) {
            // A batch may mix retry groups already covered by a trusted prior
            // reservation with fresh groups whose new charge exceeds the cap.
            // The covered retries remain authorized and must still run; pausing
            // the whole batch would strand historical rate-limit work forever.
            let covered_to_send = plan
                .to_send
                .iter()
                .enumerate()
                .filter(|(index, _)| covered_groups.contains(index))
                .map(|(_, group)| group.clone())
                .collect::<Vec<_>>();
            if !covered_to_send.is_empty() {
                match send_embed_batch(&conn, execution, &profile, &covered_to_send) {
                    Ok(()) => {
                        for claim in &activated_claims {
                            transition_reservation_after_outcome(
                                &cost_ledger,
                                *claim,
                                &scope_id,
                                EMBEDDING_ADAPTER_KIND,
                                None,
                            )?;
                        }
                        record_embedding_transitions(
                            &mut transitions,
                            covered_to_send
                                .iter()
                                .flat_map(|group| group.members.iter().copied()),
                            embedding_done_transition(),
                        );
                        outcome.executed += covered_to_send
                            .iter()
                            .map(|group| group.members.len())
                            .sum::<usize>();
                    }
                    Err(failure) => {
                        for claim in &activated_claims {
                            transition_reservation_after_outcome(
                                &cost_ledger,
                                *claim,
                                &scope_id,
                                EMBEDDING_ADAPTER_KIND,
                                Some(failure.retry_kind),
                            )?;
                        }
                        record_embedding_transitions(
                            &mut transitions,
                            covered_to_send
                                .iter()
                                .flat_map(|group| group.members.iter().copied()),
                            embedding_fail_transition(failure.retry_kind),
                        );
                        count_embedding_failure(
                            &mut outcome,
                            failure.retry_kind,
                            covered_to_send
                                .iter()
                                .map(|group| group.members.len())
                                .sum(),
                        );
                    }
                }
            }
            // Budget exhausted: pause only fresh, uncovered groups. Already-linked
            // reuse and covered retry groups retain their independently-set state.
            record_embedding_transitions(
                &mut transitions,
                plan.to_send
                    .iter()
                    .enumerate()
                    .filter(|(index, _)| !covered_groups.contains(index))
                    .flat_map(|(_, group)| group.members.iter().copied()),
                embedding_pause_transition(),
            );
            // R11-2: budget-paused this pass → docs/04 §5.6 exit 6.
            outcome.paused += plan
                .to_send
                .iter()
                .enumerate()
                .filter(|(index, _)| !covered_groups.contains(index))
                .map(|(_, group)| group.members.len())
                .sum::<usize>();
            break;
        }
        // R18-1: a fresh charge landed (`sent_chars > 0`, ChargeOutcome::Charged). Record
        // each FRESHLY-charged chunk's exact reservation so its task is stamped in the
        // end-of-pass write-back. `estimate_embedding_cost` is linear in chars, so the
        // per-chunk amounts sum to exactly the batch charge — the reclaim (R18-1) of a
        // stranded phantom then cancels it precisely. RateLimit/Quota resends covered by a
        // prior reservation are excluded (they keep their original single stamp).
        for (output_ref, reservation) in &fresh_by_ref {
            reserved_by_ref.insert(
                output_ref.clone(),
                (
                    reservation.usd,
                    reservation.month.clone(),
                    reservation.reservation_id.clone(),
                ),
            );
        }
        match send_embed_batch(&conn, execution, &profile, &plan.to_send) {
            Ok(()) => {
                // Charge already reserved under the lock above (F8).
                for claim in activated_claims
                    .iter()
                    .copied()
                    .chain(fresh_reservations.iter().map(ReservationRecord::claim))
                {
                    transition_reservation_after_outcome(
                        &cost_ledger,
                        claim,
                        &scope_id,
                        EMBEDDING_ADAPTER_KIND,
                        None,
                    )?;
                }
                record_embedding_transitions(
                    &mut transitions,
                    plan.send_chunks(),
                    embedding_done_transition(),
                );
                outcome.executed += plan.send_count();
            }
            Err(failure) => {
                for claim in activated_claims
                    .iter()
                    .copied()
                    .chain(fresh_reservations.iter().map(ReservationRecord::claim))
                {
                    transition_reservation_after_outcome(
                        &cost_ledger,
                        claim,
                        &scope_id,
                        EMBEDDING_ADAPTER_KIND,
                        Some(failure.retry_kind),
                    )?;
                }
                // Enrichment failure is non-fatal: mark the sent chunks failed and
                // stop (search sees no embeddings → text). Never fails `kcs index`.
                record_embedding_transitions(
                    &mut transitions,
                    plan.send_chunks(),
                    embedding_fail_transition(failure.retry_kind),
                );
                count_embedding_failure(&mut outcome, failure.retry_kind, plan.send_count());
                break;
            }
        }
    }
    // R11-5: single write-back for the whole pass. Its return is the retry-eligible
    // failed count (needs per-task `attempts`), feeding the batch exit-code 3-vs-4
    // split (R11-2). `fallback_reason` per chunk (done/paused/failed) is preserved.
    outcome.failed_retryable +=
        apply_embedding_transitions(&task_store, &transitions, &now, &reserved_by_ref)?;
    Ok(outcome)
}

/// R11-5: one deferred task-store transition for an embedding chunk, applied in a
/// single pass by [`apply_embedding_transitions`].
#[derive(Clone, Copy)]
struct EmbeddingTransition {
    status: TaskStatus,
    reason: &'static str,
    failure_kind: Option<RetryErrorKind>,
}

fn embedding_done_transition() -> EmbeddingTransition {
    EmbeddingTransition {
        status: TaskStatus::Done,
        reason: "embedding_adapter_done",
        failure_kind: None,
    }
}

fn embedding_pause_transition() -> EmbeddingTransition {
    EmbeddingTransition {
        status: TaskStatus::Paused,
        reason: "budget_exceeded",
        failure_kind: None,
    }
}

fn embedding_fail_transition(kind: RetryErrorKind) -> EmbeddingTransition {
    EmbeddingTransition {
        status: TaskStatus::Failed,
        reason: retry_reason(kind),
        failure_kind: Some(kind),
    }
}

/// R19-3: terminalize a non-live embedding task REVERSIBLY — non-retryable (no
/// `failure_kind`, so no backoff/attempt bump), but `retired_non_live` so the enqueue
/// guard re-creates a fresh task if the exact chunk_id reappears (revert/restore).
fn embedding_retired_non_live_transition() -> EmbeddingTransition {
    EmbeddingTransition {
        status: TaskStatus::Failed,
        reason: RETIRED_NON_LIVE,
        failure_kind: None,
    }
}

/// R11-2: tally one failed embedding batch into the pass outcome — `failed` always,
/// and `auth_failed` when the error needs user re-auth (exit 5). `failed_retryable`
/// is finalized later in [`apply_embedding_transitions`] (it needs per-task attempts).
fn count_embedding_failure(outcome: &mut ExecOutcome, kind: RetryErrorKind, count: usize) {
    outcome.failed += count;
    if kind == RetryErrorKind::AuthError {
        outcome.auth_failed += count;
    }
}

fn record_embedding_transitions<'a>(
    transitions: &mut BTreeMap<String, EmbeddingTransition>,
    chunks: impl IntoIterator<Item = &'a EmbeddableChunk>,
    transition: EmbeddingTransition,
) {
    for chunk in chunks {
        transitions.insert(embedding_task_output_ref(&chunk.chunk_id), transition);
    }
}

/// R11-5: apply all accumulated embedding-task transitions in ONE `update_matching`.
/// Returns the count of failures recorded retry-eligible (retryable kind with
/// `attempts` remaining) so the caller can split the batch exit code 3 vs 4 (R11-2).
fn apply_embedding_transitions(
    task_store: &TaskStore,
    transitions: &BTreeMap<String, EmbeddingTransition>,
    now: &str,
    // R18-1: the FRESH per-chunk F8 reservation `(usd, ledger_month)` to stamp onto each
    // freshly-charged embedding task in this same single write-back (no extra
    // tasks.jsonl pass — respects R11-5/R17-7's O(T²) avoidance). Only freshly-charged
    // chunks are present; a RateLimit/Quota resend covered by a prior reservation is
    // absent and keeps its existing stamp. The stamp lets `reconcile_committed_embedding_tasks`
    // reclaim the exact phantom if the chunk later goes non-live (R18-1).
    reserved: &BTreeMap<String, (f64, String, String)>,
) -> Result<usize> {
    if transitions.is_empty() {
        return Ok(0);
    }
    let mut failed_retryable = 0usize;
    task_store
        .update_matching(|task| {
            if task.task_type != TaskType::Embedding {
                return false;
            }
            let Some(transition) = transitions.get(&task.output_ref) else {
                return false;
            };
            task.status = transition.status;
            task.fallback_reason = Some(transition.reason.to_owned());
            if let Some((usd, month, reservation_id)) = reserved.get(&task.output_ref) {
                task.reserved_usd = Some(*usd);
                task.reserved_month = Some(month.clone());
                task.reservation_id = Some(reservation_id.clone());
            }
            if let Some(kind) = transition.failure_kind {
                let attempts_after = task.attempts.saturating_add(1);
                let policy = retry_policy(kind);
                let retryable = policy.retryable
                    && policy
                        .max_attempts
                        .map(|max| attempts_after < max)
                        .unwrap_or(true);
                task.attempts = attempts_after;
                task.next_retry_at =
                    retryable.then(|| scheduled_retry_at(now, &policy.backoff, attempts_after));
                if retryable {
                    failed_retryable += 1;
                }
            }
            true
        })
        .map_err(pipeline_to_kcs)?;
    Ok(failed_retryable)
}

/// A batch split into free content-addressed reuse and chunks needing an API call.
struct EmbedBatchPlan<'a> {
    /// (chunk, existing content-vector bytes) — link `chunk_vec`, no adapter call.
    reuse: Vec<(&'a EmbeddableChunk, Vec<u8>)>,
    /// One adapter item per content identity, fanned out to every member chunk.
    to_send: Vec<EmbeddingSendGroup<'a>>,
}

#[derive(Clone)]
struct EmbeddingSendGroup<'a> {
    embedding_hash: String,
    representative: &'a EmbeddableChunk,
    members: Vec<&'a EmbeddableChunk>,
}

impl<'a> EmbedBatchPlan<'a> {
    fn send_chunks(&'a self) -> impl Iterator<Item = &'a EmbeddableChunk> + 'a {
        self.to_send
            .iter()
            .flat_map(|group| group.members.iter().copied())
    }

    fn send_count(&self) -> usize {
        self.to_send.iter().map(|group| group.members.len()).sum()
    }
}

/// Classify a batch into reuse vs. to-send by probing the content-addressed
/// `embeddings` store (CT3-EMBED-006). No writes, no adapter calls.
fn plan_embed_batch<'a>(
    conn: &Connection,
    profile: &DeclaredEmbeddingProfile,
    batch: &'a [EmbeddableChunk],
) -> std::result::Result<EmbedBatchPlan<'a>, TaskExecutionFailure> {
    let mut reuse = Vec::new();
    let mut missing = BTreeMap::<String, Vec<&EmbeddableChunk>>::new();
    for chunk in batch {
        let embedding_hash =
            chunk_embedding_hash(chunk, profile).map_err(|_| TaskExecutionFailure {
                retry_kind: RetryErrorKind::ContractViolation,
            })?;
        match embedding_store::content_vector(conn, &embedding_hash) {
            Ok(Some(bytes)) => reuse.push((chunk, bytes)),
            Ok(None) => missing.entry(embedding_hash).or_default().push(chunk),
            Err(_) => {
                return Err(TaskExecutionFailure {
                    retry_kind: RetryErrorKind::ContractViolation,
                })
            }
        }
    }
    let to_send = missing
        .into_iter()
        .map(|(embedding_hash, members)| EmbeddingSendGroup {
            representative: members[0],
            embedding_hash,
            members,
        })
        .collect();
    Ok(EmbedBatchPlan { reuse, to_send })
}

/// Link `chunk_vec` for reuse hits (content vector already stored, no adapter).
fn link_reused_chunks(
    conn: &Connection,
    profile: &DeclaredEmbeddingProfile,
    reuse: &[(&EmbeddableChunk, Vec<u8>)],
) -> std::result::Result<(), TaskExecutionFailure> {
    for (chunk, bytes) in reuse {
        embedding_store::link_chunk_vec(conn, &chunk.chunk_id, bytes, profile.dimensions).map_err(
            |_| TaskExecutionFailure {
                retry_kind: RetryErrorKind::ContractViolation,
            },
        )?;
    }
    Ok(())
}

/// Call the adapter for the to-send chunks and write `embeddings` + `chunk_vec`.
fn send_embed_batch(
    conn: &Connection,
    execution: AdoptedEmbeddingExecution,
    profile: &DeclaredEmbeddingProfile,
    to_send: &[EmbeddingSendGroup<'_>],
) -> std::result::Result<(), TaskExecutionFailure> {
    let items = to_send
        .iter()
        .map(|group| EmbeddingItem {
            id: group.representative.chunk_id.clone(),
            text: Some(group.representative.text.clone()),
            path: None,
            mime: None,
        })
        .collect::<Vec<_>>();
    let vectors = run_embedding_adapter(execution, items, EmbeddingInputType::MarkdownChunk)?;
    let by_id = vectors
        .into_iter()
        .map(|vector| (vector.id, vector.vector))
        .collect::<BTreeMap<_, _>>();
    let held = BTreeSet::new();
    for group in to_send {
        let chunk = group.representative;
        let Some(vector) = by_id.get(&chunk.chunk_id) else {
            return Err(TaskExecutionFailure {
                retry_kind: RetryErrorKind::ContractViolation,
            });
        };
        let bytes = f32_to_le_bytes(vector);
        embedding_store::write_chunk_embedding(
            conn,
            &group.embedding_hash,
            &chunk.text_hash,
            &chunk.chunk_id,
            &bytes,
            profile.dimensions,
            &profile.distance,
            &profile.modality,
            &profile.profile_hash,
        )
        .map_err(|_| TaskExecutionFailure {
            retry_kind: RetryErrorKind::ContractViolation,
        })?;
        embedding_store::link_chunk_vecs_to_content_vector(
            conn,
            &group.embedding_hash,
            group.members.iter().map(|member| member.chunk_id.as_str()),
            &held,
        )
        .map_err(|_| TaskExecutionFailure {
            retry_kind: RetryErrorKind::ContractViolation,
        })?;
    }
    Ok(())
}

/// L2(ii)/L7 target selection: drop chunks whose embedding task must not run in
/// this pass — a sticky budget-Paused task (unless `override_budget`), or a Failed
/// task that is not retry-eligible (unelapsed `next_retry_at`, or non-retryable /
/// attempts exhausted). Failed retry-eligible tasks are left in; `batch retry`
/// resets them to Pending before the pass so they flow through normally.
fn filter_embeddable_by_task_state(
    task_store: &TaskStore,
    pending: Vec<EmbeddableChunk>,
    override_budget: bool,
) -> Result<Vec<EmbeddableChunk>> {
    let tasks = task_store.all().map_err(pipeline_to_kcs)?;
    let mut by_ref = BTreeMap::<String, Vec<&TaskDescriptor>>::new();
    for task in tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
    {
        by_ref
            .entry(task.output_ref.clone())
            .or_default()
            .push(task);
    }
    Ok(pending
        .into_iter()
        .filter(|chunk| {
            let output_ref = embedding_task_output_ref(&chunk.chunk_id);
            match by_ref.get(&output_ref) {
                Some(tasks) => tasks
                    .iter()
                    .filter(|task| task.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE))
                    .all(|task| embeddable_task_state(task, override_budget)),
                // No task row yet (should not happen post-enqueue): embed it.
                None => true,
            }
        })
        .collect())
}

/// Whether an embedding task's current state permits embedding its chunk now.
fn embeddable_task_state(task: &TaskDescriptor, override_budget: bool) -> bool {
    match task.status {
        TaskStatus::Paused => match task.fallback_reason.as_deref() {
            // Sticky budget pause (L2 ii): only an explicit override re-includes it.
            Some("budget_exceeded") => override_budget,
            // R21-1: a secrets hold must NEVER be re-driven into the send pipeline by a
            // sendable chunk (e.g. a non-secret content-twin whose JOIN fan-out shares
            // this held task's output_ref) — only `--send-secrets` (which flips the task
            // back to Pending via `release_secret_holds`) may. Defense-in-depth behind
            // the R21-1 JOIN dedup so the hold cannot be bypassed even if a same
            // output_ref collision re-appears from another source.
            Some(SECRETS_TIER_B_HOLD) => false,
            // Any other Paused reason is safe to re-drive.
            _ => true,
        },
        // Failed embeddings are owned by `batch retry` (L7): skip unless the
        // backoff has elapsed AND the error is still retryable.
        TaskStatus::Failed => task_retry_due(task) && task_retry_allowed(task),
        _ => true,
    }
}

/// Embedding identity hash (03 §8.1) keyed on the chunk's `text_hash` so identical
/// content shares one `embeddings` row (content-based reuse).
fn chunk_embedding_hash(
    chunk: &EmbeddableChunk,
    profile: &DeclaredEmbeddingProfile,
) -> Result<String> {
    embedding_store::embedding_hash(
        EmbeddingTargetType::Chunk,
        &chunk.text_hash,
        profile.dimensions,
        EmbeddingDistance::Cosine,
        EmbeddingModality::Multimodal,
        &profile.profile_hash,
    )
    .map_err(index_to_kcs)
}

/// Cost estimate for embedding `chars` of text: ~4 chars/token, $0.15 per 1M
/// tokens, consistent with the 07 §5.3 fixed adopted-profile budget figure.
fn estimate_embedding_cost(chars: u64) -> f64 {
    let tokens = chars as f64 / 4.0;
    tokens / 1_000_000.0 * 0.15
}

/// Retained current-config chunks that have no usable current-profile vector.
fn retained_chunks_without_embedding(
    conn: &Connection,
    candidates: Vec<EmbeddableChunk>,
    profile: &DeclaredEmbeddingProfile,
) -> Result<Vec<EmbeddableChunk>> {
    let mut existing_stmt = conn
        .prepare("SELECT chunk_id FROM chunk_vec")
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let existing = existing_stmt
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|err| KcsError::schema(err.to_string()))?
        .collect::<std::result::Result<BTreeSet<String>, _>>()
        .map_err(|err| KcsError::schema(err.to_string()))?;
    drop(existing_stmt);

    let mut pending = Vec::new();
    for chunk in candidates {
        let embedding_hash = chunk_embedding_hash(&chunk, profile)?;
        let has_current_profile = embedding_store::content_vector(conn, &embedding_hash)
            .map_err(index_to_kcs)?
            .is_some();
        if has_current_profile && existing.contains(&chunk.chunk_id) {
            continue;
        }
        pending.push(chunk);
    }
    Ok(pending)
}

fn embedding_task_output_ref(chunk_id: &str) -> String {
    format!("embedding:{chunk_id}")
}

/// R12-3: complete embedding tasks stranded `Pending`/`Running` by a crash between
/// the per-batch `chunk_vec` commit and the deferred task-store write-back (R11-5).
/// A chunk that already carries its embedding is "live but not in `pending`" — so
/// `live_chunks_without_embedding` never revisits it and no recovery command
/// (index / batch resume/retry / repair) ever reconciles its task, leaving
/// `index_status` reporting phantom pending enrichment permanently. Mark such tasks
/// `Done` (idempotent, no adapter call, no re-charge — the vector is already stored,
/// so search/data are unaffected; only task accounting + the Agent contract heal).
struct EmbeddingReconcileContext<'a> {
    active_chunk_ids: &'a BTreeSet<String>,
    pending: &'a [EmbeddableChunk],
    now: &'a str,
    allow_auth_revive: bool,
}

fn reconcile_committed_embedding_tasks(
    repo: &Repository,
    task_store: &TaskStore,
    context: EmbeddingReconcileContext<'_>,
) -> Result<()> {
    let pending_ids: BTreeSet<&str> = context
        .pending
        .iter()
        .map(|chunk| chunk.chunk_id.as_str())
        .collect();
    let live_ids = context.active_chunk_ids;
    // R18-1: reclaim the F8 phantom of a NON-LIVE embedding task whose send failed
    // RateLimit/Quota. Embedding charges before the send (like markdownize, F8) but had NO
    // reclaim path — `reserved_usd`/`reserved_month` are now stamped at charge time
    // (apply_embedding_transitions), and once the chunk is edited/deleted (non-live) the
    // task can never be retried, so its non-billable (RateLimit/Quota) phantom would eat
    // the embedding per-adapter/device cap for the rest of the month and falsely pause
    // unrelated embeddings — the embedding twin of the markdownize R17-3/R18-2 fix. This
    // in-place pass runs BEFORE the transitions loop below (which then re-reads and skips
    // these now-terminal tasks). Only Pending/Running/Failed STAMPED tasks are eligible: a
    // Done task's stamp is REAL spend (its vector is stored), never a phantom. A
    // NetworkError stamp is terminalized but NOT reclaimed (may have billed; R16-7). The
    // reclaim uses the task's stamped `reserved_month`, so month accounting matches the
    // charge.
    let reservation_scope_id = repo.scope_id_for_adapter();
    #[derive(Clone, Copy)]
    enum ReconcileReservationAction {
        Revive,
        Complete,
        Retire,
    }
    let mut actions = BTreeMap::<String, ReconcileReservationAction>::new();
    let mut reclaims: Vec<MonthlyCostLedgerEntry> = Vec::new();
    let cost_ledger = CostLedger::new(cost_ledger_path());
    for task in task_store.all().map_err(pipeline_to_kcs)? {
        if task.task_type != TaskType::Embedding {
            continue;
        }
        let budget_paused = task.status == TaskStatus::Paused
            && task.fallback_reason.as_deref() == Some("budget_exceeded");
        if !budget_paused
            && !matches!(
                task.status,
                TaskStatus::Pending | TaskStatus::Running | TaskStatus::Failed
            )
        {
            continue;
        }
        let auth_revive_candidate = context.allow_auth_revive
            && task.status == TaskStatus::Failed
            && retry_kind_from_reason(task.fallback_reason.as_deref()) == RetryErrorKind::AuthError;
        let Some(chunk_id) = task.output_ref.strip_prefix("embedding:") else {
            continue;
        };
        let live = live_ids.contains(chunk_id);
        let live_embedded = live && !pending_ids.contains(chunk_id);
        let materialized_completion =
            live_embedded && task_can_complete_from_materialized_output(&task);
        if task.reservation_claim().is_none()
            && !auth_revive_candidate
            && !budget_paused
            && !materialized_completion
        {
            continue;
        }
        let action = if live && !live_embedded {
            if auth_revive_candidate {
                ReconcileReservationAction::Revive
            } else {
                continue;
            }
        } else if live_embedded {
            ReconcileReservationAction::Complete
        } else {
            ReconcileReservationAction::Retire
        };
        if let Some(entry) = settle_task_reservation(
            &cost_ledger,
            &task,
            &reservation_scope_id,
            EMBEDDING_ADAPTER_KIND,
        )? {
            reclaims.push(entry);
        }
        actions.insert(task.task_id.clone(), action);
    }
    task_store
        .update_matching(|task| {
            let Some(action) = actions.get(&task.task_id).copied() else {
                return false;
            };
            task.clear_reservation();
            match action {
                ReconcileReservationAction::Revive => {
                    task.status = TaskStatus::Pending;
                    task.fallback_reason = None;
                    task.attempts = 0;
                    task.next_retry_at = None;
                    task.heartbeat_at = None;
                }
                ReconcileReservationAction::Complete => {
                    task.status = TaskStatus::Done;
                    task.fallback_reason = Some("embedding_adapter_done".to_owned());
                    task.next_retry_at = None;
                    task.heartbeat_at = None;
                }
                ReconcileReservationAction::Retire => retire_online_task(task),
            }
            true
        })
        .map_err(pipeline_to_kcs)?;
    if !reclaims.is_empty() {
        let reclaim_ledger = cost_ledger.reclaim_ledger();
        for entry in &reclaims {
            reclaim_ledger
                .append_monthly(entry)
                .map_err(pipeline_to_kcs)?;
        }
    }
    let mut transitions: BTreeMap<String, EmbeddingTransition> = BTreeMap::new();
    for task in task_store.all().map_err(pipeline_to_kcs)? {
        if task.task_type != TaskType::Embedding {
            continue;
        }
        // R22-3: `Paused` (a `secrets_tier_b_hold`, or a sticky `budget_exceeded`) was the
        // ONE status this non-live sweep never visited, so a held chunk that was later
        // edited or deleted left its task Paused forever — `compute_index_status` counts it
        // as pending enrichment, so editing a Tier B file N times accreted N orphan holds
        // and monotonically decayed `enriched_ratio`. Admit Paused here; the `paused` guard
        // below keeps it out of the Done arm (a hold was never sent, so it must never be
        // reported as embedded).
        let paused = matches!(task.status, TaskStatus::Paused);
        if !matches!(
            task.status,
            TaskStatus::Pending | TaskStatus::Running | TaskStatus::Paused
        ) {
            continue;
        }
        let Some(chunk_id) = task.output_ref.strip_prefix("embedding:") else {
            continue;
        };
        // A genuinely un-embedded LIVE chunk stays pending (real outstanding work).
        if pending_ids.contains(chunk_id) {
            continue;
        }
        // R15-7: the chunk is NOT live at HEAD — the file was deleted or re-chunked
        // (a new gen), so this task's chunk no longer exists. It can never be driven to
        // completion (`live_chunks_without_embedding` never revisits it), so leaving it
        // Pending/Running permanently pollutes `index_status`/`status.tasks` with phantom
        // pending enrichment. Terminalize it — but REVERSIBLY (R19-3 `retired_non_live`):
        // no adapter call, no re-charge; and if the exact chunk_id later reappears
        // (git revert / restore), the enqueue guard re-creates a fresh task instead of
        // this being a permanent silent hole in vector search.
        if !live_ids.contains(chunk_id) {
            transitions.insert(
                task.output_ref.clone(),
                embedding_retired_non_live_transition(),
            );
            continue;
        }
        // R22-3: a LIVE Paused task keeps its pause. Reaching here means the chunk is live
        // and already has a vector (its content-hash twin was embedded), but a held chunk's
        // text was never sent — marking it `embedding_adapter_done` would both fake the
        // audit trail and let `release_secret_holds` find nothing to release.
        if paused {
            continue;
        }
        // Live AND already embedded (live but NOT pending) → complete it (R12-3).
        transitions.insert(task.output_ref.clone(), embedding_done_transition());
    }
    // No fresh reservations to stamp on the reconcile path (it charges nothing).
    apply_embedding_transitions(task_store, &transitions, context.now, &BTreeMap::new())?;
    Ok(())
}

/// N1a: enqueue a held `Embedding` task (Paused `secrets_tier_b_hold`) per Tier B
/// chunk that lacks one, so the hold is visible in `kcs status` without ever
/// entering the send pipeline. Idempotent — a chunk that already has an embedding
/// task (held or otherwise) is left untouched.
fn hold_secret_embedding_tasks(
    task_store: &TaskStore,
    repo: &Repository,
    held: &[EmbeddableChunk],
    now: &str,
) -> Result<()> {
    if held.is_empty() {
        return Ok(());
    }
    let all_tasks = task_store.all().map_err(pipeline_to_kcs)?;
    // R22-2: `existing` used to mean "any non-retired task ⇒ already classified", which
    // silently assumed a chunk's secret classification never changes after its task is
    // created. It does: renaming a plain file INTO a Tier B name (`notes.md` →
    // `credentials_backup.md`) re-partitions the chunk into `held` on the very next index
    // (the partition reads the live `te.path`, R20-1), yet this guard skipped the demotion,
    // so the task stayed Pending/`network_opt_in_required` forever while `quarantine.jsonl`
    // recorded a "hold". Nothing was ever sent (the send set is recomputed from content each
    // pass), but the N1a disclosure contract broke and no recovery command converged.
    // Only an ALREADY-HELD task means "correctly classified"; everything else is demoted.
    let already_held = all_tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .filter(|task| {
            task.status == TaskStatus::Paused
                && task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD)
        })
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    // A `Done` task's vector is real spend that already exists in `embeddings`; demoting it
    // to a hold would fake outstanding work and strand the stored vector. R20-10 keeps the
    // held chunk out of `chunk_vec`, which is the disclosure that matters here.
    let done = all_tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .filter(|task| task.status == TaskStatus::Done)
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    // R21-7: a task retired because its chunk went non-live must NOT block a fresh HOLD
    // when the content-addressed chunk_id reappears under a Tier B name (git revert /
    // restore of the exact bytes). `enqueue_embedding_tasks` (the sendable sibling) got
    // this R19-3/R20-2 revive; the held branch was left behind, so a restored-under-a-
    // secret-name chunk got no hold task — invisible in `index_status` (R20-7 excludes
    // retired_non_live) and re-embeddable only via `--send-secrets`.
    let revivable = all_tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .filter(|task| task.fallback_reason.as_deref() == Some(RETIRED_NON_LIVE))
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    let existing_nonretired = all_tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .filter(|task| task.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE))
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    // A secret hold is a policy overlay, not permission to erase a terminal retry
    // decision. Preserve non-retryable and exhausted failures in place so a
    // hold/unhold cycle cannot turn them back into fresh sendable work.
    let terminal_failed = all_tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .filter(|task| {
            task.status == TaskStatus::Failed
                && task.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE)
                && !task_retry_allowed(task)
        })
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    // Live, non-retired, not-yet-held, not Done → demote in place to a Paused hold.
    let demotable = all_tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .filter(|task| {
            task_can_enter_secret_hold(task)
                && !already_held.contains(&task.output_ref)
                && !done.contains(&task.output_ref)
                && !terminal_failed.contains(&task.output_ref)
                && task.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE)
        })
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    let mut to_revive: BTreeSet<String> = BTreeSet::new();
    // Demoted holds carry the chunk's CURRENT (secret) path, so `kcs status` names the file
    // that is actually being held rather than whatever it was called when first indexed.
    let mut to_demote: BTreeMap<String, String> = BTreeMap::new();
    for chunk in held {
        let output_ref = embedding_task_output_ref(&chunk.chunk_id);
        if already_held.contains(&output_ref) || done.contains(&output_ref) {
            continue;
        }
        if revivable.contains(&output_ref) {
            to_revive.insert(output_ref);
            continue;
        }
        if terminal_failed.contains(&output_ref) {
            continue;
        }
        if demotable.contains(&output_ref) {
            to_demote.insert(output_ref, chunk.raw_path.clone());
            continue;
        }
        if existing_nonretired.contains(&output_ref) {
            continue;
        }
        let task = TaskDescriptor {
            task_id: format!("task_{}", new_ulid(repo.root())),
            task_type: TaskType::Embedding,
            mode: None,
            input_path: chunk.raw_path.clone(),
            input_hash: chunk.text_hash.clone(),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: vec![chunk.chunk_id.clone()],
            output_ref,
            unit_keys: None,
            status: TaskStatus::Paused,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: Some(SECRETS_TIER_B_HOLD.to_owned()),
            created_at: now.to_owned(),
            bbox_annotation_enabled: None,
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        };
        task_store.append(&task).map_err(pipeline_to_kcs)?;
    }
    // Revive retired-non-live tasks in place to a Paused hold, reusing their slot so no
    // duplicate output_ref is created. Their `reserved_*` were cleared at retirement.
    if !to_revive.is_empty() {
        task_store
            .update_matching(|task| {
                if task.task_type == TaskType::Embedding
                    && task.fallback_reason.as_deref() == Some(RETIRED_NON_LIVE)
                    && to_revive.contains(&task.output_ref)
                {
                    task.status = TaskStatus::Paused;
                    task.fallback_reason = Some(SECRETS_TIER_B_HOLD.to_owned());
                    task.attempts = 0;
                    task.next_retry_at = None;
                    task.heartbeat_at = None;
                    task.clear_reservation();
                    true
                } else {
                    false
                }
            })
            .map_err(pipeline_to_kcs)?;
    }
    // R22-2: demote an existing non-held task (Pending / Running / Failed / budget-Paused)
    // whose chunk is now classified secret. The hold takes precedence over budget and
    // network reasons (the same precedence `enqueue_online_placeholder_task` applies at
    // creation). A demoted task's kept F8 reservation now buys nothing — its send is
    // blocked by the hold — so reclaim it under the established error-kind policy
    // (RateLimit/Quota/Auth are non-billable ⇒ reclaimable; a NetworkError stamp may have
    // billed server-side, so it is conservatively retained: R16-7).
    if !to_demote.is_empty() {
        let reservation_scope_id = repo.scope_id_for_adapter();
        let mut reclaims: Vec<MonthlyCostLedgerEntry> = Vec::new();
        let cost_ledger = CostLedger::new(cost_ledger_path());
        for task in &all_tasks {
            if task.task_type == TaskType::Embedding && to_demote.contains_key(&task.output_ref) {
                if let Some(entry) = settle_task_reservation(
                    &cost_ledger,
                    task,
                    &reservation_scope_id,
                    EMBEDDING_ADAPTER_KIND,
                )? {
                    reclaims.push(entry);
                }
            }
        }
        task_store
            .update_matching(|task| {
                if task.task_type != TaskType::Embedding {
                    return false;
                }
                let Some(current_path) = to_demote.get(&task.output_ref) else {
                    return false;
                };
                task.clear_reservation();
                task.status = TaskStatus::Paused;
                task.fallback_reason = Some(SECRETS_TIER_B_HOLD.to_owned());
                task.input_path = current_path.clone();
                task.attempts = 0;
                task.next_retry_at = None;
                task.heartbeat_at = None;
                true
            })
            .map_err(pipeline_to_kcs)?;
        if !reclaims.is_empty() {
            let reclaim_ledger = cost_ledger.reclaim_ledger();
            for entry in &reclaims {
                reclaim_ledger
                    .append_monthly(entry)
                    .map_err(pipeline_to_kcs)?;
            }
        }
    }
    Ok(())
}

/// Enqueue one Pending `Embedding` task per pending chunk, skipping chunks that
/// already have any embedding task (idempotent re-index).
fn enqueue_embedding_tasks(
    task_store: &TaskStore,
    repo: &Repository,
    pending: &[EmbeddableChunk],
    online: bool,
    now: &str,
) -> Result<()> {
    let all_tasks = task_store.all().map_err(pipeline_to_kcs)?;
    // R22-1: a Paused `secrets_tier_b_hold` must not block this enqueue either. Reaching
    // `enqueue_embedding_tasks` means the chunk landed in `sendable`, i.e. NO live path of
    // it is secret (the R21-1 dedup prefers a secret path, so one live secret path would
    // have kept the survivor in `held`) or the scope is `--send-secrets`-approved. The hold
    // is therefore stale: the file was renamed out of a Tier B name, or its secret twin was
    // deleted. Before this, `existing` swallowed the hold and `embeddable_task_state`
    // (R21-1's defense-in-depth) refused to re-drive it, so the chunk fell out of vector
    // search permanently — recoverable only via `--send-secrets`, which persists a
    // scope-wide approval to send every candidate secret. Release it in place instead.
    let hold_revivable = all_tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .filter(|task| {
            task.status == TaskStatus::Paused
                && task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD)
        })
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    let existing = all_tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        // R19-3: a task retired because its chunk went non-live must NOT block a fresh
        // enqueue when the content-addressed chunk_id reappears (git revert / restore of
        // the exact bytes). Excluding it here lets a genuinely-live-again chunk be
        // re-embedded instead of being silently stuck out of vector search forever.
        .filter(|task| task.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE))
        .filter(|task| !hold_revivable.contains(&task.output_ref))
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    // R20-2: output_refs of retired-non-live tasks eligible to be REVIVED IN PLACE. R19-3
    // let a reappearing chunk enqueue past its retired task, but appending a NEW task left
    // the old retired one behind — TWO tasks sharing one `output_ref`. Because
    // `apply_embedding_transitions` and `reconcile_committed_embedding_tasks` key on
    // `output_ref` (not `task_id`), a later rate_limit send re-stamped BOTH and reconcile
    // then reclaimed the single phantom TWICE — a silent per-adapter cap under-count
    // (fail-open) that accumulated each revert cycle. Reviving the existing retired task in
    // place keeps exactly one task per output_ref, so no double-stamp / double-reclaim.
    let revivable = all_tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .filter(|task| task.fallback_reason.as_deref() == Some(RETIRED_NON_LIVE))
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    let reason = if online {
        "ready_for_online_adapter"
    } else {
        "network_opt_in_required"
    };
    let mut to_revive: BTreeSet<String> = BTreeSet::new();
    // R22-1: released holds, mapped to the chunk's CURRENT (non-secret) path so the task's
    // `input_path` stops naming the file it was held under.
    let mut to_unhold: BTreeMap<String, String> = BTreeMap::new();
    for chunk in pending {
        let output_ref = embedding_task_output_ref(&chunk.chunk_id);
        if existing.contains(&output_ref) {
            continue;
        }
        if hold_revivable.contains(&output_ref) {
            to_unhold.insert(output_ref, chunk.raw_path.clone());
            continue;
        }
        if revivable.contains(&output_ref) {
            to_revive.insert(output_ref);
            continue;
        }
        let task = TaskDescriptor {
            task_id: format!("task_{}", new_ulid(repo.root())),
            task_type: TaskType::Embedding,
            mode: None,
            input_path: chunk.raw_path.clone(),
            input_hash: chunk.text_hash.clone(),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: vec![chunk.chunk_id.clone()],
            output_ref,
            unit_keys: None,
            status: TaskStatus::Pending,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: Some(reason.to_owned()),
            created_at: now.to_owned(),
            bbox_annotation_enabled: None,
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        };
        task_store.append(&task).map_err(pipeline_to_kcs)?;
    }
    // Revive retired-non-live tasks in place (Failed -> Pending), reusing their slot so no
    // duplicate output_ref is created. Their `reserved_*` were cleared at retirement, so
    // the revived task carries no phantom reservation.
    if !to_revive.is_empty() {
        task_store
            .update_matching(|task| {
                if task.task_type == TaskType::Embedding
                    && task.fallback_reason.as_deref() == Some(RETIRED_NON_LIVE)
                    && to_revive.contains(&task.output_ref)
                {
                    task.status = TaskStatus::Pending;
                    task.fallback_reason = Some(reason.to_owned());
                    task.attempts = 0;
                    task.next_retry_at = None;
                    task.heartbeat_at = None;
                    task.clear_reservation();
                    true
                } else {
                    false
                }
            })
            .map_err(pipeline_to_kcs)?;
    }
    // R22-1: release stale secrets holds in place (Paused -> Pending). The hold carried no
    // reservation (`main.rs` hold creation stamps none), so there is nothing to reclaim.
    // `embeddable_task_state`'s `SECRETS_TIER_B_HOLD => false` guard stays untouched: a hold
    // is still never re-driven while it IS a hold — it is cleared here only because the
    // content-addressed partition just proved the chunk has no live secret path.
    if !to_unhold.is_empty() {
        task_store
            .update_matching(|task| {
                if task.task_type == TaskType::Embedding
                    && task.status == TaskStatus::Paused
                    && task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD)
                {
                    let Some(current_path) = to_unhold.get(&task.output_ref) else {
                        return false;
                    };
                    task.status = TaskStatus::Pending;
                    task.fallback_reason = Some(reason.to_owned());
                    task.input_path = current_path.clone();
                    task.attempts = 0;
                    task.next_retry_at = None;
                    task.heartbeat_at = None;
                    true
                } else {
                    false
                }
            })
            .map_err(pipeline_to_kcs)?;
    }
    Ok(())
}

// R11-5: the per-batch `update_embedding_tasks` / `complete_` / `pause_` /
// `fail_embedding_tasks` helpers were removed — each did a full tasks.jsonl
// all()+replace_all, and calling them once per 32-chunk batch was the O(N²) hang.
// The enrichment loop now accumulates `EmbeddingTransition`s and writes them back
// once via `apply_embedding_transitions`.

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
        // R19-3: a non-live retirement is non-retryable as the old task (like
        // invalid_input), but the enqueue guards treat it as non-blocking so the
        // content-addressed identity can be re-enqueued if it reappears.
        Some(RETIRED_NON_LIVE) => RetryErrorKind::InvalidInput,
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

/// R19-2: an online-send failure carrying an F8 reservation (a NON-billable phantom for
/// RateLimit/Quota/Auth, possibly-billed for NetworkError). A retire+reclaim supersede/sweep
/// must target these REGARDLESS of retry-attempt exhaustion: QuotaExceeded exhausts its
/// finite `max_attempts` (unlike RateLimit's unlimited), so gating on `task_retry_allowed`
/// left an exhausted-quota phantom reservation stuck for the month — never reclaimed,
/// starving the per-adapter cap and falsely pausing legitimate tasks. R20-3: AuthError is
/// included for the same reason — it is non-retryable (`max_attempts:0`) so `task_retry_allowed`
/// excluded it, leaving its (non-billable, 401/403) phantom orphaned; the sweep must retire it
/// so `reclaim_entry_for` can cancel the phantom. The reclaim itself stays error-kind-aware
/// inside `reclaim_entry_for` (RateLimit/Quota/Auth reclaim; NetworkError retires but keeps
/// its reservation as it may have billed). A `retired_non_live` task maps to InvalidInput
/// here, so it is excluded (idempotent).
fn is_reservation_bearing_send_failure(task: &TaskDescriptor) -> bool {
    matches!(
        retry_kind_from_reason(task.fallback_reason.as_deref()),
        RetryErrorKind::RateLimit
            | RetryErrorKind::QuotaExceeded
            | RetryErrorKind::NetworkError
            | RetryErrorKind::AuthError
    )
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

fn estimate_online_markdownize_cost(size_bytes: u64, bbox_annotation_enabled: bool) -> f64 {
    let unannotated = estimate_local_baseline_cost(size_bytes) * 10.0;
    if bbox_annotation_enabled {
        unannotated * 1.25
    } else {
        unannotated
    }
}

fn media_type_for_cli_path(path: &Path) -> &'static str {
    // R21-4: lowercase the extension so an uppercase-extension text-native file
    // (`README.MD`, `NOTE.TXT`, `MAIN.RS`) is recognized as text/markdown/plain/code and
    // handled locally — not folded to octet-stream and shipped to online OCR (R9-2).
    match path
        .extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "md" | "markdown" => "text/markdown",
        "txt" => "text/plain",
        "rs" | "py" | "js" | "ts" | "go" | "java" | "c" | "h" | "cpp" => "text/x-code",
        "pdf" => "application/pdf",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        // R20-6: recognize OOXML office documents by their real MIME so they are treated as
        // non-text-native (routed to online OCR), not folded into octet-stream and given a
        // raw-bytes local passthrough that evidences the ZIP bytes as searchable text.
        "docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx" => "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        _ => "application/octet-stream",
    }
}

/// R9-2: whether `media_type` is text-native (Markdown / plain text / code) — the
/// deterministic Adapter's domain (docs/07 §2.1). Text-native files are
/// markdownized locally and must never enqueue an online Mistral-OCR task: docs/07
/// §5.2 scopes the standard online Adapter to *non*-text-native PDF / DOCX / PPTX /
/// images. Sending a text file to OCR shipped its raw bytes to a third-party API
/// (privacy) and billed ~10x the baseline for work the deterministic pass already
/// did (redundant, and orphaned by F6).
fn is_text_native_media(media_type: &str) -> bool {
    matches!(media_type, "text/markdown" | "text/plain" | "text/x-code")
}

fn budget_status_json(repo: &Repository) -> Result<Value> {
    let caps = read_budget_policy(user_config_toml_path(), repo.kcs_dir().join("config.toml"))
        .map_err(pipeline_to_kcs)?;
    let now = now_utc_seconds();
    let month = utc_month(&now);
    let ledger = CostLedger::new(cost_ledger_path());
    let scope_id = repo.scope_id_for_adapter();
    // R18-3: report NET spend (charges − reclaimed phantoms), matching the enforcement
    // gate `budget_remaining_for_adapter`. Reading gross here made `kcs status`
    // over-report spend / under-report remaining after a reclaim.
    let device_spent = net_monthly_spent(&ledger, &month, None, None)?;
    let folder_spent = net_monthly_spent(&ledger, &month, Some(&scope_id), None)?;
    let device_remaining = caps.device_monthly_usd_cap - device_spent;
    let folder_remaining = caps.folder_monthly_usd_cap.map(|cap| cap - folder_spent);
    let cap_kind = match folder_remaining {
        Some(folder) if folder <= device_remaining => BudgetCapKind::Folder,
        _ => BudgetCapKind::Device,
    };
    // F5: surface the non-blocking `warn_at_percent` warning and the active
    // policy (hard_stop / warn_at_percent) alongside the numbers.
    let warning = budget_warning(&caps, device_spent, folder_spent);
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
        "hard_stop": caps.hard_stop,
        "warn_at_percent": caps.warn_at_percent,
        "warned": warning.is_some(),
        "warning": warning,
    }))
}

/// F5: the current scope's non-blocking budget warning (or `None`), for embedding
/// in `index` / `batch` result JSON. Reads the caps and this month's ledger totals.
fn scope_budget_warning(repo: &Repository) -> Result<Option<String>> {
    let caps = read_budget_policy(user_config_toml_path(), repo.kcs_dir().join("config.toml"))
        .map_err(pipeline_to_kcs)?;
    let month = utc_month(&now_utc_seconds());
    let ledger = CostLedger::new(cost_ledger_path());
    let scope_id = repo.scope_id_for_adapter();
    // R18-3: NET spend (charges − reclaimed), matching enforcement, so the warning
    // does not fire on a reclaimed phantom.
    let device_spent = net_monthly_spent(&ledger, &month, None, None)?;
    let folder_spent = net_monthly_spent(&ledger, &month, Some(&scope_id), None)?;
    Ok(budget_warning(&caps, device_spent, folder_spent))
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
    normalize_by_path: BTreeMap<String, PendingNormalizeRef>,
    network_allowed: bool,
    pending_online_tasks: usize,
    paused_tasks: usize,
    normalized_files: usize,
    pending_files: usize,
    failed_files: usize,
    // R12-2: files larger than adapter.policy.max_input_bytes, skipped for adapter
    // processing (input gate, 07 §7.1.2) but still archived.
    skipped_oversized_files: usize,
    // R22-4: binary inputs with no locally-extractable text whose media type is not an
    // OCR-able one (R21-4 skips their online task). Archived, but never enriched — surfaced
    // so `enriched_ratio: 1.0` cannot silently mean "this file does not exist".
    skipped_unrecognized_binary_files: usize,
}

fn online_output_ref(adapter_id: &str) -> String {
    format!("online:{adapter_id}")
}

fn explicitly_allowed_tier_a_paths(preview: &ScanPreview) -> BTreeSet<String> {
    preview
        .candidates
        .iter()
        .filter(|candidate| {
            !candidate.ignored
                && candidate.quarantine_reason.as_deref() == Some("secrets_tier_a_online_hold")
        })
        .map(|candidate| candidate.input_path.clone())
        .collect()
}

fn online_markdownize_profile() -> AdapterProfile {
    standard_online_markdownize_profile()
}

fn online_markdownize_profile_for(repo: &Repository) -> AdapterProfile {
    standard_online_markdownize_profile_with_bbox(bbox_annotation_enabled(repo))
}

fn adapter_kind_budget_key(kind: AdapterKind) -> &'static str {
    match kind {
        AdapterKind::Prepare => "prepare",
        AdapterKind::Markdownize => "markdown",
        AdapterKind::Embedding => "embedding",
        AdapterKind::Summary => "summary",
        AdapterKind::Classification => "classification",
        AdapterKind::Rerank => "rerank",
    }
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
        _ => builtin_offline_markdownize_adapter(),
    }
}

fn offline_markdownize_from_verified_bytes(
    adapter: &dyn MarkdownizeAdapter,
    request: MarkdownizeRequest,
    verified_raw_bytes: &[u8],
) -> kcs_adapter::Result<kcs_adapter::types::MarkdownizeResponse> {
    if matches!(
        std::env::var("KCS_TEST_MARKDOWNIZE_ADAPTER")
            .ok()
            .as_deref(),
        Some("incremental" | "reject_incremental" | "reject_incremental_and_full")
    ) {
        return adapter.markdownize(request);
    }
    kcs_adapter::deterministic::markdownize_from_bytes(request, verified_raw_bytes)
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
    // Q3: index holds the folder store lock end-to-end, so any Running online task
    // is an orphan from a crashed run. Reclaim it to Pending before the enqueue /
    // dedup pass so it is re-counted as pending_online_tasks (and later re-sent by
    // `batch resume`) rather than being stuck forever in the Running absorbing
    // state — invisible to the pending counter and unrecoverable by any command.
    reclaim_orphaned_running_tasks(&task_store)?;
    let now = now_utc_seconds();
    let scope_id = preview.scope_id.clone();
    let prepare_profile_hash = builtin_prepare_profile().tool_profile_hash;
    let markdown_adapter = active_markdown_adapter(repo);
    let markdown_profile = markdown_adapter.profile();
    let markdown_profile_hash = markdown_profile.tool_profile_hash.clone();
    let network_allowed = network_allowed(repo, args)?;
    let cost_ledger = CostLedger::new(cost_ledger_path());
    let budget_caps =
        read_budget_policy(user_config_toml_path(), repo.kcs_dir().join("config.toml"))
            .map_err(pipeline_to_kcs)?;
    let month = utc_month(&now);

    // R18-2: reclaim phantoms of DELETED / renamed files. R17-3's enqueue supersede
    // reclaims a stale RateLimit/Quota phantom only when the SAME path is re-scanned
    // (`task.input_path == candidate.input_path`); a DELETED or renamed file never
    // reappears as a scan candidate, so its Failed(rate_limit/quota) phantom would eat the
    // per-adapter markdown cap for the rest of the month and falsely pause unrelated tasks
    // (the same harm R17-3 fixed, surviving on the delete path). With the full live-
    // candidate set in hand, retire + reclaim any retryable Failed online markdownize task
    // whose input_path is no longer a live candidate. Runs before the enqueue loop so the
    // freed cap is available to this index's tasks.
    {
        let online_profile = online_markdownize_profile_for(repo);
        let placeholder_output_ref = online_output_ref(&online_profile.adapter_id);
        let markdown_adapter_kind = adapter_kind_budget_key(online_profile.adapter_kind);
        let reservation_scope_id = repo.scope_id_for_adapter();
        let live_paths: BTreeSet<&str> = preview
            .candidates
            .iter()
            .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
            .map(|candidate| candidate.input_path.as_str())
            .collect();
        let mut orphan_reclaims: Vec<MonthlyCostLedgerEntry> = Vec::new();
        let mut orphan_ids = BTreeSet::new();
        for task in task_store.all().map_err(pipeline_to_kcs)? {
            let orphaned = task.task_type == TaskType::Markdownize
                && targets_standard_online_markdownize(
                    task_store.kcs_dir(),
                    &task,
                    &placeholder_output_ref,
                )
                && task.status == TaskStatus::Failed
                && is_reservation_bearing_send_failure(&task)
                && !live_paths.contains(task.input_path.as_str());
            if !orphaned {
                continue;
            }
            if let Some(entry) = settle_task_reservation(
                &cost_ledger,
                &task,
                &reservation_scope_id,
                markdown_adapter_kind,
            )? {
                orphan_reclaims.push(entry);
            }
            orphan_ids.insert(task.task_id);
        }
        task_store
            .update_matching(|task| {
                if !orphan_ids.contains(&task.task_id) {
                    return false;
                }
                retire_online_task(task);
                true
            })
            .map_err(pipeline_to_kcs)?;
        if !orphan_reclaims.is_empty() {
            let reclaim_ledger = cost_ledger.reclaim_ledger();
            for entry in &orphan_reclaims {
                reclaim_ledger
                    .append_monthly(entry)
                    .map_err(pipeline_to_kcs)?;
            }
        }
    }

    let mut result = IndexPipelineResult {
        network_allowed,
        ..IndexPipelineResult::default()
    };
    let unsupported_store = UnsupportedInputStore::new(repo.kcs_dir());
    let mut unsupported_by_path = unsupported_store
        .latest_by_path()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .map(|entry| (entry.path.clone(), entry))
        .collect::<BTreeMap<_, _>>();
    let mut unsupported_paths = unsupported_by_path
        .values()
        .filter(|entry| entry.reason == UNSUPPORTED_REASON_UNRECOGNIZED_BINARY)
        .map(|entry| entry.path.clone())
        .collect::<BTreeSet<_>>();
    // N1a: a Tier B (candidate-secret) file is ingested locally but its online
    // task is held unless the scope carries an explicit `--send-secrets` approval.
    let secrets_approved = secrets_send_approved(repo);
    // R12-2: the documented `adapter.policy.max_input_bytes` input gate (07 §7.1.2 —
    // "KCS 側の入力制御" is an MVP contract). Scope config wins over user config,
    // default 100 MB. A file larger than the cap is never handed to the Markdownize
    // adapter (below); it stays archived but unenriched, and the count is disclosed.
    let max_input_bytes = effective_max_input_bytes(repo);
    // R12-1: the documented `[markdownize.incremental]` overrides (were hardcoded).
    let incremental_config = effective_incremental_config(repo)?;

    for candidate in preview
        .candidates
        .iter()
        .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
    {
        if candidate.size_bytes > max_input_bytes {
            result.skipped_oversized_files += 1;
            append_event_log(
                "KCS-I-INDEX-INPUT-OVERSIZED-001",
                "input file exceeds adapter.policy.max_input_bytes; skipped adapter processing",
                json!({
                    "size_bytes": candidate.size_bytes,
                    "max_input_bytes": max_input_bytes,
                }),
            )?;
            continue;
        }
        // R19-1: hold ANY secret (Tier B, or a lifted Tier A) from online markdownize
        // unless `--send-secrets`. Non-lifted Tier A never reaches this loop (the
        // `!candidate.ignored` filter above skips it), so `.is_some()` newly gates only
        // lifted Tier A.
        let secrets_hold = !secrets_approved && classify_secret(&candidate.input_path).is_some();
        let path = repo.root().join(&candidate.input_path);
        let verified =
            match read_verified_scan_input(repo.root(), &candidate.input_path, max_input_bytes) {
                Ok(verified) => verified,
                Err(error) => {
                    append_event_log(
                        "KCS-I-INDEX-INPUT-CHANGED-001",
                        "input could not be rebound to a regular bounded scope child; skipped",
                        json!({ "input_path": candidate.input_path }),
                    )?;
                    let _ = error;
                    result.failed_files += 1;
                    continue;
                }
            };
        // R15-8: `candidate.raw_hash` was computed at SCAN time; `bytes` is read HERE. If
        // the file was externally edited in that window, persisting the normalized
        // instance under the stale SCAN hash while the closing snapshot hashes the CURRENT
        // bytes for the tree entry would diverge their identities (the offline twin of
        // R14-2). Re-hash what we actually read and, on a mismatch, SKIP this candidate —
        // the next clean index re-scans and normalizes it under its correct identity. The
        // window is one store-lock-held `kcs index` plus an external write, so this is a
        // rare defensive guard. (No deterministic test: reproducing it needs an external
        // edit landing inside the lock-held critical section between the scan and this
        // read, which no public seam exposes.)
        let current_hash = verified.raw_hash.clone();
        if let Some(scan_hash) = &candidate.raw_hash {
            if scan_hash != &current_hash {
                append_event_log(
                    "KCS-I-INDEX-INPUT-CHANGED-001",
                    "input file changed between scan and normalize; skipped to preserve \
                     content-addressing (re-run index)",
                    json!({ "input_path": candidate.input_path }),
                )?;
                result.failed_files += 1;
                continue;
            }
        }
        if !current_scan_policy_allows_file(repo.root(), &candidate.input_path)
            .map_err(pipeline_to_kcs)?
        {
            append_event_log(
                "KCS-I-INDEX-INPUT-POLICY-CHANGED-001",
                "input is no longer authorized by current scope policy; skipped",
                json!({ "input_path": candidate.input_path }),
            )?;
            result.failed_files += 1;
            continue;
        }
        let raw_hash = current_hash;
        // Reject before Prepare/Markdownize writes any derived state. The closing
        // snapshot independently rechecks every staged raw under the store lock.
        ensure_raw_ingest_allowed(repo, &raw_hash)?;
        let prepare = prepare_units_from_bytes(PrepareStageBytesRequest {
            raw_hash: &raw_hash,
            media_type: &candidate.media_type,
            input_path: &path.display().to_string(),
            tool_profile_hash: &prepare_profile_hash,
            bytes: &verified.bytes,
        })
        .map_err(pipeline_to_kcs)?;

        write_prepared_objects(
            repo,
            &prepare.prepared_units,
            &prepare.prepared_object_hashes,
            &verified.bytes,
            &candidate.media_type,
        )?;

        if prepare.prepared_units.is_empty() {
            // R20-5: this media has no locally-extractable text — a text-layer-less/scanned
            // PDF, or (after R20-6) an image / OOXML / unrecognized binary. It needs ONLINE
            // OCR, so route it through the SAME enqueue path as a text-layer PDF's online
            // enhancement: an idempotent task carrying the executable online output_ref,
            // gated by secret / budget / network opt-in. The old branch appended a fixed
            // "pending:scanned_pdf_without_text_layer" output_ref that NO executor consumed
            // (`execute_pending_markdownize_tasks` filters on the online output_ref) and had
            // no idempotency guard (04 §5.5), so it silently duplicated on every idle
            // re-index and the file never reached OCR.
            //
            // R21-4: only a RECOGNIZED OCR-able medium (PDF / image / OOXML — docs/07 §5.2)
            // is worth an online OCR task. An unrecognized `application/octet-stream` binary
            // (a .sqlite, a .zip, a compiled blob) is not a document and can never be OCR'd,
            // so enqueuing one only pollutes pending enrichment forever. Skip it.
            if candidate.media_type != "application/octet-stream" {
                if unsupported_paths.remove(&candidate.input_path) {
                    record_unsupported_if_changed(
                        &unsupported_store,
                        &mut unsupported_by_path,
                        UnsupportedInputDisposition {
                            path: candidate.input_path.clone(),
                            raw_hash: raw_hash.clone(),
                            media_type: candidate.media_type.clone(),
                            size_bytes: verified.size_bytes,
                            reason: UNSUPPORTED_REASON_RESOLVED.to_owned(),
                        },
                    )?;
                }
                enqueue_online_placeholder_task(
                    repo,
                    &task_store,
                    candidate,
                    &raw_hash,
                    &scope_id,
                    network_allowed,
                    secrets_hold,
                    args,
                    &now,
                    &mut result,
                    &cost_ledger,
                    &budget_caps,
                    &month,
                )?;
            } else {
                // R22-4: the R21-4 skip left NO trace — no task, no counter, no event — so a
                // real document whose extension is merely missing from the MIME table (a
                // `.bmp` / `.tiff` / `.heic` image, a legacy `.doc` / `.xls`, an `.epub`)
                // vanished from enrichment while `index_status` still reported
                // `enriched_ratio: 1.0` and `kcs status` showed the file as `unchanged`. The
                // bytes are archived, but nothing is searchable and no recovery command has
                // anything to act on. Disclose it exactly the way the sibling oversized-input
                // gate does: a counter plus an INFO event (no new error code — docs frozen).
                result.skipped_unrecognized_binary_files += 1;
                record_unsupported_if_changed(
                    &unsupported_store,
                    &mut unsupported_by_path,
                    UnsupportedInputDisposition {
                        path: candidate.input_path.clone(),
                        raw_hash: raw_hash.clone(),
                        media_type: candidate.media_type.clone(),
                        size_bytes: verified.size_bytes,
                        reason: UNSUPPORTED_REASON_UNRECOGNIZED_BINARY.to_owned(),
                    },
                )?;
                unsupported_paths.insert(candidate.input_path.clone());
                append_event_log(
                    "KCS-I-INDEX-INPUT-UNRECOGNIZED-BINARY-001",
                    "binary input has no locally-extractable text and no OCR-able media type; archived but not enriched",
                    json!({
                        "media_type": candidate.media_type,
                        "size_bytes": candidate.size_bytes,
                    }),
                )?;
            }
            continue;
        }

        if unsupported_paths.remove(&candidate.input_path) {
            record_unsupported_if_changed(
                &unsupported_store,
                &mut unsupported_by_path,
                UnsupportedInputDisposition {
                    path: candidate.input_path.clone(),
                    raw_hash: raw_hash.clone(),
                    media_type: candidate.media_type.clone(),
                    size_bytes: verified.size_bytes,
                    reason: UNSUPPORTED_REASON_RESOLVED.to_owned(),
                },
            )?;
        }

        let output_ref = normalized_output_ref(repo, &raw_hash, &markdown_profile_hash, 0);
        if task_store
            .done_output_for(&raw_hash, &output_ref)
            .map_err(pipeline_to_kcs)?
            .is_some()
        {
            result.normalize_by_path.insert(
                candidate.input_path.clone(),
                PendingNormalizeRef {
                    expected_raw_hash: raw_hash.clone(),
                    normalize: NormalizeRef {
                        tool_profile_hash: markdown_profile_hash.clone(),
                        gen: 0,
                    },
                },
            );
            result.normalized_files += 1;
            // R21-4: an online OCR "enhancement" task after a SUCCESSFUL local markdownize
            // is only meaningful for a real text-layer PDF (docs/07 §8). A non-`.md`/non-
            // code TEXT file folded to `application/octet-stream` (a `.yaml` / `.json` /
            // `Dockerfile`, or an uppercase-extension text-native file) is already fully and
            // finally handled by the local passthrough — enqueuing an OCR task shipped its
            // bytes to the external API under `--online` (R9-2 routing violation) and, when
            // offline, left a permanent phantom pending that deflated enriched_ratio.
            if candidate.media_type == "application/pdf" {
                enqueue_online_placeholder_task(
                    repo,
                    &task_store,
                    candidate,
                    &raw_hash,
                    &scope_id,
                    network_allowed,
                    secrets_hold,
                    args,
                    &now,
                    &mut result,
                    &cost_ledger,
                    &budget_caps,
                    &month,
                )?;
            }
            continue;
        }

        // R14-1 (defense in depth): loading the prior instance for THIS candidate must
        // not abort the whole index and silently skip alphabetically-later files. On any
        // error (a store read fault, an unreadable prior instance the `Ok(None)` fix
        // above did not already absorb), degrade to no-previous = a Full re-send for this
        // candidate only, keeping the blast radius to the one file.
        let previous =
            previous_instance_for_path(&task_store, &candidate.input_path, &markdown_profile_hash)
                .unwrap_or_else(|_err| {
                    let _ = append_event_log(
                        "KCS-I-INDEX-PREVIOUS-UNREADABLE-001",
                        "prior normalized instance unreadable; indexing this file as Full",
                        json!({ "input_path": candidate.input_path }),
                    );
                    None
                });
        let mapping = if incremental_config.enabled {
            previous
                .as_ref()
                .map(|previous| map_units(&previous.prepared_units, &prepare.prepared_units))
        } else {
            None
        };
        let incremental_hints = mapping
            .as_ref()
            .map(|mapping| incremental_hints_from_mapping(mapping, &prepare.prepared_units))
            .unwrap_or_else(|| all_changed_hints(&prepare.prepared_units));
        // R12-1: `enabled = false` disables incremental entirely — always full mode
        // (05 / docs/10:537). Otherwise the effective threshold / max_consecutive
        // (were hardcoded 0.30 / 5) drive the documented decision.
        let mode_decision = if incremental_config.enabled {
            choose_markdownize_mode(&IncrementalModeInput {
                has_previous_done_run: previous.is_some(),
                raw_hash_only_changed: true,
                adapter_capabilities: markdown_profile.capability_flags.clone(),
                change_rate: mapping
                    .as_ref()
                    .map(|mapping| mapping.change_rate)
                    .unwrap_or(1.0),
                threshold: incremental_config.threshold,
                consecutive_incremental_count: consecutive_incremental_count(
                    &task_store,
                    &candidate.input_path,
                )?,
                max_consecutive_incremental: incremental_config.max_consecutive,
            })
        } else {
            IncrementalModeDecision {
                mode: MarkdownizeMode::Full,
                reason: Some("incremental_disabled".to_owned()),
            }
        };
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
            // Offline (deterministic) markdownize path: the builtin adapter ignores
            // page scoping (R15-5 concerns only the real Mistral client).
            restrict_to_hint_pages: false,
            bbox_annotation_enabled: false,
            tool_profile_hash: markdown_profile_hash.clone(),
            spec_version: 1,
        };

        let mut response = offline_markdownize_from_verified_bytes(
            markdown_adapter.as_ref(),
            request.clone(),
            &verified.bytes,
        )
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
            let fallback_response = offline_markdownize_from_verified_bytes(
                markdown_adapter.as_ref(),
                full_request,
                &verified.bytes,
            )
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
            // The local deterministic markdownize always returns every unit, so this
            // kind is inert here; a hypothetical missing unit would be a
            // non-retryable library/contract fault rather than a transient.
            RetryErrorKind::ContractViolation,
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
            PendingNormalizeRef {
                expected_raw_hash: raw_hash.clone(),
                normalize: NormalizeRef {
                    tool_profile_hash: markdown_profile_hash.clone(),
                    gen: 0,
                },
            },
        );
        result.normalized_files += 1;
        cost_ledger
            .append_monthly(&MonthlyCostLedgerEntry {
                month: month.clone(),
                scope_id: scope_id.clone(),
                adapter_kind: "deterministic_baseline".to_owned(),
                // F1 (04 §5.4): local deterministic markdownize is recorded at unit
                // price 0, so free local indexing never consumes the device/folder
                // USD cap. `device_spent = monthly_total(None)` sums every
                // adapter_kind, so a non-zero baseline cost here would silently pause
                // paid enrichment and inflate `status.budget.device_spent`. The row is
                // still appended (provenance of the baseline work), just at usd = 0.
                usd: 0.0,
            })
            .map_err(pipeline_to_kcs)?;
        // R21-4: only a real text-layer PDF warrants an online OCR "enhancement" task after
        // a successful local markdownize. A TEXT file folded to `application/octet-stream`
        // (`.yaml`/`.json`/`Dockerfile`/uppercase-extension text-native) is fully handled
        // locally; enqueuing OCR sent its bytes online (R9-2 violation) or left an offline
        // phantom pending.
        if candidate.media_type == "application/pdf" {
            enqueue_online_placeholder_task(
                repo,
                &task_store,
                candidate,
                &raw_hash,
                &scope_id,
                network_allowed,
                secrets_hold,
                args,
                &now,
                &mut result,
                &cost_ledger,
                &budget_caps,
                &month,
            )?;
        }
    }
    Ok(result)
}

/// Q2: crash-atomic write of a derived CAS byte object (prepared / image). Writes
/// to a uniquely-named temp file in the destination directory, fsyncs it, then
/// renames into place, so a crash / ENOSPC mid-write can never leave a partial
/// file under the final `sha256:` name. `cas::atomic_write` is `pub(crate)` and
/// unreachable from here, so this mirrors it locally. The caller keeps its
/// `if !path.exists()` dedup skip before calling this.
fn ensure_contained_directory_chain(kcs_dir: &Path, target: &Path) -> Result<()> {
    let canonical_kcs = kcs_dir
        .canonicalize()
        .map_err(|error| KcsError::io(error.to_string(), kcs_dir.display().to_string()))?;
    let relative = target
        .strip_prefix(kcs_dir)
        .map_err(|_| KcsError::schema("derived object directory escapes the repository store"))?;
    let mut current = kcs_dir.to_path_buf();
    for component in relative.components() {
        let std::path::Component::Normal(component) = component else {
            return Err(KcsError::schema(
                "derived object directory contains a non-local path component",
            ));
        };
        current.push(component);
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_dir() => {}
            Ok(_) => {
                return Err(store_corrupt_error(
                    &current,
                    "derived object ancestor is not a real directory",
                ))
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => fs::create_dir(&current)
                .map_err(|error| KcsError::io(error.to_string(), current.display().to_string()))?,
            Err(error) => {
                return Err(KcsError::io(
                    error.to_string(),
                    current.display().to_string(),
                ))
            }
        }
        let canonical = current
            .canonicalize()
            .map_err(|error| KcsError::io(error.to_string(), current.display().to_string()))?;
        if !canonical.starts_with(&canonical_kcs) {
            return Err(store_corrupt_error(
                &current,
                "derived object ancestor resolves outside the repository store",
            ));
        }
    }
    Ok(())
}

fn atomic_write_cas_object(kcs_dir: &Path, path: &Path, bytes: &[u8]) -> Result<()> {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    ensure_contained_directory_chain(kcs_dir, parent)?;
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or_default();
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let temp = parent.join(format!(".tmp-{}-{}-{}", process::id(), nanos, seq));
    match fs::symlink_metadata(path) {
        Ok(_) => return verify_exact_cas_object(path, bytes),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(KcsError::io(error.to_string(), path.display().to_string())),
    }
    let result = (|| -> Result<()> {
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options
            .open(&temp)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        file.write_all(bytes)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        file.sync_all()
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        drop(file);
        let mut permissions = fs::metadata(&temp)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?
            .permissions();
        permissions.set_readonly(true);
        fs::set_permissions(&temp, permissions)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        match fs::hard_link(&temp, path) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                verify_exact_cas_object(path, bytes)?;
            }
            Err(error) => {
                return Err(KcsError::io(error.to_string(), path.display().to_string()));
            }
        }
        fs::remove_file(&temp)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        verify_exact_cas_object(path, bytes)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

fn verify_exact_cas_object(path: &Path, expected: &[u8]) -> Result<()> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    if !metadata.file_type().is_file() || metadata.len() != expected.len() as u64 {
        return Err(store_corrupt_error(
            path,
            "content-addressed object is not the expected regular file",
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.nlink() != 1 {
            return Err(store_corrupt_error(
                path,
                "content-addressed object has an unexpected hard-link count",
            ));
        }
    }
    let mut file = fs::File::open(path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    let opened = file
        .metadata()
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    if !opened.is_file() || opened.len() != expected.len() as u64 {
        return Err(store_corrupt_error(
            path,
            "content-addressed object changed while it was verified",
        ));
    }
    let mut actual = Vec::with_capacity(expected.len());
    (&mut file)
        .take((expected.len() as u64).saturating_add(1))
        .read_to_end(&mut actual)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    if actual != expected || hash_bytes(&actual) != hash_bytes(expected) {
        return Err(store_corrupt_error(
            path,
            "content-addressed object bytes do not match their identity",
        ));
    }
    Ok(())
}

fn verify_existing_cas_objects(
    kcs_dir: &Path,
    subdir: &str,
    hash: &str,
    bytes: &[u8],
) -> Result<bool> {
    let paths = existing_cas_object_paths(kcs_dir, subdir, hash)?;
    for path in &paths {
        let parent = path
            .parent()
            .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
        ensure_contained_directory_chain(kcs_dir, parent)?;
        verify_exact_cas_object(path, bytes)?;
    }
    Ok(!paths.is_empty())
}

fn write_cas_object_or_reuse_legacy(
    kcs_dir: &Path,
    subdir: &str,
    hash: &str,
    bytes: &[u8],
) -> Result<()> {
    if verify_existing_cas_objects(kcs_dir, subdir, hash, bytes)? {
        return Ok(());
    }

    // Close the preflight/publication window as far as possible before entering the
    // atomic canonical writer. Its own create-new publication handles a canonical
    // race; the postcondition below also catches a concurrently-created legacy leaf.
    if verify_existing_cas_objects(kcs_dir, subdir, hash, bytes)? {
        return Ok(());
    }

    let canonical = cas_object_path(kcs_dir, subdir, hash)?;
    atomic_write_cas_object(kcs_dir, &canonical, bytes)?;
    if !verify_existing_cas_objects(kcs_dir, subdir, hash, bytes)? {
        return Err(KcsError::not_found(hash));
    }
    Ok(())
}

fn write_prepared_objects(
    repo: &Repository,
    prepared_units: &[PreparedUnit],
    prepared_hashes: &[String],
    bytes: &[u8],
    media_type: &str,
) -> Result<()> {
    if prepared_units.len() != prepared_hashes.len() {
        return Err(KcsError::schema(
            "prepared unit and object hash cardinalities differ",
        ));
    }
    let pdf_pages = if media_type == "application/pdf" {
        Some(pdf_text_pages_bounded(bytes).map_err(pipeline_to_kcs)?)
    } else {
        None
    };
    if pdf_pages
        .as_ref()
        .is_some_and(|pages| pages.len() != prepared_hashes.len())
    {
        return Err(KcsError::schema(
            "prepared PDF page and object hash cardinalities differ",
        ));
    }
    for (index, prepared_hash) in prepared_hashes.iter().enumerate() {
        if !is_hash(prepared_hash) {
            return Err(KcsError::schema("prepared object hash is invalid"));
        }
        let path = cas_object_path(repo.kcs_dir(), "prepared", prepared_hash)?;
        let object_bytes = pdf_pages
            .as_ref()
            .and_then(|pages| pages.get(index))
            .map_or(bytes, |page| page.as_bytes());
        if hash_bytes(object_bytes) != *prepared_hash
            || prepared_units[index].prepared_hash != *prepared_hash
        {
            return Err(store_corrupt_error(
                &path,
                "prepared object bytes do not match the declared hash",
            ));
        }
        write_cas_object_or_reuse_legacy(repo.kcs_dir(), "prepared", prepared_hash, object_bytes)?;
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
        bbox_annotation_enabled: None,
        reserved_usd: None,
        reserved_month: None,
        reservation_id: None,
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
        let Some(previous) = load_previous_instance_for_task(task_store, &task)? else {
            continue;
        };
        if previous.manifest.tool_profile_hash == tool_profile_hash {
            return Ok(Some(previous));
        }
    }
    Ok(None)
}

fn load_previous_instance_for_task(
    task_store: &TaskStore,
    task: &TaskDescriptor,
) -> Result<Option<PreviousInstance>> {
    let identity = validate_task_output_ref(task_store.kcs_dir(), task).map_err(pipeline_to_kcs)?;
    let TaskOutputRef::NormalizedInstance {
        raw_hash,
        tool_profile_hash,
        gen,
        ..
    } = identity
    else {
        return Ok(None);
    };
    // A missing/corrupt previous instance degrades to a Full run for this document,
    // while a forged task reference is rejected above before it reaches the filesystem.
    Ok(
        load_previous_instance_identity(task_store.kcs_dir(), &raw_hash, &tool_profile_hash, gen)
            .ok(),
    )
}

fn load_previous_instance_identity(
    kcs_dir: &Path,
    raw_hash: &str,
    tool_profile_hash: &str,
    gen: u64,
) -> Result<PreviousInstance> {
    let instance = load_validated_normalized_instance(kcs_dir, raw_hash, tool_profile_hash, gen)
        .map_err(pipeline_to_kcs)?;
    let manifest = instance.manifest;
    let units = instance.units;
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
    Ok(PreviousInstance {
        manifest,
        units,
        prepared_units,
    })
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
        metadata: unit.metadata.clone(),
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
                metadata: unit.metadata.clone(),
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
            metadata: previous_unit.metadata.clone(),
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

#[allow(clippy::too_many_arguments)]
fn manifest_from_units(
    prepared_units: &[PreparedUnit],
    units: &[NormalizedUnitObject],
    raw_hash: &str,
    tool_profile_hash: &str,
    parent_gen: Option<u64>,
    run_id: &str,
    generated_at: &str,
    failed_kind: RetryErrorKind,
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
                // R10-4: record the REAL retry kind for a failed unit (a fixed
                // "missing_output" string is not a `RetryErrorKind`, so the §5.2
                // permanent-vs-retryable gate could not be applied downstream). The
                // caller passes the kind appropriate to its failure mode.
                error_kind: (!done.contains(unit.unit_key.as_str()))
                    .then(|| retry_reason(failed_kind).to_owned()),
            })
            .collect(),
        generated_at: generated_at.to_owned(),
    }
}

/// R19-3: terminal `fallback_reason` for a task retired because its content-addressed
/// target (chunk_id or (path,hash)) is currently NON-LIVE. Unlike `invalid_input`
/// (a permanent, genuinely-bad-input failure), this retirement is REVERSIBLE: the
/// identity can reappear (git revert / undo / restore of the exact bytes), so the
/// `enqueue_*` idempotency guards treat it as non-blocking and let a fresh task be
/// created. It is still non-retryable AS THE OLD TASK (`retry_kind_from_reason` maps it
/// to InvalidInput), so it is never re-driven and never counts as pending work.
const RETIRED_NON_LIVE: &str = "retired_non_live";

/// R17-3/R18-1/R18-2: retire a stale-or-orphaned online adapter `task` (markdownize OR
/// embedding) to a non-retryable `retired_non_live` failure, and — if its kept F8
/// reservation was a NON-billable (RateLimit/Quota) phantom with an exact stamp — return
/// the reclaim entry for the sibling reclaim ledger (the caller appends it AFTER this
/// retirement is durable, so a crash between can only leave the phantom conservatively in
/// place). A NetworkError reservation is deliberately NOT reclaimed (it may have billed
/// server-side; keeping it is the cap-safe invariant R16-7 maintains, guarding the R15-5
/// silent-cap-bypass). The stamp is cleared on EVERY retirement so a task can never be
/// reclaimed twice. Shared by the markdownize same-path enqueue supersede (R17-3), the
/// deleted/renamed-path index sweep (R18-2), the batch-retry precondition retirement
/// (R18-2), and the embedding non-live reclaim in `reconcile_committed_embedding_tasks`
/// (R18-1) — so a phantom is reclaimed at whichever retirement fires first. MUST run
/// BEFORE `fallback_reason` is overwritten to `invalid_input` — the reclaim decision
/// reads the still-intact failure kind (`batch retry` preserves `fallback_reason` across
/// the Failed->Pending flip). `markdown_adapter_kind` is the adapter's ledger key
/// (`"markdown"` or `EMBEDDING_ADAPTER_KIND`), so the reclaim nets the correct cap.
/// R19-4: compute the reclaim ledger entry for a task's F8 reservation WITHOUT mutating
/// the task. A NON-billable (RateLimit/Quota/Auth) reservation with an exact stamp is
/// reclaimable; NetworkError (may have billed server-side) and all other kinds are not.
/// R20-3: AuthError (401/403) is refused at the auth layer BEFORE the backend processes
/// or bills the request — even earlier than a 429 RateLimit — so its F8 phantom is
/// non-billable exactly like RateLimit/Quota and must be reclaimed when the task goes
/// non-live; the reclaim series (R16-7→R19-2) had never included it, so an auth phantom
/// ate the per-adapter cap for the month. NetworkError stays out (it may have billed).
/// Shared by `retire_online_task_reclaiming` (which then retires the task) and the
/// embedding live-embedded convergence (which then completes the task as Done).
fn settle_task_reservation(
    cost_ledger: &CostLedger,
    task: &TaskDescriptor,
    reservation_scope_id: &str,
    adapter_kind: &str,
) -> Result<Option<MonthlyCostLedgerEntry>> {
    let Some(claim) = task.reservation_claim() else {
        return Ok(None);
    };
    let ledger = cost_ledger.reservation_ledger();
    if matches!(
        retry_kind_from_reason(task.fallback_reason.as_deref()),
        RetryErrorKind::RateLimit | RetryErrorKind::QuotaExceeded | RetryErrorKind::AuthError
    ) {
        if let Some(entry) = ledger
            .consume(claim, reservation_scope_id, adapter_kind)
            .map_err(pipeline_to_kcs)?
        {
            return Ok(Some(entry));
        }
    }
    // Active reservations represent successful or billing-ambiguous attempts and
    // can never authorize credit. Unknown/copied claims simply produce `false`.
    ledger
        .close(claim, reservation_scope_id, adapter_kind)
        .map_err(pipeline_to_kcs)?;
    Ok(None)
}

fn transition_reservation_after_outcome(
    cost_ledger: &CostLedger,
    claim: TaskReservationClaim<'_>,
    reservation_scope_id: &str,
    adapter_kind: &str,
    failure_kind: Option<RetryErrorKind>,
) -> Result<()> {
    let ledger = cost_ledger.reservation_ledger();
    if matches!(
        failure_kind,
        Some(RetryErrorKind::RateLimit | RetryErrorKind::QuotaExceeded | RetryErrorKind::AuthError)
    ) {
        ledger
            .mark_reclaimable(claim, reservation_scope_id, adapter_kind)
            .map_err(pipeline_to_kcs)?;
    } else {
        ledger
            .close(claim, reservation_scope_id, adapter_kind)
            .map_err(pipeline_to_kcs)?;
    }
    Ok(())
}

fn retire_online_task(task: &mut TaskDescriptor) {
    task.status = TaskStatus::Failed;
    task.fallback_reason = Some(RETIRED_NON_LIVE.to_owned());
    task.next_retry_at = None;
    task.heartbeat_at = None;
    task.clear_reservation();
}

#[allow(clippy::too_many_arguments)]
fn enqueue_online_placeholder_task(
    repo: &Repository,
    task_store: &TaskStore,
    candidate: &ScanCandidate,
    raw_hash: &str,
    scope_id: &str,
    network_allowed: bool,
    secrets_hold: bool,
    args: &IndexArgs,
    created_at: &str,
    result: &mut IndexPipelineResult,
    cost_ledger: &CostLedger,
    budget_caps: &BudgetCaps,
    month: &str,
) -> Result<()> {
    // R9-2: text-native files (Markdown / plain text / code) are fully handled by
    // the deterministic Adapter (07 §2.1) and must never enqueue an online OCR task
    // (07 §5.2 scopes Mistral OCR to non-text-native PDF/DOCX/PPTX/images). Gate at
    // enqueue so a routine `index` never creates a redundant, privacy-leaking,
    // billed task for a `.md` / `.txt` / code file.
    if is_text_native_media(&candidate.media_type) {
        return Ok(());
    }
    let online_profile = online_markdownize_profile_for(repo);
    let output_ref = online_output_ref(&online_profile.adapter_id);
    let effective_bbox_policy = bbox_annotation_enabled(repo);
    // R15-2: supersede any stale online markdownize task for THIS path whose
    // `input_hash` differs from the current content. The file was edited after that
    // task was enqueued, so it is stale: `batch resume` would R14-2-supersede a
    // Pending/Paused one at send time (adapter never called) but only AFTER the F8
    // pre-send charge already landed (the phantom charge), and left unretired these
    // stale tasks accumulate and eat the per-adapter markdownize cap, falsely pausing
    // the current (valid) task. Retire them here (non-retryable `invalid_input`; the
    // state machine has no "superseded" state and the recovery is this fresh re-index,
    // not a retry). Runs before the idempotency check so it fires even when a same-hash
    // task also exists.
    //
    // R17-3: extend the retirement to a RETRYABLE `Failed` task (gated by
    // `task_retry_allowed`, so a permanently-failed task is left alone). A task that
    // FAILED RateLimit/Quota already sent and KEPT its F8 reservation, which R16-7
    // established is a phantom (those errors are refused before the backend bills). The
    // original R15-2 retired only Pending/Paused, so this Failed(rate_limit) phantom
    // lingered after an edit and budget-paused the new task (R15-2 × R16-7 confluence).
    // When we retire such a task we also RECLAIM its phantom: a NON-billable
    // (RateLimit/Quota) reservation is canceled by appending its exact stamped
    // (usd, month) to the sibling reclaim ledger — F3-compatible (no negative row in
    // the charge ledger; the positive reclaim is netted out in
    // `budget_remaining_for_adapter`). NetworkError reservations are deliberately NOT
    // reclaimed: a NetworkError send may have been billed server-side, so keeping the
    // reservation preserves the cap-safe invariant (guarding the R15-5 silent-cap-
    // bypass, the opposite failure) — the same asymmetry R16-7's re-reservation gate
    // maintains. The reclaim is recorded AFTER the retirement is durably written (the
    // flip clears the stamp and makes the task non-retryable, so it can never match
    // again): if the reclaim-append then fails we leave the phantom conservatively in
    // place rather than risk double-reclaiming.
    let markdown_adapter_kind = adapter_kind_budget_key(online_profile.adapter_kind);
    // Reclaim under the SAME scope_id source the batch send path reserves with
    // (`repo.scope_id_for_adapter()`), so the reclaim cancels the phantom at the
    // folder-scoped totals too, not just the device total.
    let reservation_scope_id = repo.scope_id_for_adapter();
    let mut reclaims: Vec<MonthlyCostLedgerEntry> = Vec::new();
    let mut stale_ids = BTreeSet::new();
    for task in task_store.all().map_err(pipeline_to_kcs)? {
        let stale = task.task_type == TaskType::Markdownize
            && targets_standard_online_markdownize(task_store.kcs_dir(), &task, &output_ref)
            && task.input_path == candidate.input_path
            && task.input_hash != raw_hash
            && (matches!(task.status, TaskStatus::Pending | TaskStatus::Paused)
                || (task.status == TaskStatus::Failed
                    && is_reservation_bearing_send_failure(&task)));
        if !stale {
            continue;
        }
        if let Some(entry) = settle_task_reservation(
            cost_ledger,
            &task,
            &reservation_scope_id,
            markdown_adapter_kind,
        )? {
            reclaims.push(entry);
        }
        stale_ids.insert(task.task_id);
    }
    task_store
        .update_matching(|task| {
            if !stale_ids.contains(&task.task_id) {
                return false;
            }
            retire_online_task(task);
            true
        })
        .map_err(pipeline_to_kcs)?;
    // Record the reclaims positively in the sibling reclaim ledger AFTER the durable
    // retirement above. F3-safe: the charge ledger is never given a negative row; each
    // reclaim row is positive and is subtracted in `budget_remaining_for_adapter`,
    // clamped at 0 there.
    if !reclaims.is_empty() {
        let reclaim_ledger = cost_ledger.reclaim_ledger();
        for entry in &reclaims {
            reclaim_ledger
                .append_monthly(entry)
                .map_err(pipeline_to_kcs)?;
        }
    }
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
            if task.bbox_annotation_enabled != Some(effective_bbox_policy) {
                return false;
            }
            match task.status {
                TaskStatus::Pending | TaskStatus::Paused => {
                    targets_standard_online_markdownize(task_store.kcs_dir(), task, &output_ref)
                }
                TaskStatus::Done | TaskStatus::Partial => {
                    task.fallback_reason.as_deref() == Some("online_adapter_done")
                }
                // R19-3: a `retired_non_live` Failed task must NOT block a fresh enqueue
                // when the (path,hash) identity reappears (revert/restore). Other Failed
                // tasks stay deduped (owned by `batch retry`, which honors backoff).
                TaskStatus::Failed => {
                    targets_standard_online_markdownize(task_store.kcs_dir(), task, &output_ref)
                        && task.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE)
                }
                TaskStatus::Running => {
                    targets_standard_online_markdownize(task_store.kcs_dir(), task, &output_ref)
                }
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
        estimated_usd: estimate_online_markdownize_cost(
            candidate.size_bytes,
            bbox_annotation_enabled(repo),
        ),
        adapter_id: Some(online_profile.adapter_id.clone()),
    };
    let (device_remaining, folder_remaining) = budget_remaining_for_adapter(
        cost_ledger,
        budget_caps,
        month,
        scope_id,
        adapter_kind_budget_key(online_profile.adapter_kind),
    )?;
    let budget = evaluate_budget_with_caps(
        &estimate,
        device_remaining,
        folder_remaining,
        matches_batch_override(args),
    );
    // R10-7: an online markdownize task can only ever be DRIVEN by `batch`, whose
    // gate is the persistent per-adapter opt-in (`persistent_network_allowed`). A
    // one-shot `--online --yes` sets per-invocation `network_allowed = true` but
    // leaves no persistent opt-in, so the task can never be sent — a silent dead-end.
    // Report the honest state (`network_opt_in_required`) rather than a false
    // `ready_for_online_adapter`. (Inline `--yes` sending, to match embedding, is
    // deferred with the F6 promotion wiring.)
    let markdownize_drivable = network_allowed && persistent_network_allowed(repo)?;
    // N1a: a Tier B (candidate-secret) file without `--send-secrets` is held here
    // — a Paused task with `secrets_tier_b_hold`, visible in `kcs status`, that
    // `batch resume` will not un-hold and `execute_pending_markdownize_tasks` will
    // not send. The hold takes precedence over budget/network reasons.
    let (status, reason) = if secrets_hold {
        (TaskStatus::Paused, Some(SECRETS_TIER_B_HOLD))
    } else if !budget.allowed && budget_caps.hard_stop {
        // F5: only a hard-stop cap pauses the task. Under soft-stop the online task
        // is enqueued normally and its over-cap charge is recorded at execution.
        (TaskStatus::Paused, Some("budget_exceeded"))
    } else if !markdownize_drivable {
        (TaskStatus::Pending, Some("network_opt_in_required"))
    } else {
        (TaskStatus::Pending, Some("ready_for_online_adapter"))
    };
    let mut task = task_descriptor(
        repo,
        TaskType::Markdownize,
        Some(MarkdownizeMode::Full),
        candidate,
        raw_hash,
        &output_ref,
        status,
        reason,
        created_at,
    );
    task.bbox_annotation_enabled = Some(effective_bbox_policy);
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

/// R17-3/R18-3: this month's NET spend for the `(scope, adapter)` filter — gross
/// charges minus the R17-3 reclaimed phantoms recorded in the sibling reclaim ledger,
/// clamped at 0. The single source of truth shared by the enforcement gate
/// (`budget_remaining_for_adapter`) and the status/warning reports
/// (`budget_status_json` / `scope_budget_warning`), so a reclaimed phantom stops eating
/// the cap in BOTH the enforced remaining and the displayed spend. `.max(0.0)` is pure
/// defense against a corrupt reclaim ledger — in correct operation reclaimed never
/// exceeds the phantom charges it cancels, so `net >= real spend` holds (never
/// fail-open). `None` scope/adapter means "device-wide / all adapters".
fn net_monthly_spent(
    cost_ledger: &CostLedger,
    month: &str,
    scope_id: Option<&str>,
    adapter_kind: Option<&str>,
) -> Result<f64> {
    let gross = cost_ledger
        .monthly_total_for_adapter(month, scope_id, adapter_kind)
        .map_err(pipeline_to_kcs)?;
    let reclaimed = cost_ledger
        .reclaim_ledger()
        .monthly_total_for_adapter(month, scope_id, adapter_kind)
        .map_err(pipeline_to_kcs)?;
    let net = gross - reclaimed;
    // R20-11: `reclaimed > gross` is impossible in normal operation — every reclaim row
    // corresponds to a kept charge, and stamps are cleared on retirement so a reservation
    // is reclaimed at most once. A meaningfully-negative net therefore signals an anomaly
    // (reclaim-ledger corruption, or an over-reclaim bug like R20-2's duplicate-output_ref
    // double-reclaim). The old `.max(0.0)` clamp fail-OPENED the cap (net=0 → the full cap
    // reads as available); fail CLOSED instead by ignoring the untrustworthy reclaim credit
    // and charging the honest gross — the same fail-closed posture F1/F3 gave the charge
    // ledger. The −1e-9 threshold is far below a single (~1e-6) charge yet far above f64
    // summation noise, so only a real over-reclaim (>= one charge) trips it.
    if net < -1e-9 {
        return Ok(gross.max(0.0));
    }
    Ok(net.max(0.0))
}

fn budget_remaining_for_adapter(
    cost_ledger: &CostLedger,
    budget_caps: &BudgetCaps,
    month: &str,
    scope_id: &str,
    adapter_kind: &str,
) -> Result<(f64, Option<f64>)> {
    // R17-3/R18-3: spend is NET of reclaimed phantoms (gross charges − reclaim ledger,
    // clamped), computed by the shared `net_monthly_spent` helper so this enforcement
    // gate and the status/warning REPORTS (`budget_status_json`/`scope_budget_warning`)
    // use one identical netting — before R18-3 only enforcement netted, so `kcs status`
    // over-reported spend after a reclaim.
    let device_spent = net_monthly_spent(cost_ledger, month, None, None)?;
    let folder_spent = net_monthly_spent(cost_ledger, month, Some(scope_id), None)?;
    let device_adapter_spent = net_monthly_spent(cost_ledger, month, None, Some(adapter_kind))?;
    let folder_adapter_spent =
        net_monthly_spent(cost_ledger, month, Some(scope_id), Some(adapter_kind))?;
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

/// Result of an atomic (device-globally-serialized) cost-ledger charge attempt.
#[derive(Debug)]
enum ChargeOutcome {
    /// The estimate fit the cap under the lock and was appended (reserved).
    Charged,
    /// The re-read under the lock showed the cap would be exceeded; nothing was
    /// appended. The caller must not send.
    BudgetExceeded,
}

struct CostChargeRequest<'a> {
    month: &'a str,
    adapter_kind: &'a str,
    estimate: &'a BudgetEstimate,
    override_budget: bool,
    reservations: &'a [ReservationRecord],
}

/// F8: atomically reserve a charge against the device-global cost-ledger.
///
/// The ledger is device-global while `StoreLock` (`.kcs/.lock`) is scope-scoped,
/// so before this the budget read-check and the append were not serialized across
/// scopes: two concurrent `index` runs could each pass the cap check and both
/// append, exceeding the monthly cap (TOCTOU). This takes a single device-global
/// lock (`cost-ledger.lock`), RE-READS the ledger under it to re-evaluate the cap
/// against any spend a concurrent scope just committed, and only then appends the
/// estimate — so the reservation is visible to the next charger before its check.
///
/// The reservation is taken BEFORE the adapter call (which the caller issues only
/// on `Charged`, OUTSIDE this lock) so the device is not serialized on network
/// I/O. A send failure intentionally keeps the reservation: a hard safety cap must
/// never be exceeded, and F3 forbids negative compensating entries. Lock
/// contention surfaces as `KCS-E-STORE-LOCKED-001` (fail-closed), never an
/// unrecorded charge.
fn charge_cost_ledger_under_lock(
    cost_ledger: &CostLedger,
    lock_path: PathBuf,
    budget_caps: &BudgetCaps,
    request: CostChargeRequest<'_>,
) -> Result<ChargeOutcome> {
    // The reserved row is derived from the same `(month, estimate.scope_id,
    // adapter_kind, estimate.estimated_usd)` used for the cap check, so the
    // checked and appended `adapter_kind`/amount can never diverge.
    let scope_id = request.estimate.scope_id.as_str();
    let _ledger_lock = StoreLock::acquire_path(lock_path)?;
    let (device_remaining, folder_remaining) = budget_remaining_for_adapter(
        cost_ledger,
        budget_caps,
        request.month,
        scope_id,
        request.adapter_kind,
    )?;
    let budget = evaluate_budget_with_caps(
        request.estimate,
        device_remaining,
        folder_remaining,
        request.override_budget,
    );
    // F5: `hard_stop` (default true) pauses at the cap as before. `hard_stop=false`
    // is a soft-stop: over cap we still append the real charge and continue, so the
    // ledger reflects actual spend and `warn_at_percent` can surface it. The append
    // stays inside the F8 lock region either way.
    if !budget.allowed && budget_caps.hard_stop {
        return Ok(ChargeOutcome::BudgetExceeded);
    }
    let mut reservation_ids = BTreeSet::new();
    let mut task_ids = BTreeSet::new();
    let mut reservation_total = 0.0_f64;
    for reservation in request.reservations {
        if reservation.month != request.month
            || reservation.scope_id != scope_id
            || reservation.adapter_kind != request.adapter_kind
            || !reservation_ids.insert(reservation.reservation_id.as_str())
            || !task_ids.insert(reservation.task_id.as_str())
        {
            return Err(KcsError::schema(
                "cost reservation identity does not match the charged request",
            ));
        }
        reservation_total += reservation.usd;
    }
    let tolerance = 1e-12_f64.max(request.estimate.estimated_usd.abs() * 1e-12);
    if request.reservations.is_empty()
        || !reservation_total.is_finite()
        || (reservation_total - request.estimate.estimated_usd).abs() > tolerance
    {
        return Err(KcsError::schema(
            "cost reservation total does not match the charged amount",
        ));
    }
    // Issue reclaim authority before the charge row while the global cost lock is
    // held. Newly issued reservations are Active and cannot produce credit; if the
    // following charge append fails, the residue therefore fails closed.
    cost_ledger
        .reservation_ledger()
        .issue_all(request.reservations)
        .map_err(pipeline_to_kcs)?;
    cost_ledger
        .append_monthly(&MonthlyCostLedgerEntry {
            month: request.month.to_owned(),
            scope_id: scope_id.to_owned(),
            adapter_kind: request.adapter_kind.to_owned(),
            usd: request.estimate.estimated_usd,
        })
        .map_err(pipeline_to_kcs)?;
    Ok(ChargeOutcome::Charged)
    // `_ledger_lock` drops here, releasing the device-global lock.
}

fn materialize_tool_lock(repo: &Repository) -> Result<()> {
    let prepare_profile = builtin_prepare_profile();
    let markdown_profile = active_markdown_adapter(repo).profile();
    let mut value = json!({
        "spec_version": 1,
        "prepare": {
            "tool_id": prepare_profile.adapter_id,
            "profile_hash": prepare_profile.tool_profile_hash,
            "kind": "deterministic_library"
        },
        "markdown": {
            "tool_id": markdown_profile.adapter_id,
            "profile_hash": markdown_profile.tool_profile_hash,
            "kind": execution_mode_name(markdown_profile.execution_mode),
            "capabilities": markdown_profile.capability_flags
        }
    });
    // Write the embedding entry (07 §6) when an embedding adapter is configured.
    // A non-multimodal profile is rejected here (03 §7): `load_tool_lock` fails
    // with KCS-E-EMBED-MODALITY-001, which we surface as exit 2 (scenario (e))
    // *before* any indexing happens.
    if let Some(entry) = embedding_tool_lock_entry()? {
        if let Some(object) = value.as_object_mut() {
            object.insert("embedding".to_owned(), entry);
        }
    }
    let bytes =
        serde_json::to_vec_pretty(&value).map_err(|err| KcsError::schema(err.to_string()))?;
    if let Err(error) = load_tool_lock(&bytes) {
        let message = error.to_string();
        if message.contains("KCS-E-EMBED-MODALITY-001") {
            return Err(KcsError::new(
                "KCS-E-EMBED-MODALITY-001",
                message,
                json!({}),
                ExitCode::InvalidUsage,
            ));
        }
        return Err(adapter_to_kcs(error));
    }
    let path = repo.kcs_dir().join("tool-lock.json");
    atomic_overwrite_file(&path, &bytes)
}

fn execution_mode_name(mode: ExecutionMode) -> &'static str {
    match mode {
        ExecutionMode::OnlineApi => "online_api",
        ExecutionMode::OfflineApi => "offline_api",
        ExecutionMode::DeterministicLibrary => "deterministic_library",
    }
}

fn approval_exists(repo: &Repository) -> Result<bool> {
    approval_row_present_for_scope(repo, None)
}

fn network_allowed(repo: &Repository, args: &IndexArgs) -> Result<bool> {
    if args.offline {
        return Ok(false);
    }
    if network_revoked(repo)? {
        return Ok(false);
    }
    if args.online {
        return if args.yes || args.approve {
            Ok(true)
        } else {
            approval_row_present(repo, &online_markdownize_profile().adapter_id)
        };
    }
    if args.approve {
        return Ok(true);
    }
    if read_allow_network_config(&user_config_toml_path())? == Some(true) {
        return Ok(true);
    }
    approval_row_present(repo, &online_markdownize_profile().adapter_id)
}

fn network_revoked(repo: &Repository) -> Result<bool> {
    network_revoked_kcs_dir(repo.kcs_dir())
}

fn network_revoked_kcs_dir(kcs_dir: &Path) -> Result<bool> {
    // Revocation is persisted as `allow_network = false` in config.toml by
    // `write_network_revoke_record`; the audit trail lives in
    // `network-revoked.jsonl`. There is no extensionless `network-revoked`
    // sentinel file, so no such probe here (Step2c I5).
    Ok(read_allow_network_config(&kcs_dir.join("config.toml"))? == Some(false))
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
    atomic_overwrite_file(&config_path, text.as_bytes())?;
    let path = repo.kcs_dir().join("network-revoked.jsonl");
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    // M1(b): frame the record and emit it with one write_all (no interleaving).
    let tool_id = online_markdownize_profile().adapter_id;
    let mut line = serde_json::to_string(&json!({
        "recorded_at": now_utc_seconds(),
        "tool_id": tool_id,
        "execution_mode": "online_api",
        "allow_network": false,
    }))
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    line.push('\n');
    file.write_all(line.as_bytes())
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

/// N1: the marker file whose presence records an explicit `--send-secrets`
/// approval for this scope. It lifts the Tier B online hold for every subsequent
/// pass (index inline + `batch resume`), so it must be a persistent, per-scope
/// signal (decisions #45).
const SECRETS_APPROVAL_FILE: &str = "secrets-approved.jsonl";

#[derive(Clone, Copy)]
enum ConsentOperation {
    Network,
    SendSecrets,
}

impl ConsentOperation {
    fn as_str(self) -> &'static str {
        match self {
            Self::Network => "network",
            Self::SendSecrets => "send_secrets",
        }
    }
}

const DEVICE_CONSENT_SCHEMA_VERSION: u64 = 1;

fn device_consent_path() -> PathBuf {
    data_home().join("kcs/consents.jsonl")
}

fn device_consent_lock_path() -> PathBuf {
    data_home().join("kcs/consents.lock")
}

fn consent_identity(kcs_dir: &Path) -> Result<(String, String)> {
    let root = kcs_dir
        .parent()
        .ok_or_else(|| KcsError::invalid_usage(".kcs has no scope root"))?;
    let canonical_root = root
        .canonicalize()
        .map_err(|err| KcsError::io(err.to_string(), root.display().to_string()))?;
    Ok((
        scope_id(kcs_dir)?,
        canonical_root.to_string_lossy().into_owned(),
    ))
}

fn trusted_consent_present(
    kcs_dir: &Path,
    tool_id: Option<&str>,
    operation: ConsentOperation,
) -> Result<bool> {
    let path = device_consent_path();
    let metadata = match fs::symlink_metadata(&path) {
        Ok(metadata) => metadata,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(err) => return Err(KcsError::io(err.to_string(), path.display().to_string())),
    };
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(KcsError::invalid_usage(
            "device consent store must be a regular file",
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o077 != 0 {
            return Err(KcsError::invalid_usage(
                "device consent store must not be group/world accessible",
            ));
        }
    }
    let (expected_scope_id, expected_root) = consent_identity(kcs_dir)?;
    let text = fs::read_to_string(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    Ok(text
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .any(|value| {
            value.get("schema_version").and_then(Value::as_u64)
                == Some(DEVICE_CONSENT_SCHEMA_VERSION)
                && value.get("scope_id").and_then(Value::as_str) == Some(expected_scope_id.as_str())
                && value.get("canonical_root").and_then(Value::as_str)
                    == Some(expected_root.as_str())
                && value.get("operation").and_then(Value::as_str) == Some(operation.as_str())
                && tool_id
                    .map(|tool_id| value.get("tool_id").and_then(Value::as_str) == Some(tool_id))
                    .unwrap_or(true)
        }))
}

fn write_device_consent(
    repo: &Repository,
    tool_id: &str,
    operation: ConsentOperation,
) -> Result<()> {
    let path = device_consent_path();
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::invalid_usage("device consent path has no parent"))?;
    fs::create_dir_all(parent)
        .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(parent, fs::Permissions::from_mode(0o700))
            .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    }
    let _lock = StoreLock::acquire_path(device_consent_lock_path())?;
    if trusted_consent_present(repo.kcs_dir(), Some(tool_id), operation)? {
        return Ok(());
    }
    let (scope_id, canonical_root) = consent_identity(repo.kcs_dir())?;
    let mut line = serde_json::to_string(&json!({
        "schema_version": DEVICE_CONSENT_SCHEMA_VERSION,
        "scope_id": scope_id,
        "canonical_root": canonical_root,
        "tool_id": tool_id,
        "operation": operation.as_str(),
        "granted_at": now_utc_seconds(),
        "kcs_version": env!("CARGO_PKG_VERSION"),
    }))
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    line.push('\n');
    let mut options = OpenOptions::new();
    options.create(true).append(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600))
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    }
    file.write_all(line.as_bytes())
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
}

fn active_online_tool_ids() -> Result<Vec<String>> {
    let mut tool_ids = vec![online_markdownize_profile().adapter_id];
    if let Some(adapter_id) = active_embedding_adapter_id()? {
        tool_ids.push(adapter_id);
    }
    tool_ids.sort();
    tool_ids.dedup();
    Ok(tool_ids)
}

/// Whether Tier B (candidate-secret) files may be sent to online adapters for
/// this scope, i.e. `--send-secrets` was recorded at least once (N1c).
fn secrets_send_approved(repo: &Repository) -> bool {
    secrets_send_approved_in_kcs_dir(repo.kcs_dir())
}

fn secrets_send_approved_in_kcs_dir(kcs_dir: &Path) -> bool {
    active_online_tool_ids().is_ok_and(|tool_ids| {
        !tool_ids.is_empty()
            && tool_ids.iter().all(|tool_id| {
                trusted_consent_present(kcs_dir, Some(tool_id), ConsentOperation::SendSecrets)
                    .unwrap_or(false)
            })
    })
}

/// Record the explicit `--send-secrets` approval (N1c). Idempotent: appended as
/// an audit trail; `secrets_send_approved` accepts only a row bound to this scope.
fn write_secrets_approval(repo: &Repository, preview: &ScanPreview) -> Result<()> {
    for tool_id in active_online_tool_ids()? {
        write_device_consent(repo, &tool_id, ConsentOperation::SendSecrets)?;
    }
    let path = repo.kcs_dir().join(SECRETS_APPROVAL_FILE);
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    let mut line = serde_json::to_string(&json!({
        "scope_id": preview.scope_id,
        "approved_at": now_utc_seconds(),
        "actor": std::env::var("USER").unwrap_or_else(|_| "unknown".to_owned()),
        "approval_method": "send_secrets",
    }))
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    line.push('\n');
    file.write_all(line.as_bytes())
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
}

/// Release any online tasks held for Tier B secrets (`secrets_tier_b_hold`) back
/// to Pending once the scope is approved (N1c). Markdownize holds then flow to
/// `batch resume`; embedding holds are re-driven by the enrichment pass.
fn release_secret_holds(repo: &Repository) -> Result<usize> {
    let store = TaskStore::new(repo.kcs_dir());
    let mut tasks = store.all().map_err(pipeline_to_kcs)?;
    let terminal_embedding_refs = tasks
        .iter()
        .filter(|task| {
            task.task_type == TaskType::Embedding
                && task.status == TaskStatus::Failed
                && task.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE)
                && !task_retry_allowed(task)
        })
        .map(|task| task.output_ref.clone())
        .collect::<BTreeSet<_>>();
    let before = tasks.len();
    tasks.retain(|task| {
        !(task.task_type == TaskType::Embedding
            && task.status == TaskStatus::Paused
            && task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD)
            && terminal_embedding_refs.contains(&task.output_ref))
    });
    let removed_duplicates = before.saturating_sub(tasks.len());
    if removed_duplicates > 0 {
        store.replace_all(&tasks).map_err(pipeline_to_kcs)?;
    }
    let released = store
        .update_matching(|task| {
            if task.status == TaskStatus::Paused
                && task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD)
            {
                task.status = TaskStatus::Pending;
                task.fallback_reason = None;
                true
            } else {
                false
            }
        })
        .map_err(pipeline_to_kcs)?;
    Ok(removed_duplicates.saturating_add(released))
}

/// Fallback reason marking an online task held because its input is a Tier B
/// (candidate-secret) file awaiting `--send-secrets` (N1a).
const SECRETS_TIER_B_HOLD: &str = "secrets_tier_b_hold";

fn record_quarantine_candidates(
    repo: &Repository,
    preview: &ScanPreview,
    secrets_approved: bool,
) -> Result<()> {
    let path = repo.kcs_dir().join("quarantine.jsonl");
    // R19-7: dedup on (path, approval_method), not path alone — otherwise a
    // `hold` record permanently blocks the later `send_approved` transition
    // (after `--send-secrets`), leaving `kcs status` reporting an approved,
    // already-sent file as still pending-hold. The reader takes the latest row
    // per path, so appending the transition row corrects the disposition.
    let existing = read_quarantine_records(repo)?
        .into_iter()
        .filter_map(|entry| {
            let path = entry.get("path").and_then(Value::as_str)?.to_owned();
            let method = entry
                .get("approval_method")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned();
            Some((path, method))
        })
        .collect::<BTreeSet<_>>();
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    for candidate in &preview.candidates {
        // N1b: record Tier A (excluded from ingest) AND Tier B (ingested locally
        // but held from online send) so `kcs status` surfaces both. Tier B carries
        // its live disposition — "hold" until `--send-secrets`, then "send_approved".
        let (reason, approval_method) = match candidate.quarantine_reason.as_deref() {
            Some("secrets_tier_a_excluded") if candidate.ignored => {
                ("secrets_tier_a", "quarantine")
            }
            // R19-1: a lifted (ingested) Tier A secret held from online send — record it
            // with its live disposition so `kcs status` surfaces the pending online hold
            // and the eventual approval (audit trail; 07 §122).
            Some("secrets_tier_a_online_hold") => (
                "secrets_tier_a",
                if secrets_approved {
                    "send_approved"
                } else {
                    "hold"
                },
            ),
            Some("secrets_tier_b_warning") => (
                "secrets_tier_b",
                if secrets_approved {
                    "send_approved"
                } else {
                    "hold"
                },
            ),
            _ => continue,
        };
        if existing.contains(&(candidate.input_path.clone(), approval_method.to_owned())) {
            continue;
        }
        let record = json!({
            "path": candidate.input_path,
            "reason": reason,
            "recorded_at": now_utc_seconds(),
            "approval_method": approval_method,
        });
        // M1(b): one framed record per single write_all (no interleaving).
        let mut line = serde_json::to_string(&record)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        line.push('\n');
        file.write_all(line.as_bytes())
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
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

/// R20-9: quarantine records collapsed to the LATEST disposition per path, for `kcs status`
/// display. `record_quarantine_candidates` appends a `hold` row, then (after
/// `--send-secrets`) a `send_approved` row — R19-7's `(path, approval_method)` dedup lets
/// both land. The raw `read_quarantine_records` returns BOTH, so status reported a file as
/// simultaneously "hold" and "send_approved". quarantine.jsonl is append-only in
/// chronological order, so the last row per path is the current disposition — the reader
/// behavior R19-7's fix comment assumed but never implemented. The raw reader is left
/// untouched (the writer's own `(path, method)` dedup set needs every row).
fn quarantine_status_records(repo: &Repository) -> Result<Vec<Value>> {
    let mut order: Vec<String> = Vec::new();
    let mut latest: BTreeMap<String, Value> = BTreeMap::new();
    for row in read_quarantine_records(repo)? {
        let key = row
            .get("path")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        if !latest.contains_key(&key) {
            order.push(key.clone());
        }
        latest.insert(key, row);
    }
    Ok(order
        .into_iter()
        .filter_map(|key| latest.remove(&key))
        .collect())
}

fn write_approval_record(
    repo: &Repository,
    preview: &ScanPreview,
    approval_method: &str,
    network_opt_in: bool,
) -> Result<()> {
    let path = repo.kcs_dir().join("approvals.jsonl");
    // One approval row per configured online adapter (07 §3: opt-in unit is
    // scope × adapter, L4). Adapter IDs are sourced from AdapterProfile rather
    // than hard-coded in the CLI.
    let tool_ids = active_online_tool_ids()?;
    if network_opt_in {
        for tool_id in &tool_ids {
            write_device_consent(repo, tool_id, ConsentOperation::Network)?;
        }
    }
    // P7: the opt-in is a persistent, idempotent marker. Every `index` used to
    // append a fresh row per adapter, so approvals.jsonl grew unbounded (and the
    // O(n) opt-in scan with it). Skip any adapter whose equivalent
    // (scope_id, tool_id, network_opt_in, execution_mode) row is already present.
    let existing = read_existing_approval_keys(&path);
    let pending: Vec<String> = tool_ids
        .into_iter()
        .filter(|tool_id| {
            !existing.contains(&approval_dedup_key(
                &preview.scope_id,
                tool_id,
                network_opt_in,
                "online_api",
            ))
        })
        .collect();
    if pending.is_empty() {
        return Ok(());
    }
    let base = json!({
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
        "execution_mode": "online_api",
    });
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    for tool_id in pending {
        let mut record = base.clone();
        record["tool_id"] = json!(tool_id);
        // M1(b): one framed record per single write_all (no interleaving).
        let mut line = serde_json::to_string(&record)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        line.push('\n');
        file.write_all(line.as_bytes())
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    }
    Ok(())
}

/// The idempotency key for an approval row (P7): the tuple that makes two opt-in
/// records equivalent — `(scope_id, tool_id, network_opt_in, execution_mode)`.
fn approval_dedup_key(
    scope_id: &str,
    tool_id: &str,
    network_opt_in: bool,
    execution_mode: &str,
) -> String {
    format!("{scope_id}\0{tool_id}\0{network_opt_in}\0{execution_mode}")
}

/// Dedup keys for the approval rows already recorded in `approvals.jsonl` (P7).
/// A missing / unreadable file yields an empty set (nothing to dedup against).
fn read_existing_approval_keys(path: &Path) -> BTreeSet<String> {
    let Ok(text) = fs::read_to_string(path) else {
        return BTreeSet::new();
    };
    text.lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter_map(|value| {
            Some(approval_dedup_key(
                value.get("scope_id").and_then(Value::as_str)?,
                value.get("tool_id").and_then(Value::as_str)?,
                value.get("network_opt_in").and_then(Value::as_bool)?,
                value.get("execution_mode").and_then(Value::as_str)?,
            ))
        })
        .collect()
}

/// R13-2: parse the (already schema-validated) user `tools.toml` and publish its
/// declared adapters to the process-global registry so the online clients honor a
/// declared `auth`/`model`. Best-effort: a missing/unreadable file registers an
/// empty map (legacy env-var behavior preserved).
fn register_declared_adapters_from_tools_config() {
    use kcs_adapter::tool_lock::{declared_adapter_for_role, register_declared_adapters};
    let mut map = std::collections::HashMap::new();
    if let Some(path) = user_tools_toml_path() {
        if let Ok(text) = fs::read_to_string(&path) {
            if let Ok(value) = toml::from_str::<toml::Value>(&text) {
                for role in [
                    "prepare",
                    "markdown",
                    "embedding",
                    "summary",
                    "classification",
                    "rerank",
                ] {
                    if let Some(declared) = declared_adapter_for_role(&value, role) {
                        map.insert(role.to_owned(), declared);
                    }
                }
            }
        }
    }
    register_declared_adapters(map);
}

/// R13-2(4): record a one-per-run `level=warn` to errors.jsonl when an online
/// adapter activates via the legacy env var with NO `tools.toml` declaration
/// (docs/07 §7.1 drift made visible). Deduped per role for the whole process so it
/// is 1 execution / 1 record, never per task.
fn warn_undeclared_adapter_once(role: &str) {
    use std::sync::{Mutex, OnceLock};
    static WARNED: OnceLock<Mutex<std::collections::HashSet<String>>> = OnceLock::new();
    let warned = WARNED.get_or_init(|| Mutex::new(std::collections::HashSet::new()));
    let mut guard = warned
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    if !guard.insert(role.to_owned()) {
        return;
    }
    drop(guard);
    let _ = append_warn_log(
        "KCS-W-ADAPTER-UNDECLARED-001",
        "online adapter active via env var without a tools.toml declaration (undeclared-adapter)",
        json!({ "adapter_role": role }),
    );
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
    // P3 (CT2-ADAPTER-010 / 07 §1): a plaintext `plain:<api_key>` in tools.toml
    // must be owner-only (0600). If it is group/world-readable, record a warning
    // to errors.jsonl (level=warn) — never block startup, this is advisory.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if tools_toml_contains_plain_auth(&bytes) {
            if let Ok(metadata) = fs::metadata(&path) {
                let mode = metadata.permissions().mode();
                if mode & 0o077 != 0 {
                    let _ = append_warn_log(
                        "KCS-E-ADAPTER-TOOLS-PERM-001",
                        "tools.toml holds a plaintext `plain:` API key but is group/world-readable; restrict it to 0600",
                        json!({
                            "path": path.display().to_string(),
                            "mode": format!("{:o}", mode & 0o7777),
                        }),
                    );
                }
            }
        }
    }
    validate_tools_toml(&bytes).map_err(adapter_to_kcs)
}

/// Whether a tools.toml carries any `auth = "plain:<...>"` value (P3). Walks the
/// parsed TOML rather than substring-matching so a comment mentioning `plain:`
/// does not trigger a false warning.
fn tools_toml_contains_plain_auth(bytes: &[u8]) -> bool {
    let Ok(text) = std::str::from_utf8(bytes) else {
        return false;
    };
    let Ok(value) = toml::from_str::<toml::Value>(text) else {
        return false;
    };
    toml_value_has_plain_auth(&value)
}

fn toml_value_has_plain_auth(value: &toml::Value) -> bool {
    match value {
        toml::Value::String(text) => text.starts_with("plain:"),
        toml::Value::Table(table) => table.values().any(toml_value_has_plain_auth),
        toml::Value::Array(items) => items.iter().any(toml_value_has_plain_auth),
        _ => false,
    }
}

/// M8: validate the user (device) `config.toml` against `config.schema.json`
/// before dispatch (10 §12 / 06 §11). The folder `.kcs/config.toml` is already
/// validated on `Repository::open` (scope.rs `validate_config`); the user config
/// took no such path, so a negative budget cap etc. slipped through. Schema
/// failures are `KCS-E-CONFIG-SCHEMA-001` (exit 2).
fn validate_user_config() -> Result<()> {
    let path = user_config_toml_path();
    if !path.is_file() {
        return Ok(());
    }
    let text = fs::read_to_string(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    let toml_value: toml::Value =
        toml::from_str(&text).map_err(|err| KcsError::schema(err.to_string()))?;
    let json_value =
        serde_json::to_value(&toml_value).map_err(|err| KcsError::schema(err.to_string()))?;
    validate_json_schema(SchemaKind::Config, &json_value)?;
    // R12-2: apply the same documented-but-unwired value enforcement to the user
    // config (device-global) as scope config gets in `validate_config`, so e.g.
    // `store_request_body = true` there is a loud NOT-IMPLEMENTED, not a silent
    // accept.
    kcs_core::scope::enforce_config_semantics(&json_value)
}

fn validate_repo_tool_lock(repo: &Repository) -> Result<()> {
    let path = repo.kcs_dir().join("tool-lock.json");
    match fs::symlink_metadata(&path) {
        Ok(metadata) if metadata.file_type().is_file() => {}
        Ok(_) => return Err(KcsError::schema("tool-lock must be a regular file")),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(KcsError::io(error.to_string(), path.display().to_string())),
    }
    let bytes =
        fs::read(&path).map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    load_tool_lock(&bytes).map(|_| ()).map_err(adapter_to_kcs)
}

fn require_repo_tool_lock(repo: &Repository) -> Result<()> {
    let path = repo.kcs_dir().join("tool-lock.json");
    match fs::symlink_metadata(&path) {
        Ok(metadata) if metadata.file_type().is_file() => validate_repo_tool_lock(repo),
        Ok(_) => Err(KcsError::schema("tool-lock must be a regular file")),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Err(KcsError::schema(
            "tool-lock is required before executing persisted batch tasks; run `kcs index` to regenerate it",
        )),
        Err(error) => Err(KcsError::io(error.to_string(), path.display().to_string())),
    }
}

fn user_tools_toml_path() -> Option<PathBuf> {
    // R12-6 / R13-6: empty/relative `XDG_CONFIG_HOME` or `HOME` are invalid.
    if let Some(path) = kcs_core::xdg::xdg_dir("XDG_CONFIG_HOME") {
        return Some(path.join("kcs/tools.toml"));
    }
    kcs_core::xdg::home_dir().map(|home| home.join(".config/kcs/tools.toml"))
}

fn user_config_toml_path() -> PathBuf {
    // R12-6 / R13-6: empty/relative `XDG_CONFIG_HOME` or `HOME` are invalid. The
    // `ensure_device_dirs_resolvable` startup guard rejects the no-absolute-base
    // case loudly, so the relative last resort is never reached in practice.
    if let Some(path) = kcs_core::xdg::xdg_dir("XDG_CONFIG_HOME") {
        return path.join("kcs/config.toml");
    }
    kcs_core::xdg::home_dir()
        .map(|home| home.join(".config/kcs/config.toml"))
        .unwrap_or_else(|| PathBuf::from(".config/kcs/config.toml"))
}

fn data_home() -> PathBuf {
    // R12-6 / R13-6: empty/relative `XDG_DATA_HOME` or `HOME` are invalid — the
    // device data dir (registry, cost ledger, logs, 0600 cursor-key) must never
    // resolve to a CWD-relative `kcs/` that the next index could archive. The
    // startup guard rejects the no-absolute-base case before the `"."` last resort.
    if let Some(path) = kcs_core::xdg::xdg_dir("XDG_DATA_HOME") {
        return path;
    }
    if let Some(home) = kcs_core::xdg::home_dir() {
        return home.join(".local/share");
    }
    PathBuf::from(".")
}

/// `$XDG_CACHE_HOME`, else `$HOME/.cache` (06 §1.1). The device cache root for
/// disposable, regenerable data such as the open/view read-only expansion of CAS
/// objects — deliberately separate from the durable `$XDG_DATA_HOME` (P9).
fn cache_home() -> PathBuf {
    // R12-6 / R13-6: empty/relative `XDG_CACHE_HOME` or `HOME` are invalid.
    if let Some(path) = kcs_core::xdg::xdg_dir("XDG_CACHE_HOME") {
        return path;
    }
    if let Some(home) = kcs_core::xdg::home_dir() {
        return home.join(".cache");
    }
    PathBuf::from(".")
}

/// R13-6: fail loudly at startup when neither `XDG_*` nor an absolute `HOME` can
/// anchor the device-global directories, instead of silently scattering
/// device-global state (registry, cost ledger, logs, the 0600 cursor-key) and the
/// device budget cap into a CWD-relative `kcs/`. R12-6 fixed the `XDG_*` side; the
/// `HOME` fallback still degraded to `PathBuf::from(".")`. Checked once per command
/// (every command touches at least logs/registry), so `env -u HOME` with no XDG
/// override errors rather than writing under the working directory.
fn ensure_device_dirs_resolvable() -> Result<()> {
    if kcs_core::xdg::home_dir().is_some() {
        return Ok(());
    }
    for var in ["XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"] {
        if kcs_core::xdg::xdg_dir(var).is_none() {
            return Err(KcsError::invalid_usage(format!(
                "cannot resolve an absolute base directory for device-global state: \
                 set $HOME to an absolute path or export an absolute ${var} \
                 (KCS refuses to write device-global state under the working directory)"
            )));
        }
    }
    Ok(())
}

fn cost_ledger_path() -> PathBuf {
    data_home().join("kcs/cost-ledger.jsonl")
}

/// F8: the device-global lock guarding the cost-ledger budget read-check-append.
/// The ledger is shared by every scope on the device, so its own `.kcs/.lock`
/// (scope-scoped) cannot serialize two scopes charging concurrently. This single
/// file lock does.
fn cost_ledger_lock_path() -> PathBuf {
    data_home().join("kcs/cost-ledger.lock")
}

/// Device-local HMAC key that signs search cursors (O1(b)). Stored at
/// `$XDG_DATA_HOME/kcs/cursor-key` (0600), generated from the operating system's
/// cryptographically secure random source on first use. Signing binds a cursor
/// to this device so a caller cannot forge or tamper a token to jump scope or
/// page — `query_hash` alone covers only public inputs.
fn cursor_signing_key() -> Result<Vec<u8>> {
    let path = data_home().join("kcs/cursor-key");
    if let Ok(bytes) = fs::read(&path) {
        if !bytes.is_empty() {
            return Ok(bytes);
        }
    }
    let key = random_key_32()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    }
    // `create_new` so a concurrent generator does not clobber; on a lost race read
    // the winner's key so both processes agree. P8: create the file 0600 *before*
    // any bytes are written (via `OpenOptionsExt::mode`) rather than chmod-ing
    // after `write_all`, which left a window where the 32-byte HMAC signing key
    // was readable at the umask default (0644).
    let mut open_options = OpenOptions::new();
    open_options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        open_options.mode(0o600);
    }
    match open_options.open(&path) {
        Ok(mut file) => {
            file.write_all(&key)
                .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
            Ok(key)
        }
        Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => fs::read(&path)
            .map_err(|read_err| KcsError::io(read_err.to_string(), path.display().to_string()))
            .and_then(|bytes| {
                if bytes.is_empty() {
                    Err(KcsError::io(err.to_string(), path.display().to_string()))
                } else {
                    Ok(bytes)
                }
            }),
        Err(err) => Err(KcsError::io(err.to_string(), path.display().to_string())),
    }
}

/// 32 fresh bytes from the operating system's cryptographically secure random
/// source. `getrandom` selects the native source on each supported platform.
fn random_key_32() -> Result<Vec<u8>> {
    let mut buf = vec![0u8; 32];
    getrandom::fill(&mut buf).map_err(|err| {
        KcsError::io(
            format!("operating system random source failed: {err}"),
            "operating system random source",
        )
    })?;
    Ok(buf)
}

fn adapter_to_kcs(error: kcs_adapter::AdapterError) -> KcsError {
    match error {
        // R13-2: `keychain:` auth is a LOUD not-implemented error (never a silent
        // noop), surfaced with its own code + a non-zero exit rather than folded
        // into the generic schema error.
        kcs_adapter::AdapterError::NotImplemented(message) => KcsError::new(
            "KCS-E-NOT-IMPLEMENTED-001",
            message,
            json!({}),
            ExitCode::Failure,
        ),
        other => KcsError::schema(other.to_string()),
    }
}

fn pipeline_to_kcs(error: kcs_pipeline::PipelineError) -> KcsError {
    match error {
        // M1(c): a corrupt persisted store file is exit 4 (KCS-E-STORE-CORRUPT-001),
        // not a schema/config error (exit 2). The path is preserved in context.
        kcs_pipeline::PipelineError::Corrupt { path, message } => KcsError::new(
            "KCS-E-STORE-CORRUPT-001",
            format!("corrupt store file at {path}: {message}"),
            json!({ "path": path }),
            ExitCode::PermanentFailure,
        ),
        // P1: a task whose input_path escapes the scope is KCS-E-STORE-PATH-001
        // (exit 2), the same contract as an out-of-scope tree entry path. The
        // offending path stays in context (redacted in logs), never in the message.
        kcs_pipeline::PipelineError::Path { path } => KcsError::new(
            "KCS-E-STORE-PATH-001",
            "task input_path must be a scope-local file name (no separators or `..` traversal)",
            json!({ "path": path }),
            ExitCode::InvalidUsage,
        ),
        kcs_pipeline::PipelineError::Locked { path } => KcsError::locked(path),
        kcs_pipeline::PipelineError::Io { path, message } => KcsError::io(message, path),
        kcs_pipeline::PipelineError::Contract { code, message } => {
            KcsError::new(code, message, json!({}), ExitCode::Failure)
        }
        other => KcsError::schema(other.to_string()),
    }
}

fn print_output(value: Value, json_mode: bool) {
    if json_mode {
        println!(
            "{}",
            serde_json::to_string(&value).expect("serializing command output cannot fail")
        );
        return;
    }

    // M2: `kcs view` (non --json) must print the chunk body, not just the
    // "viewed" status. When the payload carries a `text` field (view / chunk
    // object resolution), print the body — that is the point of `view`.
    if let Some(text) = value.get("text").and_then(Value::as_str) {
        println!("{}", terminal_safe_text(text, true));
    } else if let Some(status) = value.get("status").and_then(Value::as_str) {
        println!("{}", terminal_safe_text(status, false));
    } else if let Some(commits) = value.get("commits").and_then(Value::as_array) {
        for commit in commits {
            println!(
                "{} {} {}",
                terminal_safe_text(commit["commit_hash"].as_str().unwrap_or_default(), false),
                terminal_safe_text(commit["created_at"].as_str().unwrap_or_default(), false),
                terminal_safe_text(commit["message"].as_str().unwrap_or_default(), false)
            );
        }
    } else if let Some(changes) = value.get("changes").and_then(Value::as_array) {
        for change in changes {
            println!(
                "{} {}",
                terminal_safe_text(change["change"].as_str().unwrap_or_default(), false),
                terminal_safe_text(change["relative_path"].as_str().unwrap_or_default(), false)
            );
        }
    } else if let Some(files) = value.get("files").and_then(Value::as_array) {
        for file in files {
            println!(
                "{} {}",
                terminal_safe_text(file["status"].as_str().unwrap_or_default(), false),
                terminal_safe_text(file["relative_path"].as_str().unwrap_or_default(), false)
            );
        }
    } else {
        let rendered =
            serde_json::to_string_pretty(&value).expect("serializing command output cannot fail");
        println!("{}", terminal_safe_text(&rendered, true));
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
        eprintln!(
            "{}: {}",
            terminal_safe_text(error.error_code(), false),
            terminal_safe_text(error.message(), false)
        );
    }
}

/// Make lower-trust repository/provider text inert before writing it to a terminal.
/// Structured JSON output is serialized separately and retains the logical value.
fn terminal_safe_text(input: &str, allow_newlines: bool) -> String {
    let mut output = String::with_capacity(input.len());
    for ch in input.chars() {
        if allow_newlines && ch == '\n' {
            output.push(ch);
            continue;
        }
        let code = ch as u32;
        let terminal_active = matches!(code, 0x00..=0x1f | 0x7f..=0x9f)
            || matches!(code, 0x061c | 0x200e..=0x200f | 0x2028..=0x202e | 0x2066..=0x2069);
        if terminal_active {
            if code <= 0xff {
                output.push_str(&format!("\\x{code:02x}"));
            } else {
                output.push_str(&format!("\\u{{{code:04x}}}"));
            }
        } else {
            output.push(ch);
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use clap::Parser;
    use kcs_adapter::catalog::deterministic_embedding_vector;

    use super::{command_captured_json_flag, terminal_safe_text, Cli, Command};

    #[test]
    fn ct4_rebuild_refuses_visible_purge_and_filters_its_raw() {
        use super::{ensure_no_visible_purge_journal, purge_blocks_rebuild_raw};
        use kcs_core::purge::{BeginOutcome, PurgePhase, PurgeReason, PurgeState, TombstoneMode};

        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        std::fs::create_dir_all(&kcs_dir).unwrap();
        let raw_hash = kcs_pipeline::prepare::hash_bytes(b"purge barrier rebuild target");
        let state = PurgeState::new(&kcs_dir);
        let journal = match state
            .begin(
                vec![raw_hash.clone()],
                PurgeReason::Privacy,
                TombstoneMode::Default,
                "2026-07-13T00:00:00Z",
            )
            .unwrap()
        {
            BeginOutcome::Started(journal) => journal,
            other => panic!("unexpected begin outcome: {other:?}"),
        };

        // Prepared is not yet public. Once the barrier is durable, every rebuild
        // entry point fails before writing and its target is filtered per raw.
        ensure_no_visible_purge_journal(&kcs_dir).unwrap();
        assert!(!purge_blocks_rebuild_raw(&kcs_dir, &raw_hash).unwrap());
        state
            .advance_phase(&journal, PurgePhase::BarrierPublished)
            .unwrap();
        let error = ensure_no_visible_purge_journal(&kcs_dir).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-PURGE-INCOMPLETE-001");
        assert!(purge_blocks_rebuild_raw(&kcs_dir, &raw_hash).unwrap());
    }

    #[test]
    fn ct4_purge_004_erase_receipt_is_not_retained_embedding_liveness() {
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        std::fs::create_dir_all(&kcs_dir).unwrap();
        let raw_hash = kcs_pipeline::prepare::hash_bytes(b"explicitly reintroduced raw");
        let profile_hash = kcs_pipeline::prepare::hash_bytes(b"profile");
        let commit_hash = kcs_pipeline::prepare::hash_bytes(b"commit");
        let receipt = kcs_core::purge::EraseReceipt::new(
            raw_hash.clone(),
            commit_hash.clone(),
            "2026-07-13T00:00:00Z",
        )
        .unwrap();
        let purge = kcs_core::purge::PurgeState::new(&kcs_dir);
        let receipt_path = purge.erase_receipt_path(&raw_hash).unwrap();
        std::fs::create_dir_all(receipt_path.parent().unwrap()).unwrap();
        std::fs::write(&receipt_path, serde_json::to_vec(&receipt).unwrap()).unwrap();

        let conn = rusqlite::Connection::open_in_memory().unwrap();
        conn.execute_batch(
            "CREATE TABLE chunks (
                 rowid INTEGER PRIMARY KEY,
                 chunk_id TEXT NOT NULL,
                 text TEXT NOT NULL,
                 text_hash TEXT NOT NULL,
                 raw_hash TEXT NOT NULL,
                 tool_profile_hash TEXT NOT NULL,
                 gen INTEGER NOT NULL,
                 first_seen_commit TEXT
             );
             CREATE TABLE chunk_config_generations (
                 chunk_id TEXT NOT NULL,
                 chunking_config_hash TEXT NOT NULL
             );",
        )
        .unwrap();
        let chunk_id = kcs_pipeline::prepare::hash_bytes(b"chunk");
        let text_hash = kcs_pipeline::prepare::hash_bytes(b"searchable text");
        conn.execute(
            "INSERT INTO chunks
             (chunk_id,text,text_hash,raw_hash,tool_profile_hash,gen,first_seen_commit)
             VALUES (?1,'searchable text',?2,?3,?4,0,?5)",
            rusqlite::params![chunk_id, text_hash, raw_hash, profile_hash, commit_hash],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO chunk_config_generations(chunk_id,chunking_config_hash)
             VALUES (?1,'config')",
            rusqlite::params![chunk_id],
        )
        .unwrap();
        let retained = vec![super::RetainedNormalizedInstance {
            raw_hash,
            normalize: kcs_core::dag::NormalizeRef {
                tool_profile_hash: profile_hash,
                gen: 0,
            },
            raw_path: "reintroduced.md".to_owned(),
            embedding_path: "reintroduced.md".to_owned(),
            first_seen_commit: commit_hash,
        }];
        let chunks = super::retained_history_chunks(&conn, &kcs_dir, &retained, "config").unwrap();
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].chunk_id, chunk_id);
    }

    #[test]
    fn r23_cand_059_human_output_escapes_terminal_controls() {
        let input = "safe\x1b]8;;https://example.invalid\x07label\x1b]8;;\x07\u{202e}";
        let rendered = terminal_safe_text(input, false);
        assert!(!rendered.contains('\x1b'));
        assert!(!rendered.contains('\x07'));
        assert!(!rendered.contains('\u{202e}'));
        assert!(rendered.contains("\\x1b"));
        assert!(rendered.contains("\\x07"));
        assert!(rendered.contains("\\u{202e}"));

        for control in [
            '\u{061c}', '\u{200e}', '\u{200f}', '\u{2028}', '\u{2029}', '\u{202a}', '\u{202b}',
            '\u{202c}', '\u{202d}', '\u{202e}', '\u{2066}', '\u{2067}', '\u{2068}', '\u{2069}',
        ] {
            let escaped = terminal_safe_text(&control.to_string(), false);
            assert!(!escaped.contains(control));
            assert!(escaped.starts_with("\\u{"));
        }
    }

    #[test]
    fn r23_cand_059_document_body_preserves_only_newline_control() {
        assert_eq!(
            terminal_safe_text("line 1\nline\t2\r", true),
            "line 1\nline\\x092\\x0d"
        );
    }

    #[test]
    fn r23_aggregate_index_status_fails_closed_for_corrupt_scope_state() {
        use super::{compute_index_status, SearchedScopeInfo};
        use kcs_core::scope::Repository;

        let healthy_root = tempfile::tempdir().unwrap();
        let corrupt_root = tempfile::tempdir().unwrap();
        let vanished_root = tempfile::tempdir().unwrap();
        Repository::init(healthy_root.path()).unwrap();
        let corrupt_repo = Repository::init(corrupt_root.path()).unwrap();
        std::fs::write(corrupt_repo.kcs_dir().join("tasks.jsonl"), b"not-json\n").unwrap();
        std::fs::write(
            corrupt_repo.kcs_dir().join("unsupported-inputs.jsonl"),
            b"not-json\n",
        )
        .unwrap();

        let searched = [
            SearchedScopeInfo {
                scope_id: "healthy".to_owned(),
                scope_path: healthy_root.path().to_path_buf(),
                snapshot_at: "sha256:healthy".to_owned(),
                max_rowid: 0,
                max_association_rowid: 0,
                chunking_config_hash: "sha256:config".to_owned(),
            },
            SearchedScopeInfo {
                scope_id: "corrupt".to_owned(),
                scope_path: corrupt_root.path().to_path_buf(),
                snapshot_at: "sha256:corrupt".to_owned(),
                max_rowid: 0,
                max_association_rowid: 0,
                chunking_config_hash: "sha256:config".to_owned(),
            },
            SearchedScopeInfo {
                scope_id: "vanished".to_owned(),
                scope_path: vanished_root.path().to_path_buf(),
                snapshot_at: "sha256:vanished".to_owned(),
                max_rowid: 0,
                max_association_rowid: 0,
                chunking_config_hash: "sha256:config".to_owned(),
            },
        ];

        let status = compute_index_status(&searched);
        assert_eq!(status["tasks_complete"], false);
        assert_eq!(status["unsupported_inputs_complete"], false);
        assert_eq!(status["task_errors"].as_array().unwrap().len(), 2);
        assert_eq!(
            status["unsupported_input_errors"].as_array().unwrap().len(),
            2
        );
        for field in ["task_errors", "unsupported_input_errors"] {
            assert!(status[field].as_array().unwrap().iter().any(|error| {
                error["scope_path"]
                    .as_str()
                    .is_some_and(|path| std::path::Path::new(path) == vanished_root.path())
            }));
        }
        assert!(status["task_errors"][0]["error_code"]
            .as_str()
            .unwrap()
            .contains("STORE-CORRUPT"));
        assert!(status["unsupported_input_errors"][0]["error_code"]
            .as_str()
            .unwrap()
            .contains("STORE-CORRUPT"));
    }

    #[test]
    fn r23_cand_001_terminal_failure_does_not_spawn_releasable_secret_hold() {
        use super::{
            embedding_task_output_ref, hold_secret_embedding_tasks, release_secret_holds,
            EmbeddableChunk,
        };
        use kcs_core::scope::Repository;
        use kcs_pipeline::task::{TaskDescriptor, TaskStatus, TaskStore, TaskType};

        let root = tempfile::tempdir().unwrap();
        let repo = Repository::init(root.path()).unwrap();
        let store = TaskStore::new(repo.kcs_dir());
        let chunk_id = format!("sha256:{}", "a".repeat(64));
        let output_ref = embedding_task_output_ref(&chunk_id);
        store
            .append(&TaskDescriptor {
                task_id: "task_terminal".to_owned(),
                task_type: TaskType::Embedding,
                mode: None,
                input_path: "credentials_backup.md".to_owned(),
                input_hash: format!("sha256:{}", "b".repeat(64)),
                previous_raw_hash: None,
                parent_run_id: None,
                changed_unit_keys: vec![chunk_id.clone()],
                output_ref: output_ref.clone(),
                unit_keys: None,
                status: TaskStatus::Failed,
                attempts: 1,
                next_retry_at: None,
                deadline: None,
                heartbeat_at: None,
                fallback_reason: Some("contract_violation".to_owned()),
                created_at: "2026-07-12T00:00:00Z".to_owned(),
                bbox_annotation_enabled: None,
                reserved_usd: None,
                reserved_month: None,
                reservation_id: None,
            })
            .unwrap();

        hold_secret_embedding_tasks(
            &store,
            &repo,
            &[EmbeddableChunk {
                chunk_id,
                text: "secret".to_owned(),
                text_hash: format!("sha256:{}", "b".repeat(64)),
                raw_path: "credentials_backup.md".to_owned(),
                requires_secret_approval: true,
            }],
            "2026-07-12T00:00:01Z",
        )
        .unwrap();

        let tasks = store.all().unwrap();
        assert_eq!(
            tasks.len(),
            1,
            "terminal state must not gain a duplicate hold"
        );
        assert_eq!(tasks[0].output_ref, output_ref);
        assert_eq!(tasks[0].status, TaskStatus::Failed);
        assert_eq!(
            tasks[0].fallback_reason.as_deref(),
            Some("contract_violation")
        );
        assert_eq!(release_secret_holds(&repo).unwrap(), 0);
        assert_eq!(store.all().unwrap()[0].status, TaskStatus::Failed);
    }

    #[test]
    fn r23_cand_001_legacy_duplicate_hold_cannot_override_terminal_failure() {
        use super::{
            embedding_task_output_ref, filter_embeddable_by_task_state, release_secret_holds,
            EmbeddableChunk, SECRETS_TIER_B_HOLD,
        };
        use kcs_core::scope::Repository;
        use kcs_pipeline::task::{TaskDescriptor, TaskStatus, TaskStore, TaskType};

        let root = tempfile::tempdir().unwrap();
        let repo = Repository::init(root.path()).unwrap();
        let store = TaskStore::new(repo.kcs_dir());
        let chunk_id = format!("sha256:{}", "c".repeat(64));
        let output_ref = embedding_task_output_ref(&chunk_id);
        let terminal = TaskDescriptor {
            task_id: "task_terminal_legacy".to_owned(),
            task_type: TaskType::Embedding,
            mode: None,
            input_path: "credentials_backup.md".to_owned(),
            input_hash: format!("sha256:{}", "d".repeat(64)),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: vec![chunk_id.clone()],
            output_ref: output_ref.clone(),
            unit_keys: None,
            status: TaskStatus::Failed,
            attempts: 1,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: Some("contract_violation".to_owned()),
            created_at: "2026-07-12T00:00:00Z".to_owned(),
            bbox_annotation_enabled: None,
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        };
        let mut legacy_hold = terminal.clone();
        legacy_hold.task_id = "task_later_hold".to_owned();
        legacy_hold.status = TaskStatus::Paused;
        legacy_hold.attempts = 0;
        legacy_hold.fallback_reason = Some(SECRETS_TIER_B_HOLD.to_owned());
        legacy_hold.created_at = "2026-07-12T00:00:01Z".to_owned();
        store.append(&terminal).unwrap();
        store.append(&legacy_hold).unwrap();

        assert_eq!(release_secret_holds(&repo).unwrap(), 1);
        let tasks = store.all().unwrap();
        assert_eq!(tasks.len(), 1, "legacy duplicate hold should be removed");
        assert!(tasks.iter().any(|task| {
            task.task_id == "task_terminal_legacy"
                && task.status == TaskStatus::Failed
                && task.fallback_reason.as_deref() == Some("contract_violation")
        }));

        let mut poisoned_pending = terminal.clone();
        poisoned_pending.task_id = "zzzz_later_pending".to_owned();
        poisoned_pending.status = TaskStatus::Pending;
        poisoned_pending.fallback_reason = None;
        poisoned_pending.created_at = "2026-07-12T00:00:02Z".to_owned();
        store.append(&poisoned_pending).unwrap();

        let sendable = filter_embeddable_by_task_state(
            &store,
            vec![EmbeddableChunk {
                chunk_id,
                text: "must not send".to_owned(),
                text_hash: format!("sha256:{}", "d".repeat(64)),
                raw_path: "credentials_backup.md".to_owned(),
                requires_secret_approval: true,
            }],
            false,
        )
        .unwrap();
        assert!(sendable.is_empty());
        assert_eq!(tasks[0].output_ref, output_ref);
    }

    #[test]
    fn r23_secret_classification_preserves_retry_backoff_state() {
        use super::{embedding_task_output_ref, hold_secret_embedding_tasks, EmbeddableChunk};
        use kcs_core::scope::Repository;
        use kcs_pipeline::task::{TaskDescriptor, TaskStatus, TaskStore, TaskType};

        let root = tempfile::tempdir().unwrap();
        let repo = Repository::init(root.path()).unwrap();
        let store = TaskStore::new(repo.kcs_dir());
        let chunk_id = format!("sha256:{}", "e".repeat(64));
        let output_ref = embedding_task_output_ref(&chunk_id);
        store
            .append(&TaskDescriptor {
                task_id: "task_retry_backoff".to_owned(),
                task_type: TaskType::Embedding,
                mode: None,
                input_path: "credentials_backup.md".to_owned(),
                input_hash: format!("sha256:{}", "f".repeat(64)),
                previous_raw_hash: None,
                parent_run_id: None,
                changed_unit_keys: vec![chunk_id.clone()],
                output_ref,
                unit_keys: None,
                status: TaskStatus::Failed,
                attempts: 3,
                next_retry_at: Some("2099-01-01T00:00:00Z".to_owned()),
                deadline: None,
                heartbeat_at: None,
                fallback_reason: Some("network_error".to_owned()),
                created_at: "2026-07-12T00:00:00Z".to_owned(),
                bbox_annotation_enabled: None,
                reserved_usd: None,
                reserved_month: None,
                reservation_id: None,
            })
            .unwrap();

        hold_secret_embedding_tasks(
            &store,
            &repo,
            &[EmbeddableChunk {
                chunk_id,
                text: "retryable".to_owned(),
                text_hash: format!("sha256:{}", "f".repeat(64)),
                raw_path: "credentials_backup.md".to_owned(),
                requires_secret_approval: true,
            }],
            "2026-07-12T00:00:01Z",
        )
        .unwrap();

        let tasks = store.all().unwrap();
        assert_eq!(tasks.len(), 1);
        assert_eq!(tasks[0].status, TaskStatus::Failed);
        assert_eq!(tasks[0].attempts, 3);
        assert_eq!(
            tasks[0].next_retry_at.as_deref(),
            Some("2099-01-01T00:00:00Z")
        );
        assert_eq!(tasks[0].fallback_reason.as_deref(), Some("network_error"));
    }

    #[test]
    fn r23_cand_057_scan_budget_charges_failures_and_caps_empty_entries() {
        use super::WorkingTreeScanBudget;

        let mut failed = WorkingTreeScanBudget {
            remaining_bytes: 10,
            remaining_entries: 2,
        };
        assert!(failed.consume_entry());
        let attempt = failed.reserve_file(u64::MAX).unwrap();
        assert_eq!(attempt.max_bytes, 9);
        assert_eq!(attempt.reserved_bytes, 10);
        assert_eq!(failed.remaining_bytes, 0);
        assert!(failed.reserve_file(0).is_none());

        let mut empty = WorkingTreeScanBudget {
            remaining_bytes: 10,
            remaining_entries: 2,
        };
        for _ in 0..2 {
            assert!(empty.consume_entry());
            let attempt = empty.reserve_file(0).unwrap();
            assert_eq!(attempt.max_bytes, 0);
            empty.finish_success(&attempt, 0);
            assert_eq!(empty.remaining_bytes, 10);
        }
        assert!(!empty.consume_entry());

        let mut valid = WorkingTreeScanBudget {
            remaining_bytes: 10,
            remaining_entries: 1,
        };
        assert!(valid.consume_entry());
        let attempt = valid.reserve_file(4).unwrap();
        valid.finish_success(&attempt, 4);
        assert_eq!(valid.remaining_bytes, 6);
    }

    #[test]
    fn r23_markdown_charge_and_send_share_one_verified_input() {
        use super::{
            classify_online_markdownize_precondition, estimate_online_markdownize_cost,
            prorated_markdownize_cost, OnlineMarkdownizePrecondition,
        };
        use kcs_core::scope::Repository;
        use kcs_pipeline::prepare::hash_bytes;
        use kcs_pipeline::task::{TaskDescriptor, TaskStatus, TaskType};

        let root = tempfile::tempdir().unwrap();
        let repo = Repository::init(root.path()).unwrap();
        let pdf = b"%PDF-1.4\n1 0 obj << /Type /Pages /Kids [2 0 R] /Count 1 >> endobj\n2 0 obj << /Type /Page /Parent 1 0 R >> stream\nBT (verified billing input) Tj ET\nendstream endobj\n%%EOF\n";
        std::fs::write(root.path().join("doc.pdf"), pdf).unwrap();
        let task = TaskDescriptor {
            task_id: "task_verified_charge".to_owned(),
            task_type: TaskType::Markdownize,
            mode: None,
            input_path: "doc.pdf".to_owned(),
            input_hash: hash_bytes(pdf),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: Vec::new(),
            output_ref: "online:mistral_ocr_markdownize".to_owned(),
            unit_keys: None,
            status: TaskStatus::Pending,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: Some("ready_for_online_adapter".to_owned()),
            created_at: "2026-07-12T00:00:00Z".to_owned(),
            bbox_annotation_enabled: None,
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        };

        let prepared = match classify_online_markdownize_precondition(&repo, &task) {
            OnlineMarkdownizePrecondition::Send(prepared) => prepared,
            _ => panic!("valid text-bearing PDF must reach the prepared send state"),
        };
        let valid_unit_key = prepared.prepared_units[0].unit_key.clone();
        for unit_keys in [
            Vec::new(),
            vec!["unknown-unit".to_owned()],
            vec![valid_unit_key.clone(), valid_unit_key.clone()],
        ] {
            let mut invalid = task.clone();
            invalid.unit_keys = Some(unit_keys);
            assert!(matches!(
                classify_online_markdownize_precondition(&repo, &invalid),
                OnlineMarkdownizePrecondition::Retire
            ));
        }
        let mut valid_retry = task.clone();
        valid_retry.unit_keys = Some(vec![valid_unit_key]);
        assert!(matches!(
            classify_online_markdownize_precondition(&repo, &valid_retry),
            OnlineMarkdownizePrecondition::Send(_)
        ));
        std::fs::write(root.path().join("doc.pdf"), b"").unwrap();

        assert_eq!(prepared.bytes, pdf);
        assert!(!prepared.prepared_units.is_empty());
        let charged = prorated_markdownize_cost(
            &task,
            prepared.bytes.len() as u64,
            prepared.prepared_units.len(),
            true,
        );
        assert_eq!(
            charged,
            estimate_online_markdownize_cost(pdf.len() as u64, true)
        );
        assert_eq!(
            estimate_online_markdownize_cost(pdf.len() as u64, true),
            estimate_online_markdownize_cost(pdf.len() as u64, false) * 1.25
        );
        assert!(
            charged > 0.0,
            "a post-check pathname change cannot mint a zero charge"
        );
    }

    #[test]
    fn r12_1_read_search_tuning_parses_documented_keys() {
        use super::{read_search_tuning, DiversifyStrategy};
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        std::fs::write(
            &path,
            "[search.rrf]\nk = 5\nw_text = 0.0\nw_vector = 2.0\ncandidate_depth = 7\n\
             [search.diversify]\nenabled = true\nstrategy = \"off\"\nmax_per_raw_hash = 1\n",
        )
        .unwrap();
        let tuning = read_search_tuning(&path).unwrap();
        assert_eq!(tuning.rrf_k, Some(5));
        assert_eq!(tuning.rrf_w_text, Some(0.0));
        assert_eq!(tuning.rrf_w_vector, Some(2.0));
        assert_eq!(tuning.rrf_candidate_depth, Some(7));
        assert_eq!(tuning.div_enabled, Some(true));
        assert_eq!(tuning.div_strategy, Some(DiversifyStrategy::Off));
        assert_eq!(tuning.div_max_per_raw_hash, Some(1));
        // Absent file -> every field None (falls back to defaults at resolution).
        let empty = read_search_tuning(&dir.path().join("nope.toml")).unwrap();
        assert!(empty.rrf_k.is_none() && empty.div_strategy.is_none());
    }

    #[test]
    fn r12_1_read_incremental_tuning_parses_documented_keys() {
        use super::read_incremental_tuning;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        std::fs::write(
            &path,
            "[markdownize.incremental]\nenabled = false\nthreshold = 0.5\nmax_consecutive = 9\n",
        )
        .unwrap();
        let (enabled, threshold, max_consecutive) = read_incremental_tuning(&path).unwrap();
        assert_eq!(enabled, Some(false));
        assert_eq!(threshold, Some(0.5));
        assert_eq!(max_consecutive, Some(9));
        // Absent file -> all None.
        let (e, t, m) = read_incremental_tuning(&dir.path().join("nope.toml")).unwrap();
        assert!(e.is_none() && t.is_none() && m.is_none());
    }

    #[test]
    fn ct4_bbox_001_reads_default_and_scope_over_user_annotation_policy() {
        use super::{effective_bbox_annotation_policy, read_bbox_annotation_config};

        let dir = tempfile::tempdir().unwrap();
        let scope = dir.path().join("scope.toml");
        let user = dir.path().join("user.toml");
        assert!(effective_bbox_annotation_policy(&scope, &user));

        std::fs::write(&user, "[markdownize.bbox_annotation]\nenabled = false\n").unwrap();
        assert_eq!(read_bbox_annotation_config(&user), Some(false));
        assert!(!effective_bbox_annotation_policy(&scope, &user));

        std::fs::write(&scope, "[markdownize.bbox_annotation]\nenabled = true\n").unwrap();
        assert!(effective_bbox_annotation_policy(&scope, &user));
    }

    #[test]
    fn r10_1_vector_capacity_message_classifier() {
        use super::is_vector_capacity_message;
        // R10-1(a): sqlite-vec's KNN k-ceiling and SQLite's bound-variable ceiling are
        // capacity limits (degrade the scope), not schema faults.
        assert!(is_vector_capacity_message(
            "index sqlite error: k value in knn query too large, provided 4200 and the limit is 4096"
        ));
        assert!(is_vector_capacity_message(
            "index sqlite error: too many SQL variables"
        ));
        // A genuine schema/contract error is NOT a capacity limit.
        assert!(!is_vector_capacity_message(
            "index schema error: no such column"
        ));
        assert!(!is_vector_capacity_message("some other failure"));
    }

    #[test]
    fn r11_10_keyword_groups_are_capped_at_64() {
        use super::build_fts_tiers;
        // 200 distinct ASCII keywords (>= 3 chars). Before R11-10 every one became an
        // OR clause; now the keyword groups are capped at 64 like the CJK trigrams.
        let query = (0..200)
            .map(|i| format!("kw{i:04}"))
            .collect::<Vec<_>>()
            .join(" ");
        let tiers = build_fts_tiers(&query);
        assert!(
            !tiers.is_empty(),
            "a long keyword query must still build a tier"
        );
        // No CJK → no trigram phrases, so each tier is purely keyword OR-groups.
        // Every tier must be capped (group count = " OR " separators + 1).
        for tier in &tiers {
            let group_count = tier.matches(" OR ").count() + 1;
            assert!(
                group_count <= 64,
                "keyword groups must be capped at 64, got {group_count}: {tier}"
            );
        }
    }

    #[test]
    fn ct4_eval_mixed_script_query_keeps_cjk_context_in_first_tier() {
        use super::build_fts_tiers;

        let tiers = build_fts_tiers("RAG パイプラインで再ランクに Merlin を使う 5 段構成の資料");
        assert_eq!(tiers.len(), 1);
        assert!(tiers[0].contains("\"RAG\""));
        assert!(tiers[0].contains("\"Merlin\""));
        assert!(tiers[0].contains("\"再ラン\""));
        assert!(tiers[0].contains("\"段構成\""));
    }

    #[test]
    fn ct4_eval_english_retrieval_terms_expand_to_japanese_index_terms() {
        use super::build_fts_tiers;

        let tiers = build_fts_tiers("chunk size was 512 tokens in the retrieval pipeline doc");
        assert!(!tiers.is_empty());
        assert!(tiers[0].contains("\"チャンク\""));
        assert!(tiers[0].contains("\"トークン\""));
        assert!(tiers[0].contains("\"パイプライン\""));
        assert!(tiers[0].matches(" OR ").count() < 64);
    }

    #[test]
    fn r11_2_exit_override_priority_batch_vs_enrichment() {
        use super::{batch_exit_override, enrichment_exit_override, ExecOutcome};
        use kcs_core::ExitCode;

        // A clean pass overrides nothing (exit 0).
        assert!(batch_exit_override(&ExecOutcome::default()).is_none());
        assert!(enrichment_exit_override(&ExecOutcome::default()).is_none());

        // Batch priority: auth (5) > budget-paused (6) > some-retryable (3) >
        // all-permanent (4).
        let all = ExecOutcome {
            executed: 1,
            failed: 3,
            paused: 1,
            auth_failed: 1,
            failed_retryable: 1,
        };
        assert_eq!(batch_exit_override(&all), Some(ExitCode::AuthError));
        assert_eq!(
            batch_exit_override(&ExecOutcome {
                auth_failed: 0,
                ..all
            }),
            Some(ExitCode::BudgetExceeded)
        );
        assert_eq!(
            batch_exit_override(&ExecOutcome {
                auth_failed: 0,
                paused: 0,
                ..all
            }),
            Some(ExitCode::PartialFailure)
        );
        // Failures present but none retryable / auth / paused → all permanent (4).
        assert_eq!(
            batch_exit_override(&ExecOutcome {
                failed: 2,
                ..ExecOutcome::default()
            }),
            Some(ExitCode::PermanentFailure)
        );

        // Enrichment (index/repair/reindex) overrides ONLY on auth (5) / budget (6);
        // a retryable/permanent embedding failure stays exit 0 (disclosed in JSON).
        assert_eq!(
            enrichment_exit_override(&ExecOutcome {
                auth_failed: 1,
                ..ExecOutcome::default()
            }),
            Some(ExitCode::AuthError)
        );
        assert_eq!(
            enrichment_exit_override(&ExecOutcome {
                paused: 1,
                ..ExecOutcome::default()
            }),
            Some(ExitCode::BudgetExceeded)
        );
        assert!(enrichment_exit_override(&ExecOutcome {
            failed: 2,
            failed_retryable: 2,
            ..ExecOutcome::default()
        })
        .is_none());
    }

    #[test]
    fn r10_4_partial_retry_plan_gates_on_retryability_and_budget() {
        use super::{partial_retry_plan_from_manifest, unit_ref, NormalizedInstanceManifest};
        let manifest = |first_error: Option<&str>, second_error: Option<&str>| {
            serde_json::from_value::<NormalizedInstanceManifest>(serde_json::json!({
                "raw_hash": format!("sha256:{}", "a".repeat(64)),
                "tool_profile_hash": format!("sha256:{}", "b".repeat(64)),
                "gen": 0,
                "parent_gen": null,
                "run_id": "run_x",
                "units": [
                    {"order":0,"unit_key":"page:1","unit_ref":unit_ref("page:1"),"unit_type":"page","status":if first_error.is_some() { "failed" } else { "done" },"prepared_hash":format!("sha256:{}", "c".repeat(64)),"error_kind":first_error},
                    {"order":1,"unit_key":"page:2","unit_ref":unit_ref("page:2"),"unit_type":"page","status":if second_error.is_some() { "failed" } else { "done" },"prepared_hash":format!("sha256:{}", "d".repeat(64)),"error_kind":second_error},
                ],
                "generated_at": "2026-07-05T00:00:00Z",
            }))
            .unwrap()
        };

        // A Failed unit with a RETRYABLE kind is re-enqueued, with a finite budget.
        let plan = partial_retry_plan_from_manifest(&manifest(None, Some("network_error")));
        assert_eq!(plan.retryable_units, vec!["page:2".to_owned()]);
        assert_eq!(plan.max_attempts, Some(5));

        // A Failed unit with a NON-retryable (permanent) kind is never re-enqueued.
        let plan = partial_retry_plan_from_manifest(&manifest(None, Some("invalid_input")));
        assert!(plan.retryable_units.is_empty());

        // Mixed: only the retryable unit survives; a contract_violation is dropped.
        let plan = partial_retry_plan_from_manifest(&manifest(
            Some("contract_violation"),
            Some("network_error"),
        ));
        assert_eq!(plan.retryable_units, vec!["page:2".to_owned()]);
    }

    #[test]
    fn r10_5_persist_failure_is_retryable() {
        use super::{persist_failure_retry_kind, retry_policy};
        // R10-5: a post-OCR persist I/O fault must be retryable so `batch retry` can
        // recover the already-billed normalized output.
        assert!(retry_policy(persist_failure_retry_kind()).retryable);
    }

    #[test]
    fn r10_6_open_cache_path_uses_full_hash() {
        use super::open_cache_path;
        // R10-6: the per-object cache dir is the FULL 64-hex sha256, not a 12-char
        // prefix, so a prefix+basename collision can't serve the wrong object.
        let hash = format!("sha256:{}", "a".repeat(64));
        let path = open_cache_path("doc.md", &hash);
        let dir = path
            .parent()
            .unwrap()
            .file_name()
            .unwrap()
            .to_str()
            .unwrap();
        assert_eq!(dir.len(), 64, "cache dir must be the full 64-hex hash");
        assert_eq!(dir, "a".repeat(64));
        let leaf = path.file_name().unwrap().to_str().unwrap();
        assert_ne!(leaf, "doc.md");
        assert!(leaf.starts_with("open-"));
        assert!(leaf.ends_with(".md"));
    }

    #[test]
    fn r10_6_open_cache_write_is_atomic_readonly_and_cleans_temp() {
        use super::write_open_cache_atomic;
        let dir = tempfile::tempdir().unwrap();
        let cache = dir.path().join("obj").join("doc.md");
        std::fs::create_dir_all(cache.parent().unwrap()).unwrap();
        write_open_cache_atomic(&cache, b"evidence bytes").unwrap();
        assert_eq!(std::fs::read(&cache).unwrap(), b"evidence bytes");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = std::fs::metadata(&cache).unwrap().permissions().mode() & 0o777;
            assert_eq!(mode, 0o400, "published cache file must be read-only 0400");
        }
        let stray: Vec<_> = std::fs::read_dir(cache.parent().unwrap())
            .unwrap()
            .filter_map(std::result::Result::ok)
            .filter(|entry| entry.file_name().to_string_lossy().starts_with(".tmp-"))
            .collect();
        assert!(stray.is_empty(), "no temp may remain: {stray:?}");
    }

    #[test]
    fn r10_6_open_cache_torn_write_leaves_no_temp() {
        use super::write_open_cache_atomic;
        // Force the rename to fail (destination is an existing directory) — a torn
        // write must clean its temp and never publish a partial file.
        let dir = tempfile::tempdir().unwrap();
        let cache = dir.path().join("doc.md");
        std::fs::create_dir(&cache).unwrap();
        let result = write_open_cache_atomic(&cache, b"bytes");
        assert!(result.is_err(), "write onto a directory must fail");
        let stray: Vec<_> = std::fs::read_dir(dir.path())
            .unwrap()
            .filter_map(std::result::Result::ok)
            .filter(|entry| entry.file_name().to_string_lossy().starts_with(".tmp-"))
            .collect();
        assert!(
            stray.is_empty(),
            "torn write must clean its temp: {stray:?}"
        );
    }

    #[test]
    fn r10_8_snapshot_tree_entries_insert_is_atomic() {
        use super::{insert_snapshot_tree_entries, TreeEntryProjection};
        use rusqlite::Connection;
        let conn = Connection::open_in_memory().unwrap();
        // A CHECK lets the test force a mid-batch failure deterministically.
        conn.execute_batch(
            "CREATE TABLE tree_entries (
                 commit_hash TEXT NOT NULL,
                 path TEXT NOT NULL,
                 raw_hash TEXT NOT NULL CHECK(raw_hash <> 'BAD'),
                 tool_profile_hash TEXT,
                 gen INTEGER NOT NULL DEFAULT 0,
                 PRIMARY KEY (commit_hash, path));",
        )
        .unwrap();
        let count = |conn: &Connection| -> i64 {
            conn.query_row(
                "SELECT COUNT(*) FROM tree_entries WHERE commit_hash='c1'",
                [],
                |row| row.get(0),
            )
            .unwrap()
        };
        // R10-8: a failing 2nd row rolls the 1st row back — the projection stays
        // all-or-nothing so `existing` remains 0 and the next read reprojects.
        let torn = vec![
            TreeEntryProjection {
                path: "a.md".to_owned(),
                raw_hash: "sha256:aa".to_owned(),
                tool_profile_hash: Some("sha256:tool".to_owned()),
                gen: 0,
            },
            TreeEntryProjection {
                path: "b.md".to_owned(),
                raw_hash: "BAD".to_owned(),
                tool_profile_hash: Some("sha256:tool".to_owned()),
                gen: 0,
            },
        ];
        assert!(insert_snapshot_tree_entries(&conn, "c1", &torn).is_err());
        assert_eq!(count(&conn), 0, "partial inserts must be rolled back");
        // A clean batch commits every row atomically.
        let good = vec![
            TreeEntryProjection {
                path: "a.md".to_owned(),
                raw_hash: "sha256:aa".to_owned(),
                tool_profile_hash: Some("sha256:tool".to_owned()),
                gen: 0,
            },
            TreeEntryProjection {
                path: "b.md".to_owned(),
                raw_hash: "sha256:bb".to_owned(),
                tool_profile_hash: None,
                gen: 1,
            },
        ];
        insert_snapshot_tree_entries(&conn, "c1", &good).unwrap();
        assert_eq!(count(&conn), 2);
    }

    #[test]
    fn r9_8_atomic_write_cas_object_removes_temp_on_failure() {
        use super::atomic_write_cas_object;
        // R9-8: a torn derived-CAS write must not leave an orphan `.tmp-*` in the
        // fanout dir. Force the rename to fail deterministically by making the
        // destination an existing directory after the temp is created + fsynced.
        let dir = tempfile::tempdir().unwrap();
        let dest = dir.path().join("obj");
        std::fs::create_dir(&dest).unwrap();
        let result = atomic_write_cas_object(dir.path(), &dest, b"derived-bytes");
        assert!(result.is_err(), "write onto a directory must fail");
        let stray: Vec<_> = std::fs::read_dir(dir.path())
            .unwrap()
            .filter_map(std::result::Result::ok)
            .map(|entry| entry.file_name().to_string_lossy().into_owned())
            .filter(|name| name.starts_with(".tmp-"))
            .collect();
        assert!(
            stray.is_empty(),
            "temp not cleaned up on failure: {stray:?}"
        );
    }

    #[test]
    fn r23_cand_031_existing_prepared_slot_must_match_exact_bytes() {
        use super::atomic_write_cas_object;

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("prepared-object");
        std::fs::write(&path, b"poison").unwrap();
        let error = atomic_write_cas_object(dir.path(), &path, b"secure").unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
        assert_eq!(std::fs::read(&path).unwrap(), b"poison");
    }

    #[cfg(unix)]
    #[test]
    fn r23_prepared_writer_rejects_symlinked_store_ancestor() {
        use std::os::unix::fs::symlink;

        use super::write_prepared_objects;
        use kcs_core::scope::Repository;
        use kcs_pipeline::prepare::{hash_bytes, PreparedUnit, UnitFingerprint, UnitType};

        let root = tempfile::tempdir().unwrap();
        let repo = Repository::init(root.path()).unwrap();
        let outside = tempfile::tempdir().unwrap();
        let prepared_root = repo.kcs_dir().join("objects/prepared");
        if prepared_root.exists() {
            std::fs::remove_dir_all(&prepared_root).unwrap();
        }
        std::fs::create_dir_all(prepared_root.parent().unwrap()).unwrap();
        symlink(outside.path(), &prepared_root).unwrap();
        let bytes = b"outside-write";
        let prepared_hash = hash_bytes(bytes);
        let unit = PreparedUnit {
            order: 0,
            unit_key: "file:0".to_owned(),
            unit_type: UnitType::File,
            prepared_hash: prepared_hash.clone(),
            fingerprint: UnitFingerprint {
                perceptual_hash: prepared_hash.clone(),
                text_hash: prepared_hash.clone(),
                visual_hash: prepared_hash.clone(),
            },
            mime: Some("text/plain".to_owned()),
            page_number: None,
        };

        let error = write_prepared_objects(&repo, &[unit], &[prepared_hash], bytes, "text/plain")
            .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
        assert!(std::fs::read_dir(outside.path()).unwrap().next().is_none());
    }

    #[test]
    fn r9_5_unit_file_and_orphan_temp_classification() {
        use super::{is_normalized_unit_file, is_orphan_temp_name};
        // Real unit files: 16 lowercase-hex chars + `.json`.
        assert!(is_normalized_unit_file("1a2b3c4d5e6f7089.json"));
        assert!(is_normalized_unit_file("0000000000000000.json"));
        // Not unit files — must be skipped by copy_normalized_instance_gen.
        assert!(!is_normalized_unit_file("manifest.json"));
        assert!(!is_normalized_unit_file(".DS_Store"));
        assert!(!is_normalized_unit_file(".tmp-99999-0000abcd"));
        assert!(!is_normalized_unit_file("1a2b3c4d5e6f7089.md")); // wrong ext
        assert!(!is_normalized_unit_file("1A2B3C4D5E6F7089.json")); // uppercase hex
        assert!(!is_normalized_unit_file("1a2b.json")); // too short
        assert!(!is_normalized_unit_file("1a2b3c4d5e6f7089z.json")); // 17 chars / non-hex
                                                                     // Orphan-temp detection (GC'd on reindex).
        assert!(is_orphan_temp_name(".tmp-99999-0000abcd"));
        assert!(is_orphan_temp_name(".1a2b3c4d5e6f7089.json.tmp-123-456"));
        assert!(!is_orphan_temp_name(".DS_Store"));
        assert!(!is_orphan_temp_name("manifest.json"));
    }

    #[test]
    fn mock_embedding_vector_is_deterministic_and_normalized() {
        let a = deterministic_embedding_vector("認証仕様 トークン", 768);
        let b = deterministic_embedding_vector("認証仕様 トークン", 768);
        assert_eq!(a.len(), 768);
        assert_eq!(a, b, "same seed must reproduce the same vector");
        let norm = a.iter().map(|value| value * value).sum::<f32>().sqrt();
        assert!((norm - 1.0).abs() < 1e-4, "vector must be L2-normalized");
        let other = deterministic_embedding_vector("別のクエリ", 768);
        assert_ne!(a, other, "different seeds must differ");
    }

    // F8: two serial charges must re-read the ledger under the device-global lock,
    // so the second sees the first's reservation and is denied when it would
    // exceed the cap — the cap is never breached even without concurrency, and the
    // ledger is not double-appended.
    #[test]
    fn f8_charge_serializes_reread_and_enforces_cap() {
        use super::{
            charge_cost_ledger_under_lock, BudgetCaps, BudgetEstimate, ChargeOutcome,
            CostChargeRequest, CostLedger, ReservationRecord, TaskType,
        };
        let reservation = |id: &str, task_id: &str| ReservationRecord {
            reservation_id: id.to_owned(),
            task_id: task_id.to_owned(),
            month: "2026-07".to_owned(),
            scope_id: "scope".to_owned(),
            adapter_kind: "embedding".to_owned(),
            usd: 0.6,
        };
        use std::collections::BTreeMap;

        let tmp = tempfile::tempdir().unwrap();
        let ledger = CostLedger::new(tmp.path().join("kcs/cost-ledger.jsonl"));
        let lock_path = tmp.path().join("kcs/cost-ledger.lock");
        let caps = BudgetCaps {
            device_monthly_usd_cap: 1.0,
            folder_monthly_usd_cap: None,
            device_per_adapter: BTreeMap::new(),
            folder_per_adapter: BTreeMap::new(),
            hard_stop: true,
            warn_at_percent: 80,
        };
        let estimate = BudgetEstimate {
            scope_id: "scope".to_owned(),
            task_type: TaskType::Embedding,
            estimated_usd: 0.6,
            adapter_id: Some("gemini".to_owned()),
        };

        // First charge: 0.6 <= 1.0 remaining → Charged and appended.
        let first = charge_cost_ledger_under_lock(
            &ledger,
            lock_path.clone(),
            &caps,
            CostChargeRequest {
                month: "2026-07",
                adapter_kind: "embedding",
                estimate: &estimate,
                override_budget: false,
                reservations: &[reservation("res_first", "task_first")],
            },
        )
        .unwrap();
        assert!(matches!(first, ChargeOutcome::Charged));

        // Second charge re-reads under the lock: spent=0.6, remaining=0.4 < 0.6 →
        // BudgetExceeded, nothing appended (serial charges cannot exceed the cap).
        let second = charge_cost_ledger_under_lock(
            &ledger,
            lock_path.clone(),
            &caps,
            CostChargeRequest {
                month: "2026-07",
                adapter_kind: "embedding",
                estimate: &estimate,
                override_budget: false,
                reservations: &[reservation("res_second", "task_second")],
            },
        )
        .unwrap();
        assert!(matches!(second, ChargeOutcome::BudgetExceeded));
        assert_eq!(ledger.monthly_total("2026-07", None).unwrap(), 0.6);
    }

    #[test]
    fn reservation_ledger_lock_preserves_retryable_cli_error_contract() {
        use super::{pipeline_to_kcs, ExitCode};

        let err = pipeline_to_kcs(kcs_pipeline::PipelineError::locked(
            "/tmp/cost-ledger-reservations.jsonl.lock",
        ));
        assert_eq!(err.error_code(), "KCS-E-STORE-LOCKED-001");
        assert_eq!(err.exit_code(), ExitCode::PartialFailure);
    }

    // F8: the charge path is gated by the device-global ledger lock. A held lock
    // (here an existing lock file) makes the charge fail-closed (STORE-LOCKED)
    // rather than appending while another charger holds the ledger.
    #[test]
    fn f8_charge_is_gated_by_the_device_global_lock() {
        use super::{
            charge_cost_ledger_under_lock, BudgetCaps, BudgetEstimate, CostChargeRequest,
            CostLedger, ReservationRecord, TaskType,
        };
        use std::collections::BTreeMap;

        let tmp = tempfile::tempdir().unwrap();
        let ledger = CostLedger::new(tmp.path().join("kcs/cost-ledger.jsonl"));
        let lock_path = tmp.path().join("kcs/cost-ledger.lock");
        std::fs::create_dir_all(lock_path.parent().unwrap()).unwrap();
        std::fs::write(&lock_path, b"held by a concurrent charge").unwrap();
        let caps = BudgetCaps {
            device_monthly_usd_cap: 50.0,
            folder_monthly_usd_cap: None,
            device_per_adapter: BTreeMap::new(),
            folder_per_adapter: BTreeMap::new(),
            hard_stop: true,
            warn_at_percent: 80,
        };
        let estimate = BudgetEstimate {
            scope_id: "scope".to_owned(),
            task_type: TaskType::Embedding,
            estimated_usd: 0.01,
            adapter_id: Some("gemini".to_owned()),
        };
        let reservation = ReservationRecord {
            reservation_id: "res_locked".to_owned(),
            task_id: "task_locked".to_owned(),
            month: "2026-07".to_owned(),
            scope_id: "scope".to_owned(),
            adapter_kind: "embedding".to_owned(),
            usd: 0.01,
        };
        let err = charge_cost_ledger_under_lock(
            &ledger,
            lock_path.clone(),
            &caps,
            CostChargeRequest {
                month: "2026-07",
                adapter_kind: "embedding",
                estimate: &estimate,
                override_budget: false,
                reservations: &[reservation],
            },
        )
        .unwrap_err();
        assert_eq!(err.error_code(), "KCS-E-STORE-LOCKED-001");
        // Nothing was charged while the lock was held.
        assert_eq!(ledger.monthly_total("2026-07", None).unwrap(), 0.0);
    }

    #[test]
    fn r23_cand_048_forged_task_stamp_cannot_create_reclaim_credit() {
        use super::{settle_task_reservation, CostLedger, TaskDescriptor, TaskStatus, TaskType};

        let tmp = tempfile::tempdir().unwrap();
        let ledger = CostLedger::new(tmp.path().join("cost-ledger.jsonl"));
        let task = TaskDescriptor {
            task_id: "task_forged".to_owned(),
            task_type: TaskType::Markdownize,
            mode: None,
            input_path: "doc.pdf".to_owned(),
            input_hash: format!("sha256:{}", "a".repeat(64)),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: Vec::new(),
            output_ref: "online:mistral_ocr_markdownize".to_owned(),
            unit_keys: None,
            status: TaskStatus::Failed,
            attempts: 1,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: Some("rate_limit".to_owned()),
            created_at: "2026-07-01T00:00:00Z".to_owned(),
            bbox_annotation_enabled: None,
            reserved_usd: Some(49.0),
            reserved_month: Some("2026-07".to_owned()),
            reservation_id: Some("res_forged".to_owned()),
        };

        assert!(settle_task_reservation(&ledger, &task, "scope", "markdown")
            .unwrap()
            .is_none());
        assert_eq!(
            ledger
                .reclaim_ledger()
                .monthly_total("2026-07", None)
                .unwrap(),
            0.0
        );
    }

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

    fn stored_chunk_line(rowid: u64, id: &str) -> String {
        serde_json::json!({
            "rowid": rowid,
            "chunk_id": id,
            "raw_hash": format!("sha256:{}", "a".repeat(64)),
            "tool_profile_hash": format!("sha256:{}", "b".repeat(64)),
            "gen": 0,
            "unit_key": "doc:1",
            "chunking_config_hash": format!("sha256:{}", "c".repeat(64)),
            "raw_path": "a.md",
            "heading_path": ["H"],
            "section_id": "h",
            "char_start": 0,
            "char_end": 4,
            "text_hash": format!("sha256:{}", "d".repeat(64)),
            "text": "body",
            "first_seen_commit": null,
            "created_at": "2026-07-04T00:00:00Z"
        })
        .to_string()
    }

    #[test]
    fn q1_read_stored_chunks_tolerates_torn_tail() {
        use super::{chunks_jsonl_path, read_stored_chunks};
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        let path = chunks_jsonl_path(&kcs_dir);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        // Two intact rows, then a torn final line (crash / ENOSPC mid-write_all,
        // no trailing newline).
        let mut contents = format!(
            "{}\n{}\n",
            stored_chunk_line(1, "c1"),
            stored_chunk_line(2, "c2")
        );
        contents.push_str(r#"{"rowid":3,"chunk_id":"c3","raw_hash":"sha256:"#);
        std::fs::write(&path, contents).unwrap();
        let chunks = read_stored_chunks(&kcs_dir).unwrap();
        assert_eq!(
            chunks.len(),
            2,
            "torn tail must be dropped so index/repair self-heal"
        );
    }

    #[test]
    fn q1_read_stored_chunks_flags_mid_file_corruption() {
        use super::{chunks_jsonl_path, read_stored_chunks};
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        let path = chunks_jsonl_path(&kcs_dir);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        // A broken NON-final line cannot be a torn tail -> STORE-CORRUPT (exit 4),
        // not the old CONFIG-SCHEMA (exit 2) misclassification.
        let contents = format!(
            "{}\n{}\n{}\n",
            stored_chunk_line(1, "c1"),
            r#"{"rowid":2,"chunk_id":BROKEN"#,
            stored_chunk_line(3, "c3")
        );
        std::fs::write(&path, contents).unwrap();
        let err = read_stored_chunks(&kcs_dir).unwrap_err();
        assert_eq!(err.error_code(), "KCS-E-STORE-CORRUPT-001");
    }

    #[test]
    fn ct4_legacy_chunk_ledger_assigns_stable_association_rowids() {
        use super::{chunks_jsonl_path, read_stored_chunks};
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        let path = chunks_jsonl_path(&kcs_dir);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(
            &path,
            format!(
                "{}\n{}\n",
                stored_chunk_line(42, "c42"),
                stored_chunk_line(7, "c7")
            ),
        )
        .unwrap();

        let chunks = read_stored_chunks(&kcs_dir).unwrap();
        assert_eq!(chunks[0].association_rowid, Some(2));
        assert_eq!(chunks[1].association_rowid, Some(1));
        assert_eq!(chunks[0].rowid, 42);
        assert_eq!(chunks[1].rowid, 7);
    }

    #[test]
    fn ct4_chunk_ledger_retains_two_configs_for_one_chunk() {
        use super::{chunks_jsonl_path, read_stored_chunks};
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        let path = chunks_jsonl_path(&kcs_dir);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        let mut first: serde_json::Value =
            serde_json::from_str(&stored_chunk_line(7, "shared")).unwrap();
        first["association_rowid"] = serde_json::json!(11);
        let mut second = first.clone();
        second["association_rowid"] = serde_json::json!(29);
        second["chunking_config_hash"] = serde_json::json!(format!("sha256:{}", "e".repeat(64)));
        std::fs::write(&path, format!("{first}\n{second}\n")).unwrap();

        let chunks = read_stored_chunks(&kcs_dir).unwrap();
        assert_eq!(chunks.len(), 2);
        assert_eq!(chunks[0].rowid, 7);
        assert_eq!(chunks[1].rowid, 7);
        assert_eq!(chunks[0].association_rowid, Some(11));
        assert_eq!(chunks[1].association_rowid, Some(29));
        assert_ne!(
            chunks[0].row.chunking_config_hash,
            chunks[1].row.chunking_config_hash
        );
    }

    #[test]
    fn q2_open_cas_byte_object_rejects_corrupt_object() {
        use super::{cas_object_path, hash_bytes, open_cas_byte_object, ScopeTarget};
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        // The correct `sha256:` filename for the AUTHENTIC bytes...
        let hash = hash_bytes(b"authentic prepared object");
        let object_path = cas_object_path(&kcs_dir, "prepared", &hash).unwrap();
        std::fs::create_dir_all(object_path.parent().unwrap()).unwrap();
        // ...but the file under it holds corrupt/torn bytes (non-atomic write).
        std::fs::write(&object_path, b"corrupt partial bytes").unwrap();
        let target = ScopeTarget {
            repo_root: dir.path().to_path_buf(),
            kcs_dir,
            scope_id: "01H00000000000000000000000".to_owned(),
        };
        let err = open_cas_byte_object(&target, "prepared", false, &hash, None).unwrap_err();
        assert_eq!(
            err.error_code(),
            "KCS-E-STORE-CORRUPT-001",
            "a corrupt CAS object must not be served as authentic evidence"
        );
    }

    #[test]
    fn portable_cas_leaf_uses_digest_and_presence_rejects_nonregular_slot() {
        use super::{cas_object_path, cas_object_present, hash_bytes, MAX_RAW_OBJECT_BYTES};

        let dir = tempfile::tempdir().unwrap();
        let hash = hash_bytes(b"portable object");
        let path = cas_object_path(dir.path(), "raw", &hash).unwrap();
        assert_eq!(
            path.file_name().and_then(|name| name.to_str()),
            hash.strip_prefix("sha256:")
        );
        assert!(!path.to_string_lossy().contains("sha256:"));

        std::fs::create_dir_all(&path).unwrap();
        let error = cas_object_present(dir.path(), "raw", &hash, MAX_RAW_OBJECT_BYTES).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
    }

    #[cfg(not(windows))]
    #[test]
    fn legacy_cas_leaf_is_verified_and_dual_conflict_fails_closed() {
        use super::{
            cas_object_path, hash_bytes, legacy_cas_object_path, read_cas_byte_object,
            MAX_RAW_OBJECT_BYTES,
        };

        let dir = tempfile::tempdir().unwrap();
        let bytes = b"legacy object";
        let hash = hash_bytes(bytes);
        let legacy = legacy_cas_object_path(dir.path(), "prepared", &hash).unwrap();
        std::fs::create_dir_all(legacy.parent().unwrap()).unwrap();
        std::fs::write(&legacy, bytes).unwrap();
        let (resolved, loaded) =
            read_cas_byte_object(dir.path(), "prepared", &hash, MAX_RAW_OBJECT_BYTES)
                .unwrap()
                .unwrap();
        assert_eq!(resolved, legacy);
        assert_eq!(loaded, bytes);

        let canonical = cas_object_path(dir.path(), "prepared", &hash).unwrap();
        std::fs::write(&canonical, bytes).unwrap();
        std::fs::write(&legacy, b"conflicting bytes").unwrap();
        let error =
            read_cas_byte_object(dir.path(), "prepared", &hash, MAX_RAW_OBJECT_BYTES).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
    }

    #[cfg(not(windows))]
    #[test]
    fn prepared_writer_reuses_verified_legacy_and_validates_both_slots() {
        use super::{
            cas_object_path, hash_bytes, legacy_cas_object_path, write_cas_object_or_reuse_legacy,
        };

        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        std::fs::create_dir(&kcs_dir).unwrap();
        let bytes = b"prepared bytes";
        let hash = hash_bytes(bytes);
        let canonical = cas_object_path(&kcs_dir, "prepared", &hash).unwrap();
        let legacy = legacy_cas_object_path(&kcs_dir, "prepared", &hash).unwrap();
        std::fs::create_dir_all(legacy.parent().unwrap()).unwrap();
        std::fs::write(&legacy, bytes).unwrap();

        write_cas_object_or_reuse_legacy(&kcs_dir, "prepared", &hash, bytes).unwrap();
        assert!(!canonical.exists(), "legacy reuse must not eagerly migrate");
        assert_eq!(std::fs::read(&legacy).unwrap(), bytes);

        std::fs::write(&canonical, bytes).unwrap();
        write_cas_object_or_reuse_legacy(&kcs_dir, "prepared", &hash, bytes).unwrap();
        std::fs::write(&legacy, b"conflict").unwrap();
        let error =
            write_cas_object_or_reuse_legacy(&kcs_dir, "prepared", &hash, bytes).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
    }

    #[test]
    fn prepared_writer_publishes_new_objects_to_portable_leaf() {
        use super::{cas_object_path, hash_bytes, write_cas_object_or_reuse_legacy};

        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        std::fs::create_dir(&kcs_dir).unwrap();
        let bytes = b"new prepared bytes";
        let hash = hash_bytes(bytes);
        write_cas_object_or_reuse_legacy(&kcs_dir, "prepared", &hash, bytes).unwrap();
        let canonical = cas_object_path(&kcs_dir, "prepared", &hash).unwrap();
        assert_eq!(std::fs::read(canonical).unwrap(), bytes);
    }

    #[test]
    fn latest_normalize_ref_parses_portable_digest_basename() {
        use super::{hash_bytes, latest_normalize_ref};

        let dir = tempfile::tempdir().unwrap();
        let raw_hash = hash_bytes(b"raw");
        let tool_hash = hash_bytes(b"tool");
        let raw_digest = raw_hash.strip_prefix("sha256:").unwrap();
        let tool_digest = tool_hash.strip_prefix("sha256:").unwrap();
        let instance = dir
            .path()
            .join("objects/normalized_units")
            .join(&raw_digest[0..2])
            .join(&raw_digest[2..4])
            .join(format!("{raw_digest}.{tool_digest}.g2"));
        std::fs::create_dir_all(instance).unwrap();

        let reference = latest_normalize_ref(dir.path(), &raw_hash)
            .unwrap()
            .unwrap();
        assert_eq!(reference.tool_profile_hash, tool_hash);
        assert_eq!(reference.gen, 2);
    }

    #[cfg(not(windows))]
    #[test]
    fn latest_normalize_ref_also_parses_legacy_prefixed_basename() {
        use super::{hash_bytes, latest_normalize_ref};

        let dir = tempfile::tempdir().unwrap();
        let raw_hash = hash_bytes(b"raw");
        let tool_hash = hash_bytes(b"tool");
        let raw_digest = raw_hash.strip_prefix("sha256:").unwrap();
        let instance = dir
            .path()
            .join("objects/normalized_units")
            .join(&raw_digest[0..2])
            .join(&raw_digest[2..4])
            .join(format!("{raw_hash}.{tool_hash}.g3"));
        std::fs::create_dir_all(instance).unwrap();

        let reference = latest_normalize_ref(dir.path(), &raw_hash)
            .unwrap()
            .unwrap();
        assert_eq!(reference.tool_profile_hash, tool_hash);
        assert_eq!(reference.gen, 3);
    }

    #[cfg(not(windows))]
    #[test]
    fn tombstone_reader_reuses_verified_legacy_and_rejects_conflict() {
        use super::{
            hash_bytes, legacy_tombstone_path, read_tombstone, tombstone_path, ScopeTarget,
        };

        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        std::fs::create_dir(&kcs_dir).unwrap();
        let raw_hash = hash_bytes(b"purged raw");
        let legacy = legacy_tombstone_path(&kcs_dir, &raw_hash).unwrap();
        std::fs::create_dir_all(legacy.parent().unwrap()).unwrap();
        let record = serde_json::json!({"raw_hash": raw_hash, "reason": "privacy"});
        std::fs::write(&legacy, serde_json::to_vec(&record).unwrap()).unwrap();
        let target = ScopeTarget {
            repo_root: dir.path().to_path_buf(),
            kcs_dir: kcs_dir.clone(),
            scope_id: "scope_test".to_owned(),
        };
        let loaded = read_tombstone(&target, &raw_hash).unwrap().unwrap();
        assert_eq!(loaded["raw_hash"], raw_hash);
        assert_eq!(loaded["reason"], "privacy");

        let canonical = tombstone_path(&kcs_dir, &raw_hash).unwrap();
        std::fs::write(
            canonical,
            serde_json::to_vec(&serde_json::json!({
                "raw_hash": raw_hash,
                "reason": "legal"
            }))
            .unwrap(),
        )
        .unwrap();
        let error = read_tombstone(&target, &raw_hash).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
    }

    #[test]
    fn q3_reclaims_orphaned_running_task_to_pending() {
        use super::reclaim_orphaned_running_tasks;
        use kcs_pipeline::markdownize::MarkdownizeMode;
        use kcs_pipeline::task::{TaskDescriptor, TaskStatus, TaskStore, TaskType};
        let dir = tempfile::tempdir().unwrap();
        let store = TaskStore::new(dir.path());
        let task = TaskDescriptor {
            task_id: "t1".to_owned(),
            task_type: TaskType::Markdownize,
            mode: Some(MarkdownizeMode::Full),
            input_path: "notes.txt".to_owned(),
            input_hash: format!("sha256:{}", "a".repeat(64)),
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: Vec::new(),
            output_ref: super::online_output_ref("test_markdownize_adapter"),
            unit_keys: None,
            // A task stuck Running is bit-identical to a crash between the
            // Running-persist and the Done-persist.
            status: TaskStatus::Running,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: Some("2020-01-01T00:00:00Z".to_owned()),
            fallback_reason: Some("ready_for_online_adapter".to_owned()),
            created_at: "2026-07-04T00:00:00Z".to_owned(),
            bbox_annotation_enabled: None,
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        };
        store.append(&task).unwrap();
        let reclaimed = reclaim_orphaned_running_tasks(&store).unwrap();
        assert_eq!(reclaimed, 1, "the orphaned Running task must be reclaimed");
        let tasks = store.all().unwrap();
        assert_eq!(tasks[0].status, TaskStatus::Pending);
        assert!(
            tasks[0].heartbeat_at.is_none(),
            "stale heartbeat must be cleared on reclaim"
        );
    }
}
