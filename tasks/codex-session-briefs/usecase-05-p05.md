# Codex セッション ブリーフ — ユースケース 5/20 : `p05` BI・予実/予測分析

> **このセッションで生成するのは `p05` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: BI analytics / quarterly reporting / 言語比率: **ja 75 / en 25**

---

## 0. 絶対規則 — 違反したらこのセッションの成果物は破棄

1. **`.kcs` を作らない・触らない・書かない。** KCS の内部 (objects / index / sqlite / manifest 相当) を
   自分で作ることは全面禁止。あなたが作るのは **普通のファイルとフォルダだけ**。
2. **OCR・Office→PDF 変換・embedding・索引化を自分で実行しない。** それらは後段の
   実 KCS パイプライン (`kcs init` / `kcs index --approve --online`) だけが行う。
3. **骨格を変えない。** 下表の **パス・ファイル名・形式・件数・ページ/スライド数** は確定済み契約。
   増減・改名・移動・形式変更は禁止。**変えてよいのは中身 (本文・図表・コード) の realism だけ。**
4. **正解 (answer) と distractor の契約を壊さない** (§4)。埋め込む fact は指定の値・出現 1 回のみ。
5. **テストのためだけの不自然な内容を作らない。** すべて、その職種の人が実際に持つ/書く体裁にする。
6. **text 系は strict UTF-8・BOM なし・NUL なし。** 文字化けや混在エンコーディングは索引から
   静かに欠落するため禁止。
7. **ファイルは指定 leaf の直下にのみ置く。** 中間ディレクトリに勝手にファイルを置かない。
8. **1 ファイル 5 MiB 以下・PDF/PPTX は 20 ページ/スライド以下。**
9. **fact・query・ソース ID・ファイル名を Office/画像のメタデータに書かない** (properties / alt text /
   EXIF / XMP / PNG text / ノート欄)。

## 1. このユースケースの規模

| 項目 | 値 |
|---|---:|
| 親フォルダ (B) | `corpus/p05/` |
| 生成ファイル数 (B) | **53** |
| └ `home/` (索引対象・20 scope leaf) | 48 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| Q_hard 追加パック (A) `qhard-a/p05/` | 3 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 26 (+A 3) |
| embedding 見積り chunk (B) | 61 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 3 |
| jpeg / jpeg | 1 |
| md / markdown | 9 |
| pdf_text / pdf-text-layer | 4 |
| png / png | 3 |
| pptx / office-powerpoint | 4 |
| txt / code-source | 11 |
| txt / jsonl | 1 |
| txt / log | 2 |
| txt / notebook-json | 6 |
| txt / structured-csv | 2 |
| txt / structured-json | 1 |
| txt / structured-sql | 2 |
| txt / structured-xml | 2 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p05/home/` の 20 scope leaf

各 leaf は **1 つの KCS scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/analytics/governance/data-dictionary` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-023.sql` | txt / structured-sql | ja | offline | filler |
| `status-review-043.pptx` | pptx / office-powerpoint | ja | online_ocr | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 2. `home/analytics/governance/lineage/warehouse` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-024.csv` | txt / structured-csv | ja | offline | filler |
| `trend-figure-044.png` | png / png | en | online_ocr | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

#### 3. `home/analytics/sql/ad-hoc/queries` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-022.xml` | txt / structured-xml | ja | offline | filler |
| `status-review-042.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 4. `home/analytics/sql/production/models` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-041.pptx` | pptx / office-powerpoint | ja | online_ocr | filler |
| `utility-021.rs` | txt / code-source | ja | offline | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

#### 5. `home/archive/closed/reporting-cycles` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-040.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `utility-020.py` | txt / code-source | ja | offline | filler |

#### 6. `home/cloud/personal/query-scratch` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-037.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |
| `utility-017.rs` | txt / code-source | ja | offline | filler |

#### 7. `home/cloud/team/analytics-shared` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-038.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-018.ts` | txt / code-source | ja | offline | filler |

#### 8. `home/dashboards/product/published` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-026.yaml` | txt / structured-yaml | en | offline | filler |
| `trend-figure-046.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 9. `home/dashboards/sales/published` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-025.json` | txt / structured-json | ja | offline | filler |
| `trend-figure-045.png` | png / png | ja | online_ocr | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 10. `home/desktop/active-analysis` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-033.ipynb` | txt / notebook-json | ja | offline | filler |
| `utility-013.rs` | txt / code-source | ja | offline | filler |

#### 11. `home/documents/reference/metric-definitions` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-034.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-014.ts` | txt / code-source | ja | offline | filler |

#### 12. `home/downloads/exports/report-packages` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-016.py` | txt / code-source | ja | offline | filler |

#### 13. `home/downloads/inbox/source-extracts` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-035.ipynb` | txt / notebook-json | ja | offline | filler |
| `utility-015.sh` | txt / code-source | ja | offline | filler |

#### 14. `home/exports/warehouse/snapshots` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-011.jsonl` | txt / jsonl | ja | offline | filler |
| `analysis-031.ipynb` | txt / notebook-json | ja | offline | filler |

#### 15. `home/forecasts/planning/scenarios` — 4 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `forecast-variance.docx` | docx / office-word | en | online_ocr | **★正解** |
| `record-029.csv` | txt / structured-csv | ja | offline | filler |
| `regional-forecast.docx` | docx / office-word | en | online_ocr | **△distractor** |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 16. `home/mail/recent/stakeholder-threads` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-039.docx` | docx / office-word | ja | online_ocr | filler |
| `utility-019.sh` | txt / code-source | ja | offline | filler |

#### 17. `home/meetings/metrics/reviews` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-032.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-012.py` | txt / code-source | ja | offline | filler |

#### 18. `home/reports/operations/monthly` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-028.sql` | txt / structured-sql | en | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 19. `home/reports/operations/weekly` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-027.xml` | txt / structured-xml | ja | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 20. `home/requests/stakeholder/active` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-010.log` | txt / log | ja | offline | filler |
| `analysis-030.ipynb` | txt / notebook-json | en | offline | filler |

### `corpus/p05/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/staging/warehouse/20260713/sales/region-jp/part-0007/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p05.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p05.log` | txt / log | ja | offline |
| `budget-sheet-p05.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p05.png` | png / png | ja | online_ocr |
| `legacy-helper-p05.py` | txt / code-source | ja | offline |

### `qhard-a/p05/` — 3 件 (Q_hard 追加パック)

**B とは事実・ファイルを共有しません。** 別の fact/query 名前空間です。

パス: `qhard-a/p05/home/analytics/governance/data-dictionary/`

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `context-overview.md` | md / markdown | en | offline | filler |
| `data-governance.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **★正解** |
| `retention-exception.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **△distractor** |

---

## 3. 形式別の生成方法と realism 要件

| subtype | 使うもの | realism 要件 |
|---|---|---|
| office-word | Word プラグイン | Word プラグインで実務文書 (見出し・表・ヘッダ/フッタ)。 |
| jpeg | 画像生成/レンダラ | 同上 (JPEG)。写真的な物は装飾のみ・文字を載せない。 |
| markdown | 直接記述 | 実務の Markdown ノート/議事録/ADR/ランブック。見出し・箇条書き・表を自然に使う。 |
| pdf-text-layer | TeX → ビルド | テキスト層のある PDF。TeX ソースを realistic な実務文書に書き換えてビルド。 |
| png | 画像生成/レンダラ | matplotlib/PIL/TeX→PNG でレンダリングした実務の図表/スキャン。 |
| office-powerpoint | PowerPoint プラグイン | PowerPoint プラグインで実務スライド (図表画像を埋込)。 |
| code-source | 直接記述 | その職種が実際に書くソース。動く体裁のコード (関数・コメント・import) にする。 |
| jsonl | 直接記述 | 実務のイベント/レコードを 1 行 1 JSON で。 |
| log | 直接記述 | 実際のアプリ/システムログ形式 (タイムスタンプ + レベル + メッセージ)。 |
| notebook-json | 直接記述 | 実際の Jupyter ノート JSON (cells 配列、code+markdown セル、outputs は簡素で可)。 |
| structured-csv | 直接記述 | 実務の CSV エクスポート (ヘッダ行 + 現実的な列)。 |
| structured-json | 直接記述 | 実務の設定/エクスポート JSON。 |
| structured-sql | 直接記述 | 実務の SQL (DDL/クエリ/マイグレーション)。 |
| structured-xml | 直接記述 | 実務の XML (設定/エクスポート/フィード)。 |
| structured-yaml | 直接記述 | 実務の設定 YAML (CI/インフラ/アプリ設定)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**KCS は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 75 / en 25` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **BI・予実/予測分析** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p05 担当分)

### `qa02` — class **hard1**

- **クエリ**: 「保持規則から外れる期限はいつか」
- **正解ファイル**: `qhard-a/p05/home/analytics/governance/data-dictionary/data-governance.pdf`
- **正解の所在**: section「例外節」
- **埋め込む事実 (この表現・値を必ず使う)**: データ保持の例外期限は 2026-10-14。
- **section hint**: 例外節
- **fact_id**: `f002` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qa02`: `qhard-a/p05/home/analytics/governance/data-dictionary/retention-exception.pdf`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard1 不変条件 (ラスタスキャン PDF)**

- TeX → PDF → `pdftoppm -r 200 -png` → `img2pdf` の順でビルドし、**テキスト層をゼロ**にする。
- 最終 PDF に `pdftotext` をかけ、Unicode 空白を除去した結果が **空** でなければ不合格。
- 事実は **ラスタ画像の画素**にのみ存在させる。

### `qb05` — class **hard2**

- **クエリ**: 「西日本地域で予測と実績がどれだけ離れたか」
- **正解ファイル**: `corpus/p05/home/forecasts/planning/scenarios/forecast-variance.docx`
- **正解の所在**: section「Scenario result」
- **埋め込む事実 (この表現・値を必ず使う)**: The Mosaic scenario logged a 14.6 percent variance for the Kyushu segment.
- **section hint**: Scenario result
- **fact_id**: `f013` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb05`: `corpus/p05/home/forecasts/planning/scenarios/regional-forecast.docx`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard2 不変条件 (語彙重複ゼロの言い換え)**

- クエリと正解本文の **content token (名詞・動詞・数値・英単語) の共通集合を空**にする。
  NFC/NFKC・大小文字・かなカナ・数値桁区切りを正規化した上で判定する。
- 意味は **言い換え/間接的な単位表現**でのみ辿れるようにする。クエリの語をコピーしない。
- DOCX の **ヘッダ/フッタ/表/テキストボックス**も判定対象。そこにも重複語を出さない。

---

## 5. 既に定義済みのソース資産 (これを realism 版に差し替える)

骨格は以下に定義済みです。**構造・ページ数・埋込 fact は維持したまま、本文と図表を realistic に**
書き換えてください。

- `office-specs/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0213-forecast-variance.docx.md`
- `office-specs/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0214-regional-forecast.docx.md`
- `office-specs/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0253-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0254-status-review-040.pptx.md`
- `office-specs/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0255-status-review-041.pptx.md`
- `office-specs/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0256-status-review-042.pptx.md`
- `office-specs/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0257-status-review-043.pptx.md`
- `sources/pdf/raster-only/r-qhard-a-v1-p05-1019.tex`
- `sources/pdf/raster-only/r-qhard-a-v1-p05-1020.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p05-0210.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p05-0250.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p05-0251.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p05-0252.tex`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0208.log`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0209.py`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0215.md`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0216.md`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0217.md`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0218.md`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0219.md`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0220.md`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0221.md`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0222.md`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0223.md`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0224.log`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0225.jsonl`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0226.py`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0227.rs`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0228.ts`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0229.sh`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0230.py`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0231.rs`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0232.ts`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0233.sh`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0234.py`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0235.rs`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0236.xml`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0237.sql`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0238.csv`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0239.json`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0240.yaml`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0241.xml`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0242.sql`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0243.csv`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0244.ipynb`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0245.ipynb`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0246.ipynb`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0247.ipynb`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0248.ipynb`
- `sources/text/baseline-fixture-b-v1/p05/r-baseline-fixture-b-v1-p05-0249.ipynb`
- `sources/text/qhard-a-v1/p05/r-qhard-a-v1-p05-1021.md`
- `sources/visual/specs/r-baseline-fixture-b-v1-p05-0211.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p05-0258.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p05-0259.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p05-0260.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p05-0212.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p05/` と `qhard-a/p05/` の中だけ**。他 persona 0 件。
- [ ] **`.kcs` を 1 つも作っていない**。KCS の内部形式を一切書いていない。
- [ ] OCR / Office→PDF 変換 / embedding / 索引化を **実行していない**。
- [ ] ファイル数が **B=53 (home 48 / ambient 5)** **A=3** と完全一致。
- [ ] パス・ファイル名・形式が §2 の表と完全一致 (改名・追加・削除なし)。
- [ ] `home/` のファイルは全て **leaf 直下**。中間ディレクトリ直下に置いていない。
- [ ] text 系は strict UTF-8・BOM/NUL なし。
- [ ] 正解の fact が **コーパス内 1 回だけ**。distractor に fact が入っていない。
- [ ] `ambient-home/` に fact を置いていない。
- [ ] Office/画像のメタデータ・alt text・EXIF に fact/クエリ/ID/ファイル名を書いていない。
- [ ] 5 MiB / 20 ページ・スライド の上限内。
- [ ] hard1 がある場合、最終 PDF の `pdftotext` 出力が空であることを確認した。

## 7. 引き渡し

生成物は **普通のファイルのみ**。この後、オペレータ側で実 KCS パイプラインが
`kcs init` → `kcs index --approve --online` を実行し、`.kcs` 生成・Office→PDF 変換・
OCR (Mistral Batch)・CAS 保存・embedding (Gemini)・索引化を行います。
さらにその後、別セッションで **編集・追加・削除・フォルダ移動**を行い、実パイプラインで
履歴 (time-travel / `--all-history` / `--include-deleted`) を生成します。

