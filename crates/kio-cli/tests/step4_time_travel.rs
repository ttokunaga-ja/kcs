use std::collections::BTreeSet;
use std::fs;

use assert_cmd::Command;
use kio_core::cas::{hash_bytes, ObjectKind, ObjectStore};
use kio_core::dag::{CommitObject, CommitStats, CommitType};
use kio_core::scope::Repository;
use rusqlite::{params, Connection};
use serde_json::Value;
use tempfile::TempDir;

// These are contract tests, not live-service tests. Keep every child hermetic even
// on a developer machine that happens to have adapter credentials or test seams.
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

fn kio(dir: &TempDir, args: &[&str], fixed_now: Option<&str>) -> Command {
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
    if let Some(now) = fixed_now {
        command.env("KIO_FIXED_NOW", now);
    }
    command
}

fn json_success(dir: &TempDir, args: &[&str]) -> Value {
    json_success_at(dir, args, None)
}

fn json_success_at(dir: &TempDir, args: &[&str], fixed_now: Option<&str>) -> Value {
    let output = kio(dir, args, fixed_now)
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_success_embed(dir: &TempDir, args: &[&str]) -> Value {
    let output = kio(dir, args, None)
        .env("KIO_TEST_GEMINI_EMBED", "mock")
        .arg("--json")
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_failure(dir: &TempDir, args: &[&str], code: i32) -> Value {
    json_failure_at(dir, args, code, None)
}

fn json_failure_at(dir: &TempDir, args: &[&str], code: i32, fixed_now: Option<&str>) -> Value {
    let output = kio(dir, args, fixed_now)
        .arg("--json")
        .assert()
        .code(code)
        .get_output()
        .stderr
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn init(dir: &TempDir) {
    json_success(dir, &["init"]);
}

fn index_at(dir: &TempDir, fixed_now: &str) -> Value {
    // `--offline` is deliberate: time travel must be reproducible from local
    // objects and must never make an adapter call in these fixtures.
    json_success_at(dir, &["index", "--offline", "--approve"], Some(fixed_now))
}

fn result_path(result: &Value) -> &str {
    result["evidence_pointer"]["path_at_commit"]
        .as_str()
        .expect("historical result path")
}

fn result_raw(result: &Value) -> &str {
    result["evidence_pointer"]["raw_hash"]
        .as_str()
        .expect("historical result raw hash")
}

fn result_commit(result: &Value) -> &str {
    result["evidence_pointer"]["commit"]
        .as_str()
        .expect("historical result commit")
}

fn results(value: &Value) -> &[Value] {
    value["results"].as_array().expect("search results array")
}

fn result_signatures(value: &Value) -> Vec<(String, String, String)> {
    results(value)
        .iter()
        .map(|result| {
            (
                result["chunk_hash"].as_str().unwrap().to_owned(),
                result_path(result).to_owned(),
                result_commit(result).to_owned(),
            )
        })
        .collect()
}

fn decode_base64url_no_pad(input: &str) -> Vec<u8> {
    fn sextet(byte: u8) -> u8 {
        match byte {
            b'A'..=b'Z' => byte - b'A',
            b'a'..=b'z' => byte - b'a' + 26,
            b'0'..=b'9' => byte - b'0' + 52,
            b'-' => 62,
            b'_' => 63,
            _ => panic!("invalid base64url byte"),
        }
    }

    let mut output = Vec::with_capacity(input.len() * 3 / 4);
    let mut accumulator = 0_u32;
    let mut bits = 0_u8;
    for byte in input.bytes() {
        accumulator = (accumulator << 6) | u32::from(sextet(byte));
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            output.push(((accumulator >> bits) & 0xff) as u8);
            accumulator &= if bits == 0 { 0 } else { (1_u32 << bits) - 1 };
        }
    }
    output
}

fn cursor_payload(token: &str) -> Value {
    let payload = token.rsplit_once('.').expect("signed cursor wire form").0;
    serde_json::from_slice(&decode_base64url_no_pad(payload)).unwrap()
}

fn search_all_history(dir: &TempDir, query: &str, limit: &str) -> Value {
    json_success(
        dir,
        &[
            "search",
            query,
            "--scope",
            ".",
            "--text",
            "--all-history",
            "--limit",
            limit,
        ],
    )
}

/// Follow a v2 cursor while omitting the selector after page 1. This intentionally
/// exercises the rule that replay inherits the signed canonical selector.
fn collect_all_history_by_cursor(dir: &TempDir, query: &str) -> Vec<(String, String, String)> {
    let mut page = json_success(
        dir,
        &[
            "search",
            query,
            "--scope",
            ".",
            "--text",
            "--all-history",
            "--limit",
            "1",
        ],
    );
    let mut collected = result_signatures(&page);
    for _ in 0..100 {
        let Some(cursor) = page["paging"]["next_cursor"].as_str().map(str::to_owned) else {
            return collected;
        };
        page = json_success(
            dir,
            &[
                "search", query, "--scope", ".", "--text", "--cursor", &cursor, "--limit", "1",
            ],
        );
        collected.extend(result_signatures(&page));
    }
    panic!("cursor did not terminate within the bounded fixture stream")
}

#[test]
fn ct4_timetravel_001_parser_exclusivity_duration_and_no_mutation() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    fs::write(
        dir.path().join("parser.md"),
        "# Parser\n\nselectorfixture duration parser contract\n",
    )
    .unwrap();
    index_at(&dir, "2026-07-12T00:00:00Z");

    // Every positive integer duration unit executes. Redundant --all-history is
    // accepted with --since because it canonicalizes to one effective selector.
    for duration in ["1s", "1m", "1h", "1d", "1w"] {
        json_success_at(
            &dir,
            &[
                "search",
                "selectorfixture",
                "--scope",
                ".",
                "--text",
                "--since",
                duration,
            ],
            Some("2026-07-13T00:00:00Z"),
        );
    }
    for selector in [
        vec!["--at", "HEAD"],
        vec!["--all-history"],
        vec!["--include-deleted"],
    ] {
        let mut args = vec!["search", "selectorfixture", "--scope", ".", "--text"];
        args.extend(selector);
        json_success(&dir, &args);
    }
    let since = json_success_at(
        &dir,
        &[
            "search",
            "selectorfixture",
            "--scope",
            ".",
            "--text",
            "--since",
            "7d",
            "--limit",
            "100",
        ],
        Some("2026-07-13T00:00:00Z"),
    );
    let redundant = json_success_at(
        &dir,
        &[
            "search",
            "selectorfixture",
            "--scope",
            ".",
            "--text",
            "--all-history",
            "--since",
            "7d",
            "--limit",
            "100",
        ],
        Some("2026-07-13T00:00:00Z"),
    );
    assert_eq!(since["results"], redundant["results"]);

    let db_path = dir.path().join(".kio/index/sqlite.db");
    let registry_path = dir.path().join(".test-data/kio/scope-registry.sqlite");
    let db_before = fs::read(&db_path).unwrap();
    let registry_before = fs::read(&registry_path).unwrap();
    let head_before = fs::read(dir.path().join(".kio/HEAD")).unwrap();
    let invalid: &[&[&str]] = &[
        &["--at", "HEAD", "--all-history"],
        &["--at", "HEAD", "--include-deleted"],
        &["--at", "HEAD", "--since", "1d"],
        &["--include-deleted", "--all-history"],
        &["--include-deleted", "--since", "1d"],
        &["--since", "0d"],
        &["--since", "7"],
        &["--since", "2026-07-01"],
        &["--since", "1.5d"],
        &["--since", "7x"],
        &["--since", "18446744073709551616s"],
        &["--since", "18446744073709551615w"],
    ];
    for suffix in invalid {
        let mut args = vec!["search", "selectorfixture", "--scope", ".", "--text"];
        args.extend_from_slice(suffix);
        let error = json_failure_at(&dir, &args, 2, Some("2026-07-13T00:00:00Z"));
        assert_eq!(error["error_code"], "KIO-E-CONFIG-USAGE-001");
        assert_eq!(fs::read(&db_path).unwrap(), db_before, "args={args:?}");
        assert_eq!(
            fs::read(&registry_path).unwrap(),
            registry_before,
            "args={args:?}"
        );
        assert_eq!(
            fs::read(dir.path().join(".kio/HEAD")).unwrap(),
            head_before,
            "args={args:?}"
        );
    }
}

#[test]
fn ct4_timetravel_002_exact_at_hash_tag_head_and_normalize_none() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    let a = b"# Version\n\nversionfixture payload alpha\n";
    let b = b"# Version\n\nversionfixture payload beta\n";
    fs::write(dir.path().join("version.md"), a).unwrap();
    let c1 = index_at(&dir, "2026-07-10T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    json_success(&dir, &["tag", "old", &c1]);

    fs::write(dir.path().join("version.md"), b).unwrap();
    let c2 = index_at(&dir, "2026-07-11T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();

    // Remove the historical projection while leaving canonical commit/tree CAS
    // intact. The first --at lookup must lazily and exactly re-project C1.
    let conn = Connection::open(dir.path().join(".kio/index/sqlite.db")).unwrap();
    conn.execute(
        "DELETE FROM tree_entries WHERE commit_hash = ?1",
        params![c1],
    )
    .unwrap();
    drop(conn);

    for (index, operand) in [&c1, "old"].into_iter().enumerate() {
        let at = json_success(
            &dir,
            &[
                "search",
                "versionfixture",
                "--scope",
                ".",
                "--text",
                "--at",
                operand,
            ],
        );
        assert_eq!(at["searched_scopes"][0]["snapshot_at"], c1);
        assert!(!results(&at).is_empty());
        assert!(results(&at)
            .iter()
            .all(|result| { result_raw(result) == hash_bytes(a) && result_commit(result) == c1 }));
        if index == 0 {
            let conn = Connection::open(dir.path().join(".kio/index/sqlite.db")).unwrap();
            let projected: i64 = conn
                .query_row(
                    "SELECT count(*) FROM tree_entries WHERE commit_hash = ?1",
                    params![c1],
                    |row| row.get(0),
                )
                .unwrap();
            assert!(projected > 0, "--at must lazily project canonical C1 tree");
        }
    }
    let head = json_success(
        &dir,
        &[
            "search",
            "versionfixture",
            "--scope",
            ".",
            "--text",
            "--at",
            "HEAD",
        ],
    );
    assert_eq!(head["searched_scopes"][0]["snapshot_at"], c2);
    assert!(results(&head)
        .iter()
        .all(|result| result_raw(result) == hash_bytes(b)));

    // A manual snapshot captures the raw file but deliberately has no normalize
    // binding. A later index may create normalized/chunk/cache rows for the exact
    // same raw bytes; --at must still return no chunk for the raw-only tree entry.
    fs::write(
        dir.path().join("latent.md"),
        "# Latent\n\nlatentnormalizefixture must not leak backward\n",
    )
    .unwrap();
    let raw_only = json_success_at(
        &dir,
        &["snapshot", "create", "-m", "raw only"],
        Some("2026-07-11T01:00:00Z"),
    )["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    index_at(&dir, "2026-07-11T02:00:00Z");
    let absent = json_success(
        &dir,
        &[
            "search",
            "latentnormalizefixture",
            "--scope",
            ".",
            "--text",
            "--at",
            &raw_only,
        ],
    );
    assert!(results(&absent).is_empty(), "{absent}");
}

#[test]
fn ct4_timetravel_003_edit_rename_aliases_twins_and_cursor_paging() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    let edit_old = b"# Edit\n\nhistoryfixture edited value oldneedle\n";
    let edit_new = b"# Edit\n\nhistoryfixture edited value newneedle\n";
    let renamed = b"# Rename\n\nhistoryfixture unchanged rename payload\n";
    fs::write(dir.path().join("edit.md"), edit_old).unwrap();
    fs::write(dir.path().join("old.md"), renamed).unwrap();
    let c1 = index_at(&dir, "2026-07-09T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();

    fs::write(dir.path().join("edit.md"), edit_new).unwrap();
    fs::rename(dir.path().join("old.md"), dir.path().join("new.md")).unwrap();
    let c2 = index_at(&dir, "2026-07-10T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();

    let history = search_all_history(&dir, "historyfixture", "100");
    let raw_set = results(&history)
        .iter()
        .map(result_raw)
        .collect::<BTreeSet<_>>();
    assert!(raw_set.contains(hash_bytes(edit_old).as_str()));
    assert!(raw_set.contains(hash_bytes(edit_new).as_str()));

    let renamed_hash = hash_bytes(renamed);
    let rename_hits = results(&history)
        .iter()
        .filter(|result| result_raw(result) == renamed_hash)
        .collect::<Vec<_>>();
    assert_eq!(
        rename_hits
            .iter()
            .map(|result| result_path(result))
            .collect::<BTreeSet<_>>(),
        BTreeSet::from(["new.md", "old.md"])
    );
    assert_eq!(
        rename_hits
            .iter()
            .map(|result| result_commit(result))
            .collect::<BTreeSet<_>>(),
        BTreeSet::from([c1.as_str(), c2.as_str()])
    );
    for result in &rename_hits {
        assert_eq!(result["current_paths"], serde_json::json!(["new.md"]));
        assert_eq!(result["current_path"], "new.md");
    }

    // Identical bytes under two live names are twins, not inferred rename lineage.
    fs::write(dir.path().join("copy.md"), renamed).unwrap();
    index_at(&dir, "2026-07-11T00:00:00Z");
    let twins = search_all_history(&dir, "historyfixture", "100");
    let twin_hits = results(&twins)
        .iter()
        .filter(|result| result_raw(result) == renamed_hash)
        .collect::<Vec<_>>();
    assert_eq!(
        twin_hits
            .iter()
            .map(|result| result_path(result))
            .collect::<BTreeSet<_>>(),
        BTreeSet::from(["copy.md", "new.md", "old.md"])
    );
    for result in &twin_hits {
        assert_eq!(
            result["current_paths"],
            serde_json::json!(["copy.md", "new.md"])
        );
        assert!(
            result.get("current_path").is_none(),
            "singular current_path is ambiguous for twins: {result}"
        );
    }

    // Pagination happens after alias expansion. A boundary inside the three aliases
    // must resume each alias exactly once and in the same order as an unpaged search.
    assert_eq!(
        collect_all_history_by_cursor(&dir, "historyfixture"),
        result_signatures(&twins)
    );
}

#[test]
fn ct4_timetravel_004_include_deleted_uses_final_version_and_frozen_tree() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    let a = b"# Gone\n\ntimelinefixture deleted alpha old version\n";
    let b = b"# Gone\n\ntimelinefixture deleted beta final version\n";
    let live = b"# Live\n\ntimelinefixture still live\n";
    fs::write(dir.path().join("gone.md"), a).unwrap();
    index_at(&dir, "2026-07-09T00:00:00Z");
    fs::write(dir.path().join("gone.md"), b).unwrap();
    let c2 = index_at(&dir, "2026-07-10T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    fs::remove_file(dir.path().join("gone.md")).unwrap();
    fs::write(dir.path().join("live.md"), live).unwrap();
    index_at(&dir, "2026-07-11T00:00:00Z");

    let included = json_success(
        &dir,
        &[
            "search",
            "timelinefixture",
            "--scope",
            ".",
            "--text",
            "--include-deleted",
            "--limit",
            "100",
        ],
    );
    let raws = results(&included)
        .iter()
        .map(result_raw)
        .collect::<BTreeSet<_>>();
    assert!(raws.contains(hash_bytes(b).as_str()));
    assert!(raws.contains(hash_bytes(live).as_str()));
    assert!(!raws.contains(hash_bytes(a).as_str()));
    let deleted = results(&included)
        .iter()
        .find(|result| result_raw(result) == hash_bytes(b))
        .unwrap();
    assert_eq!(result_path(deleted), "gone.md");
    assert_eq!(result_commit(deleted), c2);
    let repo = Repository::open(dir.path()).unwrap();
    let tree = repo
        .read_tree(&repo.read_commit(&c2).unwrap().tree)
        .unwrap();
    assert!(tree
        .entries
        .iter()
        .any(|entry| entry.path == "gone.md" && entry.raw_hash == hash_bytes(b)));

    let page1 = json_success(
        &dir,
        &[
            "search",
            "timelinefixture",
            "--scope",
            ".",
            "--text",
            "--include-deleted",
            "--limit",
            "1",
        ],
    );
    let cursor = page1["paging"]["next_cursor"]
        .as_str()
        .expect("two-result fixture must page")
        .to_owned();
    let page2_before = json_success(
        &dir,
        &[
            "search",
            "timelinefixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            &cursor,
            "--limit",
            "1",
        ],
    );

    // Advance HEAD. The same semantic chunk is now live under survivor.md, so live
    // wins and the stale deleted alias at gone.md is not emitted for this raw.
    fs::write(dir.path().join("survivor.md"), b).unwrap();
    index_at(&dir, "2026-07-12T00:00:00Z");
    let fresh = json_success(
        &dir,
        &[
            "search",
            "timelinefixture",
            "--scope",
            ".",
            "--text",
            "--include-deleted",
            "--limit",
            "100",
        ],
    );
    let b_paths = results(&fresh)
        .iter()
        .filter(|result| result_raw(result) == hash_bytes(b))
        .map(result_path)
        .collect::<Vec<_>>();
    assert_eq!(b_paths, ["survivor.md"]);

    // PC19/PC21 (05 §1.5 L180-191): the re-index above changed `chunk_fts`
    // content (one of PC20's 6 `index_generation` rotation triggers), so the
    // page-1 cursor from before it is now rejected — "再検索が正" — instead
    // of silently replaying against a stale snapshot whose BM25 ranking basis
    // (corpus-wide document-frequency/average-length statistics) has since
    // shifted. This supersedes the pre-PC19 "cursor replay uses the signed
    // snapshot/tree, never current HEAD/manifest.json" contract this test
    // used to exercise past this exact same re-index — that invariant still
    // holds for anything short of an index_generation change, but a `chunk_fts`
    // content change is no longer one of the cases a frozen cursor survives.
    let err = json_failure(
        &dir,
        &[
            "search",
            "timelinefixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            &cursor,
            "--limit",
            "1",
        ],
        2,
    );
    assert_eq!(err["error_code"], "KIO-E-SEARCH-CURSOR-001");
    assert_eq!(err["context"]["reason"], "index_generation_mismatch");
    // `page2_before` (replayed prior to the re-index) is untouched by this —
    // still a normal, valid page.
    assert!(!page2_before["results"].as_array().unwrap().is_empty());
}

#[test]
fn ct4_timetravel_006_cursor_binds_and_inherits_selector() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    for name in ["a.md", "b.md", "c.md"] {
        fs::write(
            dir.path().join(name),
            format!("# Cursor {name}\n\ncursorfixture historical paging {name}\n"),
        )
        .unwrap();
    }
    let c1 = index_at(&dir, "2026-07-09T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    fs::write(
        dir.path().join("a.md"),
        "# Cursor A2\n\ncursorfixture historical paging changed\n",
    )
    .unwrap();
    let c2 = index_at(&dir, "2026-07-10T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();

    let page1 = json_success(
        &dir,
        &[
            "search",
            "cursorfixture",
            "--scope",
            ".",
            "--text",
            "--all-history",
            "--limit",
            "1",
        ],
    );
    let cursor = page1["paging"]["next_cursor"].as_str().unwrap().to_owned();
    let payload = cursor_payload(&cursor);
    assert_eq!(payload["v"], 2);
    assert_eq!(
        payload["time_travel"],
        serde_json::json!({"all_history": true})
    );
    assert!(payload["scopes"][0]["max_association_rowid"]
        .as_u64()
        .is_some());
    assert!(payload["scopes"][0]["chunking_config_hash"]
        .as_str()
        .is_some_and(|hash| hash.starts_with("sha256:")));
    let inherited = json_success(
        &dir,
        &[
            "search",
            "cursorfixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            &cursor,
            "--limit",
            "1",
        ],
    );
    let repeated = json_success(
        &dir,
        &[
            "search",
            "cursorfixture",
            "--scope",
            ".",
            "--text",
            "--all-history",
            "--cursor",
            &cursor,
            "--limit",
            "1",
        ],
    );
    assert_eq!(inherited["results"], repeated["results"]);
    let mismatch = json_failure(
        &dir,
        &[
            "search",
            "cursorfixture",
            "--scope",
            ".",
            "--text",
            "--include-deleted",
            "--cursor",
            &cursor,
        ],
        2,
    );
    assert_eq!(mismatch["error_code"], "KIO-E-SEARCH-CURSOR-001");

    let at_page1 = json_success(
        &dir,
        &[
            "search",
            "cursorfixture",
            "--scope",
            ".",
            "--text",
            "--at",
            &c1,
            "--limit",
            "1",
        ],
    );
    let at_cursor = at_page1["paging"]["next_cursor"].as_str().unwrap();
    let at_mismatch = json_failure(
        &dir,
        &[
            "search",
            "cursorfixture",
            "--scope",
            ".",
            "--text",
            "--at",
            &c2,
            "--cursor",
            at_cursor,
        ],
        2,
    );
    assert_eq!(at_mismatch["error_code"], "KIO-E-SEARCH-CURSOR-001");

    // A caller cannot modify any signed maximum/cutoff field. Corrupt one payload
    // byte while keeping the signature, which must fail before the token is trusted.
    let mut tampered = cursor.clone().into_bytes();
    let payload_index = tampered
        .iter()
        .position(|byte| *byte != b'.')
        .expect("non-empty cursor payload");
    tampered[payload_index] = if tampered[payload_index] == b'A' {
        b'B'
    } else {
        b'A'
    };
    let tampered = String::from_utf8(tampered).unwrap();
    let error = json_failure(
        &dir,
        &[
            "search",
            "cursorfixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            &tampered,
        ],
        2,
    );
    assert_eq!(error["error_code"], "KIO-E-SEARCH-CURSOR-001");
}

#[test]
fn ct4_timetravel_005_since_includes_cutoff_and_freezes_it_in_cursor() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    fs::write(
        dir.path().join("before.md"),
        "# Before\n\nboundaryfixture one second before cutoff\n",
    )
    .unwrap();
    index_at(&dir, "2026-07-05T23:59:59Z");

    // Make the equality result deliberately lower-ranked than the two short,
    // term-dense after results, so it crosses the first page boundary.
    let equality = format!(
        "# Equal\n\nboundaryfixture exactly cutoff {}\n",
        "lengthpadding ".repeat(250)
    );
    fs::write(dir.path().join("equal.md"), equality).unwrap();
    index_at(&dir, "2026-07-06T00:00:00Z");

    fs::write(
        dir.path().join("after-a.md"),
        "# After A\n\nboundaryfixture boundaryfixture after a\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("after-b.md"),
        "# After B\n\nboundaryfixture boundaryfixture after b\n",
    )
    .unwrap();
    index_at(&dir, "2026-07-12T00:00:00Z");

    let full = json_success_at(
        &dir,
        &[
            "search",
            "boundaryfixture",
            "--scope",
            ".",
            "--text",
            "--since",
            "7d",
            "--limit",
            "100",
        ],
        Some("2026-07-13T00:00:00Z"),
    );
    let paths = results(&full)
        .iter()
        .map(result_path)
        .collect::<BTreeSet<_>>();
    assert!(paths.contains("equal.md"), "cutoff equality is inclusive");
    assert!(paths.contains("after-a.md"));
    assert!(paths.contains("after-b.md"));
    assert!(
        !paths.contains("before.md"),
        "one second before is excluded"
    );

    let page1 = json_success_at(
        &dir,
        &[
            "search",
            "boundaryfixture",
            "--scope",
            ".",
            "--text",
            "--since",
            "7d",
            "--limit",
            "2",
        ],
        Some("2026-07-13T00:00:00Z"),
    );
    assert!(
        results(&page1)
            .iter()
            .all(|result| result_path(result) != "equal.md"),
        "fixture requires equality at the page boundary: {page1}"
    );
    let cursor = page1["paging"]["next_cursor"]
        .as_str()
        .expect("equality result remains for page 2")
        .to_owned();
    let payload = cursor_payload(&cursor);
    assert_eq!(payload["v"], 2);
    assert_eq!(
        payload["time_travel"],
        serde_json::json!({"all_history": true, "since": "604800s"})
    );
    assert_eq!(payload["since_cutoff"], "2026-07-06T00:00:00Z");
    let page2_same_now = json_success_at(
        &dir,
        &[
            "search",
            "boundaryfixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            &cursor,
            "--limit",
            "10",
        ],
        Some("2026-07-13T00:00:00Z"),
    );
    assert!(results(&page2_same_now)
        .iter()
        .any(|result| result_path(result) == "equal.md"));

    // At this invocation time a recomputed 7d cutoff would be July 7 and would
    // drop equal.md. Selector-less replay must instead retain the signed July 6
    // page-1 cutoff. Explicit 1w is the same canonical selector and is accepted.
    let page2_next_day = json_success_at(
        &dir,
        &[
            "search",
            "boundaryfixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            &cursor,
            "--limit",
            "10",
        ],
        Some("2026-07-14T00:00:00Z"),
    );
    let page2_one_week = json_success_at(
        &dir,
        &[
            "search",
            "boundaryfixture",
            "--scope",
            ".",
            "--text",
            "--since",
            "1w",
            "--cursor",
            &cursor,
            "--limit",
            "10",
        ],
        Some("2026-07-14T00:00:00Z"),
    );
    assert_eq!(page2_same_now["results"], page2_next_day["results"]);
    assert_eq!(page2_same_now["results"], page2_one_week["results"]);

    let mismatch = json_failure_at(
        &dir,
        &[
            "search",
            "boundaryfixture",
            "--scope",
            ".",
            "--text",
            "--since",
            "8d",
            "--cursor",
            &cursor,
        ],
        2,
        Some("2026-07-13T00:00:00Z"),
    );
    assert_eq!(mismatch["error_code"], "KIO-E-SEARCH-CURSOR-001");
}

#[test]
fn ct4_timetravel_006_cursor_freezes_config_association_maximum() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    fs::write(
        dir.path().join("rank-a.md"),
        "# A\n\nassociationfixture associationfixture associationfixture rank a\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("rank-b.md"),
        "# B\n\nassociationfixture associationfixture rank b\n",
    )
    .unwrap();
    fs::write(
        dir.path().join("late.md"),
        "# Late\n\nassociationfixture lateassociation candidate\n",
    )
    .unwrap();
    index_at(&dir, "2026-07-10T00:00:00Z");
    let config_c1 = fs::read_to_string(dir.path().join(".kio/config.toml")).unwrap();

    // A config change that preserves these short chunk boundaries must append a
    // second association to the same immutable chunk ids.
    fs::write(
        dir.path().join(".kio/config.toml"),
        "kio_format_version = \"0.1.0\"\n[chunking]\nstrategy = \"heading\"\nmax_chars = 3999\n",
    )
    .unwrap();
    index_at(&dir, "2026-07-11T00:00:00Z");

    let db_path = dir.path().join(".kio/index/sqlite.db");
    let conn = Connection::open(&db_path).unwrap();
    let late_chunk: String = conn
        .query_row(
            "SELECT chunk_id FROM chunks WHERE text LIKE '%lateassociation%' LIMIT 1",
            [],
            |row| row.get(0),
        )
        .unwrap();
    let current_config: String = conn
        .query_row(
            "SELECT chunking_config_hash
               FROM chunk_config_generations
              GROUP BY chunking_config_hash
              ORDER BY MAX(association_rowid) DESC
              LIMIT 1",
            [],
            |row| row.get(0),
        )
        .unwrap();
    let older_config: String = conn
        .query_row(
            "SELECT chunking_config_hash
               FROM chunk_config_generations
              WHERE chunking_config_hash <> ?1
              ORDER BY association_rowid
              LIMIT 1",
            params![current_config],
            |row| row.get(0),
        )
        .unwrap();
    assert_ne!(current_config, older_config);
    conn.execute(
        "DELETE FROM chunk_config_generations
          WHERE chunk_id = ?1 AND chunking_config_hash = ?2",
        params![late_chunk, current_config],
    )
    .unwrap();
    drop(conn);

    let page1 = json_success(
        &dir,
        &[
            "search",
            "associationfixture",
            "--scope",
            ".",
            "--text",
            "--all-history",
            "--limit",
            "1",
        ],
    );
    assert!(results(&page1).iter().all(|result| !result["snippet"]
        .as_str()
        .unwrap()
        .contains("lateassociation")));
    let cursor = page1["paging"]["next_cursor"]
        .as_str()
        .expect("two pre-existing current-config candidates must page")
        .to_owned();

    // Publish the missing C2 association after page 1. A fresh search sees it,
    // while replay is frozen at the token's max_association_rowid.
    let conn = Connection::open(&db_path).unwrap();
    conn.execute(
        "INSERT INTO chunk_config_generations
             (chunk_id, chunking_config_hash, created_at)
         VALUES (?1, ?2, '2026-07-12T00:00:00Z')",
        params![late_chunk, current_config],
    )
    .unwrap();
    drop(conn);
    let replay = json_success(
        &dir,
        &[
            "search",
            "associationfixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            &cursor,
            "--limit",
            "100",
        ],
    );
    assert!(results(&replay).iter().all(|result| !result["snippet"]
        .as_str()
        .unwrap()
        .contains("lateassociation")));
    let fresh = search_all_history(&dir, "associationfixture", "100");
    assert!(results(&fresh).iter().any(|result| result["snippet"]
        .as_str()
        .unwrap()
        .contains("lateassociation")));

    // Restoring the older effective config changes the sorted per-scope mapping,
    // even though its associations are below the frozen maximum.
    fs::write(dir.path().join(".kio/config.toml"), config_c1).unwrap();
    let config_mismatch = json_failure(
        &dir,
        &[
            "search",
            "associationfixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            &cursor,
        ],
        2,
    );
    assert_eq!(config_mismatch["error_code"], "KIO-E-SEARCH-CURSOR-001");
}

#[test]
fn ct4_timetravel_011_historical_reindex_enriches_only_selected_snapshot() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    fs::write(
        dir.path().join("history.md"),
        "# Historical selected\n\nhistoricalselectedmarker belongs only to C1. This paragraph is deliberately long so the smaller current chunk configuration creates fresh text spans and embeddings.\n",
    )
    .unwrap();
    let c1 = json_success_embed(&dir, &["index", "--approve"])["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();

    fs::write(
        dir.path().join("history.md"),
        "# Current nonselected\n\ncurrentnonselectedmarker belongs only to C2. This paragraph is also deliberately long and must not receive the new current-config association from reindexing C1.\n",
    )
    .unwrap();
    let c2 = json_success_embed(&dir, &["index", "--approve"])["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_ne!(c1, c2);

    let repo = Repository::open(dir.path()).unwrap();
    let c1_tree = repo
        .read_tree(&repo.read_commit(&c1).unwrap().tree)
        .unwrap();
    let c2_tree = repo
        .read_tree(&repo.read_commit(&c2).unwrap().tree)
        .unwrap();
    let c1_entry = c1_tree
        .entries
        .iter()
        .find(|entry| entry.path == "history.md")
        .unwrap();
    let c2_entry = c2_tree
        .entries
        .iter()
        .find(|entry| entry.path == "history.md")
        .unwrap();
    let c1_raw = c1_entry.raw_hash.clone();
    let c2_raw = c2_entry.raw_hash.clone();
    let c1_gen = c1_entry.normalize.as_ref().unwrap().gen;
    let head_before = fs::read(dir.path().join(".kio/HEAD")).unwrap();
    let branch_before = fs::read(dir.path().join(".kio/refs/heads/main")).unwrap();

    // QA21 (step4b-contract-tests-p3a.md §G, 07-adapter-spec.md §3): the
    // network-approval gate's positive condition needs
    // `[adapter.policy].allow_network = true` to remain SET after this
    // wholesale config.toml rewrite (unset/lost = gate not established) —
    // the two `--approve` calls above already set it, so this full
    // overwrite must carry it forward explicitly or the scope silently
    // loses its persisted opt-in.
    fs::write(
        dir.path().join(".kio/config.toml"),
        "kio_format_version = \"0.1.0\"\n[chunking]\nstrategy = \"heading\"\nmax_chars = 48\n[adapter.policy]\nallow_network = true\n",
    )
    .unwrap();
    let current_config = kio_index::chunking::chunking_config_hash("heading", 48).unwrap();
    let count_associations = |raw_hash: &str| -> i64 {
        let conn = Connection::open(dir.path().join(".kio/index/sqlite.db")).unwrap();
        conn.query_row(
            "SELECT COUNT(*)
               FROM chunks c
               JOIN chunk_config_generations cg ON cg.chunk_id = c.chunk_id
              WHERE c.raw_hash = ?1 AND cg.chunking_config_hash = ?2",
            params![raw_hash, current_config],
            |row| row.get(0),
        )
        .unwrap()
    };
    assert_eq!(count_associations(&c1_raw), 0);
    assert_eq!(count_associations(&c2_raw), 0);

    let output = json_success_embed(&dir, &["reindex", "--at", &c1]);
    assert_eq!(output["status"], "reindexed");
    assert_eq!(output["snapshot_at"], c1);
    assert_eq!(output["head_commit"], c2);
    assert!(output["rebuilt_chunks"].as_u64().unwrap() > 0);
    assert!(output["embedding_tasks_executed"].as_u64().unwrap() > 0);

    assert_eq!(fs::read(dir.path().join(".kio/HEAD")).unwrap(), head_before);
    assert_eq!(
        fs::read(dir.path().join(".kio/refs/heads/main")).unwrap(),
        branch_before
    );
    assert!(count_associations(&c1_raw) > 0);
    assert_eq!(
        count_associations(&c2_raw),
        0,
        "historical reindex must not enrich non-selected history"
    );

    let conn = Connection::open(dir.path().join(".kio/index/sqlite.db")).unwrap();
    let (selected_vectors, min_gen, max_gen): (i64, i64, i64) = conn
        .query_row(
            "SELECT COUNT(e.id), MIN(c.gen), MAX(c.gen)
               FROM chunks c
               JOIN chunk_config_generations cg ON cg.chunk_id = c.chunk_id
               LEFT JOIN embeddings e
                 ON e.target_type = 'chunk' AND e.target_id = c.text_hash
              WHERE c.raw_hash = ?1 AND cg.chunking_config_hash = ?2",
            params![c1_raw, current_config],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .unwrap();
    assert!(
        selected_vectors > 0,
        "selected current-config chunks need embeddings"
    );
    assert_eq!(min_gen, c1_gen as i64);
    assert_eq!(
        max_gen, c1_gen as i64,
        "historical reindex must not bump gen"
    );
    drop(conn);

    let selected_search = json_success(
        &dir,
        &[
            "search",
            "historicalselectedmarker",
            "--scope",
            ".",
            "--text",
            "--at",
            &c1,
        ],
    );
    assert!(!results(&selected_search).is_empty());
    let nonselected_search = json_success(
        &dir,
        &[
            "search",
            "currentnonselectedmarker",
            "--scope",
            ".",
            "--text",
        ],
    );
    assert!(
        results(&nonselected_search).is_empty(),
        "C2 must remain missing under the new config: {nonselected_search}"
    );

    let force_at = json_failure(&dir, &["reindex", "--force", "--yes", "--at", &c1], 2);
    assert_eq!(force_at["error_code"], "KIO-E-CONFIG-USAGE-001");
}

fn discard_commit_tree(dir: &TempDir, commit_hash: &str) {
    let repo = Repository::open(dir.path()).unwrap();
    let tree_hash = repo.read_commit(commit_hash).unwrap().tree;
    let path = ObjectStore::new(repo.kio_dir())
        .object_path(ObjectKind::Tree, &tree_hash)
        .unwrap();
    fs::remove_file(path).unwrap();
}

#[test]
fn ct4_timetravel_007_shallow_history_rejects_cached_tree_rows() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    fs::write(
        dir.path().join("history.md"),
        "# Old\n\nshallowhistoryfixture old value\n",
    )
    .unwrap();
    let c1 = index_at(&dir, "2026-07-09T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    fs::write(
        dir.path().join("history.md"),
        "# New\n\nreplacement without the historical search term\n",
    )
    .unwrap();
    index_at(&dir, "2026-07-10T00:00:00Z");

    // C1's tree_entries rows remain in sqlite after C2, but they are only cache.
    let conn = Connection::open(dir.path().join(".kio/index/sqlite.db")).unwrap();
    let cached: i64 = conn
        .query_row(
            "SELECT count(*) FROM tree_entries WHERE commit_hash = ?1",
            params![c1],
            |row| row.get(0),
        )
        .unwrap();
    assert!(cached > 0, "fixture must retain historical cache rows");
    drop(conn);
    discard_commit_tree(&dir, &c1);

    // `--at c1` targets the shallow commit itself (PC47 — 05 §2.2 "kio search
    // --at <shallow-commit>" — still hard-fails: the exact target's whole tree
    // is required, so there is no partial degradation to fall back to).
    let error = json_failure(
        &dir,
        &[
            "search",
            "shallowhistoryfixture",
            "--scope",
            ".",
            "--text",
            "--at",
            c1.as_str(),
        ],
        1,
    );
    assert_eq!(error["error_code"], "KIO-E-COMMIT-SHALLOW-001");

    // PC45/PC46 (05 §1.6/§2.2): `--all-history` walks FROM HEAD (C2, not
    // shallow) and encounters the shallow c1 only as an *ancestor* mid-walk —
    // that is skipped and counted (`shallow_skipped`) rather than hard-failing
    // the whole scope/command, superseding the pre-PC45 contract this loop
    // used to assert (a shallow ancestor anywhere in the walk was a command-
    // wide `KIO-E-COMMIT-SHALLOW-001`/exit 1, taking down even an unrelated
    // healthy sibling scope in a multi-scope search). The fixture's only
    // occurrence of the search term lived in c1's (now-shallow) content, so
    // the walk finds nothing else, but it still returns a normal (empty)
    // partial page instead of erroring.
    let all_history = kio(
        &dir,
        &[
            "search",
            "shallowhistoryfixture",
            "--scope",
            ".",
            "--text",
            "--all-history",
        ],
        None,
    )
    .arg("--json")
    .assert()
    .code(3)
    .get_output()
    .stdout
    .clone();
    let all_history: Value = serde_json::from_slice(&all_history).unwrap();
    assert!(results(&all_history).is_empty());
    assert_eq!(all_history["searched_scopes"][0]["shallow_skipped"], 1);

    // A cursor snapshot that becomes shallow also hard-fails; it cannot serve a
    // partial page from cached HEAD rows.
    let cursor_dir = tempfile::tempdir().unwrap();
    init(&cursor_dir);
    for name in ["a.md", "b.md"] {
        fs::write(
            cursor_dir.path().join(name),
            format!("# {name}\n\nshallowcursorfixture {name}\n"),
        )
        .unwrap();
    }
    let head = index_at(&cursor_dir, "2026-07-10T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    let page1 = json_success(
        &cursor_dir,
        &[
            "search",
            "shallowcursorfixture",
            "--scope",
            ".",
            "--text",
            "--all-history",
            "--limit",
            "1",
        ],
    );
    let cursor = page1["paging"]["next_cursor"].as_str().unwrap();
    discard_commit_tree(&cursor_dir, &head);
    let error = json_failure(
        &cursor_dir,
        &[
            "search",
            "shallowcursorfixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            cursor,
        ],
        1,
    );
    assert_eq!(error["error_code"], "KIO-E-COMMIT-SHALLOW-001");
}

fn write_commit(store: &ObjectStore, commit: &CommitObject) -> String {
    let value = serde_json::to_value(commit).unwrap();
    store.write_json(ObjectKind::Commit, &value).unwrap().0
}

fn synthetic_commit(
    tree: String,
    parents: Vec<String>,
    created_at: &str,
    message: &str,
    tool_lock_hash: String,
    commit_type: CommitType,
) -> CommitObject {
    CommitObject::new(
        tree,
        parents,
        created_at.to_owned(),
        message.to_owned(),
        tool_lock_hash,
        CommitStats {
            files_added: 0,
            files_modified: 0,
            files_deleted: 0,
        },
        commit_type,
    )
    .unwrap()
}

#[test]
fn ct4_timetravel_012_walks_full_parent_dag_and_chooses_canonical_introduction() {
    let dir = tempfile::tempdir().unwrap();
    init(&dir);
    fs::write(
        dir.path().join("base.md"),
        "# Base\n\ncontent present on every branch\n",
    )
    .unwrap();
    let c0 = index_at(&dir, "2026-07-08T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();
    fs::write(
        dir.path().join("old.md"),
        "# Side One\n\nmergefixture side-only binding one\n\n# Side Two\n\nmergefixture side-only binding two\n",
    )
    .unwrap();
    let a1 = index_at(&dir, "2026-07-09T00:00:00Z")["commit_hash"]
        .as_str()
        .unwrap()
        .to_owned();

    let repo = Repository::open(dir.path()).unwrap();
    let c0_object = repo.read_commit(&c0).unwrap();
    let a1_object = repo.read_commit(&a1).unwrap();
    let store = ObjectStore::new(repo.kio_dir());

    // B1 is the merge's first parent and lacks X. A2 is an incomparable sibling
    // of A1 with the same (chunk, old.md) introduction. M drops X from its tree.
    let b1 = write_commit(
        &store,
        &synthetic_commit(
            c0_object.tree.clone(),
            vec![c0.clone()],
            "2026-07-09T01:00:00Z",
            "first-parent without X",
            c0_object.tool_lock_hash.clone(),
            CommitType::Manual,
        ),
    );
    let a2 = write_commit(
        &store,
        &synthetic_commit(
            a1_object.tree.clone(),
            vec![c0.clone()],
            "2026-07-09T02:00:00Z",
            "incomparable side introduction",
            a1_object.tool_lock_hash.clone(),
            CommitType::Manual,
        ),
    );
    let merge = write_commit(
        &store,
        &synthetic_commit(
            c0_object.tree,
            vec![b1, a1.clone(), a2.clone()],
            "2026-07-10T00:00:00Z",
            "merge drops X",
            a1_object.tool_lock_hash,
            CommitType::Merged,
        ),
    );
    fs::write(dir.path().join(".kio/HEAD"), format!("{merge}\n")).unwrap();
    fs::write(
        dir.path().join(".kio/refs/heads/main"),
        format!("{merge}\n"),
    )
    .unwrap();

    // Align the derived HEAD projection with synthetic M. The chunk ledger keeps
    // X, but M's HEAD tree intentionally does not contain it.
    json_success(&dir, &["repair", "--rebuild-db"]);
    let history = search_all_history(&dir, "mergefixture", "100");
    assert_eq!(history["searched_scopes"][0]["snapshot_at"], merge);
    assert!(
        !results(&history).is_empty(),
        "side-parent X must survive: {history}"
    );
    let canonical = std::cmp::min(a1.as_str(), a2.as_str());
    for result in results(&history) {
        assert_eq!(result_path(result), "old.md");
        assert_eq!(result_commit(result), canonical);
    }

    // Replay retains M and the exact incomparable-introduction tie choice.
    let page1 = json_success(
        &dir,
        &[
            "search",
            "mergefixture",
            "--scope",
            ".",
            "--text",
            "--all-history",
            "--limit",
            "1",
        ],
    );
    let cursor = page1["paging"]["next_cursor"]
        .as_str()
        .expect("two-heading side fixture must page");
    let page2 = json_success(
        &dir,
        &[
            "search",
            "mergefixture",
            "--scope",
            ".",
            "--text",
            "--cursor",
            cursor,
            "--limit",
            "100",
        ],
    );
    assert_eq!(page2["searched_scopes"][0]["snapshot_at"], merge);
    assert!(results(&page2)
        .iter()
        .all(|result| result_commit(result) == canonical));
}
