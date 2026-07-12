# OCR bounding-box arithmetic can overflow

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
parses Mistral OCR image bounding boxes from an untrusted remote OCR
response and normalizes object-style `x`/`y`/`w`/`h` coordinates with
unchecked signed addition. If the OCR service, a compatible configured OCR
endpoint, or an attacker who can influence that response returns values such
as `x = i64::MAX` and `w = 1`, the parser evaluates `x1 + w` before any
range or geometry check.

In an overflow-checked Rust build this panics during the approved OCR
operation. In a default optimized build with overflow checks disabled, the
same expression can wrap and carry an inverted bounding box such as
`[9223372036854775807, 0, -9223372036854775808, 1]` into the extracted-image
metadata. The impact is bounded to OCR availability and metadata integrity,
with no demonstrated authorization bypass or credential disclosure, so I rate
it Medium.

I reviewed the vulnerable revision directly and ran the local synthetic PoC
included with this report; I did not send traffic to Mistral or any live OCR
endpoint, and I did not identify a fixed upstream revision in this write-up.
The affected version set is therefore "revision
`0e19f3c6489da458e93a982a333c308d92d0a0ae` and any build carrying the same
`parse_bbox` implementation."

## Background

The affected component is the online Mistral OCR markdownize adapter. KCS
builds a request from an approved local input document, sends it to the
configured OCR API, deserializes the JSON response, and converts each returned
page into a `MarkdownUnit`. The remote OCR response is not an inbound KCS API
entry point, but it is still an untrusted boundary: once a KCS user authorizes
the OCR operation, the remote service controls the returned page, image, and
bounding-box fields.

The response enters the parser immediately after the HTTP client converts the
body to `serde_json::Value`:

```rust
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

From here we should expect the parser to treat every coordinate as remote
input. The parser has response-shape checks, for example it requires
`pages` to be an array and it decodes image base64 before building the
`OcrImage`, but those checks do not establish any numeric range invariant for
geometry.

The image object stores the parsed bounding box as an optional four-element
signed tuple:

```rust
pub struct OcrImage {
    pub bytes: Vec<u8>,
    pub media_type: String,
    pub bbox: Option<[i64; 4]>,
    pub confidence: Option<String>,
}
```

That representation needs a simple invariant to stay useful downstream:
coordinates should be finite product-domain coordinates, the right edge should
not precede the left edge, the bottom edge should not precede the top edge,
and arithmetic used to derive those edges must not overflow.

## Vulnerability Details

The reachable call chain is compact. `parse_ocr_response` takes the remote
JSON, extracts the `pages` array, and maps each page through
`parse_ocr_page`:

```rust
fn parse_ocr_response(value: Value, model_pin: &str) -> Result<OcrResponse> {
    let pages = value
        .get("pages")
        .and_then(Value::as_array)
        .ok_or_else(|| AdapterError::ContractViolation("OCR response missing pages".to_owned()))?
        .iter()
        .enumerate()
        .map(|(fallback_index, page)| parse_ocr_page(page, fallback_index))
        .collect::<Result<Vec<_>>>()?;
    Ok(OcrResponse {
        pages,
        model_version_pin: value
            .get("model")
            .and_then(Value::as_str)
            .unwrap_or(model_pin)
            .to_owned(),
    })
}
```

Each page then passes every remote image object into `parse_ocr_image`. The
important line is the `bbox` assignment: if the image contains a dedicated
`bbox` field, KCS parses that value; otherwise it treats the full image object
as the coordinate container.

```rust
fn parse_ocr_image(value: &Value) -> Result<OcrImage> {
    let raw_base64 = value
        .get("image_base64")
        .or_else(|| value.get("base64"))
        .and_then(Value::as_str)
        .unwrap_or_default();
    let (media_type, data) = split_data_uri(raw_base64);
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(data)
        .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
    Ok(OcrImage {
        bytes,
        media_type: value
            .get("media_type")
            .and_then(Value::as_str)
            .unwrap_or(media_type)
            .to_owned(),
        bbox: parse_bbox(value.get("bbox").unwrap_or(value)),
        confidence: value.get("confidence").map(|confidence| {
            confidence
                .as_str()
                .map(str::to_owned)
                .unwrap_or_else(|| confidence.to_string())
        }),
    })
}
```

At this point we control the `bbox` value as part of the OCR response. If the
value is an array of four integers, `parse_bbox` returns the four integers
directly. That path is a useful negative control for this overflow, because it
does not perform the `x + w` or `y + h` calculation. The overflow path is the
object form that supplies a top-left coordinate plus a width or height:

```rust
fn parse_bbox(value: &Value) -> Option<[i64; 4]> {
    if let Some(array) = value.as_array() {
        if array.len() == 4 {
            return Some([
                array[0].as_i64()?,
                array[1].as_i64()?,
                array[2].as_i64()?,
                array[3].as_i64()?,
            ]);
        }
    }
    let x1 = value
        .get("top_left_x")
        .or_else(|| value.get("x"))
        .and_then(Value::as_i64)?;
    let y1 = value
        .get("top_left_y")
        .or_else(|| value.get("y"))
        .and_then(Value::as_i64)?;
    let x2 = value
        .get("bottom_right_x")
        .or_else(|| value.get("x2"))
        .and_then(Value::as_i64)
        .or_else(|| value.get("w").and_then(Value::as_i64).map(|w| x1 + w))?;
    let y2 = value
        .get("bottom_right_y")
        .or_else(|| value.get("y2"))
        .and_then(Value::as_i64)
        .or_else(|| value.get("h").and_then(Value::as_i64).map(|h| y1 + h))?;
    Some([x1, y1, x2, y2])
}
```

The type conversion to `i64` is not enough protection. It proves only that the
remote field is representable as a signed 64-bit integer; it does not prove
that adding `w` to `x1` or adding `h` to `y1` is representable. If we carry
`x1 = i64::MAX` and `w = 1` into the closure, the vulnerable expression is
the ordinary signed addition `x1 + w`. There is no `checked_add`, no
`saturating_add`, no upper page-bound check, and no later
`x2 >= x1 && y2 >= y1` predicate.

The resulting `OcrImage` is not discarded. `page_metadata` serializes each
image's `bbox` into the `images` metadata array:

```rust
fn page_metadata(model_version_pin: &str, images: Option<&[OcrImage]>) -> BTreeMap<String, Value> {
    let mut metadata = BTreeMap::new();
    metadata.insert("model_version_pin".to_owned(), json!(model_version_pin));
    let image_values = images
        .unwrap_or(&[])
        .iter()
        .map(|image| {
            json!({
                "hash": image_hash(&image.bytes),
                "media_type": image.media_type,
                "bbox": image.bbox,
                "confidence": image.confidence,
            })
        })
        .collect::<Vec<_>>();
```

So the bad state has two build-dependent shapes. With overflow checks enabled,
we fail before the metadata object can be built. With overflow checks disabled,
we continue with a wrapped and inverted coordinate in normal product metadata.
Both outcomes are outside the parser's expected contract: a malformed OCR
response should be rejected as a contract violation, not converted into a
panic or accepted as impossible geometry.

## Exploitability Analysis

The strongest route is a response-level denial of service or operation abort
against a KCS process performing OCR. We do not need to control the local
document bytes or the Mistral request body after the user has approved the
operation. We only need the OCR response to include an image object with valid
or empty base64 and a `bbox` object such as:

```json
{
  "image_base64": "",
  "bbox": {
    "x": 9223372036854775807,
    "y": 0,
    "w": 1,
    "h": 1
  }
}
```

In a checked build, the first overflow in `x1 + w` panics. Depending on how
the surrounding binary is compiled and supervised, that can fail only the OCR
task, unwind through a worker boundary, or abort the process if panic strategy
or runtime policy turns the panic into process termination. I did not measure
batch-wide recovery behavior, so the conservative claim is availability harm
to the active OCR operation and possibly its worker process.

In a default optimized build with overflow checks disabled, the same payload
can become a metadata-integrity primitive. We can make `x2` wrap to
`i64::MIN`, producing an impossible box where the right edge is far to the
left of the left edge. We can do the same on the vertical axis with
`y = i64::MAX, h = 1`, or we can choose negative widths and heights that do
not overflow but still invert the box. Those non-overflow invalid boxes are a
nearby geometry-validation gap; the overflow case is more severe because it
also creates a checked-build panic.

The useful constraints are also clear:

- The attacker must influence the OCR response to an OCR request that the KCS
  operator already approved.
- The vulnerable addition is reached by object-style `bbox` fields that use
  `w` or `h`. Array-style `[x1, y1, x2, y2]` values and object-style
  `x2`/`bottom_right_x` values do not exercise the addition, although they
  should still be geometrically validated.
- This path does not expose the configured OCR credential. The credential is
  used on the outbound request before the response parser handles the attacker
  controlled coordinates.
- I found no source-backed path from the wrapped metadata to memory
  corruption. The observed primitive is panic or invalid product metadata, not
  arbitrary code execution.

That combination keeps the finding out of high severity: the remote response
crosses a trust boundary and can reliably control the operands, but the
demonstrated outcome is bounded to OCR processing and downstream consumers of
the derived image metadata.

## Proof of Concept

The `poc/` directory contains a standalone Rust probe. It intentionally models
only the vulnerable arithmetic and metadata shape, not the full Mistral client,
so it can run offline with synthetic values and without any API key.

From the report directory:

```sh
cd poc
make run
```

Representative output:

```text
[checked build]
normal_bbox=[10, 5, 30, 12] inverted=false
checked_add_control=None
overflow_result=panic
[wrapping build]
normal_bbox=[10, 5, 30, 12] inverted=false
checked_add_control=None
overflow_bbox=[9223372036854775807, 0, -9223372036854775808, 1] inverted=true
```

The checked binary is compiled with `-C overflow-checks=yes` to demonstrate
the panic side of the bug. The wrapping binary is compiled with
`-C overflow-checks=no -O` to demonstrate the optimized-build metadata side.
The `checked_add_control=None` line is the defensive behavior the parser
should use instead of evaluating `x1 + w` directly.

The PoC does not contact live services, write persistent state, or require
credentials. Cleanup is just:

```sh
make clean
```

## Remediation

The invariant to restore is simple: every accepted bounding box must be
representable, non-overflowing, and geometrically valid before it is attached
to `OcrImage` metadata. Width and height should be non-negative, derived
right/bottom coordinates should be computed with `checked_add`, and the final
tuple should satisfy `x2 >= x1` and `y2 >= y1`. If KCS has page dimensions at
this layer, the parser should also reject coordinates outside those bounds;
if it does not, it should still reject arithmetic overflow and inverted
geometry.

A minimal patch shape is:

```rust
fn checked_extent(start: i64, extent: i64) -> Option<i64> {
    if extent < 0 {
        return None;
    }
    start.checked_add(extent)
}

fn valid_bbox([x1, y1, x2, y2]: [i64; 4]) -> Option<[i64; 4]> {
    if x2 < x1 || y2 < y1 {
        return None;
    }
    Some([x1, y1, x2, y2])
}

let x2 = value
    .get("bottom_right_x")
    .or_else(|| value.get("x2"))
    .and_then(Value::as_i64)
    .or_else(|| {
        value
            .get("w")
            .and_then(Value::as_i64)
            .and_then(|w| checked_extent(x1, w))
    })?;
let y2 = value
    .get("bottom_right_y")
    .or_else(|| value.get("y2"))
    .and_then(Value::as_i64)
    .or_else(|| {
        value
            .get("h")
            .and_then(Value::as_i64)
            .and_then(|h| checked_extent(y1, h))
    })?;
valid_bbox([x1, y1, x2, y2])
```

The same final `valid_bbox` predicate should be applied to the array and
explicit-corner forms so the fix does not leave a sibling invalid-geometry
acceptance path behind.

Regression tests should cover:

- object-form `{"x": i64::MAX, "y": 0, "w": 1, "h": 1}` is rejected without
  panic;
- object-form `{"x": 10, "y": 5, "w": 20, "h": 7}` still returns
  `[10, 5, 30, 12]`;
- negative `w` or `h` is rejected;
- array-form and explicit-corner boxes with `x2 < x1` or `y2 < y1` are
  rejected;
- `page_metadata` never receives an inverted `bbox` from `parse_ocr_image`.

It is also worth changing `parse_bbox` to return `Result<Option<[i64; 4]>>`
rather than `Option<[i64; 4]>`. Today, a malformed box and an absent box both
collapse to `None`, which makes it harder for the adapter to distinguish "OCR
did not provide coordinates" from "OCR provided invalid coordinates that we
rejected for safety."

## Summary

The bug is a small unchecked arithmetic operation at a trust boundary. We
start with OCR response JSON controlled by the remote service, carry its
`x`/`y`/`w`/`h` fields into `parse_bbox`, and reach `x1 + w` and `y1 + h`
without a checked-add or geometry predicate. From there, checked builds panic
and optimized builds can preserve wrapped, inverted coordinates in image
metadata.

The fix should make bounding-box parsing explicit about its numeric contract:
derive coordinates only with checked arithmetic, reject negative extents and
inverted boxes, validate all supported response shapes consistently, and add
tests that exercise the actual OCR image parsing path. Future variant review
should look for other OCR or document-layout adapters that normalize remote
coordinates from start-plus-extent fields before validating arithmetic and
geometry.
