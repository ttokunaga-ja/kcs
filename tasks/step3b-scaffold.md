# Step3b 発注書: kcs-index / kcs-search クレート骨格 (Step 3 準備)

## 目的

Step 3 (index + search) 実装の土台となるクレート骨格を既存 workspace に追加する。**ロジックは実装しない** — 型定義・trait・モジュール構造のみ。

## 必読

- `docs/09-mvp-scope.md` §3.1 の Step 3 行 (実装範囲)
- `docs/04-pipeline.md` §4 (SQLite schema: chunks / embeddings / FTS5 外部 content + trigger / chunk_vec、§4.5 tree_entries 射影、§4.6 chunk 世代)
- `docs/05-runtime.md` §1 (検索契約: mode 解決 / RRF / MMR / paging / cursor / §1.7 レスポンス schema / §1.8 multi-scope)
- `docs/08-evidence-pointer-spec.md` §2-§3 (pointer schema / URI / 解決手順)
- `docs/03-data-model.md` §2.1 / §8.1 (chunk identity)

## 成果物

```text
crates/kcs-index/     # lib: chunking / embedding store / fts / tree_entries 射影 / rebuild の型と trait 骨格
crates/kcs-search/    # lib: query / rrf / mmr / cursor / multi_scope / evidence (pointer 発行・解決) の型と骨格
```

- workspace Cargo.toml の members に追加
- spec の schema を Rust 型に写す: ChunkRow / EmbeddingRow / TreeEntryRow / SearchRequest / SearchResponse
  (05 §1.7 準拠: results[] / evidence_pointer / evidence_uri / searched_scopes / index_status / next_cursor /
  fallback_reason)、CursorToken (05 §1.8 の per-scope 合成)、EvidencePointer (08 §2 必須+optional フィールド)
- `todo!()` スタブ + placeholder test。**新規依存を追加しない** (rusqlite / sqlite-vec 等は Step3c 実装側で追加)
- `docs/` 変更禁止。既存クレート変更は workspace members 追記のみ

## 受け入れ条件

```bash
cargo build --workspace && cargo test --workspace
cargo clippy --all-targets -- -D warnings && cargo fmt --check
```

コミットは発注側が行う。
