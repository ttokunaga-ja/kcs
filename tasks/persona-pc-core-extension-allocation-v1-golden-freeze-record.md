# Persona-PC core extension allocation v1 — local manifest golden-freeze record

Status: frozen content-only candidate; not issued; no G0 authority.

Date: 2026-07-23

This is the working-tree-local evidence record for the separate Manifest
Golden-Freeze Gate described by
`tasks/persona-pc-core-extension-allocation-v1-proposal.md`.  It does not
amend the decision log, issue a content-only namespace entry, authorize a
solver, or authorize source instances, rendering, filesystem writes, history,
Kio, evaluation, or actual chunk claims.

## Frozen descriptor and external body

| item | exact value |
| --- | --- |
| descriptor schema | `kio.persona.core-extension-allocation-manifest/v1` |
| descriptor canonical bytes | 5,357 |
| descriptor SHA-256 | `ca7caa3813d8f359785cb4dc65e7155f6e36153ba651e1a4b3af0d3695780e9f` |
| external body ID | `persona-core-v1-extension-allocation-rows-v1` |
| external LF-JSONL bytes | 426,889 |
| external LF-JSONL SHA-256 | `f31f696e1692758e4fc52133dba733af77b74d16711034ee05d75b16d64f7d45` |
| rows / full non-zero rows | 566 / 539 |
| first row | `persona-core-v1-extension-p01-md-md`, 745 bytes, `351991d32d2b21171ec21a77fd3ba2a52ef89638e845cf2ce590addeba885fb5` |
| last row | `persona-core-v1-extension-p20-domain_binary-source-drop-ustar`, 778 bytes, `e663127e173334127c6333909370038fa83181d903a1866a9d1380711fd0b09b` |
| maximum LF-inclusive row bytes | 786 |

The producer and independent validator both carry the identical descriptor
golden tuple.  The body pin remains independently required even before and
after descriptor validation.

## Input boundary

The allocation consumes only these pinned input projections:

| input | bytes / SHA-256 |
| --- | --- |
| core family-count matrix | 2,410 / `045d85cf7325d0ec51217f61f2069b6dd145bfcb3b4477b4eb005d0a800d9ab7` |
| persona-PC envelope | 71,979 / `12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7` |
| all-71 format implementation registry | 333,881 / `59ae0b2e5c755732e6937e70ada4b243ea2c7432a9ce654c7e9c219b4a13bc5d` |

The all-71 registry is consumed through a frozen 22,639-byte, SHA-256
`a2cf577c178bda8373952e087df5e5decba60d38fd875c13fc374f15410d0f57`
read-only projection.  It contains exactly the allocation-needed variant ID,
family, suffix, role, offline disposition, and renderer/validator binding
fields, and binds the full registry hash above.  This deliberately prevents a
content-only allocation validation from running the registry's renderer probe
implementation.  It does not weaken the full registry pin or claim that a
source was rendered.

Both the producer's fixed providers and the independent validator's injectable
providers replay matrix, envelope, and registry-projection inputs twice and
require byte-for-byte equality.  The validator reads the external JSONL body
twice, creates owned buffers, accepts the second one only, and exposes it via
`accepted_core_extension_allocation_body_bytes()` without a third provider
open.

## Reproduced invariants

- Full/pilot/tiny totals: 203,000 / 20,300 / 4,000.
- Gate-role full totals: 68,761 contributor / 62,978 incidental / 71,261 raw-only.
- 71 variants are positive in full; physical extensions total 39.
- All twenty persona rare-family splits, declared zero rows, family-local
  ordinal resets, and nested Hamilton bounds are covered by the focused gate.
- Descriptor unknown fields, wrong identity, non-NFC/noncanonical bytes,
  Boolean-as-integer rows, deep values beyond 32 nesting levels, input swaps,
  body swaps, and caller/provider mutation fail closed before acceptance.
- The producer and validator do not import the implementation-registry module;
  allocation validation does not invoke renderer probes.

## Local verification evidence

| gate | result |
| --- | --- |
| focused fast gate | 15 passed, 2 opt-in skipped |
| post-freeze full gate (`KIO_RUN_CORE_EXTENSION_ALLOCATION_FULL=1`) | passed |
| post-freeze two-seed cold gate (`KIO_RUN_CORE_EXTENSION_ALLOCATION_COLD=1`) | passed |
| direct `PYTHONHASHSEED=0/1`, `LANG=C`, `LC_ALL=C`, `TZ=UTC` replay | identical descriptor and body bytes/SHA |
| independent re-audit | no remaining implementation freeze blocker |

Remote CI remains unverified.  These local receipts are external evidence and
cannot turn this descriptor into an issued namespace artifact or an execution
authority.

## Still blocked after this gate

The next required work is content-only namespace admission and the separate
pre-solve closures, then the query-independent joint solution/proof.  A final
source plan must bind both that solution/proof and this frozen manifest.  Only
later, separately authorized stages may render/write sources, produce history,
run Kio, or execute M3 evaluation.
