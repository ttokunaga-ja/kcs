# V4 実測結果 (2026-07-27)

`tasks/local-adapter-plan.md` の **V4** を GPU 実機で実行した記録。手順は
[../README.md](../README.md)、算出規約は [07 §5.3](../../../docs/07-adapter-spec.md) と
[03 §5.1](../../../docs/03-data-model.md)。

| | |
|---|---|
| モデル | `Qwen/Qwen3-VL-Embedding-2B` revision `9f2f7e71` |
| サーバ | vLLM 0.26.0 (`--runner pooling`、`--chat-template` は**渡していない**) |
| ハード | RTX 4070 (sm_89) / WSL2 / NVIDIA driver 610.62 |
| 応答した endpoint | 全 6 リクエストが `/v1/embeddings` で通り、`/pooling` への fallback は不要だった |

## ファイル

| ファイル | 種別 | 内容 |
|---|---|---|
| `v4-capture.json` | 実測 (生) | template 候補と重みハッシュ。候補は 1 本のみ |
| `v4-probe.json` | 実測 (生) | 既定 instruction での cos 測定 |
| `v4-probe-altinstr.json` | 実測 (生) | `--instruction` のみ非既定にした対照 |
| `chat_template.confirmed.jinja` | 実測 (生) | 確定した template 本文。モデルリポジトリの `chat_template.jinja` とバイト一致 |
| `v4-profile.json` | **導出・採用** | 下記の裁定を反映した profile。生ではない (再生成手順は末尾) |

## 測定値

| 測定 | 値 | 読み |
|---|---:|---|
| `cos(input[] 経由, messages 経由)` | **0.473994** | **D4 の前提が成立** |
| `cos(instruction 有, 無)` — probe 既定 | **1.000000** | 測定の artifact。下記参照 |
| `cos(instruction 有, 無)` — 非既定文面 | **0.798898** | instruction は実際にベクトルを動かす |
| `cos(同一入力 2 回)` | **1.000000** | 決定的。first-instance-wins が成立する |
| `cos(無関係な 2 文)` — 参考 | **0.596608** | プーリング健全 |
| 観測次元 | **2048** | native。profile の 768 は MRL 切り詰め側 (V3 の判断待ち) |
| 返却ベクトルの L2 ノルム | **≈ 1.0** | 正規化済みで返る |

**1 行目と 5 行目を並べると D4 の根拠が最も強く出る。** 両者は `messages` 経由の同一
ベクトル (`b_msg`) を共通項に持つので比較は clean であり、**同一文字列を 2 つの wire 形式で
通したほうが (0.474)、無関係な 2 文を同じ形式で通すより (0.597) 遠い**。
07 §5.3 (2) の「実質 2 空間に分裂する」は比喩ではなく実測である。

**2 行目の 1.0 はトートロジーであってモデルの性質ではない。**
`chat_template.jinja` は system message が無いとき `default_system_message =
'Represent the user's input.'` を注入する。[`v4_probe.py`](../v4_probe.py) の
`DEFAULT_INSTRUCTION` が同一文字列なので、instruction の有無が同一トークン列に落ちる
(`v4-probe.json` の attempt B と C の fingerprint が一致している)。
文面を変えた `v4-probe-altinstr.json` が 0.798898 を出しており、
**D3 の instruction 側は反証されていない**。

**L2 ノルムが 1.0 で返ることは V3 の入力になる。** 2048 を 768 へ切り詰めると
ノルムが崩れるので、MRL 比較では**切り詰め後に再正規化する**必要がある。

## 確定した chat template

**`chat_template.jinja` (候補は最初から 1 本) を generation prompt 無しで適用したもの。**

- raw sha256: `sha256:a47e6afb389f86f45be7810f17d2686fd42b2bec7ba6e6958abf85845af258c5`
- normalized sha256: `sha256:26afcd6ea76e0283e700f2037c2216ddb693e7595f62e9aa367ef06903fd4627`

> ### ⚠ `v4-probe.json` の `rendered_prompt` をそのまま正にしてはならない
>
> このファイルの `rendered_prompt` は **40 token** と記録しているが、
> **embedding 経路が実際に使った描画は 37 token** である。
>
> `/tokenize` は既定で `add_generation_prompt=True` を適用するため、
> 末尾に `<|im_start|>assistant\n` の 3 token が付く。embedding にその turn は無い。
> 実際、同じサーバで
>
> - `/tokenize` に `add_generation_prompt=False` を渡すと 37 token になり、
>   **token id 列が `chat_template.jinja` のローカル描画と完全一致**する
> - embedding 応答の `usage.prompt_tokens` も **37**
>
> `rendered_prompt` を信じると、**存在しない assistant turn を含む template を恒久的に
> 凍結する**。確定は長さ一致ではなく **token id 一致**まで取ること。
>
> (`input[]` 経路が +1 token になるのは別要因で、`add_special_tokens=True` による
> 先頭 `<|im_start|>` (151644)。これが A と B の fingerprint が一致しない直接の理由である。)

## 裁定 — `instruction` は `""` を採用 (2026-07-27)

| instruction | `prompt_template_hash` | `tool_profile_hash` | |
|---|---|---|---|
| `""` | `sha256:7b7f4722…9e8b` | `sha256:f9f610bb…439a` | **採用** |
| `"Represent the user's input."` | `sha256:868cc1a9…7045` | `sha256:4787f5d2…3eb6` | 不採用 |

**この 2 つは同一のベクトルを生む** (template が同じ文字列を自動注入するため)。
違うのは identity だけである。根拠は [07 §5.3](../../../docs/07-adapter-spec.md) の
同節に注記した。要点は、`"Represent the user's input."` が **`chat_template` (T) の
1 行目にリテラルで存在し、T は既に hash 入力である**こと、そして Kio は system message を
送らない (= 07 §5.3 が「`""` を明示する」と規定している当のケース) ことの 2 点。

GPU 実行時に生成された `v4-profile.json` は不採用側だった。この裁定を受けて
`instruction=""` で再生成してある (下記コマンド)。実測の生データ 4 本は手を加えていない。

## `dimensions` は未確定 — profile hash は暫定

`v4-profile.json` の `dimensions: 768` は既定値であって実測ではない。**実測 native は
2048** で、`dimensions` は `tool_profile_hash` の入力なので、**V3 (MRL 768 vs native 2048)
が決着するまで上表の `tool_profile_hash` は暫定**である。

定数は 2 本に閉じている — [`fts.rs`](../../../crates/kio-index/src/fts.rs) の
`CHUNK_VEC_DIMENSIONS` (vec0 の DDL 幅を決める) と
[`local_embedding.rs`](../../../crates/kio-adapter/src/local_embedding.rs) の
`LOCAL_EMBEDDING_DIMENSIONS`。**V3 決着前に恒久コーパスを埋め込まないこと。**

## 重みの pin

単一 `model.safetensors` (4,255,140,312 B) の sha256
`sha256:c73fa9ca…09c1` をそのまま採った。計算値は HF の blob 名と一致しており、
ダウンロード健全性の裏も取れている。`v4-capture.json` の `proposed_aggregate`
(`sha256:ed22dcd5…`) は shard された場合の案であって、**今回は使っていない**。
集約規約は本実行の結果を受けて [03 §5.1](../../../docs/03-data-model.md) に昇格させた。

## instruction の推奨文面の出所

[../README.md](../README.md) が未確定としていた点。モデルカードではなく
**リポジトリ内の `config_sentence_transformers.json` の `prompts.default`**
(revision `9f2f7e71` / sentence_transformers 5.4.0) だった。

## 採用 profile の再生成

```bash
python3 eval/v4/v4_finalize.py \
  --chat-template-file eval/v4/results/chat_template.confirmed.jinja \
  --instruction "" \
  --model-version-pin sha256:c73fa9caeddeb3ff831d46c085a7a5708343248ca777e90f2d486964464509c1 \
  --out eval/v4/results/v4-profile.json
```

不採用側を再現するには `--instruction "Represent the user's input."` とする。
どちらも GPU を必要としない (`v4_finalize.py` は純粋な hash 計算)。
