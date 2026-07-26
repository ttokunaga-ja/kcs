READ-PROOF
1. crates/kio-cli/src/main.rs の総行数: 24688
2. tasks/step4b-backlog.md の総行数: 446
3. docs/05-runtime.md の総行数: 1319
4. tasks/step4b-backlog.md の最終 2 行を verbatim:

```text
→ **「見つからない」と報告する突合は、既知の陽性例で先に自己検証すること** (必ず見つかるはずの
   1 件を通す)。→ **同じ事実を 2 つの独立した方法で測ったら、食い違いは対象ではなく計測を先に疑う。**
```

## Part A

### [A1] 時間選択子付きの複数 scope 検索にも aggregator を適用している

- 重大度: major
- 対象: `docs/05-runtime.md:559`, `crates/kio-cli/src/main.rs:1948`, `crates/kio-cli/src/main.rs:3256`
- 根拠:

  > `docs/05-runtime.md:559` `- 時間選択子が無い (\`--at\` / \`--all-history\` / \`--since\` / \`--include-deleted\` のいずれも未指定)`

  > `docs/05-runtime.md:562` `満たさないものは **scatter-gather 経路へ委譲する**。`

  > `crates/kio-cli/src/main.rs:1948` `fn global_ranks_for(`

  > `crates/kio-cli/src/main.rs:1951` `    match_expr: Option<&str>,`

  > `crates/kio-cli/src/main.rs:1953` `    config: RrfConfig,`

  > `crates/kio-cli/src/main.rs:3256` `    let global_ranks = global_ranks_for(`

- 何が起きるか: `global_ranks_for` には時間選択子も cutoff も渡されず、呼出し側にも選択子による分岐がない。そのため複数 scope の `--all-history`、`--since`、`--include-deleted` で、時点・履歴条件で絞った候補に対し、時点条件を持たない replica の順位を上書きする。例えば `--since` は規範上 `chunks.created_at >= now - <duration>` で絞るが、期限外の高順位 chunk が replica の上位を占めると、期間内候補は global rank を失い順位が変わる。
- 再現手順: 静的指摘。2 scope に、query に一致する期限外 chunk と期間内 chunk を作り、`kio search <query> --since 1d --mode text` を実行する。scope 側は期間内候補だけを返す一方、replica 採点は期限外 chunk も含めるため、規範どおりの scatter-gather 順位にはならない。
- backlog との関係: 既知だが評価が誤り。I19 は時間選択子の replica 対応を Stage 3 へ繰延しているが、Stage 1 は規範どおり fallback しなければならず、現実装は未対応の replica をすでに使用している。

### [A2] pure-short query で global text rank がなく、per-scope text rank が残る

- 重大度: major
- 対象: `crates/kio-cli/src/main.rs:2025`, `crates/kio-cli/src/main.rs:2217`, `crates/kio-cli/src/main.rs:4683`, `crates/kio-cli/src/main.rs:5906`
- 根拠:

  > `crates/kio-cli/src/main.rs:5906` `        return QueryPlan {`

  > `crates/kio-cli/src/main.rs:5907` `            match_expr: None,`

  > `crates/kio-cli/src/main.rs:4683` `    match match_expr {`

  > `crates/kio-cli/src/main.rs:4685` `        None => execute_like_fallback(conn, filter),`

  > `crates/kio-cli/src/main.rs:2025` `    if let Some(expr) = match_expr {`

  > `crates/kio-cli/src/main.rs:2217` `/// A lane the replica did not score (text-only mode has no query vector; a`

  > `crates/kio-cli/src/main.rs:2218` `/// pure-short query has no MATCH expression) keeps whatever rank it already`

- 何が起きるか: 全 token が短い query では scope ごとに `instr` fallback で text rank を作るが、aggregator には同等の global `instr` 採点がない。text-only では local rank のまま横断整列され、hybrid では global vector rank と local text rank を再び加算する。これは replication が解消するはずだった「異なる母集団の順位の混合」を pure-short query にだけ再導入する。
- 再現手順: 静的指摘。2 scope に短語 `AI` を含む chunk を1件ずつ置き、scope A の一致位置を遅く、scope B を早くし、scope ID は A が先になるようにする。`kio search AI --all-scopes --mode text` では両者が local rank 1 となり scope ID で A が先行しうるが、規範の global bounded-LIKE 順序では B が先である。
- backlog との関係: 新規。

### [A3] replica が「解決済み live 集合」ではなく、全 committed `chunks` 行を複製する

- 重大度: major
- 対象: `docs/03-data-model.md:309`, `docs/05-runtime.md:428`, `crates/kio-cli/src/main.rs:2054`, `crates/kio-cli/src/main.rs:2081`
- 根拠:

  > `docs/03-data-model.md:309` `7. aggregator は候補の「選択と採点」を担い、liveness 判定を再実装しない。`

  > `docs/03-data-model.md:310` `   refresh 時に scope 側で解決済みの live chunk 集合だけを持つ`

  > `docs/05-runtime.md:430` `**liveness 判定が 2 箇所になり、必ず乖離する**。代わりに、refresh 時に **scope 側の既存コードで live chunk`

  > `crates/kio-cli/src/main.rs:2054` `/// Membership is \`first_seen_commit IS NOT NULL\` — the chunk is committed`

  > `crates/kio-cli/src/main.rs:2081` `            "SELECT c.chunk_id, c.text, c.heading_path, v.embedding`

  > `crates/kio-cli/src/main.rs:2084` `             WHERE c.first_seen_commit IS NOT NULL",`

- 何が起きるか: `chunks` は append-only であり、デフォルト検索は HEAD の `tree_entries` と対象 config association を使う。にもかかわらず replica は `first_seen_commit` だけで旧 config・旧 identity・現在の tree に存在しない chunk まで FTS/vector corpus に入れる。これらが BM25 の N/df/avgdl を変え、また global top `candidate_depth` を占有すると、実際に返せる current candidate が global rank を失い、RRF 順位が誤る。
- 再現手順: 静的指摘。過去 config または過去 tree にだけ属する committed chunk を含む scope と、現在の matching chunk を持つ別 scope で通常の複数 scope 検索を行う。scope 側の liveness filter は前者を候補から除外するが、replica は前者を採点母集団へ残す。
- backlog との関係: 新規。

### [A4] 非回転の in-place 書込みで write-through に失敗すると、replica が恒久的に stale になる

- 重大度: major
- 対象: `crates/kio-cli/src/main.rs:1989`, `crates/kio-cli/src/main.rs:2182`, `crates/kio-cli/src/main.rs:2202`, `crates/kio-cli/src/main.rs:14757`
- 根拠:

  > `crates/kio-cli/src/main.rs:2182` `/// they send that instead of a re-projection; and they leave \`index_generation\``

  > `crates/kio-cli/src/main.rs:2183` `/// untouched unless something else in the command rotates it, which is exactly`

  > `crates/kio-cli/src/main.rs:2184` `/// why a reader-driven refresh cannot be relied on to notice them.`

  > `crates/kio-cli/src/main.rs:2202` `    if let Err(error) = replica.apply_delta(&scope_id, &generation, delta, replica_now_ms()) {`

  > `crates/kio-cli/src/main.rs:2203` `        log_aggregator_degraded(&format!("write-through delta {scope_id} failed: {error}"));`

  > `crates/kio-cli/src/main.rs:1989` `        let cached = replica.scope_generation(&scope.scope_id).ok().flatten();`

  > `crates/kio-cli/src/main.rs:1990` `        if cached.as_deref() == Some(scope.index_generation.as_str()) {`

  > `crates/kio-cli/src/main.rs:1991` `            continue;`

- 何が起きるか: 既に generation `G` で replica 化済みの scope に同期 embedding/reuse が vector を追加しても、source の generation は変わらない。`apply_delta` が一時的に失敗するとエラーはログだけで成功扱いになり、cache 側の stamp も source 側も `G` のまま残る。次回検索は equality により refresh を skip するため、新 vector は global vector rank に永久に現れず、無関係な再構築等まで順位が劣化する。
- 再現手順: 静的指摘。既に replica 化済みの scope で同期 embedding を実行し、`aggregator.sqlite` の open または transaction が `Err` となる状態にする。write-through 後に cache を正常化しても、source/cache の generation が等しいため次の検索は再射影しない。
- backlog との関係: 既知だが評価が誤り。I21 は write-through を実装完了としているが、非回転 writer の失敗後に再同期する経路が成立していない。

### [A5] purge が replica の本文削除に失敗しても成功を返す

- 重大度: major
- 対象: `crates/kio-cli/src/main.rs:2150`, `crates/kio-cli/src/purge.rs:502`, `docs/05-runtime.md:924`
- 根拠:

  > `crates/kio-cli/src/main.rs:2150` `/// Never fails the caller. Losing this write leaves the replica's stamp behind`

  > `crates/kio-cli/src/main.rs:2160` `        Err(error) => {`

  > `crates/kio-cli/src/main.rs:2161` `            log_aggregator_degraded(&format!("write-through read {scope_id} failed: {error}"));`

  > `crates/kio-cli/src/purge.rs:502` `            crate::write_through_projection(repo.kio_dir());`

  > `crates/kio-cli/src/purge.rs:503` `            Ok(attach_working_tree_warning(`

  > `docs/05-runtime.md:924` `- **device replica (\`~/.cache/kio/aggregator.sqlite\`) の当該 scope の投影** — purge 成功時に`

  > `docs/05-runtime.md:926` `  読み手任せにすると「誰も検索しない間、purge した本文が device の cache に読める形で残る」。`

- 何が起きるか: purge の正本削除と generation 回転が成功した後、cache 再射影が失敗しても `write_through_projection` は失敗を返さず、purge は `success_report` を返す。従って purge 対象本文は旧 `aggregator.sqlite` に残り、次回検索または手動の cache 削除まで読める。これは「purge 成功時に本文を消す」という規範に反する。
- 再現手順: 静的指摘。対象本文が既に replica にある状態で、cache の再射影が `Err` となる条件で purge を実行する。`write_through_projection` はログ後 return し、`purge.rs:503` は成功結果を構成するため、本文残存と成功表示が同時に成立する。
- backlog との関係: 既知だが評価が誤り。I21 は purge の replica 再射影を「修正済み」とするが、実装は成功時の試行だけで、削除保証にはなっていない。

## Part B

### 計画

| 順位 | 作業 | なぜこの順位か | 概算規模 | 前提・リスク |
|---|---|---|---|---|
| 1 | purge の完了条件を cache 本文削除まで拡張する | 成功表示後に秘匿本文が残る状態を先に止める必要がある。 | 数日 | purge 専用の retry/journal または失敗結果を設計し、通常の cache 障害を全書込みの障害へ拡大しない。 |
| 2 | 非回転 writer 用の durable な replica-dirty/retry 機構を作る | A4 は一時障害が無期限の順位劣化へ変わるため、手動回復前提にできない。 | 数日 | generation 回転だけで代替する場合は cursor 契約への影響を同時に検証する。 |
| 3 | aggregator の採点母集団を規範へ合わせる | A1〜A3 により、通常検索・短語検索・履歴検索の順位品質がいずれも壊れる。 | 1週間以上 | scope 側の live-set resolver を共有化し、predicate を aggregator 側へ複製しない。pure-short 用の global `instr` または明示 fallback も必要。 |
| 4 | I21 の同期 embedding と `reindex --at` の cursor 無効化を実装する | rank が変わった後にページ継続すると、重複・欠落・順序不安定を招く。 | 数日 | page-N と write-through/retry の組合せを契約テストで固定する。 |
| 5 | H2-7 の reachability 読取り失敗を fail-closed で検証・修正する | 破壊的 repair が参照中 object を orphan と誤認する候補を、運用拡大前に閉じる。 | 数日 | 読取り不能と「未参照」を明確に分離し、削除対象を縮める方向で設計する。 |
| 6 | I15 の unreachable scope を vector availability から分離する | 古い registry entry 一つで device 全体が text fallback する現象を防ぐ。 | 数日 | registry prune と検索時 exclusion の責務を混同しない。 |
| 7 | Batch の F5〜F9 を一括して堅牢化する | lane 分裂、20MB 上限、profile 不一致、未知状態、一覧打切りは実 API 運用で再発しやすい。 | 1週間以上 | 実 wire fixture・pagination・サイズ境界を回帰テストへ追加する。 |
| 8 | I13 の budget 再評価・保留可視化を実装する | 実支出に余裕があっても索引化が止まり、復旧に `--override-budget` が必要な状態を解消する。 | 1週間以上 | cap を無視せず、予約・確定額・再評価時点を分ける。 |
| 9（後回し） | Stage 3 の replica 候補選択・approval 投影 | 現行 Stage 1 の live-set、fallback、purge、cursor 契約が未修正のまま候補選択を移すと、安全性再確認の新実装まで同時に増える。 | 着手しない | 上記 1〜4 の契約テストと failure-injection が揃うまで保留する。 |

判定: 条件付き合格