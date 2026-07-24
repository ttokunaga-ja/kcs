# Codex セッション ブリーフ — ユースケース 7/20 : `p07` 人文学アーカイブ・文献調査

> **このセッションで生成するのは `p07` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: humanities archive / citation recovery / 言語比率: **en 55 / fr 15 / de 15 / ja 15**

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
| 親フォルダ (B) | `corpus/p07/` |
| 生成ファイル数 (B) | **51** |
| └ `home/` (索引対象・20 scope leaf) | 46 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 28 |
| embedding 見積り chunk (B) | 60 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 3 |
| jpeg / jpeg | 2 |
| md / markdown | 19 |
| pdf_rasterized / pdf-raster-only | 3 |
| pdf_text / pdf-text-layer | 6 |
| png / png | 1 |
| pptx / office-powerpoint | 1 |
| txt / code-source | 1 |
| txt / eml | 1 |
| txt / jsonl | 3 |
| txt / log | 4 |
| txt / notebook-json | 1 |
| txt / plain-text | 3 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p07/home/` の 20 scope leaf

各 leaf は **1 つの KCS scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/closed-research/2018-2025` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-020.jsonl` | txt / jsonl | fr | offline | filler |
| `review-summary-040.docx` | docx / office-word | fr | online_ocr | filler |

#### 2. `home/cloud/personal/dissertation-notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-037.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `worklog-017.md` | md / markdown | en | offline | filler |

#### 3. `home/cloud/team-shared/translation-workshop` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `archived-note-038.pdf` | pdf_rasterized / pdf-raster-only | de | online_ocr | filler |
| `worklog-018.md` | md / markdown | de | offline | filler |

#### 4. `home/conferences/2026/presentations/accepted` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-031.eml` | txt / eml | ja | offline | filler |
| `worklog-011.md` | md / markdown | en | offline | filler |

#### 5. `home/correspondence/archives/requests/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-032.ipynb` | txt / notebook-json | fr | offline | filler |
| `worklog-012.md` | md / markdown | fr | offline | filler |

#### 6. `home/desktop/current-chapter` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-033.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `worklog-013.md` | md / markdown | en | offline | filler |

#### 7. `home/dissertation/manuscript/appendices/source-tables` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-029.csv` | txt / structured-csv | en | offline | filler |
| `worklog-009.md` | md / markdown | en | offline | filler |

#### 8. `home/dissertation/manuscript/chapter-01/drafts` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-027.txt` | txt / plain-text | ja | offline | filler |
| `worklog-007.md` | md / markdown | en | offline | filler |

#### 9. `home/dissertation/manuscript/chapter-02/drafts` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-028.log` | txt / log | fr | offline | filler |
| `worklog-008.md` | md / markdown | en | offline | filler |

#### 10. `home/documents/humanities/reference-library` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | de | online_ocr | filler |
| `worklog-014.md` | md / markdown | de | offline | filler |

#### 11. `home/downloads/exports/ocr-corrections` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | fr | online_ocr | filler |
| `worklog-016.md` | md / markdown | fr | offline | filler |

#### 12. `home/downloads/inbox/archive-images` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-035.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |
| `worklog-015.md` | md / markdown | ja | offline | filler |

#### 13. `home/mail/archive-correspondence/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-039.docx` | docx / office-word | ja | online_ocr | filler |
| `worklog-019.md` | md / markdown | ja | offline | filler |

#### 14. `home/notes/literature/periods/modernism` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-026.jsonl` | txt / jsonl | de | offline | filler |
| `worklog-006.md` | md / markdown | en | offline | filler |

#### 15. `home/notes/primary-sources/annotations/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-025.log` | txt / log | en | offline | filler |
| `worklog-005.md` | md / markdown | en | offline | filler |

#### 16. `home/research/bibliography/zotero/exports` — 4 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-024.txt` | txt / plain-text | fr | offline | filler |
| `citation-clusters.jpeg` | jpeg / jpeg | en | online_ocr | **△distractor** |
| `citation-network.jpeg` | jpeg / jpeg | en | online_ocr | **★正解** |
| `worklog-004.md` | md / markdown | en | offline | filler |

#### 17. `home/research/sources/archive-alpha/box-001/ocr-transcripts` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-021.txt` | txt / plain-text | en | offline | filler |
| `insurance-note.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | **△distractor** |
| `meeting-notes.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | **★正解** |
| `review-summary-041.docx` | docx / office-word | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | en | offline | filler |

#### 18. `home/research/sources/archive-beta/box-014/digital-surrogates` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-022.log` | txt / log | de | offline | filler |
| `status-review-042.pptx` | pptx / office-powerpoint | de | online_ocr | filler |
| `worklog-002.md` | md / markdown | en | offline | filler |

#### 19. `home/research/sources/manuscripts/collection-a/transcriptions` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-023.jsonl` | txt / jsonl | ja | offline | filler |
| `worklog-003.md` | md / markdown | en | offline | filler |

#### 20. `home/translations/archive-alpha/letters/working` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-030.json` | txt / structured-json | de | offline | filler |
| `worklog-010.md` | md / markdown | en | offline | filler |

### `corpus/p07/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/imports/archive-alpha/box-001/folder-07/item-003/derivatives/ocr/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p07.pdf` | pdf_text / pdf-text-layer | en | online_ocr |
| `archived-session-p07.log` | txt / log | en | offline |
| `budget-sheet-p07.xlsx` | xlsx_realism / xlsx-realism | en | unsupported |
| `field-photo-p07.png` | png / png | en | online_ocr |
| `legacy-helper-p07.py` | txt / code-source | en | offline |

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
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**KCS は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `en 55 / fr 15 / de 15 / ja 15` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **人文学アーカイブ・文献調査** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p07 担当分)

### `qb07` — class **hard1**

- **クエリ**: 「資料箱の運搬補償の天井額は何円か」
- **正解ファイル**: `corpus/p07/home/research/sources/archive-alpha/box-001/ocr-transcripts/meeting-notes.pdf`
- **正解の所在**: section「保険節」
- **埋め込む事実 (この表現・値を必ず使う)**: 記録箱の輸送保険上限は 42 万円。
- **section hint**: 保険節
- **fact_id**: `f015` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb07`: `corpus/p07/home/research/sources/archive-alpha/box-001/ocr-transcripts/insurance-note.pdf`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard1 不変条件 (ラスタスキャン PDF)**

- TeX → PDF → `pdftoppm -r 200 -png` → `img2pdf` の順でビルドし、**テキスト層をゼロ**にする。
- 最終 PDF に `pdftotext` をかけ、Unicode 空白を除去した結果が **空** でなければ不合格。
- 事実は **ラスタ画像の画素**にのみ存在させる。

### `qb22` — class **hard3**

- **クエリ**: 「Arendt ノードへの流入引用数はいくつか」
- **正解ファイル**: `corpus/p07/home/research/bibliography/zotero/exports/citation-network.jpeg`
- **正解の所在**: section「Rendered citation network」
- **埋め込む事実 (この表現・値を必ず使う)**: Node Arendt has 31 inbound citation links.
- **section hint**: Rendered citation network
- **fact_id**: `f030` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb22`: `corpus/p07/home/research/bibliography/zotero/exports/citation-clusters.jpeg`
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

- `office-specs/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0358-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0359-review-summary-040.docx.md`
- `office-specs/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0360-review-summary-041.docx.md`
- `office-specs/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0361-status-review-042.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p07-0316.tex`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p07-0317.tex`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p07-0357.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p07-0313.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p07-0352.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p07-0353.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p07-0354.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p07-0355.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p07-0356.tex`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0311.log`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0312.py`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0320.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0321.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0322.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0323.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0324.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0325.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0326.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0327.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0328.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0329.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0330.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0331.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0332.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0333.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0334.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0335.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0336.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0337.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0338.md`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0339.jsonl`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0340.txt`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0341.log`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0342.jsonl`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0343.txt`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0344.log`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0345.jsonl`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0346.txt`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0347.log`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0348.csv`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0349.json`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0350.eml`
- `sources/text/baseline-fixture-b-v1/p07/r-baseline-fixture-b-v1-p07-0351.ipynb`
- `sources/visual/specs/r-baseline-fixture-b-v1-p07-0314.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p07-0318.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p07-0319.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p07-0315.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p07/` と `qhard-a/p07/` の中だけ**。他 persona 0 件。
- [ ] **`.kcs` を 1 つも作っていない**。KCS の内部形式を一切書いていない。
- [ ] OCR / Office→PDF 変換 / embedding / 索引化を **実行していない**。
- [ ] ファイル数が **B=51 (home 46 / ambient 5)** と完全一致。
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

