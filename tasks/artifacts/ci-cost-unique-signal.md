# Current five-job CI unique-signal ledger

This ledger describes the workflow at measured revision
`dd1a60018c6e188654eac83685e0c1fd2ad412fb`. The machine-readable source of
truth is [`ci-cost-baseline.json`](ci-cost-baseline.json); the current workflow
is [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml).

The measurement package is complete, but formal current-CI baseline acceptance
is provisional. GitHub has no successful run matching this workflow blob and
topology, the Linux `rust` command group is not green in the isolated local
equivalent, and Windows remains unmeasured.

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
each execution covers OS-specific compilation, filesystem, process, and security
behavior.

## Duplication accounting

The workflow has 32 `run` steps: 3 in `rust`, 9 in
`persona-w0-integration`, 18 in `synthetic-history-eval`, and one in each
platform job. The workspace test command occurs three times.

- Duplicate-group coverage is `3 / 32 = 9.375%` of run steps.
- Counting the first instance as necessary, excess command copies are
  `(3 - 1) / 32 = 6.25%` of run steps.
- Within that one logical command group, `2 / 3 = 66.667%` are additional
  platform executions.
- Time-weighted duplication is unknown: Linux has no successful current sample
  and Windows has no current sample. Unknown values are not treated as zero.

There is no workflow cache action and no upload/persisted-artifact action. Cargo
registries, build outputs, generated persona material, and synthetic fixtures
are therefore either runner-local cache candidates or ephemeral job outputs,
not reusable evidence in the current workflow.

## Current Linux failure signal

The exact `rust` command group reached `cargo test` in an isolated Linux
container and exited `101`. Seven `kio-eval` library tests failed: two
snapshot-rebase cases, the dyld shared-cache catalog case, a private-executable
replacement case, the fixture-B mock, and two U7 adapter lifecycle cases. The
dyld test unconditionally reaches a sealed-macOS-runtime requirement on Linux,
and the U7 tests use `/bin/sh` while the Linux image exposes it as a symlink that
the adapter boundary deliberately rejects. Some remaining failures may depend
on Docker Desktop's arm64 bind filesystem and must be confirmed on GitHub's
Ubuntu runner. This is a local platform/test-contract failure, not a successful
cost sample and not a measurement-wrapper failure.

Because `synthetic-history-eval` needs `rust`, GitHub would skip that downstream
job after this failure. Its independent local measurement remains useful only
as provisional cost evidence for the command group after the prerequisite is
made green.

## Phase 6 candidates — not implemented here

1. Treat a green Linux `rust` suite as a prerequisite to CI optimization. The
   platform/test-contract repair needs separate authorization and is not part
   of this measurement-only phase.
2. After current GitHub runs exist, compare the time share of the three full
   workspace-test executions. Consider focused OS-specific suites only if they
   preserve the distinct macOS and Windows failure modes above.
3. Evaluate an explicit Cargo dependency/target cache and build-output reuse.
   Local warm results show what may be reusable, but a cache key, restore cost,
   and GitHub hit rate have not been measured.
4. Preserve the persona and synthetic lanes as distinct gates. Their lifecycle
   and recall signals are not supplied by the generic workspace suite.
5. Keep the existing `rust -> synthetic-history-eval` dependency unless current
   GitHub evidence shows that its fail-fast saving is outweighed by critical-path
   cost.

No workflow reorganization, product change, new job, cache action, or artifact
upload was made in Phase B.
