# p13 — 企業プライバシー法務

## 役割と世界

Windows DLP 管理ノート PC の企業プライバシー法務。Matter Alpha/Beta の法的保全、契約、規制ガイダンス、方針、DD、取締役会報告を扱う。アンカーは **Aster Legal / Matter Alpha / 2026-06-30 / 保全対象 42、例外期限 2026-07-12**。実在の当事者、事件、個人データ、秘匿特権資料、鍵は使わない。

## 完全配分

フル件数は **7,000**。FORMAT_KEYS 順: md 3%, txt_log 4%, code 0%, structured_text 1%, csv_tsv 2%, html_eml 14%, ipynb 0%, pdf_text 28%, pdf_scan 15%, docx 22%, xlsx 3%, pptx 2%, image 3%, media 0%, domain_binary 3%（合計 100%）。

## 正規の一次パス

`matters/matter-alpha/correspondence`; `matters/matter-alpha/working`; `matters/matter-beta/correspondence`; `matters/matter-beta/working`; `contracts/drafts`; `contracts/executed`; `contracts/templates`; `regulations/guidance`; `policies/privacy`; `due-diligence/data-room`; `legal-hold/notices`; `board/legal-reports`。

二次パスは共有 `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）を参照し、追加の正規パスは発明しない。

## 初回制作バッチ（比率へ継続生産する種）

全配分ではなく seed。alpha correspondence: EML、alpha working: DOCX、beta correspondence: PDF text、beta working: PDF scan、drafts: DOCX、executed: PDF text、templates: DOCX、guidance: PDF text、privacy: PDF scan、DD: XLSX、hold notices: PDF scan、board: PPTX。Aster Legal、Matter Alpha、42、2026-07-12 を共通の合成事実にする。

## 制作ルーティングと引渡し

Documents→DOCX、PDF text/scan→PDF、Spreadsheets→XLSX、Presentations→PPTX、画像/スキャン原稿→ImageGen PNG、その他→通常生成。開封可能性、ファイル形式、PDF/Office 視覚 QA、画像の読める文字、アンカー整合、実在 PII・秘密・資格情報なしを確認する。Kio 検索評価はしない。
