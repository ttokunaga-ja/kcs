# Validation: Deterministic PDF handling reparses the whole file once per page

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-034 |
| Instance key | KCS-R23-CAND-034:lexical-page-count-reparse-amplification |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-adapter/src/deterministic.rs:415-437 |
| Root control | crates/kcs-pipeline/src/prepare.rs:315-347 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Confidence score | 0.99 |
| Severity | medium |
| Validation method | V1 bounded target-runtime attack/control plus V5 resource relation and V10 complete trace |

The candidate survives as a Medium algorithmic availability defect. Raw `/Page` prefixes, including `/PageX`, determine an unbounded logical page count. Preparation pads to that count and creates one unit per page; deterministic markdownization then rereads and reconstructs the full page vector once for every hint. A small accepted PDF therefore turns lexical marker count into superlinear CPU, allocation, and filesystem work during ordinary indexing.

## Validation rubric

- [x] Source: `pdf_page_count_in_text` counts `/Page` prefix matches without PDF page-tree validation or a delimiter/count ceiling at `crates/kcs-adapter/src/deterministic.rs:419-437`.
- [x] Expansion control: `pdf_text_pages` pads extracted strings to the lexical count and `prepare_units` allocates/hashes one `PreparedUnit` per padded page at `crates/kcs-pipeline/src/prepare.rs:102-170,315-347`.
- [x] Primary sink: full markdownization maps every hint, and each PDF hint calls `fs::read` plus `extract_pdf_text_pages` at `crates/kcs-adapter/src/deterministic.rs:151-156,190-202,244-249`.
- [x] Reachability: ordinary indexing applies only the byte-size gate, prepares every admitted PDF, and sends every prepared hint to the deterministic adapter at `crates/kcs-cli/src/main.rs:9047-9118,9229-9304`.
- [x] Bounded control: a 490-byte PDF with 63 false markers produced 64 prepared and markdown units versus one unit for the 49-byte honest control; the same-size mapping exercised 4,225 versus 4 LCS cells.

## Exact source, control, sink, and boundary

- Source and boundary: an untrusted direct-child PDF controls raw bytes and lexical `/Page`-prefixed tokens. One printable literal/text layer keeps the document on the local deterministic path instead of the wholly-scanned OCR branch.
- Page-count gap: `pdf_page_count_in_text` takes the maximum of `/Type` windows containing `/Page` and every `/Page` match not beginning `/Pages`. It does not require a token boundary or a structurally reachable PDF page object; the repository regression at `deterministic.rs:500-515` explicitly records `/PageX` as a page.
- Unit expansion: `pdf_text_pages` extracts the one real string and pads empty strings until `page_count`; `prepare_units` then constructs a key, hashes, fingerprint, metadata, and vector entry for each page.
- Reparse sink: `read_source_text` reads and extracts the document once. Full markdownization iterates all hints; each call to `read_pdf_page_text` reopens the same path, reads the whole file, reconstructs and pads the entire page vector, and selects one page. For P derived pages and S input bytes this is at least P whole-file rereads plus repeated O(P) vector construction, approaching O(P*S + P^2).
- Revision sink: if a previous version exists, `map_units` additionally allocates `(m+1)*(n+1)` `usize` cells at `prepare.rs:387-416`. This supports impact but is not required for the initial-index reparse finding; the general LCS root is tracked separately by CAND-007.
- Entrypoint: `run_index_pipeline` checks `max_input_bytes` before preparation, but that byte ceiling does not constrain logical page count or work per byte. It passes all prepared hints into the offline adapter while holding the index/store operation.

## Evidence and bounded control

- `validation_artifacts/control_output.json` was produced by the pinned target crates with no network. The attack used 490 bytes, one real text page token, and 63 false `/PageX` markers: lexical count 64, 64 prepared units, 64 markdown units, and 4,225 same-size LCS cells.
- The honest 49-byte control had one structural page, one prepared/markdown unit, and four LCS cells.
- Source ordering proves the adapter performs one initial full extraction plus one full extraction per derived hint (65 in the bounded attack, two in the control). No stress-size input or external store was used.

## Counterevidence and severity calibration

- The default 100 MB `max_input_bytes` gate bounds raw bytes admitted to this stage, and wholly nontext PDFs route to OCR. Neither control bounds lexical page count, units, repeated parsing, or LCS cells for a PDF with one readable text literal.
- A legitimate PDF provider is expected to emit structural page objects; the attack relies on a malformed or adversarial document entering a scope the operator indexes.
- The effect is local CPU/memory/I/O exhaustion and index unavailability, not code execution, network use, credential access, or persistent cross-scope corruption. This supports Medium.
- CAND-007 covers the generic LCS allocation. C034 independently survives because first-time indexing already performs one complete PDF read/extraction per attacker-inflated hint.

## Proof gap and next step

No unsafe stress test was run. The exact target-runtime relation and V5/V10 trace close Medium. Remediation must structurally validate and cap page/unit count, parse each PDF once into a bounded representation, and reuse those pages for all units; LCS must retain its independent work/cell bound.

## Closure row

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-034 | KCS-R23-CAND-034:lexical-page-count-reparse-amplification | R23 deep discovery; no external advisory | crates/kcs-adapter/src/deterministic.rs:415-437 | crates/kcs-pipeline/src/prepare.rs:315-347 | untrusted indexed PDF with one text layer and false `/Page` prefixes | unit padding plus per-hint whole-file read/extraction at deterministic.rs:151-156,190-249 | reportable | byte cap and OCR routing do not bound pages/work; bounded 64-vs-1 target control | yes |
