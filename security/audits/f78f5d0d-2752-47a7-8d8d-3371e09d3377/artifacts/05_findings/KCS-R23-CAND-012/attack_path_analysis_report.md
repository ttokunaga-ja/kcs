# Attack-path analysis: Content-twin reuse leaves completed budget-paused tasks falsely pending

- Candidate: `KCS-R23-CAND-012`
- Ledger row: `KCS-R23-CAND-012`
- Instance key: `KCS-R23-CAND-012`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| content_reuse_projection | `crates/kcs-index/src/embedding_store.rs` | `149-184` | Rebuild links non-secret-held content-hash twins. |
| held_only_filter | `crates/kcs-cli/src/main.rs` | `3008-3027,3655-3658` | Only secrets holds are excluded from content-vector rebuild. |
| completion_detection | `crates/kcs-cli/src/main.rs` | `7911-7917,8006-8013` | The budget-paused live chunk has a current vector and is no longer pending. |
| root_control | `crates/kcs-cli/src/main.rs` | `8088-8132` | A reason-blind Paused guard skips the Done transition. |
| status_sink | `crates/kcs-cli/src/main.rs` | `2417-2506` | The stale row remains pending and sets budget_paused. |

## Scope and actor

### Context

Normal CLI lifecycle involving budget enforcement, content reuse, reconciliation, and status.

### In scope

Yes.

### Exposure and identity

Untrusted local scope content can influence trusted task and budget-status state under ordinary operator configuration.

A local content contributor supplies the documents; the operator controls budget configuration and later cap recovery.

### Boundary crossed

Yes.

### Authorization scope

internal-only: no authorization, secret-send, or monetary-cap bypass occurs.

## Preconditions and attacker control

### Assumptions

- An embedding profile and hard budget cap are configured.
- A genuine budget pause occurs before the twin is embedded.
- A lower-trust contributor can supply appropriately ordered content twins.
- The operator later raises or otherwise clears the cap.

### Preconditions

- An earlier hard budget pause.
- A byte-distinct chunk with identical normalized text.
- Later materialization of a current-profile vector.
- Ordinary re-indexing.

### Attacker control

A contributor controls document bytes and ordering, but does not control the configured cap or the operator's later cap change.

### Vector

none

## Attack path

- A contributor-controlled chunk reaches a configured hard budget cap and becomes Paused(budget_exceeded).
- After budget availability or configuration changes, a byte-distinct twin with identical normalized text obtains an embedding.
- Rebuild links the paused chunk to that embedding by text_hash.
- Completion detection recognizes the chunk as materially embedded.
- The reason-blind Paused guard nevertheless refuses to transition it to Done.
- Search remains functional, but automation-facing status persistently reports pending enrichment and budget_paused.

## Impact and reach

- Category: task convergence and budget-status integrity
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

runtime: automation-facing index status, budget-paused telemetry, and task convergence

### Target reach

Budget-paused chunks completed through same-profile content-twin reuse in one scope.

### Secret references

- secrets_tier_b_hold is the necessary negative control that must remain Paused

## Controls and counterevidence

### Existing controls

- The hard budget gate correctly pauses work.
- Current-vector completion detection recognizes the materialized embedding.
- A reason-blind Paused guard is the broken convergence control.

### Mitigations

- Budget enforcement correctly creates the initial pause.
- Content reuse correctly materializes the shared vector.
- Explicit batch resume --override-budget repairs the record without another adapter call.

### Counterevidence

- Both documents remain searchable and search data is intact.
- No confidentiality or extra-spend effect was observed.
- Explicit override heals the task without another adapter call.

### Blind spots or proof gap

- No downstream automation was shown taking a harmful action based on the false status.
- The lower-trust contributor cannot independently create the required cap-change lifecycle.

## Final decision

A plausible lower-trust content path exists, but it depends on a multi-stage operator budget lifecycle the contributor does not control. The false durable state can mislead automation, while intact search, no extra spend, and free explicit recovery materially constrain likelihood and consequence. Medium impact plus medium likelihood maps mechanically to low.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
