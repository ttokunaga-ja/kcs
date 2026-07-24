# Codex セッション ブリーフ — ユースケース 9/20 : `p09` UX リサーチ・インタビュー

> **このセッションで生成するのは `p09` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: UX research / interview sessions / 言語比率: **en 75 / ja 25**

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
| 親フォルダ (B) | `corpus/p09/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 15 |
| embedding 見積り chunk (B) | 51 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 2 |
| jpeg / jpeg | 4 |
| md / markdown | 14 |
| pdf_text / pdf-text-layer | 2 |
| png / png | 1 |
| pptx / office-powerpoint | 2 |
| txt / code-source | 1 |
| txt / html | 1 |
| txt / jsonl | 5 |
| txt / log | 6 |
| txt / plain-text | 6 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| txt / structured-sql | 1 |
| txt / structured-xml | 1 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p09/home/` の 20 scope leaf

各 leaf は **1 つの Kio scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/closed-studies/2023-2025` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-020.jsonl` | txt / jsonl | ja | offline | filler |
| `trend-figure-040.jpeg` | jpeg / jpeg | ja | online_ocr | filler |

#### 2. `home/cloud/personal/field-notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-017.jsonl` | txt / jsonl | en | offline | filler |
| `reference-brief-037.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 3. `home/cloud/team-shared/research-repository` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-018.txt` | txt / plain-text | en | offline | filler |
| `review-summary-038.docx` | docx / office-word | ja | online_ocr | filler |

#### 4. `home/consent/study-alpha/synthetic-records/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-032.xml` | txt / structured-xml | ja | offline | filler |
| `worklog-012.md` | md / markdown | en | offline | filler |

#### 5. `home/design/product-alpha/figma-exports/weekly` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-029.jsonl` | txt / jsonl | en | offline | filler |
| `worklog-009.md` | md / markdown | en | offline | filler |

#### 6. `home/design/product-alpha/prototype-specs/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-028.log` | txt / log | ja | offline | filler |
| `worklog-008.md` | md / markdown | en | offline | filler |

#### 7. `home/desktop/active-study/session-plans` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-033.sql` | txt / structured-sql | en | offline | filler |
| `worklog-013.md` | md / markdown | en | offline | filler |

#### 8. `home/documents/ux/reference-library` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-034.csv` | txt / structured-csv | ja | offline | filler |
| `worklog-014.md` | md / markdown | en | offline | filler |

#### 9. `home/downloads/exports/research-reports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | en | offline | filler |
| `message-036.html` | txt / html | ja | offline | filler |

#### 10. `home/downloads/inbox/recorder-imports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | en | offline | filler |
| `record-035.json` | txt / structured-json | en | offline | filler |

#### 11. `home/mail/participant-coordination/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-019.log` | txt / log | en | offline | filler |
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |

#### 12. `home/personas/product-alpha/journey-maps/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-030.txt` | txt / plain-text | ja | offline | filler |
| `worklog-010.md` | md / markdown | en | offline | filler |

#### 13. `home/recordings/study-alpha/transcript-sidecars/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-031.yaml` | txt / structured-yaml | en | offline | filler |
| `worklog-011.md` | md / markdown | en | offline | filler |

#### 14. `home/research/study-alpha/2026/findings` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-023.jsonl` | txt / jsonl | en | offline | filler |
| `trend-figure-043.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `worklog-003.md` | md / markdown | en | offline | filler |

#### 15. `home/research/study-alpha/2026/plans` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-021.txt` | txt / plain-text | en | offline | filler |
| `trend-figure-041.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | en | offline | filler |

#### 16. `home/research/study-alpha/2026/transcripts` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-022.log` | txt / log | ja | offline | filler |
| `interview-patterns.pptx` | pptx / office-powerpoint | en | online_ocr | **★正解** |
| `theme-distribution.pptx` | pptx / office-powerpoint | en | online_ocr | **△distractor** |
| `trend-figure-042.jpeg` | jpeg / jpeg | ja | online_ocr | filler |
| `worklog-002.md` | md / markdown | en | offline | filler |

#### 17. `home/research/study-beta/2026/findings` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-026.jsonl` | txt / jsonl | ja | offline | filler |
| `worklog-006.md` | md / markdown | en | offline | filler |

#### 18. `home/research/study-beta/2026/plans` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-024.txt` | txt / plain-text | ja | offline | filler |
| `worklog-004.md` | md / markdown | en | offline | filler |

#### 19. `home/research/study-beta/2026/transcripts` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-025.log` | txt / log | en | offline | filler |
| `worklog-005.md` | md / markdown | en | offline | filler |

#### 20. `home/surveys/product-alpha/results/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-027.txt` | txt / plain-text | en | offline | filler |
| `worklog-007.md` | md / markdown | en | offline | filler |

### `corpus/p09/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/recorder-staging/study-alpha/session-017/audio/raw/channels/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p09.pdf` | pdf_text / pdf-text-layer | en | online_ocr |
| `archived-session-p09.log` | txt / log | en | offline |
| `budget-sheet-p09.xlsx` | xlsx_realism / xlsx-realism | en | unsupported |
| `field-photo-p09.png` | png / png | en | online_ocr |
| `legacy-helper-p09.py` | txt / code-source | en | offline |

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
| html | 直接記述 | 実務で自然な内容にする。 |
| jsonl | 直接記述 | 実務のイベント/レコードを 1 行 1 JSON で。 |
| log | 直接記述 | 実際のアプリ/システムログ形式 (タイムスタンプ + レベル + メッセージ)。 |
| plain-text | 直接記述 | 素のテキストメモ/転記/エクスポート。 |
| structured-csv | 直接記述 | 実務の CSV エクスポート (ヘッダ行 + 現実的な列)。 |
| structured-json | 直接記述 | 実務の設定/エクスポート JSON。 |
| structured-sql | 直接記述 | 実務の SQL (DDL/クエリ/マイグレーション)。 |
| structured-xml | 直接記述 | 実務の XML (設定/エクスポート/フィード)。 |
| structured-yaml | 直接記述 | 実務の設定 YAML (CI/インフラ/アプリ設定)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**Kio は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `en 75 / ja 25` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **UX リサーチ・インタビュー** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p09 担当分)

### `qb09` — class **hard3**

- **クエリ**: 「信頼に関する発話はいくつ抽出されたか」
- **正解ファイル**: `corpus/p09/home/research/study-alpha/2026/transcripts/interview-patterns.pptx`
- **正解の所在**: section「Rendered theme chart」
- **埋め込む事実 (この表現・値を必ず使う)**: The trust theme appears in 28 of 64 interview excerpts.
- **section hint**: Rendered theme chart
- **fact_id**: `f017` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb09`: `corpus/p09/home/research/study-alpha/2026/transcripts/theme-distribution.pptx`
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

- `office-specs/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0421-interview-patterns.pptx.md`
- `office-specs/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0422-theme-distribution.pptx.md`
- `office-specs/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0460-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0461-review-summary-039.docx.md`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p09-0418.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p09-0459.tex`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0416.log`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0417.py`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0423.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0424.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0425.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0426.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0427.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0428.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0429.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0430.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0431.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0432.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0433.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0434.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0435.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0436.md`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0437.txt`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0438.log`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0439.jsonl`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0440.txt`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0441.log`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0442.jsonl`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0443.txt`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0444.log`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0445.jsonl`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0446.txt`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0447.log`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0448.jsonl`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0449.txt`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0450.log`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0451.jsonl`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0452.txt`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0453.yaml`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0454.xml`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0455.sql`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0456.csv`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0457.json`
- `sources/text/baseline-fixture-b-v1/p09/r-baseline-fixture-b-v1-p09-0458.html`
- `sources/visual/specs/r-baseline-fixture-b-v1-p09-0419.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p09-0421-embedded.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p09-0422-embedded.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p09-0462.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p09-0463.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p09-0464.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p09-0465.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p09-0420.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p09/` と `qhard-a/p09/` の中だけ**。他 persona 0 件。
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

