# Attack-path analysis: Deterministic PDF handling reparses the whole file once per page

- Candidate: `KCS-R23-CAND-034`
- Ledger row: `KCS-R23-CAND-034`
- Instance key: `KCS-R23-CAND-034:lexical-page-count-reparse-amplification`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| lexical_page_counter | `crates/kcs-adapter/src/deterministic.rs` | `415-437` |  |
| page_vector_and_unit_expansion | `crates/kcs-pipeline/src/prepare.rs` | `102-170,315-347` |  |
| per_hint_reparse_sink | `crates/kcs-adapter/src/deterministic.rs` | `151-156,190-249` |  |
| ordinary_index_entrypoint | `crates/kcs-cli/src/main.rs` | `9047-9118,9229-9304` |  |

## Scope and actor

### Context

The malformed-document parser path is part of normal offline indexing and requires no network, privilege, persisted-state write, or timing race. A tiny bounded control already demonstrated 64 derived units and 65 whole-file extractions from a 490-byte file.

### In scope

Yes.

### Exposure and identity

Local CLI indexing of an untrusted direct-child PDF; no daemon or remote endpoint is exposed.

The KCS process runs as the invoking OS user and consumes local CPU, heap, filesystem I/O, and the indexing/store operation; no credentials are involved.

### Boundary crossed

Verified: attacker-controlled PDF tokens cross the untrusted-parser boundary into unbounded logical page/unit cardinality and repeated local work.

### Authorization scope

internal-only

## Preconditions and attacker control

### Assumptions

- The contributor can place a crafted, readable regular PDF in a scope the operator indexes.
- The PDF remains within the raw byte-size cap and contains enough readable text to use deterministic rather than wholly-scanned OCR handling.
- The contributor chooses a large lexical marker count within the admitted file bytes.

### Preconditions

- Supply of an accepted text-bearing PDF within max_input_bytes.
- Operator ordinary indexing of the selected scope.

### Attacker control

yes — the contributor controls S and the false lexical page count P; the repeated parse relation is deterministic.

### Vector

none

## Attack path

- An in-scope content contributor supplies a small accepted PDF with one readable text layer and many false /Page-prefixed markers such as /PageX.
- pdf_page_count_in_text counts those lexical prefixes without structural validation or a page ceiling at crates/kcs-adapter/src/deterministic.rs:419-437.
- Preparation pads to P pages and allocates/hashes P PreparedUnits, then deterministic markdownization iterates every hint.
- Each hint rereads and reparses the entire S-byte PDF at crates/kcs-adapter/src/deterministic.rs:151-156 and 190-249, producing at least O(P*S + P^2) work and potentially blocking ordinary indexing.

## Impact and reach

- Category: CWE-400 algorithmic resource amplification through unbounded lexical page count and repeated parsing
- Impact: **medium**
- Likelihood: **high**

### Impact surface

runtime

### Target reach

One indexing process/scope per crafted PDF, with CPU, memory, I/O, and store-operation availability effects.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- raw max_input_bytes gate
- OCR routing for wholly nontext PDFs
- regular-file/direct-child filtering
- operator recovery by removing the input

### Mitigations

- The default/configured 100 MiB raw input cap bounds S.
- Wholly nontext PDFs route to OCR rather than this deterministic page loop.
- The effect is local availability degradation, not code execution, credential access, or external send.
- The operator can remove the crafted document and retry.

### Counterevidence

- max_input_bytes bounds raw bytes but not derived pages, units, repeated parses, or LCS cells.
- The document must be adversarial/malformed and text-bearing.
- No unsafe stress-size run established host-wide exhaustion; the bounded 64-vs-1 differential proves the growth mechanism.

### Blind spots or proof gap

- The largest practical P and wall-clock/RSS impact across supported PDF inputs were not stress-tested.
- Filesystem cache and parser implementation details affect constants but not the asymptotic repeated work.

## Final decision

The attack needs only a crafted in-scope document and ordinary indexing, and bounded target-runtime evidence verifies the amplification, so no hard suppression applies. Impact is medium because the result is substantial but local and recoverable availability loss. Likelihood is high because the path is deterministic and needs no race or privileged state access. The matrix maps medium impact plus high likelihood to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
