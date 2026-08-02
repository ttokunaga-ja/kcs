# `/layout-parsing` の生応答キャプチャ

PaddleOCR-VL が実際に返したバイト列。**整形も切り詰めもしていない。**
`curl` の出力をそのまま置いてある (compact JSON、末尾に改行なし、CR なし)。

置いてある理由は、mock がサービスに 3 回続けて食い違い (応答の封筒 / 図の綴り /
末尾 LF)、**3 回とも CI が緑のままだった**ため。mock とコードが互いに同意し、
サービスだけが両方と食い違っていた。実物があれば、その系統を閉じられる。

## 採取条件 (2026-08-03)

| | |
|---|---|
| Pipeline | `paddleocr-vl:latest-nvidia-gpu-offline` <br> `sha256:6c735bdf9e758ffdd58ccc067db0c2d84e37e5e6a2cbd47156069d4d7ea5d709` |
| VLM backend | `paddleocr-genai-vllm-server:latest-nvidia-gpu-offline` <br> `sha256:d0d32c04a2119613d25a0a4c292e165ccc107954b74580613cf59e378037f8f5` |
| 重み | `PaddleOCR-VL-1.6` / `model.safetensors` `sha256:85a479d5…71db` |
| ハード | RTX 4070 / WSL2 |

リクエストボディは **Kio の `EnvLocalOcrClient` が送るものと同一**:

```json
{"file": "<base64>", "fileType": 1, "useLayoutDetection": true}
```

**可視化オプションは付けていない。** Kio が投げない要求への応答を fixture にすると、
また「サービスと違う形」を固定することになるため。なお `inputImage` と
`outputImages.layout_det_res` は**既定で応答に載ってくる**ので入っている
(これがサイズの大半を占める)。

> `base64 -w0` の結果を `-d "$(...)"` でシェル引数に渡すと ARG_MAX を超えるので、
> ボディはファイルに書いて `--data-binary @file` で送った。ワイヤ上のバイトは同じ。

## 入力

すべて**リポジトリ内の合成画像** (`experiments/ocr-verification/fixtures/generated-images/`)。
公開済み・再現可能で、社内文書は使っていない。

| ファイル | 入力画像 | サイズ |
|---|---|---:|
| `infographic-two-charts.json` | `g5_infographic_high_01.png` | 1,472,174 B |
| `invoice-table.json` | `g4_invoice_photo_03.png` | 1,117,633 B |
| `slide-single-figure.json` | `g2_slide_dense_02.png` | 1,285,842 B |

## 中身の要点

| | infographic | invoice | slide |
|---|---|---|---|
| block 数 | 48 | 6 | 13 |
| `chart` | **2** | 0 | 1 |
| `table` | 0 | **1** | **2** |
| `image` | 多数 (アイコン) | 1 | 8 |
| `markdown.text` の生 HTML | `div` / `img` | `div` / `img` / **`table` `tr` `td`** | `div` / `img` / **`table` `tr` `td`** |
| GFM のパイプ表記 | 無し | 無し | 無し |
| 末尾 LF | **1** | **0** | **1** |

**表は必ず HTML で来る。** GFM のパイプ記法は 1 本も現れない。したがって
`table` を含むページは 07 §5 の生 HTML 禁止に触れ、offline 経路が拒否する
(意図した挙動 — 計画書 §9 の S3-F)。

**末尾 LF は 0 / 1 の両方が出る** (別の機会には 2 も観測している)。
07 §5.2.1 はちょうど 1 個を要求するので、`normalize_to_markdown_v1` を
最後に掛ける処理 (`d66d063`) はここでも必要になる。

> ⚠ **`slide-single-figure.json` は名前どおりではない。** 由来の
> `g2_slide_dense_02.png` には `table` が **2 つ**と `chart` が 1 つ入っており、
> 「図が 1 つだけのページ」ではない。単一図のケースが要るなら別の画像で
> 採り直すこと。名前は依頼された通りにしてある。
