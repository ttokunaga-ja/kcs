# Validation: incremental unit mapping allocates a quadratic LCS matrix

- Candidate: `KCS-R23-CAND-007`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.99)**
- Method: **V1 bounded growth probe + V5 exact complexity proof + V10 trace**

## Evidence

Incremental mapping reaches `map_units` during index/reindex at `crates/kcs-pipeline/src/prepare.rs:208-253`. Its LCS implementation allocates `(m+1) × (n+1)` `usize` cells and fills the matrix at `crates/kcs-pipeline/src/prepare.rs:387-416`. No unit-count or work budget precedes this allocation; PDF-derived cardinality can independently be inflated.

The bounded probe executed 64, 128, 256, and 512 disjoint units. Matrix cells and elapsed work grew quadratically. The exact source equation yields about 800,160,008 bytes at 10,000×10,000, 3.2 GiB at 20,000×20,000, and 20 GiB at 50,000×50,000, excluding row overhead. Large cases were computed only. Evidence: `validation_artifacts/probe_output.json`.

## Counterevidence

Small ordinary documents complete quickly, and identical/partly matching fingerprints may reduce later processing but not matrix allocation. Input byte size does not directly bound derived unit count tightly enough.

## Closure

Reportable High: a persistent crafted revision can repeatedly exhaust the process during normal indexing. Use linear-space/bounded alignment with an explicit work budget and safe fallback.

