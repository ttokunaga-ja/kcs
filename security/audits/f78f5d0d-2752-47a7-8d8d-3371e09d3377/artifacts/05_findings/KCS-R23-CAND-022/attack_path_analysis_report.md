# Attack-path analysis: Mistral model resolution lacks response-body and read-time bounds

- Candidate: `KCS-R23-CAND-022`
- Ledger row: `KCS-R23-CAND-022`
- Instance key: `KCS-R23-CAND-022`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.98)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| default mutable model alias | `crates/kcs-adapter/src/catalog.rs` | `150-157` |  |
| normal and resolve-only wrappers | `crates/kcs-adapter/src/catalog.rs` | `134-146,159-192` |  |
| model-list GET and full JSON materialization | `crates/kcs-adapter/src/mistral_ocr.rs` | `83-110` |  |
| unwired timeout control | `crates/kcs-core/src/scope.rs` | `1581-1590` |  |
| documented timeout policy | `crates/kcs-core/schemas/config.schema.json` | `124-139` |  |

## Scope and actor

### Context

This is a distinct pre-OCR remote availability path. The provider destination is selected by the operator, but remote response behavior is explicitly untrusted in the threat model.

### In scope

yes; remote model-catalog timing and body bounds fall under the adapter and bounded-processing invariants I3, I6, and I12

### Exposure and identity

outbound remote model-list request after online-adapter authorization; no inbound listener

KCS uses the victim OS identity and configured Mistral credential; the connected peer controls response timing and bytes

### Boundary crossed

yes; remote response behavior crosses the adapter boundary into synchronous victim-process time and memory consumption

### Authorization scope

internal-only; operator-approved authenticated adapter operation

## Preconditions and attacker control

### Assumptions

- The mutable default alias is used rather than a fixed immutable model.
- An online Mistral operation is authorized and a connected remote peer behaves maliciously or incorrectly.

### Preconditions

plausible: default mutable alias, approved online use, and a malicious, compromised, or faulty connected endpoint or intermediary

### Attacker control

yes; the remote peer controls header/body timing and compressed or uncompressed model-list size

### Vector

remote

## Attack path

- The operator uses the default mutable Mistral model alias in an approved online workflow.
- KCS performs the authenticated model-list request before OCR.
- The configured remote endpoint, proxy, or intermediary slow-streams or returns an oversized or compressed model-list body.
- KCS reads, decompresses, and fully materializes the JSON without a read or overall deadline or byte ceiling before family and stability filtering, hanging the command or consuming substantial memory.

## Impact and reach

- Category: remote response resource exhaustion / missing deadline (CWE-400, CWE-770)
- Impact: **medium**
- Likelihood: **high**

### Impact surface

command availability and transient process memory/CPU before OCR

### Target reach

one online Mistral command and selected scope per malicious catalog response

### Secret references

- The configured Mistral API credential is attached to the already approved model-list request; no unintended recipient was established.

## Controls and counterevidence

### Existing controls

- fixed-model bypass
- 30-second connect timeout
- authenticated request
- HTTP, JSON, model-family, and stability validation after materialization

### Mitigations

- A fixed immutable model bypasses model-list resolution.
- Connection establishment has a 30-second timeout.
- Credentials, HTTP status mapping, JSON validity, and post-parse family/stability filters remain enforced.

### Counterevidence

- Fixed model pins avoid the vulnerable request.
- Connect time is bounded and semantic model filtering prevents adoption of unrelated IDs, but both controls fail to bound a connected peer's read or body.

### Blind spots or proof gap

- No loopback timing or body-size measurement was retained; exact resource thresholds remain unknown.

## Final decision

The connected remote peer is a realistic in-scope attacker source on the default approved path. Impact is local availability rather than compromise, and the required matrix maps medium impact plus high likelihood to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
