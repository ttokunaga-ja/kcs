# p15 — 採用・People Ops

## 役割と世界

Windows HR 運用 PC。Orchid People の求人 requisition、面接、オファー、方針、合成人員計画・評価・調査、研修、報酬帯、保持要件を扱う。アンカーは **Orchid People / Requisition Alpha / 2026-08-18 / 採用枠 3、報酬帯 JPY 7.2–8.4M**。候補者・従業員の実名、履歴書、連絡先、給与、ID、秘密は絶対に使わない。

## 完全配分

フル件数は **8,000**。FORMAT_KEYS 順: md 4%, txt_log 5%, code 0%, structured_text 2%, csv_tsv 7%, html_eml 15%, ipynb 0%, pdf_text 20%, pdf_scan 8%, docx 20%, xlsx 8%, pptx 3%, image 5%, media 1%, domain_binary 2%（合計 100%）。

## 正規の一次パス

`recruiting/requisition-alpha/candidates`; `recruiting/requisition-alpha/interviews`; `recruiting/requisition-beta/candidates`; `recruiting/requisition-beta/interviews`; `recruiting/offers`; `people/policies`; `people/headcount`; `people/performance-synthetic`; `people/surveys-synthetic`; `learning/training`; `compensation/bands`; `compliance/retention`。

二次パスは共有 `SECONDARY_PATHS` 方針（`desktop/working`, `documents/reference`, `downloads/inbox`, `downloads/exports`, `cloud/my-files`, `cloud/team-shared`, `mail/recent`, `archive/closed`）を参照し、追加の権威パスを創作しない。

## 初回制作バッチ（比率へ継続生産する種）

全配分ではない seed。alpha candidates: 合成候補 PDF、alpha interviews: 決定 DOCX、beta candidates: 合成プロフィール PDF、beta interviews: 面接要約 DOCX、offers: DOCX、policies: PDF text、headcount: XLSX、performance-synthetic: CSV、surveys-synthetic: XLSX、training: PPTX、bands: XLSX、retention: PDF scan。上記アンカーの合成人物・数値だけを用いる。

## 制作ルーティングと引渡し

Documents→DOCX、PDF text/scan→PDF、Spreadsheets→XLSX、Presentations→PPTX、画像/スキャン原稿→ImageGen PNG、その他→通常生成。開封可能性、実体と拡張子、PDF/Office の視覚 QA、画像可読性、アンカー整合、実在 PII・秘密・資格情報なしのみを確認する。Kio 検索評価は対象外。
