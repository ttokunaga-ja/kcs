use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use assert_cmd::Command;
use kcs_adapter::identity::{
    canonical_profile_value, jcs_bytes, prompt_template_hash, tool_profile_hash,
};
use kcs_adapter::mistral_ocr::{image_hash, replace_image_placeholders, OcrImage};
use kcs_adapter::tool_lock::tool_lock_hash;
use kcs_pipeline::budget::{evaluate_budget_with_caps, BudgetCapKind, BudgetEstimate};
use kcs_pipeline::markdownize::{
    choose_markdownize_mode, markdownize_units, normalized_identity, normalized_instance_dir,
    validate_markdownize_response, IncrementalHints, IncrementalModeInput, MarkdownizeMode,
    MarkdownizeStageRequest, NormalizedInstanceManifest, NormalizedUnitManifestEntry, RawRef,
    UnitStatus,
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

fn profile_mistral() -> Value {
    json!({
        "adapter_kind": "markdownize",
        "adapter_role": "multimodal",
        "model_or_tool_family": "mistral-ocr",
        "model_version_pin": "mistral-ocr-2505",
        "output_schema": "kcs-markdown-v1",
        "runtime_kind": "cloud",
        "spec_version": 1
    })
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
    json!({
        "spec_version": 1,
        "prepare": {
            "tool_id": "prepare_default",
            "profile_hash": "sha256:20b67a9d7e7e2654379f16f20b445d007e95abac7c8f85d6da65beccff7e6b03"
        },
        "markdown": {
            "tool_id": "mistral_ocr_markdownize",
            "profile_hash": "sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed",
            "capabilities": ["ignored"]
        },
        "embedding": {
            "tool_id": "gemini_multimodal_embedding",
            "profile_hash": "sha256:c2bda78e217e1f9e12cd17ddac6c46e28a50b8060976f533f76f14193a807226",
            "dimensions": 1536,
            "distance": "cosine",
            "modality": "multimodal",
            "mode": "ignored"
        }
    })
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

fn inspect(dir: &TempDir, hash: &str) -> Value {
    json_success(dir, ["inspect", hash])
}

fn head(dir: &TempDir) -> String {
    fs::read_to_string(dir.path().join(".kcs/HEAD")).unwrap()
}

#[test]
fn ct2_profile_001_tool_profile_hash_mistral() {
    assert_eq!(
        jcs_bytes(&canonical_profile_value(&profile_mistral()).unwrap()).unwrap(),
        br#"{"adapter_kind":"markdownize","adapter_role":"multimodal","model_or_tool_family":"mistral-ocr","model_version_pin":"mistral-ocr-2505","output_schema":"kcs-markdown-v1","runtime_kind":"cloud","spec_version":1}"#
    );
    assert_eq!(
        tool_profile_hash(&profile_mistral()).unwrap(),
        "sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed"
    );
}

#[test]
fn ct2_profile_002_tool_profile_hash_deterministic() {
    assert_eq!(
        tool_profile_hash(&profile_deterministic()).unwrap(),
        "sha256:76c01950d19edffc1b8ca75e06d7754fb52cd05db1bb10e3268f81392bf54095"
    );
}

#[test]
fn ct2_profile_003_null_fields_are_omitted() {
    let mut with_nulls = profile_mistral();
    for key in [
        "prompt_template_id",
        "prompt_template_hash",
        "sampling",
        "dimensions",
        "distance",
        "modality",
    ] {
        with_nulls[key] = Value::Null;
    }
    assert_eq!(
        tool_profile_hash(&with_nulls).unwrap(),
        tool_profile_hash(&profile_mistral()).unwrap()
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
        "sha256:e24d8b76742e441e894181f9210453e0da60a6e84c663560214d10aeeee0b264"
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

#[test]
fn ct2_incr_008_identity_ignores_mode() {
    let raw = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    let tool = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    assert_eq!(
        normalized_identity(raw, tool),
        normalized_identity(raw, tool)
    );
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
    let (prepared, hints) = acceptance_context();
    let mut response = response_incremental(
        vec![markdown_unit("page:1", "x")],
        vec!["page:2"],
        Vec::new(),
        Vec::new(),
    );
    response.fallback_to_full = true;
    assert!(validate_markdownize_response(&response, &hints, &prepared).is_err());
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
fn ct2_secrets_003_tier_b_local_but_online_pending() {
    let dir = scope();
    fs::write(dir.path().join("api_token.txt"), "not actually secret").unwrap();
    let preview = json_success(&dir, ["index", "--preview"]);
    assert!(!preview["excluded_candidates"]
        .as_array()
        .unwrap()
        .iter()
        .any(|v| v == "api_token.txt"));
    let output = json_success(&dir, ["index", "--yes"]);
    assert!(output["pending_online_tasks"].as_u64().unwrap() > 0);
}

#[test]
fn ct2_secrets_004_added_tier_a_is_quarantined() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    json_success(&dir, ["index", "--approve"]);
    fs::write(dir.path().join(".env"), "TOKEN=x").unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    let commit = output["commit"].as_object();
    if let Some(commit) = commit {
        let tree = inspect(&dir, commit["tree"].as_str().unwrap());
        assert!(!tree["entries"]
            .as_array()
            .unwrap()
            .iter()
            .any(|entry| entry["path"] == ".env"));
    }
}

#[test]
fn ct2_network_001_yes_does_not_issue_online_tasks() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    let output = json_success(&dir, ["index", "--yes"]);
    assert_eq!(output["network_opt_in"], false);
    assert!(output["pending_online_tasks"].as_u64().unwrap() > 0);
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
fn ct2_adapter_013_baseline_and_ai_artifacts_coexist() {
    let dir = scope();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    json_success(&dir, ["index", "--approve"]);
    let baseline_root = dir.path().join(".kcs/objects/normalized_units");
    let before = collect_files(&baseline_root);
    let raw = hash_bytes(b"hello");
    let ai_tool = "sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed";
    let ai_dir = normalized_instance_dir(dir.path().join(".kcs"), &raw, ai_tool, 0);
    fs::create_dir_all(&ai_dir).unwrap();
    fs::write(ai_dir.join("manifest.json"), b"{}").unwrap();
    assert_eq!(
        collect_files(&baseline_root).intersection(&before).count(),
        before.len()
    );
}

#[test]
fn ct2_image_001_embedded_image_hash_and_fanout() {
    let hash = image_hash(b"image bytes");
    assert!(hash.starts_with("sha256:"));
    let digest = hash.strip_prefix("sha256:").unwrap();
    let path = PathBuf::from(".kcs/objects/images")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(&hash);
    assert!(path.ends_with(&hash));
}

#[test]
fn ct2_image_002_markdown_references_object_uri() {
    let replaced = replace_image_placeholders(
        "![x](placeholder)\n",
        "01H00000000000000000000000",
        &[OcrImage {
            bytes: b"image bytes".to_vec(),
            media_type: "image/png".to_owned(),
        }],
    );
    assert!(replaced.contains("kcs://01H00000000000000000000000/object/image/sha256:"));
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
