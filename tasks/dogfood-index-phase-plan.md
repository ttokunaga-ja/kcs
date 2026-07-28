# Dogfood 索引化フェーズ計画 (realistic corpus v1)

対象: `kio-realistic-corpus-v1` (20 ペルソナ / 1,039 ファイル / 44 MB)
目的: **実際の Kio パイプライン** (`kio init` → `kio index --approve --online`) でコーパスを索引化し、
Q_hard 32 契約を実データで評価できる状態にする。

本計画の数値は 2026-07-24 に**コーパスの複製に対して実測**したものであり、見積りではない
(実測手順は各節の「実測」を参照)。

---

## 0. 前提として確定した事実 (実測済み)

| 項目 | 実測値 | 根拠 |
|---|---|---|
| leaf scope 数 | **428** (corpus 20×21 + qhard-a 8) | `.kio` は**自フォルダ直下のみ**管理 (03 §3 L266)。子 `.kio` の自動生成は **MVP 未実装** — 実測でも親で index して 0 件・子 `.kio` 生成なし |
| offline で正規化できたファイル | **869 / 1,039** | 428 leaf に init + `index --approve --offline` を実行 |
| online (OCR) 待ちタスク | **287** | 同上 |
| OCR 課金ページ数 (修復後見込み) | **約 585** | PDF 270 + DOCX ~152 + PPTX 98 + 画像 65 |
| offline pass 所要時間 | **約 12 分** (428 scope) | 実測 |
| `.kio` 込みディスク | **186 MB** (offline のみ) | 実測。OCR 後で 250 MB 程度 |
| soffice | `/opt/homebrew/bin/soffice` あり | Kio は `soffice --convert-to pdf` を直接起動する (`office_convert.rs`) |
| 横断検索 | offline 時点で既に動作 | `kio search` は text mode に fallback して全 scope 横断 |

---

## 1. Phase 0 — 事前整備 (**索引化前に必須**)

### 1.1 OOXML パッケージ破損の修復 ← **ブロッカー**

**症状**: 30 個の DOCX/PPTX で `.rels` / `[Content_Types].xml` が
`ns0:` 接頭辞つきの名前空間で再直列化されている (Python ElementTree の既定出力)。
LibreOffice の OOXML パッケージ読取りは**既定名前空間 (接頭辞なし) を要求**するため、
ファイル全体の読込みに失敗する。

**影響 (実測)**:

- **22 ファイルが soffice で読込み不能** (DOCX 12 / PPTX 10)。XLSX は 0。
- Kio では **scope 全体の index が失敗**する:
  `KIO-E-PREPARE-OFFICE-CONVERT-001` / exit 1。
  破損ファイルだけが落ちるのではなく、**その leaf の全ファイルが未索引になる**。
- 実測で **428 中 18 scope** がこれで索引化されなかった (破損 22 ファイルを含む leaf の数と一致)。
- 該当ファイルに **★正解 4 件・△distractor 3 件**を含む
  (`latency-review.docx` / `assay-summary.pptx` / `deviation-map.pptx` / `forecast-variance.docx` ほか)。

**修復**: `scratchpad/repair_ooxml.py`
`.rels` と `[Content_Types].xml` だけを `xmlns:ns0=` → `xmlns=` / `ns0:` 除去で書き換え、
**他のパート (`word/document.xml`・`ppt/slides/*`・埋め込み画像) は 1 バイトも触らない**ため、
本文・埋め込み事実・画素は不変。

```bash
python3 repair_ooxml.py --dry-run <corpus root>   # 30 files / 102 parts
python3 repair_ooxml.py <corpus root>
```

**検証済み**: 修復前は exit 1 で 0 ファイル索引 → 修復後は **exit 0 / 5 ファイル索引**
(p01 `architecture` leaf で実機確認)。

修復後に再度 §1.1 の判定 (soffice 全数変換) を回し、124 ファイル中 124 が読込み可能であることを確認する。

### 1.2 コーパスを `/private/tmp` から退避 ← **完了 (2026-07-24)**

`/private/tmp` は macOS が定期的に消す領域なので、索引化の前に永続領域へ移した。

```
/private/tmp/kio-realistic-corpus-v1  →  ~/kio-dogfood/corpus-v1
```

移動後に 1,039 ファイル / 44 MB を確認済み。`.kio` 生成前に移したので registry の作り直しは不要
(`.kio` は絶対パスを `scope-registry` に記録するため、索引化後の移動は registry 再構築になる)。

### 1.3 設定ファイルの作成

`~/.config/kio/` は**現在存在しない**。以下 2 本を新規作成する。

`~/.config/kio/tools.toml` — Adapter 宣言と**単価の正本**:

```toml
[markdown.mistral_ocr_markdownize]
kind = "online_api"
model = "mistral-ocr-latest"
capabilities = ["ocr", "layout_detection", "table_extraction"]
auth = "env:MISTRAL_API_KEY"

[markdown.mistral_ocr_markdownize.pricing]
pages = 0.002          # Batch レーン $2/1,000 pages。本番送信は Batch のみ (2026-07-23 裁定)

[embedding.gemini_embedding_2]
kind = "online_api"
auth = "env:GEMINI_API_KEY"

[embedding.gemini_embedding_2.pricing]
tokens_in = 0.0000002   # $0.20/1M = gemini-embedding-2 の標準単価。
                        # 03 §11 の例が載せる 0.00000015 は gemini-embedding-001 の価格 (§6)
```

> 注: embedding の見積りは `estimate_embedding_cost()` のハードコード定数を使い、
> この `[pricing] tokens_in` を読まない (§6-(2))。ここは正しい値を書いておくが、
> **書いただけでは記帳は直らない**。

`~/.config/kio/config.toml` — device budget の**ハードストップ**:

```toml
[budget]
monthly_usd_cap = 5.0   # 既定は 50.0。実績見込み $1.4 に対し 3.5x のヘッドルーム
```

### 1.4 認証情報

- `MISTRAL_API_KEY` (OCR)
- `GEMINI_API_KEY` (Embedding)

いずれも未設定。`.env` の `#Kio_MISTRAL_WORKSPACE_ID` / `#Kio_OFFICE_CONVERTER` は
使うなら `KIO_` 接頭辞へ改名が必要 (`KIO_MISTRAL_WORKSPACE_ID` / `KIO_OFFICE_CONVERTER`)。

---

## 2. Phase 1 — offline baseline (**無課金**・約 12 分)

428 leaf それぞれで:

```bash
kio init
kio index --approve --offline
```

- 決定論 Adapter だけが動き、**1 円もかからない**。
- 実測: 869 ファイル正規化 / failed 0 / skipped 0。修復後は 1,039 全件が対象になる。
- ここで `kio search` が既に動く (text mode)。**Phase 2 に進む前に、ここで通る検索を記録しておく**と
  online 後の差分が測れる。

この段階を独立させる理由は、**課金前に配線・スコープ・エンコーディングの問題を全部出し切る**ため。

---

## 3. Phase 2 — online enrichment (**課金**)

```bash
kio index --approve --online     # scope ごと
kio batch resume                 # Batch ジョブの回収
```

`--online` は当該実行限りの一時 opt-in なので、非対話スクリプトでも成立する
(永続 opt-in が要るなら事前に対話承認)。

### コスト見積り (実測ページ数ベース)

| 用途 | 数量 | 単価 | 小計 |
|---|---|---|---|
| OCR — PDF | 270 pages (122 files) | $0.002 | $0.54 |
| OCR — DOCX | ~152 pages (60 files) | $0.002 | $0.30 |
| OCR — PPTX | 98 slides (44 files) | $0.002 | $0.20 |
| OCR — 画像 | 65 units (PNG 33 / JPEG 32) | $0.002 | $0.13 |
| Embedding | ~1.0–1.3 M tokens | **$0.10/1M (Batch)** | **$0.10–0.40** |
| **合計** | | | **約 $1.3–1.6** |

- OCR は **Batch レーンのみ** ($2/1,000 pages)。sync ($4/1,000) は本番送信に使わない実装になっている。
- **Embedding も Batch レーンになった (2026-07-25、H1 で実装)。** §6 が挙げた欠陥 (1)〜(3) は
  すべて解消済み: `PreferredRequestKind` を `EmbeddingAdapter` にも与え、
  `:asyncBatchEmbedContent` (inline 入力・相 2a なし) で job を投入して `kio batch resume` で回収する。
  単価は **$0.10/1M** (sync の半額) が自動的に効く。したがって embedding の見積りは半減する。
  **1 job = 1 task は job 自身を task にすることで保っている** (07 §5.3 訂正ブロック)。
- **`index --approve --online` は submit して返る。** 既定 (Batch) レーンでは
  この時点でベクタは入らない。**`kio batch resume` を回すまで vector search は空**である。
  Phase 3 の検証は resume の完了後に行うこと。
- device cap $5.0 を超えた時点で hard stop するので、暴走時の上限は $5。

### 段階投入 (canary)

1. **p01 のみ** (21 scope / 54 ファイル) を `--online` で実行。
   - 実費・Batch 往復時間・OCR 品質を実測する。**所要時間だけは事前に読めない**唯一の項目。
   - `kio ledger` と `kio status` で記帳が期待どおりか確認する。
2. 問題なければ **p02–p20 + qhard-a** を投入。

### 既知のギャップ — XLSX

`is_office_media()` は **DOCX / PPTX のみ**。XLSX は明示的に対象外 (「未定義のまま — 将来ラウンド」)。
そのため **XLSX 20 ファイルは prepare が空を返し、内容が索引に載らない**。

- Q_hard 32 契約の**正解ファイルに XLSX は無い** (pdf 12 / pptx 6 / docx 5 / md 4 / png 3 / jpeg 3) ため、
  **評価はブロックされない**。
- ただし XLSX にも online タスクが 20 件立つ (unit 0)。送信時の挙動は未確認なので、
  canary で 1 件だけ観測してから全体投入する。

---

## 4. Phase 3 — 受け入れ検証

1. `kio status --json` を 428 scope で集計 — `failed_files` 0 / `pending_online_tasks` 0 /
   `task_errors` 空 / `enriched_ratio` 1.0。
2. **32 契約の実測**: 各 ★正解 の事実文言で `kio search` し、
   正解ファイルの Evidence Pointer が上位に来ること・△distractor が正解として返らないことを確認。
   - 特に hard1 (raster PDF) / hard3 (図中画素) は **OCR が通って初めて到達可能**になるので、
     ここが OCR 品質の実質的な判定になる。
3. Evidence Pointer の解決 (`kio open` / `kio view`) を数件抜き取りで確認。
4. 既存 eval ハーネス (`eval/`) との接続は別ラウンド。

---

## 5. 実行順の要約

```
Phase 0  コーパス退避                    ← 完了 (~/kio-dogfood/corpus-v1)
         OOXML 修復 (30 files)          ← 完了 (2026-07-25。124/124 変換可・ns0 残 0・1,039 件維持)
         tools.toml / config.toml 作成    ← 完了 (2026-07-25。~/.config/kio/、0600)
         MISTRAL_API_KEY / GEMINI_API_KEY 設定  ← **未達 (下記)**
Phase 1  offline baseline 428 scope     ← 完了 (2026-07-25。428/428 indexed・errors 0)
Phase 2  p01 canary → 残り 19 + qhard-a ← 課金 約 $1.3–1.6 (上限 $5)
Phase 3  受け入れ検証 (32 契約の実測)
```

**残る判断・作業は 2 つ**:

1. **API キーの設定** (`MISTRAL_API_KEY` / `GEMINI_API_KEY` — Claude からは触れない)。
   `tools.toml` は `auth = "env:..."` で参照するので、**Kio を起動するシェルに export
   されている必要がある**。2026-07-25 時点で非対話シェルからは 2 本とも見えない。
2. Phase 2 の課金実行 GO / NO-GO (canary の後にもう一度確認する)

Phase 1 は無課金・可逆なので、OOXML 修復の完了後すぐ実行できる。

---

## 6. Embedding コストに関する実装側の欠陥 (2026-07-24 判明 → **2026-07-25 解消済み**)

> **状態 (2026-07-25)**: 下記 (1)〜(3) は H1 の実装で**すべて解消した**。本節は判明時点の
> 記録として残す。現行の契約は 07 §5.3 の訂正ブロックが正本である。
>
> - (1) → `PreferredRequestKind` を `EmbeddingAdapter` にも与え、`gemini_batch_client.rs` で
>   `:asyncBatchEmbedContent` を実装。既定レーンが Batch になった。
> - (2) → 定数を `$0.20/1M` (sync) / `$0.10/1M` (Batch) に是正し、**レーンで選ぶ**ようにした。
>   ただし「`tools.toml` の `tokens_in` を正本とする」という 07 §5.3 の規範に対しては
>   **なお定数のままで、tools.toml を読んでいない**。これは未解消として R24 監査の争点に載せている。
> - (3) → `usage: None` の degrade 自体は provider 側の仕様なので変わらない。ただし
>   トークン換算は `chars / 4.0` から **CJK を 1 文字 = 1 token として数える**方式に是正した
>   (`estimate_embedding_tokens`)。日本語の系統的過少評価は解消している。

公式ドキュメントを確認した結果、**Gemini は embedding にも 50% の Batch 割引を提供している**
([Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) /
[Batch API が embeddings 対応](https://developers.googleblog.com/en/gemini-batch-api-now-supports-embeddings-and-openai-compatibility/))。
`client.batches.create_embeddings()` / 24 時間以内の非同期完了。

| モデル | 標準 (text) | Batch (text) |
|---|---|---|
| **`gemini-embedding-2`** (Kio が pin) | **$0.20 / 1M** | **$0.10 / 1M** |
| `gemini-embedding-001` (text-only) | $0.15 / 1M | $0.075 / 1M |

これに対し実装側に 3 件の食い違いがある。

**(1) Batch レーンが embedding に存在しない。**
`PreferredRequestKind` は `MarkdownizeAdapter` にしか無く、`EmbeddingAdapter` は
`profile()` / `embed()` の 2 メソッドのみ (`traits.rs:40-44`)。したがって割引に到達できず標準単価を払う。
仕様 07 §5.3 の根拠は「Vertex はバッチ推論非対応」だが、**実装のエンドポイントは Vertex ではなく
Gemini API** (`https://generativelanguage.googleapis.com/v1beta`、`gemini_embedding.rs:31`) であり、
そちらには Batch がある。**根拠と実装先が食い違っている。**

**(2) 単価がハードコードされており、しかも別モデルの価格。**
`estimate_embedding_cost()` (`main.rs:14651`) は `$0.15/1M` を定数で持つ。これは
`gemini-embedding-001` の価格であって、Kio が pin する `gemini-embedding-2` は $0.20/1M。
**25% 過少**。`tools.toml [pricing] tokens_in` は読まれないので、設定側の修正では直らない。

**(3) その過少な見積りが、そのまま確定記帳になる。**
`:batchEmbedContents` の応答にトークン数が無いため adapter は `usage: None` を返し
(`gemini_embedding.rs:437-441`)、「caller の reservation 見積りに degrade」する。
つまり **cost_ledger に載るのは実測ではなく見積り**であり、provider 側と突合する数値が無い。

加えて `chars / 4.0` というトークン換算は日本語で成立しない。offline baseline の正規化 Markdown
(936,873 文字) で CJK 比率は 9.3%、素朴な換算で **約 1.28 倍**の乖離。OCR 後は日本語比率が上がるため
乖離はさらに開く。

**本計画への影響は無視できる**: embedding の総額は $0.2–0.8、Batch が使えたとしても差は $0.1–0.4。
**したがって索引化の前に Batch レーンを実装しない。** ただし (2)(3) は
「budget cap が守る対象の金額そのものが系統的に過少」という記帳の正確性の問題なので、
金額の大小と関係なく backlog に登録する ([step4b-backlog.md](step4b-backlog.md))。

> **上の 2 文は 2026-07-25 に覆した。** 「索引化の前に実装しない」という判断は、
> 「今後のコスト削減でも必要」というユーザー裁定により撤回し、Phase 2 の前に H1 として実装した。
> 金額差 $0.1–0.4 は依然として小さいが、**レーンの有無は将来の全再索引のコストを半減させる**ため、
> 一度きりの節約額で判断すべきではなかった。
