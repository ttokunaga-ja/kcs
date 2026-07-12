# Attack-path analysis: Prepare-stage reopen can poison prepared CAS identity

- Candidate: `KCS-R23-CAND-031`
- Ledger row: `KCS-R23-CAND-031`
- Instance key: `KCS-R23-CAND-031:prepare-cas-identity`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **medium**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoint_and_closest_control | `crates/kcs-cli/src/main.rs` | `9077-9118` |  |
| root_control | `crates/kcs-pipeline/src/prepare.rs` | `72-103` |  |
| sink | `crates/kcs-cli/src/main.rs` | `9505-9541` |  |

## Scope and actor

### Context

The prepare and CAS publication path is part of ordinary indexing. The issue crosses from lower-trust mutable content into an authoritative content-addressed object namespace, but the proven outcome is recoverable scope-local integrity loss rather than confidentiality or code execution.

### In scope

Yes.

### Exposure and identity

Local CLI only, reached by indexing a mutable selected-scope file. There is no listener, ingress, or remote request surface.

The invoking OS user owns the selected-scope .kcs store; no network or service identity is involved.

### Boundary crossed

Verified: a lower-trust pathname replacement causes bytes from A to enter trusted prepared CAS storage under a name derived from B, breaking the content/name integrity boundary.

### Authorization scope

internal-only

## Preconditions and attacker control

### Assumptions

- A lower-trust selected-root contributor can replace the pathname concurrently.
- The operator runs indexing and the replacement lands between the first verified read and prepare_units.
- The mismatched object path does not already contain a verified correct object.

### Preconditions

- Concurrent write/rename authority in the selected root.
- Operator indexing.
- Favorable scheduling between initial verification and prepare-stage reopen.

### Attacker control

yes — the contributor controls B and replacement timing; the old A buffer used for publication is selected by the earlier read.

### Vector

none

## Attack path

- run_index_pipeline reads selected-scope file version A, computes its raw hash, and verifies it against scan state at crates/kcs-cli/src/main.rs:9077-9103.
- A lower-trust contributor replaces the pathname with version B before prepare_units reopens it at crates/kcs-pipeline/src/prepare.rs:90.
- prepare_units derives prepared_hash values from B but does not consume or compare its raw_hash field, while write_prepared_objects receives the retained A buffer.
- write_prepared_objects publishes A bytes at paths named by H(B) at crates/kcs-cli/src/main.rs:9505-9541, creating a persistent prepared-CAS identity mismatch.

## Impact and reach

- Category: CWE-367-style pathname TOCTOU causing content-addressed prepared-object identity corruption
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

data

### Target reach

Prepared object(s) for one raced file in one selected scope, with downstream consumers potentially observing hash/name disagreement.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- initial raw-hash comparison
- atomic prepared-object publication
- existing path/shape construction
- scope rebuild recovery

### Mitigations

- The initial scan/current-buffer hash comparison rejects earlier replacements.
- Temporary-file, fsync, and rename publication protects crash atomicity.
- The effect is limited to prepared/index integrity and processing reliability in the affected scope.
- A controlled rebuild can recover affected derived objects.

### Counterevidence

- Atomic publication prevents partial visibility but does not validate content/name agreement.
- The pre-prepare hash comparison closes replacements before the first read.
- No controlled replacement or demonstrated high-impact downstream reliance was run.

### Blind spots or proof gap

- Race reliability and exact downstream failure modes are unmeasured.
- No confidentiality, outside-scope write, or code-execution consequence was established.

## Final decision

This is an explicit content-identity trust-boundary regression in a real product path, so the internal CLI surface is not dispositive. The proved corruption is bounded and recoverable, giving medium impact; the unmeasured post-check race gives medium likelihood. The mechanical matrix maps that pair to Low/P3.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
