# Attack-path analysis: incremental unit mapping allocates a quadratic LCS matrix

- Candidate: `KCS-R23-CAND-007`
- Ledger row: `KCS-R23-CAND-007`
- Instance key: `KCS-R23-CAND-007`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| mapping entrypoint | `crates/kcs-pipeline/src/prepare.rs` | `208-253` |  |
| quadratic LCS | `crates/kcs-pipeline/src/prepare.rs` | `387-416` |  |
| index reachability | `crates/kcs-cli/src/main.rs` | `9219-9235` |  |

## Scope and actor

### Context

The lower-trust revision source is in scope and the full matrix is allocated before any similarity shortcut can help. Derived unit amplification can make the required cardinality practical under existing byte limits.

### In scope

Yes.

### Exposure and identity

Operator-mediated local revision/index workflow; no network or listener is required.

The contributor controls document revisions; the KCS user bears the allocation and indexing failure.

### Boundary crossed

Yes.

### Authorization scope

untrusted local document revisions processed by an operator command

## Preconditions and attacker control

### Assumptions

- A local content contributor can control successive revisions in a scope the operator reindexes.
- Both old and new prepared representations contain sufficiently many units.
- The incremental mapping path is reached.

### Preconditions

- Two indexed revisions must each generate a large unit list.
- The operator must run incremental index or reindex.
- Unit cardinality must be high enough to exceed available memory or acceptable work.

### Attacker control

yes: an in-scope local content contributor controls both revision contents and therefore both matrix dimensions

### Vector

none

## Attack path

- A lower-trust contributor supplies an indexed document revision with many prepared units and later supplies another large revision.
- Incremental indexing passes the old and new unit lists to map_units.
- The LCS implementation allocates and fills an (m+1) by (n+1) usize matrix without a unit-count or work budget.
- The allocation reaches hundreds of megabytes or gigabytes at feasible derived unit counts and can repeatedly terminate or wedge indexing while the crafted revisions remain.

## Impact and reach

- Category: quadratic algorithmic complexity and persistent local denial of service
- Impact: **high**
- Likelihood: **medium**

### Impact surface

memory/CPU availability and incremental indexing liveness

### Target reach

the KCS process handling the crafted scope/revisions

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- Existing raw-byte limits.
- Fingerprint-based mapping semantics.
- Normal scope and direct-child controls.

### Mitigations

- Small ordinary documents complete quickly.
- Raw input size is capped elsewhere.
- Fingerprint matches may reduce later work, but not matrix allocation.

### Counterevidence

- The path requires two large revisions and incremental mapping rather than a single ordinary small file.
- Large failure cases were computed rather than allocated.
- No confidentiality, authorization, or cross-scope integrity effect is shown.

### Blind spots or proof gap

- The minimum document size and unit-generation pattern needed for a reliable host-specific denial are not fully measured.
- Interaction with operating-system memory limits is environment-dependent.

## Final decision

A realistic lower-trust revision source can drive both dimensions of an unbounded quadratic matrix and persistently deny indexing. High availability impact with the multi-revision/operator/cardinality prerequisites gives Medium likelihood, mapping to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
