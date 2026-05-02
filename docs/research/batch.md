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

ただし task state は KCS の正本ではありません。途中失敗や未完了タスクの記録は失われてもよく、失われた場合は raw object、normalized object、tree / commit object、現在の tool profile から未完了作業を再検出してキューを再構築します。優先して守る対象は原本 PDF などに由来する raw object と履歴・証拠であり、task state は検索効率と再開性のための運用データです。

---

## 基本方針

KCSの処理はすべてタスク化します。

```text
Prepare
Markdownize（OCRを含む）
Embedding
Summary
Classification
Rerank
index更新
node生成
```

それぞれを独立した task として記録します。

例：

```json
{
  "task_id": "task_01H...",
  "type": "markdownize",
  "mode": "full",
  "input_path": "docs/report.pdf",
  "input_hash": "sha256:abc...",
  "output_path": ".kcs/objects/normalized/ab/cd/abc.tool1.md",
  "status": "pending",
  "attempts": 0,
  "created_at": "2026-04-25T12:00:00Z"
}
```

`type=markdownize` は `mode` フィールドを持ち、`full` (新規 / フォールバック) と `incremental` (差分更新、要件の詳細は [diff.md §6.1](diff.md)) を区別する。

incremental task の例:

```json
{
  "task_id": "task_01H...",
  "type": "markdownize",
  "mode": "incremental",
  "input_path": "docs/report.pdf",
  "input_hash": "sha256:newraw...",
  "previous_raw_hash": "sha256:oldraw...",
  "parent_run_id": "run_01H...",
  "changed_unit_keys": ["page:12", "page:13"],
  "output_path": ".kcs/objects/normalized/ab/cd/newraw.tool1.md",
  "status": "pending",
  "attempts": 0,
  "created_at": "2026-05-02T12:00:00Z"
}
```

incremental の発動条件・閾値・Adapter capability 要件は [diff.md §6.1](diff.md) を参照。条件を満たさない / Adapter が `incremental_update` capability を持たない / Adapter が `fallback_to_full` を返した場合は、自動で `mode=full` の新タスクを生成して再試行する。フォールバック理由は task 行の `fallback_reason` に記録する。

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

APIエラーは種類で分けます。エラーコードは横断 namespace ([productization_notes.md §横断規約](productization_notes.md)) に従い `KCS-E-BATCH-*` のかたちで一意化します。

```text
network_error      → retryable    (KCS-E-BATCH-NET-001)
rate_limit         → retryable later (KCS-E-BATCH-RATE-001)
auth_error         → user action required (KCS-E-BATCH-AUTH-001)
quota_exceeded     → retryable after billing/reset (KCS-E-BATCH-QUOTA-001)
invalid_input      → failed permanent (KCS-E-BATCH-INPUT-001)
budget_exceeded    → paused (KCS-E-BATCH-BUDGET-001)
```

例：

```json
{
  "status": "failed",
  "error_kind": "network_error",
  "error_code": "KCS-E-BATCH-NET-001",
  "retryable": true,
  "attempts": 2,
  "next_retry_at": "2026-04-25T12:05:00Z"
}
```

---

## Retry budget と backoff

リトライは無制限ではなく、エラー種別ごとに以下の予算を設けます。

```text
network_error:      max_attempts=5,  backoff="exp(base=2s, cap=60s)", jitter="full"
rate_limit:         max_attempts=∞,  honor "Retry-After" header. ヘッダ無ければ exp(base=10s, cap=300s)
quota_exceeded:     max_attempts=3,  backoff="fixed(1h)" (billing/reset を待つ)
auth_error:         max_attempts=0   (user action 待ち)
invalid_input:      max_attempts=0   (permanent failure)
```

- `next_retry_at` はタスク行に保持し、worker は `now() >= next_retry_at` のものだけ pull する。
- 各タスクには `deadline` (絶対時刻) を持たせ、超過時は `failed (deadline_exceeded)` で確定。
- `running` 状態が `heartbeat_at + 5min` を超えたら `stale` 扱い。別 worker が pull 可能。

## Cost guardrail / kill switch

将来 LLM コスト低下を前提とする ([productization_notes.md §横断規約](productization_notes.md)) ものの、移行期の暴走を防ぐため **MVP から budget guardrail を入れます**。

```toml
# .kcs/config.toml または ~/.config/kcs/config.toml
[budget]
monthly_usd_cap = 50.0          # 上限。超過で全 batch を pause
warn_at_percent = 80            # 80% で warn
hard_stop = true                # true: cap で全 task を paused に遷移
[budget.per_adapter]
markdown = 30.0
embedding = 15.0
summary = 5.0
```

- 累積コストは Adapter 報告値 (input/output token × 単価) を `~/.local/share/kcs/cost-ledger.sqlite` に記録。
- `monthly_usd_cap` 超過時、走行中タスクは完了させ、新規タスクは `paused` 状態へ。`kcs status` に `budget exceeded` と表示。
- `kcs batch resume --override-budget` で明示的に再開可能。
- ローカル LLM 利用時は単価 0 として記録 (= cap に効かない)。

---

## CLI exit code

`kcs batch` 系コマンドの exit code は横断規約 ([productization_notes.md §横断規約](productization_notes.md)) に従い、以下を返します。

```text
0   全タスク success または all up_to_date
1   汎用 failure (詳細不明)
2   invalid usage / config 不正
3   一部タスク failed (retryable 残あり)
4   全タスク failed permanent
5   auth_error がある (user action 必要)
6   budget_exceeded により paused
7   user による中断 (SIGINT/SIGTERM)
```

スクリプト連携 (`kcs batch run && kcs index`) はこれらを参照します。

---

## 最終要件文

> KCSでは、Prepare・Markdownize（OCRを含む）・Embedding・Summary・Classification・Rerank・インデックス更新をすべてタスクとして管理する。各タスクには入力ハッシュ、出力ハッシュ、Tool Profile Hash、状態、試行回数を記録する。task state は正本ではなく喪失を許容する運用データであり、失われた場合は object store と tool profile から未完了作業を再検出する。オフライン・API失敗・プロセス中断が発生した場合でも、`kcs status` で未完了タスクを検出し、`kcs resume` により後から安全に再実行できる。

---

これはかなり重要な要件です。
**KCSはバッチ処理がデフォルト**なので、`resume / retry / repair` はMVP初期から入れる価値があります。
