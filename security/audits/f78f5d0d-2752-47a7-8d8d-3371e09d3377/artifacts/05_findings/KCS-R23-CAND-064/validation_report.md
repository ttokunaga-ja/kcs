# Validation: Batch recovery bypasses repository tool-lock validation

- Candidate: `KCS-R23-CAND-064`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-cli/src/main.rs:5586-5667`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.93)**
- Method: **V10 exact malformed-lock-to-batch-execution trace**

## Rubric

- [x] `Repository::open_current` accepts a scope without validating `tool-lock.json`.
- [x] Both `batch resume` and `batch retry` omit the repository tool-lock validator under the acquired store lock.
- [x] Pending work can proceed from those commands into online adapter execution while the lock is malformed.
- [x] The same malformed lock is rejected by sibling commands using the existing validator.
- [x] The surviving impact is scoped to invalid-lock authorization/provenance; broader well-formed profile mismatch is not attributed to this validator.

## Evidence

Opening the scope is not an implicit negative control. `Repository::open` calls `repo.validate()` at `crates/kcs-core/src/scope.rs:188-206`, while `Repository::validate` checks only configuration, scope, and manifest at `crates/kcs-core/src/scope.rs:235-239`. It does not parse `tool-lock.json`.

`run_batch` opens the repository and acquires the end-to-end store lock, then immediately constructs the task store at `crates/kcs-cli/src/main.rs:5586-5599`. The resume branch mutates eligible paused tasks and calls `execute_pending_tasks` at `crates/kcs-cli/src/main.rs:5600-5617`; the retry branch requeues eligible failures and calls the same executor at `crates/kcs-cli/src/main.rs:5639-5667`. Neither branch calls `validate_repo_tool_lock`.

The omission reaches protected work. `execute_pending_tasks` gates on persistent per-adapter network permission and drives markdownize plus embedding execution at `crates/kcs-cli/src/main.rs:5934-5968`. Pending markdownize tasks are selected and, after task/secret/hash/size/media/budget controls, passed to `execute_online_markdownize_task` at `crates/kcs-cli/src/main.rs:6050-6067,6080-6248`. The executor reaches the real online catalog at `crates/kcs-cli/src/main.rs:6576-6691`. None of those functions reads the repository tool lock.

The missing control is real and used elsewhere. `validate_repo_tool_lock` reads `.kcs/tool-lock.json` and calls `load_tool_lock` at `crates/kcs-cli/src/main.rs:10942-10949`; `load_tool_lock` parses and validates the shape at `crates/kcs-adapter/src/tool_lock.rs:52-57,238-260`. Status, snapshot, log, diff, inspect, and tag call it immediately after open at `crates/kcs-cli/src/main.rs:435-535`, and index, repair, search, and reindex do so at `crates/kcs-cli/src/main.rs:558-570,743-749,1132-1135,2854-2858`. The existing contract test confirms a malformed/future-version lock makes a sibling command fail with a configuration-schema error at `crates/kcs-cli/tests/step3_p0_contract.rs:3804-3817`.

Therefore the same scope state that KCS refuses to inspect, index, repair, search, or reindex can still transition tasks and issue online work through batch recovery. That violates the canonical authorization predicate requiring a valid tool lock and can produce normalized/vector state while the repository's adapter identity record is invalid.

## Counterevidence and preconditions

- The tool lock is normally owner-protected inside `.kcs`; exploitation needs a copied/shared/preseeded scope, corruption, migration fault, or same-user modification.
- General network approval, credentials, eligible task state, current file checks, secret holds, and budget controls remain effective.
- The online adapter returns its actual runtime profile and normalized outputs are keyed by that profile. The trace does not prove that batch labels bytes with a false runtime profile.
- `load_tool_lock` validates shape and modality, not equality with the current effective adapter configuration. Merely adding the existing helper would reject malformed locks but would not solve a well-formed stale-profile mismatch.
- Repairing or removing the malformed lock restores sibling command availability; the durable integrity impact is bounded compared with a credential or arbitrary-file disclosure.

Severity is medium because batch can perform external and durable state transitions under repository identity state that all sibling commands reject, weakening policy consistency and reproducibility. It is not high because the malformed lock alone does not choose a destination, bypass network/secret consent, or falsify the runtime profile attached to produced outputs.

## Tests and remaining uncertainty

No CLI execution was run because the exact branch structure and validator omission are deterministic and the target must remain read-only. Existing tests establish the validator's behavior for sibling commands; there is no corresponding batch negative control.

Proof gap: an isolated batch invocation with a malformed lock was not captured. A regression should create a valid pending task with the offline adapter seam, corrupt only `tool-lock.json`, and assert both `batch resume` and `batch retry` fail before any task mutation or adapter invocation.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-064 | `crates/kcs-cli/src/main.rs:5586-5667` | malformed repository tool lock plus recoverable batch task | task mutation and online markdownize/embedding execution without `validate_repo_tool_lock` | reportable | existing validator is schema-only; runtime profile remains explicit; no isolated CLI capture | yes |

Validation artifacts: none (V10 trace only).
