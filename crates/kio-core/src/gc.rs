//! Read-only, capability-bound garbage collection planning.
//!
//! Public paths are used only to bind and diagnose a scope.  Every store read
//! below is relative to a retained directory descriptor.

use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet, VecDeque};
use std::io::Read;
use std::path::{Component, Path, PathBuf};

use cap_primitives::{ambient_authority, fs as cap_fs};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::cas::{hash_bytes, is_hash, MAX_COMMIT_OBJECT_BYTES, MAX_TREE_OBJECT_BYTES};
use crate::dag::{CommitObject, CommitType, TreeObject, MAX_COMMIT_PARENTS, MAX_TREE_ENTRIES};
use crate::error::{KioError, Result};
use crate::schema::{validate_json_schema, SchemaKind};
use crate::scope::{
    enforce_config_semantics, format_utc_seconds, parse_utc_seconds, KIO_FORMAT_VERSION,
};
use crate::ExitCode;

const MAX_METADATA: u64 = 1024 * 1024;
const MAX_REF: u64 = 4096;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct GcPlanLimits {
    pub max_commits: u64,
    pub max_tree_entries: u64,
    pub max_verified_bytes: u64,
    pub max_refs: u64,
    pub max_receipts: u64,
    pub max_dir_entries: u64,
    pub max_name_bytes: u64,
    pub max_depth: u64,
    pub max_graph_steps: u64,
}
impl Default for GcPlanLimits {
    fn default() -> Self {
        Self {
            max_commits: 100_000,
            max_tree_entries: 10_000_000,
            max_verified_bytes: 4 * 1024 * 1024 * 1024,
            max_refs: 10_000,
            max_receipts: 100_000,
            max_dir_entries: 200_000,
            max_name_bytes: 255,
            max_depth: 4,
            max_graph_steps: 10_000_000,
        }
    }
}
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct GcPlanStats {
    pub commits: u64,
    pub trees_verified: u64,
    pub tree_entries: u64,
    pub verified_bytes: u64,
    pub refs: u64,
    pub receipts: u64,
    pub dir_entries: u64,
    pub graph_steps: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FileObservation {
    identity: Identity,
    state: FileState,
    digest: String,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct GcCandidate {
    pub commit_hash: String,
    pub tree_hash: String,
    pub commit_type: CommitType,
    pub created_at: String,
    pub policy: String,
    pub size_bytes: u64,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct GcExclusion {
    pub reason: String,
    pub count: u64,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct GcPolicy {
    pub keep_last_hours: u32,
    pub keep_hourly_days: u32,
    pub keep_daily_weeks: u32,
    pub keep_weekly_months: u32,
    pub keep_repaired_per_branch: u32,
}
impl Default for GcPolicy {
    fn default() -> Self {
        Self {
            keep_last_hours: 24,
            keep_hourly_days: 7,
            keep_daily_weeks: 4,
            keep_weekly_months: 6,
            keep_repaired_per_branch: 5,
        }
    }
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct GcPlan {
    pub status: String,
    pub as_of: String,
    pub scope_path: String,
    pub policy: GcPolicy,
    pub limits: GcPlanLimits,
    pub stats: GcPlanStats,
    /// A second, independently bounded full read of the planning truth. A
    /// mismatch aborts instead of returning a stale candidate list.
    pub stability_check_stats: GcPlanStats,
    pub candidate_count: u64,
    pub candidate_tree_count: u64,
    pub estimated_bytes: u64,
    pub candidates: Vec<GcCandidate>,
    pub exclusions: Vec<GcExclusion>,
    pub object_kinds_planned: Vec<String>,
}

#[derive(Debug)]
pub struct GcPlanner {
    root: PathBuf,
    scope: std::fs::File,
    kio: std::fs::File,
    limits: GcPlanLimits,
}

struct TruthSnapshot {
    scope_digest: String,
    config_digest: String,
    policy: GcPolicy,
    refs: BTreeMap<String, String>,
    receipts: HashMap<String, String>,
    commits: HashMap<String, CommitObject>,
    tree_sizes: HashMap<String, u64>,
    observations: BTreeMap<String, FileObservation>,
}
impl GcPlanner {
    pub fn bind_current() -> Result<Self> {
        Self::bind(std::env::current_dir().map_err(|e| ioerr(e, "."))?)
    }
    pub fn bind(root: impl Into<PathBuf>) -> Result<Self> {
        let requested = root.into();
        if !requested.is_absolute() {
            return Err(KioError::invalid_usage(
                "GC planner scope root must be absolute",
            ));
        }
        // Bind the caller's actual path component-by-component before asking
        // the OS for a canonical diagnostic name. This rejects a symlink or
        // reparse component instead of silently following it during bind.
        let scope = open_bound_absolute(&requested)?;
        let public = requested.canonicalize().map_err(|e| ioerr(e, "scope"))?;
        if id_file(&scope)? != id_path(&public)? {
            return Err(corrupt("scope root changed while binding"));
        }
        let kio = open_optional_dir(&scope, ".kio")?
            .ok_or_else(|| KioError::invalid_usage("current directory is not a Kio scope"))?;
        Ok(Self {
            root: public,
            scope,
            kio,
            limits: GcPlanLimits::default(),
        })
    }
    pub fn with_limits(mut self, limits: GcPlanLimits) -> Self {
        self.limits = limits;
        self
    }
    pub fn plan_at(&self, now: i64) -> Result<GcPlan> {
        self.plan_at_inner(now, || {})
    }

    fn plan_at_inner(&self, now: i64, before_stability_check: impl FnOnce()) -> Result<GcPlan> {
        let root_id = id_file(&self.scope)?;
        let kio_id = id_file(&self.kio)?;
        self.require_layout()?;
        let mut st = GcPlanStats::default();
        let mut observations = BTreeMap::new();
        let scope_bytes = read_accounted_observed(
            &self.kio,
            "scope.json",
            MAX_METADATA,
            &mut st,
            &self.limits,
            &mut observations,
            "scope.json",
        )?;
        let scope_digest = validate_scope_bytes(&scope_bytes)?;
        let config_bytes = read_accounted_observed(
            &self.kio,
            "config.toml",
            MAX_METADATA,
            &mut st,
            &self.limits,
            &mut observations,
            "config.toml",
        )?;
        let (policy, config_digest) = read_policy_bytes(&config_bytes)?;
        let refs = self.read_refs(&mut st, &mut observations)?;
        let receipts = self.read_receipts(&mut st, &mut observations)?;
        let all = self.inventory_commits(&mut st, &mut observations)?;
        validate_commit_links(&all)?;
        validate_receipt_links(&receipts, &all)?;
        let mut sizes = HashMap::new();
        for (h, c) in &all {
            if !receipts.contains_key(h) && !sizes.contains_key(&c.tree) {
                sizes.insert(
                    c.tree.clone(),
                    self.verify_tree(&c.tree, &mut st, &mut observations)?,
                );
            }
        }
        let mut reachable = HashSet::new();
        let mut q: VecDeque<_> = refs.values().cloned().collect();
        while let Some(h) = q.pop_front() {
            graph_step(&mut st, &self.limits)?;
            if reachable.insert(h.clone()) {
                let c = all
                    .get(&h)
                    .ok_or_else(|| corrupt("ref or parent commit is missing"))?;
                q.extend(c.parents.iter().cloned());
            }
        }
        let mut ex = BTreeMap::new();
        for _h in all.keys().filter(|h| !reachable.contains(*h)) {
            inc(&mut ex, "unreachable_commit");
        }
        let tips: HashSet<_> = refs.values().cloned().collect();
        let branches: BTreeSet<_> = refs
            .iter()
            .filter(|(n, _)| n.starts_with("heads/"))
            .map(|(_, h)| h.clone())
            .collect();
        let mut repaired = HashSet::new();
        let mut branch_reachable = HashSet::new();
        for b in &branches {
            let branch_closure = closure(b, &all, &mut st, &self.limits)?;
            branch_reachable.extend(branch_closure.iter().cloned());
            let keep = policy.keep_repaired_per_branch as usize;
            if keep == 0 {
                continue;
            }
            let mut v: Vec<_> = branch_closure
                .into_iter()
                .filter(|h| all[h].commit_type == CommitType::Repaired)
                .collect();
            if keep < v.len() {
                v.select_nth_unstable_by(keep, |a, b| newer_first((&all[a], a), (&all[b], b)));
                v.truncate(keep);
            }
            repaired.extend(v);
        }
        let mut possible = HashSet::new();
        for h in &reachable {
            let c = &all[h];
            let why = if receipts.contains_key(h) {
                Some("already_shallow")
            } else if tips.contains(h) {
                Some("ref_tip")
            } else if !matches!(c.commit_type, CommitType::Auto | CommitType::Repaired) {
                Some("protected_commit_type")
            } else if c.commit_type == CommitType::Repaired && repaired.contains(h) {
                Some("retained_repaired")
            } else if c.commit_type == CommitType::Repaired && !branch_reachable.contains(h) {
                Some("repaired_without_branch")
            } else {
                None
            };
            if let Some(x) = why {
                inc(&mut ex, x)
            } else {
                possible.insert(h.clone());
            }
        }
        let autos: HashSet<_> = possible
            .iter()
            .filter(|h| all[*h].commit_type == CommitType::Auto)
            .cloned()
            .collect();
        let kept = auto_retained(&autos, &all, now, &policy, &mut ex);
        possible.retain(|h| !kept.contains(h));
        let mut by_tree: HashMap<String, Vec<String>> = HashMap::new();
        for (h, c) in &all {
            by_tree.entry(c.tree.clone()).or_default().push(h.clone());
        }
        let initial = possible.clone();
        possible.retain(|h| {
            let ok = by_tree[&all[h].tree]
                .iter()
                .all(|x| receipts.contains_key(x) || initial.contains(x));
            if !ok {
                inc(&mut ex, "shared_tree_non_shallow")
            };
            ok
        });
        let mut candidates = Vec::with_capacity(possible.len());
        for h in possible {
            let c = &all[&h];
            let size_bytes = sizes
                .get(&c.tree)
                .copied()
                .ok_or_else(|| corrupt("candidate tree was not verified"))?;
            candidates.push(GcCandidate {
                commit_hash: h,
                tree_hash: c.tree.clone(),
                commit_type: c.commit_type,
                created_at: c.created_at.clone(),
                policy: if c.commit_type == CommitType::Auto {
                    "auto_retention".into()
                } else {
                    "derived_retention".into()
                },
                size_bytes,
            });
        }
        candidates.sort_by(|a, b| a.commit_hash.cmp(&b.commit_hash));
        let unique: BTreeSet<_> = candidates.iter().map(|c| c.tree_hash.clone()).collect();
        let estimated = unique.iter().try_fold(0u64, |n, t| {
            n.checked_add(sizes.get(t).copied().unwrap_or(0))
                .ok_or_else(|| limit("estimated bytes"))
        })?;
        before_stability_check();
        let stability_check_stats = self.require_stable_truth(&TruthSnapshot {
            scope_digest,
            config_digest,
            policy: policy.clone(),
            refs,
            receipts,
            commits: all,
            tree_sizes: sizes,
            observations,
        })?;
        self.recheck(root_id, kio_id)?;
        Ok(GcPlan {
            status: "dry_run".into(),
            as_of: format_utc_seconds(now),
            scope_path: self.root.display().to_string(),
            policy,
            limits: self.limits.clone(),
            stats: st,
            stability_check_stats,
            candidate_count: candidates.len() as u64,
            candidate_tree_count: unique.len() as u64,
            estimated_bytes: estimated,
            candidates,
            exclusions: ex
                .into_iter()
                .map(|(reason, count)| GcExclusion { reason, count })
                .collect(),
            object_kinds_planned: vec!["tree".into()],
        })
    }
    fn recheck(&self, r: Identity, k: Identity) -> Result<()> {
        if id_file(&self.scope)? != r
            || id_file(&self.kio)? != k
            || id_path(&self.root)? != r
            || id_child(&self.scope, ".kio")? != k
        {
            Err(corrupt("scope root changed while planning"))
        } else {
            Ok(())
        }
    }
    fn require_layout(&self) -> Result<()> {
        for d in [
            "refs",
            "refs/heads",
            "refs/tags-v1",
            "objects",
            "objects/commits",
            "objects/trees",
        ] {
            let _ = open_path(&self.kio, d)?;
        }
        Ok(())
    }
    fn read_refs(
        &self,
        s: &mut GcPlanStats,
        observations: &mut BTreeMap<String, FileObservation>,
    ) -> Result<BTreeMap<String, String>> {
        let mut o = BTreeMap::new();
        let h = String::from_utf8(read_accounted_observed(
            &self.kio,
            "HEAD",
            MAX_REF,
            s,
            &self.limits,
            observations,
            "HEAD",
        )?)
        .map_err(|_| corrupt("ref is not utf8"))?;
        if !h.trim().is_empty() {
            add_ref(&mut o, "HEAD".into(), h.trim(), s, &self.limits)?
        }
        let refs = open_path(&self.kio, "refs")?;
        for (dir, tag) in [("heads", false), ("tags-v1", true)] {
            let d = open_dir(&refs, dir)?;
            for n in names(&d, s, &self.limits, 2)? {
                if tag && n == "names.jsonl" {
                    let _ = read_accounted_observed(
                        &d,
                        &n,
                        MAX_METADATA,
                        s,
                        &self.limits,
                        observations,
                        &format!("refs/{dir}/{n}"),
                    )?;
                    continue;
                }
                if tag && !(n.len() == 68 && n.starts_with("tag-") && hex(&n[4..])) {
                    return Err(corrupt("invalid tag ref leaf"));
                }
                let v = String::from_utf8(read_accounted_observed(
                    &d,
                    &n,
                    MAX_REF,
                    s,
                    &self.limits,
                    observations,
                    &format!("refs/{dir}/{n}"),
                )?)
                .map_err(|_| corrupt("ref is not utf8"))?;
                if v.trim().is_empty() {
                    if tag || n != "main" {
                        return Err(corrupt("ref is empty"));
                    }
                } else {
                    add_ref(&mut o, format!("{dir}/{n}"), v.trim(), s, &self.limits)?;
                }
            }
        }
        Ok(o)
    }
    fn read_receipts(
        &self,
        s: &mut GcPlanStats,
        observations: &mut BTreeMap<String, FileObservation>,
    ) -> Result<HashMap<String, String>> {
        let gc = match open_optional_dir(&self.kio, "gc")? {
            Some(directory) => directory,
            None => return Ok(HashMap::new()),
        };
        let d = match open_optional_dir(&gc, "shallowed")? {
            Some(directory) => directory,
            None => return Ok(HashMap::new()),
        };
        let mut o = HashMap::new();
        for n in names(&d, s, &self.limits, 3)? {
            if n.len() != 64 || !hex(&n) {
                return Err(corrupt("invalid shallow receipt leaf"));
            }
            let bytes = read_accounted_observed(
                &d,
                &n,
                MAX_METADATA,
                s,
                &self.limits,
                observations,
                &format!("gc/shallowed/{n}"),
            )?;
            let r: Receipt =
                serde_json::from_slice(&bytes).map_err(|_| corrupt("malformed shallow receipt"))?;
            if r.commit_hash != format!("sha256:{n}")
                || !is_hash(&r.tree_hash)
                || r.gc_policy != "shallow"
                || !is_canonical_utc_timestamp(&r.shallowed_at)
                || o.insert(r.commit_hash, r.tree_hash).is_some()
            {
                return Err(corrupt("invalid shallow receipt"));
            }
            s.receipts = checked(s.receipts, 1, "receipts")?;
            if s.receipts > self.limits.max_receipts {
                return Err(limit("receipts"));
            }
        }
        Ok(o)
    }
    fn inventory_commits(
        &self,
        s: &mut GcPlanStats,
        observations: &mut BTreeMap<String, FileObservation>,
    ) -> Result<HashMap<String, CommitObject>> {
        let b = open_path(&self.kio, "objects/commits")?;
        let mut o = HashMap::new();
        for a in names(&b, s, &self.limits, 2)? {
            if a.len() != 2 || !hex(&a) {
                return Err(corrupt("invalid commit fanout"));
            }
            let ad = open_dir(&b, &a)?;
            for bb in names(&ad, s, &self.limits, 3)? {
                if bb.len() != 2 || !hex(&bb) {
                    return Err(corrupt("invalid commit fanout"));
                }
                let bd = open_dir(&ad, &bb)?;
                for n in names(&bd, s, &self.limits, 4)? {
                    if n.len() != 64 || !hex(&n) || n[..2] != a || n[2..4] != bb {
                        return Err(corrupt("invalid commit leaf"));
                    }
                    let x = read_accounted_observed(
                        &bd,
                        &n,
                        MAX_COMMIT_OBJECT_BYTES,
                        s,
                        &self.limits,
                        observations,
                        &format!("commit/{a}/{bb}/{n}"),
                    )?;
                    let h = format!("sha256:{n}");
                    if hash_bytes(&x) != h {
                        return Err(corrupt("commit hash mismatch"));
                    }
                    let c: CommitObject =
                        serde_json::from_slice(&x).map_err(|_| corrupt("invalid commit object"))?;
                    if c.parents.len() > MAX_COMMIT_PARENTS {
                        return Err(corrupt("commit parent limit exceeded"));
                    }
                    c.validate().map_err(|_| corrupt("invalid commit object"))?;
                    if o.insert(h, c).is_some() {
                        return Err(corrupt("duplicate commit"));
                    }
                    s.commits = checked(s.commits, 1, "commits")?;
                    if s.commits > self.limits.max_commits {
                        return Err(limit("commits"));
                    }
                }
            }
        }
        Ok(o)
    }
    fn verify_tree(
        &self,
        h: &str,
        s: &mut GcPlanStats,
        observations: &mut BTreeMap<String, FileObservation>,
    ) -> Result<u64> {
        let raw = h
            .strip_prefix("sha256:")
            .ok_or_else(|| corrupt("invalid tree hash"))?;
        if raw.len() != 64 || !hex(raw) {
            return Err(corrupt("invalid tree hash"));
        }
        let b = open_path(&self.kio, "objects/trees")?;
        let a = open_required_dir(&b, &raw[..2], "tree object fanout is missing")?;
        let d = open_required_dir(&a, &raw[2..4], "tree object fanout is missing")?;
        let x = read_required_accounted_observed(
            &d,
            raw,
            MAX_TREE_OBJECT_BYTES,
            "tree object is missing",
            s,
            &self.limits,
            observations,
            &format!("tree/{}/{}/{}", &raw[..2], &raw[2..4], raw),
        )?;
        if hash_bytes(&x) != h {
            return Err(corrupt("tree hash mismatch"));
        }
        let t: TreeObject =
            serde_json::from_slice(&x).map_err(|_| corrupt("invalid tree object"))?;
        if t.entries.len() > MAX_TREE_ENTRIES {
            return Err(corrupt("tree entry limit exceeded"));
        }
        t.validate().map_err(|_| corrupt("invalid tree object"))?;
        s.trees_verified = checked(s.trees_verified, 1, "trees")?;
        s.tree_entries = checked(s.tree_entries, t.entries.len() as u64, "tree entries")?;
        if s.tree_entries > self.limits.max_tree_entries {
            return Err(limit("tree entries"));
        }
        Ok(x.len() as u64)
    }

    fn require_stable_truth(&self, expected: &TruthSnapshot) -> Result<GcPlanStats> {
        let mut stats = GcPlanStats::default();
        let mut observations = BTreeMap::new();
        let scope_bytes = read_accounted_observed(
            &self.kio,
            "scope.json",
            MAX_METADATA,
            &mut stats,
            &self.limits,
            &mut observations,
            "scope.json",
        )?;
        let scope_digest = validate_scope_bytes(&scope_bytes)?;
        let config_bytes = read_accounted_observed(
            &self.kio,
            "config.toml",
            MAX_METADATA,
            &mut stats,
            &self.limits,
            &mut observations,
            "config.toml",
        )?;
        let (policy, config_digest) = read_policy_bytes(&config_bytes)?;
        let refs = self.read_refs(&mut stats, &mut observations)?;
        let receipts = self.read_receipts(&mut stats, &mut observations)?;
        let commits = self.inventory_commits(&mut stats, &mut observations)?;
        validate_commit_links(&commits)?;
        validate_receipt_links(&receipts, &commits)?;

        let mut tree_sizes = HashMap::new();
        for (commit_hash, commit) in &commits {
            if !receipts.contains_key(commit_hash) && !tree_sizes.contains_key(&commit.tree) {
                tree_sizes.insert(
                    commit.tree.clone(),
                    self.verify_tree(&commit.tree, &mut stats, &mut observations)?,
                );
            }
        }
        if scope_digest != expected.scope_digest
            || config_digest != expected.config_digest
            || policy != expected.policy
            || refs != expected.refs
            || receipts != expected.receipts
            || commits != expected.commits
            || tree_sizes != expected.tree_sizes
            || observations != expected.observations
        {
            return Err(corrupt("store truth changed while planning GC"));
        }
        Ok(stats)
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Receipt {
    commit_hash: String,
    tree_hash: String,
    gc_policy: String,
    shallowed_at: String,
}

fn validate_scope_bytes(bytes: &[u8]) -> Result<String> {
    let value: serde_json::Value =
        serde_json::from_slice(bytes).map_err(|error| KioError::schema(error.to_string()))?;
    let version = match value.get("kio_format_version") {
        Some(serde_json::Value::String(version)) => version.as_str(),
        Some(_) => return Err(KioError::incompatible_format("<non-string>")),
        None => return Err(KioError::incompatible_format("<missing>")),
    };
    if version != KIO_FORMAT_VERSION {
        return Err(KioError::incompatible_format(version));
    }
    validate_json_schema(SchemaKind::Scope, &value)?;
    Ok(hash_bytes(bytes))
}

fn read_policy_bytes(bytes: &[u8]) -> Result<(GcPolicy, String)> {
    if bytes.is_empty() {
        return Ok((GcPolicy::default(), hash_bytes(bytes)));
    }
    let value: toml::Value = toml::from_str(
        std::str::from_utf8(bytes).map_err(|_| KioError::schema("config not utf8"))?,
    )
    .map_err(|error| KioError::schema(error.to_string()))?;
    let json = serde_json::to_value(&value).map_err(|error| KioError::schema(error.to_string()))?;
    validate_json_schema(SchemaKind::Config, &json)?;
    enforce_config_semantics(&json)?;
    let mut policy = GcPolicy::default();
    if let Some(retention) = value.get("gc").and_then(|gc| gc.get("auto_retention")) {
        policy.keep_last_hours = num(retention, "keep_last_hours", policy.keep_last_hours)?;
        policy.keep_hourly_days = num(retention, "keep_hourly_days", policy.keep_hourly_days)?;
        policy.keep_daily_weeks = num(retention, "keep_daily_weeks", policy.keep_daily_weeks)?;
        policy.keep_weekly_months =
            num(retention, "keep_weekly_months", policy.keep_weekly_months)?;
    }
    if let Some(retention) = value.get("gc").and_then(|gc| gc.get("derived_retention")) {
        policy.keep_repaired_per_branch = num(
            retention,
            "keep_repaired_per_branch",
            policy.keep_repaired_per_branch,
        )?;
    }
    let hourly_hours = policy
        .keep_hourly_days
        .checked_mul(24)
        .ok_or_else(|| limit("policy"))?;
    let daily_days = policy
        .keep_daily_weeks
        .checked_mul(7)
        .ok_or_else(|| limit("policy"))?;
    let weekly_days = policy
        .keep_weekly_months
        .checked_mul(30)
        .ok_or_else(|| limit("policy"))?;
    if policy.keep_last_hours > hourly_hours
        || policy.keep_hourly_days > daily_days
        || daily_days > weekly_days
    {
        return Err(KioError::schema("gc retention horizons must be monotonic"));
    }
    Ok((policy, hash_bytes(bytes)))
}

fn open_bound_absolute(path: &Path) -> Result<std::fs::File> {
    let mut filesystem_root = PathBuf::new();
    let mut descendants = Vec::new();
    let mut saw_root = false;
    for c in path.components() {
        match c {
            Component::Prefix(prefix) => filesystem_root.push(prefix.as_os_str()),
            Component::RootDir => {
                filesystem_root.push(c.as_os_str());
                saw_root = true;
            }
            Component::Normal(name) if saw_root => descendants.push(name.to_os_string()),
            Component::CurDir => {}
            _ => return Err(corrupt("invalid scope path")),
        }
    }
    if !saw_root {
        return Err(corrupt("scope path has no stable filesystem root"));
    }
    let mut directory = cap_fs::open_ambient_dir(&filesystem_root, ambient_authority())
        .map_err(|error| ioerr(error, &filesystem_root))?;
    validate_directory_handle(&directory, &filesystem_root)?;
    for name in descendants {
        directory = open_dir_os(&directory, &name)?;
    }
    Ok(directory)
}
fn open_path(base: &std::fs::File, path: &str) -> Result<std::fs::File> {
    let mut d = base.try_clone().map_err(|e| ioerr(e, path))?;
    for c in Path::new(path).components() {
        let Component::Normal(x) = c else {
            return Err(corrupt("invalid store layout path"));
        };
        d = open_dir_os(&d, x)?
    }
    Ok(d)
}
fn open_dir(base: &std::fs::File, n: &str) -> Result<std::fs::File> {
    open_dir_os(base, std::ffi::OsStr::new(n))
}

/// Open one optional direct-child directory without following its final
/// component. Only an exact `NotFound` is absence; every other failure remains
/// observable so an unsafe entry cannot masquerade as an empty namespace.
fn open_optional_dir(base: &std::fs::File, n: &str) -> Result<Option<std::fs::File>> {
    let path = Path::new(n);
    let directory = match cap_fs::open_dir_nofollow(base, path) {
        Ok(directory) => directory,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(ioerr(error, n)),
    };
    validate_directory_handle(&directory, n)?;
    Ok(Some(directory))
}

fn open_required_dir(
    base: &std::fs::File,
    n: &str,
    missing_message: &str,
) -> Result<std::fs::File> {
    open_optional_dir(base, n)?.ok_or_else(|| corrupt(missing_message))
}

fn open_dir_os(base: &std::fs::File, n: &std::ffi::OsStr) -> Result<std::fs::File> {
    let d = cap_fs::open_dir_nofollow(base, Path::new(n)).map_err(|e| ioerr(e, n))?;
    validate_directory_handle(&d, n)?;
    Ok(d)
}

fn validate_directory_handle(directory: &std::fs::File, display: impl AsRef<Path>) -> Result<()> {
    let metadata =
        cap_fs::Metadata::from_file(directory).map_err(|error| ioerr(error, display.as_ref()))?;
    if !metadata.is_dir() {
        return Err(corrupt("expected real directory"));
    }
    #[cfg(windows)]
    {
        use cap_fs::_WindowsByHandle;
        use windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT;

        if metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
            return Err(corrupt("directory is a Windows reparse point"));
        }
    }
    Ok(())
}
fn names(
    d: &std::fs::File,
    s: &mut GcPlanStats,
    l: &GcPlanLimits,
    depth: u64,
) -> Result<Vec<String>> {
    if depth > l.max_depth {
        return Err(limit("directory depth"));
    }
    let mut v = Vec::new();
    for e in cap_fs::read_base_dir(d).map_err(|e| ioerr(e, "directory"))? {
        let e = e.map_err(|e| ioerr(e, "directory"))?;
        let n = e
            .file_name()
            .into_string()
            .map_err(|_| corrupt("non-utf8 store entry"))?;
        if n.len() as u64 > l.max_name_bytes {
            return Err(limit("name bytes"));
        }
        saturating_entry(s, l)?;
        v.push(n)
    }
    v.sort();
    Ok(v)
}
fn read_regular_observed(
    d: &std::fs::File,
    n: &str,
    max: u64,
) -> Result<(Vec<u8>, FileObservation)> {
    let p = Path::new(n);
    let before = cap_fs::stat(d, p, cap_fs::FollowSymlinks::No).map_err(|e| ioerr(e, n))?;
    valid_file(&before, max)?;
    let mut o = cap_fs::OpenOptions::new();
    o.read(true);
    o._cap_fs_ext_follow(cap_fs::FollowSymlinks::No);
    let mut f = cap_fs::open(d, p, &o).map_err(|e| ioerr(e, n))?;
    let opened = cap_fs::Metadata::from_file(&f).map_err(|e| ioerr(e, n))?;
    valid_file(&opened, max)?;
    if !same_file_state(&before, &opened)? {
        return Err(corrupt("store file changed while opening"));
    }
    let mut b = Vec::with_capacity(usize::try_from(opened.len()).map_err(|_| limit("file bytes"))?);
    (&mut f)
        .take(max.saturating_add(1))
        .read_to_end(&mut b)
        .map_err(|e| ioerr(e, n))?;
    if b.len() as u64 > max {
        return Err(limit("file bytes"));
    }
    let after = cap_fs::stat(d, p, cap_fs::FollowSymlinks::No).map_err(|e| ioerr(e, n))?;
    valid_file(&after, max)?;
    if b.len() as u64 != opened.len() || !same_file_state(&after, &opened)? {
        return Err(corrupt("store file changed while read"));
    }
    let observation = FileObservation {
        identity: id_meta(&opened)?,
        state: file_state(&opened),
        digest: hash_bytes(&b),
    };
    Ok((b, observation))
}

#[cfg(test)]
fn read_regular(d: &std::fs::File, n: &str, max: u64) -> Result<Vec<u8>> {
    read_regular_observed(d, n, max).map(|(bytes, _)| bytes)
}

fn read_accounted_observed(
    directory: &std::fs::File,
    name: &str,
    max: u64,
    stats: &mut GcPlanStats,
    limits: &GcPlanLimits,
    observations: &mut BTreeMap<String, FileObservation>,
    observation_name: &str,
) -> Result<Vec<u8>> {
    let (bytes, observation) = read_regular_observed(directory, name, max)?;
    account(stats, bytes.len() as u64, limits)?;
    if observations
        .insert(observation_name.to_owned(), observation)
        .is_some()
    {
        return Err(corrupt("duplicate observed store path"));
    }
    Ok(bytes)
}

#[allow(clippy::too_many_arguments)]
fn read_required_accounted_observed(
    directory: &std::fs::File,
    name: &str,
    max: u64,
    missing_message: &str,
    stats: &mut GcPlanStats,
    limits: &GcPlanLimits,
    observations: &mut BTreeMap<String, FileObservation>,
    observation_name: &str,
) -> Result<Vec<u8>> {
    match read_accounted_observed(
        directory,
        name,
        max,
        stats,
        limits,
        observations,
        observation_name,
    ) {
        Err(error) if is_io_not_found(&error) => Err(corrupt(missing_message)),
        result => result,
    }
}
fn valid_file(m: &cap_fs::Metadata, max: u64) -> Result<()> {
    if !m.is_file() || m.len() > max {
        return Err(if m.len() > max {
            limit("file bytes")
        } else {
            corrupt("non-regular store entry")
        });
    }
    #[cfg(unix)]
    {
        use cap_primitives::fs::MetadataExt;
        if m.nlink() != 1 {
            return Err(corrupt("linked store entry"));
        }
    }
    #[cfg(windows)]
    {
        use cap_fs::_WindowsByHandle;
        use windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT;

        if m.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 || m.number_of_links() != Some(1)
        {
            return Err(corrupt("linked store entry"));
        }
    }
    Ok(())
}
#[derive(Debug, Clone, PartialEq, Eq)]
struct Identity(u64, u64);

#[derive(Debug, Clone, PartialEq, Eq)]
struct FileState {
    len: u64,
    modified_seconds: i64,
    modified_nanos: i64,
    changed_seconds: i64,
    changed_nanos: i64,
}
fn id_meta(m: &cap_fs::Metadata) -> Result<Identity> {
    #[cfg(unix)]
    {
        use cap_primitives::fs::MetadataExt;
        Ok(Identity(m.dev(), m.ino()))
    }
    #[cfg(windows)]
    {
        use cap_fs::_WindowsByHandle;
        let volume = m
            .volume_serial_number()
            .ok_or_else(|| corrupt("store identity is unavailable"))?;
        let index = m
            .file_index()
            .ok_or_else(|| corrupt("store identity is unavailable"))?;
        Ok(Identity(u64::from(volume), index))
    }

    #[cfg(not(any(unix, windows)))]
    {
        let _ = m;
        Err(corrupt("store identity is unsupported on this platform"))
    }
}

#[cfg(unix)]
fn same_file_state(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> Result<bool> {
    Ok(id_meta(left)? == id_meta(right)? && file_state(left) == file_state(right))
}

#[cfg(not(unix))]
fn same_file_state(left: &cap_fs::Metadata, right: &cap_fs::Metadata) -> Result<bool> {
    Ok(id_meta(left)? == id_meta(right)?
        && left.len() == right.len()
        && left.modified().ok() == right.modified().ok())
}

#[cfg(unix)]
fn file_state(metadata: &cap_fs::Metadata) -> FileState {
    use cap_primitives::fs::MetadataExt;
    FileState {
        len: metadata.len(),
        modified_seconds: metadata.mtime(),
        modified_nanos: metadata.mtime_nsec(),
        changed_seconds: metadata.ctime(),
        changed_nanos: metadata.ctime_nsec(),
    }
}

#[cfg(not(unix))]
fn file_state(metadata: &cap_fs::Metadata) -> FileState {
    let modified = metadata
        .modified()
        .ok()
        .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok());
    FileState {
        len: metadata.len(),
        modified_seconds: modified
            .as_ref()
            .and_then(|duration| i64::try_from(duration.as_secs()).ok())
            .unwrap_or(-1),
        modified_nanos: modified
            .as_ref()
            .map_or(-1, |duration| i64::from(duration.subsec_nanos())),
        changed_seconds: -1,
        changed_nanos: -1,
    }
}
fn id_file(f: &std::fs::File) -> Result<Identity> {
    id_meta(&cap_fs::Metadata::from_file(f).map_err(|e| ioerr(e, "scope"))?)
}
fn id_path(p: &Path) -> Result<Identity> {
    let f = open_bound_absolute(p)?;
    id_file(&f)
}
fn id_child(d: &std::fs::File, n: &str) -> Result<Identity> {
    let x = open_dir(d, n)?;
    id_file(&x)
}
fn is_io_not_found(error: &KioError) -> bool {
    error.error_code() == "KIO-E-STORE-IO-001"
        && error
            .context()
            .get("io_error_kind")
            .and_then(serde_json::Value::as_str)
            == Some("not_found")
}
fn hex(x: &str) -> bool {
    !x.is_empty()
        && x.bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
fn checked(a: u64, b: u64, w: &str) -> Result<u64> {
    a.checked_add(b).ok_or_else(|| limit(w))
}
fn saturating_entry(s: &mut GcPlanStats, l: &GcPlanLimits) -> Result<()> {
    s.dir_entries = checked(s.dir_entries, 1, "directory entries")?;
    if s.dir_entries > l.max_dir_entries {
        Err(limit("directory entries"))
    } else {
        Ok(())
    }
}
fn account(s: &mut GcPlanStats, n: u64, l: &GcPlanLimits) -> Result<()> {
    s.verified_bytes = checked(s.verified_bytes, n, "verified bytes")?;
    if s.verified_bytes > l.max_verified_bytes {
        Err(limit("verified bytes"))
    } else {
        Ok(())
    }
}
fn add_ref(
    o: &mut BTreeMap<String, String>,
    n: String,
    v: &str,
    s: &mut GcPlanStats,
    l: &GcPlanLimits,
) -> Result<()> {
    if !is_hash(v) {
        return Err(corrupt("invalid ref hash"));
    }
    if o.insert(n, v.into()).is_some() {
        return Err(corrupt("duplicate ref"));
    }
    s.refs = checked(s.refs, 1, "refs")?;
    if s.refs > l.max_refs {
        Err(limit("refs"))
    } else {
        Ok(())
    }
}
fn num(t: &toml::Value, k: &str, d: u32) -> Result<u32> {
    match t.get(k).and_then(toml::Value::as_integer) {
        Some(n) => u32::try_from(n).map_err(|_| KioError::schema("gc retention must be uint32")),
        None => Ok(d),
    }
}
fn validate_commit_links(commits: &HashMap<String, CommitObject>) -> Result<()> {
    if commits.values().any(|commit| {
        commit
            .parents
            .iter()
            .any(|parent| !commits.contains_key(parent))
    }) {
        Err(corrupt("commit parent is missing"))
    } else {
        Ok(())
    }
}

fn validate_receipt_links(
    receipts: &HashMap<String, String>,
    commits: &HashMap<String, CommitObject>,
) -> Result<()> {
    for (commit_hash, tree_hash) in receipts {
        let commit = commits
            .get(commit_hash)
            .ok_or_else(|| corrupt("shallow receipt commit is missing"))?;
        if &commit.tree != tree_hash
            || !matches!(commit.commit_type, CommitType::Auto | CommitType::Repaired)
        {
            return Err(corrupt("invalid shallow receipt relation"));
        }
    }
    Ok(())
}

fn graph_step(stats: &mut GcPlanStats, limits: &GcPlanLimits) -> Result<()> {
    stats.graph_steps = checked(stats.graph_steps, 1, "graph steps")?;
    if stats.graph_steps > limits.max_graph_steps {
        Err(limit("graph steps"))
    } else {
        Ok(())
    }
}

fn closure(
    start: &str,
    all: &HashMap<String, CommitObject>,
    stats: &mut GcPlanStats,
    limits: &GcPlanLimits,
) -> Result<HashSet<String>> {
    let mut o = HashSet::new();
    let mut q: Vec<String> = vec![start.into()];
    while let Some(h) = q.pop() {
        graph_step(stats, limits)?;
        if o.insert(h.clone()) {
            if let Some(c) = all.get(&h) {
                q.extend(c.parents.iter().cloned())
            }
        }
    }
    Ok(o)
}

fn fractional_digits(timestamp: &str) -> &str {
    timestamp
        .strip_suffix('Z')
        .and_then(|body| body.split_once('.').map(|(_, fraction)| fraction))
        .unwrap_or("")
}

fn is_canonical_utc_timestamp(timestamp: &str) -> bool {
    let Some(seconds) = parse_utc_seconds(timestamp) else {
        return false;
    };
    let seconds_shape = timestamp
        .strip_suffix('Z')
        .and_then(|body| body.split_once('.').map(|(whole, _)| format!("{whole}Z")))
        .unwrap_or_else(|| timestamp.to_owned());
    seconds_shape == format_utc_seconds(seconds)
}

fn compare_fractional(left: &str, right: &str) -> Ordering {
    let width = left.len().max(right.len());
    (0..width)
        .map(|index| {
            let left = left.as_bytes().get(index).copied().unwrap_or(b'0');
            let right = right.as_bytes().get(index).copied().unwrap_or(b'0');
            left.cmp(&right)
        })
        .find(|ordering| *ordering != Ordering::Equal)
        .unwrap_or(Ordering::Equal)
}

fn compare_timestamps(left: &str, right: &str) -> Ordering {
    let left_seconds = parse_utc_seconds(left).unwrap_or(i64::MIN);
    let right_seconds = parse_utc_seconds(right).unwrap_or(i64::MIN);
    left_seconds
        .cmp(&right_seconds)
        .then_with(|| compare_fractional(fractional_digits(left), fractional_digits(right)))
}

fn newer_first(left: (&CommitObject, &str), right: (&CommitObject, &str)) -> Ordering {
    compare_timestamps(&right.0.created_at, &left.0.created_at).then_with(|| left.1.cmp(right.1))
}

fn timestamp_is_after_seconds(timestamp: &str, seconds: i64) -> bool {
    let timestamp_seconds = parse_utc_seconds(timestamp).unwrap_or(i64::MAX);
    timestamp_seconds > seconds
        || timestamp_seconds == seconds
            && fractional_digits(timestamp)
                .bytes()
                .any(|digit| digit != b'0')
}

fn age_is_less_than(timestamp: &str, now: i64, horizon_seconds: i64) -> bool {
    let timestamp_seconds = parse_utc_seconds(timestamp).unwrap_or(i64::MIN);
    let age_seconds = now.saturating_sub(timestamp_seconds);
    age_seconds < horizon_seconds
        || age_seconds == horizon_seconds
            && fractional_digits(timestamp)
                .bytes()
                .any(|digit| digit != b'0')
}
fn auto_retained(
    c: &HashSet<String>,
    all: &HashMap<String, CommitObject>,
    now: i64,
    p: &GcPolicy,
    ex: &mut BTreeMap<String, u64>,
) -> HashSet<String> {
    let mut k = HashSet::new();
    let mut b = HashMap::new();
    for h in c {
        let x = &all[h];
        let Some(t) = parse_utc_seconds(&x.created_at) else {
            continue;
        };
        if timestamp_is_after_seconds(&x.created_at, now) {
            k.insert(h.clone());
            inc(ex, "future_timestamp");
            continue;
        }
        let (tier, key, why) =
            if age_is_less_than(&x.created_at, now, (p.keep_last_hours as i64) * 3600) {
                (0, 0, "retained_recent")
            } else if age_is_less_than(&x.created_at, now, (p.keep_hourly_days as i64) * 86400) {
                (1, t.div_euclid(3600), "retained_hourly")
            } else if age_is_less_than(&x.created_at, now, (p.keep_daily_weeks as i64) * 604800) {
                (2, t.div_euclid(86400), "retained_daily")
            } else if age_is_less_than(&x.created_at, now, (p.keep_weekly_months as i64) * 2592000)
            {
                (
                    3,
                    (t.div_euclid(86400) + 3).div_euclid(7),
                    "retained_weekly",
                )
            } else {
                continue;
            };
        if tier == 0 {
            k.insert(h.clone());
            inc(ex, why)
        } else if b
            .get(&(tier, key))
            .map(|old: &String| newer_first((x, h), (&all[old], old)) == Ordering::Less)
            .unwrap_or(true)
        {
            b.insert((tier, key), h.clone());
        }
    }
    for ((tier, _), h) in b {
        k.insert(h);
        inc(
            ex,
            match tier {
                1 => "retained_hourly",
                2 => "retained_daily",
                _ => "retained_weekly",
            },
        );
    }
    k
}
fn inc(x: &mut BTreeMap<String, u64>, n: &str) {
    *x.entry(n.into()).or_default() += 1
}
fn corrupt(m: &str) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        m,
        json!({}),
        ExitCode::PermanentFailure,
    )
}
fn limit(w: &str) -> KioError {
    KioError::new(
        "KIO-E-GC-PLAN-LIMIT-001",
        format!("GC planning limit exceeded: {w}"),
        json!({"limit":w}),
        ExitCode::PermanentFailure,
    )
}
fn ioerr(e: std::io::Error, p: impl AsRef<Path>) -> KioError {
    let kind = match e.kind() {
        std::io::ErrorKind::NotFound => "not_found",
        std::io::ErrorKind::PermissionDenied => "permission_denied",
        std::io::ErrorKind::AlreadyExists => "already_exists",
        std::io::ErrorKind::InvalidData => "invalid_data",
        _ => "other",
    };
    KioError::new(
        "KIO-E-STORE-IO-001",
        e.to_string(),
        json!({ "path": p.as_ref(), "io_error_kind": kind }),
        ExitCode::Failure,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dag::CommitStats;
    use crate::scope::Repository;

    fn commit(created_at: &str) -> CommitObject {
        CommitObject::new(
            format!("sha256:{}", "a".repeat(64)),
            vec![],
            created_at.into(),
            "x".into(),
            format!("sha256:{}", "b".repeat(64)),
            CommitStats {
                files_added: 0,
                files_modified: 0,
                files_deleted: 0,
            },
            CommitType::Auto,
        )
        .unwrap()
    }

    #[test]
    fn retention_is_deterministic_at_bucket_boundary() {
        let now = parse_utc_seconds("2026-01-02T00:00:00Z").unwrap();
        let a = format!("sha256:{}", "a".repeat(64));
        let b = format!("sha256:{}", "b".repeat(64));
        let mut all = HashMap::new();
        all.insert(a.clone(), commit("2026-01-01T00:00:00Z"));
        all.insert(b.clone(), commit("2026-01-01T00:00:00Z"));
        let mut ex = BTreeMap::new();
        assert_eq!(
            auto_retained(
                &HashSet::from([a.clone(), b]),
                &all,
                now,
                &GcPolicy::default(),
                &mut ex
            ),
            HashSet::from([a])
        );
    }

    #[cfg(unix)]
    #[test]
    fn capability_reader_rejects_symlink_and_hardlink() {
        use std::os::unix::fs::symlink;
        let tmp = tempfile::tempdir().unwrap();
        let dir = cap_fs::open_ambient_dir(tmp.path(), ambient_authority()).unwrap();
        std::fs::write(tmp.path().join("file"), b"ok").unwrap();
        symlink("file", tmp.path().join("link")).unwrap();
        assert!(read_regular(&dir, "link", 16).is_err());
        std::fs::hard_link(tmp.path().join("file"), tmp.path().join("other")).unwrap();
        assert!(read_regular(&dir, "file", 16).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn stability_check_rejects_same_content_identity_replacement() {
        let tmp = tempfile::tempdir().unwrap();
        Repository::init(tmp.path()).unwrap();
        let root = tmp.path().canonicalize().unwrap();
        let head = root.join(".kio/HEAD");
        let replacement = root.join(".kio/HEAD.replacement");
        let bytes = std::fs::read(&head).unwrap();
        let planner = GcPlanner::bind(&root).unwrap();

        let error = planner
            .plan_at_inner(0, || {
                std::fs::write(&replacement, bytes).unwrap();
                std::fs::rename(&replacement, &head).unwrap();
            })
            .unwrap_err();

        assert_eq!(error.error_code(), "KIO-E-STORE-CORRUPT-001");
    }
}
