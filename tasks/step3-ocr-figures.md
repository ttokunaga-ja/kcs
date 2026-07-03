# WS-ocr-figures: Mistral OCR の図・チャート品質リスク調査

- 担当: WS-ocr-figures
- 日付: 2026-07-03
- 対象懸念 (ユーザー提起): Mistral OCR は PDF ページを画像レンダリングして処理するため、図・チャート・複雑レイアウト領域を `images[]` + placeholder として返し、本来テキスト/表として Markdown 化されるべき内容が**画像化されて欠落**する恐れ。KCS では image は CAS 保存 + `kcs://` URI 置換されるが、**画像内テキストは FTS/embedding の検索対象にならない** → 北極星 M3-1 (検索可能性) に直接影響。
- 変更範囲: `experiments/ocr-verification/` 配下の拡張と本ファイルのみ。`docs/` `crates/` は未変更。実 API は未実行 (fixture 生成の決定論性のみローカル検証)。

---

## 0. 結論 (懸念の実在性判定)

**判定: 条件付きで実在。** 根拠:

1. Mistral OCR は text-native なベクタ内容 (表・数式・日本語本文) は正しく textize する (既存 4 ページ fixture で実測済み: 表セル 17/17、CER 0.0)。**懸念が成立するのは「ラスタとして埋め込まれた図表・インフォグラフィック・スキャン領域」に限定**され、その領域の文字が `images[]` + placeholder に押し込まれると markdown 本文に出ず検索から落ちる。
2. 一次/二次情報とも「ラスタ図表内テキストが本文へ OCR されるか」は**ケース依存で保証がない** (Cohorte deep-dive は「図中テキストは画像参照として保持され本文化されない傾向」、別の実測報告は「ラベルは抽出できたが画像片を 1 つ取りこぼした」)。つまり杞憂ではないが常時発生でもない → **測って初めて分かる**。本 WS はその測定器 (fixture + 評価観点) を用意した。

補足の重要事実: `mistral-ocr-latest` は 2026-06-23 リリースの **Mistral OCR 4** を指す (ハーネスは `mistral-ocr-latest` を要求するので実検証対象は OCR 4)。懸念文の `mistral-ocr-2505` は旧世代。OCR 4 は各ブロックを typed + bbox + confidence 付きで返すため、`images[]` 比率や block type で図領域を機械判定しやすくなっている (対策 (ii) の前提)。

---

## 1. 実挙動の調査結果 (Web / 一次情報)

### 1.1 どの領域が `images[]` として返るか

- Mistral OCR は**埋め込み画像を抽出**し、markdown 中では placeholder (`![img-0.jpeg](img-0.jpeg)`) に置換、`pages[].images[]` に `id` / bbox (`top_left_x/y`, `bottom_right_x/y`) / `image_base64` (with `include_image_base64=true`) を返す ([basic_ocr docs](https://docs.mistral.ai/studio-api/document-processing/basic_ocr))。
- 対象は「図・チャート・写真・インフォグラフィック等、レイアウト分類器が figure/image と判定した領域」。**ベクタの表・数式・本文はテキスト化される** (既存 fixture 実測と一致)。「どの基準で image vs text を分けるか」は公式に明文化されていない → 経験的に測る必要あり ([basic_ocr docs](https://docs.mistral.ai/studio-api/document-processing/basic_ocr))。

### 1.2 image 内テキストの OCR は行われるか

- 公式ドキュメントは「figure 内テキストを本文へ OCR するか」を明示していない ([basic_ocr docs](https://docs.mistral.ai/studio-api/document-processing/basic_ocr))。
- 二次情報は割れている:
  - Cohorte の hands-on は「数式や図はテキスト変換されず**画像参照として保持される傾向**」と報告 ([Cohorte deep-dive](https://cohorte.co/blog/mistral-ocr-a-deep-dive-into-next-generation-document-understanding))。
  - 別の実測 (Medium) は「2 枚のラベル付き植物図で、**ラベルは完璧に抽出**したが画像片を 1 つ取りこぼした」= 図の**近傍テキストは拾うが図そのものの扱いは不安定** ([derperdoing Medium](https://derperdoing.medium.com/ocr-with-image-clippings-embedded-in-the-output-using-mistral-ai-61882b4163cd))。
- 低品質スキャンは「300DPI 以上を推奨、ノイズは前処理でコントラスト調整」= 解像度が低いと欠落リスク増 ([Cohorte deep-dive](https://cohorte.co/blog/mistral-ocr-a-deep-dive-into-next-generation-document-understanding))。

→ **本 WS の fixture (ラスタ棒グラフ / スキャン風全面ラスタ / インフォグラフィック) はこの未確定点を直接測るためのもの。**

### 1.3 annotation 機能 (2025 追加 → OCR 4 でも提供) で図領域の説明文を生成できるか

一次情報 ([Document Annotations docs](https://docs.mistral.ai/capabilities/document_ai/annotations)):

- **`bbox_annotation`** (パラメータ `bbox_annotation_format`): OCR が抽出した各 bbox (チャート/図等) を、ユーザ指定の JSON Schema (Pydantic/Zod/JSON) で注釈する。スキーマ例は `image_type` / `short_description` / `summary`。**図のキャプション/説明、さらに図中テキストの書き起こしを要求できる**。**ページ上限なし** (全 bbox を個別処理)。
- **`document_annotation`** (パラメータ `document_annotation_format` / `document_annotation_prompt`): 文書全体を 1 スキーマで注釈。**先頭 8 個の image bbox / 8 ページまで**の制約あり。
- annotation は OCR 後の**追加の vision-LLM パス**であり生成物 (= 非決定的)。→ KCS の identity `(raw_hash, tool_profile_hash)` に annotation スキーマ+プロンプトを `tool_profile_hash` へ織り込む必要 (docs 判断事項)。

### 1.4 コスト (対策のトレードオフ用)

- OCR only: **$4 / 1,000 ページ** (sync)、**$2 / 1,000** (Batch, 50% 引き)。
- **annotations 付き: $5 / 1,000 ページ** (OCR only 比 +25%、annotated ページのみ) ([Mistral pricing](https://mistral.ai/pricing/))。
- 参考: 複雑文書のベンチで VLM 系 (Gemini Flash) が図表理解で優位という報告 (Mistral OCR は構造化表で強いが、ある複雑文書ベンチで Gemini 2.0 Flash 比 -43.4% 精度) → 図領域の二次処理に生成 LLM (Gemini) を当てる対策 (ii)(iii) の根拠 ([Reducto benchmark](https://reducto.ai/blog/lvm-ocr-accuracy-mistral-gemini))。

---

## 2. 既存ハーネスのギャップ確認

`experiments/ocr-verification/fixtures/generate_fixtures.py` の旧 fixture (4 ページ: 複雑表 / 日本語 / 数式 / **1 枚の埋め込み小画像**) は:

- 埋め込み画像を「1 枚あるか (count)」しか見ておらず、**その画像内テキストが本文に出るか (= 検索可能性)** を全く検証していない。
- 図中ラベル / スキャン風全面ラスタ / インフォグラフィックのケースが無い。

→ 本懸念 (画像化による本文欠落) は**旧 fixture では検出不能**。よって図表系ページと評価観点を追加した。

---

## 3. fixture 拡張の内容 (実装済み)

`generate_fixtures.py` に**診断ページ 3 枚 (index 4-6) を追加** (reportlab 経路のみ。ラベルは全て ASCII で PIL 同梱 default TrueType のみに依存 = CJK フォント不在でも決定論的・可搬)。ラスタは PIL (Pillow) で描画し reportlab に `drawImage` で埋め込む。

| index | kind | 内容 | 画像内既知ラベル (欠落検出用) |
| ---: | --- | --- | --- |
| 4 | `raster_chart` | ラスタ棒グラフ (タイトル/カテゴリ/数値ラベルが画像内テキスト) | `REVENUE BY DEPT 2026Q1`, `Tokyo`, `Osaka`, `Nagoya`, `1250`, `980`, `760`, `Total 2990` |
| 5 | `scan_page` | ページ全体を 1 枚のラスタにしたスキャン風テキスト | `KCS SCAN FIXTURE PAGE`, `ALPHA-7731`, `BRAVO-2048`, `CHARLIE-9152`, `returned only as an image` |
| 6 | `infographic` | パイプライン概要インフォグラフィック (ボックス内テキスト) | `KCS PIPELINE OVERVIEW`, `Ingest`, `Markdownize`, `Embed`, `Index`, `Search`, `42 percent uplift` |

- `ground_truth.json` は `schema_version: 2`、`page_count: 7`、新規 `figures` セクション (各ページの `kind` / `expected_label_texts` / `risk`) を追加。旧 4 ページのセクションは不変 (既存の合格判定はそのまま維持)。
- 各図表ページには日本語見出し (実ベクタテキスト) を別途置き、「常に取れるべき実テキスト」と「画像内テキスト」を分離。
- **決定論性をローカル検証済み**: reportlab を `invariant=True` にし CreationDate / doc ID を固定。`generate_fixtures.py` を 2 回実行して PDF (`sha256=47294bed…`) と `ground_truth.json` が**バイト一致**、PIL PNG ラスタも 2 回生成で**バイト一致**を確認。
- reportlab 不在の `--allow-fallback` (dry-run 専用) 経路では図表ページは生成せず `figures` も出さない (minimal writer はラスタ内テキストを描けないため)。評価側は `figures` 欠如を graceful skip。

---

## 4. evaluate.py 拡張の内容 (実装済み)

新関数 `evaluate_figures()` を追加 (`ground_truth.figures` が無ければ `None` で skip)。overall `passed` には**影響させない診断メトリクス** (formula と同様 `passed: None`)。

各図表ページで記録:

- **(a) `images[]` 数 と markdown placeholder 数の対応**: `images_count` / `placeholder_count` / `placeholder_matches_images`。
- **(b) 図中テキストの本文出現 (欠落検出)**: 既知ラベルが markdown 本文に現れる割合 = `label_recall` (`normalize_label` で NFKC/小文字/空白除去の緩い一致)、`missing_labels`。
- **(c) 本文テキスト欠落率**: ページ横断 `aggregate_label_recall` と `body_text_loss_rate = 1 - aggregate_label_recall`。
- **画像化疑いフラグ** `text_loss_suspected`: `label_recall < 0.5` かつ `images_count > 0` (本文へ OCR されず placeholder+image に押し込まれた兆候)。閾値 `FIGURE_TEXT_LOSS_WARN = 0.5`。

`out/report.md` に "Figures (WS-ocr-figures diagnostic)" セクション (ページ別表 + 欠落ラベル一覧) を出力。

dry-run のモック応答 (`run_ocr.py` `build_mock_figure_pages`) は評価器を通すための**説明用合成**で、実挙動の主張ではない。意図的に 3 段階 (raster_chart=欠落 recall 0 / scan_page=完全 recall 1.0 / infographic=部分 recall 0.57) を作り、評価器が欠落/完全/部分を弁別することを dry-run で確認済み (下記)。

```
## Figures (WS-ocr-figures diagnostic)
- Aggregate in-figure label recall: 0.45
- Body-text loss rate: 0.55
- Pages with text-loss suspected: 1/3
| page | kind | images[] | placeholders | match | label recall | loss? |
| 4 | raster_chart | 1 | 1 | yes | 0.0 (0/8)      | YES |
| 5 | scan_page    | 0 | 0 | yes | 1.0 (5/5)      | no  |
| 6 | infographic  | 1 | 1 | yes | 0.571 (4/7)    | no  |
```

---

## 5. ユーザーが実行すべき実 API 検証コマンド

```bash
cd experiments/ocr-verification

# 1. 依存 (mistralai + reportlab + pillow)。図表 fixture には reportlab/pillow が必須。
python -m pip install -e .          # or: uv pip install -e .

# 2. 7 ページ fixture を再生成 (図表 index 4-6 を含む)。決定論。
python fixtures/generate_fixtures.py

# 3. API キー (ファイル/スクリプトに書かない)
export MISTRAL_API_KEY="..."

# 4. 実 OCR (sync) — baseline (annotations 無し)
python run_ocr.py --mode sync
python evaluate.py
#   → out/report.md の "Figures" セクションを見る。
#     判定の勘所: raster_chart / infographic で images_count>0 かつ label_recall が低い
#     (= text_loss_suspected: YES) なら懸念が実挙動として確認。
#     scan_page が recall 高なら「全面スキャンはページ本文として OCR される」= 杞憂側。

# 5. (任意) Batch モードでも同様に
python run_ocr.py --mode batch --poll-interval-seconds 10 --timeout-seconds 1800
python evaluate.py
```

注意:
- **`out/` `fixtures/generated/` は `.gitignore` 済み**。実 API 応答 (base64 画像含む) は `out/` 配下のみ。
- 現 `run_ocr.py` は **annotations 未対応** (baseline 測定に徹する)。対策 (i) bbox_annotation の効果測定は別実装 (§6 の follow-up)。
- 本 fixture のラスタ内テキストは ASCII。実運用の日本語ラスタ図表はさらに欠落しやすい可能性 → 実文書サンプルでの追試を推奨。

---

## 6. 対策の設計案と推奨順位 (実装はしない)

前提: KCS の image は既に CAS 保存 + `kcs://` URI 置換されるが、その**中身のテキストが検索対象外**なのが問題。対策は「図領域のテキスト/説明を検索対象 (FTS + embedding) に載せる」こと。

| # | 対策 | 効果 | コスト | 複雑性/リスク |
| --- | --- | --- | --- | --- |
| (0) | **まず測る** (本 WS の fixture+評価を実 API で回し、代表文書で `body_text_loss_rate` を定量化) | 以降の要否を決める | ほぼ無 ($0.028/7p) | なし |
| (i) | **Mistral `bbox_annotation`** で各 image bbox に `short_description` + **図中テキストの verbatim 書き起こし**を要求し、image object / unit metadata に格納 → FTS + embedding へ | 図の説明 + 図中文字を検索可能化。ページ上限なし。in-vendor で routing 追加不要 | annotated ページのみ **+25%** ($4→$5/1k) | 中: annotation は生成物 (非決定) → `tool_profile_hash` にスキーマ+プロンプトを織り込む要 (docs 判断)。verbatim 精度は未検証 |
| (ii) | **`images[]` 被覆率が閾値超のページを生成 LLM (Gemini) adapter (07 §8.2 代替系) へ page 単位 fallback** | 図表過多ページで高い回収 | 該当ページのみ Gemini vision 課金 | 高: 生成 LLM の Markdown 非決定性 (設計宿題) + routing + プロンプト規約が乗る |
| (iii) | 画像化された image object のみ **Gemini Vision で二次 Markdownize** (07 §5.2 の「OCR 後の図表解釈」に整合) | 図中テキストをピンポイント回収。ページ全体より安い | image 単位の少額課金 | 中〜高: image object への配線 + 生成 LLM 非決定性 |

### 推奨

- **MVP でやる**: **(0) 測定 (本 WS)** → 実 API で loss を定量化。loss が実質的なら **(i) bbox_annotation**（説明 + verbatim 書き起こし）を採用。理由: 最小複雑性・in-vendor・+25% のみ・M3-1 の検索可能性を直接回復。ただし annotation の非決定性を `tool_profile_hash` に反映する docs 追記が前提 (07 §5.2 / 03 identity)。
- **Phase 4+ に送る**: **(ii)/(iii) 生成 LLM (Gemini) fallback / 二次 Markdownize**。生成 LLM の Markdown 非決定性・プロンプト規約 (既存の設計宿題) と routing 複雑性を持ち込むため、(0) の測定で「(i) では不十分」と示された領域に限定して段階導入する。07 §5.2 の「検証が崩れた場合の fallback を維持」方針と一致。

### follow-up (実装タスク候補、本 WS 外)

1. `run_ocr.py` に `--annotations bbox` オプション追加 (`bbox_annotation_format` に `short_description` + `transcribed_text` スキーマ) → (i) の効果を同ハーネスで A/B 測定。
2. docs 反映 (別担当): 07 §5.2 に「図領域テキストの検索可能化 = bbox_annotation を第一手、生成 LLM fallback を Phase 4+」を追記。annotation の `tool_profile_hash` 織り込みを 03/07 に明記。

---

## 7. 出典 (Sources)

- [Mistral — Document Annotations (一次)](https://docs.mistral.ai/capabilities/document_ai/annotations)
- [Mistral — OCR Processor / basic_ocr (一次)](https://docs.mistral.ai/studio-api/document-processing/basic_ocr)
- [Mistral — OCR 4 発表 (一次, mistral-ocr-latest = OCR 4, 2026-06-23)](https://mistral.ai/news/ocr-4/)
- [Mistral — Pricing (一次, OCR $4/$2, annotations $5 per 1k)](https://mistral.ai/pricing/)
- [Cohorte — Mistral OCR deep dive (図中テキスト保持傾向・スキャン品質)](https://cohorte.co/blog/mistral-ocr-a-deep-dive-into-next-generation-document-understanding)
- [derperdoing (Medium) — image clippings 実測 (ラベルは抽出、画像片取りこぼし)](https://derperdoing.medium.com/ocr-with-image-clippings-embedded-in-the-output-using-mistral-ai-61882b4163cd)
- [Reducto — Mistral OCR vs Gemini Flash 精度ベンチ (複雑文書で VLM 優位)](https://reducto.ai/blog/lvm-ocr-accuracy-mistral-gemini)
