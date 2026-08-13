# p11 — アカウント営業

## 役割と世界

Windows の出張営業ノート PC。Northstar Cloud のアカウント営業として、Account Alpha/Beta の更新、提案、RFP、価格承認、契約と顧客訪問を扱う。アンカーは **Northstar Cloud / Account Alpha / 2026-07-17 / 更新額 USD 248,000**。実在の顧客、連絡先、CRM 出力、認証情報は使わない。

## 完全配分

フル件数は **10,000**。FORMAT_KEYS 順: md 3%, txt_log 4%, code 0%, structured_text 2%, csv_tsv 5%, html_eml 25%, ipynb 0%, pdf_text 16%, pdf_scan 4%, docx 14%, xlsx 7%, pptx 10%, image 5%, media 3%, domain_binary 2%（合計 100%）。

## 正規の一次パス

`accounts/account-alpha/plans`; `accounts/account-alpha/calls`; `accounts/account-alpha/proposals`; `accounts/account-beta/plans`; `accounts/account-beta/calls`; `accounts/account-beta/proposals`; `opportunities/pipeline`; `rfp/responses`; `pricing/approved`; `contracts/drafts`; `contracts/executed`; `travel/meeting-notes`。

二次パスは共有の `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）を参照し、これ以外を権威あるパスとして創作しない。

## 初回制作バッチ（比率へ継続生産する種）

これは全配分ではなく、上記比率へ続けて生産するための高忠実度 seed である。plans: 更新条件 MD、calls: 通話要約 EML、proposals: 顧客提案 DOCX、beta plans: 更新比較 PDF text、beta calls: 通話ログ HTML、beta proposals: 提案 PPTX、pipeline: 機会 CSV、RFP: 回答 DOCX、pricing: 承認済見積 XLSX、drafts: 条項 DOCX、executed: 発注書 PDF scan、travel: 訪問メモ PNG scan。数値・組織名は上記アンカーを一貫して使う。

## 制作ルーティングと引渡し

Documents は DOCX、PDF は text/scan の性質に応じ PDF、Spreadsheets は XLSX、Presentations は PPTX、画像/スキャン原稿は ImageGen PNG を使う。その他は通常生成。受入時は拡張子と内容の整合、破損しない開封、PDF/Office のページ・スライド目視、画像の可読性、アンカー整合、実在 PII・秘密・資格情報がないことだけを確認する。Kio 検索評価は対象外。
