# Current five-job CI critical path

The canonical measurements are in
[`ci-cost-baseline.json`](ci-cost-baseline.json), and the signal/duplication
ledger is [`ci-cost-unique-signal.md`](ci-cost-unique-signal.md). All values
refer to product commit `2a85016fe29421ceafa28924f43ec39bc497d23e`, tree
`49e48877971d8c4369da17610f299c693361ab1b`, and workflow blob
`049c69c0e867d74c49535a74543510460ca70615`.

Status: the measurement package is complete; formal current-CI baseline
acceptance is **provisional / GitHub and Windows confirmation pending**.

## Selected measurements

Cold successful local samples are the provisional cost basis because the
workflow has no cache action. Runner-equivalent minutes are wall seconds divided
by 60; they are not GitHub billing minutes. Mandatory validation was reused as
the measurement, so no warm rerun was performed.

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

Using successful-cold operands:

```text
rust + synthetic-history-eval = 21.942167 + 1.522000 = 23.464167
persona-w0-integration        = 2.539667
macos-security-r23            = 14.836333
windows-security-r23          = unknown
overall critical path         = unknown
```

The overall aggregate runner-equivalent time is also **unknown** because the
Windows operand is unknown. Unknown values are never zero-filled.

## 45-minute and 250-minute targets

- Critical path target: 45 minutes — **unknown**, because the Windows branch
  is missing.
- Aggregate runner-equivalent target: 250 minutes — **unknown**, because the
  Windows job is missing.
- Observed known subset: 40.840167 minutes — context only, insufficient to
  declare aggregate success.
- Known complete branch maximum: 23.464167 minutes — context only,
  insufficient to declare critical-path success.

## Evidence and limits

The selected samples come from isolated local cold validation at the exact
product tree. Their raw evidence is ephemeral and non-authorizing; only the
acquisition method and SHA-256 evidence-manifest digests are recorded in
[`ci-cost-baseline.json`](ci-cost-baseline.json). GitHub matching current runs
remain zero. GitHub queue time and billing minutes are unknown, as are Windows
wall time and all resulting overall values.

There is no workflow cache action and no persisted-artifact action. Warm local
reuse is not a current GitHub saving and was deliberately not rerun. No workflow
topology or signal lane changed in Phase C.

## Formal remeasurement condition

Formal acceptance requires successful GitHub runs that preserve the same
workflow blob/topology, Rust 1.98.0, dependency, flags, tiny fixture, Rust
persona path, and Rust evaluator path, plus a matching Windows value. Collect
the available successful runs up to 10. Queue and billing remain unknown unless
GitHub exposes usable values. Old 29-job, Rust 1.97, Python evaluator, failure,
and cancelled runs must not fill any gap.
