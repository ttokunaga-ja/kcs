# Security Hardening Review: KCS

## Evidence Basis
This portfolio is derived from Codex Security scan `f78f5d0d-2752-47a7-8d8d-3371e09d3377` at revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`. I treated the 47 accepted findings, their hash-bound write-ups, validation reports, and attack-path reports as evidence; the proposals below are design guidance and do not claim remediation is complete.

## Constraints
We should keep KCS repository-local workflows compatible while closing the repeated invariant drift. No performance or memory budget was supplied, so the recommendations use a balanced profile and call out where measurement is required.

## Opportunity Portfolio

| Opportunity | Evidence | Options | Recommendation | Proposal |
| --- | --- | --- | --- | --- |
| Centralize bounds before untrusted work is materialized | 14 findings, including KCS-R23-CAND-004, KCS-R23-CAND-006, KCS-R23-CAND-007, KCS-R23-CAND-017 and related findings | local guards; owned boundary | I recommend the owned-boundary option when the team can absorb a medium-term migration; use local guards first for urgent exposure reduction. | [bounded-input-work](proposals/bounded-input-work.md) |
| Bind content identity to final scope and provenance | 18 findings, including KCS-R23-CAND-069, KCS-R23-CAND-005, KCS-R23-CAND-008, KCS-R23-CAND-024 and related findings | local guards; owned boundary | I recommend the owned-boundary option when the team can absorb a medium-term migration; use local guards first for urgent exposure reduction. | [content-scope-binding](proposals/content-scope-binding.md) |
| Run adapters through scoped capabilities and policy-preserving targets | 6 findings, including KCS-R23-CAND-003, KCS-R23-CAND-038, KCS-R23-CAND-039, KCS-R23-CAND-040 and related findings | local guards; owned boundary | I recommend the owned-boundary option when the team can absorb a medium-term migration; use local guards first for urgent exposure reduction. | [adapter-capability-policy](proposals/adapter-capability-policy.md) |
| Make durable workflow state transitions verifiable and replay-safe | 9 findings, including KCS-R23-CAND-011, KCS-R23-CAND-013, KCS-R23-CAND-014, KCS-R23-CAND-036 and related findings | local guards; owned boundary | I recommend the owned-boundary option when the team can absorb a medium-term migration; use local guards first for urgent exposure reduction. | [durable-state-invariants](proposals/durable-state-invariants.md) |

## Recommendation Summary
I recommend treating local guards as the immediate containment layer and designing owned boundaries for the two largest recurrence classes: final content/scope binding and bounded work admission. The adapter and durable-state opportunities can use the same pattern once the project agrees on capability handles and replay-safe state transitions. What gives me pause is migration cost: the structural options touch central KCS workflows, so we should keep the tactical fixes and candidate PoCs as acceptance gates while the shared boundaries are introduced.

## Next Decisions
Decide which opportunity gets implementation planning first, set rough latency and memory budgets for the selected boundary, and choose whether tactical fixes should ship before or with the structural migration.
