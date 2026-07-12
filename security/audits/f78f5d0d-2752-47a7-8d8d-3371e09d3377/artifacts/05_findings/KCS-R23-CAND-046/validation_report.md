# Validation: CAS reads allocate attacker-sized objects before verification

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-046 |
| Instance key | KCS-R23-CAND-046:cas-whole-object-read-before-verification |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-core/src/cas.rs:78-100 |
| Root control | crates/kcs-core/src/cas.rs:78-100 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Confidence score | 0.98 |
| Severity | medium |
| Validation method | V1 bounded target-runtime CAS/inspect control plus V5 resource relation and V10 complete trace |

The candidate survives as a Medium local availability defect at the copied/preseeded store boundary. Hash syntax and digest equality protect integrity, but a valid hash-consistent object is wholly allocated before its digest, type, JSON shape, or command-specific need is checked. Even metadata-only `inspect` loads the complete raw object merely to return its byte length.

## Validation rubric

- [x] Source: a copied, shared, or preseeded store can contain a large hash-consistent raw/tree/commit object named by its supplied hash or a poisoned ref.
- [x] Closest control: `read_by_hash` validates hash syntax before lookup, but calls `fs::read` before digest comparison and has no metadata/per-kind size ceiling at `crates/kcs-core/src/cas.rs:78-100`.
- [x] Metadata sink: `Repository::inspect` receives the complete `StoredObject.bytes` and uses only `bytes.len()` for a raw object at `crates/kcs-core/src/scope.rs:623-637`.
- [x] Additional reachability: commit/tree readers use the same whole-object primitive before deserialization, including HEAD/tree resolution at `crates/kcs-core/src/scope.rs:742-755,848-865`.
- [x] Bounded control: a 65,536-byte hash-consistent raw object was returned as a 65,536-byte `Vec` and metadata-only inspect reported 65,536; malformed hash syntax was rejected before lookup.

## Exact source, control, sink, and boundary

- Source and boundary: the threat model treats copied/preseeded `.kcs` state as untrusted when adopted. Such a store can carry a hash-consistent object of attacker-selected size and communicate its valid SHA-256 or bind it through a supplied commit/tree/ref. Normal snapshots can also create large raw objects because snapshot ingestion has no CAS object ceiling, but imported-state reachability is sufficient here.
- Integrity control: `read_by_hash` rejects malformed hash strings, derives a fixed fanout path, and verifies SHA-256 after reading. These controls prevent name/content substitution; they do not prevent allocation or I/O proportional to a valid object.
- Root sink: for the first existing kind path, `fs::read` allocates the complete file, then `hash_bytes` traverses the complete buffer. Only after both operations does the function return a typed `StoredObject`.
- Metadata-only path: CLI `inspect` at `crates/kcs-cli/src/main.rs:513-530` calls `Repository::inspect`; raw inspection consumes the full object and returns only `raw_hash` and `size_bytes`.
- DAG paths: `read_commit` and `read_tree` also materialize the complete object before kind and JSON validation. A poisoned HEAD/ref can therefore trigger the same primitive during repository validation, log, diff, status, or snapshot paths.
- Resource relation: one read has O(N) allocation, I/O, and hashing for object size N. A large tree/commit then adds full JSON materialization; no object, tree-entry, or commit-parent cardinality cap intervenes before the initial allocation.

## Evidence and bounded control

- The target-runtime control initialized an isolated `/tmp` scope, wrote one 65,536-byte raw CAS object through the real `ObjectStore`, read it by its valid hash, and invoked the real metadata-only `Repository::inspect`.
- `validation_artifacts/control_output.json` records `stored_object_vec_bytes = 65536`, `inspect_reported_size_bytes = 65536`, and successful digest consistency. The malformed short-hash control was rejected.
- No network, credential, imported real store, large/sparse file, or repository mutation was used.

## Counterevidence and severity calibration

- New `.kcs` directories are owner-only, and direct arbitrary writes to an already private live store are outside the threat model. The relevant source is a copied/preseeded/shared store at adoption, a supplied ref, or a normally archived large object.
- An attacker must provide a hash-consistent object; arbitrary garbage under a false hash is detected, but only after it has already been allocated and hashed.
- `inspect` is explicit and requires the object hash. HEAD/ref consumers broaden reachability, but this remains local linear resource exhaustion rather than remote unauthenticated denial of service.
- CAND-032 covers unbounded scan/snapshot ingestion. C046 is the independent read-side primitive and requires streaming/capped verification even after write-side limits are added.

## Proof gap and next step

Peak RSS was intentionally not stress-tested. The target type and `fs::read` semantics close the O(N) allocation proof for Medium. Apply per-kind metadata/cardinality limits before allocation, stream digest verification through a bounded buffer, and let raw metadata inspection verify without retaining the complete object.

## Closure row

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-046 | KCS-R23-CAND-046:cas-whole-object-read-before-verification | R23 deep discovery; no external advisory | crates/kcs-core/src/cas.rs:78-100 | crates/kcs-core/src/cas.rs:78-100 | large valid CAS object in adopted store or supplied ref/hash | `fs::read` and digest before inspect/type/JSON checks | reportable | requires hash-consistent stored object; 64 KiB bounded target control, no stress test | yes |
