# Validation: Mistral OCR reopens the path after the final hash check and sends unbound bytes

- Candidate: `KCS-R23-CAND-028`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-cli/src/main.rs:6576-6691`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.94)**
- Method: **V10 exact last-check-to-network-sink trace**

## Rubric

- [x] A normal approved online-task path reaches the real Mistral OCR client.
- [x] The executor hashes and size-checks one path read against the authorized task identity.
- [x] The checked byte buffer is discarded while only the mutable path and old hash are forwarded.
- [x] The OCR client performs a fresh path read and places those bytes directly in the request body.
- [x] No final hash, no-follow descriptor, inode, size, or secret check binds the uploaded bytes to the approved bytes.

## Evidence

Task selection performs its secret decision from the persisted lexical `task.input_path` at `crates/kcs-cli/src/main.rs:6050-6066`. Before cost/send, `classify_online_markdownize_precondition` reads the path, compares its hash with `task.input_hash`, enforces the live size cap, and calls preparation at `crates/kcs-cli/src/main.rs:6533-6573`. The executor repeats the content check: it reads `current_bytes`, rejects a hash mismatch, and applies media controls at `crates/kcs-cli/src/main.rs:6576-6614`.

That correct check ends before the consuming operation. The executor drops `current_bytes`, calls `prepare_units` with only `input_path` and the asserted old hash at `crates/kcs-cli/src/main.rs:6615-6624`, then later calls `run_standard_online_markdownize` with `raw_hash=&task.input_hash` and `path=&path` at `crates/kcs-cli/src/main.rs:6674-6691`. The catalog preserves those as independent fields in `RawInput` and passes them to the production Mistral adapter at `crates/kcs-adapter/src/catalog.rs:82-101,134-147`; it does not carry the checked buffer or verify that the path still names the same object.

The network sink obtains its own bytes. `EnvMistralOcrClient::ocr_markdown` reads `request.raw.path` at `crates/kcs-adapter/src/mistral_ocr.rs:112-120`, then passes that fresh buffer to `ocr_request_body` and posts it with the configured bearer credential at `crates/kcs-adapter/src/mistral_ocr.rs:121-138`. `request.raw.raw_hash` is not consulted by this client. Therefore a lower-trust directory writer can keep the legitimate file in place through the executor's final hash/size check, atomically replace the name before line 117, and make the substituted bytes the exact network body.

No earlier scan race is required for this instance. The benign file and its valid task can pass every preview, secret, size, media, network-opt-in, and raw-hash control before the final replacement. Returned units are then labeled and persisted with the earlier `task.input_hash` at `crates/kcs-cli/src/main.rs:6674-6722,6770-6792`, adding provenance corruption to the unapproved upload.

## Counterevidence and preconditions

- The attacker needs concurrent rename authority in the selected root and must win the interval after the executor check but before the adapter read.
- The task must already be eligible: an OCR-supported media path, configured Mistral adapter, network opt-in, budget availability, and operator-driven `index --online`/resume/retry execution are required.
- A replacement before the executor hash check is rejected at `crates/kcs-cli/src/main.rs:6596-6605`. The defect is specifically the later fresh read.
- The destination is the operator-configured OCR provider, not automatically an attacker-controlled host. The confidentiality failure is that bytes outside the approved identity/secret decision cross that external boundary.
- An I/O failure or losing race prevents the send. Race reliability is platform/filesystem dependent.

Central severity is Medium. The complete trace identifies a potentially serious last-check-to-send swap, but no barrier-controlled replacement or request capture established practical race reliability. High is therefore not assigned under the canonical rule that a theoretical race window alone is insufficient.

## Tests and remaining uncertainty

No live path-swap harness or network request was run, as required by the no-network constraint. The V10 dataflow proves that the request buffer comes exclusively from the final unchecked `std::fs::read`; seventeen preserved local validations independently reached the same pinned source-to-sink result.

Proof gap: race reliability and a loopback body capture were not measured. A minimal regression should pause after `task.input_hash` verification, replace the path, and assert the client refuses to construct any request whose final bytes do not hash to that identity.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-028 | `crates/kcs-cli/src/main.rs:6576-6691` | post-check replacement of an eligible online-task path | fresh read and POST at `crates/kcs-adapter/src/mistral_ocr.rs:112-138` | reportable | outer approval/media/budget gates remain; race/send not reproduced | yes |

Validation artifacts: none (V10 trace only).
