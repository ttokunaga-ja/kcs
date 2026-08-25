# Current five-job CI critical path

Canonical measurements are in [ci-cost-baseline.json](ci-cost-baseline.json), with gate rationale in [ci-cost-unique-signal.md](ci-cost-unique-signal.md).

The Phase 2–4 final test topology has not been pushed, so its exact GitHub cohort is `n=0` and its formal baseline is provisional/pending. [Run 32807583550](https://github.com/ttokunaga-ja/kio/actions/runs/32807583550), head `1258f5165ce9098c011223ea3fb6543ed06d7490`, tree `4df488bb524fb7d6f4384aeabbe0646ea69e8436`, workflow blob `07ae8f90747c9bce4e0d9508af2a967ffd8bbed6`, Rust `1.98.0`, `CI`/`push`, attempt `1`, and five jobs, is retained as the last observed pre-consolidation success, not an exact sample of the final topology.

## Last observed pre-consolidation measurement

| Job | Started | Completed | Elapsed |
| --- | --- | --- | ---: |
| `rust` | 04:05:00Z | 04:30:03Z | 25:03 |
| `persona-w0-integration` | 04:04:59Z | 04:09:50Z | 04:51 |
| `synthetic-history-eval` | 04:30:07Z | 04:34:47Z | 04:40 |
| `macos-security-r23` | 04:05:00Z | 04:28:44Z | 23:44 |
| `windows-security-r23` | 04:05:00Z | 04:32:49Z | 27:49 |

The workflow started at `2026-08-25T04:04:55Z` and completed at `2026-08-25T04:34:48Z`: 29:53 wall-clock. Aggregate elapsed is 1,503 + 291 + 280 + 1,424 + 1,669 = 5,167 seconds = 86:07 = 86.116667 runner-equivalent minutes; it is not billing time.

```text
max(
  rust + synthetic-history-eval,
  persona-w0-integration,
  macos-security-r23,
  windows-security-r23
)

rust + synthetic-history-eval = 25:03 + 00:04 handoff + 04:40 = 29:47
overall critical path         = rust -> synthetic-history-eval = 29:47
```

No job failed, cancelled, skipped, or was downstream-skipped. All five check-run annotation endpoints were empty. Post-checkout completed successfully in 0s, 0s, 1s, 3s, and 1s respectively for rust, persona, macOS, Windows, and synthetic.

## Finite workflow bounds

```text
rust                         = 35 min
persona-w0-integration       = 15 min
synthetic-history-eval       = 10 min
macos-security-r23           = 35 min
windows-security-r23         = 90 min
configured dependency cap    = 35 + 10 = 45 min
configured aggregate cap     = 35 + 15 + 10 + 35 + 90 = 185 min
```

These are termination bounds, not runtime, queue, or billing measurements. The observed pre-consolidation run is below the 45-minute workflow-wall reference and the 250-minute aggregate reference, but it is not a current final-topology sample. GitHub did not expose internal queue, CPU, RSS, byte I/O, or cache telemetry. Raw billing duration values were zero but are not interpretable as billing minutes; billing therefore remains null/unknown rather than zero. Keep the Windows bound at 90 minutes and make no timeout/SLO optimization until at least three natural push successes match the final topology.

## Historical separation

Prior-success [run 32747140652](https://github.com/ttokunaga-ja/kio/actions/runs/32747140652), head `1bbae928adf2a2fdbf04b1114665cddf40631c5d`, shares the workflow blob but has a different test topology. It remains separate and is not combined with this exact cohort. Cancelled [run 32740699426](https://github.com/ttokunaga-ja/kio/actions/runs/32740699426) is the separate 45-minute Windows-timeout diagnostic: Windows was cancelled at 45:15, and the run remains ineligible for successful-cost arithmetic.
