# Commit / Snapshot Research Notes

> Status: integrated
> Canonical refs: [../05-runtime.md](../05-runtime.md), [../06-cli-spec.md](../06-cli-spec.md), [../10-operations.md](../10-operations.md)

---

# 結論

KCS では commit と snapshot を内部的に別 object にしない。どちらも `tree + parents + metadata` を持つ同一履歴 object。

CLI では開発者向けに `commit` を許容し、ユーザー向け表示では `snapshot` を使える。

# 主要 fields

```text
commit_id
tree
parents
message
actor
commit_type
protected
created_at
metadata
```

# commit_type

固定 enum。追加・削除・改名しない契約。

```text
manual     ユーザーまたは Agent の意思を持った保存
auto       system による無人保存
imported   KCS の追跡対象へ初登録
migrated   schema / tool 変更による派生 artifact 再生成
repaired   破損検出からの回復
merged     並行 autosnapshot 等の合流
purged     purge による履歴書き換え
```

新しい性質はまず `actor` / `source` / `trigger` / `metadata` で表現する。

# GC policy

```text
manual/imported/merged/purged:
  原則保持。

auto:
  tiered retention 対象。

migrated/repaired:
  方針により shallow GC 可。
```

`shallow GC` は commit object を残し、tree を破棄する。履歴 DAG の連続性は維持するが restore は拒否する。

# purge

purge は通常 GC ではない。対象 raw に由来する tree / commit / raw / normalized / chunk / embedding / evidence / index を KCS 管理下から除去する破壊的操作。

結果 commit の `commit_type` は `purged`。

# 正本へ移した内容

```text
runtime / GC / purge      → 05-runtime.md
CLI                       → 06-cli-spec.md
enum / semver contract    → 10-operations.md
```
