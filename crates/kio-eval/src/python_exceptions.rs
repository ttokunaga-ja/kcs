//! Closed inventory of the Python-native adapter boundary.
//!
//! Python is not a general-purpose evaluator runtime in this repository.  The
//! checked-in ledger must name every tracked `.py` file and justify it with a
//! concrete Python-native package/runtime dependency.  Push and pull-request
//! lanes are deliberately forbidden.

use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Component, Path, PathBuf},
};

use serde::Deserialize;
use thiserror::Error;

pub const LEDGER_PATH: &str = "eval/python-exceptions.toml";
const LEDGER_VERSION: u32 = 1;
const MAX_LEDGER_BYTES: usize = 256 * 1024;
const MAX_ENTRIES: usize = 64;
const MAX_FIELD_BYTES: usize = 4 * 1024;

#[derive(Debug, Error)]
pub enum PythonExceptionError {
    #[error("cannot read Python exception ledger: {0}")]
    Read(#[from] std::io::Error),
    #[error("Python exception ledger exceeds {MAX_LEDGER_BYTES} bytes")]
    TooLarge,
    #[error("invalid Python exception ledger TOML: {0}")]
    Toml(#[from] toml::de::Error),
    #[error("invalid Python exception ledger: {0}")]
    Invalid(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PythonExceptionLedger {
    pub version: u32,
    #[serde(rename = "exception")]
    pub exceptions: Vec<PythonException>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PythonException {
    pub path: String,
    pub reason: String,
    pub python_runtime: String,
    pub packages: Vec<String>,
    pub input_schema: String,
    pub output_schema: String,
    pub lane: String,
    pub network: bool,
    pub gpu: bool,
    pub credentials: bool,
    pub reevaluate_when: String,
    pub owner: String,
    pub status: String,
}

/// Parse and validate the repository ledger against the caller's exact set of
/// tracked Python paths.  Tests obtain that set from Git; the validator itself
/// remains deterministic and does not spawn a process.
pub fn validate_repository_ledger(
    repository: &Path,
    tracked_python: &BTreeSet<PathBuf>,
) -> Result<PythonExceptionLedger, PythonExceptionError> {
    let bytes = fs::read(repository.join(LEDGER_PATH))?;
    validate_ledger_bytes(repository, &bytes, tracked_python)
}

pub fn validate_ledger_bytes(
    repository: &Path,
    bytes: &[u8],
    tracked_python: &BTreeSet<PathBuf>,
) -> Result<PythonExceptionLedger, PythonExceptionError> {
    if bytes.len() > MAX_LEDGER_BYTES {
        return Err(PythonExceptionError::TooLarge);
    }
    let ledger: PythonExceptionLedger = toml::from_slice(bytes)?;
    if ledger.version != LEDGER_VERSION {
        return invalid("unsupported ledger version");
    }
    if ledger.exceptions.is_empty() || ledger.exceptions.len() > MAX_ENTRIES {
        return invalid("exception count is empty or exceeds its bound");
    }
    let mut entries = BTreeMap::new();
    for entry in &ledger.exceptions {
        validate_entry(repository, entry)?;
        let path = PathBuf::from(&entry.path);
        if entries.insert(path, entry).is_some() {
            return invalid("duplicate exception path");
        }
    }
    let declared = entries.into_keys().collect::<BTreeSet<_>>();
    if declared != *tracked_python {
        let missing = tracked_python
            .difference(&declared)
            .map(|path| path.display().to_string())
            .collect::<Vec<_>>();
        let extra = declared
            .difference(tracked_python)
            .map(|path| path.display().to_string())
            .collect::<Vec<_>>();
        return invalid(format!(
            "tracked Python inventory mismatch (missing={missing:?}, extra={extra:?})"
        ));
    }
    Ok(ledger)
}

fn validate_entry(repository: &Path, entry: &PythonException) -> Result<(), PythonExceptionError> {
    let path = Path::new(&entry.path);
    if path.is_absolute()
        || path.extension().and_then(|value| value.to_str()) != Some("py")
        || path.components().any(|component| {
            !matches!(component, Component::Normal(_))
                || matches!(component, Component::ParentDir | Component::CurDir)
        })
    {
        return invalid("exception path must be a normalized relative .py path");
    }
    let metadata = fs::symlink_metadata(repository.join(path)).map_err(|_| {
        PythonExceptionError::Invalid(format!("missing exception file: {}", entry.path))
    })?;
    if !metadata.file_type().is_file() {
        return invalid(format!(
            "exception path is not a regular file: {}",
            entry.path
        ));
    }
    for (label, value) in [
        ("path", entry.path.as_str()),
        ("reason", entry.reason.as_str()),
        ("python_runtime", entry.python_runtime.as_str()),
        ("input_schema", entry.input_schema.as_str()),
        ("output_schema", entry.output_schema.as_str()),
        ("lane", entry.lane.as_str()),
        ("reevaluate_when", entry.reevaluate_when.as_str()),
        ("owner", entry.owner.as_str()),
        ("status", entry.status.as_str()),
    ] {
        if value.trim().is_empty() || value.len() > MAX_FIELD_BYTES {
            return invalid(format!("{label} is empty or exceeds its byte bound"));
        }
    }
    if entry.packages.is_empty()
        || entry.packages.len() > 16
        || entry
            .packages
            .iter()
            .any(|package| package.trim().is_empty() || package.len() > 128)
    {
        return invalid("packages must name at least one bounded Python-native dependency");
    }
    let standard_library = [
        "argparse",
        "base64",
        "hashlib",
        "http",
        "json",
        "os",
        "pathlib",
        "shutil",
        "subprocess",
        "sys",
        "tomllib",
        "urllib",
    ];
    if entry
        .packages
        .iter()
        .all(|package| standard_library.contains(&package.to_ascii_lowercase().as_str()))
    {
        return invalid("standard-library-only Python is not an exception");
    }
    let reason = entry.reason.to_ascii_lowercase();
    for rejected in [
        "existing code",
        "already written",
        "easier",
        "subprocess",
        "json processing",
        "http api",
        "filesystem",
    ] {
        if reason.contains(rejected) {
            return invalid(format!(
                "reason uses a forbidden generic justification: {rejected}"
            ));
        }
    }
    if !versioned_schema(&entry.input_schema) || !versioned_schema(&entry.output_schema) {
        return invalid("input_schema and output_schema must be versioned identifiers");
    }
    let lane_tokens = entry
        .lane
        .to_ascii_lowercase()
        .split(|character: char| !character.is_ascii_alphanumeric())
        .filter(|token| !token.is_empty())
        .map(str::to_owned)
        .collect::<BTreeSet<_>>();
    if lane_tokens
        .iter()
        .any(|token| matches!(token.as_str(), "push" | "pr" | "ci" | "pullrequest"))
    {
        return invalid("Python exception lane must not be push/PR CI");
    }
    if entry.status != "active-manual" {
        return invalid("Python exception status must be active-manual");
    }
    Ok(())
}

fn versioned_schema(value: &str) -> bool {
    let Some((prefix, version_text)) = value.rsplit_once("/v") else {
        return false;
    };
    !prefix.is_empty()
        && version_text
            .parse::<u32>()
            .is_ok_and(|version| version > 0 && version.to_string() == version_text)
}

fn invalid<T>(message: impl Into<String>) -> Result<T, PythonExceptionError> {
    Err(PythonExceptionError::Invalid(message.into()))
}

#[cfg(test)]
mod tests {
    use std::process::Command;

    use super::*;

    fn repository() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap()
    }

    fn tracked_python(repository: &Path) -> BTreeSet<PathBuf> {
        let output = Command::new("git")
            .args(["ls-files", "-z", "--", "*.py"])
            .current_dir(repository)
            .output()
            .unwrap();
        assert!(output.status.success());
        assert!(output.stdout.len() <= 1024 * 1024);
        output
            .stdout
            .split(|byte| *byte == 0)
            .filter(|path| !path.is_empty())
            .map(|path| PathBuf::from(std::str::from_utf8(path).unwrap()))
            .collect()
    }

    #[test]
    fn tracked_python_exactly_matches_the_closed_ledger() {
        let repository = repository();
        validate_repository_ledger(&repository, &tracked_python(&repository)).unwrap();
    }

    #[test]
    fn malformed_ledgers_fail_closed() {
        let repository = repository();
        let one_path = "eval/u7/reference_adapter.py";
        let valid = format!(
            r#"version = 1
[[exception]]
path = "{one_path}"
reason = "PyTorch and Transformers provide the official Python-native reference model runtime"
python_runtime = "CPython 3.12"
packages = ["torch", "transformers", "pillow"]
input_schema = "kio.u7.reference-embedding-request/v1"
output_schema = "kio.u7.reference-embedding-response/v1"
lane = "manual-u7-reference"
network = false
gpu = false
credentials = false
reevaluate_when = "A supported Rust model runtime replaces live reference inference"
owner = "eval"
status = "active-manual"
"#
        );
        let only = BTreeSet::from([PathBuf::from(one_path)]);
        validate_ledger_bytes(&repository, valid.as_bytes(), &only).unwrap();
        let duplicate = format!(
            "{valid}\n[[exception]]{}",
            valid.split_once("[[exception]]").unwrap().1
        );

        for invalid_bytes in [
            valid.replace("packages = [\"torch\", \"transformers\", \"pillow\"]", "packages = [\"json\"]"),
            valid.replace("packages = [\"torch\", \"transformers\", \"pillow\"]\n", ""),
            valid.replace("lane = \"manual-u7-reference\"", "lane = \"push-ci\""),
            valid.replace("input_schema = \"kio.u7.reference-embedding-request/v1\"\n", ""),
            valid.replace("reevaluate_when = \"A supported Rust model runtime replaces live reference inference\"\n", ""),
            duplicate,
        ] {
            assert!(validate_ledger_bytes(&repository, invalid_bytes.as_bytes(), &only).is_err());
        }
        let missing = BTreeSet::from([PathBuf::from(one_path), PathBuf::from("missing.py")]);
        assert!(validate_ledger_bytes(&repository, valid.as_bytes(), &missing).is_err());
        let nonexistent = valid.replace(one_path, "eval/u7/not-present.py");
        assert!(
            validate_ledger_bytes(
                &repository,
                nonexistent.as_bytes(),
                &BTreeSet::from([PathBuf::from("eval/u7/not-present.py")])
            )
            .is_err()
        );
    }
}
