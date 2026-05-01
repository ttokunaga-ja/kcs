はい。ここは **KCSの信頼性の核心**です。
「Markdownが最新かどうか」は Markdown の中身だけでは判断できないので、**原文ファイルの状態とMarkdown化実行記録を対応付ける台帳**が必須です。

結論は次です。

> **KCSは、各原文ファイルについて `raw_hash + tool_profile_hash + status` を保存し、現在の原文ハッシュと実行済み記録を照合して、Markdown化済みかどうかを判定する。Markdown 等の派生 artifact については content hash を取らず、`(raw_hash, tool_profile_hash)` を identity として扱う。**

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
  status TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT
);

-- 注: 正規化された Markdown は read-only artifact として扱い、content hash
-- (normalized_hash 等) は計算・保存しない。identity は (raw_hash, tool_profile_hash)
-- で一意に決まり、物理パスは `<raw_hash>.<tool_hash>.md` 形式で表現される。
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
normalized_path のファイルが存在する
```

Markdown 側の content hash は判定条件に含めません。Markdownize Adapter は LLM ベースで非決定的なため、同じ raw + 同じ profile でも生成のたびに content hash が変わりえます。content hash 一致を up-to-date 条件にすると常に再生成が走るため、判定は `(raw_hash, tool_profile_hash, status=done, ファイル存在)` のみに閉じます。

擬似コード：

```text
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
  done記録はあるがnormalized_pathのファイルが見当たらない

failed:
  前回Markdown化に失敗

pending:
  実行待ち
```

注: `corrupted` (Markdown 側 content hash 不一致による破損検出) は採用しない。Markdown は read-only artifact として扱い、content hash を持たないため。ファイル消失は `missing_output` で検出する。

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

## 9.1 tool_profile_hash の計算規約

normalized_hash を採用しない結果、artifact identity は `(raw_hash, tool_profile_hash)` 単独に依存します。したがって `tool_profile_hash` の計算規約はプロダクトの再現性・互換性の根拠となるため、以下を契約として固定します。

### ハッシュ対象フィールド (capability hash)

決定性に影響する情報のみを含めます。**実行可能情報** (`cmd`, `args`, `url`, 認証情報) は kcs.md §4 の方針どおり含めません (共有 `.kcs` から外部実行されないため)。

```text
adapter_kind          # "markdownize" | "embedding" | "ocr" | ...
adapter_role          # "text" | "image" | "multimodal" | ...
model_or_tool_family  # "gemini-2.5-pro" | "gpt-4o" | "tesseract" 等の正規化名
model_version_pin     # ベンダー側 immutable tag。可変 alias (latest 等) は禁止
prompt_template_id    # KCS が管理する prompt 識別子 (内容ではなく id)
prompt_template_hash  # prompt 本文を canonical 化した上で sha256
sampling              # {temperature, top_p, top_k, max_tokens, seed} を canonical
output_schema         # 期待する Markdown / JSON schema id とそのバージョン
dimensions            # embedding 専用。次元数
distance              # embedding 専用。"cosine" | "l2" | "dot"
modality              # embedding 専用。"text" | "image" | "multimodal"
runtime_kind          # "cloud" | "local". バイナリ依存ではなく capability レベル
spec_version          # この計算規約自体のバージョン。後述
```

実装バイナリのバージョン (`adapter_binary_version`, OS, ハードウェア等) は `binary_hash` として **別途** 保存し、`tool_profile_hash` には含めません。これにより、Adapter のマイナー bug fix や CLI 配布形態の差では `tool_profile_hash` が変わらず、不要な全 re-index を回避します (詳細: [productization_notes.md §横断規約](productization_notes.md))。

### canonicalization

JSON を hash 入力に使う場合は **RFC 8785 (JSON Canonicalization Scheme, JCS)** に準拠します。

```text
1. キーを Unicode コードポイント順にソート
2. 配列は出現順保持
3. 文字列は NFC 正規化、escape は最小限
4. 数値は IEEE 754 double-precision の最短表現
5. null は "null" リテラル、boolean は true/false
6. 不要な空白なし
```

null フィールドは hash 入力に含めません (省略と null を区別しない)。これは「設定に明示的に書いた null」と「未設定」を識別しないという契約上の約束です。

### prompt_template_hash の計算

```text
1. trim trailing whitespace per line
2. normalize line endings to \n
3. NFC 正規化
4. 末尾の空行を削除
5. sha256 を取り、"sha256:" プレフィックスを付ける
```

### 算出式

```text
tool_profile_hash =
  "sha256:" + base16(
    sha256( JCS(canonicalize(profile_fields)) )
  )

where profile_fields = 上記フィールド集合 (null は除外)
```

### spec_version と互換性

`spec_version` を hash 入力に含めることで、計算規約自体が変わった場合に旧 hash と新 hash を識別できるようにします。`spec_version` の bump は **breaking change** として扱い、migration ADR を要求します ([productization_notes.md §8](productization_notes.md))。

### 不変条件

- 同じ `profile_fields` セットなら、いつ・どのデバイスで計算しても同じ `tool_profile_hash` が得られる。
- フィールドの追加は `spec_version` の bump を伴う (= 既存 hash が変わる)。
- `cmd`/`url`/認証情報は **絶対に hash 対象に含めない**。共有 `.kcs` がリモート実行を運ばないという [kcs.md §3](kcs.md) の方針と整合させるため。

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
```

これ以外は未実行または再実行対象です。

---

# 13. 要件文

設計書にはこう書くと良いです。

> KCSでは、Markdown化結果が最新かどうかをMarkdownファイル単体から判断しない。各原文ファイルについて、現在の原文ハッシュ、Markdown化Tool Profile Hash、Markdown化実行状態を台帳として保存し、それらの一致と出力ファイルの存在によってのみMarkdown化済みと判定する。Markdown 自体の content hash は計算・比較しない (Markdownize Adapter の非決定性ゆえ)。これにより、新規ファイル・更新ファイル・ツール変更・出力欠損・途中失敗を確実に検出し、後から安全に再実行できるようにする。

---

この仕様はMVP初期から入れるべきです。
これがないと、KCSは「どのファイルが本当に検索可能か」を保証できません。
