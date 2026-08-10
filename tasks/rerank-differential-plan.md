# Reranker の効果測定 — 経路の設計と、途中で判った阻害要因

**状態: 経路は決まった。器はまだ揃っていない。** [2026-08-10]

`crates/kio-adapter/src/local_rerank.rs` は書けた (`4cb182c`)。残るのは
**「その reranker が検索を良くするのか」を測ること**で、この文書はその経路の記録。

着手条件は `tasks/word-lane-measurement.md` §6 で決めた —
**順位の変更は契約テストでは検証できない**ので、eval の on/off 差分を要求する。

---

# 1. 経路 — 2 パスに割る

3 台の制約が噛み合って、素直な経路が無い:

| | |
|---|---|
| CI | GPU が無く、今後も無い |
| GPU 機 | Rust が実行できない (os error 4551) ので `kio` が動かない |
| この Mac | NVIDIA GPU が無い。torch も未導入 |

そこで**測定を 2 つに割り、git で繋ぐ**:

```
eval/rerank_dump.py   (Mac)     search      -> rerank-input.json
tasks/... のブリーフ  (GPU 機)   rerank      -> rerank-output.json
eval/rerank_apply.py  (Mac)     並べ替え適用 -> Recall@10 before/after
```

Mac 側は候補を **text lane が返した順のまま**記録し、evidence pointer の
byte span から**索引が持っているのと同じ文字**を復元する (03 §8.1)。
baseline の Recall@10 も Mac 側で計算するので、**後半を信用する必要が無い**。

`eval/rerank_dump.py` は書けていて、動く。

---

# 2. 判った阻害要因 — 合成コーパスでは差が出ようがない

dump を実走させて判った。**合成 history コーパスでは、reranker は
Recall@10 を動かせない。**

25 問を dump したときの、1 問あたりの候補数:

```
1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 2 2 3 3 3 6 7 7 8 100
```

**25 問中 24 問が候補 10 件以下。**候補が 10 件以下なら、どう並べ替えても
**上位 10 件の集合は同じ**なので、Recall@10 は定義上動かない。
動きうるのは 100 件返った 1 問だけ。

理由は語レーンのときと同じである。**合成コーパスの anchor が語彙的に
特異すぎる。**FTS の MATCH が 1〜3 件に絞り込んでしまい、
reranker が並べ替える対象が存在しない。reranker は
**もっともらしい候補が多数あるとき**にしか意味を持たない。

これは「reranker が効かない」ではなく「**この器では問えない**」である。

## 2.1 リポジトリは既に同じことを知っていた

`eval/register_fixture.py` の docstring:

> 合成 `run_eval.py` は 1.0/1.0/1.0 で目標 0.8 に対し天井に張り付いており、
> 劣化を測れない。24 問の fixture-B は直近 0.9167 (hard3 は 6/8) で、
> 合成セットに無い伸びしろがある。

**独立に同じ結論に着いた。**短問 24 問 (`golden-queries-short.jsonl`) を
足したのも同じ理由だったが、あれは*クエリ*の穴を埋めたのであって、
*コーパス*の密度は変えていない。

---

# 3. 次の一手

**器を fixture-B に替える。**`eval/fixtures/normalized-corpus/corpus/`
(1,015 文書、リポジトリ内) が正しい対象で、`golden-queries-fixture-b.jsonl`
の 24 問が自然文の日本語質問になっている。GPU 機の精度測定 (§5.6) も
この corpus を使っていた。

手順:

1. `eval/register_fixture.py` で fixture 環境を作る
2. **候補密度を先に確認する。**fixture-B で 1 問あたり何件返るかを数え、
   10 件を超えることを確かめてから先へ進む。ここが 10 件以下なら、
   reranker はこの器でも測れない
3. `rerank_dump.py` の対象を fixture 環境へ向ける
4. GPU 機のブリーフを書く (入力 JSON の形は dump が出したものそのまま)
5. `rerank_apply.py` を書く

**2 を飛ばさないこと。**§2 は「測る前に器を確かめなかった」ことで
1 往復ぶん無駄にした記録である。

## 3.1 注意 — scope は再帰しない

03 §253 は **scope 直下のファイルだけ**を管理対象とし、サブフォルダは
明示的に含めない (横断は scope_registry + aggregator の仕事、05 §1.8)。
fixture corpus は深く入れ子なので、**1 ディレクトリ 1 scope** で登録する
必要がある。`register_fixture.py` はそのために在る。

（この挙動を欠陥と誤認して 1 度調べ直した。仕様どおりである。）

## 3.2 `--limit` の天井

CLI の `--limit` は 100 で頭打ちで、05 §1.3 の `candidate_depth` は 200。
プロセスの外からは上位 100 しか見えないので、この測定は
**reranker が回復しうる量の下限**しか出せない。統合後の実装は 200 を見る。
