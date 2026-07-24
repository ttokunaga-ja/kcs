# Q_hard pack + 20-person baseline corpus — Phase 1 requirements v2

Status: **approval proposal only**.  This is the requirements lock for the
user-requested Phase 1.  It creates no `eval-gen/` tree, manifests, fixtures,
source files, binary Office documents, images, KCS roots, or external API
calls.  Phase 2 is prohibited until this proposal is explicitly approved.

## 1. Boundary and input inventory

The two deliverables are separate both logically and physically:

| deliverable | purpose | facts / queries | output root |
| --- | --- | ---: | --- |
| A: Q_hard augmentation | difficult-class regression pack | 8 facts / 8 candidate queries | `eval-gen/qhard-a/` |
| B: baseline-comparison corpus | 20 independent persona mirrors plus normal and distractor material | 24 facts / 24 candidate queries | `eval-gen/corpus/p01..p20/` |

No answer, fact ID, planted fact text, distractor, file path, or generated
payload may be shared between A and B.  Query IDs are separate namespaces:
`qa01..qa08` for A and `qb01..qb24` for B.

**Recommended inventory reference:** Phase 2 B uses the already frozen v2
benchmark-stress inventory as a *profile reference only*, pinned by
`kcs.persona.pc-envelope/v2` (`71,979` bytes,
`1d49e79049b409ee5bd82d0b307db5055c2a58544df81858b77552ea82bff370`).
Persona language/locale weights are separately pinned by
`kcs.persona.pc-realism-profile/v2` (`36,811` bytes,
`a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05`).
It does not adopt `persona-core-v1`, which remains an unselected candidate with
cellwise incompatibility against the legacy source allocation.  This prevents a
small evaluation fixture from silently deciding the broader allocation question.

The Phase 2 route is deliberately independent of v2's legacy offline
gate-role labels:

| format | Phase 2 `index_path` |
| --- | --- |
| `md`, `txt`, recognized code | `offline` |
| `pdf_rasterized`, `pdf_text`, `docx`, `pptx`, `png`, `jpeg` | `online_ocr` |
| `xlsx_realism` | `unsupported` |

`xlsx_realism` is realism-only and may never have role `answer` or
`distractor`.  Audio is omitted rather than inventing an unsupported manifest
format outside the requested enum.

The manifest string `code` is explicitly allowed for a recognized source-code
carrier.  It is the `code` category named in the physical-condition contract,
uses `offline`, and is not silently collapsed into `txt` merely because the
illustrative file-row enum abbreviated that category.

**Folder-coordinate reference:** B additionally pins the frozen
`kcs.persona.pc-topology/v2` coordinate set (134,195 bytes,
`204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f`).
This pin supplies the 20 persona-specific leaf *coordinates* for a fixture
mirror; it does not create a KCS registry, claim a formal replay, or grant
materialization/G0 authority.  The B mirror has two non-interchangeable lanes:

```text
corpus/pNN/
  home/<one frozen scope_relative_path>/<direct-child basename>
  ambient-home/<unregistered recursive relative path>
```

Every Phase 2 fixture file row (A and B) adds these fields in addition to the
user-required ones: `persona_lane`, `scope_key`, `scope_relative_path`,
`file_name`, and `index_enrollment`.  They have the following exact meanings;
replace the `corpus/<persona>` prefix with `qhard-a/<persona>` for A.

| lane | required path and fields | evaluation rule |
| --- | --- | --- |
| `fixture_home` | `path` is exactly `corpus/<persona>/home/<scope_relative_path>/<file_name>`; the scope fields resolve to one pinned topology leaf and `file_name` is a separator-free direct-child basename | `index_enrollment="fixture"`; answers, distractors, and fixture filler may use this lane |
| `ambient_home` | `path` is exactly `corpus/<persona>/ambient-home/<ambient_relative_path>`; `scope_key=null`, `scope_relative_path=null` | `index_enrollment="excluded"`; answer, distractor, fact, and expected-target roles are forbidden |

`index_path` says which extractor route a carrier would use; it is not a claim
that the file is enrolled in the formal 20-person KCS campaign.  The fixture
may later be indexed for its own baseline comparison, but that is represented
by `index_enrollment="fixture"`, never by formal-scale authority.  This
distinction prevents a realistic recursive ambient file from being mistaken
for a nested managed file below a non-recursive KCS scope.

### Fixture-versus-formal-scale boundary (normative)

A (`qhard-a`) and B (`baseline-fixture-b`) are `payload_tier="fixture"`
artifacts.  They are source/recipe and small-corpus evaluation fixtures only.
Neither may be used as evidence of a formal persona-PC device root, a persona
with 100,000+ chunks, source-to-scope allocation, KCS chunk attestation,
capacity readiness, history/replay completion, an MVP latency denominator, or
the formal Recall denominator.  In this document, “persona mirror” means a
persona-local **fixture** slice, not a formal persona-PC root.

Approval of Phase 2 fixture generation does not issue G0 or authorize formal
scale materialization.  The `20 × 120,000` campaign is a separately approved
`payload_tier="formal-scale"` artifact with a different root, manifest,
source-plan, writer, KCS, history, and receipt chain.  It may not reuse,
extend, replace, or be aggregated with `eval-gen/corpus/pNN`.

Every Phase 2 manifest line therefore carries at least these additional
boundary fields:

```json
{
  "suite_id": "qhard-a-v1 | baseline-fixture-b-v1",
  "payload_tier": "fixture",
  "formal_scale_eligible": false,
  "formal_scale_attested": false
}
```

File lines additionally carry stable `logical_document_id`, `source_recipe_id`,
`owner_persona_id`, `planned_final_path`,
`materialization_state="spec_only"`, and
`count_basis="final_corpus_document"`.  Build inputs, Office specs,
intermediate raster PNGs, image prompts, manifest files, and KCS internals are
never counted as final corpus documents.  A separate
`sources/ledgers/fixture-boundary-v1.json` self-check ledger records the
fixture hash, counts, tier, and all-negative formal-scale authority; it is not
an additional manifest row kind.

## 2. Required output shape after approval

Phase 2 creates exactly the requested public structure:

```text
eval-gen/
  manifest.jsonl
  sources/
  office-specs/
  image-prompts/
  qhard-a/p01..p20/...      # A: separate difficult-class fixture mirror
  corpus/p01..p20/
    home/...                # B fixture direct-child scope mirrors
    ambient-home/...        # B excluded recursive-realism slice
```

`corpus/` is B only.  A's files live under `qhard-a/` in the same generated
project but carry their own fact/query namespace and are excluded from B's
file-count and OCR aggregate rows.  This avoids a misleading 20-person
baseline count while keeping the required top-level convention intact.  A's
listed answer parent is likewise a registered fixture scope root: its answer
and distractor are direct children of that parent, never nested below it.

Every Phase 2 file row has the exact fields required by the user contract.
Every answer fact has a fact row, and every candidate query has a query row.
Aggregate counts belong in the required Phase 2 self-check, not in an
additional manifest row type.

Every DOCX/PPTX file row references exactly one `office-specs/*.md` file.  Each
PDF/image answer or distractor references its source/build recipe under
`sources/`.  `image-prompts/` may contain prompts only for non-factual visual
decoration; it is never the source of fact-bearing words, values, axes, or
labels.

## 3. A: Q_hard augmentation allocation

| query | persona | fixture scope / pinned topology leaf | class | answer format / route | answer placement | distractor format / route | OCR units |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| qa01 | p02 | `p02-scope-05` / `services/checkout/prod/oncall/operations` | hard1 | `pdf_rasterized` / `online_ocr` | `qhard-a/p02/home/services/checkout/prod/oncall/operations/incident-brief.pdf` | raster PDF, same topic / nearby value | 3 |
| qa02 | p05 | `p05-scope-03` / `analytics/governance/data-dictionary` | hard1 | `pdf_rasterized` / `online_ocr` | `qhard-a/p05/home/analytics/governance/data-dictionary/data-governance.pdf` | raster PDF, same topic / nearby value | 3 |
| qa03 | p11 | `p11-scope-03` / `accounts/account-alpha/proposals` | hard1 | `pdf_rasterized` / `online_ocr` | `qhard-a/p11/home/accounts/account-alpha/proposals/customer-brief.pdf` | raster PDF, same topic / nearby value | 3 |
| qa04 | p15 | `p15-scope-02` / `recruiting/requisition-alpha/interviews/round-2` | hard1 | `pdf_rasterized` / `online_ocr` | `qhard-a/p15/home/recruiting/requisition-alpha/interviews/round-2/interview-review.pdf` | raster PDF, same topic / nearby value | 3 |
| qa05 | p01 | `p01-scope-01` / `work/products/product-alpha/architecture` | hard3 | `pptx` / `online_ocr` | `qhard-a/p01/home/work/products/product-alpha/architecture/latency-chart.pptx` | PPTX, same metric / wrong series | 4 |
| qa06 | p04 | `p04-scope-04` / `research/programs/model-alpha/experiments/results` | hard3 | `png` / `online_ocr` | `qhard-a/p04/home/research/programs/model-alpha/experiments/results/ablation-grid.png` | PNG, same axes / wrong point | 2 |
| qa07 | p12 | `p12-scope-02` / `support/escalations/active` | hard3 | `pptx` / `online_ocr` | `qhard-a/p12/home/support/escalations/active/queue-trend.pptx` | PPTX, same interval / wrong bar | 4 |
| qa08 | p18 | `p18-scope-09` / `quality/nonconformance/2026/open` | hard3 | `jpeg` / `online_ocr` | `qhard-a/p18/home/quality/nonconformance/2026/open/defect-map.jpeg` | JPEG, same legend / wrong cell | 2 |

Each hard1 answer is two raster-only PDF pages and each hard1 distractor is one
raster-only PDF page.  Each hard3 PPTX answer/distractor has two slides, and
each standalone image answer/distractor is one OCR image unit.  Thus A has 24
online-OCR units: 20 structured page/slide units and 4 standalone image units.
It also has eight offline context/filler Markdown files, for 24 files total.

## 4. B: 20-person baseline allocation

B contains 24 answers: 8 hard1, 8 hard2, and 8 hard3.  Every one has exactly
one paired same-topic distractor at minimum.  All 20 personas occur in at
least one answer row; four personas deliberately contain two independent facts
to model more complex local work.  Every path in the table is relative to the
corresponding `corpus/pNN/` root.

| query | persona | fixture scope key | class | answer format / route | answer path relative to `corpus/pNN/` | distractor placement | language |
| --- | --- | --- | --- | --- | --- | --- | --- |
| qb01 | p01 | `p01-scope-01` | hard2 | `docx` / `online_ocr` | `home/work/products/product-alpha/architecture/latency-review.docx` | same fixture scope, alternative decision | ja/en |
| qb02 | p02 | `p02-scope-05` | hard2 | `md` / `offline` | `home/services/checkout/prod/oncall/operations/recovery-window.md` | same fixture scope, adjacent window | en |
| qb03 | p03 | `p03-scope-04` | hard1 | `pdf_rasterized` / `online_ocr` | `home/security/incidents/reports/retention-decision.pdf` | same fixture scope, nearby threshold | ja/en |
| qb04 | p04 | `p04-scope-04` | hard2 | `md` / `offline` | `home/research/programs/model-alpha/experiments/results/ablation-notes.md` | same fixture scope, alternate run | en |
| qb05 | p05 | `p05-scope-09` | hard2 | `docx` / `online_ocr` | `home/forecasts/planning/scenarios/forecast-variance.docx` | same fixture scope, adjacent segment | ja/en |
| qb06 | p06 | `p06-scope-04` | hard3 | `pptx` / `online_ocr` | `home/programs/study-alpha/2026/cohort-a/run-001/analysis/assay-summary.pptx` | same fixture scope, wrong plotted cohort | en |
| qb07 | p07 | `p07-scope-01` | hard1 | `pdf_rasterized` / `online_ocr` | `home/research/sources/archive-alpha/box-001/ocr-transcripts/meeting-notes.pdf` | same fixture scope, nearby amount | en/fr/de/ja |
| qb08 | p08 | `p08-scope-06` | hard2 | `docx` / `online_ocr` | `home/roadmap/fy2026/q3/quarterly/scope-tradeoff.docx` | same fixture scope, competing option | ja/en |
| qb09 | p09 | `p09-scope-02` | hard3 | `pptx` / `online_ocr` | `home/research/study-alpha/2026/transcripts/interview-patterns.pptx` | same fixture scope, wrong bar group | en/ja |
| qb10 | p10 | `p10-scope-04` | hard1 | `pdf_rasterized` / `online_ocr` | `home/engagements/client-alpha/2026/phase-1/workstream-finance/deliverables/steering-note.pdf` | same fixture scope, nearby budget | en |
| qb11 | p11 | `p11-scope-01` | hard2 | `md` / `offline` | `home/accounts/account-alpha/plans/renewal-conditions.md` | same fixture scope, alternate condition | en/es |
| qb12 | p12 | `p12-scope-02` | hard2 | `md` / `offline` | `home/support/escalations/active/escalation-sla.md` | same fixture scope, adjacent SLA | ja/en |
| qb13 | p13 | `p13-scope-02` | hard1 | `pdf_rasterized` / `online_ocr` | `home/matters/matter-alpha/legal-hold/collection-01/working/hold-exception.pdf` | same fixture scope, wrong deadline | ja/en |
| qb14 | p14 | `p14-scope-03` | hard3 | `pptx` / `online_ocr` | `home/finance/close/2026/q1/2026-03/cash-bridge.pptx` | same fixture scope, wrong chart series | ja/en |
| qb15 | p15 | `p15-scope-02` | hard2 | `docx` / `online_ocr` | `home/recruiting/requisition-alpha/interviews/round-2/decision-summary.docx` | same fixture scope, alternate candidate outcome | ja/en |
| qb16 | p16 | `p16-scope-01` | hard1 | `pdf_rasterized` / `online_ocr` | `home/clinical/studies/study-alpha/2026/protocols/protocol-note.pdf` | same fixture scope, nearby limit | ja/en |
| qb17 | p17 | `p17-scope-01` | hard3 | `pptx` / `online_ocr` | `home/portfolio/projects/project-alpha/2026/construction/drawings/deviation-map.pptx` | same fixture scope, wrong region | ja/en |
| qb18 | p18 | `p18-scope-09` | hard1 | `pdf_rasterized` / `online_ocr` | `home/quality/nonconformance/2026/open/inspection-note.pdf` | same fixture scope, nearby tolerance | ja/en |
| qb19 | p19 | `p19-scope-03` | hard1 | `pdf_rasterized` / `online_ocr` | `home/learning/courses/course-alpha/2026/term-1/assignments/rubric-note.pdf` | same fixture scope, nearby score | ja/en |
| qb20 | p20 | `p20-scope-05` | hard1 | `pdf_rasterized` / `online_ocr` | `home/newsroom/investigations/story-alpha/2026/fact-check/source-memo.pdf` | same fixture scope, nearby date | ja/en |
| qb21 | p03 | `p03-scope-06` | hard3 | `png` / `online_ocr` | `home/compliance/frameworks/soc2/control-evidence/control-coverage.png` | same fixture scope, wrong plotted cell | ja/en |
| qb22 | p07 | `p07-scope-04` | hard3 | `jpeg` / `online_ocr` | `home/research/bibliography/zotero/exports/citation-network.jpeg` | same fixture scope, wrong node | en/fr/de/ja |
| qb23 | p16 | `p16-scope-03` | hard3 | `png` / `online_ocr` | `home/clinical/studies/study-alpha/2026/results/safety-grid.png` | same fixture scope, wrong panel | ja/en |
| qb24 | p20 | `p20-scope-05` | hard3 | `jpeg` / `online_ocr` | `home/newsroom/investigations/story-alpha/2026/fact-check/source-timeline.jpeg` | same fixture scope, wrong marker | ja/en |

Hard2 answers are intentionally split exactly four DOCX / four Markdown.  Their
eight distractors retain the corresponding answer format.  Hard3 answers are
split four PPTX / four standalone PNG/JPEG, and their eight distractors retain
the corresponding carrier type.  The file- and fact-level manifest records the
paired distractor ID; a distractor may never be an answer for another query.

For every row above, the answer path is exactly the pinned `scope_key`'s
topology path followed by one direct-child basename.  Its distractor uses the
same `fixture_home` scope and a different direct-child basename.  A generated
answer/distractor path with a segment below its listed leaf (for example
`.../architecture/nested/file.docx`) is invalid even if it remains below the
same persona root.

The 995 searchable B files (`720 offline + 275 online_ocr`) are distributed
across all 20 pinned fixture scopes of **each** persona: every p01--p20 scope
receives at least one `fixture_home` direct child.  Four non-factual filler
files per persona (80 total) instead occupy `ambient_home` paths from D6 up to
that persona's frozen planned Dmax (D6--D8), with at least one at the persona's
Dmax, to exercise the realistic recursive lane.  The one `xlsx_realism` file
per persona also lives in `ambient_home`.  Thus B has 915 `fixture_home` final
documents and 100 `ambient_home` documents; all global carrier and route counts
in §5 remain unchanged.  Ambient documents preserve their route declaration
for realism, but always have `index_enrollment="excluded"` and cannot be a
fact, answer, distractor, or expected retrieval target.

## 5. B file and route mix

The following 1,015 files are a small comparison fixture, not a 20 × 100,000
chunk corpus.  They preserve persona-local paths and use the selected inventory
only as a ratio reference.  They are never a source-plan input, formal device
root, source-file-count substitute, or capacity/history/performance receipt.

The active formal-scale goal remains separately defined: at W0, each persona
must have exactly 120,000 post-index distinct `(scope_key, chunk_id)`
contract-contributor endpoints (therefore more than 100,000); W5 additionally
has at least 60,000 history-only endpoints per persona.  A source file count,
planned quota, rendered page count, raw hash, CAS object count, database row,
or path alias does not satisfy that metric.  The formal-scale campaign has its
own approved source plan, fixed chunking configuration, 20 scope registries per
persona, three fresh replays, root-bound capacity gate, and post-index receipts.
None of those values is emitted or inferred by this Phase 2 fixture package.

The current formal envelope is 203,000 planned W0 source-intent slots and
2,400,000 planned current contract chunks per replay, but its allocation
successor is still unresolved.  Those planning totals may not be derived from
the fixture's largest-remainder carrier allocation.  Conversely, the fixture
may not later be extended, aggregated, or copied into the formal-scale root.

| manifest format | physical carrier subtype | files | index path | role constraints |
| --- | --- | ---: | --- | --- |
| `md` | Markdown | 260 | offline | includes four hard2 answers and four hard2 distractors |
| `txt` | `.txt` / `.log` / `.jsonl` | 160 | offline | filler and contextual timelines |
| `code` | recognized source code | 125 | offline | filler only unless a later normal query is added |
| `txt` | structured JSON / YAML / XML / SQL | 100 | offline | filler and same-topic context |
| `txt` | HTML / EML textual carrier | 50 | offline | filler and distractor context, never a hard answer here |
| `code` | notebook JSON carrier | 25 | offline | filler only |
| `pdf_text` | text-layer PDF | 90 | online_ocr | normal/filler only |
| `pdf_rasterized` | raster-only scan PDF | 24 | online_ocr | eight hard1 answers, eight hard1 distractors, eight filler scans |
| `docx` | Office Word document | 60 | online_ocr | four hard2 answers, four hard2 distractors, 52 fillers |
| `pptx` | Office slide deck | 40 | online_ocr | four hard3 answers, four hard3 distractors, 32 fillers |
| `png` / `jpeg` | standalone raster image | 61 | online_ocr | four hard3 answers, four hard3 distractors, 53 fillers |
| `xlsx_realism` | Office spreadsheet | 20 | unsupported | realism only; no fact/query/distractor role |
| **total** |  | **1,015** |  |  |

The Phase 2 generator must allocate these counts across p01..p20 using each
persona's language and folder attributes.  It may not normalize every person
to the same local mix or copy one persona's content into another persona root.

### 5.1 Per-person B inventory and language target

The following is the exact B-level file/route allocation.  `offline` and
`online_ocr` columns count files, while `unsupported` is one XLSX realism file
per persona.  Language targets apply to generated body-text segments after
deterministic largest-remainder allocation; facts may use the persona's stated
technical English, codes, units, and product names naturally.

| persona | domain / root theme | files | fixture_home | ambient_home | offline | online_ocr | unsupported | language target |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| p01 | software engineering / payments workspace | 54 | 49 | 5 | 42 | 11 | 1 | ja 70%, en 30% |
| p02 | SRE / service operations | 53 | 48 | 5 | 42 | 10 | 1 | en 100% |
| p03 | security and GRC / incident evidence | 50 | 45 | 5 | 34 | 15 | 1 | ja 70%, en 30% |
| p04 | ML research / model experiments | 50 | 45 | 5 | 39 | 10 | 1 | en 100% |
| p05 | BI analytics / quarterly reporting | 53 | 48 | 5 | 37 | 15 | 1 | ja 75%, en 25% |
| p06 | life science / assay study | 50 | 45 | 5 | 35 | 14 | 1 | en 100% |
| p07 | humanities archive / citation recovery | 51 | 46 | 5 | 34 | 16 | 1 | en 55%, fr 15%, de 15%, ja 15% |
| p08 | product management / roadmap | 54 | 49 | 5 | 37 | 16 | 1 | ja 70%, en 30% |
| p09 | UX research / interview sessions | 50 | 45 | 5 | 38 | 11 | 1 | en 75%, ja 25% |
| p10 | consulting / client engagement | 50 | 45 | 5 | 33 | 16 | 1 | en 100% |
| p11 | account executive / opportunity | 50 | 45 | 5 | 37 | 12 | 1 | en 80%, es 20% |
| p12 | support / customer queue | 50 | 45 | 5 | 40 | 9 | 1 | ja 75%, en 25% |
| p13 | legal / hold matter | 50 | 45 | 5 | 33 | 16 | 1 | ja 75%, en 25% |
| p14 | finance / close review | 50 | 45 | 5 | 33 | 16 | 1 | ja 80%, en 20% |
| p15 | people operations / requisition | 50 | 45 | 5 | 34 | 15 | 1 | ja 80%, en 20% |
| p16 | clinical research / protocol evidence | 50 | 45 | 5 | 33 | 16 | 1 | ja 70%, en 30% |
| p17 | construction / project quality | 50 | 45 | 5 | 34 | 15 | 1 | ja 80%, en 20% |
| p18 | manufacturing quality / lot inspection | 50 | 45 | 5 | 38 | 11 | 1 | ja 75%, en 25% |
| p19 | education / assessment | 50 | 45 | 5 | 34 | 15 | 1 | ja 75%, en 25% |
| p20 | investigative journalism / evidence chain | 50 | 45 | 5 | 33 | 16 | 1 | ja 70%, en 30% |
| **total** |  | **1,015** | **915** | **100** | **720** | **275** | **20** |  |

Within each persona, the generator uses the frozen 15-family persona weights
as the first allocation pass, maps them to the strict Phase 2 manifest carrier
vocabulary in §5, then reconciles to the exact global format counts with a
deterministic largest-remainder tie-break of persona ordinal then family
ordinal.  The Phase 2 manifest is the authoritative emitted per-person format
table and must be checked against both this route allocation and the referenced
persona profile; it must not silently flatten the 20 local mixes.

### 5.2 Required family-to-carrier delta ledger

The 15-family reference cannot be claimed as an exact ratio-preserving copy in
this small fixture.  The following mapping is mandatory and every intentional
loss or consolidation is recorded per persona in the self-check ledger.

| reference family | Phase 2 manifest carrier | delta policy |
| --- | --- | --- |
| `md` | `md` | retain as Markdown |
| `txt_log` | `txt` | retain as text/log carrier |
| `code` | `code` | retain recognized code |
| `structured_text`, `csv_tsv`, `html_eml` | `txt` | preserve physical subtype in path/spec; consolidate manifest route carrier |
| `ipynb` | `code` | notebook JSON under the offline code carrier |
| `pdf_text` | `pdf_text` | retain, but route through `online_ocr` for this Phase 2 contract |
| `pdf_scan` | `pdf_rasterized` | retain only as raster-only PDF |
| `docx`, `pptx` | same | retain Office carrier and use an Office specification |
| `xlsx` | `xlsx_realism` | cap at one unsupported realism file per persona; no answer/distractor use |
| `image` | `png` or `jpeg` | retain as rendered standalone image |
| `media`, `domain_binary` | not emitted | intentional small-fixture omission; never silently counted as searchable |

For each `persona_id × reference_family`, the final self-check ledger records
`reference_weight_bp`, `projected_count`, `emitted_count`, `delta_count`,
`carrier`, and an enumerated `delta_reason`.  It must show both reference pins
above and fail if a row is missing or if a supposedly retained carrier is
emitted under another route.

Language verification uses only authored natural-language body segments:
paragraphs, list text, captions, chart labels, and Office body text.  It
excludes paths, filenames, IDs, URLs, syntax-only keys, and source-code tokens.
Each persona's segment counts are apportioned from the pinned language weights
by deterministic largest remainder and the self-check reports target versus
emitted segments.  This prevents English technical identifiers from being
mistaken for a change to the persona language profile.

## 6. Difficulty-class invariants

### hard1 — raster scan PDF

Each hard1 answer/distractor has a TeX source plus an explicit build recipe:

```text
latexmk -pdf -interaction=nonstopmode -halt-on-error source.tex
pdftoppm -r 200 -png source.pdf raster/page
img2pdf --output final.pdf <ordered-raster-page-arguments>
pdftotext -enc UTF-8 final.pdf -
```

The final `pdftotext` output, after whitespace removal, must be empty.  The
fact text is rendered into the raster image before `img2pdf`; a TeX PDF with a
retained text layer is rejected.  Every final PDF is <=5 MiB and <=20 pages.
`<ordered-raster-page-arguments>` is an explicit recorded PNG list, never a
shell glob.  “Empty” means a strict UTF-8 `pdftotext` stdout decoded and
stripped of Unicode whitespace has zero code points.

### hard2 — paraphrase with zero content-token overlap

For each hard2 row, authoring records the query content-token set and the
answer-body content-token set.  Before Phase 2 is accepted, both sets are
normalized by UTF-8 strict decode, NFC, NFKC width folding, Unicode casefold,
katakana-to-hiragana folding, and removal of number-group separators.  The
validation compares nouns, verbs, numeric tokens, and Latin/English tokens;
their intersection must be empty.  Each manifest query row has
`"lexical_overlap_expected": []`, and the Phase 2 self-check supplies one
normalization/equality rationale per hard2 query.

The pinned profile is `kcs.qhard.content-token/v1`.  It records the Unicode
and tokenizer/dictionary versions, kana-to-hiragana range, Latin-token rule
(including accented Spanish), noun/verb lemmatization rule, and compound split
rule (`read/write/admin` supplies all searchable components).  It removes group
separators only inside numeric runs and deliberately does **not** translate
Japanese numeral words such as `三千六百` into Arabic digits.  The comparison is
over normalized surface forms and available lemmas; paths, filenames, IDs, and
syntax-only tokens remain excluded.

The semantic relation must remain recoverable by paraphrase or indirect unit
description, not by copying a noun, verb, number spelling, or English token
from the answer.  The test is applied to the actual DOCX-extracted or Markdown
body, not merely to the Office instruction draft.

### hard3 — rendered figure/table facts

All fact-bearing labels, values, axes, and legend text are rendered by
matplotlib, PIL, or TeX-to-PNG.  The primary answer carriers are PPTX slides
with the rendered image embedded at the specified slide position and standalone
PNG/JPEG files.  Every PPTX/PNG/JPEG is <=5 MiB; each PPTX has <=20 slides.

Diffusion-generated imagery is permitted only for decoration with no factual
text, axes, numbers, labels, or legend.  Each Office specification states the
complete slide/body text, image filename, image insertion position, and image
alt text.  Alt text must be generic and non-factual.  It does not request a
separately exported PDF copy of DOCX/PPTX.

### 6.4 Per-artifact validation receipts and evaluation admission gate

The requested top-level layout is retained by placing validation artifacts
under `sources/validation/`:

```text
sources/validation/hard1-raster-receipts.jsonl
sources/validation/hard2-lexical-receipts.jsonl
sources/validation/hard3-render-receipts.jsonl
```

At source-only Phase 2, these are declared receipt schemas with
`observation_state="planned"`; they cannot prove a generated final file.
Admission to fixture evaluation requires one independently recomputed
`observation_state="observed"` receipt for every hard answer and distractor.
The validator reads the final carrier and manifest query/fact rather than
trusting a token array or an Office specification.

| class | minimum observed receipt binding | fail-closed conditions |
| --- | --- | --- |
| hard1 | source TeX SHA-256, exact ordered build argv, ordered raster PNG path/hash/dimensions, final PDF SHA-256/page count/bytes, and `pdftotext` argv/version/exit/stdout hash/non-whitespace count | direct text-layer TeX PDF, a final-PDF replacement, nonzero extracted text, unordered/missing raster provenance, or size/page violation |
| hard2 | answer carrier SHA-256; actual extracted-body SHA-256; extractor ID/version/text scope; token-profile ID; query and answer token-set hashes; observed intersection; human semantic-paraphrase rationale | extraction failure, undecodable input, empty content-token set, nonempty intersection, or a clean Office spec whose final DOCX header/footer/table/text box introduces an overlap |
| hard3 | renderer ID/version; source script and fact-asset SHA-256/dimensions/regions; carrier path; PPTX slide/media-part/hash binding or standalone image hash; non-media factual-token scan | missing/replaced embedded asset, diffusion asset as fact carrier, factual values/labels in slide XML, notes, comments, alt text, properties, ChartML, editable cells, filename, PNG text, EXIF/XMP, or image comments |

For a DOCX hard2 receipt, extraction covers visible paragraphs, tables,
headers/footers, and text boxes after Office materialization.  For Markdown it
uses the final strict UTF-8 bytes.  For a PPTX hard3 receipt, the designated
slide relationship must resolve to a losslessly embedded rendered PNG with the
recorded hash; generic alt text is allowed but cannot contain fact-bearing
tokens.  A standalone PNG/JPEG receipt additionally checks decode and rejects
fact-bearing metadata.  Required negative tests mutate case/NFC/NFKC/kana and
number groups, compounds, accented Latin, a DOCX header/table/text box, a
text-layer PDF, an embedded image, and a PPTX textual/alt-text fact leak.

## 7. Fact uniqueness and distractor rules

- Every `fact_id` is unique across A and B.
- The planted answer fact occurs in exactly one answer file across the entire
  generated project.
- Each answer has at least one same-topic distractor with a deliberately
  near-but-not-equal value, series, date, threshold, or entity.
- A distractor carries `role="distractor"`; it must never accidentally contain
  the exact planted fact or be listed in `expected`.
- `ambient_home` files are always `role="filler"`, `class=null`, have no fact
  row, and never appear in an `expected` result.
- File size is <=5 MiB.  PDF/PPTX page/slide limits are checked individually,
  not only in aggregate.

At source-only Phase 2, `logical_document_id`, `source_recipe_id`, and owner
persona identity are unique for every final document.  After a future fixture
build, a separate observed build receipt records `content_sha256`, inode or
equivalent identity, hard-link count, symlink target/null, clone/reflink
status, and reuse disposition.  It rejects a shared final file/inode/link
across personas; fact-bearing answer/distractor payloads also reject a
cross-person content hash match.  Non-factual template repetition requires an
explicit allowlist and is never counted as a final corpus document.

## 8. Page count and OCR-cost forecast

OCR units are counted as `PDF pages + DOCX converted pages + PPTX slides +
standalone image units`.  This is a forecast only; it makes no external API
request.

| deliverable | PDF pages | DOCX converted pages | PPTX slides | standalone images | structured units | total OCR units |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 12 | 0 | 8 | 4 | 20 | 24 |
| B | 258 | 150 | 90 | 61 | 498 | 559 |
| **total** | **270** | **150** | **98** | **65** | **518** | **583** |

B's 258 PDF pages comprise 230 text-layer PDF pages and 28 raster-PDF pages.
The eight hard1 B answers and eight hard1 B distractors are one raster page
each; four raster filler PDFs have two pages and four have one page.
No individual document exceeds the 20-page/slide limit.  Using the documented
planning rate of **$2 per 1,000 pages for OCR Batch** (and $4 per 1,000 for
sync OCR) in [the MVP scope](../docs/09-mvp-scope.md), the forecast is
**$1.17 Batch** or **$2.34 sync** for 583 units, excluding storage, egress,
retries, and any optional enhancement pass.

This is a **fixture-only** OCR forecast.  It is not a formal-scale OCR,
storage, capacity, latency, or cost estimate and must not be extrapolated to
the `20 × 120,000` payload.  Formal-scale OCR cost remains unestimated and
unapproved until its separate emitted-document, conversion, and post-index
receipts exist; `index_path="online_ocr"` in this proposal does not authorize
a remote OCR/API invocation.

## 9. Required Phase 2 self-check additions

In addition to the user's required checkboxes, Phase 2 must emit aggregates for
both A and B separately:

- facts, queries, answer files, distractors, filler files, and unsupported
  realism files;
- class counts and answer-format distribution;
- `offline`, `online_ocr`, and `unsupported` file counts;
- PDF pages, DOCX converted pages, PPTX slides, standalone image units, and
  the above cost forecast; and
- per-person B file count, `fixture_home`/`ambient_home` count, language mix,
  answer/distractor presence, and path containment checks;
- one pinned-topology resolution, direct-child result, and `scope_key` for
  every `fixture_home` document; and one ambient depth/exclusion result for
  every `ambient_home` document;
- the three planned/observed hard-class receipt counts and their evaluation
  admission status; and
- the fixture-boundary ledger hash plus `payload_tier="fixture"`, all-negative
  formal-scale authority, and the explicit statement that B has no observed
  KCS chunks, capacity receipt, history/replay receipt, or formal-scale result.

The self-check must fail if a `fixture_home` file is not an exact direct child
of its pinned topology leaf, or if an `ambient_home` file has a scope
registration, `.kcs` component, fact/answer/distractor role, or formal/Recall
accounting membership.  The 80-file ambient slice is reported as
`recursive_catalog_coverage="partial"`; it may not claim to realize the
separate 5,120-file formal robustness catalog.

`eval/golden-queries.jsonl` is not changed by this work.  The new manifest
queries remain candidates until a separate approval freezes any production
golden query set.

## 10. Separate formal-scale campaign requirements (not a Phase 2 output)

The active `20 × >100,000 chunks` objective is deliberately not weakened by
the small fixture.  Before its first physical write, the separately approved
formal-scale campaign must provide a versioned source-plan and receipt schema
that binds at minimum:

```text
payload_id, replay_id, persona_id
formal_device_root_id, formal_registry_root_id, scope_registry_sha256
chunking_config_sha256, adapter_set_sha256
source_plan_sha256, writer_plan_sha256
planned_source_file_count, observed_source_file_count
actual_current_contract_endpoint_count
actual_current_eligible_endpoint_count
actual_history_only_contract_endpoint_count
current_endpoint_set_sha256, history_only_endpoint_set_sha256
observed_after_index
```

For W0, the acceptance metric is the post-index cardinality of distinct
`(scope_key, chunk_id)` contract-contributor endpoints **per persona**;
exactly 120,000 current endpoints are required.  History-only endpoints do not
count toward W0.  W5 additionally requires the separate history endpoint
evidence defined by the formal contract.  A suite aggregate may not compensate
for a persona below the threshold.

The formal campaign has 20 direct-child managed scopes per persona and three
fresh-storage replays.  It separately attests path/registry/inode isolation,
source and history transitions, and root-bound capacity (raw, CAS,
index/WAL, history, staging, transient bytes/inodes, filesystem allocation
unit, free-space reserve, and 25% headroom).  Its source tree, manifest, OCR
conversion receipts, and roots are distinct from this fixture.

An `online_ocr` document may contribute to the formal 120,000 target only
after an approved contributor allocation and an accepted conversion receipt
containing `extractor_build_id`, `conversion_config_sha256`,
`input_file_sha256`, `extracted_text_sha256`, `extraction_status`,
`observed_chunk_count`, and rejection reason when not accepted.  Otherwise it
is non-contributor realism material.  This Phase 1/2 design uses synthetic
source and forecasts only; it neither authorizes nor performs a remote OCR/API
call.
