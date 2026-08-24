//! Contract tests for `tasks/step4b-contract-tests-p3b.md` (CLI 横断 /
//! exit・error 表 / log time-travel / その他, P3-B). Test names embed the QB
//! number they lock down. Harness mirrors
//! `crates/kio-cli/tests/step4b_p2c_contract.rs` /
//! `crates/kio-cli/tests/step4b_p2b_contract.rs`.
//!
//! Scope discipline (see the task's own §0 table and the orchestrator's
//! constraints): this file only covers contracts whose fix/verification
//! lives in the exit/error/log/config/search-carryover lane.
//!
//! Covered here: QB1-QB9 (§A, full), QB11/QB12/QB14/QB15/QB18/QB19/QB20/
//! QB23 (§B slice), QB29/QB31/QB32/QB37 (§C slice), QB50-QB58 (§D, full —
//! `kio log --at/--since` real implementation), QB61 (§E slice). QB24's
//! Recall@10 projection and frozen malformed-wire cases live in the Rust
//! `kio-eval` runner/tests; they are not CLI contracts here.
//!
//! Deliberately deferred (substantial new subsystems outside a safe,
//! single-pass scope, or dependent on P2-C infra this book explicitly does
//! not recontract) — see the final report for the full survey: QB10 (view
//! `<path> --at` syntax), QB13 (scrub-lock+3-point-check same critical
//! section), QB16 (`kio import --as-new-scope` fork — command does not
//! exist), QB17 (`.kioz` export sanitize warning — command does not exist),
//! QB21/QB22 (system-directory ignore patterns + template-version hashing),
//! QB25-QB28/QB30/QB33-QB49 except QB29/31/32/37 (mtime racy-check, fsync
//! chaining, XLSX escaping, LCS tie-break proof, UCD Script property,
//! query-vector cache persistence, embedding CAS byte reformat, tree
//! chunking_config_hash/chunk_set_hash fields, diff derived-only detection,
//! `parent_instance`, auto gen+1 on prepared_hash change, the 9-state
//! `up_to_date` machine, tool_lock_hash no-op comparison, batch resume/retry
//! auto-snapshot wiring, manifest/toollock CAS write timing, `.kio/staging/`
//! descriptor publish, tag simple-case-folding, view assembly `order`
//! uniqueness + percent-encoding, registry move-nonqualify + path validation
//! extension), QB59/QB60 (PC20 rotation-point tracing for embedding-
//! enrichment-finalize / index-batch-finalize), QB62-QB66 (multi-scope
//! reuse and PC33/44 per-binding chunking-config wiring — both
//! need QB33/34/64/65's infra first).

use std::fs;
use std::str::FromStr;

use assert_cmd::Command;
use kio_core::cas::{ObjectKind, ObjectStore, hash_bytes};
use kio_core::purge::{PurgeReason, PurgeState, TombstoneMode};
use kio_core::scope::{Repository, StoreLock};
use kio_index::registry::{RegistryDb, RegistryEntry};
use rusqlite::OptionalExtension;
use serde_json::Value;
use tempfile::TempDir;

// ---------------------------------------------------------------------------
// Harness
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
        .env_remove("KIO_FIXED_NOW")
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

/// `(exit_code, parsed_json)`, reading stdout on success and stderr on
/// failure (matches `step4b_p2c_contract.rs`'s `run`).
fn run(dir: &TempDir, args: &[&str]) -> (i32, Value) {
    let output = kio(dir, args).arg("--json").output().unwrap();
    let code = output.status.code().unwrap();
    let stream: &[u8] = if !output.stdout.is_empty() {
        &output.stdout
    } else {
        &output.stderr
    };
    (code, serde_json::from_slice(stream).unwrap())
}

fn run_with_env(dir: &TempDir, args: &[&str], key: &str, value: &str) -> (i32, Value) {
    let output = kio(dir, args)
        .env(key, value)
        .arg("--json")
        .output()
        .unwrap();
    let code = output.status.code().unwrap();
    let stream: &[u8] = if !output.stdout.is_empty() {
        &output.stdout
    } else {
        &output.stderr
    };
    (code, serde_json::from_slice(stream).unwrap())
}

/// Child scopes require a retained-handle launcher. Windows intentionally has
/// no pathname-based substitute, so an otherwise successful parent index is a
/// result-on-stdout partial failure and every planned child is reported as an
/// explicit fail-closed error.
#[cfg(windows)]
fn assert_windows_bound_children_unsupported(result: &Value, paths: &[&str]) {
    assert_eq!(result["error_code"], "KIO-E-INDEX-PARTIAL-001");
    let children = result["child_scopes"]
        .as_array()
        .expect("index partial result must retain child scope rows");
    for path in paths {
        let row = children
            .iter()
            .find(|row| row["path"] == *path)
            .unwrap_or_else(|| panic!("missing discovered child row for {path}"));
        assert_eq!(row["status"], "skipped_error", "{path}: {row}");
        assert_eq!(
            row["error_code"], "KIO-E-SCOPE-BOUND-UNSUPPORTED-001",
            "{path}: {row}"
        );
    }
}

fn kio_dir(dir: &TempDir) -> std::path::PathBuf {
    dir.path().join(".kio")
}

fn registry_path(dir: &TempDir) -> std::path::PathBuf {
    dir.path().join(".test-data/kio/scope-registry.sqlite")
}

/// A single-file indexed scope with one search-eligible pointer.
fn fixture() -> (TempDir, Value) {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("evidence.md"),
        "# Evidence\n\nTTL is 3600 seconds.\n",
    )
    .unwrap();
    success(&dir, &["init"]);
    success(&dir, &["index", "--offline", "--approve"]);
    let search = success(&dir, &["search", "3600", "--mode", "text"]);
    let pointer = search["results"][0]["evidence_pointer"].clone();
    (dir, pointer)
}

fn bump_format_version(dir: &TempDir, version: &str) {
    let scope_json = kio_dir(dir).join("scope.json");
    let mut value: Value = serde_json::from_str(&fs::read_to_string(&scope_json).unwrap()).unwrap();
    value["kio_format_version"] = Value::String(version.to_owned());
    fs::write(&scope_json, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
}

/// Directly opens (bypassing the `kio purge` CLI) an active purge journal for
/// a placeholder raw_hash — mirrors `step4b_p2b_contract.rs`'s PB15 fixture.
/// Sufficient to make `ReadBarrierCheckpoint::open`'s journal-active check
/// fire; the target raw_hash need not correspond to anything real.
fn begin_active_purge_journal(dir: &TempDir) {
    let purge = PurgeState::new(kio_dir(dir));
    purge
        .begin(
            vec![hash_bytes(b"qb4/qb12 placeholder purge target")],
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
}

/// Appends a lifecycle event directly via `PurgeState` (bypassing the `kio
/// purge` CLI, which would otherwise resync `index_metadata.
/// last_lifecycle_epoch` itself) so the scope's on-disk lifecycle-epoch
/// counter diverges from whatever `index_metadata` last recorded — the
/// documented trigger for `check_index_generation_current`'s
/// `KIO-E-INDEX-REBUILDING-001` (mirrors `step4b_p2b_contract.rs`'s
/// `resync_index_metadata` doc comment, deliberately NOT calling it here).
fn make_index_generation_stale(dir: &TempDir, raw_hash: &str) {
    let purge = PurgeState::new(kio_dir(dir));
    let repo = Repository::open(dir.path()).unwrap();
    let commit_hash = repo.head_commit_hash().unwrap().unwrap();
    purge
        .append_tombstone_event(
            raw_hash,
            kio_core::purge::LifecycleEvent::purged(
                "2026-07-13T00:00:00Z",
                &commit_hash,
                PurgeReason::Legal,
                "user",
                1,
            ),
        )
        .unwrap();
}

/// Registers `scope_id` as TWO distinct live `.kio` (the `KIO-E-REGISTRY-
/// DUP-001` precondition) — mirrors `step4b_p2b_contract.rs`'s PB21/22
/// fixture. Returns the second scope's directory (kept alive for the
/// registry row to remain "live"/reachable).
fn make_registry_duplicate(dir_a: &TempDir, scope_id: &str) -> TempDir {
    let dir_b = tempfile::tempdir().unwrap();
    kio(&dir_b, &["init"]).arg("--json").assert().success();
    let scope_path = kio_dir(&dir_b).join("scope.json");
    let mut scope: Value = serde_json::from_slice(&fs::read(&scope_path).unwrap()).unwrap();
    scope["scope_id"] = serde_json::json!(scope_id);
    fs::write(&scope_path, serde_json::to_vec_pretty(&scope).unwrap()).unwrap();

    let registry = RegistryDb::open(registry_path(dir_a)).unwrap();
    registry
        .upsert(&RegistryEntry {
            scope_id: scope_id.to_owned(),
            kio_path: kio_dir(dir_a).display().to_string(),
            root_path: dir_a.path().display().to_string(),
            participates_in_global_search: true,
            indexed: true,
            last_seen_at: "2020-01-01T00:00:00Z".to_owned(),
        })
        .unwrap();
    registry
        .upsert(&RegistryEntry {
            scope_id: scope_id.to_owned(),
            kio_path: kio_dir(&dir_b).display().to_string(),
            root_path: dir_b.path().display().to_string(),
            participates_in_global_search: true,
            indexed: true,
            last_seen_at: "2099-01-01T00:00:00Z".to_owned(),
        })
        .unwrap();
    dir_b
}

// ===========================================================================
// §A — K 領域: error code / exit code / preflight order (QB1-QB9)
// ===========================================================================

/// QB1: `open`/`view`/`restore` all classify a scope_unreachable dead
/// pointer as retryable exit 3 (`KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001`), not
/// the permanent exit 4 dead-pointer class — `scope_unreachable_error` is
/// their one shared helper (main.rs), so all three callers are fixed by the
/// same change; verified independently per command since each reaches it
/// through a different call path.
#[test]
fn qb1_scope_unreachable_is_exit_3_across_open_view_restore() {
    let pointer = serde_json::json!({
        "schema_version": 1,
        "commit": format!("sha256:{}", "a".repeat(64)),
        "raw_hash": format!("sha256:{}", "b".repeat(64)),
        "tool_profile_hash": format!("sha256:{}", "c".repeat(64)),
        "chunk_hash": format!("sha256:{}", "d".repeat(64)),
        "scope_id": "scope_totally_unregistered_and_unreachable",
    });
    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let dir = tempfile::tempdir().unwrap();

    let (code, err) = run(&dir, &["open", &pointer_json]);
    assert_eq!(code, 3, "open: {err}");
    assert_eq!(err["error_code"], "KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001");

    let (code, err) = run(&dir, &["view", &pointer_json]);
    assert_eq!(code, 3, "view: {err}");
    assert_eq!(err["error_code"], "KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001");

    let restore_to = dir.path().join("restored");
    let (code, err) = run(
        &dir,
        &[
            "restore",
            &pointer_json,
            "--to",
            restore_to.to_str().unwrap(),
        ],
    );
    assert_eq!(code, 3, "restore: {err}");
    assert_eq!(err["error_code"], "KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001");
}

/// QB2 [regression-lock]: a successful (exit 0) response's `error_code`
/// field is a degrade-reason classification only — it never determines the
/// process exit code. Exercised via search's text-fallback path (embedding
/// configured but this scope carries no vectors yet), which returns exit 0
/// with a non-null `error_code`.
#[test]
fn qb2_success_exit_is_independent_of_error_code_value() {
    use kio_adapter::catalog::TEST_ADOPTED_EMBEDDING_ENV;

    let (dir, _pointer) = fixture();
    let output = kio(&dir, &["search", "3600"])
        .env(TEST_ADOPTED_EMBEDDING_ENV, "mock")
        .arg("--json")
        .assert()
        .success() // exit 0
        .get_output()
        .stdout
        .clone();
    let value: Value = serde_json::from_slice(&output).unwrap();
    assert_eq!(value["resolved_mode"], "text");
    assert!(
        !value["error_code"].is_null(),
        "expected a non-null degrade error_code, got {value}"
    );
    assert_eq!(value["error_code"], "KIO-E-SEARCH-VEC-UNAVAIL-001");
}

/// QB3(a) [regression-lock]: a non-multimodal embedding profile is rejected
/// at tool-lock materialize time with `KIO-E-EMBED-MODALITY-001` / exit 2.
#[test]
fn qb3a_non_multimodal_embedding_profile_rejected_exit_2() {
    use kio_adapter::catalog::TEST_ADOPTED_EMBEDDING_ENV;

    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("doc.md"), "# document\n").unwrap();
    success(&dir, &["init"]);
    let tool_lock_path = kio_dir(&dir).join("tool-lock.json");
    let tool_lock_before = fs::read(&tool_lock_path).unwrap();
    let (code, error) = run_with_env(
        &dir,
        &["index", "--approve"],
        TEST_ADOPTED_EMBEDDING_ENV,
        "non_multimodal",
    );
    assert_eq!(code, 2, "{error}");
    assert_eq!(error["error_code"], "KIO-E-EMBED-MODALITY-001");
    assert_eq!(
        fs::read(&tool_lock_path).unwrap(),
        tool_lock_before,
        "rejected materialization must not replace the existing tool lock"
    );
    assert!(
        !kio_dir(&dir).join("index/sqlite.db").exists(),
        "rejected materialization must not publish an index"
    );
}

/// QB3(b) [regression-lock]: `fallback_reason` is a free-form `Option<String>`
/// (open vocabulary), not a closed enum — no schema/type constrains its
/// values.
#[test]
fn qb3b_fallback_reason_is_open_vocabulary_string() {
    use kio_adapter::catalog::TEST_ADOPTED_EMBEDDING_ENV;

    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("doc.md"), "# document\n").unwrap();
    success(&dir, &["init"]);
    kio(&dir, &["index", "--approve"])
        .env(TEST_ADOPTED_EMBEDDING_ENV, "mock")
        .assert()
        .success();
    let tasks_path = kio_dir(&dir).join("tasks.jsonl");
    let arbitrary = "provider_defined/fallback:v2026-08";
    let mut rows = fs::read_to_string(&tasks_path)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .collect::<Vec<_>>();
    assert!(
        !rows.is_empty(),
        "mock embedding index must create task rows"
    );
    let selected = rows
        .iter()
        .position(|row| row["type"] == "embedding")
        .expect("mock embedding index must create an embedding task row");
    rows[selected]["fallback_reason"] = Value::String(arbitrary.to_owned());
    fs::write(
        &tasks_path,
        rows.iter()
            .map(serde_json::to_string)
            .collect::<Result<Vec<_>, _>>()
            .unwrap()
            .join("\n")
            + "\n",
    )
    .unwrap();

    let status = success(&dir, &["status"]);
    assert!(
        status["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|task| task["fallback_reason"] == arbitrary),
        "status must preserve an arbitrary provider-defined fallback_reason: {status}"
    );
}

/// QB3(c) [regression-lock]: config schema validation failures always report
/// `KIO-E-CONFIG-SCHEMA-001` — no leftover `NNN` placeholder in the error
/// code namespace.
#[test]
fn qb3c_config_schema_error_code_has_no_placeholder() {
    let (dir, _pointer) = fixture();
    fs::write(
        kio_dir(&dir).join("config.toml"),
        "[scope]\nignore = \"not-an-array\"\n",
    )
    .unwrap();
    let (code, err) = run(&dir, &["status"]);
    assert_eq!(code, 2, "{err}");
    assert_eq!(err["error_code"], "KIO-E-CONFIG-SCHEMA-001");
    assert!(!err["error_code"].as_str().unwrap().contains("NNN"));
}

/// QB4(a)/QB4(d): (0) `kio_format_version` incompatibility outranks BOTH (1)
/// active purge journal and (3) stale index-generation — `kio log` (a
/// CWD-rooted command with no registry/(2) involvement) sees only
/// `KIO-E-STORE-VERSION-001` / exit 8 even when both lower-priority
/// conditions also hold.
#[test]
fn qb4a_qb4d_format_version_outranks_journal_and_index_generation_via_log() {
    let (dir, pointer) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    make_index_generation_stale(&dir, &raw_hash); // sets up (3)
    begin_active_purge_journal(&dir); // sets up (1)
    bump_format_version(&dir, "9.0.0"); // sets up (0)

    let (code, err) = run(&dir, &["log"]);
    assert_eq!(code, 8, "{err}");
    assert_eq!(err["error_code"], "KIO-E-STORE-VERSION-001");
}

/// QB4(b)/QB4(c): (2) registry live duplicate outranks BOTH (1) active
/// purge journal and (3) stale index-generation — `kio view <pointer>`
/// resolves the target scope (which surfaces (2) as a side effect of
/// `resolve_scope_target`) before it ever reaches the shared (1)+(3)
/// preflight pair.
#[test]
fn qb4b_qb4c_registry_duplicate_outranks_journal_and_index_generation_via_view() {
    let (dir_a, pointer) = fixture();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    make_index_generation_stale(&dir_a, &raw_hash); // sets up (3)
    begin_active_purge_journal(&dir_a); // sets up (1)
    let scope_id = pointer["scope_id"].as_str().unwrap().to_owned();
    let _dir_b = make_registry_duplicate(&dir_a, &scope_id); // sets up (2)

    // A scope_path hint that no longer resolves forces pure registry lookup
    // (PB21/22's recipe), which is where the (2) duplicate is detected.
    let mut orphan_pointer = pointer.clone();
    orphan_pointer["scope_path"] =
        serde_json::json!(dir_a.path().join("gone/.kio").display().to_string());
    let pointer_json = serde_json::to_string(&orphan_pointer).unwrap();

    let (code, err) = run(&dir_a, &["view", &pointer_json]);
    // Registry-dup's default exit is 4 (PermanentFailure) for open/view —
    // `kio evidence verify` alone overrides it to 3 (PB54, main.rs's own doc
    // comment on `registry_duplicate_error`). QB4(c)'s task text does not
    // pin an exit code for this combination, only the winning error_code.
    assert_eq!(code, 4, "{err}");
    assert_eq!(err["error_code"], "KIO-E-REGISTRY-DUP-001");
}

/// QB5 [regression-lock]: `restore` already checks (0) `kio_format_version`
/// before (1) the purge read barrier (unlike the pre-QB6-fix `open`/`view`) —
/// pin the currently-correct order so it cannot silently drift.
#[test]
fn qb5_restore_checks_format_version_before_purge_journal() {
    let (dir, pointer) = fixture();
    begin_active_purge_journal(&dir);
    bump_format_version(&dir, "9.0.0");

    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let restore_to = dir.path().join("restored");
    let (code, err) = run(
        &dir,
        &[
            "restore",
            &pointer_json,
            "--to",
            restore_to.to_str().unwrap(),
        ],
    );
    assert_eq!(code, 8, "{err}");
    assert_eq!(err["error_code"], "KIO-E-STORE-VERSION-001");
}

/// QB6: `diff` and `open` must agree on preflight priority for the exact
/// same (format-version-incompatible + active-journal) scope — both return
/// `KIO-E-STORE-VERSION-001` / exit 8, not one VERSION and the other
/// JOURNAL-ACTIVE. Before the fix, `open` checked the journal (1) before
/// the format version (0) and so disagreed with `diff`.
#[test]
fn qb6_diff_and_open_agree_on_preflight_priority() {
    let (dir, pointer) = fixture();
    begin_active_purge_journal(&dir);
    bump_format_version(&dir, "9.0.0");

    let (code, err) = run(&dir, &["diff", "HEAD", "HEAD"]);
    assert_eq!(code, 8, "diff: {err}");
    assert_eq!(err["error_code"], "KIO-E-STORE-VERSION-001", "diff: {err}");

    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let (code, err) = run(&dir, &["open", &pointer_json]);
    assert_eq!(code, 8, "open: {err}");
    assert_eq!(err["error_code"], "KIO-E-STORE-VERSION-001", "open: {err}");
}

/// QB6 (evidence verify side): the same combined scenario, through `kio
/// evidence verify`, must also report `KIO-E-STORE-VERSION-001` rather than
/// its own PB57 sqlite-availability short-circuit or the journal check.
#[test]
fn qb6_evidence_verify_agrees_with_diff_and_open() {
    let (dir, pointer) = fixture();
    begin_active_purge_journal(&dir);
    bump_format_version(&dir, "9.0.0");

    let pointer_json = serde_json::to_string(&pointer).unwrap();
    let (code, err) = run(&dir, &["evidence", "verify", &pointer_json]);
    assert_eq!(code, 8, "{err}");
    assert_eq!(err["error_code"], "KIO-E-STORE-VERSION-001");
}

/// QB7 [regression-lock — the check already exists, just not where the task
/// doc's "現状" survey looked]: a registry live duplicate fail-closes `kio
/// index --approve`. Not via an up-front preflight call in `run_index`
/// itself, but via `registry_duplicate_guard` (QA67,
/// step4b-contract-tests-p3a.md §T) — called from every device-ledger
/// charge-recording path (`record_free_local_charge` /
/// `reserve_or_reuse_task_charge`) `run_index_pipeline` reaches for its
/// first file, before any raw object or SQLite write. Exit 4 (registry-dup's
/// documented default outside `kio evidence verify`), not exit 3.
#[test]
fn qb7_index_approve_fail_closes_on_registry_duplicate() {
    let (dir_a, pointer) = fixture();
    let scope_id = pointer["scope_id"].as_str().unwrap().to_owned();
    let _dir_b = make_registry_duplicate(&dir_a, &scope_id);

    fs::write(dir_a.path().join("more.md"), "# More\n\nMore content.\n").unwrap();
    let (code, err) = run(&dir_a, &["index", "--offline", "--approve"]);
    assert_eq!(code, 4, "{err}");
    assert_eq!(err["error_code"], "KIO-E-REGISTRY-DUP-001");
}

/// QB8: an incompatible `kio_format_version` in `scope.json` is detected
/// even when the SAME file also carries a key the current schema does not
/// recognize (simulating a future MINOR-bump addition) — the version check
/// runs before JSON Schema validation, so the response is
/// `KIO-E-STORE-VERSION-001` (exit 8), never `KIO-E-CONFIG-SCHEMA-001`
/// (exit 2).
#[test]
fn qb8_format_version_checked_before_schema_validation() {
    let (dir, _pointer) = fixture();
    let scope_json = kio_dir(&dir).join("scope.json");
    let mut value: Value = serde_json::from_str(&fs::read_to_string(&scope_json).unwrap()).unwrap();
    value["kio_format_version"] = Value::String("9.0.0".to_owned());
    value["future_minor_bump_key"] = serde_json::json!("simulated unknown key");
    fs::write(&scope_json, serde_json::to_vec_pretty(&value).unwrap()).unwrap();

    let (code, err) = run(&dir, &["status"]);
    assert_eq!(code, 8, "{err}");
    assert_eq!(err["error_code"], "KIO-E-STORE-VERSION-001");
}

/// QB9: the write-side half of QB8's scenario is an immediate, zero-write
/// rejection — no raw object or SQLite mutation happens before the version
/// check fails. `kio status` (read-only) sees the identical error_code.
#[test]
fn qb9_new_version_store_write_command_rejects_with_zero_writes() {
    let (dir, _pointer) = fixture();
    let scope_json = kio_dir(&dir).join("scope.json");
    let mut value: Value = serde_json::from_str(&fs::read_to_string(&scope_json).unwrap()).unwrap();
    value["kio_format_version"] = Value::String("9.0.0".to_owned());
    value["future_minor_bump_key"] = serde_json::json!("simulated unknown key");
    fs::write(&scope_json, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
    let new_content = b"# New\n\nUnwritten content.\n";
    fs::write(dir.path().join("new.md"), new_content).unwrap();
    let new_raw_hash = hash_bytes(new_content);

    let sqlite_path = kio_dir(&dir).join("index/sqlite.db");
    let before_mtime = fs::metadata(&sqlite_path).unwrap().modified().unwrap();

    let (code, err) = run(&dir, &["index", "--offline", "--approve"]);
    assert_eq!(code, 8, "write side: {err}");
    assert_eq!(err["error_code"], "KIO-E-STORE-VERSION-001");

    let after_mtime = fs::metadata(&sqlite_path).unwrap().modified().unwrap();
    assert_eq!(before_mtime, after_mtime, "sqlite.db must not be touched");
    let store = ObjectStore::new(kio_dir(&dir));
    assert!(
        store
            .inspect_object(ObjectKind::Raw, &new_raw_hash)
            .is_err(),
        "new.md's raw object must not have been written"
    );

    let (code, err) = run(&dir, &["status"]);
    assert_eq!(code, 8, "read side: {err}");
    assert_eq!(err["error_code"], "KIO-E-STORE-VERSION-001");
}

// ===========================================================================
// §B — L 領域 (QB10-QB24)
// ===========================================================================

/// QB11/QB12 contention and purge non-mutation behavior are covered by the
/// dedicated CLI and purge contracts; this file deliberately avoids binding
/// those public guarantees to private function placement or transaction text.

/// QB14(a): indexing one root registers that root only. An initialized sibling
/// in another XDG registry is not discovered or copied into this registry.
#[test]
fn qb14a_index_registers_only_the_requested_root() {
    let primary = tempfile::tempdir().unwrap();
    let sibling = tempfile::tempdir().unwrap();
    fs::write(primary.path().join("primary.md"), "# primary\n").unwrap();
    fs::write(sibling.path().join("sibling.md"), "# sibling\n").unwrap();

    // Initialize the sibling with isolated device state: it is a real Kio
    // scope, but is deliberately unregistered in primary's observable registry.
    Command::cargo_bin("kio")
        .unwrap()
        .current_dir(sibling.path())
        .env("XDG_CONFIG_HOME", sibling.path().join("xdg/config"))
        .env("XDG_DATA_HOME", sibling.path().join("xdg/data"))
        .env("XDG_CACHE_HOME", sibling.path().join("xdg/cache"))
        .args(["init", "--json"])
        .assert()
        .success();
    success(&primary, &["init"]);
    success(&primary, &["index", "--offline", "--approve"]);

    let entries = RegistryDb::open(registry_path(&primary))
        .unwrap()
        .all_entries()
        .unwrap();
    assert_eq!(
        entries.len(),
        1,
        "index must not scan or register siblings: {entries:?}"
    );
    assert_eq!(
        entries[0].root_path,
        primary.path().canonicalize().unwrap().to_str().unwrap()
    );
}

/// QB14(b): with `XDG_DATA_HOME` unset, the device-local registry (and, by
/// the same `data_home()` fallback, `scrub.lock`) resolves under
/// `$HOME/.local/share/kio/`, never a CWD-relative path.
#[test]
fn qb14b_xdg_data_home_fallback_resolves_under_home() {
    let scope_dir = tempfile::tempdir().unwrap();
    let home = tempfile::tempdir().unwrap();
    fs::write(scope_dir.path().join("a.md"), "# A\n\nbody\n").unwrap();
    Command::cargo_bin("kio")
        .unwrap()
        .current_dir(scope_dir.path())
        .env("HOME", home.path())
        .env_remove("XDG_DATA_HOME")
        .env("XDG_CONFIG_HOME", home.path().join("config"))
        .env("XDG_CACHE_HOME", home.path().join("cache"))
        .env_remove("GEMINI_API_KEY")
        .env_remove("MISTRAL_API_KEY")
        .args(["init", "--json"])
        .assert()
        .success();
    assert!(
        home.path()
            .join(".local/share/kio/scope-registry.sqlite")
            .exists(),
        "registry must fall back to $HOME/.local/share/kio/, not a CWD-relative path"
    );

    for args in [
        &["index", "--offline", "--approve", "--json"][..],
        &["search", "body", "--mode", "text", "--json"][..],
    ] {
        Command::cargo_bin("kio")
            .unwrap()
            .current_dir(scope_dir.path())
            .env("HOME", home.path())
            .env_remove("XDG_DATA_HOME")
            .env("XDG_CONFIG_HOME", home.path().join("config"))
            .env("XDG_CACHE_HOME", home.path().join("cache"))
            .env_remove("GEMINI_API_KEY")
            .env_remove("MISTRAL_API_KEY")
            .args(args)
            .assert()
            .success();
    }
    let metrics = home.path().join(".local/share/kio/logs/metrics.jsonl");
    let metrics_before = fs::metadata(&metrics).unwrap().len();
    let scrub =
        StoreLock::acquire_path(home.path().join(".local/share/kio/logs/scrub.lock")).unwrap();
    Command::cargo_bin("kio")
        .unwrap()
        .current_dir(scope_dir.path())
        .env("HOME", home.path())
        .env_remove("XDG_DATA_HOME")
        .env("XDG_CONFIG_HOME", home.path().join("config"))
        .env("XDG_CACHE_HOME", home.path().join("cache"))
        .env_remove("GEMINI_API_KEY")
        .env_remove("MISTRAL_API_KEY")
        .args(["search", "body", "--mode", "text", "--json"])
        .assert()
        .success();
    assert_eq!(
        fs::metadata(&metrics).unwrap().len(),
        metrics_before,
        "the HOME-fallback scrub lock must suppress the matching device-log append"
    );
    drop(scrub);
}

/// QB15: parent scopes remain direct-file-only, while bounded child discovery
/// makes separate scopes for file-bearing ordinary directories. VCS roots and
/// their descendants are skipped by default, including a regular `.git`
/// gitfile; opt-in permits them. Preview reports its plan without mutation.
#[test]
fn qb15_child_scopes_vcs_default_opt_in_and_preview() {
    let dir = tempfile::tempdir().unwrap();
    fs::create_dir_all(dir.path().join("ordinary/nested")).unwrap();
    fs::create_dir_all(dir.path().join("ignored")).unwrap();
    fs::write(dir.path().join("ordinary/note.md"), "ordinary").unwrap();
    fs::write(dir.path().join("ordinary/nested/deep.md"), "nested").unwrap();
    fs::write(dir.path().join("ignored/private.md"), "ignore me").unwrap();
    fs::create_dir_all(dir.path().join("git-dir/.git")).unwrap();
    fs::write(dir.path().join("git-dir/readme.md"), "git dir").unwrap();
    fs::create_dir_all(dir.path().join("git-file/inner")).unwrap();
    fs::write(dir.path().join("git-file/.git"), "gitdir: elsewhere\n").unwrap();
    fs::write(dir.path().join("git-file/inner/readme.md"), "git file").unwrap();
    #[cfg(unix)]
    let symlink_victim = {
        let victim = tempfile::tempdir().unwrap();
        fs::write(victim.path().join("outside.md"), "must stay outside").unwrap();
        std::os::unix::fs::symlink(victim.path(), dir.path().join("linked-child")).unwrap();
        victim
    };
    success(&dir, &["init"]);
    fs::write(dir.path().join(".kioignore"), "ignored\n").unwrap();

    let preview = success(&dir, &["index", "--preview", "--offline"]);
    assert!(
        !dir.path().join("ordinary/.kio").exists(),
        "preview must not initialize children"
    );
    assert!(
        preview["candidates"]
            .as_array()
            .unwrap()
            .iter()
            .all(|row| row["input_path"] != "ordinary/note.md")
    );
    assert!(
        preview["child_scopes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|row| row["path"] == "git-dir" && row["status"] == "skipped_vcs")
    );
    assert!(
        preview["child_scopes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|row| row["path"] == "ordinary" && row["status"] == "planned")
    );
    assert_eq!(preview["estimated_aggregate_file_count"], 2);
    assert_eq!(preview["estimated_aggregate_size_bytes"], 14);
    assert!(
        preview["child_scopes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|row| row["path"] == "ordinary"
                && row["estimated_file_count"] == 1
                && row["estimated_size_bytes"] == 8)
    );
    #[cfg(unix)]
    assert!(
        preview["child_scopes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|row| row["path"] == "linked-child" && row["status"] == "skipped_symlink")
    );
    #[cfg(not(windows))]
    let indexed = success(&dir, &["index", "--offline", "--approve"]);
    #[cfg(windows)]
    let indexed = {
        let (code, output) = run(&dir, &["index", "--offline", "--approve"]);
        assert_eq!(code, 3, "{output}");
        assert_windows_bound_children_unsupported(&output, &["ordinary", "ordinary/nested"]);
        output
    };
    #[cfg(not(windows))]
    assert!(dir.path().join("ordinary/.kio").is_dir());
    #[cfg(not(windows))]
    assert!(dir.path().join("ordinary/nested/.kio").is_dir());
    #[cfg(windows)]
    assert!(
        !dir.path().join("ordinary/.kio").exists()
            && !dir.path().join("ordinary/nested/.kio").exists(),
        "Windows must fail closed rather than initialize a child by pathname"
    );
    assert!(!dir.path().join("git-dir/.kio").exists());
    assert!(!dir.path().join("git-file/.kio").exists());
    assert!(!dir.path().join("ignored/.kio").exists());
    assert!(!dir.path().join(".test-config/.kio").exists());
    assert!(!dir.path().join(".test-data/.kio").exists());
    assert!(!dir.path().join(".test-cache/.kio").exists());
    #[cfg(unix)]
    assert!(
        !symlink_victim.path().join(".kio").exists(),
        "child discovery must not follow a directory symlink into the victim"
    );
    assert!(
        indexed["child_scopes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|row| row["path"] == "git-dir" && row["status"] == "skipped_vcs")
    );
    assert!(
        indexed["child_scopes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|row| row["path"] == "git-file" && row["status"] == "skipped_vcs")
    );
    #[cfg(not(windows))]
    {
        let nested = success(&dir, &["search", "nested", "--mode", "text"]);
        assert!(
            nested["results"]
                .as_array()
                .unwrap()
                .iter()
                .any(|row| row["title"] == "deep.md")
        );
    }

    fs::write(
        kio_dir(&dir).join("config.toml"),
        "[scope]\nindex_vcs_repos = true\nignore = [\"ignored\"]\n",
    )
    .unwrap();
    #[cfg(not(windows))]
    let opted_in = success(&dir, &["index", "--offline", "--approve"]);
    #[cfg(windows)]
    let opted_in = {
        let (code, output) = run(&dir, &["index", "--offline", "--approve"]);
        assert_eq!(code, 3, "{output}");
        assert_windows_bound_children_unsupported(
            &output,
            &["ordinary", "ordinary/nested", "git-dir", "git-file/inner"],
        );
        output
    };
    #[cfg(not(windows))]
    assert!(dir.path().join("git-dir/.kio").is_dir());
    #[cfg(not(windows))]
    assert!(dir.path().join("git-file/inner/.kio").is_dir());
    #[cfg(windows)]
    assert!(
        !dir.path().join("ordinary/.kio").exists()
            && !dir.path().join("ordinary/nested/.kio").exists()
            && !dir.path().join("git-dir/.kio").exists()
            && !dir.path().join("git-file/inner/.kio").exists(),
        "VCS opt-in must not bypass the retained-handle requirement for any planned child"
    );
    assert!(
        opted_in["child_scopes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|row| {
                row["path"] == "git-dir"
                    && row["status"]
                        == if cfg!(windows) {
                            "skipped_error"
                        } else {
                            "indexed"
                        }
            })
    );
    assert!(
        opted_in["child_scopes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|row| row["path"] == "ignored" && row["status"] == "skipped_ignored")
    );
    assert!(
        !dir.path().join("git-file/.kio").exists(),
        "a gitfile marker alone is not file-bearing"
    );
}

#[test]
fn qb15_parent_ignore_is_persisted_and_excludes_child_cas() {
    let dir = tempfile::tempdir().unwrap();
    fs::create_dir_all(dir.path().join("project")).unwrap();
    fs::write(dir.path().join("project/private.md"), "private").unwrap();
    fs::write(dir.path().join("project/public.md"), "public").unwrap();
    success(&dir, &["init"]);
    fs::write(
        kio_dir(&dir).join("config.toml"),
        "[scope]\nignore = [\"project/private.md\"]\n",
    )
    .unwrap();

    #[cfg(not(windows))]
    success(&dir, &["index", "--offline", "--approve"]);
    #[cfg(windows)]
    {
        let (code, output) = run(&dir, &["index", "--offline", "--approve"]);
        assert_eq!(code, 3, "{output}");
        assert_windows_bound_children_unsupported(&output, &["project"]);
    }
    let child_kio = dir.path().join("project/.kio");
    #[cfg(windows)]
    {
        assert!(
            !child_kio.exists(),
            "an unsupported child must not receive a pathname-based .kio store"
        );
        let status = success(&dir, &["status"]);
        assert!(status["tasks"].as_array().unwrap().iter().all(|task| {
            !task["input_path"]
                .as_str()
                .is_some_and(|path| path.starts_with("project/"))
        }));
        let parent_store = ObjectStore::new(&kio_dir(&dir));
        assert!(
            !parent_store
                .object_path(ObjectKind::Raw, &hash_bytes(b"public"))
                .unwrap()
                .exists()
        );
        assert!(
            !parent_store
                .object_path(ObjectKind::Raw, &hash_bytes(b"private"))
                .unwrap()
                .exists()
        );
    }
    #[cfg(not(windows))]
    {
        let child_config = fs::read_to_string(child_kio.join("config.toml")).unwrap();
        assert!(child_config.contains("generated_parent_policy"));
        assert!(child_config.contains("scope_prefix = \"project\""));
        let store = ObjectStore::new(&child_kio);
        assert!(
            store
                .object_path(ObjectKind::Raw, &hash_bytes(b"public"))
                .unwrap()
                .exists()
        );
        assert!(
            !store
                .object_path(ObjectKind::Raw, &hash_bytes(b"private"))
                .unwrap()
                .exists()
        );
    }
}

/// QB19: a purge's device/scope scrub exclusions suppress only the matching
/// best-effort search log append. Search itself remains successful; after each
/// lock is released its corresponding log starts growing again.
#[test]
fn qb19_scrub_lock_contention_suppresses_only_matching_search_log_append() {
    let (dir, _pointer) = fixture();
    let metrics = dir.path().join(".test-data/kio/logs/metrics.jsonl");
    let access = kio_dir(&dir).join("logs/access.jsonl");
    let metrics_before = fs::metadata(&metrics).unwrap().len();
    let access_before = fs::metadata(&access).unwrap().len();

    let device_lock =
        StoreLock::acquire_path(dir.path().join(".test-data/kio/logs/scrub.lock")).unwrap();
    success(&dir, &["search", "3600", "--mode", "text"]);
    assert_eq!(fs::metadata(&metrics).unwrap().len(), metrics_before);
    assert!(fs::metadata(&access).unwrap().len() > access_before);
    drop(device_lock);
    success(&dir, &["search", "3600", "--mode", "text"]);
    let metrics_after_device_release = fs::metadata(&metrics).unwrap().len();
    assert!(metrics_after_device_release > metrics_before);

    let access_before_scope_lock = fs::metadata(&access).unwrap().len();
    let scope_lock = StoreLock::acquire_path(kio_dir(&dir).join("logs/access.scrub.lock")).unwrap();
    success(&dir, &["search", "3600", "--mode", "text"]);
    assert!(fs::metadata(&metrics).unwrap().len() > metrics_after_device_release);
    assert_eq!(
        fs::metadata(&access).unwrap().len(),
        access_before_scope_lock
    );
    drop(scope_lock);
    success(&dir, &["search", "3600", "--mode", "text"]);
    assert!(fs::metadata(&access).unwrap().len() > access_before_scope_lock);
}

/// QB20: a symlink inside the scope is never ingested.
#[cfg(unix)]
#[test]
fn qb20_symlink_ingest_is_skipped() {
    let dir = tempfile::tempdir().unwrap();
    let outside = tempfile::tempdir().unwrap();
    let target = outside.path().join("outside.md");
    fs::write(&target, "# Outside\n\nsymlink-only token\n").unwrap();
    std::os::unix::fs::symlink(&target, dir.path().join("linked.md")).unwrap();
    success(&dir, &["init"]);
    success(&dir, &["index", "--offline", "--approve"]);

    let search = success(&dir, &["search", "symlink-only", "--mode", "text"]);
    assert!(search["results"].as_array().unwrap().is_empty(), "{search}");
}

/// QB23: `kio index` and `kio open` both refuse a bare, argument-less
/// invocation in a non-interactive environment with exit 2
/// (`KIO-E-CONFIG-USAGE-001`) — the lowest-friction entry points require an
/// explicit `--approve`/`--yes` or a pointer argument, matching the
/// documented `kio index --approve` / `kio open <pointer>` entry gate.
#[test]
fn qb23_index_and_open_reject_bare_invocation_exit_2() {
    let dir = tempfile::tempdir().unwrap();
    kio(&dir, &["init"]).arg("--json").assert().success();
    fs::write(dir.path().join("a.md"), "# A\n\nbody\n").unwrap();

    let (code, err) = run(&dir, &["index"]);
    assert_eq!(code, 2, "{err}");
    assert_eq!(err["error_code"], "KIO-E-CONFIG-USAGE-001");

    let (code, err) = run(&dir, &["open"]);
    assert_eq!(code, 2, "{err}");
    assert_eq!(err["error_code"], "KIO-E-CONFIG-USAGE-001");
}

// ===========================================================================
// §C — J 領域 (QB25-QB49, exit/error/log/config/CAS-schema slice)
// ===========================================================================

/// QB31: a newly initialized source index has executable FTS/vector tables
/// with the frozen tokenizer and embedding schema.
#[test]
fn qb31_chunk_fts_and_chunk_vec_schema_is_executable() {
    let dir = tempfile::tempdir().unwrap();
    success(&dir, &["init"]);
    success(&dir, &["index", "--offline", "--approve"]);
    let conn = rusqlite::Connection::open(kio_dir(&dir).join("index/sqlite.db")).unwrap();
    let table_sql = |name: &str| {
        conn.query_row(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?1",
            [name],
            |row| row.get::<_, String>(0),
        )
        .unwrap()
    };
    let fts = table_sql("chunk_fts");
    assert!(fts.contains("tokenize='trigram'"), "{fts}");
    let vectors = table_sql("chunk_vec");
    assert!(
        vectors.contains("embedding float[768] distance_metric=cosine"),
        "{vectors}"
    );
    assert!(table_sql("image_vec").contains("embedding float[768]"));
}

/// QB37: non-current tables stay absent, while unit and commit-type contracts are
/// enforced by their public runtime APIs.
#[test]
fn qb37_non_current_tables_are_absent_from_runtime_schema() {
    let dir = tempfile::tempdir().unwrap();
    success(&dir, &["init"]);
    success(&dir, &["index", "--offline", "--approve"]);
    let conn = rusqlite::Connection::open(kio_dir(&dir).join("index/sqlite.db")).unwrap();
    for table in ["files", "normalization_runs", "prepared_units", "commits"] {
        let exists: bool = conn
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?1)",
                [table],
                |row| row.get(0),
            )
            .unwrap();
        assert!(!exists, "retired table {table} must not exist");
    }

    assert_eq!(
        kio_pipeline::prepare::unit_ref("ページ:1"),
        "92a7e22e53c4cde7",
        "unit references are frozen SHA-256 prefixes of UTF-8 unit keys"
    );
    assert!(
        kio_core::dag::CommitType::from_str("invalid").is_err(),
        "invalid commit types must be rejected before a commit is constructed"
    );
    let hash = format!("sha256:{}", "a".repeat(64));
    let invalid_purged = kio_core::dag::CommitObject {
        commit_type: kio_core::dag::CommitType::Purged,
        created_at: "2026-01-01T00:00:00Z".to_owned(),
        message: "purge".to_owned(),
        object_type: "commit".to_owned(),
        parents: Vec::new(),
        stats: kio_core::dag::CommitStats {
            files_added: 0,
            files_modified: 0,
            files_deleted: 0,
        },
        tool_lock_hash: hash.clone(),
        tree: hash,
        purged_raws: Vec::new(),
    };
    assert!(
        invalid_purged.validate().is_err(),
        "commit-type-specific invariants are validated at the public object boundary"
    );
}

// ===========================================================================
// §D — `kio log --at/--since` 本実装 (QB50-QB58, 裁定5)
// ===========================================================================

/// One `kio index --offline --approve` snapshot pinned to `fixed_now`,
/// returning its commit_hash. Distinct content each call (via `content`) so
/// every call produces a genuinely new commit (no-op detection would
/// otherwise skip an unchanged tree).
fn index_at(dir: &TempDir, fixed_now: &str, content: &str) -> String {
    fs::write(dir.path().join("a.md"), content).unwrap();
    let output = kio(dir, &["index", "--offline", "--approve"])
        .env("KIO_FIXED_NOW", fixed_now)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let value: Value = serde_json::from_slice(&output).unwrap();
    value["commit_hash"].as_str().unwrap().to_owned()
}

/// 3 auto-snapshot commits C1 -> C2 -> C3(HEAD), each with a distinct
/// `created_at`, oldest to newest.
fn three_commit_history() -> (TempDir, [String; 3]) {
    let dir = tempfile::tempdir().unwrap();
    kio(&dir, &["init"]).arg("--json").assert().success();
    let c1 = index_at(&dir, "2026-01-01T00:00:00Z", "# A\n\nv1\n");
    let c2 = index_at(&dir, "2026-01-08T00:00:00Z", "# A\n\nv2\n");
    let c3 = index_at(&dir, "2026-01-15T00:00:00Z", "# A\n\nv3\n");
    (dir, [c1, c2, c3])
}

fn log_commit_hashes(response: &Value) -> Vec<String> {
    response["commits"]
        .as_array()
        .unwrap()
        .iter()
        .map(|entry| entry["commit_hash"].as_str().unwrap().to_owned())
        .collect()
}

/// QB50: `--at <commit>` moves the history walk's origin from HEAD to that
/// commit — `entries` becomes that commit and its ancestors only, excluding
/// any descendant (HEAD itself, when `--at` names a strict ancestor).
#[test]
fn qb50_at_moves_the_walk_origin_and_excludes_descendants() {
    let (dir, [c1, c2, c3]) = three_commit_history();
    let response = success(&dir, &["log", "--at", &c2]);
    let hashes = log_commit_hashes(&response);
    assert_eq!(hashes, vec![c2.clone(), c1.clone()], "{response}");
    assert!(
        !hashes.contains(&c3),
        "HEAD (C3) must be excluded: {response}"
    );
}

/// QB51(a) [recommended interpretation]: a `--at` target whose commit object
/// is present but tree is discarded (genuinely shallow) still resolves —
/// `log` only walks the commit-object parent chain, never a tree, so tree
/// discard is irrelevant to it (unlike `restore`/`search --at`).
#[test]
fn qb51_at_shallow_commit_tree_discarded_still_resolves() {
    let (dir, [c1, c2, _c3]) = three_commit_history();
    let store = ObjectStore::new(dir.path().join(".kio"));
    let repo = Repository::open(dir.path()).unwrap();
    let c2_commit = repo.read_commit(&c2).unwrap();
    // Discard C2's tree object only — its commit object (and C1's) stay intact.
    fs::remove_file(
        store
            .object_path(ObjectKind::Tree, &c2_commit.tree)
            .unwrap(),
    )
    .unwrap();

    let response = success(&dir, &["log", "--at", &c2]);
    let hashes = log_commit_hashes(&response);
    assert_eq!(hashes, vec![c2, c1], "{response}");
    assert_eq!(response["truncated"], false, "{response}");
}

/// QB52: `--since <dur>` filters the walked entries to
/// `commit.created_at >= now - <dur>`, keeping the default HEAD-rooted walk
/// origin (no `--at`).
#[test]
fn qb52_since_filters_by_commit_created_at() {
    let (dir, [_c1, c2, c3]) = three_commit_history();
    // "now" = C3's timestamp; 8 days back excludes C1 (7 days before C2, 14
    // before C3) but keeps C2 (7 days before C3) and C3 itself.
    let response = kio(&dir, &["log", "--since", "8d"])
        .env("KIO_FIXED_NOW", "2026-01-15T00:00:00Z")
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let response: Value = serde_json::from_slice(&response).unwrap();
    let hashes = log_commit_hashes(&response);
    assert_eq!(hashes, vec![c3, c2], "{response}");
}

/// QB53 [regression-lock]: `kio log` with neither flag is unchanged — HEAD
/// origin, all 3 commits, `truncated: false`.
#[test]
fn qb53_no_flags_is_unchanged_head_rooted_walk() {
    let (dir, [c1, c2, c3]) = three_commit_history();
    let response = success(&dir, &["log"]);
    assert_eq!(log_commit_hashes(&response), vec![c3, c2, c1]);
    assert_eq!(response["truncated"], false);
}

/// QB54: `--at` accepts the same HEAD/tag/full-hash operand grammar `diff`
/// already uses (`Repository::resolve_commit`).
#[test]
fn qb54_at_accepts_head_tag_and_full_hash() {
    let (dir, [c1, c2, _c3]) = three_commit_history();
    success(&dir, &["tag", "checkpoint", &c2]);

    let via_hash = success(&dir, &["log", "--at", &c2]);
    assert_eq!(log_commit_hashes(&via_hash), vec![c2.clone(), c1.clone()]);

    let via_tag = success(&dir, &["log", "--at", "checkpoint"]);
    assert_eq!(log_commit_hashes(&via_tag), vec![c2, c1]);

    let via_head = success(&dir, &["log", "--at", "HEAD"]);
    assert_eq!(via_head["commits"], via_head["commits"].clone());
    assert_eq!(
        log_commit_hashes(&via_head).len(),
        3,
        "HEAD resolves to C3, the full 3-commit history: {via_head}"
    );
}

/// QB55 (裁定5 recommendation (a)): `--at` + `--since` compose as an
/// intersection — `--at` picks the walk's origin, `--since` further narrows
/// that origin's own history by timestamp.
#[test]
fn qb55_at_and_since_compose_as_intersection() {
    let (dir, [c1, c2, c3]) = three_commit_history();
    // --at C3 (HEAD) narrowed by --since (now = C3's time, cutoff excludes C1).
    let response = kio(&dir, &["log", "--at", &c3, "--since", "8d"])
        .env("KIO_FIXED_NOW", "2026-01-15T00:00:00Z")
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let response: Value = serde_json::from_slice(&response).unwrap();
    assert_eq!(
        log_commit_hashes(&response),
        vec![c3, c2.clone()],
        "{response}"
    );

    // --at C2 (excludes C3 as a walk origin) + generous --since (keeps C1, C2).
    let response = kio(&dir, &["log", "--at", &c2, "--since", "30d"])
        .env("KIO_FIXED_NOW", "2026-01-15T00:00:00Z")
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let response: Value = serde_json::from_slice(&response).unwrap();
    assert_eq!(log_commit_hashes(&response), vec![c2, c1], "{response}");
}

/// QB56: `--since` reuses search's duration grammar — `7d`/`24h` accepted,
/// an unparseable string rejected with `KIO-E-CONFIG-USAGE-001` / exit 2.
#[test]
fn qb56_since_duration_grammar() {
    let (dir, _hashes) = three_commit_history();
    success(&dir, &["log", "--since", "7d"]);
    success(&dir, &["log", "--since", "24h"]);
    let (code, err) = run(&dir, &["log", "--since", "not-a-duration"]);
    assert_eq!(code, 2, "{err}");
    assert_eq!(err["error_code"], "KIO-E-CONFIG-USAGE-001");
}

/// QB57 [regression-lock]: `--at`/`--since` narrow which commits are listed
/// but do not change the response shape — `commits` (array) and `truncated`
/// (boolean) remain the two top-level keys.
#[test]
fn qb57_json_shape_is_unchanged_by_at_and_since() {
    let (dir, [_c1, c2, _c3]) = three_commit_history();
    for args in [
        vec!["log", "--at", c2.as_str()],
        vec!["log", "--since", "7d"],
    ] {
        let response = success(&dir, &args);
        let object = response.as_object().unwrap();
        let mut keys: Vec<&str> = object.keys().map(String::as_str).collect();
        keys.sort_unstable();
        assert_eq!(keys, vec!["commits", "truncated"], "{response}");
        assert!(response["commits"].is_array());
        assert!(response["truncated"].is_boolean());
    }
}

/// QB58 [verified against the real precedent it cites, superseding the task
/// doc's original exit-2 guess]: `--at` with a well-formed-but-unresolvable
/// commit hash reuses `Repository::resolve_commit` — the SAME function
/// `diff`/`tag`/`restore` already use for their own commit operands — so it
/// gets the IDENTICAL classification those commands already give an unknown
/// hash: `KIO-E-COMMIT-SHALLOW-001` (a hash that resolves to no commit
/// object folds into "shallow" there, R17-5), not a bespoke
/// `KIO-E-CONFIG-USAGE-001`. This is the strongest form of the contract's
/// own justification ("diff の commit 解決失敗時の扱いと同型であるべき") —
/// literal parity with `diff`'s real behavior for the same operand.
#[test]
fn qb58_at_with_unresolvable_hash_matches_diffs_own_classification() {
    let (dir, _hashes) = three_commit_history();
    let unknown_hash = format!("sha256:{}", "ab".repeat(32));

    let (code, err) = run(&dir, &["log", "--at", &unknown_hash]);
    let (diff_code, diff_err) = run(&dir, &["diff", &unknown_hash, "HEAD"]);
    assert_eq!(
        err["error_code"], diff_err["error_code"],
        "{err} vs {diff_err}"
    );
    assert_eq!(code, diff_code);
    assert_eq!(err["error_code"], "KIO-E-COMMIT-SHALLOW-001", "{err}");
}

// ===========================================================================
// §E — P2 繰越 (QB59-QB66)
// ===========================================================================

fn index_metadata_row(dir: &TempDir) -> (String, i64) {
    let db_path = dir.path().join(".kio/index/sqlite.db");
    let conn = rusqlite::Connection::open(db_path).unwrap();
    conn.query_row(
        "SELECT index_generation, last_lifecycle_epoch FROM index_metadata WHERE id = 1",
        [],
        |row| Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?)),
    )
    .unwrap()
}

/// QB61 (PC20 note-2 / §R ruling: coexistence, not merger): a tombstone
/// lifecycle event (here, a purge-then-resurrection retire) advances BOTH
/// `index_metadata.last_lifecycle_epoch` (the tombstone-lifecycle
/// crash-safety counter) AND `index_metadata.index_generation` (PC20's
/// cursor-invalidation ULID) — neither subsumes the other.
#[test]
fn qb61_lifecycle_retire_advances_both_index_generation_and_last_lifecycle_epoch() {
    let dir = tempfile::tempdir().unwrap();
    let bytes = b"# Resurrection\n\nQB61 lifecycle coexistence probe\n";
    let raw_hash = hash_bytes(bytes);
    fs::write(dir.path().join("doc.md"), bytes).unwrap();
    success(&dir, &["init"]);
    success(&dir, &["index", "--offline", "--approve"]);
    let (generation_before, epoch_before) = index_metadata_row(&dir);

    fs::remove_file(dir.path().join("doc.md")).unwrap();
    success(
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
    fs::write(dir.path().join("doc.md"), bytes.as_slice()).unwrap();
    let index_output = success(&dir, &["index", "--offline", "--approve"]);
    assert!(index_output.get("error_code").is_none(), "{index_output}");

    let (generation_after, epoch_after) = index_metadata_row(&dir);
    assert_ne!(
        generation_before, generation_after,
        "index_generation must rotate on the retiring write"
    );
    assert!(
        epoch_after > epoch_before,
        "last_lifecycle_epoch must advance too (before={epoch_before}, after={epoch_after})"
    );
}

/// QB29(a)(b) + QB32: `chunks.chunk_id` / `embeddings.id` are
/// `NOT NULL PRIMARY KEY` (a rowid table's bare `TEXT PRIMARY KEY` does not
/// itself imply NOT NULL), and `idx_embeddings_type` supports bounded
/// target-type lookups without scanning the whole table.
#[test]
fn qb29_qb32_chunks_and_embeddings_ddl_and_target_type_index() {
    let (dir, _pointer) = fixture();
    let db_path = dir.path().join(".kio/index/sqlite.db");
    let conn = rusqlite::Connection::open(db_path).unwrap();
    let chunks_sql: String = conn
        .query_row(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='chunks'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert!(
        chunks_sql.contains("chunk_id TEXT NOT NULL PRIMARY KEY"),
        "{chunks_sql}"
    );
    let embeddings_sql: String = conn
        .query_row(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='embeddings'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert!(
        embeddings_sql.contains("id TEXT NOT NULL PRIMARY KEY"),
        "{embeddings_sql}"
    );
    let index_exists: Option<String> = conn
        .query_row(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_embeddings_type'",
            [],
            |row| row.get(0),
        )
        .optional()
        .unwrap();
    assert!(index_exists.is_some(), "idx_embeddings_type must exist");
}

/// `[observability] retention_days` is the sole canonical retention key and is
/// accepted by the strict config schema.
#[test]
fn qb18_observability_retention_days_is_the_canonical_key() {
    let (dir, _pointer) = fixture();
    fs::write(
        dir.path().join(".kio/config.toml"),
        "[observability]\nretention_days = 60\n",
    )
    .unwrap();
    success(&dir, &["status"]);
    success(&dir, &["search", "3600"]);
}
