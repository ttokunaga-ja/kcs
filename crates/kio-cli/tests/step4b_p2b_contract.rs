//! Contract tests for `tasks/step4b-contract-tests-p2b.md` (fsck expansion /
//! evidence pointer resolve-verify-retarget, P2-B). Test names embed the PB
//! number they lock down. §M/§L's display-field pieces (PB34-36) remain
//! outside this pass's scope (they need `path_at_commit`/`heading_path`
//! output fields `resolve_pointer_for_cli` does not produce yet). This file
//! does not fabricate coverage for those.

use std::fs;
use std::path::Path;

use assert_cmd::Command;
use kio_core::cas::{hash_bytes, ContentObjectKind, ObjectKind, ObjectStore};
use kio_core::dag::{build_tree, CommitObject, CommitStats, CommitType, NormalizeRef, TreeEntry};
use kio_core::purge::{PurgeReason, PurgeState, TombstoneMode};
use kio_core::scope::Repository;
use kio_index::registry::{RegistryDb, RegistryEntry};
use serde_json::Value;
use tempfile::TempDir;

// ---------------------------------------------------------------------------
// Harness (mirrors crates/kio-cli/tests/step4_verify.rs / step3_p0_contract.rs).
// ---------------------------------------------------------------------------

fn kio(dir: &TempDir, args: &[&str]) -> Command {
    let mut command = Command::cargo_bin("kio").unwrap();
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
    let output = kio(dir, args)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

/// Runs and returns `(exit_code, parsed_json)`, reading stdout on success and
/// stderr on failure.
fn run(dir: &TempDir, args: &[&str]) -> (i32, Value) {
    let output = kio(dir, args).arg("--json").output().unwrap();
    let code = output.status.code().unwrap();
    // A non-zero exit does NOT imply the JSON landed on stderr: several
    // commands (`repair --verify-objects` findings, search partial failure,
    // this session's `evidence verify` status responses) succeed at the
    // `run()` level and request a non-zero process exit via a private
    // `__exit_code` marker while still printing their JSON body to STDOUT
    // (main.rs's `take_exit_override`) — only a genuine `Err(KioError)`
    // prints to stderr. Prefer whichever stream is non-empty.
    let stream: &[u8] = if !output.stdout.is_empty() {
        &output.stdout
    } else {
        &output.stderr
    };
    (code, serde_json::from_slice(stream).unwrap())
}

fn registry_path(dir: &TempDir) -> std::path::PathBuf {
    dir.path().join(".test-data/kio/scope-registry.sqlite")
}

/// init + index + search, returning (dir, evidence_pointer, evidence_uri).
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

fn kio_dir(dir: &TempDir) -> std::path::PathBuf {
    dir.path().join(".kio")
}

/// Fixtures that append a lifecycle event directly via `PurgeState` (bypassing
/// the `kio purge` CLI, which would otherwise also resync `index_metadata.
/// last_lifecycle_epoch`) must resync it explicitly afterward, or the LC45
/// read-command-entry check (`check_index_generation_current`) correctly —
/// if inconveniently for a hand-built fixture — refuses every subsequent read
/// command with `KIO-E-INDEX-REBUILDING-001` until it does. `repair
/// --rebuild-db` is the standard resync path (PB28).
fn resync_index_metadata(dir: &TempDir) {
    success(dir, &["repair", "--rebuild-db"]);
}

/// Fan-out CAS path for a raw content-addressed object under
/// `objects/<kind_dir>/`, independent of `hash`'s real correspondence to the
/// bytes at that path (used to write deliberately-corrupt fixtures).
fn content_path(kio_dir: &Path, kind_dir: &str, hash: &str) -> std::path::PathBuf {
    let digest = hash.strip_prefix("sha256:").unwrap();
    kio_dir
        .join("objects")
        .join(kind_dir)
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(digest)
}

fn write_content_bytes(kio_dir: &Path, kind_dir: &str, bytes: &[u8]) -> String {
    let hash = hash_bytes(bytes);
    let path = content_path(kio_dir, kind_dir, &hash);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, bytes).unwrap();
    hash
}

// ===========================================================================
// §A/§B — fsck verification-target expansion (U39/U40).
// ===========================================================================

/// PB01 (a)(c)(f): a well-formed embedding object (declared dimensions ==
/// vector length, all finite, digest matches) passes verification cleanly.
#[test]
fn pb01_embedding_valid_vector_passes_verification() {
    let (dir, ..) = fixture();
    write_content_bytes(
        &kio_dir(&dir),
        ContentObjectKind::Embedding.directory(),
        serde_json::to_string(&serde_json::json!({"dimensions": 3, "vector": [0.1, 0.2, 0.3]}))
            .unwrap()
            .as_bytes(),
    );
    let output = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(output["status"], "ok", "{output}");
    assert_eq!(output["checked"]["embeddings"], 1, "{output}");
}

/// PB01 (b): declared `dimensions` does not match `vector.len()` — a finding.
#[test]
fn pb01_embedding_length_mismatch_is_a_finding() {
    let (dir, ..) = fixture();
    write_content_bytes(
        &kio_dir(&dir),
        ContentObjectKind::Embedding.directory(),
        serde_json::to_string(&serde_json::json!({"dimensions": 3, "vector": [0.1, 0.2]}))
            .unwrap()
            .as_bytes(),
    );
    let (code, output) = run(&dir, &["repair", "--verify-objects"]);
    assert_eq!(code, 3, "{output}");
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "embedding_corrupt"));
}

/// PB01 (d)/(e): a non-finite (`NaN`/`Infinity`) vector element is a finding
/// — standard JSON forbids these literals, so a byte-level-corrupt embedding
/// object fails to parse at all (still `embedding_corrupt`, PB01 only
/// requires the finding, not a specific internal code path).
#[test]
fn pb01_embedding_non_finite_vector_element_is_a_finding() {
    let (dir, ..) = fixture();
    write_content_bytes(
        &kio_dir(&dir),
        ContentObjectKind::Embedding.directory(),
        br#"{"dimensions": 1, "vector": [NaN]}"#,
    );
    let (code, output) = run(&dir, &["repair", "--verify-objects"]);
    assert_eq!(code, 3, "{output}");
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "embedding_corrupt"));
}

/// PB01 (g): stored bytes do not hash to the object's own leaf name — a
/// finding (digest mismatch).
#[test]
fn pb01_embedding_digest_mismatch_is_a_finding() {
    let (dir, ..) = fixture();
    let hash = write_content_bytes(
        &kio_dir(&dir),
        ContentObjectKind::Embedding.directory(),
        br#"{"dimensions": 1, "vector": [0.5]}"#,
    );
    let path = content_path(
        &kio_dir(&dir),
        ContentObjectKind::Embedding.directory(),
        &hash,
    );
    fs::write(&path, br#"{"dimensions": 1, "vector": [0.9]}"#).unwrap();
    let (code, output) = run(&dir, &["repair", "--verify-objects"]);
    assert_eq!(code, 3, "{output}");
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "embedding_corrupt"));
}

/// PB02: manifest and toollock CAS objects join the fsck verification
/// closure — a valid one is counted, a digest-corrupt one is a finding.
#[test]
fn pb02_manifest_and_toollock_join_the_verification_closure() {
    let (dir, ..) = fixture();
    write_content_bytes(
        &kio_dir(&dir),
        ContentObjectKind::Manifest.directory(),
        br#"{"kind":"manifest-fixture"}"#,
    );
    let toollock_hash = write_content_bytes(
        &kio_dir(&dir),
        ContentObjectKind::Toollock.directory(),
        br#"{"kind":"toollock-fixture"}"#,
    );
    let toollock_path = content_path(
        &kio_dir(&dir),
        ContentObjectKind::Toollock.directory(),
        &toollock_hash,
    );
    fs::write(&toollock_path, br#"{"kind":"corrupted-in-place"}"#).unwrap();

    let (code, output) = run(&dir, &["repair", "--verify-objects"]);
    assert_eq!(code, 3, "{output}");
    // PB04: `fixture()`'s own `kio index` now durably CAS-writes ITS
    // normalized instance's genuine manifest object too (NormalizeRef's new
    // `manifest_hash` field, computed at index time) — one real manifest
    // from the fixture's indexing plus this test's own synthetic
    // `manifest-fixture` object above, so the closure now counts 2, not 1.
    assert_eq!(output["checked"]["manifests"], 2, "{output}");
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "toollock_corrupt"));
}

/// PB03 [regression-lock]: chunk exact-span/text_hash mismatch is still
/// detected exactly as before this session's changes.
#[test]
fn pb03_regression_chunk_span_mismatch_still_a_finding() {
    let (dir, pointer, _) = fixture();
    let chunk_hash = pointer["chunk_hash"].as_str().unwrap();
    let store = ObjectStore::new(kio_dir(&dir));
    let chunk_path = store.chunk_path(chunk_hash).unwrap();
    let mut chunk: Value = serde_json::from_slice(&fs::read(&chunk_path).unwrap()).unwrap();
    // Keep `text`/`text_hash` mutually consistent (so `ChunkObject::validate`'s
    // own CAS-level identity check still passes and this reaches the span
    // comparison as `chunk_span_mismatch`, not an earlier `chunk_corrupt`),
    // but inconsistent with the normalized unit's actual [byte_start,
    // byte_end) span.
    let tampered = "tampered text that does not match the span (byte length differs)";
    chunk["text"] = serde_json::json!(tampered);
    chunk["text_hash"] = serde_json::json!(hash_bytes(tampered.as_bytes()));
    // Rewrite the object directly (bypassing CAS identity re-derivation) so
    // the exact on-disk bytes disagree with the normalized span.
    fs::write(&chunk_path, serde_json::to_vec(&chunk).unwrap()).unwrap();
    let (code, output) = run(&dir, &["repair", "--verify-objects"]);
    assert_eq!(code, 3, "{output}");
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "chunk_span_mismatch"));
}

// ===========================================================================
// §C — names.jsonl (U41).
// ===========================================================================

fn names_jsonl_path(dir: &TempDir) -> std::path::PathBuf {
    kio_dir(dir).join("refs/tags-v1/names.jsonl")
}

/// PB07: `kio tag` appends a names.jsonl row whose digest64 matches the
/// recomputed digest of the logical name; a corrupted digest64 is a finding.
#[test]
fn pb07_names_jsonl_schema_and_digest_recompute() {
    let (dir, ..) = fixture();
    success(&dir, &["tag", "release-1"]);
    let text = fs::read_to_string(names_jsonl_path(&dir)).unwrap();
    let line = text.lines().next().unwrap();
    let record: Value = serde_json::from_str(line).unwrap();
    assert_eq!(record["logical_name"], "release-1");
    assert!(record["digest64"].as_str().unwrap().len() == 64);

    // Baseline: a freshly-tagged scope has no findings.
    let clean = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(clean["status"], "ok", "{clean}");

    // Corrupt digest64 -> finding.
    let mut corrupted = record.clone();
    corrupted["digest64"] = serde_json::json!("0".repeat(64));
    fs::write(
        names_jsonl_path(&dir),
        format!("{}\n", serde_json::to_string(&corrupted).unwrap()),
    )
    .unwrap();
    let (code, output) = run(&dir, &["repair", "--verify-objects"]);
    assert_eq!(code, 3, "{output}");
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "names_jsonl_corrupt"));
}

/// PB08: only the FINAL line may be a torn (truncated) tail — tolerated. A
/// malformed line that is NOT the final one is corruption.
#[test]
fn pb08_names_jsonl_torn_tail_tolerated_mid_malformed_rejected() {
    let (dir, ..) = fixture();
    success(&dir, &["tag", "release-1"]);
    let good_line = fs::read_to_string(names_jsonl_path(&dir)).unwrap();
    let good_line = good_line.trim_end();

    // (a) torn tail: append a final line with no trailing newline that is
    // itself truncated mid-object.
    fs::write(
        names_jsonl_path(&dir),
        format!("{good_line}\n{{\"digest64\":\"ab"),
    )
    .unwrap();
    let torn = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(
        torn["status"], "ok",
        "torn tail must not be a finding: {torn}"
    );

    // (b) malformed line NOT last: a torn line followed by a valid line.
    fs::write(
        names_jsonl_path(&dir),
        format!("{{\"digest64\":\"ab\n{good_line}\n"),
    )
    .unwrap();
    let (code, output) = run(&dir, &["repair", "--verify-objects"]);
    assert_eq!(code, 3, "{output}");
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "names_jsonl_corrupt"));
}

/// PB09: a canonical tag ref with no corresponding names.jsonl row is
/// corruption; the reverse (a names row with no ref, tag-delete residue) is
/// normal.
#[test]
fn pb09_canonical_ref_names_correspondence_is_asymmetric() {
    let (dir, ..) = fixture();
    success(&dir, &["tag", "release-1"]);

    // (b) ref-less names row (simulated tag deletion: remove only the ref)
    // must NOT be a finding.
    let canonical_dir = kio_dir(&dir).join("refs/tags-v1");
    for entry in fs::read_dir(&canonical_dir).unwrap().flatten() {
        if entry.file_name() != "names.jsonl" {
            fs::remove_file(entry.path()).unwrap();
        }
    }
    let ref_less = success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(
        ref_less["status"], "ok",
        "a names row with no ref must be normal: {ref_less}"
    );

    // (a) a ref with no names row IS corruption: recreate a canonical ref
    // pointing at HEAD that names.jsonl never recorded.
    let head = fs::read_to_string(kio_dir(&dir).join("HEAD")).unwrap();
    let orphan_leaf = format!("tag-{}", "1".repeat(64));
    fs::write(canonical_dir.join(&orphan_leaf), head.trim()).unwrap();
    let (code, output) = run(&dir, &["repair", "--verify-objects"]);
    assert_eq!(code, 3, "{output}");
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "names_jsonl_corrupt"));
}

// ===========================================================================
// §E — `--prune-orphans` (U43). PB14/16/17 and two of PB15's four blockers
// are NOT implemented this session (see `prune_orphans`'s doc comment in
// src/verify_objects.rs) — not tested here.
// ===========================================================================

/// PB12: `repair` accepts exactly one of `--rebuild-db`/`--verify-objects`/
/// `--registry-prune`; `--prune-orphans` is a `--verify-objects`-only
/// modifier.
#[test]
fn pb12_prune_orphans_flag_parsing() {
    let (dir, ..) = fixture();
    let accepted = success(&dir, &["repair", "--verify-objects", "--prune-orphans"]);
    assert_eq!(accepted["status"], "ok", "{accepted}");

    kio(&dir, &["repair", "--prune-orphans"])
        .arg("--json")
        .assert()
        .code(2);
    kio(&dir, &["repair", "--rebuild-db", "--prune-orphans"])
        .arg("--json")
        .assert()
        .code(2);
}

/// PB13: an orphan prepared/image object (referenced by no live manifest) is
/// deleted by `--prune-orphans`.
#[test]
fn pb13_prune_orphans_deletes_unreferenced_prepared_and_image() {
    let (dir, ..) = fixture();
    let prepared_hash = write_content_bytes(
        &kio_dir(&dir),
        ContentObjectKind::Prepared.directory(),
        b"orphan prepared bytes never referenced by any manifest",
    );
    let image_hash = write_content_bytes(
        &kio_dir(&dir),
        ContentObjectKind::Image.directory(),
        b"orphan image bytes never referenced by any manifest",
    );
    let store = ObjectStore::new(kio_dir(&dir));
    assert!(store
        .inspect_content_accounted(ContentObjectKind::Prepared, &prepared_hash)
        .is_ok());

    let output = success(&dir, &["repair", "--verify-objects", "--prune-orphans"]);
    assert_eq!(output["status"], "ok", "{output}");
    assert_eq!(output["prune_orphans"]["status"], "pruned", "{output}");
    assert_eq!(
        output["prune_orphans"]["pruned_prepared_count"], 1,
        "{output}"
    );
    assert_eq!(output["prune_orphans"]["pruned_image_count"], 1, "{output}");
    assert!(store
        .inspect_content_accounted(ContentObjectKind::Prepared, &prepared_hash)
        .is_err());
    assert!(store
        .inspect_content_accounted(ContentObjectKind::Image, &image_hash)
        .is_err());
}

/// PB15 (partial — active purge journal only, one of four blocker
/// conditions): `--prune-orphans` refuses to run while a purge journal is
/// active, even though an orphan exists that would otherwise be pruned.
#[test]
fn pb15_prune_orphans_blocked_by_active_purge_journal() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    write_content_bytes(
        &kio_dir(&dir),
        ContentObjectKind::Prepared.directory(),
        b"orphan that must survive because the journal blocks pruning",
    );
    let purge = PurgeState::new(kio_dir(&dir));
    purge
        .begin(
            vec![raw_hash],
            PurgeReason::Legal,
            TombstoneMode::Default,
            "user",
            "2026-07-13T00:00:00Z",
            1,
            hash_bytes(b"planned purge commit placeholder"),
            hash_bytes(b"planned purge closure placeholder"),
            kio_core::scope::new_ulid(dir.path()),
        )
        .unwrap();

    let (code, output) = run(&dir, &["repair", "--verify-objects", "--prune-orphans"]);
    // The underlying verify pass itself reports the active journal as a
    // `purge_incomplete` finding (exit 3) before prune-orphans would even run.
    assert_eq!(code, 3, "{output}");
    assert!(output["remaining_findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "purge_incomplete"));
    assert!(output.get("prune_orphans").is_none(), "{output}");
}

// ===========================================================================
// §G — SQLite schema-change regression locks (U45).
// ===========================================================================

/// PB20 [regression-lock]: `migrate_legacy_chunk_config_column` remains the
/// ONLY in-place `ALTER TABLE` migration function for sqlite.db — a static
/// source check, not a CLI run.
#[test]
fn pb20_regression_single_documented_in_place_migration_function() {
    let source = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../kio-index/src/fts.rs"
    ))
    .unwrap();
    let alter_table_fns = source
        .lines()
        .filter(|line| line.contains("ALTER TABLE"))
        .count();
    assert!(
        alter_table_fns > 0,
        "expected the known chunk_config_generations migration to still exist"
    );
    assert!(
        source.contains("fn migrate_legacy_chunk_config_column"),
        "the one documented in-place migration function must still exist"
    );
}

// ===========================================================================
// §H — registry live-duplicate fail-closed + `--registry-prune` (U46).
// ===========================================================================

/// PB21/22: a scope_id registered against two distinct LIVE `.kio` with
/// DIFFERENT `last_seen_at` (not a tie) is fail-closed with the new
/// `KIO-E-REGISTRY-DUP-001` — the old implementation only caught a
/// `last_seen_at` tie and silently auto-selected the newest otherwise.
#[test]
fn pb21_pb22_live_duplicate_fails_closed_even_without_a_last_seen_tie() {
    let (dir_a, pointer, _) = fixture();
    let scope_id = pointer["scope_id"].as_str().unwrap().to_owned();

    let dir_b = tempfile::tempdir().unwrap();
    kio(&dir_b, &["init"]).arg("--json").assert().success();
    let scope_path = dir_b.path().join(".kio/scope.json");
    let mut scope: Value = serde_json::from_slice(&fs::read(&scope_path).unwrap()).unwrap();
    scope["scope_id"] = serde_json::json!(scope_id);
    fs::write(&scope_path, serde_json::to_vec_pretty(&scope).unwrap()).unwrap();

    let registry = RegistryDb::open(registry_path(&dir_a)).unwrap();
    registry
        .upsert(&RegistryEntry {
            scope_id: scope_id.clone(),
            kio_path: kio_dir(&dir_a).display().to_string(),
            root_path: dir_a.path().display().to_string(),
            participates_in_global_search: true,
            indexed: true,
            last_seen_at: "2020-01-01T00:00:00Z".to_owned(),
        })
        .unwrap();
    registry
        .upsert(&RegistryEntry {
            scope_id: scope_id.clone(),
            kio_path: dir_b.path().join(".kio").display().to_string(),
            root_path: dir_b.path().display().to_string(),
            participates_in_global_search: true,
            indexed: true,
            // Deliberately NEWER, not a tie — the old code silently picked
            // this one; PB21 requires fail-closed regardless.
            last_seen_at: "2099-01-01T00:00:00Z".to_owned(),
        })
        .unwrap();

    let mut orphan_pointer = pointer.clone();
    orphan_pointer["scope_path"] =
        serde_json::json!(dir_a.path().join("gone/.kio").display().to_string());
    let pointer_json = serde_json::to_string(&orphan_pointer).unwrap();
    let (code, output) = run(&dir_a, &["evidence", "verify", &pointer_json]);
    // PB54: registry_duplicate is exit 3 regardless of --strict — a
    // structured status (body still prints), but always retryable-flagged,
    // unlike scope_unreachable's exit-0-without-strict (PB53).
    assert_eq!(
        code, 3,
        "registry_duplicate is exit 3 unconditionally: {output}"
    );
    assert_eq!(output["status"], "registry_duplicate", "{output}");
    assert_eq!(output["error_code"], "KIO-E-REGISTRY-DUP-001", "{output}");
}

/// PB25: `kio repair --registry-prune` deletes only registry rows whose
/// `.kio` is unreachable, never a live (even if duplicated) row.
#[test]
fn pb25_registry_prune_removes_only_unreachable_rows() {
    let (dir, ..) = fixture();
    let registry = RegistryDb::open(registry_path(&dir)).unwrap();
    registry
        .upsert(&RegistryEntry {
            scope_id: "scope_deadbeef".to_owned(),
            kio_path: dir.path().join("nonexistent/.kio").display().to_string(),
            root_path: dir.path().join("nonexistent").display().to_string(),
            participates_in_global_search: true,
            indexed: true,
            last_seen_at: "2020-01-01T00:00:00Z".to_owned(),
        })
        .unwrap();
    assert_eq!(
        registry.all_entries().unwrap().len(),
        2,
        "fixture's own scope + the stale one"
    );

    let output = success(&dir, &["repair", "--registry-prune"]);
    assert_eq!(output["pruned_count"], 1, "{output}");
    let remaining = registry.all_entries().unwrap();
    assert_eq!(
        remaining.len(),
        1,
        "only the unreachable row must be pruned"
    );
    assert_ne!(
        remaining[0].scope_id, "scope_deadbeef",
        "the live fixture scope must survive; the unreachable stale row must not"
    );
}

// ===========================================================================
// §J — rebuild-db index_metadata (U144, §Z ruling 4).
// ===========================================================================

/// PB28: `kio repair --rebuild-db` initializes `index_metadata.
/// last_lifecycle_epoch` to the CURRENT lifecycle-epoch counter value (not
/// the column's `DEFAULT 0`), atomically with the rebuild.
#[test]
fn pb28_rebuild_db_initializes_last_lifecycle_epoch_to_current_value() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();

    // Bump the lifecycle-epoch counter past 0 via a real, COMPLETE purge, so
    // `last_lifecycle_epoch` would be wrong if left at DEFAULT 0. The
    // working-tree source file must be gone first — otherwise purge reports
    // `purge_incomplete` (its working-tree-alias guard, 09 §5.3) rather than
    // completing, and never advances the tombstone all the way.
    fs::remove_file(dir.path().join("evidence.md")).unwrap();
    success(
        &dir,
        &[
            "purge",
            "--raw-hash",
            raw_hash,
            "--reason",
            "legal",
            "--yes",
        ],
    );
    let before = fs::read_to_string(kio_dir(&dir).join("tombstones/lifecycle-epoch")).unwrap();
    let before: u64 = before.trim().parse().unwrap();
    assert!(
        before > 0,
        "purge must have advanced the lifecycle-epoch counter"
    );

    success(&dir, &["repair", "--rebuild-db"]);

    let db_path = kio_dir(&dir).join("index/sqlite.db");
    let conn = rusqlite::Connection::open(db_path).unwrap();
    let metadata = kio_index::fts::read_index_metadata(&conn).unwrap().unwrap();
    assert_eq!(
        metadata.last_lifecycle_epoch, before,
        "must be the current counter value, not DEFAULT 0"
    );
}

// ===========================================================================
// §N — shallow-commit strict downgrade (U51). tree_v1/manifest_missing
// reasons are unreachable this session (deferred prerequisites) and are not
// asserted here.
// ===========================================================================

/// PB39 [regression-lock]: non-strict shallow-commit resolution stays
/// `alive` with `commit_shallow: true` (tree-dependent steps skipped).
#[test]
fn pb39_regression_shallow_commit_resolves_alive_non_strict() {
    let (dir, pointer, _) = fixture();
    let repo = Repository::open(dir.path()).unwrap();
    let commit = repo
        .read_commit(pointer["commit"].as_str().unwrap())
        .unwrap();
    let store = ObjectStore::new(kio_dir(&dir));
    fs::remove_file(store.object_path(ObjectKind::Tree, &commit.tree).unwrap()).unwrap();
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let output = success(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(output["status"], "alive");
    assert_eq!(output["details"]["commit_shallow"], true);
}

/// PB40/41: `--strict` downgrades a shallow-commit resolution from `alive`
/// to `unverifiable` with `reason: "commit_shallow"`, exit 3 (retryable —
/// distinct from the exit-4 reasons, which are unreachable this session).
#[test]
fn pb40_pb41_strict_shallow_commit_downgrades_to_unverifiable_exit_three() {
    let (dir, pointer, _) = fixture();
    let repo = Repository::open(dir.path()).unwrap();
    let commit = repo
        .read_commit(pointer["commit"].as_str().unwrap())
        .unwrap();
    let store = ObjectStore::new(kio_dir(&dir));
    fs::remove_file(store.object_path(ObjectKind::Tree, &commit.tree).unwrap()).unwrap();
    let pointer_json = serde_json::to_string(&pointer).unwrap();

    let (code, output) = run(&dir, &["evidence", "verify", &pointer_json, "--strict"]);
    assert_eq!(code, 3, "{output}");
    assert_eq!(output["status"], "unverifiable", "{output}");
    assert_eq!(output["details"]["reason"], "commit_shallow", "{output}");
}

// ===========================================================================
// §O — decisive entry selection (U52), verify side only (open/view side is
// P2-A's `resolve_pointer_for_cli`, out of this session's scope).
// ===========================================================================

/// PB44 (verify side): zero tree entries name the pointer's raw_hash at this
/// commit — short-circuits directly to `KIO-E-STORE-CORRUPT-001`, never
/// consulting the tombstone/erase-receipt markers.
#[test]
fn pb44_verify_side_no_matching_entry_short_circuits_to_store_corrupt() {
    let (dir, mut pointer, _) = fixture();
    pointer["raw_hash"] = serde_json::json!(hash_bytes(
        b"content that was never part of any commit's tree"
    ));
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let (code, output) = run(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(code, 4, "{output}");
    assert_eq!(output["error_code"], "KIO-E-STORE-CORRUPT-001", "{output}");
}

// ===========================================================================
// §P — procedure 6a's unit-status check (U54), the part reachable without
// `normalize.manifest_hash` (§B's deferred prerequisite).
// ===========================================================================

/// PB45 (b): a chunk whose backing unit is not `status: done` in the tree
/// entry's own normalized-instance manifest resolves `not_found` — it did
/// not exist at this commit's point in time.
#[test]
fn pb45_chunk_backed_by_non_done_unit_resolves_not_found() {
    let (dir, pointer, _) = fixture();
    let repo = Repository::open(dir.path()).unwrap();
    let commit = repo
        .read_commit(pointer["commit"].as_str().unwrap())
        .unwrap();
    let tree = repo.read_tree(&commit.tree).unwrap();
    let entry = tree
        .entries
        .iter()
        .find(|entry| entry.raw_hash == pointer["raw_hash"].as_str().unwrap())
        .unwrap();
    let normalize = entry.normalize.as_ref().unwrap();

    // PB04: a v2/v3 tree entry's `normalize.manifest_hash` pins the manifest
    // object as it existed at commit time — 6a reads THAT frozen CAS object,
    // not the mutable working-copy `manifest.json` a same-gen retry may have
    // since moved on (03 §8's "unit の failed → done 遷移で変わるため, past
    // resolution only through the manifest object"). Mutate the CAS object
    // directly (fsck-style fixture — `read_content_object_bytes` does not
    // itself re-verify the digest) so this test exercises the actual
    // same-gen-retry scenario 6a guards against, not a stale read path.
    if let Some(manifest_hash) = &normalize.manifest_hash {
        let manifest_path = content_path(
            &kio_dir(&dir),
            ContentObjectKind::Manifest.directory(),
            manifest_hash,
        );
        let mut manifest: Value =
            serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
        for unit in manifest["units"].as_array_mut().unwrap() {
            unit["status"] = serde_json::json!("failed");
        }
        fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();
    } else {
        // v1 legacy fallback (no `manifest_hash`): mutate the live
        // working-copy manifest.json directly — the only source 6a's
        // lenient legacy resolution ever reads.
        // `objects/normalized_units/<raw[0:2]>/<raw[2:4]>/<raw_digest>.<tool_profile_digest>.g<gen>/manifest.json`
        // — bare (no `sha256:` prefix) digests in the instance leaf name.
        let raw_digest = entry.raw_hash.trim_start_matches("sha256:");
        let tool_digest = normalize.tool_profile_hash.trim_start_matches("sha256:");
        let instance_leaf = format!("{raw_digest}.{tool_digest}.g{}", normalize.gen);
        let manifest_path = kio_dir(&dir)
            .join("objects/normalized_units")
            .join(&raw_digest[0..2])
            .join(&raw_digest[2..4])
            .join(instance_leaf)
            .join("manifest.json");
        let mut manifest: Value =
            serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
        for unit in manifest["units"].as_array_mut().unwrap() {
            unit["status"] = serde_json::json!("failed");
        }
        fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();
    }

    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let output = success(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(output["status"], "not_found", "{output}");
}

// ===========================================================================
// §S — evidence verify 6-value status union (U57/U53).
// ===========================================================================

/// PB53: `scope_unreachable` is a structured `status`, not a raw command
/// error — exit 0 without `--strict`.
#[test]
fn pb53_scope_unreachable_is_a_structured_status_exit_zero() {
    let dir = tempfile::tempdir().unwrap();
    let pointer = serde_json::json!({
        "schema_version": 1,
        "commit": format!("sha256:{}", "a".repeat(64)),
        "raw_hash": format!("sha256:{}", "b".repeat(64)),
        "tool_profile_hash": format!("sha256:{}", "c".repeat(64)),
        "chunk_hash": format!("sha256:{}", "d".repeat(64)),
        "scope_id": "scope_totally_unregistered_and_unreachable",
    });
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let temp = TempDir::new_in(dir.path()).unwrap();
    let output = success(&temp, &["evidence", "verify", &pointer_json]);
    assert_eq!(output["status"], "scope_unreachable", "{output}");
}

/// PB57: sqlite.db missing/unavailable is a command-level retryable error
/// (`KIO-E-INDEX-REBUILDING-001`), not a status — regardless of `--strict`.
#[test]
fn pb57_sqlite_unavailable_is_command_level_retryable_error() {
    let (dir, pointer, _) = fixture();
    fs::remove_file(kio_dir(&dir).join("index/sqlite.db")).unwrap();
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    for args in [
        vec!["evidence", "verify", pointer_json.as_str()],
        vec!["evidence", "verify", pointer_json.as_str(), "--strict"],
    ] {
        let (code, output) = run(&dir, &args);
        assert_eq!(code, 3, "{output}");
        assert_eq!(
            output["error_code"], "KIO-E-INDEX-REBUILDING-001",
            "{output}"
        );
    }
}

/// PB56: the reason-based exit table — `alive` is 0, `not_found` is 4 (a
/// permanent, not merely retryable, outcome).
#[test]
fn pb56_exit_table_alive_zero_not_found_four() {
    // `alive` -> 0 is already exercised by every other `success(&dir,
    // &["evidence", "verify", ...])` call in this file. This test locks the
    // `not_found` -> 4 half: canonical `erased` + raw absent (LC12) is a
    // genuine `not_found` status (unlike an unmarked absence, which is
    // corruption — pb65_lc14_unmarked_missing_raw_is_store_corrupt).
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    let store = ObjectStore::new(kio_dir(&dir));
    fs::remove_file(store.object_path(ObjectKind::Raw, &raw_hash).unwrap()).unwrap();
    let purge = PurgeState::new(kio_dir(&dir));
    let repo = Repository::open(dir.path()).unwrap();
    let commit_hash = repo.head_commit_hash().unwrap().unwrap();
    purge
        .append_erase_receipt_event(
            &raw_hash,
            kio_core::purge::LifecycleEvent::erased(
                "2026-07-13T00:00:00Z",
                &commit_hash,
                PurgeReason::Legal,
                "user",
                1,
            ),
        )
        .unwrap();
    resync_index_metadata(&dir);
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let (code, output) = run(&dir, &["evidence", "verify", &pointer_json, "--strict"]);
    assert_eq!(code, 4, "{output}");
    assert_eq!(output["status"], "not_found", "{output}");
}

// ===========================================================================
// §T/§V — regression locks (U58/U61).
// ===========================================================================

/// PB58 [regression-lock]: `kio evidence verify` refuses to evaluate while a
/// purge journal is active for the scope, regardless of whether the pointer's
/// own raw_hash is the journal's target.
#[test]
fn pb58_regression_active_journal_blocks_verify_for_unrelated_raw_hash() {
    let (dir, pointer, _) = fixture();
    let unrelated_raw_hash = hash_bytes(b"a raw_hash the journal does not target");
    let purge = PurgeState::new(kio_dir(&dir));
    purge
        .begin(
            vec![unrelated_raw_hash],
            PurgeReason::Legal,
            TombstoneMode::Default,
            "user",
            "2026-07-13T00:00:00Z",
            1,
            hash_bytes(b"planned purge commit placeholder"),
            hash_bytes(b"planned purge closure placeholder"),
            kio_core::scope::new_ulid(dir.path()),
        )
        .unwrap();
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let (code, output) = run(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(code, 3, "{output}");
    assert_eq!(
        output["error_code"], "KIO-E-PURGE-JOURNAL-ACTIVE-001",
        "{output}"
    );
}

/// PB62 [regression-lock]: `--batch` stays outside the MVP (exit 2).
#[test]
fn pb62_regression_batch_flag_rejected() {
    let (dir, ..) = fixture();
    kio(&dir, &["evidence", "verify", "--batch", "pointers.jsonl"])
        .arg("--json")
        .assert()
        .code(2);
}

// ===========================================================================
// §X — canonical validator unification (LC21 principle extended to
// canonical-event aggregation; Phase 1 hand-off).
// ===========================================================================

/// A tombstone with a `retired` tail (via erase-receipt resurrection) that
/// out-epochs a `purged` tombstone tail. Returns the raw_hash and pointer.
fn build_lc10_fixture() -> (TempDir, Value) {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    let purge = PurgeState::new(kio_dir(&dir));
    let repo = Repository::open(dir.path()).unwrap();
    let commit_hash = repo.head_commit_hash().unwrap().unwrap();
    // Tombstone tail = purged (lifecycle_epoch stamped 1st -> lower).
    purge
        .append_tombstone_event(
            &raw_hash,
            kio_core::purge::LifecycleEvent::purged(
                "2026-07-13T00:00:00Z",
                &commit_hash,
                PurgeReason::Legal,
                "user",
                1,
            ),
        )
        .unwrap();
    // Erase receipt: erased then retired (tail = retired, stamped later ->
    // higher lifecycle_epoch, so canonical_final_event picks this marker).
    purge
        .append_erase_receipt_event(
            &raw_hash,
            kio_core::purge::LifecycleEvent::erased(
                "2026-07-13T00:00:01Z",
                &commit_hash,
                PurgeReason::Legal,
                "user",
                1,
            ),
        )
        .unwrap();
    purge
        .append_erase_receipt_event(
            &raw_hash,
            kio_core::purge::LifecycleEvent::retired("2026-07-13T00:00:02Z", &commit_hash, "user"),
        )
        .unwrap();
    resync_index_metadata(&dir);
    (dir, pointer)
}

/// PB64: the LC10 worked example reproduced via `kio evidence verify` —
/// tombstone tail `purged` + erase-receipt tail `retired` (higher
/// lifecycle_epoch) is canonical `retired`, which resolves `alive` — the
/// resolver never short-circuits on the tombstone's own tail alone.
#[test]
fn pb64_lc10_worked_example_tombstone_purged_receipt_retired_is_alive() {
    let (dir, pointer) = build_lc10_fixture();
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let output = success(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(output["status"], "alive", "{output}");
}

/// PB65 (a) / LC12: canonical `erased`, raw absent — `not_found`,
/// `KIO-E-PURGE-NOT-FOUND-001` (erase receipts are never disclosed as
/// "tombstoned").
#[test]
fn pb65_lc12_canonical_erased_raw_absent_is_not_found() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    let store = ObjectStore::new(kio_dir(&dir));
    fs::remove_file(store.object_path(ObjectKind::Raw, &raw_hash).unwrap()).unwrap();
    let purge = PurgeState::new(kio_dir(&dir));
    let repo = Repository::open(dir.path()).unwrap();
    let commit_hash = repo.head_commit_hash().unwrap().unwrap();
    purge
        .append_erase_receipt_event(
            &raw_hash,
            kio_core::purge::LifecycleEvent::erased(
                "2026-07-13T00:00:00Z",
                &commit_hash,
                PurgeReason::Legal,
                "user",
                1,
            ),
        )
        .unwrap();
    resync_index_metadata(&dir);
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let (code, output) = run(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(code, 0, "{output}");
    assert_eq!(output["status"], "not_found", "{output}");
    assert_eq!(
        output["error_code"], "KIO-E-PURGE-NOT-FOUND-001",
        "{output}"
    );
}

/// PB65 (c) / LC14(a): no marker at all, raw absent — genuine corruption
/// (`KIO-E-STORE-CORRUPT-001`), distinct from the expected-absence LC12 code.
#[test]
fn pb65_lc14_unmarked_missing_raw_is_store_corrupt() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let store = ObjectStore::new(kio_dir(&dir));
    fs::remove_file(store.object_path(ObjectKind::Raw, raw_hash).unwrap()).unwrap();
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let (code, output) = run(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(code, 4, "{output}");
    assert_eq!(output["error_code"], "KIO-E-STORE-CORRUPT-001", "{output}");
}

/// PB67 [regression-lock]: a structurally malformed tombstone record is
/// `KIO-E-STORE-CORRUPT-001` identically via `kio repair --verify-objects`
/// (a finding) and `kio evidence verify` (a raw command error) — both read
/// through the same low-level `PurgeState::read_tombstone` parse/validate
/// path.
#[test]
fn pb67_regression_malformed_tombstone_is_store_corrupt_in_both_commands() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let digest = raw_hash.trim_start_matches("sha256:");
    let tombstone_path = kio_dir(&dir)
        .join("tombstones")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(digest);
    fs::create_dir_all(tombstone_path.parent().unwrap()).unwrap();
    fs::write(&tombstone_path, b"not valid json").unwrap();

    let (fsck_code, fsck_output) = run(&dir, &["repair", "--verify-objects"]);
    assert_eq!(fsck_code, 3, "{fsck_output}");
    assert_eq!(
        fsck_output["error_code"], "KIO-E-STORE-CORRUPT-001",
        "{fsck_output}"
    );

    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let (verify_code, verify_output) = run(&dir, &["evidence", "verify", &pointer_json]);
    assert_ne!(verify_code, 0, "{verify_output}");
    assert_eq!(
        verify_output["error_code"], "KIO-E-STORE-CORRUPT-001",
        "{verify_output}"
    );
}

/// PB68: `kio evidence verify` and `kio open` agree on `status`/`error_code`
/// for the same fixture (structural result of PB66's shared-implementation
/// requirement — `enforce_canonical_marker_barrier` backs both).
#[test]
fn pb68_verify_and_open_agree_on_canonical_erased_raw_absent() {
    let (dir, pointer, _) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    let store = ObjectStore::new(kio_dir(&dir));
    fs::remove_file(store.object_path(ObjectKind::Raw, &raw_hash).unwrap()).unwrap();
    // `open` checks the working tree before CAS (05 §4.2) — remove it too so
    // this genuinely probes the CAS+purge-marker cross-check the pointer
    // resolution path is supposed to take, not the working-tree fast path.
    fs::remove_file(dir.path().join("evidence.md")).unwrap();
    let purge = PurgeState::new(kio_dir(&dir));
    let repo = Repository::open(dir.path()).unwrap();
    let commit_hash = repo.head_commit_hash().unwrap().unwrap();
    purge
        .append_erase_receipt_event(
            &raw_hash,
            kio_core::purge::LifecycleEvent::erased(
                "2026-07-13T00:00:00Z",
                &commit_hash,
                PurgeReason::Legal,
                "user",
                1,
            ),
        )
        .unwrap();
    resync_index_metadata(&dir);

    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let (verify_code, verify_output) = run(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(verify_code, 0, "{verify_output}");
    assert_eq!(verify_output["status"], "not_found", "{verify_output}");

    let (open_code, open_output) = run(&dir, &["open", &pointer_json]);
    assert_ne!(open_code, 0, "{open_output}");
    assert_eq!(
        open_output["error_code"], "KIO-E-PURGE-NOT-FOUND-001",
        "verify's not_found <-> open's error_code must agree: {open_output}"
    );
    assert_eq!(verify_output["error_code"], open_output["error_code"]);
}

// ===========================================================================
// §Q — procedure 6b: manifest-missing direct-resolution downgrade and
// resurrection-link fallback (U55).
// ===========================================================================

/// PB48/PB49: an old pointer whose commit precedes a purge (`in_commit`)
/// cannot resolve directly once the purge deletes its manifest object AND
/// `chunk_publications`/`chunk_config_generations` rows (05 §3.5) — but once
/// the raw is resurrected (re-ingested with byte-identical content, same
/// deterministic `--offline` markdownize reproducing the same chunk_hash at
/// gen 0), canonical final event becomes `retired` with a
/// `resurrection_commit`, and 6b's link path re-runs the SAME
/// publication/association ancestry check against that later commit. The old
/// pointer resolves alive again (`manifest_missing: true`) through `open`,
/// `view`, and `evidence verify` alike (PB68's cross-command agreement).
#[test]
fn pb48_pb49_manifest_missing_resolves_via_resurrection_link_after_reingest() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("evidence.md"),
        "# Evidence\n\nTTL is 3600 seconds.\n",
    )
    .unwrap();
    success(&dir, &["init"]);
    success(&dir, &["index", "--offline", "--approve"]);
    let search = success(&dir, &["search", "3600", "--text"]);
    let old_pointer = search["results"][0]["evidence_pointer"].clone();
    let old_pointer_json = serde_json::to_string(&old_pointer).unwrap();
    let raw_hash = old_pointer["raw_hash"].as_str().unwrap().to_owned();

    // Confirm the pre-purge pointer resolves normally (sanity baseline).
    let baseline = success(&dir, &["evidence", "verify", &old_pointer_json]);
    assert_eq!(baseline["status"], "alive", "{baseline}");

    success(
        &dir,
        &[
            "purge",
            "--raw-hash",
            &raw_hash,
            "--reason",
            "legal",
            "--yes",
        ],
    );

    // Purged: canonical final event is (still active) `purged` at the
    // raw_hash level, which procedure 5 short-circuits to `tombstoned`
    // regardless of which commit the pointer names -- 6b (commit-scoped)
    // never even runs yet. It starts mattering once resurrection makes the
    // canonical event `retired` below.
    let purged = success(&dir, &["evidence", "verify", &old_pointer_json]);
    assert_eq!(purged["status"], "tombstoned", "{purged}");

    // Kio never deletes the working-tree original (05 §3.5), so the exact
    // same bytes are still sitting in evidence.md -- the next `kio index`
    // re-ingests and resurrects (retires the tombstone) in the same locked
    // mutation, reproducing the identical chunk_hash at gen 0.
    success(&dir, &["index", "--offline", "--approve"]);

    for args in [
        vec![
            "evidence".to_owned(),
            "verify".to_owned(),
            old_pointer_json.clone(),
        ],
        vec!["open".to_owned(), old_pointer_json.clone()],
        vec!["view".to_owned(), old_pointer_json.clone()],
    ] {
        let args_ref = args.iter().map(String::as_str).collect::<Vec<_>>();
        let output = success(&dir, &args_ref);
        if args_ref[0] == "evidence" {
            assert_eq!(output["status"], "alive", "{output}");
            assert_eq!(
                output["details"]["manifest_missing"], true,
                "resurrection-link resolution must still surface manifest_missing: {output}"
            );
        } else {
            assert_eq!(output["manifest_missing"], true, "{output}");
            assert_eq!(output["commit_shallow"], false, "{output}");
        }
    }
}

// ===========================================================================
// §O — decisive entry selection (U52), open/view side
// (`resolve_pointer_for_cli`, main.rs).
// ===========================================================================

/// PB42 (open/view side): when the same raw_hash is duplicate-placed in a
/// commit's tree under two different `tool_profile_hash` bindings, selection
/// must bind to the pointer's own `tool_profile_hash` — not to whichever
/// entry a naive `tree.entries.iter().find(...)` happens to reach first.
/// The synthetic alias entry here is a UTF-8-byte-order-earlier path
/// (`a-alias.md` < `evidence.md`) with a DIFFERENT `tool_profile_hash`/`gen`
/// than the pointer's own: before PB42's fix, `resolve_pointer_for_cli`
/// picked the first raw_hash match regardless of binding, mismatched the
/// pointer's `tool_profile_hash` against the alias's, and rejected a
/// perfectly valid pointer as `invalid_pointer_identity` (misreported
/// corruption). `kio open`/`kio view` must succeed, resolving through the
/// correctly-bound `evidence.md` entry instead.
#[test]
fn pb42_open_view_side_binds_to_pointer_tool_profile_hash_not_first_raw_hash_match() {
    let (dir, pointer, _) = fixture();
    let repo = Repository::open(dir.path()).unwrap();
    let head = repo.head_commit_hash().unwrap().unwrap();
    let commit = repo.read_commit(&head).unwrap();
    let tree = repo.read_tree(&commit.tree).unwrap();
    let real_entry = tree
        .entries
        .iter()
        .find(|entry| entry.raw_hash == pointer["raw_hash"].as_str().unwrap())
        .unwrap()
        .clone();
    let real_normalize = real_entry.normalize.clone().unwrap();

    // A byte-order-earlier alias path, same raw_hash, a DIFFERENT (fake)
    // tool_profile_hash/gen binding -- exactly the "duplicate placement"
    // shape PB42 describes, engineered so a naive first-match `.find()`
    // reaches the wrong (alias) entry first.
    let alias_normalize = NormalizeRef {
        tool_profile_hash: hash_bytes(b"a different tool profile entirely"),
        gen: real_normalize.gen + 7,
        manifest_hash: None,
    };
    let mut alias_entry = TreeEntry::raw_file("a-alias.md", real_entry.raw_hash.clone()).unwrap();
    alias_entry.normalize = Some(alias_normalize);
    assert!(alias_entry.path.as_bytes() < real_entry.path.as_bytes());

    let mut entries = tree.entries.clone();
    entries.push(alias_entry);
    let new_tree = build_tree(entries).unwrap();
    let store = ObjectStore::new(kio_dir(&dir));
    let (new_tree_hash, _) = store
        .write_json(ObjectKind::Tree, &serde_json::to_value(&new_tree).unwrap())
        .unwrap();
    let new_commit = CommitObject::new(
        new_tree_hash,
        vec![head],
        "2026-07-21T00:00:00Z".to_owned(),
        "pb42 fixture: duplicate raw_hash placement".to_owned(),
        commit.tool_lock_hash.clone(),
        CommitStats {
            files_added: 1,
            files_modified: 0,
            files_deleted: 0,
        },
        CommitType::Manual,
    )
    .unwrap();
    let (new_commit_hash, _) = store
        .write_json(
            ObjectKind::Commit,
            &serde_json::to_value(&new_commit).unwrap(),
        )
        .unwrap();
    fs::write(kio_dir(&dir).join("refs/heads/main"), &new_commit_hash).unwrap();
    fs::write(kio_dir(&dir).join("HEAD"), &new_commit_hash).unwrap();

    let mut new_pointer = pointer.clone();
    new_pointer["commit"] = Value::String(new_commit_hash);
    let pointer_json = serde_json::to_string(&new_pointer).unwrap();

    let open_output = success(&dir, &["open", &pointer_json]);
    assert_eq!(open_output["status"], "opened", "{open_output}");
    let view_output = success(&dir, &["view", &pointer_json]);
    assert_eq!(view_output["status"], "viewed", "{view_output}");

    // Cross-command agreement (PB66/68's principle applied to §O): evidence
    // verify resolves the same pointer through the same binding.
    let verify_output = success(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(verify_output["status"], "alive", "{verify_output}");
}
