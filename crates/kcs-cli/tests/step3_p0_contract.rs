use std::fs;
use std::path::Path;

use assert_cmd::Command;
use serde_json::Value;
use tempfile::TempDir;

fn kcs(dir: &TempDir, args: &[&str]) -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    command
        .current_dir(dir.path())
        .env("XDG_CONFIG_HOME", dir.path().join(".test-config"))
        .env("XDG_DATA_HOME", dir.path().join(".test-data"))
        .args(args);
    command
}

fn json_success(dir: &TempDir, args: &[&str]) -> Value {
    let output = kcs(dir, args)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_failure(dir: &TempDir, args: &[&str], code: i32) -> Value {
    let output = kcs(dir, args)
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stderr
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_success_path(path: &Path, data_home: &Path, args: &[&str]) -> Value {
    let output = Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(path)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .args(args)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn indexed_scope() -> TempDir {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("auth.md"),
        "# 認証仕様\n\n## API Token\nトークン TTL は 3600 秒です。\n\n## Scopes\nスコープは read write admin です。\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("ranking.md"),
        "# 検索ランキング\n\n## RRF 融合\nRRF の定数 k=60 を使います。\n\n## MMR 多様化\nMMR の係数 lambda 0.7 で多様化します。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);
    dir
}

fn first_result(search: &Value) -> &Value {
    &search["results"].as_array().unwrap()[0]
}

#[test]
fn ct3_hybrid_002_auto_vector_unavailable_falls_back_visibly() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    assert_eq!(search["requested_mode"], "auto");
    assert_eq!(search["resolved_mode"], "text");
    assert_eq!(search["fallback"], true);
    assert_eq!(search["error_code"], "KCS-E-SEARCH-VEC-UNAVAIL-001");
}

#[test]
fn ct3_hybrid_006_text_mode_uses_text_rank_without_fusion() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "RRF k 60", "--text"]);
    assert_eq!(search["requested_mode"], "text");
    assert_eq!(search["resolved_mode"], "text");
    assert_eq!(search["fallback"], false);
    assert_eq!(
        first_result(&search)["evidence_pointer"]["section_id"],
        "検索ランキング/rrf-融合"
    );
}

#[test]
fn ct3_embed_002_vector_only_without_index_is_an_error() {
    let dir = indexed_scope();
    let err = json_failure(&dir, &["search", "トークン", "--vector"], 1);
    assert_eq!(err["error_code"], "KCS-E-SEARCH-VEC-UNAVAIL-001");
}

#[test]
fn ct3_evidence_001_search_results_include_pointer_and_uri() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let result = first_result(&search);
    let pointer = &result["evidence_pointer"];
    assert!(pointer["commit"].as_str().unwrap().starts_with("sha256:"));
    assert!(pointer["raw_hash"].as_str().unwrap().starts_with("sha256:"));
    assert!(pointer["chunk_hash"]
        .as_str()
        .unwrap()
        .starts_with("sha256:"));
    assert_eq!(pointer["heading_path"][1], "API Token");
    assert!(result["evidence_uri"]
        .as_str()
        .unwrap()
        .starts_with("kcs://"));
}

#[test]
fn ct3_evidence_002_live_pointer_commit_matches_searched_scope_snapshot() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let snapshot = search["searched_scopes"][0]["snapshot_at"]
        .as_str()
        .unwrap();
    assert_eq!(
        first_result(&search)["evidence_pointer"]["commit"]
            .as_str()
            .unwrap(),
        snapshot
    );
}

#[test]
fn ct3_evidence_009_eval_reads_raw_hash_and_section_from_pointer() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let pointer = &first_result(&search)["evidence_pointer"];
    assert!(pointer["raw_hash"].as_str().unwrap().starts_with("sha256:"));
    assert_eq!(pointer["section_id"], "認証仕様/api-token");
}

#[test]
fn ct3_open_001_open_prefers_working_tree_raw_hash() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"].as_str().unwrap();
    let opened = json_success(&dir, &["open", uri]);
    assert_eq!(opened["status"], "opened");
    assert_eq!(opened["temporary"], false);
    assert!(opened["path"].as_str().unwrap().ends_with("auth.md"));
}

#[test]
fn ct3_open_004_view_returns_chunk_text_without_regeneration() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"].as_str().unwrap();
    let viewed = json_success(&dir, &["view", uri]);
    assert!(viewed["text"].as_str().unwrap().contains("トークン TTL"));
}

#[test]
fn ct3_open_003_dead_pointer_returns_exit_4() {
    let dir = indexed_scope();
    let bad = "kcs://missing/sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc/sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd";
    let err = json_failure(&dir, &["open", bad], 4);
    assert_eq!(err["error_code"], "KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001");
}

#[test]
fn ct3_cursor_001_same_cursor_recomputes_same_second_page() {
    let dir = indexed_scope();
    let first = json_success(&dir, &["search", "検索", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap();
    let second_a = json_success(
        &dir,
        &["search", "検索", "--cursor", cursor, "--limit", "1"],
    );
    let second_b = json_success(
        &dir,
        &["search", "検索", "--cursor", cursor, "--limit", "1"],
    );
    assert_eq!(second_a["results"], second_b["results"]);
}

#[test]
fn ct3_cursor_003_mismatched_cursor_is_rejected() {
    let dir = indexed_scope();
    let first = json_success(&dir, &["search", "検索", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap();
    let err = json_failure(
        &dir,
        &["search", "別クエリ", "--cursor", cursor, "--limit", "1"],
        2,
    );
    assert_eq!(err["error_code"], "KCS-E-SEARCH-CURSOR-001");
}

#[test]
fn ct3_multi_004_single_scope_response_lists_searched_scopes() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン"]);
    assert_eq!(search["searched_scopes"].as_array().unwrap().len(), 1);
    assert!(search["excluded_scopes"].as_array().unwrap().is_empty());
}

#[test]
fn ct3_obs_002_metrics_jsonl_records_per_search_latency() {
    let dir = indexed_scope();
    json_success(&dir, &["search", "トークン"]);
    let metrics = fs::read_to_string(dir.path().join(".test-data/kcs/logs/metrics.jsonl")).unwrap();
    let last: Value = serde_json::from_str(metrics.lines().last().unwrap()).unwrap();
    assert_eq!(last["metric"], "search.latency_ms");
    assert_eq!(last["context"]["mode"], "text");
}

#[test]
fn ct3_obs_003_access_jsonl_records_redacted_search() {
    let dir = indexed_scope();
    json_success(&dir, &["search", "トークン"]);
    let access = fs::read_to_string(dir.path().join(".kcs/logs/access.jsonl")).unwrap();
    let last: Value = serde_json::from_str(access.lines().last().unwrap()).unwrap();
    assert_eq!(last["context"]["query"], "[redacted]");
}

#[test]
fn ct3_reindex_003_force_requires_yes_in_noninteractive_mode() {
    let dir = indexed_scope();
    let err = json_failure(&dir, &["reindex", "--force"], 9);
    assert_eq!(err["error_code"], "KCS-E-CONFIRM-REJECTED-001");
}

#[test]
fn ct3_reindex_001_force_creates_new_generation_and_preserves_old_chunks() {
    let dir = indexed_scope();
    let before = line_count(dir.path().join(".kcs/index/chunks.jsonl"));
    let out = json_success(&dir, &["reindex", "--force", "--yes"]);
    assert_eq!(out["status"], "reindexed");
    let after = line_count(dir.path().join(".kcs/index/chunks.jsonl"));
    assert!(after > before);
}

#[test]
fn ct3_chunk_008_deleted_file_does_not_remove_existing_chunk_rows() {
    let dir = indexed_scope();
    let before = line_count(dir.path().join(".kcs/index/chunks.jsonl"));
    fs::remove_file(dir.path().join("auth.md")).unwrap();
    json_success(&dir, &["index", "--approve"]);
    let after = line_count(dir.path().join(".kcs/index/chunks.jsonl"));
    assert!(after >= before);
}

#[test]
fn ct3_chunk_009_chunks_have_first_seen_commit_after_index() {
    let dir = indexed_scope();
    let text = fs::read_to_string(dir.path().join(".kcs/index/chunks.jsonl")).unwrap();
    let row: Value = serde_json::from_str(text.lines().next().unwrap()).unwrap();
    assert!(row["first_seen_commit"]
        .as_str()
        .unwrap()
        .starts_with("sha256:"));
}

#[test]
fn ct3_chunk_012_repair_rebuild_db_preserves_search_result() {
    let dir = indexed_scope();
    let before = json_success(&dir, &["search", "トークン TTL 3600"]);
    fs::remove_file(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    json_success(&dir, &["repair", "--rebuild-db"]);
    let after = json_success(&dir, &["search", "トークン TTL 3600"]);
    assert_eq!(
        first_result(&before)["evidence_uri"],
        first_result(&after)["evidence_uri"]
    );
    assert!(dir.path().join(".kcs/index/sqlite.db").is_file());
}

#[test]
fn ct3_uri_003_inline_json_pointer_is_accepted_by_view() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let pointer = first_result(&search)["evidence_pointer"].to_string();
    let viewed = json_success(&dir, &["view", &pointer]);
    assert!(viewed["text"].as_str().unwrap().contains("3600"));
}

#[test]
fn ct3_open_002_missing_working_tree_file_expands_temporary_copy() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"].as_str().unwrap();
    fs::remove_file(dir.path().join("auth.md")).unwrap();
    let opened = json_success(&dir, &["open", uri]);
    assert_eq!(opened["temporary"], true);
    assert!(Path::new(opened["path"].as_str().unwrap()).is_file());
}

#[test]
fn ct3_reindex_002_existing_pointer_still_resolves_old_chunk_after_reindex() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"]
        .as_str()
        .unwrap()
        .to_owned();
    json_success(&dir, &["reindex", "--force", "--yes"]);
    let viewed = json_success(&dir, &["view", &uri]);
    assert!(viewed["text"].as_str().unwrap().contains("トークン TTL"));
}

#[test]
fn ct3_chunk_007_chunking_config_change_appends_new_generation_chunks() {
    let dir = indexed_scope();
    let before = line_count(dir.path().join(".kcs/index/chunks.jsonl"));
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[chunking]\nstrategy = \"heading\"\nmax_chars = 25\n",
    )
    .unwrap();
    json_success(&dir, &["index", "--approve"]);
    let after = line_count(dir.path().join(".kcs/index/chunks.jsonl"));
    assert!(after > before);
}

#[test]
fn ct3_cursor_006_offset_matches_cursor_page() {
    let dir = indexed_scope();
    let first = json_success(&dir, &["search", "検索", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap();
    let by_cursor = json_success(
        &dir,
        &["search", "検索", "--cursor", cursor, "--limit", "1"],
    );
    let by_offset = json_success(&dir, &["search", "検索", "--offset", "1", "--limit", "1"]);
    assert_eq!(by_cursor["results"], by_offset["results"]);
}

#[test]
fn ct3_cursor_001_end_of_stream_has_null_next_cursor() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "検索", "--limit", "100"]);
    assert!(search["paging"]["next_cursor"].is_null());
}

#[test]
fn ct3_fts_003_two_character_query_is_skipped_with_zero_results() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "認"]);
    assert!(search["results"].as_array().unwrap().is_empty());
}

#[test]
fn ct3_multi_001_and_008_all_scopes_discovers_sibling_indexed_scopes() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## Local\nalpha only\n").unwrap();
    fs::write(
        b.join("b.md"),
        "# B\n\n## Remote\nunique sibling token 4242\n",
    )
    .unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);
    let search = json_success_path(
        &a,
        &data_home,
        &["search", "unique sibling 4242", "--all-scopes"],
    );
    assert!(first_result(&search)["scope_path"]
        .as_str()
        .unwrap()
        .ends_with("/b"));
    assert_eq!(search["searched_scopes"].as_array().unwrap().len(), 2);
}

#[test]
fn ct3_embed_003_all_scope_vector_incompatibility_falls_back_to_text_merge() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## One\nalpha 111\n").unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Two\nbeta 222\n").unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);
    let search = json_success_path(&a, &data_home, &["search", "beta 222", "--all-scopes"]);
    assert_eq!(search["resolved_mode"], "text");
    assert_eq!(search["fallback"], true);
}

#[test]
fn ct3_obs_002_metrics_do_not_record_query_text() {
    let dir = indexed_scope();
    json_success(&dir, &["search", "secret query phrase 3600"]);
    let metrics = fs::read_to_string(dir.path().join(".test-data/kcs/logs/metrics.jsonl")).unwrap();
    assert!(!metrics.contains("secret query phrase"));
}

#[test]
fn ct3_obs_003_access_log_has_required_envelope_fields() {
    let dir = indexed_scope();
    json_success(&dir, &["search", "トークン"]);
    let access = fs::read_to_string(dir.path().join(".kcs/logs/access.jsonl")).unwrap();
    let last: Value = serde_json::from_str(access.lines().last().unwrap()).unwrap();
    for key in ["ts", "level", "code", "component", "message", "context"] {
        assert!(last.get(key).is_some(), "missing {key}");
    }
}

fn line_count(path: impl AsRef<Path>) -> usize {
    fs::read_to_string(path).unwrap().lines().count()
}
