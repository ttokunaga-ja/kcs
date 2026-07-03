# Step3c K ラウンド完了報告 (2026-07-04、8a089f5 への fix-required 対応)

対象裁定: `tasks/step3c-fixes.md` (K1-K8、fix-required 4/4)。
ブランチ `step3c-impl` への追加コミット 6 件 (84337a1 → de7b379)。
体制: 実装 = Opus/Sonnet サブエージェント 4 系統 (検索中核 / Evidence resolver /
embedding / P0 検収)、設計裁定・マージ・監査・実機検証 = 調整役。

## 受け入れ条件の達成状況

```
cargo test --workspace        227 green (P0 60/60 に専用テスト、tasks/step3c-p0-matrix.md)
cargo clippy --all-targets -- -D warnings   clean
cargo fmt --check             clean
eval M3-1                     Recall@10 = 0.8889 (>= 0.8 PASS、独立 3 回一致)
実機シナリオ (a)-(e)          全 PASS (結合テスト + 調整役による実バイナリ手動再現の両方)
```

実機シナリオの結合テスト: (a) `ct3_multi_001_default_searches_participating_indexed_scopes`
(b) `ct3_multi_005_partial_failure_returns_results_with_exit_3` (c)
`ct3_cursor_002_max_rowid_excludes_post_cursor_chunks` (d)
`ct3_hybrid_001_auto_resolves_to_hybrid_with_rrf_fusion` (e)
`ct3_embed_008_non_multimodal_profile_is_rejected_at_index`。

## eval M3-1 の数値変動理由 (0.944 → 0.889)

旧 0.944 は規約違反の自作字句スコアラ (`score_chunk`) による値であり比較基準にならない。
spec 準拠経路 (per-scope FTS5 BM25 → RRF → rank ベース scope 間統合、05 §1.8) の正値が
0.8889 (16/18)。素朴な単一 OR クエリ + 純 BM25 では 0.667 だが、**クエリ構築の階層化**
(spec が規定しない実装自由領域): tier-1 = keyword 群の OR (BM25 の IDF が希少語複数一致を
上位化) / keyword 1 + trigram 文脈 AND、tier-2 = 全 unit 緩和 OR、scope ごとに最初に候補を
返した tier のみ採用 — により **rank は純 BM25 のまま** 0.8889 へ回復した。
数値 keyword は実行クエリ内で桁区切り variant を OR 展開 ("3600" OR "3,600")。

残 miss 2 件 (いずれも意味ギャップで、text 検索の構造限界):
1. 近似数値パラフレーズ (クエリ「40 くらい」 vs 本文「42」)
2. 英語クエリ vs 日本語本文 (cross-language)
どちらも vector/hybrid の担当領域。モック embedding は意味信号を持たないため hybrid の
lift は本ラウンドでは測定不能 (モックで 0.389 に低下するのは期待どおりのノイズ挙動)。
実 Gemini API での hybrid 実測は発注側の実 API 検証マターとして残す。

## K 項目別の実装概要

- **K2** (d243359 + d7d8d97): score_chunk と字句ヘルパ群を削除し FTS5→fuse_rrf→
  diversify_candidates を配線。検索毎の index 全再構築も廃止 (sqlite.db を読むだけ)。
  mode 解決・fallback_reason・diversify 表示は実態値 (text-only は group_by_raw_hash を
  報告、幻の "mmr" を返さない)。text rank は 1 回の FTS5 MATCH の
  bm25(chunk_fts, 1.0, 0.3) 順のみ (調整役裁定で keyword 再ランクを却下・除去済み)
- **K3** (d243359): デフォルト = scope_registry (scope-registry.sqlite、84337a1 新設)
  の participates_in_global_search=true な indexed scope 全列挙。init/index 成功時に
  upsert 登録 (cache 層 — 登録失敗は index を失敗させない、03 §4)。部分失敗は
  excluded_scopes 記録 + exit 3、全失敗 exit 4。sibling ディレクトリ走査は廃止
- **K5** (d243359): per-scope sub-cursor {scope_id, snapshot_commit, max_rowid, consumed}。
  再計算は snapshot_commit の tree_entries (無ければ tree object から再展開) +
  rowid <= max_rowid で集合固定。shallow snapshot の cursor 再計算は
  KCS-E-COMMIT-SHALLOW-001
- **K6** (75d0c6d): 08 §3.1 の解決順を完全実装 (scope 2 段解決 → commit → shallow 判定 →
  tree gate → tombstone → chunk/raw)。tombstoned / not_found / scope_unreachable の
  3 値実区別、`kcs://<scope>/object/<type>/<hash>` URI 受理。誤解を招く kcs-search の
  resolver スタブは削除。新 error code 2 件は ws1c-decisions #32
- **K4** (07948af): GeminiEmbeddingAdapter (Mistral 方式 client trait、429 backoff、
  起動時 pin 解決) + KCS_TEST_GEMINI_EMBED モック seam + TaskType::Embedding 生成/実行
  (network opt-in・budget・cost ledger 接続) + sqlite-vec 0.1.6 で chunk_vec を vec0 実体化
  (embeddings テーブルが正、rebuild-db は embeddings→chunk_vec 再導出で vector 検索を保存)
  + tool-lock embedding entry 書込で KCS-E-EMBED-MODALITY-001 検証が実配線 + hybrid は
  chunk_vec KNN (cosine 距離順) → RRF、MMR に実 embedding 供給
- **K7** (d243359): index_status {enriched_ratio (task ledger の done/total、対象件数加重),
  pending_enrichment_tasks, budget_paused} を search --json に常時付与
- **K8** (d243359 ほか): metrics = KCS-M-SEARCH-001 / component "search" / 05 §7 envelope。
  検索対象は現行 chunking_config_hash のみ。rebuild-db テストは「SQLite が実検索に使われる」
  前提で実体化 (ct3_fts_004 / ct3_embed_005)。open の JSON 返却は ws1c-decisions #31 に記録
- **K1** (de7b379): P0 60/60 の契約⇔テスト対応を確立 (tasks/step3c-p0-matrix.md)。
  常真 3 件 (HYBRID-002 / EMBED-002 / EMBED-003) は KCS_TEST_GEMINI_EMBED seam で
  compatible / incompatible / 未生成の embedding 状態を実際に作り分けて実体化。
  MULTI-001 は MULTI-008 から分離して独立検証。弱テスト 8 件補強

## 死コードの扱い (前ラウンド根本診断への恒久対応)

「正実装のまま未配線」を再発させないため、未配線のライブラリ scaffold は今ラウンドで
**配線するか削除するか**に二分した。削除分 (de7b379): kcs-index の tree_entries.rs /
rebuild.rs、kcs-search の multi_scope.rs / query.rs の未使用 response 型・SearchEngine・
search() スタブ / lib.rs placeholder テスト、embedding_store の validate_embedding_profile
(実施行は tool_lock::validate_embedding_entry と matches_adopted に配線済み)、
kcs-search の evidence resolver スタブ (75d0c6d)、EmbeddingStore trait (07948af)。

## 未実装・限界の明示 (過小開示の禁止に基づく全数開示)

1. **実 Gemini HTTP は未検証** (hermetic 方針、ws1c-decisions #28 踏襲)。wire format
   (:batchEmbedContents / x-goog-api-key / outputDimensionality) はドキュメント準拠の
   ベストエフォートで、モックで contract のみ検証。実 API 検証は発注側
2. **hybrid の品質 lift は未実測** (モックは意味信号なし)。配線と契約のみ保証
3. time-travel フラグ (--at / --all-history / --include-deleted / --since) は従来どおり
   KCS-E-CONFIG-NOT-IMPLEMENTED-001 (Step3c 発注範囲外)
4. KNN は全 chunk_vec 行を取得後に live 集合フィルタ (sqlite-vec が KNN LIMIT を join より
   先に適用するため)。MVP 規模では十分、大規模化時は metadata partitioning を検討
5. クエリ embedding のコストは非計上 (微小。budget guardrail は bulk index が対象)。
   検索時の embedding 失敗 (auth/rate) は text fallback に退避 (検索は失敗させない)
6. CT3-EMBED-006 (content 再利用) は再 index 冪等性レベルで検証済みだが、同一 text_hash
   専用の CLI assert は無し。auth_error/rate_limit seam は index 経路に配線済みだが
   専用テスト無し (K1 必須外)
7. shallow commit の判定は「tree object 物理欠損」(Step 3 に shallow 生成系が無いため)。
   store 破損と区別しない。KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001 経路はテスト未カバー
   (P0 外)。CT3-CHUNK-009 の「indexing 途中は不可視」節は同期 CLI では実質検証不能
8. registry 登録パスは canonicalize していない (シンボリックリンク経由の重複登録が
   理論上可能)。eval ハーネスは XDG_DATA_HOME を隔離せず継承するため、実行時は
   `XDG_DATA_HOME=$(mktemp -d)` での起動を推奨 (レポートの実測はすべて隔離環境)

## 主要な設計判断の記録先

ws1c-decisions #31 (open の JSON 返却) / #32 (新 error code 2 件)。その他は各コミット
メッセージと tasks/step3c-p0-matrix.md の判定列。
