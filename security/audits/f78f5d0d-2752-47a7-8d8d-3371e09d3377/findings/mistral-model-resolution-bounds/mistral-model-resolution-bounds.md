# Mistral model resolution lacks response-body and read-time bounds

| Field | Value |
| --- | --- |
| Severity | **Medium** |
| Priority | **P2** |
| Weakness | CWE-400 (Uncontrolled Resource Consumption), CWE-770 (Allocation of Resources Without Limits or Throttling) |
| Affected component | `kcs-adapter` Mistral model-alias resolution |
| Affected source | KCS `0.1.0`, revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` |

## Executive Summary

KCS resolves the default `mistral-ocr-latest` alias by making an authenticated
`GET /v1/models` request before it submits an OCR job. At the affected revision,
that request has no application-level response deadline and the response is
deserialized into an unconstrained `serde_json::Value`. Model-family and
stability checks run only after the entire JSON value has been built.

A malicious, compromised, misdirected, or faulty configured endpoint, proxy, or
intermediary can therefore accept the connection and then delay response bytes,
slow-stream a body, or return an oversized (including gzip-expanded) model
catalog. The affected KCS command has no application-defined completion bound
and can consume substantial memory and CPU before OCR begins. When the path is
reached from an indexing or batch command, the command can also retain the
selected scope's store lock for the duration.

The impact is local command and scope availability. This path does not bypass
online-adapter approval, remove the API-key requirement, select an unrelated
model, expose an unintended inbound service, or establish a data-integrity
primitive. A fixed immutable model pin bypasses the model-list request. Those
constraints support a **Medium / P2** rating rather than a higher severity.

I reviewed the affected KCS revision and the locked `ureq 2.12.1` source
directly. I also ran the included offline, allocation-capped regression oracle;
I did not contact Mistral, use a credential, or execute a live slow-response or
oversized-response trigger. I found no fixing revision or release tag in the
source history inspected. The vulnerable model-list implementation first
appears in commit `3b5039710177d9ceb3cdb07fc99275b4d573efbd` dated 2026-07-03.

## Background

KCS uses an immutable model identifier as part of the adapter profile. Operators
may configure a mutable `*-latest` alias, so KCS must resolve that alias before
it can calculate the final profile and send OCR work. The normal online wrapper
constructs the environment-backed Mistral client, takes the configured model,
and resolves it. If no model is declared, the mutable alias is the default:

```rust
// crates/kcs-adapter/src/catalog.rs:134-156
let client = EnvMistralOcrClient::new();
let configured_model = declared_markdown_model();
let model_pin = client.resolve_model_pin(&configured_model)?;
let adapter = MistralOcrMarkdownizeAdapter::new(client, model_pin, request.scope_id)
    .with_image_store(request.kcs_dir);

fn declared_markdown_model() -> String {
    crate::tool_lock::registered_declared_adapter("markdown")
        .and_then(|declared| declared.model)
        .unwrap_or_else(|| "mistral-ocr-latest".to_owned())
}
```

The incremental-profile path independently resolves the same alias before it
decides whether an incremental OCR send is eligible. Consequently, model
resolution is a pre-OCR operation: a peer can consume victim time and memory
without processing or receiving the document itself.

This is an outbound, operator-approved trust boundary. KCS uses the local
process identity and intentionally attaches the configured Mistral credential
to the selected service. The security-relevant untrusted inputs are the
connected peer's response timing, transfer framing, content encoding, and body
bytes. The finding does not depend on an inbound KCS listener or on an arbitrary
Internet host being able to choose the destination.

KCS exposes a timeout policy in its configuration schema
(`crates/kcs-core/schemas/config.schema.json:127-137`):

```json
"policy": {
  "type": "object",
  "properties": {
    "allow_network": { "type": "boolean" },
    "max_input_bytes": { "type": "integer", "minimum": 1 },
    "timeout_seconds": { "type": "integer", "minimum": 1 },
    "redact_logs": { "type": "boolean" }
  }
}
```

At this revision, however, that setting is configuration syntax rather than a
transport bound. The default value is accepted, while non-default values are
rejected because the value is not passed to adapter HTTP code. That distinction
is important: an operator who leaves `timeout_seconds = 300` in place does not
receive a 300-second execution deadline.

The dependency lock selects `ureq 2.12.1`. Its default agent bounds connection
establishment to 30 seconds but leaves read, write, and overall timeouts unset:

```rust
// ureq 2.12.1, src/agent.rs:251-260
config: AgentConfig {
    proxy: None,
    timeout_connect: Some(Duration::from_secs(30)),
    timeout_read: None,
    timeout_write: None,
    timeout: None,
    // ...
}
```

That 30-second control helps only until the connection is established. It does
not bound a connected peer that withholds headers, pauses between body chunks,
or keeps a chunked response open.

## Vulnerability Details

We first reach `resolve_model_pin` with the default mutable alias. A fixed model
returns at lines 85-87 and is not affected by this particular request. For a
`*-latest` alias, KCS obtains the credential, performs the model-list request,
and immediately calls `into_json`:

```rust
// crates/kcs-adapter/src/mistral_ocr.rs:84-109
fn resolve_model_pin(&self, configured_model: &str) -> Result<String> {
    if !configured_model.ends_with("-latest") {
        return Ok(configured_model.to_owned());
    }
    let api_key = Self::api_key()?;
    let value: Value = ureq::get(&format!("{}/v1/models", self.base_url()))
        .set("Authorization", &format!("Bearer {api_key}"))
        .call()
        .map_err(http_error)?
        .into_json()
        .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
    let family = configured_model.trim_end_matches("-latest");
    value
        .get("data")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|model| model.get("id").and_then(Value::as_str))
        .filter(|id| id.starts_with(family) && !id.ends_with("-latest"))
        .max()
        .map(str::to_owned)
        .ok_or_else(|| {
            AdapterError::ContractViolation(format!(
                "no versioned model found for {configured_model}"
            ))
        })
}
```

There is no `.timeout(...)`, bounded agent, `Read::take`, `Content-Length`
rejection, catalog-entry limit, or maximum identifier length on this path. The
locked dependency's `into_json` implementation feeds the response reader
directly to Serde:

```rust
// ureq 2.12.1, src/response.rs:531-536
pub fn into_json<T: DeserializeOwned>(self) -> io::Result<T> {
    let reader = self.into_reader();
    serde_json::from_reader(reader).map_err(|e| {
        // error mapping follows
```

Serde parses incrementally from the stream, but the requested target type is a
general `Value`. Thus, all response-controlled strings, arrays, and objects are
allocated into the value tree before `resolve_model_pin` examines `data` or
filters IDs. A syntactically valid catalog can carry irrelevant large fields or
an arbitrarily long `data` array; semantic filtering does not act as a resource
guard because it comes later.

Default `ureq` features include gzip. Its response reader is wrapped in a
`MultiGzDecoder` before `into_json` sees it. KCS places no decoded-byte ceiling
around that reader, so a relatively small encoded response can expand into a
much larger JSON value. A declared wire `Content-Length` would not be a complete
control even if KCS checked it: chunked responses need not provide one, a peer
can lie, and encoded length is not decoded length.

We can now compare this with the closest intended control. The source explicitly
documents that the configured timeout is not wired into any adapter transport:

```rust
// crates/kcs-core/src/scope.rs:1581-1590
// timeout_seconds: a per-adapter execution timeout is not threaded through
// the adapter HTTP path (it would touch every adapter's transport). Accept
// the documented default (300); reject any other value loudly rather than
// silently ignore it. (R12-2 decision: real wiring is a large change.)
if let Some(timeout) = policy.get("timeout_seconds").and_then(Value::as_i64) {
    if timeout != 300 {
        return Err(KcsError::not_implemented(
            "adapter.policy.timeout_seconds other than 300",
        ));
    }
}
```

The resulting sequence is straightforward:

1. An approved online workflow uses the default mutable model alias.
2. KCS opens the authenticated model-list request before OCR.
3. Connection establishment succeeds within the dependency's 30-second bound.
4. The peer controls subsequent header/body timing and encoded response bytes.
5. KCS reads, decompresses, and constructs a full JSON `Value` without an
   application deadline or byte ceiling.
6. Only then does KCS validate the shape, family, stability, and maximum ID.

If the peer stops making progress or continues slow progress, step 5 has no
application-defined end time. If it supplies a large valid catalog, process
memory grows with the decoded body and with the larger in-memory JSON
representation. The exact point at which latency, memory pressure, allocator
failure, or an operating-system kill occurs is host-dependent.

## Exploitability Analysis

The strongest and least resource-intensive route is a slow response. We let the
normal authenticated request connect, then have the selected service or an
in-path intermediary delay headers or deliver an incomplete JSON body in small
chunks. The 30-second connect timeout no longer helps after connection setup.
Because neither an idle-read timeout nor an overall deadline is present, the
peer can keep the synchronous resolver occupied until the peer, network stack,
operator, or process terminates the operation.

That primitive affects more than one isolated function call. `kcs index`
acquires the folder store lock before the pipeline runs and documents that the
lock is held end-to-end (`crates/kcs-cli/src/main.rs:558-570`). `kcs batch`
similarly acquires the lock before it drives pending online tasks
(`crates/kcs-cli/src/main.rs:5586-5593`). If model resolution stalls on either
path, work for that selected scope remains incomplete and concurrent writers
cannot acquire the same store lock. This is scope-local operational denial of
service, not a machine-wide lock or a persistent lock after process exit.

The second route is response expansion. A peer can send a large, valid JSON
object whose `data` entries contain acceptable or irrelevant IDs plus large
unused properties. We do not need to defeat model-family validation: allocation
happens while the `Value` is built, before that validation. Gzip can improve the
attacker's bandwidth-to-decoded-size ratio. Depending on available memory and
allocator behavior, the outcome ranges from high transient memory and CPU use
to process termination. I did not measure a reliable exhaustion threshold, so
the report does not claim a particular byte count or guaranteed out-of-memory
kill.

Several constraints materially bound exploitation:

- The operator must authorize online adapter use and configure a credential.
- The default mutable alias is affected, but an immutable model pin returns
  locally and avoids this catalog request.
- The peer must be the configured endpoint, a compromised endpoint, or an
  effective proxy/intermediary. KCS exposes no inbound unauthenticated trigger.
- Connection setup itself is bounded to 30 seconds.
- HTTP status handling, JSON syntax checks, and post-parse model-family and
  stability filters still apply. They prevent accepting an unrelated model but
  do not prevent pre-validation resource use.
- One response directly blocks one command and its selected scope. There is no
  demonstrated authorization bypass, code execution, persistent corruption, or
  cross-scope write primitive.

A malformed JSON body is a weaker route because Serde can fail as soon as the
syntax error becomes decisive. Similarly, a large `Content-Length` is easy to
reject in a repaired implementation, but relying only on that header would
leave chunked and compressed cases open. The robust exploit path is therefore
either a syntactically plausible slow stream or a valid catalog whose decoded
representation grows before the filter.

These preconditions are realistic for a remote-service boundary, while the
impact remains bounded to availability and resource consumption. That
combination is why the final rating is **Medium**, priority **P2**.

## Proof of Concept

The `poc/` directory contains `bounded_model_catalog_probe.py`, a deliberately
safe regression oracle. It creates no socket, reads no environment variables or
credentials, does not import KCS, and never sleeps. Its largest generated
response body is fixed at 128 KiB; parser overhead is likewise bounded by this
small input. We use a logical timestamp carried with each in-memory chunk to
test timeout behavior immediately.

From the report directory, run:

```sh
cd poc
python3 bounded_model_catalog_probe.py
```

I ran that command and observed:

```text
[+] vulnerable ordering: materialized 131072 bytes before selecting mistral-ocr-2505 (demo hard-capped)
[+] decoded-byte regression: rejected: decoded body exceeds 4096 bytes
[+] gzip-expansion regression: rejected: decoded body exceeds 4096 bytes
[+] deadline regression: rejected: chunk arrived at 1001 ms; deadline is 1000 ms
[+] valid-catalog regression: selected mistral-ocr-2505
[+] PASS: offline byte, decompression, and deadline invariants hold
```

The first check mirrors the affected ordering at a harmless ceiling: it builds
the complete JSON object and only then selects the model. The next checks show
the desired fixed behavior for a limit-plus-one decoded body, gzip expansion,
and a chunk arriving after a logical deadline. The final case ensures a small
valid catalog still resolves normally.

This artifact is intentionally not a live reproduction of `ureq` blocking or
KCS memory exhaustion. It neither measures real transport timing nor proves an
environment-specific exhaustion threshold; the source and dependency trace
establish the missing controls. There is no cleanup step.

## Remediation

The invariant to restore is: **every remote model-catalog operation must have a
finite overall deadline, a bounded response read, and a decoded-body ceiling
that is enforced before JSON deserialization**. The configured policy must be
passed to the adapter rather than accepted as a no-op. Wire-size and decoded-size
budgets should be distinct when compression is allowed.

A minimal repair can construct a bounded shared agent, request identity encoding
for this small response, and replace `into_json` with an explicit limit-plus-one
read. The following illustrates the important ordering; error variants and
policy plumbing should follow KCS conventions:

```rust
use std::io::Read;
use std::time::Duration;

const MAX_MODEL_CATALOG_BYTES: usize = 1 * 1024 * 1024;

fn read_model_catalog(response: ureq::Response) -> Result<Value> {
    let mut body = Vec::new();
    response
        .into_reader() // decoded bytes when ureq compression is enabled
        .take((MAX_MODEL_CATALOG_BYTES + 1) as u64)
        .read_to_end(&mut body)
        .map_err(|err| AdapterError::Network(err.to_string()))?;

    if body.len() > MAX_MODEL_CATALOG_BYTES {
        return Err(AdapterError::ContractViolation(
            "Mistral model catalog exceeds response limit".to_owned(),
        ));
    }
    serde_json::from_slice(&body)
        .map_err(|err| AdapterError::ContractViolation(err.to_string()))
}

let timeout = Duration::from_secs(configured_timeout_seconds);
let agent = ureq::AgentBuilder::new()
    .timeout_connect(Duration::from_secs(30))
    .timeout(timeout) // includes reading the response body
    .build();

let response = agent
    .get(&format!("{}/v1/models", self.base_url()))
    .set("Authorization", &format!("Bearer {api_key}"))
    .set("Accept-Encoding", "identity")
    .call()
    .map_err(http_error)?;
let value = read_model_catalog(response)?;
```

`Read::take(limit + 1)` is important: it lets KCS distinguish an exact-limit
response from a truncated over-limit response before parsing. Because the
current `ureq` reader transparently decompresses gzip, this helper caps decoded
bytes. Requesting `identity` avoids negotiated expansion for this normally small
catalog, but a stronger shared transport layer should either disable transparent
decompression and perform bounded decoding itself or otherwise enforce a raw
wire budget as well. A hostile peer need not honor `Accept-Encoding`.

The transport should also use one absolute deadline across DNS, redirects,
headers, and the complete body rather than resetting a generous timeout on each
successful chunk. An idle-read deadline can supplement that absolute deadline,
but must not let a one-byte slow stream run forever. Cancellation and error
mapping should release the command normally so RAII drops the scope lock.

Beyond the minimal patch, deserialize into a narrow model-catalog type and
bound the number of entries and individual ID lengths after the byte ceiling.
Keep the existing family and mutable-alias rejection checks; they protect a
different semantic invariant. Consider centralizing these limits for every
online adapter so a future call site cannot fall back to raw `into_json`.

Regression coverage should include:

- a fixed immutable model, asserting that no catalog transport is invoked;
- a small valid `*-latest` catalog, asserting the expected maximum stable ID;
- decoded bodies exactly at the byte ceiling and one byte over it;
- an in-memory gzip body below the wire ceiling that exceeds the decoded ceiling;
- a fake `Read` that returns `io::ErrorKind::TimedOut` before complete JSON;
- a logical slow stream that continues making progress but crosses the absolute
  deadline;
- excessive catalog entries and overlong IDs after a body passes the byte cap;
- configuration tests proving that a non-default `timeout_seconds` value is now
  honored, and that the documented 300-second value reaches the agent; and
- error-path tests confirming the store lock is released and no OCR request is
  attempted after model-resolution timeout or size rejection.

These tests can all be deterministic and credential-free. The included PoC
describes the parser/deadline cases without using a network.

## Summary

KCS's default Mistral alias-resolution path crosses a remote-service boundary
before OCR, but revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
does not carry its documented timeout into that request and does not cap the
decoded model-list response before constructing a JSON value. We traced the
default alias through the wrapper, the blocking `ureq` call, transparent
decompression, full `Value` construction, and only then the semantic model
filter. A connected peer can consequently prolong a command without an
application deadline or pressure process memory and CPU with an oversized
catalog.

The fixed-model bypass, approved outbound-only exposure, connect timeout, and
absence of a demonstrated confidentiality or integrity impact keep the finding
at **Medium / P2**. Wiring the timeout, bounding wire and decoded bytes before
deserialization, and exercising those invariants with deterministic readers
closes the root cause. Variant analysis should apply the same shared transport
invariant to other online response parsers, while keeping this report's proven
scope limited to Mistral model resolution.
