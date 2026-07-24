# Codex セッション ブリーフ — ユースケース 12/20 : `p12` カスタマーサポート・エスカレーション

> **このセッションで生成するのは `p12` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: support / customer queue / 言語比率: **ja 75 / en 25**

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
| 親フォルダ (B) | `corpus/p12/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| Q_hard 追加パック (A) `qhard-a/p12/` | 3 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 13 (+A 4) |
| embedding 見積り chunk (B) | 51 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 2 |
| jpeg / jpeg | 2 |
| md / markdown | 14 |
| pdf_text / pdf-text-layer | 2 |
| png / png | 3 |
| txt / code-source | 7 |
| txt / eml | 1 |
| txt / html | 1 |
| txt / jsonl | 4 |
| txt / log | 5 |
| txt / plain-text | 3 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| txt / structured-sql | 1 |
| txt / structured-xml | 1 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p12/home/` の 20 scope leaf

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

#### 1. `home/archive/support/fy2024/closed-cases` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-020.jsonl` | txt / jsonl | ja | offline | filler |
| `trend-figure-040.png` | png / png | ja | online_ocr | filler |

#### 2. `home/cloud/drive/support-personal` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-017.jsonl` | txt / jsonl | ja | offline | filler |
| `reference-brief-037.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 3. `home/cloud/sharepoint/customer-success` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-018.txt` | txt / plain-text | ja | offline | filler |
| `review-summary-038.docx` | docx / office-word | ja | online_ocr | filler |

#### 4. `home/customers/customer-alpha/cases/case-history` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-027.sh` | txt / code-source | en | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 5. `home/customers/customer-alpha/qbr` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-026.ts` | txt / code-source | ja | offline | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 6. `home/customers/customer-beta/cases/case-history` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-029.rs` | txt / code-source | en | offline | filler |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 7. `home/customers/customer-beta/qbr` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-028.py` | txt / code-source | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 8. `home/desktop/active-queue` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-013.log` | txt / log | ja | offline | filler |
| `record-033.sql` | txt / structured-sql | en | offline | filler |

#### 9. `home/documents/customer-success/knowledge/reference` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | ja | offline | filler |
| `record-034.csv` | txt / structured-csv | ja | offline | filler |

#### 10. `home/downloads/exports/ticket-batches` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | ja | offline | filler |
| `message-036.html` | txt / html | ja | offline | filler |

#### 11. `home/downloads/inbox/case-attachments` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | ja | offline | filler |
| `message-035.eml` | txt / eml | en | offline | filler |

#### 12. `home/knowledge-base/drafts` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-024.py` | txt / code-source | ja | offline | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

#### 13. `home/knowledge-base/published` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-025.rs` | txt / code-source | en | offline | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 14. `home/mail/outlook/escalations/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-019.log` | txt / log | ja | offline | filler |
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |

#### 15. `home/support/customer-attachments/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-030.json` | txt / structured-json | ja | offline | filler |
| `worklog-010.md` | md / markdown | ja | offline | filler |

#### 16. `home/support/escalations/active` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-022.log` | txt / log | ja | offline | filler |
| `escalation-sla.md` | md / markdown | en | offline | **★正解** |
| `response-guidance.md` | md / markdown | en | offline | **△distractor** |
| `trend-figure-042.jpeg` | jpeg / jpeg | ja | online_ocr | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 17. `home/support/incidents/linked-cases` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-032.xml` | txt / structured-xml | ja | offline | filler |
| `worklog-012.md` | md / markdown | ja | offline | filler |

#### 18. `home/support/known-issues/triage` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-023.jsonl` | txt / jsonl | en | offline | filler |
| `trend-figure-043.jpeg` | jpeg / jpeg | en | online_ocr | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 19. `home/support/macros/replies` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-031.yaml` | txt / structured-yaml | en | offline | filler |
| `worklog-011.md` | md / markdown | ja | offline | filler |

#### 20. `home/support/ticket-exports` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-021.txt` | txt / plain-text | ja | offline | filler |
| `trend-figure-041.png` | png / png | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

### `corpus/p12/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/ticket-cache/customer-alpha/case-1042/updates/2026/07/attachments/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p12.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p12.log` | txt / log | ja | offline |
| `budget-sheet-p12.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p12.png` | png / png | ja | online_ocr |
| `legacy-helper-p12.py` | txt / code-source | ja | offline |

### `qhard-a/p12/` — 3 件 (Q_hard 追加パック)

**B とは事実・ファイルを共有しません。** 別の fact/query 名前空間です。

パス: `qhard-a/p12/home/support/escalations/active/`

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `backlog-trend.pptx` | pptx / office-powerpoint | ja | online_ocr | **△distractor** |
| `context-overview.md` | md / markdown | en | offline | filler |
| `queue-trend.pptx` | pptx / office-powerpoint | ja | online_ocr | **★正解** |

---

## 3. 形式別の生成方法と realism 要件

| subtype | 使うもの | realism 要件 |
|---|---|---|
| office-word | Word プラグイン | Word プラグインで実務文書 (見出し・表・ヘッダ/フッタ)。 |
| jpeg | 画像生成/レンダラ | 同上 (JPEG)。写真的な物は装飾のみ・文字を載せない。 |
| markdown | 直接記述 | 実務の Markdown ノート/議事録/ADR/ランブック。見出し・箇条書き・表を自然に使う。 |
| pdf-text-layer | TeX → ビルド | テキスト層のある PDF。TeX ソースを realistic な実務文書に書き換えてビルド。 |
| png | 画像生成/レンダラ | matplotlib/PIL/TeX→PNG でレンダリングした実務の図表/スキャン。 |
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

- 本文は `ja 75 / en 25` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **カスタマーサポート・エスカレーション** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p12 担当分)

### `qa07` — class **hard3**

- **クエリ**: 「金曜日のキュー件数はいくつか」
- **正解ファイル**: `qhard-a/p12/home/support/escalations/active/queue-trend.pptx`
- **正解の所在**: section「Rendered queue trend」
- **埋め込む事実 (この表現・値を必ず使う)**: Friday's queue bar shows 63 cases.
- **section hint**: Rendered queue trend
- **fact_id**: `f007` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qa07`: `qhard-a/p12/home/support/escalations/active/backlog-trend.pptx`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard3 不変条件 (レンダリングされた図表の事実)**

- 事実の値・軸・凡例・ラベルは **matplotlib/PIL/TeX→PNG でレンダリングした画像**にのみ描く。
- PPTX の場合はその画像を指定スライドに埋め込む。**スライドの編集可能テキスト・ノート・
  alt text・プロパティ・ChartML に事実を漏らさない** (alt text は一般的な語のみ)。
- 拡散生成画像を事実の担体にしない。

### `qb12` — class **hard2**

- **クエリ**: 「客への初動をどれほど急ぐ取り決めか」
- **正解ファイル**: `corpus/p12/home/support/escalations/active/escalation-sla.md`
- **正解の所在**: section「Case policy」
- **埋め込む事実 (この表現・値を必ず使う)**: The Nimbus case sets its opening reply deadline at 6h.
- **section hint**: Case policy
- **fact_id**: `f020` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb12`: `corpus/p12/home/support/escalations/active/response-guidance.md`
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

- `office-specs/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0610-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0611-review-summary-039.docx.md`
- `office-specs/qhard-a-v1/p12/r-qhard-a-v1-p12-1034-queue-trend.pptx.md`
- `office-specs/qhard-a-v1/p12/r-qhard-a-v1-p12-1035-backlog-trend.pptx.md`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p12-0568.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p12-0609.tex`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0566.log`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0567.py`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0571.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0572.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0573.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0574.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0575.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0576.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0577.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0578.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0579.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0580.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0581.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0582.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0583.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0584.md`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0585.log`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0586.jsonl`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0587.txt`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0588.log`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0589.jsonl`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0590.txt`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0591.log`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0592.jsonl`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0593.txt`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0594.log`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0595.jsonl`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0596.py`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0597.rs`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0598.ts`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0599.sh`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0600.py`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0601.rs`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0602.json`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0603.yaml`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0604.xml`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0605.sql`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0606.csv`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0607.eml`
- `sources/text/baseline-fixture-b-v1/p12/r-baseline-fixture-b-v1-p12-0608.html`
- `sources/text/qhard-a-v1/p12/r-qhard-a-v1-p12-1036.md`
- `sources/visual/specs/r-baseline-fixture-b-v1-p12-0569.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p12-0612.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p12-0613.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p12-0614.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p12-0615.json`
- `sources/visual/specs/r-qhard-a-v1-p12-1034-embedded.json`
- `sources/visual/specs/r-qhard-a-v1-p12-1035-embedded.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p12-0570.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] **プレースホルダ名 (`-001` 連番 / `-pNN`) が 1 つも残っていない。**
- [ ] **`★正解` / `△distractor` のファイル名を変えていない。**

- [ ] 生成したファイルは **`corpus/p12/` と `qhard-a/p12/` の中だけ**。他 persona 0 件。
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

