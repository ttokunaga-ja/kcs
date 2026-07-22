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
    ///
    /// Same boundary-node generalization as [`validate_acyclic`] (a
    /// module-private free function): a parent hash absent from `self.nodes`
    /// (a shallow-skipped ancestor on a tolerant graph, PC45) does not count
    /// against its children's readiness. This is a no-op for a complete graph.
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
            .map(|(hash, node)| {
                let present = node
                    .commit
                    .parents
                    .iter()
                    .filter(|parent| self.nodes.contains_key(parent.as_str()))
                    .count();
                (hash.clone(), present)
            })
            .collect::<BTreeMap<_, _>>();
        let mut children = BTreeMap::<&str, Vec<&str>>::new();
        for (child_hash, node) in &self.nodes {
            for parent in &node.commit.parents {
                if !self.nodes.contains_key(parent.as_str()) {
                    continue;
                }
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

    /// PC45/PC46 (05 §1.6 / §2.2): the all-parent walk used by `--all-history` /
    /// `--since`, tolerant of a shallow (tree-discarded) *ancestor* — it is
    /// skipped (recorded in the returned `shallow_skipped` list, sorted/deduped)
    /// and the walk continues through that commit's parents (still readable from
    /// its commit object, which shallow GC never discards, §2.2). The **start**
    /// commit itself is never tolerated this way: if its own tree is gone the
    /// call hard-fails exactly like `all_parents` (PC47 — a cursor's or `--at`'s
    /// snapshot commit needs its whole tree, so there is no partial degradation
    /// to fall back to). A missing *commit* object (not just its tree) is never
    /// shallow-tolerated either — shallow GC only ever discards trees (§2.2), so
    /// a missing commit is corruption, and this call fails exactly like
    /// `all_parents` in that case too.
    pub fn all_parents_tolerant(&self, start_commit: &str) -> Result<(HistoryGraph, Vec<String>)> {
        let walk = self.walk_tolerant(start_commit, ParentMode::All)?;
        // `validate_acyclic` counts only parent hashes that are themselves keys
        // of `nodes` (a no-op generalization for a complete, non-tolerant graph,
        // where every referenced parent is always present) — a shallow-skipped
        // ancestor is simply not a "remaining parent" any walked descendant
        // needs to wait on.
        validate_acyclic(&walk.nodes)?;
        Ok((
            HistoryGraph {
                start_commit: start_commit.to_owned(),
                nodes: walk.nodes,
                visit_order: walk.order,
                stats: walk.stats,
            },
            walk.shallow_skipped,
        ))
    }

    /// The `first_parent` counterpart of [`Self::all_parents_tolerant`], used by
    /// `--include-deleted`'s first-parent ancestry walk.
    pub fn first_parent_tolerant(
        &self,
        start_commit: &str,
    ) -> Result<(FirstParentHistory, Vec<String>)> {
        let walk = self.walk_tolerant(start_commit, ParentMode::First)?;
        Ok((
            FirstParentHistory {
                start_commit: start_commit.to_owned(),
                nodes: walk.nodes,
                newest_first: walk.order,
                stats: walk.stats,
            },
            walk.shallow_skipped,
        ))
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

    /// Same traversal as [`Self::walk`], except a shallow (tree-missing) commit
    /// other than `start_commit` is skipped instead of failing the whole walk
    /// (PC45). The commit object of a skipped node is still required (it is
    /// where the parent list to keep walking comes from) — only the tree read is
    /// tolerated. Skipped hashes are still counted against `HistoryStats` for
    /// their commit bytes (their tree contributes zero entries/bytes, same as a
    /// legitimately empty tree would).
    fn walk_tolerant(&self, start_commit: &str, mode: ParentMode) -> Result<TolerantWalkState> {
        let mut state = TolerantWalkState::default();
        let mut pending = vec![start_commit.to_owned()];
        let mut scheduled = BTreeSet::from([start_commit.to_owned()]);

        while let Some(commit_hash) = pending.pop() {
            let is_start = commit_hash == start_commit;
            let outcome = self.read_node_tolerant(&commit_hash, state.stats, is_start)?;
            let (parents, next_stats) = match outcome {
                TolerantNodeOutcome::Full(node, next_stats) => {
                    let parents = match mode {
                        ParentMode::All => node.commit.parents.clone(),
                        ParentMode::First => {
                            node.commit.parents.get(..1).unwrap_or_default().to_vec()
                        }
                    };
                    state.order.push(commit_hash.clone());
                    state.nodes.insert(commit_hash.clone(), *node);
                    (parents, next_stats)
                }
                TolerantNodeOutcome::ShallowSkipped { parents, stats } => {
                    state.shallow_skipped.push(commit_hash.clone());
                    let parents = match mode {
                        ParentMode::All => parents,
                        ParentMode::First => parents.get(..1).unwrap_or_default().to_vec(),
                    };
                    // A shallow ancestor still occupies a position in the
                    // newest-first / visit order for `--include-deleted`'s
                    // `nodes_newest_first()` — but that method already
                    // filter_maps through `self.nodes`, so a hash with no node
                    // is silently and correctly skipped there. Do not push it
                    // into `order` — nothing downstream needs it and every
                    // consumer indexes through `self.nodes` first.
                    (parents, stats)
                }
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
        }

        state.shallow_skipped.sort();
        state.shallow_skipped.dedup();
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

    /// [`Self::read_node`]'s shallow-tolerant counterpart (PC45): the commit
    /// object is always required (shallow GC never discards commits, only trees
    /// — §2.2 — so a missing commit is corruption regardless of `is_start`), but
    /// a missing *tree* is tolerated for any node other than `is_start` (the
    /// walk's own starting commit, whose full tree PC47 always requires).
    fn read_node_tolerant(
        &self,
        commit_hash: &str,
        stats: HistoryStats,
        is_start: bool,
    ) -> Result<TolerantNodeOutcome> {
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

        let tree_object = match self.store.read_object(ObjectKind::Tree, &commit.tree) {
            Ok(object) => object,
            Err(error) if error.error_code() == "KCS-E-STORE-NOT-FOUND-001" => {
                if is_start {
                    return Err(history_shallow_error(
                        commit_hash,
                        ObjectKind::Tree,
                        &commit.tree,
                    ));
                }
                return Ok(TolerantNodeOutcome::ShallowSkipped {
                    parents: commit.parents,
                    stats: HistoryStats {
                        commits: next_commit_count,
                        tree_entries: stats.tree_entries,
                        verified_bytes: after_commit_bytes,
                    },
                });
            }
            Err(error) => return Err(error),
        };
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

        Ok(TolerantNodeOutcome::Full(
            Box::new(HistoryNode {
                commit_hash: commit_hash.to_owned(),
                commit,
                tree,
                commit_bytes,
                tree_bytes,
            }),
            HistoryStats {
                commits: next_commit_count,
                tree_entries: next_tree_entries,
                verified_bytes: next_verified_bytes,
            },
        ))
    }
}

enum TolerantNodeOutcome {
    // Boxed: `HistoryNode` is much larger than `ShallowSkipped`'s fields, and
    // this enum is returned by value on every walked commit.
    Full(Box<HistoryNode>, HistoryStats),
    ShallowSkipped {
        parents: Vec<String>,
        stats: HistoryStats,
    },
}

#[derive(Debug, Default)]
struct TolerantWalkState {
    nodes: BTreeMap<String, HistoryNode>,
    order: Vec<String>,
    stats: HistoryStats,
    /// Commit hashes skipped because their tree was gone (PC45/PC46), sorted +
    /// deduped once the walk completes.
    shallow_skipped: Vec<String>,
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

/// Kahn's-algorithm cycle check. Counts only parent hashes that are themselves
/// keys of `nodes` — for a *complete* graph (every `all_parents()` caller today)
/// this is a no-op, because a walk that referenced an unread parent would
/// already have failed with an `Err` before reaching this call. It is a real
/// generalization for `all_parents_tolerant`'s graph (PC45), where a
/// shallow-skipped ancestor is a legitimate "boundary" node: present as a
/// parent reference in its children's commit objects, but deliberately absent
/// from `nodes` (its tree was never read). Such a boundary parent must not
/// block its children from ever becoming "ready" — it contributes no further
/// ancestor information (its own tree is gone), so it is correct to treat it as
/// if it were not there at all for topological-order purposes.
fn validate_acyclic(nodes: &BTreeMap<String, HistoryNode>) -> Result<()> {
    let mut remaining_parents = nodes
        .iter()
        .map(|(hash, node)| {
            let present = node
                .commit
                .parents
                .iter()
                .filter(|parent| nodes.contains_key(parent.as_str()))
                .count();
            (hash.clone(), present)
        })
        .collect::<BTreeMap<_, _>>();
    let mut children = BTreeMap::<&str, Vec<&str>>::new();
    for (child_hash, node) in nodes {
        for parent in &node.commit.parents {
            if !nodes.contains_key(parent.as_str()) {
                continue;
            }
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

/// R23-15 (06 §8 L403 "単独操作 exit 4" / 05 §1.6 L307-310): a bounded
/// history-walk aggregate cap overrun is a PERMANENT failure for a standalone
/// walk (restore/purge's ancestor checks, or any other direct
/// `HistoryReader` caller) -- re-running the identical command cannot change
/// the outcome, so `ExitCode::PermanentFailure` (4), not the generic
/// `ExitCode::Failure` (1) this constructor returned before the fix. Search's
/// own multi-scope aggregation (`crates/kcs-cli/src/main.rs`) computes ITS
/// exit independently across all searched scopes and does not read this
/// field for that computation, so widening it here cannot regress the
/// existing partial-failure behavior there.
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
        ExitCode::PermanentFailure,
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
            manifest_hash: None,
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

    /// R23-15 (06 §8 L403 "単独操作 exit 4"): a standalone history walk
    /// (this is the same `HistoryReader` call restore/purge use directly for
    /// their own ancestor checks) that overruns the aggregate cap is a
    /// PERMANENT failure -- exit 4, not the generic exit 1
    /// `history_limit_error` returned before the fix.
    #[test]
    fn r23_15_history_limit_error_is_permanent_failure_exit_4() {
        let fixture = Fixture::new();
        let tree = fixture.tree(vec![entry("x.md", b"x", Some(profile()))]);
        let root = fixture.commit("root", &tree, Vec::new());
        let head = fixture.commit("head", &tree, vec![root]);
        let baseline = HistoryReader::new(&fixture.kcs_dir)
            .all_parents(&head)
            .unwrap()
            .stats();
        let limits = HistoryLimits::new(
            baseline.commits - 1,
            baseline.tree_entries,
            baseline.verified_bytes,
        );
        let reader = HistoryReader::with_limits(&fixture.kcs_dir, limits);
        for error in [
            reader.all_parents(&head).unwrap_err(),
            reader.first_parent(&head).unwrap_err(),
        ] {
            assert_eq!(error.error_code(), "KCS-E-COMMIT-HISTORY-LIMIT-001");
            assert_eq!(error.exit_code(), crate::ExitCode::PermanentFailure);
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

    /// PC45: an all-parent walk with a shallow (tree-discarded) *ancestor*
    /// skips it and keeps walking through commits reachable beyond it, instead
    /// of failing the whole walk the way plain `all_parents` still does
    /// (regression guard: the non-tolerant path is unchanged).
    #[test]
    fn pc45_all_parents_tolerant_skips_a_shallow_ancestor_and_keeps_walking() {
        let fixture = Fixture::new();
        let root_tree = fixture.tree(vec![entry("root.md", b"root", Some(profile()))]);
        let root = fixture.commit("root", &root_tree, Vec::new());
        let missing_tree = hash_bytes(b"pc45-missing-tree");
        let shallow_mid = fixture.commit("shallow-mid", &missing_tree, vec![root.clone()]);
        let head_tree = fixture.tree(vec![entry("head.md", b"head", Some(profile()))]);
        let head = fixture.commit("head", &head_tree, vec![shallow_mid.clone()]);

        // Unchanged baseline: the non-tolerant walk still hard-fails.
        let error = HistoryReader::new(&fixture.kcs_dir)
            .all_parents(&head)
            .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-COMMIT-SHALLOW-001");

        let (graph, shallow_skipped) = HistoryReader::new(&fixture.kcs_dir)
            .all_parents_tolerant(&head)
            .unwrap();
        assert_eq!(shallow_skipped, vec![shallow_mid.clone()]);
        // The walk continued past the shallow node to its own parent.
        assert!(graph.node(&root).is_some());
        assert!(graph.node(&head).is_some());
        assert!(graph.node(&shallow_mid).is_none());
        // The root's binding is still reachable through the shallow boundary —
        // `canonical_introduction` (which depends on the generalized
        // `ancestor_most_introductions` topology) resolves it correctly rather
        // than silently dropping it.
        let binding = TreeBinding {
            path: "root.md".to_owned(),
            raw_hash: hash_bytes(b"root"),
            normalize: Some(profile()),
        };
        assert_eq!(
            graph.canonical_introduction(&binding).unwrap().commit_hash,
            root
        );
    }

    /// PC47: the *start* commit of a tolerant walk still hard-fails when its own
    /// tree is shallow — only a deeper ancestor is tolerated (PC45's skip is not
    /// a blanket exemption; a `--cursor` replay or `--at <shallow-commit>` needs
    /// the whole tree of the exact commit it targets).
    #[test]
    fn pc47_all_parents_tolerant_still_hard_fails_when_the_start_commit_itself_is_shallow() {
        let fixture = Fixture::new();
        let missing_tree = hash_bytes(b"pc47-missing-tree");
        let shallow_head = fixture.commit("shallow-head", &missing_tree, Vec::new());
        let error = HistoryReader::new(&fixture.kcs_dir)
            .all_parents_tolerant(&shallow_head)
            .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-COMMIT-SHALLOW-001");
        assert_eq!(error.context()["commit_hash"], json!(shallow_head));
    }

    /// PC45's `first_parent` counterpart (used by `--include-deleted`): a
    /// shallow ancestor on the first-parent chain is skipped and the walk keeps
    /// going through commits beyond it.
    #[test]
    fn pc45_first_parent_tolerant_skips_a_shallow_ancestor() {
        let fixture = Fixture::new();
        let root_tree = fixture.tree(Vec::new());
        let root = fixture.commit("root", &root_tree, Vec::new());
        let missing_tree = hash_bytes(b"pc45-fp-missing-tree");
        let shallow_mid = fixture.commit("shallow-mid", &missing_tree, vec![root.clone()]);
        let head_tree = fixture.tree(Vec::new());
        let head = fixture.commit("head", &head_tree, vec![shallow_mid.clone()]);

        let (history, shallow_skipped) = HistoryReader::new(&fixture.kcs_dir)
            .first_parent_tolerant(&head)
            .unwrap();
        assert_eq!(shallow_skipped, vec![shallow_mid]);
        assert!(history.node(&root).is_some());
        assert!(history.node(&head).is_some());
    }

    /// A commit object that is itself missing (as opposed to just its tree) is
    /// never shallow-tolerated, at any position in the walk — shallow GC only
    /// ever discards trees (§2.2), so a missing commit is corruption.
    #[test]
    fn pc45_tolerant_walk_does_not_tolerate_a_missing_commit_object() {
        let fixture = Fixture::new();
        let tree = fixture.tree(Vec::new());
        let missing_parent = hash_bytes(b"pc45-missing-commit");
        let head = fixture.commit("head", &tree, vec![missing_parent.clone()]);
        let error = HistoryReader::new(&fixture.kcs_dir)
            .all_parents_tolerant(&head)
            .unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-COMMIT-SHALLOW-001");
        assert_eq!(error.context()["missing_object_kind"], json!("commit"));
        assert_eq!(error.context()["commit_hash"], json!(missing_parent));
    }

    /// Two independent branches each carrying a shallow ancestor still merge
    /// and topologically resolve correctly (the `ancestor_most_introductions`
    /// generalization holds even with multiple boundary nodes, and duplicate
    /// shallow hashes reached via different paths are deduped).
    #[test]
    fn pc45_tolerant_walk_handles_shallow_ancestors_on_both_merge_branches() {
        let fixture = Fixture::new();
        let empty = fixture.tree(Vec::new());
        let root = fixture.commit("root", &empty, Vec::new());
        let missing_tree_left = hash_bytes(b"pc45-merge-left-missing");
        let missing_tree_right = hash_bytes(b"pc45-merge-right-missing");
        let shallow_left = fixture.commit("shallow-left", &missing_tree_left, vec![root.clone()]);
        let shallow_right =
            fixture.commit("shallow-right", &missing_tree_right, vec![root.clone()]);
        let merge = fixture.commit(
            "merge",
            &empty,
            vec![shallow_left.clone(), shallow_right.clone()],
        );

        let (graph, mut shallow_skipped) = HistoryReader::new(&fixture.kcs_dir)
            .all_parents_tolerant(&merge)
            .unwrap();
        shallow_skipped.sort();
        let mut expected = vec![shallow_left, shallow_right];
        expected.sort();
        assert_eq!(shallow_skipped, expected);
        assert!(graph.node(&root).is_some());
        assert!(graph.node(&merge).is_some());
    }
}
