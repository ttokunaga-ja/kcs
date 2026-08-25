# Realistic-corpus dogfood evidence

Status: **historical, non-authorizing**. This is the compact evidence retained
from the 2026-07-24/25 dogfood indexing plan. The former API-key, paid-run,
configuration, repair, and execution instructions were removed. The statement
that child-scope generation was unimplemented described the measured 2026-07-24
binary only and is not a current product-status claim.

## Measured corpus and offline pass

| Observation | Historical value |
| --- | ---: |
| Corpus | 20 personas, 1,039 files, 44 MB |
| Leaf scopes in the manual pre-auto-scope run | 428 |
| Files normalized before OOXML repair | 869 / 1,039 |
| Pending OCR tasks in that run | 287 |
| Offline pass duration | about 12 minutes |
| Store size after the offline pass | 186 MB |

The 428-scope topology was measured before automatic child-scope creation. It
must not be reused as evidence for the current discovery implementation or its
Windows authority boundary.

## OOXML failure and recovery evidence

Thirty DOCX/PPTX packages contained namespace-rewritten relationship or content
type parts. Twenty-two were unreadable by LibreOffice, causing 18 scopes to fail
as a unit. The repair changed only the affected relationship/content-type XML;
afterward, all 124 Office inputs used by the conversion check were readable,
the corpus still contained 1,039 files, and the offline baseline completed for
428/428 manually initialized scopes with no reported indexing errors.

## Embedding-cost evidence

The investigation found three implementation gaps at the time: no embedding
Batch lane, a price constant for the wrong model, and provider responses without
usage being charged from an estimate. The subsequent H1 change added the Batch
lane, selected $0.20/1M sync versus $0.10/1M Batch pricing, and replaced the
`chars / 4` estimate with a CJK-aware estimate. Provider usage remained
unavailable rather than being represented as zero. The contemporary corpus
measurement found 936,873 normalized Markdown characters and a 9.3% CJK share;
the old estimator understated that sample by about 1.28x.

These figures are investigation evidence only. Current pricing, model behavior,
and implementation contracts must be taken from current code and canonical
documentation; no paid dogfood execution is authorized by this record.
