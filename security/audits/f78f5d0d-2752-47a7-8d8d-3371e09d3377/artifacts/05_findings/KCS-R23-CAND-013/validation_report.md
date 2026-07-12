# Validation: Embedding reconciliation revives AuthError work during batch retry

- Candidate: `KCS-R23-CAND-013`
- Instance key: not supplied
- Ledger row id: `KCS-R23-CAND-013`
- Advisory/source reference: R23 discovery; no advisory or distinct seed anchor supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-cli/src/main.rs:7997-8043`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.99)**
- Method: **V8 retry/resume differential + V9 command-output check + V10 exact static trace**

## Rubric

- [x] The public `batch retry` contract explicitly excludes non-retryable `AuthError` work.
- [x] A live `Failed(auth_error)` embedding task is reachable through the normal approved embedding workflow.
- [ ] The command-specific `allow_auth_revive=false` control reaches embedding reconciliation as it does markdownize reconciliation.
- [x] The disputed reconciliation occurs before task-state filtering and the adapter-send sink in the same retry pass.
- [x] A hermetic command differential observes zero explicit retry updates but one embedding attempt/execution and a final Done task.

## Evidence

`batch retry` only requeues failed tasks for which `task_retry_allowed` and `task_retry_due` are true, then calls `execute_pending_tasks(..., false, false)` at `crates/kcs-cli/src/main.rs:5639-5666`. The adjacent comment states the command never revives `auth_error`; `max_attempts=0` is the documented command contract.

`execute_pending_tasks` propagates `allow_auth_revive` into markdownize at `crates/kcs-cli/src/main.rs:5934-5956`, and markdownize gates its revival set on that flag at `:5992-6022`. The embedding call at `:5958-5967` has no corresponding argument. In `reconcile_committed_embedding_tasks`, every live, unembedded `Failed(auth_error)` row is changed to Pending, cleared, and reset at `:7997-8043`, regardless of which command invoked the shared enrichment pass.

This mutation precedes the empty-pending return and `filter_embeddable_by_task_state` at `crates/kcs-cli/src/main.rs:7295-7345`. The revived chunk therefore reaches `send_embed_batch` at `:7526-7544`, where its text is placed into an `EmbeddingItem` and passed to the adapter at `:7727-7742`.

A hermetic CLI reproduction under `/tmp/kcs-r23-d2-013` closed the transition:

1. An approved online index using the built-in `auth_error` embedding seam exited 5 and persisted one embedding task as `Failed(auth_error)` with `attempts=1`.
2. With the deterministic mock representing repaired credentials, `batch retry` returned `tasks_updated=0` but `tasks_attempted=1` and `tasks_executed=1`.
3. Readback showed the same task as `Done(embedding_adapter_done)`, with the AuthError state cleared.

The zero update count is the command-specific control behaving as documented in the outer retry loop; the nonzero attempt proves embedding reconciliation independently revived and sent the excluded task.

## Counterevidence and preconditions

- A persistent embedding network approval, an existing AuthError task, repaired credentials, and an operator-issued `batch retry` are all required.
- Secret holds, adapter opt-in, and budget checks remain in force; this does not grant initial network consent or bypass the monthly cap.
- The operator did request retry work generally, but the documented lifecycle makes AuthError a deliberate non-retryable exclusion for this command and reserves credential-repair revival for `batch resume`.
- The built-in mock did not contact a provider. The real sink and request construction are nevertheless the same code path up to the adapter seam.

These controls bound confidentiality and cost impact but do not restore the command-specific authorization/recovery invariant.

## Tests and remaining uncertainty

The reproduction used unique `HOME` and `XDG_*` directories, a private temporary scope, built-in AuthError/mock seams, fake state only, and no external network or credentials. No repository file was changed.

Proof gap: none for the command-policy bypass and same-pass send. The minimal remediation test should mirror the existing markdownize resume-vs-retry test for embedding and assert that `batch retry` leaves `Failed(auth_error)` unchanged while `batch resume` revives it.

## Closure

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|---|---|---|
| KCS-R23-CAND-013 | not supplied | R23 discovery | — | `crates/kcs-cli/src/main.rs:7997-8043` | `batch retry` over a live `Failed(auth_error)` embedding task | `send_embed_batch`, `main.rs:7526-7544,7727-7742` | reportable / medium / high 0.99 | prior approval and operator retry required; budget/secret gates remain; no proof gap | yes |

Validation artifacts: none (ephemeral `/tmp` reproduction; no retained PoC files).
