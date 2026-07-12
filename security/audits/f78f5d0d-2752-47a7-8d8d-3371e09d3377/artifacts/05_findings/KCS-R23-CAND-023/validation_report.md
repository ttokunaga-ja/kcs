# Validation: Gemini embedding responses lack body and read-time bounds before semantic checks

- Candidate: `KCS-R23-CAND-023`
- Instance key / ledger row: `KCS-R23-CAND-023`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.98)**
- Method: **bounded parser/control tests + V10 exact static/dependency trace; no network**
- Root control: `crates/kcs-adapter/src/gemini_embedding.rs:120-149`

## Rubric

- [x] Both shipped embedding consumers were traced to the real Gemini response path.
- [x] The configured timeout and pinned HTTP dependency defaults were checked at the closest control.
- [x] Full-body materialization was ordered before response count, numeric-type, and dimension validation.
- [x] Batch-size, error fallback, post-parse shape checks, and fixed-model behavior were assessed as counterevidence.
- [x] Availability impact and neighboring candidate boundaries were explicitly scoped.

## Exact trace and evidence

Real activation selects `GeminiEmbeddingAdapter::default()` at `crates/kcs-adapter/src/catalog.rs:303-333,386-401`. The default profile uses the fixed adopted model and 768 dimensions at `crates/kcs-adapter/src/gemini_embedding.rs:213-220`; adapter execution reaches the client at lines 259-285.

The query path synchronously submits one item at `crates/kcs-cli/src/main.rs:7179-7204`. Index enrichment processes at most 32 chunks per batch at `crates/kcs-cli/src/main.rs:7108-7112,7420-7423`, calls the adapter at lines 7526-7547 and `7726-7742`, and persists accepted vectors only afterward at lines 7743-7768.

The real client constructs the request and invokes `POST ...:batchEmbedContents` at `crates/kcs-adapter/src/gemini_embedding.rs:120-146`. It then calls `into_json()` directly at lines 146-148. Only after the complete JSON tree exists does `parse_embeddings` check response count, numeric JSON types, and width at lines 153-203. Those checks bound accepted vector shape, but they cannot prevent a slow read, decompression growth, oversized irrelevant fields, or an oversized array from being materialized and rejected afterward.

`Cargo.lock:1396-1397` pins `ureq 2.12.1`. Its default agent has a 30-second connect timeout and no read, write, or overall timeout (`ureq-2.12.1/src/agent.rs:251-264`). Its `into_json` uses `serde_json::from_reader` without a byte ceiling (`ureq-2.12.1/src/response.rs:531-536`); the dependency documents that untrusted callers must apply `.take()` to impose one (`response.rs:248-259`). Default gzip decompression wraps the reader before parsing with no decoded-size maximum (`response.rs:640-673`). KCS's accepted `timeout_seconds=300` is explicitly not threaded into adapter HTTP at `crates/kcs-core/src/scope.rs:1581-1590`.

Two bounded, network-free parser tests passed:

- `batch_embed_response_is_parsed_in_order` (`gemini_embedding.rs:380-406`) confirms normal response conversion.
- `embedding_wrong_dimension_is_contract_violation` (`gemini_embedding.rs:408-430`) confirms the width control rejects after a response value already exists.

Neither test exercises or imposes a transport/read/decompressed-body limit.

## Counterevidence and impact

Connection establishment is bounded to 30 seconds; the adopted model is fixed, avoiding model resolution on this path; index batches contain at most 32 items and query uses one; response count, numeric type, and width are checked; invalid responses are not persisted; query errors degrade to text search; index errors become failed tasks; and online adapter activation/authorization is required. These controls limit accepted semantic output and durable effects. They do not bound time or memory before semantic validation.

A faulty or hostile configured service or intermediary can therefore stall a synchronous query/index operation or cause substantial transient memory/CPU consumption. The result is an approved-online availability defect rather than an authorization or confidentiality bypass, so the final severity is Medium. Numeric-domain validation is separately tracked by `KCS-R23-CAND-003`, and Gemini model-list bounds by `KCS-R23-CAND-058`.

## Remaining uncertainty and next step

No loopback delay/body measurement was run under the read-only/no-network constraint. The exact source and pinned dependency defaults settle the missing pre-parse controls. Remediation should use a shared Gemini HTTP client with configured overall/read/write deadlines and compressed/decompressed response byte ceilings before `serde_json` materialization; retain the existing count/dimension checks.

Validation artifacts: none.
