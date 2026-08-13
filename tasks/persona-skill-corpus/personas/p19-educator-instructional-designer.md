# p19 — 教育者・インストラクショナルデザイナー

## 役割と世界

ChromeOS 由来の教育端末スナップショット。Maple Learning の Course Alpha/Beta の授業案、読解、課題、完全合成の学習者成果物、評価項目、LMS export、講義資料を扱う。アンカーは **Maple Learning / Course Alpha 2026 Term 1 / 2026-09-14 / 合成受講者 36、rubric 配点 20**。実在の学習者・教員、成績、連絡先、LMS 資格情報は禁止。

## 完全配分

フル件数は **9,000**。FORMAT_KEYS 順: md 8%, txt_log 5%, code 0%, structured_text 2%, csv_tsv 5%, html_eml 5%, ipynb 0%, pdf_text 20%, pdf_scan 8%, docx 15%, xlsx 7%, pptx 12%, image 8%, media 3%, domain_binary 2%（合計 100%）。

## 正規の一次パス

`learning/courses/course-alpha/2026/term-1/lesson-plans`; `learning/courses/course-alpha/2026/term-1/readings`; `learning/courses/course-alpha/2026/term-1/assignments`; `learning/courses/course-alpha/2026/term-1/synthetic-student-work`; `learning/courses/course-beta/2026/term-2/lesson-plans`; `learning/courses/course-beta/2026/term-2/readings`; `learning/courses/course-beta/2026/term-2/assignments`; `learning/courses/course-beta/2026/term-2/synthetic-student-work`; `assessments/item-bank`; `lms/exports`; `presentations/lectures`; `professional-development/notes`。

二次パスは共有 `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）のみを参照し、権威あるパスを追加しない。

## 初回制作バッチ（比率へ継続生産する種）

全配分ではなく seed。alpha lesson plans: DOCX、readings: PDF text、assignments: PDF scan、synthetic work: DOCX、beta lesson plans: DOCX、beta readings: PDF text、beta assignments: PDF scan、beta synthetic work: PNG scan、item bank: XLSX、LMS exports: CSV、lectures: PPTX、PD notes: MD。Maple Learning、Term 1、36、20 を合成アンカーとして保つ。

## 制作ルーティングと引渡し

Documents→DOCX、PDF text/scan→PDF、Spreadsheets→XLSX、Presentations→PPTX、画像/スキャン原稿→ImageGen PNG、他は通常生成。開封可能性、形式一致、PDF/Office 視覚 QA、画像可読性、アンカー整合、実在 PII・秘密・資格情報なしだけを確認する。Kio 検索評価は行わない。
