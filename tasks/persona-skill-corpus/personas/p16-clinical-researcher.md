# p16 — 臨床研究者

## 役割と世界

Windows clinical VDI の臨床研究者。Study Alpha/Beta のプロトコル、完全合成ケース、結果、ガイドライン、文献、規制提出、合成有害事象、統計、講演を扱う。アンカーは **Sakura Clinical / Study Alpha 2026 / 2026-09-02 / 合成 cohort 48、閾値 2.5 mg**。実在 PHI、患者・医療者・施設情報、検査結果、秘密は不可。

## 完全配分

フル件数は **8,000**。FORMAT_KEYS 順: md 5%, txt_log 6%, code 1%, structured_text 4%, csv_tsv 10%, html_eml 4%, ipynb 1%, pdf_text 24%, pdf_scan 12%, docx 10%, xlsx 8%, pptx 5%, image 6%, media 1%, domain_binary 3%（合計 100%）。

## 正規の一次パス

`clinical/studies/study-alpha/2026/protocols`; `clinical/studies/study-alpha/2026/synthetic-cases`; `clinical/studies/study-alpha/2026/results`; `clinical/studies/study-beta/2026/protocols`; `clinical/studies/study-beta/2026/synthetic-cases`; `clinical/studies/study-beta/2026/results`; `guidelines/clinical`; `literature/papers`; `regulatory/submissions`; `safety/adverse-events-synthetic`; `statistics/analysis`; `presentations/grand-rounds`。

二次パスは共有 `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）に限定し、正規パスを追加しない。

## 初回制作バッチ（比率へ継続生産する種）

全配分ではない seed。alpha protocols: PDF text、alpha synthetic cases: DOCX、alpha results: XLSX、beta protocols: PDF text、beta synthetic cases: PDF scan、beta results: CSV、guidelines: PDF text、papers: PDF text、submissions: DOCX、adverse events: XLSX、statistics: IPYNB、grand rounds: PPTX。Sakura Clinical、Study Alpha、48、2.5 mg を一貫させる。

## 制作ルーティングと引渡し

Documents→DOCX、PDF text/scan→PDF、Spreadsheets→XLSX、Presentations→PPTX、画像/スキャン原稿→ImageGen PNG、他は通常生成。開封、内容形式、PDF/Office 視覚 QA、画像可読性、アンカー整合、実在 PII/PHI・秘密・資格情報なしだけを確認する。Kio 検索評価は対象外。
