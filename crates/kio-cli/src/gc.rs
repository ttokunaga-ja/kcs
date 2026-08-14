//! Phase 4 receipt-first shallow sweep CLI orchestration.
//!
//! CAS mutation remains in `kio_core::gc::GcSweepSession`; this module only
//! owns the explicit confirmation, store-lock and SQLite generation boundary.

use std::io::{BufRead, IsTerminal, Read, Write};
use std::time::Instant;

use kio_core::gc::{
    GcInProgressMarker, GcIndexRotation, GcIndexRotationRole, GcIndexState, GcPlan,
    GcReceiptPublication, GcSweepPhase, GcSweepSession,
};
use kio_core::scope::{format_utc_seconds, new_ulid, now_utc_seconds, parse_utc_seconds};
use kio_core::{ExitCode, KioError, Result};
use kio_index::fts::{
    cleanup_stale_bound_gc_index_rotations, exchange_prepared_bound_gc_index,
    prepare_bound_gc_index_rotation, read_bound_gc_index_metadata,
    read_bound_gc_index_rotation_attestation, remove_prepared_bound_gc_index, FtsSchemaConfig,
    FtsTokenizer, GcIndexRotationAttestation, PreparedGcIndexCleanup,
};
use serde::Serialize;
use serde_json::{json, Value};

/// A soft monotonic execution budget.  The executor consults it only after a
/// durable, resumable state transition, so an invocation always makes forward
/// progress and never abandons an in-flight receipt/tree/index operation.
struct ExecutionBudget {
    deadline: Option<Instant>,
    test_checkpoint_limit: Option<u64>,
    completed_checkpoints: u64,
}

impl ExecutionBudget {
    fn new(deadline: Option<Instant>) -> Self {
        Self {
            deadline,
            test_checkpoint_limit: test_runtime_checkpoint_limit(),
            completed_checkpoints: 0,
        }
    }

    fn should_defer_after_checkpoint(&mut self) -> bool {
        self.completed_checkpoints = self.completed_checkpoints.saturating_add(1);
        let synthetic_limit = self
            .test_checkpoint_limit
            .is_some_and(|limit| self.completed_checkpoints >= limit.max(1));
        let elapsed = self
            .deadline
            .is_some_and(|deadline| Instant::now() >= deadline);
        synthetic_limit || elapsed
    }
}

pub(super) fn run(dry_run: bool, yes: bool, json_mode: bool) -> Result<Value> {
    let now = fixed_now()?;
    // Do not canonicalize the public cwd before binding: canonicalization
    // follows a symlink and would erase the evidence that the supplied scope
    // was unsafe.  `GcSweepSession::bind` opens this original absolute name
    // no-follow, retains descriptor capabilities, and then verifies identity.
    let root = std::env::current_dir().map_err(|error| KioError::io(error.to_string(), "."))?;
    // Bind the scope read-only before probing the optional marker so an
    // ordinary non-scope is an invalid-usage error, never an I/O-shaped
    // missing-marker failure.  This has no HEAD self-heal side effect.
    let preview_session = GcSweepSession::bind(root.clone())?;

    if let Some(marker) = preview_session.read_marker()? {
        if dry_run {
            return Ok(recovery_pending_value(&marker));
        }
        // Recovery confirmation must show the complete frozen marker, not a
        // synthesized count summary: it is the exact durable state that will
        // be validated and resumed.
        confirm(&marker, marker.candidates.len(), true, yes, json_mode)?;
        return resume(root, now);
    }

    let preview_plan = preview_session.plan_at(now)?;
    if dry_run {
        return serde_json::to_value(preview_plan)
            .map_err(|error| KioError::schema(error.to_string()));
    }
    let preview_candidate_count = preview_plan.candidates.len();
    // Invocation authorization is independent of candidate count: a JSON or
    // non-TTY caller must always state `--yes` when asking for the mutating
    // command, rather than relying on a currently empty plan.
    // Print the complete plan (policy, candidates, exclusions and both truth
    // bindings) before asking.  The subsequent locked re-plan remains the
    // only mutation authority.
    confirm(
        &preview_plan,
        preview_candidate_count,
        false,
        yes,
        json_mode,
    )?;
    // An authorized empty plan has no destructive effect and needs no marker.
    if preview_candidate_count == 0 {
        return serde_json::to_value(preview_plan)
            .map_err(|error| KioError::schema(error.to_string()));
    }
    // A narrow integration-test seam for the exact preview-to-lock window.
    // It is inert unless explicitly named and has no role in production
    // mutation authority: the locked replan below remains mandatory.
    maybe_wait_at_test_prelock_barrier();
    start(root, now, preview_plan)
}

fn start(root: std::path::PathBuf, now: i64, preview: GcPlan) -> Result<Value> {
    let mut budget = ExecutionBudget::new(None);
    start_with_budget(root, now, preview, &mut budget)
}

fn start_with_budget(
    root: std::path::PathBuf,
    now: i64,
    preview: GcPlan,
    budget: &mut ExecutionBudget,
) -> Result<Value> {
    // Bind before acquiring the lock.  The session's forthcoming bound lock
    // API uses this retained `.kio` descriptor, so a replacement of the
    // public cwd cannot create or remove a victim `.kio/.lock`.
    let session = GcSweepSession::bind(root)?;
    let _lock = session.acquire_store_lock()?;
    // A platform without a descriptor-bound SQLite rotation must reject the
    // operation before publication.  In particular, do not manufacture an
    // active marker/receipts on Windows and then discover that finalization
    // can never complete.
    session.ensure_index_rotation_supported()?;
    let locked = session.plan_at(now)?;
    if !preview.mutation_equivalent(&locked) {
        return Err(plan_changed());
    }
    if session.read_marker()?.is_some() {
        return Err(plan_changed());
    }
    let marker = marker_from_plan(&session, &locked, now)?;
    session.publish_marker(&marker)?;
    inject_fault("after_marker_fsync")?;
    if budget.should_defer_after_checkpoint() {
        return Ok(runtime_limit_value(&marker));
    }
    execute_locked(&session, marker, now, budget)
}

fn resume(root: std::path::PathBuf, now: i64) -> Result<Value> {
    let mut budget = ExecutionBudget::new(None);
    resume_with_budget(root, now, &mut budget)
}

fn resume_with_budget(
    root: std::path::PathBuf,
    now: i64,
    budget: &mut ExecutionBudget,
) -> Result<Value> {
    let session = GcSweepSession::bind(root)?;
    let _lock = session.acquire_store_lock()?;
    session.ensure_index_rotation_supported()?;
    let marker = session.read_marker()?.ok_or_else(plan_changed)?;
    let marker_can_be_discarded = session.marker_can_be_discarded_after_fresh_replan(&marker)?;
    // Marker phase is not evidence of durable progress: a crash can happen
    // after moving to `receipting` but before the first receipt.  Only core's
    // descriptor-bound progress inventory decides whether no irreversible
    // receipt/tree action occurred.  In that case a stale frozen marker may
    // be discarded after a locked fresh plan; otherwise it remains recovery
    // authority and the core validator below must accept it.
    if marker_can_be_discarded {
        let fresh = session.plan_at(now)?;
        if fresh.plan_digest != marker.plan_digest || fresh.truth_digest != marker.truth_digest {
            session.remove_marker(&marker)?;
            return Err(plan_changed());
        }
    }
    // This evaluates current refs, immutable commits and all sharing rules;
    // it permits only matching receipts produced by this frozen marker.
    // Recovery authorization is frozen at the marker start time.  Using the
    // invocation clock here would let an otherwise valid crash cross a
    // retention bucket boundary and become permanently unresumable.
    session.validate_frozen_marker_current_truth(&marker)?;
    execute_locked(&session, marker, now, budget)
}

fn execute_locked(
    session: &GcSweepSession,
    mut marker: GcInProgressMarker,
    _now: i64,
    budget: &mut ExecutionBudget,
) -> Result<Value> {
    if marker.phase == GcSweepPhase::Prepared {
        marker.phase = GcSweepPhase::Receipting;
        session.advance_marker(&marker)?;
        if budget.should_defer_after_checkpoint() {
            return Ok(runtime_limit_value(&marker));
        }
    }
    if marker.phase == GcSweepPhase::Receipting {
        for (index, frozen) in marker.candidates.iter().enumerate() {
            let candidate = kio_core::gc::GcCandidate {
                commit_hash: frozen.commit_hash.clone(),
                tree_hash: frozen.tree_hash.clone(),
                // The session does not act on this field; frozen marker
                // validation binds the canonical commit before receipt write.
                commit_type: kio_core::dag::CommitType::Auto,
                created_at: marker.started_at.clone(),
                policy: "shallow".to_owned(),
                size_bytes: frozen.size_bytes,
            };
            let publication = session.create_receipt(&candidate, marker.started_at.clone())?;
            if index == 0 {
                inject_fault("after_first_receipt")?;
            }
            if publication == GcReceiptPublication::NewlyPublished
                && budget.should_defer_after_checkpoint()
            {
                return Ok(runtime_limit_value(&marker));
            }
        }
        inject_fault("after_all_receipts_before_tree_delete")?;
        // Freeze the exact inode/state/content observations for every
        // operation-owned receipt before the marker can authorize Sweeping.
        // Recovery and each physical tree mutation re-check this digest, so a
        // same-bytes receipt replacement cannot silently rewrite audit truth.
        marker = session.bind_operation_receipts(&marker)?;
        marker.phase = GcSweepPhase::Sweeping;
        session.advance_marker(&marker)?;
        if budget.should_defer_after_checkpoint() {
            return Ok(runtime_limit_value(&marker));
        }
    }
    if marker.phase == GcSweepPhase::Sweeping {
        // Rotation happens before the first potential physical tree deletion.
        if ensure_pre_sweep_index_rotation(session, &mut marker, budget)? {
            return Ok(runtime_limit_value(&marker));
        }
        inject_fault("after_pre_sweep_rotation")?;
        for (index, tree) in marker.trees.iter().enumerate() {
            // A logical generation is not enough to bind the SQLite source:
            // reject a same-generation primary-file replacement before every
            // irreversible tree retirement.
            let attested_index_file = ensure_sweep_index_binding(session, &marker)?;
            // SAFETY: `ensure_sweep_index_binding` has just descriptor-bound
            // the public SQLite leaf and compared its strict, transactionally
            // persisted rotation attestation with this exact frozen marker.
            let permit = unsafe {
                session.authorize_tree_removal_after_index_attestation(
                    &marker,
                    attested_index_file.as_ref(),
                )?
            };
            let removed = session.remove_candidate_tree(&permit, &marker, tree)?;
            if index == 0 {
                inject_fault("after_first_tree_delete")?;
            }
            if removed && budget.should_defer_after_checkpoint() {
                return Ok(runtime_limit_value(&marker));
            }
        }
        inject_fault("after_all_trees_before_final_rotation")?;
        marker.phase = GcSweepPhase::Finalizing;
        session.advance_marker(&marker)?;
        if budget.should_defer_after_checkpoint() {
            return Ok(runtime_limit_value(&marker));
        }
    }
    if marker.phase == GcSweepPhase::Finalizing {
        // `index_final` is an audit record, never a permission slip.  Every
        // finalizing invocation (including crash recovery from a marker that
        // already records a generation) performs and fsyncs a fresh bound
        // rotation before marker completion.  This closes the interval where
        // an attacker could restore a stale index then leave a forged or old
        // `index_final` value that merely happens to match it.
        ensure_final_index_rotation(session, &mut marker)?;
        inject_fault("after_final_rotation_before_marker_removal")?;
        let completed_index_state = index_state_bound(session)?;
        if marker.index_final.as_ref() != Some(&completed_index_state) {
            return Err(index_binding_changed(
                "between the final rotation and marker completion",
            ));
        }
        session.remove_marker(&marker)?;
    }
    Ok(json!({
        "status": "completed",
        "sweep_id": marker.sweep_id,
        "candidate_count": marker.candidates.len(),
        "candidate_tree_count": marker.trees.len(),
        "estimated_bytes": marker.estimated_bytes,
        "index_initial": marker.index_initial,
        "index_pre_sweep": marker.index_pre_sweep,
        "index_final": marker.index_final,
    }))
}

fn marker_from_plan(
    session: &GcSweepSession,
    plan: &GcPlan,
    now: i64,
) -> Result<GcInProgressMarker> {
    GcInProgressMarker::from_plan(
        plan,
        new_ulid(std::path::Path::new(".kio")),
        format_utc_seconds(now),
        index_state_bound(session)?,
    )
}

fn bound_fts_config() -> FtsSchemaConfig {
    FtsSchemaConfig {
        tokenizer: FtsTokenizer::Trigram,
    }
}

fn index_state_bound(session: &GcSweepSession) -> Result<GcIndexState> {
    let kio = session.retained_kio_handle()?;
    let metadata =
        read_bound_gc_index_metadata(&kio, &bound_fts_config()).map_err(super::index_to_kio)?;
    session.assert_public_identity()?;
    let Some(metadata) = metadata else {
        return Ok(GcIndexState::Absent);
    };
    Ok(GcIndexState::Present {
        generation: metadata.metadata.index_generation,
        identity: metadata.file_identity,
    })
}

/// Read-only observer check used by fsck while a sweep marker is active.
/// Structural marker validation alone cannot prove that the pre-delete
/// generation was actually published: bind the current public SQLite leaf to
/// the exact source/target state that recovery would accept, without advancing
/// or cleaning any rotation state.
pub(super) fn validate_marker_index_binding_for_observer(
    session: &GcSweepSession,
    marker: &GcInProgressMarker,
) -> Result<()> {
    let live = index_state_bound(session)?;
    let valid = if let Some(rotation) = &marker.index_rotation {
        live == rotation.source || live == rotation.target
    } else {
        let expected = match marker.phase {
            GcSweepPhase::Prepared | GcSweepPhase::Receipting => &marker.index_initial,
            GcSweepPhase::Sweeping => marker
                .index_pre_sweep
                .as_ref()
                .unwrap_or(&marker.index_initial),
            GcSweepPhase::Finalizing => marker
                .index_final
                .as_ref()
                .or(marker.index_pre_sweep.as_ref())
                .ok_or_else(|| index_binding_changed("during fsck marker validation"))?,
        };
        &live == expected
    };
    if !valid {
        return Err(index_binding_changed("during fsck marker validation"));
    }
    if marker.phase == GcSweepPhase::Sweeping && marker.index_rotation.is_none() {
        let _ = validate_pre_sweep_index_attestation(session, marker)?;
    }
    Ok(())
}

fn ensure_pre_sweep_index_rotation(
    session: &GcSweepSession,
    marker: &mut GcInProgressMarker,
    budget: &mut ExecutionBudget,
) -> Result<bool> {
    if matches!(marker.index_initial, GcIndexState::Absent) {
        if index_state_bound(session)? == GcIndexState::Absent {
            marker.index_pre_sweep = Some(GcIndexState::Absent);
            session.advance_marker(marker)?;
            return Ok(budget.should_defer_after_checkpoint());
        }
        return Err(index_binding_changed("before the pre-sweep rotation"));
    }
    if marker.index_rotation.is_some()
        && complete_marked_index_rotation(
            session,
            marker,
            GcIndexRotationRole::PreSweep,
            Some(budget),
        )?
    {
        return Ok(true);
    }
    // A completed pre-sweep rotation is already the durable barrier required
    // for recovery. Re-rotating it would both churn cursors and hide a forged
    // marker by manufacturing a fresh attestation before validation.
    if marker.index_pre_sweep.is_some() {
        let _ = ensure_sweep_index_binding(session, marker)?;
        return Ok(false);
    }
    cleanup_stale_index_rotations(session, None)?;
    let target = {
        // Persist the exact target before SQLite mutation. A crash after
        // the rotation can then resume only when the retained database is
        // still either the frozen initial state or this target, never an
        // arbitrary replacement generation.
        let source_state = marker
            .index_pre_sweep
            .as_ref()
            .unwrap_or(&marker.index_initial);
        let GcIndexState::Present {
            generation: initial,
            identity,
        } = source_state
        else {
            unreachable!()
        };
        let generation = new_ulid(std::path::Path::new(".kio"));
        let temp_leaf = format!(".gc-index-{}-pre", new_ulid(std::path::Path::new(".kio")));
        let kio = session.retained_kio_handle()?;
        let prepared = prepare_bound_gc_index_rotation(
            &kio,
            &temp_leaf,
            &generation,
            (initial, identity),
            &GcIndexRotationAttestation {
                sweep_id: marker.sweep_id.clone(),
                role: "pre_sweep".to_owned(),
                plan_digest: marker.plan_digest.clone(),
                source_generation: initial.clone(),
                target_generation: generation.clone(),
            },
            &bound_fts_config(),
        )
        .map_err(|_| index_binding_changed("before the pre-sweep rotation"))?;
        inject_fault("after_private_prepare")?;
        let target = GcIndexState::Present {
            generation: prepared.target.metadata.index_generation,
            identity: prepared.target.file_identity,
        };
        marker.index_rotation = Some(GcIndexRotation {
            role: GcIndexRotationRole::PreSweep,
            temp_leaf,
            private_dir_identity: prepared.private_dir_identity,
            source: source_state.clone(),
            source_state_digest: prepared.source_state_digest,
            target: target.clone(),
        });
        session.advance_marker(marker)?;
        inject_fault("after_rotation_marker_persist")?;
        if budget.should_defer_after_checkpoint() {
            return Ok(true);
        }
        target
    };
    let _ = target;
    complete_marked_index_rotation(session, marker, GcIndexRotationRole::PreSweep, Some(budget))
}

fn ensure_final_index_rotation(
    session: &GcSweepSession,
    marker: &mut GcInProgressMarker,
) -> Result<()> {
    if marker.index_rotation.is_some() {
        let _ = complete_marked_index_rotation(session, marker, GcIndexRotationRole::Final, None)?;
    }
    cleanup_stale_index_rotations(session, None)?;
    // A retry after the final-rotation fault point can only advance from the
    // already-recorded final generation.  On the first finalization this is
    // the pre-sweep generation.  Either way, never use `None`: the exact
    // descriptor identity remains an expected precondition for every write.
    let expected = marker
        .index_final
        .as_ref()
        .or(marker.index_pre_sweep.as_ref())
        .ok_or_else(|| index_binding_changed("before the final rotation"))?;
    match expected {
        GcIndexState::Absent => {
            if index_state_bound(session)? != GcIndexState::Absent {
                return Err(index_binding_changed("before the final rotation"));
            }
            marker.index_final = Some(GcIndexState::Absent);
            session.advance_marker(marker)
        }
        GcIndexState::Present {
            generation: expected_generation,
            identity: expected_identity,
        } => {
            let generation = new_ulid(std::path::Path::new(".kio"));
            let temp_leaf = format!(".gc-index-{}-final", new_ulid(std::path::Path::new(".kio")));
            let kio = session.retained_kio_handle()?;
            let prepared = prepare_bound_gc_index_rotation(
                &kio,
                &temp_leaf,
                &generation,
                (expected_generation, expected_identity),
                &GcIndexRotationAttestation {
                    sweep_id: marker.sweep_id.clone(),
                    role: "final".to_owned(),
                    plan_digest: marker.plan_digest.clone(),
                    source_generation: expected_generation.clone(),
                    target_generation: generation.clone(),
                },
                &bound_fts_config(),
            )
            .map_err(|_| index_binding_changed("during the final rotation"))?;
            inject_fault("after_private_prepare")?;
            let target = GcIndexState::Present {
                generation: prepared.target.metadata.index_generation,
                identity: prepared.target.file_identity,
            };
            marker.index_rotation = Some(GcIndexRotation {
                role: GcIndexRotationRole::Final,
                temp_leaf,
                private_dir_identity: prepared.private_dir_identity,
                source: expected.clone(),
                source_state_digest: prepared.source_state_digest,
                target,
            });
            session.advance_marker(marker)?;
            inject_fault("after_rotation_marker_persist")?;
            let _ =
                complete_marked_index_rotation(session, marker, GcIndexRotationRole::Final, None)?;
            Ok(())
        }
    }
}

fn complete_marked_index_rotation(
    session: &GcSweepSession,
    marker: &mut GcInProgressMarker,
    role: GcIndexRotationRole,
    mut budget: Option<&mut ExecutionBudget>,
) -> Result<bool> {
    let rotation = marker
        .index_rotation
        .clone()
        .ok_or_else(|| index_binding_changed("during durable rotation"))?;
    if rotation.role != role {
        return Err(index_binding_changed("during durable rotation"));
    }
    let (
        GcIndexState::Present {
            identity: source, ..
        },
        GcIndexState::Present {
            identity: target, ..
        },
    ) = (&rotation.source, &rotation.target)
    else {
        return Err(index_binding_changed("during durable rotation"));
    };
    let kio = session.retained_kio_handle()?;
    match index_state_bound(session)? {
        state if state == rotation.source => {
            exchange_prepared_bound_gc_index(
                &kio,
                &rotation.temp_leaf,
                &rotation.private_dir_identity,
                source,
                &rotation.source_state_digest,
                target,
            )
            .map_err(|_| index_binding_changed("during durable rotation"))?;
            inject_fault("after_index_exchange")?;
            if budget
                .as_deref_mut()
                .is_some_and(ExecutionBudget::should_defer_after_checkpoint)
            {
                return Ok(true);
            }
        }
        state if state == rotation.target => {}
        _ => return Err(index_binding_changed("during durable rotation")),
    }
    // A prior crash may already have durably cleaned the exchanged old-source
    // leaf.  That is the only third recovery state accepted here.
    let cleanup = remove_prepared_bound_gc_index(
        &kio,
        &rotation.temp_leaf,
        &rotation.private_dir_identity,
        source,
    )
    .map_err(|_| index_binding_changed("during durable rotation"))?;
    inject_fault("after_temp_cleanup_before_marker_advance")?;
    if cleanup == PreparedGcIndexCleanup::Removed
        && budget
            .as_deref_mut()
            .is_some_and(ExecutionBudget::should_defer_after_checkpoint)
    {
        return Ok(true);
    }
    match role {
        GcIndexRotationRole::PreSweep => marker.index_pre_sweep = Some(rotation.target),
        GcIndexRotationRole::Final => marker.index_final = Some(rotation.target),
    }
    marker.index_rotation = None;
    session.advance_marker(marker)?;
    Ok(budget.is_some_and(|budget| budget.should_defer_after_checkpoint()))
}

fn cleanup_stale_index_rotations(session: &GcSweepSession, keep: Option<&str>) -> Result<()> {
    let kio = session.retained_kio_handle()?;
    cleanup_stale_bound_gc_index_rotations(&kio, keep)
        .map_err(|_| index_binding_changed("during private rotation cleanup"))
}

fn index_binding_changed(when: &str) -> KioError {
    KioError::new(
        "KIO-E-STORE-CORRUPT-001",
        format!("GC source index changed {when}"),
        json!({}),
        ExitCode::PermanentFailure,
    )
}

fn ensure_sweep_index_binding(
    session: &GcSweepSession,
    marker: &GcInProgressMarker,
) -> Result<Option<std::fs::File>> {
    let expected = marker
        .index_pre_sweep
        .as_ref()
        .ok_or_else(|| index_binding_changed("before tree retirement"))?;
    if &index_state_bound(session)? != expected {
        return Err(index_binding_changed("before tree retirement"));
    }
    validate_pre_sweep_index_attestation(session, marker)
}

/// A matching generation and inode alone prove only which database is live.
/// This transactionally-written private-copy record proves that this exact
/// database was produced for the frozen receipt operation before any tree can
/// be retired.
fn validate_pre_sweep_index_attestation(
    session: &GcSweepSession,
    marker: &GcInProgressMarker,
) -> Result<Option<std::fs::File>> {
    let (
        GcIndexState::Present {
            generation: source_generation,
            ..
        },
        Some(GcIndexState::Present {
            generation: target_generation,
            ..
        }),
    ) = (&marker.index_initial, marker.index_pre_sweep.as_ref())
    else {
        // There is no SQLite database to attest in the deliberately indexless
        // case. The marker/state equality check above remains authoritative.
        return Ok(None);
    };
    let kio = session.retained_kio_handle()?;
    let Some((live, attestation, attested_file)) =
        read_bound_gc_index_rotation_attestation(&kio, &bound_fts_config())
            .map_err(|_| index_binding_changed("before tree retirement"))?
    else {
        return Err(index_binding_changed("before tree retirement"));
    };
    session.assert_public_identity()?;
    let expected_live = marker.index_pre_sweep.as_ref().expect("matched above");
    if live.metadata.index_generation != *target_generation
        || live.file_identity
            != *match expected_live {
                GcIndexState::Present { identity, .. } => identity,
                GcIndexState::Absent => unreachable!(),
            }
    {
        return Err(index_binding_changed("before tree retirement"));
    }
    if attestation
        != (GcIndexRotationAttestation {
            sweep_id: marker.sweep_id.clone(),
            role: "pre_sweep".to_owned(),
            plan_digest: marker.plan_digest.clone(),
            source_generation: source_generation.clone(),
            target_generation: target_generation.clone(),
        })
    {
        return Err(index_binding_changed("before tree retirement"));
    }
    Ok(Some(attested_file))
}

fn fixed_now() -> Result<i64> {
    let now = now_utc_seconds();
    parse_utc_seconds(&now)
        .ok_or_else(|| KioError::schema("current time is not canonical UTC seconds"))
}

fn runtime_limit_value(marker: &GcInProgressMarker) -> Value {
    json!({
        "status": "deferred",
        "reason": "max_runtime_seconds",
        "recovery_pending": true,
        "sweep_id": marker.sweep_id,
        "phase": marker.phase,
        "candidate_count": marker.candidates.len(),
        "candidate_tree_count": marker.trees.len(),
        "estimated_bytes": marker.estimated_bytes,
        "index_initial": marker.index_initial,
        "index_pre_sweep": marker.index_pre_sweep,
        "index_final": marker.index_final,
    })
}

#[cfg(debug_assertions)]
fn test_runtime_checkpoint_limit() -> Option<u64> {
    std::env::var("KIO_TEST_GC_RUNTIME_CHECKPOINTS")
        .ok()?
        .parse()
        .ok()
}

#[cfg(not(debug_assertions))]
fn test_runtime_checkpoint_limit() -> Option<u64> {
    None
}

fn plan_changed() -> KioError {
    KioError::new(
        "KIO-E-GC-PLAN-CHANGED-001",
        "GC plan changed before the locked recheck; re-run kio gc",
        json!({}),
        ExitCode::PartialFailure,
    )
}

fn recovery_pending_value(marker: &GcInProgressMarker) -> Value {
    json!({
        "status": "recovery_pending",
        "recovery_pending": true,
        "marker": marker,
        "candidate_count": marker.candidates.len(),
        "candidate_tree_count": marker.trees.len(),
        "estimated_bytes": marker.estimated_bytes,
    })
}

fn confirm<T: Serialize>(
    preview: &T,
    candidate_count: usize,
    recovery_pending: bool,
    yes: bool,
    json_mode: bool,
) -> Result<()> {
    if yes {
        return Ok(());
    }
    if json_mode || !std::io::stdin().is_terminal() {
        return Err(KioError::invalid_usage(
            "kio gc requires --yes in JSON or non-interactive mode",
        ));
    }
    let mut stderr = std::io::stderr().lock();
    let rendered = serde_json::to_string_pretty(preview)
        .map_err(|error| KioError::schema(error.to_string()))?;
    writeln!(stderr, "GC shallow-sweep preview:\n{rendered}")
        .map_err(|error| KioError::io(error.to_string(), "stderr"))?;
    write!(
        stderr,
        "Create shallow receipts and remove planned tree objects? [y/N] "
    )
    .map_err(|error| KioError::io(error.to_string(), "stderr"))?;
    stderr
        .flush()
        .map_err(|error| KioError::io(error.to_string(), "stderr"))?;
    let stdin = std::io::stdin();
    let mut reader = std::io::BufReader::new(stdin.lock().take(32));
    let mut answer = String::new();
    reader
        .read_line(&mut answer)
        .map_err(|error| KioError::io(error.to_string(), "stdin"))?;
    if matches!(answer.trim().to_ascii_lowercase().as_str(), "y" | "yes") {
        return Ok(());
    }
    Err(KioError::new(
        "KIO-E-GC-CONFIRMATION-REJECTED-001",
        "GC shallow sweep confirmation was rejected",
        json!({"candidate_count":candidate_count,"recovery_pending":recovery_pending}),
        ExitCode::ConfirmationRejected,
    ))
}

fn inject_fault(point: &str) -> Result<()> {
    if std::env::var("KIO_TEST_GC_FAULT").ok().as_deref() == Some(point) {
        return Err(KioError::new(
            "KIO-E-GC-TEST-INTERRUPTED-001",
            "GC test fault injection interrupted the sweep",
            json!({"point":point}),
            ExitCode::Interrupted,
        ));
    }
    Ok(())
}

fn maybe_wait_at_test_prelock_barrier() {
    let Some(ready_path) = std::env::var_os("KIO_TEST_GC_PRELOCK_READY") else {
        return;
    };
    let ready_path = std::path::PathBuf::from(ready_path);
    if std::fs::write(&ready_path, b"ready").is_err() {
        return;
    }
    let release_path = ready_path.with_extension("release");
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
    while !release_path.exists() && std::time::Instant::now() < deadline {
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
}
