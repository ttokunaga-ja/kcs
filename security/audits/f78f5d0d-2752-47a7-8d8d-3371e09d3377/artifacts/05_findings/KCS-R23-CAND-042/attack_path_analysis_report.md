# Attack-path analysis: closing snapshot can attach normalization metadata to different bytes

- Candidate: `KCS-R23-CAND-042`
- Ledger row: `KCS-R23-CAND-042`
- Instance key: `KCS-R23-CAND-042`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high (0.97) for the static interleaving; medium for occurrence frequency**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| scan-to-normalize guard | `crates/kcs-cli/src/main.rs` | `9077-9103` |  |
| path-keyed normalize map | `crates/kcs-cli/src/main.rs` | `9390-9426` |  |
| closing read/attach | `crates/kcs-core/src/scope.rs` | `254-299` |  |
| rebuild consumer | `crates/kcs-cli/src/main.rs` | `3045-3090` |  |

## Scope and actor

### Context

This is a production index-to-auto-snapshot workflow. The initial scan-to-normalize guard is sound, but the later publication loses the raw-byte binding and crosses the untrusted working-file boundary into authoritative history.

### In scope

yes; stable-byte use, CAS/DAG provenance, and search/evidence identity are explicit I2, I7, and I8 concerns

### Exposure and identity

no network listener; local or synced file mutation during a normal index operation

An untrusted local content or shared/synced contributor changes a working file while KCS publishes history under the operator identity.

### Boundary crossed

yes: normalization metadata for old bytes is attached to a trusted tree entry naming new bytes

### Authorization scope

internal-only (local scope contributor versus archive provenance boundary)

## Preconditions and attacker control

### Assumptions

- A lower-trust contributor can modify the file during an index run.
- The closing snapshot executes after the modification.
- Consumers rely on the published tree and normalization references for historical provenance or enrichment.

### Preconditions

- Concurrent modification access to the selected scope
- A file change after normalization and before closing snapshot
- A later rebuild or consumer that relies on the published provenance tuple

### Attacker control

yes over working-file bytes and timing for an in-scope local or synced contributor; deterministic scheduling was not demonstrated

### Vector

none

## Attack path

- Index reads and hashes a candidate, normalizes those verified bytes, and stores units for the old raw hash.
- It records only a path-keyed NormalizeRef containing tool_profile_hash and generation.
- A local or synced content contributor changes the file after normalization but before the closing snapshot.
- The closing snapshot rereads the path, records the new raw hash, and attaches the stale NormalizeRef without comparing the expected old raw hash.
- Rebuild resolves the new raw hash with the stale profile/generation, producing missing or skipped enrichment and false historical provenance.

## Impact and reach

- Category: TOCTOU provenance confusion and stale normalization binding
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

data

### Target reach

one scope and each file changed in the normalization-to-snapshot interval

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- Carry expected raw_hash with every path-to-NormalizeRef mapping.
- Reject or drain any file whose closing-snapshot raw hash differs before attaching normalization metadata.

### Mitigations

- Index rehashes scan candidates before normalization.
- Normalized units themselves remain keyed to the old raw hash.
- Rebuild encounters missing/skipped enrichment rather than silently resolving unrelated old units as valid new content.
- The affected history remains local to the selected scope.

### Counterevidence

- The earlier scan-to-normalize raw-hash guard is correct.
- The demonstrated consequence is missing/skipped enrichment and false provenance, not arbitrary file read or code execution.
- No scheduler-controlled race was run.

### Blind spots or proof gap

- The practical interleaving frequency was not measured.
- No downstream decision that turns the false provenance into broader compromise was demonstrated.

## Final decision

A realistic lower-trust scope contributor can cross the provenance boundary in a production workflow, but the impact is bounded to local historical integrity/enrichment and the timing was not measured. Medium impact and medium likelihood map mechanically to low.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
