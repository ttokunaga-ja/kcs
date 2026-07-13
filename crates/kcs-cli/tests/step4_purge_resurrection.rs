use std::collections::{BTreeMap, BTreeSet};
use std::fs;

use assert_cmd::Command;
use kcs_core::cas::{hash_bytes, ObjectKind, ObjectStore};
use kcs_core::purge::PurgeState;
use kcs_core::scope::{PendingNormalizeRef, Repository};
use kcs_pipeline::task::{TaskStatus, TaskStore, TaskType};
use serde_json::Value;
use tempfile::TempDir;

const DENYLIST: &[&str] = &[
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "KCS_FIXED_NOW",
    "KCS_TEST_PURGE_FAIL_AFTER_PHASE",
    "KCS_TEST_MISTRAL_OCR",
];

fn kcs(dir: &TempDir, args: &[&str]) -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    for name in DENYLIST {
        command.env_remove(name);
    }
    command
        .current_dir(dir.path())
        .env("XDG_CONFIG_HOME", dir.path().join(".test-config"))
        .env("XDG_DATA_HOME", dir.path().join(".test-data"))
        .env("XDG_CACHE_HOME", dir.path().join(".test-cache"))
        .args(args);
    command
}

fn json_success(dir: &TempDir, args: &[&str]) -> Value {
    let stdout = kcs(dir, args)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&stdout).unwrap()
}

fn json_failure(dir: &TempDir, args: &[&str], code: i32) -> Value {
    let stderr = kcs(dir, args)
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stderr
        .clone();
    serde_json::from_slice(&stderr).unwrap()
}

fn current_raw(dir: &TempDir, path: &str) -> String {
    let repo = Repository::open(dir.path()).unwrap();
    let head = repo.head_commit_hash().unwrap().unwrap();
    let commit = repo.read_commit(&head).unwrap();
    repo.read_tree(&commit.tree)
        .unwrap()
        .entries
        .into_iter()
        .find(|entry| entry.path == path)
        .unwrap()
        .raw_hash
}

fn raw_exists(dir: &TempDir, raw_hash: &str) -> bool {
    ObjectStore::new(dir.path().join(".kcs"))
        .inspect_object(ObjectKind::Raw, raw_hash)
        .is_ok()
}

fn ingest_temps(dir: &TempDir) -> Vec<String> {
    fs::read_dir(dir.path().join(".kcs/objects/raw"))
        .unwrap()
        .filter_map(Result::ok)
        .filter_map(|entry| entry.file_name().into_string().ok())
        .filter(|name| name.starts_with(".ingest-"))
        .collect()
}

fn fake_pdf(text: &str) -> String {
    format!(
        "%PDF-1.4\n1 0 obj << /Type /Pages /Kids [2 0 R] /Count 1 >> endobj\n\
         2 0 obj << /Type /Page /Parent 1 0 R >> stream\n\
         BT ({text}) Tj ET\nendstream endobj\n%%EOF\n"
    )
}

#[test]
fn ct4_purge_default_tombstone_rejects_reingest_before_any_raw_publication() {
    let dir = tempfile::tempdir().unwrap();
    let blocked_bytes = b"# Blocked\n\ndefault tombstone identity\n";
    fs::write(dir.path().join("z-blocked.md"), blocked_bytes).unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--offline", "--approve"]);
    let blocked_hash = current_raw(&dir, "z-blocked.md");
    fs::remove_file(dir.path().join("z-blocked.md")).unwrap();
    json_success(
        &dir,
        &[
            "purge",
            "--raw-hash",
            &blocked_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
    );
    assert!(!raw_exists(&dir, &blocked_hash));
    let head = fs::read(dir.path().join(".kcs/HEAD")).unwrap();

    let allowed_bytes = b"# Allowed\n\nmust not publish before complete gate\n";
    let allowed_hash = hash_bytes(allowed_bytes);
    fs::write(dir.path().join("a-allowed.md"), allowed_bytes).unwrap();
    fs::write(dir.path().join("z-blocked.md"), blocked_bytes).unwrap();

    // Exercise the core boundary directly: every candidate is staged and gated
    // before the first raw publication, independent of directory iteration order.
    let repo = Repository::open(dir.path()).unwrap();
    let error = repo
        .auto_snapshot_with_bound_normalize(
            Some("must fail"),
            None,
            &BTreeSet::new(),
            &BTreeMap::new(),
            &BTreeSet::new(),
        )
        .unwrap_err();
    assert_eq!(error.error_code(), "KCS-E-PURGE-TOMBSTONED-001");
    assert!(!raw_exists(&dir, &allowed_hash));
    assert!(!raw_exists(&dir, &blocked_hash));
    assert!(ingest_temps(&dir).is_empty());
    assert_eq!(fs::read(dir.path().join(".kcs/HEAD")).unwrap(), head);

    let cli_error = json_failure(&dir, &["index", "--offline", "--approve"], 4);
    assert_eq!(cli_error["error_code"], "KCS-E-PURGE-TOMBSTONED-001");
    assert!(!raw_exists(&dir, &allowed_hash));
    assert!(ingest_temps(&dir).is_empty());
}

#[test]
fn ct4_purge_erase_receipt_is_ignored_then_retired_by_explicit_ingest() {
    let dir = tempfile::tempdir().unwrap();
    let bytes = b"# Reintroduced\n\nerase receipt permits explicit ingest\n";
    fs::write(dir.path().join("doc.md"), bytes).unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--offline", "--approve"]);
    let historical_head = fs::read_to_string(dir.path().join(".kcs/HEAD"))
        .unwrap()
        .trim()
        .to_owned();
    let raw_hash = current_raw(&dir, "doc.md");
    fs::remove_file(dir.path().join("doc.md")).unwrap();
    json_success(
        &dir,
        &[
            "purge",
            "--raw-hash",
            &raw_hash,
            "--reason",
            "misingest",
            "--erase-tombstone",
            "--yes",
        ],
    );
    let purge = PurgeState::new(dir.path().join(".kcs"));
    assert!(purge.read_erase_receipt(&raw_hash).unwrap().is_some());

    let historical = json_success(&dir, &["reindex", "--at", &historical_head]);
    assert_eq!(historical["blocked_raw_hashes"], 0);

    fs::write(dir.path().join("doc.md"), bytes).unwrap();
    json_success(&dir, &["index", "--offline", "--approve"]);
    assert!(raw_exists(&dir, &raw_hash));
    assert!(purge.read_erase_receipt(&raw_hash).unwrap().is_none());
    assert_eq!(current_raw(&dir, "doc.md"), raw_hash);
}

#[test]
fn ct4_purge_active_barrier_blocks_index_and_leaves_no_raw_or_temp() {
    let dir = tempfile::tempdir().unwrap();
    let bytes = fake_pdf("active purge blocks resurrection");
    fs::write(dir.path().join("doc.pdf"), &bytes).unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--approve"]);
    let raw_hash = current_raw(&dir, "doc.pdf");
    fs::remove_file(dir.path().join("doc.pdf")).unwrap();
    let stdout = kcs(
        &dir,
        &[
            "purge",
            "--raw-hash",
            &raw_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
    )
    .env("KCS_TEST_PURGE_FAIL_AFTER_PHASE", "barrier_published")
    .arg("--json")
    .assert()
    .code(3)
    .get_output()
    .stdout
    .clone();
    let partial: Value = serde_json::from_slice(&stdout).unwrap();
    assert_eq!(partial["error_code"], "KCS-E-PURGE-INCOMPLETE-001");

    let store = ObjectStore::new(dir.path().join(".kcs"));
    let raw_path = store.object_path(ObjectKind::Raw, &raw_hash).unwrap();
    fs::remove_file(raw_path).unwrap();
    fs::write(dir.path().join("doc.pdf"), &bytes).unwrap();
    let head = fs::read(dir.path().join(".kcs/HEAD")).unwrap();

    // The repository primitive independently refuses to rebind a normalized
    // result while the target identity is behind the active visibility barrier.
    let repo = Repository::open(dir.path()).unwrap();
    let head_hash = repo.head_commit_hash().unwrap().unwrap();
    let commit = repo.read_commit(&head_hash).unwrap();
    let entry = repo
        .read_tree(&commit.tree)
        .unwrap()
        .entries
        .into_iter()
        .find(|entry| entry.path == "doc.pdf")
        .unwrap();
    let mut promotion = BTreeMap::new();
    promotion.insert(
        entry.path,
        PendingNormalizeRef {
            expected_raw_hash: raw_hash.clone(),
            normalize: entry.normalize.unwrap(),
        },
    );
    let promotion_error = repo
        .promote_normalize_refs(Some("must remain blocked"), &promotion)
        .unwrap_err();
    assert_eq!(promotion_error.error_code(), "KCS-E-PURGE-INCOMPLETE-001");

    // The pending online task left by the pre-purge PDF index is retired before
    // charge/send; a batch pass cannot recreate normalized output behind barrier.
    let batch_stdout = kcs(&dir, &["batch", "resume"])
        .env("KCS_TEST_MISTRAL_OCR", "mock")
        .arg("--json")
        .assert()
        .code(4)
        .get_output()
        .stdout
        .clone();
    let batch: Value = serde_json::from_slice(&batch_stdout).unwrap();
    assert_eq!(batch["tasks_executed"], 0);
    assert!(TaskStore::new(repo.kcs_dir())
        .all()
        .unwrap()
        .iter()
        .filter(|task| task.input_hash == raw_hash && task.task_type == TaskType::Markdownize)
        .all(|task| !matches!(task.status, TaskStatus::Pending | TaskStatus::Running)));

    let error = json_failure(&dir, &["index", "--offline", "--approve"], 3);
    assert_eq!(error["error_code"], "KCS-E-PURGE-INCOMPLETE-001");
    assert!(!raw_exists(&dir, &raw_hash));
    assert!(ingest_temps(&dir).is_empty());
    assert_eq!(fs::read(dir.path().join(".kcs/HEAD")).unwrap(), head);
}
