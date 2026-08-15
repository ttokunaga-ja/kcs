# p06 生命科学研究者

## 役割と作業世界

Windows 実験室ワークステーション（en-US、en）。架空の **Orchid Cellworks** で Study Alpha/Beta の protocol run と cohort batch を扱う。2026-07-13 の SMB/instrument 合成 export、S2/S3 は架空試料のみ。

## 正式配分（W0 8,000 物理ファイル）

`md 6% / txt_log 6% / code 3% / structured_text 5% / csv_tsv 15% / html_eml 2% / ipynb 3% / pdf_text 18% / pdf_scan 8% / docx 8% / xlsx 8% / pptx 5% / image 9% / media 0% / domain_binary 4%`（計100%）。

## 正式 primary paths（12）

`lab/lab-notebooks`; `lab/protocols`; `programs/study-alpha/2026/cohort-a/raw-exports`; `programs/study-alpha/2026/cohort-a/analysis`; `programs/study-beta/2026/cohort-b/raw-exports`; `programs/study-beta/2026/cohort-b/analysis`; `instruments/calibration`; `samples/manifests`; `literature/papers`; `grants/applications`; `figures/manuscript`; `meetings/lab`。

secondary は accepted Rust plan の共通 secondary paths 参照のみ。

## 初回制作バッチ（比率達成そのものではない）

notebooks=Markdown、protocols=DOCX、alpha raw=CSV、alpha analysis=IPYNB、beta raw=TSV、beta analysis=XLSX、calibration=scan PDF、manifests=JSON、papers=PDF text、grants=DOCX、figures=PNG、lab meetings=PPTX。全配分の代替ではなく、継続制作への種である。

## 生成・受け渡し

DOCX=Documents、PDF text/scan=PDF、XLSX=Spreadsheets、PPTX=Presentations、PNG/スキャン原稿=ImageGen、その他=通常生成。アンカー: `Orchid Cellworks / Study Alpha / 2026-07-13 / cohort A-24 / assay 6.8 ng/mL`。実在の患者・被験者・試料ID、PHI、資格情報は禁止。

実体/拡張子、開封、Office/PDF レンダリング、図表・単位・画像ラベルの可読性、アンカー整合のみをQAする。Kio 検索評価は含まない。
