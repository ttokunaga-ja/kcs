# 実装ブリーフ — 横断検索を replica 単独経路へ移す

**この文書だけで作業できるように書いてある。**チャット履歴を参照しないこと。

**仕様の正本は [docs/05-runtime.md §1.8](../docs/05-runtime.md) と
[docs/03-data-model.md §4](../docs/03-data-model.md)。**本ブリーフと食い違ったら**仕様が正**。
仕様が誤っていると判断した場合は、実装を進める前にその旨を報告すること。

---

# 0. 何をする作業か

`kio search` の横断検索を、**device-level の replica (`aggregator.sqlite`) 単独**で行うようにする。

現状は逆になっている。**per-scope 経路が全スコープの `.kio` を開いて候補を出し、replica は
その候補に順位を付け直しているだけ**である。replica は候補を 1 件も返していない。

```
現状:  全スコープの .kio を開く → 各スコープで SQL → per-scope RRF → (条件が合えば) replica が再採点
目標:  replica を 1 回引く
```

**確認方法** (最初にこれを自分の目で見ること):

```bash
grep -n "search_one_scope(\|let global_ranks" crates/kio-cli/src/main.rs
```

`search_one_scope` の呼び出しが `multi_scope::run_ordered(exec_scopes.len(), ...)` の中にあり、
**無条件**であること。`global_ranks` の算出がその**後**にあること。これが「replica が候補を
返していない」の実体である。

## 0.1 この作業で守る規則 (仕様で今日確定した)

1. **検索が読む索引は `aggregator.sqlite` ただ 1 つ。**scope 数によらず
   `.kio/index/sqlite.db` を `kio search` が引いてはならない
   ([05 §1.8「検索は `.kio/index/sqlite.db` を引かない」](../docs/05-runtime.md))
2. **反映順序は「各 scope の索引 → aggregator」。**逆順は「検索に出るのに開けない結果」を作る
   ([05 §1.8「書き込み順序」](../docs/05-runtime.md))
3. **replica は live + 過去の全 chunk を 1 表で持ち、生存で絞るのは `WHERE` 句。**
   分表にしてはならない ([03 §4 不変条件 7](../docs/03-data-model.md))
4. **後方互換の分岐を書かない。**未リリースなので旧データは存在しない
   ([10 §12.5](../docs/10-operations.md))

---

# 1. 作業項目 (7 件)

**番号は [05 §1.8「候補選択の所在」](../docs/05-runtime.md) の表と対応している。**

行番号は変わりうるので、**シンボル名で grep すること**。以下の行番号は目安。

| # | 内容 |
|---|---|
| 1 | `agg_chunks` に**生存区間**の列 (`first_seen_commit` / 失効 commit) を足し、射影を全 chunk に広げる |
| 2 | `agg_chunks` に **`raw_hash` / byte span / `section_id`** を足す |
| 3 | replica 側の**短語レーン** (`agg_chunks.text` への bounded LIKE) |
| 4 | **replica が候補を返す経路。**入った時点で per-scope 呼び出しを検索から削除 |
| 5 | **purge barrier を replica 経路側に持たせる** |
| 6 | `aggregator_decline_reason` を**関数ごと**削除 |
| 7 | `aggregator` object から `applied` / `fallback_reason` を削除 |

## 1.1 【最重要】4 と 5 は同一の変更で行うこと

**分けてはならない。**理由:

purge barrier は現在 `ReadBarrierCheckpoint` として **per-scope 経路のコードパスに埋まっている**。
3 点ある (`grep -n "ReadBarrierCheckpoint\|\.recheck()" crates/kio-cli/src/main.rs`):

- `search_one_scope_inner` 冒頭の `open`
- 同関数末尾、そのスコープの候補を返す直前の `recheck`
- `run_search_inner` の全スコープマージ後の第 3 バリア

**4 だけを実施して per-scope 経路を消すと、この 3 点も一緒に消える。**そして
per-scope 経路を前提にした既存テストも同時に無効化されるので、**検査が消えたことに
誰も気付かない。**purge は法務・秘匿の操作であり、これは静かなセキュリティ後退である。

**受け入れ条件:** purge journal が活性なスコープの chunk が、**replica 経路の検索結果に
出ないこと**を検証するテストを追加し、**そのテストが barrier を外すと RED になることを
実際に確認して報告すること。**

---

# 2. 実装の手掛かり

## 2.1 replica の現状

`crates/kio-index/src/aggregator.rs`。

- 表は `agg_scopes` / `agg_chunks` / `agg_fts` / `agg_embeddings` の 4 つ
- **`agg_chunks` は順位に要る列しか持たない** (`scope_id` / `chunk_id` / `text` / `heading_path`)。
  `raw_hash` も byte span も無いので、**Evidence Pointer を組み立てられない。
  これが「候補を返せない」の根本原因**である (項目 2)
- 公開 API は `text_scores` / `vector_scores` / `image_vector_scores` / `corpus_size` /
  `scope_ids` / `refresh_scope` など。**候補を返す関数が存在しない**
- module doc 冒頭が今も "read replica of every scope's **live** chunks" と書いている。
  項目 1 で書き換えること

## 2.2 削除対象

`crates/kio-cli/src/main.rs`。シンボルで grep すること。

| シンボル | 扱い |
|---|---|
| `aggregator_decline_reason` | **関数ごと削除** (項目 6)。今も 4 条件 (`single_scope` / `time_selector` / `text_lane_not_rankable` / `vector_lane_not_rankable`) を返す。**全部撤回済み** |
| `cursor_pinned_scatter_gather` | 削除。受け皿が無くなる |
| `regrade_vector_rank_globally` | **削除。**doc comment が「撤回された CT3-MULTI-002 がこの経路では引き続き支配する」と自ら書いている。経路ごと消える |
| `apply_global_ranks` | 役割が変わる。候補に順位を「付け直す」関数ではなくなる |
| `search_one_scope` / `search_one_scope_inner` | **検索からは呼ばない。**ただし関数自体を消せるかは要確認 — refresh の射影が同じ解決コードを使う (下記 2.3) |

## 2.3 射影は per-scope の解決コードを使い続けること

**[03 §4 不変条件 7](../docs/03-data-model.md) が「liveness 判定を再実装しない」を要求している。**
replica 側で eligibility 述語を組み直すと liveness 判定が 2 箇所になり、必ず乖離する。

射影は per-scope 検索と**同じ関数**を呼ぶ (`current_history_plan_from_cache` +
`install_eligible_identities`)。項目 1 で射影範囲を全 chunk に広げるときも、
**述語を replica 側に書き直すのではなく、scope 側が解決した答えに生存区間の列を付けて運ぶ。**

## 2.4 短語レーン (項目 3)

per-scope 側の短語経路を読むこと (`grep -n "short_token_instr_sql\|execute_like_fallback"`)。
3 文字未満のクエリは FTS5 の MATCH が空になるので `chunks.text` への bounded LIKE
(`instr` ベース、上限 `candidate_depth`) に落ちる。

**同じ述語を `agg_chunks.text` に対して実装すること。**2 つの実装を持つと
短語検索の結果が経路によって変わる。**共通化できるなら共通化すること。**

日本語では 2 文字語 (認証・設計・課金・障害・監査) が最も普通のクエリ長なので、
**これは辺縁事例ではなく主要経路**である。

---

# 3. 書き換えが要る既存テスト

**以下は撤回済みの規範を固定している。消すのではなく、新しい契約に書き換えること。**

| テスト | 何を固定しているか |
|---|---|
| `ct3_multi_020_the_replica_projects_live_chunks_not_every_committed_row` | **不変条件 7 が禁じた「live だけを持つ」状態。**項目 1 と同時に書き換える |
| `ct3_multi_014` / `ct3_multi_015` | `fallback_reason` に `time_selector` / `text_lane_not_rankable` を期待している。**両方とも撤回済み** |
| `ct3_multi_003_diversify_caps_raw_hash_across_scopes` | 4 スコープの同一内容が 3 件に丸められることを期待。**別件だが関連** — 下記 5 参照 |

`crates/kio-cli/tests/step3_p0_contract.rs` にある。

---

# 4. 測定 (省略不可)

**ランキングを変える作業なので、契約テストが緑でも退行を検出できない。**
過去に、1 文書コーパスの契約テスト 4 本が緑のまま実測ランキングが退行した例がある。

## 4.1 使う道具

```bash
python3 eval/run_eval.py --help
python3 eval/run_crossscope.py --help
```

- 評価コーパスは **7 スコープ** (`eval/corpus_spec.py` の `SCOPES`)。横断経路を通る
- `eval/golden-queries-short.jsonl` は **24 問の短語セット** (各 12 文字以下)。
  **項目 3 (短語レーン) の直接の検査になる**
- CI が短語セットを `--min-recall 0.9166666666666666` で門番している
  (`.github/workflows/ci.yml`)

## 4.2 必ず測ること

1. **着手前にベースラインを取り、記録すること。**変更後だけ測っても意味がない
2. **項目 3 の前後で短語セットを測ること。**replica 側の短語レーンが per-scope と
   同じ答えを返すかは、ここでしか判らない
3. **横断 eval (`run_crossscope.py`) の `worst_expected_rank`。**
   [09-mvp-scope.md](../docs/09-mvp-scope.md) に「replica を無効化して比較する」旧手法の
   数字が残っているが、**その手法は再現不能になった** (無効化する対象が無い)。
   **移行後に 16 問すべてで測り直し、その数字を 09 に書くこと** — 特に履歴 8 問は
   従来 per-scope 順位で融合されていたので、`5.38` から**下がるはず**である。
   下がらなければ、それは報告に値する発見である

## 4.3 数字の読み方

24 問のセットでは **1 問 = 0.0417**。これ未満の差は差ではない。

---

# 5. この作業に含めないこと

- **文書単位の検索結果集約** — 別作業。[tasks/search-result-presentation-design.md](search-result-presentation-design.md) §1
- **`max_per_raw_hash` のキーに `scope_id` を足す** — 上記集約と同時に行う。
  ただし `ct3_multi_003` を触る必要が出たら、**期待値を勝手に変えず報告すること**
- **後方互換分岐の削除** — 別作業。[tasks/pre-release-legacy-removal.md](pre-release-legacy-removal.md)
- **reranker の統合**

---

# 6. この機で踏んだ罠 (実話)

- **`cargo test` の出力をパイプで要約しないこと。**パイプの exit code は cargo のものではない。
  失敗しているクレートが「0 failed」に見えた実例がある。**素で実行して終了コードを見る**
- **ビルドしたてのテストバイナリが最初の 1 行を出すまで数分止まる**ことがある。
  ハングに見えたら `ps -o time` を見る (CPU が 0:00.00 なら本当に止まっている、増えていれば待つ)
- **zsh は未クォート展開を語分割しない。**`cargo test $args` は `-p kio-index` を
  1 引数として渡す。コマンドは明示的に書くこと
- **`.claude/worktrees/` は古い複製。**grep すると同名ファイルが二重に出る。
  編集対象はリポジトリルート直下の `crates/` だけ
- **`git add -A` は関係ないファイルを巻き込む。**コミット前に `git status` を見ること

---

# 7. 報告してほしいこと

1. **`cargo test` の素の実行結果** (クレートごと、テスト数の before/after)
2. **4.2 の測定結果** — ベースラインと変更後の両方
3. **§1.1 の受け入れ条件** — purge barrier のテストを、barrier を外して RED にした実験の内容と結果
4. **書き換えた既存テストの一覧**と、それぞれ何を固定する形に変えたか
5. **仕様と食い違うと判断した点があれば、その一覧。**実装を仕様に合わせる前に報告すること
6. **判断に迷って自分で決めた点の一覧**

コミット単位は分けること。特に**項目 4 + 5 は 1 コミット**にすること — 後から
「barrier がいつ消えたか」を追えるようにするため。

コード内のコメントは**英語**、ドキュメントは**日本語** (既存に合わせる)。
