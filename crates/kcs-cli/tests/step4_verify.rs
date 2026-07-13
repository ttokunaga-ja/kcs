use std::fs;

use assert_cmd::Command;
use kcs_core::cas::{ObjectKind, ObjectStore};
use kcs_core::dag::{CommitObject, CommitStats, CommitType};
use kcs_core::purge::{PurgeReason, PurgeState, TombstoneMode};
use serde_json::Value;
use tempfile::TempDir;

fn kcs(dir: &TempDir, args: &[&str]) -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    command
        .current_dir(dir.path())
        .env("XDG_CONFIG_HOME", dir.path().join(".test-config"))
        .env("XDG_DATA_HOME", dir.path().join(".test-data"))
        .env("XDG_CACHE_HOME", dir.path().join(".test-cache"))
        .env_remove("GEMINI_API_KEY")
        .env_remove("MISTRAL_API_KEY")
        .args(args);
    command
}

fn success(dir: &TempDir, args: &[&str]) -> Value {
    let output = kcs(dir, args)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn fixture() -> (TempDir, Value, String) {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("evidence.md"),
        "# Evidence\n\nTTL is 3600 seconds.\n",
    )
    .unwrap();
    success(&dir, &["init"]);
    success(&dir, &["index", "--offline", "--approve"]);
    let search = success(&dir, &["search", "3600", "--text"]);
    let pointer = search["results"][0]["evidence_pointer"].clone();
    let uri = search["results"][0]["evidence_uri"]
        .as_str()
        .unwrap()
        .to_owned();
    (dir, pointer, uri)
}

fn files_named(root: &std::path::Path, name: &str) -> Vec<std::path::PathBuf> {
    let mut found = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(directory) = stack.pop() {
        let Ok(entries) = fs::read_dir(directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
            } else if path.file_name().and_then(|leaf| leaf.to_str()) == Some(name) {
                found.push(path);
            }
        }
    }
    found
}

fn write_purged_commit(dir: &TempDir, timestamp: &str) -> String {
    let repo = kcs_core::scope::Repository::open(dir.path()).unwrap();
    let parent_hash = repo.head_commit_hash().unwrap().unwrap();
    let parent = repo.read_commit(&parent_hash).unwrap();
    let purged = CommitObject::new(
        parent.tree,
        vec![parent_hash],
        timestamp.to_owned(),
        "legal".to_owned(),
        parent.tool_lock_hash,
        CommitStats {
            files_added: 0,
            files_modified: 0,
            files_deleted: 0,
        },
        CommitType::Purged,
    )
    .unwrap();
    ObjectStore::new(dir.path().join(".kcs"))
        .write_json(ObjectKind::Commit, &serde_json::to_value(&purged).unwrap())
        .unwrap()
        .0
}

fn tag_commit(dir: &TempDir, name: &str, commit_hash: &str) {
    let tag = dir
        .path()
        .join(".kcs/refs/tags-v1")
        .join(kcs_core::portable::portable_tag_leaf(name));
    fs::write(tag, commit_hash).unwrap();
}

fn write_receipt(
    dir: &TempDir,
    raw_hash: &str,
    purged_hash: &str,
    timestamp: &str,
) -> std::path::PathBuf {
    let digest = raw_hash.trim_start_matches("sha256:");
    let receipt = dir
        .path()
        .join(".kcs/purge/erase-receipts")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(digest);
    fs::create_dir_all(receipt.parent().unwrap()).unwrap();
    fs::write(
        &receipt,
        serde_json::to_vec(&serde_json::json!({
            "schema_version": 1,
            "raw_hash": raw_hash,
            "purged_in_commit": purged_hash,
            "erased_at": timestamp,
        }))
        .unwrap(),
    )
    .unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&receipt, fs::Permissions::from_mode(0o600)).unwrap();
    }
    receipt
}

fn write_tombstone(
    dir: &TempDir,
    raw_hash: &str,
    purged_hash: &str,
    timestamp: &str,
) -> std::path::PathBuf {
    let digest = raw_hash.trim_start_matches("sha256:");
    let path = dir
        .path()
        .join(".kcs/tombstones")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(digest);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(
        &path,
        serde_json::to_vec(&serde_json::json!({
            "raw_hash": raw_hash,
            "purged_at": timestamp,
            "purged_reason": "legal",
            "purged_in_commit": purged_hash,
        }))
        .unwrap(),
    )
    .unwrap();
    path
}

#[test]
fn ct4_verify_alive_is_content_free_and_accepts_strict() {
    let (dir, pointer, _) = fixture();
    let pointer = serde_json::to_string(&pointer).unwrap();
    for args in [
        vec!["evidence", "verify", pointer.as_str()],
        vec!["evidence", "verify", pointer.as_str(), "--strict"],
    ] {
        let output = success(&dir, &args);
        assert_eq!(output["status"], "alive");
        assert!(output.get("text").is_none());
        assert!(output["details"].get("path_at_commit").is_none());
    }
}

#[test]
fn ct4_verify_rejects_non_pointer_and_ambiguous_cli_forms() {
    let (dir, mut pointer, _) = fixture();
    let valid = serde_json::to_string(&pointer).unwrap();
    for args in [
        vec!["evidence", "verify", valid.as_str(), "extra"],
        vec!["evidence", "verify", "--batch", valid.as_str()],
        vec![
            "evidence",
            "verify",
            pointer["chunk_hash"].as_str().unwrap(),
        ],
    ] {
        kcs(&dir, &args).arg("--json").assert().code(2);
    }
    pointer["schema_version"] = Value::from(999);
    let future = serde_json::to_string(&pointer).unwrap();
    kcs(&dir, &["evidence", "verify", &future])
        .arg("--json")
        .assert()
        .code(2);
}

#[test]
fn ct4_verify_missing_raw_is_completed_not_found_and_strict_exit_four() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let store = ObjectStore::new(dir.path().join(".kcs"));
    fs::remove_file(store.object_path(ObjectKind::Raw, raw_hash).unwrap()).unwrap();
    let pointer = serde_json::to_string(&pointer).unwrap();

    let output = success(&dir, &["evidence", "verify", &pointer]);
    assert_eq!(output["status"], "not_found");
    let strict = kcs(&dir, &["evidence", "verify", &pointer, "--strict"])
        .arg("--json")
        .assert()
        .code(4)
        .get_output()
        .stdout
        .clone();
    let strict: Value = serde_json::from_slice(&strict).unwrap();
    assert_eq!(strict["status"], "not_found");
}

#[test]
fn ct4_fsck_healthy_graph_is_unchanged() {
    let (dir, _, _) = fixture();
    let head_before = fs::read(dir.path().join(".kcs/HEAD")).unwrap();
    let output = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(output["status"], "ok", "{output}");
    assert!(output["checked"]["raw"].as_u64().unwrap() > 0);
    assert!(output["checked"]["chunks"].as_u64().unwrap() > 0);
    assert_eq!(fs::read(dir.path().join(".kcs/HEAD")).unwrap(), head_before);
}

#[test]
fn ct4_fsck_recovers_identical_working_raw_and_records_repaired_commit() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let store = ObjectStore::new(dir.path().join(".kcs"));
    fs::remove_file(store.object_path(ObjectKind::Raw, raw_hash).unwrap()).unwrap();
    let output = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(output["status"], "ok", "{output}");
    assert_eq!(output["repaired_raw_count"], 1);
    assert!(output["repaired_commit_hash"].as_str().is_some());
    assert!(store.inspect_object(ObjectKind::Raw, raw_hash).is_ok());
}

#[test]
fn ct4_fsck_replaces_corrupt_present_raw_from_identical_working_bytes() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let store = ObjectStore::new(dir.path().join(".kcs"));
    let raw_path = store.object_path(ObjectKind::Raw, raw_hash).unwrap();
    fs::write(&raw_path, b"corrupt-present-raw").unwrap();

    let output = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(output["status"], "ok", "{output}");
    assert_eq!(output["repaired_raw_count"], 1);
    assert!(output["repaired_commit_hash"].as_str().is_some());
    assert!(store.inspect_object(ObjectKind::Raw, raw_hash).is_ok());
}

#[test]
fn ct4_verify_uri_and_bounded_stdin_are_read_only() {
    let (dir, pointer, uri) = fixture();
    assert_eq!(
        success(&dir, &["evidence", "verify", &uri])["status"],
        "alive"
    );
    let inline = serde_json::to_string(&pointer).unwrap();
    let stdin = kcs(&dir, &["evidence", "verify", "-"])
        .arg("--json")
        .write_stdin(inline)
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    assert_eq!(
        serde_json::from_slice::<Value>(&stdin).unwrap()["status"],
        "alive"
    );
    assert!(!dir.path().join(".test-cache/kcs/open").exists());

    let oversized = "x".repeat(64 * 1024 + 1);
    let error = kcs(&dir, &["evidence", "verify", "-"])
        .arg("--json")
        .write_stdin(oversized)
        .assert()
        .code(2)
        .get_output()
        .stderr
        .clone();
    assert_eq!(
        serde_json::from_slice::<Value>(&error).unwrap()["error_code"],
        "KCS-E-CONFIG-USAGE-001"
    );
}

#[test]
fn ct4_verify_genuine_shallow_commit_uses_durable_chunk_cas() {
    let (dir, pointer, _) = fixture();
    let repo = kcs_core::scope::Repository::open(dir.path()).unwrap();
    let commit = repo
        .read_commit(pointer["commit"].as_str().unwrap())
        .unwrap();
    let store = ObjectStore::new(dir.path().join(".kcs"));
    fs::remove_file(store.object_path(ObjectKind::Tree, &commit.tree).unwrap()).unwrap();
    let pointer = serde_json::to_string(&pointer).unwrap();
    let output = success(&dir, &["evidence", "verify", &pointer]);
    assert_eq!(output["status"], "alive");
    assert_eq!(output["details"]["commit_shallow"], true);
}

#[test]
fn ct4_verify_chunk_cas_is_truth_over_jsonl_and_sqlite() {
    let (dir, pointer, _) = fixture();
    let chunk_hash = pointer["chunk_hash"].as_str().unwrap();
    let store = ObjectStore::new(dir.path().join(".kcs"));
    fs::remove_file(store.chunk_path(chunk_hash).unwrap()).unwrap();
    let pointer = serde_json::to_string(&pointer).unwrap();
    let error = kcs(&dir, &["evidence", "verify", &pointer])
        .arg("--json")
        .assert()
        .code(8)
        .get_output()
        .stderr
        .clone();
    assert_eq!(
        serde_json::from_slice::<Value>(&error).unwrap()["error_code"],
        "KCS-E-EVIDENCE-RETARGET-REQUIRED-001"
    );
}

#[test]
fn ct4_fsck_unrecoverable_raw_is_bounded_partial_and_logged() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let store = ObjectStore::new(dir.path().join(".kcs"));
    fs::remove_file(store.object_path(ObjectKind::Raw, raw_hash).unwrap()).unwrap();
    fs::remove_file(dir.path().join("evidence.md")).unwrap();
    let stdout = kcs(&dir, &["repair", "--verify-objects"])
        .arg("--json")
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let output: Value = serde_json::from_slice(&stdout).unwrap();
    assert_eq!(output["status"], "corrupt");
    assert_eq!(output["external_pointers_may_be_affected"], true);
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "missing_raw"));
    assert!(dir.path().join(".test-data/kcs/logs/errors.jsonl").exists());
}

#[test]
fn ct4_verify_and_fsck_accept_valid_tombstone_terminal() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let digest = raw_hash.trim_start_matches("sha256:");
    let tombstone = dir
        .path()
        .join(".kcs/tombstones")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(digest);
    fs::create_dir_all(tombstone.parent().unwrap()).unwrap();
    let repo = kcs_core::scope::Repository::open(dir.path()).unwrap();
    let parent_hash = repo.head_commit_hash().unwrap().unwrap();
    let parent = repo.read_commit(&parent_hash).unwrap();
    let purged_at = "2026-07-13T00:00:00Z";
    let purged = CommitObject::new(
        parent.tree,
        vec![parent_hash],
        purged_at.to_owned(),
        "legal".to_owned(),
        parent.tool_lock_hash,
        CommitStats {
            files_added: 0,
            files_modified: 0,
            files_deleted: 0,
        },
        CommitType::Purged,
    )
    .unwrap();
    let store = ObjectStore::new(dir.path().join(".kcs"));
    let (purged_hash, _) = store
        .write_json(ObjectKind::Commit, &serde_json::to_value(&purged).unwrap())
        .unwrap();
    fs::write(dir.path().join(".kcs/HEAD"), &purged_hash).unwrap();
    fs::write(dir.path().join(".kcs/refs/heads/main"), &purged_hash).unwrap();
    fs::write(
        &tombstone,
        serde_json::to_vec(&serde_json::json!({
            "raw_hash": raw_hash,
            "purged_at": purged_at,
            "purged_reason": "legal",
            "purged_in_commit": purged_hash,
        }))
        .unwrap(),
    )
    .unwrap();
    fs::remove_file(store.object_path(ObjectKind::Raw, raw_hash).unwrap()).unwrap();
    fs::remove_dir_all(dir.path().join(".kcs/objects/normalized_units")).unwrap();
    fs::remove_dir_all(dir.path().join(".kcs/objects/chunks")).unwrap();
    let pointer = serde_json::to_string(&pointer).unwrap();
    assert_eq!(
        success(&dir, &["evidence", "verify", &pointer])["status"],
        "tombstoned"
    );
    let fsck = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(fsck["status"], "ok", "{fsck}");
    assert_eq!(fsck["dead_by_tombstone_count"], 1);
}

#[test]
fn ct4_fsck_checks_failed_prepared_and_metadata_only_image_references() {
    let (dir, _, _) = fixture();
    let normalized = dir.path().join(".kcs/objects/normalized_units");
    let manifest_path = files_named(&normalized, "manifest.json").remove(0);
    let mut manifest: Value = serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
    let template = manifest["units"][0].clone();
    let failed_key = "failed:image";
    let mut failed = template;
    failed["unit_key"] = Value::from(failed_key);
    failed["unit_ref"] = Value::from(kcs_pipeline::prepare::unit_ref(failed_key));
    failed["status"] = Value::from("failed");
    failed["prepared_hash"] = Value::from(format!("sha256:{}", "e".repeat(64)));
    failed["error_kind"] = Value::from("contract_violation");
    manifest["units"].as_array_mut().unwrap().push(failed);
    fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();

    let unit_path = fs::read_dir(manifest_path.parent().unwrap())
        .unwrap()
        .flatten()
        .map(|entry| entry.path())
        .find(|path| {
            path.extension().and_then(|ext| ext.to_str()) == Some("json") && path != &manifest_path
        })
        .unwrap();
    let mut unit: Value = serde_json::from_slice(&fs::read(&unit_path).unwrap()).unwrap();
    unit["metadata"]["images"] = serde_json::json!([{
        "hash": format!("sha256:{}", "f".repeat(64)),
        "media_type": "image/png"
    }]);
    fs::write(&unit_path, serde_json::to_vec(&unit).unwrap()).unwrap();

    let stdout = kcs(&dir, &["repair", "--verify-objects"])
        .arg("--json")
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let output: Value = serde_json::from_slice(&stdout).unwrap();
    let kinds = output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|finding| finding["kind"].as_str())
        .collect::<std::collections::BTreeSet<_>>();
    assert!(kinds.contains("prepared_corrupt"), "{output}");
    assert!(kinds.contains("image_corrupt"), "{output}");
}

#[test]
fn ct4_fsck_accepts_erase_receipt_reachable_only_from_canonical_tag() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let timestamp = "2026-07-13T00:00:00Z";
    let purged_hash = write_purged_commit(&dir, timestamp);
    tag_commit(&dir, "purged-only", &purged_hash);
    write_receipt(&dir, raw_hash, &purged_hash, timestamp);
    let store = ObjectStore::new(dir.path().join(".kcs"));
    fs::remove_file(store.object_path(ObjectKind::Raw, raw_hash).unwrap()).unwrap();
    fs::remove_dir_all(dir.path().join(".kcs/objects/normalized_units")).unwrap();
    fs::remove_dir_all(dir.path().join(".kcs/objects/chunks")).unwrap();
    let output = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(output["status"], "ok", "{output}");
    assert_eq!(output["dead_by_erase_receipt_count"], 1);
}

#[test]
fn ct4_fsck_live_raw_retires_valid_stale_receipt_without_commit() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let timestamp = "2026-07-13T00:00:00Z";
    let purged_hash = write_purged_commit(&dir, timestamp);
    tag_commit(&dir, "stale-receipt", &purged_hash);
    let receipt = write_receipt(&dir, raw_hash, &purged_hash, timestamp);
    let head_before = fs::read(dir.path().join(".kcs/HEAD")).unwrap();
    let output = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(output["status"], "ok", "{output}");
    assert_eq!(output["repaired_commit_hash"], Value::Null);
    assert!(!receipt.exists());
    assert_eq!(fs::read(dir.path().join(".kcs/HEAD")).unwrap(), head_before);
}

#[test]
fn ct4_fsck_active_journal_suppresses_raw_recovery_and_ref_mutation() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    let purge = PurgeState::new(dir.path().join(".kcs"));
    purge
        .begin(
            vec![raw_hash.clone()],
            PurgeReason::Legal,
            TombstoneMode::Default,
            "2026-07-13T00:00:00Z",
        )
        .unwrap();
    let journal_before = fs::read(purge.journal_path()).unwrap();
    let head_before = fs::read(dir.path().join(".kcs/HEAD")).unwrap();
    let store = ObjectStore::new(dir.path().join(".kcs"));
    let raw_path = store.object_path(ObjectKind::Raw, &raw_hash).unwrap();
    fs::remove_file(&raw_path).unwrap();
    let stdout = kcs(&dir, &["repair", "--verify-objects"])
        .arg("--json")
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let output: Value = serde_json::from_slice(&stdout).unwrap();
    assert_eq!(output["status"], "corrupt");
    assert_eq!(output["error_code"], "KCS-E-PURGE-INCOMPLETE-001");
    assert_eq!(output["checked"]["raw"], 0);
    assert_eq!(output["checked"]["chunks"], 0);
    assert_eq!(output["checked"]["normalized_instances"], 0);
    assert!(!raw_path.exists());
    assert_eq!(fs::read(purge.journal_path()).unwrap(), journal_before);
    assert_eq!(fs::read(dir.path().join(".kcs/HEAD")).unwrap(), head_before);
}

#[cfg(unix)]
#[test]
fn ct4_fsck_rejects_linked_object_namespace_without_traversing_it() {
    use std::os::unix::fs::symlink;

    let (dir, _, _) = fixture();
    let chunks = dir.path().join(".kcs/objects/chunks");
    fs::remove_dir_all(&chunks).unwrap();
    let outside = tempfile::tempdir().unwrap();
    fs::write(outside.path().join("secret"), b"must not be inventoried").unwrap();
    symlink(outside.path(), &chunks).unwrap();

    let stdout = kcs(&dir, &["repair", "--verify-objects"])
        .arg("--json")
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let output: Value = serde_json::from_slice(&stdout).unwrap();
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "non_regular_object"));
}

#[test]
fn ct4_fsck_rejects_live_raw_tombstone_and_dual_terminal_markers() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let timestamp = "2026-07-13T00:00:00Z";
    let purged_hash = write_purged_commit(&dir, timestamp);
    tag_commit(&dir, "marker-conflict", &purged_hash);
    let tombstone = write_tombstone(&dir, raw_hash, &purged_hash, timestamp);
    let stdout = kcs(&dir, &["repair", "--verify-objects"])
        .arg("--json")
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let output: Value = serde_json::from_slice(&stdout).unwrap();
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "tombstone_conflict"));

    let store = ObjectStore::new(dir.path().join(".kcs"));
    fs::remove_file(store.object_path(ObjectKind::Raw, raw_hash).unwrap()).unwrap();
    write_receipt(&dir, raw_hash, &purged_hash, timestamp);
    assert!(tombstone.exists());
    let stdout = kcs(&dir, &["repair", "--verify-objects"])
        .arg("--json")
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let output: Value = serde_json::from_slice(&stdout).unwrap();
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "purge_marker_conflict"));
}
