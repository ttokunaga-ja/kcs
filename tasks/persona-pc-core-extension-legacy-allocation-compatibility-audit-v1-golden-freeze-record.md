# Persona-PC core-vs-legacy allocation compatibility audit v1 — local golden-freeze record

Status: frozen **count-only incompatibility audit candidate**; not an adoption
decision, namespace artifact, source plan, write authority, history authority,
evaluation authority, or G0 gate.

## Frozen output

| item | canonical bytes | SHA-256 |
| --- | ---: | --- |
| audit descriptor | 3,500 | `cceb525f9e3b4912b6ea582f9fe0596056ad257b6ef8a875365d79ebc40883f1` |
| external delta JSONL | 236,068 | `a755ef7ee770796f7d0a02c261c706089b23b6a016a766d6962e600bf027de44` |

Identity:

```text
schema: kio.persona.pc-core-extension-legacy-source-allocation-compatibility-audit/v1
artifact: persona-core-v1-legacy-source-allocation-compatibility-audit-v1
delta body: persona-core-v1-legacy-source-allocation-delta-rows-v1
delta row schema: kio.persona.pc-core-extension-legacy-source-allocation-delta-row/v1
```

The body has 489 union-mismatch rows, ordered by persona, declared family
order, then ASCII variant ID.  Its maximum LF-inclusive row size is 529 bytes.

## Frozen inputs

| input | canonical bytes | SHA-256 |
| --- | ---: | --- |
| core extension allocation descriptor | 5,357 | `ca7caa3813d8f359785cb4dc65e7155f6e36153ba651e1a4b3af0d3695780e9f` |
| core extension allocation external rows | 426,889 | `f31f696e1692758e4fc52133dba733af77b74d16711034ee05d75b16d64f7d45` |
| legacy v2 variant catalog | 211,733 | `807dd3cdd8df613ac21e6ba64877fb5abb40c72ed4949abaa0d440a449e7f9e9` |

The comparison coordinate is exactly
`(persona_id, family_id, variant_id)`.  It compares only `full_count` and
`pilot_count` under exact integer equality.  It intentionally excludes the
repeated family aggregates, source-instance information, renderer metadata,
and core `tiny_count` (the legacy catalog has a different `tiny_smoke_count`
concept).

## Reproduced result

| measure | value |
| --- | ---: |
| coordinates | 566 |
| full totals (core / legacy) | 203,000 / 203,000 |
| pilot totals (core / legacy) | 20,300 / 20,300 |
| full mismatches | 489 |
| pilot mismatches | 483 |
| union mismatches | 489 |
| full-only mismatches | 6 |
| pilot-only mismatches | 0 |
| full L1 delta | 70,500 |
| pilot L1 delta | 7,050 |

For example, p01/docx has core full/pilot counts `24/2`, while the legacy
catalog has `360/36`.  Matching suite totals do not establish cellwise
compatibility.

## Local verification evidence

| gate | result |
| --- | --- |
| focused audit test | 7 passed, 1 skipped |
| core manifest + legacy catalog + audit focused regression | 31 passed, 3 skipped |
| opt-in two-seed cold replay | passed (`PYTHONHASHSEED=0/1`) |
| audit input calls | descriptor, core body, legacy catalog, and delta body each exactly two reads in the independent validator |

The audit accepts an incompatible result as a valid diagnostic output, but
fails closed for coordinate drift, duplicate/missing rows, input/body swaps,
noncanonical rows, changed pins, mutable provider outputs, or any attempt to
claim downstream authority.

## Still blocked

This record sets neither allocation truth.  The required next decision is one
of: exact additive reuse after an independent zero-mismatch proof (currently
disproved), content-owner supersession with a full dependency-closure audit, or
deferral outside the semantic namespace.  It does not amend the decision log
or issue `corpus-semantic-namespace/v4`.
