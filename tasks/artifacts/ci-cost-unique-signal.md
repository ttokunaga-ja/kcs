# Current five-job CI unique-signal ledger

Phase 2 through Phase 4 changed the test-control and test topology but have not been pushed. Consequently the final topology has **zero** GitHub exact-cohort successes (`n=0`): its formal CI baseline is provisional/pending, not a distribution or continuous-SLO result. [Run 32807583550](https://github.com/ttokunaga-ja/kio/actions/runs/32807583550) is retained only as the last observed **pre-consolidation** success: `CI` / `push` / attempt `1`, head `1258f5165ce9098c011223ea3fb6543ed06d7490`, tree `4df488bb524fb7d6f4384aeabbe0646ea69e8436`, workflow blob `07ae8f90747c9bce4e0d9508af2a967ffd8bbed6`, Rust `1.98.0`, and five jobs with `rust -> synthetic-history-eval`. The machine-readable source is [ci-cost-baseline.json](ci-cost-baseline.json).

| Job | Unique signal | Failure signal |
| --- | --- | --- |
| `rust` | Ubuntu format, warnings-denied lint, and complete workspace/all-target tests | format, lint, or workspace test exits nonzero |
| `persona-w0-integration` | Rust Tiny persona lifecycle, create-only preservation, leases, and filesystem attestation | rematerialization, hashes, lease coordination, or attestation claims disagree |
| `synthetic-history-eval` | release/all-features scale, history, cross-scope, rerank, and M3 recall gates | any command fails, rerank cannot apply, or M3-1 recall is below `0.9166666666666666` |
| `macos-security-r23` | complete workspace/all-target tests under macOS semantics | any workspace test exits nonzero on macOS |
| `windows-security-r23` | complete workspace/all-target tests under Windows portability and security semantics | any workspace test exits nonzero on Windows |

The platform test invocations use similar Cargo text but are noninterchangeable OS evidence. Only a demonstrated duplicate signal may be consolidated; scale, history, and cross-platform gates remain when they add a distinct signal.

## Last observed pre-consolidation success

| Job | Result | Elapsed | Cargo test | Post-checkout | GitHub job ID |
| --- | --- | ---: | ---: | ---: | ---: |
| `rust` | success | 25:03 | 24:00 | 0s | 97680591307 |
| `persona-w0-integration` | success | 04:51 | — | 0s | 97680591373 |
| `synthetic-history-eval` | success | 04:40 | — | 1s | 97685151117 |
| `macos-security-r23` | success | 23:44 | 23:26 | 1s | 97680591378 |
| `windows-security-r23` | success | 27:49 | 27:22 | 3s | 97680591455 |

The run ran from `2026-08-25T04:04:55Z` to `2026-08-25T04:34:48Z`: 29:53 wall-clock. Aggregate elapsed is 5,167 seconds = 86:07 = 86.116667 runner-equivalent minutes (job elapsed divided by 60, **not** GitHub billing minutes). The overall critical path is `rust` 25:03 + 00:04 handoff + `synthetic-history-eval` 04:40 = 29:47; Windows completed in 27:49. No job failed, was cancelled, skipped, or was downstream-skipped. Every job's check-run annotation endpoint was empty, and every post-checkout action completed successfully.

This pre-consolidation run is below the 45-minute workflow-wall reference and the 250-minute aggregate runner-equivalent reference. It is not a result for the final topology. GitHub supplied raw billing duration values of zero by OS/job; zero is not interpretable as free, CPU time, or billing minutes, so billing minutes remain null. Internal queue, CPU, RSS, byte I/O, and cache telemetry are unavailable and remain null/unknown rather than zero.

### Long-test warning evidence

The seven `has been running for over 60 seconds` log warnings in this run all later terminated `ok`; they are not unfinished tests or post-checkout work. They covered distinct Tiny/Pilot signals: canonical-plan binding, replaced-source inode detection, partial/cross-plan rejection, schedule/render cross-plan rejection, Tiny shard handling, renderer variants, and artifact-bound enforcement. They therefore remain non-duplicative coverage, while the observed Windows cost is concentrated in the `kio_eval` harness (193 tests / 329.39s) and the `step3` harness (274 / 473.76s), not checkout cleanup. Other observed Windows harnesses were `step2` (104 / 89.55s), `p2c` (40 / 58.19s), `p2b` (44 / 54.77s), `p3b` (33 / 41.06s), and `p2a` (32 / 37.46s).

The repair range `8ba72640744b02a81e31ecd9545a23161e347727..1258f5165ce9098c011223ea3fb6543ed06d7490` has security scan `362c7120-a14d-4154-8c92-d809b76d4adf` with zero findings.

## Cohort separation

[Run 32747140652](https://github.com/ttokunaga-ja/kio/actions/runs/32747140652), head `1bbae928adf2a2fdbf04b1114665cddf40631c5d`, has the same workflow blob but a different test topology. It remains a preserved prior-success cohort and is excluded from the exact current cohort; it does not make `n=2`.

Cancelled [run 32740699426](https://github.com/ttokunaga-ja/kio/actions/runs/32740699426) is a separate 45-minute Windows-timeout diagnostic cohort. Its Windows job was cancelled at 45:15, with the Cargo-test step cancelled after 44:39, so it is ineligible for successful-cost arithmetic. Historical local and failed cohorts remain context only and are never mixed into the current result.

The workflow remains five jobs with a 90-minute Windows bound, no cache action, no schedule, and no Python push/PR evaluator. Manual Full/cold/GPU/external-OCR coverage remains outside this CI cohort. Do not optimize a timeout or declare an SLO until at least three natural push successes match the final topology.
