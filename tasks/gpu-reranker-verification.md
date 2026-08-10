# Reranker の GPU 実機検証 ブリーフ

このファイルはそのまま作業者 (人でもエージェントでも) への指示として読める形にしてある。
実行には **NVIDIA GPU + Linux** が要る。**WSL2 で構わない** — 必要なのは Linux と CUDA
であって Windows 実機ではない (`tasks/gpu-local-ocr-verification.md` と同じ条件)。

**状態: 未実施。** [2026-08-10]

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
