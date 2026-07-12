# Validation: Scan-time replacement can authorize an outside-scope file under a benign name

- Candidate: `KCS-R23-CAND-027`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-pipeline/src/scan.rs:97-149`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.91)**
- Method: **V10 exact multi-stage interleaving and source/control/sink trace**

## Rubric

- [x] Normal non-preview index asks the scanner to hash direct-child candidates.
- [x] File type and benign-name secret/media classification occur before a later path-based hash read.
- [x] A replacement symlink can make the accepted scan hash belong to a user-readable outside file.
- [x] The later index hash comparison accepts that same outside file while retaining benign filename decisions.
- [x] Preparation, normalization, and online OCR reopen the path without binding the consumed bytes to a stable descriptor.

## Evidence

`run_index` builds the preview from the selected canonical root and requests raw hashes for a real indexing pass at `crates/kcs-cli/src/main.rs:558-580`. The scanner enumerates a direct child, checks `DirEntry::file_type().is_file()` at `crates/kcs-pipeline/src/scan.rs:97-113`, derives a relative name, then uses that name for secret classification and media policy at `crates/kcs-pipeline/src/scan.rs:114-147`. Only afterward does it reopen the pathname with `std::fs::read(&path)` to compute `raw_hash` at `crates/kcs-pipeline/src/scan.rs:147-149`.

If a lower-trust directory writer replaces the checked regular file with a symlink in that interval and leaves it pointing to the same outside target, the preview's `raw_hash` and metadata describe the target while `input_path`, secret tier, and media type retain the benign direct-child name. The stable-symlink control does not help because it observed the earlier regular inode.

The later change detector is real but incomplete for this interleaving. `run_index_pipeline` computes `secrets_hold` from `candidate.input_path`, rereads `repo.root().join(input_path)`, hashes that buffer, and accepts it when it equals the scan hash at `crates/kcs-cli/src/main.rs:9072-9103`. A symlink left on the same outside file satisfies that equality. The code then passes only the mutable pathname and asserted hash to `prepare_units` at `crates/kcs-cli/src/main.rs:9104-9118`; preparation independently reads the path at `crates/kcs-pipeline/src/prepare.rs:72-103`.

The path remains unbound downstream. The deterministic adapter reopens `request.raw.path` for source text at `crates/kcs-adapter/src/deterministic.rs:113-155,225-247`. For OCR-eligible content, the deferred executor hash-checks one read at `crates/kcs-cli/src/main.rs:6533-6605`, calls preparation through another pathname open at `crates/kcs-cli/src/main.rs:6615-6624`, and then passes the path and earlier task hash to the online wrapper at `crates/kcs-cli/src/main.rs:6674-6691`. The Mistral client performs its own final `std::fs::read(path)`, base64-encodes the bytes into the request, and sends them at `crates/kcs-adapter/src/mistral_ocr.rs:112-138`.

Thus the initial scan race can bless an outside-scope document under a harmless filename and content hash; no additional swap is required if the link remains stable. Secret holds continue to use the harmless name at `crates/kcs-cli/src/main.rs:9072-9077`, and derived embedding holds likewise classify stored `raw_path` rather than the physical target at `crates/kcs-cli/src/main.rs:7317-7329`.

## Counterevidence and preconditions

- The attacker needs concurrent rename authority in the selected root and must win the initial window between `file_type` and the scanner's metadata/read operations.
- A symlink already present at the type check is skipped. A later byte change that produces a different hash is rejected by `crates/kcs-cli/src/main.rs:9090-9102`.
- The outside target must be readable by the victim process and fit the effective size/media path. OCR egress additionally requires an OCR-eligible document, configured adapter, network opt-in, budget availability, and task execution.
- KCS has no listener; the operator must index the supplied/shared scope. The provider is the configured external service, not automatically the local path attacker.
- The final Mistral reopen also permits a separate post-check race tracked by candidate 028. This candidate survives on the earlier scan-time authorization mismatch even if no later swap occurs.

Central severity is Medium. The source trace shows potentially serious outside-scope upload, but the path is an unreproduced timing race whose reliability was not measured. The canonical calibration explicitly bars High for a merely theoretical race window; operator indexing, an eligible target, generic online approval, and a successful local swap are all required.

## Tests and remaining uncertainty

No live timing race or network capture was run. The task permits V10 validation; the source trace closes the interleaving and shows why the later hash equality is not counterevidence when the scan hash was already computed from the substituted target. Four preserved worker validations independently trace the same pinned path.

Proof gap: race reliability and a full loopback send were not measured. A regression should atomically replace a regular direct child during scan and assert that no outside bytes can become the candidate hash, normalized content, raw object, task identity, or adapter body.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-027 | `crates/kcs-pipeline/src/scan.rs:97-149` | direct-child replacement during non-preview `index` | accepted hash/name at `main.rs:9072-9118`; OCR read/send at `mistral_ocr.rs:112-138` | reportable | hash mismatch blocks changed bytes, but not a scan hash already taken from the substituted target; race/send not reproduced | yes |

Validation artifacts: none (V10 trace only).
