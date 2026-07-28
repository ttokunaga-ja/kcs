# Persona-PC v2 formal-leaf placement binding v1 — local golden-freeze record

Status: frozen content-only planning candidate; not issued; no G0 or execution authority.

Date: 2026-07-23

This record freezes the deterministic join of the current v2 topology and the
non-authorizing device-lane compositor.  It does not create a device root,
directory, registry, file, history entry, Kio index, query result, or actual
chunk.  It also does not select an allocation/source-plan successor.

## Frozen descriptor and external body

| item | exact value |
| --- | --- |
| descriptor schema | `kcs.persona.pc-formal-leaf-placement-binding/v1` |
| descriptor canonical bytes | 27,117 |
| descriptor SHA-256 | `de518d1fef7a6955462774ace7321943ff5ca918be7f6210380890fca78857f8` |
| external body ID | `persona-pc-v2-formal-leaf-placement-rows-v1` |
| external body framing | canonical UTF-8 NFC LF-JSONL |
| external LF-JSONL bytes | 889,056 |
| external LF-JSONL SHA-256 | `98e7239f498c8ebff3f2c754a24036ac7c5263a2f5f6b2bb66275ceaccd8f66e` |
| rows | 1,200 = 3 replays × 20 personas × 20 scopes |
| row order | replay → persona → scope ordinal |
| registries planned | 60 = 3 replays × 20 personas |
| scope kinds | 720 primary / 480 secondary |
| depth distribution | D2=69, D3=564, D4=339, D5=132, D6=96 |
| maximum LF-inclusive row bytes | 835 |

The `body_descriptor_golden_frozen` flag is true only for these content
receipts.  `g0_contract_frozen`, all materialization/Kio/history authority
flags, and all observed-completion claims remain false.

## Input boundary

The candidate consumes only the two exact upstream artifacts below.  It does
not consume a family allocation, source inventory, semantic namespace,
format registry, source recipe, history plan, or query plan.

| input | canonical bytes / SHA-256 |
| --- | --- |
| topology v2 (`kcs.persona.pc-topology/v2`) | 134,195 / `204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f` |
| device-lane compositor v1 (`kcs.persona.pc-device-lane-compositor/v1`) | 41,099 / `eb1a82d631b810ca96d90c84f9324263b4bb1018f0cde2a8339037a183d35bdf` |

Both producer and independent validator read and authenticate each upstream
twice.  The validator then regenerates every row independently, reads the
external body twice, accepts only an owned second read, and verifies both the
whole scope-registry digest and the ordered leaf-root projection digest.  The
descriptor additionally holds 60 per-`(replay, persona)` registry summaries.
Those are planning digests, not on-disk registry receipts.

## Frozen semantics

For each row, the binding fixes only:

- replay and persona identity/order;
- the topology scope key, kind, functional slot, relative path, and depth;
- the compositor-derived `home_root` and isolated `registry_root`; and
- `leaf_root = home_root / relative_path` with `direct_child_only=true` and
  `runtime_scope_id_assigned=false`.

It deliberately holds no filename, file format, source ID, fact/query ID,
quota, chunk count, byte count, writer input, or observed scope ID.  Therefore
the statement `direct_child_only=true` is a downstream writer requirement, not
a claim that a direct child was written or indexed.

## Local verification evidence

| gate | result |
| --- | --- |
| focused binding gate | 9 passed |
| producer ↔ independent validator | descriptor/body accepted; two-read providers verified |
| strict JSON checks | duplicate key, BOM, whitespace/noncanonical body rejected |
| tamper checks | authority, registry/path/digest, body order/truncation, and upstream drift rejected |
| cold replay | `PYTHONHASHSEED=101` and `907` reproduced all four frozen receipts |

This is local evidence only.  No remote CI, filesystem, external API, OCR,
Kio, history, M3, or baseline evaluation was run.

## Still blocked

The next P0 items are a direct-child writer guard and a Kio direct-child
regression; both must reject a nested managed file rather than let it silently
fall outside the present scope scanner.  A later source-plan binding must join
this frozen placement body with the chosen allocation truth, exact source
instances, path quotas, format/index-route ledger, and root-bound capacity
gate.  Only after separate authorization may any physical materialization,
readback receipt, history execution, Kio run, or evaluation begin.
