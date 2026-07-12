# Lexical PDF Page Markers Amplify Derived Work Without a Cardinality Bound

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` accepts
untrusted local PDFs during ordinary indexing, applies a raw byte-size cap, and
then derives PDF page cardinality by counting textual `/Page` prefixes in the
file body. Because that count is not structural and has no page/unit ceiling, a
small PDF with one printable stream and many inert `/PageX` markers can be
expanded into one `PreparedUnit` per marker. The affected version range beyond
the reviewed revision is not established here, and I did not compare a fixing
revision because no fix commit was available for this review.

I reviewed the vulnerable revision directly and ran a bounded local probe with
synthetic PDF bytes; I did not run an unbounded allocation test because the
intended failure mode is process-wide memory and CPU exhaustion. The validated
impact is persistent local denial of service against the KCS indexing workflow:
a lower-trust contributor who can place or revise content in an indexed scope can
leave a crafted PDF that repeatedly exhausts the indexing process when the
operator indexes that scope. The final severity is Medium/P2 because the impact
is high for local availability, while exploitation requires content placement,
deterministic-path selection, and an operator indexing action.

## Background

KCS treats local repository or scope content as an ingestion boundary. During
`kcs index`, it walks candidate files, skips ignored entries and directories,
enforces `adapter.policy.max_input_bytes`, reads the selected file, and invokes
the preparation stage. The default input cap is 100 MiB:

```rust
// crates/kcs-cli/src/main.rs:4425-4433
/// Documented default for `adapter.policy.max_input_bytes`: 100 MB.
const DEFAULT_MAX_INPUT_BYTES: u64 = 104_857_600;

fn effective_max_input_bytes(repo: &Repository) -> u64 {
    read_max_input_bytes_config(&repo.kcs_dir().join("config.toml"))
        .or_else(|| read_max_input_bytes_config(&user_config_toml_path()))
        .unwrap_or(DEFAULT_MAX_INPUT_BYTES)
}
```

That byte gate is the main general-purpose size control before parsing:

```rust
// crates/kcs-cli/src/main.rs:9047-9061
// Scope config wins over user config, default 100 MB.
let max_input_bytes = effective_max_input_bytes(repo);

for candidate in preview
    .candidates
    .iter()
    .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
{
    if candidate.size_bytes > max_input_bytes {
        result.skipped_oversized_files += 1;
        // ...
        continue;
    }
```

Once a file is below that cap, the normal path reads the bytes and asks
`prepare_units()` to create the deterministic units that later drive storage and
markdownization:

```rust
// crates/kcs-cli/src/main.rs:9077-9110
let path = repo.root().join(&candidate.input_path);
let bytes = fs::read(&path)
    .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
// ...
let raw_hash = current_hash;
let prepare = prepare_units(PrepareStageRequest {
    raw_hash: raw_hash.clone(),
    media_type: candidate.media_type.clone(),
    input_path: path.display().to_string(),
    tool_profile_hash: prepare_profile_hash.clone(),
})
.map_err(pipeline_to_kcs)?;
```

For PDFs, the normal invariant should be that derived page count comes from a
validated page tree or another bounded structural source. We need that invariant
because the preparation stage does not just record the raw file. It allocates
per-page metadata, hashes, fingerprints, and unit keys, and those units persist
as the normalized representation of the document.

## Vulnerability Details

The vulnerable transition begins in the deterministic PDF helper. Instead of
parsing a PDF page tree, KCS lossy-decodes the entire file and counts textual
substrings. The second branch below counts every `/Page` prefix whose eight-byte
lookahead does not start with `/Pages`; a token such as `/PageX` is therefore
counted as one page even though it is not a page object:

```rust
// crates/kcs-adapter/src/deterministic.rs:415-437
fn pdf_page_count(bytes: &[u8]) -> usize {
    pdf_page_count_in_text(&String::from_utf8_lossy(bytes))
}

/// Count PDF page objects from the (lossy-decoded) file text.
pub fn pdf_page_count_in_text(text: &str) -> usize {
    let pages = text
        .match_indices("/Type")
        .filter(|(index, _)| {
            let tail = bounded_str_window(text, *index, 32);
            tail.contains("/Page") && !tail.contains("/Pages")
        })
        .count();
    pages.max(
        text.match_indices("/Page")
            .filter(|(index, _)| {
                let tail = bounded_str_window(text, *index, 8);
                !tail.starts_with("/Pages")
            })
            .count(),
    )
}
```

If we carry that attacker-controlled count into the pipeline copy of the PDF
text extraction logic, it becomes a vector length. A PDF beginning with `%PDF`
and containing a text layer reaches `pdf_text_pages()`. The function computes
`page_count`, extracts a small number of actual stream pages, and then pads the
page vector with empty strings until its length equals the lexical count:

```rust
// crates/kcs-pipeline/src/prepare.rs:315-340
pub fn pdf_text_pages(bytes: &[u8]) -> Vec<String> {
    if !bytes.starts_with(b"%PDF") {
        return vec![String::from_utf8_lossy(bytes).into_owned()];
    }
    if !pdf_has_text_layer(bytes) {
        return Vec::new();
    }
    let page_count =
        kcs_adapter::deterministic::pdf_page_count_in_text(&String::from_utf8_lossy(bytes)).max(1);
    let stream_pages = kcs_adapter::deterministic::pdf_stream_text_pages(bytes);
    if !stream_pages.is_empty() {
        return normalize_pdf_page_count(stream_pages, page_count);
    }
    let strings = pdf_literal_strings(bytes);
    if strings.is_empty() {
        return vec![pdf_text_fallback(bytes)];
    }
    // ...
    let mut pages = strings;
    while pages.len() < page_count {
        pages.push(String::new());
    }
    pages.truncate(page_count);
    pages
}
```

The scanned-PDF fallback does not break this path when the crafted PDF includes
one printable stream. `prepare_units()` only routes to OCR if every recovered
page is empty or non-printable. One real text page makes `pages.iter().all(...)`
false, so the padded vector remains active:

```rust
// crates/kcs-pipeline/src/prepare.rs:102-127
let pdf_pages = if request.media_type == "application/pdf" {
    let pages = pdf_text_pages(&bytes);
    if pages.iter().all(|page| !is_probably_real_text(page)) {
        return Ok(PrepareStageOutput {
            prepared_object_hashes: Vec::new(),
            prepared_units: Vec::new(),
            image_object_hashes: Vec::new(),
        });
    }
    pages
} else {
    Vec::new()
};
let unit_count = if unit_type == UnitType::Page {
    pdf_pages.len().max(1)
} else {
    1
};
```

From here, the count becomes owned work. KCS iterates `0..unit_count`, creates a
canonical page key, computes per-page hashes and fingerprints, and pushes a
`PreparedUnit` for every padded page:

```rust
// crates/kcs-pipeline/src/prepare.rs:130-163
let mut prepared_units = Vec::new();
for index in 0..unit_count {
    let selector = match unit_type {
        UnitType::Page | UnitType::Slide => (index + 1).to_string(),
        UnitType::Sheet => "Sheet1".to_owned(),
        UnitType::Image => index.to_string(),
        UnitType::File | UnitType::HeadingSection | UnitType::Symbol => "1".to_owned(),
    };
    let unit_key = canonical_unit_key(unit_type, &selector);
    let page_bytes = pdf_pages
        .get(index)
        .map(|page| page.as_bytes())
        .unwrap_or(bytes.as_slice());
    let unit_prepared_hash = if unit_type == UnitType::Page {
        hash_bytes(page_bytes)
    } else if unit_count == 1 {
        prepared_hash.clone()
    } else {
        hash_bytes(format!("{prepared_hash}\0{unit_key}").as_bytes())
    };
    let fingerprint = if unit_type == UnitType::Page {
        fingerprint_for_bytes(page_bytes, page_bytes)
    } else {
        fingerprint_for_bytes(&bytes, unit_prepared_hash.as_bytes())
    };
    prepared_units.push(PreparedUnit {
        order: index as u64,
        unit_key,
        unit_type,
        prepared_hash: unit_prepared_hash,
        fingerprint,
        mime: Some(request.media_type.clone()),
        page_number: (unit_type == UnitType::Page).then_some(index as u64 + 1),
    });
}
```

The missed invariant is therefore precise: KCS bounds input bytes but never
bounds the number of logical PDF pages or prepared units derived from those
bytes. A six-byte lexical marker controls one additional page entry, one
additional page key, one additional unit object, and later work over that unit
list.

## Exploitability Analysis

The strongest practical route is a persistent local denial of service against
indexing. We place a PDF in a scope the victim normally indexes. The file only
needs to be under `adapter.policy.max_input_bytes`, begin with `%PDF`, contain
one printable text stream, and include many compact `/Page`-prefixed markers
outside the actual page structure. When the operator runs `kcs index`, the byte
gate accepts the file, the lexical counter converts marker count to page count,
and preparation allocates per-page units until the process becomes memory- or
CPU-bound.

The byte cap limits raw input but not derived cardinality. With the default
100 MiB cap and six-byte markers, the theoretical marker budget is in the tens
of millions even after PDF framing overhead. The bounded probe included with
this report uses a 100-byte synthetic body and computes 17,476,250 marker slots
under the default cap. We should not treat that as an exact production crash
threshold, because real memory pressure depends on allocator behavior, process
limits, build mode, and surrounding indexing work. It is enough to show that the
control is in the wrong unit: bytes are bounded, while page count and unit count
are not.

The route is also persistent. The crafted file remains in the indexed scope, so
an operator who retries indexing can trigger the same expansion again. There is
no need for a listener, credentials, or a live service target. The attacker does
need a content-placement path and the victim must index the affected scope, which
is why I would not rate this as a network-style unauthenticated DoS. Within the
local content threat model, however, the primitive is direct and repeatable.

One tempting dead end is to rely on wholly non-text or compressed garbage PDF
content. That is less reliable because `prepare_units()` intentionally routes
documents whose recovered pages are all non-printable to OCR. The better trigger
keeps the document on the deterministic path with a single printable stream, then
uses empty padded pages for the amplification. Another non-requirement is a
structurally valid page tree. The vulnerability is specifically that KCS accepts
lexical page-like markers as cardinality, so inert marker text is enough.

## Proof of Concept

The `poc/` directory contains a bounded Python probe and `Makefile`. The probe
does not invoke KCS or allocate millions of units. Instead, it mirrors the
reviewed parser logic over synthetic PDF bytes, caps materialized unit keys with
`--max-allocate`, and computes the default-cap upper range.

Run it from the report directory:

```sh
cd poc
make run
```

Representative output from the included 64-marker run:

```text
python3 pdf_page_marker_probe.py --markers 64
[+] synthetic_pdf_bytes=479
[+] marker_bytes=6
[+] lexical_page_count=64
[+] extracted_stream_pages=1
[+] padded_page_vector_len=64
[+] deterministic_path_active=true
[+] prepared_units=64
[+] materialized_in_probe=64
[+] first_unit=page:1
[+] last_materialized_unit=page:64
[+] estimated_markers_under_default_100MiB_cap=17476250
```

The test target confirms the growth shape for 1, 4, 16, and 64 markers:

```sh
cd poc
make test
```

On a vulnerable KCS build, the same relationship is dangerous when the marker
count is increased beyond the bounded probe sizes: `lexical_page_count`,
`padded_page_vector_len`, and `prepared_units` all follow attacker-controlled
marker count. Do not run a high-marker reproduction on a workstation that cannot
be safely restarted, because the expected outcome is resource exhaustion.

## Remediation

The invariant to restore is: raw PDF bytes may be capped by size, but derived
page cardinality must also be structural, bounded, and enforced before vector
padding or `PreparedUnit` allocation. The fix should not make `/Page` string
counting more elaborate; it should stop using loose lexical prefixes as an
authoritative page count.

A minimal safe shape is to replace `pdf_page_count_in_text()` at the call site
with a structural counter that returns an error or OCR fallback when the page
tree cannot be parsed confidently, and to enforce a configured derived-page
ceiling before normalization:

```rust
// Sketch: preserve the invariant before Vec padding or PreparedUnit creation.
const DEFAULT_MAX_DERIVED_PDF_PAGES: usize = 10_000;

fn bounded_pdf_page_count(bytes: &[u8], limit: usize) -> Result<usize> {
    let count = structural_pdf_page_count(bytes)?
        .ok_or_else(|| PipelineError::InvalidPdf("missing page tree".to_owned()))?;
    if count == 0 {
        return Ok(1);
    }
    if count > limit {
        return Err(PipelineError::ResourceLimit(format!(
            "pdf page count {count} exceeds limit {limit}"
        )));
    }
    Ok(count)
}

pub fn pdf_text_pages(bytes: &[u8]) -> Result<Vec<String>> {
    if !bytes.starts_with(b"%PDF") {
        return Ok(vec![String::from_utf8_lossy(bytes).into_owned()]);
    }
    if !pdf_has_text_layer(bytes) {
        return Ok(Vec::new());
    }
    let page_count = bounded_pdf_page_count(bytes, DEFAULT_MAX_DERIVED_PDF_PAGES)?;
    let stream_pages = kcs_adapter::deterministic::pdf_stream_text_pages(bytes);
    Ok(normalize_pdf_page_count(stream_pages, page_count))
}
```

The exact error type and limit source should match KCS configuration style, but
the important point is where the control lands: before `normalize_pdf_page_count`
and before `prepare_units()` enters `0..unit_count`. If compatibility requires a
fallback for malformed PDFs, route them to OCR or a single conservative document
unit instead of trusting lexical page markers.

Regression coverage should include:

- a PDF with one real text stream and many `/PageX` markers, asserting that
  prepared-unit count stays at the structural page count or returns a resource
  limit;
- a valid multi-page PDF below the limit, asserting normal per-page preparation;
- a valid PDF above the configured derived-page limit, asserting a controlled
  skip/error path rather than partial allocation;
- a scanned or textless PDF, asserting the existing OCR fallback behavior still
  applies;
- a boundary test that combines the raw byte cap and page limit so a small file
  cannot create disproportionate derived work.

As hardening, carry the same derived-cardinality budget through later stages
that consume `PreparedUnit` vectors. Even with structural page counts, downstream
unit mapping, markdownization, and persistence should reject or degrade large
unit sets before allocating work proportional to attacker-controlled cardinality.

## Summary

The vulnerability is a unit mismatch between input validation and derived work.
KCS bounds PDF bytes, but then turns loose textual `/Page` prefixes into logical
pages and allocates one prepared unit per inferred page. We can keep the file
small, keep the deterministic path active with one printable stream, and still
force the indexer to allocate and process an attacker-selected number of units.

The supplied PoC demonstrates the unsafe growth curve locally without exhausting
the host. A production fix should replace lexical counting with bounded
structural parsing, enforce a configured page/unit ceiling before vector padding,
and add regression tests that exercise compact marker amplification directly.
Variant analysis should look for other places where KCS bounds raw bytes but not
the parser-derived item count that drives allocation or repeated work.
