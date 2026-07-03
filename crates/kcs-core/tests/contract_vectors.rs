use std::fs;

use kcs_core::cas::{
    canonical_json_bytes, fanout_path, hash_bytes, hash_json, ObjectKind, ObjectStore,
};
use kcs_core::dag::{
    build_tree, commit_hash, gc_policy, protected, CommitObject, CommitStats, CommitType, GcPolicy,
    NormalizeRef, TreeEntry,
};
use kcs_core::scope::Repository;
use serde_json::json;

const RAW_EMPTY: &str = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
const RAW_JA: &str = "sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59";
const RAW_NOTES: &str = "sha256:365d0b84ae63c2afc293dedd2b00bdf0dc8d6ef70c9297d90f9e5682ab0d72ee";
const RAW_REPORT: &str = "sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a";
const TOOL_PROFILE: &str =
    "sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0";
const TOOL_LOCK: &str = "sha256:8a32a740871b1dd9db1bda186dce07e8e6c60d2cd316f21683ea2bd857c16ffb";
const PARENT: &str = "sha256:30fa71e5c11a90a28c8c0895382e8f45df431047fcc699afed45ee316cfbf65a";
const TREE_HASH: &str = "sha256:eca8de0abaf2a27a1ea57feff4f44385bcfb3485274e73ddfa7c47144f383e1e";
const COMMIT_HASH: &str = "sha256:6b9884a55265cb9dab75ecc79e1e90de145aeae91e3bb5b43538e58fe848eac6";

#[test]
fn ct_hash_001_002_raw_hash_vectors() {
    assert_eq!(hash_bytes(b""), RAW_EMPTY);
    assert_eq!(hash_bytes("認証仕様\n".as_bytes()), RAW_JA);
}

#[test]
fn ct_hash_003_tree_jcs_vector() {
    let tree = vector_tree();
    let bytes = canonical_json_bytes(&serde_json::to_value(&tree).unwrap()).unwrap();

    assert_eq!(String::from_utf8(bytes.clone()).unwrap(), "{\"entries\":[{\"normalize\":{\"gen\":0,\"tool_profile_hash\":\"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0\"},\"path\":\"notes.md\",\"raw_hash\":\"sha256:365d0b84ae63c2afc293dedd2b00bdf0dc8d6ef70c9297d90f9e5682ab0d72ee\",\"type\":\"file\"},{\"normalize\":{\"gen\":0,\"tool_profile_hash\":\"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0\"},\"path\":\"report.pdf\",\"raw_hash\":\"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a\",\"type\":\"file\"}],\"object_type\":\"tree\"}");
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
    assert_eq!(String::from_utf8(bytes.clone()).unwrap(), "{\"commit_type\":\"manual\",\"created_at\":\"2026-04-29T12:00:00Z\",\"message\":\"snapshot after indexing docs\",\"object_type\":\"commit\",\"parents\":[\"sha256:30fa71e5c11a90a28c8c0895382e8f45df431047fcc699afed45ee316cfbf65a\"],\"stats\":{\"files_added\":12,\"files_deleted\":1,\"files_modified\":3},\"tool_lock_hash\":\"sha256:8a32a740871b1dd9db1bda186dce07e8e6c60d2cd316f21683ea2bd857c16ffb\",\"tree\":\"sha256:eca8de0abaf2a27a1ea57feff4f44385bcfb3485274e73ddfa7c47144f383e1e\"}");
    assert_eq!(hash_bytes(&bytes), COMMIT_HASH);
}

#[test]
fn ct_hash_005_fanout_path_uses_prefixed_leaf() {
    let path = fanout_path("objects/commits", COMMIT_HASH).unwrap();
    assert_eq!(
        path.to_string_lossy(),
        "objects/commits/6b/98/sha256:6b9884a55265cb9dab75ecc79e1e90de145aeae91e3bb5b43538e58fe848eac6"
    );
}

#[test]
fn ct_hash_006_007_008_hash_shape_round_trip_and_key_order() {
    assert!(kcs_core::cas::is_hash(RAW_EMPTY));
    assert!(!kcs_core::cas::is_hash("sha256:E3B0"));
    assert!(!kcs_core::cas::is_hash("e3b0"));

    let a = json!({"object_type":"tree","entries":[{"path":"a.pdf","type":"file","raw_hash":RAW_EMPTY}]});
    let b = json!({"entries":[{"raw_hash":RAW_EMPTY,"type":"file","path":"a.pdf"}],"object_type":"tree"});
    assert_eq!(hash_json(&a).unwrap(), hash_json(&b).unwrap());

    let temp = tempfile::tempdir().unwrap();
    let repo = Repository::init(temp.path()).unwrap();
    let store = ObjectStore::new(repo.kcs_dir());
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
    assert_eq!(duplicate.unwrap_err().error_code(), "KCS-E-STORE-PATH-001");

    let nested = TreeEntry::raw_file("sub/report.pdf", RAW_REPORT);
    assert_eq!(nested.unwrap_err().error_code(), "KCS-E-STORE-PATH-001");
}

#[test]
fn ct_tree_004_gen_missing_defaults_to_zero() {
    let entry: TreeEntry = serde_json::from_value(json!({
        "path": "notes.md",
        "type": "file",
        "raw_hash": RAW_NOTES,
        "normalize": { "tool_profile_hash": TOOL_PROFILE }
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
        "sha256:c0cc8b407ba5e9a8e1769b3919b1c804a1853ad3ab34c9674eb56f81f59e6059"
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

    let head = fs::read_to_string(repo.kcs_dir().join("HEAD")).unwrap();
    let main = fs::read_to_string(repo.kcs_dir().join("refs/heads/main")).unwrap();
    assert_eq!(head, second.commit_hash.clone().unwrap());
    assert_eq!(main, second.commit_hash.clone().unwrap());

    let noop = repo
        .snapshot(Some("same"), Some("2026-04-29T12:00:02Z"))
        .unwrap();
    assert!(noop.noop);
    assert_eq!(
        fs::read_to_string(repo.kcs_dir().join("HEAD")).unwrap(),
        second.commit_hash.unwrap()
    );
}

fn vector_tree() -> kcs_core::dag::TreeObject {
    build_tree(vec![
        TreeEntry {
            path: "notes.md".to_owned(),
            entry_type: "file".to_owned(),
            raw_hash: RAW_NOTES.to_owned(),
            normalize: Some(NormalizeRef {
                tool_profile_hash: TOOL_PROFILE.to_owned(),
                gen: 0,
            }),
        },
        TreeEntry {
            path: "report.pdf".to_owned(),
            entry_type: "file".to_owned(),
            raw_hash: RAW_REPORT.to_owned(),
            normalize: Some(NormalizeRef {
                tool_profile_hash: TOOL_PROFILE.to_owned(),
                gen: 0,
            }),
        },
    ])
    .unwrap()
}
