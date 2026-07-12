# Attack-path analysis: Deterministic normalization persists a later path read under the earlier raw hash

- Candidate: `KCS-R23-CAND-029`
- Ledger row: `KCS-R23-CAND-029`
- Instance key: `KCS-R23-CAND-029`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| caller_control | `crates/kcs-cli/src/main.rs` | `9072-9118` | The caller reads and verifies one buffer, retains it for object writes, then passes only a mutable pathname and earlier raw hash to later stages. |
| prepare_reopen | `crates/kcs-pipeline/src/prepare.rs` | `72-103` | Preparation independently reads input_path and derives prepared_hash without checking request.raw_hash. |
| path_request | `crates/kcs-cli/src/main.rs` | `9282-9304` | MarkdownizeRequest carries earlier raw_hash and mutable path as independent fields. |
| normalization_sink | `crates/kcs-adapter/src/deterministic.rs` | `113-118,225-249` | The adapter rereads raw.path to obtain normalized source text and does not compare those bytes with raw_hash. |
| persistence_sink | `crates/kcs-cli/src/main.rs` | `9364-9388` | Normalized units and manifest derived from the later read are persisted under the earlier raw_hash. |

## Scope and actor

### Context

The affected deterministic normalization and persistence path is a real product workflow. Impact is not self-only: untrusted content becomes trusted archive/search evidence under a different content identity, although it remains confined to one selected scope in the validated trace.

### In scope

Yes.

### Exposure and identity

Local operator-invoked CLI only, with no listener or public ingress. The relevant surface is a selected root containing mutable lower-trust direct-child content.

The pipeline runs with the invoking OS user's access to the selected scope and authoritative .kcs store; no separate service identity is involved.

### Boundary crossed

Verified: version B crosses from an untrusted mutable pathname into the authoritative normalized/search/evidence store while being labeled with version A's raw identity.

### Authorization scope

internal-only

## Preconditions and attacker control

### Assumptions

- A lower-trust contributor has concurrent rename/write authority in the selected root.
- The operator performs ordinary deterministic indexing.
- The contributor wins the post-hash/pre-adapter interval.

### Preconditions

- Concurrent selected-root write/rename access.
- Operator indexing of the targeted file.
- Favorable scheduling after the caller hash comparison and before the adapter read.

### Attacker control

yes — the contributor controls version B and the replacement timing; the resulting stored identity remains chosen by the earlier benign version A.

### Vector

none

## Attack path

- A lower-trust selected-scope contributor leaves text/code version A stable while run_index_pipeline reads it and verifies H(A) against the scan identity at crates/kcs-cli/src/main.rs:9072-9103.
- After that verified read, the contributor replaces the mutable pathname with version B before deterministic markdownization.
- The deterministic adapter reopens the path at crates/kcs-adapter/src/deterministic.rs:225-241, derives normalized text from B, and never rebinds it to request.raw.raw_hash.
- KCS persists B-derived normalized/searchable units under H(A) at crates/kcs-cli/src/main.rs:9364-9388, poisoning one scope's provenance and evidence state.

## Impact and reach

- Category: CWE-367-style pathname TOCTOU causing content/provenance identity misbinding
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

data

### Target reach

One file's normalized units, chunks, search results, and evidence provenance within one selected scope.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- scan/current-buffer raw-hash comparison
- response shape validation
- content-addressed raw/prepared persistence
- operator re-index recovery

### Mitigations

- Changes before the caller's current-buffer hash comparison are detected and skipped.
- Stable, non-mutating files produce consistent raw, prepared, and normalized identities.
- The validated consequence is scope-local provenance corruption, not an outside-file overwrite or required network send.
- Re-indexing stable content can repair derived state.

### Counterevidence

- The pre-normalization hash comparison closes replacements that happen before its read.
- No live controlled interleaving established exploit reliability.
- Network egress is optional and was not needed or proven for this candidate; the direct impact is recoverable, scope-local integrity loss.

### Blind spots or proof gap

- Scheduler/filesystem race reliability is unmeasured.
- No downstream consumer reliance was demonstrated beyond persistence into searchable/evidence state.

## Final decision

The explicit untrusted-content-to-authoritative-provenance boundary prevents internal-surface suppression, and the contributor need not control the private live store. The proved impact is material but bounded and recoverable within one scope, so impact is medium. The unresolved local race and operator indexing precondition make likelihood medium. The matrix mechanically maps medium impact plus medium likelihood to Low/P3.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
