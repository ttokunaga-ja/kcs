# Validation: Mistral OCR responses lack read, body, cardinality, and persistence bounds

- Candidate: `KCS-R23-CAND-020`
- Instance key / ledger row: `KCS-R23-CAND-020`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.96)**
- Method: **V5 bounded existing controls/tests + V10 exact static trace; no network**
- Root control: `crates/kcs-adapter/src/mistral_ocr.rs:112-138,356-422`

## Rubric

- [x] The normal online OCR workflow reaches the real response parser and persistence sinks.
- [x] The nearest transport controls were inspected, including dependency defaults and configured timeout wiring.
- [x] Response bytes, decompressed bytes, pages, markdown, images, decoded image bytes, and disk writes were checked independently.
- [x] Existing input/page-scoping, shape, CAS, and acceptance controls were treated as counterevidence rather than presumed absent.
- [x] Each claimed subpart was closed and impact was calibrated to the approved remote-adapter boundary.

## Exact trace and evidence

The supported CLI send path rechecks the current input and the configured input cap at `crates/kcs-cli/src/main.rs:6533-6552`, prepares the request, and invokes the standard online adapter at `crates/kcs-cli/src/main.rs:6576-6691`. The catalog constructs the real Mistral adapter and calls it at `crates/kcs-adapter/src/catalog.rs:82-147`.

The OCR client rereads the bounded local input and builds a base64 JSON request at `crates/kcs-adapter/src/mistral_ocr.rs:112-135`. It then calls `into_json()` directly at lines 135-137. The pinned dependency is `ureq 2.12.1` (`Cargo.lock:1396-1397`). Its default agent has a 30-second connect timeout but no read, write, or overall timeout (`ureq-2.12.1/src/agent.rs:251-264`). Its `into_json` delegates to `serde_json::from_reader` without a byte ceiling (`ureq-2.12.1/src/response.rs:531-536`); the dependency itself instructs untrusted callers to apply `.take()` to bound response bytes (`response.rs:248-259`). Gzip is enabled by the resolved feature graph, and decompression wraps the body reader before JSON parsing without a decoded-size ceiling (`response.rs:640-673`).

After full JSON materialization, every response page is collected at `crates/kcs-adapter/src/mistral_ocr.rs:356-364`; every page markdown string is cloned and every image is collected at lines 375-395; every base64 image string is decoded into a second byte buffer at lines 398-422. The adapter persists the images from every returned page before the caller's acceptance check at `crates/kcs-adapter/src/mistral_ocr.rs:229-235`. `persist_images` iterates and writes every distinct image object with no per-response or aggregate quota at lines 570-594. The later response acceptance check is at `crates/kcs-cli/src/main.rs:6694-6696`, after that persistence.

Bounded, network-free existing tests passed:

- `q2_persist_images_writes_hash_consistent_object` proves that an accepted image is materialized in CAS.
- `r14_4_full_send_has_no_pages_parameter`, `r14_4_incremental_scopes_pages_to_changed_units`, and `r15_5_unit_scoped_retry_scopes_pages_despite_full_mode` prove request-page scoping behavior.

Those tests use small values and do not impose or test response-size, response-page, response-image, decoded-byte, or persistence quotas.

## Claimed-subpart closure

| Subpart | Decision | Evidence |
|---|---|---|
| No time bound | **survives, narrowed** | Connect is bounded to 30 seconds by ureq, but read/write/overall time remain unbounded and the accepted `timeout_seconds=300` is explicitly not threaded at `crates/kcs-core/src/scope.rs:1581-1590`. |
| Unbounded request body | **does not independently survive on the supported CLI path** | `effective_max_input_bytes` is rechecked before the adapter call at `main.rs:6533-6552`; base64 expansion is large but bounded by that configured input cap. Direct adapter use has no internal cap, but the shipped CLI boundary supplies one. |
| Unbounded wire/decompressed response body | **survives** | Direct `into_json` with no `.take()`; gzip decompression precedes JSON parsing without a decoded-size cap. |
| Unbounded page/markdown cardinality | **survives** | All pages and markdown strings are collected with no count/length guard at `mistral_ocr.rs:356-395`. Request page scoping is not a response maximum. |
| Unbounded image count/decoded bytes | **survives** | All images are iterated and base64-decoded at `mistral_ocr.rs:375-422` without per-image or aggregate limits. |
| Unbounded persistence | **survives** | Every page's images are persisted before response acceptance at `mistral_ocr.rs:229-235,570-594`; content-addressed deduplication and atomic publication protect integrity, not quota. |

## Counterevidence and impact

Online execution requires operator authorization; the input has a configurable/default 100 MiB cap; incremental and unit-retry requests can restrict requested pages; HTTP connection establishment has a 30-second timeout; JSON shape errors fail; image objects are content-addressed and crash-atomically published; later acceptance checks can reject incomplete page output. These controls narrow the source and protect integrity, but none bounds a connected peer's response read, decoded expansion, response cardinality, or pre-acceptance image persistence.

The realistic effect is command hang or substantial memory, CPU, and disk consumption during an approved online OCR operation. It is not an authentication or confidentiality bypass and requires a faulty/hostile configured service or intermediary, so the final severity is Medium.

## Remaining uncertainty and next step

No loopback timing/body experiment was run under the read-only/no-network constraint. The exact source and pinned dependency defaults settle the missing controls; runtime measurement would refine constants, not disposition. Remediation should use one bounded OCR transport policy that enforces configured overall/read/write deadlines, compressed and decompressed response limits, page/markdown/image/decoded-byte limits, and a pre-persistence aggregate quota. The model-list request is tracked separately as `KCS-R23-CAND-022`.

Validation artifacts: none.
