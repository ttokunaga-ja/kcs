//! Validation and deterministic planning for online Markdownize promotion.
//!
//! The online executor owns adapter calls and task lifecycle.  This module starts
//! strictly after a task reached `Done`: it re-opens the typed normalized-instance
//! reference and verifies that the manifest and every unit form one complete,
//! immutable identity before the CLI is allowed to bind that identity into HEAD.

use std::fs;
use std::path::{Path, PathBuf};

use kcs_adapter::tool_lock::{load_tool_lock, tool_lock_hash};
use kcs_core::cas::{is_hash, read_bounded_regular_file};
use kcs_core::{ExitCode, KcsError};
use kcs_pipeline::markdownize::{load_validated_normalized_instance, UnitStatus};
use kcs_pipeline::task::{validate_task_output_ref, TaskDescriptor, TaskOutputRef, TaskStatus};
use kcs_pipeline::{PipelineError, Result as PipelineResult};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::atomic_overwrite_file;
use crate::*;

const PROMOTION_STATE_FILE: &str = "promotion-state.json";
const PROMOTION_STATE_MAX_BYTES: u64 = 1024 * 1024;
const PROMOTION_STATE_SPEC_VERSION: u32 = 1;

/// Durable boundary between immutable HEAD publication and the derived SQLite
/// swap. The staged tool-lock contains no execution/auth authority and is kept in
/// the journal so a crash immediately after HEAD can restore the exact live
/// projection before rebuilding the index.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PromotionState {
    pub spec_version: u32,
    pub previous_head: String,
    pub staged_tool_lock: Value,
    pub staged_tool_lock_hash: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target_head: Option<String>,
}

pub(crate) fn promotion_state_path(kcs_dir: &Path) -> PathBuf {
    kcs_dir.join(PROMOTION_STATE_FILE)
}

pub(crate) fn stage_promotion(
    kcs_dir: &Path,
    previous_head: &str,
    staged_tool_lock: Value,
) -> kcs_core::Result<PromotionState> {
    if !is_hash(previous_head) {
        return Err(KcsError::schema(
            "promotion previous_head must be sha256 lowercase hex",
        ));
    }
    let tool_lock_bytes = serde_json::to_vec_pretty(&staged_tool_lock)
        .map_err(|error| KcsError::schema(error.to_string()))?;
    load_tool_lock(&tool_lock_bytes).map_err(|error| KcsError::schema(error.to_string()))?;
    let staged_tool_lock_hash =
        tool_lock_hash(&staged_tool_lock).map_err(|error| KcsError::schema(error.to_string()))?;
    let state = PromotionState {
        spec_version: PROMOTION_STATE_SPEC_VERSION,
        previous_head: previous_head.to_owned(),
        staged_tool_lock,
        staged_tool_lock_hash,
        target_head: None,
    };
    persist_promotion_state(kcs_dir, &state)?;
    Ok(state)
}

pub(crate) fn load_promotion_state(kcs_dir: &Path) -> kcs_core::Result<Option<PromotionState>> {
    let path = promotion_state_path(kcs_dir);
    match fs::symlink_metadata(&path) {
        Ok(_) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(KcsError::io(error.to_string(), path.display().to_string())),
    }
    let bytes = read_bounded_regular_file(&path, PROMOTION_STATE_MAX_BYTES)?;
    let state: PromotionState = serde_json::from_slice(&bytes)
        .map_err(|error| promotion_recovery_error("invalid", error.to_string()))?;
    validate_promotion_state(&state)?;
    Ok(Some(state))
}

pub(crate) fn persist_promotion_state(
    kcs_dir: &Path,
    state: &PromotionState,
) -> kcs_core::Result<()> {
    validate_promotion_state(state)?;
    let bytes = serde_json::to_vec_pretty(state)
        .map_err(|error| promotion_recovery_error("invalid", error.to_string()))?;
    if bytes.len() as u64 > PROMOTION_STATE_MAX_BYTES {
        return Err(promotion_recovery_error(
            "invalid",
            "promotion state exceeds its byte limit",
        ));
    }
    atomic_overwrite_file(&promotion_state_path(kcs_dir), &bytes)
}

pub(crate) fn publish_staged_tool_lock(
    kcs_dir: &Path,
    state: &PromotionState,
) -> kcs_core::Result<()> {
    validate_promotion_state(state)?;
    let bytes = serde_json::to_vec_pretty(&state.staged_tool_lock)
        .map_err(|error| promotion_recovery_error("invalid", error.to_string()))?;
    atomic_overwrite_file(&kcs_dir.join("tool-lock.json"), &bytes)
}

pub(crate) fn clear_promotion_state(kcs_dir: &Path) -> kcs_core::Result<()> {
    let path = promotion_state_path(kcs_dir);
    match fs::remove_file(&path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(KcsError::io(error.to_string(), path.display().to_string())),
    }
}

pub(crate) fn maybe_inject_promotion_fault(phase: &str) -> kcs_core::Result<()> {
    if std::env::var("KCS_TEST_PROMOTION_FAULT").as_deref() == Ok(phase) {
        return Err(KcsError::new(
            "KCS-E-PROMOTION-FAULT-001",
            "injected promotion publication fault",
            json!({ "phase": phase }),
            ExitCode::Failure,
        ));
    }
    Ok(())
}

fn validate_promotion_state(state: &PromotionState) -> kcs_core::Result<()> {
    if state.spec_version != PROMOTION_STATE_SPEC_VERSION
        || !is_hash(&state.previous_head)
        || !is_hash(&state.staged_tool_lock_hash)
        || state
            .target_head
            .as_deref()
            .is_some_and(|hash| !is_hash(hash))
    {
        return Err(promotion_recovery_error(
            "invalid",
            "promotion state identity is invalid",
        ));
    }
    let bytes = serde_json::to_vec_pretty(&state.staged_tool_lock)
        .map_err(|error| promotion_recovery_error("invalid", error.to_string()))?;
    load_tool_lock(&bytes)
        .map_err(|error| promotion_recovery_error("invalid", error.to_string()))?;
    let actual = tool_lock_hash(&state.staged_tool_lock)
        .map_err(|error| promotion_recovery_error("invalid", error.to_string()))?;
    if actual != state.staged_tool_lock_hash {
        return Err(promotion_recovery_error(
            "invalid",
            "staged tool-lock hash does not match its promotion state",
        ));
    }
    Ok(())
}

pub(crate) fn promotion_recovery_error(phase: &str, message: impl Into<String>) -> KcsError {
    KcsError::new(
        "KCS-E-PROMOTION-RECOVERY-001",
        message,
        json!({ "phase": phase }),
        ExitCode::Failure,
    )
}

/// One complete online result that is safe to consider for promotion.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ValidatedOnlinePromotion {
    pub task_id: String,
    pub input_path: String,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub created_at: String,
    pub bbox_annotation_enabled: bool,
}

/// Validate every completed online Markdownize task and return a deterministic
/// path/time/task ordered promotion pool.
///
/// Partial, failed, pending, baseline, and superseded tasks are intentionally not
/// candidates.  A task that claims `online_adapter_done` but points at malformed or
/// incomplete persisted output is store corruption, not something to silently bind
/// into a commit.
pub(crate) fn validated_online_promotions(
    kcs_dir: &Path,
    tasks: &[TaskDescriptor],
) -> PipelineResult<Vec<ValidatedOnlinePromotion>> {
    let mut promotions = Vec::new();
    for task in tasks {
        if task.task_type != kcs_pipeline::task::TaskType::Markdownize
            || task.status != TaskStatus::Done
            || task.fallback_reason.as_deref() != Some("online_adapter_done")
        {
            continue;
        }

        let output = validate_task_output_ref(kcs_dir, task)?;
        let TaskOutputRef::NormalizedInstance {
            raw_hash,
            tool_profile_hash,
            gen,
            ..
        } = output
        else {
            return Err(PipelineError::corrupt(
                kcs_dir.join("tasks.jsonl").display().to_string(),
                "completed online Markdownize task has no normalized-instance output",
            ));
        };
        let instance =
            load_validated_normalized_instance(kcs_dir, &raw_hash, &tool_profile_hash, gen)?;
        let complete = !instance.manifest.units.is_empty()
            && instance
                .manifest
                .units
                .iter()
                .all(|unit| unit.status == UnitStatus::Done)
            && instance.units.len() == instance.manifest.units.len();
        if !complete {
            return Err(PipelineError::corrupt(
                task.output_ref.clone(),
                "Done online Markdownize task points at an incomplete normalized instance",
            ));
        }
        promotions.push(ValidatedOnlinePromotion {
            task_id: task.task_id.clone(),
            input_path: task.input_path.clone(),
            raw_hash,
            tool_profile_hash,
            gen,
            created_at: task.created_at.clone(),
            bbox_annotation_enabled: task.bbox_annotation_enabled.unwrap_or(false),
        });
    }
    promotions.sort_by(|left, right| {
        left.input_path
            .as_bytes()
            .cmp(right.input_path.as_bytes())
            .then_with(|| left.created_at.cmp(&right.created_at))
            .then_with(|| left.task_id.cmp(&right.task_id))
    });
    Ok(promotions)
}

#[derive(Debug)]
struct OnlinePromotionPlan {
    normalize_by_path: BTreeMap<String, PendingNormalizeRef>,
    active_profile_hash: String,
}

/// Re-derive the promotable online result set from persisted task/instance truth.
/// Mutable task status alone is never enough: `validated_online_promotions`
/// verifies the typed output and complete manifest/unit set, while this boundary
/// rechecks current scope policy, working bytes, HEAD membership, and the adapter's
/// currently resolved immutable profile.
fn plan_online_markdownize_promotion(
    repo: &Repository,
) -> kcs_core::Result<Option<OnlinePromotionPlan>> {
    let task_store = TaskStore::new(repo.kcs_dir());
    let tasks = task_store.all().map_err(pipeline_to_kcs)?;
    let Some(head_hash) = repo.head_commit_hash()? else {
        return Ok(None);
    };
    let head = match repo.read_commit(&head_hash) {
        Ok(commit) => commit,
        Err(error) if is_store_not_found(&error) => return Ok(None),
        Err(error) => return Err(error),
    };
    let head_tree = match repo.read_tree(&head.tree) {
        Ok(tree) => tree,
        Err(error) if is_store_not_found(&error) => return Ok(None),
        Err(error) => return Err(error),
    };
    let head_entries = head_tree
        .entries
        .iter()
        .map(|entry| (entry.path.as_str(), entry))
        .collect::<BTreeMap<_, _>>();
    let max_input_bytes = effective_max_input_bytes(repo);
    // Establish that the task still describes the live HEAD/working identity
    // before opening its normalized output. A corrupt output for the current
    // identity is fatal, but a stale previous generation must not break a later
    // full re-index after the file changed.
    let mut current_tasks = Vec::new();
    for task in tasks {
        if task.task_type != TaskType::Markdownize
            || task.status != TaskStatus::Done
            || task.fallback_reason.as_deref() != Some("online_adapter_done")
        {
            continue;
        }
        let Some(head_entry) = head_entries.get(task.input_path.as_str()) else {
            continue;
        };
        if head_entry.raw_hash != task.input_hash
            || !current_scan_policy_allows_file(repo.root(), &task.input_path)
                .map_err(pipeline_to_kcs)?
        {
            continue;
        }
        let Ok(verified) = read_verified_scan_input(repo.root(), &task.input_path, max_input_bytes)
        else {
            continue;
        };
        if verified.raw_hash != task.input_hash {
            continue;
        }
        ensure_raw_ingest_allowed(repo, &task.input_hash)?;
        current_tasks.push(task);
    }
    let current =
        validated_online_promotions(repo.kcs_dir(), &current_tasks).map_err(pipeline_to_kcs)?;
    if current.is_empty() {
        return Ok(None);
    }

    // A result already bound by HEAD stays authoritative without another model
    // resolution. A not-yet-bound result is promotable only if its immutable hash
    // matches the profile resolved now; this prevents a Done result from an older
    // mutable model alias being promoted after the alias advances.
    let policies_to_resolve = current
        .iter()
        .filter(|candidate| {
            head_entries
                .get(candidate.input_path.as_str())
                .and_then(|entry| entry.normalize.as_ref())
                .is_none_or(|normalize| {
                    normalize.tool_profile_hash != candidate.tool_profile_hash
                        || normalize.gen != candidate.gen
                })
        })
        .map(|candidate| candidate.bbox_annotation_enabled)
        .collect::<BTreeSet<_>>();
    let resolved_profiles = policies_to_resolve
        .into_iter()
        .filter_map(|bbox_enabled| {
            resolve_standard_online_markdownize_profile_with_bbox(
                &repo.scope_id_for_adapter(),
                bbox_enabled,
            )
            .ok()
            .map(|profile| (bbox_enabled, profile))
        })
        .collect::<BTreeMap<_, _>>();

    let mut by_path = BTreeMap::<String, Vec<_>>::new();
    for candidate in current {
        by_path
            .entry(candidate.input_path.clone())
            .or_default()
            .push(candidate);
    }
    let mut selected = Vec::new();
    for (path, candidates) in by_path {
        let resolved = candidates.iter().rev().find(|candidate| {
            resolved_profiles
                .get(&candidate.bbox_annotation_enabled)
                .is_some_and(|profile| candidate.tool_profile_hash == profile.tool_profile_hash)
        });
        let already_bound = candidates.iter().rev().find(|candidate| {
            head_entries
                .get(path.as_str())
                .and_then(|entry| entry.normalize.as_ref())
                .is_some_and(|normalize| {
                    normalize.tool_profile_hash == candidate.tool_profile_hash
                        && normalize.gen == candidate.gen
                })
        });
        if let Some(candidate) = resolved.or(already_bound) {
            selected.push(candidate.clone());
        }
    }
    if selected.is_empty() {
        return Ok(None);
    }
    selected.sort_by(|left, right| left.input_path.as_bytes().cmp(right.input_path.as_bytes()));
    let effective_bbox_policy = bbox_annotation_enabled(repo)?;
    let active_profile_hash = selected
        .iter()
        .rev()
        .filter(|candidate| candidate.bbox_annotation_enabled == effective_bbox_policy)
        .find_map(|candidate| {
            resolved_profiles
                .get(&candidate.bbox_annotation_enabled)
                .filter(|profile| profile.tool_profile_hash == candidate.tool_profile_hash)
                .map(|profile| profile.tool_profile_hash.clone())
        })
        .unwrap_or_else(|| {
            selected
                .iter()
                .rev()
                .find(|candidate| candidate.bbox_annotation_enabled == effective_bbox_policy)
                .or_else(|| selected.last())
                .expect("selected promotion is non-empty")
                .tool_profile_hash
                .clone()
        });
    let normalize_by_path = selected
        .into_iter()
        .map(|candidate| {
            (
                candidate.input_path,
                PendingNormalizeRef {
                    expected_raw_hash: candidate.raw_hash,
                    normalize: NormalizeRef {
                        tool_profile_hash: candidate.tool_profile_hash,
                        gen: candidate.gen,
                    },
                },
            )
        })
        .collect();
    Ok(Some(OnlinePromotionPlan {
        normalize_by_path,
        active_profile_hash,
    }))
}

/// Replace only the Markdownize identity in tool-lock. The entry deliberately
/// carries no URL, command, arguments, credentials, or other execution authority.
fn promoted_markdown_tool_lock(repo: &Repository, profile_hash: &str) -> kcs_core::Result<Value> {
    const TOOL_LOCK_MAX_BYTES: u64 = 1024 * 1024;
    let path = repo.kcs_dir().join("tool-lock.json");
    let bytes = read_bounded_regular_file(&path, TOOL_LOCK_MAX_BYTES)?;
    let mut value: Value =
        serde_json::from_slice(&bytes).map_err(|error| KcsError::schema(error.to_string()))?;
    let online = standard_online_markdownize_profile();
    value["markdown"] = json!({
        "tool_id": online.adapter_id,
        "profile_hash": profile_hash,
        "kind": "online_api",
        "capabilities": online.capability_flags,
    });
    let bytes =
        serde_json::to_vec_pretty(&value).map_err(|error| KcsError::schema(error.to_string()))?;
    load_tool_lock(&bytes).map_err(adapter_to_kcs)?;
    Ok(value)
}

fn materialize_promoted_markdown_tool_lock(
    repo: &Repository,
    profile_hash: &str,
) -> kcs_core::Result<()> {
    let path = repo.kcs_dir().join("tool-lock.json");
    let value = promoted_markdown_tool_lock(repo, profile_hash)?;
    let bytes =
        serde_json::to_vec_pretty(&value).map_err(|error| KcsError::schema(error.to_string()))?;
    atomic_overwrite_file(&path, &bytes)
}

/// Reconcile already-Done online results into an ordinary index's single pending
/// snapshot. This prevents the deterministic baseline pass from demoting a
/// previously promoted file and avoids an extra promotion commit.
pub(super) fn apply_online_promotion_to_index(
    repo: &Repository,
    result: &mut IndexPipelineResult,
) -> kcs_core::Result<()> {
    let Some(plan) = plan_online_markdownize_promotion(repo)? else {
        return Ok(());
    };
    materialize_promoted_markdown_tool_lock(repo, &plan.active_profile_hash)?;
    result.normalize_by_path.extend(plan.normalize_by_path);
    Ok(())
}

/// Publish one deterministic promotion commit for all accepted outputs completed
/// by a batch pass. The repository primitive changes only matching HEAD bindings;
/// unrelated deferred working-tree edits are never captured.
pub(super) fn promote_completed_online_markdownize(repo: &Repository) -> kcs_core::Result<bool> {
    let Some(plan) = plan_online_markdownize_promotion(repo)? else {
        return Ok(false);
    };
    let previous_head = repo
        .head_commit_hash()?
        .ok_or_else(|| KcsError::invalid_usage("cannot promote in an unborn scope"))?;
    let staged_tool_lock = promoted_markdown_tool_lock(repo, &plan.active_profile_hash)?;
    let mut state = stage_promotion(repo.kcs_dir(), &previous_head, staged_tool_lock)?;
    maybe_inject_promotion_fault("before_head")?;
    let outcome = repo.promote_normalize_refs_with_staged_tool_lock(
        Some("online Markdownize promotion"),
        &plan.normalize_by_path,
        &state.staged_tool_lock_hash,
    )?;
    if outcome.noop {
        publish_staged_tool_lock(repo.kcs_dir(), &state)?;
        clear_promotion_state(repo.kcs_dir())?;
        return Ok(false);
    }
    let commit_hash = outcome
        .commit_hash
        .as_ref()
        .ok_or_else(|| promotion_recovery_error("after_head", "promotion commit is missing"))?;
    state.target_head = Some(commit_hash.clone());
    persist_promotion_state(repo.kcs_dir(), &state)?;
    publish_staged_tool_lock(repo.kcs_dir(), &state)?;
    maybe_inject_promotion_fault("after_head")?;
    if let Some(commit_hash) = &outcome.commit_hash {
        append_event_log(
            "KCS-I-COMMIT-CREATED-001",
            "online Markdownize promotion commit created",
            json!({
                "commit_hash": commit_hash,
                "tree_hash": outcome.tree_hash,
                "commit_type": "auto",
            }),
        )?;
    }
    Ok(true)
}

/// Recover the durable half of a promotion publication. A prepared transaction
/// whose HEAD never moved is discarded so the task can be planned again. Once
/// HEAD moved, the exact staged tool-lock is restored and the retained journal
/// makes the required SQLite rebuild explicit to the caller.
pub(super) fn recover_pending_online_promotion(repo: &Repository) -> kcs_core::Result<bool> {
    let Some(mut state) = load_promotion_state(repo.kcs_dir())? else {
        return Ok(false);
    };
    let current_head = repo
        .head_commit_hash()?
        .ok_or_else(|| promotion_recovery_error("invalid", "promotion HEAD is missing"))?;
    if current_head == state.previous_head {
        if state.target_head.is_some() {
            return Err(promotion_recovery_error(
                "invalid",
                "promotion state names a published HEAD but repository HEAD is still its parent",
            ));
        }
        clear_promotion_state(repo.kcs_dir())?;
        return Ok(false);
    }

    if state
        .target_head
        .as_deref()
        .is_some_and(|target| target != current_head)
    {
        return Err(promotion_recovery_error(
            "invalid",
            "repository HEAD diverged from the pending promotion",
        ));
    }
    let commit = repo.read_commit(&current_head)?;
    if commit.parents != [state.previous_head.clone()]
        || commit.commit_type != CommitType::Auto
        || commit.message != "online Markdownize promotion"
        || commit.tool_lock_hash != state.staged_tool_lock_hash
    {
        return Err(promotion_recovery_error(
            "invalid",
            "repository HEAD does not match the pending promotion identity",
        ));
    }
    if state.target_head.is_none() {
        state.target_head = Some(current_head);
        persist_promotion_state(repo.kcs_dir(), &state)?;
    }
    publish_staged_tool_lock(repo.kcs_dir(), &state)?;
    Ok(true)
}

pub(super) fn finish_pending_online_promotion(repo: &Repository) -> kcs_core::Result<()> {
    rebuild_step3_index(repo)?;
    maybe_inject_promotion_fault("after_index_swap")?;
    clear_promotion_state(repo.kcs_dir())
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::fs;

    use kcs_pipeline::markdownize::{
        normalized_instance_dir, persist_normalized_instance, MarkdownizeMode,
        NormalizedInstanceManifest, NormalizedUnitManifestEntry, NormalizedUnitObject, UnitStatus,
    };
    use kcs_pipeline::prepare::{hash_bytes, unit_ref, UnitType};
    use kcs_pipeline::task::{TaskDescriptor, TaskStatus, TaskType};

    use super::validated_online_promotions;

    fn done_task(output_ref: String, raw_hash: String) -> TaskDescriptor {
        TaskDescriptor {
            task_id: "task_01TEST".to_owned(),
            task_type: TaskType::Markdownize,
            mode: Some(MarkdownizeMode::Full),
            input_path: "report.pdf".to_owned(),
            input_hash: raw_hash,
            previous_raw_hash: None,
            parent_run_id: None,
            changed_unit_keys: vec!["page:1".to_owned()],
            output_ref,
            unit_keys: Some(vec!["page:1".to_owned()]),
            status: TaskStatus::Done,
            attempts: 0,
            next_retry_at: None,
            deadline: None,
            heartbeat_at: None,
            fallback_reason: Some("online_adapter_done".to_owned()),
            created_at: "2026-07-13T00:00:00Z".to_owned(),
            bbox_annotation_enabled: Some(true),
            reserved_usd: None,
            reserved_month: None,
            reservation_id: None,
        }
    }

    #[test]
    fn accepts_only_complete_done_online_instances() {
        let dir = tempfile::tempdir().unwrap();
        let kcs_dir = dir.path().join(".kcs");
        fs::create_dir_all(&kcs_dir).unwrap();
        let raw_hash = hash_bytes(b"raw");
        let profile_hash = hash_bytes(b"profile");
        let prepared_hash = hash_bytes(b"prepared");
        let unit_key = "page:1".to_owned();
        let manifest = NormalizedInstanceManifest {
            raw_hash: raw_hash.clone(),
            tool_profile_hash: profile_hash.clone(),
            gen: 0,
            parent_gen: None,
            run_id: "run_01TEST".to_owned(),
            units: vec![NormalizedUnitManifestEntry {
                order: 0,
                unit_key: unit_key.clone(),
                unit_ref: unit_ref(&unit_key),
                unit_type: UnitType::Page,
                status: UnitStatus::Done,
                prepared_hash: prepared_hash.clone(),
                error_kind: None,
            }],
            generated_at: "2026-07-13T00:00:00Z".to_owned(),
        };
        let unit = NormalizedUnitObject {
            unit_key,
            unit_type: UnitType::Page,
            raw_hash: raw_hash.clone(),
            prepared_hash,
            tool_profile_hash: profile_hash.clone(),
            gen: 0,
            mode: MarkdownizeMode::Full,
            markdown: "promoted mock text".to_owned(),
            metadata: BTreeMap::new(),
            reused_from: None,
            generated_at: "2026-07-13T00:00:00Z".to_owned(),
        };
        persist_normalized_instance(&kcs_dir, &manifest, &[unit]).unwrap();
        let output_ref = normalized_instance_dir(&kcs_dir, &raw_hash, &profile_hash, 0)
            .display()
            .to_string();
        let task = done_task(output_ref, raw_hash);
        let planned = validated_online_promotions(&kcs_dir, std::slice::from_ref(&task)).unwrap();
        assert_eq!(planned.len(), 1);
        assert_eq!(planned[0].tool_profile_hash, profile_hash);
        assert!(planned[0].bbox_annotation_enabled);

        let mut partial = task;
        partial.status = TaskStatus::Partial;
        assert!(validated_online_promotions(&kcs_dir, &[partial])
            .unwrap()
            .is_empty());
    }
}
