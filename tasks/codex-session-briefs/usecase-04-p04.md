# Codex セッション ブリーフ — ユースケース 4/20 : `p04` ML 研究・実験管理

> **このセッションで生成するのは `p04` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: ML research / model experiments / 言語比率: **en 100**

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
| 親フォルダ (B) | `corpus/p04/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| Q_hard 追加パック (A) `qhard-a/p04/` | 3 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 17 (+A 2) |
| embedding 見積り chunk (B) | 54 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 1 |
| jpeg / jpeg | 1 |
| md / markdown | 7 |
| pdf_text / pdf-text-layer | 4 |
| png / png | 2 |
| pptx / office-powerpoint | 2 |
| txt / code-source | 18 |
| txt / log | 2 |
| txt / notebook-json | 8 |
| txt / plain-text | 1 |
| txt / structured-json | 1 |
| txt / structured-xml | 1 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p04/home/` の 20 scope leaf

各 leaf は **1 つの Kio scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/closed/experiment-runs` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-040.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `utility-020.py` | txt / code-source | en | offline | filler |

#### 2. `home/cloud/personal/experiment-notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-037.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-017.rs` | txt / code-source | en | offline | filler |

#### 3. `home/cloud/team/research-shared` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-038.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-018.ts` | txt / code-source | en | offline | filler |

#### 4. `home/datasets/governance/cards` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-028.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-008.py` | txt / code-source | en | offline | filler |

#### 5. `home/desktop/current-experiment` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-033.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-013.rs` | txt / code-source | en | offline | filler |

#### 6. `home/documents/reference/research-methods` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-034.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-014.ts` | txt / code-source | en | offline | filler |

#### 7. `home/downloads/exports/model-reports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-016.py` | txt / code-source | en | offline | filler |

#### 8. `home/downloads/inbox/dataset-drops` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-035.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-015.sh` | txt / code-source | en | offline | filler |

#### 9. `home/evaluations/benchmarks/leaderboards` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-030.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-010.ts` | txt / code-source | en | offline | filler |

#### 10. `home/mail/recent/review-threads` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |
| `utility-019.sh` | txt / code-source | en | offline | filler |

#### 11. `home/models/registry/model-cards` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-029.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-009.rs` | txt / code-source | en | offline | filler |

#### 12. `home/notebooks/exports/analysis` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-007.log` | txt / log | en | offline | filler |
| `record-027.xml` | txt / structured-xml | en | offline | filler |

#### 13. `home/presentations/lab/meetings` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-031.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-011.sh` | txt / code-source | en | offline | filler |

#### 14. `home/repos/ml-project/documentation` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-032.ipynb` | txt / notebook-json | en | offline | filler |
| `utility-012.py` | txt / code-source | en | offline | filler |

#### 15. `home/research/library/literature-notes` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `trend-figure-042.png` | png / png | en | online_ocr | filler |
| `utility-022.ts` | txt / code-source | en | offline | filler |
| `worklog-002.md` | md / markdown | en | offline | filler |

#### 16. `home/research/library/papers` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-041.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `utility-021.rs` | txt / code-source | en | offline | filler |
| `worklog-001.md` | md / markdown | en | offline | filler |

#### 17. `home/research/programs/model-alpha/experiments/configs` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `trend-figure-043.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `utility-023.sh` | txt / code-source | en | offline | filler |
| `worklog-003.md` | md / markdown | en | offline | filler |

#### 18. `home/research/programs/model-alpha/experiments/results` — 4 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `ablation-notes.md` | md / markdown | en | offline | **★正解** |
| `experiment-comparison.md` | md / markdown | en | offline | **△distractor** |
| `utility-024.py` | txt / code-source | en | offline | filler |
| `worklog-004.md` | md / markdown | en | offline | filler |

#### 19. `home/research/programs/model-beta/experiments/configs` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-025.json` | txt / structured-json | en | offline | filler |
| `worklog-005.md` | md / markdown | en | offline | filler |

#### 20. `home/research/programs/model-beta/experiments/results` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-006.txt` | txt / plain-text | en | offline | filler |
| `record-026.yaml` | txt / structured-yaml | en | offline | filler |

### `corpus/p04/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/scratch/runs/model-alpha/exp-0042/seed-003/checkpoints/epoch-020/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p04.pdf` | pdf_text / pdf-text-layer | en | online_ocr |
| `archived-session-p04.log` | txt / log | en | offline |
| `budget-sheet-p04.xlsx` | xlsx_realism / xlsx-realism | en | unsupported |
| `field-photo-p04.png` | png / png | en | online_ocr |
| `legacy-helper-p04.py` | txt / code-source | en | offline |

### `qhard-a/p04/` — 3 件 (Q_hard 追加パック)

**B とは事実・ファイルを共有しません。** 別の fact/query 名前空間です。

パス: `qhard-a/p04/home/research/programs/model-alpha/experiments/results/`

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `ablation-grid.png` | png / png | en | online_ocr | **★正解** |
| `context-overview.md` | md / markdown | en | offline | filler |
| `validation-grid.png` | png / png | en | online_ocr | **△distractor** |

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
| log | 直接記述 | 実際のアプリ/システムログ形式 (タイムスタンプ + レベル + メッセージ)。 |
| notebook-json | 直接記述 | 実際の Jupyter ノート JSON (cells 配列、code+markdown セル、outputs は簡素で可)。 |
| plain-text | 直接記述 | 素のテキストメモ/転記/エクスポート。 |
| structured-json | 直接記述 | 実務の設定/エクスポート JSON。 |
| structured-xml | 直接記述 | 実務の XML (設定/エクスポート/フィード)。 |
| structured-yaml | 直接記述 | 実務の設定 YAML (CI/インフラ/アプリ設定)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**Kio は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `en 100` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **ML 研究・実験管理** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p04 担当分)

### `qa06` — class **hard3**

- **クエリ**: 「ablation 表の seed 17 の精度はいくつか」
- **正解ファイル**: `qhard-a/p04/home/research/programs/model-alpha/experiments/results/ablation-grid.png`
- **正解の所在**: section「Rendered ablation grid」
- **埋め込む事実 (この表現・値を必ず使う)**: Seed 17 records an accuracy of 0.842 in the ablation grid.
- **section hint**: Rendered ablation grid
- **fact_id**: `f006` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qa06`: `qhard-a/p04/home/research/programs/model-alpha/experiments/results/validation-grid.png`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard3 不変条件 (レンダリングされた図表の事実)**

- 事実の値・軸・凡例・ラベルは **matplotlib/PIL/TeX→PNG でレンダリングした画像**にのみ描く。
- PPTX の場合はその画像を指定スライドに埋め込む。**スライドの編集可能テキスト・ノート・
  alt text・プロパティ・ChartML に事実を漏らさない** (alt text は一般的な語のみ)。
- 拡散生成画像を事実の担体にしない。

### `qb04` — class **hard2**

- **クエリ**: 「乱数条件の成果はどの水準だったか」
- **正解ファイル**: `corpus/p04/home/research/programs/model-alpha/experiments/results/ablation-notes.md`
- **正解の所在**: section「Experiment result」
- **埋め込む事実 (この表現・値を必ず使う)**: The Lumen trial retained a validation score of 0.913 for seed K-17.
- **section hint**: Experiment result
- **fact_id**: `f012` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb04`: `corpus/p04/home/research/programs/model-alpha/experiments/results/experiment-comparison.md`
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

- `office-specs/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0203-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0204-status-review-040.pptx.md`
- `office-specs/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0205-status-review-041.pptx.md`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p04-0160.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p04-0200.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p04-0201.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p04-0202.tex`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0158.log`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0159.py`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0163.md`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0164.md`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0165.md`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0166.md`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0167.md`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0168.md`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0169.md`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0170.txt`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0171.log`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0172.py`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0173.rs`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0174.ts`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0175.sh`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0176.py`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0177.rs`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0178.ts`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0179.sh`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0180.py`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0181.rs`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0182.ts`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0183.sh`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0184.py`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0185.rs`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0186.ts`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0187.sh`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0188.py`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0189.json`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0190.yaml`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0191.xml`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0192.ipynb`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0193.ipynb`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0194.ipynb`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0195.ipynb`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0196.ipynb`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0197.ipynb`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0198.ipynb`
- `sources/text/baseline-fixture-b-v1/p04/r-baseline-fixture-b-v1-p04-0199.ipynb`
- `sources/text/qhard-a-v1/p04/r-qhard-a-v1-p04-1033.md`
- `sources/visual/specs/r-baseline-fixture-b-v1-p04-0161.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p04-0206.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p04-0207.json`
- `sources/visual/specs/r-qhard-a-v1-p04-1031.json`
- `sources/visual/specs/r-qhard-a-v1-p04-1032.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p04-0162.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p04/` と `qhard-a/p04/` の中だけ**。他 persona 0 件。
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

