# Validation: Deterministic normalization persists a later path read under the earlier raw hash

- Candidate: `KCS-R23-CAND-029`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-cli/src/main.rs:9072-9118,9282-9304`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.92)**
- Method: **V10 exact verified-read-to-normalized-persistence trace**

## Rubric

- [x] Normal deterministic indexing reads and hashes a candidate before normalization.
- [x] The caller retains the verified buffer for raw/prepared persistence but gives the adapter only a path and old hash.
- [x] Preparation and the deterministic adapter independently reopen that mutable path.
- [x] The adapter does not compare reopened bytes with `request.raw.raw_hash`.
- [x] Output derived from the later bytes is persisted under the earlier raw hash and prepared identity.

## Evidence

For each accepted candidate, `run_index_pipeline` classifies secrets from the filename, reads the path, computes `current_hash`, and rejects a mismatch with the scan hash at `crates/kcs-cli/src/main.rs:9072-9103`. It then sets `raw_hash=current_hash` and calls `prepare_units` with the asserted hash plus a pathname at `crates/kcs-cli/src/main.rs:9103-9110`. The verified `bytes` buffer is retained separately for prepared/raw object writes at `crates/kcs-cli/src/main.rs:9112-9118`.

Preparation does not consume that buffer or verify its own read against `request.raw_hash`. It independently calls `std::fs::read(&request.input_path)` and derives `prepared_hash` from those bytes at `crates/kcs-pipeline/src/prepare.rs:72-103`. Later, the CLI constructs `MarkdownizeRequest.raw` with the earlier `raw_hash` and the same mutable path at `crates/kcs-cli/src/main.rs:9282-9304`.

The deterministic adapter separates identity from content in the same way. `markdownize` accepts the caller's hints/hash but obtains `source_text` through `read_source_text` at `crates/kcs-adapter/src/deterministic.rs:113-118`. That helper performs another `std::fs::read(path)` and converts those bytes to normalized text at `crates/kcs-adapter/src/deterministic.rs:225-241`; PDF handling can reopen again per page at `crates/kcs-adapter/src/deterministic.rs:244-249`. No comparison with `request.raw.raw_hash` follows.

The response's unit structure is validated, but its source bytes are not rebound. The CLI passes the old `raw_hash` into `normalized_units_from_response` and `manifest_from_units`, then persists the resulting units/manifest at `crates/kcs-cli/src/main.rs:9364-9388`. A concrete interleaving is therefore:

1. benign text A passes scan and the caller's `H(A)` check;
2. preparation completes with the expected hints;
3. a lower-trust writer atomically replaces the path with text B before `markdown_adapter.markdownize`;
4. the adapter reads and normalizes B;
5. KCS persists B-derived searchable content under raw identity `H(A)`.

This is durable false provenance in the product's content-addressed search/evidence model. If online embeddings are later enabled, B-derived chunks can also be sent under the benign stored path classification, but network egress is not required for this candidate to survive.

## Counterevidence and preconditions

- A change before the caller's hash comparison is detected and skipped at `crates/kcs-cli/src/main.rs:9090-9102`; the attacker must replace the path afterward.
- The attacker needs concurrent write/rename authority in the selected root, victim read access to replacement content, and operator indexing.
- A stable, non-mutating file produces consistent raw, prepared, and normalized identity. Losing races may normalize the benign bytes or fail an I/O operation.
- The issue does not overwrite the user's working file outside the attacker's existing directory authority. Its primary impact is archive/search/evidence integrity, with optional later embedding disclosure.
- Re-indexing a stable file may be a recovery path, though first-instance and cached normalized state can make the false result durable until the affected derived state is rebuilt.

Central severity is Medium. The exact dataflow can create false provenance, but the required replacement remains an unreproduced timing race and does not itself send data or modify an outside file. The canonical calibration does not permit High from the theoretical race window alone.

## Tests and remaining uncertainty

No scheduler-controlled replacement harness was run. The permitted V10 trace is complete: the verified buffer never reaches the deterministic adapter, the adapter's fresh read is the normalized-text source, and persistence uses the earlier hash. Ten preserved local validation receipts independently confirm the same path.

Proof gap: live race reliability was not measured. A regression should hold the pipeline after the hash check, replace the path, and assert either stable-buffer normalization or a final hash mismatch before any normalized unit is persisted.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-029 | `crates/kcs-cli/src/main.rs:9072-9118,9282-9304` | post-hash replacement of a deterministic text/code input | path read at `deterministic.rs:225-241`; persistence at `main.rs:9364-9388` | reportable | earlier mismatch guard works; live race not reproduced | yes |

Validation artifacts: none (V10 trace only).
