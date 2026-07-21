//! Bounded object-store verification for `repair --verify-objects`.

use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};

use kcs_core::cas::{
    hash_bytes, is_hash, read_bounded_regular_file, AccountedReadError, ChunkObject,
    ContentObjectKind, ObjectKind, ObjectStore, MAX_RAW_OBJECT_BYTES,
};
use kcs_core::dag::{CommitObject, CommitType, TreeObject};
use kcs_core::purge::{
    canonical_final_event, CanonicalFinalEvent, EventKind, LifecycleEvent, PurgeState,
    TombstoneMode, MAX_PURGE_RECORD_BYTES,
};
use kcs_core::scope::{now_utc_seconds, Repository};
use kcs_core::{KcsError, Result};
use kcs_pipeline::markdownize::{
    load_validated_normalized_instance, normalized_instance_read_budget,
    NormalizedInstanceIdentity, ValidatedNormalizedInstance,
};
use serde::Serialize;

use crate::*;

const MAX_OBJECTS: usize = 1_000_000;
const MAX_VERIFIED_BYTES: u64 = 1024 * 1024 * 1024 * 1024;
const MAX_FINDINGS: usize = 1_024;
const MAX_AFFECTED_COMMITS: usize = 4_096;

pub(super) fn run_evidence(args: UnsupportedArgs) -> Result<Value> {
    let (pointer_operand, strict) = parse_evidence_verify_args(without_json(args.args))?;
    let raw = read_pointer_input(vec![pointer_operand])?;
    if raw.starts_with("sha256:") || parse_object_uri(&raw)?.is_some() {
        return Err(KcsError::invalid_usage(
            "evidence verify accepts only a pointer URI, inline JSON, or '-' stdin",
        ));
    }
    let pointer = parse_pointer_text(&raw)?;
    let mut output = verify_pointer_for_cli(&pointer)?;
    if strict && output.get("status").and_then(Value::as_str) != Some("alive") {
        if let Some(object) = output.as_object_mut() {
            object.insert("__exit_code".to_owned(), json!(4));
        }
    }
    Ok(output)
}

fn parse_evidence_verify_args(args: Vec<String>) -> Result<(String, bool)> {
    let mut args = args.into_iter();
    if args.next().as_deref() != Some("verify") {
        return Err(KcsError::invalid_usage(
            "evidence currently supports `evidence verify <pointer> [--strict]`",
        ));
    }
    let mut pointer = None;
    let mut strict = false;
    for arg in args {
        let (flag, inline) = split_flag_value(&arg);
        match flag {
            "--strict" if !strict => {
                reject_inline_value(flag, inline)?;
                strict = true;
            }
            "--strict" => {
                return Err(KcsError::invalid_usage(
                    "evidence verify accepts --strict only once",
                ))
            }
            "--batch" => {
                return Err(KcsError::invalid_usage(
                    "evidence verify --batch is outside the MVP",
                ))
            }
            value if value.starts_with('-') && value != "-" => {
                return Err(KcsError::invalid_usage(format!(
                    "unknown evidence verify flag: {value}"
                )))
            }
            value if pointer.is_none() => pointer = Some(value.to_owned()),
            _ => {
                return Err(KcsError::invalid_usage(
                    "evidence verify accepts exactly one pointer",
                ))
            }
        }
    }
    pointer
        .map(|pointer| (pointer, strict))
        .ok_or_else(|| KcsError::invalid_usage("evidence verify requires a pointer"))
}

/// Read-only, content-free Evidence liveness check (08 §4.3). This deliberately
/// does not call `resolve_pointer_for_cli`: open/view may materialize an open-cache
/// file and return chunk text, both forbidden for verify.
fn verify_pointer_for_cli(pointer: &EvidencePointer) -> Result<Value> {
    let target = resolve_scope_target(&pointer.scope_id, pointer.scope_path.as_deref())?;
    // §I checkpoint 1 (LC53). Evidence verify's whole response IS existence
    // information (08 §4.3 — it never returns body), so checkpoint 2 below
    // (LC54/LC55) gates every return point, not only a single "success" path.
    let checkpoint = ReadBarrierCheckpoint::open(&target.kcs_dir)?;
    // LC45 (item 2): a separate check from §I's checkpoint — see
    // `check_index_generation_current`'s doc comment.
    check_index_generation_current(&target.kcs_dir)?;
    let repo = Repository::open(&target.repo_root)?;
    let commit = match repo.read_commit(&pointer.commit) {
        Ok(commit) => commit,
        Err(error) if is_store_not_found(&error) => {
            return Err(unresolvable_commit_pointer_error(pointer));
        }
        Err(error) => return Err(error),
    };
    let (commit_shallow, entry_gen) = match repo.read_tree(&commit.tree) {
        Ok(tree) => {
            let Some(entry) = tree
                .entries
                .iter()
                .find(|entry| entry.raw_hash == pointer.raw_hash)
            else {
                if let Some(tombstone) = read_tombstone(&target, &pointer.raw_hash)? {
                    return checkpoint.finish(tombstoned_verify_output(tombstone));
                }
                return checkpoint.finish(not_found_verify_output(&target, &pointer.raw_hash));
            };
            let entry_gen = match &entry.normalize {
                Some(normalize) => {
                    if normalize.tool_profile_hash != pointer.tool_profile_hash {
                        return Err(invalid_pointer_identity_error(pointer));
                    }
                    Some(normalize.gen)
                }
                None => None,
            };
            (false, entry_gen)
        }
        Err(error) if is_store_not_found(&error) => (true, None),
        Err(error) => return Err(error),
    };

    if let Some(tombstone) = read_tombstone(&target, &pointer.raw_hash)? {
        return checkpoint.finish(tombstoned_verify_output(tombstone));
    }
    if PurgeState::new(&target.kcs_dir).barrier_blocks(&pointer.raw_hash)? {
        return checkpoint.finish(not_found_verify_output(&target, &pointer.raw_hash));
    }

    let store = ObjectStore::new(&target.kcs_dir);
    match store.inspect_object(ObjectKind::Raw, &pointer.raw_hash) {
        Ok(_) => {}
        Err(error) if is_store_not_found(&error) => {
            return checkpoint.finish(not_found_verify_output(&target, &pointer.raw_hash));
        }
        Err(error) => return Err(error),
    }
    let chunk = match store.read_chunk(&pointer.chunk_hash) {
        Ok(chunk) => chunk,
        Err(error) if is_store_not_found(&error) => {
            return Err(KcsError::new(
                "KCS-E-EVIDENCE-RETARGET-REQUIRED-001",
                "chunk object is unavailable for this tool profile; retarget required (08 §5)",
                json!({
                    "chunk_hash": pointer.chunk_hash,
                    "tool_profile_hash": pointer.tool_profile_hash,
                    "raw_hash": pointer.raw_hash,
                }),
                ExitCode::IncompatibleProfile,
            ));
        }
        Err(error) => return Err(error),
    };
    if chunk.raw_hash != pointer.raw_hash
        || chunk.tool_profile_hash != pointer.tool_profile_hash
        || entry_gen.is_some_and(|gen| chunk.gen != gen)
    {
        return Err(invalid_pointer_identity_error(pointer));
    }
    if let Some(tombstone) = read_tombstone(&target, &pointer.raw_hash)? {
        return checkpoint.finish(tombstoned_verify_output(tombstone));
    }
    if PurgeState::new(&target.kcs_dir).barrier_blocks(&pointer.raw_hash)? {
        return checkpoint.finish(not_found_verify_output(&target, &pointer.raw_hash));
    }

    checkpoint.finish(json!({
        "status": "alive",
        "details": {
            "scope_id": pointer.scope_id,
            "scope_path": target.kcs_dir.display().to_string(),
            "commit": pointer.commit,
            "raw_hash": pointer.raw_hash,
            "tool_profile_hash": pointer.tool_profile_hash,
            "chunk_hash": pointer.chunk_hash,
            "commit_shallow": commit_shallow,
        }
    }))
}

fn tombstoned_verify_output(mut tombstone: Value) -> Value {
    if let Some(object) = tombstone.as_object_mut() {
        object.remove("status");
    }
    json!({
        "status": "tombstoned",
        "error_code": "KCS-E-PURGE-TOMBSTONED-001",
        "details": tombstone,
    })
}

fn not_found_verify_output(target: &ScopeTarget, raw_hash: &str) -> Value {
    json!({
        "status": "not_found",
        "error_code": "KCS-E-PURGE-NOT-FOUND-001",
        "details": {
            "raw_hash": raw_hash,
            "scope_path": target.kcs_dir.display().to_string(),
        }
    })
}

#[derive(Debug, Default, Serialize)]
pub struct CheckedObjects {
    pub raw: u64,
    pub chunks: u64,
    pub trees: u64,
    pub commits: u64,
    pub normalized_instances: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ObjectFinding {
    pub kind: String,
    pub object_hash: String,
    pub reason: String,
    pub affected_commits: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct VerifyObjectsReport {
    pub status: String,
    pub checked: CheckedObjects,
    pub repaired_raw_count: u64,
    pub repaired_commit_hash: Option<String>,
    pub dead_by_tombstone_count: u64,
    pub dead_by_erase_receipt_count: u64,
    pub remaining_findings: Vec<ObjectFinding>,
    pub findings_truncated: bool,
    pub external_pointers_may_be_affected: bool,
    #[serde(skip)]
    #[cfg_attr(not(test), allow(dead_code))]
    verified_bytes: u64,
    #[serde(skip)]
    #[cfg_attr(not(test), allow(dead_code))]
    inventoried_objects: usize,
}

impl VerifyObjectsReport {
    #[must_use]
    pub fn has_remaining_findings(&self) -> bool {
        !self.remaining_findings.is_empty() || self.findings_truncated
    }
}

pub fn verify_objects(repo: &Repository) -> Result<VerifyObjectsReport> {
    verify_objects_with_limits(repo, VerifyLimits::default())
}

#[derive(Debug, Clone, Copy)]
struct VerifyLimits {
    max_objects: usize,
    max_verified_bytes: u64,
}

impl Default for VerifyLimits {
    fn default() -> Self {
        Self {
            max_objects: MAX_OBJECTS,
            max_verified_bytes: MAX_VERIFIED_BYTES,
        }
    }
}

fn verify_objects_with_limits(
    repo: &Repository,
    limits: VerifyLimits,
) -> Result<VerifyObjectsReport> {
    let store = ObjectStore::new(repo.kcs_dir());
    let purge = PurgeState::new(repo.kcs_dir());
    let invocation_time = now_utc_seconds();
    let mut state = State {
        max_objects: limits.max_objects,
        max_verified_bytes: limits.max_verified_bytes,
        ..State::default()
    };
    match purge.read_journal() {
        Ok(Some(_)) => {
            state.finding("purge_incomplete", "", "active purge journal", &[]);
            return Ok(finish_report(state, 0, None));
        }
        Ok(None) => {}
        Err(error) => {
            state.finding("purge_journal_corrupt", "", &error.to_string(), &[]);
            return Ok(finish_report(state, 0, None));
        }
    }
    let mut repairs_allowed = true;

    let raw_hashes = inventory(repo.kcs_dir(), "raw", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let chunk_hashes = inventory(repo.kcs_dir(), "chunks", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let tree_hashes = inventory(repo.kcs_dir(), "trees", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let commit_hashes = inventory(repo.kcs_dir(), "commits", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let tombstone_hashes = marker_inventory(repo.kcs_dir(), "tombstones", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let receipt_hashes = marker_inventory(repo.kcs_dir(), "purge/erase-receipts", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }

    let mut corrupt_raws = BTreeMap::<String, String>::new();
    let mut verified_raws = BTreeSet::<String>::new();
    for hash in &raw_hashes {
        match store.inspect_object_accounted(ObjectKind::Raw, hash) {
            Ok(metadata) => {
                state.checked.raw += 1;
                verified_raws.insert(hash.clone());
                state.add_bytes(metadata.size_bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
            }
            Err(failure) => {
                state.add_bytes(failure.consumed_bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
                corrupt_raws.insert(hash.clone(), failure.error.to_string());
            }
        }
    }

    let mut chunks = BTreeMap::<String, ChunkObject>::new();
    for hash in &chunk_hashes {
        match store.read_chunk_accounted(hash) {
            Ok((chunk, bytes)) => {
                state.checked.chunks += 1;
                state.add_bytes(bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
                chunks.insert(hash.clone(), chunk);
            }
            Err(failure) => {
                state.add_bytes(failure.consumed_bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
                state.finding("chunk_corrupt", hash, &failure.error.to_string(), &[]);
            }
        }
    }

    let mut trees = BTreeMap::<String, TreeObject>::new();
    for hash in &tree_hashes {
        match store.read_object_accounted(ObjectKind::Tree, hash) {
            Ok((object, verified_bytes)) => {
                state.add_bytes(verified_bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
                match serde_json::from_slice::<TreeObject>(&object.bytes)
                    .map_err(|error| KcsError::schema(error.to_string()))
                    .and_then(|tree| {
                        tree.validate()?;
                        Ok(tree)
                    }) {
                    Ok(tree) => {
                        state.checked.trees += 1;
                        trees.insert(hash.clone(), tree);
                    }
                    Err(error) => state.finding("tree_corrupt", hash, &error.to_string(), &[]),
                }
            }
            Err(failure) => {
                state.add_bytes(failure.consumed_bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
                state.finding("tree_corrupt", hash, &failure.error.to_string(), &[]);
            }
        }
    }

    let mut commits = BTreeMap::<String, CommitObject>::new();
    for hash in &commit_hashes {
        match store.read_object_accounted(ObjectKind::Commit, hash) {
            Ok((object, verified_bytes)) => {
                state.add_bytes(verified_bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
                match serde_json::from_slice::<CommitObject>(&object.bytes)
                    .map_err(|error| KcsError::schema(error.to_string()))
                    .and_then(|commit| {
                        commit.validate()?;
                        Ok(commit)
                    }) {
                    Ok(commit) => {
                        state.checked.commits += 1;
                        commits.insert(hash.clone(), commit);
                    }
                    Err(error) => state.finding("commit_corrupt", hash, &error.to_string(), &[]),
                }
            }
            Err(failure) => {
                state.add_bytes(failure.consumed_bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
                state.finding("commit_corrupt", hash, &failure.error.to_string(), &[]);
            }
        }
    }

    let reachable = reachable_commits(repo, &commits, &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    let mut raw_affected = BTreeMap::<String, BTreeSet<String>>::new();
    let mut normalized = BTreeMap::<(String, String, u64), ValidatedNormalizedInstance>::new();
    let mut prepared_references = BTreeSet::<String>::new();
    let mut raw_substitutable_prepared = BTreeSet::<String>::new();
    let mut image_references = BTreeSet::<String>::new();
    let mut prepared_affected = BTreeMap::<String, BTreeSet<String>>::new();
    let mut image_affected = BTreeMap::<String, BTreeSet<String>>::new();
    let mut recovery_paths = BTreeMap::<String, Vec<PathBuf>>::new();
    for commit_hash in &reachable {
        let Some(commit) = commits.get(commit_hash) else {
            continue;
        };
        let Some(tree) = trees.get(&commit.tree) else {
            continue;
        };
        for entry in &tree.entries {
            let affected = raw_affected.entry(entry.raw_hash.clone()).or_default();
            if affected.len() < MAX_AFFECTED_COMMITS {
                affected.insert(commit_hash.clone());
            }
            let path = repo.root().join(&entry.path);
            let paths = recovery_paths.entry(entry.raw_hash.clone()).or_default();
            if paths.len() < MAX_AFFECTED_COMMITS && !paths.contains(&path) {
                paths.push(path);
            }
        }
    }
    let dead_raws = raw_affected
        .keys()
        .filter(|raw_hash| {
            valid_dead_terminal(
                &verified_raws,
                &purge,
                raw_hash,
                &commits,
                &trees,
                &reachable,
                &invocation_time,
            )
        })
        .cloned()
        .collect::<BTreeSet<_>>();
    for commit_hash in &reachable {
        let Some(commit) = commits.get(commit_hash) else {
            continue;
        };
        let Some(tree) = trees.get(&commit.tree) else {
            state.finding(
                "missing_tree",
                &commit.tree,
                "commit references a missing tree",
                std::slice::from_ref(commit_hash),
            );
            continue;
        };
        for entry in &tree.entries {
            if dead_raws.contains(&entry.raw_hash) {
                continue;
            }
            if let Some(reference) = &entry.normalize {
                let key = (
                    entry.raw_hash.clone(),
                    reference.tool_profile_hash.clone(),
                    reference.gen,
                );
                let lookup_key = key.clone();
                if let std::collections::btree_map::Entry::Vacant(slot) = normalized.entry(key) {
                    state.count_object();
                    if state.exceeded_bounds {
                        return Ok(finish_limit_report(state));
                    }
                    let key = slot.key();
                    let identity = NormalizedInstanceIdentity {
                        raw_hash: key.0.clone(),
                        tool_profile_hash: key.1.clone(),
                        gen: key.2,
                    };
                    let budget = match normalized_instance_read_budget(
                        repo.kcs_dir(),
                        &identity.raw_hash,
                        &identity.tool_profile_hash,
                        identity.gen,
                    ) {
                        Ok(bytes) => bytes,
                        Err(error) => {
                            state.finding(
                                "normalized_corrupt",
                                &entry.raw_hash,
                                &error.to_string(),
                                std::slice::from_ref(commit_hash),
                            );
                            continue;
                        }
                    };
                    state.add_bytes(budget);
                    if state.exceeded_bounds {
                        return Ok(finish_limit_report(state));
                    }
                    match load_validated_normalized_instance(
                        repo.kcs_dir(),
                        &identity.raw_hash,
                        &identity.tool_profile_hash,
                        identity.gen,
                    ) {
                        Ok(instance) => {
                            state.checked.normalized_instances += 1;
                            slot.insert(instance);
                        }
                        Err(error) => state.finding(
                            "normalized_corrupt",
                            &entry.raw_hash,
                            &error.to_string(),
                            std::slice::from_ref(commit_hash),
                        ),
                    }
                }
                if let Some(instance) = normalized.get(&lookup_key) {
                    for manifest_entry in &instance.manifest.units {
                        prepared_references.insert(manifest_entry.prepared_hash.clone());
                        let affected = prepared_affected
                            .entry(manifest_entry.prepared_hash.clone())
                            .or_default();
                        if affected.len() < MAX_AFFECTED_COMMITS {
                            affected.insert(commit_hash.clone());
                        }
                        if manifest_entry.prepared_hash == instance.manifest.raw_hash {
                            raw_substitutable_prepared.insert(manifest_entry.prepared_hash.clone());
                        }
                    }
                    for unit in &instance.units {
                        let mut unit_images = BTreeSet::new();
                        if let Err(reason) = collect_unit_image_references(
                            &unit.metadata,
                            &unit.markdown,
                            &mut unit_images,
                        ) {
                            state.finding(
                                "normalized_corrupt",
                                &entry.raw_hash,
                                &reason,
                                std::slice::from_ref(commit_hash),
                            );
                        }
                        for hash in unit_images {
                            image_references.insert(hash.clone());
                            let affected = image_affected.entry(hash).or_default();
                            if affected.len() < MAX_AFFECTED_COMMITS {
                                affected.insert(commit_hash.clone());
                            }
                        }
                    }
                }
            }
        }
    }

    for prepared_hash in prepared_references {
        state.count_object();
        if state.exceeded_bounds {
            return Ok(finish_limit_report(state));
        }
        match verify_prepared_reference(
            &store,
            &prepared_hash,
            raw_substitutable_prepared.contains(&prepared_hash)
                && verified_raws.contains(&prepared_hash),
        ) {
            Ok(bytes) => state.add_bytes(bytes),
            Err(failure) => {
                state.add_bytes(failure.consumed_bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
                let affected = prepared_affected
                    .get(&prepared_hash)
                    .map_or_else(Vec::new, |commits| commits.iter().cloned().collect());
                state.finding(
                    "prepared_corrupt",
                    &prepared_hash,
                    &failure.error.to_string(),
                    &affected,
                )
            }
        }
        if state.exceeded_bounds {
            return Ok(finish_limit_report(state));
        }
    }
    for image_hash in image_references {
        state.count_object();
        if state.exceeded_bounds {
            return Ok(finish_limit_report(state));
        }
        match store.inspect_content_accounted(ContentObjectKind::Image, &image_hash) {
            Ok(metadata) => state.add_bytes(metadata.size_bytes),
            Err(failure) => {
                state.add_bytes(failure.consumed_bytes);
                if state.exceeded_bounds {
                    return Ok(finish_limit_report(state));
                }
                let affected = image_affected
                    .get(&image_hash)
                    .map_or_else(Vec::new, |commits| commits.iter().cloned().collect());
                state.finding(
                    "image_corrupt",
                    &image_hash,
                    &failure.error.to_string(),
                    &affected,
                )
            }
        }
        if state.exceeded_bounds {
            return Ok(finish_limit_report(state));
        }
    }

    let marker_hashes = tombstone_hashes
        .union(&receipt_hashes)
        .cloned()
        .collect::<BTreeSet<_>>();
    // (raw_hash, marker_kind, purge/erase event `in_commit`) queued for a
    // `retired` append once the corresponding physical-object pass completes
    // (LC27/LC35: verified raw + a ref-reachable, ancestor-respecting
    // republication commit of the canonical purged/erased event).
    let mut retirements_to_backfill = Vec::<(String, TombstoneMode, String)>::new();
    for raw_hash in marker_hashes {
        if raw_affected.contains_key(&raw_hash) {
            continue;
        }
        let lookup = canonical_lookup(
            &purge,
            &raw_hash,
            &commits,
            &trees,
            &reachable,
            &invocation_time,
        );
        if let Some(reason) = lookup.tombstone_error {
            state.finding("tombstone_corrupt", &raw_hash, &reason, &[]);
        }
        if let Some(reason) = lookup.receipt_error {
            state.finding("erase_receipt_corrupt", &raw_hash, &reason, &[]);
        }
        let Some(canonical) = lookup.canonical else {
            continue;
        };
        let raw_alive = verified_raws.contains(&raw_hash);
        match (canonical.event.kind, raw_alive) {
            // LC34/F34: canonical = retired is normal coexistence (resurrection).
            (EventKind::Retired, _) => {}
            (EventKind::Purged, false) => state.dead_by_tombstone_count += 1,
            (EventKind::Erased, false) => state.dead_by_erase_receipt_count += 1,
            (EventKind::Purged | EventKind::Erased, true) => {
                // LC35/LC36 (§F): verified raw + canonical purged/erased.
                // Backfill `retired` only when a ref-reachable, ancestor-
                // respecting republication commit exists; otherwise this is
                // an incomplete purge (exit 3), not a corruption, and is
                // never silently "fixed" by resurrecting the tombstone.
                if repairs_allowed && !state.exceeded_bounds {
                    match find_republication_commit(&canonical.event.in_commit, &commits, &reachable)
                    {
                        Some(republication_commit) => retirements_to_backfill.push((
                            raw_hash.clone(),
                            canonical.marker_kind,
                            republication_commit,
                        )),
                        None => state.finding(
                            "purge_incomplete",
                            &raw_hash,
                            "verified raw exists but no causal republication commit was found (09 §5.3: re-run kcs purge --raw-hash to complete idempotently)",
                            &[],
                        ),
                    }
                } else {
                    state.finding(
                        "purge_incomplete",
                        &raw_hash,
                        "resurrection backfill suppressed while purge state is active or corrupt",
                        &[],
                    );
                }
            }
        }
    }

    repairs_allowed &= !state.exceeded_bounds;
    let mut staged_raws = Vec::<(String, Vec<u8>)>::new();
    for (raw_hash, affected) in &raw_affected {
        let affected = affected
            .iter()
            .take(MAX_AFFECTED_COMMITS)
            .cloned()
            .collect::<Vec<_>>();
        if verified_raws.contains(raw_hash) {
            // §F (LC34-LC38): canonical final event basis, not marker-pair
            // presence — a tombstone and erase receipt coexisting is not
            // itself a finding (§C computes canonical over both).
            let lookup = canonical_lookup(
                &purge,
                raw_hash,
                &commits,
                &trees,
                &reachable,
                &invocation_time,
            );
            if let Some(reason) = lookup.tombstone_error {
                state.finding("tombstone_corrupt", raw_hash, &reason, &affected);
            }
            if let Some(reason) = lookup.receipt_error {
                state.finding("erase_receipt_corrupt", raw_hash, &reason, &affected);
            }
            if let Some(canonical) = lookup.canonical {
                match canonical.event.kind {
                    EventKind::Retired => {} // LC34: normal coexistence.
                    EventKind::Purged | EventKind::Erased => {
                        if repairs_allowed && !state.exceeded_bounds {
                            match find_republication_commit(
                                &canonical.event.in_commit,
                                &commits,
                                &reachable,
                            ) {
                                Some(republication_commit) => retirements_to_backfill.push((
                                    raw_hash.clone(),
                                    canonical.marker_kind,
                                    republication_commit,
                                )),
                                None => state.finding(
                                    "purge_incomplete",
                                    raw_hash,
                                    "verified raw exists but no causal republication commit was found (09 §5.3: re-run kcs purge --raw-hash to complete idempotently)",
                                    &affected,
                                ),
                            }
                        } else {
                            state.finding(
                                "purge_incomplete",
                                raw_hash,
                                "resurrection backfill suppressed while purge state is active or corrupt",
                                &affected,
                            );
                        }
                    }
                }
            }
            continue;
        }
        // Raw is *not* verified-present: a canonical `purged`/`erased` marker
        // is the normal, explained dead terminal (10 §7.5.1). A canonical
        // `retired` here means the marker asserts the raw should be alive
        // again but it is missing — that is not a valid explanation (LC13's
        // resolver-side rule is the same corruption class), so it falls
        // through to the recovery/`missing_raw` path below like an unmarked
        // absence would.
        let lookup = canonical_lookup(
            &purge,
            raw_hash,
            &commits,
            &trees,
            &reachable,
            &invocation_time,
        );
        if let Some(reason) = lookup.tombstone_error {
            state.finding("tombstone_corrupt", raw_hash, &reason, &affected);
            continue;
        }
        if let Some(reason) = lookup.receipt_error {
            state.finding("erase_receipt_corrupt", raw_hash, &reason, &affected);
            continue;
        }
        match lookup.canonical.map(|canonical| canonical.event.kind) {
            Some(EventKind::Purged) => {
                state.dead_by_tombstone_count += 1;
                continue;
            }
            Some(EventKind::Erased) => {
                state.dead_by_erase_receipt_count += 1;
                continue;
            }
            Some(EventKind::Retired) | None => {}
        }
        if !repairs_allowed {
            state.finding(
                "missing_raw",
                raw_hash,
                "raw recovery suppressed while purge state is active or corrupt",
                &affected,
            );
            continue;
        }
        let mut recovered = false;
        for path in recovery_paths.get(raw_hash).into_iter().flatten() {
            let remaining = state
                .max_verified_bytes
                .saturating_sub(state.verified_bytes);
            match recover_raw(path, raw_hash, remaining)? {
                RawRecovery::Missing(bytes) => {
                    state.add_bytes(bytes);
                    if state.exceeded_bounds {
                        break;
                    }
                }
                RawRecovery::Candidate(bytes) => {
                    state.add_bytes(bytes.len() as u64);
                    if state.exceeded_bounds {
                        break;
                    }
                    corrupt_raws.remove(raw_hash);
                    staged_raws.push((raw_hash.clone(), bytes));
                    recovered = true;
                    break;
                }
                RawRecovery::LimitExceeded => {
                    state.exceeded_bounds = true;
                    break;
                }
            }
        }
        if !recovered && !state.exceeded_bounds {
            if let Some(reason) = corrupt_raws.remove(raw_hash) {
                state.finding("raw_corrupt", raw_hash, &reason, &affected);
            } else {
                state.finding(
                    "missing_raw",
                    raw_hash,
                    "reachable tree references an unmarked missing raw object",
                    &affected,
                );
            }
        }
    }
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    for (raw_hash, reason) in corrupt_raws {
        state.finding("raw_corrupt", &raw_hash, &reason, &[]);
    }

    for (chunk_hash, chunk) in &chunks {
        if dead_raws.contains(&chunk.raw_hash) {
            continue;
        }
        let key = (
            chunk.raw_hash.clone(),
            chunk.tool_profile_hash.clone(),
            chunk.gen,
        );
        let Some(instance) = normalized.get(&key) else {
            state.finding(
                "chunk_normalized_missing",
                chunk_hash,
                "chunk has no reachable normalized instance",
                &[],
            );
            continue;
        };
        let Some(unit) = instance
            .units
            .iter()
            .find(|unit| unit.unit_key == chunk.unit_key)
        else {
            state.finding(
                "chunk_unit_missing",
                chunk_hash,
                "chunk unit_key is absent from normalized instance",
                &[],
            );
            continue;
        };
        // byte_start/byte_end are unit-local UTF-8 byte offsets (03 §8.1), always
        // present and ordered by construction — `ChunkObject::validate()` already
        // rejected any object with byte_start > byte_end before it reached this
        // map (cas.rs `read_chunk_path_accounted`). `str::get` on a byte range
        // additionally guards against an out-of-bounds span or one that doesn't
        // land on a UTF-8 char boundary — either is exact-span corruption
        // surfaced as a finding here, not a panic.
        let start = chunk.byte_start as usize;
        let end = chunk.byte_end as usize;
        match unit.markdown.get(start..end) {
            Some(exact)
                if exact == chunk.text && hash_bytes(exact.as_bytes()) == chunk.text_hash => {}
            _ => {
                state.finding(
                    "chunk_span_mismatch",
                    chunk_hash,
                    "chunk text does not match normalized span",
                    &[],
                );
            }
        }
    }

    for (raw_hash, bytes) in &staged_raws {
        store.repair_raw(raw_hash, bytes)?;
    }
    // LC27/LC35 backfill: append `retired` to whichever marker was canonical,
    // linking the republication commit found above as `resurrection_commit`.
    let repair_actor = std::env::var("USER").unwrap_or_else(|_| "local-user".to_owned());
    for (raw_hash, marker_kind, republication_commit) in retirements_to_backfill {
        let outcome = match marker_kind {
            TombstoneMode::Default => purge
                .retire_tombstone(
                    &raw_hash,
                    &republication_commit,
                    &invocation_time,
                    &repair_actor,
                )
                .map(|_| ()),
            TombstoneMode::Erase => purge
                .retire_erase_receipt(
                    &raw_hash,
                    &republication_commit,
                    &invocation_time,
                    &repair_actor,
                )
                .map(|_| ()),
        };
        if let Err(error) = outcome {
            let kind = match marker_kind {
                TombstoneMode::Default => "tombstone_corrupt",
                TombstoneMode::Erase => "erase_receipt_corrupt",
            };
            state.finding(kind, &raw_hash, &error.to_string(), &[]);
        }
    }
    let repaired = staged_raws.len() as u64;
    let repaired_commit_hash = if repaired > 0 && repairs_allowed && !state.exceeded_bounds {
        Some(repo.record_repaired_commit(Some("repair --verify-objects recovered raw CAS"))?)
    } else {
        None
    };
    if state.exceeded_bounds {
        state.finding("inventory_limit", "", "fsck inventory bound exceeded", &[]);
    }
    Ok(finish_report(state, repaired, repaired_commit_hash))
}

fn finish_report(
    state: State,
    repaired_raw_count: u64,
    repaired_commit_hash: Option<String>,
) -> VerifyObjectsReport {
    let has_findings = !state.findings.is_empty() || state.findings_truncated;
    VerifyObjectsReport {
        status: if has_findings { "corrupt" } else { "ok" }.to_owned(),
        checked: state.checked,
        repaired_raw_count,
        repaired_commit_hash,
        dead_by_tombstone_count: state.dead_by_tombstone_count,
        dead_by_erase_receipt_count: state.dead_by_erase_receipt_count,
        remaining_findings: state.findings,
        findings_truncated: state.findings_truncated,
        external_pointers_may_be_affected: has_findings,
        verified_bytes: state.verified_bytes,
        inventoried_objects: state.inventoried_objects,
    }
}

fn finish_limit_report(mut state: State) -> VerifyObjectsReport {
    state.finding("inventory_limit", "", "fsck inventory bound exceeded", &[]);
    finish_report(state, 0, None)
}

struct State {
    checked: CheckedObjects,
    findings: Vec<ObjectFinding>,
    findings_truncated: bool,
    exceeded_bounds: bool,
    unsafe_namespace: bool,
    verified_bytes: u64,
    inventoried_objects: usize,
    visited_entries: usize,
    dead_by_tombstone_count: u64,
    dead_by_erase_receipt_count: u64,
    max_objects: usize,
    max_verified_bytes: u64,
    remaining_affected_commits: usize,
}

impl Default for State {
    fn default() -> Self {
        Self {
            checked: CheckedObjects::default(),
            findings: Vec::new(),
            findings_truncated: false,
            exceeded_bounds: false,
            unsafe_namespace: false,
            verified_bytes: 0,
            inventoried_objects: 0,
            visited_entries: 0,
            dead_by_tombstone_count: 0,
            dead_by_erase_receipt_count: 0,
            max_objects: MAX_OBJECTS,
            max_verified_bytes: MAX_VERIFIED_BYTES,
            remaining_affected_commits: MAX_AFFECTED_COMMITS,
        }
    }
}

impl State {
    fn add_bytes(&mut self, bytes: u64) {
        self.verified_bytes = self.verified_bytes.saturating_add(bytes);
        self.exceeded_bounds |= self.verified_bytes > self.max_verified_bytes;
    }

    fn visit_entry(&mut self) {
        self.visited_entries = self.visited_entries.saturating_add(1);
        self.exceeded_bounds |= self.visited_entries > MAX_OBJECTS;
    }

    fn count_object(&mut self) {
        self.inventoried_objects = self.inventoried_objects.saturating_add(1);
        self.exceeded_bounds |= self.inventoried_objects > self.max_objects;
    }

    fn finding(&mut self, kind: &str, hash: &str, reason: &str, affected: &[String]) {
        if self.findings.len() >= MAX_FINDINGS {
            self.findings_truncated = true;
            return;
        }
        let affected_count = affected.len().min(self.remaining_affected_commits);
        self.remaining_affected_commits -= affected_count;
        self.findings.push(ObjectFinding {
            kind: kind.to_owned(),
            object_hash: hash.to_owned(),
            reason: reason.to_owned(),
            affected_commits: affected.iter().take(affected_count).cloned().collect(),
        });
    }
}

fn inventory(kcs_dir: &Path, kind: &str, state: &mut State) -> Result<BTreeSet<String>> {
    let base = kcs_dir.join("objects").join(kind);
    if !real_directory(&base)? {
        if fs::symlink_metadata(&base).is_ok() {
            state.unsafe_namespace = true;
            state.finding(
                "non_regular_object",
                "",
                "object namespace root is not a real directory",
                &[],
            );
        }
        return Ok(BTreeSet::new());
    }
    let mut hashes = BTreeSet::new();
    let mut stack = vec![base.clone()];
    while let Some(directory) = stack.pop() {
        for entry in fs::read_dir(&directory)
            .map_err(|error| KcsError::io(error.to_string(), directory.display().to_string()))?
        {
            let entry = entry.map_err(|error| {
                KcsError::io(error.to_string(), directory.display().to_string())
            })?;
            state.visit_entry();
            if state.exceeded_bounds {
                return Ok(hashes);
            }
            let path = entry.path();
            let file_type = entry
                .file_type()
                .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
            if file_type.is_dir() && !file_type.is_symlink() {
                if real_directory(&path)? {
                    stack.push(path);
                } else {
                    state.unsafe_namespace = true;
                    state.finding(
                        "non_regular_object",
                        "",
                        "object inventory contains a linked directory",
                        &[],
                    );
                }
                continue;
            }
            if !file_type.is_file() || file_type.is_symlink() {
                state.count_object();
                state.finding(
                    "non_regular_object",
                    "",
                    "object inventory contains a non-regular entry",
                    &[],
                );
                continue;
            }
            let leaf = entry.file_name().to_string_lossy().into_owned();
            let digest = leaf.strip_prefix("sha256:").unwrap_or(&leaf);
            let hash = format!("sha256:{digest}");
            let relative = path.strip_prefix(&base).unwrap_or(&path);
            let parts = relative
                .iter()
                .map(|p| p.to_string_lossy())
                .collect::<Vec<_>>();
            if !is_hash(&hash)
                || parts.len() != 3
                || parts[0] != digest[0..2]
                || parts[1] != digest[2..4]
            {
                state.count_object();
                state.finding(
                    "invalid_fanout",
                    &hash,
                    "object leaf does not match canonical fan-out",
                    &[],
                );
                continue;
            }
            if hashes.insert(hash) {
                state.count_object();
            }
            if state.exceeded_bounds {
                return Ok(hashes);
            }
        }
    }
    Ok(hashes)
}

fn verify_prepared_reference(
    store: &ObjectStore,
    prepared_hash: &str,
    verified_raw_substitution: bool,
) -> std::result::Result<u64, AccountedReadError> {
    match store.inspect_content_accounted(ContentObjectKind::Prepared, prepared_hash) {
        Ok(metadata) => Ok(metadata.size_bytes),
        Err(failure)
            if failure.error.error_code() == "KCS-E-STORE-NOT-FOUND-001"
                && verified_raw_substitution =>
        {
            Ok(0)
        }
        Err(failure) => Err(failure),
    }
}

fn marker_inventory(kcs_dir: &Path, relative: &str, state: &mut State) -> Result<BTreeSet<String>> {
    let base = kcs_dir.join(relative);
    if !real_directory(&base)? {
        if fs::symlink_metadata(&base).is_ok() {
            state.unsafe_namespace = true;
            state.finding(
                "purge_marker_corrupt",
                "",
                "purge marker namespace root is not a real directory",
                &[],
            );
        }
        return Ok(BTreeSet::new());
    }
    let mut hashes = BTreeSet::new();
    let mut stack = vec![base.clone()];
    while let Some(directory) = stack.pop() {
        let entries = fs::read_dir(&directory)
            .map_err(|error| KcsError::io(error.to_string(), directory.display().to_string()))?;
        for entry in entries {
            let entry = entry.map_err(|error| {
                KcsError::io(error.to_string(), directory.display().to_string())
            })?;
            state.visit_entry();
            if state.exceeded_bounds {
                return Ok(hashes);
            }
            let path = entry.path();
            let file_type = entry
                .file_type()
                .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
            if file_type.is_dir() && !file_type.is_symlink() {
                if real_directory(&path)? {
                    stack.push(path);
                } else {
                    state.unsafe_namespace = true;
                    state.finding(
                        "purge_marker_corrupt",
                        "",
                        "purge marker inventory contains a linked directory",
                        &[],
                    );
                }
                continue;
            }
            if !file_type.is_file() || file_type.is_symlink() {
                state.count_object();
                state.finding(
                    "purge_marker_corrupt",
                    "",
                    "purge marker inventory contains a non-regular entry",
                    &[],
                );
                continue;
            }
            let leaf = entry.file_name().to_string_lossy().into_owned();
            let digest = if relative == "tombstones" {
                leaf.strip_prefix("sha256:").unwrap_or(&leaf)
            } else {
                &leaf
            };
            let hash = format!("sha256:{digest}");
            let parts = path
                .strip_prefix(&base)
                .unwrap_or(&path)
                .iter()
                .map(|part| part.to_string_lossy())
                .collect::<Vec<_>>();
            if !is_hash(&hash)
                || parts.len() != 3
                || parts[0] != digest[0..2]
                || parts[1] != digest[2..4]
            {
                state.count_object();
                state.finding(
                    "purge_marker_corrupt",
                    &hash,
                    "purge marker leaf does not match canonical fan-out",
                    &[],
                );
                continue;
            }
            match read_bounded_regular_file(&path, MAX_PURGE_RECORD_BYTES) {
                Ok(bytes) => {
                    state.add_bytes(bytes.len() as u64);
                    if state.exceeded_bounds {
                        return Ok(hashes);
                    }
                }
                Err(error) => {
                    state.finding("purge_marker_corrupt", &hash, &error.to_string(), &[]);
                    continue;
                }
            }
            if hashes.insert(hash) {
                state.count_object();
            }
            if state.exceeded_bounds {
                return Ok(hashes);
            }
        }
    }
    Ok(hashes)
}

fn real_directory(path: &Path) -> Result<bool> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(error) => return Err(KcsError::io(error.to_string(), path.display().to_string())),
    };
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Ok(false);
    }
    #[cfg(windows)]
    if !kcs_core::cas::windows_directory_is_real(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?
    {
        return Ok(false);
    }
    Ok(true)
}

fn reachable_commits(
    repo: &Repository,
    commits: &BTreeMap<String, CommitObject>,
    state: &mut State,
) -> Result<BTreeSet<String>> {
    let mut visited = BTreeSet::new();
    let mut queue = commit_roots(repo, state)?
        .into_iter()
        .collect::<VecDeque<_>>();
    while let Some(hash) = queue.pop_front() {
        if !visited.insert(hash.clone()) {
            continue;
        }
        let Some(commit) = commits.get(&hash) else {
            state.finding(
                "missing_commit",
                &hash,
                "reachable commit object is missing",
                &[],
            );
            continue;
        };
        queue.extend(commit.parents.iter().cloned());
        if visited.len() > state.max_objects {
            state.exceeded_bounds = true;
            break;
        }
    }
    Ok(visited)
}

fn commit_roots(repo: &Repository, state: &mut State) -> Result<BTreeSet<String>> {
    const MAX_REF_BYTES: u64 = 128;
    let mut roots = BTreeSet::new();
    let mut tag_targets = BTreeMap::<String, String>::new();
    let head_path = repo.kcs_dir().join("HEAD");
    match read_bounded_regular_file(&head_path, MAX_REF_BYTES) {
        Ok(bytes) => {
            state.add_bytes(bytes.len() as u64);
            if state.exceeded_bounds {
                return Ok(roots);
            }
            match std::str::from_utf8(&bytes).map(str::trim) {
                Ok("") => {}
                Ok(value) if is_hash(value) => {
                    roots.insert(value.to_owned());
                }
                _ => state.finding("ref_corrupt", "", "HEAD is not a commit hash", &[]),
            }
        }
        Err(error) => state.finding("ref_corrupt", "", &error.to_string(), &[]),
    }
    for relative in ["refs/heads", "refs/tags-v1", "refs/tags"] {
        let base = repo.kcs_dir().join(relative);
        let metadata = match fs::symlink_metadata(&base) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => {
                state.finding("ref_io", "", &error.to_string(), &[]);
                continue;
            }
        };
        if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
            state.finding(
                "ref_non_regular",
                "",
                "ref root is not a real directory",
                &[],
            );
            continue;
        }
        let mut stack = vec![base];
        while let Some(directory) = stack.pop() {
            let entries = match fs::read_dir(&directory) {
                Ok(entries) => entries,
                Err(error) => {
                    state.finding("ref_io", "", &error.to_string(), &[]);
                    continue;
                }
            };
            for entry in entries {
                let entry = match entry {
                    Ok(entry) => entry,
                    Err(error) => {
                        state.finding("ref_io", "", &error.to_string(), &[]);
                        continue;
                    }
                };
                state.visit_entry();
                if state.exceeded_bounds {
                    return Ok(roots);
                }
                let path = entry.path();
                let file_type = match entry.file_type() {
                    Ok(file_type) => file_type,
                    Err(error) => {
                        state.finding("ref_io", "", &error.to_string(), &[]);
                        continue;
                    }
                };
                if file_type.is_dir() && !file_type.is_symlink() {
                    state.finding(
                        "ref_non_regular",
                        "",
                        "nested ref directories are not allowed",
                        &[],
                    );
                    continue;
                }
                if !file_type.is_file() || file_type.is_symlink() {
                    state.finding("ref_non_regular", "", "ref is not a real regular file", &[]);
                    continue;
                }
                if relative == "refs/tags-v1" {
                    let leaf = entry.file_name().to_string_lossy().into_owned();
                    let valid = leaf.strip_prefix("tag-").is_some_and(|digest| {
                        digest.len() == 64
                            && digest
                                .bytes()
                                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
                    });
                    if !valid {
                        state.finding("ref_corrupt", "", "canonical tag leaf is invalid", &[]);
                        continue;
                    }
                }
                let bytes = match read_bounded_regular_file(&path, MAX_REF_BYTES) {
                    Ok(bytes) => bytes,
                    Err(error) => {
                        state.finding("ref_corrupt", "", &error.to_string(), &[]);
                        continue;
                    }
                };
                state.add_bytes(bytes.len() as u64);
                if state.exceeded_bounds {
                    return Ok(roots);
                }
                let value = match std::str::from_utf8(&bytes) {
                    Ok(value) => value.trim(),
                    Err(_) => {
                        state.finding("ref_corrupt", "", "ref is not UTF-8", &[]);
                        continue;
                    }
                };
                if value.is_empty() {
                    if relative != "refs/heads" || entry.file_name() != "main" {
                        state.finding("ref_corrupt", "", "ref value is empty", &[]);
                    }
                    continue;
                }
                if !is_hash(value) {
                    state.finding("ref_corrupt", value, "ref value is not a commit hash", &[]);
                    continue;
                }
                let tag_key = if relative == "refs/tags-v1" {
                    Some(entry.file_name().to_string_lossy().into_owned())
                } else if relative == "refs/tags" {
                    let logical = entry.file_name().to_string_lossy().into_owned();
                    Some(kcs_core::portable::portable_tag_leaf(&logical))
                } else {
                    None
                };
                if let Some(tag_key) = tag_key {
                    if tag_targets
                        .insert(tag_key, value.to_owned())
                        .is_some_and(|existing| existing != value)
                    {
                        state.finding(
                            "ref_corrupt",
                            value,
                            "canonical and legacy tag refs disagree",
                            &[],
                        );
                    }
                }
                roots.insert(value.to_owned());
                if roots.len() > state.max_objects {
                    state.exceeded_bounds = true;
                    return Ok(roots);
                }
            }
        }
    }
    Ok(roots)
}

/// LC8-LC10 (§C): canonical final event across both markers for `raw_hash`,
/// after LC9's "only validated markers participate" gate. A marker whose
/// `events[]` fails structural (`kcs_core::purge`, already applied by
/// `PurgeState::read_tombstone`/`read_erase_receipt`) or semantic (this
/// module's DAG-bound `validate_marker_events`) validation does not
/// contribute its tail — its failure reason is returned separately so the
/// caller can still surface a `*_corrupt` finding for it (LC21: fsck and the
/// resolver never disagree about which markers explain state).
struct CanonicalLookup {
    canonical: Option<CanonicalFinalEvent>,
    tombstone_error: Option<String>,
    receipt_error: Option<String>,
}

fn canonical_lookup(
    purge: &PurgeState,
    raw_hash: &str,
    commits: &BTreeMap<String, CommitObject>,
    trees: &BTreeMap<String, TreeObject>,
    reachable: &BTreeSet<String>,
    invocation_time: &str,
) -> CanonicalLookup {
    let mut tombstone_tail = None;
    let mut tombstone_error = None;
    match purge.read_tombstone(raw_hash) {
        Ok(Some(record)) => {
            match validate_marker_events(
                raw_hash,
                &record.events,
                commits,
                trees,
                reachable,
                invocation_time,
            ) {
                Ok(()) => tombstone_tail = Some(record.tail().clone()),
                Err(reason) => tombstone_error = Some(reason),
            }
        }
        Ok(None) => {}
        Err(error) => tombstone_error = Some(error.to_string()),
    }
    let mut receipt_tail = None;
    let mut receipt_error = None;
    match purge.read_erase_receipt(raw_hash) {
        Ok(Some(receipt)) => {
            match validate_marker_events(
                raw_hash,
                &receipt.events,
                commits,
                trees,
                reachable,
                invocation_time,
            ) {
                Ok(()) => receipt_tail = Some(receipt.tail().clone()),
                Err(reason) => receipt_error = Some(reason),
            }
        }
        Ok(None) => {}
        Err(error) => receipt_error = Some(error.to_string()),
    }
    CanonicalLookup {
        canonical: canonical_final_event(tombstone_tail.as_ref(), receipt_tail.as_ref()),
        tombstone_error,
        receipt_error,
    }
}

/// LC17/LC18/LC20/LC21 (10 §7.5.1): the DAG-bound semantic checks on top of
/// `kcs_core::purge`'s structural validation (kind closure, required-field
/// matrix, transition grammar). Applied identically to tombstone and erase
/// receipt events (10 §7.5.1: "tombstone lifecycle にも同じ event 検証を適用する").
fn validate_marker_events(
    raw_hash: &str,
    events: &[LifecycleEvent],
    commits: &BTreeMap<String, CommitObject>,
    trees: &BTreeMap<String, TreeObject>,
    reachable: &BTreeSet<String>,
    invocation_time: &str,
) -> std::result::Result<(), String> {
    for (index, event) in events.iter().enumerate() {
        match event.kind {
            EventKind::Purged | EventKind::Erased => {
                validate_purge_or_erase_in_commit(
                    raw_hash,
                    event,
                    commits,
                    reachable,
                    invocation_time,
                )?;
            }
            EventKind::Retired => {
                let previous_index = index
                    .checked_sub(1)
                    .ok_or_else(|| "retired event has no preceding event".to_owned())?;
                let previous = events
                    .get(previous_index)
                    .ok_or_else(|| "retired event has no preceding event".to_owned())?;
                validate_retired_event(
                    raw_hash,
                    event,
                    &previous.in_commit,
                    commits,
                    trees,
                    reachable,
                )?;
            }
        }
    }
    Ok(())
}

/// LC17/LC18: a `purged`/`erased` event's `in_commit` must be a bounded
/// verified CAS object, ref-reachable, `commit_type=purged`, whose
/// `purged_raws` includes this marker's raw_hash (03 §8: forged-`in_commit`
/// defense — a purge commit for a *different* raw cannot explain this one's
/// absence), with `at` equal to that commit's `created_at` and not in the
/// future relative to the fixed invocation time.
fn validate_purge_or_erase_in_commit(
    raw_hash: &str,
    event: &LifecycleEvent,
    commits: &BTreeMap<String, CommitObject>,
    reachable: &BTreeSet<String>,
    invocation_time: &str,
) -> std::result::Result<(), String> {
    if !reachable.contains(&event.in_commit) {
        return Err("lifecycle event in_commit is not ref-reachable".to_owned());
    }
    let commit = commits
        .get(&event.in_commit)
        .ok_or_else(|| "lifecycle event in_commit object is missing or corrupt".to_owned())?;
    if commit.commit_type != CommitType::Purged {
        return Err("lifecycle event in_commit commit_type is not purged".to_owned());
    }
    if !commit.purged_raws.iter().any(|hash| hash == raw_hash) {
        return Err(
            "lifecycle event in_commit purged_raws does not include this raw_hash".to_owned(),
        );
    }
    if commit.created_at != event.at {
        return Err("lifecycle event at does not equal commit created_at".to_owned());
    }
    if timestamp_is_after(&event.at, invocation_time)? {
        return Err("lifecycle event at is in the future".to_owned());
    }
    Ok(())
}

/// LC20: terminal `retired`'s `resurrection_commit` must be ref-reachable and
/// a (strict) descendant of the immediately-preceding `purged`/`erased`
/// event's `in_commit` — i.e. the republication happened *after* that purge.
/// Additionally (defense-in-depth, 08-evidence-pointer-spec.md step 8's own
/// tree-membership re-check), when the resurrection commit's tree has NOT
/// been shallow-discarded, that tree must actually contain a leaf entry for
/// this same `raw_hash` — a `retired` event whose resurrection commit exists,
/// is ref-reachable, and descends correctly, but whose tree simply never
/// carried this raw_hash at all, is still corruption (a forged/mismatched
/// resurrection link). `trees` mirrors this module's own inventory-scanned
/// tree map (`fsck`'s `trees`, keyed by tree hash — physically-absent trees,
/// including a shallow-discarded one, are simply absent from it, so the leaf
/// check is skipped rather than misreported as corruption for a legitimately
/// shallow auto-type publication commit).
fn validate_retired_event(
    raw_hash: &str,
    event: &LifecycleEvent,
    previous_in_commit: &str,
    commits: &BTreeMap<String, CommitObject>,
    trees: &BTreeMap<String, TreeObject>,
    reachable: &BTreeSet<String>,
) -> std::result::Result<(), String> {
    let resurrection_commit = event
        .resurrection_commit
        .as_deref()
        .ok_or_else(|| "retired event is missing its resurrection_commit".to_owned())?;
    if !reachable.contains(resurrection_commit) {
        return Err("retired event resurrection_commit is not ref-reachable".to_owned());
    }
    let Some(commit) = commits.get(resurrection_commit) else {
        return Err("retired event resurrection_commit object is missing or corrupt".to_owned());
    };
    if resurrection_commit == previous_in_commit
        || !is_ancestor(commits, previous_in_commit, resurrection_commit)
    {
        return Err(
            "retired event resurrection_commit does not descend from the preceding purge/erase event"
                .to_owned(),
        );
    }
    if let Some(tree) = trees.get(&commit.tree) {
        if !tree.entries.iter().any(|entry| entry.raw_hash == raw_hash) {
            return Err(
                "retired event resurrection_commit tree does not contain a leaf for this raw_hash"
                    .to_owned(),
            );
        }
    }
    // `trees.get(&commit.tree) == None`: the resurrection commit's tree is
    // not physically present (shallow-discarded, or GC'd) — LC20's explicit
    // "tree 不在時は本検証を省略する" carve-out. A tree that IS present but
    // fails to parse already produced its own `tree_corrupt` finding
    // elsewhere in the fsck scan that built `trees`, independent of this
    // function.
    Ok(())
}

/// Strict-descendant test over the fsck-scanned commit map's parent chains
/// (`ancestor != descendant`; every commit is reachable from itself only via
/// its own chain, never treated as its own ancestor here since callers always
/// want "happened strictly after").
fn is_ancestor(commits: &BTreeMap<String, CommitObject>, ancestor: &str, descendant: &str) -> bool {
    let mut pending = vec![descendant.to_owned()];
    let mut visited = BTreeSet::new();
    while let Some(hash) = pending.pop() {
        let Some(commit) = commits.get(&hash) else {
            continue;
        };
        for parent in &commit.parents {
            if parent == ancestor {
                return true;
            }
            if visited.insert(parent.clone()) {
                pending.push(parent.clone());
            }
        }
    }
    false
}

/// LC27/LC29/LC35/LC36: search the ref-reachable set for a commit that
/// causally republished `raw_hash` after `purge_in_commit` — a strict
/// descendant of it. Deterministic (lexicographically smallest hash) when
/// more than one candidate exists; this is an existence/ancestry check only
/// (it does not additionally re-verify that the candidate's tree still
/// carries a live leaf for the raw_hash — a documented simplification).
fn find_republication_commit(
    purge_in_commit: &str,
    commits: &BTreeMap<String, CommitObject>,
    reachable: &BTreeSet<String>,
) -> Option<String> {
    reachable
        .iter()
        .filter(|candidate| {
            candidate.as_str() != purge_in_commit
                && commits.contains_key(candidate.as_str())
                && is_ancestor(commits, purge_in_commit, candidate)
        })
        .min()
        .cloned()
}

/// LC17: `dead_raws` (skips normalized/manifest/chunk verification for a
/// purged raw_hash) now follows the canonical final event, not per-marker
/// presence — a `retired` canonical means the raw is alive again and must
/// NOT be treated as an explained dead terminal even if a (superseded)
/// tombstone/receipt event still exists earlier in that marker's history.
fn valid_dead_terminal(
    verified_raws: &BTreeSet<String>,
    purge: &PurgeState,
    raw_hash: &str,
    commits: &BTreeMap<String, CommitObject>,
    trees: &BTreeMap<String, TreeObject>,
    reachable: &BTreeSet<String>,
    invocation_time: &str,
) -> bool {
    if verified_raws.contains(raw_hash) {
        return false;
    }
    let lookup = canonical_lookup(purge, raw_hash, commits, trees, reachable, invocation_time);
    matches!(
        lookup.canonical.map(|canonical| canonical.event.kind),
        Some(EventKind::Purged) | Some(EventKind::Erased)
    )
}

fn timestamp_is_after(left: &str, right: &str) -> std::result::Result<bool, String> {
    let (left_seconds, left_fraction) = timestamp_parts(left)?;
    let (right_seconds, right_fraction) = timestamp_parts(right)?;
    if left_seconds != right_seconds {
        return Ok(left_seconds > right_seconds);
    }
    let width = left_fraction.len().max(right_fraction.len());
    for index in 0..width {
        let left_digit = left_fraction.as_bytes().get(index).copied().unwrap_or(b'0');
        let right_digit = right_fraction
            .as_bytes()
            .get(index)
            .copied()
            .unwrap_or(b'0');
        if left_digit != right_digit {
            return Ok(left_digit > right_digit);
        }
    }
    Ok(false)
}

fn timestamp_parts(value: &str) -> std::result::Result<(i64, &str), String> {
    let Some(body) = value.strip_suffix('Z') else {
        return Err("timestamp is not canonical UTC".to_owned());
    };
    let (seconds_form, fraction) = match body.split_once('.') {
        Some((seconds, fraction))
            if !fraction.is_empty() && fraction.bytes().all(|byte| byte.is_ascii_digit()) =>
        {
            (format!("{seconds}Z"), fraction)
        }
        Some(_) => return Err("timestamp fractional seconds are invalid".to_owned()),
        None => (value.to_owned(), ""),
    };
    let seconds = kcs_core::scope::parse_utc_seconds(&seconds_form)
        .ok_or_else(|| "timestamp is not canonical UTC".to_owned())?;
    Ok((seconds, fraction))
}

fn collect_unit_image_references(
    metadata: &BTreeMap<String, serde_json::Value>,
    markdown: &str,
    output: &mut BTreeSet<String>,
) -> std::result::Result<(), String> {
    for (field, hash_field) in [("images", "hash"), ("bbox_annotations", "image_hash")] {
        let Some(value) = metadata.get(field) else {
            continue;
        };
        let array = value
            .as_array()
            .ok_or_else(|| format!("normalized metadata {field} must be an array"))?;
        for item in array {
            let hash = item
                .as_object()
                .and_then(|object| object.get(hash_field))
                .and_then(serde_json::Value::as_str)
                .ok_or_else(|| format!("normalized metadata {field} has a missing image hash"))?;
            if !is_hash(hash) {
                return Err(format!(
                    "normalized metadata {field} has an invalid image hash"
                ));
            }
            output.insert(hash.to_owned());
        }
    }

    let mut remaining = markdown;
    while let Some(index) = remaining.find("kcs://") {
        let candidate = &remaining[index..];
        let token = candidate
            .split(|character: char| {
                character.is_whitespace() || matches!(character, ')' | ']' | '>' | '"' | '\'')
            })
            .next()
            .unwrap_or_default();
        if token.contains("/object/image/") {
            let object = super::parse_object_uri(token)
                .map_err(|error| error.to_string())?
                .ok_or_else(|| "normalized Markdown image URI is malformed".to_owned())?;
            if object.object_type != "image" {
                return Err("normalized Markdown image URI has the wrong type".to_owned());
            }
            output.insert(object.hash);
        }
        remaining = candidate.get(token.len()..).unwrap_or_default();
        if remaining.is_empty() {
            break;
        }
    }
    Ok(())
}

enum RawRecovery {
    Missing(u64),
    Candidate(Vec<u8>),
    LimitExceeded,
}

fn recover_raw(path: &Path, expected_hash: &str, remaining_bytes: u64) -> Result<RawRecovery> {
    let bytes = match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.len() > remaining_bytes => return Ok(RawRecovery::LimitExceeded),
        Ok(_) => match read_bounded_regular_file(path, MAX_RAW_OBJECT_BYTES.min(remaining_bytes)) {
            Ok(bytes) => bytes,
            Err(error) if error.error_code() == "KCS-E-STORE-OBJECT-OVERSIZED-001" => {
                return Ok(RawRecovery::LimitExceeded)
            }
            Err(error) => return Err(error),
        },
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(RawRecovery::Missing(0))
        }
        Err(error) => return Err(KcsError::io(error.to_string(), path.display().to_string())),
    };
    if hash_bytes(&bytes) != expected_hash {
        return Ok(RawRecovery::Missing(bytes.len() as u64));
    }
    Ok(RawRecovery::Candidate(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;
    use kcs_core::dag::CommitStats;

    fn hash(byte: char) -> String {
        format!("sha256:{}", byte.to_string().repeat(64))
    }

    fn commit(kind: CommitType, created_at: &str) -> CommitObject {
        CommitObject::new(
            hash('a'),
            Vec::new(),
            created_at.to_owned(),
            "marker test".to_owned(),
            hash('b'),
            CommitStats {
                files_added: 0,
                files_modified: 0,
                files_deleted: 0,
            },
            kind,
        )
        .unwrap()
    }

    fn purged_commit(created_at: &str, purged_raws: Vec<String>) -> CommitObject {
        CommitObject::new_purged(
            hash('a'),
            Vec::new(),
            created_at.to_owned(),
            "marker test".to_owned(),
            hash('b'),
            CommitStats {
                files_added: 0,
                files_modified: 0,
                files_deleted: 0,
            },
            purged_raws,
        )
        .unwrap()
    }

    fn purged_event(in_commit: &str, at: &str) -> LifecycleEvent {
        LifecycleEvent::purged(
            at,
            in_commit,
            kcs_core::purge::PurgeReason::Legal,
            "user",
            1,
        )
    }

    #[test]
    fn lc17_in_commit_binding_requires_reachable_purged_exact_non_future_commit_and_purged_raws_membership(
    ) {
        let commit_hash = hash('c');
        let target_raw = hash('9');
        let created_at = "2026-07-13T00:00:00.25Z";
        let mut commits = BTreeMap::from([(
            commit_hash.clone(),
            purged_commit(created_at, vec![target_raw.clone()]),
        )]);
        let reachable = BTreeSet::from([commit_hash.clone()]);
        let event = purged_event(&commit_hash, created_at);

        assert!(validate_purge_or_erase_in_commit(
            &target_raw,
            &event,
            &commits,
            &reachable,
            "2026-07-13T00:00:01Z"
        )
        .is_ok());
        // Not ref-reachable.
        assert!(validate_purge_or_erase_in_commit(
            &target_raw,
            &event,
            &commits,
            &BTreeSet::new(),
            "2026-07-13T00:00:01Z"
        )
        .is_err());
        // `at` does not equal commit.created_at.
        let mismatched_at = purged_event(&commit_hash, "2026-07-13T00:00:00Z");
        assert!(validate_purge_or_erase_in_commit(
            &target_raw,
            &mismatched_at,
            &commits,
            &reachable,
            "2026-07-13T00:00:01Z"
        )
        .is_err());
        // commit_type is not purged.
        commits.insert(commit_hash.clone(), commit(CommitType::Manual, created_at));
        assert!(validate_purge_or_erase_in_commit(
            &target_raw,
            &event,
            &commits,
            &reachable,
            "2026-07-13T00:00:01Z"
        )
        .is_err());
        // purged_raws does not include this raw_hash (borrowed marker defense).
        commits.insert(
            commit_hash.clone(),
            purged_commit(created_at, vec![hash('8')]),
        );
        assert!(validate_purge_or_erase_in_commit(
            &target_raw,
            &event,
            &commits,
            &reachable,
            "2026-07-13T00:00:01Z"
        )
        .is_err());
        // `at` in the future relative to the fixed invocation time.
        commits.insert(
            commit_hash.clone(),
            purged_commit(created_at, vec![target_raw.clone()]),
        );
        assert!(validate_purge_or_erase_in_commit(
            &target_raw,
            &event,
            &commits,
            &reachable,
            "2026-07-13T00:00:00.2Z"
        )
        .is_err());
    }

    #[test]
    fn byte_and_object_bounds_are_global_and_exact() {
        let mut state = State {
            max_objects: 2,
            max_verified_bytes: 5,
            ..State::default()
        };
        state.add_bytes(2);
        state.add_bytes(3);
        assert!(!state.exceeded_bounds);
        state.add_bytes(1);
        assert!(state.exceeded_bounds);
        state.inventoried_objects = 3;
        assert!(state.inventoried_objects > state.max_objects);
    }

    #[test]
    fn injected_fsck_limits_accept_exact_and_reject_one_beyond_without_refs_mutation() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("doc.md"), "bounded fsck").unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        repo.snapshot(Some("fixture"), Some("2026-07-13T00:00:00Z"))
            .unwrap();
        let baseline = verify_objects(&repo).unwrap();
        assert!(!baseline.has_remaining_findings());
        let head_before = std::fs::read(repo.kcs_dir().join("HEAD")).unwrap();

        let exact = verify_objects_with_limits(
            &repo,
            VerifyLimits {
                max_objects: baseline.inventoried_objects,
                max_verified_bytes: baseline.verified_bytes,
            },
        )
        .unwrap();
        assert!(!exact.has_remaining_findings());

        let bytes_over = verify_objects_with_limits(
            &repo,
            VerifyLimits {
                max_objects: baseline.inventoried_objects,
                max_verified_bytes: baseline.verified_bytes.saturating_sub(1),
            },
        )
        .unwrap();
        assert!(bytes_over.has_remaining_findings());
        let object_over = verify_objects_with_limits(
            &repo,
            VerifyLimits {
                max_objects: baseline.inventoried_objects.saturating_sub(1),
                max_verified_bytes: baseline.verified_bytes,
            },
        )
        .unwrap();
        assert!(object_over.has_remaining_findings());
        assert_eq!(
            std::fs::read(repo.kcs_dir().join("HEAD")).unwrap(),
            head_before
        );
    }

    #[test]
    fn active_or_corrupt_purge_journal_stops_before_any_object_read() {
        let dir = tempfile::tempdir().unwrap();
        let contents = b"private purge target";
        std::fs::write(dir.path().join("private.md"), contents).unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        repo.snapshot(Some("fixture"), Some("2026-07-13T00:00:00Z"))
            .unwrap();
        let purge = PurgeState::new(repo.kcs_dir());
        purge
            .begin(
                vec![hash_bytes(contents)],
                kcs_core::purge::PurgeReason::Legal,
                kcs_core::purge::TombstoneMode::Default,
                "user",
                "2026-07-13T00:00:01Z",
                1,
                hash_bytes(b"planned commit placeholder"),
                kcs_core::scope::new_ulid(dir.path()),
            )
            .unwrap();

        let active = verify_objects(&repo).unwrap();
        assert!(active.has_remaining_findings());
        assert_eq!(active.checked.raw, 0);
        assert_eq!(active.checked.chunks, 0);
        assert_eq!(active.checked.trees, 0);
        assert_eq!(active.checked.commits, 0);
        assert_eq!(active.checked.normalized_instances, 0);
        assert_eq!(active.verified_bytes, 0);
        assert_eq!(active.inventoried_objects, 0);
        assert_eq!(active.remaining_findings[0].kind, "purge_incomplete");

        std::fs::write(purge.journal_path(), b"not-json").unwrap();
        let corrupt = verify_objects(&repo).unwrap();
        assert!(corrupt.has_remaining_findings());
        assert_eq!(corrupt.checked.raw, 0);
        assert_eq!(corrupt.verified_bytes, 0);
        assert_eq!(corrupt.inventoried_objects, 0);
        assert_eq!(corrupt.remaining_findings[0].kind, "purge_journal_corrupt");
    }

    #[test]
    fn raw_substitution_only_applies_when_prepared_slot_is_absent() {
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        std::fs::create_dir(&kcs_dir).unwrap();
        let store = ObjectStore::new(&kcs_dir);
        let hash = store.write_raw(b"direct prepared bytes").unwrap();
        assert_eq!(verify_prepared_reference(&store, &hash, true).unwrap(), 0);

        let digest = hash.strip_prefix("sha256:").unwrap();
        let corrupt = kcs_dir
            .join("objects/prepared")
            .join(&digest[..2])
            .join(&digest[2..4])
            .join(digest);
        std::fs::create_dir_all(corrupt.parent().unwrap()).unwrap();
        std::fs::write(&corrupt, b"corrupt prepared bytes").unwrap();
        assert!(verify_prepared_reference(&store, &hash, true).is_err());
    }

    #[test]
    fn canonical_and_legacy_tag_forms_must_agree() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("doc.md"), "tag conflict").unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        repo.snapshot(Some("fixture"), Some("2026-07-13T00:00:00Z"))
            .unwrap();
        let canonical = repo
            .kcs_dir()
            .join("refs/tags-v1")
            .join(kcs_core::portable::portable_tag_leaf("Release"));
        std::fs::create_dir_all(canonical.parent().unwrap()).unwrap();
        std::fs::write(&canonical, repo.head_commit_hash().unwrap().unwrap()).unwrap();
        std::fs::write(repo.kcs_dir().join("refs/tags/Release"), hash('f')).unwrap();

        let report = verify_objects(&repo).unwrap();
        assert!(report.remaining_findings.iter().any(|finding| {
            finding.kind == "ref_corrupt"
                && finding.reason == "canonical and legacy tag refs disagree"
        }));
    }

    #[test]
    fn failed_corrupt_reads_obey_the_exact_global_byte_boundary() {
        let dir = tempfile::tempdir().unwrap();
        let original = b"accounted raw fixture";
        std::fs::write(dir.path().join("doc.md"), original).unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        repo.snapshot(Some("fixture"), Some("2026-07-13T00:00:00Z"))
            .unwrap();
        let raw_hash = hash_bytes(original);
        let raw_path = ObjectStore::new(repo.kcs_dir())
            .object_path(ObjectKind::Raw, &raw_hash)
            .unwrap();
        std::fs::write(&raw_path, vec![b'x'; original.len()]).unwrap();
        std::fs::write(dir.path().join("doc.md"), vec![b'y'; original.len()]).unwrap();

        let baseline = verify_objects(&repo).unwrap();
        assert!(baseline
            .remaining_findings
            .iter()
            .any(|finding| finding.kind == "raw_corrupt"));
        let exact = verify_objects_with_limits(
            &repo,
            VerifyLimits {
                max_objects: baseline.inventoried_objects,
                max_verified_bytes: baseline.verified_bytes,
            },
        )
        .unwrap();
        assert!(!exact
            .remaining_findings
            .iter()
            .any(|finding| finding.kind == "inventory_limit"));
        let one_under = verify_objects_with_limits(
            &repo,
            VerifyLimits {
                max_objects: baseline.inventoried_objects,
                max_verified_bytes: baseline.verified_bytes.saturating_sub(1),
            },
        )
        .unwrap();
        assert!(one_under
            .remaining_findings
            .iter()
            .any(|finding| finding.kind == "inventory_limit"));
    }

    #[test]
    fn logical_object_count_excludes_directories_and_counts_invalid_leaves_once() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("doc.md"), "logical count").unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        repo.snapshot(Some("fixture"), Some("2026-07-13T00:00:00Z"))
            .unwrap();
        let baseline = verify_objects(&repo).unwrap();
        let extra = repo.kcs_dir().join("objects/raw/fe/ed/empty-directory");
        std::fs::create_dir_all(&extra).unwrap();
        let with_directory = verify_objects(&repo).unwrap();
        assert_eq!(
            with_directory.inventoried_objects,
            baseline.inventoried_objects
        );

        std::fs::write(extra.parent().unwrap().join("invalid-leaf"), b"x").unwrap();
        let with_invalid_leaf = verify_objects(&repo).unwrap();
        assert_eq!(
            with_invalid_leaf.inventoried_objects,
            baseline.inventoried_objects + 1
        );
    }
}
