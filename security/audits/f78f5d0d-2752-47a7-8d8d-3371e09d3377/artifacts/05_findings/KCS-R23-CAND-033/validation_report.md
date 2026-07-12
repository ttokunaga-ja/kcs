# Validation: Deferred OCR tasks read replacement files before enforcing the cap

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-033 |
| Instance key | KCS-R23-CAND-033:deferred-ocr-precap-read |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-cli/src/main.rs:5974-6081 |
| Root control | crates/kcs-cli/src/main.rs:6533-6551 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Severity | medium |
| Method | V5 bounded resource reasoning plus V10 exact static trace |

The candidate survives as local availability amplification. The oversized input is retired before charge or network send, so confidentiality and billed-network impacts are not adopted.

## Validation rubric

- [x] Establish the deferred task and replacement-file source without requiring a narrow race.
- [x] Identify the effective size cap and the exact order of read versus comparison.
- [x] Quantify the pre-control work and memory in terms of attacker-controlled file size.
- [x] Verify the oversized branch fails before reservation and online execution.
- [x] Use only a bounded temporary control and static reasoning; avoid host exhaustion.

## Exact source, control, sink, and boundary

- Source and boundary: execute_pending_markdownize_tasks selects a persisted Pending online-markdownize task at crates/kcs-cli/src/main.rs:6050-6067. Enqueue and resume are separate commands, so a lower-trust scope contributor can replace the formerly small direct child with a much larger or sparse regular file before resume; no timing race inside one call is required.
- Entrypoint: every selected task reaches classify_online_markdownize_precondition before charging at crates/kcs-cli/src/main.rs:6069-6081.
- Broken control and sink: classify_online_markdownize_precondition calls fs::read on the entire current file at crates/kcs-cli/src/main.rs:6537-6541. Only after allocation and I/O does it compare current_bytes.len() with effective_max_input_bytes at 6542-6551.
- Configuration control: the default cap is 104,857,600 bytes at crates/kcs-cli/src/main.rs:4425-4433 and may be overridden. Its placement cannot cap the preceding fs::read.
- Resource relation: for current file size n and configured cap C, the pre-check performs O(n) I/O and retains O(n) bytes even when n is much greater than C. The intended rejection happens only after that work.
- Safety impact: memory pressure, process termination, and I/O contention can occur before the task is safely retired. The Retire branch prevents adapter execution and reservation for an oversized file.

## Evidence and observations

- Immutable source inspection at the pinned revision establishes the control order directly.
- A bounded /tmp control file was exactly 65,536 bytes and was removed after observation. No large allocation, sparse amplification, KCS invocation, external network, real data, or credential was used.
- execute_online_markdownize_task has a later read at crates/kcs-cli/src/main.rs:6596, but the oversized case does not reach it because classification returns Retire first.

## Counterevidence and calibration

- Initial indexing checks ScanCandidate.size_bytes against the cap at crates/kcs-cli/src/main.rs:9060-9070, so the issue requires the deferred task's file to change after enqueue.
- Hash mismatch and cap checks both retire the task, and the pre-charge ordering at 6071-6081 prevents a paid send.
- The affected file must be readable by the KCS process; ordinary disk exhaustion and deliberate operator configuration are not needed, but impact remains local and recoverable.

## Proof gap and next step

Proof gap: peak allocator behavior was not measured because an exhausting probe would be disproportionate and unsafe. A regression should open the deferred input, obtain bounded metadata, reject size greater than C, and then read at most C+1 bytes from the same file identity. The source-order proof is deterministic and sufficient for Medium reportability.

## Closure row

| Ledger row id | Instance key | Source reference | Seed anchor | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-033 | KCS-R23-CAND-033:deferred-ocr-precap-read | R23 discovery | crates/kcs-cli/src/main.rs:5974-6081 | crates/kcs-cli/src/main.rs:6533-6551 | replacement of a queued scope file before resume | whole-file fs::read before effective_max_input_bytes comparison | reportable | retires before send; no unsafe peak-memory probe was run | yes |
