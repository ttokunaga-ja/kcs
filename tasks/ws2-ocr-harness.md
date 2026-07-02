# WS2 発注書: Mistral OCR 実地検証ハーネス (設計宿題 #6)

## 目的

`docs/09-mvp-scope.md` §5.5 宿題 #6 / `docs/07-adapter-spec.md` §5.2 リスク注記の実地検証を可能にする検証ハーネスを実装する。検証観点: **複雑表・日本語・数式の変換品質、画像抽出、Batch API 実挙動、コスト実測**。

## 必読

- `docs/07-adapter-spec.md` §5.2 (標準 Adapter 規約: table inline / include_image_base64 / bbox は metadata)
- `docs/research/markdown.md` (選定の経緯・単価)
- `docs/09-mvp-scope.md` §4.1 (基準データセット D1 とコスト予実)

## 成果物 (`experiments/ocr-verification/` 配下)

```text
pyproject.toml               # Python 3.12+, uv 互換。deps: mistralai (公式 SDK), reportlab 等最小限
README.md                    # セットアップ / 実行手順 / API キーの扱い (コミット禁止を明記)
fixtures/generate_fixtures.py  # 合成 PDF + ground truth (JSON) 生成
run_ocr.py                   # OCR 実行 (sync / batch 両モード)
evaluate.py                  # ground truth 比較 → results.json + report.md
```

## fixtures 要件 (合成 PDF、ground truth 付き)

1. 複雑表 (結合セル・数値列・罫線あり) — セル内容の ground truth JSON
2. 日本語本文ページ (横書き必須) — 全文 ground truth
3. 数式を含むページ (画像化した数式で可)
4. 埋め込み画像 (図) を含むページ — 画像数の ground truth

## run_ocr.py 要件

- `MISTRAL_API_KEY` は環境変数のみ。model = `mistral-ocr-latest`、**応答中の実モデル名を必ず記録**
- sync / batch 両モード (`--mode sync|batch`)。`include_image_base64=true`、表は inline (table_format null 相当)
- 記録: レイテンシ / ページ数 / 公称単価による推定コスト (OCR 4: API $4, Batch $2 per 1,000 pages) / 生応答 JSON (`out/`)
- `--dry-run`: API キー不要のモック応答で end-to-end が通ること

## evaluate.py 要件 (暫定合格基準 — report.md に明記、最終判断は人間)

```text
表セル一致率        >= 0.95
日本語 CER          <= 0.02
画像抽出数の一致    100%
数式               テキスト化 or 画像 fallback かを判定・記録 (合否基準なし)
```

## 制約

- API キー・応答内の資格情報をリポジトリに残さない。`out/` は .gitignore
- `docs/` を変更しない。ネットワーク呼び出しは run_ocr.py の非 dry-run 時のみ

## 受け入れ条件

```bash
cd experiments/ocr-verification
python fixtures/generate_fixtures.py
python run_ocr.py --dry-run
python evaluate.py --dry-run     # キー無しで全て成功すること
```

完了後、このブランチ (`ws2-ocr-harness`) にコミットすること。実 API での実行はリポジトリ所有者が行う。
