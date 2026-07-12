# Attack-path analysis: Oversized task JSONL records allocate before validation

- Candidate: `KCS-R23-CAND-050`
- Ledger row: `KCS-R23-CAND-050`
- Instance key: `KCS-R23-CAND-050`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high (0.99)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| unbounded line and serde | `crates/kcs-pipeline/src/task.rs` | `129-150` |  |
| late semantic checks | `crates/kcs-pipeline/src/task.rs` | `151-184` |  |
| map retention | `crates/kcs-pipeline/src/task.rs` | `140-186` |  |
| status consumer | `crates/kcs-cli/src/main.rs` | `435-450` |  |

## Scope and actor

### Context

Copied and preseeded-store adoption is explicitly in scope and distinct from equivalent same-user mutation of a private live store. The impact is local, persistent task-command availability loss.

### In scope

yes; persisted-task boundedness and availability are covered by I4, I6, and I12

### Exposure and identity

not public; local adopted-store workflow with no listener or network entry point

Parsing runs as the KCS user; the lower-trust contributor needs only pre-adoption control of supplied state, not access to the victim's private live store.

### Boundary crossed

yes: untrusted adopted task state deterministically consumes victim process resources and wedges trusted recovery/status workflows

### Authorization scope

internal-only adopted-store workflow

## Preconditions and attacker control

### Assumptions

- The supplied scope retains contributor-controlled .kcs task state.
- The JSON is syntactically valid and large enough relative to victim resources.
- The operator invokes an ordinary task-reading command.

### Preconditions

- Adoption of lower-trust copied or preseeded task state
- A large valid tasks.jsonl using unique task IDs
- Invocation of a task-reading command

### Attacker control

yes over pre-adoption line size, strings, collection cardinalities, record count, and task IDs

### Vector

none

## Attack path

- A lower-trust contributor supplies an adopted or preseeded scope whose .kcs/tasks.jsonl contains one huge valid record or many uniquely keyed records.
- The operator invokes status, index, batch retry/resume, or another TaskStore::all consumer.
- BufRead::lines allocates the complete line and serde allocates all strings and changed_unit_keys/unit_keys values before path/hash validation at crates/kcs-pipeline/src/task.rs:140-183.
- Each unique task is retained in a BTreeMap through lines 184-186, consuming memory and CPU and repeatedly wedging task-reading commands until the supplied state is repaired.

## Impact and reach

- Category: unbounded persisted-state parsing and retention causing local denial of service
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

runtime memory/CPU and task/status/recovery availability

### Target reach

one adopted scope and its task-consuming commands; restart repeats the failure until state repair

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- Enforce total-file and per-line byte budgets before String growth.
- Bound record counts, string lengths, and vector cardinalities during deserialization.
- Return an actionable bounded corruption/recovery error for over-limit state.

### Mitigations

- Fresh .kcs stores are owner-only.
- Malformed JSON fails closed.
- Paths and hashes are semantically checked after deserialization.
- Duplicate task IDs replace earlier map entries.

### Counterevidence

- Unrestricted same-user live-store tampering is excluded and would provide equivalent authority.
- Normal KCS writers emit ordinary-sized records.
- The bounded validation proved full parsing and retention but intentionally did not force OOM.
- Resource use remains bounded by supplied file size and manual removal restores service.

### Blind spots or proof gap

- Practical RSS and failure thresholds were not measured.
- The prevalence and provenance UX of copied-store adoption are unknown.

## Final decision

Hard suppression does not apply because a lower-trust pre-adoption store contributor is explicitly modeled. Persistent but one-scope and recoverable availability loss is Medium impact; copied-store adoption and a sufficiently large valid payload constrain likelihood to Medium. The matrix yields Low/P3.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
