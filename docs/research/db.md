# DB / Search Backend Research Notes

> Status: integrated
> Canonical refs: [../04-pipeline.md](../04-pipeline.md), [../05-runtime.md](../05-runtime.md)

---

# 結論

SQLite は query acceleration layer。正本ではない。

```text
truth:
  .kcs/objects, commits, refs

cache / index:
  SQLite metadata, FTS5, sqlite-vec, tasks
```

SQLite が壊れても object store と commit から再構築できる設計にする。

# backend

```text
SQLite:
  manifest、object metadata、tasks、evidence、access log。

FTS5:
  Normalized Markdown / chunk の全文検索。

sqlite-vec:
  chunk embedding / node embedding の vector search。
```

MVP は SQLite + FTS5 + sqlite-vec を標準 backend とする。外部 DB は v2 以降。

# search mode

| Mode | 動作 |
| --- | --- |
| `auto` | vector があれば hybrid、なければ text |
| `text` | FTS5 のみ |
| `vector` | sqlite-vec のみ。使えなければ error |
| `hybrid` | FTS5 + sqlite-vec。vector 不可時は設定に従い fallback / error |

# fallback

Embedding 未生成、profile mismatch、sqlite-vec unavailable の場合:

```text
kcs search:
  text fallback 可。warning を出す。

kcs search --vector:
  error。

kcs search --hybrid:
  設定に従い fallback または error。
```

# schema の核

```text
chunks:
  chunk_id, raw_hash, normalized_ref, unit_key, text, span, evidence pointer fields

chunk_fts:
  FTS5 external content table

embeddings:
  target_id, profile_hash, dimensions, distance, vector_ref

tasks:
  task_type, input_hash, tool_profile_hash, state, attempts
```

詳細 schema は正本へ移動済み。

# 横断検索

複数 `.kcs` の横断検索は scope registry を使う。ただし registry は cache であり、検索結果には必ず正本 `.kcs` path / scope id を含める。

# 正本へ移した内容

```text
SQLite schema / task relation    → 04-pipeline.md
search mode / fallback / cursor  → 05-runtime.md
CLI                              → 06-cli-spec.md
```
