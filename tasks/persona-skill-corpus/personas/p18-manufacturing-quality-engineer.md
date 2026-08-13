# p18 — 製造品質エンジニア

## 役割と世界

Windows 品質エンジニアリング端末。ForgeLine の Product Alpha/Beta に対する FMEA、試験、CAPA、SOP、作業指示、不適合、供給者監査・証明書、設計変更を扱う。アンカーは **ForgeLine / Product Alpha / 2026-08-11 / NCR-026、許容差 ±0.18 mm**。実在製品、工場、供給者、品質記録、アクセス情報、秘密は使わない。

## 完全配分

フル件数は **12,000**。FORMAT_KEYS 順: md 6%, txt_log 12%, code 2%, structured_text 6%, csv_tsv 15%, html_eml 3%, ipynb 0%, pdf_text 18%, pdf_scan 6%, docx 8%, xlsx 10%, pptx 3%, image 5%, media 0%, domain_binary 6%（合計 100%）。

## 正規の一次パス

`products/product-alpha/fmea`; `products/product-alpha/test-results`; `products/product-alpha/capa`; `products/product-beta/fmea`; `products/product-beta/test-results`; `products/product-beta/capa`; `quality/sop`; `quality/work-instructions`; `quality/nonconformance`; `suppliers/audits`; `suppliers/certificates`; `engineering/change-orders`。

二次パスは共有 `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）を参照し、正規の追加パスを創作しない。

## 初回制作バッチ（比率へ継続生産する種）

これは全配分でなく seed。alpha FMEA: XLSX、alpha test results: CSV、alpha CAPA: DOCX、beta FMEA: XLSX、beta tests: CSV、beta CAPA: PDF text、SOP: PDF text、work instructions: DOCX、nonconformance: PDF scan、supplier audits: PDF scan、certificates: PNG scan、change orders: XLSX。ForgeLine、NCR-026、2026-08-11、±0.18 mm を共通化する。

## 制作ルーティングと引渡し

Documents→DOCX、PDF text/scan→PDF、Spreadsheets→XLSX、Presentations→PPTX、画像/スキャン原稿→ImageGen PNG、その他→通常生成。形式・開封、PDF/Office 視覚 QA、画像可読性、アンカー整合、実在 PII・秘密・資格情報がないことのみを確認する。Kio 検索評価は対象外。
