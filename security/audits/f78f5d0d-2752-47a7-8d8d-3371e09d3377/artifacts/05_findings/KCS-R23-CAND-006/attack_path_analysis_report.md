# Attack-path analysis: lexical PDF page markers amplify derived work without a cardinality bound

- Candidate: `KCS-R23-CAND-006`
- Ledger row: `KCS-R23-CAND-006`
- Instance key: `KCS-R23-CAND-006`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| lexical page counter | `crates/kcs-adapter/src/deterministic.rs` | `415-437` |  |
| page-vector expansion | `crates/kcs-pipeline/src/prepare.rs` | `315-349` |  |
| unit materialization | `crates/kcs-pipeline/src/prepare.rs` | `102-170` |  |
| input-size-only control | `crates/kcs-cli/src/main.rs` | `9047-9061` |  |

## Scope and actor

### Context

Ordinary untrusted local content is an explicit attack surface, and the threat model treats persistent application-wide denial of service from such content as material. The missing derived-cardinality bound is after the raw-byte control.

### In scope

Yes.

### Exposure and identity

Operator-mediated local file ingestion; no listener or network prerequisite.

The lower-trust contributor controls the PDF bytes; parsing and allocation occur with the KCS user's process resources.

### Boundary crossed

Yes.

### Authorization scope

untrusted direct-child content processed by a local operator command

## Preconditions and attacker control

### Assumptions

- A local content contributor can place or revise a PDF in an indexed scope.
- The PDF stays on the deterministic path by retaining printable content.
- The operator runs normal indexing.

### Preconditions

- A crafted PDF must contain enough compact /Page-like tokens while remaining under the input cap.
- The deterministic preparation path must be selected.
- The operator must index the scope.

### Attacker control

yes: the in-scope local content contributor directly controls the marker count and PDF persistence

### Vector

none

## Attack path

- A lower-trust scope contributor supplies a PDF containing one printable stream and many compact lexical /Page prefixes that are not structural page objects.
- Normal indexing accepts the file under the raw-byte cap and the deterministic helper counts each prefix as a page.
- Preparation pads the page vector to that attacker-controlled count and allocates an owned PreparedUnit for every synthetic page.
- Derived allocation and processing exhaust process resources, and the persistent file retriggers the condition on later indexing.

## Impact and reach

- Category: derived-cardinality amplification and persistent local denial of service
- Impact: **high**
- Likelihood: **medium**

### Impact surface

CPU/memory availability and preparation/indexing liveness

### Target reach

the KCS indexing process for any scope containing the persistent crafted PDF

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- Raw input byte cap.
- Scanned-PDF/OCR fallback selection.
- Normal direct-child scope filtering.

### Mitigations

- A default 100 MiB raw input cap exists.
- Some wholly non-text PDFs take an OCR fallback path.
- Validation avoided actually exhausting memory and computed the unsafe upper range.

### Counterevidence

- The raw file is capped at 100 MiB.
- Non-text inputs may route away from deterministic preparation.
- No cross-scope corruption or code execution is shown.

### Blind spots or proof gap

- The unsafe upper bound was calculated rather than allocated, so the exact failure threshold depends on host resources.
- The receipt does not measure whether partial derived artifacts survive an out-of-memory termination.

## Final decision

A realistic untrusted PDF deterministically controls millions of derived units and can repeatedly exhaust the local application. That supports High availability impact, while crafted content plus operator indexing and path selection make likelihood Medium; the matrix yields Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
