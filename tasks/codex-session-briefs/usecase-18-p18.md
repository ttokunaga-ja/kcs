# Codex セッション ブリーフ — ユースケース 18/20 : `p18` 製造品質・検査

> **このセッションで生成するのは `p18` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: manufacturing quality / lot inspection / 言語比率: **ja 75 / en 25**

---

## 0. 絶対規則 — 違反したらこのセッションの成果物は破棄

1. **`.kio` を作らない・触らない・書かない。** KIO の内部 (objects / index / sqlite / manifest 相当) を
   自分で作ることは全面禁止。あなたが作るのは **普通のファイルとフォルダだけ**。
2. **OCR・Office→PDF 変換・embedding・索引化を自分で実行しない。** それらは後段の
   実 KIO パイプライン (`kio init` / `kio index --approve --online`) だけが行う。
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
| 親フォルダ (B) | `corpus/p18/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| Q_hard 追加パック (A) `qhard-a/p18/` | 3 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 21 (+A 2) |
| embedding 見積り chunk (B) | 57 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 2 |
| jpeg / jpeg | 1 |
| md / markdown | 10 |
| pdf_rasterized / pdf-raster-only | 2 |
| pdf_text / pdf-text-layer | 4 |
| png / png | 1 |
| pptx / office-powerpoint | 1 |
| txt / code-source | 6 |
| txt / html | 1 |
| txt / jsonl | 4 |
| txt / log | 5 |
| txt / plain-text | 4 |
| txt / structured-csv | 2 |
| txt / structured-json | 2 |
| txt / structured-sql | 2 |
| txt / structured-xml | 1 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p18/home/` の 20 scope leaf

各 leaf は **1 つの KIO scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/quality/2021-2025/closed` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-020.jsonl` | txt / jsonl | ja | offline | filler |
| `review-summary-040.docx` | docx / office-word | ja | online_ocr | filler |

#### 2. `home/cloud/onedrive/quality-working` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-017.jsonl` | txt / jsonl | ja | offline | filler |
| `reference-brief-037.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 3. `home/cloud/sharepoint/quality/team` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-018.txt` | txt / plain-text | ja | offline | filler |
| `reference-brief-038.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 4. `home/desktop/current-capa` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-013.log` | txt / log | ja | offline | filler |
| `record-033.sql` | txt / structured-sql | en | offline | filler |

#### 5. `home/documents/quality/sop/reference` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | ja | offline | filler |
| `record-034.csv` | txt / structured-csv | ja | offline | filler |

#### 6. `home/downloads/exports/qms/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | ja | offline | filler |
| `message-036.html` | txt / html | ja | offline | filler |

#### 7. `home/downloads/inbox/supplier-certificates` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | ja | offline | filler |
| `record-035.json` | txt / structured-json | en | offline | filler |

#### 8. `home/engineering/quality/change-orders` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-012.txt` | txt / plain-text | ja | offline | filler |
| `record-032.xml` | txt / structured-xml | ja | offline | filler |

#### 9. `home/mail/outlook/capa/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-019.log` | txt / log | en | offline | filler |
| `reference-brief-039.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 10. `home/products/product-alpha/capa` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `trend-figure-043.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `utility-023.sh` | txt / code-source | en | offline | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 11. `home/products/product-alpha/fmea` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-021.txt` | txt / plain-text | en | offline | filler |
| `review-summary-041.docx` | docx / office-word | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

#### 12. `home/products/product-alpha/test-results` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-022.log` | txt / log | ja | offline | filler |
| `status-review-042.pptx` | pptx / office-powerpoint | ja | online_ocr | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 13. `home/products/product-beta/capa` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-026.ts` | txt / code-source | ja | offline | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 14. `home/products/product-beta/fmea` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-024.py` | txt / code-source | ja | offline | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

#### 15. `home/products/product-beta/test-results` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-025.rs` | txt / code-source | en | offline | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 16. `home/quality/nonconformance/2026/open` — 4 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `inspection-note.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **★正解** |
| `record-029.csv` | txt / structured-csv | en | offline | filler |
| `tolerance-review.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **△distractor** |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 17. `home/quality/sop` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-027.sh` | txt / code-source | en | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 18. `home/quality/work-instructions` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-028.sql` | txt / structured-sql | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 19. `home/suppliers/quality/audits` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-030.json` | txt / structured-json | ja | offline | filler |
| `worklog-010.md` | md / markdown | ja | offline | filler |

#### 20. `home/suppliers/quality/certificates` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-011.jsonl` | txt / jsonl | ja | offline | filler |
| `record-031.yaml` | txt / structured-yaml | en | offline | filler |

### `corpus/p18/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/plm-cache/product-alpha/changes/eco-0042/attachments/supplier-alpha/certificates/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p18.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p18.log` | txt / log | ja | offline |
| `budget-sheet-p18.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p18.png` | png / png | ja | online_ocr |
| `legacy-helper-p18.py` | txt / code-source | ja | offline |

### `qhard-a/p18/` — 3 件 (Q_hard 追加パック)

**B とは事実・ファイルを共有しません。** 別の fact/query 名前空間です。

パス: `qhard-a/p18/home/quality/nonconformance/2026/open/`

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `context-overview.md` | md / markdown | en | offline | filler |
| `defect-map.jpeg` | jpeg / jpeg | ja | online_ocr | **★正解** |
| `inspection-map.jpeg` | jpeg / jpeg | ja | online_ocr | **△distractor** |

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
| html | 直接記述 | 実務で自然な内容にする。 |
| jsonl | 直接記述 | 実務のイベント/レコードを 1 行 1 JSON で。 |
| log | 直接記述 | 実際のアプリ/システムログ形式 (タイムスタンプ + レベル + メッセージ)。 |
| plain-text | 直接記述 | 素のテキストメモ/転記/エクスポート。 |
| structured-csv | 直接記述 | 実務の CSV エクスポート (ヘッダ行 + 現実的な列)。 |
| structured-json | 直接記述 | 実務の設定/エクスポート JSON。 |
| structured-sql | 直接記述 | 実務の SQL (DDL/クエリ/マイグレーション)。 |
| structured-xml | 直接記述 | 実務の XML (設定/エクスポート/フィード)。 |
| structured-yaml | 直接記述 | 実務の設定 YAML (CI/インフラ/アプリ設定)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**KIO は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 75 / en 25` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **製造品質・検査** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p18 担当分)

### `qa08` — class **hard3**

- **クエリ**: 「C4 セルの不良率は何パーセントか」
- **正解ファイル**: `qhard-a/p18/home/quality/nonconformance/2026/open/defect-map.jpeg`
- **正解の所在**: section「Rendered defect map」
- **埋め込む事実 (この表現・値を必ず使う)**: Cell C4 has a defect rate of 2.7 percent.
- **section hint**: Rendered defect map
- **fact_id**: `f008` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qa08`: `qhard-a/p18/home/quality/nonconformance/2026/open/inspection-map.jpeg`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard3 不変条件 (レンダリングされた図表の事実)**

- 事実の値・軸・凡例・ラベルは **matplotlib/PIL/TeX→PNG でレンダリングした画像**にのみ描く。
- PPTX の場合はその画像を指定スライドに埋め込む。**スライドの編集可能テキスト・ノート・
  alt text・プロパティ・ChartML に事実を漏らさない** (alt text は一般的な語のみ)。
- 拡散生成画像を事実の担体にしない。

### `qb18` — class **hard1**

- **クエリ**: 「検査で許される寸法の振れ幅は何ミリか」
- **正解ファイル**: `corpus/p18/home/quality/nonconformance/2026/open/inspection-note.pdf`
- **正解の所在**: section「許容差節」
- **埋め込む事実 (この表現・値を必ず使う)**: 許容ばらつきは 0.36 mm。
- **section hint**: 許容差節
- **fact_id**: `f026` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb18`: `corpus/p18/home/quality/nonconformance/2026/open/tolerance-review.pdf`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard1 不変条件 (ラスタスキャン PDF)**

- TeX → PDF → `pdftoppm -r 200 -png` → `img2pdf` の順でビルドし、**テキスト層をゼロ**にする。
- 最終 PDF に `pdftotext` をかけ、Unicode 空白を除去した結果が **空** でなければ不合格。
- 事実は **ラスタ画像の画素**にのみ存在させる。

---

## 5. 既に定義済みのソース資産 (これを realism 版に差し替える)

骨格は以下に定義済みです。**構造・ページ数・埋込 fact は維持したまま、本文と図表を realistic に**
書き換えてください。

- `office-specs/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0912-review-summary-040.docx.md`
- `office-specs/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0913-review-summary-041.docx.md`
- `office-specs/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0914-status-review-042.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p18-0871.tex`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p18-0872.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p18-0868.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p18-0909.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p18-0910.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p18-0911.tex`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0866.log`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0867.py`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0873.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0874.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0875.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0876.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0877.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0878.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0879.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0880.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0881.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0882.md`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0883.jsonl`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0884.txt`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0885.log`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0886.jsonl`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0887.txt`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0888.log`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0889.jsonl`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0890.txt`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0891.log`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0892.jsonl`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0893.txt`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0894.log`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0895.sh`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0896.py`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0897.rs`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0898.ts`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0899.sh`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0900.sql`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0901.csv`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0902.json`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0903.yaml`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0904.xml`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0905.sql`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0906.csv`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0907.json`
- `sources/text/baseline-fixture-b-v1/p18/r-baseline-fixture-b-v1-p18-0908.html`
- `sources/text/qhard-a-v1/p18/r-qhard-a-v1-p18-1039.md`
- `sources/visual/specs/r-baseline-fixture-b-v1-p18-0869.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p18-0915.json`
- `sources/visual/specs/r-qhard-a-v1-p18-1037.json`
- `sources/visual/specs/r-qhard-a-v1-p18-1038.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p18-0870.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p18/` と `qhard-a/p18/` の中だけ**。他 persona 0 件。
- [ ] **`.kio` を 1 つも作っていない**。KIO の内部形式を一切書いていない。
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

生成物は **普通のファイルのみ**。この後、オペレータ側で実 KIO パイプラインが
`kio init` → `kio index --approve --online` を実行し、`.kio` 生成・Office→PDF 変換・
OCR (Mistral Batch)・CAS 保存・embedding (Gemini)・索引化を行います。
さらにその後、別セッションで **編集・追加・削除・フォルダ移動**を行い、実パイプラインで
履歴 (time-travel / `--all-history` / `--include-deleted`) を生成します。

