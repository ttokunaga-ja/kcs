# 04 Pipeline

統合元: `diff.md` (units / 差分判定) + `db.md` (SQLite schema / 検索バックエンド) + `batch.md` (タスク実行 / retry / budget)。

---

# 1. パイプライン全体

```
working tree
   │ ingest
   ▼
raw object        (CAS, raw_hash 単位)
   │ prepare (Adapter, 任意)
   ▼
prepared object   (page image, sheet 等の中間表現)
   │ markdownize (Adapter, full または incremental)
   ▼
normalized        (read-only artifact, content hash 不採用)
   │ chunking
   ▼
chunk             (CAS, chunk_hash 単位)
   │ embedding (Adapter)
   ▼
embedding         (CAS)
   │ indexing
   ▼
SQLite (FTS5 + sqlite-vec, query acceleration)
```

各ステージは [batch.md タスク](#5-バッチ実行) として記録される。`task state` は喪失を許容する運用データで、失われても object store と tool profile から未完了作業を再検出できる。

# 2. Prepared Units と差分判定

ファイル全体ではなく **unit 単位** で Markdownize する。これにより差分更新と decoded 単位の局所一貫性を両立する。

```
ファイル種別   | unit
PDF           | page
PPTX          | slide
DOCX          | heading section / page (page hash がデバイス間で安定しないので heading 優先)
XLSX          | sheet
画像          | image
Markdown      | heading section
code          | file / symbol
```

```
.kcs/objects/prepared_units/
  page_001.json
  page_002.json
.kcs/objects/normalized_units/
  unit_<unit_id>.json
```

unit object:

```json
{
  "unit_id": "unit_...",
  "raw_hash": "sha256:...",
  "prepared_hash": "sha256:...",
  "unit_type": "page",
  "unit_key": "page:12",
  "markdown": "## 3.2 認証仕様\n...",
  "tool_profile_hash": "sha256:..."
}
```

normalized 全文 (`report.pdf.md`) は **生成物 (view)** で、unit を結合して組み立てる。正本は unit object 群。

## 2.1 page fingerprint と再利用判定

差分判定は **raw 側 + tool_profile_hash** で完結し、Markdown content hash は使わない (Adapter の非決定性ゆえ)。

unit が「変わったか」の判定:

```
prepared_hash が変わった
  または
raw_hash が変わり、unit に対応する page_fingerprint が変わった
  または
tool_profile_hash が変わった
```

これらが変わらなければ **既存 Markdown unit をそのまま再利用** (= LLM 再呼び出し不要)。

page fingerprint は `(perceptual hash, text hash, visual hash)` の三つ組。一致時は再 Markdownize 不要を契約として明記する。

## 2.2 Diff 種別

```
Raw Diff       原文の差分 (raw_hash / page_fingerprint 変化)
Unit Diff      unit 単位の追加・削除・変更
Semantic Diff  chunk 単位の意味的差分 (Phase 4+ で使用、optional)
```

# 3. Markdownize

raw / prepared → normalized。LLM ベース Adapter が中心 (Gemini / Claude / GPT)。Adapter contract は [07-adapter-spec.md](#) (将来分離予定) を参照。

## 3.1 Incremental Markdownize (要件)

ファイル更新時、Adapter に **新 raw + 旧 raw + 旧 Markdown + 変更ヒント** をセットで渡し、軽微な変更なら Adapter が部分更新を返す。

**発動条件 (AND 5 つ)**:

```
1. 同一 file_id に対する既存 done normalization_run がある
2. raw_hash のみ変化 (tool_profile_hash は不変)
3. Adapter が capabilities = ["incremental_update"] を宣言
4. page fingerprint 変化率 < threshold (default 0.30)
5. 直前 N 回 (default 5) 連続 incremental の場合は full を強制 (style drift 防止)
```

いずれかが満たされなければ自動 fallback to full。

**Adapter 入力契約**:

```json
{
  "mode": "incremental",
  "new_raw":  { "path": "...", "raw_hash": "sha256:..." },
  "previous": {
    "raw":               { "path": "...", "raw_hash": "sha256:..." },
    "normalized_units":  [...],
    "tool_profile_hash": "sha256:..."
  },
  "hints": {
    "changed_unit_keys":  ["page:12", "page:13"],
    "added_unit_keys":    ["page:57"],
    "removed_unit_keys":  [],
    "page_fingerprints":  {...}
  },
  "tool_profile_hash":   "sha256:...",
  "spec_version":        1
}
```

**Adapter 出力契約**:

```json
{
  "mode_used":           "incremental" | "full",
  "updated_units":       [...],
  "unchanged_unit_keys": [...],
  "added_units":         [...],
  "removed_unit_keys":   [...],
  "fallback_to_full":    false,
  "reason":              null | "..."
}
```

Adapter 側に「軽微とは言えない」拒否権あり (`fallback_to_full=true`)。

**identity 不変性**: incremental/full で出力が異なっても identity は `(raw_hash, tool_profile_hash)` のまま。`tool_profile_hash` 計算入力に incremental flag は含めない。

# 4. SQLite Schema (Query Acceleration Layer)

`.kcs/index/sqlite.db`。**真実は objects/、SQLite は再構築可能** (`kcs repair --rebuild-db`)。

## 4.1 chunks

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
```

chunk が属する Markdown 全体の content hash (normalized_hash) は持たない。identity は `(raw_hash, tool_profile_hash, heading_path/section_id, span)` から導かれる。

## 4.2 chunk_fts (FTS5 外部 content)

MVP から **外部 content モード** を採用 (整合性保証のため):

```sql
CREATE VIRTUAL TABLE chunk_fts USING fts5(
  chunk_id UNINDEXED,
  text,
  heading_path,
  content='chunks',
  content_rowid='rowid'
);
```

trigger で chunks との同期を自動保守:

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

**Tokenizer**: デフォルト `trigram` (CJK 対応)。英文中心の場合のみ `unicode61 remove_diacritics 2` を選択可。`.kcs/config.toml [search.fts]` で切替。

## 4.3 embeddings (sqlite-vec + metadata)

```sql
CREATE TABLE embeddings (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,    -- chunk | image | node | query_cache
  target_id TEXT NOT NULL,
  modality TEXT NOT NULL,       -- text | image | multimodal
  vector BLOB NOT NULL,
  dimensions INTEGER NOT NULL,
  distance TEXT NOT NULL,
  profile_hash TEXT NOT NULL
);

CREATE VIRTUAL TABLE chunk_vec USING vec0(
  chunk_id TEXT PRIMARY KEY,
  embedding FLOAT[<dim>]
);
```

KCS は Text/Image を分けず **単一マルチモーダル Embedding Adapter** を使う前提。

## 4.4 normalization_runs / tasks / snapshots / nodes / edges / evidence_pointers / access_events

詳細は [03-data-model.md §8](03-data-model.md)。

# 5. バッチ実行 (Batch / Retry / Budget)

すべての非同期処理 (Prepare / Markdownize / Embedding / Summary / Classification / Rerank / index / node 生成) は **task** として記録する。

## 5.1 タスクモデル

```json
{
  "task_id": "task_01H...",
  "type": "markdownize",
  "mode": "full",                       // or "incremental"
  "input_path": "docs/report.pdf",
  "input_hash": "sha256:abc...",
  "previous_raw_hash": "sha256:old...", // incremental 時
  "parent_run_id": "run_01H...",        // incremental 時
  "changed_unit_keys": ["page:12"],     // incremental 時
  "output_path": ".kcs/objects/normalized/ab/cd/abc.tool1.md",
  "status": "pending",
  "attempts": 0,
  "next_retry_at": null,
  "deadline": "2026-05-02T23:59:59Z",
  "heartbeat_at": null,
  "fallback_reason": null,
  "created_at": "2026-04-25T12:00:00Z"
}
```

## 5.2 状態遷移

```
pending → running → done
pending → running → failed → pending (retryable)
running が heartbeat_at + 5min を超えたら stale。別 worker が pull 可能
```

`task` テーブルが消えても問題ない設計 (object store と tool profile から再検出可能)。ただし `attempts` 履歴は失われる (リトライ予算がリセットされる) 点を許容。

## 5.3 エラー種別と Retry Budget

```
network_error      retryable             max_attempts=5,  exp(base=2s, cap=60s), jitter=full
                                         KCS-E-BATCH-NET-001
rate_limit         retryable later       max_attempts=∞,  honor "Retry-After" header
                                         KCS-E-BATCH-RATE-001
auth_error         user action required  max_attempts=0
                                         KCS-E-BATCH-AUTH-001
quota_exceeded     retryable             max_attempts=3,  fixed(1h)
                                         KCS-E-BATCH-QUOTA-001
invalid_input      failed permanent      max_attempts=0
                                         KCS-E-BATCH-INPUT-001
budget_exceeded    paused                KCS-E-BATCH-BUDGET-001
```

エラーコード namespace は [productization_notes.md §12.1](productization_notes.md)。

## 5.4 Cost Guardrail / Kill Switch

将来 LLM コスト低下を前提とするが、移行期の暴走防止のため **MVP から budget guardrail を入れる**。

```toml
[budget]
monthly_usd_cap = 50.0
warn_at_percent = 80
hard_stop = true
[budget.per_adapter]
markdown = 30.0
embedding = 15.0
summary = 5.0
```

- 累積コストは Adapter 報告値 (input/output token × 単価) を `~/.local/share/kcs/cost-ledger.sqlite` に記録
- cap 超過時、走行中タスクは完了させ、新規タスクは `paused` 状態へ。`kcs status` に `budget exceeded` 表示
- `kcs batch resume --override-budget` で明示的に再開可能
- ローカル LLM 利用時は単価 0 として記録 (= cap に効かない)

## 5.5 冪等性

`(input_hash, tool_profile_hash) → output_path` 一致なら done として短絡 (キャッシュヒット)。これは **first-instance-wins** ([03-data-model.md §6](03-data-model.md), [09-mvp-scope.md §設計宿題](09-mvp-scope.md))。LLM API の二重課金を防ぐため、Adapter 層に idempotency_key を要求する。

## 5.6 CLI exit code (batch 系)

横断規約 ([productization_notes.md §12.2](productization_notes.md)) に従う:

```
0  全タスク success または all up_to_date
1  汎用 failure
2  invalid usage / config 不正
3  一部タスク failed (retryable 残あり)
4  全タスク failed permanent
5  auth_error がある
6  budget_exceeded により paused
7  user 中断 (SIGINT/SIGTERM)
```

## 5.7 Resume と Repair

- `kcs batch resume`: 中断状態 (running stale, pending) を再開
- `kcs repair --rebuild-db`: SQLite を objects/ から再構築。喪失耐性

# 6. 検索バックエンド方針

```
text  : FTS5 (外部 content + trigram tokenizer)         デフォルト
vector: sqlite-vec                                      デフォルト
hybrid: RRF + MMR (詳細は 05-runtime.md §1)
```

将来候補 (Phase 4+):

```
Tantivy           large-scale BM25
LanceDB / Qdrant  large-scale vector
```

MVP では single SQLite に集約。`.kcs` 単位の export/restore/portability を優先。
