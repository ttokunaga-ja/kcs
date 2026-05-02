# 03 Data Model

統合元: `git_kcs.md` (CAS / DAG) + `kcs.md` (.kcs layout) + `hash.md` (identity) + `read_only.md` (write boundary)。

---

# 1. 概念モデル — CAS + Snapshot DAG

KCS は Git inspired な content-addressed store と snapshot DAG を、ローカルファイル全体に拡張したアーカイブ。

```
Object 種別:
  raw          原本ファイルバイト列
  prepared     Markdownize 前の中間表現 (page image, sheet etc.)
  normalized   Markdown (read-only artifact, content hash 不採用)
  chunk        normalized から見出し単位で切り出し
  embedding    chunk のベクトル表現
  tree         path → object_hash のスナップショット
  commit       tree + parents + metadata
```

raw / prepared / chunk / embedding / tree / commit は **CAS object** として `objects/<type>/ab/cd/<hash>` に保存。normalized は **path-named** で `objects/normalized/ab/cd/<raw_hash>.<tool_profile_hash>.md`。

# 2. .kcs 物理レイアウト

```
.kcs/
  HEAD
  config.toml         folder-scope の設定 (ignore, chunking, search, budget)
  scope.json          このフォルダ自身と子 .kcs リンク (旧称 folder.json は廃止)
  tool-lock.json      Adapter capability 記録 (cmd/url/auth は含めない)
  manifest.json       working/index state (永続的真実は tree/commit object)
  objects/
    raw/ab/cd/<raw_hash>
    prepared/ab/cd/<prepared_hash>
    normalized/ab/cd/<raw_hash>.<tool_profile_hash>.md
    chunks/ab/cd/<chunk_hash>
    embeddings/ab/cd/<embedding_hash>
    trees/ab/cd/<tree_hash>
    commits/ab/cd/<commit_hash>
  refs/
    heads/main
    tags/<name>
  index/
    sqlite.db         FTS5 + sqlite-vec (query acceleration layer; 真実は objects/)
  logs/
    access.jsonl
  packs/              v2+ (delta compression, MVP 対象外)
```

**format_version**: `kcs.md` 旧称 `VERSION 0.1.0` は `kcs_format_version` に統一。semver は `productization_notes.md §12.5` 参照。

# 3. スコープ境界 (重要)

各 `.kcs` が管理するのは **その `.kcs` が配置されたフォルダ自身が直接保持するファイルのみ**。サブフォルダに別の `.kcs` がある場合、そのサブツリーは独立スコープ (子 `.kcs`) であり、親 `.kcs` は子配下を再帰取り込みしない。

```
親 .kcs と子 .kcs 間で同一ファイルが二重 object 保存されることは発生しない。
別 .kcs 間の同一内容ファイルは、ユーザーが意図的に複数フォルダへ配置した場合に限り
物理的重複保存を許容する (per-.kcs dedup, cross-.kcs dedup なし)。
```

# 4. 二層構造 — truth vs cache

```
truth = folder-local .kcs           raw object / normalized / chunks / commits / refs
cache = scope_registry / aggregator 検索の探索対象一覧 / stale 検出 / UI 統合
```

`scope_registry` 保存先: `~/.local/share/kcs/scope-registry.sqlite`。

不変条件:

```
1. scope_registry のみで .kcs の状態を変える実装は禁止
2. scope_registry 喪失は再構築可能 (各 .kcs を rescan)
3. .kcs 喪失は復旧不能
4. 検索結果メタには「正本の .kcs パス」を必ず含める
5. raw object の所有権・dedup は scope_registry でグローバル化しない
```

# 5. Identity — hash と semantic_fingerprint の分離

```
raw_hash             原文バイト列の同一性 (1 バイト違えば別 object)
tool_profile_hash    Adapter capability の identity (§5.1)
tool_lock_hash       tool-lock.json 全体を畳み込んだ識別子 (§5.2)
semantic_fingerprint 意味的・視覚的・構造的な近さ (page fingerprint, embedding 等)
```

ルール:

- 同一性判定 (up_to_date / dedup) には hash を使う
- 類似性判定 (重複候補提示, page reuse, 分類) には semantic_fingerprint を使う
- 命名で区別 (`*_hash` vs `*_fingerprint`)
- **Markdown content hash (normalized_hash 等) は採用しない**。Markdown は LLM ベース非決定的なため。Markdown 識別は `(raw_hash, tool_profile_hash)` のみ

## 5.1 tool_profile_hash 計算規約

artifact identity は `(raw_hash, tool_profile_hash)` 単独に依存するため、計算規約をプロダクト契約として固定する。

**ハッシュ対象フィールド (capability hash)** — 決定性に影響する情報のみ。`cmd`/`args`/`url`/認証情報は **絶対に含めない**:

```
adapter_kind          "markdownize" | "embedding" | "ocr" | ...
adapter_role          "text" | "image" | "multimodal"
model_or_tool_family  "gemini-2.5-pro" | "gpt-4o" | "tesseract" の正規化名
model_version_pin     ベンダー側 immutable tag (latest 等の可変 alias は禁止)
prompt_template_id    KCS が管理する prompt 識別子
prompt_template_hash  prompt 本文を canonical 化した sha256
sampling              {temperature, top_p, top_k, max_tokens, seed}
output_schema         期待する Markdown / JSON schema id とバージョン
dimensions / distance / modality   embedding 専用
runtime_kind          "cloud" | "local" (capability レベル)
spec_version          この計算規約自体のバージョン
```

実装バイナリのバージョン (`adapter_binary_version`, OS, ハードウェア) は **`binary_hash` として別保存**し、`tool_profile_hash` には含めない。これにより Adapter のマイナー bug fix で全 re-index が走らない。

**算出式** (RFC 8785 JCS 準拠):

```
tool_profile_hash = "sha256:" + base16(sha256(JCS(canonicalize(profile_fields))))
```

null フィールドは hash 入力に含めない (省略と null を識別しない)。

**prompt_template_hash**:

```
1. trim trailing whitespace per line
2. normalize line endings to \n
3. NFC 正規化
4. 末尾の空行を削除
5. sha256, "sha256:" プレフィックス
```

`spec_version` の bump は breaking change 扱い (migration plan 必須)。

## 5.2 tool_lock_hash 計算規約

commit object 等で参照される `tool_lock_hash` は `tool-lock.json` 全体の identity:

```
tool_lock_hash = "sha256:" + base16(sha256(JCS({
  spec_version: <int>,
  prepare:        { tool_id, profile_hash },
  markdown:       { tool_id, profile_hash },
  embedding:      { tool_id, profile_hash, dimensions, distance, modality },
  summary:        { tool_id, profile_hash },         # optional
  classification: { tool_id, profile_hash },         # optional
  rerank:         { tool_id, profile_hash }          # optional
})))
```

`cmd`/`args`/`url`/`config_hash`/capabilities は入力に含めない。embedding のみ次元・距離・modality を含めるのは、横断検索互換性 (§7) の決定根拠になるため。optional adapter は未設定なら省略 (null と識別しない)。

# 6. Up_to_date 判定

ファイルが Markdown 化済みかの判定は `(raw_hash, tool_profile_hash, status=done, 出力ファイル存在)` のみで決定する。Markdown content hash 一致は **判定条件に含めない** (§5)。

```python
current_raw_hash = hash(file)
run = find normalization_run
  where path = file.path
  and raw_hash = current_raw_hash
  and tool_profile_hash = current_tool_profile_hash
  and status = done
if run exists and file_exists(run.normalized_path):
    up_to_date
else:
    pending
```

ファイル状態分類:

```
new            初めて見つかった原文
up_to_date     最新 Markdown あり
modified       path 同じだが raw_hash が変わった
tool_changed   raw_hash 同じだが tool_profile_hash が変わった
missing_output done 記録あるが normalized_path のファイルが見当たらない
failed         前回 Markdown 化失敗
pending        実行待ち
```

`corrupted` (Markdown content hash 不一致) は採用しない。Markdown は read-only artifact として content hash を持たないため。

# 7. Embedding 互換性ルール

複数 `.kcs` 横断 vector 検索の条件:

```
dimensions / distance / modality / embedding profile_hash がすべて一致
```

不一致なら BM25 のみ横断検索、または再 index 要求。

# 8. 主要テーブル / object スキーマ

## files (working state)

```sql
CREATE TABLE files (
  file_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  raw_hash TEXT NOT NULL,
  size_bytes INTEGER,
  mtime INTEGER,
  kind TEXT NOT NULL,
  first_seen_at TEXT,
  last_seen_at TEXT,
  status TEXT NOT NULL
);
```

## normalization_runs

```sql
CREATE TABLE normalization_runs (
  run_id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL,
  path TEXT NOT NULL,
  raw_hash TEXT NOT NULL,
  tool_profile_hash TEXT NOT NULL,
  normalized_path TEXT NOT NULL,
  status TEXT NOT NULL,         -- pending | running | done | failed
  mode TEXT NOT NULL,           -- full | incremental
  parent_run_id TEXT,           -- incremental の chain
  changed_unit_keys TEXT,       -- JSON array
  fallback_reason TEXT,         -- capability_missing | threshold_exceeded | ...
  started_at TEXT,
  finished_at TEXT,
  error TEXT
);
```

## tree / commit object

```json
// tree
{
  "tree_id": "tree_abc",
  "entries": [
    {
      "path": "docs/report.pdf",
      "type": "file",
      "raw_hash": "sha256:abc",
      "normalize": { "tool_profile_hash": "sha256:tool1" }
    }
  ]
}

// commit
{
  "commit_id": "kcs_01H...",
  "tree": "tree_abc",
  "parents": ["kcs_01G..."],
  "created_at": "2026-04-29T12:00:00Z",
  "message": "snapshot after indexing docs",
  "tool_lock_hash": "sha256:...",
  "stats": { "files_added": 12, "files_modified": 3, "files_deleted": 1 },
  "commit_type": "manual"
}
```

`commit_type` は固定 enum (詳細は [05-runtime.md §2](05-runtime.md)):

```
manual | auto | imported | migrated | repaired | merged | purged
```

SQLite CHECK 制約で固定し、**この値域は永久に変更しない契約** (semver MAJOR でも bump しない)。

## chunk

```json
{
  "chunk_hash": "sha256:chunk",
  "raw_hash": "sha256:abc",
  "tool_profile_hash": "sha256:tool1",
  "heading_path": ["認証仕様", "API Token"],
  "section_id": "auth/api-token",
  "char_start": 1200,
  "char_end": 1500,
  "text_hash": "sha256:text"
}
```

chunk identity は `(raw_hash, tool_profile_hash, heading_path/section_id, char_start, char_end)` で決まる。`text_hash` は **chunk 抽出範囲のみ** の hash であり、Markdown 全体の hash ではない。

# 9. Dedup スコープ

```
dedup scope            = one .kcs object store
cross-.kcs dedup       = not guaranteed
cross-.kcs GC scope    = none (各 .kcs に閉じる)
```

per-`.kcs` の prepared/normalized/embedding 重複と purge の `.kcs` 単位スコープは、将来 LLM コスト低下/ローカル LLM 進展前提で **容認** ([01-positioning.md](01-positioning.md))。

# 10. 書き込み主体マトリクス

```
レイヤー                       | User | KCS  | Agent (提案) | Agent (自動適用)
------------------------------ | ---- | ---- | ------------ | ----------------
原本 (raw)                     | yes  | no*  | propose      | no
原本の移動 (file system mv)     | yes  | yes* | propose      | user 承認後のみ
normalized markdown            | no   | yes  | no           | no
chunks / embeddings            | no   | yes  | no           | no
annotations / tags / notes     | yes  | no   | yes          | yes
nodes / edges (Phase 5)        | yes  | no   | yes          | yes
commits / refs (履歴)           | no   | yes  | no           | yes (auto commit)
extraction issues              | yes  | yes  | yes          | yes
```

`*` 「原本の移動」は `kcs move --accept` 経由でのみ KCS が原本を mv する。原本の **内容** は不変なので write ではなく移動。Agent が `kcs move --accept` を直接呼ぶことは禁止 (`--propose` 経由のみ)。

normalized は **read-only artifact**。Markdown ヘッダ template:

```markdown
<!--
KCS GENERATED FILE
Do not edit manually.
Source: docs/report.pdf
Raw-Hash: sha256:...
Tool-Profile-Hash: sha256:...
Generated-At: 2026-04-25T12:00:00Z
-->
```

ハッシュ検証で破損検出はしない (§5: Markdown content hash を持たないため)。直接編集された場合でも次回 `kcs index` は `(raw_hash, tool_profile_hash)` 一致で「up-to-date」と判定する (= Markdown 内容そのものは正本ではなく、原文 + tool_profile が正本)。

# 11. 設定ファイル

`~/.config/kcs/tools.toml` (デバイスローカル, 共有 `.kcs` には含まれない):

```toml
[markdown.markdown_default]
kind = "local_adapter"
cmd = "uvx kcs-markdownize-adapter"
profile_hash = "sha256:..."
capabilities = ["ocr", "layout_detection", "incremental_update"]
```

`.kcs/config.toml`:

```toml
[scope]
participates_in_global_search = true
[chunking]
strategy = "heading"
max_chars = 6000
[markdownize.incremental]
enabled = true
threshold = 0.30
max_consecutive = 5
[budget]
monthly_usd_cap = 50.0
[gc]
mode = "on_idle"
idle_threshold_seconds = 300
```

すべての設定は JSON Schema/TOML Schema で validate ([productization_notes.md §12.3](productization_notes.md))。
