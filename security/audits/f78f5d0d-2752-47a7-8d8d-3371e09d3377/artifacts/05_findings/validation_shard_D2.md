# Validation Shard D2

- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Scope: `.`
- Candidate inventory: exactly `KCS-R23-CAND-012`, `KCS-R23-CAND-013`, `KCS-R23-CAND-014`
- Closure: 3/3
- Dispositions: 3 reportable, 0 suppressed, 0 not_applicable, 0 deferred
- Repository writes: none
- External network: none

## Validation closure table

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|---|---|---|
| KCS-R23-CAND-012 | not supplied | R23 discovery | — | `crates/kcs-cli/src/main.rs:8088-8132` | budget-paused live chunk plus byte-distinct content twin | task-derived `compute_index_status`, `main.rs:2417-2506` | reportable / medium / high 0.99 | both paths remain searchable; explicit override heals without send; no proof gap | yes |
| KCS-R23-CAND-013 | not supplied | R23 discovery | — | `crates/kcs-cli/src/main.rs:7997-8043` | `batch retry` over live `Failed(auth_error)` embedding task | `send_embed_batch`, `main.rs:7526-7544,7727-7742` | reportable / medium / high 0.99 | prior approval/operator retry required; budget and secret gates remain; no proof gap | yes |
| KCS-R23-CAND-014 | not supplied | R23 discovery | — | `crates/kcs-cli/src/main.rs:9120-9169` | unsupported binary direct child | `status` and task-only completeness, `main.rs:435-450,2417-2506` | reportable / medium / high 0.99 | raw bytes preserved and one-run count exists; no proof gap | yes |

## Focused validation

All runtime cases used unique `HOME`/`XDG_*` directories and private `/tmp` scopes.

- CAND-012: zero-cap pause -> raised cap -> byte-distinct normalized-text twin -> one mock embedding -> rebuild -> both paths searchable while the first task remained budget-paused; explicit override healed it with zero adapter attempts.
- CAND-013: mock AuthError -> persisted `Failed(auth_error)` -> `batch retry` with repaired mock -> `tasks_updated=0` but one attempted/executed embedding -> Done.
- CAND-014: unsupported binary plus searchable text control -> one-run skipped counter -> later status lacked a disposition -> search claimed `enriched_ratio=1.0` and pending 0 -> retained event omitted the path.

Per-finding reports and final validation receipts are stored in each candidate directory. Each ledger ends with exactly: `discovery`, `candidate_local_validation`, `candidate_local_attack_path`, `validation`.
