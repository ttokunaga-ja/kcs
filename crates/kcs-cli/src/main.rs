use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{IsTerminal, Write};
use std::path::{Path, PathBuf};
use std::process;
use std::time::Instant;

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
use kcs_core::cas::is_hash;
use kcs_core::dag::NormalizeRef;
use kcs_core::scope::{
    append_error_log, append_event_log, new_ulid, now_utc_seconds, InspectedObject, Repository,
};
use kcs_core::{ExitCode, KcsError, Result};
use kcs_index::chunking::{
    chunk_normalized_instance, ChunkingConfig, ChunkingInput, NormalizedUnitInput,
};
use kcs_index::fts::{FtsIndex, FtsSchemaConfig, FtsTokenizer, SqliteFtsIndex};
use kcs_index::registry::{RegistryDb, RegistryEntry};
use kcs_index::{ChunkRow, TreeEntryRow};
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
use kcs_search::cursor::{
    decode_cursor_token, encode_cursor_token, CursorToken, ScopeCursor, ScopeMode,
};
use kcs_search::evidence::{
    evidence_pointer_to_uri, issue_evidence_pointer, parse_evidence_pointer_uri, EvidencePointer,
    EvidencePointerIssueRequest,
};
use kcs_search::mmr::{diversify_candidates, MmrCandidate, MmrConfig};
use kcs_search::query::{
    query_hash, DiversifyRequest, DiversifyStrategy, QueryHashInput, ScopeSelectionMode, SearchMode,
};
use kcs_search::rrf::{fuse_rrf, BackendRank, RrfConfig};
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
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
    /// Rebuild local acceleration tables.
    Repair(UnsupportedArgs),
    /// Search indexed chunks.
    Search(UnsupportedArgs),
    /// Open an Evidence Pointer target.
    Open(UnsupportedArgs),
    /// View an Evidence Pointer target.
    View(UnsupportedArgs),
    /// Step 4 command placeholder.
    Restore(UnsupportedArgs),
    /// Phase 4+ command placeholder.
    Gc(UnsupportedArgs),
    /// Step 4 command placeholder.
    Purge(UnsupportedArgs),
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
        Ok(mut output) => {
            // A command may request a non-zero success exit code (e.g. multi-scope
            // search partial failure returns its result JSON on stdout with exit 3,
            // 05 §1.8). The private `__exit_code` marker is stripped before printing.
            let code = take_exit_override(&mut output).unwrap_or(ExitCode::Success);
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

/// Remove and interpret the private `__exit_code` marker a command may embed in
/// its success output to request a non-zero process exit while still printing the
/// payload to stdout (multi-scope search partial failure, 05 §1.8).
fn take_exit_override(output: &mut Value) -> Option<ExitCode> {
    let code = output.as_object_mut()?.remove("__exit_code")?.as_u64()?;
    match code {
        3 => Some(ExitCode::PartialFailure),
        4 => Some(ExitCode::PermanentFailure),
        _ => None,
    }
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
            // Register the scope in the device-local registry so multi-scope search
            // can enumerate it (05 §1.8). `indexed=false` until `kcs index` runs.
            // The registry is a cache, never truth (03 §4): a write failure is a
            // warning, never a hard error.
            register_scope(&repo, false);
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
        Command::Repair(args) => run_repair(args),
        Command::Search(args) => run_search(args),
        Command::Open(args) => run_open(args),
        Command::View(args) => run_view(args),
        Command::Reindex(args) => run_reindex(args),
        Command::Restore(_)
        | Command::Gc(_)
        | Command::Purge(_)
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
    rebuild_step3_index(&repo)?;
    // The scope now has a search index; register it as indexed so it participates
    // in default multi-scope search (05 §1.8, K3). Cache write, never fatal.
    register_scope(&repo, true);
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

#[derive(Debug, Clone, Serialize, Deserialize)]
struct StoredChunk {
    rowid: u64,
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
    scope: Option<PathBuf>,
    descendants: bool,
    all_scopes: bool,
    limit: u64,
    offset: Option<u64>,
    cursor: Option<String>,
}

fn run_repair(args: UnsupportedArgs) -> Result<Value> {
    let args = without_json(args.args);
    if !args.iter().any(|arg| arg == "--rebuild-db") {
        return Err(KcsError::invalid_usage(
            "repair currently supports --rebuild-db",
        ));
    }
    let repo = Repository::open_current()?;
    validate_repo_tool_lock(&repo)?;
    let db = repo.kcs_dir().join("index/sqlite.db");
    if db.exists() {
        fs::remove_file(&db)
            .map_err(|err| KcsError::io(err.to_string(), db.display().to_string()))?;
    }
    let report = rebuild_step3_index(&repo)?;
    Ok(json!({
        "status": "rebuilt",
        "rebuilt_chunks": report.rebuilt_chunks,
        "rebuilt_tree_entries": report.rebuilt_tree_entries,
        "sqlite_db": db,
    }))
}

/// Resolved search mode plus the honest fallback reporting fields (05 §1.1/§1.7).
struct ResolvedMode {
    requested: SearchMode,
    resolved: SearchMode,
    fallback: bool,
    fallback_reason: Option<String>,
    error_code: Option<String>,
}

/// Vector backend availability (the K4 embedding seam). Until embeddings are
/// wired, this is always `Unavailable` — but the mode-resolution and RRF plumbing
/// treats it uniformly so K4 only has to change this one function.
#[allow(dead_code)]
enum VectorAvailability {
    /// Every searched scope has a compatible embedding index (K4).
    Available,
    /// No embedding index present.
    Unavailable,
    /// Embedding present but the profile is incompatible (03 §7).
    Incompatible,
}

/// K4 seam: aggregate embedding availability across the searched scopes. Vector
/// search is only offered when every scope has a compatible embedding index
/// (03 §7). Always `Unavailable` in Step3c.
fn resolve_vector_availability() -> VectorAvailability {
    VectorAvailability::Unavailable
}

/// K4 seam: per-scope vector ranks from the chunk_vec KNN backend. Always `None`
/// (text-only) until embeddings land.
fn vector_ranks_for_scope() -> Result<Option<Vec<BackendRank>>> {
    Ok(None)
}

fn resolve_search_mode(requested: SearchMode, vector: &VectorAvailability) -> Result<ResolvedMode> {
    let vector_ok = matches!(vector, VectorAvailability::Available);
    let (reason, error_code) = match vector {
        VectorAvailability::Available => (None, None),
        VectorAvailability::Unavailable => (
            Some("embedding_endpoint_not_configured".to_owned()),
            Some("KCS-E-SEARCH-VEC-UNAVAIL-001".to_owned()),
        ),
        VectorAvailability::Incompatible => (
            Some("embedding_profile_incompatible".to_owned()),
            Some("KCS-E-SEARCH-VEC-INCOMPAT-001".to_owned()),
        ),
    };
    match requested {
        SearchMode::Text => Ok(ResolvedMode {
            requested,
            resolved: SearchMode::Text,
            fallback: false,
            fallback_reason: None,
            error_code: None,
        }),
        SearchMode::Vector => {
            if vector_ok {
                Ok(ResolvedMode {
                    requested,
                    resolved: SearchMode::Vector,
                    fallback: false,
                    fallback_reason: None,
                    error_code: None,
                })
            } else {
                // --vector with no vector backend is a hard error (05 §1.2).
                Err(KcsError::new(
                    "KCS-E-SEARCH-VEC-UNAVAIL-001",
                    "vector search requested but no compatible embedding index is available",
                    json!({}),
                    ExitCode::Failure,
                ))
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
                })
            } else {
                // auto / --hybrid fall back to text (fail_behavior default = fallback).
                Ok(ResolvedMode {
                    requested,
                    resolved: SearchMode::Text,
                    fallback: true,
                    fallback_reason: reason,
                    error_code,
                })
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
    from_cursor: bool,
}

/// A candidate that survived per-scope RRF, carried into the cross-scope merge.
struct ScoredCandidate {
    scope_index: usize,
    scope_id: String,
    scope_path: PathBuf,
    snapshot_commit: String,
    chunk_hash: String,
    rrf_score: f64,
    meta: ChunkMeta,
}

#[derive(Clone)]
struct ChunkMeta {
    raw_hash: String,
    tool_profile_hash: String,
    heading_path: Option<Vec<String>>,
    section_id: Option<String>,
    char_start: Option<u64>,
    char_end: Option<u64>,
    text: String,
    path_at_commit: String,
}

struct SearchedScopeInfo {
    scope_id: String,
    scope_path: PathBuf,
    snapshot_at: String,
    max_rowid: u64,
}

fn run_search(args: UnsupportedArgs) -> Result<Value> {
    let started = Instant::now();
    let parsed = parse_search_args(without_json(args.args))?;
    let repo = Repository::open_current()?;
    validate_repo_tool_lock(&repo)?;

    // Mode resolution up front (05 §1.1). Vector availability does not depend on
    // the scope set today (always Unavailable), so this errors early for --vector.
    let vector = resolve_vector_availability();
    let mode = resolve_search_mode(parsed.requested_mode, &vector)?;

    if parsed.query.chars().count() < 2 {
        return empty_search_response(&parsed, &repo, started, &mode, &[], &[]);
    }

    // Page 1 enumerates scopes (registry-based, K3); later pages replay the frozen
    // scope set stored in the cursor (05 §1.8 — the cursor scope set is truth).
    let decoded_cursor = match &parsed.cursor {
        Some(token) => Some(decode_cursor_token(token).map_err(search_to_kcs)?),
        None => None,
    };
    let (scope_mode, exec_scopes) = match &decoded_cursor {
        Some(cursor) => (
            scope_selection_from_cursor(cursor.scope_mode),
            resolve_cursor_exec_scopes(cursor),
        ),
        None => {
            let (scope_mode, targets) = enumerate_scope_targets(&repo, &parsed)?;
            let exec = targets
                .into_iter()
                .map(|target| ExecScope {
                    target,
                    snapshot_commit: None,
                    max_rowid: None,
                    from_cursor: false,
                })
                .collect::<Vec<_>>();
            (scope_mode, exec)
        }
    };

    if exec_scopes.is_empty() {
        return Err(scope_all_failed_error(
            "no indexed scopes are registered for search; run `kcs index` in a scope first",
            Vec::new(),
        ));
    }

    let mut scope_ids = exec_scopes
        .iter()
        .map(|exec| exec.target.scope_id.clone())
        .collect::<Vec<_>>();
    scope_ids.sort();
    let qhash = query_hash(&QueryHashInput {
        query: parsed.query.clone(),
        mode: mode.resolved,
        scope_mode,
        scopes: scope_ids,
        diversify: default_diversify_request(),
        rrf_k: 60,
        rrf_candidate_depth: 200,
        rrf_w_text: 1.0,
        rrf_w_vector: 1.0,
        at: None,
        all_history: false,
        include_deleted: false,
        since: None,
    })
    .map_err(search_to_kcs)?;

    if let Some(cursor) = &decoded_cursor {
        if cursor.query_hash != qhash {
            return Err(KcsError::new(
                "KCS-E-SEARCH-CURSOR-001",
                "search cursor query_hash mismatch",
                json!({ "expected": qhash, "actual": cursor.query_hash }),
                ExitCode::InvalidUsage,
            ));
        }
    }

    // Per-scope: FTS5 text ranks -> RRF (text-only until K4) -> candidate pool.
    let tiers = build_fts_tiers(&parsed.query);
    let mut searched = Vec::<SearchedScopeInfo>::new();
    let mut excluded = Vec::<Value>::new();
    let mut candidates = Vec::<ScoredCandidate>::new();

    for (idx, exec) in exec_scopes.iter().enumerate() {
        match search_one_scope(exec, idx, &tiers) {
            Ok(outcome) => {
                searched.push(SearchedScopeInfo {
                    scope_id: exec.target.scope_id.clone(),
                    scope_path: exec.target.repo_root.clone(),
                    snapshot_at: outcome.snapshot_commit.clone(),
                    max_rowid: outcome.max_rowid,
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
            Err(ScopeSearchError::Excluded(reason)) => excluded.push(json!({
                "scope_id": exec.target.scope_id,
                "scope_path": exec.target.repo_root,
                "reason": reason,
            })),
            Err(ScopeSearchError::Fatal(error)) => return Err(error),
        }
    }

    if searched.is_empty() {
        // Every scope failed: permanent all-scope failure (05 §1.8, exit 4).
        return Err(scope_all_failed_error(
            "all searched scopes failed",
            excluded,
        ));
    }

    // Cross-scope merge is rank-based: RRF score desc, tie-break (scope_path,
    // chunk_hash) — never compare raw BM25 across corpora (05 §1.8 / CT3-MULTI-002).
    candidates.sort_by(|a, b| {
        b.rrf_score
            .total_cmp(&a.rrf_score)
            .then_with(|| a.scope_path.cmp(&b.scope_path))
            .then_with(|| a.chunk_hash.cmp(&b.chunk_hash))
    });

    // Diversify the merged pool once (05 §1.8 step 4). Text-only -> MMR is skipped;
    // only the raw_hash dedup runs (spanning scopes and pages, CT3-MULTI-003).
    let (ordered, diversify_summary) = diversify_merged(&candidates, mode.resolved)?;

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
    let slice_start = total_skip.min(ordered.len());
    let slice_end = slice_start.saturating_add(limit).min(ordered.len());
    let page = &ordered[slice_start..slice_end];

    // Per-scope consumed = candidates from that scope within the first `slice_end`
    // positions of the deterministic stream (uniform for cursor and --offset,
    // CT3-CURSOR-006). Preserves the frozen scope set even at 0 consumed.
    let next_cursor = if slice_end < ordered.len() {
        let mut consumed = vec![0u64; exec_scopes.len()];
        for candidate in &ordered[..slice_end] {
            consumed[candidate.scope_index] += 1;
        }
        let sub_cursors = exec_scopes
            .iter()
            .enumerate()
            .map(|(idx, exec)| {
                let searched_scope = searched
                    .iter()
                    .find(|scope| scope.scope_id == exec.target.scope_id);
                ScopeCursor {
                    scope_id: exec.target.scope_id.clone(),
                    snapshot_commit: searched_scope
                        .map(|scope| scope.snapshot_at.clone())
                        .or_else(|| exec.snapshot_commit.clone())
                        .unwrap_or_default(),
                    max_rowid: searched_scope
                        .map(|scope| scope.max_rowid)
                        .or(exec.max_rowid)
                        .unwrap_or_default(),
                    consumed: consumed[idx],
                }
            })
            .collect::<Vec<_>>();
        Some(
            encode_cursor_token(&CursorToken {
                version: 1,
                scope_mode: cursor_mode_from_selection(scope_mode),
                query_hash: qhash,
                scopes: sub_cursors,
            })
            .map_err(search_to_kcs)?,
        )
    } else {
        None
    };

    let mut results = Vec::new();
    for candidate in page {
        let pointer = issue_evidence_pointer(EvidencePointerIssueRequest {
            scope_id: candidate.scope_id.clone(),
            scope_path: Some(candidate.scope_path.display().to_string()),
            commit: candidate.snapshot_commit.clone(),
            tree: None,
            raw_hash: candidate.meta.raw_hash.clone(),
            tool_profile_hash: candidate.meta.tool_profile_hash.clone(),
            chunk_hash: candidate.chunk_hash.clone(),
            path_at_commit: Some(candidate.meta.path_at_commit.clone()),
            heading_path: candidate.meta.heading_path.clone(),
            section_id: candidate.meta.section_id.clone(),
            char_start: candidate.meta.char_start,
            char_end: candidate.meta.char_end,
        })
        .map_err(search_to_kcs)?;
        let uri = evidence_pointer_to_uri(&pointer).map_err(search_to_kcs)?;
        results.push(json!({
            "chunk_hash": candidate.chunk_hash,
            "evidence_pointer": pointer,
            "evidence_uri": uri,
            "score": candidate.rrf_score,
            "scope_path": candidate.scope_path,
            "title": candidate.meta.path_at_commit,
            "snippet": candidate.meta.text.chars().take(200).collect::<String>(),
        }));
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
        "diversify": diversify_summary,
        "paging": { "limit": parsed.limit, "next_cursor": next_cursor },
        "searched_scopes": searched_scopes,
        "excluded_scopes": excluded,
        "index_status": index_status,
        "results": results,
    });
    append_search_logs(&repo, &response, started)?;
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

struct ScopeOutcome {
    snapshot_commit: String,
    max_rowid: u64,
    candidates: Vec<ScoredCandidate>,
}

fn search_one_scope(
    exec: &ExecScope,
    scope_index: usize,
    tiers: &[String],
) -> std::result::Result<ScopeOutcome, ScopeSearchError> {
    let repo = Repository::open(&exec.target.repo_root)
        .map_err(|_| ScopeSearchError::Excluded("unreachable".to_owned()))?;

    // Resolve the search snapshot: frozen commit on a cursor replay, else HEAD.
    let snapshot_commit = match &exec.snapshot_commit {
        Some(commit) => commit.clone(),
        None => repo
            .head_commit_hash()
            .map_err(|_| ScopeSearchError::Excluded("unreachable".to_owned()))?
            .ok_or_else(|| ScopeSearchError::Excluded("not_indexed".to_owned()))?,
    };

    let db_path = sqlite_path(&exec.target.kcs_dir);
    if !db_path.exists() {
        return Err(ScopeSearchError::Excluded("index_missing".to_owned()));
    }
    let conn = Connection::open(&db_path)
        .map_err(|_| ScopeSearchError::Excluded("index_corrupt".to_owned()))?;

    // On a cursor replay, the snapshot's tree must still exist to reproduce the
    // page. A shallow (tree-discarded) snapshot fails hard (05 §2.2).
    if exec.from_cursor {
        match ensure_snapshot_tree_entries(&repo, &conn, &snapshot_commit) {
            Ok(true) => {}
            Ok(false) => return Err(ScopeSearchError::Shallow),
            Err(error) => return Err(ScopeSearchError::Fatal(error)),
        }
    } else {
        // HEAD tree_entries are written by `kcs index`; project defensively in
        // case the caller points at a non-HEAD snapshot in future.
        if let Err(error) = ensure_snapshot_tree_entries(&repo, &conn, &snapshot_commit) {
            return Err(ScopeSearchError::Fatal(error));
        }
    }

    let max_rowid = match exec.max_rowid {
        Some(value) => value,
        None => current_max_rowid(&conn).map_err(ScopeSearchError::Fatal)?,
    };

    let chunking_config_hash = read_chunking_config(&repo)
        .map(|config| config.chunking_config_hash)
        .map_err(ScopeSearchError::Fatal)?;

    // FTS5 text ranks (empty when the query has no indexable token).
    let (text_ranks, meta) = fts_scope_search(
        &conn,
        &snapshot_commit,
        tiers,
        &chunking_config_hash,
        max_rowid,
    )
    .map_err(ScopeSearchError::Fatal)?;

    let vector_ranks = vector_ranks_for_scope()
        .map_err(ScopeSearchError::Fatal)?
        .unwrap_or_default();

    let fused = fuse_rrf(
        &text_ranks,
        &vector_ranks,
        RrfConfig {
            k: 60,
            w_text: 1.0,
            w_vector: 1.0,
            candidate_depth: 200,
        },
    )
    .map_err(search_to_kcs)
    .map_err(ScopeSearchError::Fatal)?;

    let mut candidates = Vec::new();
    for candidate in fused {
        let Some(chunk_meta) = meta.get(&candidate.chunk_hash) else {
            continue;
        };
        candidates.push(ScoredCandidate {
            scope_index,
            scope_id: exec.target.scope_id.clone(),
            scope_path: exec.target.repo_root.clone(),
            snapshot_commit: snapshot_commit.clone(),
            chunk_hash: candidate.chunk_hash,
            rrf_score: candidate.rrf_score,
            meta: chunk_meta.clone(),
        });
    }

    Ok(ScopeOutcome {
        snapshot_commit,
        max_rowid,
        candidates,
    })
}

/// Per-scope text backend: execute the tiered MATCH queries (see
/// [`build_fts_tiers`]) in order; the first tier returning any candidate is the
/// scope's text backend. The candidate list handed to RRF comes from exactly one
/// executed query, ranked purely by that query's BM25 (05 §1.3 / K2 ruling — no
/// post-hoc re-ordering by hand-computed features).
fn fts_scope_search(
    conn: &Connection,
    snapshot_commit: &str,
    tiers: &[String],
    chunking_config_hash: &str,
    max_rowid: u64,
) -> Result<(Vec<BackendRank>, BTreeMap<String, ChunkMeta>)> {
    for match_expr in tiers {
        let (ranks, meta) = execute_fts_tier(
            conn,
            snapshot_commit,
            match_expr,
            chunking_config_hash,
            max_rowid,
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
    snapshot_commit: &str,
    match_expr: &str,
    chunking_config_hash: &str,
    max_rowid: u64,
) -> Result<(Vec<BackendRank>, BTreeMap<String, ChunkMeta>)> {
    let sql = "SELECT c.chunk_id, c.raw_hash, c.tool_profile_hash, c.heading_path,
                      c.section_id, c.char_start, c.char_end, c.text, te.path,
                      bm25(chunk_fts, 1.0, 0.3) AS score
               FROM chunk_fts f
               JOIN chunks c ON c.rowid = f.rowid
               JOIN tree_entries te ON te.commit_hash = ?1
                   AND te.raw_hash = c.raw_hash
                   AND te.tool_profile_hash = c.tool_profile_hash
                   AND te.gen = c.gen
               WHERE chunk_fts MATCH ?2
                   AND c.chunking_config_hash = ?3
                   AND c.rowid <= ?4
               ORDER BY score, c.chunk_id
               LIMIT 200";
    let mut stmt = conn
        .prepare(sql)
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let rows = stmt
        .query_map(
            rusqlite::params![
                snapshot_commit,
                match_expr,
                chunking_config_hash,
                max_rowid as i64
            ],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, Option<String>>(3)?,
                    row.get::<_, Option<String>>(4)?,
                    row.get::<_, Option<i64>>(5)?,
                    row.get::<_, Option<i64>>(6)?,
                    row.get::<_, String>(7)?,
                    row.get::<_, String>(8)?,
                ))
            },
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;

    let mut ranks = Vec::new();
    let mut meta = BTreeMap::new();
    for (index, row) in rows.enumerate() {
        let (
            chunk_id,
            raw_hash,
            tool_profile_hash,
            heading_path_raw,
            section_id,
            char_start,
            char_end,
            text,
            path,
        ) = row.map_err(|err| KcsError::schema(err.to_string()))?;
        ranks.push(BackendRank {
            chunk_hash: chunk_id.clone(),
            rank: index as u64 + 1,
        });
        meta.insert(
            chunk_id,
            ChunkMeta {
                raw_hash,
                tool_profile_hash,
                heading_path: heading_path_raw
                    .and_then(|value| serde_json::from_str::<Vec<String>>(&value).ok()),
                section_id: section_id.filter(|value| !value.is_empty()),
                char_start: char_start.map(|value| value as u64),
                char_end: char_end.map(|value| value as u64),
                text,
                path_at_commit: path,
            },
        );
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

/// Ensure `tree_entries` rows for `commit_hash` exist in `conn`, projecting them
/// from the commit's tree object when absent (04 §4.5). Returns `Ok(false)` when
/// the commit is shallow (its tree object is gone).
fn ensure_snapshot_tree_entries(
    repo: &Repository,
    conn: &Connection,
    commit_hash: &str,
) -> Result<bool> {
    let existing: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM tree_entries WHERE commit_hash = ?1",
            rusqlite::params![commit_hash],
            |row| row.get(0),
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
    if existing > 0 {
        // Cached — but a cursor replay still needs the tree object to prove the
        // snapshot is not shallow, so verify object presence regardless.
        let commit = repo.read_commit(commit_hash)?;
        return tree_object_present(repo, &commit.tree);
    }
    let commit = repo.read_commit(commit_hash)?;
    let tree = match repo.read_tree(&commit.tree) {
        Ok(tree) => tree,
        Err(error) if error.error_code() == "KCS-E-STORE-NOT-FOUND-001" => return Ok(false),
        Err(error) => return Err(error),
    };
    for entry in &tree.entries {
        let normalize = match &entry.normalize {
            Some(normalize) => normalize.clone(),
            None => match latest_normalize_ref(repo.kcs_dir(), &entry.raw_hash)? {
                Some(normalize) => normalize,
                None => continue,
            },
        };
        conn.execute(
            "INSERT OR REPLACE INTO tree_entries(commit_hash, path, raw_hash, tool_profile_hash, gen)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            rusqlite::params![
                commit_hash,
                entry.path,
                entry.raw_hash,
                Some(normalize.tool_profile_hash.clone()),
                normalize.gen
            ],
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
    }
    Ok(true)
}

fn tree_object_present(repo: &Repository, tree_hash: &str) -> Result<bool> {
    match repo.read_tree(tree_hash) {
        Ok(_) => Ok(true),
        Err(error) if error.error_code() == "KCS-E-STORE-NOT-FOUND-001" => Ok(false),
        Err(error) => Err(error),
    }
}

/// Apply diversify (05 §1.4/§1.8) to the merged candidate pool and report the
/// strategy actually applied. Text-only (no embeddings) means MMR is skipped and
/// only the `max_per_raw_hash` dedup runs — reported honestly as
/// `group_by_raw_hash`, never a phantom "mmr" (K2 fix for the false report).
fn diversify_merged(
    candidates: &[ScoredCandidate],
    resolved_mode: SearchMode,
) -> Result<(Vec<&ScoredCandidate>, Value)> {
    let request = default_diversify_request();
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
            embedding: None,
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

    // Report the strategy actually applied (05 §1.7). MMR needs embeddings; with
    // none present only the raw_hash dedup ran.
    let mmr_ran = matches!(resolved_mode, SearchMode::Hybrid | SearchMode::Vector)
        && request.strategy == DiversifyStrategy::Mmr;
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
/// Embedding; "done" is `Done`/`Partial`. `budget_paused` is any paused task or
/// an exhausted monthly budget.
fn compute_index_status(searched: &[SearchedScopeInfo]) -> Value {
    let mut total = 0u64;
    let mut done = 0u64;
    let mut pending = 0u64;
    let mut budget_paused = false;

    for scope in searched {
        let kcs_dir = scope.scope_path.join(".kcs");
        let store = TaskStore::new(&kcs_dir);
        let Ok(tasks) = store.all() else {
            continue;
        };
        for task in tasks {
            if !matches!(task.task_type, TaskType::Markdownize | TaskType::Embedding) {
                continue;
            }
            total += 1;
            match task.status {
                TaskStatus::Done | TaskStatus::Partial => done += 1,
                TaskStatus::Pending | TaskStatus::Running => pending += 1,
                TaskStatus::Paused => {
                    pending += 1;
                    budget_paused = true;
                }
                TaskStatus::Failed => {}
            }
        }
        if let Ok(repo) = Repository::open(&scope.scope_path) {
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
    }

    let enriched_ratio = if total == 0 {
        1.0
    } else {
        done as f64 / total as f64
    };
    json!({
        "enriched_ratio": enriched_ratio,
        "pending_enrichment_tasks": pending,
        "budget_paused": budget_paused,
    })
}

fn scope_all_failed_error(message: &str, excluded: Vec<Value>) -> KcsError {
    KcsError::new(
        "KCS-E-SEARCH-SCOPE-ALL-FAILED-001",
        message,
        json!({ "excluded_scopes": excluded }),
        ExitCode::PermanentFailure,
    )
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
    let keyword_groups = keywords
        .iter()
        .map(|keyword| fts_keyword_group(keyword))
        .collect::<Vec<_>>();

    let strict = if keyword_groups.len() >= 2 {
        Some(keyword_groups.join(" OR "))
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

fn cursor_mode_from_selection(mode: ScopeSelectionMode) -> ScopeMode {
    match mode {
        ScopeSelectionMode::All => ScopeMode::All,
        ScopeSelectionMode::Scope => ScopeMode::Scope,
        ScopeSelectionMode::Descendants => ScopeMode::Descendants,
    }
}

/// Resolve a cursor's frozen per-scope sub-cursors into execution scopes. The
/// cursor scope set is authoritative (05 §1.8): scope_id -> path is resolved via
/// the registry; unresolvable scopes are dropped (recorded as excluded later).
fn resolve_cursor_exec_scopes(cursor: &CursorToken) -> Vec<ExecScope> {
    let registry = RegistryDb::open_default().ok();
    cursor
        .scopes
        .iter()
        .filter_map(|sub| {
            let target = registry.as_ref().and_then(|db| {
                db.lookup_scope_id(&sub.scope_id)
                    .ok()
                    .and_then(|entries| entries.into_iter().next())
                    .map(|entry| ScopeTarget {
                        repo_root: PathBuf::from(&entry.root_path),
                        kcs_dir: PathBuf::from(&entry.kcs_path),
                        scope_id: entry.scope_id,
                    })
            })?;
            Some(ExecScope {
                target,
                snapshot_commit: Some(sub.snapshot_commit.clone()),
                max_rowid: Some(sub.max_rowid),
                from_cursor: true,
            })
        })
        .collect()
}

fn run_open(args: UnsupportedArgs) -> Result<Value> {
    let raw = read_pointer_input(without_json(args.args))?;
    if let Some(object) = parse_object_uri(&raw)? {
        return resolve_object_uri(&object, false);
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
    let pointer = parse_pointer_text(&raw)?;
    let resolved = resolve_pointer_for_cli(&pointer)?;
    Ok(json!({
        "status": "viewed",
        "raw_hash": pointer.raw_hash,
        "chunk_hash": pointer.chunk_hash,
        "text": resolved.text.unwrap_or_default(),
        "path": resolved.path,
        "commit_shallow": resolved.commit_shallow,
    }))
}

fn run_reindex(args: UnsupportedArgs) -> Result<Value> {
    let args = without_json(args.args);
    if !args.iter().any(|arg| arg == "--force") {
        return Err(KcsError::invalid_usage(
            "reindex requires --force in Step 3",
        ));
    }
    if !args.iter().any(|arg| arg == "--yes") {
        return Err(KcsError::new(
            "KCS-E-CONFIRM-REJECTED-001",
            "reindex --force requires confirmation; pass --yes in non-interactive mode",
            json!({}),
            ExitCode::ConfirmationRejected,
        ));
    }
    let repo = Repository::open_current()?;
    validate_repo_tool_lock(&repo)?;
    let head = repo
        .head_commit_hash()?
        .ok_or_else(|| KcsError::not_found("HEAD"))?;
    let tree = repo.read_tree(&repo.read_commit(&head)?.tree)?;
    let mut normalize_by_path = BTreeMap::new();
    let mut reindexed = 0u64;
    for entry in &tree.entries {
        let Some(normalize) = &entry.normalize else {
            continue;
        };
        let new_gen = normalize.gen + 1;
        copy_normalized_instance_gen(
            repo.kcs_dir(),
            &entry.raw_hash,
            &normalize.tool_profile_hash,
            normalize.gen,
            new_gen,
        )?;
        normalize_by_path.insert(
            entry.path.clone(),
            NormalizeRef {
                tool_profile_hash: normalize.tool_profile_hash.clone(),
                gen: new_gen,
            },
        );
        reindexed += 1;
    }
    let excluded = BTreeSet::new();
    let outcome = repo.auto_snapshot_with_normalize(
        Some("kcs reindex --force"),
        None,
        &excluded,
        &normalize_by_path,
    )?;
    let report = rebuild_step3_index(&repo)?;
    Ok(json!({
        "status": "reindexed",
        "reindexed_files": reindexed,
        "commit_hash": outcome.commit_hash,
        "rebuilt_chunks": report.rebuilt_chunks,
    }))
}

fn rebuild_step3_index(repo: &Repository) -> Result<Step3RebuildReport> {
    let Some(head) = repo.head_commit_hash()? else {
        return Ok(Step3RebuildReport::default());
    };
    let commit = repo.read_commit(&head)?;
    let tree = repo.read_tree(&commit.tree)?;
    let config = read_chunking_config(repo)?;
    let existing = read_stored_chunks(repo.kcs_dir())?;
    let mut known = existing
        .iter()
        .map(|chunk| chunk.row.chunk_id.clone())
        .collect::<BTreeSet<_>>();
    let mut next_rowid = existing.iter().map(|chunk| chunk.rowid).max().unwrap_or(0) + 1;
    let mut appended = Vec::<StoredChunk>::new();
    let mut tree_entries = Vec::<TreeEntryRow>::new();

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
        let units = load_normalized_units(
            repo.kcs_dir(),
            &entry.raw_hash,
            &normalize.tool_profile_hash,
            normalize.gen,
        )?;
        let input = ChunkingInput {
            raw_path: entry.path.clone(),
            units,
            config: config.clone(),
            created_at: now_utc_seconds(),
        };
        for mut row in chunk_normalized_instance(input).map_err(index_to_kcs)? {
            row.first_seen_commit = Some(head.clone());
            if known.insert(row.chunk_id.clone()) {
                appended.push(StoredChunk {
                    rowid: next_rowid,
                    row,
                });
                next_rowid += 1;
            }
        }
    }

    append_stored_chunks(repo.kcs_dir(), &appended)?;
    write_tree_entries(repo.kcs_dir(), &tree_entries)?;
    rebuild_sqlite_index(repo.kcs_dir(), &tree_entries)?;
    Ok(Step3RebuildReport {
        rebuilt_chunks: appended.len() as u64,
        rebuilt_tree_entries: tree_entries.len() as u64,
    })
}

fn latest_normalize_ref(kcs_dir: &Path, raw_hash: &str) -> Result<Option<NormalizeRef>> {
    let digest = raw_hash.trim_start_matches("sha256:");
    if digest.len() < 4 {
        return Ok(None);
    }
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
        let Some(rest) = name
            .strip_prefix(raw_hash)
            .and_then(|value| value.strip_prefix('.'))
        else {
            continue;
        };
        let Some((tool_profile_hash, gen_part)) = rest.rsplit_once(".g") else {
            continue;
        };
        let Ok(gen) = gen_part.parse::<u64>() else {
            continue;
        };
        if best
            .as_ref()
            .map(|current| gen > current.gen)
            .unwrap_or(true)
        {
            best = Some(NormalizeRef {
                tool_profile_hash: tool_profile_hash.to_owned(),
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
    let dir = kcs_pipeline::markdownize::normalized_instance_dir(
        kcs_dir,
        raw_hash,
        tool_profile_hash,
        gen,
    );
    let manifest_path = dir.join("manifest.json");
    let manifest: NormalizedInstanceManifest = serde_json::from_slice(
        &fs::read(&manifest_path)
            .map_err(|err| KcsError::io(err.to_string(), manifest_path.display().to_string()))?,
    )
    .map_err(|err| KcsError::schema(err.to_string()))?;
    let mut units = Vec::new();
    for entry in &manifest.units {
        if entry.status != UnitStatus::Done {
            continue;
        }
        let unit_path = dir.join(format!("{}.json", entry.unit_ref));
        let unit: NormalizedUnitObject = serde_json::from_slice(
            &fs::read(&unit_path)
                .map_err(|err| KcsError::io(err.to_string(), unit_path.display().to_string()))?,
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
        units.push(NormalizedUnitInput {
            raw_hash: unit.raw_hash,
            tool_profile_hash: unit.tool_profile_hash,
            gen: unit.gen,
            unit_key: unit.unit_key,
            markdown: unit.markdown,
        });
    }
    Ok(units)
}

fn index_dir(kcs_dir: &Path) -> PathBuf {
    kcs_dir.join("index")
}

fn chunks_jsonl_path(kcs_dir: &Path) -> PathBuf {
    index_dir(kcs_dir).join("chunks.jsonl")
}

fn tree_entries_path(kcs_dir: &Path) -> PathBuf {
    index_dir(kcs_dir).join("tree_entries.json")
}

fn sqlite_path(kcs_dir: &Path) -> PathBuf {
    index_dir(kcs_dir).join("sqlite.db")
}

fn read_stored_chunks(kcs_dir: &Path) -> Result<Vec<StoredChunk>> {
    let path = chunks_jsonl_path(kcs_dir);
    let Ok(text) = fs::read_to_string(&path) else {
        return Ok(Vec::new());
    };
    text.lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str(line).map_err(|err| KcsError::schema(err.to_string())))
        .collect()
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
        serde_json::to_writer(&mut file, chunk)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        file.write_all(b"\n")
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    }
    Ok(())
}

fn write_tree_entries(kcs_dir: &Path, entries: &[TreeEntryRow]) -> Result<()> {
    let path = tree_entries_path(kcs_dir);
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent)
        .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    let bytes =
        serde_json::to_vec_pretty(entries).map_err(|err| KcsError::schema(err.to_string()))?;
    fs::write(&path, bytes).map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
}

fn read_tree_entries(kcs_dir: &Path) -> Result<Vec<TreeEntryRow>> {
    let path = tree_entries_path(kcs_dir);
    let Ok(bytes) = fs::read(&path) else {
        return Ok(Vec::new());
    };
    serde_json::from_slice(&bytes).map_err(|err| KcsError::schema(err.to_string()))
}

fn rebuild_sqlite_index(kcs_dir: &Path, tree_entries: &[TreeEntryRow]) -> Result<()> {
    let path = sqlite_path(kcs_dir);
    if path.exists() {
        fs::remove_file(&path)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    }
    let mut fts = SqliteFtsIndex::open(
        &path,
        FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        },
    )
    .map_err(index_to_kcs)?;
    for chunk in read_stored_chunks(kcs_dir)? {
        fts.index_chunk(&chunk.row).map_err(index_to_kcs)?;
    }
    for entry in tree_entries {
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
    Ok(())
}

fn parse_search_args(args: Vec<String>) -> Result<ParsedSearch> {
    let mut query = None;
    let mut requested_mode = SearchMode::Auto;
    let mut scope = None;
    let mut descendants = false;
    let mut all_scopes = false;
    let mut limit = 20u64;
    let mut offset = None;
    let mut cursor = None;
    let mut i = 0usize;
    while i < args.len() {
        match args[i].as_str() {
            "--at" | "--all-history" | "--include-deleted" | "--since" => {
                return Err(KcsError::new(
                    "KCS-E-CONFIG-NOT-IMPLEMENTED-001",
                    "time-travel search flags are Step 4",
                    json!({ "flag": args[i] }),
                    ExitCode::InvalidUsage,
                ));
            }
            "--text" | "--no-vector" => requested_mode = SearchMode::Text,
            "--vector" => requested_mode = SearchMode::Vector,
            "--hybrid" => requested_mode = SearchMode::Hybrid,
            "--all-scopes" => all_scopes = true,
            "--descendants" => descendants = true,
            "--scope" => {
                i += 1;
                let Some(value) = args.get(i) else {
                    return Err(KcsError::invalid_usage("--scope requires a value"));
                };
                scope = Some(PathBuf::from(value));
            }
            "--limit" => {
                i += 1;
                let Some(value) = args.get(i) else {
                    return Err(KcsError::invalid_usage("--limit requires a value"));
                };
                limit = value
                    .parse::<u64>()
                    .map_err(|_| KcsError::invalid_usage("--limit must be an integer"))?
                    .clamp(1, 100);
            }
            "--offset" => {
                i += 1;
                let Some(value) = args.get(i) else {
                    return Err(KcsError::invalid_usage("--offset requires a value"));
                };
                offset = Some(
                    value
                        .parse::<u64>()
                        .map_err(|_| KcsError::invalid_usage("--offset must be an integer"))?,
                );
            }
            "--cursor" => {
                i += 1;
                let Some(value) = args.get(i) else {
                    return Err(KcsError::invalid_usage("--cursor requires a value"));
                };
                cursor = Some(value.clone());
            }
            value if value.starts_with('-') => {
                return Err(KcsError::invalid_usage(format!(
                    "unknown search flag: {value}"
                )));
            }
            value => {
                if query.is_some() {
                    return Err(KcsError::invalid_usage("search accepts one query string"));
                }
                query = Some(value.to_owned());
            }
        }
        i += 1;
    }
    Ok(ParsedSearch {
        query: query.ok_or_else(|| KcsError::invalid_usage("search query is required"))?,
        requested_mode,
        scope,
        descendants,
        all_scopes,
        limit,
        offset,
        cursor,
    })
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
            return Ok((
                ScopeSelectionMode::Descendants,
                registry_targets_under(&root)?,
            ));
        }
        return Ok((ScopeSelectionMode::Scope, vec![scope_target(&root)?]));
    }
    if parsed.descendants {
        return Ok((
            ScopeSelectionMode::Descendants,
            registry_targets_under(repo.root())?,
        ));
    }
    // Default and `--all-scopes` share the same enumeration: every indexed,
    // participating scope in the registry (05 §1.8 / 06 §3, CT3-MULTI-008). The
    // difference between the two is spec-undefined (§C-8) and intentionally none.
    let _all_scopes = parsed.all_scopes;
    Ok((ScopeSelectionMode::All, registry_all_targets()?))
}

/// All indexed, participating scopes from the registry (deterministic order).
fn registry_all_targets() -> Result<Vec<ScopeTarget>> {
    let Ok(db) = RegistryDb::open_default() else {
        return Ok(Vec::new());
    };
    let entries = db.search_targets().map_err(index_to_kcs)?;
    Ok(entries.into_iter().map(registry_entry_target).collect())
}

/// Registered scopes whose root path is at or below `root` (05 §1.8 prefix filter).
fn registry_targets_under(root: &Path) -> Result<Vec<ScopeTarget>> {
    Ok(registry_all_targets()?
        .into_iter()
        .filter(|target| target.repo_root.starts_with(root))
        .collect())
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
        if let Err(error) = db.upsert(&entry) {
            eprintln!(
                "warning: scope registry write failed (search cache; recover with `kcs index`): {}",
                error
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
    let repo = Repository::open(root)?;
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
    let tree_entries = read_tree_entries(&target.kcs_dir)?;
    let live = tree_entries
        .iter()
        .filter(|entry| entry.commit_hash == head)
        .filter_map(|entry| {
            entry.tool_profile_hash.as_ref().map(|tool| {
                (
                    (entry.raw_hash.clone(), tool.clone(), entry.gen),
                    entry.path.clone(),
                )
            })
        })
        .collect::<BTreeMap<_, _>>();
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

fn default_diversify_request() -> DiversifyRequest {
    DiversifyRequest {
        strategy: DiversifyStrategy::Mmr,
        mmr_lambda: Some(0.7),
        max_per_raw_hash: Some(3),
        mmr_depth: Some(100),
    }
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
    searched_scopes: &[Value],
    excluded_scopes: &[Value],
) -> Result<Value> {
    // Short queries still report the resolved mode honestly (auto -> text with the
    // vector-unavailable fallback) plus index_status (K7).
    let response = json!({
        "query": parsed.query,
        "requested_mode": search_mode_json(mode.requested),
        "resolved_mode": search_mode_json(mode.resolved),
        "fallback": mode.fallback,
        "fallback_reason": mode.fallback_reason.clone().map(Value::from).unwrap_or(Value::Null),
        "error_code": mode.error_code.clone().map(Value::from).unwrap_or(Value::Null),
        "diversify": { "strategy": "group_by_raw_hash" },
        "paging": { "limit": parsed.limit, "next_cursor": Value::Null },
        "searched_scopes": searched_scopes,
        "excluded_scopes": excluded_scopes,
        "index_status": json!({
            "enriched_ratio": 1.0,
            "pending_enrichment_tasks": 0,
            "budget_paused": false,
        }),
        "results": [],
    });
    append_search_logs(repo, &response, started)?;
    Ok(response)
}

fn append_search_logs(repo: &Repository, response: &Value, started: Instant) -> Result<()> {
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
    append_jsonl_cli(
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
    )?;
    append_jsonl_cli(
        &repo.kcs_dir().join("logs/access.jsonl"),
        &json!({
            "ts": now_utc_seconds(),
            "level": "info",
            "code": "KCS-I-SEARCH-ACCESS-001",
            "component": "kcs-cli",
            "message": "search access",
            "context": {
                "query": "[redacted]",
                "mode": response.get("resolved_mode").and_then(Value::as_str).unwrap_or("text"),
                "result_count": result_count,
            },
        }),
    )
}

fn append_jsonl_cli(path: &Path, value: &Value) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent)
        .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    serde_json::to_writer(&mut file, value)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    file.write_all(b"\n")
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
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
    let Some(pointer) = args.into_iter().next() else {
        return Err(KcsError::invalid_usage("pointer argument is required"));
    };
    if pointer == "-" {
        let mut input = String::new();
        std::io::Read::read_to_string(&mut std::io::stdin(), &mut input)
            .map_err(|err| KcsError::io(err.to_string(), "stdin"))?;
        return Ok(input.trim().to_owned());
    }
    Ok(pointer)
}

fn parse_pointer_text(pointer: &str) -> Result<EvidencePointer> {
    if pointer.starts_with("kcs://") {
        return parse_evidence_pointer_uri(pointer).map_err(search_to_kcs);
    }
    if pointer.trim_start().starts_with('{') {
        return serde_json::from_str(pointer).map_err(|err| KcsError::schema(err.to_string()));
    }
    if pointer.starts_with("sha256:") {
        return resolve_short_hash(pointer);
    }
    Err(KcsError::invalid_usage("invalid pointer argument"))
}

fn resolve_short_hash(hash: &str) -> Result<EvidencePointer> {
    let repo = Repository::open_current()?;
    let target = scope_target(repo.root())?;
    let chunks = load_searchable_chunks(&target)?;
    let matches = chunks
        .into_iter()
        .filter(|chunk| chunk.row.chunk_id == hash || chunk.row.raw_hash == hash)
        .collect::<Vec<_>>();
    if matches.len() != 1 {
        return Err(KcsError::invalid_usage(
            "short hash is ambiguous or not found",
        ));
    }
    let chunk = &matches[0];
    issue_evidence_pointer(EvidencePointerIssueRequest {
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
    .map_err(search_to_kcs)
}

fn resolve_pointer_for_cli(pointer: &EvidencePointer) -> Result<PointerResolution> {
    // 08 §3.1 step 1: two-stage scope resolution (scope_path hint -> registry).
    let target = resolve_scope_target(&pointer.scope_id, pointer.scope_path.as_deref())?;
    let repo = Repository::open(&target.repo_root)?;

    // 08 §3.1 step 2: fetch the commit object (append-only; never GC'd).
    let commit = repo.read_commit(&pointer.commit)?;

    // 08 §3.1 step 2a/3-4: a shallow commit (tree object discarded) skips the
    // tree walk; otherwise the raw_hash must appear in commit.tree for the
    // pointer to resolve against *this* commit's snapshot (not the working tree
    // of some later commit).
    let commit_shallow = match repo.read_tree(&commit.tree) {
        Ok(tree) => {
            let in_tree = tree
                .entries
                .iter()
                .any(|entry| entry.raw_hash == pointer.raw_hash);
            if !in_tree {
                // step 5 (tombstone) is checked before declaring not_found.
                if let Some(tombstone) = read_tombstone(&target, &pointer.raw_hash)? {
                    return Err(tombstone_error(tombstone));
                }
                return Err(purge_not_found_error(&target, &pointer.raw_hash));
            }
            false
        }
        Err(error) if is_store_not_found(&error) => true,
        Err(error) => return Err(error),
    };

    // 08 §3.1 step 5: purged raw_hash carrying a tombstone -> tombstone response.
    if let Some(tombstone) = read_tombstone(&target, &pointer.raw_hash)? {
        return Err(tombstone_error(tombstone));
    }

    // 08 §3.1 step 6-7: chunk_hash -> chunk text (the normalized instance is
    // keyed by (raw_hash, tool_profile_hash, gen); chunk rows carry the span).
    let text = read_stored_chunks(&target.kcs_dir)?
        .into_iter()
        .find(|chunk| chunk.row.chunk_id == pointer.chunk_hash)
        .map(|chunk| chunk.row.text);

    // Raw object resolution: working tree first (rename-tolerant), else CAS
    // read-only expansion. Absent from both with no tombstone -> not_found.
    match open_raw_object(
        &target,
        &pointer.raw_hash,
        pointer.path_at_commit.as_deref(),
    )? {
        Some((path, temporary)) => Ok(PointerResolution {
            path: Some(path),
            text,
            temporary,
            commit_shallow,
        }),
        None => Err(purge_not_found_error(&target, &pointer.raw_hash)),
    }
}

/// Two-stage scope resolution (08 §3.1 step 1). Root trust is `scope_id`; the
/// `scope_path` hint and the scope-registry are both non-authoritative caches
/// (05 §1.7 truth vs cache).
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
    if let Ok(registry) = RegistryDb::open_default() {
        if let Ok(entries) = registry.lookup_scope_id(scope_id) {
            let mut resolved: Vec<(String, ScopeTarget)> = Vec::new();
            for entry in &entries {
                if let Some(target) = open_scope_from_hint(&entry.root_path) {
                    if target.scope_id == scope_id {
                        resolved.push((entry.last_seen_at.clone(), target));
                    }
                }
            }
            if !resolved.is_empty() {
                // Newest last_seen_at wins; a tie across distinct .kcs is ambiguous.
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
                return Ok(resolved.remove(0).1);
            }
        }
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
/// raw object under `$XDG_DATA_HOME/kcs/open` (05 §4.2 / 06 §1.1). Returns
/// `Ok(None)` when the raw object is absent from both.
fn open_raw_object(
    target: &ScopeTarget,
    raw_hash: &str,
    path_hint: Option<&str>,
) -> Result<Option<(PathBuf, bool)>> {
    if let Some(path) = find_working_tree_raw(&target.repo_root, raw_hash)? {
        return Ok(Some((path, false)));
    }
    let raw_path = raw_object_path(&target.kcs_dir, raw_hash);
    if !raw_path.is_file() {
        return Ok(None);
    }
    let basename = path_hint
        .and_then(|path| Path::new(path).file_name())
        .and_then(|name| name.to_str())
        .unwrap_or("object");
    let cache = data_home()
        .join("kcs/open")
        .join(
            raw_hash
                .trim_start_matches("sha256:")
                .chars()
                .take(12)
                .collect::<String>(),
        )
        .join(basename);
    if let Some(parent) = cache.parent() {
        fs::create_dir_all(parent)
            .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    }
    fs::copy(&raw_path, &cache)
        .map_err(|err| KcsError::io(err.to_string(), cache.display().to_string()))?;
    let mut permissions = fs::metadata(&cache)
        .map_err(|err| KcsError::io(err.to_string(), cache.display().to_string()))?
        .permissions();
    permissions.set_readonly(true);
    fs::set_permissions(&cache, permissions)
        .map_err(|err| KcsError::io(err.to_string(), cache.display().to_string()))?;
    Ok(Some((cache, true)))
}

fn find_working_tree_raw(root: &Path, raw_hash: &str) -> Result<Option<PathBuf>> {
    for entry in fs::read_dir(root)
        .map_err(|err| KcsError::io(err.to_string(), root.display().to_string()))?
    {
        let entry =
            entry.map_err(|err| KcsError::io(err.to_string(), root.display().to_string()))?;
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
        let path = entry.path();
        let bytes = fs::read(&path)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        if hash_bytes(&bytes) == raw_hash {
            return Ok(Some(path));
        }
    }
    Ok(None)
}

fn raw_object_path(kcs_dir: &Path, raw_hash: &str) -> PathBuf {
    let digest = raw_hash.trim_start_matches("sha256:");
    kcs_dir
        .join("objects/raw")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(raw_hash)
}

/// `.kcs/tombstones/ab/cd/<raw_hash>` (05 §3.5). `Ok(None)` when no tombstone
/// exists. The returned value is the on-disk tombstone JSON augmented with the
/// resolved `scope_path` (08 §4.1 response shape).
fn read_tombstone(target: &ScopeTarget, raw_hash: &str) -> Result<Option<Value>> {
    let digest = raw_hash.trim_start_matches("sha256:");
    if digest.len() < 4 {
        return Ok(None);
    }
    let path = target
        .kcs_dir
        .join("tombstones")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(raw_hash);
    let bytes = match fs::read(&path) {
        Ok(bytes) => bytes,
        // Only a missing tombstone file means "no tombstone"; an unreadable
        // tombstones dir must not be misclassified as not_found (08 §3.2).
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(err) => return Err(KcsError::io(err.to_string(), path.display().to_string())),
    };
    let mut value: Value =
        serde_json::from_slice(&bytes).map_err(|err| KcsError::schema(err.to_string()))?;
    if let Some(object) = value.as_object_mut() {
        object
            .entry("raw_hash".to_owned())
            .or_insert_with(|| json!(raw_hash));
        object.insert(
            "scope_path".to_owned(),
            json!(target.kcs_dir.display().to_string()),
        );
    }
    Ok(Some(value))
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
        let text = read_stored_chunks(&target.kcs_dir)?
            .into_iter()
            .find(|chunk| chunk.row.chunk_id == object.hash)
            .map(|chunk| chunk.row.text)
            .ok_or_else(|| KcsError::not_found(object.hash.clone()))?;
        return Ok(json!({
            "status": status,
            "object_type": "chunk",
            "hash": object.hash,
            "text": text,
        }));
    }
    // raw / image / normalized / prepared resolve as byte objects in the CAS raw
    // store (07 §5.2). Only `raw` is materialised as a top-level object in Step 3.
    match open_raw_object(&target, &object.hash, None)? {
        Some((path, temporary)) => Ok(json!({
            "status": status,
            "object_type": object.object_type,
            "hash": object.hash,
            "path": path,
            "temporary": temporary,
        })),
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
    let new_dir = kcs_pipeline::markdownize::normalized_instance_dir(
        kcs_dir,
        raw_hash,
        tool_profile_hash,
        new_gen,
    );
    fs::create_dir_all(&new_dir)
        .map_err(|err| KcsError::io(err.to_string(), new_dir.display().to_string()))?;
    let manifest_path = old_dir.join("manifest.json");
    let mut manifest: Value = serde_json::from_slice(
        &fs::read(&manifest_path)
            .map_err(|err| KcsError::io(err.to_string(), manifest_path.display().to_string()))?,
    )
    .map_err(|err| KcsError::schema(err.to_string()))?;
    manifest["parent_gen"] = json!(old_gen);
    manifest["gen"] = json!(new_gen);
    manifest["run_id"] = json!(format!("run_{}", new_ulid(kcs_dir)));
    manifest["generated_at"] = json!(now_utc_seconds());
    fs::write(
        new_dir.join("manifest.json"),
        serde_json::to_vec_pretty(&manifest).map_err(|err| KcsError::schema(err.to_string()))?,
    )
    .map_err(|err| KcsError::io(err.to_string(), new_dir.display().to_string()))?;
    for entry in fs::read_dir(&old_dir)
        .map_err(|err| KcsError::io(err.to_string(), old_dir.display().to_string()))?
    {
        let entry =
            entry.map_err(|err| KcsError::io(err.to_string(), old_dir.display().to_string()))?;
        if entry.file_name() == "manifest.json" {
            continue;
        }
        let mut unit: Value =
            serde_json::from_slice(&fs::read(entry.path()).map_err(|err| {
                KcsError::io(err.to_string(), entry.path().display().to_string())
            })?)
            .map_err(|err| KcsError::schema(err.to_string()))?;
        unit["gen"] = json!(new_gen);
        unit["generated_at"] = json!(now_utc_seconds());
        fs::write(
            new_dir.join(entry.file_name()),
            serde_json::to_vec_pretty(&unit).map_err(|err| KcsError::schema(err.to_string()))?,
        )
        .map_err(|err| KcsError::io(err.to_string(), new_dir.display().to_string()))?;
    }
    Ok(())
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
