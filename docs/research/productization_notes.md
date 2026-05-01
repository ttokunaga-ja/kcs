# プロダクト化に向けた追記メモ

この文書は、既存の正本方針を変更するものではなく、実装・UI・運用へ落とすときに問題になりやすい点を補足する。

MVP は、検索体験を削った薄いデモではなく、KCS の基本機能を一通り実装した最小の完全系として扱う。この方針は維持する。

---

# 1. 初回スキャン前の承認

KCS はデフォルトで全 indexed scope を検索対象にし、全ファイルを管理対象にする。ただし、初回スキャンでは、対象範囲 preview、除外提案、明示承認を必須にする。

目的はデフォルト全管理を弱めることではない。KCS が単なる検索インデックスではなく、原本を content-addressed object として保存する知識アーカイブであることを、ユーザーが理解したうえで開始するためである。

必須フロー:

```text
kcs init
  ↓
候補 scope を探索
  ↓
対象フォルダ / 推定ファイル数 / 推定容量 / 大容量ファイル / 除外候補を preview
  ↓
.kcsignore / 設定を調整
  ↓
再 preview
  ↓
明示承認
  ↓
raw object 保存、Markdownize、Embedding、index 更新を開始
```

preview では、少なくとも次を表示する。

```text
root path
included scopes
excluded scopes
estimated file count
estimated total bytes
large files
hidden directories
build/cache/vendor candidates
network transmission policy
adapter execution mode
```

除外候補は提案であり、ユーザーの承認なしに自動除外しない。

```text
Suggested exclusions:
  node_modules/     build/cache candidate
  target/           build output candidate
  .git/             VCS internal metadata
  *.tmp             temporary file
  *.cache           cache file
  video.mp4         large file: 8.2GB
```

非対話環境では、承認済み scope または `--yes` / `--approve` のような明示オプションがない限り、`kcs index` は失敗させる。

承認記録には、少なくとも次を残す。

```text
scope_id
root_path
approved_at
actor
kcs_version
effective_ignore_hash
estimated_file_count
estimated_total_bytes
```

---

# 2. 容量より利便性を優先する

KCS は、容量効率よりも知識を失わないこと、あとから検索・履歴探索・復元できることを優先する。

したがって、全ファイル管理をデフォルトとする方針は維持する。動画・巨大PDF・画像・Officeファイルも、ユーザーが明示的に ignore しない限り管理対象に含める。

ただし、プロダクトはこの事実を隠してはならない。

```text
KCS は検索インデックスだけでなく、原本ファイルを content-addressed archive に保存します。
各 `.kcs` が管理するのはその `.kcs` が置かれたフォルダ自身が直接保持するファイルのみで、
サブフォルダにある別の `.kcs` 配下のファイルを親 `.kcs` が再帰的に取り込むことはありません。
同じ `.kcs` 内では同じ内容を重複保存しません。
別フォルダの別 `.kcs` に同じ内容のファイルが存在するのは、ユーザーが意図的に複数フォルダへ
同じファイルを配置した場合に限られ、その場合はフォルダ単位の独立性を優先して重複保存します。
```

必要な表示:

```text
推定追加容量
`.kcs` 内 dedup 後の保存見込み
別 `.kcs` 間で重複する可能性のある容量 (ユーザーが複数フォルダへ同じファイルを配置している場合のみ発生)
大容量ファイル一覧
現在の空き容量
ディスク枯渇リスク
除外候補
```

ディスク枯渇が予測される場合、KCS は勝手に対象範囲を狭めない。続行、除外、延期、中断をユーザーに選ばせる。

---

# 3. Scope Registry

各 `.kcs` は親と子だけを知り、兄弟や全体を直接管理しない。全体検索は、検索実行側が scope registry または探索済み `.kcs` 一覧を束ねることで実現する。

実装では、device-local な scope registry を明確に持つことを推奨する。

保存先候補:

```text
~/.local/share/kcs/scope-registry.sqlite
```

保存する情報:

```text
scope_id
root_path
kcs_path
folder_id
participates_in_global_search
approved_at
last_seen_at
effective_ignore_hash
permission_status
```

scope registry はデバイスローカルな探索・検索対象管理であり、共有 `.kcs` の正本ではない。フォルダ移動や外部ドライブ切断時は、`folder_id` と `scope.json` を使って再発見または stale 扱いにする。

scope registry は横断検索の対象一覧を束ねるためのものであり、raw object の所有権や dedup をグローバル化するためのものではない。dedup は各 `.kcs/objects` 内に限定し、別 `.kcs` 間の同一内容ファイルは重複保存を許容する。

---

# 4. フォルダごとの `.kcs` 運用

`.kcs` は基本的に各フォルダに生成される。ただし、空フォルダや未到達フォルダへ先回りして作る必要はない。

推奨:

```text
kcs init は現在フォルダの .kcs だけを作る
kcs index は対象ファイルや子scopeを発見した時点で必要な .kcs を作る
空フォルダには .kcs を作らない
履歴やobjectを持たない .kcs は repair / cleanup で整理可能にする
```

実装前に方針を明示すべき境界:

```text
symlink
hardlink
外部ドライブ
クラウドストレージの placeholder file
権限のないフォルダ
hidden directory
system directory
```

---

# 5. 物理レイアウト統一

内部正本は `.kcs/objects/normalized/` に統一する。

過去メモにある `.kcs/normalized/` は、bootstrap 時の簡略表記または仮想表示パスとして扱う。実装・契約ドキュメントでは、hash ベースの object store を正とする。

```text
internal:
  .kcs/objects/normalized/ab/cd/<raw_hash>.<tool_profile_hash>.md

virtual view:
  docs/report.pdf.md
```

---

# 6. 検索バックエンド統一

MVP の標準全文検索バックエンドは SQLite FTS5 とする。Vector は sqlite-vec を標準とする。

Tantivy など他の BM25 / full-text backend は将来候補として扱い、採用する場合は ADR で明示する。

```text
MVP:
  MetadataStore = SQLite
  TextSearchBackend = SQLite FTS5
  VectorSearchBackend = sqlite-vec

Future:
  Tantivy
  LanceDB
  Qdrant
  PostgreSQL + pgvector
```

---

# 7. Purge の保証範囲

`purge` は、KCS 管理下の object store、snapshot DAG、index、pack、cache、tombstone から対象ファイル由来の情報を削除する操作である。

ただし、OS backup、Time Machine、クラウド同期の過去版、外部 export、ユーザーが手動コピーしたファイル、KCS 外のログまでは KCS 単体では保証しない。

UI 文言は、過剰な保証を避ける。

```text
推奨:
  KCS 管理下の履歴から完全削除

避ける:
  世界中のすべてのコピーを完全削除
```

`purge` は必ず次を要求する。

```text
影響範囲 preview
理由入力
明示確認
対象 raw / normalized / chunk / embedding / evidence / index の削除
pack / cache / index rebuild
復元不能な最小 tombstone
```

---

# 8. commit_type の固定 enum について

現在の正本では、`commit_type` を `manual / auto / imported / migrated / repaired / merged / purged` の7種に閉じる方針である。

この方針を採用する場合でも、実装では以下を守る。

```text
type に混ぜない情報は actor / source / trigger / metadata に逃がす
metadata には schema_version を持たせる
未知 type を読んだ場合の error message を明確にする
新 type が必要に見える場合は、まず既存 type + metadata で表現できないか確認する
```

将来、実運用で固定 enum が強すぎると判明した場合は、既存の互換性を壊さない ADR と migration plan を作る。

---

# 9. local-first と同期構想の分離

MVP は単一端末・local-first を優先する。同期、共有版、Web修正提案、複数ユーザー権限は将来構想であり、MVP の CLI / core 仕様へ混ぜすぎない。

推奨:

```text
MVP文書:
  local object store
  local snapshot
  local search
  local restore
  local purge

将来同期文書:
  共有版
  Web修正提案
  権限
  同期競合
```

---

# 10. Adapter セキュリティ

Adapter は任意コマンド、任意URL、ローカルAPI、オンラインAPIを扱えるため、実行境界を明確にする。

最低限必要な制御:

```text
allow_network
allowed_scope
max_input_bytes
timeout_seconds
redact_logs
store_request_body = false
store_response_body = false
command allowlist / confirmation
secret redaction
```

オンライン Adapter は、`--online` 等の明示 opt-in なしにファイル内容を送信してはならない。初回スキャン preview でも、network transmission policy を表示する。

---

# 11. 実装前に埋めるべき仕様

実装前に、少なくとも以下の空ドキュメントを優先して具体化する。

```text
02_data-model/object-store.md
02_data-model/snapshot-dag.md
02_data-model/evidence-pointer-schema.md
02_data-model/normalized-markdown-spec.md
02_data-model/kcsignore-spec.md
02_data-model/sqlite-schema.sql.md
03_pipeline/ingest.md
03_pipeline/markdownization.md
03_pipeline/snapshot.md
04_runtime/restore.md
04_runtime/resume-and-retry.md
07_implementation/testing-strategy.md
08_evaluation/metrics-definitions.md
09_mvp/done-criteria.md
```

特に object hash 算出、Evidence Pointer、Normalized Markdown の決定性、purge 後の到達不能性は、実装後に変えると互換性コストが高い。

---

# 12. 横断規約 (cross-cutting contracts)

複数のドキュメントで部分的に触れられている規約事項を一元化する。各個別ドキュメントの記述はこの章を **正本** として参照する。

## 12.1 エラーコード namespace

すべての error は `KCS-E-<DOMAIN>-<SUBDOMAIN>-<NNN>` 形式の **error_code** を持つ。`error_kind` などのフリーテキストはユーザー向け表示専用で、機械判定には `error_code` を使う。

```text
DOMAIN:
  BATCH    バッチ処理 (markdownize / embedding / etc.)
  INDEX    インデックス更新
  SEARCH   検索 (FTS / vector / hybrid)
  COMMIT   commit / snapshot / restore
  GC       garbage collection
  PURGE    purge 操作
  SYNC     同期・共有
  ADAPTER  Adapter ロード・実行
  CONFIG   config / schema / 設定
  STORE    object store / fs IO
  AUTH     認証・認可
```

例: `KCS-E-BATCH-NET-001`, `KCS-E-SEARCH-VEC-INCOMPAT`, `KCS-E-COMMIT-SHALLOW-001`.

各ドキュメントが定義した個別エラー (batch.md / hybrid.md / commit_snapshot.md 等) はこの namespace に従う。新規 code 追加は ADR を要する。

## 12.2 CLI exit code

KCS のすべての CLI コマンドは以下の exit code を返す。

```text
0   成功 / 全 up_to_date
1   汎用 failure (詳細不明)
2   invalid usage / config 不正 / schema validation 失敗
3   一部失敗 (retryable 残あり)
4   全失敗 permanent
5   auth_error (user action 必要)
6   budget_exceeded により paused
7   user 中断 (SIGINT/SIGTERM)
8   incompatible profile / format version
9   confirm 拒否 (purge 等の確認プロンプトで no)
```

スクリプト連携はこれらを参照する。コマンド固有の補足は各 sub-command が docstring に明記する。

## 12.3 設定ファイル schema validation

すべての設定ファイルは JSON Schema (TOML は JSON 等価表現に変換して同 schema で validate) を持ち、CLI 起動時に schema-driven validation を行う。schema は KCS 本体に同梱する。

```text
~/.config/kcs/tools.toml          → schemas/tools.schema.json
~/.config/kcs/config.toml         → schemas/user-config.schema.json
.kcs/config.toml                  → schemas/folder-config.schema.json
.kcs/scope.json                   → schemas/scope.schema.json
.kcs/tool-lock.json               → schemas/tool-lock.schema.json
.kcs/manifest.json (簡易管理時)    → schemas/manifest.schema.json
```

validation 失敗は exit code 2 で停止し、`KCS-E-CONFIG-SCHEMA-NNN` を返す。schema は semver で版管理し、breaking change は migration を要求 (§12.5)。

## 12.4 時刻・タイムゾーン

すべての永続データ (commit timestamps, normalization_runs, access_events, snapshot lineage 等) の時刻は **UTC ISO8601 拡張形式 + suffix `Z`** に固定する。

```text
正:   2026-04-25T12:00:00Z
正:   2026-04-25T12:00:00.123456Z
誤:   2026-04-25T12:00:00      (TZ 欠落)
誤:   2026-04-25T12:00:00+09:00 (local 表記)
```

ユーザー向け UI 表示時のみ local TZ に変換する。snapshot lineage の順序判定は UTC タイムスタンプを使い、Lamport/HLC 系の論理時計は v0 では採用しない (採用判断は synchronization.md の改訂で別途)。

## 12.5 semver / 互換性 promise

KCS が公開する識別子は次のいずれかの semver 軸を持つ。

```text
kcs_format_version       .kcs ディレクトリ全体のフォーマットバージョン (kcs.md §5)
tool_lock_spec_version   tool-lock.json の schema バージョン (kcs.md §8.1)
profile_hash_spec        tool_profile_hash の計算規約バージョン (hash.md §9.1)
schema_version_<name>    各 config schema の semver
```

ルール:

```text
MAJOR bump:
  - 既存データの非互換破壊。migration 必須。
  - ADR と CHANGELOG への明示記載が必要。
  - 既存ユーザーは旧バージョンの read-only モード または migrate のいずれかを選択。

MINOR bump:
  - 新フィールド追加 (default 値で旧データを補える場合)
  - 既存値の意味は不変。

PATCH bump:
  - typo / コメント修正レベル。意味変更なし。
```

`commit_type` の値域 (commit_snapshot.md) のみは「永久に変更しない契約」として MAJOR bump も発動しない約束をしている。これは一般 semver 規約より強い保証である。

## 12.6 観測 (observability)

`logs/access.jsonl` 以外に、以下の構造化ログを `~/.local/share/kcs/logs/` に出す。

```text
events.jsonl       重要イベント (commit, gc, purge, schema migration)
metrics.jsonl      数値メトリクス (任意の interval、デフォルト1時間に1行)
errors.jsonl       error_code 付きの全エラー
```

各行 JSON で次のフィールドを必須とする:

```text
ts        UTC ISO8601 (§12.4)
level     debug | info | warn | error
code      error_code または event_code
component batch | search | commit | gc | ...
message   人間可読な短文
context   任意の JSON object (tool_profile_hash, commit_id, file_id 等)
```

ログのローテーションは日次、保持は 30 日 (config 上書き可)。`redact_logs=true` 時は `context` の `query`, `path`, `prompt` 等の機微フィールドをマスク。

## 12.7 命名リネーム表 (旧 → 新)

過去メモから現行設計への移行で発生した renaming を一覧化する。実装者はこの表を grep して旧称残置を排除する。

```text
旧称                            | 現行                                | 出所
-------------------------------- | ----------------------------------- | ----
folder.json                      | scope.json                          | kcs.md §6
normalized_hash                  | (廃止)                               | hash.md §9
canonical_text_hash              | (廃止)                               | diff.md §8
canonical_hash                   | (廃止)                               | diff.md §17
markdown_hash                    | (廃止)                               | diff.md §3
Normalized-Hash: <Markdown header> | Tool-Profile-Hash: <Markdown header> | read_only.md §2
.kcs/normalized/<path>.md        | .kcs/objects/normalized/ab/cd/<raw>.<tool>.md | kcs.md §11
last_indexed_git_commit          | (廃止: Git 連携は持たない)             | kcs.md §10
output_hash (in normalization_runs) | (廃止)                            | hash.md §3
```

## 12.8 推奨 Reading Path

ドキュメント間の依存順は以下を推奨する。新規参加者はこの順で読むことで概念がぶつからない。

```text
1. philosophy.md        理念と用語 (Git の翻訳, 忘れない/purge)
2. git_kcs.md           概念モデル (CAS, snapshot DAG, dedup scope)
3. kcs.md               .kcs ディレクトリの最終設計案
4. hash.md              identity と up_to_date 判定 + tool_profile_hash 規約
5. diff.md              prepared_units / normalized_units と差分判定
6. db.md                SQLite schema と検索バックエンド
7. read_only.md         書き込み主体と権限境界
8. batch.md             非同期ジョブと retry / budget
9. hybrid.md            検索モードと paging / MMR
10. commit_snapshot.md  commit_type と GC / purge
11. auto_organize.md    分類器と評価方針
12. synchronization.md  共有・修正提案 (v2 以降)
13. productization_notes.md  プロダクト方針 + 横断規約 (本章)
```

各章は前章までの概念を前提にできる。逆順参照は基本的に発生しない。

