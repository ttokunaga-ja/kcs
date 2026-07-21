use std::fs;
use std::path::Path;

use assert_cmd::Command;
use kcs_adapter::catalog::{TEST_ADOPTED_EMBEDDING_ENV, TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV};
use serde_json::Value;
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

fn hermetic_kcs_command() -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    for name in KCS_CHILD_ENV_DENYLIST {
        command.env_remove(name);
    }
    command
}

fn hermetic_process_command(bin: &Path) -> std::process::Command {
    let mut command = std::process::Command::new(bin);
    for name in KCS_CHILD_ENV_DENYLIST {
        command.env_remove(name);
    }
    command
}

fn value_path_ends_with(value: &Value, suffix: &str) -> bool {
    value
        .as_str()
        .is_some_and(|path| Path::new(path).ends_with(suffix))
}

fn kcs(dir: &TempDir, args: &[&str]) -> Command {
    let mut command = hermetic_kcs_command();
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
    let output = hermetic_kcs_command()
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

fn read_scope_id(path: &Path) -> String {
    let scope: Value =
        serde_json::from_str(&fs::read_to_string(path.join(".kcs/scope.json")).unwrap()).unwrap();
    scope["scope_id"].as_str().unwrap().to_owned()
}

fn replace_scope_id(path: &Path, scope_id: &str) {
    let scope_path = path.join(".kcs/scope.json");
    let mut scope: Value = serde_json::from_str(&fs::read_to_string(&scope_path).unwrap()).unwrap();
    scope["scope_id"] = serde_json::json!(scope_id);
    fs::write(scope_path, serde_json::to_vec_pretty(&scope).unwrap()).unwrap();
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
    let output = hermetic_kcs_command()
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
    assert!(pointer["byte_start"].as_u64().is_some());
    assert!(pointer["byte_end"].as_u64().is_some());
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
    // new generation's chunk_hash (byte_start/byte_end shift) differs from the
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
fn ct4_current_config_association_is_added_for_deleted_history() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("historical.md"),
        "# Historical\n\nretained-history-config-fixture\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);

    let db_path = dir.path().join(".kcs/index/sqlite.db");
    let conn = rusqlite::Connection::open(&db_path).unwrap();
    let historical_chunk: String = conn
        .query_row(
            "SELECT chunk_id FROM chunks
             WHERE text LIKE '%retained-history-config-fixture%' LIMIT 1",
            [],
            |row| row.get(0),
        )
        .unwrap();
    drop(conn);

    fs::remove_file(dir.path().join("historical.md")).unwrap();
    json_success(&dir, &["index", "--approve"]);
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[chunking]\nstrategy = \"heading\"\nmax_chars = 5999\n",
    )
    .unwrap();
    json_success(&dir, &["index", "--approve"]);

    let conn = rusqlite::Connection::open(&db_path).unwrap();
    let current_config: String = conn
        .query_row(
            "SELECT chunking_config_hash
             FROM chunk_config_generations
             ORDER BY association_rowid DESC LIMIT 1",
            [],
            |row| row.get(0),
        )
        .unwrap();
    let current_association_count: u64 = conn
        .query_row(
            "SELECT COUNT(*) FROM chunk_config_generations
             WHERE chunk_id = ?1 AND chunking_config_hash = ?2",
            rusqlite::params![historical_chunk, current_config],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(
        current_association_count, 1,
        "a config-preserving boundary must append a current-config association even when the normalized instance is historical-only"
    );
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*) FROM chunks WHERE chunk_id = ?1",
            rusqlite::params![historical_chunk],
            |row| row.get::<_, u64>(0),
        )
        .unwrap(),
        1,
        "the immutable chunk row is shared by both config generations"
    );
}

#[test]
fn ct4_historical_only_current_config_chunks_enqueue_embeddings() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("historical.md"),
        "# Historical\n\nretained embedding history alpha bravo charlie delta echo\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed(&dir, "mock", &["index", "--yes"]);
    let conn = rusqlite::Connection::open(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    let historical_raw: String = conn
        .query_row(
            "SELECT raw_hash FROM chunks WHERE text LIKE '%retained embedding history%' LIMIT 1",
            [],
            |row| row.get(0),
        )
        .unwrap();
    drop(conn);

    fs::remove_file(dir.path().join("historical.md")).unwrap();
    json_success_embed(&dir, "mock", &["index", "--yes"]);
    fs::write(
        dir.path().join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[chunking]\nstrategy = \"heading\"\nmax_chars = 24\n",
    )
    .unwrap();
    json_success_embed(&dir, "mock", &["index", "--yes"]);

    let conn = rusqlite::Connection::open(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    let current_config: String = conn
        .query_row(
            "SELECT chunking_config_hash FROM chunk_config_generations
             ORDER BY association_rowid DESC LIMIT 1",
            [],
            |row| row.get(0),
        )
        .unwrap();
    let mut statement = conn
        .prepare(
            "SELECT c.chunk_id FROM chunks c
             WHERE c.raw_hash = ?1
               AND EXISTS (
                   SELECT 1 FROM chunk_config_generations cg
                   WHERE cg.chunk_id = c.chunk_id AND cg.chunking_config_hash = ?2
               )",
        )
        .unwrap();
    let historical_current_ids = statement
        .query_map(rusqlite::params![historical_raw, current_config], |row| {
            row.get::<_, String>(0)
        })
        .unwrap()
        .collect::<std::result::Result<std::collections::BTreeSet<_>, _>>()
        .unwrap();
    assert!(!historical_current_ids.is_empty());

    let status = json_success_embed(&dir, "mock", &["status"]);
    let task_refs = tasks_of_type(&status, "embedding")
        .into_iter()
        .filter_map(|task| task["output_ref"].as_str())
        .collect::<std::collections::BTreeSet<_>>();
    for chunk_id in historical_current_ids {
        assert!(
            task_refs.contains(format!("embedding:{chunk_id}").as_str()),
            "every retained historical current-config chunk needs an embedding task: {status}"
        );
    }
}

#[test]
fn ct4_rebuild_preserves_historical_tree_projection_cache() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("cached.md"), "# C1\n\nfirst snapshot\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    let first = json_success(&dir, &["index", "--approve"]);
    let first_commit = first["commit_hash"].as_str().unwrap().to_owned();

    fs::write(dir.path().join("cached.md"), "# C2\n\nsecond snapshot\n").unwrap();
    let second = json_success(&dir, &["index", "--approve"]);
    let second_commit = second["commit_hash"].as_str().unwrap();
    assert_ne!(first_commit, second_commit);

    let conn = rusqlite::Connection::open(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    for commit in [&first_commit, second_commit] {
        assert_eq!(
            conn.query_row(
                "SELECT COUNT(*) FROM tree_entries
                 WHERE commit_hash = ?1 AND path = 'cached.md'",
                rusqlite::params![commit],
                |row| row.get::<_, u64>(0),
            )
            .unwrap(),
            1,
            "atomic rebuild must retain immutable historical tree cache rows"
        );
    }
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
    assert!(value_path_ends_with(
        &first_result(&search)["scope_path"],
        "b"
    ));
    let searched = search["searched_scopes"].as_array().unwrap();
    assert_eq!(searched.len(), 2, "c (participates=false) must be excluded");
    assert!(searched
        .iter()
        .all(|scope| !value_path_ends_with(&scope["scope_path"], "c")));
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
    assert!(value_path_ends_with(
        &first_result(&search)["scope_path"],
        "b"
    ));
    assert_eq!(search["searched_scopes"].as_array().unwrap().len(), 2);
}

// R15-3: a `.kcs` deleted and re-`init`ed at the SAME path mints a fresh scope_id.
// The device registry keyed the old row by `(scope_id, kcs_path)`, so it survived — and
// multi-scope search then enumerated the SAME `.kcs` twice (once per scope_id), double-
// returning every document, the stale copy carrying a dead-pointer scope_id whose
// Evidence can no longer resolve. `register_scope` now retires the stale same-path row on
// re-init, and the search enumeration additionally drops any row whose on-disk scope_id
// no longer matches — a re-init'd scope is searched exactly once.
#[test]
fn r15_3_reinit_same_path_does_not_duplicate_registry_target() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let b = parent.path().join("b");
    fs::create_dir_all(&b).unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Sec\nunique reinit token 7331\n").unwrap();

    // Scope A: init + index at `b` (registers (scope_A, b/.kcs), indexed).
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);

    // Delete `.kcs` and re-init + index → scope B (fresh scope_id) at the SAME path.
    fs::remove_dir_all(b.join(".kcs")).unwrap();
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);

    // `--all-scopes` enumerates the registry. The stale (scope_A) row must be gone:
    // exactly one scope target, and the document returned exactly once (no dead-pointer
    // duplicate). Pre-fix this was 2 searched scopes and 2 identical results.
    let search = json_success_path(
        &b,
        &data_home,
        &["search", "unique reinit token 7331", "--all-scopes"],
    );
    assert_eq!(
        search["searched_scopes"].as_array().unwrap().len(),
        1,
        "a re-init'd scope must be searched exactly once (stale scope_id retired): {search}"
    );
    assert_eq!(
        search["results"].as_array().unwrap().len(),
        1,
        "the document must not be double-returned via a dead scope_id: {search}"
    );
}

// scope-cross merge is rank-based: both scopes' rank-1 hits get the SAME RRF score
// (1/(60+1)) despite skewed corpus statistics, and tie-break is (scope_id, ...).
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
    // Make immutable scope-id order intentionally oppose mutable path order.
    // This catches accidental reintroduction of the old scope_path tie-break.
    replace_scope_id(&a, "7ZZZZZZZZZZZZZZZZZZZZZZZZZ");
    replace_scope_id(&b, "00000000000000000000000001");
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);
    let search = json_success_path(&a, &data_home, &["search", "zephyrterm"]);
    let results = search["results"].as_array().unwrap();
    assert_eq!(results.len(), 2);
    // Identical RRF score proves the merge compares ranks, not raw BM25.
    assert_eq!(results[0]["score"], results[1]["score"]);
    let expected = 1.0f64 / 61.0;
    assert!((results[0]["score"].as_f64().unwrap() - expected).abs() < 1e-12);
    // Deterministic tie-break by scope_id: b's low id precedes a's high id even
    // though registry/input order is path a then path b.
    assert!(value_path_ends_with(&results[0]["scope_path"], "b"));
    assert!(value_path_ends_with(&results[1]["scope_path"], "a"));
}

#[test]
fn ct3_multi_006_completion_order_does_not_change_results_or_cursor() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## Sec\norderstable token\n").unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Sec\norderstable token\n").unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    replace_scope_id(&a, "7ZZZZZZZZZZZZZZZZZZZZZZZZZ");
    replace_scope_id(&b, "00000000000000000000000001");
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);
    fs::write(
        a.join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[search.multi_scope]\nparallelism = 2\n",
    )
    .unwrap();

    let baseline = json_success_path(&a, &data_home, &["search", "orderstable", "--limit", "1"]);
    let delayed_output = hermetic_kcs_command()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        // Registry/input order is a then b. Delay a so b completes first.
        .env(
            "KCS_TEST_SCOPE_SEARCH_DELAY_SCOPE_ID",
            "7ZZZZZZZZZZZZZZZZZZZZZZZZZ",
        )
        .env("KCS_TEST_SCOPE_SEARCH_DELAY_MS", "300")
        .args(["search", "orderstable", "--limit", "1", "--json"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let delayed: Value = serde_json::from_slice(&delayed_output).unwrap();

    assert!(baseline["paging"]["next_cursor"].is_string());
    assert_eq!(delayed["results"], baseline["results"]);
    assert_eq!(delayed["searched_scopes"], baseline["searched_scopes"]);
    assert_eq!(delayed["excluded_scopes"], baseline["excluded_scopes"]);
    assert_eq!(delayed["paging"], baseline["paging"]);
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
#[cfg(unix)]
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

    let output = hermetic_kcs_command()
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
    assert!(value_path_ends_with(&excluded[0]["scope_path"], "b"));
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

#[test]
fn ct3_multi_006_timeout_preserves_fresh_all_failed_and_cursor_contracts() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## Sec\ntimeouttoken alpha\n").unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Sec\ntimeouttoken beta\n").unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);
    fs::write(
        a.join(".kcs/config.toml"),
        "kcs_format_version = \"0.1.0\"\n[search.multi_scope]\nparallelism = 2\nper_scope_timeout_seconds = 1\n",
    )
    .unwrap();
    let b_scope_id = read_scope_id(&b);

    // A fresh search isolates the timed-out scope, returns the healthy result,
    // and uses the established partial-failure exit 3 payload contract.
    let partial_output = hermetic_kcs_command()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .env("KCS_TEST_SCOPE_SEARCH_DELAY_SCOPE_ID", &b_scope_id)
        .env("KCS_TEST_SCOPE_SEARCH_DELAY_MS", "2500")
        .args(["search", "timeouttoken", "--json"])
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let partial: Value = serde_json::from_slice(&partial_output).unwrap();
    assert_eq!(partial["searched_scopes"].as_array().unwrap().len(), 1);
    assert_eq!(partial["excluded_scopes"].as_array().unwrap().len(), 1);
    assert_eq!(partial["excluded_scopes"][0]["scope_id"], b_scope_id);
    assert_eq!(partial["excluded_scopes"][0]["reason"], "timeout");
    assert!(!partial["results"].as_array().unwrap().is_empty());
    assert!(partial.get("__exit_code").is_none());

    // With only the delayed scope selected, the same reason participates in the
    // established all-scopes-failed exit 4 aggregation.
    let b_arg = b.display().to_string();
    let all_failed = hermetic_kcs_command()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .env("KCS_TEST_SCOPE_SEARCH_DELAY_SCOPE_ID", &b_scope_id)
        .env("KCS_TEST_SCOPE_SEARCH_DELAY_MS", "2500")
        .args(["search", "timeouttoken", "--scope", &b_arg, "--json"])
        .assert()
        .code(4)
        .get_output()
        .stderr
        .clone();
    let all_failed: Value = serde_json::from_slice(&all_failed).unwrap();
    assert_eq!(
        all_failed["error_code"],
        "KCS-E-SEARCH-SCOPE-ALL-FAILED-001"
    );
    assert_eq!(
        all_failed["context"]["excluded_scopes"][0]["reason"],
        "timeout"
    );

    // Cursor replay cannot shrink its frozen active set. A timeout therefore
    // hard-fails with no partial stdout or replacement cursor.
    let first = json_success_path(&a, &data_home, &["search", "timeouttoken", "--limit", "1"]);
    let cursor = first["paging"]["next_cursor"].as_str().unwrap();
    let replay = hermetic_kcs_command()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .env("KCS_TEST_SCOPE_SEARCH_DELAY_SCOPE_ID", &b_scope_id)
        .env("KCS_TEST_SCOPE_SEARCH_DELAY_MS", "2500")
        .args([
            "search",
            "timeouttoken",
            "--limit",
            "1",
            "--cursor",
            cursor,
            "--json",
        ])
        .output()
        .unwrap();
    assert_eq!(replay.status.code(), Some(2));
    assert!(
        replay.stdout.is_empty(),
        "cursor failure must not emit a page"
    );
    let replay_error: Value = serde_json::from_slice(&replay.stderr).unwrap();
    assert_eq!(replay_error["error_code"], "KCS-E-SEARCH-CURSOR-001");
    assert_eq!(replay_error["context"]["cause"], "timeout");
}

// Step 4 cursor v2 freezes the complete active scope set. Losing any active
// scope makes replay non-reproducible, so replay hard-fails and instructs a
// fresh search instead of silently shrinking to the surviving scopes.
#[test]
fn ct4_cursor_replay_with_unresolvable_active_scope_hard_fails() {
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

    let (code, error) = run_json(
        &b,
        &data_home,
        &[
            "search",
            "共通トピック",
            "--cursor",
            &cursor,
            "--limit",
            "5",
        ],
    );
    assert_eq!(code, 2, "active-scope loss is a cursor misuse: {error}");
    assert_eq!(error["error_code"], "KCS-E-SEARCH-CURSOR-001");
    assert_eq!(error["context"]["reason"], "active_scope_unavailable");
    assert_eq!(error["context"]["scope_id"], a_scope_id);
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
    let output = hermetic_kcs_command()
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

/// CAS object path: `<kcs>/objects/<kind>/ab/cd/<digest>` (kcs_core::cas::fanout).
fn object_path(kcs_dir: &Path, kind: &str, hash: &str) -> std::path::PathBuf {
    let digest = hash.strip_prefix("sha256:").unwrap();
    kcs_dir
        .join("objects")
        .join(kind)
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(digest)
}

/// Tombstone path: `<kcs>/tombstones/ab/cd/<raw-digest>` (05 §3.5).
fn tombstone_path(kcs_dir: &Path, raw_hash: &str) -> std::path::PathBuf {
    let digest = raw_hash.strip_prefix("sha256:").unwrap();
    kcs_dir
        .join("tombstones")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(digest)
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
    // (a) tombstoned -> status="tombstoned" response, open exit 4.
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
    assert_eq!(err["context"]["status"], "tombstoned");
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

// Step 4 all-history keeps a deleted chunk active while its exact normalized
// binding remains reachable. Its embedding task is real pending history work,
// not a HEAD-only phantom to terminalize.
#[test]
fn ct4_deleted_historical_chunk_embedding_stays_pending() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("keep.md"),
        "# Keep\n\n## Body\n生き残るチャンクの本文です。\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("drop.md"),
        "# Drop\n\n## Body\n削除されるチャンクの本文です。\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Offline embedding (opt-in recorded, network_opt_in=false) → tasks stay Pending.
    json_success_embed(&dir, "mock", &["index", "--yes"]);

    let before = json_success_embed(&dir, "mock", &["status"]);
    let pending_before = tasks_of_type(&before, "embedding")
        .iter()
        .filter(|task| task["status"] == "pending")
        .count();
    assert!(
        pending_before >= 2,
        "both files' chunks start pending: {before}"
    );
    let count_before = json_success_embed(&dir, "mock", &["search", "本文"])["index_status"]
        ["pending_enrichment_tasks"]
        .as_u64()
        .unwrap();

    // Delete drop.md and re-index: its chunk remains reachable through history.
    fs::remove_file(dir.path().join("drop.md")).unwrap();
    json_success_embed(&dir, "mock", &["index", "--yes"]);

    let after = json_success_embed(&dir, "mock", &["status"]);
    let emb_after = tasks_of_type(&after, "embedding");
    assert!(
        emb_after.iter().all(|task| task["status"] == "pending"),
        "retained historical embedding tasks remain genuine pending work: {after}"
    );
    // The surviving file still has a pending embedding task (no over-terminalization).
    assert!(
        emb_after.iter().any(|task| task["status"] == "pending"),
        "the live file's embedding task must stay pending: {after}"
    );
    // Both live and historical gaps remain in index_status.
    let count_after = json_success_embed(&dir, "mock", &["search", "本文"])["index_status"]
        ["pending_enrichment_tasks"]
        .as_u64()
        .unwrap();
    assert!(
        count_after == count_before,
        "deletion must not retire retained-history embedding work: {count_before} -> {count_after}"
    );
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
    let output = hermetic_kcs_command()
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
    assert!(value_path_ends_with(&excluded[0]["scope_path"], "b"));
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
// object lives only under objects/image; it resolves via object/image/<hash>
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
    let image_obj = object_path(&kcs_dir, "image", &image_hash);
    fs::create_dir_all(image_obj.parent().unwrap()).unwrap();
    fs::write(&image_obj, bytes).unwrap();

    // Correct dispatch: image resolves from objects/image.
    let opened = json_success(
        &dir,
        &[
            "open",
            &format!("kcs://{scope_id}/object/image/{image_hash}"),
        ],
    );
    assert_eq!(opened["object_type"], "image");
    assert!(Path::new(opened["path"].as_str().unwrap()).is_file());
    // Same hash under object/raw must NOT resolve (the bytes live only under image).
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

// Step 4 implements exact snapshot search; HEAD is a canonical commit selector.
#[test]
fn ct4_search_at_head_is_implemented() {
    let dir = indexed_scope();
    let result = json_success(&dir, &["search", "認証仕様", "--at", "HEAD"]);
    assert!(!result["results"].as_array().unwrap().is_empty());
    assert_eq!(
        result["results"][0]["evidence_pointer"]["commit"],
        result["searched_scopes"][0]["snapshot_at"]
    );
}

/// R9-6: every remaining KCS-E-CONFIG-NOT-IMPLEMENTED-001 path exits with the
/// canonical class 1. Step 4 implements search-at, historical reindex, and object
/// verification, so none of those completed paths belongs here.
#[test]
fn r9_6_not_implemented_exit_code_is_uniform() {
    let dir = indexed_scope();
    let args = ["log", "--at", "HEAD"];
    let err = json_failure(&dir, &args, 1);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-NOT-IMPLEMENTED-001");
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

    // Case variants normalize to the same reserved hash operand. This must be
    // rejected semantically as a hash collision, not merely because `:` is an
    // invalid portable-leaf character.
    let uppercase_hash_name = format!("SHA256:{}", "A".repeat(64));
    let err = json_failure(&dir, &["tag", &uppercase_hash_name], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001");
    assert!(err["message"].as_str().unwrap().contains("commit hash"));

    // A normal tag name still resolves HEAD and is created.
    let ok = json_success(&dir, &["tag", "v1"]);
    assert!(
        ok["commit_hash"].as_str().is_some(),
        "tag v1 should succeed: {ok}"
    );
    assert!(Path::new(ok["path"].as_str().unwrap()).is_file());
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

// (a) / O1: a cursor minted for another scope cannot bypass a --scope restriction.
// Step 4 v2 rejects any restriction that drops a frozen active scope; a
// tampered/forged cursor also fails HMAC verification.
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
    // The active vault scope cannot be intersected out of a signed v2 replay.
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
        code, 2,
        "dropping an active cursor scope is rejected: {resp}"
    );
    assert_eq!(resp["error_code"], "KCS-E-SEARCH-CURSOR-001");
    assert_eq!(resp["context"]["reason"], "active_scope_unavailable");

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
    hermetic_kcs_command()
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
    hermetic_kcs_command()
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
        hermetic_process_command(&bin)
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
                let _ = hermetic_process_command(&bin)
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
        hermetic_process_command(&bin)
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
                let _ = hermetic_process_command(&bin)
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
fn r6_reindex_rejects_force_at_and_extra_operands() {
    let dir = indexed_scope();
    // Step 4 decision #67: historical enrichment and generation-forcing are
    // mutually exclusive. The extra positional remains a usage error too.
    let at = json_failure(&dir, &["reindex", "--force", "--yes", "--at", "HEAD"], 2);
    assert_eq!(at["error_code"], "KCS-E-CONFIG-USAGE-001");
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

    // R16-4: a corrupt normalized unit no longer aborts the whole rebuild — repair
    // SKIPS that document, recording it under KCS-E-STORE-CORRUPT-001 (the original R6
    // concern: NOT a CONFIG-SCHEMA misclassification) with recovery guidance, instead
    // of the former whole-scope exit-4 failure.
    let out = json_success(&dir, &["repair", "--rebuild-db"]);
    let skipped = out["skipped_units"].as_array().unwrap();
    assert_eq!(
        skipped.len(),
        1,
        "the corrupt unit's document is skipped: {out}"
    );
    assert_eq!(skipped[0]["reason"], "KCS-E-STORE-CORRUPT-001");
    assert_ne!(skipped[0]["reason"], "KCS-E-CONFIG-SCHEMA-001");
    assert_eq!(skipped[0]["path"], "note.md");
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
    let output = hermetic_kcs_command()
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
fn r7_repair_rejects_unknown_flags_and_extra_operands() {
    let dir = indexed_scope();
    let unknown = json_failure(
        &dir,
        &["repair", "--rebuild-db", "--definitely-invalid", "EXTRA"],
        2,
    );
    assert_eq!(unknown["error_code"], "KCS-E-CONFIG-USAGE-001");

    let verify = json_success(&dir, &["repair", "--verify-objects"]);
    assert_eq!(verify["status"], "ok");
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

// R17-2/R17-6: locate a normalized-instance `manifest.json` (one per document per gen).
fn first_manifest_json(root: &Path) -> std::path::PathBuf {
    let mut stack = vec![root.to_path_buf()];
    while let Some(path) = stack.pop() {
        for entry in fs::read_dir(&path).unwrap() {
            let entry = entry.unwrap();
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            if path.file_name().and_then(|name| name.to_str()) == Some("manifest.json") {
                return path;
            }
        }
    }
    panic!(
        "normalized instance manifest not found under {}",
        root.display()
    );
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

// [search.multi_scope] is a live execution setting; both documented keys are
// accepted and the hard worker ceiling rejects accidental oversubscription.
#[test]
fn r12_1_multi_scope_config_is_wired_and_bounded() {
    let dir = multi_chunk_scope();
    write_scope_config(
        &dir,
        "[search.multi_scope]\nparallelism = 4\nper_scope_timeout_seconds = 2\n",
    );
    json_success(&dir, &["search", "sharedtoken"]);

    write_scope_config(&dir, "[search.multi_scope]\nparallelism = 5\n");
    let error = json_failure(&dir, &["search", "sharedtoken"], 2);
    assert_eq!(error["error_code"], "KCS-E-CONFIG-SCHEMA-001");
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

#[test]
fn r23_materialized_embedding_completes_legacy_failed_task_without_charge() {
    let dir = indexed_scope_embed("mock");
    let tasks_path = dir.path().join(".kcs/tasks.jsonl");
    let original = fs::read_to_string(&tasks_path).unwrap();
    let mut rewritten = String::new();
    let mut changed_task_id = None;
    for line in original.lines() {
        let mut task: Value = serde_json::from_str(line).unwrap();
        if changed_task_id.is_none() && task["type"] == "embedding" && task["status"] == "done" {
            changed_task_id = task["task_id"].as_str().map(str::to_owned);
            task["status"] = Value::from("failed");
            task["fallback_reason"] = Value::from("contract_violation");
            task["attempts"] = Value::from(1);
            let object = task.as_object_mut().unwrap();
            object.remove("reservation_id");
            object.remove("reserved_month");
            object.remove("reserved_usd");
        }
        rewritten.push_str(&serde_json::to_string(&task).unwrap());
        rewritten.push('\n');
    }
    let changed_task_id = changed_task_id.expect("fixture must have a done embedding task");
    fs::write(&tasks_path, rewritten).unwrap();
    let ledger_before = embedding_ledger_rows(&dir);

    let reindex = json_success_embed(&dir, "mock", &["index", "--approve"]);
    assert_eq!(reindex["embedding_tasks_executed"], 0);
    assert_eq!(embedding_ledger_rows(&dir), ledger_before);

    let tasks = fs::read_to_string(&tasks_path).unwrap();
    let recovered = tasks
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .find(|task| task["task_id"] == changed_task_id)
        .unwrap();
    assert_eq!(recovered["status"], "done");
    assert_eq!(recovered["fallback_reason"], "embedding_adapter_done");
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
#[cfg(unix)]
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
    hermetic_kcs_command()
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
#[cfg(unix)]
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

/// CAND-038/039: executable targets unsupported by the built-in runtime fail closed.
#[test]
fn r13_2_cli_unsupported_documented_targets_are_rejected() {
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
    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
}

/// CAND-038: a URL on an unknown/custom markdown target is never silently ignored.
#[test]
fn r13_2_cli_custom_url_is_rejected() {
    let dir = indexed_scope();
    write_tools_toml(&dir, "[markdown.x]\nurl = \"plain:\"\n");
    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
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
    write_tools_toml(
        &dir,
        "[embedding.gemini_embedding_2]\nauth = \"keychain:login\"\n",
    );
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

// ---------------------------------------------------------------------------
// R16 exploratory audit fixes — store-corruption / shallow-consistency cluster.
// A *deleted* CAS object (KCS-E-STORE-NOT-FOUND-001) is the shallow class these
// tests place by hand (05 §2.2 has no Step 3 GC generator); a *corrupted* object
// (hash mismatch → KCS-E-STORE-CORRUPT-001) is a distinct class exercised by R16-2.
// ---------------------------------------------------------------------------

/// Read a scope's HEAD commit hash from its `.kcs/HEAD`.
fn head_commit(kcs_dir: &Path) -> String {
    fs::read_to_string(kcs_dir.join("HEAD"))
        .unwrap()
        .trim()
        .to_owned()
}

// R16-1: a missing HEAD *commit* object (not merely its tree) is the same shallow
// corruption class R13-4/R15-4 defend against, but every `read_commit` call site was
// an unconditional `?`. Pure reads (status/log/search) must degrade to exit 0;
// writes (snapshot/index/reindex/repair) must reject with a clear COMMIT-SHALLOW;
// restoring the object heals everything. Before the fix all of these bricked exit 4
// on a raw KCS-E-STORE-NOT-FOUND-001.
// R17-1: `view`/`open` are the Evidence-*authenticity* entry point, NOT pure reads —
// a missing commit object there is rejected as EVIDENCE-POINTER-INVALID (exit 4), not
// degraded, because a forged/absent commit must not bypass the tree-membership + N5
// gen checks. See r17_1_* below; this test asserts the read-degrade + write-reject
// halves and the (now rejecting) view.
#[test]
fn r16_1_missing_commit_object_degrades_reads_and_rejects_writes() {
    let dir = indexed_scope();
    // Capture a valid Evidence pointer while the scope is healthy.
    let search0 = json_success(&dir, &["search", "トークン TTL 3600"]);
    let ptr = first_result(&search0)["evidence_pointer"].to_string();

    let kcs_dir = dir.path().join(".kcs");
    let head = head_commit(&kcs_dir);
    let commit_path = object_path(&kcs_dir, "commits", &head);
    let commit_bytes = fs::read(&commit_path).unwrap();

    // Delete the HEAD COMMIT object; its tree survives — exactly the R16-1 corruption.
    fs::remove_file(&commit_path).unwrap();

    // (a) pure reads degrade to exit 0, never a raw KCS-E-STORE-NOT-FOUND-001.
    let status = json_success(&dir, &["status"]);
    assert_eq!(
        status["head_shallow"], true,
        "status must flag the shallow HEAD: {status}"
    );
    let log = json_success(&dir, &["log"]);
    assert_eq!(
        log["truncated"], true,
        "log must flag truncation at the missing HEAD commit: {log}"
    );
    assert!(
        log["commits"].as_array().unwrap().is_empty(),
        "no commit is readable from the missing HEAD: {log}"
    );
    // search degrades via the cached tree_entries rows (ShallowCachedRows) — real
    // results, exit 0 — rather than dying or silently emptying (R16-1 × R16-3 seam).
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    assert!(
        !search["results"].as_array().unwrap().is_empty(),
        "search must degrade to cached results, not brick: {search}"
    );
    // R17-1: view/open are the Evidence-authenticity gate, so a missing commit object
    // is REJECTED (EVIDENCE-POINTER-INVALID exit 4), not degraded like the pure reads
    // above — a missing/forged commit must not skip the tree-membership + N5 gen
    // checks. (Before R17-1 this returned commit_shallow:true exit 0.)
    let view_err = json_failure(&dir, &["view", &ptr], 4);
    assert_eq!(
        view_err["error_code"], "KCS-E-EVIDENCE-POINTER-INVALID-001",
        "view must reject a missing commit object, not degrade: {view_err}"
    );
    let open_err = json_failure(&dir, &["open", &ptr], 4);
    assert_eq!(
        open_err["error_code"], "KCS-E-EVIDENCE-POINTER-INVALID-001",
        "open must reject a missing commit object, not degrade: {open_err}"
    );

    // (b) writes reject with COMMIT-SHALLOW (exit 1), not a raw STORE-NOT-FOUND. Edit a
    // file first so `index`'s unchanged-scope short-circuit still reaches the snapshot.
    fs::write(
        dir.path().join("auth.md"),
        "# 認証仕様\n\n## API\n更新された本文です。\n",
    )
    .unwrap();
    for (args, label) in [
        (vec!["snapshot", "-m", "x"], "snapshot"),
        (vec!["index", "--yes"], "index"),
        (vec!["reindex", "--force", "--yes"], "reindex"),
        (vec!["repair", "--rebuild-db"], "repair"),
    ] {
        let err = json_failure(&dir, &args, 1);
        assert_eq!(
            err["error_code"], "KCS-E-COMMIT-SHALLOW-001",
            "{label} must reject the missing commit with COMMIT-SHALLOW: {err}"
        );
    }

    // (c) restore the commit object → reads are healthy again.
    fs::write(&commit_path, &commit_bytes).unwrap();
    let status2 = json_success(&dir, &["status"]);
    assert_eq!(
        status2["head_shallow"], false,
        "restore must clear the shallow flag: {status2}"
    );
    let log2 = json_success(&dir, &["log"]);
    assert_eq!(log2["truncated"], false);
    assert!(!log2["commits"].as_array().unwrap().is_empty());
}

// R17-1: `view`/`open` are the Evidence-authenticity entry point. A pointer whose
// `commit` is a FORGED hash (a well-formed sha256 naming no object) must be rejected
// as EVIDENCE-POINTER-INVALID (exit 4), NOT resolved best-effort as if it were a
// shallow commit — otherwise the tree-membership + N5 gen checks are both skipped and
// forged evidence resolves. A GENUINE shallow commit (commit present, tree GC'd) must
// still resolve directly (R17-1 narrows the best-effort path, it does not remove it).
#[test]
fn r17_1_forged_commit_pointer_rejected_while_true_shallow_resolves() {
    // (a) forged commit hash → view/open reject.
    let dir = indexed_scope();
    let search = json_success(&dir, &["search", "トークン TTL 3600"]);
    let genuine = first_result(&search)["evidence_pointer"].clone();
    // Control: the untampered pointer resolves, non-shallow.
    let ok = json_success(&dir, &["view", &genuine.to_string()]);
    assert_eq!(ok["commit_shallow"], false, "control must resolve: {ok}");

    let forged_commit = format!("sha256:{}", "0".repeat(64));
    let mut forged = genuine.clone();
    forged["commit"] = serde_json::json!(forged_commit);
    let view_err = json_failure(&dir, &["view", &forged.to_string()], 4);
    assert_eq!(
        view_err["error_code"], "KCS-E-EVIDENCE-POINTER-INVALID-001",
        "a forged commit hash must be rejected by view: {view_err}"
    );
    let open_err = json_failure(&dir, &["open", &forged.to_string()], 4);
    assert_eq!(
        open_err["error_code"], "KCS-E-EVIDENCE-POINTER-INVALID-001",
        "a forged commit hash must be rejected by open: {open_err}"
    );

    // (b) genuine shallow commit (tree object GC'd, commit present) → still resolves
    // directly, commit_shallow:true exit 0. Fresh scope so (a) cannot mask a regression.
    let dir2 = indexed_scope();
    let search2 = json_success(&dir2, &["search", "トークン TTL 3600"]);
    let pointer2 = first_result(&search2)["evidence_pointer"].clone();
    let kcs_dir2 = dir2.path().join(".kcs");
    let commit2 = pointer2["commit"].as_str().unwrap();
    let commit_obj: Value =
        serde_json::from_slice(&fs::read(object_path(&kcs_dir2, "commits", commit2)).unwrap())
            .unwrap();
    let tree2 = commit_obj["tree"].as_str().unwrap();
    fs::remove_file(object_path(&kcs_dir2, "trees", tree2)).unwrap();
    let viewed = json_success(&dir2, &["view", &pointer2.to_string()]);
    assert_eq!(
        viewed["commit_shallow"], true,
        "a genuine shallow commit must still resolve directly: {viewed}"
    );
    assert!(viewed["text"].as_str().unwrap().contains("トークン TTL"));
    let opened = json_success(&dir2, &["open", &pointer2.to_string()]);
    assert_eq!(
        opened["commit_shallow"], true,
        "genuine shallow open must resolve: {opened}"
    );
}

// R17-1 / N5 contrast (the core harm): after `reindex --force` advances the
// normalization generation, a pointer that keeps a REAL old commit but splices in a
// gen-1 chunk_hash is rejected by the N5 gen binding (Attack A). Attack B — the SAME
// gen-1 chunk under a FORGED commit — must be rejected TOO (identically), instead of
// resolving best-effort with the gen check skipped. The only difference between the
// two attacks is the truthful-vs-forged commit field.
#[test]
fn r17_1_n5_forged_commit_cannot_bypass_generation_binding() {
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

    // Attack A: real old commit + gen-1 chunk → rejected by the N5 gen binding.
    let mut attack_a = old_pointer.clone();
    attack_a["chunk_hash"] = new_chunk_hash;
    let err_a = json_failure(&dir, &["view", &attack_a.to_string()], 4);
    assert_eq!(
        err_a["error_code"], "KCS-E-EVIDENCE-POINTER-INVALID-001",
        "old commit + new-gen chunk must be rejected (N5): {err_a}"
    );

    // Attack B: forged commit + gen-1 chunk → BEFORE R17-1 this resolved exit 0
    // (commit_shallow:true), because the missing commit collapsed onto the shallow
    // path and skipped the gen binding. Now it is rejected identically to Attack A.
    let mut attack_b = attack_a.clone();
    attack_b["commit"] = serde_json::json!(format!("sha256:{}", "0".repeat(64)));
    let err_b = json_failure(&dir, &["view", &attack_b.to_string()], 4);
    assert_eq!(
        err_b["error_code"], "KCS-E-EVIDENCE-POINTER-INVALID-001",
        "forged commit + new-gen chunk must NOT bypass the gen binding (R17-1): {err_b}"
    );
}

// R16-1: `log` truncates at a missing ANCESTOR commit and returns the healthy prefix
// from HEAD (Sonnet-B's repro: a missing root commit must not swallow the healthy
// recent commits too). Reads that only need HEAD stay fully healthy.
#[test]
fn r16_1_log_truncates_at_missing_ancestor_commit() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("d.md"), "# D\n\n## S\nv1 body\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    let c1 = json_success(&dir, &["snapshot", "-m", "first"]);
    let c1_hash = c1["commit_hash"].as_str().unwrap().to_owned();
    fs::write(dir.path().join("d.md"), "# D\n\n## S\nv2 body\n").unwrap();
    let c2 = json_success(&dir, &["snapshot", "-m", "second"]);
    let c2_hash = c2["commit_hash"].as_str().unwrap().to_owned();

    // (control) a healthy log returns both commits, HEAD-first, not truncated.
    let full = json_success(&dir, &["log"]);
    assert_eq!(full["truncated"], false);
    assert_eq!(full["commits"].as_array().unwrap().len(), 2);

    // Delete the ROOT commit object (c1); HEAD (c2) survives.
    let kcs_dir = dir.path().join(".kcs");
    fs::remove_file(object_path(&kcs_dir, "commits", &c1_hash)).unwrap();

    let log = json_success(&dir, &["log"]);
    assert_eq!(
        log["truncated"], true,
        "a missing ancestor must flag truncation: {log}"
    );
    let commits = log["commits"].as_array().unwrap();
    assert_eq!(
        commits.len(),
        1,
        "the healthy HEAD prefix must still return: {log}"
    );
    assert_eq!(commits[0]["commit_hash"], c2_hash);
    // status only needs HEAD (c2), which is present → not shallow.
    let status = json_success(&dir, &["status"]);
    assert_eq!(
        status["head_shallow"], false,
        "HEAD present → status is not shallow: {status}"
    );
}

// R16-2: a store-corruption failure in ONE scope must not abort a multi-scope search
// and discard the healthy scopes' already-collected results (05 §1.8 per-scope
// isolation). A CORRUPTED (hash-mismatch) HEAD commit object in scope B surfaces a
// KCS-E-STORE-CORRUPT-001 Fatal (a class NOT absorbed as shallow); the loop downgrades
// it to Excluded("store_corrupt") so scope A still returns → exit 3. Before the fix the
// whole search died exit 4.
#[test]
fn r16_2_one_scope_store_corruption_is_partial_not_all_failed() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## Sec\nalphaunique survivor\n").unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Sec\nbetaunique other\n").unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);

    // (control) both scopes healthy → the search reaches both.
    let healthy = json_success_path(&a, &data_home, &["search", "alphaunique", "--all-scopes"]);
    assert_eq!(healthy["searched_scopes"].as_array().unwrap().len(), 2);

    // Corrupt scope B's HEAD commit object: garbage bytes → content hash mismatch →
    // read_by_hash returns KCS-E-STORE-CORRUPT-001 (distinct from the shallow /
    // STORE-NOT-FOUND class, so only R16-2's Fatal downgrade can catch it).
    let b_kcs = b.join(".kcs");
    let b_head = head_commit(&b_kcs);
    fs::write(
        object_path(&b_kcs, "commits", &b_head),
        b"this is not a valid commit object",
    )
    .unwrap();

    let output = hermetic_kcs_command()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .args(["search", "alphaunique", "--all-scopes", "--json"])
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let search: Value = serde_json::from_slice(&output).unwrap();
    assert!(
        !search["results"].as_array().unwrap().is_empty(),
        "healthy scope A must still return results: {search}"
    );
    assert_eq!(search["searched_scopes"].as_array().unwrap().len(), 1);
    let excluded = search["excluded_scopes"].as_array().unwrap();
    assert_eq!(excluded.len(), 1);
    assert_eq!(excluded[0]["reason"], "store_corrupt");
    assert!(value_path_ends_with(&excluded[0]["scope_path"], "b"));
}

// R16-3: a fresh search against a scope whose HEAD advanced via a bare `snapshot`
// (tree_entries NOT projected) and whose new tree object was then discarded must
// EXCLUDE that scope with reason "snapshot_shallow" — not silently place it in
// searched_scopes with an empty result set (exit 0), the P10-type silent
// false-negative GPT-5.5 found in the fresh path's dropped `Ok(false)`.
#[test]
fn r16_3_fresh_search_shallow_no_rows_excludes_not_silent_empty() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## Sec\nalphaunique survivor\n").unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Sec\nbetashared token\n").unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);

    // Advance scope B's HEAD with a bare snapshot — the new commit's tree_entries are
    // NOT projected (only index/reindex project) — then discard its tree object. B's
    // HEAD is now shallow with NO cached rows for the new commit (ShallowNoRows).
    fs::write(b.join("b.md"), "# B\n\n## Sec\nbetashared token v2\n").unwrap();
    let snap = json_success_path(&b, &data_home, &["snapshot", "-m", "advance"]);
    let b2 = snap["commit_hash"].as_str().unwrap().to_owned();
    let b_kcs = b.join(".kcs");
    let b2_obj: Value =
        serde_json::from_slice(&fs::read(object_path(&b_kcs, "commits", &b2)).unwrap()).unwrap();
    fs::remove_file(object_path(
        &b_kcs,
        "trees",
        b2_obj["tree"].as_str().unwrap(),
    ))
    .unwrap();

    let output = hermetic_kcs_command()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .args(["search", "alphaunique", "--all-scopes", "--json"])
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let search: Value = serde_json::from_slice(&output).unwrap();
    assert!(
        !search["results"].as_array().unwrap().is_empty(),
        "healthy scope A must still return results: {search}"
    );
    // Scope B is EXCLUDED loudly, not silently searched-with-empty-results.
    assert_eq!(search["searched_scopes"].as_array().unwrap().len(), 1);
    let excluded = search["excluded_scopes"].as_array().unwrap();
    assert_eq!(excluded.len(), 1);
    assert_eq!(excluded[0]["reason"], "snapshot_shallow");
    assert!(value_path_ends_with(&excluded[0]["scope_path"], "b"));
}

// R16-4(a): `repair --rebuild-db` — the only implemented recovery command — must not
// die on the very shallow-HEAD corruption it exists to recover from. A discarded HEAD
// tree object yields a clear COMMIT-SHALLOW (via the shared rebuilder), not a raw
// KCS-E-STORE-NOT-FOUND-001 (R15-4 fixed reindex but its fix skipped repair).
#[test]
fn r16_4_repair_on_shallow_head_reports_commit_shallow() {
    let dir = indexed_scope();
    let kcs_dir = dir.path().join(".kcs");
    let head = head_commit(&kcs_dir);
    let commit_obj: Value =
        serde_json::from_slice(&fs::read(object_path(&kcs_dir, "commits", &head)).unwrap())
            .unwrap();
    fs::remove_file(object_path(
        &kcs_dir,
        "trees",
        commit_obj["tree"].as_str().unwrap(),
    ))
    .unwrap();

    let err = json_failure(&dir, &["repair", "--rebuild-db"], 1);
    assert_eq!(
        err["error_code"], "KCS-E-COMMIT-SHALLOW-001",
        "repair must report the shallow HEAD, not a raw STORE-NOT-FOUND: {err}"
    );
}

// R16-4(b): a single document's missing normalized unit must not abort the whole
// rebuild. `repair --rebuild-db` skips that document (reporting it under skipped_units
// with KCS-E-STORE-IO-001 + recovery guidance) and rebuilds the rest. Before the fix
// one missing unit failed the entire scope (STORE-IO exit 1).
#[test]
fn r16_4_repair_skips_missing_unit_and_rebuilds_the_rest() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("keep.md"),
        "# Keep\n\n## Body\nkeepsurvivor token here\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("drop.md"),
        "# Drop\n\n## Body\ndropskipped token here\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--yes"]);

    // Delete ONE document's normalized unit file (a missing unit → KCS-E-STORE-IO-001).
    let unit_path = first_normalized_unit_json(&dir.path().join(".kcs/objects/normalized_units"));
    fs::remove_file(&unit_path).unwrap();

    // repair completes (exit 0): it rebuilds the healthy document and reports the
    // skipped one loudly, rather than aborting the whole scope.
    let out = json_success(&dir, &["repair", "--rebuild-db"]);
    let skipped = out["skipped_units"].as_array().unwrap();
    assert_eq!(skipped.len(), 1, "exactly one document is skipped: {out}");
    assert_eq!(skipped[0]["reason"], "KCS-E-STORE-IO-001");
    assert!(
        out["skipped_units_guidance"]
            .as_str()
            .unwrap()
            .contains("reindex --force"),
        "the recovery guidance must be surfaced: {out}"
    );
    // The scope still searches — the rebuild completed rather than bricking.
    let search = json_success(&dir, &["search", "token"]);
    assert!(
        !search["results"].as_array().unwrap().is_empty(),
        "the rebuilt scope must still search: {search}"
    );
}

// R16-5: `kcs diff` with a shallow side (its commit or tree object discarded) must
// surface a clear COMMIT-SHALLOW that names WHICH side (a/b) is shallow, not a raw
// opaque KCS-E-STORE-NOT-FOUND-001 whose hash the user cannot map to an operand.
#[test]
fn r16_5_diff_with_shallow_side_names_the_side() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("d.md"), "# D\n\n## S\nv1 body\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    let c1 = json_success(&dir, &["snapshot", "-m", "first"]);
    let c1_hash = c1["commit_hash"].as_str().unwrap().to_owned();
    fs::write(dir.path().join("d.md"), "# D\n\n## S\nv2 body\n").unwrap();
    let c2 = json_success(&dir, &["snapshot", "-m", "second"]);
    let c2_hash = c2["commit_hash"].as_str().unwrap().to_owned();

    // (control) a healthy diff of the two commits works.
    let ok = json_success(&dir, &["diff", &c1_hash, &c2_hash]);
    assert!(!ok["changes"].as_array().unwrap().is_empty());

    // Make C2 shallow: discard its tree object (its commit survives).
    let kcs_dir = dir.path().join(".kcs");
    let c2_obj: Value =
        serde_json::from_slice(&fs::read(object_path(&kcs_dir, "commits", &c2_hash)).unwrap())
            .unwrap();
    fs::remove_file(object_path(
        &kcs_dir,
        "trees",
        c2_obj["tree"].as_str().unwrap(),
    ))
    .unwrap();

    // Naming C2 as operand b → COMMIT-SHALLOW, context side="b".
    let err_b = json_failure(&dir, &["diff", &c1_hash, &c2_hash], 1);
    assert_eq!(err_b["error_code"], "KCS-E-COMMIT-SHALLOW-001", "{err_b}");
    assert_eq!(err_b["context"]["side"], "b", "{err_b}");
    // Naming C2 as operand a → COMMIT-SHALLOW, context side="a".
    let err_a = json_failure(&dir, &["diff", &c2_hash, &c1_hash], 1);
    assert_eq!(err_a["error_code"], "KCS-E-COMMIT-SHALLOW-001", "{err_a}");
    assert_eq!(err_a["context"]["side"], "a", "{err_a}");
}

// R17-5: `resolve_commit` (hash-literal + tag-name branches) and `tag`'s implicit-HEAD
// verification read were the 3 read_commit sites R16-1's COMMIT-SHALLOW sweep missed.
// A shallow commit (its whole commit object gone, not merely its tree — the case that
// fails INSIDE resolve_commit, before diff_side_tree's R16-5 absorption) reached via a
// hash literal, a tag name, or the implicit HEAD must fold into KCS-E-COMMIT-SHALLOW-001
// (exit 1) — the same contract the `HEAD` *string* operand already reached — not
// escape as a raw KCS-E-STORE-NOT-FOUND-001 (exit 4).
#[test]
fn r17_5_shallow_commit_via_hash_tag_and_implicit_head_folds_to_commit_shallow() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("d.md"), "# D\n\n## S\nv1 body\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    let c1 = json_success(&dir, &["snapshot", "-m", "first"]);
    let c1_hash = c1["commit_hash"].as_str().unwrap().to_owned();
    // A tag pointing at C1, created while C1 is healthy (control + tag-name coverage).
    json_success(&dir, &["tag", "tagc1", &c1_hash]);
    fs::write(dir.path().join("d.md"), "# D\n\n## S\nv2 body\n").unwrap();
    let c2 = json_success(&dir, &["snapshot", "-m", "second"]);
    let c2_hash = c2["commit_hash"].as_str().unwrap().to_owned();

    // (control) a healthy diff of the two hash literals works.
    let ok = json_success(&dir, &["diff", &c1_hash, &c2_hash]);
    assert!(!ok["changes"].as_array().unwrap().is_empty());

    // Make C1 shallow by deleting its whole COMMIT object (not merely its tree).
    let kcs_dir = dir.path().join(".kcs");
    fs::remove_file(object_path(&kcs_dir, "commits", &c1_hash)).unwrap();

    // hash literal as diff side a, then side b (resolve_commit hash branch, scope.rs:689).
    let err_a = json_failure(&dir, &["diff", &c1_hash, "HEAD"], 1);
    assert_eq!(err_a["error_code"], "KCS-E-COMMIT-SHALLOW-001", "{err_a}");
    let err_b = json_failure(&dir, &["diff", "HEAD", &c1_hash], 1);
    assert_eq!(err_b["error_code"], "KCS-E-COMMIT-SHALLOW-001", "{err_b}");
    // tag creation with a shallow hash-literal operand (tag -> resolve_commit).
    let err_tag = json_failure(&dir, &["tag", "newtag", &c1_hash], 1);
    assert_eq!(
        err_tag["error_code"], "KCS-E-COMMIT-SHALLOW-001",
        "{err_tag}"
    );
    // tag-NAME target now shallow (resolve_commit tag-name branch, scope.rs:696).
    let err_tagname = json_failure(&dir, &["diff", "tagc1", "HEAD"], 1);
    assert_eq!(
        err_tagname["error_code"], "KCS-E-COMMIT-SHALLOW-001",
        "{err_tagname}"
    );

    // Implicit HEAD: make HEAD (C2) shallow too, then `tag` with no operand resolves
    // the implicit HEAD via head_commit_hash() and verifies it (scope.rs:662).
    fs::remove_file(object_path(&kcs_dir, "commits", &c2_hash)).unwrap();
    let err_head = json_failure(&dir, &["tag", "headtag"], 1);
    assert_eq!(
        err_head["error_code"], "KCS-E-COMMIT-SHALLOW-001",
        "{err_head}"
    );
}

// R17-2: `reindex --force` must not let ONE document's corrupt normalized unit abort the
// whole scope's re-normalization (docs/10 §7.2). R16-4 gave `rebuild_step3_index` this
// skip-continue resilience, but the pre-rebuild copy loop in `run_reindex` never inherited
// it — a single STORE-CORRUPT unit killed the reindex (exit 4) and the healthy documents
// were never re-normalized, while `repair`'s guidance still pointed users AT this broken
// command. Now the corrupt document is skipped (its previous gen kept) and reported under
// skipped_units; the healthy document is re-normalized and the scope stays searchable.
#[test]
fn r17_2_reindex_force_skips_corrupt_unit_and_renormalizes_healthy() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("healthy.md"),
        "# Healthy\n\n## Body\nhealthytoken alpha content here\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("corrupt.md"),
        "# Corrupt\n\n## Body\ncorrupttoken beta content here\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--yes"]);

    // Corrupt ONE document's normalized-instance manifest → copy_normalized_instance_gen
    // raises KCS-E-STORE-CORRUPT-001 for that raw_hash during re-normalization.
    let units_root = dir.path().join(".kcs/objects/normalized_units");
    let manifest = first_manifest_json(&units_root);
    let corrupt_raw_hash = {
        let value: Value = serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();
        value["raw_hash"].as_str().unwrap().to_owned()
    };
    fs::write(&manifest, r#"{"torn":"#).unwrap();

    // Before the fix: exit 4 (KCS-E-STORE-CORRUPT-001), no re-normalization at all.
    let out = json_success(&dir, &["reindex", "--force", "--yes"]);
    // The healthy document IS re-normalized (the loop no longer dies on the corrupt one).
    assert_eq!(
        out["reindexed_files"].as_u64().unwrap(),
        1,
        "the healthy document is re-normalized: {out}"
    );
    let skipped = out["skipped_units"].as_array().unwrap();
    assert_eq!(
        skipped.len(),
        1,
        "exactly the corrupt document is skipped (deduped across both phases): {out}"
    );
    assert_eq!(skipped[0]["reason"], "KCS-E-STORE-CORRUPT-001");
    assert_eq!(
        skipped[0]["raw_hash"], corrupt_raw_hash,
        "the skip names the corrupted document: {out}"
    );
    assert!(
        out["skipped_units_guidance"].as_str().is_some(),
        "the skip is loudly disclosed: {out}"
    );
    // The scope is not bricked — the healthy document still searches after the reindex.
    let search = json_success(&dir, &["search", "healthytoken"]);
    assert!(
        !search["results"].as_array().unwrap().is_empty(),
        "healthy document searchable after reindex: {search}"
    );
}

// R17-4: when EVERY searched scope is excluded for a store-corruption class the search
// must not fall through to the bare KCS-E-SEARCH-SCOPE-ALL-FAILED-001 (exit 4, no
// guidance) — that left an operator/agent with no recovery path, unlike the
// index_missing/index_corrupt case which points at `repair`. A store_corrupt (tampered
// HEAD commit object) all-scope failure keeps the docs-registered
// KCS-E-SEARCH-SCOPE-ALL-FAILED-001 code but now carries class-specific recovery
// guidance in `context.recovery` + the message. Exit stays 4: `repair --rebuild-db`
// rebuilds the index FROM the store, so it does not heal a corrupt commit object.
#[test]
fn r17_4_store_corrupt_all_scopes_returns_recovery_guidance() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("a.md"),
        "# A\n\n## Sec\nalphacorrupt token\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--yes"]);

    // Corrupt the single scope's HEAD commit object (garbage → content-hash mismatch →
    // STORE-CORRUPT → Excluded("store_corrupt")); with no healthy scope, every searched
    // scope failed for the store-corruption class.
    let kcs_dir = dir.path().join(".kcs");
    let head = head_commit(&kcs_dir);
    fs::write(
        object_path(&kcs_dir, "commits", &head),
        b"this is not a valid commit object",
    )
    .unwrap();

    let err = json_failure(&dir, &["search", "alphacorrupt"], 4);
    assert_eq!(
        err["error_code"], "KCS-E-SEARCH-SCOPE-ALL-FAILED-001",
        "store corruption keeps the docs-registered all-failed code (no new code): {err}"
    );
    // Distinguished from the BARE all-failed not by a new code but by carrying
    // class-specific `context.recovery` guidance (asserted below).
    let recovery = err["context"]["recovery"].as_array().unwrap();
    assert!(
        recovery
            .iter()
            .any(|line| line.as_str().unwrap().contains("store_corrupt")),
        "store_corrupt-specific recovery guidance is present: {err}"
    );
    assert!(
        err["message"]
            .as_str()
            .unwrap()
            .contains("repair --rebuild-db"),
        "guidance names the recovery command: {err}"
    );
}

// R17-4: the snapshot_shallow class (R16-3: a bare-snapshot HEAD whose tree object was
// discarded, no cached rows) gets its OWN recovery guidance — deliberately NOT the
// index_missing "run repair" push, because repair cannot restore a discarded object.
#[test]
fn r17_4_snapshot_shallow_all_scopes_returns_recovery_guidance() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("a.md"),
        "# A\n\n## Sec\nalphashallow token\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--yes"]);

    // Advance HEAD with a bare snapshot (tree_entries NOT projected) then discard its
    // tree object → the fresh search sees ShallowNoRows → Excluded("snapshot_shallow").
    fs::write(
        dir.path().join("a.md"),
        "# A\n\n## Sec\nalphashallow token v2\n",
    )
    .unwrap();
    let snap = json_success(&dir, &["snapshot", "-m", "advance"]);
    let c2 = snap["commit_hash"].as_str().unwrap().to_owned();
    let kcs_dir = dir.path().join(".kcs");
    let c2_obj: Value =
        serde_json::from_slice(&fs::read(object_path(&kcs_dir, "commits", &c2)).unwrap()).unwrap();
    fs::remove_file(object_path(
        &kcs_dir,
        "trees",
        c2_obj["tree"].as_str().unwrap(),
    ))
    .unwrap();

    let err = json_failure(&dir, &["search", "alphashallow"], 4);
    assert_eq!(
        err["error_code"], "KCS-E-SEARCH-SCOPE-ALL-FAILED-001",
        "{err}"
    );
    let recovery = err["context"]["recovery"].as_array().unwrap();
    assert!(
        recovery
            .iter()
            .any(|line| line.as_str().unwrap().contains("snapshot_shallow")),
        "snapshot_shallow-specific recovery guidance is present: {err}"
    );
    assert!(
        err["message"]
            .as_str()
            .unwrap()
            .contains("re-run `kcs index`")
            || err["message"]
                .as_str()
                .unwrap()
                .contains("restore the discarded"),
        "guidance names object restore / re-index (NOT `repair --rebuild-db` alone): {err}"
    );
}

// R17-6: a document whose normalized unit is corrupt but whose persisted chunks survive
// in chunks.jsonl is STILL searchable — `build_sqlite_index_at` re-serves the cached
// chunks. Its skipped_units entry must be flagged searchable with a soft "stale source"
// note, not the emergency "re-normalize now" push (which points at the reindex --force
// R17-2 just un-bricked). Before the fix every skip got the emergency guidance.
#[test]
fn r17_6_repair_softens_guidance_for_searchable_cached_document() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("a.md"),
        "# A\n\n## Body\ncachedserving unique token\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--yes"]);

    // Corrupt the normalized unit (→ skipped during rebuild) AND delete sqlite so repair
    // must rebuild. The cached chunks in chunks.jsonl survive → the document stays
    // searchable and its skip is a stale-source note, not an emergency.
    let unit = first_normalized_unit_json(&dir.path().join(".kcs/objects/normalized_units"));
    fs::write(&unit, r#"{"torn":"#).unwrap();
    fs::remove_file(dir.path().join(".kcs/index/sqlite.db")).unwrap();

    let out = json_success(&dir, &["repair", "--rebuild-db"]);
    let skipped = out["skipped_units"].as_array().unwrap();
    assert_eq!(skipped.len(), 1, "{out}");
    assert_eq!(
        skipped[0]["searchable"],
        Value::Bool(true),
        "the cached document is flagged still-searchable: {out}"
    );
    assert!(
        skipped[0]["guidance"]
            .as_str()
            .unwrap()
            .to_lowercase()
            .contains("stale"),
        "the searchable document's per-entry guidance is a stale note: {out}"
    );
    // Top-level guidance is the softened (non-emergency) form.
    assert!(
        out["skipped_units_guidance"]
            .as_str()
            .unwrap()
            .contains("when convenient"),
        "top-level guidance is softened, not the emergency push: {out}"
    );
    // The document is genuinely searchable after the rebuild (the false alarm was false).
    let search = json_success(&dir, &["search", "cachedserving"]);
    assert!(
        !search["results"].as_array().unwrap().is_empty(),
        "cached document still searches after repair: {search}"
    );
}

// R17-6 discriminator: a skipped document with NO surviving chunks (chunks.jsonl gone) is
// genuinely unsearchable and MUST keep the emergency re-normalization guidance — softening
// is scoped to documents that are actually still being served.
#[test]
fn r17_6_repair_keeps_emergency_guidance_when_no_cached_chunks_survive() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("only.md"),
        "# Only\n\n## Body\nonlydoc unique token\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--yes"]);

    // Corrupt the unit AND remove the persisted chunks — nothing can be re-served, so the
    // document is genuinely unsearchable.
    let unit = first_normalized_unit_json(&dir.path().join(".kcs/objects/normalized_units"));
    fs::write(&unit, r#"{"torn":"#).unwrap();
    fs::remove_file(dir.path().join(".kcs/index/chunks.jsonl")).unwrap();

    let out = json_success(&dir, &["repair", "--rebuild-db"]);
    let skipped = out["skipped_units"].as_array().unwrap();
    assert_eq!(skipped.len(), 1, "{out}");
    assert_eq!(
        skipped[0]["searchable"],
        Value::Bool(false),
        "no live chunks → not searchable: {out}"
    );
    assert!(
        !skipped[0]["guidance"]
            .as_str()
            .unwrap()
            .to_lowercase()
            .contains("stale"),
        "an unsearchable document keeps the emergency guidance, not the stale note: {out}"
    );
    // The document truly cannot be served — the emergency guidance is warranted.
    let search = json_success(&dir, &["search", "onlydoc"]);
    assert!(
        search["results"].as_array().unwrap().is_empty(),
        "no chunks remain → no results: {search}"
    );
}

// ===========================================================================
// R16-6: the hand-rolled arg parsers coerced `--flag=<value>` on a value-LESS
// (boolean / SetTrue) flag into `true`, silently dropping the inline value — so
// `reindex --force=false --yes=false` (an explicit negation) bypassed the
// confirmation gate and ran a full reindex (exit 0). Every value-less flag must
// now reject an inline value with KCS-E-CONFIG-USAGE-001 (exit 2), matching clap's
// derived bool flags (which already reject `--json=false`). Value-TAKING flags keep
// consuming their inline value.
// ===========================================================================
#[test]
fn r16_6_valueless_flag_inline_value_is_a_usage_error() {
    let dir = indexed_scope();

    // reindex: the reported gate bypass. `--force=false` must not be coerced to true.
    let err = json_failure(&dir, &["reindex", "--force=false"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001", "{err}");
    assert!(
        err["message"]
            .as_str()
            .unwrap()
            .contains("--force does not take a value"),
        "{err}"
    );
    // The negated confirmation flag is equally rejected (would have bypassed --yes).
    let err = json_failure(&dir, &["reindex", "--force", "--yes=false"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001", "{err}");

    // repair: `--rebuild-db=false` must not still rebuild the DB.
    let err = json_failure(&dir, &["repair", "--rebuild-db=false"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001", "{err}");

    // search: `--text=false` must not be read as "text mode requested".
    let err = json_failure(&dir, &["search", "トークン", "--text=false"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001", "{err}");
    // A second boolean search flag, for good measure.
    let err = json_failure(&dir, &["search", "トークン", "--all-scopes=false"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-USAGE-001", "{err}");

    // Controls: a value-TAKING flag still accepts its inline value, and the real
    // reindex confirmation path (no inline value) still runs.
    let search = json_success(&dir, &["search", "トークン", "--limit=1"]);
    assert!(
        search["results"].as_array().unwrap().len() <= 1,
        "value-taking --limit=1 must be honored, not rejected: {search}"
    );
    let reindexed = json_success(&dir, &["reindex", "--force", "--yes"]);
    assert_eq!(reindexed["status"], "reindexed", "{reindexed}");
}

// ===========================================================================
// R16-7: a retry-able failure re-reserved the FULL cost on every send attempt, so a
// phantom charge accumulated without bound (RateLimit retries are unbounded) and
// could exhaust the device month cap, falsely pausing unrelated tasks in other
// scopes. The gate is error-kind-aware: a resend whose PREVIOUS failure was a
// non-billable rejection (RateLimit / QuotaExceeded) reuses the prior reservation
// and does NOT re-charge; a NetworkError resend (possibly billed server-side,
// bounded by max_attempts) still does.
// ===========================================================================

/// Run `kcs <args> --json` with the online markdownize seam pinned to `seam` and an
/// optional frozen clock, tolerating ANY exit (batch resume/retry return non-zero on
/// a retry-able failure while still printing their JSON result to stdout).
fn run_markdownize_seam(
    dir: &TempDir,
    seam: &str,
    fixed_now: Option<&str>,
    args: &[&str],
) -> Value {
    let mut command = kcs(dir, args);
    command.env(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, seam);
    if let Some(now) = fixed_now {
        command.env("KCS_FIXED_NOW", now);
    }
    let output = command.arg("--json").assert().get_output().stdout.clone();
    serde_json::from_slice(&output).unwrap_or(Value::Null)
}

/// Count the online-markdownize (`adapter_kind = "markdown"`) reservation rows in the
/// device-global cost ledger. The harness roots `$XDG_DATA_HOME` at `.test-data`.
fn markdown_ledger_rows(dir: &TempDir) -> usize {
    let path = dir.path().join(".test-data/kcs/cost-ledger.jsonl");
    let Ok(text) = fs::read_to_string(&path) else {
        return 0;
    };
    text.lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter(|row| row["adapter_kind"] == "markdown")
        .count()
}

// Discriminator (a): rate_limit ×N retry keeps the online markdownize charge row at 1
// (attempts still advance). Before R16-7 each resend re-reserved the full cost.
#[test]
fn r16_7_rate_limit_retry_does_not_reaccrue_charge() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("doc.pdf"),
        fake_pdf(&["レート制限リトライの課金累積回帰テスト本文です。"]),
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    // index only ENQUEUES the online markdownize task (Pending); no send, no charge.
    run_markdownize_seam(&dir, "mock", None, &["index", "--approve"]);
    assert_eq!(
        markdown_ledger_rows(&dir),
        0,
        "index must not reserve a markdownize charge before any send"
    );

    // First real send under the rate_limit seam: one charge reserved, task -> Failed.
    run_markdownize_seam(
        &dir,
        "rate_limit",
        Some("2026-07-03T00:00:00Z"),
        &["batch", "resume"],
    );
    assert_eq!(
        markdown_ledger_rows(&dir),
        1,
        "the first online send reserves exactly one charge"
    );

    // Retry past the backoff repeatedly. RateLimit is refused before billing, so the
    // prior reservation covers each resend — the charge count must stay 1 (the fix).
    for minute in 1..=4 {
        let now = format!("2026-07-03T00:0{minute}:30Z");
        run_markdownize_seam(&dir, "rate_limit", Some(&now), &["batch", "retry"]);
        assert_eq!(
            markdown_ledger_rows(&dir),
            1,
            "rate_limit retry #{minute} must not re-accrue a phantom charge"
        );
    }

    // The attempts counter still advanced (retries happened; only the charge is gated).
    let status = run_markdownize_seam(&dir, "rate_limit", None, &["status"]);
    let online = tasks_of_type(&status, "markdownize")
        .into_iter()
        .find(|task| task["fallback_reason"] == "rate_limit")
        .expect("a rate-limited online markdownize task");
    assert!(
        online["attempts"].as_u64().unwrap() >= 2,
        "retries must advance attempts even while the charge stays 1: {status}"
    );
}

// Discriminator (b): a NetworkError resend re-reserves each attempt (it may have been
// billed server-side; bounded by max_attempts=5). The charge row count must GROW —
// the contrast that proves the gate is error-kind-aware, not a blanket "reserve once".
#[test]
fn r16_7_network_error_retry_reaccrues_charge() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("doc.pdf"),
        fake_pdf(&["ネットワークエラーリトライの課金回帰テスト本文です。"]),
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    run_markdownize_seam(&dir, "mock", None, &["index", "--approve"]);

    // First send fails NetworkError: one charge.
    run_markdownize_seam(
        &dir,
        "network_error",
        Some("2026-07-03T00:00:00Z"),
        &["batch", "resume"],
    );
    assert_eq!(
        markdown_ledger_rows(&dir),
        1,
        "the first online send reserves one charge"
    );

    // Each retry reserves afresh → the charge count grows one per attempt.
    let mut expected = 1;
    for minute in 1..=3 {
        let now = format!("2026-07-03T00:0{minute}:30Z");
        run_markdownize_seam(&dir, "network_error", Some(&now), &["batch", "retry"]);
        expected += 1;
        assert_eq!(
            markdown_ledger_rows(&dir),
            expected,
            "network_error retry #{minute} must reserve a fresh charge (not skipped)"
        );
    }
}

// ===========================================================================
// R17-3: a rate_limit-Failed online markdownize task keeps its F8 reservation, which
// R16-7 established is a phantom (rate_limit/quota never bill). R15-2's enqueue-time
// supersede retired only Pending/Paused, so after the file was edited the stale
// Failed(rate_limit) task lingered and its phantom reservation exhausted the per-
// adapter markdownize cap, falsely pausing the re-indexed (valid) task. The fix
// retires the retryable-Failed task AND reclaims the phantom into a sibling positive-
// only reclaim ledger (F3: the charge ledger is never negatively amended). The
// discriminator pair below proves the reclaim is error-kind-aware: a rate_limit
// phantom is reclaimed (the edited doc is Pending), a NetworkError reservation is
// conservatively kept (the edited doc is budget-Paused, cap-safe) — the same
// asymmetry R16-7 maintains, because a NetworkError send may have billed server-side.
// ===========================================================================

/// Sum the usd of the online-markdownize (`adapter_kind = "markdown"`) rows in the
/// device-global CHARGE ledger — the exact per-document reservation cost, used to
/// size a per-adapter cap between one and two documents.
fn markdown_ledger_usd(dir: &TempDir) -> f64 {
    markdown_rows_usd_at(&dir.path().join(".test-data/kcs/cost-ledger.jsonl"))
}

/// Sum the usd of the markdown rows in the device-global RECLAIM ledger (R17-3).
/// Zero when no phantom has been reclaimed (or the file does not yet exist).
fn markdown_reclaim_usd(dir: &TempDir) -> f64 {
    markdown_rows_usd_at(
        &dir.path()
            .join(".test-data/kcs/cost-ledger-reclaimed.jsonl"),
    )
}

fn markdown_rows_usd_at(path: &Path) -> f64 {
    let Ok(text) = fs::read_to_string(path) else {
        return 0.0;
    };
    text.lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter(|row| row["adapter_kind"] == "markdown")
        .filter_map(|row| row["usd"].as_f64())
        .sum()
}

/// Pin a DEVICE per-adapter markdown cap sized to fit exactly ONE document cost but
/// not two (1.5×), with a generous overall monthly cap so only the per-adapter cap
/// binds. Written to the user (device) config the m8 tests already exercise.
fn set_markdown_adapter_cap(dir: &TempDir, cap: f64) {
    let config = dir.path().join(".test-config/kcs/config.toml");
    fs::create_dir_all(config.parent().unwrap()).unwrap();
    fs::write(
        &config,
        format!("[budget]\nmonthly_usd_cap = 1000\n[budget.per_adapter]\nmarkdown = {cap}\n"),
    )
    .unwrap();
}

/// Two page bodies of EQUAL byte length (they differ only in one trailing ASCII
/// char), so editing `v1 -> v2` changes `raw_hash` while keeping the document size —
/// and therefore the reservation cost — identical. This lets a cap of `1.5 × cost`
/// discriminate "one reservation fits" from "two reservations exceed".
const R17_3_BODY_V1: &str = "R17-3 phantom reclaim regression 本文あいうえお A";
const R17_3_BODY_V2: &str = "R17-3 phantom reclaim regression 本文あいうえお B";

// Discriminator (a): rate_limit phantom → edit → re-index. The phantom is reclaimed,
// so the edited doc's online task is Pending (matches the control where rate_limit
// never happened), NOT budget-Paused. The charge ledger is untouched (F3); the
// reclaim ledger carries the exact canceling amount.
#[test]
fn r17_3_rate_limit_phantom_reclaimed_frees_cap_for_edited_doc() {
    let dir = tempfile::tempdir().unwrap();
    assert_eq!(
        R17_3_BODY_V1.len(),
        R17_3_BODY_V2.len(),
        "the two doc bodies must be equal byte length so the cost is identical"
    );
    fs::write(dir.path().join("doc.pdf"), fake_pdf(&[R17_3_BODY_V1])).unwrap();
    kcs(&dir, &["init"]).assert().success();
    run_markdownize_seam(&dir, "mock", None, &["index", "--approve"]);

    // First real send under rate_limit: v1 -> Failed(rate_limit), one phantom row.
    run_markdownize_seam(
        &dir,
        "rate_limit",
        Some("2026-07-03T00:00:00Z"),
        &["batch", "resume"],
    );
    assert_eq!(
        markdown_ledger_rows(&dir),
        1,
        "the rate_limit send reserves exactly one (phantom) charge"
    );
    let doc_cost = markdown_ledger_usd(&dir);
    assert!(doc_cost > 0.0, "the reservation must be a positive cost");

    // Cap fits ONE document but not two: phantom (1×) + edited doc (1×) would exceed.
    set_markdown_adapter_cap(&dir, doc_cost * 1.5);

    // Edit (new raw_hash, identical size) and re-index in the SAME ledger month.
    fs::write(dir.path().join("doc.pdf"), fake_pdf(&[R17_3_BODY_V2])).unwrap();
    run_markdownize_seam(
        &dir,
        "mock",
        Some("2026-07-05T00:00:00Z"),
        &["index", "--approve"],
    );

    // The phantom is reclaimed by exactly its reserved cost (F3-safe positive row).
    assert!(
        (markdown_reclaim_usd(&dir) - doc_cost).abs() < 1e-12,
        "the rate_limit phantom must be reclaimed by exactly its reserved cost"
    );
    // F3: the charge ledger is never negatively amended — the phantom row still stands
    // and the reclaim nets it out at read time instead.
    assert_eq!(
        markdown_ledger_rows(&dir),
        1,
        "the charge ledger keeps the phantom row (no negative compensating entry, F3)"
    );

    let status = run_markdownize_seam(&dir, "mock", Some("2026-07-05T00:00:00Z"), &["status"]);
    let markdownize = tasks_of_type(&status, "markdownize");
    let pending = markdownize
        .iter()
        .filter(|task| task["status"] == "pending")
        .count();
    let paused_budget = markdownize
        .iter()
        .filter(|task| task["status"] == "paused" && task["fallback_reason"] == "budget_exceeded")
        .count();
    assert_eq!(
        pending, 1,
        "the edited doc's online task must be Pending (phantom reclaimed): {status}"
    );
    assert_eq!(
        paused_budget, 0,
        "no online task may be budget-paused after the reclaim: {status}"
    );
    // The stale v1 task is retired (non-retryable retired_non_live), not left rate_limit.
    let still_rate_limited = markdownize
        .iter()
        .filter(|task| task["fallback_reason"] == "rate_limit")
        .count();
    assert_eq!(
        still_rate_limited, 0,
        "the stale rate_limit task must be superseded: {status}"
    );
    // R19-3: the retirement uses the reversible `retired_non_live` reason (still
    // non-retryable, but re-enqueueable if the exact bytes reappear).
    let retired = markdownize
        .iter()
        .filter(|task| task["status"] == "failed" && task["fallback_reason"] == "retired_non_live")
        .count();
    assert_eq!(
        retired, 1,
        "the stale online task must be retired as retired_non_live: {status}"
    );
}

// Discriminator (b): NetworkError phantom → edit → re-index. A NetworkError send may
// have billed server-side, so its reservation is NOT reclaimed (keeping the cap-safe
// invariant, the R15-5 silent-bypass guard). The stale task is still retired, but the
// reservation stands, so the edited doc's online task is budget-Paused — the contrast
// that proves the reclaim is error-kind-aware, not a blanket "reclaim on supersede".
#[test]
fn r17_3_network_error_reservation_kept_pauses_edited_doc() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("doc.pdf"), fake_pdf(&[R17_3_BODY_V1])).unwrap();
    kcs(&dir, &["init"]).assert().success();
    run_markdownize_seam(&dir, "mock", None, &["index", "--approve"]);

    // First real send under network_error: v1 -> Failed(network_error), one reserved row.
    run_markdownize_seam(
        &dir,
        "network_error",
        Some("2026-07-03T00:00:00Z"),
        &["batch", "resume"],
    );
    assert_eq!(
        markdown_ledger_rows(&dir),
        1,
        "the send reserves one charge"
    );
    let doc_cost = markdown_ledger_usd(&dir);
    assert!(doc_cost > 0.0, "the reservation must be a positive cost");
    set_markdown_adapter_cap(&dir, doc_cost * 1.5);

    // Edit and re-index in the same ledger month.
    fs::write(dir.path().join("doc.pdf"), fake_pdf(&[R17_3_BODY_V2])).unwrap();
    run_markdownize_seam(
        &dir,
        "mock",
        Some("2026-07-05T00:00:00Z"),
        &["index", "--approve"],
    );

    // The NetworkError reservation is conservatively KEPT (not reclaimed).
    assert_eq!(
        markdown_reclaim_usd(&dir),
        0.0,
        "a NetworkError reservation must NOT be reclaimed (may have billed server-side)"
    );
    assert_eq!(
        markdown_ledger_rows(&dir),
        1,
        "the reservation stands in the charge ledger (cap-safe)"
    );

    let status = run_markdownize_seam(&dir, "mock", Some("2026-07-05T00:00:00Z"), &["status"]);
    let markdownize = tasks_of_type(&status, "markdownize");
    // The stale v1 is still retired (retryable-Failed supersede), but its reservation
    // is not reclaimed, so the edited doc's online task is budget-Paused.
    let retired = markdownize
        .iter()
        .filter(|task| task["status"] == "failed" && task["fallback_reason"] == "retired_non_live")
        .count();
    assert_eq!(retired, 1, "the stale task is still retired: {status}");
    let paused_budget = markdownize
        .iter()
        .filter(|task| task["status"] == "paused" && task["fallback_reason"] == "budget_exceeded")
        .count();
    assert_eq!(
        paused_budget, 1,
        "the edited doc must be budget-paused (phantom kept, cap-safe): {status}"
    );
}

// ===========================================================================
// R18-1: the EMBEDDING pipeline had NO reclaim path (only markdownize did, R17-3). An
// embedding send charges before the send (F8) and keeps its reservation on a
// RateLimit/Quota failure (R16-7); once the chunk is edited/deleted (non-live) the task
// can never be retried, so its phantom ate the embedding per-adapter cap for the rest of
// the month and falsely paused unrelated future embeddings. R18-1 stamps the per-chunk
// reservation (`apply_embedding_transitions`) and reclaims a non-live RateLimit/Quota
// phantom in `reconcile_committed_embedding_tasks`. The discriminator pair mirrors R17-3:
// rate_limit is reclaimed (the edited doc embeds), NetworkError is conservatively kept
// (the edited doc is budget-paused, cap-safe).
// ===========================================================================

fn embedding_rows_usd_at(path: &Path) -> f64 {
    let Ok(text) = fs::read_to_string(path) else {
        return 0.0;
    };
    text.lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter(|row| row["adapter_kind"] == "embedding")
        .filter_map(|row| row["usd"].as_f64())
        .sum()
}

fn embedding_ledger_rows(dir: &TempDir) -> usize {
    let path = dir.path().join(".test-data/kcs/cost-ledger.jsonl");
    let Ok(text) = fs::read_to_string(&path) else {
        return 0;
    };
    text.lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .filter(|row| row["adapter_kind"] == "embedding")
        .count()
}

fn embedding_ledger_usd(dir: &TempDir) -> f64 {
    embedding_rows_usd_at(&dir.path().join(".test-data/kcs/cost-ledger.jsonl"))
}

fn embedding_reclaim_usd(dir: &TempDir) -> f64 {
    embedding_rows_usd_at(
        &dir.path()
            .join(".test-data/kcs/cost-ledger-reclaimed.jsonl"),
    )
}

fn set_embedding_adapter_cap(dir: &TempDir, cap: f64) {
    let config = dir.path().join(".test-config/kcs/config.toml");
    fs::create_dir_all(config.parent().unwrap()).unwrap();
    fs::write(
        &config,
        format!("[budget]\nmonthly_usd_cap = 1000\n[budget.per_adapter]\nembedding = {cap}\n"),
    )
    .unwrap();
}

// Two equal-byte-length embedding doc bodies (differ only in a trailing marker), so
// editing v1 -> v2 changes raw_hash (making the old chunk non-live) while keeping the
// per-document embedding cost identical — letting a `1.5 × cost` cap discriminate.
const R18_1_BODY_V1: &str =
    "# R18-1\n\nembedding phantom reclaim regression 本文あいうえお かきくけこ さしすせそ A\n";
const R18_1_BODY_V2: &str =
    "# R18-1\n\nembedding phantom reclaim regression 本文あいうえお かきくけこ さしすせそ B\n";

// Step 4 discriminator: a rate-limited edited-away chunk remains active historical
// work. Its reservation is not reclaimed; retry may complete it, while the newer
// chunk remains budget-paused under a cap sized for only one send.
#[test]
fn ct4_retained_embedding_reservation_is_not_reclaimed_on_edit() {
    let dir = tempfile::tempdir().unwrap();
    assert_eq!(R18_1_BODY_V1.len(), R18_1_BODY_V2.len());
    fs::write(dir.path().join("doc.md"), R18_1_BODY_V1).unwrap();
    kcs(&dir, &["init"]).assert().success();

    // index --online charges the embedding (F8) then fails rate_limit → Failed(rate_limit)
    // with a stamped phantom reservation. Embedding failure is non-fatal (exit 0).
    json_success_embed_at(
        &dir,
        "rate_limit",
        "2026-07-03T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    assert_eq!(
        embedding_ledger_rows(&dir),
        1,
        "the rate_limit embedding send reserves one (phantom) charge"
    );
    let doc_cost = embedding_ledger_usd(&dir);
    assert!(doc_cost > 0.0, "the embedding reservation must be positive");
    set_embedding_adapter_cap(&dir, doc_cost * 1.5);

    // Edit (new chunk_id → old chunk non-live) and re-index with mock in the same month.
    fs::write(dir.path().join("doc.md"), R18_1_BODY_V2).unwrap();
    // Retained historical work still owns the adapter cap, so publishing the new
    // snapshot succeeds but enrichment truthfully reports the budget pause (exit 6).
    kcs(&dir, &["index", "--approve", "--online"])
        .env(TEST_ADOPTED_EMBEDDING_ENV, "mock")
        .env("KCS_FIXED_NOW", "2026-07-05T00:00:00Z")
        .arg("--json")
        .assert()
        .code(6);

    assert_eq!(
        embedding_reclaim_usd(&dir),
        0.0,
        "a retained historical send reservation is still live and cannot be reclaimed"
    );

    let status = json_success_embed_at(&dir, "mock", "2026-07-05T00:00:00Z", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    let paused_budget = embedding
        .iter()
        .filter(|task| task["status"] == "paused" && task["fallback_reason"] == "budget_exceeded")
        .count();
    assert_eq!(
        paused_budget, 1,
        "the newer chunk waits because retained historical work owns the cap: {status}"
    );
    let done = embedding
        .iter()
        .filter(|task| task["status"] == "done")
        .count();
    assert!(
        done >= 1,
        "the retained rate-limited historical chunk should complete on retry: {status}"
    );
}

// Discriminator (b) — error-kind-awareness (a NetworkError embedding reservation is KEPT,
// not reclaimed, because it may have billed server-side) — is NOT re-tested here: the
// deterministic embedding seam models `network_error` as an unreachable adapter that never
// charges (no phantom to reclaim), and the reclaim runs through the SHARED
// `retire_online_task_reclaiming` helper whose error-kind gate is already validated by
// `r17_3_network_error_reservation_kept_pauses_edited_doc` (markdownize). The embedding
// path passes `EMBEDDING_ADAPTER_KIND` into that identical helper, so its NetworkError
// branch is covered by construction.

// R18-2: markdownize's R17-3 reclaim only fired for a re-scanned SAME path. A DELETED (or
// renamed) file never reappears as a scan candidate, so its Failed(rate_limit) phantom was
// never reclaimed and kept eating the markdown cap. R18-2 sweeps deleted-path phantoms
// during `index`. Delete doc.pdf (phantom) + add an equal-cost doc2.pdf under a cap that
// fits ONE document: without the reclaim doc2 is budget-paused; with it, doc2 completes.
#[test]
fn r18_2_markdownize_deleted_file_phantom_reclaimed_frees_cap() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("doc.pdf"), fake_pdf(&[R17_3_BODY_V1])).unwrap();
    kcs(&dir, &["init"]).assert().success();
    run_markdownize_seam(&dir, "mock", None, &["index", "--approve"]);
    run_markdownize_seam(
        &dir,
        "rate_limit",
        Some("2026-07-03T00:00:00Z"),
        &["batch", "resume"],
    );
    assert_eq!(markdown_ledger_rows(&dir), 1, "one phantom charge");
    let doc_cost = markdown_ledger_usd(&dir);
    assert!(doc_cost > 0.0);
    set_markdown_adapter_cap(&dir, doc_cost * 1.5);

    // DELETE doc.pdf (its phantom must be reclaimed) and add an equal-cost doc2.pdf.
    fs::remove_file(dir.path().join("doc.pdf")).unwrap();
    fs::write(dir.path().join("doc2.pdf"), fake_pdf(&[R17_3_BODY_V2])).unwrap();
    // index sweeps the deleted-path phantom, then batch resume charges doc2 against the
    // freed cap.
    run_markdownize_seam(
        &dir,
        "mock",
        Some("2026-07-05T00:00:00Z"),
        &["index", "--approve"],
    );
    assert!(
        (markdown_reclaim_usd(&dir) - doc_cost).abs() < 1e-12,
        "the deleted file's rate_limit phantom must be reclaimed by its exact cost"
    );
    run_markdownize_seam(
        &dir,
        "mock",
        Some("2026-07-05T00:00:00Z"),
        &["batch", "resume"],
    );
    let status = run_markdownize_seam(&dir, "mock", Some("2026-07-05T00:00:00Z"), &["status"]);
    let markdownize = tasks_of_type(&status, "markdownize");
    let paused_budget = markdownize
        .iter()
        .filter(|task| task["status"] == "paused" && task["fallback_reason"] == "budget_exceeded")
        .count();
    assert_eq!(
        paused_budget, 0,
        "doc2 must not be budget-paused (deleted-file phantom reclaimed): {status}"
    );
    let doc2_done = markdownize.iter().any(|task| {
        task["input_path"] == "doc2.pdf"
            && task["status"] == "done"
            && task["fallback_reason"] == "online_adapter_done"
    });
    assert!(
        doc2_done,
        "doc2's online markdownize must complete: {status}"
    );
}

// R18-3: R17-3's reclaim ledger was netted by the enforcement gate but NOT by the
// status/warning reports, so `kcs status` over-reported spend after a reclaim. After a
// rate_limit phantom is reclaimed (charge == reclaim, so effective spend is 0 for that
// document), the status budget must report the NET spend, not the gross charge.
#[test]
fn r18_3_status_budget_nets_reclaim_ledger() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("doc.pdf"), fake_pdf(&[R17_3_BODY_V1])).unwrap();
    kcs(&dir, &["init"]).assert().success();
    run_markdownize_seam(&dir, "mock", None, &["index", "--approve"]);
    run_markdownize_seam(
        &dir,
        "rate_limit",
        Some("2026-07-03T00:00:00Z"),
        &["batch", "resume"],
    );
    let doc_cost = markdown_ledger_usd(&dir);
    assert!(doc_cost > 0.0);

    // Edit → re-index: the same-path supersede reclaims the phantom. The new task is
    // Pending (not yet charged), so charge == reclaim == doc_cost and net spend is 0.
    fs::write(dir.path().join("doc.pdf"), fake_pdf(&[R17_3_BODY_V2])).unwrap();
    run_markdownize_seam(
        &dir,
        "mock",
        Some("2026-07-05T00:00:00Z"),
        &["index", "--approve"],
    );
    assert!(
        (markdown_reclaim_usd(&dir) - doc_cost).abs() < 1e-12,
        "the phantom must be reclaimed (precondition for the netting check)"
    );

    let status = run_markdownize_seam(&dir, "mock", Some("2026-07-05T00:00:00Z"), &["status"]);
    let device_spent = status["budget"]["device_spent_usd"].as_f64().unwrap();
    assert!(
        device_spent < doc_cost * 0.5,
        "status must report NET spend (charge − reclaim ≈ 0), not the gross phantom \
         charge {doc_cost}: device_spent_usd={device_spent}"
    );
}

// R18-4: R17-4 attached store-corruption recovery guidance only when EVERY scope failed.
// A PARTIAL multi-scope exclusion (some scopes healthy) got a bare `reason` with no
// `recovery`. R18-4 attaches the hint to each individual excluded entry. (Models r16_2.)
#[test]
fn r18_4_partial_store_corruption_entry_carries_recovery_hint() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## Sec\nalphaunique survivor\n").unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Sec\nbetaunique other\n").unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);

    // Corrupt scope B's HEAD commit object (store_corrupt) — A stays healthy, so this is a
    // PARTIAL exclusion and the all-failed aggregate block is never reached.
    let b_kcs = b.join(".kcs");
    let b_head = head_commit(&b_kcs);
    fs::write(
        object_path(&b_kcs, "commits", &b_head),
        b"this is not a valid commit object",
    )
    .unwrap();

    let output = hermetic_kcs_command()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .args(["search", "alphaunique", "--all-scopes", "--json"])
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let search: Value = serde_json::from_slice(&output).unwrap();
    let excluded = search["excluded_scopes"].as_array().unwrap();
    assert_eq!(excluded.len(), 1);
    assert_eq!(excluded[0]["reason"], "store_corrupt");
    let recovery = excluded[0]["recovery"].as_str().unwrap_or_default();
    assert!(
        recovery.contains("store_corrupt") && recovery.contains("repair --rebuild-db"),
        "the partial-exclusion entry must carry the store_corrupt recovery hint: {search}"
    );
}

// ===========================================================================
// R19 探索型監査 第19ラウンド 回帰テスト
// ===========================================================================

fn json_online_both_seams(dir: &TempDir, ocr: &str, embed: &str, args: &[&str]) -> Value {
    let output = kcs(dir, args)
        .env(TEST_STANDARD_ONLINE_MARKDOWNIZE_ENV, ocr)
        .env(TEST_ADOPTED_EMBEDDING_ENV, embed)
        .arg("--json")
        .assert()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap_or(Value::Null)
}

fn env_online_tasks<'a>(status: &'a Value, path: &str) -> Vec<&'a Value> {
    tasks_of_type(status, "markdownize")
        .into_iter()
        .chain(tasks_of_type(status, "embedding"))
        .filter(|t| t["input_path"] == path)
        .collect()
}

// R19-1: a Tier A secret explicitly un-ignored (`!pattern`) is ingested locally but its
// ONLINE send (OCR + embedding) must be HELD until `--send-secrets` — exactly like a
// (lower-risk) Tier B file. Before R19-1 the lifted Tier A slipped BOTH online gates
// (a risk-gradient inversion) and left no quarantine audit record.
#[test]
fn r19_1_lifted_tier_a_secret_held_from_online_send() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join(".env"),
        "AWS_SECRET_ACCESS_KEY=FAKE_TESTKEY_abcdefghijklmnop\n",
    )
    .unwrap();
    fs::write(dir.path().join(".kcsignore"), "!.env\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_online_both_seams(&dir, "mock", "mock", &["index", "--approve", "--online"]);
    json_online_both_seams(&dir, "mock", "mock", &["batch", "resume"]);
    let status = json_online_both_seams(&dir, "mock", "mock", &["status"]);

    let held = env_online_tasks(&status, ".env")
        .iter()
        .filter(|t| t["fallback_reason"] == "secrets_tier_b_hold")
        .count();
    assert!(
        held >= 1,
        "lifted Tier A online task(s) must be HELD from send: {status}"
    );
    let sent = env_online_tasks(&status, ".env")
        .iter()
        .filter(|t| {
            t["fallback_reason"] == "online_adapter_done"
                || t["fallback_reason"] == "embedding_adapter_done"
        })
        .count();
    assert_eq!(
        sent, 0,
        "no lifted Tier A online task may be SENT without --send-secrets: {status}"
    );
    assert!(
        status["quarantine"]
            .as_array()
            .unwrap()
            .iter()
            .any(|q| q["path"] == ".env" && q["reason"] == "secrets_tier_a"),
        "lifted Tier A must be recorded in quarantine as secrets_tier_a: {status}"
    );

    // --send-secrets releases and sends BOTH online paths.
    json_online_both_seams(
        &dir,
        "mock",
        "mock",
        &["index", "--approve", "--online", "--send-secrets"],
    );
    json_online_both_seams(&dir, "mock", "mock", &["batch", "resume"]);
    let status = json_online_both_seams(&dir, "mock", "mock", &["status"]);
    let sent = env_online_tasks(&status, ".env")
        .iter()
        .filter(|t| {
            t["fallback_reason"] == "online_adapter_done"
                || t["fallback_reason"] == "embedding_adapter_done"
        })
        .count();
    assert!(
        sent >= 1,
        "--send-secrets must release + send the lifted Tier A online tasks: {status}"
    );
    // R19-7: the quarantine disposition must transition hold -> send_approved (a path-only
    // dedup previously froze it at "hold", misreporting an approved+sent file as pending).
    let dispositions: Vec<&str> = status["quarantine"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|q| q["path"] == ".env")
        .filter_map(|q| q["approval_method"].as_str())
        .collect();
    assert!(
        dispositions.contains(&"send_approved"),
        "R19-7: quarantine disposition must reach send_approved after --send-secrets: {status}"
    );
}

// Step 4 retains edited-away chunks as active historical work. Reverting exact
// bytes reuses the same task without a retire/revive cycle or duplicate output_ref.
#[test]
fn ct4_reverted_chunk_reuses_retained_embedding_task() {
    let dir = tempfile::tempdir().unwrap();
    assert_eq!(R18_1_BODY_V1.len(), R18_1_BODY_V2.len());
    fs::write(dir.path().join("doc.md"), R18_1_BODY_V1).unwrap();
    kcs(&dir, &["init"]).assert().success();
    // v1 embedding fails rate_limit -> Failed(rate_limit) phantom.
    json_success_embed_at(
        &dir,
        "rate_limit",
        "2026-07-03T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    // Edit to v2: v1 remains retained and is retried in this pass.
    fs::write(dir.path().join("doc.md"), R18_1_BODY_V2).unwrap();
    json_success_embed_at(
        &dir,
        "mock",
        "2026-07-05T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    let status = json_success_embed_at(&dir, "mock", "2026-07-05T00:00:00Z", &["status"]);
    let retired = tasks_of_type(&status, "embedding")
        .iter()
        .filter(|t| t["fallback_reason"] == "retired_non_live")
        .count();
    assert_eq!(
        retired, 0,
        "retained history is never retired_non_live: {status}"
    );
    let tasks_before = tasks_of_type(&status, "embedding").len();

    // Revert to the EXACT v1 bytes -> the v1 chunk_id reappears; it must re-embed.
    fs::write(dir.path().join("doc.md"), R18_1_BODY_V1).unwrap();
    json_success_embed_at(
        &dir,
        "mock",
        "2026-07-07T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    let status = json_success_embed_at(&dir, "mock", "2026-07-07T00:00:00Z", &["status"]);
    let tasks_after = tasks_of_type(&status, "embedding").len();
    // Reverting reuses the retained task in place rather than appending a duplicate
    // `output_ref` task. A duplicate
    // would be double-stamped by `apply_embedding_transitions` (keyed on output_ref) and
    // then double-reclaimed (silent cap fail-open). So the task count must NOT grow; the
    // reappeared chunk still re-embeds (asserted below via `reverted_done`).
    assert_eq!(
        tasks_after, tasks_before,
        "reverting must reuse the retained task, not append a duplicate \
         output_ref task (before={tasks_before}, after={tasks_after}): {status}"
    );
    let reverted_done = tasks_of_type(&status, "embedding")
        .iter()
        .filter(|t| t["status"] == "done")
        .count();
    assert!(
        reverted_done >= 1,
        "R19-3: the reverted chunk must embed (Done): {status}"
    );
}

// R19-4: when two docs share an identical section (same text_hash, different chunk_id),
// and one's embedding fails rate_limit while the other succeeds, `rebuild_chunk_vec`
// links the failed chunk's vector via the content-hash twin. The reconcile must then
// CONVERGE that live-and-embedded Failed task to Done and reclaim its phantom — before
// R19-4 it stayed Failed forever (reconcile's live->Done loop skipped Failed), stuck at
// pending_enrichment == 1 with a phantom reservation eating the cap.
#[test]
fn r19_4_duplicate_content_failed_chunk_converges_via_twin() {
    let dir = tempfile::tempdir().unwrap();
    let shared =
        "## 共有セクション\n\n共有される段落です。十分な長さの本文をここに置きます。あいうえお かきくけこ さしすせそ。\n";
    fs::write(
        dir.path().join("a.md"),
        format!("# 見出し AAAA\n\n{shared}"),
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Pin ALL passes to one instant so a.md's rate_limit chunks are never retry-DUE (their
    // 2s backoff never elapses) — the ONLY way its shared chunk can complete is the R19-4
    // twin convergence, not a normal mock retry. (A later wall-clock would just re-embed it
    // via retry and never exercise the bug.)
    let now = "2026-07-03T00:00:00Z";
    // a.md's chunks fail rate_limit (phantom reservations).
    json_success_embed_at(&dir, "rate_limit", now, &["index", "--approve", "--online"]);
    // b.md carries the IDENTICAL section (same text_hash, different chunk_id). Indexing it
    // with mock embeds the shared text into the `embeddings` table.
    fs::write(
        dir.path().join("b.md"),
        format!("# 見出し BBBB\n\n{shared}"),
    )
    .unwrap();
    json_success_embed_at(&dir, "mock", now, &["index", "--approve", "--online"]);
    // `rebuild_chunk_vec` runs BEFORE embedding enrichment in a given index pass, so it is
    // the NEXT pass that links a.md's shared chunk_id to the twin's now-persisted vector —
    // and the reconcile then converges a.md's stuck Failed chunk (self-heal on re-index).
    json_success_embed_at(&dir, "mock", now, &["index", "--approve", "--online"]);
    assert!(
        embedding_reclaim_usd(&dir) > 0.0,
        "R19-4: the twin-embedded rate_limit phantom must be reclaimed (got {})",
        embedding_reclaim_usd(&dir)
    );
    let status = json_success_embed_at(&dir, "mock", now, &["status"]);
    let a_done = tasks_of_type(&status, "embedding")
        .iter()
        .filter(|t| t["input_path"] == "a.md" && t["status"] == "done")
        .count();
    assert!(
        a_done >= 1,
        "R19-4: a.md's twin-embedded chunk must CONVERGE to Done, not stay Failed: {status}"
    );
}

// R19-2: an exhausted-quota (QuotaExceeded, attempts >= max) online markdownize phantom
// must still be reclaimed by the deleted/renamed sweep. Before R19-2 the sweep gated on
// `task_retry_allowed` (false once the finite quota budget is spent), stranding the
// phantom reservation for the month. Quota has no test seam, so the terminal state is
// crafted directly (as the round's control repro did).
#[test]
fn r19_2_exhausted_quota_phantom_reclaimed_on_sweep() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("doc.pdf"), fake_pdf(&[R17_3_BODY_V1])).unwrap();
    kcs(&dir, &["init"]).assert().success();
    run_markdownize_seam(&dir, "mock", None, &["index", "--approve"]);
    // Fail the online send under rate_limit -> Failed(rate_limit) with a phantom reservation.
    run_markdownize_seam(
        &dir,
        "rate_limit",
        Some("2026-07-03T00:00:00Z"),
        &["batch", "resume"],
    );
    assert_eq!(
        markdown_ledger_rows(&dir),
        1,
        "one phantom charge is reserved"
    );

    // Rewrite the reserved online markdownize task's terminal state to an EXHAUSTED quota
    // failure (quota_exceeded, attempts = 3 = its max). Last-write-wins jsonl.
    let tasks_path = dir.path().join(".kcs/tasks.jsonl");
    let text = fs::read_to_string(&tasks_path).unwrap();
    let mut crafted: Option<String> = None;
    for line in text.lines() {
        let t: Value = serde_json::from_str(line).unwrap();
        if t["type"] == "markdownize" && t.get("reserved_usd").and_then(Value::as_f64).is_some() {
            let mut row = t.clone();
            row["fallback_reason"] = Value::from("quota_exceeded");
            row["attempts"] = Value::from(3);
            row["status"] = Value::from("failed");
            row["next_retry_at"] = Value::Null;
            crafted = Some(serde_json::to_string(&row).unwrap());
        }
    }
    let crafted = crafted.expect("a reserved markdownize task must exist to craft");
    let mut appended = text.clone();
    appended.push_str(&crafted);
    appended.push('\n');
    fs::write(&tasks_path, appended).unwrap();

    // Delete the file (non-live) + add another, then re-index: the R18-2 sweep runs.
    fs::remove_file(dir.path().join("doc.pdf")).unwrap();
    fs::write(dir.path().join("doc2.pdf"), fake_pdf(&[R17_3_BODY_V2])).unwrap();
    run_markdownize_seam(
        &dir,
        "mock",
        Some("2026-07-05T00:00:00Z"),
        &["index", "--approve"],
    );

    assert!(
        markdown_reclaim_usd(&dir) > 0.0,
        "R19-2: the exhausted-quota phantom must be reclaimed by the sweep (got {})",
        markdown_reclaim_usd(&dir)
    );
}

// R19-6: R18-4 wired the store-corruption recovery hint only for store_corrupt/
// snapshot_shallow. The most common class — index_missing/index_corrupt (sqlite.db
// absent/damaged) — surfaced bare in a partial exclusion. Mirrors r18_4 with a corrupt
// sqlite.db instead of a corrupt commit object.
#[test]
fn r19_6_partial_index_corrupt_entry_carries_recovery_hint() {
    let parent = tempfile::tempdir().unwrap();
    let data_home = parent.path().join("xdg");
    let a = parent.path().join("a");
    let b = parent.path().join("b");
    fs::create_dir_all(&a).unwrap();
    fs::create_dir_all(&b).unwrap();
    fs::write(a.join("a.md"), "# A\n\n## Sec\nalphaunique survivor\n").unwrap();
    fs::write(b.join("b.md"), "# B\n\n## Sec\nbetaunique other\n").unwrap();
    json_success_path(&a, &data_home, &["init"]);
    json_success_path(&b, &data_home, &["init"]);
    json_success_path(&a, &data_home, &["index", "--approve"]);
    json_success_path(&b, &data_home, &["index", "--approve"]);

    // Corrupt scope B's sqlite.db (index_corrupt) — A stays healthy (partial exclusion).
    fs::write(b.join(".kcs/index/sqlite.db"), b"GARBAGE not a sqlite db").unwrap();

    let output = hermetic_kcs_command()
        .current_dir(&a)
        .env("XDG_CONFIG_HOME", data_home.join("config"))
        .env("XDG_DATA_HOME", data_home.join("data"))
        .env("XDG_CACHE_HOME", data_home.join("cache"))
        .args(["search", "alphaunique", "--all-scopes", "--json"])
        .assert()
        .code(3)
        .get_output()
        .stdout
        .clone();
    let search: Value = serde_json::from_slice(&output).unwrap();
    let excluded = search["excluded_scopes"].as_array().unwrap();
    assert_eq!(excluded.len(), 1);
    assert_eq!(excluded[0]["reason"], "index_corrupt");
    let recovery = excluded[0]["recovery"].as_str().unwrap_or_default();
    assert!(
        recovery.contains("index_corrupt") && recovery.contains("repair --rebuild-db"),
        "R19-6: the partial index_corrupt entry must carry a recovery hint: {search}"
    );
}

// R19-8: a `max_input_bytes` cap tightened AFTER a task is enqueued must be honored at
// send time — a Pending online task is not shipped if the file now exceeds the cap
// (the sibling `allow_network` key is likewise re-checked at send).
#[test]
fn r19_8_lowered_max_input_bytes_blocks_queued_online_send() {
    let dir = tempfile::tempdir().unwrap();
    let pdf = fake_pdf(&[R17_3_BODY_V1]);
    fs::write(dir.path().join("doc.pdf"), &pdf).unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Enqueue the online markdownize task under the default (generous) cap.
    run_markdownize_seam(&dir, "mock", None, &["index", "--approve"]);
    // Tighten the cap below the file size in the scope config.
    let cap = pdf.len() - 5;
    let cfg = dir.path().join(".kcs/config.toml");
    let mut content = fs::read_to_string(&cfg).unwrap_or_default();
    content.push_str(&format!("\n[adapter.policy]\nmax_input_bytes = {cap}\n"));
    fs::write(&cfg, content).unwrap();
    // batch resume must NOT send the now-oversized task (no online charge).
    run_markdownize_seam(
        &dir,
        "mock",
        Some("2026-07-05T00:00:00Z"),
        &["batch", "resume"],
    );
    assert_eq!(
        markdown_ledger_rows(&dir),
        0,
        "R19-8: the oversized queued task must not be sent/charged"
    );
    let status = run_markdownize_seam(&dir, "mock", None, &["status"]);
    let sent = tasks_of_type(&status, "markdownize")
        .iter()
        .filter(|t| t["fallback_reason"] == "online_adapter_done")
        .count();
    assert_eq!(
        sent, 0,
        "R19-8: no online markdownize may complete under the lowered cap: {status}"
    );
}

// ===========================================================================
// R21 — exploratory audit round 21 regression tests.
// ===========================================================================

const R21_TWIN_BODY: &str =
    "# Notes\n\n## Body\nSome plain readable content for indexing purposes here alpha bravo.\n";

/// R21-1 [critical]: a byte-identical NON-secret twin of a Tier B file must NOT let the
/// secret file's chunk slip the embedding hold. The content-addressed `chunk_id` fans out
/// across both live paths; before the fix the non-secret instance landed in `sendable`
/// while the secret instance landed in `held`, and the send loop drove the shared held
/// task Done — shipping the Tier B file's text online with no `--send-secrets`.
#[test]
fn r21_1_byte_identical_twin_does_not_bypass_tier_b_hold() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(dir.path().join("notes.md"), R21_TWIN_BODY).unwrap();
    fs::write(dir.path().join("password_backup.md"), R21_TWIN_BODY).unwrap();
    kcs(&dir, &["init"]).assert().success();
    // No `--send-secrets`.
    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    assert!(
        !embedding.is_empty(),
        "R21-1: expected embedding tasks: {status}"
    );
    for task in &embedding {
        assert_eq!(
            task["status"], "paused",
            "R21-1: every embedding task for a Tier B twin must stay held (paused), \
             not be driven Done by the non-secret twin: {status}"
        );
        assert_eq!(
            task["fallback_reason"], "secrets_tier_b_hold",
            "R21-1: held reason must be secrets_tier_b_hold: {status}"
        );
    }
}

/// R21-2: two byte-identical NON-secret files share one content-addressed `chunk_id`, so
/// they must produce exactly ONE embedding task per `output_ref` — not a duplicate that is
/// double-sent and double-charged (the R20-2 one-task-per-output_ref invariant, broken here
/// from a second source: the `tree_entries` JOIN fan-out).
#[test]
fn r21_2_byte_identical_twins_share_single_embedding_task() {
    let dir = tempfile::tempdir().unwrap();
    let body = "# Shared\nalpha bravo charlie delta echo foxtrot golf hotel india.\n";
    fs::write(dir.path().join("a.md"), body).unwrap();
    fs::write(dir.path().join("b.md"), body).unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    let distinct: std::collections::BTreeSet<&str> = embedding
        .iter()
        .map(|t| t["output_ref"].as_str().unwrap())
        .collect();
    assert_eq!(
        embedding.len(),
        distinct.len(),
        "R21-2: byte-identical twins must not create duplicate output_ref tasks \
         (tasks={}, distinct={}): {status}",
        embedding.len(),
        distinct.len()
    );
}

/// R21-4: a TEXT file the extension table folds to `application/octet-stream` — an
/// uppercase-extension text-native file (`README.MD`) or an unknown-extension config file
/// (`.yaml`) — is fully handled by the local passthrough and must NOT also enqueue an
/// online OCR task (R9-2: shipping its bytes to Mistral OCR is a routing violation).
#[test]
fn r21_4_uppercase_and_octet_stream_text_enqueue_no_online_ocr() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("README.MD"),
        "# Upper\nreadme text body here.\n",
    )
    .unwrap();
    fs::write(dir.path().join("config.yaml"), "name: acme\nvalue: 42\n").unwrap();
    fs::write(dir.path().join("Dockerfile"), "FROM alpine\nRUN echo hi\n").unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success(&dir, &["index", "--approve"]);
    let status = json_success(&dir, &["status"]);
    let online: Vec<_> = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|t| {
            t["output_ref"]
                .as_str()
                .is_some_and(|r| r.starts_with("online:"))
        })
        .collect();
    assert!(
        online.is_empty(),
        "R21-4: text files must not enqueue online OCR tasks: {online:?} in {status}"
    );
    // The text is still locally searchable.
    let search = json_success(&dir, &["search", "acme", "--text"]);
    assert!(
        !search["results"].as_array().unwrap().is_empty(),
        "R21-4: octet-stream text must still be indexed locally: {search}"
    );
}

/// CAND-013/R21-6: AuthError revival requires explicit `batch resume`; ordinary indexing
/// must not silently revive a failed online operation.
#[test]
fn r21_6_auth_error_live_task_recovers_after_credentials_fixed() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("notes.txt"),
        "plain readable content alpha bravo charlie delta echo.\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Credentials bad -> AuthError. `index` still exits 0 (enrichment failure is reported,
    // not fatal); read the resulting task state from `status`.
    let _ = kcs(&dir, &["index", "--approve", "--online"])
        .env(TEST_ADOPTED_EMBEDDING_ENV, "auth_error")
        .assert();
    let status = json_success_embed(&dir, "mock", &["status"]);
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .any(|t| t["status"] == "failed" && t["fallback_reason"] == "auth_error"),
        "R21-6: precondition — an AuthError embedding task must exist: {status}"
    );
    // Credentials fixed (mock succeeds) -> explicit resume recovers it.
    json_success_embed(&dir, "mock", &["batch", "resume"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    assert!(
        embedding.iter().any(|t| t["status"] == "done"),
        "R21-6: fixing credentials + explicit resume must recover AuthError to Done: {status}"
    );
    assert!(
        !embedding
            .iter()
            .any(|t| t["fallback_reason"] == "auth_error"),
        "R21-6: no AuthError task may remain stuck after recovery: {status}"
    );
}

/// Step 4 keeps a chunk active while any reachable history binds it. If an already
/// embedded historical chunk later appears under a Tier B path, the durable Done
/// task remains truthful, but the derived vector row is withheld until approval.
#[test]
fn ct4_historical_secret_path_withholds_existing_vector() {
    let dir = tempfile::tempdir().unwrap();
    let v1 = "# Notes\n\nordinary paragraph alpha bravo charlie delta echo foxtrot.\n";
    let v2 = "# Notes\n\nCOMPLETELY different body xray yankee zulu whiskey victor.\n";
    fs::write(dir.path().join("notes.md"), v1).unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed_at(
        &dir,
        "rate_limit",
        "2026-07-03T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    let initial_status = json_success_embed_at(&dir, "mock", "2026-07-03T00:00:00Z", &["status"]);
    let v1_output_ref = tasks_of_type(&initial_status, "embedding")[0]["output_ref"]
        .as_str()
        .unwrap()
        .to_owned();
    let v1_chunk_id = v1_output_ref.strip_prefix("embedding:").unwrap().to_owned();
    // Edit: v1 stays retained by history and may complete on the next pass.
    fs::write(dir.path().join("notes.md"), v2).unwrap();
    json_success_embed_at(
        &dir,
        "mock",
        "2026-07-05T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    // Delete and restore the EXACT v1 bytes under a Tier B name.
    fs::remove_file(dir.path().join("notes.md")).unwrap();
    fs::write(dir.path().join("password_notes.md"), v1).unwrap();
    json_success_embed_at(
        &dir,
        "mock",
        "2026-07-06T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    let status = json_success_embed_at(&dir, "mock", "2026-07-06T00:00:00Z", &["status"]);
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .any(|task| task["output_ref"] == v1_output_ref && task["status"] == "done"),
        "the already materialized embedding task remains a truthful terminal record: {status}"
    );
    kcs_index::vec::ensure_registered();
    let conn = rusqlite::Connection::open(dir.path().join(".kcs/index/sqlite.db")).unwrap();
    assert_eq!(
        conn.query_row(
            "SELECT COUNT(*) FROM chunk_vec WHERE chunk_id = ?1",
            rusqlite::params![v1_chunk_id],
            |row| row.get::<_, u64>(0),
        )
        .unwrap(),
        0,
        "any retained secret path must exclude the chunk from derived vector search"
    );
}

/// CT4-BBOX-006: a scanned/text-layer-less PDF (empty local `prepared_units`) must
/// complete OCR-from-scratch and remain idempotent across resume/re-index, rather than
/// staying Pending forever or churning replacement tasks.
#[test]
fn ct4_bbox_006_scanned_pdf_completes_without_churn() {
    let dir = tempfile::tempdir().unwrap();
    // %PDF header but no text layer (no `BT`): prepare_units returns empty.
    let mut scan = b"%PDF-1.4\n".to_vec();
    scan.extend((0u32..4000).map(|i| (i.wrapping_mul(97) & 0x7f) as u8 | 0x80));
    fs::write(dir.path().join("scan.pdf"), &scan).unwrap();
    kcs(&dir, &["init"]).assert().success();
    // `--approve` records the persistent consent that deferred batch execution needs.
    json_both_mock(&dir, &["index", "--approve"]);
    json_both_mock(&dir, &["batch", "resume"]);
    json_both_mock(&dir, &["index", "--approve"]);
    json_both_mock(&dir, &["batch", "resume"]);
    let status = json_both_mock(&dir, &["status"]);
    let tasks = status["tasks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| task["type"] == "markdownize")
        .collect::<Vec<_>>();
    assert_eq!(
        tasks.len(),
        1,
        "the scanned-PDF online task must not churn: {status}"
    );
    assert_eq!(
        tasks[0]["status"], "done",
        "OCR-from-scratch must reach Done: {status}"
    );
    assert!(
        !tasks[0]["output_ref"]
            .as_str()
            .unwrap()
            .starts_with("online:"),
        "Done must retain a normalized-instance output_ref: {status}"
    );
}

// ===========================================================================
// R22: exploratory-audit round 22 fixes (tasks/step3-bughunt22-fixes.md).
// ===========================================================================

/// Step 4 historical search retains old path aliases. Renaming a Tier B path to a
/// public live name therefore does not release its embedding hold: the old secret
/// alias remains reachable and secret-any-path wins until explicit approval.
#[test]
fn ct4_historical_secret_alias_keeps_hold_after_public_rename() {
    let dir = tempfile::tempdir().unwrap();
    let body = "# Notes\n\nalpha bravo charlie delta echo foxtrot golf hotel india juliet.\n";
    fs::write(dir.path().join("password_notes.md"), body).unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Tier B name + online + no --send-secrets → the embedding task is HELD.
    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    assert!(
        !embedding.is_empty()
            && embedding
                .iter()
                .all(|t| t["status"] == "paused" && t["fallback_reason"] == "secrets_tier_b_hold"),
        "R22-1 precondition: the Tier B embedding task must be held: {status}"
    );
    // Rename to a NON-secret live name. The historical secret alias is retained.
    fs::rename(
        dir.path().join("password_notes.md"),
        dir.path().join("notes.md"),
    )
    .unwrap();
    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    assert!(
        embedding
            .iter()
            .all(|task| task["status"] == "paused"
                && task["fallback_reason"] == "secrets_tier_b_hold"),
        "a reachable historical secret alias must keep the shared task held: {status}"
    );
}

/// R22-1 NEGATIVE control: while a secret twin is STILL live, the hold must NOT release.
/// The content-addressed dedup keeps the secret path as the survivor, so the single shared
/// task stays held even though a byte-identical non-secret twin is also live — and a plain
/// `batch resume` must not un-hold it either (only `--send-secrets` may).
#[test]
fn r22_1b_secret_hold_survives_while_a_secret_twin_is_live() {
    let dir = tempfile::tempdir().unwrap();
    let body = "# Notes\n\nalpha bravo charlie delta echo foxtrot golf hotel india juliet.\n";
    fs::write(dir.path().join("notes.md"), body).unwrap();
    fs::write(dir.path().join("password_backup.md"), body).unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);
    let assert_single_hold = |status: &Value, when: &str| {
        let embedding = tasks_of_type(status, "embedding");
        assert_eq!(
            embedding.len(),
            1,
            "R22-1b ({when}): byte-identical twins must share exactly one embedding task: {status}"
        );
        assert!(
            embedding
                .iter()
                .all(|t| t["status"] == "paused" && t["fallback_reason"] == "secrets_tier_b_hold"),
            "R22-1b ({when}): the shared task must stay held while a secret twin is live: {status}"
        );
    };
    assert_single_hold(
        &json_success_embed(&dir, "mock", &["status"]),
        "after index",
    );
    // A plain `batch resume` must not release the hold (N1: only --send-secrets lifts it).
    json_success_embed(&dir, "mock", &["batch", "resume"]);
    assert_single_hold(
        &json_success_embed(&dir, "mock", &["status"]),
        "after batch resume",
    );
}

/// R22-2 [major]: an existing NON-held embedding task (here Pending/`network_opt_in_required`)
/// must be DEMOTED to a `secrets_tier_b_hold` when the chunk's current path becomes a Tier B
/// secret name. Before the fix the "existing task ⇒ skip" idempotency guard left it Pending
/// forever, so `kcs status` and the quarantine record permanently disagreed about the hold.
#[test]
fn r22_2_existing_task_is_demoted_to_hold_when_path_becomes_secret() {
    let dir = tempfile::tempdir().unwrap();
    let body = "# Plain\n\nalpha bravo charlie delta echo foxtrot golf hotel india juliet.\n";
    fs::write(dir.path().join("plain.md"), body).unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Offline index with the embedding adapter configured but no opt-in (`--yes` ⇒
    // network_opt_in=false) → the task is Pending/network_opt_in_required (enqueue-only).
    json_success_embed(&dir, "mock", &["index", "--yes"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .any(|t| t["status"] == "pending" && t["fallback_reason"] == "network_opt_in_required"),
        "R22-2 precondition: a Pending/network_opt_in_required embedding task must exist: {status}"
    );
    // Rename INTO a Tier B name and re-index: the existing task must demote to a hold.
    fs::rename(
        dir.path().join("plain.md"),
        dir.path().join("credentials_backup.md"),
    )
    .unwrap();
    json_success_embed(&dir, "mock", &["index", "--yes"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    let held = embedding
        .iter()
        .find(|t| t["status"] == "paused" && t["fallback_reason"] == "secrets_tier_b_hold");
    assert!(
        held.is_some(),
        "R22-2: the existing task must be demoted to a secrets hold: {status}"
    );
    assert!(
        held.unwrap()["input_path"]
            .as_str()
            .unwrap()
            .ends_with("credentials_backup.md"),
        "R22-2: the demoted hold must name the current secret path: {status}"
    );
    assert!(
        !embedding
            .iter()
            .any(|t| t["fallback_reason"] == "network_opt_in_required"),
        "R22-2: no task may remain Pending/network_opt_in_required after the demotion: {status}"
    );
}

/// R22-2 NEGATIVE control: a DONE embedding task must NOT be demoted when the path later
/// becomes a Tier B secret name — its vector is real spend that already exists, so demoting
/// it would fake outstanding work and strand the stored vector.
#[test]
fn r22_2b_done_task_is_not_demoted_when_path_becomes_secret() {
    let dir = tempfile::tempdir().unwrap();
    let body = "# Plain\n\nalpha bravo charlie delta echo foxtrot golf hotel india juliet.\n";
    fs::write(dir.path().join("plain.md"), body).unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Online mock index → the embedding is sent and Done.
    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    assert!(
        tasks_of_type(&status, "embedding")
            .iter()
            .any(|t| t["status"] == "done"),
        "R22-2b precondition: the embedding task must be Done: {status}"
    );
    // Rename into a Tier B name and re-index: the Done task must stay Done.
    fs::rename(
        dir.path().join("plain.md"),
        dir.path().join("credentials_backup.md"),
    )
    .unwrap();
    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);
    let status = json_success_embed(&dir, "mock", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    assert!(
        embedding.iter().any(|t| t["status"] == "done"),
        "R22-2b: the Done embedding task must remain Done after the rename-in: {status}"
    );
    assert!(
        !embedding
            .iter()
            .any(|t| t["fallback_reason"] == "secrets_tier_b_hold"),
        "R22-2b: a Done task must never be demoted to a secrets hold: {status}"
    );
}

/// Step 4 all-history keeps each edited-away secret version eligible. Its hold is
/// real outstanding historical vector work, not an orphan to retire.
#[test]
fn ct4_edited_secret_history_keeps_each_version_held() {
    let dir = tempfile::tempdir().unwrap();
    let v1 = "# Secret\n\nalpha bravo charlie delta echo foxtrot golf hotel india.\n";
    let v2 = "# Secret\n\nkilo lima mike november oscar papa quebec romeo sierra.\n";
    let v3 = "# Secret\n\ntango uniform victor whiskey xray yankee zulu juliet.\n";
    fs::write(dir.path().join("password_notes.md"), v1).unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed_at(
        &dir,
        "mock",
        "2026-07-03T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    // Edit twice; each edit sends the previous chunk non-live under the same Tier B name.
    fs::write(dir.path().join("password_notes.md"), v2).unwrap();
    json_success_embed_at(
        &dir,
        "mock",
        "2026-07-05T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    fs::write(dir.path().join("password_notes.md"), v3).unwrap();
    json_success_embed_at(
        &dir,
        "mock",
        "2026-07-07T00:00:00Z",
        &["index", "--approve", "--online"],
    );
    let status = json_success_embed_at(&dir, "mock", "2026-07-07T00:00:00Z", &["status"]);
    let embedding = tasks_of_type(&status, "embedding");
    let held = embedding
        .iter()
        .filter(|t| t["status"] == "paused" && t["fallback_reason"] == "secrets_tier_b_hold")
        .count();
    let retired = embedding
        .iter()
        .filter(|t| t["status"] == "failed" && t["fallback_reason"] == "retired_non_live")
        .count();
    assert_eq!(
        held, 3,
        "each retained secret version must stay held for historical vector search: {status}"
    );
    assert_eq!(
        retired, 0,
        "retained historical holds are not non-live: {status}"
    );
    // `index_status` counts all three real historical embedding gaps.
    let search = json_success_embed(&dir, "mock", &["search", "juliet"]);
    assert_eq!(
        search["index_status"]["pending_enrichment_tasks"], 3,
        "all retained historical holds count as pending enrichment: {search}"
    );
}

/// R22-4 [major]: a real binary DOCUMENT whose extension is merely absent from the MIME
/// table (a `.bmp`/`.tiff`/`.heic`/legacy `.doc`) must be DISCLOSED via the
/// `skipped_unrecognized_binary_files` counter (the oversized-input visibility pattern),
/// not silently dropped with a false `enriched_ratio: 1.0`. An all-text scope reports 0.
#[test]
fn r22_4_unrecognized_binary_is_disclosed_not_silently_dropped() {
    let dir = tempfile::tempdir().unwrap();
    // `BM` header + high-bit bytes → a genuine binary (no text layer; folds to
    // application/octet-stream because `.bmp` is not in the MIME table).
    let mut bmp = b"BM".to_vec();
    bmp.extend((0u32..2000).map(|i| (i.wrapping_mul(97) & 0x7f) as u8 | 0x80));
    fs::write(dir.path().join("photo.bmp"), &bmp).unwrap();
    fs::write(
        dir.path().join("ok.md"),
        "# OK\n\nplain readable body alpha bravo charlie.\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    let index = json_success(&dir, &["index", "--yes"]);
    assert_eq!(
        index["skipped_unrecognized_binary_files"], 1,
        "R22-4: the unrecognized binary document must be disclosed, not silently dropped: {index}"
    );
    let unsupported_store = dir.path().join(".kcs/unsupported-inputs.jsonl");
    let first_len = fs::metadata(&unsupported_store).unwrap().len();
    let repeated = json_success(&dir, &["index", "--yes"]);
    assert_eq!(repeated["skipped_unrecognized_binary_files"], 1);
    assert_eq!(
        fs::metadata(&unsupported_store).unwrap().len(),
        first_len,
        "R23 CAND-014: an unchanged disposition must not grow the durable store"
    );
    let status = json_success(&dir, &["status"]);
    assert_eq!(status["unsupported_inputs"].as_array().unwrap().len(), 1);
    // NEGATIVE control: a scope of only recognized text reports zero.
    let clean = tempfile::tempdir().unwrap();
    fs::write(
        clean.path().join("ok.md"),
        "# OK\n\nplain readable body charlie delta echo.\n",
    )
    .unwrap();
    kcs(&clean, &["init"]).assert().success();
    let clean_index = json_success(&clean, &["index", "--yes"]);
    assert_eq!(
        clean_index["skipped_unrecognized_binary_files"], 0,
        "R22-4 control: an all-text scope must report zero unrecognized binaries: {clean_index}"
    );
}

#[test]
fn r23_cand_014_status_fails_closed_on_corrupt_unsupported_store() {
    let dir = tempfile::tempdir().unwrap();
    kcs(&dir, &["init"]).assert().success();
    fs::write(
        dir.path().join(".kcs/unsupported-inputs.jsonl"),
        b"{not-json}\n",
    )
    .unwrap();

    let stderr = kcs(&dir, &["status"])
        .assert()
        .failure()
        .get_output()
        .stderr
        .clone();
    assert!(
        String::from_utf8_lossy(&stderr).contains("KCS-E-STORE-CORRUPT-001"),
        "corrupt unsupported-input state must be surfaced"
    );
}

/// R22-5 [major]: a legacy `online:mistral_ocr_markdownize` task an OLDER build enqueued for
/// an octet-stream TEXT file (`.yaml`/`.json`/`Dockerfile`) must be RETIRED at send time, not
/// shipped to the OCR API and billed. R21-4 only stopped fresh enqueues; the send gate is the
/// migration path for tasks already sitting in `tasks.jsonl` after an upgrade.
#[test]
fn r22_5_legacy_octet_stream_text_task_is_retired_not_sent() {
    use kcs_pipeline::prepare::hash_bytes;
    use kcs_pipeline::task::{TaskDescriptor, TaskStatus, TaskStore, TaskType};
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("config.yaml"),
        "name: acme\nvalue: 42\nnested:\n  key: value\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    // `index --approve` records the markdownize network opt-in and (R21-4) enqueues NO
    // online task for the octet-stream text file.
    json_success(&dir, &["index", "--approve"]);
    assert_eq!(
        markdown_ledger_rows(&dir),
        0,
        "R22-5 precondition: index must not charge markdownize for octet-stream text"
    );
    // Inject the legacy online task an older build would have enqueued (input_hash matches
    // the current bytes so the only reason it can retire is the octet-stream-text gate).
    let input_hash = hash_bytes(&fs::read(dir.path().join("config.yaml")).unwrap());
    let legacy = TaskDescriptor {
        task_id: "r22-5-legacy-markdownize".to_owned(),
        task_type: TaskType::Markdownize,
        mode: None,
        input_path: "config.yaml".to_owned(),
        input_hash,
        previous_raw_hash: None,
        parent_run_id: None,
        changed_unit_keys: Vec::new(),
        output_ref: "online:mistral_ocr_markdownize".to_owned(),
        unit_keys: None,
        status: TaskStatus::Pending,
        attempts: 0,
        next_retry_at: None,
        deadline: None,
        heartbeat_at: None,
        fallback_reason: Some("ready_for_online_adapter".to_owned()),
        created_at: "2026-07-01T00:00:00Z".to_owned(),
        bbox_annotation_enabled: None,
        reserved_usd: None,
        reserved_month: None,
        reservation_id: None,
    };
    TaskStore::new(dir.path().join(".kcs"))
        .append(&legacy)
        .unwrap();
    // `batch resume` (with the OCR seam mocked) must RETIRE the legacy task without a send.
    run_markdownize_seam(&dir, "mock", None, &["batch", "resume"]);
    let status = run_markdownize_seam(&dir, "mock", None, &["status"]);
    assert!(
        tasks_of_type(&status, "markdownize").iter().any(|t| {
            t["output_ref"] == "online:mistral_ocr_markdownize"
                && t["status"] == "failed"
                && t["fallback_reason"] == "retired_non_live"
        }),
        "R22-5: the legacy octet-stream-text online task must be retired, not sent: {status}"
    );
    assert_eq!(
        markdown_ledger_rows(&dir),
        0,
        "R22-5: retiring the legacy task must add no markdownize charge row: {status}"
    );
}

/// R22-6 [major]: R21-6's AuthError live-stuck revive must extend to the MARKDOWNIZE
/// pipeline. A 401/403 leaves the online task Failed(`auth_error`) — non-retryable, so
/// `batch retry` (CT2-TASK-005: `max_attempts=0` is that command's contract) must NOT revive
/// it; only `batch resume` ("carry on, credentials fixed") may revive and execute it.
#[test]
fn r22_6_auth_error_markdownize_revives_on_resume_not_retry() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("doc.pdf"),
        fake_pdf(&["認証エラー markdownize 復活の回帰テスト本文です。"]),
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    // Enqueue the online markdownize task (Pending) and grant the network opt-in.
    run_markdownize_seam(&dir, "mock", None, &["index", "--online", "--approve"]);
    // Send under the auth_error seam → the online task fails auth_error.
    run_markdownize_seam(
        &dir,
        "auth_error",
        Some("2026-07-03T00:00:00Z"),
        &["batch", "resume"],
    );
    let has_auth_error = |status: &Value| {
        tasks_of_type(status, "markdownize")
            .iter()
            .any(|t| t["status"] == "failed" && t["fallback_reason"] == "auth_error")
    };
    assert!(
        has_auth_error(&run_markdownize_seam(&dir, "mock", None, &["status"])),
        "R22-6 precondition: the online markdownize task must be Failed(auth_error)"
    );
    // `batch retry` must NOT revive an auth_error task (CT2-TASK-005).
    let retry = run_markdownize_seam(
        &dir,
        "mock",
        Some("2026-07-03T01:00:00Z"),
        &["batch", "retry"],
    );
    assert_eq!(
        retry["tasks_executed"], 0,
        "R22-6: batch retry must not execute the auth_error task: {retry}"
    );
    assert!(
        has_auth_error(&run_markdownize_seam(&dir, "mock", None, &["status"])),
        "R22-6: batch retry must leave the auth_error task Failed (contract of that command)"
    );
    // `batch resume` with fixed credentials (mock) must revive AND execute it.
    let resumed = run_markdownize_seam(
        &dir,
        "mock",
        Some("2026-07-03T02:00:00Z"),
        &["batch", "resume"],
    );
    assert_eq!(
        resumed["tasks_executed"], 1,
        "R22-6: batch resume must revive the auth_error markdownize task and execute it: {resumed}"
    );
}

/// R22-7 [minor]: a scope holding only a Tier B `secrets_tier_b_hold` (with budget to spare)
/// must report `budget_paused: false` — a hold is not a budget pause. Before the fix
/// `compute_index_status` mapped every Paused task to `budget_paused: true`, misdirecting the
/// operator to "raise the budget" instead of `--send-secrets`.
#[test]
fn r22_7_budget_paused_false_for_secrets_hold() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("password_reset_flow.md"),
        "# Reset\n\nalpha bravo charlie delta echo foxtrot golf hotel india juliet.\n",
    )
    .unwrap();
    kcs(&dir, &["init"]).assert().success();
    json_success_embed(&dir, "mock", &["index", "--approve", "--online"]);
    let search = json_success_embed(&dir, "mock", &["search", "juliet"]);
    let index_status = &search["index_status"];
    assert_eq!(
        index_status["budget_paused"], false,
        "R22-7: a secrets hold must not report budget_paused=true: {search}"
    );
    assert_eq!(
        index_status["pending_enrichment_tasks"], 1,
        "R22-7: the single secrets hold must count as pending enrichment: {search}"
    );
}
