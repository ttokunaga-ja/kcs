# Persona-PC v2 — 20-person formal readiness audit v1

Status: **pre-materialization audit**.  This records the evidence boundary for
the active 20-persona objective.  It does not issue G0, select an allocation
truth, create a corpus root, run Kio, attest chunks, mutate history, or
authorize Phase 2 `eval-gen/` generation.

## 1. Exact target being audited

The formal retrieval/history lane must eventually provide all of the following:

- 20 independent persona-PC roots (`p01` through `p20`) per replay, each with
  20 active leaf scopes; no cross-person file, chunk, inode, registry, or
  completed-root pooling;
- 3 fresh-storage replays, yielding 60 independent device roots and 1,200
  formal scopes across the campaign;
- for **each** persona, exactly 120,000 observed W0 and W5 current
  contract-contributor chunks, and at least 180,000 observed W5
  current-plus-history contract chunks;
- persona-specific directory topology, language/locale assumptions, primary
  use case, format-family/variant mix, source size/complexity mix, and
  lifecycle behavior; and
- physical-file, Kio, history, query, capacity, and cross-replay receipts that
  prove those facts after materialization rather than inferring them from a
  plan.

The primary contract is
[`persona-pc-fidelity-v2-contract.md`](persona-pc-fidelity-v2-contract.md).
The human-readable folder/format proposal is
[`persona-pc-fidelity-v2-proposal.md`](persona-pc-fidelity-v2-proposal.md).

## 2. Evidence matrix

| objective requirement | current evidence | state | what is still required for completion |
| --- | --- | --- | --- |
| 20 distinct personas and 20 primary use cases | `persona_v2_contract` and the v2 proposal define `p01..p20`; the contract tests assert 20 distinct roles and 20 per-person profiles | static contract verified | bind each persona to a solved source/path/quota plan and physical root |
| Per-person folder topology and nested PC structure | v2 proposal specifies separate `devices/pXX-.../home/` roots, 12 primary + 8 secondary scopes, formal D2--D6 and a separate recursive ambient lane | planned topology | emit and read back all 20 × 20 scope paths in every replay |
| Persona-specific 15-family format ratios | `persona_v2_contract` defines 20 × 15 integer family marginals; the suite total is 203,000 W0 planned source-intent slots | static allocation verified | choose the upstream allocation truth, then bind source IDs, variants, recipes, MIME/magic, and rendered files |
| 120,000 current chunks per person | density intervals in `persona_v2_contract` cover 120,000 for every full persona; W0/W5 checkpoint literals are tested | integer feasibility only | exact solved per-source quotas, materialize/index, then person-scoped Kio attestation |
| W5 current + history at least 180,000 per person | formal checkpoint contract defines 120,000 current + 60,000 history-only | planned history arithmetic | immutable event plan, W1--W5 execution, and DB/CAS/history readback |
| No pooling across persons or replays | v2 contract requires 3 fresh roots and forbids clone/link/completed-root reuse | planned invariant | inode/registry/path/CAS evidence for every root and cross-replay comparison |
| Capacity sufficiency | formal workload lower bounds define 203,000 planned source slots and 2,400,000 contract chunk objects per replay; measurement gate remains false | unmeasured | pilot destination measurements, projected full capacity with >=25% headroom, then full preflight |
| M3 / Q_hard quality and baseline comparison | v2 query/semantic candidates exist, but target resolution remains a blocker; requested Q_hard package is Phase 1 approval pending | incomplete | approved separate `eval-gen/` artifacts, concrete source mapping, and observed evaluation |

Passing the existing static tests demonstrates cardinality and consistency only.
It is not evidence that any actual Kio chunk, history object, search result,
filesystem object, capacity allocation, or latency measurement exists.

## 3. Non-substitution rules

The Rust-only `kio-eval scale` v2 fixture has one root containing 20 scopes and
120,000 expected Markdown chunks. It is useful for a narrow single-machine
performance gate, but it is **not** evidence for this objective:

- its 20 scopes are not 20 independent people;
- it does not provide 20 persona-specific folder trees, file-format mixes, or
  language attributes;
- it does not prove 120,000 chunks separately for every persona; and
- it has no 20-person W1--W5 history or 60-root replay evidence.

Likewise, the requested Phase 2 `eval-gen/` package is a deliberately small
fixture for Q_hard and baseline comparison.  It must remain separate from the
120,000-chunk/person formal lane and cannot substitute for capacity, history,
or performance attestation.

## 4. Current numerical planning envelope

| measure | pilot | full |
| --- | ---: | ---: |
| W0 planned source-intent slots per replay | 20,300 | 203,000 |
| W0 contract chunks per replay | 240,000 | 2,400,000 |
| W0 contract chunks across 3 replays | 720,000 | 7,200,000 |
| W5 final current + history chunks per replay | 360,000 | 3,600,000 |
| W5 final current + history chunks across 3 replays | 1,080,000 | 10,800,000 |

For the full lane, these values arise from 20 independent persons, each with
120,000 current chunks at W0/W5 and 60,000 W5 history-only chunks.  They are
planning values, not observed values.  The capacity model deliberately leaves
`absolute_root_bound_caps_frozen=false` until pilot readback has measured raw,
CAS, index, history, staging, transient bytes, and inode consumption on the
actual destination.

## 5. Blocking decisions and safe order

1. Keep the current core-vs-legacy allocation discrepancy explicit.  The
   count-only audit found 489/566 full and 483/566 pilot coordinate mismatches;
   no existing source/namespace artifact may be silently reinterpreted.
2. Select either allocation supersession or deferral.  If supersession is
   selected, follow the versioned successor closure in
   [`persona-pc-core-extension-supersession-dependency-closure-v1-proposal.md`](persona-pc-core-extension-supersession-dependency-closure-v1-proposal.md).
3. Complete the source/path/quota/query/history closure and its independent
   validators before authorizing any formal writer.
4. Run a pilot W0 materialization and Kio attestation for all 20 personas;
   use its destination readback for the full capacity decision.
5. Only after the full preflight passes, execute three fresh W0--W5 replays,
   collect all receipts, then run M3 and Q_hard/baseline evaluation.

The formal lane deliberately counts only direct-child files in its 20 leaf
scopes.  Complex recursive trees are currently a separate robustness lane.  If
the target requires recursively discovered nested files to participate in the
same formal 100,000-chunk performance denominator, a separate recursive-scale
scope/chunk/latency contract must be added before materialization; it cannot be
inferred from the existing ambient-tree catalog.

The Phase 2 request has an additional user-controlled gate: generate no
`eval-gen/` files, manifests, sources, recipes, or Office instructions until
the Phase 1 requirements proposal is explicitly approved.
