# Codex セッション ブリーフ — ユースケース 13/20 : `p13` 法務・リーガルホールド

> **このセッションで生成するのは `p13` だけです。** 他の 19 ユースケースには一切触れないでください。
> 対象領域: legal / hold matter / 言語比率: **ja 75 / en 25**

---

## 0. 絶対規則 — 違反したらこのセッションの成果物は破棄

1. **`.kcs` を作らない・触らない・書かない。** KCS の内部 (objects / index / sqlite / manifest 相当) を
   自分で作ることは全面禁止。あなたが作るのは **普通のファイルとフォルダだけ**。
2. **OCR・Office→PDF 変換・embedding・索引化を自分で実行しない。** それらは後段の
   実 KCS パイプライン (`kcs init` / `kcs index --approve --online`) だけが行う。
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
| 親フォルダ (B) | `corpus/p13/` |
| 生成ファイル数 (B) | **50** |
| └ `home/` (索引対象・20 scope leaf) | 45 |
| └ `ambient-home/` (**索引対象外**・realism 専用) | 5 |
| OCR 課金ユニット (B / 後段パイプラインが消費) | 37 |
| embedding 見積り chunk (B) | 68 |

### 形式の分布 (この数値どおりに作る)

| format / subtype | 件数 |
|---|---:|
| docx / office-word | 6 |
| md / markdown | 11 |
| pdf_rasterized / pdf-raster-only | 2 |
| pdf_text / pdf-text-layer | 6 |
| png / png | 1 |
| pptx / office-powerpoint | 1 |
| txt / code-source | 1 |
| txt / eml | 5 |
| txt / html | 5 |
| txt / jsonl | 2 |
| txt / log | 4 |
| txt / plain-text | 3 |
| txt / structured-json | 1 |
| txt / structured-yaml | 1 |
| xlsx_realism / xlsx-realism | 1 |

---

## 2. 生成対象ファイル (完全リスト) — `corpus/p13/home/` の 20 scope leaf

各 leaf は **1 つの KCS scope** になります。ファイルは **leaf 直下**に置いてください。

#### 1. `home/archive/legal/matters/2020-2025/closed` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-020.json` | txt / structured-json | ja | offline | filler |
| `review-summary-040.docx` | docx / office-word | ja | online_ocr | filler |

#### 2. `home/cloud/onedrive/legal/working` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-017.jsonl` | txt / jsonl | ja | offline | filler |
| `review-summary-037.docx` | docx / office-word | en | online_ocr | filler |

#### 3. `home/cloud/sharepoint/legal/matters/matter-alpha` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-018.txt` | txt / plain-text | ja | offline | filler |
| `review-summary-038.docx` | docx / office-word | ja | online_ocr | filler |

#### 4. `home/desktop/privileged-working` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-013.log` | txt / log | ja | offline | filler |
| `reference-brief-033.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 5. `home/documents/legal/privileged/reference` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-014.jsonl` | txt / jsonl | ja | offline | filler |
| `reference-brief-034.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 6. `home/downloads/exports/dms/matter-alpha` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-016.log` | txt / log | ja | offline | filler |
| `reference-brief-036.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 7. `home/downloads/inbox/legal-hold-drops` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-015.txt` | txt / plain-text | ja | offline | filler |
| `reference-brief-035.pdf` | pdf_text / pdf-text-layer | en | online_ocr | filler |

#### 8. `home/legal/board/reports/privileged` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-012.txt` | txt / plain-text | ja | offline | filler |
| `reference-brief-032.pdf` | pdf_text / pdf-text-layer | ja | online_ocr | filler |

#### 9. `home/legal/contracts/drafts/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-025.eml` | txt / eml | en | offline | filler |
| `worklog-005.md` | md / markdown | ja | offline | filler |

#### 10. `home/legal/contracts/executed/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-026.html` | txt / html | ja | offline | filler |
| `worklog-006.md` | md / markdown | ja | offline | filler |

#### 11. `home/legal/contracts/templates/approved` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-027.eml` | txt / eml | en | offline | filler |
| `worklog-007.md` | md / markdown | ja | offline | filler |

#### 12. `home/legal/due-diligence/data-room/review` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-030.html` | txt / html | ja | offline | filler |
| `worklog-010.md` | md / markdown | ja | offline | filler |

#### 13. `home/legal/legal-hold/notices/issued` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-031.eml` | txt / eml | en | offline | filler |
| `worklog-011.md` | md / markdown | ja | offline | filler |

#### 14. `home/legal/policies/privacy/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-029.eml` | txt / eml | en | offline | filler |
| `worklog-009.md` | md / markdown | ja | offline | filler |

#### 15. `home/legal/regulations/guidance/current` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-028.html` | txt / html | ja | offline | filler |
| `worklog-008.md` | md / markdown | ja | offline | filler |

#### 16. `home/mail/outlook/legal-hold/recent` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `activity-019.log` | txt / log | en | offline | filler |
| `review-summary-039.docx` | docx / office-word | en | online_ocr | filler |

#### 17. `home/matters/matter-alpha/correspondence` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `record-021.yaml` | txt / structured-yaml | en | offline | filler |
| `review-summary-041.docx` | docx / office-word | en | online_ocr | filler |
| `worklog-001.md` | md / markdown | ja | offline | filler |

#### 18. `home/matters/matter-alpha/legal-hold/collection-01/working` — 5 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `hold-exception.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **★正解** |
| `message-022.html` | txt / html | ja | offline | filler |
| `notification-memo.pdf` | pdf_rasterized / pdf-raster-only | ja | online_ocr | **△distractor** |
| `review-summary-042.docx` | docx / office-word | ja | online_ocr | filler |
| `worklog-002.md` | md / markdown | ja | offline | filler |

#### 19. `home/matters/matter-beta/correspondence` — 3 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-023.eml` | txt / eml | en | offline | filler |
| `status-review-043.pptx` | pptx / office-powerpoint | en | online_ocr | filler |
| `worklog-003.md` | md / markdown | ja | offline | filler |

#### 20. `home/matters/matter-beta/legal-hold/collection-02/working` — 2 件

| ファイル名 | 形式 / subtype | 言語 | レーン | 役割 |
|---|---|---|---|---|
| `message-024.html` | txt / html | ja | offline | filler |
| `worklog-004.md` | md / markdown | ja | offline | filler |

### `corpus/p13/ambient-home/` — 5 件 (**索引対象外**)

PC に実在する「深い未管理フォルダ」の再現。**検索・正解・評価分母から除外**されるので、
fact は絶対に置かないこと。realism のためだけに存在します。

パス: `ambient-home/legal-hold/matter-alpha/collection-01/custodian-syn-01/mail/attachments/`

| ファイル名 | 形式 / subtype | 言語 | レーン |
|---|---|---|---|
| `archive-brief-p13.pdf` | pdf_text / pdf-text-layer | ja | online_ocr |
| `archived-session-p13.log` | txt / log | ja | offline |
| `budget-sheet-p13.xlsx` | xlsx_realism / xlsx-realism | ja | unsupported |
| `field-photo-p13.png` | png / png | ja | online_ocr |
| `legacy-helper-p13.py` | txt / code-source | ja | offline |

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
| eml | 直接記述 | 実務で自然な内容にする。 |
| html | 直接記述 | 実務で自然な内容にする。 |
| jsonl | 直接記述 | 実務のイベント/レコードを 1 行 1 JSON で。 |
| log | 直接記述 | 実際のアプリ/システムログ形式 (タイムスタンプ + レベル + メッセージ)。 |
| plain-text | 直接記述 | 素のテキストメモ/転記/エクスポート。 |
| structured-json | 直接記述 | 実務の設定/エクスポート JSON。 |
| structured-yaml | 直接記述 | 実務の設定 YAML (CI/インフラ/アプリ設定)。 |
| xlsx-realism | Excel プラグイン | Excel プラグインで実務の表。**KCS は索引しない** (realism 専用・正解に使わない)。 |

**共通の realism 方針**

- 本文は `ja 75 / en 25` の比率で書く。技術用語・製品名・単位・コードは自然に英語のままでよい。
- 内容は **法務・リーガルホールド** の実務そのもの。プロジェクト名・製品名・チーム名・日付・数値に一貫性を持たせ、
  複数ファイルにまたがって同じ世界観 (同じ製品/案件/期) を共有させる。
- ファイル名は既に確定済み。**中身をファイル名に合わせて**書く。
- 図表 (png/jpeg/pptx 埋込) の数値・軸・凡例は **レンダリングして画素に描く**。装飾目的の
  拡散画像を使う場合は **文字を一切入れない**。

---

## 4. 正解クエリ契約 (p13 担当分)

### `qb13` — class **hard1**

- **クエリ**: 「保全除外を知らせる期限はいつか」
- **正解ファイル**: `corpus/p13/home/matters/matter-alpha/legal-hold/collection-01/working/hold-exception.pdf`
- **正解の所在**: section「通知節」
- **埋め込む事実 (この表現・値を必ず使う)**: hold exception の通知期限は 2026-09-03。
- **section hint**: 通知節
- **fact_id**: `f021` — **コーパス全体で出現 1 回のみ**
- **distractor** `d-qb13`: `corpus/p13/home/matters/matter-alpha/legal-hold/collection-01/working/notification-memo.pdf`
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

- `office-specs/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0659-review-summary-037.docx.md`
- `office-specs/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0660-review-summary-038.docx.md`
- `office-specs/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0661-review-summary-039.docx.md`
- `office-specs/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0662-review-summary-040.docx.md`
- `office-specs/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0663-review-summary-041.docx.md`
- `office-specs/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0664-review-summary-042.docx.md`
- `office-specs/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0665-status-review-043.pptx.md`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p13-0621.tex`
- `sources/pdf/raster-only/r-baseline-fixture-b-v1-p13-0622.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p13-0618.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p13-0654.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p13-0655.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p13-0656.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p13-0657.tex`
- `sources/pdf/text-layer/r-baseline-fixture-b-v1-p13-0658.tex`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0616.log`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0617.py`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0623.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0624.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0625.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0626.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0627.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0628.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0629.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0630.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0631.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0632.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0633.md`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0634.txt`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0635.log`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0636.jsonl`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0637.txt`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0638.log`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0639.jsonl`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0640.txt`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0641.log`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0642.json`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0643.yaml`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0644.html`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0645.eml`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0646.html`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0647.eml`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0648.html`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0649.eml`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0650.html`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0651.eml`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0652.html`
- `sources/text/baseline-fixture-b-v1/p13/r-baseline-fixture-b-v1-p13-0653.eml`
- `sources/visual/specs/r-baseline-fixture-b-v1-p13-0619.json`
- `sources/xlsx-realism/r-baseline-fixture-b-v1-p13-0620.json`

---

## 6. セッション完了前の自己検査 (すべて満たすこと)

- [ ] 生成したファイルは **`corpus/p13/` と `qhard-a/p13/` の中だけ**。他 persona 0 件。
- [ ] **`.kcs` を 1 つも作っていない**。KCS の内部形式を一切書いていない。
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

生成物は **普通のファイルのみ**。この後、オペレータ側で実 KCS パイプラインが
`kcs init` → `kcs index --approve --online` を実行し、`.kcs` 生成・Office→PDF 変換・
OCR (Mistral Batch)・CAS 保存・embedding (Gemini)・索引化を行います。
さらにその後、別セッションで **編集・追加・削除・フォルダ移動**を行い、実パイプラインで
履歴 (time-travel / `--all-history` / `--include-deleted`) を生成します。

