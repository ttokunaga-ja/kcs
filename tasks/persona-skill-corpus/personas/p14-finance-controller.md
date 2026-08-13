# p14 — 財務コントローラー

## 役割と世界

Windows 財務管理 PC。Cedar Works の月次締め、予算、予測、請求書、部門経費、監査証跡、取締役会資料、ERP 出力を管理する。アンカーは **Cedar Works / FY2026 Q1・2026-03 close / cash variance JPY 12,400,000**。実在の口座、請求先、従業員、税情報、資格情報は禁止。

## 完全配分

フル件数は **9,000**。FORMAT_KEYS 順: md 3%, txt_log 3%, code 1%, structured_text 4%, csv_tsv 15%, html_eml 5%, ipynb 0%, pdf_text 13%, pdf_scan 8%, docx 8%, xlsx 27%, pptx 7%, image 3%, media 0%, domain_binary 3%（合計 100%）。

## 正規の一次パス

`finance/close/2026/q1/2026-01`; `finance/close/2026/q1/2026-02`; `finance/close/2026/q1/2026-03`; `budget/annual`; `forecasts/base-case`; `forecasts/scenarios`; `invoices/vendor`; `expenses/department`; `audit/evidence`; `board/finance-packs`; `models/operating-model`; `erp/exports`。

二次パスは共有 `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）を参照し、権威ある追加パスを作らない。

## 初回制作バッチ（比率へ継続生産する種）

これは全配分ではなく seed。各月 close は XLSX、annual budget は XLSX、base/scenario forecast は XLSX、vendor invoices は PDF scan、department expenses は CSV、audit evidence は PDF text、board pack は PPTX、operating model は XLSX、ERP export は CSV。Cedar Works、FY2026 Q1、2026-03、JPY 12,400,000 を共通に保つ。

## 制作ルーティングと引渡し

Documents→DOCX、PDF text/scan→PDF、Spreadsheets→XLSX、Presentations→PPTX、画像/スキャン原稿→ImageGen PNG、その他→通常生成。形式・開封・PDF/Office 視覚 QA・画像可読性・アンカー整合・実在 PII/秘密/資格情報なしのみを確認し、Kio 検索評価は行わない。
