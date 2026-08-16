# Reranker の差分測定 — GPU 機への作業ブリーフ (パス 2)

このファイルはそのまま作業指示として読める形にしてある。

**状態: 実施済み。** [2026-08-11]

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
- **採点する。**Mac 側の `kio-eval rerank apply` が正本。二重に出すと食い違う
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

---

# 5. 実施記録

実施 2026-08-11。**採点はしていない。**`expected` / `key` / `scenario` /
`baseline_recall_at_10` は 1 度も読んでいない。読んだのは
`id` / `query` / `candidates[].text` の 3 つだけである。

## 5.1 出したもの

**優先順の 1・2 に加えて 3 も走らせた** (余力があったため)。3 本とも 24 問すべて、
100 件すべてを並べてある (`top_n` による切り詰めはしていない)。

| ファイル | `model` | bytes |
|---|---|---|
| `eval/rerank/rerank-output-bge-reranker-v2-m3.json.gz` | `BAAI/bge-reranker-v2-m3` | 3,387 |
| `eval/rerank/rerank-output-japanese-reranker-base-v2.json.gz` | `hotchpotch/japanese-reranker-base-v2` | 3,415 |
| `eval/rerank/rerank-output-ruri-v3-reranker-310m.json.gz` | `cl-nagoya/ruri-v3-reranker-310m` | 3,414 |

投入前に機械的に検査した (すべて通過):

- `queries` の `id` が入力と**同じ順で 24 問**そろっている
- 各 `ranking` が **`0..99` の順列**である (長さ 100・範囲内・重複なし)
- gzip に書いたあと**読み直して**、元の構造と一致することを確認

## 5.2 起動コマンド

3 本とも §4 の実績どおり。`--max-model-len` は**3 本とも 1024** に揃えた
(`/v1/models` の `max_model_len` で確認済み)。切り詰め幅が同じなので、
3 つの出力は互いに比較できる。

```bash
export PATH="$HOME/v4venv/bin:$PATH"
export HF_HOME="$HOME/.cache/huggingface"
export CPATH="$HOME/pyhdr/usr/include/python3.12:$HOME/pyhdr/usr/include"

vllm serve <model> --host 127.0.0.1 --port <port> \
  --gpu-memory-utilization 0.35 --max-model-len 1024 \
  --served-model-name reranker
```

リクエストは 1 問 = 1 リクエスト (100 documents)、24 リクエスト:

```json
{"model":"reranker","query":"<query>","documents":["<text>", ...],"truncate_prompt_tokens":-1}
```

応答は `relevance_score` の**降順**に並べ、同点は**元の添字の昇順**で割った
(再実行しても同じ順になるようにするため)。返しているのは `results[].index` である。

## 5.3 所要時間と VRAM

baseline (モデル無し) は **1,952 MiB / 12,282 MiB**。
前回 (2026-08-10) は 1,456〜1,539 MiB だったので、**baseline 自体が日によって動く**。
Windows 側のデスクトップが使っている分で、WSL からは内訳が取れない。

| モデル | ロード後 idle | peak | 24 問の実時間 | 1 問あたり min / p50 / max |
|---|---|---|---|---|
| `japanese-reranker-base-v2` | 2,647 MiB | **2,713 MiB** | **3.5 s** | 76.1 / 108.9 / 366.4 ms |
| `ruri-v3-reranker-310m` | (未記録) | **3,181 MiB** | **5.7 s** | 121.9 / 188.3 / 541.3 ms |
| `bge-reranker-v2-m3` | 3,435 MiB | **3,455 MiB** | **6.5 s** | 140.4 / 224.1 / 538.6 ms |

- **2,400 件を通しても 10 秒未満。**モデルのロード (`/health` が 200 になるまで) の方が
  長く、4〜36 秒かかった
- 各モデルの最初の 1 問だけ 366〜541 ms と遅い。**warmup 分**で、2 問目以降は半分以下
- `ruri` のロード後 idle は取り忘れた。**peak は取れているのでそちらを使ってほしい**

## 5.4 入力について気づいたこと (採点側で効くかもしれない)

`candidates[].text` の実測:

| | |
|---|---|
| 件数 | 24 問 × 100 = **2,400** (欠けなし) |
| 文字数 | min **3** / p50 147 / p95 1,165 / max **5,480** |
| **空白のみの text** | **36 件** |

- **空の候補 36 件は、そのまま投げて 200 が返った。**vLLM は空文字列を拒否しないので、
  置換はしていない (**出力の添字は入力の添字とそのまま 1:1**)。
  ただし**空文字に付いたスコアには意味が無い**はずなので、採点側で気になるなら
  そちらで落としてほしい
- `max_model_len` (1024) を超える候補は実際に存在した (最長 5,480 字)。
  §4.1 のとおり **`truncate_prompt_tokens: -1` を全リクエストに付けたので 400 は 1 度も出ていない。**
  付け忘れれば確実に落ちていた

## 5.5 並べ替えが実際に起きたことの確認 (**採点ではない**)

出力が恒等順列でないことだけ確かめた。**`expected` を使っていないので精度ではない。**
採点は `kio-eval rerank apply` が正本である。

| モデル | 先頭が baseline と変わった問 | baseline の上位 10 のうち上位 10 に残った数 (24 問平均) |
|---|---|---|
| `bge-reranker-v2-m3` | 16/24 | 3.1/10 |
| `japanese-reranker-base-v2` | 16/24 | 3.0/10 |
| `ruri-v3-reranker-310m` | 14/24 | 3.2/10 |

**baseline の上位 10 のうち 7 件が入れ替わっている。**動いていないという可能性は消える。
どちらに動いたのかは Mac 側の採点で出る。

モデル同士の一致 (上位 10 の重なり、24 問平均):

| | |
|---|---|
| `bge` vs `base-v2` | 6.0/10 |
| `bge` vs `ruri-v3` | 5.8/10 |
| `base-v2` vs `ruri-v3` | 5.8/10 |

**3 本は互いに 4 割方違うものを上位に置いている。**前回 §5.6 が 24 問 1 問差で
分離できなかったのは、順位を 1 個の数字に潰していたためで、**出力そのものは
かなり違う。**Recall@10 の差分なら分離できる見込みがある。

## 5.6 環境

§6 の記載と食い違う点は**無かった** (repo path・`~/v4venv`・GPU いずれも一致)。
Docker と Rust は今回使っていないので確認していない。

前回からの持ち越しで効いたのは 1 点:
**WSL の `/tmp` は `wsl.exe` の呼び出しをまたぐと消える。**
入力の展開先を `/tmp/rerank-input.json` (§2 の手順) ではなく
`~/rrwork/rerank-input.json` にしてある。**§2 の手順をそのまま踏むと、
次の呼び出しでファイルが消えていることがある。**
