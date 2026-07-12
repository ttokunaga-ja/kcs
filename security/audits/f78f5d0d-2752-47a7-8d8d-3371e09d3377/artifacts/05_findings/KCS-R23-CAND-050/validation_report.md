# Validation: Oversized task JSONL records allocate before validation

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-050 |
| Instance key | KCS-R23-CAND-050:task-jsonl-unbounded-line-collections-records |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-pipeline/src/task.rs:129-186 |
| Root control | crates/kcs-pipeline/src/task.rs:140-184 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Confidence score | 0.99 |
| Severity | medium |
| Validation method | V1 bounded target-runtime JSONL controls plus V5 resource relation and V10 complete trace |

The candidate survives as a Medium persistent-state availability defect. `TaskStore::all` accepts an unbounded line, deserializes unbounded strings and `changed_unit_keys`/`unit_keys` arrays, performs semantic path/hash checks only afterward, and retains every unique task in a `BTreeMap`. A copied/preseeded task store can therefore consume memory before it reaches the controls intended to reject poisoned tasks, wedging status, index, batch recovery, and other task consumers.

## Validation rubric

- [x] Source: copied, shared, or preseeded `tasks.jsonl` controls total file size, line size, record count, string sizes, and task collection cardinalities.
- [x] Root allocation: `BufRead::lines` builds an unbounded `String`, then `serde_json::from_str` constructs the complete `TaskDescriptor` and vectors at `crates/kcs-pipeline/src/task.rs:140-150`.
- [x] Late controls: scope-local path and CAS-hash checks run only after line and descriptor allocation at `crates/kcs-pipeline/src/task.rs:151-183`.
- [x] Retention/reachability: each unique task is retained in the `BTreeMap` through line 186, and ordinary `status`, index, and batch paths call `TaskStore::all` or `update_matching`.
- [x] Bounded control: one 38,318-byte record with 512 changed and 512 unit keys parsed completely, 64 unique records were retained, and the poisoned-path case returned its path error only after parsing the same large arrays.

## Exact source, control, sink, and boundary

- Source and boundary: `.kcs` task state is trusted for live execution but can originate in a copied, synced, archived, or preseeded store. The threat model explicitly treats it as untrusted at adoption. A contributor can supply one huge newline-terminated JSON object, many unique records, or large strings/arrays while keeping the final descriptor syntactically valid.
- Line allocation: `BufReader::lines` repeatedly extends a `String` until newline/EOF and provides no `take`, `read_until` byte ceiling, total-file budget, or record-count bound.
- Descriptor allocation: `serde_json::from_str` allocates all `String` fields plus `Vec<String>` for `changed_unit_keys` and optional `unit_keys` before returning a typed descriptor. The struct carries no custom bounded visitor and the reader performs no pre-deserialization cardinality check.
- Late semantic checks: direct-child `input_path`, `input_hash`, and `previous_raw_hash` validation protects later filesystem/hash consumers, but it executes only after the expensive line and descriptor exist. A record destined for rejection can therefore consume the same resources first.
- Retention sink: the reader clones the task id and stores the descriptor in a `BTreeMap`; all unique ids remain resident until conversion to the result vector. Duplicate ids replace values but do not bound unique cardinality or cumulative bytes.
- Entrypoints: `kcs status` calls `all` at `crates/kcs-cli/src/main.rs:435-450`; batch resume/retry calls `update_matching`, which first calls `all`, at `crates/kcs-pipeline/src/task.rs:254-266`; index and task helpers call the same reader repeatedly. A persistent oversized file therefore denies routine reads and recovery.

## Evidence and bounded control

- The pinned target-runtime control used isolated `/tmp` task stores and no network. A single task line of 38,318 bytes containing 512 `changed_unit_keys` and 512 `unit_keys` was accepted and returned with both full arrays.
- A separate bounded store retained 64 unique task descriptors in one `all` result.
- A third record used `../escape.pdf` with the same 512+512 arrays; `all` returned `KCS-E-STORE-PATH-001`, confirming the semantic guard is correct but temporally after deserialization. See `validation_artifacts/control_output.json`.

## Counterevidence and severity calibration

- Fresh stores are owner-only. Mere arbitrary same-user modification of an already private live store is not the security boundary; copied/preseeded/shared-store adoption is.
- Filesystem capacity is an ultimate bound, and malformed JSON returns a corruption error. Neither prevents allocation proportional to a well-formed line or collection before rejection/retention.
- Duplicate task ids collapse in the map, but an attacker controls unique ids. Normal KCS writers produce ordinary-sized records; they do not enforce a reader-side invariant on imported state.
- The impact is local memory/CPU exhaustion across task-reading commands and recovery, with no direct confidentiality or code-execution effect. This supports Medium.

## Proof gap and next step

No OOM-sized record was created. Deterministic reader semantics, target-runtime bounded controls, and widespread call sites close Medium. Enforce a total task-file budget, a per-line byte cap before `String` growth, a maximum record count, and bounded string/array cardinalities during deserialization; reject over-limit state with an actionable corruption/recovery error.

## Closure row

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-050 | KCS-R23-CAND-050:task-jsonl-unbounded-line-collections-records | R23 deep discovery; no external advisory | crates/kcs-pipeline/src/task.rs:129-186 | crates/kcs-pipeline/src/task.rs:140-184 | adopted/preseeded `tasks.jsonl` line, arrays, and records | unbounded line/serde allocation then BTreeMap retention | reportable | owner-only live store narrows source; 38,318-byte/64-record bounded controls, no OOM test | yes |
