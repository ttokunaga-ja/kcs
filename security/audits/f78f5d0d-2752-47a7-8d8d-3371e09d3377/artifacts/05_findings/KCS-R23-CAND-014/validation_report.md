# Validation: Unrecognized binary gaps disappear from durable completeness and path telemetry

- Candidate: `KCS-R23-CAND-014`
- Instance key: not supplied
- Ledger row id: `KCS-R23-CAND-014`
- Advisory/source reference: R23 discovery; no advisory or distinct seed anchor supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-cli/src/main.rs:9120-9169`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.99)**
- Method: **V9 durable-observability reproduction + V8 state readback + V10 exact static trace**

## Rubric

- [x] A normal repository input can be archived as `application/octet-stream` while yielding no locally extractable text.
- [x] The skip branch creates no task or durable per-path unsupported disposition.
- [x] The one-run counter and event disclose the class of gap but the retained event omits the affected path.
- [x] Later public `status` and search completeness are derived without the skipped file and can claim no pending work/full enrichment.
- [x] A recognized text file in the same scope remains searchable, proving the observation is specific to unsupported input rather than a failed index.

## Evidence

When `prepare.prepared_units` is empty, `crates/kcs-cli/src/main.rs:9120-9150` enqueues online OCR only for a recognized OCR-able media type. The `application/octet-stream` branch at `:9151-9169` increments an in-memory result counter and writes an INFO event, but creates no task or persistent unsupported-file record. Its event context includes only `media_type` and `size_bytes`, not `candidate.input_path`.

The counter reaches only the current index response at `crates/kcs-cli/src/main.rs:656-671`. Public `status` later emits archive file status plus task rows at `:435-450`; neither field states that an unchanged archived file has no searchable representation. Search completeness at `:2417-2506` counts Markdownize and Embedding tasks only and returns `enriched_ratio=1.0` when all existing tasks are done (or none exist), so a skipped input with no task is absent from both numerator and denominator.

A private offline CLI reproduction under `/tmp/kcs-r23-d2-014` used a 17,097-byte inert binary named `photo.bmp` and a recognized `ok.md` control:

1. `index --yes --json` archived both files and reported `skipped_unrecognized_binary_files=1`, `normalized_files=1`, and no pending or failed work.
2. Subsequent `status --json` listed `photo.bmp` merely as `unchanged`; its task list contained only the completed Markdownize task for `ok.md`.
3. Search returned the recognized text and reported `enriched_ratio=1.0`, `pending_enrichment_tasks=0`, and `budget_paused=false`.
4. The retained `KCS-I-INDEX-INPUT-UNRECOGNIZED-BINARY-001` event recorded `application/octet-stream` and `size_bytes=17097` but contained no `photo.bmp` path. The archived tree still named `photo.bmp` and its raw hash, confirming preservation without searchable/disposition state.

This is the exact false-completeness and non-actionability path required by invariants I4/I10: the invocation reports a count, but durable product state cannot identify or account for the unsupported file.

## Counterevidence and preconditions

- Raw bytes are preserved in the content-addressed archive; there is no data destruction or network transmission.
- A caller that retains the immediate index response learns the number of skipped binaries, and rerunning index repeats the count.
- The impact is incomplete search and misleading workflow state, not a confidentiality, authorization, or budget bypass.
- A content contributor must supply an unsupported binary and the operator must index the scope.

These facts bound severity but do not make the later full-enrichment state accurate or path-actionable.

## Tests and remaining uncertainty

The reproduction used unique `HOME` and `XDG_*` directories, a private temporary scope, offline execution, no credentials, and no external network. It inspected the real CLI response, task store projection, search status, event log, and archived tree. No repository file was changed.

Proof gap: none for the durable observability claim. The minimal remediation test should assert a persistent path-bearing unsupported disposition after the original index response is gone and include that disposition in completeness/status semantics.

## Closure

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|---|---|---|
| KCS-R23-CAND-014 | not supplied | R23 discovery | — | `crates/kcs-cli/src/main.rs:9120-9169` | unsupported binary direct child of indexed scope | `status` at `main.rs:435-450`; task-only completeness at `:2417-2506` | reportable / medium / high 0.99 | raw bytes preserved and one-run count exists; no proof gap | yes |

Validation artifacts: none (ephemeral `/tmp` reproduction; no retained PoC files).
