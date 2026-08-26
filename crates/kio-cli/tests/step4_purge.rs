use std::fs;
use std::path::{Path, PathBuf};

use assert_cmd::Command;
use kio_core::cas::{ContentObjectKind, ObjectKind, ObjectStore, fanout_path, hash_bytes};
use kio_core::dag::CommitType;
use kio_core::purge::{PurgeReason, PurgeState};
use kio_core::scope::Repository;
use kio_pipeline::markdownize::{
    NormalizedInstanceManifest, UnitStatus, load_validated_normalized_instance,
    persist_normalized_instance,
};
use kio_pipeline::task::TaskStore;
use rusqlite::Connection;
use serde_json::{Value, json};
use tempfile::TempDir;

const CHILD_ENV_DENYLIST: &[&str] = &[
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "KIO_FIXED_NOW",
    "KIO_TEST_PURGE_FAIL_AFTER_PHASE",
    // Set per-command by the embedded fixtures only, so an ambient value cannot
    // silently turn the `--offline` fixtures into embedding ones.
    "KIO_TEST_GEMINI_EMBED",
    "KIO_EVAL_DETERMINISTIC_EMBED",
    "KIO_TEST_MISTRAL_OCR",
];

fn kio(dir: &TempDir, args: &[&str]) -> Command {
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
    command
}

fn json_success(dir: &TempDir, args: &[&str]) -> Value {
    let stdout = kio(dir, args)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&stdout).unwrap()
}

fn json_success_with_env(dir: &TempDir, args: &[&str], env: &[(&str, &str)]) -> Value {
    let mut command = kio(dir, args);
    for (name, value) in env {
        command.env(name, value);
    }
    let stdout = command
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&stdout).unwrap()
}

fn json_failure(dir: &TempDir, args: &[&str], code: i32) -> Value {
    let stderr = kio(dir, args)
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stderr
        .clone();
    serde_json::from_slice(&stderr).unwrap()
}

fn json_partial_with_fault(dir: &TempDir, raw_hash: &str, phase: &str) -> Value {
    let stdout = kio(
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
    .env("KIO_TEST_PURGE_FAIL_AFTER_PHASE", phase)
    .env("KIO_FIXED_NOW", "2026-07-13T01:02:03Z")
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
    let search = json_success(&dir, &["search", "needle-purge-content", "--mode", "text"]);
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

fn normalized_unit_pins_for(dir: &TempDir, path: &str) -> Vec<String> {
    let repo = Repository::open(dir.path()).unwrap();
    let head = repo.head_commit_hash().unwrap().unwrap();
    let commit = repo.read_commit(&head).unwrap();
    let entry = repo
        .read_tree(&commit.tree)
        .unwrap()
        .entries
        .into_iter()
        .find(|entry| entry.path == path)
        .unwrap();
    let normalize = entry.normalize.unwrap();
    let manifest_bytes = ObjectStore::new(repo.kio_dir())
        .read_content_object_bytes(
            ContentObjectKind::Manifest,
            &normalize.manifest_hash,
            8 * 1024 * 1024,
        )
        .unwrap();
    assert_eq!(hash_bytes(&manifest_bytes), normalize.manifest_hash);
    let manifest: NormalizedInstanceManifest = serde_json::from_slice(&manifest_bytes).unwrap();
    manifest
        .units
        .into_iter()
        .filter(|entry| entry.status == UnitStatus::Done)
        .map(|entry| entry.unit_object_hash.unwrap())
        .collect()
}

fn tree_manifest_hash_for(dir: &TempDir, path: &str) -> String {
    let repo = Repository::open(dir.path()).unwrap();
    let head = repo.head_commit_hash().unwrap().unwrap();
    let commit = repo.read_commit(&head).unwrap();
    repo.read_tree(&commit.tree)
        .unwrap()
        .entries
        .into_iter()
        .find(|entry| entry.path == path)
        .unwrap()
        .normalize
        .unwrap()
        .manifest_hash
}

fn current_manifest_hash_for_raw(dir: &TempDir, raw_hash: &str) -> String {
    let repo = Repository::open(dir.path()).unwrap();
    let head = repo.head_commit_hash().unwrap().unwrap();
    let commit = repo.read_commit(&head).unwrap();
    let normalize = repo
        .read_tree(&commit.tree)
        .unwrap()
        .entries
        .into_iter()
        .find(|entry| entry.raw_hash == raw_hash)
        .unwrap()
        .normalize
        .unwrap();
    let instance = load_validated_normalized_instance(
        repo.kio_dir(),
        raw_hash,
        &normalize.tool_profile_hash,
        normalize.r#gen,
    )
    .unwrap();
    kio_core::cas::hash_json(&serde_json::to_value(instance.manifest).unwrap()).unwrap()
}

fn tombstone_path(kio_dir: &Path, raw_hash: &str) -> PathBuf {
    fanout_path(kio_dir.join("tombstones"), raw_hash).unwrap()
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
        repo.kio_dir(),
        raw_hash,
        &normalize.tool_profile_hash,
        normalize.r#gen,
    )
    .unwrap();
    let image_hash = hash_bytes(image_bytes);
    let image_path = fanout_path(repo.kio_dir().join("objects/image"), &image_hash).unwrap();
    fs::create_dir_all(image_path.parent().unwrap()).unwrap();
    fs::write(&image_path, image_bytes).unwrap();
    instance.units[0]
        .metadata
        .insert("images".to_owned(), json!([{ "hash": image_hash }]));
    persist_normalized_instance(repo.kio_dir(), &instance.manifest, &instance.units).unwrap();
    image_hash
}

/// Every published leaf of one `objects/<namespace>/` CAS fan-out, as
/// `sha256:`-prefixed hashes. The fan-out dirs are a prefix of the digest that
/// the leaf then repeats in full, so the leaf name alone is the digest.
fn cas_leaf_hashes(kio_dir: &Path, namespace: &str) -> Vec<String> {
    let base = kio_dir.join("objects").join(namespace);
    let Ok(first_level) = fs::read_dir(&base) else {
        return Vec::new();
    };
    let mut hashes = first_level
        .filter_map(Result::ok)
        .filter_map(|first| fs::read_dir(first.path()).ok())
        .flat_map(|second_level| second_level.filter_map(Result::ok))
        .filter_map(|second| fs::read_dir(second.path()).ok())
        .flat_map(|leaves| leaves.filter_map(Result::ok))
        .filter(|leaf| leaf.file_type().is_ok_and(|kind| kind.is_file()))
        .filter_map(|leaf| leaf.file_name().into_string().ok())
        .map(|digest| format!("sha256:{digest}"))
        .collect::<Vec<_>>();
    hashes.sort();
    hashes
}

/// A scanned PDF taken all the way through the ONLINE lane: `index` defers the
/// page to a markdownize task, and `batch resume` runs the OCR + embedding
/// adapters against their mock seams. Unlike [`indexed_fixture`] and
/// [`add_image_reference`] — `--offline`, with a hand-written image object —
/// this produces the real derived surfaces an embedded document owns: an
/// `objects/image/` object the OCR adapter persisted and linked from the unit
/// Markdown as a `kio://<scope>/object/image/<hash>` URI, AND an
/// `objects/embeddings/` object for the chunk vector.
struct EmbeddedImageFixture {
    dir: TempDir,
    raw_hash: String,
    image_hash: String,
    embedding_hashes: Vec<String>,
}

fn embedded_image_fixture() -> EmbeddedImageFixture {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("figures.pdf"), "%PDF-1.4\ntest\n").unwrap();
    json_success(&dir, &["init"]);
    json_success_with_env(
        &dir,
        &["index", "--approve"],
        &[("KIO_TEST_GEMINI_EMBED", "mock")],
    );
    json_success_with_env(
        &dir,
        &["batch", "resume"],
        &[
            ("KIO_TEST_GEMINI_EMBED", "mock"),
            // The seam that makes the OCR mock emit a Markdown image whose
            // target is rewritten to an image-object URI.
            ("KIO_TEST_MISTRAL_OCR", "mock_link_image"),
        ],
    );
    let kio_dir = dir.path().join(".kio");
    let images = cas_leaf_hashes(&kio_dir, "image");
    assert_eq!(images.len(), 1, "fixture must own exactly one image object");
    let embedding_hashes = cas_leaf_hashes(&kio_dir, "embeddings");
    assert!(
        !embedding_hashes.is_empty(),
        "fixture must own at least one embedding object"
    );
    EmbeddedImageFixture {
        raw_hash: current_raw_for(&dir, "figures.pdf"),
        image_hash: images.into_iter().next().unwrap(),
        embedding_hashes,
        dir,
    }
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
fn ct4_purge_typed_path_preview_warns_on_live_working_copy_and_purges_all_versions() {
    // Step4b P2-A PA37-39 (§K, U34; §R ruling #1): the prior
    // `KIO-E-PURGE-WORKING-COPY-001` hard block is retired — a live
    // working-tree copy of a purge target is now a WARNING, carried on
    // whatever response purge produces, rather than a categorical refusal.
    // (Full completion while the residual is STILL present at commit-publish
    // time additionally depended on `Repository::snapshot_with_type`'s
    // archival step and `planned_commit`'s LC48 fixed-at-`prepared` value
    // both being reconciled with the residual — a P2-A-identified,
    // pre-existing `archive_staged_working_tree` self-barrier gap, now fixed
    // in `kio-core/src/scope.rs`: `commit_type=purged`'s own targets are
    // excluded from its own snapshot rebuild rather than treated as a
    // blocked ingest. Purge now reaches `status: "purged"` even with the
    // residual present; see
    // `pa37_pa38_pa39_working_tree_residual_warns_instead_of_the_retired_hard_block`
    // in `step4b_p2a_contract.rs` for the fuller note.)
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("doc.md"), "version one").unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--offline", "--approve"]);
    let raw_one = current_raw_for(&dir, "doc.md");
    fs::write(dir.path().join("doc.md"), "version two").unwrap();
    json_success(&dir, &["index", "--offline", "--approve"]);
    let raw_two = current_raw_for(&dir, "doc.md");
    assert_ne!(raw_one, raw_two);

    let before_head = fs::read(dir.path().join(".kio/HEAD")).unwrap();
    // Rejecting the confirmation prompt is still the only thing that leaves
    // HEAD untouched.
    kio(&dir, &["purge", "doc.md", "--reason", "legal"])
        .write_stdin("no\n")
        .arg("--json")
        .assert()
        .code(9);
    assert_eq!(fs::read(dir.path().join(".kio/HEAD")).unwrap(), before_head);
    assert!(!dir.path().join(".kio/purge/in-progress.json").exists());

    // "version two" (raw_two) is still live in doc.md here — the retired
    // hard block must not fire, and (journal-barrier fix) purge now
    // completes fully despite the live residual: the warning is carried on
    // the SUCCESS response, and the file itself is never touched.
    let output = json_success(&dir, &["purge", "doc.md", "--reason", "legal", "--yes"]);
    assert_eq!(output["status"], "purged");
    assert_ne!(output["error_code"], "KIO-E-PURGE-WORKING-COPY-001");
    assert_eq!(output["working_tree_warning"]["live_alias_count"], 1);
    assert_eq!(fs::read(dir.path().join("doc.md")).unwrap(), b"version two");

    // A fresh scope with no working-tree residual purges both historical
    // versions to completion, exactly as before this ruling.
    let clean = tempfile::tempdir().unwrap();
    fs::write(clean.path().join("doc.md"), "version one").unwrap();
    json_success(&clean, &["init"]);
    json_success(&clean, &["index", "--offline", "--approve"]);
    let raw_one = current_raw_for(&clean, "doc.md");
    fs::write(clean.path().join("doc.md"), "version two").unwrap();
    json_success(&clean, &["index", "--offline", "--approve"]);
    let raw_two = current_raw_for(&clean, "doc.md");
    fs::remove_file(clean.path().join("doc.md")).unwrap();
    let output = json_success(&clean, &["purge", "doc.md", "--reason", "legal", "--yes"]);
    assert_eq!(output["target_raw_count"], 2);
    assert!(output.get("working_tree_warning").is_none());

    let state = PurgeState::new(clean.path().join(".kio"));
    for raw_hash in [&raw_one, &raw_two] {
        assert_eq!(
            state
                .read_tombstone(raw_hash)
                .unwrap()
                .unwrap()
                .tail()
                .reason,
            Some(PurgeReason::Legal)
        );
    }
    let repo = Repository::open(clean.path()).unwrap();
    let head = repo.head_commit_hash().unwrap().unwrap();
    let commit = repo.read_commit(&head).unwrap();
    assert_eq!(commit.commit_type, CommitType::Purged);
    assert_eq!(commit.message, "legal");
    assert_eq!(commit.parents.len(), 1);
}

#[test]
fn ct4_purge_default_deletes_all_surfaces_blocks_reads_and_is_idempotent() {
    let fixture = indexed_fixture();
    let kio_dir = fixture.dir.path().join(".kio");
    let historical_manifest_hash = tree_manifest_hash_for(&fixture.dir, "doc.md");
    let image_hash = add_image_reference(&fixture.dir, &fixture.raw_hash, b"private image bytes");
    let current_manifest_hash = current_manifest_hash_for_raw(&fixture.dir, &fixture.raw_hash);
    assert_ne!(historical_manifest_hash, current_manifest_hash);
    for hash in [&historical_manifest_hash, &current_manifest_hash] {
        assert!(
            ObjectStore::new(&kio_dir)
                .content_path(ContentObjectKind::Manifest, hash)
                .unwrap()
                .exists()
        );
    }
    let image_path = fanout_path(kio_dir.join("objects/image"), &image_hash).unwrap();

    fs::write(
        kio_dir.join("unsupported-inputs.jsonl"),
        format!(
            "{}\n{}\n",
            json!({"path":"doc.md","raw_hash":fixture.raw_hash,"media_type":"x","size_bytes":1,"reason":"test"}),
            json!({"path":"keep.bin","raw_hash":format!("sha256:{}", "a".repeat(64)),"media_type":"x","size_bytes":1,"reason":"keep"})
        ),
    )
    .unwrap();
    fs::write(
        kio_dir.join("quarantine.jsonl"),
        format!(
            "{}\n{}\n",
            json!({"path":"doc.md","reason":"secret","recorded_at":"2026-01-01T00:00:00Z","approval_method":"hold"}),
            json!({"path":"keep.md","reason":"secret","recorded_at":"2026-01-01T00:00:00Z","approval_method":"hold"})
        ),
    )
    .unwrap();
    let device_logs = fixture.dir.path().join(".test-data/kio/logs");
    let scope_logs = kio_dir.join("logs");
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
        .join(".test-cache/kio/open")
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
    assert_eq!(output["guarantee"], "removed from KIO-managed history");
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
    for hash in [&historical_manifest_hash, &current_manifest_hash] {
        assert!(
            !ObjectStore::new(&kio_dir)
                .content_path(ContentObjectKind::Manifest, hash)
                .unwrap()
                .exists()
        );
    }
    assert!(output["deleted_counts"]["tasks"].as_u64().unwrap() >= 1);
    assert!(output["log_files_scrubbed"].as_u64().unwrap() >= 2);
    let bounded_report = output.to_string();
    for secret in [&fixture.raw_hash, "doc.md", "needle-purge-content"] {
        assert!(!bounded_report.contains(secret));
    }

    let store = ObjectStore::new(&kio_dir);
    assert!(
        store
            .inspect_object(ObjectKind::Raw, &fixture.raw_hash)
            .is_err()
    );
    assert!(store.read_chunk(&fixture.chunk_id).is_err());
    assert!(
        store
            .inspect_content_object(ContentObjectKind::Image, &image_hash)
            .is_err()
    );
    assert!(!image_path.exists());
    assert!(!kio_dir.join("purge/in-progress.json").exists());
    assert!(tombstone_path(&kio_dir, &fixture.raw_hash).exists());
    assert!(!cache.exists());

    let chunks = read_json_lines(&kio_dir.join("index/chunks.jsonl"));
    assert!(chunks.iter().all(|row| row["raw_hash"] != fixture.raw_hash));
    let conn = Connection::open(kio_dir.join("index/sqlite.db")).unwrap();
    let count: u64 = conn
        .query_row(
            "SELECT COUNT(*) FROM chunks WHERE raw_hash = ?1",
            [&fixture.raw_hash],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 0);
    assert!(
        TaskStore::new(&kio_dir)
            .all()
            .unwrap()
            .iter()
            .all(|task| task.input_hash != fixture.raw_hash)
    );
    assert!(
        read_json_lines(&kio_dir.join("unsupported-inputs.jsonl"))
            .iter()
            .all(|row| row["raw_hash"] != fixture.raw_hash)
    );
    assert!(
        read_json_lines(&kio_dir.join("quarantine.jsonl"))
            .iter()
            .all(|row| row["path"] != "doc.md")
    );
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
        vec!["search", "needle-purge-content", "--mode", "text"],
        vec![
            "search",
            "needle-purge-content",
            "--mode",
            "text",
            "--all-history",
        ],
    ] {
        assert!(
            json_success(&fixture.dir, &args)["results"]
                .as_array()
                .unwrap()
                .is_empty()
        );
    }
    let pointer = fixture.pointer.to_string();
    assert_eq!(
        json_failure(&fixture.dir, &["open", &pointer], 4)["error_code"],
        "KIO-E-PURGE-TOMBSTONED-001"
    );
    // PA01 (§A, U22): MVP object URIs accept only `image` — a `raw`-type URI
    // is now rejected at parse time (exit 2) before any tombstone dispatch
    // even runs.
    let raw_uri = format!("kio://{}/object/raw/{}", fixture.scope_id, fixture.raw_hash);
    assert_eq!(
        json_failure(&fixture.dir, &["open", &raw_uri], 2)["error_code"],
        "KIO-E-CONFIG-USAGE-001"
    );

    let head = fs::read(kio_dir.join("HEAD")).unwrap();
    let tombstone = fs::read(tombstone_path(&kio_dir, &fixture.raw_hash)).unwrap();
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
    assert_eq!(fs::read(kio_dir.join("HEAD")).unwrap(), head);
    assert_eq!(
        fs::read(tombstone_path(&kio_dir, &fixture.raw_hash)).unwrap(),
        tombstone
    );
}

#[test]
fn ct4_purge_deletes_target_immutable_normalized_unit_objects() {
    let fixture = indexed_fixture();
    let kio_dir = fixture.dir.path().join(".kio");
    let unit_hashes = normalized_unit_pins_for(&fixture.dir, "doc.md");
    assert!(!unit_hashes.is_empty());
    for hash in &unit_hashes {
        assert!(
            ObjectStore::new(&kio_dir)
                .content_path(ContentObjectKind::NormalizedUnit, hash)
                .unwrap()
                .exists()
        );
    }

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
    assert_eq!(
        output["deleted_counts"]["normalized_unit_objects"],
        unit_hashes.len()
    );
    for hash in &unit_hashes {
        assert!(
            !ObjectStore::new(&kio_dir)
                .content_path(ContentObjectKind::NormalizedUnit, hash)
                .unwrap()
                .exists()
        );
    }
}

#[test]
fn ct4_purge_preserves_other_raws_immutable_normalized_unit_objects() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("target.md"), "target-only secret").unwrap();
    fs::write(dir.path().join("survivor.md"), "survivor-only text").unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--offline", "--approve"]);
    let raw_hash = current_raw_for(&dir, "target.md");
    let target_units = normalized_unit_pins_for(&dir, "target.md");
    let survivor_units = normalized_unit_pins_for(&dir, "survivor.md");
    let kio_dir = dir.path().join(".kio");

    fs::remove_file(dir.path().join("target.md")).unwrap();
    json_success(
        &dir,
        &[
            "purge",
            "--raw-hash",
            &raw_hash,
            "--reason",
            "privacy",
            "--yes",
        ],
    );
    let store = ObjectStore::new(&kio_dir);
    for hash in target_units {
        assert!(
            !store
                .content_path(ContentObjectKind::NormalizedUnit, &hash)
                .unwrap()
                .exists()
        );
    }
    for hash in survivor_units {
        assert!(
            store
                .content_path(ContentObjectKind::NormalizedUnit, &hash)
                .unwrap()
                .exists()
        );
    }
}

#[test]
fn ct4_purge_rejects_forged_target_ledger_row_before_deleting_survivor_chunk() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("target.md"), "target-only secret").unwrap();
    fs::write(dir.path().join("survivor.md"), "unrelated survivor content").unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--offline", "--approve"]);

    let target_raw = current_raw_for(&dir, "target.md");
    let survivor_raw = current_raw_for(&dir, "survivor.md");
    let survivor_chunk = json_success(
        &dir,
        &["search", "unrelated survivor content", "--mode", "text"],
    )["results"][0]["evidence_pointer"]["chunk_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    let repo = Repository::open(dir.path()).unwrap();
    let ledger_path = repo.kio_dir().join("index/chunks.jsonl");
    let mut forged = false;
    let rewritten = fs::read_to_string(&ledger_path)
        .unwrap()
        .lines()
        .map(|line| {
            let mut row: Value = serde_json::from_str(line).unwrap();
            if row["raw_hash"] == survivor_raw && row["chunk_id"] == survivor_chunk {
                row["raw_hash"] = json!(target_raw);
                forged = true;
            }
            serde_json::to_string(&row).unwrap()
        })
        .collect::<Vec<_>>()
        .join("\n");
    assert!(forged, "fixture must contain the survivor chunk ledger row");
    fs::write(&ledger_path, format!("{rewritten}\n")).unwrap();

    fs::remove_file(dir.path().join("target.md")).unwrap();
    let error = json_failure(
        &dir,
        &[
            "purge",
            "--raw-hash",
            &target_raw,
            "--reason",
            "privacy",
            "--yes",
        ],
        4,
    );
    assert_eq!(error["error_code"], "KIO-E-STORE-CORRUPT-001");
    assert!(
        ObjectStore::new(repo.kio_dir())
            .chunk_path(&survivor_chunk)
            .unwrap()
            .exists()
    );
    assert!(
        ObjectStore::new(repo.kio_dir())
            .object_path(ObjectKind::Raw, &target_raw)
            .unwrap()
            .exists()
    );
    assert!(
        PurgeState::new(repo.kio_dir())
            .read_tombstone(&target_raw)
            .unwrap()
            .is_none()
    );
}

#[test]
fn ct4_purge_fails_closed_on_cross_raw_reachable_manifest_reuse() {
    // The target binding is visited first.  A corrupt survivor binding then
    // reuses its manifest hash: de-duplicating before validating each binding
    // used to skip that second tuple check and could delete content still
    // named by the surviving tree.
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a-target.md"), "target-only secret").unwrap();
    fs::write(dir.path().join("z-survivor.md"), "survivor-only text").unwrap();
    json_success(&dir, &["init"]);
    json_success(&dir, &["index", "--offline", "--approve"]);

    let target_raw = current_raw_for(&dir, "a-target.md");
    let target_manifest = tree_manifest_hash_for(&dir, "a-target.md");
    let target_units = normalized_unit_pins_for(&dir, "a-target.md");
    let repo = Repository::open(dir.path()).unwrap();
    let head = repo.head_commit_hash().unwrap().unwrap();
    let mut forged_tree = repo
        .read_tree(&repo.read_commit(&head).unwrap().tree)
        .unwrap();
    let survivor = forged_tree
        .entries
        .iter_mut()
        .find(|entry| entry.path == "z-survivor.md")
        .unwrap();
    survivor.normalize.as_mut().unwrap().manifest_hash = target_manifest.clone();
    let store = ObjectStore::new(repo.kio_dir());
    let (tree_hash, _) = store
        .write_json(
            ObjectKind::Tree,
            &serde_json::to_value(&forged_tree).unwrap(),
        )
        .unwrap();
    let mut forged_commit = repo.read_commit(&head).unwrap();
    forged_commit.tree = tree_hash;
    forged_commit.parents = vec![head];
    forged_commit.message = "test: forged cross-raw manifest binding".to_owned();
    let (commit_hash, _) = store
        .write_json(
            ObjectKind::Commit,
            &serde_json::to_value(&forged_commit).unwrap(),
        )
        .unwrap();
    fs::write(repo.kio_dir().join("refs/heads/main"), &commit_hash).unwrap();
    fs::write(repo.kio_dir().join("HEAD"), &commit_hash).unwrap();

    fs::remove_file(dir.path().join("a-target.md")).unwrap();
    let error = json_failure(
        &dir,
        &[
            "purge",
            "--raw-hash",
            &target_raw,
            "--reason",
            "privacy",
            "--yes",
        ],
        4,
    );
    assert_eq!(error["error_code"], "KIO-E-STORE-CORRUPT-001");
    assert!(
        store
            .content_path(ContentObjectKind::Manifest, &target_manifest)
            .unwrap()
            .exists()
    );
    for unit_hash in target_units {
        assert!(
            store
                .content_path(ContentObjectKind::NormalizedUnit, &unit_hash)
                .unwrap()
                .exists()
        );
    }
    assert!(
        store
            .object_path(ObjectKind::Raw, &target_raw)
            .unwrap()
            .exists()
    );
    assert!(
        PurgeState::new(repo.kio_dir())
            .read_tombstone(&target_raw)
            .unwrap()
            .is_none()
    );
}

#[test]
fn ct4_purge_fails_closed_when_a_target_manifest_pinned_unit_is_missing() {
    let fixture = indexed_fixture();
    let kio_dir = fixture.dir.path().join(".kio");
    let unit_hash = normalized_unit_pins_for(&fixture.dir, "doc.md")
        .into_iter()
        .next()
        .unwrap();
    let unit_path = ObjectStore::new(&kio_dir)
        .content_path(ContentObjectKind::NormalizedUnit, &unit_hash)
        .unwrap();
    fs::remove_file(&unit_path).unwrap();
    fs::remove_file(fixture.dir.path().join("doc.md")).unwrap();

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
    assert_eq!(error["error_code"], "KIO-E-STORE-CORRUPT-001");
    assert!(
        ObjectStore::new(&kio_dir)
            .object_path(ObjectKind::Raw, &fixture.raw_hash)
            .unwrap()
            .exists()
    );
    assert!(
        PurgeState::new(&kio_dir)
            .read_tombstone(&fixture.raw_hash)
            .unwrap()
            .is_none()
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
    let state = PurgeState::new(fixture.dir.path().join(".kio"));
    assert!(state.read_tombstone(&fixture.raw_hash).unwrap().is_none());
    let receipt = state
        .read_erase_receipt(&fixture.raw_hash)
        .unwrap()
        .unwrap();
    assert_eq!(receipt.tail().in_commit, output["purged_in_commit"]);
    assert!(state.read_journal().unwrap().is_none());

    let pointer = fixture.pointer.to_string();
    assert_eq!(
        json_failure(&fixture.dir, &["open", &pointer], 4)["error_code"],
        "KIO-E-PURGE-NOT-FOUND-001"
    );
    let head = fs::read(fixture.dir.path().join(".kio/HEAD")).unwrap();
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
        fs::read(fixture.dir.path().join(".kio/HEAD")).unwrap(),
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
    ObjectStore::new(dir.path().join(".kio"))
        .inspect_content_object(ContentObjectKind::Image, &image_a)
        .unwrap();
}

/// Purge one document that went through the online lane end to end, so the
/// image-object and embedding-object surfaces are the ones the adapters
/// actually wrote rather than test-authored stand-ins.
///
/// This is the fixture shape no purge test had: every other one indexes
/// `--offline`, which never buys a vector, so `objects/embeddings/` was always
/// empty and the orphan-embedding deletion at the top of
/// `delete_derived_surfaces` never ran against a real object. It could not
/// succeed when it did — that namespace is keyed by the vector's IDENTITY hash
/// (what the vector is OF), and `ObjectStore::remove_content` verifies a leaf
/// by re-hashing its BYTES against the key, and an embedding's bytes also carry
/// the vector body. So a perfectly healthy object was reported as
/// `KIO-E-STORE-CORRUPT-001`, aborting the phase and leaving every purge of an
/// embedded document permanently `purge_incomplete` — with the image object
/// neither deleted nor deliberately preserved, because the abort happened
/// before that phase was reached at all.
#[test]
fn ct4_purge_deletes_image_and_embedding_objects_of_an_embedded_document() {
    let fixture = embedded_image_fixture();
    let kio_dir = fixture.dir.path().join(".kio");
    let image_path = fanout_path(kio_dir.join("objects/image"), &fixture.image_hash).unwrap();
    assert!(image_path.exists());
    fs::remove_file(fixture.dir.path().join("figures.pdf")).unwrap();

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
    assert!(output.get("error_code").is_none());
    assert_eq!(output["deleted_counts"]["image_objects"], 1);
    // The image is this document's alone, so it is deleted rather than kept as
    // a shared artifact — both counters were 0 while the bug was live.
    assert_eq!(output["shared_artifacts_preserved"]["image_objects"], 0);
    assert!(
        output["deleted_counts"]["sqlite_orphan_embeddings"]
            .as_u64()
            .unwrap()
            >= 1
    );

    // R25-6: the vector must stop existing in `objects/embeddings/` too, or the
    // next `repair rebuild-db` replays the purged vector back into the index.
    let store = ObjectStore::new(&kio_dir);
    assert!(
        store
            .inspect_content_object(ContentObjectKind::Image, &fixture.image_hash)
            .is_err()
    );
    assert!(!image_path.exists());
    for hash in &fixture.embedding_hashes {
        assert!(store.read_embedding(hash).is_err(), "embedding={hash}");
    }
    assert!(cas_leaf_hashes(&kio_dir, "image").is_empty());
    assert!(cas_leaf_hashes(&kio_dir, "embeddings").is_empty());
    assert!(tombstone_path(&kio_dir, &fixture.raw_hash).exists());
    assert!(!kio_dir.join("purge/in-progress.json").exists());
}

/// The OFFLINE lane's counterpart to the test above, and the only one that can
/// reach an image *embedding* object.
///
/// `embedded_image_fixture` uses the adopted ONLINE adapter, which declares no
/// `image_object` capability and therefore writes no `image_vec` rows and no
/// `target_type='image'` object — it covers image OBJECTS and CHUNK vectors and
/// stops there. The offline adapter is the one that declares the capability, so
/// only this fixture owns the full set 04 §4.3 creates: an image object, chunk
/// vectors, AND a vector OF the image.
///
/// The number that regressed silently is `sqlite_vectors`. Nothing in the suite
/// had ever read it — every other purge fixture indexes `--offline`, which buys
/// no vectors at all, so it was 0 everywhere and an undercount was invisible by
/// construction.
#[test]
fn ct4_purge_deletes_the_image_vector_of_a_locally_embedded_document() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("figures.pdf"), "%PDF-1.4\ntest\n").unwrap();
    json_success(&dir, &["init"]);
    let local = [("KIO_EVAL_DETERMINISTIC_EMBED", "scale-v3")];
    let both = [
        ("KIO_EVAL_DETERMINISTIC_EMBED", "scale-v3"),
        ("KIO_TEST_MISTRAL_OCR", "mock_link_image"),
    ];
    json_success_with_env(&dir, &["index", "--approve"], &local);
    json_success_with_env(&dir, &["batch", "resume"], &both);
    // The image-embedding pass runs on the next index, once the normalized body
    // (and therefore the image reference it cites) exists.
    json_success_with_env(&dir, &["index"], &local);

    let kio_dir = dir.path().join(".kio");
    assert_eq!(cas_leaf_hashes(&kio_dir, "image").len(), 1);
    let embeddings_before = cas_leaf_hashes(&kio_dir, "embeddings");
    assert!(
        embeddings_before.len() >= 2,
        "fixture must own chunk vectors AND an image vector: {embeddings_before:?}"
    );

    let raw_hash = current_raw_for(&dir, "figures.pdf");
    fs::remove_file(dir.path().join("figures.pdf")).unwrap();
    let output = json_success_with_env(
        &dir,
        &[
            "purge",
            "--raw-hash",
            &raw_hash,
            "--reason",
            "legal",
            "--yes",
        ],
        &local,
    );

    assert_eq!(output["status"], "purged", "{output}");
    assert_eq!(output["deleted_counts"]["image_objects"], 1, "{output}");
    // Both vec0 tables in one counter: two chunk vectors plus the one image
    // vector. Folding only `deleted_chunk_vectors` here reported 2.
    assert_eq!(
        output["deleted_counts"]["sqlite_vectors"],
        embeddings_before.len(),
        "sqlite_vectors must count image_vec rows too: {output}"
    );

    // R25-6: the vector must stop existing in `objects/embeddings/` as well, or
    // `repair rebuild-db` replays the purged figure's vector straight back into
    // `image_vec`.
    assert!(
        cas_leaf_hashes(&kio_dir, "embeddings").is_empty(),
        "{output}"
    );
    assert!(cas_leaf_hashes(&kio_dir, "image").is_empty(), "{output}");
    assert!(tombstone_path(&kio_dir, &raw_hash).exists());
}

#[test]
fn ct4_purge_acquires_publication_lock_before_publishing_barrier() {
    let fixture = indexed_fixture();
    fs::remove_file(fixture.dir.path().join("doc.md")).unwrap();
    fs::write(
        fixture.dir.path().join(".kio/purge-publication.lock"),
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
    assert_eq!(error["error_code"], "KIO-E-STORE-LOCKED-001");
    assert!(
        ObjectStore::new(fixture.dir.path().join(".kio"))
            .inspect_object(ObjectKind::Raw, &fixture.raw_hash)
            .is_ok()
    );
    assert!(
        !fixture
            .dir
            .path()
            .join(".kio/purge/in-progress.json")
            .exists()
    );
}

#[test]
fn ct4_purge_cleans_tombstoned_ingest_orphan_before_live_copy_warning() {
    // Step4b P2-A §R ruling #1: this is a RE-purge of an already-active
    // tombstone (`BeginOutcome::AlreadyComplete` — LC59), which short-circuits
    // before any phase-machine execution, so it is idempotent success with a
    // `working_tree_warning`, not the retired `KIO-E-PURGE-WORKING-COPY-001`
    // hard block this test used to exercise.
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
        .join(".kio/objects/raw/.ingest-killed-after-purge");
    fs::write(&orphan, raw_bytes).unwrap();
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
    assert_eq!(output["working_tree_warning"]["live_alias_count"], 1);
    assert!(!orphan.exists());
    assert!(tombstone_path(&fixture.dir.path().join(".kio"), &fixture.raw_hash).exists());
}

#[test]
fn ct4_purge_faults_publish_no_prebarrier_state_and_resume_every_visible_phase() {
    let prepared = indexed_fixture();
    fs::remove_file(prepared.dir.path().join("doc.md")).unwrap();
    let error = kio(
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
    .env("KIO_TEST_PURGE_FAIL_AFTER_PHASE", "prepared")
    .arg("--json")
    .assert()
    .code(1)
    .get_output()
    .stderr
    .clone();
    let error: Value = serde_json::from_slice(&error).unwrap();
    assert_eq!(error["error_code"], "KIO-E-STORE-IO-001");
    assert!(
        ObjectStore::new(prepared.dir.path().join(".kio"))
            .inspect_object(ObjectKind::Raw, &prepared.raw_hash)
            .is_ok()
    );
    assert!(
        !prepared
            .dir
            .path()
            .join(".kio/purge/in-progress.json")
            .exists()
    );

    // LC46/LC47: the journal's phase vocabulary is now `prepared -> tombstoned
    // -> deleted -> committed`. `tombstoned` is the first point at which the
    // barrier is visible (marker durable, LC49) — a fault injected earlier, at
    // `prepared_visible` (before any marker exists), has nothing yet to hide
    // and is intentionally not exercised by this "content must already be
    // hidden on resume" loop.
    for phase in ["tombstoned", "deleted", "committed"] {
        let fixture = indexed_fixture();
        fs::remove_file(fixture.dir.path().join("doc.md")).unwrap();
        let partial = json_partial_with_fault(&fixture.dir, &fixture.raw_hash, phase);
        assert_eq!(partial["error_code"], "KIO-E-PURGE-INCOMPLETE-001");
        assert_eq!(partial["status"], "purge_incomplete");
        assert!(!partial.to_string().contains(&fixture.raw_hash));
        assert!(
            fixture
                .dir
                .path()
                .join(".kio/purge/in-progress.json")
                .exists()
        );
        // §I (LC52-56, this session): search's read barrier now rejects the
        // WHOLE command outright while a journal is active/visible, rather
        // than silently degrading to a success response with the blocked
        // content merely filtered out of `results` (the old per-raw_hash-only
        // `purge_blocks_raw` behavior this loop originally pinned). A
        // single-scope search with every scope excluded for this one reason
        // is promoted to the command-level retryable error (mirrors
        // KIO-E-INDEX-REBUILDING-001's own all-excluded promotion).
        let blocked = json_failure(
            &fixture.dir,
            &["search", "needle-purge-content", "--mode", "text"],
            3,
        );
        assert_eq!(blocked["error_code"], "KIO-E-PURGE-JOURNAL-ACTIVE-001");
        assert!(!blocked.to_string().contains("needle-purge-content"));
        let raw_uri = format!("kio://{}/object/raw/{}", fixture.scope_id, fixture.raw_hash);
        let read = kio(&fixture.dir, &["open", &raw_uri, "--json"])
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
        assert!(
            !fixture
                .dir
                .path()
                .join(".kio/purge/in-progress.json")
                .exists()
        );
    }
}
