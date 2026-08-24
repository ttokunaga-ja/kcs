# Step4b 契約テスト仕様書: task 状態機械 / Tier 承認 / adapter 契約 / pipeline 残 (P3-A)

> **Historical record, non-authorizing.** 現行 authority は本文が引用する canonical docs と Rust tests に限る。ID は review provenance のためだけに残し、compatibility、migration、CLI、schema、future work を authorize しない。

> 本書は **実装より先にテストを固定する** ための契約仕様。Rust 実装コードは含まない。
> 正本は `docs/04-pipeline.md` **§3 (Markdownize, §3.1/§3.2) / §5.1〜§5.3 (タスクモデル・状態遷移・
> エラー種別) / §5.5〜§5.7 (冪等性・exit code・Resume/Repair)**、`docs/07-adapter-spec.md` **全体
> (§1〜§9)**、`docs/10-operations.md` **§1/§1.1 (初回スキャン承認・Secrets デフォルト除外)** — 期待値は
> これら (および直接引用する隣接節) の規範文からのみ導く。系譜は
> Phase 1 の ledger/lifecycle ID 体系・優先度規約・
> 「未定義/曖昧の切り出し」方針。記法は `### QA<連番> ... - 正本 / 前提 / 操作 / 期待` 形式 (自己完結)。
>
> **現状確認の前置き**: 当時の gap inventory の「実装状態」欄は 2026-07-21 時点のスナップショットで
> あり、本書作成時点 (2026-07-22) には Phase 1 (`crates/kio-pipeline/src/ledger/` — cost-ledger.sqlite
> 2 相プロトコル・abandon・`--reset-violations`・stalled 表示) と一部 Phase 2 相当の作業
> (`--prune-orphans`/`--registry-prune` CLI 配線、`kio search` の `--online`/`--offline`) が実際には
> 既に着地しており、historical inventory の記述より実装が進んでいる箇所が複数ある。本書の各契約は inventory の
> 文言ではなく **本書作成時点で直接読んだ現行コード** を「現状」として引用する (該当箇所ごとに
> file:line を再確認済み)。

**担当グループ**: P3-A (task 状態機械 / Tier 承認 / adapter 契約 / pipeline 残)。

**対象 U 項目 (当時の gap inventory)**: A 領域残り **U1, U2, U3, U4, U11, U12**、I 領域全部
**U78-U94, U143**。加えて Phase 2 からの繰越 3 件: **PB14, PB16, PB17** (staging root 分類・open cache
残骸回収)、**PB24** (registry live 重複 fail-closed の書込系/online 起動への拡大)、**CL40**
(Markdownize 部分回復の再導出)。

## 対象外 (他グループ・Phase 1/2 既済 — 混同注意)

- **U1 のうち `kio batch abandon` CLI と `kio status` の `stalled` 表示**: Phase 1 で実装済み
  (`crates/kio-pipeline/src/ledger/ops.rs` `resolve_abandon_selector`/`execute_abandon`/`stalled_rows`、
  `crates/kio-cli/src/main.rs` `BatchCommand::Abandon`/`run_batch_abandon`)。
  `step4b-contract-tests-ledger.md` **CL62-CL68** (abandon) / **CL37** (stalled) が正本。本書 §A は
  taskの**状態機械**部分 (hold_reason 3 値・paused/pending 分離) のみを扱う。
- **U1 のうち `kio batch retry --reset-violations`**: Phase 1 で実装済み
  (`main.rs` `run_batch_reset_violations`、`RetryArgs.reset_violations`)。ledger.md §M note-6 が
  裁定済み・`crates/kio-cli/tests/step4b_ledger_contract.rs` に実 CLI テストあり。本書は再契約しない。
- **U4 のうち check-then-reserve の Tx 機構本体 (device/folder/device_per_adapter 三条件・
  candidate=0 免除・ledger() 合成・sync 縮退 2 相)**: Phase 1 で実装済み
  (`crates/kio-pipeline/src/ledger/ops.rs` `check_then_reserve`、`step4b-contract-tests-ledger.md`
  **CL56-CL61**)。本書 §D は CL56-61 が明示的に「立ち入らない」と宣言した残余 — **folder 層の
  per_adapter が config パース・enqueue 時事前チェック・`kio status` 表示のいずれからも消えていない
  こと** のみを扱う (ledger.md §I 冒頭の但し書き参照)。`markdown`→`markdownize` の adapter_kind 文字列
  リネームは本書作成時点で**既に完了**しており (根拠は §D 前置き参照)、再契約しない。
- **U11 のうち「二重課金防止の手段が sync/Batch の二段構えである」という事実確認**: Phase 1
  `step4b-contract-tests-ledger.md` **CL41** が既に契約化済み。本書 §E は CL41 が明示的に
  「Adapter レベルの契約 — 実装詳細は 07-adapter-spec 側」と本書へ委譲した部分 (sync 呼出が provider
  idempotency key を実際に要求する Adapter 層の機構) のみを扱う。
- **U82 (`--reset-violations` 機能新設)**: I 領域の一連番だが Phase 1 で実装済み (上記 U1 の対象外
  項目と同一機構)。本書は対象外とする。
- **PB17 の cache 型分離自体 (`open/image/<digest64>/` への raw/image 分離、U22-U24)**:
  `step4b-contract-tests-p2a.md` (P2-A, PA03) の管轄であり本書は再契約しない。本書が引き取るのは
  「PB14/16 (staging root 分類) と同じ `--prune-orphans` 経路の中で、PB17 の削除トリガーが**現に
  正しく動作しているか**」の現状確認 1 本のみ (§S 末尾、regression-lock)。
- **fsck の検証ロジック本体・evidence pointer 解決・restore・purge 機構本体・検索 gate/cursor**:
  P2-A/B/C の管轄 (`step4b-contract-tests-p2{a,b,c}.md`)。本書は必要な箇所のみ参照する。
- **`kio evidence retarget` の実装そのもの**: Phase 4+ (08§5)。本書の対象外。

## 実装対象ファイルの見込み (現状把握の記録 — 実装方針を指図するものではない)

- `crates/kio-pipeline/src/task.rs` — `TaskStatus`/`RetryErrorKind`/`RetryPolicy`/`retry_policy`
  (hold_reason 相当の分離が無い。§A)、`MAX_TASK_RECORDS` の hard reject のみ (§C)
- `crates/kio-pipeline/src/markdownize.rs` — `validate_markdownize_response`/`validate_full_response`/
  `validate_unit_shapes` (§K/§L/§M の主戦場)
- `crates/kio-pipeline/src/budget.rs` / `crates/kio-pipeline/src/ledger/ops.rs` — `BudgetCaps`
  (`folder_per_adapter` 残存) vs `BudgetCapConfig` (該当 field 無し) の不整合 (§D)
- `crates/kio-adapter/src/types.rs` — `AdapterRun`/`AdapterProfile`/`MarkdownizeResponse`/
  `EmbeddingResponse`/`validate_cosine_vector` (§F/§K/§N)
- `crates/kio-adapter/src/traits.rs` — 6 kind 別 trait のみ、Batch 実行契約 trait 皆無 (§O)
- `crates/kio-adapter/src/identity.rs` — `PROFILE_FIELDS` に `render_params`/`bbox_annotation` が
  無い (§J)
- `crates/kio-adapter/src/bbox_annotation.rs`/`mistral_ocr.rs`/`gemini_embedding.rs` — §J/§L/§N/§O
- `crates/kio-cli/src/main.rs` — Commands enum に `Adapter` 無し (§H)、`persistent_network_allowed_for_kio_dir`
  が device-global `consents.jsonl` を使い OR ゲート (§G)、`--online`/`--offline` の
  per-subcommand 配線状況 (§I)、`consecutive_incremental_count`/`previous_instance_for_path` (§R)
- `crates/kio-cli/src/verify_objects.rs` — `prune_orphans` (§S。PB14/16 は関数自身の doc comment が
  「本セッション未実装」と明記)
- `crates/kio-core/src/scope.rs` — `is_tier_a_secret_name`、scope.json は 3 key のみ (§B)
- `crates/kio-core/schemas/{scope,config}.schema.json` — `approvals`/`scan_approval` 皆無 (§B/§G)

---

## A. task 状態機械の拡張 (U1)

### QA1 hold_reason 3 値 enum が存在せず、budget/tier_b の 2 値のみが Paused を生成する [P0]
- 正本: 04 §5.2 L679-683『pending → paused → pending 保留。**hold_reason = budget (§5.4) | auth |
  tier_b_approval** (10-operations.md §1.1)。解除条件 = 理由の解消...』
- 前提: 現行 `TaskDescriptor` (`crates/kio-pipeline/src/task.rs:45-52,76`) は理由を型なしの
  `fallback_reason: Option<String>` で表現し、`TaskStatus::Paused` を生成する本番コード上の呼出箇所は
  `main.rs:9728-9729`(`"budget_exceeded"`)・`main.rs:12229/12252/12293`
  (`SECRETS_TIER_B_HOLD="secrets_tier_b_hold"`)・`main.rs:14655-14665`
  (online markdownize task 作成時、同 2 値の分岐) の**厳密に 2 値のみ**である (`hold_reason` という
  field/文字列は crates 全体で grep 0 件)。
- 操作: budget 超過・Tier B secrets・auth_error の 3 パターンでタスクを生成する。
- 期待: 3 パターンとも `status=paused` かつ `hold_reason` が閉 enum `{"budget","auth","tier_b_approval"}`
  のいずれかを持つこと。現行実装は budget/tier_b の 2 値しか Paused を生成せず (下記 QA2 のとおり
  auth は Paused を生成しない)、値の綴りも spec の `tier_b_approval` ではなく `secrets_tier_b_hold`
  である — 3 値 enum への統合とスペル統一の両方が未達。

### QA2 auth_error は Paused を生成せず Failed (非 retryable) に直行する [P0]
- 正本: 04 §5.2 L679『hold_reason = budget (§5.4) | **auth** | tier_b_approval』(auth も paused 側の
  理由として明記)
- 前提: `retry_policy(RetryErrorKind::AuthError)` (`task.rs:889-896`) は
  `retryable: false, max_attempts: Some(0), paused: false` を返す。実際に status を書き込む送信失敗
  handler (`main.rs:9808-9845`、特に line 9832) は **全 error kind に対して無条件に**
  `candidate.status = TaskStatus::Failed;` を実行し、`policy.paused` を一切参照しない
  (`grep -rn "policy\.paused" crates/` は 1 件のみ — `task.rs:1174` の unit test assertion で、
  本番コードからの参照は 0 件)。
- 操作: online Adapter 呼出が auth_error で失敗するタスクを実行する。
- 期待: spec が `auth` を hold_reason の閉 enum に含める以上、auth_error は (少なくとも
  `kio status` 上は) `paused (hold_reason=auth)` として表示され、user action (認証情報更新) で解除
  可能な状態として扱われるべきである。現行は `status=Failed` (exit 5 相当の permanent failure) に
  直行し、`RetryPolicy.paused` フィールド自体が本番コードから到達不能な死んだ抽象化になっている。

### QA3 [regression] rate_limit は仕様どおり Failed ではなく pending + next_retry_at で表現されるべきだが、現行は Failed に着地する [P0]
- 正本: 04 §5.2 L682-683『rate_limit は paused ではなく **pending + next_retry_at** で表現する
  (§5.3 — 呼出後に判明し Retry-After が解除条件)』
- 前提: 送信失敗 handler (`main.rs:9808-9836`) は rate_limit を含む**全** error kind に対し
  `candidate.status = TaskStatus::Failed;`(line 9832) を実行したうえで `next_retry_at` を設定する
  (`task.rs:600` の `task_retry_kind` は `"rate_limit"` を `RetryErrorKind::RateLimit` へ正しく
  分類するが、分類結果は status 選択に反映されない)。
- 操作: online Adapter 呼出が rate_limit (429 相当) で失敗するタスクを実行する。
- 期待: spec は明示的に「paused **ではなく**」と否定形で rate_limit を pending 側へ位置づけるが、
  現行は paused でもなく仕様が禁じる **Failed** (第 3 の状態) に落ちる — 「paused ではない」を
  「Failed でよい」と誤読した回帰の疑いが強い。正しい実装は `status=Pending`・
  `next_retry_at=<Retry-After 由来の時刻>` を維持し、`attempts` を消費しない (max_attempts=∞、
  04§5.3) ことを確認する。

### QA4 `kio status` は paused 件数を hold_reason 別に内訳表示しない [P1]
- 正本: 10 §1 L117『`kio status` は AI 強化の進捗 (done/pending/paused 件数) と **paused の理由
  (budget/auth/tier_b_approval)** を表示する』
- 前提: `Command::Status` の JSON 構築 (`main.rs:530-567`) は `"tasks": task_store.all()...` として
  生の task 配列をそのまま返すのみで、サーバー側集計を行わない。`paused_tasks` という集計 key は
  `kio index`/`kio open` 等の**別コマンド**の出力にのみ存在し (`main.rs:841,1024,4549`)、
  `kio status` には存在せず、存在する場合も理由別内訳は持たない。
- 操作: budget/tier_b の 2 理由で paused のタスクを混在させ `kio status` を実行する。
- 期待: 応答に paused 件数の理由別内訳 (少なくとも QA1 の 3 値 enum に対応する 3 バケット) が含まれる
  こと。現行は呼出側が生の `tasks[]` 配列をクライアント側で filter するしかない。

---

## B. Tier A/B 走査承認ゲートと承認記録の保存先 (U2)

### QA5 `.kio/scope.json` に `scan_approval` key が存在しない (scope.json は 3 key のみ) [P0]
- 正本: 10 §1 L97『承認記録には...少なくとも次を残す (**保存先 = `.kio/scope.json` の
  `scan_approval` key** — schema 検証対象 §12.3。adapter 単位の network opt-in 承認 `approvals[]`
  ...とは別 key)』
- 前提: `crates/kio-core/schemas/scope.schema.json` は `additionalProperties: false` で
  `{kio_format_version, scope_id, scope_path}` の 3 key のみを許可し、`scan_approval` は
  schema にも実装 (`scope.rs:248-257` の `Repository::init` 書込み、`scope.rs:1720-1741` の
  読取り) にも存在しない (`grep -rn "scan_approval" crates/` は 0 件)。scope.json はこの 3 key から
  一切増えず (init 時に一度書かれた後は読み取り専用)。
- 操作: `kio init && kio index --approve` を実行後、`.kio/scope.json` を検査する。
- 期待: `scope.json` に `scan_approval` key (object) が追加され、`approved_at`/`actor`/
  `approval_method`/`kio_version`/`effective_ignore_hash`/`estimated_file_count`/
  `estimated_total_bytes`/`estimated_markdownize_usd`/`estimated_embedding_usd` を持つ
  (10 §1 L101-113 の列挙)。現行は `scope.json` に一切追記されない。

### QA6 スキャン承認の実データは `approvals.jsonl` に adapter 行として書かれ、scope 単位の承認と adapter 単位の opt-in が未分離 [P0]
- 正本: 10 §1 L97『(保存先 = `.kio/scope.json` の `scan_approval` key) ... adapter 単位の
  network opt-in 承認 `approvals[]` ... とは**別 key**』/ 07 §3 L169『初回スキャン承認 (10-operations.md
  §1) の記録とは別物 — あちらは scope 単位の取り込み承認、こちらは adapter 単位の network opt-in』
- 前提: 現行の `write_approval_record` (`main.rs:15257-15321`) は `.kio/approvals.jsonl` へ
  **adapter (tool_id) ごとに 1 行**を書き、各行に scan-approval 相当の field
  (`estimated_file_count`/`effective_ignore_hash`/`approved_at`/`approval_method`) を
  **重複して**埋め込む。scope 単位で 1 回だけ確定するはずの scan-approval と、adapter 単位で複数回
  起こりうる network opt-in が同一ファイルの同一行形状に畳み込まれている。
- 操作: 1 scope に対し 2 つの online Adapter (markdownize・embedding) を承認する。
- 期待: scan-approval (scope 単位、1 回) と adapter opt-in (adapter 単位、複数回あり得る) が
  独立した記録として存在し、後者の複数化が前者の重複を生まないこと。現行は `approvals.jsonl` の
  行数が adapter 数に比例して増え、scan-approval 相当の値もその都度複製される。

### QA7 [P2] `effective_ignore_hash` が built-in テンプレート内容ではなく固定リテラルのハッシュである
- 正本: 10 §1.1 L128-130『system directory...も Tier A 相当の built-in 除外に含め、OS 別の対象
  パターンは built-in template に列挙し、**その template の版を effective_ignore_hash の入力に
  含める** (パターン更新が承認記録の同一性判定に反映されるように)』
- 前提: `main.rs:15299` は `"effective_ignore_hash": hash_bytes(b"built-in-tier-a-v1")` —
  固定バイト列リテラルの hash であり、実際の Tier A/B パターンリスト内容 (`scope.rs:2709-2743`
  `is_tier_a_secret_name` のパターン集合、`scan.rs` の Tier B needle 集合) を入力にしていない。
- 操作: Tier A パターンリストに 1 パターンを追加する変更を行い (バージョン文字列リテラルは
  更新しない)、`effective_ignore_hash` を再計算する。
- 期待: パターン内容の変更が `effective_ignore_hash` の変化として現れる (パターン更新が承認記録の
  同一性判定に反映される)。現行は版文字列リテラルを手動で更新し忘れると値が変化せず、
  spec が意図する「パターン更新の検出」が構造的に保証されない。
  **[解釈割れ]**: `hash_bytes(b"built-in-tier-a-v1")` の `"v1"` サフィックス自体は「版」を表す
  意図を持つとも読めるため、これが「テンプレートの版」の充足として十分か (手動バージョン文字列で
  足りるか、パターン集合の実 hash が必要か) は spec 文言のみからは確定できない。

---

## C. Retry 予算カウンタ・tasks.jsonl 圧縮・partial の settled 化 (U3)

### QA8 `.kio/tasks.jsonl` に bounded compaction (既定 4096 行) が存在しない [P1]
- 正本: 04 §5.1 L639-645『タスクストアは `.kio/tasks.jsonl` (append-only・喪失許容)。
  **bounded compaction**: 書き込み系コマンド冒頭で行数が閾値 (既定 **4096 行**) を超えていたら、
  `.kio/.lock` 下で terminal task の行を落とし...非 terminal task は task_id ごとの最新行 1 行のみを
  ...再生成する』
- 前提: `crates/kio-pipeline/src/task.rs` は `MAX_TASK_RECORDS: usize = 100_000` の**hard reject**
  のみを持ち (`task.rs:20`、超過時は `PipelineError::corrupt` で読み込み自体を失敗させる)、
  「4096」「compaction」「bounded」のいずれの語も crates 全体で grep 0 件。
- 操作: `tasks.jsonl` に 5000 行 (terminal task の旧遷移行を含む) を書き込んだ状態で書き込み系
  コマンドを実行する。
- 期待: 冒頭で compaction が発火し、terminal task の全行が落ち、非 terminal task は最新 1 行のみへ
  再生成される (temp 完書き→fsync→atomic rename)。現行は 100,000 行に達するまで一切圧縮されず、
  達した瞬間は圧縮ではなく致命的な `KIO-E-STORE-CORRUPT-001` として読み込み自体が失敗する
  (spec が意図する「安全な自動圧縮」ではなく「無圧縮のまま突然の読み込み拒否」になる)。

### QA9 全 unit terminal な partial task の「settled」概念が存在しない [P1]
- 正本: 04 §5.2 L718-721『**partial の settled 化**: 全 unit が terminal (done/failed permanent) と
  なり再投入対象が尽きた partial task は、表示上は partial のまま **task としては terminal
  (settled) として扱う** — staging cleanup を実行し、prune-orphans の blocker からも除外する』
- 前提: `crates/kio-pipeline/src/task.rs` の `TaskStatus` enum (45-52) に `Settled` 相当の値は無く、
  `"settled"` という語も grep 0 件 (`ledger/model.rs` の `Outcome::UnknownSettled` は cost-ledger
  crash 回収の別概念であり、task 側の settled-partial とは無関係)。`task_can_complete_from_materialized_output`
  等の既存ヘルパ (`task.rs:632-642`) も all-unit-terminal 判定を持たない。
- 操作: partial task の失敗 unit が全て permanent (invalid_input 等、再投入不可) になるまで進める。
- 期待: 当該 task が (表示は partial のまま) prune-orphans の non-terminal-task blocker
  (`verify_objects.rs` `prune_orphans` の `"non_terminal_task"` 判定、PB15 に相当) から除外され、
  staging cleanup が実行される。現行は `TaskStatus::Partial` が settled かどうかを区別する機構が
  無いため、全失敗 unit が permanent 化した partial task も non-terminal 側に留まり続け、
  prune-orphans を無期限に blocking しうる。

### QA10 失敗 unit のみの retry における hints 合成規則 (added/removed=[]・N=失敗 unit 集合) が明文化された実装として存在しない [P1]
- 正本: 04 §5.2 L705-711『合成 hints の残余 field は `added_unit_keys = []`・
  `removed_unit_keys = []` と定める...この再投入の受け入れ検査 (§3.2) では **N = 合成した hints の
  集合 (= 失敗 unit のみ)**...合成 hints に対する §2.2 の unchanged 候補集合は空であり、V1 の
  完全一致は `unchanged_unit_keys = []` として評価する』
- 前提: `crates/kio-cli/src/main.rs` を `retry.*hint|synthesiz.*hint` で grep しても専用の合成関数は
  見つからず、`validate_markdownize_response` (`markdownize.rs:336-390`) は常に呼出元が渡す
  `prepared_units`/`hints` をそのまま母集合として使う汎用関数であり、「partial retry 時は N を
  失敗 unit 集合に限定する」という特別な合成ロジックの有無は本関数からは判別できない。
- 操作: 3 unit 中 1 unit が failed permanent 以外の理由で失敗した partial task を、
  `incremental_update` を持つ Adapter で retry する。
- 期待: 合成される `hints.changed_unit_keys` = 失敗 unit のキーのみ、`added_unit_keys`/
  `removed_unit_keys` は空配列、受け入れ検査の母集合 N も失敗 unit のみに縮小され、
  既 done の 2 unit は応答への再掲を要求されない。この合成規則がどこにも実装されていないか、
  実装されているが本節の規則と異なるかを実機で確定する必要がある。
  **[解釈割れ]**: 現状コードから「合成ロジックが存在しないため通常の full/incremental 母集合に
  縮退している」のか「別名の既存関数がこの規則を満たしている」のかを、spec の記述のみからは
  断定できない (grep だけでは実装の有無を機械的に確定できない領域)。

---

## D. Budget guardrail — folder 層 per_adapter の残存 (U4 残り)

> `check_then_reserve` (Tx 本体) は Phase 1 実装済み・CL56-61 が正本。本節は folder 層
> `per_adapter` が「定義しない」対象であるにも関わらず config パース・enqueue 時事前チェック・
> `kio status` 表示の 3 箇所に残存している現状を扱う。

### QA11 enqueue 時事前チェックと `kio status` 表示が folder 層 per_adapter を依然として参照する [P0]
- 正本: 04 §5.4 L768『`per_adapter` の下限は **device 層専用** (folder cap は total のみ —
  **folder 側 `[budget.per_adapter]` は定義しない**) で、第三条件として同様に判定する:
  `ledger(device, adapter_kind, 当月) + candidate < per_adapter_cap(adapter_kind)`』
- 前提: `crates/kio-pipeline/src/ledger/ops.rs` の `BudgetCapConfig`
  (`device_cap`/`folder_cap`/`device_per_adapter_cap` の 3 field のみ、1352-1359) と
  `check_then_reserve` (1409-1446) は folder per_adapter を参照する field/分岐を一切持たない
  (真の Tx-atomic gate は spec どおり)。しかし **その手前**の enqueue 時事前チェック
  `budget_remaining_for_adapter` (`main.rs:14703-14730`、line 14726:
  `if let Some(adapter_cap) = budget_caps.folder_per_adapter.get(adapter_kind) { ... }`) は
  folder per_adapter を read し remaining budget を狭める側に反映し、`kio status` の budget JSON
  (`main.rs:12683`: `"folder_per_adapter": caps.folder_per_adapter`) はこれをそのまま表示する。
- 操作: `.kio/config.toml` (folder) に `[budget.per_adapter] markdownize = 1.0` を設定し、
  device/folder 総額 cap には十分な残余がある状態でタスクを enqueue する。
- 期待: folder 層に per_adapter という概念が存在しない以上、この設定はタスクの起動可否に一切
  影響しないべきである。現行は enqueue 時事前チェックが folder per_adapter で remaining を
  縮小するため、**真の Tx-atomic gate (`check_then_reserve`) では起動できるはずのタスクが、
  事前チェック段階で `paused(budget_exceeded)` に落ちる**不整合を再現できる (2 つの budget 判定
  経路が異なる結論を出す)。`kio status` の `folder_per_adapter` 表示も、存在しないはずの制約を
  ユーザーに提示してしまう。

### QA12 config schema が folder `.kio/config.toml` の `[budget.per_adapter]` を拒否しない [P1]
- 正本: 04 §5.4 L768『folder 側 `[budget.per_adapter]` は定義しない』
- 前提: `crates/kio-core/schemas/config.schema.json` の `budget.per_adapter`
  (schema.json:80-83) は device/folder 両方の config.toml に共通の 1 schema として適用され、
  folder ファイルに対する特別な拒否規則を持たない。`crates/kio-pipeline/src/budget.rs`
  `read_budget_config` (192-266) も device/folder いずれの path に対しても同一のパース・
  検証ロジック (`is_valid_per_adapter_key` による enum 検証のみ) を適用し、「folder では
  この section 自体を禁止する」という file-role 別の分岐を持たない。
- 操作: `.kio/config.toml` (folder 側) に `[budget.per_adapter] embedding = 5.0` を書いて
  scope config を読み込ませる。
- 期待: **[解釈割れ]** spec の「folder 側は定義しない」を (a) schema レベルで folder config への
  この key の記述自体を `KIO-E-CONFIG-SCHEMA-001` で拒否すべき、と読むか、(b) 記述は許容し
  単に判定に使わない (QA11 の是正のみで足りる) と読むかは、本節の文言のみからは一意に決まらない。
  本契約は (a) の解釈を暫定採用し「folder config の `[budget.per_adapter]` は schema error」を
  期待とするが、確定は実装時の裁定を要する。

---

## E. LLM API idempotency 二段階 (U11) と cost-ledger バックアップ・復元後 reconcile (U12)

### QA13 sync 呼出の Adapter 層に provider idempotency key 要求機構が存在しない [P1]
- 正本: 04 §5.5 L880『LLM API の二重課金防止は二段構え: **sync 呼出は provider が idempotency key を
  提供する場合にそれを要求し**、Batch 投入は §5.8 の 2 相プロトコルを正本とする』(CL41 が
  「要求されることの事実確認」を既契約化、実装詳細は本書へ委譲— 対象外リスト参照)
- 前提: `crates/kio-adapter/src/` を `idempotency` (大小無視) で grep すると 0 件。sync 呼出を行う
  唯一の実装 (`gemini_embedding.rs` の `GeminiEmbeddingClient::embed`) は `ureq` ベースの単純な
  POST 呼出であり、HTTP header や request body に idempotency key 相当のフィールドを一切含めない。
  provider (Vertex AI) が idempotency key を提供するかどうかの宣言・判定機構も存在しない。
- 操作: sync 呼出対応の Embedding Adapter を実行する。
- 期待: provider が idempotency key を提供する場合はそれを要求・送信し (Adapter 契約レベルで
  必須化)、提供しない場合は §5.4 の縮退 2 相 (batch_requests 行ベースの記帳冪等性) のみで
  二重課金を防止する — Adapter 層への idempotency_key 一律要求はしない、という条件分岐が
  存在すること。現行は分岐そのものが無く、常に「provider idempotency key 不使用」の状態と
  等価である。**混同注意**: `crate::kio_pipeline::task::idempotency_key`
  (`task.rs:932-934`, `input_hash`+`tool_profile_hash` の sha256) は task/run の重複排除用の
  別概念であり (実際の dedup は `TaskKey`/`LedgerTaskKey` が担い、この関数自体は本番コードから
  呼ばれない死んだヘルパ)、本契約の provider-side idempotency key とは無関係。

### QA14 cost-ledger.sqlite のバックアップ手順・復元後 integrity_check が存在しない [P1]
- 正本: 10 §7.5.2 (統合要約より、U12)『デバイスグローバルな cost-ledger.sqlite は `.kio` コピーに
  含まれないため `sqlite3 ... .backup` による別バックアップ手順が必要...復元後は
  `PRAGMA integrity_check` + 両表存在確認...§5.8 の回復 (reconcile) 完了まで新規 Batch 投入禁止』
- 前提: `crates/` 全体を `\.backup|integrity_check|PRAGMA integrity` で grep すると 0 件。
  `cost-ledger.sqlite` 自体は Phase 1 で実装済みだが (`crates/kio-pipeline/src/ledger/schema.rs`)、
  バックアップ手順・復元検知・「復元後は新規 Batch 投入禁止」というガードは Kio 側のコード・
  ドキュメント (docs/10-operations.md への文言記載のみ) いずれにも実行可能な形で存在しない。
- 操作: `cost-ledger.sqlite` を手動バックアップ→破損させる→バックアップから復元する、という手順を
  実行した状態で `kio batch resume` 等の書き込み系コマンドを実行する。
- 期待: Kio 側に復元検知の仕組みが無い以上、復元されたファイルは無条件に通常どおり扱われる
  (「復元後は reconcile 完了まで新規投入禁止」という安全策が機能しない状態を再現できる)。
  この契約は現状「安全策皆無」であることの固定であり、実装が復元検知手段 (例: 起動時
  `PRAGMA integrity_check` の常時実行、または明示 `kio ledger reconcile` コマンドの新設) を
  持つべきという要求を含む。

### QA15 復元後の orphan job 判定 (provider_scope 全走査 + task key 4 組帰属判定) が存在しない [P1]
- 正本: 10 §7.5.2 (統合要約より)『復元 DB が投入記録を欠く場合、provider_scope 全走査で
  batch_requests に対応行の無い job/upload を検出し task key 4 組で帰属判定、ローカル構成 scope に
  一致する job は orphan 候補として報告 (結果取得・削除を案内)、一致しない job は unknown として
  報告のみ (自動再投入・自動削除はしない)』
- 前提: `crates/kio-pipeline/src/ledger/ops.rs` の crash 回収 (`recovery_candidates`/
  `recovery_mark_found`/`recovery_settle_unknown`) は**既存の `batch_requests` 行**を起点に
  found/confirmed-absent/unknown を判定する仕組みであり (§Z 参照)、「provider 側の job 一覧を
  全走査し、ローカル `batch_requests` に対応行が**存在しない** job を発見する」という逆方向の
  照合 (orphan 検出) は行わない。この逆方向照合は復元 DB の欠落シナリオ専用であり、
  Batch 実行契約 trait 自体が不在 (§O) のため job 一覧取得の手段もない。
- 操作: cost-ledger.sqlite を「投入記録を一部欠く」状態 (例: 古いバックアップ) から復元し、
  書き込み系コマンドを実行する。
- 期待: provider 上に存在するが `batch_requests` に対応行が無い job を検出し、ローカル構成 scope に
  帰属するものは orphan 候補として報告 (自動処理はしない)。現行はこの検出経路自体が存在しないため
  無応答 (何も報告されない) になることを固定し、実装時の新設対象であることを明示する。

---

## F. AdapterRun/AdapterProfile 応答 schema の拡張 (U78)

### QA16 `AdapterRun` が単一 `error_kind` のみで `error_code`/`error_category`/`retry_after_ms` を持たない [P0]
- 正本: 07 §4 L278-290『AdapterRun: task_id / input_hashes / output_hashes / status /
  **error_code** (機械判定用) / **error_category** (transient\|permanent\|rate_limit — 04§5.3の
  retry分類の入力) / **retry_after_ms** (optional — provider の Retry-After を透過)』
- 前提: `crates/kio-adapter/src/types.rs:48-55` の `AdapterRun` は
  `{task_id, input_hashes, output_hashes, status, error_kind: Option<String>}` の 5 field のみ。
  `error_code`/`error_category`/`retry_after_ms` は crates/kio-adapter/src/ 全体で grep 0 件。
- 操作: online Adapter 呼出が transient エラー (429 相当、Retry-After ヘッダ付き) で失敗する。
- 期待: `AdapterRun` に `error_code` (機械判定文字列) と `error_category="rate_limit"`、
  `retry_after_ms=<Retry-After 由来のミリ秒>` が個別 field として現れる。現行は単一の
  自由記述 `error_kind: Option<String>` にしか情報が乗らず、機械判定用コードとリトライ分類の
  粗分類が構造的に分離されていない。

### QA17 `usage` (one-of usd\|billable_units) が AdapterRun に存在せず、billable terminal 応答での必須化がない [P0]
- 正本: 07 §4 L291-307『usage one-of { usd } \| { billable_units } — request 単位の課金報告...
  **billable な terminal 応答...で必須** — 欠落・不正値は estimated 記帳へ縮退する』
- 前提: `usage`/`billable_units`/`usd` (課金 field として) は `crates/kio-adapter/src/` 全体で
  grep 0 件。`AdapterRun`/`AdapterProfile` いずれにもこの構造が無い。
- 操作: billable な online Adapter が成功終端する。
- 期待: 応答に `usage` (usd 実測額、または pages/tokens_in/tokens_out 等の kind 別 count 配列) が
  含まれ、欠落時は Kio 側が estimated 縮退で吸収する。現行はこの field 自体が存在しないため、
  課金額は `AdapterRun` からは一切取得できない (§D/§O とも接続する構造的欠落)。

### QA18 `AdapterProfile` に `billable_kinds`/`reject_billing` が存在しない [P0]
- 正本: 07 §4 L264-275『billable_kinds billable を宣言する Adapter (§5.7 条件6) は必須...
  reject_billing billable を宣言する Adapter (§5.7 条件6) は必須 — "billable"\|"nonbillable" の
  閉 enum』
- 前提: `crates/kio-adapter/src/types.rs:37-46` の `AdapterProfile` は
  `{adapter_kind, adapter_id, execution_mode, tool_profile_hash, version, capability_flags,
  allow_network}` の 7 field のみ。`billable_kinds`/`reject_billing` は crates 全体で grep 0 件。
- 操作: billable を宣言する online Adapter (Markdownize/Embedding) の profile を構築する。
- 期待: `billable_kinds` (報告し得る `billable_units.kind` の閉集合) と `reject_billing`
  ("billable"\|"nonbillable") が profile に含まれ、送信前の pricing 被覆検査 (下記 QA19) の
  入力になる。現行はいずれの field も存在しない。

### QA19 tools.toml の `[pricing]` 単価表が実装にまったく存在しない (grep 0 件) [P0]
- 正本: 07 §4 L298-300『単価解決元 = tools.toml の `[pricing]` 単価表 (kind → USD 単価...
  **単価の正本は tools.toml** — tool-lock ではない)』/ 03 §11 L832-837 (`[markdown.
  mistral_ocr_markdownize.pricing] pages = 0.004` の TOML 例) / 04-pipeline.md §5.1
  L53『コスト概算は、現行 `tools.toml` の `[pricing]` 単価表...×推定ページ数/トークン数から算出する』
- 前提: `"pricing"` を `crates/kio-adapter/src/tool_lock.rs` と `crates/kio-cli/src/main.rs` で
  grep すると **0 件**。`tool_lock.rs` の `TOOLS_ENTRY_FIELDS` (121-134、tools.toml の adapter
  entry に許可される field の閉リスト) にも `"pricing"` は含まれない — 現行の strict schema
  validation (R13-2, "unknown 型を全て拒否") の下では、spec 例の
  `[markdown.mistral_ocr_markdownize.pricing]` ネストテーブルを含む tools.toml は
  **未知 field として拒否されるか、単に無視される**可能性が高い。
- 操作: `~/.config/kio/tools.toml` に 03§11 の例のとおり `[markdown.mistral_ocr_markdownize.pricing]
  pages = 0.004` を設定し、`kio index --preview` (コスト概算) または billable 応答の USD 換算を
  実行する。
- 期待: pricing 単価表が読み込まれ、billable_units の USD 換算・preview のコスト概算に使われる。
  現行はこの節自体が実装に存在しないため、単価はどこからも解決されない (tool-lock 側にも
  単価は無いため、現状は「単価を一切持たない」状態)。

### QA20 `max_input_bytes` の適用単位が AdapterRun 1 回か task 全体かを判別する検査が存在しない [P1]
- 正本: 07 §7.1 L654-657『max_input_bytes は **AdapterRun 1 回の入力 (prepared input の
  canonical bytes 合計)** に適用する...task 全体の総量上限ではない — 超過は送信前に当該 task を
  terminal failed (invalid_input・非再試行) とし、送信しない (課金なし)』
- 前提: `[adapter.policy] max_input_bytes` は `config.schema.json:139` に存在するが、この値を
  実際に「1 AdapterRun (= 1 request/job) の入力バイト数」と照合して送信前に拒否する検査コードの
  有無は、本書の直接調査範囲では確認できていない (`crates/kio-cli/src/main.rs` の送信経路の
  該当箇所は他ドメイン (§K/§M) の調査で手一杯だった)。
- 操作: `max_input_bytes` を小さく設定し、1 request が超過する入力 (例: 1 unit が巨大) と、
  task 全体 (複数 unit の合計) では超過するが個々の request は超過しない入力の 2 パターンを用意する。
- 期待: 前者は送信前に `invalid_input`・非再試行で terminal failed になる。後者は (spec が
  「task 全体の総量上限ではない」と明記する以上) 単体の request 超過ではないため通常どおり送信される
  べきだが、現行がどちらの粒度で判定しているかは実機検証を要する。
  **[解釈割れ]**: 現行実装の有無・粒度は grep のみからは確定できない — 実装着手前に既存コードの
  該当箇所を精読して現状を確定する必要がある。

---

## G. online opt-in の AND ゲート成立条件と承認記録 schema (U79)

### QA21 送信 gate が AND ではなく OR — config bool 単独 (`allow_network=true`) だけで送信可能 [P0]
- 正本: 07 §3 L101-105『成立: (a) 初回スキャン承認フローで...**承認の成立 = approvals[] 行の
  materialize と、同一承認操作での scope config `allow_network=true` の設定の両方 (AND)** —
  行だけでは送信が有効にならない』
- 前提: `persistent_network_allowed_for_kio_dir` (`main.rs:9880-9890`) は
  `if network_revoked_kio_dir(...)? { return Ok(false); }` の次に
  `if read_allow_network_config(&user_config_toml_path())? == Some(true) { return Ok(true); }`
  を評価し、**config bool が true なら承認行の有無を確認せず即座に true を返す** — 行 (下記 QA22
  の `consents.jsonl`) の存在確認は config bool が false または未設定の場合のフォールバックとして
  しか呼ばれない (`approval_row_present_in_kio_dir`)。
- 操作: 承認行を一切 materialize せず (対話承認も `--approve` も未実行)、`~/.config/kio/config.toml`
  (または `.kio/config.toml`) の `allow_network` を手編集で `true` に設定した状態で online
  markdownize/embedding タスクを起動する。
- 期待: 「承認の成立 = 行 materialize と boolean 設定の両方 (AND)」である以上、行が存在しない状態
  では boolean が true でも送信は成立しない (例外は初回 materialize — 未消費の場合のみ許容)。
  現行は boolean 単独で送信が成立する (OR 相当) ため、手編集した config だけでオンライン送信が
  始まることを再現できる。

### QA22 承認状態の永続化先が `.kio/scope.json` の `approvals[]` ではなく device-global `consents.jsonl` [P0]
- 正本: 07 §3 L151-152『**保存先 = `.kio/scope.json` の `approvals[]` 配列** (schema 検証対象
  10§12.3、truth 03§4.1)』
- 前提: 実際の gate 判定 (`trusted_consent_present`) が参照する永続データは
  `data_home().join("kio/consents.jsonl")` (`main.rs:14927-14928`) — **device-global** な
  単一ファイルであり、行は `{schema_version, scope_id, canonical_root, tool_id, operation,
  granted_at, kio_version}` の形状 (`.kio/scope.json` ではない)。`.kio/scope.json` に
  `approvals` property は存在せず (`scope.schema.json` の `additionalProperties:false` で
  3 key のみ)、これとは別に scope-local `<kio_dir>/approvals.jsonl` も存在するが、これは
  監査ログ専用で gate 判定には使われない (`scope.rs:348-349` のコメントが明記: "portable audit
  data, not active consent")。
- 操作: 同一 scope_id を持つ 2 つの `.kio` clone (fork 複製) を用意し、一方でのみ承認を成立させる。
- 期待: spec は承認記録を `.kio/scope.json` に置くことで **scope (フォルダ) ごと**に承認状態が
  独立することを前提にしている。現行の `consents.jsonl` は `(scope_id, canonical_root)` の組を
  key にしているため類似の独立性は持つが、正本の保存場所・データ形状が spec と根本的に異なり、
  `.kio` を丸ごとコピー (`03-data-model.md §4.1` の truth 定義上、`.kio` が正本であるべき) しても
  承認状態が付いてこない (device-global ファイルは export/import・別デバイスへの `.kio` 移動で
  再現されない) という副作用を生む。

### QA23 承認行に `execution_mode`/`tool_profile_hash` の記録が無く、profile 変更時の失効判定ができない [P1]
- 正本: 07 §3 L148-150,164-168『承認記録に scope_id/tool_id/**execution_mode/tool_profile_hash
  (承認時点)**/approved_at/approval_method を残す。送信前に現在の execution_mode/profile と照合し、
  不一致 = 失効 (再承認要求)』/ L164『`approvals[]` 要素の required field = scope_id/tool_id/
  execution_mode/tool_profile_hash/approved_at/approval_method/status』
- 前提: `consents.jsonl` の行形状 (`main.rs:15014-15022`)
  `{schema_version, scope_id, canonical_root, tool_id, operation, granted_at, kio_version}` には
  `execution_mode`/`tool_profile_hash`/`status` が存在しない。
- 操作: online Adapter 承認後に `[markdownize].bbox_annotation` を切り替え (tool_profile_hash が
  変わる設定変更、07§3 L114-116 の明記どおり) てから online 送信を試みる。
- 期待: profile 変更により承認が失効し、再承認 (対話/`--approve`) が要求される。現行は
  `consents.jsonl` が profile 情報を記録しないため、profile が変わっても既存の承認行がそのまま
  有効であり続ける (失効判定が構造的に不可能)。

### QA24 単一 Adapter revoke に必要な `status=active|revoked` 状態遷移が承認記録に存在しない [P1]
- 正本: 07 §3 L164-168『required field ... **status (`active`\|`revoked`)** — status=revoked の
  行は revoked_at も必須』
- 前提: `consents.jsonl` の行は追記専用の許可ログであり (grant のみ、revoke に対応する行の
  status 更新や `revoked_at` field は存在しない)、`network_revoked_kio_dir`
  (`main.rs:14820-14825`) は revoke を `config.toml` の `allow_network=false` **のみ**で表現する
  scope 全体のkill switch であり、単一 Adapter 単位の revoke 状態は記録も判定もされない。
- 操作: 2 つの online Adapter (markdownize・embedding) を承認済みの scope で、markdownize のみを
  revoke する (§H の `kio adapter revoke` 相当操作、現状は未実装のため代替手段が無い)。
- 期待: markdownize の承認行が `status=revoked`・`revoked_at` 付きで更新され、embedding の承認・
  `allow_network` boolean は変化しない。現行はこの粒度の revoke を表現する記録形式自体が
  存在しない (§H の `kio adapter revoke` 未実装と表裏)。

---

## H. 承認失効条件の拡張と単一 Adapter revoke 機構 (U80)

### QA25 `kio adapter revoke` コマンドが存在しない (トップレベル `Adapter` subcommand 皆無) [P0]
- 正本: 06 §1 L31-43『kio adapter revoke (\<tool_id\> \| --all) # Adapter の network 承認取り消し
  (相互排他)』/ 07 §3 L136-137『単一 Adapter revoke の実行主体 = `kio adapter revoke <tool_id>`』
- 前提: `crates/kio-cli/src/main.rs:152-193` の `enum Command` (18 variant: Init/Status/Snapshot/
  Log/Diff/Inspect/Tag/Index/Batch/Repair/Search/Open/View/Restore/Gc/Purge/Reindex/Move/Evidence)
  に `Adapter` variant は存在しない (`grep -rn '"revoke"|AdapterRevoke|adapter revoke'` は
  main.rs:10855 の docstring 内言及 1 件のみで実装なし)。現行の唯一の revoke 相当機構は
  `kio index --revoke-network` (`IndexArgs.revoke_network: bool`, `main.rs:259`,
  `write_network_revoke_record` 呼出) — **scope 全体の kill switch のみ**で単一 Adapter 粒度を
  持たない。
- 操作: `kio adapter revoke mistral_ocr_markdownize` を実行する。
- 期待: 新設の `Command::Adapter(AdapterArgs)` subcommand が存在し、`revoke <tool_id>`・
  `revoke --all` を受理する。現行は該当 subcommand が clap レベルで存在しないため usage error に
  なる。

### QA26 `KIO-E-ADAPTER-APPROVAL-CONFLICT-001` が存在しない (revoke publish 直前 CAS 競合検出なし) [P0]
- 正本: 07 §3 L138-142『承認側の行 publish・self-heal も同じ lock 下で行い、**publish の直前に
  approval_pending の存在を再検証する** (CAS)...明示承認コマンドはこの再検証の不一致を
  **明示エラー (KIO-E-ADAPTER-APPROVAL-CONFLICT-001 / exit 5)** で終端する』
- 前提: `grep -rn "KIO-E-ADAPTER-APPROVAL-CONFLICT-001" crates/` は 0 件。現行の `KIO-E-ADAPTER-`
  namespace には `AUTH-001`(`main.rs:444`)・`CONTRACT-001`(`task.rs:918`等)・
  `TOOLS-PERM-001`(`main.rs:15422`) の 3 code のみが存在し、4 つ目の APPROVAL-CONFLICT-001 は
  未定義 (承認/`approval_pending` の概念自体が §G のとおり不在のため、この CAS 競合状態を検出する
  対象データも存在しない)。
- 操作: 対話承認 (publish 直前) と並行して別プロセスから `kio adapter revoke` を実行し、
  対象の `approval_pending` を除去させる。
- 期待: 承認コマンド側が publish 直前の再検証で不一致を検知し、`KIO-E-ADAPTER-APPROVAL-CONFLICT-001`
  (exit 5) で終端する (無音の no-op 成功にしない)。現行は `approval_pending` という中間状態自体が
  無いため、この競合シナリオ自体を構成できない。

### QA27 単一 Adapter revoke の 4 組不問 pending 除去・`approvals_initialized` marker 消費規則が存在しない [P1]
- 正本: 07 §3 L120-134『**単一 Adapter だけの revoke** は approvals[] 当該行の status=revoked +
  revoked_at への更新で行う...revoke は単一 Adapter では同一 (scope_id, tool_id) の
  `approval_pending` を execution_mode/tool_profile_hash **不問**で同一 atomic write 除去...
  revoke が...行った場合、`approvals_initialized` marker が無ければ同一 atomic write で
  `approvals_initialized: true` を記録する』
- 前提: `approval_pending`/`approvals_initialized` は §G QA22-24 のとおり概念として不在
  (scope.schema.json に property が無い)。したがって「4 組不問で pending を除去」「marker を
  同一 atomic write で true 化」という規則を実装する対象データがそもそも存在しない。
- 操作: profile 変更で失効した pending 承認 (旧 execution_mode/tool_profile_hash) が残る状態で
  `kio adapter revoke <tool_id>` を実行する。
- 期待: 4 組完全一致ではなく `(scope_id, tool_id)` のみで pending を除去し、同一 atomic write で
  `approvals_initialized` marker を true 化する。§G の schema/データ構造が新設されない限り、
  本契約は検証不能である (§G→§H の依存関係を明示する)。

---

## I. `--online`/`--offline` の適用範囲拡大 (U81)

### QA28 [regression-lock] `kio index`/`kio search` は既に `--online`/`--offline` を持ち、明示 revoke が `--online` に優先する [P1]
- 正本: 07 §3 L237-239『この優先で `--online` が上書きできるのは opt-in 未成立の既定閉鎖である。
  **明示 revoke (`allow_network = false` の明示設定) は `--online` より優先する** (kill switch の
  趣旨)』/ 06 §1 L16-25 (`kio index [--online|--offline]`)
- 前提: `IndexArgs` (`main.rs:246-267`, `online`/`offline` field) と `ParsedSearch`
  (`main.rs:912-934`, 手動 parse `parse_search_args`) は既に配線済み。優先順位は
  `embedding_online_allowed` (`main.rs:9945-9973`) が実装する:
  `if online { if network_revoked(repo)? { return Ok(false); } ... }` — **`--online` 指定時も
  まず revoke を確認し、revoke 済みなら false を返す**。
- 操作: scope を明示 revoke (`allow_network=false`) した状態で `kio search --vector --online` を
  実行する。
- 期待: revoke が優先し、`--online` は無効なまま (text fallback または `--vector` 明示時は
  error)。現行実装はこの優先順位を正しく満たしている — 本契約は regression-lock として固定し、
  以後の変更でこの優先順位が崩れないようにする。**混同注意**: 以下 QA29-31 は
  `--online`/`--offline` が**未配線**の他コマンドを扱う (この優先順位ロジック自体の欠陥ではない)。

### QA29 `kio repair --rebuild-db` に `--online`/`--offline` が配線されていない (docstring は誤って配線済みと主張) [P0]
- 正本: 06 §1 L52-55『kio repair (--rebuild-db [--online\|--offline] \| ...)...--rebuild-db は
  rebuild 後に enrichment を駆動し得るため online/offline 上書きの対象』
- 前提: `parse_repair_args` (`main.rs:1049-, RepairMode` enum 1034-1045) は `--rebuild-db`・
  `--verify-objects`・`--prune-orphans`・`--registry-prune`・`--yes` のみを認識し、
  `--online`/`--offline` を渡すと `main.rs:1107-1110` の unknown-flag 分岐に落ちてエラーになる。
  興味深いことに `main.rs:1047` 付近には「`kio repair` accepts exactly one of
  `--rebuild-db [--online|--offline]`...」という**現状と矛盾する docstring** が存在する
  (実装が追いついていない stale なコメント)。
- 操作: `kio repair --rebuild-db --online` を実行する。
- 期待: rebuild 後の enrichment (§5.4) がこの実行に限り online opt-in される。現行は
  unknown flag エラーになり、rebuild 後の enrichment は既存の永続 opt-in 状態にのみ従う
  (一時上書きができない)。

### QA30 `kio batch resume`/`kio batch retry` に `--online`/`--offline` が配線されておらず、常時 offline=false/online=false で実行される [P0]
- 正本: 06 §1 L21-30『kio batch resume [--override-budget] [--online\|--offline] ... kio batch
  retry [--online\|--offline] [--reset-violations <selector>]』
- 前提: `ResumeArgs` (`main.rs:284-288`, `override_budget` のみ)・`RetryArgs`
  (`main.rs:290-296`, `reset_violations` のみ) いずれにも online/offline field が無い。
  実行経路 `execute_pending_tasks` (`main.rs:9509-9553`) は
  `embedding_online_allowed(repo, false, false, false)` (line 9546) を**ハードコード**しており、
  resume/retry からは一時 opt-in が原理的に不可能 (永続承認状態のみに従う)。
- 操作: 永続 opt-in が未成立の scope で `kio batch resume --online` を実行する。
- 期待: 当該実行に限り online 送信が opt-in される。現行は `--online` という引数自体を受理せず
  (usage error)、受理できたとしても実行経路がハードコードされた false を渡すため無効化される。

### QA31 `kio reindex --force`/`--at` に `--online`/`--offline` が配線されていない [P1]
- 正本: 07 §3 L220-222『適用対象は online 作業を駆動し得る全コマンド (`kio index` / `kio batch
  resume` / `kio batch retry` / `kio reindex` — `--force` / `--at <commit>` のいずれも online
  embedding を駆動し得る...)』
- 前提: `ParsedReindex` (`crates/kio-cli/src/historical_reindex.rs:10-15`,
  `{force, yes, at}` のみ) に online/offline field が無く、embedding enrichment パス
  (`historical_reindex.rs:437`) も `embedding_online_allowed(repo, false, false, false)` を
  ハードコードする。
- 操作: `kio reindex --force --online` を実行する。
- 期待: reindex が駆動する embedding enrichment に一時 online opt-in が適用される。現行は
  引数自体が存在せず、常に永続承認状態のみに従う。

---

## J. bbox_annotation の identity 畳み込み・render_params・tool_lock_hash (U83/U84)

### QA32 [regression-lock] bbox_annotation の on/off は `output_schema`/`prompt_template_*` の差分経由で `tool_profile_hash` に間接的に畳み込まれている [P1]
- 正本: 07 §5.2 L370『値は出力に影響するため **tool_profile_hash に畳み込む** = 切替は世代判定に
  乗る』/ 03 §5.1 L357-359『bbox_annotation markdownize 専用: boolean — ... 実効値を採用時に
  畳み込む』
- 前提: `crates/kio-adapter/src/identity.rs` の `PROFILE_FIELDS` (9-23) には文字どおりの
  `"bbox_annotation"` key は含まれない。しかし `mistral_markdownize_profile(pin, enabled)`
  (`bbox_annotation.rs:53-77`) は `enabled` に応じて `output_schema`
  (`"kio-markdown+bbox-annotation-v1"` vs `"kio-markdown-v1"`) と `prompt_template_hash`/
  `prompt_template_id` の有無を変え、これらは全て `PROFILE_FIELDS` に含まれるため、結果として
  `identity::tool_profile_hash` の出力は enabled/disabled で異なる。
- 操作: 同一 `model_version_pin` で `enabled=true`/`enabled=false` の 2 profile から
  `tool_profile_hash` を計算する。
- 期待: 2 つの hash が異なる (切替が世代判定に乗る)。現行実装はこの帰結を機能的に満たしている —
  regression-lock として固定する。**[解釈割れ]**: この「間接畳み込み」方式が 03§5.1 の
  「hash 対象フィールド」列挙 (`bbox_annotation` を明示の 1 field として列挙) の要求を字面どおり
  満たすかは見解が分かれる — 挙動 (hash が変わること) は満たすが、同じ仕組みを他の boolean 設定に
  再利用する場合は都度 `output_schema` 等を変える設計が必要になり、汎用的な「boolean field を
  そのまま列挙に加える」設計ではない。

### QA33 config.schema.json の `markdownize.bbox_annotation` がネスト object 形状で、spec の平坦 key 例と一致しない [P2]
- 正本: 07 §5.2 L370『`.kio/config.toml` の **`[markdownize] bbox_annotation = true`** (既定) で
  制御』(平坦 TOML key の文字どおりの例)
- 前提: `crates/kio-core/schemas/config.schema.json:121-127` は
  `markdownize.bbox_annotation: {type: object, properties: {enabled: boolean}}` — 実際の TOML は
  `[markdownize.bbox_annotation]\nenabled = true` という**ネストテーブル**形状が必要であり、
  spec の文字どおりの例 `[markdownize]\nbbox_annotation = true` (平坦 boolean key) とは異なる。
- 操作: spec の例のとおり `[markdownize]\nbbox_annotation = true` を書いた config.toml を
  schema 検証する。
- 期待: **[解釈割れ]** spec の TOML 例が正本なら現行 schema はこれを型不一致 (object 期待に
  boolean が来る) で拒否するはずで、これは spec 例との不一致である。一方、07§5.2 の例示は
  「folder-config schema の正式 key」という要求の**例示**であり、ネスト形状自体を厳密に禁じる
  意図かは断定できない。本契約は「現行 schema が spec の literal TOML 例を受理しない」という
  事実を固定するに留め、どちらの形状を正とするかは実装時の裁定を要する。

### QA34 `render_params` (prepare 専用 hash 入力) が identity 計算に一切存在しない [P0]
- 正本: 03 §5.1 L355-356『render_params prepare 専用: {renderer_name, renderer_version, dpi,
  color_space, output_format} (バイト列決定性に影響する全レンダリング設定 — 04-pipeline.md
  §2.1)』/ 04 §2.1 L167-171『prepared のレンダリングパラメータ (renderer 名/version/DPI/色空間/
  出力フォーマット) は prepare Adapter の tool_profile に含め、同一入力ページ×同一 profile の
  レンダリングはバイト安定であることを prepare Adapter の**採用要件**とする』(2026-07-03 確定、
  猶予のない正規要件)
- 前提: `render_params`/`renderer_name`/`renderer_version`/`dpi`/`color_space` は
  `crates/kio-adapter/src/` 全体・crates 全体で grep 0 件。`PROFILE_FIELDS`
  (`identity.rs:9-23`) にも該当 field は無く、`PrepareToolLockEntry`
  (`tool_lock.rs:21-27`) も `tool_id`/`profile_hash`/`kind` の 3 field のみで render 関連情報を
  持たない。
- 操作: prepare Adapter の profile (PDF → page image のような将来のレンダリング系 Adapter を
  想定) の tool_profile_hash を計算する。
- 期待: `render_params` が hash 入力に含まれ、renderer 設定の変更が prepared_hash の世代判定
  (04§2.1) に反映される。現行はこの機構が丸ごと存在しない。**現行の同梱 Prepare Adapter
  (`crates/kio-pipeline/src/prepare.rs`) はページ画像レンダリングを行わない (PDF text layer 抽出の
  み) ため今日時点で実害は顕在化しないが、spec は 2026-07-03 に猶予なく確定した「採用要件」と
  明記しており、レンダリング系 Adapter が採用される前に schema/計算規約として先行整備すべき対象**
  であることを本契約は固定する。

### QA35 [regression-lock] `tool_lock_hash` は tool-lock.json 全体ではなく role 別 canonical 入力 (tool_id+profile_hash、embedding のみ +dimensions/distance/modality) のみを畳み込む [P0]
- 正本: 07 §6 L587『`tool_lock_hash` は...**tool-lock.json 全体ではない**』/ 03 §5.2 L396-405
  (JCS canonical 構造: 各 role `{tool_id, profile_hash}`、embedding のみ `+dimensions+distance+
  modality`)
- 前提: `canonical_tool_lock_value` (`tool_lock.rs:70-96`) → `canonical_simple_entry`
  (`tool_lock.rs:384-`, prepare/markdown/summary/classification/rerank に適用、
  `tool_id`+`profile_hash` のみ抽出) / `canonical_embedding_entry`
  (`tool_lock.rs:406-`, 上記 5 field 抽出) — `kind`/`capabilities`/`mode` はいずれの entry
  構造体 (`PrepareToolLockEntry`/`MarkdownToolLockEntry`/`EmbeddingToolLockEntry`) にも
  フィールドとして存在するが、`canonical` Map への挿入対象からは明示的に除外されている。
- 操作: 同一 tool_id/profile_hash だが `capabilities` (markdown role) または `mode`
  (embedding role) のみが異なる 2 つの tool-lock.json から `tool_lock_hash` を計算する。
- 期待: 2 つの hash が一致する (`kind`/`capabilities`/`mode` は表示用 field で identity に
  含まれない)。現行実装は spec の計算規約を正確に満たしている — regression-lock として固定する。

---

## K. Markdownize 入出力契約 — failed_units・evidence_pointers・V1-V6・unit_ref 衝突 (U85)

### QA36 `failed_units` field が `MarkdownizeResponse` に存在しない (部分失敗を表現できない) [P0]
- 正本: 04 §3.1 (Adapter 出力契約 JSON 例) L295『"failed_units": [{ "unit_key": "...",
  "error_kind": "..." }]』/ 07 §5.2 L345-348『failed_units [{ unit_key, error_kind }] — 部分失敗の
  unit...persist されず manifest 側で failed へ遷移』
- 前提: `crates/kio-adapter/src/types.rs:194-203` の `MarkdownizeResponse` に `failed_units` は
  存在しない。`failed_units` という語自体は crates 全体で grep すると
  `crates/kio-cli/tests/step4b_ledger_contract.rs:15` のコメント (「CL40 は未実装」の注記) の
  1 件のみで、実 field/構造体としては皆無。
- 操作: incremental Markdownize 応答で 1 unit のみ Adapter 側処理エラーとなる状況を用意する。
- 期待: 応答に `failed_units: [{unit_key, error_kind}]` が含まれ、Kio 側は当該 unit を manifest
  上で `failed` へ遷移させる (persist はしない)。現行はこの field が無いため、部分失敗を
  Adapter が構造化して報告する手段が存在しない (§3.2 V1/V4/V6 いずれの被覆判定も
  failed_units 抜きで評価されている — 下記 QA38/QA39 参照)。

### QA37 `evidence_pointers` field が `MarkdownizeResponse` に残存し、常に空配列を書くだけの死んだ field になっている [P1]
- 正本: 07 §5.2 L351-352『# Evidence Pointer は Adapter output に含めない — 必須フィールド...は
  chunking と snapshot の後にしか存在しないため、発行は Kio core が行う』
- 前提: `crates/kio-adapter/src/types.rs:200` に `pub evidence_pointers: Vec<Value>` が残存する。
  構築箇所 10 件 (`main.rs:10509,12921,12939`、`markdownize.rs:1660`、`mistral_ocr.rs:658`、
  `deterministic.rs:203,218`、テスト 2 件) は**すべて** `Vec::new()` を渡し、読み取り側でこの
  field を参照する箇所は crates 全体で 0 件。
- 操作: `MarkdownizeResponse` の serde schema を検査する。
- 期待: `evidence_pointers` field が構造体から削除されている (spec は「Adapter output に含めない」
  と明記)。現行は field が残存し、常に空配列を書き込むだけの死んだコードパスになっている
  (実害は乏しいが spec の「削除」という明示指示に反する)。

### QA38 V1 の「同一配列内 unit_key 重複」検査と「unchanged_unit_keys の完全一致 (§2.2 候補集合との照合)」が実施されない [P0]
- 正本: 04 §3.2 L313-323『V1 被覆・排他: ...4 集合は互いに素 (...**同一配列内の unit_key 重複も
  違反** — keys() の集合化では隠れるため、**各配列の要素数 = distinct unit_key 数**を
  あわせて検査する)...**unchanged_unit_keys は §2.2 の unchanged 候補集合と完全一致**
  (changed/added の unit を unchanged と申告して旧内容を成功公開させるのは違反 — 集合は
  Kio 側確定)』
- 前提: `validate_markdownize_response` (`markdownize.rs:336-390`) の
  `unit_keys()`/`set_from()` ヘルパ (1431-1437) は `Vec<String>` を `BTreeSet` へ変換するのみで
  要素数比較を行わない (同一配列内で `"page:1"` が 2 回出現しても `BTreeSet` 化で 1 要素に
  縮退し検出されない)。また `unchanged_keys` (354-358) は応答の `unchanged_unit_keys` を
  そのまま信頼する集合として使い、Kio 側で独立計算した §2.2 unchanged 候補集合
  (`crate::prepare::map_units` の `unchanged: Vec<UnitReuse>`) と突合しない — Adapter が
  changed unit を虚偽で unchanged と申告しても検出されない。
- 操作: (a) `updated_units` 配列内に同一 `unit_key` を 2 回含む応答。(b) 実際は変化した unit
  (fingerprint 不一致) を `unchanged_unit_keys` に含める応答。
- 期待: (a)(b) いずれも contract_violation として reject される。現行はいずれも通過しうる
  (要素数チェック・独立集合突合が無いため)。

### QA39 V4 (added ∪ (failed ∩ hints.added) = hints.added、互いに素) が未実装、V6 (full 出力での failed_units 被覆) も同様 [P0]
- 正本: 04 §3.2 L327-329『V4 added: `keys(added_units) ∪ (keys(failed_units) ∩
  hints.added_unit_keys) = hints.added_unit_keys` かつ両集合は互いに素 (added unit の部分失敗は
  failed_units 側で表現する)』/ L335-342『V6 mode: mode_used="full" の場合...
  `keys(updated_units) ∪ keys(added_units) ∪ keys(failed_units) = prepared unit 全集合`』
- 前提: `validate_markdownize_response` の incremental 経路 (385-387) は
  `if added_keys != set_from(&hints.added_unit_keys) { ... }` という**単純完全一致**のみを
  検査し、failed_units による部分免除の余地が無い (`failed_units` 自体が存在しないため構造的に
  不可能)。`validate_full_response` (1380-1395) も `updated_units` 単独で prepared unit 全集合との
  完全一致を要求し、`added_units`/`failed_units` を V6 の被覆式に含めない。
- 操作: added 対象 2 unit のうち 1 unit が失敗した incremental 応答、および mode=full で
  一部 unit が失敗した応答をそれぞれ用意する。
- 期待: 前者は `added_units` (成功 1 件) + `failed_units` (失敗 1 件) の合計が
  `hints.added_unit_keys` と一致すれば受理される。後者は `updated_units ∪ failed_units` が
  prepared unit 全集合と一致すれば受理される。現行はいずれも `failed_units` が存在しないため、
  1 unit でも失敗すると応答全体が reject される (全体 all-or-nothing に縮退している)。

### QA40 unit_ref 衝突検査 (persist 前の合成後最終集合に対する単射性チェック) が存在しない [P0]
- 正本: 04 §3.2 L349-356『unit_ref 衝突の拒否: 衝突とは異なる unit_key が同一 unit_ref
  (`base16(sha256(unit_key))[0:16]`) へ写像されることをいう...検査対象は**persist 前**に確定する
  合成後の最終 unit 集合...衝突があれば persist 先 `<unit_ref>.json` が競合するため当該応答を
  whole-response reject とする...検査は persist 前の V 検査と同時に行う』
- 前提: `validate_markdownize_response`/`validate_full_response`
  (persist 前の受け入れ検査、V1-V6 相当) に unit_ref 由来の衝突検査は存在しない。衝突検査自体は
  `validate_manifest_identity` (`markdownize.rs:716-744`, `manifest_refs.insert(...)`) に
  **存在するが、これは persist 済みの manifest を検証する関数**であり (fsck/load 時の
  自己整合性検査)、応答受理時の pre-persist gate ではない。
- 操作: 2 つの異なる `unit_key` が偶然 (または人為的に) 同一 `unit_ref` prefix を持つ応答を用意し
  (テストでは実際の 64bit 衝突ではなく、検査ロジックへ疑似衝突ペアを注入する形で代替可)、
  `validate_markdownize_response` 相当の受理判定に通す。
- 期待: persist 前に whole-response reject される。現行は persist 前の検査経路にこの検査が
  存在しないため通過してしまい、後続の manifest 書込み時に初めて (無条件上書きか、
  `validate_manifest_identity` による load 時検出か、実装依存の) 未定義動作を起こしうる。

---

## L. Normalized Markdown v1 形式 (U86)

### QA41 `validate_unit_shapes` は非空・unit_key・unit_type の 3 点のみを検査し、v1 構造規約を一切検査しない [P0]
- 正本: 04 §3.2 L330-334『V5 形式: 各 updated/added unit の markdown が非空文字列で、unit_key/
  unit_type が prepared unit 側と整合。加えて **Normalized Markdown v1...の機械検証可能な規約 —
  UTF-8 (BOM禁止)・NFC・LF のみ・trailing space 禁止・ATX 見出し・``` fence・生HTML/autolink 禁止
  — への適合を検査し、違反 unit を含む応答は reject する**』/ 07 §5.2.1 (v1 の完全定義)
- 前提: `validate_unit_shapes` (`markdownize.rs:1397-1417`) は
  `unit.markdown.is_empty()`・`unit_key` の prepared 存在確認・`unit_type` 一致の 3 点のみを
  検査する。`NFC`/`nfc`/`BOM`/`trailing_space`/`atx`/`fenced_code`/`Setext`/`setext` を
  `markdownize.rs` 全体で grep すると全て 0 件 — v1 の構造規約は 1 つも機械検証されていない。
- 操作: (a) BOM 付き UTF-8 の markdown。(b) NFD (未正規化) の markdown。(c) CRLF 改行の
  markdown。(d) 行末 trailing space を含む markdown。(e) Setext 見出し (`===`/`---` 下線式) を
  含む markdown。(f) 生 HTML block を含む markdown。を含む updated_units をそれぞれ用意する。
- 期待: (a)-(f) いずれも contract violation として reject される。現行は全パターンとも
  `validate_unit_shapes` の 3 チェックをすり抜けて受理される (同型の 6 ケースを 1 契約に
  パラメタ化)。

### QA42 同梱 deterministic Markdownize Adapter が Setext→ATX 変換を行わない [P0]
- 正本: 07 §2.1 L77『(同梱 deterministic Adapter の) 出力は単純な passthrough ではなく、
  Normalized Markdown v1 (§5.2.1) への決定的正規化である — **少なくとも Setext 見出し→ATX変換**・
  生 HTML block の fenced text 化・改行/空白/fence の正規化を行う』
- 前提: `crates/kio-adapter/src/deterministic.rs` を `Setext|setext` で grep すると 0 件。
  同ファイルには BOM 除去 (`670-702` 付近、Q5 コメント) と code fence 整形 (`fence_code`,
  308-313) は存在するが、Setext 見出し (`Title\n=====` 形式) を ATX (`# Title`) へ変換する
  処理は存在しない。
- 操作: `Title\n=====\n\nBody text` (Setext H1) を含む plain text/Markdown ファイルを同梱
  deterministic Adapter で markdownize する。
- 期待: 出力が `# Title\n\nBody text` (ATX 形式) へ正規化される。現行は Setext 記法がそのまま
  素通りし、v1 の「ATX 見出しのみ (Setext 禁止)」規約に違反した markdown が (Kio 側検査も
  QA41 のとおり機能しないため) そのまま persist される — オフライン基線 index で通常の
  Markdown 文書 (README 等、Setext 見出しは稀だが GitHub Flavored Markdown で許容される記法) が
  v1 違反のまま格納されるリスクを再現できる。

### QA43 [regression-lock] 同梱 deterministic Adapter の BOM 除去・code fence 正規化は既に部分実装済み [P2]
- 正本: 07 §2.1 L77 (上記 QA42 と同一パラグラフ)
- 前提: `deterministic.rs:670-702` 付近 (Q5 コメント「a leading UTF-8 BOM...used heading」) は
  入力側 BOM を確実に 1 個ストリップするテスト付き実装を持ち、`fence_code`
  (308-313, ` ```{lang}\n{}\n```\n` 形式で `trim_end()` 適用) は出力の code fence を
  CommonMark 標準形へ揃える。
- 操作: 入力ファイルの先頭に UTF-8 BOM を付与し、deterministic Adapter で処理する。
- 期待: 出力 markdown の見出しが column 0 から始まり BOM を含まない。現行実装は既にこの点を
  満たしている — regression-lock として固定し、QA41/QA42 の新規実装が既存の正しい挙動を
  壊さないことの回帰防止に使う。

---

## M. fallback_to_full 制御応答と contract_violation retry の分離 (U87)

### QA44 fallback_to_full=true が mode 不問で無条件 contract_violation となり、制御応答としての再発行が行われない [P0]
- 正本: 04 §3.2 L358『fallback_to_full=true の応答は V1〜V6 に先立ち制御応答として評価する...Kio は
  当該応答を成功・失敗のどちらの終端にもせず、**同一 task を mode=full で再発行する** (§3.1 の
  発動条件は再評価しない)。full 応答でのこの flag は contract violation = ループ防止』
- 前提: `validate_markdownize_response` (`markdownize.rs:341-343`) は
  `if response.fallback_to_full { return Err(contract_violation("adapter_requested_full_fallback")); }`
  — **mode を一切見ずに無条件で reject する**。呼出元は 2 系統に分岐する: (a) online incremental
  試行 (`main.rs:10552-10554`) は本関数を呼ぶ前に独自に `if response.fallback_to_full {
  return Ok(None); }` で回避し「中止」として扱う (制御応答ではあるが、mode=full での**同一 task
  再発行**ではなく単に incremental 試行を諦めるだけ)。(b) offline pipeline loop
  (`main.rs:13395-13453`) は本関数の reject 結果を利用し、`mode==Incremental` の場合のみ
  full へ再発行するが、この再発行は「contract_violation を経由した副作用としての再送」であり、
  spec が要求する「V1-V6 に先立つ制御応答としての評価 (contract_violation を一切経由しない)」
  ではない。
- 操作: mode=incremental で `fallback_to_full=true` の応答を返す状況を作る。
- 期待: 当該 request が `outcome='fallback_to_full'` で確定記帳・state=3 (task は非終端) となり、
  `contract_violation_count`/`attempts` いずれも増加せず、直後に mode=full の新 request が相 1
  として開始される。現行はいずれの経路も何らかの形で `KIO-E-ADAPTER-CONTRACT-001` を経由するか
  (offline)、記帳を一切経ずに黙って `None` を返す (online) かのどちらかであり、spec が定める
  「制御応答としての記帳付き再発行」を満たさない。

### QA45 `RetryErrorKind::ContractViolation` の retry policy が `retryable:false, max_attempts:0` のままで、spec の `retryable, max_attempts=1` に更新されていない [P0]
- 正本: 04 §5.3 L738-740『contract_violation retryable max_attempts=1 (同一 mode で 1 回のみ
  再投入 — 出力揺れ対策。再違反は failed permanent = Adapter バグ。full への自動 fallback は
  しない)』
- 前提: `crates/kio-pipeline/src/task.rs:913-920` の `retry_policy` は
  `RetryErrorKind::ContractViolation => RetryPolicy { retryable: false, max_attempts: Some(0),
  backoff: "full_fallback_once", ... }` — 旧仕様 (failed permanent, max_attempts=0, full
  fallback を 1 回自動投入) のままであり、新仕様 (retryable, max_attempts=1, 同一 mode で
  再投入・full への自動 fallback はしない) に未更新。
- 操作: `retry_policy(RetryErrorKind::ContractViolation)` を呼び出す。
- 期待: `retryable: true, max_attempts: Some(1)` を返す。現行は `retryable: false,
  max_attempts: Some(0)` を返す — 「1 回のみ再試行」の実現手段そのものが逆転している
  (現行は「0 回・即 permanent」、spec は「1 回・同一 mode で再試行」)。
  **接続**: 「1 回のみ」の真の durable 判定源は task 側カウンタではなく
  `batch_requests.contract_violation_count` である (04§5.2 L723、Phase 1 実装済み — CL21) — 本
  contract は **task 側 `RetryPolicy` の表示値・ローカル/offline 実行時の再試行許可判定**を
  対象とし、online/Batch 経路の durable 判定 (既に CL21 で正しく実装済み) とは別物である。

### QA46 `KIO-E-ADAPTER-SPECVER-001` が存在せず、spec_version 不一致が汎用 contract_violation と区別されない [P0]
- 正本: 07 §8.1 L693『5. spec_version 不一致なら、Adapter は invalid_input として失敗
  (`KIO-E-ADAPTER-SPECVER-001` — 汎用 `KIO-E-ADAPTER-CONTRACT-001` (retryable 1回) と区別し、
  invalid_input 分類 = max_attempts 0 に一意に対応させる)』/ 04 §3.2 L367
  『full への自動 fallback は行わない (fallback は incremental capability 非互換の場合のみ)』
- 前提: `grep -rn "KIO-E-ADAPTER-SPECVER-001" crates/` は 0 件 (docs にのみ記載)。
  spec_version 不一致は現行コードでは汎用 `KIO-E-ADAPTER-CONTRACT-001` (`markdownize.rs:1440`)
  として扱われる可能性が高く (専用の判定分岐が見当たらない)、QA45 是正後は
  `retryable/max_attempts=1` になる contract_violation と、spec_version 不一致
  (invalid_input・max_attempts=0・非再試行) が同一エラーコードに混在するリスクがある。
- 操作: `spec_version` が Adapter の対応範囲外の request を送る。
- 期待: `KIO-E-ADAPTER-SPECVER-001` (invalid_input, max_attempts=0) として failed permanent に
  なり、full への自動 fallback もしない (capability 非互換とは異なる理由のため)。現行は
  この専用コードが存在せず、QA45 の是正と合わせて実装すると「同一 mode で 1 回再試行」の
  対象に spec_version 不一致まで誤って含まれてしまう回帰リスクがある。

---

## N. Embedding 応答受入検査・Vertex 並列規約・SQL 正本 (U88/U89/U90)

### QA47 embedding id は provider 応答からではなく request から位置的に合成されており、真の集合ベース全単射検査が成立しない [P1]
- 正本: 07 §5.3 L458『(1) vectors[].id は入力 id 集合との**全単射**(欠落・過剰・重複は違反)』
- 前提: `parse_embeddings` (`gemini_embedding.rs:199-252`) は Gemini `batchEmbedContents` 応答に
  per-item id が存在しないため `id: item.id.clone()` (246-249) で **request 側の id を
  そのまま複製**する。その後の突合 (`gemini_embedding.rs:332-337`) は
  `for (item, vector) in request.items.iter().zip(&vectors) { if vector.id != item.id { ... } }`
  という**位置的 (zip) 一致検査**であり、`vector.id` が id 自体を持たない (構築時に複製される)
  以上この検査は構造的に常に真になる — 真に検証されているのは「応答ベクタ数 = 入力 item 数」
  (327-330 の長さチェック) のみである。
- 操作: provider が (実際には起こり得ないが検証のため) 入力より 1 件少ない vector 配列を返す
  状況、および順序が入れ替わった vector 配列を返す状況を用意する。
- 期待: 件数不一致は現行でも検出される (長さチェックあり)。順序入れ替えは、真の id が
  provider から来ない設計のため「入れ替わった」という事象自体が定義できず、位置的に
  再ラベルされて見かけ上正常に通過する。**[解釈割れ]**: provider が id を返さない (Gemini の
  API 仕様上の制約) 場合、「全単射検査」を spec が要求する意味は「件数一致 + 順序保存」を
  代替要件として認めているのか、あるいは順序が保証されない provider を採用しないことが
  前提なのかは spec 文言のみからは確定できない。

### QA48 L2 正規化後の再検査 (単位ノルムであること) が実施されない — norm > 0 の確認に留まる [P0]
- 正本: 07 §5.3 L458『(4) float32 への決定的変換と L2 正規化は core 側で実施する...
  **変換・正規化後の最終 vector にも (3) と同じ有限・非ゼロ (かつ単位ノルム — 許容誤差内) を
  再検査する** (underflow の零 vector/overflow の Inf を index に入れない — 違反は同じ
  contract violation)』
- 前提: `validate_cosine_vector` (`crates/kio-adapter/src/types.rs:246-268`) は
  finite かつ `norm_squared > 0.0` を検査するのみで、**L2 正規化そのもの (core 側での実施) も
  正規化後の単位ノルム再検査も行わない** — 関数名が示すとおり cosine 距離が定義可能かの
  検証に留まり、"unit norm within tolerance" の検査は存在しない。
- 操作: 正規化前の (norm ≠ 1) raw vector を Adapter から受け取り、Kio 側の正規化パイプラインを
  通す。
- 期待: 正規化後の vector に対し、単位ノルム (許容誤差内) であることを再検査し、外れる場合は
  contract violation とする。現行は正規化処理自体・正規化後の再検査のいずれも
  `validate_cosine_vector` には存在しない (正規化が別の場所に実装されているか、実装されていない
  かは本書の調査範囲では確定できていない — 実装着手時に正規化コードの所在を先に確認する必要が
  ある)。

### QA49 応答 metadata (`embedding_profile_hash`/`modality`/`distance`) が期待 profile と突合されない [P0]
- 正本: 07 §5.3 L458『(5) 応答 metadata の `embedding_profile_hash`・`modality`・`distance` が
  期待 profile と一致する (同次元の別 vector space の混入を契約で拒否する — 不一致は同じ
  contract violation)』
- 前提: `embedding_profile_hash` は crates 全体で grep 0 件。`EmbeddingResponse`
  (`types.rs:235-241`) は `dimensions`/`distance`/`modality` を持つが、消費側
  `run_adopted_embedding` (`catalog.rs:577-607`) は `Ok(response.vectors)` のみを返し
  `response.dimensions`/`response.distance`/`response.modality` を**読み捨てる** —
  `DeclaredEmbeddingProfile` (`catalog.rs:560-574`) との突合は一切行われない。
- 操作: 期待 profile と異なる `modality`/`distance` を応答 metadata に持つ (擬似) Embedding
  応答を用意する。
- 期待: metadata 不一致が contract violation として reject される。現行は応答の
  dimensions/distance/modality が構造体に存在するにもかかわらず消費側で破棄されるため、
  不一致があっても検出されない (同次元の別 vector space が index に紛れ込むリスクを
  塞げない)。

### QA50 [規約確認] Vertex embedding はタスク内で常に単一 request にまとめて送信されており、直列化・並列化いずれの規約も現状「該当なし」で通過する [P2]
- 正本: 07 §5.3 (実地検証済みパラグラフ)『Vertex はバッチ推論非対応のため sync 呼出 — client
  側の並列は**タスク間** (別 batch_requests 行) で行い、**単一タスク内の複数 request は直列**
  (04-pipeline.md §5.4 の縮退2相)』
- 前提: `send_embed_batch` (`main.rs:11753-11807`) は 1 task 内の最大 32 chunk
  (`EMBEDDING_BATCH_SIZE`) を**常に 1 回の `run_embedding_adapter` 呼出**にまとめる。
  `gemini_embedding.rs` に `sync`/`parallel` の語は 0 件、`tokio`/`rayon`/`par_iter`/`spawn` も
  crates 全体で kio-cli には 0 件 (完全同期・単一スレッド実行)。
- 操作: 33 chunk (バッチ境界を跨ぐ) を含む embedding タスクを実行する。
- 期待: 2 回の `run_embedding_adapter` 呼出が発生し、直列に (前の呼出の終端後に次を開始)
  実行される。現行はループが `for batch in embeddable.chunks(32)` で単純な逐次 for であり、
  結果的に「単一タスク内の複数 request は直列」という規範を**偶然満たしている**
  (並列化コードが存在しないため直列以外の実行順序があり得ない)。タスク間並列 (spec が
  許容するが要求はしない) も同様に存在しない。**[解釈割れ]**: 「タスク間並列で行う」が
  MUST (規範) か MAY (許容) かは文言 (「並列は...行い」) だけでは断定しづらく、本契約は
  現状 (タスク間並列も未実装) が spec 違反かどうかを断定しない — 少なくとも「単一タスク内
  直列」は現状で満たされていることのみを regression-lock として固定する。

### QA51 embeddings/chunk_vec SQL authority の重複テストは統合済み [P2]
- 正本: 07 §5.3 L464-466『embedding の SQLite schema (embeddings/chunk_vec) の正本は
  04-pipeline.md §4.3 とする...SQL 定義の重複記載は 2026-07-14 に解消し、本節から参照する』
- 判定: production Rust source を走査して `CREATE TABLE` 文字列の不在を固定する旧テストは、
  リファクタリングで壊れる一方で runtime failure を検出する固有 signal を持たないため削除した。
- 現行 coverage: `step4b_p3b_contract::qb31_chunk_fts_and_chunk_vec_schema_is_executable`が実際に
  index DB を生成し、`embeddings`/`chunk_vec`を含む現行 schema を SQLite に実行・照合する。
  authority は public schema behavior で検査し、module 内の SQL 文字列の個数や配置はテスト契約にしない。

---

## O. Batch 実行契約とプロバイダ採用条件 (U91)

### QA52 Batch 実行契約 trait (upload/create_job/get_job/list_jobs/list_uploads/delete_upload/fetch_output/provider_scope_id) が存在しない [P0]
- 正本: 07 §5.7 L498-515『Batch モードを持つ online Adapter...は、04-pipeline.md §5.8 の
  2 相プロトコルが要求する次の操作を trait として公開する: upload/create_job/get_job/
  list_jobs/list_uploads/delete_upload/fetch_output/provider_scope_id』
- 前提: `crates/kio-adapter/src/traits.rs` (全 61 行) は `PrepareAdapter`/`MarkdownizeAdapter`/
  `EmbeddingAdapter`/`SummaryAdapter`/`ClassificationAdapter`/`RerankAdapter` の 6 trait のみを
  持ち、いずれも `profile()` + 単一 execute メソッドの 2 メソッドのみ。`upload`/`create_job`/
  `get_job`/`list_jobs`/`list_uploads`/`delete_upload`/`fetch_output`/`provider_scope_id` は
  `mistral_ocr.rs`/`gemini_embedding.rs` を含め kio-adapter クレート全体で grep 0 件 (`
  provider_scope_id` という語は `kio-pipeline/src/ledger/` 側に SQL 列として存在するのみで、
  Adapter が実装すべき trait メソッドとしては皆無)。
- 操作: Batch 実行契約 trait の存在を検査する。
- 期待: `BatchAdapter` (仮称) trait が新設され、8 操作全てを公開する。現行は trait 自体が
  存在せず、実 provider 呼出 (`mistral_ocr.rs`) も単発同期 HTTP POST (`.post("{}/v1/ocr")`,
  line 207-208) のみで job/upload の概念を一切持たない。

### QA53 `mistral_ocr_markdownize` は Batch モードを実装しておらず、spec が「採用済み」と記す実地検証との乖離がある [P0]
- 正本: 07 §5.7 L552『`mistral_ocr_markdownize` の Batch モードは 2026-07-03 の実地検証...の
  範囲でこの条件下で採用済み』/ 07 §5.2 末尾『合成 fixture...を sync / **Batch 両モードで検証**』
- 前提: `crates/kio-adapter/src/mistral_ocr.rs` (2468 行) は `MarkdownizeAdapter` trait
  (単発同期呼出) の実装のみを持つ。`custom_id`/`"batch"`/`"Batch"` は本ファイル全体で grep 0 件。
  `EnvMistralOcrClient` (line 92) も同期クライアントであり、Batch job 経路は存在しない。
- 操作: Mistral OCR markdownize タスクを Batch モードで投入する。
- 期待: §5.7 の 2 相プロトコル (相1 intent 記録→相2a upload→相2b job作成→相3 collect) に
  従って投入・収集される。現行は Batch モード自体が実装に存在しないため、常に sync (同期)
  呼出のみが行われる — spec が「実地検証で採用済み」と記す Batch 経路と現行実装の乖離を
  固定する。

### QA54 プロバイダ採用条件 7 項目 (可視化遅延上限・保持期間・intent_token 埋込・安定識別子・投入拒否課金宣言・job id 恒久非再利用) を検査する機構が存在しない [P1]
- 正本: 07 §5.7 L529-550 (7 条件の全文列挙、特に条件7『job id/provider request id が...
  **恒久に実質再利用されない**こと (...恒久保持の cost_ledger 全履歴に対して突合するため —
  期限付きの一意性では期限超の再利用が過去行と誤合致して確定記帳を落とす)』)
- 前提: QA52 のとおり Batch trait 自体が存在しないため、これらの条件を「プロバイダがこの trait
  実装を通じて満たしているか」を検査する仕組みも存在しない (検査対象となる trait メソッドが
  無い)。
- 操作: 7 条件のうち 1 つ (例: 条件2「可視化遅延上限 10 分」) を満たさない provider 実装を
  接続しようとする。
- 期待: Kio 側で採用可否判定に失敗し、Batch モードでの採用を拒否する (sync のみでの採用に
  縮退するか、非採用とする)。現行はこの判定ロジック自体が存在しない (QA52 の Batch trait 新設に
  伴って初めて意味を持つ、依存契約)。

### QA55 sync provider の投入拒否課金 (permanent 4xx でも課金する場合の usage 返却義務) が Adapter 契約として存在しない [P1]
- 正本: 07 §5.7 L540-545『投入拒否 (permanent 4xx) にも課金するか否かを宣言すること。課金する
  provider の Adapter は、拒否応答時に usage (...) を機械可読で返却する (この返却義務は
  **Batch 限定でなく sync online Adapter にも共通**)』
- 前提: `AdapterError` (`crates/kio-adapter/src/lib.rs:19-38`) の各 variant
  (`ContractViolation`/`Auth`/`RateLimit`/`QuotaExceeded`/`Network`/`ConfigSchema`/
  `NotImplemented`/`Io`) はいずれも `String` メッセージのみを持ち、拒否時の usage
  (`usd`/`billable_units`) を運べる構造を持たない (QA17 の `usage` field 不在と表裏)。
- 操作: sync online Adapter が投入拒否 (課金対象の permanent 4xx) で失敗する状況を用意する。
- 期待: エラー値に usage (宣言請求額) が付随し、Kio 側が `submit_rejected` として同一 Tx で
  記帳できる。現行は `AdapterError` の型自体が usage を運べないため、拒否時の課金額は
  常に estimated 縮退にしかならない。

---

## P. ログ記録フィールドの拡張と adapter_id=tool_id 規約 (U92)

### QA56 `network_consent`/`submission_seq`/`usage_validation`/`billing_source` がログ可能 field として存在しない [P2]
- 正本: 07 §7 L613-633『ログに残してよいもの: ...network_consent (approvals\|cli_online — 送信を
  伴った実行のみ)...adapter_kind, input_hash, intent_token, **submission_seq**...
  **usage_validation** (missing\|invalid), **billing_source** (estimated)』
- 前提: `network_consent`/`usage_validation`/`billing_source` は `crates/kio-adapter/` 全体で
  grep 0 件。`submission_seq` は `kio-pipeline/src/ledger/` の SQL 列としては存在するが、
  Adapter 層のログ出力 field としては存在しない。
- 操作: online Adapter 呼出のログ出力を検査する。
- 期待: 4 field (該当条件下) がログレコードに含まれる。現行はいずれも欠落している。

### QA57 [regression-lock] `adapter_id` は `tools.toml` の `tool_id` と同一値である規約が既にテストで担保されている [P2]
- 正本: 07 §7 L635『`adapter_id` は tools.toml の `tool_id` と同一値である (別 namespace を
  作らない — approvals[] (§3) の照合キーと一致し...)』
- 前提: `crates/kio-adapter/src/catalog.rs:725-733`
  (`declared_adopted_embedding_profile_uses_adopted_profile_by_default`) が
  `assert_eq!(declared.tool_id, adopted.adapter_id);` を既に検証している。
- 操作: 登録済み Adapter の `AdapterProfile.adapter_id` と `tools.toml` の対応 `tool_id` を
  比較する。
- 期待: 一致する。現行は既存テストが担保している — regression-lock として固定し、§H
  (`kio adapter revoke <tool_id>`) が同じ照合キーに依拠できることを確認する。

---

## Q. ストリーミング処理の全面改訂 (U93)

### QA58 大型入力のストリーミング応答 (SSE/chunked JSON) 受信・unit 単位 persist が実装に存在しない [P0]
- 正本: 07 §8.3 L728-730『大型 PDF (100+ pages) では TTFB を抑えるためストリーミング出力を許容
  する。Kio は Adapter からの SSE/chunked JSON を受け取り、unit 完了ごとに persist する』
- 前提: `crates/kio-adapter/src/mistral_ocr.rs` (2468 行) を `stream|SSE|chunked` (大小無視) で
  grep しても HTTP ストリーミングに関する実装は見当たらず (該当箇所は既存の「incremental な
  page 単位処理」を指すコメントのみで、SSE/chunked-JSON 受信とは別概念)、実装は単発同期
  `.post()` 呼出で応答全体を一括受信する。`.kio/staging/` 自体は purge.rs/scope.rs/restore.rs に
  実在する (下記 QA59) が、ストリーミング応答の unit 単位受信・persist という入口が存在しない。
- 操作: 100+ ページの PDF を Markdownize する。
- 期待: SSE/chunked JSON でストリーミング受信し、unit 完了ごとに staging へ persist される
  (§8.3 の「検査前は公開しない」規律のもとで)。現行は応答全体が揃うまでブロックする単発呼出の
  ため、この機構自体が実装対象として丸ごと未着手であることを固定する。

### QA59 staging root の「同一 root 名残存時の前置回復」「no-replace 公開」が markdownize 経路に存在しない [P0]
- 正本: 07 §8.3 L747-752『同一 `(raw64, tool64, adapter_kind)` の staging root が既に存在する
  状態で新しい task を開始する場合、root 公開 (atomic rename) の**前**に旧 root の回復を、
  呼び出し元コマンドが既に保持する `.kio/.lock` の同一 critical section 内で完了する...root 公開の
  rename は既存 root 名への上書きをしない (no-replace)』
- 前提: `.kio/staging/` は実在する (`purge.rs:1373` の `kio_dir.join("staging")`、
  `scope.rs` の `create_raw_staging_file` 等) が、これらは purge 対象列挙・raw ingest 用の
  既存機構であり、**markdownize のストリーミング staging root**
  (`(raw64, tool64, adapter_kind)` 単位の descriptor 付き root) という専用レイアウトは
  `crates/kio-pipeline/src/markdownize.rs`/`crates/kio-cli/src/main.rs` いずれにも存在しない
  (§S の PB14/16 が扱う「staging root」も同じ空白領域を指す — 本節はその**書込み側**の
  publish 規律、§S はその**読取/prune 側**の分類を扱う、表裏の関係)。
- 操作: 同一 `(raw64, tool64, adapter_kind)` の staging root が残存する状態 (前回 crash の
  残骸) で新しい markdownize task を開始する。
- 期待: 新 task 開始前に `.kio/.lock` 下で旧 root の状態 (対応 task が terminal なら cleanup、
  non-terminal なら新規開始せず再開) を判定し、root 公開は no-replace rename で行う。現行は
  このレイアウト・回復ロジック自体が存在しないため、複数回の crash-retry で staging root が
  無制御に蓄積するか、上書きによる新旧 bytes 混在が起こりうる。

### QA60 retry 応答の合成規則 (transport 中断のみ凍結保全、受け入れ検査 reject は staging 破棄) が実装されていない [P1]
- 正本: 07 §8.3 L754-764『**凍結保全と合成が適用されるのは transport 中断 (stream 失敗) からの
  resume に限る** — 受け入れ検査 reject (contract violation) 起因の再投入では staging を破棄して
  開始する...まず生の retry 応答の各配列に V1/V6 の配列内 unit_key 重複検査と配列間の排他検査を
  適用し...その後 staging に確定済みの unit_key と重複する応答 unit は黙って破棄する』
- 前提: QA58/QA59 のとおりストリーミング staging root の専用機構が存在しないため、
  「transport 中断由来の retry」と「contract_violation 由来の retry」を区別して staging の
  凍結保全/破棄を分岐する実装も存在しない (区別する入力データ自体が無い)。
- 操作: (a) transport 中断 (stream 失敗) で一部 unit が staging に確定済みの状態からの retry。
  (b) contract_violation (V1-V6 reject) で終端した後の retry。を用意する。
- 期待: (a) は staging の完了済み bytes を保全し、retry 応答と合成する。(b) は staging を
  破棄し全 unit を再取得する。現行はこの分岐自体が存在しないため、どちらも同じ (おそらく
  「staging 概念なしの全再取得」) 経路に落ちることを固定する。

---

## R. include_neighbors キーと incremental 発動条件の精密化 (U94/U143)

### QA61 [regression-lock + 解釈割れ] `include_neighbors` は schema に残存し値=1 のみ許容する no-op として実装されているが、キー自体の削除要否は spec が明言しない [P2]
- 正本: 10-operations.md (config 例からの削除、U94 統合要約)『config 例から `include_neighbors = 1`
  が削除された...schema 上もこのキーが不採用になった可能性がある (削除理由の記述なし)』
- 前提: `config.schema.json:117` は `include_neighbors: {type: integer, minimum: 0}` を保持し、
  `enforce_config_semantics` (`crates/kio-core/src/scope.rs:2454-2468`) は値が 1 以外なら
  `KioError::not_implemented` で拒否する (コメント「R12-1: has no implementation concept」)。
  既存テスト `r12_1_incremental_include_neighbors_non_default_rejected`
  (`crates/kio-cli/tests/step3_p0_contract.rs:4820-4829`) がこの挙動を担保する。
- 操作: `include_neighbors = 1` と `include_neighbors = 2` をそれぞれ設定して config validation を
  実行する。
- 期待: `= 1` は受理 (no-op)、`= 2` 以上は拒否。現行は既にこの挙動を満たしている —
  regression-lock として固定する。**[解釈割れ]**: U94 の統合要約自身が「削除された可能性がある」
  としつつ断定を避けているため、本契約は「現状の no-op 挙動を維持する」ことのみを固定し、
  schema からキー自体を削除すべきか (呼出側が unknown key として拒否されるべきか) は
  実装時の裁定を要する。

### QA62 [regression-lock] incremental 発動条件 1 (file_id 不使用・path binding) と条件 5 のカウンタ更新は現行実装が機能的に満たしている [P1]
- 正本: 04 §3.1 L247-248『同一ファイル (= scope 内の同一 path binding。file_id は廃止済み)...に
  対する既存 done normalization_run がある。rename を跨いだ同一性は追跡しない』/ L252-255
  『カウンタの更新点: accepted された incremental 応答の finalize で+1・accepted された full 応答の
  finalize で 0 へ reset...正常な制御応答と reject された応答はどちらにも数えない』
- 前提: `previous_instance_for_path` (`main.rs:13921-13946`) は `task.input_path == input_path`
  (パス一致) のみを条件にし `file_id` を一切参照しない (crates 全体で `file_id` は
  `same_file_identity` という**無関係な**別概念 — OS レベルのファイル実体同一性判定、
  scan.rs/unsupported.rs 用途 — にのみ現れ、Markdownize の同一性判定には使われない)。
  `consecutive_incremental_count` (`main.rs:14065-14082`) は `status==Done` かつ
  `mode==Incremental` の task を新しい順に数え、最初の非 Incremental Done task で打ち切る —
  これは「accepted incremental で+1・accepted full で reset」と**history 再計算という手段が
  違うだけで機能的に等価**である (Failed task は filter で除外されるため増減いずれにも
  寄与しない = 「reject は数えない」を満たす)。
- 操作: 同一 path で (a) rename を挟んだ incremental 試行、(b) 5 回連続 incremental 成功後の
  6 回目、を実行する。
- 期待: (a) は同一性追跡されず full 強制。(b) は `max_consecutive` (既定5) 到達で full 強制。
  現行はいずれも満たす — regression-lock として固定する。**[解釈割れ/依存関係]**: `Partial`
  (settled 含む、§C QA9) 状態の task は `consecutive_incremental_count` の filter
  (`status==Done` のみ) から漏れるため、部分成功で settled した incremental task が連続回数に
  正しく寄与するかは §C QA9 の是正と連動して再検証が必要。また QA44 (fallback_to_full の
  制御応答化) が実装されると、正常な制御応答由来の task 生成パターンが新たに生じるため、
  「制御応答はカウンタに数えない」という規約がその時点で初めて実地検証可能になる (現状は
  制御応答が即 contract_violation になるため、この規約は事実上未着手のまま検証不能)。

---

## S. staging root の 3 分類と open cache 残骸回収 (PB14/PB16/PB17 継承)

### QA63 staging root の 3 分類 (descriptor 無し/path 不整合/terminal task 対応) が `--prune-orphans` に実装されていない — 実装者自身が既知ギャップとして明記 [P0]
- 正本: 10 §7.5.1 L588-592 (`step4b-contract-tests-p2b.md` PB14 引用)『descriptor の無い
  staging root・path と不整合な staging root・terminal 化済み task にのみ対応する staging root
  ...を列挙し、locked repair として削除する』
- 前提: `crates/kio-cli/src/verify_objects.rs` の `pub fn prune_orphans` (2059-2228) 自身の
  doc comment (2038-2058) に次の記述がある: 『**NOT implemented this session — documented gap,
  not a silent omission**: PB14/16 (staging-root descriptor 3-way classification and the
  terminal-task escape hatch...)』。実際に本関数は staging root を一切列挙・削除しない
  (関数内に `staging` という語は 1 度も現れない — prepared/image object の live-set 差分削除の
  みを行う)。既存の別機構 `delete_target_staging` (`purge.rs:1372-`, `.kio/staging/` を
  raw_hash 属性で削除) は **purge 専用**であり、terminal task 判定・descriptor 整合性判定を
  一切行わない別目的の関数である (混同注意)。
- 操作: (a) descriptor の無い staging root。(b) descriptor はあるが記載 path と実体が不一致な
  staging root。(c) descriptor・path とも整合するが対応 task が terminal
  (done/failed permanent/abandoned/settled partial) な staging root。(d) 同様に整合するが
  対応 task が non-terminal (pending/running/partial-with-retryable-failed-unit) な
  staging root。の 4 パターンを用意して `kio repair --verify-objects --prune-orphans` を
  実行する。
- 期待: (a)(b)(c) は削除対象、(d) は削除対象外 (進行中 task の保全)。現行は 4 パターンいずれも
  `prune_orphans` の削除対象・拒否条件のどちらにも該当せず、単に無視される (放置されたままになる
  — 削除も拒否もされない、という第 3 の未定義挙動)。

### QA64 特定不能退出経路 (task 記録喪失 + 全 gen terminal + state 0/1 batch_requests 行無し) のエスケープハッチが実装されていない [P0]
- 正本: 10 §7.5.1 L600-609 (PB16 引用)『descriptor の (raw_hash, tool_profile_hash) 配下に
  存在する**全て**の normalized instance (全 gen) の manifest で全 unit が terminal であり、
  **かつ同 key の state 0/1 batch_requests 行が無い**なら、terminal 残骸とみなし削除対象へ移す』
- 前提: QA63 と同じ doc comment が PB16 も「本セッション未実装」と明記する。task 記録が
  失われた (tasks.jsonl から該当 task_id が消えた) staging root を all-gen-terminal かどうかで
  判定する経路、および `batch_requests` (Phase 1 実装済み、`ledger/ops.rs`) の state 0/1 行の
  有無で in-flight 信号を判定する経路のいずれも `prune_orphans` に存在しない。
- 操作: staging root の descriptor が指す task_id が tasks.jsonl から失われており (task 記録
  喪失は許容される、04§1)、かつ当該 (raw_hash, tool_profile_hash) の全 gen normalized instance
  manifest が全 unit terminal、かつ同キーの `batch_requests` 行に state 0/1 が無い状態を用意して
  `--prune-orphans` を実行する。
- 期待: task 記録が特定できなくても削除対象に含まれる (PB15 の non-terminal-task 拒否原則の
  **例外**として、この条件だけは in-flight 信号を cost-ledger 側で判定し削除を許可する)。
  現行はこの判定経路自体が無いため、当該 staging root は永久に放置される。

### QA65 [regression-lock] open cache の purge/prune-orphans 時冪等削除は raw/image 型分離込みで既に正しく実装されている (PB17) [P1]
- 正本: 10 §7.5.1 L616-626 (PB17 引用)『`--prune-orphans` は、当該 scope で canonical final
  event が `purged` **または `erased`** である各 raw_hash について
  `~/.cache/kio/open/<raw_hash digest64>/` の残存も検査し、存在すれば...削除対象に含める...
  **image cache も同様に回収する**』
- 前提: `prune_orphans` (`verify_objects.rs:2180-2219`) は (a) tombstone/erase-receipt の
  canonical final event が Purged\|Erased の raw_hash について
  `cache_home().join("kio/open").join(digest)` を削除し (2197-2205)、(b) 別途
  `cache_home().join("kio/open/image")` 配下を全走査して `live_images` に含まれない digest の
  ディレクトリを削除する (2207-2219) — raw 系と image 系が既に型分離された path
  (`open/<digest>/` vs `open/image/<digest>/`) で扱われている（当時の U24 記載
  「image/型分離は無くflat namespace」は本書作成時点では既に解消済み)。
- 操作: (a) canonical final event が purged/erased な raw_hash の open cache 残存。(b) live
  参照 0 の image object の open cache 残存 (`open/image/<digest>/`)。を用意して
  `--prune-orphans` を実行する。
- 期待: (a)(b) いずれも削除される。現行は既にこの挙動を満たしている — regression-lock として
  固定する。**境界注記**: cache の型分離自体 (`open/image/` への分離の設計) は
  `step4b-contract-tests-p2a.md` PA03 の管轄であり、本契約は「`--prune-orphans` という本書
  §S の CLI フラグがこの削除を正しく trigger すること」の現状確認のみを固定する。

---

## T. registry live 重複 fail-closed の書込系コマンド・online 起動への拡大 (PB24 継承)

### QA66 `kio index` (書込系) は registry live 重複を一切検査しない [P0]
- 正本: 10 §3 L296-299『live 重複が解消するまでは、当該 scope_id での**書き込み系コマンド**と
  online タスク起動 (相1) も `KIO-E-REGISTRY-DUP-001` で fail-closed とする』
- 前提: `KIO-E-REGISTRY-DUP-001` を raise する唯一の関数 `registry_duplicate_error`
  (`main.rs:8572-8584`、呼出元 `resolve_scope_id_in_registry_with_hint` 経由) の**全**呼出箇所
  (main.rs:4327 検索カーソル replay、main.rs:7419 evidence pointer 解決、main.rs:8677 object
  URI 解決 (open/view)、restore.rs:126 evidence-sourced restore、verify_objects.rs:118
  evidence verify) は**すべて読み取り系コマンド**である。`fn run_index(args: IndexArgs)`
  (main.rs:716) の本体を `resolve_scope` で grep すると 0 件 — registry 重複検査を一切呼ばない。
- 操作: 同一 scope_id を持つ 2 つの live `.kio` clone を用意し、一方で `kio index` を実行する。
- 期待: `KIO-E-REGISTRY-DUP-001` で拒否される (dedupe を要求)。現行は検査自体が呼ばれないため、
  live 重複状態でも `kio index` が通常どおり進行し、device-global `batch_requests` 行
  (PK に scope_id) を複数 clone が共有する状態を作れてしまう。

### QA67 online タスク起動の相 1 (`phase1_intent`/`check_then_reserve`) も registry live 重複を検査しない [P0]
- 正本: 10 §3 L297-299『online タスク起動 (相1) も `KIO-E-REGISTRY-DUP-001` で fail-closed とする
  — device-global `batch_requests` の行 (PK に scope_id) を複数 clone が共有し、回復・終端・
  課金の帰属が混線するため (04-pipeline.md §5.8)』
- 前提: online タスク起動の相 1 は `reserve_or_reuse_task_charge` (main.rs:14324、内部で
  `phase1_intent` を呼ぶ、ops.rs:283) と `record_free_local_charge` (main.rs:14468) の 2 経路
  だが、いずれも QA66 で列挙した registry-dup 検査の呼出元一覧に含まれない
  (`crates/kio-cli/src/online_task.rs` — 全 27 行 — も
  `targets_standard_online_markdownize` という task 所有権判定関数のみで registry 検査は
  皆無)。
- 操作: 同一 scope_id を持つ 2 つの live `.kio` clone の一方で online markdownize/embedding
  タスクを起動する (相1)。
- 期待: `KIO-E-REGISTRY-DUP-001` で拒否される。現行は相1が無条件に進行し、
  `batch_requests` PK (scope_id, adapter_kind, input_hash, tool_profile_hash) が
  2 clone 間で衝突・共有される状態を作れてしまう (どちらの clone が実際に相2a/2b/3を進めたか
  の帰属が構造的に混線する)。

### QA68 [regression-lock] registry live 重複検査は読み取り系コマンド (search cursor/evidence verify/open/view/restore) には既に正しく配線されている [P1]
- 正本: 10 §3 L284-287 (`PB21`/`PB22` の正本と同一)『同一 scope_id の複数 live path は clone
  併存であり、fail-closed で扱う: global search は当該 scope_id を skip して excluded_scopes に
  `KIO-E-REGISTRY-DUP-001` の理由付きで記録し、pointer 解決は候補一覧 error とする』
- 前提: QA66 で列挙した 5 箇所 (検索カーソル replay・evidence pointer 解決・open/view の object
  URI 解決・restore の evidence-sourced 解決・evidence verify) は全て
  `resolve_scope_id_in_registry`/`resolve_scope_target` 経由で `KIO-E-REGISTRY-DUP-001` を
  一貫して raise できる。
- 操作: 同一 scope_id の live 重複状態で `kio evidence verify`/`kio open`/`kio view`/
  `kio restore <evidence>` のいずれかを実行する。
- 期待: `KIO-E-REGISTRY-DUP-001` で拒否される。現行は既にこの挙動を満たしている —
  regression-lock として固定し、QA66/QA67 の是正 (書込系・online 起動への拡張) がこの
  既存の読み取り系挙動を壊さないことの回帰防止に使う。

---

## U. Markdownize 部分回復の再導出 (CL40 継承)

### QA69 tasks.jsonl 喪失時の Batch 出力再導出 (custom_id 差分→failed_units 合成) が丸ごと未実装 — テストファイル自身が明記 [P0]
- 正本: 04 §5.8 L953 (`step4b-contract-tests-ledger.md` CL40 引用)『tasks.jsonl の task 記述子
  (mode/unit_keys/output_ref) は喪失しうるが、確定先と対象 unit は決定論的に再導出できる...
  mode が不明な場合は full として扱う...この full 扱いの受け入れ検査では、差集合の unit を
  当該 job の failed_units と見なして §3.2 (V6 を含む) を評価する...合成する failed_units の
  error_kind は network_error (retryable) に固定する』
- 前提: `crates/kio-cli/tests/step4b_ledger_contract.rs:14-18` の module doc comment 自身が
  『CL40...**is not implemented and not tested here**』と明記する。`custom_id` は
  crates 全体で grep 0 件 (`mistral_ocr.rs` を含む — Batch 出力 JSONL の custom_id 概念自体が
  §O の Batch trait 不在と表裏で存在しない)。`failed_units` も §K QA36 のとおり構造として
  存在しない。
- 操作: `tasks.jsonl` が失われた状態で、provider 出力 JSONL に custom_id (=unit_key) 5 件中
  3 件のみが含まれる (2 件は転送中に欠落) 状況を用意する。当該タスクキーの prepared units
  (raw から再導出) は 5 件。
- 期待: 出力先が当該タスクキー (input_hash, tool_profile_hash) の最新 instance の未完了 unit を
  補完する先として決定論的に再導出され、mode 不明のため full として扱われ、出力に現れない
  2 件 (5件−3件の差集合) が `failed_units` として合成され、V6 (updated∪added∪failed=prepared
  全集合) の評価にこの差集合を含めることで違反にならない。現行はこの回復ロジック自体が
  存在しないため、tasks.jsonl 喪失時に当該 Batch job の出力は一切再導出されない
  (§O の Batch trait 新設・§K の failed_units 新設の両方に依存する複合ギャップ)。

### QA70 合成 failed_units の `error_kind` を実際の失敗原因に関わらず `network_error` へ固定する規則が実装されていない [P0]
- 正本: 04 §5.8 L953『合成する failed_units の error_kind は**実際の失敗原因に関わらず**
  network_error (retryable) に**固定**される...通常の retry 経路 (§5.3 exp backoff) に乗る』
- 前提: QA69 と同一の欠落 (機構自体が存在しない) に加え、仮に将来 failed_units 合成ロジックが
  実装される場合でも「error_kind を無条件に network_error へ固定する」という一見不自然な規則
  (通常は実際の失敗理由を報告するのが自然) は、既存の `error_kind` 閉 enum 検証
  (04§3.2 V6『failed_units[].error_kind は §5.3 の閉 enum との membership を必ず検査』) と
  組み合わせて初めて意味を持つため、実装時に見落とされやすい規則として単独契約化する。
- 操作: QA69 と同じ「2 件が出力に現れない」状況を用意する。
- 期待: 合成された 2 件の `failed_units[].error_kind` はいずれも文字どおり `"network_error"`
  (04§5.3 の `max_attempts=5, exp backoff` 経路) であり、転送欠落の実際の原因 (ネットワーク
  断・provider 側切り捨て等の別理由) を推測して別の error_kind を割り当てることはしない。

### QA71 ledger 層の crash 回収 (found/confirmed-absent/unknown) はビリング層で完結し、markdownize content 層への引き渡し経路が存在しない [P1]
- 正本: 04 §5.8 L1059-1091 (found/confirmed-absent/unknown の回復手順) と L953 (CL40 引用) の
  接続 — found と判定された job の出力を実際に markdownize content として復元するには、
  billing 層の「found」判定の**先**に content 層の custom_id 差分再導出 (QA69) が必要である。
- 前提: `crates/kio-pipeline/src/ledger/ops.rs` の module doc comment (1-17) 自身が
  『No 07-adapter-spec.md Batch trait exists in this codebase yet...so the actual provider
  upload/job-create/list-jobs calls this state machine drives are represented here only as
  the *data* a caller would have obtained from them』と明記する。`recovery_mark_found`
  (924-941) は「found と判定した」という**事実の記帳**のみを行い、`ops.rs` 全体を
  grep しても `markdownize` は `PER_ADAPTER_KIND_ENUM` の列挙値としてのみ現れ
  (ops.rs 側から markdownize.rs への関数呼出は 0 件)、found 判定後に実際の出力 JSONL を
  取得し unit を復元する処理へのハンドオフは存在しない。
- 操作: 照合可能な (found と判定される) Batch job の crash 回収を実行する。
- 期待: found 判定の後、当該 job の出力を取得し (§O の `fetch_output` trait メソッド新設が
  前提)、QA69 の custom_id 差分再導出ロジックへ引き渡される。現行はこの層をまたぐ接続点
  (billing 層の「found」から content 層の「unit 復元」への呼び出し) 自体が存在しないことを
  固定する — §O (Batch trait) → 本節 (found 後のハンドオフ) → §K/QA69 (差分再導出) の
  3 層依存チェーンとして実装順序を明示する。

---

## V. 解釈が割れうる点 (spec の文言からは一意に決まらない — 勝手に決めない)

1. **QA7 (effective_ignore_hash の版管理)**: 固定リテラル `"built-in-tier-a-v1"` の hash が
   「テンプレートの版」の要求を字面上満たすか (手動バージョン文字列で足りるか、パターン集合の
   実 hash が必要か) は 10§1.1 の文言のみからは確定できない。
2. **QA12 (folder config の per_adapter を schema レベルで拒否すべきか)**: 04§5.4 の「folder 側
   `[budget.per_adapter]` は定義しない」を、schema レベルの拒否と読むか、判定に使わないだけで
   記述自体は許容すると読むかは一意に決まらない。
3. **QA20 (max_input_bytes の現行実装粒度)**: 現行コードが「1 AdapterRun 単位」と「task 全体」の
   どちらで判定しているか (あるいはそもそも未実装か) は grep のみからは確定できず、実装着手前に
   該当コードの精読が必要。
4. **QA33 (bbox_annotation の TOML 形状)**: spec の literal 例 `[markdownize] bbox_annotation =
   true` (平坦 key) と現行 schema のネスト object 形状のどちらを正とするかは、07§5.2 の例示が
   厳密な形状指定を意図しているかに依存し断定できない。
5. **QA47 (embedding id 全単射の provider-id-欠如下での意味)**: provider (Gemini) が per-item id
   を返さない制約下で、07§5.3 の「全単射検査」が位置的一致 (現状) で足りるとする趣旨か、
   順序非保証を前提に真の id 突合を要求する趣旨かは文言のみから確定できない。
6. **QA50 (Vertex embedding のタスク間並列が MUST か MAY か)**: 07§5.3 実地検証パラグラフの
   「client 側の並列はタスク間で行い」という記述が規範 (必須) か許容 (可) かは、この 1 文単独
   からは確定できない。
7. **QA61 (include_neighbors キー自体の削除要否)**: U94 の統合要約自身が「削除された可能性が
   ある」と述べるに留まり断定しないため、schema からキーを削除すべきかは実装時裁定を要する。
8. **QA62 の依存関係 (Partial/settled task が consecutive_incremental_count に寄与すべきか)**:
   04§3.1 発動条件 5 は「accepted incremental 応答の finalize」を+1 の条件とするが、
   settled partial (§C QA9) が「finalize」に該当するかは 04§5.2/§3.1 の文言だけでは
   一意に決まらない。

## W. 裁定 (§V の解釈割れ — 実装用、2026-07-22 オーケストレータ裁定)

1. **QA7**: **built-in パターン集合の正規化テキストの sha256 を用いる** — 手動版文字列は更新忘れでテンプレ変更が承認記録に反映されないため不採用。目的 (何に対する承認かの固定) は実 hash が満たす。
2. **QA12**: **schema レベルで拒否** — folder config の `[budget.per_adapter]` は unknown key として KIO-E-CONFIG-SCHEMA 系 error (10 §12.3 の「enum 外の未知キーは schema error」と同じ流儀)。
3. **QA20**: **1 AdapterRun 単位で判定** (07 の AdapterRun = 1 request 規範に従う)。実装が task 全体粒度ならバグとして修正。
4. **QA33**: **spec の平坦 key (`[markdownize] bbox_annotation = true`) を正とし schema を追随** — config 例示は規範。
5. **QA47**: **現行の位置合成方式を正とする** — Adapter が入力順序から id を合成し、受入検査は合成後 id で全単射を確認。順序保証は provider 採用の前提として記録 (順序非保証 provider はこの Adapter 形式で採用不可)。
6. **QA50**: **MAY (許容)** — 実地検証パラグラフは知見の記録であり性能規範ではない。契約は「タスク内直列を壊さない」ことの固定に留める。
7. **QA61**: **schema からキーを削除** (unknown key として拒否) — spec から消えた設定の追随。再 init 方針で互換負債なし。
8. **QA62**: **寄与しない** — consecutive_incremental_count は成功 finalize のみ +1。settled partial は「accepted 応答の finalize」に該当せず、カウンタ変化なし (リセットもしない)。full 強制を遠ざけない安全側。

## 集計

| 領域 | 契約数 | P0 | P1 | P2 |
|---|---|---|---|---|
| §A task 状態機械 (U1, QA1-4) | 4 | 3 | 1 | 0 |
| §B Tier A/B 走査承認 (U2, QA5-7) | 3 | 2 | 0 | 1 |
| §C retry予算・compaction・settled (U3, QA8-10) | 3 | 0 | 3 | 0 |
| §D budget folder per_adapter 残 (U4, QA11-12) | 2 | 1 | 1 | 0 |
| §E idempotency・cost-ledger backup (U11/U12, QA13-15) | 3 | 0 | 3 | 0 |
| §F AdapterRun/Profile schema (U78, QA16-20) | 5 | 4 | 1 | 0 |
| §G opt-in ANDゲート (U79, QA21-24) | 4 | 2 | 2 | 0 |
| §H revoke機構 (U80, QA25-27) | 3 | 2 | 1 | 0 |
| §I --online/--offline (U81, QA28-31) | 4 | 2 | 2 | 0 |
| §J bbox/render_params/tool_lock_hash (U83/U84, QA32-35) | 4 | 2 | 1 | 1 |
| §K Markdownize I/O契約 (U85, QA36-40) | 5 | 4 | 1 | 0 |
| §L Normalized Markdown v1 (U86, QA41-43) | 3 | 2 | 0 | 1 |
| §M fallback_to_full/contract_violation (U87, QA44-46) | 3 | 3 | 0 | 0 |
| §N Embedding受入検査 (U88/U89/U90, QA47-51) | 5 | 2 | 1 | 2 |
| §O Batch実行契約 (U91, QA52-55) | 4 | 2 | 2 | 0 |
| §P ログ・adapter_id (U92, QA56-57) | 2 | 0 | 0 | 2 |
| §Q ストリーミング (U93, QA58-60) | 3 | 2 | 1 | 0 |
| §R include_neighbors/incremental精密化 (U94/U143, QA61-62) | 2 | 0 | 1 | 1 |
| §S staging root 3分類 (PB14/16/17, QA63-65) | 3 | 2 | 1 | 0 |
| §T registry-dup拡大 (PB24, QA66-68) | 3 | 2 | 1 | 0 |
| §U Markdownize部分回復 (CL40, QA69-71) | 3 | 2 | 1 | 0 |
| **合計** | **71** | **39** | **24** | **8** |

**契約数**: 71 件 (QA1-QA71、番号連続・欠番なし・重複なし — grep 実カウント済み。P0=39 / P1=24 /
P2=8、目安 50-70 をやや超過するが、内 10 件は regression-lock (新規実装ではなく現状固定) であり
実質的な新規ギャップ契約は 61 件)。
**解釈割れ注記**: 8 件 (§V)。**regression-lock (現状固定・回帰防止のみ)**: QA28, QA32, QA35, QA43,
QA57, QA61 (部分), QA62, QA65, QA68 = 9 件（QA51 は runtime schema coverage へ統合。historical inventory の「適合済みの可能性」再精査により
U84・U90・一部 U81/U83/U86/U92/U94/U143 を契約 1 本ずつに圧縮する方針を確定)。
