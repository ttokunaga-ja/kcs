# Dogfood realistic-corpus investigation — 20 use-case folders for Codex to generate

Status: investigation / design brief (2026-07-24). Not yet approved for generation.
Consumer: Codex (Office-generation plugins + image-generation plugins).
Author context: written after the baseline gate closed (22/24). Remaining user-side
Done item = **dogfood on realistic data**. This document is the research + design
that lets an AI (Codex) create the 20 realistic use-case folders.

---

## 0. Purpose and non-goals

**Purpose.** Produce a small, *realistic* knowledge-work corpus — 20 use-case
folders whose **file names, content, and formats look like a real person's actual
folders** — so Kio can be dogfooded on realistic data and (optionally) measured
with a realistic query set. The target user is a developer/researcher
(local-first archive; "データはローカル、計算は最強の AI").

**This is NOT.**
- Not the current *synthetic* baseline fixture (`eval-gen/corpus/pNN`), which has a
  realistic **topology** but synthetic filenames/content (`utility-029.rs`,
  `worklog-009.md`, `trend-figure-046.png`). We reuse its topology, replace its
  content.
- Not the formal-scale `20 × 120,000` campaign (separate root, source-plan,
  receipts — see `tasks/q-hard-20persona-phase1-requirements-v2.md` §1). This is a
  **fixture-tier**, hundreds-of-files corpus.

**Primary axis = realism.** Eval-queryability (planted facts + queries) is a
valuable *secondary* layer, kept optional and clearly separated (§6).

---

## 0.5 MANDATORY methodology — real pipeline only, plus real history (user ruling 2026-07-24)

Non-negotiable. Any behavior that only holds for a shortcut is rejected.

- **Codex creates ONLY ordinary files and folders** (Office / PDF / Image / Text)
  in a plain directory tree. **Codex must NEVER write anything under `.kio`** — not
  objects, not index DBs, not manifests-in-place-of-indexing. `.kio` is created and
  populated **exclusively by the real Kio pipeline**.
- **The real Kio pipeline does everything downstream**, in the real order:
  `kio init` / `kio index --approve --online` → scan (direct-child files) →
  **prepare** (Office→PDF **convert**, PDF text-layer extract) → offline
  markdownize → **CAS store into `.kio`** → enqueue + run **OCR (Mistral Batch)** for
  Office/scan-PDF/image → enriched markdownize → **embedding (Gemini)** → FTS +
  vector index. No step is faked or bypassed. `.kio` scopes for subfolders are the
  pipeline's own auto-created child scopes, never hand-made.
- **History is generated through the pipeline, not fabricated.** After the initial
  tree is created and indexed, **Codex mutates the ordinary files** — delete, edit,
  add, and **move/rename folders and files** — and the pipeline is re-run so Kio's
  own snapshot/commit DAG records real history. This is what exercises Kio's core
  value (time-travel, `--all-history`, `--include-deleted`, rename raw_hash
  identity — the three north-star scenarios). The mutation rounds are part of the
  deliverable, not an afterthought.
- **No use-case-deviating, test-only content.** Every file, every mutation must be
  something a real person in that role would plausibly have or do. Nothing exists
  solely to trip a code path.

**The four phases (uniform for ALL folders):**

1. **Create** — Codex generates the initial realistic folder tree + files (Office
   via Office plugin, images via image plugin, PDFs, text/code Codex writes
   directly). Plain files only.
2. **Index** — the operator runs the real Kio pipeline (`kio init` + `kio index
   --approve --online`) over the tree. Kio makes the `.kio`, converts Office→PDF,
   OCRs, embeds, indexes. → commit #1 (the "initial" snapshot).
3. **Evolve (history)** — Codex performs realistic mutations in rounds (a sprint of
   edits/adds; a folder reorg/rename; a cleanup that deletes stale files). Re-index
   after each round → commits #2..#N. This is the real history.
4. **Measure** — search / time-travel / `--all-history` / `--include-deleted` over
   the resulting scopes (optionally against a planted query set, §6).

The existing synthetic fixture already followed phases 1-2 correctly (Codex wrote
plain files; `register_fixture.py` ran real `kio index`; no `.kio` was
hand-authored). This round (a) makes the phase-1 content **realistic** and (b) adds
phase 3 (**real mutation history**), which the synthetic fixture never exercised.

---

## 1. Kio pipeline coverage the corpus MUST exercise

Authoritative format → lane map (cited from `crates/kio-pipeline/src/{scan,prepare}.rs`,
`crates/kio-adapter/src/{office_convert,mistral_ocr,deterministic,pdf_decode}.rs`,
`docs/07-adapter-spec.md`). Extension → MIME happens once in `scan.rs:859-886`;
anything not in the table becomes `application/octet-stream` and is content-sniffed.

| Format | Lane | Searchable? | Costs $ (OCR) | Plugin to generate |
|---|---|---|---|---|
| `.md` `.markdown` | offline deterministic | yes | no | Codex writes directly |
| `.txt` `.log` | offline (fenced) | yes | no | Codex writes directly |
| code `.rs .py .ts .js .go .java .c .cpp .sh .rb .php` | offline (fenced, lang hint) | yes | no | Codex writes directly |
| structured text `.json .yaml .xml .html .eml .csv .tsv .sql .ipynb` | offline passthrough **iff sniffs as UTF-8 text** (no structural parse) | yes | no | Codex writes directly |
| **PDF, text-layer** | offline baseline **+** online OCR enhancement | yes | enhancement only | Word/PPT "export PDF", or a PDF writer |
| **PDF, scanned/raster (no text layer)** | **online OCR only** | only after OCR | **yes** | image-gen → render pages → image-only PDF |
| **`.docx`** | convert→PDF (needs `soffice`) → offline text + OCR enhancement | yes | enhancement | **Word plugin** |
| **`.pptx`** | convert→PDF, **1 slide = 1 page** → offline + OCR | yes | enhancement | **PowerPoint plugin** |
| **image `.png .jpg .jpeg .webp .gif`** | **online OCR only**, **1 image = 1 page** | only after OCR | **yes** | **image-gen plugin** |
| **`.xlsx`** | **UNSUPPORTED — archived, never searchable** (`prepare.rs:126-129`, spec `07 §5.1`) | **no** | no | Excel plugin (realism + tests skip path) |
| legacy `.doc .ppt .xls`, `.tiff .bmp .heic .svg`, binary, audio/video | **skipped** (`unsupported_inputs` / unrecognized binary) | no | no | — (include a few to test skip) |

**Coverage requirement:** across the 20 folders, the corpus must collectively hit
**every lane** — offline-text, offline-text-layer-PDF, OCR-scanned-PDF, OCR-docx,
OCR-pptx, OCR-image, and the **unsupported-skip** path (xlsx + one binary). A
dogfood that never OCRs a scan or never trips the xlsx-skip is not exercising the
whole product.

---

## 2. Scope-model constraint on folder layout (NON-RECURSIVE)

Confirmed in code + spec (`scan.rs:155-247` `collect_direct_candidates` does a single
`read_dir` and skips directories; `docs/03-data-model.md:264-270`):

- **One `.kio` indexes only files DIRECTLY in its folder.** `kio index`
  auto-creates a **child `.kio`** in each subfolder that contains target files —
  **except** ignored subtrees and **VCS repo roots** (a folder with `.git` is
  skipped unless `[scope] index_vcs_repos = true`).
- Files that sit only in subfolders of a scope root (with no `.kio` there) are the
  `ambient-home/` "recursive-realism" slice — present on disk, **invisible to
  search**. The existing fixture uses exactly this split (`home/` = indexed direct-child
  scopes; `ambient-home/` = excluded realism).

**Design implications for Codex:**
1. A realistic nested tree is fine — every file-bearing folder becomes its own
   scope (auto). Keep each folder's file set as the searchable unit.
2. **Do NOT drop a real code repo with a `.git`** into an indexed area (it will be
   skipped) — use plain `repos/<name>/docs/` folders instead, matching the existing
   topology.
3. Reuse the **20 leaf folders/persona** frozen in an accepted Rust
   `kio-eval persona plan` artifact: e.g. SRE = `desktop/active-incident`,
   `changes/deployments/production`, `infrastructure/terraform/environments`,
   `downloads/inbox/diagnostic-bundles`; legal = `matters/matter-alpha/correspondence`,
   `mail/outlook/legal-hold/recent`, `archive/legal/matters/…`. These are excellent —
   keep them; only the files inside change.
4. Soft limit **10,000 files/scope** — irrelevant at this scale (~30-50 files/persona).

---

## 3. Plugin assignment and what "realistic" requires per format

| Layer | Plugin | Realistic output to aim for | Notes / gaps |
|---|---|---|---|
| notes/logs/config/code/data | none (Codex writes bytes) | real prose notes, changelogs, meeting minutes, terraform/yaml, source files, JSON/CSV exports, `.ipynb` | Free lane. json/html/ipynb are indexed as **raw text** (no structural parse) — realistic content still fully searchable. |
| Word docs | **Word/Office plugin** | reports, design docs, memos, contracts, SOPs — with **headings, tables, headers/footers, styles** | Needs `soffice` (LibreOffice) on the KIO-index machine or docx is skipped (`office_conversion_unavailable`). OOXML embeds timestamps → non-deterministic bytes on re-gen (§4). |
| slide decks | **PowerPoint plugin** | pitch decks, QBRs, incident reviews, research readouts — slides with **charts, diagrams, embedded images** | 1 slide = 1 OCR page. Same `soffice` requirement. |
| spreadsheets | **Excel plugin** | budgets, trackers, close schedules, test matrices | **Realism only** — Kio archives but never searches xlsx. Good for exercising the skip path; do NOT put a fact/answer only in xlsx. |
| charts / diagrams / figures | **image-gen (chart/diagram)** | matplotlib/PIL/mermaid-style charts, architecture diagrams, dashboards, control-coverage grids | Fact-bearing figures = the hard3 carrier. Must render values/labels/axes into the image (not into slide text) if used as an OCR answer. |
| scanned documents | **image-gen (document/photo)** | photographed whiteboards, signed PDFs, scanned invoices/receipts, lab printouts, ID-less forms | The **scanned-PDF / image OCR** carrier (hard1). Must have **no text layer** — render text into pixels, then wrap image-only into PDF, or keep as png/jpeg. |
| decorative photos | image-gen (diffusion) | product photos, site photos, cover images | Decoration only; must carry **no factual text** if you also plant queries. |

**Capability gaps to verify before generation (Codex-side):**
- Can the image-gen plugin produce a **text-in-pixels** scanned-look document/chart
  (needed for OCR carriers), not just decorative art? If not, use
  matplotlib/PIL/TeX→PNG for fact figures and reserve diffusion for decoration
  (this is exactly the split `q-hard §6.3` mandates).
- Is **LibreOffice `soffice`** present on the machine that will run `kio index`? If
  not, the docx/pptx lane is inert (skipped, not an error). Confirm or install.
- Does the Office plugin let you control body text precisely (needed if a docx is a
  paraphrase answer)? If not, keep Office files as filler/realism only and put
  planted answers in md/PDF/image.

---

## 4. Determinism and environment constraints

- **OOXML (docx/pptx) are non-deterministic** — the ZIP embeds wall-clock
  timestamps + doc IDs, so regenerating "the same" file yields different bytes →
  different `raw_hash` → re-work. Kio normalizes the **converted PDF**'s dates
  (`office_convert.rs:275-313`) but **not** your source file. For a dogfood corpus
  this is usually fine; if you want a **frozen** corpus (stable identity across
  runs), generate each file **once** and reuse the exact bytes (don't re-emit).
- **Scanned/OCR carriers must have no decodable text layer** (`is_probably_real_text`
  gate) — render to raster and wrap image-only.
- **Text is hard-blocked from OCR** (privacy + ~10× cost) — you cannot force a
  `.txt` through OCR; the lane is chosen by format.
- **Converter presence** decides the whole Office lane — verify `soffice` (or the
  `KIO_OFFICE_CONVERTER` env) up front.

---

## 5. OCR cost model and budget

Mistral OCR bills **per page**, Batch lane **$2 / 1,000 pages**, **+~25% for
bbox_annotation (default ON)**. Page counts: PDF page = 1, docx = rendered pages,
pptx = slides, **image = 1 page**. Text/code/structured cost **$0** (offline).

The existing synthetic fixture was **583 OCR units ≈ $1.17 Batch** (270 PDF pages +
150 docx pages + 98 slides + 65 images). A realistic corpus of similar size lands
in the same order (**~$1–2**). **Budget scales with the count of Office+image+scan
files** — pick a per-persona OCR-file count and multiply. Recommend a hard ceiling
(e.g. $3) and the existing `ocr_batch_driver.py` ceiling guard when generating.

---

## 6. Eval-queryability (optional secondary layer)

Two modes; **recommend the hybrid**:

- **(a) Pure realistic dogfood** — realistic files, no planted facts. Simple.
  Validates the pipeline end-to-end and lets the user try their own ad-hoc queries.
  Produces **no Recall number**.
- **(b) Realistic + planted query set** — reuse the frozen difficulty classes but
  with **realistic carriers**, extending the 24-query baseline to realistic data:
  - **hard1 (OCR)**: a realistic *scanned* doc (signed PDF / photographed whiteboard
    / scanned receipt) whose fact lives **only in pixels**.
  - **hard2 (paraphrase)**: a realistic docx/md where the answer is phrased with
    **zero content-token overlap** with the query (natural business paraphrase).
  - **hard3 (figure)**: a realistic chart/slide where the fact is a **rendered
    value/label**.
  - Keep the fact-uniqueness + near-miss-distractor + filler rules from
    `q-hard §6-7` so Recall@10 is meaningful.

**Recommended hybrid:** mostly realistic filler + **2-3 planted queries per persona**
(≈ 40-60 realistic queries total) so we get a realistic-data Recall number that
complements the frozen 24. Keep the planted-fact machinery lightweight vs the
formal q-hard receipts (this is dogfood, not the formal admission gate).

---

## 7. The 20 use cases (domains, folders, realistic file mix, plugin map)

Domains and leaf-folder vocabulary are already defined and realistic — reuse them.
Below: the realistic **file** direction per domain. "OCR files" = docx+pptx+pdf-scan+image.

| # | domain | representative real folders | realistic file examples (real names + content) | Office/image plugin load | lang |
|---|---|---|---|---|---|
| p01 | payments eng | `work-items/code-reviews`, `repos/product-alpha/docs`, `decision-records` | `adr-0007-idempotency-keys.md`, `settlement-retry.rs`, `pci-scope-review.docx`, `latency-review.docx`, `throughput-dashboard.png` | Word, chart img | ja70/en30 |
| p02 | SRE / ops | `desktop/active-incident`, `changes/deployments/production`, `infrastructure/terraform/environments` | `incident-2026-07-postmortem.md`, `runbook-failover.md`, `recovery-window.md`, `terraform/prod.tf`, `latency-slo.png`, `oncall-review.pptx` | PPT, chart img | en |
| p03 | security / GRC | `security/assessments/pentest-reports`, `privacy/assessments/risk-register`, `desktop/active-audit` | `pentest-findings.docx`, `soc2-control-coverage.png` (scanned matrix), `dpia-payments.docx`, `evidence-log.csv` | Word, scan img | ja70/en30 |
| p04 | ML research | `desktop/current-experiment`, `cloud/team/research-shared`, `documents/reference/research-methods` | `ablation-notes.md`, `train.py`, `results.ipynb`, `model-card.docx`, `loss-curve.png`, `readout.pptx` | PPT, chart img | en |
| p05 | BI analytics | `dashboards/sales/published`, `reports/operations/monthly`, `exports/warehouse/snapshots` | `q3-forecast.docx`, `regional-forecast.docx`, `kpi-deck.pptx`, `revenue-by-region.png`, `warehouse-export.csv`, `budget.xlsx` (skip) | PPT, Excel, chart img | ja75/en25 |
| p06 | life science | `downloads/inbox/instrument-drops`, `archive/completed-studies/2020-2025`, `statistics` | `assay-summary.pptx`, `protocol.docx`, `plate-readout-scan.pdf` (scanned), `dose-response.png`, `analysis.ipynb` | PPT, Word, scan+chart img | en |
| p07 | humanities | `desktop/current-chapter`, `archive/closed-research/2018-2025`, `cloud/personal/dissertation-notes` | `chapter-3-draft.docx`, `citation-network.jpeg` (figure), `archival-scan-letter.pdf` (scanned), `sources.md` | Word, scan+figure img | en55/fr15/de15/ja15 |
| p08 | product mgmt | `documents/product/reference-library`, `downloads/inbox/customer-exports`, `archive/closed-launches/2024-2025` | `roadmap-h2.pptx`, `prd-checkout.docx`, `scope-tradeoff.docx`, `launch-metrics.png`, `feedback-export.csv` | PPT, Word, chart img | ja70/en30 |
| p09 | UX research | `downloads/inbox/recorder-imports`, `cloud/team-shared/research-repository`, `cloud/personal/field-notes` | `interview-patterns.pptx`, `usability-report.docx`, `affinity-map.png`, `session-notes.md`, `transcript.txt` | PPT, diagram img | en75/ja25 |
| p10 | consulting | client engagement folders | `engagement-readout.pptx`, `findings-memo.docx`, `benchmark-chart.png`, `workplan.xlsx` (skip), `interview-notes.md` | PPT, Word, Excel, chart img | en |
| p11 | sales AE | `accounts/account-beta/calls`, `downloads/crm-exports`, `travel/customer-meetings/notes` | `renewal-conditions.md`, `proposal.docx`, `pricing-outline.pdf`, `call-notes.md`, `crm-export.csv` | Word | en80/es20 |
| p12 | support | `customers/customer-beta/qbr`, `desktop/active-queue`, `support/ticket-exports` | `escalation-sla.md`, `qbr-deck.pptx`, `response-guidance.md`, `ticket-export.jsonl`, `known-issues.md` | PPT | ja75/en25 |
| p13 | legal | `matters/matter-alpha/correspondence`, `mail/outlook/legal-hold/recent`, `archive/legal/matters/…` | `hold-notice.docx`, `hold-exception.pdf` (scanned signed), `correspondence.eml`, `matter-summary.md`, `privilege-log.csv` | Word, scan img | ja75/en25 |
| p14 | finance | `desktop/current-close`, `archive/finance/close/2021-2025`, `cloud/onedrive/finance-working` | `close-checklist.docx`, `cash-bridge.pptx`, `variance-note.md`, `reconciliation.xlsx` (skip), `journal-export.csv` | PPT, Word, Excel | ja80/en20 |
| p15 | people ops | `desktop/recruiting/requisition-alpha`, `compensation/bands/current`, `learning/training/catalog` | `requisition.docx`, `comp-bands.png` (chart), `offer-letter-scan.pdf` (scanned), `interview-rubric.md` | Word, scan+chart img | ja80/en20 |
| p16 | clinical | `downloads/edc-exports`, `statistics/clinical/analysis`, `literature/clinical/papers` | `protocol-note.pdf` (scanned), `deviation-map.pptx`, `sae-narrative.docx`, `analysis.ipynb`, `dose-monitoring.pdf` | PPT, Word, scan img | ja70/en30 |
| p17 | construction | `bim/construction/exports`, `mail/outlook/project-alpha/recent`, `downloads/inbox/cde-packages` | `inspection-note.pdf` (scanned field form), `rfi-log.csv`, `site-progress.pptx`, `deviation-photo.jpeg`, `spec-section.docx` | PPT, Word, scan+photo img | ja80/en20 |
| p18 | manufacturing | `quality/sop`, `engineering/quality/change-orders`, `downloads/inbox/supplier-certificates` | `lot-inspection-report.docx`, `control-chart.png`, `supplier-cert-scan.pdf` (scanned), `sop-torque.md`, `capa.docx` | Word, scan+chart img | ja75/en25 |
| p19 | education | `downloads/lms-exports`, `downloads/inbox/student-submissions`, `professional-development/instructional/notes` | `rubric-note.pdf` (scanned), `syllabus.docx`, `grade-distribution.png`, `assessment-deck.pptx`, `lesson-plan.md` | PPT, Word, scan+chart img | ja75/en25 |
| p20 | journalism | `archive/newsroom/investigations/2021-2025`, `downloads/foia-exports`, `data/investigations/analysis` | `source-memo.pdf` (scanned notes), `source-timeline.jpeg` (figure), `foia-response.pdf` (scanned), `story-draft.docx`, `records.csv` | Word, scan+figure img | ja70/en30 |

(File names above are illustrative; some intentionally reuse the frozen baseline
answer names — `recovery-window.md`, `control-coverage.png`, `cash-bridge.pptx` —
so the existing 24-query set keeps working on the realistic corpus.)

---

## 8. Open decisions for the user (recommendations in bold)

1. **Purpose depth** — realistic dogfood only, or realistic **+ planted query set**?
   → **Recommend the hybrid (§6b), ~2-3 queries/persona.**
2. **Relationship to the existing corpus** — regenerate `eval-gen/corpus/pNN` in
   place (realistic content, same topology), or a **new** parallel realistic root?
   → **Recommend a new root** (`realistic-corpus/pNN`) so the frozen synthetic
   fixture + its committed results stay intact for regression.
3. **Scale** — files/persona (existing ≈ 50). → **Recommend 30-50**, OCR files
   capped so total OCR ≤ ~$2-3.
4. **Frozen or regenerable** — do we need byte-stable identity (freeze bytes) or is
   regeneration acceptable? → **Recommend generate-once-then-freeze** if we attach
   queries; regenerable if pure dogfood.
5. **Plugin verification** — confirm Codex has (a) Office generation with body-text
   control, (b) image-gen that can render **fact text into pixels** (scans/charts),
   and that the index machine has **`soffice`**.
6. **xlsx / binary realism** — include a few to exercise the skip path (recommended,
   1 xlsx + 1 binary per a handful of personas), never as answer carriers.

---

## 9. Codex generation brief (once approved) — phased, real-pipeline only

**Hard rule (repeat of §0.5):** Codex writes ONLY ordinary files/folders. It never
creates or touches `.kio`. All `.kio`, OCR, Office→PDF conversion, CAS storage,
embedding, indexing, and history are done by the real Kio pipeline. No test-only
content or shortcuts.

### Phase 1 — Create (Codex, plain files only)
- **Topology**: reuse the 20 personas × ~20 leaf folders from an accepted Rust
  plan artifact (see §7 + the p01 example). This historical investigation is
  not an executable Python authority. Files go **directly** in each file-bearing
  folder (the pipeline auto-creates a child `.kio` per such folder). **No `.git`**
  in indexed areas (VCS roots are skipped) — use `repos/<name>/docs/` folders.
- **Format spread per persona**: hit offline (md/txt/code/structured), online OCR
  (≥1 docx, ≥1 pptx, ≥1 scanned-PDF or image, ≥1 text-layer PDF), and ≥1
  unsupported (xlsx or binary) — so every lane is exercised.
- **Realism**: real filenames, real domain prose in the persona's language mix,
  Office files with headings/tables/charts (Office plugin), images that look like
  real charts/scans/photos (image plugin). OCR carriers (scan PDF / image) have
  **no text layer**; facts on figures are rendered into pixels.
- **Output of this phase**: the plain folder tree + a `files.jsonl` describing what
  was created (path, format, intended lane, role) — a description of the tree, NOT
  an index. Optionally `queries.jsonl` if §6b.

### Phase 2 — Index (operator runs the real pipeline)
- `kio init` + `kio index --approve --online` over each persona root; Kio makes the
  `.kio` child scopes, converts Office→PDF, OCRs (Batch), embeds, indexes.
- Cost: keep total OCR pages under the agreed ceiling; run via a spend-guarded
  driver (pattern: `ocr_batch_driver.py`). → commit #1 per scope.

### Phase 3 — Evolve (Codex mutates plain files → real history)
Codex performs **realistic mutation rounds** on the ordinary files; the operator
re-indexes after each round so Kio records real commits. Each mutation must be
plausible for the role. Suggested rounds (design, not fixed):
- **R1 edit sprint**: revise ~10-20% of live docs (update figures/values in an
  Office file, append to a runbook, correct a memo). → new versions; old versions
  live in `--all-history`.
- **R2 reorg**: rename/move files and folders (e.g. `desktop/current-*` →
  `archive/closed/*`, rename `draft` → final). → exercises rename raw_hash identity
  + path history (north-star #2).
- **R3 cleanup**: delete stale/superseded files. → tombstones; content still
  recoverable via `--include-deleted` (north-star #3).
- **R4 add**: a few new files land (new incident, new chapter). → additive commits.
- Emit a `mutations.jsonl` (round, op ∈ {edit,add,delete,move}, path(s), rationale)
  so the history is reproducible and auditable.

### Phase 4 — Measure
- Search / `--at` / `--all-history` / `--include-deleted` over the scopes.
- **If queryable (§6b)**: each planted fact is unique across the corpus, has a
  near-miss distractor, and a natural-language query with the class's overlap rule
  (`queries.jsonl`); measure Recall@10 with a `run_baseline`-style runner. Add
  **history queries** too (find the pre-edit value; find a deleted number; find a
  renamed file's old path) to exercise time-travel.

### Determinism
- Generate each file once; if the corpus is to be frozen, record `content_sha256`
  per file (OOXML embeds timestamps, so re-emitting changes bytes → `raw_hash`).
  The mutation rounds are also recorded (`mutations.jsonl`) so the exact history is
  reproducible from the initial bytes + the ops log.
