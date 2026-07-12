# Validation shard C3b closure

- Scan: `f78f5d0d-2752-47a7-8d8d-3371e09d3377`
- Target revision: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Closure: **2/2 exact candidates**
- Repository writes: **none**
- External network / credentials: **none**
- Safe controls: one bounded pure page-mapping model; all other evidence is immutable source trace

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-051 | KCS-R23-CAND-051:duplicate-page-index-content-misbinding | R23 deep discovery; no external advisory | crates/kcs-adapter/src/mistral_ocr.rs:356-395 | crates/kcs-adapter/src/mistral_ocr.rs:249-263 | approved remote OCR `pages[].index` and markdown | hint-key acceptance then Done persistence at crates/kcs-pipeline/src/markdownize.rs:476-511 and crates/kcs-cli/src/main.rs:6674-6789 | reportable | normal provider should be well formed; bounded exact model and V10 trace close deterministic mapping | yes |
| KCS-R23-CAND-058 | KCS-R23-CAND-058:model-list-unbounded-but-unreachable | R23 deep discovery; no external advisory | crates/kcs-adapter/src/gemini_embedding.rs:84-118 | crates/kcs-adapter/src/catalog.rs:386-400 | CLI embedding via crates/kcs-cli/src/main.rs:7139-7153 | latent model-list `into_json` at gemini_embedding.rs:89-95, gated by early return at 85-88 | suppressed | real path fixes immutable model and does not thread declared embedding model; CAND-023 remains separate | no |
