//! Bounded object-store verification for `repair verify-objects`.

use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};

use kio_core::cas::{
    hash_bytes, is_hash, read_bounded_regular_file, AccountedReadError, ChunkObject,
    ContentObjectKind, EmbeddingObject, ObjectKind, ObjectStore, MAX_RAW_OBJECT_BYTES,
};
use kio_core::dag::{CommitObject, TreeObject};
use kio_core::portable::portable_tag_digest64;
use kio_core::purge::{
    canonical_final_event, CanonicalFinalEvent, EventKind, LifecycleEvent, PurgeState,
    TombstoneMode, MAX_PURGE_RECORD_BYTES,
};
use kio_core::scope::{names_jsonl_path, now_utc_seconds, Repository};
use kio_core::{KioError, Result};
use kio_pipeline::markdownize::{
    load_validated_normalized_instance, normalized_instance_read_budget,
    NormalizedInstanceIdentity, ValidatedNormalizedInstance,
};
use serde::Serialize;

use crate::*;

const MAX_OBJECTS: usize = 1_000_000;
const MAX_VERIFIED_BYTES: u64 = 1024 * 1024 * 1024 * 1024;
const MAX_FINDINGS: usize = 1_024;
const MAX_AFFECTED_COMMITS: usize = 4_096;

pub(super) fn run_evidence(args: EvidenceArgs) -> Result<Value> {
    // B (2026-07-24): operand shape and `--strict` are declared on
    // `EvidenceArgs`; only the sub-command name is checked here because
    // `verify` is the sole one that exists (08 §4.3's `--batch` form is
    // Phase 4+).
    if args.subcommand.as_deref() != Some("verify") {
        return Err(KioError::invalid_usage(
            "evidence currently supports `evidence verify <pointer> [--strict]`",
        ));
    }
    let Some(pointer_operand) = args.pointer else {
        return Err(KioError::invalid_usage("pointer argument is required"));
    };
    let strict = args.strict;
    let raw = read_pointer_input(vec![pointer_operand])?;
    if raw.starts_with("sha256:") || parse_object_uri(&raw)?.is_some() {
        return Err(KioError::invalid_usage(
            "evidence verify accepts only a pointer URI, inline JSON, or '-' stdin",
        ));
    }
    let pointer = parse_pointer_text(&raw)?;
    verify_pointer_for_cli(&pointer, strict)
}

/// Read-only, content-free Evidence liveness check (08 §4.3). This deliberately
/// does not call `resolve_pointer_for_cli`: open/view may materialize an open-cache
/// file and return chunk text, both forbidden for verify.
///
/// PB64-68 (step4b-contract-tests-p2b.md §X, LC21 principle extended past
/// malformed-marker corruption to canonical-event *aggregation*): the
/// tombstone/erase-receipt dispatch below calls `enforce_canonical_marker_barrier`
/// (main.rs) — the SAME function `open`/`view`/`restore` use — instead of a
/// parallel, narrower single-marker (`read_tombstone(...).is_some()`) judgment.
/// A canonical `retired` tail (tombstone says `purged`, but the erase receipt
/// or a later tombstone event says `retired` with the greater lifecycle_epoch)
/// therefore resolves as alive here exactly as it does for `open`, per PB64's
/// LC10 worked example.
///
/// PB53-57 (§S): returns the full 6-value `status` union
/// (`alive|tombstoned|not_found|scope_unreachable|unverifiable|registry_duplicate`)
/// as a structured `Ok(Value)` wherever 08§4.3 specifies one. Only genuine
/// command-level conditions — sqlite.db unavailable (PB57), an active purge
/// journal (PB58, unchanged), and genuine store corruption (LC13/LC14 via the
/// shared canonical dispatch) — still propagate as a raw `KioError`.
///
/// Procedures 6a/6b (08§3.1, PB45-50/55) are implemented via the shared
/// `verify_point_in_time_attribution` (main.rs) — `unverifiable`'s
/// `manifest_missing` reason, the publication/config-association
/// ancestor-or-equal checks, and 6b's in_commit-scoped manifest-missing
/// downgrade (with resurrection-link fallback) all flow through the same
/// judgment `resolve_pointer_for_cli` (open/view/restore) uses — PB66's
/// structural requirement.
fn verify_pointer_for_cli(pointer: &EvidencePointer, strict: bool) -> Result<Value> {
    let target = match resolve_scope_target(&pointer.scope_id, pointer.scope_path.as_deref()) {
        Ok(target) => target,
        // PB53: a structured `status`, not a raw command failure — exit 0
        // unless `--strict` (PB56 promotes it to 3).
        Err(error) if error.error_code() == "KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001" => {
            return Ok(verify_exit_override(
                json!({
                    "status": "scope_unreachable",
                    "error_code": error.error_code(),
                    "details": error.context().clone(),
                }),
                if strict { 3 } else { 0 },
            ));
        }
        // PB54: live registry duplicate — exit 3 regardless of --strict.
        Err(error) if error.error_code() == "KIO-E-REGISTRY-DUP-001" => {
            return Ok(verify_exit_override(
                json!({
                    "status": "registry_duplicate",
                    "error_code": error.error_code(),
                    "details": error.context().clone(),
                }),
                3,
            ));
        }
        Err(error) => return Err(error),
    };
    // PB57: sqlite.db missing/unavailable is a command-level retryable error
    // (never a `status` field), independent of `--strict` — the verification
    // itself has not run, so there is nothing to report as a result.
    if !sqlite_path(&target.kio_dir).exists() {
        return Err(index_rebuilding_error());
    }
    // QB6 (step4b-contract-tests-p3b.md §A, 10 §3 L300-305): (0)
    // kio_format_version compatibility, checked before (1)/(3) below — this
    // used to open second, so a format-incompatible scope with an active
    // purge journal surfaced the lower-priority
    // `KIO-E-PURGE-JOURNAL-ACTIVE-001` instead of `KIO-E-STORE-VERSION-001`.
    let repo = Repository::open(&target.repo_root)?;
    // QB5/QB6/裁定1: shared (1)+(3) preflight pair. Evidence verify's whole
    // response IS existence information (08 §4.3 — it never returns body),
    // so checkpoint 2 below (LC54/LC55) gates every return point, not only a
    // single "success" path.
    let checkpoint = preflight_barrier_and_index(&target.kio_dir)?;
    let commit = match repo.read_commit(&pointer.commit) {
        Ok(commit) => commit,
        Err(error) if is_store_not_found(&error) => {
            return Err(unresolvable_commit_pointer_error(pointer));
        }
        Err(error) => return Err(error),
    };
    let store = ObjectStore::new(&target.kio_dir);
    let (commit_shallow, entry_gen, entry_normalize) = match repo.read_tree(&commit.tree) {
        Ok(tree) => {
            // PB42/43/44 (§O, verify side): select the entry whose
            // `normalize.tool_profile_hash` binds to the pointer's (not just
            // the first raw_hash match), tie-broken by UTF-8 byte-order-
            // minimal path (05 §1.7's `path_at_commit` rule) when more than
            // one entry shares that binding. Zero matching entries at all
            // short-circuits straight to KIO-E-STORE-CORRUPT-001 WITHOUT
            // consulting the tombstone/erase-receipt markers (PB44) — the DAG
            // is never rewritten by purge, so a genuinely absent entry is
            // corruption, not an explainable purge outcome.
            let candidates = tree
                .entries
                .iter()
                .filter(|entry| entry.raw_hash == pointer.raw_hash)
                .collect::<Vec<_>>();
            if candidates.is_empty() {
                return Err(store_corrupt_pointer_entry_missing_error(pointer));
            }
            let Some(entry) = candidates
                .into_iter()
                .filter(|entry| {
                    entry.normalize.as_ref().is_some_and(|normalize| {
                        normalize.tool_profile_hash == pointer.tool_profile_hash
                    })
                })
                .min_by(|a, b| a.path.as_bytes().cmp(b.path.as_bytes()))
            else {
                return Err(invalid_pointer_identity_error(pointer));
            };
            let entry_gen = entry.normalize.as_ref().map(|normalize| normalize.gen);
            (false, entry_gen, entry.normalize.clone())
        }
        Err(error) if is_store_not_found(&error) => (true, None, None),
        Err(error) => return Err(error),
    };

    let raw_present = match store.inspect_object(ObjectKind::Raw, &pointer.raw_hash) {
        Ok(_) => true,
        Err(error) if is_store_not_found(&error) => false,
        Err(error) => return Err(error),
    };
    if let Err(marker_error) =
        enforce_canonical_marker_barrier(&target, &pointer.raw_hash, raw_present)
    {
        return dispatch_marker_barrier_error(
            &checkpoint,
            &target,
            &pointer.raw_hash,
            marker_error,
            strict,
        );
    }

    let chunk = match store.read_chunk(&pointer.chunk_hash) {
        Ok(chunk) => chunk,
        Err(error) if is_store_not_found(&error) => {
            return Err(KioError::new(
                "KIO-E-EVIDENCE-RETARGET-REQUIRED-001",
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

    // 08 §3.1 procedures 6a/6b (PB45-50/55, §P/§Q; item 2 of this session's
    // task): point-in-time attribution, shared with `resolve_pointer_for_cli`
    // (main.rs, PB66's structural requirement) rather than a parallel
    // judgment. `PB45`'s unit-status check is folded into this shared path
    // rather than a bespoke best-effort read here.
    let mut manifest_missing = false;
    if !commit_shallow {
        if let Some(normalize) = &entry_normalize {
            match verify_point_in_time_attribution(
                &target,
                &repo,
                &pointer.raw_hash,
                normalize,
                &pointer.chunk_hash,
                &chunk,
                &pointer.commit,
            )? {
                PointInTimeAttribution::Alive => {}
                PointInTimeAttribution::ManifestMissing => manifest_missing = true,
                PointInTimeAttribution::NotFound => {
                    return checkpoint.finish(verify_exit_override(
                        not_found_verify_output(&target, &pointer.raw_hash),
                        if strict { 4 } else { 0 },
                    ));
                }
                PointInTimeAttribution::StoreCorrupt => {
                    return Err(store_corrupt_pointer_entry_missing_error(pointer));
                }
                PointInTimeAttribution::IndexRebuilding => return Err(index_rebuilding_error()),
            }
        }
    }

    // Defense-in-depth: re-run the identical canonical dispatch after the
    // chunk read, in case a purge raced the resolution above (mirrors the
    // pre-existing double-check this function has always performed).
    if let Err(marker_error) = enforce_canonical_marker_barrier(&target, &pointer.raw_hash, true) {
        return dispatch_marker_barrier_error(
            &checkpoint,
            &target,
            &pointer.raw_hash,
            marker_error,
            strict,
        );
    }

    // PB55/56 (§S/§N): the closed `unverifiable` reason union.
    if strict && (commit_shallow || manifest_missing) {
        let reason = if manifest_missing {
            "manifest_missing"
        } else {
            "commit_shallow"
        };
        // PB41/56: `commit_shallow` alone is retryable (unshallow may
        // resolve it, exit 3); `manifest_missing` is permanent (exit 4).
        let exit = if manifest_missing { 4 } else { 3 };
        return checkpoint.finish(verify_exit_override(
            json!({
                "status": "unverifiable",
                "details": {
                    "scope_id": pointer.scope_id,
                    "scope_path": target.kio_dir.display().to_string(),
                    "commit": pointer.commit,
                    "raw_hash": pointer.raw_hash,
                    "tool_profile_hash": pointer.tool_profile_hash,
                    "chunk_hash": pointer.chunk_hash,
                    "reason": reason,
                },
            }),
            exit,
        ));
    }

    checkpoint.finish(json!({
        "status": "alive",
        "details": {
            "scope_id": pointer.scope_id,
            "scope_path": target.kio_dir.display().to_string(),
            "commit": pointer.commit,
            "raw_hash": pointer.raw_hash,
            "tool_profile_hash": pointer.tool_profile_hash,
            "chunk_hash": pointer.chunk_hash,
            "commit_shallow": commit_shallow,
            "manifest_missing": manifest_missing,
        }
    }))
}

/// PB64-68: translate an `enforce_canonical_marker_barrier` `Err` into the
/// SAME `status` shapes verify has always returned for tombstoned/not_found —
/// this is the one place that bridges main.rs's shared canonical dispatch
/// (which returns `KioError`, appropriate for `open`/`view`/`restore`'s "fail
/// the whole command" contract) into verify's "return a structured status,
/// don't fail the command" contract (08 §4.3). `KIO-E-STORE-CORRUPT-001`
/// (LC13/LC14 — a `retired` marker or no marker at all with the raw absent)
/// is not a `status` value in the 6-value union (§S) and propagates as-is.
fn dispatch_marker_barrier_error(
    checkpoint: &ReadBarrierCheckpoint,
    target: &ScopeTarget,
    raw_hash: &str,
    error: KioError,
    strict: bool,
) -> Result<Value> {
    // PB56 (§S/§N exit table): under `--strict`, `tombstoned`/`not_found`
    // are permanent (exit 4) — both are `KIO-E-PURGE-*-001` error-code
    // marker states, never transient. Non-strict always stays exit 0 (a
    // structured status, not a command failure).
    let exit = if strict { 4 } else { 0 };
    match error.error_code() {
        "KIO-E-PURGE-TOMBSTONED-001" => checkpoint.finish(verify_exit_override(
            tombstoned_verify_output(error.context().clone()),
            exit,
        )),
        "KIO-E-PURGE-NOT-FOUND-001" => checkpoint.finish(verify_exit_override(
            not_found_verify_output(target, raw_hash),
            exit,
        )),
        _ => Err(error),
    }
}

/// PB53/54/56: embed the private `__exit_code` marker `main()` strips before
/// printing (matching the existing convention `run_repair`/search partial
/// failure already use) so a structured status response can still request a
/// non-zero exit.
fn verify_exit_override(mut value: Value, exit: u64) -> Value {
    if exit != 0 {
        if let Some(object) = value.as_object_mut() {
            object.insert("__exit_code".to_owned(), json!(exit));
        }
    }
    value
}

/// PB57: sqlite.db is missing/unavailable — the same retryable code
/// `check_index_generation_current`'s cursor-mismatch branch and search's
/// exclusion path already use (main.rs), reused here rather than minted
/// fresh so verify and search agree on what "index rebuilding" means.
fn index_rebuilding_error() -> KioError {
    KioError::new(
        "KIO-E-INDEX-REBUILDING-001",
        "the search index is unavailable (not yet built or mid-rebuild); retry",
        json!({}),
        ExitCode::PartialFailure,
    )
}

/// PB44: zero tree entries name this pointer's raw_hash at this commit — the
/// DAG is never rewritten by purge (02-philosophy §2.4), so this is genuine
/// corruption, not an explainable purge outcome. Distinct from
/// `invalid_pointer_identity_error` (entries exist but none bind to this
/// pointer's tool_profile_hash) — same downstream `not_found`-class handling
/// (08 §3.1 step 8), different corruption code per PB44.
fn store_corrupt_pointer_entry_missing_error(pointer: &EvidencePointer) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        "no tree entry at this commit names the pointer's raw_hash; the DAG is never \
         rewritten by purge, so this is corruption rather than a purge outcome",
        json!({
            "commit": pointer.commit,
            "raw_hash": pointer.raw_hash,
        }),
        ExitCode::PermanentFailure,
    )
}

fn tombstoned_verify_output(mut tombstone: Value) -> Value {
    if let Some(object) = tombstone.as_object_mut() {
        object.remove("status");
    }
    json!({
        "status": "tombstoned",
        "error_code": "KIO-E-PURGE-TOMBSTONED-001",
        "details": tombstone,
    })
}

fn not_found_verify_output(target: &ScopeTarget, raw_hash: &str) -> Value {
    json!({
        "status": "not_found",
        "error_code": "KIO-E-PURGE-NOT-FOUND-001",
        "details": {
            "raw_hash": raw_hash,
            "scope_path": target.kio_dir.display().to_string(),
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
    /// PB01 (§A, U39): `objects/embeddings/` CAS objects verified (digest +
    /// declared-length/finite-vector).
    pub embeddings: u64,
    /// PB02 (§B, U39): `objects/manifests/` CAS objects verified (content
    /// hash).
    pub manifests: u64,
    /// PB02 (§B, U39): `objects/toollocks/` CAS objects verified (canonical
    /// JCS content hash — 03 §5.2).
    pub toollocks: u64,
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
    let store = ObjectStore::new(repo.kio_dir());
    let purge = PurgeState::new(repo.kio_dir());
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

    let raw_hashes = inventory(repo.kio_dir(), "raw", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let chunk_hashes = inventory(repo.kio_dir(), "chunks", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let tree_hashes = inventory(repo.kio_dir(), "trees", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let commit_hashes = inventory(repo.kio_dir(), "commits", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let tombstone_hashes = marker_inventory(repo.kio_dir(), "tombstones", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }
    let receipt_hashes = marker_inventory(repo.kio_dir(), "purge/erase-receipts", &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    if state.unsafe_namespace {
        return Ok(finish_report(state, 0, None));
    }

    // PB01/PB02 (§A/§B, 10 §7.5.1 L489): embedding/manifest/toollock CAS
    // objects join the verification closure. These are inventoried
    // standalone (not tree-cross-referenced — that requires
    // `normalize.manifest_hash`, PB04's prerequisite schema field, not
    // implemented this session; see this module's PB64-68 doc comment for
    // the analogous, explicitly-documented gap on the resolver side).
    verify_embeddings(&store, repo.kio_dir(), &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    verify_content_hash_closure(
        &store,
        repo.kio_dir(),
        ContentObjectKind::Manifest,
        "manifest_corrupt",
        &mut state,
    )?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }
    verify_content_hash_closure(
        &store,
        repo.kio_dir(),
        ContentObjectKind::Toollock,
        "toollock_corrupt",
        &mut state,
    )?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
    }

    // §C (U41, PB07-09): names.jsonl full-line verification + canonical tag
    // ref correspondence.
    verify_names_jsonl(repo.kio_dir(), &mut state)?;
    if state.exceeded_bounds {
        return Ok(finish_limit_report(state));
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
                    .map_err(|error| KioError::schema(error.to_string()))
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
                    .map_err(|error| KioError::schema(error.to_string()))
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
                        repo.kio_dir(),
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
                        repo.kio_dir(),
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
    // (raw_hash, marker_kind, republication commit hash, republication
    // commit `created_at`) queued for a `retired` append once the
    // corresponding physical-object pass completes (LC27/LC35: verified raw
    // + a ref-reachable, ancestor-respecting, raw-carrying republication
    // commit of the canonical purged/erased event -- R23-08).
    let mut retirements_to_backfill = Vec::<(String, TombstoneMode, String, String)>::new();
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
                    match find_republication_commit(
                        &raw_hash,
                        &canonical.event.in_commit,
                        &commits,
                        &trees,
                        &reachable,
                    ) {
                        Some((republication_commit, republication_created_at)) => {
                            retirements_to_backfill.push((
                                raw_hash.clone(),
                                canonical.marker_kind,
                                republication_commit,
                                republication_created_at,
                            ));
                        }
                        None => state.finding(
                            "purge_incomplete",
                            &raw_hash,
                            "verified raw exists but no causal republication commit was found (09 §5.3: re-run kio purge --raw-hash to complete idempotently)",
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
                                raw_hash,
                                &canonical.event.in_commit,
                                &commits,
                                &trees,
                                &reachable,
                            ) {
                                Some((republication_commit, republication_created_at)) => {
                                    retirements_to_backfill.push((
                                        raw_hash.clone(),
                                        canonical.marker_kind,
                                        republication_commit,
                                        republication_created_at,
                                    ));
                                }
                                None => state.finding(
                                    "purge_incomplete",
                                    raw_hash,
                                    "verified raw exists but no causal republication commit was found (09 §5.3: re-run kio purge --raw-hash to complete idempotently)",
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
    // R23-08: `at` is that commit's OWN `created_at` (05-runtime.md §3.5's
    // "その event の commit created_at と一致" requirement), never this fsck
    // invocation's own clock -- `find_republication_commit` now returns it
    // paired with the winning hash so this loop never has to re-derive it.
    let repair_actor = std::env::var("USER").unwrap_or_else(|_| "local-user".to_owned());
    let mut any_retired = false;
    for (raw_hash, marker_kind, republication_commit, republication_created_at) in
        retirements_to_backfill
    {
        let outcome = match marker_kind {
            TombstoneMode::Default => purge
                .retire_tombstone(
                    &raw_hash,
                    &republication_commit,
                    &republication_created_at,
                    &repair_actor,
                )
                .map(|_| ()),
            TombstoneMode::Erase => purge
                .retire_erase_receipt(
                    &raw_hash,
                    &republication_commit,
                    &republication_created_at,
                    &repair_actor,
                )
                .map(|_| ()),
        };
        match outcome {
            Ok(()) => any_retired = true,
            Err(error) => {
                let kind = match marker_kind {
                    TombstoneMode::Default => "tombstone_corrupt",
                    TombstoneMode::Erase => "erase_receipt_corrupt",
                };
                state.finding(kind, &raw_hash, &error.to_string(), &[]);
            }
        }
    }
    // R23-09/R23-22 (05-runtime.md §1.5 L215-219 "tombstone lifecycle の
    // 更新 (retire・再 purge)" is one of the six named `index_generation`
    // rotation triggers, and §3.5 L792-799's counter-rollback recovery must
    // run at every locked-mutation entry point that can advance the
    // lifecycle-epoch counter): a backfilled `retired` above bumps that
    // counter exactly like the index/reindex/purge paths' own retire events
    // do, but fsck had no call to `recover_index_generation` at all --
    // `index_metadata.last_lifecycle_epoch`/`index_generation` stayed stale
    // (and any genuine counter rollback undetected) until an unrelated
    // index-touching write happened to run. Only when `sqlite.db` already
    // exists: fsck must not conjure a fresh, empty index for a scope that
    // was never indexed (`recover_index_generation` has no existence guard
    // of its own -- its other callers run only after `rebuild_step3_index`
    // already guarantees the file is there).
    if any_retired && sqlite_path(repo.kio_dir()).exists() {
        recover_index_generation(repo.kio_dir())?;
    }
    let repaired = staged_raws.len() as u64;
    let repaired_commit_hash = if repaired > 0 && repairs_allowed && !state.exceeded_bounds {
        Some(repo.record_repaired_commit(Some("repair verify-objects recovered raw CAS"))?)
    } else {
        None
    };
    if state.exceeded_bounds {
        state.finding("inventory_limit", "", "fsck inventory bound exceeded", &[]);
    }
    Ok(finish_report(state, repaired, repaired_commit_hash))
}

/// PB01 (§A, 10 §7.5.1 L489 → 03 §8.1): `objects/embeddings/` CAS objects.
///
/// The per-type algorithm is 03 §8.1's, not the generic byte-hash every other
/// content-addressed kind uses, because an embedding's storage key is its
/// IDENTITY hash — what the vector is OF (target, profile, context) — rather
/// than a hash of the bytes. Recomputing the identity from the parsed header
/// and comparing it to the leaf name is the equivalent check, and it catches
/// something the byte hash cannot: an object filed under the wrong identity.
///
/// [`EmbeddingObject::from_bytes`] performs the rest of what 03 §8.1 asks for —
/// vector length against declared `dimensions`, NaN/infinity rejection, and the
/// trailing vector digest (which is what detects a bit flip INSIDE the vector,
/// since the storage key says nothing about the body).
fn verify_embeddings(store: &ObjectStore, kio_dir: &Path, state: &mut State) -> Result<()> {
    let hashes = inventory(kio_dir, ContentObjectKind::Embedding.directory(), state)?;
    if state.exceeded_bounds || state.unsafe_namespace {
        return Ok(());
    }
    for hash in hashes {
        state.count_object();
        if state.exceeded_bounds {
            return Ok(());
        }
        let bytes =
            match store.read_content_object_bytes(ContentObjectKind::Embedding, &hash, 1 << 20) {
                Ok(bytes) => bytes,
                Err(error) => {
                    state.finding("embedding_corrupt", &hash, &error.to_string(), &[]);
                    continue;
                }
            };
        state.add_bytes(bytes.len() as u64);
        if state.exceeded_bounds {
            return Ok(());
        }
        match EmbeddingObject::from_bytes(&bytes) {
            Ok(embedding) => match embedding.identity_hash() {
                Ok(identity) if identity == hash => state.checked.embeddings += 1,
                Ok(identity) => state.finding(
                    "embedding_corrupt",
                    &hash,
                    &format!("embedding identity hashes to {identity}, not its storage key"),
                    &[],
                ),
                Err(error) => {
                    state.finding("embedding_corrupt", &hash, &error.to_string(), &[]);
                }
            },
            Err(error) => {
                state.finding("embedding_corrupt", &hash, &error.to_string(), &[]);
            }
        }
    }
    Ok(())
}

/// PB02 (§B, 10 §7.5.1 L489): the standalone (non-tree-cross-referenced —
/// see the module-level PB64-68 doc comment's gap note on
/// `normalize.manifest_hash`) part of manifest/toollock verification: every
/// object under `objects/<kind>/` is content-addressed and its stored bytes
/// must hash to its own leaf name, exactly like prepared/image already are.
fn verify_content_hash_closure(
    store: &ObjectStore,
    kio_dir: &Path,
    kind: ContentObjectKind,
    finding_kind: &str,
    state: &mut State,
) -> Result<()> {
    let hashes = inventory(kio_dir, kind.directory(), state)?;
    if state.exceeded_bounds || state.unsafe_namespace {
        return Ok(());
    }
    for hash in hashes {
        state.count_object();
        if state.exceeded_bounds {
            return Ok(());
        }
        match store.inspect_content_accounted(kind, &hash) {
            Ok(metadata) => {
                state.add_bytes(metadata.size_bytes);
                if state.exceeded_bounds {
                    return Ok(());
                }
                match kind {
                    ContentObjectKind::Manifest => state.checked.manifests += 1,
                    ContentObjectKind::Toollock => state.checked.toollocks += 1,
                    _ => {}
                }
            }
            Err(failure) => {
                state.add_bytes(failure.consumed_bytes);
                if state.exceeded_bounds {
                    return Ok(());
                }
                state.finding(finding_kind, &hash, &failure.error.to_string(), &[]);
            }
        }
    }
    Ok(())
}

/// One parsed `names.jsonl` line (PB07-09, 03-data-model.md §2 L140-152).
#[derive(Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct NamesJsonlRecord {
    digest64: String,
    logical_name: String,
    recorded_at: String,
}

/// §C (U41, PB07-09): `refs/tags-v1/names.jsonl` full-line verification and
/// its correspondence with the canonical tag refs `commit_roots` already
/// inventoried into `roots` — but this function re-derives the canonical ref
/// leaf set independently (a bounded directory listing, not a mutation of
/// `commit_roots`'s return shape) so it stays a self-contained, orthogonal
/// check.
///
/// - PB07: every line's schema is valid and `digest64` equals
///   `portable_tag_digest64(logical_name)` (a mismatch — schema-valid but
///   wrong digest — is corruption distinct from a schema-invalid line, but
///   both are reported under the same `names_jsonl_corrupt` finding kind,
///   matching PB07's framing of both as corruption without requiring a
///   third finding kind).
/// - PB08: only the FINAL line may be a torn (truncated) tail; a malformed
///   line anywhere else is corruption.
/// - PB09: a canonical ref with no corresponding names.jsonl line is
///   corruption; a names.jsonl line with no corresponding canonical ref is
///   normal (tag-delete residue, append-only by design).
fn verify_names_jsonl(kio_dir: &Path, state: &mut State) -> Result<()> {
    // Bounded like every other fsck read in this module (never an unbounded
    // read of a file an attacker/bug could grow without limit).
    const MAX_NAMES_JSONL_BYTES: u64 = 64 * 1024 * 1024;
    let path = names_jsonl_path(kio_dir);
    // A scope with no tags at all has no names.jsonl yet — normal, not a
    // finding (checked before the open so ENOENT is never ambiguous with a
    // genuine I/O failure on an existing path).
    if fs::symlink_metadata(&path).is_err() {
        return Ok(());
    }
    let text = match read_bounded_regular_file(&path, MAX_NAMES_JSONL_BYTES) {
        Ok(bytes) => bytes,
        Err(error) => {
            state.finding("names_jsonl_corrupt", "", &error.to_string(), &[]);
            return Ok(());
        }
    };
    state.add_bytes(text.len() as u64);
    if state.exceeded_bounds {
        return Ok(());
    }
    let raw_lines = text
        .split(|byte| *byte == b'\n')
        .map(|line| String::from_utf8_lossy(line).into_owned())
        .collect::<Vec<_>>();
    // PB08: a JSONL file ending in `\n` has one trailing empty split segment
    // (not a torn tail); a file NOT ending in `\n` has a genuinely torn final
    // line, tolerated (silently truncated) here exactly like `chunks.jsonl`
    // (Q1) and `PurgeState`'s own record parsing.
    let mut lines = raw_lines;
    let torn_tail = !text.is_empty() && text.last() != Some(&b'\n');
    // Either the well-terminated case's trailing empty split segment, or the
    // torn-tail case's genuinely incomplete final line — both are dropped by
    // the same `pop()`, just for different reasons (see the comment above).
    if torn_tail || lines.last().is_some_and(String::is_empty) {
        lines.pop();
    }

    let mut last_valid_by_digest = BTreeMap::<String, String>::new();
    for line in &lines {
        if line.trim().is_empty() {
            continue;
        }
        state.count_object();
        if state.exceeded_bounds {
            return Ok(());
        }
        match serde_json::from_str::<NamesJsonlRecord>(line) {
            Ok(record) => {
                let expected_digest = portable_tag_digest64(&record.logical_name);
                if record.digest64 != expected_digest {
                    state.finding(
                        "names_jsonl_corrupt",
                        &record.digest64,
                        "names.jsonl digest64 does not match the recomputed logical_name digest",
                        &[],
                    );
                } else if record.recorded_at.is_empty() {
                    state.finding(
                        "names_jsonl_corrupt",
                        &record.digest64,
                        "names.jsonl row is missing recorded_at",
                        &[],
                    );
                } else {
                    last_valid_by_digest.insert(record.digest64.clone(), record.logical_name);
                }
            }
            Err(error) => {
                state.finding("names_jsonl_corrupt", "", &error.to_string(), &[]);
            }
        }
    }

    // PB09: canonical ref <-> names.jsonl correspondence. A ref with no
    // matching (schema-valid) names row is corruption; the reverse (a names
    // row with no matching ref) is normal tag-delete residue.
    let canonical_dir = kio_dir.join("refs/tags-v1");
    let Ok(entries) = fs::read_dir(&canonical_dir) else {
        return Ok(());
    };
    for entry in entries.flatten() {
        let leaf = entry.file_name().to_string_lossy().into_owned();
        if leaf == "names.jsonl" {
            continue;
        }
        let Some(digest) = leaf.strip_prefix("tag-") else {
            continue;
        };
        if !last_valid_by_digest.contains_key(digest) {
            state.finding(
                "names_jsonl_corrupt",
                digest,
                "canonical tag ref has no corresponding names.jsonl row",
                &[],
            );
        }
    }
    Ok(())
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

fn inventory(kio_dir: &Path, kind: &str, state: &mut State) -> Result<BTreeSet<String>> {
    let base = kio_dir.join("objects").join(kind);
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
            .map_err(|error| KioError::io(error.to_string(), directory.display().to_string()))?
        {
            let entry = entry.map_err(|error| {
                KioError::io(error.to_string(), directory.display().to_string())
            })?;
            state.visit_entry();
            if state.exceeded_bounds {
                return Ok(hashes);
            }
            let path = entry.path();
            let file_type = entry
                .file_type()
                .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?;
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
            if failure.error.error_code() == "KIO-E-STORE-NOT-FOUND-001"
                && verified_raw_substitution =>
        {
            Ok(0)
        }
        Err(failure) => Err(failure),
    }
}

fn marker_inventory(kio_dir: &Path, relative: &str, state: &mut State) -> Result<BTreeSet<String>> {
    let base = kio_dir.join(relative);
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
            .map_err(|error| KioError::io(error.to_string(), directory.display().to_string()))?;
        for entry in entries {
            let entry = entry.map_err(|error| {
                KioError::io(error.to_string(), directory.display().to_string())
            })?;
            state.visit_entry();
            if state.exceeded_bounds {
                return Ok(hashes);
            }
            let path = entry.path();
            let file_type = entry
                .file_type()
                .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?;
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
            if relative == "tombstones" && directory == base && leaf == "lifecycle-epoch" {
                // `.kio/tombstones/lifecycle-epoch` is the monotonic lifecycle
                // counter (03 §4.1 / 05 §3.5), not a marker record — it lives at
                // the inventory root, outside the fan-out namespace.
                continue;
            }
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
        Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
    };
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Ok(false);
    }
    #[cfg(windows)]
    if !kio_core::cas::windows_directory_is_real(path)
        .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?
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
    let head_path = repo.kio_dir().join("HEAD");
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
    for relative in ["refs/heads", "refs/tags-v1"] {
        let base = repo.kio_dir().join(relative);
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
                if relative == "refs/tags-v1" && entry.file_name() == "names.jsonl" {
                    // §C (PB07-09): names.jsonl co-resides in refs/tags-v1/
                    // (03 §2 L80) but is a ledger, not a tag ref — its own
                    // verification lives in `verify_names_jsonl`, not here.
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

// ===========================================================================
// `kio repair verify-objects --prune-orphans` (step4b-contract-tests-p2b.md
// §E, U43, 10-operations.md §7.5.1 L586-626).
// ===========================================================================

#[derive(Debug, Default, Serialize)]
pub struct PruneOrphansReport {
    /// `"pruned"` or `"blocked"` (PB15 fail-closed refusal).
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub blocked_by: Option<String>,
    pub pruned_prepared_count: u64,
    pub pruned_image_count: u64,
    pub pruned_open_cache_count: u64,
}

/// H2-4 (R24b, 3/3 系統一致・うち 2 件 fatal): the exact set a prune will
/// delete.
///
/// The confirmation prompt 06 §1 requires is only meaningful if the set the
/// user approves is the set that gets deleted. Previously `prune_orphans` was
/// called twice — once to count, once to delete — and re-derived the targets
/// each time, so anything that became an orphan in between was deleted without
/// ever having been shown. This type is the binding: [`prune_orphans_plan`]
/// computes it, the prompt enumerates it, and [`prune_orphans_apply`] deletes
/// nothing that is not in it.
#[derive(Debug, Default)]
pub struct PruneOrphansPlan {
    pub status: String,
    pub blocked_by: Option<String>,
    pub prepared: Vec<String>,
    pub images: Vec<String>,
    pub cache_dirs: Vec<PathBuf>,
}

impl PruneOrphansPlan {
    fn blocked(reason: &str) -> Self {
        Self {
            status: "blocked".to_owned(),
            blocked_by: Some(reason.to_owned()),
            ..Default::default()
        }
    }

    #[must_use]
    pub fn is_blocked(&self) -> bool {
        self.status == "blocked"
    }

    /// The targets as `(kind, label)` pairs, for the confirmation prompt's
    /// enumeration (06 §1: 削除対象を先に列挙して見せてから問う).
    #[must_use]
    pub fn target_lines(&self) -> Vec<String> {
        let mut lines = Vec::new();
        for hash in &self.prepared {
            lines.push(format!("prepared  {hash}"));
        }
        for hash in &self.images {
            lines.push(format!("image     {hash}"));
        }
        for dir in &self.cache_dirs {
            lines.push(format!("cache     {}", dir.display()));
        }
        lines
    }

    fn to_blocked_report(&self) -> PruneOrphansReport {
        PruneOrphansReport {
            status: self.status.clone(),
            blocked_by: self.blocked_by.clone(),
            ..Default::default()
        }
    }
}

/// Delete exactly what [`prune_orphans_plan`] listed — never a re-derived set.
///
/// The counts report what was actually removed, which can be lower than the
/// plan's if something disappeared in between (another process, a concurrent
/// `gc`). Lower is safe; the invariant that matters is that nothing OUTSIDE
/// the plan is touched.
pub fn prune_orphans_apply(
    repo: &Repository,
    plan: &PruneOrphansPlan,
) -> Result<PruneOrphansReport> {
    if plan.is_blocked() {
        return Ok(plan.to_blocked_report());
    }
    let store = ObjectStore::new(repo.kio_dir());
    let mut pruned_prepared = 0u64;
    for hash in &plan.prepared {
        if store
            .remove_content(ContentObjectKind::Prepared, hash)
            .unwrap_or(false)
        {
            pruned_prepared += 1;
        }
    }
    let mut pruned_images = 0u64;
    for hash in &plan.images {
        if store
            .remove_content(ContentObjectKind::Image, hash)
            .unwrap_or(false)
        {
            pruned_images += 1;
        }
    }
    let mut pruned_cache = 0u64;
    for dir in &plan.cache_dirs {
        if dir.exists() && fs::remove_dir_all(dir).is_ok() {
            pruned_cache += 1;
        }
    }
    Ok(PruneOrphansReport {
        status: "pruned".to_owned(),
        blocked_by: None,
        pruned_prepared_count: pruned_prepared,
        pruned_image_count: pruned_images,
        pruned_open_cache_count: pruned_cache,
    })
}

/// PB12-17 (§E): `kio repair verify-objects --prune-orphans`.
///
/// **Implemented this session**: PB13 (orphan prepared/image — referenced by
/// no live manifest across the FULL reachable commit history, not just HEAD),
/// two of PB15's four fail-closed blocker conditions (active purge journal;
/// pending/running task), and PB17 (open-cache residue for canonically
/// `purged`/`erased` raw_hashes, image cache included and type-separated per
/// `open/image/<digest64>/`).
///
/// **NOT implemented this session — documented gap, not a silent omission**:
/// PB14/16 (staging-root descriptor 3-way classification and the terminal-
/// task escape hatch — depends on staging-root/task-descriptor internals this
/// session did not have scope to research safely) and the remaining two of
/// PB15's four blockers (state 0/1 `batch_requests` rows, which need
/// cost-ledger.sqlite schema this module does not touch; unfinalized-manifest
/// progress, which needs the `normalize.manifest_hash` prerequisite §B defers
/// this session). Callers must NOT treat this function's `"pruned"` status as
/// a complete PB15 fail-closed guarantee — it is a conservative subset that
/// only ever deletes strictly-unreferenced prepared/image/cache objects, never
/// a false-positive orphan, but it can still run while one of the two
/// unimplemented blocker conditions is true.
/// This computes the deletion set; it removes nothing. [`prune_orphans_apply`]
/// does the removing, and only of what this returned — see [`PruneOrphansPlan`]
/// for why the two are split (H2-4).
pub fn prune_orphans_plan(repo: &Repository) -> Result<PruneOrphansPlan> {
    let purge = PurgeState::new(repo.kio_dir());
    if purge.read_journal()?.is_some() {
        return Ok(PruneOrphansPlan::blocked("active_purge_journal"));
    }
    let tasks = kio_pipeline::task::TaskStore::new(repo.kio_dir())
        .all()
        .map_err(pipeline_to_kio)?;
    if tasks.iter().any(|task| {
        matches!(
            task.status,
            kio_pipeline::task::TaskStatus::Pending | kio_pipeline::task::TaskStatus::Running
        )
    }) {
        return Ok(PruneOrphansPlan::blocked("non_terminal_task"));
    }

    let invocation_time = now_utc_seconds();
    let mut root_state = State::default();
    let roots = commit_roots(repo, &mut root_state)?;
    if root_state.exceeded_bounds || !root_state.findings.is_empty() {
        // A ref/inventory anomaly means the live set below cannot be trusted
        // — refuse to prune rather than risk deleting something still live.
        return Ok(PruneOrphansPlan::blocked("ref_inventory_unsafe"));
    }
    let mut commits = BTreeMap::<String, CommitObject>::new();
    let mut trees = BTreeMap::<String, TreeObject>::new();
    let mut reachable = BTreeSet::<String>::new();
    let mut queue: VecDeque<String> = roots.into_iter().collect();
    while let Some(hash) = queue.pop_front() {
        if !reachable.insert(hash.clone()) {
            continue;
        }
        let commit = repo.read_commit(&hash)?;
        queue.extend(commit.parents.iter().cloned());
        if let Ok(tree) = repo.read_tree(&commit.tree) {
            trees.insert(commit.tree.clone(), tree);
        }
        commits.insert(hash, commit);
    }

    let mut live_prepared = BTreeSet::<String>::new();
    let mut live_images = BTreeSet::<String>::new();
    for commit_hash in &reachable {
        let Some(commit) = commits.get(commit_hash) else {
            continue;
        };
        let Some(tree) = trees.get(&commit.tree) else {
            continue;
        };
        for entry in &tree.entries {
            let Some(normalize) = &entry.normalize else {
                continue;
            };
            let Ok(instance) = load_validated_normalized_instance(
                repo.kio_dir(),
                &entry.raw_hash,
                &normalize.tool_profile_hash,
                normalize.gen,
            ) else {
                // A missing/corrupt normalized instance is fsck's concern
                // (`kio repair verify-objects` without `--prune-orphans`);
                // prune-orphans conservatively treats it as "cannot prove
                // orphan-ness" rather than compounding a corruption finding
                // with a deletion.
                continue;
            };
            for unit_manifest in &instance.manifest.units {
                live_prepared.insert(unit_manifest.prepared_hash.clone());
            }
            for unit in &instance.units {
                let _ =
                    collect_unit_image_references(&unit.metadata, &unit.markdown, &mut live_images);
            }
        }
    }

    let mut prepared_targets = Vec::new();
    for hash in inventory_content_dir(repo.kio_dir(), ContentObjectKind::Prepared)? {
        if !live_prepared.contains(&hash) {
            prepared_targets.push(hash);
        }
    }
    let mut image_targets = Vec::new();
    for hash in inventory_content_dir(repo.kio_dir(), ContentObjectKind::Image)? {
        if !live_images.contains(&hash) {
            image_targets.push(hash);
        }
    }

    // PB17: open-cache residue for raw_hashes whose canonical final event is
    // `purged`/`erased` (the publish-then-check crash window, 05 §4.2), plus
    // any image cache entry no live manifest references (mirrors the
    // prepared/image CAS orphan judgment above; the raw/image cache-type
    // separation itself is C-territory, out of this contract's scope — PB17
    // only fixes that `--prune-orphans` triggers the cleanup).
    let mut cache_targets: Vec<PathBuf> = Vec::new();
    let mut marker_state = State::default();
    let tombstone_hashes = marker_inventory(repo.kio_dir(), "tombstones", &mut marker_state)?;
    let receipt_hashes =
        marker_inventory(repo.kio_dir(), "purge/erase-receipts", &mut marker_state)?;
    for raw_hash in tombstone_hashes.union(&receipt_hashes) {
        let lookup = canonical_lookup(
            &purge,
            raw_hash,
            &commits,
            &trees,
            &reachable,
            &invocation_time,
        );
        let retired = matches!(
            lookup.canonical.map(|canonical| canonical.event.kind),
            Some(EventKind::Purged) | Some(EventKind::Erased)
        );
        if !retired {
            continue;
        }
        if let Ok(digest) = kio_core::cas::hash_path_component(raw_hash) {
            let cache_dir = crate::cache_home().join("kio/open").join(digest);
            if cache_dir.exists() {
                cache_targets.push(cache_dir);
            }
        }
    }
    let image_cache_root = crate::cache_home().join("kio/open/image");
    if let Ok(entries) = fs::read_dir(&image_cache_root) {
        for entry in entries.flatten() {
            let leaf = entry.file_name().to_string_lossy().into_owned();
            let candidate_hash = format!("sha256:{leaf}");
            if is_hash(&candidate_hash) && !live_images.contains(&candidate_hash) {
                cache_targets.push(entry.path());
            }
        }
    }

    Ok(PruneOrphansPlan {
        status: "pruned".to_owned(),
        blocked_by: None,
        prepared: prepared_targets,
        images: image_targets,
        cache_dirs: cache_targets,
    })
}

/// Non-recursive fan-out inventory of one `ContentObjectKind` directory —
/// lighter-weight than `inventory()` (no byte/object bounds accounting,
/// `--prune-orphans` is an explicit maintenance operation, not the routine
/// fsck hot path).
fn inventory_content_dir(kio_dir: &Path, kind: ContentObjectKind) -> Result<BTreeSet<String>> {
    let base = kio_dir.join("objects").join(kind.directory());
    let mut hashes = BTreeSet::new();
    if !base.exists() {
        return Ok(hashes);
    }
    let mut stack = vec![base];
    while let Some(directory) = stack.pop() {
        for entry in fs::read_dir(&directory)
            .map_err(|error| KioError::io(error.to_string(), directory.display().to_string()))?
        {
            let entry = entry.map_err(|error| {
                KioError::io(error.to_string(), directory.display().to_string())
            })?;
            let path = entry.path();
            let file_type = entry
                .file_type()
                .map_err(|error| KioError::io(error.to_string(), path.display().to_string()))?;
            if file_type.is_dir() {
                stack.push(path);
                continue;
            }
            let leaf = entry.file_name().to_string_lossy().into_owned();
            let digest = leaf.strip_prefix("sha256:").unwrap_or(&leaf);
            let hash = format!("sha256:{digest}");
            if is_hash(&hash) {
                hashes.insert(hash);
            }
        }
    }
    Ok(hashes)
}

// ===========================================================================
// `kio repair registry-prune` (step4b-contract-tests-p2b.md §H, U46,
// 10-operations.md §3 L291-293).
// ===========================================================================

#[derive(Debug, Default, Serialize)]
pub struct RegistryPruneReport {
    pub pruned_count: u64,
}

/// PB25: delete registry rows whose `.kio` is unreachable (no re-init, no
/// re-discovery possible) — NOT rows that are merely live-duplicated (PB21's
/// concern; dedupe there is a user decision, never automatic here). A row is
/// unreachable when `open_scope_from_hint` cannot open it AT ALL (the `.kio`
/// itself does not validate), independent of whether its `scope_id` matches
/// what the registry row claims (a mismatched-but-openable `.kio` is a stale
/// registration for a DIFFERENT purpose — R15-3's `retire_stale_kio_path`
/// already owns that case on the next `init`/`index`, not this command).
/// `dry_run` counts the rows that WOULD be retired without touching the
/// registry — the preview half of 06 §1's required confirmation prompt.
/// H2-4/H2-6: the exact registry rows a prune will retire.
#[derive(Debug, Default)]
pub struct RegistryPrunePlan {
    /// `(scope_id, kio_path, root_path)` per row.
    pub rows: Vec<(String, String, String)>,
}

impl RegistryPrunePlan {
    #[must_use]
    pub fn target_lines(&self) -> Vec<String> {
        self.rows
            .iter()
            .map(|(scope_id, _, root_path)| format!("registry  {scope_id}  {root_path}"))
            .collect()
    }
}

/// Compute which registry rows are unreachable. Removes nothing.
pub fn registry_prune_plan() -> Result<RegistryPrunePlan> {
    let registry = RegistryDb::open_default().map_err(index_to_kio)?;
    let mut rows = Vec::new();
    for entry in registry.all_entries().map_err(index_to_kio)? {
        if crate::open_scope_from_hint(&entry.root_path).is_none() {
            rows.push((entry.scope_id, entry.kio_path, entry.root_path));
        }
    }
    Ok(RegistryPrunePlan { rows })
}

/// Retire exactly the rows [`registry_prune_plan`] listed.
///
/// H2-6 (R24b terra-002, fatal): re-scanning here instead would let a row that
/// became unreachable AFTER the user saw the preview be deleted without ever
/// having been shown.
pub fn registry_prune_apply(plan: &RegistryPrunePlan) -> Result<RegistryPruneReport> {
    let registry = RegistryDb::open_default().map_err(index_to_kio)?;
    let mut pruned = 0u64;
    for (scope_id, kio_path, _) in &plan.rows {
        registry.remove(scope_id, kio_path).map_err(index_to_kio)?;
        pruned += 1;
    }
    Ok(RegistryPruneReport {
        pruned_count: pruned,
    })
}

/// LC8-LC10 (§C): canonical final event across both markers for `raw_hash`,
/// after LC9's "only validated markers participate" gate. A marker whose
/// `events[]` fails structural (`kio_core::purge`, already applied by
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
    let canonical = match canonical_final_event(tombstone_tail.as_ref(), receipt_tail.as_ref()) {
        Ok(canonical) => canonical,
        Err(error) => {
            // Keep malformed tails out of ordering and report them through
            // the existing per-marker corruption findings.
            let reason = error.to_string();
            if tombstone_tail.is_some_and(|event| event.lifecycle_epoch.is_none()) {
                tombstone_error = Some(reason.clone());
            }
            if receipt_tail.is_some_and(|event| event.lifecycle_epoch.is_none()) {
                receipt_error = Some(reason);
            }
            None
        }
    };
    CanonicalLookup {
        canonical,
        tombstone_error,
        receipt_error,
    }
}

/// LC17/LC18/LC20/LC21 (10 §7.5.1): the DAG-bound semantic checks on top of
/// `kio_core::purge`'s structural validation (kind closure, required-field
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
    // R23-11: the type / purged_raws-membership / at-equality / not-future
    // checks are the shared validator (`kio_core::purge::verify_marker_binding`)
    // also used by the resolver's `read_tombstone` wrapper and
    // `PurgeState::begin`'s re-purge short-circuit — only the
    // ref-reachability check above (this module's own bounded all-parent
    // walk) stays local, matching that function's documented
    // "resolver/re-purge-weight vs fsck-weight" split.
    kio_core::purge::verify_marker_binding(raw_hash, event, commit, invocation_time)
        .map_err(|error| error.to_string())
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

/// LC27/LC29/LC35/LC36 (R23-08): search the ref-reachable set for a commit
/// that causally republished `raw_hash` after `purge_in_commit` — a strict
/// descendant of it whose tree, when present, actually carries a live leaf
/// for `raw_hash` (10-operations.md §7.5.1's "resurrection_commit の
/// verified tree が同一 raw_hash の leaf を含むことを tree 存置時に限り
/// 検証する" — an ancestry-only match could pick an unrelated LATER commit
/// that never republished this raw at all, which `validate_retired_event`
/// would then flag as corruption on the very next fsck run: this function
/// used to be the one caller that skipped its own module's leaf check). A
/// tree that is not present at all (shallow-discarded — an `auto`-type
/// publication commit can lose its tree to shallow GC) does not penalize
/// the candidate, matching `validate_retired_event`'s own carve-out.
/// Deterministic (lexicographically smallest hash) when more than one
/// candidate exists. Returns the candidate's own `created_at` alongside its
/// hash — the backfilled `retired` event's `at` must be that commit's
/// `created_at` (05-runtime.md §3.5's "その event の commit created_at と
/// 一致"), never the fsck invocation's own clock.
fn find_republication_commit(
    raw_hash: &str,
    purge_in_commit: &str,
    commits: &BTreeMap<String, CommitObject>,
    trees: &BTreeMap<String, TreeObject>,
    reachable: &BTreeSet<String>,
) -> Option<(String, String)> {
    reachable
        .iter()
        .filter(|candidate| {
            candidate.as_str() != purge_in_commit
                && commits.get(candidate.as_str()).is_some_and(|commit| {
                    is_ancestor(commits, purge_in_commit, candidate)
                        && trees.get(&commit.tree).is_none_or(|tree| {
                            tree.entries.iter().any(|entry| entry.raw_hash == raw_hash)
                        })
                })
        })
        .min()
        .cloned()
        .map(|winner| {
            let created_at = commits
                .get(&winner)
                .expect("filtered candidates are always present in `commits`")
                .created_at
                .clone();
            (winner, created_at)
        })
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
    while let Some(index) = remaining.find("kio://") {
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
            Err(error) if error.error_code() == "KIO-E-STORE-OBJECT-OVERSIZED-001" => {
                return Ok(RawRecovery::LimitExceeded)
            }
            Err(error) => return Err(error),
        },
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(RawRecovery::Missing(0))
        }
        Err(error) => return Err(KioError::io(error.to_string(), path.display().to_string())),
    };
    if hash_bytes(&bytes) != expected_hash {
        return Ok(RawRecovery::Missing(bytes.len() as u64));
    }
    Ok(RawRecovery::Candidate(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;
    use kio_core::dag::{CommitStats, CommitType, TreeEntry};

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
            kio_core::purge::PurgeReason::Legal,
            "user",
            1,
        )
    }

    /// R23-08 test helper: [`commit`], parameterized on `tree`/`parents` so a
    /// candidate republication commit's tree membership and ancestry can be
    /// controlled independently.
    fn commit_with_tree(
        kind: CommitType,
        created_at: &str,
        tree: &str,
        parents: Vec<String>,
    ) -> CommitObject {
        CommitObject::new(
            tree.to_owned(),
            parents,
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

    #[test]
    fn r23_08_find_republication_commit_requires_a_raw_leaf_and_returns_created_at() {
        let purge_commit_hash = hash('c');
        let target_raw = hash('9');
        let other_raw = hash('8');
        let purge_created_at = "2026-07-13T00:00:00Z";
        let commits_only_purge = BTreeMap::from([(
            purge_commit_hash.clone(),
            purged_commit(purge_created_at, vec![target_raw.clone()]),
        )]);

        // A candidate that is ref-reachable and a strict descendant of the
        // purge commit, but whose tree does NOT carry a leaf for the target
        // raw_hash, must be rejected -- ancestry alone is not enough (it
        // could be an unrelated later commit that never republished this
        // raw at all).
        let bad_candidate_hash = hash('d');
        let bad_tree_hash = hash('e');
        let mut commits = commits_only_purge.clone();
        commits.insert(
            bad_candidate_hash.clone(),
            commit_with_tree(
                CommitType::Auto,
                "2026-07-14T00:00:00Z",
                &bad_tree_hash,
                vec![purge_commit_hash.clone()],
            ),
        );
        let trees = BTreeMap::from([(
            bad_tree_hash.clone(),
            TreeObject {
                entries: vec![TreeEntry::raw_file("unrelated.txt", other_raw.clone()).unwrap()],
                object_type: "tree".to_owned(),
            },
        )]);
        let reachable = BTreeSet::from([purge_commit_hash.clone(), bad_candidate_hash.clone()]);
        assert!(find_republication_commit(
            &target_raw,
            &purge_commit_hash,
            &commits,
            &trees,
            &reachable,
        )
        .is_none());

        // A candidate whose tree DOES carry the leaf is accepted, and its
        // OWN `created_at` -- not the caller's invocation time -- is
        // returned alongside its hash (R23-08).
        let good_candidate_hash = hash('f');
        let good_tree_hash = hash('0');
        let good_created_at = "2026-07-15T00:00:00Z";
        commits.insert(
            good_candidate_hash.clone(),
            commit_with_tree(
                CommitType::Auto,
                good_created_at,
                &good_tree_hash,
                vec![purge_commit_hash.clone()],
            ),
        );
        let mut trees_with_good = trees.clone();
        trees_with_good.insert(
            good_tree_hash.clone(),
            TreeObject {
                entries: vec![TreeEntry::raw_file("resurrected.txt", target_raw.clone()).unwrap()],
                object_type: "tree".to_owned(),
            },
        );
        let reachable_both = BTreeSet::from([
            purge_commit_hash.clone(),
            bad_candidate_hash.clone(),
            good_candidate_hash.clone(),
        ]);
        let (winner, winner_created_at) = find_republication_commit(
            &target_raw,
            &purge_commit_hash,
            &commits,
            &trees_with_good,
            &reachable_both,
        )
        .expect("a valid resurrection candidate exists");
        assert_eq!(winner, good_candidate_hash);
        assert_eq!(winner_created_at, good_created_at);

        // A candidate whose tree is absent (shallow-discarded) is not
        // penalized -- "tree 存置時に限り検証する" (05-runtime.md §3.5 /
        // 10-operations.md §7.5.1).
        let shallow_candidate_hash = hash('1');
        let shallow_tree_hash = hash('2');
        let mut commits_shallow = commits_only_purge.clone();
        commits_shallow.insert(
            shallow_candidate_hash.clone(),
            commit_with_tree(
                CommitType::Auto,
                "2026-07-16T00:00:00Z",
                &shallow_tree_hash,
                vec![purge_commit_hash.clone()],
            ),
        );
        let reachable_shallow =
            BTreeSet::from([purge_commit_hash.clone(), shallow_candidate_hash.clone()]);
        let (winner, _) = find_republication_commit(
            &target_raw,
            &purge_commit_hash,
            &commits_shallow,
            &BTreeMap::new(), // no trees inventoried -- shallow
            &reachable_shallow,
        )
        .expect("a shallow-tree candidate is still accepted (tree absent skips the leaf check)");
        assert_eq!(winner, shallow_candidate_hash);
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
        let head_before = std::fs::read(repo.kio_dir().join("HEAD")).unwrap();

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
            std::fs::read(repo.kio_dir().join("HEAD")).unwrap(),
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
        let purge = PurgeState::new(repo.kio_dir());
        purge
            .begin(
                vec![hash_bytes(contents)],
                kio_core::purge::PurgeReason::Legal,
                kio_core::purge::TombstoneMode::Default,
                "user",
                "2026-07-13T00:00:01Z",
                1,
                hash_bytes(b"planned commit placeholder"),
                hash_bytes(b"planned closure placeholder"),
                kio_core::scope::new_ulid(dir.path()),
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
        let kio_dir = dir.path().join(".kio");
        std::fs::create_dir(&kio_dir).unwrap();
        let store = ObjectStore::new(&kio_dir);
        let hash = store.write_raw(b"direct prepared bytes").unwrap();
        assert_eq!(verify_prepared_reference(&store, &hash, true).unwrap(), 0);

        let digest = hash.strip_prefix("sha256:").unwrap();
        let corrupt = kio_dir
            .join("objects/prepared")
            .join(&digest[..2])
            .join(&digest[2..4])
            .join(digest);
        std::fs::create_dir_all(corrupt.parent().unwrap()).unwrap();
        std::fs::write(&corrupt, b"corrupt prepared bytes").unwrap();
        assert!(verify_prepared_reference(&store, &hash, true).is_err());
    }

    /// A tag ref pointing at a hash with no commit object behind it is a
    /// dangling root, not a silently-skipped ref.
    #[test]
    fn a_tag_ref_to_a_missing_commit_is_a_finding() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("doc.md"), "tag target").unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        repo.snapshot(Some("fixture"), Some("2026-07-13T00:00:00Z"))
            .unwrap();
        let tag = repo
            .kio_dir()
            .join("refs/tags-v1")
            .join(kio_core::portable::portable_tag_leaf("Release"));
        std::fs::create_dir_all(tag.parent().unwrap()).unwrap();
        std::fs::write(&tag, hash('f')).unwrap();

        let report = verify_objects(&repo).unwrap();
        assert!(report
            .remaining_findings
            .iter()
            .any(|finding| finding.object_hash == hash('f')));
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
        let raw_path = ObjectStore::new(repo.kio_dir())
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
        let extra = repo.kio_dir().join("objects/raw/fe/ed/empty-directory");
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

    /// H2-4 (R24b, 3/3 系統一致・うち 2 件 fatal): the plan BINDS the deletion.
    ///
    /// `repair --prune-orphans` used to count with one scan, ask, then delete
    /// with a SECOND scan that re-derived the targets. Anything that became an
    /// orphan between the two — another process finishing, a concurrent
    /// command — was deleted without ever having been shown to the user. The
    /// prompt 06 §1 requires is only meaningful if what is approved is what is
    /// removed, so `apply` now takes the plan and touches nothing else.
    #[test]
    fn apply_removes_only_what_the_plan_listed() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        repo.snapshot(Some("fixture"), Some("2026-07-13T00:00:00Z"))
            .unwrap();
        let store = ObjectStore::new(repo.kio_dir());

        // An orphan that exists when the user is asked.
        let approved = store
            .write_content_object(ContentObjectKind::Prepared, b"approved orphan")
            .unwrap();
        let plan = prune_orphans_plan(&repo).unwrap();
        assert!(
            plan.prepared.contains(&approved),
            "the fixture orphan must be in the plan: {plan:?}"
        );

        // A NEW orphan appears after the preview — exactly the race the split
        // exists to close.
        let latecomer = store
            .write_content_object(ContentObjectKind::Prepared, b"appeared after the prompt")
            .unwrap();

        let report = prune_orphans_apply(&repo, &plan).unwrap();
        assert_eq!(report.status, "pruned");
        assert!(
            store
                .content_path(ContentObjectKind::Prepared, &latecomer)
                .unwrap()
                .exists(),
            "an orphan created after the preview must NOT be deleted"
        );
        assert!(
            !store
                .content_path(ContentObjectKind::Prepared, &approved)
                .unwrap()
                .exists(),
            "the approved orphan must be deleted"
        );
    }

    /// A blocked plan deletes nothing, and `apply` cannot be talked into it.
    #[test]
    fn a_blocked_plan_applies_nothing() {
        let dir = tempfile::tempdir().unwrap();
        let repo = Repository::init(dir.path()).unwrap();
        repo.snapshot(Some("fixture"), Some("2026-07-13T00:00:00Z"))
            .unwrap();
        let store = ObjectStore::new(repo.kio_dir());
        let orphan = store
            .write_content_object(ContentObjectKind::Prepared, b"orphan")
            .unwrap();

        let blocked = PruneOrphansPlan::blocked("active_purge_journal");
        let report = prune_orphans_apply(&repo, &blocked).unwrap();
        assert_eq!(report.status, "blocked");
        assert_eq!(report.blocked_by.as_deref(), Some("active_purge_journal"));
        assert_eq!(report.pruned_prepared_count, 0);
        assert!(
            store
                .content_path(ContentObjectKind::Prepared, &orphan)
                .unwrap()
                .exists(),
            "a blocked plan must remove nothing"
        );
    }
}
