# Persona-PC core extension allocation — content-only namespace admission v1 proposal

Status: **proposal only; admission blocked**.  This is neither a `Manifest
Golden-Freeze Decision/Gate` nor a namespace issuance.  It does not amend the
user-owned decision log, change complete inventory v2 or namespace v3,
authorize a solver, or authorize source rendering, filesystem writes, history,
Kio, evaluation, capacity completion, or G0.

## 1. Decision requested

The frozen `persona-core-v1` extension-allocation candidate must not be copied
as-is into a future corpus semantic namespace.  Its raw rows contain renderer,
validator, and registry bindings; its descriptor contains upstream validation
provenance and authority/completion fields.  None of those are semantic
pre-solve corpus content.

There is also a P0 compatibility blocker: the candidate allocation disagrees
with the existing frozen source-inventory allocation.  Therefore the requested
decision is deliberately conditional:

1. define the smallest possible content projection and a separate derivation
   receipt; but
2. keep that projection **outside every semantic namespace** until an
   independent compatibility owner resolves the two allocation truths.

The frozen source candidate pinned by this proposal is exactly:

| source item | canonical bytes | SHA-256 |
| --- | ---: | --- |
| descriptor `persona-core-v1-extension-allocation-manifest-v1` | 5,357 | `ca7caa3813d8f359785cb4dc65e7155f6e36153ba651e1a4b3af0d3695780e9f` |
| external rows `persona-core-v1-extension-allocation-rows-v1` | 426,889 | `f31f696e1692758e4fc52133dba733af77b74d16711034ee05d75b16d64f7d45` |

Those pins attest an authored, frozen **candidate** only.  They do not record a
formal decision or issue an admission.

## 2. P0: legacy allocation compatibility is unresolved

Read-only comparison of the frozen core rows with the existing
`source_intent_profile_manifest(pXX, "full"|"pilot")` variant counts finds
the same suite totals but materially different distributions.  Normalizing the
legacy omission of zero rows to the 566 core coordinates gives:

| profile | both suite totals | mismatched persona × variant rows |
| --- | ---: | ---: |
| full | 203,000 | 489 / 566 |
| pilot | 20,300 | 483 / 566 |

This result is now reproduced by the separate, non-authorizing
`core-extension-legacy-source-allocation-compatibility-audit/v1` candidate.
Its descriptor/body pins and local replay evidence are recorded in
`persona-pc-core-extension-legacy-allocation-compatibility-audit-v1-golden-freeze-record.md`.
The audit is count-only: it proves neither format-metadata compatibility nor a
choice of which allocation truth should win.

For example, p01 has core `docx=24`, `pdf-scan=12`, `pptx=20`, and `xlsx=20`,
whereas the existing full source inventory has 360, 120, 240, and 240
respectively.  Equality of the aggregate totals is therefore not an allocation
compatibility proof.

Set the following state until a new independent owner closes it:

```text
legacy_source_allocation_compatibility = unresolved
legacy_source_projection_reuse_authorized = false
```

Before admission, exactly one of these outcomes must be formally selected:

1. **Additive reuse:** an independent comparison proves fixture/envelope
   persona/family/variant-universe equality, zero mismatch for every
   `(persona_id, variant_id, profile)` allocation, and the extension/suffix/
   role/disposition mapping.  Only then can the existing source content
   projections coexist with this allocation projection.
2. **Supersession:** core allocation becomes the selected upstream truth and a
   new content-only source-inventory/parameter/base-context/effective-membership
   successor is regenerated before any namespace successor.  A dependency-closure
   audit must also identify every transitive legacy content owner whose per-intent
   allocation depends on the old inventory (including overlay, source-matched
   lifecycle, payload/recipe-linked projection, and candidate-domain inputs).
   Each such owner needs an exact compatibility proof or a versioned successor.
   This must not be a solution-derived translation or override; otherwise it
   creates a source-plan/solution back-edge.
3. **Deferral:** retain the core candidate as a planning artifact outside the
   semantic namespace until a later source-inventory program resolves it.

The current measured mismatch rules out outcome 1.  No namespace implementation
may assume a simple append-only admission while this state is unresolved.

## 3. Proposed minimal semantic projection (conditional)

If and only if §2 is resolved, create one suite-level external semantic body.
These names are candidates, not issued identifiers.

| field | candidate value |
| --- | --- |
| artifact schema | `kcs.persona.pc-core-extension-allocation-content-projection/v1` |
| artifact kind | `persona-pc-v2-core-extension-allocation-content-projection` |
| projection class ID | `core-extension-allocation` |
| body ID | `persona-core-v1-extension-allocation-content-projection-rows-v1` |
| row schema | `kcs.persona.pc-core-extension-allocation-content-projection-row/v1` |
| body framing | canonical JSON per row, UTF-8 NFC, exactly one LF per row |
| namespace coordinates, when admitted | `{ "profile_id": "persona-core-v1" }` |
| expected projection entries, when admitted | exactly 1 |

The semantic body has no descriptor, receipt, authority, completion claim, or
input pin.  A future namespace stores only its standard six-field body pin:
`artifact_kind`, `artifact_schema`, `artifact_schema_version`, `body_framing`,
`canonical_bytes`, and `sha256`.  It embeds no body and no source artifact.

### 3.1 Exact projected row schema

Each of the 566 source rows maps one-to-one to one projected row.  The exact
key set contains the following 13 fields; there are no optional fields.

```text
schema_version = 1
row_schema = kcs.persona.pc-core-extension-allocation-content-projection-row/v1
profile_id
persona_id
family_id
variant_id
filename_extension
compound_suffix_parts
gate_role
expected_offline_disposition
full_count
pilot_count
tiny_count
```

`full_count`, `pilot_count`, and `tiny_count` are exact non-boolean integers.
`compound_suffix_parts` is a nonempty ordered bounded NFC string array; every
other retained scalar is a bounded NFC string.  Output order is canonical by
`persona_id`, `family_id`, and `variant_id`, not by a source-plan, source-ID,
or capacity assignment order.

This is an allocation *outcome* projection.  It intentionally omits
`row_id`, family/variant ordinals, `variant_weight`, and family aggregate
counts because those are derivation/order mechanics once the per-variant counts
are fixed.  Suite aggregates can be recomputed from the body and do not need to
perturb namespace identity separately.

### 3.2 Explicit exclusions

The projected body excludes all of the following source-row fields:

```text
row_id
family_ordinal
variant_ordinal
variant_weight
family_full_count
family_pilot_count
family_tiny_count
renderer_binding_id
validator_binding_id
format_registry_sha256
```

It also excludes every source ID, logical-document ID, scope/path key,
physical path, raw hash, payload/body text, section ID, capacity cell,
source-to-cell assignment, source-plan coordinate, query, oracle, answer,
history/cohort/event/checkpoint, solver output, final plan, renderer directive
or probe, review result, actual file/chunk/latency/cost measurement, filesystem
receipt, and authority/completion field.

`expected_offline_disposition` is retained only as an authored allocation
property.  It is not a claim that a file was created, indexed, readable,
searchable, or yielded any number of chunks.

## 4. Separate derivation receipt

Provenance is not semantic projection content.  The projector instead produces
a separate canonical `projection-derivation-receipt` that is never embedded in
or pinned directly by the namespace.  A later complete-inventory successor may
bind that receipt, and a later corpus evidence closure may bind its review and
validation evidence.

The receipt may contain only:

```text
receipt identity/schema/version and projector identity/version
the new semantic-body standard six-field pin
the frozen source descriptor full-owner pin
the frozen source rows direct-body pin
field allowlist/version and deterministic transformation name
derived planned row/aggregate checks
independent validation result and bounded canonical limits
```

The receipt rejects all `authorizes_*`, authority, completion, issuance, G0,
actual-observation, query, history, solution, source-instance, and runtime
receipt fields.  Successful derivation is not an authority grant.

The source descriptor full-owner pin follows the existing receipt convention,
including an explicit empty coordinate map:

```json
{
  "artifact_kind": "persona-core-v1-extension-allocation-manifest-candidate",
  "artifact_schema": "kcs.persona.core-extension-allocation-manifest/v1",
  "artifact_schema_version": 1,
  "body_framing": "canonical-json",
  "canonical_bytes": 5357,
  "sha256": "ca7caa3813d8f359785cb4dc65e7155f6e36153ba651e1a4b3af0d3695780e9f",
  "coordinates": {},
  "owner_id": "persona-core-v1-extension-allocation-manifest-v1",
  "owner_role": "frozen-content-candidate-descriptor"
}
```

The source rows direct-body pin is:

```json
{
  "body_framing": "canonical-jsonl-lf",
  "canonical_bytes": 426889,
  "direct_pin_id": "persona-core-v1-extension-allocation-rows-v1",
  "direct_pin_role": "frozen-content-candidate-rows",
  "sha256": "f31f696e1692758e4fc52133dba733af77b74d16711034ee05d75b16d64f7d45"
}
```

The receipt's planned checks must recompute from the projected body only:
566 rows; 20 personas; 15 families; 71 variants; 39 physical extensions; 539
full-nonzero rows; full/pilot/tiny totals 203,000/20,300/4,000; and full role
totals 68,761/62,978/71,261.  These remain allocation targets, never actual
capacity or file/chunk observations.

## 5. Producer and independent-validator requirements

When §2 authorizes implementation, create a projector, a separate independent
validator, and focused tests.  The validator must not import the projector.
Neither module may import or invoke `persona_v2_format_implementation_registry`
or a renderer probe.

The source input boundary is exactly two artifacts:

1. source allocation descriptor: read twice into independently owned canonical
   JSON snapshots; and
2. source external rows: passed to the existing independent
   `accepted_core_extension_allocation_body_bytes()` validation path, which
   receives the accepted descriptor snapshot plus a
   `body_provider(ARTIFACT_ID, BODY_ID)`, opens the rows exactly twice, and
   returns its accepted second owned buffer.

The projection must derive solely from that accepted second owned buffer and
must not reopen the rows.  The core validator's family-matrix, envelope, and
static consumed-registry checks are delegated validation dependencies; they are
not new semantic-body fields or direct namespace provenance.  Provider mutation,
alias, swapped ID/body, duplicate key, non-NFC string, CRLF, missing LF, float,
boolean-as-integer, unknown key, deep object, or oversized value fails closed.

The independent validator must independently:

1. authenticate the two source pins and obtain the accepted source body through
   the existing independent core validator;
2. require all 566 source rows to have the frozen 23-key source schema;
3. apply only §3.1's 13-field allowlist and canonical output order;
4. verify the 13-key projected schema, uniqueness, and one-to-one coverage;
5. recompute every §4 planned aggregate from projected rows;
6. reject every §3.2 field/category from the semantic body and receipt's
   prohibited authority or execution/source/path/cell-coordinate categories
   (while permitting only the receipt's exact empty full-owner-pin
   `coordinates: {}`); and
7. authenticate the new semantic body twice, compare it to independent
   regeneration, and postflight all caller/provider-owned inputs.

Use canonical sorted-key compact JSON, UTF-8 NFC, depth at most 32, and a
final LF.  Assign exact new byte/SHA goldens only after `fast -> pre-freeze full
-> cold hash-seed 0/1 -> producer/independent-validator agreement`.  A formal
Golden-Freeze Decision/Gate remains separate and cannot be simulated by a
descriptor boolean.

## 6. Future inventory/namespace admission

No existing artifact changes:

- complete inventory v2 and corpus semantic namespace v3 remain byte-for-byte
  frozen;
- v3's 253 entries and 12-class registry retain their existing meaning; and
- the W0 history pre-solve slice remains bound to v3 and is not backfilled.

The source-semantic v2 plan currently closes namespace v4 over content owners
1--3 (capacity axis, truth/occurrence policy, and candidate-domain).  The core
projection must not be silently added to that closed owner set.  It must first
resolve both the §2 allocation-truth conflict and the owner-set decision.

For an additive-reuse outcome, the complete-inventory successor must dispatch
legacy receipts to the frozen v2 provider and the one new allocation receipt to
its new provider; it must not extend or replace the v2 provider.  A namespace
successor then consumes only that successor inventory, not a second direct
allocation argument.  Its legacy 253 entries **must** be the exact v3 prefix
(same pins, coordinates, class order, and namespace ordinals), and the one
`core-extension-allocation` entry must occur exactly once with a body SHA that
aliases no other suite body.  This prefix rule is available only when no
conflicting legacy content projection is retained under a new meaning.

For a supersession outcome, the decision must identify the new source-content
owner set, audit the full transitive allocation-dependent legacy content
closure, and create every required versioned successor.  It must not claim that
a v3 prefix has the same source-allocation semantics.  v2/v3 themselves still
remain immutable.

The admission decision must also resolve the external-body budget explicitly:
v2/v3 use a 256 MiB cumulative cap with 155,741,469 bytes already bound,
leaving 112,693,987 bytes under that same cap.  The source-semantic v2 proposal
uses a separate 256 MiB budget for new bodies.  A successor must state whether
it retains the old total cap or adopts a new total cap; it may not silently add
the two interpretations.

Regardless of outcome, the future namespace has no new renderer directive,
renderer probe, or renderer execution authority.  This does not rewrite or
remove any already frozen legacy `renderer_policy` content pin.

## 7. Required ordering and formal decision

The local freeze record is evidence, not a decision-log entry.  Before any
admission, record a separate formal Manifest Golden-Freeze Decision/Gate with
the two source pins, replay evidence, all-false source authority boundary, and
the statement that it issues no namespace, solver, source, history, or G0 work.
Because `tasks/ws1c-decisions.md` has user-owned in-progress changes, do not
edit it incidentally as part of this proposal.

The safe order is:

```text
allocation descriptor/body local freeze
  -> formal manifest Golden-Freeze Decision/Gate
  -> independent legacy allocation compatibility owner (§2)
  -> conditional allocation content projection candidate + receipt/freeze
  -> capacity-axis v1 -> truth/occurrence policy v1 -> candidate-domain v1
  -> formal owner-set and total-body-budget reconciliation
  -> complete inventory successor + corpus semantic namespace successor
  -> pre-solve corpus/evaluation closures
  -> namespace-only joint solution/proof
  -> final source plan / planned history
```

The three capacity owners may progress independently where their own contracts
allow it, but none may issue a v4-or-later namespace without the compatibility
and owner-set gates.  This projector never creates files and does not authorize
the separately requested Phase 2 corpus materialization.

## 8. Acceptance and non-claims

This design work is acceptable only if all statements below remain true:

- [ ] `legacy_source_allocation_compatibility` is explicitly unresolved until a
      dedicated independent owner chooses a valid outcome from §2.
- [ ] The semantic body is the 13-field, one-to-one allocation-outcome
      projection; it contains no provenance, authority, or runtime coordinate.
- [ ] Full-owner/direct-body pins, projector identity, and validation result are
      confined to a derivation receipt outside the semantic body and namespace.
- [ ] Renderer/validator/registry bindings, source/path/cell/query/history/
      solution fields, and execution authority are rejected from the body.
- [ ] Any supersession first audits the full transitive set of allocation-
      dependent legacy content owners; no stale per-intent owner is silently
      reused under a new allocation truth.
- [ ] The projector delegates source-body authentication to the existing
      independent validator and never opens a third source-body read.
- [ ] v2/v3 immutability, the capacity owner order, legacy renderer-policy pins,
      and total-body-cap ambiguity are all preserved for formal reconciliation.
- [ ] No new namespace, file, history, observed chunk, searchability, latency,
      cost, recall, dogfood, or MVP-Done claim is made.
