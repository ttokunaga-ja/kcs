# Attack-path analysis: Persisted task output_ref can escape the scope

- Candidate: `KCS-R23-CAND-047`
- Ledger row: `KCS-R23-CAND-047`
- Instance key: `KCS-R23-CAND-047:task-output-ref-cross-scope`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.88)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoint_and_partial_control | `crates/kcs-pipeline/src/task.rs` | `129-184` |  |
| root_control_and_read_sink | `crates/kcs-cli/src/main.rs` | `9685-9713` |  |
| reuse_sink | `crates/kcs-cli/src/main.rs` | `9863-9885` |  |
| persistence_sink | `crates/kcs-cli/src/main.rs` | `6977-6995` |  |

## Scope and actor

### Context

This is a real archive and incremental-processing confused-deputy path. Lower-trust persisted task state makes KCS exercise the victim's filesystem authority across scope boundaries and persist foreign text under current-scope provenance.

### In scope

yes; copied stores, cross-scope reads, and provenance binding are covered by I1 and I7

### Exposure and identity

not public; deterministic local reachability through processing of an adopted store

KCS reads as the victim OS user. The supplied-store contributor controls output_ref without requiring arbitrary write access to the victim's already-private live store.

### Boundary crossed

yes: supplied task state selects another readable scope and its normalized text is reused under the current scope's identity

### Authorization scope

internal-only adopted/shared-store workflow

## Preconditions and attacker control

### Assumptions

- The victim adopts a copied, shared, synced, or preseeded store.
- The contributor knows or can arrange a readable compatible normalized-instance path.
- A matching incremental or retry workflow is invoked and the profile check passes.

### Preconditions

- Adoption of lower-trust persisted task state
- A known, readable, parseable normalized instance outside the current scope
- Compatible profile/task metadata and a victim incremental or retry invocation

### Attacker control

yes over the supplied task record and output_ref; conditional over knowledge or arrangement of the external normalized instance

### Vector

none

## Attack path

- A lower-trust copied or shared-store contributor seeds tasks.jsonl with valid input fields but an absolute or traversing output_ref naming another operator-readable normalized instance.
- TaskStore::all validates input_path and hash fields but not output_ref at crates/kcs-pipeline/src/task.rs:129-184.
- A Done or Partial online task is selected at crates/kcs-cli/src/main.rs:7008-7026, and load_previous_instance reads the foreign manifest and units directly at crates/kcs-cli/src/main.rs:9685-9713.
- After a profile-compatibility check, unchanged foreign markdown is relabeled under the current raw identity at crates/kcs-cli/src/main.rs:9863-9885 and persisted into the current scope at lines 6977-6995.

## Impact and reach

- Category: path traversal, cross-scope normalized-data read, and provenance poisoning
- Impact: **high**
- Likelihood: **medium**

### Impact surface

cross-scope data confidentiality and archive/search provenance integrity

### Target reach

one current scope and one compatible victim-readable normalized instance per malicious task reference

### Secret references

- The foreign normalized markdown can contain sensitive document text; no credential file is directly selected.

## Controls and counterevidence

### Existing controls

- Require output_ref to be a canonical contained normalized-instance reference.
- Rebind loaded manifest and units to the current scope, raw hash, profile, and generation before reuse.
- Reject absolute and parent-bearing persisted references before filesystem access.

### Mitigations

- TaskStore validates input filenames and hash-shaped fields.
- Manifest and unit objects must deserialize successfully.
- Online incremental reuse compares tool profile hashes.
- Unreadable or malformed instances degrade to no previous instance.

### Counterevidence

- Fresh .kcs stores are intended owner-only, so ordinary direct-child contributors cannot normally rewrite a healthy live ledger.
- The target must be valid KCS normalized state and satisfy profile and workflow prerequisites.
- Existing adapter/network authorization remains required for the online incremental path and does not itself authorize output_ref.
- Automatic remote exfiltration of previous markdown was not established; the direct effects are cross-scope read and durable contamination.

### Blind spots or proof gap

- No end-to-end two-root runtime regression was retained.
- Target-path predictability and shared-store readback are deployment-dependent.
- CAND-049 and CAND-061 cover adjacent inner-reference and semantic-tuple gaps.

## Final decision

Hard suppression does not apply because a lower-trust supplied/shared-store actor is expressly in scope and can redirect the victim's broader filesystem authority. Cross-scope normalized-text read and durable provenance substitution are High impact; adoption, path knowledge, compatibility, and victim-workflow prerequisites make likelihood Medium. The matrix yields Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
