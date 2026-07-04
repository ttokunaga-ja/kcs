use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{IsTerminal, Write};
use std::path::{Path, PathBuf};
use std::process;
use std::time::Instant;

use clap::{Args, Parser, Subcommand};
use kcs_adapter::catalog::{
    active_adopted_embedding_execution, adopted_embedding_profile,
    builtin_offline_markdownize_adapter, builtin_prepare_profile,
    declared_adopted_embedding_profile, run_adopted_embedding, run_standard_online_markdownize,
    standard_online_markdownize_profile, AdoptedEmbeddingExecution, DeclaredEmbeddingProfile,
    StandardOnlineMarkdownizeRequest,
};
use kcs_adapter::identity::tool_profile_hash;
use kcs_adapter::tool_lock::{load_tool_lock, validate_tools_toml};
use kcs_adapter::traits::MarkdownizeAdapter;
use kcs_adapter::types::{
    AdapterKind, AdapterProfile, EmbeddingInputType, EmbeddingItem, ExecutionMode, MarkdownUnit,
    MarkdownizeMode as AdapterMarkdownizeMode, MarkdownizeRequest, PreparedUnitHint,
    PreviousMarkdownizeContext, RawInput, UnitKind,
};
use kcs_core::cas::is_hash;
use kcs_core::dag::NormalizeRef;
use kcs_core::schema::{validate_json_schema, SchemaKind};
use kcs_core::scope::{
    append_error_log, append_event_log, append_warn_log, new_ulid, now_utc_seconds,
    InspectedObject, Repository,
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
use kcs_pipeline::scan::{
    build_scan_preview, classify_secret, ScanCandidate, ScanPreview, ScanPreviewRequest, SecretTier,
};
use kcs_pipeline::task::{retry_policy, task_status_from_unit_counts, RetryErrorKind};
use kcs_pipeline::task::{TaskDescriptor, TaskStatus, TaskStore, TaskType};
use kcs_search::cursor::{
    decode_cursor_token, encode_cursor_token, CursorToken, ScopeCursor, ScopeMode,
};
use kcs_search::evidence::{
    evidence_pointer_to_uri, issue_evidence_pointer, parse_evidence_pointer_uri, EvidencePointer,
    EvidencePointerIssueRequest, EVIDENCE_POINTER_SCHEMA_VERSION,
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
    validate_user_config()?;
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
            let outcome = repo.snapshot_filtered(args.message.as_deref(), None, &excluded)?;
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
    // Generate chunk embeddings behind the online opt-in / budget / cost-ledger
    // guardrails (K4). No-op unless an embedding adapter is configured.
    generate_scope_embeddings(&repo, &args)?;
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
    parse_repair_args(args)?;
    let repo = Repository::open_current()?;
    // M1(a): serialize the DB rebuild against concurrent index/repair/reindex.
    let _lock = repo.lock_store()?;
    validate_repo_tool_lock(&repo)?;
    let db = repo.kcs_dir().join("index/sqlite.db");
    // `rebuild_sqlite_index` drops and rebuilds chunks/FTS/tree_entries in place
    // while preserving the `embeddings` rows and re-deriving `chunk_vec` from them
    // (04 §4.3). It is not pre-deleted here so vector search survives the rebuild.
    let report = rebuild_step3_index(&repo)?;
    // L1: after a DB rebuild, re-drive enrichment so any chunk lacking an
    // embedding (e.g. a rebuild that produced new chunk rows, or a scope whose
    // enrichment never ran) is enqueued/embedded rather than silently reported as
    // fully enriched. `rebuild_sqlite_index` already preserved existing
    // embeddings, so reuse keeps this near-free; offline it only enqueues.
    let embedding_online = embedding_online_allowed(&repo, false, false, false)?;
    run_embedding_enrichment(&repo, embedding_online, false)?;
    Ok(json!({
        "status": "rebuilt",
        "rebuilt_chunks": report.rebuilt_chunks,
        "rebuilt_tree_entries": report.rebuilt_tree_entries,
        "sqlite_db": db,
    }))
}

fn parse_repair_args(args: Vec<String>) -> Result<()> {
    if args.is_empty() {
        return Err(KcsError::invalid_usage(
            "repair currently supports --rebuild-db",
        ));
    }
    let mut rebuild_db = false;
    for arg in args {
        match arg.as_str() {
            "--rebuild-db" if !rebuild_db => rebuild_db = true,
            "--rebuild-db" => {
                return Err(KcsError::invalid_usage(
                    "repair accepts --rebuild-db only once",
                ))
            }
            "--yes" => {}
            "--verify-objects" => {
                return Err(KcsError::new(
                    "KCS-E-CONFIG-NOT-IMPLEMENTED-001",
                    "repair --verify-objects is Step 4",
                    json!({ "flag": arg }),
                    ExitCode::InvalidUsage,
                ))
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
    if !rebuild_db {
        return Err(KcsError::invalid_usage(
            "repair currently supports --rebuild-db",
        ));
    }
    Ok(())
}

/// Resolved search mode plus the honest fallback reporting fields (05 §1.1/§1.7).
struct ResolvedMode {
    requested: SearchMode,
    resolved: SearchMode,
    fallback: bool,
    fallback_reason: Option<String>,
    error_code: Option<String>,
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

fn resolve_search_mode(requested: SearchMode, vector: &VectorAvailability) -> Result<ResolvedMode> {
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
                // --vector with no usable vector backend is a hard error (05 §1.2);
                // the code distinguishes "unavailable" from "incompatible" (03 §7).
                Err(KcsError::new(
                    error_code
                        .as_deref()
                        .unwrap_or("KCS-E-SEARCH-VEC-UNAVAIL-001"),
                    "vector search requested but no compatible embedding index is available",
                    json!({ "fallback_reason": reason }),
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
    /// The chunk's embedding (hybrid/vector mode only), fed into MMR (05 §1.4).
    /// `None` in text mode, which makes MMR skip and only the raw_hash dedup run.
    embedding: Option<Vec<f32>>,
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
    let (scope_mode, exec_scopes, cursor_excluded) = match &decoded_cursor {
        Some(cursor) => {
            let (exec, mut excluded) = resolve_cursor_exec_scopes(cursor)?;
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
            let (permitted, restricted): (Vec<ExecScope>, Vec<ExecScope>) = exec
                .into_iter()
                .partition(|exec| allowed_ids.contains(&exec.target.scope_id));
            for exec in restricted {
                excluded.push(json!({
                    "scope_id": exec.target.scope_id,
                    "scope_path": exec.target.repo_root,
                    "reason": "scope_restriction_mismatch",
                }));
            }
            (
                scope_selection_from_cursor(cursor.scope_mode),
                permitted,
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
    let precheck_mode = resolve_search_mode(parsed.requested_mode, &vector_precheck)?;
    // Only now, and only when the pre-resolved mode uses vectors, compute (send)
    // the query embedding. In --text this branch is never taken, so the query is
    // never sent.
    let uses_vectors = matches!(
        precheck_mode.resolved,
        SearchMode::Hybrid | SearchMode::Vector
    );
    let query_embedding = if uses_vectors {
        compute_query_embedding(&parsed.query)?
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
    let mode = resolve_search_mode(parsed.requested_mode, &vector)?;

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

    // query_hash covers the search's scope set. On a cursor replay that set is
    // the cursor token's OWN scope_id list (05 §1.8 — the cursor scope set is
    // truth), not the currently-resolvable subset: a scope that became
    // unreachable must surface as excluded_scopes/exit 3, never as a misleading
    // KCS-E-SEARCH-CURSOR-001 mismatch.
    let mut scope_ids = match &decoded_cursor {
        Some(cursor) => cursor
            .scopes
            .iter()
            .map(|sub| sub.scope_id.clone())
            .collect::<Vec<_>>(),
        None => exec_scopes
            .iter()
            .map(|exec| exec.target.scope_id.clone())
            .collect::<Vec<_>>(),
    };
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

    // Per-scope: FTS5 text ranks + chunk_vec KNN vector ranks -> RRF -> candidate
    // pool. Vector ranks are supplied only in hybrid/vector mode (K4).
    let tiers = build_fts_tiers(&parsed.query);
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
        match search_one_scope(exec, idx, &tiers, mode.resolved, scope_query_embedding) {
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
            return Err(KcsError::new(
                "KCS-E-SEARCH-VEC-UNAVAIL-001",
                "text and vector search are both unavailable: the search index (sqlite.db) is missing or corrupt in every scope; run `kcs repair --rebuild-db`",
                json!({ "excluded_scopes": excluded }),
                ExitCode::Failure,
            ));
        }
        return Err(scope_all_failed_error(
            "all searched scopes failed",
            excluded,
        ));
    }

    // N8: now that scope resolution, the all-failed check, and (below) index_status
    // are honored, a short (< 2 char) query — which produces no indexable token —
    // short-circuits the ranking/paging with an honest empty page that still
    // reports the real searched scopes and index_status.
    if parsed.query.chars().count() < 2 {
        return empty_search_response(&parsed, &repo, started, &mode, &searched, &excluded);
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
    // Only resolvable scopes count: a dropped (unreachable) scope's candidates are
    // no longer in the stream, so counting its consumed would silently swallow
    // results from the surviving scopes.
    let total_skip = match &decoded_cursor {
        Some(cursor) => {
            let resolved = exec_scopes
                .iter()
                .map(|exec| exec.target.scope_id.as_str())
                .collect::<BTreeSet<_>>();
            cursor
                .scopes
                .iter()
                .filter(|sub| resolved.contains(sub.scope_id.as_str()))
                .map(|scope| scope.consumed)
                .sum::<u64>() as usize
        }
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
            encode_cursor_token(
                &CursorToken {
                    version: 1,
                    scope_mode: cursor_mode_from_selection(scope_mode),
                    query_hash: qhash,
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

/// Exclusion reason for a scope observed mid-reindex (P10): HEAD has advanced to a
/// new generation but the rebuilt sqlite is not yet swapped in, so not one chunk is
/// live. Surfaced as `KCS-E-INDEX-REBUILDING-001` when it is the sole failure mode.
const INDEX_REBUILDING_REASON: &str = "index_rebuilding";

struct ScopeOutcome {
    snapshot_commit: String,
    max_rowid: u64,
    candidates: Vec<ScoredCandidate>,
}

fn search_one_scope(
    exec: &ExecScope,
    scope_index: usize,
    tiers: &[String],
    resolved_mode: SearchMode,
    query_embedding: Option<&[f32]>,
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
    if index_is_rebuilding(&conn, &snapshot_commit).map_err(ScopeSearchError::Fatal)? {
        return Err(ScopeSearchError::Excluded(
            INDEX_REBUILDING_REASON.to_owned(),
        ));
    }

    let max_rowid = match exec.max_rowid {
        Some(value) => value,
        None => current_max_rowid(&conn).map_err(ScopeSearchError::Fatal)?,
    };

    let chunking_config_hash = read_chunking_config(&repo)
        .map(|config| config.chunking_config_hash)
        .map_err(ScopeSearchError::Fatal)?;

    let want_vector = matches!(resolved_mode, SearchMode::Hybrid | SearchMode::Vector);

    // FTS5 text ranks (empty when the query has no indexable token). Vector-only
    // mode skips the text backend entirely (05 §1.3: no fusion, use vector order).
    let (text_ranks, mut meta) = if resolved_mode == SearchMode::Vector {
        (Vec::new(), BTreeMap::new())
    } else {
        fts_scope_search(
            &conn,
            &snapshot_commit,
            tiers,
            &chunking_config_hash,
            max_rowid,
        )
        .map_err(ScopeSearchError::Fatal)?
    };

    // chunk_vec KNN vector ranks (hybrid/vector mode with a query embedding).
    let vector_ranks = if want_vector {
        if let Some(query_vec) = query_embedding {
            let (ranks, vmeta) = vector_scope_search(
                &conn,
                &snapshot_commit,
                query_vec,
                &chunking_config_hash,
                max_rowid,
            )
            .map_err(ScopeSearchError::Fatal)?;
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
            snapshot_commit: snapshot_commit.clone(),
            chunk_hash: candidate.chunk_hash,
            rrf_score: candidate.rrf_score,
            meta: chunk_meta.clone(),
            embedding,
        });
    }

    Ok(ScopeOutcome {
        snapshot_commit,
        max_rowid,
        candidates,
    })
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
    snapshot_commit: &str,
    query_embedding: &[f32],
    chunking_config_hash: &str,
    max_rowid: u64,
) -> Result<(Vec<BackendRank>, BTreeMap<String, ChunkMeta>)> {
    let total = embedding_store::chunk_vec_count(conn).map_err(index_to_kcs)?;
    if total == 0 || query_embedding.len() != CHUNK_VEC_DIMENSIONS {
        return Ok((Vec::new(), BTreeMap::new()));
    }
    let query_bytes = f32_to_le_bytes(query_embedding);
    let knn =
        embedding_store::knn_chunk_distances(conn, &query_bytes, total).map_err(index_to_kcs)?;
    let chunk_ids = knn.iter().map(|(id, _)| id.clone()).collect::<Vec<_>>();
    let meta = fetch_live_meta(
        conn,
        snapshot_commit,
        &chunk_ids,
        chunking_config_hash,
        max_rowid,
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
    snapshot_commit: &str,
    chunk_ids: &[String],
    chunking_config_hash: &str,
    max_rowid: u64,
) -> Result<BTreeMap<String, ChunkMeta>> {
    if chunk_ids.is_empty() {
        return Ok(BTreeMap::new());
    }
    let placeholders = chunk_ids.iter().map(|_| "?").collect::<Vec<_>>().join(",");
    let sql = format!(
        "SELECT c.chunk_id, c.raw_hash, c.tool_profile_hash, c.heading_path,
                c.section_id, c.char_start, c.char_end, c.text, te.path
         FROM chunks c
         JOIN tree_entries te ON te.commit_hash = ?1
             AND te.raw_hash = c.raw_hash
             AND te.tool_profile_hash = c.tool_profile_hash
             AND te.gen = c.gen
         WHERE c.chunking_config_hash = ?2 AND c.rowid <= ?3
             AND c.chunk_id IN ({placeholders})"
    );
    let mut params: Vec<Box<dyn rusqlite::ToSql>> = vec![
        Box::new(snapshot_commit.to_owned()),
        Box::new(chunking_config_hash.to_owned()),
        Box::new(max_rowid as i64),
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
            heading_path: heading_path_raw
                .and_then(|value| serde_json::from_str::<Vec<String>>(&value).ok()),
            section_id: row
                .get::<_, Option<String>>(4)?
                .filter(|value| !value.is_empty()),
            char_start: row.get::<_, Option<i64>>(5)?.map(|value| value as u64),
            char_end: row.get::<_, Option<i64>>(6)?.map(|value| value as u64),
            text: row.get(7)?,
            path_at_commit: row.get(8)?,
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
/// the registry. A scope_id the registry can no longer resolve is returned as an
/// `excluded_scopes` entry (reason `unreachable`) rather than dropped silently —
/// the replay then follows partial-failure semantics (exit 3, CT3-MULTI-005),
/// never a misleading cursor-mismatch error.
fn resolve_cursor_exec_scopes(cursor: &CursorToken) -> Result<(Vec<ExecScope>, Vec<Value>)> {
    let mut exec = Vec::new();
    let mut excluded = Vec::new();
    for sub in &cursor.scopes {
        // O7: resolve through the shared registry resolver so a scope_id that a
        // `.kcs` copy made ambiguous is reported KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001
        // (like Evidence), not silently pinned to whichever row sorted first.
        match resolve_scope_id_in_registry(&sub.scope_id)? {
            Some(target) => exec.push(ExecScope {
                target,
                snapshot_commit: Some(sub.snapshot_commit.clone()),
                max_rowid: Some(sub.max_rowid),
                from_cursor: true,
            }),
            None => excluded.push(json!({
                "scope_id": sub.scope_id,
                "scope_path": Value::Null,
                "reason": "unreachable",
            })),
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
        "commit_shallow": resolved.commit_shallow,
    }))
}

fn run_reindex(args: UnsupportedArgs) -> Result<Value> {
    let parsed = parse_reindex_args(without_json(args.args))?;
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
    let repo = Repository::open_current()?;
    // M1(a): serialize reindex (re-normalize + rebuild) against concurrent
    // index/repair/reindex. Reentrant with the internal auto-snapshot.
    let _lock = repo.lock_store()?;
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
    // L1: reindex = re-normalize + re-embedding (docs/06). The rebuild appends
    // fresh chunk rows; enrich them symmetrically with the `kcs index` path so
    // the embedding index tracks the new generation. Online only under the
    // embedding adapter's opt-in; offline this enqueues Embedding tasks so
    // `index_status` reports the pending enrichment instead of falsely showing
    // enriched_ratio = 1.0 (the tasks would otherwise never be created).
    let embedding_online = embedding_online_allowed(&repo, false, false, false)?;
    run_embedding_enrichment(&repo, embedding_online, false)?;
    Ok(json!({
        "status": "reindexed",
        "reindexed_files": reindexed,
        "commit_hash": outcome.commit_hash,
        "rebuilt_chunks": report.rebuilt_chunks,
    }))
}

#[derive(Debug, Default)]
struct ParsedReindex {
    force: bool,
    yes: bool,
}

fn parse_reindex_args(args: Vec<String>) -> Result<ParsedReindex> {
    let mut parsed = ParsedReindex::default();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--force" => parsed.force = true,
            "--yes" => parsed.yes = true,
            "--at" => {
                if i + 1 >= args.len() {
                    return Err(KcsError::invalid_usage("--at requires a commit argument"));
                }
                return Err(KcsError::new(
                    "KCS-E-CONFIG-NOT-IMPLEMENTED-001",
                    "reindex --at is not implemented in Step 3",
                    json!({ "flag": "--at" }),
                    ExitCode::InvalidUsage,
                ));
            }
            value if value.starts_with('-') => {
                return Err(KcsError::invalid_usage(format!(
                    "unknown reindex flag: {value}"
                )));
            }
            value => {
                return Err(KcsError::invalid_usage(format!(
                    "unexpected reindex argument: {value}"
                )));
            }
        }
        i += 1;
    }
    Ok(parsed)
}

fn rebuild_step3_index(repo: &Repository) -> Result<Step3RebuildReport> {
    let Some(head) = repo.head_commit_hash()? else {
        return Ok(Step3RebuildReport::default());
    };
    let commit = repo.read_commit(&head)?;
    let tree = repo.read_tree(&commit.tree)?;
    let config = read_chunking_config(repo)?;
    let existing = read_stored_chunks(repo.kcs_dir())?;
    // Q1: physically remove any torn trailing record from `chunks.jsonl` before the
    // append below, so the new records land on a clean `'\n'`-terminated boundary
    // instead of being welded onto the torn bytes (which would create a
    // permanently-skipped malformed line and re-brick every later rebuild).
    // read/skip alone is not self-healing; this truncation is what makes it so.
    truncate_torn_chunk_tail(repo.kcs_dir())?;
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
    // The SQLite `tree_entries` table (below) is the single source of truth for
    // live-chunk resolution (search and short-hash resolution both read it via
    // `ensure_snapshot_tree_entries`). The former JSON projection went stale after
    // a bare snapshot and is no longer written (L3).
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
    .map_err(|err| store_corrupt_error(&manifest_path, err.to_string()))?;
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
        .map_err(|err| store_corrupt_error(&unit_path, err.to_string()))?;
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
            Ok(chunk) => chunks.push(chunk),
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
    Ok(chunks)
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

fn rebuild_sqlite_index(kcs_dir: &Path, tree_entries: &[TreeEntryRow]) -> Result<()> {
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
    let preserved = if path.exists() {
        let existing = Connection::open(&path).map_err(|err| KcsError::schema(err.to_string()))?;
        let rows = embedding_store::snapshot_chunk_embeddings(&existing).map_err(index_to_kcs)?;
        drop(existing);
        rows
    } else {
        Vec::new()
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
    match build_sqlite_index_at(&temp_path, kcs_dir, tree_entries, &preserved) {
        Ok(()) => fs::rename(&temp_path, &path)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string())),
        Err(error) => {
            let _ = fs::remove_file(&temp_path);
            Err(error)
        }
    }
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
    tree_entries: &[TreeEntryRow],
    preserved: &[embedding_store::ChunkEmbeddingSnapshotRow],
) -> Result<()> {
    let mut fts = SqliteFtsIndex::open(
        temp_path,
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
    // Replay preserved embeddings (source of truth) and re-derive chunk_vec.
    for row in preserved {
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
    embedding_store::rebuild_chunk_vec(fts.connection()).map_err(index_to_kcs)?;
    drop(fts);
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
            .map(registry_entry_target)
            .filter(|target| participates_in_global_search(&target.kcs_dir))
            .collect(),
    ))
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
        "diversify": { "strategy": "group_by_raw_hash" },
        "paging": { "limit": parsed.limit, "next_cursor": Value::Null },
        "searched_scopes": searched_scopes,
        "excluded_scopes": excluded_scopes,
        "index_status": compute_index_status(searched),
        "results": [],
    });
    append_search_logs(repo, &response, started)?;
    if !excluded_scopes.is_empty() {
        if let Some(object) = response.as_object_mut() {
            object.insert("__exit_code".to_owned(), json!(3));
        }
    }
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
    // M1(b): frame the record as one buffer and emit it with a single write_all so
    // concurrent appends cannot interleave byte-wise under O_APPEND.
    let mut line = serde_json::to_string(value)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    line.push('\n');
    file.write_all(line.as_bytes())
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
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
        let mut input = String::new();
        std::io::Read::read_to_string(&mut std::io::stdin(), &mut input)
            .map_err(|err| KcsError::io(err.to_string(), "stdin"))?;
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
    let is_raw = raw_path_hint.is_some() || raw_object_present(&target, hash)?;
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
            Ok(ShortHash::Chunk(Box::new(pointer)))
        }
        (false, true) => Ok(ShortHash::Raw {
            target,
            raw_hash: hash.to_owned(),
            path_hint: raw_path_hint,
        }),
        (false, false) => Err(KcsError::invalid_usage(
            "short hash is not found in the current scope",
        )),
    }
}

/// True when a raw object with `raw_hash` is present in the working tree or the
/// CAS raw store (08 §2.3 rule 4 raw resolution). Used only for the raw-only
/// short-hash case (no chunk carries the raw_hash).
fn raw_object_present(target: &ScopeTarget, raw_hash: &str) -> Result<bool> {
    if cas_object_path(&target.kcs_dir, "raw", raw_hash).is_file() {
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

    // 08 §3.1 step 2: fetch the commit object (append-only; never GC'd).
    let commit = repo.read_commit(&pointer.commit)?;

    // 08 §3.1 step 2a/3-4: a shallow commit (tree object discarded) skips the
    // tree walk; otherwise the raw_hash must appear in commit.tree for the
    // pointer to resolve against *this* commit's snapshot (not the working tree
    // of some later commit).
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
                if let Some(tombstone) = read_tombstone(&target, &pointer.raw_hash)? {
                    return Err(tombstone_error(tombstone));
                }
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
        Err(error) if is_store_not_found(&error) => (true, None),
        Err(error) => return Err(error),
    };

    // 08 §3.1 step 5: purged raw_hash carrying a tombstone -> tombstone response.
    if let Some(tombstone) = read_tombstone(&target, &pointer.raw_hash)? {
        return Err(tombstone_error(tombstone));
    }

    // 08 §3.1 step 6-7: chunk_hash -> chunk text (the normalized instance is
    // keyed by (raw_hash, tool_profile_hash, gen); chunk rows carry the span).
    // A pointer whose chunk_hash has NO materialized chunk row in this scope
    // cannot be served under this tool_profile_hash — that is 08 §3.2's
    // "tool_profile_hash 不一致: chunk が存在しない場合は retarget が必要 (§5)",
    // exit 8 (06 §7). Applies on the shallow path too: chunk rows outlive tree
    // discard, so their absence means the profile mismatch, not GC.
    let chunk = read_stored_chunks(&target.kcs_dir)?
        .into_iter()
        .find(|chunk| chunk.row.chunk_id == pointer.chunk_hash);
    let Some(chunk) = chunk else {
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
    };
    // M6: the resolved chunk row must bind to the pointer's (raw_hash,
    // tool_profile_hash). A chunk_hash that materializes under a *different* raw
    // or tool identity than the pointer claims is a tampered pointer — reject it
    // rather than serve inconsistent evidence (body from A, raw from B).
    if chunk.row.raw_hash != pointer.raw_hash
        || chunk.row.tool_profile_hash != pointer.tool_profile_hash
    {
        return Err(invalid_pointer_identity_error(pointer));
    }
    // N5: on a non-shallow commit, the chunk's generation must equal the tree
    // entry's normalize.gen. Otherwise a pointer to an old commit could resolve a
    // chunk_hash from a *newer* generation (post `reindex --force`), serving body
    // from gen N+1 under a commit that only ever normalized gen N. The shallow
    // path has no tree entry, so gen stays unbound there (chunk (raw, tool)
    // identity is the only available check).
    if let Some(entry_gen) = entry_gen {
        if chunk.row.gen != entry_gen {
            return Err(invalid_pointer_identity_error(pointer));
        }
    }
    let text = chunk.row.text;

    // Raw object resolution: working tree first (rename-tolerant), else CAS
    // read-only expansion. Absent from both with no tombstone -> not_found.
    match open_raw_object(
        &target,
        &pointer.raw_hash,
        pointer.path_at_commit.as_deref(),
    )? {
        Some((path, temporary)) => Ok(PointerResolution {
            path: Some(path),
            text: Some(text),
            temporary,
            commit_shallow,
        }),
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
    if scan_working_tree {
        if let Some(path) = find_working_tree_raw(&target.repo_root, hash)? {
            return Ok(Some((path, false)));
        }
    }
    let object_path = cas_object_path(&target.kcs_dir, subdir, hash);
    if !object_path.is_file() {
        return Ok(None);
    }
    let basename = path_hint
        .and_then(|path| Path::new(path).file_name())
        .and_then(|name| name.to_str())
        .unwrap_or("object");
    // P9 (06 §1.1): the read-only expansion cache belongs under $XDG_CACHE_HOME
    // (regenerable, safe to purge), not $XDG_DATA_HOME (durable truth/state).
    let cache = cache_home()
        .join("kcs/open")
        .join(
            hash.trim_start_matches("sha256:")
                .chars()
                .take(12)
                .collect::<String>(),
        )
        .join(basename);
    // M5: the open cache is idempotent. A prior open already materialized this
    // object read-only; a second open must reuse it, not `fs::copy` onto a
    // read-only destination (EACCES). Reuse the cached file when it already
    // exists (the CAS object is immutable, so the content is identical).
    if cache.is_file() {
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
    let bytes = fs::read(&object_path)
        .map_err(|err| KcsError::io(err.to_string(), object_path.display().to_string()))?;
    if hash_bytes(&bytes) != hash {
        return Err(KcsError::new(
            "KCS-E-STORE-CORRUPT-001",
            "CAS object hash mismatch",
            json!({ "path": object_path.display().to_string(), "expected": hash }),
            ExitCode::PermanentFailure,
        ));
    }
    if let Some(parent) = cache.parent() {
        fs::create_dir_all(parent)
            .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    }
    fs::write(&cache, &bytes)
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

/// Fan-out path of a content-hashed CAS byte object: `objects/<subdir>/ab/cd/<hash>`
/// (03 §2 / §8.1). `subdir` is the object-type directory ("raw" / "prepared" /
/// "images").
fn cas_object_path(kcs_dir: &Path, subdir: &str, hash: &str) -> PathBuf {
    let digest = hash.trim_start_matches("sha256:");
    kcs_dir
        .join("objects")
        .join(subdir)
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(hash)
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
    match open_cas_byte_object(&target, subdir, scan_working_tree, &object.hash, None)? {
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
    .map_err(|err| store_corrupt_error(&manifest_path, err.to_string()))?;
    manifest["parent_gen"] = json!(old_gen);
    manifest["gen"] = json!(new_gen);
    manifest["run_id"] = json!(format!("run_{}", new_ulid(kcs_dir)));
    manifest["generated_at"] = json!(now_utc_seconds());
    let manifest_bytes =
        serde_json::to_vec_pretty(&manifest).map_err(|err| KcsError::schema(err.to_string()))?;
    atomic_overwrite_file(&new_dir.join("manifest.json"), &manifest_bytes)?;
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
            .map_err(|err| store_corrupt_error(&entry.path(), err.to_string()))?;
        unit["gen"] = json!(new_gen);
        unit["generated_at"] = json!(now_utc_seconds());
        let unit_bytes =
            serde_json::to_vec_pretty(&unit).map_err(|err| KcsError::schema(err.to_string()))?;
        atomic_overwrite_file(&new_dir.join(entry.file_name()), &unit_bytes)?;
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
    // O3: `batch resume` / `batch retry` read-modify-write `tasks.jsonl` and drive
    // online sends, so hold the folder store lock end-to-end — the same guard M1
    // wired onto index/repair/reindex. Without it two concurrent `batch resume`
    // runs interleave the ledger and double-send held tasks. Reentrant with any
    // inner auto-snapshot; losers fail fast with KCS-E-STORE-LOCKED-001 (exit 3).
    let _lock = repo.lock_store()?;
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
            let executed = execute_pending_tasks(&repo, &store, resume.override_budget)?;
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
            // `batch retry` never overrides the budget cap (retry re-schedules,
            // it does not bypass caps — `batch resume --override-budget` does).
            let executed = execute_pending_tasks(&repo, &store, false)?;
            Ok(
                json!({ "status": "retry scheduled", "tasks_updated": changed, "tasks_executed": executed }),
            )
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

fn execute_pending_tasks(
    repo: &Repository,
    store: &TaskStore,
    override_budget: bool,
) -> Result<usize> {
    let mut executed = 0usize;
    // Q3: under the folder store lock, any Running task is an orphan from a crashed
    // run — reclaim it to Pending so this pass re-executes it.
    reclaim_orphaned_running_tasks(store)?;
    // Markdownize and embedding opt-ins are per-adapter (07 §3, L4): gate each
    // adapter on its own approval rather than one blanket check.
    if persistent_network_allowed(repo)? {
        executed += execute_pending_markdownize_tasks(repo, store, override_budget)?;
    }
    // Embedding tasks are executed by the same enrichment pass `kcs index` uses;
    // without this, rate-limited Pending embedding tasks could never be completed
    // by `batch resume` / `batch retry`. `override_budget` reaches the budget
    // judgement (L2) and the embedding opt-in is the embedding adapter's own (L4).
    let embedding_online = embedding_online_allowed(repo, false, false, false)?;
    executed += run_embedding_enrichment(repo, embedding_online, override_budget)?;
    Ok(executed)
}

/// Execute Pending online markdownize tasks, honoring `override_budget` (L2 i).
fn execute_pending_markdownize_tasks(
    repo: &Repository,
    store: &TaskStore,
    override_budget: bool,
) -> Result<usize> {
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
    let online_profile = online_markdownize_profile();
    let output_ref = online_output_ref(&online_profile.adapter_id);
    let tasks = store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.status == TaskStatus::Pending
                && task.task_type == TaskType::Markdownize
                && task.output_ref == output_ref
                // Honor an unelapsed retry backoff even for a Pending task
                // (Step2c I2); `batch retry` already gates on this, so this is
                // a defensive belt-and-braces guard.
                && task_retry_due(task)
                && (secrets_approved
                    || classify_secret(&task.input_path) != Some(SecretTier::TierB))
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
            adapter_id: Some(online_profile.adapter_id.clone()),
        };
        let (device_remaining, folder_remaining) = budget_remaining_for_adapter(
            &cost_ledger,
            &budget_caps,
            &month,
            &scope_id,
            adapter_kind_budget_key(online_profile.adapter_kind),
        )?;
        let budget = evaluate_budget_with_caps(
            &estimate,
            device_remaining,
            folder_remaining,
            override_budget,
        );
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
    if read_allow_network_config(&kcs_dir.join("config.toml"))? == Some(true)
        || read_allow_network_config(&user_config_toml_path())? == Some(true)
    {
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
    let expected_scope_id = scope_id(kcs_dir)?;
    let path = kcs_dir.join("approvals.jsonl");
    let Ok(text) = fs::read_to_string(&path) else {
        return Ok(false);
    };
    Ok(text
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .any(|value| {
            value.get("scope_id").and_then(Value::as_str) == Some(expected_scope_id.as_str())
                && tool_id
                    .map(|tool_id| value.get("tool_id").and_then(Value::as_str) == Some(tool_id))
                    .unwrap_or(true)
                && value.get("execution_mode").and_then(Value::as_str) == Some("online_api")
                && value.get("network_opt_in").and_then(Value::as_bool) == Some(true)
        }))
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
    let prepare_profile_hash = builtin_prepare_profile().tool_profile_hash;
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
    let scope_id = repo.scope_id_for_adapter();
    let outcome = run_standard_online_markdownize(StandardOnlineMarkdownizeRequest {
        scope_id: &scope_id,
        kcs_dir: repo.kcs_dir(),
        raw_hash: &task.input_hash,
        path: &path,
        media_type: &media_type,
        prepared_unit_hints: prepared_unit_hints(&prepare.prepared_units),
    })
    .map_err(task_failure_from_adapter)?;
    let profile = outcome.profile;
    let response = outcome.response;
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

// ===========================================================================
// K4 — embedding catalog wiring (adapter selection, index generation, query
// embedding).
// ===========================================================================

const EMBEDDING_ADAPTER_KIND: &str = "embedding";
/// Chunks embedded per adapter batch. Task granularity is per-chunk; adapter
/// call granularity is this.
const EMBEDDING_BATCH_SIZE: usize = 32;

fn embedding_execution() -> Option<AdoptedEmbeddingExecution> {
    active_adopted_embedding_execution()
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
    run_adopted_embedding(execution, items, input_type).map_err(task_failure_from_adapter)
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

/// A live chunk awaiting an embedding (current chunking_config_hash, HEAD-live).
struct EmbeddableChunk {
    chunk_id: String,
    text: String,
    text_hash: String,
    raw_path: String,
}

/// Generate chunk embeddings for the scope after the SQLite index is rebuilt
/// (04 §4.3 / 07 §5.3). Enqueues one `TaskType::Embedding` task per pending chunk,
/// then — if the online opt-in and budget allow — embeds them (batched), writing
/// the `embeddings` rows (source of truth) and `chunk_vec` (derived KNN copy),
/// charging the cost ledger under `adapter_kind="embedding"`. Offline leaves tasks
/// Pending (surfaced by `index_status`). No-op when no embedding adapter is
/// configured (keeps the default index path unchanged).
fn generate_scope_embeddings(repo: &Repository, args: &IndexArgs) -> Result<()> {
    // Embedding online opt-in is the embedding adapter's own (L4), not a
    // ride-along on the markdownize approval. `--offline` forces enqueue-only;
    // N7: `--online` now reaches the embedding adapter too (was ignored).
    let online =
        embedding_online_allowed(repo, args.offline, args.online, args.yes || args.approve)?;
    run_embedding_enrichment(repo, online, false).map(|_| ())
}

/// Core enrichment pass shared by `kcs index` (inline) and `kcs batch
/// resume/retry`. Without the resume path, embedding tasks left Pending by a
/// rate limit could never complete (`batch resume` only executed Markdownize
/// tasks). Returns the number of chunks embedded in this pass.
fn run_embedding_enrichment(
    repo: &Repository,
    online: bool,
    override_budget: bool,
) -> Result<usize> {
    let Some(execution) = embedding_execution() else {
        return Ok(0);
    };
    let profile = declared_embedding_profile(execution);
    // Non-multimodal is rejected at materialize_tool_lock; never reach embed here.
    if profile.modality != "multimodal" {
        return Ok(0);
    }
    let db_path = sqlite_path(repo.kcs_dir());
    if !db_path.exists() {
        return Ok(0);
    }
    let conn = Connection::open(&db_path).map_err(|err| KcsError::schema(err.to_string()))?;
    let Some(head) = repo.head_commit_hash()? else {
        return Ok(0);
    };
    // `kcs snapshot` advances HEAD without projecting tree_entries (search
    // projects lazily); do the same here or the live-chunk JOIN silently
    // matches nothing for any scope whose last commit was a snapshot.
    ensure_snapshot_tree_entries(repo, &conn, &head)?;
    let chunking_config_hash = read_chunking_config(repo)?.chunking_config_hash;
    let pending = live_chunks_without_embedding(&conn, &head, &chunking_config_hash, &profile)?;
    if pending.is_empty() {
        return Ok(0);
    }

    let task_store = TaskStore::new(repo.kcs_dir());
    let now = now_utc_seconds();
    // N1a: partition off chunks whose raw file is a Tier B (candidate-secret)
    // document without a `--send-secrets` approval. Their embedding tasks are held
    // (Paused `secrets_tier_b_hold`, visible in `kcs status`) and never enter the
    // send pipeline, so `index --online` / `batch resume` cannot ship their text
    // to the embedding API. Approval moves them back into `sendable`.
    let secrets_approved = secrets_send_approved(repo);
    let (held, sendable): (Vec<EmbeddableChunk>, Vec<EmbeddableChunk>) =
        pending.into_iter().partition(|chunk| {
            !secrets_approved && classify_secret(&chunk.raw_path) == Some(SecretTier::TierB)
        });
    hold_secret_embedding_tasks(&task_store, repo, &held, &now)?;
    if sendable.is_empty() {
        return Ok(0);
    }
    enqueue_embedding_tasks(&task_store, repo, &sendable, online, &now)?;
    if !online {
        // Offline: tasks stay Pending; `index_status` reports them (05 §1.7).
        return Ok(0);
    }

    // L2(ii)/L7: skip chunks whose embedding task is sticky budget-Paused (unless
    // override) or a Failed task that is not retry-eligible (unelapsed backoff or
    // non-retryable) — the same lifecycle semantics markdownize already honors.
    let embeddable = filter_embeddable_by_task_state(&task_store, sendable, override_budget)?;
    if embeddable.is_empty() {
        return Ok(0);
    }

    let mut executed = 0usize;
    let cost_ledger = CostLedger::new(cost_ledger_path());
    let budget_caps =
        read_budget_policy(user_config_toml_path(), repo.kcs_dir().join("config.toml"))
            .map_err(pipeline_to_kcs)?;
    let month = utc_month(&now);
    let scope_id = repo.scope_id_for_adapter();

    for batch in embeddable.chunks(EMBEDDING_BATCH_SIZE) {
        // Split content-addressed reuse (no API call, free) from chunks that
        // require a live adapter call (CT3-EMBED-006).
        let plan = match plan_embed_batch(&conn, &profile, batch) {
            Ok(plan) => plan,
            Err(failure) => {
                fail_embedding_tasks(&task_store, batch, failure.retry_kind, &now)?;
                break;
            }
        };
        // L6: reuse links are free and always succeed → link + complete them up
        // front so an API failure on the *sent* portion can never contaminate an
        // already-materialized (chunk_vec written) chunk into a stuck Failed task.
        if !plan.reuse.is_empty() {
            match link_reused_chunks(&conn, &profile, &plan.reuse) {
                Ok(()) => {
                    complete_embedding_tasks(
                        &task_store,
                        plan.reuse.iter().map(|(chunk, _)| *chunk),
                    )?;
                    executed += plan.reuse.len();
                }
                Err(failure) => {
                    fail_embedding_tasks(
                        &task_store,
                        plan.reuse.iter().map(|(chunk, _)| *chunk),
                        failure.retry_kind,
                        &now,
                    )?;
                    break;
                }
            }
        }
        if plan.to_send.is_empty() {
            continue;
        }
        // L5: budget judgement and ledger charge only the chars actually sent to
        // the API — reused chunks issue no request and must not be billed.
        let sent_chars: u64 = plan
            .to_send
            .iter()
            .map(|(chunk, _)| chunk.text.chars().count() as u64)
            .sum();
        let estimate = BudgetEstimate {
            scope_id: scope_id.clone(),
            task_type: TaskType::Embedding,
            estimated_usd: estimate_embedding_cost(sent_chars),
            adapter_id: Some(profile.tool_id.clone()),
        };
        let (device_remaining, folder_remaining) = budget_remaining_for_adapter(
            &cost_ledger,
            &budget_caps,
            &month,
            &scope_id,
            EMBEDDING_ADAPTER_KIND,
        )?;
        let budget = evaluate_budget_with_caps(
            &estimate,
            device_remaining,
            folder_remaining,
            override_budget,
        );
        if !budget.allowed {
            // Budget exhausted: pause the remaining to-send chunks
            // (index_status.budget_paused). Already-linked reuse stays done.
            pause_embedding_tasks(&task_store, plan.to_send.iter().map(|(chunk, _)| *chunk))?;
            break;
        }
        match send_embed_batch(&conn, execution, &profile, &plan.to_send) {
            Ok(()) => {
                cost_ledger
                    .append_monthly(&MonthlyCostLedgerEntry {
                        month: month.clone(),
                        scope_id: scope_id.clone(),
                        adapter_kind: EMBEDDING_ADAPTER_KIND.to_owned(),
                        usd: estimate.estimated_usd,
                    })
                    .map_err(pipeline_to_kcs)?;
                complete_embedding_tasks(
                    &task_store,
                    plan.to_send.iter().map(|(chunk, _)| *chunk),
                )?;
                executed += plan.to_send.len();
            }
            Err(failure) => {
                // Enrichment failure is non-fatal: mark the sent chunks failed and
                // stop (search sees no embeddings → text). Never fails `kcs index`.
                fail_embedding_tasks(
                    &task_store,
                    plan.to_send.iter().map(|(chunk, _)| *chunk),
                    failure.retry_kind,
                    &now,
                )?;
                break;
            }
        }
    }
    Ok(executed)
}

/// A batch split into free content-addressed reuse and chunks needing an API call.
struct EmbedBatchPlan<'a> {
    /// (chunk, existing content-vector bytes) — link `chunk_vec`, no adapter call.
    reuse: Vec<(&'a EmbeddableChunk, Vec<u8>)>,
    /// (chunk, embedding_hash) — must be sent to the adapter.
    to_send: Vec<(&'a EmbeddableChunk, String)>,
}

/// Classify a batch into reuse vs. to-send by probing the content-addressed
/// `embeddings` store (CT3-EMBED-006). No writes, no adapter calls.
fn plan_embed_batch<'a>(
    conn: &Connection,
    profile: &DeclaredEmbeddingProfile,
    batch: &'a [EmbeddableChunk],
) -> std::result::Result<EmbedBatchPlan<'a>, TaskExecutionFailure> {
    let mut reuse = Vec::new();
    let mut to_send = Vec::new();
    for chunk in batch {
        let embedding_hash =
            chunk_embedding_hash(chunk, profile).map_err(|_| TaskExecutionFailure {
                retry_kind: RetryErrorKind::ContractViolation,
            })?;
        match embedding_store::content_vector(conn, &embedding_hash) {
            Ok(Some(bytes)) => reuse.push((chunk, bytes)),
            Ok(None) => to_send.push((chunk, embedding_hash)),
            Err(_) => {
                return Err(TaskExecutionFailure {
                    retry_kind: RetryErrorKind::ContractViolation,
                })
            }
        }
    }
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
    to_send: &[(&EmbeddableChunk, String)],
) -> std::result::Result<(), TaskExecutionFailure> {
    let items = to_send
        .iter()
        .map(|(chunk, _)| EmbeddingItem {
            id: chunk.chunk_id.clone(),
            text: Some(chunk.text.clone()),
            path: None,
            mime: None,
        })
        .collect::<Vec<_>>();
    let vectors = run_embedding_adapter(execution, items, EmbeddingInputType::MarkdownChunk)?;
    let by_id = vectors
        .into_iter()
        .map(|vector| (vector.id, vector.vector))
        .collect::<BTreeMap<_, _>>();
    for (chunk, embedding_hash) in to_send {
        let Some(vector) = by_id.get(&chunk.chunk_id) else {
            return Err(TaskExecutionFailure {
                retry_kind: RetryErrorKind::ContractViolation,
            });
        };
        let bytes = f32_to_le_bytes(vector);
        embedding_store::write_chunk_embedding(
            conn,
            embedding_hash,
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
    let by_ref = tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .map(|task| (task.output_ref.clone(), task))
        .collect::<BTreeMap<_, _>>();
    Ok(pending
        .into_iter()
        .filter(|chunk| {
            let output_ref = embedding_task_output_ref(&chunk.chunk_id);
            match by_ref.get(&output_ref) {
                Some(task) => embeddable_task_state(task, override_budget),
                // No task row yet (should not happen post-enqueue): embed it.
                None => true,
            }
        })
        .collect())
}

/// Whether an embedding task's current state permits embedding its chunk now.
fn embeddable_task_state(task: &TaskDescriptor, override_budget: bool) -> bool {
    match task.status {
        // Sticky budget pause (L2 ii): only an explicit override re-includes it;
        // any other Paused reason is safe to re-drive.
        TaskStatus::Paused => {
            override_budget || task.fallback_reason.as_deref() != Some("budget_exceeded")
        }
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

/// Live chunks (current chunking_config_hash, HEAD tree_entries) that have no
/// `chunk_vec` row yet.
fn live_chunks_without_embedding(
    conn: &Connection,
    head: &str,
    chunking_config_hash: &str,
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

    let mut stmt = conn
        .prepare(
            "SELECT c.chunk_id, c.text, c.text_hash, c.raw_path
             FROM chunks c
             JOIN tree_entries te ON te.commit_hash = ?1
                 AND te.raw_hash = c.raw_hash
                 AND te.tool_profile_hash = c.tool_profile_hash
                 AND te.gen = c.gen
             WHERE c.chunking_config_hash = ?2
             ORDER BY c.rowid",
        )
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let rows = stmt
        .query_map(rusqlite::params![head, chunking_config_hash], |row| {
            Ok(EmbeddableChunk {
                chunk_id: row.get(0)?,
                text: row.get(1)?,
                text_hash: row.get(2)?,
                raw_path: row.get(3)?,
            })
        })
        .map_err(|err| KcsError::schema(err.to_string()))?;
    let mut pending = Vec::new();
    for row in rows {
        let chunk = row.map_err(|err| KcsError::schema(err.to_string()))?;
        let embedding_hash = chunk_embedding_hash(&chunk, profile)?;
        let has_current_profile = embedding_store::content_vector(conn, &embedding_hash)
            .map_err(index_to_kcs)?
            .is_some();
        if !(has_current_profile && existing.contains(&chunk.chunk_id)) {
            pending.push(chunk);
        }
    }
    Ok(pending)
}

fn embedding_task_output_ref(chunk_id: &str) -> String {
    format!("embedding:{chunk_id}")
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
    let existing = task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .map(|task| task.output_ref)
        .collect::<BTreeSet<_>>();
    for chunk in held {
        let output_ref = embedding_task_output_ref(&chunk.chunk_id);
        if existing.contains(&output_ref) {
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
        };
        task_store.append(&task).map_err(pipeline_to_kcs)?;
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
    let existing = task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .map(|task| task.output_ref)
        .collect::<BTreeSet<_>>();
    let reason = if online {
        "ready_for_online_adapter"
    } else {
        "network_opt_in_required"
    };
    for chunk in pending {
        let output_ref = embedding_task_output_ref(&chunk.chunk_id);
        if existing.contains(&output_ref) {
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
        };
        task_store.append(&task).map_err(pipeline_to_kcs)?;
    }
    Ok(())
}

fn update_embedding_tasks<'a>(
    task_store: &TaskStore,
    chunks: impl IntoIterator<Item = &'a EmbeddableChunk>,
    status: TaskStatus,
    reason: &str,
    failure_kind: Option<RetryErrorKind>,
    now: Option<&str>,
) -> Result<()> {
    let refs = chunks
        .into_iter()
        .map(|chunk| embedding_task_output_ref(&chunk.chunk_id))
        .collect::<BTreeSet<_>>();
    if refs.is_empty() {
        return Ok(());
    }
    task_store
        .update_matching(|task| {
            if task.task_type == TaskType::Embedding && refs.contains(&task.output_ref) {
                task.status = status;
                task.fallback_reason = Some(reason.to_owned());
                if let Some(kind) = failure_kind {
                    let attempts_after = task.attempts.saturating_add(1);
                    let policy = retry_policy(kind);
                    let retryable = policy.retryable
                        && policy
                            .max_attempts
                            .map(|max| attempts_after < max)
                            .unwrap_or(true);
                    task.attempts = attempts_after;
                    task.next_retry_at = retryable.then(|| {
                        scheduled_retry_at(now.unwrap_or(""), &policy.backoff, attempts_after)
                    });
                }
                true
            } else {
                false
            }
        })
        .map_err(pipeline_to_kcs)?;
    Ok(())
}

fn complete_embedding_tasks<'a>(
    task_store: &TaskStore,
    chunks: impl IntoIterator<Item = &'a EmbeddableChunk>,
) -> Result<()> {
    update_embedding_tasks(
        task_store,
        chunks,
        TaskStatus::Done,
        "embedding_adapter_done",
        None,
        None,
    )
}

fn pause_embedding_tasks<'a>(
    task_store: &TaskStore,
    chunks: impl IntoIterator<Item = &'a EmbeddableChunk>,
) -> Result<()> {
    update_embedding_tasks(
        task_store,
        chunks,
        TaskStatus::Paused,
        "budget_exceeded",
        None,
        None,
    )
}

fn fail_embedding_tasks<'a>(
    task_store: &TaskStore,
    chunks: impl IntoIterator<Item = &'a EmbeddableChunk>,
    kind: RetryErrorKind,
    now: &str,
) -> Result<()> {
    update_embedding_tasks(
        task_store,
        chunks,
        TaskStatus::Failed,
        retry_reason(kind),
        Some(kind),
        Some(now),
    )
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

fn online_output_ref(adapter_id: &str) -> String {
    format!("online:{adapter_id}")
}

fn online_markdownize_profile() -> AdapterProfile {
    standard_online_markdownize_profile()
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

    let mut result = IndexPipelineResult {
        network_allowed,
        ..IndexPipelineResult::default()
    };
    // N1a: a Tier B (candidate-secret) file is ingested locally but its online
    // task is held unless the scope carries an explicit `--send-secrets` approval.
    let secrets_approved = secrets_send_approved(repo);

    for candidate in preview
        .candidates
        .iter()
        .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
    {
        let secrets_hold = candidate.quarantine_reason.as_deref() == Some("secrets_tier_b_warning")
            && !secrets_approved;
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
                secrets_hold,
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
            secrets_hold,
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

/// Q2: crash-atomic write of a derived CAS byte object (prepared / image). Writes
/// to a uniquely-named temp file in the destination directory, fsyncs it, then
/// renames into place, so a crash / ENOSPC mid-write can never leave a partial
/// file under the final `sha256:` name. `cas::atomic_write` is `pub(crate)` and
/// unreachable from here, so this mirrors it locally. The caller keeps its
/// `if !path.exists()` dedup skip before calling this.
fn atomic_write_cas_object(path: &Path, bytes: &[u8]) -> Result<()> {
    use std::sync::atomic::{AtomicU64, Ordering};
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent)
        .map_err(|err| KcsError::io(err.to_string(), parent.display().to_string()))?;
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or_default();
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let temp = parent.join(format!(".tmp-{}-{}-{}", process::id(), nanos, seq));
    {
        let mut file = fs::File::create(&temp)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        file.write_all(bytes)
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
        file.sync_all()
            .map_err(|err| KcsError::io(err.to_string(), temp.display().to_string()))?;
    }
    fs::rename(&temp, path).map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))
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
            // Q2: crash-atomic (temp + fsync + rename) so a torn write cannot
            // leave a partial prepared object under the final `sha256:` name.
            atomic_write_cas_object(&path, object_bytes)?;
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
    secrets_hold: bool,
    args: &IndexArgs,
    created_at: &str,
    result: &mut IndexPipelineResult,
    cost_ledger: &CostLedger,
    budget_caps: &BudgetCaps,
    month: &str,
) -> Result<()> {
    let online_profile = online_markdownize_profile();
    let output_ref = online_output_ref(&online_profile.adapter_id);
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
    // N1a: a Tier B (candidate-secret) file without `--send-secrets` is held here
    // — a Paused task with `secrets_tier_b_hold`, visible in `kcs status`, that
    // `batch resume` will not un-hold and `execute_pending_markdownize_tasks` will
    // not send. The hold takes precedence over budget/network reasons.
    let (status, reason) = if secrets_hold {
        (TaskStatus::Paused, Some(SECRETS_TIER_B_HOLD))
    } else if !budget.allowed {
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
        &output_ref,
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
    if read_allow_network_config(&repo.kcs_dir().join("config.toml"))? == Some(true)
        || read_allow_network_config(&user_config_toml_path())? == Some(true)
    {
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

/// Whether Tier B (candidate-secret) files may be sent to online adapters for
/// this scope, i.e. `--send-secrets` was recorded at least once (N1c).
fn secrets_send_approved(repo: &Repository) -> bool {
    let Ok(expected_scope_id) = scope_id(repo.kcs_dir()) else {
        return false;
    };
    let Ok(text) = fs::read_to_string(repo.kcs_dir().join(SECRETS_APPROVAL_FILE)) else {
        return false;
    };
    text.lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .any(|value| {
            value.get("scope_id").and_then(Value::as_str) == Some(expected_scope_id.as_str())
                && value.get("approval_method").and_then(Value::as_str) == Some("send_secrets")
        })
}

/// Record the explicit `--send-secrets` approval (N1c). Idempotent: appended as
/// an audit trail; `secrets_send_approved` accepts only a row bound to this scope.
fn write_secrets_approval(repo: &Repository, preview: &ScanPreview) -> Result<()> {
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
    store
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
        .map_err(pipeline_to_kcs)
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
        // N1b: record Tier A (excluded from ingest) AND Tier B (ingested locally
        // but held from online send) so `kcs status` surfaces both. Tier B carries
        // its live disposition — "hold" until `--send-secrets`, then "send_approved".
        let (reason, approval_method) = match candidate.quarantine_reason.as_deref() {
            Some("secrets_tier_a_excluded") if candidate.ignored => {
                ("secrets_tier_a", "quarantine")
            }
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
        if existing.contains(&candidate.input_path) {
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
    let mut tool_ids = vec![online_markdownize_profile().adapter_id];
    if let Some(adapter_id) = active_embedding_adapter_id()? {
        tool_ids.push(adapter_id);
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
    validate_json_schema(SchemaKind::Config, &json_value)
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

/// `$XDG_CACHE_HOME`, else `$HOME/.cache` (06 §1.1). The device cache root for
/// disposable, regenerable data such as the open/view read-only expansion of CAS
/// objects — deliberately separate from the durable `$XDG_DATA_HOME` (P9).
fn cache_home() -> PathBuf {
    if let Some(path) = std::env::var_os("XDG_CACHE_HOME") {
        return PathBuf::from(path);
    }
    if let Some(home) = std::env::var_os("HOME") {
        return PathBuf::from(home).join(".cache");
    }
    PathBuf::from(".")
}

fn cost_ledger_path() -> PathBuf {
    data_home().join("kcs/cost-ledger.jsonl")
}

/// Device-local HMAC key that signs search cursors (O1(b)). Stored at
/// `$XDG_DATA_HOME/kcs/cursor-key` (0600), generated from `/dev/urandom` on first
/// use. Signing binds a cursor to this device so a caller cannot forge or tamper
/// a token to jump scope or page — `query_hash` alone covers only public inputs.
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

/// 32 fresh random bytes from `/dev/urandom` (available on the supported
/// unix-like targets); the cursor key needs no CSPRNG crate.
fn random_key_32() -> Result<Vec<u8>> {
    use std::io::Read;
    let mut buf = vec![0u8; 32];
    fs::File::open("/dev/urandom")
        .and_then(|mut file| file.read_exact(&mut buf))
        .map_err(|err| KcsError::io(err.to_string(), "/dev/urandom".to_owned()))?;
    Ok(buf)
}

fn adapter_to_kcs(error: kcs_adapter::AdapterError) -> KcsError {
    KcsError::schema(error.to_string())
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
        println!("{text}");
    } else if let Some(status) = value.get("status").and_then(Value::as_str) {
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
    use kcs_adapter::catalog::deterministic_embedding_vector;

    use super::{command_captured_json_flag, Cli, Command};

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
    fn q2_open_cas_byte_object_rejects_corrupt_object() {
        use super::{cas_object_path, hash_bytes, open_cas_byte_object, ScopeTarget};
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        // The correct `sha256:` filename for the AUTHENTIC bytes...
        let hash = hash_bytes(b"authentic prepared object");
        let object_path = cas_object_path(&kcs_dir, "prepared", &hash);
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
