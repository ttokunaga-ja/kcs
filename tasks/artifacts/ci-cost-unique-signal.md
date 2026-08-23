# Current five-job CI unique-signal ledger

This ledger keeps the cohorts separate. The current product changes end at
`2c7db5de3251eb6fb9630731cd987aa09439e6fb`, tree
`7ea87a6d07a62a85dff3cfcb7e33af0a70ddbd30`, and use workflow blob
`bdc01e224cf952148910b6a6200b9ac1e451dd9e`. The final-candidate clean-Linux
cold/warm cohort is bound to that same product head/tree. The earlier
`f50e8cc...` / `477a8d9...` pair remains a separate historical cohort. The candidate
commit containing this evidence is resolved with
`git log -1 --format=%H -- tasks/artifacts/ci-cost-baseline.json`; a commit
cannot contain its own SHA.
Earlier Phase C local measurements refer to product commit `2a85016...`, while
GitHub attempt 1 refers to head `c9f334e...` and older workflow blob
`049c69c...`. Values are never merged across those identities. The
machine-readable source of truth is
[`ci-cost-baseline.json`](ci-cost-baseline.json); the current workflow is
[`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml).

The local measurement package is complete only after the Phase F cold/warm
record below. Formal current-CI baseline acceptance remains provisional: the
current Phase F candidate has no GitHub run and therefore zero matching
successful runs. Prior attempt 1 failed independently on macOS and Windows; a
successful Windows test measurement, queue time, and billing minutes remain
unknown.

## Signal carried by each job

| Job | Dependency | Unique signal | Job-specific failure signal |
| --- | --- | --- | --- |
| `rust` | none | Ubuntu formatting, linting with warnings denied, the complete workspace/all-target Rust suite, and compilation of the manual Full example | `cargo fmt`, Clippy, example compilation, or any workspace test exits nonzero |
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

## Cohort-separated cost evidence

The successful cold local values retained from Phase C belong only to product
commit `2a85016...` and workflow blob `049c69c...`. They are historical context,
not a cost sample for the Phase F candidate. Their raw evidence is ephemeral and
non-authorizing; the retained acquisition record is its isolated measurement
method and two manifest digests in
[`ci-cost-baseline.json`](ci-cost-baseline.json).

Linux `rust`, persona, and synthetic jobs and macOS workspace tests are green
in their measured local equivalents. Windows remains without a successful test
measurement, so this does not establish an overall critical path, total, or
threshold result.

The prior GitHub observation is failure cohort
`workflow=CI / event=push / head=c9f334e957863e1c6daf8f54cc1b917a8e0ae07a /
workflow_blob=049c69c0e867d74c49535a74543510460ca70615 / attempt=1`, run
[`32626254306`](https://github.com/ttokunaga-ja/kio/actions/runs/32626254306).
It is diagnostic evidence, not a successful cost sample:

| Job | Result | Elapsed | Signal observed |
| --- | --- | ---: | --- |
| `rust` | success | 50:53 | all Linux format/lint/workspace gates completed |
| `persona-w0-integration` | success | 03:12 | complete Rust persona W0 lifecycle |
| `synthetic-history-eval` | success | 04:06 | dependent release/history/scale/rerank/M3 lane |
| `macos-security-r23` | failure | 23:45 | host-dependent dyld-cache test failed after the portable suite ran |
| `windows-security-r23` | failure | 01:45 | seven compile errors; tests did not start |

Workflow wall was 55:06, aggregate elapsed was 83:41 runner-equivalent,
and the `rust -> synthetic-history-eval` elapsed critical path was 54:59.
There were no downstream skips: `rust` succeeded, so `synthetic-history-eval`
ran. Failure elapsed is never mixed into successful cost, and the matching
success count remains `n=0`. GitHub did not expose internal queue, billing,
CPU, RSS, I/O, or cache values; each remains unknown rather than zero.

The complete Rust job log is 518,323 bytes / 3,418 lines with SHA-256
`2b6e7084a9b5fd90d7fbb614e43a091d71e7d1d8626a5429b834c7def8355c5c`.
It has no truncation marker and includes post-checkout cleanup and job
completion. The exact 30-name machine-readable list and conservative wall lower
bounds are recorded in [`ci-cost-baseline.json`](ci-cost-baseline.json).

## Attempt 1 slow-test classification

The Linux test harness emitted 30 over-60-second warnings and later emitted
`ok` for all 30; none was ignored, failed, or left unterminated. The wall values
below are lower bounds reconstructed as 60 seconds plus warning-to-completion
time. GitHub supplied no per-test CPU, RSS, or I/O telemetry, so those values
are unknown. “Dominant path” is a code-path classification, not measured host
telemetry.

| Group | Warnings | Maximum observed wall lower bound | Fixture / dominant path | Unique signal and disposition |
| --- | ---: | ---: | --- | --- |
| `persona_attest` | 7 | 279.514 s | Tiny; repeated plan -> schedule -> render -> materialize, descriptor rechecks and durable create-only publication | retain mutation/TOCTOU classes per fresh root; share only immutable canonical input bytes |
| `persona_consumer` | 2 | 971.851 s | Tiny/Pilot/Full; Full is 195,000 sources / 2,400,000 chunks, canonical serialization, hashing, and temp-file reads | keep Tiny/Pilot identity, parser, binding, and cross-plan rejection; move duplicate Full downstream generation to the explicit manual lane |
| `persona_lease` | 8 | 1,802.368 s | Tiny workspace; locks, descriptor rechecks, file/directory `fsync`, including 32 claim/release cycles | keep lifecycle and fault signals; replace arbitrary repetition with a direct workspace-FD invariant |
| `persona_materialize` | 7 | 74.766 s | Tiny; create-only staged writes, file/directory `fsync`, rename and post-publication recheck | retain distinct publication/fault signals per fresh root; share immutable inputs |
| `persona_render` | 1 | 90.464 s | Tiny; bounded all-variant rendering and canonical computation | retain in normal CI |
| `persona_render_artifact` | 1 | 378.027 s | Tiny/Pilot/Full; Full 195,000-row artifact serialization and hashing | retain Tiny/Pilot bounds in normal CI; validate Full once in the manual Rust command |
| `persona_scaffold` | 2 | 96.094 s | Tiny/Pilot/Full; bounded topology creation, retained-directory validation and sync | retain Tiny/Pilot topology plus opaque-payload signal; remove duplicate Full topology generation |
| `persona_schedule` | 1 | 211.019 s | Tiny/Pilot/Full; Full history/event projection and repeated canonical serialization | retain Tiny/Pilot deterministic/parser signal; validate Full suite digest once manually |
| `app` | 1 | 86.881 s | Tiny Rust CLI persona lifecycle and create-only artifacts | retain as the public command-surface integration signal |

The categories overlap while tests run in parallel, so their maxima must not be
summed into job wall time. CPU-bound serialization, filesystem durability, and
parallel disk/`OnceLock` contention are plausible code-path explanations only;
the runner did not expose enough telemetry to apportion measured CPU or I/O.

## Phase F signal consolidation

Ordinary CI now has one Full plan/source-projection authority:
`persona_plan::tests::profiles_are_deterministic_and_semantically_complete`.
It still checks Tiny, Pilot, and Full frozen digests, source/chunk totals, cohort
feasibility, and structural event identities/dependencies. Duplicate standalone
cohort and structural tests were deleted. Secondary consumer, schedule,
render-artifact, and scaffold tests retain Tiny/Pilot behavior but no longer
regenerate the Full fixture.

The one-pass Full schedule/render signal is owned by this explicit manual Rust
command:

```sh
cargo +1.98.0 run --release --locked -p kio-eval --example persona_full_contract
```

The example generates Full source projections, suite schedule, and render
artifact once each and checks the frozen digests and canonical byte bounds. It
is compiled by `--all-targets` but is not run by ordinary CI; no ignored test or
scheduled Actions charge was added.

Attest/materialize tests share only immutable canonical Tiny input bytes; every
filesystem mutation still uses its own temporary root. The old 32-iteration FD
growth proxy was replaced by a direct Linux `/proc/self/fd` assertion that no
descriptor remains under the workspace after a complete claim/release
lifecycle. Production `fsync`, nofollow, identity revalidation, create-only, and
credential boundaries were not weakened.

## Final-candidate clean-Linux cold/warm evidence

The exact tracked tree at `2c7db5d...` was measured in a writable Debian
Bookworm arm64 container with a fresh target, network disabled, a read-only
preexisting Cargo registry, Rust 1.98.0, 14 logical CPUs, and a 14 GiB memory
limit. The cold command and its one immediate warm repeat were:

```sh
cargo +1.98.0 test --workspace --all-targets --locked --no-fail-fast
```

`--no-fail-fast` retains complete diagnostic output; both commands exited zero.
This is the workspace-test operand, not formatting, Clippy, a complete job,
GitHub queue/billing, or the five-job workflow.

| Pass | Wall | Runner-equivalent | User / system CPU | Max RSS | Harness result | Over-60 s warnings |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| cold, empty target | 744.24 s | 12.404 min | 5,477.88 / 368.39 s | 1,374,808 KiB | 49 result blocks; 2,219 passed; 0 failed/ignored | 28; all later `ok` |
| warm, same target | 491.76 s | 8.196 min | 3,193.56 / 94.59 s | 766,348 KiB | 49 result blocks; 2,219 passed; 0 failed/ignored | 20; all later `ok` |

The warm pass was 252.48 seconds (33.92454%) shorter in this single
non-dedicated-host pair. This is not a distribution or GitHub cache claim. The
raw log SHA-256 values are
`ede42185fd47ac4d5cf40dc3b1e90e907459dd49f094241db95b0097257af1dd`
and `f8db5fc366cbb0a68d86ade46777a1e41211343178bf2744c69f4f1b54ac959d`.
The machine-readable artifact records all 49 binary/result-block identities,
times, aggregate resource counters, and evidence digests. Per-binary CPU, RSS,
and I/O remain unavailable; GNU `time` filesystem counters are tool-defined
rusage counts, not bytes.

The cold evidence-wrapper exited after the successful command because its `jq`
marker writer used a reserved variable name. The marker was recovered from the
already sealed begin time, completion time, GNU `time` exit status, and log;
cold was not rerun. Warm then ran exactly once and its wrapper exited zero.

An earlier clean attempt at `57819593...` failed after 424.13 seconds in
`bound_reentrant_lock_allows_nested_repository_store_lock`. It exposed a
fork-before-exec inherited-flock race and is excluded from successful cost.
`2c7db5d...` removed the spawning liveness probe, explicitly unlocks the final
logical gate, and adds cloned-open-file-description regressions; 200 repeated
parallel `kio-core` full-suite runs then passed before this successful cold/warm
pair.

## Slow-warning disposition on final bytes

The older GitHub attempt emitted 30 progress warnings; the final cold/warm pair
emitted 28/20. Every warned test in all three logs later emitted `... ok`; no
warning was a missing result, failure, ignore, or infinite wait. Counts are
host-sensitive and are not a formal speedup percentage. The structural change
is stronger evidence: the Full consumer/schedule/render/scaffold regeneration
and the 32-lifecycle FD proxy no longer exist in ordinary CI. The remaining
heavy paths retain distinct behavior:

| Current heavy group | Cold / warm warnings | Retained unique signal |
| --- | ---: | --- |
| `persona_attest` | 7 / 7 | descriptor-bound mutation detection, publication identity, link/case-fold rejection, and create-only attestation |
| `persona_consumer` | 5 / 3 | Tiny/Pilot canonical loading, identity recheck, malformed/cross-plan rejection |
| `persona_lease` | 8 / 8 | durable claim/release, recovery, linked/opaque-state rejection, ancestor mutation detection, and direct workspace-FD invariant |
| materialize/render/scaffold/public CLI | 8 / 2 | durable publication, bounded rendering/topology, and canonical command-surface integration |

`kio-eval` remained the dominant binary: its library block took 407.72/259.79
seconds and its CLI block 63.28/60.10 seconds. These binary walls overlap no
other binary, but individual tests within a block run concurrently; warning
durations must not be summed.

## Critical-path planning evidence

The older immutable `f50e8cc...` cohort is preserved rather than relabeled. Its
cold/warm workspace-test values were 394.88/329.78 seconds for 2,216 passed,
with 16/13 warnings, and its exact workflow-order `rust` and synthetic command
lanes were 426.38 and 83.99689 seconds. Persona W0 was 138.275887 seconds.

For the final candidate, combining the exact 744.24-second cold test operand
with the latest topology-identical `f50e8cc...` fmt (1.13 s), Clippy (13.99 s),
and synthetic (83.99689 s) operands gives a planning estimate of
**843.35689 seconds = 14.055948 minutes** for `rust -> synthetic-history-eval`.
It is below the 40-minute local target by 25.944052 minutes and the 45-minute
reference by 30.944052 minutes. Because the operands are cohort-separated, this
is not an exact same-run measurement, guarantee, GitHub success sample, or
billing result. The configured five-job timeout sum is 140 minutes, below the
250-minute reference, but the measured successful aggregate remains unknown
without current macOS and Windows success operands.

The bounded-runner delta validations remain green: Linux runner 18/18, U7
14/14, OCR 10/10, all 18 synthetic commands, and Persona W0. Windows runtime
remains CI-only confirmation; unknown is not substituted with zero.

## Non-current historical asset

`tasks/artifacts/ci-cost-baseline-2026-08-12.json` was deleted: it had zero
live consumers and was historical-only. It is recoverable from Git commit
`11a4147e0d5972ef0f7325ac61efb6ad9a3f7345`; no archive, stub, or redirect was
kept.

## Current acceptance boundary

Phase F changed finite timeout caps and removed duplicated ordinary Full/FD
stress, but did not reorganize the five-job topology, add a job, add a cache
action, or upload an artifact. Full plan/source-projection semantics remain in
ordinary Rust CI; the one-pass Full schedule/render signal has an explicit
Rust-owned manual command documented in [`../../eval/README.md`](../../eval/README.md).
Formal remeasurement requires matching successful runs of workflow blob
`bdc01e224cf952148910b6a6200b9ac1e451dd9e` and a successful Windows
measurement; queue and billing remain unknown unless GitHub exposes usable
values.
