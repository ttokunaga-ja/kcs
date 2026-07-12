# Deterministic PDF page markers amplify indexing work

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` contains a
Medium severity local availability issue in its deterministic PDF indexing
path. When KCS indexes an in-scope PDF, it derives the logical page count from
raw textual `/Page` prefixes rather than structurally validated PDF page
objects. The same derived count then drives page-vector padding, one
`PreparedUnit` per page, and a deterministic markdown conversion that reopens
and reparses the whole PDF for each page hint.

I reviewed the vulnerable revision directly and relied on a bounded local
synthetic control run for the measured relationship; I did not run a
stress-size input because the validated issue is resource exhaustion and the
safe evidence already proves the growth mechanism. The bounded run used a
490-byte readable PDF-like input with 63 false `/PageX` markers and observed
64 prepared units, 64 markdown units, and a source-trace minimum of 65
whole-file PDF extractions. The honest 49-byte control produced one unit and
two extractions.

The attack is operator-mediated and local: a lower-trust contributor places a
crafted readable PDF in a scope that the operator indexes. No credential,
network listener, code execution primitive, or persistence mechanism is
involved. The impact is CPU, heap, filesystem I/O, and index availability for
the affected KCS process and scope.

## Background

KCS has a deterministic offline path for locally extractable text. During
`kcs index`, the CLI walks accepted scope candidates, enforces a raw
`max_input_bytes` limit, reads the file, prepares units, and then calls the
offline markdown adapter with every prepared unit hint. For PDFs, the
important invariant should be that logical pages come from a bounded,
structurally valid page representation, and that text extraction work is
shared across page hints.

The ordinary indexing entry point does enforce a byte-size control before it
hands a file to the adapter:

```rust
// crates/kcs-cli/src/main.rs:9047-9118
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
    let path = repo.root().join(&candidate.input_path);
    let bytes = fs::read(&path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    let current_hash = hash_bytes(&bytes);
    // ...
    let prepare = prepare_units(PrepareStageRequest {
        raw_hash: raw_hash.clone(),
        media_type: candidate.media_type.clone(),
        input_path: path.display().to_string(),
        tool_profile_hash: prepare_profile_hash.clone(),
    })
    .map_err(pipeline_to_kcs)?;
```

That control bounds the raw document size `S`, but it does not bound the
derived logical page count `P` or the amount of work KCS performs per admitted
byte. Once preparation returns `P` units, the normal path passes all of those
unit hints to the deterministic adapter:

```rust
// crates/kcs-cli/src/main.rs:9229-9304
let mapping = previous
    .as_ref()
    .map(|previous| map_units(&previous.prepared_units, &prepare.prepared_units));
let incremental_hints = mapping
    .as_ref()
    .map(|mapping| incremental_hints_from_mapping(mapping, &prepare.prepared_units))
    .unwrap_or_else(|| all_changed_hints(&prepare.prepared_units));
// ...
let hints = prepared_unit_hints(&prepare.prepared_units);
let request = MarkdownizeRequest {
    raw: RawInput {
        raw_hash: raw_hash.clone(),
        path: Some(path.display().to_string()),
    },
    media_type: candidate.media_type.clone(),
    prepared_unit_hint: Some(hints),
    mode: adapter_mode(mode),
    // ...
};
```

So we should read the PDF path as a pipeline: an admitted local file controls
the parser input, the parser produces a page count, preparation expands that
count into units, and markdownization iterates those units.

## Vulnerability Details

The root issue begins in the deterministic adapter's page counter. It scans a
lossy-decoded text view of the entire PDF and counts lexical `/Page` prefixes.
The second branch suppresses `/Pages`, but it does not require a delimiter,
object type, page-tree reachability, or a page ceiling. A token such as
`/PageX` still contributes to the count.

```rust
// crates/kcs-adapter/src/deterministic.rs:415-437
fn pdf_page_count(bytes: &[u8]) -> usize {
    pdf_page_count_in_text(&String::from_utf8_lossy(bytes))
}

/// Count PDF page objects from the (lossy-decoded) file text. Shared by the
/// pipeline crate so the char-boundary-safe lookahead lives in one place (O4).
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

The repository already has a regression that documents this lexical behavior:

```rust
// crates/kcs-adapter/src/deterministic.rs:500-515
#[test]
fn o4_pdf_page_count_survives_multibyte_char_boundary() {
    // "あ" occupies the +8 byte window measured from "/Page".
    assert_eq!(
        pdf_page_count_in_text("/PageXあ padding to extend length"),
        1
    );
    // "あ" straddles the +32 byte window measured from "/Type" (no panic).
    let type_case = format!("/Type{}あ/Pages", "y".repeat(26));
    let _ = pdf_page_count_in_text(&type_case);
    // Genuine /Pages still suppresses the count.
    assert_eq!(pdf_page_count_in_text("/Type /Pages catalog"), 0);
}
```

If we carry that lexical count into the pipeline crate, it becomes allocation
and hash work. `pdf_text_pages()` first extracts whatever text layer is present
and then pads the page vector until it reaches `page_count`:

```rust
// crates/kcs-pipeline/src/prepare.rs:315-347
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
    if strings.len() == page_count {
        return strings;
    }
    let mut pages = strings;
    while pages.len() < page_count {
        pages.push(String::new());
    }
    pages.truncate(page_count);
    pages
}
```

`prepare_units()` then treats the padded length as the unit count. For each
derived page it constructs a `PreparedUnit`, page number, unit key, prepared
hash, and fingerprint:

```rust
// crates/kcs-pipeline/src/prepare.rs:102-170
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
let mut prepared_units = Vec::new();
for index in 0..unit_count {
    let selector = match unit_type {
        UnitType::Page | UnitType::Slide => (index + 1).to_string(),
        // ...
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

The more expensive second half happens during markdownization. The adapter
first reads the source once, and for a PDF that initial read already calls
`extract_pdf_text_pages()`. Full markdownization then maps every hint through
`markdown_unit_from_hint()`:

```rust
// crates/kcs-adapter/src/deterministic.rs:113-163
fn markdownize(&self, request: MarkdownizeRequest) -> Result<MarkdownizeResponse> {
    let hints = request
        .prepared_unit_hint
        .clone()
        .unwrap_or_else(|| vec![default_hint(&request.raw.raw_hash)]);
    let source_text = read_source_text(&request);
    // ...
    Ok(MarkdownizeResponse {
        mode_used: MarkdownizeMode::Full,
        updated_units: hints
            .iter()
            .map(|hint| markdown_unit_from_hint(hint, &request, source_text.as_deref()))
            .collect(),
        unchanged_unit_keys: Vec::new(),
        added_units: Vec::new(),
        removed_unit_keys: Vec::new(),
        evidence_pointers: Vec::new(),
        fallback_to_full: false,
        reason: None,
    })
}
```

When the media type is PDF, each hint calls `read_pdf_page_text()`:

```rust
// crates/kcs-adapter/src/deterministic.rs:190-249
fn markdown_unit_from_hint(
    hint: &PreparedUnitHint,
    request: &MarkdownizeRequest,
    source_text: Option<&str>,
) -> MarkdownUnit {
    let markdown = match source_text {
        Some(text) if request.media_type == "application/pdf" => {
            let page_text = read_pdf_page_text(request, hint).unwrap_or_else(|| text.to_owned());
            format!("{}\n", page_text.trim())
        }
        // ...
    };
    // ...
}

fn read_pdf_page_text(request: &MarkdownizeRequest, hint: &PreparedUnitHint) -> Option<String> {
    let path = request.raw.path.as_ref()?;
    let bytes = std::fs::read(path).ok()?;
    let pages = extract_pdf_text_pages(&bytes);
    let page_index = page_index_from_unit_key(&hint.unit_key).unwrap_or(hint.order as usize);
    let page = pages.get(page_index).cloned()?;
    // ...
    Some(page)
}
```

Now the state transition is clear. A contributor controls the raw PDF bytes.
The byte cap admits the file, but the lexical page counter turns false
`/Page` prefixes into `P`. Preparation creates `P` units. Markdownization
performs one initial extraction plus one whole-file read and full page-vector
reconstruction for each of those `P` hints. The resulting work is at least
`O(P * S)` for repeated file parsing and, because each extraction pads to `P`,
also contains `O(P^2)` vector growth across the repeated calls.

If a previous version of the same file exists, incremental mapping can add a
separate quadratic allocation. This is not required for the first-index impact
but it increases the practical pressure:

```rust
// crates/kcs-pipeline/src/prepare.rs:387-416
fn lcs_fingerprint_pairs(
    old_units: &[PreparedUnit],
    new_units: &[PreparedUnit],
) -> Vec<(usize, usize)> {
    let m = old_units.len();
    let n = new_units.len();
    let mut dp = vec![vec![0usize; n + 1]; m + 1];
    for i in (0..m).rev() {
        for j in (0..n).rev() {
            dp[i][j] = if old_units[i].fingerprint == new_units[j].fingerprint {
                1 + dp[i + 1][j + 1]
            } else {
                dp[i + 1][j].max(dp[i][j + 1])
            };
        }
    }
    // ...
}
```

## Exploitability Analysis

The strongest route is a straightforward resource-amplification document. We
place one real text-bearing PDF-like page in the scope so that the deterministic
path is selected, and then we add many false `/Page` prefixes that are cheap in
bytes but expensive after KCS interprets them as pages. The false marker does
not need to be a valid page object; `/PageX` is enough for the lexical counter.

The useful attacker-controlled variables are:

- `S`, the admitted file size, bounded by `adapter.policy.max_input_bytes`;
- `P`, the lexical `/Page` count, not structurally validated and not separately
  capped;
- whether a previous normalized version exists, which determines whether the
  LCS matrix path is also exercised.

For first-time indexing, we already get a practical primitive without relying
on prior state. The file is read once to prepare pages, and markdownization
does another full extraction per unit. If `P` grows while `S` stays under the
raw byte cap, the indexing operation spends CPU and I/O on the same file again
and again. The empty padded pages still become units, so the attack does not
need meaningful content for every page.

The incremental route is a useful variant rather than the root requirement.
When old and new prepared units are available, `map_units()` allocates an
`(m + 1) * (n + 1)` dynamic-programming matrix. If both revisions are driven by
the inflated count, we can add substantial heap pressure before the adapter
even starts emitting the changed units. That path is tracked separately as a
general LCS issue, so for this finding we rely on repeated PDF parsing as the
independent sink.

There are meaningful constraints. Wholly nontext PDFs route away from this
deterministic loop, so the crafted document must retain at least one readable
text layer or literal. The raw input cap also prevents unbounded document size,
and the operator can recover by removing the crafted input and rerunning the
index. These controls lower the impact from host compromise to local,
recoverable availability loss, but they do not restore the missing invariant:
work should be bounded by validated pages and should not multiply full-document
parsing by attacker-inflated page hints.

## Proof of Concept

The included PoC is a bounded local regression probe, not a stress tool. It
builds an in-memory synthetic PDF-like byte string with one readable literal and
a configurable number of false `/PageX` markers, then mirrors the source-level
relationships that matter: lexical page count, padded units, minimum full
extractions, and same-size LCS cells. It does not invoke KCS, touch a repository
store, use credentials, or contact a network.

Run it from the report directory:

```sh
cd poc
make
make run
```

Representative output with the default bounded marker count:

```text
python3 -m py_compile pdf_page_reparse_amplification_probe.py
python3 pdf_page_reparse_amplification_probe.py --markers 63
{
  "attack": {
    "false_page_markers": 63,
    "input_bytes": 490,
    "lexical_page_count": 64,
    "markdown_units": 64,
    "prepared_units": 64,
    "same_size_revision_lcs_cells": 4225,
    "source_trace_minimum_full_pdf_extractions": 65
  },
  "control": {
    "false_page_markers": 0,
    "input_bytes": 49,
    "lexical_page_count": 1,
    "markdown_units": 1,
    "prepared_units": 1,
    "same_size_revision_lcs_cells": 4,
    "source_trace_minimum_full_pdf_extractions": 2
  },
  "network": false
}
```

We should treat larger marker counts as regression-test inputs only after a fix
adds explicit work ceilings. The PoC caps its own marker argument to keep this
artifact safe for routine review.

## Remediation

The invariant to restore is: one admitted PDF must produce a bounded number of
validated logical pages, and the expensive extraction result must be reused
across page hints. There are two separate controls to add.

First, replace lexical page counting with a structural page-source decision.
If a full PDF parser is not in scope for the deterministic baseline, the safe
fallback is to cap heuristic pages aggressively and treat suspicious excess as
one file-level unit or route it to the safer online/OCR path under the existing
approval and budget controls. A minimal defensive pattern is:

```rust
const MAX_DETERMINISTIC_PDF_PAGES: usize = 256;

fn bounded_pdf_pages(bytes: &[u8]) -> Result<Vec<String>> {
    let pages = structurally_extract_text_pages(bytes)?;
    if pages.len() > MAX_DETERMINISTIC_PDF_PAGES {
        return Err(PipelineError::contract(
            "KCS-E-PDF-PAGE-LIMIT-001",
            "pdf page count exceeds deterministic page limit",
        ));
    }
    Ok(pages)
}
```

Second, change the adapter request flow so the PDF text pages are extracted
once and shared by every hint. If the API boundary cannot carry the vector, the
adapter can still cache by `raw_hash` and path for the lifetime of a single
markdownize call:

```rust
fn markdownize(&self, request: MarkdownizeRequest) -> Result<MarkdownizeResponse> {
    let hints = request
        .prepared_unit_hint
        .clone()
        .unwrap_or_else(|| vec![default_hint(&request.raw.raw_hash)]);
    let pdf_pages = if request.media_type == "application/pdf" {
        request.raw.path.as_ref()
            .and_then(|path| std::fs::read(path).ok())
            .map(|bytes| extract_pdf_text_pages_bounded(&bytes))
            .transpose()?
    } else {
        None
    };
    // Each hint indexes into `pdf_pages` instead of reopening the file.
    // ...
}
```

Regression tests should cover both the root and the sink:

- `/PageX` and `/Type ... /Page` tokens that are not real page objects must not
  increase deterministic page count;
- a readable PDF with many false markers must produce either one file-level
  unit, a bounded page count, or a controlled error;
- markdownization of `P` page hints must perform one PDF read/extraction per
  request, not one per hint;
- incremental mapping should retain an independent `(m, n)` work or cell cap
  so PDF fixes do not leave the LCS allocation route exposed.

## Summary

This finding is present because KCS treats raw PDF text as both a parser input
and an authority for page cardinality. Once we let a false `/Page` prefix become
logical state, the rest of the pipeline faithfully expands that state into
units, hashes, markdown hints, repeated full-document parsing, and sometimes
quadratic revision mapping. The validated result is not code execution or data
exposure; it is local availability loss during ordinary indexing of an
attacker-controlled but admitted document.

The fix should make page count structural and bounded, parse each PDF once per
indexing operation, and keep independent work ceilings on unit mapping. After
that, variant analysis should focus on other media types where a cheap lexical
or metadata field controls unit count, object count, or repeated full-input
processing.
