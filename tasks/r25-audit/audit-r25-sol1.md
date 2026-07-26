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

### [A1] embedding の正本が実在せず、SQLite 喪失時に vector を復旧不能にする

- 重大度: fatal
- 対象: `docs/03-data-model.md:28,329-345`, `crates/kio-cli/src/main.rs:14228-14234,7277-7289,7334-7353,15109-15135`, `crates/kio-core/src/cas.rs:973-978`, `crates/kio-index/src/embedding_store.rs:435-466`
- 根拠:

  `docs/03-data-model.md:28`

  > raw / prepared / image / chunk / embedding / manifest / toollock / tree / commit は **CAS object** として `objects/<type>/ab/cd/<digest64>` に保存。

  `crates/kio-cli/src/main.rs:14228-14234`

  ```rust
  /// Generate chunk embeddings for the scope after the SQLite index is rebuilt
  /// (04 §4.3 / 07 §5.3). Enqueues one `TaskType::Embedding` task per pending chunk,
  /// then — if the online opt-in and budget allow — embeds them (batched), writing
  /// the `embeddings` rows (source of truth) and `chunk_vec` (derived KNN copy),
  /// charging the cost ledger under `adapter_kind="embedding"`. Offline leaves tasks
  /// Pending (surfaced by `index_status`). No-op when no embedding adapter is
  /// configured (keeps the default index path unchanged).
  ```

  `crates/kio-cli/src/main.rs:7277-7289`

  ```rust
      // Embeddings live only in SQLite (objects/ holds no embedding objects in the
      // MVP), so snapshot them from the CURRENT db (without removing it) and replay
      // them into the fresh db, then rebuild chunk_vec from them (04 §4.3). This
      // keeps `kio repair --rebuild-db` / reindex from wiping vector search.
      let (preserved, preserved_tree_entries) = if path.exists() {
          let existing = Connection::open(&path).map_err(|err| KioError::schema(err.to_string()))?;
          let rows = embedding_store::snapshot_chunk_embeddings(&existing).map_err(index_to_kio)?;
          let tree_rows = snapshot_tree_entries(&existing)?;
          drop(existing);
          (rows, tree_rows)
      } else {
          (Vec::new(), Vec::new())
      };
  ```

  `crates/kio-core/src/cas.rs:973-978`

  ```rust
      /// PB01/PB02: write a content-addressed embedding/manifest/toollock
      /// object, keyed by `hash_bytes(bytes)`. Idempotent (matching
      /// [`Self::write_object_bytes`]'s "verify existing, don't overwrite"
      /// contract) — used by tests to construct fsck fixtures directly, and is
      /// the storage primitive a future write-path integration would call.
  ```

- 何が起きるか: fully embedded な scope で、仕様上は再生成可能な cache である `.kio/index/sqlite.db` が失われると、`rebuild-db` は `preserved = []` で成功し、過去の vector は復元されない。offline では task が Pending になるだけで、既存 vector の完全な値は消失する。一方、破損 DB が存在する場合は、再構築前に旧 DB の `embeddings` と `tree_entries` を必須読取するため、`tree_entries` 欠落などで fresh DB の構築前に失敗する。破損 DB を手動で退避すると前者のデータ損失経路へ移る。
- 再現手順: 静的指摘。検証用 scope で online embedding 完了後、コピー側の `sqlite.db` を退避して `kio repair rebuild-db --offline` を実行する経路では、コード上 `preserved` は必ず空になる。別のコピーで `tree_entries` を欠落させれば、`snapshot_tree_entries(&existing)?` が fresh DB 構築前に失敗する。監査規約に従い実行はしていない。
- backlog との関係: 新規。`tasks/step4b-backlog.md` は Done・fatal 0 を記録しているが、embedding CAS の production write-path と「embedding あり × SQLite 不在/破損」の復旧は未掲載である。

### [A2] purge は device replica の消去失敗を無視し、成功と消去保証を返す

- 重大度: fatal
- 対象: `docs/05-runtime.md:924-928`, `crates/kio-cli/src/purge.rs:328-332,488-506,1963-1978`, `crates/kio-cli/src/main.rs:2150-2174`, `tasks/step4b-backlog.md:415`
- 根拠:

  `docs/05-runtime.md:924-928`

  > - **device replica (`~/.cache/kio/aggregator.sqlite`) の当該 scope の投影** — purge 成功時に  
  >   scope 全体を再射影して置き換える (§1.8 write-through)。**replica は chunk 本文を持つ**ので、  
  >   読み手任せにすると「誰も検索しない間、purge した本文が device の cache に読める形で残る」。  
  >   順位の正しさの話ではない (回転が次の検索に再射影させるので順位は自然に直る) — **本文を消すのが  
  >   purge の目的そのもの**だという話である

  `crates/kio-cli/src/main.rs:2150-2154`

  ```rust
  /// Never fails the caller. Losing this write leaves the replica's stamp behind
  /// the index and the next search re-projects the scope — the same repair path
  /// that carried the whole design before write-through existed (03 §4: the
  /// replica is a cache, and a cache may not break a write).
  fn write_through_projection(kio_dir: &Path) {
  ```

  `crates/kio-cli/src/main.rs:2165-2174`

  ```rust
      let mut replica = match kio_index::aggregator::Aggregator::open(&aggregator_path()) {
          Ok(replica) => replica,
          Err(error) => {
              log_aggregator_degraded(&format!("write-through open failed: {error}"));
              return;
          }
      };
      if let Err(error) = replica.refresh_scope(&scope_id, &generation, &chunks, replica_now_ms()) {
          log_aggregator_degraded(&format!("write-through refresh {scope_id} failed: {error}"));
      }
  ```

  `crates/kio-cli/src/purge.rs:1963-1978`

  ```rust
  fn success_report(plan: &PurgePlan, report: &PurgeReport) -> Value {
      json!({
          "status": "purged",
          "purged_in_commit": report.purged_in_commit,
          "reason": plan.reason,
          "target_raw_count": plan.target_raw_hashes.len(),
          "deleted_counts": report.deleted,
          "shared_artifacts_preserved": report.shared,
          "tombstone_mode": plan.tombstone_mode,
          "tombstone_count": report.tombstone_count,
          "erase_receipt_count": report.erase_receipt_count,
          "logs_scrubbed": true,
          "log_files_scrubbed": report.log_files_scrubbed,
          "log_rows_removed": report.log_rows_removed,
          "log_fields_masked": report.log_fields_masked,
          "guarantee": "removed from KIO-managed history",
  ```

- 何が起きるか: aggregator に対象の secret 本文がある状態で cache DB の open/refresh が失敗すると、folder-local purge と tombstone は完了するが、write-through はログだけ残して戻る。CLI は `status: purged` と消去保証を返す。journal は完了済みで、同一 purge の再実行も `completed_report` へ短絡するため replica scrub は再試行されない。将来の成功した複数-scope検索か手動 cache 削除まで、本文が cache に読み取り可能な形で残る。
- 再現手順: 静的指摘。対象を含む aggregator を作成し、purge 時だけ aggregator DB を書込み不能または破損状態にする。`Aggregator::open`/`refresh_scope` の失敗は `Result` として呼出側へ戻らず、`purge.rs:502-506` はそのまま成功報告を作る。同一 purge の再試行は `purge.rs:328-332` で完了済み応答へ短絡する。
- backlog との関係: 既知だが評価が誤り。I21 は「purge 成功時に全再射影を追加した」として実装完了扱いだが、成功経路しか成立しておらず、privacy 上必要な失敗時の耐久再試行がない。

### [A3] `reindex --at` が pinned manifest を無視し、後日の same-gen 完了を過去 commit へ逆流させる

- 重大度: major
- 対象: `docs/03-data-model.md:232-237`, `crates/kio-cli/src/historical_reindex.rs:3-6,268-301,337-343,478-500,519-527`, `crates/kio-cli/src/main.rs:6796-6803`, `crates/kio-pipeline/src/markdownize.rs:821-839`, `tasks/step4b-backlog.md:185-188`
- 根拠:

  `docs/03-data-model.md:232-237`

  > - **manifest の各確定版は immutable object として保存する**: manifest の finalize (初回確定と、partial retry で  
  >   `failed → done` を反映した各確定) のたびに、canonical JCS bytes を `objects/manifests/ab/cd/<manifest64>` へ  
  >   content-addressed で書く (post-write verify 対象)。path-named `manifest.json` は**最新版の作業コピー**であり、  
  >   過去版の解決は manifest object のみが担う。tree entry の `normalize.manifest_hash` (§8) は常に対応する  
  >   manifest object を指すため、same-gen partial retry で作業コピーが更新された後も、過去 commit 時点の  
  >   unit 完成状態を正確に列挙・検証できる (fsck の照合 = [10-operations.md §7.5.1](10-operations.md))

  `crates/kio-cli/src/historical_reindex.rs:3-6`

  ```rust
  //! The selected commit/tree and exact normalized references are immutable truth.
  //! This path therefore never consults a later normalize cache, creates a normalized
  //! generation, or advances a ref. It only appends missing current-config chunk
  //! associations and their derived search/embedding projections.
  ```

  `crates/kio-cli/src/historical_reindex.rs:337-343`

  ```rust
      for instance in selected.values() {
          let units = match load_normalized_units(
              repo.kio_dir(),
              &instance.raw_hash,
              &instance.normalize.tool_profile_hash,
              instance.normalize.gen,
          ) {
  ```

  `crates/kio-cli/src/historical_reindex.rs:478-500,523-527`

  ```rust
      let selected_keys = selected_instances
          .iter()
          .map(|instance| {
              (
                  instance.raw_hash.clone(),
                  instance.normalize.tool_profile_hash.clone(),
                  instance.normalize.gen,
              )
          })
          .collect::<BTreeSet<_>>();
  ```

  ```rust
              kio_index::fts::record_chunk_publication(
                  fts.connection(),
                  &chunk.row.chunk_id,
                  selected_commit,
              )
  ```

- 何が起きるか: commit `C1` が manifest `H1` を pin し、その後の partial retry が同じ `(raw_hash, tool_profile_hash, gen)` の `H2` を作った場合、`reindex --at C1` は `H1` の `manifest_hash` を使わず、最新版 `manifest.json = H2` を読む。さらに chunk 選択も同じ3要素だけなので、H2 で初めて完成した chunk を選び、その publication を `C1` として記録する。以後 `search --at C1` は、C1 時点に存在しなかった本文を返せる。
- 再現手順: 静的指摘。`C1: H1(partial)` → same-gen retry → `C2: H2(done)` → `kio reindex --at C1` の順序で、`manifest_hash` がロード・選択条件のどこにも渡らず、選ばれた chunk に `introduction_commit=C1` が書かれることをコードから断定できる。
- backlog との関係: 既知の範囲外への波及。PC33/PC44 は `--all-history`/`--include-deleted` の per-binding ancestry gate の欠落だが、本件は publication 自体を誤って C1 に遡及登録する。gate を追加しても、偽の introduction が ancestor-equal と判定されるため防げない。

### [A4] in-place write-through の失敗には retry も generation 回転もなく、replica が永久に stale になる

- 重大度: major
- 対象: `docs/05-runtime.md:457-464`, `crates/kio-cli/src/historical_reindex.rs:553-571`, `crates/kio-cli/src/main.rs:2186-2204,14749-14758,1989-2003`, `tasks/step4b-backlog.md:415`
- 根拠:

  `crates/kio-cli/src/historical_reindex.rs:558-570`

  ```rust
              // 05 §1.8 write-through. This path publishes chunk TEXT into the
              // live `sqlite.db` in place — no temp+rename, and no rotation
              // anywhere in this command — so it is the one in-place writer that
              // changes the text corpus. Without this the replica would keep
              // matching its stamp against an `index_generation` that never
              // moved, conclude the scope was current, and leave every chunk this
              // reindex published out of the collection entirely.
              //
              // A full projection because the published set is a snapshot, not an
              // increment: `index_chunk_with_rowids` re-affirms existing rows as
              // readily as it adds new ones.
              drop(fts);
              crate::write_through_projection(repo.kio_dir());
  ```

  `crates/kio-cli/src/main.rs:2188-2204`

  ```rust
  fn write_through_delta(kio_dir: &Path, delta: &kio_index::aggregator::ScopeDelta) {
      if delta.is_empty() {
          return;
      }
      let Some((scope_id, generation)) = replica_scope_stamp(kio_dir) else {
          return;
      };
      let mut replica = match kio_index::aggregator::Aggregator::open(&aggregator_path()) {
          Ok(replica) => replica,
          Err(error) => {
              log_aggregator_degraded(&format!("write-through open failed: {error}"));
              return;
          }
      };
      if let Err(error) = replica.apply_delta(&scope_id, &generation, delta, replica_now_ms()) {
          log_aggregator_degraded(&format!("write-through delta {scope_id} failed: {error}"));
      }
  }
  ```

  `crates/kio-cli/src/main.rs:1989-1992`

  ```rust
          let cached = replica.scope_generation(&scope.scope_id).ok().flatten();
          if cached.as_deref() == Some(scope.index_generation.as_str()) {
              continue;
          }
  ```

- 何が起きるか: `reindex --at` または回転しない embedding in-place 更新で write-through が失敗すると、local SQLite だけが更新される。呼出元は成功し、retry intent は残らず、`index_generation` も変わらない。次の横断検索は旧 replica stamp と live stamp が一致すると判断し、再射影しない。新しい本文または vector は global rank に永久に入らず、古い行も残り続ける。無関係な後続操作が generation を回転させるまで自己修復しない。
- 再現手順: 静的指摘。既存 replica の generation を `G` とし、aggregator を一時的に書込み不能にした状態で `reindex --at` または同期 embedding を完了させる。コード上 write-through エラーは握り潰され、live/replica の stamp はともに `G` のため、後続検索の比較は必ず refresh を skip する。
- backlog との関係: 既知だが評価が誤り。I21 はこの2経路を write-through により「原理的に処理漏れなし」と評価したが、別 DB transaction の失敗を回収する durable protocol がない。

### [A5] stale な既存 scope への delta が欠落 chunk を飛ばして最新 generation を刻む

- 重大度: major
- 対象: `tasks/aggregator-design.md:83-89`, `crates/kio-index/src/aggregator.rs:260-323,713-724`, `crates/kio-cli/src/main.rs:1989-2003,2186-2204,7314-7321`, `tasks/step4b-backlog.md:415`
- 根拠:

  `tasks/aggregator-design.md:83-89`

  > **差分は replica にまだ無い scope には何も書かない。** 差分は変化分しか運ばないので scope を新規に  
  > 作れず、それでスタンプだけ押すと**一度も複製されていない本文について「最新」と検索に告げる**。  
  > 押さずに残せば次の検索が全射影する — それが正しい縮退。  
  >  
  > **スタンプは最後に書く。** generation スタンプがこの投影の commit marker で、その手前で落ちた更新は  
  > スタンプが古いまま残り、次の検索が再射影する。

  `crates/kio-index/src/aggregator.rs:280-305`

  ```rust
          if self.scope_generation(scope_id)?.is_none() {
              return Ok(false);
          }
          let tx = self.conn.transaction()?;
          delete_chunks(&tx, scope_id, &delta.removed)?;
          {
              let mut rowid_of = tx
                  .prepare("SELECT rowid FROM agg_chunks WHERE scope_id = ?1 AND chunk_id = ?2")?;
              let mut vecs = tx.prepare(
                  "INSERT INTO agg_embeddings(chunk_rowid, scope_id, vector, dimensions)
                   VALUES (?1, ?2, ?3, ?4)
                   ON CONFLICT(chunk_rowid) DO UPDATE SET
                       vector = excluded.vector,
                       dimensions = excluded.dimensions",
              )?;
              for (chunk_id, vector) in &delta.vectors_added {
                  // A chunk the replica does not hold is not an error. The scope
                  // was projected before this chunk existed, so the projection
                  // that first picks the chunk up carries its vector along with
                  // it; inserting an orphan vector row here would only leave a
                  // row no join can reach.
                  let Some(rowid) = rowid_of
                      .query_row(params![scope_id, chunk_id], |row| row.get::<_, i64>(0))
                      .optional()?
                  else {
                      continue;
  ```

  `crates/kio-index/src/aggregator.rs:315-322`

  ```rust
          // Stamped LAST, for the reason spelled out on `refresh_scope`.
          tx.execute(
              "UPDATE agg_scopes SET index_generation = ?2, refreshed_at = ?3
               WHERE scope_id = ?1",
              params![scope_id, index_generation, now_ms],
          )?;
          tx.commit()?;
          Ok(true)
  ```

- 何が起きるか: replica が旧 generation `G0` の scope を保持した状態で、live index の rebuild が `G1` を作るが全射影に失敗すると、replica は stale ながら「存在」はする。その後、新規 chunk への embedding delta が成功すると、`apply_delta` は scope 存在チェックを通過し、replica にない新規 chunk を `continue` で捨て、最後に `G1` を刻む。以後検索は generation 一致により全射影を行わず、旧 chunk が残り、新 chunk の text/vector が欠けた replica を最新として使い続ける。
- 再現手順: 静的指摘。`G0` replica → 新 chunk を含む `G1` rebuild → full projection の一時失敗 → cache 回復 → 新 chunk の embedding delta、の順序で、`scope_generation().is_none()` は false、missing row は `continue`、generation update は無条件に実行される。
- backlog との関係: 既知の範囲外への波及。I21 は「scope が完全に不在」の場合だけ `false` とする修正を記録している。本件は「scope は存在するが generation が古く、chunk 集合が不完全」な場合であり、同じ危険な stamp を許している。

## Part B

### 計画

| 順位 | 作業 | なぜこの順位か | 概算規模 | 前提・リスク |
|---|---|---|---|---|
| 1 | purge の replica scrub を journal の完了条件へ組み込む。refresh 失敗時は `purge_incomplete` とし、同一 purge で再試行する | 先に直さない限り、消去保証を返した後も秘匿本文が残る | 数日 | device-global cache lock と scope lock の順序を固定する。安全な代替として aggregator 全体の破棄も検討 |
| 2 | 規範形式の embedding CAS write-path と既存 SQLite 行の migration を実装する | 現在の唯一の vector コピーが「破棄可能な cache」にあり、次の破損・移行でデータを失う | 1週間以上 | identity hash、vector bytes、context_key の canonical 形式を先に確定する |
| 3 | `repair rebuild-db` を旧 SQLite 非依存にし、CAS/chunks/tree truth だけから再構築する | 2 より先に単独修正すると vector を黙って捨てる。2 の後に行わないと recovery 契約を証明できない | 数日 | 破損 DB は optional salvage 入力に格下げし、読取失敗で rebuild 本体を止めない |
| 4 | `reindex --at` を `normalize.manifest_hash` が指す immutable manifest から materialize し、publication をその集合に限定する | 放置すると過去 snapshot の内容と publication provenance が恒久的に汚染される | 数日 | legacy `manifest_hash=None` の明示的な fail-closed/互換規則が必要 |
| 5 | in-place write-through に durable retry または local generation 回転を導入する | 書込み失敗を1回でも見逃すと、同じ stamp のまま replica が永久に stale になる | 数日 | cursor 無効化規範との統合が必要。単なるログ出力では不可 |
| 6 | `apply_delta` に baseline-generation 一致と全対象 chunk 存在の前提を追加し、不一致時は scope を dirty 化する | 5 だけでは、すでに stale な scope を delta が「最新」に昇格させる経路が残る | 1日未満 | missing chunk 時は stamp を維持せず、次回全射影を必ず発火させる |
| 7 | 4 の後で backlog PC33/PC44 の per-binding ancestry gate を実装し、same-gen H1/H2 fixture を追加する | provenance が誤ったまま gate だけ足すと、偽の `introduction_commit` を正当化してしまう | 数日 | `--at`、`--all-history`、`--include-deleted` の共通判定にする |
| 8 | QB46 は producer 単独で実装せず、normative staging root の purge/status/prune 読み手と契約テストを同時に直す | 現在の flat-file purge test のまま producer を追加すると、staging payload を残す privacy 欠陥が即座に有効化される | 1週間以上 | `staging/<raw>.<tool>.<kind>/descriptor.json` を全経路で唯一の形にする |
| 9 | やらない方がよい / 後回し: I19 Stage 2/3、agg_approvals、replica 候補選択、新機能拡張 | truth/recovery/purge と replica commit protocol が未確立のまま読み手を増やすと、欠陥の影響面と migration 規模が拡大する | 1週間以上（延期） | 1〜8 の fault matrixが通るまで着手しない |

判定: 不合格