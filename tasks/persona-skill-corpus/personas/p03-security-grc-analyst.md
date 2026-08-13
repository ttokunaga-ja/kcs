# p03 Security GRC アナリスト

## 役割と作業世界

Windows 管理対象 GRC ラップトップ（ja-JP、ja/en）。架空組織 **Cobalt Harbor Systems** の監査・インシデント証跡担当。2026-07-13 時点の監査ケース／incident case、SharePoint/SIEM の合成 export、S3 架空証跡を扱う。

## 正式配分（W0 10,000 物理ファイル）

`md 10% / txt_log 12% / code 8% / structured_text 15% / csv_tsv 10% / html_eml 8% / ipynb 0% / pdf_text 15% / pdf_scan 5% / docx 5% / xlsx 4% / pptx 2% / image 3% / media 0% / domain_binary 3%`（計100%）。

## 正式 primary paths（12）

`security/threat-models`; `security/pentest-reports`; `security/vulnerabilities`; `security/incident-reports`; `compliance/policies`; `compliance/control-evidence`; `compliance/audit-requests`; `vendor-risk/questionnaires`; `soc/siem-exports`; `soc/detection-rules`; `privacy/risk-assessments`; `meetings/security-reviews`。

secondary は共通 `SECONDARY_PATHS`（`eval/persona_fixture_spec.py`）参照のみ。

## 初回制作バッチ（比率達成そのものではない）

threat-models=Markdown、pentest-reports=PDF text、vulnerabilities=CSV、incident-reports=DOCX、policies=PDF text、control-evidence=scan PDF、audit-requests=EML、questionnaires=XLSX、siem-exports=JSON、detection-rules=YAML、risk-assessments=PNG、security-reviews=PPTX。これは継続制作を正式比率へ寄せる開始点である。

## 生成・受け渡し

DOCX=Documents、PDF text/scan=PDF、XLSX=Spreadsheets、PPTX=Presentations、PNG/スキャン原稿=ImageGen、その他=通常生成。アンカー: `Cobalt Harbor / Aegis Control AC-27 / 2026-07-13 / evidence set 184 / RISK-031`。実在の脆弱性、ログ、顧客、氏名、メール、IP、資格情報・鍵は禁止。

実体/拡張子、開封、PDF/Office レンダリング、OCR対象の見やすさ、表・証跡番号の整合だけをQAして渡す。Kio 検索評価はしない。
