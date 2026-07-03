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
    let first = json_success(&dir, &["search", "認証仕様", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap();
    let second_a = json_success(
        &dir,
        &["search", "認証仕様", "--cursor", cursor, "--limit", "1"],
    );
    let second_b = json_success(
        &dir,
        &["search", "認証仕様", "--cursor", cursor, "--limit", "1"],
    );
    assert_eq!(second_a["results"], second_b["results"]);
    // Page 2 is a distinct chunk from page 1 (deterministic recompute + skip).
    assert_ne!(first["results"], second_a["results"]);
}

#[test]
fn ct3_cursor_003_mismatched_cursor_is_rejected() {
    let dir = indexed_scope();
    let first = json_success(&dir, &["search", "認証仕様", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap();
    let err = json_failure(
        &dir,
        &[
            "search",
            "検索ランキング",
            "--cursor",
            cursor,
            "--limit",
            "1",
        ],
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
    let first = json_success(&dir, &["search", "認証仕様", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap();
    let by_cursor = json_success(
        &dir,
        &["search", "認証仕様", "--cursor", cursor, "--limit", "1"],
    );
    let by_offset = json_success(
        &dir,
        &["search", "認証仕様", "--offset", "1", "--limit", "1"],
    );
    assert_eq!(by_cursor["results"], by_offset["results"]);
}

#[test]
fn ct3_cursor_001_end_of_stream_has_null_next_cursor() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "認証仕様", "--limit", "100"]);
    assert!(!search["results"].as_array().unwrap().is_empty());
    assert!(search["paging"]["next_cursor"].is_null());
}

#[test]
fn ct3_fts_003_two_character_query_is_skipped_with_zero_results() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "認"]);
    assert!(search["results"].as_array().unwrap().is_empty());
}

// Real-machine scenario (a): default (no flag) search crosses sibling scopes via
// the registry, and a `participates_in_global_search=false` scope is excluded.
#[test]
fn ct3_multi_001_default_searches_participating_indexed_scopes() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    let c = parent.path().join("c");
    for dir in [&a, &b, &c] {
        fs::create_dir_all(dir).unwrap();
    }
    fs::write(a.join("a.md"), "# A\n\n## Local\nalpha only\n").unwrap();
    fs::write(
        b.join("b.md"),
        "# B\n\n## Remote\nunique sibling token 4242\n",
    )
    .unwrap();
    fs::write(
        c.join("c.md"),
        "# C\n\n## Hidden\nunique sibling token 4242 private\n",
    )
    .unwrap();
    for dir in [&a, &b, &c] {
        json_success_path(dir, &data_home, &["init"]);
    }
    // Scope c opts out of global search.
    fs::write(
        c.join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[scope]\nparticipates_in_global_search = false\n",
    )
    .unwrap();
    for dir in [&a, &b, &c] {
        json_success_path(dir, &data_home, &["index", "--approve"]);
    }
    // Default search (no --all-scopes) from scope a still reaches sibling b.
    let search = json_success_path(&a, &data_home, &["search", "unique sibling 4242"]);
    assert!(first_result(&search)["scope_path"]
        .as_str()
        .unwrap()
        .ends_with("/b"));
    let searched = search["searched_scopes"].as_array().unwrap();
    assert_eq!(searched.len(), 2, "c (participates=false) must be excluded");
    assert!(searched
        .iter()
        .all(|scope| !scope["scope_path"].as_str().unwrap().ends_with("/c")));
}

#[test]
fn ct3_multi_008_all_scopes_flag_targets_all_indexed_scopes() {
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

// scope-cross merge is rank-based: both scopes' rank-1 hits get the SAME RRF score
// (1/(60+1)) despite skewed corpus statistics, and tie-break is (scope_path, ...).
#[test]
fn ct3_multi_002_cross_scope_merge_is_rank_based() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    // Scope a: the term sits in a long, filler-heavy chunk (low BM25); scope b: a
    // short chunk (high BM25). Raw BM25 differs; RRF (rank-only) does not.
    let filler = "filler ".repeat(60);
    fs::write(
        a.join("a.md"),
        format!("# A\n\n## Sec\nzephyrterm {filler}\n"),
    )
    .unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Sec\nzephyrterm\n").unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);
    let search = json_success_path(&a, &data_home, &["search", "zephyrterm"]);
    let results = search["results"].as_array().unwrap();
    assert_eq!(results.len(), 2);
    // Identical RRF score proves the merge compares ranks, not raw BM25.
    assert_eq!(results[0]["score"], results[1]["score"]);
    let expected = 1.0f64 / 61.0;
    assert!((results[0]["score"].as_f64().unwrap() - expected).abs() < 1e-12);
    // Deterministic tie-break by scope_path: /a before /b.
    assert!(results[0]["scope_path"].as_str().unwrap().ends_with("/a"));
    assert!(results[1]["scope_path"].as_str().unwrap().ends_with("/b"));
}

// diversify runs on the merged pool: max_per_raw_hash caps a raw_hash across scopes.
#[test]
fn ct3_multi_003_diversify_caps_raw_hash_across_scopes() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let dirs = ["s0", "s1", "s2", "s3"]
        .iter()
        .map(|name| parent.path().join(name))
        .collect::<Vec<_>>();
    for dir in &dirs {
        fs::create_dir_all(dir).unwrap();
        // Identical content across scopes -> identical raw_hash.
        fs::write(
            dir.join("dup.md"),
            "# Dup\n\n## Section\nsharedtoken body\n",
        )
        .unwrap();
        json_success_path(dir, &data_home, &["init"]);
        json_success_path(dir, &data_home, &["index", "--approve"]);
    }
    let search = json_success_path(&dirs[0], &data_home, &["search", "sharedtoken"]);
    assert_eq!(search["searched_scopes"].as_array().unwrap().len(), 4);
    // 4 scopes match the same raw_hash; max_per_raw_hash=3 caps the stream at 3.
    assert_eq!(search["results"].as_array().unwrap().len(), 3);
}

// Real-machine scenario (b): one scope unreachable (chmod 000) -> results + exit 3.
#[test]
fn ct3_multi_005_partial_failure_returns_results_with_exit_3() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## Sec\nalphaunique token\n").unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Sec\nbetaunique token\n").unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);

    // Make scope b unreachable at discovery (its .kcs is unreadable).
    let b_kcs = b.join(".kcs");
    let mut perms = fs::metadata(&b_kcs).unwrap().permissions();
    use std::os::unix::fs::PermissionsExt;
    perms.set_mode(0o000);
    fs::set_permissions(&b_kcs, perms).unwrap();

    let output = Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .args(["search", "alphaunique", "--json"])
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();

    // Restore permissions so the tempdir can be cleaned up.
    let mut restore = fs::metadata(&b_kcs).unwrap().permissions();
    restore.set_mode(0o755);
    fs::set_permissions(&b_kcs, restore).unwrap();

    let search: Value = serde_json::from_slice(&output).unwrap();
    assert!(!search["results"].as_array().unwrap().is_empty());
    assert_eq!(search["searched_scopes"].as_array().unwrap().len(), 1);
    let excluded = search["excluded_scopes"].as_array().unwrap();
    assert_eq!(excluded.len(), 1);
    assert!(excluded[0]["scope_path"].as_str().unwrap().ends_with("/b"));
    // The private exit marker never leaks into the payload.
    assert!(search.get("__exit_code").is_none());
}

#[test]
fn ct3_multi_005_all_failed_returns_exit_4() {
    // A scope that is init'd but not indexed is not a search target; with no other
    // indexed scope the search is a permanent all-scope failure.
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# A\n\n## Sec\nalpha\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    let err = json_failure(&dir, &["search", "alpha"], 4);
    assert_eq!(err["error_code"], "KCS-E-SEARCH-SCOPE-ALL-FAILED-001");
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

// Real-machine scenario (c): a cursor freezes the chunk set by max_rowid; chunks
// indexed after the cursor was issued do not leak into page 2.
#[test]
fn ct3_cursor_002_max_rowid_excludes_post_cursor_chunks() {
    let dir = indexed_scope();
    let first = json_success(&dir, &["search", "認証仕様", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap().to_owned();

    // Append a new file that also matches the query, then re-index (HEAD advances,
    // new chunk rows get rowid > the cursor's max_rowid).
    fs::write(
        dir.path().join("addendum.md"),
        "# 認証仕様の追補\n\n## 追補\nposttoken マーカー を追加しました。\n",
    )
    .unwrap();
    json_success(&dir, &["index", "--approve"]);

    // A fresh search sees the new chunk (proves the setup is live)...
    let fresh = json_success(&dir, &["search", "認証仕様", "--limit", "100"]);
    let fresh_has_new = fresh["results"]
        .as_array()
        .unwrap()
        .iter()
        .any(|r| r["snippet"].as_str().unwrap_or("").contains("posttoken"));
    assert!(fresh_has_new, "fresh search must include the new chunk");

    // ...but page 2 via the frozen cursor must not.
    let page2 = json_success(
        &dir,
        &["search", "認証仕様", "--cursor", &cursor, "--limit", "100"],
    );
    let leaked = page2["results"]
        .as_array()
        .unwrap()
        .iter()
        .any(|r| r["snippet"].as_str().unwrap_or("").contains("posttoken"));
    assert!(!leaked, "post-cursor chunk must not appear on page 2");
}

#[test]
fn ct3_cursor_005_shallow_snapshot_cursor_is_rejected() {
    let dir = indexed_scope();
    let first = json_success(&dir, &["search", "認証仕様", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap().to_owned();
    // Discard the snapshot's tree objects, emulating a shallow (tiered-retention)
    // commit. The cursor can no longer be replayed.
    fs::remove_dir_all(dir.path().join(".kcs/objects/trees")).unwrap();
    let err = json_failure(
        &dir,
        &["search", "認証仕様", "--cursor", &cursor, "--limit", "100"],
        1,
    );
    assert_eq!(err["error_code"], "KCS-E-COMMIT-SHALLOW-001");
}

#[test]
fn ct3_obs_001_index_status_reports_partial_enrichment() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "認証仕様"]);
    let status = &search["index_status"];
    assert!(status.is_object());
    // Offline index leaves online markdownize enhancement pending.
    assert!(status["enriched_ratio"].as_f64().unwrap() < 1.0);
    assert!(status["pending_enrichment_tasks"].as_u64().unwrap() > 0);
    assert_eq!(status["budget_paused"], false);
}

#[test]
fn ct3_hybrid_003_text_and_vector_unavailable_is_an_error() {
    let dir = indexed_scope();
    // Remove the FTS index (text unavailable) and request vector (also unavailable).
    fs::remove_file(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    let err = json_failure(&dir, &["search", "認証仕様", "--vector"], 1);
    assert_eq!(err["error_code"], "KCS-E-SEARCH-VEC-UNAVAIL-001");
}

#[test]
fn ct3_obs_002_metrics_use_search_namespace_code_and_component() {
    let dir = indexed_scope();
    json_success(&dir, &["search", "認証仕様"]);
    let metrics = fs::read_to_string(dir.path().join(".test-data/kcs/logs/metrics.jsonl")).unwrap();
    let last: Value = serde_json::from_str(metrics.lines().last().unwrap()).unwrap();
    assert_eq!(last["code"], "KCS-M-SEARCH-001");
    assert_eq!(last["component"], "search");
    assert_eq!(last["metric"], "search.latency_ms");
    assert!(last["value"].as_f64().is_some());
    assert!(last["context"]["result_count"].as_u64().is_some());
}

// K8 / CT3-FTS-004: search is served from sqlite.db; deleting it disables search,
// and `repair --rebuild-db` re-derives the FTS index from chunks.
#[test]
fn ct3_fts_004_rebuild_db_reenables_fts_search() {
    let dir = indexed_scope();
    fs::remove_file(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    // With the only scope's index gone, search is a permanent all-scope failure.
    let err = json_failure(&dir, &["search", "認証仕様"], 4);
    assert_eq!(err["error_code"], "KCS-E-SEARCH-SCOPE-ALL-FAILED-001");
    json_success(&dir, &["repair", "--rebuild-db"]);
    let after = json_success(&dir, &["search", "認証仕様"]);
    assert!(!after["results"].as_array().unwrap().is_empty());
}

fn line_count(path: impl AsRef<Path>) -> usize {
    fs::read_to_string(path).unwrap().lines().count()
}

// ---------------------------------------------------------------------------
// K6 — Evidence Pointer resolver (08 §3 / §4). Helpers below run `kcs` with a
// caller-chosen cwd + XDG home so scope resolution stages can be isolated, and
// place fixtures (tombstones, shallow commits) that Step 3 has no generator for.
// ---------------------------------------------------------------------------

use kcs_index::registry::{RegistryDb, RegistryEntry};

/// Runs `kcs <args> --json` and returns `(exit_code, parsed_json)`, reading
/// stdout on success and stderr on failure (mirrors `json_success`/`json_failure`).
fn run_json(cwd: &Path, data_home: &Path, args: &[&str]) -> (i32, Value) {
    let output = Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(cwd)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .args(args)
        .arg("--json")
        .output()
        .unwrap();
    let code = output.status.code().unwrap();
    let stream = if output.status.success() {
        &output.stdout
    } else {
        &output.stderr
    };
    (code, serde_json::from_slice(stream).unwrap())
}

/// CAS object path: `<kcs>/objects/<kind>/ab/cd/<hash>` (kcs_core::cas::fanout).
fn object_path(kcs_dir: &Path, kind: &str, hash: &str) -> std::path::PathBuf {
    let digest = hash.strip_prefix("sha256:").unwrap();
    kcs_dir
        .join("objects")
        .join(kind)
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(hash)
}

/// Tombstone path: `<kcs>/tombstones/ab/cd/<raw_hash>` (05 §3.5).
fn tombstone_path(kcs_dir: &Path, raw_hash: &str) -> std::path::PathBuf {
    let digest = raw_hash.strip_prefix("sha256:").unwrap();
    kcs_dir
        .join("tombstones")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(raw_hash)
}

fn registry_path(data_home: &Path) -> std::path::PathBuf {
    data_home.join("data/kcs/scope-registry.sqlite")
}

#[test]
fn ct3_evidence_003_scope_resolves_via_path_then_registry() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let scope = parent.path().join("research");
    let elsewhere = parent.path().join("elsewhere");
    fs::create_dir_all(&scope).unwrap();
    fs::create_dir_all(&elsewhere).unwrap();
    fs::write(
        scope.join("auth.md"),
        "# 認証仕様\n\n## API Token\nトークン TTL は 3600 秒です。\n",
    )
    .unwrap();
    json_success_path(&scope, &data_home, &["init"]);
    json_success_path(&scope, &data_home, &["index", "--approve"]);
    let search = json_success_path(&scope, &data_home, &["search", "トークン TTL 3600"]);
    let pointer = first_result(&search)["evidence_pointer"].clone();
    let scope_id = pointer["scope_id"].as_str().unwrap().to_owned();

    // (a) valid scope_path + matching scope_id resolves. Run from a non-scope
    //     cwd with an empty registry so *only* stage 1a (scope_path) can succeed.
    let (code, viewed) = run_json(&elsewhere, &data_home, &["view", &pointer.to_string()]);
    assert_eq!(code, 0, "scope_path stage failed: {viewed}");
    assert!(viewed["text"].as_str().unwrap().contains("トークン TTL"));

    // (b) broken scope_path -> registry lookup by scope_id resolves. Register the
    //     scope directly (index-time registry wiring is Agent A's; §3.1 permits
    //     the registry as the authoritative kcs_path source).
    let registry = RegistryDb::open(registry_path(&data_home)).unwrap();
    registry
        .upsert(&RegistryEntry {
            scope_id: scope_id.clone(),
            kcs_path: scope.join(".kcs").display().to_string(),
            root_path: scope.display().to_string(),
            participates_in_global_search: true,
            indexed: true,
            last_seen_at: "2026-07-04T00:00:00Z".to_owned(),
        })
        .unwrap();
    let mut broken = pointer.clone();
    broken["scope_path"] = serde_json::json!(parent.path().join("gone/.kcs").display().to_string());
    let (code, viewed) = run_json(&elsewhere, &data_home, &["view", &broken.to_string()]);
    assert_eq!(code, 0, "registry stage failed: {viewed}");
    assert!(viewed["text"].as_str().unwrap().contains("トークン TTL"));

    // (c) broken scope_path + unknown scope_id + registry miss -> scope_unreachable.
    let mut orphan = pointer.clone();
    orphan["scope_path"] = serde_json::json!(parent.path().join("gone/.kcs").display().to_string());
    orphan["scope_id"] = serde_json::json!("scope_does_not_exist");
    let (code, err) = run_json(&elsewhere, &data_home, &["view", &orphan.to_string()]);
    assert_eq!(code, 4);
    assert_eq!(err["error_code"], "KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001");
}

#[test]
fn ct3_evidence_004_resolves_through_pointer_commit_tree() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let scope = parent.path().join("research");
    fs::create_dir_all(&scope).unwrap();
    fs::write(
        scope.join("auth.md"),
        "# 認証仕様\n\n## API Token\nトークン TTL は 3600 秒です。\n",
    )
    .unwrap();
    json_success_path(&scope, &data_home, &["init"]);
    json_success_path(&scope, &data_home, &["index", "--approve"]);
    let search1 = json_success_path(&scope, &data_home, &["search", "トークン TTL 3600"]);
    let p_auth = first_result(&search1)["evidence_pointer"].clone();
    let commit1 = p_auth["commit"].as_str().unwrap().to_owned();

    // Advance HEAD: add a second file, re-index (new tree -> commit2).
    fs::write(
        scope.join("ranking.md"),
        "# 検索ランキング\n\n## RRF 融合\nRRF の定数 k=60 を使います。\n",
    )
    .unwrap();
    json_success_path(&scope, &data_home, &["index", "--approve"]);
    let search2 = json_success_path(&scope, &data_home, &["search", "RRF 定数 k 60"]);
    let p_rank = pointer_for_path(&search2, "ranking.md").clone();
    let commit2 = p_rank["commit"].as_str().unwrap().to_owned();
    assert_ne!(commit1, commit2, "HEAD did not advance");

    // The auth pointer (commit1) still resolves after HEAD advanced: resolution
    // walks pointer.commit's tree, not HEAD's.
    let (code, viewed) = run_json(&scope, &data_home, &["view", &p_auth.to_string()]);
    assert_eq!(code, 0, "old-commit pointer stopped resolving: {viewed}");
    assert!(viewed["text"].as_str().unwrap().contains("トークン TTL"));

    // Discriminator: ranking.md's raw_hash exists in the working tree, in CAS,
    // and in commit2's tree — but NOT in commit1's tree. Pointing p_rank at
    // commit1 must fail (a working-tree scan would wrongly succeed).
    let mut mismatched = p_rank.clone();
    mismatched["commit"] = serde_json::json!(commit1);
    let (code, err) = run_json(&scope, &data_home, &["view", &mismatched.to_string()]);
    assert_eq!(
        code, 4,
        "raw_hash absent from pointer.commit tree should fail"
    );
    assert_eq!(err["error_code"], "KCS-E-PURGE-NOT-FOUND-001");
}

#[test]
fn ct3_evidence_005_shallow_commit_resolves_directly() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let pointer = first_result(&search)["evidence_pointer"].clone();
    let commit = pointer["commit"].as_str().unwrap();
    let kcs_dir = dir.path().join(".kcs");

    // Make the commit shallow: discard its tree object (05 §2.2 GC has no Step 3
    // generator, so hand-place the shallow state).
    let commit_bytes = fs::read(object_path(&kcs_dir, "commits", commit)).unwrap();
    let commit_obj: Value = serde_json::from_slice(&commit_bytes).unwrap();
    let tree = commit_obj["tree"].as_str().unwrap();
    fs::remove_file(object_path(&kcs_dir, "trees", tree)).unwrap();

    let ptr = pointer.to_string();
    let viewed = json_success(&dir, &["view", &ptr]);
    assert_eq!(viewed["commit_shallow"], true);
    assert!(viewed["text"].as_str().unwrap().contains("トークン TTL"));

    let opened = json_success(&dir, &["open", &ptr]);
    assert_eq!(opened["commit_shallow"], true);
    assert_eq!(opened["status"], "opened");
    assert!(opened["path"].as_str().unwrap().ends_with("auth.md"));
}

#[test]
fn ct3_evidence_006_three_valued_resolution_failures() {
    // (a) tombstoned -> status="purged" response, open exit 4.
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let pointer = first_result(&search)["evidence_pointer"].clone();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    let commit = pointer["commit"].as_str().unwrap().to_owned();
    let kcs_dir = dir.path().join(".kcs");
    let tomb = tombstone_path(&kcs_dir, &raw_hash);
    fs::create_dir_all(tomb.parent().unwrap()).unwrap();
    fs::write(
        &tomb,
        serde_json::json!({
            "raw_hash": raw_hash,
            "purged_at": "2026-04-25T12:00:00Z",
            "purged_reason": "legal",
            "purged_in_commit": commit,
        })
        .to_string(),
    )
    .unwrap();
    let ptr = pointer.to_string();
    let err = json_failure(&dir, &["open", &ptr], 4);
    assert_eq!(err["error_code"], "KCS-E-PURGE-TOMBSTONED-001");
    assert_eq!(err["context"]["status"], "purged");
    assert_eq!(err["context"]["purged_reason"], "legal");
    assert_eq!(err["context"]["raw_hash"], raw_hash);

    // (b) no tombstone but the raw object is gone -> not_found.
    let dir_b = indexed_scope();
    let search_b = json_success(&dir_b, &["search", "トークン TTL 3600"]);
    let pointer_b = first_result(&search_b)["evidence_pointer"].clone();
    let raw_hash_b = pointer_b["raw_hash"].as_str().unwrap().to_owned();
    fs::remove_file(dir_b.path().join("auth.md")).unwrap();
    fs::remove_file(object_path(&dir_b.path().join(".kcs"), "raw", &raw_hash_b)).unwrap();
    let ptr_b = pointer_b.to_string();
    let err_b = json_failure(&dir_b, &["open", &ptr_b], 4);
    assert_eq!(err_b["error_code"], "KCS-E-PURGE-NOT-FOUND-001");

    // (c) scope unreachable.
    let dir_c = indexed_scope();
    let bad = "kcs://scope_missing/sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc/sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd";
    let err_c = json_failure(&dir_c, &["open", bad], 4);
    assert_eq!(err_c["error_code"], "KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001");
}

#[test]
fn ct3_uri_002_open_resolves_object_raw_uri() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let pointer = &first_result(&search)["evidence_pointer"];
    let scope_id = pointer["scope_id"].as_str().unwrap();
    let raw_hash = pointer["raw_hash"].as_str().unwrap();
    let uri = format!("kcs://{scope_id}/object/raw/{raw_hash}");
    let opened = json_success(&dir, &["open", &uri]);
    assert_eq!(opened["status"], "opened");
    assert_eq!(opened["object_type"], "raw");
    assert!(opened["path"].as_str().unwrap().ends_with("auth.md"));
}

#[test]
fn ct3_uri_002_open_rejects_invalid_object_uri() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let pointer = &first_result(&search)["evidence_pointer"];
    let scope_id = pointer["scope_id"].as_str().unwrap().to_owned();
    let raw_hash = pointer["raw_hash"].as_str().unwrap().to_owned();
    // Unknown object type -> exit 2.
    json_failure(
        &dir,
        &["open", &format!("kcs://{scope_id}/object/bogus/{raw_hash}")],
        2,
    );
    // Malformed hash -> exit 2.
    json_failure(
        &dir,
        &["open", &format!("kcs://{scope_id}/object/raw/not-a-hash")],
        2,
    );
}

fn pointer_for_path<'a>(search: &'a Value, path: &str) -> &'a Value {
    search["results"]
        .as_array()
        .unwrap()
        .iter()
        .find(|result| result["evidence_pointer"]["path_at_commit"] == path)
        .map(|result| &result["evidence_pointer"])
        .unwrap_or_else(|| panic!("no search result for {path}"))
}
