# Validation: Prepare-stage reopen can poison prepared CAS identity

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-031 |
| Instance key | KCS-R23-CAND-031:prepare-cas-identity |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-cli/src/main.rs:9077-9118 |
| Root control | crates/kcs-pipeline/src/prepare.rs:72-103 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | medium |
| Severity | medium |
| Method | V10 exact static trace plus bounded, non-destructive local control observations |

The candidate survives as a prepared-object integrity defect. High severity is not supported without a controlled pathname replacement and a demonstrated downstream reliance that materially crosses the selected-scope boundary.

## Validation rubric

- [x] Establish the checked byte buffer and concurrent pathname source.
- [x] Verify whether prepare_units binds its reopened bytes to request.raw_hash.
- [x] Compare the bytes used to derive prepared hashes with the bytes written under those names.
- [x] Inspect atomic-write and existing-object controls for content verification.
- [ ] Reproduce the mismatch with a barrier-controlled benign replacement in an isolated scope.

## Exact source, control, sink, and boundary

- Source and boundary: crates/kcs-cli/src/main.rs:9077-9103 reads and hashes version A of a selected-scope file. A concurrent scope writer can replace that pathname before prepare.
- Closest control: crates/kcs-cli/src/main.rs:9090-9102 compares only the first buffer with the scan hash. The call at 9104-9109 passes raw_hash plus a pathname, not the verified bytes.
- Broken edge: prepare_units reads the pathname at crates/kcs-pipeline/src/prepare.rs:90 and computes prepared_hash and per-page prepared hashes from those reopened bytes at 100-159. PrepareStageRequest.raw_hash is declared at 41-46 but is not consumed anywhere in prepare.rs, so there is no rebind.
- Sink: write_prepared_objects receives the earlier caller buffer at crates/kcs-cli/src/main.rs:9112-9117 while receiving the reopened-input hashes from prepare. It derives destination paths from those hashes at 9505-9522 but selects object bytes from the earlier buffer or its earlier-buffer PDF pages at 9512 and 9528-9537, then publishes at 9540.
- Result: if prepare read version B while the retained bytes are version A, the object named H(B) contains bytes from A. Later prepared-object consumers can observe a persistent CAS identity mismatch.

## Evidence and observations

- Immutable revision inspection confirmed the raw_hash field has no use in crates/kcs-pipeline/src/prepare.rs beyond its struct declaration.
- crates/kcs-cli/src/main.rs:9527 skips a pre-existing destination, while atomic_write_cas_object only provides crash-atomic publication; neither branch verifies that bytes hash to prepared_hash.
- Validation used only git source reads and a bounded /tmp control file. It did not write any target-store object or repository file.

## Counterevidence and calibration

- The pre-prepare scan-hash comparison defeats changes that occur before the first read.
- Prepared-object writes use a temporary file, fsync, and rename, which protects publication atomicity but not content/name agreement.
- A successful mismatch needs a replacement between the first read and prepare; no deterministic barrier exists in the revision.
- The proved consequence is prepared CAS/index integrity and recoverable processing failure, not an independently demonstrated confidentiality or code-execution boundary.

## Proof gap and next step

Proof gap: no controlled runtime interleaving was run. A focused regression can pause immediately before prepare_units, replace one benign temporary text/PDF file, and assert either rejection or hash(bytes-at-destination) equals the prepared object name. The static mismatch is complete enough for Medium reportability.

## Closure row

| Ledger row id | Instance key | Source reference | Seed anchor | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-031 | KCS-R23-CAND-031:prepare-cas-identity | R23 discovery | crates/kcs-cli/src/main.rs:9077-9118 | crates/kcs-pipeline/src/prepare.rs:72-103 | mutable selected-scope file after initial hash | write_prepared_objects at crates/kcs-cli/src/main.rs:9505-9541 | reportable | atomic publication exists; no barrier-controlled replacement was run | yes |
