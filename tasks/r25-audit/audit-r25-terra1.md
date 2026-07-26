READ-PROOF
1. crates/kio-cli/src/main.rs の総行数: 24688
2. tasks/step4b-backlog.md の総行数: 446
3. docs/05-runtime.md の総行数: 1319
4. tasks/step4b-backlog.md の最終 2 行を verbatim (原文のまま、改行位置も保つ):

```text
→ **「見つからない」と報告する突合は、既知の陽性例で先に自己検証すること** (必ず見つかるはずの
   1 件を通す)。→ **同じ事実を 2 つの独立した方法で測ったら、食い違いは対象ではなく計測を先に疑う。**
```

## Part A

### [A1] 時間選択子付き横断検索が current replica で再採点される

- 重大度: major
- 対象: `docs/05-runtime.md:557-563`、`crates/kio-cli/src/main.rs:1948-1953, 2805-2814, 3253-3262`
- 根拠:
  - `docs/05-runtime.md:559-563`
    > - 時間選択子が無い (`--at` / `--all-history` / `--since` / `--include-deleted` のいずれも未指定)  
    > 満たさないものは **scatter-gather 経路へ委譲する**。
  - `crates/kio-cli/src/main.rs:3256-3262`
    > let global_ranks = global_ranks_for(  
    >     &searched,  
    >     scope_mode,  
    >     query_plan.match_expr.as_deref(),  
    >     query_vec_for_ranks,  
    >     rrf_config,  
    > );
  - `global_ranks_for` の引数には `TimeSelector` も cursor 状態も無く、時間選択子は per-scope 呼出しだけに渡されている。
- 何が起きるか: `--since`、`--all-history`、`--include-deleted` を付けた複数 scope 検索でも、候補は時点条件で選ぶ一方、順位は current replica の全文書集合で付け直される。時点外の文書が BM25 の統計・上位 `candidate_depth` を占有し、時点内候補が global rank を失うため、履歴検索の順位が指定時点の集合に対する順位でなくなる。
- 再現手順: 静的指摘。2 scope に、`--since 1h` の対象外だが同一語に強く一致する文書を `candidate_depth` 超、対象内文書を 1 件置き、`kio search "<3文字以上の語>" --since 1h --text` を実行する。per-scope SQL は `created_at >=` を適用するが、無条件の `global_ranks_for` は selector を受け取らないため current replica で再採点する。
- backlog との関係: 既知の範囲外への波及 (I19 の Stage 1 は候補選択を per-scope に残す設計であり、非既定検索を fallback せず再採点することは記載されていない)。

### [A2] replica が解決済み live 集合ではなく全コミット済み chunk を複製する

- 重大度: major
- 対象: `docs/03-data-model.md:309-320`、`crates/kio-cli/src/main.rs:2054-2061, 2081-2084, 4738-4752`、`crates/kio-index/src/aggregator.rs:365-372`
- 根拠:
  - `docs/03-data-model.md:309-310`
    > 7. aggregator は候補の「選択と採点」を担い、liveness 判定を再実装しない。  
    >    refresh 時に scope 側で解決済みの live chunk 集合だけを持つ
  - `crates/kio-cli/src/main.rs:2054-2061`
    > Membership is `first_seen_commit IS NOT NULL` — the chunk is committed  
    > rather than mid-write. The query-time liveness filters (cursor bound,  
    > config-generation association, eligible identity, ancestor gate) are  
    > deliberately NOT re-derived here
  - `crates/kio-cli/src/main.rs:2081-2084`
    > FROM chunks c  
    > LEFT JOIN chunk_vec v ON v.chunk_id = c.chunk_id  
    > WHERE c.first_seen_commit IS NOT NULL
- 何が起きるか: 現在の config association や `kio_eligible_identity` から外れた chunk も replica に残り、`agg_fts` の N・df・上位候補を汚染する。per-scope 経路では除外される正しい候補が、global top `candidate_depth` に入れず text 項を失う。結果として既定検索でも RRF が正しい live corpus の順位にならない。
- 再現手順: 静的指摘。2 scope を登録し、一方に旧 config の同一語一致 chunk を `candidate_depth` 超、もう一方に現 config で適格な chunk を置く。per-scope FTS は `chunk_config_generations` と `kio_eligible_identity` を `EXISTS` で検査するが、projection は `first_seen_commit` のみで複製するため、後者は global rank を得ない。
- backlog との関係: 新規 (I19 の「per-scope が候補選択を担う」は、採点母集団を live 集合にしなくてよいという意味ではない)。

### [A3] 失敗した全射影が後続 delta により最新世代として誤って確定される

- 重大度: major
- 対象: `docs/05-runtime.md:492-495`、`crates/kio-cli/src/main.rs:2150-2174, 2188-2204, 1989-1991`、`crates/kio-index/src/aggregator.rs:280-282, 315-320`
- 根拠:
  - `docs/05-runtime.md:492-494`
    > **スタンプは最後に書く。** generation スタンプがこの投影の commit marker であり、  
    > その手前で落ちた更新はスタンプが古いまま残って次の検索に再射影させる。
  - `crates/kio-index/src/aggregator.rs:280-282`
    > if self.scope_generation(scope_id)?.is_none() {  
    >     return Ok(false);  
    > }
  - `crates/kio-index/src/aggregator.rs:315-320`
    > UPDATE agg_scopes SET index_generation = ?2, refreshed_at = ?3  
    > WHERE scope_id = ?1
- 何が起きるか: replica が世代 G1 のまま、正本が G2 へ全置換された際に `write_through_projection` が失敗すると、次の埋め込み/reuse delta が既存 scope であることだけを確認して G2 をスタンプする。本文集合は G1 のままなのに、検索側は G2 と一致すると判断して refresh を飛ばす。古い本文・削除済み本文が corpus 統計と順位に残る。
- 再現手順: 静的指摘。G1 の replica を持つ scope で、G2 への再構築後に projection を失敗させ、その後に成功する embedding delta を流す。`apply_delta` は保存済み世代との等値比較をせず G2 を記録し、`global_ranks_for` は世代一致で `continue` するため、この状態は次検索で修復されない。
- backlog との関係: 既知の範囲外への波及 (I21 は「未射影 scope に delta のみでスタンプしない」点を修正済みだが、ここでは scope は存在し、世代だけが古い)。

### [A4] pure-short query の横断 hybrid が再び異尺度 RRF になる

- 重大度: major
- 対象: `docs/05-runtime.md:94-112`、`crates/kio-cli/src/main.rs:2025-2049, 2217-2219, 5906-5909`、`crates/kio-index/src/aggregator.rs:395-419`
- 根拠:
  - `docs/05-runtime.md:104-109`
    > **全 unit が 3 文字未満の場合のみ**、従来どおり短語 instr 条件を text / vector 両バックエンド  
    > 共通の eligibility 述語として候補確定 (candidate_depth 充足前) に AND 適用する。
  - `crates/kio-cli/src/main.rs:2025-2030`
    > if let Some(expr) = match_expr {  
    >     match replica.text_scores(expr, depth) {  
    >         Ok(scores) => {  
    >             ranks.text = kio_index::aggregator::text_ranks(&scores);  
    >             ranks.scored_text = true;
  - `crates/kio-cli/src/main.rs:2217-2219`
    > A lane the replica did not score (text-only mode has no query vector; a  
    > pure-short query has no MATCH expression) keeps whatever rank it already  
    > carried
- 何が起きるか: 例えば `認証` のような 2 文字 query は `match_expr = None` となる。text は per-scope LIKE 順位のまま残る一方、hybrid の vector は全 replica を短語 `instr` 条件なしで採点する。その結果、local text rank と global vector rank を再び加算し、短語に一致しない文書まで vector の top `candidate_depth` を占有する。
- 再現手順: 静的指摘。互換な embedding を持つ 2 以上の scope で `kio search "認証" --hybrid` を実行する。query plan は pure-short で `None` を返し、aggregator は text を採点せず、`vector_scores(query, limit)` は短語を受け取らず全 vector を走査する。
- backlog との関係: 既知の範囲外への波及 (I17/I19 の global rank 修正は MATCH 経路にしか適用されず、pure-short 経路で同じ混合が復活している)。

### [A5] profile 切替が sibling の旧 `chunk_vec` を残し、互換判定をすり抜ける

- 重大度: major
- 対象: `docs/03-data-model.md:521-527`、`crates/kio-index/src/embedding_store.rs:150-154, 211-245, 278-285`、`crates/kio-cli/src/main.rs:15136-15140, 15671-1578, 15857-15861`
- 根拠:
  - `crates/kio-cli/src/main.rs:15857-15861`
    > Two chunks with identical bodies but different filenames therefore get  
    > distinct `embedding_hash`es (and distinct vectors), never a shared one.
  - `crates/kio-index/src/embedding_store.rs:211-215`
    > DELETE FROM embeddings  
    > WHERE target_type = 'chunk' AND target_id = ?1 AND profile_hash <> ?2
  - `crates/kio-index/src/embedding_store.rs:278-285`
    > DELETE FROM chunk_vec WHERE chunk_id = ?1  
    > INSERT INTO chunk_vec(chunk_id, embedding) VALUES (?1, ?2)
- 何が起きるか: 同じ本文で異なる filename context を持つ A/B を旧 profile P1 で埋め込んだ後、P2 の batch 結果が A だけ先に届くと、A の書込みは同じ `text_hash` の P1 source rows を全削除する。しかし B は別 `embedding_hash` のため link 対象にならず、B の P1 `chunk_vec` は残る。profile 判定は `embeddings` だけを読むので P2 のみと誤認し、B の P1 vector を P2 query と比較する。
- 再現手順: 静的指摘。filename が異なり本文が同一の A/B を P1 で index し、P2 への切替後に batch 結果を A のみ返す。partial result は受信済み group を逐次 `persist_group_vector` する実装であり、B は旧 vector のまま残る。この連鎖は SQL の削除対象と `chunk_vec` の更新対象が異なるため必ず起こる。
- backlog との関係: 新規。

### [A6] 絞り込み横断検索が未選択・不互換 profile の vector を global rank に混入させる

- 重大度: major
- 対象: `docs/05-runtime.md:553`、`crates/kio-cli/src/main.rs:1625-1651, 1972-1976`、`crates/kio-index/src/aggregator.rs:163-168, 395-419`
- 根拠:
  - `docs/05-runtime.md:553`
    > embedding profile が全 scope で一致しない場合、横断部分は text (BM25 rank) のみで統合する
  - `crates/kio-cli/src/main.rs:1646-1651`
    > for exec in exec_scopes {  
    >     match scope_embedding_state(&exec.target.kio_dir) {
  - `crates/kio-index/src/aggregator.rs:163-168`
    > CREATE TABLE IF NOT EXISTS agg_embeddings (  
    >     chunk_rowid INTEGER PRIMARY KEY,  
    >     scope_id    TEXT NOT NULL,  
    >     vector      BLOB NOT NULL,  
    >     dimensions  INTEGER NOT NULL
- 何が起きるか: `--scope ... --descendants` で選ばれた A/C が互換でも、対象外 B が同じ dimensions・別 profile の vector を replica に持つと、事前互換確認は A/C だけで成功する。絞り込み検索は B を replica から削除せず、`vector_scores` は profile hash ではなく dimensions だけで B を cosine 採点する。B が上位を占めると A/C の vector rank がずれ、hybrid の RRF が壊れる。
- 再現手順: 静的指摘。互換 profile の A/C を同一 subtree、同 dimensions の別 profile B を別 subtree に置き、B を先に index する。B が query に近い vector を持つ状態で `kio search "<3文字以上の語>" --scope <親> --descendants --hybrid` を実行する。global scorer は B を含む全 `agg_embeddings` を走査し、B は候補として返らなくても順位を消費する。
- backlog との関係: 新規。

## Part B

### 計画

| 順位 | 作業 | なぜこの順位か | 概算規模 | 前提・リスク |
|---|---|---|---|---|
| 1 | scope 側で解決済み live projection を共通化し、時間選択子・cursor replay では aggregator を必ず fallback させる | A1/A2 のままでは既定・履歴の双方で採点母集団が不正確で、以後の品質測定も信用できない。 | 1 週間以上 | liveness を replica 側で再実装しない。config・identity・時点・短語を含む契約テストが必要。 |
| 2 | `apply_delta` に「保存済み generation と入力 generation の一致」を前提条件として追加する | A3 を先に止めないと、一時的な cache 書込み失敗が永続的な偽 freshness へ変わる。 | 1 日未満 | 世代不一致では何も書かず次検索の full refresh に委ねる。失敗→delta→検索の回帰試験を追加する。 |
| 3 | profile 切替時の `embeddings` / `chunk_vec` 更新を原子的に整合させる | A5 により互換判定済みでも旧 vector が検索に残る。profile 移行中の partial batch を安全に扱えない。 | 数日 | contextual embedding、content reuse、secret hold を維持したまま sibling vector を再構築または明示的に無効化する。 |
| 4 | aggregator に profile identity を持たせ、絞り込み検索の global vector corpus を互換 profile に限定する | A6 を残すと、対象外 scope が返却順位を静かに変える。 | 数日 | cache schema migration と再投影が必要。全 scope 不一致時の text fallback / explicit vector の除外契約を固定する。 |
| 5 | pure-short 用の global `instr` scorer を実装する | A4 の有効入力で I17 と同じ異尺度 RRF が再発する。 | 数日 | text/vector の両方で短語 eligibility を candidate-depth 前に適用し、順位を `instr` 位置→chunk_id に固定する。 |
| 6 | I15: `Unreachable` と `Absent` を分離し、到達不能 scope を vector 集計から除外する | registry の死んだ entry 1 件で device 全体が text fallback する既知障害を残せない。 | 数日 | scope ごとの除外理由と `fallback_reason` を分離し、既存 explicit `--vector` の部分成功契約を保つ。 |
| 7 | I16: batch collect の下位エラーを保持し、永久 in-flight を診断・回復可能にする | profile 移行を含む batch 障害の原因が隠れ、課金済み job を手作業 abandon するしかなくなる。 | 数日 | 台帳の unknown settlement と retry/terminal 遷移を変えず、診断情報だけを失わない設計にする。 |
| 8 | Stage 3 の replica 候補選択と `agg_approvals` は後回しにする | 現在の Stage 1 の corpus・freshness・profile が不正確なまま候補選択を移すと、誤順位をより高速に返すだけになる。 | 1 週間以上 | 上位 1〜7 の契約試験と安全性再確認の設計確定後に再開する。 |

判定: 不合格