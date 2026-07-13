//! Full-history purge orchestration.
//!
//! Target discovery is deliberately CAS-backed: path mode walks every parent
//! commit/tree, while raw-hash mode remains usable when unrelated history is
//! shallow.  Mutable manifests and index/cache projections are never accepted as
//! purge truth.

use std::collections::BTreeSet;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use clap::{ArgGroup, Args};
use kcs_core::cas::{is_hash, ContentObjectKind, ObjectKind, ObjectStore};
use kcs_core::dag::CommitType;
use kcs_core::dag::TreeEntry;
use kcs_core::history::HistoryReader;
use kcs_core::purge::{
    BeginOutcome, EraseReceipt, PurgeJournal, PurgePhase, PurgeReason, PurgeState, TombstoneMode,
    TombstoneRecord,
};
use kcs_core::scope::{
    append_event_log, cleanup_orphan_raw_ingest_temps, now_utc_seconds, Repository, StoreLock,
};
use kcs_core::{ExitCode, KcsError, Result};
use kcs_index::fts::{FtsSchemaConfig, FtsTokenizer, SqliteFtsIndex};
use kcs_pipeline::budget::CostLedger;
use kcs_pipeline::markdownize::{
    load_validated_normalized_instance, NormalizedInstanceManifest, NormalizedUnitObject,
};
use kcs_pipeline::task::{TaskStore, TaskType, MAX_TASK_STORE_BYTES};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

const PURGE_REASONS: [&str; 5] = ["legal", "privacy", "misingest", "copyright", "other"];
const VALIDATION_HASH: &str =
    "sha256:0000000000000000000000000000000000000000000000000000000000000000";

#[derive(Debug, Args)]
#[command(group(
    ArgGroup::new("target")
        .required(true)
        .multiple(false)
        .args(["path", "raw_hash"])
))]
pub(crate) struct PurgeArgs {
    /// Logical direct-child path. Every historical raw binding is selected.
    pub(crate) path: Option<PathBuf>,

    /// Exact raw object identity to purge.
    #[arg(long, value_name = "SHA256")]
    pub(crate) raw_hash: Option<String>,

    /// Required legal/operational reason recorded in the purged commit.
    #[arg(long, value_parser = PURGE_REASONS)]
    pub(crate) reason: String,

    /// Leave only the fsck-private non-content erase receipt.
    #[arg(long)]
    pub(crate) erase_tombstone: bool,

    /// Skip the destructive confirmation prompt.
    #[arg(long)]
    pub(crate) yes: bool,
}

pub(crate) fn purge_publication_lock_path(kcs_dir: &Path) -> PathBuf {
    kcs_dir.join("purge-publication.lock")
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PurgePlan {
    /// HEAD observed while deriving the target. It is rechecked under the store
    /// lock before the journal can be created.
    head_commit: String,
    target_raw_hashes: Vec<String>,
    /// Known historical names are audit/log-scrub inputs only, never target
    /// authority. Raw-hash mode intentionally does not require a history walk.
    historical_paths: Vec<String>,
    reason: PurgeReason,
    tombstone_mode: TombstoneMode,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CompletedTerminal {
    purged_in_commit: String,
    tombstone_count: u64,
    erase_receipt_count: u64,
}

#[derive(Debug)]
struct PurgePreview {
    plan: PurgePlan,
    completed: Option<CompletedTerminal>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
struct DeletedCounts {
    raw_objects: u64,
    chunk_objects: u64,
    chunk_ledger_rows: u64,
    sqlite_chunks: u64,
    sqlite_associations: u64,
    sqlite_vectors: u64,
    sqlite_orphan_embeddings: u64,
    normalized_instances: u64,
    normalized_views: u64,
    prepared_objects: u64,
    image_objects: u64,
    tasks: u64,
    reservations: u64,
    manifest_rows: u64,
    unsupported_rows: u64,
    quarantine_rows: u64,
    cache_directories: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
struct SharedArtifactsPreserved {
    prepared_objects: u64,
    image_objects: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
struct PurgeReport {
    purged_in_commit: Option<String>,
    deleted: DeletedCounts,
    shared: SharedArtifactsPreserved,
    tombstone_count: u64,
    erase_receipt_count: u64,
    log_files_scrubbed: u64,
    log_rows_removed: u64,
    log_fields_masked: u64,
}

pub(crate) fn run(args: PurgeArgs) -> Result<Value> {
    let repo = Repository::open_current()?;
    // Orphan cleanup is transaction recovery, not target mutation. Run it under
    // the store lock before preview/working-copy refusal so a tombstoned raw temp
    // is removed even when the requested purge cannot proceed.
    {
        let _store_lock = repo.lock_store()?;
        cleanup_orphan_raw_ingest_temps(repo.kcs_dir())?;
    }
    let preview = preflight(&repo, &args)?;
    confirm(&preview, args.yes)?;
    execute_phase_machine(&repo, &args, &preview)
}

/// Run the durable phase machine. This is kept separate from preview so there
/// is no mutation before confirmation and so an under-lock target re-plan can be
/// compared byte-for-byte with the previewed authority.
fn execute_phase_machine(
    repo: &Repository,
    args: &PurgeArgs,
    preview: &PurgePreview,
) -> Result<Value> {
    let _store_lock = repo.lock_store()?;
    let locked_plan = resolve_plan(repo, args)?;
    if locked_plan != preview.plan {
        return Err(KcsError::new(
            "KCS-E-PURGE-PLAN-CHANGED-001",
            "purge target changed between preview and the locked recheck",
            json!({ "target_raw_count": preview.plan.target_raw_hashes.len() }),
            ExitCode::PartialFailure,
        ));
    }
    // Serialize the visibility barrier and destructive phases against restore's
    // final source recheck/staging/publication window. Lock order is always scope
    // store -> purge publication; restore takes only the latter.
    let _publication_lock = StoreLock::acquire_path(purge_publication_lock_path(repo.kcs_dir()))?;
    // Re-run after reacquiring the store lock: a prior KCS writer could have
    // crashed between preview cleanup and this confirmed phase-machine entry.
    cleanup_orphan_raw_ingest_temps(repo.kcs_dir())?;

    let state = PurgeState::new(repo.kcs_dir());
    let active = state.read_journal()?;
    if let Err(error) =
        refuse_live_working_copy_for_phase(repo, &locked_plan.target_raw_hashes, active.as_ref())
    {
        if let Some(journal) = active
            .as_ref()
            .filter(|journal| journal.phase.is_barrier_visible())
        {
            let report = load_phase_report(repo.kcs_dir())?.unwrap_or_default();
            return Ok(incomplete_report(&locked_plan, journal, &report, &error));
        }
        return Err(error);
    }
    let completed = if active.is_none() {
        inspect_terminal_state(&state, &locked_plan)?
    } else {
        // Terminal records precede physical deletion. Their presence cannot
        // complete a transaction while its resumable journal still exists.
        inspect_terminal_state(&state, &locked_plan)?;
        None
    };
    verify_targets_exist(repo, &locked_plan, active.is_some(), completed.is_some())?;
    if let Some(completed) = completed {
        return Ok(completed_report(&locked_plan, completed));
    }

    let started_at = now_utc_seconds();
    let (mut journal, newly_started) = match state.begin(
        locked_plan.target_raw_hashes.clone(),
        locked_plan.reason,
        locked_plan.tombstone_mode,
        started_at,
    )? {
        BeginOutcome::Started(journal) => (journal, true),
        BeginOutcome::Resumed(journal) => (journal, false),
        BeginOutcome::AlreadyComplete(tombstones) => {
            let completed = CompletedTerminal {
                purged_in_commit: tombstones
                    .first()
                    .map(|record| record.purged_in_commit.clone())
                    .unwrap_or_default(),
                tombstone_count: u64::try_from(tombstones.len()).unwrap_or(u64::MAX),
                erase_receipt_count: 0,
            };
            return Ok(completed_report(&locked_plan, completed));
        }
    };

    if let Err(error) = maybe_inject_fault("prepared") {
        if newly_started {
            state.abort_before_barrier(&journal)?;
        }
        return Err(error);
    }
    let allow_commit_reconcile = journal.phase.is_barrier_visible();
    if journal.phase == PurgePhase::Prepared {
        journal = state.advance_phase(&journal, PurgePhase::BarrierPublished)?;
    }

    let mut report = load_phase_report(repo.kcs_dir())?.unwrap_or_default();
    let result = execute_visible_phases(
        repo,
        &state,
        &locked_plan,
        &mut journal,
        &mut report,
        allow_commit_reconcile,
    );
    match result {
        Ok(()) => Ok(success_report(&locked_plan, &report)),
        Err(error) => Ok(incomplete_report(&locked_plan, &journal, &report, &error)),
    }
}

fn execute_visible_phases(
    repo: &Repository,
    state: &PurgeState,
    plan: &PurgePlan,
    journal: &mut PurgeJournal,
    report: &mut PurgeReport,
    allow_commit_reconcile: bool,
) -> Result<()> {
    maybe_inject_fault("barrier_published")?;

    if journal.phase == PurgePhase::BarrierPublished {
        let commit_hash =
            create_or_reconcile_purged_commit(repo, plan, journal, allow_commit_reconcile)?;
        verify_purged_commit(repo, &commit_hash, &plan.target_raw_hashes)?;
        *journal = state.bind_purged_commit(journal, commit_hash, journal.started_at.clone())?;
    }
    report.purged_in_commit = journal.purged_in_commit.clone();
    publish_terminal_records(state, journal, report)?;
    maybe_inject_fault("purged_commit_created")?;

    if journal.phase == PurgePhase::PurgedCommitCreated {
        delete_content_surfaces(repo, plan, report)?;
        *journal = state.advance_phase(journal, PurgePhase::ContentDeleted)?;
        store_phase_report(repo.kcs_dir(), report)?;
    }
    maybe_inject_fault("content_deleted")?;

    if journal.phase == PurgePhase::ContentDeleted {
        delete_derived_surfaces(repo, plan, report)?;
        *journal = state.advance_phase(journal, PurgePhase::DerivedDeleted)?;
        store_phase_report(repo.kcs_dir(), report)?;
    }
    maybe_inject_fault("derived_deleted")?;

    if journal.phase == PurgePhase::DerivedDeleted {
        scrub_logs(repo, plan, journal, report)?;
        *journal = state.advance_phase(journal, PurgePhase::LogsScrubbed)?;
        store_phase_report(repo.kcs_dir(), report)?;
    }
    maybe_inject_fault("logs_scrubbed")?;

    // Final scrub closes the append race before the visibility barrier is
    // removed. The audit row is identifier-free and is appended while both scrub
    // locks are still covered by `scrub_logs`' own serialized pass.
    finalize_purge(repo, state, plan, journal, report)?;
    Ok(())
}

fn create_or_reconcile_purged_commit(
    repo: &Repository,
    plan: &PurgePlan,
    journal: &PurgeJournal,
    allow_reconcile: bool,
) -> Result<String> {
    let current_head = repo
        .head_commit_hash()?
        .ok_or_else(|| KcsError::invalid_usage("cannot purge an unborn scope"))?;
    let current = repo.read_commit(&current_head)?;
    if allow_reconcile
        && current.commit_type == CommitType::Purged
        && current.message == journal.reason.to_string()
        && current.created_at == journal.started_at
    {
        return Ok(current_head);
    }

    // `purged_snapshot` captures the locked, rechecked working tree and forces a
    // child even if it is byte-identical to its parent. The journal timestamp
    // makes retry after commit-CAS publication deterministic.
    let outcome = repo.purged_snapshot(&plan.reason.to_string(), Some(&journal.started_at))?;
    if outcome.noop
        || outcome.commit.as_ref().map(|commit| commit.commit_type) != Some(CommitType::Purged)
    {
        return Err(KcsError::new(
            "KCS-E-STORE-CORRUPT-001",
            "purged snapshot did not create a protected commit",
            json!({}),
            ExitCode::PermanentFailure,
        ));
    }
    outcome.commit_hash.ok_or_else(|| {
        KcsError::new(
            "KCS-E-STORE-CORRUPT-001",
            "purged snapshot did not return its commit hash",
            json!({}),
            ExitCode::PermanentFailure,
        )
    })
}

fn verify_purged_commit(repo: &Repository, commit_hash: &str, targets: &[String]) -> Result<()> {
    let commit = repo.read_commit(commit_hash)?;
    if commit.commit_type != CommitType::Purged {
        return Err(KcsError::schema(
            "purge journal commit is not commit_type=purged",
        ));
    }
    let tree = repo.read_tree(&commit.tree)?;
    let targets = targets.iter().map(String::as_str).collect::<BTreeSet<_>>();
    if tree
        .entries
        .iter()
        .any(|entry| targets.contains(entry.raw_hash.as_str()))
    {
        return Err(KcsError::new(
            "KCS-E-PURGE-WORKING-COPY-001",
            "purged commit still contains target bytes",
            json!({}),
            ExitCode::PartialFailure,
        ));
    }
    Ok(())
}

fn publish_terminal_records(
    state: &PurgeState,
    journal: &PurgeJournal,
    report: &mut PurgeReport,
) -> Result<()> {
    let commit = journal
        .purged_in_commit
        .as_deref()
        .ok_or_else(|| KcsError::schema("purge journal is missing its commit"))?;
    let purged_at = journal
        .purged_at
        .as_deref()
        .ok_or_else(|| KcsError::schema("purge journal is missing its timestamp"))?;
    for raw_hash in &journal.target_raw_hashes {
        match journal.tombstone_mode {
            TombstoneMode::Default => {
                let record = TombstoneRecord::new(raw_hash, purged_at, journal.reason, commit)?;
                state.publish_tombstone(journal, &record)?;
                report.tombstone_count =
                    u64::try_from(journal.target_raw_hashes.len()).unwrap_or(u64::MAX);
            }
            TombstoneMode::Erase => {
                let receipt = EraseReceipt::new(raw_hash, commit, purged_at)?;
                state.publish_erase_receipt(journal, &receipt)?;
                report.erase_receipt_count =
                    u64::try_from(journal.target_raw_hashes.len()).unwrap_or(u64::MAX);
            }
        }
    }
    Ok(())
}

fn delete_content_surfaces(
    repo: &Repository,
    plan: &PurgePlan,
    report: &mut PurgeReport,
) -> Result<()> {
    let targets = plan
        .target_raw_hashes
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let stored = crate::read_stored_chunks(repo.kcs_dir())?;
    let chunk_ids = stored
        .iter()
        .filter(|stored| targets.contains(stored.row.raw_hash.as_str()))
        .map(|stored| stored.row.chunk_id.clone())
        .collect::<BTreeSet<_>>();
    store_phase_chunk_ids(
        repo.kcs_dir(),
        &chunk_ids.iter().cloned().collect::<Vec<_>>(),
    )?;

    let store = ObjectStore::new(repo.kcs_dir());
    for raw_hash in &plan.target_raw_hashes {
        if store.remove_raw(raw_hash)? {
            report.deleted.raw_objects = report.deleted.raw_objects.saturating_add(1);
        }
    }
    for chunk_id in &chunk_ids {
        if store.remove_chunk(chunk_id)? {
            report.deleted.chunk_objects = report.deleted.chunk_objects.saturating_add(1);
        }
    }

    let kept = stored
        .into_iter()
        .filter(|stored| !targets.contains(stored.row.raw_hash.as_str()))
        .collect::<Vec<_>>();
    report.deleted.chunk_ledger_rows = rewrite_chunk_ledger(repo.kcs_dir(), &kept)?;
    Ok(())
}

fn rewrite_chunk_ledger(kcs_dir: &Path, kept: &[crate::StoredChunk]) -> Result<u64> {
    let original_count = crate::read_stored_chunks(kcs_dir)?.len();
    let mut bytes = Vec::new();
    for stored in kept {
        serde_json::to_writer(&mut bytes, stored)
            .map_err(|error| KcsError::schema(error.to_string()))?;
        bytes.push(b'\n');
    }
    atomic_private_replace(&crate::chunks_jsonl_path(kcs_dir), &bytes)?;
    Ok(u64::try_from(original_count.saturating_sub(kept.len())).unwrap_or(u64::MAX))
}

fn phase_chunk_ids_path(kcs_dir: &Path) -> PathBuf {
    kcs_dir.join("purge/chunk-ids.json")
}

fn store_phase_chunk_ids(kcs_dir: &Path, chunk_ids: &[String]) -> Result<()> {
    let bytes =
        serde_json::to_vec(chunk_ids).map_err(|error| KcsError::schema(error.to_string()))?;
    atomic_private_replace(&phase_chunk_ids_path(kcs_dir), &bytes)
}

fn load_phase_chunk_ids(kcs_dir: &Path) -> Result<BTreeSet<String>> {
    let path = phase_chunk_ids_path(kcs_dir);
    let Some(bytes) = read_bounded_regular(&path, 8 * 1024 * 1024)? else {
        return Ok(BTreeSet::new());
    };
    let ids = serde_json::from_slice::<Vec<String>>(&bytes).map_err(|error| {
        KcsError::new(
            "KCS-E-STORE-CORRUPT-001",
            "purge chunk-id sidecar is corrupt",
            json!({ "path": path.display().to_string(), "message": error.to_string() }),
            ExitCode::PermanentFailure,
        )
    })?;
    if ids.iter().any(|id| !is_hash(id)) {
        return Err(KcsError::schema(
            "purge chunk-id sidecar contains an invalid hash",
        ));
    }
    Ok(ids.into_iter().collect())
}

fn phase_report_path(kcs_dir: &Path) -> PathBuf {
    kcs_dir.join("purge/report.json")
}

fn store_phase_report(kcs_dir: &Path, report: &PurgeReport) -> Result<()> {
    let bytes = serde_json::to_vec(report).map_err(|error| KcsError::schema(error.to_string()))?;
    atomic_private_replace(&phase_report_path(kcs_dir), &bytes)
}

fn load_phase_report(kcs_dir: &Path) -> Result<Option<PurgeReport>> {
    let path = phase_report_path(kcs_dir);
    let Some(bytes) = read_bounded_regular(&path, 1024 * 1024)? else {
        return Ok(None);
    };
    serde_json::from_slice(&bytes).map(Some).map_err(|error| {
        KcsError::new(
            "KCS-E-STORE-CORRUPT-001",
            "purge report sidecar is corrupt",
            json!({ "path": path.display().to_string(), "message": error.to_string() }),
            ExitCode::PermanentFailure,
        )
    })
}

#[derive(Debug, Default)]
struct DerivedInventory {
    target_instance_dirs: BTreeSet<PathBuf>,
    target_prepared: BTreeSet<String>,
    target_images: BTreeSet<String>,
    surviving_prepared: BTreeSet<String>,
    surviving_images: BTreeSet<String>,
}

fn delete_derived_surfaces(
    repo: &Repository,
    plan: &PurgePlan,
    report: &mut PurgeReport,
) -> Result<()> {
    let targets = plan
        .target_raw_hashes
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let store = ObjectStore::new(repo.kcs_dir());

    // SQLite owns FTS, config associations, vectors, and text-hash embeddings.
    // Its typed purge transaction preserves embeddings still referenced by a
    // surviving chunk. Collect index-only chunk IDs before their rows disappear.
    let sqlite = crate::sqlite_path(repo.kcs_dir());
    let mut chunk_ids = load_phase_chunk_ids(repo.kcs_dir())?;
    if path_exists(&sqlite)? {
        validate_existing_regular(&sqlite, None)?;
        let mut index = SqliteFtsIndex::open(
            &sqlite,
            FtsSchemaConfig {
                tokenizer: FtsTokenizer::Trigram,
            },
        )
        .map_err(crate::index_to_kcs)?;
        for raw_hash in &plan.target_raw_hashes {
            let deleted = index.purge_raw(raw_hash).map_err(crate::index_to_kcs)?;
            chunk_ids.extend(deleted.chunk_ids);
            report.deleted.sqlite_chunks = report
                .deleted
                .sqlite_chunks
                .saturating_add(deleted.deleted_chunks);
            report.deleted.sqlite_associations = report
                .deleted
                .sqlite_associations
                .saturating_add(deleted.deleted_associations);
            report.deleted.sqlite_vectors = report
                .deleted
                .sqlite_vectors
                .saturating_add(deleted.deleted_chunk_vectors);
            report.deleted.sqlite_orphan_embeddings = report
                .deleted
                .sqlite_orphan_embeddings
                .saturating_add(deleted.deleted_orphan_embeddings);
        }
        drop(index);
        store_phase_chunk_ids(
            repo.kcs_dir(),
            &chunk_ids.iter().cloned().collect::<Vec<_>>(),
        )?;
    }
    for chunk_id in &chunk_ids {
        if store.remove_chunk(chunk_id)? {
            report.deleted.chunk_objects = report.deleted.chunk_objects.saturating_add(1);
        }
    }

    let inventory = scan_derived_inventory(repo.kcs_dir(), &targets)?;
    let shared_prepared = inventory
        .target_prepared
        .intersection(&inventory.surviving_prepared)
        .cloned()
        .collect::<BTreeSet<_>>();
    let shared_images = inventory
        .target_images
        .intersection(&inventory.surviving_images)
        .cloned()
        .collect::<BTreeSet<_>>();
    report.shared.prepared_objects = u64::try_from(shared_prepared.len()).unwrap_or(u64::MAX);
    report.shared.image_objects = u64::try_from(shared_images.len()).unwrap_or(u64::MAX);

    let removable_prepared = inventory
        .target_prepared
        .difference(&shared_prepared)
        .cloned()
        .collect::<BTreeSet<_>>();
    let removable_images = inventory
        .target_images
        .difference(&shared_images)
        .cloned()
        .collect::<BTreeSet<_>>();
    for hash in &removable_prepared {
        if store.remove_content(ContentObjectKind::Prepared, hash)? {
            report.deleted.prepared_objects = report.deleted.prepared_objects.saturating_add(1);
        }
    }
    for hash in &removable_images {
        if store.remove_content(ContentObjectKind::Image, hash)? {
            report.deleted.image_objects = report.deleted.image_objects.saturating_add(1);
        }
    }

    for directory in &inventory.target_instance_dirs {
        if remove_tree_nofollow(directory)? {
            report.deleted.normalized_instances =
                report.deleted.normalized_instances.saturating_add(1);
        }
    }
    report.deleted.normalized_views = remove_target_normalized_views(repo.kcs_dir(), &targets)?;

    delete_target_tasks(repo, &targets, &chunk_ids, report)?;
    report.deleted.manifest_rows = scrub_manifest(repo.kcs_dir(), &targets)?;
    report.deleted.unsupported_rows = scrub_unsupported(repo.kcs_dir(), &targets)?;
    report.deleted.quarantine_rows = scrub_quarantine(repo.kcs_dir(), &plan.historical_paths)?;

    let mut cache_hashes = plan
        .target_raw_hashes
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    cache_hashes.extend(removable_prepared);
    cache_hashes.extend(removable_images);
    report.deleted.cache_directories = evict_open_cache(&cache_hashes)?;
    Ok(())
}

fn scan_derived_inventory(kcs_dir: &Path, targets: &BTreeSet<&str>) -> Result<DerivedInventory> {
    const MAX_INSTANCES: usize = 100_000;
    let root = kcs_dir.join("objects/normalized_units");
    if !path_exists(&root)? {
        return Ok(DerivedInventory::default());
    }
    validate_real_directory(&root)?;
    let mut leaves = Vec::new();
    let mut first_count = 0usize;
    for first in read_real_directory(&root)? {
        first_count = first_count.saturating_add(1);
        if first_count > 256 {
            return Err(store_corrupt(&root, "normalized fanout exceeds its bound"));
        }
        validate_real_directory(&first)?;
        for second in read_real_directory(&first)? {
            validate_real_directory(&second)?;
            for leaf in read_real_directory(&second)? {
                if leaves.len() >= MAX_INSTANCES {
                    return Err(store_corrupt(
                        &root,
                        "normalized instance count exceeds its bound",
                    ));
                }
                validate_real_directory(&leaf)?;
                leaves.push(leaf);
            }
        }
    }

    let mut inventory = DerivedInventory::default();
    let mut identities = BTreeSet::new();
    for leaf in leaves {
        let manifest_path = leaf.join("manifest.json");
        let bytes = read_bounded_regular(&manifest_path, 8 * 1024 * 1024)?.ok_or_else(|| {
            store_corrupt(&manifest_path, "normalized instance manifest is missing")
        })?;
        let manifest: NormalizedInstanceManifest = serde_json::from_slice(&bytes)
            .map_err(|error| store_corrupt(&manifest_path, &error.to_string()))?;
        validate_instance_leaf(&leaf, &manifest)?;
        let identity = (
            manifest.raw_hash.clone(),
            manifest.tool_profile_hash.clone(),
            manifest.gen,
        );
        let target = targets.contains(manifest.raw_hash.as_str());
        if target {
            inventory.target_instance_dirs.insert(leaf.clone());
        }
        if !identities.insert(identity.clone()) {
            // A canonical/legacy duplicate is validated together by the loader;
            // only its physical directory still needs removal.
            continue;
        }
        let instance =
            load_validated_normalized_instance(kcs_dir, &identity.0, &identity.1, identity.2)
                .map_err(crate::pipeline_to_kcs)?;
        let (prepared, images) = normalized_references(&instance.manifest, &instance.units);
        if target {
            inventory.target_prepared.extend(prepared);
            inventory.target_images.extend(images);
        } else {
            inventory.surviving_prepared.extend(prepared);
            inventory.surviving_images.extend(images);
        }
    }
    Ok(inventory)
}

fn validate_instance_leaf(path: &Path, manifest: &NormalizedInstanceManifest) -> Result<()> {
    if !is_hash(&manifest.raw_hash) || !is_hash(&manifest.tool_profile_hash) {
        return Err(store_corrupt(
            path,
            "normalized manifest contains an invalid hash",
        ));
    }
    let raw = manifest.raw_hash.trim_start_matches("sha256:");
    let tool = manifest.tool_profile_hash.trim_start_matches("sha256:");
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| store_corrupt(path, "normalized instance leaf is not valid UTF-8"))?;
    let canonical = format!("{raw}.{tool}.g{}", manifest.gen);
    #[cfg(not(windows))]
    let legacy = format!(
        "{}.{}.g{}",
        manifest.raw_hash, manifest.tool_profile_hash, manifest.gen
    );
    #[cfg(windows)]
    let valid_name = name == canonical;
    #[cfg(not(windows))]
    let valid_name = name == canonical || name == legacy;
    let fanout = path
        .parent()
        .and_then(Path::file_name)
        .and_then(|name| name.to_str());
    let first = path
        .parent()
        .and_then(Path::parent)
        .and_then(Path::file_name)
        .and_then(|name| name.to_str());
    if !valid_name || first != Some(&raw[0..2]) || fanout != Some(&raw[2..4]) {
        return Err(store_corrupt(
            path,
            "normalized instance path disagrees with its manifest identity",
        ));
    }
    Ok(())
}

fn normalized_references(
    manifest: &NormalizedInstanceManifest,
    units: &[NormalizedUnitObject],
) -> (BTreeSet<String>, BTreeSet<String>) {
    let prepared = manifest
        .units
        .iter()
        .map(|entry| entry.prepared_hash.clone())
        .collect::<BTreeSet<_>>();
    let mut images = BTreeSet::new();
    for unit in units {
        collect_image_hashes_from_value(
            &Value::Object(unit.metadata.clone().into_iter().collect()),
            &mut images,
        );
        collect_markdown_image_uris(&unit.markdown, &mut images);
    }
    (prepared, images)
}

fn collect_image_hashes_from_value(value: &Value, output: &mut BTreeSet<String>) {
    match value {
        Value::Object(object) => {
            for (key, child) in object {
                if key == "image_hash" {
                    if let Some(hash) = child.as_str().filter(|hash| is_hash(hash)) {
                        output.insert(hash.to_owned());
                    }
                }
                if key == "images" {
                    if let Some(items) = child.as_array() {
                        for item in items {
                            if let Some(hash) = item
                                .get("hash")
                                .and_then(Value::as_str)
                                .filter(|hash| is_hash(hash))
                            {
                                output.insert(hash.to_owned());
                            }
                        }
                    }
                }
                collect_image_hashes_from_value(child, output);
            }
        }
        Value::Array(array) => {
            for child in array {
                collect_image_hashes_from_value(child, output);
            }
        }
        _ => {}
    }
}

fn collect_markdown_image_uris(markdown: &str, output: &mut BTreeSet<String>) {
    const MARKER: &str = "/object/image/sha256:";
    let mut remainder = markdown;
    while let Some(index) = remainder.find(MARKER) {
        let hash_start = index + MARKER.len() - "sha256:".len();
        let Some(candidate) = remainder.get(hash_start..hash_start.saturating_add(71)) else {
            break;
        };
        if is_hash(candidate) {
            output.insert(candidate.to_owned());
        }
        remainder = &remainder[index + MARKER.len()..];
    }
}

fn remove_target_normalized_views(kcs_dir: &Path, targets: &BTreeSet<&str>) -> Result<u64> {
    let root = kcs_dir.join("objects/normalized");
    if !path_exists(&root)? {
        return Ok(0);
    }
    validate_real_directory(&root)?;
    let mut candidates = Vec::new();
    for raw_hash in targets {
        let digest = raw_hash.trim_start_matches("sha256:");
        let fanout = root.join(&digest[0..2]).join(&digest[2..4]);
        if !path_exists(&fanout)? {
            continue;
        }
        validate_real_directory(&fanout)?;
        for path in read_real_directory(&fanout)? {
            let name = path
                .file_name()
                .and_then(|value| value.to_str())
                .ok_or_else(|| store_corrupt(&path, "normalized view leaf is not valid UTF-8"))?;
            let canonical = name.starts_with(&format!("{digest}."));
            #[cfg(not(windows))]
            let legacy = name.starts_with(&format!("{raw_hash}."));
            #[cfg(windows)]
            let legacy = false;
            if (canonical || legacy) && name.ends_with(".md") {
                validate_existing_regular(&path, Some(256 * 1024 * 1024))?;
                candidates.push(path);
            }
        }
    }
    let mut deleted = 0_u64;
    for path in candidates {
        fs::remove_file(&path)
            .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
        deleted = deleted.saturating_add(1);
    }
    Ok(deleted)
}

fn delete_target_tasks(
    repo: &Repository,
    targets: &BTreeSet<&str>,
    chunk_ids: &BTreeSet<String>,
    report: &mut PurgeReport,
) -> Result<()> {
    let path = repo.kcs_dir().join("tasks.jsonl");
    if path_exists(&path)? {
        validate_existing_regular(&path, Some(MAX_TASK_STORE_BYTES))?;
    }
    let store = TaskStore::new(repo.kcs_dir());
    let tasks = store.all().map_err(crate::pipeline_to_kcs)?;
    let mut removed = Vec::new();
    let mut kept = Vec::new();
    for task in tasks {
        let embedding_target = task.task_type == TaskType::Embedding
            && task
                .output_ref
                .strip_prefix("embedding:")
                .is_some_and(|chunk_id| chunk_ids.contains(chunk_id));
        if targets.contains(task.input_hash.as_str())
            || task
                .previous_raw_hash
                .as_deref()
                .is_some_and(|hash| targets.contains(hash))
            || embedding_target
        {
            removed.push(task);
        } else {
            kept.push(task);
        }
    }

    let scope_id = read_scope_id(repo.kcs_dir())?;
    let reservation_ledger = CostLedger::new(crate::cost_ledger_path()).reservation_ledger();
    for task in &removed {
        if let Some(claim) = task.reservation_claim() {
            if reservation_ledger
                .close_for_purge(claim, &scope_id)
                .map_err(crate::pipeline_to_kcs)?
            {
                report.deleted.reservations = report.deleted.reservations.saturating_add(1);
            }
        }
    }
    if !removed.is_empty() {
        store.replace_all(&kept).map_err(crate::pipeline_to_kcs)?;
        report.deleted.tasks = report
            .deleted
            .tasks
            .saturating_add(u64::try_from(removed.len()).unwrap_or(u64::MAX));
    }
    Ok(())
}

fn read_scope_id(kcs_dir: &Path) -> Result<String> {
    let path = kcs_dir.join("scope.json");
    let bytes = read_bounded_regular(&path, 64 * 1024)?
        .ok_or_else(|| store_corrupt(&path, "scope identity is missing"))?;
    let value: Value =
        serde_json::from_slice(&bytes).map_err(|error| store_corrupt(&path, &error.to_string()))?;
    value
        .get("scope_id")
        .and_then(Value::as_str)
        .filter(|scope_id| !scope_id.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| store_corrupt(&path, "scope identity is invalid"))
}

fn scrub_manifest(kcs_dir: &Path, targets: &BTreeSet<&str>) -> Result<u64> {
    let path = kcs_dir.join("manifest.json");
    let Some(bytes) = read_bounded_regular(&path, 64 * 1024 * 1024)? else {
        return Ok(0);
    };
    let mut value: Value =
        serde_json::from_slice(&bytes).map_err(|error| store_corrupt(&path, &error.to_string()))?;
    let files = value
        .get_mut("files")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| store_corrupt(&path, "manifest files array is missing"))?;
    let before = files.len();
    files.retain(|row| {
        !row.get("raw_hash")
            .and_then(Value::as_str)
            .is_some_and(|hash| targets.contains(hash))
    });
    let removed = before.saturating_sub(files.len());
    if removed > 0 {
        let output = serde_json::to_vec_pretty(&value)
            .map_err(|error| KcsError::schema(error.to_string()))?;
        atomic_private_replace(&path, &output)?;
    }
    Ok(u64::try_from(removed).unwrap_or(u64::MAX))
}

fn scrub_unsupported(kcs_dir: &Path, targets: &BTreeSet<&str>) -> Result<u64> {
    let path = kcs_dir.join("unsupported-inputs.jsonl");
    rewrite_jsonl_filter(&path, 16 * 1024 * 1024, |row| {
        row.get("raw_hash")
            .and_then(Value::as_str)
            .is_none_or(|hash| !targets.contains(hash))
    })
}

fn scrub_quarantine(kcs_dir: &Path, historical_paths: &[String]) -> Result<u64> {
    let path = kcs_dir.join("quarantine.jsonl");
    let paths = historical_paths
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    rewrite_jsonl_filter(&path, 16 * 1024 * 1024, |row| {
        row.get("path")
            .and_then(Value::as_str)
            .is_none_or(|path| !paths.contains(path))
    })
}

fn rewrite_jsonl_filter(
    path: &Path,
    max_bytes: u64,
    mut retain: impl FnMut(&Value) -> bool,
) -> Result<u64> {
    let Some(bytes) = read_bounded_regular(path, max_bytes)? else {
        return Ok(0);
    };
    let mut kept = Vec::new();
    let mut removed = 0_u64;
    for (index, line) in bytes.split(|byte| *byte == b'\n').enumerate() {
        if line.iter().all(u8::is_ascii_whitespace) {
            continue;
        }
        let value: Value = serde_json::from_slice(line).map_err(|error| {
            store_corrupt(path, &format!("invalid JSONL row {}: {error}", index + 1))
        })?;
        if retain(&value) {
            serde_json::to_writer(&mut kept, &value)
                .map_err(|error| KcsError::schema(error.to_string()))?;
            kept.push(b'\n');
        } else {
            removed = removed.saturating_add(1);
        }
    }
    if removed > 0 {
        atomic_private_replace(path, &kept)?;
    }
    Ok(removed)
}

fn evict_open_cache(hashes: &BTreeSet<String>) -> Result<u64> {
    let root = crate::cache_home().join("kcs/open");
    if !path_exists(&root)? {
        return Ok(0);
    }
    validate_real_directory(&root)?;
    let mut removed = 0_u64;
    for hash in hashes {
        let path = root.join(hash.trim_start_matches("sha256:"));
        if remove_tree_nofollow(&path)? {
            removed = removed.saturating_add(1);
        }
    }
    Ok(removed)
}

fn scrub_logs(
    repo: &Repository,
    plan: &PurgePlan,
    journal: &PurgeJournal,
    report: &mut PurgeReport,
) -> Result<()> {
    let device_root = crate::data_home().join("kcs/logs");
    let scope_root = repo.kcs_dir().join("logs");
    let _device_lock = StoreLock::acquire_path(device_root.join("scrub.lock"))?;
    let _scope_lock = StoreLock::acquire_path(scope_root.join("access.scrub.lock"))?;

    let identifiers = plan
        .target_raw_hashes
        .iter()
        .chain(plan.historical_paths.iter())
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let mut files = collect_log_files(&device_root, &["events", "errors", "metrics"])?;
    files.extend(collect_log_files(&scope_root, &["access"])?);
    files.sort();
    files.dedup();
    let mut pass_files = 0_u64;
    let mut pass_rows = 0_u64;
    let mut pass_fields = 0_u64;
    for path in files {
        let (rows, fields) = scrub_one_log(&path, &identifiers)?;
        pass_files = pass_files.saturating_add(1);
        pass_rows = pass_rows.saturating_add(rows);
        pass_fields = pass_fields.saturating_add(fields);
    }
    report.log_files_scrubbed = report.log_files_scrubbed.max(pass_files);
    report.log_rows_removed = report.log_rows_removed.saturating_add(pass_rows);
    report.log_fields_masked = report.log_fields_masked.saturating_add(pass_fields);

    if journal.phase == PurgePhase::DerivedDeleted {
        append_event_log(
            "KCS-PURGE-COMPLETED",
            "purge removed content from KCS-managed history",
            json!({
                "actor": std::env::var("USER").unwrap_or_else(|_| "local-user".to_owned()),
                "reason": plan.reason,
                "purged_in_commit": journal.purged_in_commit,
                "target_raw_count": plan.target_raw_hashes.len(),
                "deleted_counts": report.deleted,
            }),
        )?;
    }
    Ok(())
}

fn finalize_purge(
    repo: &Repository,
    state: &PurgeState,
    plan: &PurgePlan,
    journal: &PurgeJournal,
    report: &mut PurgeReport,
) -> Result<()> {
    // Hold both append/scrub locks across the final pass and journal removal.
    // `scrub_logs` re-acquires these paths reentrantly, so its inner guards drop
    // without releasing the outer exclusion window.
    let device_root = crate::data_home().join("kcs/logs");
    let scope_root = repo.kcs_dir().join("logs");
    let _device_lock = StoreLock::acquire_path(device_root.join("scrub.lock"))?;
    let _scope_lock = StoreLock::acquire_path(scope_root.join("access.scrub.lock"))?;
    scrub_logs(repo, plan, journal, report)?;
    remove_purge_sidecars(repo.kcs_dir())?;
    state.finish(journal)
}

fn collect_log_files(root: &Path, prefixes: &[&str]) -> Result<Vec<PathBuf>> {
    if !path_exists(root)? {
        return Ok(Vec::new());
    }
    validate_real_directory(root)?;
    let mut output = Vec::new();
    for path in read_real_directory(root)? {
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(|| store_corrupt(&path, "log file name is not valid UTF-8"))?;
        if name.ends_with(".lock") || !prefixes.iter().any(|prefix| name.starts_with(prefix)) {
            continue;
        }
        validate_existing_regular(&path, Some(64 * 1024 * 1024))?;
        output.push(path);
    }
    Ok(output)
}

fn scrub_one_log(path: &Path, identifiers: &BTreeSet<&str>) -> Result<(u64, u64)> {
    let Some(bytes) = read_bounded_regular(path, 64 * 1024 * 1024)? else {
        return Ok((0, 0));
    };
    let mut output = Vec::new();
    let mut removed = 0_u64;
    let mut masked = 0_u64;
    for (index, line) in bytes.split(|byte| *byte == b'\n').enumerate() {
        if line.iter().all(u8::is_ascii_whitespace) {
            continue;
        }
        let mut row: Value = serde_json::from_slice(line).map_err(|error| {
            store_corrupt(path, &format!("invalid log row {}: {error}", index + 1))
        })?;
        if value_contains_identifier(&row, identifiers) {
            removed = removed.saturating_add(1);
            continue;
        }
        mask_sensitive_log_fields(&mut row, &mut masked);
        serde_json::to_writer(&mut output, &row)
            .map_err(|error| KcsError::schema(error.to_string()))?;
        output.push(b'\n');
    }
    if removed > 0 || masked > 0 {
        atomic_private_replace(path, &output)?;
    }
    Ok((removed, masked))
}

fn value_contains_identifier(value: &Value, identifiers: &BTreeSet<&str>) -> bool {
    match value {
        Value::String(text) => identifiers
            .iter()
            .any(|identifier| !identifier.is_empty() && text.contains(identifier)),
        Value::Array(array) => array
            .iter()
            .any(|child| value_contains_identifier(child, identifiers)),
        Value::Object(object) => object
            .values()
            .any(|child| value_contains_identifier(child, identifiers)),
        _ => false,
    }
}

fn mask_sensitive_log_fields(value: &mut Value, count: &mut u64) {
    match value {
        Value::Array(array) => {
            for child in array {
                mask_sensitive_log_fields(child, count);
            }
        }
        Value::Object(object) => {
            for (key, child) in object {
                if matches!(key.as_str(), "query" | "prompt") && !child.is_null() {
                    *child = json!("[redacted-by-purge]");
                    *count = count.saturating_add(1);
                } else {
                    mask_sensitive_log_fields(child, count);
                }
            }
        }
        _ => {}
    }
}

fn remove_purge_sidecars(kcs_dir: &Path) -> Result<()> {
    for path in [phase_chunk_ids_path(kcs_dir), phase_report_path(kcs_dir)] {
        if path_exists(&path)? {
            validate_existing_regular(&path, Some(8 * 1024 * 1024))?;
            fs::remove_file(&path)
                .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
        }
    }
    Ok(())
}

fn path_exists(path: &Path) -> Result<bool> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(KcsError::io(error.to_string(), path.display().to_string())),
    }
}

fn validate_real_directory(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(store_corrupt(path, "expected a real directory"));
    }
    // On Windows, `is_symlink` does not cover every directory reparse-point
    // kind (notably junctions).  Purge recursively deletes normalized/cache
    // trees, so descending through one could unlink files outside KCS.  Verify
    // the opened directory handle before every traversal step.
    #[cfg(windows)]
    if !kcs_core::cas::windows_directory_is_real(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?
    {
        return Err(store_corrupt(path, "expected a real non-reparse directory"));
    }
    Ok(())
}

fn read_real_directory(path: &Path) -> Result<Vec<PathBuf>> {
    validate_real_directory(path)?;
    let mut output = Vec::new();
    let entries = fs::read_dir(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    for entry in entries {
        let entry =
            entry.map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
        if output.len() >= 100_000 {
            return Err(store_corrupt(
                path,
                "directory entry count exceeds its bound",
            ));
        }
        output.push(entry.path());
    }
    output.sort();
    Ok(output)
}

fn validate_existing_regular(path: &Path, max_bytes: Option<u64>) -> Result<fs::Metadata> {
    let listed = fs::symlink_metadata(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    if listed.file_type().is_symlink() || !listed.file_type().is_file() {
        return Err(store_corrupt(path, "expected a real regular file"));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if listed.nlink() != 1 {
            return Err(store_corrupt(
                path,
                "regular file has an unexpected hard-link count",
            ));
        }
    }
    if max_bytes.is_some_and(|limit| listed.len() > limit) {
        return Err(store_corrupt(path, "regular file exceeds its byte bound"));
    }
    Ok(listed)
}

fn read_bounded_regular(path: &Path, max_bytes: u64) -> Result<Option<Vec<u8>>> {
    if !path_exists(path)? {
        return Ok(None);
    }
    let listed = validate_existing_regular(path, Some(max_bytes))?;
    let mut file = fs::File::open(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    let opened = file
        .metadata()
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    if !same_file_identity(&listed, &opened) {
        return Err(store_corrupt(
            path,
            "regular file changed while it was opened",
        ));
    }
    let capacity = usize::try_from(opened.len().min(max_bytes)).unwrap_or(0);
    let mut bytes = Vec::with_capacity(capacity);
    Read::by_ref(&mut file)
        .take(max_bytes.saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    if bytes.len() as u64 > max_bytes {
        return Err(store_corrupt(path, "regular file exceeds its byte bound"));
    }
    Ok(Some(bytes))
}

fn same_file_identity(left: &fs::Metadata, right: &fs::Metadata) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        left.dev() == right.dev() && left.ino() == right.ino()
    }
    #[cfg(not(unix))]
    {
        left.len() == right.len()
            && left.modified().ok() == right.modified().ok()
            && left.file_type() == right.file_type()
    }
}

fn remove_tree_nofollow(path: &Path) -> Result<bool> {
    if !path_exists(path)? {
        return Ok(false);
    }
    validate_real_directory(path)?;
    let mut removals = Vec::<(PathBuf, fs::Metadata, bool)>::new();
    collect_tree_removals(path, &mut removals, 0)?;
    for (entry, expected, is_directory) in removals {
        let current = fs::symlink_metadata(&entry)
            .map_err(|error| KcsError::io(error.to_string(), entry.display().to_string()))?;
        if !same_file_identity(&expected, &current) {
            return Err(store_corrupt(&entry, "artifact changed before deletion"));
        }
        if is_directory {
            fs::remove_dir(&entry)
                .map_err(|error| KcsError::io(error.to_string(), entry.display().to_string()))?;
        } else {
            fs::remove_file(&entry)
                .map_err(|error| KcsError::io(error.to_string(), entry.display().to_string()))?;
        }
    }
    Ok(true)
}

fn collect_tree_removals(
    path: &Path,
    output: &mut Vec<(PathBuf, fs::Metadata, bool)>,
    depth: usize,
) -> Result<()> {
    if depth > 16 || output.len() >= 100_000 {
        return Err(store_corrupt(
            path,
            "artifact tree exceeds its deletion bound",
        ));
    }
    let metadata = fs::symlink_metadata(path)
        .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
    if metadata.file_type().is_symlink() {
        return Err(store_corrupt(
            path,
            "artifact tree contains a symbolic link",
        ));
    }
    if metadata.is_dir() {
        for child in read_real_directory(path)? {
            collect_tree_removals(&child, output, depth + 1)?;
        }
        output.push((path.to_path_buf(), metadata, true));
    } else if metadata.is_file() {
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            if metadata.nlink() != 1 {
                return Err(store_corrupt(
                    path,
                    "artifact has an unexpected hard-link count",
                ));
            }
        }
        output.push((path.to_path_buf(), metadata, false));
    } else {
        return Err(store_corrupt(
            path,
            "artifact tree contains a non-regular entry",
        ));
    }
    Ok(())
}

fn store_corrupt(path: &Path, message: &str) -> KcsError {
    KcsError::new(
        "KCS-E-STORE-CORRUPT-001",
        "purge encountered corrupt store state",
        json!({ "path": path.display().to_string(), "message": message }),
        ExitCode::PermanentFailure,
    )
}

fn refuse_live_working_copy_for_phase(
    repo: &Repository,
    targets: &[String],
    journal: Option<&PurgeJournal>,
) -> Result<()> {
    match refuse_live_working_copy(repo, targets) {
        Ok(()) => Ok(()),
        Err(_error) if journal.is_some_and(|active| active.phase.is_barrier_visible()) => {
            Err(KcsError::new(
                "KCS-E-PURGE-INCOMPLETE-001",
                "target bytes reappeared while a purge barrier is active",
                json!({ "target_raw_count": targets.len() }),
                ExitCode::PartialFailure,
            ))
        }
        Err(error) => Err(error),
    }
}

fn completed_report(plan: &PurgePlan, completed: CompletedTerminal) -> Value {
    let report = PurgeReport {
        purged_in_commit: Some(completed.purged_in_commit),
        tombstone_count: completed.tombstone_count,
        erase_receipt_count: completed.erase_receipt_count,
        ..PurgeReport::default()
    };
    success_report(plan, &report)
}

fn success_report(plan: &PurgePlan, report: &PurgeReport) -> Value {
    json!({
        "status": "purged",
        "purged_in_commit": report.purged_in_commit,
        "reason": plan.reason,
        "target_raw_count": plan.target_raw_hashes.len(),
        "deleted_counts": report.deleted,
        "shared_artifacts_preserved": report.shared,
        "tombstone_mode": plan.tombstone_mode,
        "tombstone_count": report.tombstone_count,
        "erase_receipt_count": report.erase_receipt_count,
        "logs_scrubbed": true,
        "log_files_scrubbed": report.log_files_scrubbed,
        "log_rows_removed": report.log_rows_removed,
        "log_fields_masked": report.log_fields_masked,
        "guarantee": "removed from KCS-managed history",
        "not_covered": [
            "external backups and Time Machine",
            "exported or manually copied files",
            "cloud-sync past versions",
            "logs outside KCS management"
        ],
    })
}

fn incomplete_report(
    plan: &PurgePlan,
    journal: &PurgeJournal,
    report: &PurgeReport,
    error: &KcsError,
) -> Value {
    let mut value = success_report(plan, report);
    value["status"] = json!("purge_incomplete");
    value["logs_scrubbed"] = json!(journal.phase >= PurgePhase::LogsScrubbed);
    value["error_code"] = json!("KCS-E-PURGE-INCOMPLETE-001");
    value["message"] = json!("purge is incomplete and will resume on the next identical command");
    value["failure_phase"] = json!(journal.phase);
    value["cause_error_code"] = json!(error.error_code());
    crate::set_exit_override(&mut value, ExitCode::PartialFailure);
    value
}

fn maybe_inject_fault(phase: &str) -> Result<()> {
    #[cfg(debug_assertions)]
    if std::env::var("KCS_TEST_PURGE_FAIL_AFTER_PHASE").as_deref() == Ok(phase) {
        return Err(KcsError::io(
            format!("injected purge failure after {phase}"),
            "purge fault seam",
        ));
    }
    let _ = phase;
    Ok(())
}

fn atomic_private_replace(path: &Path, bytes: &[u8]) -> Result<()> {
    static SEQUENCE: AtomicU64 = AtomicU64::new(0);
    let parent = path.parent().ok_or_else(|| {
        KcsError::io("purge state path has no parent", path.display().to_string())
    })?;
    fs::create_dir_all(parent)
        .map_err(|error| KcsError::io(error.to_string(), parent.display().to_string()))?;
    let metadata = fs::symlink_metadata(parent)
        .map_err(|error| KcsError::io(error.to_string(), parent.display().to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(KcsError::io(
            "purge state parent is not a real directory",
            parent.display().to_string(),
        ));
    }
    let original_leaf = if path_exists(path)? {
        Some(validate_existing_regular(path, None)?)
    } else {
        None
    };
    let sequence = SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let temp = parent.join(format!(
        ".purge-write-{}-{nanos}-{sequence}.tmp",
        std::process::id()
    ));
    let result = (|| -> Result<()> {
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options
            .open(&temp)
            .map_err(|error| KcsError::io(error.to_string(), temp.display().to_string()))?;
        file.write_all(bytes)
            .map_err(|error| KcsError::io(error.to_string(), temp.display().to_string()))?;
        file.sync_all()
            .map_err(|error| KcsError::io(error.to_string(), temp.display().to_string()))?;
        drop(file);
        let current_parent = fs::symlink_metadata(parent)
            .map_err(|error| KcsError::io(error.to_string(), parent.display().to_string()))?;
        if !same_file_identity(&metadata, &current_parent) {
            return Err(store_corrupt(
                parent,
                "purge state parent changed during rewrite",
            ));
        }
        match &original_leaf {
            Some(expected) => {
                let current = validate_existing_regular(path, None)?;
                if !same_file_identity(expected, &current) {
                    return Err(store_corrupt(
                        path,
                        "purge state file changed during rewrite",
                    ));
                }
            }
            None if path_exists(path)? => {
                return Err(store_corrupt(
                    path,
                    "purge state leaf appeared during rewrite",
                ));
            }
            None => {}
        }
        fs::rename(&temp, path)
            .map_err(|error| KcsError::io(error.to_string(), path.display().to_string()))?;
        if let Ok(directory) = fs::File::open(parent) {
            let _ = directory.sync_all();
        }
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

fn preflight(repo: &Repository, args: &PurgeArgs) -> Result<PurgePreview> {
    let plan = resolve_plan(repo, args)?;
    let state = PurgeState::new(repo.kcs_dir());
    let journal = state.read_journal()?;
    if let Some(active) = &journal {
        if active.target_raw_hashes != plan.target_raw_hashes
            || active.reason != plan.reason
            || active.tombstone_mode != plan.tombstone_mode
        {
            return Err(KcsError::new(
                "KCS-E-PURGE-INCOMPLETE-001",
                "a different purge transaction is already in progress",
                json!({
                    "phase": active.phase,
                    "target_raw_count": active.target_raw_hashes.len(),
                }),
                ExitCode::PartialFailure,
            ));
        }
    }

    let completed = if journal.is_none() {
        inspect_terminal_state(&state, &plan)?
    } else {
        inspect_terminal_state(&state, &plan)?;
        None
    };
    verify_targets_exist(repo, &plan, journal.is_some(), completed.is_some())?;
    // A visible transaction must reach the locked phase-machine wrapper so a
    // reappeared working file returns the bounded incomplete report (exit 3)
    // without dropping its journal. Fresh/Prepared operations still fail before
    // any barrier or mutation.
    if !journal
        .as_ref()
        .is_some_and(|active| active.phase.is_barrier_visible())
    {
        refuse_live_working_copy(repo, &plan.target_raw_hashes)?;
    }

    Ok(PurgePreview { plan, completed })
}

fn resolve_plan(repo: &Repository, args: &PurgeArgs) -> Result<PurgePlan> {
    let reason = PurgeReason::from_str(&args.reason)?;
    let tombstone_mode = if args.erase_tombstone {
        TombstoneMode::Erase
    } else {
        TombstoneMode::Default
    };
    let head_commit = repo
        .head_commit_hash()?
        .ok_or_else(|| KcsError::invalid_usage("cannot purge an unborn scope"))?;

    let (target_raw_hashes, historical_paths) = match (&args.path, &args.raw_hash) {
        (Some(path), None) => {
            let logical_path = path
                .to_str()
                .ok_or_else(|| KcsError::invalid_usage("purge path must be valid UTF-8"))?;
            // Reuse the persisted TreeEntry boundary rather than interpreting a
            // deleted historical operand through host filesystem canonicalization.
            TreeEntry::raw_file(logical_path, VALIDATION_HASH)?;
            let graph = HistoryReader::new(repo.kcs_dir()).all_parents(&head_commit)?;
            let bindings = graph.bindings();
            let targets = bindings
                .iter()
                .filter(|binding| binding.binding.path == logical_path)
                .map(|binding| binding.binding.raw_hash.clone())
                .collect::<BTreeSet<_>>();
            if targets.is_empty() {
                return Err(purge_not_found());
            }
            let paths = bindings
                .iter()
                .filter(|binding| targets.contains(&binding.binding.raw_hash))
                .map(|binding| binding.binding.path.clone())
                .collect::<BTreeSet<_>>();
            (targets.into_iter().collect(), paths.into_iter().collect())
        }
        (None, Some(raw_hash)) => {
            if !is_hash(raw_hash) {
                return Err(KcsError::invalid_usage(
                    "--raw-hash must be sha256 followed by 64 lowercase hexadecimal digits",
                ));
            }
            // Raw identity remains authoritative even when history is shallow or
            // beyond traversal bounds. A successful best-effort walk only
            // enriches the conservative log/quarantine alias scrub.
            let paths = HistoryReader::new(repo.kcs_dir())
                .all_parents(&head_commit)
                .ok()
                .into_iter()
                .flat_map(|graph| graph.bindings())
                .filter(|binding| binding.binding.raw_hash == *raw_hash)
                .map(|binding| binding.binding.path)
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect();
            (vec![raw_hash.clone()], paths)
        }
        _ => {
            return Err(KcsError::invalid_usage(
                "purge requires exactly one of a path or --raw-hash",
            ));
        }
    };

    Ok(PurgePlan {
        head_commit,
        target_raw_hashes,
        historical_paths,
        reason,
        tombstone_mode,
    })
}

fn inspect_terminal_state(
    state: &PurgeState,
    plan: &PurgePlan,
) -> Result<Option<CompletedTerminal>> {
    let mut tombstones = Vec::new();
    let mut receipts = Vec::new();
    for raw_hash in &plan.target_raw_hashes {
        if let Some(tombstone) = state.read_tombstone(raw_hash)? {
            if plan.tombstone_mode == TombstoneMode::Erase {
                return Err(KcsError::invalid_usage(
                    "converting an existing tombstone to erase mode is not supported",
                ));
            }
            if tombstone.purged_reason != plan.reason {
                return Err(KcsError::invalid_usage(
                    "an existing tombstone has a different purge reason",
                ));
            }
            tombstones.push(tombstone);
        }
        if let Some(receipt) = state.read_erase_receipt(raw_hash)? {
            receipts.push(receipt);
        }
    }

    let target_count = plan.target_raw_hashes.len();
    let completed = match plan.tombstone_mode {
        TombstoneMode::Default if tombstones.len() == target_count => Some(CompletedTerminal {
            purged_in_commit: tombstones[0].purged_in_commit.clone(),
            tombstone_count: u64::try_from(tombstones.len()).unwrap_or(u64::MAX),
            erase_receipt_count: 0,
        }),
        TombstoneMode::Erase if receipts.len() == target_count => Some(CompletedTerminal {
            purged_in_commit: receipts[0].purged_in_commit.clone(),
            tombstone_count: 0,
            erase_receipt_count: u64::try_from(receipts.len()).unwrap_or(u64::MAX),
        }),
        _ => None,
    };

    if completed.is_none() && (!tombstones.is_empty() || !receipts.is_empty()) {
        return Err(KcsError::new(
            "KCS-E-PURGE-INCOMPLETE-001",
            "only part of the requested purge target has terminal state",
            json!({ "target_raw_count": target_count }),
            ExitCode::PartialFailure,
        ));
    }
    Ok(completed)
}

fn verify_targets_exist(
    repo: &Repository,
    plan: &PurgePlan,
    has_matching_journal: bool,
    is_complete: bool,
) -> Result<()> {
    if has_matching_journal || is_complete {
        return Ok(());
    }
    let store = ObjectStore::new(repo.kcs_dir());
    for raw_hash in &plan.target_raw_hashes {
        match store.inspect_object(ObjectKind::Raw, raw_hash) {
            Ok(_) => {}
            Err(error) if error.error_code() == "KCS-E-STORE-NOT-FOUND-001" => {
                return Err(purge_not_found());
            }
            Err(error) => return Err(error),
        }
    }
    Ok(())
}

fn refuse_live_working_copy(repo: &Repository, targets: &[String]) -> Result<()> {
    let targets = targets.iter().map(String::as_str).collect::<BTreeSet<_>>();
    let working_tree = repo.build_working_tree(false)?;
    let live_alias_count = working_tree
        .tree
        .entries
        .iter()
        .filter(|entry| targets.contains(entry.raw_hash.as_str()))
        .count();
    if live_alias_count == 0 {
        return Ok(());
    }
    Err(KcsError::new(
        "KCS-E-PURGE-WORKING-COPY-001",
        "purge refuses to delete bytes that remain in the working tree",
        json!({ "live_alias_count": live_alias_count }),
        ExitCode::PermanentFailure,
    ))
}

fn purge_not_found() -> KcsError {
    KcsError::new(
        "KCS-E-PURGE-NOT-FOUND-001",
        "purge target was not found in this scope",
        json!({}),
        ExitCode::PermanentFailure,
    )
}

fn confirm(preview: &PurgePreview, yes: bool) -> Result<()> {
    if yes {
        return Ok(());
    }

    let mode = match preview.plan.tombstone_mode {
        TombstoneMode::Default => "default tombstone",
        TombstoneMode::Erase => "fsck-only erase receipt",
    };
    let mut stderr = std::io::stderr().lock();
    writeln!(
        stderr,
        "Purge preview: {} raw object(s); reason={}; terminal={mode}.",
        preview.plan.target_raw_hashes.len(),
        preview.plan.reason
    )
    .map_err(|error| KcsError::io(error.to_string(), "stderr"))?;
    if preview.completed.is_some() {
        writeln!(stderr, "This exact purge is already complete.")
            .map_err(|error| KcsError::io(error.to_string(), "stderr"))?;
    }
    write!(
        stderr,
        "Remove this content from KCS-managed history? [y/N] "
    )
    .map_err(|error| KcsError::io(error.to_string(), "stderr"))?;
    stderr
        .flush()
        .map_err(|error| KcsError::io(error.to_string(), "stderr"))?;

    // Bound confirmation input so a hostile pipe cannot force an unbounded
    // allocation. Inputs longer than 32 bytes simply fail the exact y/yes check.
    let stdin = std::io::stdin();
    let mut reader = BufReader::new(stdin.lock().take(32));
    let mut answer = String::new();
    reader
        .read_line(&mut answer)
        .map_err(|error| KcsError::io(error.to_string(), "stdin"))?;
    if matches!(answer.trim().to_ascii_lowercase().as_str(), "y" | "yes") {
        return Ok(());
    }

    Err(KcsError::new(
        "KCS-E-PURGE-CONFIRMATION-REJECTED-001",
        "purge confirmation was rejected",
        json!({
            "target_raw_count": preview.plan.target_raw_hashes.len(),
        }),
        ExitCode::ConfirmationRejected,
    ))
}

#[cfg(all(test, windows))]
mod windows_tests {
    use std::process::Command;

    use super::validate_real_directory;

    #[test]
    fn ct4_purge_rejects_directory_junction_before_traversal() {
        let root = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let junction = root.path().join("poisoned-junction");
        let status = Command::new("cmd.exe")
            .args(["/D", "/C", "mklink", "/J"])
            .arg(&junction)
            .arg(outside.path())
            .status()
            .expect("cmd.exe must be available on Windows");
        assert!(status.success(), "test junction creation failed");

        let error = validate_real_directory(&junction).unwrap_err();
        assert_eq!(error.error_code(), "KCS-E-STORE-CORRUPT-001");
        std::fs::remove_dir(&junction).unwrap();
    }
}
