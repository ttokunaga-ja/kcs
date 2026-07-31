# V3b 実行ブリーフ (GPU 実機)

このファイルはそのまま作業者 (人でもエージェントでも) への指示として読める形にしてある。
`eval/v4/README.md` と `eval/v3/results/README.md` の続きにあたる。

---

# 任務

**MRL 切り詰め (native 2048 → 768) が検索品質をどれだけ落とすかを、24 問 fixture の
recall で測る。** そのうえで `dimensions` を 768 のまま据え置くか native 2048 へ移すかを
決める材料を出す。

なぜ急ぐか: いま `dimensions = 768` と
`tool_profile_hash = sha256:f9f610bb…439a` は**暫定**で、その結果
**恒久コーパスの埋め込みが禁止されている** (`crates/kio-adapter/src/local_embedding.rs:57`
のコメント、`tasks/local-adapter-plan.md` §11)。この凍結を解除できるのは V3b だけである。
Stage 2 は実装としては U7 を残すのみだが、成果を実データに適用できないのはこの 1 件が
理由になっている。

**追加費用はゼロ。** 必要な OCR 済み本文は支払い済みで、repo に入っている。

---

# 先に読むもの (この順で)

1. `eval/v3/results/README.md` — V3a の実測と、そこから V3b へ送られた理由
2. `eval/v3/v3_mrl.py` の docstring — 計器が何を測っているか
3. `eval/fixtures/normalized-corpus/README.md` — コーパスの出所と形
4. `tasks/local-adapter-plan.md` §11 の V3 / V8 行

---

# 環境

| | |
|---|---|
| 必要なもの | Linux + NVIDIA GPU (V3a は RTX 4070 / WSL2 / driver 610.62) |
| サーバ | vLLM 0.26.0 |
| モデル | `Qwen/Qwen3-VL-Embedding-2B` revision `9f2f7e71` |

```bash
vllm serve Qwen/Qwen3-VL-Embedding-2B --runner pooling
```

**`--chat-template` は渡さない。** V3a がそうしており、比較の前提を揃えるため。
渡すと V3a の 0.8037 と地続きでなくなる。

---

# 手順

## 1. V3b 本体

```bash
python3 eval/v3/v3_mrl.py \
  --corpus eval/fixtures/normalized-corpus \
  --queries eval/golden-queries-fixture-b.jsonl \
  --limit 1013 \
  --out eval/v3/results/v3b-mrl.json
```

**`--limit 1013` は必須。** 既定は 400 で、`collect_passages` は `sorted()` 順に 400 件で
打ち切る。コーパスは persona 順に並ぶので p09〜p20 の 12 persona が丸ごと落ち、
answerable が 24 問中 **9 問**まで下がる。`recall_at_k` の足切りは「過半 (12 問) が
引けなければ測らない」なので発火し、`measured: false` だけが返る。
**GPU セッションを 1 回無駄にする。** (2026-07-31 にローカルで実測して確認した数字である)

そのとき返る注記は「index 済み fixture から取り出した Markdown を渡すこと」だが、
**この状況ではその注記は原因を指していない**。コーパスは正しく、足りないのは `--limit`。

`--corpus` は `eval/fixtures/normalized-corpus` (親) を渡す。`…/corpus` を渡すと
golden query の `expected[].path` (`corpus/p01/…` 形式) と部分一致しなくなる。

## 2. 決定性の確認

**2 回走らせて数字が完全に一致することを確かめる。** V3a はそうしており、
一致しなければ計器かサーバのどちらかが非決定的なので、値を採る前にそれを潰す。

## 3. V8(a) — 対称運用のコスト (同じセッションで測れる)

`tasks/local-adapter-plan.md` §11 の V8: Qwen3-Embedding 系は query 側にだけ instruct
prefix を付ける非対称運用が標準だが、Kio は `prompt_template_hash` が (T, I) を 1 組しか
畳まないので**構造的に採れない**。それが品質をどれだけ損しているかを先に測る。

**注意: `v3_mrl.py` はそのままでは測れない。** `embed_one` は
`messages: [{"role":"user","content":[{"type":"text","text": text}]}]` を送るだけで、
system message も instruction も持たない (Kio の `local_embedding.rs` と同形にしてある)。
**`--query-instruction` を足す小改修が要る** — passage 側は素のまま、query 側にだけ
prefix を付けて同じ 24 問を回し、recall を比べる。

比較するのは 2 条件だけでよい:

| 条件 | passage | query |
|---|---|---|
| 現行 (対称) | instruction なし | instruction なし |
| 非対称 | instruction なし | instruct prefix あり |

差が小さければ V8 は「書き留めるだけ」で閉じられる。大きければ、query 用 profile を
分ける仕様改訂の検討に進む材料になる (**その改訂自体はここではやらない** — ゲートの
意味を変える大改訂なので、実測を持って別途裁定する)。

---

# 判定基準

`v3-mrl.json` / `v3b-mrl.json` の `recall.measured` が `true` であることをまず確認する。
`false` なら **recall は出ていない**ので、値を報告しない。理由 (`note` と `answerable`)
を報告する。

**V3a からの予測**: 768 が失った類似度は中央値 0.00445 で、これは native 側の 10 位と
11 位の間隔 0.00394 と同じ桁だった。したがって **recall@10 の差は小さく出るはず**である。

> **大きな recall 差が出たら、それを MRL 幅の効果として報告する前に別の要因を疑うこと。**
> V3a がそう予告している。切り詰め以外の何か (コーパスの取り違え、instruction の混入、
> サーバ設定の差) を先に潰す。

---

# 絶対規則

1. **恒久コーパスを埋め込まない。** V3b の結論が出るまで `dimensions` は暫定である。
   測定は使い捨てのベクトルで完結させる
2. **数字を推測で埋めない。** 測れなかったものは「測れなかった」と書く。この
   リポジトリでは推測値を焼いた事故が実際に起きている (`eval/repin/README.md`)
3. **`--chat-template` を渡さない** (V3a と揃える)
4. **2 回走らせて一致を確認してから**値を採る

---

# 2048 を採る判断になった場合 (ここでは実行しない)

影響範囲だけ先に書いておく。**大きいので、測定と同じセッションで着手しないこと。**

| 変更点 | 場所 |
|---|---|
| vec0 の DDL 幅 | `crates/kio-index/src/fts.rs:955` `CHUNK_VEC_DIMENSIONS` |
| adapter の宣言次元 | `crates/kio-adapter/src/local_embedding.rs:64` `LOCAL_EMBEDDING_DIMENSIONS` |
| `tool_profile_hash` | `dimensions` は hash 入力なので再凍結が要る |
| 既存インデックス | **全再埋め込み** |

---

# 報告フォーマット

```
## V3b 実測

サーバ: vLLM <version> / <GPU> / model rev <rev>
passages: <n>   answerable: <n>/24   measured: <true|false>

| 幅 | recall@10 |
|---|---|
| native 2048 | |
| MRL 768 | |

2 回目の実行と一致: <はい|いいえ>

## V8(a)

| 条件 | recall@10 |
|---|---|
| 対称 (現行) | |
| 非対称 (query 側 instruct) | |

## 判断
768 据え置き / 2048 へ移行 / さらに測定が要る — のどれかと、その根拠

## 更新したファイル
```

## 測定後に更新するもの

- `eval/v3/results/README.md` — V3b の節を足し、V3a の「V3b へ進む」を結論で置き換える
- `tasks/local-adapter-plan.md` §11 の **V3 行** — 現在 ✅ が付いておらず
  `eval/v3/results/` への参照も無い。**V3a が済んでいることすら読み取れない状態**なので、
  V3a / V3b の両方を反映する
- 768 据え置きなら `local_embedding.rs:57` の「V3 が答えるまで暫定」コメントを確定へ

---

# やってはいけないこと

- `--limit` を省く (上記のとおり `measured: false` にしかならない)
- 生のコーパス (`~/kio-baseline-corpus`) を渡す — 24 問中 0 問しか引けない
- `measured: false` の結果から recall を読み取って報告する
- 低い recall を「切り詰めのせい」と決めつける — 計器が足切りを持っているのは
  「候補に無い」と「切り詰めで落ちた」を混ぜないためである
- 2048 への移行をこのセッションで実行する
