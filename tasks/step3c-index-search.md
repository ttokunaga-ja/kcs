# Step3c 発注書: kcs-index + kcs-search 本体実装 (Step 3)

## 目的

KCS Step 3 の本体実装。**契約テスト仕様 `tasks/step3a-contract-tests.md` (r2) の P0 59 件を green にする**ことが完了条件。

## 前提 (main に揃っている)

- Step 1-2 実装済み (CAS/DAG/CLI + pipeline/adapter/index、テスト 131)
- スキャフォールド: `crates/kcs-index` / `crates/kcs-search` (型 + trait 骨格)
- 契約テスト仕様: `tasks/step3a-contract-tests.md` r2 — ベクタ実計算済み・クロスレビュー再計算一致。**期待値の変更禁止**
- spec 追記済み (2026-07-03): chunk 境界の正準規則 (04 §4.1)、MMR relevance 正規化 (05 §1.4)、query_hash 正準構成 (05 §1.8)、per-search latency 記録 (05 §7)
- embedding は **単一 multimodal profile 採用** (07 §5.3 再検証で確定、tasks/step3-embedding-verify.md 再検証節): `gemini-embedding-2` (GA) / 768 次元 (MRL 切り詰め、profile 固定) / cosine / modality=multimodal / mode=online (バッチ非対応 — client 側並列 + 429 backoff)。**MVP で embed するのは text chunk のみ**
- 検索評価ハーネス: `eval/` (コーパス生成・履歴再現・golden queries 50・run_eval.py)

## 実装範囲 (正本: docs/09-mvp-scope.md §3.1 の Step 3 行)

1. chunking (04 §4.1 の正準規則: ATX heading / heading_path / section_id slug / max_chars 分割、unit-local span、chunk_hash = 03 §8.1)
2. SQLite 層: chunks / embeddings (+ chunk_vec sqlite-vec) / chunk_fts (FTS5 外部 content + trigger + trigram) / tree_entries (HEAD 射影、04 §4.5) / chunk 世代 (04 §4.6、chunking_config_hash)
3. embedding: Gemini embedding adapter (`gemini-embedding-2`、multimodal profile、768/MRL、mode=online + 429 backoff、GA 版を起動時解決して pin = 07 §6)、互換性ルール (03 §7: dimensions/distance/modality/profile_hash 不一致で vector 拒否 + text fallback)。**テストはモック** (Step 2 の Mistral と同じ trait seam 方式)
4. hybrid search: mode 解決 auto→hybrid→text fallback + fallback_reason 可視化 (05 §1.1)、weighted RRF (k=60、candidate_depth 200、同点 chunk_id 昇順)、MMR (正規化 relevance、mmr_depth 100、text-only 時は不適用)
5. paging / cursor: 決定論的再計算 (05 §1.5)、query_hash (正準構成)、multi-scope 合成 token (05 §1.8)、CURSOR-001 / SHALLOW-001
6. multi-scope search: scope 列挙 (registry)、並列 min(4,N)、per-scope timeout、rank ベース統合 (raw スコア比較禁止)、searched_scopes / excluded_scopes、部分失敗 exit 3 / 全失敗 exit 4
7. Evidence Pointer: 検索結果への発行 (08 §2 必須フィールド + evidence_uri)、解決 (scope_id 2 段 / gen / working tree / CAS / tombstoned / not_found / scope_unreachable)、`kcs open` (06 §1.1)、`kcs view`。**`kcs evidence verify` CLI は Step 4** (09 §3.1) — resolver 内部関数までが Step 3 範囲
8. `kcs search` CLI (06 §3: --scope/--descendants/--all-scopes/--text/--vector/--hybrid/--no-vector/--limit/--offset/--cursor/--json)。time-travel フラグ (--at 等) は**受理して "Step 4" エラー** (§D の境界判定どおり)
9. `kcs reindex [--force]` (gen+1、旧 gen 残置、pointer 不変、確認プロンプト)
10. index_status (05 §1.7)、metrics.jsonl per-search latency (05 §7)、access.jsonl

## 実装手順

1. step3a の P0 59 を Rust テストに落とす (ベクタ fixture 一致 assert 含む)。**pipeline 系契約は CLI (kcs search / kcs index) を通る結合テスト** — Step 2 の教訓 (純関数テストのみは完了と見なさない)
2. 依存追加可 (最小): rusqlite (bundled)、sqlite-vec、既存 ureq。**テストの外部通信ゼロ** (embedding はモック / KCS_TEST_* env フック方式を踏襲)
3. 実装 green 化 → `eval/` の M3-1 サブセットで実測: `python3 eval/generate_corpus.py` → `replay_history.py` → `run_eval.py --scenario M3-1` で **Recall@10 >= 0.8** を確認 (M3-2/3 は Step 4 完了時)

## spec 未定義部の暫定判断 (step3a §C の実装者判断 5 件。この通り実装し decisions に記録)

```text
- FTS trigram のクエリ最小長: 2 文字未満は FTS skip + vector/全 scan にしない (結果 0 でよい)
- sqlite-vec の距離: cosine (03 §7 の profile と一致させる)
- 検索結果の text スニペット: chunk text 先頭 200 文字 (レスポンス schema の title/snippet 相当は 05 §1.7 に従う)
- tree_entries の更新契機: snapshot / index 完了時に HEAD 分を全量再射影 (差分更新は Phase 4+)
- access.jsonl の記録粒度: 1 検索 1 行 (redact 済み)
```

## 制約

- LOC 目安: テスト除き 3,500-5,000 (09 §3)。docs/ 変更禁止 (矛盾は decisions に記録)
- 完了報告では**未実装箇所を未実装と明記**すること (過去ラウンドの教訓)
- eval/golden-queries.jsonl は凍結済み — 変更禁止

## 受け入れ条件

```bash
cargo test --workspace          # P0 59 green + Step 1-2 の既存 131 テスト回帰なし
cargo clippy --all-targets -- -D warnings && cargo fmt --check
eval M3-1: Recall@10 >= 0.8 (実測値を報告に含める)
```

ブランチ `step3c-impl` (main から分岐)。完了後、発注側が 4 エンジン監査を実施する。
