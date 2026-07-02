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

## 出力

```text
fixtures/generated/kcs_ocr_verification.pdf
fixtures/generated/ground_truth.json
out/raw_response.json
out/ocr_response.json
out/results.json
out/report.md
```

評価の暫定合格基準は `evaluate.py` が生成する `out/report.md` にも明記されます。

