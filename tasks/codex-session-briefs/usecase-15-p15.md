# Codex セッション ブリーフ — ユースケース 15/20 : `p15` 採用・候補者評価

> **このセッションで生成するのは `p15` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: people operations / requisition / 言語比率: **ja 80 / en 20**

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
| 親フォルダ (B) | `corpus/p15/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| Q_hard 追加パック (A) `qhard-a/p15/` | 3 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 35 (+A 3) |
| embedding 見積り chunk (B) | 67 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 5 |
| jpeg / jpeg | 1 |
| md / markdown | 15 |
| pdf_rasterized / pdf-raster-only | 1 |
| pdf_text / pdf-text-layer | 6 |
| png / png | 1 |
| pptx / office-powerpoint | 1 |
| txt / code-source | 1 |
| txt / eml | 3 |
| txt / html | 3 |
| txt / jsonl | 2 |
| txt / log | 3 |
| txt / notebook-json | 1 |
| txt / plain-text | 2 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| txt / structured-sql | 1 |
| txt / structured-xml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p15/home/` の 20 scope leaf

各 leaf は **1 つの Kio scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/recruiting/fy2025/closed` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-020.jsonl` | txt / jsonl | ja | offline | filler |
| `review-summary-040.docx` | docx / office-word | ja | online_ocr | filler |

#### 2. `home/cloud/drive/recruiting-notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-017.jsonl` | txt / jsonl | ja | offline | filler |
| `reference-brief-037.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 3. `home/cloud/sharepoint/people-operations` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-018.txt` | txt / plain-text | ja | offline | filler |
| `archived-note-038.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | filler |

#### 4. `home/compensation/bands/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-031.eml` | txt / eml | en | offline | filler |
| `worklog-011.md` | md / markdown | ja | offline | filler |

#### 5. `home/compliance/retention/hr-records` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-032.ipynb` | txt / notebook-json | ja | offline | filler |
| `worklog-012.md` | md / markdown | ja | offline | filler |

#### 6. `home/desktop/recruiting/requisition-alpha` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-033.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `worklog-013.md` | md / markdown | ja | offline | filler |

#### 7. `home/documents/people/policies/reference` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |
| `worklog-014.md` | md / markdown | ja | offline | filler |

#### 8. `home/downloads/ats-exports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | ja | offline | filler |
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 9. `home/downloads/inbox/candidate-packets` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-035.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `worklog-015.md` | md / markdown | ja | offline | filler |

#### 10. `home/learning/training/catalog` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-030.html` | txt / html | ja | offline | filler |
| `worklog-010.md` | md / markdown | ja | offline | filler |

#### 11. `home/mail/outlook/requisition-alpha/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-019.log` | txt / log | ja | offline | filler |
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |

#### 12. `home/people/headcount/planning` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-027.eml` | txt / eml | ja | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 13. `home/people/performance/synthetic-cycles` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-028.html` | txt / html | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 14. `home/people/policies/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-026.html` | txt / html | ja | offline | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 15. `home/people/surveys/synthetic-results` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-029.eml` | txt / eml | en | offline | filler |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 16. `home/recruiting/offers/active` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-025.json` | txt / structured-json | ja | offline | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 17. `home/recruiting/requisition-alpha/candidates` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-021.txt` | txt / plain-text | ja | offline | filler |
| `review-summary-041.docx` | docx / office-word | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

#### 18. `home/recruiting/requisition-alpha/interviews/round-2` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `decision-summary.docx` | docx / office-word | en | online_ocr | **★正解** |
| `panel-review.docx` | docx / office-word | en | online_ocr | **△distractor** |
| `record-022.xml` | txt / structured-xml | ja | offline | filler |
| `status-review-042.pptx` | pptx / office-powerpoint | ja | online_ocr | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 19. `home/recruiting/requisition-beta/candidates` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-023.sql` | txt / structured-sql | ja | offline | filler |
| `trend-figure-043.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 20. `home/recruiting/requisition-beta/interviews/round-2` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-024.csv` | txt / structured-csv | ja | offline | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

### `corpus/p15/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/ats-cache/req-alpha/candidate-syn-017/interviews/round-2/panel/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p15.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p15.log` | txt / log | ja | offline |
| `budget-sheet-p15.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p15.png` | png / png | ja | online_ocr |
| `legacy-helper-p15.py` | txt / code-source | ja | offline |

### `qhard-a/p15/` — 3 件 (Q_hard 追加パック)

**B とは事実・ファイルを共有しません。** 別の fact/query 名前空間です。

パス: `qhard-a/p15/home/recruiting/requisition-alpha/interviews/round-2/`

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `context-overview.md` | md / markdown | en | offline | filler |
| `interview-review.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **★正解** |
| `panel-schedule.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **△distractor** |

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
| html | 直接記述 | 実務で自然な内容にする。 |
| jsonl | 直接記述 | 実務のイベント/レコードを 1 行 1 JSON で。 |
| log | 直接記述 | 実際のアプリ/システムログ形式 (タイムスタンプ + レベル + メッセージ)。 |
| notebook-json | 直接記述 | 実際の Jupyter ノート JSON (cells 配列、code+markdown セル、outputs は簡素で可)。 |
| plain-text | 直接記述 | 素のテキストメモ/転記/エクスポート。 |
| structured-csv | 直接記述 | 実務の CSV エクスポート (ヘッダ行 + 現実的な列)。 |
| structured-json | 直接記述 | 実務の設定/エクスポート JSON。 |
| structured-sql | 直接記述 | 実務の SQL (DDL/クエリ/マイグレーション)。 |
| structured-xml | 直接記述 | 実務の XML (設定/エクスポート/フィード)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**Kio は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 80 / en 20` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **採用・候補者評価** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p15 担当分)

### `qa04` — class **hard1**

- **クエリ**: 「最終面談に割り当てた時間は何分か」
- **正解ファイル**: `qhard-a/p15/home/recruiting/requisition-alpha/interviews/round-2/interview-review.pdf`
- **正解の所在**: section「面談節」
- **埋め込む事実 (この表現・値を必ず使う)**: 採用面談の最終枠は 45 分。
- **section hint**: 面談節
- **fact_id**: `f004` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qa04`: `qhard-a/p15/home/recruiting/requisition-alpha/interviews/round-2/panel-schedule.pdf`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard1 不変条件 (ラスタスキャン PDF)**

- TeX → PDF → `pdftoppm -r 200 -png` → `img2pdf` の順でビルドし、**テキスト層をゼロ**にする。
- 最終 PDF に `pdftotext` をかけ、Unicode 空白を除去した結果が **空** でなければ不合格。
- 事実は **ラスタ画像の画素**にのみ存在させる。

### `qb15` — class **hard2**

- **クエリ**: 「採用提案へ進むための評価値はいくつか」
- **正解ファイル**: `corpus/p15/home/recruiting/requisition-alpha/interviews/round-2/decision-summary.docx`
- **正解の所在**: section「Panel threshold」
- **埋め込む事実 (この表現・値を必ず使う)**: The Cobalt applicant requires a panel score of 4.3 before offer review.
- **section hint**: Panel threshold
- **fact_id**: `f023` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb15`: `corpus/p15/home/recruiting/requisition-alpha/interviews/round-2/panel-review.docx`
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

- `office-specs/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0721-decision-summary.docx.md`
- `office-specs/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0722-panel-review.docx.md`
- `office-specs/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0761-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0762-review-summary-040.docx.md`
- `office-specs/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0763-review-summary-041.docx.md`
- `office-specs/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0764-status-review-042.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p15-0760.tex`
- `sources/pdf/raster-only/r-qhard-a-v1-p15-1025.tex`
- `sources/pdf/raster-only/r-qhard-a-v1-p15-1026.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p15-0718.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p15-0755.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p15-0756.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p15-0757.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p15-0758.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p15-0759.tex`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0716.log`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0717.py`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0723.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0724.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0725.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0726.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0727.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0728.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0729.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0730.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0731.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0732.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0733.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0734.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0735.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0736.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0737.md`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0738.log`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0739.jsonl`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0740.txt`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0741.log`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0742.jsonl`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0743.txt`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0744.xml`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0745.sql`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0746.csv`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0747.json`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0748.html`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0749.eml`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0750.html`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0751.eml`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0752.html`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0753.eml`
- `sources/text/baseline-fixture-b-v1/p15/r-baseline-fixture-b-v1-p15-0754.ipynb`
- `sources/text/qhard-a-v1/p15/r-qhard-a-v1-p15-1027.md`
- `sources/visual/specs/r-baseline-fixture-b-v1-p15-0719.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p15-0765.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p15-0720.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p15/` と `qhard-a/p15/` の中だけ**。他 persona 0 件。
- [ ] **`.kio` を 1 つも作っていない**。Kio の内部形式を一切書いていない。
- [ ] OCR / Office→PDF 変換 / embedding / 索引化を **実行していない**。
- [ ] ファイル数が **B=50 (home 45 / ambient 5)** **A=3** と完全一致。
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

