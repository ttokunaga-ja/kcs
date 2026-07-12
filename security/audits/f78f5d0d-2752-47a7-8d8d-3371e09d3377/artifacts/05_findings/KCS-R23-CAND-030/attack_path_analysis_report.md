# Attack-path analysis: Deterministic PDF normalization repeatedly reopens an unbound pathname

- Candidate: `KCS-R23-CAND-030`
- Ledger row: `KCS-R23-CAND-030`
- Instance key: `KCS-R23-CAND-030:deterministic-pdf-path-reopen`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **medium**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoint_and_closest_control | `crates/kcs-cli/src/main.rs` | `9077-9109` |  |
| root_control | `crates/kcs-adapter/src/deterministic.rs` | `225-249` |  |
| sink | `crates/kcs-cli/src/main.rs` | `9364-9388` |  |

## Scope and actor

### Context

This is the PDF instance of a real normalization workflow. It crosses the untrusted-file-to-authoritative-provenance boundary, but validation proves only scope-local normalized/search integrity and not arbitrary-file disclosure or online upload.

### In scope

Yes.

### Exposure and identity

No public network surface. Exposure is local CLI indexing of a mutable selected-scope PDF supplied or changed by an in-scope content contributor.

The invoking OS user reads the working file and writes the scope-local authoritative store; no service account, credential, or remote identity participates in the validated path.

### Boundary crossed

Verified: later PDF bytes cross into trusted normalized persistence while bound to the earlier PDF's raw identity; repeated reopens can also mix versions within one normalized result.

### Authorization scope

internal-only

## Preconditions and attacker control

### Assumptions

- A lower-trust contributor can concurrently replace a selected-scope PDF pathname.
- The operator runs ordinary deterministic indexing.
- One or more replacements land after the verified read and before or between later PDF reads.

### Preconditions

- Concurrent write/rename authority in the selected root.
- Operator deterministic indexing of the PDF.
- Favorable scheduling after the first verified read.

### Attacker control

yes — the contributor controls replacement PDF bytes and timing; stable mixed-page output was not dynamically demonstrated.

### Vector

none

## Attack path

- The operator indexes a selected-scope PDF version A, and run_index_pipeline reads and verifies H(A) at crates/kcs-cli/src/main.rs:9077-9103.
- A lower-trust concurrent pathname writer replaces A after that read with PDF B, and may replace it again between later page reads.
- prepare_units and the deterministic adapter independently reopen the pathname at crates/kcs-pipeline/src/prepare.rs:72-103 and crates/kcs-adapter/src/deterministic.rs:225-249 without comparing reopened bytes to the earlier raw hash.
- KCS persists B-derived or mixed-version normalized PDF units under H(A) at crates/kcs-cli/src/main.rs:9364-9388.

## Impact and reach

- Category: CWE-367-style pathname TOCTOU causing PDF normalization identity misbinding
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

data

### Target reach

One PDF's normalized units and search/evidence provenance in one selected scope.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- initial scan/type and symlink filtering
- current-buffer raw-hash comparison
- normalized response/persistence shape checks
- re-index recovery

### Mitigations

- The initial current-buffer hash check rejects replacements occurring before it.
- Symlinks observed during initial scan enumeration are rejected.
- The proved impact is confined to normalized/search evidence integrity in one scope.
- A stable re-index can rebuild affected derived state.

### Counterevidence

- The initial raw-hash comparison closes pre-read replacements.
- No barrier-controlled replacement proved practical reliability, mixed-page output, outside-file disclosure, or a network send.
- Initial symlink filtering reduces but does not bind later pathname opens.

### Blind spots or proof gap

- Race success rate and stable mixed-version output are unmeasured.
- Validation did not establish a broader downstream compromise beyond the affected scope's derived state.

## Final decision

The trusted provenance misbinding is a meaningful in-scope boundary regression, so local/internal exposure alone does not suppress it. Impact is medium because the demonstrated result is bounded, recoverable integrity loss in one scope. Likelihood is medium because a lower-trust writer and favorable timing are needed and no controlled race was run. The matrix yields Low/P3.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
