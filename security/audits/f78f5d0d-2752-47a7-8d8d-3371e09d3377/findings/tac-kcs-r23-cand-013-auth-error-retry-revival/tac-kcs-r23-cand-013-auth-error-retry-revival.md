# Embedding AuthError Revival During Batch Retry

## Executive Summary

The affected KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
lets `kcs batch retry` revive and send embedding work that previously failed
with `auth_error`, even though the command contract explicitly reserves
credential-repair recovery for `kcs batch resume`. The bypass is not in the
top-level retry scheduler. That layer correctly excludes `AuthError` by using
the retry policy with `max_attempts = 0`; the bug appears later when the shared
embedding reconciliation path unconditionally rewrites a live
`Failed(auth_error)` embedding task back to `Pending` before the normal
task-state filter and adapter send.

I reviewed revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` directly and
ran the offline synthetic PoC shipped with this report. I did not exercise a
real embedding provider, use real credentials, or contact a live service. The
validated impact is command-scoped authorization bypass: previously approved
chunk text can be resent and bounded online embedding cost can be incurred
under `batch retry`, contrary to the non-retryable `AuthError` lifecycle.
Initial network approval, secret holds, and budget enforcement still apply, so
the severity is medium rather than high.

## Background

KCS records online enrichment work as tasks. For embedding, each chunk has an
`Embedding` task keyed by an `embedding:<chunk_id>` output reference. A normal
online indexing pass sends eligible chunks to the configured embedding adapter,
writes vectors to the local store, and then updates the corresponding task to
`Done`. Failures are stored with a retry reason such as `network_error`,
`rate_limit`, or `auth_error`.

The retry policy makes `AuthError` special:

```rust
// crates/kcs-pipeline/src/task.rs:338-345
RetryErrorKind::AuthError => RetryPolicy {
    error_kind,
    retryable: false,
    max_attempts: Some(0),
    backoff: "user_action".to_owned(),
    error_code: "KCS-E-BATCH-AUTH-001".to_owned(),
    paused: false,
},
```

That policy is important because a 401/403-style failure means the user must
repair credentials. KCS exposes two recovery commands with different semantics:
`batch retry` is for retryable transient work, while `batch resume` is the
credential-repair path. We can see that split in the batch command handler:

```rust
// crates/kcs-cli/src/main.rs:5639-5666
Some(BatchCommand::Retry) => {
    let partial_reenqueued = reenqueue_partial_markdownize_tasks(&store)?;
    let changed = store
        .update_matching(|task| {
            if task.status == TaskStatus::Failed
                && task_retry_allowed(task)
                && task_retry_due(task)
            {
                task.status = TaskStatus::Pending;
                task.next_retry_at = None;
                true
            } else {
                false
            }
        })
        .map_err(pipeline_to_kcs)?;
    // `batch retry` never overrides the budget cap ... and never
    // revives an auth_error task ...
    let outcome = execute_pending_tasks(&repo, &store, false, false)?;
```

We start from a local operator boundary. The operator has already approved
embedding for the scope, a previous adapter response or broken credential has
left a live embedding task in `Failed(auth_error)`, and credentials later become
usable again. The attacker-relevant influence is earlier in the workflow: a
lower-trust provider response can create the `AuthError` state, and a content
contributor may control text that was already approved for embedding. Neither
actor controls the later `batch retry` command, which is why the bug is best
understood as a command-policy bypass rather than arbitrary remote execution.

## Vulnerability Details

The retry handler passes `allow_auth_revive = false` into the shared pending
task executor. If we carry that flag into the executor, markdownize receives it
as expected, but embedding does not:

```rust
// crates/kcs-cli/src/main.rs:5934-5967
fn execute_pending_tasks(
    repo: &Repository,
    store: &TaskStore,
    override_budget: bool,
    allow_auth_revive: bool,
) -> Result<ExecOutcome> {
    let mut outcome = ExecOutcome::default();
    reclaim_orphaned_running_tasks(store)?;
    if persistent_network_allowed(repo)? {
        outcome.add(execute_pending_markdownize_tasks(
            repo,
            store,
            override_budget,
            allow_auth_revive,
        )?);
    }
    let embedding_online = embedding_online_allowed(repo, false, false, false)?;
    outcome.add(run_embedding_enrichment(
        repo,
        embedding_online,
        override_budget,
    )?);
    Ok(outcome)
}
```

The adjacent markdownize implementation shows the intended invariant. When
`allow_auth_revive` is false, the set of `AuthError` tasks to revive is empty:

```rust
// crates/kcs-cli/src/main.rs:6002-6022
let auth_revivable = if allow_auth_revive {
    store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.task_type == TaskType::Markdownize
                && task.output_ref == output_ref
                && task.status == TaskStatus::Failed
                && retry_kind_from_reason(task.fallback_reason.as_deref())
                    == RetryErrorKind::AuthError
                && !matches!(
                    classify_online_markdownize_precondition(repo, task),
                    OnlineMarkdownizePrecondition::Retire
                )
        })
        .map(|task| task.task_id)
        .collect::<BTreeSet<_>>()
} else {
    BTreeSet::new()
};
```

For embedding, we take a different route. `run_embedding_enrichment()` first
computes live chunks that lack vectors, then calls
`reconcile_committed_embedding_tasks()` before the empty-pending return and
before the task-state filter. That ordering is normally useful: reconciliation
cleans up crash-stranded task state. Here it is also the vulnerable transition.

```rust
// crates/kcs-cli/src/main.rs:7295-7315
let pending = live_chunks_without_embedding(&conn, &head, &chunking_config_hash, &profile)?;

let task_store = TaskStore::new(repo.kcs_dir());
let now = now_utc_seconds();
reconcile_committed_embedding_tasks(
    repo,
    &conn,
    &task_store,
    &head,
    &chunking_config_hash,
    &pending,
    &now,
)?;
if pending.is_empty() {
    return Ok(ExecOutcome::default());
}
```

Inside reconciliation, a live, unembedded `Failed(auth_error)` task is reset to
`Pending` unconditionally. The function does not know whether the current pass
came from `batch resume`, `batch retry`, or a fresh `index --online`.

```rust
// crates/kcs-cli/src/main.rs:7997-8043
let auth_revive_candidate = matches!(task.status, TaskStatus::Failed)
    && retry_kind_from_reason(task.fallback_reason.as_deref())
        == RetryErrorKind::AuthError;
if task.reserved_usd.is_none() && !auth_revive_candidate {
    return false;
}
let Some(chunk_id) = task.output_ref.strip_prefix("embedding:") else {
    return false;
};
let live = live_ids.contains(chunk_id);
let live_embedded = live && !pending_ids.contains(chunk_id);
if live && !live_embedded {
    if retry_kind_from_reason(task.fallback_reason.as_deref())
        == RetryErrorKind::AuthError
    {
        if let Some(entry) =
            reclaim_entry_for(task, &reservation_scope_id, EMBEDDING_ADAPTER_KIND)
        {
            reclaims.push(entry);
        }
        task.status = TaskStatus::Pending;
        task.fallback_reason = None;
        task.attempts = 0;
        task.reserved_usd = None;
        task.reserved_month = None;
        task.next_retry_at = None;
        task.heartbeat_at = None;
        return true;
    }
    return false;
}
```

From here the bypass is deterministic. The task-state filter would have
excluded a still-failed `AuthError` task because `task_retry_allowed()` is false
for `AuthError`. But we no longer have a failed task; we have a freshly
`Pending` one, so the filter lets the chunk continue:

```rust
// crates/kcs-cli/src/main.rs:7777-7820
fn filter_embeddable_by_task_state(
    task_store: &TaskStore,
    pending: Vec<EmbeddableChunk>,
    override_budget: bool,
) -> Result<Vec<EmbeddableChunk>> {
    let tasks = task_store.all().map_err(pipeline_to_kcs)?;
    let by_ref = tasks
        .iter()
        .filter(|task| task.task_type == TaskType::Embedding)
        .map(|task| (task.output_ref.clone(), task))
        .collect::<BTreeMap<_, _>>();
    Ok(pending
        .into_iter()
        .filter(|chunk| {
            let output_ref = embedding_task_output_ref(&chunk.chunk_id);
            match by_ref.get(&output_ref) {
                Some(task) => embeddable_task_state(task, override_budget),
                None => true,
            }
        })
        .collect())
}

fn embeddable_task_state(task: &TaskDescriptor, override_budget: bool) -> bool {
    match task.status {
        TaskStatus::Paused => match task.fallback_reason.as_deref() {
            Some("budget_exceeded") => override_budget,
            Some(SECRETS_TIER_B_HOLD) => false,
            _ => true,
        },
        TaskStatus::Failed => task_retry_due(task) && task_retry_allowed(task),
        _ => true,
    }
}
```

The send path then constructs `EmbeddingItem` objects from the chunk text and
passes them to the adopted embedding adapter. That is the sink that makes the
policy bypass security-relevant: the wrong recovery command can trigger a real
outbound send and a budget reservation.

```rust
// crates/kcs-cli/src/main.rs:7526-7544
match send_embed_batch(&conn, execution, &profile, &plan.to_send) {
    Ok(()) => {
        record_embedding_transitions(
            &mut transitions,
            plan.to_send.iter().map(|(chunk, _)| *chunk),
            embedding_done_transition(),
        );
        outcome.executed += plan.to_send.len();
    }
    Err(failure) => {
        record_embedding_transitions(
            &mut transitions,
            plan.to_send.iter().map(|(chunk, _)| *chunk),
            embedding_fail_transition(failure.retry_kind),
        );
        count_embedding_failure(&mut outcome, failure.retry_kind, plan.to_send.len());
        break;
    }
}
```

```rust
// crates/kcs-cli/src/main.rs:7727-7742
fn send_embed_batch(
    conn: &Connection,
    execution: AdoptedEmbeddingExecution,
    profile: &DeclaredEmbeddingProfile,
    to_send: &[(&EmbeddableChunk, String)],
) -> std::result::Result<(), TaskExecutionFailure> {
    let items = to_send
        .iter()
        .map(|(chunk, _)| EmbeddingItem {
            id: chunk.chunk_id.clone(),
            text: Some(chunk.text.clone()),
            path: None,
            mime: None,
        })
        .collect::<Vec<_>>();
    let vectors = run_embedding_adapter(execution, items, EmbeddingInputType::MarkdownChunk)?;
```

The important state table is small:

| Step | Expected under `batch retry` | Vulnerable embedding path |
| --- | --- | --- |
| Existing task | `Failed(auth_error)`, `attempts=1` | same |
| Top-level retry scheduler | leaves task failed, `tasks_updated=0` | same |
| Auth revival policy | `allow_auth_revive=false` | not passed to embedding reconciliation |
| Reconciliation | should leave `AuthError` failed | changes task to `Pending`, clears reason and attempts |
| Task filter | would skip failed non-retryable task | accepts `Pending` task |
| Adapter sink | no send | sends chunk text and may charge budget |

That is why the command output can honestly report `tasks_updated=0` while the
same pass still reports embedding attempts and executions. The visible outer
retry update count describes only the scheduler. The later reconciliation
mutation creates work behind that scheduler's policy boundary.

## Exploitability Analysis

The strongest realistic route is a provider-response and operator-recovery
sequence. We first need an embedding task that is live, unembedded, and failed
with `auth_error`. A broken credential, expired token, or lower-trust remote
provider returning an authorization error can create that state during an
already-approved online embedding attempt. We then wait for credentials to be
usable again. If the operator chooses `batch retry` to re-drive transient work,
the outer loop still refuses the `AuthError` task, but the embedding
reconciliation pass revives it and reaches the adapter send.

This route has meaningful constraints:

- Persistent embedding approval must already exist for the scope. The bug does
  not create initial network consent.
- Secret hold checks still run before sendable chunks enter the embedding
  pipeline, so a candidate-secret file remains held unless the operator has
  approved sending secrets.
- Budget enforcement still runs before `send_embed_batch()`, so the monetary
  impact is bounded by configured caps and by the chunks selected in the scope.
- The attacker does not directly issue `batch retry`. The later command is a
  trusted operator action, which limits the primitive to a confused recovery
  workflow.

Within those bounds, the primitive is still useful. If we control content that
was already approved for embedding, we can make that text eligible for a resend
under a command whose documented semantics say `AuthError` is not retried. If
we are the provider-side actor, we can shape the earlier failure state and then
observe a later request that should have required the operator to choose
`batch resume`. In both cases the outcome is a recovery-policy bypass: content
leaves the host, the adapter may bill, and audit/accounting fields show a
successful embedding transition from a command that was supposed to skip this
failure class.

A stronger confidentiality story is constrained by existing consent. The text
was already in the approved embedding scope before the `AuthError`, so this is
not equivalent to sending a newly unapproved file. A stronger cost story is
also constrained by the budget gate and the per-chunk reservation logic. The
interesting exploitability point is therefore not "unbounded exfiltration" or
"uncapped spend"; it is that KCS presents `batch retry` as a non-auth-revival
operation, while embedding has a second state machine that silently defeats
that operation-specific guarantee.

The most natural variant search is any enrichment or reconciliation function
that mutates task state before shared task-state filtering. Markdownize is a
negative control here because it receives and honors `allow_auth_revive`.
Embedding should carry the same policy bit, or its reconciliation should be
split into command-neutral cleanup and explicitly authorized credential
revival.

## Proof of Concept

The included PoC is intentionally local and synthetic. It does not import KCS,
open a repository, read credentials, or contact an adapter. Instead, it models
the relevant state machine from the source snippets above:

1. Start with a live unembedded embedding chunk and a matching
   `Failed(auth_error)` task.
2. Run the `batch retry` outer scheduler and show that it updates zero tasks.
3. Run the vulnerable embedding reconciliation and show that it changes the
   failed task to `Pending` without an `allow_auth_revive` check.
4. Run the task-state filter and mock adapter send.
5. Compare that with a fixed reconciliation that honors
   `allow_auth_revive=false` for retry and `true` for resume.

From the report directory:

```sh
cd poc
make
```

Representative output:

```text
[setup] live embedding task starts as Failed(auth_error), attempts=1
[retry] outer retry scheduler changed 0 task(s)
[vulnerable] reconciliation changed 1 task(s) without an auth-revival gate
[vulnerable] adapter mock sent 1 chunk(s): approved-chunk-1
[vulnerable] final task: Done(embedding_adapter_done), attempts=0
[fixed retry] reconciliation changed 0 task(s); sent 0 chunk(s); task stays Failed(auth_error)
[fixed resume] reconciliation changed 1 task(s); sent 1 chunk(s); task becomes Done(embedding_adapter_done)
[ok] vulnerable retry revival and fixed retry/resume split reproduced offline
```

The PoC proves the policy failure, not provider behavior. The prior validation
for this finding used KCS's hermetic built-in adapter seams to confirm the real
CLI transition: an initial `auth_error` embedding attempt persisted a failed
task, then `batch retry` with repaired mock credentials returned
`tasks_updated=0` but `tasks_attempted=1` and `tasks_executed=1`, and the task
became `Done(embedding_adapter_done)`.

## Remediation

The invariant to restore is: `AuthError` revival is command-scoped recovery
work. `batch resume` may revive it after credentials are repaired; `batch
retry` must not. Embedding reconciliation should receive and enforce the same
policy decision that markdownize already receives.

A minimal fix is to pass `allow_auth_revive` through the embedding path and
gate only the live-`AuthError` revival branch on that value:

```rust
fn execute_pending_tasks(
    repo: &Repository,
    store: &TaskStore,
    override_budget: bool,
    allow_auth_revive: bool,
) -> Result<ExecOutcome> {
    // ...
    outcome.add(run_embedding_enrichment(
        repo,
        embedding_online,
        override_budget,
        allow_auth_revive,
    )?);
    Ok(outcome)
}

fn reconcile_committed_embedding_tasks(
    // existing parameters...
    allow_auth_revive: bool,
) -> Result<()> {
    // ...
    if live && !live_embedded {
        if allow_auth_revive
            && retry_kind_from_reason(task.fallback_reason.as_deref())
                == RetryErrorKind::AuthError
        {
            task.status = TaskStatus::Pending;
            task.fallback_reason = None;
            task.attempts = 0;
            task.reserved_usd = None;
            task.reserved_month = None;
            task.next_retry_at = None;
            task.heartbeat_at = None;
            return true;
        }
        return false;
    }
}
```

I would also add focused regression tests that mirror the markdownize
resume-vs-retry coverage:

- Create a live embedding task in `Failed(auth_error)` with an unembedded live
  chunk and repaired mock credentials.
- Assert `kcs batch retry --json` leaves the task `Failed(auth_error)`, reports
  `tasks_updated=0`, and records no embedding attempt or execution.
- Assert `kcs batch resume --json` revives the same state and completes the
  embedding.
- Assert non-auth retry classes still follow their existing retry behavior, and
  secret holds plus budget pauses remain sticky.

Longer-term hardening should make task reconciliation APIs explicit about which
state repairs are command-neutral cleanup and which are policy-bearing recovery
actions. Cleanup such as "already embedded, mark done" can run in every
embedding pass. Credential revival should not be hidden inside a generic
reconcile step without the caller's recovery mode.

## Summary

The vulnerable revision has two recovery state machines for enrichment tasks.
The visible `batch retry` state machine correctly treats `AuthError` as
non-retryable, but the embedding reconciliation state machine revives the same
failure class before task-state filtering and adapter send. We demonstrated how
that converts a live `Failed(auth_error)` embedding task into an outbound
embedding request under the wrong command, while existing network approval,
secret hold, and budget controls keep the impact bounded.

The direct fix is to propagate and enforce the command's `allow_auth_revive`
decision in the embedding path. Variant review should focus on other
pre-filter reconciliation or repair routines that can change task eligibility
without receiving the command-level authorization policy.
