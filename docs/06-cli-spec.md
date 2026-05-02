# 06 CLI Spec

KCS の CLI 契約。GUI は MVP 範囲外 (Phase 4+) だが、将来の用語翻訳マッピングを最後に明記する。

> 関連: [03-data-model.md](03-data-model.md) (`.kcs` レイアウト) / [04-pipeline.md](04-pipeline.md) (batch / retry / budget) / [05-runtime.md](05-runtime.md) (検索 / restore / GC / purge) / [09-mvp-scope.md](09-mvp-scope.md) (Phase plan)

---

# 1. Core Commands

`snapshot` を正規コマンド名とし、`commit` は Git に慣れた開発者向け alias。内部的には同じ履歴 object を作る。

```bash
kcs init [<path>]                       # 現在フォルダの .kcs を作成
kcs status                              # ファイル状態 / pending タスク / budget
kcs index [--preview|--approve|--yes]   # 取り込み (初回は preview + 承認必須)
kcs resume                              # 中断タスクの再開
kcs retry                               # failed タスクの再試行
kcs repair [--rebuild-db]               # SQLite を objects/ から再構築
kcs commit -m "<message>"               # = kcs snapshot create -m
kcs snapshot create -m "<message>"
kcs log [--at <commit>] [--since <dur>]
kcs diff <a> <b>
kcs search "<query>" [options]          # 詳細 §3
kcs open <evidence|chunk_id|raw_hash>   # OS 規定アプリで原本を開く
kcs view <evidence|path> [--at <commit>]
kcs inspect <hash>                      # object を JSON で表示
kcs restore <evidence|commit> --to <dir> # 詳細 §5
kcs tag <name> [<commit>]
kcs gc [--dry-run|--prune-unreachable]
kcs purge <path|--raw-hash <h>> --reason <reason> [--all-history]  # 詳細 §6
kcs evidence verify <pointer> [--strict]
kcs evidence retarget <pointer> [--latest|--at <commit>]  # 設計確定後 (09-mvp-scope.md §5.2)
```

`kcs init` は現在フォルダの `.kcs` のみ作成する。子フォルダの `.kcs` は `kcs index` の探索が対象を検出した時点で必要に応じて生成される。

---

# 2. 初回スキャン承認 (init / index preview)

未承認 scope に対する `kcs index` は、raw object 保存・Adapter 実行を始める前に **対象範囲 preview** を表示し、明示承認を要求する。

```bash
kcs index --preview     # preview のみ。何も書き込まない
kcs index --approve     # preview を承認、index 開始
kcs index --yes         # 非対話: 自動承認 (CI 用)
```

preview 内容:

```
- 対象 root / scope
- 推定ファイル数 / 推定容量
- 大容量ファイル一覧 (上位 N)
- 現在有効な ignore (.kcsignore + config)
- 除外候補 (提案。自動除外しない)
- network transmission policy (どの Adapter がオンライン送信するか)
- 別 .kcs と重複する可能性のある容量 (ユーザー配置由来のみ)
```

**非対話環境** (`isatty=false` / CI) では、承認済み scope または `--yes`/`--approve` がない限り `kcs index` は **exit 2** で失敗する。

---

# 3. Search

デフォルトは全 indexed scope を対象とする hybrid 検索 ([05-runtime.md §1](05-runtime.md))。

```bash
kcs search "認証仕様"

# scope 制限
kcs search "..." --scope .                  # カレントフォルダのみ
kcs search "..." --scope . --descendants    # カレントとその配下
kcs search "..." --scope ./Research [--descendants]
kcs search "..." --all-scopes

# モード
kcs search "..."              # auto (hybrid → text fallback)
kcs search "..." --text       # text only
kcs search "..." --vector     # vector only。失敗時は error
kcs search "..." --hybrid     # hybrid 強制。失敗時は fail_behavior 設定に従う
kcs search "..." --no-vector

# time-travel
kcs search "..." --at <commit>
kcs search "..." --all-history          # 削除済み・移動済み含む全 commit
kcs search "..." --include-deleted
kcs search "..." --since 7d

# paging / 結果制御
kcs search "..." --limit 20 [--offset 20|--cursor <token>]
kcs search "..." --json                 # 機械可読
```

レスポンス schema は [05-runtime.md §1.7](05-runtime.md)。`json` モードでは Evidence Pointer フル構造 + `next_cursor` を返す。

---

# 4. Output Format

すべての CLI は `--json` を持つ。デフォルトは人間向け整形、`--json` で機械可読。

```bash
kcs <command> --json
```

人間向け表示は色付き + path 短縮形 (`~/Documents/...`)。`--json` は色なし + 絶対 path + 完全 hash。エラーも `{ "error_code": "...", "message": "...", "context": {...} }` 形式で返る。

---

# 5. Restore

過去 commit 状態の復元。**現実ファイルを直接上書きしない**:

```bash
kcs restore <evidence|commit|raw_hash> --to <dir>
kcs restore <commit> --to ~/Recovered/<commit>     # 通常
kcs restore <evidence> --to ./recovered/ --force   # 既存上書き許可 (確認 prompt)
```

安全要件:

```
- --to <dir> は必須
- 既存ファイル上書きは --force + 確認 prompt
- restore は raw object をそのまま展開 (再 Markdownize しない)
- shallow commit からの restore は KCS-E-COMMIT-SHALLOW-001 で拒否
- purged 対象は KCS-E-PURGE-NOT-FOUND-001 / tombstone
```

---

# 6. Delete / Archive / Purge

通常削除 (`rm`) や archive は最新状態から対象を消すだけで、過去履歴は保持する。法務・秘匿・誤取り込みで履歴ごと消す場合のみ `purge` を使う。

```bash
kcs purge <path> --reason <legal|privacy|misingest|copyright|...> [--all-history]
kcs purge --raw-hash sha256:abc... --reason "mistaken import" --all-history
```

- `--reason` は必須引数 (`enum`)
- 確認 prompt 必須 (`--yes` でスキップ可)
- 結果 commit は `commit_type=purged`
- 詳細は [05-runtime.md §3](05-runtime.md)

---

# 7. Exit Code (横断規約)

```
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

スクリプト連携 (`kcs index && kcs search`) はこれらを参照する。コマンド固有の補足は各 sub-command の docstring で明記。

---

# 8. Error Code Namespace

すべてのエラーは `KCS-E-<DOMAIN>-<SUBDOMAIN>-<NNN>` 形式の `error_code` を持つ。`error_kind` などのフリーテキストはユーザー向け表示専用。機械判定は `error_code`。

```
DOMAIN:
  BATCH    バッチ処理 (markdownize / embedding / etc.)
  INDEX    インデックス更新
  SEARCH   検索 (FTS / vector / hybrid)
  COMMIT   commit / snapshot / restore
  GC       garbage collection
  PURGE    purge 操作
  ADAPTER  Adapter ロード・実行
  CONFIG   config / schema / 設定
  STORE    object store / fs IO
  AUTH     認証・認可
```

例: `KCS-E-BATCH-NET-001`, `KCS-E-SEARCH-VEC-INCOMPAT`, `KCS-E-COMMIT-SHALLOW-001`, `KCS-E-PURGE-NOT-FOUND-001`。

新規 code 追加は本書および各 spec の更新を伴う (破壊的変更扱い)。

---

# 9. Agent / Adapter API

CLI と同等の操作を、AI Agent と Adapter が共通利用する **構造化 API** として提供する。CLI は同一 API のフロントエンド。

```
KCS API が保証するもの:
  - 入力 object hash を明示
  - 処理対象 scope を明示
  - execution_mode (online_api | offline_api | deterministic_library) を明示
  - ネットワーク送信の許可状態を明示
  - 出力 artifact hash を記録
  - tool_profile_hash / agent_profile_hash を記録
  - 検索時は searched_scopes / excluded_scopes / fallback_reason を返す
```

URL、認証情報、コマンドパス、ライブラリ選択などの実行設定は **device-local config** に置き、`.kcs/` には保存しない。

```
KCS core
  → task descriptor
  → device-local Adapter
  → online API / offline API / deterministic library
  → artifact descriptor
  → KCS core
```

Adapter 種別と契約は [07-adapter-spec.md](07-adapter-spec.md)。

---

# 10. Export / Import

```bash
kcs export <scope> --to <bundle.kcsz>
kcs import <bundle.kcsz> --to <dir>
```

`.kcsz` は `.kcs/` の bundle 形式 (zip 等)。`.kcs` 単位で公開可能。別 `.kcs` の object 参照を前提にしないため、同一 raw_hash が別 `.kcs` に存在しても export 単位では重複を許容する。

---

# 11. Settings / Schema

すべての設定ファイルは JSON Schema (TOML は JSON 等価表現) で validate。CLI 起動時に schema-driven validation を行う:

```
~/.config/kcs/tools.toml          tools.schema.json
~/.config/kcs/config.toml         user-config.schema.json
.kcs/config.toml                  folder-config.schema.json
.kcs/scope.json                   scope.schema.json
.kcs/tool-lock.json               tool-lock.schema.json
.kcs/manifest.json                manifest.schema.json
```

validation 失敗は **exit 2** + `KCS-E-CONFIG-SCHEMA-NNN`。schema は semver で版管理し、breaking change は migration を要求。

---

# 12. 時刻 / TZ

すべての永続データ (commit timestamps / normalization_runs / access_events / snapshot lineage) は **UTC ISO8601 拡張形式 + suffix `Z`** に固定:

```
正:   2026-04-25T12:00:00Z
正:   2026-04-25T12:00:00.123456Z
誤:   2026-04-25T12:00:00         (TZ 欠落)
誤:   2026-04-25T12:00:00+09:00   (local 表記)
```

ユーザー向け UI 表示時のみ local TZ に変換する。Lamport/HLC は v0 で採用しない。

---

# 13. Observability

`logs/access.jsonl` 以外に、以下の構造化ログを `~/.local/share/kcs/logs/` に出力:

```
events.jsonl       重要イベント (commit, gc, purge, schema migration)
metrics.jsonl      数値メトリクス (デフォルト 1h 間隔)
errors.jsonl       error_code 付きの全エラー
```

各行 JSON 必須フィールド: `ts, level, code, component, message, context`。日次ローテーション、保持 30 日 (config 上書き可)。

`redact_logs=true` 時は `context` の `query`, `path`, `prompt` 等の機微フィールドをマスク。

---

# 14. GUI 用語翻訳マッピング (Phase 4+)

MVP では CLI のみ提供。将来 GUI を作る際の用語置換テーブル:

| CLI / internal | GUI 表示 |
| --- | --- |
| commit / snapshot | 版を保存 |
| checkout | 表示する版を切り替える |
| restore | 以前の版を復元 |
| branch | 修正提案 / 変更案 |
| merge | 反映 |
| conflict | 最新版と重なる編集 |
| gc | 不要な内部データを整理 |
| purge | このファイルの履歴を完全削除 |

GUI は MVP の責務ではないため、用語翻訳は GUI 実装フェーズで再評価する (今書いた表は出発点に過ぎない)。
