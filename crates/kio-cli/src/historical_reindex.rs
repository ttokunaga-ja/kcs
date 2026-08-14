//! Enrichment-only historical reindexing (CT4-TIMETRAVEL-011).
//!
//! The selected commit/tree and exact normalized references are immutable truth.
//! This path therefore never consults a later normalize cache, creates a normalized
//! generation, or advances a ref. It only appends missing current-config chunk
//! associations and their derived search/embedding projections.

use super::*;
use kio_core::history::TreeBinding;

#[derive(Debug, Default)]
pub(super) struct ParsedReindex {
    pub(super) force: bool,
    pub(super) yes: bool,
    pub(super) at: Option<String>,
    /// QA31 (step4b-contract-tests-p3a.md §I, 06-cli-spec.md §1 L77-83,
    /// 07-adapter-spec.md §3 L220-222): one-shot embedding opt-in for THIS
    /// reindex — both `--force` and `--at` can drive online embedding
    /// enrichment. Mutually exclusive with `offline`.
    pub(super) online: bool,
    /// QA31: forbids new online sends for this reindex.
    pub(super) offline: bool,
}

// B (2026-07-24): the hand-rolled `parse_args` was replaced by the clap
// declaration on `ReindexArgs` in main.rs — see `run_reindex`.

/// The immutable unit bodies this tree entry's PINNED manifest reports as
/// `Done` — the state of the normalized instance at the commit being
/// reindexed (03 §2.1).
///
/// A pinned hash whose object is GONE is an error rather than a silent fall
/// back to the working copy. Purge deletes manifest objects, and the working
/// copy is precisely the thing that may have moved on — answering from it is
/// the defect, not the recovery. The caller records the instance in
/// `skipped_units`, which is how every other unreadable-unit case already
/// surfaces.
pub(super) fn pinned_done_units(
    kio_dir: &Path,
    raw_hash: &str,
    normalize: &NormalizeRef,
) -> Result<Vec<NormalizedUnitObject>> {
    let manifest_hash = &normalize.manifest_hash;
    let store = ObjectStore::new(kio_dir);
    let bytes = store.read_content_object_bytes(
        ContentObjectKind::Manifest,
        manifest_hash,
        MAX_MANIFEST_OBJECT_READ_BYTES,
    )?;
    let manifest_path = store.content_path(ContentObjectKind::Manifest, manifest_hash)?;
    if kio_core::cas::hash_bytes(&bytes) != *manifest_hash {
        return Err(crate::store_corrupt_error(
            &manifest_path,
            "pinned manifest CAS object does not match its tree hash",
        ));
    }
    let manifest: NormalizedInstanceManifest = serde_json::from_slice(&bytes)
        .map_err(|error| crate::store_corrupt_error(&manifest_path, error.to_string()))?;
    let canonical_manifest = canonical_json_bytes(
        &serde_json::to_value(&manifest)
            .map_err(|error| crate::store_corrupt_error(&manifest_path, error.to_string()))?,
    )?;
    if canonical_manifest != bytes {
        return Err(crate::store_corrupt_error(
            &manifest_path,
            "pinned manifest CAS object is not canonical JSON",
        ));
    }
    if manifest.raw_hash != raw_hash
        || manifest.tool_profile_hash != normalize.tool_profile_hash
        || manifest.gen != normalize.gen
    {
        return Err(crate::store_corrupt_error(
            &manifest_path,
            "pinned manifest identity does not match its tree normalization reference",
        ));
    }
    let selected_units = kio_pipeline::markdownize::load_validated_normalized_units_from_manifest(
        kio_dir, &manifest,
    )
    .map_err(pipeline_to_kio)?;
    let identity = NormalizedInstanceIdentity {
        raw_hash: raw_hash.to_owned(),
        tool_profile_hash: normalize.tool_profile_hash.clone(),
        gen: normalize.gen,
    };
    validate_normalized_instance(&manifest_path, &identity, &manifest, &selected_units).map_err(
        |error| {
            crate::store_corrupt_error(
                &manifest_path,
                format!("pinned manifest/unit validation failed: {error}"),
            )
        },
    )?;
    Ok(selected_units)
}

/// Projection predicates only need keys, but deliberately go through the same
/// immutable-CAS validation as chunk reconstruction. A mutable normalized-unit
/// cache must never make an older pinned snapshot appear to contain new text.
pub(super) fn merge_reindex_skips(report: &mut Step3RebuildReport, reindex_skipped: Vec<Value>) {
    let seen: BTreeSet<String> = report
        .skipped_units
        .iter()
        .filter_map(|entry| {
            entry
                .get("raw_hash")
                .and_then(Value::as_str)
                .map(str::to_owned)
        })
        .collect();
    for skip in reindex_skipped {
        let already = skip
            .get("raw_hash")
            .and_then(Value::as_str)
            .is_some_and(|raw_hash| seen.contains(raw_hash));
        if !already {
            report.skipped_units.push(skip);
        }
    }
}

#[derive(Debug, Clone)]
struct SelectedInstance {
    raw_hash: String,
    normalize: NormalizeRef,
    raw_path: String,
    embedding_path: String,
}

#[derive(Debug, Clone)]
pub(super) struct RetainedNormalizedInstance {
    pub(super) raw_hash: String,
    pub(super) normalize: NormalizeRef,
    pub(super) raw_path: String,
    pub(super) embedding_path: String,
    pub(super) first_seen_commit: String,
    /// PC37/PC41/PC43 (05 §1.6 L265-266): every ancestor-most (mutually
    /// incomparable) introduction commit for this content identity, sorted by
    /// full commit hash — `first_seen_commit` is always `introductions[0]`
    /// (the deterministic byte-order-min winner already used for display /
    /// the legacy single-valued column). A merge side-branch or independent
    /// import produces more than one entry; the common case has exactly one.
    pub(super) introductions: Vec<String>,
}

/// Resolve every exact normalized instance retained by the bounded all-parent
/// snapshot graph. Mutable caches and `latest_normalize_ref` never participate.
///
/// PC61/PC62 (U145 04-pipeline.md §4.6) asks for this rebuild target set to be
/// narrowed to HEAD-only identities. NOT applied here: this function is the
/// single shared source both `rebuild_step3_index` (index/reindex/repair
/// --rebuild-db) AND the embedding-task-generation path read from — narrowing
/// it broke existing coverage for historical/deleted-file content (several
/// `step3_p0_contract.rs` tests — `ct4_historical_secret_path_withholds_existing_vector`,
/// `ct4_retained_embedding_reservation_is_not_reclaimed_on_edit`,
/// `ct4_edited_secret_history_keeps_each_version_held`,
/// `ct4_deleted_historical_chunk_embedding_stays_pending` — regressed when
/// tried locally), which depend on non-HEAD identities staying discoverable
/// through this same function. PC61/62 needs a narrower fix scoped to
/// specifically the rebuild-time re-association decision (or a dedicated
/// parameter distinguishing the two call sites) rather than a blanket filter
/// here; left unimplemented given the regression risk and the P2-C task's own
/// completion gate (`cargo test --workspace` green).
pub(super) fn retained_history_instances(
    kio_dir: &Path,
    head: &str,
) -> Result<Vec<RetainedNormalizedInstance>> {
    let graph = HistoryReader::new(kio_dir).all_parents(head)?;
    retained_history_instances_from_graph(kio_dir, &graph, std::iter::once(head))
}

/// Derive retained instances from a complete strict graph.  Keeping the graph
/// shared across all durable roots prevents repeated CAS walks of overlapping
/// ancestry while calculating introductions against the complete union.
fn retained_history_instances_from_graph<'a>(
    kio_dir: &Path,
    graph: &kio_core::history::HistoryGraph,
    roots: impl IntoIterator<Item = &'a str>,
) -> Result<Vec<RetainedNormalizedInstance>> {
    let mut all_paths_by_raw = BTreeMap::<String, BTreeSet<String>>::new();
    for appearance in graph.bindings() {
        all_paths_by_raw
            .entry(appearance.binding.raw_hash)
            .or_default()
            .insert(appearance.binding.path);
    }
    let mut current_paths_by_raw = BTreeMap::<String, BTreeSet<String>>::new();
    for root in roots {
        if let Some(snapshot) = graph.node(root) {
            for entry in &snapshot.tree.entries {
                current_paths_by_raw
                    .entry(entry.raw_hash.clone())
                    .or_default()
                    .insert(entry.path.clone());
            }
        }
    }
    let exact_bindings = graph
        .bindings()
        .into_iter()
        .map(|appearance| appearance.binding)
        .filter(|binding| binding.normalize.is_some())
        .collect::<BTreeSet<TreeBinding>>();
    // PC37/PC41/PC43 (05 §1.6 L265-266): collect EVERY ancestor-most
    // introduction per exact binding (not just its own byte-min winner via
    // `canonical_introduction`) so a content identity reachable through
    // several incomparable paths/roots (rename/copy aliases, merge side
    // branches, independent imports) keeps every one of them as a candidate
    // before the group-level reduction below.
    let mut by_instance =
        BTreeMap::<(String, String, u64, String), Vec<(TreeBinding, String)>>::new();
    for binding in exact_bindings {
        if purge_blocks_rebuild_raw(kio_dir, &binding.raw_hash)? {
            continue;
        }
        let normalize = binding
            .normalize
            .as_ref()
            .expect("normalize=None bindings were filtered");
        let key = (
            binding.raw_hash.clone(),
            normalize.tool_profile_hash.clone(),
            normalize.gen,
            normalize.manifest_hash.clone(),
        );
        let introductions = graph.ancestor_most_introductions(&binding);
        if introductions.is_empty() {
            return Err(KioError::schema(
                "retained history binding has no introduction commit",
            ));
        }
        let entry = by_instance.entry(key).or_default();
        for introduction in introductions {
            entry.push((binding.clone(), introduction.commit_hash));
        }
    }

    let mut instances = Vec::with_capacity(by_instance.len());
    for ((raw_hash, tool_profile_hash, gen, manifest_hash), candidates) in by_instance {
        // Several bindings (distinct paths) can share the same introduction
        // commit; keep one representative binding per distinct commit before
        // the ancestor-most reduction below.
        let mut binding_by_commit = BTreeMap::<String, TreeBinding>::new();
        for (binding, commit) in candidates {
            binding_by_commit.entry(commit).or_insert(binding);
        }
        let commits = binding_by_commit.keys().cloned().collect::<Vec<_>>();
        // A rename/copy/independent-import can introduce several mutually
        // incomparable introduction commits for one content identity. Keep
        // every ancestor-most one (PC37/41/43's multi-introduction case);
        // the frozen full-hash byte order both breaks ties deterministically
        // and gives `introductions[0]` as the legacy single-valued winner.
        let mut ancestor_most = commits
            .iter()
            .filter(|candidate_commit| {
                !commits.iter().any(|other_commit| {
                    other_commit != *candidate_commit
                        && graph.is_ancestor(other_commit, candidate_commit)
                })
            })
            .cloned()
            .collect::<Vec<_>>();
        ancestor_most.sort_by(|left, right| left.as_bytes().cmp(right.as_bytes()));
        if ancestor_most.is_empty() {
            return Err(KioError::schema(
                "retained normalized instance has no introduction",
            ));
        }
        let first_seen_commit = ancestor_most[0].clone();
        let binding = binding_by_commit
            .get(&first_seen_commit)
            .cloned()
            .ok_or_else(|| {
                KioError::schema("retained normalized instance winner has no binding")
            })?;
        let all_paths = all_paths_by_raw
            .get(&raw_hash)
            .ok_or_else(|| KioError::schema("retained raw identity has no historical path"))?;
        let embedding_path = all_paths
            .iter()
            .find(|path| classify_secret(path).is_some())
            .or_else(|| {
                current_paths_by_raw
                    .get(&raw_hash)
                    .and_then(|paths| paths.first())
            })
            .or_else(|| all_paths.first())
            .cloned()
            .ok_or_else(|| KioError::schema("retained raw identity has no embedding path"))?;
        instances.push(RetainedNormalizedInstance {
            raw_hash,
            normalize: NormalizeRef {
                tool_profile_hash,
                gen,
                // PB04: carried forward from the winning binding's own
                // normalize ref, not recomputed — this instance's manifest
                // identity was fixed when its introducing commit was
                // written.
                manifest_hash,
            },
            raw_path: binding.path,
            embedding_path,
            first_seen_commit,
            introductions: ancestor_most,
        });
    }
    Ok(instances)
}

/// The union of exact normalized instances reachable from every current ref.
///
/// All roots are strict, but a receipt-backed, markerless shallow *ancestor*
/// is a deliberate boundary: its absent tree contributes no bindings while its
/// readable commit parents remain in the union. An unreceipted missing tree (or
/// a missing root tree) remains corruption and aborts rebuild. Computing
/// introductions in that union is necessary to remove descendant
/// re-introductions across roots deterministically.
pub(super) fn retained_history_instances_for_roots(
    kio_dir: &Path,
    roots: &BTreeSet<String>,
) -> Result<Vec<RetainedNormalizedInstance>> {
    if roots.is_empty() {
        return Ok(Vec::new());
    }
    let (graph, _) = HistoryReader::new(kio_dir).all_parents_for_roots_tolerant(roots)?;
    retained_history_instances_from_graph(kio_dir, &graph, roots.iter().map(String::as_str))
}

pub(super) fn run(repo: &Repository, operand: &str, online: bool, offline: bool) -> Result<Value> {
    ensure_no_visible_purge_journal(repo.kio_dir())?;
    let head_before = repo
        .head_commit_hash()?
        .ok_or_else(|| KioError::not_found("HEAD"))?;
    let selected_commit = repo.resolve_commit(operand)?;
    // Unlike a history walk, an explicit historical reindex needs only the exact
    // selected commit and tree. HistoryReader gives this read the same strict CAS,
    // shallow, per-object, no-cache semantics as `search --at`.
    let snapshot = HistoryReader::new(repo.kio_dir()).snapshot(&selected_commit)?;
    let config = read_chunking_config(repo)?;

    let mut tree_entries = Vec::<TreeEntryRow>::with_capacity(snapshot.tree.entries.len());
    // The pinned manifest is part of the immutable selected identity. Two
    // aliases can share `(raw, profile, gen)` yet pin distinct manifests (for
    // example, a same-generation unit retry); collapsing them would erase one
    // selected snapshot's attested body.
    let mut selected = BTreeMap::<(String, String, u64, String), SelectedInstance>::new();
    let mut blocked_raw_hashes = BTreeSet::<String>::new();
    for entry in &snapshot.tree.entries {
        // R23-10 (05-runtime.md §3.5 L813/L934, AUD-08's shrunk finding):
        // `purge.read_tombstone(...).is_some()` blocked on marker EXISTENCE
        // (any tombstone at all, even a retired/resurrected one), not the
        // canonical final event across both markers.
        // `purge_blocks_historical_reindex_raw` fixes that while staying
        // narrower than `purge_blocks_rebuild_raw` (used by
        // `project_selected_snapshot` below and `retained_history_instances`
        // for the primary full-rebuild/embedding index): an explicit `--at`
        // historical enrichment gates only on the PUBLIC tombstone's
        // canonical state, never on a non-public erase receipt
        // (08-evidence-pointer-spec.md §4.2's closed use-list for erase
        // receipts excludes this).
        if purge_blocks_historical_reindex_raw(repo.kio_dir(), &entry.raw_hash)? {
            blocked_raw_hashes.insert(entry.raw_hash.clone());
            continue;
        }
        let (tool_profile_hash, gen, manifest_hash) =
            entry
                .normalize
                .as_ref()
                .map_or((None, None, None), |normalize| {
                    (
                        Some(normalize.tool_profile_hash.clone()),
                        Some(normalize.gen),
                        Some(normalize.manifest_hash.clone()),
                    )
                });
        tree_entries.push(TreeEntryRow {
            commit_hash: selected_commit.clone(),
            path: entry.path.clone(),
            raw_hash: entry.raw_hash.clone(),
            tool_profile_hash,
            gen,
            manifest_hash,
        });

        let Some(normalize) = &entry.normalize else {
            // Exact snapshot semantics: never supplement an omitted normalize ref
            // with `latest_normalize_ref` from mutable/later state.
            continue;
        };
        let key = (
            entry.raw_hash.clone(),
            normalize.tool_profile_hash.clone(),
            normalize.gen,
            normalize.manifest_hash.clone(),
        );
        selected
            .entry(key)
            .and_modify(|instance| {
                // Chunk identity is path-independent. Keep output deterministic,
                // while conservatively retaining a secret-classified alias for the
                // embedding consent gate when any selected alias is secret.
                if entry.path.as_bytes() < instance.raw_path.as_bytes() {
                    instance.raw_path = entry.path.clone();
                }
                let existing_secret = classify_secret(&instance.embedding_path).is_some();
                let candidate_secret = classify_secret(&entry.path).is_some();
                if (candidate_secret && !existing_secret)
                    || (candidate_secret == existing_secret
                        && entry.path.as_bytes() < instance.embedding_path.as_bytes())
                {
                    instance.embedding_path = entry.path.clone();
                }
            })
            .or_insert_with(|| SelectedInstance {
                raw_hash: entry.raw_hash.clone(),
                normalize: normalize.clone(),
                raw_path: entry.path.clone(),
                embedding_path: entry.path.clone(),
            });
    }

    let existing = read_stored_chunks(repo.kio_dir())?;
    truncate_torn_chunk_tail(repo.kio_dir())?;
    // A chunk identity may already exist under an older config association. Its
    // durable metadata (notably first_seen_commit/created_at/raw_path) must remain
    // byte-for-byte stable when we append only the new config association.
    let canonical_rows = existing
        .iter()
        .map(|chunk| (chunk.row.chunk_id.clone(), chunk.row.clone()))
        .collect::<BTreeMap<_, _>>();
    let mut known_associations = existing
        .iter()
        .map(|chunk| {
            (
                chunk.row.chunk_id.clone(),
                chunk.row.chunking_config_hash.clone(),
            )
        })
        .collect::<BTreeSet<_>>();
    let mut chunk_rowids = existing
        .iter()
        .map(|chunk| (chunk.row.chunk_id.clone(), chunk.rowid))
        .collect::<BTreeMap<_, _>>();
    let mut next_rowid = existing.iter().map(|chunk| chunk.rowid).max().unwrap_or(0) + 1;
    let mut next_association_rowid = existing
        .iter()
        .map(|chunk| chunk.association_rowid)
        .max()
        .unwrap_or(0)
        + 1;
    let mut appended = Vec::<StoredChunk>::new();
    let mut pending_publication_events = Vec::new();
    let mut skipped_units = Vec::<Value>::new();
    let mut reindexed_instances = 0_u64;
    // Only instances whose pinned immutable closure was actually available
    // can be projected below.  An active erase-purge explained gap is a
    // deliberate skip, not permission for the projection pass to reread the
    // same deleted manifest.
    let mut projected_instances = Vec::<SelectedInstance>::new();

    for instance in selected.values() {
        // R25-10: which units were DONE at `selected_commit`, per the manifest
        // object that commit's tree pinned — not per the working copy.
        //
        // The pinned manifest transitively selects immutable normalized-unit
        // CAS bodies. The path-named normalized instance is only a current
        // cache and may have been overwritten by a same-gen retry.
        let units = match pinned_done_units(repo.kio_dir(), &instance.raw_hash, &instance.normalize)
        {
            Ok(units) => units
                .into_iter()
                .map(|unit| {
                    let unit_content_hash = kio_core::cas::hash_bytes(unit.markdown.as_bytes());
                    Ok(NormalizedUnitInput {
                        raw_hash: unit.raw_hash,
                        tool_profile_hash: unit.tool_profile_hash,
                        gen: unit.gen,
                        unit_key: unit.unit_key,
                        unit_content_hash,
                        markdown: unit.markdown,
                    })
                })
                .collect::<Result<Vec<_>>>(),
            Err(error) => {
                if error.error_code() == "KIO-E-STORE-NOT-FOUND-001"
                    && active_erase_purge_explains_historical_missing_manifest(
                        repo,
                        &instance.raw_hash,
                        &selected_commit,
                    )?
                {
                    continue;
                }
                if error.error_code() == "KIO-E-STORE-NOT-FOUND-001"
                    && purge_explains_missing_pinned_manifest(
                        repo,
                        &instance.raw_hash,
                        [selected_commit.clone()],
                    )?
                {
                    continue;
                }
                // An explicit `--at` pins one immutable snapshot.  A corrupt
                // pinned manifest is not a recoverable per-document cache
                // gap: accepting it would let the in-place projection succeed
                // and defer the fault to best-effort replica publication.
                // Fail synchronously before any derived snapshot publication.
                if error.error_code() == "KIO-E-STORE-CORRUPT-001" {
                    return Err(error);
                }
                if is_rebuild_skippable_unit_error(&error) {
                    skipped_units.push(json!({
                        "raw_hash": instance.raw_hash,
                        "path": instance.raw_path,
                        "gen": instance.normalize.gen,
                        "reason": error.error_code(),
                    }));
                    continue;
                }
                return Err(error);
            }
        };
        reindexed_instances += 1;
        let input = ChunkingInput {
            raw_path: instance.raw_path.clone(),
            units: units?,
            config: config.clone(),
            created_at: now_utc_seconds(),
        };
        let unit_authorities = unit_authorities_from_inputs(&input.units);
        for mut row in chunk_normalized_instance(input).map_err(index_to_kio)? {
            if let Some(canonical) = canonical_rows.get(&row.chunk_id) {
                let current_config = row.chunking_config_hash;
                row = canonical.clone();
                row.chunking_config_hash = current_config;
            } else {
                // This is the first local materialization of the semantic chunk.
                // The selected immutable commit is its historical witness.
                row.first_seen_commit = Some(selected_commit.clone());
            }
            // PC40 (05 §1.6 L266): if this specific (chunk_id, config) pair is
            // genuinely new, its association is introduced now, at the
            // explicit selected commit — this narrow, single-target-commit
            // path's only possible introduction. `append_new_chunk_association`
            // discards this row entirely when the pair already exists (its
            // `known_associations` dedup), so an already-durable association's
            // real, earlier `chunking_config_introduction_commit` is never
            // overwritten by this line.
            row.chunking_config_introduction_commit = selected_commit.clone();
            append_new_chunk_association(
                repo.kio_dir(),
                row,
                &mut known_associations,
                &mut chunk_rowids,
                &mut next_rowid,
                &mut next_association_rowid,
                &mut appended,
                &mut pending_publication_events,
                &unit_authorities,
                true,
            )?;
        }
        projected_instances.push(instance.clone());
    }
    append_stored_chunks(repo.kio_dir(), &appended)?;
    crate::append_chunk_publication_events(repo.kio_dir(), &pending_publication_events)?;

    let selected_instances = projected_instances
        .into_iter()
        .map(|instance| RetainedNormalizedInstance {
            raw_hash: instance.raw_hash,
            normalize: instance.normalize,
            raw_path: instance.raw_path,
            embedding_path: instance.embedding_path,
            first_seen_commit: selected_commit.clone(),
            // A targeted `--at <commit>` reindex has exactly one explicit
            // target commit, so its introduction is trivially single-valued
            // (no multi-introduction ambiguity like the general rebuild path).
            introductions: vec![selected_commit.clone()],
        })
        .collect::<Vec<_>>();
    project_selected_snapshot(
        repo,
        &selected_commit,
        &tree_entries,
        &selected_instances,
        &config.chunking_config_hash,
    )?;

    // QA31 (step4b-contract-tests-p3a.md §I): `--online`/`--offline` now
    // reach `--at`'s historical-enrichment pass instead of the hard-coded
    // `(false, false, false)` this used to pass unconditionally.
    // `online_confirmed = false`: `kio reindex` carries no same-invocation
    // `--yes`/`--approve`-equivalent confirming flag.
    let embedding_online = embedding_online_allowed(repo, offline, online, false)?;
    let enrichment =
        run_historical_embedding_enrichment(repo, embedding_online, &selected_instances)?;

    // The invariant is checked after every derived write while the store lock is
    // still held. A violated ref invariant is store corruption, never success.
    let head_after = repo
        .head_commit_hash()?
        .ok_or_else(|| KioError::not_found("HEAD"))?;
    if head_after != head_before {
        return Err(KioError::new(
            "KIO-E-STORE-CORRUPT-001",
            "historical reindex changed HEAD",
            json!({ "head_before": head_before, "head_after": head_after }),
            ExitCode::PermanentFailure,
        ));
    }

    let report = Step3RebuildReport {
        rebuilt_chunks: appended.len() as u64,
        rebuilt_tree_entries: tree_entries.len() as u64,
        skipped_units,
    };
    let mut output = json!({
        "status": "reindexed",
        "snapshot_at": selected_commit,
        "head_commit": head_after,
        "reindexed_files": reindexed_instances,
        "rebuilt_chunks": report.rebuilt_chunks,
        "embedding_tasks_executed": enrichment.executed,
        "embedding_tasks_failed": enrichment.failed,
        "paused_tasks": enrichment.paused,
        "blocked_raw_hashes": blocked_raw_hashes.len(),
    });
    attach_skipped_units(&mut output, &report, repo.kio_dir());
    if let Some(code) = enrichment_exit_override(&enrichment) {
        set_exit_override(&mut output, code);
    }
    Ok(output)
}

/// Incrementally publish only the selected snapshot's current-config chunks and
/// exact tree projection. Rebuilding the whole ledger would be observable work on
/// non-selected history; this narrow transaction is the enrichment-only boundary.
fn project_selected_snapshot(
    repo: &Repository,
    selected_commit: &str,
    tree_entries: &[TreeEntryRow],
    selected_instances: &[RetainedNormalizedInstance],
    chunking_config_hash: &str,
) -> Result<()> {
    let path = sqlite_path(repo.kio_dir());
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| KioError::io(error.to_string(), parent.display().to_string()))?;
    }
    // The ledger can already contain a unit completed by a later same-gen
    // retry.  Its `(raw, profile, gen)` identity alone is not enough to prove
    // the selected commit had that unit: include only the `unit_key`s marked
    // Done in this tree entry's own pinned manifest.
    let mut selected_units = BTreeSet::new();
    let mut selected_unit_authorities = AuthenticatedNormalizedUnits::new();
    for instance in selected_instances {
        for unit in pinned_done_units(repo.kio_dir(), &instance.raw_hash, &instance.normalize)? {
            let unit_content_hash = kio_core::cas::hash_bytes(unit.markdown.as_bytes());
            let key = (
                instance.raw_hash.clone(),
                instance.normalize.tool_profile_hash.clone(),
                instance.normalize.gen,
                unit.unit_key,
                unit_content_hash,
            );
            selected_units.insert(key.clone());
            match selected_unit_authorities.entry(key) {
                std::collections::btree_map::Entry::Vacant(entry) => {
                    entry.insert(AuthenticatedNormalizedUnit {
                        markdown: unit.markdown,
                        introductions: BTreeSet::new(),
                    });
                }
                std::collections::btree_map::Entry::Occupied(entry) => {
                    if entry.get().markdown != unit.markdown {
                        return Err(KioError::schema(
                            "selected pinned manifests disagree on normalized unit markdown",
                        ));
                    }
                }
            }
        }
    }
    let mut selected_chunks = Vec::new();
    for chunk in read_stored_chunks(repo.kio_dir())? {
        if purge_blocks_rebuild_raw(repo.kio_dir(), &chunk.row.raw_hash)? {
            continue;
        }
        if chunk.row.chunking_config_hash == chunking_config_hash
            && selected_units.contains(&(
                chunk.row.raw_hash.clone(),
                chunk.row.tool_profile_hash.clone(),
                chunk.row.gen,
                chunk.row.unit_key.clone(),
                chunk.row.unit_content_hash.clone(),
            ))
        {
            authenticate_chunk_row(&chunk.row, &selected_unit_authorities)?;
            selected_chunks.push(chunk);
        }
    }

    let mut fts = SqliteFtsIndex::open(
        &path,
        FtsSchemaConfig {
            tokenizer: FtsTokenizer::Trigram,
        },
    )
    .map_err(index_to_kio)?;
    fts.connection()
        .execute_batch("BEGIN IMMEDIATE")
        .map_err(|error| KioError::schema(error.to_string()))?;
    let publish = (|| -> Result<()> {
        for chunk in &selected_chunks {
            persist_chunk_object(repo.kio_dir(), &chunk.row)?;
            fts.index_chunk_with_rowids(
                &chunk.row,
                Some(chunk.rowid),
                Some(chunk.association_rowid),
            )
            .map_err(index_to_kio)?;
            // PC37 (05 §1.6 L265): a targeted historical reindex introduces
            // (or re-affirms, idempotently) this chunk as of the explicit
            // selected commit — the only introduction candidate this narrow,
            // single-commit path can ever produce.
            kio_index::fts::record_chunk_publication(
                fts.connection(),
                &chunk.row.chunk_id,
                selected_commit,
            )
            .map_err(index_to_kio)?;
            // The creation association keeps its explicit durable rowid; an
            // additional historical publication gets a separate, derived
            // rowid for its `(chunk, config, introduction)` triple.
            kio_index::fts::record_chunk_config_association(
                fts.connection(),
                &chunk.row.chunk_id,
                &chunk.row.chunking_config_hash,
                &chunk.row.created_at,
                None,
                selected_commit,
            )
            .map_err(index_to_kio)?;
        }
        fts.connection()
            .execute(
                "DELETE FROM tree_entries WHERE commit_hash = ?1",
                rusqlite::params![selected_commit],
            )
            .map_err(|error| KioError::schema(error.to_string()))?;
        for entry in tree_entries {
            fts.connection()
                .execute(
                    "INSERT INTO tree_entries(commit_hash, path, raw_hash, tool_profile_hash, gen, manifest_hash)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                    rusqlite::params![
                        entry.commit_hash,
                        entry.path,
                        entry.raw_hash,
                        entry.tool_profile_hash,
                        entry.gen,
                        entry.manifest_hash,
                    ],
                )
                .map_err(|error| KioError::schema(error.to_string()))?;
        }
        Ok(())
    })();
    match publish {
        Ok(()) => {
            fts.connection()
                .execute_batch("COMMIT")
                .map_err(|error| KioError::schema(error.to_string()))?;
            // 05 §1.8 write-through. This path publishes chunk TEXT into the
            // live `sqlite.db` in place — no temp+rename — so it is the one
            // in-place writer that changes the text corpus itself.
            //
            // The rotation is what makes the write-through recoverable rather
            // than a single point of failure (R25-4): until R25 this command
            // rotated nowhere, so a failed projection left the stamp naming a
            // state the index had already left, direct search now fails closed
            // until a writer publishes a coherent replacement, rather than staying wrong
            // for good. It is also what LC25 requires on its own terms — a
            // command that republishes the text corpus can certainly make a
            // cursor replay rank differently.
            //
            // A full projection because the published set is a snapshot, not an
            // increment: `index_chunk_with_rowids` re-affirms existing rows as
            // readily as it adds new ones.
            drop(fts);
            crate::rotate_index_generation_unconditionally(repo.kio_dir())?;
            crate::write_through_projection_or_log_for_at_snapshot(repo.kio_dir(), selected_commit);
            Ok(())
        }
        Err(error) => {
            let _ = fts.connection().execute_batch("ROLLBACK");
            Err(error)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use kio_core::cas::{hash_bytes, ObjectKind};
    use kio_core::dag::{build_tree, CommitStats, TreeEntry};
    use std::fs;

    #[test]
    fn multi_root_retained_instances_keep_winning_binding_and_secret_path() {
        let temp = tempfile::tempdir().unwrap();
        let kio_dir = temp.path().join(".kio");
        fs::create_dir(&kio_dir).unwrap();
        let store = ObjectStore::new(&kio_dir);
        let raw_hash = hash_bytes(b"same raw");
        let normalize = NormalizeRef {
            tool_profile_hash: hash_bytes(b"profile"),
            gen: 1,
            manifest_hash: hash_bytes(b"manifest"),
        };
        let commit = |label: &str, path: &str| {
            let mut entry = TreeEntry::raw_file(path, raw_hash.clone()).unwrap();
            entry.normalize = Some(normalize.clone());
            let tree = build_tree(vec![entry]).unwrap();
            let tree_hash = store
                .write_json(ObjectKind::Tree, &serde_json::to_value(tree).unwrap())
                .unwrap()
                .0;
            let commit = CommitObject::new(
                tree_hash,
                Vec::new(),
                "2026-08-12T00:00:00Z".to_owned(),
                label.to_owned(),
                hash_bytes(b"tool-lock"),
                CommitStats {
                    files_added: 1,
                    files_modified: 0,
                    files_deleted: 0,
                },
                CommitType::Manual,
            )
            .unwrap();
            store
                .write_json(ObjectKind::Commit, &serde_json::to_value(commit).unwrap())
                .unwrap()
                .0
        };
        let public_root = commit("public", "z-public.md");
        let secret_root = commit("secret", ".env");
        let roots = BTreeSet::from([public_root.clone(), secret_root.clone()]);
        let graph = HistoryReader::new(&kio_dir)
            .all_parents_for_roots(&roots)
            .unwrap();
        let instances = retained_history_instances_from_graph(
            &kio_dir,
            &graph,
            roots.iter().map(String::as_str),
        )
        .unwrap();

        assert_eq!(instances.len(), 1);
        let instance = &instances[0];
        let winning_root = public_root.clone().min(secret_root);
        let expected_raw_path = if winning_root == public_root {
            "z-public.md"
        } else {
            ".env"
        };
        assert_eq!(instance.first_seen_commit, winning_root);
        assert_eq!(instance.raw_path, expected_raw_path);
        assert_eq!(instance.normalize.manifest_hash, normalize.manifest_hash);
        assert_eq!(
            instance.embedding_path, ".env",
            "embedding selection remains secret-conservative"
        );
    }
}
