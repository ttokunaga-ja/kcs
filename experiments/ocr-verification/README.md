# Mistral OCR verification harness

`docs/09-mvp-scope.md` の設計宿題 #6 用に、Mistral OCR の複雑表、日本語、数式、画像抽出、Batch API、コスト見積もりを実地検証するための最小ハーネスです。

## セットアップ

Python 3.12 以上を使います。`uv` を使う場合:

```bash
cd experiments/ocr-verification
uv venv --python 3.12
uv pip install -e .
```

`uv` を使わない場合:

```bash
cd experiments/ocr-verification
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

**fixture 生成には reportlab (CID フォント) が必須です。** 最小 PDF writer によるフォールバックはテキスト層のみで日本語グリフを描画できないため、実 OCR の品質評価には使えません (Mistral OCR はレンダリング画像を読むため、日本語・表の評価が無意味になります)。フォールバックは `--allow-fallback` を明示した場合のみ許可され、dry-run のパイプライン確認専用です。

**系統 A/B/C (下記) には reportlab に加えて Pillow と CJK 対応 TrueType/TTC フォントが必要です。** CJK フォントが見つからない環境では A/B/C を自動 skip し (警告を表示)、既存 0-6 ページのみ生成します (`ground_truth.json` からも A/B/C セクションは省かれ、`evaluate.py` は graceful に読み飛ばします)。macOS はヒラギノ角ゴシック、Linux は Noto Sans CJK 等を探索します (`generate_fixtures.py` の `CJK_FONT_CANDIDATES`)。

## API キー

実 API 実行時だけ `MISTRAL_API_KEY` を環境変数で渡します。

```bash
export MISTRAL_API_KEY="..."
```

API キーをファイル、README、スクリプト、Git 管理対象に書き込まないでください。`out/` と `fixtures/generated/` は `.gitignore` 済みです。実 API の応答 JSON も `out/` 配下だけに保存します。

## Dry-run

API キー不要で end-to-end を確認します。

```bash
cd experiments/ocr-verification
python fixtures/generate_fixtures.py                  # 依存インストール済みの場合
python fixtures/generate_fixtures.py --allow-fallback # reportlab 無しの環境 (fixture は実検証に使用不可)
python run_ocr.py --dry-run
python evaluate.py --dry-run
```

## 実 API 実行

同期 OCR:

```bash
python run_ocr.py --mode sync
python evaluate.py
```

Batch OCR:

```bash
python run_ocr.py --mode batch --poll-interval-seconds 10 --timeout-seconds 1800
python evaluate.py
```

`run_ocr.py` は `model="mistral-ocr-latest"` で呼び出し、応答中の実モデル名を `out/ocr_response.json` の `resolved_model` に記録します。`include_image_base64=true` を指定し、表は `table_format=None` で Markdown 本文 inline にします。

## 拡張 fixture: 系統 A/B/C (画像化・手書き・境界調査)

既存 0-3 (text-native) と 4-6 (WS-ocr-figures: raster 図表) に加え、以下 3 系統を index 7-17 に追加しています。いずれも **全面 raster + text layer なし** の PDF ページ (PIL でレンダリングした PNG を全面配置し、テキストを一切描かない) で、メタデータからテキストは抽出できません。よって「OCR が rendered image を読むか」を直接測れます。全ページ 200DPI 相当 (A4 = 1654x2339px)、フォント固定 + seed 固定 Random のみ使用で **2 回生成しても byte 一致** します。

- **系統 A — メタデータからテキストが取得できない PDF** (index 7-9): text-native ページ (表 / 日本語 / 数式) を PIL でラスタ画像にし、その画像だけを埋め込んだページ。ground truth は既存 fixture 0-2 の元テキストを流用。`evaluate.py` は per-page で cell recall / 日本語 CER→recall / formula token recall を測ります (診断のみ、pass 閾値なし)。
- **系統 B — 手書き風ページ** (index 10-11): フォント依存を避け、文字ごとに回転 (±6°)・ベースライン上下ゆらぎ・字間ゆらぎ・線の太さゆらぎを加えた手書き風レンダリング。買い物リスト / 会議メモ (日本語+英数字)。`evaluate.py` は既知トークンの recall を測ります (診断のみ)。
- **系統 C — 画像化境界の段階調査 (最重要)** (index 12-17): ラスタ化テキストページに段階的に表・グラフを足す C0..C5。図 / 表 / 本文それぞれに一意トークン (例: `C3-FIG-AXIS-61`) を埋め、`evaluate.py` が「どのトークンが markdown 本文に出たか / images[] に消えたか」を段階別 (body/table/figure zone 別) に測り、recall が急落する **『画像化境界』を機械判定** して `boundary-report.md` に出力します。

| stage | 内容 |
| --- | --- |
| C0 | ラスタ化した純テキスト (ベースライン) |
| C1 | テキスト + 小さな罫線表 (2x3) |
| C2 | テキスト + 大きめの数値密な表 |
| C3 | テキスト + 折れ線グラフ (軸/凡例/値ラベル) |
| C4 | テキスト + 棒グラフ + 表 (ダッシュボード風) |
| C5 | グラフ主体・テキスト僅少 (インフォグラフィック風) |

境界判定: 段階間で stage token recall が `BOUNDARY_DROP_DELTA` (0.25) 以上落ちた最大の段階を境界 (`sharp_drop`)、急落が無ければ recall が `BOUNDARY_RECALL_FLOOR` (0.5) を最初に割った段階 (`below_floor`) とします。

## 生成画像検証 (Codex APP 納品の曖昧画像 15 枚)

`fixtures/generated-images/` に納品された曖昧画像 15 枚 (`g1_*.png`〜`g5_*.png`) と
`ground-truth.json` を、実 API OCR で採点できるようにハーネスへ統合したものです。上記の
合成 fixture (18 ページ) とは **別 PDF・別 ground truth・別出力先** で、評価は混ざりません。

- 系統 (family): G1 UI/エディタ, G2 スライド, G3 ホワイトボード, G4 写真書類, G5 インフォグラフィック
- 各画像は `tokens` (一意トークン)・`visible_text`・`expect` (`text-dominant` / `mixed` / `image-dominant`) を持つ

> **`ground-truth.json` を一括置換の対象にしないこと。**
> `visible_text` は「画像の**画素に描かれている文字**」の写しであり、プロダクトの現在名ではありません。
> 画像は 2026-07 の旧名時点で生成されており、`g1_terminal_02.png` には `$ kcs verify --ocr`、
> `g4_receipt_photo_01.png` には `担当 KCS` が**画素として焼き込まれています**。
> ここを新名へ書き換えると、OCR が正しく読めた場合に不一致と採点され、**採点が静かに壊れます**
> (KCS→Kio リネーム時に実際に混入し、画像を目視して復元しました)。
> 名前を変えたい場合は ground truth ではなく**画像を再生成**してください。

### 1. PDF と ground truth を生成

```bash
cd experiments/ocr-verification
python fixtures/build_images_pdf.py
```

`generated-images/*.png` を **ファイル名昇順で 1 ページ 1 画像** の PDF
(`fixtures/generated/generated_images.pdf`) にまとめ、ハーネス互換の ground truth
(`fixtures/generated/generated_images_ground_truth.json`, `schema_version 1`, `dataset: generated-images`)
を書き出します。reportlab `invariant=True` + 納品 PNG のみ埋め込みで **2 回生成しても byte 一致** します。

### 2. Dry-run (API キー不要)

```bash
python run_ocr.py --fixture generated-images --dry-run
python evaluate.py --fixture generated-images --dry-run
```

### 3. 実 API 実行

```bash
# 同期 (15 ページ ≈ $0.06)
python run_ocr.py --fixture generated-images --mode sync
python evaluate.py --fixture generated-images

# Batch (15 ページ ≈ $0.03)
python run_ocr.py --fixture generated-images --mode batch --poll-interval-seconds 10 --timeout-seconds 1800
python evaluate.py --fixture generated-images
```

`--fixture generated-images` は ground truth を `generated_images_ground_truth.json`、出力先を
`out/generated-images/` に自動設定します (`--ground-truth` / `--out-dir` で個別上書き可)。

### 評価内容

`out/generated-images/report.md` に、画像 (=ページ) ごとに (i) 埋め込みトークンが markdown
本文に出たか、(ii) `visible_text` の正規化トークン回収率、(iii) `images[]` として返ったか、を測り、
**family 別集計**と **`expect` との突合表 (expect × observed のクロス集計)** を出力します。観測分類は
visible recall による診断ヒューリスティック (recall ≥ 0.7 → text-dominant, < 0.3 → image-dominant,
それ以外 mixed) で、合格閾値ではありません (`passed: null`)。

出力:

```text
fixtures/generated/generated_images.pdf
fixtures/generated/generated_images_ground_truth.json
out/generated-images/raw_response.json
out/generated-images/ocr_response.json
out/generated-images/results.json
out/generated-images/report.md
```

## 出力

```text
fixtures/generated/kio_ocr_verification.pdf
fixtures/generated/ground_truth.json   # schema_version 3 (figures / rasterized_text / handwriting / staged_boundary)
out/raw_response.json
out/ocr_response.json
out/results.json
out/report.md                          # 系統 A/B/C の診断セクションを含む
out/boundary-report.md                 # 系統C 境界調査レポート (staged_boundary がある時のみ)
```

評価の暫定合格基準は `evaluate.py` が生成する `out/report.md` にも明記されます。系統 A/B/C はいずれも診断メトリクス (`passed: null`) で、overall pass/fail には影響しません。

