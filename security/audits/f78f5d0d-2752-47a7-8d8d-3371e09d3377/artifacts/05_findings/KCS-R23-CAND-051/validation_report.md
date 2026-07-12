# Validation: Duplicate OCR page indices bind one provider page to multiple evidence units

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-051 |
| Instance key | KCS-R23-CAND-051:duplicate-page-index-content-misbinding |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-adapter/src/mistral_ocr.rs:356-395 |
| Root control | crates/kcs-adapter/src/mistral_ocr.rs:229-276 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Confidence score | 0.99 |
| Severity | medium |
| Validation method | V1 bounded pure mapping control plus V10 complete source-to-sink trace |

The candidate survives as a Medium integrity defect at the approved remote OCR response boundary. Duplicate provider page indices deterministically overwrite one page in the index map; the positional fallback then reuses the surviving page for the missing index. KCS synthesizes distinct unit keys from trusted request hints, so coverage validation passes and the task can be persisted as Done even though one source page is lost and another is duplicated.

## Validation rubric

- [x] Source: `parse_ocr_response` accepts each remote `pages[].index` independently and performs no uniqueness, range, or completeness check at `crates/kcs-adapter/src/mistral_ocr.rs:356-395`.
- [x] Root control: collecting `(page.index, page)` into a `BTreeMap` overwrites an earlier duplicate, then lookup falls back to response position at `crates/kcs-adapter/src/mistral_ocr.rs:249-263`.
- [x] Safe reproduction: the bounded pure control maps `[(0,A),(0,B)]` to `[B,B]`, while the unique-index negative control maps `[(0,A),(1,B)]` to `[A,B]`.
- [x] Closest acceptance: full-response validation compares synthesized hint unit keys and unit shapes, not provider page identity, at `crates/kcs-pipeline/src/markdownize.rs:476-511`.
- [x] Sink: the CLI treats the fully covered response as strict-valid, marks it Done, and persists the normalized units at `crates/kcs-cli/src/main.rs:6674-6696,6714-6789`.

## Exact source, control, sink, and boundary

- Source and boundary: an approved Mistral-compatible OCR response controls the order, `index`, and markdown of every `pages[]` entry. `parse_ocr_page` uses the supplied unsigned index when present and only uses enumeration order when it is absent; it never rejects duplicates.
- Root-control gap: `MistralOcrMarkdownizeAdapter::markdownize` collects page references into a `BTreeMap<usize, &OcrPage>`. Standard collection semantics retain the last value for a duplicate key. It then resolves each prepared hint by indexed lookup and, if absent, by the response vector at that numerical position.
- Exact construction: for provider pages `[(0,A),(0,B)]` and prepared orders `[0,1]`, the map is `{0:B}`. Order 0 selects B from the map; order 1 misses the map and selects response position 1, also B. The adapter assigns the two different prepared `unit_key` values to those two outputs.
- Closest control: `validate_full_response` compares the set of expected prepared keys with the set of adapter-produced keys, and `validate_unit_shapes` checks non-empty markdown and unit type. Because keys and types come from the hints rather than the provider page identity, both checks pass.
- Sink and impact: the full online executor records strict validity, builds normalized units, computes a Done status, and persists them. Downstream chunks and evidence therefore attribute B to both unit keys while A is absent, corrupting search and provenance without a retry signal.

## Evidence and safe control

- All repository source was read from immutable revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`.
- `validation_artifacts/mapping_control.json` records a six-element, network-free pure model of the exact map/fallback operations. The attack result is `[page-B,page-B]`; the unique-index control preserves `[page-A,page-B]`.
- No credentials, external service, KCS store, repository file, or production input was used or modified.

## Counterevidence and severity calibration

- The official provider is expected to return well-formed, unique indices; exploitation requires a malformed, compromised, redirected, or compatible endpoint response after the user has enabled the online adapter.
- The response still needs non-empty markdown to pass unit-shape validation. This does not restore the missing page-to-unit binding.
- The demonstrated effect is integrity and provenance corruption within the OCR task, not arbitrary code execution, credential exposure, or cross-scope file access.
- The behavior is deterministic once duplicate indices cross the response boundary, and the task's Done state removes the normal retry/reconciliation signal. These facts support Medium rather than suppression or Low.

## Proof gap and next step

No live provider was contacted. The exact V10 trace and deterministic bounded model close the source, mapping, acceptance, and persistence tuple for Medium. A regression should reject any response unless page indices are unique, in range, and form the exact expected bijection before content is assigned to unit keys; positional fallback must not conceal an explicitly indexed malformed response.

## Closure row

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-051 | KCS-R23-CAND-051:duplicate-page-index-content-misbinding | R23 deep discovery; no external advisory | crates/kcs-adapter/src/mistral_ocr.rs:356-395 | crates/kcs-adapter/src/mistral_ocr.rs:249-263 | approved remote OCR `pages[].index` and markdown | hint-key acceptance then Done persistence at crates/kcs-pipeline/src/markdownize.rs:476-511 and crates/kcs-cli/src/main.rs:6674-6789 | reportable | normal provider should be well formed; no live service needed for deterministic mapping proof | yes |
