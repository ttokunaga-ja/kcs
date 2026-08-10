//! Contract tests for the Japanese word lane (`tasks/japanese-word-lane-design.md`).
//!
//! The whole suite is behind the `word-lane` feature, because with the feature
//! compiled out `build_word_match_expr` returns `None` and every path through
//! `fts_scope_search` is the one that existed before the lane did. Run with:
//!
//! ```sh
//! cargo test -p kio-cli --features word-lane --test word_lane_contract
//! ```
#![cfg(feature = "word-lane")]

use std::fs;

use assert_cmd::Command;
use serde_json::Value;
use tempfile::TempDir;

// ---------------------------------------------------------------------------
// Harness (mirrors crates/kio-cli/tests/step4b_p2c_contract.rs).
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
        .env_remove("KIO_TEST_QUERY_EMBED_TRACE")
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

fn init(dir: &TempDir) {
    success(dir, &["init"]);
}

fn paths_in(search: &Value) -> Vec<String> {
    search["results"]
        .as_array()
        .unwrap()
        .iter()
        .map(|result| {
            result["evidence_pointer"]["path_at_commit"]
                .as_str()
                .unwrap_or_default()
                .to_owned()
        })
        .collect()
}

/// The motivating case, end to end.
///
/// `期限` is two Unicode scalars, so `build_query_plan` drops it from a mixed
/// query outright: the query `期限はいつですか` script-segments into `期限` (Han,
/// dropped for length) and `はいつですか` (Hiragana, kept for length), and the
/// generated MATCH is over the whole token and that Hiragana run — neither of
/// which the document contains. Before this lane the query returned nothing,
/// even though the document is *about* the 期限.
///
/// The word lane segments the same query by part of speech instead, keeps the
/// content word, and finds it.
#[test]
fn wl1_a_two_scalar_content_word_finds_its_document() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("keiyaku.md"),
        "# 契約条件\n\n本件の期限は来月末とする。\n",
    )
    .unwrap();
    init(&dir);
    success(&dir, &["index", "--offline", "--approve"]);

    let search = success(&dir, &["search", "期限はいつですか", "--mode", "text"]);
    let paths = paths_in(&search);
    assert!(
        paths.iter().any(|path| path.contains("keiyaku")),
        "the word lane must find a document by a 2-scalar content word: {search}"
    );
}

/// The other half of the same rule: what the length rule keeps, part of speech
/// throws away. A query made only of particles must not drag in a document that
/// merely uses the same grammar, because the lane indexes no particles at all.
#[test]
fn wl2_a_grammar_only_query_does_not_retrieve_through_the_word_lane() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("keiyaku.md"),
        "# 契約条件\n\n本件の期限は来月末とする。\n",
    )
    .unwrap();
    init(&dir);
    success(&dir, &["index", "--offline", "--approve"]);

    // `をしたのは` is 助詞 / 動詞 / 助動詞 / 助詞 / 助詞 — the word lane keeps
    // only the verb, and the document has no such verb. Any hit here would have
    // to come from the trigram lane matching grammar, which is precisely the
    // failure mode 05 §1.3's feedback #2 removed.
    let search = success(&dir, &["search", "をしたのは", "--mode", "text"]);
    assert!(
        !paths_in(&search)
            .iter()
            .any(|path| path.contains("keiyaku")),
        "grammar alone must not retrieve the contract: {search}"
    );
}

/// The lane is an addition, not a replacement: an identifier is one opaque word
/// to a morphological analyzer and a substring to trigram, and the substring
/// query has to keep working.
#[test]
fn wl3_the_trigram_lane_still_answers_identifier_substrings() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("config.md"),
        "# Config\n\nThe related_images_min_area_ratio setting is read at search time.\n",
    )
    .unwrap();
    init(&dir);
    success(&dir, &["index", "--offline", "--approve"]);

    let search = success(&dir, &["search", "min_area_ratio", "--mode", "text"]);
    assert!(
        paths_in(&search).iter().any(|path| path.contains("config")),
        "substring matching must survive the lane split: {search}"
    );
}

/// Both lanes pointing at one document must not make it two results.
#[test]
fn wl4_a_document_both_lanes_find_is_returned_once() {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("gijiroku.md"),
        "# 議事録\n\n本日の議事録では契約の期限を確認した。\n",
    )
    .unwrap();
    init(&dir);
    success(&dir, &["index", "--offline", "--approve"]);

    let search = success(
        &dir,
        &["search", "契約の期限を確認した議事録", "--mode", "text"],
    );
    let hits = paths_in(&search)
        .into_iter()
        .filter(|path| path.contains("gijiroku"))
        .count();
    assert_eq!(hits, 1, "fusion must not duplicate a document: {search}");
}
