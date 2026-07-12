# Validation: Inline EvidencePointer raw_hash escapes tombstone storage and discloses arbitrary JSON files

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-069 |
| Instance key | KCS-R23-CAND-069:inline-raw-hash-tombstone-read |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-search/src/evidence.rs:9-30 |
| Root control | crates/kcs-cli/src/main.rs:4576-4586 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Confidence score | 0.91 |
| Severity | high |
| Validation method | Complete V10 inline-input-to-JSON-disclosure trace plus safe lexical containment observation |

The candidate survives at High. An untrusted inline EvidencePointer can supply an arbitrary raw_hash; when a valid commit tree lacks that value, tombstone lookup treats it as a path component, reads a process-readable JSON file outside the scope, preserves its fields in KcsError.context, and emits them in JSON error output. No actual file-disclosure payload was executed.

## Validation rubric

- [x] Source: EvidencePointer.raw_hash is an unconstrained String at crates/kcs-search/src/evidence.rs:9-30 and inline JSON checks only schema_version at crates/kcs-cli/src/main.rs:4576-4586.
- [x] Reachability: a valid scope and existing commit whose tree lacks raw_hash reaches read_tombstone at crates/kcs-cli/src/main.rs:4773-4784.
- [x] Closest control: read_tombstone checks only digest length at crates/kcs-cli/src/main.rs:5207-5211; the strict short-hash validator at 4609-4620 is not called.
- [x] File sink: raw_hash reaches the final PathBuf joins and fs::read at crates/kcs-cli/src/main.rs:5212-5226 without containment.
- [x] Disclosure sink: parsed fields become tombstone error context at crates/kcs-cli/src/main.rs:5225-5249 and are serialized in JSON mode at 11184-11190; safe path-only observation confirmed non-containment.

## Exact source, control, sink, and boundary

- Source and interface: run_open/run_view read a caller-supplied pointer, and parse_pointer_text accepts inline JSON at crates/kcs-cli/src/main.rs:2796-2825 and 4572-4586. Serde fills EvidencePointer.raw_hash as an arbitrary String; only schema_version is checked.
- Scope/commit prerequisites: resolve_pointer_for_cli validates scope resolution and requires an existing content-addressed commit at crates/kcs-cli/src/main.rs:4737-4763. These controls are real and must be satisfied.
- Reachable branch: on a non-shallow commit, the tree search compares entry.raw_hash directly with the attacker string. If absent, it calls read_tombstone before returning not_found at crates/kcs-cli/src/main.rs:4773-4784.
- Missing validator: validate_short_hash_operand enforces lowercase hex and minimum length for the sha256 short form at crates/kcs-cli/src/main.rs:4609-4620, but inline pointers bypass it. read_tombstone strips an optional prefix and checks only digest length at 5207-5211.
- Broken path control: read_tombstone joins digest fanout slices and finally joins raw_hash at crates/kcs-cli/src/main.rs:5212-5217. An absolute final component replaces the accumulated path; parent-bearing components are likewise unresolved against the tombstone root. No canonical containment check follows.
- Read and parse sink: fs::read consumes the resulting path at 5218-5224, and serde_json parses the bytes at 5225-5226. Therefore the target must be readable JSON; non-JSON bytes fail without disclosure.
- Disclosure sink: read_tombstone preserves existing object fields while adding scope_path at 5227-5236; tombstone_error adds status and installs the object as KcsError.context at 5241-5249. KcsError::to_error_json includes context at crates/kcs-core/src/error.rs:168-173, and print_error emits it in JSON mode at crates/kcs-cli/src/main.rs:11184-11190.

## Evidence and safe observation

- The complete trace was inspected at revision 0e19f3c6489da458e93a982a333c308d92d0a0ae.
- A disposable /tmp path-only calculation joined one benign absolute JSON path beneath a synthetic tombstone fanout and observed common-path containment false. It did not create or read the JSON target and did not invoke KCS.
- URI parsing requires five slash-separated segments at crates/kcs-search/src/evidence.rs:83-131, so the strongest path form is specifically the inline JSON surface; this scopes rather than defeats the finding.

## Counterevidence and severity calibration

- A legitimate scope_id/scope_path and existing commit are required. An arbitrary standalone JSON operand cannot bypass those controls.
- The chosen raw_hash must be absent from the referenced tree to take the early branch, or otherwise reach the later tombstone check.
- Only process-readable, parseable JSON is exposed. Human error output prints code/message only; JSON mode is the disclosure surface.
- The issue does not write files or execute code. High reflects arbitrary user-readable JSON confidentiality across the selected-scope boundary, especially in agent/tool integrations, not broader filesystem compromise.

## Proof gap and next step

No material V10 gap remains: source, validator bypass, reachable branch, path semantics, read, parse, error context, and output are exact. A safe isolated regression may use only a synthetic marker JSON under /tmp and assert rejection before fs::read, but runtime proof is not required to decide this High finding. Remediation should apply one full hash validator before every EvidencePointer lookup and construct tombstone paths only from validated digest components.

## Closure row

| Ledger row id | Instance key | Source reference | Seed anchor | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-069 | KCS-R23-CAND-069:inline-raw-hash-tombstone-read | R23 discovery | crates/kcs-search/src/evidence.rs:9-30 | crates/kcs-cli/src/main.rs:4576-4586 | untrusted inline EvidencePointer JSON | uncontained tombstone read and JSON error context output | reportable | requires valid scope/commit, absent raw, parseable JSON, and JSON mode; complete V10 | yes |
