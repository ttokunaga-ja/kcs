はい。ここは **KCSの信頼性の核心**です。
「Markdownが最新かどうか」は Markdown の中身だけでは判断できないので、**原文ファイルの状態とMarkdown化実行記録を対応付ける台帳**が必須です。

結論は次です。

> **KCSは、各原文ファイルについて `raw_hash + tool_profile_hash + output_hash + status` を保存し、現在の原文ハッシュと実行済み記録を照合して、Markdown化済みかどうかを判定する。**

---

# 1. なぜMarkdownだけでは判定できないか

Markdown化後のファイルだけ見ても、

```text
このMarkdownがどの原文から作られたか
どの時点の原文から作られたか
どのMarkdown化ツールで作られたか
途中失敗したものではないか
```

が分かりません。

したがって、判定対象はMarkdownではなく、**原文ファイルとMarkdown化実行記録の対応**です。

---

# 2. 必須となる台帳

`.kcs` には以下を持つべきです。

```text
manifest
normalization_runs
tasks
```

MVPではSQLiteで管理するのがよいです。

---

# 3. ファイル単位の状態管理

## `files` テーブル

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

`raw_hash` は必須です。
mtimeだけでは不十分です。

---

## `normalization_runs` テーブル

```sql
CREATE TABLE normalization_runs (
  run_id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL,
  path TEXT NOT NULL,
  raw_hash TEXT NOT NULL,
  tool_profile_hash TEXT NOT NULL,
  normalized_path TEXT NOT NULL,
  normalized_hash TEXT,
  status TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT
);
```

ここで重要なのは、

```text
raw_hash
tool_profile_hash
status
```

です。

---

# 4. Markdown化済み判定の条件

あるファイルがMarkdown化済みと判定される条件はこれです。

```text
現在の raw_hash と一致する normalization_run が存在する
かつ
tool_profile_hash が現在の設定と一致する
かつ
status = done
かつ
normalized_path が存在する
かつ
normalized_hash が一致する
```

擬似コード：

```text
current_raw_hash = hash(file)

run = find normalization_run
  where path = file.path
  and raw_hash = current_raw_hash
  and tool_profile_hash = current_tool_profile_hash
  and status = done

if run exists and file_exists(run.normalized_path):
    normalized_hash = hash(run.normalized_path)
    if normalized_hash == run.normalized_hash:
        up_to_date
    else:
        stale_or_corrupted
else:
    pending
```

---

# 5. 状態分類

KCSはファイルごとに状態を分類します。

```text
new
up_to_date
modified
tool_changed
missing_output
failed
corrupted
pending
```

## 意味

```text
new:
  初めて見つかった原文

modified:
  pathは同じだがraw_hashが変わった

tool_changed:
  raw_hashは同じだがtool_profile_hashが変わった

missing_output:
  done記録はあるがnormalized_pathがない

corrupted:
  normalized_hashが記録と一致しない

failed:
  前回Markdown化に失敗

pending:
  実行待ち
```

---

# 6. `kcs status` の出力例

```text
KCS status

Markdownization:
  up to date: 284
  new: 12
  modified: 5
  tool changed: 0
  failed: 2
  missing output: 1
  corrupted: 0

Run:
  kcs normalize
```

これがあれば、確実に「何が未実行か」が分かります。

---

# 7. 新規ファイル検出

新規ファイル検出は、

```text
現在のスコープ内ファイル一覧
-
manifestに登録済みファイル一覧
```

です。

ただしpathだけでなくhashも見ます。

```text
path未登録 → new
path登録済み + hash変更 → modified
path登録済み + hash同一 → unchanged
```

さらに、ファイル移動にも対応したい場合：

```text
hash同一 + path変更 → moved
```

---

# 8. Markdown化タスク生成ルール

以下の場合はMarkdown化タスクを生成します。

```text
new
modified
tool_changed
missing_output
corrupted
failed retryable
```

生成しない：

```text
up_to_date
ignored
```

---

# 9. tool_profile_hash が必要な理由

同じ原文でも、

```text
Markdown化プロンプトが変わった
Markdown化コマンドが変わった
モデルが変わった
設定が変わった
```

場合、出力Markdownは変わる可能性があります。

だから、`raw_hash` だけでは不十分です。

必要：

```text
markdownized version = raw_hash + tool_profile_hash
```

---

# 10. normalized_path の命名

path依存にするとファイル移動で壊れやすいので、内部保存はhashベースが安全です。

推奨：

```text
.kcs/normalized/ab/cd/<raw_hash>.<tool_hash>.md
```

例：

```text
.kcs/normalized/ab/cd/abcdef1234.tool9876.md
```

ただし、人間が見やすい別名として元パスもDBに保存します。

---

# 11. manifest.json に書くなら

JSONだけで管理するならこうです。

```json
{
  "files": [
    {
      "path": "docs/report.pdf",
      "file_id": "sha256:abc",
      "raw_hash": "sha256:abc",
      "kind": "non_text_native",
      "normalization": {
        "status": "done",
        "tool_profile_hash": "sha256:tool",
        "normalized_path": ".kcs/normalized/ab/cd/abc.tool.md",
        "normalized_hash": "sha256:norm",
        "finished_at": "2026-04-25T12:00:00Z"
      }
    }
  ]
}
```

ただし、ファイル数が増えるならSQLite推奨です。

---

# 12. 重要な最終ルール

KCSでは、Markdown化済み判定をこの条件に固定します。

```text
Up-to-date Markdown =
  current raw_hash
  + current markdownize tool_profile_hash
  + done normalization record
  + existing normalized file
  + matching normalized_hash
```

これ以外は未実行または再実行対象です。

---

# 13. 要件文

設計書にはこう書くと良いです。

> KCSでは、Markdown化結果が最新かどうかをMarkdownファイル単体から判断しない。各原文ファイルについて、現在の原文ハッシュ、Markdown化Tool Profile Hash、Markdown化実行状態、出力Markdownハッシュを台帳として保存し、それらの一致によってのみMarkdown化済みと判定する。これにより、新規ファイル・更新ファイル・ツール変更・出力欠損・途中失敗を確実に検出し、後から安全に再実行できるようにする。

---

この仕様はMVP初期から入れるべきです。
これがないと、KCSは「どのファイルが本当に検索可能か」を保証できません。
