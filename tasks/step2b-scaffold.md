# Step2b 発注書: kio-pipeline / kio-adapter クレート骨格 (Step 2 準備)

## 目的

Step 2 (pipeline + adapter) 実装の土台となるクレート骨格を既存 workspace に追加する。**ロジックは実装しない** — モジュール構造・trait 定義・型定義のみ。

## 必読

- `docs/09-mvp-scope.md` §3.1 の Step 2 行 (実装範囲)
- `docs/04-pipeline.md` §2 (unit model)、§3 (incremental 入出力 schema)、§5.1 (task descriptor)
- `docs/07-adapter-spec.md` §2 (実行形態)、§5.1/§5.2 (Prepare / Markdownize trait I/O)、§6 (tool-lock)
- `docs/03-data-model.md` §2.1 (normalized instance / manifest / unit_ref)

## 成果物

```text
crates/kio-pipeline/    # lib: scan / prepare / markdownize / task / budget モジュール骨格
crates/kio-adapter/     # lib: Adapter trait 群 + deterministic / mistral_ocr の空実装骨格
```

- workspace Cargo.toml の members に追加
- 各モジュールは spec の型を Rust 型に写した定義 (例: NormalizationRun / UnitRef / TaskDescriptor /
  AdapterRequest/Response、07 §5.2 の入出力フィールド) + `todo!()` スタブ + placeholder test 1 個以上
- **新規依存を追加しない** (serde / serde_json / thiserror 等の既存 workspace 依存のみ使用可。
  HTTP クライアント・rusqlite 等は本体実装 (Step2c) 側で追加する)
- `docs/` 変更禁止。既存クレート (kio-core / kio-cli) の変更は workspace members 追記以外禁止

## 受け入れ条件

```bash
cargo build --workspace && cargo test --workspace
cargo clippy --all-targets -- -D warnings && cargo fmt --check
```

コミットは発注側が行う (git 操作不要)。
