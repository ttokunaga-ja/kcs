# Codex セッション ブリーフ — ユースケース 11/20 : `p11` アカウント営業・更新交渉

> **このセッションで生成するのは `p11` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: account executive / opportunity / 言語比率: **en 80 / es 20**

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
| 親フォルダ (B) | `corpus/p11/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| Q_hard 追加パック (A) `qhard-a/p11/` | 3 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 21 (+A 3) |
| embedding 見積り chunk (B) | 56 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 3 |
| jpeg / jpeg | 1 |
| md / markdown | 13 |
| pdf_rasterized / pdf-raster-only | 1 |
| pdf_text / pdf-text-layer | 4 |
| png / png | 1 |
| pptx / office-powerpoint | 2 |
| txt / code-source | 1 |
| txt / eml | 7 |
| txt / html | 6 |
| txt / jsonl | 1 |
| txt / log | 3 |
| txt / plain-text | 2 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| txt / structured-sql | 1 |
| txt / structured-xml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p11/home/` の 20 scope leaf

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

#### 1. `home/accounts/account-alpha/calls` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-022.html` | txt / html | en | offline | filler |
| `status-review-042.pptx` | pptx / office-powerpoint | es | online_ocr | filler |
| `worklog-002.md` | md / markdown | en | offline | filler |

#### 2. `home/accounts/account-alpha/plans` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-021.eml` | txt / eml | en | offline | filler |
| `renewal-alternatives.md` | md / markdown | en | offline | **△distractor** |
| `renewal-conditions.md` | md / markdown | en | offline | **★正解** |
| `status-review-041.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | en | offline | filler |

#### 3. `home/accounts/account-alpha/proposals` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-023.eml` | txt / eml | en | offline | filler |
| `trend-figure-043.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `worklog-003.md` | md / markdown | en | offline | filler |

#### 4. `home/accounts/account-beta/calls` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-025.eml` | txt / eml | en | offline | filler |
| `worklog-005.md` | md / markdown | en | offline | filler |

#### 5. `home/accounts/account-beta/plans` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-024.html` | txt / html | es | offline | filler |
| `worklog-004.md` | md / markdown | en | offline | filler |

#### 6. `home/accounts/account-beta/proposals` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-026.html` | txt / html | es | offline | filler |
| `worklog-006.md` | md / markdown | en | offline | filler |

#### 7. `home/archive/sales/fy2025/closed-opportunities` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-020.json` | txt / structured-json | en | offline | filler |
| `review-summary-040.docx` | docx / office-word | es | online_ocr | filler |

#### 8. `home/cloud/onedrive/sales-notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `archived-note-037.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | filler |
| `record-017.xml` | txt / structured-xml | en | offline | filler |

#### 9. `home/cloud/sharepoint/revenue-team` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-018.sql` | txt / structured-sql | en | offline | filler |
| `review-summary-038.docx` | docx / office-word | es | online_ocr | filler |

#### 10. `home/desktop/sales/account-alpha/working` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-013.log` | txt / log | en | offline | filler |
| `message-033.eml` | txt / eml | en | offline | filler |

#### 11. `home/documents/sales/playbooks/reference` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | en | offline | filler |
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | es | online_ocr | filler |

#### 12. `home/downloads/crm-exports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | en | offline | filler |
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | es | online_ocr | filler |

#### 13. `home/downloads/inbox/crm-attachments` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | en | offline | filler |
| `reference-brief-035.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 14. `home/mail/outlook/account-alpha/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-019.csv` | txt / structured-csv | en | offline | filler |
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |

#### 15. `home/sales/contracts/drafts/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-030.html` | txt / html | es | offline | filler |
| `worklog-010.md` | md / markdown | en | offline | filler |

#### 16. `home/sales/contracts/executed/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-031.eml` | txt / eml | en | offline | filler |
| `worklog-011.md` | md / markdown | en | offline | filler |

#### 17. `home/sales/opportunities/active/pipeline` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-027.eml` | txt / eml | en | offline | filler |
| `worklog-007.md` | md / markdown | en | offline | filler |

#### 18. `home/sales/pricing/approved/quotes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-029.eml` | txt / eml | en | offline | filler |
| `worklog-009.md` | md / markdown | en | offline | filler |

#### 19. `home/sales/rfp/active/responses` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-028.html` | txt / html | es | offline | filler |
| `worklog-008.md` | md / markdown | en | offline | filler |

#### 20. `home/travel/customer-meetings/notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-012.txt` | txt / plain-text | en | offline | filler |
| `message-032.html` | txt / html | es | offline | filler |

### `corpus/p11/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/outlook-cache/account-alpha/2026/07/thread-0042/attachments/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p11.pdf` | pdf_text / pdf-text-layer | en | online_ocr |
| `archived-session-p11.log` | txt / log | en | offline |
| `budget-sheet-p11.xlsx` | xlsx_realism / xlsx-realism | en | unsupported |
| `field-photo-p11.png` | png / png | en | online_ocr |
| `legacy-helper-p11.py` | txt / code-source | en | offline |

### `qhard-a/p11/` — 3 件 (Q_hard 追加パック)

**B とは事実・ファイルを共有しません。** 別の fact/query 名前空間です。

パス: `qhard-a/p11/home/accounts/account-alpha/proposals/`

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `context-overview.md` | md / markdown | en | offline | filler |
| `customer-brief.pdf` | pdf_rasterized / pdf-raster-only | en | online_ocr | **★正解** |
| `pricing-outline.pdf` | pdf_rasterized / pdf-raster-only | es | online_ocr | **△distractor** |

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
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**Kio は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `en 80 / es 20` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **アカウント営業・更新交渉** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p11 担当分)

### `qa03` — class **hard1**

- **クエリ**: 「追加支援に使える最大金額はいくらか」
- **正解ファイル**: `qhard-a/p11/home/accounts/account-alpha/proposals/customer-brief.pdf`
- **正解の所在**: section「費用節」
- **埋め込む事実 (この表現・値を必ず使う)**: 顧客向け追加作業の上限は 38,400 USD。
- **section hint**: 費用節
- **fact_id**: `f003` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qa03`: `qhard-a/p11/home/accounts/account-alpha/proposals/pricing-outline.pdf`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard1 不変条件 (ラスタスキャン PDF)**

- TeX → PDF → `pdftoppm -r 200 -png` → `img2pdf` の順でビルドし、**テキスト層をゼロ**にする。
- 最終 PDF に `pdftotext` をかけ、Unicode 空白を除去した結果が **空** でなければ不合格。
- 事実は **ラスタ画像の画素**にのみ存在させる。

### `qb11` — class **hard2**

- **クエリ**: 「契約を延長できるのは、どのくらい前に知らせた場合か」
- **正解ファイル**: `corpus/p11/home/accounts/account-alpha/plans/renewal-conditions.md`
- **正解の所在**: section「Commercial condition」
- **埋め込む事実 (この表現・値を必ず使う)**: The Lark agreement permits renewal only with a 72-day notice.
- **section hint**: Commercial condition
- **fact_id**: `f019` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb11`: `corpus/p11/home/accounts/account-alpha/plans/renewal-alternatives.md`
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

- `office-specs/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0560-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0561-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0562-review-summary-040.docx.md`
- `office-specs/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0563-status-review-041.pptx.md`
- `office-specs/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0564-status-review-042.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p11-0559.tex`
- `sources/pdf/raster-only/r-qhard-a-v1-p11-1022.tex`
- `sources/pdf/raster-only/r-qhard-a-v1-p11-1023.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p11-0518.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p11-0556.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p11-0557.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p11-0558.tex`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0516.log`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0517.py`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0521.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0522.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0523.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0524.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0525.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0526.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0527.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0528.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0529.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0530.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0531.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0532.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0533.md`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0534.txt`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0535.log`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0536.jsonl`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0537.txt`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0538.log`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0539.xml`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0540.sql`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0541.csv`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0542.json`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0543.eml`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0544.html`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0545.eml`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0546.html`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0547.eml`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0548.html`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0549.eml`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0550.html`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0551.eml`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0552.html`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0553.eml`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0554.html`
- `sources/text/baseline-fixture-b-v1/p11/r-baseline-fixture-b-v1-p11-0555.eml`
- `sources/text/qhard-a-v1/p11/r-qhard-a-v1-p11-1024.md`
- `sources/visual/specs/r-baseline-fixture-b-v1-p11-0519.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p11-0565.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p11-0520.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] **プレースホルダ名 (`-001` 連番 / `-pNN`) が 1 つも残っていない。**
- [ ] **`★正解` / `△distractor` のファイル名を変えていない。**

- [ ] 生成したファイルは **`corpus/p11/` と `qhard-a/p11/` の中だけ**。他 persona 0 件。
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

