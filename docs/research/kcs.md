## `.kcs` の最終設計案

> NOTE: この文書は `.kcs` ディレクトリ構造の初期設計案を含む。object store / snapshot DAG / デフォルト検索範囲については、後続の [git_kcs.md](git_kcs.md) と [philosophy.md](philosophy.md) の方針を優先する。プロダクト位置づけ・ターゲット・MVP スコープは [positioning.md](positioning.md) を参照。

`.kcs` は、基本的に **各フォルダに隠しディレクトリとして生成されるフォルダローカルな知識メタデータ**です。macOS の `.DS_Store` に近く、子フォルダや孫フォルダにもそれぞれ `.kcs` が存在する前提です。
ただし、Prepare・Markdownize（OCRを含む）・マルチモーダル Embedding・optional Summary / Classification / Rerank などの実行方法は `.kcs` に直接持たせません。Adapter の実行設定、コマンドパス、URL、認証情報は各デバイスの `~/.config/kcs/` や OS keychain に保存し、`.kcs` は生成済み artifact の provenance と互換性判定に必要な profile hash だけを保持します。

> **二層構造 (重要)**: KCS のデータ・所有権・権限の **正本は各フォルダ直下の `.kcs`** に閉じます (truth)。device-local な scope_registry (`~/.local/share/kcs/scope-registry.sqlite`) や将来の global aggregator は **検索キャッシュ・発見補助に過ぎません** (cache)。両者を混同しないでください。scope_registry のみを更新して `.kcs` の状態が変わる実装は禁止です。scope_registry 喪失は再構築可能 (各 `.kcs` を rescan)、`.kcs` 喪失は復旧不能。詳細は [productization_notes.md §3](productization_notes.md), [positioning.md §7](positioning.md)。

> **スコープ境界 (重要)**: 各 `.kcs` が管理するのは **その `.kcs` が配置されたフォルダ自身が直接保持するファイルのみ** です。サブフォルダに別の `.kcs` が存在する場合、そのサブツリーは独立したスコープとして子 `.kcs` が管理し、親 `.kcs` は子 `.kcs` 配下のファイルを再帰的に取り込んで object 化することはありません。したがって、階層的に `.kcs` が並んでも、親子間で同一ファイルが二重に object 保存されることは発生しません。横断検索は scope registry (= cache レイヤー) を通じて複数 `.kcs` を束ねる別レイヤーで実現します (詳細は本文書 §6 と [git_kcs.md](git_kcs.md))。

`.kcs` が分散配置されるため、raw / normalized object の dedup は **各 `.kcs/objects` 内** に限定します。別フォルダの別 `.kcs` に同一内容のファイルがある場合 (= ユーザーが意図的に複数フォルダへ同一ファイルを配置した場合) は、フォルダ単位の独立性・部分公開・partial sync・purge の単純さを優先し、物理的な重複保存を許容します。これは「親 `.kcs` がサブツリーを再帰的に取り込んで生じる重複」ではなく、ユーザーのファイル配置に起因する重複である点に注意してください。

---

# 1. 全体構造

```text
target-folder/
  .kcs/
    VERSION
    scope.json
    config.toml
    manifest.json
    tool-lock.json
    normalized/
    index/
      sqlite.db
      bm25/
      vector/
    objects/
      chunks/
      nodes/
      edges/
      commits/
    refs/
      heads/
      tags/
    logs/
      access.jsonl
      events.jsonl
    cache/
    tmp/
  child-folder/
    .kcs/
    grandchild-folder/
      .kcs/
```

実装初期の bootstrap layout は以下から始めてもよい。ただし、これはプロダクトMVPの完了条件ではない。MVPは検索体験を損なわない基本機能セットを実装する。

```text
.kcs/
  VERSION
  scope.json
  config.toml
  manifest.json
  tool-lock.json
  normalized/
  index/
    sqlite.db
```

---

# 2. `.kcs` が持つもの / 持たないもの

## `.kcs` が持つもの

```text
スコープ情報
対象ファイル一覧
Markdown化済みファイル
チャンク情報
検索インデックス
Evidence Pointer
知識ノード
アクセスログ
KCS履歴
使用したTool Profileの記録
```

## `.kcs` が持たないもの

```text
APIキー
秘密情報
外部ツール本体
Prepareツールの詳細実装
Markdownizeツールの詳細実装
Embeddingツールの詳細実装
Summary / Classification / Rerankツールの詳細実装
```

---

# 3. グローバル設定との関係

外部ツールはユーザー共通設定に置きます。

```text
~/.config/kcs/
  config.toml
  tools.toml
  credentials.toml   # 可能ならOS keychain推奨
```

`.kcs` は、実体ではなく **どのprofileでartifactが生成されたか**だけを参照します。

共有・export される `.kcs` から、別デバイスの任意コマンドや URL が誘導実行されてはなりません。`.kcs` に残してよいのは、`tool_profile_hash`、`adapter_kind`、`model_or_tool_family`、`dimensions`、`distance`、artifact の input / output hash などの非実行情報です。

---

# 4. `~/.config/kcs/tools.toml`

例：

```toml
[tools.prepare_default]
kind = "library"
library = "kcs_prepare_default"

[tools.markdown_default]
kind = "command"
cmd = "/Users/takumi/bin/markdownize"
args = ["--input", "{input}", "--output", "{output}"]

[tools.gemini_multimodal_embedding]
kind = "http"
url = "https://example.invalid/embedding"
method = "POST"

[tools.summary_default]
kind = "http"
url = "http://localhost:8000/summary"
method = "POST"

[tools.classification_default]
kind = "library"
library = "kcs_classification_rules"

[tools.rerank_default]
kind = "http"
url = "http://localhost:8000/rerank"

[defaults]
prepare = "prepare_default"
markdownize = "markdown_default"
embedding = "gemini_multimodal_embedding"
summary = "summary_default"
classification = "classification_default"
rerank = "rerank_default"
```

KCSは provider を制限せず、任意のコマンド・URL・パスを呼び出せるようにします。

---

# 5. `VERSION`

`.kcs` フォーマットのバージョン。

```text
0.1.0
```

---

# 6. `scope.json`

`.kcs` が配置されたフォルダ自身と、全体検索への参加ポリシーを定義します。

このファイル名を正とします。過去メモに出てくる `folder.json` は同じ概念の旧称であり、実装・契約ドキュメントでは `scope.json` に統一します。

```json
{
  "folder_id": "kcs_folder_01H...",
  "folder_path": ".",
  "parent": {
    "path": "../",
    "kcs_path": "../.kcs",
    "relation": "parent_link"
  },
  "children": [
    {
      "path": "Research/",
      "kcs_path": "Research/.kcs",
      "relation": "child_link"
    }
  ],
  "created_at": "2026-04-25T12:00:00Z",
  "format_version": "0.1.0",
  "policy": {
    "participates_in_global_search": true,
    "allow_restricted_scope_search": true
  }
}
```

重要ルール：

```text
デフォルト検索はKCSが認識している全 indexed scope を対象にする
初回の indexed scope は明示的に ignore されていないすべての対象範囲とする
現在フォルダだけ検索したい場合は --scope . を指定する
現在フォルダと配下だけ検索したい場合は --scope . --descendants を指定する
各 .kcs 自体は自フォルダ直下の情報と子フォルダリンクを保持する
子フォルダや孫フォルダにも、それぞれ独立した .kcs が存在する
```

---

# 7. `.kcs/config.toml`

スコープ固有設定のみを書きます。

```toml
[scope]
name = "research-notes"
root = "."
allow_parent_access = false

[tools]
prepare = "prepare_default"
markdownize = "markdown_default"
embedding = "gemini_multimodal_embedding"
summary = "summary_default"
classification = "classification_default"
rerank = "rerank_default"

[chunking]
strategy = "heading"
split_levels = [1, 2, 3]
min_chars = 300
max_chars = 6000
overlap_chars = 300
include_heading_path = true
preserve_blocks = true

[index]
text_index = "tantivy"
vector_index = "sqlite-vec"
fusion = "rrf"

[ignore]
patterns = [
  ".git/**",
  ".kcs/**",
  "node_modules/**",
  "target/**",
  "*.tmp",
  "*.log"
]
```

ポイント：

```text
.kcs/config.toml は「何を対象にするか」
~/.config/kcs/tools.toml は「どう処理するか」
```

---

# 8. `tool-lock.json`

非常に重要です。
インデックス作成時に使用した Adapter profile を記録します。ただし、共有 `.kcs` が任意コマンドや任意 URL の実行設定を運ばないよう、実行可能な `cmd`、`args`、`url`、認証情報は記録しません。

```json
{
  "prepare": {
    "tool_id": "prepare_default",
    "kind": "deterministic_library",
    "profile_hash": "sha256:...",
    "config_hash": "sha256:..."
  },
  "markdown": {
    "tool_id": "markdown_default",
    "kind": "local_adapter",
    "profile_hash": "sha256:...",
    "capabilities": ["ocr", "layout_detection", "incremental_update"],
    "config_hash": "sha256:..."
  },
  "embedding": {
    "tool_id": "gemini_multimodal_embedding",
    "kind": "online_api",
    "mode": "batch",
    "config_hash": "sha256:...",
    "dimensions": 1536,
    "distance": "cosine",
    "modality": "multimodal",
    "profile_hash": "sha256:..."
  },
  "summary": {
    "tool_id": "summary_default",
    "kind": "offline_api",
    "profile_hash": "sha256:...",
    "config_hash": "sha256:..."
  },
  "classification": {
    "tool_id": "classification_default",
    "kind": "deterministic_library",
    "profile_hash": "sha256:...",
    "config_hash": "sha256:..."
  },
  "rerank": {
    "tool_id": "rerank_default",
    "kind": "offline_api",
    "profile_hash": "sha256:...",
    "config_hash": "sha256:..."
  }
}
```

役割：

```text
どのprofileで作ったartifactか記録する
横断検索時の互換性を判定する
再indexが必要か判定する
共有先デバイスのAdapter設定を上書きしない
```

## 8.1 tool_lock_hash の計算規約

commit object 等で参照される `tool_lock_hash` は、`tool-lock.json` 全体を1つの hash に畳み込んだものです。各 adapter の `profile_hash` 計算規約は [hash.md §9.1](hash.md) に従います。

```text
tool_lock_hash =
  "sha256:" + base16(
    sha256(
      JCS({
        spec_version: <int>,
        prepare:        { tool_id, profile_hash },
        markdown:       { tool_id, profile_hash },
        embedding:      { tool_id, profile_hash, dimensions, distance, modality },
        summary:        { tool_id, profile_hash },         # optional
        classification: { tool_id, profile_hash },         # optional
        rerank:         { tool_id, profile_hash }          # optional
      })
    )
  )
```

ルール:

- `cmd`, `args`, `url`, `config_hash`, capabilities などの実行可能・派生情報は **`tool_lock_hash` の入力に含めない**。`tool_lock_hash` は capability identity のみを表現する。
- optional adapter (summary 等) が未設定の場合、そのキーごと省略する (= null と未設定を識別しない)。
- `embedding` のみ次元・距離・modality を含めるのは、横断検索互換性 (§9) の決定根拠になるため。
- `tool_lock_hash` の `spec_version` は `tool-lock.json` 自体の schema バージョンを指し、bump は breaking change として扱う ([productization_notes.md §横断規約](productization_notes.md))。

これにより、commit が参照する `tool_lock_hash` から **どの artifact 群が再現可能か** を一意に決定できます。

---

# 9. Embedding互換性ルール

複数 `.kcs` を横断検索する場合：

```text
dimensions が同じ
distance が同じ
modality が同じ
embedding profile_hash が同じ
```

ならVector横断検索可能。

違う場合：

```text
BM25のみ横断検索
または再index要求
```

---

# 10. `manifest.json`

対象ファイル一覧。

```json
{
  "files": [
    {
      "file_id": "sha256:abc...",
      "path": "docs/report.pdf",
      "raw_hash": "sha256:abc...",
      "kind": "non_text_native",
      "normalized_path": ".kcs/objects/normalized/ab/cd/abc.tool1.md",
      "status": "indexed",
      "last_indexed_at": "2026-04-25T12:00:00Z",
      "tool_profile_hash": "sha256:..."
    }
  ]
}
```

---

# 11. `objects/normalized/`

すべての入力をNormalized Markdownとして保存します。**物理保存は hash ベースの object store に統一**し、原文パスベースの表示は仮想 view として別レイヤーで提供します ([read_only.md §9](read_only.md), [productization_notes.md §5](productization_notes.md))。

```text
internal (正本):
  .kcs/objects/normalized/ab/cd/<raw_hash>.<tool_profile_hash>.md

virtual view (UI 表示用):
  docs/report.pdf.md
  slides/intro.pptx.md
  images/architecture.png.md
```

処理ルール：

```text
Text-native → Normalized Markdownとして保存
Non-text-native → Markdown化 → Normalized Markdownとして保存
```

KCS Coreは **Normalized Markdownだけを扱う**。Markdown 自体の content hash は計算・保存・比較しない (identity は `(raw_hash, tool_profile_hash)`、判定は [hash.md](hash.md) 参照)。

---

# 12. チャンク設計

チャンクは文字数固定ではなく、Markdown見出しベース。

```toml
[chunking]
strategy = "heading"
split_levels = [1, 2, 3]
max_chars = 6000
preserve_blocks = true
```

チャンク例：

```json
{
  "chunk_id": "chk_01H...",
  "raw_path": "docs/report.pdf",
  "normalized_path": ".kcs/objects/normalized/ab/cd/<raw_hash>.<tool_profile_hash>.md",
  "heading_path": ["認証仕様", "API Token", "有効期限"],
  "section_id": "auth/api-token/expiry",
  "char_start": 1200,
  "char_end": 1500,
  "text_hash": "sha256:..."
}
```

---

# 13. `objects/chunks/`

MVPではSQLite内保存でもよいですが、将来公開可能性を考えるならJSONにもできます。

```json
{
  "chunk_id": "chk_01H...",
  "file_id": "sha256:abc...",
  "raw_path": "docs/report.pdf",
  "normalized_path": ".kcs/objects/normalized/ab/cd/<raw_hash>.<tool_profile_hash>.md",
  "heading_path": ["認証仕様", "API Token"],
  "section_id": "auth/api-token",
  "char_start": 880,
  "char_end": 1550,
  "text": "## API Token\n...",
  "summary": null,
  "hash": "sha256:..."
}
```

---

# 14. `objects/nodes/`

知識ノード。
最初から全自動生成せず、検索・利用履歴から動的に昇格。

```json
{
  "node_id": "node_01H...",
  "type": "dynamic_topic",
  "label": "API認証仕様",
  "summary": "API認証に関する仕様変更の知識ノード",
  "status": "dynamic",
  "evidence": [
    {
      "chunk_id": "chk_01H...",
      "weight": 0.91
    }
  ],
  "created_by": "search_cluster",
  "confidence": 0.82,
  "created_at": "2026-04-25T12:10:00Z"
}
```

---

# 15. `objects/edges/`

高信頼・頻出の関係のみ永続化。

```json
{
  "edge_id": "edge_01H...",
  "source": "node_01H...",
  "target": "node_02H...",
  "type": "related_to",
  "origin": "behavioral",
  "confidence": 0.76,
  "evidence": ["chk_01H...", "chk_02H..."]
}
```

---

# 16. `index/`

検索用インデックス。

```text
.kcs/index/
  sqlite.db
  bm25/
  vector/
```

## SQLiteテーブル例

```text
files
normalized_files
chunks
embeddings
nodes
edges
evidence
access_events
kcs_commits
```

---

# 17. `logs/`

## `access.jsonl`

```json
{"ts":"2026-04-25T12:00:00Z","actor":"human","query":"API認証","result_count":8}
{"ts":"2026-04-25T12:01:00Z","actor":"agent","query":"API token rotation","opened_chunk":"chk_01H..."}
```

## `events.jsonl`

```json
{"ts":"2026-04-25T12:00:00Z","event":"index_started"}
{"ts":"2026-04-25T12:10:00Z","event":"node_promoted","node_id":"node_01H..."}
```

---

# 18. `objects/commits/`

KCS独自履歴。

```json
{
  "kcs_commit": "kcs_01H...",
  "parent": "kcs_01G...",
  "git_commit": null,
  "created_at": "2026-04-25T12:30:00Z",
  "message": "index docs update",
  "tool_lock_hash": "sha256:...",
  "stats": {
    "files_added": 3,
    "files_modified": 2,
    "chunks_added": 42,
    "nodes_added": 5
  }
}
```

---

# 19. `refs/`

将来のbranch/tag用。

```text
.kcs/refs/
  heads/
    main
  tags/
    v0.1
```

---

# 20. `.kcsignore`

`.kcs/config.toml` だけでなく、`.kcsignore` も許可すると使いやすいです。

```text
.git/
.kcs/
node_modules/
target/
*.tmp
*.log
```

---

# 21. 公開・共有

`.kcs` 単位で公開可能。

```bash
kcs export
```

オプション：

```bash
kcs export --with-index
kcs export --without-index
kcs export --public
```

公開時に除外：

```text
credentials
cache
tmp
private logs
absolute local paths
```

export は対象フォルダ配下の各 `.kcs` が所有する object を、それぞれの `.kcs` 単位で同梱する。別 `.kcs` の object store への参照を前提にしないため、同一 raw_hash が別 `.kcs` に存在していても export 単位では重複を許容する。

---

# 22. 最終的な責務分離

## `.kcs`

```text
何を対象にするか
何が生成されたか
どの原文に戻れるか
どのTool Profileで作られたか
```

## `~/.config/kcs`

```text
どのコマンド/URL/パスでPrepare・Markdownize・Embedding・Summary・Classification・Rerankを実行するか
各デバイスごとに保持する
共有対象にしない
```

## Device-local Adapter

```text
実際のPrepare・Markdownize（OCRを含む）・Embedding・Summary・Classification・Rerank処理
各デバイスの設定に従う
```

---

# 23. Bootstrap時の最小 `.kcs`

最初はこれだけで実装開始できます。ただし、これは bootstrap 用の最小ディレクトリであり、KCS MVP の受入範囲を縮小するものではありません。

```text
.kcs/
  VERSION
  scope.json
  config.toml
  manifest.json
  tool-lock.json
  normalized/
  index/
    sqlite.db
```

これで以下が可能です。

```text
kcs init
kcs index
kcs search
kcs open
```

`kcs init` は現在フォルダの `.kcs` を作成します。子フォルダの `.kcs` は、`kcs index` や探索処理が ignore されていない対象を見つけた時点で生成します。KCS は各フォルダに `.kcs` を置く設計ですが、空フォルダや未到達フォルダへ先回りして全生成する必要はありません。

---

# 最終結論

`.kcs` は、**各フォルダに隠しディレクトリとして生成され、そのフォルダ直下の知識インデックス・Normalized Markdown・Evidence Pointer・実行時のTool Lockを保持するディレクトリ**です。

外部ツールの実体は持たず、`~/.config/kcs/tools.toml` に定義された任意のコマンド・URL・パスを参照します。

この構造により、

```text
スコープごとの独立性
ツールの自由度
Embedding互換性
Evidence保証
.kcs単位の公開
```

を同時に満たせます。
