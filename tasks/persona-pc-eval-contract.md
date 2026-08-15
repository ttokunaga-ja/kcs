# Persona-PC Rust contract (v2)

Status: Phase 4 milestone 5 remains in progress. The executable persona contract is Rust-only. This document is normative for canonical artifacts and their create-only materialization/workspace scaffold; it does not authorize source generation, Kio indexing, history replay, or a full-scale acceptance claim.

## Authority and invocation

`kio-eval` is the sole authority for the closed persona topology, allocation, rendering, physical/logical/search expectation ledgers, W0--W5 event schedule, canonical bundle materialization, and workspace scaffold. Python is retained temporarily only for opaque owner-record lease coordination and materialization-record-bound filesystem-byte observation; it cannot rebuild, validate, or substitute a semantic persona contract.

```bash
kio-eval persona plan --profile tiny --out /absolute/path/persona-plan.json
kio-eval persona render --plan /absolute/path/persona-plan.json --out /absolute/path/persona-render.json
kio-eval persona schedule --plan /absolute/path/persona-plan.json --out /absolute/path/persona-schedule.json
kio-eval persona materialize --plan /absolute/path/persona-plan.json --schedule /absolute/path/persona-schedule.json --render /absolute/path/persona-render.json --destination /absolute/new/materialized-root --replay-id replay-01
kio-eval persona scaffold --plan /absolute/path/persona-plan.json --root /absolute/new/workspace-root
```

Each output path must be absolute and create-only. The commands reject an unknown profile, non-canonical artifact, mismatched plan digest, malformed paths, and pre-existing output. `materialize` publishes exactly the three accepted artifacts plus `kio.persona.materialization/v1`; `scaffold` publishes exact plan-derived topology plus `kio.persona.workspace-owner/v1`. No legacy command spelling, migration input, or compatibility alias exists.

## Closed plan

The `kio.persona.plan/v2` artifact freezes a deterministic seed, all twenty personas, exactly twenty direct-file scopes per persona (twelve primary and eight secondary), source identities, family/variant routing, contributor quotas, and structural lifecycle rows. It is bounded, canonical JSON, and digest-bound before a consumer accepts it. The profiles are `tiny`, `pilot`, and `full`; only `tiny` is a contract smoke, and neither is physical/full acceptance evidence.

The fixture uses fifteen format families and twenty-five deterministic variants. Renderers are functions of the accepted plan only. They produce deterministic UTF-8 text and structurally checked PDF, PNG, WAV, PCAP, DOCX, XLSX, and PPTX bytes; raw bytes and their digests remain renderer-owned facts.

## Manifests and schedule

`kio.persona.manifest/v2` holds the plan-bound physical, logical, and search expectation ledgers. It is a projection of the closed plan and renderer output, not evidence that Kio indexed a raw artifact or produced the planned chunks.

`kio.persona.schedule/v2` derives W0--W5 history without a second allocation truth. W1 edits P/X/Y plus history; W3 edits X/Y/N plus history; W4 deletes and replaces X without changing the current target; W5 corrects N, creates P replacements, indexes the coexistence state, serially purges the old P versions, and then indexes each affected scope once as a no-op. Structural rows remain history-neutral. IDs, dependency edges, local ticks, global order, source versions, and deltas are canonical and independently validated.

Suite construction processes one person at a time and retains only compact projections for the global merge. It must not materialize an unbounded all-person event graph. All parsing limits are applied before JSON deserialization and all totals use checked arithmetic.

## Non-claims and retained boundaries

The plan, render, manifest, and schedule artifacts are pure planning evidence. Rust materialization proves only exact artifact bytes, identity, create-only publication, and explicit false claims (`sources_materialized=false`, `actual_kio_evidence=false`, `history_ready=false`). Rust scaffold proves only the exact plan-derived workspace topology and owner record. Neither proves source generation, Kio prepare/index behavior, chunk counts, history readiness, or performance. The retained Python history observer reports bounded filesystem bytes with the same Kio/history claims false; the opaque lease is duplicate-writer coordination, not semantic or Kio evidence. A historical Python proposal or artifact is non-normative and must not be executed as a current contract.

Rust tests in `crates/kio-eval` directly test the canonical plan, render, manifest, schedule, artifact consumer, materializer, and scaffold contracts. Python CI temporarily retains only opaque owner-digest lease, materialization-digest history observation, and their filesystem-boundary tests.
