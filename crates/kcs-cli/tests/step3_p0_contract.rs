use std::fs;
use std::path::Path;

use assert_cmd::Command;
use kcs_adapter::catalog::{TEST_ADOPTED_EMBEDDING_ENV, TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV};
use serde_json::Value;
use tempfile::TempDir;

fn kcs(dir: &TempDir, args: &[&str]) -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    command
        .current_dir(dir.path())
        .env("XDG_CONFIG_HOME", dir.path().join(".test-config"))
        .env("XDG_DATA_HOME", dir.path().join(".test-data"))
        .env("XDG_CACHE_HOME", dir.path().join(".test-cache"))
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
        .env("XDG_CACHE_HOME", data_home.join("cache"))
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

// K4 embedding seam helpers: run `kcs` with the deterministic adapter mock.
fn json_success_embed(dir: &TempDir, embed: &str, args: &[&str]) -> Value {
    let output = kcs(dir, args)
        .env(TEST_ADOPTED_EMBEDDING_ENV, embed)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_failure_embed(dir: &TempDir, embed: &str, args: &[&str], code: i32) -> Value {
    let output = kcs(dir, args)
        .env(TEST_ADOPTED_EMBEDDING_ENV, embed)
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stderr
        .clone();
    serde_json::from_slice(&output).unwrap()
}

/// R11-2: an embedding-adapter run that exits non-zero (auth 5 / budget 6) while
/// still printing its full result JSON to stdout (the search "result + nonzero"
/// shape). Asserts the exit code and returns the stdout payload.
fn json_code_stdout_embed(dir: &TempDir, embed: &str, code: i32, args: &[&str]) -> Value {
    let output = kcs(dir, args)
        .env(TEST_ADOPTED_EMBEDDING_ENV, embed)
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_success_embed_at(dir: &TempDir, embed: &str, fixed_now: &str, args: &[&str]) -> Value {
    let output = kcs(dir, args)
        .env(TEST_ADOPTED_EMBEDDING_ENV, embed)
        .env("KCS_FIXED_NOW", fixed_now)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn run_embed_path(path: &Path, data_home: &Path, embed: &str, args: &[&str]) -> Value {
    let output = Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(path)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .env(TEST_ADOPTED_EMBEDDING_ENV, embed)
        .args(args)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

/// The `indexed_scope` fixture indexed with a configured embedding adapter.
fn indexed_scope_embed(embed: &str) -> TempDir {
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
    json_success_embed(&dir, embed, &["index", "--approve"]);
    dir
}

fn chunk_hash_set(search: &Value) -> std::collections::BTreeSet<String> {
    search["results"]
        .as_array()
        .unwrap()
        .iter()
        .map(|result| result["chunk_hash"].as_str().unwrap().to_owned())
        .collect()
}

fn first_result(search: &Value) -> &Value {
    &search["results"].as_array().unwrap()[0]
}

// CT3-HYBRID-001 (scenario (d)): with a configured, compatible embedding index,
// auto resolves to hybrid, RRF fuses text+vector, MMR runs on real embeddings, and
// the fallback fields are clean.
#[test]
fn ct3_hybrid_001_auto_resolves_to_hybrid_with_rrf_fusion() {
    let dir = indexed_scope_embed("mock");
    let hybrid = json_success_embed(&dir, "mock", &["search", "認証仕様 トークン"]);
    assert_eq!(hybrid["requested_mode"], "auto");
    assert_eq!(hybrid["resolved_mode"], "hybrid");
    assert_eq!(hybrid["fallback"], false);
    assert!(hybrid["fallback_reason"].is_null());
    // MMR ran on real embeddings — impossible in text-only, which reports
    // "group_by_raw_hash" (the K2 honesty fix). This is the vector-supply proof.
    assert_eq!(hybrid["diversify"]["strategy"], "mmr");
    // Vector recall contributes candidates the text backend never matched: the
    // hybrid result set is a strict superset of the text-only set (RRF fusion —
    // the order/content genuinely changes vs text alone).
    let text = json_success_embed(&dir, "mock", &["search", "認証仕様 トークン", "--text"]);
    let hybrid_set = chunk_hash_set(&hybrid);
    let text_set = chunk_hash_set(&text);
    assert!(
        hybrid_set.len() > text_set.len(),
        "hybrid must add vector-only candidates"
    );
    assert!(text_set.iter().all(|chunk| hybrid_set.contains(chunk)));
}

// CT3-HYBRID-002 (de-tautologized, pair-discriminating): the fallback_reason names
// the ACTUAL cause, and the same scope+query flips to hybrid once the cause is
// removed — so the assertion cannot pass against a permanently-degraded stub.
#[test]
fn ct3_hybrid_002_auto_vector_configured_but_absent_falls_back_visibly() {
    let dir = indexed_scope(); // indexed without an embedding adapter → no vectors
                               // (a) endpoint truly unconfigured → the 05 §1.7 example string.
                               // "off" is an unrecognized seam value → no adapter, regardless of any
                               // ambient GEMINI_API_KEY.
    let unconfigured = json_success_embed(&dir, "off", &["search", "トークン TTL 3600"]);
    assert_eq!(unconfigured["resolved_mode"], "text");
    assert_eq!(
        unconfigured["fallback_reason"],
        "embedding_endpoint_not_configured"
    );
    // (b) endpoint configured (mock) but this scope carries no embeddings →
    // the precise cause, not the generic endpoint string.
    let search = json_success_embed(&dir, "mock", &["search", "トークン TTL 3600"]);
    assert_eq!(search["requested_mode"], "auto");
    assert_eq!(search["resolved_mode"], "text");
    assert_eq!(search["fallback"], true);
    assert_eq!(search["fallback_reason"], "embedding_index_missing");
    assert_eq!(search["error_code"], "KCS-E-SEARCH-VEC-UNAVAIL-001");
    // (c) pair-discrimination: embed the same scope, then the SAME query resolves
    // hybrid with the fallback gone.
    json_success_embed(&dir, "mock", &["index", "--approve"]);
    let hybrid = json_success_embed(&dir, "mock", &["search", "トークン TTL 3600"]);
    assert_eq!(hybrid["resolved_mode"], "hybrid");
    assert_eq!(hybrid["fallback"], false);
    assert!(hybrid["fallback_reason"].is_null());
    assert!(hybrid["error_code"].is_null());
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

// F2: NFD (decomposed) body content must be found by an NFC (composed) query.
// The FTS index projection and the CLI query are both normalized to NFC, so
// canonically-equivalent forms match regardless of input form. Before the fix
// the trigram index kept the raw NFD bytes and an NFC query returned 0 results
// (a silent false negative — exit 0, empty).
#[test]
fn f2_nfd_body_is_found_by_nfc_query() {
    let dir = tempfile::tempdir().unwrap();
    // Body word "café" written in NFD: "cafe" + U+0301 COMBINING ACUTE ACCENT.
    fs::write(
        dir.path().join("menu.md"),
        "# メニュー\n\n## Cafe\nThe cafe\u{301} latte special is served every morning.\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);

    // Composed (NFC) query "café": the byte substring is absent from the NFD
    // content, so only the normalized index projection makes this hit.
    let search = json_success(&dir, &["search", "caf\u{e9} latte", "--text"]);
    assert!(
        !search["results"].as_array().unwrap().is_empty(),
        "NFC query must find NFD-stored content: {search}"
    );
}

// CT3-EMBED-002 (de-tautologized): a genuinely incompatible embedding profile in
// the index. auto → text fallback with INCOMPAT; --vector → hard error INCOMPAT
// (does not fall back, distinct from UNAVAIL).
#[test]
fn ct3_embed_002_incompatible_profile_falls_back_or_errors() {
    let dir = indexed_scope_embed("incompatible_profile");
    let auto = json_success_embed(
        &dir,
        "incompatible_profile",
        &["search", "トークン TTL 3600"],
    );
    assert_eq!(auto["resolved_mode"], "text");
    assert_eq!(auto["fallback"], true);
    assert_eq!(auto["error_code"], "KCS-E-SEARCH-VEC-INCOMPAT-001");
    let err = json_failure_embed(
        &dir,
        "incompatible_profile",
        &["search", "トークン", "--vector"],
        1,
    );
    assert_eq!(err["error_code"], "KCS-E-SEARCH-VEC-INCOMPAT-001");
}

// CT3-EMBED-007: --vector with no embedding index at all is a hard error (UNAVAIL,
// not a fallback). Distinct code from the incompatible case above.
#[test]
fn ct3_embed_007_vector_only_without_index_is_an_error() {
    let dir = indexed_scope();
    let err = json_failure_embed(&dir, "mock", &["search", "トークン", "--vector"], 1);
    assert_eq!(err["error_code"], "KCS-E-SEARCH-VEC-UNAVAIL-001");
}

// R11-7: the `[search]` config (default_mode / fail_behavior) was schema-valid and
// documented but entirely unwired (the [search] version of R10-2 config drift). A
// text-only scope (no embedding adapter → vector unavailable) exercises all three.
fn write_search_config(dir: &TempDir, body: &str) {
    fs::write(
        dir.path().join(".kcs/config.toml"),
        format!("kcs_format_version = \"0.1.0\"\n[search]\n{body}"),
    )
    .unwrap();
}

#[test]
fn r11_7_default_mode_config_seeds_requested_mode() {
    let dir = indexed_scope();
    write_search_config(&dir, "default_mode = \"hybrid\"\n");
    // No CLI mode flag → the config default_mode is adopted as requested_mode
    // (previously ignored: requested_mode was always the hardcoded "auto").
    let search = json_success(&dir, &["search", "トークン TTL"]);
    assert_eq!(search["requested_mode"], "hybrid");
    // An explicit flag still wins over the config default.
    let text = json_success(&dir, &["search", "トークン TTL", "--text"]);
    assert_eq!(text["requested_mode"], "text");
}

#[test]
fn r11_7_fail_behavior_error_makes_hybrid_hard_error() {
    let dir = indexed_scope();
    write_search_config(&dir, "fail_behavior = \"error\"\n");
    // --hybrid with no vector backend + fail_behavior=error is now the same hard
    // error the explicit --vector path returns, not a silent exit-0 text fallback.
    let err = json_failure(&dir, &["search", "トークン TTL", "--hybrid"], 1);
    assert_eq!(err["error_code"], "KCS-E-SEARCH-VEC-UNAVAIL-001");
}

#[test]
fn r11_7_fail_behavior_warn_falls_back_with_warning() {
    let dir = indexed_scope();
    write_search_config(&dir, "fail_behavior = \"warn\"\n");
    let search = json_success(&dir, &["search", "トークン TTL", "--hybrid"]);
    assert_eq!(search["resolved_mode"], "text");
    assert_eq!(search["fallback"], true);
    assert!(
        search["warning"]
            .as_str()
            .is_some_and(|w| w.contains("vector search unavailable")),
        "warn must surface a warning field: {search}"
    );
}

#[test]
fn ct3_evidence_001_search_results_include_pointer_and_uri() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let result = first_result(&search);
    let pointer = &result["evidence_pointer"];
    // 08 §2.1 required 6: schema_version / commit / raw_hash / tool_profile_hash /
    // chunk_hash / scope_id — all 6, not a subset, at the actual `--json` output
    // level (the response is hand-assembled JSON in the CLI, not a struct
    // serialization, so field presence must be checked here and not assumed from
    // the kcs-search type definitions).
    assert_eq!(pointer["schema_version"], 1);
    assert!(pointer["commit"].as_str().unwrap().starts_with("sha256:"));
    assert!(pointer["raw_hash"].as_str().unwrap().starts_with("sha256:"));
    assert!(pointer["tool_profile_hash"]
        .as_str()
        .unwrap()
        .starts_with("sha256:"));
    assert!(pointer["chunk_hash"]
        .as_str()
        .unwrap()
        .starts_with("sha256:"));
    // scope_id is a bare 26-char Crockford-base32 ULID (kcs-core::scope::is_ulid),
    // not "scope_"-prefixed — that prefix only appears in the spec doc's
    // illustrative fixture strings.
    assert_eq!(pointer["scope_id"].as_str().unwrap().len(), 26);
    // M3-1 completion condition: search-issued pointers additionally carry
    // heading_path + span.
    assert_eq!(pointer["heading_path"][1], "API Token");
    assert!(pointer["char_start"].as_u64().is_some());
    assert!(pointer["char_end"].as_u64().is_some());
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

// R11-9: `view --json` must expose the same `temporary` field as `open --json`,
// since both resolve the identical pointer and Agents branch on it.
#[test]
fn r11_9_view_json_exposes_temporary_field() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"]
        .as_str()
        .unwrap()
        .to_owned();
    // Working-tree file present -> resolves from raw, not a temporary copy.
    let viewed = json_success(&dir, &["view", &uri]);
    assert_eq!(viewed["temporary"], false);
    // Removing the working-tree file forces a temporary expansion, and `view`
    // must surface it just like `open` does (ct3_open_002).
    fs::remove_file(dir.path().join("auth.md")).unwrap();
    let viewed_temp = json_success(&dir, &["view", &uri]);
    assert_eq!(viewed_temp["temporary"], true);
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
    let searched = search["searched_scopes"].as_array().unwrap();
    assert_eq!(searched.len(), 1);
    assert!(search["excluded_scopes"].as_array().unwrap().is_empty());
    // 05 §1.8: searched_scopes[] = {scope_id, scope_path, snapshot_at}, same
    // shape for a single-scope search as for multi-scope.
    // Bare 26-char ULID, see the ct3_evidence_001 scope_id note above.
    assert_eq!(searched[0]["scope_id"].as_str().unwrap().len(), 26);
    assert!(!searched[0]["scope_path"].as_str().unwrap().is_empty());
    assert!(searched[0]["snapshot_at"]
        .as_str()
        .unwrap()
        .starts_with("sha256:"));
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

// CT3-CHUNK-010: the tree_entries projection is asserted against the real
// `sqlite.db` written by `kcs index` (the CLI projects tree_entries with its
// own SQL — `ensure_snapshot_tree_entries` / `write_tree_entries` /
// `rebuild_sqlite_index`; the former kcs-index::tree_entries scaffold module
// was dead code and has been removed).
#[test]
fn ct3_chunk_010_head_tree_entries_are_populated_with_gen_after_index() {
    let dir = indexed_scope();
    let conn = rusqlite::Connection::open(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    let mut stmt = conn
        .prepare("SELECT commit_hash, path, raw_hash, gen FROM tree_entries")
        .unwrap();
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, i64>(3)?,
            ))
        })
        .unwrap()
        .collect::<std::result::Result<Vec<_>, _>>()
        .unwrap();
    assert!(!rows.is_empty(), "tree_entries must be populated for HEAD");
    // All rows belong to the single HEAD commit (the `indexed_scope` fixture
    // never reindexes), and gen defaults to 0 (04 §4.5 gen projection).
    let head_commit = rows[0].0.clone();
    assert!(rows.iter().all(|(commit, _, _, _)| *commit == head_commit));
    assert!(rows.iter().any(|(_, path, _, _)| path == "auth.md"));
    assert!(rows.iter().any(|(_, path, _, _)| path == "ranking.md"));
    assert!(rows.iter().all(|(_, _, _, gen)| *gen == 0));
    // The projection is what actually gates search (chunks ⨝ tree_entries(HEAD),
    // 05 §1.6): cross-check a live search result's raw_hash is one of the
    // projected rows, proving this table (not just the unused pure function) is
    // what search reads.
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let raw_hash = first_result(&search)["evidence_pointer"]["raw_hash"]
        .as_str()
        .unwrap();
    assert!(rows.iter().any(|(_, _, rh, _)| rh == raw_hash));
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

// R11-4: `build_sqlite_index_at` now wraps all three rebuild loops (chunks,
// tree_entries, preserved embeddings) in one transaction. The rebuild must stay
// functionally identical — the FULL result set (every chunk, not just the top
// hit) must be byte-identical before and after a from-scratch rebuild.
#[test]
fn r11_4_transactional_rebuild_preserves_full_result_set() {
    let dir = indexed_scope();
    let before = json_success(&dir, &["search", "認証仕様", "--limit", "20"]);
    let before_set = chunk_hash_set(&before);
    assert!(!before_set.is_empty(), "fixture must return chunks");
    fs::remove_file(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    json_success(&dir, &["repair", "--rebuild-db"]);
    let after = json_success(&dir, &["search", "認証仕様", "--limit", "20"]);
    assert_eq!(before_set, chunk_hash_set(&after));
    assert_eq!(before["results"], after["results"]);
}

#[test]
fn ct3_uri_003_inline_json_pointer_is_accepted_by_view() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let pointer = first_result(&search)["evidence_pointer"].to_string();
    let viewed = json_success(&dir, &["view", &pointer]);
    assert!(viewed["text"].as_str().unwrap().contains("3600"));
}

// CT3-URI-003 (gap fill): the `<pointer>` receiver has 5 prefix branches
// (`-` stdin / `kcs://` / `{` inline JSON / `sha256:` short form / other ->
// exit 2). Only the `kcs://` (ct3_open_001 etc.) and `{` (above) branches had
// a dedicated P0 test; `-` stdin and the exit-2 fallback were untested.
#[test]
fn ct3_uri_003_stdin_dash_prefix_is_accepted_by_view() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"]
        .as_str()
        .unwrap()
        .to_owned();
    let output = kcs(&dir, &["view", "-"])
        .arg("--json")
        .write_stdin(uri)
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let viewed: Value = serde_json::from_slice(&output).unwrap();
    assert!(viewed["text"].as_str().unwrap().contains("3600"));
}

#[test]
fn ct3_uri_003_unrecognized_pointer_prefix_is_invalid_usage_exit_2() {
    let dir = indexed_scope();
    let err = json_failure(&dir, &["view", "not-a-pointer-at-all"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");
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

// CT3-CHUNK-007 (gap fill): the test above only checks that chunks.jsonl grew
// (append-only), never the "検索対象は現行 chunking_config_hash の chunk のみ"
// clause (04 §4.4/§4.6, K8). The stale-generation chunk row must survive on
// disk but stop being served by search once a newer chunking_config_hash
// generation exists for the same content.
#[test]
fn ct3_chunk_007_search_only_serves_current_chunking_config_generation() {
    let dir = indexed_scope();
    let before = json_success(&dir, &["search", "トークン TTL 3600"]);
    let stale_chunk_hash = first_result(&before)["chunk_hash"]
        .as_str()
        .unwrap()
        .to_owned();

    // A much smaller max_chars forces this section to actually re-split, so the
    // new generation's chunk_hash (char_start/char_end shift) differs from the
    // stale one — this isn't a same-hash no-op reindex.
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[chunking]\nstrategy = \"heading\"\nmax_chars = 10\n",
    )
    .unwrap();
    json_success(&dir, &["index", "--approve"]);

    let after = json_success(&dir, &["search", "トークン TTL 3600"]);
    let after_hashes = chunk_hash_set(&after);
    assert!(
        !after_hashes.is_empty(),
        "new-generation chunks must remain searchable"
    );
    assert!(
        !after_hashes.contains(&stale_chunk_hash),
        "stale chunking_config_hash generation leaked into search results"
    );
    // The stale row genuinely still exists on disk (append-only, CT3-CHUNK-008),
    // it just must not be served by search.
    let jsonl = fs::read_to_string(dir.path().join(".kcs/index/chunks.jsonl")).unwrap();
    assert!(
        jsonl.contains(&stale_chunk_hash),
        "stale chunk row must not be deleted from disk"
    );
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

// Label fix: this is CT3-CURSOR-006 ("--offset は cursor の糖衣 ... 末尾を超え
// たら next_cursor: null で終端"), not a second instance of CT3-CURSOR-001
// (determinism of cursor recompute, already covered above). Renamed off the
// ct3_cursor_001_* prefix to stop misclaiming CURSOR-001 coverage.
#[test]
fn ct3_cursor_006_end_of_stream_has_null_next_cursor() {
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
        .env("XDG_CACHE_HOME", data_home.join("cache"))
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
    // 05 §1.8: excluded_scopes[] = {scope_id, scope_path, reason} — the reason
    // must be recorded, not just the fact of exclusion.
    assert!(!excluded[0]["reason"].as_str().unwrap().is_empty());
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

// Cursor replay when a frozen scope is no longer resolvable via the registry:
// query_hash is validated against the cursor's OWN scope list, the surviving
// scope is served, the dropped scope lands in excluded_scopes (reason
// "unreachable"), and the exit is 3 (CT3-MULTI-005 partial-failure semantics) —
// never a misleading KCS-E-SEARCH-CURSOR-001.
#[test]
fn ct3_multi_005_cursor_replay_with_unresolvable_scope_is_partial() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    // "a" sorts first → page 1 serves its chunk (RRF tie-break by scope_path),
    // so the survivor "b" has consumed 0 and still owns results for page 2.
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(
        a.join("a.md"),
        "# 共通仕様\n\n## Alpha\n共通トピック alpha 版です。\n",
    )
    .unwrap();
    fs::write(
        b.join("b.md"),
        "# 共通仕様\n\n## Beta\n共通トピック beta 版です。\n",
    )
    .unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);
    let a_scope: Value =
        serde_json::from_str(&fs::read_to_string(a.join(".kcs/scope.json")).unwrap()).unwrap();
    let a_scope_id = a_scope["scope_id"].as_str().unwrap().to_owned();

    let first = json_success_path(&b, &data_home, &["search", "共通トピック", "--limit", "1"]);
    assert_eq!(first["searched_scopes"].as_array().unwrap().len(), 2);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap().to_owned();

    // Make scope a unresolvable: wipe the registry, re-register b only.
    fs::remove_file(registry_path(&data_home)).unwrap();
    json_success_path(&b, &data_home, &["index", "--approve"]);

    let output = Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(&b)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .args([
            "search",
            "共通トピック",
            "--cursor",
            &cursor,
            "--limit",
            "5",
        ])
        .arg("--json")
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let page2: Value = serde_json::from_slice(&output).unwrap();
    let excluded = page2["excluded_scopes"].as_array().unwrap();
    assert_eq!(excluded.len(), 1);
    assert_eq!(excluded[0]["scope_id"], a_scope_id.as_str());
    assert_eq!(excluded[0]["reason"], "unreachable");
    assert_eq!(page2["searched_scopes"].as_array().unwrap().len(), 1);
    // The surviving scope's results are served on the replayed page.
    let results = page2["results"].as_array().unwrap();
    assert!(!results.is_empty());
    assert!(results[0]["scope_path"].as_str().unwrap().ends_with("/b"));
}

// CT3-EMBED-003 (de-tautologized): cross-scope embedding profiles disagree — scope
// a has a compatible embedding index, scope b an incompatible one. The cross-scope
// search must merge on text only and record the fallback (05 §1.8(5) / 03 §7).
#[test]
fn ct3_embed_003_cross_scope_incompatibility_falls_back_to_text_merge() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## One\nalpha 111\n").unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Two\nbeta 222\n").unwrap();
    run_embed_path(&a, &data_home, "mock", &["init"]);
    run_embed_path(&b, &data_home, "mock", &["init"]);
    // a: compatible embeddings; b: incompatible embeddings.
    run_embed_path(&a, &data_home, "mock", &["index", "--approve"]);
    run_embed_path(
        &b,
        &data_home,
        "incompatible_profile",
        &["index", "--approve"],
    );
    let search = run_embed_path(
        &a,
        &data_home,
        "mock",
        &["search", "beta 222", "--all-scopes"],
    );
    assert_eq!(search["resolved_mode"], "text");
    assert_eq!(search["fallback"], true);
    assert!(search["fallback_reason"].is_string());
    // The cross-scope text merge still returns b's content.
    assert!(!search["results"].as_array().unwrap().is_empty());
}

// CT3-EMBED-008 / scenario (e): a non-multimodal embedding profile is rejected at
// `kcs index` (tool-lock materialize) with KCS-E-EMBED-MODALITY-001 and exit 2 —
// no embeddings are written.
// Naming convention fix (ct3_<domain>_<nnn>_<description>): was
// ct3_embed_modality_..., missing the CT3-EMBED-008 number.
#[test]
fn ct3_embed_008_non_multimodal_profile_is_rejected_at_index() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# A\n\n## One\nalpha 111\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    let err = json_failure_embed(&dir, "non_multimodal", &["index", "--approve"], 2);
    assert_eq!(err["error_code"], "KCS-E-EMBED-MODALITY-001");
}

// CT3-EMBED-005: `repair --rebuild-db` re-derives chunk_vec from the preserved
// `embeddings` rows (source of truth), so hybrid vector search survives the
// rebuild rather than falling back to text.
#[test]
fn ct3_embed_005_rebuild_db_preserves_vector_search() {
    let dir = indexed_scope_embed("mock");
    let before = json_success_embed(&dir, "mock", &["search", "認証仕様 トークン"]);
    assert_eq!(before["resolved_mode"], "hybrid");
    json_success_embed(&dir, "mock", &["repair", "--rebuild-db"]);
    let after = json_success_embed(&dir, "mock", &["search", "認証仕様 トークン"]);
    assert_eq!(after["resolved_mode"], "hybrid");
    assert_eq!(after["fallback"], false);
    assert_eq!(after["diversify"]["strategy"], "mmr");
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
    // R9-2: text-native files no longer enqueue an online task, so the pending
    // enrichment CT3-OBS-001 measures comes from a PDF whose online markdownize
    // stays Pending after an offline index (the deterministic baseline is Done).
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("report.pdf"),
        fake_pdf(&["認証仕様 トークン TTL 3600 のテスト本文"]),
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);
    let search = json_success(&dir, &["search", "認証仕様"]);
    let status = &search["index_status"];
    assert!(status.is_object());
    // Offline index leaves online markdownize enhancement pending.
    assert!(status["enriched_ratio"].as_f64().unwrap() < 1.0);
    assert!(status["pending_enrichment_tasks"].as_u64().unwrap() > 0);
    assert_eq!(status["budget_paused"], false);
}

// CT3-HYBRID-003: "text も vector も不可 → error" on a PLAIN auto search (no
// flags). Both backends live in sqlite.db, so deleting it makes them both
// structurally unavailable → KCS-E-SEARCH-VEC-UNAVAIL-001, exit 1 (05 §1.1).
#[test]
fn ct3_hybrid_003_text_and_vector_unavailable_is_an_error() {
    let dir = indexed_scope();
    // Counter-assertion: the same auto search succeeds while the index exists.
    let before = json_success(&dir, &["search", "認証仕様"]);
    assert!(!before["results"].as_array().unwrap().is_empty());
    // Remove the search index: text (FTS5) and vector (chunk_vec) are both gone.
    fs::remove_file(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    let err = json_failure(&dir, &["search", "認証仕様"], 1);
    assert_eq!(err["error_code"], "KCS-E-SEARCH-VEC-UNAVAIL-001");
    // The excluded scope list discloses why (index_missing).
    assert_eq!(
        err["context"]["excluded_scopes"][0]["reason"],
        "index_missing"
    );
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

// K8 / CT3-FTS-004: search is served from sqlite.db; deleting it disables search
// (both backends unavailable → VEC-UNAVAIL, exit 1 — CT3-HYBRID-003 conformance),
// and `repair --rebuild-db` re-derives the FTS index from chunks.
#[test]
fn ct3_fts_004_rebuild_db_reenables_fts_search() {
    let dir = indexed_scope();
    fs::remove_file(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    // With the only scope's index gone, text and vector are both unavailable.
    let err = json_failure(&dir, &["search", "認証仕様"], 1);
    assert_eq!(err["error_code"], "KCS-E-SEARCH-VEC-UNAVAIL-001");
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
        .env("XDG_CACHE_HOME", data_home.join("cache"))
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

// 08 §3.2 step 6/7 failure contract: scope, commit, and raw_hash all resolve but
// the pointer's chunk_hash has no materialized chunk row in this scope (a
// different tool_profile_hash produced it) → retarget required (08 §5), exit 8
// (06 §7), for BOTH view and open. Decision #33 (tasks/ws1c-decisions.md).
#[test]
fn ct3_evidence_004_missing_chunk_row_requires_retarget() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let mut pointer = first_result(&search)["evidence_pointer"].clone();
    // Valid sha256 shape, absent from the scope's chunk rows.
    pointer["chunk_hash"] = serde_json::json!(
        "sha256:feedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedface"
    );
    let ptr = pointer.to_string();
    let err_view = json_failure(&dir, &["view", &ptr], 8);
    assert_eq!(
        err_view["error_code"],
        "KCS-E-EVIDENCE-RETARGET-REQUIRED-001"
    );
    assert_eq!(err_view["context"]["chunk_hash"], pointer["chunk_hash"]);
    assert_eq!(
        err_view["context"]["tool_profile_hash"],
        pointer["tool_profile_hash"]
    );
    let err_open = json_failure(&dir, &["open", &ptr], 8);
    assert_eq!(
        err_open["error_code"],
        "KCS-E-EVIDENCE-RETARGET-REQUIRED-001"
    );
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

#[test]
fn ct3_embed_009_batch_retry_and_resume_execute_pending_embedding_tasks() {
    // 2026-07-04 実運用で発見した gap の回帰ガード: rate limit で Pending に
    // 積まれた embedding タスクは、`batch retry`/`resume` の executor が
    // Markdownize 専用だったため永遠に実行されなかった。retry → (seam 回復) →
    // 実行完了までを検証する。
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# メモ\n回収率のテスト。\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    let base_now = "2026-07-03T00:00:00Z";
    json_success_embed_at(&dir, "rate_limit", base_now, &["index", "--approve"]);

    let status = json_success_embed(&dir, "rate_limit", &["status"]);
    let failed: Vec<_> = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|t| t["type"] == "embedding" && t["status"] == "failed")
        .collect();
    assert!(
        !failed.is_empty(),
        "rate_limit seam should leave failed embedding tasks"
    );
    assert!(
        failed
            .iter()
            .all(|t| t["attempts"].as_u64().unwrap() > 0 && t["next_retry_at"].is_string()),
        "rate_limit failures must persist retry backoff: {status}"
    );
    let retry_at = failed[0]["next_retry_at"].as_str().unwrap();

    let early = json_success_embed_at(&dir, "mock", base_now, &["batch", "retry"]);
    assert_eq!(
        early["tasks_executed"], 0,
        "retry before next_retry_at must honor backoff: {early}"
    );

    // seam が回復した状態で retry → executor が embedding を実行し done になる
    let retry = json_success_embed_at(&dir, "mock", retry_at, &["batch", "retry"]);
    assert!(
        retry["tasks_executed"].as_u64().unwrap() > 0,
        "retry must execute pending embedding tasks, got {retry}"
    );
    let status = json_success_embed(&dir, "mock", &["status"]);
    let tasks = status["tasks"].as_array().unwrap();
    let emb: Vec<_> = tasks.iter().filter(|t| t["type"] == "embedding").collect();
    assert!(!emb.is_empty());
    assert!(
        emb.iter().all(|t| t["status"] == "done"),
        "all embedding tasks must be done after retry"
    );
}

// R11-5: the enrichment pass now aggregates every embedding task-store update into
// ONE write-back at the end (was a full all()+replace_all per 32-chunk batch =
// O(N²)). The aggregation must not lose per-chunk `fallback_reason`: a rate_limit
// failure must still land the task Failed with reason "rate_limit" and a scheduled
// retry (the paused-side reason "budget_exceeded" is covered by ct3_l2).
#[test]
fn r11_5_aggregated_writeback_preserves_embedding_fallback_reason() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("a.md"),
        "# メモ\n\n## 本文\n集約書き戻しの回帰テスト本文です。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed_at(
        &dir,
        "rate_limit",
        "2026-07-03T00:00:00Z",
        &["index", "--approve"],
    );
    let status = json_success_embed(&dir, "rate_limit", &["status"]);
    let emb = tasks_of_type(&status, "embedding");
    assert!(!emb.is_empty(), "must enqueue embedding tasks: {status}");
    assert!(
        emb.iter().all(|task| task["status"] == "failed"
            && task["fallback_reason"] == "rate_limit"
            && task["next_retry_at"].is_string()),
        "aggregated write-back must preserve each task's rate_limit reason + retry: {status}"
    );
}

// R11-8: a retryable Failed enrichment task (rate_limit, recoverable by `batch
// retry`) must count toward `index_status.pending_enrichment_tasks` — otherwise the
// scope reports enriched_ratio<1.0 with pending=0 and budget_paused=false, a dead
// end an Agent can't act on (the dual of R9-4's "Partial counts as incomplete").
#[test]
fn r11_8_retryable_failed_enrichment_counts_as_pending_in_index_status() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("a.md"),
        "# メモ\n\n## 本文\n再試行可能な失敗の可視化テスト本文です。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed_at(
        &dir,
        "rate_limit",
        "2026-07-03T00:00:00Z",
        &["index", "--approve"],
    );
    let search = json_success_embed(&dir, "rate_limit", &["search", "本文 再試行"]);
    let index_status = &search["index_status"];
    assert!(
        index_status["pending_enrichment_tasks"].as_u64().unwrap() > 0,
        "retryable failed embedding must surface as pending: {index_status}"
    );
    assert!(index_status["enriched_ratio"].as_f64().unwrap() < 1.0);
    // The dead end this closes: ratio<1.0 must no longer coincide with pending=0.
    assert_eq!(index_status["budget_paused"], false);
}

#[test]
fn ct3_embed_010_retry_executes_after_snapshot_advances_head() {
    // 2026-07-04 実運用バグ #2 の回帰ガード: `kcs snapshot` は tree_entries を
    // 射影せず HEAD だけ進めるため、enrichment の live-chunk JOIN が 0 件になり
    // retry/resume が何も実行しなかった (search は lazy 射影するので隠れていた)。
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# メモ\n射影テスト。\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    let base_now = "2026-07-03T00:00:00Z";
    json_success_embed_at(&dir, "rate_limit", base_now, &["index", "--approve"]);
    let status = json_success_embed(&dir, "rate_limit", &["status"]);
    let retry_at = tasks_of_type(&status, "embedding")
        .into_iter()
        .find(|t| t["status"] == "failed")
        .and_then(|t| t["next_retry_at"].as_str())
        .unwrap()
        .to_owned();
    // snapshot で HEAD を射影なしに前進させる (replay の各 step と同じ形)
    json_success_embed_at(&dir, "rate_limit", base_now, &["snapshot", "-m", "advance"]);

    let retry = json_success_embed_at(&dir, "mock", &retry_at, &["batch", "retry"]);
    assert!(
        retry["tasks_executed"].as_u64().unwrap() > 0,
        "retry must project tree_entries lazily and execute, got {retry}"
    );
    let status = json_success_embed(&dir, "mock", &["status"]);
    let emb: Vec<_> = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|t| t["type"] == "embedding")
        .collect();
    assert!(!emb.is_empty());
    assert!(emb.iter().all(|t| t["status"] == "done"));
}

// ---------------------------------------------------------------------------
// Step 4 checkpoint fixes L1-L7 — real-machine acceptance scenarios (a)-(d).
// ---------------------------------------------------------------------------

/// Run `kcs <args> --json` with BOTH online mock seams (markdownize + embedding)
/// so `batch resume`/index can execute both adapters deterministically offline.
fn json_both_mock(dir: &TempDir, args: &[&str]) -> Value {
    json_both_mock_code(dir, args, 0)
}

/// `json_both_mock` asserting a specific exit code and reading STDOUT. R11-2: an
/// `index`/`batch` run whose inline enrichment budget-pauses prints its full result
/// JSON to stdout with a non-zero exit (6), the search "result + nonzero" shape.
fn json_both_mock_code(dir: &TempDir, args: &[&str], code: i32) -> Value {
    let output = kcs(dir, args)
        .env(TEST_ADOPTED_EMBEDDING_ENV, "mock")
        .env(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn tasks_of_type<'a>(status: &'a Value, ty: &str) -> Vec<&'a Value> {
    status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| task["type"] == ty)
        .collect()
}

fn first_online_output_ref(status: &Value) -> String {
    status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .find_map(|task| {
            let output_ref = task["output_ref"].as_str()?;
            output_ref
                .starts_with("online:")
                .then(|| output_ref.to_owned())
        })
        .expect("online task output_ref")
}

fn is_budget_paused(status: &Value, ty: &str) -> bool {
    tasks_of_type(status, ty)
        .iter()
        .any(|task| task["status"] == "paused" && task["fallback_reason"] == "budget_exceeded")
}

// Scenario (a) — L1: a chunking-config change + `reindex --force` re-embeds the
// new generation (docs/06 "reindex = 再 normalize / 再 embedding"). The smaller
// max_chars re-splits sections into chunks with fresh text (new text_hash), so
// no content vector can be reused — the enrichment must issue real embeddings.
// Before L1 the rebuild never called enrichment, so the new generation carried
// no embeddings and `index_status` falsely read fully enriched.
#[test]
fn ct3_l1_reindex_enriches_new_generation_embeddings() {
    let dir = indexed_scope_embed("mock");
    let before = tasks_of_type(&json_success_embed(&dir, "mock", &["status"]), "embedding").len();
    assert!(before > 0, "initial index must have embedding tasks");

    // Force a genuine re-split so the new chunks have text unseen by the embedding
    // store (otherwise the DB rebuild would reuse content vectors by text_hash).
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[chunking]\nstrategy = \"heading\"\nmax_chars = 10\n",
    )
    .unwrap();
    let out = json_success_embed(&dir, "mock", &["reindex", "--force", "--yes"]);
    assert_eq!(out["status"], "reindexed");

    let status = json_success_embed(&dir, "mock", &["status"]);
    let emb = tasks_of_type(&status, "embedding");
    assert!(
        emb.len() > before,
        "reindex must enqueue embeddings for the new generation (L1): {status}"
    );
    assert!(
        emb.iter().all(|task| task["status"] == "done"),
        "opted-in reindex must embed the new generation, not leave it pending: {status}"
    );
}

// Scenario (a) — L1 offline: with the embedding adapter configured but NOT
// opted-in, `reindex` must still enqueue the new generation's embedding tasks so
// `index_status` surfaces them as pending. Before L1 no tasks were created and
// `index_status` reported enriched_ratio = 1.0 / pending = 0 for them.
#[test]
fn ct3_l1_reindex_offline_surfaces_pending_embeddings_in_index_status() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("note.md"),
        "# ノート\n\n## 本文\n埋め込み保留の可視化テストです。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    // `--yes` records the opt-in rows with network_opt_in=false → embedding stays
    // offline (enqueue-only), the same as the markdownize online task.
    json_success_embed(&dir, "mock", &["index", "--yes"]);
    let before = tasks_of_type(&json_success_embed(&dir, "mock", &["status"]), "embedding").len();

    json_success_embed(&dir, "mock", &["reindex", "--force", "--yes"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let emb = tasks_of_type(&status, "embedding");
    assert!(
        emb.len() > before,
        "offline reindex must still enqueue new-generation embedding tasks (L1)"
    );
    assert!(
        emb.iter().any(|task| task["status"] == "pending"),
        "offline reindex must leave embedding tasks pending: {status}"
    );
    let search = json_success_embed(&dir, "mock", &["search", "本文 埋め込み"]);
    assert!(
        search["index_status"]["pending_enrichment_tasks"]
            .as_u64()
            .unwrap()
            > 0
    );
    assert!(search["index_status"]["enriched_ratio"].as_f64().unwrap() < 1.0);
}

// R11-2: the embedding enrichment DRIVEN inline by `index` auth-failed but the run
// reported exit 0 with no embedding keys — a silent enrichment failure. It must now
// exit 5 (docs/04 §5.6, user re-auth) with the full result JSON on stdout: local
// index succeeded (`status: indexed`), embedding failures disclosed, and the failure
// visible in `status` as well.
#[test]
fn r11_2_index_embedding_auth_error_exits_5() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("note.md"),
        "# ノート\n\n## 本文\n認証失敗の可視化テスト本文です。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    let indexed = json_code_stdout_embed(&dir, "auth_error", 5, &["index", "--approve"]);
    assert_eq!(
        indexed["status"], "indexed",
        "the local index still succeeds: {indexed}"
    );
    assert!(
        indexed["embedding_tasks_failed"].as_u64().unwrap() > 0,
        "the embedding auth failure must be disclosed on stdout: {indexed}"
    );
    let status = json_success_embed(&dir, "auth_error", &["status"]);
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .any(|task| task["status"] == "failed" && task["fallback_reason"] == "auth_error"),
        "status must show the failed embedding task: {status}"
    );
}

// Scenario (b) — L2: budget-exceeded Paused tasks are sticky under `batch resume`
// and only run under `--override-budget`, SYMMETRICALLY for markdownize and
// embedding. Before L2, `resume --override-budget` re-paused markdownize (the
// override never reached the executor's budget judgement) while embedding, being
// DB-driven, ran even a Paused task without any override.
#[test]
fn ct3_l2_budget_paused_resume_symmetry_across_adapters() {
    let dir = tempfile::tempdir().unwrap();
    // R9-2: the markdownize online task only exists for a non-text-native file, so
    // the both-adapters budget-pause symmetry is exercised with a PDF (its
    // deterministic baseline still produces chunks for the embedding adapter).
    fs::write(
        dir.path().join("budget.pdf"),
        fake_pdf(&["スティッキー一時停止の対称性テスト本文です。"]),
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    // A zero folder cap pauses BOTH adapters on budget.
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[budget]\nmonthly_usd_cap = 0\n",
    )
    .unwrap();
    // R11-2: the embedding enrichment DRIVEN inline by index budget-pauses here, so
    // index reports exit 6 (docs/04 §5.6) with its full result JSON still on stdout.
    let indexed = json_both_mock_code(&dir, &["index", "--approve"], 6);
    assert!(
        indexed["paused_tasks"].as_u64().unwrap() > 0,
        "index must disclose the budget-paused work: {indexed}"
    );
    let status = json_both_mock(&dir, &["status"]);
    assert!(
        is_budget_paused(&status, "markdownize"),
        "markdownize must be budget-paused: {status}"
    );
    assert!(
        is_budget_paused(&status, "embedding"),
        "embedding must be budget-paused: {status}"
    );

    // resume WITHOUT override → both remain sticky-Paused (symmetry).
    json_both_mock(&dir, &["batch", "resume"]);
    let status = json_both_mock(&dir, &["status"]);
    assert!(
        is_budget_paused(&status, "markdownize"),
        "markdownize must stay paused without override: {status}"
    );
    assert!(
        is_budget_paused(&status, "embedding"),
        "embedding must stay paused without override (L2 ii): {status}"
    );

    // resume WITH override → both execute to done (symmetry).
    json_both_mock(&dir, &["batch", "resume", "--override-budget"]);
    let status = json_both_mock(&dir, &["status"]);
    assert!(
        tasks_of_type(&status, "markdownize")
            .iter()
            .all(|task| task["status"] == "done"),
        "override must run markdownize (L2 i): {status}"
    );
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .all(|task| task["status"] == "done"),
        "override must run embedding: {status}"
    );
}

// Scenario (c) — L3: a short-hash `view` still resolves after a bare `kcs
// snapshot` advanced HEAD. The manual snapshot writes a raw-only tree (differs
// from the index's normalized tree, so HEAD genuinely advances) without
// refreshing the tree_entries projection; before L3 the short-hash resolver read
// a stale JSON projection filtered by the new HEAD and returned CONFIG-USAGE,
// while search (SQLite lazy projection) still succeeded — the asymmetry.
#[test]
fn ct3_l3_short_hash_resolves_after_bare_snapshot() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let chunk_hash = first_result(&search)["chunk_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    // Sanity: resolves before the snapshot.
    assert!(json_success(&dir, &["view", &chunk_hash])["text"]
        .as_str()
        .unwrap()
        .contains("3600"));
    // Advance HEAD via a bare snapshot (proves it is not a no-op).
    let snap = json_success(&dir, &["snapshot", "-m", "advance"]);
    assert_eq!(
        snap["status"], "created",
        "snapshot must advance HEAD: {snap}"
    );
    // L3: the same short-hash view still resolves.
    let viewed = json_success(&dir, &["view", &chunk_hash]);
    assert!(
        viewed["text"].as_str().unwrap().contains("3600"),
        "short-hash view must survive a bare snapshot (L3): {viewed}"
    );
}

// Scenario (d) — L4: an embedding adapter rides on its OWN opt-in, not the
// markdownize approval. A scope approved for markdownize only (backward-compat:
// no embedding approval row) must enqueue embedding tasks without ever calling
// the adapter; granting the embedding opt-in then embeds them.
#[test]
fn ct3_l4_embedding_without_own_optin_is_enqueue_only() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("adapter.md"),
        "# アダプタ\n\n## 本文\nアダプタ単位 opt-in のテスト本文です。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Approve WITHOUT the embedding seam → only the markdownize opt-in row exists.
    json_success(&dir, &["index", "--approve"]);
    // Now configure the embedding adapter (mock) and re-drive enrichment via
    // reindex. The scope has no embedding opt-in row → enqueue-only.
    json_success_embed(&dir, "mock", &["reindex", "--force", "--yes"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let emb = tasks_of_type(&status, "embedding");
    assert!(!emb.is_empty(), "embedding tasks must be enqueued");
    assert!(
        emb.iter().all(|task| task["status"] == "pending"),
        "embedding without its own opt-in must stay enqueue-only (L4): {status}"
    );

    // Grant the embedding opt-in explicitly → the same chunks now embed.
    json_success_embed(&dir, "mock", &["index", "--approve"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .any(|task| task["status"] == "done"),
        "granting the embedding opt-in must embed the pending tasks (L4): {status}"
    );
}

// ===========================================================================
// Exploratory-audit fix regression tests (tasks/step3-bughunt-fixes.md, M2-M8
// + acceptance scenarios (b)-(f) and the two previously-untested error codes).
// ===========================================================================

// M2 + acceptance (b): `kcs view` without --json prints the chunk BODY, not just
// the "viewed" status line.
#[test]
fn m2_view_non_json_prints_chunk_body() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"]
        .as_str()
        .unwrap()
        .to_owned();
    let stdout = kcs(&dir, &["view", &uri])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let text = String::from_utf8(stdout).unwrap();
    assert!(
        text.contains("トークン TTL"),
        "view (non --json) must print the body, got: {text}"
    );
    assert_ne!(text.trim(), "viewed");
}

// M3 + acceptance (c): a raw_hash short form for a normal multi-heading file
// (auth.md has two `##` sections → two chunks sharing one raw_hash) resolves as
// raw instead of failing "ambiguous". `open` uses the raw path directly.
#[test]
fn m3_short_raw_hash_open_succeeds_for_multi_heading_file() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let raw_hash = first_result(&search)["evidence_pointer"]["raw_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    // Two chunks share this raw_hash; the old code counted chunk matches and
    // rejected this as ambiguous.
    let opened = json_success(&dir, &["open", &raw_hash]);
    assert_eq!(opened["status"], "opened");
    assert_eq!(opened["object_type"], "raw");
    assert!(opened["path"].as_str().unwrap().ends_with("auth.md"));
}

// M3: a chunk_hash short form still resolves to that chunk (the other kind).
#[test]
fn m3_short_chunk_hash_view_resolves_chunk() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let chunk_hash = first_result(&search)["chunk_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    let viewed = json_success(&dir, &["view", &chunk_hash]);
    assert!(viewed["text"].as_str().unwrap().contains("トークン TTL"));
}

// M4 + acceptance (d): a scope whose sqlite.db is corrupt (garbage bytes, which
// `Connection::open` accepts lazily) is excluded from a multi-scope search with
// reason "index_corrupt" while the healthy scope's results survive (exit 3), not
// exploded into an exit-2 that drops everything.
#[test]
fn m4_corrupt_sqlite_scope_excluded_multiscope_exit_3() {
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

    // Corrupt scope b's index in place (still a readable file, so b is discovered).
    fs::write(
        b.join(".kcs/index/sqlite.db"),
        b"this is not a sqlite database",
    )
    .unwrap();

    // A partial-failure search writes results to STDOUT with exit 3.
    let output = Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .args(["search", "alphaunique", "--json"])
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let search: Value = serde_json::from_slice(&output).unwrap();
    assert!(!search["results"].as_array().unwrap().is_empty());
    assert_eq!(search["searched_scopes"].as_array().unwrap().len(), 1);
    let excluded = search["excluded_scopes"].as_array().unwrap();
    assert_eq!(excluded.len(), 1);
    assert!(excluded[0]["scope_path"].as_str().unwrap().ends_with("/b"));
    assert_eq!(excluded[0]["reason"], "index_corrupt");
}

// M4: a single corrupt-index scope lands on the existing VEC-UNAVAIL branch
// (exit 1) rather than an exit-2 config-schema lie, with reason "index_corrupt".
#[test]
fn m4_single_corrupt_sqlite_is_vec_unavailable() {
    let dir = indexed_scope();
    fs::write(
        dir.path().join(".kcs/index/sqlite.db"),
        b"not a sqlite database at all",
    )
    .unwrap();
    let err = json_failure(&dir, &["search", "認証仕様"], 1);
    assert_eq!(err["error_code"], "KCS-E-SEARCH-VEC-UNAVAIL-001");
    assert_eq!(
        err["context"]["excluded_scopes"][0]["reason"],
        "index_corrupt"
    );
}

// M5 + acceptance (e): two consecutive `view`s (and opens) that fall back to the
// read-only CAS open-cache both succeed — the second must reuse the cache, not
// `fs::copy` onto the read-only file (EACCES).
#[test]
fn m5_repeated_view_via_cas_cache_is_idempotent() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"]
        .as_str()
        .unwrap()
        .to_owned();
    // Remove the working-tree file so resolution must expand the CAS raw object
    // into the read-only open cache.
    fs::remove_file(dir.path().join("auth.md")).unwrap();

    let first = json_success(&dir, &["view", &uri]);
    assert!(first["text"].as_str().unwrap().contains("トークン TTL"));
    // The second view previously failed with EACCES (fs::copy onto read-only cache).
    let second = json_success(&dir, &["view", &uri]);
    assert!(second["text"].as_str().unwrap().contains("トークン TTL"));
    // open twice as well.
    let opened1 = json_success(&dir, &["open", &uri]);
    assert_eq!(opened1["temporary"], true);
    let opened2 = json_success(&dir, &["open", &uri]);
    assert_eq!(opened2["temporary"], true);
    assert!(Path::new(opened2["path"].as_str().unwrap()).is_file());
}

// M6: a tampered Evidence Pointer whose raw_hash names file B but whose
// chunk_hash resolves to file A's chunk is rejected — the resolver requires the
// chunk row to bind to the pointer's (raw_hash, tool_profile_hash) identity.
#[test]
fn m6_tampered_pointer_identity_mismatch_is_rejected() {
    let dir = indexed_scope();
    let auth = json_success(&dir, &["search", "トークン TTL 3600"]);
    let pointer_a = first_result(&auth)["evidence_pointer"].clone();
    let ranking = json_success(&dir, &["search", "RRF 定数 k 60"]);
    let raw_hash_b = first_result(&ranking)["evidence_pointer"]["raw_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_ne!(pointer_a["raw_hash"].as_str().unwrap(), raw_hash_b);

    // Keep A's chunk_hash / commit, but claim B's raw_hash: "raw is B, body is A".
    let mut tampered = pointer_a.clone();
    tampered["raw_hash"] = serde_json::json!(raw_hash_b);
    let err = json_failure(&dir, &["view", &tampered.to_string()], 4);
    assert_eq!(err["error_code"], "KCS-E-EVIDENCE-POINTER-INVALID-001");
    // The unmodified pointer still resolves (no over-rejection of valid pointers).
    let ok = json_success(&dir, &["view", &pointer_a.to_string()]);
    assert!(ok["text"].as_str().unwrap().contains("トークン TTL"));
}

// M7: an `object` URI dispatches to the CORRECT CAS type directory. An image
// object lives only under objects/images; it resolves via object/image/<hash>
// and is NOT found via object/raw/<hash> (which previously mis-served all types).
#[test]
fn m7_object_uri_dispatches_by_type_directory() {
    use kcs_core::cas::hash_bytes;
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let scope_id = first_result(&search)["evidence_pointer"]["scope_id"]
        .as_str()
        .unwrap()
        .to_owned();
    let kcs_dir = dir.path().join(".kcs");
    let bytes = b"fake-embedded-image-bytes";
    let image_hash = hash_bytes(bytes);
    let image_obj = object_path(&kcs_dir, "images", &image_hash);
    fs::create_dir_all(image_obj.parent().unwrap()).unwrap();
    fs::write(&image_obj, bytes).unwrap();

    // Correct dispatch: image resolves from objects/images.
    let opened = json_success(
        &dir,
        &[
            "open",
            &format!("kcs://{scope_id}/object/image/{image_hash}"),
        ],
    );
    assert_eq!(opened["object_type"], "image");
    assert!(Path::new(opened["path"].as_str().unwrap()).is_file());
    // Same hash under object/raw must NOT resolve (the bytes live only in images).
    json_failure(
        &dir,
        &["open", &format!("kcs://{scope_id}/object/raw/{image_hash}")],
        4,
    );
    // `normalized` is path-named (not single-hash addressable) -> invalid usage.
    json_failure(
        &dir,
        &[
            "open",
            &format!("kcs://{scope_id}/object/normalized/{image_hash}"),
        ],
        2,
    );
}

// M8 + acceptance (f): a negative budget cap in the USER (device) config.toml is
// rejected at startup with exit 2, exactly like the folder config already was.
#[test]
fn m8_user_config_negative_budget_cap_rejected() {
    let dir = tempfile::tempdir().unwrap();
    kcs(&dir, &["init"]).assert().success();
    let user_config = dir.path().join(".test-config/kcs/config.toml");
    fs::create_dir_all(user_config.parent().unwrap()).unwrap();
    fs::write(&user_config, "[budget]\nmonthly_usd_cap = -5\n").unwrap();
    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

// M8: a valid user config with a non-negative cap passes (no over-rejection).
#[test]
fn m8_user_config_valid_budget_cap_accepted() {
    let dir = tempfile::tempdir().unwrap();
    kcs(&dir, &["init"]).assert().success();
    let user_config = dir.path().join(".test-config/kcs/config.toml");
    fs::create_dir_all(user_config.parent().unwrap()).unwrap();
    fs::write(&user_config, "[budget]\nmonthly_usd_cap = 25\n").unwrap();
    json_success(&dir, &["status"]);
}

// Minor: previously-untested error code KCS-E-CONFIG-NOT-IMPLEMENTED-001
// (time-travel search flags are a later step).
#[test]
fn minor_not_implemented_error_code_is_emitted() {
    let dir = indexed_scope();
    // R9-6: KCS-E-CONFIG-NOT-IMPLEMENTED-001 exits 1 (canonical
    // `KcsError::not_implemented`), unified across every not-implemented path.
    let err = json_failure(&dir, &["search", "認証仕様", "--at", "HEAD"], 1);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-NOT-IMPLEMENTED-001");
}

/// R9-6: every KCS-E-CONFIG-NOT-IMPLEMENTED-001 path exits with the SAME class
/// (1, canonical `KcsError::not_implemented`). Before the fix `log --at` exited 1
/// while `search --at`, `reindex --at` and `repair --verify-objects` exited 2, so
/// an agent classifying by exit code saw one error_code split across two classes.
#[test]
fn r9_6_not_implemented_exit_code_is_uniform() {
    let dir = indexed_scope();
    for args in [
        vec!["search", "認証仕様", "--at", "HEAD"],
        vec!["reindex", "--force", "--yes", "--at", "HEAD"],
        vec!["repair", "--verify-objects"],
        vec!["log", "--at", "HEAD"],
    ] {
        let err = json_failure(&dir, &args, 1);
        assert_eq!(
            err["error_code"], "KCS-E-CONFIG-NOT-IMPLEMENTED-001",
            "args {args:?} must map to the not-implemented code at exit 1"
        );
    }
}

// Minor: previously-untested error code KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001 — a
// scope_id registered against two distinct .kcs with the same last_seen_at.
#[test]
fn minor_evidence_scope_ambiguous_error_code_is_emitted() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    let elsewhere = parent.path().join("elsewhere");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::create_dir_all(&elsewhere).unwrap();
    fs::write(
        a.join("auth.md"),
        "# 認証仕様\n\n## API Token\nトークン TTL は 3600 秒です。\n",
    )
    .unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    let search = json_success_path(&a, &data_home, &["search", "トークン TTL 3600"]);
    let pointer = first_result(&search)["evidence_pointer"].clone();
    let scope_id = pointer["scope_id"].as_str().unwrap().to_owned();

    // Init b, then give its scope.json the SAME scope_id as a (a duplicate正本).
    json_success_path(&b, &data_home, &["init"]);
    let b_scope_path = b.join(".kcs/scope.json");
    let mut b_scope: Value =
        serde_json::from_str(&fs::read_to_string(&b_scope_path).unwrap()).unwrap();
    b_scope["scope_id"] = serde_json::json!(scope_id);
    fs::write(
        &b_scope_path,
        serde_json::to_string_pretty(&b_scope).unwrap(),
    )
    .unwrap();

    // Register both .kcs under the shared scope_id with the SAME last_seen_at,
    // newer than the index-time registration so they form the unique newest set
    // (both resolve to distinct .kcs -> ambiguous winner).
    let registry = RegistryDb::open(registry_path(&data_home)).unwrap();
    for root in [&a, &b] {
        registry
            .upsert(&RegistryEntry {
                scope_id: scope_id.clone(),
                kcs_path: root.join(".kcs").display().to_string(),
                root_path: root.display().to_string(),
                participates_in_global_search: true,
                indexed: true,
                last_seen_at: "2099-01-01T00:00:00Z".to_owned(),
            })
            .unwrap();
    }

    // Force registry resolution (broken scope_path hint) from a neutral cwd.
    let mut orphan = pointer.clone();
    orphan["scope_path"] = serde_json::json!(parent.path().join("gone/.kcs").display().to_string());
    let (code, err) = run_json(&elsewhere, &data_home, &["view", &orphan.to_string()]);
    assert_eq!(code, 4, "ambiguous scope must fail: {err}");
    assert_eq!(err["error_code"], "KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001");
}

// ===========================================================================
// Second exploratory-audit round (tasks/step3-bughunt2-fixes.md, N1-N8):
// acceptance scenarios (a)-(f). Scenario (g) (O(N²) chunking) lives as a timing
// proxy in kcs-index/src/chunking.rs (n6_chunking_scales_linearly...).
// ===========================================================================

// (a) / N1: a Tier B (candidate-secret) file is ingested locally but its online
// send (embedding here) is HELD until an explicit `--send-secrets` approval, and
// stays visible in `kcs status` quarantine + as a held task the whole time.
#[test]
fn n1_tier_b_online_send_held_until_send_secrets() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("notes.md"),
        "# Notes\n\n## Body\n通常の本文です。十分な長さの段落を含みます。\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("api_secret.md"),
        "# 秘密メモ\n\n## Body\n秘匿候補ファイルの本文です。十分な長さの段落。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);

    let status = json_success_embed(&dir, "mock", &["status"]);
    let secret_embed: Vec<_> = tasks_of_type(&status, "embedding")
        .into_iter()
        .filter(|task| task["input_path"] == "api_secret.md")
        .collect();
    assert!(
        !secret_embed.is_empty(),
        "Tier B file must produce an embedding task: {status}"
    );
    assert!(
        secret_embed
            .iter()
            .all(|task| task["status"] == "paused"
                && task["fallback_reason"] == "secrets_tier_b_hold"),
        "Tier B embedding must be held, not sent: {status}"
    );
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .any(|task| { task["input_path"] == "notes.md" && task["status"] == "done" }),
        "non-secret embedding must still execute: {status}"
    );
    assert!(
        status["quarantine"]
            .as_array()
            .unwrap()
            .iter()
            .any(|q| { q["path"] == "api_secret.md" && q["reason"] == "secrets_tier_b" }),
        "Tier B must be recorded in quarantine: {status}"
    );

    // Explicit approval lifts the hold → the Tier B chunks now embed.
    json_success_embed(
        &dir,
        "mock",
        &["index", "--approve", "--online", "--send-secrets"],
    );
    let status = json_success_embed(&dir, "mock", &["status"]);
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .any(|task| { task["input_path"] == "api_secret.md" && task["status"] == "done" }),
        "--send-secrets must release and embed the Tier B chunks: {status}"
    );
}

// (b) / N2: a manual `kcs snapshot` must not bake Tier A secrets into the CAS or
// the latest tree.
#[test]
fn n2_manual_snapshot_excludes_tier_a() {
    use kcs_core::cas::hash_bytes;
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    fs::write(dir.path().join(".env"), "TOKEN=supersecret").unwrap();
    kcs(&dir, &["init"]).assert().success();

    let snap = json_success(&dir, &["snapshot", "-m", "manual"]);
    assert_eq!(
        snap["status"], "created",
        "snapshot must commit a.txt: {snap}"
    );
    let tree = json_success(&dir, &["inspect", snap["tree_hash"].as_str().unwrap()]);
    assert!(
        !tree["entries"]
            .as_array()
            .unwrap()
            .iter()
            .any(|entry| entry["path"] == ".env"),
        "manual snapshot must not put .env in the tree: {tree}"
    );
    let env_hash = hash_bytes(b"TOKEN=supersecret");
    assert!(
        !object_path(&dir.path().join(".kcs"), "raw", &env_hash).exists(),
        "manual snapshot must not write .env plaintext to objects/raw"
    );
}

// (c) / N3: errors.jsonl must mask the `path` field under redact_logs (default on).
#[test]
fn n3_errors_jsonl_redacts_path() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    kcs(&dir, &["init"]).assert().success();
    fs::write(dir.path().join(".kcs/tasks.jsonl"), "{ not json\n").unwrap();
    json_failure(&dir, &["status"], 4);
    let errors = fs::read_to_string(dir.path().join(".test-data/kcs/logs/errors.jsonl")).unwrap();
    let last: Value = serde_json::from_str(errors.lines().last().unwrap()).unwrap();
    assert_eq!(
        last["context"]["path"], "[redacted]",
        "errors.jsonl must redact path under redact_logs: {last}"
    );
}

// (d) / N4: `diff` / `tag <commit>` reject path-traversal operands with exit 2
// instead of turning `refs/tags`.join into an out-of-scope existence oracle.
#[test]
fn n4_diff_and_tag_reject_traversal_operands() {
    let dir = indexed_scope();
    let err = json_failure(&dir, &["diff", "../../../etc/passwd", "HEAD"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");
    let err = json_failure(&dir, &["tag", "mytag", "../../../etc/passwd"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");
}

// F4: a tag whose NAME is `HEAD` or a `sha256:` hash is permanently shadowed by
// `resolve_commit` (which resolves those forms before ever consulting
// refs/tags), so creating one must be rejected instead of returning a dead-ref
// "success". Ordinary tag names are unaffected.
#[test]
fn f4_tag_rejects_reserved_head_and_hash_names() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# T\n\n## S\nbody text here.\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    // A commit must exist so a legitimate tag (resolving HEAD) can be created.
    json_success(&dir, &["snapshot", "-m", "first"]);

    // Reserved name `HEAD`: rejected before any ref is written.
    let err = json_failure(&dir, &["tag", "HEAD"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");
    assert!(!dir.path().join(".kcs/refs/tags/HEAD").exists());

    // Reserved name in `sha256:<64hex>` form: also rejected.
    let hash_name = format!("sha256:{}", "a".repeat(64));
    let err = json_failure(&dir, &["tag", &hash_name], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");

    // A normal tag name still resolves HEAD and is created.
    let ok = json_success(&dir, &["tag", "v1"]);
    assert!(
        ok["commit_hash"].as_str().is_some(),
        "tag v1 should succeed: {ok}"
    );
    assert!(dir.path().join(".kcs/refs/tags/v1").exists());
}

// (e) / N5: after `reindex --force`, a pointer that keeps the OLD commit but
// splices in a NEW-generation chunk_hash is rejected (gen binding), while the
// untampered old pointer still resolves.
#[test]
fn n5_pointer_rejects_generation_mixing_after_reindex() {
    let dir = indexed_scope();
    let before = json_success(&dir, &["search", "トークン TTL 3600"]);
    let old_pointer = first_result(&before)["evidence_pointer"].clone();
    json_success(&dir, &["reindex", "--force", "--yes"]);
    let after = json_success(&dir, &["search", "トークン TTL 3600"]);
    let new_chunk_hash = first_result(&after)["evidence_pointer"]["chunk_hash"].clone();
    assert_ne!(
        old_pointer["chunk_hash"], new_chunk_hash,
        "reindex --force must produce a new-generation chunk_hash"
    );
    let mut tampered = old_pointer.clone();
    tampered["chunk_hash"] = new_chunk_hash;
    let err = json_failure(&dir, &["view", &tampered.to_string()], 4);
    assert_eq!(
        err["error_code"], "KCS-E-EVIDENCE-POINTER-INVALID-001",
        "generation-mixing pointer must be rejected (N5)"
    );
    let ok = json_success(&dir, &["view", &old_pointer.to_string()]);
    assert!(ok["text"].as_str().unwrap().contains("トークン TTL"));
}

// (f) / N7: a single-shot `--online` drives embedding enrichment (previously only
// markdownize honored the flag; embedding stayed Pending).
#[test]
fn n7_online_flag_drives_embedding_enrichment() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("notes.md"),
        "# Notes\n\n## Body\n通常本文の十分な長さのテキストです。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed(&dir, "mock", &["index", "--yes", "--online"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .any(|task| task["status"] == "done"),
        "single-shot --online must execute embedding (N7): {status}"
    );
}

// ===========================================================================
// Third exploratory-audit round (tasks/step3-bughunt3-fixes.md, O1-O7):
// acceptance scenarios (a)-(f).
// ===========================================================================

// (a) / O1: a cursor minted for another scope cannot bypass a --scope restriction
// (no secret leak; the frozen vault scope is excluded scope_restriction_mismatch),
// and a tampered/forged cursor fails HMAC verification (KCS-E-SEARCH-CURSOR-001).
#[test]
fn o1_cursor_scope_restriction_and_signature() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let safe = parent.path().join("safe");
    let vault = parent.path().join("vault");
    fs::create_dir_all(&safe).unwrap();
    fs::create_dir_all(&vault).unwrap();
    fs::write(
        safe.join("safe.md"),
        "# 公開\n\n## Body\n公開情報の本文です。十分な長さの段落を含みます。\n",
    )
    .unwrap();
    // Same query terms as CT3-CURSOR (認証仕様) so one query yields several chunks
    // (=> a paging cursor), plus a secret marker in the body.
    fs::write(
        vault.join("auth.md"),
        "# 認証仕様\n\n## API Token\nトークン TTL は 3600 秒です。秘密鍵 TOP-SECRET-KEY-XYZ を含みます。\n\n## Scopes\nスコープは read write admin です。\n",
    )
    .unwrap();
    fs::write(
        vault.join("ranking.md"),
        "# 検索ランキング\n\n## RRF 融合\nRRF の定数 k=60 を使います。\n\n## MMR 多様化\nMMR の係数 lambda 0.7 で多様化します。\n",
    )
    .unwrap();
    json_success_path(&safe, &data_home, &["init"]);
    json_success_path(&vault, &data_home, &["init"]);
    json_success_path(&safe, &data_home, &["index", "--approve"]);
    json_success_path(&vault, &data_home, &["index", "--approve"]);

    // Legitimate owner pages their own vault: --scope <vault> freezes the cursor's
    // scope set to the vault.
    let first = json_success_path(
        &vault,
        &data_home,
        &[
            "search",
            "認証仕様",
            "--scope",
            vault.to_str().unwrap(),
            "--limit",
            "1",
        ],
    );
    let cursor = first["paging"]["next_cursor"]
        .as_str()
        .expect("vault page 1 must yield a cursor")
        .to_owned();

    // Attacker in the safe scope replays the vault cursor but restricts --scope .
    // (their own scope). O1(a): the vault scope is intersected out — no leak.
    let (code, resp) = run_json(
        &safe,
        &data_home,
        &[
            "search",
            "認証仕様",
            "--scope",
            ".",
            "--cursor",
            &cursor,
            "--limit",
            "5",
        ],
    );
    let dump = resp.to_string();
    assert!(
        !dump.contains("TOP-SECRET-KEY-XYZ"),
        "a cursor must not leak another scope's content across a --scope restriction: {dump}"
    );
    assert_eq!(
        code, 4,
        "every cursor scope excluded => all-failed exit 4: {resp}"
    );
    let excluded = resp["context"]["excluded_scopes"].as_array().unwrap();
    assert!(
        excluded
            .iter()
            .any(|entry| entry["reason"] == "scope_restriction_mismatch"),
        "the restricted vault scope must be excluded with scope_restriction_mismatch: {resp}"
    );

    // O1(b): a forged cursor (payload byte flipped) fails signature verification.
    let (payload, signature) = cursor.rsplit_once('.').unwrap();
    let mut forged = payload.to_owned();
    let last = forged.pop().unwrap();
    forged.push(if last == 'A' { 'B' } else { 'A' });
    let forged = format!("{forged}.{signature}");
    let (code, err) = run_json(
        &vault,
        &data_home,
        &["search", "認証仕様", "--cursor", &forged, "--limit", "5"],
    );
    assert_eq!(code, 2, "a forged cursor is a usage error: {err}");
    assert_eq!(err["error_code"], "KCS-E-SEARCH-CURSOR-001");
}

// (b) / O2: `--text` must never send the query to the embedding endpoint, while a
// vector-resolving search does (proving the send seam works — pair-discriminated).
#[test]
fn o2_text_search_never_sends_query_embedding() {
    let dir = indexed_scope_embed("mock");
    let trace = dir.path().join("query-embed-trace.log");

    // --text: the query embedding must NOT be computed/sent.
    Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(dir.path())
        .env("XDG_CONFIG_HOME", dir.path().join(".test-config"))
        .env("XDG_DATA_HOME", dir.path().join(".test-data"))
        .env("XDG_CACHE_HOME", dir.path().join(".test-cache"))
        .env(TEST_ADOPTED_EMBEDDING_ENV, "mock")
        .env("KCS_TEST_QUERY_EMBED_TRACE", &trace)
        .args(["search", "認証仕様 トークン", "--text", "--json"])
        .assert()
        .success();
    assert!(
        !trace.exists(),
        "--text must not reach the embedding send path (trace file was written)"
    );

    // auto → hybrid: the same seam DOES send, so the trace appears (discriminator).
    Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(dir.path())
        .env("XDG_CONFIG_HOME", dir.path().join(".test-config"))
        .env("XDG_DATA_HOME", dir.path().join(".test-data"))
        .env("XDG_CACHE_HOME", dir.path().join(".test-cache"))
        .env(TEST_ADOPTED_EMBEDDING_ENV, "mock")
        .env("KCS_TEST_QUERY_EMBED_TRACE", &trace)
        .args(["search", "認証仕様 トークン", "--json"])
        .assert()
        .success();
    assert!(
        trace.exists() && fs::read_to_string(&trace).unwrap().contains("認証仕様"),
        "a vector-resolving search must send the query embedding"
    );
}

// (c) / O3: `batch resume` now holds the folder store lock end-to-end, so a
// concurrent holder makes it fail fast (KCS-E-STORE-LOCKED-001, exit 3) rather
// than racing tasks.jsonl / the ledger into a double send.
#[test]
fn o3_batch_resume_takes_the_store_lock() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.md"), "# A\n\n## B\n本文です。\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    // A live (non-stale) lock held by "another process".
    fs::write(dir.path().join(".kcs/.lock"), "{}").unwrap();
    let err = json_failure(&dir, &["batch", "resume"], 3);
    assert_eq!(err["error_code"], "KCS-E-STORE-LOCKED-001");
}

// (d) / O4: a crafted PDF whose multibyte char straddles the /Page lookahead
// window indexes cleanly (no char-boundary panic / exit 101, no body dump).
#[test]
fn o4_crafted_multibyte_pdf_does_not_panic() {
    let dir = tempfile::tempdir().unwrap();
    // "/PageXあ": the 3-byte あ sits across the +8 byte window from "/Page"; the
    // old str slice panicked here. `BT` gives the file a text layer.
    let mut pdf = Vec::new();
    pdf.extend_from_slice(b"%PDF-1.4\nBT (hi) Tj ET\n");
    pdf.extend_from_slice(
        "/PageXあ /Type /Page trailing padding to extend the length\n".as_bytes(),
    );
    pdf.extend_from_slice(b"%%EOF\n");
    fs::write(dir.path().join("crafted.pdf"), &pdf).unwrap();
    kcs(&dir, &["init"]).assert().success();
    let assert = kcs(&dir, &["index", "--approve", "--json"]).assert();
    let code = assert.get_output().status.code().unwrap();
    assert_ne!(code, 101, "crafted PDF must not panic (exit 101)");
    assert_eq!(code, 0, "crafted PDF must index cleanly (exit 0)");
}

// (e) / O5: a 0-chunk scope (empty folder) indexes cleanly (exit 0), instead of a
// half-initialized "commit but no index" that fails every re-index with exit 2.
#[test]
fn o5_empty_scope_indexes_with_exit_0() {
    let dir = tempfile::tempdir().unwrap();
    kcs(&dir, &["init"]).assert().success();
    kcs(&dir, &["index", "--approve", "--json"])
        .assert()
        .success();
    // Re-index is also clean (no stuck "commit, no index" state).
    kcs(&dir, &["index", "--approve", "--json"])
        .assert()
        .success();
}

// (f) / O6: a too-short `sha256:` operand is a usage error (exit 2), not a slice
// panic in cas_object_path's digest[0..2].
#[test]
fn o6_short_sha256_operand_is_usage_error() {
    let dir = indexed_scope();
    let err = json_failure(&dir, &["open", "sha256:a"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");
    let err = json_failure(&dir, &["view", "sha256:ZZZZ"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");
}

// (g) / O7: a scope_id collision (a wholesale `.kcs` copy) makes a cursor replay
// ambiguous — detected the same way the Evidence path is
// (KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001), not silently pinned to one copy.
#[test]
fn o7_cursor_replay_detects_scope_id_collision() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(
        a.join("auth.md"),
        "# 認証仕様\n\n## API Token\nトークン TTL は 3600 秒です。\n\n## Scopes\nスコープは read write admin です。\n",
    )
    .unwrap();
    fs::write(
        a.join("ranking.md"),
        "# 検索ランキング\n\n## RRF 融合\nRRF の定数 k=60 を使います。\n\n## MMR 多様化\nMMR の係数 lambda 0.7 で多様化します。\n",
    )
    .unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    let first = json_success_path(&a, &data_home, &["search", "認証仕様", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"]
        .as_str()
        .expect("page 1 must yield a cursor")
        .to_owned();
    let scope_id = first["searched_scopes"].as_array().unwrap()[0]["scope_id"]
        .as_str()
        .unwrap()
        .to_owned();

    // Copy a's identity into b and register both under the shared scope_id with the
    // SAME newest last_seen_at → the cursor's scope_id now resolves to two .kcs.
    json_success_path(&b, &data_home, &["init"]);
    let b_scope_path = b.join(".kcs/scope.json");
    let mut b_scope: Value =
        serde_json::from_str(&fs::read_to_string(&b_scope_path).unwrap()).unwrap();
    b_scope["scope_id"] = serde_json::json!(scope_id);
    fs::write(
        &b_scope_path,
        serde_json::to_string_pretty(&b_scope).unwrap(),
    )
    .unwrap();
    let registry = RegistryDb::open(registry_path(&data_home)).unwrap();
    for root in [&a, &b] {
        registry
            .upsert(&RegistryEntry {
                scope_id: scope_id.clone(),
                kcs_path: root.join(".kcs").display().to_string(),
                root_path: root.display().to_string(),
                participates_in_global_search: true,
                indexed: true,
                last_seen_at: "2099-01-01T00:00:00Z".to_owned(),
            })
            .unwrap();
    }

    let (code, err) = run_json(&a, &data_home, &["search", "認証仕様", "--cursor", &cursor]);
    assert_eq!(code, 4, "ambiguous cursor scope must fail: {err}");
    assert_eq!(err["error_code"], "KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001");
}

// ---------------------------------------------------------------------------
// Step 3 bug-hunt round 4 (P1-P9) regression tests.
// ---------------------------------------------------------------------------

/// P1: a poisoned tasks.jsonl whose online markdownize task points outside the
/// scope (absolute path / `..` traversal) must be rejected at read time
/// (KCS-E-STORE-PATH-001, exit 2) so `batch resume` never reads the external
/// file or sends it to the online adapter.
#[test]
fn p1_batch_resume_rejects_out_of_scope_task_input_path() {
    for poison_path in [
        "/etc/hosts",
        "../../../../../../etc/hosts",
        "sub/secret.txt",
    ] {
        let dir = tempfile::tempdir().unwrap();
        // R9-2: a PDF so `index --approve` enqueues a real online task whose
        // output_ref the poison row reuses (text-native files enqueue none).
        fs::write(dir.path().join("a.pdf"), fake_pdf(&["hello world content"])).unwrap();
        kcs(&dir, &["init"]).assert().success();
        // Records the online opt-in and enqueues legitimate tasks.
        json_success(&dir, &["index", "--approve"]);
        let online_output_ref = first_online_output_ref(&json_success(&dir, &["status"]));
        // Append a pending online markdownize task escaping the scope.
        let tasks = dir.path().join(".kcs/tasks.jsonl");
        let poison = serde_json::json!({
            "task_id": "task_poison",
            "type": "markdownize",
            "mode": "full",
            "input_path": poison_path,
            "input_hash": format!("sha256:{}", "0".repeat(64)),
            "previous_raw_hash": null,
            "parent_run_id": null,
            "changed_unit_keys": [],
            "output_ref": online_output_ref,
            "unit_keys": null,
            "status": "pending",
            "attempts": 0,
            "next_retry_at": null,
            "deadline": null,
            "heartbeat_at": null,
            "fallback_reason": null,
            "created_at": "2026-04-25T12:00:00Z"
        });
        let mut line = serde_json::to_string(&poison).unwrap();
        line.push('\n');
        let mut existing = fs::read_to_string(&tasks).unwrap_or_default();
        existing.push_str(&line);
        fs::write(&tasks, existing).unwrap();

        // `batch resume` must reject before reading the external file. The mock
        // The online markdownize seam is set so that if the guard were missing
        // the task would execute, proving the guard blocks it.
        let err = kcs(&dir, &["batch", "resume"])
            .env(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")
            .arg("--json")
            .assert()
            .code(2)
            .get_output()
            .stderr
            .clone();
        let err: Value = serde_json::from_slice(&err).unwrap();
        assert_eq!(
            err["error_code"], "KCS-E-STORE-PATH-001",
            "poison {poison_path:?} must be rejected"
        );
        // The offending task never completed (rejection happens at read time,
        // before any adapter call), so no normalized output ref was recorded.
        let tasks_after = fs::read_to_string(&tasks).unwrap();
        assert!(!tasks_after.contains("normalized_output"));
    }
}

/// P4: with `redact_logs` (default true), a corrupt store file error must not
/// leak the scope's absolute path into errors.jsonl — neither in the context
/// (N3) nor in the message (the P4 gap: the `corrupt store file at {path}`
/// Display embedded the path verbatim).
#[test]
fn p4_corrupt_store_error_message_has_no_absolute_path() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.txt"), "hi").unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);
    // Corrupt tasks.jsonl so the next read raises KCS-E-STORE-CORRUPT-001.
    let tasks = dir.path().join(".kcs/tasks.jsonl");
    let mut contents = fs::read_to_string(&tasks).unwrap_or_default();
    contents.push_str("this is not valid json{{{\n");
    fs::write(&tasks, contents).unwrap();

    kcs(&dir, &["status"]).assert().failure();

    let errors = fs::read_to_string(dir.path().join(".test-data/kcs/logs/errors.jsonl")).unwrap();
    let record = errors
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .find(|value| value["code"] == "KCS-E-STORE-CORRUPT-001")
        .expect("a corrupt-store error must be logged");
    // The scope's absolute path (the tempdir) must not appear in message or context.
    let scope_abs = dir.path().to_string_lossy().into_owned();
    assert!(
        !record["message"].as_str().unwrap().contains(&scope_abs),
        "message leaked an absolute path: {}",
        record["message"]
    );
    assert!(!serde_json::to_string(&record["context"])
        .unwrap()
        .contains(&scope_abs));
    // The path token is masked in the message, not just dropped.
    assert!(record["message"].as_str().unwrap().contains("[redacted]"));
    assert_eq!(record["context"]["path"], "[redacted]");
}

/// P2: after `kcs init` the `.kcs` tree and the device data dir are owner-only
/// (0700) so document bytes / usage data are not world/group-readable.
#[cfg(unix)]
#[test]
fn p2_init_restricts_kcs_and_data_dir_to_owner() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.txt"), "secret-ish bytes").unwrap();
    kcs(&dir, &["init"]).assert().success();

    let kcs_mode = fs::metadata(dir.path().join(".kcs"))
        .unwrap()
        .permissions()
        .mode()
        & 0o777;
    assert_eq!(kcs_mode, 0o700, ".kcs must be 0700, got {kcs_mode:o}");

    // register_scope runs during init and creates $XDG_DATA_HOME/kcs.
    let data_kcs = dir.path().join(".test-data/kcs");
    let data_mode = fs::metadata(&data_kcs).unwrap().permissions().mode() & 0o777;
    assert_eq!(data_mode, 0o700, "data dir must be 0700, got {data_mode:o}");
}

/// P3: a plaintext `plain:` API key in a group/world-readable tools.toml records
/// a level=warn observation (KCS-E-ADAPTER-TOOLS-PERM-001) without blocking
/// startup; a 0600 tools.toml records nothing.
#[cfg(unix)]
#[test]
fn p3_plain_auth_tools_toml_permission_warning() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.txt"), "x").unwrap();
    kcs(&dir, &["init"]).assert().success();

    let tools_dir = dir.path().join(".test-config/kcs");
    fs::create_dir_all(&tools_dir).unwrap();
    let tools = tools_dir.join("tools.toml");
    fs::write(&tools, "[markdown]\nauth = \"plain:sk-secret-key\"\n").unwrap();
    let errors = dir.path().join(".test-data/kcs/logs/errors.jsonl");

    // 0644 -> warn recorded, startup still succeeds (exit 0).
    fs::set_permissions(&tools, fs::Permissions::from_mode(0o644)).unwrap();
    kcs(&dir, &["status"]).assert().success();
    let text = fs::read_to_string(&errors).unwrap_or_default();
    let warn = text
        .lines()
        .filter_map(|l| serde_json::from_str::<Value>(l).ok())
        .find(|v| v["code"] == "KCS-E-ADAPTER-TOOLS-PERM-001" && v["level"] == "warn");
    assert!(
        warn.is_some(),
        "0644 plain: tools.toml must warn; got {text}"
    );
    // The redacted log never carries the absolute config path.
    assert_eq!(warn.unwrap()["context"]["path"], "[redacted]");

    // 0600 -> no new warning.
    fs::remove_file(&errors).ok();
    fs::set_permissions(&tools, fs::Permissions::from_mode(0o600)).unwrap();
    kcs(&dir, &["status"]).assert().success();
    let text = fs::read_to_string(&errors).unwrap_or_default();
    assert!(
        !text.contains("KCS-E-ADAPTER-TOOLS-PERM-001"),
        "0600 tools.toml must not warn; got {text}"
    );
}

/// P5: a concurrent `kcs search` during repeated `repair --rebuild-db` must
/// never silently return exit 0 with 0 / partial results — the temp+rename
/// rebuild keeps the reader on a complete DB (old until the atomic swap, new
/// after), exactly the docs/05:564 contract. `repair --rebuild-db` leaves HEAD
/// untouched, so the only thing search observes changing is the sqlite.db swap —
/// the precise window P5's atomic rebuild closes (the old remove_file + in-place
/// rebuild exposed an empty/missing DB here, yielding exit 0 with 0 results).
#[test]
fn p5_concurrent_search_during_rebuild_is_never_silently_empty() {
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;

    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("a.md"),
        "# Alpha\n\n## S\nalphaunique alphaunique alphaunique\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("b.md"),
        "# Beta\n\n## T\nalphaunique betaword\n",
    )
    .unwrap();
    let data = dir.path().join(".test-data");
    let config = dir.path().join(".test-config");
    let cache = dir.path().join(".test-cache");
    let bin = assert_cmd::cargo::cargo_bin("kcs");
    let root = dir.path().to_path_buf();

    let run = |args: &[&str]| -> std::process::Output {
        std::process::Command::new(&bin)
            .args(args)
            .current_dir(&root)
            .env("XDG_DATA_HOME", &data)
            .env("XDG_CONFIG_HOME", &config)
            .env("XDG_CACHE_HOME", &cache)
            .output()
            .unwrap()
    };
    assert!(run(&["init"]).status.success());
    assert!(run(&["index", "--approve"]).status.success());
    let baseline = run(&["search", "alphaunique", "--text", "--json"]);
    assert!(baseline.status.success());
    let baseline: Value = serde_json::from_slice(&baseline.stdout).unwrap();
    let expected = baseline["results"].as_array().unwrap().len();
    assert!(expected > 0);

    let stop = Arc::new(AtomicBool::new(false));
    let handle = {
        let (bin, root) = (bin.clone(), root.clone());
        let (data, config, cache) = (data.clone(), config.clone(), cache.clone());
        let stop = stop.clone();
        std::thread::spawn(move || {
            let mut spins = 0;
            while !stop.load(Ordering::Relaxed) && spins < 200 {
                let _ = std::process::Command::new(&bin)
                    .args(["repair", "--rebuild-db"])
                    .current_dir(&root)
                    .env("XDG_DATA_HOME", &data)
                    .env("XDG_CONFIG_HOME", &config)
                    .env("XDG_CACHE_HOME", &cache)
                    .output();
                spins += 1;
            }
        })
    };

    for _ in 0..60 {
        let out = run(&["search", "alphaunique", "--text", "--json"]);
        // Any exit-0 search must return the full result set — never a silent
        // empty/partial (the P5 false negative). Non-zero exits (REBUILDING /
        // transient) are tolerated by the contract.
        if out.status.success() {
            let json: Value = serde_json::from_slice(&out.stdout).unwrap();
            let n = json["results"].as_array().unwrap().len();
            assert_eq!(
                n, expected,
                "search returned {n} results during rebuild (expected {expected}): silent false negative"
            );
        }
    }
    stop.store(true, Ordering::Relaxed);
    handle.join().unwrap();
}

/// P7: re-running `index` with the same opt-in must not append an equivalent
/// approval row every time — approvals.jsonl stays bounded (idempotent opt-in).
#[test]
fn p7_repeated_index_does_not_grow_approvals() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    kcs(&dir, &["init"]).assert().success();
    let approvals = dir.path().join(".kcs/approvals.jsonl");

    json_success(&dir, &["index", "--approve"]);
    let first = fs::read_to_string(&approvals).unwrap();
    let first_lines = first.lines().filter(|l| !l.trim().is_empty()).count();
    assert!(first_lines >= 1);

    for _ in 0..4 {
        json_success(&dir, &["index", "--approve"]);
    }
    let after = fs::read_to_string(&approvals).unwrap();
    let after_lines = after.lines().filter(|l| !l.trim().is_empty()).count();
    assert_eq!(
        after_lines, first_lines,
        "equivalent opt-in rows must not accumulate ({first_lines} -> {after_lines})"
    );
}

/// P8: the cursor signing key is created 0600 from the first byte (no 0644
/// window) — assert the resulting file is owner-only.
#[cfg(unix)]
#[test]
fn p8_cursor_key_is_created_0600() {
    use std::os::unix::fs::PermissionsExt;
    let dir = indexed_scope();
    // Page-1 search generates and signs a cursor with the device key.
    json_success(&dir, &["search", "認証仕様"]);
    let key = dir.path().join(".test-data/kcs/cursor-key");
    assert!(key.is_file(), "cursor-key must exist after a search");
    let mode = fs::metadata(&key).unwrap().permissions().mode() & 0o777;
    assert_eq!(mode, 0o600, "cursor-key must be 0600, got {mode:o}");
}

/// P9: the open/view read-only expansion cache lives under $XDG_CACHE_HOME
/// (06 §1.1), not $XDG_DATA_HOME.
#[test]
fn p9_open_expansion_cache_is_under_xdg_cache_home() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"]
        .as_str()
        .unwrap()
        .to_owned();
    // Remove the working-tree file so `open` must expand from the CAS.
    fs::remove_file(dir.path().join("auth.md")).unwrap();
    let opened = json_success(&dir, &["open", &uri]);
    assert_eq!(opened["temporary"], true);
    let path = opened["path"].as_str().unwrap();
    let expected_root = dir.path().join(".test-cache/kcs/open");
    assert!(
        Path::new(path).starts_with(&expected_root),
        "expansion cache {path} must be under {}",
        expected_root.display()
    );
    assert!(Path::new(path).is_file());
    // It must NOT be under the data home any more.
    assert!(!Path::new(path).starts_with(dir.path().join(".test-data/kcs/open")));
}

/// R9-3: the open/view expansion cache must be owner-only (dir 0700, file 0600 or
/// 0400) like the CAS it mirrors (P2), not world-readable at the umask default
/// (dir 0755 / file 0444). It materializes document bytes / images / pre-OCR raw
/// data, which must not be readable by group/other on a multi-user host.
#[cfg(unix)]
#[test]
fn r9_3_open_expansion_cache_is_owner_only() {
    use std::os::unix::fs::PermissionsExt;
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"]
        .as_str()
        .unwrap()
        .to_owned();
    // Remove the working-tree file so `open` must expand from the CAS.
    fs::remove_file(dir.path().join("auth.md")).unwrap();
    let opened = json_success(&dir, &["open", &uri]);
    let path = std::path::PathBuf::from(opened["path"].as_str().unwrap());

    // The cache file must be owner-only (created 0600, then 0400 readonly) — never
    // group/other-readable (pre-fix it was 0444).
    let file_mode = fs::metadata(&path).unwrap().permissions().mode() & 0o777;
    assert_eq!(
        file_mode & 0o077,
        0,
        "cache file must not be group/other-readable, got {file_mode:o}"
    );

    // Every dir from $XDG_CACHE_HOME/kcs down to the leaf must be 0700 (pre-fix
    // they were 0755, exposing the whole subtree to traversal).
    let cache_root = dir.path().join(".test-cache/kcs");
    let mut current = path.parent().unwrap().to_path_buf();
    loop {
        let mode = fs::metadata(&current).unwrap().permissions().mode() & 0o777;
        assert_eq!(
            mode,
            0o700,
            "cache dir {} must be 0700, got {mode:o}",
            current.display()
        );
        if current == cache_root {
            break;
        }
        current = current.parent().unwrap().to_path_buf();
    }
}

/// R9-3 (reuse path): a cache dir/file left world-readable by an earlier (pre-fix)
/// build must be re-hardened on the next `open`, not served as-is.
#[cfg(unix)]
#[test]
fn r9_3_open_reuse_rehardens_stale_permissions() {
    use std::os::unix::fs::PermissionsExt;
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"]
        .as_str()
        .unwrap()
        .to_owned();
    fs::remove_file(dir.path().join("auth.md")).unwrap();
    let opened = json_success(&dir, &["open", &uri]);
    let path = std::path::PathBuf::from(opened["path"].as_str().unwrap());
    let leaf = path.parent().unwrap().to_path_buf();

    // Simulate a cache materialized by the pre-fix, world-readable code path.
    fs::set_permissions(&path, fs::Permissions::from_mode(0o444)).unwrap();
    fs::set_permissions(&leaf, fs::Permissions::from_mode(0o755)).unwrap();

    // A second open reuses the cache (M5) and must correct the permissions.
    let reopened = json_success(&dir, &["open", &uri]);
    assert_eq!(reopened["path"].as_str().unwrap(), path.to_str().unwrap());
    let file_mode = fs::metadata(&path).unwrap().permissions().mode() & 0o777;
    assert_eq!(
        file_mode & 0o077,
        0,
        "reused cache file must be re-hardened, got {file_mode:o}"
    );
    let dir_mode = fs::metadata(&leaf).unwrap().permissions().mode() & 0o777;
    assert_eq!(
        dir_mode, 0o700,
        "reused cache dir must be re-hardened, got {dir_mode:o}"
    );
}

/// P10 (deterministic): `run_reindex` advances HEAD to a new generation and only
/// afterwards swaps in the rebuilt sqlite (P5's temp+rename). A concurrent search
/// in that window reads HEAD=C_new against the old-generation sqlite, whose chunks
/// join to none of C_new's tree_entries — pre-P10 that was a silent exit-0 empty
/// page. This reproduces the exact window without a race: back up the generation-N
/// sqlite, `reindex` to N+1 (HEAD moves), then restore the generation-N sqlite while
/// HEAD stays at N+1. The search must surface KCS-E-INDEX-REBUILDING-001 (docs/05
/// §6, retryable exit 3), never a silent empty. It also asserts a *completed*
/// reindex still returns the full set (no false positive) and that the state is
/// transient (a fresh reindex recovers).
#[test]
fn p10_reindex_window_returns_rebuilding_not_silent_empty() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("a.md"),
        "# Alpha\n\n## S\nalphaunique alphaunique content here\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("b.md"),
        "# Beta\n\n## T\nalphaunique betaword more\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);

    let baseline = json_success(&dir, &["search", "alphaunique", "--text"]);
    let expected = baseline["results"].as_array().unwrap().len();
    assert!(expected > 0);

    let db = dir.path().join(".kcs/index/sqlite.db");
    let backup = dir.path().join("sqlite_gen_n.db");
    fs::copy(&db, &backup).unwrap();

    // A completed reindex advances HEAD and atomically swaps in a fresh sqlite; the
    // search still returns the full set — no false REBUILDING.
    json_success(&dir, &["reindex", "--force", "--yes"]);
    let after = json_success(&dir, &["search", "alphaunique", "--text"]);
    assert_eq!(after["results"].as_array().unwrap().len(), expected);

    // Restore the generation-N sqlite while HEAD is at generation N+1 — the exact
    // state a concurrent search observes inside the reindex window (HEAD=C_new,
    // on-disk sqlite still the old generation, no live chunk for C_new).
    fs::copy(&backup, &db).unwrap();
    let err = json_failure(&dir, &["search", "alphaunique", "--text"], 3);
    assert_eq!(err["error_code"], "KCS-E-INDEX-REBUILDING-001");
    // The offending scope is reported as a part-failure exclusion, not dropped.
    assert_eq!(
        err["context"]["excluded_scopes"][0]["reason"],
        "index_rebuilding"
    );

    // The state is transient: rebuilding the index recovers the full result set.
    json_success(&dir, &["reindex", "--force", "--yes"]);
    let recovered = json_success(&dir, &["search", "alphaunique", "--text"]);
    assert_eq!(recovered["results"].as_array().unwrap().len(), expected);
}

/// P10 false-positive guard: the `kcs index` window must NOT be flagged REBUILDING.
/// `kcs index` re-generates only the changed documents, so an unchanged document's
/// chunk stays live for the new HEAD — the index is serviceable, not rebuilding.
/// Reproduce that window (change one doc, re-index, restore the pre-change sqlite
/// with HEAD at the new commit) and assert a query for the unchanged doc still
/// returns its hit at exit 0, never a spurious REBUILDING.
#[test]
fn p10_partial_index_window_does_not_false_rebuilding() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("a.md"),
        "# Alpha\n\n## S\nalphaword alphaword\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("b.md"),
        "# Beta\n\n## T\nbetaword betaword betaword\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);

    let db = dir.path().join(".kcs/index/sqlite.db");
    let backup = dir.path().join("sqlite_c0.db");
    fs::copy(&db, &backup).unwrap();

    // Change ONLY a.md and re-index: HEAD advances to a commit where a.md is a new
    // generation but b.md is unchanged.
    fs::write(
        dir.path().join("a.md"),
        "# Alpha\n\n## S\nalphaword alphaword changed newtext\n",
    )
    .unwrap();
    json_success(&dir, &["index", "--approve"]);

    // Restore the pre-change sqlite while HEAD is the post-change commit. Unlike
    // reindex, b.md's chunk is still live for HEAD, so a query for the unchanged
    // doc must return its hit (exit 0) — never a spurious REBUILDING.
    fs::copy(&backup, &db).unwrap();
    let search = json_success(&dir, &["search", "betaword", "--text"]);
    assert!(
        !search["results"].as_array().unwrap().is_empty(),
        "unchanged doc must stay searchable in the index window (not REBUILDING)"
    );
    assert!(search["excluded_scopes"].as_array().unwrap().is_empty());
}

/// P10 non-regression: a genuine no-hit on a healthy index and a query on an empty
/// scope both stay exit-0 empty — the rebuilding detector must not fire when live
/// chunks exist (genuine miss) or when the scope has no tree_entries (empty scope).
#[test]
fn p10_genuine_no_hit_and_empty_scope_stay_exit_zero() {
    // Healthy indexed scope: a matching query has hits; a non-matching query is an
    // honest exit-0 empty page (live chunks exist -> fast-path returns not-rebuilding).
    let dir = indexed_scope();
    assert!(
        !json_success(&dir, &["search", "認証仕様", "--text"])["results"]
            .as_array()
            .unwrap()
            .is_empty()
    );
    let miss = json_success(&dir, &["search", "zzznotpresentquery", "--text"]);
    assert!(miss["results"].as_array().unwrap().is_empty());
    assert!(miss["excluded_scopes"].as_array().unwrap().is_empty());

    // Empty scope (no documents): exit-0 empty page (no tree_entries for HEAD).
    let empty = tempfile::tempdir().unwrap();
    kcs(&empty, &["init"]).assert().success();
    kcs(&empty, &["index", "--approve"]).assert().success();
    let search = json_success(&empty, &["search", "anything", "--text"]);
    assert!(search["results"].as_array().unwrap().is_empty());
    assert!(search["excluded_scopes"].as_array().unwrap().is_empty());
}

/// P10 (concurrent, end-to-end): a `kcs search` running while `reindex --force`
/// spins must never silently return exit 0 with an empty/partial page — every
/// exit-0 search returns the complete result set (old or new generation, both the
/// same content). Non-zero exits are the honest transient (REBUILDING, docs/05:564
/// — proven exactly by `p10_reindex_window_returns_rebuilding_not_silent_empty`)
/// and are tolerated. Mirrors the P5 concurrency harness but drives `reindex`,
/// which re-generates every document and so exposes the HEAD-vs-sqlite window P5's
/// atomic rebuild alone does not close.
#[test]
fn p10_concurrent_search_during_reindex_is_never_silently_empty() {
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;

    let dir = tempfile::tempdir().unwrap();
    // Enough documents that the all-document re-generation + rebuild spans a window
    // a concurrent search can land in.
    for i in 0..12 {
        fs::write(
            dir.path().join(format!("doc{i}.md")),
            format!("# Doc {i}\n\n## S\nalphaunique alphaunique body {i} filler filler filler\n"),
        )
        .unwrap();
    }
    let data = dir.path().join(".test-data");
    let config = dir.path().join(".test-config");
    let cache = dir.path().join(".test-cache");
    let bin = assert_cmd::cargo::cargo_bin("kcs");
    let root = dir.path().to_path_buf();

    // Hermetic adapter seams (no network); text search does not exercise them, but
    // set them so any accidental adapter call is a mock.
    let run = |args: &[&str]| -> std::process::Output {
        std::process::Command::new(&bin)
            .args(args)
            .current_dir(&root)
            .env("XDG_DATA_HOME", &data)
            .env("XDG_CONFIG_HOME", &config)
            .env("XDG_CACHE_HOME", &cache)
            .env(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")
            .env(TEST_ADOPTED_EMBEDDING_ENV, "mock")
            .output()
            .unwrap()
    };
    assert!(run(&["init"]).status.success());
    assert!(run(&["index", "--approve"]).status.success());
    let baseline = run(&["search", "alphaunique", "--text", "--json"]);
    assert!(baseline.status.success());
    let baseline: Value = serde_json::from_slice(&baseline.stdout).unwrap();
    let expected = baseline["results"].as_array().unwrap().len();
    assert!(expected > 0);

    let stop = Arc::new(AtomicBool::new(false));
    let handle = {
        let (bin, root) = (bin.clone(), root.clone());
        let (data, config, cache) = (data.clone(), config.clone(), cache.clone());
        let stop = stop.clone();
        std::thread::spawn(move || {
            let mut spins = 0;
            while !stop.load(Ordering::Relaxed) && spins < 50 {
                let _ = std::process::Command::new(&bin)
                    .args(["reindex", "--force", "--yes"])
                    .current_dir(&root)
                    .env("XDG_DATA_HOME", &data)
                    .env("XDG_CONFIG_HOME", &config)
                    .env("XDG_CACHE_HOME", &cache)
                    .env(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, "mock")
                    .env(TEST_ADOPTED_EMBEDDING_ENV, "mock")
                    .output();
                spins += 1;
            }
        })
    };

    let mut saw_success = false;
    for _ in 0..150 {
        let out = run(&["search", "alphaunique", "--text", "--json"]);
        if out.status.success() {
            saw_success = true;
            let json: Value = serde_json::from_slice(&out.stdout).unwrap();
            let n = json["results"].as_array().unwrap().len();
            assert_eq!(
                n, expected,
                "search returned {n} results during reindex (expected {expected}): P10 silent false negative"
            );
        }
    }
    stop.store(true, Ordering::Relaxed);
    handle.join().unwrap();
    assert!(
        saw_success,
        "expected at least one exit-0 search across the concurrent run"
    );
}

// Q1 (full cycle): a torn trailing record in `chunks.jsonl` (crash / ENOSPC
// post-state, no trailing '\n') must fully self-heal. Skipping it on read alone
// welds the next append onto the torn bytes, producing a permanently-skipped
// malformed line that re-bricks `repair --rebuild-db` on exit 4 and re-appends the
// same chunk forever. After the fix the torn tail is physically truncated before
// the append, so index -> repair -> index all exit 0 and the file stays valid with
// no duplicate chunk_id.
#[test]
fn q1_torn_chunk_tail_fully_self_heals_across_index_repair_index() {
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
    json_success(&dir, &["index", "--yes"]);

    let chunks_path = dir.path().join(".kcs/index/chunks.jsonl");
    let bytes = fs::read(&chunks_path).unwrap();
    assert_eq!(
        bytes.last(),
        Some(&b'\n'),
        "a fresh index must be newline-terminated"
    );
    // Cut the final record in half: leaves the earlier records intact and a torn
    // tail with no trailing '\n' (== crash between two `write_all`s).
    let last_nl = bytes.iter().rposition(|&byte| byte == b'\n').unwrap();
    let prev_nl = bytes[..last_nl]
        .iter()
        .rposition(|&byte| byte == b'\n')
        .expect("need at least two records so the final one can be torn");
    let record_start = prev_nl + 1;
    let cut = record_start + (last_nl - record_start) / 2;
    fs::write(&chunks_path, &bytes[..cut]).unwrap();
    assert_ne!(
        fs::read(&chunks_path).unwrap().last(),
        Some(&b'\n'),
        "torn tail must not end in a newline"
    );

    // Full self-heal cycle. Every step must exit 0 — the middle `repair` was the
    // one that used to exit 4 (KCS-E-STORE-CORRUPT-001).
    json_success(&dir, &["index", "--yes"]);
    json_success(&dir, &["repair", "--rebuild-db", "--yes"]);
    json_success(&dir, &["index", "--yes"]);

    // chunks.jsonl is now fully valid with no duplicated chunk_id (no torn-line
    // skip -> re-append loop, no permanently-skipped welded line).
    let text = fs::read_to_string(&chunks_path).unwrap();
    let mut ids = std::collections::BTreeSet::new();
    let mut count = 0usize;
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        let value: Value = serde_json::from_str(line).unwrap_or_else(|err| {
            panic!("every chunks.jsonl line must be valid JSON ({err}): {line}")
        });
        let id = value["chunk_id"].as_str().unwrap().to_owned();
        assert!(ids.insert(id), "chunk_id must not be duplicated: {line}");
        count += 1;
    }
    assert!(
        count >= 2,
        "regenerated chunks must be present, got {count}"
    );
}

// ---------------------------------------------------------------------------
// R6 exploratory audit fixes.
// ---------------------------------------------------------------------------

#[test]
fn r6_foreign_approval_rows_do_not_grant_online_embedding() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("note.md"),
        "# Note\nforeign approval probe\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    let other = tempfile::tempdir().unwrap();
    fs::write(other.path().join("other.md"), "# Other\napproval source\n").unwrap();
    kcs(&other, &["init"]).assert().success();
    json_success_embed(&other, "mock", &["index", "--approve"]);
    let foreign_approvals = fs::read_to_string(other.path().join(".kcs/approvals.jsonl")).unwrap();
    fs::write(dir.path().join(".kcs/approvals.jsonl"), foreign_approvals).unwrap();

    let out = json_success_embed(&dir, "mock", &["index", "--yes"]);
    assert_eq!(out["network_allowed"], false);
    assert_eq!(out["network_opt_in"], false);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    assert!(
        !embedding.is_empty(),
        "embedding task should be enqueued: {status}"
    );
    assert!(
        embedding.iter().all(|task| {
            task["status"] == "pending" && task["fallback_reason"] == "network_opt_in_required"
        }),
        "foreign approvals must not execute embedding tasks: {status}"
    );
}

#[test]
fn r6_empty_approvals_file_does_not_satisfy_online_flag() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("note.md"), "# Note\nempty approval probe\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    fs::write(dir.path().join(".kcs/approvals.jsonl"), "").unwrap();

    let err = json_failure_embed(&dir, "mock", &["index", "--online"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");
}

#[test]
fn r6_view_open_reject_extra_pointer_arguments() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let uri = first_result(&search)["evidence_uri"].as_str().unwrap();

    let view_err = json_failure(&dir, &["view", uri, "EXTRA"], 2);
    assert_eq!(view_err["error_code"], "KCS-E-CONFIG-USAGE-001");
    let open_err = json_failure(&dir, &["open", uri, "--definitely-invalid"], 2);
    assert_eq!(open_err["error_code"], "KCS-E-CONFIG-USAGE-001");
}

#[test]
fn r6_reindex_rejects_unimplemented_at_and_extra_operands() {
    let dir = indexed_scope();
    // R9-6: not-implemented `--at` exits 1 (canonical not_implemented); the extra
    // positional stays a usage error (exit 2).
    let at = json_failure(&dir, &["reindex", "--force", "--yes", "--at", "HEAD"], 1);
    assert_eq!(at["error_code"], "KCS-E-CONFIG-NOT-IMPLEMENTED-001");
    let extra = json_failure(&dir, &["reindex", "--force", "--yes", "HEAD"], 2);
    assert_eq!(extra["error_code"], "KCS-E-CONFIG-USAGE-001");
}

#[test]
fn r6_inline_json_pointer_rejects_unsupported_schema_version() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let mut pointer = first_result(&search)["evidence_pointer"].clone();
    pointer["schema_version"] = Value::from(999);

    let err = json_failure(&dir, &["view", &pointer.to_string()], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

#[test]
fn r6_default_search_rereads_current_global_opt_out() {
    let data_home = tempfile::tempdir().unwrap();
    let a = tempfile::tempdir().unwrap();
    let b = tempfile::tempdir().unwrap();
    fs::write(a.path().join("a.md"), "# A\nalphaonly optout leak\n").unwrap();
    fs::write(b.path().join("b.md"), "# B\nbetapublic\n").unwrap();
    json_success_path(a.path(), data_home.path(), &["init"]);
    json_success_path(b.path(), data_home.path(), &["init"]);
    json_success_path(a.path(), data_home.path(), &["index", "--approve"]);
    json_success_path(b.path(), data_home.path(), &["index", "--approve"]);
    fs::write(
        a.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[scope]\nparticipates_in_global_search = false\n",
    )
    .unwrap();

    let search = json_success_path(
        b.path(),
        data_home.path(),
        &["search", "alphaonly", "--text"],
    );
    assert!(
        search["results"].as_array().unwrap().is_empty(),
        "stale registry opt-in must not leak opted-out scope results: {search}"
    );
}

#[test]
fn r6_tool_lock_rejects_future_spec_version() {
    let dir = indexed_scope();
    let path = dir.path().join(".kcs/tool-lock.json");
    let mut value: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    value["spec_version"] = Value::from(999);
    fs::write(&path, serde_json::to_vec_pretty(&value).unwrap()).unwrap();

    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
    assert!(err["message"]
        .as_str()
        .unwrap()
        .contains("unsupported tool-lock spec_version"));
}

#[test]
fn r6_corrupt_normalized_unit_is_store_corrupt_not_config_schema() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("note.md"),
        "# Note\nnormalized corruption searchable\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--yes"]);
    let unit_path = first_normalized_unit_json(&dir.path().join(".kcs/objects/normalized_units"));
    fs::write(&unit_path, r#"{"torn":"#).unwrap();

    let err = json_failure(&dir, &["repair", "--rebuild-db"], 4);
    assert_eq!(err["error_code"], "KCS-E-STORE-CORRUPT-001");
    let reported = std::path::PathBuf::from(err["context"]["path"].as_str().unwrap())
        .canonicalize()
        .unwrap();
    assert_eq!(reported, unit_path.canonicalize().unwrap());
}

// ---------------------------------------------------------------------------
// R7 exploratory audit fixes.
// ---------------------------------------------------------------------------

#[test]
fn r7_empty_secrets_approval_file_does_not_lift_tier_b_hold() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("api_secret.md"),
        "# Secret\nprobable secret body\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    fs::write(dir.path().join(".kcs/secrets-approved.jsonl"), "").unwrap();

    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    assert!(
        status["quarantine"]
            .as_array()
            .unwrap()
            .iter()
            .any(|entry| {
                entry["path"] == "api_secret.md"
                    && entry["reason"] == "secrets_tier_b"
                    && entry["approval_method"] == "hold"
            }),
        "empty secrets approval file must not mark Tier B as send-approved: {status}"
    );
    assert!(
        tasks_of_type(&status, "embedding").iter().any(|task| {
            task["input_path"] == "api_secret.md"
                && task["status"] == "paused"
                && task["fallback_reason"] == "secrets_tier_b_hold"
        }),
        "Tier B embedding must stay held without a scoped send-secrets row: {status}"
    );
}

#[test]
fn r7_multiscope_query_embedding_requires_every_target_scope_opt_in() {
    let data_home = tempfile::tempdir().unwrap();
    let a = tempfile::tempdir().unwrap();
    let b = tempfile::tempdir().unwrap();
    fs::write(a.path().join("a.md"), "# A\nsharedterm alpha\n").unwrap();
    fs::write(b.path().join("b.md"), "# B\nsharedterm beta\n").unwrap();
    run_embed_path(a.path(), data_home.path(), "mock", &["init"]);
    run_embed_path(b.path(), data_home.path(), "mock", &["init"]);
    run_embed_path(
        a.path(),
        data_home.path(),
        "mock",
        &["index", "--approve", "--online"],
    );
    // B has embeddings from a one-shot send, but no persistent embedding opt-in.
    run_embed_path(
        b.path(),
        data_home.path(),
        "mock",
        &["index", "--yes", "--online"],
    );

    let trace = data_home.path().join("query.trace");
    let output = Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(a.path())
        .env("XDG_CONFIG_HOME", data_home.path().join("config"))
        .env("XDG_DATA_HOME", data_home.path().join("data"))
        .env("XDG_CACHE_HOME", data_home.path().join("cache"))
        .env(TEST_ADOPTED_EMBEDDING_ENV, "mock")
        .env("KCS_TEST_QUERY_EMBED_TRACE", &trace)
        .args(["search", "sharedterm", "--json"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let search: Value = serde_json::from_slice(&output).unwrap();
    assert_eq!(search["resolved_mode"], "text");
    assert_eq!(search["fallback_reason"], "embedding_opt_in_required");
    assert!(
        !trace.exists(),
        "query embedding must not be sent when any searched scope lacks opt-in"
    );
}

#[test]
fn r7_repair_rejects_unknown_flags_extra_operands_and_step4_verify() {
    let dir = indexed_scope();
    let unknown = json_failure(
        &dir,
        &["repair", "--rebuild-db", "--definitely-invalid", "EXTRA"],
        2,
    );
    assert_eq!(unknown["error_code"], "KCS-E-CONFIG-USAGE-001");

    // R9-6: not-implemented `--verify-objects` exits 1 (canonical not_implemented).
    let verify = json_failure(&dir, &["repair", "--verify-objects"], 1);
    assert_eq!(verify["error_code"], "KCS-E-CONFIG-NOT-IMPLEMENTED-001");
}

#[test]
fn r7_embedding_profile_change_reembeds_current_profile() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("doc.md"), "# Doc\nalpha profile flip\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed(&dir, "incompatible_profile", &["index", "--approve"]);
    json_success_embed(&dir, "mock", &["index", "--approve"]);
    let after = json_success_embed(&dir, "mock", &["search", "alpha"]);
    assert_eq!(after["resolved_mode"], "hybrid", "{after}");
    assert_eq!(after["fallback"], false, "{after}");
}

fn first_normalized_unit_json(root: &Path) -> std::path::PathBuf {
    let mut stack = vec![root.to_path_buf()];
    while let Some(path) = stack.pop() {
        for entry in fs::read_dir(&path).unwrap() {
            let entry = entry.unwrap();
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            if path.extension().and_then(|ext| ext.to_str()) == Some("json")
                && path.file_name().and_then(|name| name.to_str()) != Some("manifest.json")
            {
                return path;
            }
        }
    }
    panic!("normalized unit json not found under {}", root.display());
}

/// R9-5: a normalized gen dir polluted with crash/OS junk — a torn `.tmp-*` left
/// by a killed atomic writer and a `.DS_Store` — must not brick `reindex`. Before
/// the fix, `copy_normalized_instance_gen` read every non-manifest entry as a unit
/// and failed with KCS-E-STORE-CORRUPT-001 (exit 4), which `repair --rebuild-db`
/// could not heal. After: junk is skipped, the orphan `.tmp-*` is GC'd from the
/// old gen dir, and reindex succeeds and the index still resolves the document.
#[test]
fn r9_5_reindex_survives_junk_in_gen_dir() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("doc.md"),
        "# Title\n\n## Section\nr9five unique body text here\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);

    let units_root = dir.path().join(".kcs/objects/normalized_units");
    let gen_dir = gen_dir_under(&units_root).expect("a .g0 gen dir exists after index");
    let torn = gen_dir.join(".tmp-99999-0000abcd");
    fs::write(&torn, b"torn partial write, not json").unwrap();
    fs::write(gen_dir.join(".DS_Store"), b"\0\0mac junk").unwrap();

    // Before the fix this exited 4 (STORE-CORRUPT); now it succeeds.
    json_success(&dir, &["reindex", "--force", "--yes"]);

    // The orphan temp was GC'd from the old gen dir (Q1-style self-heal).
    assert!(
        !torn.exists(),
        "orphan .tmp-* must be cleaned up by reindex"
    );
    // Search still resolves the document (index rebuilt cleanly).
    let search = json_success(&dir, &["search", "r9five", "--text"]);
    assert!(!search["results"].as_array().unwrap().is_empty());
}

/// A minimal fake PDF with one text-bearing page per string (mirrors the step2
/// helper). Used where a non-text-native fixture is needed so an online
/// markdownize task is enqueued (R9-2 gates text-native files out of online OCR).
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

fn gen_dir_under(units_root: &Path) -> Option<std::path::PathBuf> {
    let mut stack = vec![units_root.to_path_buf()];
    while let Some(current) = stack.pop() {
        let Ok(entries) = fs::read_dir(&current) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            if path
                .file_name()
                .and_then(|name| name.to_str())
                .map(|name| name.ends_with(".g0"))
                .unwrap_or(false)
            {
                return Some(path);
            }
            stack.push(path);
        }
    }
    None
}

// ===========================================================================
// R12-2: [adapter.policy] documented keys — schema accepts the 8 documented keys
// (was: 7 of 8 rejected -> scope/device brick), non-default UNIMPLEMENTED values
// are loudly rejected, redact_logs is actually wired, max_input_bytes gates input.
// ===========================================================================

// docs/07 §7 block (every key at its documented default) must let ALL commands run
// (exit 0) instead of bricking the scope with KCS-E-CONFIG-SCHEMA-001.
#[test]
fn r12_2_adapter_policy_full_default_block_all_commands_ok() {
    let dir = indexed_scope();
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n\
         [adapter.policy]\n\
         allow_network = false\n\
         allowed_scope = \".\"\n\
         max_input_bytes = 104857600\n\
         timeout_seconds = 300\n\
         redact_logs = true\n\
         store_request_body = false\n\
         store_response_body = false\n\
         require_command_confirmation = true\n",
    )
    .unwrap();
    // status and search both open the repo (schema + semantic validation) — both
    // succeed with the full default block present.
    let status = json_success(&dir, &["status"]);
    assert!(status.get("scope_path").is_some());
    let search = json_success(&dir, &["search", "トークン TTL"]);
    assert!(!search["results"].as_array().unwrap().is_empty());
}

// A non-default value for an UNIMPLEMENTED enforcement key is a loud
// KCS-E-CONFIG-NOT-IMPLEMENTED-001 (exit 1), not a silent accept.
#[test]
fn r12_2_allowed_scope_non_default_is_loud_rejected() {
    let dir = indexed_scope();
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[adapter.policy]\nallowed_scope = \"sub\"\n",
    )
    .unwrap();
    let err = json_failure(&dir, &["status"], 1);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-NOT-IMPLEMENTED-001");
}

#[test]
fn r12_2_store_request_body_true_is_loud_rejected() {
    let dir = indexed_scope();
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[adapter.policy]\nstore_request_body = true\n",
    )
    .unwrap();
    let err = json_failure(&dir, &["status"], 1);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-NOT-IMPLEMENTED-001");
}

#[test]
fn r12_2_timeout_seconds_non_default_is_loud_rejected() {
    let dir = indexed_scope();
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[adapter.policy]\ntimeout_seconds = 30\n",
    )
    .unwrap();
    let err = json_failure(&dir, &["status"], 1);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-NOT-IMPLEMENTED-001");
    // The documented default (300) is accepted.
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[adapter.policy]\ntimeout_seconds = 300\n",
    )
    .unwrap();
    json_success(&dir, &["status"]);
}

// A typo / unknown key under [adapter.policy] is a schema error (exit 2), distinct
// from the semantic NOT-IMPLEMENTED (exit 1) above.
#[test]
fn r12_2_unknown_policy_key_is_schema_error() {
    let dir = indexed_scope();
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[adapter.policy]\nallow_netwrok = false\n",
    )
    .unwrap();
    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

// redact_logs is finally reachable: user config `redact_logs = false` turns off the
// errors.jsonl path masking (was permanently pinned to redacted because the schema
// rejected the key before it could ever be read).
#[test]
fn r12_2_user_config_redact_logs_false_records_path() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("a.txt"), "hello").unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Device-global user config (XDG_CONFIG_HOME/kcs/config.toml).
    let user_cfg = dir.path().join(".test-config/kcs");
    fs::create_dir_all(&user_cfg).unwrap();
    fs::write(
        user_cfg.join("config.toml"),
        "[adapter.policy]\nredact_logs = false\n",
    )
    .unwrap();
    // Same corrupt-tasks trigger as n3_errors_jsonl_redacts_path -> errors.jsonl.
    fs::write(dir.path().join(".kcs/tasks.jsonl"), "{ not json\n").unwrap();
    json_failure(&dir, &["status"], 4);
    let errors = fs::read_to_string(dir.path().join(".test-data/kcs/logs/errors.jsonl")).unwrap();
    let last: Value = serde_json::from_str(errors.lines().last().unwrap()).unwrap();
    assert_ne!(
        last["context"]["path"], "[redacted]",
        "redact_logs = false must record the real path: {last}"
    );
    assert!(
        last["context"]["path"]
            .as_str()
            .is_some_and(|path| path.contains("tasks.jsonl")),
        "path must be the real tasks.jsonl path: {last}"
    );
}

// max_input_bytes is a real input gate: a file larger than the cap is skipped for
// adapter processing (never normalized) but the index still succeeds.
#[test]
fn r12_2_max_input_bytes_gates_oversized_input() {
    let dir = tempfile::tempdir().unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Cap at 50 bytes; write a markdown file well over that.
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[adapter.policy]\nmax_input_bytes = 50\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("big.md"),
        "# Big\n\n## Section\nthis body is definitely longer than fifty bytes in total.\n",
    )
    .unwrap();
    let index = json_success(&dir, &["index", "--approve"]);
    assert_eq!(index["skipped_oversized_files"], 1);
    assert_eq!(index["normalized_files"], 0);
}

// ===========================================================================
// R12-1: [search.rrf] / [search.diversify] / [markdownize.incremental] were
// documented + schema-valid but hardcoded at every call site (dead tuning knobs).
// ===========================================================================

/// A single-file scope whose file has 5 heading sections all sharing one token
/// (so one raw_hash, 5 chunks) — the fixture for diversify dedup behavior.
fn multi_chunk_scope() -> TempDir {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("doc.md"),
        "# Doc\n\n\
         ## S1\nsharedtoken alpha section body text.\n\n\
         ## S2\nsharedtoken beta section body text.\n\n\
         ## S3\nsharedtoken gamma section body text.\n\n\
         ## S4\nsharedtoken delta section body text.\n\n\
         ## S5\nsharedtoken epsilon section body text.\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);
    dir
}

fn write_scope_config(dir: &TempDir, body: &str) {
    fs::write(
        dir.path().join(".kcs/config.toml"),
        format!("kcs_format_version = \"0.1.0\"\n{body}"),
    )
    .unwrap();
}

// strategy = "off" is a real no-op (no dedup); max_per_raw_hash caps the stream —
// both were dead before R12-1 (default MMR/3 applied regardless of config).
#[test]
fn r12_1_diversify_config_controls_dedup() {
    let dir = multi_chunk_scope();

    // Default (no config): text-only -> MMR skipped -> max_per_raw_hash=3 cap.
    let default = json_success(&dir, &["search", "sharedtoken"]);
    assert_eq!(default["results"].as_array().unwrap().len(), 3);

    // strategy = "off": diversification disabled entirely -> every matching chunk.
    write_scope_config(&dir, "[search.diversify]\nstrategy = \"off\"\n");
    let off = json_success(&dir, &["search", "sharedtoken"]);
    assert!(
        off["results"].as_array().unwrap().len() >= 4,
        "off must return more than the default cap of 3: {}",
        off["results"].as_array().unwrap().len()
    );
    assert_eq!(off["diversify"]["strategy"], "off");

    // max_per_raw_hash = 1: cap the raw_hash to a single chunk.
    write_scope_config(&dir, "[search.diversify]\nmax_per_raw_hash = 1\n");
    let capped = json_success(&dir, &["search", "sharedtoken"]);
    assert_eq!(capped["results"].as_array().unwrap().len(), 1);
}

// The cursor query_hash embeds the EFFECTIVE rrf/diversify (05 §1.8:280): changing
// [search.rrf] between pages invalidates an in-flight cursor instead of silently
// replaying a differently-ranked page.
#[test]
fn r12_1_query_hash_depends_on_rrf_config() {
    let dir = multi_chunk_scope();
    let page1 = json_success(&dir, &["search", "sharedtoken", "--limit", "1"]);
    let cursor = page1["paging"]["next_cursor"]
        .as_str()
        .expect("cursor present");
    // Same config -> the cursor replays fine (sanity).
    json_success(
        &dir,
        &["search", "sharedtoken", "--limit", "1", "--cursor", cursor],
    );
    // Change the effective rrf -> query_hash changes -> the old cursor is rejected.
    write_scope_config(&dir, "[search.rrf]\nk = 1\n");
    let err = json_failure(
        &dir,
        &["search", "sharedtoken", "--limit", "1", "--cursor", cursor],
        2,
    );
    assert_eq!(err["error_code"], "KCS-E-SEARCH-CURSOR-001");
}

// An unknown key under the now-typed [search.rrf] is a schema error (exit 2) — the
// [search] block is `additionalProperties: false` after R12-1 (typo detection).
#[test]
fn r12_1_unknown_search_rrf_key_is_schema_error() {
    let dir = multi_chunk_scope();
    write_scope_config(&dir, "[search.rrf]\nnonsense_key = 1\n");
    let err = json_failure(&dir, &["search", "sharedtoken"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

// [search.multi_scope] stays typed-but-accepted (MULTI-006 defer): a documented
// key must not brick, even though it is unwired.
#[test]
fn r12_1_multi_scope_config_is_accepted_not_bricked() {
    let dir = multi_chunk_scope();
    write_scope_config(&dir, "[search.multi_scope]\nparallelism = 4\n");
    json_success(&dir, &["search", "sharedtoken"]);
}

// include_neighbors has no implementation concept: a non-default value is a loud
// NOT-IMPLEMENTED (exit 1), the documented default (1) is a no-op accept.
#[test]
fn r12_1_incremental_include_neighbors_non_default_rejected() {
    let dir = multi_chunk_scope();
    write_scope_config(&dir, "[markdownize.incremental]\ninclude_neighbors = 2\n");
    let err = json_failure(&dir, &["status"], 1);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-NOT-IMPLEMENTED-001");
    // The documented default (1) is accepted.
    write_scope_config(&dir, "[markdownize.incremental]\ninclude_neighbors = 1\n");
    json_success(&dir, &["status"]);
}

// ===========================================================================
// R12-3: R11-5's deferred embedding write-back opened a crash window — a chunk's
// chunk_vec commits per batch but the task Done transition is deferred to after the
// loop. A crash between leaves the chunk embedded yet its task stuck Pending
// forever (no recovery command reconciles it), so index_status reports phantom
// pending enrichment. The reconcile step on the shared enrichment path heals it.
// ===========================================================================
#[test]
fn r12_3_reconcile_completes_committed_embedding_tasks() {
    let dir = indexed_scope_embed("mock");
    let tasks_path = dir.path().join(".kcs/tasks.jsonl");

    // Reproduce the crash window: chunk_vec/embeddings are committed (from the mock
    // index above) but the Done write-back was lost -> flip every Done embedding
    // task back to Pending.
    let original = fs::read_to_string(&tasks_path).unwrap();
    let mut flipped = String::new();
    let mut embedding_pending = 0u64;
    for line in original.lines() {
        let mut task: Value = serde_json::from_str(line).unwrap();
        if task["type"] == "embedding" && task["status"] == "done" {
            task["status"] = Value::from("pending");
            task["attempts"] = Value::from(0);
            task["next_retry_at"] = Value::Null;
            embedding_pending += 1;
        }
        flipped.push_str(&serde_json::to_string(&task).unwrap());
        flipped.push('\n');
    }
    assert!(embedding_pending > 0, "fixture must have embedding tasks");
    fs::write(&tasks_path, flipped).unwrap();

    // The phantom: index_status reports the stranded tasks as pending enrichment.
    let before = json_success_embed(&dir, "mock", &["search", "トークン TTL", "--hybrid"]);
    assert_eq!(
        before["index_status"]["pending_enrichment_tasks"], embedding_pending,
        "flipped tasks must read as pending before reconcile"
    );

    // A single recovery command (index) reconciles the accounting WITHOUT re-sending:
    // every chunk is already embedded, so `pending` is empty and nothing is executed.
    let reindex = json_success_embed(&dir, "mock", &["index", "--approve"]);
    assert_eq!(
        reindex["embedding_tasks_executed"], 0,
        "reconcile must not re-send embeddings: {reindex}"
    );

    // Tasks converge to Done and index_status reports zero pending.
    let after = json_success_embed(&dir, "mock", &["search", "トークン TTL", "--hybrid"]);
    assert_eq!(after["index_status"]["pending_enrichment_tasks"], 0);
    let final_tasks = fs::read_to_string(&tasks_path).unwrap();
    for line in final_tasks.lines() {
        let task: Value = serde_json::from_str(line).unwrap();
        if task["type"] == "embedding" {
            assert_eq!(
                task["status"], "done",
                "every embedding task must reconcile to done: {task}"
            );
        }
    }
}

// ===========================================================================
// R12-4: exit 3/5/6 __exit_code overrides and clap usage errors bypassed
// errors.jsonl, and a failed search dropped its per-search metrics.jsonl line —
// the whole failure surface was invisible to the observability logs.
// ===========================================================================

// Enrichment auth failure (exit 5 via __exit_code) must now reach errors.jsonl.
#[test]
fn r12_4_enrichment_auth_failure_reaches_errors_jsonl() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("note.md"),
        "# ノート\n\n## 本文\n認証失敗の可視化テスト本文です。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    let indexed = json_code_stdout_embed(&dir, "auth_error", 5, &["index", "--approve"]);
    assert!(indexed["embedding_tasks_failed"].as_u64().unwrap() > 0);
    let errors = fs::read_to_string(dir.path().join(".test-data/kcs/logs/errors.jsonl")).unwrap();
    assert!(
        errors.lines().any(|line| {
            serde_json::from_str::<Value>(line).unwrap()["code"]
                .as_str()
                .is_some_and(|code| code.contains("AUTH"))
        }),
        "the enrichment auth failure must reach errors.jsonl: {errors}"
    );
}

// Multi-scope partial failure (exit 3 via __exit_code) must record the exclusion.
#[test]
fn r12_4_multi_scope_partial_records_exclusion_in_errors_jsonl() {
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
    let b_kcs = b.join(".kcs");
    use std::os::unix::fs::PermissionsExt;
    let mut perms = fs::metadata(&b_kcs).unwrap().permissions();
    perms.set_mode(0o000);
    fs::set_permissions(&b_kcs, perms).unwrap();
    Command::cargo_bin("kcs")
        .unwrap()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .args(["search", "alphaunique", "--json"])
        .assert()
        .code(3);
    let mut restore = fs::metadata(&b_kcs).unwrap().permissions();
    restore.set_mode(0o755);
    fs::set_permissions(&b_kcs, restore).unwrap();
    let errors = fs::read_to_string(data_home.join("data/kcs/logs/errors.jsonl")).unwrap();
    assert!(
        errors.lines().any(|line| {
            let value: Value = serde_json::from_str(line).unwrap();
            value["context"]["excluded_scopes"].is_array()
        }),
        "the multi-scope exclusion must reach errors.jsonl: {errors}"
    );
}

// A failed search still emits a per-search metrics.jsonl line (result_count 0 +
// error_code) so it is not silently dropped from the latency population, and the
// errors.jsonl line (main Err arm) is present too.
#[test]
fn r12_4_failed_search_writes_metrics_and_errors() {
    let dir = indexed_scope();
    json_failure(
        &dir,
        &["search", "トークン", "--cursor", "not-a-real-cursor"],
        2,
    );
    let metrics = fs::read_to_string(dir.path().join(".test-data/kcs/logs/metrics.jsonl")).unwrap();
    assert!(
        metrics.lines().any(|line| {
            let value: Value = serde_json::from_str(line).unwrap();
            value["message"] == "search failed" && value["context"]["result_count"] == 0
        }),
        "a failed search must emit a metrics line: {metrics}"
    );
    let errors = fs::read_to_string(dir.path().join(".test-data/kcs/logs/errors.jsonl")).unwrap();
    assert!(
        errors.lines().any(|line| {
            serde_json::from_str::<Value>(line).unwrap()["code"]
                .as_str()
                .is_some_and(|code| code.contains("CURSOR"))
        }),
        "a failed search must record errors.jsonl: {errors}"
    );
}

// A clap usage error belongs in the device-global errors.jsonl too (it bypassed
// run() entirely, exiting inside exit_from_clap_error).
#[test]
fn r12_4_clap_usage_error_reaches_errors_jsonl() {
    let dir = tempfile::tempdir().unwrap();
    kcs(&dir, &["index", "--this-flag-does-not-exist"])
        .assert()
        .code(2);
    let errors_path = dir.path().join(".test-data/kcs/logs/errors.jsonl");
    let errors = fs::read_to_string(&errors_path).unwrap();
    assert!(
        errors.lines().any(|line| {
            serde_json::from_str::<Value>(line).unwrap()["code"] == "KCS-E-CONFIG-USAGE-001"
        }),
        "a clap usage error must record errors.jsonl: {errors}"
    );
}

// ===========================================================================
// R12-5: a metrics.jsonl / access.jsonl append failure must NOT kill the search —
// observability logging must not destroy an already-computed result (device-global
// files would otherwise stop every scope's search on disk-full).
// ===========================================================================
#[test]
fn r12_5_search_survives_unwritable_metrics_log() {
    let dir = indexed_scope();
    let metrics = dir.path().join(".test-data/kcs/logs/metrics.jsonl");
    fs::create_dir_all(metrics.parent().unwrap()).unwrap();
    fs::write(&metrics, "").unwrap();
    use std::os::unix::fs::PermissionsExt;
    let mut perms = fs::metadata(&metrics).unwrap().permissions();
    perms.set_mode(0o444);
    fs::set_permissions(&metrics, perms).unwrap();
    // The search still succeeds with results (was exit 1 KCS-E-STORE-IO-001).
    let search = json_success(&dir, &["search", "トークン TTL"]);
    assert!(!search["results"].as_array().unwrap().is_empty());
    let mut restore = fs::metadata(&metrics).unwrap().permissions();
    restore.set_mode(0o644);
    fs::set_permissions(&metrics, restore).unwrap();
}

// ===========================================================================
// R12-7: the manual arg parsers (search/repair/reindex) rejected `--flag=value` as
// an unknown flag even though the flag exists, and `--limit 0` was silently clamped
// to 1 (faking success on a meaningless value).
// ===========================================================================
#[test]
fn r12_7_search_accepts_flag_equals_value_syntax() {
    let dir = indexed_scope();
    // `--limit=5` == `--limit 5`.
    let eq = json_success(&dir, &["search", "トークン TTL", "--limit=5"]);
    assert_eq!(eq["paging"]["limit"], 5);
    let space = json_success(&dir, &["search", "トークン TTL", "--limit", "5"]);
    assert_eq!(eq["paging"]["limit"], space["paging"]["limit"]);

    // `--offset=N` and `--scope=.` are accepted (were "unknown search flag").
    let off_eq = json_success(&dir, &["search", "トークン TTL", "--offset=1"]);
    let off_space = json_success(&dir, &["search", "トークン TTL", "--offset", "1"]);
    assert_eq!(off_eq["results"], off_space["results"]);
    let scoped = json_success(&dir, &["search", "トークン TTL", "--scope=."]);
    assert_eq!(scoped["searched_scopes"].as_array().unwrap().len(), 1);
}

// A positional query containing `=` must NOT be split into a flag.
#[test]
fn r12_7_positional_query_with_equals_is_preserved() {
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "ranking=test"]);
    assert_eq!(search["query"], "ranking=test");
}

// `--limit 0` (and `--limit=0`) is a usage error, not a silent clamp to 1.
#[test]
fn r12_7_limit_zero_is_a_usage_error() {
    let dir = indexed_scope();
    let err = json_failure(&dir, &["search", "トークン TTL", "--limit", "0"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");
    let err_eq = json_failure(&dir, &["search", "トークン TTL", "--limit=0"], 2);
    assert_eq!(err_eq["error_code"], "KCS-E-CONFIG-USAGE-001");
    // The upper clamp (100) is unchanged: a large value still succeeds.
    let big = json_success(&dir, &["search", "トークン TTL", "--limit=500"]);
    assert_eq!(big["paging"]["limit"], 100);
}

/// R13-3: `[logs] retention_days` is a real, schema-validated config key. Before
/// the fix docs/06 §13 / docs/10 §12.6 documented "日次ローテ・保持 30 日 (config
/// 上書き可)" but no such key existed, so pasting `[logs] retention_days = 7` into
/// a config bricked EVERY command with exit 2 (additionalProperties:false). Both
/// scope and user config must now accept it (exit 0).
#[test]
fn r13_3_logs_retention_days_accepted_in_scope_config() {
    let dir = indexed_scope();
    write_scope_config(&dir, "[logs]\nretention_days = 7\n");
    // A previously-bricking config now runs cleanly end-to-end.
    json_success(&dir, &["status"]);
    json_success(&dir, &["search", "トークン"]);
}

#[test]
fn r13_3_logs_retention_days_accepted_in_user_config() {
    let dir = indexed_scope();
    let user_cfg = dir.path().join(".test-config/kcs");
    fs::create_dir_all(&user_cfg).unwrap();
    fs::write(
        user_cfg.join("config.toml"),
        "kcs_format_version = \"0.1.0\"\n[logs]\nretention_days = 7\n",
    )
    .unwrap();
    json_success(&dir, &["status"]);
    json_success(&dir, &["search", "トークン"]);
}

/// R13-3 (d) / R12-5: a log write that cannot land (here the device metrics path is
/// occupied by a directory, so both rotation and append fail) must NOT fail the
/// command body — the search result still returns exit 0.
#[test]
fn r13_3_unwritable_log_path_does_not_fail_the_search() {
    let dir = indexed_scope();
    let logs = dir.path().join(".test-data/kcs/logs");
    fs::create_dir_all(&logs).unwrap();
    // Occupy metrics.jsonl with a directory so the append (and any rotation) fails.
    let metrics = logs.join("metrics.jsonl");
    if metrics.exists() {
        fs::remove_file(&metrics).ok();
    }
    fs::create_dir_all(&metrics).unwrap();
    // Search still succeeds despite the broken device log path.
    json_success(&dir, &["search", "トークン"]);
}

/// R13-2(4)/(f): an online embedding adapter that activates via the legacy
/// GEMINI_API_KEY env var with NO tools.toml declaration is env-only drift
/// (docs/07 §7.1). It must be recorded once per run (undeclared-adapter warn),
/// not silently. A bad API base keeps any actual embed attempt hermetic (fast
/// connection refusal → graceful text fallback), so the search still succeeds.
#[test]
fn r13_2_undeclared_env_only_embedding_activation_warns_once() {
    let dir = indexed_scope();
    kcs(&dir, &["search", "トークン"])
        .env("GEMINI_API_KEY", "fake-key-not-used-for-real-http")
        .env("GEMINI_API_BASE", "http://127.0.0.1:1")
        .arg("--json")
        .assert()
        .success();
    let errors =
        fs::read_to_string(dir.path().join(".test-data/kcs/logs/errors.jsonl")).unwrap_or_default();
    let warns = errors
        .lines()
        .filter(|line| line.contains("KCS-W-ADAPTER-UNDECLARED-001"))
        .count();
    assert_eq!(
        warns, 1,
        "env-only (undeclared) activation must warn exactly once per run: {errors}"
    );
}

/// R13-2: write a user tools.toml under the test's XDG_CONFIG_HOME.
fn write_tools_toml(dir: &TempDir, body: &str) {
    let cfg = dir.path().join(".test-config/kcs");
    fs::create_dir_all(&cfg).unwrap();
    fs::write(cfg.join("tools.toml"), body).unwrap();
}

/// R13-2(a): a bogus key / type-mismatch in tools.toml is exit 2 (schema),
/// symmetric with config.toml — before, tools.toml silently accepted it at exit 0.
#[test]
fn r13_2_cli_tools_toml_bogus_key_and_type_are_exit_2() {
    let dir = indexed_scope();
    write_tools_toml(&dir, "[markdown]\ntotally_bogus_key = \"xyz\"\n");
    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");

    write_tools_toml(&dir, "[markdown.x]\ncmd = 12345\n");
    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

/// R13-2(b): the docs/03 §11 + docs/07 §1 copy-paste passes (exit 0) — a
/// documented config must never brick the device (R12-2 lesson).
#[test]
fn r13_2_cli_documented_tools_toml_is_accepted() {
    let dir = indexed_scope();
    write_tools_toml(
        &dir,
        "[markdown.mistral_ocr_markdownize]\n\
         kind = \"online_api\"\n\
         cmd = \"uvx kcs-mistral-ocr-adapter\"\n\
         model = \"mistral-ocr-latest\"\n\
         profile_hash = \"sha256:...\"\n\
         capabilities = [\"ocr\", \"layout_detection\", \"table_extraction\"]\n\
         \n\
         [embedding.gemini_embedding_2]\n\
         auth = \"env:GEMINI_API_KEY\"\n",
    );
    json_success(&dir, &["status"]);
}

/// R13-2(c)/(e): the auth-prefix check is scoped to the `auth` field, so a
/// documented `url = "plain:"` no longer bricks every command (exit 0).
#[test]
fn r13_2_cli_url_plain_prefix_does_not_brick() {
    let dir = indexed_scope();
    write_tools_toml(&dir, "[markdown.x]\nurl = \"plain:\"\n");
    json_success(&dir, &["status"]);
}

/// R13-2(e): a declared `auth = "keychain:<svc>"` is not implemented — when the
/// embedding adapter activates from it (the finding: a declared auth used to be a
/// silent noop), the misconfig must be LOUD (recorded to errors.jsonl as
/// KCS-E-NOT-IMPLEMENTED-001), never silently swallowed.
#[test]
fn r13_2_keychain_auth_is_loud_not_silent() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("note.md"),
        "# 認証\n\nトークン TTL は 3600 秒。スコープは read write admin。\n",
    )
    .unwrap();
    // Declare the embedding adapter with an (unimplemented) keychain auth BEFORE
    // indexing, so `index` activates it and the enrichment pass resolves the auth.
    write_tools_toml(&dir, "[embedding.g]\nauth = \"keychain:login\"\n");
    kcs(&dir, &["init"]).assert().success();
    // The index itself still succeeds (the failed embedding is a counted task), but
    // the keychain misconfig must be recorded loudly.
    let out = json_success(&dir, &["index", "--approve"]);
    assert!(
        out["embedding_tasks_failed"].as_u64().unwrap_or(0) >= 1,
        "the declared keychain adapter must ACTIVATE (fail visibly), not be ignored: {out}"
    );
    let errors =
        fs::read_to_string(dir.path().join(".test-data/kcs/logs/errors.jsonl")).unwrap_or_default();
    assert!(
        errors.contains("KCS-E-NOT-IMPLEMENTED-001"),
        "keychain auth must be recorded loudly, not silently ignored: {errors}"
    );
}
