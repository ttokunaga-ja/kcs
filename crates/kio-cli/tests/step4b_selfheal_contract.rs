//! Step4b crash self-heal contract tests: `docs/07-adapter-spec.md` §3
//! L191-206's "途中で crash した中間 (true × 行なし) は、次回実行の self-heal
//! が approval_pending と完全一致する場合に限り行 publish を完遂する" letter
//! — `kio-cli`'s `try_self_heal_network_approval` (the fallthrough
//! `persistent_network_allowed_for_kio_dir` takes when `approval_pending` is
//! present and no `active` row matches).
//!
//! This file is deliberately SEPARATE from `step4b_p3a_contract.rs` (which
//! already owns QA21/22/25/26/27, the materialize/revoke/explicit-approval
//! side of this same 07 §3 area) — harness helpers below are self-contained
//! copies of that file's `kio`/`json_success`/`init`/`scope_json`/
//! `write_scope_allow_network_true`/`fake_pdf` (integration test binaries in
//! this crate do not share a `tests/common` module, so every file carries
//! its own copies; this mirrors the established convention rather than
//! introducing a new one).
//!
//! Every scenario drives the gate through the exact CLI invocation QA21 uses
//! (`kio index --yes`) rather than `--approve`: `--approve` runs the FULL
//! explicit write-order (`publish_online_network_approval`, gated on
//! `args.approve` inside `write_approval_record`) and would overwrite the
//! hand-crafted `approval_pending` fixture before the gate is ever
//! evaluated. `--yes` only unlocks the scan-approval flow (07 §3's (a) path
//! explicitly does NOT accept `--yes`: "対話承認 または --approve。--yes で
//! は成立しない") and leaves `approval_pending`/`approvals`/
//! `approvals_initialized` untouched except through the read+fallthrough
//! gate (`persistent_network_allowed`) this file targets.

use std::fs;
use std::path::PathBuf;

use assert_cmd::Command;
use kio_adapter::catalog::standard_online_markdownize_profile_with_bbox;
use kio_core::scope::{publish_network_approval, write_network_approval_pending};
use serde_json::{json, Value};
use tempfile::TempDir;

const KIO_CHILD_ENV_DENYLIST: &[&str] = &[
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "KIO_FIXED_NOW",
    "KIO_TEST_GEMINI_EMBED",
    "KIO_TEST_MISTRAL_OCR",
    "KIO_TEST_MISTRAL_BATCH",
    "KIO_TEST_MARKDOWNIZE_ADAPTER",
    "KIO_TEST_QUERY_EMBED_TRACE",
    "KIO_TEST_HOLD_LOCK_MS",
    "KIO_TEST_R13_2_AUTH",
    "KIO_TEST_R13_2_DECLARED",
    "KIO_TEST_R13_2_FALLBACK",
    "KIO_TEST_WINDOWS_PROFILE",
];

fn kio(dir: &TempDir, args: &[&str]) -> Command {
    let mut command = Command::cargo_bin("kio").unwrap();
    for name in KIO_CHILD_ENV_DENYLIST {
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

fn init(dir: &TempDir) {
    kio(dir, &["init"]).assert().success();
}

fn scope_json(dir: &TempDir) -> Value {
    serde_json::from_str(&fs::read_to_string(dir.path().join(".kio/scope.json")).unwrap()).unwrap()
}

fn kio_dir(dir: &TempDir) -> PathBuf {
    dir.path().join(".kio")
}

/// The SCOPE-local `.kio/config.toml` — 07 §3's (b) path (mirrors
/// `step4b_p3a_contract.rs`'s helper of the same name/content exactly).
fn write_scope_allow_network_true(dir: &TempDir) {
    fs::write(
        dir.path().join(".kio/config.toml"),
        "[adapter.policy]\nallow_network = true\n",
    )
    .unwrap();
}

fn fake_pdf(pages: &[&str]) -> String {
    let kids = (0..pages.len())
        .map(|index| format!("{} 0 R", index + 2))
        .collect::<Vec<_>>()
        .join(" ");
    let mut out = format!(
        "%PDF-1.4\n1 0 obj << /Type /Pages /Kids [{kids}] /Count {} >> endobj\n",
        pages.len()
    );
    for (index, page) in pages.iter().enumerate() {
        out.push_str(&format!(
            "{} 0 obj << /Type /Page /Parent 1 0 R >> stream\nBT ({page}) Tj ET\nendstream endobj\n",
            index + 2
        ));
    }
    out.push_str("%%EOF\n");
    out
}

/// The `(tool_id, tool_profile_hash)` a fresh scope's `kio index --yes`
/// computes for the standard online markdownize adapter — the same
/// `standard_online_markdownize_profile_with_bbox(bbox_annotation_enabled)`
/// call `online_markdownize_profile_for` makes internally, with
/// `bbox_annotation` at its frozen default `true` (no `.kio/config.toml`
/// `[markdownize]` override is written by any scenario below, so the
/// default holds).
fn standard_markdownize_identity() -> (String, String) {
    let profile = standard_online_markdownize_profile_with_bbox(true);
    (profile.adapter_id, profile.tool_profile_hash)
}

fn init_with_allow_network(dir: &TempDir) -> String {
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello"])).unwrap();
    init(dir);
    write_scope_allow_network_true(dir);
    scope_json(dir)["scope_id"]
        .as_str()
        .expect("fresh scope.json must carry scope_id")
        .to_owned()
}

/// selfheal_01 (07 §3 L191-198/L195-196): a crash mid-flight between step
/// (0) (pending write) and step (2) (row publish) — boolean already `true`,
/// a well-formed pending exact-matching the scope's actual first-tool
/// identity, no rows, no marker. The NEXT `kio index --yes` must complete
/// the publish from the pending's payload VERBATIM: `approved_at`/
/// `approval_method` copied as-is (NOT re-stamped with "now"/"materialize"),
/// `status` set to `active`, the marker set true, and `approval_pending`
/// removed — all in one self-heal, not a fabricated materialize row.
#[test]
fn selfheal_01_crash_pending_completes_publish_verbatim() {
    let dir = tempfile::tempdir().unwrap();
    let scope_id = init_with_allow_network(&dir);
    let (tool_id, tool_profile_hash) = standard_markdownize_identity();

    let pending = json!({
        "scope_id": scope_id,
        "tool_id": tool_id,
        "execution_mode": "online_api",
        "tool_profile_hash": tool_profile_hash,
        // Deliberately far from "now" (today is 2026-07-22) so a re-stamping
        // regression is caught by simple inequality, not just presence.
        "approved_at": "2020-01-01T00:00:00Z",
        "approval_method": "approve",
    });
    write_network_approval_pending(&kio_dir(&dir), pending).unwrap();
    assert!(
        scope_json(&dir).get("approvals").is_none(),
        "no row must exist before the self-heal run"
    );

    let output = json_success(&dir, &["index", "--yes"]);
    assert_eq!(
        output["network_opt_in"], true,
        "self-heal must complete the publish and open the gate: {output}"
    );

    let scope = scope_json(&dir);
    let approvals = scope["approvals"]
        .as_array()
        .expect("approvals[] must exist after self-heal");
    assert_eq!(approvals.len(), 1, "exactly the healed row: {approvals:?}");
    let row = &approvals[0];
    assert_eq!(row["scope_id"], json!(scope_id));
    assert_eq!(row["tool_id"], json!(tool_id));
    assert_eq!(row["execution_mode"], json!("online_api"));
    assert_eq!(row["tool_profile_hash"], json!(tool_profile_hash));
    assert_eq!(
        row["approved_at"], "2020-01-01T00:00:00Z",
        "approved_at must be copied VERBATIM from the pending, not re-stamped: {row}"
    );
    assert_eq!(
        row["approval_method"], "approve",
        "approval_method must be copied VERBATIM from the pending, not overwritten with \
         \"materialize\": {row}"
    );
    assert_eq!(row["status"], "active");
    assert_eq!(scope["approvals_initialized"], true);
    assert!(
        scope.get("approval_pending").is_none(),
        "approval_pending must be removed in the same write: {scope}"
    );
}

/// selfheal_02 (07 §3 L196-198): a pending whose `tool_profile_hash` does
/// NOT match the scope's actual current identity (well-formed otherwise) —
/// self-heal must NOT publish, must leave the STALE pending untouched (the
/// next EXPLICIT approval's own step (0) is what overwrites it), and must
/// NOT let the fallthrough fall back to fabricating a materialize row
/// either, even though `approvals[]` is empty and no marker is set (the
/// pending's mere PRESENCE rules out materialize regardless of whether
/// self-heal itself fires for it).
#[test]
fn selfheal_02_mismatched_profile_pending_is_left_untouched_and_gate_stays_closed() {
    let dir = tempfile::tempdir().unwrap();
    let scope_id = init_with_allow_network(&dir);
    let (tool_id, _real_hash) = standard_markdownize_identity();
    let stale_hash = format!("sha256:{}", "0".repeat(64));

    let pending = json!({
        "scope_id": scope_id,
        "tool_id": tool_id,
        "execution_mode": "online_api",
        "tool_profile_hash": stale_hash,
        "approved_at": "2020-01-01T00:00:00Z",
        "approval_method": "approve",
    });
    write_network_approval_pending(&kio_dir(&dir), pending.clone()).unwrap();

    let output = json_success(&dir, &["index", "--yes"]);
    assert_eq!(
        output["network_opt_in"], false,
        "a profile-mismatched pending must not open the gate: {output}"
    );

    let scope = scope_json(&dir);
    assert!(
        scope.get("approvals").is_none(),
        "no row must be published — neither self-heal (mismatch) nor a \
         fabricated materialize (pending present): {scope}"
    );
    assert!(
        scope.get("approvals_initialized").is_none(),
        "the marker must stay unset — nothing consumed the initial-materialize \
         exception: {scope}"
    );
    assert_eq!(
        scope["approval_pending"], pending,
        "the stale pending must be left byte-for-byte untouched for a future \
         explicit approval's step (0) to overwrite: {scope}"
    );
}

/// selfheal_03 (07 §3 L199-205, 10 §12.3): a LEGACY pending (missing
/// `approval_method` — the r9-schema-and-earlier shape 10 §12.3 keeps from
/// being a schema error) is outside self-heal's exact-match condition
/// entirely. The first run must discard it via the locked-mutation cleanup
/// (removed + marker set true in the same write, since it was previously
/// absent) rather than leaving it to rot or erroring out. A second,
/// otherwise-identical run must be a clean no-op (idempotent: no error, gate
/// stays closed, no row appears) — the marker being true now is what stops
/// the SECOND run's fallthrough from taking the fresh-scope materialize
/// branch.
#[test]
fn selfheal_03_legacy_pending_is_discarded_then_idempotent_on_rerun() {
    let dir = tempfile::tempdir().unwrap();
    let scope_id = init_with_allow_network(&dir);
    let (tool_id, tool_profile_hash) = standard_markdownize_identity();

    let legacy_pending = json!({
        "scope_id": scope_id,
        "tool_id": tool_id,
        "execution_mode": "online_api",
        "tool_profile_hash": tool_profile_hash,
        "approved_at": "2020-01-01T00:00:00Z",
        // approval_method intentionally absent — the legacy shape.
    });
    write_network_approval_pending(&kio_dir(&dir), legacy_pending).unwrap();
    assert!(!scope_json(&dir)["approvals_initialized"]
        .as_bool()
        .unwrap_or(false));

    let first = json_success(&dir, &["index", "--yes"]);
    assert_eq!(
        first["network_opt_in"], false,
        "a legacy pending must never self-heal: {first}"
    );
    let after_first = scope_json(&dir);
    assert!(
        after_first.get("approvals").is_none(),
        "no row must be published from a legacy pending: {after_first}"
    );
    assert!(
        after_first.get("approval_pending").is_none(),
        "the legacy pending must be discarded: {after_first}"
    );
    assert_eq!(
        after_first["approvals_initialized"], true,
        "the discard must set the marker in the same write (07 §3 L202-205): {after_first}"
    );

    // Idempotent re-run: the pending is already gone, so the fallthrough now
    // takes the materialize branch — which must stay a no-op because the
    // marker is already true (not a fresh scope).
    let second = json_success(&dir, &["index", "--yes"]);
    assert_eq!(
        second["network_opt_in"], false,
        "the marker set by the first run's cleanup must keep materialize closed \
         on rerun: {second}"
    );
    let after_second = scope_json(&dir);
    assert!(
        after_second.get("approvals").is_none(),
        "still no row after the idempotent rerun: {after_second}"
    );
}

/// selfheal_04 (07 §3 L186-190, 197-198): a SECOND tool's crash mid-flight —
/// `approvals_initialized` is already `true` and an unrelated tool_id
/// already carries an `active` row (a previously, fully-completed
/// approval), while a well-formed pending for THIS run's tool (the standard
/// markdownize identity) sits unpublished. Self-heal must still complete
/// tool B's publish from its pending verbatim, independent of the marker
/// already being consumed by tool A, and leave tool A's row completely
/// unmodified.
#[test]
fn selfheal_04_second_tool_crash_pending_heals_without_disturbing_the_first_tools_row() {
    let dir = tempfile::tempdir().unwrap();
    let scope_id = init_with_allow_network(&dir);
    let (tool_id_b, tool_profile_hash_b) = standard_markdownize_identity();
    let tool_id_a = "kio_selfheal_test_tool_a";
    let tool_profile_hash_a = format!("sha256:{}", "1".repeat(64));

    let row_a = json!({
        "scope_id": scope_id,
        "tool_id": tool_id_a,
        "execution_mode": "online_api",
        "tool_profile_hash": tool_profile_hash_a,
        "approved_at": "2019-01-01T00:00:00Z",
        "approval_method": "approve",
        "status": "active",
    });
    publish_network_approval(&kio_dir(&dir), row_a.clone(), None).unwrap();
    assert_eq!(scope_json(&dir)["approvals_initialized"], true);

    let pending_b = json!({
        "scope_id": scope_id,
        "tool_id": tool_id_b,
        "execution_mode": "online_api",
        "tool_profile_hash": tool_profile_hash_b,
        "approved_at": "2021-02-02T00:00:00Z",
        "approval_method": "approve",
    });
    write_network_approval_pending(&kio_dir(&dir), pending_b).unwrap();

    let output = json_success(&dir, &["index", "--yes"]);
    assert_eq!(
        output["network_opt_in"], true,
        "self-heal must fire for tool B despite the marker already being \
         consumed by tool A: {output}"
    );

    let scope = scope_json(&dir);
    let approvals = scope["approvals"].as_array().unwrap();
    assert_eq!(
        approvals.len(),
        2,
        "tool A's row plus the healed tool B row: {approvals:?}"
    );
    let row_b_after = approvals
        .iter()
        .find(|row| row["tool_id"] == json!(tool_id_b))
        .expect("tool B's healed row must exist");
    assert_eq!(row_b_after["approved_at"], "2021-02-02T00:00:00Z");
    assert_eq!(row_b_after["approval_method"], "approve");
    assert_eq!(row_b_after["status"], "active");
    assert_eq!(row_b_after["tool_profile_hash"], json!(tool_profile_hash_b));

    let row_a_after = approvals
        .iter()
        .find(|row| row["tool_id"] == json!(tool_id_a))
        .expect("tool A's row must still exist");
    assert_eq!(
        row_a_after, &row_a,
        "tool A's row must be completely unmodified by tool B's self-heal: {row_a_after}"
    );
    assert!(
        scope.get("approval_pending").is_none(),
        "tool B's pending must be removed: {scope}"
    );
    assert_eq!(scope["approvals_initialized"], true);
}
