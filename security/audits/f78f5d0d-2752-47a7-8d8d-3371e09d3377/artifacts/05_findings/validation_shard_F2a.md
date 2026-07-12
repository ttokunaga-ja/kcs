# R23 central validation shard F2a

Scope: exactly KCS-R23-CAND-065 at revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`. Validation was repository-read-only and network-free; it used an exact V10 supported-flow trace plus a bounded in-memory SQLite differential.

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives | Confidence | Score | Severity | Validation report |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-065 | KCS-R23-CAND-065:chunk-id-text-identity-collision | R23 discovery | crates/kcs-index/src/chunking.rs:60-76 | crates/kcs-index/src/chunking.rs:60-76 | equal-span normalized text can differ while the structural identity tuple remains fixed | rebuild rejects a known ID before JSONL append; SQLite and downstream consumers retain the same first row | suppressed | changed bytes/gen and partial-retry controls prevent a normal second body; direct store/library synthesis is outside the supported CLI path; no combined Rust regression added | no | high | 0.92 | none | artifacts/05_findings/KCS-R23-CAND-065/validation_report.md |
