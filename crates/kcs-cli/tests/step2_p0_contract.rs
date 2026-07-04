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
    let mut command = Command::cargo_bin("kcs").unwrap();
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

fn json_failure_with_env<const N: usize>(
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
        .stderr
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
        PathBuf::from(".kcs/objects/normalized_units/bb/e1/sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59.sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed.g0")
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
    let error = json_failure_with_env(
        &dir,
        ["index", "--yes"],
        3,
        &[(
            "KCS_TEST_MARKDOWNIZE_ADAPTER",
            "reject_incremental_and_full",
        )],
    );
    assert_eq!(error["error_code"], "KCS-E-INDEX-PARTIAL-001");
    assert_eq!(error["context"]["output"]["failed_files"], 1);
    assert!(
        error["context"]["output"]["normalized_files"]
            .as_u64()
            .unwrap()
            > 0
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
    fs::write(dir.path().join("a.txt"), "hello budget").unwrap();
    let output = json_success(&dir, ["index", "--approve"]);
    assert!(output["paused_tasks"].as_u64().unwrap() > 0);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "a.txt"
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
    fs::write(dir.path().join("api_token.txt"), "not actually secret").unwrap();
    let preview = json_success(&dir, ["index", "--preview"]);
    // Still ingested (not hard-excluded like Tier A), but flagged sensitive.
    assert!(!preview["excluded_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|v| v == "api_token.txt"));
    assert!(preview["sensitive_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|c| c["path"] == "api_token.txt" && c["reason"] == "secrets_tier_b_warning"));
    json_success(&dir, ["index", "--yes"]);
    let status = json_success(&dir, ["status"]);
    // The online task is held, not sendable.
    assert!(
        status["tasks"].as_array().unwrap().iter().any(|task| {
            task["input_path"] == "api_token.txt"
                && task["status"] == "paused"
                && task["fallback_reason"] == "secrets_tier_b_hold"
        }),
        "Tier B online task must be held (secrets_tier_b_hold): {status}"
    );
    assert!(
        !status["tasks"].as_array().unwrap().iter().any(|task| {
            task["input_path"] == "api_token.txt"
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
            .any(|q| q["path"] == "api_token.txt" && q["reason"] == "secrets_tier_b"),
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
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    assert_eq!(output["network_opt_in"], false);
    assert!(output["pending_online_tasks"].as_u64().unwrap() > 0);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "a.txt"
            && task["status"] == "pending"
            && task["fallback_reason"] == "network_opt_in_required"
    }));
}

#[test]
fn ct2_network_002_approve_grants_opt_in_yes_does_not() {
    let yes_dir = scope();
    fs::write(yes_dir.path().join("a.txt"), "hello").unwrap();
    assert_eq!(
        json_success(&yes_dir, ["index", "--yes"])["network_opt_in"],
        false
    );

    let approve_dir = scope();
    fs::write(approve_dir.path().join("a.txt"), "hello").unwrap();
    assert_eq!(
        json_success(&approve_dir, ["index", "--approve"])["network_opt_in"],
        true
    );

    let online_dir = scope();
    fs::write(online_dir.path().join("a.txt"), "hello").unwrap();
    let error = json_failure(&online_dir, ["index", "--online"], 2);
    assert_eq!(error["error_code"], "KCS-E-CONFIG-USAGE-001");
    assert_eq!(
        json_success(&online_dir, ["index", "--yes", "--online"])["network_opt_in"],
        false
    );
    assert!(json_success(&online_dir, ["status"])["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .any(|task| task["fallback_reason"] == "ready_for_online_adapter"));
    let approvals = fs::read_to_string(online_dir.path().join(".kcs/approvals.jsonl")).unwrap();
    assert!(approvals.contains(r#""network_opt_in":false"#));
}

#[test]
fn ct2_network_004_config_allow_network_enables_online() {
    let dir = scope();
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "[adapter.policy]\nallow_network = true\n",
    )
    .unwrap();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    assert_eq!(output["network_allowed"], true);
    assert_eq!(output["network_opt_in"], true);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "a.txt"
            && task["status"] == "pending"
            && task["fallback_reason"] == "ready_for_online_adapter"
    }));
}

#[test]
fn ct2_network_003_revoke_blocks_online_one_shot() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success(&dir, ["index", "--revoke-network"]);
    fs::write(dir.path().join("b.txt"), "new after revoke").unwrap();
    let output = json_success(&dir, ["index", "--yes", "--online"]);
    assert_eq!(output["network_opt_in"], false);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "b.txt"
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
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
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
    fs::write(dir.path().join("a.txt"), "hello online cost").unwrap();
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
    fs::write(dir.path().join("b.txt"), "second online cost").unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    assert!(output["paused_tasks"].as_u64().unwrap() > 0);
    let status = json_success(&dir, ["status"]);
    assert!(status["tasks"].as_array().unwrap().iter().any(|task| {
        task["input_path"] == "b.txt"
            && task["status"] == "paused"
            && task["fallback_reason"] == "budget_exceeded"
    }));
    assert!(status["budget"]["cap_kind"].as_str().is_some());
    assert_eq!(status["budget"]["folder_per_adapter"]["markdown"], 0.0);
}

#[test]
fn ct2_image_003_cli_mock_preserves_links_when_replacing_images() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello image link").unwrap();
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
    fs::write(dir.path().join("a.txt"), "hello auth").unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
        &[(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "auth_error")],
    );
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
    fs::write(dir.path().join("a.txt"), "hello dedup").unwrap();
    json_success(&dir, ["index", "--approve"]);
    json_success_with_env(
        &dir,
        ["batch", "resume"],
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

#[test]
fn ct2_task_007_online_task_not_reissued_for_completed_identity() {
    // Step2c I1: once an online task for an identity is Done, re-indexing the
    // unchanged file must not enqueue a duplicate task. The bug was a later
    // `batch resume` re-sending that duplicate and double-charging the ledger.
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello dedup").unwrap();
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
    fs::write(dir.path().join("a.txt"), "hello dedup changed content").unwrap();
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
    fs::write(dir.path().join("a.txt"), "hello retry backoff").unwrap();
    json_success(&dir, ["index", "--approve"]);

    // Fail the online task with a rate-limit-like (retryable) error at T0.
    kcs(&dir, ["batch", "resume"])
        .env(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "rate_limit")
        .env("KCS_FIXED_NOW", "2026-07-03T00:00:00Z")
        .assert()
        .success();
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
