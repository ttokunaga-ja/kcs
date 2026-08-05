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

`…-as-pdf.json` だけは `"fileType": 0` (PDF)。理由は下の「PDF 入力」を参照。

**可視化オプションは付けていない。** Kio が投げない要求への応答を fixture にすると、
また「サービスと違う形」を固定することになるため。なお `inputImage` と
`outputImages.layout_det_res` は**既定で応答に載ってくる**ので入っている
(これがサイズの大半を占める)。

> `base64 -w0` の結果を `-d "$(...)"` でシェル引数に渡すと ARG_MAX を超えるので、
> ボディはファイルに書いて `--data-binary @file` で送った。ワイヤ上のバイトは同じ。

## 入力

すべて**リポジトリ内の合成画像** (`experiments/ocr-verification/fixtures/generated-images/`)。
公開済み・再現可能で、社内文書は使っていない。

| ファイル | 入力画像 | `fileType` | サイズ |
|---|---|---|---:|
| `infographic-two-charts.json` | `g5_infographic_high_01.png` | 1 (image) | 1,472,174 B |
| `invoice-table.json` | `g4_invoice_photo_03.png` | 1 (image) | 1,117,633 B |
| `slide-single-figure.json` | `g2_slide_dense_02.png` | 1 (image) | 1,285,842 B |
| `infographic-two-charts-as-pdf.json` | 同上を 150 dpi で PDF 化 | **0 (pdf)** | 1,279,343 B |

## PDF 入力 (2026-08-05 追加)

`infographic-two-charts-as-pdf.json` は**同じ画像を PDF に包んで投げた応答**。
上の 3 本はすべて `fileType: 1` なので、**PDF 応答の形はどれも押さえていなかった**。

`dataInfo` の形が違う。ページ寸法が配列の中へ移り、`numPages` が増える:

```json
image: {"width":1024,"height":1536,"type":"image"}
pdf  : {"numPages":1,"pages":[{"width":984,"height":1475}],"type":"pdf"}
```

**中身も同一ではない。**PDF 経路は 150 dpi でラスタライズし直すため寸法が
1024×1536 → 984×1475 に変わり、レイアウト検出の結果もわずかにずれる:

| | image 入力 | pdf 入力 |
|---|---:|---:|
| block 数 | 48 | **49** |
| クロップ数 | 20 | **21** |
| `markdown.text` 中の `<img>` | 19 | **20** |
| `chart` | 2 | 2 |

同じ文書でも**入れ方が変われば検出数が変わる**。決定性が保証されるのは
「同じバイト列を同じ経路で投げたとき」までで、それ以上ではない。

### ずれるのは座標だけではない — 可視テキストも変わる

上の表は件数だけを並べているが、**読める文字列そのものが変わる**。
`Risk: medium` は image 経路では見出しに 1 回だけ現れるのに対し、
**pdf 経路では見出しと本文の両方に現れて 2 回になる**:

```
image: ('paragraph_title', 'Risk: medium')  ('text', 'Potential text loss in images')
pdf  : ('paragraph_title', 'Risk: medium')  ('text', 'Risk: medium\nPotential text loss\nin images')
```

別の `footer` では改行位置が変わる (image は `...detected.\nOCR output`、
pdf は `...detected. OCR output`)。

**これは chunk の中身が変わるということである。**箱がずれるだけなら
`related_images` の当たり所の話で済むが、テキストが変われば検索の対象と
埋め込みの入力が変わる。同じ 1 枚の絵でも、**PNG で入れたか PDF に包んだかで
索引の中身が違う**ものになり、しかもどちらも「正しい OCR 結果」である。

> **07 §9 の first-instance-wins は、ここでは助けにならない。**あれは同じ
> content-addressed object に対する規則であり、PNG とそれを包んだ PDF は
> raw hash が違うので**別の object になる**。したがって片方が凍結されるのでは
> なく、**両方が索引に入り、同じ文書について食い違う読み方が 2 つ並ぶ**。
> 「PDF に包んでから入れる」といった前処理は、体裁の問題ではなく索引の
> 中身を決める選択になる。

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

**表は必ず HTML で来る。** GFM のパイプ記法は 1 本も現れない。**この 3 本が、
表を拒否するのをやめる根拠になった** — 07 §5 は元から表を GFM 記法と定めており、
足りていなかったのは「PaddleOCR-VL が何を送るか」の実測だけだったからである。
2026-08-06 から `convert_html_tables_to_gfm` がこの形を変換する (計画書 S3-L)。

> **形はここで確定している** — `border=1` / `<tr>` / `<td style='…'>` の 3 要素だけで、
> `rowspan` も `colspan` も `<th>` も入れ子も、3 本 11 行 38 セルに 1 つも無い。
> 変換するのはこの形だけで、外れたものは今までどおり拒否される。
>
> **見出し行は空にする。**invoice と slide 右の先頭行は見出しだが、**slide 左の
> 先頭行は本文**である (アイコン + `High text density` + 説明文)。`<th>` が無いので
> 応答からは区別できず、先頭行を昇格させると 3 本に 1 本で本文が列名として
> 07 §9 に凍る。これも「1 ページで成立した規則が次で成立しない」型である。

> ⚠ **採取直後は、そこへ到達すらしていなかった。**この 3 本は当時、生 HTML の
> 検査より前に `pair_images_with_boxes` の件数チェックで拒否されていた
> (19 参照/20 画像、1 参照/2 ボックス、11 参照/13 画像)。**表を 1 つも含まない
> infographic すら拒否されていた**ので、「表だから拒否される」という上の説明は
> 当時の挙動としては誤りだった。原因はペアリングの前提が実データで成り立たない
> ことで、`markdown.images` は figure ブロックと 1:1 の集合ではなく、
> **ネストした切り出しも含む全クロップの平坦な袋**である。
>
> `44842bd` の後に、各画像の**ファイル名が持つ bbox**
> (`img_in_<label>_box_<x0>_<y0>_<x1>_<y1>`) を読む方式へ直した。いまは 3 本とも
> パーサを通る。この訂正自体が、キャプチャを置いた理由の実例である。
> (その後 2026-08-06 に表の変換が入り、**3 本とも索引まで通る**ようになった。
> 拒否されていた期間に測れたのは「拒否の理由が 2 度とも思っていたのと違った」
> ことで、それがキャプチャの仕事だった。)

**末尾 LF は 0 / 1 の両方が出る** (別の機会には 2 も観測している)。
07 §5.2.1 はちょうど 1 個を要求するので、`normalize_to_markdown_v1` を
最後に掛ける処理 (`d66d063`) はここでも必要になる。

> ⚠ **`slide-single-figure.json` は名前どおりではない。** 由来の
> `g2_slide_dense_02.png` には `table` が **2 つ**と `chart` が 1 つ入っており、
> 「図が 1 つだけのページ」ではない。単一図のケースが要るなら別の画像で
> 採り直すこと。名前は依頼された通りにしてある。
