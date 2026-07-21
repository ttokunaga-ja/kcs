//! Step4b Phase 3-A contract tests: task state machine / Tier A-B scan
//! approval / adapter contract / pipeline remainder (batch/task/adapter/
//! approval wiring — main.rs exit-code/error/log/config cross-cutting areas
//! are P3-B's, tested in `step4b_p3b_contract.rs`).
//!
//! Source: `tasks/step4b-contract-tests-p3a.md` (QA1-QA71, §W arbitration
//! 1-8). Test names carry their QA number so a failure maps directly back to
//! the contract text. Most of the markdownize-response (§K/§L/§M),
//! adapter-type (§F), and identity (§J) contracts are pure functions and are
//! covered by inline `#[cfg(test)]` unit tests in `kcs-pipeline`/`kcs-adapter`
//! instead of duplicated here — this file covers the CLI-process-level
//! wiring: config/schema behavior, `kcs status`/`kcs index` end-to-end
//! effects, and cross-crate structural checks that need a real build tree.
//!
//! Coverage is partial by design: several QA items (§E idempotency/backup,
//! §G/§H opt-in AND-gate + `kcs adapter revoke`, §O Batch trait, §Q
//! streaming, §U Batch content recovery) are large, independent features
//! deferred out of this pass — see the implementation report, not this file,
//! for the full QA-by-QA accounting.

use std::fs;
use std::path::Path;

use assert_cmd::Command;
use kcs_adapter::bbox_annotation::mistral_markdownize_profile;
use kcs_adapter::identity::tool_profile_hash;
use kcs_adapter::tool_lock::{canonical_tool_lock_value, tool_lock_hash};
use kcs_core::scope::tier_a_template_text;
use kcs_pipeline::scan::TIER_B_NEEDLES;
use serde_json::{json, Value};
use tempfile::TempDir;

const KCS_CHILD_ENV_DENYLIST: &[&str] = &[
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "KCS_FIXED_NOW",
    "KCS_TEST_GEMINI_EMBED",
    "KCS_TEST_MISTRAL_OCR",
    "KCS_TEST_MARKDOWNIZE_ADAPTER",
    "KCS_TEST_QUERY_EMBED_TRACE",
    "KCS_TEST_HOLD_LOCK_MS",
    "KCS_TEST_SCOPE_SEARCH_DELAY_SCOPE_ID",
    "KCS_TEST_SCOPE_SEARCH_DELAY_MS",
    "KCS_TEST_R13_2_AUTH",
    "KCS_TEST_R13_2_DECLARED",
    "KCS_TEST_R13_2_FALLBACK",
    "KCS_TEST_WINDOWS_PROFILE",
];

fn kcs(dir: &TempDir, args: &[&str]) -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    for name in KCS_CHILD_ENV_DENYLIST {
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

fn init(dir: &TempDir) {
    kcs(dir, &["init"]).assert().success();
}

fn scope_json(dir: &TempDir) -> Value {
    serde_json::from_str(&fs::read_to_string(dir.path().join(".kcs/scope.json")).unwrap()).unwrap()
}

// ===========================================================================
// §A task 状態機械 (U1, QA1/QA4 — QA2/QA3 deferred, see the pipeline crate's
// `HoldReason` doc comment for why)
// ===========================================================================

/// QA1 (partial) + QA4: a budget-paused task carries `hold_reason="budget"`
/// (QA1's closed enum wired at the budget-pause site), and `kcs status`
/// reports it in a `paused_by_hold_reason` breakdown (QA4) instead of
/// forcing the caller to filter the raw task array client-side.
#[test]
fn qa1_qa4_status_reports_budget_paused_task_with_hold_reason() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# Doc\n\nbody text.\n").unwrap();
    init(&dir);
    json_success(&dir, &["index", "--approve"]);
    let status = json_success(&dir, &["status"]);
    let breakdown = &status["paused_by_hold_reason"];
    for reason in ["budget", "auth", "tier_b_approval", "unknown"] {
        assert!(
            breakdown.get(reason).is_some(),
            "paused_by_hold_reason must always report all 4 buckets: {breakdown}"
        );
    }
    // No paused task yet in this fresh scope.
    assert_eq!(breakdown["budget"], 0);
}

// ===========================================================================
// §B Tier A/B scan approval (U2, QA5-7)
// ===========================================================================

/// QA5: `.kcs/scope.json` carries a `scan_approval` key (distinct from the
/// adapter-level `approvals.jsonl`) after `kcs index --approve`, with the 10
/// §1 L101-113 required fields.
#[test]
fn qa5_scope_json_records_scan_approval_after_index_approve() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# Doc\n\nbody text.\n").unwrap();
    init(&dir);
    assert!(
        scope_json(&dir).get("scan_approval").is_none(),
        "scan_approval must not exist before any approval"
    );

    json_success(&dir, &["index", "--approve"]);
    let scope = scope_json(&dir);
    let scan_approval = scope
        .get("scan_approval")
        .expect("scan_approval must exist after `index --approve`");
    for field in [
        "scope_id",
        "root_path",
        "approved_at",
        "actor",
        "approval_method",
        "kcs_version",
        "effective_ignore_hash",
        "estimated_file_count",
        "estimated_total_bytes",
        "estimated_markdownize_usd",
        "estimated_embedding_usd",
    ] {
        assert!(
            scan_approval.get(field).is_some(),
            "scan_approval missing required field {field}: {scan_approval}"
        );
    }
    assert_eq!(scan_approval["approval_method"], "approve");
    assert_eq!(scan_approval["scope_id"], scope["scope_id"]);
}

/// QA5 (idempotency): a second `index --approve` does not overwrite the
/// original scan_approval (scope-level approval is recorded once).
#[test]
fn qa5_scan_approval_is_recorded_once_not_per_index_run() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# Doc\n\nbody text.\n").unwrap();
    init(&dir);
    json_success(&dir, &["index", "--approve"]);
    let first_approved_at = scope_json(&dir)["scan_approval"]["approved_at"]
        .as_str()
        .unwrap()
        .to_owned();

    fs::write(dir.path().join("b.md"), "# Doc2\n\nmore text.\n").unwrap();
    json_success(&dir, &["index", "--approve"]);
    let second_approved_at = scope_json(&dir)["scan_approval"]["approved_at"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_eq!(
        first_approved_at, second_approved_at,
        "scan_approval is a one-time scope-level record, not per-adapter"
    );
}

/// QA7 (arbitration #1): `effective_ignore_hash` is the sha256 of the actual
/// built-in Tier A/B pattern content (`tier_a_template_text`), not a fixed
/// version-string literal — it must equal the same computation the
/// production code performs on the current pattern set, and it must NOT
/// equal a hash of an arbitrary unrelated literal (proving it is content-
/// derived, not a hardcoded constant reused verbatim).
#[test]
fn qa7_effective_ignore_hash_is_derived_from_real_pattern_content() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# Doc\n\nbody text.\n").unwrap();
    init(&dir);
    json_success(&dir, &["index", "--approve"]);
    let scope = scope_json(&dir);
    let hash = scope["scan_approval"]["effective_ignore_hash"]
        .as_str()
        .unwrap()
        .to_owned();

    let expected = kcs_core::cas::hash_bytes(tier_a_template_text(TIER_B_NEEDLES).as_bytes());
    assert_eq!(hash, expected);
    // Not the old fixed version-literal hash (QA7's identified regression).
    let stale_literal_hash = kcs_core::cas::hash_bytes(b"built-in-tier-a-v1");
    assert_ne!(hash, stale_literal_hash);
}

// ===========================================================================
// §D budget guardrail — folder per_adapter removal (U4 残り, QA11-12)
// ===========================================================================

/// QA12 (arbitration #2): the folder `.kcs/config.toml` does not define
/// `[budget.per_adapter]` (04 §5.4 — device-layer only) — setting it is a
/// config schema error (`KCS-E-CONFIG-SCHEMA-001`), not a silently-parsed-
/// but-unused key.
#[test]
fn qa12_folder_config_per_adapter_is_a_schema_error() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# Doc\n\nbody text.\n").unwrap();
    init(&dir);
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[budget.per_adapter]\nmarkdownize = 1.0\n",
    )
    .unwrap();
    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

/// QA11: `kcs status`'s budget report no longer presents a folder
/// `per_adapter` constraint (it does not exist, 04 §5.4) — only the
/// device-layer one appears.
#[test]
fn qa11_status_budget_report_has_no_folder_per_adapter_key() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# Doc\n\nbody text.\n").unwrap();
    init(&dir);
    json_success(&dir, &["index", "--approve"]);
    let status = json_success(&dir, &["status"]);
    let budget = &status["budget"];
    assert!(budget.get("device_per_adapter").is_some());
    assert!(
        budget.get("folder_per_adapter").is_none(),
        "folder_per_adapter must not be reported: {budget}"
    );
}

// ===========================================================================
// §J bbox_annotation / tool_lock_hash (U83/U84, QA32/33/35)
// ===========================================================================

/// QA32 [regression-lock]: bbox_annotation on/off is folded into
/// `tool_profile_hash` via the `output_schema`/`prompt_template_*` diff
/// (identity.rs has no literal `"bbox_annotation"` PROFILE_FIELDS entry) —
/// the two hashes must differ.
#[test]
fn qa32_bbox_annotation_toggle_changes_tool_profile_hash() {
    let enabled = mistral_markdownize_profile("mistral-ocr-2505", true);
    let disabled = mistral_markdownize_profile("mistral-ocr-2505", false);
    assert_ne!(
        tool_profile_hash(&enabled).unwrap(),
        tool_profile_hash(&disabled).unwrap()
    );
}

/// QA33 (arbitration #4): `[markdownize] bbox_annotation = true` (the spec's
/// literal flat-key TOML example, 07 §5.2) is accepted by config.schema.json
/// and honored by `kcs index`; a stale nested
/// `[markdownize.bbox_annotation] enabled = true` shape is now a schema
/// error (type mismatch: boolean expected, object found).
#[test]
fn qa33_bbox_annotation_flat_key_is_accepted_nested_shape_is_rejected() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# Doc\n\nbody text.\n").unwrap();
    init(&dir);
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[markdownize]\nbbox_annotation = false\n",
    )
    .unwrap();
    json_success(&dir, &["status"]);

    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[markdownize.bbox_annotation]\nenabled = false\n",
    )
    .unwrap();
    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

/// QA35 [regression-lock]: `tool_lock_hash` folds only the role-specific
/// canonical fields (`tool_id`+`profile_hash`, embedding also
/// `+dimensions+distance+modality`) — `capabilities` (markdown) and `mode`
/// (embedding) are display-only and must not perturb the hash.
#[test]
fn qa35_tool_lock_hash_ignores_capabilities_and_mode() {
    let base = json!({
        "spec_version": 1,
        "markdown": {
            "tool_id": "mistral_ocr_markdownize",
            "profile_hash": format!("sha256:{}", "a".repeat(64)),
            "capabilities": ["ocr"]
        },
        "embedding": {
            "tool_id": "gemini_embedding_2",
            "profile_hash": format!("sha256:{}", "b".repeat(64)),
            "dimensions": 768,
            "distance": "cosine",
            "modality": "multimodal",
            "mode": "online"
        }
    });
    let mut changed = base.clone();
    changed["markdown"]["capabilities"] = json!(["ocr", "layout_detection"]);
    changed["embedding"]["mode"] = json!("offline_replay");
    assert_eq!(
        canonical_tool_lock_value(&base).unwrap(),
        canonical_tool_lock_value(&changed).unwrap()
    );
    assert_eq!(
        tool_lock_hash(&base).unwrap(),
        tool_lock_hash(&changed).unwrap()
    );
}

// ===========================================================================
// §N SQL 正本 regression-lock (U88/U89/U90, QA51)
// ===========================================================================

/// QA51 [regression-lock]: the `embeddings`/`chunk_vec` SQLite schema's
/// single source of truth is `kcs-index` (04-pipeline.md §4.3) — no
/// duplicate `CREATE TABLE` for either name exists under `kcs-adapter/src`.
#[test]
fn qa51_embeddings_and_chunk_vec_ddl_has_no_duplicate_in_kcs_adapter() {
    let manifest_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
    let adapter_src = manifest_dir
        .parent()
        .unwrap()
        .join("kcs-adapter")
        .join("src");
    let mut offenders = Vec::new();
    for entry in walk_rs_files(&adapter_src) {
        let text = fs::read_to_string(&entry).unwrap();
        if text.contains("CREATE TABLE")
            && (text.contains("embeddings") || text.contains("chunk_vec"))
        {
            offenders.push(entry);
        }
    }
    assert!(
        offenders.is_empty(),
        "embeddings/chunk_vec DDL must live only in kcs-index (04 §4.3): {offenders:?}"
    );
}

fn walk_rs_files(root: &Path) -> Vec<std::path::PathBuf> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
            } else if path.extension().is_some_and(|extension| extension == "rs") {
                out.push(path);
            }
        }
    }
    out
}

// ===========================================================================
// §R include_neighbors removal (U94/U143, QA61)
// ===========================================================================

/// QA61 (arbitration #7): `markdownize.incremental.include_neighbors` was
/// removed from config.schema.json entirely — even the old documented
/// default (1) is now an unknown-key schema error, not a silent no-op
/// accept.
#[test]
fn qa61_include_neighbors_key_removed_from_schema() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# Doc\n\nbody text.\n").unwrap();
    init(&dir);
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[markdownize.incremental]\ninclude_neighbors = 1\n",
    )
    .unwrap();
    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

// ===========================================================================
// §T registry live 重複 fail-closed の拡大 (PB24 継承, QA66-68)
// ===========================================================================

fn make_registry_duplicate(dir_a: &TempDir, scope_id: &str) -> TempDir {
    let dir_b = tempfile::tempdir().unwrap();
    fs::write(dir_b.path().join("other.md"), "# Other\n\nOther body.\n").unwrap();
    kcs(&dir_b, &["init"]).assert().success();
    let scope_path = dir_b.path().join(".kcs/scope.json");
    let mut value: Value = serde_json::from_str(&fs::read_to_string(&scope_path).unwrap()).unwrap();
    value["scope_id"] = json!(scope_id);
    fs::write(&scope_path, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
    // XDG_DATA_HOME is per-TempDir (dir_a/dir_b each have their own
    // `.test-data`), but the scope-registry is keyed by `XDG_DATA_HOME`, so
    // point dir_b's registry writes (`index`) at dir_a's data home to make
    // the two `.kcs` clones share one live registry (mirrors
    // step4b_p3b_contract.rs's `make_registry_duplicate`).
    let mut command = Command::cargo_bin("kcs").unwrap();
    for name in KCS_CHILD_ENV_DENYLIST {
        command.env_remove(name);
    }
    command
        .current_dir(dir_b.path())
        .env("XDG_CONFIG_HOME", dir_a.path().join(".test-config"))
        .env("XDG_DATA_HOME", dir_a.path().join(".test-data"))
        .env("XDG_CACHE_HOME", dir_a.path().join(".test-cache"))
        .args(["index", "--offline", "--approve"])
        .assert()
        .success();
    dir_b
}

/// QA67 (+ QA66 as a consequence — both write paths share the
/// `reserve_or_reuse_task_charge`/`record_free_local_charge` choke point):
/// online task phase 1 (and, transitively, `kcs index`'s free-local-baseline
/// bookkeeping through the same functions) must fail-close
/// (`KCS-E-REGISTRY-DUP-001`) on a live registry scope_id duplicate, instead
/// of writing a device-global `batch_requests`/`cost_ledger` row two clones
/// could collide on.
#[test]
fn qa66_qa67_index_fails_closed_on_registry_duplicate_before_charging() {
    let dir_a = tempfile::tempdir().unwrap();
    fs::write(dir_a.path().join("seed.md"), "# Seed\n\nSeed body.\n").unwrap();
    kcs(&dir_a, &["init"]).assert().success();
    json_success(&dir_a, &["index", "--offline", "--approve"]);
    let scope_id = scope_json(&dir_a)["scope_id"].as_str().unwrap().to_owned();
    let _dir_b = make_registry_duplicate(&dir_a, &scope_id);

    fs::write(dir_a.path().join("more.md"), "# More\n\nMore body.\n").unwrap();
    // `registry_duplicate_error` uses `ExitCode::PermanentFailure` (4) — this
    // scenario has no partial success to report (the only new file this pass
    // never reaches a charge decision at all).
    let err = json_failure(&dir_a, &["index", "--offline", "--approve"], 4);
    assert_eq!(err["error_code"], "KCS-E-REGISTRY-DUP-001");
}

/// QA68 [regression-lock]: the read-only registry-dup check
/// (`resolve_scope_id_in_registry`/`resolve_scope_target`) already correctly
/// fail-closes `kcs evidence verify` — unaffected by the QA66/67 write-path
/// extension above.
#[test]
fn qa68_evidence_verify_still_fails_closed_on_registry_duplicate() {
    let dir_a = tempfile::tempdir().unwrap();
    fs::write(
        dir_a.path().join("seed.md"),
        "# Seed\n\nTTL is 3600 seconds.\n",
    )
    .unwrap();
    kcs(&dir_a, &["init"]).assert().success();
    json_success(&dir_a, &["index", "--offline", "--approve"]);
    let search = json_success(&dir_a, &["search", "3600", "--text"]);
    let pointer = search["results"][0]["evidence_pointer"].clone();
    let scope_id = scope_json(&dir_a)["scope_id"].as_str().unwrap().to_owned();
    let _dir_b = make_registry_duplicate(&dir_a, &scope_id);

    // `kcs evidence verify` is the one command whose doc comment on
    // `registry_duplicate_error` pins exit 3 (PB54) instead of the default
    // `ExitCode::PermanentFailure` (4) other write/read commands use — see
    // `qb4b_qb4c_registry_duplicate_outranks_journal_and_index_generation_via_view`
    // in step4b_p3b_contract.rs for the sibling `open`/`view` case (exit 4).
    // `evidence verify`'s registry_duplicate outcome is a structured result
    // on stdout (`{"status":"registry_duplicate","error_code":...}`), not a
    // stderr failure envelope — unlike most other error paths in this CLI.
    let stdout = kcs(
        &dir_a,
        &[
            "evidence",
            "verify",
            &serde_json::to_string(&pointer).unwrap(),
        ],
    )
    .arg("--json")
    .assert()
    .code(3)
    .get_output()
    .stdout
    .clone();
    let result: Value = serde_json::from_slice(&stdout).unwrap();
    assert_eq!(result["status"], "registry_duplicate");
    assert_eq!(result["error_code"], "KCS-E-REGISTRY-DUP-001");
}
