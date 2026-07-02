# 03 Data Model

統合元: `research/git_kcs.md` (CAS / DAG) + `research/kcs.md` (.kcs layout) + `research/hash.md` (identity) + `research/read_only.md` (write boundary)。いずれも正本ではない (経緯参照用)。

---

# 1. 概念モデル — CAS + Snapshot DAG

KCS は Git inspired な content-addressed store と snapshot DAG を、ローカルファイル全体に拡張したアーカイブ。

```
Object 種別:
  raw          原本ファイルバイト列
  prepared     Markdownize 前の中間表現 (page image, sheet etc.)
  image        文書内 embedded image (Markdownize 時に抽出。type は予約済み、実装は Step 2
               [09-mvp-scope.md §3.1](09-mvp-scope.md))
  normalized_unit  unit 単位の Markdown (read-only artifact, content hash 不採用)。
                   normalized の正本 (§2.1)
  chunk        normalized から見出し単位で切り出し
  embedding    chunk のベクトル表現
  tree         path → object_hash のスナップショット
  commit       tree + parents + metadata
```

raw / prepared / image / chunk / embedding / tree / commit は **CAS object** として `objects/<type>/ab/cd/<hash>` に保存。hash の算出は object 種別ごとに §8.1 で規定する: raw / prepared / image は**バイト列そのものの content hash**、tree / commit は **canonical JSON 保存バイト列の content hash**、chunk / embedding は **identity タプルから導出する identity hash**。normalized_unit は **path-named** で `objects/normalized_units/ab/cd/<raw_hash>.<tool_profile_hash>.g<gen>/` 配下に保存する (content hash 不採用、§5。詳細は §2.1)。ファイル全文の normalized Markdown は unit を決定論的に結合した **view (再生成可能な cache)** であり、正本ではない。

# 2. .kcs 物理レイアウト

```
.kcs/
  HEAD
  config.toml         folder-scope の設定 (ignore, chunking, search, budget)
  scope.json          scope_id (init 時採番の ULID、以後不変・export/import でも保持) と
                      このフォルダ自身・子 .kcs リンク (旧称 folder.json は廃止)
  tool-lock.json      Adapter capability 記録 (cmd/url/auth は含めない)
  manifest.json       working/index state (永続的真実は tree/commit object)
  objects/
    raw/ab/cd/<raw_hash>
    prepared/ab/cd/<prepared_hash>
    images/ab/cd/<image_hash>       # 文書内 embedded image (type 予約済み、実装 Step 2。
                                    # media_type は unit metadata に記録)
    normalized_units/ab/cd/<raw_hash>.<tool_profile_hash>.g<gen>/
      manifest.json                    # 順序付き unit 一覧 + unit status (正本, §2.1)
      <unit_ref>.json                  # unit object (unit_ref = base16(sha256(unit_key))[0:16])
    normalized/ab/cd/<raw_hash>.<tool_profile_hash>.g<gen>.md   # 全文 view (cache, 再生成可能)
    chunks/ab/cd/<chunk_hash>
    embeddings/ab/cd/<embedding_hash>
    trees/ab/cd/<tree_hash>
    commits/ab/cd/<commit_hash>
  refs/
    heads/main
    tags/<name>
  tombstones/ab/cd/<raw_hash>   purge の tombstone 記録 (05-runtime.md §3.5。CAS object ではない)
  index/
    sqlite.db         FTS5 + sqlite-vec (query acceleration layer; 真実は objects/)
  logs/
    access.jsonl
  packs/              v2+ (delta compression, MVP 対象外)
```

**format_version**: 旧称 `VERSION 0.1.0` (research/kcs.md) は `kcs_format_version` に統一。semver は [10-operations.md §12.5](10-operations.md) 参照。

## 2.1 normalized instance と全文 view

**normalized の正本は unit object 群** ([04-pipeline.md §2](04-pipeline.md))。1 つの
`(raw_hash, tool_profile_hash, gen)` の組を **normalized instance** と呼び、
`objects/normalized_units/ab/cd/<raw_hash>.<tool_profile_hash>.g<gen>/` ディレクトリ全体で表現する。

manifest schema:

```json
{
  "raw_hash": "sha256:abc...",
  "tool_profile_hash": "sha256:tool1...",
  "gen": 0,
  "parent_gen": null,
  "run_id": "run_01H...",
  "units": [
    {
      "order": 0,
      "unit_key": "page:1",
      "unit_ref": "3f2a9c0d1b4e5f60",
      "unit_type": "page",
      "status": "done",
      "prepared_hash": "sha256:...",
      "error_kind": null
    },
    {
      "order": 56,
      "unit_key": "page:57",
      "unit_ref": "9c1b7788aa02c3d4",
      "unit_type": "page",
      "status": "failed",
      "prepared_hash": "sha256:...",
      "error_kind": "invalid_input"
    }
  ],
  "generated_at": "2026-04-25T12:00:00Z"
}
```

unit object schema (`<unit_ref>.json`):

```json
{
  "unit_key": "page:12",
  "unit_type": "page",
  "raw_hash": "sha256:abc...",
  "prepared_hash": "sha256:...",
  "tool_profile_hash": "sha256:tool1...",
  "gen": 0,
  "mode": "full",
  "markdown": "## 3.2 認証仕様\n...",
  "reused_from": null,
  "generated_at": "2026-04-25T12:00:00Z"
}
```

`reused_from` は unit_mapping ([04-pipeline.md §2.2](04-pipeline.md)) による再利用の provenance:
`{ "raw_hash": "sha256:old...", "gen": 0, "unit_key": "page:11" }`。再利用時は unit object 本体を
新 instance へ **複製** する (per-.kcs 重複容認、§9)。

不変条件:

- unit object は read-only artifact。書き換え・削除しない (purge を除く)
- manifest の `units[].status` の遷移は `failed → done` の一方向のみ (部分失敗の再開、§6)。
  done unit の差し替えは `kcs reindex --force` による新 gen 作成のみ

**gen (generation)**: 同一 `(raw_hash, tool_profile_hash)` に対する instance の世代番号 (0 起点の整数)。
通常は `g0` のみ存在する。`kcs reindex --force` だけが `gen = 現最大 + 1` の新 instance を作り、
既存 instance は保全する ([07-adapter-spec.md §9](07-adapter-spec.md))。identity はあくまで
`(raw_hash, tool_profile_hash)` であり、gen は同一 identity 配下の instance の区別にのみ使う。
**normalized_hash の代替ではない** (§5: Markdown の content hash は計算・保存・比較しない)。
新規参照 (新規 commit の tree entry / 新規 chunk) は常に最新 gen を使う。

**全文 view**: `objects/normalized/ab/cd/<raw_hash>.<tool_profile_hash>.g<gen>.md` は
unit を決定論的に結合した **再生成可能な cache** であり、正本ではない。組み立て規則:

1. manifest.units を `order` 昇順に走査する
2. `status = done` の unit は、その `markdown` から末尾の連続する改行を除去した文字列を採用する
3. `status = failed` の unit は、固定文字列 `<!-- KCS-MISSING-UNIT <unit_key> <error_kind> -->` を採用する
4. 採用した文字列を `"\n\n"` で結合し、末尾に `"\n"` を 1 つ付す — これが view 本文
5. §10 のヘッダコメントを本文の前に付す。chunk の char offset は **unit-local** (当該 unit の
   `markdown` 本文先頭を 0 とする文字 span、§8.1) であり、全文 view 上の位置・ヘッダ・結合順は
   chunk identity に影響しない

view の破損・喪失・直接編集は `kcs repair` による再生成で解消する。up_to_date 判定 (§6) に
view の存在は使わない。

# 3. スコープ境界 (重要)

各 `.kcs` が管理するのは **その `.kcs` が配置されたフォルダ直下のファイルのみ** である。この規則は次の 3 点で一意に定まる:

1. 管理対象は scope フォルダ **直下** のファイルに限る。サブフォルダ配下のファイルは、そのサブフォルダに `.kcs` が存在するか否かに関わらず、親 `.kcs` の管理対象に **ならない** (再帰包含は行わない)。
2. サブフォルダは常に独立スコープの候補である。対象ファイルを含むサブフォルダには `kcs index` が子 `.kcs` を生成する ([06-cli-spec.md §1](06-cli-spec.md), [10-operations.md §4](10-operations.md))。ignore されたサブツリーには子 `.kcs` を生成しない。
3. したがって tree entry の `path`、Evidence Pointer の `path_at_commit`、task の `input_path` は **パス区切り (`/`) を含まないファイル名** である。`/` を含む path を持つ tree / pointer は schema violation (`KCS-E-STORE-PATH-001`) として拒否する。

ファイルの位置は `scope_path` (正本 `.kcs` の絶対パス) + ファイル名で一意に表現される。「フォルダ木を横断してファイルを探す」体験は、個々の `.kcs` の再帰包含ではなく scope_registry を使った横断検索 ([05-runtime.md §1.8](05-runtime.md)) が担う。

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
3. .kcs 喪失は復旧不能 (検証とバックアップの運用は 10-operations.md §7.5)
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

## 5.3 chunking_config_hash 計算規約

chunk 境界は Adapter ではなく core 側の chunking 設定 (`.kcs/config.toml [chunking]`、§11) で決まるため、`tool_profile_hash` には畳み込まれない。chunk / embedding の世代判定用に独立の hash を持つ:

```text
chunking_config_hash = "sha256:" + base16(sha256(JCS({
  spec_version: <int>,
  strategy: "heading",
  max_chars: 6000
})))
```

- 対象は `[chunking]` 配下の **chunk 境界に影響する全キー**。キーを追加したら `spec_version` を bump する
- デフォルト値も明示的に畳み込む (キー省略と明示指定を識別しない)
- これは同一性 hash であり、identity には使わない。chunk identity は §8.1 のとおり `(raw_hash, tool_profile_hash, gen, unit_key, heading_path, section_id, char_start, char_end)` のまま。`chunking_config_hash` は chunk の**世代**を表すメタデータに留める

# 6. Up_to_date 判定

ファイルが Markdown 化済みかの判定は、最新 normalized instance の manifest と unit object の存在 (§2.1) のみで決定する。Markdown content hash 一致は **判定条件に含めない** (§5)。

```python
current_raw_hash = hash(file)
inst = latest_instance(current_raw_hash, current_tool_profile_hash)
       # objects/normalized_units/ 配下の最大 gen の manifest (§2.1)
if inst is None:
    pending
elif any(u.status == "failed" for u in inst.units):
    partial          # 成功 unit は検索対象。失敗 unit のみ再投入 (04-pipeline.md §5.2)
elif all(u.status == "done" and unit_object_exists(u) for u in inst.units):
    up_to_date
else:
    missing_output   # manifest は done を記録しているが unit object が見当たらない
```

判定の正本は manifest + unit object の存在であり、SQLite の `normalization_runs` は cache
([04-pipeline.md §5.7](04-pipeline.md) の再構築セマンティクス参照)。全文 view の存在は判定に使わない。

ファイル状態分類:

```
new            初めて見つかった原文
up_to_date     最新 Markdown あり
modified       path 同じだが raw_hash が変わった
tool_changed   raw_hash 同じだが tool_profile_hash が変わった
partial        一部 unit の Markdownize が失敗 (成功 unit は検索対象、欠損は kcs status に表示)
missing_output manifest は done を記録しているが unit object ファイルが見当たらない
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

ファイル削除を検出しても files 行は **DELETE しない**。`status = 'deleted'` に更新し、最後に観測した raw_hash を保持する (`--include-deleted` 検索の判定に使う、[05-runtime.md §1.6](05-runtime.md))。同一 path が再作成されたら status を戻す。

## normalization_runs

```sql
CREATE TABLE normalization_runs (
  run_id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL,
  path TEXT NOT NULL,
  raw_hash TEXT NOT NULL,
  tool_profile_hash TEXT NOT NULL,
  gen INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,         -- pending | running | done | partial | failed
  mode TEXT NOT NULL,           -- full | incremental
  parent_run_id TEXT,           -- incremental の chain
  changed_unit_keys TEXT,       -- JSON array
  fallback_reason TEXT,         -- capability_missing | threshold_exceeded | ...
  started_at TEXT,
  finished_at TEXT,
  error TEXT
);
```

`normalized_path` 列は持たない。instance は `(raw_hash, tool_profile_hash, gen)` から一意に決まる。
`normalization_runs` は `index/sqlite.db` 上の cache であり、喪失時の復元範囲は
[04-pipeline.md §5.7](04-pipeline.md) に従う。

## 8.1 Object hash 算出規約

object hash は artifact identity と Evidence Pointer の永続性 (08 §6) を支えるプロダクト契約であり、`tool_profile_hash` (§5.1) と同じ厳密さで固定する。

**共通規則**:

- hash 表記は `"sha256:" + base16(sha256(...))` (小文字 hex)。
- fan-out パス `objects/<type>/ab/cd/<hash>` の `ab` / `cd` は、`sha256:` プレフィックスを除いた digest の先頭 2 文字 / 続く 2 文字。
- object 本体は**自身の hash を含めない** (Git 同様、保存キーが ID。旧 `tree_id` / `commit_id` フィールドは廃止)。
- 人間向け表示は先頭 12 hex への短縮可 (`sha256:9f2c1a7b04de…`)。`--json` は完全 hash ([06-cli-spec.md §4](06-cli-spec.md))。
- 本規約の変更は `kcs_format_version` の MAJOR bump (migration plan 必須)。

**raw / prepared / image** — content hash:

```text
raw_hash      = "sha256:" + base16(sha256(原本ファイルのバイト列))
prepared_hash = "sha256:" + base16(sha256(prepared object のバイト列))
image_hash    = "sha256:" + base16(sha256(抽出画像のバイト列))
```

**tree / commit** — canonical JSON の content hash:

- object は RFC 8785 JCS canonical form の JSON バイト列として保存する。
- `tree_hash` / `commit_hash` = 保存バイト列の sha256。検証は再ハッシュのみで足りる。
- 種別誤認防止のため object 本体に `"object_type": "tree" | "commit"` を必須で含める (Git の object header 相当)。
- tree の `entries` は `path` の UTF-8 バイト列昇順で一意にソートする。同一 `path` の重複 entry は禁止。
- commit の `parents` は commit_hash の配列。第一要素は直前 HEAD (first parent)。
- timestamp は UTC ISO8601 + `Z` ([06-cli-spec.md §12](06-cli-spec.md))。
- `HEAD` / `refs/heads/*` / `refs/tags/*` の値は commit_hash。

**chunk** — identity hash:

```text
chunk_hash = "sha256:" + base16(sha256(JCS({
  "spec_version": 1,
  "raw_hash": "...",
  "tool_profile_hash": "...",
  "gen": <int>,
  "unit_key": "...",
  "heading_path": ["...", "..."],
  "section_id": "...",
  "char_start": <int>,
  "char_end": <int>
})))
```

- `gen` は normalized unit の世代番号、`unit_key` は chunk が属する unit の識別子 (例 `page:12`)。`char_start` / `char_end` は **unit-local** (当該 unit 本文先頭を 0 とする文字 span)。
- null / 未設定フィールドは hash 入力に含めない (§5.1 と同じ規則。`section_id` を持たない chunking strategy では省略)。
- chunk object 本体 (`text_hash` 等を含む) は `chunk_hash` をキーに保存されるが、`text_hash` は **hash 入力に含めない**。Markdown は LLM ベース非決定的であり (§5)、chunk の同一性は原文 + tool capability + unit 世代 + 構造的位置 + span のみで決まるため。

**embedding** — identity hash:

```text
embedding_hash = "sha256:" + base16(sha256(JCS({
  "spec_version": 1,
  "target_type": "chunk",
  "target_hash": <chunk_hash>,
  "profile_hash": <embedding profile_hash>,
  "modality": "...", "dimensions": <int>, "distance": "..."
})))
```

## tree / commit object

```json
// tree — objects/trees/3f/9a/<tree_hash> に JCS 形式で保存 (tree_hash は保存バイト列の sha256)
{
  "object_type": "tree",
  "entries": [
    {
      "path": "report.pdf",
      "type": "file",
      "raw_hash": "sha256:abc...",
      "normalize": { "tool_profile_hash": "sha256:tool1...", "gen": 0 }
    }
  ]
}

// commit — objects/commits/9f/2c/<commit_hash> に JCS 形式で保存
{
  "object_type": "commit",
  "tree": "sha256:3f9a...",
  "parents": ["sha256:71bd..."],
  "created_at": "2026-04-29T12:00:00Z",
  "message": "snapshot after indexing docs",
  "tool_lock_hash": "sha256:...",
  "stats": { "files_added": 12, "files_modified": 3, "files_deleted": 1 },
  "commit_type": "manual"
}
```

JCS ではキー順は canonical 化時に自動決定されるため、上記の記載順は可読性のためのもの。

tree entry の `normalize` ブロックは **optional**。normalized instance が存在しないファイル (未 Markdownize) の
entry では `normalize` を**省略**する (省略 = 当該ファイルの normalized / chunk は存在しない。`null` は書かない —
§5.1 の「省略と null を識別しない」に従う)。Step 1 (pipeline 未実装) では全 entry が `normalize` 省略形になり、
Step 2 で Markdownize されたファイルから順に `normalize` 付き entry へ移行する。

`normalize` が存在する場合、tree entry の `gen` は commit 時点で参照していた normalized instance の世代 (§2.1)。フィールド欠落は `gen = 0`
と読む (forward compatible)。`kcs reindex --force` 後も過去 commit の tree entry は旧 gen を
指し続けるため、`kcs view --at` ([05-runtime.md §4.2](05-runtime.md)) と Evidence Pointer の
不変性保証 ([08-evidence-pointer-spec.md §6](08-evidence-pointer-spec.md)) は gen 保全により成立する。

`commit_type` は固定 enum (詳細は [05-runtime.md §2](05-runtime.md)):

```
manual | auto | imported | migrated | repaired | merged | purged
```

SQLite CHECK 制約で固定し、**この値域は永久に変更しない契約** (semver MAJOR でも bump しない)。

## 8.2 tree のスケール前提 (flat entries)

tree は entries を単一の flat 配列で持つ。スコープ境界規則 (§3) により entry 数は scope フォルダ直下のファイル数に一致し、1 tree に階層は存在しないため、Git 式のディレクトリ単位 tree object (サブツリー hash 共有) は導入しない。

サイズ見積り (1 entry ≈ 150-250 bytes):

| 直下ファイル数 | tree object サイズ | 備考 |
| --- | --- | --- |
| 100 | 約 25 KB | 典型的なフォルダ |
| 1,000 | 約 250 KB | 大きめの Downloads 等 |
| 10,000 | 約 2.5 MB | 想定上限 (soft limit) |

規範:

- 1 scope の直下ファイル数の想定上限は 10,000 (soft limit)。超過時 `kcs index` は警告を表示し、サブフォルダへの分割または ignore を提案する (処理自体は継続する)
- snapshot 時に tree_hash が現在の HEAD の tree と一致する場合、auto snapshot は commit を作らない (no-op、[05-runtime.md §8](05-runtime.md))。tree は CAS object なので、内容不変なら新規 object も生成されない (tree_hash は保存バイト列の content hash、§8.1)
- 1 ファイルの変更で tree 全体 (上表のサイズ) が新 object として書かれるのは仕様どおりの挙動である。pack/delta 圧縮 (§2, v2+) の導入判断は、この見積りの実測値で再評価する

## chunk

```json
{
  "chunk_hash": "sha256:chunk",
  "raw_hash": "sha256:abc",
  "tool_profile_hash": "sha256:tool1",
  "gen": 3,
  "unit_key": "page:12",
  "heading_path": ["認証仕様", "API Token"],
  "section_id": "auth/api-token",
  "char_start": 1200,
  "char_end": 1500,
  "chunking_config_hash": "sha256:cfg1",
  "text_hash": "sha256:text"
}
```

chunk identity は `(raw_hash, tool_profile_hash, gen, unit_key, heading_path, section_id, char_start, char_end)` で決まり、chunk_hash の算出式は §8.1 に定める (heading_path と section_id は両方 hash 入力。未設定フィールドは省略。`char_start` / `char_end` は unit-local)。`text_hash` は **chunk 抽出範囲のみ** の hash であり、Markdown 全体の hash ではない。`chunking_config_hash` は chunk の**世代**を表すメタデータであり、identity には含めない (§5.3)。chunk object 本体が `gen` を保持するため、tree を失った shallow commit からでも chunk_hash → chunk object → gen で normalized unit instance まで直接解決できる ([08-evidence-pointer-spec.md §3.1](08-evidence-pointer-spec.md))。

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
image objects (抽出画像)        | no   | yes  | no           | no
chunks / embeddings            | no   | yes  | no           | no
annotations / tags / notes     | yes  | no   | yes          | yes
nodes / edges (Phase 5)        | yes  | no   | yes          | yes
commits / refs (履歴)           | no   | yes  | no           | yes (auto commit)
extraction issues              | yes  | yes  | yes          | yes
```

`*` 「原本の移動」は `kcs move --accept` 経由でのみ KCS が原本を mv する。原本の **内容** は不変なので write ではなく移動。Agent が `kcs move --accept` を直接呼ぶことは禁止 (`--propose` 経由のみ)。

normalized (unit object および全文 view) は **read-only artifact**。全文 view の生成時に付与する
Markdown ヘッダ template:

```markdown
<!--
KCS GENERATED FILE
Do not edit manually.
Source: report.pdf
Raw-Hash: sha256:...
Tool-Profile-Hash: sha256:...
Generated-At: 2026-04-25T12:00:00Z
-->
```

ハッシュ検証で破損検出はしない (§5: Markdown content hash を持たないため)。unit object が直接編集された場合でも次回 `kcs index` は `(raw_hash, tool_profile_hash)` 一致で「up-to-date」と判定する (= Markdown 内容そのものは正本ではなく、原文 + tool_profile が正本)。全文 view (`objects/normalized/*.md`) は cache のため、直接編集は次回 view 再生成で破棄される。

# 11. 設定ファイル

`~/.config/kcs/tools.toml` (デバイスローカル, 共有 `.kcs` には含まれない):

```toml
[markdown.mistral_ocr_markdownize]
kind = "online_api"
cmd = "uvx kcs-mistral-ocr-adapter"
model = "mistral-ocr-latest"        # config では可変 alias 可。tool_profile の pin は解決済み immutable 版 (§5.1)
profile_hash = "sha256:..."
capabilities = ["ocr", "layout_detection", "table_extraction"]
```

`.kcs/config.toml`:

```toml
[scope]
participates_in_global_search = true
[chunking]
strategy = "heading"
max_chars = 6000
# [chunking] の変更は chunking_config_hash (§5.3) の変化として検出され、
# chunk / embedding のみ再生成される (再 Markdownize しない)。規則は 04-pipeline.md §4.6
[markdownize.incremental]
enabled = true
threshold = 0.30
max_consecutive = 5
[budget]                   # folder cap (任意の追加制限)。device cap との判定は 04-pipeline.md §5.4
monthly_usd_cap = 10.0
[gc]
mode = "manual_only"           # MVP デフォルト。GC 実行系の実装は Phase 4+ (05-runtime.md §2.3)
idle_threshold_seconds = 300
```

すべての設定は JSON Schema/TOML Schema で validate ([10-operations.md §12.3](10-operations.md))。
