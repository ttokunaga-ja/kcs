# Mistral OCR can upload bytes reopened after the final hash check

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` validates an
online OCR task by reading its selected-scope pathname and comparing the
result with the task's approved SHA-256 identity. That is the right check,
but the checked byte buffer is not used as downstream input. The Mistral OCR
adapter later opens the pathname again and constructs the authenticated
request from this second read without comparing it with the approved hash.

A lower-trust contributor who can replace a file in the selected directory
while KCS is processing it can therefore leave version A in place for the
final hash, size, media, secret, approval, and budget gates, then atomically
replace the pathname with version B before the adapter read. KCS sends B to
the operator-configured OCR provider while retaining `H(A)` as the task and
normalized-output identity. If the replacement is a symlink to a file that
the KCS process can read, the same primitive can cross the selected-scope
boundary; that stronger branch is platform- and permission-dependent and was
not exercised here.

The direct consequences are an unapproved document upload and false
provenance for the returned normalized units. The request still goes to the
operator-configured Mistral endpoint, and the bearer credential is not shown
to the contributor, so this is neither arbitrary-destination exfiltration nor
credential theft. The affected surface is also an operator-invoked local CLI,
not a listener. Taking those controls together with the required concurrent
rename and unmeasured race reliability, the final rating is **Medium / P2**.

The production client first gained the unbound pathname read and HTTP upload
in commit `3b5039710177d9ceb3cdb07fc99275b4d573efbd` on 2026-07-03. The exact
check-then-reopen form described here exists from
`b36679f1517e1ac0488d346ec485db62ad69c130` on 2026-07-06, when the executor's
stale-task hash check was added without carrying its buffer to the sink. It
remains present in the reviewed 2026-07-10 revision. I found no repository tag,
fixed revision, or advisory identifier that narrows that confirmed source
range.

I reviewed the exact target revision and its relevant history, traced both
full and incremental online paths to the production request body, and ran the
credential-free temporary-file regression included with this report. The
regression deterministically showed that a post-check atomic replacement is
captured by the vulnerable adapter model and rejected by a final-byte binding
oracle. I did not invoke KCS end to end, access an API key, open a socket,
contact Mistral, test a symlink to a sensitive file, or measure how often an
unassisted race wins on supported filesystems.

## Background

KCS is a local-first CLI. Its online Markdownize path enriches selected files
through an OCR adapter only after network use has been enabled for the scope
or for the current command. The persistent task records a scope-relative
`input_path` and the raw content identity accepted when the task was created.
At execution time, the CLI again checks task state, secret policy, file
identity, size, media type, adapter policy, and available budget before it
enters the online adapter.

The relevant threat actor is not a remote HTTP client. It is a lower-trust
writer to a selected directory: for example, a collaborator, sync process, or
another local process that can rename a direct child while the operator runs
`index --online`, `batch resume`, or `batch retry`. The KCS store lock
serializes KCS's own store operations, but it does not freeze external changes
to the selected directory.

Two identities are intended to stay coupled throughout this workflow:

- the logical authorization identity, `task.input_hash`; and
- the exact bytes placed in the OCR request.

As we follow those values into the adapter layer, the request type does not
encode their coupling. `RawInput` stores a hash and an optional path as
independent values
(`crates/kcs-adapter/src/types.rs:79-83`):

```rust
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawInput {
    pub raw_hash: String,
    pub path: Option<String>,
}
```

This representation is safe only if every consumer either uses bytes already
bound to `raw_hash` or re-establishes the binding after opening `path`. The
Mistral consumer does neither.

Secret gating also makes the exact-byte invariant security-sensitive. Pending
tasks are filtered using their retained lexical path at
`crates/kcs-cli/src/main.rs:6050-6066`:

```rust
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

`classify_secret` classifies the filename and relative path. That is a useful
hold for stable content, but replacing the object named by an innocuous path
does not change the string being classified. The executor's later hash check
is consequently the last control that can bind the approved task to physical
bytes. Its result must survive all the way to the network serialization
boundary.

## Vulnerability Details

### The last correct check ends before the consuming read

The network-free precondition already reads the pathname, compares its hash,
and checks its length against `effective_max_input_bytes` at
`crates/kcs-cli/src/main.rs:6537-6551`. That buffer is also not passed to the
adapter. The executor then performs the final repeated identity check.

`execute_online_markdownize_task` performs a sound stale-task comparison at
`crates/kcs-cli/src/main.rs:6596-6605`. We first read the current pathname into
`current_bytes`, calculate its content identity, and reject it if it differs
from `task.input_hash`:

```rust
let Ok(current_bytes) = fs::read(&path) else {
    return Err(TaskExecutionFailure {
        retry_kind: RetryErrorKind::InvalidInput,
    });
};
if hash_bytes(&current_bytes) != task.input_hash {
    return Err(TaskExecutionFailure {
        retry_kind: RetryErrorKind::InvalidInput,
    });
}
```

The local variable is not carried forward. Instead, the next stage receives
the pathname and the asserted old hash at lines 6615-6621:

```rust
let prepare = prepare_units(PrepareStageRequest {
    raw_hash: task.input_hash.clone(),
    media_type: media_type.clone(),
    input_path: path.display().to_string(),
    tool_profile_hash: prepare_profile_hash,
})
.map_err(|_| TaskExecutionFailure {
    retry_kind: RetryErrorKind::InvalidInput,
})?;
```

`prepare_units` itself opens `input_path` again at
`crates/kcs-pipeline/src/prepare.rs:90`, but even a stable preparation does not
protect the later OCR read. For the clearest interleaving, we can keep A in
place through preparation and replace the directory entry only after that
stage. The subsequent full-send call at
`crates/kcs-cli/src/main.rs:6674-6691` still forwards only `H(A)` and the
mutable pathname:

```rust
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
.map_err(task_failure_from_adapter)?;
```

The incremental branch reaches the same catalog function at lines 6907-6920
with the same `task.input_hash` and `path`, so changing modes does not restore
the invariant.

### The request bridge preserves the mismatch

The catalog translates these fields directly into `RawInput` at
`crates/kcs-adapter/src/catalog.rs:82-101`:

```rust
pub fn run_standard_online_markdownize(
    request: StandardOnlineMarkdownizeRequest<'_>,
) -> Result<StandardOnlineMarkdownizeOutcome> {
    let adapter_request = MarkdownizeRequest {
        raw: RawInput {
            raw_hash: request.raw_hash.to_owned(),
            path: Some(request.path.display().to_string()),
        },
        media_type: request.media_type.to_owned(),
        prepared_unit_hint: Some(request.prepared_unit_hints),
        mode: request.mode,
        previous: request.previous,
        hints: request.hints,
        restrict_to_hint_pages: request.restrict_to_hint_pages,
        tool_profile_hash: String::new(),
        spec_version: 1,
    };
```

No buffer, open file, inode identity, or verified snapshot accompanies the
pair. If we carry this request into the concrete client, `raw_hash` is
therefore only an assertion.

### The production sink obtains and sends a new byte sequence

The decisive sink is `EnvMistralOcrClient::ocr_markdown` at
`crates/kcs-adapter/src/mistral_ocr.rs:112-138`:

```rust
fn ocr_markdown(&self, request: &MarkdownizeRequest, model_pin: &str) -> Result<OcrResponse> {
    let api_key = Self::api_key()?;
    let path = request.raw.path.as_deref().ok_or_else(|| {
        AdapterError::ContractViolation("Mistral OCR requires a local raw path".to_owned())
    })?;
    let bytes = std::fs::read(path).map_err(|err| AdapterError::Io {
        path: path.to_owned(),
        message: err.to_string(),
    })?;
    let pages = request_pages(request);
    let value: Value = ureq::post(&format!("{}/v1/ocr", self.base_url()))
        .set("Authorization", &format!("Bearer {api_key}"))
        .set("Content-Type", "application/json")
        .send_json(ocr_request_body(
            &request.media_type,
            &bytes,
            model_pin,
            pages.as_deref(),
        ))
        .map_err(http_error)?
        .into_json()
        .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
    parse_ocr_response(value, model_pin)
}
```

From here, the second `std::fs::read` resolves the pathname in its current
state.
`request.raw.raw_hash` is not referenced anywhere in the function. The
freshly read `bytes` are immediately base64-encoded into a `data:` URL by
`document_payload` at lines 287-300, then supplied to `send_json`. Because
serialization consumes this in-memory `Vec<u8>`, a change after line 117 no
longer matters; the exploitable transition is specifically the pathname
replacement before line 117.

We can express the complete state transition with two versions:

| Step | Pathname state | Identity or bytes used |
| --- | --- | --- |
| Task creation and approval | A | task records `H(A)` |
| Secret/media/network gates | A | lexical path and approved task |
| Executor's final read | A | verifies `hash(A) == H(A)` |
| Checked buffer is not carried onward | A | only path plus `H(A)` are used |
| Concurrent atomic replacement | B | pathname now resolves to B |
| Mistral client read and request | B | request body contains B; no hash check |
| Normalized persistence | B-derived response | records still use `H(A)` |

The final integrity consequence appears at
`crates/kcs-cli/src/main.rs:6714-6722`, where normalized units are created with
the old task identity:

```rust
let mut units = normalized_units_from_response(
    &response,
    &prepare.prepared_units,
    previous.as_ref(),
    &task.input_hash,
    &profile.tool_profile_hash,
    MarkdownizeMode::Full,
    &generated_at,
)
.map_err(|_| TaskExecutionFailure {
    retry_kind: RetryErrorKind::ContractViolation,
})?;
```

The manifest is likewise built with `task.input_hash` at lines 6770-6784 and
persisted at lines 6785-6789. A successful substituted response is therefore
not merely transient: KCS presents OCR derived from B as enrichment for A.

## Exploitability Analysis

For the strongest practical attempt, we start with an OCR-eligible direct
child such as `selected.pdf` in a directory writable by both the operator and
a lower-trust contributor. Version A must remain stable long enough to create
an eligible task and pass the execution-time checks. The contributor then
needs an atomic directory-entry replacement after the hash comparison and
before the client read. Atomic rename is preferable to modifying the file in
place: the adapter sees either complete A or complete B, avoiding torn input
that would simply produce an I/O or provider parsing failure.

There are two useful payload routes:

1. **Controlled regular-file replacement.** The contributor replaces A with a
   different OCR-compatible B. This route proves the authorization and
   provenance failure with the fewest assumptions. Here we control bytes that
   cross the provider boundary without being covered by the operator's task
   identity or secret decision. Its confidentiality value depends on what B
   contains and who already knows it, but the false `H(A)` provenance is
   direct.

2. **Symlink replacement to a victim-readable file.** On systems where the
   contributor can create the link, `std::fs::read` follows it. If we place
   that link only after the initial `entry.file_type().is_file()` check at
   `crates/kcs-pipeline/src/scan.rs:110-112`, the lexical
   task path remains an innocuous scope-local filename while the final lookup
   can resolve elsewhere. If the target is readable by the invoking KCS user,
   its bytes can enter the request even when the contributor could not read
   them directly. The request labels the bytes with A's extension-derived
   media type, so the provider may reject an incompatible target, but the
   disclosure has already occurred once the authenticated body is received.
   I did not validate a sensitive target, Windows link semantics, or provider
   behavior for a MIME-mismatched payload, so this is a source-supported
   escalation route rather than a reproduced result.

The race window is not limited to adjacent source lines. After the executor
check, KCS reparses the path for preparation, performs incremental mapping and
prior-instance checks where applicable, may resolve a mutable model alias,
and only then reaches the final read. We can repeatedly exchange A and B to
improve the chance of landing in that interval, but doing so also
risks presenting B to either of the two earlier hash checks, which correctly
retire the task. A synchronized test seam would make the ordering
deterministic; production exposes no such barrier, so real success rates
remain dependent on scheduling, filesystem behavior, and the work performed
between the check and sink.

Several existing controls materially limit the result:

- A replacement present during either execution-time hash check is rejected.
- The file must already have an eligible online Markdownize task, an
  OCR-supported filename/media type, explicit network permission, provider
  configuration, available budget, and operator-driven execution.
- The destination is configured by the operator. The path writer does not
  gain an arbitrary URL or receive the Mistral bearer token.
- A lost race, unreadable target, I/O error, or provider-side rejection
  prevents useful OCR output. Provider rejection does not necessarily undo
  disclosure of a request body already received.
- One winning execution affects one task, one provider request, and one
  normalized identity in one selected scope. The trace does not establish
  code execution, a persistent daemon compromise, or broad credential loss.

The repository's test adapter is also an informative dead end. The
`KCS_TEST_MISTRAL_OCR=mock` seam synthesizes pages from prepared hints and does
not perform the production path read. Existing end-to-end tests using that
mode can pass while the real client remains vulnerable. A regression must
place the identity check in a helper shared by the real and local-capture
paths, or inject a client that actually consumes the final bytes.

The confidentiality boundary is important enough to treat the impact as
high, while likelihood is medium because the attacker needs a mutable shared
scope, a live approved online task, and a favorable unmeasured interleaving.
That combination yields **Medium / P2** rather than High. The rating does not
depend on claiming API-key theft or an attacker-controlled endpoint.

## Proof of Concept

The accompanying
`poc/ocr_final_hash_reopen_regression.py` is a bounded, credential-free
adapter-seam regression. It uses Python's standard library only and performs
the following local sequence:

1. write approved PDF-like bytes A to a temporary selected pathname;
2. calculate the same `sha256:<lower-hex>` identity format KCS uses;
3. read and verify A, modeling `main.rs:6596-6605`;
4. atomically replace the pathname with PDF-like bytes B using `os.replace`;
5. let the vulnerable client model reopen the path and deliver its body to an
   in-memory capture seam; and
6. assert that a fixed client rejects the mismatch before that seam, while a
   stable-A control still succeeds.

Run it from this report directory:

```sh
python3 poc/ocr_final_hash_reopen_regression.py
```

I ran that command with Python 3. It produced:

```text
approved_hash=sha256:4228e28ce7f955dce0a8f66ef17549a4c598261aa225b1c380b936c5f1fd1756
replacement_hash=sha256:163794a26042ff14c52f54bd0a372403c9ccb185053b66eb4fb0fc81bc8d2b6f
executor_checked_bytes=37
vulnerable_capture=replacement bytes=True
fixed_result=identity_mismatch
fixed_capture_count=0
stable_control=accepted
network_calls=0 credential_reads=0 status=pass
```

The important differential is that the vulnerable capture receives B even
though the request still carries `H(A)`, whereas the binding oracle leaves its
capture empty. The stable control guards against a fix that simply disables
OCR.

This is deliberately a local model of the exact check/reopen boundary, not an
end-to-end exploit. It does not import KCS internals, invoke the CLI, inspect
environment credentials, start a loopback server, or contact a provider. Its
temporary directory is removed automatically. It therefore establishes the
byte-identity invariant and supplies a deterministic regression shape without
claiming a measured production race or a captured real request.

## Remediation

The invariant to restore is simple: **the byte sequence checked against the
approved raw hash must be the same byte sequence serialized into the OCR
request**. A path and a hash are not a verified document. That invariant must
be enforced at, or below, the last component capable of sending the request.

The smallest defensive patch is to hash the client's fresh buffer before any
POST and use that same buffer for request construction. In
`EnvMistralOcrClient::ocr_markdown`, the essential change is:

```rust
let bytes = std::fs::read(path).map_err(|err| AdapterError::Io {
    path: path.to_owned(),
    message: err.to_string(),
})?;

let actual_hash = hash_bytes(&bytes);
if actual_hash != request.raw.raw_hash {
    return Err(AdapterError::ContractViolation(format!(
        "OCR input identity changed: expected {}, got {actual_hash}",
        request.raw.raw_hash
    )));
}

// `bytes` is now both verified and the only buffer passed to the body builder.
let body = ocr_request_body(
    &request.media_type,
    &bytes,
    model_pin,
    pages.as_deref(),
);
```

This closes the final check-to-send gap because no pathname lookup occurs
between `hash_bytes(&bytes)` and serialization of `bytes`. A dedicated
`AdapterError::InputIdentityMismatch` mapped to the task's non-retryable
`InvalidInput` state would be cleaner than overloading `ContractViolation`.
The caller should also reclaim any pre-send reservation for this case: no OCR
request was issued, so retaining a billed reservation would create a phantom
charge.

The stronger structural fix is to stop reopening the path at all. Pass
`current_bytes` onward after `main.rs:6596-6605` through
`StandardOnlineMarkdownizeRequest` as a verified byte slice or immutable
`Arc<[u8]>`, and make the production client accept bytes rather than a path.
The catalog can assert the hash once more as defense in depth:

```rust
pub struct StandardOnlineMarkdownizeRequest<'a> {
    pub raw_hash: &'a str,
    pub verified_raw_bytes: &'a [u8],
    // existing scope, media, hint, and mode fields...
}

if hash_bytes(request.verified_raw_bytes) != request.raw_hash {
    return Err(AdapterError::InputIdentityMismatch {
        expected: request.raw_hash.to_owned(),
        actual: hash_bytes(request.verified_raw_bytes),
    });
}

client.ocr_markdown(&adapter_request, model_pin, request.verified_raw_bytes)?;
```

KCS already allocates the whole checked file and enforces a configured input
cap, so carrying that buffer avoids another read without introducing a new
unbounded allocation. If a descriptor-based abstraction is preferred, open a
regular file with no-follow semantics, read and hash it once, and pass the
resulting immutable bytes onward. Merely comparing inode metadata and then
reopening the name would create another TOCTOU boundary.

The fix needs deterministic tests at the real consumption seam:

- **Post-check rename:** pause after the executor verifies A, atomically
  replace the pathname with B, resume, and assert an identity-mismatch error
  before the capture transport receives any body.
- **Stable control:** leave A unchanged and assert the exact checked bytes are
  captured once.
- **Symlink substitution:** on platforms that support it, replace the direct
  child with a link after verification and assert no target bytes reach the
  transport.
- **All online modes:** run the same assertion for a fresh full send,
  incremental send, and unit-scoped retry; all three reach the shared catalog
  and must use the same verified-byte helper.
- **Task and cost state:** ensure a mismatch is non-retryable/superseded,
  creates no normalized instance under the old hash, and leaves no billed
  reservation.
- **Mock parity:** make the local mock/capture seam execute the shared
  byte-binding helper so production-only path behavior cannot disappear from
  tests.
- **Nearby mutation cases:** cover same-size B, larger B, deletion, unreadable
  replacement, and a rapid A/B exchange. Size equality must not bypass the
  hash, and every error path must fail before transport.

These tests should use temporary files and an injected in-memory transport;
they need neither an API key nor a real or loopback service. The included
regression provides the core rename and stable-file assertions in that safe
form.

## Summary

KCS correctly checks an online task's current bytes against its approved
identity, but then loses the result and reconstructs the document from a
mutable pathname inside the Mistral client. If a lower-trust directory writer
changes that name during the remaining interval, we can carry `H(A)` through
every approval control while the provider receives B and KCS persists the
response as enrichment for A.

The bounded local regression demonstrates the state transition without a
service or credentials; it does not claim a measured production win rate or
a sensitive-file disclosure. Those constraints, plus explicit online opt-in
and an operator-configured destination, keep the final rating at
**Medium / P2**.

The immediate fix is a hash comparison over the exact final buffer before any
transport call. The preferable design is to pass the executor-verified bytes
through the adapter boundary and eliminate the sink's pathname reopen. Future
variant analysis should treat every API that carries an asserted content hash
beside a mutable path as suspect: a check is only effective when the checked
object, not merely its name, reaches the consuming boundary.
