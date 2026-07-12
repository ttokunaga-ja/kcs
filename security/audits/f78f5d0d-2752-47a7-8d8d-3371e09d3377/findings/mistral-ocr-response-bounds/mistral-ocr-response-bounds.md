# Mistral OCR responses lack read, body, cardinality, and persistence bounds

## Executive Summary

KCS's online Mistral OCR adapter trusts a successful remote response to finish
and fit in local resources.  Once a connection is established, the adapter has
no read or overall deadline.  It deserializes the complete, transparently
decompressed response into an unrestricted `serde_json::Value`, collects every
page and image, clones every Markdown string, and base64-decodes every image.
It then writes images from every returned page to the image CAS before the CLI
checks whether the response is acceptable for the pages it requested.

A faulty, compromised, or hostile configured OCR service, proxy, or
intermediary can therefore slow-stream a valid response to hold a command open,
or return a syntactically valid oversized response to consume process memory,
CPU, and archive disk.  An `index` invocation also holds the KCS store lock
end-to-end while it waits.  This is an availability and resource-governance
failure; it does not establish code execution, authentication bypass, path
traversal, or disclosure to a previously unauthorized destination.

The final rating is **Medium / P2** (CWE-400 and CWE-770).  The operation must be
an operator-approved online OCR call, and the connected peer must misbehave, but
that peer directly controls response timing and content across the adapter trust
boundary.  Existing request-size, connection-establishment, page-scoping,
content-addressing, and atomic-write controls do not bound this response path.

I reviewed revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` and its locked
`ureq 2.12.1` source directly.  I also ran the existing image-persistence and
page-scoping unit tests and the included in-memory boundary probe.  I did not
contact Mistral or another service, use credentials, slow a real socket, exhaust
memory, or write a large response to disk.  No fixed revision was supplied or
identified, so the affected-version claim is limited to the reviewed revision.

## Background

KCS uses the Mistral OCR adapter to turn supported non-text-native documents
into Markdown and extracted image objects.  The live CLI path constructs a
`MistralOcrMarkdownizeAdapter` with an image-store directory and invokes it from
`run_standard_online_markdownize`:

```rust
// crates/kcs-adapter/src/catalog.rs:134-147
let client = EnvMistralOcrClient::new();
let configured_model = declared_markdown_model();
let model_pin = client.resolve_model_pin(&configured_model)?;
let adapter = MistralOcrMarkdownizeAdapter::new(client, model_pin, request.scope_id)
    .with_image_store(request.kcs_dir);
let profile = adapter.profile();
let mut adapter_request = adapter_request;
adapter_request.tool_profile_hash = profile.tool_profile_hash.clone();
let response = adapter.markdownize(adapter_request)?;
```

The supported CLI route has several important safeguards.  Online adapter use
requires operator authorization.  Immediately before a send, the CLI rereads
the local file, verifies its queued hash, and checks it against
`effective_max_input_bytes`; the documented default is 100 MiB
(`crates/kcs-cli/src/main.rs:6533-6552,4425-4434`).  Incremental sends and
unit-scoped retries can include a `pages` list so the request asks the provider
to process only specific page indexes.  These controls bound the source
document and narrow what KCS requests.  They do not constrain what a connected
peer returns.

The response path has five distinct resource boundaries, each of which needs an
independent invariant:

```text
remote response stream
  -> compressed and decompressed response bytes
  -> JSON pages / Markdown / image cardinality
  -> decoded image bytes
  -> accepted requested-page output
  -> durable unique image bytes
```

A defensive implementation should stop at any boundary that exceeds its
budget, and it should not cross the durable-write boundary until the response
has passed request-specific acceptance checks and a persistence quota has been
reserved.  The reviewed implementation crosses all five boundaries without
such a policy.

## Vulnerability Details

### The OCR exchange has no effective read, overall, or body bound

We first reach `EnvMistralOcrClient::ocr_markdown`.  After reading the locally
bounded input and forming the request, it uses a one-off `ureq::post` and calls
`into_json()` directly on the response:

```rust
// crates/kcs-adapter/src/mistral_ocr.rs:125-138
let pages = request_pages(request);
let value: Value = ureq::post(&format!("{}/v1/ocr", self.base_url()))
    .set("Authorization", &format!("Bearer {api_key}"))
    .set("Content-Type", "application/json")
    .send_json(ocr_request_body(
        &request.media_type,
        &bytes,
        model_pin,
        pages.as_deref(),
    ))
    .map_err(http_error)?
    .into_json()
    .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
parse_ocr_response(value, model_pin)
```

There is no `Request::timeout`, no agent read timeout, and no bounded reader.
`Cargo.lock` pins `ureq 2.12.1`.  In that version, a default agent has a 30-second
connection timeout but no read, write, or overall timeout:

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

That distinction matters.  A peer that never completes the connection is
bounded.  A peer that connects and then stops making progress, or delivers one
small chunk often enough to avoid lower-layer behavior, has no KCS deadline.
The configuration schema exposes `adapter.policy.timeout_seconds`, but the
semantic checker explicitly records that it is not threaded into the HTTP path:

```rust
// crates/kcs-core/src/scope.rs:1581-1590
// timeout_seconds: a per-adapter execution timeout is not threaded through
// the adapter HTTP path (it would touch every adapter's transport). Accept
// the documented default (300); reject any other value loudly rather than
// silently ignore it.
if let Some(timeout) = policy.get("timeout_seconds").and_then(Value::as_i64) {
    if timeout != 300 {
        return Err(KcsError::not_implemented(
            "adapter.policy.timeout_seconds other than 300",
        ));
    }
}
```

The accepted value therefore does not provide a five-minute execution bound.

`ureq::Response::into_json` delegates to
`serde_json::from_reader(self.into_reader())`.  The dependency documentation
warns callers that an untrusted body reader should be wrapped in `.take()` to
avoid exhausting memory, but KCS does not do that.  The default `gzip` feature
is active in the resolved dependency graph, and `into_reader()` wraps a gzip
response in `MultiGzDecoder` before JSON parsing.  Consequently, neither a
chunked or peer-declared wire body nor its decompressed JSON has an
application-level byte ceiling.  A `Content-Length` header is not a security
bound because the peer chooses it, and chunked responses need not provide one.

### Every page, Markdown string, image, and decoded byte is materialized

If we carry the unrestricted `Value` into `parse_ocr_response`, every element
of `pages` is collected.  Each page clones its Markdown and collects every
image.  Each image's base64 text is then decoded into a fresh owned `Vec<u8>`:

```rust
// crates/kcs-adapter/src/mistral_ocr.rs:356-407
fn parse_ocr_response(value: Value, model_pin: &str) -> Result<OcrResponse> {
    let pages = value
        .get("pages")
        .and_then(Value::as_array)
        .ok_or_else(|| AdapterError::ContractViolation("OCR response missing pages".to_owned()))?
        .iter()
        .enumerate()
        .map(|(fallback_index, page)| parse_ocr_page(page, fallback_index))
        .collect::<Result<Vec<_>>>()?;
    // ...
}

fn parse_ocr_page(value: &Value, fallback_index: usize) -> Result<OcrPage> {
    let images = value
        .get("images")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .map(parse_ocr_image)
        .collect::<Result<Vec<_>>>()?;
    Ok(OcrPage {
        // ...
        markdown: value
            .get("markdown")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned(),
        images,
    })
}

fn parse_ocr_image(value: &Value) -> Result<OcrImage> {
    let raw_base64 = value
        .get("image_base64")
        .or_else(|| value.get("base64"))
        .and_then(Value::as_str)
        .unwrap_or_default();
    let (_media_type, data) = split_data_uri(raw_base64);
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(data)
        .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
    // ...
}
```

The only root-shape check here is that `pages` is an array.  There is no maximum
for:

- response bytes before or after transparent decompression;
- page count or a requirement that page indexes are distinct and requested;
- Markdown bytes per page or in aggregate;
- images per page or in aggregate;
- base64 text length;
- decoded bytes for one image or for the response as a whole.

This is more than one large allocation.  While parsing, the full JSON value and
its base64 strings remain live as KCS clones Markdown and allocates decoded
image vectors.  Base64 text is roughly four bytes for every three decoded
bytes, so a response can transiently hold both representations, plus JSON and
allocator overhead.  Hashing, placeholder replacement, and metadata generation
then add CPU proportional to attacker-selected response content.

Request page scoping does not restore the missing invariant.  It tells a
well-behaved provider which pages KCS wants; it does not cap the response array,
reject an out-of-set index, or limit image content on a requested page.

### Image persistence happens before response acceptance

The ordering creates a durable disk variant.  Immediately after the client
returns `OcrResponse`, the adapter persists images from every returned page:

```rust
// crates/kcs-adapter/src/mistral_ocr.rs:229-253
let model_pin = self.client.resolve_model_pin(&self.configured_model)?;
let ocr = self.client.ocr_markdown(&request, &model_pin)?;
if let Some(kcs_dir) = &self.image_store_dir {
    for page in &ocr.pages {
        persist_images(kcs_dir, &page.images)?;
    }
}
// ...
let pages_by_index = ocr
    .pages
    .iter()
    .map(|page| (page.index, page))
    .collect::<BTreeMap<_, _>>();
```

Only after those writes does the adapter map requested hints to response pages.
That means images on extra response pages are durable even when those pages are
never selected as Markdown units.  `persist_images` has no per-call or
aggregate quota:

```rust
// crates/kcs-adapter/src/mistral_ocr.rs:570-591
pub fn persist_images(kcs_dir: impl AsRef<Path>, images: &[OcrImage]) -> Result<Vec<String>> {
    let mut hashes = Vec::new();
    for image in images {
        let hash = image_hash(&image.bytes);
        // derive .kcs/objects/images fan-out path from the hash
        // ...
        if !path.exists() {
            atomic_write_image_object(&path, &image.bytes)?;
        }
        hashes.push(hash);
    }
    Ok(hashes)
}
```

Content addressing deduplicates identical payloads, and
`atomic_write_image_object` prevents a torn object from appearing under a valid
hash.  Those are integrity properties, not capacity controls.  A peer can vary
each valid image payload to create a fresh hash.  Each successfully published
object remains even if a later image write fails or the response is subsequently
rejected; there is no aggregate transaction or rollback around the response.

The caller's semantic check is visibly later:

```rust
// crates/kcs-cli/src/main.rs:6674-6696
let outcome = run_standard_online_markdownize(StandardOnlineMarkdownizeRequest {
    // ...
})
.map_err(task_failure_from_adapter)?;
let profile = outcome.profile;
let response = outcome.response;
let hints = all_changed_hints(&prepare.prepared_units);
let strict_valid =
    validate_markdownize_response(&response, &hints, &prepare.prepared_units).is_ok();
```

By this point, the network body has been read, JSON and images have been
allocated and decoded, and every response-page image has already crossed the
durable-write boundary.  A post-materialization acceptance check cannot reclaim
those resources or undo the CAS writes.

### Existing controls narrow but do not close the path

The following controls are real and should remain:

- Online OCR is an explicitly authorized outbound operation, not a public
  inbound service.
- The shipped CLI rechecks the current input hash and the configured input-size
  cap before sending.  The request body is therefore not independently
  unbounded on this path.
- Default `ureq` behavior limits connection establishment to 30 seconds.
- Full, incremental, and unit-retry modes scope the pages KCS requests.
- Non-success HTTP status codes are mapped to adapter errors, `pages` must be an
  array, and invalid base64 is rejected.
- Image objects are content-addressed and crash-atomically published.

None of these controls sets a connected-peer read deadline, limits response
bytes or structure, caps decoded output, or reserves an image-persistence
budget.  They are counterevidence against broader claims, not a defense against
this finding.

## Exploitability Analysis

The relevant actor is the connected OCR peer: the configured service itself,
an intermediary or proxy, or infrastructure that has become faulty or
compromised.  The operator chooses and authorizes the destination, so this is
not an SSRF or consent bypass.  Once the legitimate request is accepted,
however, the peer controls the response stream and all fields that reach the
unbounded sinks.

The strongest availability route is a successful, slowly delivered response.
We can return valid HTTP headers, begin a JSON object, and delay completion
after the 30-second connection phase.  Because neither the request nor the
reader has an overall/read deadline, the operation remains blocked.  When this
happens through `index`, `run_index` has already acquired the store lock and
holds it end-to-end (`crates/kcs-cli/src/main.rs:558-570`), so other serialized
store operations can be delayed as well.  Reliability depends on the remote
path remaining connected and any operating-system or intermediary timeouts,
but KCS itself provides no intended 300-second stop.

For memory and CPU exhaustion, we can instead complete a valid JSON response
containing a large root field, many pages with large Markdown strings, or many
large valid base64 images.  A gzip-compressed response can make the wire body
much smaller than the decompressed JSON.  The full `Value`, cloned Markdown,
decoded images, hash work, and metadata work all occur before the caller can
judge the response.  The exact memory-to-body multiplier is allocator- and
payload-dependent, so this report does not assign a precise OOM threshold.

For durable disk consumption, we use syntactically valid, distinct image
payloads.  Extra pages are useful because their images are persisted before KCS
maps the requested hints; their Markdown need not become a normalized unit.
Making each payload unique defeats CAS deduplication.  The practical ceiling is
available filesystem space or an external filesystem quota, neither of which
is a response policy enforced by KCS.  Atomic publication ensures each object
is complete, but does not make the collection bounded or roll it back.

Several apparent alternatives are weaker or dead ends:

- Repeating one identical image spends decode and hashing work but usually
  consumes only one durable CAS object.  Unique bytes are needed for linear disk
  growth.
- Invalid JSON is rejected, but only after response bytes have been read far
  enough for parsing to fail.  Invalid base64 prevents the adapter from reaching
  persistence, so the disk route keeps every image valid.
- Extra-page Markdown is collected in memory but may be ignored when hints are
  mapped.  Images from those same pages are still persisted earlier.
- A non-success HTTP status stops the parser.  The peer returns a successful
  status and a valid `pages` array instead.
- Hash-derived paths prevent choosing an arbitrary destination file.  The
  useful primitive is resource consumption inside the image CAS, not path
  traversal or overwrite.

These constraints are why Medium / P2 is appropriate.  The finding requires an
approved online operation and a misbehaving connected peer, and its validated
impact is local availability, lock duration, and disk use rather than privilege
gain or unintended data disclosure.  Within those preconditions, the peer has
direct and reliable control of the missing bounds.

## Proof of Concept

The `poc/response_bounds_poc.py` artifact is a safe, dependency-free boundary
probe.  Its source-equivalent path performs the relevant operations in memory:
it materializes the complete JSON, traverses every page and image, decodes every
base64 value, and calculates how many unique image bytes would be written by
content-addressed persistence.  It deliberately performs no disk writes.

The same small responses then pass through a defensive model with deliberately
tiny test limits for virtual elapsed time, body bytes, pages, Markdown, image
counts, per-image decoded bytes, aggregate decoded bytes, and unique persistence
bytes.  This lets us demonstrate each missing invariant with kilobytes rather
than consume meaningful resources.

Run it from this report directory:

```sh
cd poc
python3 response_bounds_poc.py
```

Representative output from the reviewed environment is:

```text
PASS baseline: current=accepted(pages=1, images=1, decoded=200, would_persist=200); bounded=accepted(decoded=200, unique_persist=200)
PASS virtual_slow_read: current=accepted(pages=1, images=1, decoded=200, would_persist=200); bounded=rejected[deadline]
PASS body_over_limit: current=accepted(pages=0, images=0, decoded=0, would_persist=0); bounded=rejected[body_bytes]
PASS page_cardinality: current=accepted(pages=5, images=0, decoded=0, would_persist=0); bounded=rejected[pages]
PASS image_cardinality: current=accepted(pages=1, images=3, decoded=48, would_persist=48); bounded=rejected[images_page]
PASS decoded_aggregate: current=accepted(pages=2, images=3, decoded=2400, would_persist=2400); bounded=rejected[decoded_total]
PASS unique_persistence_budget: current=accepted(pages=1, images=2, decoded=1600, would_persist=1600); bounded=rejected[persist_total]
PASS cas_dedup_control: current=accepted(pages=1, images=2, decoded=1600, would_persist=800); bounded=accepted(decoded=1600, unique_persist=800)
All cases passed; no network, credentials, sleeps, or file writes were used.
```

No cleanup is required.  The virtual ticks are a deterministic policy test, not
a live measurement of `ureq`.  The body case is uncompressed and the
persistence figure is an in-memory accounting value.  I relied on exact source
for the real timeout, decompression, and write ordering and intentionally did
not build a local HTTP service or create a destructive disk-fill case.

As counterevidence, I also ran these existing exact-revision unit tests and they
passed: `q2_persist_images_writes_hash_consistent_object`,
`r14_4_full_send_has_no_pages_parameter`,
`r14_4_incremental_scopes_pages_to_changed_units`, and
`r15_5_unit_scoped_retry_scopes_pages_despite_full_mode`.  They prove atomic
image publication and request page scoping for small values; they do not assert
any response or persistence limit.

## Remediation

The invariant to restore is straightforward: an OCR response must fit one
request-specific resource budget before untrusted bytes are fully materialized
or durably published.  The budget must cover elapsed time, compressed and
decompressed body bytes, response structure, decoded images, and newly
persisted unique bytes.  Returned page indexes must also be a distinct subset
of the pages KCS requested.

First, thread a real transport policy into `EnvMistralOcrClient` and apply an
overall timeout to the OCR request.  Replace `into_json()` with a bounded read
that consumes at most `limit + 1` bytes before deserialization.  A minimal
decoded-body guard using the current `ureq` API can look like this:

```rust
use std::io::Read as _;
use std::time::Duration;

fn read_json_bounded(response: ureq::Response, max_bytes: usize) -> Result<Value> {
    let mut body = Vec::with_capacity(max_bytes.min(64 * 1024));
    response
        .into_reader() // decompressed bytes with the current ureq feature set
        .take(max_bytes as u64 + 1)
        .read_to_end(&mut body)
        .map_err(|err| AdapterError::Network(err.to_string()))?;
    if body.len() > max_bytes {
        return Err(AdapterError::ContractViolation(
            "OCR response exceeds max_decompressed_response_bytes".to_owned(),
        ));
    }
    serde_json::from_slice(&body)
        .map_err(|err| AdapterError::ContractViolation(err.to_string()))
}

let response = ureq::post(&format!("{}/v1/ocr", self.base_url()))
    .timeout(Duration::from_secs(policy.overall_timeout_seconds))
    .set("Authorization", &format!("Bearer {api_key}"))
    .set("Content-Type", "application/json")
    .send_json(request_body)
    .map_err(http_error)?;
let value = read_json_bounded(response, policy.max_decompressed_response_bytes)?;
```

This snippet fixes the immediate deadline and decompressed-body issues, but it
is not the complete compression policy.  With `ureq`'s current transparent gzip
reader, `.take()` sees bytes after decompression.  KCS should either request
`Accept-Encoding: identity`, reject any non-identity `Content-Encoding`, and
bound that single representation, or use a transport/decompression layer that
can independently count compressed wire bytes and decompressed bytes.  Merely
checking peer-supplied `Content-Length` is only an early rejection optimization,
not the streaming limit.

Second, validate response structure against checked counters before cloning or
decoding large fields.  The concrete values should be configurable secure
defaults informed by supported provider/document limits; the PoC's tiny values
are not production recommendations.  The parser should enforce at least:

```rust
if pages.len() > policy.max_pages || pages.len() > requested_pages.len() {
    return Err(contract("too many OCR response pages"));
}

let mut markdown_total = 0usize;
let mut image_total = 0usize;
let mut decoded_total = 0usize;
for page in pages {
    require_distinct_requested_index(page.index, requested_pages)?;
    markdown_total = markdown_total
        .checked_add(page.markdown.len())
        .ok_or_else(|| contract("OCR markdown size overflow"))?;
    require_at_most(page.markdown.len(), policy.max_markdown_bytes_per_page)?;
    require_at_most(markdown_total, policy.max_markdown_bytes_total)?;
    require_at_most(page.images.len(), policy.max_images_per_page)?;
    image_total = image_total
        .checked_add(page.images.len())
        .ok_or_else(|| contract("OCR image count overflow"))?;
    require_at_most(image_total, policy.max_images_total)?;

    for image in &page.images {
        require_encoded_bound_before_decode(image, policy.max_image_bytes)?;
        let bytes = decode_image(image)?;
        require_at_most(bytes.len(), policy.max_image_bytes)?;
        decoded_total = decoded_total
            .checked_add(bytes.len())
            .ok_or_else(|| contract("OCR decoded size overflow"))?;
        require_at_most(decoded_total, policy.max_decoded_image_bytes_total)?;
    }
}
```

In production code, this should preferably be a custom streaming deserializer
or a bounded schema type, so the parser can reject cardinality before building
an unrestricted `Value`.  Encoded base64 length must be checked before decode;
checking only the resulting `Vec` is too late for allocation control.  Every
aggregate counter should use `checked_add`.

Finally, move image publication after request-specific response acceptance.
Carry decoded images as staged output, hash and deduplicate them, calculate the
bytes of objects that do not already exist, and atomically reserve that
aggregate against a per-operation and per-scope quota before writing any final
object.  Only then publish the staged objects and normalized instance.  A
rejected or over-quota response should leave the image CAS unchanged.  The
existing temp-file, `fsync`, and rename logic remains useful once this
precondition is satisfied.

Regression tests should cover the real boundaries, not only helper arithmetic:

- exactly-at-limit and one-byte-over response bodies, with fixed-length,
  chunked, and compressed-expansion variants;
- a slow response that exceeds the configured overall deadline;
- one more page than requested, duplicate indexes, and an out-of-request index;
- per-page and aggregate Markdown limits;
- per-page and aggregate image-count limits;
- oversized encoded input, oversized decoded image, and aggregate decoded-byte
  overflow, including checked-counter overflow cases;
- identical-image deduplication versus distinct-image aggregate quota;
- an acceptance failure and a quota failure that both leave the image CAS
  byte-for-byte unchanged;
- concurrent responses that cannot race past the same scope quota; and
- preservation of the existing input-cap, page-scoping, atomic-write, auth,
  rate-limit, and retry behavior.

## Summary

At the reviewed revision, an approved Mistral OCR call crosses from a bounded
local input into an unbounded remote response path.  KCS provides only a
connection-establishment timeout, materializes the full decompressed JSON,
accepts arbitrary response cardinality, decodes arbitrary image bytes, and
persists every page's images before semantic acceptance.  A connected peer can
therefore hold the command and store lock or consume substantial memory, CPU,
and durable image-CAS space.

We demonstrated each missing boundary with harmless in-memory cases and
confirmed that CAS deduplication helps only for identical payloads.  The durable
fix is one end-to-end OCR response policy: real deadlines, streaming body caps,
request-bound page semantics, checked Markdown/image/decode budgets, and
quota-reserved persistence after acceptance.  Similar response consumers should
be reviewed for the same transport-and-post-parse ordering pattern, but this
report makes no claim about a separate endpoint.
