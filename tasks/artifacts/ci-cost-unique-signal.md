# Current five-job CI unique-signal ledger

This ledger keeps the cohorts separate. The current product changes end at
`b849f7cc927806fb6264f1ad5b6c696016655053`, tree
`3817b04e490d4020e4fc6066bf5cdc1002bb8937`, and use workflow blob
`bdc01e224cf952148910b6a6200b9ac1e451dd9e`. The clean-Linux cold/warm cost
cohort remains bound to the earlier Phase F product head `f50e8cc...`, tree
`477a8d9...`; it is not relabeled as a final-head measurement. The candidate
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

## Phase F clean-Linux cold/warm evidence

The immutable `f50e8cc...` measurement bytes were copied into a writable Debian
Bookworm arm64 container with a fresh target, network disabled, a read-only
preexisting Cargo registry, Rust 1.98.0, 14 logical CPUs, and a 14 GiB memory
limit. The exact measurement command was:

```sh
cargo +1.98.0 test --workspace --all-targets --locked --no-fail-fast
```

`--no-fail-fast` was added locally to retain complete diagnostics; both passes
exited zero. This measures the workspace test command, not `cargo fmt`, Clippy,
the complete `rust` job, another job, queueing, billing, or the five-job
workflow.

| Pass | Wall | Runner-equivalent | User / system CPU | Max RSS | Harness result | Over-60 s warnings |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| cold, empty target | 394.88 s | 6.581333 min | 3,097.29 / 113.58 s | 1,303,388 KiB | 49 binaries; 2,216 passed; 0 failed/ignored | 16; all later `ok` |
| warm, same target | 329.78 s | 5.496333 min | 2,431.99 / 71.51 s | 793,404 KiB | 49 binaries; 2,216 passed; 0 failed/ignored | 13; all later `ok` |

The warm pass was 65.10 seconds shorter than the cold pass in this single
non-dedicated-host pair. That observation is not a distribution or a GitHub
cache claim. The raw log digests are
`dc667ef40501c0a7162bde5e79a35716caead6efe9105c9bc2f2a91323896cd9`
(cold) and
`9167c089beda618b86924d6ec76285c48a3f849170b4b1b7d289dbadc0143757`
(warm). The machine-readable artifact records all 49 binary names, pass
counts, and cold/warm harness times.

GNU `time` reported aggregate page faults, context switches, and filesystem
input/output counters. Those filesystem counters are tool-defined rusage
counts, not bytes. Per-test CPU, RSS, and I/O were not available and remain
unknown. Post-run target and temporary-directory sizes were 8,745,391,528 and
97,609,519 bytes respectively; they are storage sizes, not I/O throughput.

The old GitHub Rust job emitted 30 warnings and later `ok` for all 30. The
measured Phase F cold/warm runs emitted 16/13 and later `ok` for every warning.
The cold groups were six attestation, two consumer, and eight lease tests;
the warm groups were four, two, and seven. Ordinary Full regeneration no longer
appears in consumer/render/schedule/scaffold warning paths, and the old
32-lifecycle FD proxy is gone. The retained heavy signals are deliberate:

| Current heavy group | Retained unique signal |
| --- | --- |
| `persona_attest` | descriptor-bound mutation detection, publication identity, symlink/hardlink/case-fold rejection, and create-only attestation |
| `persona_consumer` | Tiny/Pilot canonical artifact loading plus foreign-plan schedule/render rejection |
| `persona_lease` | durable claim/release, recovery, linked/opaque-state rejection, ancestor mutation detection, and the direct workspace-FD invariant |

The 30-to-16/13 comparison is diagnostic only because host, command, and cohort
differ. It does not supply a formal speedup percentage or a successful GitHub
sample.

After that cost measurement, `b849f7c...` corrected the bounded runner state
machine so EOF on both output pipes cannot fall through to an unbounded child
`wait`, and added one Unix regression test. The workflow blob did not change.
An isolated Linux delta validation at that exact product head passed runner
18/18, U7 14/14, OCR 10/10, all 18 Synthetic workflow commands, and the Persona
W0 lifecycle in about 123 seconds. No clean-Linux cold/warm cost rerun was made
for this one-test delta, so the 49-binary / 2,216-test timings above remain
evidence only for `f50e8cc...`.

Separate fresh local Linux job containers then replayed the workflow command
order. The `rust` sequence succeeded in 426.38 seconds by command sum (fmt
1.13 s, Clippy 13.99 s, test 411.26 s). The dependent synthetic sequence
succeeded in 83.99689 seconds, including a 54.68-second fresh release build and
all scale, replay, cross-scope, rerank, and M3 gates. Their local command-path
estimate is 510.37689 seconds = **8.506281 minutes**. It is below the 40-minute
local planning target with 31.493719 minutes of margin, but excludes checkout,
toolchain setup, GitHub queueing, and runner differences. It is not a current
GitHub success sample or billing result.

The independent Persona W0 lane also succeeded from a fresh target in
138.275887 seconds = 2.304598 minutes, including the expected refusal of the
second materialization, unchanged first-publication hashes, lease lifecycle,
and filesystem attestation. The three known successful Linux command lanes sum
to 10.810880 runner-equivalent minutes locally. The five-job aggregate remains
unknown because current successful macOS and Windows cost operands are absent.

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
