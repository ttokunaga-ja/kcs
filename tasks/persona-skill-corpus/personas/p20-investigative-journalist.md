# p20 — 調査報道記者

## 役割と世界

macOS 暗号化記者ノート PC。Civic Ledger の Story Alpha/Beta の合成情報源、逐語録、FOIA、草稿、ファクトチェック、データ分析、メディア副次記録、企画調査を扱う。アンカーは **Civic Ledger / Story Alpha 2026 / 2026-08-22 / FOIA batch 17、確認日 2026-08-19**。実在情報源、匿名者、連絡先、位置情報、未公開資料、暗号鍵・認証情報は使わない。

## 完全配分

フル件数は **10,000**。FORMAT_KEYS 順: md 8%, txt_log 18%, code 1%, structured_text 3%, csv_tsv 8%, html_eml 10%, ipynb 0%, pdf_text 16%, pdf_scan 10%, docx 8%, xlsx 2%, pptx 2%, image 8%, media 4%, domain_binary 2%（合計 100%）。

## 正規の一次パス

`newsroom/investigations/story-alpha/2026/sources`; `newsroom/investigations/story-alpha/2026/transcripts`; `newsroom/investigations/story-alpha/2026/foia`; `newsroom/investigations/story-alpha/2026/drafts`; `newsroom/investigations/story-alpha/2026/fact-check`; `newsroom/investigations/story-beta/2026/sources`; `newsroom/investigations/story-beta/2026/transcripts`; `newsroom/investigations/story-beta/2026/foia`; `newsroom/investigations/story-beta/2026/drafts`; `data/analysis`; `media/transcript-sidecars`; `pitches/research`。

二次パスは共有 `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）を参照し、追加の正規パスは発明しない。

## 初回制作バッチ（比率へ継続生産する種）

これは全配分ではない seed。alpha sources: EML、alpha transcripts: TXT log、alpha FOIA: PDF scan、alpha drafts: DOCX、alpha fact-check: PDF text、beta sources: HTML、beta transcripts: TXT log、beta FOIA: PDF scan、beta drafts: MD、analysis: CSV、media sidecars: WAV、pitches: PPTX。Civic Ledger、batch 17、2026-08-22、2026-08-19 を一貫して使う。

## 制作ルーティングと引渡し

Documents→DOCX、PDF text/scan→PDF、Spreadsheets→XLSX、Presentations→PPTX、画像/スキャン原稿→ImageGen PNG、その他→通常生成。開封、形式整合、PDF/Office 視覚 QA、画像可読性、アンカー整合、実在 PII・秘密・資格情報なしのみを確認する。Kio 検索評価は含めない。
