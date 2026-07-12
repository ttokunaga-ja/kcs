# Attack-path analysis: Mistral OCR responses lack read, body, cardinality, and persistence bounds

- Candidate: `KCS-R23-CAND-020`
- Ledger row: `KCS-R23-CAND-020`
- Instance key: `KCS-R23-CAND-020`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.96)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| OCR POST and full JSON materialization | `crates/kcs-adapter/src/mistral_ocr.rs` | `112-138` |  |
| page/image/base64 expansion | `crates/kcs-adapter/src/mistral_ocr.rs` | `356-422` |  |
| pre-acceptance image persistence | `crates/kcs-adapter/src/mistral_ocr.rs` | `229-235,570-594` |  |
| late caller acceptance | `crates/kcs-cli/src/main.rs` | `6694-6696` |  |
| live input cap control | `crates/kcs-cli/src/main.rs` | `6533-6552` |  |
| unwired timeout control | `crates/kcs-core/src/scope.rs` | `1581-1590` |  |

## Scope and actor

### Context

The remote adapter response is explicitly untrusted in the threat model even though the destination is operator-selected. The path affects availability and pre-acceptance storage during an approved outbound workflow; it does not bypass authorization or disclose data to a new origin.

### In scope

yes; remote response timing, size, decompression, cardinality, and persistence are explicit I6/I12 surfaces

### Exposure and identity

outbound remote connection only; KCS has no public listener and the path begins after online-adapter approval

KCS uses the victim OS identity and configured Mistral credential; the untrusted remote peer controls response timing and content but gains no additional local identity

### Boundary crossed

yes; authenticated remote response bytes cross the adapter boundary into local memory, CPU, and CAS disk writes

### Authorization scope

internal-only; operator-approved authenticated adapter operation, not a public inbound endpoint

## Preconditions and attacker control

### Assumptions

- An operator-approved online OCR request is made.
- The configured service, proxy, or intermediary is faulty, compromised, or hostile.
- The response remains syntactically processable long enough to drive the unbounded sinks.

### Preconditions

plausible: an eligible approved OCR operation reaches a connected peer that can control the response; no local privilege or private-store write is required

### Attacker control

yes; the connected remote peer controls response timing, wire/decompressed body size, pages, markdown, images, and base64 values

### Vector

remote

## Attack path

- The operator configures and authorizes an online Mistral OCR operation for an eligible document.
- The configured remote service, proxy, or intermediary accepts the authenticated request and slow-streams or returns an oversized or highly expanded response.
- KCS reads and decompresses the complete JSON without a read or overall deadline or byte ceiling, then collects all pages, markdown, and images and decodes every base64 image.
- Images are persisted before the caller's acceptance check, allowing the remote peer to hang the command or consume substantial memory, CPU, and disk.

## Impact and reach

- Category: uncontrolled resource consumption from remote response (CWE-400, CWE-770)
- Impact: **medium**
- Likelihood: **high**

### Impact surface

runtime memory, CPU, command availability, store-lock duration, and archive disk usage

### Target reach

one online OCR command, its selected scope, and image CAS per malicious response

### Secret references

- The configured Mistral API credential and document body are sent to the already approved origin; no unintended credential recipient was established.

## Controls and counterevidence

### Existing controls

- online opt-in and current input-size check
- 30-second connect timeout
- request page scoping
- post-materialization response validation
- content-addressed atomic image publication

### Mitigations

- The supported CLI rechecks the local input cap before sending.
- Connection establishment has a 30-second timeout.
- Online approval, page-scoped requests, JSON shape checks, content-addressed deduplication, and atomic publication narrow the path.

### Counterevidence

- The outbound request body is bounded by effective_max_input_bytes on the shipped CLI path.
- Later acceptance checks can reject bad semantic output, but run only after response allocation and image persistence.
- A well-behaved provider ordinarily constrains responses, but the threat model treats provider behavior as untrusted.

### Blind spots or proof gap

- No loopback slow-read or oversized-body measurement was retained; the exact resource constants remain unmeasured.

## Final decision

A remote adapter response is a realistic in-scope attacker source once an ordinary approved OCR request occurs. The path is bounded to availability and disk effects, and the required matrix maps medium impact plus high likelihood to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
