# Persona-PC Rust contract snapshot

Status: **historical, non-authorizing**. This record described the Phase 4
milestone-5 boundary. Phase 4 milestones 1-8 are now implemented, so the former
in-progress status and operational command list were removed. Current authority
is the `kio-eval` implementation, its Rust tests,
and canonical product documentation.

The retained contract facts are:

- `kio-eval` owned the closed persona topology, deterministic plan/render/
  schedule artifacts, create-only materialization and scaffold, lease
  coordination, and filesystem attestation.
- The `tiny`, `pilot`, and `full` profiles were planning/materialization
  profiles; none alone proved that Kio indexed source documents or satisfied a
  full-scale acceptance gate.
- Plan, render, manifest, schedule, materialization, scaffold, lease, and
  attestation records were digest-bound. Consumers could not reconstruct or
  substitute them through a second runtime.
- Materialization and attestation deliberately kept
  `sources_materialized=false`, `actual_kio_evidence=false`, and
  `history_ready=false` until separately established.
- Leases coordinated duplicate writers but did not constitute semantic,
  indexing, history, or performance evidence.

This snapshot does not authorize corpus production or claim current RC
acceptance. A consumer must use accepted Rust records and the current executable
contract directly.
