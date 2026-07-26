use std::fs;

use kio_core::cas::{
    canonical_json_bytes, fanout_path, hash_bytes, hash_json, ObjectKind, ObjectStore,
};
use kio_core::dag::{
    build_tree, commit_hash, gc_policy, protected, CommitObject, CommitStats, CommitType, GcPolicy,
    NormalizeRef, TreeEntry,
};
use kio_core::scope::Repository;
use serde_json::json;

const RAW_EMPTY: &str = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
const RAW_JA: &str = "sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59";
const RAW_NOTES: &str = "sha256:365d0b84ae63c2afc293dedd2b00bdf0dc8d6ef70c9297d90f9e5682ab0d72ee";
const RAW_REPORT: &str = "sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a";
const TOOL_PROFILE: &str =
    "sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0";
/// `sha256("manifest")` — a fixed stand-in for a normalized-instance
/// manifest's content hash. `normalize.manifest_hash` is required (PB04), so
/// the canonical tree vector carries one.
const MANIFEST_HASH: &str =
    "sha256:05b3abf2579a5eb66403cd78be557fd860633a1fe2103c7642030defe32c657f";
const TOOL_LOCK: &str = "sha256:8a32a740871b1dd9db1bda186dce07e8e6c60d2cd316f21683ea2bd857c16ffb";
const PARENT: &str = "sha256:30fa71e5c11a90a28c8c0895382e8f45df431047fcc699afed45ee316cfbf65a";
const TREE_HASH: &str = "sha256:484102953bc67a38fed8985744899fbde1d29d84623ad6ad6c5e363b9688a11a";
const COMMIT_HASH: &str = "sha256:ccb5e32bb3500546b148533ecb9d41d28862e5c481ee6c7c44f1246b4d969d17";

#[test]
fn ct_hash_001_002_raw_hash_vectors() {
    assert_eq!(hash_bytes(b""), RAW_EMPTY);
    assert_eq!(hash_bytes("認証仕様\n".as_bytes()), RAW_JA);
}

#[test]
fn ct_hash_003_tree_jcs_vector() {
    let tree = vector_tree();
    let bytes = canonical_json_bytes(&serde_json::to_value(&tree).unwrap()).unwrap();

    assert_eq!(String::from_utf8(bytes.clone()).unwrap(), "{\"entries\":[{\"normalize\":{\"gen\":0,\"manifest_hash\":\"sha256:05b3abf2579a5eb66403cd78be557fd860633a1fe2103c7642030defe32c657f\",\"tool_profile_hash\":\"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0\"},\"path\":\"notes.md\",\"raw_hash\":\"sha256:365d0b84ae63c2afc293dedd2b00bdf0dc8d6ef70c9297d90f9e5682ab0d72ee\",\"type\":\"file\"},{\"normalize\":{\"gen\":0,\"manifest_hash\":\"sha256:05b3abf2579a5eb66403cd78be557fd860633a1fe2103c7642030defe32c657f\",\"tool_profile_hash\":\"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0\"},\"path\":\"report.pdf\",\"raw_hash\":\"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a\",\"type\":\"file\"}],\"object_type\":\"tree\"}");
    assert_eq!(hash_bytes(&bytes), TREE_HASH);
}

#[test]
fn ct_hash_004_commit_jcs_vector() {
    let commit = CommitObject::new(
        TREE_HASH.to_owned(),
        vec![PARENT.to_owned()],
        "2026-04-29T12:00:00Z".to_owned(),
        "snapshot after indexing docs".to_owned(),
        TOOL_LOCK.to_owned(),
        CommitStats {
            files_added: 12,
            files_modified: 3,
            files_deleted: 1,
        },
        CommitType::Manual,
    )
    .unwrap();

    let bytes = canonical_json_bytes(&serde_json::to_value(&commit).unwrap()).unwrap();
    assert_eq!(String::from_utf8(bytes.clone()).unwrap(), "{\"commit_type\":\"manual\",\"created_at\":\"2026-04-29T12:00:00Z\",\"message\":\"snapshot after indexing docs\",\"object_type\":\"commit\",\"parents\":[\"sha256:30fa71e5c11a90a28c8c0895382e8f45df431047fcc699afed45ee316cfbf65a\"],\"stats\":{\"files_added\":12,\"files_deleted\":1,\"files_modified\":3},\"tool_lock_hash\":\"sha256:8a32a740871b1dd9db1bda186dce07e8e6c60d2cd316f21683ea2bd857c16ffb\",\"tree\":\"sha256:484102953bc67a38fed8985744899fbde1d29d84623ad6ad6c5e363b9688a11a\"}");
    assert_eq!(hash_bytes(&bytes), COMMIT_HASH);
}

#[test]
fn ct_hash_005_fanout_path_uses_portable_digest_leaf() {
    let path = fanout_path("objects/commits", COMMIT_HASH).unwrap();
    assert_eq!(
        path,
        std::path::Path::new("objects")
            .join("commits")
            .join("cc")
            .join("b5")
            .join("ccb5e32bb3500546b148533ecb9d41d28862e5c481ee6c7c44f1246b4d969d17")
    );
}

#[test]
fn ct_hash_006_007_008_hash_shape_round_trip_and_key_order() {
    assert!(kio_core::cas::is_hash(RAW_EMPTY));
    assert!(!kio_core::cas::is_hash("sha256:E3B0"));
    assert!(!kio_core::cas::is_hash("e3b0"));

    let a = json!({"object_type":"tree","entries":[{"path":"a.pdf","type":"file","raw_hash":RAW_EMPTY}]});
    let b = json!({"entries":[{"raw_hash":RAW_EMPTY,"type":"file","path":"a.pdf"}],"object_type":"tree"});
    assert_eq!(hash_json(&a).unwrap(), hash_json(&b).unwrap());

    let temp = tempfile::tempdir().unwrap();
    let repo = Repository::init(temp.path()).unwrap();
    let store = ObjectStore::new(repo.kio_dir());
    let (stored_hash, stored_bytes) = store.write_json(ObjectKind::Tree, &a).unwrap();
    let read = store.read_by_hash(&stored_hash).unwrap();
    assert_eq!(hash_bytes(&read.bytes), stored_hash);
    assert_eq!(read.bytes, stored_bytes);

    let stored = String::from_utf8(read.bytes).unwrap();
    assert!(!stored.contains("tree_hash"));
    assert!(!stored.contains("tree_id"));
    assert!(!stored.contains("commit_hash"));
    assert!(!stored.contains("commit_id"));
}

#[test]
fn ct_tree_001_002_003_sort_duplicate_and_path_validation() {
    let tree = build_tree(vec![
        TreeEntry::raw_file("report.pdf", RAW_REPORT).unwrap(),
        TreeEntry::raw_file("notes.md", RAW_NOTES).unwrap(),
    ])
    .unwrap();
    assert_eq!(tree.entries[0].path, "notes.md");
    assert_eq!(tree.entries[1].path, "report.pdf");

    let duplicate = build_tree(vec![
        TreeEntry::raw_file("notes.md", RAW_NOTES).unwrap(),
        TreeEntry::raw_file("notes.md", RAW_REPORT).unwrap(),
    ]);
    // CT-TREE-002 mandates rejection but not a specific code; duplicate paths
    // use KIO-E-STORE-DUP-001, kept distinct from the `/`-in-path violation.
    assert_eq!(duplicate.unwrap_err().error_code(), "KIO-E-STORE-DUP-001");

    // CT-TREE-003 mandates KIO-E-STORE-PATH-001 for a `/`-containing path.
    let nested = TreeEntry::raw_file("sub/report.pdf", RAW_REPORT);
    assert_eq!(nested.unwrap_err().error_code(), "KIO-E-STORE-PATH-001");
}

#[test]
fn ct_tree_004_gen_missing_defaults_to_zero() {
    let entry: TreeEntry = serde_json::from_value(json!({
        "path": "notes.md",
        "type": "file",
        "raw_hash": RAW_NOTES,
        "normalize": { "tool_profile_hash": TOOL_PROFILE, "manifest_hash": MANIFEST_HASH }
    }))
    .unwrap();

    assert_eq!(entry.normalize.unwrap().gen, 0);
}

#[test]
fn ct_tree_empty_vector_and_step1_entries_omit_normalize() {
    let tree = build_tree(Vec::new()).unwrap();
    assert_eq!(
        hash_json(&serde_json::to_value(&tree).unwrap()).unwrap(),
        "sha256:849dc4fa25bc1a7b09b74dba30c0bb85224fb8f659c3b2b177b7189b0327a967"
    );

    let raw_tree = build_tree(vec![TreeEntry::raw_file("notes.md", RAW_NOTES).unwrap()]).unwrap();
    let bytes = canonical_json_bytes(&serde_json::to_value(&raw_tree).unwrap()).unwrap();
    assert!(!String::from_utf8(bytes).unwrap().contains("normalize"));
}

#[test]
fn ct_commit_001_002_and_gc_mappings() {
    for value in [
        "manual", "auto", "imported", "migrated", "repaired", "merged", "purged",
    ] {
        assert!(value.parse::<CommitType>().is_ok());
    }
    assert!("snapshot".parse::<CommitType>().is_err());

    assert_eq!(gc_policy(CommitType::Auto), GcPolicy::Shallow);
    assert_eq!(gc_policy(CommitType::Migrated), GcPolicy::Shallow);
    assert_eq!(gc_policy(CommitType::Repaired), GcPolicy::Shallow);
    assert_eq!(gc_policy(CommitType::Manual), GcPolicy::None);
    assert_eq!(gc_policy(CommitType::Imported), GcPolicy::None);
    assert_eq!(gc_policy(CommitType::Merged), GcPolicy::None);
    assert_eq!(gc_policy(CommitType::Purged), GcPolicy::None);
    assert!(![
        CommitType::Manual,
        CommitType::Auto,
        CommitType::Imported,
        CommitType::Migrated,
        CommitType::Repaired,
        CommitType::Merged,
        CommitType::Purged,
    ]
    .into_iter()
    .any(|ty| gc_policy(ty) == GcPolicy::Full));

    assert!(protected(CommitType::Manual));
    assert!(!protected(CommitType::Auto));
}

#[test]
fn ct_commit_004_root_commit_vector() {
    let commit = CommitObject::new(
        TREE_HASH.to_owned(),
        Vec::new(),
        "2026-04-29T12:00:00Z".to_owned(),
        "initial snapshot".to_owned(),
        TOOL_LOCK.to_owned(),
        CommitStats {
            files_added: 2,
            files_modified: 0,
            files_deleted: 0,
        },
        CommitType::Manual,
    )
    .unwrap();

    assert!(commit.parents.is_empty());
    assert_eq!(
        commit_hash(&commit).unwrap(),
        "sha256:ab368388a7daf62d5846ecaab20d0e1d60fd1303a50d6633993d6eec4276a07b"
    );
}

#[test]
fn ct_scope_001_snapshot_scans_direct_children_only() {
    let temp = tempfile::tempdir().unwrap();
    let repo = Repository::init(temp.path()).unwrap();
    fs::write(temp.path().join("a.pdf"), b"a").unwrap();
    fs::create_dir(temp.path().join("sub")).unwrap();
    fs::write(temp.path().join("sub").join("b.pdf"), b"b").unwrap();

    let tree = repo.build_working_tree(false).unwrap().tree;
    assert_eq!(tree.entries.len(), 1);
    assert_eq!(tree.entries[0].path, "a.pdf");
}

#[test]
fn ct_commit_003_005_007_snapshot_parent_refs_and_noop() {
    let temp = tempfile::tempdir().unwrap();
    let repo = Repository::init(temp.path()).unwrap();
    fs::write(temp.path().join("a.pdf"), b"one").unwrap();

    let first = repo
        .snapshot(Some("first"), Some("2026-04-29T12:00:00Z"))
        .unwrap();
    fs::write(temp.path().join("a.pdf"), b"two").unwrap();
    let second = repo
        .snapshot(Some("second"), Some("2026-04-29T12:00:01Z"))
        .unwrap();
    assert_eq!(
        second.commit.as_ref().unwrap().parents[0],
        first.commit_hash.unwrap()
    );

    let head = fs::read_to_string(repo.kio_dir().join("HEAD")).unwrap();
    let main = fs::read_to_string(repo.kio_dir().join("refs/heads/main")).unwrap();
    assert_eq!(head, second.commit_hash.clone().unwrap());
    assert_eq!(main, second.commit_hash.clone().unwrap());

    let noop = repo
        .snapshot(Some("same"), Some("2026-04-29T12:00:02Z"))
        .unwrap();
    assert!(noop.noop);
    assert_eq!(
        fs::read_to_string(repo.kio_dir().join("HEAD")).unwrap(),
        second.commit_hash.unwrap()
    );
}

#[test]
fn s2_manifest_retains_deleted_rows_and_recovers() {
    let temp = tempfile::tempdir().unwrap();
    let repo = Repository::init(temp.path()).unwrap();
    fs::write(temp.path().join("a.pdf"), b"one").unwrap();
    fs::write(temp.path().join("b.pdf"), b"two").unwrap();
    repo.snapshot(Some("first"), Some("2026-04-29T12:00:00Z"))
        .unwrap();

    // Deleting b.pdf keeps its manifest row as deleted with its last raw_hash.
    fs::remove_file(temp.path().join("b.pdf")).unwrap();
    repo.snapshot(Some("second"), Some("2026-04-29T12:00:01Z"))
        .unwrap();
    let files = manifest_files(repo.kio_dir());
    let b = find_file(&files, "b.pdf");
    assert_eq!(b["status"], "deleted");
    assert_eq!(b["raw_hash"].as_str().unwrap(), hash_bytes(b"two"));
    assert_eq!(find_file(&files, "a.pdf")["status"], "unchanged");

    // Recreating b.pdf with new content recovers the row from deleted -> modified.
    fs::write(temp.path().join("b.pdf"), b"three").unwrap();
    repo.snapshot(Some("third"), Some("2026-04-29T12:00:02Z"))
        .unwrap();
    let files = manifest_files(repo.kio_dir());
    let b = find_file(&files, "b.pdf");
    assert_eq!(b["status"], "modified");
    assert_eq!(b["raw_hash"].as_str().unwrap(), hash_bytes(b"three"));
}

#[test]
fn s2_stale_manifest_cannot_lose_a_deletion() {
    // WS1d cross-review: the previous state must come from the prior HEAD tree,
    // not the manifest. A stale manifest that lost b.pdf's live row must not
    // prevent the deleted row (with the tree's raw_hash) from being recorded.
    let temp = tempfile::tempdir().unwrap();
    let repo = Repository::init(temp.path()).unwrap();
    fs::write(temp.path().join("a.pdf"), b"one").unwrap();
    fs::write(temp.path().join("b.pdf"), b"two").unwrap();
    repo.snapshot(Some("first"), Some("2026-04-29T12:00:00Z"))
        .unwrap();

    // Simulate a stale (schema-valid) manifest missing b.pdf's row entirely.
    let stale = serde_json::json!({
        "schema_version": 1,
        "files": [
            { "path": "a.pdf", "raw_hash": hash_bytes(b"one"), "status": "unchanged" }
        ],
        "updated_at": "2026-04-29T12:00:00Z",
    });
    fs::write(
        repo.kio_dir().join("manifest.json"),
        serde_json::to_vec_pretty(&stale).unwrap(),
    )
    .unwrap();

    fs::remove_file(temp.path().join("b.pdf")).unwrap();
    repo.snapshot(Some("second"), Some("2026-04-29T12:00:01Z"))
        .unwrap();
    let files = manifest_files(repo.kio_dir());
    let b = find_file(&files, "b.pdf");
    assert_eq!(b["status"], "deleted");
    assert_eq!(b["raw_hash"].as_str().unwrap(), hash_bytes(b"two"));
}

fn manifest_files(kio_dir: &std::path::Path) -> Vec<serde_json::Value> {
    let value: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(kio_dir.join("manifest.json")).unwrap()).unwrap();
    value["files"].as_array().unwrap().clone()
}

fn find_file<'a>(files: &'a [serde_json::Value], path: &str) -> &'a serde_json::Value {
    files
        .iter()
        .find(|file| file["path"] == path)
        .unwrap_or_else(|| panic!("manifest missing {path}"))
}

fn vector_tree() -> kio_core::dag::TreeObject {
    build_tree(vec![
        TreeEntry {
            path: "notes.md".to_owned(),
            entry_type: "file".to_owned(),
            raw_hash: RAW_NOTES.to_owned(),
            normalize: Some(NormalizeRef {
                tool_profile_hash: TOOL_PROFILE.to_owned(),
                gen: 0,
                manifest_hash: MANIFEST_HASH.to_owned(),
            }),
        },
        TreeEntry {
            path: "report.pdf".to_owned(),
            entry_type: "file".to_owned(),
            raw_hash: RAW_REPORT.to_owned(),
            normalize: Some(NormalizeRef {
                tool_profile_hash: TOOL_PROFILE.to_owned(),
                gen: 0,
                manifest_hash: MANIFEST_HASH.to_owned(),
            }),
        },
    ])
    .unwrap()
}
