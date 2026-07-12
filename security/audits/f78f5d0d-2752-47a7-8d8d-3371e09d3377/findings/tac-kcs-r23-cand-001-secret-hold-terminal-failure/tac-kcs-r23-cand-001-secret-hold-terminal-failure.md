# Secret-hold cycles erase terminal embedding failure state

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` contains a
task-lifecycle bug in the local CLI embedding pipeline. When an embedding task
has already reached a terminal or retry-exhausted `Failed` state, an ordinary
secret-classification cycle can overwrite that terminal state with
`Paused(secrets_tier_b_hold)`. When the same content later becomes non-secret
again, KCS releases the hold as fresh `Pending` work with `attempts = 0`, so the
normal embedding path can reserve budget and invoke the configured embedding
adapter again.

The realistic actor is a lower-trust local content contributor who can affect
file names or revisions in a scope that an operator continues to index. The
operator still has to run KCS with online embedding already configured and
approved, so this does not create a new network destination, expose credentials,
or execute arbitrary commands. The security impact is bounded but real: terminal
retry policy is bypassed, operator-visible failure state is lost, and repeated
rename/index cycles can cause repeated outbound embedding attempts and cost or
cap consumption for work that KCS had already decided not to retry.

I reviewed the vulnerable revision directly and ran the included offline
state-machine PoC. I did not contact a live embedding provider, use real API
keys, or establish an exact release range or fixing commit. The final severity
for this finding is low/P3 because exploitation is operator-mediated and remains
bounded by existing adapter approval and budget controls.

## Background

KCS tracks online work in `TaskDescriptor` rows. For embeddings, the key fields
are `status`, `fallback_reason`, `attempts`, `next_retry_at`, and `output_ref`.
The retry contract in `crates/kcs-pipeline/src/task.rs` distinguishes transient
adapter failures from terminal ones. For example, network errors get five
attempts, rate limits are retryable, and `auth_error`, `invalid_input`,
`contract_violation`, and `budget_exceeded` are non-retryable:

```rust
// crates/kcs-pipeline/src/task.rs
RetryErrorKind::AuthError => RetryPolicy {
    error_kind,
    retryable: false,
    max_attempts: Some(0),
    backoff: "user_action".to_owned(),
    error_code: "KCS-E-BATCH-AUTH-001".to_owned(),
    paused: false,
},
RetryErrorKind::ContractViolation => RetryPolicy {
    error_kind,
    retryable: false,
    max_attempts: Some(0),
    backoff: "full_fallback_once".to_owned(),
    error_code: "KCS-E-ADAPTER-CONTRACT-001".to_owned(),
    paused: false,
},
```

The CLI also has a Tier-B secret hold. If a chunk belongs to a file whose live
path looks secret-like, and the scope has not approved `--send-secrets`, the
chunk is put into the `held` partition and `hold_secret_embedding_tasks()` marks
its embedding task as `Paused(secrets_tier_b_hold)`. While a task is actually in
that hold, `embeddable_task_state()` refuses to send it:

```rust
// crates/kcs-cli/src/main.rs
TaskStatus::Paused => match task.fallback_reason.as_deref() {
    Some("budget_exceeded") => override_budget,
    Some(SECRETS_TIER_B_HOLD) => false,
    _ => true,
},
TaskStatus::Failed => task_retry_due(task) && task_retry_allowed(task),
```

Those two systems are both reasonable in isolation. The retry policy should make
terminal failures sticky, and the secret hold should be a temporary
classification overlay. The bug appears where the overlay is implemented by
mutating the same task-row fields that also encode terminal retry state.

## Vulnerability Details

We first reach the vulnerable path through the embedding partition in
`crates/kcs-cli/src/main.rs`. KCS computes pending live chunks, splits them by
secret classification, and applies the hold before enqueueing or sending the
non-secret side:

```rust
let secrets_approved = secrets_send_approved(repo);
let (held, sendable): (Vec<EmbeddableChunk>, Vec<EmbeddableChunk>) =
    pending.into_iter().partition(|chunk| {
        !secrets_approved && classify_secret(&chunk.raw_path).is_some()
    });
hold_secret_embedding_tasks(&task_store, repo, &held, &now)?;
```

From there, the hold selector is too broad. It excludes tasks that are already
held, tasks that are `Done`, and tasks retired as `retired_non_live`. It does
not exclude `Failed` tasks that the retry policy has made permanent, nor failed
tasks whose finite attempt count is already exhausted:

```rust
// crates/kcs-cli/src/main.rs
let demotable = all_tasks
    .iter()
    .filter(|task| task.task_type == TaskType::Embedding)
    .filter(|task| {
        !already_held.contains(&task.output_ref)
            && !done.contains(&task.output_ref)
            && task.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE)
    })
    .map(|task| task.output_ref.clone())
    .collect::<BTreeSet<_>>();
```

If we carry a `Failed(contract_violation)` task through that selector, it lands
in `to_demote`. The mutation then overwrites the failure with secret-hold
metadata and clears the fields that enforce the terminal decision:

```rust
// crates/kcs-cli/src/main.rs
task.status = TaskStatus::Paused;
task.fallback_reason = Some(SECRETS_TIER_B_HOLD.to_owned());
task.input_path = current_path.clone();
task.attempts = 0;
task.next_retry_at = None;
task.heartbeat_at = None;
```

At this point the task is safe from immediate sending because
`embeddable_task_state()` treats `secrets_tier_b_hold` as not sendable. The
problem is that the original failure reason and attempt count are gone. When the
same content later appears only under a non-secret path, `enqueue_embedding_tasks()`
identifies the old hold as stale and releases it in place:

```rust
// crates/kcs-cli/src/main.rs
if !to_unhold.is_empty() {
    task_store
        .update_matching(|task| {
            if task.task_type == TaskType::Embedding
                && task.status == TaskStatus::Paused
                && task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD)
            {
                let Some(current_path) = to_unhold.get(&task.output_ref) else {
                    return false;
                };
                task.status = TaskStatus::Pending;
                task.fallback_reason = Some(reason.to_owned());
                task.input_path = current_path.clone();
                task.attempts = 0;
                task.next_retry_at = None;
                task.heartbeat_at = None;
                true
            } else {
                false
            }
        })
        .map_err(pipeline_to_kcs)?;
}
```

That is the state-integrity break. Before the classification cycle, the task was
`Failed(contract_violation, attempts = 1)` and `task_retry_allowed()` would never
allow it to run. After the cycle, the same `output_ref` is
`Pending(ready_for_online_adapter, attempts = 0)`. The next online pass treats it
as normal pending work:

```rust
let embeddable = filter_embeddable_by_task_state(&task_store, sendable, override_budget)?;
if embeddable.is_empty() {
    return Ok(ExecOutcome::default());
}
```

When the chunk is not satisfied by content-addressed vector reuse, the normal
send path reserves budget and calls the adopted embedding adapter:

```rust
let charge = if sent_chars == 0 {
    ChargeOutcome::Charged
} else {
    let estimate = BudgetEstimate {
        scope_id: scope_id.clone(),
        task_type: TaskType::Embedding,
        estimated_usd: estimate_embedding_cost(sent_chars),
        adapter_id: Some(profile.tool_id.clone()),
    };
    charge_cost_ledger_under_lock(
        &cost_ledger,
        cost_ledger_lock_path(),
        &budget_caps,
        &month,
        EMBEDDING_ADAPTER_KIND,
        &estimate,
        override_budget,
    )?
};
match send_embed_batch(&conn, execution, &profile, &plan.to_send) {
```

The retry policy was therefore not bypassed by a direct call into the adapter.
It was bypassed by temporarily reclassifying the task as a secret hold and then
letting the unhold path synthesize fresh pending state instead of restoring the
pre-hold failure state.

## Exploitability Analysis

The strongest route is an operator-mediated local workflow. We need a task that
has already failed terminally or exhausted a bounded retry policy. A
collaborator then causes the same content to be indexed under a Tier-B-looking
name, such as a name that `classify_secret()` treats as candidate-secret. On the
next index pass, KCS demotes the existing embedding row into
`secrets_tier_b_hold`. The collaborator then causes the content to be indexed
again under a non-secret name, and a later online pass releases the hold to
fresh `Pending` work.

That route gives us a repeat-send primitive, not a general code-execution
primitive. The adapter identity, destination, and budget authority still come
from the operator's existing KCS configuration. If no online embedding adapter
is configured, or if the operator never runs online processing, the revived task
does not leave the machine. If the content already has a reusable vector in the
content-addressed embedding store, the send path can link the existing vector
instead of calling the adapter. `Done` rows are also excluded from the hold
demotion set, so completed embeddings are not the vulnerable target.

The useful cases are the tasks with no usable vector because the prior failure
stopped the adapter path: `contract_violation`, `invalid_input`, `auth_error`,
`budget_exceeded`, and exhausted bounded failures such as `network_error` or
`quota_exceeded`. For `rate_limit`, the retry policy is already unbounded, so
the same field erasure is less interesting as a terminal-state bypass, although
it can still disturb backoff and accounting. For terminal failures, one rename
cycle converts "do not retry" into "try again as new pending work." Repeating
the cycle can consume per-adapter budget or provider quota and keep the index in
a churny state, but each iteration still depends on operator indexing and the
configured budget gates.

The important dead end is trying to send while the task is still held. The code
has a specific `SECRETS_TIER_B_HOLD => false` guard in
`embeddable_task_state()`, so the hold itself is not a network bypass. We only
get the adapter path after the classification moves back to non-secret and the
unhold branch has erased the old terminal state.

## Proof of Concept

The included PoC is a local Python model of the relevant task fields. It starts
with a synthetic embedding task in `Failed(contract_violation, attempts = 1)`,
applies the vulnerable secret-hold mutation, releases the stale hold, and checks
that the resulting task is sendable as fresh `Pending` work. It also models a
minimal fixed invariant, where terminal failures are not demoted into a
destructive hold.

Run it from the report directory:

```sh
cd poc
make run
```

Representative output:

```text
[setup] terminal failure: status=Failed reason=contract_violation attempts=1 retry_allowed=False sendable=False path=notes.md
[vulnerable] after secret hold: status=Paused reason=secrets_tier_b_hold attempts=0 retry_allowed=False sendable=False path=credentials_backup.md
[vulnerable] after non-secret unhold: status=Pending reason=ready_for_online_adapter attempts=0 retry_allowed=False sendable=True path=notes.md
[vulnerable] synthetic adapter path: reserve_usd=0.0000031125 network_used=False call_would_run=True
[fixed] after classification cycle: status=Failed reason=contract_violation attempts=1 retry_allowed=False sendable=False path=notes.md
[result] vulnerable_revives_terminal_failure=True fixed_blocks_revival=True
```

The PoC is intentionally offline. It does not execute the full KCS CLI, call a
provider, read credentials, or create persistent state. It demonstrates the
specific lifecycle violation that lets the real send path see a formerly
terminal task as new pending work.

## Remediation

The invariant to restore is simple: secret classification must not destroy the
retry lifecycle state of an embedding task. A hold can be layered on top of the
task, or it can be refused for states that must remain terminal, but it should
not overwrite `status`, `fallback_reason`, `attempts`, and `next_retry_at` in a
way that cannot be reversed.

A narrow patch is to exclude non-retryable and exhausted failures from
destructive hold demotion:

```rust
let terminal_failed = all_tasks
    .iter()
    .filter(|task| task.task_type == TaskType::Embedding)
    .filter(|task| task.status == TaskStatus::Failed && !task_retry_allowed(task))
    .map(|task| task.output_ref.clone())
    .collect::<BTreeSet<_>>();

let demotable = all_tasks
    .iter()
    .filter(|task| task.task_type == TaskType::Embedding)
    .filter(|task| {
        !already_held.contains(&task.output_ref)
            && !done.contains(&task.output_ref)
            && !terminal_failed.contains(&task.output_ref)
            && task.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE)
    })
    .map(|task| task.output_ref.clone())
    .collect::<BTreeSet<_>>();
```

The more complete design is to make the secret hold an overlay with preserved
pre-hold state. For example, KCS could store the prior status, failure reason,
attempt count, retry timestamp, and reservation fields in explicit hold metadata
and restore those fields on unhold. That would let KCS keep the operator-visible
secret-hold status without weakening retry policy or backoff semantics.

Regression tests should cover at least these cases:

1. `Failed(contract_violation)` renamed into a Tier-B path and back remains
   non-sendable and does not reserve budget.
2. An exhausted `Failed(network_error, attempts = 5)` remains exhausted after a
   hold/unhold cycle.
3. A legitimate fresh secret hold still blocks sending while secret and releases
   only when the pre-hold state was sendable.
4. `Done` and `retired_non_live` tasks keep their existing special handling.

Those tests should assert the task row after each index pass, not just the final
exit code, because the vulnerability is the intermediate loss of state.

## Summary

The vulnerability is a state-machine bug in the boundary between secret
classification and embedding retry policy. We can take an embedding task that
KCS already marked terminal, move the same content through a secret-looking path
and then a non-secret path, and end up with fresh `Pending` work that can enter
the normal budget reservation and adapter-send path. Existing controls keep the
impact low: the workflow is local and operator-mediated, live adapter approval
and budget checks still apply, and the bug does not disclose credentials or
choose a new provider. The state loss is still reportable because it defeats the
retry contract and can repeatedly spend or consume budget for work that should
have stayed terminal.

Future variant analysis should look for other places where KCS encodes two
different state machines in the same `TaskDescriptor` fields. Any path that
temporarily rewrites `status`, `fallback_reason`, `attempts`, or
`next_retry_at` should either prove that the previous lifecycle state is
irrelevant or preserve enough metadata to restore it exactly.
