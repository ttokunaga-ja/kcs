# Validation: Deterministic PDF normalization repeatedly reopens an unbound pathname

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-030 |
| Instance key | KCS-R23-CAND-030:deterministic-pdf-path-reopen |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-cli/src/main.rs:9077-9109 |
| Root control | crates/kcs-adapter/src/deterministic.rs:225-247 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | medium |
| Severity | medium |
| Method | V10 exact static trace plus bounded, non-destructive local control observations |

The candidate survives for normalization and search-evidence integrity. The stronger arbitrary-file disclosure or online-upload consequence is not adopted here because this shard did not run a barrier-controlled replacement and those effects have separately scoped candidates.

## Validation rubric

- [x] Establish the lower-trust pathname writer and the exact checked-byte source.
- [x] Locate the nearest raw-hash control and determine where its protection ends.
- [x] Trace every later PDF pathname read to normalized persistence under the earlier identity.
- [x] Check nearby controls and scope the result to the impact proved by static evidence.
- [ ] Reproduce a deterministic, barrier-controlled replacement using two benign temporary PDFs.

## Exact source, control, sink, and boundary

- Source and boundary: run_index_pipeline reads the selected direct child at crates/kcs-cli/src/main.rs:9077-9079 and hashes that buffer at 9090-9103. A contributor able to update that selected scope pathname can replace the file after this read. The store lock does not serialize unrelated filesystem writers.
- Closest control: the scan/current-buffer comparison at crates/kcs-cli/src/main.rs:9080-9102 rejects a change that occurred before that read. It passes only input_path and the earlier raw_hash into prepare_units at 9104-9109; no descriptor, inode identity, or verified byte buffer crosses that boundary.
- Broken edge: prepare_units opens input_path again at crates/kcs-pipeline/src/prepare.rs:72-103. Deterministic markdownization then opens request.raw.path at crates/kcs-adapter/src/deterministic.rs:225-230 and opens it again for each page hint at 244-249. Neither function compares the reopened bytes with request.raw.raw_hash.
- Sink: the response is converted with the earlier raw_hash at crates/kcs-cli/src/main.rs:9364-9383 and persisted at 9388. Thus later PDF bytes can become searchable normalized units named by the earlier content identity.
- Ordered condition: read and hash version A; replace the pathname; prepare and/or deterministic reads consume version B; persistence still uses H(A). Repeated page reads permit mixed B/C page derivation if another replacement lands between hints.

## Evidence and observations

- Immutable evidence was read with git show from revision 0e19f3c6489da458e93a982a333c308d92d0a0ae; HEAD matched that revision before validation.
- The adapter source has two independent fs::read calls, and no raw-hash comparison exists between either read and the persistence sink.
- A bounded /tmp control used only benign paths and a 64 KiB file. No KCS state, external file, credential, network endpoint, or repository file was touched.

## Counterevidence and calibration

- The scan-time/current-buffer hash comparison closes replacements that occur before crates/kcs-cli/src/main.rs:9078.
- Initial scan classification rejects a symlink observed at enumeration time, but it does not bind the later opens.
- Exploitation needs a concurrent pathname writer and favorable scheduling. No deterministic scheduling seam is exposed in the target revision.
- No runtime evidence in this shard proves arbitrary out-of-scope disclosure, stable mixed-page output, or an online send. Those claims therefore do not support High severity here.

## Proof gap and next step

Proof gap: V1/V2 replacement control was not run under the static-only shard constraint. A minimal follow-up would add a test-only barrier after crates/kcs-cli/src/main.rs:9102, replace a benign temporary PDF, and assert that later stages either use the verified buffer or fail before persistence. This gap limits confidence and severity but does not defeat the exact identity mismatch.

## Closure row

| Ledger row id | Instance key | Source reference | Seed anchor | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-030 | KCS-R23-CAND-030:deterministic-pdf-path-reopen | R23 discovery | crates/kcs-cli/src/main.rs:9077-9109 | crates/kcs-adapter/src/deterministic.rs:225-247 | mutable selected-scope PDF pathname | normalized persistence at crates/kcs-cli/src/main.rs:9364-9388 after unbound reopens | reportable | prior hash check exists; no controlled interleaving was run | yes |
