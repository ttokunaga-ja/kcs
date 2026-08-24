# Current five-job CI critical path

The canonical measurements are in
[`ci-cost-baseline.json`](ci-cost-baseline.json), and the signal/duplication
ledger is [`ci-cost-unique-signal.md`](ci-cost-unique-signal.md). All values
are cohort-bound. The current immutable GitHub-success cohort is
`4f49cce...` / tree `5816125...` / workflow blob `bdc01e2...`; the
final-candidate clean-Linux cold/warm cohort remains separately bound to
`d66b958...` / `8ef044c...`. The older `f50e8cc...` / tree
`477a8d9...` and superseded `2c7db5d...` / tree `7ea87a6...` measurements
remain historical and are not relabeled. Earlier Phase C local values refer
to `2a85016...` / tree `49e4887...` / workflow `049c69c...`; GitHub attempt 1
refers to `c9f334e...` / workflow `049c69c...`. They are not combined.

Status: the current immutable GitHub-success cohort has `n=1`, including the
Windows measurement. Formal current-CI baseline acceptance remains
**provisional**: one success is not a distribution or continuous-SLO result.

## Prior Phase C selected measurements

These cold successful local samples belong only to the earlier Phase C product
tree. Runner-equivalent minutes are wall seconds divided by 60; they are not
GitHub billing minutes. No warm rerun was performed for this prior cohort.

| Job | Cold wall | Cold runner-equivalent | Result and use |
| --- | ---: | ---: | --- |
| `rust` | 1,316.53 s | 21.942167 min | success; cold selected |
| `persona-w0-integration` | 152.38 s | 2.539667 min | success; cold selected |
| `synthetic-history-eval` | 91.32 s | 1.522000 min | success; cold selected |
| `macos-security-r23` | 890.18 s | 14.836333 min | success; cold selected |
| `windows-security-r23` | unknown | unknown | no matching GitHub run or Windows measurement |

The observed known successful subset is 2,450.41 seconds = **40.840167
runner-equivalent minutes**. It is not the whole workflow: Windows is unknown.

## Formula and result

The workflow dependency contract gives:

```text
max(
  rust + synthetic-history-eval,
  persona-w0-integration,
  macos-security-r23,
  windows-security-r23
)
```

Using only the prior Phase C successful-cold operands:

```text
rust + synthetic-history-eval = 21.942167 + 1.522000 = 23.464167
persona-w0-integration        = 2.539667
macos-security-r23            = 14.836333
windows-security-r23          = unknown
overall critical path         = unknown
```

This prior cohort's overall aggregate runner-equivalent time is also **unknown**
because its Windows operand is unknown. Unknown values are never zero-filled.

## Current immutable GitHub-success measurement

Run [`32698672753`](https://github.com/ttokunaga-ja/kio/actions/runs/32698672753)
is `CI` / `push` / attempt `1` / `success` for head
`4f49cce01a4fd614066f772ac9b10070a12dfd24`, tree
`5816125ba27beeac062b424d9ddfbb552df77df5`, workflow blob
`bdc01e224cf952148910b6a6200b9ac1e451dd9e`, Rust `1.98.0`, and the five-job
topology. It is a separate immutable cohort, not a relabeling of the local or
failure data.

| Job | Started | Completed | Elapsed |
| --- | --- | --- | ---: |
| `rust` | 06:46:19Z | 07:00:04Z | 13:45 |
| `persona-w0-integration` | 06:46:19Z | 06:50:15Z | 03:56 |
| `synthetic-history-eval` | 07:00:08Z | 07:04:15Z | 04:07 |
| `macos-security-r23` | 06:46:20Z | 07:11:24Z | 25:04 |
| `windows-security-r23` | 06:46:22Z | 07:16:42Z | 30:20 |

The run began at `2026-08-24T06:46:16Z` and completed at
`2026-08-24T07:16:42Z`: 30:26 wall-clock. Aggregate elapsed is
825 + 236 + 247 + 1,504 + 1,820 = 4,632 seconds = 77:12 = 77.2
runner-equivalent minutes, not billing minutes. The overall critical path is
Windows: 1,820 seconds = 30:20. The required dependency path is
825 + 4-second handoff + 247 = 1,076 seconds = 17:56.

GitHub exposed no internal queue, billing, CPU, RSS, byte I/O, or cache
telemetry; these values are null/unknown and not zero-filled. No job failed,
cancelled, skipped, or was downstream-skipped.

## Phase F configured finite bounds

The current workflow applies these job-level caps:

```text
rust                         = 35 min
persona-w0-integration       = 15 min
synthetic-history-eval       = 10 min (needs rust)
macos-security-r23           = 35 min
windows-security-r23         = 45 min
configured dependency cap    = rust + synthetic = 45 min
configured aggregate cap     = 35 + 15 + 10 + 35 + 45 = 140 min
```

These are termination bounds, not runtime measurements, queue time, or billing
minutes. The immutable success cohort above separately measures Windows at
30:20; a future cohort's runtime must be measured rather than inferred from its
finite 45-minute cap.

## Final-candidate measured Linux operand and path estimate

At exact product head `d66b958...`, tree `8ef044c...`, and workflow blob
`bdc01e2...`, the clean Linux workspace-test command succeeded cold in
**434.42 seconds = 7.240333 minutes** and warm in **378.37 seconds = 6.306167
minutes**. Both covered 49 result blocks and 2,220 passed tests with zero
failures or ignored tests. The cold/warm pair covers only:

```text
cargo +1.98.0 test --workspace --all-targets --locked --no-fail-fast
```

Every over-60-second progress warning—15 cold and 19 warm—later terminated
`ok`. These warnings do not represent missing results or infinite waits. The
failed pre-fix `57819593...` cold attempt is excluded: it exposed an inherited
flock race, after which historical `2c7db5d...` passed 200 repeated parallel `kio-core`
suite runs. Final `d66b958...` then added readiness-driven bounded-stdin draining,
and the successful pair above measures that final tree.

The latest topology-identical exact workflow-order operands remain attached to
the separate `f50e8cc...` cohort:

```text
historical rust fmt                  =   1.13 s
historical rust clippy               =  13.99 s
current exact cold workspace test    = 434.42 s
historical synthetic command lane    =  83.99689 s
mixed-cohort planning estimate       = 533.53689 s = 8.892282 min
```

The estimate is below the 40-minute local target with 31.107718 minutes of
margin and below the 45-minute GitHub reference with 36.107718 minutes of
margin. It is deliberately labelled a planning estimate: it is not a same-run
measurement, upper-bound guarantee, GitHub workflow result, queue/billing
sample, or successful-current baseline.

For historical comparison only, the exact `f50e8cc...` workflow sequence was
426.38 seconds for `rust` and 83.99689 seconds for synthetic, or 8.506281
minutes along the dependency path; its independent Persona W0 lane was
2.304598 minutes. The `f50e8cc...` clean/warm workspace-test pair was
394.88/329.78 seconds for 2,216 passed. Host load and later product tests differ,
so these values are preserved rather than interpreted as a formal before/after
percentage.

The successful-current GitHub critical path is 30:20 and five-job aggregate is
77:12 runner-equivalent. The finite configured dependency cap is 45 minutes and
configured aggregate cap is 140 minutes; caps are termination configuration,
not measured runtime. Current macOS and Windows cost operands are recorded in
the immutable success cohort; unknown telemetry is never treated as zero.

## Matching GitHub attempt 1 (failure cohort)

GitHub run [`32626254306`](https://github.com/ttokunaga-ja/kio/actions/runs/32626254306)
is the first matching `CI` / `push` / attempt `1` observation for head
`c9f334e957863e1c6daf8f54cc1b917a8e0ae07a` and workflow blob
`049c69c0e867d74c49535a74543510460ca70615`. It is retained separately because
its conclusion was `failure`; it contributes zero successful samples.

```text
workflow wall                         = 55:06 (3,306 s)
aggregate job elapsed                 = 83:41 (5,021 s)
rust + synthetic-history-eval         = 50:53 + 04:06 = 54:59
persona-w0-integration                = 03:12
macos-security-r23                    = 23:45 (failure)
windows-security-r23                  = 01:45 (compile failure; tests not run)
matching successful sample count      = 0 for this failure cohort
```

The macOS and Windows failures were independent. `rust` succeeded, so its
dependent synthetic job ran; no job was downstream-skipped. The 54:59 failure
cohort path and 83:41 aggregate are diagnostic elapsed values, not successful
cost operands and not billing minutes. GitHub internal queue, billing, CPU,
RSS, I/O, and cache telemetry were unavailable and remain unknown.

## 45-minute and 250-minute targets

- Critical path target: 45 minutes — **pass for the one current success run**:
  its overall measured critical path is Windows at 30:20. This is a single-run
  comparison, not a distribution or continuous-SLO claim. Attempt 1 observed
  54:59 under the older workflow, failed, and remains a separate cohort. The
  Phase F workflow's configured `rust + synthetic` cap is configuration, not a
  measured result.
- Final-candidate local Linux dependency-path planning estimate: 8.892282
  minutes — **below the 40-minute local planning target**, but mixed-cohort and
  not a GitHub acceptance sample.
- Aggregate runner-equivalent target: 250 minutes — **pass for the one current
  success run**: 77:12 (77.2 minutes). This is elapsed runner-equivalent time,
  not billing minutes, and is not a continuous-SLO claim. Attempt 1 observed
  83:41 before its independent failures, but failure cost remains excluded from
  successful cost.
- Final-candidate exact cold workspace-test operand: 7.240333 minutes — one
  command only, insufficient to declare either the complete Rust job or the
  five-job aggregate.
- Historical `f50e8cc...` local known Linux subset: 10.810880 minutes — three
  successful job command lanes only; context, not current aggregate evidence.
- Prior Phase C observed known subset: 40.840167 minutes — context only,
  insufficient to declare aggregate success.
- Prior Phase C known complete branch maximum: 23.464167 minutes — context only,
  insufficient to declare critical-path success.
- Phase F configured aggregate timeout cap: 140 minutes — finite configuration,
  not measured runner time and not GitHub billing time.

## Evidence and limits

The prior and final-candidate local samples came from isolated validation at
their exact product trees. Their raw evidence is ephemeral and non-authorizing;
the acquisition method, per-binary values, and SHA-256 evidence digests are
recorded in [`ci-cost-baseline.json`](ci-cost-baseline.json). The current
immutable cohort has one matching GitHub attempt and one matching successful
run. The recorded older-workflow attempt remains a separate failure cohort.
GitHub queue and billing remain unknown, while current Windows wall time and
successful-current overall values are recorded above.

There is no workflow cache action and no persisted-artifact action. Local warm
reuse is not a current GitHub saving. Phase F preserves the five-job topology
while changing finite timeout caps and the ordinary/manual Full-test split.

## Formal remeasurement condition

Formal acceptance requires successful GitHub runs of workflow blob
`bdc01e224cf952148910b6a6200b9ac1e451dd9e` that preserve the five-job
topology, Rust 1.98.0, dependency, flags, tiny fixture, Rust persona path, and
Rust evaluator path. Collect additional matching successful runs up to 10.
Queue and billing remain unknown unless GitHub exposes usable values. Old
29-job, old-workflow, Rust 1.97, Python
evaluator, failure, and cancelled runs must not fill any gap.
