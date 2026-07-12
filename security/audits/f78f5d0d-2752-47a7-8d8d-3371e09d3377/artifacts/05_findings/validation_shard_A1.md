# Validation Shard A1

- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Scope: `.`
- Candidate inventory: exactly `KCS-R23-CAND-021`, `KCS-R23-CAND-025`, `KCS-R23-CAND-052`, `KCS-R23-CAND-053`
- Closure: 4/4
- Dispositions: 3 reportable, 1 suppressed, 0 not_applicable, 0 deferred
- Repository writes: none
- External network: none

## Validation closure table

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|---|---|---|
| KCS-R23-CAND-021 | not supplied | R23 discovery | — | `crates/kcs-pipeline/src/scan.rs:164-175` | effective `$HOME/.config/kcs/tools.toml`; `main.rs:10952-10957` | embedding item/request body; `main.rs:7726-7742`, `gemini_embedding.rs:120-146` | reportable / medium / high 0.85 | explicit config-directory scope selection and approval; preview lists the file; no loopback capture | yes |
| KCS-R23-CAND-025 | not supplied | R23 discovery | — | `crates/kcs-cli/src/main.rs:6362-6378` | copied/preseeded store accepted by `scope.rs:188-200,889-909` | prompt/network/secret gates; `main.rs:586-610,10418-10445,10543-10555` | reportable / medium / high 0.88 | `--offline`/revocation and tool-id checks scope impact; portable-scope intent ambiguity; no same-ID runtime send | yes |
| KCS-R23-CAND-052 | not supplied | R23 discovery | — | `crates/kcs-cli/src/main.rs:10862-10893` | operator-created readable `tools.toml`; `tool_lock.rs:479-492` | configured provider credential headers | suppressed / none / high 0.97 | docs and focused test require warning-only success; KCS does not create/widen the file; OS exposure already exists | no |
| KCS-R23-CAND-053 | not supplied | R23 discovery | — | `crates/kcs-adapter/src/catalog.rs:102-132,314-333` | lower-trust inherited `KCS_TEST_*` environment | normalized/vector persistence; `main.rs:6674-6789,7480-7553,7726-7768` | reportable / medium / medium 0.78 | outer approval/budget controls remain; no concrete shipped lower-trust launcher demonstrated | yes |

## Focused tests

All commands used `CARGO_NET_OFFLINE=true` and `CARGO_TARGET_DIR=/tmp/kcs-r23-auth-static-target`.

- `p3_plain_auth_tools_toml_permission_warning`: passed (1/1).
- `r6_foreign_approval_rows_do_not_grant_online_embedding`: passed (1/1).
- `ct3_hybrid_001_auto_resolves_to_hybrid_with_rrf_fusion`: passed (1/1).
- `catalog::tests::standard_online_markdownize_mock_runs`: passed (1/1).

Per-finding reports and final validation receipts are stored in each candidate directory. Each ledger ends with exactly: `discovery`, `candidate_local_validation`, `candidate_local_attack_path`, `validation`.
