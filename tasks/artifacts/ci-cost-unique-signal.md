# Latest observed five-job CI unique-signal ledger

[Run 32890496534](https://github.com/ttokunaga-ja/kio/actions/runs/32890496534) is the latest exact success observed at the record's capture time (`n=1`): successful `CI` / natural `push` / attempt `1`, tested HEAD `55b87e05bc59adbfa33d80af02de37e7fda3de95`, tree `39f738fd4a6b8cfe5d5ba72e729c4fdf10fb9570`, workflow blob `07ae8f90747c9bce4e0d9508af2a967ffd8bbed6`, Rust `1.98.0`, five jobs, and runner contract `ubuntu-latest`, `ubuntu-latest`, `ubuntu-latest`, `macos-latest`, `windows-latest`. The machine-readable source is [ci-cost-baseline.json](ci-cost-baseline.json). The label is time-fixed to that run and does not claim that a later commit is measured, a distribution, or a continuous-SLO result.

| Job | Unique signal | Failure signal |
| --- | --- | --- |
| `rust` | Ubuntu format, warnings-denied lint, and complete workspace/all-target tests | format, lint, or workspace test exits nonzero |
| `persona-w0-integration` | Rust Tiny persona lifecycle, create-only preservation, leases, and filesystem attestation | rematerialization, hashes, lease coordination, or attestation claims disagree |
| `synthetic-history-eval` | release/all-features scale, history, cross-scope, rerank, and M3 recall gates | any command fails, rerank cannot apply, or M3-1 recall is below `0.9166666666666666` |
| `macos-security-r23` | complete workspace/all-target tests under macOS semantics | any workspace test exits nonzero on macOS |
| `windows-security-r23` | complete workspace/all-target tests under Windows portability and security semantics | any workspace test exits nonzero on Windows |

The platform test invocations use similar Cargo text but are noninterchangeable OS evidence. Only a demonstrated duplicate signal may be consolidated; scale, history, and cross-platform gates remain when they add a distinct signal.

All five jobs succeeded in 1,659 seconds = 27:39 wall-clock. Aggregate job elapsed was 4,927 seconds = 82:07 = 82.116667 runner-equivalent minutes, not GitHub billing time. The observed longest individual job was Windows at 1,618 seconds = 26:58; the `rust -> synthetic-history-eval` dependency path took 1,655 seconds = 27:35.

GitHub internal queue, billing, CPU, RSS, byte I/O, and cache telemetry are unavailable and remain null/unknown rather than zero. The run is below the stated 45-minute workflow-wall and 250-minute aggregate runner-equivalent references only as a single run. Do not optimize a timeout or declare an SLO until at least three natural push successes match the exact topology, toolchain, flags, and runner contract.

The exact observation remains bound to tested HEAD `55b87e05bc59adbfa33d80af02de37e7fda3de95` and tree `39f738fd4a6b8cfe5d5ba72e729c4fdf10fb9570`. Its recording commit and every later commit are unmeasured until a distinct exact cohort exists.

Previous exact-success run 32848763996 at HEAD `049288af26515edba125925a7f496fe77a8ff90f`, failed run 32884825839, prior topology-different success 32747140652, and cancelled run 32740699426 remain historical context only; none increments this observation.
