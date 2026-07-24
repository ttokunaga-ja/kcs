# WS1c 発注書: kio-core + kio-cli 本体実装 (Step 1)

## 目的

Kio Step 1 の本体実装。**契約テスト仕様 `tasks/ws1a-contract-tests.md` の P0 39 件を green にする**ことが完了条件。CAS + snapshot DAG + CLI 7 コマンド。

## 前提 (main に揃っている)

- スキャフォールド: `crates/kio-core` (cas/dag/scope/exit_code) + `crates/kio-cli` (clap、7 サブコマンド骨格) + CI
- 契約テスト仕様: `tasks/ws1a-contract-tests.md` — テストベクタは実計算済み・別ベンダー再計算で全件一致確認済み
- 正本 spec: `docs/03-data-model.md` (§1/§2/§3/§8/§8.1/§8.2/§10)、`docs/05-runtime.md` (§2/§6/§8)、`docs/06-cli-spec.md` (§1/§4/§7/§8/§12)、`docs/09-mvp-scope.md` §3.1 (Step 1 行のみが実装範囲)

## 実装手順 (この順で)

1. `tasks/ws1a-contract-tests.md` の P0 を Rust テストに落とす (`crates/kio-core/tests/` + CLI は `assert_cmd` 等)。**ベクタの期待値は変更禁止** — 実装をベクタに合わせる
2. kio-core: JCS (RFC 8785) canonical 化 → `serde_jcs` crate を第一候補、不採用なら自前実装 (ws1a §A のベクタで検証)。sha256 は `sha2`
3. CAS object store (raw/tree/commit、fan-out `ab/cd`、atomic write)、refs/HEAD、`.kio/.lock` (05 §6: 敗者は即失敗 exit 3 / KIO-E-STORE-LOCKED-001 / stale 回収)
4. CLI 7 コマンド実装 + `--json` (完全 hash、06 §4)、観測ログ events.jsonl / errors.jsonl、scope.json / manifest.json / config.toml の JSON Schema validation

## spec 未定義部の暫定判断 (ws1a §C #3-#14。この通りに実装し、判断を `tasks/ws1c-decisions.md` に記録)

```text
#3  manual snapshot で tree 不変      → no-op (新 commit を作らず exit 0 + 通知)
#4  Step 1 の status 状態語彙          → new / modified / deleted / unchanged の 4 値に縮退
                                         (2026-07-03 監査裁定で up_to_date → unchanged に改訂。
                                          up_to_date は 03 §6 で normalized instance 前提の意味を持つため)
#5  init: 既存 .kio あり              → no-op + "already initialized" exit 0。path 引数不存在は exit 2
#6  tag: 既存名への再 tag             → exit 2 (上書きは Step 1 対象外)。commit 省略時は HEAD
#7  diff 出力                         → added / modified / deleted の 3 分類。差分の有無で exit code を変えない (常に 0)
#8  inspect: 対象 hash 不存在         → KIO-E-STORE-NOT-FOUND-001 / exit 4
#9  log 順序                          → HEAD から first-parent を新しい順。--at/--since は受理して未実装なら exit 1
#10 created_at 精度                   → 秒 (ISO8601 UTC "Z"、06 §12)
#11 tree entry type 値域              → Step 1 は "file" のみ (それ以外は schema violation)
#12 (解決済み: spec 追記反映済み — status/diff は読み取り系、tag は書き込み系。05 §6)
#13 files 行の生成主体                → snapshot 実行時にスキャンして更新。status は read-only 表示のみ
#14 未実装機能の挙動                  → "not implemented" + exit 1 (スキャフォールド踏襲)
```

## 制約

- 実装範囲は 09 §3.1 の **Step 1 行のみ**。pipeline / 検索 / GC 実行 / purge は書かない (gc_policy × commit_type の schema 遵守のみ)
- LOC 目安: テスト除き 2,500-4,000 (09 §3)。超えそうなら削る相談を先に
- 依存は最小 (clap / serde / serde_json / serde_jcs / sha2 / thiserror / anyhow / assert_cmd + jsonschema 程度)。unsafe 禁止
- `docs/` は変更禁止。spec の矛盾・実装不能を見つけたら `tasks/ws1c-decisions.md` に記録して作業は継続
- tree entry の `normalize` は省略形のみ生成 (Step 1 は全 entry 省略。03 §8 の optional 規定)

## 受け入れ条件

```bash
cargo test --workspace          # 契約テスト P0 全 green (ws1a ベクタ一致を含む)
cargo clippy --all-targets -- -D warnings
cargo fmt --check
```

ブランチ `ws1c-core-impl` (main から分岐) にコミットすること。完了後、別ベンダー (Claude) による spec 準拠レビューを行う。
