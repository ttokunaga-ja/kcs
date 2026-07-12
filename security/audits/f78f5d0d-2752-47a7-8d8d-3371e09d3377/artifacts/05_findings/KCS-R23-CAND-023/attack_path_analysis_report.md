# Attack-path analysis: Gemini embedding responses lack body and read-time bounds before semantic checks

- Candidate: `KCS-R23-CAND-023`
- Ledger row: `KCS-R23-CAND-023`
- Instance key: `KCS-R23-CAND-023`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.98)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| Gemini POST and full JSON materialization | `crates/kcs-adapter/src/gemini_embedding.rs` | `120-149` |  |
| post-materialization semantic checks | `crates/kcs-adapter/src/gemini_embedding.rs` | `153-203` |  |
| query consumer | `crates/kcs-cli/src/main.rs` | `7179-7204` |  |
| index batch and persistence consumer | `crates/kcs-cli/src/main.rs` | `7420-7423,7526-7547,7726-7768` |  |
| unwired timeout control | `crates/kcs-core/src/scope.rs` | `1581-1590` |  |

## Scope and actor

### Context

The attack is limited to pre-validation availability. Invalid vectors are not persisted, query errors can fall back to text, and the fixed adopted model avoids model-resolution risk, but a connected peer still controls synchronous response time and allocation.

### In scope

yes; untrusted remote response timing and body expansion are explicit I6/I12 surfaces

### Exposure and identity

outbound remote embedding request after adapter activation and authorization; no public inbound endpoint

KCS uses the victim OS identity and configured Gemini credential; the remote peer controls only response behavior

### Boundary crossed

yes; untrusted remote response bytes cross into victim-process memory, CPU, and command latency before semantic validation

### Authorization scope

internal-only; operator-approved authenticated adapter operation

## Preconditions and attacker control

### Assumptions

- An operator-approved Gemini query or indexing request is made.
- The connected provider, proxy, or intermediary is faulty, compromised, or hostile.

### Preconditions

plausible: an approved query or index call reaches a connected malicious or malfunctioning remote peer

### Attacker control

yes; the remote peer controls response timing, compressed/decompressed body size, irrelevant fields, and response-array cardinality before checks

### Vector

remote

## Attack path

- The operator activates the Gemini embedding adapter and runs an online query or index operation.
- KCS sends a one-item query or at-most-32-item index batch to the configured remote service.
- The service, proxy, or intermediary slow-streams or returns an oversized or highly compressed JSON response.
- KCS fully reads, decompresses, and materializes the response before count, numeric-type, and dimension checks, allowing the remote peer to block the operation or consume substantial transient resources.

## Impact and reach

- Category: remote response resource exhaustion / missing deadline (CWE-400, CWE-770)
- Impact: **medium**
- Likelihood: **high**

### Impact surface

query/index availability and transient process memory/CPU

### Target reach

one query or index batch and its KCS process per malicious response

### Secret references

- The configured Gemini API credential and intended query/chunk text reach the approved origin; no additional secret disclosure was established.

## Controls and counterevidence

### Existing controls

- online activation and authorization
- 30-second connect timeout
- fixed embedding model
- request batch cap
- post-materialization count, type, and dimension validation
- error fallback and failed-task handling

### Mitigations

- Connection establishment has a 30-second timeout and the embedding model is fixed.
- Query sends one item and index batches at most 32.
- Response count, numeric JSON type, and dimension are checked after parsing.
- Invalid responses are not persisted; query errors fall back to text and index errors become failed tasks.

### Counterevidence

- Small request batches and post-parse shape checks bound accepted semantic output, not the body materialized before those checks.
- No invalid vectors are persisted and a returned query error degrades to text search.

### Blind spots or proof gap

- No loopback slow-read or oversized-body measurement was retained; exact memory and timing thresholds remain unmeasured.

## Final decision

Remote response control is realistic and explicitly in scope once an ordinary approved operation occurs. Existing controls prevent durable bad vectors but not the availability sink; medium impact plus high likelihood maps to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
