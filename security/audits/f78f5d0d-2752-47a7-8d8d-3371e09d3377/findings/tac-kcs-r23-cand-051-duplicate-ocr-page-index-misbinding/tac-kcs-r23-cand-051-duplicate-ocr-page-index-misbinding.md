# Duplicate OCR page indices bind one provider page to multiple evidence units

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` accepts explicit page
indices from a Mistral-compatible OCR response without checking that they form
a unique, complete, in-range mapping to the prepared page hints. If a configured
OCR endpoint returns two pages with the same index, the adapter collapses the
first page in a `BTreeMap` and then uses positional fallback for the missing
index. We can therefore carry one provider page into two distinct KCS evidence
units while another provider page disappears.

I reviewed the vulnerable revision directly and validated the control flow with
a local, offline synthetic probe; I did not contact a live OCR provider, use
credentials, or write to a KCS store. The validated impact is document-scoped
integrity and provenance corruption in normalized OCR output: chunks, search
results, and Evidence views can attribute the wrong page content to trusted unit
keys while the task is marked `Done`.

## Background

The online OCR route prepares one or more page-like units, sends the document to
a configured Mistral-compatible OCR adapter, and expects the adapter response to
return page markdown. KCS owns the prepared unit keys, while the remote provider
controls the response order, each page's optional `index`, and the page
markdown. That distinction matters because the unit key becomes the durable KCS
identity used for normalized units and evidence, while the provider index is the
adapter's bridge from returned pages back to those prepared units.

The response parser reads every entry in `pages[]` and accepts the explicit
index whenever one is present:

```rust
// crates/kcs-adapter/src/mistral_ocr.rs, parse_ocr_response / parse_ocr_page
fn parse_ocr_response(value: Value, model_pin: &str) -> Result<OcrResponse> {
    let pages = value
        .get("pages")
        .and_then(Value::as_array)
        .ok_or_else(|| AdapterError::ContractViolation("OCR response missing pages".to_owned()))?
        .iter()
        .enumerate()
        .map(|(fallback_index, page)| parse_ocr_page(page, fallback_index))
        .collect::<Result<Vec<_>>>()?;
    Ok(OcrResponse { pages, model_version_pin: value.get("model").and_then(Value::as_str).unwrap_or(model_pin).to_owned() })
}

fn parse_ocr_page(value: &Value, fallback_index: usize) -> Result<OcrPage> {
    Ok(OcrPage {
        index: value.get("index").and_then(Value::as_u64).map(|index| index as usize).unwrap_or(fallback_index),
        markdown: value.get("markdown").and_then(Value::as_str).unwrap_or_default().to_owned(),
        images,
    })
}
```

There is no uniqueness check, no range check, and no completeness check. In the
normal well-formed case, that is harmless: `index = 0` maps to the first
prepared hint, `index = 1` maps to the second, and so on. The bug appears when
we let the remote structural metadata become inconsistent.

## Vulnerability Details

After parsing, `MistralOcrMarkdownizeAdapter::markdownize()` builds a lookup map
from provider index to page, then iterates over trusted prepared hints:

```rust
// crates/kcs-adapter/src/mistral_ocr.rs, MistralOcrMarkdownizeAdapter::markdownize
let pages_by_index = ocr
    .pages
    .iter()
    .map(|page| (page.index, page))
    .collect::<BTreeMap<_, _>>();
Ok(MarkdownizeResponse {
    mode_used: request.mode,
    updated_units: hints
        .iter()
        .filter_map(|hint| {
            let page_index = hint.order as usize;
            let page = pages_by_index
                .get(&page_index)
                .copied()
                .or_else(|| ocr.pages.get(page_index))?;
            Some(MarkdownUnit {
                unit_key: hint.unit_key.clone(),
                unit_type: hint.unit_kind,
                markdown,
                metadata: page_metadata(&ocr.model_version_pin, Some(page.images.as_slice())),
            })
        })
        .collect(),
    // ...
})
```

The decisive transition is the `BTreeMap` collection. If the remote response is
`[(index=0, markdown=A), (index=0, markdown=B)]`, the map contains only
`{0: B}` because the second duplicate overwrites the first. We then iterate over
two prepared hints:

| Hint order | Lookup result | Produced unit |
| --- | --- | --- |
| `0` | `pages_by_index[0]` | unit key for page 1 receives `B` |
| `1` | missing map key, fallback to `ocr.pages[1]` | unit key for page 2 also receives `B` |

At this point we have distinct KCS unit keys, but both carry the same provider
page. Page `A` is no longer represented.

The nearest KCS-side acceptance check validates coverage by synthesized unit
keys and shape, not by provider page identity:

```rust
// crates/kcs-pipeline/src/markdownize.rs, validate_full_response / validate_unit_shapes
let expected = prepared_units
    .iter()
    .map(|unit| unit.unit_key.clone())
    .collect::<BTreeSet<_>>();
let actual = unit_keys(&response.updated_units);
if actual != expected {
    return Err(contract_violation("full response does not cover all prepared units"));
}
validate_unit_shapes(&response.updated_units, prepared_units)
```

`validate_unit_shapes()` rejects empty markdown, unknown unit keys, and wrong
unit types. It does not know which provider page produced each unit. Because the
adapter copied the hint keys onto both outputs, the malformed response now looks
complete.

The full online executor uses that validation result as the strict `Done`
shortcut and persists normalized units:

```rust
// crates/kcs-cli/src/main.rs, full online markdownize path
let strict_valid =
    validate_markdownize_response(&response, &hints, &prepare.prepared_units).is_ok();
let mut units = normalized_units_from_response(
    &response,
    &prepare.prepared_units,
    previous.as_ref(),
    &task.input_hash,
    &profile.tool_profile_hash,
    MarkdownizeMode::Full,
    &generated_at,
)?;
let status = if retry_units.is_none() && strict_valid {
    TaskStatus::Done
} else {
    task_status_from_unit_counts(done, failed, false)
};
persist_normalized_instance(repo.kcs_dir(), &manifest, &units)?;
```

The normalized unit constructor again trusts the KCS unit key and copies the
markdown from the adapter response into that key's durable object. We therefore
end with a consistent-looking normalized instance whose identity layer says both
pages are done, while the content layer has duplicated the provider's second
page and lost the first.

## Exploitability Analysis

The attacker boundary is narrow but real: an operator must approve an online OCR
operation, and the configured endpoint must return malformed or hostile response
data. KCS has no inbound listener here, and the remote actor does not gain local
filesystem identity or credentials. The remote response actor does, however,
control the exact structural fields that KCS later treats as normalized
provenance.

The strongest route is a structural misbinding rather than a content injection.
The provider already controls OCR markdown for the approved request, so the
incremental advantage is not "can write arbitrary markdown"; it is "can make KCS
believe page identity `page:1` contains the bytes from page 2 while marking both
units complete." That matters for downstream Evidence workflows. If a user later
searches, chunks, or reviews provenance by unit key, the evidence can point to a
trusted page identity that no longer corresponds to the original page.

We also have a useful reliability property: duplicate-key overwrite and
positional fallback are deterministic. The attacker does not need a race or a
heap shape. For two prepared hints, `[(0, A), (0, B)]` is enough. For larger
documents, the same class of malformed response can omit selected indices,
duplicate another index, and rely on the fallback to fill missing positions from
the response vector. The practical constraint is that every produced markdown
must be non-empty and the provider response must still parse as typed JSON.

There are meaningful limits. The official provider is expected to return
well-formed unique indices, and malformed-response prevalence was not measured.
This path does not redirect the configured endpoint, disclose the OCR credential,
escape the selected scope, or execute code. It corrupts the integrity of one
approved OCR task and its derived state. Those limits are why Medium severity is
appropriate even though the local mapping primitive is clean.

## Proof of Concept

The accompanying PoC is a local Python probe that models only the vulnerable
mapping and acceptance relation. It does not contact a network service, read
real documents, use credentials, or modify a KCS store. From the report
directory:

```sh
cd poc
make
```

Representative output:

```text
[+] attack provider pages: [(0, 'page-A'), (0, 'page-B')]
[+] attack mapped outputs: ['page-B', 'page-B']
[+] strict coverage validation still passes: True
[+] unique-index control outputs: ['page-A', 'page-B']
[+] proposed bijection check rejects attack: duplicate page index 0
```

The attack case constructs two provider pages with duplicate index `0`. The
probe then performs the same two operations we traced in source: last-writer
map construction and positional fallback by hint order. We get two distinct
unit keys with `page-B` content. The negative control uses unique indices
`0` and `1` and preserves the bijection.

## Remediation

The invariant to restore is simple: before content is assigned to prepared unit
keys, explicit provider page indices must form an exact bijection over the
expected prepared hint orders. Positional fallback can remain useful for legacy
responses that omit indices entirely, but it should not conceal an explicitly
indexed malformed response.

A minimal defensive shape is:

```rust
fn pages_by_verified_index<'a>(
    pages: &'a [OcrPage],
    expected_len: usize,
) -> Result<BTreeMap<usize, &'a OcrPage>> {
    let mut by_index = BTreeMap::new();
    for page in pages {
        if page.index >= expected_len {
            return Err(AdapterError::ContractViolation("OCR page index out of range".to_owned()));
        }
        if by_index.insert(page.index, page).is_some() {
            return Err(AdapterError::ContractViolation("duplicate OCR page index".to_owned()));
        }
    }
    if by_index.len() != expected_len {
        return Err(AdapterError::ContractViolation("OCR response missing page index".to_owned()));
    }
    Ok(by_index)
}
```

Regression tests should cover:

- duplicate indices, such as `[(0, A), (0, B)]`, are rejected before mapping;
- out-of-range indices are rejected;
- missing explicit indices are rejected when any explicit index is present;
- all-index-omitted legacy responses either follow a documented positional
  path or are rejected consistently;
- valid `[(0, A), (1, B)]` responses still produce `[A, B]` and pass full
  response validation.

It is also worth carrying the provider page index into adapter metadata or a
debug-only validation path so KCS can audit page-to-unit binding after
normalization. The final acceptance check does not need to understand provider
internals, but it should have enough metadata to reject "complete" responses
whose page identity was already invalid upstream.

## Summary

We traced a malformed OCR response from the remote `pages[].index` field through
the adapter's duplicate-collapsing map, into hint-key coverage validation, and
finally into `Done` normalized persistence. The vulnerability is not that a
provider controls OCR text; that is inherent in the approved online OCR model.
The vulnerable step is that KCS lets provider-controlled page indices decide
which authoritative evidence unit receives that text without proving a unique
page-to-unit bijection.

The local probe demonstrates the core behavior safely: duplicate index `0`
turns `A, B` into `B, B`, while the valid control preserves `A, B`. Future
variant review should look for other adapter paths that merge remote structural
metadata into trusted unit keys, especially where KCS validates synthesized
keys but not the lower-level identity that produced the content.
