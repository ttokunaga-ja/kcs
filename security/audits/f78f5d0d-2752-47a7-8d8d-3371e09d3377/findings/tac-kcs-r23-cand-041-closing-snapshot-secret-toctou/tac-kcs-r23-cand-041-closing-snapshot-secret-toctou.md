# Closing Snapshot Can Ingest a Newly Introduced Tier-A Secret

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
contains a time-of-check/time-of-use gap in both manual `snapshot` and
`index` archival flows. The CLI first previews the selected scope, classifies
the files that already exist, and converts currently ignored Tier-A names into
an exclusion set. Later, the closing snapshot enumerates the scope again and
applies only that stale set of names before writing raw bytes into the local
CAS and commit history.

If a lower-trust local or synced contributor can create or rename a direct
child during that interval, we can introduce `.env`, `*.pem`, or another
Tier-A secret-bearing name after preview but before the closing enumeration.
Because the new name was not present in the preview set, KCS reads and archives
the plaintext bytes. The final attack-path decision rates this as **Low
severity / P3**: the crossed boundary is real, but the immediate sink is the
operator's owner-only local archive, no automatic remote send was established,
and the practical race width was not dynamically measured.

I reviewed the vulnerable revision and the source trace directly; I did not run
a barrier-controlled race against KCS itself. The included PoC is a safe local
model that exercises the same stale-exclusion state transition with synthetic
files in a temporary directory.

## Background

KCS treats Tier-A secret files as content that should not be archived as raw
scope material. For manual snapshots, the CLI builds a scan preview with the
shared scanner and turns the preview's ignored candidates into a set of file
names to exclude:

```rust
// crates/kcs-cli/src/main.rs, Command::Snapshot, lines 456-472
let preview = build_scan_preview(ScanPreviewRequest {
    scope_path: repo.root().display().to_string(),
    include_raw_hashes: false,
    require_network_approval: false,
})
.map_err(pipeline_to_kcs)?;
let excluded = preview
    .candidates
    .iter()
    .filter(|candidate| candidate.ignored)
    .map(|candidate| candidate.input_path.clone())
    .collect::<BTreeSet<_>>();
let outcome = repo.snapshot_filtered(args.message.as_deref(), None, &excluded)?;
```

The `index` command follows the same shape. We first build a preview and later
pass the preview-derived exclusion set into the auto snapshot:

```rust
// crates/kcs-cli/src/main.rs, run_index, lines 575-580 and 623-635
let preview = build_scan_preview(ScanPreviewRequest {
    scope_path: repo.root().display().to_string(),
    include_raw_hashes: !args.preview,
    require_network_approval: !args.offline,
})
.map_err(pipeline_to_kcs)?;

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

The important invariant is temporal: classification must protect the exact
bytes and names that are ultimately persisted. A preview-only classification is
safe for files that do not drift, and it correctly excludes Tier-A files that
already existed when the preview ran. It stops being sufficient when another
actor can mutate the direct children between preview and commit.

## Vulnerability Details

The closing snapshot path performs a fresh filesystem enumeration. At this
point we would expect KCS either to reclassify each entry at last use or to bind
the accepted preview identity tightly enough that new names cannot slip in.
Instead, the core layer treats the caller-provided `excluded_paths` set as a
complete policy decision and only compares the current file name against that
set:

```rust
// crates/kcs-core/src/scope.rs, Repository::build_working_tree_with_normalize,
// lines 254-299
for entry in fs::read_dir(&self.root).kcs_io(&self.root)? {
    let entry = entry.kcs_io(&self.root)?;
    if entry.file_name() == ".kcs" {
        continue;
    }
    let path = entry.path();
    let file_type = entry.file_type().kcs_io(&path)?;
    if file_type.is_dir() {
        continue;
    }
    if !file_type.is_file() {
        eprintln!("warning: skipping non-regular file: {}", path.display());
        continue;
    }
    let file_name = match entry.file_name().into_string() {
        Ok(name) => name,
        Err(_) => {
            eprintln!("warning: skipping non-UTF-8 file name: {}", path.display());
            continue;
        }
    };
    if excluded_paths.contains(&file_name) {
        continue;
    }
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
}
```

If we carry the preview state into this function, the bypass is precise:

1. The operator starts `kcs snapshot` or a non-preview `kcs index`.
2. KCS previews the current direct children and records ignored names such as
   an already-present `present.pem`.
3. Before `build_working_tree_with_normalize()` reaches the closing
   enumeration, a lower-trust local or synced contributor creates `.env` or
   renames an existing file into a Tier-A name.
4. The closing enumeration sees the new file, but `excluded_paths` does not
   contain the new name.
5. KCS reads the file and calls `write_raw()`, then publishes a tree entry that
   references the plaintext raw object.

The bug is not that the scanner fails to recognize Tier-A names in general.
Files present during preview are excluded correctly. The missing control is at
the last-use boundary: the core snapshot path never asks whether the newly
enumerated name would be ignored if classified now, and the CLI never proves
that the closing candidate is the same candidate that was previewed.

## Exploitability Analysis

The useful primitive is unintended archival rather than immediate exfiltration.
We control the direct-child name and bytes through a local or synced writer that
can mutate the selected scope while the KCS operator runs a normal workflow.
The strongest path is to time a create or rename so a Tier-A name appears after
preview. Once the file reaches `write_raw()`, the sensitive bytes are
irreversibly represented in the local object store and the commit history can
continue to reference that object even if the working-tree file is later
removed.

The attack is easiest to reason about when the writer uses rename rather than
incremental writes. We can prepare bytes under a benign temporary name outside
the final Tier-A classification shape, then atomically rename the file to
`.env` or `service.pem` during the preview-to-snapshot interval. That reduces
the risk of KCS reading a partially written file and gives us a single
filesystem event to place inside the window. A synced-folder actor has a
similar shape, although sync latency makes timing less deterministic.

There are meaningful constraints. The saved attack-path review did not measure
the width or frequency of the window, and KCS's store is intended to be
owner-only. We also do not get direct code execution or direct network
disclosure from this primitive. The value comes from crossing the repository
policy boundary: data that should have been excluded as Tier-A becomes part of
the authoritative archive and may later be retained, copied, backed up, or
processed as ordinary historical content.

Two defensive observations make variant analysis straightforward. First, any
workflow that does preview-time policy classification but performs a later
filesystem read by mutable name has the same weakness unless it rechecks at the
read site. Second, binding only the path string is weaker than binding the
candidate identity. If the fix chooses an identity-binding approach, we should
ensure it rejects name, type, and byte drift rather than only checking that the
same path still exists.

## Proof of Concept

The PoC under `poc/` is a non-destructive local model of the vulnerable state
machine. It does not call KCS, touch a real `.kcs` store, use credentials, or
read real secrets. The script creates a temporary scope, performs a preview
classification over the initial names, introduces `.env` after preview, and
then runs the same kind of closing enumeration that excludes only names from
the stale preview set.

From the report directory:

```sh
cd poc
make
```

Representative output:

```text
[+] created synthetic scope
[+] preview excluded names: ['present.pem']
[+] introduced Tier-A name after preview: .env
[+] vulnerable closing snapshot would archive: ['notes.md', '.env']
[!] stale exclusion admitted newly introduced Tier-A file: .env
[+] fixed last-use classification would exclude: ['.env', 'present.pem']
```

The expected vulnerable result is the warning line showing `.env` in the
closing snapshot's archive list. The expected fixed result is that a last-use
classifier excludes both the original `present.pem` and the newly introduced
`.env`.

## Remediation

The invariant to restore is simple: the decision to persist raw bytes must be
made on the same candidate that is being persisted. The most direct patch is to
move Tier-A classification to the closing enumeration, immediately before
`fs::read()` and `write_raw()`. Conceptually, the core loop should reject a
file if either the preview exclusion set contains its name or the current entry
is classified as ignored at last use:

```rust
// Sketch: keep the preview exclusion as defense in depth, but classify the
// closing candidate before raw persistence.
if excluded_paths.contains(&file_name) || classify_secret_name(&file_name).ignored {
    continue;
}

let bytes = fs::read(&path).kcs_io(&path)?;
let raw_hash = if store_raw {
    self.store.write_raw(&bytes)?
} else {
    hash_bytes(&bytes)
};
```

In the actual codebase, this may mean moving a small classification interface
into `kcs-core`, passing a classifier callback into
`build_working_tree_with_normalize()`, or keeping the classifier in the CLI and
creating a candidate list whose identities are verified by the core layer. The
important part is not the module boundary; it is that a fresh `.env` or PEM
name seen during the closing enumeration cannot reach `write_raw()`.

A stronger structural fix is to bind preview candidates to immutable
properties and reject drift before publication. For example, the preview could
record expected file type, normalized direct-child name, and a raw hash when
available, then the closing snapshot could require the current entry to match
that accepted identity. That approach catches both newly introduced Tier-A
names and benign-looking names whose bytes change after policy approval.

Regression coverage should include:

- manual snapshot with `.env` created after preview but before closing
  enumeration;
- `index` auto snapshot with the same interleaving after
  `run_index_pipeline()`;
- a control case where a Tier-A file present during preview remains excluded;
- a benign file introduced during the interval, to confirm the fix does not
  over-block ordinary new content unless the chosen identity-binding policy is
  intentionally stricter.

The most valuable regression harness would add a test hook or barrier between
preview and `build_working_tree_with_normalize()` so the test can create the
new Tier-A file deterministically rather than racing wall-clock timing.

## Summary

KCS already knows how to classify Tier-A secret names, but in these workflows
it applies that policy to a preview snapshot of the directory rather than to
the files ultimately archived. We followed the source from preview
classification, through the stale exclusion set, into the closing enumeration
and raw object write. The safe PoC demonstrates the same state transition with
synthetic input: a newly introduced `.env` name is absent from the stale set and
therefore reaches the archive list.

Future variant review should look for other preview-to-persist paths where
policy is computed from mutable names and then consumed later without identity
binding. This is especially relevant for archive, indexing, normalization, and
approval workflows, because those paths often convert a user-facing preview
into durable historical state.
