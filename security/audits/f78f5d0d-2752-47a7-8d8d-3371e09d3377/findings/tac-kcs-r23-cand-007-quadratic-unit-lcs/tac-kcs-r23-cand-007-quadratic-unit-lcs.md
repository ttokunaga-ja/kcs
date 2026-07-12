# Incremental Unit Mapping Allocates a Quadratic LCS Matrix

## Executive Summary

KCS revision indexing maps a file's previous prepared units against its current
prepared units before it decides whether the next markdownize run should be
incremental or full. At revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`,
that mapping is implemented with a full dynamic-programming LCS matrix of
`(old_units + 1) * (new_units + 1)` `usize` cells. A contributor who can place
successive document revisions in a scope that an operator indexes can therefore
drive both matrix dimensions and consume memory and CPU during an ordinary local
index workflow.

I reviewed the vulnerable revision directly and ran the bundled offline
synthetic PoC at bounded sizes up to 512 by 512; I did not allocate the larger
10,000, 20,000, or 50,000 unit matrices, and I did not test against any live or
public target. No fixed revision was provided with this finding, so the affected
set should be read as revisions that retain the source shape shown below. The
validated security impact is persistent local denial of indexing for the KCS
process handling the crafted scope, with final severity calibrated to Medium
because exploitation requires two large prepared revisions and an
operator-mediated local indexing action.

## Background

KCS stores normalized document instances and tries to reuse work across
successive revisions. For each index candidate, the CLI first applies a raw
input byte limit, prepares the current file into logical units, then, when a
prior normalized instance exists for the same path and profile, computes a unit
mapping between the old and new prepared-unit lists.

The byte gate is useful, but it is not a unit-count or pairwise-work budget:

```rust
// crates/kcs-cli/src/main.rs
let max_input_bytes = effective_max_input_bytes(repo);
let incremental_config = effective_incremental_config(repo)?;

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

Once a candidate passes that size check, KCS prepares logical units from the
current bytes:

```rust
// crates/kcs-cli/src/main.rs
let prepare = prepare_units(PrepareStageRequest {
    raw_hash: raw_hash.clone(),
    media_type: candidate.media_type.clone(),
    input_path: path.display().to_string(),
    tool_profile_hash: prepare_profile_hash.clone(),
})
.map_err(pipeline_to_kcs)?;
```

For PDFs, `prepare_units` makes one `PreparedUnit` per recovered page entry.
The important invariant is that the number of prepared units must be kept
within a resource budget before any all-pairs algorithm runs over revisions:

```rust
// crates/kcs-pipeline/src/prepare.rs
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
```

The local PDF helper can also pad a page vector up to the inferred page count.
We do not need that helper to prove the LCS bug, but it explains why a raw byte
limit alone is a weak proxy for the prepared-unit cardinality that later reaches
the mapper:

```rust
// crates/kcs-pipeline/src/prepare.rs
let page_count =
    kcs_adapter::deterministic::pdf_page_count_in_text(&String::from_utf8_lossy(bytes)).max(1);
let stream_pages = kcs_adapter::deterministic::pdf_stream_text_pages(bytes);
if !stream_pages.is_empty() {
    return normalize_pdf_page_count(stream_pages, page_count);
}
// ...
let mut pages = strings;
while pages.len() < page_count {
    pages.push(String::new());
}
pages.truncate(page_count);
```

From here, the normal threat model is straightforward: a lower-trust local
contributor controls document revisions in a scope, and the higher-trust KCS
operator runs `kcs index` or an equivalent reindex path over that scope. No
network listener or remote service is required.

## Vulnerability Details

The vulnerable transition begins after current units have already been prepared.
KCS loads the prior normalized instance for the same path, then calls
`map_units` with the complete previous and current unit arrays:

```rust
// crates/kcs-cli/src/main.rs
let previous =
    previous_instance_for_path(&task_store, &candidate.input_path, &markdown_profile_hash)
        .unwrap_or_else(|_err| {
            let _ = append_event_log(
                "KCS-I-INDEX-PREVIOUS-UNREADABLE-001",
                "prior normalized instance unreadable; indexing this file as Full",
                json!({ "input_path": candidate.input_path }),
            );
            None
        });
let mapping = previous
    .as_ref()
    .map(|previous| map_units(&previous.prepared_units, &prepare.prepared_units));
let incremental_hints = mapping
    .as_ref()
    .map(|mapping| incremental_hints_from_mapping(mapping, &prepare.prepared_units))
    .unwrap_or_else(|| all_changed_hints(&prepare.prepared_units));
```

One subtle point matters for remediation: this mapping is computed before the
later `incremental_config.enabled` branch chooses full mode. If we try to
mitigate the issue only by disabling incremental markdownization, we still have
to move or guard this `map_units` call; otherwise a previous instance continues
to trigger the expensive comparison.

Inside the pipeline crate, `map_units` does not check either unit count or the
product of the two dimensions. We immediately enter the LCS helper:

```rust
// crates/kcs-pipeline/src/prepare.rs
pub fn map_units(old_units: &[PreparedUnit], new_units: &[PreparedUnit]) -> UnitMapping {
    let pairs = lcs_fingerprint_pairs(old_units, new_units);
    let mut unchanged = Vec::new();
    let mut changed_unit_keys = Vec::new();
    let mut added_unit_keys = Vec::new();
    let mut removed_unit_keys = Vec::new();
```

The helper allocates the full dynamic-programming table before it knows whether
there are useful matching fingerprints:

```rust
// crates/kcs-pipeline/src/prepare.rs
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
```

For `m` old units and `n` new units, the table needs `(m + 1) * (n + 1)`
`usize` cells, and the nested loops perform `m * n` fingerprint comparisons.
On a common 64-bit Rust target, the cell storage alone is eight bytes per cell,
excluding the row-vector overhead introduced by `Vec<Vec<usize>>`.

That gives concrete resource sizes before we discuss allocator overhead:

| Old units | New units | Matrix cells | `usize` cell bytes |
| ---: | ---: | ---: | ---: |
| 10,000 | 10,000 | 100,020,001 | 763.09 MiB |
| 20,000 | 20,000 | 400,040,001 | 2.98 GiB |
| 50,000 | 50,000 | 2,500,100,001 | 18.63 GiB |

Those costs are paid merely to decide which unit fingerprints form an LCS. A
document pair with no shared fingerprints is not a cheap case: we still allocate
the same matrix and fill every cell before concluding that no anchors exist.

## Exploitability Analysis

The strongest practical route is a persistent local denial of indexing through
two prepared revisions at the same path. We first get a large-unit revision
indexed so KCS persists a prior normalized instance. We then provide another
large-unit revision and wait for the operator to index or reindex the same
scope. When `previous_instance_for_path` succeeds, KCS carries both unit arrays
into `map_units`, and the matrix dimensions are now attacker-influenced through
the revision contents.

The primitive is availability-oriented rather than memory-corruption-oriented.
We do not control a write outside the matrix, and the vulnerable operation is a
safe Rust allocation plus deterministic nested loops. The useful effect is that
we can force the victim KCS process to request a matrix far larger than the
logical value of the indexing task. Depending on host memory limits and
allocator behavior, the process may abort on allocation failure, be killed by
the operating system, or spend enough CPU time filling the table that indexing
is effectively wedged.

Several potential mitigations do not fully solve the issue on their own:

* Raw input size limits help keep enormous files out, but they do not directly
  bound `old_units.len() * new_units.len()`.
* Fingerprint matches may improve the final mapping result, but the full matrix
  is allocated before matches can reduce any later work.
* Switching the final markdownize decision to full mode is too late in the
  current caller, because `map_units` runs before that decision is made.

The main reliability constraints are also clear. The attacker needs a prior
completed normalized instance for the same path/profile, and both old and new
revisions must produce enough prepared units to exceed the victim's acceptable
memory or CPU budget. The attack does not by itself disclose secrets, cross a
network boundary, or execute code. Its persistence comes from the crafted
revisions remaining in the scope: each affected indexing attempt can revisit
the same expensive comparison until one revision is removed, remapped through a
safe fallback, or bounded by a patch.

## Proof of Concept

The accompanying PoC is intentionally local and synthetic. It mirrors the
matrix shape and nested loop of `lcs_fingerprint_pairs` using generated
fingerprint strings. The default run allocates only small matrices, then prints
exact estimates for larger cases without allocating them.

From this report directory:

```sh
cd poc
make run
```

Representative output from my bounded run:

```text
python3 lcs_matrix_probe.py
[+] bounded synthetic LCS probe
[+] 64x64: cells=4,225 comparisons=4,096 rust_matrix=33.01 KiB elapsed=0.0002s
[+] 128x128: cells=16,641 comparisons=16,384 rust_matrix=130.01 KiB elapsed=0.0007s
[+] 256x256: cells=66,049 comparisons=65,536 rust_matrix=516.01 KiB elapsed=0.0031s
[+] 512x512: cells=263,169 comparisons=262,144 rust_matrix=2.01 MiB elapsed=0.0132s
[+] large-size estimates only
[+] 10000x10000: cells=100,020,001 rust_matrix=763.09 MiB (not allocated)
[+] 20000x20000: cells=400,040,001 rust_matrix=2.98 GiB (not allocated)
[+] 50000x50000: cells=2,500,100,001 rust_matrix=18.63 GiB (not allocated)
```

The PoC does not create malformed files, does not touch a KCS repository, and
does not allocate the dangerous large matrices. It is meant to make the cost
equation easy to verify and to give reviewers a safe way to reproduce the
quadratic growth trend.

## Remediation

The invariant to restore is simple: KCS must never run an all-pairs unit
alignment unless the product of old and new unit counts is within an explicit,
tested work and memory budget. When the budget would be exceeded, the code
should fall back to a deterministic safe mapping, such as treating the interval
as changed/full, rather than trying to compute an exact LCS.

A minimal defensive shape is:

```rust
const MAX_UNIT_LCS_CELLS: usize = 2_000_000; // tune from production budgets

fn within_unit_mapping_budget(old_len: usize, new_len: usize) -> bool {
    old_len
        .checked_add(1)
        .and_then(|old| new_len.checked_add(1).and_then(|new| old.checked_mul(new)))
        .is_some_and(|cells| cells <= MAX_UNIT_LCS_CELLS)
}

pub fn map_units(old_units: &[PreparedUnit], new_units: &[PreparedUnit]) -> UnitMapping {
    if !within_unit_mapping_budget(old_units.len(), new_units.len()) {
        return full_changed_mapping(old_units, new_units);
    }

    let pairs = lcs_fingerprint_pairs(old_units, new_units);
    // existing exact mapping path
}
```

The caller should also avoid computing a mapping when incremental behavior is
disabled or when a higher-level policy has already selected full mode:

```rust
let mapping = if incremental_config.enabled {
    previous
        .as_ref()
        .map(|previous| map_units(&previous.prepared_units, &prepare.prepared_units))
} else {
    None
};
```

For a stronger long-term fix, replace the full `Vec<Vec<usize>>` table with a
bounded or linear-space alignment strategy. Hirschberg-style LCS can reduce
space, and a document-oriented anchored diff can often give good reuse hints
without exact all-pairs dynamic programming. Even with a linear-space mapper,
the `m * n` CPU budget still needs an explicit ceiling and a fallback path.

Regression coverage should include:

* a `map_units` test where `old_len * new_len` exceeds the configured budget and
  returns the fallback without allocating the matrix;
* boundary tests for the exact maximum permitted cell count and checked
  arithmetic overflow;
* a CLI pipeline test showing that `incremental.enabled = false` does not call
  `map_units` for a file with a prior instance;
* an integration fixture with two high-unit revisions that completes by taking
  the safe full/remap fallback instead of exhausting memory.

## Summary

The vulnerable code treats unit mapping as a small bookkeeping step, but the
implementation allocates and fills a matrix whose size is the product of two
revision-controlled unit counts. We traced the reachable local index path from
the raw byte gate, through preparation and previous-instance loading, into the
unbounded `lcs_fingerprint_pairs` sink. The safe PoC reproduces the quadratic
growth with synthetic units and computes the exact memory scale of larger cases
without allocating them.

The immediate fix is to put an explicit budget in front of exact LCS and to
fall back deterministically when the budget is exceeded. Variant analysis should
look for other places where KCS converts bounded input bytes into a larger
logical unit count and then performs pairwise comparison, per-unit reparsing, or
per-unit allocation without carrying a shared resource budget forward.
