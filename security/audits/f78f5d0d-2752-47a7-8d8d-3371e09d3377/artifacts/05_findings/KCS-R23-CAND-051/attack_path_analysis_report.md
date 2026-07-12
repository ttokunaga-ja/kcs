# Attack-path analysis: Duplicate OCR page indices bind one provider page to multiple evidence units

- Candidate: `KCS-R23-CAND-051`
- Ledger row: `KCS-R23-CAND-051`
- Instance key: `KCS-R23-CAND-051:duplicate-page-index-content-misbinding`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.99)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| untrusted_response_parser | `crates/kcs-adapter/src/mistral_ocr.rs` | `356-395` |  |
| root_mapping_control | `crates/kcs-adapter/src/mistral_ocr.rs` | `229-276` |  |
| insufficient_acceptance | `crates/kcs-pipeline/src/markdownize.rs` | `476-511` |  |
| done_persistence_sink | `crates/kcs-cli/src/main.rs` | `6674-6696,6714-6789` |  |

## Scope and actor

### Context

Remote adapter responses and indices are explicitly untrusted. The defect crosses structural response metadata into authoritative normalized provenance, although the provider already controls OCR markdown.

### In scope

yes; remote response validation and evidence identity are covered by I6, I7, and I8

### Exposure and identity

outbound OCR workflow after operator approval; KCS has no inbound listener

KCS authenticates to the configured provider as the operator; the remote actor controls response indices/content but gains no local credential or filesystem identity.

### Boundary crossed

yes: untrusted remote page metadata is accepted as trusted normalized page identity and persisted as Done

### Authorization scope

remote response to a previously approved outbound OCR operation

## Preconditions and attacker control

### Assumptions

- An approved online OCR call reaches a service returning malformed or hostile response data.
- At least two prepared hints exist and duplicated pages contain non-empty markdown.

### Preconditions

- An operator-approved OCR request
- A response with duplicate indices that creates a missing expected index
- Non-empty markdown sufficient for existing shape validation

### Attacker control

yes over pages[].index, response order, and markdown

### Vector

remote

## Attack path

- The operator approves an OCR operation with at least two prepared page hints.
- The remote response supplies duplicate explicit indices, for example pages [(0,A),(0,B)], with non-empty markdown; parsing at crates/kcs-adapter/src/mistral_ocr.rs:356-395 does not reject them.
- BTreeMap collection at crates/kcs-adapter/src/mistral_ocr.rs:249-263 overwrites A with B, then indexed lookup and positional fallback select B for both prepared orders.
- Hint-derived distinct unit keys pass crates/kcs-pipeline/src/markdownize.rs:476-511 coverage and shape checks, and crates/kcs-cli/src/main.rs:6674-6789 persists both units and marks the task Done.
- Chunks, search results, and Evidence provenance omit A and attribute B to two page identities.

## Impact and reach

- Category: remote structural-response validation failure causing OCR page/provenance misbinding
- Impact: **medium**
- Likelihood: **high**

### Impact surface

normalized data, chunks, search integrity, and Evidence provenance

### Target reach

the affected document/task within one scope and its downstream derived state

### Secret references

- The OCR credential and document reach only the already approved provider; no additional disclosure or origin change is shown.

## Controls and counterevidence

### Existing controls

- Reject duplicate and out-of-range page indices.
- Require an exact complete index bijection before mapping content to prepared unit keys.
- Do not use positional fallback when explicit response indices are present.

### Mitigations

- Online OCR is opt-in and destination-configured.
- Typed JSON parsing and non-empty markdown checks apply.
- Expected synthesized hint keys and unit types are validated.
- Input hash, secret approval, destination, and credential controls remain intact.

### Counterevidence

- The official provider is expected to return unique, well-formed indices.
- The operator must activate OCR and choose the endpoint.
- The provider already controls OCR markdown, limiting the incremental attacker advantage to identity and provenance misbinding.
- No credential disclosure, code execution, cross-scope access, or budget bypass occurs.

### Blind spots or proof gap

- No live-provider behavior or malformed-response prevalence was measured.
- Downstream reliance on corrupted Evidence output was not quantified.

## Final decision

Hard suppression does not apply because the remote response actor is explicitly lower trust and directly controls the missing uniqueness predicate during an ordinary approved call. Durable but document-scoped provenance corruption is Medium impact; direct remote control makes likelihood High. The matrix yields Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
