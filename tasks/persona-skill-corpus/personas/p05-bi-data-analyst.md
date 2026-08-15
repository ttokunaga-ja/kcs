# p05 BI データアナリスト

## 役割と作業世界

Windows 分析ラップトップ（ja-JP、ja/en）。架空組織 **Mosaic Retail Analytics** の定期報告・ダッシュボード更新者。2026-07-13 の OneDrive/warehouse 合成 export、S2 架空分析データのみ。

## 正式配分（W0 12,000 物理ファイル）

`md 8% / txt_log 5% / code 6% / structured_text 14% / csv_tsv 20% / html_eml 5% / ipynb 5% / pdf_text 5% / pdf_scan 1% / docx 3% / xlsx 15% / pptx 4% / image 3% / media 0% / domain_binary 6%`（計100%）。

## 正式 primary paths（12）

`analytics/sql/production`; `analytics/sql/ad-hoc`; `analytics/data-dictionary`; `analytics/lineage`; `dashboards/sales`; `dashboards/product`; `reports/weekly`; `reports/monthly`; `forecasts/scenarios`; `requests/stakeholder`; `exports/warehouse`; `meetings/metric-reviews`。

secondary は accepted Rust plan の共通 secondary paths のみ。

## 初回制作バッチ（比率達成そのものではない）

production SQL=SQL、ad-hoc SQL=Markdown、dictionary=DOCX、lineage=JSON、sales dashboard=CSV、product dashboard=PNG、weekly report=PDF text、monthly report=XLSX、scenarios=XLSX、stakeholder request=EML、warehouse export=TSV、metric review=PPTX。以後、正式比率への制作を継続する種である。

## 生成・受け渡し

DOCX=Documents、PDF text/scan=PDF、XLSX=Spreadsheets、PPTX=Presentations、PNG/スキャン原稿=ImageGen、その他=通常生成。アンカー: `Mosaic Retail / FY26 Q3 / 2026-07-13 / GMV ¥84.2M / metric MTR-09`。実在顧客、売上、個人情報、接続文字列、資格情報は禁止。

実体/拡張子、開封、Office/PDF レンダリング、表・グラフ・単位の可読性、数値アンカー整合だけを確認して渡す。Kio 検索評価は対象外。
