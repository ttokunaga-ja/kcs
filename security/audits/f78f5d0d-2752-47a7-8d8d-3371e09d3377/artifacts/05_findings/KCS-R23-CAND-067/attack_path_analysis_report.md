# Attack-path analysis: Persisted OCR tasks bypass current ignore authorization

- Candidate: `KCS-R23-CAND-067`
- Ledger row: `KCS-R23-CAND-067`
- Instance key: `KCS-R23-CAND-067`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| scan_authorization | `crates/kcs-pipeline/src/scan.rs` | `56-87,90-160,178-200` | A fresh scan loads ignore policy and marks candidate eligibility. |
| normal_task_source | `crates/kcs-cli/src/main.rs` | `10015-10039,10179-10213` | An allowed OCR candidate is normally persisted as an online placeholder task. |
| persisted_task_loader | `crates/kcs-pipeline/src/task.rs` | `41-75,129-186` | Tasks retain path/hash/state but no scan decision or ignore-policy binding; the loader checks only shape, locality, and hash syntax. |
| missing_current_authorization | `crates/kcs-cli/src/main.rs` | `6050-6067,6533-6573` | Selection and preconditions check secrets/hash/size/media but not current ignore policy or scan membership. |
| ocr_sink | `crates/kcs-adapter/src/mistral_ocr.rs` | `112-138` | The production client reads and posts the task path's document bytes with authentication. |

## Scope and actor

### Context

The path crosses a current local exclusion/authorization boundary into an external service. Persisted task state is incorrectly treated as sufficient authority after current scan policy has removed the path from eligibility.

### In scope

Yes.

### Exposure and identity

Operator- or automation-mediated local batch workflow followed by an authenticated outbound OCR request; KCS has no inbound listener.

The KCS OS user and configured adapter credential perform the send. A local content/shared-scope contributor can influence files and ignore policy, and calling automation can invoke recovery, but neither should inherit stale authorization to disclose excluded bytes.

### Boundary crossed

Yes.

### Authorization scope

local operator/automation recovery path with prior adapter authorization but revoked current scan membership

## Preconditions and attacker control

### Assumptions

- An eligible online OCR task was created before the ignore-policy change, or an equivalent task came from an adopted shared store.
- The document bytes remain unchanged while only current ignore policy changes.
- The operator retains valid credentials, persistent network approval, available budget, and later invokes a batch recovery command.
- The document is locally preparable for the concrete OCR path, such as a text-layer PDF enhancement task.

### Preconditions

- A prior allowed task must remain recoverable after its path becomes ignored.
- Document bytes must remain identical so the raw-hash recheck passes.
- The path must pass current filename-secret, media, and size checks.
- The operator must have approved the adapter and later run batch recovery with credentials and budget available.

### Attacker control

plausible: an in-scope local content or shared-scope contributor can influence the file and ignore-policy state, and a partially trusted automation can invoke batch; the operator still controls credentials and the configured destination

### Vector

none

## Attack path

- A document is legitimately eligible for OCR and KCS persists a pending or paused online markdownize task for its current bytes.
- The operator or a lower-trust scope contributor changes .kcsignore or the effective scope ignore rules so that a fresh scan excludes the unchanged document.
- The operator or calling automation later invokes batch resume or retry; the command consumes persisted tasks without building a current scan preview.
- Task selection and the send precondition recheck status, filename-secret class, direct-child path, raw hash, size, media, network approval, budget, and credentials, but never current ignore membership.
- The unchanged now-excluded document is read and sent in an authenticated request to the configured external OCR adapter.

## Impact and reach

- Category: stale authorization and excluded-document egress
- Impact: **high**
- Likelihood: **medium**

### Impact surface

confidentiality of an excluded user-readable document and correctness of durable authorization state

### Target reach

one unchanged OCR-eligible document per stale task, repeatable across eligible tasks in the scope

### Secret references

- The configured OCR credential authenticates the request but is not disclosed by this defect.
- The excluded document can contain confidential content not recognized by filename-based secret classification.

## Controls and counterevidence

### Existing controls

- Fresh indexing loads .kcsignore and effective scope ignore rules before enqueue.
- Persisted TaskDescriptor stores path, hash, and lifecycle state but no current scan-membership or ignore-policy binding.
- Batch recovery and send-time classification omit build_scan_preview and ignored_by_rules while preserving other send controls.

### Mitigations

- Direct-child locality, exact current raw hash, size, media routing, persistent network approval, credential presence, budget, and filename-based secret classification are rechecked.
- Changing the document bytes retires the stale task.
- Known secret-looking names remain held absent separate secret-send approval.
- A fresh ignored file does not create a task; prior eligible durable state is required.

### Counterevidence

- The document must previously have been allowed and enqueued; ignore rules do not create tasks for fresh excluded files.
- The user explicitly approved the configured external adapter and must invoke a later recovery command.
- Current hash, direct-child, size, media, secret-name, budget, and credential controls all remain effective.
- No runtime adapter capture was made, although the normal task source through authenticated sink trace is complete.

### Blind spots or proof gap

- The prevalence of long-lived OCR tasks across ignore-policy changes is not measured.
- The V10 proof does not quantify whether particular external providers retain or train on the transmitted document.

## Final decision

The path reaches a meaningful confidentiality boundary from a normal stale-task workflow and an in-scope lower-trust scope/automation source, so it is reportable. Prior enqueue, unchanged bytes, explicit batch use, existing adapter consent, and the remaining send controls materially constrain likelihood. High impact with Medium likelihood maps mechanically to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
