# Codex セッション ブリーフ — ユースケース 1/20 : `p01` 決済プロダクトのソフトウェア開発者

> **このセッションで生成するのは `p01` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: software engineering / payments workspace / 言語比率: **ja 70 / en 30**

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
| 親フォルダ (B) | `corpus/p01/` |
| 生成ファイル数 (B) | **54** |
| └ `home/` (索引対象・20 scope leaf) | 49 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| Q_hard 追加パック (A) `qhard-a/p01/` | 3 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 19 (+A 4) |
| embedding 見積り chunk (B) | 59 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 2 |
| jpeg / jpeg | 1 |
| md / markdown | 13 |
| pdf_text / pdf-text-layer | 4 |
| png / png | 2 |
| pptx / office-powerpoint | 2 |
| txt / code-source | 24 |
| txt / jsonl | 1 |
| txt / log | 1 |
| txt / notebook-json | 1 |
| txt / plain-text | 1 |
| txt / structured-csv | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p01/home/` の 20 scope leaf

各 leaf は **1 つの KIO scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/closed/releases` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `analysis-040.ipynb` | txt / notebook-json | ja | offline | filler |
| `utility-020.py` | txt / code-source | ja | offline | filler |

#### 2. `home/cloud/personal/scratch-notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-017.rs` | txt / code-source | ja | offline | filler |
| `utility-037.rs` | txt / code-source | en | offline | filler |

#### 3. `home/cloud/team/engineering-shared` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-018.ts` | txt / code-source | ja | offline | filler |
| `utility-038.ts` | txt / code-source | ja | offline | filler |

#### 4. `home/desktop/current-patch` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-033.rs` | txt / code-source | en | offline | filler |
| `worklog-013.md` | md / markdown | ja | offline | filler |

#### 5. `home/documents/reference/engineering` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | ja | offline | filler |
| `utility-034.ts` | txt / code-source | ja | offline | filler |

#### 6. `home/downloads/exports/build-reports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-016.py` | txt / code-source | ja | offline | filler |
| `utility-036.py` | txt / code-source | ja | offline | filler |

#### 7. `home/downloads/inbox/review-bundles` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | ja | offline | filler |
| `utility-035.sh` | txt / code-source | en | offline | filler |

#### 8. `home/mail/recent/engineering` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-039.csv` | txt / structured-csv | en | offline | filler |
| `utility-019.sh` | txt / code-source | ja | offline | filler |

#### 9. `home/meetings/engineering/notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-030.ts` | txt / code-source | ja | offline | filler |
| `worklog-010.md` | md / markdown | ja | offline | filler |

#### 10. `home/operations/migrations/notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-032.py` | txt / code-source | ja | offline | filler |
| `worklog-012.md` | md / markdown | ja | offline | filler |

#### 11. `home/repos/product-alpha/docs` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `trend-figure-046.png` | png / png | ja | online_ocr | filler |
| `utility-026.ts` | txt / code-source | ja | offline | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 12. `home/repos/product-beta/docs` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `trend-figure-047.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `utility-027.sh` | txt / code-source | en | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 13. `home/vendor-docs/platforms/reference` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-031.sh` | txt / code-source | en | offline | filler |
| `worklog-011.md` | md / markdown | ja | offline | filler |

#### 14. `home/work-items/code-reviews` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-029.rs` | txt / code-source | en | offline | filler |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 15. `home/work-items/decision-records` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-028.py` | txt / code-source | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 16. `home/work/products/product-alpha/api-contracts` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-042.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |
| `utility-022.ts` | txt / code-source | ja | offline | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 17. `home/work/products/product-alpha/architecture` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `capacity-options.docx` | docx / office-word | en | online_ocr | **△distractor** |
| `latency-review.docx` | docx / office-word | en | online_ocr | **★正解** |
| `reference-brief-041.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-021.rs` | txt / code-source | en | offline | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

#### 18. `home/work/products/product-alpha/release-notes` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-043.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-023.sh` | txt / code-source | en | offline | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 19. `home/work/products/product-beta/api-contracts` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-045.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `utility-025.rs` | txt / code-source | en | offline | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 20. `home/work/products/product-beta/architecture` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-044.pptx` | pptx / office-powerpoint | ja | online_ocr | filler |
| `utility-024.py` | txt / code-source | ja | offline | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

### `corpus/p01/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/scratch/product-alpha/feature-auth/rebase-03/conflicts/files/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p01.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p01.log` | txt / log | ja | offline |
| `budget-sheet-p01.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p01.png` | png / png | ja | online_ocr |
| `legacy-helper-p01.py` | txt / code-source | ja | offline |

### `qhard-a/p01/` — 3 件 (Q_hard 追加パック)

**B とは事実・ファイルを共有しません。** 別の fact/query 名前空間です。

パス: `qhard-a/p01/home/work/products/product-alpha/architecture/`

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `context-overview.md` | md / markdown | en | offline | filler |
| `latency-chart.pptx` | pptx / office-powerpoint | ja | online_ocr | **★正解** |
| `latency-comparison.pptx` | pptx / office-powerpoint | ja | online_ocr | **△distractor** |

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
| plain-text | 直接記述 | 素のテキストメモ/転記/エクスポート。 |
| structured-csv | 直接記述 | 実務の CSV エクスポート (ヘッダ行 + 現実的な列)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**KIO は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 70 / en 30` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **決済プロダクトのソフトウェア開発者** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p01 担当分)

### `qa05` — class **hard3**

- **クエリ**: 「同時接続千二百時の Ridge 系列の遅延は何ミリ秒か」
- **正解ファイル**: `qhard-a/p01/home/work/products/product-alpha/architecture/latency-chart.pptx`
- **正解の所在**: section「Rendered latency chart」
- **埋め込む事実 (この表現・値を必ず使う)**: Ridge series reaches 184 ms at 1,200 sessions.
- **section hint**: Rendered latency chart
- **fact_id**: `f005` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qa05`: `qhard-a/p01/home/work/products/product-alpha/architecture/latency-comparison.pptx`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard3 不変条件 (レンダリングされた図表の事実)**

- 事実の値・軸・凡例・ラベルは **matplotlib/PIL/TeX→PNG でレンダリングした画像**にのみ描く。
- PPTX の場合はその画像を指定スライドに埋め込む。**スライドの編集可能テキスト・ノート・
  alt text・プロパティ・ChartML に事実を漏らさない** (alt text は一般的な語のみ)。
- 拡散生成画像を事実の担体にしない。

### `qb01` — class **hard2**

- **クエリ**: 「一度に許される上限はどれほどだったか」
- **正解ファイル**: `corpus/p01/home/work/products/product-alpha/architecture/latency-review.docx`
- **正解の所在**: section「Decision record」
- **埋め込む事実 (この表現・値を必ず使う)**: The Orchid release caps concurrently retained credits at 47,200.
- **section hint**: Decision record
- **fact_id**: `f009` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb01`: `corpus/p01/home/work/products/product-alpha/architecture/capacity-options.docx`
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

- `office-specs/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0006-latency-review.docx.md`
- `office-specs/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0007-capacity-options.docx.md`
- `office-specs/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0051-status-review-044.pptx.md`
- `office-specs/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0052-status-review-045.pptx.md`
- `office-specs/qhard-a-v1/p01/r-qhard-a-v1-p01-1028-latency-chart.pptx.md`
- `office-specs/qhard-a-v1/p01/r-qhard-a-v1-p01-1029-latency-comparison.pptx.md`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p01-0003.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p01-0048.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p01-0049.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p01-0050.tex`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0001.log`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0002.py`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0008.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0009.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0010.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0011.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0012.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0013.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0014.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0015.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0016.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0017.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0018.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0019.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0020.md`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0021.jsonl`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0022.txt`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0023.py`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0024.rs`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0025.ts`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0026.sh`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0027.py`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0028.rs`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0029.ts`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0030.sh`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0031.py`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0032.rs`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0033.ts`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0034.sh`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0035.py`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0036.rs`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0037.ts`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0038.sh`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0039.py`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0040.rs`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0041.ts`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0042.sh`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0043.py`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0044.rs`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0045.ts`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0046.csv`
- `sources/text/baseline-fixture-b-v1/p01/r-baseline-fixture-b-v1-p01-0047.ipynb`
- `sources/text/qhard-a-v1/p01/r-qhard-a-v1-p01-1030.md`
- `sources/visual/specs/r-baseline-fixture-b-v1-p01-0004.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p01-0053.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p01-0054.json`
- `sources/visual/specs/r-qhard-a-v1-p01-1028-embedded.json`
- `sources/visual/specs/r-qhard-a-v1-p01-1029-embedded.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p01-0005.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p01/` と `qhard-a/p01/` の中だけ**。他 persona 0 件。
- [ ] **`.kio` を 1 つも作っていない**。KIO の内部形式を一切書いていない。
- [ ] OCR / Office→PDF 変換 / embedding / 索引化を **実行していない**。
- [ ] ファイル数が **B=54 (home 49 / ambient 5)** **A=3** と完全一致。
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

