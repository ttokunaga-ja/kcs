# Git / KCS Research Notes

> Status: integrated
> Canonical refs: [../03-data-model.md](../03-data-model.md), [../05-runtime.md](../05-runtime.md), [../10-operations.md](../10-operations.md)

---

# 核心

KCS は Git の「content-addressed object store + tree + commit」の構造を、ローカル知識アーカイブへ移植する。ただし目的はコード共同編集ではなく、原本根拠付きの検索・復元・時点指定ナビゲーション。

| Git | KCS |
| --- | --- |
| blob | raw object / normalized object / chunk |
| tree | folder snapshot |
| commit | KCS commit / snapshot |
| branch | snapshot lineage。MVP では明示 branch を持たない |
| tag | named archive point |
| index | pending task / index state。正本ではない |
| checkout | view / restore |
| blame | Evidence Pointer / provenance |

# object model

```text
raw object:
  原本バイト列。CAS の最重要 object。

normalized object:
  raw object + tool_profile_hash から作る read-only Markdown artifact。

chunk object:
  検索・Evidence Pointer の単位。normalized object から導出。

embedding object:
  chunk/node に対する派生 artifact。profile 不一致なら再生成または fallback。

tree object:
  path、raw_hash、normalized refs、metadata の snapshot。

commit object:
  tree + parents + metadata。manual / auto / imported 等は commit_type で表す。
```

# `.kcs` scope

各 `.kcs` は、それが置かれたフォルダ直下のスコープを管理する。子フォルダに別 `.kcs` がある場合、親は子スコープを object 化しない。

```text
truth:
  各 folder-local .kcs

cache:
  scope registry / aggregator
```

scope registry は横断検索の補助であり、正本ではない。registry を失っても rescan できるが、`.kcs` を失うと raw object / snapshot / evidence を失う。

# dedup 方針

同一 `.kcs` 内では raw_hash によって同一ファイルを一度だけ保存する。異なる `.kcs` 間の横断 dedup は MVP ではしない。容量効率より、スコープ境界・権限・移動可能性を優先する。

# search scope

> **NOTE**: 本節のフラグ表記 (`--here` / `--below` / `--scope <path>`) は旧案。フラグの正本は [06-cli-spec.md §3](../06-cli-spec.md) (`--scope .` / `--descendants` / `--all-scopes`)。デフォルト scope の定義も 06 §3 を正とする。

```text
default:
  scope registry で発見可能な全 `.kcs` を横断検索。

--here:
  現在フォルダの `.kcs` のみ。

--below:
  現在フォルダ配下の `.kcs` を含める。

--scope <path>:
  指定パスの `.kcs` のみ。

--scope <path> --below:
  指定パス配下の `.kcs` を含める。
```

AI Agent も CLI と同じスコープ規則を使う。

# GC / purge

GC は到達不能 object の掃除。過去 commit / tag / protected object から到達可能な raw / normalized / chunk / embedding / tree / commit は消さない。

purge は別物で、法務・秘匿・誤取り込みに対応する履歴破壊操作。対象 raw に由来する派生 artifact と index を削除し、必要に応じて tombstone を残す。

# 正本へ移した内容

```text
CAS / object / scope          → 03-data-model.md
commit / restore / search     → 05-runtime.md
scope registry / 運用規約      → 10-operations.md
CLI 表現                      → 06-cli-spec.md
```
