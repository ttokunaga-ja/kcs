# p17 — 建設プロジェクトマネージャー

## 役割と世界

Windows 現場ノート PC。Harbor Build の Project Alpha/Beta の図面、仕様、RFI、提出物、変更、現場報告、BIM export、会議記録を管理する。アンカーは **Harbor Build / Project Alpha 2026 / 2026-07-29 / Change Order CO-014、JPY 18,600,000**。実在住所、図面、顧客・作業員情報、現場アクセス情報、秘密は使用禁止。

## 完全配分

フル件数は **8,000**。FORMAT_KEYS 順: md 3%, txt_log 4%, code 0%, structured_text 2%, csv_tsv 5%, html_eml 4%, ipynb 0%, pdf_text 20%, pdf_scan 12%, docx 8%, xlsx 10%, pptx 4%, image 12%, media 1%, domain_binary 15%（合計 100%）。

## 正規の一次パス

`portfolio/projects/project-alpha/2026/construction/drawings`; `portfolio/projects/project-alpha/2026/construction/specifications`; `portfolio/projects/project-alpha/2026/construction/rfi`; `portfolio/projects/project-alpha/2026/construction/submittals`; `portfolio/projects/project-alpha/2026/construction/change-orders`; `portfolio/projects/project-alpha/2026/construction/site-reports`; `portfolio/projects/project-beta/2026/construction/drawings`; `portfolio/projects/project-beta/2026/construction/specifications`; `portfolio/projects/project-beta/2026/construction/rfi`; `portfolio/projects/project-beta/2026/construction/submittals`; `bim/exports`; `meetings/site`。

二次パスは共有 `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）だけを参照し、新たな正規パスは作らない。

## 初回制作バッチ（比率へ継続生産する種）

全配分ではない seed。alpha drawings: PNG scan、specifications: PDF text、RFI: DOCX、submittals: PDF scan、change-orders: XLSX、site reports: PNG scan、beta drawings: PNG scan、beta specifications: PDF text、beta RFI: EML、beta submittals: XLSX、BIM exports: IFC-like domain binary、site meetings: PPTX。Harbor Build、CO-014、2026-07-29、JPY 18,600,000 を統一する。

## 制作ルーティングと引渡し

Documents→DOCX、PDF text/scan→PDF、Spreadsheets→XLSX、Presentations→PPTX、画像/スキャン原稿→ImageGen PNG、他は通常生成。開封、形式、PDF/Office 視覚 QA、画像可読性、アンカー整合、実在 PII・秘密・資格情報なしのみを受入確認し、Kio 検索評価は含めない。
