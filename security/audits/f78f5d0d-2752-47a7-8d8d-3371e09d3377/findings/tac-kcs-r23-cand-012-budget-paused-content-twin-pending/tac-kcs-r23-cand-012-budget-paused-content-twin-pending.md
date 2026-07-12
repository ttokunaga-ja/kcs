# Content-Twin Reuse Leaves Completed Budget-Paused Tasks Falsely Pending

## Executive Summary

KCS can preserve a completed embedding task as `Paused(budget_exceeded)` after
the corresponding chunk has already received a searchable vector through
content-addressed reuse. The affected path is present in revision
`0e19f3c6489da458e93a982a333c308d92d0a0ae`; I did not identify a fixed
revision or public advisory while preparing this report.

The bug appears when a chunk first hits a hard embedding budget cap, and a
byte-distinct content twin later normalizes to the same chunk text and obtains
the current-profile embedding. We then rebuild `chunk_vec` from the shared
`text_hash`, so the originally paused chunk is materially complete and
searchable. Reconciliation recognizes the chunk as live and already embedded,
but a reason-blind `Paused` guard skips the `Done` transition. `index_status`
continues to report pending enrichment and `budget_paused=true` even though the
underlying vector work is done.

I reviewed the vulnerable revision directly and ran the included local
state-model PoC. I did not rerun the full CLI lifecycle or call an embedding
service; the full lifecycle has also been validated in a hermetic mock-embedding
run. The practical impact is low-severity task and
budget-status integrity: search data remains intact, no secrets are sent, and
no extra adapter spend was demonstrated, but automation can keep treating a
completed scope as blocked on budget until an explicit recovery command is run.

## Background

KCS stores chunk embeddings in two related forms. The durable embedding row is
keyed by normalized content, while `chunk_vec` is the searchable projection that
maps each live `chunk_id` to the vector for its current text hash. That design
lets two byte-distinct files that normalize to the same text share one vector.

The important safety exception is a secrets hold. If a file is paused because
its text is classified as Tier B secret material, KCS must not link that held
chunk to a vector produced by a non-secret twin. We can see that narrow
negative control in `crates/kcs-cli/src/main.rs`:

```rust
fn held_secret_embedding_chunk_ids(kcs_dir: &Path) -> Result<BTreeSet<String>> {
    let task_store = TaskStore::new(kcs_dir);
    Ok(task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.task_type == TaskType::Embedding
                && task.status == TaskStatus::Paused
                && task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD)
        })
        .filter_map(|task| {
            task.output_ref
                .strip_prefix("embedding:")
                .map(str::to_owned)
        })
        .collect())
}
```

The rebuild caller passes only those secret-held chunk IDs into
`rebuild_chunk_vec`. A budget pause is therefore intentionally eligible for
content-twin reuse; it is a cost gate, not a secret-send gate:

```rust
let held_chunk_ids = held_secret_embedding_chunk_ids(kcs_dir)?;
embedding_store::rebuild_chunk_vec(fts.connection(), &held_chunk_ids).map_err(index_to_kcs)?;
```

In `crates/kcs-index/src/embedding_store.rs`, the projection is rebuilt by
joining every chunk to the authoritative embedding row on `text_hash`, then
skipping only the held secret chunks:

```rust
pub fn rebuild_chunk_vec(
    conn: &Connection,
    held_chunk_ids: &std::collections::BTreeSet<String>,
) -> Result<()> {
    conn.execute_batch("DELETE FROM chunk_vec;")?;
    let mut stmt = conn.prepare(
        "SELECT c.chunk_id, e.vector, e.dimensions
         FROM chunks c
         JOIN embeddings e ON e.target_type = 'chunk' AND e.target_id = c.text_hash",
    )?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Vec<u8>>(1)?,
                row.get::<_, i64>(2)? as u64,
            ))
        })?
        .collect::<std::result::Result<Vec<_>, _>>()?;
    for (chunk_id, vector, dimensions) in rows {
        if held_chunk_ids.contains(&chunk_id) {
            continue;
        }
        link_chunk_vec(conn, &chunk_id, &vector, dimensions)?;
    }
    Ok(())
}
```

This is the right shape for normal content reuse. The vulnerable state appears
later, when task reconciliation reasons about whether a materially complete
chunk should move its durable task state to `Done`.

## Vulnerability Details

The attack surface is local content plus ordinary operator budget changes. A
lower-trust contributor cannot set the operator's budget cap, but they can
place content in a scope and choose byte sequences that normalize to the same
chunk text. We first need one twin to be indexed while the folder or device
budget is exhausted, producing an embedding task with
`TaskStatus::Paused` and `fallback_reason=budget_exceeded`. After the operator
raises or clears the cap, the contributor's second byte-distinct twin can be
embedded under the same normalized content hash.

Once the twin vector exists, the pending scanner stops considering the first
chunk outstanding. In `live_chunks_without_embedding`, KCS computes the current
profile hash and checks that both the content vector and `chunk_vec` projection
exist:

```rust
let chunk = row.map_err(|err| KcsError::schema(err.to_string()))?;
let embedding_hash = chunk_embedding_hash(&chunk, profile)?;
let has_current_profile = embedding_store::content_vector(conn, &embedding_hash)
    .map_err(index_to_kcs)?
    .is_some();
if has_current_profile && existing.contains(&chunk.chunk_id) {
    continue;
}
```

We should carry that state into reconciliation: the chunk is live, but it is
absent from `pending_ids` because it already has a current-profile vector and a
`chunk_vec` row. The code names that exact state `live_embedded`:

```rust
let live = live_ids.contains(chunk_id);
let live_embedded = live && !pending_ids.contains(chunk_id);
```

For failed or crashed tasks, that state correctly converges the task to `Done`
without another adapter call. The later sweep, however, admits
`TaskStatus::Paused` and then collapses every pause reason to one Boolean:

```rust
let paused = matches!(task.status, TaskStatus::Paused);
if !matches!(
    task.status,
    TaskStatus::Pending | TaskStatus::Running | TaskStatus::Paused
) {
    continue;
}
let Some(chunk_id) = task.output_ref.strip_prefix("embedding:") else {
    continue;
};
if pending_ids.contains(chunk_id) {
    continue;
}
if !live_ids.contains(chunk_id) {
    transitions.insert(
        task.output_ref.clone(),
        embedding_retired_non_live_transition(),
    );
    continue;
}
if paused {
    continue;
}
transitions.insert(task.output_ref.clone(), embedding_done_transition());
```

The guard is correct for `Paused(secrets_tier_b_hold)`: the held file's text was
not approved for online sending, and marking it `Done` would erase the pending
release action. It is too broad for `Paused(budget_exceeded)`. In the budget
case, we are no longer deciding whether to send the original bytes. The vector
has already been materialized under the same content hash by the twin, and
`chunk_vec` already links the original `chunk_id` to it. By skipping the
transition, we leave a durable task row saying budget work is still pending
after the search index has caught up.

The false state reaches the user-facing status sink. `compute_index_status`
counts every paused enrichment task as pending and sets the budget flag when
the fallback reason is `budget_exceeded`:

```rust
TaskStatus::Paused => {
    pending += 1;
    if task.fallback_reason.as_deref() == Some("budget_exceeded") {
        budget_paused = true;
    }
}
```

That gives automation a stale control-plane view: semantic search can return
both twins, but `index_status` still advertises pending enrichment and an
active budget pause.

## Exploitability Analysis

The strongest practical route is a workflow-integrity attack against agents,
CI jobs, or operators that gate behavior on `index_status`. We arrange for one
content twin to become `Paused(budget_exceeded)`, wait for the operator to make
budget available, then let a second twin create the shared vector. From there
we do not need code execution or database corruption. We rely on normal KCS
indexing to rebuild `chunk_vec` from `text_hash`, and then on the reason-blind
paused guard to preserve the wrong durable state.

The attacker control is meaningful but bounded. A content contributor controls
file bytes and ordering, and can make two files normalize to identical chunk
text. They do not independently control the budget lifecycle. If the operator
never has a hard pause or never raises the cap, this particular path does not
materialize. If the operator runs an explicit `batch resume --override-budget`,
the stale row can be healed without a new adapter attempt because the vector is
already present.

The primitive is not direct data disclosure. Search remains functional, both
paths are returned, and the rebuild code still preserves the critical
`secrets_tier_b_hold` boundary. It is also not an extra-spend primitive: the
completion state comes from reuse of an existing content vector. The useful
impact is instead persistent false budget pressure. Downstream automation can
keep delaying work, asking for budget overrides, or reporting a degraded
enrichment ratio even though no adapter work remains for that chunk.

There are a few instructive dead ends. Trying to generalize the fix to every
paused task would break the secrets-hold invariant, because a secret-held chunk
must remain releasable and must not be quietly marked complete through a
non-secret twin. Treating all pauses as sticky avoids that confidentiality
problem but creates this budget-state bug. The stable fix needs to branch on
the pause reason, not only on `TaskStatus::Paused`.

## Proof of Concept

The `poc/` directory contains a small local model of the relevant KCS state. It
uses synthetic byte-distinct twins, strips a UTF-8 BOM to model normalization,
links `chunk_vec` by content hash unless a chunk is on a secrets hold, and then
compares the vulnerable reason-blind reconciliation with a reason-specific
fixed reconciliation. It does not call an embedding adapter or touch a real KCS
store.

Run it from the report directory:

```sh
cd poc
make
```

Representative output:

```text
[+] first twin paused: alpha.md -> Paused(budget_exceeded)
[+] second twin embedded: beta.md shares text_hash 2cf24dba5fb0...
[+] rebuild linked chunk_vec for: alpha.md, beta.md
[+] vulnerable index_status: enriched_ratio=0.50 pending_enrichment_tasks=1 budget_paused=True
[+] fixed index_status: enriched_ratio=1.00 pending_enrichment_tasks=0 budget_paused=False
[+] secrets hold negative control remains Paused(secrets_tier_b_hold)
```

The important assertion is that the vulnerable model leaves `alpha.md`
search-visible and still budget-paused, while the fixed model marks the
budget-paused task `Done` without adding any send or charge. The same fixed
model keeps a same-shape `secrets_tier_b_hold` task paused, which is the
regression condition that prevents the remediation from weakening the
confidentiality control.

## Remediation

The invariant to restore is reason-specific: a live paused chunk that is
already embedded through current-profile content reuse should remain paused
only when the pause reason still represents an unsatisfied authorization gate.
`secrets_tier_b_hold` is such a gate. `budget_exceeded` is not, once the vector
and projection already exist.

A minimal patch should replace the Boolean `paused` guard with a pause
classification. Conceptually:

```rust
let paused_reason = task.fallback_reason.as_deref();
let secret_hold = task.status == TaskStatus::Paused
    && paused_reason == Some(SECRETS_TIER_B_HOLD);

if secret_hold {
    continue;
}

transitions.insert(task.output_ref.clone(), embedding_done_transition());
```

In the real function, this branch belongs after the live and pending checks
that prove the chunk is live and already embedded. The transition should not
call the adapter, should not reserve new budget, and should clear the stale
budget pause by using the existing completion transition. If other paused
reasons exist or are added later, they should be classified explicitly as
authorization holds, budget gates, retry gates, or unknown-sticky states rather
than inheriting a catch-all `Paused` behavior.

Regression tests should exercise both sides of the invariant:

1. Create a chunk that becomes `Paused(budget_exceeded)`, then embed a
   byte-distinct normalized-content twin, rebuild `chunk_vec`, and assert that
   ordinary indexing converges the original task to `Done` with
   `pending_enrichment_tasks=0` and `budget_paused=false`.
2. Repeat the same content-twin shape for a `secrets_tier_b_hold` task and
   assert that it remains paused and excluded from unauthorized vector search
   until the explicit secrets-release path runs.
3. Assert that the convergence path performs no adapter attempt and records no
   new budget reservation when the vector already exists.

## Summary

This vulnerability is a narrow but durable task-convergence bug. We can make a
budget-paused chunk materially complete through content-twin reuse, but the
reconciliation code treats that completed budget pause like an unsent secrets
hold and refuses to mark it `Done`. The result is a false pending and
budget-paused signal that survives normal re-indexing.

The security consequence is limited: the content remains searchable, the
secrets negative control is the reason this code exists, and explicit override
recovery can repair the stale row without another send. The reportable issue is
that lower-trust content can influence trusted automation-facing budget status
under an ordinary multi-stage budget lifecycle. Variant review should focus on
other places where `TaskStatus::Paused` is used without preserving the reason
that made the pause security-relevant.
