# Current five-job CI unique-signal ledger

The authoritative current cohort is [run 32747140652](https://github.com/ttokunaga-ja/kio/actions/runs/32747140652): `CI` / `push` / attempt `1`, head `1bbae928adf2a2fdbf04b1114665cddf40631c5d`, tree `22ad7bc8001347a4510422dfbf6e43d0215400a9`, workflow blob `07ae8f90747c9bce4e0d9508af2a967ffd8bbed6`, Rust `1.98.0`, and five jobs with `rust -> synthetic-history-eval`. It has one matching success (`n=1`), so the formal current-CI baseline is **provisional**, not a distribution or continuous-SLO result. The machine-readable source is [ci-cost-baseline.json](ci-cost-baseline.json).

| Job | Unique signal | Failure signal |
| --- | --- | --- |
| `rust` | Ubuntu format, warnings-denied lint, complete workspace/all-target tests, and Full-example compile | format, lint, example, or workspace test exits nonzero |
| `persona-w0-integration` | Rust Tiny persona lifecycle, create-only preservation, leases, and filesystem attestation | rematerialization, hashes, lease coordination, or attestation claims disagree |
| `synthetic-history-eval` | release/all-features evaluator plus tiny scale, history, cross-scope, rerank, and M3 recall | any command fails, rerank cannot apply, or M3-1 recall is below `0.9166666666666666` |
| `macos-security-r23` | complete workspace/all-target tests under macOS semantics | any workspace test exits nonzero on macOS |
| `windows-security-r23` | complete workspace/all-target tests under Windows portability and security semantics | any workspace test exits nonzero on Windows |

The three platform test invocations have identical Cargo text but noninterchangeable OS evidence. Only a demonstrated duplicate signal may be consolidated; Full, cold, and scale commands remain manual when they add a distinct signal.

## Current matching success

| Job | Result | Elapsed | GitHub job ID |
| --- | --- | ---: | ---: |
| `rust` | success | 23:50 | 97495261887 |
| `persona-w0-integration` | success | 04:02 | 97495262074 |
| `synthetic-history-eval` | success | 04:06 | 97502852808 |
| `macos-security-r23` | success | 21:51 | 97495262123 |
| `windows-security-r23` | success | 29:38 | 97495262075 |

The run ran from `2026-08-24T15:48:52Z` to `2026-08-24T16:18:35Z`: 29:43 wall-clock. Aggregate elapsed is 5,007 seconds = 83:27 = 83.45 runner-equivalent minutes (elapsed divided by 60, **not** GitHub billing minutes). The overall critical path is Windows at 29:38. The required dependency path is `rust` 23:50 + 00:03 handoff + `synthetic-history-eval` 04:06 = 27:59. No job failed, was cancelled, skipped, or was downstream-skipped.

This one run is below the 45-minute wall-clock reference and the 250-minute aggregate runner-equivalent reference. Those are single-run comparisons only. GitHub did not expose internal queue, billing, CPU, RSS, byte I/O, or cache telemetry; each value remains null/unknown and is not treated as zero.

### Windows harness evidence and Phase 3 candidates

The Windows job produced 49 harness result blocks with 1,947 passed, zero failed, and zero ignored tests. Its longest harness block was 452.70 seconds. Cargo emitted 11 `has been running for over 60 seconds` progress warnings; every warned test later had terminal `ok`. The warnings are candidate inputs for Phase 3 bounded-fixture or duplicate-signal review, not missing results, failures, or evidence of an unbounded test. Harness wall times are not GitHub billing, CPU, RSS, or I/O measurements.

The Phase 3 priority harnesses measured on Windows were `step2_p0_contract` 86.62s, `step3_p0_contract` 452.70s, `step4b_p2a_contract` 36.00s, `step4b_p2b_contract` 52.97s, `step4b_p2c_contract` 103.90s, `step4b_p3a_contract` 29.75s, and `step4b_p3b_contract` 39.20s. The complete 49-harness extraction, including pass counts and elapsed seconds, is retained under `current_success_cohort.windows_harness_evidence.per_harness` in the JSON artifact.

Phase 3 should inventory the warned tests by failure mode, fixture, subprocess, SQLite, and CAS-rebuild signal, then retain one bounded behavior test per distinct failure class. A later non-`ok`, timeout, cancellation, or missing terminal result is the failure signal requiring investigation.

## Phase 3 bounded-fixture ledger

The seven priority suites remain distinct checks; the current Windows cohort's
per-harness measurements are evidence of platform cost, not a promise that a
local macOS run will improve them.

| Suite | Current Windows elapsed / passed | Unique signal, platform, process, SQLite/CAS coverage | Phase 3 decision |
| --- | ---: | --- | --- |
| `step2_p0_contract` | 86.62s / 104 | pipeline, approval, retry-budget, PDF/image; portable plus Windows child and Unix filesystem branches; ~17 CLI helpers; limited ledger/CAS | retain |
| `step3_p0_contract` | 452.70s / 274 | ranking/hybrid, cursor, multi-scope, rebuild, corruption and race paths; Windows child plus Unix race/permission branches; immutable fixture copied per test; ~168 CLI helpers and extensive SQLite/CAS | retain |
| `step4b_p2a_contract` | 36.00s / 32 | cache, purge, tombstone and restore races; cross-platform filesystem paths; ~11 CLI helpers and deliberate CAS coverage | retain |
| `step4b_p2b_contract` | 52.97s / 44 | verify/fsck, evidence, shallow, malformed input, SQLite-loss and batch parity; portable plus Unix branch; ~12 CLI helpers with CAS/DAG/SQLite coverage | retain |
| `step4b_p2c_contract` | 103.90s / 40 | search, candidate-depth, cursor, scope and history; portable; ~36 CLI commands and moderate SQLite coverage | optimize only its 210-chunk fixture |
| `step4b_p3a_contract` | 29.75s / 35 | budget, auth, rate-limit, approval and online wiring; portable mock seams; ~17 CLI helpers and negligible SQLite | retain |
| `step4b_p3b_contract` | 39.20s / 33 | error precedence, version, child-scope, history, DDL and observability; Windows and Unix branches; ~21 CLI helpers with SQLite/CAS/history coverage | retain |

The pre-change host reference was measured at commit `cbff8e1`, sequentially
with Rust `1.98.0`: `step2` 36.31s / 107, `step3` 129.76s / 282, `p2a` 18.93s
/ 32, `p2b` 19.48s / 45, `p2c` 41.78s / 40, `p3a` 12.18s / 35, and `p3b`
17.20s / 34. It is a host reference, not a replacement for the current
Windows cohort counts above.

Two changes are justified, and only these two: `p2c` now generates one
Markdown input with 210 distinct nonempty heading/chunk records instead of
210 paths, while still exercising the CLI, indexer, chunker, default offset
200 exclusion, and configured-depth 205 five-result path; the FTS overflow
test still makes all 4,097 public `index_chunk` calls (including validation
and per-call savepoints), under one outer `BEGIN IMMEDIATE` transaction. No
raw SQLite insert, limit change, fixture bypass, cache, skip, or weakened
assertion is used. Fixture-construction failure explicitly rolls the outer
transaction back before failing the test.

The directly changed `p2c` host reference moved from 41.78s to 22.82s real
time: -18.96s, about 45.4%. Across the seven-suite sequence, real time moved
from 275.64s to 271.30s: -4.34s, about 1.6%. This aggregate is a noisy host
reference; movement in unchanged suites is not attributed to this patch. The
FTS transaction fixture has no matched pre-measurement, so it makes no local
or Windows reduction claim.

### Over-60-second warning audit

All 11 Windows Cargo progress warnings had finite test input and a later
terminal `ok`; none was a missing result, timeout, cancellation, or ignored
test. The two fixture candidates are
`pc15_pc17_candidate_depth_configuration_is_not_hardcoded_to_200` and
`fts::tests::exact_retarget_candidates_classify_overflow`, addressed above.
The remaining nine persona warnings are retained because each covers a
separate generated-artifact or identity failure class:

- `persona_consumer::tests::loads_actual_generated_canonical_artifacts_for_tiny_and_pilot` — Tiny/Pilot canonical artifacts.
- `persona_consumer::tests::recheck_rejects_replaced_source_bytes` — source-byte replacement detection.
- `persona_consumer::tests::recheck_rejects_same_content_inode_replacement` — same-content inode replacement detection.
- `persona_consumer::tests::rejects_handcrafted_partial_plan_and_cross_plan_artifacts` — partial/cross-plan artifact rejection.
- `persona_consumer::tests::rejects_schedule_and_render_from_another_plan` — schedule/render plan binding.
- `persona_manifest::tests::tiny_all_person_shards_are_renderer_bound_and_frozen` — all Tiny persona shards and renderer binding.
- `persona_render::tests::plan_bound_person_rendering_covers_all_variants` — deterministic rendering variants.
- `persona_render_artifact::tests::tiny_and_pilot_artifacts_fit_the_explicit_bounds` — explicit artifact size/count bounds.
- `persona_schedule::tests::tiny_and_pilot_have_deterministic_plan_bound_schedules` — deterministic schedules.

Those persona checks use finite Tiny/Pilot data, bounded shard/variant loops,
filesystem and hash/identity assertions. They launch no subprocess, use no
SQLite or CAS rebuild, sleep nowhere, and contain no unbounded retry or
generation loop. The immutable fixture reuse is not a mutable cache; removing
or coalescing these checks would erase distinct failure signal, so the
warnings alone do not justify a cost cut.

### AFTER local host reference

After the two changes, the same seven suites were run sequentially with Rust
`1.98.0` and `/usr/bin/time -p`; each exited zero and had no failed, ignored,
or measured test. `p3a` was accidentally invoked a second time by the shell
loop, but only its first result below is recorded; it is not treated as an
additional sample.

| Suite | Pass count | Test elapsed | real | user | sys |
| --- | ---: | ---: | ---: | ---: | ---: |
| `step2_p0_contract` | 107 | 26.12s | 27.34s | 13.06s | 18.15s |
| `step3_p0_contract` | 282 | 151.17s | 152.27s | 71.85s | 100.05s |
| `step4b_p2a_contract` | 32 | 21.23s | 22.32s | 5.94s | 8.32s |
| `step4b_p2b_contract` | 45 | 22.50s | 22.88s | 9.28s | 11.46s |
| `step4b_p2c_contract` | 40 | 20.10s | 22.82s | 7.79s | 12.46s |
| `step4b_p3a_contract` | 35 | 9.05s | 10.03s | 4.19s | 5.86s |
| `step4b_p3b_contract` | 34 | 13.29s | 13.64s | 6.46s | 9.45s |

These are local host references only. No Windows improvement is claimed until
a matching native Windows CI run completes; the retained Windows cohort and
its warning audit remain the current platform evidence.

## Separate cancelled cohort

[Run 32740699426](https://github.com/ttokunaga-ja/kio/actions/runs/32740699426) is a separate cancelled 45-minute cohort: head `0584667837bee12afe125ecd7d6cf395ac673298`, workflow blob `bdc01e224cf952148910b6a6200b9ac1e451dd9e`, workflow wall 45:20, jobs 29:56 / 04:47 / 04:11 / 24:05 / 45:15, aggregate 6,494 seconds = 108:14, and `rust -> synthetic-history-eval` 34:12. It is ineligible for successful-cost arithmetic and does not increase `n`.

Historical local and failed cohorts remain historical context only. They are not relabeled as current, and their values are never mixed into this cohort.
