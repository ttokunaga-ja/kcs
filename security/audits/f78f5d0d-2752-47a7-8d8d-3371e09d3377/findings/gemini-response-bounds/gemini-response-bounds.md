# Gemini embedding responses lack body and read-time bounds

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` reads a Gemini
`batchEmbedContents` response into an unrestricted `serde_json::Value`. The
HTTP request uses `ureq`'s one-off default agent, which has a 30-second connect
timeout but no read, write, or overall deadline. KCS applies no response-byte
ceiling before JSON deserialization. Its response-count, numeric-type, and
vector-dimension checks all run only after the complete response tree is in
memory.

Once an operator has enabled the online embedding adapter, a faulty,
compromised, or hostile Gemini-compatible service, proxy, or intermediary can
accept the connection and then stop making progress, slow-stream a response,
or return an oversized or compressed JSON body. The first route can block the
current query or index operation indefinitely. The second can consume
substantial transient memory and CPU, potentially terminating the KCS process,
before the response is rejected. This is an outbound, opt-in availability
issue; it does not establish an unauthenticated inbound path, credential
disclosure, invalid-vector persistence, or code execution.

| Property | Assessment |
|---|---|
| Severity | **Medium** |
| Engineering priority | **P2** |
| Weakness | CWE-400 (Uncontrolled Resource Consumption), CWE-770 (Allocation of Resources Without Limits or Throttling) |
| Confirmed affected revision | `0e19f3c6489da458e93a982a333c308d92d0a0ae` |
| Fix revision | None identified |

I reviewed the confirmed revision and the pinned `ureq 2.12.1`
source directly. I ran KCS's existing normal-response and wrong-dimension
Gemini parser tests, and both passed. I also ran the included bounded,
in-memory response/deadline regression harness. I did not contact Gemini or
any other service, use a credential, open a listener, send a request, or
measure production memory-exhaustion thresholds. No fixing revision, release
advisory, or CVE was available for comparison.

The affected-version statement is intentionally narrow. Repository history
shows that the unbounded `batchEmbedContents` response path was introduced
with the embedding implementation in commit
`07948af0dde4cf3de2c7a6d455060d6ce0925f54` on 2026-07-04 and remains present
at the confirmed revision. The repository has no release tags from which to
infer a broader package-version range.

## Background

KCS is a local-first CLI rather than a network service. Network use is
optional: the real embedding path becomes active only when the operator has
declared embedding authentication or supplied the legacy Gemini credential.
The adapter profile is an online API profile and explicitly permits network
access. Those consent controls are important preconditions, but after an
approved send the response still crosses from a remote trust boundary into
the KCS process.

If we follow an approved real execution into the catalog, it constructs the
default client without transport limits:

```rust
// crates/kcs-adapter/src/catalog.rs:386-401
pub fn run_adopted_embedding(
    execution: AdoptedEmbeddingExecution,
    items: Vec<EmbeddingItem>,
    input_type: EmbeddingInputType,
) -> Result<Vec<EmbeddingVector>> {
    let request = EmbeddingRequest { input_type, items };
    let response = match execution {
        AdoptedEmbeddingExecution::Real => GeminiEmbeddingAdapter::default().embed(request),
        other => GeminiEmbeddingAdapter::new(
            MockAdoptedEmbeddingClient { execution: other },
            ADOPTED_MODEL_PIN,
            ADOPTED_DIMENSIONS,
        )
        .embed(request),
    }?;
    Ok(response.vectors)
}
```

The adopted adapter fixes the model to `gemini-embedding-2` and requests 768
dimensions. Because the model is not a mutable alias,
`resolve_model_pin` returns locally before its model-list HTTP branch. We can
therefore keep this report focused on the embedding exchange itself; model
catalog response handling is not required to trigger this issue.

Two shipped consumers reach the same blocking call. A search embeds one query
item. Index enrichment divides work into batches of at most 32 chunks and
sends each batch synchronously. Those limits bound the expected number of
vectors, but they do not constrain the number of bytes that the peer may send
in response.

KCS also exposes `adapter.policy.timeout_seconds` in its schema. At the
confirmed revision, the semantic checker explicitly accepts only the
documented value of 300 seconds while acknowledging that it is not connected
to adapter HTTP:

```rust
// crates/kcs-core/src/scope.rs:1581-1591
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

The security invariant needed at this boundary is straightforward: KCS must
finish each approved HTTP operation within an enforced deadline and must cap
encoded and decoded response bytes before general JSON materialization. Only
after those resource checks pass should it apply count, type, and dimension
validation.

## Vulnerability Details

### The response goes directly into an unrestricted JSON value

`EnvGeminiEmbeddingClient::embed` builds the request from one query item or
the current index batch. The decisive transition is at lines 139-149:

```rust
// crates/kcs-adapter/src/gemini_embedding.rs:120-150
fn embed(
    &self,
    items: &[EmbeddingItem],
    model_pin: &str,
    dimensions: u32,
) -> Result<Vec<EmbeddingVector>> {
    let api_key = Self::api_key()?;
    let requests = items
        .iter()
        .map(|item| {
            json!({
                "model": format!("models/{model_pin}"),
                "content": { "parts": [{ "text": item.text.clone().unwrap_or_default() }] },
                "outputDimensionality": dimensions,
            })
        })
        .collect::<Vec<_>>();
    let response: Value = ureq::post(&format!(
        "{}/v1beta/models/{model_pin}:batchEmbedContents",
        self.base_url()
    ))
    .set("x-goog-api-key", &api_key)
    .set("Content-Type", "application/json")
    .send_json(json!({ "requests": requests }))
    .map_err(http_error)?
    .into_json()
    .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
    parse_embeddings(&response, items, dimensions)
}
```

There is no `.timeout(...)`, no configured `Agent`, no `Content-Length`
ceiling, and no limited reader between `send_json` and `into_json`. The full
body must complete and deserialize before `parse_embeddings` is called.

The workspace lockfile pins `ureq 2.12.1`. Its default `AgentBuilder` makes
the timing gap explicit:

```rust
// ureq 2.12.1, src/agent.rs:251-264
config: AgentConfig {
    proxy: None,
    timeout_connect: Some(Duration::from_secs(30)),
    timeout_read: None,
    timeout_write: None,
    timeout: None,
    // ...
}
```

The one-off `ureq::post` helper creates this default agent. If we carry that
default into `embed`, the connect limit protects only connection
establishment. Once a peer accepts the connection, no inactivity or total
deadline requires headers or body bytes to arrive.

The dependency's JSON helper exposes the size gap just as directly:

```rust
// ureq 2.12.1, src/response.rs:531-536
pub fn into_json<T: DeserializeOwned>(self) -> io::Result<T> {
    use crate::stream::io_err_timeout;

    let reader = self.into_reader();
    serde_json::from_reader(reader).map_err(|e| {
        // ...
    })
}
```

For `T = serde_json::Value`, `serde_json` constructs the complete object,
including unknown top-level fields, strings, arrays, and numbers. A
peer-supplied `Content-Length` is framing, not a client policy ceiling, and a
chunked or close-delimited response need not declare a size at all. The
dependency itself advises callers of `into_reader` to apply `Read::take` when
reading untrusted bodies, but KCS does not do so.

The workspace enables `ureq`'s default features, including gzip. In the
pinned dependency, the response reader is wrapped in `MultiGzDecoder` before
it reaches `serde_json::from_reader`. No decoded-size maximum is applied.
Consequently, a small encoded body may expand substantially inside the KCS
process, and the HTTP `Content-Length`, when present, describes the encoded
stream rather than the allocation ultimately produced by JSON parsing.

### Semantic checks happen after the resource sink

`parse_embeddings` has useful contract controls, but their order is too late
to protect availability:

```rust
// crates/kcs-adapter/src/gemini_embedding.rs:153-203
let embeddings = response
    .get("embeddings")
    .and_then(Value::as_array)
    .ok_or_else(|| {
        AdapterError::ContractViolation("embedding response missing embeddings".to_owned())
    })?;
if embeddings.len() != items.len() {
    return Err(AdapterError::ContractViolation(
        "embedding response count does not match request".to_owned(),
    ));
}
items
    .iter()
    .zip(embeddings)
    .map(|(item, embedding)| {
        let vector = embedding
            .get("values")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                AdapterError::ContractViolation("embedding missing values".to_owned())
            })?
            .iter()
            .map(|value| value.as_f64().map(|value| value as f32))
            .collect::<Option<Vec<f32>>>()
            .ok_or_else(|| {
                AdapterError::ContractViolation("embedding values must be numeric".to_owned())
            })?;
        if vector.len() != dimensions as usize {
            return Err(AdapterError::ContractViolation(format!(
                "embedding dimension mismatch: expected {dimensions}, got {}",
                vector.len()
            )));
        }
        // ...
    })
    .collect()
```

By the time we reach the response-count check, the untrusted JSON tree is
already allocated. If we carry one oversized `values` array forward, it
already exists in that tree and is then copied into a new `Vec<f32>` before we
reach the width check. The array is therefore materialized, converted, and
only then rejected. A large irrelevant field never even needs to resemble an
embedding: it is retained in the `Value` before the missing or wrong
`embeddings` member causes a contract error.

### Both consumers wait for the same unbounded operation

The query path does have a graceful fallback, but only after the adapter
returns an error:

```rust
// crates/kcs-cli/src/main.rs:7179-7204
fn compute_query_embedding(query: &str) -> Result<Option<Vec<f32>>> {
    // ... build one query item ...
    match run_embedding_adapter(execution, items, EmbeddingInputType::Query) {
        Ok(vectors) => Ok(vectors.into_iter().next().map(|vector| vector.vector)),
        Err(_) => Ok(None),
    }
}
```

An open response with no progress produces neither branch, so text fallback
does not begin. The index path similarly waits inside `send_embed_batch`.
Only after vectors return does it construct the ID map and persist embeddings.
This ordering is valuable counterevidence: invalid vectors are not written.
It does not help the blocked command, and index task transitions are not
applied until control returns from the adapter.

We can now state the complete path:

1. The operator enables the online Gemini embedding adapter and runs a query
   or index operation.
2. KCS sends one query item or at most 32 chunk items to the configured
   endpoint.
3. The peer accepts the connection, defeating the relevance of the connect
   timeout, and controls subsequent response timing, framing, compression,
   and JSON bytes.
4. KCS reads, optionally decompresses, and materializes the unrestricted
   response as a `Value`.
5. Only afterward does KCS check response count, numeric JSON types, and the
   requested width of 768.
6. A stalled response blocks the operation; an oversized response consumes
   resources before eventual rejection or process termination.

## Exploitability Analysis

The most reliable availability route is a no-progress or slow-progress
response. We need no large payload: after accepting the connection and
returning enough protocol data to keep it open, the peer can withhold the next
byte or avoid terminating the body. Because both the read timeout and overall
deadline are `None`, the current thread remains blocked. A future fix that
sets only an inactivity timeout would still be vulnerable to a peer that
delivers one small fragment before each interval expires, so an overall
deadline is the stronger control and should be retained alongside per-read
and per-write limits.

The memory route offers several interchangeable inputs. We can place a large
string in an irrelevant top-level field, return far more `embeddings` than the
one or 32 requested, make one `values` array much wider than 768, or use gzip
expansion. All of these bytes cross the resource sink before semantic checks.
The oversized-array form adds a second allocation when KCS converts JSON
numbers into `f32` values. The irrelevant-field form is simpler because it
does not need to satisfy any embedding syntax at all. Exact peak allocation
depends on JSON shape, allocator growth, compression ratio, and host memory;
I did not run a stress case, so this report does not claim a measured OOM
threshold.

Several constraints keep the finding at Medium/P2:

- KCS has no public listener. The trigger requires an operator-approved online
  embedding operation and a faulty or adversarial configured service,
  intermediary, or network path.
- The adopted model is fixed, query batches contain one item, and index
  batches contain no more than 32. Those controls reduce normal request and
  accepted-response size, but do not constrain the received body.
- Count, JSON numeric type, and exact dimension are checked, and persistence
  occurs only after they pass. The primitive is pre-validation availability,
  not durable vector poisoning.
- A returned query error degrades to text search, and an index error can be
  recorded as a failed task. Those recovery paths become effective only after
  a bounded error is produced; they cannot recover from an endless read.
- A single response directly targets the current command process and current
  query or batch. KCS is not a daemon, and no cross-scope persistence or
  authorization bypass was established.

Operational bounds at a well-behaved provider may make accidental exposure
less frequent, but they are not an enforceable client-side invariant. A
misconfigured compatibility endpoint, compromised proxy, or transient
provider failure is enough to exercise the same path. Remote control is
therefore realistic once the opt-in precondition is met, while the confirmed
impact remains availability-only.

## Proof of Concept

The `poc` directory contains a deliberately harmless regression model rather
than a live denial-of-service trigger. It uses Python's standard library and
in-memory readers. The body ceiling is 160 bytes, the test deadline is 20 ms,
and the only delayed reader sleeps for 100 ms. It neither imports KCS nor
opens a socket, and it never reads an API key.

The harness preserves the fixed ordering we want in production: a worker
completes a byte-capped read within the deadline; only then does the main
thread call `json.loads` and the semantic validator. Four cases establish the
boundary:

- a valid response padded to exactly the limit is accepted and then checked;
- a semantically valid response with an oversized irrelevant field is
  rejected before the semantic callback;
- a delayed in-memory reader exceeds the deadline before the semantic
  callback; and
- a small wrong-width vector passes the transport bounds and is still rejected
  by the semantic check.

Run it from the report directory:

```sh
cd poc
make test
```

Representative output from my run is:

```text
PYTHONDONTWRITEBYTECODE=1 python3 run.py
[PASS] exact-limit response accepted, then passed semantic validation
[PASS] oversized response rejected before semantic validation
[PASS] delayed response rejected by 20 ms deadline before semantic validation
[PASS] wrong-width vector rejected after transport bounds
[PASS] 4 bounded in-memory regressions; no network or credentials used
```

No cleanup is required. This harness proves the intended control ordering and
is suitable as a starting point for KCS unit tests after the response reader
is factored behind a seam. It does not exercise `ureq`, a socket deadline,
gzip, or the live adapter, and should not be mistaken for production timeout
machinery or a measurement of exploit scale.

## Remediation

The invariant to restore is:

> Every Gemini request must have an enforced total deadline, every response
> must cross encoded and decoded byte ceilings before JSON materialization,
> and semantic vector checks must run only after those resource controls pass.

First, resolve an absent `adapter.policy.timeout_seconds` to the documented
300-second default and thread the effective value into the adapter rather than
merely accepting it in configuration. Construct one shared `ureq::Agent` with
explicit connect, read, and write timeouts, and apply the effective overall
timeout to every request. Sharing the client also ensures model and embedding
calls use the same policy rather than relying on one-off defaults.

Second, replace `into_json::<Value>()` with a capped read. The following is an
illustrative minimal shape; the byte value should be derived from the maximum
batch cardinality, dimensions, permitted number encoding, and measured
provider overhead rather than copied blindly:

```rust
use std::io::Read;
use std::time::Duration;

const MAX_DECODED_EMBED_RESPONSE_BYTES: usize = 4 * 1024 * 1024;

fn bounded_response_json(response: ureq::Response) -> Result<serde_json::Value> {
    let mut body = Vec::new();
    response
        .into_reader()
        .take((MAX_DECODED_EMBED_RESPONSE_BYTES + 1) as u64)
        .read_to_end(&mut body)
        .map_err(|error| AdapterError::Network(error.to_string()))?;

    if body.len() > MAX_DECODED_EMBED_RESPONSE_BYTES {
        return Err(AdapterError::ContractViolation(
            "Gemini embedding response exceeds byte limit".to_owned(),
        ));
    }

    serde_json::from_slice(&body)
        .map_err(|error| AdapterError::ContractViolation(error.to_string()))
}

let agent = ureq::AgentBuilder::new()
    .timeout_connect(Duration::from_secs(30))
    .timeout_read(Duration::from_secs(30))
    .timeout_write(Duration::from_secs(30))
    .build();

let response = agent
    .post(&url)
    .timeout(Duration::from_secs(timeout_seconds))
    .set("x-goog-api-key", &api_key)
    .set("Content-Type", "application/json")
    .send_json(json!({ "requests": requests }))
    .map_err(http_error)?;
let response = bounded_response_json(response)?;
let vectors = parse_embeddings(&response, items, dimensions)?;
```

Reading `limit + 1` bytes is important: it distinguishes an exactly-at-limit
body from a truncated oversized body before attempting JSON parsing. In the
pinned `ureq`, `into_reader` exposes the decompression wrapper, so this helper
caps decoded bytes. With that ordering, we can preserve semantic validation
without letting it become the first resource control. The request-level total
timeout bounds slow-drip behavior; the read timeout separately bounds
inactivity.

That minimal patch does not independently measure encoded bytes because
`ureq` performs automatic gzip handling before exposing the reader and removes
the encoding and encoded-length headers. KCS should therefore either disable
automatic compression for this small response class and cap the identity
stream, or use a transport that exposes the raw reader so it can apply an
encoded ceiling before decompression and a decoded ceiling afterward. A
`Content-Length` precheck is a useful fast rejection, but it cannot replace
the streaming cap because the header may be absent, wrong, chunked, or refer
only to compressed bytes.

Further hardening should deserialize into a typed response rather than a
general `Value`, ignore unneeded fields without retaining them, and use a
bounded sequence visitor to stop after the expected number of embeddings and
768 values per embedding. The existing equality checks should remain as
defense in depth. Timeout and oversize errors should map consistently into
the current query fallback and index failed-task paths, with error messages
that distinguish transport failure from a provider contract violation.

### Regression tests

The fix should add network-free tests at the response-reader and transport
configuration seams:

1. Accept a valid one-item response whose decoded length is exactly the
   ceiling.
2. Reject `ceiling + 1` bytes before JSON parsing or semantic validation,
   including a valid response with an oversized irrelevant field.
3. Reject an oversized `embeddings` array and an oversized `values` array
   without collecting either into unrestricted vectors.
4. Feed an in-memory compressed body that expands past the decoded ceiling;
   if compression remains enabled, verify both encoded and decoded limits.
5. Use a recording mock transport to prove the configured 300-second value is
   passed as an overall request deadline and that explicit read/write limits
   are present.
6. Use a deterministic delayed or slow-drip reader and fake clock to verify
   that neither inactivity nor repeated small progress can exceed the total
   deadline before semantic checks.
7. Retain valid one-item and 32-item, 768-dimension cases plus wrong count,
   non-numeric value, and wrong-dimension cases.
8. Verify that bounded timeout/oversize errors reach text fallback for query
   embedding and the expected failed-task transition for index embedding.

The existing tests
`batch_embed_response_is_parsed_in_order` and
`embedding_wrong_dimension_is_contract_violation` remain useful negative and
positive semantic controls. They passed during this review, but because they
start from an already materialized `Value`, they cannot cover the vulnerable
transport-to-parser transition by themselves.

## Summary

KCS correctly limits expected embedding batches and rejects semantically
wrong response counts, JSON types, and dimensions. The vulnerability lies one
layer earlier: the real Gemini client uses default `ureq` timing and fully
materializes an unbounded, automatically decompressed response before any of
those checks can run. An approved remote peer can therefore hold the current
query or index operation open indefinitely or force substantial transient
resource consumption with bytes that KCS will later reject.

The included offline harness demonstrates the repaired ordering without
network traffic or credentials. A P2 fix should wire the documented timeout,
enforce total/read/write deadlines, cap encoded and decoded response bytes,
and preserve the current semantic checks behind those bounds. Variant review
should then examine other online adapter response paths for the same one-off
client plus `into_json` pattern, while keeping their distinct protocol and
impact characteristics separate.
