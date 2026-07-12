# Validation: Persisted OCR tasks bypass current ignore authorization

- Candidate: `KCS-R23-CAND-067`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-cli/src/main.rs:6050-6067,6533-6573`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.97)**
- Method: **V10 exact normal-task-to-currently-ignored-upload trace**

## Rubric

- [x] A normally produced, scope-local persisted task can remain pending after its path becomes ignored.
- [x] Batch recovery consumes persisted tasks without building a current scan preview.
- [x] Path, hash, size, media, network, budget, and filename-secret controls all pass for an unchanged eligible ignored document.
- [x] No send-time control loads `.kcsignore`, `[scope] ignore`, or checks current scan membership.
- [x] The unchanged document reaches the external OCR request under the stale task.

## Evidence

The source requires no poisoned-state author. A normal scan loads device/scope ignore rules and marks each direct candidate at `crates/kcs-pipeline/src/scan.rs:56-87,90-160`; `load_kcsignore` reads the current file at `crates/kcs-pipeline/src/scan.rs:178-200`. Index processes only candidates whose `ignored` flag is false at `crates/kcs-cli/src/main.rs:9055-9059`. For an eligible PDF or other OCR medium, `enqueue_online_placeholder_task` persists the path, raw hash, online output marker, and pending/paused state at `crates/kcs-cli/src/main.rs:10015-10039,10179-10213`. `TaskDescriptor` carries no scan-decision, ignore-policy digest, or membership token at `crates/kcs-pipeline/src/task.rs:41-75`.

After enqueue, adding a matching `.kcsignore` or `[scope] ignore` rule leaves that task record intact. `run_batch` opens the task store and drives resume/retry directly at `crates/kcs-cli/src/main.rs:5586-5667`; it never calls `build_scan_preview`. `TaskStore::all` validates JSON shape, direct-child path form, and hash syntax at `crates/kcs-pipeline/src/task.rs:129-186`, but has no current scan/ignore input.

The closest send controls are substantial but orthogonal. Pending selection checks task status/type/adapter marker, retry timing, and filename-based secret classification at `crates/kcs-cli/src/main.rs:6050-6067`. `classify_online_markdownize_precondition` rereads the file and verifies the stored hash, current input cap, media routing, and prepare result at `crates/kcs-cli/src/main.rs:6533-6573`. Neither function loads `.kcsignore`, calls `ignored_by_rules`, or compares the path with a current `ScanPreview`. For an unchanged text-layer PDF whose ordinary name is not secret-classified, every one of these controls returns `Send` even though a fresh preview marks the path ignored.

The executor repeats the byte hash and media checks, prepares the document, and calls `run_standard_online_markdownize` with the persisted path/hash at `crates/kcs-cli/src/main.rs:6576-6691`. The production Mistral client rereads the path and places the document into the authenticated OCR request at `crates/kcs-adapter/src/mistral_ocr.rs:112-138`. The current ignore decision never participates between durable task load and that external sink.

This is a normal stale-authorization sequence: enqueue an allowed unchanged document, change only current ignore policy, then invoke batch recovery. Imported or corrupted `tasks.jsonl` can widen the source class, but is not required to validate the candidate.

## Counterevidence and preconditions

- The task must have been legitimately enqueued while the path was allowed, or otherwise supplied through a shared/copied store; a fresh ignored file alone does not create a task.
- Changing the file bytes retires the task through the raw-hash check. The validated sequence keeps the document unchanged and changes only ignore policy.
- Direct-child validation, current size/media checks, filename secret classification, explicit per-adapter network approval, secret-send approval when applicable, budget, credentials, and operator invocation remain required.
- Known secret-looking names remain blocked unless separately approved. Arbitrary confidential PDFs and other non-secret-named documents receive no equivalent ignore recheck.
- A scanned/image document with no prepared hints currently remains `AwaitOcr`; the concrete sink uses a locally preparable OCR-eligible document such as a text-layer PDF enhancement task.

Severity is high because current exclusion policy can be bypassed by an ordinary durable recovery workflow, causing user-readable document bytes to cross an external adapter boundary after the operator has removed that path from scan eligibility. It is not critical because a prior eligible task, persistent network consent, valid credentials, an unchanged OCR-eligible document, and explicit batch execution are all required.

## Tests and remaining uncertainty

No adapter seam or network request was executed under the read-only/no-network constraint. The V10 trace is complete from normal task creation, through the absent current-scan predicate and all nearest contrary controls, to the authenticated document sink.

Proof gap: a hermetic task lifecycle capture was not run. A safe regression should enqueue a fake PDF using the existing mock adapter seam, add the path to `.kcsignore` without changing the file, invoke `batch resume`, and assert zero task attempts, zero charges, and no adapter trace.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-067 | `crates/kcs-cli/src/main.rs:6050-6067,6533-6573` | normal pending task whose unchanged path is now ignored | authenticated OCR document request at `mistral_ocr.rs:112-138` | reportable | prior task/network consent and eligible unchanged document required; no hermetic lifecycle capture | yes |

Validation artifacts: none (V10 trace only).
