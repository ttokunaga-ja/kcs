//! The 2026-08-02 ruling: the Tier A secrets hold applies to an `offline_api`
//! markdownize adapter too, and the consent it records must name the adapter
//! that will actually see the file.
//!
//! 07 §3 (2) exempts `offline_api` from `approvals[]` and `allow_network`
//! because those gate *transmission off the machine*. The secrets hold asks a
//! different question — may this credential be handed to this tool — and a
//! local model server is a separate process that can log what it is given.
//!
//! The failure this pins down is quiet rather than loud. Before the split, the
//! `--send-secrets` consent was keyed off the *online* markdownize id
//! unconditionally, so approving a local pipeline wrote an audit row naming
//! Mistral: a durable record asserting the user consented to send a credential
//! to a cloud API that never received it.

use std::fs;

use assert_cmd::Command;
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

fn run(dir: &TempDir, args: &[&str], env: &[(&str, &str)]) -> (bool, String) {
    let mut full = vec!["--json"];
    full.extend_from_slice(args);
    let output = kio(dir, &full, env).output().unwrap();
    (
        output.status.success(),
        String::from_utf8_lossy(&output.stdout).into_owned(),
    )
}

/// Every `send_secrets` consent row this run wrote, as tool ids.
fn secrets_consent_tool_ids(dir: &TempDir) -> Vec<String> {
    let path = dir
        .path()
        .join(".test-data")
        .join("kio")
        .join("consents.jsonl");
    if !path.exists() {
        return Vec::new();
    }
    fs::read_to_string(&path)
        .unwrap()
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter(|row| {
            row.get("operation")
                .and_then(Value::as_str)
                .is_some_and(|operation| operation.contains("secret"))
        })
        .filter_map(|row| {
            row.get("tool_id")
                .and_then(Value::as_str)
                .map(str::to_owned)
        })
        .collect()
}

fn fixture() -> TempDir {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("scan.pdf"), "%PDF-1.4\nscanned page\n").unwrap();
    dir
}

/// With a local OCR pipeline declared, `--send-secrets` must record consent
/// against the local adapter — not against the cloud OCR that is not running.
#[test]
fn the_secrets_consent_names_the_adapter_that_will_see_the_file() {
    let dir = fixture();
    let local = [("KIO_TEST_LOCAL_OCR", "mock")];
    let (ok, out) = run(&dir, &["init"], &local);
    assert!(ok, "{out}");
    let (ok, out) = run(
        &dir,
        &["index", "--approve", "--offline", "--send-secrets"],
        &local,
    );
    assert!(ok, "{out}");

    let recorded = secrets_consent_tool_ids(&dir);
    assert!(
        !recorded.is_empty(),
        "--send-secrets must record a consent row: {recorded:?}"
    );
    assert!(
        recorded.iter().all(|id| id != "mistral_ocr_markdownize"),
        "a local pipeline must not have its secrets consent recorded against \
         the cloud OCR adapter: {recorded:?}"
    );
    assert!(
        recorded.iter().any(|id| id == "paddleocr_vl_local"),
        "the local pipeline must be named in the consent it needs: {recorded:?}"
    );
}

/// Without a local pipeline, nothing changes: the consent still names the
/// online OCR adapter, exactly as it did before the split.
#[test]
fn the_online_route_records_its_consent_unchanged() {
    let dir = fixture();
    let (ok, out) = run(&dir, &["init"], &[]);
    assert!(ok, "{out}");
    let (ok, out) = run(
        &dir,
        &["index", "--approve", "--offline", "--send-secrets"],
        &[],
    );
    assert!(ok, "{out}");

    let recorded = secrets_consent_tool_ids(&dir);
    assert!(
        recorded.iter().any(|id| id == "mistral_ocr_markdownize"),
        "the pre-existing online consent must be untouched: {recorded:?}"
    );
    assert!(
        recorded.iter().all(|id| id != "paddleocr_vl_local"),
        "an undeclared local pipeline must not appear in any consent: {recorded:?}"
    );
}
