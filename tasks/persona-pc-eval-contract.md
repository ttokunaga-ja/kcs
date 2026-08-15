# Persona-PC Rust contract (v2)

Status: Phase 4 milestone 5 remains in progress. The executable persona contract is Rust-only. This document is normative for planning artifacts; it does not authorize filesystem materialization, Kio indexing, history replay, or a full-scale acceptance claim.

## Authority and invocation

`kio-eval` is the sole authority for the closed persona topology, allocation, rendering, physical/logical/search expectation ledgers, and W0--W5 event schedule. Python is retained only for filesystem/runtime safety boundaries and cannot rebuild, validate, or substitute a semantic persona contract.

```bash
kio-eval persona plan --profile tiny --out /absolute/path/persona-plan.json
kio-eval persona render --plan /absolute/path/persona-plan.json --out /absolute/path/persona-render.json
kio-eval persona schedule --plan /absolute/path/persona-plan.json --out /absolute/path/persona-schedule.json
```

Each output path must be absolute and create-only. The commands reject an unknown profile, non-canonical artifact, mismatched plan digest, malformed paths, and pre-existing output. No legacy command spelling, migration input, or compatibility alias exists.

## Closed plan

The `kio.persona.plan/v2` artifact freezes a deterministic seed, all twenty personas, exactly twenty direct-file scopes per persona (twelve primary and eight secondary), source identities, family/variant routing, contributor quotas, and structural lifecycle rows. It is bounded, canonical JSON, and digest-bound before a consumer accepts it. The profiles are `tiny`, `pilot`, and `full`; only `tiny` is a contract smoke, and neither is physical/full acceptance evidence.

The fixture uses fifteen format families and twenty-five deterministic variants. Renderers are functions of the accepted plan only. They produce deterministic UTF-8 text and structurally checked PDF, PNG, WAV, PCAP, DOCX, XLSX, and PPTX bytes; raw bytes and their digests remain renderer-owned facts.

## Manifests and schedule

`kio.persona.manifest/v2` holds the plan-bound physical, logical, and search expectation ledgers. It is a projection of the closed plan and renderer output, not evidence that Kio indexed a raw artifact or produced the planned chunks.

`kio.persona.schedule/v2` derives W0--W5 history without a second allocation truth. W1 edits P/X/Y plus history; W3 edits X/Y/N plus history; W4 deletes and replaces X without changing the current target; W5 corrects N, creates P replacements, indexes the coexistence state, serially purges the old P versions, and then indexes each affected scope once as a no-op. Structural rows remain history-neutral. IDs, dependency edges, local ticks, global order, source versions, and deltas are canonical and independently validated.

Suite construction processes one person at a time and retains only compact projections for the global merge. It must not materialize an unbounded all-person event graph. All parsing limits are applied before JSON deserialization and all totals use checked arithmetic.

## Non-claims and retained boundaries

The plan, render, manifest, and schedule artifacts are pure planning evidence. They do not prove W0 publication, root ownership, native durability, Kio prepare/index behavior, chunk counts, history readiness, or performance. Those claims require the retained Python filesystem/runtime boundary helpers and separate readback/attestation work. A historical Python proposal or artifact is non-normative and must not be executed as a current contract.

Rust tests in `crates/kio-eval` directly test the canonical plan, render, manifest, and schedule contracts. Python CI retains only storage, streaming storage, root-lock, command-runner, prepare-receipt, history-attestation, and filesystem integration boundaries.
