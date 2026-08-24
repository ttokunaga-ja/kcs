# Current five-job CI unique-signal ledger

The authoritative current cohort is [run 32747140652](https://github.com/ttokunaga-ja/kio/actions/runs/32747140652): `CI` / `push` / attempt `1`, head `1bbae928adf2a2fdbf04b1114665cddf40631c5d`, tree `22ad7bc8001347a4510422dfbf6e43d0215400a9`, workflow blob `07ae8f90747c9bce4e0d9508af2a967ffd8bbed6`, Rust `1.98.0`, and five jobs with `rust -> synthetic-history-eval`. It has one matching success (`n=1`), so the formal current-CI baseline is **provisional**, not a distribution or continuous-SLO result. The machine-readable source is [ci-cost-baseline.json](ci-cost-baseline.json).

| Job | Unique signal | Failure signal |
| --- | --- | --- |
| `rust` | Ubuntu format, warnings-denied lint, complete workspace/all-target tests, and Full-example compile | format, lint, example, or workspace test exits nonzero |
| `persona-w0-integration` | Rust Tiny persona lifecycle, create-only preservation, leases, and filesystem attestation | rematerialization, hashes, lease coordination, or attestation claims disagree |
| `synthetic-history-eval` | release/all-features evaluator plus tiny scale, history, cross-scope, rerank, and M3 recall | any command fails, rerank cannot apply, or M3-1 recall is below `0.9166666666666666` |
| `macos-security-r23` | complete workspace/all-target tests under macOS semantics | any workspace test exits nonzero on macOS |
| `windows-security-r23` | complete workspace/all-target tests under Windows portability and security semantics | any workspace test exits nonzero on Windows |

The three platform test invocations have identical Cargo text but noninterchangeable OS evidence. Only a demonstrated duplicate signal may be consolidated; Full, cold, and scale commands remain manual when they add a distinct signal.

## Current matching success

| Job | Result | Elapsed | GitHub job ID |
| --- | --- | ---: | ---: |
| `rust` | success | 23:50 | 97495261887 |
| `persona-w0-integration` | success | 04:02 | 97495262074 |
| `synthetic-history-eval` | success | 04:06 | 97502852808 |
| `macos-security-r23` | success | 21:51 | 97495262123 |
| `windows-security-r23` | success | 29:38 | 97495262075 |

The run ran from `2026-08-24T15:48:52Z` to `2026-08-24T16:18:35Z`: 29:43 wall-clock. Aggregate elapsed is 5,007 seconds = 83:27 = 83.45 runner-equivalent minutes (elapsed divided by 60, **not** GitHub billing minutes). The overall critical path is Windows at 29:38. The required dependency path is `rust` 23:50 + 00:03 handoff + `synthetic-history-eval` 04:06 = 27:59. No job failed, was cancelled, skipped, or was downstream-skipped.

This one run is below the 45-minute wall-clock reference and the 250-minute aggregate runner-equivalent reference. Those are single-run comparisons only. GitHub did not expose internal queue, billing, CPU, RSS, byte I/O, or cache telemetry; each value remains null/unknown and is not treated as zero.

### Windows harness evidence and Phase 3 candidates

The Windows job produced 49 harness result blocks with 1,947 passed, zero failed, and zero ignored tests. Its longest harness block was 452.70 seconds. Cargo emitted 11 `has been running for over 60 seconds` progress warnings; every warned test later had terminal `ok`. The warnings are candidate inputs for Phase 3 bounded-fixture or duplicate-signal review, not missing results, failures, or evidence of an unbounded test. Harness wall times are not GitHub billing, CPU, RSS, or I/O measurements.

The Phase 3 priority harnesses measured on Windows were `step2_p0_contract` 86.62s, `step3_p0_contract` 452.70s, `step4b_p2a_contract` 36.00s, `step4b_p2b_contract` 52.97s, `step4b_p2c_contract` 103.90s, `step4b_p3a_contract` 29.75s, and `step4b_p3b_contract` 39.20s. The complete 49-harness extraction, including pass counts and elapsed seconds, is retained under `current_success_cohort.windows_harness_evidence.per_harness` in the JSON artifact.

Phase 3 should inventory the warned tests by failure mode, fixture, subprocess, SQLite, and CAS-rebuild signal, then retain one bounded behavior test per distinct failure class. A later non-`ok`, timeout, cancellation, or missing terminal result is the failure signal requiring investigation.

## Separate cancelled cohort

[Run 32740699426](https://github.com/ttokunaga-ja/kio/actions/runs/32740699426) is a separate cancelled 45-minute cohort: head `0584667837bee12afe125ecd7d6cf395ac673298`, workflow blob `bdc01e224cf952148910b6a6200b9ac1e451dd9e`, workflow wall 45:20, jobs 29:56 / 04:47 / 04:11 / 24:05 / 45:15, aggregate 6,494 seconds = 108:14, and `rust -> synthetic-history-eval` 34:12. It is ineligible for successful-cost arithmetic and does not increase `n`.

Historical local and failed cohorts remain historical context only. They are not relabeled as current, and their values are never mixed into this cohort.
