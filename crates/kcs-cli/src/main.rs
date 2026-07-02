use std::path::PathBuf;
use std::process;

use clap::{Args, Parser, Subcommand};
use kcs_core::ExitCode;

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

fn main() {
    let cli = Cli::parse();
    let exit_code = run(cli);
    process::exit(exit_code.code());
}

fn run(cli: Cli) -> ExitCode {
    let _json = cli.json;

    match cli.command {
        Command::Init(args) => {
            let _path = args.path;
            not_implemented("init")
        }
        Command::Status => not_implemented("status"),
        Command::Snapshot(args) => {
            let (_action, _message) = (args.action, args.message);
            not_implemented("snapshot")
        }
        Command::Log(args) => {
            let (_at, _since) = (args.at, args.since);
            not_implemented("log")
        }
        Command::Diff(args) => {
            let (_a, _b) = (args.a, args.b);
            not_implemented("diff")
        }
        Command::Inspect(args) => {
            let _hash = args.hash;
            not_implemented("inspect")
        }
        Command::Tag(args) => {
            let (_name, _commit) = (args.name, args.commit);
            not_implemented("tag")
        }
    }
}

fn not_implemented(command: &str) -> ExitCode {
    eprintln!("{command}: not implemented");

    // docs/06-cli-spec.md §7 reserves exit code 1 for generic failure.
    // Scaffolded commands parse successfully, but their business logic is absent.
    ExitCode::Failure
}

#[cfg(test)]
mod tests {
    use clap::Parser;

    use super::{Cli, Command};

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
}
