# Attack-path analysis: CAS reads allocate attacker-sized objects before verification

- Candidate: `KCS-R23-CAND-046`
- Ledger row: `KCS-R23-CAND-046`
- Instance key: `KCS-R23-CAND-046:cas-whole-object-read-before-verification`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high (0.96)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| whole_object_read_before_digest | `crates/kcs-core/src/cas.rs` | `78-100` |  |
| raw_inspect_sink | `crates/kcs-core/src/scope.rs` | `623-637` |  |
| commit_tree_consumers | `crates/kcs-core/src/scope.rs` | `742-755,848-865` |  |
| cli_inspect_entrypoint | `crates/kcs-cli/src/main.rs` | `513-530` |  |

## Scope and actor

### Context

Copied, shared, and preseeded stores are explicitly untrusted at adoption. The issue crosses that supplied-state boundary into the KCS process's resources, but remains a local, scope-bounded availability defect.

### In scope

yes; adopted-store parsing and CAS boundedness are covered by I6, I7, and I12

### Exposure and identity

not public; local filesystem artifact consumed through operator-invoked CLI commands

KCS reads as the operator's OS user; the lower-trust contributor needs pre-adoption control of the supplied store, not write access to the victim's private live store.

### Boundary crossed

yes: untrusted adopted CAS state deterministically controls victim allocation and hashing, though no confidentiality or privilege boundary is crossed

### Authorization scope

internal-only adopted-store workflow

## Preconditions and attacker control

### Assumptions

- The victim adopts the supplied store and invokes a command that selects the object.
- The contributor can provide a valid SHA-256 name or a supplied ref for the oversized object.
- The object is large enough relative to victim memory and I/O capacity to cause substantial disruption.

### Preconditions

- Adoption of a lower-trust copied or preseeded store
- A hash-consistent oversized CAS object
- A supplied hash/ref and an inspect, HEAD, tree, or related consuming command

### Attacker control

yes over the supplied object bytes, size, hash, and store refs; no control over the victim process identity is required

### Vector

none

## Attack path

- A lower-trust contributor supplies an adopted or preseeded .kcs store containing an attacker-sized, hash-consistent CAS object and a hash or ref that selects it.
- The operator invokes inspect or a HEAD/tree consumer against that supplied store.
- ObjectStore::read_by_hash validates hash syntax but calls fs::read at crates/kcs-core/src/cas.rs:78-100 before digest, kind, JSON-shape, or command-specific size validation.
- The victim process allocates, reads, and hashes all N bytes; raw inspect at crates/kcs-core/src/scope.rs:623-637 retains the full object merely to report its size, while poisoned refs can repeat the primitive in routine repository commands.

## Impact and reach

- Category: unbounded CAS object allocation and local denial of service
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

runtime memory, I/O, CPU, and repository-command availability

### Target reach

one adopted scope and each command that selects the oversized object or poisoned ref

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- Stream digest verification with a bounded buffer.
- Apply per-kind byte and cardinality ceilings before allocation.
- Implement metadata-only raw inspection without retaining complete object bytes.

### Mitigations

- Hash syntax and fixed fan-out paths are checked before lookup.
- SHA-256 equality is verified after the read.
- Kind and JSON validation protect integrity after allocation.
- Fresh stores are created owner-only.

### Counterevidence

- The contributor must supply a hash-consistent object, so arbitrary false-hash garbage is rejected.
- Resource use is approximately linear in bytes already present in the supplied store rather than a small-input amplification.
- Direct same-user mutation of an already private live store is out of scope.
- The bounded control proved full allocation but intentionally did not measure peak RSS or force OOM.

### Blind spots or proof gap

- Practical exhaustion thresholds and packaging of very large supplied stores were not measured.
- No end-to-end poisoned-HEAD stress case was run.

## Final decision

Hard suppression does not apply because the threat model recognizes a lower-trust supplied-store contributor distinct from private-live-store authority. The substantial but local and recoverable availability impact is Medium; adoption, object size, and command-selection prerequisites constrain likelihood to Medium. The matrix yields Low/P3.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
