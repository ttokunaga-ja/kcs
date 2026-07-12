# Persisted OCR tasks bypass current ignore authorization

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` can send a
document to the online OCR adapter after that same document has become
excluded by the current `.kcsignore` or scope ignore policy. The issue is a
stale authorization bug in the durable task recovery path: a normal index pass
creates an online markdownize task while the document is allowed, but a later
`batch resume` or `batch retry` consumes the persisted task without rebinding
it to a fresh scan candidate or current ignore decision.

I reviewed revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` directly and
validated this report by static source tracing plus a local synthetic
regression probe. I did not execute the production OCR adapter, use real
credentials, or send any document to an external service.

The security impact is disclosure of an unchanged, OCR-eligible document that
the operator has since removed from scan eligibility. The final attack-path
rating is Medium/P2: impact is high because excluded document bytes can cross
the external adapter boundary, while likelihood is medium because exploitation
requires a prior allowed task, unchanged bytes, persistent network approval,
valid credentials, budget, and an explicit batch recovery workflow.

## Background

KCS separates a fresh scan decision from later online enrichment. During
indexing, the scanner loads ignore policy, classifies each direct child, and
marks ignored candidates before the index path decides which files can produce
work. We first reach that policy boundary in `build_scan_preview`:

```rust
// crates/kcs-pipeline/src/scan.rs
pub fn build_scan_preview(request: ScanPreviewRequest) -> Result<ScanPreview> {
    let scope_path = PathBuf::from(&request.scope_path);
    let case_insensitive = probe_case_insensitive(&scope_path);
    let mut ignore_rules = load_config_ignore(&scope_path)?;
    ignore_rules.extend(load_kcsignore(&scope_path)?);
    let mut candidates = Vec::new();
    collect_direct_candidates(
        &scope_path,
        &ignore_rules,
        request.include_raw_hashes,
        case_insensitive,
        &mut candidates,
    )?;
```

Inside candidate collection, the scanner records whether the current path is
eligible. The decision is not just cosmetic: the index loop later processes
only candidates where `ignored` is false.

```rust
// crates/kcs-pipeline/src/scan.rs
let ignored = ignored_by_rules(
    &relative,
    file_type.is_dir(),
    ignore_rules,
    case_insensitive,
) || secret == Some(SecretTier::TierA)
    && !explicitly_unignored(
        &relative,
        file_type.is_dir(),
        ignore_rules,
        case_insensitive,
    );

candidates.push(ScanCandidate {
    input_path: relative.clone(),
    media_type: media_type_for_path(&path).to_owned(),
    size_bytes,
    raw_hash,
    ignored,
    quarantine_reason,
});
```

That means the normal authorization model is current and policy-dependent. If
we add a path to `.kcsignore`, a fresh scan should stop treating that path as
eligible for indexing and online OCR.

Online OCR is intentionally delayed. For eligible non-text-native files, KCS
persists a markdownize task and later drives it through the batch machinery.
The task stores identity and lifecycle fields, but it does not store the scan
membership decision or any digest of the ignore policy that authorized the
task:

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
    pub next_retry_at: Option<String>,
    pub deadline: Option<String>,
    pub heartbeat_at: Option<String>,
    pub fallback_reason: Option<String>,
    pub created_at: String,
}
```

We should treat that as a cache of work to do, not as permanent authority to
send the document forever. The vulnerable path does the latter.

## Vulnerability Details

The normal task source is an allowed candidate. The index pipeline filters out
currently ignored files before it reaches per-file processing:

```rust
// crates/kcs-cli/src/main.rs
for candidate in preview
    .candidates
    .iter()
    .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
{
```

When such a candidate needs online OCR, KCS creates a durable task from the
candidate path and raw hash:

```rust
// crates/kcs-cli/src/main.rs
let task = task_descriptor(
    repo,
    TaskType::Markdownize,
    Some(MarkdownizeMode::Full),
    candidate,
    raw_hash,
    &output_ref,
    status,
    reason,
    created_at,
);
task_store.append(&task).map_err(pipeline_to_kcs)?;
```

The descriptor constructor carries `candidate.input_path` and the raw hash
forward, but not `candidate.ignored`, a scan generation, or an ignore-rule
binding:

```rust
// crates/kcs-cli/src/main.rs
fn task_descriptor(
    repo: &Repository,
    task_type: TaskType,
    mode: Option<MarkdownizeMode>,
    candidate: &ScanCandidate,
    input_hash: &str,
    output_ref: &str,
    status: TaskStatus,
    fallback_reason: Option<&str>,
    created_at: &str,
) -> TaskDescriptor {
    TaskDescriptor {
        task_id: format!("task_{}", new_ulid(repo.root())),
        task_type,
        mode,
        input_path: candidate.input_path.clone(),
        input_hash: input_hash.to_owned(),
        previous_raw_hash: None,
```

Now we change only policy: the document bytes stay the same, but the operator
adds the path to `.kcsignore` or changes the effective scope ignore rules. A
fresh `build_scan_preview` would mark the path ignored. The batch path,
however, does not build that preview before it revives or executes persisted
tasks:

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
                    let held_secret = task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD);
                    if task.status == TaskStatus::Paused
                        && (resume.override_budget
                            || task.fallback_reason.as_deref() != Some("budget_exceeded"))
                        && (!held_secret || secrets_approved)
                    {
```

From here we enter the markdownize task executor. The task selection gate
checks lifecycle state, type, adapter output, retry timing, and filename-based
secret classification:

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
```

Those are useful controls, but none asks whether the current scanner still
admits `task.input_path`. The next precondition reopens the current file,
checks the stored hash, applies the current input size cap, rejects
text-native files, prepares the document, and rejects local passthrough text:

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
    if is_text_native_media(&media_type) {
        return OnlineMarkdownizePrecondition::Retire;
    }
```

Again, we carry an unchanged file through the live controls, but no current
ignore rule is loaded and no `ScanCandidate` membership is consulted. For a
text-layer PDF or other locally preparable OCR-eligible document, this
function returns `Send`.

The executor repeats the byte identity and media checks, prepares units, and
then constructs the standard online markdownize request with the persisted
path:

```rust
// crates/kcs-cli/src/main.rs
let outcome = run_standard_online_markdownize(StandardOnlineMarkdownizeRequest {
    scope_id: &scope_id,
    kcs_dir: repo.kcs_dir(),
    raw_hash: &task.input_hash,
    path: &path,
    media_type: &media_type,
    prepared_unit_hints: prepared_unit_hints(&request_units),
    mode: AdapterMarkdownizeMode::Full,
    previous: None,
    hints: None,
    restrict_to_hint_pages: retry_units.is_some(),
})
```

The Mistral OCR adapter then reads the document bytes and sends them in an
authenticated OCR request:

```rust
// crates/kcs-adapter/src/mistral_ocr.rs
fn ocr_markdown(&self, request: &MarkdownizeRequest, model_pin: &str) -> Result<OcrResponse> {
    let api_key = Self::api_key()?;
    let path = request.raw.path.as_deref().ok_or_else(|| {
        AdapterError::ContractViolation("Mistral OCR requires a local raw path".to_owned())
    })?;
    let bytes = std::fs::read(path).map_err(|err| AdapterError::Io {
        path: path.to_owned(),
        message: err.to_string(),
    })?;
    let value: Value = ureq::post(&format!("{}/v1/ocr", self.base_url()))
        .set("Authorization", &format!("Bearer {api_key}"))
        .set("Content-Type", "application/json")
        .send_json(ocr_request_body(
            &request.media_type,
            &bytes,
            model_pin,
            pages.as_deref(),
        ))
```

The violated invariant is narrow: every online send must be authorized by the
current scan policy for the exact bytes being sent. KCS verifies the exact
bytes, but it lets the stale task stand in for the current scan-policy
decision.

## Exploitability Analysis

The strongest realistic path is a stale-task workflow, not arbitrary task
injection. We start with a document that is genuinely eligible for OCR. KCS
indexes it, persists a `Pending` or resumable online markdownize task, and the
operator has already configured the OCR adapter and persistent network
approval. At this point the durable task is legitimate.

The bug becomes security-relevant when policy changes. If the operator later
excludes `private-plan.pdf`, a fresh scan would treat the file as out of
scope. The unchanged bytes still satisfy the durable task's raw-hash check,
however, so the stale task moves through `classify_online_markdownize_precondition`
as if current policy had not changed. We get one external OCR request per live
stale task, and the same pattern can repeat for each eligible task left in the
store.

Several controls limit the primitive:

- We do not get an arbitrary path read. `TaskStore::all` rejects non-local task
  paths before consumers join them onto the repository root.
- We do not bypass the raw-hash guard. If the document changes, the task is
  retired instead of sent.
- We do not bypass filename-based secret classification, persistent network
  approval, adapter credentials, or budget checks.
- We need an OCR-eligible document that reaches a concrete send path. A file
  with no locally prepared hints can remain `AwaitOcr`, and text-native files
  are retired by the send-time mirror controls.

Those constraints are why the likelihood is not high. Still, they do not fix
the authorization bug. Ignore policy is the user's current boundary for what
KCS may process. A local content contributor, shared-scope workflow, or
partially trusted automation can leave a previously eligible task in place
while policy has changed underneath it; later recovery performs the actual
egress under the operator's configured credential. From the user's point of
view, the surprising event is that a document removed from KCS eligibility can
still be posted to an external OCR service because an older task remained
recoverable.

I did not attempt to maximize this into broader credential compromise or code
execution, and the source does not support that conclusion. The impact is
confidentiality loss for excluded document bytes and stale authorization state,
not disclosure of the OCR API key itself.

## Proof of Concept

The included PoC is a safe regression probe that models the vulnerable
decision point with synthetic data. It does not invoke KCS, open a network
connection, or require OCR credentials. We use it to show the missing predicate:
when the task hash still matches and all other local checks pass, the
vulnerable gate returns `Send` even though the current ignore policy excludes
the path. The fixed gate retires the same task before any adapter call.

From the report directory:

```sh
cd poc
make
```

Representative output:

```text
[+] created synthetic OCR-eligible task for private-plan.pdf
[+] current ignore policy excludes private-plan.pdf
[+] vulnerable gate decision: Send
[+] fixed gate decision: Retire
[+] regression expectation satisfied without network or credentials
```

The probe is intentionally a regression model rather than an end-to-end OCR
exercise. A stronger integration regression inside KCS should enqueue a fake
OCR-eligible document with a mock adapter, add the path to `.kcsignore` without
changing the file, run batch recovery, and assert zero task attempts, zero
charges, and zero adapter traces.

## Remediation

The invariant to restore is: immediately before any adapter reservation or
send, the task must still correspond to a current, non-ignored scan candidate
for the same direct-child path and the same raw bytes. If that current
membership check fails, the recovery path should retire the task as non-live
without charging or calling the adapter.

One minimal shape is to add a current-authorization check before
`OnlineMarkdownizePrecondition::Send` can be returned:

```rust
fn current_scan_allows_task(repo: &Repository, task: &TaskDescriptor) -> Result<bool> {
    let preview = build_scan_preview(ScanPreviewRequest {
        scope_path: repo.root().display().to_string(),
        include_raw_hashes: true,
        require_network_approval: false,
    })?;

    Ok(preview.candidates.iter().any(|candidate| {
        candidate.input_path == task.input_path
            && !candidate.ignored
            && candidate.raw_hash.as_deref() == Some(task.input_hash.as_str())
    }))
}
```

Then call that check before budgeting and before `execute_online_markdownize_task`
can reach the adapter:

```rust
match current_scan_allows_task(repo, task) {
    Ok(true) => {}
    Ok(false) => return OnlineMarkdownizePrecondition::Retire,
    Err(_) => return OnlineMarkdownizePrecondition::Retire,
}
```

In production, it may be better to avoid rebuilding a full preview for every
task by computing an equivalent current authorization predicate once per batch
pass: load current config ignore plus `.kcsignore`, probe case sensitivity,
classify the direct child, compute the raw hash only when the candidate remains
eligible, and compare that hash with the task. The important point is that
durable task state must not be the sole authorization artifact.

Regression coverage should include:

- allowed PDF enqueue, unchanged bytes, then `.kcsignore` exclusion before
  `batch resume`;
- the same case through `[scope] ignore` config;
- paused-to-pending recovery and failed-auth revival paths;
- unchanged ignored document with valid budget and credentials, expecting no
  adapter call and no charge;
- changed document bytes, expecting the existing raw-hash retirement behavior
  to remain intact;
- secret-looking filenames, confirming the existing secret-send hold continues
  to apply independently of ignore-policy retirement.

## Summary

KCS correctly treats ignore rules as current scan authorization during fresh
indexing, and it also has meaningful send-time controls for hash identity,
media type, file size, network approval, budget, credentials, and filename
secrets. The missing piece is current scan membership. Because
`TaskDescriptor` does not bind a task to the ignore policy that authorized it,
and because batch recovery does not rebuild or emulate that policy before
sending, a stale OCR task can disclose a document after the user has excluded
it from KCS processing.

We demonstrated the issue from source and with a safe local regression model.
The fix should make current scan authorization an explicit send-time
precondition, then retire stale tasks before cost reservation or adapter
execution. Variant review should cover other durable online work queues that
cache a path and hash without rechecking the current policy boundary before
egress.
