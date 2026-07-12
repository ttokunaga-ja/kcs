# Unrecognized binary gaps disappear from durable completeness and path telemetry

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` archives direct-child input files before it decides how they can be enriched for search. When an input is classified as `application/octet-stream` and the local prepare stage extracts no text, the CLI increments `skipped_unrecognized_binary_files` in the current `index` result and writes an INFO event. It does not create a task, a per-path unsupported disposition, or an event context that names the affected input path.

That makes the gap disappear from durable product state. After the one `index` response is gone, `kcs status` can show the file only as `unchanged`, and `kcs search` can report `index_status.enriched_ratio = 1.0` with zero pending enrichment tasks. A lower-trust content contributor can therefore place an unsupported but relevant binary in a scope and influence a trusted operator or automation into accepting a false "fully enriched" state. The raw bytes remain archived, so this is not data destruction, code execution, or an authorization bypass; the impact is search completeness and recovery telemetry integrity. I rate it medium severity with high confidence.

I reviewed revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` directly and ran the included offline PoC against the local CLI binary in a disposable scope. I did not use live services, credentials, online adapters, or third-party targets because the vulnerable path is local. I did not identify a fixed revision or public CVE/advisory for this issue.

## Background

KCS is a local-first archive and search CLI. For each indexed direct child, it snapshots the raw bytes, prepares locally extractable units when possible, and uses the task store to represent enrichment work such as Markdownize and Embedding tasks. Humans and agents then use `kcs status` and search `index_status` as workflow signals: "what files exist, what work remains, and how complete is the searchable corpus?"

The security boundary here is not a network boundary. The actor is a lower-trust content contributor who can cause an operator or automation to index a directory containing attacker-chosen files. The trusted side is the operator or agent that relies on KCS completeness telemetry before making decisions from search results.

For that boundary to be reliable, an archived file that cannot become searchable needs a durable, path-bearing state. It can be a task, a permanent unsupported disposition, or another public status row, but it must survive the immediate `index` response and identify the affected path. Otherwise we preserve the raw bytes but lose the fact that the corpus is incomplete.

`status` currently exposes the working tree and the task store:

```rust
// crates/kcs-cli/src/main.rs:435-450
Command::Status => {
    let repo = Repository::open_current()?;
    validate_repo_tool_lock(&repo)?;
    let task_store = TaskStore::new(repo.kcs_dir());
    let status = repo.status()?;
    Ok(json!({
        "scope_path": repo.kcs_dir(),
        "files": status.files,
        "head_shallow": status.head_shallow,
        "tasks": task_store.all().map_err(pipeline_to_kcs)?,
        "quarantine": quarantine_status_records(&repo)?,
        "budget": budget_status_json(&repo)?,
    }))
}
```

We can already see the invariant this interface assumes: any enrichment gap that matters later must be represented in either `files`, `tasks`, or a sibling durable status field. A bare one-run counter cannot satisfy that contract.

## Vulnerability Details

The vulnerable path starts during indexing, after the file has been classified and read. The prepare request carries both the raw hash and the input path, so the code has enough information to bind any unsupported disposition to the path:

```rust
// crates/kcs-cli/src/main.rs:9104-9110
let prepare = prepare_units(PrepareStageRequest {
    raw_hash: raw_hash.clone(),
    media_type: candidate.media_type.clone(),
    input_path: path.display().to_string(),
    tool_profile_hash: prepare_profile_hash.clone(),
})
.map_err(pipeline_to_kcs)?;
```

From here we reach the no-local-text branch. Recognized OCR-able media are sent into the online placeholder path, which creates durable task state. The `application/octet-stream` branch takes a different exit: it increments a counter and writes an event with `media_type` and `size_bytes`, but not `candidate.input_path` or another stable path key.

```rust
// crates/kcs-cli/src/main.rs:9120-9169
if prepare.prepared_units.is_empty() {
    if candidate.media_type != "application/octet-stream" {
        enqueue_online_placeholder_task(
            repo,
            &task_store,
            candidate,
            &raw_hash,
            &scope_id,
            network_allowed,
            secrets_hold,
            args,
            &now,
            &mut result,
            &cost_ledger,
            &budget_caps,
            &month,
        )?;
    } else {
        result.skipped_unrecognized_binary_files += 1;
        append_event_log(
            "KCS-I-INDEX-INPUT-UNRECOGNIZED-BINARY-001",
            "binary input has no locally-extractable text and no OCR-able media type; archived but not enriched",
            json!({
                "media_type": candidate.media_type,
                "size_bytes": candidate.size_bytes,
            }),
        )?;
    }
    continue;
}
```

The immediate response discloses the aggregate count:

```rust
// crates/kcs-cli/src/main.rs:656-671
let mut output = json!({
    "status": if outcome.noop { "noop" } else { "indexed" },
    "approval_method": if args.approve { "approve" } else if args.yes { "yes" } else { "existing" },
    "network_allowed": index_result.network_allowed,
    "network_opt_in": persistent_network_allowed(&repo)?,
    "pending_online_tasks": index_result.pending_online_tasks,
    "paused_tasks": index_result.paused_tasks + enrichment.paused,
    "failed_files": index_result.failed_files,
    "normalized_files": index_result.normalized_files,
    "pending_files": index_result.pending_files,
    "skipped_oversized_files": index_result.skipped_oversized_files,
    "skipped_unrecognized_binary_files": index_result.skipped_unrecognized_binary_files,
```

That is useful while the caller still has this JSON object, but it is not durable completeness state. Once we carry the same scope into later reads, `status` lists the archived working-tree file and all task rows. Because the octet-stream branch created no task and no unsupported-file row, `photo.bmp` or a similar file can appear only as an ordinary unchanged archived file.

Search completeness has the same blind spot. It computes `index_status` entirely from Markdownize and Embedding tasks:

```rust
// crates/kcs-cli/src/main.rs:2422-2506
fn compute_index_status(searched: &[SearchedScopeInfo]) -> Value {
    let mut total = 0u64;
    let mut done = 0u64;
    let mut pending = 0u64;
    let mut budget_paused = false;

    for scope in searched {
        let kcs_dir = scope.scope_path.join(".kcs");
        let store = TaskStore::new(&kcs_dir);
        let Ok(tasks) = store.all() else {
            continue;
        };
        for task in tasks {
            if !matches!(task.task_type, TaskType::Markdownize | TaskType::Embedding) {
                continue;
            }
            if task.fallback_reason.as_deref() == Some(RETIRED_NON_LIVE) {
                continue;
            }
            total += 1;
            match task.status {
                TaskStatus::Done => done += 1,
                TaskStatus::Partial | TaskStatus::Pending | TaskStatus::Running => pending += 1,
                TaskStatus::Paused => {
                    pending += 1;
                    if task.fallback_reason.as_deref() == Some("budget_exceeded") {
                        budget_paused = true;
                    }
                }
                TaskStatus::Failed if task_retry_allowed(&task) => pending += 1,
                TaskStatus::Failed => {}
            }
        }
    }

    let enriched_ratio = if total == 0 {
        1.0
    } else {
        done as f64 / total as f64
    };
    json!({
        "enriched_ratio": enriched_ratio,
        "pending_enrichment_tasks": pending,
        "budget_paused": budget_paused,
    })
}
```

If the unsupported file never produced a task, it is absent from both the numerator and the denominator. If a recognized sibling file produced one completed Markdownize task, the scope looks fully enriched even though one archived file has no searchable representation and no path-addressable recovery state.

## Exploitability Analysis

The strongest route is a completeness-integrity attack against a local workflow. We supply a normal direct-child file whose bytes are binary and whose extension is not mapped to a recognized OCR-able media type. The validation used `photo.bmp`, but the same shape can apply to other unsupported binary inputs: missing-extension images, legacy office files, archives, database files, or compiled blobs. The operator then runs `kcs index --yes` or an equivalent offline index.

During that index run, we get a deterministic state transition:

1. The raw file is archived, so the working tree and commit retain it.
2. `prepare_units()` produces no local text units.
3. The media type is `application/octet-stream`, so no OCR placeholder task is created.
4. The immediate response reports one skipped unrecognized binary.
5. Later public state cannot identify which path was skipped.

That makes the attack practical against agents and operators that do not retain every historical `index` response. A follow-up `status` call says `photo.bmp` is `unchanged`; that is true as a raw archive statement, but it is silent about searchability. A follow-up `search` call can report `enriched_ratio: 1.0` and `pending_enrichment_tasks: 0`; that is true for the existing task set, but the task set no longer covers the full archived corpus.

The useful primitive is not hiding the raw bytes from every possible forensic inspection. A careful operator can still inspect the archive or rerun `index` and observe that some unrecognized binary exists. The primitive is narrower and more workflow-oriented: we can make KCS' durable completeness projection non-actionable. It tells the trusted side that enrichment is done without naming the skipped path or giving a recovery command a durable object to act on.

There are important constraints:

- The attacker needs influence over content that the operator indexes.
- The input must be a direct child in the indexed scope and must reach `application/octet-stream` with no local text units.
- The immediate `index` response does disclose the aggregate count.
- This does not bypass file permissions, network consent, budget limits, or secret handling.
- Recognized OCR-able inputs do not follow this path because they receive task state.

Those constraints keep the severity at medium. We cannot turn this into code execution or data exfiltration from the shown primitive alone. The realistic impact is that downstream search, review, or recovery decisions can be made from a false complete state, especially in automation that treats `index_status` as authoritative.

## Proof of Concept

The included PoC is an offline harness around the real `kcs` CLI. It creates a disposable scope with two files: `ok.md`, which is recognized and searchable, and `photo.bmp`, which is a small binary file that reaches the unrecognized octet-stream branch. The script sets private `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `XDG_CACHE_HOME` directories, runs `init`, `index --yes`, `status`, and text search, then checks the device-local event log.

From the report directory:

```sh
cd poc
make dry-run
KCS_BIN=kcs make run
```

If the binary is not on `PATH`, point `KCS_BIN` at a built `kcs` executable
using a path that is valid from the `poc` directory:

```sh
KCS_BIN=./kcs make run
```

Representative output:

```text
[+] created disposable scope with ok.md and photo.bmp
[+] index: skipped_unrecognized_binary_files=1 normalized_files=1 pending_online_tasks=0
[+] status: photo.bmp status=unchanged and no task references photo.bmp
[+] search: ok.md is searchable and index_status=enriched_ratio=1.0,pending=0,budget_paused=false
[+] event: KCS-I-INDEX-INPUT-UNRECOGNIZED-BINARY-001 has media_type=application/octet-stream,size_bytes=2002 and no path/input_path
[+] vulnerable behavior reproduced: archived binary is absent from durable completeness telemetry
```

The PoC does not contact the network, does not use credentials, and cleans up its temporary directory unless run with `--keep-temp`.

## Remediation

The invariant to restore is simple: every archived input that is intentionally excluded from searchable enrichment must have durable, path-bearing state. The unsupported disposition should be bound at least to the relative input path, raw hash, media type, size, reason, and timestamp. `status` should expose it, and search `index_status` should either count it as an explicit permanent gap or expose a separate unsupported-file count that prevents "fully enriched" from implying full corpus coverage.

A minimal patch should write that disposition at the same branch that currently increments only the counter:

```rust
// sketch: exact storage type omitted
let unsupported = UnsupportedInputDisposition {
    input_path: candidate.input_path.clone(),
    raw_hash: raw_hash.clone(),
    media_type: candidate.media_type.clone(),
    size_bytes: candidate.size_bytes,
    reason: "unrecognized_binary_without_local_text".to_owned(),
    status: UnsupportedInputStatus::Permanent,
};
unsupported_store.record(&unsupported).map_err(pipeline_to_kcs)?;

result.skipped_unrecognized_binary_files += 1;
append_event_log(
    "KCS-I-INDEX-INPUT-UNRECOGNIZED-BINARY-001",
    "binary input has no locally-extractable text and no OCR-able media type; archived but not enriched",
    json!({
        "input_path": candidate.input_path,
        "raw_hash": raw_hash,
        "media_type": candidate.media_type,
        "size_bytes": candidate.size_bytes,
    }),
)?;
```

The event should remain relative-path based and should still honor the existing log redaction policy. The durable store is the more important fix: logs are diagnostic, while `status` and search completeness are the public workflow contracts.

Regression coverage should include:

- a mixed scope with `photo.bmp` and `ok.md`, followed by `index --yes`;
- a later `status --json` after discarding the original index output, asserting that `photo.bmp` appears in an unsupported disposition with its path and raw hash;
- a later `search --text --json` asserting that completeness cannot report an unqualified `enriched_ratio: 1.0` without also exposing the unsupported gap;
- a negative control where an all-text scope reports no unsupported dispositions;
- a recognized OCR-able no-text input control that still receives a task rather than the unsupported disposition.

For existing scopes, a migration or repair pass should reconstruct unsupported dispositions from the current tree and normalized/task state where possible. If the system cannot infer old skipped inputs with high confidence, it should say so explicitly rather than silently keeping the false complete projection.

## Summary

This issue is a durable observability failure. We archive an unsupported binary, then drop the only path-addressable state that would let later status and search account for it. The immediate `index` response reports a count, but the event is pathless and the task-only completeness model excludes the skipped file from both pending work and enrichment ratio calculations.

The PoC demonstrates the full workflow locally: a mixed scope indexes successfully, the recognized Markdown file is searchable, the unsupported binary is preserved as an unchanged file, and search reports full enrichment with no pending work. Fixing the bug requires turning the one-run counter into durable unsupported-input state and teaching the public completeness APIs to include that state in their model.
