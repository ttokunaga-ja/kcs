use std::fs;

use kio_core::cas::{hash_bytes, ChunkObject, ObjectKind, ObjectStore};
use kio_core::dag::{build_tree, CommitObject, CommitStats, CommitType, TreeEntry};
use kio_core::gc::{GcPlan, GcPlanLimits, GcPlanner};
use kio_core::scope::Repository;
use serde_json::json;
use tempfile::TempDir;

const NOW: i64 = 1_767_225_600; // 2026-01-01T00:00:00Z
const TOOL: &str = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const RAW: &str = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

struct Fixture {
    temp: TempDir,
}

impl Fixture {
    fn new() -> Self {
        let temp = tempfile::tempdir().unwrap();
        Repository::init(temp.path()).unwrap();
        Self { temp }
    }

    fn kio(&self) -> std::path::PathBuf {
        self.temp.path().join(".kio")
    }

    fn canonical_root(&self) -> std::path::PathBuf {
        self.temp.path().canonicalize().unwrap()
    }

    fn tree(&self, name: &str) -> String {
        let tree = build_tree(vec![TreeEntry::raw_file(name, RAW).unwrap()]).unwrap();
        let store = ObjectStore::new(self.kio());
        store
            .write_json(ObjectKind::Tree, &serde_json::to_value(tree).unwrap())
            .unwrap()
            .0
    }

    fn commit(&self, tree: &str, parents: Vec<String>, at: &str, kind: CommitType) -> String {
        let commit = CommitObject::new(
            tree.into(),
            parents,
            at.into(),
            "fixture".into(),
            TOOL.into(),
            CommitStats {
                files_added: 0,
                files_modified: 0,
                files_deleted: 0,
            },
            kind,
        )
        .unwrap();
        let store = ObjectStore::new(self.kio());
        store
            .write_json(ObjectKind::Commit, &serde_json::to_value(commit).unwrap())
            .unwrap()
            .0
    }

    fn purged_commit(&self, tree: &str, parents: Vec<String>, at: &str) -> String {
        let commit = CommitObject::new_purged(
            tree.into(),
            parents,
            at.into(),
            "fixture purge".into(),
            TOOL.into(),
            CommitStats {
                files_added: 0,
                files_modified: 0,
                files_deleted: 0,
            },
            vec![RAW.into()],
        )
        .unwrap();
        ObjectStore::new(self.kio())
            .write_json(ObjectKind::Commit, &serde_json::to_value(commit).unwrap())
            .unwrap()
            .0
    }

    fn head(&self, hash: &str) {
        fs::write(self.kio().join("HEAD"), hash).unwrap();
    }
    fn branch(&self, name: &str, hash: &str) {
        fs::write(self.kio().join("refs/heads").join(name), hash).unwrap();
    }
    fn policy(&self, text: &str) {
        fs::write(self.kio().join("config.toml"), text).unwrap();
    }
    fn plan(&self) -> GcPlan {
        GcPlanner::bind(self.canonical_root())
            .unwrap()
            .plan_at(NOW)
            .unwrap()
    }
}

fn hashes(plan: &GcPlan) -> Vec<String> {
    plan.candidates
        .iter()
        .map(|c| c.commit_hash.clone())
        .collect()
}
fn excluded(plan: &GcPlan, reason: &str) -> u64 {
    plan.exclusions
        .iter()
        .find(|x| x.reason == reason)
        .map_or(0, |x| x.count)
}

#[test]
fn retention_tier_boundaries_keep_each_tier_and_plan_only_expired_auto() {
    let f = Fixture::new();
    f.policy("[gc.auto_retention]\nkeep_last_hours=1\nkeep_hourly_days=1\nkeep_daily_weeks=1\nkeep_weekly_months=1\n");
    let old = f.commit(
        &f.tree("old"),
        vec![],
        "2025-12-02T00:00:00Z",
        CommitType::Auto,
    );
    let weekly = f.commit(
        &f.tree("weekly"),
        vec![old.clone()],
        "2025-12-25T00:00:00Z",
        CommitType::Auto,
    );
    let daily = f.commit(
        &f.tree("daily"),
        vec![weekly],
        "2025-12-31T00:00:00Z",
        CommitType::Auto,
    );
    let hourly = f.commit(
        &f.tree("hourly"),
        vec![daily],
        "2025-12-31T23:00:00Z",
        CommitType::Auto,
    );
    let recent = f.commit(
        &f.tree("recent"),
        vec![hourly],
        "2025-12-31T23:00:01Z",
        CommitType::Auto,
    );
    let head = f.commit(
        &f.tree("head"),
        vec![recent],
        "2026-01-01T00:00:00Z",
        CommitType::Manual,
    );
    f.head(&head);
    let p = f.plan();
    assert_eq!(hashes(&p), vec![old]);
    assert_eq!(excluded(&p, "retained_recent"), 1);
    assert_eq!(excluded(&p, "retained_hourly"), 1);
    assert_eq!(excluded(&p, "retained_daily"), 1);
    assert_eq!(excluded(&p, "retained_weekly"), 1);
}

#[test]
fn retention_policy_rejects_unknown_fields_and_non_monotonic_horizons() {
    let unknown = Fixture::new();
    unknown.policy("[gc.auto_retention]\nkeep_last_hours=24\nkeep_forever=true\n");
    assert_eq!(
        GcPlanner::bind(unknown.canonical_root())
            .unwrap()
            .plan_at(NOW)
            .unwrap_err()
            .error_code(),
        "KIO-E-CONFIG-SCHEMA-001"
    );

    let non_monotonic = Fixture::new();
    non_monotonic.policy("[gc.auto_retention]\nkeep_last_hours=25\nkeep_hourly_days=1\n");
    assert_eq!(
        GcPlanner::bind(non_monotonic.canonical_root())
            .unwrap()
            .plan_at(NOW)
            .unwrap_err()
            .error_code(),
        "KIO-E-CONFIG-SCHEMA-001"
    );
}

#[test]
fn fractional_timestamps_preserve_true_future_and_latest_bucket_member() {
    let f = Fixture::new();
    f.policy("[gc.auto_retention]\nkeep_last_hours=0\nkeep_hourly_days=7\nkeep_daily_weeks=1\nkeep_weekly_months=1\n");
    let older = f.commit(
        &f.tree("fraction-older"),
        vec![],
        "2025-12-31T12:00:00.100Z",
        CommitType::Auto,
    );
    let newer = f.commit(
        &f.tree("fraction-newer"),
        vec![older.clone()],
        "2025-12-31T12:00:00.900Z",
        CommitType::Auto,
    );
    let future = f.commit(
        &f.tree("fraction-future"),
        vec![newer],
        "2026-01-01T00:00:00.100Z",
        CommitType::Auto,
    );
    let head = f.commit(
        &f.tree("head"),
        vec![future],
        "2026-01-01T00:00:01Z",
        CommitType::Manual,
    );
    f.head(&head);

    let plan = f.plan();
    assert_eq!(hashes(&plan), vec![older]);
    assert_eq!(excluded(&plan, "retained_hourly"), 1);
    assert_eq!(excluded(&plan, "future_timestamp"), 1);
}

#[test]
fn head_branch_tag_tips_and_protected_types_are_excluded() {
    let f = Fixture::new();
    f.policy("[gc.auto_retention]\nkeep_last_hours=0\nkeep_hourly_days=0\nkeep_daily_weeks=0\nkeep_weekly_months=0\n");
    let auto = f.commit(
        &f.tree("auto"),
        vec![],
        "2025-01-01T00:00:00Z",
        CommitType::Auto,
    );
    let manual = f.commit(
        &f.tree("manual"),
        vec![auto.clone()],
        "2025-01-02T00:00:00Z",
        CommitType::Manual,
    );
    let imported = f.commit(
        &f.tree("imported"),
        vec![manual],
        "2025-01-03T00:00:00Z",
        CommitType::Imported,
    );
    let merged = f.commit(
        &f.tree("merged"),
        vec![imported],
        "2025-01-04T00:00:00Z",
        CommitType::Merged,
    );
    let purged = f.purged_commit(&f.tree("purged"), vec![merged], "2025-01-05T00:00:00Z");
    let head = f.commit(
        &f.tree("head"),
        vec![purged],
        "2025-01-06T00:00:00Z",
        CommitType::Auto,
    );
    let branch = f.commit(
        &f.tree("branch"),
        vec![],
        "2025-01-07T00:00:00Z",
        CommitType::Auto,
    );
    let tag = f.commit(
        &f.tree("tag"),
        vec![],
        "2025-01-08T00:00:00Z",
        CommitType::Auto,
    );
    f.head(&head);
    f.branch("topic", &branch);
    fs::write(
        f.kio()
            .join("refs/tags-v1")
            .join(format!("tag-{}", &tag[7..])),
        &tag,
    )
    .unwrap();
    let p = f.plan();
    assert_eq!(hashes(&p), vec![auto]);
    assert_eq!(excluded(&p, "ref_tip"), 3);
    assert_eq!(excluded(&p, "protected_commit_type"), 4);
}

#[test]
fn raw_chunk_and_commit_objects_are_never_planned() {
    let f = Fixture::new();
    f.policy("[gc.auto_retention]\nkeep_last_hours=0\nkeep_hourly_days=0\nkeep_daily_weeks=0\nkeep_weekly_months=0\n");
    let store = ObjectStore::new(f.kio());
    let raw_hash = store.write_raw(b"retained raw bytes").unwrap();
    let text = "retained chunk text";
    let chunk = ChunkObject {
        spec_version: 1,
        raw_hash: raw_hash.clone(),
        tool_profile_hash: TOOL.into(),
        gen: 0,
        unit_key: "unit-1".into(),
        unit_content_hash: hash_bytes(text.as_bytes()),
        heading_path: vec!["heading".into()],
        section_id: None,
        byte_start: 0,
        byte_end: text.len() as u64,
        text_hash: hash_bytes(text.as_bytes()),
        text: text.into(),
    };
    let chunk_hash = store.write_chunk(&chunk).unwrap();
    let auto = f.commit(
        &f.tree("auto"),
        vec![],
        "2025-01-01T00:00:00Z",
        CommitType::Auto,
    );
    let head = f.commit(
        &f.tree("head"),
        vec![auto.clone()],
        "2025-01-02T00:00:00Z",
        CommitType::Manual,
    );
    f.head(&head);

    let raw_path = store.object_path(ObjectKind::Raw, &raw_hash).unwrap();
    let chunk_path = store.chunk_path(&chunk_hash).unwrap();
    let commit_path = store.object_path(ObjectKind::Commit, &auto).unwrap();
    let plan = f.plan();

    assert_eq!(plan.object_kinds_planned, vec!["tree"]);
    assert_eq!(hashes(&plan), vec![auto]);
    assert!(raw_path.is_file());
    assert!(chunk_path.is_file());
    assert!(commit_path.is_file());
}

#[test]
fn repaired_retention_is_per_branch_and_shared_trees_are_not_candidates() {
    let f = Fixture::new();
    f.policy("[gc.auto_retention]\nkeep_last_hours=0\nkeep_hourly_days=0\nkeep_daily_weeks=0\nkeep_weekly_months=0\n[gc.derived_retention]\nkeep_repaired_per_branch=1\n");
    let repaired_old = f.commit(
        &f.tree("old"),
        vec![],
        "2025-01-01T00:00:00Z",
        CommitType::Repaired,
    );
    let repaired_new = f.commit(
        &f.tree("new"),
        vec![repaired_old.clone()],
        "2025-01-02T00:00:00Z",
        CommitType::Repaired,
    );
    let shared_tree = f.tree("shared");
    let auto = f.commit(
        &shared_tree,
        vec![repaired_new],
        "2025-01-03T00:00:00Z",
        CommitType::Auto,
    );
    let manual = f.commit(
        &shared_tree,
        vec![auto],
        "2025-01-04T00:00:00Z",
        CommitType::Manual,
    );
    f.head(&manual);
    f.branch("main", &manual);
    let p = f.plan();
    assert_eq!(hashes(&p), vec![repaired_old]);
    assert_eq!(excluded(&p, "retained_repaired"), 1);
    assert_eq!(excluded(&p, "shared_tree_non_shallow"), 1);
    assert_eq!(p.object_kinds_planned, vec!["tree"]);
    assert_eq!(p.candidate_tree_count, 1);
}

#[test]
fn an_existing_shallow_receipt_is_idempotent_and_skips_missing_tree() {
    let f = Fixture::new();
    let tree = f.tree("gone");
    let shallow = f.commit(&tree, vec![], "2025-01-01T00:00:00Z", CommitType::Auto);
    let head = f.commit(
        &f.tree("head"),
        vec![shallow.clone()],
        "2025-01-02T00:00:00Z",
        CommitType::Manual,
    );
    f.head(&head);
    let leaf = &shallow[7..];
    let receipt_dir = f.kio().join("gc/shallowed");
    fs::create_dir_all(&receipt_dir).unwrap();
    fs::write(receipt_dir.join(leaf), serde_json::to_vec(&json!({"commit_hash": shallow, "tree_hash": tree, "gc_policy":"shallow", "shallowed_at":"2026-01-01T00:00:00Z"})).unwrap()).unwrap();
    let path = f
        .kio()
        .join("objects/trees")
        .join(&tree[7..9])
        .join(&tree[9..11])
        .join(&tree[7..]);
    fs::remove_file(path).unwrap();
    let p = f.plan();
    assert!(p.candidates.is_empty());
    assert_eq!(p.stats.trees_verified, 1); // only the live HEAD tree
    assert_eq!(excluded(&p, "already_shallow"), 1);
}

#[test]
fn malformed_receipt_and_missing_unreceipted_tree_fail_safely() {
    let f = Fixture::new();
    let tree = f.tree("missing");
    let auto = f.commit(&tree, vec![], "2025-01-01T00:00:00Z", CommitType::Auto);
    let head = f.commit(
        &f.tree("head"),
        vec![auto],
        "2025-01-02T00:00:00Z",
        CommitType::Manual,
    );
    f.head(&head);
    let tree_path = f
        .kio()
        .join("objects/trees")
        .join(&tree[7..9])
        .join(&tree[9..11])
        .join(&tree[7..]);
    fs::remove_file(tree_path).unwrap();
    assert_eq!(
        GcPlanner::bind(f.canonical_root())
            .unwrap()
            .plan_at(NOW)
            .unwrap_err()
            .error_code(),
        "KIO-E-STORE-CORRUPT-001"
    );

    let f = Fixture::new();
    let receipts = f.kio().join("gc/shallowed");
    fs::create_dir_all(&receipts).unwrap();
    fs::write(receipts.join("a".repeat(64)), b"not json").unwrap();
    assert_eq!(
        GcPlanner::bind(f.canonical_root())
            .unwrap()
            .plan_at(NOW)
            .unwrap_err()
            .error_code(),
        "KIO-E-STORE-CORRUPT-001"
    );

    let f = Fixture::new();
    let tree = f.tree("invalid-receipt-time");
    let commit = f.commit(&tree, vec![], "2025-01-01T00:00:00Z", CommitType::Auto);
    let receipts = f.kio().join("gc/shallowed");
    fs::create_dir_all(&receipts).unwrap();
    fs::write(
        receipts.join(&commit[7..]),
        serde_json::to_vec(&json!({
            "commit_hash": commit,
            "tree_hash": tree,
            "gc_policy": "shallow",
            "shallowed_at": "2026-02-31T00:00:00Z"
        }))
        .unwrap(),
    )
    .unwrap();
    assert_eq!(
        GcPlanner::bind(f.canonical_root())
            .unwrap()
            .plan_at(NOW)
            .unwrap_err()
            .error_code(),
        "KIO-E-STORE-CORRUPT-001"
    );
}

#[cfg(unix)]
#[test]
fn rejects_symlink_hardlink_and_traversal_limits() {
    use std::os::unix::fs::symlink;
    let real = Fixture::new();
    let parent = tempfile::tempdir().unwrap();
    let scope_link = parent.path().join("scope-link");
    symlink(real.temp.path(), &scope_link).unwrap();
    assert!(GcPlanner::bind(&scope_link).is_err());

    let f = Fixture::new();
    let saved = f.kio().join("HEAD.saved");
    fs::rename(f.kio().join("HEAD"), &saved).unwrap();
    symlink("HEAD.saved", f.kio().join("HEAD")).unwrap();
    assert!(GcPlanner::bind(f.canonical_root())
        .unwrap()
        .plan_at(NOW)
        .is_err());

    let f = Fixture::new();
    fs::hard_link(f.kio().join("HEAD"), f.kio().join("HEAD.copy")).unwrap();
    assert!(GcPlanner::bind(f.canonical_root())
        .unwrap()
        .plan_at(NOW)
        .is_err());

    let f = Fixture::new();
    let auto = f.commit(
        &f.tree("depth"),
        vec![],
        "2025-01-01T00:00:00Z",
        CommitType::Auto,
    );
    f.head(&auto);
    let err = GcPlanner::bind(f.canonical_root())
        .unwrap()
        .with_limits(GcPlanLimits {
            max_depth: 3,
            ..GcPlanLimits::default()
        })
        .plan_at(NOW)
        .unwrap_err();
    assert_eq!(err.error_code(), "KIO-E-GC-PLAN-LIMIT-001");

    let f = Fixture::new();
    let err = GcPlanner::bind(f.canonical_root())
        .unwrap()
        .with_limits(GcPlanLimits {
            max_dir_entries: 0,
            ..GcPlanLimits::default()
        })
        .plan_at(NOW)
        .unwrap_err();
    assert_eq!(err.error_code(), "KIO-E-GC-PLAN-LIMIT-001");

    let f = Fixture::new();
    let err = GcPlanner::bind(f.canonical_root())
        .unwrap()
        .with_limits(GcPlanLimits {
            max_verified_bytes: 0,
            ..GcPlanLimits::default()
        })
        .plan_at(NOW)
        .unwrap_err();
    assert_eq!(err.error_code(), "KIO-E-GC-PLAN-LIMIT-001");

    let f = Fixture::new();
    let auto = f.commit(
        &f.tree("graph"),
        vec![],
        "2025-01-01T00:00:00Z",
        CommitType::Auto,
    );
    f.head(&auto);
    let err = GcPlanner::bind(f.canonical_root())
        .unwrap()
        .with_limits(GcPlanLimits {
            max_graph_steps: 0,
            ..GcPlanLimits::default()
        })
        .plan_at(NOW)
        .unwrap_err();
    assert_eq!(err.error_code(), "KIO-E-GC-PLAN-LIMIT-001");
}

#[cfg(unix)]
#[test]
fn retained_scope_binding_rejects_kio_path_replacement() {
    let f = Fixture::new();
    let planner = GcPlanner::bind(f.canonical_root()).unwrap();
    fs::rename(f.kio(), f.temp.path().join(".kio.replaced")).unwrap();
    fs::create_dir(f.kio()).unwrap();
    let error = planner.plan_at(NOW).unwrap_err();
    assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
}

#[test]
fn plan_serialization_is_deterministic() {
    let f = Fixture::new();
    let auto = f.commit(
        &f.tree("auto"),
        vec![],
        "2025-01-01T00:00:00Z",
        CommitType::Auto,
    );
    let head = f.commit(
        &f.tree("head"),
        vec![auto],
        "2025-01-02T00:00:00Z",
        CommitType::Manual,
    );
    f.head(&head);
    let planner = GcPlanner::bind(f.canonical_root()).unwrap();
    assert_eq!(
        serde_json::to_vec(&planner.plan_at(NOW).unwrap()).unwrap(),
        serde_json::to_vec(&planner.plan_at(NOW).unwrap()).unwrap()
    );
}
