# Validation: Persisted DAG semantics are not revalidated, enabling poisoned fields and path escape

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-036 |
| Instance key | KCS-R23-CAND-036:persisted-tree-normalize-path |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-core/src/dag.rs:40-79 |
| Root control | crates/kcs-core/src/scope.rs:742-755 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Severity | high |
| Method | V6 poisoned-state provenance by exact static construction, V10 complete static trace, and safe lexical /tmp control |

The candidate survives at High because a supplied or copied scope store can carry a content-hash-correct but semantically invalid tree, and the explicit reindex workflow consumes its unvalidated path-bearing normalize field in filesystem create, overwrite, and recursive-cleanup operations outside the selected store. The complete V10 addresses the nearest controls; no real store or external target was touched.

## Validation rubric

- [x] Establish how a lower-trust supplied store can provide a CAS-integrity-valid tree and commit.
- [x] Compare writer-side TreeEntry validation with the persisted read path.
- [x] Trace the unvalidated normalize field through path construction to concrete filesystem effects.
- [x] Address reindex confirmation, CAS hash verification, suffix constraints, and failure cleanup.
- [x] Confirm lexical non-containment using only a disposable /tmp path, with no KCS mutation.

## Exact source, control, sink, and boundary

- Source and boundary: a shared, copied, or preseeded .kcs store can contain a correctly content-hashed commit and tree whose TreeEntry.normalize.tool_profile_hash includes path separators and parent components. The contributor can compute the corresponding CAS hashes, so CAS integrity does not imply semantic validity.
- Intended control: TreeEntry::validate rejects an invalid tool_profile_hash at crates/kcs-core/src/dag.rs:40-65, and build_tree invokes that validator at 76-79. CommitObject::new similarly validates structural hash/timestamp fields at 117-156. These are construction-time controls only.
- Root-control gap: Repository::read_commit and Repository::read_tree at crates/kcs-core/src/scope.rs:742-755 check the CAS object kind and deserialize JSON, but never reconstruct through CommitObject::new, TreeEntry::validate, or build_tree.
- Countercontrol addressed: ObjectStore::read_by_hash verifies the requested hash and actual bytes at crates/kcs-core/src/cas.rs:78-100. A malicious store author can satisfy that check; it does not examine path-bearing semantics.
- Reachable workflow: reindex requires --force and --yes at crates/kcs-cli/src/main.rs:2839-2853, opens and locks the store, then reads the HEAD tree at 2854-2868. For each persisted normalize entry, it passes raw_hash and the unvalidated tool_profile_hash to copy_normalized_instance_gen at 2879-2890.
- Broken path control: normalized_instance_dir uses a raw-hash fanout but embeds tool_profile_hash verbatim into a path at crates/kcs-pipeline/src/markdownize.rs:311-329. No component or containment validation intervenes.
- Filesystem sinks: copy_normalized_instance_gen creates new_dir at crates/kcs-cli/src/main.rs:5453-5473, reads the constructed old_dir and atomically overwrites manifest/unit JSON in new_dir at 5477-5538, and recursively removes new_dir on any error at 5540-5543.
- Result: parent components can move old_dir/new_dir outside .kcs. The operation can create a directory, replace fixed KCS-shaped JSON names, or recursively remove a selected user-writable directory when the copy fails.

## Evidence and safe control observation

- All code references came from immutable revision 0e19f3c6489da458e93a982a333c308d92d0a0ae.
- A disposable /tmp calculation reproduced the exact normalized_instance_dir component shape using a benign marker and parent components. The normalized destination had common-path containment false relative to the normalized_units fanout base. No directory at that destination was created and no KCS command ran.
- The proof is semantic rather than an actual poisoned-store payload: the formatting and filesystem calls are direct and contain no later canonicalization or starts_with check.

## Counterevidence and severity calibration

- Exploitation requires adoption of a lower-trust store, not merely control of an ordinary direct-child document in an already private healthy scope.
- The operator must intentionally run reindex --force --yes. This is a meaningful interaction, but it is the documented recovery/rebuild operation for an adopted archive and is not consent to filesystem effects outside that scope.
- Result paths retain the generated .gN suffix and writes use fixed manifest.json and normalized-unit file shapes. This constrains exact targets but does not restore scope containment.
- Freshly constructed trees pass TreeEntry::validate; only persisted/adopted semantics are affected.
- Same-user unrestricted mutation of a private live store would already grant broad local authority, but the supplied/copied-store boundary is independently in scope under the central threat model.

## Proof gap and next step

No material V10 gap remains for path reachability or filesystem effect. A hermetic two-root runtime test would raise assurance but would not change reportability: open a disposable supplied store, run the reindex copy helper against benign fixture directories, and assert rejection before create_dir_all. It must not use an external path or real data.

## Closure row

| Ledger row id | Instance key | Source reference | Seed anchor | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-036 | KCS-R23-CAND-036:persisted-tree-normalize-path | R23 discovery | crates/kcs-core/src/dag.rs:40-79 | crates/kcs-core/src/scope.rs:742-755 | CAS-valid supplied HEAD tree | uncontained normalized_instance_dir into create/write/remove at crates/kcs-cli/src/main.rs:5453-5543 | reportable | explicit reindex and .gN/fixed-name constraints; complete V10 has no material path gap | yes |
