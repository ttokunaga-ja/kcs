# Deferred OCR Tasks Read Replacement Files Before Enforcing the Cap

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
contains a local availability issue in the deferred online OCR task path. A
pending markdownize task records the original `input_path` and `input_hash`,
but when `kcs batch resume` or the equivalent deferred execution path revisits
that task, KCS reads the entire current file before checking whether the file
still matches the task or whether it exceeds `adapter.policy.max_input_bytes`.

I reviewed the pinned revision directly and ran only a bounded synthetic probe;
I did not execute KCS against a large file or attempt to exhaust host memory.
The impact is local and recoverable, but a lower-trust contributor who can
replace a selected-scope file between enqueue and resume can force the invoking
KCS process to perform attacker-controlled `O(n)` I/O and allocation before the
task is retired. The final severity is Low/P3 because the branch stops before
online adapter execution, credential use, network egress, or billing.

## Background

KCS indexes files inside a selected local scope and may defer online OCR-style
markdownization for non-text-native inputs. The deferred task is represented by
a `TaskDescriptor`; the fields that matter here are the path and the raw hash
captured when the task was created:

```rust
// crates/kcs-pipeline/src/task.rs
pub struct TaskDescriptor {
    pub task_id: String,
    #[serde(rename = "type")]
    pub task_type: TaskType,
    pub mode: Option<MarkdownizeMode>,
    pub input_path: String,
    pub input_hash: String,
    pub previous_raw_hash: Option<String>,
    // ...
}
```

During initial indexing, KCS has a documented per-input cap. The default is 100
MB, with scope configuration taking precedence over user configuration:

```rust
// crates/kcs-cli/src/main.rs
const DEFAULT_MAX_INPUT_BYTES: u64 = 104_857_600;

fn effective_max_input_bytes(repo: &Repository) -> u64 {
    read_max_input_bytes_config(&repo.kcs_dir().join("config.toml"))
        .or_else(|| read_max_input_bytes_config(&user_config_toml_path()))
        .unwrap_or(DEFAULT_MAX_INPUT_BYTES)
}
```

The enqueue-time path applies that cap to the scan candidate before adapter
processing:

```rust
// crates/kcs-cli/src/main.rs
let max_input_bytes = effective_max_input_bytes(repo);

for candidate in preview
    .candidates
    .iter()
    .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
{
    if candidate.size_bytes > max_input_bytes {
        result.skipped_oversized_files += 1;
        append_event_log(
            "KCS-I-INDEX-INPUT-OVERSIZED-001",
            "input file exceeds adapter.policy.max_input_bytes; skipped adapter processing",
            json!({
                "size_bytes": candidate.size_bytes,
                "max_input_bytes": max_input_bytes,
            }),
        )?;
        continue;
    }
    // ...
}
```

That first gate means we are not starting from an originally enormous input.
The interesting lifecycle is: we enqueue a valid task for a formerly acceptable
file, then some later command resumes that task after the path has changed.

## Vulnerability Details

The deferred execution loop first selects pending online markdownize tasks from
the task store. We can see that a task survives across commands as a stored
record, and that the precondition check happens before any new budget
reservation or adapter send:

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

for task in tasks {
    let task_id = task.task_id.clone();
    match classify_online_markdownize_precondition(repo, &task) {
        OnlineMarkdownizePrecondition::Send => {}
        OnlineMarkdownizePrecondition::AwaitOcr => {
            continue;
        }
        OnlineMarkdownizePrecondition::Retire => {
            // retire before charge or adapter execution
        }
    }
    // budget reservation and send happen later
}
```

The bug is in the precondition helper. We first rebuild a filesystem path from
the repository root and the task's `input_path`, then `fs::read` pulls the
entire current file into memory. Only after that read does KCS hash the bytes
and check the size cap:

```rust
// crates/kcs-cli/src/main.rs
fn classify_online_markdownize_precondition(
    repo: &Repository,
    task: &TaskDescriptor,
) -> OnlineMarkdownizePrecondition {
    let path = repo.root().join(&task.input_path);
    let media_type = media_type_for_cli_path(&path).to_owned();
    let Ok(current_bytes) = fs::read(&path) else {
        return OnlineMarkdownizePrecondition::Retire;
    };
    if hash_bytes(&current_bytes) != task.input_hash {
        return OnlineMarkdownizePrecondition::Retire;
    }
    if current_bytes.len() as u64 > effective_max_input_bytes(repo) {
        return OnlineMarkdownizePrecondition::Retire;
    }
    // ...
}
```

For the ordinary replacement-file case, the larger file will not hash to the
queued `input_hash`, so we usually retire on the hash-mismatch branch rather
than the size branch. That does not save resources: to compute that hash, we
have already allocated and read the attacker-controlled replacement. If we call
the replacement size `n` and the configured cap `C`, the rejected path still
does `O(n)` I/O and keeps `O(n)` bytes in memory even when `n` is much larger
than `C`. The cap is present in the code, but it is downstream of the operation
it is meant to bound.

This does not require a narrow same-call race. A lower-trust contributor only
needs write or rename authority over a selected-scope file after the original
acceptable task is enqueued and before the operator resumes pending work. When
we carry that changed path into `classify_online_markdownize_precondition`, KCS
has no pre-read metadata or streaming limit to contain the replacement.

## Exploitability Analysis

The strongest route is local resource exhaustion against the user who runs KCS.
We first need a legitimate pending OCR task for a non-text-native file that was
small enough to pass the initial cap. Then the contributor replaces the same
path with a much larger regular file, including a sparse file on filesystems
where logical size and read behavior can amplify the cost. When the operator
later resumes pending work, the process reaches `fs::read` before it has
revalidated the file identity or the size.

From here the attacker controls the replacement's logical size and storage
layout, but not a direct remote execution primitive. The observable outcomes
are memory pressure, process termination, and local I/O contention before the
task is safely retired. The precondition loop is placed before charging and
before `execute_online_markdownize_task`, so the oversized or changed input
does not reach the online adapter and does not create a billing or external
network effect.

There are two useful constraints. First, the original task must exist; a file
that is already oversized at initial index time is skipped by the enqueue gate.
Second, the attacker needs selected-root write or rename authority during the
inter-command window. This is still a realistic internal boundary in shared
folders, generated-content directories, or review folders where the person
running KCS trusts the tool but not every file producer equally.

The main dead end is trying to turn this into content injection or adapter
exfiltration. Because the hash mismatch is checked before the send path, a
normal replacement is retired rather than transmitted. The security issue is
therefore the pre-control local work: the old identity check and the cap both
exist, but they are enforced after an unbounded read.

## Proof of Concept

The included PoC is a safe local model of the vulnerable order. It uses a
temporary directory, a 1 KiB original file, and a 16 KiB replacement with a 4
KiB cap. It does not invoke KCS, contact external services, read real data, or
try to exhaust memory.

Run it from the report directory:

```sh
cd poc
make run
```

Representative output:

```text
python3 deferred_precap_read_probe.py
[+] queued small task: size=1024 cap=4096
[+] replacement before resume: size=16384
[vulnerable-order] decision=retire_hash_mismatch bytes_read_before_control=16384
[fixed-order] decision=retire_oversize_before_read bytes_read_before_control=0
[+] synthetic probe completed without external services or large allocations
```

The important line is the vulnerable-order measurement. We retire the task, but
only after reading the whole 16 KiB replacement. Scaling the replacement from
16 KiB to a much larger file changes only the local resource cost, not the
control-flow conclusion.

## Remediation

The invariant to restore is simple: the deferred-task precondition must bound
the current file before materializing it into a `Vec<u8>`. The check should open
the file, reject non-regular or over-cap metadata, and then read through a
`max + 1` byte stream limit so growth after metadata cannot become another
unbounded read.

One minimal pattern is:

```rust
use std::io::Read;

fn read_capped_input(path: &Path, max_bytes: u64) -> Option<Vec<u8>> {
    let file = fs::File::open(path).ok()?;
    let metadata = file.metadata().ok()?;
    if !metadata.is_file() || metadata.len() > max_bytes {
        return None;
    }

    let mut limited = file.take(max_bytes.saturating_add(1));
    let mut bytes = Vec::with_capacity(metadata.len().min(max_bytes) as usize);
    limited.read_to_end(&mut bytes).ok()?;
    if bytes.len() as u64 > max_bytes {
        return None;
    }
    Some(bytes)
}

fn classify_online_markdownize_precondition(
    repo: &Repository,
    task: &TaskDescriptor,
) -> OnlineMarkdownizePrecondition {
    let path = repo.root().join(&task.input_path);
    let media_type = media_type_for_cli_path(&path).to_owned();
    let max_input_bytes = effective_max_input_bytes(repo);
    let Some(current_bytes) = read_capped_input(&path, max_input_bytes) else {
        return OnlineMarkdownizePrecondition::Retire;
    };
    if hash_bytes(&current_bytes) != task.input_hash {
        return OnlineMarkdownizePrecondition::Retire;
    }
    // ...
}
```

Regression coverage should exercise the real deferred path rather than only the
helper. A focused test should create a pending markdownize task for a small
non-text-native input, replace that path with an over-cap file, run the
precondition or batch-resume path under a deliberately small cap, and assert
that the task retires without reading more than `cap + 1` bytes. A nearby
variant should cover a file that grows after metadata is read; the streaming
limit should still retire it without unbounded allocation.

## Summary

The bug is a resource-bound ordering mistake in a deferred local workflow. KCS
correctly remembers the original task identity and has a configured input cap,
but the resume-time precondition reads the current path before either control
can reject changed or oversized content. We demonstrated that the rejected path
still performs pre-control work, and the fix is to make size and streaming
limits part of the file materialization step itself. Future variant analysis
should look for other deferred consumers that join a stored path to the scope
root and call whole-file readers before revalidating identity, metadata, or
policy caps.
