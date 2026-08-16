# Archive: OCR 境界調査用の曖昧画像 fixture 生成

> この作業は完了済みの履歴であり、現在の実行手順ではない。生成済み画像と
> ground truth は non-authorizing archive で、Rust evaluator が暗黙に探索しない。

## 目的

Mistral OCR の「テキストとして OCR されるか / image として返されるか」の境界調査
(`tasks/step3-ocr-figures.md`、`experiments/ocr-verification/`) に使う **曖昧画像 fixture** を
ImageGeneration で作成する。合成描画 (PIL) では作れない「実態はテキストだが見た目は画像」の
リアルなサンプルが対象。

## 生成する画像 (各 2-4 枚、計 15-20 枚)

| 系統 | 内容 | 例 |
|---|---|---|
| G1 | **実態はテキストの画像** | コードエディタのスクリーンショット風、ターミナル出力風、チャット画面風 (日本語+英語) |
| G2 | **プレゼン資料の 1 ページ風** | タイトル + 箇条書き + 図が混在するスライド。文字量多め/少なめの 2 段階 |
| G3 | **ホワイトボード / 手書きメモ風** | 手書き文字 + 矢印 + 簡単な図。日本語含む |
| G4 | **文書写真風** | 紙の書類を斜めから撮影したような領収書・回覧文書風 (影・歪みあり) |
| G5 | **インフォグラフィック** | 数値・ラベル・アイコンが密に混在。テキスト比率 高/中/低 の 3 段階 |

## 必須要件

1. **既知トークンの埋め込み**: 各画像の描画テキスト内に一意トークンを必ず含める —
   形式 `G<系統>-<連番>-TOKEN-<4桁>` (例: `G2-01-TOKEN-7315`)。後段の Rust evaluator が
   「このトークンが OCR 結果の markdown に出たか」で判定するため、**画像内に視認可能な文字として**
   描かれていること (プロンプトに明記して生成後に目視確認)
2. **ground truth の記録**: `experiments/ocr-verification/fixtures/generated-images/ground-truth.json` に
   1 画像 1 エントリで保存:
   ```json
   {"file": "g2_slide_dense_01.png", "family": "G2", "tokens": ["G2-01-TOKEN-7315"],
    "visible_text": "画像内に描かれた全テキストの書き起こし",
    "expect": "text-dominant | mixed | image-dominant"}
   ```
   `visible_text` は生成後に**目視で書き起こす** (生成プロンプトの写しではなく実際に描画された文字)
3. **配置**: `experiments/ocr-verification/fixtures/generated-images/*.png` (ファイル名は
   `g<系統>_<内容>_<連番>.png` 小文字 snake)。PDF 化は不要 (ハーネス側で画像→PDF 変換を行う)
4. 生成できなかった/文字が崩れた画像は破棄して再生成し、最終的に**全トークンが視認可能**な
   セットのみ納品。文字化けや存在しないグリフが混ざった画像は不可
5. 完了報告: 系統別枚数、ground-truth.json のエントリ数、目視確認の結果 (トークン視認性)。
   git commit はせず working tree に置く (コミットは発注側が検収後に行う)

## 背景 (読むと精度が上がる)

- `tasks/step3-ocr-figures.md` — 図画像化問題の調査報告と診断メトリクス
- `experiments/ocr-verification/README.md` — ハーネスの使い方
- 懸念: Mistral OCR は PDF ページをレンダリングして処理するため、図・スキャン・写真領域を
  images[] として返し、その中のテキストが検索対象から漏れる可能性がある。この fixture は
  「見た目は画像だが実態はテキスト」の曖昧領域で境界を測るためのもの
