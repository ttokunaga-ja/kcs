use std::fs;
use std::path::Path;
use std::process::{Command as ProcessCommand, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use assert_cmd::Command as AssertCommand;
use kcs_core::cas::{canonical_json_bytes, fanout_path, hash_bytes};
use serde_json::Value;

/// A process-wide isolated XDG home so `init` / `index` never touch the developer's
/// real `~/.local/share/kcs/scope-registry.sqlite` (K3 — init/index now register
/// scopes). Tests that need to read the data home set `XDG_DATA_HOME` explicitly,
/// which overrides this default.
fn isolated_home() -> &'static std::path::Path {
    use std::sync::OnceLock;
    static HOME: OnceLock<tempfile::TempDir> = OnceLock::new();
    HOME.get_or_init(|| tempfile::tempdir().unwrap()).path()
}

fn kcs() -> AssertCommand {
    let mut command = AssertCommand::cargo_bin("kcs").unwrap();
    command
        .env("XDG_DATA_HOME", isolated_home().join("data"))
        .env("XDG_CONFIG_HOME", isolated_home().join("config"));
    command
}

#[test]
fn ct_cli_001_init_layout_and_idempotent_noop() {
    let temp = tempfile::tempdir().unwrap();

    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    let kcs_dir = temp.path().join(".kcs");
    assert!(kcs_dir.join("HEAD").is_file());
    assert!(kcs_dir.join("refs/heads").is_dir());
    assert!(kcs_dir.join("objects/raw").is_dir());
    assert!(kcs_dir.join("objects/trees").is_dir());
    assert!(kcs_dir.join("objects/commits").is_dir());
    assert!(kcs_dir.join("config.toml").is_file());
    assert!(kcs_dir.join("scope.json").is_file());

    let scope: Value =
        serde_json::from_str(&fs::read_to_string(kcs_dir.join("scope.json")).unwrap()).unwrap();
    let scope_id = scope["scope_id"].as_str().unwrap().to_owned();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    let scope2: Value =
        serde_json::from_str(&fs::read_to_string(kcs_dir.join("scope.json")).unwrap()).unwrap();
    assert_eq!(scope2["scope_id"], scope_id);
}

#[test]
fn ct_cli_003_state_001_002_status_reports_new_modified_unchanged() {
    let temp = tempfile::tempdir().unwrap();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    fs::write(temp.path().join("a.pdf"), b"one").unwrap();

    let out = kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let json: Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(json["files"][0]["status"], "new");
    assert!(json["files"][0]["path"].as_str().unwrap().starts_with('/'));

    kcs()
        .args(["snapshot", "create", "-m", "first"])
        .env("KCS_FIXED_NOW", "2026-04-29T12:00:00Z")
        .current_dir(temp.path())
        .assert()
        .success();
    let out = kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let json: Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(json["files"][0]["status"], "unchanged");

    fs::write(temp.path().join("a.pdf"), b"two").unwrap();
    let out = kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let json: Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(json["files"][0]["status"], "modified");
}

#[test]
fn ct_cli_snapshot_commit_alias_log_inspect_tag_diff() {
    let left = tempfile::tempdir().unwrap();
    let right = tempfile::tempdir().unwrap();
    for dir in [left.path(), right.path()] {
        kcs().arg("init").current_dir(dir).assert().success();
        fs::write(dir.join("a.pdf"), b"one").unwrap();
    }

    let snap = snapshot_json(
        left.path(),
        &["snapshot", "create", "-m", "same"],
        "2026-04-29T12:00:00Z",
    );
    let alias = snapshot_json(
        right.path(),
        &["commit", "-m", "same"],
        "2026-04-29T12:00:00Z",
    );
    assert_eq!(snap["commit_hash"], alias["commit_hash"]);

    fs::write(left.path().join("a.pdf"), b"two").unwrap();
    fs::write(left.path().join("b.pdf"), b"new").unwrap();
    let second = snapshot_json(
        left.path(),
        &["snapshot", "-m", "second"],
        "2026-04-29T12:00:01Z",
    );

    let log_out = kcs()
        .args(["log", "--json"])
        .current_dir(left.path())
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let log: Value = serde_json::from_slice(&log_out).unwrap();
    assert_eq!(log["commits"][0]["commit_hash"], second["commit_hash"]);
    assert_eq!(log["commits"][1]["commit_hash"], snap["commit_hash"]);

    let inspect_out = kcs()
        .args(["inspect", second["commit_hash"].as_str().unwrap(), "--json"])
        .current_dir(left.path())
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let inspected: Value = serde_json::from_slice(&inspect_out).unwrap();
    assert_eq!(inspected["object_type"], "commit");
    assert_eq!(inspected["parents"][0], snap["commit_hash"]);

    kcs()
        .args(["tag", "v1", second["commit_hash"].as_str().unwrap()])
        .current_dir(left.path())
        .assert()
        .success();
    assert_eq!(
        fs::read_to_string(left.path().join(".kcs/refs/tags/v1")).unwrap(),
        second["commit_hash"].as_str().unwrap()
    );

    let diff_out = kcs()
        .args([
            "diff",
            snap["commit_hash"].as_str().unwrap(),
            second["commit_hash"].as_str().unwrap(),
            "--json",
        ])
        .current_dir(left.path())
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let diff: Value = serde_json::from_slice(&diff_out).unwrap();
    let changes = diff["changes"].as_array().unwrap();
    assert_eq!(changes.len(), 2);
    assert!(changes
        .iter()
        .any(|c| c["change"] == "modified" && c["path"].as_str().unwrap().ends_with("/a.pdf")));
    assert!(changes
        .iter()
        .any(|c| c["change"] == "added" && c["path"].as_str().unwrap().ends_with("/b.pdf")));
}

#[test]
fn ct_lock_001_concurrent_snapshots_fail_fast() {
    let temp = tempfile::tempdir().unwrap();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    fs::write(temp.path().join("a.pdf"), b"one").unwrap();

    let bin = assert_cmd::cargo::cargo_bin("kcs");
    let first = ProcessCommand::new(&bin)
        .args(["snapshot", "-m", "first", "--json"])
        .env("KCS_FIXED_NOW", "2026-04-29T12:00:00Z")
        .env("KCS_TEST_HOLD_LOCK_MS", "800")
        .current_dir(temp.path())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();

    wait_for_path(temp.path().join(".kcs/.lock").as_path());

    let second = ProcessCommand::new(&bin)
        .args(["snapshot", "-m", "second", "--json"])
        .env("KCS_FIXED_NOW", "2026-04-29T12:00:01Z")
        .current_dir(temp.path())
        .output()
        .unwrap();
    let first = first.wait_with_output().unwrap();

    assert!(first.status.success());
    assert_eq!(second.status.code(), Some(3));
    let error: Value = serde_json::from_slice(&second.stderr).unwrap();
    assert_eq!(error["error_code"], "KCS-E-STORE-LOCKED-001");
}

#[test]
fn ct_lock_003_read_commands_do_not_acquire_lock() {
    let temp = tempfile::tempdir().unwrap();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    fs::write(temp.path().join("a.pdf"), b"one").unwrap();
    let first = snapshot_json(
        temp.path(),
        &["snapshot", "-m", "first"],
        "2026-04-29T12:00:00Z",
    );
    fs::write(temp.path().join("a.pdf"), b"two").unwrap();
    let second = snapshot_json(
        temp.path(),
        &["snapshot", "-m", "second"],
        "2026-04-29T12:00:01Z",
    );

    write_active_lock(temp.path());

    kcs()
        .args(["log", "--json"])
        .current_dir(temp.path())
        .assert()
        .success();
    kcs()
        .args(["inspect", second["commit_hash"].as_str().unwrap(), "--json"])
        .current_dir(temp.path())
        .assert()
        .success();
    kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .success();
    kcs()
        .args([
            "diff",
            first["commit_hash"].as_str().unwrap(),
            second["commit_hash"].as_str().unwrap(),
            "--json",
        ])
        .current_dir(temp.path())
        .assert()
        .success();
}

#[test]
fn ct_cli_011_012_013_lock_and_schema_errors_are_structured() {
    let temp = tempfile::tempdir().unwrap();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    let scope_json = fs::read_to_string(temp.path().join(".kcs/scope.json")).unwrap();
    kcs()
        .args(["status", "--bogus"])
        .current_dir(temp.path())
        .assert()
        .code(2);

    fs::write(temp.path().join(".kcs/config.toml"), "not = [").unwrap();

    let out = kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .code(2)
        .get_output()
        .stderr
        .clone();
    let err: Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");

    fs::write(
        temp.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n",
    )
    .unwrap();
    fs::write(
        temp.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[chunking]\nstrategy = \"heading\"\nmax_chars = 0\n",
    )
    .unwrap();
    kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .code(2);
    fs::write(
        temp.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[budget]\nmonthly_usd_cap = -1\n",
    )
    .unwrap();
    kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .code(2);
    fs::write(
        temp.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n",
    )
    .unwrap();

    fs::write(temp.path().join(".kcs/scope.json"), "{}").unwrap();
    kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .code(2);
    fs::write(temp.path().join(".kcs/scope.json"), scope_json).unwrap();

    fs::write(
        temp.path().join(".kcs/manifest.json"),
        "{\"files\":\"bad\"}",
    )
    .unwrap();
    kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .code(2);
    fs::write(temp.path().join(".kcs/manifest.json"), "{\"files\":[]}").unwrap();

    let missing = "sha256:0000000000000000000000000000000000000000000000000000000000000000";
    let out = kcs()
        .args(["inspect", missing, "--json"])
        .current_dir(temp.path())
        .assert()
        .code(4)
        .get_output()
        .stderr
        .clone();
    let err: Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(err["error_code"], "KCS-E-STORE-NOT-FOUND-001");

    let bad_commit = write_invalid_commit_type(temp.path());
    fs::write(temp.path().join(".kcs/HEAD"), &bad_commit).unwrap();
    fs::write(temp.path().join(".kcs/refs/heads/main"), bad_commit).unwrap();
    let out = kcs()
        .args(["log", "--json"])
        .current_dir(temp.path())
        .assert()
        .code(2)
        .get_output()
        .stderr
        .clone();
    let err: Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
    fs::write(temp.path().join(".kcs/HEAD"), "").unwrap();
    fs::write(temp.path().join(".kcs/refs/heads/main"), "").unwrap();

    fs::write(temp.path().join(".kcs/.lock"), "{}").unwrap();
    fs::write(temp.path().join("a.pdf"), b"a").unwrap();
    let out = kcs()
        .args(["snapshot", "-m", "locked", "--json"])
        .current_dir(temp.path())
        .assert()
        .code(3)
        .get_output()
        .stderr
        .clone();
    let err: Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(err["error_code"], "KCS-E-STORE-LOCKED-001");

    fs::write(
        temp.path().join(".kcs/.lock"),
        r#"{"pid":99999999,"token":"stale","created_at":"2026-04-29T12:00:00Z"}"#,
    )
    .unwrap();
    kcs()
        .args(["snapshot", "-m", "stale recovered", "--json"])
        .env("KCS_FIXED_NOW", "2026-04-29T12:00:02Z")
        .current_dir(temp.path())
        .assert()
        .success();
    assert!(!temp.path().join(".kcs/.lock").exists());
}

#[test]
fn ct_obs_001_002_events_and_errors_jsonl() {
    let temp = tempfile::tempdir().unwrap();
    let data = tempfile::tempdir().unwrap();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    fs::write(temp.path().join("a.pdf"), b"a").unwrap();

    kcs()
        .args(["snapshot", "-m", "event"])
        .env("KCS_FIXED_NOW", "2026-04-29T12:00:00Z")
        .env("XDG_DATA_HOME", data.path())
        .current_dir(temp.path())
        .assert()
        .success();
    let events = fs::read_to_string(data.path().join("kcs/logs/events.jsonl")).unwrap();
    let event: Value = serde_json::from_str(events.lines().last().unwrap()).unwrap();
    assert_eq!(event["code"], "KCS-I-COMMIT-CREATED-001");
    assert_eq!(event["component"], "kcs-cli");

    let missing = "sha256:0000000000000000000000000000000000000000000000000000000000000000";
    kcs()
        .args(["inspect", missing])
        .env("XDG_DATA_HOME", data.path())
        .current_dir(temp.path())
        .assert()
        .code(4);
    let errors = fs::read_to_string(data.path().join("kcs/logs/errors.jsonl")).unwrap();
    let error: Value = serde_json::from_str(errors.lines().last().unwrap()).unwrap();
    assert_eq!(error["code"], "KCS-E-STORE-NOT-FOUND-001");
}

#[cfg(unix)]
#[test]
fn s5_symlink_is_skipped_with_warning() {
    let temp = tempfile::tempdir().unwrap();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    fs::write(temp.path().join("a.pdf"), b"one").unwrap();
    std::os::unix::fs::symlink(temp.path().join("a.pdf"), temp.path().join("link.pdf")).unwrap();

    let output = kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .success()
        .get_output()
        .clone();
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("warning: skipping non-regular file"),
        "stderr was: {stderr}"
    );
    let json: Value = serde_json::from_slice(&output.stdout).unwrap();
    let files = json["files"].as_array().unwrap();
    assert_eq!(files.len(), 1);
    assert_eq!(files[0]["relative_path"], "a.pdf");

    // Snapshot succeeds and the symlink is absent from the stored tree.
    let snap = snapshot_json(
        temp.path(),
        &["snapshot", "-m", "s"],
        "2026-04-29T12:00:00Z",
    );
    let tree_hash = snap["tree_hash"].as_str().unwrap();
    let inspect = kcs()
        .args(["inspect", tree_hash, "--json"])
        .current_dir(temp.path())
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let tree: Value = serde_json::from_slice(&inspect).unwrap();
    let entries = tree["entries"].as_array().unwrap();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0]["path"], "a.pdf");
}

// Linux-only: macOS/APFS rejects non-UTF-8 file names at the filesystem level,
// so the byte sequence cannot even be created there.
#[cfg(target_os = "linux")]
#[test]
fn s6_non_utf8_filename_is_skipped_with_warning() {
    use std::ffi::OsStr;
    use std::os::unix::ffi::OsStrExt;

    let temp = tempfile::tempdir().unwrap();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    fs::write(temp.path().join("a.pdf"), b"ok").unwrap();
    let bad = temp.path().join(OsStr::from_bytes(b"bad\xff.pdf"));
    fs::write(&bad, b"x").unwrap();

    let output = kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .success()
        .get_output()
        .clone();
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("warning: skipping non-UTF-8 file name"),
        "stderr was: {stderr}"
    );
    let json: Value = serde_json::from_slice(&output.stdout).unwrap();
    let files = json["files"].as_array().unwrap();
    assert_eq!(files.len(), 1);
    assert_eq!(files[0]["relative_path"], "a.pdf");
}

#[test]
fn n3_config_ignore_array_validates() {
    let temp = tempfile::tempdir().unwrap();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();

    // A valid top-level `ignore` array of strings is accepted (03 §11).
    fs::write(
        temp.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\nignore = [\"*.tmp\", \"secret.pdf\"]\n",
    )
    .unwrap();
    kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .success();

    // A non-array `ignore` is a schema violation (exit 2).
    fs::write(
        temp.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\nignore = \"not-an-array\"\n",
    )
    .unwrap();
    kcs()
        .args(["status", "--json"])
        .current_dir(temp.path())
        .assert()
        .code(2);
}

fn snapshot_json(dir: &std::path::Path, args: &[&str], now: &str) -> Value {
    let out = kcs()
        .args(args)
        .arg("--json")
        .env("KCS_FIXED_NOW", now)
        .current_dir(dir)
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&out).unwrap()
}

fn wait_for_path(path: &Path) {
    let deadline = Instant::now() + Duration::from_secs(5);
    while Instant::now() < deadline {
        if path.exists() {
            return;
        }
        thread::sleep(Duration::from_millis(10));
    }
    panic!("timed out waiting for {}", path.display());
}

fn write_active_lock(root: &Path) {
    fs::write(
        root.join(".kcs/.lock"),
        serde_json::json!({
            "pid": std::process::id(),
            "token": "read-lock-test",
            "created_at": "2026-04-29T12:00:00Z"
        })
        .to_string(),
    )
    .unwrap();
}

fn write_invalid_commit_type(root: &Path) -> String {
    let commit = serde_json::json!({
        "commit_type": "snapshot",
        "created_at": "2026-04-29T12:00:00Z",
        "message": "bad commit type",
        "object_type": "commit",
        "parents": [],
        "stats": { "files_added": 0, "files_deleted": 0, "files_modified": 0 },
        "tool_lock_hash": "sha256:8a32a740871b1dd9db1bda186dce07e8e6c60d2cd316f21683ea2bd857c16ffb",
        "tree": "sha256:849dc4fa25bc1a7b09b74dba30c0bb85224fb8f659c3b2b177b7189b0327a967"
    });
    let bytes = canonical_json_bytes(&commit).unwrap();
    let hash = hash_bytes(&bytes);
    let path = fanout_path(root.join(".kcs/objects/commits"), &hash).unwrap();
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, bytes).unwrap();
    hash
}
