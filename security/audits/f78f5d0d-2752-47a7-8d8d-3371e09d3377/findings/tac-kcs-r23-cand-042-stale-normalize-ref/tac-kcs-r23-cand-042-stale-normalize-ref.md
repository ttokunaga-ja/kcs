# Closing snapshot can attach normalization metadata to different bytes

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` can publish a tree
entry whose `raw_hash` names one set of file bytes while its `normalize` metadata
was produced for earlier bytes at the same path. The affected path is the normal
`kcs index` auto-snapshot workflow: the indexer correctly rehashes a candidate
before normalization, but it then records only a path-keyed `NormalizeRef`. When
the closing snapshot later rereads the working file, it attaches that earlier
reference by file name without checking that the bytes are still the bytes that
were normalized.

I reviewed the vulnerable revision directly and ran the included synthetic
Python probe locally; I did not run a scheduler-controlled race inside KCS or
against a live shared folder. The saved scan validation rated the static
interleaving with high confidence, and the final attack-path decision is
reportable, low severity, priority P3: the impact is local provenance and
enrichment integrity rather than code execution or credential exposure.

## Background

KCS treats working-file bytes, normalized units, and snapshot tree entries as
content-addressed evidence. During `kcs index`, we first scan candidate files,
normalize eligible content, and then create an automatic snapshot that commits
the current tree. The important invariant is that a tree entry's `raw_hash` and
its optional `NormalizeRef` must describe the same file bytes. If they drift, a
later rebuild can carry a plausible profile and generation for a document whose
normalized units were never produced for the tree entry's raw hash.

The auto-snapshot call receives the normalization map produced by the index
pipeline:

```rust
// crates/kcs-cli/src/main.rs:623-635
let index_result = run_index_pipeline(&repo, &preview, &args)?;
let excluded = preview
    .candidates
    .iter()
    .filter(|candidate| candidate.ignored)
    .map(|candidate| candidate.input_path.clone())
    .collect::<BTreeSet<_>>();
let outcome = repo.auto_snapshot_with_normalize(
    Some("kcs index auto snapshot"),
    None,
    &excluded,
    &index_result.normalize_by_path,
)?;
```

`NormalizeRef` itself contains the tool profile and generation, but no raw hash
for the bytes it was prepared from:

```rust
// crates/kcs-core/src/dag.rs:11-25
pub struct NormalizeRef {
    pub tool_profile_hash: String,
    #[serde(default)]
    pub gen: u64,
}

pub struct TreeEntry {
    pub path: String,
    #[serde(rename = "type")]
    pub entry_type: String,
    pub raw_hash: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub normalize: Option<NormalizeRef>,
}
```

That shape is safe only if the publication path can prove the reference still
belongs to the current bytes. Here, the later snapshot path has no expected hash
to compare.

## Vulnerability Details

The first part of the workflow is careful. When the pipeline is ready to
normalize a candidate, it reads the file again and compares the current hash to
the scan-time hash. If the file changed between scan and normalization, the
candidate is skipped instead of persisting normalized units under stale identity:

```rust
// crates/kcs-cli/src/main.rs:9077-9103
let path = repo.root().join(&candidate.input_path);
let bytes = fs::read(&path)
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
let current_hash = hash_bytes(&bytes);
if let Some(scan_hash) = &candidate.raw_hash {
    if scan_hash != &current_hash {
        append_event_log(
            "KCS-I-INDEX-INPUT-CHANGED-001",
            "input file changed between scan and normalize; skipped to preserve              content-addressing (re-run index)",
            json!({ "input_path": candidate.input_path }),
        )?;
        result.failed_files += 1;
        continue;
    }
}
let raw_hash = current_hash;
```

We can rely on this guard for the scan-to-normalize interval. The issue begins
after normalization succeeds. The pipeline records the completed normalization
in a map keyed only by path:

```rust
// crates/kcs-cli/src/main.rs:9417-9423
result.normalize_by_path.insert(
    candidate.input_path.clone(),
    NormalizeRef {
        tool_profile_hash: markdown_profile_hash.clone(),
        gen: 0,
    },
);
```

At this point, the normalized units are bound to `raw_hash`, but the publication
handle we carry forward has lost that hash. If the file is changed after this
insert and before the automatic snapshot reads the tree, we have no field left
that says which raw bytes the reference expects.

The closing snapshot then reads the current file bytes, computes or stores the
current raw hash, and attaches a normalization reference by file name:

```rust
// crates/kcs-core/src/scope.rs:290-299
let bytes = fs::read(&path).kcs_io(&path)?;
let raw_hash = if store_raw {
    self.store.write_raw(&bytes)?
} else {
    hash_bytes(&bytes)
};
let mut tree_entry = TreeEntry::raw_file(file_name.clone(), raw_hash)?;
tree_entry.normalize = normalize_by_path.get(&file_name).cloned();
tree_entry.validate()?;
entries.push(tree_entry);
```

This is the exact vulnerable transition. We enter the function with a
path-keyed reference for old bytes. We then read new bytes, create a tree entry
whose `raw_hash` names those new bytes, and copy the old `NormalizeRef` into the
entry because the path still matches. There is no comparison against the raw
hash that was verified immediately before normalization.

The bad tuple reaches a real consumer during rebuild. If the tree entry carries
`normalize`, rebuild uses the tree entry's current `raw_hash` together with that
profile and generation:

```rust
// crates/kcs-cli/src/main.rs:3063-3083
for entry in &tree.entries {
    let normalize = match &entry.normalize {
        Some(normalize) => normalize.clone(),
        None => match latest_normalize_ref(repo.kcs_dir(), &entry.raw_hash)? {
            Some(normalize) => normalize,
            None => continue,
        },
    };
    tree_entries.push(TreeEntryRow {
        commit_hash: head.clone(),
        path: entry.path.clone(),
        raw_hash: entry.raw_hash.clone(),
        tool_profile_hash: Some(normalize.tool_profile_hash.clone()),
        gen: normalize.gen,
    });
    let units = match load_normalized_units(
        repo.kcs_dir(),
        &entry.raw_hash,
        &normalize.tool_profile_hash,
        normalize.gen,
    ) {
```

Because the normalized unit store was populated for the old raw hash, the new
raw hash plus stale profile/generation normally resolves to missing or skipped
enrichment. Even when the failure mode is availability-oriented, the published
tree row still asserts a misleading provenance tuple: this file at this commit
appears to have a specific normalization profile and generation even though that
work was done for different bytes.

## Exploitability Analysis

The realistic actor is a lower-trust local or shared-folder contributor who can
modify a selected scope while an operator runs `kcs index`. We do not need a
network listener or credentials. We need timing: the contributor changes a file
after KCS has normalized it and inserted `normalize_by_path[path]`, but before
the automatic snapshot's `fs::read()` for that file.

The strongest practical route is a provenance-confusion route. We let the
operator index content `A`, wait until KCS has generated normalized units for
`hash(A)`, and then replace the working file with content `B` before the closing
snapshot. The resulting tree entry names `hash(B)` but carries the
`tool_profile_hash` and `gen` selected for `A`. From there, rebuild asks for
units under `(hash(B), profile(A), gen(A))`. The validated consequence is
missing or skipped enrichment plus false historical metadata for that path.

This route is bounded. We do not get arbitrary file read, arbitrary write, code
execution, or secret disclosure from the saved evidence. KCS already prevents a
similar earlier race between scan and normalization, and normalized units remain
keyed by raw hash. That means a stale reference does not normally cause old units
to be silently treated as units for new bytes; instead, the rebuild path records
the tuple, tries to load units for the new hash, and can skip the document when
they are absent. The security value is still real because KCS' archive and search
features depend on stable evidence identity, but the primitive is local integrity
and availability degradation rather than a direct host compromise.

A stronger exploit would need either a measured scheduling primitive that makes
the replacement reliable across many files, or a downstream consumer that trusts
the tree row's profile/generation without resolving units by raw hash. I did not
find such a downstream escalation in the saved validation package. That is why
we keep the final severity at low even though the violated invariant is central
to provenance correctness.

## Proof of Concept

The included PoC is a synthetic regression probe. It models the vulnerable state
transition in memory instead of racing KCS or modifying a real repository. We
create old bytes, compute their raw hash, create a path-keyed `NormalizeRef`,
then publish new bytes under the same path. In the vulnerable model, the tree
entry has the new raw hash and the stale normalization reference. In the fixed
model, the pending reference also carries `expected_raw_hash`, so publication
rejects the drift and leaves `normalize` unset.

Run it from the report directory:

```sh
cd poc
make run
```

Representative output:

```text
old_hash=cf70c13e81b90e64aa8b860f164787442aef1ff9be1cca4fd3c5148477e48f10
new_hash=3c03ccf866410229debb5fbf97a3b78676c4289e45b647754825b8cd9b5c1957
vulnerable_tree_has_normalize= True
vulnerable_rebuild_units_found= False
fixed_drift_rejected= True
fixed_tree_has_normalize= False
```

The probe is deliberately non-destructive. It does not run `kcs index`, does not
read any user content, and does not attempt to win a scheduler race. Its purpose
is to make the identity error and the remediation invariant executable as a
local regression check.

## Remediation

The invariant to restore is simple: a normalization reference may be attached to
a tree entry only when the closing snapshot's raw hash is the same raw hash that
was verified immediately before normalization. We should carry that expected raw
hash alongside the pending reference, then reject or drain the entry when the
snapshot sees different bytes.

One minimal shape is to keep `TreeEntry.normalize` unchanged, but change the
in-memory publication map to include the expected hash:

```rust
struct PendingNormalizeRef {
    expected_raw_hash: String,
    normalize: NormalizeRef,
}

// after successful normalization
result.normalize_by_path.insert(
    candidate.input_path.clone(),
    PendingNormalizeRef {
        expected_raw_hash: raw_hash.clone(),
        normalize: NormalizeRef {
            tool_profile_hash: markdown_profile_hash.clone(),
            gen: 0,
        },
    },
);

// during closing snapshot
if let Some(pending) = normalize_by_path.get(&file_name) {
    if pending.expected_raw_hash == raw_hash {
        tree_entry.normalize = Some(pending.normalize.clone());
    } else {
        append_event_log(
            "KCS-I-SNAPSHOT-NORMALIZE-DRIFT-001",
            "input file changed after normalization; normalization metadata not attached",
            json!({ "path": file_name }),
        )?;
    }
}
```

Whether the implementation skips the changed file, snapshots it without
`normalize`, or aborts the auto-snapshot should be a product decision. For the
security invariant, the key point is that it must not publish
`raw_hash(current_bytes)` with `NormalizeRef(old_bytes)`.

Regression tests should cover three cases. First, unchanged bytes attach the
reference as before. Second, bytes changed after normalization do not attach the
reference and emit a visible event. Third, rebuild of the resulting tree does
not create a `tree_entries` row that claims the changed raw hash has the old
profile/generation.

## Summary

We proved a local TOCTOU provenance bug in the `kcs index` closing path. The
indexer correctly protects the scan-to-normalize interval, but then downgrades a
raw-hash-bound normalization result into a path-keyed publication reference. The
auto-snapshot rereads current bytes and attaches that reference by path, so a
concurrent local or synced-file edit can publish a tree entry whose raw hash and
normalization metadata describe different byte streams.

The included PoC demonstrates the identity mismatch and the proposed
`expected_raw_hash` fix without touching a real repository. Future variant work
should review every place KCS converts content-addressed state into path-keyed
state across a filesystem boundary, especially around auto-snapshot, repair,
rebuild, and incremental enrichment workflows.
