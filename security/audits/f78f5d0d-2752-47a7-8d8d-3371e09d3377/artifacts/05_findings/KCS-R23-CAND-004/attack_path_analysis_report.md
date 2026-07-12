# Attack-path analysis: OCR bounding-box arithmetic can overflow

- Candidate: `KCS-R23-CAND-004`
- Ledger row: `KCS-R23-CAND-004`
- Instance key: `KCS-R23-CAND-004`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| bbox parser | `crates/kcs-adapter/src/mistral_ocr.rs` | `434-463` |  |
| metadata sink | `crates/kcs-adapter/src/mistral_ocr.rs` | `398-422,466-480` |  |

## Scope and actor

### Context

The remote response is an in-scope untrusted source. The missing arithmetic check lets that source affect process availability or derived metadata beyond a normal rejected OCR response, but it does not bypass authorization.

### In scope

Yes.

### Exposure and identity

Outbound OCR client workflow controlled by the configured remote service; no inbound KCS listener exists.

The KCS user performs an approved OCR call; the remote service controls the response coordinates but gains no KCS credential or filesystem identity.

### Boundary crossed

Yes.

### Authorization scope

remote response to a previously approved OCR call

## Preconditions and attacker control

### Assumptions

- Online OCR is enabled and the remote response actor can choose bounding-box coordinates.
- The response uses the array form that reaches the unchecked additions.

### Preconditions

- An approved OCR request must reach the configured service.
- The response must include the accepted array bounding-box representation.
- Coordinates must overflow signed 64-bit addition or otherwise form unreasonable geometry.

### Attacker control

yes: the in-scope remote response actor directly controls x, y, width, and height

### Vector

remote

## Attack path

- The operator invokes an approved OCR operation.
- The remote OCR service returns the accepted array bounding-box form with extreme signed 64-bit coordinates.
- KCS computes x+w or y+h without checked arithmetic or geometry validation.
- A debug build panics and aborts the operation, while a release build can wrap the values and persist invalid extracted-image metadata.

## Impact and reach

- Category: remote-response integer overflow causing process availability or metadata-integrity failure
- Impact: **medium**
- Likelihood: **high**

### Impact surface

OCR runtime availability and extracted-image metadata integrity

### Target reach

the active OCR operation and its process/batch; no cross-scope persistence was shown

### Secret references

- The configured OCR credential is used for the approved request, with no demonstrated disclosure or forwarding.

## Controls and counterevidence

### Existing controls

- Typed response deserialization.
- Accepted response-shape checks.
- Prior adapter authorization.

### Mitigations

- Only the accepted array form reaches the addition; other forms are unaffected.
- Adapter approval is required before the request.
- The failure is confined to OCR processing and does not authorize a different destination or read.

### Counterevidence

- The remote service already can fail its own OCR response, and this issue adds no authorization bypass.
- Only one response representation reaches the overflow.
- The report shows panic or invalid coordinates, not durable cross-scope corruption.

### Blind spots or proof gap

- The final receipt does not demonstrate end-to-end release-build persistence or downstream use of wrapped coordinates.
- Batch-wide recovery effects after a panic are not measured.

## Final decision

The remote response actor directly controls the unchecked operands during an ordinary approved call. The resulting availability/metadata harm is bounded to OCR and carries no auth bypass, so impact is Medium; remote direct control makes likelihood High, mapping to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
