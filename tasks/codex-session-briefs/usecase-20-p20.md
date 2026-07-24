# Codex セッション ブリーフ — ユースケース 20/20 : `p20` 調査報道・証拠管理

> **このセッションで生成するのは `p20` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: investigative journalism / evidence chain / 言語比率: **ja 70 / en 30**

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
| 親フォルダ (B) | `corpus/p20/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 34 |
| embedding 見積り chunk (B) | 65 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 3 |
| jpeg / jpeg | 4 |
| md / markdown | 10 |
| pdf_rasterized / pdf-raster-only | 2 |
| pdf_text / pdf-text-layer | 5 |
| png / png | 1 |
| pptx / office-powerpoint | 1 |
| txt / code-source | 3 |
| txt / eml | 1 |
| txt / html | 1 |
| txt / jsonl | 5 |
| txt / log | 5 |
| txt / plain-text | 5 |
| txt / structured-csv | 1 |
| txt / structured-sql | 1 |
| txt / structured-xml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p20/home/` の 20 scope leaf

各 leaf は **1 つの Kio scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/newsroom/investigations/2021-2025` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-020.jsonl` | txt / jsonl | ja | offline | filler |
| `trend-figure-040.jpeg` | jpeg / jpeg | ja | online_ocr | filler |

#### 2. `home/cloud/drive/newsroom/story-alpha` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-017.jsonl` | txt / jsonl | en | offline | filler |
| `review-summary-037.docx` | docx / office-word | en | online_ocr | filler |

#### 3. `home/cloud/sharepoint/newsroom/investigations/team` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-018.txt` | txt / plain-text | ja | offline | filler |
| `review-summary-038.docx` | docx / office-word | ja | online_ocr | filler |

#### 4. `home/data/investigations/analysis` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-030.html` | txt / html | ja | offline | filler |
| `worklog-010.md` | md / markdown | ja | offline | filler |

#### 5. `home/desktop/newsroom/story-alpha/active` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-013.log` | txt / log | en | offline | filler |
| `reference-brief-033.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 6. `home/documents/journalism/source-protection/reference` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | ja | offline | filler |
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 7. `home/downloads/foia-exports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | ja | offline | filler |
| `review-summary-036.docx` | docx / office-word | ja | online_ocr | filler |

#### 8. `home/downloads/inbox/source-drops` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | en | offline | filler |
| `reference-brief-035.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 9. `home/mail/outlook/story-alpha/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-019.log` | txt / log | en | offline | filler |
| `status-review-039.pptx` | pptx / office-powerpoint | en | online_ocr | filler |

#### 10. `home/media/investigations/transcript-sidecars` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-011.jsonl` | txt / jsonl | ja | offline | filler |
| `message-031.eml` | txt / eml | en | offline | filler |

#### 11. `home/newsroom/investigations/story-alpha/2026/drafts` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-024.txt` | txt / plain-text | ja | offline | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

#### 12. `home/newsroom/investigations/story-alpha/2026/fact-check` — 6 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `evidence-sequence.jpeg` | jpeg / jpeg | ja | online_ocr | **△distractor** |
| `source-memo.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **★正解** |
| `source-timeline.jpeg` | jpeg / jpeg | ja | online_ocr | **★正解** |
| `utility-025.rs` | txt / code-source | en | offline | filler |
| `verification-log.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **△distractor** |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 13. `home/newsroom/investigations/story-alpha/2026/foia` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-023.jsonl` | txt / jsonl | en | offline | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 14. `home/newsroom/investigations/story-alpha/2026/sources` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-021.txt` | txt / plain-text | en | offline | filler |
| `trend-figure-041.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

#### 15. `home/newsroom/investigations/story-alpha/2026/transcripts` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-022.log` | txt / log | ja | offline | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 16. `home/newsroom/investigations/story-beta/2026/drafts` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-029.csv` | txt / structured-csv | en | offline | filler |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 17. `home/newsroom/investigations/story-beta/2026/foia` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-028.sql` | txt / structured-sql | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 18. `home/newsroom/investigations/story-beta/2026/sources` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-026.ts` | txt / code-source | ja | offline | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 19. `home/newsroom/investigations/story-beta/2026/transcripts` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-027.xml` | txt / structured-xml | en | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 20. `home/pitches/investigations/research` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-012.txt` | txt / plain-text | ja | offline | filler |
| `reference-brief-032.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

### `corpus/p20/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/source-drop/story-alpha/source-syn-017/device-export/messages/attachments/2026-07/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p20.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p20.log` | txt / log | ja | offline |
| `budget-sheet-p20.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p20.png` | png / png | ja | online_ocr |
| `legacy-helper-p20.py` | txt / code-source | ja | offline |

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
| plain-text | 直接記述 | 素のテキストメモ/転記/エクスポート。 |
| structured-csv | 直接記述 | 実務の CSV エクスポート (ヘッダ行 + 現実的な列)。 |
| structured-sql | 直接記述 | 実務の SQL (DDL/クエリ/マイグレーション)。 |
| structured-xml | 直接記述 | 実務の XML (設定/エクスポート/フィード)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**Kio は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 70 / en 30` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **調査報道・証拠管理** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p20 担当分)

### `qb20` — class **hard1**

- **クエリ**: 「取材先へ確認できる締めの時刻はいつか」
- **正解ファイル**: `corpus/p20/home/newsroom/investigations/story-alpha/2026/fact-check/source-memo.pdf`
- **正解の所在**: section「確認節」
- **埋め込む事実 (この表現・値を必ず使う)**: 記者確認の最終時刻は 18:40 JST。
- **section hint**: 確認節
- **fact_id**: `f028` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb20`: `corpus/p20/home/newsroom/investigations/story-alpha/2026/fact-check/verification-log.pdf`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard1 不変条件 (ラスタスキャン PDF)**

- TeX → PDF → `pdftoppm -r 200 -png` → `img2pdf` の順でビルドし、**テキスト層をゼロ**にする。
- 最終 PDF に `pdftotext` をかけ、Unicode 空白を除去した結果が **空** でなければ不合格。
- 事実は **ラスタ画像の画素**にのみ存在させる。

### `qb24` — class **hard3**

- **クエリ**: 「Delta 印の時刻はいつか」
- **正解ファイル**: `corpus/p20/home/newsroom/investigations/story-alpha/2026/fact-check/source-timeline.jpeg`
- **正解の所在**: section「Rendered timeline」
- **埋め込む事実 (この表現・値を必ず使う)**: Marker Delta is placed at 14:25 JST on the source timeline.
- **section hint**: Rendered timeline
- **fact_id**: `f032` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb24`: `corpus/p20/home/newsroom/investigations/story-alpha/2026/fact-check/evidence-sequence.jpeg`
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

- `office-specs/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1010-review-summary-036.docx.md`
- `office-specs/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1011-review-summary-037.docx.md`
- `office-specs/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1012-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1013-status-review-039.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p20-0971.tex`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p20-0972.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p20-0968.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p20-1006.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p20-1007.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p20-1008.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p20-1009.tex`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0966.log`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0967.py`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0975.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0976.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0977.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0978.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0979.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0980.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0981.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0982.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0983.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0984.md`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0985.jsonl`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0986.txt`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0987.log`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0988.jsonl`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0989.txt`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0990.log`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0991.jsonl`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0992.txt`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0993.log`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0994.jsonl`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0995.txt`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0996.log`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0997.jsonl`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0998.txt`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-0999.rs`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1000.ts`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1001.xml`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1002.sql`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1003.csv`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1004.html`
- `sources/text/baseline-fixture-b-v1/p20/r-baseline-fixture-b-v1-p20-1005.eml`
- `sources/visual/specs/r-baseline-fixture-b-v1-p20-0969.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p20-0973.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p20-0974.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p20-1014.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p20-1015.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p20-0970.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p20/` と `qhard-a/p20/` の中だけ**。他 persona 0 件。
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

