# Codex セッション ブリーフ — ユースケース 6/20 : `p06` ライフサイエンス・アッセイ研究

> **このセッションで生成するのは `p06` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: life science / assay study / 言語比率: **en 100**

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
| 親フォルダ (B) | `corpus/p06/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 23 |
| embedding 見積り chunk (B) | 56 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 3 |
| jpeg / jpeg | 1 |
| md / markdown | 9 |
| pdf_rasterized / pdf-raster-only | 1 |
| pdf_text / pdf-text-layer | 4 |
| png / png | 3 |
| pptx / office-powerpoint | 2 |
| txt / code-source | 8 |
| txt / jsonl | 2 |
| txt / log | 3 |
| txt / notebook-json | 5 |
| txt / plain-text | 1 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| txt / structured-sql | 2 |
| txt / structured-xml | 2 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p06/home/` の 20 scope leaf

各 leaf は **1 つの Kio scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/completed-studies/2020-2025` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-040.docx` | docx / office-word | en | online_ocr | filler |
| `utility-020.py` | txt / code-source | en | offline | filler |

#### 2. `home/cloud/personal/research-scratch` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `archived-note-037.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | filler |
| `utility-017.rs` | txt / code-source | en | offline | filler |

#### 3. `home/cloud/team-shared/study-alpha-consortium` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-038.docx` | docx / office-word | en | online_ocr | filler |
| `utility-018.ts` | txt / code-source | en | offline | filler |

#### 4. `home/desktop/lab-dashboard/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-013.log` | txt / log | en | offline | filler |
| `analysis-033.ipynb` | txt / notebook-json | en | offline | filler |

#### 5. `home/documents/life-science/reference-library` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | en | offline | filler |
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 6. `home/downloads/exports/analysis-packages` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-016.py` | txt / code-source | en | offline | filler |

#### 7. `home/downloads/inbox/instrument-drops` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-035.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-015.sh` | txt / code-source | en | offline | filler |

#### 8. `home/grants/fy2027/applications/active` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-010.log` | txt / log | en | offline | filler |
| `analysis-030.ipynb` | txt / notebook-json | en | offline | filler |

#### 9. `home/instruments/mass-spec/calibration/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-027.xml` | txt / structured-xml | en | offline | filler |
| `worklog-007.md` | md / markdown | en | offline | filler |

#### 10. `home/lab/notebooks/2026/current` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `trend-figure-041.png` | png / png | en | online_ocr | filler |
| `utility-021.rs` | txt / code-source | en | offline | filler |
| `worklog-001.md` | md / markdown | en | offline | filler |

#### 11. `home/literature/life-science/papers/reviewed` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-029.ipynb` | txt / notebook-json | en | offline | filler |
| `worklog-009.md` | md / markdown | en | offline | filler |

#### 12. `home/mail/lab-collaborators/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |
| `utility-019.sh` | txt / code-source | en | offline | filler |

#### 13. `home/manuscripts/study-alpha/figures/revision-03` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-011.jsonl` | txt / jsonl | en | offline | filler |
| `analysis-031.ipynb` | txt / notebook-json | en | offline | filler |

#### 14. `home/meetings/life-science/lab/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-012.txt` | txt / plain-text | en | offline | filler |
| `analysis-032.ipynb` | txt / notebook-json | en | offline | filler |

#### 15. `home/programs/study-alpha/2026/cohort-a/run-001/analysis` — 4 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `assay-summary.pptx` | pptx / office-powerpoint | en | online_ocr | **★正解** |
| `cohort-comparison.pptx` | pptx / office-powerpoint | en | online_ocr | **△distractor** |
| `record-024.csv` | txt / structured-csv | en | offline | filler |
| `worklog-004.md` | md / markdown | en | offline | filler |

#### 16. `home/programs/study-alpha/2026/cohort-a/run-001/raw-exports` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-023.sql` | txt / structured-sql | en | offline | filler |
| `trend-figure-043.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `worklog-003.md` | md / markdown | en | offline | filler |

#### 17. `home/programs/study-alpha/2026/protocols/approved` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-022.xml` | txt / structured-xml | en | offline | filler |
| `trend-figure-042.png` | png / png | en | online_ocr | filler |
| `worklog-002.md` | md / markdown | en | offline | filler |

#### 18. `home/programs/study-beta/2026/cohort-b/run-014/analysis` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-026.yaml` | txt / structured-yaml | en | offline | filler |
| `worklog-006.md` | md / markdown | en | offline | filler |

#### 19. `home/programs/study-beta/2026/cohort-b/run-014/raw-exports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-025.json` | txt / structured-json | en | offline | filler |
| `worklog-005.md` | md / markdown | en | offline | filler |

#### 20. `home/samples/cohort-manifests/2026/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-028.sql` | txt / structured-sql | en | offline | filler |
| `worklog-008.md` | md / markdown | en | offline | filler |

### `corpus/p06/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/instrument-staging/mass-spec/run-001/vendor/raw/chunks/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p06.pdf` | pdf_text / pdf-text-layer | en | online_ocr |
| `archived-session-p06.log` | txt / log | en | offline |
| `budget-sheet-p06.xlsx` | xlsx_realism / xlsx-realism | en | unsupported |
| `field-photo-p06.png` | png / png | en | online_ocr |
| `legacy-helper-p06.py` | txt / code-source | en | offline |

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

- 本文は `en 100` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **ライフサイエンス・アッセイ研究** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p06 担当分)

### `qb06` — class **hard3**

- **クエリ**: 「6回目の測定で cohort A はどの値に達したか」
- **正解ファイル**: `corpus/p06/home/programs/study-alpha/2026/cohort-a/run-001/analysis/assay-summary.pptx`
- **正解の所在**: section「Rendered assay chart」
- **埋め込む事実 (この表現・値を必ず使う)**: Cohort A reached 73.4 ng/mL at cycle 6.
- **section hint**: Rendered assay chart
- **fact_id**: `f014` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb06`: `corpus/p06/home/programs/study-alpha/2026/cohort-a/run-001/analysis/cohort-comparison.pptx`
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

- `office-specs/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0266-assay-summary.pptx.md`
- `office-specs/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0267-cohort-comparison.pptx.md`
- `office-specs/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0305-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0306-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0307-review-summary-040.docx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p06-0304.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p06-0263.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p06-0301.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p06-0302.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p06-0303.tex`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0261.log`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0262.py`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0268.md`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0269.md`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0270.md`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0271.md`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0272.md`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0273.md`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0274.md`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0275.md`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0276.md`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0277.log`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0278.jsonl`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0279.txt`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0280.log`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0281.jsonl`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0282.sh`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0283.py`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0284.rs`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0285.ts`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0286.sh`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0287.py`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0288.rs`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0289.xml`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0290.sql`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0291.csv`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0292.json`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0293.yaml`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0294.xml`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0295.sql`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0296.ipynb`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0297.ipynb`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0298.ipynb`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0299.ipynb`
- `sources/text/baseline-fixture-b-v1/p06/r-baseline-fixture-b-v1-p06-0300.ipynb`
- `sources/visual/specs/r-baseline-fixture-b-v1-p06-0264.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p06-0266-embedded.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p06-0267-embedded.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p06-0308.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p06-0309.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p06-0310.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p06-0265.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p06/` と `qhard-a/p06/` の中だけ**。他 persona 0 件。
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

