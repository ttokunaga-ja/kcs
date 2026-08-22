# Current five-job CI unique-signal ledger

This ledger describes the workflow at measured revision
`2a85016fe29421ceafa28924f43ec39bc497d23e`, tree
`49e48877971d8c4369da17610f299c693361ab1b`, and workflow blob
`049c69c0e867d74c49535a74543510460ca70615`. The machine-readable source of
truth is [`ci-cost-baseline.json`](ci-cost-baseline.json); the current workflow
is [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml).

The Phase C measurement package is complete. Formal current-CI baseline
acceptance remains provisional: GitHub has zero matching current runs, and the
Windows job, queue time, and billing minutes are unknown.

## Signal carried by each job

| Job | Dependency | Unique signal | Job-specific failure signal |
| --- | --- | --- | --- |
| `rust` | none | Ubuntu formatting, linting with warnings denied, and the complete workspace/all-target Rust suite | `cargo fmt`, Clippy, or any workspace test exits nonzero |
| `persona-w0-integration` | none | End-to-end Rust persona plan, schedule, render, materialization, scaffold, lease lifecycle, and filesystem-attestation behavior | create-only rematerialization succeeds, any of four hashes changes, lease coordination fails, or attestation schema/claims differ |
| `synthetic-history-eval` | `rust` | Release/all-features binaries plus scale-tiny, synthetic history, cross-scope, rerank, and M3 recall gates | any fixture/evaluator command fails, fixture rerank cannot apply, or the short M3-1 recall is below `0.9166666666666666` |
| `macos-security-r23` | none | The complete workspace/all-target test suite under macOS security and filesystem semantics | any workspace test exits nonzero on macOS |
| `windows-security-r23` | none | The complete workspace/all-target test suite under Windows portability and security semantics | any workspace test exits nonzero on Windows |

The three platform jobs invoke the exact same `cargo test --workspace
--all-targets --locked` text, but they do not carry interchangeable evidence:
each execution covers OS-specific compilation, filesystem, process, and
security behavior.

## Duplication accounting

The workflow has 32 `run` steps: 3 in `rust`, 9 in
`persona-w0-integration`, 18 in `synthetic-history-eval`, and one in each
platform job. The workspace test command occurs three times.

- Duplicate-group coverage is `3 / 32 = 9.375%` of run steps.
- Counting the first instance as necessary, excess command copies are
  `(3 - 1) / 32 = 6.25%` of run steps.
- Within that one logical command group, `2 / 3 = 66.667%` are additional
  platform executions.
- Time-weighted duplication is unknown because Windows is unknown; unknown is
  not treated as zero.

There is no workflow cache action and no upload/persisted-artifact action.
Cargo registries, build outputs, generated persona material, and synthetic
fixtures are therefore either runner-local cache candidates or ephemeral job
outputs, not reusable evidence in the current workflow.

## Current cost evidence

Successful cold local samples only are the provisional cost basis. Mandatory
validation was reused as the measurement; no warm rerun was made, avoiding a
duplicate high-cost execution. The raw evidence is ephemeral and non-authorizing;
the retained acquisition record is its isolated cold-validation method and the
two manifest digests in [`ci-cost-baseline.json`](ci-cost-baseline.json).

Linux `rust`, persona, and synthetic jobs and macOS workspace tests are green
in their measured local equivalents. Windows remains unmeasured, so this does
not establish an overall critical path, total, or threshold result.

## Non-current historical asset

`tasks/artifacts/ci-cost-baseline-2026-08-12.json` was deleted: it had zero
live consumers and was historical-only. It is recoverable from Git commit
`11a4147e0d5972ef0f7325ac61efb6ad9a3f7345`; no archive, stub, or redirect was
kept.

## Phase C boundary

No workflow reorganization, product change, new job, cache action, or artifact
upload was made. The five-job topology and its distinct signal lanes remain
unchanged. Formal remeasurement requires matching successful GitHub runs and a
Windows measurement; queue and billing remain unknown unless GitHub exposes
usable values.
