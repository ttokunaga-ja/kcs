# Persisted task `output_ref` can select a foreign normalized instance

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` accepts a
persisted task descriptor whose `output_ref` points outside the current KCS
scope. The single task-ledger read choke point validates `input_path`,
`input_hash`, and `previous_raw_hash`, but it leaves `output_ref` as an
untrusted filesystem string. Later incremental markdownize code treats that
string as an authority-bearing normalized-instance directory, reads its
`manifest.json` and unit JSON files, and can persist unchanged foreign markdown
under the current scope's raw identity.

I reviewed the vulnerable revision directly, traced the saved validation and
attack-path reports, and ran the included local synthetic PoC. I did not contact
an online adapter, read any real external document, or exercise a live shared
store. The final scan decision is `medium` severity with `P2` priority: the data
read and provenance substitution are high-impact for a supplied or shared store,
while exploitation still requires adoption of lower-trust persisted task state,
a readable compatible normalized instance, and an incremental or retry workflow.

## Background

KCS stores asynchronous pipeline work in `.kcs/tasks.jsonl`. Each line
serializes a `TaskDescriptor`, and downstream batch and status workflows consume
those descriptors through `TaskStore::all()`. For a copied or shared KCS store,
that file is exactly the trust boundary: a contributor can supply persisted task
state before the operator adopts the scope, while the operator's KCS process
later runs with the operator's filesystem authority.

The descriptor carries both current-scope identity and previous-output state:

```rust
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
```

The normal invariant should be that every persisted reference used to read
normalized state is either a contained reference below the current `.kcs`
directory or a deliberately typed logical reference that is resolved under that
scope. Once `output_ref` is a plain string, we need the reader to enforce that
invariant before any later workflow opens files through it.

## Vulnerability Details

We first reach the task reader through `TaskStore::all()`. The function does a
useful amount of centralized validation, but the decisive gap is the field that
is missing from that list:

```rust
let descriptor: TaskDescriptor = serde_json::from_str(&line).map_err(|err| {
    PipelineError::corrupt(self.path.display().to_string(), err.to_string())
})?;
if !is_scope_local_file_name(&descriptor.input_path) {
    return Err(PipelineError::path(descriptor.input_path));
}
if !kcs_core::cas::is_hash(&descriptor.input_hash) {
    return Err(PipelineError::corrupt(
        self.path.display().to_string(),
        format!("task input_hash is not a valid hash: {}", descriptor.input_hash),
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

If we supply a descriptor with a current-scope `input_path` and valid hash-shaped
fields, the descriptor survives even when `output_ref` is absolute or contains a
parent traversal. From here the dangerous path is the online incremental reuse
flow. The selector looks for a prior online task for the same input path and
carries the unchecked `output_ref` into `load_previous_instance()`:

```rust
let mut tasks = task_store
    .all()
    .map_err(pipeline_to_kcs)?
    .into_iter()
    .filter(|task| {
        task.input_path == input_path
            && matches!(task.status, TaskStatus::Done | TaskStatus::Partial)
            && task.fallback_reason.as_deref() == Some("online_adapter_done")
    })
    .collect::<Vec<_>>();
tasks.sort_by(|a, b| b.created_at.cmp(&a.created_at));
for task in tasks {
    if let Some(previous) = load_previous_instance(&task.output_ref)? {
        return Ok(Some(previous));
    }
}
```

Inside `load_previous_instance()`, the string becomes a `PathBuf` directly. There
is no canonicalization against the current repository root, no `.kcs` containment
check, and no proof that the normalized directory belongs to the same raw input:

```rust
fn load_previous_instance(output_ref: &str) -> Result<Option<PreviousInstance>> {
    let dir = PathBuf::from(output_ref);
    let manifest_path = dir.join("manifest.json");
    let Ok(bytes) = fs::read(&manifest_path) else {
        return Ok(None);
    };
    let manifest: NormalizedInstanceManifest =
        serde_json::from_slice(&bytes).map_err(|err| KcsError::schema(err.to_string()))?;
    let mut units = Vec::new();
    for entry in &manifest.units {
        if entry.status != UnitStatus::Done {
            continue;
        }
        let unit_path = dir.join(format!("{}.json", entry.unit_ref));
        let Ok(bytes) = fs::read(&unit_path) else {
            return Ok(None);
        };
```

At this point we have crossed the boundary. A supplied task state can make the
victim process read another operator-readable normalized instance. Random files
will not pass the manifest and unit shape checks, and the incremental path still
compares tool profile hashes, but those are compatibility checks rather than
scope-ownership checks. If the foreign instance is compatible, the previous unit
objects become the trusted base for reuse.

The bad state becomes durable when unchanged units are copied into the current
run. In the reuse loop below, we carry `previous_unit.markdown` forward while
relabeling the object with the current `raw_hash`, current `prepared_hash`, and
current `tool_profile_hash`:

```rust
for unit_key in &response.unchanged_unit_keys {
    let prepared = prepared
        .get(unit_key.as_str())
        .ok_or_else(|| KcsError::schema("adapter returned unknown unchanged unit"))?;
    let previous_unit = previous_units
        .get(unit_key.as_str())
        .ok_or_else(|| KcsError::schema("unchanged unit has no previous normalized unit"))?;
    units.push(NormalizedUnitObject {
        unit_key: unit_key.clone(),
        unit_type: prepared.unit_type,
        raw_hash: raw_hash.to_owned(),
        prepared_hash: prepared.prepared_hash.clone(),
        tool_profile_hash: tool_profile_hash.to_owned(),
        gen: 0,
        mode,
        markdown: previous_unit.markdown.clone(),
        reused_from: Some(kcs_pipeline::markdownize::ReusedFrom {
            raw_hash: previous_unit.raw_hash.clone(),
```

The caller then persists the new manifest and units into the current scope:

```rust
let manifest = manifest_from_units(
    prepared_units,
    &units,
    &task.input_hash,
    &profile_tool_hash,
    Some(previous.manifest.gen),
    &run_id,
    &generated_at,
    RetryErrorKind::NetworkError,
);
persist_normalized_instance(repo.kcs_dir(), &manifest, &units).map_err(|_| {
    TaskExecutionFailure {
        retry_kind: persist_failure_retry_kind(),
    }
})?;
```

So the root cause is not merely that an odd path string is accepted. We first let
a lower-trust persisted descriptor choose a previous normalized-instance
directory; we then read its manifest and unit JSON with the victim's filesystem
authority; finally, if the compatibility gates line up, we bind foreign markdown
to current-scope provenance and store it as if it belonged to the current input.

A second workflow shows the same authority pattern in a lighter form. Partial
retry planning also opens `output_ref/manifest.json` directly:

```rust
fn partial_retry_plan_from_instance(output_ref: &str) -> Result<PartialRetryPlan> {
    let empty = PartialRetryPlan {
        retryable_units: Vec::new(),
        max_attempts: Some(0),
    };
    let manifest_path = PathBuf::from(output_ref).join("manifest.json");
    let Ok(bytes) = fs::read(&manifest_path) else {
        return Ok(empty);
    };
```

That path does not itself copy markdown into the current scope, but it confirms
that `output_ref` is treated as a filesystem authority in more than one
consumer.

## Exploitability Analysis

The most practical route is an archive or supplied-store attack. We begin with a
valid task record for a current direct-child file so the existing `input_path`
and hash controls do not fire. We set `status` to `done` or `partial`, set
`fallback_reason` to `online_adapter_done`, and point `output_ref` at a readable
normalized instance outside the current `.kcs` tree. If the victim invokes an
online incremental path for the same `input_path`, KCS selects that task as the
latest previous online instance and opens the foreign manifest.

The strongest primitive is durable provenance substitution. We do not need the
foreign file to be arbitrary JSON; it needs to be genuine KCS normalized state
with unit keys and profile data that can satisfy the incremental mapping and
profile comparison. Once that is true, unchanged units can carry their foreign
`markdown` into a new normalized object whose `raw_hash` and prepared metadata
belong to the current scope. That can pollute later search, evidence, archive,
and review workflows: the displayed text is from the foreign instance, while the
new object appears to derive from the current input.

There is also a confidentiality angle. The victim process reads the foreign
manifest and unit files as the victim OS user. The bug does not let a task record
select an arbitrary credential file directly; the target has to look like a
parseable normalized instance. But normalized markdown often contains extracted
document text, and the vulnerable flow can move that text across scope
boundaries without the operator explicitly authorizing that previous scope as an
incremental source.

Several constraints keep the severity at the scan's final `medium` rating. A
fresh `.kcs` directory is intended to be owner-only, so a normal direct-child
contributor should not be able to rewrite a healthy live task ledger. The
attacker needs a copied, synced, preseeded, or otherwise lower-trust persisted
store before adoption. The attacker also needs either knowledge of a compatible
foreign normalized-instance path or the ability to arrange one. Finally, the
online incremental branch still depends on the operator's adapter authorization
and profile compatibility. Those checks limit reachability, but they do not
restore the missing scope binding once the task state is accepted.

A less powerful route is partial retry manipulation. If we carry the same
unchecked `output_ref` into `partial_retry_plan_from_instance()`, KCS reads a
foreign manifest and can alter retry eligibility. That route is useful for
showing the pattern, but the incremental unchanged-unit copy is the route that
turns the cross-scope read into durable current-scope contamination.

## Proof of Concept

The PoC is a local model of the vulnerable state transition. It does not invoke
KCS, contact an adapter, read a real external document, or require credentials.
Instead it builds two synthetic scopes under one disposable temporary directory:
a victim scope with a supplied task record, and a foreign scope with a compatible
normalized manifest and unit. The vulnerable model accepts the absolute foreign
`output_ref`, loads the foreign markdown, and rebinds it to a current raw hash.
The fixed model rejects the same reference before any manifest read because the
resolved path is outside the victim's normalized root.

From this report directory:

```sh
cd poc
make
```

Representative output:

```text
[+] built victim and foreign fixture under a disposable temp root
[+] vulnerable loader accepted foreign output_ref
[+] unchanged reuse copied foreign markdown into current raw identity
[+] fixed guard rejected cross-scope output_ref before reading manifest
```

The PoC is intentionally non-destructive. It creates only temporary directories
through Python's `tempfile` module and removes them automatically when the process
exits.

## Remediation

Restore the invariant at the single task read boundary and again at the file read
boundary: a persisted `output_ref` must be a canonical, scope-contained
normalized-instance reference, and the loaded manifest and units must be rebound
to the current tuple before reuse.

A minimal defensive shape is:

```rust
fn validate_task_output_ref(kcs_dir: &Path, output_ref: &str) -> Result<PathBuf> {
    let normalized_root = kcs_dir.join("objects").join("normalized");
    let rel = Path::new(output_ref);
    if rel.is_absolute() || rel.components().any(|c| matches!(c, Component::ParentDir)) {
        return Err(PipelineError::path(output_ref.to_owned()));
    }
    let candidate = normalized_root.join(rel);
    let canonical_root = normalized_root.canonicalize().pipeline_io(&normalized_root)?;
    let canonical_candidate = candidate.canonicalize().pipeline_io(&candidate)?;
    if !canonical_candidate.starts_with(&canonical_root) {
        return Err(PipelineError::path(output_ref.to_owned()));
    }
    Ok(canonical_candidate)
}
```

The exact storage layout may call for a typed normalized-instance identifier
instead of a relative path string. The important part is that KCS should not pass
an arbitrary persisted string into `PathBuf::from()` and then read from it.
`TaskStore::all()` should reject absolute and parent-bearing `output_ref` values
before returning descriptors, and `load_previous_instance()` should accept a
validated reference or a current-scope base directory rather than a raw string.

Regression tests should cover these cases:

- `TaskStore::all()` rejects absolute `output_ref` values while still accepting
  valid current-scope task records.
- `TaskStore::all()` rejects `../` traversal in `output_ref`.
- `load_previous_instance()` refuses a normalized directory outside the current
  `.kcs` root before reading `manifest.json`.
- Incremental reuse fails closed when the previous manifest's raw hash, profile,
  generation, unit keys, or prepared hashes do not match the current tuple.
- Partial retry planning uses the same validated reference resolver as the
  incremental path.

For defense in depth, store normalized references as structured object IDs rather
than filesystem paths, and keep all previous-instance resolution behind one API
that receives the current `Repository` or current `.kcs` root.

## Summary

The vulnerable path starts with lower-trust persisted task state and ends with
foreign normalized markdown stored under current-scope provenance. We can follow
the chain from `TaskStore::all()` accepting an unchecked `output_ref`, through
`load_previous_instance()` reading a manifest and unit JSON from that path, to
`normalized_units_from_response()` copying prior markdown into a new current
object. The existing input filename, hash-shape, manifest parse, and profile
checks reduce accidental misuse, but none of them proves that the previous
instance belongs to the current scope. Binding `output_ref` to the current `.kcs`
root before any read, then rechecking the loaded manifest against the current
raw/profile/unit tuple, closes the confused-deputy path.
