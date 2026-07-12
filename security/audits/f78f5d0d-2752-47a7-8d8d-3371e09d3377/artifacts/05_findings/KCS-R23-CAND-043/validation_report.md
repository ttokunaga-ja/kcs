# Validation: CAS write accepts a pre-existing corrupt destination as success

- Candidate: `KCS-R23-CAND-043`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.99)**
- Method: **V6 adopted-state provenance + V10 exact write/read/publication trace**

All raw/tree/commit writes reach `atomic_write`. If the computed destination pathname already exists, it returns success without checking type, bytes, or digest at `crates/kcs-core/src/cas.rs:155-163`. Read paths do verify the digest after reading at `cas.rs:78-100`, but that later control does not repair the slot.

A copied/preseeded store can therefore contain wrong bytes (or a wrong-type filesystem entry) at the exact fanout path for content the operator later snapshots. `write_raw` reports success, the working tree retains the expected hash, and snapshot publishes tree/commit/refs at `crates/kcs-core/src/scope.rs:413-520`. Later inspection/read fails as corrupt, while future legitimate writes continue treating the occupied slot as success.

Private live-store arbitrary tampering alone is out of scope, but adopted/shared state is an explicit lower-trust boundary. Impact is recoverable archive availability/integrity rather than external overwrite, supporting Medium. Verify an existing regular file's digest/type before success, and reject/quarantine mismatches atomically.

