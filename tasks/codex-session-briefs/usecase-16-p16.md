# Codex セッション ブリーフ — ユースケース 16/20 : `p16` 臨床研究・プロトコル

> **このセッションで生成するのは `p16` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: clinical research / protocol evidence / 言語比率: **ja 70 / en 30**

---

## 0. 絶対規則 — 違反したらこのセッションの成果物は破棄

1. **`.kio` を作らない・触らない・書かない。** Kio の内部 (objects / index / sqlite / manifest 相当) を
   自分で作ることは全面禁止。あなたが作るのは **普通のファイルとフォルダだけ**。
2. **OCR・Office→PDF 変換・embedding・索引化を自分で実行しない。** それらは後段の
   実 Kio パイプライン (`kio init` / `kio index --approve --online`) だけが行う。
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
| 親フォルダ (B) | `corpus/p16/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 34 |
| embedding 見積り chunk (B) | 65 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 3 |
| jpeg / jpeg | 1 |
| md / markdown | 11 |
| pdf_rasterized / pdf-raster-only | 2 |
| pdf_text / pdf-text-layer | 6 |
| png / png | 2 |
| pptx / office-powerpoint | 2 |
| txt / code-source | 4 |
| txt / eml | 1 |
| txt / jsonl | 2 |
| txt / log | 3 |
| txt / notebook-json | 2 |
| txt / plain-text | 3 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| txt / structured-sql | 2 |
| txt / structured-xml | 2 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p16/home/` の 20 scope leaf

各 leaf は **1 つの Kio scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/clinical/studies/2020-2025/closed` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-040.pptx` | pptx / office-powerpoint | ja | online_ocr | filler |
| `utility-020.py` | txt / code-source | ja | offline | filler |

#### 2. `home/clinical/studies/study-alpha/2026/protocols` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `dose-monitoring.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **△distractor** |
| `protocol-note.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **★正解** |
| `status-review-041.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `utility-021.rs` | txt / code-source | en | offline | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

#### 3. `home/clinical/studies/study-alpha/2026/results` — 4 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-023.sql` | txt / structured-sql | en | offline | filler |
| `safety-grid.png` | png / png | ja | online_ocr | **★正解** |
| `safety-panels.png` | png / png | ja | online_ocr | **△distractor** |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 4. `home/clinical/studies/study-alpha/2026/synthetic-cases` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-022.xml` | txt / structured-xml | ja | offline | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 5. `home/clinical/studies/study-beta/2026/protocols` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-024.csv` | txt / structured-csv | ja | offline | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

#### 6. `home/clinical/studies/study-beta/2026/results` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-026.yaml` | txt / structured-yaml | ja | offline | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 7. `home/clinical/studies/study-beta/2026/synthetic-cases` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-025.json` | txt / structured-json | en | offline | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 8. `home/cloud/onedrive/clinical-working` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-017.jsonl` | txt / jsonl | en | offline | filler |
| `review-summary-037.docx` | docx / office-word | en | online_ocr | filler |

#### 9. `home/cloud/sharepoint/clinical/study-alpha/team` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-018.txt` | txt / plain-text | ja | offline | filler |
| `review-summary-038.docx` | docx / office-word | ja | online_ocr | filler |

#### 10. `home/desktop/clinical/study-alpha/active` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-013.log` | txt / log | en | offline | filler |
| `reference-brief-033.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 11. `home/documents/clinical/protocols/reference` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | ja | offline | filler |
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 12. `home/downloads/edc-exports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | ja | offline | filler |
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 13. `home/downloads/inbox/dicom-series` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | en | offline | filler |
| `reference-brief-035.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 14. `home/guidelines/clinical/practice-updates` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-027.xml` | txt / structured-xml | en | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 15. `home/literature/clinical/papers` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-028.sql` | txt / structured-sql | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 16. `home/mail/outlook/study-alpha/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |
| `utility-019.sh` | txt / code-source | en | offline | filler |

#### 17. `home/presentations/clinical/grand-rounds` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-012.txt` | txt / plain-text | ja | offline | filler |
| `reference-brief-032.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 18. `home/regulatory/clinical/submissions` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-029.eml` | txt / eml | en | offline | filler |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 19. `home/safety/clinical/adverse-events-synthetic` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-030.ipynb` | txt / notebook-json | ja | offline | filler |
| `worklog-010.md` | md / markdown | ja | offline | filler |

#### 20. `home/statistics/clinical/analysis` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-031.ipynb` | txt / notebook-json | en | offline | filler |
| `worklog-011.md` | md / markdown | ja | offline | filler |

### `corpus/p16/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/secure-smb/study-alpha/site-03/subject-syn-004/visit-02/imaging/series-01/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p16.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p16.log` | txt / log | ja | offline |
| `budget-sheet-p16.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p16.jpeg` | jpeg / jpeg | ja | online_ocr |
| `legacy-helper-p16.py` | txt / code-source | ja | offline |

---

## 3. 形式別の生成方法と realism 要件

| subtype | 使うもの | realism 要件 |
|---|---|---|
| office-word | Word プラグイン | Word プラグインで実務文書 (見出し・表・ヘッダ/フッタ)。 |
| jpeg | 画像生成/レンダラ | 同上 (JPEG)。写真的な物は装飾のみ・文字を載せない。 |
| markdown | 直接記述 | 実務の Markdown ノート/議事録/ADR/ランブック。見出し・箇条書き・表を自然に使う。 |
| pdf-raster-only | TeX → ビルド | 実務で自然な内容にする。 |
| pdf-text-layer | TeX → ビルド | テキスト層のある PDF。TeX ソースを realistic な実務文書に書き換えてビルド。 |
| png | 画像生成/レンダラ | matplotlib/PIL/TeX→PNG でレンダリングした実務の図表/スキャン。 |
| office-powerpoint | PowerPoint プラグイン | PowerPoint プラグインで実務スライド (図表画像を埋込)。 |
| code-source | 直接記述 | その職種が実際に書くソース。動く体裁のコード (関数・コメント・import) にする。 |
| eml | 直接記述 | 実務で自然な内容にする。 |
| jsonl | 直接記述 | 実務のイベント/レコードを 1 行 1 JSON で。 |
| log | 直接記述 | 実際のアプリ/システムログ形式 (タイムスタンプ + レベル + メッセージ)。 |
| notebook-json | 直接記述 | 実際の Jupyter ノート JSON (cells 配列、code+markdown セル、outputs は簡素で可)。 |
| plain-text | 直接記述 | 素のテキストメモ/転記/エクスポート。 |
| structured-csv | 直接記述 | 実務の CSV エクスポート (ヘッダ行 + 現実的な列)。 |
| structured-json | 直接記述 | 実務の設定/エクスポート JSON。 |
| structured-sql | 直接記述 | 実務の SQL (DDL/クエリ/マイグレーション)。 |
| structured-xml | 直接記述 | 実務の XML (設定/エクスポート/フィード)。 |
| structured-yaml | 直接記述 | 実務の設定 YAML (CI/インフラ/アプリ設定)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**Kio は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 70 / en 30` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **臨床研究・プロトコル** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p16 担当分)

### `qb16` — class **hard1**

- **クエリ**: 「投薬を止める基準値はいくつか」
- **正解ファイル**: `corpus/p16/home/clinical/studies/study-alpha/2026/protocols/protocol-note.pdf`
- **正解の所在**: section「安全性節」
- **埋め込む事実 (この表現・値を必ず使う)**: 投与中止の閾値は 1.8 mg/L。
- **section hint**: 安全性節
- **fact_id**: `f024` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb16`: `corpus/p16/home/clinical/studies/study-alpha/2026/protocols/dose-monitoring.pdf`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard1 不変条件 (ラスタスキャン PDF)**

- TeX → PDF → `pdftoppm -r 200 -png` → `img2pdf` の順でビルドし、**テキスト層をゼロ**にする。
- 最終 PDF に `pdftotext` をかけ、Unicode 空白を除去した結果が **空** でなければ不合格。
- 事実は **ラスタ画像の画素**にのみ存在させる。

### `qb23` — class **hard3**

- **クエリ**: 「第12週の B パネルの有害事象数はいくつか」
- **正解ファイル**: `corpus/p16/home/clinical/studies/study-alpha/2026/results/safety-grid.png`
- **正解の所在**: section「Rendered safety grid」
- **埋め込む事実 (この表現・値を必ず使う)**: Panel B reports 4 adverse events at week 12.
- **section hint**: Rendered safety grid
- **fact_id**: `f031` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb23`: `corpus/p16/home/clinical/studies/study-alpha/2026/results/safety-panels.png`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard3 不変条件 (レンダリングされた図表の事実)**

- 事実の値・軸・凡例・ラベルは **matplotlib/PIL/TeX→PNG でレンダリングした画像**にのみ描く。
- PPTX の場合はその画像を指定スライドに埋め込む。**スライドの編集可能テキスト・ノート・
  alt text・プロパティ・ChartML に事実を漏らさない** (alt text は一般的な語のみ)。
- 拡散生成画像を事実の担体にしない。

---

## 5. 既に定義済みのソース資産 (これを realism 版に差し替える)

骨格は以下に定義済みです。**構造・ページ数・埋込 fact は維持したまま、本文と図表を realistic に**
書き換えてください。

- `office-specs/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0811-review-summary-037.docx.md`
- `office-specs/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0812-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0813-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0814-status-review-040.pptx.md`
- `office-specs/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0815-status-review-041.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p16-0771.tex`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p16-0772.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p16-0768.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p16-0806.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p16-0807.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p16-0808.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p16-0809.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p16-0810.tex`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0766.log`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0767.py`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0775.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0776.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0777.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0778.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0779.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0780.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0781.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0782.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0783.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0784.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0785.md`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0786.txt`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0787.log`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0788.jsonl`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0789.txt`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0790.log`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0791.jsonl`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0792.txt`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0793.sh`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0794.py`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0795.rs`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0796.xml`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0797.sql`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0798.csv`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0799.json`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0800.yaml`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0801.xml`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0802.sql`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0803.eml`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0804.ipynb`
- `sources/text/baseline-fixture-b-v1/p16/r-baseline-fixture-b-v1-p16-0805.ipynb`
- `sources/visual/specs/r-baseline-fixture-b-v1-p16-0769.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p16-0773.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p16-0774.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p16-0770.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p16/` と `qhard-a/p16/` の中だけ**。他 persona 0 件。
- [ ] **`.kio` を 1 つも作っていない**。Kio の内部形式を一切書いていない。
- [ ] OCR / Office→PDF 変換 / embedding / 索引化を **実行していない**。
- [ ] ファイル数が **B=50 (home 45 / ambient 5)** と完全一致。
- [ ] パス・ファイル名・形式が §2 の表と完全一致 (改名・追加・削除なし)。
- [ ] `home/` のファイルは全て **leaf 直下**。中間ディレクトリ直下に置いていない。
- [ ] text 系は strict UTF-8・BOM/NUL なし。
- [ ] 正解の fact が **コーパス内 1 回だけ**。distractor に fact が入っていない。
- [ ] `ambient-home/` に fact を置いていない。
- [ ] Office/画像のメタデータ・alt text・EXIF に fact/クエリ/ID/ファイル名を書いていない。
- [ ] 5 MiB / 20 ページ・スライド の上限内。
- [ ] hard1 がある場合、最終 PDF の `pdftotext` 出力が空であることを確認した。

## 7. 引き渡し

生成物は **普通のファイルのみ**。この後、オペレータ側で実 Kio パイプラインが
`kio init` → `kio index --approve --online` を実行し、`.kio` 生成・Office→PDF 変換・
OCR (Mistral Batch)・CAS 保存・embedding (Gemini)・索引化を行います。
さらにその後、別セッションで **編集・追加・削除・フォルダ移動**を行い、実パイプラインで
履歴 (time-travel / `--all-history` / `--include-deleted`) を生成します。

