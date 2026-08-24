# Current five-job CI critical path

Canonical measurements are in [ci-cost-baseline.json](ci-cost-baseline.json), with job-signal rationale in [ci-cost-unique-signal.md](ci-cost-unique-signal.md).

The current matching success is [run 32747140652](https://github.com/ttokunaga-ja/kio/actions/runs/32747140652): head `1bbae928adf2a2fdbf04b1114665cddf40631c5d`, tree `22ad7bc8001347a4510422dfbf6e43d0215400a9`, workflow blob `07ae8f90747c9bce4e0d9508af2a967ffd8bbed6`, Rust `1.98.0`, `CI`/`push`, attempt `1`, and five jobs. It is the sole current success sample (`n=1`), so the baseline is provisional.

## Measured result

| Job | Started | Completed | Elapsed |
| --- | --- | --- | ---: |
| `rust` | 15:48:57Z | 16:12:47Z | 23:50 |
| `persona-w0-integration` | 15:48:57Z | 15:52:59Z | 04:02 |
| `synthetic-history-eval` | 16:12:50Z | 16:16:56Z | 04:06 |
| `macos-security-r23` | 15:48:57Z | 16:10:48Z | 21:51 |
| `windows-security-r23` | 15:48:56Z | 16:18:34Z | 29:38 |

The workflow started at `2026-08-24T15:48:52Z` and completed at `2026-08-24T16:18:35Z`: 29:43 wall-clock. Aggregate elapsed is 1,430 + 242 + 246 + 1,311 + 1,778 = 5,007 seconds = 83:27 = 83.45 runner-equivalent minutes; it is not billing time.

```text
max(
  rust + synthetic-history-eval,
  persona-w0-integration,
  macos-security-r23,
  windows-security-r23
)

rust + synthetic-history-eval = 23:50 + 00:03 handoff + 04:06 = 27:59
overall critical path         = windows-security-r23 = 29:38
```

No job failed, cancelled, skipped, or was downstream-skipped. GitHub provided no internal queue, billing, CPU, RSS, byte I/O, or cache telemetry; these are null/unknown, not zero.

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

These are termination bounds, not runtime, queue, or billing measurements. The measured current run is below the 45-minute workflow-wall reference and the 250-minute aggregate reference, but `n=1` is not a continuous-SLO claim.

## Historical separation

Cancelled [run 32740699426](https://github.com/ttokunaga-ja/kio/actions/runs/32740699426) (head `0584667837bee12afe125ecd7d6cf395ac673298`, blob `bdc01e224cf952148910b6a6200b9ac1e451dd9e`) ended at 45:20 with aggregate 108:14 and a 34:12 `rust -> synthetic-history-eval` path. It is not a successful-cost sample. Older local and failed cohorts remain separately recorded in the JSON artifact and are never combined with the current result.
