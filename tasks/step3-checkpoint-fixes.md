# Step 4 着手前チェックポイント監査の裁定 (2026-07-04、main HEAD = 8d240fa)

4 エンジン統合裁定: **fix-required (4/4)**。hot-fix 2 件 (fb60a12/9b61e51) 自体は 3 エンジンの実機/読解で
sound 確認。しかし「同型ギャップの兄弟探し」で新規 critical 1 + major 4 が確定した。

## 必須修正 L1-L8

- **L1 [critical] reindex/repair 後の enrichment 欠落** (Sonnet 実機 + GPT-5.5): `run_reindex` と
  `run_repair --rebuild-db` は `rebuild_step3_index` 後に enrichment を呼ばない (index 経路と非対称)。
  さらに `compute_index_status` が TaskStore 集計のため、task が enqueue されない新規 chunk は不可視で
  **enriched_ratio 1.0 / pending 0 の虚偽報告**になる (docs/06 §「reindex = 再 normalize / 再 embedding」
  違反)。修正: 両経路の rebuild 直後に `run_embedding_enrichment(repo, persistent opt-in による online)`
  を呼ぶ (offline なら enqueue のみ = index_status で可視化)。回帰テスト: chunking config 変更 →
  reindex --force → (seam mock) embeddings が新 chunk 分生成される / offline なら pending が
  index_status に出る。ct3_reindex 系は embedding seam 未使用なので seam 付き版を追加
- **L2 [major] override_budget の不達と Paused の意味論非対称** (Sonnet/Opus 実機 + GPT-5.5):
  `execute_pending_tasks` が `resume.override_budget` を受け取らず、markdownize/embedding とも
  `evaluate_budget_with_caps(..., false)` 固定 (docs/04 の「cap を無視して再開」契約違反)。
  さらに embedding は DB 駆動のため **budget_exceeded で Paused の task を override なしで実行して
  しまう** (markdownize は sticky に据え置く — 非対称)。修正: (i) `execute_pending_tasks(repo, store,
  override_budget)` に thread し、markdownize / `run_embedding_enrichment(…, override_budget)` の
  budget 判定へ伝播、(ii) enrichment の対象選定で「budget_exceeded の Paused embedding task を持つ
  chunk」は override なしでは skip (markdownize と同じ sticky 意味論)。実機シナリオ両方をテスト化
- **L3 [major] view/open の短縮ハッシュ解決が snapshot 後に破綻** (Opus 実機): `resolve_short_hash` /
  `load_searchable_chunks` が **tree_entries.json (ファイル射影)** を `commit_hash == HEAD` で filter
  するが、9b61e51 の lazy 射影は SQLite 側のみで JSON は refresh されない → snapshot 直後は
  KIO-E-CONFIG-USAGE-001 (search は同条件で成功する非対称)。修正: 短縮ハッシュ解決を SQLite
  tree_entries + `ensure_snapshot_tree_entries` 経由に一本化 (JSON 射影は廃止候補 — 残すなら同時
  refresh)。回帰テスト: index → snapshot → view/open (短縮ハッシュ) が成功
- **L4 [major] embedding の opt-in が Mistral 承認に相乗り** (GPT-5.5): `persistent_network_allowed`
  が `mistral_ocr_markdownize` の承認行しか見ず、承認書込みも Mistral 固定。07 §3 の opt-in 単位は
  scope × adapter (tool_id)。修正: index --approve 時に構成済み online adapter (markdownize +
  embedding) それぞれの承認行を記録し、embedding 実行前の判定は自 tool_id (`gemini_embedding_2`) の
  行を見る。revoke も adapter 単位で効くこと。既存 scope の後方互換 (mistral 行しか無い場合) は
  「embedding 承認なし = enqueue のみ」とし、decisions に記録
- **L5 [major] content-reuse 時の空課金** (GPT-5.5): budget 判定と ledger 記帳が batch 全 chunk の
  文字数ベースで、`embed_batch` 内の reuse (API 非呼出) 分も課金される (CT3-EMBED-006 の billing 面
  違反)。修正: embed_batch が実送信 chunk 数/文字数を返し、その分のみ判定・記帳
- **L6 [minor] batch 内 reuse/実呼出混在時の failure 汚染** (Sonnet 読解): adapter 失敗時に
  fail_embedding_tasks が batch 全体を Failed にするが、reuse で既に chunk_vec 書込済みの chunk は
  live 集合から外れて永遠に Failed のまま実体と乖離。修正: reuse/link 済み chunk は失敗時も done に
- **L7 [minor] enrichment が task lifecycle (next_retry_at / 非 retryable) を見ない**: L2 (ii) の
  sticky-Paused 対応と合わせ、failed + next_retry_at 未来の task を持つ chunk は skip
- **L8 [minor] docs 同期**: 03 §8.1 の embedding identity (target_hash → text_hash ベースの実勢に
  更新、04 §4.3 と整合)。04/06 の batch resume/retry 節に enrichment 実行の追記

## 受け入れ条件

cargo test --workspace (回帰なし + 新規回帰テスト) / clippy -D warnings / fmt。
実機シナリオ: (a) config 変更 → reindex --force → mock seam で embeddings 追随 + offline では
pending が index_status に可視、(b) budget_exceeded Paused が override なし resume で据え置き・
override ありで実行 (markdownize/embedding 対称)、(c) snapshot 直後の view/open 短縮ハッシュ成功、
(d) embedding 承認の無い scope で embedding が enqueue のみになる。
