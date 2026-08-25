# Latest observed five-job CI critical path

The canonical machine-readable record is [ci-cost-baseline.json](ci-cost-baseline.json); the distinct gate rationale is in [ci-cost-unique-signal.md](ci-cost-unique-signal.md).

[Run 32890496534](https://github.com/ttokunaga-ja/kio/actions/runs/32890496534) is the latest exact GitHub success observed at the record's capture time (`n=1`): `CI` / natural `push` / attempt `1` / success, tested HEAD `55b87e05bc59adbfa33d80af02de37e7fda3de95`, tree `39f738fd4a6b8cfe5d5ba72e729c4fdf10fb9570`, workflow blob `07ae8f90747c9bce4e0d9508af2a967ffd8bbed6`, Rust `1.98.0`, and the five-job topology below. This is a time-fixed observation, not a claim that any later commit is measured, a distribution, or a continuous SLO.

| Job | Runner | Needs | Elapsed |
| --- | --- | --- | ---: |
| `rust` | `ubuntu-latest` | — | 23:26 |
| `persona-w0-integration` | `ubuntu-latest` | — | 04:24 |
| `synthetic-history-eval` | `ubuntu-latest` | `rust` | 04:04 |
| `macos-security-r23` | `macos-latest` | — | 23:15 |
| `windows-security-r23` | `windows-latest` | — | 26:58 |

The run started at `2026-08-25T19:36:10Z` and completed at `2026-08-25T20:03:49Z`: 1,659 seconds = 27:39 wall-clock. Aggregate job elapsed is 4,927 seconds = 82:07 = 82.116667 runner-equivalent minutes; it is not billing time. The longest individual job was `windows-security-r23` at 26:58. The critical dependency path was `rust` 23:26 + 00:05 handoff + `synthetic-history-eval` 04:04 = 1,655 seconds = 27:35.

```text
max(
  rust + synthetic-history-eval,
  persona-w0-integration,
  macos-security-r23,
  windows-security-r23
)
```

All five jobs succeeded; none failed, was cancelled, skipped, or downstream-skipped.

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

These are termination bounds, not runtime, queue, or billing measurements. The single cohort is below the 45-minute workflow-wall reference and the 250-minute aggregate runner-equivalent reference, but no SLO or distribution is claimed. GitHub internal queue, billing, CPU, RSS, byte I/O, and cache telemetry remain null/unknown, never zero. Do not optimize a timeout or declare an SLO until at least three natural push successes match the exact topology, toolchain, flags, and runner contract.

## Recording boundary and historical separation

This observation is bound only to tested HEAD `55b87e05bc59adbfa33d80af02de37e7fda3de95` and tree `39f738fd4a6b8cfe5d5ba72e729c4fdf10fb9570`. The commit that records this evidence and every later commit are unmeasured until a distinct exact cohort exists; equality of selected blobs does not extend the observation's authority.

Previous exact-success [run 32848763996](https://github.com/ttokunaga-ja/kio/actions/runs/32848763996) at HEAD `049288af26515edba125925a7f496fe77a8ff90f` is historical. Failed [run 32884825839](https://github.com/ttokunaga-ja/kio/actions/runs/32884825839) is also historical and is excluded from successful-cost arithmetic. Prior-success [run 32747140652](https://github.com/ttokunaga-ja/kio/actions/runs/32747140652) used the same workflow blob but a different test topology, and cancelled [run 32740699426](https://github.com/ttokunaga-ja/kio/actions/runs/32740699426) is the separate Windows-timeout diagnostic; neither enters this exact success observation.
