# Oversized task JSONL records allocate before validation

## Executive Summary

KCS stores pending batch work in `.kcs/tasks.jsonl`. At revision
`0e19f3c6489da458e93a982a333c308d92d0a0ae`, `TaskStore::all()` reads that
file with an unbounded per-line `String`, deserializes the whole JSON object
into `TaskDescriptor`, and only then applies the path and hash checks that
reject poisoned task state. A lower-trust contributor who supplies an adopted
or preseeded KCS scope can place one very large valid task record, or many
unique task records, so ordinary commands such as `kcs status` allocate memory
and CPU before any semantic guard can fire.

I reviewed the vulnerable revision and the saved target-runtime validation
artifacts directly. I did not create an OOM-sized payload; the included PoC is
a bounded local regression probe that demonstrates the ordering defect with
synthetic records and no network or credentials. The final scan decision rates
this finding Low/P3 because the attack is local to an adopted scope and is
recoverable by repairing the supplied state, while the technical impact remains
a persistent availability failure for task-reading commands.

## Background

KCS task state records deferred work such as markdownization, embedding, and
batch recovery. The writer path serializes a `TaskDescriptor` as one JSON line:

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
    pub parent_run_id: Option<String>,
    pub changed_unit_keys: Vec<String>,
    pub output_ref: String,
    pub unit_keys: Option<Vec<String>>,
    pub status: TaskStatus,
    pub attempts: u32,
    // retry, heartbeat, and budget fields follow
}
```

Those vector and string fields are meaningful to later consumers, but they
also create a size and cardinality boundary. When we adopt a copied scope, the
task file is not freshly emitted by the victim process; it may have been
preseeded by someone else. The reader therefore has to treat the bytes as
untrusted persisted state until it proves the record is small, local, and
well-formed enough to use.

The vulnerable reader is the common choke point:

```rust
// crates/kcs-pipeline/src/task.rs
pub fn all(&self) -> Result<Vec<TaskDescriptor>> {
    let file = match fs::File::open(&self.path) {
        Ok(file) => file,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(err) => { /* convert to PipelineError::Io */ }
    };
    let mut by_id = BTreeMap::new();
    for line in std::io::BufReader::new(file).lines() {
        let line = line.pipeline_io(&self.path)?;
        if line.trim().is_empty() {
            continue;
        }
        let descriptor: TaskDescriptor = serde_json::from_str(&line).map_err(|err| {
            PipelineError::corrupt(self.path.display().to_string(), err.to_string())
        })?;
        // semantic checks follow
        by_id.insert(descriptor.task_id.clone(), descriptor);
    }
    Ok(by_id.into_values().collect())
}
```

Every ordinary caller gets the same behavior. For example, `kcs status` opens
the repository, constructs a `TaskStore`, and includes `task_store.all()` in
its output:

```rust
// crates/kcs-cli/src/main.rs
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

That makes the parsing invariant security-relevant. If we let an adopted task
file allocate first and reject later, a status command, index helper, or batch
recovery path can be wedged before it can explain or repair the bad state.

## Vulnerability Details

The important ordering is inside `TaskStore::all()`. We first let
`BufRead::lines()` grow a `String` until the next newline or EOF. There is no
`take()` wrapper, byte budget, per-line cap, or total record count cap before
that allocation. We then hand the full string to `serde_json::from_str()`,
which allocates every `String` and `Vec<String>` field in the descriptor.

Only after that work do we reach the semantic controls:

```rust
// crates/kcs-pipeline/src/task.rs
if !is_scope_local_file_name(&descriptor.input_path) {
    return Err(PipelineError::path(descriptor.input_path));
}
if !kcs_core::cas::is_hash(&descriptor.input_hash) {
    return Err(PipelineError::corrupt(
        self.path.display().to_string(),
        format!(
            "task input_hash is not a valid hash: {}",
            descriptor.input_hash
        ),
    ));
}
if let Some(previous) = &descriptor.previous_raw_hash {
    if !kcs_core::cas::is_hash(previous) {
        return Err(PipelineError::corrupt(
            self.path.display().to_string(),
            format!("task previous_raw_hash is not a valid hash: {previous}"),
        ));
    }
}
by_id.insert(descriptor.task_id.clone(), descriptor);
```

Those checks are useful, but they are too late for availability. If we carry a
record with `../escape.pdf` in `input_path` and 512 values in both
`changed_unit_keys` and `unit_keys`, KCS still reads the complete line and
builds both arrays before returning the path error. If we instead keep the
path valid and vary `task_id`, every unique descriptor is retained in the
`BTreeMap` until the full result vector is returned.

The saved validation artifacts used exactly that bounded control. A 38,318
byte record with 512 changed-unit keys and 512 unit keys parsed successfully.
A separate file with 64 unique task IDs returned all 64 descriptors. A poisoned
path record with the same large arrays returned `KCS-E-STORE-PATH-001`, proving
that the path guard works semantically but runs only after the expensive parse.

The direct-child path helper shows what the intended boundary is:

```rust
// crates/kcs-pipeline/src/task.rs
pub fn is_scope_local_file_name(input_path: &str) -> bool {
    if input_path.is_empty() || input_path.contains('/') || input_path.contains('\\') {
        return false;
    }
    let mut components = Path::new(input_path).components();
    matches!(components.next(), Some(Component::Normal(_))) && components.next().is_none()
}
```

We want that rule to protect later consumers from scope escape, but it cannot
protect memory use if the reader must first materialize attacker-chosen strings
and collections.

## Exploitability Analysis

The strongest route is a persistent local denial of service against an adopted
scope. The attacker does not need the victim's private live store. They need a
workflow where lower-trust state is copied, synced, archived, or preseeded and
then opened by a KCS user. From there, we control the JSONL file that the victim
will parse as task state.

There are three useful knobs:

1. Per-line size. A single valid JSON object can carry very long strings and
   very large arrays. `BufRead::lines()` and `serde_json::from_str()` pay that
   cost before KCS reaches any project-specific guard.
2. Collection cardinality. `changed_unit_keys` and `unit_keys` are vectors, so
   a syntactically valid descriptor can force allocation proportional to the
   number and length of entries.
3. Unique record count. Duplicate task IDs collapse in the `BTreeMap`, but
   unique IDs are retained. We can therefore shift from one huge line to many
   moderate records when we want to avoid a line-size anomaly and still consume
   memory across the whole read.

Malformed JSON is not a useful bypass; it fails closed as store corruption.
Likewise, direct mutation of a private live store by the same OS user is not an
interesting security boundary, because that user could already damage their
own state. The boundary crossed here is adoption: lower-trust persisted state
causes a trusted local command to allocate before it can reject or recover.

This primitive is not code execution and it does not expose secrets. It is most
useful as a reliable availability wedge. Once the oversized task file is in a
scope, restart does not help; every task-reading command repeats the same parse
until the operator removes or repairs the task state. The practical threshold
depends on the victim machine and allocator behavior, and I did not measure RSS
failure points. The source ordering is still deterministic, and the bounded
probe confirms the allocation and late-rejection sequence without risking a
destructive OOM test.

## Proof of Concept

The included PoC is a safe regression probe. It does not execute KCS commands
or touch any live scope. Instead, it builds synthetic `tasks.jsonl` records with
the same fields that `TaskDescriptor` deserializes, then demonstrates the
vulnerable order: line read, JSON allocation, semantic path validation, and
unique-record retention.

Run it from the report directory:

```sh
cd poc
make run
```

Representative output:

```text
[ok] large record line bytes: 39362
[ok] parsed changed_unit_keys: 512
[ok] parsed unit_keys: 512
[ok] retained unique records: 64
[ok] poisoned path rejected after parsing path guard ran after parsing 512+512 keys: ../escape.pdf
```

The last line is the key property. The path is rejected, but only after the
probe has parsed and counted the large arrays. A fixed reader should reject
over-limit state before building the complete line or descriptor.

## Remediation

The invariant should be: task state is bounded before KCS allocates a complete
record, and every later semantic check runs on data that has already passed
size and cardinality limits. The most direct fix is to replace `lines()` with a
bounded reader loop, enforce total-file and record-count budgets, and deserialize
through bounded field visitors or a preflight object validator.

One minimal shape is:

```rust
const MAX_TASK_FILE_BYTES: u64 = 8 * 1024 * 1024;
const MAX_TASK_LINE_BYTES: u64 = 64 * 1024;
const MAX_TASK_RECORDS: usize = 10_000;
const MAX_TASK_KEYS: usize = 1_024;

pub fn all(&self) -> Result<Vec<TaskDescriptor>> {
    let file = fs::File::open(&self.path)?;
    if file.metadata()?.len() > MAX_TASK_FILE_BYTES {
        return Err(PipelineError::corrupt(
            self.path.display().to_string(),
            "tasks.jsonl exceeds the supported size".to_owned(),
        ));
    }

    let mut by_id = BTreeMap::new();
    let mut reader = std::io::BufReader::new(file);
    let mut line = Vec::new();
    while reader.by_ref().take(MAX_TASK_LINE_BYTES + 1).read_until(b'\n', &mut line)? != 0 {
        if line.len() as u64 > MAX_TASK_LINE_BYTES {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                "task record exceeds the supported line size".to_owned(),
            ));
        }
        let descriptor: TaskDescriptor = serde_json::from_slice(&line)?;
        if descriptor.changed_unit_keys.len() > MAX_TASK_KEYS
            || descriptor.unit_keys.as_ref().map_or(false, |keys| keys.len() > MAX_TASK_KEYS)
        {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                "task record exceeds the supported key count".to_owned(),
            ));
        }
        validate_task_descriptor(&descriptor)?;
        by_id.insert(descriptor.task_id.clone(), descriptor);
        if by_id.len() > MAX_TASK_RECORDS {
            return Err(PipelineError::corrupt(
                self.path.display().to_string(),
                "tasks.jsonl contains too many task records".to_owned(),
            ));
        }
        line.clear();
    }
    Ok(by_id.into_values().collect())
}
```

The exact limits should come from KCS's expected batch sizes, but the order is
the important part. KCS should bound file bytes, line bytes, record count,
string lengths, and vector cardinalities before it retains descriptors. The
error should be actionable and should point the operator at safe task-state
repair rather than repeatedly trying to parse the same oversized file.

Regression tests should cover:

- a record above the per-line byte limit is rejected before JSON
  deserialization;
- a record with too many `changed_unit_keys` or `unit_keys` is rejected with a
  bounded corruption error;
- many unique task IDs cannot exceed the record-count limit;
- malformed paths and hashes are still rejected after the bounded parse;
- `kcs status` surfaces the bounded error without unbounded allocation.

## Summary

KCS correctly validates task paths and hashes, but `TaskStore::all()` reaches
those controls only after it has read and deserialized attacker-shaped task
records. In an adopted or preseeded scope, we can use one huge valid record or
many unique records to consume resources whenever status, index, or batch
recovery reads `.kcs/tasks.jsonl`. The fix is to make task state a bounded
format at the reader boundary: cap bytes and cardinalities first, then run the
existing semantic checks, and finally retain only a bounded number of tasks.
