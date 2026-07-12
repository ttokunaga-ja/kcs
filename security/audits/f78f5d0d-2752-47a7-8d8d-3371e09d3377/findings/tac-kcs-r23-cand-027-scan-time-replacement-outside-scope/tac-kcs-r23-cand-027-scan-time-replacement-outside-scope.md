# Scan-time replacement can authorize an outside-scope file under a benign name

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` contains a local
TOCTOU scope-escape in the `kcs index` path. During a non-preview index, the
scanner observes a direct child as a regular file and derives policy decisions
from its benign relative name, but it later reopens the mutable pathname to
compute the accepted raw hash. If a lower-trust writer can replace that child
with a symlink after the regular-file check and before the read, KCS can bind
an outside, victim-readable file to the benign in-scope name.

The later index pipeline hash check does not close this interleaving. It
compares a second read against the scan hash, but the scan hash can already
belong to the substituted outside target. From there, preparation and online
OCR paths continue to carry a mutable path rather than a descriptor-bound file
identity or verified byte buffer. The practical result is a medium-severity
confidentiality issue: one outside file per successful race can be archived or
normalized under an in-scope identity, and OCR-eligible content can be sent to
the configured OCR provider if the ordinary online controls are also satisfied.

I reviewed the vulnerable revision directly, traced the affected source paths,
and ran the included local/offline synthetic PoC. I did not run a live timing
race against KCS, use real credentials, read a real private target, or send any
network request. No fixed revision was supplied with the finding material.

## Background

KCS indexes a selected local scope. A realistic lower-trust actor for this bug
is a contributor who can write and rename entries in that selected directory,
while KCS itself runs as a victim user that may be able to read files outside
the selected scope. The security invariant we need is simple: once KCS decides
that a direct child is eligible, the bytes consumed later must be the same file
that satisfied the direct-child, regular-file, size, media, and secret-policy
checks.

The normal non-preview `index` command asks the scanner to include raw hashes:

```rust
let preview = build_scan_preview(ScanPreviewRequest {
    scope_path: repo.root().display().to_string(),
    include_raw_hashes: !args.preview,
    require_network_approval: !args.offline,
})
.map_err(pipeline_to_kcs)?;
```

That scan preview is then used by the rest of the indexing pipeline. We
therefore care about what exactly the preview binds together: the relative
name, the file type, the media type, the secret decision, and the raw content
hash.

## Vulnerability Details

The scanner iterates direct children and first asks the directory entry for a
file type:

```rust
for entry in std::fs::read_dir(scope_path).pipeline_io(scope_path)? {
    let entry = entry.pipeline_io(scope_path)?;
    let name = match entry.file_name().into_string() {
        Ok(name) => name,
        Err(_) => continue,
    };
    if name == ".kcs" || name == ".kcsignore" {
        continue;
    }
    let path = entry.path();
    if is_xdg_state_inside_scope(scope_path, &path) {
        continue;
    }
    let file_type = entry.file_type().pipeline_io(&path)?;
    if !file_type.is_file() {
        continue;
    }
    let relative = path
        .strip_prefix(scope_path)
        .unwrap_or(&path)
        .to_string_lossy()
        .replace('\\', "/");
```

At this point, a symlink that already existed as the direct child is skipped.
The problem is that the result is not tied to an open file descriptor or inode
identity. If the directory writer replaces the entry immediately after this
check, the following code keeps the old benign `relative` string while later
path operations can follow the replacement:

```rust
let size_bytes = entry.metadata().pipeline_io(&path)?.len();
let secret = classify_secret(&relative);
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
let quarantine_reason = match secret {
    Some(SecretTier::TierA) if ignored => Some("secrets_tier_a_excluded".to_owned()),
    Some(SecretTier::TierA) => Some("secrets_tier_a_online_hold".to_owned()),
    Some(SecretTier::TierB) => Some("secrets_tier_b_warning".to_owned()),
    _ => None,
};
let raw_hash = if include_raw_hashes && !ignored {
    Some(hash_bytes(&std::fs::read(&path).pipeline_io(&path)?))
} else {
    None
};
candidates.push(ScanCandidate {
    input_path: relative.clone(),
    media_type: media_type_for_path(&path).to_owned(),
    size_bytes,
    raw_hash,
    ignored,
    quarantine_reason,
});
```

We now have the bad binding. `input_path`, secret classification, and media
classification still describe `quarterly-summary.pdf` or a similar harmless
direct-child name. The `raw_hash`, however, can be computed by following a new
symlink to a file outside the selected scope. That is enough to defeat the
later index-time hash comparison.

The pipeline rereads the path and rejects candidates whose current bytes do
not match the scan hash:

```rust
let secrets_hold = !secrets_approved && classify_secret(&candidate.input_path).is_some();
let path = repo.root().join(&candidate.input_path);
let bytes = fs::read(&path)
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
let current_hash = hash_bytes(&bytes);
if let Some(scan_hash) = &candidate.raw_hash {
    if scan_hash != &current_hash {
        append_event_log(
            "KCS-I-INDEX-INPUT-CHANGED-001",
            "input file changed between scan and normalize; skipped to preserve \
             content-addressing (re-run index)",
            json!({ "input_path": candidate.input_path }),
        )?;
        result.failed_files += 1;
        continue;
    }
}
let raw_hash = current_hash;
let prepare = prepare_units(PrepareStageRequest {
    raw_hash: raw_hash.clone(),
    media_type: candidate.media_type.clone(),
    input_path: path.display().to_string(),
    tool_profile_hash: prepare_profile_hash.clone(),
})
.map_err(pipeline_to_kcs)?;
```

That check is useful for ordinary edits between scan and normalize, but it is
not a containment check. If the symlink remains pointed at the same outside
target, the current hash equals the scan hash because both reads consumed the
outside target. Meanwhile, `secrets_hold` is still decided from the benign
`candidate.input_path`, not from the physical target.

Preparation then receives only `input_path` and independently opens it again:

```rust
pub struct PrepareStageRequest {
    pub raw_hash: String,
    pub media_type: String,
    pub input_path: String,
    pub tool_profile_hash: String,
}

pub fn prepare_units(request: PrepareStageRequest) -> Result<PrepareStageOutput> {
    let media_type = request.media_type.as_str();
    let is_text_native = matches!(media_type, "text/markdown" | "text/plain" | "text/x-code");
    let is_pdf = media_type == "application/pdf";
    if !is_text_native && !is_pdf && media_type != "application/octet-stream" {
        return Ok(PrepareStageOutput {
            prepared_object_hashes: Vec::new(),
            prepared_units: Vec::new(),
            image_object_hashes: Vec::new(),
        });
    }
    let bytes = std::fs::read(&request.input_path).pipeline_io(Path::new(&request.input_path))?;
```

For an OCR-eligible file, the deferred online path repeats the same pattern.
The executor performs another hash check, prepares from the path, and then
passes the same mutable path to the standard online markdownize wrapper:

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

The Mistral OCR client finally reads `request.raw.path` immediately before
constructing the request body:

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
```

The decisive issue is not that KCS lacks a hash check entirely. The issue is
that the first accepted hash can already be the outside target's hash while the
authorization identity is still the in-scope benign name. Later equality checks
then compare the outside file to itself.

## Exploitability Analysis

The strongest route is a local shared-directory race. We start with a regular
file under a harmless name such as `quarterly-summary.pdf`. KCS observes it as
a direct child and carries the relative path into the secret and media checks.
The attacker then atomically replaces the entry with a symlink to a known file
that the KCS process can read but the attacker cannot read directly. When the
scanner hashes the path, it follows the replacement. If the link remains in
place, the later index read follows the same replacement and the hash equality
passes.

What we gain is a confused-deputy read under a false identity. The outside file
is treated as if it were the benign direct child. For local processing, that
can place outside bytes into raw or prepared KCS state associated with the
benign path. For OCR-eligible media, it can also reach the OCR adapter, but
only after the normal online requirements are met: adapter configuration,
credential availability, network approval, budget, media eligibility, and task
execution. This is why the practical severity is medium rather than high even
though the confidentiality impact can be serious for the selected file.

The route has useful constraints that keep the finding bounded:

- A symlink present before `entry.file_type()` is skipped.
- A later change to different bytes is rejected by the scan-hash comparison.
- The attacker needs rename authority in the selected scope and must win a
  timing window.
- The target must be readable by the victim process.
- The online OCR outcome is not automatic; it depends on ordinary online
  controls and an OCR-eligible target.

Those constraints also shape the best exploitation strategy. We do not need a
second post-acceptance swap for this finding. The more reliable approach is to
leave the replacement symlink pointing at the same outside target so every
later path-based hash check continues to see the same bytes. A separate
post-check replacement would exercise a different race class and is not needed
to prove this authorization mismatch.

The main uncertainty is race reliability. The affected window is real in
source because there is no descriptor-bound open across the check and the read,
but I did not measure how often an attacker can win it in a live KCS run on a
specific filesystem. Practical exploitability will depend on scheduling,
filesystem behavior, and how much control the contributor has over repeatedly
triggering index operations.

## Proof of Concept

The included PoC is a deterministic local model of the vulnerable interleaving.
It creates a synthetic selected scope, a synthetic outside target, observes a
benign regular direct child, replaces the child with a symlink, and then
computes both the scan-time and index-time hashes through the same path. It
does not execute KCS, contact Mistral, use credentials, or read any real
private file.

Run it from this report directory:

```sh
cd poc
make run
```

Representative output from the included run:

```text
sh ./scan_time_replacement_poc.sh
[+] setup complete with a synthetic selected scope and synthetic outside target
[+] phase 1: observed quarterly-summary.pdf as a regular direct child
[+] phase 1: benign identity secret_hold=no media_type=application/pdf
[+] phase 2: replaced the direct child with a symlink to the outside target
[+] phase 3: scan raw_hash=sha256:bfe7ed99e9302d234603d9a086ead544c12cbec67fa7bb67134222bb2753405f
[+] phase 4: later index hash matched the scan hash
[+] result: accepted identity=quarterly-summary.pdf content_source=outside target
[+] result: synthetic outside marker reached through the benign path
```

The PoC intentionally stops at the authorization state. It shows why the later
hash comparison accepts the same outside target under the benign name, which is
the core primitive for this candidate.

## Remediation

The invariant to restore is that KCS must classify, size-check, hash, prepare,
and send exactly the same file identity. Pathname checks should not authorize a
later pathname read. The minimal repair is to open each direct child with a
no-follow, descriptor-bound operation, verify that descriptor is a regular file
inside the selected scope, read from that descriptor, and carry either the
verified bytes or a stable file identity into later stages.

A Unix-oriented sketch of the scan-side helper is:

```rust
use std::fs::OpenOptions;
use std::io::Read;
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;

fn read_regular_child_no_follow(path: &Path) -> Result<(Vec<u8>, u64)> {
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .pipeline_io(path)?;
    let metadata = file.metadata().pipeline_io(path)?;
    if !metadata.is_file() {
        return Err(PipelineError::Schema("candidate is not a regular file".to_owned()));
    }
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes).pipeline_io(path)?;
    Ok((bytes, metadata.len()))
}
```

The exact platform abstraction can vary, but the important part is the data
flow: `collect_direct_candidates()` should compute `size_bytes`, `raw_hash`,
and any content-derived decision from the opened object, not from a later path
open. `run_index_pipeline()` should then either consume the same verified
buffer or repeat the same no-follow descriptor-bound open and reject identity
changes. `prepare_units()` and the online OCR path should be refactored to
accept verified bytes or a held descriptor, rather than reopening
`input_path`.

Regression coverage should include:

- A scanner test with a controlled replacement between file-type observation
  and read, asserting that a replacement symlink cannot supply `raw_hash`.
- An index-pipeline test where the scan hash belongs to a replaced outside
  target, asserting that the candidate is rejected rather than accepted under
  the benign name.
- A preparation test proving that `prepare_units` consumes caller-verified
  bytes and does not reopen a mutable path.
- An OCR-adapter test with a mock client proving that the adapter body is built
  from verified bytes or from a still-bound descriptor identity.
- A negative test confirming that stable symlinks remain skipped and ordinary
  regular files still index normally.

## Summary

The bug is a pathname binding failure across the KCS scan and index pipeline.
We first authorize a regular direct child by name, but then compute the accepted
hash by reopening a mutable path. A lower-trust writer who wins that interval
can make KCS adopt an outside victim-readable file under a benign in-scope
identity, after which later hash checks compare the outside file to itself.

The included PoC demonstrates the core state transition offline with synthetic
files. The fix should remove pathname reopening as an authorization primitive:
bind checks and bytes to one no-follow file identity, carry that identity or
the verified bytes through preparation and OCR, and test the race directly so
future refactors cannot reintroduce the same mismatch.
