# 06 CLI Spec

KCS の CLI 契約。GUI は MVP 範囲外 (Phase 4+) だが、将来の用語翻訳マッピングを最後に明記する。

> 関連: [03-data-model.md](03-data-model.md) (`.kcs` レイアウト) / [04-pipeline.md](04-pipeline.md) (batch / retry / budget) / [05-runtime.md](05-runtime.md) (検索 / restore / GC / purge) / [09-mvp-scope.md](09-mvp-scope.md) (Phase plan)

---

# 1. Core Commands

`snapshot` を正規コマンド名とし、`commit` は Git に慣れた開発者向け alias。内部的には同じ履歴 object を作る。

```bash
kcs init [<path>]                       # <path> (省略時 = カレント) の .kcs を作成
kcs status                              # ファイル状態 / pending タスク / budget
kcs index [--preview|--approve|--yes] [--online|--offline]  # 取り込み (初回は preview + 承認必須)。
                                        # --online/--offline は当該実行の送信可否を上書き (正本 07-adapter-spec.md §3。
                                        # 優先順位: CLI > scope config > user config)
kcs batch resume [--override-budget] [--online|--offline]  # 中断タスクの再開 (budget 超過 pause は --override-budget 必須。04-pipeline.md §5.4/§5.7)。
                                        # --online は当該実行限りの一時 opt-in、--offline は当該実行の新規送信を禁止する逆向き上書き
                                        # (online 作業は据え置き。07 §3 — resume/retry/reindex も online 作業を駆動するため)。
                                        # in-flight の照会・出力取得・upload 掃除は新規送信に当たらず opt-in 不要 (04 §5.8 回復)。
                                        # markdownize online タスクと embedding enrichment パスを両方駆動 (04-pipeline.md §5.4)
kcs batch retry [--online|--offline] [--reset-violations <selector>]  # failed タスクの再試行 (markdownize + embedding。backoff/retry 予算を尊重)。
                                        # --reset-violations = 検証済み Adapter 更新後に contract_violation_count を 0 へ戻す
                                        # (selector は abandon と同形: intent_token または 4 組タスクキー — 曖昧時は拒否。
                                        # 変えるのは count のみ。確認プロンプト必須 — 04 §5.8。監査は cost-ledger の outcome 列に残る)
kcs batch abandon <intent_token|scope/adapter/input_hash/tool_profile_hash>
                                        # 照合が恒久不能な in-flight Batch job の打ち切り (estimated 記帳 + terminal 化。
                                        # 指定子は intent_token または batch_requests の 4 組タスクキー (3 組では別
                                        # profile 行と曖昧 — 曖昧時は拒否して token を要求)。tasks.jsonl の task_id は
                                        # 喪失許容のため使わない。kcs status が stalled 行の token を表示。
                                        # 確認プロンプト必須。残骸掃除完了まで intent_token は保持 — 04-pipeline.md §5.8)
kcs repair [--rebuild-db|--verify-objects] [--online|--offline]  # SQLite 再構築 / CAS 整合性検証 (10-operations.md §7.5)。
                                        # --rebuild-db は rebuild 後に enrichment を駆動し得るため online/offline 上書きの対象 (07 §3・04 §5.4)
kcs commit -m "<message>"               # = kcs snapshot create -m
kcs snapshot [create] [-m "<message>"]  # create 省略可。-m 省略時は自動 message ("snapshot at <UTC timestamp>")
kcs snapshot create -m "<message>"      # 正規形
kcs log [--at <commit>] [--since <dur>]
kcs diff <a> <b>                        # raw/path 差分 + derived-only 差分 (下記の差分種別)
kcs search "<query>" [options]          # 詳細 §3
kcs open <pointer|chunk_hash|raw_hash>  # OS 規定アプリで原本を開く。解決規則は §1.1
kcs view <pointer|path> [--at <commit>]
kcs inspect <hash>                      # object を JSON で表示
kcs restore <evidence|path|commit> --to <dir> # 詳細 §5
kcs tag <name> [<commit>]               # 論理名を refs/tags-v1/names.jsonl (truth) に append してから
                                        # canonical ref を作る (書込順序固定 — 03-data-model.md §2)
kcs tag --delete <name>                 # canonical ref を .kcs/.lock 下で atomic に除去。names.jsonl の
                                        # 行は残す (監査保全 — 「ref の無い names 行 = 正常」と整合。
                                        # 付替えは削除 → 再作成の 2 操作 — 専用 retarget は持たない)
kcs gc [--dry-run|--prune-unreachable] # prune 対象は 05-runtime.md §2.6 (raw/chunk/commit は対象外)。実装は Phase 4+ (09 §3.1)
kcs purge <path|--raw-hash <h>> --reason <reason> [--erase-tombstone] [--yes]  # 詳細 §6 (確認プロンプト必須 — --yes で省略)
kcs reindex [--force] [--at <commit>] [--yes] [--online|--offline]  # --at = 過去 snapshot の embedding 再生成 (05-runtime.md §1)。
                                        # --force = 新 gen で再 normalize / 再 embedding (Step 3)。--force は first-instance-wins の
                                        # 明示経路で gen+1 の新 instance を作る (07-adapter-spec.md §9。もう 1 つの合法経路 =
                                        # prepared_hash 変化起因の自動 gen+1 — 03-data-model.md §2.1)。
                                        # 上書きチェーンは manifest.parent_instance (三つ組) で永続記録 — parent_run_id は
                                        # task cache の揮発情報 (03-data-model.md §8、09-mvp-scope.md §5.1)。--force は確認プロンプト必須 (--yes で省略可)
kcs move --propose <src> <dst>          # 原本移動の提案。Agent はこちらのみ (Phase 4+、MVP 対象外)
kcs move --accept <id> | --reject <id>  # 提案の承認/却下。KCS が原本を mv できる唯一の経路 (03-data-model.md §10)。書き込み境界の予約定義
kcs evidence verify <pointer> [--strict]
kcs evidence verify --batch <pointers.jsonl> [--strict]  # <pointer> と --batch は相互排他 (--batch は Step 4+ — §7、08 §4.3)
kcs evidence retarget <pointer> [--latest|--at <commit>]  # 設計確定後 (09-mvp-scope.md §5.2)
```

本表はコマンド全量の spec である。MVP での採否・実装 Step の正本は [09-mvp-scope.md §1.2 / §3.1](09-mvp-scope.md) (Phase 4+ のコマンドは行内に注記)。

**`kcs diff` の差分種別**: raw / path の差分に加え、tree schema v2/v3 ([03-data-model.md §8](03-data-model.md)) が生む derived-only の変化 — `normalize_manifest_changed` (unit の failed → done 完成を含む) / `chunking_config_changed` / `chunk_set_changed` (公開 chunk 集合のみの変化) / `tool_lock_changed` (旧新 tool_lock_hash と変更 role) / `resurrection_published` (no-op 例外 (a) の publication commit — [05-runtime.md §8.1](05-runtime.md)) — を差分として表示する (`--json` も同種別を持つ)。derived-only commit を「差分なし」と表示してはならない。片側が旧版 tree (該当フィールド欠落) の場合、derived 差分は `unknown` と表示する。

`kcs init` は指定フォルダ (省略時 = カレント) の `.kcs` を 1 つだけ作成する (子孫には作らない)。子フォルダの `.kcs` は `kcs index` の探索が対象を検出した時点で必要に応じて生成される (**VCS repo root 配下には既定で生成しない**。既定導入以前の既存子 `.kcs` は grandfathered として引き続き有効 — [03-data-model.md §3](03-data-model.md))。この結果、深いフォルダ木では scope 数が多くなる。`kcs search` のデフォルトが全 indexed scope 横断である ([05-runtime.md §1.8](05-runtime.md)) のはこの帰結を受けた設計である。

`<pointer>` 引数の受理形式 (URI / inline JSON / stdin / hash 短縮形) は [08-evidence-pointer-spec.md §2.3](08-evidence-pointer-spec.md) を正本とする。

本節が CLI コマンドの **正本一覧** である。他 spec が新しいコマンド・フラグに言及する場合、本節への追加を伴う (破壊的変更扱い)。

`kcs tag` の新規 `<name>` は OS 非依存の portable leaf 規則に従い、Windows 予約名・禁止文字・
末尾 dot/space を拒否する。NFC 正規化 + Unicode lowercase が同じ tag は case-insensitive collision
として重複作成を拒否し、`HEAD` の case variant は予約する。canonical ref は legacy raw-name ref と
分離した `refs/tags-v1/tag-<digest64>` に保存する。
物理 ref leaf と legacy read 規則は [03-data-model.md §2](03-data-model.md) を正本とする。

## 1.1 open の原本解決

`kcs open <pointer|chunk_hash|raw_hash>` は以下の順で「開く対象」を決める:

```text
1. pointer を解決して raw_hash を得る (08-evidence-pointer-spec.md §3)
1a. object URI (kcs://<scope_id>/object/image/<image_hash> — 08 §2) の場合: type / hash を検証し、
   scope_id が文脈 store と不一致でも**自 store に該当 hash の object があればそれを解決する**
   (fork 複製由来の旧 scope_id URI — §10。hash が identity、08 §2)。自 store に無い場合のみ
   scope_id で通常解決する。image object を ~/.cache/kcs/open/ へ read-only materialize して開く
   (raw と同じ tombstone / journal barrier と purge closure の対象)。以降の手順 2-5 は raw 系入力のみ
2. tombstone 判定 (最優先): raw_hash に **active な** tombstone があるなら、working tree・cache の状態に
   関わらず §7 の規約どおり exit 4 — purge 済み原本が folder に残っていても KCS 経由では開かない
   (退役済み tombstone は対象外 — 再 ingest による退役は 05-runtime.md §3.5 の resurrection 規則)
3. working tree 解決:
   現在の working tree に同一 raw_hash を持つファイルが存在すれば (path_at_commit と
   異なる path でもよい。リネーム済みケース)、その実ファイルを OS 規定アプリで開く
4. 一時展開 (working tree に存在しない = 削除済み・過去版・raw_hash 直指定):
   raw object を ~/.cache/kcs/open/<raw_hash digest64>/<basename から導出した portable leaf> に
   read-only で展開し、それを OS 規定アプリで開く。basename の拡張子により OS の
   アプリ関連付けを機能させるが、元 basename 自体は物理名に使用しない
   (path_at_commit が無い場合は kind から推定した拡張子)
5. raw object が not_found → §7 の規約どおり exit 4
```

一時展開は **restore ではない**: working tree に書かず read-only であるため、[§5](06-cli-spec.md) の安全要件 (`--to` 必須 / `--force`) の対象外。展開先はキャッシュであり、GC (on_idle、Phase 4+) の掃除対象。MVP では自動掃除されないため、必要ならユーザーが削除してよい (正本は `objects/` に無傷)。**purge はこの展開 cache を削除 closure に含める** ([05-runtime.md §3.5](05-runtime.md))。永続的なコピーが必要な場合は `kcs restore <pointer> --to <dir>` を使う。一時展開で開いた場合、CLI は「原本は working tree に存在しない (削除または過去版)。永続コピーは kcs restore --to」の注記を stderr に表示する。

---

# 2. 初回スキャン承認 (init / index preview)

未承認 scope に対する `kcs index` は、raw object 保存・Adapter 実行を始める前に **対象範囲 preview** を表示し、明示承認を要求する。

```bash
kcs index --preview     # preview のみ。何も書き込まない
kcs index --approve     # preview を承認、index 開始
kcs index --yes         # 非対話: ローカル取り込み承認のみ自動化 (CI 用。制約は下記)
```

preview 内容:

```
- 対象 root / scope
- 推定ファイル数 / 推定容量
- 大容量ファイル一覧 (上位 N)
- 現在有効な ignore (.kcsignore + config)
- 除外候補 (提案。自動除外しない)
- 機微ファイル候補の警告 (secrets Tier A: デフォルト除外済み / Tier B: 要確認。10-operations.md §1.1)
- network transmission policy (どの Adapter がオンライン送信するか)
- 別 .kcs と重複する可能性のある容量 (ユーザー配置由来のみ)
- 推定 LLM コスト (markdownize / embedding 別。tool-lock の Adapter 単価による桁の目安)
- 現行 budget cap での推定完了時期 (cap 超過が予見される場合は承認前に警告 + 選択肢提示。[10-operations.md §1](10-operations.md))
```

**非対話環境** (`isatty=false` / CI) では、承認済み scope または `--yes`/`--approve` がない限り `kcs index` は **exit 2** で失敗する。

**`--yes` の制約**: `--yes` が自動化できるのはローカル取り込みの承認のみである。

```text
1. network opt-in を付与しない。opt-in 未成立の scope では、--yes で index を
   開始しても online_api Adapter への送信 task は発行されず pending のまま残る
   (07-adapter-spec.md §3)。非対話環境で opt-in が必要な場合は、事前に
   adapter.policy.allow_network = true を設定しておく。
2. secrets の built-in デフォルト除外 (10-operations.md §1.1 Tier A) を解除できない。
3. 承認記録の approval_method に "yes" が記録され、対話承認と事後監査で区別できる。
```

---

# 3. Search

デフォルトは全 indexed scope を対象とする hybrid 検索 ([05-runtime.md §1](05-runtime.md))。scope の列挙・結果統合・部分失敗・cursor は [05-runtime.md §1.8](05-runtime.md) の multi-scope search 契約に従う。

```bash
kcs search "認証仕様"

# scope 制限
kcs search "..." --scope .                  # カレントフォルダのみ
kcs search "..." --scope . --descendants    # カレントとその配下
kcs search "..." --scope ./Research [--descendants]
# path 引数は canonical 化 (絶対化 → lexical 解決 → 末尾 separator 除去 → realpath) して
# registry の root_path と byte 比較する (05-runtime.md §1.8)
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
kcs restore <evidence|path|commit> --to <dir>
kcs restore <commit> --to ~/Recovered/<commit>     # 通常
kcs restore <pointer> --to ./recovered/ --force    # 既存上書き許可 (確認 prompt)
```

安全要件:

```
- --to <dir> は必須
- 既存ファイル上書きは --force + 確認 prompt
- restore は raw object をそのまま展開 (再 Markdownize しない)
- evidence は pointer URI / inline JSON / stdin、path は論理 direct-child 名、commit は HEAD / tag / full commit hash。tag と同名の path は tag を優先する。raw_hash shorthand は restore では受理しない
- shallow commit からの restore は KCS-E-COMMIT-SHALLOW-001 で拒否
- purged 対象は KCS-E-PURGE-NOT-FOUND-001 / tombstone
```

---

# 6. Delete / Archive / Purge

通常削除 (`rm`) や archive は最新状態から対象を消すだけで、過去履歴は保持する。法務・秘匿・誤取り込みで履歴ごと消す場合のみ `purge` を使う。

```bash
kcs purge <path> --reason <legal|privacy|misingest|copyright|...>
kcs purge --raw-hash sha256:abc... --reason misingest --erase-tombstone
```

purge は常に**全履歴**の raw 本文・派生 artifact を対象とする (commit / tree object は書き換えない。[05-runtime.md §3.5](05-runtime.md))。デフォルトでは tombstone を記録し、`--erase-tombstone` は public tombstone を残さない (Evidence Pointer は not_found)。後者の fsck-only non-content erase receipt は pointer state や re-ingest を阻止しない。

- `--reason` は必須引数 (`enum`)
- 確認 prompt 必須 (`--yes` でスキップ可)
  - (purge の `--yes` は確認プロンプトのスキップのみで、§2 の初回スキャン承認の `--yes` とは
    独立。network opt-in を付与する効果はどちらにもない)
- 結果 commit は `commit_type=purged`
- 詳細は [05-runtime.md §3](05-runtime.md)

> MVP の purge は raw 本文・派生 artifact の全履歴削除 + tombstone (既定) / `--erase-tombstone` (not_found) まで。tree/commit を書き換える完全な履歴書き換え (filename 秘匿ケース) は MVP 非対応で v2+ / Phase 4+ ([05-runtime.md §3.5](05-runtime.md), [09-mvp-scope.md §3.1](09-mvp-scope.md))。

---

# 7. Exit Code (横断規約)

```
0   成功 / 全 up_to_date
1   汎用 failure (詳細不明)
2   invalid usage / config 不正 / schema validation 失敗
3   retryable な失敗が残っている (部分成功を含む。lock 取得失敗のような全体 retryable もここ)
4   全失敗 permanent
5   auth_error (user action 必要)
6   budget_exceeded により paused
7   user 中断 (SIGINT/SIGTERM)
8   incompatible profile / format version
9   confirm 拒否 (purge 等の確認プロンプトで no)
```

**Evidence Pointer 系コマンドへの割当** ([08-evidence-pointer-spec.md §4.3](08-evidence-pointer-spec.md)):

```text
kcs evidence verify            検査完了で 0 (結果は status フィールド)。parse 失敗は 2
kcs evidence verify --strict   全 alive なら 0。tombstoned / not_found が 1 件でもあれば 4。
                               scope_unreachable のみの失敗は 3 (retryable — 08 §4.3)。
                               unverifiable のみも 3 (reason = commit_shallow / tree_v1 /
                               manifest_missing — 08 §4.3。shallow/tree_v1 は状況変化で解消し得るが
                               manifest_missing は恒久 — reason で判別)。registry_duplicate も 3
kcs evidence verify --batch <pointers.jsonl>   一括 verify (Step 4+ — 08 §4.3)
                               (--batch 混在時も 4。内訳は --json の各行 status で判定)
kcs open / view / restore      dead pointer (tombstoned / not_found) は 4。scope_unreachable は 3 (retryable — 08 §4.3)
kcs evidence retarget          対応なし / ambiguous は 4。
                               tool_profile_hash 不一致で chunk 解決不能 (retarget 要) は 8
```

スクリプト連携 (`kcs index && kcs search`) はこれらを参照する。コマンド固有の補足は各 sub-command の docstring で明記。

---

# 8. Error Code Namespace

すべてのエラーは `KCS-E-<DOMAIN>-<SUBDOMAIN>-<NNN>` 形式の `error_code` を持つ。`error_kind` などのフリーテキストはユーザー向け表示専用。機械判定は `error_code`。

DOMAIN 一覧の正本は [10-operations.md §12.1](10-operations.md)。本節は同一リストの転記であり、差分が生じた場合は 10 側を正とする。

```
DOMAIN:
  BATCH    バッチ処理 (markdownize / embedding / etc.)
  INDEX    インデックス更新
  SEARCH   検索 (FTS / vector / hybrid)
  COMMIT   commit / snapshot / restore
  GC       garbage collection
  PURGE    purge 操作
  EVIDENCE Evidence Pointer 解決 / verify / retarget
  REGISTRY scope registry (live clone 重複・退役)
  SYNC     同期・共有 (v2 予約。MVP では発行しない)
  ADAPTER  Adapter ロード・実行
  EMBED    embedding profile / modality 検証
  CONFIG   config / schema / 設定
  STORE    object store / fs IO
  AUTH     認証・認可
```

例: `KCS-E-BATCH-NET-001`, `KCS-E-SEARCH-VEC-INCOMPAT-001`, `KCS-E-COMMIT-SHALLOW-001`, `KCS-E-COMMIT-HISTORY-LIMIT-001` (bounded history walk の aggregate cap 超過、単独操作 exit 4 / multi-scope は既存 partial 規則、[05-runtime.md §1.6](05-runtime.md)), `KCS-E-PURGE-NOT-FOUND-001`, `KCS-E-STORE-PATH-001` (パス区切りを含む path の schema violation、[03-data-model.md §3](03-data-model.md)), `KCS-E-SEARCH-SCOPE-ALL-FAILED-001` (multi-scope search の全 scope 失敗、[05-runtime.md §1.8](05-runtime.md)), `KCS-E-SEARCH-CURSOR-001` (別クエリ・別条件の cursor 誤用、[05-runtime.md §1.5](05-runtime.md)), `KCS-E-INDEX-REBUILDING-001` (index 再構築中、[05-runtime.md §6](05-runtime.md)), `KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001` (pointer の scope が scope_path・registry のどちらでも解決不能、[08-evidence-pointer-spec.md §3.2](08-evidence-pointer-spec.md)), `KCS-E-EVIDENCE-RETARGET-AMBIG-001` (retarget 候補が複数で一意に定まらない、[08-evidence-pointer-spec.md §5](08-evidence-pointer-spec.md))、`KCS-E-REGISTRY-DUP-001` (同一 scope_id の複数 live clone — 検索 skip・解決 error、[10-operations.md §3](10-operations.md))、`KCS-E-STORE-CORRUPT-001` (CAS object の content hash 不一致・欠落、`kcs repair --verify-objects`、[10-operations.md §7.5](10-operations.md))、`KCS-E-STORE-LOCKED-001` (`.kcs/.lock` 取得失敗 — 待機せず即失敗、exit 3、[05-runtime.md §6](05-runtime.md))、`KCS-E-STORE-DUP-001` (単一 tree 内の重複 `path`、[03-data-model.md §8.1](03-data-model.md)。`/` 入り path の `KCS-E-STORE-PATH-001` とは区別する)、`KCS-E-CONFIG-USAGE-001` (invalid usage / 不正オペランド — 例: `init` path 不存在、`.kcs` scope 外での実行、不正 hash 引数。schema violation の `KCS-E-CONFIG-SCHEMA-001` とは区別。exit 2)、`KCS-E-EMBED-MODALITY-001` (`modality != "multimodal"` の embedding profile の採用拒否 — tool-lock materialize / adapter 登録時に検証、[03-data-model.md §7](03-data-model.md)。exit 2)。

新規 code 追加は本書および各 spec の更新を伴う (破壊的変更扱い)。

---

# 9. Agent / Adapter API

CLI と同等の操作を、AI Agent と Adapter が共通利用する **構造化 API** として提供する。CLI は同一 API のフロントエンド。

**Phase 境界**: Agent 向けの構造化 API の提供は Phase 5 ([09-mvp-scope.md §2](09-mvp-scope.md))。MVP (Phase 1-3) における外部 Agent の導線は **CLI + `--json` (§4) のみ** であり、Agent はシェル経由で `kcs search --json` / `kcs evidence verify` 等を実行する。`kcs evidence verify` も MVP の互換性契約に含まれる。Phase 5 の構造化 API は以下を **互換性契約** として維持しなければならない:

- 検索レスポンス schema ([05-runtime.md §1.7](05-runtime.md))
- Evidence Pointer schema と正規シリアライズ ([08-evidence-pointer-spec.md §2](08-evidence-pointer-spec.md))
- exit code / error_code 規約 (§7, §8)

MCP server 等の Agent 統合導線は Phase 5 の検討論点であり、MVP では設計しない。Adapter API (task descriptor / artifact descriptor) は Step 2 から必要となる別契約で、[07-adapter-spec.md](07-adapter-spec.md) を正本とする。

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

> 実装は Phase 4+ ([09-mvp-scope.md §3.1](09-mvp-scope.md))。MVP のバックアップは lock 未取得確認 + ディレクトリコピーで代替する ([10-operations.md §7.5](10-operations.md))。

```bash
kcs export <scope> --to <bundle.kcsz>
kcs import <bundle.kcsz> --to <dir> [--as-new-scope]  # bundle の scope_id が registry に live 登録済みなら拒否
                                        # (KCS-E-REGISTRY-DUP-001 — clone 併存を正規操作で作らない)。
                                        # 複製として取り込むには --as-new-scope で新 scope_id を採番
                                        # (fork 相当。以後の Evidence Pointer は新 ID を指す。既存 normalized 内の
                                        # kcs:// URI が旧 scope_id を含んでいても、自 store に該当 object があれば
                                        # 解決する — hash が identity (08 §2、解決手順は §1.1 1a)。bundle 内 object で自足)。
                                        # fork は旧 scope の approvals[]・初回スキャン承認 (scan_approval)・
                                        # adapter.policy.allow_network を引き継がない — 新 scope_id で preview +
                                        # 取り込み承認と network opt-in を再実施する (安全側。07 §3・10 §1)
```

`.kcsz` は `.kcs/` **全体**の bundle 形式 (zip 等 — objects/・refs/ (tags-v1/names.jsonl を含む)・chunks.jsonl 等の truth 一式)。`.kcs` 単位で可搬。別 `.kcs` の object 参照を前提にしないため、同一 raw_hash が別 `.kcs` に存在しても export 単位では重複を許容する。**bundle には scope.json の approvals[]・logs/ の運用記録・登録 path 等の機微 metadata が含まれる** — 共有は同一信頼境界内 (自分の別端末・バックアップ) を想定し、第三者公開用の sanitize (承認・log・path の除去) は Phase 4+ の export mode で扱う。

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

`tools.schema.json` の認証情報フィールド (`auth`) の形式は [07-adapter-spec.md §1](07-adapter-spec.md) に従う (`keychain:` / `env:` / `plain:` prefix)。

validation 失敗は **exit 2** + `KCS-E-CONFIG-SCHEMA-NNN`。schema は semver で版管理し、breaking change は migration を要求。

---

# 12. 時刻 / TZ

すべての永続データ (commit timestamps / normalization_runs / access_events / snapshot lineage) は **UTC ISO8601 拡張形式 + suffix `Z`** に固定 (例外 = cost-ledger.sqlite の内部時刻列は UTC epoch ミリ秒 INTEGER — 正本 [10-operations.md §12.4](10-operations.md)):

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

`redact_logs` のデフォルトは true (ログ全域。正本は [10-operations.md §12.6](10-operations.md))。true 時は `context` の `query`, `path`, `prompt` 等の機微フィールドをマスク。

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
| purge | このファイルの本文を全履歴から物理削除 (削除した事実は記録に残る) |

GUI は MVP の責務ではないため、用語翻訳は GUI 実装フェーズで再評価する (今書いた表は出発点に過ぎない)。
