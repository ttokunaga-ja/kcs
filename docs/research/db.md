以下を **KCSのDB・検索バックエンド要件** として固定するのがよいです。

# KCS DB・検索バックエンド要件

## 1. 基本方針

KCSのローカルMVPでは、常駐DBサーバを必要としない構成を採用する。

標準バックエンドは次とする。

```text
MetadataStore      = SQLite
TextSearchBackend  = SQLite FTS5
VectorSearchBackend = sqlite-vec
ObjectStore        = .kcs/objects
```

KCSでは、原文・Markdown化結果・snapshot object は `.kcs/objects` を正本とし、SQLiteはメタデータ管理・検索・タスク状態管理・高速参照のために使う。

---

## 2. 役割分担

```text
.kcs/objects/
  raw/
  normalized/
  chunks/
  embeddings/
  nodes/
  edges/
  trees/
  commits/

.kcs/index/
  kcs.sqlite
```

役割は以下。

| 層              | 役割                                                           |
| -------------- | ------------------------------------------------------------ |
| `.kcs/objects` | content-addressed object store。原文・Markdown・chunk・snapshotの正本 |
| SQLite         | object metadata、manifest、tasks、evidence、access log、検索状態      |
| FTS5           | Normalized Markdown / chunk の全文検索                            |
| sqlite-vec     | chunk embedding / node embedding のベクトル検索                     |

Embedding object は検索用の派生 artifact であり、正本ではない。欠損・破損・profile 不一致がある場合は再生成または全文検索 fallback により扱う。

SQLite 内の tasks / queue / retry state も正本ではない。DB が失われた場合、KCS は raw object、normalized object、tree / commit object、tool profile から未完了処理を再検出し、検索インデックスとタスクキューを再構築する。正本として守るのは `.kcs/objects` 側の原本由来 object と履歴 object である。

---

## 3. SQLiteを正本にしない

SQLiteはKCSの正本ではない。

正本：

```text
.kcs/objects
```

SQLite：

```text
再構築可能な検索・メタデータ層
```

要件：

```text
SQLiteが破損しても、objects/ と commits/trees から再構築可能であること
```

コマンド例：

```bash
kcs repair --rebuild-db
```

---

## 4. sqlite-vecの位置付け

`sqlite-vec` は、KCS標準のローカルベクトル検索バックエンドとする。

要件：

```text
常駐サーバ不要
SQLiteファイル内またはSQLite管理下でベクトル検索
Embeddingが利用可能な場合はHybrid検索に参加
Embeddingが利用不可の場合は自動で全文検索へfallback
```

---

## 5. 検索モード

KCSの標準検索モードは `auto` とする。

```bash
kcs search "query"
```

`auto` の動作：

```text
1. FTS5全文検索を実行
2. sqlite-vecが利用可能か確認
3. vector indexが存在すればベクトル検索を実行
4. RRF等で統合
5. vectorが利用できなければ全文検索のみ返す
```

明示モード：

```bash
kcs search "query" --text
kcs search "query" --vector
kcs search "query" --hybrid
```

挙動：

| モード      | 動作                                                |
| -------- | ------------------------------------------------- |
| `auto`   | vectorがあればhybrid、なければtext                         |
| `text`   | FTS5のみ                                            |
| `vector` | sqlite-vecのみ。利用不可ならerror                          |
| `hybrid` | FTS5 + sqlite-vec。vector不可時は設定に従いfallbackまたはerror |

---

## 6. fallback要件

以下の場合、デフォルトでは全文検索へfallbackする。

```text
Embedding tool未設定
Embedding tool実行失敗
API key未設定
APIエラー
vector index未作成
sqlite-vec拡張ロード失敗
embedding profile不一致
vector table破損
```

検索結果メタデータには必ず実際の検索モードを含める。

```json
{
  "requested_mode": "auto",
  "resolved_mode": "text",
  "fallback": true,
  "fallback_reason": "vector_index_missing"
}
```

---

## 7. DBファイル配置

各フォルダの `.kcs` ごとにSQLite DBを持つ。

```text
folder/
  .kcs/
    index/
      kcs.sqlite
```

各 `.kcs` は自フォルダ直下のファイルと子 `.kcs` リンクを管理する。

検索時はデフォルトで、

```text
all indexed scopes
```

を対象にする。現在フォルダのみ、現在フォルダと配下のみ、任意フォルダのみなどに絞る場合は、検索コマンド側で明示的に scope を指定する。

つまり、検索実行側がscope registryまたは探索済み `.kcs` 一覧を束ね、対象scopeのSQLite DBを横断検索する。

---

## 8. SQLite schema要件

MVPで必要な主要テーブルは以下。

```sql
files
raw_objects
normalized_objects
chunks
chunk_fts
embeddings
nodes
edges
evidence_pointers
tasks
snapshots
access_events
```

---

## 9. chunksテーブル

```sql
CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY,
  raw_hash TEXT NOT NULL,
  tool_profile_hash TEXT NOT NULL,
  raw_path TEXT NOT NULL,
  normalized_path TEXT NOT NULL,
  heading_path TEXT,
  section_id TEXT,
  char_start INTEGER,
  char_end INTEGER,
  text_hash TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- 注: chunk が属する Markdown 全体の content hash (normalized_hash) は持たない。
-- chunk の identity は (raw_hash, tool_profile_hash, heading_path/section_id, char_start, char_end)
-- から導かれる。`text_hash` は chunk の抽出範囲のテキストに対する hash であり、
-- Markdown 全体の hash ではない。
```

---

## 10. FTS5テーブル

全文検索用。

```sql
CREATE VIRTUAL TABLE chunk_fts USING fts5(
  chunk_id UNINDEXED,
  text,
  heading_path,
  content='chunks',
  content_rowid='rowid'
);
```

### MVP での FTS5 構成方針

MVP では **外部 content モード (`content='chunks'`) を採用** します。理由:

```text
1. chunks テーブルとの整合を SQLite の trigger で自動保守できる
   (DELETE / INSERT / UPDATE on chunks → chunk_fts も同期)
2. text を二重保存せずディスク使用量を抑えられる
3. データ不整合 (chunks にあって chunk_fts に無い、逆も) を構造的に防げる
   = MVP done-criteria の「最小完全系」(productization_notes.md §1) を満たす
```

過去に「`content_rowid` が面倒なら外部contentなしでもよい」と書いていたが、整合性保証のため **MVP から外部 content モードを採用** に方針を変える。`content_rowid='rowid'` を使い、chunks の rowid を chunk_fts と共有する。

trigger の例:

```sql
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunk_fts(rowid, chunk_id, text, heading_path)
    VALUES (new.rowid, new.chunk_id, new.text, new.heading_path);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunk_fts(chunk_fts, rowid, chunk_id, text, heading_path)
    VALUES('delete', old.rowid, old.chunk_id, old.text, old.heading_path);
END;
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunk_fts(chunk_fts, rowid, chunk_id, text, heading_path)
    VALUES('delete', old.rowid, old.chunk_id, old.text, old.heading_path);
  INSERT INTO chunk_fts(rowid, chunk_id, text, heading_path)
    VALUES (new.rowid, new.chunk_id, new.text, new.heading_path);
END;
```

### CJK tokenizer

FTS5 デフォルトの `unicode61` は日本語/中国語/韓国語で適切に動かないため、tokenizer は以下を採用する。

```text
日本語/CJK: tokenize="trigram" (または ICU tokenizer がビルド済みなら ICU)
英文中心の用途のみ: tokenize="unicode61 remove_diacritics 2"
```

config (`.kcs/config.toml` の `[search.fts]`) で切替可能とし、デフォルトは `trigram` (CJK 対応のため)。

---

## 11. Embedding / sqlite-vecテーブル

KCSでは Text Embedding Adapter と Image Embedding Adapter を分けず、単一のマルチモーダル Embedding Adapter を使う。概念上の metadata table は1つに統一する。

```sql
CREATE TABLE embeddings (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL, -- chunk | image | node | query_cache
  target_id TEXT NOT NULL,
  modality TEXT NOT NULL,    -- text | image | multimodal
  vector BLOB NOT NULL,
  dimensions INTEGER NOT NULL,
  distance TEXT NOT NULL,
  profile_hash TEXT NOT NULL
);
```

sqlite-vec用のvector tableは、実装都合で分けてもよい。

```sql
CREATE VIRTUAL TABLE chunk_vec USING vec0(
  chunk_id TEXT PRIMARY KEY,
  embedding FLOAT[DIM]
);

CREATE VIRTUAL TABLE image_vec USING vec0(
  image_id TEXT PRIMARY KEY,
  embedding FLOAT[DIM]
);
```

ただし概念上は次を満たす。

```text
same Embedding Adapter
same profile_hash
same vector space
```

---

## 12. embedding profile

Embedding互換性を判定するため、必ず保存する。

```json
{
  "embedding": {
    "enabled": true,
    "tool_id": "gemini_multimodal_embedding",
    "dimensions": 1536,
    "distance": "cosine",
    "modality": "multimodal",
    "profile_hash": "sha256:..."
  }
}
```

互換条件：

```text
dimensions一致
distance一致
modality一致
profile_hash一致
```

一致しない場合、子孫 `.kcs` であっても vector横断検索には参加させない。
その `.kcs` は全文検索のみ参加する。

---

## 13. Hybrid fusion

KCSの標準fusionはRRFとする。

```text
RRF(text_rank, vector_rank)
```

要件：

```text
FTS5とsqlite-vecのスコアスケールを直接比較しない
順位ベースで統合する
vectorがない場合はFTS5順位をそのまま使う
```

---

## 14. `.kcs` 横断検索

デフォルト検索では、KCSが認識している全 indexed scope の `.kcs` を横断する。

初回の indexed scope は、ユーザーが `.kcsignore` や設定で明示的に除外していないすべての対象範囲とする。

```text
A/.kcs
A/B/.kcs
A/B/C/.kcs
Work/.kcs
Downloads/.kcs
```

検索実行：

```text
対象scopeの各.kcsのSQLiteでFTS5検索
embedding profileが一致する.kcsのみsqlite-vec検索
結果をscope単位で集約
最終的にRRFまたはscore fusion
```

レスポンスには検索対象scopeと、scope指定や権限により除外されたscopeを含める。

```json
{
  "searched_scopes": [
    "A/.kcs",
    "A/B/.kcs",
    "A/B/C/.kcs"
  ],
  "excluded_scopes": [
    {
      "path": "A/D/.kcs",
      "reason": "embedding_profile_mismatch_for_vector"
    }
  ]
}
```

※ profile mismatchでも全文検索は可能なので、完全除外ではなく「vectorのみ除外」が基本。

---

## 15. バッチ処理との関係

Prepare・Markdownize（OCRを含む）・Embeddingはデフォルトでバッチ。

Embedding処理後にsqlite-vecへupsertする。

```text
kcs index
  ↓
Prepare batch
  ↓
Markdownize batch
  ↓
chunking
  ↓
Embedding batch
  ↓
FTS5 update
  ↓
sqlite-vec update
```

リアルタイムは明示時のみ。

```bash
kcs index --realtime
```

---

## 16. task管理

Embedding失敗時も復旧可能にする。

```sql
CREATE TABLE tasks (
  task_id TEXT PRIMARY KEY,
  task_type TEXT NOT NULL,
  target_id TEXT,
  input_hash TEXT,
  tool_profile_hash TEXT,
  status TEXT NOT NULL,
  attempts INTEGER DEFAULT 0,
  error TEXT,
  created_at TEXT,
  updated_at TEXT
);
```

`embedding` task が未完了の場合、そのchunkは全文検索のみ対象。

---

## 17. status表示

`kcs status` は検索バックエンド状態を表示する。

```text
KCS status

Text index:
  FTS5 ready
  indexed chunks: 1240

Vector index:
  sqlite-vec ready
  embedded chunks: 1180
  pending embeddings: 60
  profile: sha256:...

Search mode:
  default: auto
  resolved: hybrid
```

sqlite-vecが使えない場合：

```text
Vector index:
  unavailable
  reason: sqlite-vec extension not loaded

Search mode:
  default: auto
  resolved: text fallback
```

---

## 18. config要件

`.kcs/config.toml`

```toml
[search]
default_mode = "auto"
fusion = "rrf"
fallback = "text"

[text_search]
enabled = true
backend = "fts5"

[vector_search]
enabled = true
backend = "sqlite-vec"
optional = true
fail_behavior = "fallback"
```

グローバル設定側では単一のマルチモーダル Embedding toolを定義。

```toml
[tools.gemini_multimodal_embedding]
kind = "http"
url = "https://example.invalid/embedding"
method = "POST"
```

---

## 19. sqlite-vecが使えない環境

sqlite-vecがビルド・ロードできない環境でもKCSは動作する必要がある。

要件：

```text
sqlite-vec unavailableでもkcs init/index/searchは動く
ただしvector検索はdisabled
全文検索へfallback
```

---

## 20. 将来拡張

VectorSearchBackendは抽象化しておく。

標準：

```text
sqlite-vec
```

将来候補：

```text
libSQL/Turso vector
LanceDB
Qdrant
PostgreSQL + pgvector
```

ただしMVPではsqlite-vecのみ実装でよい。

---

# 最終要件文

> KCSのローカルMVPでは、常駐DBサーバを必要としないSQLite系バックエンドを採用する。メタデータ管理にはSQLite、全文検索にはSQLite FTS5、ベクトル検索にはsqlite-vecを標準で使用する。KCSの標準検索は `auto` とし、sqlite-vecによるベクトル検索が利用可能な場合は全文検索と統合したHybrid検索を行い、利用できない場合は自動的に全文検索へフォールバックする。原文・Markdown化結果・snapshot objectは `.kcs/objects` に保存し、SQLiteは再構築可能な検索・状態管理層として扱う。
