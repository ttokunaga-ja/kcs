# Validation: Mistral model resolution lacks response-body and read-time bounds

- Candidate: `KCS-R23-CAND-022`
- Instance key / ledger row: `KCS-R23-CAND-022`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.98)**
- Method: **bounded configuration test + V10 exact static/dependency trace; no network**
- Root control: `crates/kcs-adapter/src/mistral_ocr.rs:83-110`

## Rubric

- [x] The default mutable model alias reaches the model-list request in normal online execution.
- [x] The configured timeout and pinned HTTP dependency defaults were checked at the closest control.
- [x] Response read, decompression, full JSON materialization, and post-parse filtering were ordered exactly.
- [x] Fixed-model, connect-timeout, auth/HTTP, and model-family controls were assessed as counterevidence.
- [x] Availability impact and remaining runtime proof gap were explicitly calibrated.

## Exact trace and evidence

The configured markdown model defaults to `mistral-ocr-latest` at `crates/kcs-adapter/src/catalog.rs:150-157`. Normal online markdownization resolves it before OCR at `crates/kcs-adapter/src/catalog.rs:134-146`; the resolve-only incremental profile path independently reaches the same call at lines 159-192.

`EnvMistralOcrClient::resolve_model_pin` bypasses HTTP only for a fixed model at `crates/kcs-adapter/src/mistral_ocr.rs:84-87`. For the default `*-latest` alias it performs `GET /v1/models` and immediately calls `into_json` at lines 88-94. Only after full materialization does it select a stable family match at lines 95-109.

The schema accepts `adapter.policy.timeout_seconds` at `crates/kcs-core/schemas/config.schema.json:124-139`, but semantic validation explicitly states that it is not threaded to adapter HTTP; only the value 300 is accepted at `crates/kcs-core/src/scope.rs:1581-1590`. The bounded existing test `r12_2_timeout_seconds_non_default_is_loud_rejected` passed: 30 is rejected and 300 is accepted, confirming configuration semantics but not transport enforcement.

`Cargo.lock:1396-1397` pins `ureq 2.12.1`. Its default agent has a 30-second connect timeout and `None` for read, write, and overall timeouts (`ureq-2.12.1/src/agent.rs:251-264`). `into_json` parses the entire reader with `serde_json::from_reader` (`ureq-2.12.1/src/response.rs:531-536`) and this callsite applies no `.take()` maximum. With default gzip enabled, decompression wraps that reader before parsing without a decoded-size cap (`response.rs:640-673`).

## Counterevidence and impact

A fixed immutable model avoids the request; connection establishment is bounded to 30 seconds; a credential is required; HTTP error classes are mapped; malformed JSON fails; and family/stability filtering prevents adopting an unrelated model ID. None of those controls limits a connected peer that stalls during headers/body delivery, a chunked/large body, or decompressed JSON size before the filter executes.

The source is the configured Mistral endpoint, proxy, or intermediary during an explicitly authorized online workflow. The sink is a synchronous model-resolution call that can block the command or consume memory while materializing the model catalog. This is a bounded online availability defect, not an authorization bypass, so the final severity is Medium.

## Remaining uncertainty and next step

No loopback delay/body experiment was run under the read-only/no-network constraint. The exact callsite, explicit configuration comment, and pinned dependency defaults provide a complete source/control/sink trace. Remediation should thread the configured timeout into a shared client and cap compressed/decompressed response bytes before JSON parsing; model-family filtering remains a separate semantic control.

Validation artifacts: none.
