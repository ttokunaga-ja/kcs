# Validation shard C3a closure

- Scan: `f78f5d0d-2752-47a7-8d8d-3371e09d3377`
- Target revision: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Closure: **3/3 exact candidates**
- Repository writes: **none**
- External network / credentials: **none**
- Safe controls: bounded target-runtime PDF (490 bytes), raw CAS object (65,536 bytes), task line (38,318 bytes), and task record set (64 records), all isolated under `/tmp`

| Ledger row id | Instance key | Advisory/source reference | Seed anchor | Root-control file:line | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-034 | KCS-R23-CAND-034:lexical-page-count-reparse-amplification | R23 deep discovery; no external advisory | crates/kcs-adapter/src/deterministic.rs:415-437 | crates/kcs-pipeline/src/prepare.rs:315-347 | untrusted indexed PDF with text and false page prefixes | unit padding plus per-hint whole-file parse | reportable | byte cap/OCR routing do not bound pages; 64-vs-1 bounded control | yes |
| KCS-R23-CAND-046 | KCS-R23-CAND-046:cas-whole-object-read-before-verification | R23 deep discovery; no external advisory | crates/kcs-core/src/cas.rs:78-100 | crates/kcs-core/src/cas.rs:78-100 | large valid CAS object in adopted store or supplied ref/hash | whole `fs::read` and digest before inspect/type/JSON checks | reportable | requires hash-consistent object; 64 KiB bounded control, no RSS stress | yes |
| KCS-R23-CAND-050 | KCS-R23-CAND-050:task-jsonl-unbounded-line-collections-records | R23 deep discovery; no external advisory | crates/kcs-pipeline/src/task.rs:129-186 | crates/kcs-pipeline/src/task.rs:140-184 | adopted task line, arrays, and unique records | unbounded line/serde allocation then BTreeMap retention | reportable | owner-only live store narrows source; bounded line/record controls, no OOM test | yes |
