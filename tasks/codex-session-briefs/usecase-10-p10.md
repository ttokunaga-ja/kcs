# Codex セッション ブリーフ — ユースケース 10/20 : `p10` コンサルティング案件

> **このセッションで生成するのは `p10` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: consulting / client engagement / 言語比率: **en 100**

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
| 親フォルダ (B) | `corpus/p10/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 29 |
| embedding 見積り chunk (B) | 60 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 4 |
| jpeg / jpeg | 1 |
| md / markdown | 13 |
| pdf_rasterized / pdf-raster-only | 2 |
| pdf_text / pdf-text-layer | 4 |
| pptx / office-powerpoint | 5 |
| txt / code-source | 1 |
| txt / eml | 2 |
| txt / html | 2 |
| txt / jsonl | 3 |
| txt / log | 3 |
| txt / plain-text | 2 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| txt / structured-sql | 1 |
| txt / structured-xml | 2 |
| txt / structured-yaml | 2 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p10/home/` の 20 scope leaf

> **ファイル名の扱い** — この表の名前は 2 種類あります。
>
> - 役割が **`★正解` / `△正解` / `△distractor`** の行 … **名前を 1 文字も変えない**。
>   §4 の正解クエリ契約がこのパスを参照しています。
> - それ以外で **`-001` の連番** や **`-pNN` の接尾辞**を持つ名前 … **プレースホルダ**です。
>   骨格を機械生成したときの仮名なので、**世界観に合った実務的な名前へ必ず付け替えてください**
>   (`utility-021.rs` → `posting_link.rs` のように)。拡張子・件数・leaf は変えないこと。
> - 連番でも `-pNN` でもない名前 (`context-overview.md` 等) は既に自然なのでそのままで構いません。
>
> 付け替えの基準は共通プロンプトの **Step 1.5** を参照してください。

各 leaf は **1 つの Kio scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/closed-engagements/2021-2025` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-020.jsonl` | txt / jsonl | en | offline | filler |
| `status-review-040.pptx` | pptx / office-powerpoint | en | online_ocr | filler |

#### 2. `home/benchmarks/consumer-sector/2026/market-sizing` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-030.html` | txt / html | en | offline | filler |
| `worklog-010.md` | md / markdown | en | offline | filler |

#### 3. `home/cloud/personal/working-models` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-017.jsonl` | txt / jsonl | en | offline | filler |
| `review-summary-037.docx` | docx / office-word | en | online_ocr | filler |

#### 4. `home/cloud/team-shared/client-alpha-steerco` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-018.txt` | txt / plain-text | en | offline | filler |
| `review-summary-038.docx` | docx / office-word | en | online_ocr | filler |

#### 5. `home/desktop/active-engagement/storyline` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-033.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `worklog-013.md` | md / markdown | en | offline | filler |

#### 6. `home/documents/consulting/reference-library` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | en | offline | filler |
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 7. `home/downloads/exports/client-packages` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | en | offline | filler |
| `review-summary-036.docx` | docx / office-word | en | online_ocr | filler |

#### 8. `home/downloads/inbox/data-room` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | en | offline | filler |
| `review-summary-035.docx` | docx / office-word | en | online_ocr | filler |

#### 9. `home/engagements/client-alpha/2026/phase-1/workstream-finance/analysis` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-023.sql` | txt / structured-sql | en | offline | filler |
| `status-review-043.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `worklog-003.md` | md / markdown | en | offline | filler |

#### 10. `home/engagements/client-alpha/2026/phase-1/workstream-finance/data-room` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-021.yaml` | txt / structured-yaml | en | offline | filler |
| `status-review-041.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | en | offline | filler |

#### 11. `home/engagements/client-alpha/2026/phase-1/workstream-finance/deliverables` — 4 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `budget-options.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | **△distractor** |
| `record-024.csv` | txt / structured-csv | en | offline | filler |
| `steering-note.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | **★正解** |
| `worklog-004.md` | md / markdown | en | offline | filler |

#### 12. `home/engagements/client-alpha/2026/phase-1/workstream-finance/interviews` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-022.xml` | txt / structured-xml | en | offline | filler |
| `status-review-042.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `worklog-002.md` | md / markdown | en | offline | filler |

#### 13. `home/engagements/client-beta/2026/phase-2/workstream-operations/analysis` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-027.xml` | txt / structured-xml | en | offline | filler |
| `worklog-007.md` | md / markdown | en | offline | filler |

#### 14. `home/engagements/client-beta/2026/phase-2/workstream-operations/data-room` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-025.json` | txt / structured-json | en | offline | filler |
| `worklog-005.md` | md / markdown | en | offline | filler |

#### 15. `home/engagements/client-beta/2026/phase-2/workstream-operations/deliverables` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-028.html` | txt / html | en | offline | filler |
| `worklog-008.md` | md / markdown | en | offline | filler |

#### 16. `home/engagements/client-beta/2026/phase-2/workstream-operations/interviews` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-026.yaml` | txt / structured-yaml | en | offline | filler |
| `worklog-006.md` | md / markdown | en | offline | filler |

#### 17. `home/mail/client-steering/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-019.log` | txt / log | en | offline | filler |
| `status-review-039.pptx` | pptx / office-powerpoint | en | online_ocr | filler |

#### 18. `home/meetings/internal/reviews/2026` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-032.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `worklog-012.md` | md / markdown | en | offline | filler |

#### 19. `home/proposals/client-gamma/2026/active` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-029.eml` | txt / eml | en | offline | filler |
| `worklog-009.md` | md / markdown | en | offline | filler |

#### 20. `home/templates/consulting/financial-models/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-031.eml` | txt / eml | en | offline | filler |
| `worklog-011.md` | md / markdown | en | offline | filler |

### `corpus/p10/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/vdi-export/client-alpha/phase-1/workstream-finance/share/old/final/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p10.pdf` | pdf_text / pdf-text-layer | en | online_ocr |
| `archived-session-p10.log` | txt / log | en | offline |
| `budget-sheet-p10.xlsx` | xlsx_realism / xlsx-realism | en | unsupported |
| `field-photo-p10.jpeg` | jpeg / jpeg | en | online_ocr |
| `legacy-helper-p10.py` | txt / code-source | en | offline |

---

## 3. 形式別の生成方法と realism 要件

| subtype | 使うもの | realism 要件 |
|---|---|---|
| office-word | Word プラグイン | Word プラグインで実務文書 (見出し・表・ヘッダ/フッタ)。 |
| jpeg | 画像生成/レンダラ | 同上 (JPEG)。写真的な物は装飾のみ・文字を載せない。 |
| markdown | 直接記述 | 実務の Markdown ノート/議事録/ADR/ランブック。見出し・箇条書き・表を自然に使う。 |
| pdf-raster-only | TeX → ビルド | 実務で自然な内容にする。 |
| pdf-text-layer | TeX → ビルド | テキスト層のある PDF。TeX ソースを realistic な実務文書に書き換えてビルド。 |
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

- 本文は `en 100` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **コンサルティング案件** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p10 担当分)

### `qb10` — class **hard1**

- **クエリ**: 「調達に備えた予算の上限はいくらか」
- **正解ファイル**: `corpus/p10/home/engagements/client-alpha/2026/phase-1/workstream-finance/deliverables/steering-note.pdf`
- **正解の所在**: section「Finance decision」
- **埋め込む事実 (この表現・値を必ず使う)**: 調達予備費の上限は 318,000 USD。
- **section hint**: Finance decision
- **fact_id**: `f018` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb10`: `corpus/p10/home/engagements/client-alpha/2026/phase-1/workstream-finance/deliverables/budget-options.pdf`
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

- `office-specs/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0507-review-summary-035.docx.md`
- `office-specs/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0508-review-summary-036.docx.md`
- `office-specs/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0509-review-summary-037.docx.md`
- `office-specs/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0510-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0511-status-review-039.pptx.md`
- `office-specs/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0512-status-review-040.pptx.md`
- `office-specs/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0513-status-review-041.pptx.md`
- `office-specs/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0514-status-review-042.pptx.md`
- `office-specs/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0515-status-review-043.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p10-0471.tex`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p10-0472.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p10-0468.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p10-0504.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p10-0505.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p10-0506.tex`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0466.log`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0467.py`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0473.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0474.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0475.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0476.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0477.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0478.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0479.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0480.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0481.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0482.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0483.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0484.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0485.md`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0486.jsonl`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0487.txt`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0488.log`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0489.jsonl`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0490.txt`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0491.log`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0492.jsonl`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0493.yaml`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0494.xml`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0495.sql`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0496.csv`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0497.json`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0498.yaml`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0499.xml`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0500.html`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0501.eml`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0502.html`
- `sources/text/baseline-fixture-b-v1/p10/r-baseline-fixture-b-v1-p10-0503.eml`
- `sources/visual/specs/r-baseline-fixture-b-v1-p10-0469.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p10-0470.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] **プレースホルダ名 (`-001` 連番 / `-pNN`) が 1 つも残っていない。**
- [ ] **`★正解` / `△distractor` のファイル名を変えていない。**

- [ ] 生成したファイルは **`corpus/p10/` と `qhard-a/p10/` の中だけ**。他 persona 0 件。
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

