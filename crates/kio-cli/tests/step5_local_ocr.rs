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
    "KIO_TEST_LOCAL_OCR_BODY",
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

/// A standalone image, which reaches the OCR route for a different reason.
///
/// A scanned PDF gets there by having no text layer; an image gets there by
/// being a recognized binary Prepare will not parse at all. Both end with no
/// prepared units, so both depend on the adapter discovering them -- and until
/// this fixture existed every test on this route was a PDF, so the discovery
/// code only ever had to be right about pages.
fn scanned_image_fixture() -> TempDir {
    let dir = tempfile::tempdir().unwrap();
    // A real PNG signature and IHDR. The mock backend ignores the bytes, but
    // the scanner's media-type routing should not be the thing under test.
    let png: [u8; 33] = [
        0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, b'I', b'H', b'D',
        b'R', 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x02, 0x00, 0x00, 0x00, 0x90,
        0x77, 0x53, 0xde,
    ];
    fs::write(dir.path().join("scan.png"), png).unwrap();
    dir
}

/// The same one-command flow, for an image instead of a PDF.
#[test]
fn s3e_one_index_enriches_a_standalone_image_through_the_local_pipeline() {
    let dir = scanned_image_fixture();
    let local = [("KIO_TEST_LOCAL_OCR", "mock")];
    json_success(&dir, &["init"], &local);
    json_success(&dir, &["index", "--approve", "--offline"], &local);

    let tasks = tasks(&dir);
    let scan = tasks
        .iter()
        .find(|task| {
            task.get("input_path")
                .and_then(Value::as_str)
                .is_some_and(|path| path.ends_with("scan.png"))
        })
        .unwrap_or_else(|| panic!("no task for scan.png: {tasks:?}"));
    assert_eq!(scan["status"], "done", "{scan}");
    assert_eq!(scan["fallback_reason"], "local_adapter_done", "{scan}");

    let texts = chunk_texts(&dir);
    assert!(
        texts.iter().any(|text| text.contains(MOCK_PAGE_TEXT)),
        "the local pipeline must have produced the image's body: {texts:?}"
    );
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

/// The figure the local pipeline extracted must be reachable from the search
/// result that cites it (05 §1.7).
///
/// This is the assertion that was missing when Stage 3 first met a real server.
/// PaddleOCR-VL writes figures as HTML `<img src="…">` and never `![](…)`, and
/// `kio-search`'s `extract_related_images` — which also decides which images get
/// embedded, what the scope projection counts, and what purge treats as an
/// orphan — reads only the CommonMark form. Every check that stopped at "the
/// normalized Markdown contains a `kio://` URI" passed anyway, because the URI
/// was there; it was simply written in a spelling nothing downstream could read.
/// So this asserts the field the contract actually promises, and then opens what
/// it names.
#[test]
fn s3e_the_local_pipelines_figure_is_reachable_from_the_chunk_that_cites_it() {
    let dir = scanned_pdf_fixture();
    let local = [("KIO_TEST_LOCAL_OCR", "mock")];
    json_success(&dir, &["init"], &local);
    json_success(&dir, &["index", "--approve", "--offline"], &local);

    let search = json_success(&dir, &["search", "mock", "--mode", "text"], &local);
    let hit = search["results"]
        .as_array()
        .unwrap()
        .iter()
        .find(|result| result["result_type"] == "chunk")
        .unwrap_or_else(|| panic!("no chunk hit for the mock page: {search}"));
    let images = hit["related_images"]
        .as_array()
        .unwrap_or_else(|| panic!("the cited figure must be enumerated: {hit}"));
    assert_eq!(images.len(), 1, "{hit}");
    let uri = images[0]["image_uri"].as_str().unwrap();
    assert!(uri.contains("/object/image/sha256:"), "{uri}");

    let opened = json_success(&dir, &["open", uri], &local);
    assert_eq!(opened["status"], "opened", "{opened}");
    assert_eq!(opened["object_type"], "image", "{opened}");
}

/// A unit that fails 07 §5's acceptance check must not reach the archive.
///
/// The check has always detected raw HTML; what it did not do was stop anything.
/// Its single production caller used the result only to decide whether to take
/// the Done shortcut, and the count-based status returns Done for "1 unit
/// produced, 0 failed" regardless — so the local route wrote raw `<div>` into
/// normalized units for a release with nothing saying so. 07 §9 then freezes
/// whatever landed.
///
/// The offline route now refuses instead. It can afford to: nothing was billed
/// and re-running is free, which is not true of the online routes and is why
/// they are deliberately left as they were.
#[test]
fn s3e_a_unit_that_fails_the_v1_acceptance_check_is_refused_not_frozen() {
    let dir = scanned_pdf_fixture();
    let local = [
        ("KIO_TEST_LOCAL_OCR", "mock"),
        // An HTML table: real enough that upstream may well send it, and
        // deliberately outside what the adapter rewrites.
        ("KIO_TEST_LOCAL_OCR_BODY", "nonconforming"),
    ];
    json_success(&dir, &["init"], &local);
    json_success(&dir, &["index", "--approve", "--offline"], &local);

    let tasks = tasks(&dir);
    let scan = tasks
        .iter()
        .find(|task| {
            task.get("input_path")
                .and_then(Value::as_str)
                .is_some_and(|path| path.ends_with("scan.pdf"))
        })
        .unwrap_or_else(|| panic!("no task for scan.pdf: {tasks:?}"));
    assert_eq!(scan["status"], "failed", "{scan}");
    assert_eq!(scan["fallback_reason"], "contract_violation", "{scan}");

    // The refusal is only worth anything if nothing was persisted. A unit that
    // reached the index would be frozen there by 07 §9's first-instance-wins.
    assert!(
        !chunk_texts(&dir)
            .iter()
            .any(|text| text.contains(MOCK_PAGE_TEXT)),
        "a refused unit must not be indexed: {:?}",
        chunk_texts(&dir)
    );
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
