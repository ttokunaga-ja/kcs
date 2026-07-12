# Attack-path analysis: recursive star matching has exponential backtracking

- Candidate: `KCS-R23-CAND-017`
- Ledger row: `KCS-R23-CAND-017`
- Instance key: `KCS-R23-CAND-017`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| ignore source | `crates/kcs-pipeline/src/scan.rs` | `178-200` |  |
| per-candidate dispatch | `crates/kcs-pipeline/src/scan.rs` | `90-159,315-327` |  |
| recursive matcher | `crates/kcs-pipeline/src/scan.rs` | `383-415` |  |
| command reachability | `crates/kcs-cli/src/main.rs` | `452-472,558-580` |  |

## Scope and actor

### Context

Ordinary local scope adoption; the recurrence is 2^(n+2)-3 for the validated pattern family and requires no private-store access.

### In scope

Yes.

### Exposure and identity

Untrusted local scope content is synchronously parsed by snapshot and index; KCS has no daemon or remote listener.

A local content contributor or shared/synced scope contributor controls .kcsignore and candidate names; the operator runs KCS.

### Boundary crossed

Yes.

### Authorization scope

internal-only: an untrusted scope contributor can trigger the issue when the operator processes the scope.

## Preconditions and attacker control

### Assumptions

- The operator opens or indexes a supplied/shared scope containing the crafted .kcsignore.
- At least one candidate pathname reaches the adversarial failing match.

### Preconditions

- A crafted overlapping-star ignore rule.
- A candidate name that drives the failing backtracking case.
- An ordinary snapshot or index invocation.

### Attacker control

The lower-trust contributor fully controls the ignore rule and candidate path needed to trigger deterministic exponential work.

### Vector

none

## Attack path

- A lower-trust scope contributor supplies a crafted .kcsignore pattern with overlapping star branches.
- Snapshot or index accepts the rule without length or complexity limits and evaluates it for candidate paths.
- The recursive matcher explores both zero-consumption and input-consumption states without memoization.
- Matching work grows exponentially and blocks the synchronous CLI operation before useful indexing or snapshot work completes.

## Impact and reach

- Category: algorithmic complexity denial of service
- Impact: **medium**
- Likelihood: **high**

### Impact surface

runtime: CPU exhaustion and availability of snapshot/index for the selected scope

### Target reach

Every snapshot or index evaluation of matching candidates in the crafted scope.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- Rule parsing drops comments and empty lines but imposes no complexity bound.
- The recursive star matcher lacks memoization or a work budget.
- Synchronous scan preview makes the sink reachable from normal commands.

### Mitigations

- Simple glob patterns remain fast.
- The impact is confined to the selected local scope and command.
- The operator can remove the rule and retry.

### Counterevidence

- Simple patterns are fast.
- There is no daemon, listener, or cross-scope persistence.
- The operator can remove the local rule and recover.

### Blind spots or proof gap

- The bounded probe stopped at n=18 and did not intentionally exhaust the host; larger-case wall time is inferred from the proven recurrence.

## Final decision

A realistic lower-trust contributor directly controls the crafted rule, and normal snapshot/index deterministically reaches the exponential matcher. The local, removable scope wedge bounds impact to medium, while deterministic reachability supports high likelihood. The matrix yields medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
