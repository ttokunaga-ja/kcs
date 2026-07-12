# Attack-path analysis: same-batch duplicate embedding identities split authoritative and KNN vectors

- Candidate: `KCS-R23-CAND-068`
- Ledger row: `KCS-R23-CAND-068`
- Instance key: `KCS-R23-CAND-068`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| embedding identity | `crates/kcs-index/src/embedding_store.rs` | `10-27` |  |
| all-read planning | `crates/kcs-cli/src/main.rs` | `7675-7708` |  |
| sequential response writes | `crates/kcs-cli/src/main.rs` | `7726-7769` |  |
| first-wins source and current-vector KNN | `crates/kcs-index/src/embedding_store.rs` | `86-145` |  |

## Scope and actor

### Context

Remote adapter responses are explicitly untrusted. The path crosses from response-controlled vector bytes into an authoritative local embedding identity and a derived native KNN projection that disagree about the same content.

### In scope

Yes.

### Exposure and identity

Approved outbound embedding workflow whose response is controlled by the configured remote service; KCS has no inbound listener.

The KCS user authorizes the adapter call. The remote service controls each returned vector, while KCS is responsible for enforcing one canonical vector per content/profile identity.

### Boundary crossed

Yes.

### Authorization scope

remote response to a previously approved outbound embedding request

## Preconditions and attacker control

### Assumptions

- Two equal texts under the same profile occur in one write-before-reprobe batch while retaining distinct chunk IDs.
- The configured remote adapter is faulty, variable, compromised, or malicious and returns different width-valid vectors for the duplicates.
- Vector search or downstream evidence selection relies on the divergent derived rows before repair/rebuild.

### Preconditions

- The same batch must contain duplicate embedding identities that were all probed before any write.
- The adapter must return non-identical vectors that satisfy existing count, dimension, and representation checks.
- A consumer must use vector KNN results before an eventual rebuild normalizes the derived rows.

### Attacker control

yes: the in-scope remote response actor directly chooses both valid-looking vector payloads and can recognize duplicate inputs in the same request

### Vector

remote

## Attack path

- A normal embedding batch contains two distinct chunks whose equal text and profile produce the same authoritative embedding identity.
- Batch planning probes both identities before either write and sends both equal texts because it does not group duplicate misses.
- The untrusted remote adapter returns two shape-valid but non-identical vectors for the equal inputs.
- The first response creates the authoritative embeddings row; the conflicting second insert is ignored, but each response's current vector is independently linked into its chunk_vec row.
- KNN search observes different vectors for the same authoritative identity, while a later rebuild relinks both chunks from the first vector and changes search ordering or evidence selection.

## Impact and reach

- Category: authoritative/derived embedding identity split and search-evidence integrity
- Impact: **medium**
- Likelihood: **high**

### Impact surface

trusted vector-index integrity, KNN ordering, and evidence selection within one scope

### Target reach

duplicate-content chunks in the affected batch and the scope's derived vector search until rebuild

### Secret references

- The configured embedding credential authenticates the approved request; no credential disclosure or destination change is shown.

## Controls and counterevidence

### Existing controls

- Text/profile-derived embedding IDs provide the intended authoritative identity.
- All-read planning checks existing rows but does not deduplicate same-batch misses.
- ON CONFLICT DO NOTHING preserves the first authoritative row, while link_chunk_vec incorrectly consumes the current response vector.
- Rebuild uses the authoritative row and exposes the prior projection inconsistency.

### Mitigations

- Embedding identity already binds text hash and profile.
- Response count and vector dimension are checked.
- The authoritative embeddings table keeps the first vector, and a later rebuild relinks derived rows from it.
- Baseline text search remains available and no credential or document-confidentiality bypass is caused by the split itself.

### Counterevidence

- Stable deterministic adapters ordinarily return equal or near-equal vectors for identical text.
- The configured adapter is already entrusted to generate semantic vectors and can degrade search quality without this identity collision.
- The defect requires same-batch duplicates and conflicting responses; later rebuild converges both chunks to the first authoritative vector.
- No confidentiality, code-execution, authorization, or monetary-cap impact is involved.

### Blind spots or proof gap

- The validation reproduces storage divergence but does not quantify downstream decisions made from altered KNN ordering.
- Duplicate-text batch frequency and legitimate provider nondeterminism are not measured.

## Final decision

The remote response actor is realistic and directly controls the conflicting payloads, so the path is reportable. However, the incremental impact is bounded to vector/evidence integrity in one scope, the provider already supplies semantic vectors, and rebuild converges the rows; Medium impact with High likelihood maps mechanically to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
