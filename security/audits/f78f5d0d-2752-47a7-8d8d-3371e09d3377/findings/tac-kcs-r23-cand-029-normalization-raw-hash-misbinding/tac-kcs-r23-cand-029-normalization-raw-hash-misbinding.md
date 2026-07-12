# Deterministic normalization persists a later path read under the earlier raw hash

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` has a
path-based time-of-check/time-of-use gap in deterministic normalization. During
`kcs index`, the CLI reads a candidate file, verifies that the read bytes still
match the scan-time hash, and assigns that value as `raw_hash`. The later
preparation and deterministic markdownization stages then receive a mutable
pathname rather than the verified byte buffer. If a lower-trust writer in the
selected root replaces that pathname after the hash check and before the
deterministic adapter reads it, KCS can persist normalized text from version B
under the raw identity of version A.

I reviewed the vulnerable revision and the final attack-path calibration
directly, and I ran only the included local/offline synthetic PoC; I did not
run a scheduler-controlled race against a live KCS store or any network-backed
adapter. The validated impact is durable false provenance in one selected
scope's normalized/search/evidence state. It does not require network egress,
does not write outside the attacker's existing directory authority, and can be
repaired by rebuilding from stable content, so the final policy severity is
Low/P3 despite high confidence in the source trace.

No fixed revision was supplied with this material. The affected state is the
reviewed revision and any build with the same invariant: raw hashing,
preparation, deterministic markdownization, and normalized persistence are not
all bound to one verified byte source or stable descriptor.

## Background

KCS treats a selected root as an operator-approved scope. A normal deterministic
indexing pass scans direct children, computes or verifies raw object identity,
derives prepared units, runs a markdownization adapter, and writes normalized
units plus a manifest into the authoritative `.kcs` store. The important
security invariant is simple: when KCS records normalized content under a
`raw_hash`, that content must have been derived from the same bytes that
produced the `raw_hash`.

The relevant attacker is a lower-trust contributor with concurrent write or
rename authority inside the selected root. They do not need direct access to
private KCS state and they do not need a listener or public ingress; they need
the operator to run deterministic indexing while the shared pathname remains
mutable. We start from ordinary text or code content because the deterministic
adapter can read it locally. PDF text layers have an additional per-page reopen,
but text is enough to prove the binding failure.

The adapter request format separates identity from location. `RawInput` carries
a caller-provided `raw_hash` and an optional path:

```rust
// crates/kcs-adapter/src/types.rs
pub struct RawInput {
    pub raw_hash: String,
    pub path: Option<String>,
}
```

That shape is not automatically unsafe. It becomes unsafe when downstream code
trusts `raw_hash` as the identity while still deriving source text from a later
path read.

## Vulnerability Details

The deterministic indexing path first does the right defensive thing for
ordinary edits: it reads the file and compares the current bytes to the
scan-time candidate hash. We reach this point with an attacker-controlled
pathname under the selected root, but KCS still has a concrete byte buffer in
hand:

```rust
// crates/kcs-cli/src/main.rs:9076-9109
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
```

If the attacker swaps the file before this read, the comparison against
`candidate.raw_hash` detects the change and the candidate is skipped. The gap
opens immediately after `raw_hash` is assigned. KCS retains `bytes` for
prepared/raw object writes, but the preparation call is already based on
`input_path`:

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

Preparation then reopens the path. In the strongest interleaving for this
finding, the attacker waits until preparation completes, so the prepared unit
identity still describes version A. This source still matters because it shows
the design pattern: `raw_hash` is available, but a fresh pathname read supplies
the next stage's bytes.

```rust
// crates/kcs-pipeline/src/prepare.rs:72-103
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

After preparation, the CLI constructs the markdownization request from two
independent facts: the earlier `raw_hash` and the still-mutable path.

```rust
// crates/kcs-cli/src/main.rs:9282-9304
let request = MarkdownizeRequest {
    raw: RawInput {
        raw_hash: raw_hash.clone(),
        path: Some(path.display().to_string()),
    },
    media_type: candidate.media_type.clone(),
    prepared_unit_hint: Some(hints),
    mode: adapter_mode(mode),
    previous: (mode == MarkdownizeMode::Incremental)
        .then_some(adapter_previous)
        .flatten(),
    hints: (mode == MarkdownizeMode::Incremental)
        .then(|| adapter_hints(&incremental_hints)),
    restrict_to_hint_pages: false,
    tool_profile_hash: markdown_profile_hash.clone(),
    spec_version: 1,
};

let mut response = markdown_adapter
    .markdownize(request.clone())
    .map_err(adapter_to_kcs)?;
```

Inside the deterministic adapter, `raw_hash` helps choose default hints, but it
does not bind the source text. We carry the request into `read_source_text()`,
which opens `request.raw.path` again and returns lossy UTF-8 text. For PDF, a
later page helper can reopen the same path again, but the plain text path
already proves the issue.

```rust
// crates/kcs-adapter/src/deterministic.rs:113-118
fn markdownize(&self, request: MarkdownizeRequest) -> Result<MarkdownizeResponse> {
    let hints = request
        .prepared_unit_hint
        .clone()
        .unwrap_or_else(|| vec![default_hint(&request.raw.raw_hash)]);
    let source_text = read_source_text(&request);
```

```rust
// crates/kcs-adapter/src/deterministic.rs:190-241
fn markdown_unit_from_hint(
    hint: &PreparedUnitHint,
    request: &MarkdownizeRequest,
    source_text: Option<&str>,
) -> MarkdownUnit {
    let markdown = match source_text {
        Some(text) if request.media_type == "text/markdown" => text.to_owned(),
        Some(text) if request.media_type == "text/x-code" => {
            fence_code(text, request.raw.path.as_deref())
        }
        Some(text) if request.media_type == "application/pdf" => {
            let page_text = read_pdf_page_text(request, hint).unwrap_or_else(|| text.to_owned());
            format!("{}\n", page_text.trim())
        }
        Some(text) => text.to_owned(),
        None => format!(
            "<!-- KCS deterministic baseline {} {} -->\n",
            hint.unit_key, hint.prepared_hash
        ),
    };
    MarkdownUnit {
        unit_key: hint.unit_key.clone(),
        unit_type: hint.unit_kind,
        markdown: if markdown.trim().is_empty() {
            format!(
                "<!-- KCS deterministic baseline {} {} -->\n",
                hint.unit_key, hint.prepared_hash
            )
        } else {
            markdown
        },
        metadata: Default::default(),
    }
}

fn read_source_text(request: &MarkdownizeRequest) -> Option<String> {
    let path = request.raw.path.as_ref()?;
    let bytes = std::fs::read(path).ok()?;
    if request.media_type == "application/pdf" {
        return Some(extract_pdf_text_pages(&bytes).join("\n\n"));
    }
    let text = String::from_utf8_lossy(&bytes).into_owned();
```

No code after that read compares `hash_bytes(&bytes)` with
`request.raw.raw_hash`. The response validator checks unit structure, not byte
provenance. Finally, the CLI stamps the adapter's markdown with the old
`raw_hash` and persists it:

```rust
// crates/kcs-cli/src/main.rs:9364-9388
let generated_at = now_utc_seconds();
let run_id = format!("run_{}", new_ulid(repo.root()));
let units = normalized_units_from_response(
    &response,
    &prepare.prepared_units,
    previous.as_ref(),
    &raw_hash,
    &markdown_profile_hash,
    final_mode,
    &generated_at,
)?;
let manifest = manifest_from_units(
    &prepare.prepared_units,
    &units,
    &raw_hash,
    &markdown_profile_hash,
    previous.as_ref().map(|previous| previous.manifest.gen),
    &run_id,
    &generated_at,
    RetryErrorKind::ContractViolation,
);
persist_normalized_instance(repo.kcs_dir(), &manifest, &units).map_err(pipeline_to_kcs)?;
```

The concrete bad state is therefore:

| Step | Path contents | Identity carried forward |
| --- | --- | --- |
| caller hash check | version A | `raw_hash = H(A)` |
| preparation | version A in the strongest interleaving | prepared hint for A |
| attacker rename | version B | no rebind occurs |
| deterministic adapter read | version B | still receives `raw_hash = H(A)` |
| normalized persistence | markdown from B | manifest/unit `raw_hash = H(A)` |

That is the violated invariant. We are not saying KCS loses control of the file
system outside the selected root, and we are not relying on online embeddings or
OCR for this finding. We are saying the authoritative normalized record can
claim to describe raw object A while its searchable text came from B.

## Exploitability Analysis

The strongest route is an atomic replacement race in a shared or supplied
selected root. The attacker first leaves benign version A in place long enough
for the operator's index run to pass the scan/current-buffer hash comparison.
After preparation has derived the expected unit hint, the attacker atomically
renames version B over the same pathname. When the deterministic adapter opens
the path, it reads B, and KCS persists B-derived markdown under `H(A)`.

We should calibrate this as an integrity/provenance primitive, not as direct
code execution or direct outside-file disclosure. The attacker controls B and
the timing; the operator controls whether indexing happens. The result reaches
the authoritative `.kcs` normalized units, chunks, search results, and evidence
state for that one selected scope. If a reviewer later searches or cites the
record by raw identity, KCS can present B's text as if it was derived from A.
That is materially different from a harmless self-race because the store is the
product's evidence and retrieval substrate.

The natural reliability problem is the race window. A change before the
current-buffer comparison is rejected. A change too late leaves A normalized. A
replacement during the preparation read may create a noisier state where
prepared hashes and raw bytes diverge, which is useful for variant analysis but
less clean for this candidate. The clean interleaving waits until preparation
finishes and targets the interval before `markdown_adapter.markdownize()`.
Large files, slow stores, previous-instance lookup, or adapter setup work may
widen that interval, but I did not measure it with a live scheduler-controlled
harness.

A second route is PDF-specific. `read_source_text()` reads the PDF once and
`read_pdf_page_text()` can read the path again per page. If a PDF text layer is
in scope, that repeated reopen could create page-level inconsistencies. I treat
that as a useful variant direction rather than the primary proof, because the
plain text route already shows a complete source-to-sink path without requiring
PDF parsing behavior.

The main dead end is network egress. Some merged notes discussed later online
embedding or OCR consequences. Those are not needed for this finding and would
raise separate eligibility, approval, budget, credential, and sink questions.
For this report, the direct and validated outcome is local durable false
provenance. That boundary keeps the final severity low even though the root
cause is real and source-proven.

## Proof of Concept

The included PoC is a local/offline model of the vulnerable dataflow. It uses
temporary synthetic files and mirrors the relevant operations:

1. Write benign version A and compute `H(A)`.
2. Read the path and verify the current hash equals the scan hash.
3. Prepare from A, deriving a prepared unit hint.
4. Replace the path with attacker-controlled version B.
5. Run a modeled deterministic markdownizer that reads the current path while
   carrying the old `raw_hash`.
6. Persist a modeled normalized unit with markdown from B and `raw_hash = H(A)`.

Run it from the report directory:

```sh
cd poc
make
```

Representative output:

```text
[+] scan hash for version A: a31b2d3f75db14c2
[+] caller verified current read equals scan hash
[+] prepare derived prepared hash: a31b2d3f75db14c2
[+] attacker replaced the path after prepare and before markdownize
[+] adapter markdown came from version B: 461c1060d311aaf2
[+] persisted normalized raw_hash: a31b2d3f75db14c2
[+] primitive reached: version B text is stored under H(version A)
[+] fixed final binding check would reject: final read hash does not match request raw_hash
```

The PoC intentionally does not try to win a live KCS race. That keeps it safe
and repeatable while still demonstrating the exact violated invariant: the
later content hash is different, but the persisted normalized identity remains
the earlier raw hash.

## Remediation

The invariant to restore is: raw hashing, preparation, markdownization, and
normalized persistence must all operate on the same verified bytes or on a
stable file identity that is revalidated before use. Passing a mutable pathname
beside a trusted `raw_hash` is not enough.

The most robust fix is to carry the verified byte buffer, or an opened
no-follow descriptor with stable identity checks, through both `prepare_units`
and deterministic markdownization. A final rehash immediately before calling
the adapter is useful defense in depth, but it is not sufficient if the adapter
then performs another independent path read.

A minimal structural patch looks like this:

```rust
// Sketch: make the verified bytes the source of truth for local stages.
let bytes = fs::read(&path)
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
let current_hash = hash_bytes(&bytes);
if candidate.raw_hash.as_ref().is_some_and(|scan_hash| scan_hash != &current_hash) {
    skip_changed_candidate(...)?;
    continue;
}

let raw_hash = current_hash;
let prepare = prepare_units_from_bytes(PrepareStageBytesRequest {
    raw_hash: raw_hash.clone(),
    media_type: candidate.media_type.clone(),
    input_path: candidate.input_path.clone(),
    bytes: bytes.clone(),
    tool_profile_hash: prepare_profile_hash.clone(),
})?;

let response = deterministic_markdownize_from_bytes(MarkdownizeBytesRequest {
    raw_hash: raw_hash.clone(),
    display_path: candidate.input_path.clone(),
    media_type: candidate.media_type.clone(),
    prepared_unit_hint: hints,
    bytes,
    tool_profile_hash: markdown_profile_hash.clone(),
})?;
```

If the public adapter contract must continue to support paths, add a required
`source_hash` to `MarkdownizeResponse` and reject a response unless it equals
`request.raw.raw_hash`. That still works best when local adapters compute it
from the same bytes they used for markdown. For PDF, make per-page extraction
reuse the same byte buffer instead of reopening `request.raw.path`.

Regression coverage should include:

- Replace a text file after the current-buffer hash check and before
  deterministic markdownization; assert KCS either normalizes A or rejects the
  candidate, never stores B under `H(A)`.
- Replace before preparation and assert prepared hashes cannot be derived from
  a different byte source than raw persistence.
- Exercise text, code, and PDF text-layer paths, including the per-page PDF
  helper.
- Confirm response validation rejects adapter output whose source hash differs
  from `raw_hash`.
- Confirm stable non-mutating files still index and re-index normally.

## Summary

This bug is a deterministic local normalization TOCTOU. KCS verifies one file
read, but it does not carry that verified byte source through preparation and
markdownization. We can therefore arrange for the deterministic adapter to read
version B while KCS persists the resulting normalized text under version A's
raw hash.

The practical attacker needs concurrent write or rename authority in the
selected root, operator indexing, and a favorable timing window. The validated
impact is scope-local but security-relevant: false normalized/search/evidence
provenance under a content-addressed identity. Future variant analysis should
focus on other repeated path reads that sit after an identity or policy check,
especially PDF per-page extraction and any online path that serializes bytes
after a separate approval decision.
