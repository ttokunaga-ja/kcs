# Batch recovery bypasses repository tool-lock validation

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
lets `kcs batch resume` and `kcs batch retry` recover and execute queued
online enrichment tasks without first validating the repository
`.kcs/tool-lock.json`.  The same malformed tool-lock state is rejected by
ordinary sibling commands such as `status`, `index`, `repair`, `search`, and
`reindex`, so batch recovery becomes a policy-consistency bypass for adopted
or copied repository state.

I reviewed the vulnerable revision directly and validated the control gap with
a local static regression probe; I did not run an online adapter, use
credentials, or execute a live batch send.  The final attack-path decision is
reportable with **low** severity and **P3** priority because the operator still
controls the command, credential, destination, network approval, byte checks,
secret holds, and budget controls.  The remaining impact is that KCS can mutate
task state, issue approved outbound adapter work, and persist derived state
while the repository identity record is malformed enough that other commands
refuse to operate.

## Background

The repository tool lock is KCS's record of tool identity for a scope.  It
lives under `.kcs/tool-lock.json`, and the CLI already has a helper that parses
the file and fails closed on malformed schema.  The relevant parser rejects a
future or invalid `spec_version` before the deserialized lock is trusted:

```rust
// crates/kcs-adapter/src/tool_lock.rs
pub fn load_tool_lock(bytes: &[u8]) -> Result<ToolLock> {
    let value: Value =
        serde_json::from_slice(bytes).map_err(|err| AdapterError::ConfigSchema(err.to_string()))?;
    validate_tool_lock_value(&value)?;
    serde_json::from_value(value).map_err(|err| AdapterError::ConfigSchema(err.to_string()))
}

fn validate_tool_lock_value(value: &Value) -> Result<()> {
    let object = value
        .as_object()
        .ok_or_else(|| AdapterError::ConfigSchema("tool-lock.json must be an object".to_owned()))?;
    let Some(spec_version) = object.get("spec_version").and_then(Value::as_u64) else {
        return Err(AdapterError::ConfigSchema(
            "tool-lock.json spec_version must be an integer".to_owned(),
        ));
    };
    if spec_version != 1 {
        return Err(AdapterError::ConfigSchema(format!(
            "unsupported tool-lock spec_version: {spec_version}"
        )));
    }
    // ...
    Ok(())
}
```

Several CLI paths call that helper immediately after opening the repository.
For example, `index` takes the store lock and then validates the tool lock
before scanning, snapshotting, or running enrichment work:

```rust
// crates/kcs-cli/src/main.rs
fn run_index(args: IndexArgs) -> Result<Value> {
    if args.online && args.offline {
        return Err(KcsError::invalid_usage(
            "--online and --offline are mutually exclusive",
        ));
    }
    let repo = Repository::open_current()?;
    let _lock = repo.lock_store()?;
    validate_repo_tool_lock(&repo)?;
    if args.revoke_network {
        write_network_revoke_record(&repo)?;
        return Ok(json!({ "status": "network revoked" }));
    }
    // ...
}
```

The sibling negative control is not theoretical.  The existing contract test
corrupts `tool-lock.json` to a future schema version and asserts that `status`
fails with `KCS-E-CONFIG-SCHEMA-001`:

```rust
// crates/kcs-cli/tests/step3_p0_contract.rs
#[test]
fn r6_tool_lock_rejects_future_spec_version() {
    let dir = indexed_scope();
    let path = dir.path().join(".kcs/tool-lock.json");
    let mut value: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    value["spec_version"] = Value::from(999);
    fs::write(&path, serde_json::to_vec_pretty(&value).unwrap()).unwrap();

    let err = json_failure(&dir, &["status"], 2);
    assert_eq!(err["error_code"], "KCS-E-CONFIG-SCHEMA-001");
    assert!(err["message"]
        .as_str()
        .unwrap()
        .contains("unsupported tool-lock spec_version"));
}
```

The important boundary is therefore not remote network exposure.  KCS has no
inbound listener in this finding.  The boundary is local adoption of repository
state from a lower-trust archive, shared folder, migration, or preseeded scope,
followed by an operator-mediated recovery command that may perform outbound
adapter work under the operator's existing approval.

## Vulnerability Details

We first reach the gap at repository open.  `Repository::open()` validates the
scope's config, scope metadata, and manifest, then self-heals `HEAD`; it does
not parse `.kcs/tool-lock.json`.

```rust
// crates/kcs-core/src/scope.rs
pub fn open(path: impl AsRef<Path>) -> Result<Self> {
    let root = path.as_ref().canonicalize().kcs_io(path.as_ref())?;
    let kcs_dir = root.join(".kcs");
    if !kcs_dir.is_dir() {
        return Err(KcsError::invalid_usage("not a kcs scope"));
    }

    let repo = Self {
        root,
        kcs_dir: kcs_dir.clone(),
        store: ObjectStore::new(kcs_dir),
    };
    repo.validate()?;
    repo.self_heal_head()?;
    Ok(repo)
}

pub fn validate(&self) -> Result<()> {
    self.validate_config()?;
    self.validate_scope()?;
    self.validate_manifest()?;
    Ok(())
}
```

That means every command which needs the repository identity predicate must
call `validate_repo_tool_lock()` explicitly.  Most relevant commands do.  The
batch recovery dispatcher does not.

```rust
// crates/kcs-cli/src/main.rs
fn run_batch(args: BatchArgs) -> Result<Value> {
    let repo = Repository::open_current()?;
    let _lock = repo.lock_store()?;
    let store = TaskStore::new(repo.kcs_dir());
    let secrets_approved = secrets_send_approved(&repo);
    match args.command {
        Some(BatchCommand::Resume(resume)) => {
            let changed = store
                .update_matching(|task| {
                    // Paused -> Pending transition
                    // ...
                })
                .map_err(pipeline_to_kcs)?;
            let outcome = execute_pending_tasks(&repo, &store, resume.override_budget, true)?;
            // ...
        }
        Some(BatchCommand::Retry) => {
            let partial_reenqueued = reenqueue_partial_markdownize_tasks(&store)?;
            let changed = store
                .update_matching(|task| {
                    // Failed -> Pending transition
                    // ...
                })
                .map_err(pipeline_to_kcs)?;
            let outcome = execute_pending_tasks(&repo, &store, false, false)?;
            // ...
        }
        // ...
    }
}
```

If we carry a malformed tool lock into this function, the store lock is
acquired and the task store is opened before any tool-lock validation could
fail.  The `resume` branch can flip paused work back to `Pending`; the `retry`
branch can requeue failed or partial work.  Both branches then call
`execute_pending_tasks()`.

The sink is meaningful because pending work is not just a local status change.
`execute_pending_tasks()` can drive markdownize and embedding enrichment when
the independent network approval gates pass:

```rust
// crates/kcs-cli/src/main.rs
fn execute_pending_tasks(
    repo: &Repository,
    store: &TaskStore,
    override_budget: bool,
    allow_auth_revive: bool,
) -> Result<ExecOutcome> {
    let mut outcome = ExecOutcome::default();
    reclaim_orphaned_running_tasks(store)?;
    if persistent_network_allowed(repo)? {
        outcome.add(execute_pending_markdownize_tasks(
            repo,
            store,
            override_budget,
            allow_auth_revive,
        )?);
    }
    let embedding_online = embedding_online_allowed(repo, false, false, false)?;
    outcome.add(run_embedding_enrichment(
        repo,
        embedding_online,
        override_budget,
    )?);
    Ok(outcome)
}
```

The markdownize path still performs many important checks.  It filters pending
tasks, respects retry timing, enforces secret holds, checks current bytes
against the queued raw hash, blocks text-native sends, prepares units, applies
budget accounting, and only then calls the online markdownize adapter:

```rust
// crates/kcs-cli/src/main.rs
let tasks = store
    .all()
    .map_err(pipeline_to_kcs)?
    .into_iter()
    .filter(|task| {
        task.status == TaskStatus::Pending
            && task.task_type == TaskType::Markdownize
            && task.output_ref == output_ref
            && task_retry_due(task)
            && (secrets_approved
                || classify_secret(&task.input_path).is_none())
    })
    .collect::<Vec<_>>();

// ...

store
    .update_matching(|candidate| {
        if candidate.task_id == task_id {
            candidate.status = TaskStatus::Running;
            candidate.heartbeat_at = Some(now_utc_seconds());
            candidate.fallback_reason = None;
            // ...
            true
        } else {
            false
        }
    })
    .map_err(pipeline_to_kcs)?;
match execute_online_markdownize_task(repo, &task) {
    // ...
}
```

Those controls are why the finding is bounded.  They do not, however, restore
the missing repository identity predicate.  The same scope state that `status`,
`index`, `repair`, `search`, and `reindex` reject as malformed can still be
used by `batch resume` or `batch retry` to mutate recovery state and attempt
adapter work.

## Exploitability Analysis

The realistic route is a supplied-state workflow rather than direct remote
attack.  We need a lower-trust source that can influence a copied, shared,
migrated, or preseeded KCS scope.  We also need an otherwise eligible persisted
task: the file bytes must still match the queued hash, the task must not be
blocked by secret classification, the relevant adapter/network approval must
already exist, and budget checks must pass.

From there the primitive is simple.  We provide a scope whose
`.kcs/tool-lock.json` is malformed, for example with a future
`spec_version`, while preserving a recoverable markdownize or embedding task.
An operator or automation then runs:

```text
kcs batch resume
kcs batch retry
```

The operator is still the actor who executes the command and supplies the
credential context.  The defect is that batch recovery accepts a repository
identity state that the normal fail-closed command surface rejects.  That can
produce durable normalized, OCR, or vector state during a window where the
repository's tool identity record is invalid.  In a workflow that relies on the
tool lock for provenance, reproducibility, or policy auditing, we can now get
derived state whose surrounding repository identity predicate would have
stopped sibling commands.

The strongest practical abuse is policy inconsistency.  We do not get to
choose the configured adapter destination solely by corrupting
`tool-lock.json`; the saved analysis correctly notes that the existing helper
validates schema and modality, not equality with the current effective adapter
configuration.  We also do not bypass send-time file hash checks, secret holds,
network opt-in, credentials, or spend controls.  A malformed lock by itself
therefore does not become credential theft, arbitrary code execution, or
unbounded exfiltration.

There are still useful defender-facing consequences:

- a shared archive can be made to fail safe under `status` or `index` but
  proceed under recovery automation;
- a CI or operator runbook that uses `batch retry` to drain prior work can
  create or update derived state before noticing that the repository identity
  record is invalid;
- audit trails can contain outputs generated during an invalid-lock interval,
  which makes later reproducibility and incident review harder.

The main dead end is destination substitution.  If we try to present this as
"malformed tool-lock changes the adapter target," the source does not support
that claim.  The adapter path uses existing configuration and runtime profile
reporting, and the finding remains about missing validation before recovery,
not about falsifying the runtime profile attached to produced outputs.

## Proof of Concept

The included PoC is a local static regression probe.  It reads a KCS checkout,
extracts the relevant functions, and verifies three facts without running a
live adapter or touching credentials:

1. `run_batch()` reaches `execute_pending_tasks()` without calling
   `validate_repo_tool_lock()` first.
2. sibling commands such as `run_index()` and `run_repair()` do call
   `validate_repo_tool_lock()`;
3. the tool-lock parser rejects unsupported `spec_version` values when the
   helper is invoked.

From the PoC directory, point `KCS_REPO` at a checkout of the vulnerable
revision:

```sh
cd poc
KCS_REPO=../kcs make run
```

Representative output on revision
`0e19f3c6489da458e93a982a333c308d92d0a0ae`:

```text
[+] run_batch opens the repository and holds the store lock
[+] run_batch can reach execute_pending_tasks
[!] VULNERABLE: run_batch reaches execution without validate_repo_tool_lock
[+] run_index validates the tool lock
[+] run_repair validates the tool lock
[+] Repository::validate does not cover tool-lock.json
[+] tool-lock parser rejects unsupported spec_version
[result] observed expected state: vulnerable
```

For a patched tree, run the same probe with `EXPECT=fixed`:

```sh
cd poc
KCS_REPO=../kcs EXPECT=fixed make run
```

The probe is intentionally non-destructive.  It does not create a `.kcs`
scope, mutate task ledgers, invoke KCS commands, contact providers, or read
credentials.  It is suitable as a guardrail regression check, while a full
integration test should exercise the actual `batch resume` and `batch retry`
commands with a temporary scope and an offline adapter seam.

## Remediation

The minimal invariant is: after the store lock is acquired and before any
batch recovery state transition, KCS must validate the repository tool lock in
the same fail-closed way as sibling commands.

The smallest patch shape is to insert `validate_repo_tool_lock(&repo)?` in
`run_batch()` immediately after `repo.lock_store()` and before constructing or
mutating `TaskStore`:

```rust
fn run_batch(args: BatchArgs) -> Result<Value> {
    let repo = Repository::open_current()?;
    let _lock = repo.lock_store()?;
    validate_repo_tool_lock(&repo)?;
    let store = TaskStore::new(repo.kcs_dir());
    let secrets_approved = secrets_send_approved(&repo);
    // ...
}
```

We want the validation under the lock so the checked repository state is the
same state that recovery is about to consume.  We also want it before
`update_matching()` so a malformed tool lock cannot even cause Paused ->
Pending or Failed -> Pending mutations.

Regression coverage should include:

- a malformed/future-version `.kcs/tool-lock.json` plus a paused markdownize
  task, asserting `batch resume` fails with `KCS-E-CONFIG-SCHEMA-001` and no
  task status changes;
- the same malformed lock plus retryable failed and partial markdownize tasks,
  asserting `batch retry` fails before requeue;
- a positive test showing well-formed locks still allow recovery when the
  independent network, secret, byte, and budget gates permit it;
- a guard that keeps this schema-validation fix separate from stronger
  adapter-profile binding work.  The helper rejects malformed locks; it does
  not prove that every queued task matches the current effective adapter
  profile.

As structural hardening, KCS can centralize "open a scope for work that may
consume adapter-derived state" into one helper that opens the repository,
acquires the store lock when needed, validates `tool-lock.json`, and returns a
typed context.  That reduces the chance that future recovery, maintenance, or
inspection paths manually remember only part of the command prelude.

## Summary

`batch resume` and `batch retry` were brought up to the same store-locking
standard as other mutating commands, but they missed the repository tool-lock
validation that sibling commands apply.  We followed the source from
`Repository::open_current()` into `run_batch()`, through task mutation, and
into pending online execution, then compared that path with the existing
validator and sibling negative test.

The result is a bounded provenance and authorization-control bypass: an
adopted scope with malformed tool-lock state can still drive recovery work
under the operator's already approved adapter context.  Future variant analysis
should look for other command paths that consume adapter-derived state after
`Repository::open_current()` without using a shared validated-work context,
especially maintenance and recovery code that was added after the original
tool-lock contract.
