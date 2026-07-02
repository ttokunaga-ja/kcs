# Productization Research Notes

> Status: integrated
> Canonical refs: [../01-positioning.md](../01-positioning.md), [../09-mvp-scope.md](../09-mvp-scope.md), [../10-operations.md](../10-operations.md)

---

# 採用した運用方針

## 1. 初回スキャン前の承認

KCS は初回に勝手に全ファイルを読み込まない。`kcs init` / `kcs index preview` で対象、推定容量、online adapter 使用有無を提示し、承認後に実行する。

## 2. 容量より利便性

MVP では容量最適化より「消えない根拠」と「探せること」を優先する。pack / aggressive dedup は v1+。

## 3. scope registry は cache

正本は folder-local `.kcs`。scope registry は横断検索と stale 検出の cache。registry 更新だけで `.kcs` の状態を変えてはいけない。

## 4. folder-local `.kcs`

`.kcs` はフォルダごとのスコープ境界。親 `.kcs` は子 `.kcs` の配下を直接取り込まない。

## 5. 物理 layout 統一

Normalized Markdown は `.kcs/objects/normalized/` に hash ベースで保存する。path ベースの `.md` は view。

## 6. 検索 backend

SQLite + FTS5 + sqlite-vec を MVP 標準にする。外部 DB は v2 以降。

## 7. purge の保証範囲

KCS 管理下の object store、snapshot DAG、index、pack、cache、tombstone が対象。OS backup、Time Machine、外部 export、手動コピーまでは保証しない。

## 8. local-first と同期

MVP は単一端末 local-first。同期、共有、Web 修正提案は `synchronization.md` の将来構想へ分離する。

## 9. Adapter security

`.kcs` は実行コマンド、URL、credential を運ばない。Adapter 実行設定は device-local config / keychain に置く。

## 10. 横断規約

```text
error code:
  KCS-E-<AREA>-<DETAIL>-<NNN>

exit code:
  0 success
  1 generic failure
  2 usage/config
  3 partial success
  4 retryable external failure
  5 data integrity / corruption

time:
  永続データは UTC ISO8601 + Z。

schema:
  config / tool-lock / evidence pointer は schema validation 必須。

observability:
  events.jsonl は ts, level, code, component, message, context を持つ。
```

# 旧語彙の扱い

```text
offline-first      → local-first
normalized_hash    → 廃止
folder.json        → scope.json
canonical_hash     → 廃止
last_indexed_git_commit → 廃止
```

# 正本へ移した内容

```text
positioning / MVP      → 01-positioning.md, 09-mvp-scope.md
横断規約               → 10-operations.md
runtime / purge        → 05-runtime.md
Adapter security       → 07-adapter-spec.md
```
