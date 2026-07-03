use std::fs;

use assert_cmd::Command;
use serde_json::Value;

fn kcs() -> Command {
    Command::cargo_bin("kcs").unwrap()
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
fn ct_cli_003_state_001_002_status_reports_new_modified_up_to_date() {
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
    assert_eq!(json["files"][0]["status"], "up_to_date");

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
fn ct_cli_011_012_013_lock_and_schema_errors_are_structured() {
    let temp = tempfile::tempdir().unwrap();
    kcs()
        .arg("init")
        .current_dir(temp.path())
        .assert()
        .success();
    let scope_json = fs::read_to_string(temp.path().join(".kcs/scope.json")).unwrap();
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
