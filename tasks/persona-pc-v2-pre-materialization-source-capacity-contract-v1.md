# Persona-PC v2 pre-materialization source and capacity contract v1

Status: **candidate contract; not issued**.  This is the missing bridge between
the static 20-persona artifacts and a future writer.  It neither selects the
core allocation, creates a source plan, grants write/Kio/history authority, nor
claims an actual chunk or capacity observation.

## 1. Purpose

The formal 20-persona lane cannot be materialized from aggregate ratios alone.
Before a writer is allowed, it needs one solution-backed, replay-independent
source plan that maps every source-intent coordinate to exactly one persona,
scope, path, recipe request, chunk quota, and lifecycle role.  The same plan
must be the sole planned input for W0 generation, history compilation, and
post-index comparison.

The contract deliberately distinguishes:

```text
pre-solve source intent / semantic content
  -> solver solution and proof
  -> final planned source plan
  -> writer + Kio index
  -> observed materialization/chunk/history receipts
```

No later identity, observed hash, or receipt may feed back into the solver or
change a ratio, route, quota, cohort, or scope decision.

## 2. Admission prerequisites

The source-plan builder must reject unless all of the following are present as
exact, independently validated pins:

- one selected allocation truth and its 566-coordinate body; an unresolved
  core-versus-legacy comparison is a hard stop;
- version-compatible source inventory/layout, topology, realism profile,
  format/recipe/route metadata, semantic membership, overlay, parameter,
  lifecycle, and namespace/input closure artifacts;
- a fixed Kio build identity and chunking configuration; and
- a solver input, canonical solution, and independent proof that use only
  pre-solve content inputs.

If core supersession is selected, every dependent owner must first be a
versioned successor or have an explicit byte-identity proof as required by
[`persona-pc-core-extension-supersession-dependency-closure-v1-proposal.md`](persona-pc-core-extension-supersession-dependency-closure-v1-proposal.md).
The legacy v2/v3 artifacts remain frozen and cannot be reinterpreted.

## 3. Final planned source-plan shape

The final plan is a bounded descriptor plus external canonical JSONL shards.
Each W0 source row has at least these fields:

```text
persona_id, replay-independent source_intent_key,
source_id, materialization_id, logical_document_id,
scope_key, relative_path, basename,
family, variant_id, extension, gate_role, index_path,
density_bucket, selected_chunk_quota, history_cohort,
language, semantic/fact references,
recipe_id, target_complexity, target_bytes, payload_seed
```

`source_id` and `materialization_id` are domain-separated derivations after
the solver has fixed content-affecting coordinates.  They are not solver
tie-break keys and do not include a root path, observed raw hash, chunk ID,
query result, history receipt, or writer output.

The plan has separate non-overlapping sections for:

- W0 source rows;
- pilot/full subset and residual proof;
- planned per-person/per-scope/family/variant/route/quota aggregates;
- planned W1--W5 source/event transitions compiled only after the W0 plan; and
- external-body pins and canonical limits.

It does not embed payload bytes, rendered binary files, observed database rows,
or actual performance values.

## 4. Exact planning invariants

The independent validator must fail closed unless it can prove all of these:

| area | required invariant |
| --- | --- |
| cardinality | full W0 has 20 personas, 20 formal scopes/person, and the selected allocation's exact source-intent cardinality |
| source mapping | every selected source-intent is mapped exactly once; no source/path/materialization ID is shared across persona or replay |
| scope placement | every formal row maps to one topology leaf and a direct-child basename; no nested managed file, unknown directory, casefold collision, symlink, hard link, clone, or reparse point is permitted |
| quotas | contributor quotas are integers in 1--70; each persona sums to exactly 120,000 planned W0 contributor chunks; raw-only rows have planned/observed chunk quota zero |
| route | each row has exactly one `offline`, `online_ocr`, or `unsupported` route; `unsupported` rows cannot be query answers |
| pilot subset | pilot rows are a strict source/materialization/recipe/semantic/path/quota subset of full; full residual adds rows without mutating pilot identities |
| realism | per-person family/variant and language projections equal the selected profile or an explicit approved delta ledger |
| lifecycle | planned W0--W5 C/H checkpoint targets, scope effects, and transition prerequisites match the immutable event contract |
| determinism | two independent provider reads and two hash-seed cold builds yield byte-identical bodies and descriptor pins |

The plan must report planned values as `planned_*`; it may never expose them as
`actual_*`, `attested_*`, or `observed_*`.

## 5. Capacity preflight and post-write evidence

Planning estimates are necessary but never enough to authorize a full write.
The campaign uses three distinct stages:

1. **Static feasibility:** source count, planned file bytes, expected chunks,
   paths, and resource model are internally consistent.  This is non-writing.
2. **Pilot readback:** all 20 personas are materialized and indexed in the
   approved pilot profile on the target filesystem.  Measure raw tree, CAS,
   SQLite/FTS/WAL, history, staging, transient peak, allocated bytes, inodes,
   RSS, registry count, and per-person post-index chunks.
3. **Full go/no-go:** calculate a full three-replay projection from the pilot
   observations component by component, require at least 25% headroom against
   actual free bytes/inodes and explicit reserve, then allow or refuse the
   full campaign before its first write.

Every measurement receipt identifies destination filesystem, allocation unit,
root nonce, plan pin, writer/build pin, registry digest, and timestamps.  It
separates formal and ambient lane costs before device-level aggregation.

## 6. Observed materialization receipt

After a successful W0 or W5 checkpoint, each `(persona_id, replay_id)` emits a
receipt containing at minimum:

```text
plan / writer / Kio / chunking pins
root nonce and scope-registry digest
file-manifest and path-tree digests
family / variant / route / page-slide-image / MIME / validator aggregates
formal and ambient allocated bytes + inodes
no-link / no-clone / no-cross-person-sharing result
distinct current (scope_key, chunk_hash) digest and count
history-only endpoint digest and count when applicable
planned-versus-observed delta ledger and failure reasons
```

For W0 and W5 final, the formal per-person observed count must satisfy the
chosen contract (currently exactly 120,000 current; W5 at least 180,000
current-plus-history).  A global suite total cannot compensate for a person
below the floor.  Raw-only files contribute zero observed chunks.

## 7. Safe gate sequence

```text
allocation decision + compatible source closure
  -> semantic/query/history input closure and independent review
  -> solver solution/proof
  -> final planned source plan and validation
  -> all-20-person pilot W0 materialization + Kio readback
  -> root-bound full capacity go/no-go
  -> three fresh W0--W5 replays + receipts
  -> M3 / Q_hard / baseline evaluation
```

The separate Phase 2 `eval-gen/` package may be generated only after its own
Phase 1 approval.  It remains a small evaluation fixture and is neither an
input substitute nor evidence for this source-plan contract.
