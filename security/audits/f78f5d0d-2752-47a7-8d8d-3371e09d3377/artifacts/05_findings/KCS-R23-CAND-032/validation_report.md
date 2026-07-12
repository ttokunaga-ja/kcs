# Validation: scan hashing allocates the full file before the input-size gate

- Candidate: `KCS-R23-CAND-032`
- Instance key / ledger row: `KCS-R23-CAND-032`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.99)**
- Method: **bounded existing cap test + V5 exact allocation/order proof + V10 exact trace**
- Root control: `crates/kcs-pipeline/src/scan.rs:122-149`

## Rubric

- [x] An included direct-child regular file reaches raw-hash computation on the normal index path.
- [x] The known metadata length and configured input cap were ordered relative to whole-file allocation.
- [x] Heap, I/O, and hashing growth were derived from the actual caller and sink.
- [x] Preview mode, ignored files, type filters, and the late adapter gate were assessed as counterevidence.
- [x] Existing tests were checked for both cap behavior and missing large/sparse-file coverage.

## Exact trace and evidence

`kcs index` acquires the scope store lock and constructs a scan preview at `crates/kcs-cli/src/main.rs:558-580`. Normal indexing passes `include_raw_hashes=true`; only `--preview` passes false and returns before the pipeline at lines 575-584.

The scanner enumerates direct children and keeps regular, non-ignored candidates at `crates/kcs-pipeline/src/scan.rs:90-146`. It obtains the exact logical file length from metadata at line 122. Despite already knowing that length, the raw-hash branch calls `std::fs::read(&path)` and hashes the returned complete `Vec<u8>` at lines 147-149, with no preceding length or streaming control.

Only after `build_scan_preview` returns does `run_index_pipeline` load the configured/default 100 MiB adapter cap and compare `candidate.size_bytes` at `crates/kcs-cli/src/main.rs:9047-9070`. Thus even a cap of one byte cannot prevent the earlier scanner allocation. Accepted files are read again later at lines 9077-9090, but that second read is after the cap and is not needed to establish this candidate. Snapshot/status whole-file reads are separately tracked by `KCS-R23-CAND-019`.

For an included file of logical size `n`, the vulnerable operation has peak heap growth `O(n)` for the owned byte vector and `O(n)` read/hash work. A sparse file makes a large logical `n` inexpensive to place in a supplied scope while `fs::read` still materializes its logical contents. The metadata length at line 122 provides an available pre-allocation decision point, and a streaming hash would keep heap usage bounded even when raw archival policy permits large inputs.

The bounded, network-free existing test `r12_2_max_input_bytes_gates_oversized_input` passed (`crates/kcs-cli/tests/step3_p0_contract.rs:4212-4231`). It demonstrates that a small file over a 50-byte cap is skipped for adapter normalization, but does not assert that hashing was bounded before that gate. Repository tests contain no large/sparse input or scanner allocation regression; the scanner's own tests at `crates/kcs-pipeline/src/scan.rs:453-596` cover serialization, ignore semantics, and filesystem case probing rather than `build_scan_preview` resource bounds.

## Counterevidence and impact

Directories, symlinks/non-regular files, XDG state, `.kcs`, `.kcsignore`, ignored files, and default-excluded Tier-A secrets do not enter the hash read. `--preview` disables raw hashes. The operator can remove the file and retry, and the defect does not cross confidentiality or authorization boundaries. The later cap does correctly prevent adapter normalization and network submission of oversized input.

These controls reduce scope but do not bound ordinary non-preview indexing of an included regular file. One supplied oversized or sparse direct child can consume memory and I/O before useful index work and while the command holds the store lock. This is a recoverable scope-local availability/robustness defect, so the final severity is Medium.

## Remaining uncertainty and next step

No high-memory or exhaustion experiment was performed. The exact `metadata.len() -> fs::read -> late cap` order and standard whole-file-read semantics provide a complete proof; a bounded measurement would refine constants only. Remediation should either reject above a per-file/aggregate scan budget before allocation or stream hashing/CAS ingestion with bounded memory. Add a sparse-file regression that verifies normal index reaches no whole-file allocation before the configured decision.

Validation artifacts: none.
