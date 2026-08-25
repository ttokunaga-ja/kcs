# Current five-job CI unique-signal ledger

[Run 32848763996](https://github.com/ttokunaga-ja/kio/actions/runs/32848763996) is the exact current cohort (`n=1`): successful `CI` / natural `push` / attempt `1`, tested HEAD `049288af26515edba125925a7f496fe77a8ff90f`, tree `25975f5da1a8e39f999e1282600d2ebc088a2f70`, workflow blob `07ae8f90747c9bce4e0d9508af2a967ffd8bbed6`, Rust `1.98.0`, five jobs, and runner contract `ubuntu-latest`, `ubuntu-latest`, `ubuntu-latest`, `macos-latest`, `windows-latest`. The machine-readable source is [ci-cost-baseline.json](ci-cost-baseline.json). This single success is not a distribution or a continuous-SLO result.

| Job | Unique signal | Failure signal |
| --- | --- | --- |
| `rust` | Ubuntu format, warnings-denied lint, and complete workspace/all-target tests | format, lint, or workspace test exits nonzero |
| `persona-w0-integration` | Rust Tiny persona lifecycle, create-only preservation, leases, and filesystem attestation | rematerialization, hashes, lease coordination, or attestation claims disagree |
| `synthetic-history-eval` | release/all-features scale, history, cross-scope, rerank, and M3 recall gates | any command fails, rerank cannot apply, or M3-1 recall is below `0.9166666666666666` |
| `macos-security-r23` | complete workspace/all-target tests under macOS semantics | any workspace test exits nonzero on macOS |
| `windows-security-r23` | complete workspace/all-target tests under Windows portability and security semantics | any workspace test exits nonzero on Windows |

The platform test invocations use similar Cargo text but are noninterchangeable OS evidence. Only a demonstrated duplicate signal may be consolidated; scale, history, and cross-platform gates remain when they add a distinct signal.

All five jobs succeeded in 31:41 wall-clock. Aggregate job elapsed was 5,179 seconds = 86:19 = 86.316667 runner-equivalent minutes, not GitHub billing time. The observed longest job was Windows at 31:37; the `rust -> synthetic-history-eval` dependency path took 29:10.

GitHub internal queue, billing, CPU, RSS, byte I/O, and cache telemetry are unavailable and remain null/unknown rather than zero. The run is below the stated 45-minute workflow-wall and 250-minute aggregate runner-equivalent references only as a single run. Do not optimize a timeout or declare an SLO until at least three natural push successes match the exact topology, toolchain, flags, and runner contract.

Any later docs-only Phase A recording commit is not itself measured. The exact sample remains bound to tested HEAD `049288af26515edba125925a7f496fe77a8ff90f`; product, test, and workflow blobs remain unchanged in the follow-on record.

Prior successful run 32747140652 and cancelled run 32740699426 remain historical, topology-different or unsuccessful context only; neither increments this cohort.
