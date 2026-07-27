# V4 — ローカル embedding profile の identity を実測で確定する

> **2026-07-27 に実行済み。結果は [results/](results/README.md)。**
> 本書はその実行を経て手順を直してある — 特に **step 4 の確定手続き**は、
> 初版の指示に従うと**誤った template を恒久凍結する**ことが実行中に判明したので
> 書き換えた。再実行 (別モデル / 別 backend) では本書の現行版に従うこと。

`tasks/local-adapter-plan.md` の **V4**。Stage 2 の U2 (実 vLLM の `messages` 配線) は
これが出るまで着手できなかった。理由は [07 §5.3](../../docs/07-adapter-spec.md) が述べている
とおりで、embedding は content-addressed identity を持ち first-instance-wins で永続化
されるため、**誤った空間のベクトルは恒久的に凍結される**。placeholder の
`prompt_template_hash` で本番ベクトルを作ると、後で直すには全再埋め込みが要る。

実行場所は **Linux + NVIDIA GPU の機械**。macOS 開発機では vLLM が動かず、CI にも
GPU runner がないので、この計測だけは自動化の外にある。

## 何を持ち帰るのか

| # | 値 | 使い道 |
|---|---|---|
| 1 | vLLM が実際に適用した chat template の本文 | `prompt_template_hash` の入力 (D3) |
| 2 | 推奨 instruction の文面 (無ければ空文字) | 同上 |
| 3 | 重みファイルの sha256 | `model_version_pin` (D2) |
| 4 | `cos(input 経由, messages 経由)` | **D4 の是非**。1.0 なら D4 は無駄なコストを払っている |
| 5 | `cos(instruction 有, 無)` | **D3 の instruction 側の是非** |
| 6 | `cos(同一入力 2 回)` | 1.0 でなければ **Stage 2 の採用可否に戻る** |
| 7 | 観測された次元 (768 / native) | V3 の入口 |

4〜6 は「裁定を追認するため」ではなく**反証しうる形**で置いてある。1.0 が出たら
そのまま報告してほしい — Stage 0 の裁定を書き換える根拠になる。

## 手順

### 0. 移植が壊れていないことを先に確認する (GPU 不要・どこでも)

```bash
python3 eval/v4/v4_identity.py
```

Kio 本体に凍結済みの 4 ベクタと突き合わせる。**ここが落ちたら以降は全部無意味**なので
先に通すこと。`v4_identity.py` は `identity.rs` の写経であって仕様の再解釈ではない。

### 1. モデルを取得して、テンプレート候補と重みハッシュを採る

```bash
python3 eval/v4/v4_capture.py --model-dir /path/to/Qwen3-VL-Embedding-2B --out v4-capture.json
```

chat template の在り処は HF の規約が動いており複数候補が同居しうるので、**優先順位を
付けずに全部列挙する**。「正規化後も内容の異なる候補が複数ある」と警告が出たら、
どれが本物かは次の実測で決める。

重みが shard されている場合、スクリプトは各 shard の sha256 と集約
`sha256(JCS({relative_path: sha256}))` を出す。**この集約は 2026-07-27 に
[03 §5.1](../../docs/03-data-model.md) の規約へ昇格した** — shard されているなら集約を、
単一ファイルなら**そのファイルの sha256 をそのまま**採る (集約を通さないのは、pin が
配布元の blob hash と一致してダウンロード健全性の確認を兼ねるため)。

### 2. vLLM を起動する

```bash
vllm serve Qwen/Qwen3-VL-Embedding-2B --runner pooling --host 127.0.0.1 --port 8000
```

127.0.0.1 に閉じるのは D1 の loopback 制約と同じ姿勢で、計測中も外へ出さないため。

> **起動ログに chat template は出ない (vLLM 0.26.0 で確認)。** 初版はここで
> 「起動ログの chat template 行を控える」と指示していたが、この版はそのログ行を
> 一切出さない。**どの template が使われたかは step 4 の実測でしか分からない。**
>
> GPU の実装量に対して既定値が大きすぎる場合は `--gpu-memory-utilization` /
> `--max-model-len` で合わせてよい。どちらも template・エンドポイント・プーリングに
> 触れないので、測定対象を動かさない (2026-07-27 の実行では両方を使い、
> `max_model_len` は 16384 だった)。

### 3. 実測する

```bash
python3 eval/v4/v4_probe.py --model Qwen/Qwen3-VL-Embedding-2B --out v4-probe.json
```

エンドポイント (`/v1/embeddings` が `messages` を受けるか、`/pooling` が要るか) は
vLLM の版で動くので、**候補を順に試して通ったものを記録する**。決め打ちで書いて
GPU セッションを溶かさないための設計。

終了コードは、決定性が壊れていたときだけ 1 になる。

### 4. template を確定して profile を出す

`v4-capture.json` の候補と実測を突き合わせ、**どの候補が実際に使われたか**を人間が
1 回判断する。自動化していないのは、ここでの取り違えが恒久的に凍結されるため。

> **⚠ `v4-probe.json` の `rendered_prompt` をそのまま正にしてはならない。**
>
> `rendered_prompt` は `/tokenize` の出力だが、**`/tokenize` は既定で
> `add_generation_prompt=True` を適用する**。embedding 経路にその turn は無いので、
> 記録された長さは実際の描画より `<|im_start|>assistant\n` の 3 token 分だけ長い
> (2026-07-27 の実行では 40 対 37)。これを正にすると**存在しない assistant turn を
> 含む template を凍結する**。
>
> 確定は次の 3 つを突き合わせ、**長さではなく token id 列の一致**まで取ること:
>
> 1. 候補 template をローカルで `apply_chat_template(..., add_generation_prompt=False)`
> 2. `/tokenize` に **`add_generation_prompt=False` を明示**して投げた token id
> 3. embedding 応答の `usage.prompt_tokens`
>
> `input[]` 経路が +1 token になるのは別要因 (`add_special_tokens=True` による
> 先頭の `<|im_start|>`) で、template の違いではない。混同しないこと。

確定したら本文をファイルに落として:

```bash
python3 eval/v4/v4_finalize.py \
  --chat-template-file eval/v4/results/chat_template.confirmed.jinja \
  --instruction "" \
  --model-version-pin sha256:... \
  --out eval/v4/results/v4-profile.json
```

`local_embedding.rs` に貼る定数がそのまま出る。

> **`--instruction` は「Kio が供給する文面」であって、template が注入する既定文ではない。**
> 2026-07-27 の実行では、モデルの chat template が system message 不在時に
> `"Represent the user's input."` を注入することが判明した。この文字列は
> `--chat-template-file` の側に既に入っているので、`--instruction` にも書くと
> 二重記録になる。**Kio が system message を送らない構成では `""`** が正しい
> ([07 §5.3](../../docs/07-adapter-spec.md) の裁定)。

### 5. 返すもの

`eval/v4/results/` へ次の 5 つを置く — `v4-capture.json` / `v4-probe.json` /
確定した template 本文 (生データ)、`v4-profile.json` (導出)、そして出所と裁定を書いた
`README.md`。これがあれば実 adapter の profile を書ける。

生データは編集しないこと。裁定を反映して作り直すのは `v4-profile.json` だけで、
それは `v4_finalize.py` を回せばいつでも再生成できる (GPU 不要)。

## 既知の未確定点 — 2026-07-27 の実行ですべて決着した

- ~~**shard された重みの pin 規約**が 03 §5.1 で一意でない~~
  → 集約規約を [03 §5.1](../../docs/03-data-model.md) へ昇格。実行したモデルは単一
  `model.safetensors` だったので、集約は使わず file の sha256 をそのまま採った
- ~~**instruction の「推奨文面」の出所**~~
  → モデルカードではなく**リポジトリ内の `config_sentence_transformers.json` の
  `prompts.default`**。ただし実行の結果、この文面は chat template が自動注入するもので
  **Kio が供給する instruction ではない**と分かり、`instruction = ""` を採ることになった
- **`rendered_prompt` を正とする、と書いていたのは誤り** (初版の指示)。
  「識別したいのは実際にトークン列を決めたものであって、リポジトリに置いてあるファイル
  ではない」という**原則は正しい**。誤っていたのは証人の選び方で、`/tokenize` は
  embedding 経路とは**別の既定** (`add_generation_prompt=True`) で描画するため、
  「実際にトークン列を決めたもの」の証人にならない。実行では結果的に
  **ファイル上の候補のほうが正しかった**。step 4 の現行手順 (token id の 3 点照合) が
  この修正版である

## この harness で V3 / U7 まで測るか

測らない。V3 (MRL 768 と native の品質差) と U7 (image/text 同一空間の数値一致) は
同じサーバ 1 起動で追加測定できるが、**V4 は Stage 2 全体のブロッカーであり、
先に単独で決着させる価値がある**。`v4_probe.py` が観測次元を記録するので、V3 に
進むときの入口だけは残してある。
