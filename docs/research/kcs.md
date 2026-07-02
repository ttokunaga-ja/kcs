# `.kcs` Layout Research Notes

> Status: integrated
> Canonical refs: [../03-data-model.md](../03-data-model.md), [../07-adapter-spec.md](../07-adapter-spec.md)

---

# 結論

`.kcs` は folder-local な truth store。Adapter 実行情報や個人環境の設定は持たず、生成済み artifact と provenance、互換性判定に必要な非実行情報だけを保持する。

# 最小 layout

```text
.kcs/
  VERSION
  scope.json
  config.toml
  tool-lock.json
  manifest.json
  objects/
    raw/
    normalized/
    chunks/
    embeddings/
    trees/
    commits/
    nodes/
    edges/
  refs/
    heads/
    tags/
  index/
    kcs.sqlite
  logs/
    events.jsonl
    access.jsonl
```

# 役割分担

```text
.kcs:
  raw object / normalized / chunk / commit / refs / provenance。
  共有・移動できる正本。

~/.config/kcs:
  adapter executable、API URL、認証情報、device-local default。
  共有 `.kcs` には入れない。

scope registry:
  複数 `.kcs` を発見する cache。truth ではない。
```

# tool-lock

`tool-lock.json` は「どの capability profile で artifact を作ったか」を固定する。実行コマンド、URL、認証情報は含めない。

commit object は `tool_lock_hash` / `tool_profile_hash` を参照して、同じ raw object に対する派生 artifact の互換性を判断する。

# normalized object

Normalized Markdown は path ベースではなく hash ベース object store に保存する。ユーザー向けの `<original>.md` 表示は view として扱う。

```text
identity = (raw_hash, tool_profile_hash)
```

Markdown content hash (`normalized_hash`) は採用しない。

# scope.json

`scope.json` は、その `.kcs` が管理する folder scope を識別する。親 `.kcs` は子 `.kcs` の配下を直接 object 化しない。

# Bootstrap

`kcs init` が作る最小 `.kcs` は、VERSION / scope.json / config.toml / tool-lock.json / manifest.json / refs / objects / index を持てばよい。未生成 artifact は task と status で検出する。

# 正本へ移した内容

```text
layout / scope / object schema       → 03-data-model.md
tool-lock / adapter capability       → 07-adapter-spec.md
横断運用                            → 10-operations.md
```
