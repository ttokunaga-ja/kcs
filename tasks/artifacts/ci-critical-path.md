# Current five-job CI critical path

The canonical measurements are in
[`ci-cost-baseline.json`](ci-cost-baseline.json), and the signal/duplication
ledger is [`ci-cost-unique-signal.md`](ci-cost-unique-signal.md). All values here
refer to workflow blob `049c69c0e867d74c49535a74543510460ca70615` at
measured tree `6a645072002fbe7ac08fa3e381c78f956c6e9e71`.

Status: the measurement package is complete; formal current-CI baseline
acceptance is **provisional / GitHub confirmation pending**.

## Selected measurements

Cold successful local samples are the provisional cost basis because the
workflow has no cache action. Runner-equivalent minutes are wall seconds divided
by 60; they are not GitHub billing minutes.

| Job | Cold wall | Warm wall | Cold runner-equivalent | Result and use |
| --- | ---: | ---: | ---: | --- |
| `rust` | 1,335.65 s | not run | — | exit 101 after 22.260833 min; diagnostic time-to-failure only |
| `persona-w0-integration` | 160.01 s | 119.40 s | 2.666833 min | success; cold selected |
| `synthetic-history-eval` | 99.29 s | 33.39 s | 1.654833 min | success when run independently; GitHub would currently skip it after `rust` fails |
| `macos-security-r23` | 885.97 s | 822.72 s | 14.766167 min | success; cold selected |
| `windows-security-r23` | unknown | unknown | unknown | no matching GitHub run or Windows measurement |

The successful cold subset totals 1,145.27 seconds = **19.087833
runner-equivalent minutes**. Its warm counterpart totals 975.51 seconds =
16.258500 minutes, a 14.823% local reduction. This subset is not the whole
workflow and is not a threshold pass.

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

Using successful-cost operands:

```text
rust + synthetic-history-eval = unknown + 1.654833 = unknown
persona-w0-integration        = 2.666833
macos-security-r23            = 14.766167
windows-security-r23          = unknown
overall critical path         = unknown
```

The maximum among complete observed branches is 14.766167 minutes, but it is
not the overall maximum because two branches are incomplete. Unknown operands
are not zero-filled.

The overall aggregate runner-equivalent time is also **unknown**: `rust` has no
successful local cost and Windows has no current measurement. The independently
measured successful subset is reported separately above.

## Failure-path diagnostic

The Linux `rust` cold run spent 1,335.65 seconds before seven `kio-eval` tests
failed. In a workflow run, that failure would skip `synthetic-history-eval` while
the persona and platform jobs remain independent. The known local runner work
for `rust` failure + persona cold + macOS cold is 2,381.63 seconds = 39.693833
minutes; Windows is still unknown, so this is neither a complete failure-waste
total nor successful cost.

No current GitHub failure/cancelled run matches the five-job contract. The five
recent failure/cancelled runs belong to the old 29-job workflow and are excluded
from current waste arithmetic.

## Resource observations

| Job/sample | CPU user / system | Peak RSS observation | Cache/output observation |
| --- | ---: | ---: | --- |
| `rust` cold failure | 4,847.27 / 386.42 s | 4,695,449,600 B max-process; 12,267,044,864 B cgroup peak | 9,318,190,312 B target; 46,812,869 B `/tmp` |
| persona cold | 201.93 / 35.96 s | 1,298,083,840 B max-process; 2,891,530,240 B cgroup peak | 1,962,132,763 B target; 10,328,388 B `/tmp` |
| persona warm | 116.73 / 1.14 s | 63,713,280 B max-process; 161,931,264 B cgroup peak | same target; 25.380% wall saving |
| synthetic cold | 364.59 / 53.98 s | 1,448,878,080 B max-process; 2,756,681,728 B cgroup peak | 540,070,401 B target; 95,896,006 B `/tmp` |
| synthetic warm | 14.27 / 10.50 s | 97,345,536 B max-process; 250,646,528 B cgroup peak | same target; 66.371% wall saving |
| macOS cold | 3,468.60 / 349.13 s | 3,998,351,360 B BSD-time max descendant | 3,834,449,920 B allocated target |
| macOS warm | 3,239.98 / 319.84 s | 4,106,059,776 B BSD-time max descendant | same allocated target; 7.139% wall saving |
| Windows | unknown | unknown | unknown |

Linux cgroup I/O was recorded, but Docker Desktop bind-mount writes are not
fully represented by those counters. macOS byte I/O was unavailable; BSD
`time` reported zero block operations, and target capacity came from allocated
KiB reported by `du -sk`. GitHub CPU, RSS, byte I/O, internal queue, and usable
billing minutes were unavailable and remain `null` in the JSON.

The workflow has no cache action and no persisted-artifact action. Local warm
measurements reuse a target directory that GitHub jobs do not currently share,
so warm savings are opportunity evidence, not current GitHub savings.

## 45-minute and 250-minute targets

- Critical path target: 45 minutes — **unknown**, because the Linux success path
  and Windows branch are missing.
- Aggregate runner-equivalent target: 250 minutes — **unknown**, because the
  same values are missing.
- Observed successful subset: 19.087833 minutes — numerically below 250, but
  insufficient to declare aggregate success.
- Complete observed branch maximum: 14.766167 minutes — numerically below 45,
  but insufficient to declare critical-path success.

## Formal remeasurement condition

Formal acceptance requires separately authorized work to make the current Linux
`rust` command group green, followed by successful GitHub runs that preserve the
same workflow blob/topology, Rust 1.98.0, dependency, flags, tiny fixture, Rust
persona path, and Rust evaluator path. Collect the available successful runs up
to 10, plus a matching Windows value. Queue and billing remain unknown unless
GitHub exposes usable values. Old 29-job, Rust 1.97, Python evaluator,
failure, and cancelled runs must not fill any gap.
