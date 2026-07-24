# Codex セッション ブリーフ — ユースケース 2/20 : `p02` SRE・障害対応

> **このセッションで生成するのは `p02` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: SRE / service operations / 言語比率: **en 100**

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
| 親フォルダ (B) | `corpus/p02/` |
| 生成ファイル数 (B) | **53** |
| └ `home/` (索引対象・20 scope leaf) | 48 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| Q_hard 追加パック (A) `qhard-a/p02/` | 3 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 17 (+A 3) |
| embedding 見積り chunk (B) | 57 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 2 |
| jpeg / jpeg | 1 |
| md / markdown | 13 |
| pdf_text / pdf-text-layer | 4 |
| png / png | 2 |
| pptx / office-powerpoint | 1 |
| txt / code-source | 16 |
| txt / jsonl | 2 |
| txt / log | 4 |
| txt / plain-text | 3 |
| txt / structured-json | 1 |
| txt / structured-sql | 1 |
| txt / structured-xml | 1 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p02/home/` の 20 scope leaf

各 leaf は **1 つの KIO scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/closed/incidents` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-040.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-020.py` | txt / code-source | en | offline | filler |

#### 2. `home/capacity/planning/reports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-031.sh` | txt / code-source | en | offline | filler |
| `worklog-011.md` | md / markdown | en | offline | filler |

#### 3. `home/changes/deployments/production` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-030.ts` | txt / code-source | en | offline | filler |
| `worklog-010.md` | md / markdown | en | offline | filler |

#### 4. `home/cloud/personal/oncall-notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-017.jsonl` | txt / jsonl | en | offline | filler |
| `record-037.xml` | txt / structured-xml | en | offline | filler |

#### 5. `home/cloud/team/reliability-shared` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-018.txt` | txt / plain-text | en | offline | filler |
| `record-038.sql` | txt / structured-sql | en | offline | filler |

#### 6. `home/desktop/active-incident` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-013.log` | txt / log | en | offline | filler |
| `utility-033.rs` | txt / code-source | en | offline | filler |

#### 7. `home/documents/operations/postmortems` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-042.docx` | docx / office-word | en | online_ocr | filler |
| `utility-022.ts` | txt / code-source | en | offline | filler |
| `worklog-002.md` | md / markdown | en | offline | filler |

#### 8. `home/documents/operations/runbooks` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-041.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-021.rs` | txt / code-source | en | offline | filler |
| `worklog-001.md` | md / markdown | en | offline | filler |

#### 9. `home/documents/reference/platform-standards` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | en | offline | filler |
| `utility-034.ts` | txt / code-source | en | offline | filler |

#### 10. `home/downloads/exports/log-batches` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | en | offline | filler |
| `record-036.yaml` | txt / structured-yaml | en | offline | filler |

#### 11. `home/downloads/inbox/diagnostic-bundles` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | en | offline | filler |
| `record-035.json` | txt / structured-json | en | offline | filler |

#### 12. `home/infrastructure/kubernetes/clusters` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-043.docx` | docx / office-word | en | online_ocr | filler |
| `utility-023.sh` | txt / code-source | en | offline | filler |
| `worklog-003.md` | md / markdown | en | offline | filler |

#### 13. `home/infrastructure/terraform/environments` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-044.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `utility-024.py` | txt / code-source | en | offline | filler |
| `worklog-004.md` | md / markdown | en | offline | filler |

#### 14. `home/mail/recent/incident-threads` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-019.log` | txt / log | en | offline | filler |
| `reference-brief-039.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 15. `home/meetings/operations/reviews` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-012.txt` | txt / plain-text | en | offline | filler |
| `utility-032.py` | txt / code-source | en | offline | filler |

#### 16. `home/observability/alerts/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-027.sh` | txt / code-source | en | offline | filler |
| `worklog-007.md` | md / markdown | en | offline | filler |

#### 17. `home/observability/dashboards/production` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-028.py` | txt / code-source | en | offline | filler |
| `worklog-008.md` | md / markdown | en | offline | filler |

#### 18. `home/observability/log-exports/service` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-029.rs` | txt / code-source | en | offline | filler |
| `worklog-009.md` | md / markdown | en | offline | filler |

#### 19. `home/services/checkout/prod/oncall/operations` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `recovery-window.md` | md / markdown | en | offline | **★正解** |
| `service-restoration.md` | md / markdown | en | offline | **△distractor** |
| `trend-figure-045.png` | png / png | en | online_ocr | filler |
| `utility-025.rs` | txt / code-source | en | offline | filler |
| `worklog-005.md` | md / markdown | en | offline | filler |

#### 20. `home/services/identity/prod/oncall/operations` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `trend-figure-046.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `utility-026.ts` | txt / code-source | en | offline | filler |
| `worklog-006.md` | md / markdown | en | offline | filler |

### `corpus/p02/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/incident-staging/inc-2026-0713/checkout/prod/pods/pod-004/logs/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p02.pdf` | pdf_text / pdf-text-layer | en | online_ocr |
| `archived-session-p02.log` | txt / log | en | offline |
| `budget-sheet-p02.xlsx` | xlsx_realism / xlsx-realism | en | unsupported |
| `field-photo-p02.png` | png / png | en | online_ocr |
| `legacy-helper-p02.py` | txt / code-source | en | offline |

### `qhard-a/p02/` — 3 件 (Q_hard 追加パック)

**B とは事実・ファイルを共有しません。** 別の fact/query 名前空間です。

パス: `qhard-a/p02/home/services/checkout/prod/oncall/operations/`

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `context-overview.md` | md / markdown | en | offline | filler |
| `failover-summary.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | **△distractor** |
| `incident-brief.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | **★正解** |

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
| plain-text | 直接記述 | 素のテキストメモ/転記/エクスポート。 |
| structured-json | 直接記述 | 実務の設定/エクスポート JSON。 |
| structured-sql | 直接記述 | 実務の SQL (DDL/クエリ/マイグレーション)。 |
| structured-xml | 直接記述 | 実務の XML (設定/エクスポート/フィード)。 |
| structured-yaml | 直接記述 | 実務の設定 YAML (CI/インフラ/アプリ設定)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**KIO は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `en 100` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **SRE・障害対応** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p02 担当分)

### `qa01` — class **hard1**

- **クエリ**: 「障害メモに記された切替判断の時間条件は何分か」
- **正解ファイル**: `qhard-a/p02/home/services/checkout/prod/oncall/operations/incident-brief.pdf`
- **正解の所在**: section「判断節」
- **埋め込む事実 (この表現・値を必ず使う)**: 障害切替を承認した閾値は 17 分。
- **section hint**: 判断節
- **fact_id**: `f001` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qa01`: `qhard-a/p02/home/services/checkout/prod/oncall/operations/failover-summary.pdf`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard1 不変条件 (ラスタスキャン PDF)**

- TeX → PDF → `pdftoppm -r 200 -png` → `img2pdf` の順でビルドし、**テキスト層をゼロ**にする。
- 最終 PDF に `pdftotext` をかけ、Unicode 空白を除去した結果が **空** でなければ不合格。
- 事実は **ラスタ画像の画素**にのみ存在させる。

### `qb02` — class **hard2**

- **クエリ**: 「修復作業に充てる時間枠は何分か」
- **正解ファイル**: `corpus/p02/home/services/checkout/prod/oncall/operations/recovery-window.md`
- **正解の所在**: section「Runbook note」
- **埋め込む事実 (この表現・値を必ず使う)**: The Atlas fallback interval after the gateway patch is 19 minutes.
- **section hint**: Runbook note
- **fact_id**: `f010` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb02`: `corpus/p02/home/services/checkout/prod/oncall/operations/service-restoration.md`
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

- `office-specs/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0103-review-summary-042.docx.md`
- `office-specs/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0104-review-summary-043.docx.md`
- `office-specs/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0105-status-review-044.pptx.md`
- `sources/pdf/raster-only/r-qhard-a-v1-p02-1016.tex`
- `sources/pdf/raster-only/r-qhard-a-v1-p02-1017.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p02-0057.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p02-0100.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p02-0101.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p02-0102.tex`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0055.log`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0056.py`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0060.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0061.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0062.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0063.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0064.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0065.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0066.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0067.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0068.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0069.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0070.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0071.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0072.md`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0073.txt`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0074.log`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0075.jsonl`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0076.txt`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0077.log`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0078.jsonl`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0079.txt`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0080.log`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0081.py`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0082.rs`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0083.ts`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0084.sh`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0085.py`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0086.rs`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0087.ts`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0088.sh`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0089.py`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0090.rs`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0091.ts`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0092.sh`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0093.py`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0094.rs`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0095.ts`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0096.json`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0097.yaml`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0098.xml`
- `sources/text/baseline-fixture-b-v1/p02/r-baseline-fixture-b-v1-p02-0099.sql`
- `sources/text/qhard-a-v1/p02/r-qhard-a-v1-p02-1018.md`
- `sources/visual/specs/r-baseline-fixture-b-v1-p02-0058.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p02-0106.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p02-0107.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p02-0059.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p02/` と `qhard-a/p02/` の中だけ**。他 persona 0 件。
- [ ] **`.kio` を 1 つも作っていない**。KIO の内部形式を一切書いていない。
- [ ] OCR / Office→PDF 変換 / embedding / 索引化を **実行していない**。
- [ ] ファイル数が **B=53 (home 48 / ambient 5)** **A=3** と完全一致。
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

