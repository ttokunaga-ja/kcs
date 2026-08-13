# p02 Site Reliability Engineer

## 役割と作業世界

Ubuntu の SRE ワークステーション（en-US、en）。架空組織 **Northstar Transit Cloud** の Checkout/Identity 運用者が、2026-07-13 の当番、追記型ログ、障害対応を扱う。Git/server export の合成素材のみ、S2/S3 はすべて架空。

## 正式配分（W0 15,000 物理ファイル）

`md 20% / txt_log 22% / code 15% / structured_text 20% / csv_tsv 5% / html_eml 3% / ipynb 0% / pdf_text 4% / pdf_scan 0% / docx 2% / xlsx 1% / pptx 1% / image 2% / media 0% / domain_binary 5%`（計100%）。

## 正式 primary paths（12）

`documents/operations/runbooks`; `documents/operations/postmortems`; `infrastructure/kubernetes`; `infrastructure/terraform`; `services/checkout/prod/oncall/operations`; `services/identity/prod/oncall/operations`; `observability/alerts`; `observability/dashboards`; `observability/log-exports`; `changes/deployments`; `capacity/reports`; `meetings/operations`。

secondary は `eval/persona_fixture_spec.py` の共通 `SECONDARY_PATHS` を参照し、独自の正式 path は追加しない。

## 初回制作バッチ（比率達成そのものではない）

runbooks=Markdown、postmortems=DOCX、kubernetes=YAML、terraform=HCL相当のテキスト、checkout oncall=incident log、identity oncall=runbook Markdown、alerts=JSON、dashboards=CSV export、log-exports=log、deployments=change HTML、capacity=PDF text、meetings=operations PPTX。全比率の完了ではなく、以後の制作を比率へ導く種である。

## 生成・受け渡し

DOCX=Documents、PDF text/scan=PDF、XLSX=Spreadsheets、PPTX=Presentations、PNG/スキャン原稿=ImageGen、その他=通常生成。アンカーは `Northstar Transit Cloud / Checkout SVC-17 / 2026-07-13 / error budget 2.4% / INC-260713`。実在 PII、実 IP、資格情報、トークン、秘密鍵、顧客データは禁止。

受け渡しは実体/拡張子、開封、PDF/Office レンダリング、図表・ログの可読性、アンカー整合のみを確認する。Kio 検索評価は含めない。
