# Validation: Content-twin reuse leaves completed budget-paused tasks falsely pending

- Candidate: `KCS-R23-CAND-012`
- Instance key: not supplied
- Ledger row id: `KCS-R23-CAND-012`
- Advisory/source reference: R23 discovery; no advisory or distinct seed anchor supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-cli/src/main.rs:8088-8132`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.99)**
- Method: **V8 lifecycle reproduction + V9 observability + V10 exact static trace**

## Rubric

- [x] A normal CLI sequence can create a live `Paused(budget_exceeded)` embedding task without corrupting private state.
- [x] A byte-distinct content twin can materialize the same current-profile content vector and rebuild a `chunk_vec` row for the paused chunk.
- [ ] The closest reconciliation control distinguishes a secrets hold from a completed budget pause before preserving `Paused`.
- [x] Durable task state drives a false pending/budget signal after the underlying embedding is searchable.
- [x] A nearby control demonstrates scope: explicit `batch resume --override-budget` heals the row without an adapter attempt.

## Evidence

The rebuild derives `chunk_vec` by joining every chunk to authoritative embeddings on `text_hash` at `crates/kcs-index/src/embedding_store.rs:149-184`. The caller excludes only chunk ids whose task is `Paused(secrets_tier_b_hold)` at `crates/kcs-cli/src/main.rs:3008-3027,3655-3658`; a budget-paused chunk is intentionally eligible for content reuse.

`live_chunks_without_embedding` treats a current content vector plus a `chunk_vec` row as complete at `crates/kcs-cli/src/main.rs:7911-7917`. Reconciliation then recognizes the chunk as live and not pending at `:8006-8013`, but its final sweep reduces every pause reason to the Boolean `paused` and skips the Done transition at `:8088-8132`. That guard is necessary for a secrets hold, whose text was never approved for sending, but is overbroad for `budget_exceeded` after content-addressed reuse has completed the work.

A hermetic CLI lifecycle under `/tmp/kcs-r23-d2-012` reproduced the exact state:

1. A UTF-8-BOM `alpha.md` was indexed with a zero folder cap and the built-in embedding mock. The command exited 6 and left its embedding task `paused` with `fallback_reason=budget_exceeded`.
2. The cap was raised to 50, and byte-distinct `beta.md` containing the same normalized text was added. Its index pass executed one embedding. A following no-op index rebuilt `chunk_vec` from the shared `text_hash`.
3. Search returned both `alpha.md` and `beta.md`, proving the paused chunk had a current searchable vector, while `index_status` still returned `enriched_ratio=0.75`, `pending_enrichment_tasks=1`, and `budget_paused=true`. `status` retained the alpha embedding task as `Paused(budget_exceeded)`.
4. `batch resume --override-budget` then reported `tasks_updated=1`, `tasks_attempted=0`, and `tasks_executed=0`, confirming the stale row was healable without another send or charge.

`compute_index_status` counts that preserved pause as pending and sets the budget flag at `crates/kcs-cli/src/main.rs:2417-2506`. The false state therefore survives ordinary re-indexing and directly reaches automation-facing search output.

## Counterevidence and preconditions

- The sequence needs an earlier hard budget pause and a byte-distinct chunk with identical normalized text.
- Search data is intact: both paths are returned, and no confidentiality or cap-bypass effect was observed.
- The explicit override command repairs the record for free; the defect is durable task/status integrity and misleading recovery, not unbounded spend.
- A `secrets_tier_b_hold` must remain paused even when a twin vector exists. The needed fix is reason-specific and must preserve that negative control.

These constraints bound impact but do not defeat the persistent false workflow state or its automation-facing sink.

## Tests and remaining uncertainty

The reproduction used unique `HOME` and `XDG_*` directories, a private temporary scope, the built-in deterministic embedding mock, and no external network or credentials. It exercised the real CLI, task store, SQLite rebuild, search, and recovery command. No repository file was changed.

Proof gap: none for the claimed state transition. The minimal remediation test should repeat this lifecycle and assert that an already-embedded `budget_exceeded` task converges to Done while a same-shape secrets hold remains Paused.

## Closure

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|---|---|---|
| KCS-R23-CAND-012 | not supplied | R23 discovery | — | `crates/kcs-cli/src/main.rs:8088-8132` | budget-paused live chunk plus byte-distinct content twin | `compute_index_status`, `main.rs:2417-2506` | reportable / medium / high 0.99 | searchable data remains intact; explicit override heals without a send; no proof gap | yes |

Validation artifacts: none (ephemeral `/tmp` reproduction; no retained PoC files).
