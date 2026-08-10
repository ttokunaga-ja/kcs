# Reranker の差分測定 — GPU 機への作業ブリーフ (パス 2)

このファイルはそのまま作業指示として読める形にしてある。

**状態: 未実施。** [2026-08-11]

前提は `tasks/gpu-reranker-verification.md` の実測 (2026-08-10) で、
serving と JSON の形はそこで確定している。**今回は形の確認ではなく、
「この reranker は検索を良くするのか」を数字で出す。**

---

# 任務

**`eval/rerank/rerank-input-fixture.json.gz` の 24 問を reranker にかけ、
並べ替えた結果を JSON で返す。**

Mac 側で採点する。**採点はしなくてよい**し、してもこちらは使わない。

---

# 1. なぜ 3 台に割れているか

| | |
|---|---|
| CI | GPU が無く、今後も無い |
| **この GPU 機** | Rust が実行できない (os error 4551) ので `kio` が動かない |
| Mac | NVIDIA GPU が無い |

2 台の間にネットワーク経路も無い。**受け渡しは git だけ。**
だから検索は Mac、reranker はここ、採点は Mac、と 3 つに割ってある。

---

# 2. 入力

```bash
cd /mnt/c/Users/ttokunaga-ja/github.com/ttokunaga-ja/kio   # §3 の注意を読むこと
git pull
gunzip -c eval/rerank/rerank-input-fixture.json.gz > /tmp/rerank-input.json
```

形:

```json
{
  "limit": 100,
  "queries": [
    {
      "id": "qb01",
      "query": "一度に許される上限はどれほどだったか",
      "expected": [["latency-review.docx"]],
      "baseline_recall_at_10": 1.0,
      "candidates": [ {"key": ["<title>"], "text": "<chunk 本文>"}, ... ]
    }
  ]
}
```

- **24 問、各 100 候補、合計 2,400 件。**すべて `eval/fixtures/normalized-corpus/`
  由来なので公開可 (リポジトリ内のデータである)
- `candidates` は **text lane + vector lane が返した順**に並んでいる。
  この順が baseline
- **`expected` と `key` は見なくてよい。**採点は Mac 側でやる。
  見て並べ替えに使うことは**しないこと** — それは reranker の性能ではなくなる

---

# 3. 出力

```json
{
  "model": "<実際に serve したモデル ID>",
  "queries": [ {"id": "qb01", "ranking": [17, 3, 92, ...]}, ... ]
}
```

- `ranking` は **その問の `candidates` 配列への添字**を、良い順に並べたもの
- **添字で返すこと。**id でも本文でもない。範囲外や重複はこちらで検出して弾く
- 全 100 件を並べてもよいし、`top_n` で切ってもよい。
  **切った場合、残りは元の順のまま後ろに続くものとして採点される** (捨てたとは見なさない)
- 24 問すべてを含めること。欠けた問は `unranked` として報告され、
  baseline のまま採点される

置き場所と報告:

```bash
# 出力は圧縮して置く
gzip -9 -c /tmp/rerank-output.json > eval/rerank/rerank-output-<model>.json.gz
git add eval/rerank/rerank-output-<model>.json.gz
git commit && git push
```

このファイルの末尾に `# 5. 実施記録` を足し、**使ったモデル / 起動コマンド /
所要時間 / VRAM** を書くこと。冒頭の状態行も更新すること。

---

# 4. どのモデルで走らせるか

**複数走らせてほしい。**`gpu-reranker-verification.md` §5.6 の精度は
24 問での 1 問差で、分離できていない。今回は**同じ 24 問に対する
Recall@10 の差分**という別の量を測るので、そこで並べ直したい。

優先順:

1. `BAAI/bge-reranker-v2-m3` — §5.6 で 21/24 の首位
2. `hotchpotch/japanese-reranker-base-v2` — 20/24 で、**VRAM 半分・遅延半分**
3. `cl-nagoya/ruri-v3-reranker-310m` — 元の第一候補

**1 と 2 は必ず。**3 は余力があれば。

起動は §5.1 の実績どおり:

```bash
export PATH="$HOME/v4venv/bin:$PATH"
export HF_HOME="$HOME/.cache/huggingface"
export CPATH="$HOME/pyhdr/usr/include/python3.12:$HOME/pyhdr/usr/include"

vllm serve <model> --host 127.0.0.1 --port 8100 \
  --gpu-memory-utilization 0.35 --max-model-len 1024 \
  --served-model-name reranker
```

## 4.1 呼び出しで必ず守ること (§5.7 の実測)

- **`truncate_prompt_tokens: -1` を必ず付ける。**1 件でも `max_model_len` を
  超えるとバッチ全体が 400 になる。**2,400 件を投げる今回はほぼ確実に踏む**
- `model` は `--served-model-name` の値。間違えると 404
- 応答の `index` は**入力添字**。`results` は降順で返るが、順序ではなく
  `index` で引くこと
- `relevance_score` の値域はモデル依存 (base-v2 は −11.2〜+4.5 の無界)。
  **絶対閾値で足切りしないこと。**今回要るのは順序だけ

---

# 5. やってはいけないこと

- **`expected` / `key` を見て並べ替える。**測っている量が変わる
- **採点する。**Mac 側の `eval/rerank_apply.py` が正本。二重に出すと食い違う
- **リポジトリ外のデータを混ぜる。**`ttokunaga-ja/kio` は public である
- **「だいたい良くなった」で報告する。**要るのは並べ替えた添字だけ

---

# 6. 環境メモ

`tasks/gpu-reranker-verification.md` §3 の記載は **4 点が実機と違っていた**
(GPU / VRAM / user / repo path)。**正しい値は同ファイル §5.0 にある。**
今回も、書いてあることと目の前の機械が食い違ったら**機械を信じること。**

判っている範囲:

- リポジトリは `/mnt/c/Users/ttokunaga-ja/github.com/ttokunaga-ja/kio`
- Python は `~/v4venv` (system の `pip3` も `ensurepip` も無い)
- Docker は WSL から使えない。Rust は実行できない
- ビルドしたてのバイナリは最初の 1 行を出すまで数分止まることがある。
  `ps -o time` を見てから殺すこと
