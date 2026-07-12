# Attack-path analysis: secret-hold cycles erase terminal embedding failure state

- Candidate: `KCS-R23-CAND-001`
- Ledger row: `KCS-R23-CAND-001`
- Instance key: `KCS-R23-CAND-001`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| demotion selector | `crates/kcs-cli/src/main.rs` | `8221-8231` |  |
| destructive hold | `crates/kcs-cli/src/main.rs` | `8295-8325` |  |
| fresh unhold | `crates/kcs-cli/src/main.rs` | `8360-8368,8463-8484` |  |
| retry contract | `crates/kcs-pipeline/src/task.rs` | `320-378` |  |
| send sink | `crates/kcs-cli/src/main.rs` | `7340-7345,7727-7768` |  |

## Scope and actor

### Context

KCS is a local CLI with no listener. The relevant boundary is destructive task-state reauthorization: lower-trust file revisions can combine with ordinary operator indexing to revive work that the retry contract made terminal.

### In scope

Yes.

### Exposure and identity

Operator-mediated local filesystem workflow; the eventual adapter call is outbound only.

The KCS OS user performs the call with the already configured adapter identity and budget authority; the lower-trust contributor controls file naming/revisions, not credentials or commands.

### Boundary crossed

Yes.

### Authorization scope

local operator-mediated workflow with prior online-adapter authorization

## Preconditions and attacker control

### Assumptions

- A local content contributor can control names or revisions in a scope the operator continues to index.
- An online embedding adapter was already approved and configured.
- A terminal or retry-exhausted task exists before the secret/non-secret classification cycle.

### Preconditions

- A failed embedding task must already exist.
- The same content must cycle into and out of Tier-B secret classification.
- The operator must run the relevant index/enrichment cycles with online processing enabled.

### Attacker control

plausible: an in-scope local content contributor can control the name and revision sequence, while operator invocations remain required

### Vector

none

## Attack path

- A lower-trust scope revision leaves an embedding task in a terminal or retry-exhausted Failed state.
- The file name or classification changes to Tier B and a later index cycle demotes the failed task to a secrets_tier_b_hold state, overwriting its reason, attempts, and retry timing.
- A subsequent non-secret revision is indexed and unhold converts the row to fresh Pending work with attempts reset to zero.
- Normal enrichment reserves budget and invokes the configured embedding adapter again despite the original non-retryable or exhausted failure.

## Impact and reach

- Category: task lifecycle, retry-policy bypass, and bounded budget/network re-execution
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

task-state integrity, outbound adapter execution, and bounded cost

### Target reach

one affected embedding task at a time within the indexed scope

### Secret references

- The configured adapter credential may be used for the revived request, but the evidence shows no credential disclosure or destination change.

## Controls and counterevidence

### Existing controls

- Typed retry policy marks AuthError, InvalidInput, and ContractViolation non-retryable and caps NetworkError retries.
- The hold selector excludes Done and retired non-live tasks, but not terminal or exhausted failures.
- Pre-send approval and budget enforcement remain present.

### Mitigations

- Done tasks and retired non-live tasks are excluded from hold demotion.
- Adapter approval, tool, credential, and budget checks still apply to the revived send.
- The issue does not grant a new destination or credential.

### Counterevidence

- The reproduced sequence required content/name reclassification and repeated operator indexing.
- Done and retired-non-live tasks do not enter the destructive transition.
- Existing approval and budget controls bound the revived execution.

### Blind spots or proof gap

- The receipts do not establish how frequently attacker-controlled shared/synced revisions produce the full lifecycle.
- Actual provider billing for the revived failure mode is adapter-dependent.

## Final decision

The lower-trust file-revision path is realistic enough to avoid hard suppression, and the revived send/cost plus terminal-state loss is material but bounded. Medium impact with medium likelihood maps mechanically to Low/P3.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
