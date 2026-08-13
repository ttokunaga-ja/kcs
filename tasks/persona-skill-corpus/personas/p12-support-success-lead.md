# p12 — サポート・サクセス責任者

## 役割と世界

Windows 管理端末で HelioDesk の支援・定着化を率いる。キュー、エスカレーション、既知問題、ナレッジ、QBR、添付ログと定型返信を扱う。アンカーは **HelioDesk / Customer Alpha / 2026-08-04 / SLA 4 時間、未解決 17 件**。実在チケット、顧客名、メール、API キーは不可。

## 完全配分

フル件数は **16,000**。FORMAT_KEYS 順: md 15%, txt_log 20%, code 4%, structured_text 15%, csv_tsv 12%, html_eml 12%, ipynb 0%, pdf_text 5%, pdf_scan 1%, docx 3%, xlsx 2%, pptx 1%, image 7%, media 1%, domain_binary 2%（合計 100%）。

## 正規の一次パス

`support/ticket-exports`; `support/escalations`; `support/known-issues`; `knowledge-base/drafts`; `knowledge-base/published`; `customers/customer-alpha/qbr`; `customers/customer-alpha/case-history`; `customers/customer-beta/qbr`; `customers/customer-beta/case-history`; `logs/customer-attachments`; `macros/replies`; `incidents/support-links`。

二次パスは共有 `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）だけを参照し、権威ある追加パスは作らない。

## 初回制作バッチ（比率へ継続生産する種）

これは全配分ではない。ticket exports: JSON、escalations: SLA MD、known issues: HTML、KB drafts: DOCX、KB published: PDF text、alpha QBR: PPTX、alpha history: EML、beta QBR: XLSX、beta history: CSV、attachments: PNG scan、macros: TXT、incident links: LOG。HelioDesk、2026-08-04、4 時間、17 件を一貫利用する。

## 制作ルーティングと引渡し

Documents は DOCX、PDF は text/scan に応じ PDF、Spreadsheets は XLSX、Presentations は PPTX、画像/スキャン原稿は ImageGen PNG、他は通常生成。破損しない開封、形式と内容の一致、Office/PDF の目視、画像可読性、アンカー整合、実在 PII・秘密・資格情報の不在のみを受入確認する。Kio 検索評価は含めない。
