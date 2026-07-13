//! Bounded, CAS-backed snapshot-history traversal.
//!
//! This module deliberately reads commit and tree objects from the CAS. Mutable
//! manifests, SQLite projections, and other acceleration data are never accepted
//! as history truth.

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use serde_json::json;

use crate::cas::{ObjectKind, ObjectStore, StoredObject};
use crate::dag::{
    CommitObject, NormalizeRef, TreeEntry, TreeObject, MAX_COMMIT_PARENTS, MAX_TREE_ENTRIES,
};
use crate::error::{KcsError, Result};
use crate::ExitCode;

pub const DEFAULT_MAX_HISTORY_COMMITS: u64 = 100_000;
pub const DEFAULT_MAX_HISTORY_TREE_ENTRIES: u64 = 10_000_000;
pub const DEFAULT_MAX_HISTORY_VERIFIED_BYTES: u64 = 4 * 1024 * 1024 * 1024;

/// Aggregate limits for one history walk. A reader applies a fresh set of
/// counters to every all-parent or first-parent invocation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HistoryLimits {
    pub max_commits: u64,
    pub max_tree_entries: u64,
    pub max_verified_bytes: u64,
}

impl HistoryLimits {
    #[must_use]
    pub const fn new(max_commits: u64, max_tree_entries: u64, max_verified_bytes: u64) -> Self {
        Self {
            max_commits,
            max_tree_entries,
            max_verified_bytes,
        }
    }
}

impl Default for HistoryLimits {
    fn default() -> Self {
        Self::new(
            DEFAULT_MAX_HISTORY_COMMITS,
            DEFAULT_MAX_HISTORY_TREE_ENTRIES,
            DEFAULT_MAX_HISTORY_VERIFIED_BYTES,
        )
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct HistoryStats {
    pub commits: u64,
    pub tree_entries: u64,
    pub verified_bytes: u64,
}

/// The immutable tree identity used to join a persisted tree entry to indexed
/// chunks. `normalize = None` is an exact value and is never supplemented from a
/// later commit or mutable cache.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct TreeBinding {
    pub path: String,
    pub raw_hash: String,
    pub normalize: Option<NormalizeRef>,
}

impl From<&TreeEntry> for TreeBinding {
    fn from(entry: &TreeEntry) -> Self {
        Self {
            path: entry.path.clone(),
            raw_hash: entry.raw_hash.clone(),
            normalize: entry.normalize.clone(),
        }
    }
}

/// One exact binding appearance, including the commit and tree that attest it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HistoryBinding {
    pub commit_hash: String,
    pub tree_hash: String,
    pub binding: TreeBinding,
}

#[derive(Debug, Clone)]
pub struct HistoryNode {
    pub commit_hash: String,
    pub commit: CommitObject,
    pub tree: TreeObject,
    pub commit_bytes: u64,
    pub tree_bytes: u64,
}

impl HistoryNode {
    fn binding(&self, entry: &TreeEntry) -> HistoryBinding {
        HistoryBinding {
            commit_hash: self.commit_hash.clone(),
            tree_hash: self.commit.tree.clone(),
            binding: TreeBinding::from(entry),
        }
    }

    fn entry(&self, path: &str) -> Option<&TreeEntry> {
        self.tree
            .entries
            .binary_search_by(|entry| entry.path.as_bytes().cmp(path.as_bytes()))
            .ok()
            .map(|index| &self.tree.entries[index])
    }

    fn contains_binding(&self, binding: &TreeBinding) -> bool {
        self.entry(&binding.path).map(TreeBinding::from).as_ref() == Some(binding)
    }
}

/// A complete all-parent graph reachable from one snapshot commit.
#[derive(Debug, Clone)]
pub struct HistoryGraph {
    start_commit: String,
    nodes: BTreeMap<String, HistoryNode>,
    visit_order: Vec<String>,
    stats: HistoryStats,
}

impl HistoryGraph {
    #[must_use]
    pub fn start_commit(&self) -> &str {
        &self.start_commit
    }

    #[must_use]
    pub const fn stats(&self) -> HistoryStats {
        self.stats
    }

    #[must_use]
    pub fn node(&self, commit_hash: &str) -> Option<&HistoryNode> {
        self.nodes.get(commit_hash)
    }

    /// Deterministic traversal order: each commit's persisted parent order is
    /// honored depth-first, and every reachable commit appears exactly once.
    pub fn nodes_in_visit_order(&self) -> impl Iterator<Item = &HistoryNode> {
        self.visit_order
            .iter()
            .filter_map(|hash| self.nodes.get(hash))
    }

    /// Every binding appearance, sorted by exact identity and then commit hash.
    #[must_use]
    pub fn bindings(&self) -> Vec<HistoryBinding> {
        let mut bindings = self
            .nodes
            .values()
            .flat_map(|node| {
                node.tree
                    .entries
                    .iter()
                    .map(move |entry| node.binding(entry))
            })
            .collect::<Vec<_>>();
        sort_bindings(&mut bindings);
        bindings
    }

    /// Test reachability within the complete graph. A commit is its own ancestor.
    #[must_use]
    pub fn is_ancestor(&self, ancestor: &str, descendant: &str) -> bool {
        if !self.nodes.contains_key(ancestor) || !self.nodes.contains_key(descendant) {
            return false;
        }
        let mut pending = vec![descendant];
        let mut visited = BTreeSet::new();
        while let Some(hash) = pending.pop() {
            if hash == ancestor {
                return true;
            }
            if !visited.insert(hash) {
                continue;
            }
            if let Some(node) = self.nodes.get(hash) {
                for parent in node.commit.parents.iter().rev() {
                    pending.push(parent);
                }
            }
        }
        false
    }

    /// Commits where `binding` is present and absent from every parent.
    #[must_use]
    pub fn introduction_candidates(&self, binding: &TreeBinding) -> Vec<HistoryBinding> {
        let mut candidates = self
            .nodes
            .values()
            .filter(|node| {
                node.contains_binding(binding)
                    && node.commit.parents.iter().all(|parent| {
                        self.nodes
                            .get(parent)
                            .is_none_or(|parent_node| !parent_node.contains_binding(binding))
                    })
            })
            .filter_map(|node| node.entry(&binding.path).map(|entry| node.binding(entry)))
            .collect::<Vec<_>>();
        candidates.sort_by(|a, b| a.commit_hash.as_bytes().cmp(b.commit_hash.as_bytes()));
        candidates
    }

    /// Introduction candidates with every descendant re-introduction removed.
    /// The result is sorted by full commit hash, giving the frozen incomparable
    /// introduction tie order.
    #[must_use]
    pub fn ancestor_most_introductions(&self, binding: &TreeBinding) -> Vec<HistoryBinding> {
        let candidates = self.introduction_candidates(binding);
        let candidate_hashes = candidates
            .iter()
            .map(|candidate| candidate.commit_hash.clone())
            .collect::<BTreeSet<_>>();
        let mut remaining_parents = self
            .nodes
            .iter()
            .map(|(hash, node)| (hash.clone(), node.commit.parents.len()))
            .collect::<BTreeMap<_, _>>();
        let mut children = BTreeMap::<&str, Vec<&str>>::new();
        for (child_hash, node) in &self.nodes {
            for parent in &node.commit.parents {
                children
                    .entry(parent)
                    .or_default()
                    .push(child_hash.as_str());
            }
        }
        let mut ready = remaining_parents
            .iter()
            .filter_map(|(hash, count)| (*count == 0).then_some(hash.clone()))
            .collect::<BTreeSet<_>>();
        let mut has_candidate_ancestor = BTreeSet::new();
        let mut retained = BTreeSet::new();
        while let Some(hash) = ready.pop_first() {
            let inherited = has_candidate_ancestor.contains(&hash);
            let is_candidate = candidate_hashes.contains(&hash);
            if is_candidate && !inherited {
                retained.insert(hash.clone());
            }
            let lineage_contains_candidate = inherited || is_candidate;
            if let Some(node_children) = children.get(hash.as_str()) {
                for child in node_children {
                    if lineage_contains_candidate {
                        has_candidate_ancestor.insert((*child).to_owned());
                    }
                    let count = remaining_parents
                        .get_mut(*child)
                        .expect("child was collected from graph nodes");
                    *count -= 1;
                    if *count == 0 {
                        ready.insert((*child).to_owned());
                    }
                }
            }
        }
        candidates
            .into_iter()
            .filter(|candidate| retained.contains(&candidate.commit_hash))
            .collect()
    }

    /// Canonical introduction: the sole ancestor-most introduction, or the
    /// bytewise-smallest full hash when multiple candidates are incomparable.
    #[must_use]
    pub fn canonical_introduction(&self, binding: &TreeBinding) -> Option<HistoryBinding> {
        self.ancestor_most_introductions(binding).into_iter().next()
    }

    /// Distinct snapshot paths carrying `raw_hash`, in UTF-8 byte order.
    #[must_use]
    pub fn snapshot_paths_for_raw(&self, raw_hash: &str) -> Vec<String> {
        self.nodes
            .get(&self.start_commit)
            .into_iter()
            .flat_map(|node| node.tree.entries.iter())
            .filter(|entry| entry.raw_hash == raw_hash)
            .map(|entry| entry.path.clone())
            .collect()
    }
}

/// A complete newest-first first-parent ancestry.
#[derive(Debug, Clone)]
pub struct FirstParentHistory {
    start_commit: String,
    nodes: BTreeMap<String, HistoryNode>,
    newest_first: Vec<String>,
    stats: HistoryStats,
}

impl FirstParentHistory {
    #[must_use]
    pub fn start_commit(&self) -> &str {
        &self.start_commit
    }

    #[must_use]
    pub const fn stats(&self) -> HistoryStats {
        self.stats
    }

    #[must_use]
    pub fn node(&self, commit_hash: &str) -> Option<&HistoryNode> {
        self.nodes.get(commit_hash)
    }

    pub fn nodes_newest_first(&self) -> impl Iterator<Item = &HistoryNode> {
        self.newest_first
            .iter()
            .filter_map(|hash| self.nodes.get(hash))
    }

    #[must_use]
    pub fn binding_at(&self, commit_hash: &str, path: &str) -> Option<HistoryBinding> {
        let node = self.nodes.get(commit_hash)?;
        node.entry(path).map(|entry| node.binding(entry))
    }

    /// The newest exact persisted binding for `path` on the snapshot's
    /// first-parent ancestry.
    #[must_use]
    pub fn newest_binding_for_path(&self, path: &str) -> Option<HistoryBinding> {
        self.nodes_newest_first()
            .find_map(|node| node.entry(path).map(|entry| node.binding(entry)))
    }

    /// For every path absent from the snapshot tree, return its newest exact
    /// first-parent binding. Results are sorted by path bytes. A binding whose
    /// normalize reference is absent remains present here with `normalize=None`;
    /// downstream chunk projection must treat it as ineligible.
    #[must_use]
    pub fn final_deleted_bindings(&self) -> Vec<HistoryBinding> {
        let live_paths = self
            .nodes
            .get(&self.start_commit)
            .into_iter()
            .flat_map(|node| node.tree.entries.iter().map(|entry| entry.path.as_str()))
            .collect::<BTreeSet<_>>();
        let mut newest_by_path = BTreeMap::new();
        for node in self.nodes_newest_first() {
            for entry in &node.tree.entries {
                if !live_paths.contains(entry.path.as_str()) {
                    newest_by_path
                        .entry(entry.path.clone())
                        .or_insert_with(|| node.binding(entry));
                }
            }
        }
        newest_by_path.into_values().collect()
    }
}

#[derive(Debug, Clone)]
pub struct HistoryReader {
    store: ObjectStore,
    limits: HistoryLimits,
}

impl HistoryReader {
    #[must_use]
    pub fn new(kcs_dir: impl Into<PathBuf>) -> Self {
        Self::with_limits(kcs_dir, HistoryLimits::default())
    }

    #[must_use]
    pub fn with_limits(kcs_dir: impl Into<PathBuf>, limits: HistoryLimits) -> Self {
        Self {
            store: ObjectStore::new(kcs_dir),
            limits,
        }
    }

    /// Read one selected snapshot without traversing its ancestry. This is the
    /// direct `--at`/explicit-commit primitive; a shallow ancestor that is not
    /// required by the selected snapshot cannot make this read fail.
    pub fn snapshot(&self, commit_hash: &str) -> Result<HistoryNode> {
        self.read_node(commit_hash, HistoryStats::default())
            .map(|(node, _)| node)
    }

    pub fn all_parents(&self, start_commit: &str) -> Result<HistoryGraph> {
        let walk = self.walk(start_commit, ParentMode::All)?;
        validate_acyclic(&walk.nodes)?;
        Ok(HistoryGraph {
            start_commit: start_commit.to_owned(),
            nodes: walk.nodes,
            visit_order: walk.order,
            stats: walk.stats,
        })
    }

    pub fn first_parent(&self, start_commit: &str) -> Result<FirstParentHistory> {
        let walk = self.walk(start_commit, ParentMode::First)?;
        Ok(FirstParentHistory {
            start_commit: start_commit.to_owned(),
            nodes: walk.nodes,
            newest_first: walk.order,
            stats: walk.stats,
        })
    }

    fn walk(&self, start_commit: &str, mode: ParentMode) -> Result<WalkState> {
        let mut state = WalkState::default();
        let mut pending = vec![start_commit.to_owned()];
        let mut scheduled = BTreeSet::from([start_commit.to_owned()]);

        while let Some(commit_hash) = pending.pop() {
            let (node, next_stats) = self.read_node(&commit_hash, state.stats)?;

            let parents = match mode {
                ParentMode::All => node.commit.parents.as_slice(),
                ParentMode::First => node.commit.parents.get(..1).unwrap_or_default(),
            };
            for parent in parents.iter().rev() {
                if scheduled.insert(parent.clone()) {
                    pending.push(parent.clone());
                } else if matches!(mode, ParentMode::First) {
                    return Err(KcsError::schema(
                        "commit history contains a first-parent cycle",
                    ));
                }
            }

            state.stats = next_stats;
            state.order.push(commit_hash.clone());
            state.nodes.insert(commit_hash, node);
        }

        Ok(state)
    }

    fn read_node(
        &self,
        commit_hash: &str,
        stats: HistoryStats,
    ) -> Result<(HistoryNode, HistoryStats)> {
        let next_commit_count = checked_total(stats.commits, 1);
        if next_commit_count > self.limits.max_commits {
            return Err(history_limit_error(
                "commits",
                stats,
                self.limits,
                next_commit_count,
            ));
        }

        let commit_object = self.read_required(ObjectKind::Commit, commit_hash, commit_hash)?;
        let commit_bytes = commit_object.bytes.len() as u64;
        let after_commit_bytes = checked_total(stats.verified_bytes, commit_bytes);
        if after_commit_bytes > self.limits.max_verified_bytes {
            return Err(history_limit_error(
                "verified_bytes",
                stats,
                self.limits,
                after_commit_bytes,
            ));
        }
        let commit = decode_commit(commit_object)?;

        let tree_object = self.read_required(ObjectKind::Tree, &commit.tree, commit_hash)?;
        let tree_bytes = tree_object.bytes.len() as u64;
        let next_verified_bytes = checked_total(after_commit_bytes, tree_bytes);
        if next_verified_bytes > self.limits.max_verified_bytes {
            return Err(history_limit_error(
                "verified_bytes",
                stats,
                self.limits,
                next_verified_bytes,
            ));
        }
        let tree = decode_tree(tree_object)?;
        let next_tree_entries = checked_total(stats.tree_entries, tree.entries.len() as u64);
        if next_tree_entries > self.limits.max_tree_entries {
            return Err(history_limit_error(
                "tree_entries",
                stats,
                self.limits,
                next_tree_entries,
            ));
        }

        Ok((
            HistoryNode {
                commit_hash: commit_hash.to_owned(),
                commit,
                tree,
                commit_bytes,
                tree_bytes,
            },
            HistoryStats {
                commits: next_commit_count,
                tree_entries: next_tree_entries,
                verified_bytes: next_verified_bytes,
            },
        ))
    }

    fn read_required(
        &self,
        kind: ObjectKind,
        object_hash: &str,
        commit_hash: &str,
    ) -> Result<StoredObject> {
        match self.store.read_object(kind, object_hash) {
            Ok(object) => Ok(object),
            Err(error) if error.error_code() == "KCS-E-STORE-NOT-FOUND-001" => {
                Err(history_shallow_error(commit_hash, kind, object_hash))
            }
            Err(error) => Err(error),
        }
    }
}

#[derive(Debug, Clone, Copy)]
enum ParentMode {
    All,
    First,
}

#[derive(Debug, Default)]
struct WalkState {
    nodes: BTreeMap<String, HistoryNode>,
    order: Vec<String>,
    stats: HistoryStats,
}

fn decode_commit(object: StoredObject) -> Result<CommitObject> {
    let commit: CommitObject = serde_json::from_slice(&object.bytes)
        .map_err(|error| KcsError::schema(error.to_string()))?;
    if commit.parents.len() > MAX_COMMIT_PARENTS {
        return Err(KcsError::schema(format!(
            "commit parents exceed the limit of {MAX_COMMIT_PARENTS}"
        )));
    }
    commit.validate()?;
    Ok(commit)
}

fn decode_tree(object: StoredObject) -> Result<TreeObject> {
    let tree: TreeObject = serde_json::from_slice(&object.bytes)
        .map_err(|error| KcsError::schema(error.to_string()))?;
    if tree.entries.len() > MAX_TREE_ENTRIES {
        return Err(KcsError::schema(format!(
            "tree entries exceed the limit of {MAX_TREE_ENTRIES}"
        )));
    }
    tree.validate()?;
    Ok(tree)
}

fn validate_acyclic(nodes: &BTreeMap<String, HistoryNode>) -> Result<()> {
    let mut remaining_parents = nodes
        .iter()
        .map(|(hash, node)| (hash.clone(), node.commit.parents.len()))
        .collect::<BTreeMap<_, _>>();
    let mut children = BTreeMap::<&str, Vec<&str>>::new();
    for (child_hash, node) in nodes {
        for parent in &node.commit.parents {
            children
                .entry(parent)
                .or_default()
                .push(child_hash.as_str());
        }
    }
    let mut ready = remaining_parents
        .iter()
        .filter_map(|(hash, count)| (*count == 0).then_some(hash.clone()))
        .collect::<BTreeSet<_>>();
    let mut processed = 0_usize;
    while let Some(hash) = ready.pop_first() {
        processed += 1;
        if let Some(node_children) = children.get(hash.as_str()) {
            for child in node_children {
                let count = remaining_parents
                    .get_mut(*child)
                    .expect("child was collected from nodes");
                *count -= 1;
                if *count == 0 {
                    ready.insert((*child).to_owned());
                }
            }
        }
    }
    if processed != nodes.len() {
        return Err(KcsError::schema("commit history contains a parent cycle"));
    }
    Ok(())
}

fn sort_bindings(bindings: &mut [HistoryBinding]) {
    bindings.sort_by(|a, b| {
        a.binding
            .cmp(&b.binding)
            .then_with(|| a.commit_hash.as_bytes().cmp(b.commit_hash.as_bytes()))
            .then_with(|| a.tree_hash.as_bytes().cmp(b.tree_hash.as_bytes()))
    });
}

fn checked_total(current: u64, increment: u64) -> u64 {
    current.saturating_add(increment)
}

fn history_limit_error(
    exceeded: &str,
    stats: HistoryStats,
    limits: HistoryLimits,
    attempted: u64,
) -> KcsError {
    KcsError::new(
        "KCS-E-COMMIT-HISTORY-LIMIT-001",
        "history walk aggregate limit exceeded",
        json!({
            "exceeded": exceeded,
            "attempted": attempted,
            "commits": stats.commits,
            "tree_entries": stats.tree_entries,
            "verified_bytes": stats.verified_bytes,
            "max_commits": limits.max_commits,
            "max_tree_entries": limits.max_tree_entries,
            "max_verified_bytes": limits.max_verified_bytes,
        }),
        ExitCode::Failure,
    )
}

fn history_shallow_error(
    commit_hash: &str,
    missing_kind: ObjectKind,
    missing_object_hash: &str,
) -> KcsError {
    KcsError::new(
        "KCS-E-COMMIT-SHALLOW-001",
        format!(
            "history walk requires a {} object that is missing or shallow",
            missing_kind.object_type()
        ),
        json!({
            "commit_hash": commit_hash,
            "missing_object_kind": missing_kind.object_type(),
            "missing_object_hash": missing_object_hash,
        }),
        ExitCode::Failure,
    )
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::PathBuf;

    use serde_json::json;

    use super::{HistoryLimits, HistoryReader, TreeBinding};
    use crate::cas::{hash_bytes, ObjectKind, ObjectStore};
    use crate::dag::{build_tree, CommitObject, CommitStats, CommitType, NormalizeRef, TreeEntry};

    struct Fixture {
        _temp: tempfile::TempDir,
        kcs_dir: PathBuf,
        store: ObjectStore,
    }

    impl Fixture {
        fn new() -> Self {
            let temp = tempfile::tempdir().unwrap();
            let kcs_dir = temp.path().join(".kcs");
            fs::create_dir(&kcs_dir).unwrap();
            let store = ObjectStore::new(&kcs_dir);
            Self {
                _temp: temp,
                kcs_dir,
                store,
            }
        }

        fn tree(&self, entries: Vec<TreeEntry>) -> String {
            let tree = build_tree(entries).unwrap();
            self.store
                .write_json(ObjectKind::Tree, &serde_json::to_value(tree).unwrap())
                .unwrap()
                .0
        }

        fn commit(&self, label: &str, tree: &str, parents: Vec<String>) -> String {
            let commit = CommitObject::new(
                tree.to_owned(),
                parents,
                "2026-07-13T00:00:00Z".to_owned(),
                label.to_owned(),
                hash_bytes(b"tool-lock"),
                CommitStats {
                    files_added: 0,
                    files_modified: 0,
                    files_deleted: 0,
                },
                CommitType::Manual,
            )
            .unwrap();
            self.store
                .write_json(ObjectKind::Commit, &serde_json::to_value(commit).unwrap())
                .unwrap()
                .0
        }
    }

    fn entry(path: &str, body: &[u8], normalize: Option<NormalizeRef>) -> TreeEntry {
        let mut entry = TreeEntry::raw_file(path, hash_bytes(body)).unwrap();
        entry.normalize = normalize;
        entry
    }

    fn profile() -> NormalizeRef {
        NormalizeRef {
            tool_profile_hash: hash_bytes(b"profile"),
            gen: 7,
        }
    }

    #[test]
    fn all_parent_graph_keeps_merge_side_bindings_and_hash_ties_introductions() {
        let fixture = Fixture::new();
        let empty = fixture.tree(Vec::new());
        let with_x = fixture.tree(vec![entry("x.md", b"x", Some(profile()))]);
        let root = fixture.commit("root", &empty, Vec::new());
        let left = fixture.commit("left", &with_x, vec![root.clone()]);
        let right = fixture.commit("right", &with_x, vec![root]);
        let merge = fixture.commit("merge", &with_x, vec![left.clone(), right.clone()]);

        let graph = HistoryReader::new(&fixture.kcs_dir)
            .all_parents(&merge)
            .unwrap();
        let binding = TreeBinding {
            path: "x.md".to_owned(),
            raw_hash: hash_bytes(b"x"),
            normalize: Some(profile()),
        };
        let candidates = graph.introduction_candidates(&binding);
        let mut expected = vec![left.as_str(), right.as_str()];
        expected.sort_unstable();
        assert_eq!(
            candidates
                .iter()
                .map(|candidate| candidate.commit_hash.as_str())
                .collect::<Vec<_>>(),
            expected
        );
        assert_eq!(graph.ancestor_most_introductions(&binding), candidates);
        assert_eq!(
            graph.canonical_introduction(&binding).unwrap().commit_hash,
            left.min(right)
        );
    }

    #[test]
    fn all_parent_walk_finds_binding_dropped_by_merge_first_parent() {
        let fixture = Fixture::new();
        let empty = fixture.tree(Vec::new());
        let with_x = fixture.tree(vec![entry("side.md", b"side", Some(profile()))]);
        let root = fixture.commit("root", &empty, Vec::new());
        let main = fixture.commit("main", &empty, vec![root.clone()]);
        let side = fixture.commit("side", &with_x, vec![root]);
        let merge = fixture.commit("merge-drops-side", &empty, vec![main, side.clone()]);

        let graph = HistoryReader::new(&fixture.kcs_dir)
            .all_parents(&merge)
            .unwrap();
        let binding = TreeBinding {
            path: "side.md".to_owned(),
            raw_hash: hash_bytes(b"side"),
            normalize: Some(profile()),
        };
        let historical = graph.canonical_introduction(&binding).unwrap();
        assert_eq!(historical.commit_hash, side);
        assert_eq!(historical.binding.path, "side.md");
    }

    #[test]
    fn ancestor_most_introduction_removes_later_reintroduction() {
        let fixture = Fixture::new();
        let empty = fixture.tree(Vec::new());
        let with_x = fixture.tree(vec![entry("x.md", b"x", Some(profile()))]);
        let root = fixture.commit("root-add", &with_x, Vec::new());
        let deletion = fixture.commit("delete", &empty, vec![root.clone()]);
        let readd = fixture.commit("readd", &with_x, vec![deletion]);

        let graph = HistoryReader::new(&fixture.kcs_dir)
            .all_parents(&readd)
            .unwrap();
        let binding = TreeBinding {
            path: "x.md".to_owned(),
            raw_hash: hash_bytes(b"x"),
            normalize: Some(profile()),
        };
        assert_eq!(graph.introduction_candidates(&binding).len(), 2);
        let ancestor_most = graph.ancestor_most_introductions(&binding);
        assert_eq!(ancestor_most.len(), 1);
        assert_eq!(ancestor_most[0].commit_hash, root);
    }

    #[test]
    fn first_parent_derives_final_deleted_binding_and_preserves_none_normalize() {
        let fixture = Fixture::new();
        let old = fixture.tree(vec![entry("old.md", b"old", None)]);
        let current = fixture.tree(vec![entry("live.md", b"live", Some(profile()))]);
        let root = fixture.commit("old", &old, Vec::new());
        let head = fixture.commit("head", &current, vec![root.clone()]);

        let history = HistoryReader::new(&fixture.kcs_dir)
            .first_parent(&head)
            .unwrap();
        let newest = history.newest_binding_for_path("old.md").unwrap();
        assert_eq!(newest.commit_hash, root);
        assert_eq!(newest.binding.normalize, None);
        let deleted = history.final_deleted_bindings();
        assert_eq!(deleted, vec![newest]);
        assert!(history
            .final_deleted_bindings()
            .iter()
            .all(|binding| binding.binding.path != "live.md"));

        let graph = HistoryReader::new(&fixture.kcs_dir)
            .all_parents(&head)
            .unwrap();
        let binding = TreeBinding {
            path: "old.md".to_owned(),
            raw_hash: hash_bytes(b"old"),
            normalize: None,
        };
        assert_eq!(
            graph
                .canonical_introduction(&binding)
                .unwrap()
                .binding
                .normalize,
            None
        );
    }

    #[test]
    fn exact_aggregate_boundaries_succeed_and_one_beyond_fails_in_each_walk() {
        let fixture = Fixture::new();
        let tree = fixture.tree(vec![entry("x.md", b"x", Some(profile()))]);
        let root = fixture.commit("root", &tree, Vec::new());
        let head = fixture.commit("head", &tree, vec![root]);
        let baseline = HistoryReader::new(&fixture.kcs_dir)
            .all_parents(&head)
            .unwrap()
            .stats();
        assert_eq!(
            HistoryReader::new(&fixture.kcs_dir)
                .first_parent(&head)
                .unwrap()
                .stats(),
            baseline
        );

        let exact = HistoryLimits::new(
            baseline.commits,
            baseline.tree_entries,
            baseline.verified_bytes,
        );
        let exact_reader = HistoryReader::with_limits(&fixture.kcs_dir, exact);
        assert_eq!(exact_reader.all_parents(&head).unwrap().stats(), baseline);
        assert_eq!(exact_reader.first_parent(&head).unwrap().stats(), baseline);
        // A second invocation proves that all-parent and first-parent counters are
        // fresh per walk rather than retained on the reader.
        assert_eq!(exact_reader.all_parents(&head).unwrap().stats(), baseline);

        let cases = [
            (
                "commits",
                HistoryLimits::new(
                    baseline.commits - 1,
                    baseline.tree_entries,
                    baseline.verified_bytes,
                ),
            ),
            (
                "tree_entries",
                HistoryLimits::new(
                    baseline.commits,
                    baseline.tree_entries - 1,
                    baseline.verified_bytes,
                ),
            ),
            (
                "verified_bytes",
                HistoryLimits::new(
                    baseline.commits,
                    baseline.tree_entries,
                    baseline.verified_bytes - 1,
                ),
            ),
        ];
        for (expected_dimension, limits) in cases {
            let reader = HistoryReader::with_limits(&fixture.kcs_dir, limits);
            for error in [
                reader.all_parents(&head).unwrap_err(),
                reader.first_parent(&head).unwrap_err(),
            ] {
                assert_eq!(error.error_code(), "KCS-E-COMMIT-HISTORY-LIMIT-001");
                assert_eq!(error.context()["exceeded"], json!(expected_dimension));
            }
        }
    }

    #[test]
    fn missing_commit_or_tree_is_reported_as_shallow_with_object_cause() {
        let fixture = Fixture::new();
        let empty = fixture.tree(Vec::new());
        let missing_parent = hash_bytes(b"missing-parent");
        let head = fixture.commit("head", &empty, vec![missing_parent.clone()]);
        assert_eq!(
            HistoryReader::new(&fixture.kcs_dir)
                .snapshot(&head)
                .unwrap()
                .commit_hash,
            head
        );
        let error = HistoryReader::new(&fixture.kcs_dir)
            .all_parents(&head)
            .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-COMMIT-SHALLOW-001");
        assert_eq!(error.context()["commit_hash"], json!(missing_parent));
        assert_eq!(error.context()["missing_object_kind"], json!("commit"));

        let missing_tree = hash_bytes(b"missing-tree");
        let shallow = fixture.commit("shallow", &missing_tree, Vec::new());
        let error = HistoryReader::new(&fixture.kcs_dir)
            .first_parent(&shallow)
            .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-COMMIT-SHALLOW-001");
        assert_eq!(error.context()["commit_hash"], json!(shallow));
        assert_eq!(error.context()["missing_object_kind"], json!("tree"));
        assert_eq!(error.context()["missing_object_hash"], json!(missing_tree));

        let raw_only_tree = fixture.store.write_raw(b"raw-only-tree").unwrap();
        let shallow = fixture.commit("raw-is-not-tree", &raw_only_tree, Vec::new());
        let error = HistoryReader::new(&fixture.kcs_dir)
            .snapshot(&shallow)
            .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-COMMIT-SHALLOW-001");
        assert_eq!(error.context()["missing_object_kind"], json!("tree"));
    }

    #[test]
    fn reader_revalidates_cas_instead_of_reusing_previous_walk_truth() {
        let fixture = Fixture::new();
        let tree = fixture.tree(Vec::new());
        let head = fixture.commit("head", &tree, Vec::new());
        let reader = HistoryReader::new(&fixture.kcs_dir);
        reader.all_parents(&head).unwrap();

        let tree_path = fixture.store.object_path(ObjectKind::Tree, &tree).unwrap();
        fs::remove_file(tree_path).unwrap();
        let error = reader.all_parents(&head).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-COMMIT-SHALLOW-001");
        assert_eq!(error.context()["missing_object_kind"], json!("tree"));
    }

    #[test]
    fn first_parent_ignores_merge_side_parent_but_all_parent_does_not() {
        let fixture = Fixture::new();
        let empty = fixture.tree(Vec::new());
        let root = fixture.commit("root", &empty, Vec::new());
        let main = fixture.commit("main", &empty, vec![root.clone()]);
        let side = fixture.commit("side", &empty, vec![root]);
        let merge = fixture.commit("merge", &empty, vec![main.clone(), side.clone()]);

        let first = HistoryReader::new(&fixture.kcs_dir)
            .first_parent(&merge)
            .unwrap();
        assert!(first.node(&main).is_some());
        assert!(first.node(&side).is_none());
        let all = HistoryReader::new(&fixture.kcs_dir)
            .all_parents(&merge)
            .unwrap();
        assert!(all.node(&main).is_some());
        assert!(all.node(&side).is_some());
    }
}
