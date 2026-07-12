# Prepare-stage reopen can poison prepared CAS identity

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` can publish a
prepared content-addressed object under a name derived from one read while
writing bytes from an earlier read. During ordinary local indexing, the CLI
reads a selected-scope file, verifies the bytes against the scan-time raw
hash, then passes only the mutable pathname into `prepare_units()`. The
prepare stage reopens that pathname and derives prepared hashes from the
later bytes, but `write_prepared_objects()` still receives and writes the
earlier byte buffer.

If a lower-trust contributor can replace the selected-scope path in that
small post-check window, we can end up with an object path named for version
B while the object body contains version A. That breaks the prepared CAS
identity boundary for one scope and can make later indexing, evidence, or
search consumers trust a prepared object whose name does not describe its
contents. The validated final severity is Low/P3: the impact is real data
integrity loss, but it is local, race-dependent, bounded to a selected
scope, and recoverable by rebuilding stable state.

I reviewed the vulnerable revision directly and ran only a local synthetic
regression probe that models the two-read invariant. I did not run a
barrier-controlled replacement inside a live `.kcs` store, and I did not use
credentials, external services, or real target data.

## Background

KCS indexes files from an operator-selected root into a local `.kcs` store.
For each candidate, the index path is expected to preserve a simple
content-addressing invariant: the bytes used to derive a `sha256:` object
name should be the bytes later written at that object name. That invariant
matters because later consumers treat the prepared object namespace as
authoritative, not as a best-effort cache keyed by a nearby file state.

The relevant path starts in the CLI index pipeline. KCS first reads the
candidate and verifies that the bytes match the scan-time raw hash:

```rust
// crates/kcs-cli/src/main.rs:9077-9109
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
```

That check is a useful control, but it only protects the first read. Once we
carry `input_path` instead of a verified byte buffer or stable descriptor into
the prepare stage, a second open becomes security-relevant.

## Vulnerability Details

The prepare request contains both `raw_hash` and `input_path`, so a reader
might expect `prepare_units()` to bind its input to the hash the caller just
verified. It does not. The function reopens the path and derives
`prepared_hash` values from the bytes returned by that later open:

```rust
// crates/kcs-pipeline/src/prepare.rs:41-46,72-103
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
    if !is_text_native && !is_pdf && !bytes_are_text(&bytes) {
        return Ok(PrepareStageOutput {
            prepared_object_hashes: Vec::new(),
            prepared_units: Vec::new(),
            image_object_hashes: Vec::new(),
        });
    }
    let prepared_hash = hash_bytes(&bytes);
```

From here, we have two byte buffers with different security meanings. The
CLI's `bytes` buffer is version A, already checked against the scan state.
The prepare-stage `bytes` buffer can be version B if the pathname changed
after the first read. `PrepareStageRequest.raw_hash` is declared, but the
validated source trace found no comparison between that field and the
prepare-stage read.

The mismatch becomes durable when the caller writes prepared objects. The
caller passes the original `bytes` from the first read into
`write_prepared_objects()`, while it passes `prepare.prepared_object_hashes`
from the second read:

```rust
// crates/kcs-cli/src/main.rs:9112-9118
write_prepared_objects(
    repo,
    &prepare.prepared_units,
    &prepare.prepared_object_hashes,
    &bytes,
    &candidate.media_type,
)?;
```

The writer then derives the destination path from each prepared hash and
writes `object_bytes` from the earlier caller buffer for text/native single
unit content:

```rust
// crates/kcs-cli/src/main.rs:9505-9541
fn write_prepared_objects(
    repo: &Repository,
    prepared_units: &[PreparedUnit],
    prepared_hashes: &[String],
    bytes: &[u8],
    media_type: &str,
) -> Result<()> {
    let pdf_pages = (media_type == "application/pdf").then(|| pdf_text_pages(bytes));
    for (index, prepared_hash) in prepared_hashes.iter().enumerate() {
        let digest = prepared_hash
            .strip_prefix("sha256:")
            .ok_or_else(|| KcsError::schema("prepared hash must use sha256 prefix"))?;
        let path = repo
            .kcs_dir()
            .join("objects/prepared")
            .join(&digest[0..2])
            .join(&digest[2..4])
            .join(prepared_hash);
        if !path.exists() {
            let object_bytes = pdf_pages
                .as_ref()
                .and_then(|pages| pages.get(index))
                .map(|page| page.as_bytes())
                .or_else(|| {
                    prepared_units
                        .get(index)
                        .and_then(|unit| (unit.unit_type == UnitType::Page).then_some(b"" as &[u8]))
                })
                .unwrap_or(bytes);
            atomic_write_cas_object(&path, object_bytes)?;
        }
    }
    Ok(())
}
```

For a simple text file, `unwrap_or(bytes)` is the decisive line. If prepare
reopened version B, `prepared_hash` names B, but the bytes written are still
version A. The atomic write helper protects publication from torn writes; it
does not check that `sha256(object_bytes)` equals the `sha256:` name.

There is one more subtle guard to account for: `if !path.exists()` skips an
already-existing prepared object. That prevents overwriting a correct object
that is already present, but it also means the first raced publication can
seed a wrong object that later stable runs will not automatically replace
unless the store is rebuilt or the object is explicitly repaired.

## Exploitability Analysis

The strongest realistic route is a local selected-root race. We need a file
that the operator has selected for indexing and a lower-trust actor who can
rename or rewrite that path during the index run. The actor lets version A
survive long enough for the CLI read and hash comparison, then replaces the
path with version B before `prepare_units()` performs its own
`std::fs::read()`.

For text-like media, the resulting primitive is clean:

1. the scan/current check accepts A;
2. prepare derives `sha256(B)`;
3. prepared CAS publication writes A to the path for `sha256(B)`;
4. later consumers can see a prepared object whose name and body disagree.

That is useful as a provenance and integrity primitive, not as a direct code
execution primitive. We can make a downstream component believe a prepared
object for B exists while the bytes are A. Depending on consumer behavior,
that can cause stale evidence, failed verification, confusing search results,
or persistent rebuild churn. The saved attack-path analysis did not prove a
confidentiality boundary, an outside-scope write, or arbitrary code execution,
so we should not overstate it.

PDFs add a slightly different shape. `prepare_units()` may derive per-page
hashes from the reopened bytes, while `write_prepared_objects()` computes
`pdf_pages` from the earlier buffer. That broadens the mismatch from a
single whole-file object to page-level objects, but it also increases
reliability constraints because page extraction must produce compatible page
counts and text layers. The text case is the best regression target because
it isolates the violated invariant without making the result depend on PDF
parser behavior.

The main reliability constraint is scheduling. The validated scan artifacts
did not identify a public barrier between line 9090's hash comparison and
line 9104's `prepare_units()` call. In practice, a synchronized filesystem,
editor, or shared folder could supply replacement timing, but without a
test seam this remains a race-dependent integrity issue. That is why the
calibrated severity is Low/P3 despite the clear source mismatch.

## Proof of Concept

The included PoC is a local, synthetic regression probe. It does not race the
real CLI and does not touch a `.kcs` store. Instead, it models the exact
state transition we care about: the caller retains version A, prepare derives
the prepared object name from version B, and publication writes A at the path
named for B.

Run it from this report directory:

```sh
cd poc
make
```

Representative output:

```text
[+] first read accepted version A
[+] prepare-stage reopen derived sha256:b2bcf2178491b9d37bea5d41227350d9dc89cbc4c28ac8e30ad78656cb13827d from version B
[+] publication wrote caller-retained version A under B's prepared hash
[+] mismatch reproduced: object name expects b2bcf2178491b9d3..., body hashes to 69c0e2bbc06a8709...
[+] fixed invariant would reject before publication or write bytes that hash to the object name
```

The probe is intentionally non-destructive. It uses temporary directories,
synthetic byte strings, and local SHA-256 calculations. A fixed KCS design
should make this state impossible by either passing the already-verified
bytes into prepare, reopening through a stable descriptor and revalidating,
or checking `sha256(object_bytes) == prepared_hash` immediately before
publication.

## Remediation

The invariant to restore is direct: the bytes that determine a prepared
object name must be the same bytes published at that name. KCS can enforce
that invariant at more than one layer, but the best minimal fix is to stop
passing a mutable pathname across the check/use boundary. Prepare should
consume the caller-verified bytes or a stable file descriptor, not reopen
`request.input_path`.

One minimal shape is:

```rust
pub struct PrepareStageRequest<'a> {
    pub raw_hash: String,
    pub media_type: String,
    pub input_path: String,
    pub input_bytes: &'a [u8],
    pub tool_profile_hash: String,
}

pub fn prepare_units(request: PrepareStageRequest<'_>) -> Result<PrepareStageOutput> {
    let bytes = request.input_bytes;
    if hash_bytes(bytes) != request.raw_hash {
        return Err(PipelineError::contract(
            "prepare input bytes do not match raw hash",
        ));
    }
    // derive prepared_hash and per-page hashes from `bytes`
}
```

If ownership or API boundaries make borrowed bytes inconvenient, an
equivalent fix is to carry an opened descriptor with `O_NOFOLLOW`/same-inode
checks and rehash before prepare output is accepted. A second defensive layer
should live in `write_prepared_objects()`: before `atomic_write_cas_object()`,
compute `hash_bytes(object_bytes)` and reject if it does not match the
destination `prepared_hash`. That check would catch this bug and similar
future mismatches even if another call path accidentally supplies divergent
hashes and bytes.

Regression tests should cover:

- a text candidate where prepare is forced to see bytes different from the
  caller's checked buffer, expecting rejection rather than publication;
- a PDF candidate where per-page prepared hashes are verified against the
  page bytes actually written;
- an existing-object case where a stale object with mismatched content is
  detected and repaired or quarantined instead of silently skipped.

## Summary

This issue exists because KCS verifies one byte buffer but then hands a
mutable pathname to the prepare stage. We can carry one file version into the
hash comparison, a second file version into prepared hash derivation, and the
first version back into prepared object publication. The result is a
recoverable but persistent prepared CAS identity mismatch inside one selected
scope.

The useful future research area is variant analysis across every path that
passes both a content hash and a pathname. Any stage that derives authority
from a hash but later reopens the path should either consume the checked
bytes, carry a stable descriptor, or validate the bytes again at the final
sink.
