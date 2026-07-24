# Codex セッション ブリーフ — ユースケース 8/20 : `p08` プロダクトマネジメント・ロードマップ

> **このセッションで生成するのは `p08` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: product management / roadmap / 言語比率: **ja 70 / en 30**

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
| 親フォルダ (B) | `corpus/p08/` |
| 生成ファイル数 (B) | **54** |
| └ `home/` (索引対象・20 scope leaf) | 49 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 28 |
| embedding 見積り chunk (B) | 63 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 4 |
| jpeg / jpeg | 2 |
| md / markdown | 23 |
| pdf_rasterized / pdf-raster-only | 1 |
| pdf_text / pdf-text-layer | 4 |
| png / png | 1 |
| pptx / office-powerpoint | 4 |
| txt / code-source | 3 |
| txt / eml | 1 |
| txt / html | 1 |
| txt / jsonl | 1 |
| txt / log | 2 |
| txt / plain-text | 1 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| txt / structured-sql | 1 |
| txt / structured-xml | 1 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p08/home/` の 20 scope leaf

各 leaf は **1 つの Kio scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/analytics/product-alpha/product-metrics/weekly` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-030.json` | txt / structured-json | ja | offline | filler |
| `worklog-010.md` | md / markdown | ja | offline | filler |

#### 2. `home/archive/closed-launches/2024-2025` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-040.docx` | docx / office-word | ja | online_ocr | filler |
| `worklog-020.md` | md / markdown | ja | offline | filler |

#### 3. `home/cloud/personal/product-notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-037.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `worklog-017.md` | md / markdown | ja | offline | filler |

#### 4. `home/cloud/team-shared/product-council` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-038.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |
| `worklog-018.md` | md / markdown | ja | offline | filler |

#### 5. `home/customer-feedback/product-alpha/interviews/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-028.py` | txt / code-source | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 6. `home/customer-feedback/product-alpha/support-summaries/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-029.csv` | txt / structured-csv | en | offline | filler |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 7. `home/decisions/product-council/meeting-notes/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-031.yaml` | txt / structured-yaml | en | offline | filler |
| `worklog-011.md` | md / markdown | ja | offline | filler |

#### 8. `home/desktop/active-prd/review` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-033.sql` | txt / structured-sql | en | offline | filler |
| `worklog-013.md` | md / markdown | ja | offline | filler |

#### 9. `home/documents/product/reference-library` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-034.html` | txt / html | ja | offline | filler |
| `worklog-014.md` | md / markdown | ja | offline | filler |

#### 10. `home/downloads/exports/roadmap-packages` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |
| `worklog-016.md` | md / markdown | ja | offline | filler |

#### 11. `home/downloads/inbox/customer-exports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-035.eml` | txt / eml | en | offline | filler |
| `worklog-015.md` | md / markdown | ja | offline | filler |

#### 12. `home/mail/stakeholder-updates/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `archived-note-039.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | filler |
| `worklog-019.md` | md / markdown | ja | offline | filler |

#### 13. `home/portfolio/product-alpha/2026/q3/discovery` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-042.pptx` | pptx / office-powerpoint | ja | online_ocr | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |
| `worklog-022.md` | md / markdown | ja | offline | filler |

#### 14. `home/portfolio/product-alpha/2026/q3/launch-readiness` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-043.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |
| `worklog-023.md` | md / markdown | en | offline | filler |

#### 15. `home/portfolio/product-alpha/2026/q3/prds` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-041.docx` | docx / office-word | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |
| `worklog-021.md` | md / markdown | en | offline | filler |

#### 16. `home/portfolio/product-beta/2026/q4/discovery` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-025.log` | txt / log | en | offline | filler |
| `status-review-045.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 17. `home/portfolio/product-beta/2026/q4/prds` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-024.txt` | txt / plain-text | ja | offline | filler |
| `status-review-044.pptx` | pptx / office-powerpoint | ja | online_ocr | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

#### 18. `home/research/markets/search-platform/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-032.xml` | txt / structured-xml | ja | offline | filler |
| `worklog-012.md` | md / markdown | ja | offline | filler |

#### 19. `home/roadmap/fy2026/q3/dependencies` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `trend-figure-047.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `utility-027.sh` | txt / code-source | en | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 20. `home/roadmap/fy2026/q3/quarterly` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-026.jsonl` | txt / jsonl | ja | offline | filler |
| `quarter-plan.docx` | docx / office-word | en | online_ocr | **△distractor** |
| `scope-tradeoff.docx` | docx / office-word | en | online_ocr | **★正解** |
| `trend-figure-046.jpeg` | jpeg / jpeg | ja | online_ocr | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

### `corpus/p08/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/meeting-imports/teams/product-alpha/2026/q3/chat/attachments/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p08.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p08.log` | txt / log | ja | offline |
| `budget-sheet-p08.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p08.png` | png / png | ja | online_ocr |
| `legacy-helper-p08.py` | txt / code-source | ja | offline |

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
| structured-json | 直接記述 | 実務の設定/エクスポート JSON。 |
| structured-sql | 直接記述 | 実務の SQL (DDL/クエリ/マイグレーション)。 |
| structured-xml | 直接記述 | 実務の XML (設定/エクスポート/フィード)。 |
| structured-yaml | 直接記述 | 実務の設定 YAML (CI/インフラ/アプリ設定)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**Kio は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 70 / en 30` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **プロダクトマネジメント・ロードマップ** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p08 担当分)

### `qb08` — class **hard2**

- **クエリ**: 「次の四半期に取りかかる対象はいつ始まるか」
- **正解ファイル**: `corpus/p08/home/roadmap/fy2026/q3/quarterly/scope-tradeoff.docx`
- **正解の所在**: section「Roadmap commitment」
- **埋め込む事実 (この表現・値を必ず使う)**: The Harbor roadmap schedules the Cedar workstream to begin on 2026-11-04.
- **section hint**: Roadmap commitment
- **fact_id**: `f016` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb08`: `corpus/p08/home/roadmap/fy2026/q3/quarterly/quarter-plan.docx`
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

- `office-specs/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0367-scope-tradeoff.docx.md`
- `office-specs/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0368-quarter-plan.docx.md`
- `office-specs/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0408-review-summary-040.docx.md`
- `office-specs/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0409-review-summary-041.docx.md`
- `office-specs/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0410-status-review-042.pptx.md`
- `office-specs/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0411-status-review-043.pptx.md`
- `office-specs/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0412-status-review-044.pptx.md`
- `office-specs/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0413-status-review-045.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p08-0407.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p08-0364.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p08-0404.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p08-0405.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p08-0406.tex`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0362.log`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0363.py`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0369.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0370.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0371.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0372.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0373.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0374.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0375.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0376.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0377.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0378.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0379.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0380.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0381.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0382.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0383.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0384.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0385.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0386.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0387.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0388.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0389.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0390.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0391.md`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0392.txt`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0393.log`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0394.jsonl`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0395.sh`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0396.py`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0397.csv`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0398.json`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0399.yaml`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0400.xml`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0401.sql`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0402.html`
- `sources/text/baseline-fixture-b-v1/p08/r-baseline-fixture-b-v1-p08-0403.eml`
- `sources/visual/specs/r-baseline-fixture-b-v1-p08-0365.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p08-0414.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p08-0415.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p08-0366.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p08/` と `qhard-a/p08/` の中だけ**。他 persona 0 件。
- [ ] **`.kio` を 1 つも作っていない**。Kio の内部形式を一切書いていない。
- [ ] OCR / Office→PDF 変換 / embedding / 索引化を **実行していない**。
- [ ] ファイル数が **B=54 (home 49 / ambient 5)** と完全一致。
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

