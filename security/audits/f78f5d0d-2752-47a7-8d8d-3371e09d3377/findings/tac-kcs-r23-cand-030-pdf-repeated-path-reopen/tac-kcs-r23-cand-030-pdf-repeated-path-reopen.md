# Deterministic PDF normalization repeatedly reopens an unbound pathname

## Executive Summary

KCS deterministic PDF normalization binds normalized output to a raw hash that
was calculated from one read of a selected-scope file, but the later PDF
normalization path reopens the same mutable pathname instead of consuming the
verified bytes. A lower-trust contributor who can replace a PDF in a scope
while an operator indexes it can cause PDF text from a later file version, or
from multiple later versions, to be persisted under the earlier file's raw
identity.

I reviewed KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` directly
and ran the included local/offline synthetic PoC against disposable PDF-like
files. I did not run a barrier-controlled race inside the unmodified KCS binary,
and I did not test any live service, external repository, credential, or
third-party target. The validated impact is therefore limited to local
normalization, search, and evidence-provenance integrity for one selected scope;
broader arbitrary-file disclosure or network-upload claims are not relied on in
this report.

The issue is best treated as a low-severity, P3 pathname TOCTOU/provenance
misbinding: the boundary crossed is real, but exploitation requires a concurrent
writer with scope write authority and favorable scheduling, and the demonstrated
effect is bounded and recoverable by a clean re-index.

## Background

KCS indexes direct child files from a local scope and stores derived data under
content identities. For a PDF, the expected invariant is simple: once we decide
that `H(A)` is the raw identity for the current input, all prepared units,
markdown, normalized instances, and search material for that operation should
come from the same bytes `A`.

The deterministic adapter is local and non-networked, but its output is still
authoritative in the store. That matters for a shared or staged scope: the
operator may trust search results, normalized evidence, and raw-hash provenance
even when the file was supplied by a lower-trust contributor. The contributor
does not need KCS credentials or an API boundary. The useful control is ordinary
filesystem authority to rename or replace a selected PDF pathname while
indexing is in progress.

The CLI does include a defensive hash check. We first reach the selected file in
`run_index_pipeline()`, read the current bytes, compare them with the scan-time
hash when one is available, and keep the current hash as `raw_hash`:

```rust
// crates/kcs-cli/src/main.rs:9077-9109
let path = repo.root().join(&candidate.input_path);
let bytes = fs::read(&path)
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
// ...
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

That check closes replacements that land before the read at line 9078. The
important question is what happens after it passes. The code keeps `bytes` only
for prepared-object persistence, while the later normalization stages keep
receiving the pathname.

## Vulnerability Details

After the CLI establishes `raw_hash`, it builds a markdownize request that
carries both the hash and the same pathname. We can carry the state forward as
`raw_hash = H(A)` and `path = "report.pdf"`, where `report.pdf` is not bound to
the file object that produced `H(A)`:

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
    // Offline (deterministic) markdownize path: the builtin adapter ignores
    // page scoping (R15-5 concerns only the real Mistral client).
    restrict_to_hint_pages: false,
    tool_profile_hash: markdown_profile_hash.clone(),
    spec_version: 1,
};

let mut response = markdown_adapter
    .markdownize(request.clone())
    .map_err(adapter_to_kcs)?;
```

The request type makes that split explicit. `RawInput` has a `raw_hash` field
and an optional `path`; it does not carry the already verified byte buffer or an
open descriptor:

```rust
// crates/kcs-adapter/src/types.rs:79-83
pub struct RawInput {
    pub raw_hash: String,
    pub path: Option<String>,
}
```

Inside the deterministic adapter, `markdownize()` asks `read_source_text()` for
aggregate source text, then maps every prepared hint through
`markdown_unit_from_hint()`:

```rust
// crates/kcs-adapter/src/deterministic.rs:113-156
fn markdownize(&self, request: MarkdownizeRequest) -> Result<MarkdownizeResponse> {
    let hints = request
        .prepared_unit_hint
        .clone()
        .unwrap_or_else(|| vec![default_hint(&request.raw.raw_hash)]);
    let source_text = read_source_text(&request);
    if request.mode == MarkdownizeMode::Incremental {
        // ...
        return Ok(MarkdownizeResponse {
            mode_used: MarkdownizeMode::Incremental,
            updated_units: hints
                .iter()
                .filter(|hint| changed.contains(&hint.unit_key))
                .map(|hint| markdown_unit_from_hint(hint, &request, source_text.as_deref()))
                .collect(),
            // ...
        });
    }

    Ok(MarkdownizeResponse {
        mode_used: MarkdownizeMode::Full,
        updated_units: hints
            .iter()
            .map(|hint| markdown_unit_from_hint(hint, &request, source_text.as_deref()))
            .collect(),
        // ...
    })
}
```

For PDFs, the aggregate read reopens the pathname and parses whatever bytes are
present then. It never compares those bytes with `request.raw.raw_hash`:

```rust
// crates/kcs-adapter/src/deterministic.rs:225-230
fn read_source_text(request: &MarkdownizeRequest) -> Option<String> {
    let path = request.raw.path.as_ref()?;
    let bytes = std::fs::read(path).ok()?;
    if request.media_type == "application/pdf" {
        return Some(extract_pdf_text_pages(&bytes).join("\n\n"));
    }
```

The PDF branch in `markdown_unit_from_hint()` then calls another helper for each
page-like hint:

```rust
// crates/kcs-adapter/src/deterministic.rs:190-203
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
```

The per-page helper reopens the same path again. This is the repeated reopen
that widens the window: if a contributor replaces the file after the aggregate
read, a later page can come from a different version than the aggregate text.

```rust
// crates/kcs-adapter/src/deterministic.rs:244-249
fn read_pdf_page_text(request: &MarkdownizeRequest, hint: &PreparedUnitHint) -> Option<String> {
    let path = request.raw.path.as_ref()?;
    let bytes = std::fs::read(path).ok()?;
    let pages = extract_pdf_text_pages(&bytes);
    let page_index = page_index_from_unit_key(&hint.unit_key).unwrap_or(hint.order as usize);
    let page = pages.get(page_index).cloned()?;
```

At this point the state can be:

| Step | Path contents | Trusted identity kept by KCS | Bytes used for text |
| --- | --- | --- | --- |
| Checked read | version A | `H(A)` | A |
| Aggregate PDF read | version B | `H(A)` | B |
| Per-page PDF read | version C | `H(A)` | C |

The sink keeps using the earlier `raw_hash`. When normalized units are built,
the code labels adapter-returned markdown with that hash and then persists the
normalized instance:

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

The actual assignment into each normalized unit is direct:

```rust
// crates/kcs-cli/src/main.rs:9819-9858
fn normalized_units_from_response(
    response: &kcs_adapter::types::MarkdownizeResponse,
    prepared_units: &[PreparedUnit],
    previous: Option<&PreviousInstance>,
    raw_hash: &str,
    tool_profile_hash: &str,
    mode: MarkdownizeMode,
    generated_at: &str,
) -> Result<Vec<NormalizedUnitObject>> {
    // ...
    let mut units = response
        .updated_units
        .iter()
        .chain(response.added_units.iter())
        .map(|unit| {
            let prepared = prepared
                .get(unit.unit_key.as_str())
                .ok_or_else(|| KcsError::schema("adapter returned unknown unit"))?;
            Ok(NormalizedUnitObject {
                unit_key: unit.unit_key.clone(),
                unit_type: prepared.unit_type,
                raw_hash: raw_hash.to_owned(),
                prepared_hash: prepared.prepared_hash.clone(),
                tool_profile_hash: tool_profile_hash.to_owned(),
                gen: 0,
                mode,
                markdown: unit.markdown.clone(),
```

The violated invariant is not that KCS lacks every hash check. The bug is more
specific: the effective hash check protects only the first read. We then cross a
trust boundary by reusing the checked identity with later bytes from a mutable
pathname.

## Exploitability Analysis

The strongest practical route is an atomic replacement race in a writable scope.
We want the operator to index version A, let the check at `main.rs:9090-9102`
compute and accept `H(A)`, then replace `report.pdf` before the deterministic
adapter reaches `std::fs::read()` in `read_source_text()` or
`read_pdf_page_text()`. Atomic rename is enough; the attacker does not need to
modify partial file contents in place.

If the first replacement lands before the checked read, KCS skips the candidate
because `current_hash` no longer matches the scan hash. That is real
counterevidence and keeps this from being a general "change any time" bug. The
useful window starts after the checked read and ends before the later adapter
reopens. The store lock does not serialize unrelated filesystem writers in the
selected root, so a collaborating process with write authority can still race
that path.

We get two integrity primitives:

1. A version-B PDF can provide the markdown text while the normalized objects
   remain tied to `H(A)`.
2. Because the deterministic adapter reopens once for aggregate text and again
   for every PDF page hint, different pages can be derived from different
   pathname versions if replacements land between page reads.

The second primitive is interesting but less stable. The source proves the
repeated reads, and the PoC models the interleaving, but I did not measure race
success rate in the unmodified binary. Scheduling, PDF size, number of prepared
page hints, filesystem latency, and host load will all affect reliability. A
test-only barrier after the checked hash and before adapter invocation would be
the clean way to turn the source trace into a deterministic regression test.

The realistic impact is search and provenance poisoning inside one scope. A
lower-trust contributor can make a trusted user see and search normalized text
that does not match the raw object named by the manifest. That can mislead
review workflows that treat raw hashes as evidence anchors. It can also make a
later audit harder because the normalized unit says "this markdown belongs to
`H(A)`" while the visible text came from B or C.

The constraints are important:

- The attacker needs write or rename authority for the selected PDF pathname.
- The operator must run deterministic indexing while the attacker can race it.
- The report does not prove arbitrary out-of-scope file disclosure.
- The report does not prove any online upload path or credential exposure.
- A stable re-index after the file stops changing can rebuild the derived state.

Those constraints are why the calibrated severity is low even though the root
cause is a real content-identity violation.

## Proof of Concept

The included PoC is a local synthetic control-flow model. It does not modify KCS
state or rely on a timing race in the production binary. Instead, it creates
three disposable PDF-like byte strings and performs the relevant sequence from
the source:

1. read and hash version A;
2. keep `H(A)` as the trusted raw identity;
3. replace the pathname with version B before the aggregate deterministic read;
4. replace the pathname with version C before the per-page deterministic read;
5. show that C-derived markdown is stored under `H(A)` in the modeled normalized
   unit.

Run it from the report directory:

```sh
cd poc
make run
```

Representative output:

```text
python3 pdf_reopen_misbinding_poc.py
[+] checked read observed A: VERSION_A_APPROVED_AT_HASH_CHECK
[+] checked raw hash H(A): b55bab4737db47438ddab4770d7a7987d86594dd7eab467efa37d9567e6a75a1
[+] aggregate reopen observed: VERSION_B_AFTER_HASH_BEFORE_SOURCE_READ
[+] current hash after source reopen H(B): c76aa24180370df799263c85a0419355080418146c645a8214318d10ac43d9b5
[+] per-page reopen observed: VERSION_C_BEFORE_PER_PAGE_READ
[+] current hash before persistence H(C): 6ac3d88400f77f7a7cfc4de977f1e93891f8488baf08ddf8db10dd2b64735f7d
[+] persisted unit raw_hash: b55bab4737db47438ddab4770d7a7987d86594dd7eab467efa37d9567e6a75a1
[+] persisted unit markdown: VERSION_C_BEFORE_PER_PAGE_READ
[+] misbinding reproduced in the synthetic control-flow model
```

This is intentionally a proof of the bad state for the reviewed interleaving,
not a claim that the race is deterministic in an uninstrumented production run.
The next stronger PoC would add a test-only barrier after `current_hash` is
accepted and before deterministic markdownization, then assert that later bytes
cannot be persisted under `H(A)`.

## Remediation

The invariant to restore is: normalized PDF output must be derived from the same
bytes that produced the `raw_hash` used in the normalized manifest and units.
The most direct fix is to stop passing a mutable pathname as the authority after
the checked read. Carry an immutable byte snapshot, or an opened file descriptor
whose identity is revalidated, through prepare and deterministic markdownize.

One minimal shape is to introduce a verified raw input object and make the
deterministic adapter parse bytes, not paths:

```rust
struct VerifiedRawInput {
    raw_hash: String,
    bytes: Arc<[u8]>,
    display_path: Option<String>,
}

let bytes = fs::read(&path)
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
let raw_hash = hash_bytes(&bytes);
if candidate.raw_hash.as_ref().is_some_and(|scan_hash| scan_hash != &raw_hash) {
    // Existing skip path.
    continue;
}

let verified = VerifiedRawInput {
    raw_hash: raw_hash.clone(),
    bytes: Arc::<[u8]>::from(bytes.clone()),
    display_path: Some(path.display().to_string()),
};

let prepare = prepare_units_from_verified(&verified, candidate.media_type.clone())?;
let response = markdown_adapter.markdownize_verified(verified, hints, mode)?;
```

If the project needs path-based adapter compatibility for other backends, add a
final guard immediately before every path-consuming backend read:

```rust
let bytes = std::fs::read(path)?;
if hash_bytes(&bytes) != request.raw.raw_hash {
    return Err(AdapterError::InputChanged);
}
```

That guard is weaker than byte-snapshot plumbing because it still leaves
multiple readers and repeated parsing, but it fails closed instead of silently
binding B-derived markdown to `H(A)`.

Regression tests should cover the real boundary:

- replace a PDF after the checked read and assert that deterministic
  normalization either uses the original verified bytes or fails before
  persistence;
- replace the PDF between aggregate and per-page extraction and assert that
  mixed-version markdown cannot be produced under one raw hash;
- repeat the test with a scan-time symlink rejection followed by a later
  regular-file replacement to confirm the later opens are also protected;
- verify that normal stable PDFs still produce the same prepared units and
  normalized markdown as before.

## Summary

KCS already recognizes that file bytes can change between scan and normalize,
but the current protection stops at the first checked read. From there we keep
the earlier `raw_hash` and repeatedly reopen a mutable PDF pathname for
deterministic normalization. We showed from source that later bytes can flow
into normalized units while the persisted identity remains `H(A)`, and the PoC
demonstrates that bad state with disposable synthetic PDFs.

The practical risk is bounded local integrity loss: normalized/search evidence
can claim one raw object while describing another. Fixing this should focus on
one structural rule across prepare and markdownize: once KCS has accepted the
raw identity, every deterministic byte consumer must use the same verified input
or revalidate and fail closed before producing persistent output.
