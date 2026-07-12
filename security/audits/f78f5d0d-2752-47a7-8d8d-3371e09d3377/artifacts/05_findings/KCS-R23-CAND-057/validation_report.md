# Validation: Raw-hash working-tree resolution reads every direct child without bounds

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-057 |
| Instance key | KCS-R23-CAND-057:raw-resolver-unbounded-scan |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-cli/src/main.rs:2796-2825 |
| Root control | crates/kcs-cli/src/main.rs:5165-5188 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Confidence score | 0.87 |
| Severity | medium |
| Validation method | V5 bounded resource analysis plus V10 exact static caller trace |

The candidate survives as substantial local CPU, I/O, and memory amplification. A read-oriented open/view/Evidence operation scans the working tree before checking CAS, allocates each regular file wholly, and has no per-file or aggregate byte/work limit.

## Validation rubric

- [x] Source: an approved scope may contain attacker-sized or sparse direct-child regular files.
- [x] Closest control: the resolver skips .kcs and non-regular entries at crates/kcs-cli/src/main.rs:5165-5180.
- [x] Resource sink: each candidate is fully read and SHA-256 hashed at crates/kcs-cli/src/main.rs:5181-5185 without a bound.
- [x] Reachability: open_cas_byte_object invokes the scan before checking immutable CAS at crates/kcs-cli/src/main.rs:4993-5007.
- [x] Quantification: peak retained bytes are O(max n_i), total read/hash work is O(sum n_i) for an absent or late match; only bounded 98,304-byte controls were observed.

## Exact source, control, sink, and boundary

- Source and boundary: untrusted direct-child content in an otherwise approved scope controls the number of regular files m and each file size n_i. A requested raw hash may be absent or match the last enumerated candidate.
- Entrypoints: run_open and run_view accept pointers and short hashes at crates/kcs-cli/src/main.rs:2796-2825. Evidence resolution calls open_raw_object at 4861-4874.
- Reachability: open_raw_object calls open_cas_byte_object; when scan_working_tree is true, the latter always calls find_working_tree_raw before checking the CAS object at crates/kcs-cli/src/main.rs:4977-5007.
- Closest controls: find_working_tree_raw skips .kcs, ignores non-files, and compares a cryptographic hash at crates/kcs-cli/src/main.rs:5165-5185. These constrain candidates and correctness, not bytes or work.
- Sink and bound: fs::read allocates the entire current file at 5181-5183, then hash_bytes traverses it at 5184. There is no max_input_bytes, metadata precheck, streaming reader, file-count limit, aggregate-byte budget, or indexed raw-hash lookup.
- Complexity: peak live input allocation is proportional to the largest visited file, and total I/O/hash time is proportional to the sum of all visited file sizes. Directory order is not security-controlled, so an absent hash gives the deterministic worst-case full scan.

## Evidence and safe observation

- Immutable source proves the loop and call ordering.
- A disposable /tmp control used only 65,536-byte and 32,768-byte synthetic files: total 98,304 bytes and peak 65,536 bytes. No KCS command or large/sparse allocation was attempted.
- The configured adapter max_input_bytes does not govern this read-oriented resolver.

## Counterevidence and severity calibration

- Entries observed as directories, symlinks, or special files are skipped.
- Bytes from one loop iteration are dropped before the next, limiting steady-state input memory to approximately the largest visited file rather than the total corpus.
- The attack requires the user to open/view an absent or late-matching hash in a hostile scope. It causes local availability loss, not network egress or persistent cross-scope corruption.
- If no working file matches, the CAS path may still succeed, but only after the full scan has already occurred.

## Proof gap and next step

Peak allocator/RSS behavior was intentionally not stress-tested. The deterministic V5/V10 proof is sufficient for Medium. A regression should stream SHA-256 through a bounded buffer or consult an indexed raw-hash map, apply per-file and aggregate limits, and verify an existing CAS hit does not first scan unrelated files.

## Closure row

| Ledger row id | Instance key | Source reference | Seed anchor | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-057 | KCS-R23-CAND-057:raw-resolver-unbounded-scan | R23 discovery | crates/kcs-cli/src/main.rs:2796-2825 | crates/kcs-cli/src/main.rs:5165-5188 | attacker-sized direct-child regular files | repeated whole-file read/hash before CAS lookup | reportable | one-file-at-a-time limits peak; no unsafe stress test | yes |
