//! Stage 3 (S3-E): the `offline_api` markdownize route, end to end.
//!
//! A scanned PDF never reaches the deterministic baseline route — with no text
//! layer it produces no prepared units and is enqueued for enrichment instead —
//! so this is the only route where a local OCR pipeline is any use. These
//! assert that it runs there, and that selecting it drags in none of what an
//! *online* enrichment brings: a network opt-in, a ledger row, or a second
//! command.
//!
//! Every test that claims the local backend ran checks the *content*, not the
//! recorded profile. A wiring that swaps `tool_lock.json`'s markdown profile
//! while another adapter produces the text passes every profile assertion and
//! is the worse of the two failures — the archive would assert the local
//! pipeline's identity over bytes it never touched.

use std::fs;

use assert_cmd::Command;
use rusqlite::Connection;
use serde_json::Value;
use tempfile::TempDir;

const CHILD_ENV_DENYLIST: &[&str] = &[
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "KIO_FIXED_NOW",
    "KIO_TEST_GEMINI_EMBED",
    "KIO_TEST_LOCAL_EMBED",
    "KIO_TEST_LOCAL_OCR",
    "KIO_TEST_MISTRAL_OCR",
    "KIO_TEST_MARKDOWNIZE_ADAPTER",
];

/// The mock backend's own page text. Used as the witness that the local
/// pipeline produced a document's body rather than merely being recorded.
const MOCK_PAGE_TEXT: &str = "Kio local OCR mock page.";

fn kio(dir: &TempDir, args: &[&str], env: &[(&str, &str)]) -> Command {
    let mut command = Command::cargo_bin("kio").unwrap();
    for name in CHILD_ENV_DENYLIST {
        command.env_remove(name);
    }
    command
        .current_dir(dir.path())
        .env("XDG_CONFIG_HOME", dir.path().join(".test-config"))
        .env("XDG_DATA_HOME", dir.path().join(".test-data"))
        .env("XDG_CACHE_HOME", dir.path().join(".test-cache"))
        .args(args);
    for (name, value) in env {
        command.env(name, value);
    }
    command
}

fn json_success(dir: &TempDir, args: &[&str], env: &[(&str, &str)]) -> Value {
    let mut full = vec!["--json"];
    full.extend_from_slice(args);
    let output = kio(dir, &full, env).output().unwrap();
    assert!(
        output.status.success(),
        "kio {args:?} failed: {}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).unwrap_or_else(|error| {
        panic!(
            "kio {args:?} stdout is not JSON ({error}): {}",
            String::from_utf8_lossy(&output.stdout)
        )
    })
}

fn tasks(dir: &TempDir) -> Vec<Value> {
    let path = dir.path().join(".kio").join("tasks.jsonl");
    if !path.exists() {
        return Vec::new();
    }
    fs::read_to_string(&path)
        .unwrap()
        .lines()
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect()
}

fn chunk_texts(dir: &TempDir) -> Vec<String> {
    let path = dir.path().join(".kio").join("index").join("chunks.jsonl");
    if !path.exists() {
        return Vec::new();
    }
    fs::read_to_string(&path)
        .unwrap()
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter_map(|row| row.get("text").and_then(Value::as_str).map(str::to_owned))
        .collect()
}

fn ledger_charge_rows(dir: &TempDir) -> i64 {
    let mut total = 0;
    for candidate in [
        dir.path().join(".test-data").join("kio").join("ledger.db"),
        dir.path().join(".kio").join("ledger.db"),
    ] {
        if !candidate.exists() {
            continue;
        }
        let connection = Connection::open(&candidate).unwrap();
        let tables: Vec<String> = connection
            .prepare("SELECT name FROM sqlite_master WHERE type='table'")
            .unwrap()
            .query_map([], |row| row.get(0))
            .unwrap()
            .map(Result::unwrap)
            .collect();
        for table in tables
            .iter()
            .filter(|name| name.contains("charge") || name.contains("batch_request"))
        {
            total += connection
                .query_row::<i64, _, _>(&format!("SELECT COUNT(*) FROM \"{table}\""), [], |row| {
                    row.get(0)
                })
                .unwrap();
        }
    }
    total
}

fn scanned_pdf_fixture() -> TempDir {
    let dir = tempfile::tempdir().unwrap();
    // No text layer, so the deterministic Prepare mints no units and the file
    // is enqueued for enrichment. That is the whole point: this is the shape a
    // local OCR pipeline exists to handle.
    fs::write(dir.path().join("scan.pdf"), "%PDF-1.4\nscanned page\n").unwrap();
    dir
}

/// One `kio index` is the whole flow.
///
/// The online lane splits enqueue from send because sending needs approval and
/// money. A local pipeline needs neither, so requiring a second command would
/// be ceremony guarding nothing — and the task is still created first, so a
/// crash mid-OCR leaves work the next index picks up.
#[test]
fn s3e_one_index_enriches_a_scanned_pdf_through_the_local_pipeline() {
    let dir = scanned_pdf_fixture();
    let local = [("KIO_TEST_LOCAL_OCR", "mock")];
    json_success(&dir, &["init"], &local);
    json_success(&dir, &["index", "--approve", "--offline"], &local);

    let texts = chunk_texts(&dir);
    assert!(
        texts.iter().any(|text| text.contains(MOCK_PAGE_TEXT)),
        "the local pipeline must have produced the PDF's body: {texts:?}"
    );

    let tasks = tasks(&dir);
    let scan = tasks
        .iter()
        .find(|task| {
            task.get("input_path")
                .and_then(Value::as_str)
                .is_some_and(|path| path.ends_with("scan.pdf"))
        })
        .unwrap_or_else(|| panic!("no task for scan.pdf: {tasks:?}"));
    assert_eq!(scan["status"], "done", "{scan}");
    assert_eq!(scan["fallback_reason"], "local_adapter_done", "{scan}");
}

/// D9 plus the no-billing rule, checked from outside the adapter.
///
/// `--offline` is passed deliberately: 07 §3 states it does not stop an
/// `offline_api` adapter, because its definition bans new *sends* and a
/// loopback pipeline performs none. If that exemption regressed, this test
/// would find an unenriched PDF.
#[test]
fn s3e_the_local_route_needs_no_network_opt_in_and_opens_no_ledger_row() {
    let dir = scanned_pdf_fixture();
    let local = [("KIO_TEST_LOCAL_OCR", "mock")];
    json_success(&dir, &["init"], &local);
    json_success(&dir, &["index", "--approve", "--offline"], &local);

    assert!(
        chunk_texts(&dir)
            .iter()
            .any(|text| text.contains(MOCK_PAGE_TEXT)),
        "--offline must not stop an offline_api adapter (07 §3)"
    );
    assert_eq!(
        ledger_charge_rows(&dir),
        0,
        "a local pipeline has no invoice, so nothing may be reserved or settled"
    );
}

/// The task must never be visible to the online lane.
///
/// `output_ref`'s prefix is what every online gate matches on — the network
/// opt-in, the ledger reservation, the batch sender, the auth revive. A local
/// task keyed `online:` would be swept into all of them.
#[test]
fn s3e_the_local_task_is_not_addressed_to_the_online_lane() {
    let dir = scanned_pdf_fixture();
    let local = [("KIO_TEST_LOCAL_OCR", "mock")];
    json_success(&dir, &["init"], &local);
    json_success(&dir, &["index", "--approve", "--offline"], &local);

    for task in tasks(&dir) {
        let output_ref = task["output_ref"].as_str().unwrap_or_default();
        assert!(
            !output_ref.starts_with("online:"),
            "a local enrichment must not be addressed to the online lane: {task}"
        );
    }
}

/// Without the backend, nothing about the online route changes.
#[test]
fn s3e_an_undeclared_local_backend_leaves_the_online_route_alone() {
    let dir = scanned_pdf_fixture();
    json_success(&dir, &["init"], &[]);
    json_success(&dir, &["index", "--approve", "--offline"], &[]);

    let tasks = tasks(&dir);
    let scan = tasks
        .iter()
        .find(|task| {
            task.get("input_path")
                .and_then(Value::as_str)
                .is_some_and(|path| path.ends_with("scan.pdf"))
        })
        .unwrap_or_else(|| panic!("no task for scan.pdf: {tasks:?}"));
    assert_eq!(
        scan["output_ref"], "online:mistral_ocr_markdownize",
        "{scan}"
    );
    assert!(
        !chunk_texts(&dir)
            .iter()
            .any(|text| text.contains(MOCK_PAGE_TEXT)),
        "no local backend is declared, so its text must not appear"
    );
}

/// A second index over unchanged content must not re-run the pipeline.
///
/// The task reaching `done` is what stops it. Were it left Pending, every
/// subsequent `kio index` would re-OCR the whole document — free in money, but
/// minutes of GPU each time.
#[test]
fn s3e_a_second_index_does_not_re_run_the_finished_pipeline() {
    let dir = scanned_pdf_fixture();
    let local = [("KIO_TEST_LOCAL_OCR", "mock")];
    json_success(&dir, &["init"], &local);
    json_success(&dir, &["index", "--approve", "--offline"], &local);
    let after_first = tasks(&dir).len();

    json_success(&dir, &["index", "--approve", "--offline"], &local);
    let scan_tasks: Vec<_> = tasks(&dir)
        .into_iter()
        .filter(|task| {
            task.get("input_path")
                .and_then(Value::as_str)
                .is_some_and(|path| path.ends_with("scan.pdf"))
        })
        .collect();
    assert!(
        scan_tasks.iter().all(|task| task["status"] != "pending"),
        "a finished document must not be re-enqueued: {scan_tasks:?}"
    );
    assert!(
        tasks(&dir).len() >= after_first,
        "the task journal is append-only"
    );
}
