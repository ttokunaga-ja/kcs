# Validation: Persisted manifest unit_ref can escape its normalized-instance directory

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-049 |
| Instance key | KCS-R23-CAND-049:manifest-unit-ref-cross-scope |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-pipeline/src/markdownize.rs:65-84 |
| Root control | crates/kcs-cli/src/main.rs:3355-3383 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Confidence score | 0.88 |
| Severity | high |
| Validation method | V6 poisoned-state provenance, complete V10 static trace, and safe absolute-path containment observation |

The candidate survives at High for an adopted, copied, or shared store. A manifest-controlled unit_ref selects a file outside its normalized instance; a compatible normalized-unit JSON is then accepted and indexed or reused under the current scope. The proof preserves this root cause separately from output_ref directory selection and semantic tuple rebinding.

## Validation rubric

- [x] Source: NormalizedUnitManifestEntry.unit_ref is a plain deserialized String at crates/kcs-pipeline/src/markdownize.rs:65-74.
- [x] Closest control: normal writers derive a 16-lowercase-hex unit reference at crates/kcs-pipeline/src/markdownize.rs:347-376, but readers do not enforce it.
- [x] Sink: load_normalized_units joins unit_ref plus .json and reads it at crates/kcs-cli/src/main.rs:3367-3383.
- [x] Reachability/impact: loaded markdown reaches chunk/index rebuilding at crates/kcs-cli/src/main.rs:3030-3127; the previous-instance reader repeats the unsafe join at 9685-9713.
- [x] Countercontrol: an isolated path-only observation confirmed an absolute final component is not contained; no external file was read.

## Exact source, control, sink, and boundary

- Source and boundary: a lower-trust supplied .kcs store can carry a parseable NormalizedInstanceManifest whose Done entry has an absolute or parent-bearing unit_ref. The imported-store boundary is distinct from unrestricted mutation of an already private live store.
- Writer-side control: persist_normalized_instance derives filenames from prepared_unit_ref(unit.unit_key) at crates/kcs-pipeline/src/markdownize.rs:347-376. That helper yields the intended 16-hex reference. This only constrains records created by the normal writer.
- Root-control gap: NormalizedUnitManifestEntry declares unit_ref as String at crates/kcs-pipeline/src/markdownize.rs:65-74 with no deserialization validation.
- Primary sink: load_normalized_units reads the manifest at crates/kcs-cli/src/main.rs:3367-3372, then computes dir.join(format!("{}.json", entry.unit_ref)) and reads/parses that path at 3373-3389. An absolute formatted component resets the base; parent components traverse it.
- Downstream impact: rebuild_step3_index calls load_normalized_units and feeds returned markdown to chunk_normalized_instance before persisting the index at crates/kcs-cli/src/main.rs:3030-3127. A compatible unit from another readable scope can therefore become searchable under the current tree entry.
- Sibling sink: load_previous_instance repeats the same manifest-controlled join at crates/kcs-cli/src/main.rs:9691-9713, allowing the external unit to enter incremental reuse.

## Evidence and safe observation

- All source was read from immutable revision 0e19f3c6489da458e93a982a333c308d92d0a0ae.
- A disposable /tmp path calculation used a benign external unit.json name. Joining it beneath a synthetic normalized instance produced common-path containment false. No manifest, normalized unit, KCS command, or non-synthetic file was created or read.
- The reader has no call to is_normalized_unit_file or prepared_unit_ref before its fs::read.

## Counterevidence and severity calibration

- Fresh .kcs creation is intended to be owner-only. The practical lower-trust source is an adopted/copied/shared store, not an ordinary direct-child content writer.
- The selected external bytes must parse as NormalizedUnitObject; arbitrary non-JSON files do not pass.
- The exact path ends with .json because the reader appends that suffix. Cross-scope normalized unit files naturally satisfy this constraint.
- CAND-047 covers output_ref choosing the instance directory, while CAND-061 covers semantic raw/profile/gen rebinding. Neither replaces this inner manifest filename control.

## Proof gap and next step

No material V10 gap remains for path selection, file read, and indexing. A safe two-root regression can place only synthetic normalized objects in both roots and assert that a non-canonical unit_ref is rejected before fs::read. Runtime proof would increase assurance but would not change reportability.

## Closure row

| Ledger row id | Instance key | Source reference | Seed anchor | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-049 | KCS-R23-CAND-049:manifest-unit-ref-cross-scope | R23 discovery | crates/kcs-pipeline/src/markdownize.rs:65-84 | crates/kcs-cli/src/main.rs:3355-3383 | supplied normalized manifest unit_ref | external unit read then index rebuild at crates/kcs-cli/src/main.rs:3030-3127 | reportable | requires adopted store and parseable KCS unit JSON; complete V10 | yes |
