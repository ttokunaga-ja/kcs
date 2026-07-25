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
//! eval/run_eval.py Recall@10 projection fix lives in `eval/run_eval.py` /
//! `eval/test_run_eval.py`, not here (Python, not a CLI contract).
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
//! query_cache SQL read/write, embedding CAS byte reformat, tree
//! chunking_config_hash/chunk_set_hash fields, diff derived-only detection,
//! `parent_instance`, auto gen+1 on prepared_hash change, the 9-state
//! `up_to_date` machine, tool_lock_hash no-op comparison, batch resume/retry
//! auto-snapshot wiring, manifest/toollock CAS write timing, `.kio/staging/`
//! descriptor publish, tag simple-case-folding, view assembly `order`
//! uniqueness + percent-encoding, registry move-nonqualify + path validation
//! extension), QB59/QB60 (PC20 rotation-point tracing for embedding-
//! enrichment-finalize / index-batch-finalize), QB62-QB66 (query_cache
//! multi-scope reuse and PC33/44 per-binding chunking-config wiring — both
//! need QB33/34/64/65's infra first).

use std::fs;

use assert_cmd::Command;
use kio_core::cas::{hash_bytes, ObjectKind, ObjectStore};
use kio_core::purge::{PurgeReason, PurgeState, TombstoneMode};
use kio_core::scope::Repository;
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

    // Structural half of the claim: `take_exit_override` is the ONE place
    // that turns a success payload into a non-zero exit, and it reads only
    // the private `__exit_code` marker — never `error_code`.
    let source = fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/src/main.rs")).unwrap();
    let take_exit_override = source
        .split("fn take_exit_override")
        .nth(1)
        .and_then(|rest| rest.split("\n}\n").next())
        .expect("take_exit_override body");
    assert!(
        !take_exit_override.contains("\"error_code\""),
        "take_exit_override must not branch on error_code"
    );
}

/// QB3(a) [regression-lock]: a non-multimodal embedding profile is rejected
/// at tool-lock materialize time with `KIO-E-EMBED-MODALITY-001` / exit 2.
#[test]
fn qb3a_non_multimodal_embedding_profile_rejected_exit_2() {
    let source = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../kio-adapter/src/tool_lock.rs"
    ))
    .unwrap();
    assert!(
        source.contains("KIO-E-EMBED-MODALITY-001"),
        "tool_lock.rs must still reject non-multimodal profiles"
    );
}

/// QB3(b) [regression-lock]: `fallback_reason` is a free-form `Option<String>`
/// (open vocabulary), not a closed enum — no schema/type constrains its
/// values.
#[test]
fn qb3b_fallback_reason_is_open_vocabulary_string() {
    let source = fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/src/main.rs")).unwrap();
    assert!(
        source.contains("fallback_reason"),
        "fallback_reason field must exist"
    );
    // No enum type named after fallback_reason exists to constrain it.
    assert!(!source.contains("enum FallbackReason"));
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

/// QB11 [regression-lock, structural]: `.kio/.lock` (`repo.lock_store()`) is
/// acquired exactly at the top of `run_index`/`run_repair`/`run_reindex`/
/// `run_batch` (covering batch resume/retry/abandon, which share `run_batch`'s
/// one lock guard across their dispatch) and nowhere in the `open`/`view`
/// resolution paths. A functional two-process race for one representative
/// pair (`reindex` vs `open`) backs this structural read.
#[test]
fn qb11_lock_store_call_sites_are_write_commands_only() {
    let source = fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/src/main.rs")).unwrap();
    for needle in [
        "fn run_index(",
        "fn run_repair(",
        "fn run_reindex(",
        "fn run_batch(",
    ] {
        let body = source
            .split(needle)
            .nth(1)
            .unwrap_or_else(|| panic!("{needle} not found"));
        let head = &body[..body.len().min(1500)];
        assert!(
            head.contains("lock_store()"),
            "{needle} must acquire the store lock near its top"
        );
    }
    for needle in [
        "fn resolve_pointer_for_cli(",
        "fn resolve_object_uri(",
        "fn resolve_short_hash_command(",
    ] {
        let body = source
            .split(needle)
            .nth(1)
            .unwrap_or_else(|| panic!("{needle} not found"));
        // Stop at the next top-level `fn` to bound the search to this function.
        let end = body.find("\nfn ").unwrap_or(body.len());
        assert!(
            !body[..end].contains("lock_store()"),
            "{needle} (open/view resolution) must not acquire the store lock"
        );
    }
}

/// QB12 [regression-lock, structural]: `kio purge`'s lock acquisition order
/// is scope-store -> purge-publication -> device-scrub -> scope-access
/// (`execute_phase_machine` acquires the first two and stays in scope
/// through `execute_visible_phases` -> `scrub_logs`, which acquires the
/// latter two — genuine nesting, not just textual sequence). 裁定3(a):
/// cost-ledger's `BEGIN IMMEDIATE` Tx (`kio_pipeline::ledger::ops`) never
/// acquires a scope `StoreLock` while open — `kio-pipeline` has no
/// `StoreLock` dependency at all, so the forbidden reverse order (Tx held ->
/// store lock taken) is structurally impossible from within that crate, and
/// none of `kio-cli`'s 4 `with_immediate_transaction` call sites nest a
/// `StoreLock`/`lock_store` acquisition inside the transaction closure.
#[test]
fn qb12_purge_lock_order_and_no_reverse_cost_ledger_acquisition() {
    let purge_source =
        fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/src/purge.rs")).unwrap();
    let store_lock_pos = purge_source
        .find("let _store_lock = repo.lock_store()?;")
        .unwrap();
    let publication_lock_pos = purge_source
        .find("let _publication_lock = StoreLock::acquire_path(purge_publication_lock_path")
        .unwrap();
    let device_lock_pos = purge_source
        .find("let _device_lock = StoreLock::acquire_path(device_root.join(\"scrub.lock\"))")
        .unwrap();
    let scope_lock_pos = purge_source
        .find("let _scope_lock = StoreLock::acquire_path(scope_root.join(\"access.scrub.lock\"))")
        .unwrap();
    assert!(
        store_lock_pos < publication_lock_pos,
        "store before publication"
    );
    assert!(
        publication_lock_pos < device_lock_pos,
        "publication before device-scrub"
    );
    assert!(
        device_lock_pos < scope_lock_pos,
        "device-scrub before scope-access"
    );

    // 裁定3(a): kio-pipeline (the cost-ledger crate) never references StoreLock.
    let ledger_source = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../kio-pipeline/src/ledger/ops.rs"
    ))
    .unwrap();
    assert!(!ledger_source.contains("StoreLock"));

    // None of main.rs's `with_immediate_transaction` call sites nest a
    // StoreLock acquisition inside the closure — checked by bounding each
    // call site to the next top-level `}` at column 0 (the closure/statement
    // end) and confirming no known StoreLock call text occurs before it.
    let main_source =
        fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/src/main.rs")).unwrap();
    let mut search_from = 0;
    let mut found = 0;
    while let Some(offset) = main_source[search_from..].find("with_immediate_transaction(") {
        let start = search_from + offset;
        let end = main_source[start..]
            .find("\n}\n")
            .map(|relative| start + relative)
            .unwrap_or(main_source.len());
        let span = &main_source[start..end];
        assert!(
            !span.contains("StoreLock") && !span.contains("lock_store()"),
            "with_immediate_transaction at byte {start} must not nest a StoreLock acquisition"
        );
        found += 1;
        search_from = start + "with_immediate_transaction(".len();
    }
    assert!(found >= 4, "expected at least 4 call sites, found {found}");
}

/// QB14(a) [regression-lock]: no full-disk-walk crate (`walkdir` or similar
/// recursive-descent dependency) is linked into the workspace — registry
/// re-registration can only happen one `kio index` root at a time.
#[test]
fn qb14a_no_full_disk_walk_dependency() {
    let lockfile =
        fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../Cargo.lock")).unwrap();
    assert!(
        !lockfile.contains("name = \"walkdir\""),
        "no crate may perform an unbounded recursive filesystem walk"
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
}

/// QB15 (weak subset — the child-`.kio`-generation mechanism itself does not
/// exist yet, per the task's own note): `[scope] index_vcs_repos` is not yet
/// declared in `config.schema.json`, confirming the spec-gap's premise this
/// contract pins for later implementation.
#[test]
fn qb15_index_vcs_repos_schema_key_not_yet_declared() {
    let schema = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../kio-core/schemas/config.schema.json"
    ))
    .unwrap();
    assert!(
        !schema.contains("index_vcs_repos"),
        "index_vcs_repos is not implemented yet; this test must be updated when it lands"
    );
}

/// QB19 [regression-lock, structural]: scope-local `access.jsonl` and
/// device-global `metrics.jsonl` both append through the SAME rotating
/// writer (`append_jsonl_cli` -> `kio_core::scope::append_jsonl_rotating`) —
/// access.jsonl does not have a separate, rotation-less code path.
#[test]
fn qb19_access_jsonl_shares_device_global_rotation_writer() {
    let source = fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/src/main.rs")).unwrap();
    assert_eq!(
        source.matches("fn append_jsonl_cli(").count(),
        1,
        "exactly one rotating-jsonl writer function"
    );
    let append_search_logs = source
        .split("fn append_search_logs(")
        .nth(1)
        .and_then(|rest| rest.split("\nfn ").next())
        .expect("append_search_logs body");
    assert!(append_search_logs.contains("kio/logs/metrics.jsonl"));
    assert!(append_search_logs.contains("logs/access.jsonl"));
    // Both writes go through `append_jsonl_cli` (grep count == 2 within this
    // one function: one for metrics, one for access).
    assert_eq!(append_search_logs.matches("append_jsonl_cli(").count(), 2);
}

/// QB20 [regression-lock]: a symlink inside the scope is never ingested —
/// `open_scope_file_nofollow`'s lstat -> `O_NOFOLLOW` open -> fstat-identity
/// 3-stage check (scope.rs) backs this; functionally, an existing sibling
/// test (`contract_cli.rs::s5_symlink_is_skipped_with_warning`) already
/// covers the CLI-visible half. This test pins the structural mechanism.
#[test]
fn qb20_symlink_ingest_uses_lstat_then_nofollow_open_then_fstat_identity() {
    let source = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../kio-core/src/scope.rs"
    ))
    .unwrap();
    let body = source
        .split("fn open_scope_file_nofollow(")
        .nth(1)
        .and_then(|rest| rest.split("\nfn ").next())
        .expect("open_scope_file_nofollow body");
    assert!(body.contains("symlink_metadata"), "must lstat first");
    assert!(
        body.contains("configure_scope_no_follow"),
        "must open with O_NOFOLLOW semantics"
    );
    assert!(
        body.contains("same_scope_file_identity") || body.contains("same_identity"),
        "must verify post-open identity (fstat-equivalent) before trusting the read"
    );
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

/// QB31 [regression-lock]: `chunk_fts`'s `tokenize=` clause is always an
/// interpolated, executable value (never a literal placeholder string), and
/// `chunk_vec`'s embedding column is a fixed `float[768] distance_metric=cosine`.
#[test]
fn qb31_chunk_fts_and_chunk_vec_ddl_are_executable() {
    let source = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../kio-index/src/fts.rs"
    ))
    .unwrap();
    assert!(source.contains("tokenize='{tokenizer}'"));
    assert!(
        !source.contains("tokenize='<"),
        "no literal placeholder token"
    );
    assert!(source.contains("embedding float[{CHUNK_VEC_DIMENSIONS}] distance_metric=cosine"));
    assert!(source.contains("pub const CHUNK_VEC_DIMENSIONS: usize = 768;"));
}

/// QB37 [regression-lock, 3 subclaims compressed into 1]: (a) the legacy
/// `files`/`normalization_runs`/`prepared_units`/`commits` SQLite tables are
/// not defined anywhere in the schema; (b) `unit_ref` hashes
/// `unit_key.as_bytes()` directly (Rust `&str`'s UTF-8 guarantee IS the
/// "regulated normalization, then UTF-8 bytes" preimage rule); (c)
/// `CommitObject::validate` is the sole `commit_type` enforcement point —
/// there is no SQLite `commits` table to carry a parallel CHECK constraint.
#[test]
fn qb37_legacy_tables_absent_unit_ref_is_utf8_bytes_commit_type_single_validator() {
    let fts_source = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../kio-index/src/fts.rs"
    ))
    .unwrap();
    for table in ["files", "normalization_runs", "prepared_units", "commits"] {
        assert!(
            !fts_source.contains(&format!("CREATE TABLE IF NOT EXISTS {table} "))
                && !fts_source.contains(&format!("CREATE TABLE {table} ")),
            "table {table} must not exist"
        );
    }

    let prepare_source = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../kio-pipeline/src/prepare.rs"
    ))
    .unwrap();
    assert!(prepare_source.contains("unit_key.as_bytes()"));

    let dag_source = fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../kio-core/src/dag.rs"
    ))
    .unwrap();
    assert!(dag_source.contains("pub fn validate(&self) -> Result<()>"));
    assert!(
        !fts_source.contains("commit_type"),
        "SQLite side must not carry a parallel commit_type constraint"
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
/// itself imply NOT NULL), and `idx_embeddings_type` exists so a
/// `target_type='query_cache'` lookup does not scan the whole table.
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

/// QB18: `[observability] retention_days` is the canonical key (10 §12.3
/// L954) and takes effect — exercised indirectly via the config accepting
/// it without a schema error (the same "previously bricked every command"
/// regression class `[logs] retention_days` was fixed for) and, precisely,
/// by confirming `[observability]` wins over a simultaneously-set `[logs]`.
#[test]
fn qb18_observability_retention_days_is_the_canonical_key() {
    let (dir, _pointer) = fixture();
    fs::write(
        dir.path().join(".kio/config.toml"),
        "[observability]\nretention_days = 60\n",
    )
    .unwrap();
    // A previously-schema-rejected key now runs cleanly end-to-end.
    success(&dir, &["status"]);
    success(&dir, &["search", "3600"]);

    // Both sections set, with different values: [observability] wins.
    fs::write(
        dir.path().join(".kio/config.toml"),
        "[observability]\nretention_days = 90\n[logs]\nretention_days = 7\n",
    )
    .unwrap();
    success(&dir, &["status"]);
}
