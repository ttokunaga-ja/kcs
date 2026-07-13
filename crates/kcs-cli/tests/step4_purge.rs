use std::fs;
use std::path::{Path, PathBuf};

use assert_cmd::Command;
use kcs_core::cas::{fanout_path, hash_bytes, ContentObjectKind, ObjectKind, ObjectStore};
use kcs_core::dag::CommitType;
use kcs_core::purge::{PurgeReason, PurgeState};
use kcs_core::scope::Repository;
use kcs_pipeline::markdownize::{load_validated_normalized_instance, persist_normalized_instance};
use kcs_pipeline::task::TaskStore;
use rusqlite::Connection;
use serde_json::{json, Value};
use tempfile::TempDir;

const CHILD_ENV_DENYLIST: &[&str] = &[
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "KCS_FIXED_NOW",
    "KCS_TEST_PURGE_FAIL_AFTER_PHASE",
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

fn json_partial_with_fault(dir: &TempDir, raw_hash: &str, phase: &str) -> Value {
    let stdout = kcs(
        dir,
        &[
            "purge",
            "--raw-hash",
            raw_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
    )
    .env("KCS_TEST_PURGE_FAIL_AFTER_PHASE", phase)
    .env("KCS_FIXED_NOW", "2026-07-13T01:02:03Z")
    .arg("--json")
    .assert()
    .code(3)
    .get_output()
    .stdout
    .clone();
    serde_json::from_slice(&stdout).unwrap()
}

struct IndexedFixture {
    dir: TempDir,
    raw_hash: String,
    chunk_id: String,
    scope_id: String,
    pointer: Value,
}

fn indexed_fixture() -> IndexedFixture {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("doc.md"),
        "# Private\n\nneedle-purge-content must disappear\n",
    )
    .unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--offline", "--approve"]);
    let search = json_success(&dir, &["search", "needle-purge-content", "--text"]);
    let pointer = search["results"][0]["evidence_pointer"].clone();
    IndexedFixture {
        raw_hash: pointer["raw_hash"].as_str().unwrap().to_owned(),
        chunk_id: pointer["chunk_hash"].as_str().unwrap().to_owned(),
        scope_id: pointer["scope_id"].as_str().unwrap().to_owned(),
        pointer,
        dir,
    }
}

fn current_raw_for(dir: &TempDir, path: &str) -> String {
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

fn tombstone_path(kcs_dir: &Path, raw_hash: &str) -> PathBuf {
    fanout_path(kcs_dir.join("tombstones"), raw_hash).unwrap()
}

fn add_image_reference(dir: &TempDir, raw_hash: &str, image_bytes: &[u8]) -> String {
    let repo = Repository::open(dir.path()).unwrap();
    let head = repo.head_commit_hash().unwrap().unwrap();
    let commit = repo.read_commit(&head).unwrap();
    let tree = repo.read_tree(&commit.tree).unwrap();
    let normalize = tree
        .entries
        .iter()
        .find(|entry| entry.raw_hash == raw_hash)
        .and_then(|entry| entry.normalize.clone())
        .unwrap();
    let mut instance = load_validated_normalized_instance(
        repo.kcs_dir(),
        raw_hash,
        &normalize.tool_profile_hash,
        normalize.gen,
    )
    .unwrap();
    let image_hash = hash_bytes(image_bytes);
    let image_path = fanout_path(repo.kcs_dir().join("objects/images"), &image_hash).unwrap();
    fs::create_dir_all(image_path.parent().unwrap()).unwrap();
    fs::write(&image_path, image_bytes).unwrap();
    instance.units[0]
        .metadata
        .insert("images".to_owned(), json!([{ "hash": image_hash }]));
    persist_normalized_instance(repo.kcs_dir(), &instance.manifest, &instance.units).unwrap();
    image_hash
}

fn read_json_lines(path: &Path) -> Vec<Value> {
    fs::read_to_string(path)
        .unwrap_or_default()
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
}

#[test]
fn ct4_purge_typed_path_preview_live_refusal_and_all_versions() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("doc.md"), "version one").unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--offline", "--approve"]);
    let raw_one = current_raw_for(&dir, "doc.md");
    fs::write(dir.path().join("doc.md"), "version two").unwrap();
    json_success(&dir, &["index", "--offline", "--approve"]);
    let raw_two = current_raw_for(&dir, "doc.md");
    assert_ne!(raw_one, raw_two);

    let before_head = fs::read(dir.path().join(".kcs/HEAD")).unwrap();
    let error = json_failure(&dir, &["purge", "doc.md", "--reason", "legal", "--yes"], 4);
    assert_eq!(error["error_code"], "KCS-E-PURGE-WORKING-COPY-001");
    assert_eq!(fs::read(dir.path().join(".kcs/HEAD")).unwrap(), before_head);
    assert!(!dir.path().join(".kcs/purge/in-progress.json").exists());

    fs::remove_file(dir.path().join("doc.md")).unwrap();
    kcs(&dir, &["purge", "doc.md", "--reason", "legal"])
        .write_stdin("no\n")
        .arg("--json")
        .assert()
        .code(9);
    assert_eq!(fs::read(dir.path().join(".kcs/HEAD")).unwrap(), before_head);
    assert!(!dir.path().join(".kcs/purge/in-progress.json").exists());

    let output = json_success(&dir, &["purge", "doc.md", "--reason", "legal", "--yes"]);
    assert_eq!(output["target_raw_count"], 2);
    let state = PurgeState::new(dir.path().join(".kcs"));
    for raw_hash in [&raw_one, &raw_two] {
        assert_eq!(
            state
                .read_tombstone(raw_hash)
                .unwrap()
                .unwrap()
                .purged_reason,
            PurgeReason::Legal
        );
    }
    let repo = Repository::open(dir.path()).unwrap();
    let head = repo.head_commit_hash().unwrap().unwrap();
    let commit = repo.read_commit(&head).unwrap();
    assert_eq!(commit.commit_type, CommitType::Purged);
    assert_eq!(commit.message, "legal");
    assert_eq!(commit.parents.len(), 1);
}

#[test]
fn ct4_purge_default_deletes_all_surfaces_blocks_reads_and_is_idempotent() {
    let fixture = indexed_fixture();
    let kcs_dir = fixture.dir.path().join(".kcs");
    let image_hash = add_image_reference(&fixture.dir, &fixture.raw_hash, b"private image bytes");
    let image_path = fanout_path(kcs_dir.join("objects/images"), &image_hash).unwrap();

    fs::write(
        kcs_dir.join("unsupported-inputs.jsonl"),
        format!(
            "{}\n{}\n",
            json!({"path":"doc.md","raw_hash":fixture.raw_hash,"media_type":"x","size_bytes":1,"reason":"test"}),
            json!({"path":"keep.bin","raw_hash":format!("sha256:{}", "a".repeat(64)),"media_type":"x","size_bytes":1,"reason":"keep"})
        ),
    )
    .unwrap();
    fs::write(
        kcs_dir.join("quarantine.jsonl"),
        format!(
            "{}\n{}\n",
            json!({"path":"doc.md","reason":"secret","recorded_at":"2026-01-01T00:00:00Z","approval_method":"hold"}),
            json!({"path":"keep.md","reason":"secret","recorded_at":"2026-01-01T00:00:00Z","approval_method":"hold"})
        ),
    )
    .unwrap();
    let device_logs = fixture.dir.path().join(".test-data/kcs/logs");
    let scope_logs = kcs_dir.join("logs");
    fs::create_dir_all(&device_logs).unwrap();
    fs::create_dir_all(&scope_logs).unwrap();
    let target_log =
        json!({"raw_hash":fixture.raw_hash,"path":"doc.md","query":"needle-purge-content"});
    fs::write(
        device_logs.join("events.jsonl.1"),
        format!("{target_log}\n{}\n", json!({"event":"keep"})),
    )
    .unwrap();
    fs::write(scope_logs.join("access.jsonl"), format!("{target_log}\n")).unwrap();
    let cache = fixture
        .dir
        .path()
        .join(".test-cache/kcs/open")
        .join(fixture.raw_hash.trim_start_matches("sha256:"));
    fs::create_dir_all(&cache).unwrap();
    fs::write(cache.join("doc.md"), b"needle-purge-content").unwrap();

    fs::remove_file(fixture.dir.path().join("doc.md")).unwrap();
    let output = json_success(
        &fixture.dir,
        &[
            "purge",
            "--raw-hash",
            &fixture.raw_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
    );
    assert_eq!(output["status"], "purged");
    assert_eq!(output["tombstone_mode"], "default");
    assert_eq!(output["tombstone_count"], 1);
    assert_eq!(output["erase_receipt_count"], 0);
    assert_eq!(output["guarantee"], "removed from KCS-managed history");
    assert_eq!(output["deleted_counts"]["raw_objects"], 1);
    assert!(
        output["deleted_counts"]["normalized_instances"]
            .as_u64()
            .unwrap()
            >= 1
    );
    assert!(
        output["deleted_counts"]["prepared_objects"]
            .as_u64()
            .unwrap()
            >= 1
    );
    assert_eq!(output["deleted_counts"]["image_objects"], 1);
    assert!(output["deleted_counts"]["tasks"].as_u64().unwrap() >= 1);
    assert!(output["log_files_scrubbed"].as_u64().unwrap() >= 2);
    let bounded_report = output.to_string();
    for secret in [&fixture.raw_hash, "doc.md", "needle-purge-content"] {
        assert!(!bounded_report.contains(secret));
    }

    let store = ObjectStore::new(&kcs_dir);
    assert!(store
        .inspect_object(ObjectKind::Raw, &fixture.raw_hash)
        .is_err());
    assert!(store.read_chunk(&fixture.chunk_id).is_err());
    assert!(store
        .inspect_content_object(ContentObjectKind::Image, &image_hash)
        .is_err());
    assert!(!image_path.exists());
    assert!(!kcs_dir.join("purge/in-progress.json").exists());
    assert!(tombstone_path(&kcs_dir, &fixture.raw_hash).exists());
    assert!(!cache.exists());

    let chunks = read_json_lines(&kcs_dir.join("index/chunks.jsonl"));
    assert!(chunks.iter().all(|row| row["raw_hash"] != fixture.raw_hash));
    let conn = Connection::open(kcs_dir.join("index/sqlite.db")).unwrap();
    let count: u64 = conn
        .query_row(
            "SELECT COUNT(*) FROM chunks WHERE raw_hash = ?1",
            [&fixture.raw_hash],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 0);
    assert!(TaskStore::new(&kcs_dir)
        .all()
        .unwrap()
        .iter()
        .all(|task| task.input_hash != fixture.raw_hash));
    assert!(read_json_lines(&kcs_dir.join("unsupported-inputs.jsonl"))
        .iter()
        .all(|row| row["raw_hash"] != fixture.raw_hash));
    assert!(read_json_lines(&kcs_dir.join("quarantine.jsonl"))
        .iter()
        .all(|row| row["path"] != "doc.md"));
    for path in [
        device_logs.join("events.jsonl.1"),
        scope_logs.join("access.jsonl"),
    ] {
        let text = fs::read_to_string(path).unwrap();
        assert!(!text.contains(&fixture.raw_hash));
        assert!(!text.contains("needle-purge-content"));
        assert!(!text.contains("doc.md"));
    }

    for args in [
        vec!["search", "needle-purge-content", "--text"],
        vec!["search", "needle-purge-content", "--text", "--all-history"],
    ] {
        assert!(json_success(&fixture.dir, &args)["results"]
            .as_array()
            .unwrap()
            .is_empty());
    }
    let pointer = fixture.pointer.to_string();
    assert_eq!(
        json_failure(&fixture.dir, &["open", &pointer], 4)["error_code"],
        "KCS-E-PURGE-TOMBSTONED-001"
    );
    let raw_uri = format!("kcs://{}/object/raw/{}", fixture.scope_id, fixture.raw_hash);
    assert_eq!(
        json_failure(&fixture.dir, &["open", &raw_uri], 4)["error_code"],
        "KCS-E-PURGE-TOMBSTONED-001"
    );

    let head = fs::read(kcs_dir.join("HEAD")).unwrap();
    let tombstone = fs::read(tombstone_path(&kcs_dir, &fixture.raw_hash)).unwrap();
    let repeated = json_success(
        &fixture.dir,
        &[
            "purge",
            "--raw-hash",
            &fixture.raw_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
    );
    assert_eq!(repeated["purged_in_commit"], output["purged_in_commit"]);
    assert_eq!(fs::read(kcs_dir.join("HEAD")).unwrap(), head);
    assert_eq!(
        fs::read(tombstone_path(&kcs_dir, &fixture.raw_hash)).unwrap(),
        tombstone
    );
}

#[test]
fn ct4_purge_erase_leaves_only_private_receipt_and_is_repeatable() {
    let fixture = indexed_fixture();
    fs::remove_file(fixture.dir.path().join("doc.md")).unwrap();
    let output = json_success(
        &fixture.dir,
        &[
            "purge",
            "--raw-hash",
            &fixture.raw_hash,
            "--reason",
            "misingest",
            "--erase-tombstone",
            "--yes",
        ],
    );
    assert_eq!(output["tombstone_mode"], "erase");
    assert_eq!(output["tombstone_count"], 0);
    assert_eq!(output["erase_receipt_count"], 1);
    let state = PurgeState::new(fixture.dir.path().join(".kcs"));
    assert!(state.read_tombstone(&fixture.raw_hash).unwrap().is_none());
    let receipt = state
        .read_erase_receipt(&fixture.raw_hash)
        .unwrap()
        .unwrap();
    assert_eq!(receipt.purged_in_commit, output["purged_in_commit"]);
    assert!(state.read_journal().unwrap().is_none());

    let pointer = fixture.pointer.to_string();
    assert_eq!(
        json_failure(&fixture.dir, &["open", &pointer], 4)["error_code"],
        "KCS-E-PURGE-NOT-FOUND-001"
    );
    let head = fs::read(fixture.dir.path().join(".kcs/HEAD")).unwrap();
    let repeat = json_success(
        &fixture.dir,
        &[
            "purge",
            "--raw-hash",
            &fixture.raw_hash,
            "--reason",
            "misingest",
            "--erase-tombstone",
            "--yes",
        ],
    );
    assert_eq!(repeat["purged_in_commit"], output["purged_in_commit"]);
    assert_eq!(
        fs::read(fixture.dir.path().join(".kcs/HEAD")).unwrap(),
        head
    );
}

#[test]
fn ct4_purge_preserves_shared_image_until_last_reference_is_removed() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# A\n\nshared-image-a").unwrap();
    fs::write(dir.path().join("b.md"), "# B\n\nshared-image-b").unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--offline", "--approve"]);
    let raw_a = current_raw_for(&dir, "a.md");
    let raw_b = current_raw_for(&dir, "b.md");
    let image_a = add_image_reference(&dir, &raw_a, b"one shared image");
    let image_b = add_image_reference(&dir, &raw_b, b"one shared image");
    assert_eq!(image_a, image_b);
    fs::remove_file(dir.path().join("a.md")).unwrap();
    let output = json_success(
        &dir,
        &[
            "purge",
            "--raw-hash",
            &raw_a,
            "--reason",
            "copyright",
            "--yes",
        ],
    );
    assert_eq!(output["shared_artifacts_preserved"]["image_objects"], 1);
    ObjectStore::new(dir.path().join(".kcs"))
        .inspect_content_object(ContentObjectKind::Image, &image_a)
        .unwrap();
}

#[test]
fn ct4_purge_acquires_publication_lock_before_publishing_barrier() {
    let fixture = indexed_fixture();
    fs::remove_file(fixture.dir.path().join("doc.md")).unwrap();
    fs::write(
        fixture.dir.path().join(".kcs/purge-publication.lock"),
        serde_json::to_vec(&json!({
            "pid": std::process::id(),
            "token": "ct4-purge-held-publication-lock",
            "created_at": "2026-07-13T00:00:00Z",
        }))
        .unwrap(),
    )
    .unwrap();

    let error = json_failure(
        &fixture.dir,
        &[
            "purge",
            "--raw-hash",
            &fixture.raw_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
        3,
    );
    assert_eq!(error["error_code"], "KCS-E-STORE-LOCKED-001");
    assert!(ObjectStore::new(fixture.dir.path().join(".kcs"))
        .inspect_object(ObjectKind::Raw, &fixture.raw_hash)
        .is_ok());
    assert!(!fixture
        .dir
        .path()
        .join(".kcs/purge/in-progress.json")
        .exists());
}

#[test]
fn ct4_purge_cleans_tombstoned_ingest_orphan_before_live_copy_refusal() {
    let fixture = indexed_fixture();
    let raw_bytes = b"# Private\n\nneedle-purge-content must disappear\n";
    fs::remove_file(fixture.dir.path().join("doc.md")).unwrap();
    json_success(
        &fixture.dir,
        &[
            "purge",
            "--raw-hash",
            &fixture.raw_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
    );

    // Model a killed post-purge ingest: the working bytes were reintroduced and
    // a complete private staging leaf survived before its tombstone check.
    fs::write(fixture.dir.path().join("doc.md"), raw_bytes).unwrap();
    let orphan = fixture
        .dir
        .path()
        .join(".kcs/objects/raw/.ingest-killed-after-purge");
    fs::write(&orphan, raw_bytes).unwrap();
    let error = json_failure(
        &fixture.dir,
        &[
            "purge",
            "--raw-hash",
            &fixture.raw_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
        4,
    );
    assert_eq!(error["error_code"], "KCS-E-PURGE-WORKING-COPY-001");
    assert!(!orphan.exists());
    assert!(tombstone_path(&fixture.dir.path().join(".kcs"), &fixture.raw_hash).exists());
}

#[test]
fn ct4_purge_faults_publish_no_prebarrier_state_and_resume_every_visible_phase() {
    let prepared = indexed_fixture();
    fs::remove_file(prepared.dir.path().join("doc.md")).unwrap();
    let error = kcs(
        &prepared.dir,
        &[
            "purge",
            "--raw-hash",
            &prepared.raw_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
    )
    .env("KCS_TEST_PURGE_FAIL_AFTER_PHASE", "prepared")
    .arg("--json")
    .assert()
    .code(1)
    .get_output()
    .stderr
    .clone();
    let error: Value = serde_json::from_slice(&error).unwrap();
    assert_eq!(error["error_code"], "KCS-E-STORE-IO-001");
    assert!(ObjectStore::new(prepared.dir.path().join(".kcs"))
        .inspect_object(ObjectKind::Raw, &prepared.raw_hash)
        .is_ok());
    assert!(!prepared
        .dir
        .path()
        .join(".kcs/purge/in-progress.json")
        .exists());

    for phase in [
        "barrier_published",
        "purged_commit_created",
        "content_deleted",
        "derived_deleted",
        "logs_scrubbed",
    ] {
        let fixture = indexed_fixture();
        fs::remove_file(fixture.dir.path().join("doc.md")).unwrap();
        let partial = json_partial_with_fault(&fixture.dir, &fixture.raw_hash, phase);
        assert_eq!(partial["error_code"], "KCS-E-PURGE-INCOMPLETE-001");
        assert_eq!(partial["status"], "purge_incomplete");
        assert!(!partial.to_string().contains(&fixture.raw_hash));
        assert!(fixture
            .dir
            .path()
            .join(".kcs/purge/in-progress.json")
            .exists());
        assert!(
            json_success(&fixture.dir, &["search", "needle-purge-content", "--text"])["results"]
                .as_array()
                .unwrap()
                .is_empty()
        );
        let raw_uri = format!("kcs://{}/object/raw/{}", fixture.scope_id, fixture.raw_hash);
        let read = kcs(&fixture.dir, &["open", &raw_uri, "--json"])
            .assert()
            .failure()
            .get_output()
            .clone();
        assert!(!String::from_utf8_lossy(&read.stdout).contains("needle-purge-content"));
        assert!(!String::from_utf8_lossy(&read.stderr).contains("needle-purge-content"));

        let resumed = json_success(
            &fixture.dir,
            &[
                "purge",
                "--raw-hash",
                &fixture.raw_hash,
                "--reason",
                "privacy",
                "--yes",
            ],
        );
        assert_eq!(resumed["status"], "purged", "phase={phase}");
        assert!(!fixture
            .dir
            .path()
            .join(".kcs/purge/in-progress.json")
            .exists());
    }
}
