use std::fs;

use assert_cmd::Command;
use kcs_core::cas::{fanout_path, ObjectKind, ObjectStore};
use serde_json::{json, Value};
use tempfile::TempDir;

const CHILD_ENV_DENYLIST: &[&str] = &[
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "KCS_FIXED_NOW",
    "KCS_TEST_GEMINI_EMBED",
    "KCS_TEST_MISTRAL_OCR",
    "KCS_TEST_MARKDOWNIZE_ADAPTER",
];

fn kcs(dir: &TempDir, args: &[&str]) -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    for name in CHILD_ENV_DENYLIST {
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
    let output = kcs(dir, args)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_failure(dir: &TempDir, args: &[&str], code: i32) -> Value {
    let output = kcs(dir, args)
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stderr
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn init(dir: &TempDir) {
    json_success(dir, &["init"]);
}

fn snapshot(dir: &TempDir, message: &str) -> String {
    json_success(dir, &["snapshot", "-m", message])["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned()
}

fn inspect(dir: &TempDir, hash: &str) -> Value {
    json_success(dir, &["inspect", hash])
}

fn path_text(path: &std::path::Path) -> String {
    path.to_str().unwrap().to_owned()
}

#[test]
fn ct4_restore_commit_restores_verified_files_and_empty_commit() {
    let dir = TempDir::new().unwrap();
    init(&dir);
    fs::write(dir.path().join("a.md"), b"alpha").unwrap();
    fs::write(dir.path().join("b.md"), b"beta").unwrap();
    let commit = snapshot(&dir, "two files");
    let destination = dir.path().join("recovered");
    let output = json_success(
        &dir,
        &["restore", &commit, "--to", &path_text(&destination)],
    );
    assert_eq!(output["status"], "restored");
    assert_eq!(output["source_kind"], "commit");
    assert_eq!(output["source_commit"], commit);
    assert_eq!(output["restored_count"], 2);
    assert_eq!(output["overwritten_count"], 0);
    assert_eq!(fs::read(destination.join("a.md")).unwrap(), b"alpha");
    assert_eq!(fs::read(destination.join("b.md")).unwrap(), b"beta");

    fs::remove_file(dir.path().join("a.md")).unwrap();
    fs::remove_file(dir.path().join("b.md")).unwrap();
    let empty = snapshot(&dir, "empty");
    let empty_destination = dir.path().join("empty-recovered");
    let output = json_success(
        &dir,
        &["restore", &empty, "--to", &path_text(&empty_destination)],
    );
    assert_eq!(output["restored_count"], 0);
    assert!(empty_destination.is_dir());
}

#[test]
fn ct4_restore_deleted_path_uses_newest_first_parent_binding() {
    let dir = TempDir::new().unwrap();
    init(&dir);
    fs::write(dir.path().join("deleted.md"), b"historical").unwrap();
    let old_commit = snapshot(&dir, "old");
    fs::remove_file(dir.path().join("deleted.md")).unwrap();
    snapshot(&dir, "deleted");

    let destination = dir.path().join("path-restore");
    let output = json_success(
        &dir,
        &["restore", "deleted.md", "--to", &path_text(&destination)],
    );
    assert_eq!(output["source_kind"], "path");
    assert_eq!(output["source_commit"], old_commit);
    assert_eq!(output["restored_count"], 1);
    assert_eq!(
        fs::read(destination.join("deleted.md")).unwrap(),
        b"historical"
    );
}

#[test]
fn ct4_restore_preflight_no_clobber_and_force_confirmation() {
    let dir = TempDir::new().unwrap();
    init(&dir);
    fs::write(dir.path().join("a.md"), b"alpha").unwrap();
    fs::write(dir.path().join("b.md"), b"beta").unwrap();
    let commit = snapshot(&dir, "source");
    let destination = dir.path().join("conflict");
    fs::create_dir(&destination).unwrap();
    fs::write(destination.join("b.md"), b"existing").unwrap();

    let error = json_failure(
        &dir,
        &["restore", &commit, "--to", &path_text(&destination)],
        1,
    );
    assert_eq!(error["error_code"], "KCS-E-COMMIT-RESTORE-CONFLICT-001");
    assert!(!destination.join("a.md").exists());
    assert_eq!(fs::read(destination.join("b.md")).unwrap(), b"existing");

    let error = json_failure(
        &dir,
        &[
            "restore",
            &commit,
            "--to",
            &path_text(&destination),
            "--force",
        ],
        9,
    );
    assert_eq!(error["error_code"], "KCS-E-CONFIRM-REJECTED-001");

    let output = json_success(
        &dir,
        &[
            "restore",
            &commit,
            "--to",
            &path_text(&destination),
            "--force",
            "--yes",
        ],
    );
    assert_eq!(output["restored_count"], 2);
    assert_eq!(output["overwritten_count"], 1);
    assert_eq!(fs::read(destination.join("a.md")).unwrap(), b"alpha");
    assert_eq!(fs::read(destination.join("b.md")).unwrap(), b"beta");
}

#[test]
fn ct4_restore_source_preflight_is_atomic_and_raw_shorthand_is_invalid() {
    let dir = TempDir::new().unwrap();
    init(&dir);
    fs::write(dir.path().join("a.md"), b"alpha").unwrap();
    fs::write(dir.path().join("b.md"), b"beta").unwrap();
    let commit = snapshot(&dir, "source");
    let tree_hash = inspect(&dir, &commit)["tree"].as_str().unwrap().to_owned();
    let tree = inspect(&dir, &tree_hash);
    let raw_hash = tree["entries"][0]["raw_hash"].as_str().unwrap().to_owned();

    let raw_error = json_failure(
        &dir,
        &[
            "restore",
            &raw_hash,
            "--to",
            &path_text(&dir.path().join("raw")),
        ],
        2,
    );
    assert_eq!(raw_error["error_code"], "KCS-E-CONFIG-USAGE-001");

    let store = ObjectStore::new(dir.path().join(".kcs"));
    fs::remove_file(store.object_path(ObjectKind::Raw, &raw_hash).unwrap()).unwrap();
    let destination = dir.path().join("missing-raw");
    let error = json_failure(
        &dir,
        &["restore", &commit, "--to", &path_text(&destination)],
        4,
    );
    assert_eq!(error["error_code"], "KCS-E-PURGE-NOT-FOUND-001");
    assert!(!destination.exists());
}

#[test]
fn ct4_restore_source_authorization_is_serialized_by_purge_publication_lock() {
    let dir = TempDir::new().unwrap();
    init(&dir);
    fs::write(dir.path().join("doc.md"), b"authorized bytes").unwrap();
    let commit = snapshot(&dir, "source");

    // Model a concurrent live purge publication window. Restore intentionally
    // does not take `.kcs/.lock`, but must fail before staging/publishing while
    // this narrower coordination lock is owned by another live process.
    fs::write(
        dir.path().join(".kcs/purge-publication.lock"),
        serde_json::to_vec(&json!({
            "pid": std::process::id(),
            "token": "ct4-restore-held-publication-lock",
            "created_at": "2026-07-13T00:00:00Z",
        }))
        .unwrap(),
    )
    .unwrap();
    let destination = dir.path().join("must-not-publish");
    let error = json_failure(
        &dir,
        &["restore", &commit, "--to", &path_text(&destination)],
        3,
    );
    assert_eq!(error["error_code"], "KCS-E-STORE-LOCKED-001");
    assert!(destination.is_dir());
    assert_eq!(fs::read_dir(&destination).unwrap().count(), 0);
}

#[test]
fn ct4_restore_rejects_shallow_tombstoned_and_store_destinations() {
    let tombstoned = TempDir::new().unwrap();
    init(&tombstoned);
    fs::write(tombstoned.path().join("doc.md"), b"secret").unwrap();
    let commit = snapshot(&tombstoned, "source");
    let tree_hash = inspect(&tombstoned, &commit)["tree"]
        .as_str()
        .unwrap()
        .to_owned();
    let tree = inspect(&tombstoned, &tree_hash);
    let raw_hash = tree["entries"][0]["raw_hash"].as_str().unwrap().to_owned();
    let tombstone = fanout_path(tombstoned.path().join(".kcs/tombstones"), &raw_hash).unwrap();
    fs::create_dir_all(tombstone.parent().unwrap()).unwrap();
    fs::write(
        tombstone,
        serde_json::to_vec(&json!({
            "raw_hash": raw_hash,
            "purged_at": "2026-07-13T00:00:00Z",
            "purged_reason": "legal",
            "purged_in_commit": commit,
        }))
        .unwrap(),
    )
    .unwrap();
    let error = json_failure(
        &tombstoned,
        &[
            "restore",
            &commit,
            "--to",
            &path_text(&tombstoned.path().join("dead")),
        ],
        4,
    );
    assert_eq!(error["error_code"], "KCS-E-PURGE-TOMBSTONED-001");

    for forbidden in [
        tombstoned.path().to_path_buf(),
        tombstoned.path().join(".kcs/restore"),
    ] {
        let error = json_failure(
            &tombstoned,
            &["restore", &commit, "--to", &path_text(&forbidden)],
            1,
        );
        assert_eq!(error["error_code"], "KCS-E-COMMIT-RESTORE-UNSAFE-001");
    }

    let shallow = TempDir::new().unwrap();
    init(&shallow);
    fs::write(shallow.path().join("doc.md"), b"content").unwrap();
    let commit = snapshot(&shallow, "source");
    let tree_hash = inspect(&shallow, &commit)["tree"]
        .as_str()
        .unwrap()
        .to_owned();
    let store = ObjectStore::new(shallow.path().join(".kcs"));
    fs::remove_file(store.object_path(ObjectKind::Tree, &tree_hash).unwrap()).unwrap();
    let error = json_failure(
        &shallow,
        &[
            "restore",
            &commit,
            "--to",
            &path_text(&shallow.path().join("shallow")),
        ],
        1,
    );
    assert_eq!(error["error_code"], "KCS-E-COMMIT-SHALLOW-001");
}

#[test]
fn ct4_restore_tag_wins_over_same_named_historical_path() {
    let dir = TempDir::new().unwrap();
    init(&dir);
    fs::write(dir.path().join("tagged.md"), b"tag target").unwrap();
    let tagged_commit = snapshot(&dir, "tag target");
    json_success(&dir, &["tag", "same", &tagged_commit]);
    fs::write(dir.path().join("same"), b"path target").unwrap();
    snapshot(&dir, "path exists");

    let destination = dir.path().join("tag-precedence");
    let output = json_success(&dir, &["restore", "same", "--to", &path_text(&destination)]);
    assert_eq!(output["source_kind"], "commit");
    assert_eq!(output["source_commit"], tagged_commit);
    assert_eq!(
        fs::read(destination.join("tagged.md")).unwrap(),
        b"tag target"
    );
    assert!(!destination.join("same").exists());
}

#[test]
fn ct4_restore_evidence_uses_exact_attested_commit_path_and_raw() {
    let dir = TempDir::new().unwrap();
    init(&dir);
    fs::write(dir.path().join("evidence.md"), b"attested bytes").unwrap();
    json_success(&dir, &["index", "--offline", "--approve"]);

    let commit = fs::read_to_string(dir.path().join(".kcs/HEAD"))
        .unwrap()
        .trim()
        .to_owned();
    let tree_hash = inspect(&dir, &commit)["tree"].as_str().unwrap().to_owned();
    let tree = inspect(&dir, &tree_hash);
    let entry = tree["entries"]
        .as_array()
        .unwrap()
        .iter()
        .find(|entry| entry["path"] == "evidence.md")
        .unwrap();
    let raw_hash = entry["raw_hash"].as_str().unwrap();
    let profile_hash = entry["normalize"]["tool_profile_hash"].as_str().unwrap();
    let chunk_hash = fs::read_to_string(dir.path().join(".kcs/index/chunks.jsonl"))
        .unwrap()
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .find(|chunk| chunk["raw_hash"] == raw_hash)
        .and_then(|chunk| chunk["chunk_id"].as_str().map(str::to_owned))
        .unwrap();
    let scope: Value =
        serde_json::from_slice(&fs::read(dir.path().join(".kcs/scope.json")).unwrap()).unwrap();
    let scope_id = scope["scope_id"].as_str().unwrap().to_owned();
    let uri = format!("kcs://{scope_id}/{commit}/{raw_hash}/{profile_hash}/{chunk_hash}");
    let pointer = json!({
        "schema_version": 1,
        "commit": commit,
        "tree": tree_hash,
        "raw_hash": raw_hash,
        "tool_profile_hash": profile_hash,
        "chunk_hash": chunk_hash,
        "path_at_commit": "evidence.md",
        "scope_id": scope_id,
        "scope_path": dir.path().join(".kcs"),
    })
    .to_string();
    fs::remove_file(dir.path().join("evidence.md")).unwrap();
    let destination = dir.path().join("evidence-restore");
    let output = json_success(
        &dir,
        &["restore", &pointer, "--to", &path_text(&destination)],
    );
    assert_eq!(output["source_kind"], "evidence");
    assert_eq!(output["restored_count"], 1);
    assert_eq!(
        fs::read(destination.join("evidence.md")).unwrap(),
        b"attested bytes"
    );

    let stdin_destination = dir.path().join("evidence-stdin");
    let stdin_output = kcs(
        &dir,
        &["restore", "-", "--to", &path_text(&stdin_destination)],
    )
    .arg("--json")
    .write_stdin(pointer.clone())
    .assert()
    .success()
    .get_output()
    .stdout
    .clone();
    let stdin_output: Value = serde_json::from_slice(&stdin_output).unwrap();
    assert_eq!(stdin_output["source_kind"], "evidence");
    assert_eq!(
        fs::read(stdin_destination.join("evidence.md")).unwrap(),
        b"attested bytes"
    );

    let uri_destination = dir.path().join("evidence-uri");
    let uri_output = json_success(
        &dir,
        &["restore", &uri, "--to", &path_text(&uri_destination)],
    );
    assert_eq!(uri_output["source_kind"], "evidence");
    assert_eq!(
        fs::read(uri_destination.join("evidence.md")).unwrap(),
        b"attested bytes"
    );
}

#[test]
fn ct4_restore_cli_requires_to_and_rejects_extras_and_yes_without_force() {
    let dir = TempDir::new().unwrap();
    init(&dir);
    fs::write(dir.path().join("doc.md"), b"content").unwrap();
    let commit = snapshot(&dir, "source");
    let yes_only = dir.path().join("yes-only");

    for args in [
        vec!["restore", commit.as_str()],
        vec![
            "restore",
            commit.as_str(),
            "--to",
            dir.path().to_str().unwrap(),
            "extra",
        ],
        vec![
            "restore",
            commit.as_str(),
            "--to",
            yes_only.to_str().unwrap(),
            "--yes",
        ],
    ] {
        let error = json_failure(&dir, &args, 2);
        assert_eq!(error["error_code"], "KCS-E-CONFIG-USAGE-001");
    }
}

#[cfg(unix)]
#[test]
fn ct4_restore_refuses_symlink_and_hardlink_destination_leaves() {
    use std::os::unix::fs::symlink;

    let dir = TempDir::new().unwrap();
    init(&dir);
    fs::write(dir.path().join("doc.md"), b"restored").unwrap();
    let commit = snapshot(&dir, "source");
    let outside = dir.path().join("outside.txt");
    fs::write(&outside, b"outside").unwrap();

    let symlink_destination = dir.path().join("symlink-dest");
    fs::create_dir(&symlink_destination).unwrap();
    symlink(&outside, symlink_destination.join("doc.md")).unwrap();
    let error = json_failure(
        &dir,
        &[
            "restore",
            &commit,
            "--to",
            &path_text(&symlink_destination),
            "--force",
            "--yes",
        ],
        1,
    );
    assert_eq!(error["error_code"], "KCS-E-COMMIT-RESTORE-UNSAFE-001");
    assert_eq!(fs::read(&outside).unwrap(), b"outside");

    let hardlink_destination = dir.path().join("hardlink-dest");
    fs::create_dir(&hardlink_destination).unwrap();
    fs::hard_link(&outside, hardlink_destination.join("doc.md")).unwrap();
    let error = json_failure(
        &dir,
        &[
            "restore",
            &commit,
            "--to",
            &path_text(&hardlink_destination),
            "--force",
            "--yes",
        ],
        1,
    );
    assert_eq!(error["error_code"], "KCS-E-COMMIT-RESTORE-UNSAFE-001");
    assert_eq!(fs::read(&outside).unwrap(), b"outside");
}
