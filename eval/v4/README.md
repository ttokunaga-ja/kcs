# V4 — ローカル embedding profile の identity を実測で確定する

`tasks/local-adapter-plan.md` の **V4**。Stage 2 の U2 (実 vLLM の `messages` 配線) は
これが出るまで着手できない。理由は [07 §5.3](../../docs/07-adapter-spec.md) が述べている
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

重みが shard されている場合、03 §5.1 の「重みファイルの sha256」は一意に決まらない。
スクリプトは各 shard の sha256 と集約案 `sha256(JCS({path: sha256}))` を出す。
**集約案は確定規約ではない** — 報告に載せて 03 §5.1 に追記するまで profile に焼かないこと。

### 2. vLLM を起動する

```bash
vllm serve Qwen/Qwen3-VL-Embedding-2B --runner pooling --host 127.0.0.1 --port 8000
```

起動ログの chat template 行を控えておくこと (`--chat-template` を渡していないときに
vLLM が何を拾ったかがそこに出る)。127.0.0.1 に閉じるのは D1 の loopback 制約と
同じ姿勢で、計測中も外へ出さないため。

### 3. 実測する

```bash
python3 eval/v4/v4_probe.py --model Qwen/Qwen3-VL-Embedding-2B --out v4-probe.json
```

エンドポイント (`/v1/embeddings` が `messages` を受けるか、`/pooling` が要るか) は
vLLM の版で動くので、**候補を順に試して通ったものを記録する**。決め打ちで書いて
GPU セッションを溶かさないための設計。

終了コードは、決定性が壊れていたときだけ 1 になる。

### 4. template を確定して profile を出す

`v4-capture.json` の候補と `v4-probe.json` の `rendered_prompt` を突き合わせ、
**どの候補が実際に使われたか**を人間が 1 回判断する。自動化していないのは、ここでの
取り違えが恒久的に凍結されるため。

確定したら本文をファイルに落として:

```bash
python3 eval/v4/v4_finalize.py \
  --chat-template-file ./chat_template.confirmed.jinja \
  --instruction "Represent the user's input." \
  --model-version-pin sha256:... \
  --out v4-profile.json
```

`local_embedding.rs` に貼る定数がそのまま出る。

### 5. 返すもの

`v4-capture.json` / `v4-probe.json` / `v4-profile.json` の 3 つと、確定した
template 本文。これがあれば実 adapter の profile を書ける。

## 既知の未確定点 (V4 が暴く想定のもの)

- **shard された重みの pin 規約**が 03 §5.1 で一意でない。V4 の集約案を持ち帰って裁定する
- **instruction の「推奨文面」の出所**。モデルカード由来なら、その版も記録しないと
  再現できない。`v4_finalize.py` は渡された文字列をそのまま使うので、出所は報告側で残す
- **vLLM が template を暗黙に補完する場合**、`rendered_prompt` とファイル上の候補が
  一致しないことがある。その場合の正は **rendered_prompt 側** — 識別したいのは
  「実際にトークン列を決めたもの」であって、リポジトリに置いてあるファイルではない

## この harness で V3 / U7 まで測るか

測らない。V3 (MRL 768 と native の品質差) と U7 (image/text 同一空間の数値一致) は
同じサーバ 1 起動で追加測定できるが、**V4 は Stage 2 全体のブロッカーであり、
先に単独で決着させる価値がある**。`v4_probe.py` が観測次元を記録するので、V3 に
進むときの入口だけは残してある。
