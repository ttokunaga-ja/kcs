# Attack-path analysis: Gemini vectors lack numeric-domain and positive-norm validation

- Candidate: `KCS-R23-CAND-003`
- Ledger row: `KCS-R23-CAND-003`
- Instance key: `KCS-R23-CAND-003`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| remote response parser | `crates/kcs-adapter/src/gemini_embedding.rs` | `153-203` |  |
| persistence caller | `crates/kcs-cli/src/main.rs` | `7727-7768` |  |
| vector store and KNN | `crates/kcs-index/src/embedding_store.rs` | `91-146,240-264` |  |

## Scope and actor

### Context

Remote adapter responses are explicitly untrusted in the threat model. This path crosses from an approved remote response into authoritative local vector state and native SQLite/vector processing.

### In scope

Yes.

### Exposure and identity

Outbound client workflow reachable by the configured remote service; KCS itself has no inbound listener.

The KCS user makes an approved request with the configured adapter identity; the remote service controls the returned numeric values.

### Boundary crossed

Yes.

### Authorization scope

remote response to a previously approved outbound adapter call

## Preconditions and attacker control

### Assumptions

- Online embedding is enabled and the configured service returns attacker-controlled or faulty response data.
- The response satisfies existing count, numeric-JSON, and width checks.

### Preconditions

- The operator must approve and invoke online embedding.
- The remote service must return width-correct but non-f32-finite or zero-norm numeric values.

### Attacker control

yes: the in-scope remote response actor directly controls vector elements

### Vector

remote

## Attack path

- The operator authorizes an outbound Gemini embedding operation.
- The remote adapter returns a shape- and width-correct JSON vector containing a finite f64 value outside the f32 range or an exact-width zero vector.
- The parser casts values to f32 and performs no finite-range or positive-norm validation.
- The malformed vector is used as a query vector or persisted as authoritative embedding state.
- KNN distance decoding fails, and a persisted malformed vector continues to disable vector search for the scope.

## Impact and reach

- Category: remote numeric-domain validation failure causing persistent vector-index denial of service
- Impact: **medium**
- Likelihood: **high**

### Impact surface

authoritative embedding data, native vector query runtime, and search availability

### Target reach

the affected scope's vector index and later vector searches/rebuilds

### Secret references

- The configured Gemini credential is used for the approved request; the defect does not redirect or disclose it.

## Controls and counterevidence

### Existing controls

- JSON numeric parsing.
- Response count and dimension validation.
- Transactional authoritative embedding persistence and profile-aware identity.

### Mitigations

- JSON syntax rejects literal NaN and Infinity.
- Response count and vector width are checked.
- Online adapter approval is required.
- Text search remains an online-independent fallback.

### Counterevidence

- Literal JSON NaN/Infinity is rejected and ordinary provider vectors are normalized.
- The operator must first approve the remote adapter.
- The demonstrated failure disables vector KNN, not baseline text search or the whole local archive.

### Blind spots or proof gap

- The receipts do not quantify how readily the official configured service can emit these values absent compromise or fault.
- Recovery effort for already persisted malformed vectors is not measured.

## Final decision

A single approved call gives the in-scope remote response actor direct control over the missing predicate, while persistence extends impact beyond one response. Scope-limited vector-search denial is Medium impact; remote direct control supports High likelihood, mapping to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
