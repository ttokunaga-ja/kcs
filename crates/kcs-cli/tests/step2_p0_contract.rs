use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use assert_cmd::Command;
use kcs_adapter::catalog::{
    builtin_prepare_profile, standard_online_markdownize_profile,
    TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV,
};
use kcs_adapter::identity::{prompt_template_hash, tool_profile_hash};
use kcs_adapter::tool_lock::tool_lock_hash;
use kcs_pipeline::budget::{evaluate_budget_with_caps, BudgetCapKind, BudgetEstimate};
use kcs_pipeline::markdownize::{
    choose_markdownize_mode, markdownize_units, normalized_identity, normalized_instance_dir,
    validate_markdownize_response, IncrementalHints, IncrementalModeInput, MarkdownizeMode,
    MarkdownizeStageRequest, NormalizedInstanceManifest, NormalizedUnitManifestEntry,
    NormalizedUnitObject, RawRef, UnitStatus,
};
use kcs_pipeline::prepare::{
    change_rate, hash_bytes, map_units, unit_ref, PreparedUnit, UnitFingerprint, UnitType,
};
use kcs_pipeline::task::{
    idempotency_key, retry_policy, task_status_from_unit_counts, RetryErrorKind, TaskStatus,
    TaskType,
};
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
    "KCS_TEST_R13_2_AUTH",
    "KCS_TEST_R13_2_DECLARED",
    "KCS_TEST_R13_2_FALLBACK",
];

fn hermetic_kcs_command() -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    for name in KCS_CHILD_ENV_DENYLIST {
        command.env_remove(name);
    }
    command
}

fn profile_deterministic() -> Value {
    json!({
        "adapter_kind": "markdownize",
        "adapter_role": "text",
        "model_or_tool_family": "kcs-deterministic-text",
        "model_version_pin": "1.0.0",
        "output_schema": "kcs-markdown-v1",
        "runtime_kind": "local",
        "spec_version": 1
    })
}

fn tool_lock_fixture() -> Value {
    let prepare = builtin_prepare_profile();
    let markdown = standard_online_markdownize_profile();
    json!({
        "spec_version": 1,
        "prepare": {
            "tool_id": prepare.adapter_id,
            "profile_hash": "sha256:20b67a9d7e7e2654379f16f20b445d007e95abac7c8f85d6da65beccff7e6b03"
        },
        "markdown": {
            "tool_id": markdown.adapter_id,
            "profile_hash": "sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed",
            "capabilities": ["ignored"]
        },
        "embedding": {
            "tool_id": "fixture_embedding_adapter",
            "profile_hash": "sha256:c2bda78e217e1f9e12cd17ddac6c46e28a50b8060976f533f76f14193a807226",
            "dimensions": 1536,
            "distance": "cosine",
            "modality": "multimodal",
            "mode": "ignored"
        }
    })
}

fn is_online_output_ref(task: &Value) -> bool {
    task["output_ref"]
        .as_str()
        .map(|output_ref| output_ref.starts_with("online:"))
        .unwrap_or(false)
}

fn first_online_task(status: &Value) -> &Value {
    status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|task| is_online_output_ref(task))
        .expect("online task")
}

fn prepared_page(order: u64, key: &str, fp: &str) -> PreparedUnit {
    PreparedUnit {
        order,
        unit_key: key.to_owned(),
        unit_type: UnitType::Page,
        prepared_hash: format!("sha256:{:0<64}", fp),
        fingerprint: UnitFingerprint {
            perceptual_hash: fp.to_owned(),
            text_hash: fp.to_owned(),
            visual_hash: fp.to_owned(),
        },
        mime: Some("application/pdf".to_owned()),
        page_number: Some(order + 1),
    }
}

fn markdown_unit(key: &str, text: &str) -> kcs_adapter::types::MarkdownUnit {
    kcs_adapter::types::MarkdownUnit {
        unit_key: key.to_owned(),
        unit_type: kcs_adapter::types::UnitKind::Page,
        markdown: text.to_owned(),
        metadata: BTreeMap::new(),
    }
}

fn acceptance_context() -> (Vec<PreparedUnit>, IncrementalHints) {
    (
        vec![
            prepared_page(0, "page:1", "a"),
            prepared_page(1, "page:2", "b"),
        ],
        IncrementalHints {
            changed_unit_keys: vec!["page:1".to_owned()],
            added_unit_keys: Vec::new(),
            removed_unit_keys: Vec::new(),
            page_fingerprints: BTreeMap::new(),
        },
    )
}

fn response_incremental(
    updated: Vec<kcs_adapter::types::MarkdownUnit>,
    unchanged: Vec<&str>,
    added: Vec<kcs_adapter::types::MarkdownUnit>,
    removed: Vec<&str>,
) -> kcs_adapter::types::MarkdownizeResponse {
    kcs_adapter::types::MarkdownizeResponse {
        mode_used: kcs_adapter::types::MarkdownizeMode::Incremental,
        updated_units: updated,
        unchanged_unit_keys: unchanged.into_iter().map(str::to_owned).collect(),
        added_units: added,
        removed_unit_keys: removed.into_iter().map(str::to_owned).collect(),
        evidence_pointers: Vec::new(),
        fallback_to_full: false,
        reason: None,
    }
}

fn scope() -> TempDir {
    let dir = tempfile::tempdir().unwrap();
    kcs(&dir, ["init"]).assert().success();
    dir
}

fn kcs<const N: usize>(dir: &TempDir, args: [&str; N]) -> Command {
    let mut command = hermetic_kcs_command();
    command
        .current_dir(dir.path())
        .env("XDG_CONFIG_HOME", dir.path().join(".test-config"))
        .env("XDG_DATA_HOME", dir.path().join(".test-data"))
        .env("XDG_CACHE_HOME", dir.path().join(".test-cache"))
        .args(args);
    command
}

fn json_success<const N: usize>(dir: &TempDir, args: [&str; N]) -> Value {
    let output = kcs(dir, args)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_success_with_env<const N: usize>(
    dir: &TempDir,
    args: [&str; N],
    envs: &[(&str, &str)],
) -> Value {
    let mut command = kcs(dir, args);
    for (key, value) in envs {
        command.env(key, value);
    }
    let output = command
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_failure<const N: usize>(dir: &TempDir, args: [&str; N], code: i32) -> Value {
    let output = kcs(dir, args)
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stderr
        .clone();
    serde_json::from_slice(&output).unwrap()
}

/// R11-2/R11-3: a command that prints its full result JSON to STDOUT yet exits
/// non-zero (batch 3/4/5/6, index partial 3) — the "result + nonzero exit" shape
/// (05 §1.8 search parity), distinct from an Err envelope (stderr). Asserts the
/// exit code and returns the stdout payload (with `__exit_code` already stripped).
fn json_code_stdout_with_env<const N: usize>(
    dir: &TempDir,
    args: [&str; N],
    code: i32,
    envs: &[(&str, &str)],
) -> Value {
    let mut command = kcs(dir, args);
    for (key, value) in envs {
        command.env(key, value);
    }
    let output = command
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn inspect(dir: &TempDir, hash: &str) -> Value {
    json_success(dir, ["inspect", hash])
}

fn head(dir: &TempDir) -> String {
    fs::read_to_string(dir.path().join(".kcs/HEAD")).unwrap()
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

fn fake_pdf_stream_strings(pages: Vec<Vec<&str>>) -> String {
    let kids = (0..pages.len())
        .map(|index| format!("{} 0 R", index + 2))
        .collect::<Vec<_>>()
        .join(" ");
    let mut out = format!(
        "%PDF-1.4\n1 0 obj << /Type /Pages /Kids [{kids}] /Count {} >> endobj\n",
        pages.len()
    );
    for (index, strings) in pages.iter().enumerate() {
        let ops = strings
            .iter()
            .map(|text| format!("({text}) Tj"))
            .collect::<Vec<_>>()
            .join(" ");
        out.push_str(&format!(
            "{} 0 obj << /Type /Page /Parent 1 0 R >> stream\nBT {ops} ET\nendstream endobj\n",
            index + 2
        ));
    }
    out.push_str("%%EOF\n");
    out
}

fn normalized_units(dir: &TempDir) -> Vec<NormalizedUnitObject> {
    let root = dir.path().join(".kcs/objects/normalized_units");
    collect_files(&root)
        .into_iter()
        .filter(|path| path.extension().and_then(|ext| ext.to_str()) == Some("json"))
        .filter(|path| path.file_name().and_then(|name| name.to_str()) != Some("manifest.json"))
        .map(|path| {
            let bytes = fs::read(root.join(path)).unwrap();
            serde_json::from_slice::<NormalizedUnitObject>(&bytes).unwrap()
        })
        .collect()
}

fn ledger_lines(dir: &TempDir) -> Vec<Value> {
    let path = dir.path().join(".test-data/kcs/cost-ledger.jsonl");
    let text = fs::read_to_string(path).unwrap_or_default();
    text.lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str(line).unwrap())
        .collect()
}

#[test]
fn ct2_profile_002_tool_profile_hash_deterministic() {
    assert_eq!(
        tool_profile_hash(&profile_deterministic()).unwrap(),
        "sha256:76c01950d19edffc1b8ca75e06d7754fb52cd05db1bb10e3268f81392bf54095"
    );
}

#[test]
fn ct2_profile_004_execution_and_auth_are_not_identity() {
    let mut a = profile_deterministic();
    a["cmd"] = json!("/usr/bin/a");
    a["url"] = json!("https://a.example");
    a["auth"] = json!("plain:not-real");
    let mut b = profile_deterministic();
    b["cmd"] = json!("/usr/bin/b");
    b["url"] = json!("https://b.example");
    b["auth"] = json!("env:TOKEN");
    assert_eq!(
        tool_profile_hash(&a).unwrap(),
        tool_profile_hash(&b).unwrap()
    );
}

#[test]
fn ct2_profile_005_prompt_template_hash_vector() {
    let raw =
        "You are a markdownize adapter.  \r\nProcess the cafe\u{301} uncha\u{301}nged unit.\t\t\r\n\r\n";
    assert_eq!(
        prompt_template_hash(raw),
        "sha256:3f5200e929d23e1f113f605fb528b1b7b75e183d226064d319f57fb3e467d238"
    );
}

#[test]
fn ct2_profile_006_tool_lock_hash_vector() {
    assert_eq!(
        tool_lock_hash(&tool_lock_fixture()).unwrap(),
        "sha256:eb4cf0cebc4bacf1808e6e89dc4d7c57a4ac5e42dabad5dc0163ef41b04d6a4b"
    );
}

#[test]
fn ct2_profile_010_tool_lock_schema_validation() {
    let dir = scope();
    fs::write(
        dir.path().join(".kcs/tool-lock.json"),
        br#"{"markdown":{}}"#,
    )
    .unwrap();
    let error = json_failure(&dir, ["status"], 2);
    assert_eq!(error["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

#[test]
fn ct2_unit_001_unit_ref_vectors() {
    assert_eq!(unit_ref("page:12"), "3c2fa650872d5484");
    assert_eq!(unit_ref("page:1"), "00f081779b832543");
    assert_eq!(unit_ref("page:57"), "d2255263b6d52dc8");
    assert_eq!(unit_ref("slide:3"), "22814b0d608d29b9");
    assert_eq!(unit_ref("sheet:Sheet1"), "fae07767a7986381");
    assert_eq!(unit_ref("image:0"), "beadc43287ae0d1a");
}

#[test]
fn ct2_unit_002_normalized_instance_layout() {
    let raw = "sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59";
    let tool = "sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed";
    assert_eq!(
        normalized_instance_dir(".kcs", raw, tool, 0),
        PathBuf::from(".kcs/objects/normalized_units/bb/e1/bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59.24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed.g0")
    );
}

#[test]
fn ct2_unit_003_manifest_schema_and_status() {
    let manifest = NormalizedInstanceManifest {
        raw_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            .to_owned(),
        tool_profile_hash:
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_owned(),
        gen: 0,
        parent_gen: None,
        run_id: "run_01H00000000000000000000000".to_owned(),
        units: vec![NormalizedUnitManifestEntry {
            order: 0,
            unit_key: "page:1".to_owned(),
            unit_ref: unit_ref("page:1"),
            unit_type: UnitType::Page,
            status: UnitStatus::Failed,
            prepared_hash:
                "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc".to_owned(),
            error_kind: Some("invalid_input".to_owned()),
        }],
        generated_at: "2026-04-25T12:00:00Z".to_owned(),
    };
    let value = serde_json::to_value(manifest).unwrap();
    assert_eq!(value["units"][0]["status"], "failed");
    assert!(value["run_id"].as_str().unwrap().starts_with("run_"));
}

#[test]
fn ct2_unit_004_fingerprint_match_reuses_unit() {
    let old = vec![prepared_page(0, "page:1", "same")];
    let new = vec![prepared_page(0, "page:9", "same")];
    let mapping = map_units(&old, &new);
    assert_eq!(mapping.unchanged[0].old_unit_key, "page:1");
    assert_eq!(mapping.unchanged[0].new_unit_key, "page:9");
    assert!(mapping.changed_unit_keys.is_empty());
}

#[test]
fn ct2_unit_005_change_rate_vectors() {
    assert!((change_rate(0, 1, 0, 11) - 1.0 / 11.0).abs() < f64::EPSILON);
    assert_eq!(change_rate(4, 0, 0, 10), 0.4);
    assert_eq!(change_rate(0, 0, 2, 8), 0.25);
    assert_eq!(change_rate(0, 0, 3, 0), 3.0);
}

#[test]
fn ct2_unit_013_full_markdownize_initial_output() {
    let output = markdownize_units(MarkdownizeStageRequest {
        mode: MarkdownizeMode::Full,
        new_raw: RawRef {
            path: "note.txt".to_owned(),
            raw_hash: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                .to_owned(),
        },
        previous: None,
        hints: None,
        tool_profile_hash:
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_owned(),
        spec_version: 1,
    })
    .unwrap();
    assert_eq!(output.manifest.gen, 0);
    assert_eq!(output.manifest.units[0].status, UnitStatus::Done);
    assert_eq!(output.updated_units[0].mode, MarkdownizeMode::Full);
}

#[test]
fn ct2_incr_001_all_conditions_use_incremental() {
    let decision = choose_markdownize_mode(&IncrementalModeInput {
        has_previous_done_run: true,
        raw_hash_only_changed: true,
        adapter_capabilities: vec!["incremental_update".to_owned()],
        change_rate: 0.09,
        threshold: 0.30,
        consecutive_incremental_count: 4,
        max_consecutive_incremental: 5,
    });
    assert_eq!(decision.mode, MarkdownizeMode::Incremental);
}

#[test]
fn ct2_incr_002_no_previous_run_falls_back_full() {
    let input = IncrementalModeInput {
        has_previous_done_run: false,
        raw_hash_only_changed: true,
        adapter_capabilities: vec!["incremental_update".to_owned()],
        change_rate: 0.09,
        threshold: 0.30,
        consecutive_incremental_count: 0,
        max_consecutive_incremental: 5,
    };
    assert_eq!(choose_markdownize_mode(&input).mode, MarkdownizeMode::Full);
}

#[test]
fn ct2_incr_003_tool_profile_change_falls_back_full() {
    let input = IncrementalModeInput {
        has_previous_done_run: true,
        raw_hash_only_changed: false,
        adapter_capabilities: vec!["incremental_update".to_owned()],
        change_rate: 0.09,
        threshold: 0.30,
        consecutive_incremental_count: 0,
        max_consecutive_incremental: 5,
    };
    assert_eq!(choose_markdownize_mode(&input).mode, MarkdownizeMode::Full);
}

#[test]
fn ct2_incr_004_missing_capability_falls_back_full() {
    let input = IncrementalModeInput {
        has_previous_done_run: true,
        raw_hash_only_changed: true,
        adapter_capabilities: Vec::new(),
        change_rate: 0.09,
        threshold: 0.30,
        consecutive_incremental_count: 0,
        max_consecutive_incremental: 5,
    };
    assert_eq!(choose_markdownize_mode(&input).mode, MarkdownizeMode::Full);
}

#[test]
fn ct2_incr_005_change_rate_threshold_falls_back_full() {
    let input = IncrementalModeInput {
        has_previous_done_run: true,
        raw_hash_only_changed: true,
        adapter_capabilities: vec!["incremental_update".to_owned()],
        change_rate: 0.40,
        threshold: 0.30,
        consecutive_incremental_count: 0,
        max_consecutive_incremental: 5,
    };
    assert_eq!(choose_markdownize_mode(&input).mode, MarkdownizeMode::Full);
}

#[test]
fn ct2_incr_006_max_consecutive_falls_back_full() {
    let input = IncrementalModeInput {
        has_previous_done_run: true,
        raw_hash_only_changed: true,
        adapter_capabilities: vec!["incremental_update".to_owned()],
        change_rate: 0.09,
        threshold: 0.30,
        consecutive_incremental_count: 5,
        max_consecutive_incremental: 5,
    };
    assert_eq!(choose_markdownize_mode(&input).mode, MarkdownizeMode::Full);
}

// §A identity-vector check (Step2c I5): asserts the *pure* identity contract —
// `normalized_identity` is a function of `(raw_hash, tool_profile_hash)` only and
// ignores `mode` and `markdown`. The end-to-end behaviour that a light change
// actually reuses units through the CLI is verified separately by
// `ct2_incr_009_cli_mock_adapter_uses_incremental_for_light_change`.
#[test]
fn ct2_incr_008_identity_vector_ignores_mode() {
    let raw = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    let tool = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    let full = NormalizedUnitObject {
        unit_key: "page:1".to_owned(),
        unit_type: UnitType::Page,
        raw_hash: raw.to_owned(),
        prepared_hash: "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
            .to_owned(),
        tool_profile_hash: tool.to_owned(),
        gen: 0,
        mode: MarkdownizeMode::Full,
        markdown: "full".to_owned(),
        reused_from: None,
        generated_at: "2026-04-25T12:00:00Z".to_owned(),
    };
    let mut incremental = full.clone();
    incremental.mode = MarkdownizeMode::Incremental;
    incremental.markdown = "incremental".to_owned();
    assert_eq!(
        normalized_identity(&full.raw_hash, &full.tool_profile_hash),
        normalized_identity(&incremental.raw_hash, &incremental.tool_profile_hash)
    );
    assert_ne!(full.markdown, incremental.markdown);
}

#[test]
fn ct2_accept_001_rejects_coverage_or_overlap_violation() {
    let (prepared, hints) = acceptance_context();
    let response = response_incremental(
        vec![markdown_unit("page:1", "x")],
        Vec::new(),
        Vec::new(),
        Vec::new(),
    );
    assert!(validate_markdownize_response(&response, &hints, &prepared).is_err());
}

#[test]
fn ct2_accept_002_rejects_removed_mismatch() {
    let (prepared, hints) = acceptance_context();
    let response = response_incremental(
        vec![markdown_unit("page:1", "x")],
        vec!["page:2"],
        Vec::new(),
        vec!["page:9"],
    );
    assert!(validate_markdownize_response(&response, &hints, &prepared).is_err());
}

#[test]
fn ct2_accept_003_rejects_update_outside_changed_set() {
    let (prepared, hints) = acceptance_context();
    let response = response_incremental(
        vec![markdown_unit("page:2", "x")],
        vec!["page:1"],
        Vec::new(),
        Vec::new(),
    );
    assert!(validate_markdownize_response(&response, &hints, &prepared).is_err());
}

#[test]
fn ct2_accept_004_rejects_added_mismatch() {
    let (prepared, mut hints) = acceptance_context();
    hints.added_unit_keys = vec!["page:2".to_owned()];
    let response = response_incremental(
        vec![markdown_unit("page:1", "x")],
        Vec::new(),
        Vec::new(),
        Vec::new(),
    );
    assert!(validate_markdownize_response(&response, &hints, &prepared).is_err());
}

#[test]
fn ct2_accept_005_rejects_empty_markdown() {
    let (prepared, hints) = acceptance_context();
    let response = response_incremental(
        vec![markdown_unit("page:1", "")],
        vec!["page:2"],
        Vec::new(),
        Vec::new(),
    );
    assert!(validate_markdownize_response(&response, &hints, &prepared).is_err());
}

#[test]
fn ct2_accept_006_full_mode_uses_full_contract() {
    let (prepared, hints) = acceptance_context();
    let response = kcs_adapter::types::MarkdownizeResponse {
        mode_used: kcs_adapter::types::MarkdownizeMode::Full,
        updated_units: vec![markdown_unit("page:1", "a"), markdown_unit("page:2", "b")],
        unchanged_unit_keys: Vec::new(),
        added_units: Vec::new(),
        removed_unit_keys: Vec::new(),
        evidence_pointers: Vec::new(),
        fallback_to_full: false,
        reason: None,
    };
    validate_markdownize_response(&response, &hints, &prepared).unwrap();
}

#[test]
fn ct2_accept_007_reject_triggers_full_fallback_path() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2", "p3", "p4", "p5"]),
    )
    .unwrap();
    kcs(&dir, ["index", "--approve"])
        .env("KCS_TEST_MARKDOWNIZE_ADAPTER", "reject_incremental")
        .assert()
        .success();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2 changed", "p3", "p4", "p5"]),
    )
    .unwrap();
    kcs(&dir, ["index", "--yes"])
        .env("KCS_TEST_MARKDOWNIZE_ADAPTER", "reject_incremental")
        .assert()
        .success();
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "report.pdf"
            && task["status"] == "done"
            && task["mode"] == "full"
            && task["fallback_reason"] == "full_fallback_after_incremental_reject"
    }));
    assert!(!normalized_units(&dir)
        .iter()
        .any(|unit| unit.markdown.starts_with("incremental ")));
}

#[test]
fn ct2_accept_008_full_fallback_failure_is_per_candidate_partial_exit() {
    let dir = scope();
    fs::write(
        dir.path().join("a_report.pdf"),
        fake_pdf(&["p1", "p2", "p3", "p4"]),
    )
    .unwrap();
    fs::write(dir.path().join("z.txt"), "stable").unwrap();
    json_success_with_env(
        &dir,
        ["index", "--approve"],
        &[("KCS_TEST_MARKDOWNIZE_ADAPTER", "incremental")],
    );

    fs::write(
        dir.path().join("a_report.pdf"),
        fake_pdf(&["p1 changed", "p2", "p3", "p4"]),
    )
    .unwrap();
    // R11-3: a partial index now prints its full result JSON to stdout with a
    // top-level `error_code` + `__exit_code:3` (search parity), not an Err envelope
    // that buried `failed_files`/`commit_hash` inside a private `context.output`.
    let output = json_code_stdout_with_env(
        &dir,
        ["index", "--yes"],
        3,
        &[(
            "KCS_TEST_MARKDOWNIZE_ADAPTER",
            "reject_incremental_and_full",
        )],
    );
    assert_eq!(output["error_code"], "KCS-E-INDEX-PARTIAL-001");
    assert_eq!(output["failed_files"], 1);
    assert!(output["normalized_files"].as_u64().unwrap() > 0);
    // The index result (commit_hash/tree_hash) is now visible on stdout, not hidden.
    assert!(
        output["commit_hash"].is_string(),
        "commit_hash must survive on stdout for a partial index: {output}"
    );
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "a_report.pdf"
            && task["status"] == "failed"
            && task["fallback_reason"] == "full_fallback_failed"
    }));
}

#[test]
fn ct2_task_001_state_transitions() {
    assert_eq!(task_status_from_unit_counts(2, 0, false), TaskStatus::Done);
    assert_eq!(
        task_status_from_unit_counts(1, 1, false),
        TaskStatus::Partial
    );
    assert_eq!(
        task_status_from_unit_counts(0, 2, false),
        TaskStatus::Failed
    );
}

#[test]
fn ct2_task_002_retry_budget_matrix() {
    assert_eq!(
        retry_policy(RetryErrorKind::NetworkError).max_attempts,
        Some(5)
    );
    assert_eq!(retry_policy(RetryErrorKind::RateLimit).max_attempts, None);
    assert_eq!(
        retry_policy(RetryErrorKind::AuthError).max_attempts,
        Some(0)
    );
    assert_eq!(
        retry_policy(RetryErrorKind::QuotaExceeded).max_attempts,
        Some(3)
    );
    assert!(!retry_policy(RetryErrorKind::InvalidInput).retryable);
    assert_eq!(
        retry_policy(RetryErrorKind::ContractViolation).error_code,
        "KCS-E-ADAPTER-CONTRACT-001"
    );
    assert!(retry_policy(RetryErrorKind::BudgetExceeded).paused);
}

#[test]
fn ct2_task_003_idempotency_key_is_stable() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    json_success(&dir, ["index", "--approve"]);
    let before = collect_files(&dir.path().join(".kcs/objects/normalized_units"));
    json_success(&dir, ["index", "--yes"]);
    let after = collect_files(&dir.path().join(".kcs/objects/normalized_units"));
    assert_eq!(before, after);
    assert_eq!(
        idempotency_key("sha256:a", "sha256:b"),
        idempotency_key("sha256:a", "sha256:b")
    );
}

#[test]
fn ct2_task_004_partial_keeps_done_units_retry_failed_only() {
    assert_eq!(
        task_status_from_unit_counts(1, 1, false),
        TaskStatus::Partial
    );
    assert!(!retry_policy(RetryErrorKind::InvalidInput).retryable);
}

#[test]
fn ct2_budget_001_two_layer_cap_uses_min_remaining() {
    let estimate = BudgetEstimate {
        scope_id: "scope".to_owned(),
        task_type: TaskType::Markdownize,
        estimated_usd: 12.0,
        adapter_id: Some("mistral".to_owned()),
    };
    let decision = evaluate_budget_with_caps(&estimate, 50.0, Some(10.0), false);
    assert_eq!(decision.remaining_usd, 10.0);
    assert_eq!(decision.cap_kind, Some(BudgetCapKind::Folder));
}

#[test]
fn ct2_budget_002_cap_reached_pauses_new_tasks() {
    let estimate = BudgetEstimate {
        scope_id: "scope".to_owned(),
        task_type: TaskType::Markdownize,
        estimated_usd: 12.0,
        adapter_id: None,
    };
    let decision = evaluate_budget_with_caps(&estimate, 8.0, None, false);
    assert!(!decision.allowed);
    assert_eq!(decision.cap_kind, Some(BudgetCapKind::Device));
}

#[test]
fn ct2_budget_003_override_budget_ignores_caps() {
    let estimate = BudgetEstimate {
        scope_id: "scope".to_owned(),
        task_type: TaskType::Markdownize,
        estimated_usd: 1000.0,
        adapter_id: None,
    };
    assert!(evaluate_budget_with_caps(&estimate, 0.0, Some(0.0), true).allowed);
}

#[test]
fn ct2_budget_004_cli_cap_zero_pauses_online_task() {
    let dir = scope();
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[budget]\nmonthly_usd_cap = 0\n",
    )
    .unwrap();
    // R9-2: online tasks are only enqueued for non-text-native files, so the
    // online-lifecycle fixture is a PDF (the test's intent is budget/pause, not
    // media routing).
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello budget"])).unwrap();
    let output = json_success(&dir, ["index", "--approve"]);
    assert!(output["paused_tasks"].as_u64().unwrap() > 0);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "a.pdf"
            && task["status"] == "paused"
            && task["fallback_reason"] == "budget_exceeded"
    }));
}

#[test]
fn ct2_approve_001_noninteractive_index_without_approval_exits_2() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let error = json_failure(&dir, ["index"], 2);
    assert_eq!(error["error_code"], "KCS-E-CONFIG-USAGE-001");
}

// R11-1: derive-path (`#[derive(Args)]`) commands routed clap's usage error
// straight to `process::exit(2)` with plaintext, bypassing the `--json` contract.
// `diff` requires two positionals; `kcs diff --json` must now emit the standard
// KCS-E-CONFIG-USAGE-001 envelope on stderr with clap's exit code (2).
#[test]
fn r11_1_derive_usage_error_honors_json_envelope() {
    let dir = tempfile::tempdir().unwrap();
    let error = json_failure(&dir, ["diff"], 2);
    assert_eq!(error["error_code"], "KCS-E-CONFIG-USAGE-001");
    assert!(error["message"].as_str().is_some_and(|m| !m.is_empty()));
    assert_eq!(error["context"], serde_json::json!({}));
}

// An unknown subcommand and an unexpected derive-command flag are both usage
// errors that must honor the machine contract under `--json`.
#[test]
fn r11_1_unknown_subcommand_and_flag_return_json_envelope() {
    let dir = tempfile::tempdir().unwrap();
    let bogus = json_failure(&dir, ["bogus"], 2);
    assert_eq!(bogus["error_code"], "KCS-E-CONFIG-USAGE-001");
    let flag = json_failure(&dir, ["index", "--nope"], 2);
    assert_eq!(flag["error_code"], "KCS-E-CONFIG-USAGE-001");
}

// Without `--json`, clap's native plaintext error + exit 2 must be preserved
// verbatim (the envelope is a machine-mode-only affordance).
#[test]
fn r11_1_usage_error_without_json_stays_plaintext() {
    let dir = tempfile::tempdir().unwrap();
    let stderr = kcs(&dir, ["diff"])
        .assert()
        .code(2)
        .get_output()
        .stderr
        .clone();
    assert!(
        String::from_utf8_lossy(&stderr).contains("error:"),
        "expected clap plaintext error"
    );
    assert!(
        serde_json::from_slice::<Value>(&stderr).is_err(),
        "plaintext error must not be JSON"
    );
}

// `--help` / `--version` are clap "errors" that must still render to stdout and
// exit 0 — the try_parse wrapper must not regress them into the error path.
#[test]
fn r11_1_help_and_version_still_exit_zero() {
    let dir = tempfile::tempdir().unwrap();
    kcs(&dir, ["--help"]).assert().success();
    kcs(&dir, ["--version"]).assert().success();
}

#[test]
fn ct2_approve_002_preview_writes_nothing() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let before = head(&dir);
    let preview = json_success(&dir, ["index", "--preview"]);
    assert_eq!(preview["status"], "preview");
    assert_eq!(head(&dir), before);
    assert!(!dir.path().join(".kcs/approvals.jsonl").exists());
}

#[test]
fn ct2_approve_003_preview_required_fields() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let preview = json_success(&dir, ["index", "--preview"]);
    for key in [
        "root",
        "scope",
        "estimated_file_count",
        "estimated_size_bytes",
        "large_files",
        "effective_ignore",
        "excluded_candidates",
        "sensitive_candidates",
        "network_transmission_policy",
        "adapter_execution_mode",
        "estimated_cost",
        "budget_cap",
        "estimated_completion",
    ] {
        assert!(preview.get(key).is_some(), "missing {key}");
    }
}

#[test]
fn ct2_approve_004_approve_records_and_starts_index() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let output = json_success(&dir, ["index", "--approve"]);
    assert_eq!(output["approval_method"], "approve");
    assert!(dir.path().join(".kcs/approvals.jsonl").is_file());
    assert!(output["commit_hash"].as_str().is_some());
}

#[test]
fn ct2_secrets_001_tier_a_default_excluded_in_preview() {
    let dir = scope();
    fs::write(dir.path().join(".env"), "TOKEN=x").unwrap();
    let preview = json_success(&dir, ["index", "--preview"]);
    assert!(preview["excluded_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|v| v == ".env"));
}

#[test]
fn ct2_secrets_002_yes_cannot_unexclude_tier_a() {
    let dir = scope();
    fs::write(dir.path().join(".env"), "TOKEN=x").unwrap();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    let tree = inspect(&dir, output["commit"]["tree"].as_str().unwrap());
    let entries = tree["entries"].as_array().unwrap();
    assert!(!entries.iter().any(|entry| entry["path"] == ".env"));
}

#[test]
fn ct2_secrets_003_tier_b_local_but_online_held() {
    // N1: a Tier B (candidate-secret) file is ingested locally but its online task
    // is HELD (not a ready-to-send pending task) until `--send-secrets`. This test
    // previously asserted the pre-fix behavior (a `pending`/`network_opt_in_required`
    // task that a network opt-in would ship) — the very leak N1 closes.
    let dir = scope();
    // R9-2: online tasks are only enqueued for non-text-native files. Use a PDF
    // whose name still classifies as Tier B (`token`) so the online hold is
    // exercised (the test's intent is the secrets hold, not media routing).
    fs::write(
        dir.path().join("api_token.pdf"),
        fake_pdf(&["not actually secret"]),
    )
    .unwrap();
    let preview = json_success(&dir, ["index", "--preview"]);
    // Still ingested (not hard-excluded like Tier A), but flagged sensitive.
    assert!(!preview["excluded_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|v| v == "api_token.pdf"));
    assert!(preview["sensitive_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|c| c["path"] == "api_token.pdf" && c["reason"] == "secrets_tier_b_warning"));
    json_success(&dir, ["index", "--yes"]);
    let status = json_success(&dir, ["status"]);
    // The online task is held, not sendable.
    assert!(
        status["tasks"].as_array().unwrap().iter().any(|task| {
            task["input_path"] == "api_token.pdf"
                && task["status"] == "paused"
                && task["fallback_reason"] == "secrets_tier_b_hold"
        }),
        "Tier B online task must be held (secrets_tier_b_hold): {status}"
    );
    assert!(
        !status["tasks"].as_array().unwrap().iter().any(|task| {
            task["input_path"] == "api_token.pdf"
                && task["status"] == "pending"
                && task["fallback_reason"] == "network_opt_in_required"
        }),
        "Tier B online task must NOT be a ready-to-send pending task: {status}"
    );
    // Quarantine-visible for the operator.
    assert!(
        status["quarantine"]
            .as_array()
            .unwrap()
            .iter()
            .any(|q| q["path"] == "api_token.pdf" && q["reason"] == "secrets_tier_b"),
        "Tier B must be recorded in quarantine: {status}"
    );
}

#[test]
fn ct2_secrets_004_added_tier_a_is_quarantined() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    json_success(&dir, ["index", "--approve"]);
    fs::write(dir.path().join(".env"), "TOKEN=x").unwrap();
    fs::write(dir.path().join("b.txt"), "force commit").unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    let commit = output["commit"]
        .as_object()
        .expect("non-secret addition creates commit");
    let tree = inspect(&dir, commit["tree"].as_str().unwrap());
    assert!(!tree["entries"]
        .as_array()
        .unwrap()
        .iter()
        .any(|entry| entry["path"] == ".env"));
    let env_hash = hash_bytes(b"TOKEN=x");
    json_failure(&dir, ["inspect", &env_hash], 4);
    let status = json_success(&dir, ["status"]);
    assert!(status["quarantine"]
        .as_array()
        .unwrap()
        .iter()
        .any(|entry| entry["path"] == ".env"));
}

#[test]
fn ct2_ignore_001_double_star_ext_pattern_excludes_nested_file() {
    let dir = scope();
    fs::create_dir(dir.path().join("logs")).unwrap();
    fs::write(dir.path().join("logs/app.log"), "ignore me").unwrap();
    fs::write(dir.path().join("logs/app.txt"), "keep me").unwrap();
    fs::write(dir.path().join("debug.log"), "ignore direct").unwrap();
    fs::write(dir.path().join("keep.txt"), "keep direct").unwrap();
    fs::write(dir.path().join(".kcsignore"), "**/*.log\n").unwrap();
    let preview = json_success(&dir, ["index", "--preview"]);
    assert!(preview["excluded_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|path| path == "debug.log"));
    assert!(preview["candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|candidate| candidate["input_path"] == "keep.txt"
            && !candidate["ignored"].as_bool().unwrap()));
    assert!(!preview["candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|candidate| candidate["input_path"]
            .as_str()
            .is_some_and(|path| path.starts_with("logs/"))));
    assert!(!preview["excluded_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|path| path == "logs/app.log"));
}

#[test]
fn ct2_ignore_002_scope_ignore_config_is_accepted_and_applied() {
    // Step2c I4: `[scope] ignore` must pass config-schema validation (it was
    // previously rejected by `scope.additionalProperties:false`) and take
    // effect during scan. `kcs index` validates config.toml against the schema
    // on every invocation via `Repository::open`, so a schema violation would
    // fail the `json_success` (exit 0) assertions below.
    let dir = scope();
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[scope]\nignore = [\"*.tmp\"]\n",
    )
    .unwrap();
    fs::write(dir.path().join("keep.txt"), "keep me").unwrap();
    fs::write(dir.path().join("scratch.tmp"), "ignore me").unwrap();

    let preview = json_success(&dir, ["index", "--preview"]);
    assert!(preview["excluded_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|path| path == "scratch.tmp"));
    assert!(preview["candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|candidate| candidate["input_path"] == "keep.txt"
            && !candidate["ignored"].as_bool().unwrap()));
    assert!(preview["candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|candidate| candidate["input_path"] == "scratch.tmp"
            && candidate["ignored"].as_bool().unwrap()));

    // A full index also validates the schema and must succeed.
    json_success(&dir, ["index", "--approve"]);
}

#[test]
fn ct2_scope_001_subfolder_files_do_not_reach_parent_artifacts() {
    let dir = scope();
    fs::create_dir(dir.path().join("child")).unwrap();
    fs::write(dir.path().join("a.txt"), "parent public").unwrap();
    fs::write(dir.path().join("child/secret.txt"), "child private").unwrap();
    let child_hash = hash_bytes(b"child private");

    json_success(&dir, ["index", "--approve"]);

    let status = json_success(&dir, ["status"]);
    assert!(!status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"]
            .as_str()
            .is_some_and(|path| path == "child/secret.txt" || path.starts_with("child/"))
    }));

    let object_root = dir.path().join(".kcs/objects");
    let object_text = collect_files(&object_root)
        .into_iter()
        .filter_map(|path| fs::read(object_root.join(path)).ok())
        .map(|bytes| String::from_utf8_lossy(&bytes).into_owned())
        .collect::<Vec<_>>()
        .join("\n");
    assert!(!object_text.contains(&child_hash));
    assert!(!object_text.contains("child private"));

    let ledger = ledger_lines(&dir);
    assert_eq!(ledger.len(), 1);
    assert!(!serde_json::to_string(&ledger)
        .unwrap()
        .contains(&child_hash));
}

#[test]
fn ct2_network_001_yes_does_not_issue_online_tasks() {
    let dir = scope();
    // R9-2: only non-text-native files enqueue online tasks; PDF fixture keeps the
    // network-opt-in lifecycle intent.
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello"])).unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    assert_eq!(output["network_opt_in"], false);
    assert!(output["pending_online_tasks"].as_u64().unwrap() > 0);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "a.pdf"
            && task["status"] == "pending"
            && task["fallback_reason"] == "network_opt_in_required"
    }));
}

#[test]
fn ct2_network_002_approve_grants_opt_in_yes_does_not() {
    // R9-2: PDF fixtures so the online opt-in / ready_for_online_adapter task path
    // is exercised (text-native files no longer enqueue online tasks).
    let yes_dir = scope();
    fs::write(yes_dir.path().join("a.pdf"), fake_pdf(&["hello"])).unwrap();
    assert_eq!(
        json_success(&yes_dir, ["index", "--yes"])["network_opt_in"],
        false
    );

    let approve_dir = scope();
    fs::write(approve_dir.path().join("a.pdf"), fake_pdf(&["hello"])).unwrap();
    assert_eq!(
        json_success(&approve_dir, ["index", "--approve"])["network_opt_in"],
        true
    );

    let online_dir = scope();
    fs::write(online_dir.path().join("a.pdf"), fake_pdf(&["hello"])).unwrap();
    let error = json_failure(&online_dir, ["index", "--online"], 2);
    assert_eq!(error["error_code"], "KCS-E-CONFIG-USAGE-001");
    assert_eq!(
        json_success(&online_dir, ["index", "--yes", "--online"])["network_opt_in"],
        false
    );
    // R10-7: `--yes --online` grants NO persistent opt-in, and online markdownize can
    // only be driven by `batch` (which gates on the persistent opt-in). So the task
    // is NOT actually sendable — it must report `network_opt_in_required`, not a false
    // `ready_for_online_adapter` that no `batch resume` could ever fulfill.
    assert!(json_success(&online_dir, ["status"])["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .any(|task| task["input_path"] == "a.pdf"
            && task["fallback_reason"] == "network_opt_in_required"));
    assert!(!json_success(&online_dir, ["status"])["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .any(|task| task["fallback_reason"] == "ready_for_online_adapter"));
    let approvals = fs::read_to_string(online_dir.path().join(".kcs/approvals.jsonl")).unwrap();
    assert!(approvals.contains(r#""network_opt_in":false"#));
}

#[test]
fn ct2_network_004_portable_scope_config_cannot_grant_network_consent() {
    let dir = scope();
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[adapter.policy]\nallow_network = true\n",
    )
    .unwrap();
    // R9-2: PDF fixture keeps the online-adapter enqueue path (text-native files
    // no longer enqueue online tasks).
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello"])).unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    assert_eq!(output["network_allowed"], false);
    assert_eq!(output["network_opt_in"], false);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "a.pdf"
            && task["status"] == "pending"
            && task["fallback_reason"] == "network_opt_in_required"
    }));
}

#[test]
fn ct2_network_003_revoke_blocks_online_one_shot() {
    let dir = scope();
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success(&dir, ["index", "--revoke-network"]);
    // R9-2: the post-revoke online-task subject is a PDF (non-text-native).
    fs::write(dir.path().join("b.pdf"), fake_pdf(&["new after revoke"])).unwrap();
    let output = json_success(&dir, ["index", "--yes", "--online"]);
    assert_eq!(output["network_opt_in"], false);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "b.pdf"
            && task["status"] == "pending"
            && task["fallback_reason"] == "network_opt_in_required"
    }));
}

#[test]
fn ct2_adapter_001_baseline_index_without_key() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let output = json_success(&dir, ["index", "--approve"]);
    assert_eq!(output["status"], "indexed");
    assert!(dir.path().join(".kcs/objects/normalized_units").is_dir());
}

#[test]
fn ct2_adapter_002_no_embedding_without_online_opt_in() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    json_success(&dir, ["index", "--yes"]);
    assert!(!dir.path().join(".kcs/objects/embeddings").exists());
}

#[test]
fn ct2_pdf_001_two_page_pdf_produces_page_specific_markdown() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["First page text", "Second page text"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    let units = normalized_units(&dir);
    let page1 = units.iter().find(|unit| unit.unit_key == "page:1").unwrap();
    let page2 = units.iter().find(|unit| unit.unit_key == "page:2").unwrap();
    assert!(page1.markdown.contains("First page text"));
    assert!(page2.markdown.contains("Second page text"));
    assert_ne!(page1.markdown, page2.markdown);
}

#[test]
fn ct2_pdf_002_uneven_three_page_pdf_preserves_stream_boundaries() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf_stream_strings(vec![
            vec!["p1a", "p1b"],
            vec!["p2"],
            vec!["p3a", "p3b", "p3c"],
        ]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    let units = normalized_units(&dir);
    let page1 = units.iter().find(|unit| unit.unit_key == "page:1").unwrap();
    let page2 = units.iter().find(|unit| unit.unit_key == "page:2").unwrap();
    let page3 = units.iter().find(|unit| unit.unit_key == "page:3").unwrap();
    assert!(page1.markdown.contains("p1a"));
    assert!(page1.markdown.contains("p1b"));
    assert!(!page1.markdown.contains("p2"));
    assert_eq!(page2.markdown.trim(), "p2");
    assert!(!page2.markdown.contains("p1b"));
    assert!(!page2.markdown.contains("p3a"));
    assert!(page3.markdown.contains("p3a"));
    assert!(page3.markdown.contains("p3c"));
    assert!(!page3.markdown.contains("p2"));
}

#[test]
fn ct2_pdf_003_endstream_keyword_in_page_text_is_not_a_stream_boundary() {
    // Step2c I3: a page whose text literally contains the word "endstream"
    // must not truncate to empty markdown. The real boundary is the line-start
    // `endstream` token, not the mid-line occurrence in the page's prose.
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&[
            "this text mentions stream and endstream keywords",
            "second page body",
            "third page body",
        ]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    let units = normalized_units(&dir);
    let page1 = units.iter().find(|unit| unit.unit_key == "page:1").unwrap();
    let page2 = units.iter().find(|unit| unit.unit_key == "page:2").unwrap();
    let page3 = units.iter().find(|unit| unit.unit_key == "page:3").unwrap();
    assert!(page1
        .markdown
        .contains("this text mentions stream and endstream keywords"));
    assert!(page2.markdown.contains("second page body"));
    assert!(page3.markdown.contains("third page body"));
    // No page collapses to empty, and the boundary did not bleed across pages.
    assert!(!page1.markdown.trim().is_empty());
    assert!(!page2.markdown.trim().is_empty());
    assert!(!page3.markdown.trim().is_empty());
    assert!(!page2.markdown.contains("second page body\nthird"));
}

#[test]
fn ct2_incr_009_cli_mock_adapter_uses_incremental_for_light_change() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2", "p3", "p4", "p5"]),
    )
    .unwrap();
    kcs(&dir, ["index", "--approve"])
        .env("KCS_TEST_MARKDOWNIZE_ADAPTER", "incremental")
        .assert()
        .success();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2 changed", "p3", "p4", "p5"]),
    )
    .unwrap();
    kcs(&dir, ["index", "--yes"])
        .env("KCS_TEST_MARKDOWNIZE_ADAPTER", "incremental")
        .assert()
        .success();
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "report.pdf"
            && task["status"] == "done"
            && task["mode"] == "incremental"
            && task["changed_unit_keys"]
                .as_array()
                .unwrap()
                .contains(&json!("page:2"))
    }));
    assert!(normalized_units(&dir)
        .iter()
        .any(|unit| unit.mode == MarkdownizeMode::Incremental && unit.reused_from.is_some()));
}

#[test]
fn ct2_adapter_013_baseline_and_ai_artifacts_coexist() {
    let dir = scope();
    // R9-2: only non-text-native files enqueue an online task, so the coexistence
    // fixture (baseline + online-AI artifacts) is a PDF.
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    let baseline_root = dir.path().join(".kcs/objects/normalized_units");
    let before = collect_files(&baseline_root);
    kcs(&dir, ["batch", "resume"])
        .env(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")
        .assert()
        .success();
    assert_eq!(
        collect_files(&baseline_root).intersection(&before).count(),
        before.len()
    );
    assert!(dir.path().join(".kcs/objects/images").is_dir());
    assert!(collect_files(&baseline_root).len() > before.len());
}

#[test]
fn ct2_budget_005_online_success_records_ledger_and_caps_next_task() {
    let dir = scope();
    // R9-2: online-cost lifecycle uses PDF fixtures (text-native files are baseline
    // only, no online task).
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello online cost"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    let online_entry = ledger_lines(&dir).into_iter().find(|entry| {
        entry["adapter_kind"] == "markdown" && entry["usd"].as_f64().unwrap_or_default() > 0.0
    });
    assert!(online_entry.is_some());

    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[budget]\nmonthly_usd_cap = 50\n[budget.per_adapter]\nmarkdown = 0.0\n",
    )
    .unwrap();
    fs::write(dir.path().join("b.pdf"), fake_pdf(&["second online cost"])).unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    assert!(output["paused_tasks"].as_u64().unwrap() > 0);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "b.pdf"
            && task["status"] == "paused"
            && task["fallback_reason"] == "budget_exceeded"
    }));
    assert!(status["budget"]["cap_kind"].as_str().is_some());
    assert_eq!(status["budget"]["folder_per_adapter"]["markdown"], 0.0);
}

// R11-2: the batch-side Then of CT2-BUDGET-005 (tasks/step2a-contract-tests.md) —
// finally verified. A `batch resume` that drives a Pending online task straight into
// a budget pause THIS pass must exit 6 (docs/04 §5.6), print its full result JSON to
// stdout (tasks_paused > 0), and leave the task Paused/budget_exceeded. Before R11-2
// resume returned exit 0 with tasks_updated:0 while the store silently flipped.
#[test]
fn r11_2_batch_resume_budget_pause_exits_6() {
    let dir = scope();
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["budget pause body"])).unwrap();
    // `--approve` records a persistent opt-in, so the online task is Pending-ready.
    json_success(&dir, ["index", "--approve"]);
    // Zero the markdown cap so the pending online send is over budget on resume.
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[budget]\nmonthly_usd_cap = 50\n[budget.per_adapter]\nmarkdown = 0.0\n",
    )
    .unwrap();
    let resumed = json_code_stdout_with_env(
        &dir,
        ["batch", "resume"],
        6,
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    assert!(
        resumed["tasks_paused"].as_u64().unwrap() > 0,
        "resume must disclose the budget pause it caused: {resumed}"
    );
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "a.pdf"
            && task["status"] == "paused"
            && task["fallback_reason"] == "budget_exceeded"
    }));
}

// F1 (04 §5.4): offline/deterministic markdownize is billed at unit price 0, so
// free local indexing never consumes the device USD budget cap. Before the fix
// the baseline row carried `usd = $0.01/MB`; because `device_spent` sums every
// adapter_kind, that counted against the device cap and could silently pause
// paid enrichment (and inflate `status.budget.device_spent_usd`).
#[test]
fn f1_offline_baseline_records_zero_usd_and_does_not_consume_budget() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello offline baseline cost").unwrap();
    json_success(&dir, ["index", "--offline", "--yes"]);

    let baseline: Vec<_> = ledger_lines(&dir)
        .into_iter()
        .filter(|entry| entry["adapter_kind"] == "deterministic_baseline")
        .collect();
    assert!(
        !baseline.is_empty(),
        "offline index must still record a deterministic_baseline row (provenance)"
    );
    assert!(
        baseline
            .iter()
            .all(|entry| entry["usd"].as_f64() == Some(0.0)),
        "deterministic_baseline usd must be 0.0: {baseline:?}"
    );

    // Free local work must not lower the remaining device budget.
    let status = json_success(&dir, ["status"]);
    assert_eq!(status["budget"]["device_spent_usd"].as_f64(), Some(0.0));
    assert_eq!(
        status["budget"]["device_remaining_usd"].as_f64(),
        status["budget"]["device_monthly_usd_cap"].as_f64(),
        "device remaining must equal the full cap after free local indexing"
    );
}

// F5: `hard_stop = false` is a soft-stop — an over-cap online task is NOT paused;
// it runs and its real charge is appended to the ledger (so spend is visible to
// `warn_at_percent`) instead of pausing at the cap.
#[test]
fn f5_soft_stop_runs_over_cap_and_records_charge() {
    let dir = scope();
    // R9-2: the over-cap online-task fixture is a PDF (text-native files enqueue no
    // online task, so there would be nothing to soft-stop).
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["soft stop body"])).unwrap();
    // Folder cap 0 with soft-stop: any charge is over cap, but must not pause.
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[budget]\nmonthly_usd_cap = 0\nhard_stop = false\n",
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    let after_index = json_success(&dir, ["status"]);
    assert!(
        !after_index["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|task| task["type"] == "markdownize" && task["status"] == "paused"),
        "soft-stop must not pause the over-cap online task: {after_index}"
    );

    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    let charged = ledger_lines(&dir).into_iter().any(|entry| {
        entry["adapter_kind"] == "markdown" && entry["usd"].as_f64().unwrap_or_default() > 0.0
    });
    assert!(
        charged,
        "soft-stop must append the over-cap charge to the ledger"
    );
    let done = json_success(&dir, ["status"]);
    assert!(
        done["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|task| task["type"] == "markdownize" && task["status"] == "done"),
        "soft-stop online task must run to done: {done}"
    );
}

// F5: crossing `warn_at_percent` surfaces a non-blocking warning in the status and
// index result JSON, without pausing (spend is still under the cap).
#[test]
fn f5_warn_at_percent_surfaces_non_blocking_warning() {
    let dir = scope();
    let fixed_now = "2026-07-15T00:00:00Z";
    // Device (user) cap 1.0, warn at 80%.
    let cfg_dir = dir.path().join(".test-config/kcs");
    fs::create_dir_all(&cfg_dir).unwrap();
    fs::write(
        cfg_dir.join("config.toml"),
        "[budget]\nmonthly_usd_cap = 1.0\nwarn_at_percent = 80\n",
    )
    .unwrap();
    // Seed 0.9 spent this month → 90% of cap (>= 80%, but < 100% so not over cap).
    let ledger = dir.path().join(".test-data/kcs/cost-ledger.jsonl");
    fs::create_dir_all(ledger.parent().unwrap()).unwrap();
    fs::write(
        &ledger,
        "{\"month\":\"2026-07\",\"scope_id\":\"seed\",\"adapter_kind\":\"embedding\",\"usd\":0.9}\n",
    )
    .unwrap();

    let status = json_success_with_env(&dir, ["status"], &[("KCS_FIXED_NOW", fixed_now)]);
    assert_eq!(
        status["budget"]["warned"], true,
        "status must warn at 90% of cap: {status}"
    );
    assert!(status["budget"]["warning"]
        .as_str()
        .unwrap()
        .contains("device budget"));
    assert_eq!(status["budget"]["warn_at_percent"], 80);
    // Non-blocking: budget still remains (not over cap).
    assert!(
        status["budget"]["device_remaining_usd"].as_f64().unwrap() > 0.0,
        "warning must not imply over-cap: {status}"
    );

    // The index result JSON also carries the warning; processing continues.
    let index = json_success_with_env(&dir, ["index", "--yes"], &[("KCS_FIXED_NOW", fixed_now)]);
    assert_eq!(index["status"], "indexed");
    assert!(index["budget_warning"]
        .as_str()
        .unwrap()
        .contains("device budget"));
}

// F5: with `hard_stop` unspecified (default true) and `warn_at_percent` unspecified
// (default 80), the historical behavior holds — an over-cap online task is paused.
#[test]
fn f5_default_hard_stop_pauses_over_cap() {
    let dir = scope();
    // R9-2: the over-cap online-task fixture is a PDF (text-native files enqueue no
    // online task, so there would be nothing to pause).
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hard stop body"])).unwrap();
    // Folder cap 0, no hard_stop key → default hard_stop=true → pause at the cap.
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[budget]\nmonthly_usd_cap = 0\n",
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    let status = json_success(&dir, ["status"]);
    assert!(
        status["tasks"].as_array().unwrap().iter().any(|task| {
            task["type"] == "markdownize"
                && task["status"] == "paused"
                && task["fallback_reason"] == "budget_exceeded"
        }),
        "default hard_stop must pause the over-cap online task: {status}"
    );
    assert_eq!(status["budget"]["hard_stop"], true);
    assert_eq!(status["budget"]["warn_at_percent"], 80);
}

#[test]
fn ct2_image_003_cli_mock_preserves_links_when_replacing_images() {
    let dir = scope();
    // R9-2: image-link replacement happens on the online OCR path, only reached by
    // non-text-native files → PDF fixture.
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello image link"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock_link_image")],
    );
    let unit = normalized_units(&dir)
        .into_iter()
        .find(|unit| unit.markdown.contains("mock ocr"))
        .unwrap();
    assert!(unit.markdown.contains("[source](https://example.com/0)"));
    assert!(unit.markdown.contains("![img-0](kcs://"));
    assert!(!unit.markdown.contains("](img-0.png)"));
}

#[test]
fn ct2_task_005_auth_error_task_is_not_retried() {
    let dir = scope();
    // R9-2: online-task retry lifecycle uses a PDF fixture (non-text-native).
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello auth"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    // R11-2: an auth failure driven this pass → docs/04 §5.6 exit 5, result on stdout.
    let resumed = json_code_stdout_with_env(
        &dir,
        ["batch", "resume"],
        5,
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "auth_error")],
    );
    assert_eq!(resumed["tasks_failed"], 1);
    let status = json_success(&dir, ["status"]);
    let online_task = first_online_task(&status);
    assert_eq!(online_task["status"], "failed");
    assert_eq!(online_task["fallback_reason"], "auth_error");
    assert_eq!(online_task["attempts"], 1);

    let retry = json_success_with_env(
        &dir,
        ["batch", "retry"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    assert_eq!(retry["tasks_updated"], 0);
    let status = json_success(&dir, ["status"]);
    let online_task = first_online_task(&status);
    assert_eq!(online_task["status"], "failed");
    assert_eq!(online_task["attempts"], 1);
}

#[test]
fn ct2_task_009_failed_online_task_is_not_reenqueued_by_reindex() {
    // I2 クロスレビュー指摘の回帰ガード: retryable Failed task が存在する状態で
    // 未変更ファイルを再 index しても、新しい Pending online task が積まれて
    // backoff ゲートを迂回できないこと (Failed の再試行は batch retry の責務)。
    let dir = scope();
    // R9-2: PDF fixture so a retryable online task exists to guard against reindex
    // re-enqueue.
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello dedup"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    // R11-2: a retryable (rate_limit) failure driven this pass → exit 3 (some
    // retryable work remains), result on stdout.
    json_code_stdout_with_env(
        &dir,
        ["batch", "resume"],
        3,
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "rate_limit")],
    );
    let status = json_success(&dir, ["status"]);
    let tasks_after_fail = status["tasks"].as_array().unwrap().len();
    let failed = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|task| task["status"] == "failed")
        .expect("rate_limit mock should leave a failed online task");
    assert!(failed["next_retry_at"].is_string());

    // 未変更で再 index — task 総数が増えない (新規 online task が発行されない)
    json_success(&dir, ["index", "--yes"]);
    let status = json_success(&dir, ["status"]);
    assert_eq!(status["tasks"].as_array().unwrap().len(), tasks_after_fail);
    let failed_count = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| task["status"] == "failed")
        .count();
    assert_eq!(failed_count, 1);
}

#[test]
fn ct2_task_006_partial_online_result_persists_partial_status() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["partial one", "partial two"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "partial")],
    );
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "report.pdf"
            && task["status"] == "partial"
            && task["fallback_reason"] == "online_adapter_done"
    }));
}

/// R9-4: a Partial online markdownize task must be recoverable — `batch retry`
/// completes its Failed units and drives it to Done (docs/04 §5.2 `partial ->
/// done`), and `index_status` counts a Partial as incomplete rather than falsely
/// reporting 100% enrichment. Pre-fix Partial was a dead-end (retry/resume/reindex
/// all ignored it) and `index_status` showed enriched_ratio 1.0 / pending 0 — a
/// silent data gap.
#[test]
fn r9_4_partial_task_recovers_via_retry_and_status_counts_it() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["page one alpha", "page two beta"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    // The `partial` seam drops the last page → a Partial online task.
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "partial")],
    );
    let has_partial = |status: &Value| {
        status["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|task| task["input_path"] == "report.pdf" && task["status"] == "partial")
    };
    assert!(has_partial(&json_success(&dir, ["status"])));
    // index_status (surfaced by search) must NOT claim full enrichment while a unit
    // is still missing.
    let search = json_success(&dir, ["search", "alpha"]);
    assert!(
        search["index_status"]["enriched_ratio"].as_f64().unwrap() < 1.0,
        "a Partial task must lower enriched_ratio: {search}"
    );
    assert!(
        search["index_status"]["pending_enrichment_tasks"]
            .as_u64()
            .unwrap()
            > 0,
        "a Partial task must count as pending enrichment: {search}"
    );

    // Retry with the full mock: the failed unit completes → the task reaches Done.
    let retry = json_success_with_env(
        &dir,
        ["batch", "retry"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    assert!(
        retry["tasks_updated"].as_u64().unwrap() >= 1,
        "the Partial task must be re-enqueued: {retry}"
    );
    assert!(
        retry["tasks_executed"].as_u64().unwrap() >= 1,
        "the re-driven task must complete: {retry}"
    );
    let status = json_success(&dir, ["status"]);
    assert!(
        !has_partial(&status),
        "no Partial task may remain: {status}"
    );
    let search = json_success(&dir, ["search", "alpha"]);
    assert_eq!(
        search["index_status"]["enriched_ratio"].as_f64().unwrap(),
        1.0,
        "the recovered scope must report full enrichment: {search}"
    );
}

/// R10-4: a Partial online markdownize task whose unit keeps failing must NOT be
/// re-sent & re-billed forever. Each `batch retry` charges the retry budget
/// (`attempts`++) and, once `max_attempts` is reached, the task is left Partial and
/// no further online send is issued (`tasks_updated`/`tasks_executed` == 0). Pre-fix
/// `attempts` stayed 0 and every retry re-sent (a fresh cost-ledger markdown row),
/// bounded only by the monthly budget cap.
#[test]
fn r10_4_partial_retry_respects_budget_and_stops_resending() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["page one alpha", "page two beta"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    // The `partial` seam drops the last page -> a Partial online task (attempts 0).
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "partial")],
    );
    // A text-layer PDF has TWO markdownize tasks: the Done local baseline and the
    // online OCR task. Track the online one — at rest it is the Partial task.
    let online_task = |status: &Value| -> Value {
        status["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .find(|task| {
                task["input_path"] == "report.pdf"
                    && task["type"] == "markdownize"
                    && task["status"] == "partial"
            })
            .cloned()
            .expect("partial online markdownize task present")
    };
    let task0 = online_task(&json_success(&dir, ["status"]));
    assert_eq!(task0["status"], "partial");
    let attempts0 = task0["attempts"].as_u64().unwrap();

    // Keep retrying under the SAME still-failing (partial) seam. Attempts must climb
    // while budget remains, then the loop must halt (no further re-enqueue / re-send).
    let mut progressed = false;
    let mut halted = false;
    for _ in 0..12 {
        let retry = json_success_with_env(
            &dir,
            ["batch", "retry"],
            &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "partial")],
        );
        if retry["tasks_updated"].as_u64().unwrap() >= 1 {
            progressed = true;
        }
        if retry["tasks_updated"].as_u64().unwrap() == 0
            && retry["tasks_executed"].as_u64().unwrap() == 0
        {
            halted = true;
            break;
        }
    }
    assert!(
        progressed,
        "retries must progress attempts while the retry budget remains"
    );
    assert!(
        halted,
        "retries must eventually stop re-sending a permanently-failing unit"
    );

    // The task is still Partial (never falsely Done) and attempts advanced then froze.
    let task1 = online_task(&json_success(&dir, ["status"]));
    assert_eq!(
        task1["status"], "partial",
        "a persistently-failing unit stays Partial: {task1}"
    );
    let attempts1 = task1["attempts"].as_u64().unwrap();
    assert!(
        attempts1 > attempts0,
        "attempts must have progressed: {attempts0} -> {attempts1}"
    );

    // Once halted, a further retry issues no work at all — the re-billing loop is
    // closed.
    let again = json_success_with_env(
        &dir,
        ["batch", "retry"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "partial")],
    );
    assert_eq!(
        again["tasks_updated"].as_u64().unwrap(),
        0,
        "halted task must not re-enqueue: {again}"
    );
    assert_eq!(
        again["tasks_executed"].as_u64().unwrap(),
        0,
        "halted task must not re-send: {again}"
    );
}

// R11-6: a unit-scoped retry re-sends and re-bills ONLY the still-failed units, not
// the whole document, and keeps the already-done units' output verbatim
// (first-instance-wins). Before R11-6 `unit_keys` was written but never read: every
// retry re-sent the full document (a full-price ledger row) and regenerated the done
// units (fingerprint churn → needless re-embedding).
#[test]
fn r11_6_unit_scoped_retry_prorates_cost_and_preserves_done_units() {
    let dir = scope();
    // 3-page PDF: the `partial` seam drops the last page → page:3 fails, page:1/2 done.
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["page one alpha", "page two beta", "page three gamma"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "partial")],
    );

    let markdown_costs = |dir: &TempDir| -> Vec<f64> {
        ledger_lines(dir)
            .iter()
            .filter(|entry| {
                entry["adapter_kind"] == "markdown" && entry["usd"].as_f64().unwrap_or(0.0) > 0.0
            })
            .map(|entry| entry["usd"].as_f64().unwrap())
            .collect()
    };
    let first = markdown_costs(&dir);
    assert_eq!(
        first.len(),
        1,
        "the first send bills exactly one full-document row: {first:?}"
    );
    let full_cost = first[0];

    // The online (mock) done unit for page:1 before the retry.
    let online_page1 = |dir: &TempDir| -> NormalizedUnitObject {
        normalized_units(dir)
            .into_iter()
            .find(|unit| unit.unit_key == "page:1" && unit.markdown.contains("mock ocr"))
            .expect("online page:1 normalized unit")
    };
    let before = online_page1(&dir);

    // Unit-scoped retry: re-sends ONLY the still-failing page:3 → a smaller ledger row.
    json_success_with_env(
        &dir,
        ["batch", "retry"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "partial")],
    );

    let after_costs = markdown_costs(&dir);
    assert!(
        after_costs.len() >= 2,
        "the retry appends its own markdown row: {after_costs:?}"
    );
    let retry_cost = *after_costs.last().unwrap();
    assert!(
        retry_cost < full_cost,
        "unit-scoped retry ({retry_cost}) must bill less than the full document ({full_cost})"
    );

    // First-instance-wins: the already-done page:1 output is unchanged across the retry
    // (regenerating it under Markdown non-determinism would churn its fingerprint).
    let after = online_page1(&dir);
    assert_eq!(
        before.markdown, after.markdown,
        "a done unit's output must not change across a retry"
    );
}

/// R9-7: `batch retry`/`resume` must report driven online-send attempts and
/// failures in their JSON, not just successes. Pre-fix a Pending online task that
/// failed on send left `{tasks_executed:0, tasks_updated:0}` — the attempt (rate
/// limit / auth / charge consumed) was invisible to an orchestrator.
#[test]
fn r9_7_batch_retry_reports_failed_attempts_in_json() {
    let dir = scope();
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["body text"])).unwrap();
    // Approve network so the Pending online task is ready to send.
    json_success(&dir, ["index", "--approve"]);
    // Retry drives the Pending online task; the auth_error mock fails the send.
    // R11-2: the auth failure this pass exits 5, with the full result JSON on stdout.
    let retry = json_code_stdout_with_env(
        &dir,
        ["batch", "retry"],
        5,
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "auth_error")],
    );
    assert_eq!(
        retry["tasks_executed"], 0,
        "the send failed, nothing completed: {retry}"
    );
    assert_eq!(
        retry["tasks_attempted"], 1,
        "the failed send must appear as an attempt: {retry}"
    );
    assert_eq!(
        retry["tasks_failed"], 1,
        "the failure must be reported: {retry}"
    );
    // The task really transitioned Pending -> Failed (the send was attempted).
    let status = json_success(&dir, ["status"]);
    assert_eq!(first_online_task(&status)["status"], "failed");
}

/// R9-2: text-native files (Markdown / plain text / code) must NOT enqueue an
/// online Mistral-OCR task — they are fully handled by the deterministic Adapter
/// (07 §2.1 / §5.2). A non-text-native PDF still does (routing preserved). Pre-fix
/// every text file's raw bytes were queued for a third-party OCR API and billed
/// ~10x the baseline for redundant, orphaned work.
#[test]
fn r9_2_text_native_files_do_not_enqueue_online_ocr_task() {
    let dir = scope();
    // Standing network opt-in so the media gate is the ONLY thing that could stop
    // the enqueue.
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[adapter.policy]\nallow_network = true\n",
    )
    .unwrap();
    fs::write(dir.path().join("note.md"), "# Note\n\nbody text here\n").unwrap();
    fs::write(dir.path().join("main.rs"), "fn main() { let _x = 1; }\n").unwrap();
    fs::write(dir.path().join("plain.txt"), "just some plain text\n").unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    assert_eq!(
        output["pending_online_tasks"].as_u64().unwrap(),
        0,
        "text-native files must not enqueue online tasks: {output}"
    );
    let status = json_success(&dir, ["status"]);
    assert!(
        !status["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .any(is_online_output_ref),
        "no online-output-ref task may exist for text-native files: {status}"
    );

    // A PDF in the same scope still enqueues an online task (routing preserved).
    fs::write(dir.path().join("scan.pdf"), fake_pdf(&["scanned page"])).unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    assert!(
        output["pending_online_tasks"].as_u64().unwrap() > 0,
        "a PDF must still enqueue an online task: {output}"
    );
    assert!(
        json_success(&dir, ["status"])["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|task| task["input_path"] == "scan.pdf" && is_online_output_ref(task)),
        "the PDF's online task must be present"
    );
}

#[test]
fn ct2_task_007_online_task_not_reissued_for_completed_identity() {
    // Step2c I1: once an online task for an identity is Done, re-indexing the
    // unchanged file must not enqueue a duplicate task. The bug was a later
    // `batch resume` re-sending that duplicate and double-charging the ledger.
    let dir = scope();
    // R9-2: PDF fixture so a real online task is enqueued for the dedup guard.
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello dedup"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    // A completed online task keeps this fallback_reason even after its
    // output_ref is rewritten to the normalized-instance path.
    let completed_online = |status: &Value| -> usize {
        status["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|task| task["fallback_reason"] == "online_adapter_done")
            .count()
    };
    let done = json_success(&dir, ["status"]);
    assert_eq!(
        completed_online(&done),
        1,
        "resume should complete exactly one online task"
    );
    let tasks_before = done["tasks"].as_array().unwrap().len();
    let ledger_before = ledger_lines(&dir).len();
    assert!(ledger_before > 0);

    // Unchanged re-index: the pipeline runs but must not pile a duplicate task.
    json_success(&dir, ["index", "--yes"]);
    let after = json_success(&dir, ["status"]);
    assert_eq!(
        after["tasks"].as_array().unwrap().len(),
        tasks_before,
        "unchanged re-index must not enqueue a duplicate online task"
    );
    assert_eq!(completed_online(&after), 1);

    // Resuming again must find nothing to execute and must not re-charge.
    let second = json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    assert_eq!(
        second["tasks_executed"], 0,
        "no duplicate online task should remain to execute"
    );
    assert_eq!(
        ledger_lines(&dir).len(),
        ledger_before,
        "re-index + resume must not double-charge the ledger"
    );

    // A changed file yields a new input_hash and does enqueue a fresh task.
    fs::write(
        dir.path().join("a.pdf"),
        fake_pdf(&["hello dedup changed content"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--yes"]);
    let changed = json_success(&dir, ["status"]);
    let pending_online = changed["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| is_online_output_ref(task))
        .count();
    assert_eq!(
        pending_online, 1,
        "a changed file (new input_hash) must enqueue a fresh online task"
    );
}

#[test]
fn ct2_task_008_retryable_failure_defers_until_backoff_elapses() {
    // Step2c I2: a retryable failure schedules `next_retry_at` in the future
    // (exp/retry_after backoff). `batch retry` skips the task until that time
    // is reached, then executes it.
    let dir = scope();
    // R9-2: PDF fixture so a real online task exists to fail and retry.
    fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello retry backoff"])).unwrap();
    json_success(&dir, ["index", "--approve"]);

    // Fail the online task with a rate-limit-like (retryable) error at T0.
    // R11-2: a retryable failure driven this pass exits 3 (result on stdout).
    kcs(&dir, ["batch", "resume"])
        .env(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "rate_limit")
        .env("KCS_FIXED_NOW", "2026-07-03T00:00:00Z")
        .arg("--json")
        .assert()
        .code(3);
    let status = json_success(&dir, ["status"]);
    let failed = first_online_task(&status);
    assert_eq!(failed["status"], "failed");
    assert_eq!(failed["attempts"], 1);
    let next_retry_at = failed["next_retry_at"].as_str().unwrap();
    assert!(
        next_retry_at > "2026-07-03T00:00:00Z",
        "backoff must schedule a future retry, got {next_retry_at}"
    );

    // Retry at the same instant: backoff has not elapsed, nothing runs.
    let early = json_success_with_env(
        &dir,
        ["batch", "retry"],
        &[
            (TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock"),
            ("KCS_FIXED_NOW", "2026-07-03T00:00:00Z"),
        ],
    );
    assert_eq!(early["tasks_updated"], 0);
    assert_eq!(early["tasks_executed"], 0);
    let still_failed = json_success(&dir, ["status"]);
    assert!(still_failed["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .any(|task| is_online_output_ref(task) && task["status"] == "failed"));

    // Advance the clock past the backoff window: the task becomes due and runs.
    let late = json_success_with_env(
        &dir,
        ["batch", "retry"],
        &[
            (TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock"),
            ("KCS_FIXED_NOW", "2026-07-03T01:00:00Z"),
        ],
    );
    assert_eq!(late["tasks_updated"], 1);
    assert_eq!(late["tasks_executed"], 1);
    let resolved = json_success(&dir, ["status"]);
    // On success the online task's output_ref is rewritten to the normalized
    // path but stamped with this fallback_reason.
    assert!(resolved["tasks"].as_array().unwrap().iter().any(|task| {
        task["fallback_reason"] == "online_adapter_done"
            && (task["status"] == "done" || task["status"] == "partial")
    }));
}

#[test]
fn ct2_index_001_preview_approve_ingest_auto_snapshot() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    assert_eq!(
        json_success(&dir, ["index", "--preview"])["status"],
        "preview"
    );
    let output = json_success(&dir, ["index", "--approve"]);
    assert!(output["commit_hash"].as_str().is_some());
}

#[test]
fn ct2_index_002_successful_index_commit_type_auto() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let output = json_success(&dir, ["index", "--approve"]);
    assert_eq!(output["commit"]["commit_type"], "auto");
}

#[test]
fn ct2_index_003_unchanged_tree_auto_snapshot_noop() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    json_success(&dir, ["index", "--approve"]);
    let before = head(&dir);
    let second = json_success(&dir, ["index", "--yes"]);
    assert_eq!(second["status"], "noop");
    assert!(second["commit_hash"].is_null());
    assert_eq!(head(&dir), before);
}

fn collect_files(root: &Path) -> BTreeSet<PathBuf> {
    let mut out = BTreeSet::new();
    collect_files_inner(root, root, &mut out);
    out
}

fn collect_files_inner(root: &Path, current: &Path, out: &mut BTreeSet<PathBuf>) {
    if !current.exists() {
        return;
    }
    for entry in fs::read_dir(current).unwrap() {
        let entry = entry.unwrap();
        let path = entry.path();
        if path.is_dir() {
            collect_files_inner(root, &path, out);
        } else {
            out.insert(path.strip_prefix(root).unwrap().to_path_buf());
        }
    }
}

/// R13-4: an empty or missing `.kcs/HEAD` with a healthy `refs/heads/main` is a
/// CORRUPT HEAD, not an unborn branch. Before the fix `head_commit_hash` returned
/// `None`, so `log` showed nothing and `snapshot` orphaned all history under a
/// fresh `parents=[]` root commit (silent data loss, exit 0). Now HEAD is
/// self-repaired from refs on `open`, so `log` shows C1 and the next `snapshot`
/// extends it. A genuinely unborn branch (both empty) still root-commits.
fn events_log(dir: &TempDir) -> String {
    let path = dir.path().join(".test-data/kcs/logs/events.jsonl");
    fs::read_to_string(path).unwrap_or_default()
}

#[test]
fn r13_4_empty_head_with_healthy_refs_is_repaired_not_orphaned() {
    let dir = scope();
    fs::write(dir.path().join("doc.txt"), "v1").unwrap();
    let c1 = json_success(&dir, ["snapshot", "-m", "first"]);
    let c1_hash = c1["commit_hash"].as_str().unwrap().to_owned();

    // Corrupt HEAD to empty; refs/heads/main still names C1.
    fs::write(dir.path().join(".kcs/HEAD"), "").unwrap();
    assert_eq!(
        fs::read_to_string(dir.path().join(".kcs/refs/heads/main")).unwrap(),
        c1_hash,
        "precondition: refs still names C1"
    );

    // (a) `log` must surface C1 (HEAD self-heals on open).
    let log = json_success(&dir, ["log"]);
    assert!(
        log["commits"]
            .as_array()
            .unwrap()
            .iter()
            .any(|commit| commit["commit_hash"] == c1_hash),
        "log must show the recovered C1: {log}"
    );

    // (a) the next snapshot must extend C1, not orphan it under a root commit.
    fs::write(dir.path().join("doc.txt"), "v2").unwrap();
    let c2 = json_success(&dir, ["snapshot", "-m", "after"]);
    assert_eq!(c2["status"], "created");
    assert_eq!(
        c2["commit"]["parents"].as_array().unwrap(),
        &vec![json!(c1_hash)],
        "C2 must have C1 as its parent (history preserved): {c2}"
    );

    // (d) the recovery is recorded (never silent).
    assert!(
        events_log(&dir).contains("KCS-I-STORE-HEAD-REPAIRED-001"),
        "HEAD repair must be logged to events.jsonl"
    );
}

#[test]
fn r13_4_missing_head_with_healthy_refs_is_repaired() {
    let dir = scope();
    fs::write(dir.path().join("doc.txt"), "v1").unwrap();
    let c1 = json_success(&dir, ["snapshot", "-m", "first"]);
    let c1_hash = c1["commit_hash"].as_str().unwrap().to_owned();

    // (b) delete HEAD entirely; refs/heads/main still healthy.
    fs::remove_file(dir.path().join(".kcs/HEAD")).unwrap();
    let log = json_success(&dir, ["log"]);
    assert!(log["commits"]
        .as_array()
        .unwrap()
        .iter()
        .any(|commit| commit["commit_hash"] == c1_hash));
    assert_eq!(
        fs::read_to_string(dir.path().join(".kcs/HEAD"))
            .unwrap()
            .trim(),
        c1_hash,
        "HEAD file must be restored on disk"
    );
}

#[test]
fn r13_4_fresh_init_both_empty_still_root_commits() {
    // (c) a genuinely unborn branch (HEAD and refs both empty at fresh init) must
    // NOT be treated as corrupt — the first snapshot is still a root commit and no
    // repair event is emitted.
    let dir = scope();
    fs::write(dir.path().join("doc.txt"), "v1").unwrap();
    let first = json_success(&dir, ["snapshot", "-m", "first"]);
    assert_eq!(first["status"], "created");
    assert!(
        first["commit"]["parents"].as_array().unwrap().is_empty(),
        "the first snapshot on a fresh scope is a root commit"
    );
    assert!(
        !events_log(&dir).contains("KCS-I-STORE-HEAD-REPAIRED-001"),
        "fresh init must not emit a spurious HEAD-repair event"
    );
}

/// R13-5: re-`init` on a broken store used to report "already initialized" exit 0
/// without verifying or repairing anything, leaving the store broken for the very
/// next command. Now a recoverable HEAD is repaired (via the R13-4 self-heal path)
/// and reported; unrecoverable corruption (bad scope.json) exits non-zero.
#[test]
fn r13_5_reinit_repairs_missing_head_and_status_recovers() {
    let dir = scope();
    fs::write(dir.path().join("doc.txt"), "v1").unwrap();
    json_success(&dir, ["snapshot", "-m", "first"]);

    fs::remove_file(dir.path().join(".kcs/HEAD")).unwrap();
    let reinit = json_success(&dir, ["init", "."]);
    assert_eq!(
        reinit["status"], "repaired",
        "re-init must report the repair"
    );
    assert_eq!(reinit["repaired"], json!(["HEAD"]));

    // The natural recovery worked: the next command succeeds (exit 0) instead of
    // KCS-E-STORE-IO-001.
    json_success(&dir, ["status"]);
}

#[test]
fn r13_5_reinit_reports_already_initialized_when_healthy() {
    let dir = scope();
    fs::write(dir.path().join("doc.txt"), "v1").unwrap();
    json_success(&dir, ["snapshot", "-m", "first"]);
    let reinit = json_success(&dir, ["init", "."]);
    assert_eq!(reinit["status"], "already initialized");
    assert_eq!(reinit["repaired"], json!([]));
}

#[test]
fn r13_5_reinit_on_unrecoverable_corruption_exits_nonzero() {
    let dir = scope();
    // Corrupt scope.json (unrecoverable) → re-init must NOT swallow it as
    // "already initialized"; open()'s validate rejects it with a non-zero exit.
    fs::write(dir.path().join(".kcs/scope.json"), "{ not valid json").unwrap();
    let err = json_failure(&dir, ["init", "."], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

/// R13-6: with no absolute `$HOME` and no `$XDG_*` override, device-global state
/// used to scatter into a CWD-relative `kcs/` (registry, cost ledger, logs, the
/// 0600 cursor-signing key) and the device budget cap silently split per working
/// directory. Now the startup guard refuses to run and writes nothing under CWD.
fn kcs_no_base<const N: usize>(work: &Path, home: Option<&str>, args: [&str; N]) -> Command {
    let mut command = hermetic_kcs_command();
    command
        .current_dir(work)
        .env_remove("XDG_CONFIG_HOME")
        .env_remove("XDG_DATA_HOME")
        .env_remove("XDG_CACHE_HOME")
        .args(args);
    match home {
        Some(value) => command.env("HOME", value),
        None => command.env_remove("HOME"),
    };
    command
}

#[test]
fn r13_6_unset_home_no_xdg_errors_and_writes_nothing_under_cwd() {
    for (label, home) in [
        ("unset", None),
        ("empty", Some("")),
        ("relative", Some("rel/path")),
    ] {
        let work = tempfile::tempdir().unwrap();
        let output = kcs_no_base(work.path(), home, ["init", ".", "--json"])
            .assert()
            .code(2)
            .get_output()
            .stderr
            .clone();
        let err: Value = serde_json::from_slice(&output).unwrap();
        assert_eq!(
            err["error_code"], "KCS-E-CONFIG-USAGE-001",
            "HOME={label}: must be a loud usage error"
        );
        // Nothing device-global may be written under the working directory.
        assert!(
            !work.path().join("kcs").exists(),
            "HOME={label}: device-global `kcs/` must not be created under CWD"
        );
    }
}

#[test]
fn r13_6_absolute_xdg_lets_commands_run_even_without_home() {
    // An absolute XDG override is a valid base even when HOME is unset — the guard
    // must NOT block that case (XDG takes precedence over HOME).
    let work = tempfile::tempdir().unwrap();
    let xdg = tempfile::tempdir().unwrap();
    let mut command = hermetic_kcs_command();
    command
        .current_dir(work.path())
        .env_remove("HOME")
        .env("XDG_CONFIG_HOME", xdg.path().join("config"))
        .env("XDG_DATA_HOME", xdg.path().join("data"))
        .env("XDG_CACHE_HOME", xdg.path().join("cache"))
        .args(["init", ".", "--json"]);
    command.assert().success();
    assert!(!work.path().join("kcs").exists());
}

// R13-1: incremental Markdownize on the ONLINE (Mistral OCR) route. Before the fix
// the online adapter never declared `incremental_update` and the request path
// hard-coded mode=Full, so every light revision re-sent (and re-billed) the whole
// document. These exercise the mock OCR seam across a v1→v2 revision.
fn online_incremental_task(status: &Value) -> Option<&Value> {
    status["tasks"].as_array().unwrap().iter().find(|task| {
        task["input_path"] == "report.pdf"
            && task["fallback_reason"] == "online_adapter_done"
            && task["status"] == "done"
            && task["mode"] == "incremental"
    })
}

#[test]
fn r13_1_online_incremental_fires_on_light_revision_and_reuses_unchanged() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2", "p3", "p4", "p5"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    // v2: a light revision — only page 2 changes (change_rate 1/5 = 0.2 < 0.30).
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2 changed", "p3", "p4", "p5"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--yes"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    // (a) the v2 online task fired incremental and named the changed unit.
    let status = json_success(&dir, ["status"]);
    let online = online_incremental_task(&status)
        .unwrap_or_else(|| panic!("expected an online incremental task: {status}"));
    assert!(
        online["changed_unit_keys"]
            .as_array()
            .unwrap()
            .contains(&json!("page:2")),
        "changed_unit_keys must name page:2: {online}"
    );

    // (b) the 4 unchanged pages were reused from the prior online instance
    // (mode=incremental + reused_from). The offline deterministic adapter never
    // declares incremental_update, so these can only come from the online route.
    let reused = normalized_units(&dir)
        .into_iter()
        .filter(|unit| unit.mode == MarkdownizeMode::Incremental && unit.reused_from.is_some())
        .count();
    assert_eq!(
        reused, 4,
        "4 unchanged pages must be reused from the prior run"
    );
}

#[test]
fn r13_1_online_full_when_change_rate_exceeds_threshold() {
    let dir = scope();
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["a1", "a2", "a3"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    // v2: every page changes (change_rate 3/3 = 1.0 >= 0.30) → stays Full.
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["b1", "b2", "b3"])).unwrap();
    json_success(&dir, ["index", "--yes"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    let status = json_success(&dir, ["status"]);
    assert!(
        online_incremental_task(&status).is_none(),
        "a full-document change must NOT use incremental: {status}"
    );
    // Both v1 and v2 online tasks completed as Full sends.
    let online_done = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| {
            task["input_path"] == "report.pdf"
                && task["fallback_reason"] == "online_adapter_done"
                && task["status"] == "done"
        })
        .count();
    assert_eq!(
        online_done, 2,
        "v1 + v2 online tasks both done (Full): {status}"
    );
}

#[test]
fn r13_1_online_incremental_acceptance_fail_falls_back_to_full() {
    let dir = scope();
    // 7 pages so a 2-page change is light (2/7 ≈ 0.29 < 0.30) → incremental fires,
    // but the `incr_incomplete` seam drops a requested unit so acceptance fails.
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2", "p3", "p4", "p5", "p6", "p7"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2 X", "p3", "p4 X", "p5", "p6", "p7"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--yes"]);
    // incr_incomplete: the incremental response drops a requested page → the KCS
    // acceptance check fails → the online route re-sends Full (which returns every
    // page) → the task completes as Full, not incremental.
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "incr_incomplete")],
    );

    let status = json_success(&dir, ["status"]);
    assert!(
        online_incremental_task(&status).is_none(),
        "acceptance failure must fall back to Full (no incremental task): {status}"
    );
    // The Full fallback succeeded: 2 online done tasks (v1 + v2), no failure.
    let online_done = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| {
            task["input_path"] == "report.pdf"
                && task["fallback_reason"] == "online_adapter_done"
                && task["status"] == "done"
        })
        .count();
    assert_eq!(online_done, 2, "both online tasks done via Full: {status}");
}

// R14-1: a partially-corrupt previous instance (`manifest.json` still claims a unit
// is `done` but the unit's `<unit_ref>.json` is missing/unreadable) must degrade to
// "no usable previous" and re-send Full — never a hard Err. Before the fix
// `load_previous_instance` returned a non-retryable Err for the missing unit, which
// permanently bricked the document's online markdownize (every run read the same
// corrupt previous and failed identically) and, on the offline route, aborted the
// whole `kcs index`, silently skipping alphabetically-later files.

/// The instance directory (`output_ref`) of the DONE offline markdownize task for a
/// path — used to plant a corruption inside a prior normalized instance.
fn offline_instance_output_ref(dir: &TempDir, input_path: &str) -> String {
    let status = json_success(dir, ["status"]);
    status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|task| {
            task["input_path"] == input_path
                && task["type"] == "markdownize"
                && task["status"] == "done"
                && !task["output_ref"]
                    .as_str()
                    .unwrap_or_default()
                    .starts_with("online:")
        })
        .and_then(|task| task["output_ref"].as_str())
        .unwrap_or_else(|| panic!("offline instance output_ref for {input_path}: {status}"))
        .to_owned()
}

/// Delete one unit `<unit_ref>.json` inside a normalized instance dir, leaving
/// `manifest.json` (which still marks the unit `done`) intact.
fn corrupt_one_unit_json(instance_dir: &Path) {
    let unit_json = fs::read_dir(instance_dir)
        .unwrap()
        .flatten()
        .map(|entry| entry.path())
        .find(|path| {
            path.extension().and_then(|ext| ext.to_str()) == Some("json")
                && path.file_name().and_then(|name| name.to_str()) != Some("manifest.json")
        })
        .unwrap_or_else(|| panic!("a unit json to corrupt under {}", instance_dir.display()));
    fs::remove_file(&unit_json).unwrap();
}

// (a)+(d): online route — a deleted unit in the v1 online instance must not brick the
// document; v2 re-sends Full and completes (self-heal), never a stuck failed task.
#[test]
fn r14_1_online_previous_partial_corruption_recovers_via_full() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2", "p3", "p4", "p5"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    // Corrupt the v1 online instance: delete ONE unit json (manifest untouched).
    let status = json_success(&dir, ["status"]);
    let output_ref = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|task| {
            task["input_path"] == "report.pdf"
                && task["fallback_reason"] == "online_adapter_done"
                && task["status"] == "done"
        })
        .and_then(|task| task["output_ref"].as_str())
        .unwrap_or_else(|| panic!("v1 online done task with instance output_ref: {status}"))
        .to_owned();
    corrupt_one_unit_json(Path::new(&output_ref));

    // v2 light revision (would be incremental if the previous were intact).
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2 changed", "p3", "p4", "p5"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--yes"]);
    let resume = json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    // The corrupt previous is bypassed (Full re-send), not a hard non-retryable fail.
    assert_eq!(
        resume["tasks_failed"], 0,
        "corrupt previous must degrade to Full, not fail the task: {resume}"
    );

    // v1 + v2 online tasks are both done; v2 could NOT reuse the corrupt previous, so
    // it is a Full send, not incremental.
    let status = json_success(&dir, ["status"]);
    let done_online = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| {
            task["input_path"] == "report.pdf"
                && task["fallback_reason"] == "online_adapter_done"
                && task["status"] == "done"
        })
        .count();
    assert!(
        done_online >= 2,
        "v2 online task must recover via a Full re-send: {status}"
    );
    assert!(
        online_incremental_task(&status).is_none(),
        "a corrupt previous cannot drive incremental — v2 must be Full: {status}"
    );
}

// (b): offline route — a corrupt prior instance for one file must not abort the whole
// index and skip alphabetically-later candidates.
#[test]
fn r14_1_offline_previous_corruption_does_not_abort_index() {
    let dir = scope();
    // `report.pdf` sorts before `zzz.pdf`; report.pdf gets the corrupt previous.
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["a1", "a2", "a3"])).unwrap();
    fs::write(dir.path().join("zzz.pdf"), fake_pdf(&["z1", "z2"])).unwrap();
    json_success(&dir, ["index", "--approve"]);

    corrupt_one_unit_json(Path::new(&offline_instance_output_ref(&dir, "report.pdf")));

    // Change report.pdf so re-index reaches `previous_instance_for_path` (a new
    // raw_hash bypasses the done-output early return).
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["a1 X", "a2", "a3"]),
    )
    .unwrap();
    // Before the fix this aborted the whole index (exit 1); now report.pdf
    // re-normalizes as Full and the run continues — `json_success` asserts exit 0.
    let reindex = json_success(&dir, ["index", "--yes"]);
    assert!(
        reindex["normalized_files"].as_u64().unwrap() >= 1,
        "report.pdf must re-normalize (Full), not abort the index: {reindex}"
    );

    // zzz.pdf (sorts after report.pdf) is still tracked — the index did not abort
    // before reaching it.
    let status = json_success(&dir, ["status"]);
    assert!(
        status["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|task| task["input_path"] == "zzz.pdf" && task["status"] == "done"),
        "zzz.pdf must remain indexed (not skipped by an aborted run): {status}"
    );
}

// (c): the pre-existing missing-`manifest.json` degradation (Ok(None) → Full) is
// unchanged by the unit-corruption fix that now sits beside it.
#[test]
fn r14_1_offline_previous_missing_manifest_still_degrades_to_full() {
    let dir = scope();
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["a1", "a2"])).unwrap();
    json_success(&dir, ["index", "--approve"]);

    let output_ref = offline_instance_output_ref(&dir, "report.pdf");
    fs::remove_file(Path::new(&output_ref).join("manifest.json")).unwrap();

    fs::write(dir.path().join("report.pdf"), fake_pdf(&["a1 X", "a2"])).unwrap();
    let reindex = json_success(&dir, ["index", "--yes"]);
    assert!(
        reindex["normalized_files"].as_u64().unwrap() >= 1,
        "missing manifest must still degrade to a Full re-normalize: {reindex}"
    );
}

// R14-2: an online markdownize task is deferred (enqueued by `index`, executed by a
// later `batch resume`), so the file can change in between. Executing the stale task
// would read the CURRENT bytes yet persist them under the enqueue-time `input_hash`
// (= v2 content stored under v1 identity), breaking content-addressing, mis-billing,
// and poisoning the next incremental baseline. The fix supersedes a task whose current
// file no longer hashes to `input_hash`, without persisting anything under the old hash.

/// Number of persisted normalized instances (one `manifest.json` each).
fn instance_manifest_count(dir: &TempDir) -> usize {
    let root = dir.path().join(".kcs/objects/normalized_units");
    collect_files(&root)
        .iter()
        .filter(|path| path.file_name().and_then(|name| name.to_str()) == Some("manifest.json"))
        .count()
}

// (a)+(c)+(d): a file edited AFTER enqueue but BEFORE execution supersedes the stale
// task (no instance under the old hash), and a re-index recovers the current content.
#[test]
fn r14_2_stale_online_task_superseded_then_recovers_on_reindex() {
    let dir = scope();
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["p1", "p2"])).unwrap();
    // `index` enqueues the online task for H(v1) but does NOT run it.
    json_success(&dir, ["index", "--approve"]);
    let instances_before = instance_manifest_count(&dir);

    // (a) Edit to v2 WITHOUT re-indexing → the online task's input_hash is now stale.
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2 changed"]),
    )
    .unwrap();
    let resume = json_code_stdout_with_env(
        &dir,
        ["batch", "resume"],
        4,
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    assert_eq!(
        resume["tasks_executed"], 0,
        "a stale task must not execute: {resume}"
    );
    assert!(
        resume["tasks_failed"].as_u64().unwrap() >= 1,
        "a stale task is superseded (failed), not executed: {resume}"
    );
    // No new normalized instance was persisted → v2 bytes are NOT stored under the v1
    // raw_hash identity (content-addressing invariant preserved).
    assert_eq!(
        instance_manifest_count(&dir),
        instances_before,
        "a superseded stale task must not persist any normalized instance"
    );
    let status = json_success(&dir, ["status"]);
    assert!(
        !status["tasks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|task| task["input_path"] == "report.pdf"
                && task["fallback_reason"] == "online_adapter_done"),
        "no online done instance for the superseded task: {status}"
    );

    // (c)+(d) recovery: re-index enqueues a fresh online task for the CURRENT (v2)
    // content; batch resume completes it under its own correct identity. Since no v1
    // online instance was poisoned, the next enrichment is a clean send.
    json_success(&dir, ["index", "--yes"]);
    let recover = json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    assert_eq!(
        recover["tasks_failed"], 0,
        "the recovery send must succeed: {recover}"
    );
    let status = json_success(&dir, ["status"]);
    assert!(
        status["tasks"].as_array().unwrap().iter().any(|task| {
            task["input_path"] == "report.pdf"
                && task["fallback_reason"] == "online_adapter_done"
                && task["status"] == "done"
        }),
        "the current (v2) content is enriched under its own identity: {status}"
    );
}

// (b): an unchanged file (current bytes still hash to `input_hash`) executes normally.
#[test]
fn r14_2_unchanged_online_task_executes_normally() {
    let dir = scope();
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["p1", "p2"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    // No edit between enqueue and execution.
    let resume = json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    assert!(
        resume["tasks_executed"].as_u64().unwrap() >= 1,
        "an unchanged task must execute: {resume}"
    );
    assert_eq!(
        resume["tasks_failed"], 0,
        "an unchanged task must not be superseded: {resume}"
    );
    let status = json_success(&dir, ["status"]);
    assert!(
        status["tasks"].as_array().unwrap().iter().any(|task| {
            task["input_path"] == "report.pdf"
                && task["fallback_reason"] == "online_adapter_done"
                && task["status"] == "done"
        }),
        "an unchanged online task completes: {status}"
    );
}

// R15-2: a stale online markdownize task (current bytes no longer hash to `input_hash`)
// is superseded inside the executor WITHOUT ever calling the adapter (R14-2). Before
// R15-2, `execute_pending_markdownize_tasks` reserved the markdownize cost (F8 charges
// under the device-global cost-ledger lock BEFORE the send) and only THEN entered the
// executor, which immediately superseded the task — leaving a PHANTOM markdown row for a
// send that never happened. That double-bills and can exhaust the per-adapter markdownize
// cap, falsely pausing the valid task. The pre-charge gate must verify the network-free
// preconditions first: a stale task fails WITHOUT any markdown charge landing.
#[test]
fn r15_2_stale_online_task_supersede_does_not_phantom_charge() {
    let dir = scope();
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["p1", "p2"])).unwrap();
    // `index` enqueues the online task for H(v1) but does NOT run it — so no markdown
    // charge has landed yet (the send is what bills).
    json_success(&dir, ["index", "--approve"]);

    let markdown_rows = |dir: &TempDir| -> usize {
        ledger_lines(dir)
            .iter()
            .filter(|entry| {
                entry["adapter_kind"] == "markdown" && entry["usd"].as_f64().unwrap_or(0.0) > 0.0
            })
            .count()
    };
    assert_eq!(
        markdown_rows(&dir),
        0,
        "index alone must not charge markdown before any send"
    );

    // Edit to v2 WITHOUT re-indexing → the task's input_hash is now stale.
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2 changed"]),
    )
    .unwrap();
    let resume = json_code_stdout_with_env(
        &dir,
        ["batch", "resume"],
        4,
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );
    assert_eq!(
        resume["tasks_executed"], 0,
        "a stale task must not execute (adapter never called): {resume}"
    );
    assert!(
        resume["tasks_failed"].as_u64().unwrap() >= 1,
        "a stale task is superseded (failed): {resume}"
    );

    // The phantom charge is gone: the pre-charge gate failed the task before reserving
    // the cost, so no markdown row exists for a send that never happened.
    assert_eq!(
        markdown_rows(&dir),
        0,
        "a superseded stale task must not phantom-charge the cost-ledger"
    );
}

// R15-6: a 0-change incremental (metadata-only edit → new raw_hash but every page's
// content byte-identical, change_rate 0) must NOT call the adapter — with nothing
// changed/added there is no page to OCR. Before this, the empty `requested` still issued
// an Incremental request whose empty `pages` the real Mistral client paired with the
// WHOLE base64 document (all-pages upload/bill); the plain `mock` seam hid this by
// composing only from the (empty) hints. The `no_change_no_send` seam keeps the pin
// stable (so incremental fires) but fails loudly on ANY incremental send — so a resume
// that reaches the adapter fails, while the fix completes `done` by reuse (exit 0).
#[test]
fn r15_6_zero_change_incremental_reuses_without_calling_adapter() {
    let dir = scope();
    let v1 = fake_pdf(&["stable page body content"]);
    fs::write(dir.path().join("report.pdf"), &v1).unwrap();
    // v1: enqueue + run the online task (mock) → the prior online instance.
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    // v2: append a trailing PDF comment. The raw bytes (raw_hash) change — so re-index
    // enqueues a fresh online task — but the page stream text is byte-identical, so every
    // unit maps `unchanged` (change_rate 0). `pdf_text_pages` ignores bytes after %%EOF.
    let v2 = format!("{v1}%kcs-metadata-only-change\n");
    assert_ne!(hash_bytes(v2.as_bytes()), hash_bytes(v1.as_bytes()));
    fs::write(dir.path().join("report.pdf"), &v2).unwrap();
    json_success(&dir, ["index", "--yes"]);

    // Resume under `no_change_no_send`: an incremental send would fail loudly (the seam's
    // guard). With the fix the 0-change task never calls the adapter, so it completes
    // `done` purely by reuse → exit 0, no failure.
    let resume = json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "no_change_no_send")],
    );
    assert_eq!(
        resume["tasks_failed"], 0,
        "a 0-change incremental must not call the adapter (the seam fails any send): {resume}"
    );
    let status = json_success(&dir, ["status"]);
    assert!(
        status["tasks"].as_array().unwrap().iter().any(|task| {
            task["input_path"] == "report.pdf"
                && task["fallback_reason"] == "online_adapter_done"
                && task["status"] == "done"
                && task["changed_unit_keys"]
                    .as_array()
                    .is_some_and(|keys| keys.is_empty())
        }),
        "the 0-change task completes done with no changed units: {status}"
    );

    // Every unit of the current (v2) online instance was reused from the prior instance
    // (reused_from set) — no page was freshly OCR'd.
    let v2_hash = hash_bytes(v2.as_bytes());
    let reused: Vec<_> = normalized_units(&dir)
        .into_iter()
        .filter(|unit| unit.raw_hash == v2_hash && unit.markdown.contains("mock ocr"))
        .collect();
    assert!(
        !reused.is_empty(),
        "the v2 instance must have reused units carrying the prior markdown"
    );
    assert!(
        reused.iter().all(|unit| unit.reused_from.is_some()),
        "every v2 unit must be reused_from the prior instance (no fresh OCR)"
    );
}

// R14-3: R13-4's HEAD self-heal runs on the common `Repository::open` path and used to
// unconditionally take the store lock and overwrite HEAD. On a read-only `.kcs` (archive
// / forensic mount) with a corrupt (empty) HEAD, the `.lock` create failed with
// PermissionDenied and bricked even pure-read commands (KCS-E-STORE-IO-001). The fix
// makes the repair best-effort (defer on a read-only/contended lock) while still healing
// a writable scope and recording the repair.

fn errors_log(dir: &TempDir) -> String {
    let path = dir.path().join(".test-data/kcs/logs/errors.jsonl");
    fs::read_to_string(path).unwrap_or_default()
}

// (a): corrupt HEAD + read-only `.kcs` → pure-read commands still run (exit 0), the heal
// is deferred (not performed, not silent), and a later WRITABLE open completes it.
#[cfg(unix)]
#[test]
fn r14_3_corrupt_head_read_only_scope_reads_run_and_defer_heal() {
    use std::os::unix::fs::PermissionsExt;
    let dir = scope();
    fs::write(dir.path().join("doc.txt"), "v1").unwrap();
    let c1 = json_success(&dir, ["snapshot", "-m", "first"]);
    let c1_hash = c1["commit_hash"].as_str().unwrap().to_owned();

    // Corrupt HEAD to empty (refs still names C1), then make `.kcs` read-only so the
    // self-heal can neither create `.lock` nor overwrite HEAD.
    fs::write(dir.path().join(".kcs/HEAD"), "").unwrap();
    let kcs_dir = dir.path().join(".kcs");
    fs::set_permissions(&kcs_dir, fs::Permissions::from_mode(0o500)).unwrap();

    // Pure-read commands must succeed (exit 0). Before R14-3 the self-heal's `.lock`
    // create failed with PermissionDenied → KCS-E-STORE-IO-001, exit 1.
    let status = json_success(&dir, ["status"]);
    assert!(status.is_object(), "status must run read-only: {status}");
    // R15-1b: even though the physical HEAD file stays empty while the heal is
    // deferred, `head_commit_hash` now recovers the real commit from `refs/heads/main`
    // (side-effect-free), so `log` returns the true history (C1) instead of the former
    // misreport of an empty commit list on an indexed scope.
    let log = json_success(&dir, ["log"]);
    let commits = log["commits"].as_array().expect("log commits array");
    assert_eq!(
        commits.len(),
        1,
        "log must recover the real commit from refs even while HEAD is unhealed: {log}"
    );
    assert_eq!(commits[0]["commit_hash"], c1_hash);
    // `inspect <hash>` resolves the object directly (not via HEAD), so it still returns
    // the commit object — proving the open path itself no longer bricks.
    let inspect = json_success(&dir, ["inspect", &c1_hash]);
    assert!(
        inspect.is_object(),
        "inspect must resolve the commit read-only: {inspect}"
    );

    // The heal was deferred (best-effort warn), not silently performed: HEAD is still
    // empty and no repair event was written.
    assert!(
        fs::read_to_string(dir.path().join(".kcs/HEAD"))
            .unwrap()
            .trim()
            .is_empty(),
        "a read-only scope's HEAD stays unhealed (deferred)"
    );
    assert!(
        !events_log(&dir).contains("KCS-I-STORE-HEAD-REPAIRED-001"),
        "no repair may be claimed while the scope is read-only"
    );
    assert!(
        errors_log(&dir).contains("KCS-W-STORE-HEAD-HEAL-DEFERRED-001"),
        "the deferred heal must be observable as a warn"
    );

    // A later WRITABLE open completes the heal (never lost): HEAD is restored and the
    // repair is now recorded.
    fs::set_permissions(&kcs_dir, fs::Permissions::from_mode(0o700)).unwrap();
    json_success(&dir, ["log"]);
    assert_eq!(
        fs::read_to_string(dir.path().join(".kcs/HEAD"))
            .unwrap()
            .trim(),
        c1_hash,
        "a writable open must complete the deferred heal"
    );
    assert!(
        events_log(&dir).contains("KCS-I-STORE-HEAD-REPAIRED-001"),
        "the completed repair must be recorded (never silent)"
    );
}

// (c): a HEALTHY HEAD + read-only `.kcs` is unchanged — reads run and nothing is healed
// (the fast path never touches the lock).
#[cfg(unix)]
#[test]
fn r14_3_healthy_head_read_only_scope_unchanged() {
    use std::os::unix::fs::PermissionsExt;
    let dir = scope();
    fs::write(dir.path().join("doc.txt"), "v1").unwrap();
    let c1 = json_success(&dir, ["snapshot", "-m", "first"]);
    let c1_hash = c1["commit_hash"].as_str().unwrap().to_owned();

    let kcs_dir = dir.path().join(".kcs");
    fs::set_permissions(&kcs_dir, fs::Permissions::from_mode(0o500)).unwrap();

    let status = json_success(&dir, ["status"]);
    assert!(
        status.is_object(),
        "healthy read-only status runs: {status}"
    );
    let log = json_success(&dir, ["log"]);
    assert!(
        log["commits"]
            .as_array()
            .unwrap()
            .iter()
            .any(|commit| commit["commit_hash"] == c1_hash),
        "healthy read-only log runs: {log}"
    );
    assert!(
        !events_log(&dir).contains("KCS-I-STORE-HEAD-REPAIRED-001")
            && !errors_log(&dir).contains("KCS-W-STORE-HEAD-HEAL-DEFERRED-001"),
        "a healthy HEAD triggers neither a repair nor a deferred-heal warn"
    );

    fs::set_permissions(&kcs_dir, fs::Permissions::from_mode(0o700)).unwrap();
}

// R15-4: a HEAD commit whose TREE object is gone (shallow: GC'd / manually deleted /
// corrupt CAS) must NOT brick the scope. `status` is a pure read → it degrades
// (head_shallow, no per-file classification) and exits 0. Writes that need the prior
// tree — `index` / `snapshot` / `reindex` — fail with a clear KCS-E-COMMIT-SHALLOW-001
// (recovery guidance) instead of a raw KCS-E-STORE-NOT-FOUND-001 whose hash is opaque.
#[test]
fn r15_4_shallow_head_degrades_reads_and_rejects_writes() {
    let dir = scope();
    fs::write(dir.path().join("doc.md"), "# Doc\n\nbody one\n").unwrap();
    json_success(&dir, ["index", "--yes"]);

    // Delete the HEAD commit's tree object(s), leaving the commit reachable — exactly
    // the shallow state (05 §2.2: tree discarded, commit retained).
    let trees_dir = dir.path().join(".kcs/objects/trees");
    fs::remove_dir_all(&trees_dir).unwrap();

    // (a) `status` degrades: exit 0, head_shallow = true, files listed WITHOUT a
    // tree-derived classification (the prior tree needed to classify is gone).
    let status = json_success(&dir, ["status"]);
    assert_eq!(
        status["head_shallow"], true,
        "status must flag the shallow HEAD: {status}"
    );
    let files = status["files"].as_array().unwrap();
    assert!(
        !files.is_empty(),
        "status still lists the working files: {status}"
    );
    assert!(
        files.iter().all(|file| file.get("status").is_none()),
        "a shallow HEAD omits the per-file classification: {status}"
    );

    // Edit the file so `index` has a change to snapshot (its no-change short-circuit
    // uses the sqlite cache, not the tree object; snapshot/reindex read the tree
    // unconditionally). The write must then extend the shallow HEAD → rejected.
    fs::write(dir.path().join("doc.md"), "# Doc\n\nbody two\n").unwrap();

    // (b) `index` / `snapshot` reject the shallow commit with the clear error code,
    // not a raw KCS-E-STORE-NOT-FOUND-001.
    let index_err = json_failure(&dir, ["index", "--yes"], 1);
    assert_eq!(
        index_err["error_code"], "KCS-E-COMMIT-SHALLOW-001",
        "{index_err}"
    );
    let snap_err = json_failure(&dir, ["snapshot", "-m", "x"], 1);
    assert_eq!(
        snap_err["error_code"], "KCS-E-COMMIT-SHALLOW-001",
        "{snap_err}"
    );

    // (c) `reindex --force --yes` likewise fails with the shallow error.
    let reindex_err = json_failure(&dir, ["reindex", "--force", "--yes"], 1);
    assert_eq!(
        reindex_err["error_code"], "KCS-E-COMMIT-SHALLOW-001",
        "{reindex_err}"
    );

    // (control) `log` stays healthy — it traverses commits, not trees.
    let log = json_success(&dir, ["log"]);
    assert_eq!(
        log["commits"].as_array().unwrap().len(),
        1,
        "log still reads the (tree-less) commit: {log}"
    );
}

// R14-5: `batch resume`/`retry` exit 3 (partial) / 4 (permanent) previously logged a
// SEARCH error_code to errors.jsonl (`KCS-E-SEARCH-PARTIAL-001` — not even catalogued —
// and `KCS-E-SEARCH-SCOPE-ALL-FAILED-001`, the multi-scope-search all-failed code),
// mis-classifying a batch task failure as a search failure. The fix gives batch its own
// error_code, like `index` self-sets `KCS-E-INDEX-PARTIAL-001`.

// Exit 4 (all-permanent): a superseded stale online task (non-retryable InvalidInput).
#[test]
fn r14_5_batch_permanent_failure_logs_batch_error_code() {
    let dir = scope();
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["p1", "p2"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    // Edit without re-indexing → the online task is stale (permanent failure) → exit 4.
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2 changed"]),
    )
    .unwrap();
    json_code_stdout_with_env(
        &dir,
        ["batch", "resume"],
        4,
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    let errors = errors_log(&dir);
    assert!(
        errors.contains("KCS-E-BATCH-TASK-FAILED-001"),
        "the exit-4 batch failure must log a batch-owned error_code: {errors}"
    );
    assert!(
        !errors.contains("KCS-E-SEARCH-SCOPE-ALL-FAILED-001"),
        "batch must not borrow the multi-scope-search all-failed code: {errors}"
    );
}

// Exit 3 (some retryable): a rate-limited online task (retryable) with the file
// unchanged (so it passes the staleness guard and actually reaches the adapter).
#[test]
fn r14_5_batch_partial_failure_logs_batch_error_code() {
    let dir = scope();
    fs::write(dir.path().join("report.pdf"), fake_pdf(&["p1", "p2"])).unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_code_stdout_with_env(
        &dir,
        ["batch", "resume"],
        3,
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "rate_limit")],
    );

    let errors = errors_log(&dir);
    assert!(
        errors.contains("KCS-E-BATCH-PARTIAL-001"),
        "the exit-3 batch failure must log a batch-owned error_code: {errors}"
    );
    assert!(
        !errors.contains("KCS-E-SEARCH-PARTIAL-001"),
        "batch must not borrow the search partial code: {errors}"
    );
}

// R14-6: the incremental `tool_profile_hash` mismatch check used to run AFTER the OCR
// send, so a model-pin change wasted an incremental send (and, with R14-4, a whole-doc
// upload) before falling back to Full. The gate now runs BEFORE the send. The
// `pin_changed` mock seam resolves a different pin AND errors on any incremental send, so
// the task can only complete if the gate fires before sending.
#[test]
fn r14_6_pin_change_gates_incremental_before_send() {
    let dir = scope();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2", "p3", "p4", "p5"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--approve"]);
    // v1 online instance under the default pin (mistral-ocr-2505).
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")],
    );

    // v2 light revision (change_rate 1/5 < 0.30 → would be incremental if the pin held).
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["p1", "p2 changed", "p3", "p4", "p5"]),
    )
    .unwrap();
    json_success(&dir, ["index", "--yes"]);

    // pin_changed: the resolved profile differs from the v1 instance, so the gate must
    // fire BEFORE any send. If an incremental send is attempted (the old post-send order),
    // the mock errors and the task fails — `json_success_with_env` asserts exit 0.
    let resume = json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "pin_changed")],
    );
    assert_eq!(
        resume["tasks_failed"], 0,
        "a pin change must gate incremental before sending (no failing wasted send): {resume}"
    );
    assert!(
        resume["tasks_executed"].as_u64().unwrap() >= 1,
        "the v2 task completes via a single Full send: {resume}"
    );

    // The v2 task is a Full send (not incremental) under the new pin.
    let status = json_success(&dir, ["status"]);
    assert!(
        online_incremental_task(&status).is_none(),
        "a pin change must NOT produce an incremental task: {status}"
    );
    let done = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| {
            task["input_path"] == "report.pdf"
                && task["fallback_reason"] == "online_adapter_done"
                && task["status"] == "done"
        })
        .count();
    assert!(
        done >= 2,
        "v1 + v2 online tasks both done (v2 via Full after the gate): {status}"
    );
}
