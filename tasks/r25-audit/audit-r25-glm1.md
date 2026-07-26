target.md の続きを読み込みます。
target.md の残りを読み込みます。
target.md の最後の部分を読み込みます。
READ-PROOF
1. target.md の総行数: 2180
2. target.md の最終 2 行を verbatim:
```
446:    1 件を通す)。→ **同じ事実を 2 つの独立した方法で測ったら、食い違いは対象ではなく計測を先に疑う。**
```

## Part A

### [G1] 同期レーンの埋め込み・reuse link・`reindex --at` が `index_generation` を回転させないため、cursor replay 中に順位が変わったことに気づかず stale なページを返す
- 重大度: major
- 対象: 資料 3 (05-runtime.md §1.8) 行 507-509・資料 4-c (main.rs:14986-15080)・資料 4-d (main.rs:14425-14460)・資料 6 (historical_reindex.rs:558-570)
- 根拠:
  - 資料 3 行 507-509: `**未解決**: 同期レーンの埋め込みと `reindex --at` は cursor を無効化しうるが回転しない (前者は再構築直後に走るので `kio index` 経路では実害が無いが、`batch resume` 経路では残る)。replica 側は write-through で塞がっているため、これは cursor 契約単独の課題である。`
  - 資料 4-c 行 15019-15020: `// A content-addressed reuse hit writes `chunk_vec` with no adapter call // and no rebuild` — `link_reused_chunks` は回転しない経路で `replica.vectors_added` に積む。
  - 資料 6 行 558-560: `// This path publishes chunk TEXT into the // live `sqlite.db` in place — no temp+rename, and no rotation // anywhere in this command` — `reindex --at` は本文 corpus を変えるのに回転しない。
- 何が起きるか: `kio batch resume` で同期レーン (または reuse link) が走り vector が増える、または `reindex --at` で chunk 本文が増える。順位が変わりうるにもかかわらず `index_generation` が回転しないので、cursor は §1.5 の `index_generation` 比較で「有効」と判定されたまま page N の replay を続ける。page 1 と page N とで異なる順位・候補集合が返され、重複または欠落が生じる。LC25「順位が変わりうる変更では cursor を退役させる」への違反。backlog §7 の I20/I21 は replica 側の staleness であって cursor 契約単独の穴には触れていない。

### [G2] `ScopeDelta.removed` フィールドが本番経路で未使用 (doc は purge 向けと書くが purge は full projection を使う)
- 重大度: minor
- 対象: 資料 2 (aggregator.rs) 行 96-108・行 284-285・資料 5 (purge.rs:502)
- 根拠:
  - 資料 2 行 103-107: `/// Chunk ids purge removed. ... pub removed: Vec<String>,`
  - 資料 2 行 284-285: `delete_chunks(&tx, scope_id, &delta.removed)?;` — `apply_delta` が処理する経路。
  - 資料 5 行 502: `crate::write_through_projection(repo.kio_dir());` — purge 成功時に呼ばれるのは projection (全置換) であり、delta 経路ではない。
  - 資料 4-c・4-d・4-e・4-f の `write_through_delta` 呼び出しはいずれも `vectors_added` のみを積み、`removed` には触れない。
- 何が起きるか: `removed` に値を入れる本番経路が target.md の範囲に一つも無く、`delete_chunks`・関連テスト (`a_delta_drops_what_purge_removed_from_the_text_index_too`) が事実上 dead code になる。replica の削除は常に projection の delete-then-insert で足りているため機能上の実害は無いが、doc が「purge 用」と明記するのに purger が使わないという不整合が、将来の経路追加時に「未対応の経路がある」との誤読を招く。

### [G3] refresh の並列度と per-scope timeout が spec §1.8 に対して未実装
- 重大度: minor
- 対象: 資料 3 (05-runtime.md §1.8) 行 518-519・資料 4-a (main.rs:1988-2014)
- 根拠:
  - 資料 3 行 518-519: `並列度は min(4, 差分 scope 数)、per-scope timeout は 2 秒 (いずれも config で上書き可)。`
  - 資料 4-a 行 1988-2014: `for scope in searched { ... match collect_scope_projection(&scope.scope_path) { ... } }` — 直列ループであり、`rayon` 等の並列化も timeout も無い。
- 何が起きるか: 差分 scope 数が大きい初回射影 (実測 428 scope / 2.3 秒) が直列で走る。読めない scope があるとその read が戻るまで待つ (READ_ONLY で失敗すれば `return None` で scatter-gather へ落ちるため無限待ちにはならないが、timeout 2 秒という上限が無いので実環境での最悪値が bound されない)。正しさには影響しない。

## Part B

| 順位 | 作業 | なぜこの順位か (先にやらないと何が起きるか) | 概算規模 |
|---|---|---|---|
| 1 | G1 の cursor 未退役を潰す — 同期レーン・reuse link・`reindex --at` を `rotate_index_generation_unconditionally` の対象に加えるか、cursor 契約を vector/text corpus の内容 hash で拡張する | 先に潰さないと cursor 利用中の page 送りで重複・欠落が観測され続ける。replica 側は write-through で正しいので、この穴は cursor 契約だけで残る。G2/G3 はこの上に載せる意味が薄いので先に片付ける | 数日 |
| 2 | G2 の整理 — `ScopeDelta.removed` を使う delta 経路を purge に切り替える (projection のコストを避ける) か、フィールドと `delete_chunks`・関連テストを削除して doc を訂正する | 現状の「doc は purge 向け・実装は未使用」を残したまま経路を足すと、delta と projection の二重維持になり不変条件 7 と同型の乖離が生まれる。G1 の後に片付ければ影響範囲が明確 | 1 日未満 |
| 3 | G3 の実装 — `global_ranks_for` の refresh ループを spec §1.8 の min(4, 差分 scope 数) と per-scope timeout 2 秒へ合わせる | 正しさには影響しないが timeout 無しは実環境での最悪値が bound されない。G1 の cursor 解決で回転経路が増える前に並列化枠を固定しておくと、回転呼び出しの順序込みでテストできる | 数日 |
| 4 | Stage 2 (`agg_approvals`) の着手 — `agg_approvals` 表追加と `kio approvals list --all-scopes` 等の横断コマンド | Stage 1 の replica が安定したら次の段階。権限の横断管理は replication 変更の動機の 1 つ (資料 1 §1)。G1-G3 を先に潰さないと権限投影にも同じ staleness 課題が乗る | 1 週間以上 |
| 5 | Stage 3 (候補選択の replica 移行と安全性再確認の独立実装) の準備 — 手順 3 (a)(b)(c) を replica 側に独立実装し、per-scope `candidate_depth` 打ち切りを解消する | Stage 3 開始前に手順 3 が無いと staleness が「死んだ Evidence Pointer を返す」に化ける (資料 1 §4.2・§7)。現行の scope 数比例レイテンシ (実測 1.2 秒) はここでしか縮まない | 1 週間以上 |

判定: 条件付き合格
