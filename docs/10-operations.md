# 10 Operations (横断規約と運用)

この文書は、実装・UI・運用へ落とすときに問題になりやすい点を補足する。

> **NOTE (2026-05 改訂)**: ポジショニング・ターゲットユーザー・MVP スコープ・Phase plan は **正本を [01-positioning.md](01-positioning.md) に移した**。本書はその下位の運用ルールを扱う。競合分析は [competitive-landscape.md](competitive-landscape.md) を参照。

MVP は **「Evidence-grounded local knowledge archive」としての最小完全系** として扱う。「全部入りの Git for knowledge」を目指さない。詳細は [01-positioning.md §5](01-positioning.md)。

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

# 3. Scope Registry (= cache only, NOT truth)

KCS は **二層構造** をとる。データ・所有権・権限の **正本は各フォルダ直下の `.kcs`** に閉じる。device-local な scope_registry や将来の global aggregator は **検索キャッシュ・発見補助に過ぎない**。両者を混同しない。

```
truth = folder-local .kcs
  raw object / normalized / chunks / commits / refs
  権限境界 / partial sync / purge / export の単位

cache = scope_registry / aggregator
  検索の探索対象一覧、stale 検出、UI 統合
```

実装では、device-local な scope registry を明確に持つ。

保存先:

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

### 不変条件 (cache vs truth)

```text
1. scope_registry のみを更新して `.kcs` の状態が変わる実装は禁止。
2. scope_registry 喪失は再構築可能 (各 `.kcs` を rescan)。
3. `.kcs` 喪失は復旧不能 (registry には正本データがない)。
4. 検索結果メタには「正本の `.kcs` パス」を必ず含める。
5. raw object の所有権・dedup は scope_registry でグローバル化しない。
   各 `.kcs/objects` 内に閉じる (横断 dedup を諦めた帰結、git_kcs.md §5)。
```

scope registry は共有 `.kcs` の正本ではない。フォルダ移動や外部ドライブ切断時は、`folder_id` と `scope.json` を使って再発見または stale 扱いにする。

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

Tantivy など他の BM25 / full-text backend は将来候補として扱い、採用する場合は本書を更新する (破壊的変更扱い)。

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

将来、実運用で固定 enum が強すぎると判明した場合は、既存の互換性を壊さない migration plan を本書および 05-runtime.md に明記する。

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

# 10.5 Incremental Markdownize (要件)

ファイルが更新された場合、Markdownize (OCR を含む) Adapter には **新 raw だけでなく、旧 raw + 旧 normalized Markdown + 変更ヒント** をセットで渡し、変更が軽微なら Adapter が部分更新を返す方式を採用する。MVP〜v1 のプロダクト要件として確定する。

目的:

```text
1. LLM API コスト抑制 (cost guardrail と整合、batch.md §Cost guardrail)
2. 全文再生成による表記ゆれ・見出し変動を抑制
   → unit_id / chunk / Evidence Pointer の安定性向上
3. 変わっていない unit の再 LLM 呼び出しを完全排除
```

実装責務の分担:

```text
KCS:
  - 変更検出 (raw_hash 変化 + page fingerprint 変化率算出, diff.md §13)
  - 発動条件の判定 (capability / 閾値 / 連続回数)
  - Adapter への入力組み立て (旧 raw, 旧 Markdown, hints)
  - Adapter からの fallback_to_full 受信時の full 再投入
  - normalization_run への mode/parent_run_id/changed_unit_keys の記録

Markdownize Adapter:
  - capabilities = ["incremental_update"] の宣言
  - incremental 入力を受け取って updated_units / unchanged_unit_keys を返す
  - 軽微でないと判断したら fallback_to_full=true を返す
```

Adapter が `incremental_update` capability を宣言しない場合は、KCS は常に full モードで Adapter を呼ぶ。これにより既存 Adapter との後方互換が保たれる。

詳細仕様: [diff.md §6.1](diff.md), [batch.md task type=markdownize, mode](batch.md), [kcs.md §8 capabilities](kcs.md)

設定上書き例 (`.kcs/config.toml`):

```toml
[markdownize.incremental]
enabled = true
threshold = 0.30
max_consecutive = 5
include_neighbors = 1
```

---

# 11. 実装前に埋めるべき仕様

> Phase 1〜3 ([01-positioning.md §6](01-positioning.md)) を着手する前に、少なくとも以下を具体化する。Phase 4-5 の仕様は MVP リリース後に着手する。

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

各 spec が定義した個別エラー (04-pipeline.md / 05-runtime.md / 06-cli-spec.md 等) はこの namespace に従う。新規 code 追加は本書および該当 spec の更新を伴う (破壊的変更扱い)。

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
  - 該当 spec と CHANGELOG への明示記載が必要。
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
0a. 01-positioning.md             プロダクト位置づけ・ターゲット・MVP スコープ・Phase plan (正本)
0b. competitive-landscape.md   競合分析 / Perkeep 失敗分析 / 差別化の核
1.  02-philosophy.md              理念 (Evidence Pointer, Markdown 正規化, 忘れない/purge)
2.  git_kcs.md                 概念モデル (CAS, snapshot DAG, dedup scope)
3.  kcs.md                     .kcs ディレクトリの最終設計案
4.  hash.md                    identity (hash) vs 類似性 (semantic_fingerprint) + tool_profile_hash
5.  diff.md                    prepared_units / 差分判定 / incremental Markdownize
6.  db.md                      SQLite schema と検索バックエンド
7.  read_only.md               書き込み主体と権限境界
8.  batch.md                   非同期ジョブと retry / budget
9.  hybrid.md                  検索モードと paging / MMR
10. commit_snapshot.md         commit_type と GC / purge
11. auto_organize.md           分類器と評価方針 (Phase 4)
12. synchronization.md         共有・修正提案 (v2 以降, Phase 5+)
13. productization_notes.md    プロダクト方針 + 横断規約 (本章)
```

各章は前章までの概念を前提にできる。逆順参照は基本的に発生しない。新規参加者は **0a → 0b → 1** の順に読むことで KCS が「Evidence-grounded local knowledge archive」であることを最初に理解できる。

