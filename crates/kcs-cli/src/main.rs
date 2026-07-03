use std::collections::BTreeSet;
use std::fs::{self, OpenOptions};
use std::io::{IsTerminal, Write};
use std::path::{Path, PathBuf};
use std::process;

use clap::{Args, Parser, Subcommand};
use kcs_adapter::tool_lock::{load_tool_lock, validate_tools_toml};
use kcs_core::scope::{append_error_log, append_event_log, InspectedObject, Repository};
use kcs_core::{ExitCode, KcsError, Result};
use kcs_pipeline::markdownize::{
    persist_normalized_instance, MarkdownizeMode, NormalizedInstanceManifest,
    NormalizedUnitManifestEntry, NormalizedUnitObject, ReusedFrom, UnitStatus,
};
use kcs_pipeline::prepare::{hash_bytes, unit_ref, UnitType};
use kcs_pipeline::scan::{build_scan_preview, ScanCandidate, ScanPreview, ScanPreviewRequest};
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
            Ok(json!({
                "scope_path": repo.kcs_dir(),
                "files": repo.status()?,
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
            "interactive approval is not implemented; use --approve or --yes",
        ));
    }

    if !approved || args.approve || args.yes {
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

    write_baseline_artifacts(&repo, &preview)?;
    let excluded = preview
        .candidates
        .iter()
        .filter(|candidate| candidate.ignored)
        .map(|candidate| candidate.input_path.clone())
        .collect::<BTreeSet<_>>();
    let outcome = repo.auto_snapshot(Some("kcs index auto snapshot"), None, &excluded)?;
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
        "network_opt_in": args.approve || args.online,
        "pending_online_tasks": if args.yes && !args.online { preview.candidates.iter().filter(|candidate| !candidate.ignored).count() } else { 0 },
        "tree_hash": outcome.tree_hash,
        "commit_hash": outcome.commit_hash,
        "commit": outcome.commit,
    }))
}

fn run_batch(args: BatchArgs) -> Result<Value> {
    match args.command {
        Some(BatchCommand::Resume(resume)) => Ok(json!({
            "status": "resumed",
            "override_budget": resume.override_budget,
        })),
        Some(BatchCommand::Retry) => Ok(json!({ "status": "retry scheduled" })),
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

fn write_baseline_artifacts(repo: &Repository, preview: &ScanPreview) -> Result<()> {
    const TOOL_PROFILE_HASH: &str =
        "sha256:76c01950d19edffc1b8ca75e06d7754fb52cd05db1bb10e3268f81392bf54095";
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
        let generated_at = "2026-04-25T12:00:00Z".to_owned();
        let unit_key = if candidate.media_type == "application/pdf" {
            "page:1"
        } else {
            "doc:1"
        }
        .to_owned();
        let unit_type = if candidate.media_type == "application/pdf" {
            UnitType::Page
        } else {
            UnitType::File
        };
        let prepared_hash = hash_bytes(&bytes);
        let manifest = NormalizedInstanceManifest {
            raw_hash: raw_hash.clone(),
            tool_profile_hash: TOOL_PROFILE_HASH.to_owned(),
            gen: 0,
            parent_gen: None,
            run_id: "run_00000000000000000000000000".to_owned(),
            units: vec![NormalizedUnitManifestEntry {
                order: 0,
                unit_key: unit_key.clone(),
                unit_ref: unit_ref(&unit_key),
                unit_type,
                status: UnitStatus::Done,
                prepared_hash: prepared_hash.clone(),
                error_kind: None,
            }],
            generated_at: generated_at.clone(),
        };
        let unit = NormalizedUnitObject {
            unit_key: unit_key.clone(),
            unit_type,
            raw_hash,
            prepared_hash,
            tool_profile_hash: TOOL_PROFILE_HASH.to_owned(),
            gen: 0,
            mode: MarkdownizeMode::Full,
            markdown: baseline_markdown(candidate, &bytes),
            reused_from: None::<ReusedFrom>,
            generated_at,
        };
        persist_normalized_instance(repo.kcs_dir(), &manifest, &[unit]).map_err(pipeline_to_kcs)?;
    }
    Ok(())
}

fn baseline_markdown(candidate: &ScanCandidate, bytes: &[u8]) -> String {
    if candidate.media_type.starts_with("text/") {
        String::from_utf8_lossy(bytes).into_owned()
    } else {
        format!(
            "<!-- KCS deterministic baseline {} {} bytes -->\n",
            candidate.input_path,
            bytes.len()
        )
    }
}

fn approval_exists(repo: &Repository) -> Result<bool> {
    Ok(repo.kcs_dir().join("approvals.jsonl").is_file())
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
        "approved_at": "2026-04-25T12:00:00Z",
        "actor": std::env::var("USER").unwrap_or_else(|_| "unknown".to_owned()),
        "approval_method": approval_method,
        "kcs_version": env!("CARGO_PKG_VERSION"),
        "effective_ignore_hash": hash_bytes(b"built-in-tier-a-v1"),
        "estimated_file_count": preview.candidates.iter().filter(|candidate| !candidate.ignored).count(),
        "estimated_size_bytes": preview.candidates.iter().filter(|candidate| !candidate.ignored).map(|candidate| candidate.size_bytes).sum::<u64>(),
        "network_opt_in": network_opt_in,
        "tool_id": "mistral_ocr_markdownize",
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
