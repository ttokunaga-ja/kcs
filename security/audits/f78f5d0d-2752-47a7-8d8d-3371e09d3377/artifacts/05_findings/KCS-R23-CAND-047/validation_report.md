# Validation: Persisted task output_ref can escape the scope

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-047 |
| Instance key | KCS-R23-CAND-047:task-output-ref-cross-scope |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-pipeline/src/task.rs:129-184 |
| Root control | crates/kcs-cli/src/main.rs:9685-9713 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Severity | high |
| Method | V6 poisoned-state provenance, V10 complete static trace, and safe absolute-path control observation |

The candidate survives at High for the supplied/shared-store boundary. A schema-valid task can select another readable scope's normalized-instance directory; KCS reads it and, on the online incremental reuse path, can copy its unit text into the current scope under a current identity. Validation did not contact an adapter or read any external document.

## Validation rubric

- [x] Establish the lower-trust persisted task source and the supported supplied-store boundary.
- [x] Inspect the single TaskStore read choke point for output_ref validation.
- [x] Trace output_ref to exact manifest/unit reads without containment.
- [x] Trace a loaded external unit to a current-scope persistence sink and address profile controls.
- [x] Confirm absolute-path selection safely without reading any referenced file.

## Exact source, control, sink, and boundary

- Source and boundary: a tampered, copied, or shared scope store supplies a schema-valid tasks.jsonl record. Its input_path can be a valid current-scope direct-child name while output_ref is absolute or traversing and identifies a compatible normalized instance in another readable scope.
- Closest control: TaskStore::all deserializes each record at crates/kcs-pipeline/src/task.rs:129-150, validates input_path at 151-159, input_hash at 160-175, and previous_raw_hash at 176-183. It performs no validation, canonicalization, or scope ownership check on output_ref.
- Direct read sink: load_previous_instance creates PathBuf directly from output_ref at crates/kcs-cli/src/main.rs:9685-9688, parses that directory's manifest at 9691-9692, and reads manifest-selected unit JSON at 9693-9713. A missing/unparseable file degrades to None, but a valid external normalized instance is accepted.
- Reachability: latest_online_instance_for_path selects a Done/Partial online task by current input_path and fallback_reason, then calls load_previous_instance on task.output_ref at crates/kcs-cli/src/main.rs:7008-7026.
- Apparent semantic control: online incremental execution compares the resolved profile hash with previous.manifest.tool_profile_hash at crates/kcs-cli/src/main.rs:6855-6860. This limits compatibility but neither binds the directory to the current repo nor validates the previous raw/profile/unit provenance. A supplied task can identify a genuinely compatible external instance.
- Cross-scope persistence: the previous units enter incremental mapping at crates/kcs-cli/src/main.rs:6820-6830. Unchanged units are designated at 6944-6950; normalized_units_from_response copies previous_unit.markdown into a newly constructed current-raw unit at 9863-9885; the result is persisted in the current scope at 6977-6995.
- Additional effect: partial retry planning independently reads output_ref/manifest.json at crates/kcs-cli/src/main.rs:5780-5790 and can alter retry eligibility, confirming output_ref is treated as an authority-bearing filesystem reference in more than one workflow.

## Evidence and safe control observation

- The static chain is complete at immutable revision 0e19f3c6489da458e93a982a333c308d92d0a0ae.
- A disposable /tmp observation confirmed that an absolute output reference remains absolute and is not rooted beneath the current scope. No manifest/unit file was created or read, and no KCS or network operation ran.
- Existing TaskStore tests at crates/kcs-pipeline/src/task.rs:418-519 verify rejection of bad input_path and input_hash; no corresponding output_ref test or guard exists.

## Counterevidence and severity calibration

- A newly initialized .kcs directory is intended to be owner-only, so ordinary direct-child contributors cannot normally rewrite a healthy live task ledger. The supported lower-trust path is an adopted, copied, preseeded, or shared store.
- The target directory must contain parseable KCS normalized metadata and satisfy incremental/profile preconditions. Random files do not pass these shape checks.
- The online incremental path requires the operator's existing adapter/network authorization. That authorization covers current-scope content, not the unvalidated external output_ref, so it is a precondition rather than scope consent.
- CAND-049 separately covers traversal through manifest.unit_ref, and CAND-061 separately covers semantic tuple rebinding. This report preserves only the output_ref directory-selection root cause.
- Same-user unrestricted writes to the private live ledger would already grant broad authority, but a malicious supplied store can carry the record before the operator adopts it.

## Proof gap and next step

No material V10 gap remains for cross-scope selection, read, and reuse. A two-root, no-network regression would add runtime assurance: construct two benign normalized fixtures, point a current-scope task at the other fixture, and assert TaskStore::all or load_previous_instance rejects it before any read. This shard intentionally did not construct that state.

## Closure row

| Ledger row id | Instance key | Source reference | Seed anchor | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-047 | KCS-R23-CAND-047:task-output-ref-cross-scope | R23 discovery | crates/kcs-pipeline/src/task.rs:129-184 | crates/kcs-cli/src/main.rs:9685-9713 | supplied/shared tasks.jsonl output_ref | external manifest/unit read and current-scope reuse at crates/kcs-cli/src/main.rs:9863-9885 | reportable | requires compatible normalized instance and adopted store; complete V10 closes path | yes |
