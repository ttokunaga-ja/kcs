# Codex セッション ブリーフ — ユースケース 14/20 : `p14` 経理・月次締め

> **このセッションで生成するのは `p14` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: finance / close review / 言語比率: **ja 80 / en 20**

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
| 親フォルダ (B) | `corpus/p14/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 33 |
| embedding 見積り chunk (B) | 64 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 4 |
| jpeg / jpeg | 1 |
| md / markdown | 8 |
| pdf_rasterized / pdf-raster-only | 2 |
| pdf_text / pdf-text-layer | 5 |
| png / png | 1 |
| pptx / office-powerpoint | 3 |
| txt / code-source | 5 |
| txt / eml | 1 |
| txt / html | 1 |
| txt / jsonl | 1 |
| txt / log | 2 |
| txt / notebook-json | 1 |
| txt / plain-text | 2 |
| txt / structured-csv | 2 |
| txt / structured-json | 2 |
| txt / structured-sql | 3 |
| txt / structured-xml | 3 |
| txt / structured-yaml | 2 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p14/home/` の 20 scope leaf

各 leaf は **1 つの Kio scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/finance/close/2021-2025` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-020.json` | txt / structured-json | ja | offline | filler |
| `review-summary-040.docx` | docx / office-word | ja | online_ocr | filler |

#### 2. `home/cloud/onedrive/finance-working` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `archived-note-037.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | filler |
| `record-017.xml` | txt / structured-xml | ja | offline | filler |

#### 3. `home/cloud/sharepoint/finance/close/2026-q1` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-018.sql` | txt / structured-sql | ja | offline | filler |
| `review-summary-038.docx` | docx / office-word | ja | online_ocr | filler |

#### 4. `home/desktop/current-close` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-033.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-013.rs` | txt / code-source | ja | offline | filler |

#### 5. `home/documents/finance/policies/reference` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |
| `utility-014.ts` | txt / code-source | ja | offline | filler |

#### 6. `home/downloads/exports/erp/2026-q1` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `archived-note-036.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | filler |
| `utility-016.py` | txt / code-source | ja | offline | filler |

#### 7. `home/downloads/inbox/bank-statements` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-035.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-015.sh` | txt / code-source | ja | offline | filler |

#### 8. `home/finance/audit/evidence/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-009.txt` | txt / plain-text | ja | offline | filler |
| `message-029.eml` | txt / eml | en | offline | filler |

#### 9. `home/finance/board/packs/2026-q1` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-010.log` | txt / log | ja | offline | filler |
| `message-030.html` | txt / html | ja | offline | filler |

#### 10. `home/finance/budget/2026/annual` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-024.csv` | txt / structured-csv | ja | offline | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

#### 11. `home/finance/close/2026/q1/2026-01` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-021.yaml` | txt / structured-yaml | ja | offline | filler |
| `review-summary-041.docx` | docx / office-word | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

#### 12. `home/finance/close/2026/q1/2026-02` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-022.xml` | txt / structured-xml | ja | offline | filler |
| `status-review-042.pptx` | pptx / office-powerpoint | ja | online_ocr | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 13. `home/finance/close/2026/q1/2026-03` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `cash-bridge.pptx` | pptx / office-powerpoint | ja | online_ocr | **★正解** |
| `closing-bridge.pptx` | pptx / office-powerpoint | ja | online_ocr | **△distractor** |
| `record-023.sql` | txt / structured-sql | ja | offline | filler |
| `trend-figure-043.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 14. `home/finance/erp/exports/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-012.txt` | txt / plain-text | ja | offline | filler |
| `reference-brief-032.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 15. `home/finance/expenses/department/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-028.sql` | txt / structured-sql | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 16. `home/finance/forecasts/2026/base-case` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-025.json` | txt / structured-json | en | offline | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 17. `home/finance/forecasts/2026/scenarios` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-026.yaml` | txt / structured-yaml | ja | offline | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 18. `home/finance/invoices/vendor/open` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-027.xml` | txt / structured-xml | en | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 19. `home/finance/models/operating/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-011.jsonl` | txt / jsonl | ja | offline | filler |
| `analysis-031.ipynb` | txt / notebook-json | en | offline | filler |

#### 20. `home/mail/outlook/close-team/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-019.csv` | txt / structured-csv | ja | offline | filler |
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |

### `corpus/p14/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/onedrive-sync/finance/close/fy2026/q1/2026-03/review/final/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p14.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p14.log` | txt / log | ja | offline |
| `budget-sheet-p14.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p14.png` | png / png | ja | online_ocr |
| `legacy-helper-p14.py` | txt / code-source | ja | offline |

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
| structured-yaml | 直接記述 | 実務の設定 YAML (CI/インフラ/アプリ設定)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**Kio は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 80 / en 20` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **経理・月次締め** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p14 担当分)

### `qb14` — class **hard3**

- **クエリ**: 「三月の営業キャッシュはいくらか」
- **正解ファイル**: `corpus/p14/home/finance/close/2026/q1/2026-03/cash-bridge.pptx`
- **正解の所在**: section「Rendered cash bridge」
- **埋め込む事実 (この表現・値を必ず使う)**: March operating cash is 6.8 million JPY in the bridge chart.
- **section hint**: Rendered cash bridge
- **fact_id**: `f022` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb14`: `corpus/p14/home/finance/close/2026/q1/2026-03/closing-bridge.pptx`
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

- `office-specs/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0671-cash-bridge.pptx.md`
- `office-specs/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0672-closing-bridge.pptx.md`
- `office-specs/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0710-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0711-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0712-review-summary-040.docx.md`
- `office-specs/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0713-review-summary-041.docx.md`
- `office-specs/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0714-status-review-042.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p14-0708.tex`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p14-0709.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p14-0668.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p14-0704.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p14-0705.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p14-0706.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p14-0707.tex`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0666.log`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0667.py`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0673.md`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0674.md`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0675.md`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0676.md`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0677.md`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0678.md`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0679.md`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0680.md`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0681.txt`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0682.log`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0683.jsonl`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0684.txt`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0685.rs`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0686.ts`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0687.sh`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0688.py`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0689.xml`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0690.sql`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0691.csv`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0692.json`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0693.yaml`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0694.xml`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0695.sql`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0696.csv`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0697.json`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0698.yaml`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0699.xml`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0700.sql`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0701.eml`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0702.html`
- `sources/text/baseline-fixture-b-v1/p14/r-baseline-fixture-b-v1-p14-0703.ipynb`
- `sources/visual/specs/r-baseline-fixture-b-v1-p14-0669.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p14-0671-embedded.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p14-0672-embedded.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p14-0715.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p14-0670.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p14/` と `qhard-a/p14/` の中だけ**。他 persona 0 件。
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

