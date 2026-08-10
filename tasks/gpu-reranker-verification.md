# Reranker の GPU 実機検証 ブリーフ

このファイルはそのまま作業者 (人でもエージェントでも) への指示として読める形にしてある。
実行には **NVIDIA GPU + Linux** が要る。**WSL2 で構わない** — 必要なのは Linux と CUDA
であって Windows 実機ではない (`tasks/gpu-local-ocr-verification.md` と同じ条件)。

**状態: 実施済み。** [2026-08-10]

---

# 任務

**Rerank Adapter を書く前に、「どのモデルを、どの serving で、どういう JSON で叩くのか」
を実測で確定させる。**

## なぜ実装より先にこれをやるのか

07 §5.6 は Rerank の席を既に用意している:

```
input:   query, candidate_result_ids, candidate_features
output:  reranked_result_ids, scores
metadata: profile_hash, searched_scopes, fallback_reason
```

そして `crates/kio-adapter/src/local_embedding.rs` に、ローカル HTTP Adapter の
ひな型 (`LocalEmbeddingClient` trait → `EnvLocalEmbeddingClient` → `LocalEmbeddingAdapter<C>`)
が既にある。**書こうと思えば今日書ける。**

書かない理由は、局所 OCR のときとの違いにある。あのときは PaddleOCR-VL の
`/layout-parsing` という**実在するエンドポイントの形が判っていた**。それでも
第 1 回の実機接続で **応答 schema が 2 箇所間違っていた** (ページが封筒の中にある、
図が CommonMark で来ない、`block_order` が全部 null)。**形が判っている状態ですら
そうだった。**

reranker はまだ形が判っていない。ここで client を書けば、それは推測に対する実装になる。

---

# 1. 測ること

## 1.1 モデル — 8GB に載って日本語が効くか

**GPU は RTX 4060 (VRAM 8GB)。**これが上限で、ここに載らないものは検討対象外。

| 候補 | 規模 | 見るべき点 |
|---|---|---|
| **Ruri v3 reranker** (`cl-nagoya/ruri-v3-reranker-310m`) | 310m | 日本語特化。第一候補 |
| `BAAI/bge-reranker-v2-m3` | 568m | 多言語。日本語込みだが特化ではない |
| `hotchpotch/japanese-reranker-cross-encoder-*` | 小〜中 | 日本語特化の別系統 |

**正確なモデル ID は実機で確認すること。**上の ID は記憶からの記載で、検証していない。

各候補について記録する:

- **VRAM 実測** (`nvidia-smi` の使用量。ロード時とバッチ推論時の両方)
- 8GB に**載らなかった**場合はそう書く。載らないことも結果である

## 1.2 serving — エンドポイントの形

**仮説: TEI (`text-embeddings-inference`) の `/rerank`。**HuggingFace の公式 serving で
cross-encoder の rerank エンドポイントを持つ。これが動くなら、形が標準化されている分だけ
Adapter が素直になる。

**仮説であって前提ではない。**動かなければ別の serving (vLLM / sentence-transformers を
FastAPI で包む / TEI の別バージョン) を試し、**実際に動いたものの形を記録する**。

記録するもの:

```
起動コマンド (そのまま再現できる形で)
POST 先の URL とパス
リクエスト JSON の実物 (1 件でよい)
レスポンス JSON の実物 (1 件でよい)
エラー時のレスポンス JSON (わざと壊して 1 件)
```

**エラー時の形を必ず取ること。**OCR のときは `errorCode` が HTTP 200 に乗って返り、
先に検査しないとサービス側の失敗が「ページの無い文書」に化けた。同じ罠を踏まないため。

## 1.3 遅延 — `candidate_depth` = 200 で使いものになるか

05 §1.3 の候補取得は既定 **200 件**。reranker は 1 クエリでこれを見ることになる。

| 測る条件 | 記録 |
|---|---|
| N = 200、chunk 本文は実物相当の長さ | p50 / p95 レイテンシ |
| N = 50 | 同上 (打ち切る価値があるかの判断材料) |
| バッチ 1 件 | 同上 (下限の把握) |

**入力は `eval/fixtures/normalized-corpus/` の chunk を使ってよい。**リポジトリ内の
データなので公開可。それ以外の実文書は使わないこと (下記)。

---

# 2. やってはいけないこと

- **Adapter のコードを書く。**この任務は測定であって実装ではない。形が出たらこちらで書く
- **リポジトリ外の実文書を入力にする。**`ttokunaga-ja/kio` は **public リポジトリ**である。
  検証ログに文書本文が入ると、そのまま公開されることになる。入力は
  `eval/fixtures/normalized-corpus/` に限ること
- **「だいたい動いた」で報告する。**リクエストとレスポンスの**実物の JSON** が要る。
  要約された形では Adapter が書けない
- **モデル ID を記憶で書く。**§1.1 の ID は未検証。実機で引いたものを書くこと

---

# 3. 環境メモ (2026-08-06 / 08-09 実測)

**この機の状態は判っている。探し直さないこと。**

| | |
|---|---|
| GPU | RTX 4060、**8188 MiB**。idle (P8) で ~894 MiB 使用済み → **空きは ~7.3 GB** |
| OS | Windows 11 + WSL2、user `RM2C` |
| CUDA | driver KMD 610.88 / WSL 610.57.01、UMD 13.3。`/usr/lib/wsl/lib` に `libcuda.so` 一式あり、WSL からの CUDA compute は動く |

## リポジトリの場所

**`/mnt/c/users/rm2c/dev/github.com/ttokunaga-ja/kio`** — Windows 側の
ファイルシステムにあり、WSL からは `/mnt/c` 越しに見える。

**`/home/rm2c` は空である。**そこだけ見て「リポジトリが無い」と判断しないこと。
`origin` は SSH で、WSL からの pull は動く (鍵は配置済み)。

## 入っていないもの

- **`pip3` が無い** (`python3` / `git` / `curl` はある)
- **Docker Desktop は動いているが WSL integration が off**
- vLLM も PaddleOCR-VL も未インストール

serving を立てる前に、この 3 つのどれを使うかを先に決めること。

## Rust はビルドできない

application control policy が、cargo が `target\` に書く未署名の
`build-script-build` の**実行**を拒否する (**os error 4551**)。`--release` だけでなく
debug でも、msvc でも gnu でも同じ。コンパイル自体は通り、実行だけが止まる。
解除は管理者権限が要る。詳細は `tasks/windows-realmachine-verification.md`。

**したがってこの機で `kio` バイナリは動かせない。**候補 chunk を `kio search` で
作ることはできないので、**§1.3 の入力は `eval/fixtures/normalized-corpus/corpus/`
のテキストを直接読んで作ること** (p01〜p20 に 1,015 文書ぶんの正規化済み本文がある)。
**コンパイルを伴う手順を計画しないこと。**

## 操作経路

この機は **Claude Code がネイティブに動いている**ので、実行はそのエージェントが行う。
人が Chrome Remote Desktop で介入する場合のみ注意: **CRD は修飾キーを一切送らない。**
Shift が落ちるので `_` は `-` になり、大文字と `|` `:` `"` `~` が打てない。Ctrl も
落ちるので **Ctrl+C で止められない** (`nvidia-smi -L` が `-l` になり、ウィンドウを
閉じるしか止める手が無かった実績がある)。長いコマンドはファイルに書いてから実行する。

---

# 4. 報告の形

次の 4 つが揃っていれば、こちらで Adapter を書ける:

1. **動いたモデル ID と serving の起動コマンド** (再現できる形で)
2. **リクエスト / レスポンス / エラーレスポンスの実物 JSON**
3. **VRAM 実測**と、載らなかった候補があればその事実
4. **N = 200 / 50 / 1 の遅延**

揃わなかった項目は「揃わなかった」と書いてよい。**推測で埋めないこと** —
埋まっていない項目があるほうが、間違った値が入っているより遥かに扱いやすい。

## 報告の経路

**この機と Mac の間にネットワーク経路は無い** (ping 100% loss、TCP 22/445 とも
*No route to host*。SSH も CRD のクリップボードも経路にならない)。**受け渡しは git だけ。**

このファイルの末尾に `# 5. 実測結果` を足して書き、commit して push すること。
JSON は要約せず**実物をそのまま**貼る。Adapter を書くのはそれを読んでからで、
書くのは Mac 側である。

冒頭の **状態** 行を `実施済み [日付]` に更新すること。

---

# 5. 実測結果

実施 2026-08-10。測定のみ。**Adapter のコードは書いていない。**

## 5.0 ブリーフと実機が食い違っていた点

§3 は「この機の状態は判っている。探し直さないこと」と書いてあるが、
**4 点が実機と違った。**先に置く。

| §3 の記載 | 実測 |
|---|---|
| GPU は RTX 4060、**8188 MiB**、空き ~7.3 GB | **RTX 4070、12282 MiB**、driver 610.62。idle 使用 1456〜1539 MiB、**空き ~10.5 GB** |
| リポジトリは `/mnt/c/users/rm2c/dev/github.com/ttokunaga-ja/kio` | **その path は無い。`rm2c` というユーザ自体が無い** (`/home` にも `/mnt/c/Users` にも)。実在は `/mnt/c/Users/ttokunaga-ja/github.com/ttokunaga-ja/kio` |
| `/home/rm2c` は空 | `/home/rm2c` は**存在しない**。WSL ユーザは `ttokunaga-ja` で、`/home/ttokunaga-ja` は**空ではない** (後述の venv がある) |
| Docker Desktop は動いているが WSL integration が off | **WSL から docker は使えない。**PATH 上の `docker` は Windows 側バイナリで、実行すると Desktop の shim が `The command 'docker' could not be found in this WSL 2 distro.` を返す。`wsl -l -v` でも `docker-desktop` は **Stopped** |

合っていた点: **`pip3` が無い**のは事実。ただしそれより厳しく、**`ensurepip` も無い**ので
`python3 -m venv` では pip 入りの環境すら作れない。`python3` / `git` / `curl` /
`nvidia-smi` はある。Rust は §3 のとおり使っていない (コンパイルを伴う手順は踏んでいない)。

**8GB という上限そのものについて。**この機は 12 GB なので、**「8GB に載るか」は
実測 MiB からの推定であって、8GB 機で確かめたわけではない。**下の 5.4 は絶対値
(MiB) で書いてあるので、そちらで判断してほしい。結論だけ言うと、
**4 候補すべて peak 3.2 GB 未満**で、8GB が拘束条件になる候補は無かった。

**§1.1 のモデル ID は 3 つとも実在した** (HF API で確認、未検証と書かれていたが正しかった)。

| ID | HF API | DL 数 |
|---|---|---|
| `cl-nagoya/ruri-v3-reranker-310m` | 200 | 301,641 |
| `BAAI/bge-reranker-v2-m3` | 200 | 17,552,867 |
| `hotchpotch/japanese-reranker-cross-encoder-large-v1` | 200 | 1,373 |

## 5.1 serving — 何を使ったか、TEI をなぜ使わなかったか

**TEI は使えなかった。**インストール経路が 2 つとも塞がっている:

- **Docker 経由** — 上記のとおり WSL から docker が使えない
- **`cargo install` 経由** — TEI は Rust 実装で、この機では Rust が実行できない (os error 4551)

**採ったもの: 既存の `~/v4venv` + vLLM 0.26.0 の `/v1/rerank`。**
`~/v4venv` は 2026-07-27 に別任務 (eval/v4) で作られた venv で、
**pip 26.1.2 / torch 2.11.0 / vllm 0.26.0 / transformers 5.14.1** が既に入っている。
system の pip3 が無くても、この venv の中には pip がある。

vLLM を選んだのは、**TEI と同じ形の API を持っているから**である。
`/v1/rerank` は Jina / Cohere 互換で、`query` + `documents[]` → `results[].relevance_score`。
TEI に切り替えることになっても Adapter の形はほぼ変わらない。

### 起動コマンド (そのまま再現できる形)

```bash
export PATH="$HOME/v4venv/bin:$PATH"
export HF_HOME="$HOME/.cache/huggingface"
# Triton の JIT が Python.h を要る (python3.12-dev が無く sudo も無い) ため、
# 2026-07-27 に作った展開済みヘッダを指す。今回 外して試してはいない。
export CPATH="$HOME/pyhdr/usr/include/python3.12:$HOME/pyhdr/usr/include"

vllm serve BAAI/bge-reranker-v2-m3 \
  --host 127.0.0.1 --port 8100 \
  --gpu-memory-utilization 0.35 \
  --max-model-len 1024 \
  --served-model-name reranker
```

- `--runner` は**指定していない。**vLLM が `--runner auto` を **`pooling`** に解決し、
  `XLMRobertaForSequenceClassification` を認識した (ログに出る)。`--task` も不要
- `--served-model-name reranker` を付けたので、リクエストの `"model"` は `reranker`。
  付けなければ HF の ID をそのまま書く
- `--gpu-memory-utilization 0.35` は**上限であって予約ではない。**pooling model では
  KV キャッシュを取らないので、実際の使用量はモデルごとに違った (5.4)
- 起動〜`/health` が 200 になるまで **約 68 秒** (重みが cache 済みの場合)

**モデルによって追加で要るもの:**
`hotchpotch/japanese-reranker-cross-encoder-large-v1` だけ、
**MeCab 系トークナイザ (`BertJapaneseTokenizer`) を使うので `fugashi` が要る。**
入れずに起動すると `ModuleNotFoundError: You need to install fugashi to use MecabTokenizer.`
でサーバが**起動しない**。

```bash
$HOME/v4venv/bin/python -m pip install fugashi unidic-lite
```

他の 3 つ (bge / Ruri / base-v2) には要らない。**Adapter ではなく deploy の条件**である。

## 5.2 エンドポイントの形

`/openapi.json` が実際に広告した route (`vllm serve` 起動後に取得):

```
   /classify ['post']
   /detokenize ['post']
   /health ['get']
   /invocations ['post']
   /load ['get']
   /metrics ['get']
   /ping ['get', 'post']
   /pooling ['post']
   /rerank ['post']
   /score ['post']
   /tokenize ['post']
   /v1/models ['get']
   /v1/rerank ['post']
   /v1/score ['post']
   /v2/rerank ['post']
   /version ['get']
```

`GET /v1/models` (HTTP 200) — **`max_model_len` がここに出る**ので、
Adapter は切り詰め幅を決め打ちせずここから取れる:

```json
{"object":"list","data":[{"id":"reranker","object":"model","created":1786353561,"owned_by":"vllm","root":"BAAI/bge-reranker-v2-m3","parent":null,"max_model_len":1024,"permission":[{"id":"modelperm-a7951d8e5822818b","object":"model_permission","created":1786353561,"allow_create_engine":false,"allow_sampling":true,"allow_logprobs":true,"allow_search_indices":false,"allow_view":true,"allow_fine_tuning":false,"organization":"*","group":null,"is_blocking":false}]}]}
```

### リクエストの実物

`POST http://127.0.0.1:8100/v1/rerank`、`Content-Type: application/json`。
本文は `eval/fixtures/normalized-corpus/` の実チャンク 3 件、query は
`eval/golden-queries-fixture-b.jsonl` の qb01:

```json
{
  "model": "reranker",
  "query": "一度に許される上限はどれほどだったか",
  "documents": [
    "```log 2026-07-18T09:14:32.482+09:00 INFO rebase-helper: checkout product-alpha/release/2026.07 2026-07-18T09:14:34.019+09:00 INFO rebase-helper: applying Ledger Platform migration commits 2026-07-18T",
    "```py \"\"\"一時退避していたリベース用の小さな補助関数。\"\"\" from __future__ import annotations from dataclasses import dataclass @dataclass(frozen=True) class ConflictMarker: path: str preferred_side: str def select_release_s",
    "## ledger-platform / release-check - > reconciliation window: healthy - > callback samples: reviewed - > handoff notes: ready - > next check: afternoon rotation"
  ],
  "top_n": 3
}
```

### レスポンスの実物 (HTTP 200、0.242382s)

```json
{"id":"score-b03bc1b9d3684578","model":"reranker","usage":{"prompt_tokens":226,"total_tokens":226},"results":[{"index":2,"document":{"text":"## ledger-platform / release-check - > reconciliation window: healthy - > callback samples: reviewed - > handoff notes: ready - > next check: afternoon rotation","multi_modal":null},"relevance_score":1.66491972777294e-05},{"index":1,"document":{"text":"```py \"\"\"一時退避していたリベース用の小さな補助関数。\"\"\" from __future__ import annotations from dataclasses import dataclass @dataclass(frozen=True) class ConflictMarker: path: str preferred_side: str def select_release_s","multi_modal":null},"relevance_score":1.6425787180196494e-05},{"index":0,"document":{"text":"```log 2026-07-18T09:14:32.482+09:00 INFO rebase-helper: checkout product-alpha/release/2026.07 2026-07-18T09:14:34.019+09:00 INFO rebase-helper: applying Ledger Platform migration commits 2026-07-18T","multi_modal":null},"relevance_score":1.621661431272514e-05}]}
```

形 (`vllm/entrypoints/pooling/scoring/protocol.py` の pydantic 定義とも一致):

- `RerankResponse` = `id` / `model` / `usage` / `results[]`
- `RerankResult` = `index` / `document` / `relevance_score`
- `RerankUsage` = `prompt_tokens` / `total_tokens`
- `RerankRequest` の受け口 = `query` `documents` `top_n` `model` `truncate_prompt_tokens`
  `truncation_side` `instruction` `use_activation` `priority` `request_id` ほか

**`index` は入力 `documents` の添字**で、`results` は**降順に並んで返る** (上の例は 2,1,0)。
**`document` に本文がそのまま echo される。**N=200 を投げると応答に 200 件の本文が乗るので、
**`top_n` を必ず付けた方がよい** (`top_n: 2` を投げると本当に 2 件だけ返ることは確認済み)。

## 5.3 エラー時のレスポンス — **HTTP 200 に化けなかった**

§1.2 が警戒していた「`errorCode` が HTTP 200 に乗る」形は、**vLLM では起きなかった。**
6 通り壊して 6 通りとも **HTTP の status line で失敗が判る。**
本文の形も一定で `{"error":{message,type,param,code}}`、`code` は HTTP status と同じ値。

| 壊し方 | HTTP |
|---|---|
| `query` を落とす | 400 |
| `documents` を空配列に | 400 |
| 存在しない `model` | **404** |
| 型違い (`query`:123, `documents`:文字列) | 400 |
| JSON として壊す | 400 |
| `max_model_len` 超過 | 400 |

実物 (すべて verbatim):

```json
{"error":{"message":"1 validation error:\n  {'type': 'missing', 'loc': ('body', 'query'), 'msg': 'Field required', 'input': {'model': 'reranker', 'documents': ['a', 'b']}}","type":"Bad Request","param":"body.query","code":400}}
```
```json
{"error":{"message":"At least one text_pair element must be given","type":"BadRequestError","param":null,"code":400}}
```
```json
{"error":{"message":"The model `no-such-model` does not exist.","type":"NotFoundError","param":null,"code":404}}
```
```json
{"error":{"message":"2 validation errors:\n  {'type': 'string_type', 'loc': ('body', 'query', 'str'), 'msg': 'Input should be a valid string', 'input': 123}\n  {'type': 'dict_type', 'loc': ('body', 'query', 'ScoreMultiModalParam'), 'msg': 'Input should be a valid dictionary', 'input': 123}","type":"Bad Request","param":"body.query","code":400}}
```
```json
{"error":{"message":"1 validation error:\n  {'type': 'json_invalid', 'loc': ('body', 32), 'msg': 'JSON decode error', 'input': {}, 'ctx': {'error': 'Expecting property name enclosed in double quotes'}}","type":"Bad Request","param":"body.32","code":400}}
```
```json
{"error":{"message":"This model's maximum context length is 1024 tokens. However, you requested 0 output tokens and your prompt contains at least 1025 input tokens, for a total of at least 1025 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=1025)","type":"BadRequestError","param":"input_tokens","code":400}}
```

**局所 OCR との違いははっきりしている。**あちらは 200 の中を見ないと失敗が判らなかったが、
こちらは status を見れば済む。ただし **`code` は本文にもあるので、
`HTTP status != 200` を先に見る実装で十分**、という確認までが今回の結果である。

### 長すぎる入力は落ちる — `truncate_prompt_tokens` が要る

**これは Adapter に直接効く。**`max_model_len` を超える (query, document) 対があると、
**リクエスト全体が 400 になる。**黙って切り詰めてはくれない。

`truncate_prompt_tokens` を付けると 200 になり、`prompt_tokens` はちょうど上限で返る:

| 送ったもの | HTTP | usage |
|---|---|---|
| 20,000 字の document、指定なし | **400** | — |
| 同じ + `"truncate_prompt_tokens": 1024` | 200 | `{"prompt_tokens":1024,"total_tokens":1024}` |
| 同じ + `"truncate_prompt_tokens": -1` | 200 | `{"prompt_tokens":1024,"total_tokens":1024}` |

`-1` は「モデルの上限まで」の意味で使える。**候補 200 件のうち 1 件でも長いと
バッチ全体が落ちる**ので、Adapter は常に付けるか、投げる前に自分で切ること。

## 5.4 VRAM 実測

`nvidia-smi` の `memory.used` (GPU 全体の値。WSL からは compute process 単位に
分解できないので、**モデル無しの baseline との差**で見ている)。

**baseline (vllm を止めた状態): 1456〜1539 MiB / 12282 MiB。**
この差は Windows 側のデスクトップが使っている分で、WSL からは内訳が取れない。

| モデル | 重み (safetensors) | ロード後 idle | 実測 peak | baseline との差 | 8GB に載るか |
|---|---|---|---|---|---|
| `hotchpotch/japanese-reranker-base-v2` | 529.6 MB | 2333 MiB | **2393 MiB** | ~0.85 GB | 載る |
| `hotchpotch/japanese-reranker-cross-encoder-large-v1` | 1349.8 MB | 2715 MiB | **2743 MiB** | ~1.2 GB | 載る |
| `cl-nagoya/ruri-v3-reranker-310m` | 1260.8 MB | 2836 MiB | **2879 MiB** | ~1.4 GB | 載る |
| `BAAI/bge-reranker-v2-m3` | 2271.1 MB | 3063 MiB | **3141 MiB** | ~1.6 GB | 載る |

- 重みは fp32 で公開されているが、**vLLM が起動時に fp16 へ落とす**
  (`Downcasting torch.float32 to torch.float16.`)。上の実測はすべて fp16
- **載らなかった候補は無い。**「8GB に載らない」で落ちたものは 1 つも無かった
- 起動に失敗した候補は 1 つある (`cross-encoder-large-v1` / `fugashi` 不足) が、
  これは **VRAM ではなく依存パッケージ**の問題で、入れたら載った

## 5.5 遅延 (05 §1.3 の `candidate_depth` = 200)

候補は `eval/fixtures/normalized-corpus/corpus/` の実チャンク
(200 件が**200 個の別文書**から。88〜400 字、中央値 327 字)。
query は `eval/golden-queries-fixture-b.jsonl` の qb01。
warmup 1 回のあと、N=1 は 30 回、N=50 / N=200 は各 20 回。

| モデル | N=200 p50 | N=200 p95 | N=50 p50 | N=1 p50 | N=200 の prompt_tokens |
|---|---|---|---|---|---|
| `hotchpotch/japanese-reranker-base-v2` | **191.4 ms** | 207.3 ms | 57.0 ms | 4.8 ms | 22,892 |
| `cl-nagoya/ruri-v3-reranker-310m` | **326.4 ms** | 334.6 ms | 92.5 ms | 7.1 ms | 22,892 |
| `BAAI/bge-reranker-v2-m3` | **408.4 ms** | 421.4 ms | 119.8 ms | 7.6 ms | 25,433 |
| `hotchpotch/japanese-reranker-cross-encoder-large-v1` | **564.0 ms** | 567.4 ms | 153.1 ms | 7.6 ms | 33,533 |

- **p95 は p50 の 1.05 倍以内。**バッチが GPU で素直に並ぶので、ばらつきが小さい
- **N を 200 → 50 に落として節約できるのは 200〜400 ms。**打ち切る価値があるかは
  この幅で判断できる
- N=1 が 5〜8 ms なので、**200 件の 400 ms はほぼ全部が実計算**であって
  往復のオーバーヘッドではない
- `cross-encoder-large-v1` だけ token 数が多い (33,533)。MeCab 系トークナイザが
  この混在テキスト (日本語 + コード + ログ) を細かく割るため。**遅さの一因**

## 5.6 日本語が効くか — repo の golden query で確認した

§1.1 は「日本語が効くか」を見ろと書いてあるので、**公開ベンチの数字ではなく
この repo のデータで**測った。

**方法。**`eval/golden-queries-fixture-b.jsonl` の 24 問それぞれについて、
正解文書 (`expected[].path` + `.md`) のチャンクを最大 10 件と、
**別文書から採ったチャンク**を混ぜて合計 200 件にし、rerank にかけて
**正解文書のチャンクが何位に来るか**を見た。文書検索の proxy であって
「答えの抽出」ではない。**24 問しかないので、下の差は小さな標本の差である。**

| モデル | 1 位 | 上位 5 | 上位 10 | スコアの型 |
|---|---|---|---|---|
| `BAAI/bge-reranker-v2-m3` | **21/24** | **23/24** | 23/24 | (0,1) |
| `hotchpotch/japanese-reranker-base-v2` | 20/24 | 22/24 | 22/24 | **符号付き・無界** |
| `cl-nagoya/ruri-v3-reranker-310m` | 17/24 | 21/24 | 22/24 | (0,1) |
| `hotchpotch/japanese-reranker-cross-encoder-large-v1` | 13/24 | 15/24 | 18/24 | (0,1) |

- **ブリーフの第一候補 (Ruri v3) は、この corpus では bge に負けた。**
  公開ベンチ (JQaRA 86.9 など) では Ruri v3 の方が上なので、**逆になっている。**
  24 問なので断定はできないが、「第一候補だから Ruri」で決めない方がよい
- `cross-encoder-large-v1` が最下位なのは、**`max_position_embeddings` が 512 しかなく、
  400 字のチャンクでも切り詰めが効く**ためと思われる (他は 1024 で測った)
- **どのモデルも `qb22` (`Arendt ノードへの流入引用数はいくつか`) を外した** (79 位 /
  122 位 / 11 位 / 135 位)。正解は `citation-network.jpeg` で、画像から起こした本文である
- `hotchpotch/japanese-reranker-base-v2` は**ブリーフに無い**が、
  v1 系の model card が `new_version` として指している後継である。
  **最速 (191 ms) かつ最小 (0.85 GB) で精度は 2 位**なので、候補に入れる価値がある

## 5.7 Adapter を書くときに効くこと

1. **`truncate_prompt_tokens` を必ず付ける** (5.3)。1 件長いだけでバッチ全体が 400
2. **`relevance_score` の範囲はモデル依存。**bge / Ruri / v1 は (0,1) で返るが、
   **`japanese-reranker-base-v2` は −11.2 〜 +4.5 の無界の値**で返る。
   `use_activation` を明示しても (0,1) にはならなかった (下記)。
   **絶対値の閾値を書くなら model ごとに決めるしかない。**順序は保たれるので、
   並べ替えだけなら影響しない
3. **`document` が応答に echo される。**`top_n` を付けないと 200 件の本文が返る
4. **`model` は `--served-model-name` の値。**間違えると **404**
5. **`max_model_len` は `/v1/models` から取れる。**決め打ちしなくてよい
6. **`index` は入力添字。**`results` は降順で返るが、順序に依存せず `index` で引くこと

`use_activation` の実測 (`japanese-reranker-base-v2`、同じ 3 件):

| 指定 | scores |
|---|---|
| 指定なし | `[-8.079494, -9.013225, -9.043308]` |
| `"use_activation": true` | `[-8.08035, -9.015653, -9.041377]` |
| `"use_activation": false` | `[-11.187228, -11.966308, -12.955419]` |

既定は `true` と同じ挙動。ただし **`true` にしても (0,1) にはならない。**
順序は 3 通りとも同じ。なぜこの値域になるのかまでは追っていない
(`config.json` は `ModernBertForSequenceClassification` / `num_labels=1` /
`problem_type=regression`)。**推測は書かない。**

## 5.8 揃わなかったもの

- **TEI (`text-embeddings-inference`) は 1 回も動かしていない。**§1.2 の仮説は
  **検証できていない。**Docker と cargo の両方が塞がっているため (5.1)。
  「TEI が駄目だった」ではなく「**この機では試せなかった**」である
- **8GB 機での確認はしていない。**この機は 12 GB (5.0)。5.4 は絶対値で書いてある
- **`/v2/rerank` と `/score` は叩いていない。**`/v1/rerank` で足りたため
- **精度は 24 問のみ。**統計的な差を主張できる規模ではない
- **`CPATH` を外して起動できるかは試していない。**要らないかもしれない

## 5.9 再現に使ったもの

- 測定スクリプトは `~/rrwork/` に置いたままで、**repo には入れていない**
  (測定の使い捨てコードなので)
- 入力は `eval/fixtures/normalized-corpus/` と `eval/golden-queries-fixture-b.jsonl`
  **のみ。**repo 外の文書は 1 件も使っていない (§2)
- HF cache は `~/.cache/huggingface` に 9.1 GB (Qwen3-VL-Embedding-2B 4.0 GB を含む)
