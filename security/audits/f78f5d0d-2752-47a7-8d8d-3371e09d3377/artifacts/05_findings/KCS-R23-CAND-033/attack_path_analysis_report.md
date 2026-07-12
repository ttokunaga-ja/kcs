# Attack-path analysis: Deferred OCR tasks read replacement files before enforcing the cap

- Candidate: `KCS-R23-CAND-033`
- Ledger row: `KCS-R23-CAND-033`
- Instance key: `KCS-R23-CAND-033:deferred-ocr-precap-read`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoint | `crates/kcs-cli/src/main.rs` | `5974-6081` |  |
| root_control_and_sink | `crates/kcs-cli/src/main.rs` | `6533-6551` |  |
| cap_definition | `crates/kcs-cli/src/main.rs` | `4425-4445` |  |

## Scope and actor

### Context

This is a deterministic lifecycle/resource path in the shipped CLI. The attack crosses from mutable scope content into process memory before a known cap, but the oversized branch retires before network or billing effects.

### In scope

Yes.

### Exposure and identity

No listener or public ingress. The relevant surface is a deferred local OCR task whose selected-scope input remains writable by an in-scope contributor.

The invoking OS user owns the KCS process, pending task state, memory, and I/O resources; no credential is attached because the oversized branch stops before online execution.

### Boundary crossed

Verified: attacker-controlled replacement-file size crosses the deferred-task input boundary into whole-file allocation before the cap; no external network boundary is crossed for the oversized case.

### Authorization scope

internal-only

## Preconditions and attacker control

### Assumptions

- An eligible Pending OCR task exists for a selected-scope path.
- A lower-trust contributor can replace that path between enqueue and a later resume/retry.
- The operator invokes the deferred-task processing command.

### Preconditions

- A queued Pending OCR task for a formerly acceptable file.
- Selected-root write/rename authority between enqueue and resume/retry.
- Operator execution of deferred task processing.

### Attacker control

yes — the contributor controls the replacement file and its logical size; after resume the vulnerable allocation order is deterministic.

### Vector

none

## Attack path

- A legitimate small OCR file first produces a persisted Pending online-markdownize task.
- Before the operator resumes or retries the task, a lower-trust selected-scope contributor replaces the path with a much larger or sparse regular file; no same-call race is needed.
- classify_online_markdownize_precondition reads the entire current file at crates/kcs-cli/src/main.rs:6537-6541 before comparing its length to effective_max_input_bytes at 6542-6551.
- KCS incurs O(n) allocation and I/O before retiring the task; pre-charge ordering prevents the oversized replacement from reaching the adapter or budget reservation.

## Impact and reach

- Category: CWE-400 uncontrolled resource consumption in deferred task precondition checking
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

runtime

### Target reach

One deferred task execution and local process/host resources; no provider or cross-scope data effect is established.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- initial enqueue-time input cap
- post-read hash and size retirement
- pre-charge/pre-send ordering
- task lifecycle eligibility checks

### Mitigations

- Initial indexing enforces the cap before enqueue for the original file.
- Hash mismatch and oversize checks retire the changed task.
- Classification occurs before budget reservation and online execution, preventing a paid send.
- The operator can remove the replacement and recreate/retry work.

### Counterevidence

- The original file had to pass the input cap before the task existed.
- The changed task is retired before charge or network send.
- Peak allocator behavior was not stress-tested, and the operator must later resume or retry the task.

### Blind spots or proof gap

- Actual memory-pressure severity depends on host resources and allocator behavior.
- The frequency of long-lived deferred tasks in real deployments is not established.

## Final decision

A lower-trust mutable scope file can deterministically trigger substantial pre-cap work in a real deferred-task workflow, so the internal surface does not mandate suppression. Impact is medium because the availability loss may be substantial but remains local/recoverable and stops before billing or egress. Likelihood is medium due to the required prior task and later operator resume/retry. The matrix yields Low/P3.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
