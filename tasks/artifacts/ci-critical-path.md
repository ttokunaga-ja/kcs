# Current five-job CI critical path

The canonical machine-readable record is [ci-cost-baseline.json](ci-cost-baseline.json); the distinct gate rationale is in [ci-cost-unique-signal.md](ci-cost-unique-signal.md).

[Run 32848763996](https://github.com/ttokunaga-ja/kio/actions/runs/32848763996) is the sole exact current GitHub cohort (`n=1`): `CI` / natural `push` / attempt `1` / success, tested HEAD `049288af26515edba125925a7f496fe77a8ff90f`, tree `25975f5da1a8e39f999e1282600d2ebc088a2f70`, workflow blob `07ae8f90747c9bce4e0d9508af2a967ffd8bbed6`, Rust `1.98.0`, and the five-job topology below. It is a single observation, not a distribution or continuous SLO.

| Job | Runner | Needs | Elapsed |
| --- | --- | --- | ---: |
| `rust` | `ubuntu-latest` | — | 24:54 |
| `persona-w0-integration` | `ubuntu-latest` | — | 03:20 |
| `synthetic-history-eval` | `ubuntu-latest` | `rust` | 04:12 |
| `macos-security-r23` | `macos-latest` | — | 22:16 |
| `windows-security-r23` | `windows-latest` | — | 31:37 |

The run started at `2026-08-25T12:39:05Z` and completed at `2026-08-25T13:10:46Z`: 31:41 wall-clock. Aggregate job elapsed is 5,179 seconds = 86:19 = 86.316667 runner-equivalent minutes; it is not billing time. The longest observed job was `windows-security-r23` at 31:37. The dependency path was `rust` 24:54 + 00:04 handoff + `synthetic-history-eval` 04:12 = 29:10.

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

Any later docs-only Phase A recording commit is not itself measured: this cohort is bound only to tested HEAD `049288af26515edba125925a7f496fe77a8ff90f`. The follow-on record leaves product, test, and workflow blobs unchanged from that tested HEAD.

Prior-success [run 32747140652](https://github.com/ttokunaga-ja/kio/actions/runs/32747140652) used the same workflow blob but a different test topology, so it remains excluded. Cancelled [run 32740699426](https://github.com/ttokunaga-ja/kio/actions/runs/32740699426) is the separate 45-minute Windows-timeout diagnostic and is ineligible for successful-cost arithmetic.
