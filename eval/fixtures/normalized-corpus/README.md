# 正規化済みコーパス — 支払い済み OCR の恒久化

24 問ベースライン (`eval/golden-queries-fixture-b.jsonl`) が指す 1,015 文書の
**正規化済み本文**。`eval/v3/extract_normalized_corpus.py` が index 済み fixture
から取り出したもの。

## なぜ repo に置くのか

golden query の正解は 24 問中 **20 問が `.pdf` / `.docx` / `.pptx` / `.png`** で、
本文を得るには Markdownize (OCR) を通す必要がある。それは実費 **$1.21** を伴う。

この費用は**既に 2 回払われている** — 2026-07-24 と 2026-07-27。2 回目を払った
理由は、1 回目の成果物の在り処が記録から失われたためで、実際には失われて
いなかった (計画書が index 済み store の場所を誤記していた)。

本文だけなら **1.5 MB のテキスト**である。置いておけば

- V3b (MRL 768 の recall 実測) が **GPU だけで、無料で**回る
- 将来の再測定も無料になる
- 3 度目の支払いが構造的に起こり得なくなる

元の index (1.9 GB、`~/kio-dogfood/corpus-v1/corpus`) は `.kio` の object store と
sqlite に依存し、可搬でも commit 可能でもない。ここに要るのは本文だけである。

## 形

    corpus/<persona>/<scope path>/<元のファイル名>.md

元の拡張子を**残したまま** `.md` を足してある。golden query の
`expected[].path` (`corpus/p01/home/.../latency-review.docx`) と部分一致で
突き合わせるため — 拡張子を置き換えると当たらなくなる。

同一文書の chunk は `byte_start` 昇順で連結し、`gen` は最新のみを採っている
(複数世代を連結すると本文が重複する)。

## 使い方

```bash
python3 eval/v3/v3_mrl.py \
  --corpus eval/fixtures/normalized-corpus \
  --queries eval/golden-queries-fixture-b.jsonl \
  --out v3b-mrl.json
```

このコーパスなら **24/24 の query が正解を引ける**ので、`v3_mrl.py` の recall
ガードは発火せず、実際の recall@10 が両幅で出る。生のコーパス
(`~/kio-baseline-corpus`) では 0/24 になり、ガードが `measured: false` を返す。

## 出所

| | |
|---|---|
| 抽出元 | `~/kio-dogfood/corpus-v1/corpus` (420 scope) |
| 文書数 | 1,015 (原本のファイル数と一致) |
| 抽出日 | 2026-07-28 |
| 再生成 | `python3 eval/v3/extract_normalized_corpus.py --fixture <index 済み fixture> --out <dir>` |

内容は合成である (`eval/generate_persona_corpus.py` 系が生成した persona corpus を
OCR したもの)。実在の人物・組織の情報は含まない。
