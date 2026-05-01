はい、あります。KCSでは **「処理キュー + 状態管理 + ハッシュ検出」** を入れることで、オフライン・API失敗・途中クラッシュ後に、あとから安全に再実行できます。

設計としては、`.kcs` 内に **pending tasks** を持つのが良いです。

```text
.kcs/
  tasks/
    pending.jsonl
    running.jsonl
    failed.jsonl
    done.jsonl
```

またはSQLiteに `tasks` テーブルを作ります。実装上は **SQLite管理がおすすめ**です。

---

## 基本方針

KCSの処理はすべてタスク化します。

```text
Markdown処理（OCRを含む）
Embedding
検索代行Agent
要約Agent
index更新
node生成
```

それぞれを独立した task として記録します。

例：

```json
{
  "task_id": "task_01H...",
  "type": "markdownize",
  "input_path": "docs/report.pdf",
  "input_hash": "sha256:abc...",
  "output_path": ".kcs/normalized/docs/report.pdf.md",
  "status": "pending",
  "attempts": 0,
  "created_at": "2026-04-25T12:00:00Z"
}
```

---

## 状態遷移

```text
pending
  ↓
running
  ↓
done

pending
  ↓
running
  ↓
failed
  ↓
pending（再試行）
```

重要なのは、クラッシュ時に `running` のまま残ったタスクを再検出することです。

---

## オフライン・失敗検出

以下を検出できます。

### 1. Markdown化未完了

```text
raw_hash はある
normalized_path がない
```

→ Markdown化タスクを再作成

---

### 2. Markdown化結果が古い

```text
raw_hash != manifest.raw_hash
```

→ 再Markdown化

---

### 3. Embedding未完了

```text
chunk はある
embedding がない
```

→ Embeddingタスクを再作成

---

### 4. Embedding設定が変わった

```text
current_embedding_profile_hash != stored_profile_hash
```

→ 再Embedding

---

### 5. Index未更新

```text
chunk_hash はある
BM25/vector index に未登録
```

→ index更新

---

### 6. runningのまま停止

```text
status = running
updated_at が一定時間以上古い
```

→ stale task と判定して再実行

---

## コマンド設計

### 状態確認

```bash
kcs status
```

出力例：

```text
KCS status

Files tracked: 320
Markdownized: 290
Pending markdownization: 12
Pending embeddings: 48
Failed tasks: 3
Stale running tasks: 2

Run:
  kcs resume
```

---

### 再開

```bash
kcs resume
```

未完了・失敗・stale task を再実行。

---

### 失敗だけ再試行

```bash
kcs retry
```

---

### キュー確認

```bash
kcs tasks
```

---

### キュー再構築

```bash
kcs repair
```

manifest / normalized / chunks / embeddings / index を照合して、不足タスクを再生成。

---

## SQLiteテーブル案

```sql
CREATE TABLE tasks (
  task_id TEXT PRIMARY KEY,
  task_type TEXT NOT NULL,
  input_path TEXT,
  input_hash TEXT,
  output_path TEXT,
  output_hash TEXT,
  tool_profile_hash TEXT,
  status TEXT NOT NULL,
  attempts INTEGER DEFAULT 0,
  error TEXT,
  created_at TEXT,
  updated_at TEXT,
  started_at TEXT,
  finished_at TEXT
);
```

加えて、依存関係を入れると安全です。

```sql
CREATE TABLE task_dependencies (
  task_id TEXT,
  depends_on TEXT
);
```

例：

```text
embedding task
  depends on chunking task
chunking task
  depends on markdownize task
```

---

## 冪等性が重要

タスクは何度実行しても壊れないようにします。

```text
同じ input_hash + tool_profile_hash
→ 同じ output_path
```

すでに出力がある場合：

```text
output_hashを確認
一致すればdone
違えば再生成
```

これで、途中停止しても安全です。

---

## batch前提との相性

バッチ処理でも、内部的には小さなタスク単位に分けます。

```text
batch job
  ├ markdownize task 1
  ├ markdownize task 2
  ├ embedding task 1
  └ embedding task 2
```

ユーザーから見ると一括実行ですが、KCS内部では再開可能です。

---

## APIエラー時の扱い

APIエラーは種類で分けます。

```text
network_error      → retryable
rate_limit         → retryable later
auth_error         → user action required
quota_exceeded     → retryable after billing/reset
invalid_input      → failed permanent
```

例：

```json
{
  "status": "failed",
  "error_kind": "network_error",
  "retryable": true
}
```

---

## 最終要件文

> KCSでは、Markdown処理（OCRを含む）・Embedding・検索代行Agent・要約Agent・インデックス更新をすべてタスクとして管理する。各タスクには入力ハッシュ、出力ハッシュ、Tool Profile Hash、状態、試行回数を記録する。オフライン・API失敗・プロセス中断が発生した場合でも、`kcs status` で未完了タスクを検出し、`kcs resume` により後から安全に再実行できる。

---

これはかなり重要な要件です。
**KCSはバッチ処理がデフォルト**なので、`resume / retry / repair` はMVP初期から入れる価値があります。
