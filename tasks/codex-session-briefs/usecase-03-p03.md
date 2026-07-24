# Codex セッション ブリーフ — ユースケース 3/20 : `p03` セキュリティ/GRC・インシデント証跡

> **このセッションで生成するのは `p03` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: security and GRC / incident evidence / 言語比率: **ja 70 / en 30**

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
| 親フォルダ (B) | `corpus/p03/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 27 |
| embedding 見積り chunk (B) | 59 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 3 |
| md / markdown | 9 |
| pdf_rasterized / pdf-raster-only | 2 |
| pdf_text / pdf-text-layer | 7 |
| png / png | 2 |
| pptx / office-powerpoint | 1 |
| txt / code-source | 12 |
| txt / html | 1 |
| txt / jsonl | 2 |
| txt / log | 3 |
| txt / plain-text | 2 |
| txt / structured-csv | 1 |
| txt / structured-json | 1 |
| txt / structured-sql | 1 |
| txt / structured-xml | 1 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p03/home/` の 20 scope leaf

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

#### 1. `home/archive/closed/assessments` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-040.docx` | docx / office-word | ja | online_ocr | filler |
| `utility-020.py` | txt / code-source | ja | offline | filler |

#### 2. `home/cloud/personal/review-notes` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-037.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |
| `utility-017.rs` | txt / code-source | en | offline | filler |

#### 3. `home/cloud/team/grc-shared` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-038.docx` | docx / office-word | ja | online_ocr | filler |
| `utility-018.ts` | txt / code-source | ja | offline | filler |

#### 4. `home/compliance/audits/evidence-requests` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-027.xml` | txt / structured-xml | en | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 5. `home/compliance/frameworks/soc2/control-evidence` — 4 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `control-coverage.png` | png / png | ja | online_ocr | **★正解** |
| `control-matrix.png` | png / png | ja | online_ocr | **△distractor** |
| `utility-026.ts` | txt / code-source | ja | offline | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 6. `home/compliance/governance/policies` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-025.rs` | txt / code-source | en | offline | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 7. `home/desktop/active-audit` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-013.log` | txt / log | en | offline | filler |
| `reference-brief-033.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 8. `home/documents/reference/control-library` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | ja | offline | filler |
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 9. `home/downloads/exports/audit-packages` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |
| `utility-016.py` | txt / code-source | ja | offline | filler |

#### 10. `home/downloads/inbox/evidence-drops` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | en | offline | filler |
| `reference-brief-035.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 11. `home/mail/recent/auditor-threads` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |
| `utility-019.sh` | txt / code-source | en | offline | filler |

#### 12. `home/meetings/security/reviews` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-012.txt` | txt / plain-text | ja | offline | filler |
| `message-032.html` | txt / html | ja | offline | filler |

#### 13. `home/privacy/assessments/risk-register` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-011.jsonl` | txt / jsonl | ja | offline | filler |
| `record-031.yaml` | txt / structured-yaml | en | offline | filler |

#### 14. `home/security/assessments/pentest-reports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-022.ts` | txt / code-source | ja | offline | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 15. `home/security/findings/vulnerabilities` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `utility-023.sh` | txt / code-source | en | offline | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 16. `home/security/incidents/reports` — 4 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `retention-decision.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **★正解** |
| `retention-review.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **△distractor** |
| `utility-024.py` | txt / code-source | ja | offline | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

#### 17. `home/security/programs/threat-models` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `status-review-041.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `utility-021.rs` | txt / code-source | en | offline | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

#### 18. `home/soc/detections/rules` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-010.log` | txt / log | ja | offline | filler |
| `record-030.json` | txt / structured-json | ja | offline | filler |

#### 19. `home/soc/siem/event-exports` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-029.csv` | txt / structured-csv | en | offline | filler |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 20. `home/third-party/vendor-risk/questionnaires` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-028.sql` | txt / structured-sql | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

### `corpus/p03/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/evidence-staging/soc2/cc6-1/2026/request-042/raw/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p03.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p03.log` | txt / log | ja | offline |
| `budget-sheet-p03.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `legacy-helper-p03.py` | txt / code-source | ja | offline |
| `vendor-record-p03.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |

---

## 3. 形式別の生成方法と realism 要件

| subtype | 使うもの | realism 要件 |
|---|---|---|
| office-word | Word プラグイン | Word プラグインで実務文書 (見出し・表・ヘッダ/フッタ)。 |
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
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**Kio は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 70 / en 30` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **セキュリティ/GRC・インシデント証跡** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p03 担当分)

### `qb03` — class **hard1**

- **クエリ**: 「保持例外の決裁日はいつだったか」
- **正解ファイル**: `corpus/p03/home/security/incidents/reports/retention-decision.pdf`
- **正解の所在**: section「承認節」
- **埋め込む事実 (この表現・値を必ず使う)**: 保持除外の承認期限は 2026-08-27。
- **section hint**: 承認節
- **fact_id**: `f011` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb03`: `corpus/p03/home/security/incidents/reports/retention-review.pdf`
  - 同じ leaf・同じ形式・自然なファイル名。**近いが異なる値**にする。
  - **正解の事実そのものを絶対に含めない。**

**hard1 不変条件 (ラスタスキャン PDF)**

- TeX → PDF → `pdftoppm -r 200 -png` → `img2pdf` の順でビルドし、**テキスト層をゼロ**にする。
- 最終 PDF に `pdftotext` をかけ、Unicode 空白を除去した結果が **空** でなければ不合格。
- 事実は **ラスタ画像の画素**にのみ存在させる。

### `qb21` — class **hard3**

- **クエリ**: 「CC6.1 の証跡充足率は何パーセントか」
- **正解ファイル**: `corpus/p03/home/compliance/frameworks/soc2/control-evidence/control-coverage.png`
- **正解の所在**: section「Rendered control matrix」
- **埋め込む事実 (この表現・値を必ず使う)**: Control CC6.1 is evidenced by 87 percent of sampled records.
- **section hint**: Rendered control matrix
- **fact_id**: `f029` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb21`: `corpus/p03/home/compliance/frameworks/soc2/control-evidence/control-matrix.png`
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

- `office-specs/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0154-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0155-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0156-review-summary-040.docx.md`
- `office-specs/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0157-status-review-041.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p03-0113.tex`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p03-0114.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p03-0110.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p03-0111.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p03-0149.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p03-0150.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p03-0151.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p03-0152.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p03-0153.tex`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0108.log`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0109.py`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0117.md`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0118.md`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0119.md`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0120.md`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0121.md`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0122.md`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0123.md`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0124.md`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0125.md`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0126.log`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0127.jsonl`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0128.txt`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0129.log`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0130.jsonl`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0131.txt`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0132.py`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0133.rs`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0134.ts`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0135.sh`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0136.py`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0137.rs`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0138.ts`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0139.sh`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0140.py`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0141.rs`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0142.ts`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0143.xml`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0144.sql`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0145.csv`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0146.json`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0147.yaml`
- `sources/text/baseline-fixture-b-v1/p03/r-baseline-fixture-b-v1-p03-0148.html`
- `sources/visual/specs/r-baseline-fixture-b-v1-p03-0115.json`
- `sources/visual/specs/r-baseline-fixture-b-v1-p03-0116.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p03-0112.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] **プレースホルダ名 (`-001` 連番 / `-pNN`) が 1 つも残っていない。**
- [ ] **`★正解` / `△distractor` のファイル名を変えていない。**

- [ ] 生成したファイルは **`corpus/p03/` と `qhard-a/p03/` の中だけ**。他 persona 0 件。
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

