# Step 4b: spec 追随の差分票 (spec-gap inventory)

作成: 2026-07-21。**実装凍結 55c56b7 (2026-07-13) → 確定 spec fc07df4 (r41 終了・凍結解除)** の docs 差分 5,057 行から、実装挙動に影響する機構変更を棚卸しした正本。

## 作成方法

1. per-file diff を Sonnet ×5 (領域別) + GPT-5.6-sol ×1 (全量独立クロスチェック) で抽出 — 生 392 件 (矛盾 0)
2. Sonnet 統合で重複統合 → **145 項目** (U1〜U145、領域 A〜L)
3. Sonnet ×3 で crates/ への実装突合 — 各項目に「実装状態」を付与

## 実装状態の集計

| 実装状態 | 件数 | 意味 |
|---|---|---|
| 未実装 | 72 | キー概念の痕跡が実装に無い — 新規実装が必要 |
| 部分 | 46 | 骨格はあるが新規範の細部 (列・分岐・順序・code) が欠ける |
| 適合済みの可能性 | 23 | diff への映り込みの可能性大 — 着手時の精査で確定 |
| 判定不能 | 4 | 挙動の順序・意味論 — 実装読解で判定 |

## Phase 割当 (tasks 管理と対応)

- **Phase 1 (データ形式)**: A 領域の U5〜U10 (cost-ledger.sqlite 3 表 + 2 相プロトコル + sync 縮退 + device 行 — 全て未実装)、B 領域全部 (U13〜U21 events[] lifecycle — **U19 は現行実装が正反対: 再 publication を永久ブロック → retire で復活へ**)、E 領域の U35/U36 (purge journal + 読取 barrier)、J 領域の U97 (char→byte span 全域改称)・U113 (objects/image/)・U120 (epoch/lifecycle-epoch layout)
- **Phase 2 (挙動意味論)**: C (open/EEXIST/image cache)、D (restore 束縛)、E 残り、F (fsck 拡大/prune-orphans/registry-prune)、G (canonical final event 4 分岐/手順 6a/6b/verify 6 値)、H (検索 gate/cursor/時点条件/multi-scope)
- **Phase 3 (残余)**: A 残り (U1〜U4/U11/U12)、I (adapter 契約)、J 残り、K (exit/error 横断 — **具体バグ 2 件を含む: scope_unreachable が exit 4 のまま [main.rs:6721-6728] / kio_format_version 判定が schema validation より後 [scope.rs:1536]**)、L
- 「適合済みの可能性」23 件は各 Phase 着手時に該当領域分を精査して確定 (作業対象から外すか部分へ降格)

## 進め方の規約

- 契約テスト先行 (監査確定規範のテスト化 — 4 面同文系は面ごとに固定)
- migration は書かない (MVP 前 — 既存 .kio は再 init。cost-ledger は U5 の 2 相 import プロトコルが spec 側に規定されているため、それに従う)
- fix 断言句には根拠 grep (spec 監査 AJ4 教訓) / 同一 § 内の同種文は全数列挙してから「既備」判定 (AI1 教訓)

---

## A. cost-ledger / batch 2相プロトコル (04 §5.4/§5.8/§5.2/§5.3)

### U1 タスク状態機械の拡張 (paused/hold_reason/rate_limit分離/stalled batch) [P0]
- 出典: gap-04 G41, gap-10-03 G5, G6, G7, gap-07-06 G30
- spec §: 04-pipeline.md §5.1, 06-cli-spec.md (コマンド一覧), 10-operations.md §1
- 種別: schema / 挙動
- 統合要約: task状態遷移に `pending → paused → pending` を追加し、`hold_reason` enum を `budget | auth | tier_b_approval` の3値に確定する (旧仕様は budget/auth/rate_limit の3値だったが、rate_limit は paused から切り離し `pending + next_retry_at` 表示に変更)。Tier B一致ファイルの online_api 送信 task の保留状態も `pending` から `paused (hold_reason=tier_b_approval)` に変更し、対話確認による承認を「paused 解除」と定義する。照合が恒久不能な in-flight Batch job は `stalled` として表示し続け、唯一の脱出路として新設CLI `kio batch abandon <intent_token|4組>` (estimated記帳+terminal化、確認プロンプト必須、対象なしは冪等成功) を追加する。

- **実装状態: [部分]** TaskStatus::Paused は既存 (task.rs:45-52) だが `hold_reason` 3値enum・rate_limit分離・`stalled` は grep 0件。`kio batch abandon` も無く BatchCommand は Resume/Retry のみ (main.rs:264-268)
### U2 Tier A/B 走査承認ゲートと承認記録の保存先確定 [P0]
- 出典: gap-10-03 G2, G3, G19, sol G22
- spec §: 10-operations.md §1, §1.1, §12.3, 03-data-model.md §11.1
- 種別: schema / 挙動
- 統合要約: ベースライン index 完了条件を「選択肢に依らず先に完了する」から「明示承認後の実行において先に完了する」に精緻化し、`[2]`/`[3]` (online強化) の再調整中は raw object 保存を含む一切の取り込みを開始しないと新規則化する。走査承認記録の保存先を `.kio/scope.json` の `scan_approval` key (adapter単位の network opt-in `approvals[]` とは別key) に確定し、scope.schema.json にも正式keyとして追加する。Tier A 対話確認による取り込みは当該raw_hashの取り込みとして完結する一回性承認であり (再確認は内容変更時のみ)、持続的な Tier A 解除は明示 `!pattern` のみが経路で、対話承認の個別選択は pattern の解除にならないことを2箇所で明確化する。

- **実装状態: [部分]** Tier A判定 (`is_tier_a_secret_name`, scope.rs:2510) と `network_opt_in` (main.rs:754等) は既存だが `scan_approval` key は grep 0件、scope.schema.json は additionalProperties:false でその key を持たない
### U3 Retry予算カウンタ・incremental hints合成・partial task settled化・tasks.jsonl圧縮 [P1]
- 出典: gap-04 G40, G42, G43, G44
- spec §: 04-pipeline.md §5.1, §5.2
- 種別: 挙動 / 新規機能
- 統合要約: `.kio/tasks.jsonl` に bounded compaction を新設し、書き込み系コマンド冒頭で行数が既定4096行を超えたら terminal task 全行を落とし非terminal taskは最新1行のみへ再生成する (temp完書き→fsync→atomic rename)。失敗unitのみ対象のretryでmode=incrementalを使う場合のhints合成規則 (発動条件4は失敗unit集合のみを分子とする、added/removed_unit_keysは空、受け入れ検査Nは失敗unitのみ) を新設する。全unitがterminalとなり再投入対象が尽きたpartial taskは表示上partialのままtaskとしてはterminal (settled) として扱い、staging cleanupを実行しprune-orphansのblockerからも除外する。リトライ予算に関わる3カウンタ (task揮発カウンタ/batch_requests.attempts/contract_violation_count) の役割を分離し、「1回のみ」再試行のdurable判定源はcontract_violation_countでありmode切替後も別枠にならないと明確化する。

- **実装状態: [部分]** incremental hints (`added_unit_keys`/`removed_unit_keys`, main.rs:8411,10771他) は既存だが tasks.jsonl の 4096行 bounded compaction・`settled` 概念・`contract_violation_count` は grep 0件 (task.rs:20 MAX_TASK_RECORDS=100,000 の hard reject のみ)
### U4 Budget guardrail の candidate予約方式と per_adapter cap 変更 [P0]
- 出典: gap-04 G45, G46, G47, sol G34
- spec §: 04-pipeline.md §5.4
- 種別: 挙動 / schema
- 統合要約: budget cap判定式を `ledger(S, 当月) < folder_cap(S)` から `ledger(S, 当月) + candidate < folder_cap(S)` へ変更し、起動しようとするタスク自身の予約額 (candidate) を含めたcheck-then-reserve方式にする。判定と相1のreservation作成は同一の `BEGIN IMMEDIATE` Tx で行い並行超過を防ぎ、candidate=0のタスク (単価0のローカルLLM) はcap判定対象外として常に起動できる。`per_adapter` の下限判定はdevice層専用に限定し (folder capはtotalのみ)、`ledger(device, adapter_kind, 当月) + candidate < per_adapter_cap(adapter_kind)` を第三条件として追加する。`.kio/config.toml` の `[budget.per_adapter]` セクションのAdapter種別キー `markdown` は `markdownize` にリネームする。

- **実装状態: [部分]** ReservationLedger (budget.rs:124-458) が予約方式の骨格だが、`folder_per_adapter` が現存し (budget.rs:133,844。新規則は folder 側 per_adapter 廃止と矛盾)、adapter_kind文字列は本番コードで "markdown" のまま (main.rs:10685 `AdapterKind::Markdownize => "markdown"`、"markdownize"へ未リネーム)
### U5 cost-ledger.sqlite の3テーブル化・位置づけ・時刻列例外 [P0]
- 出典: gap-04 G48, G49, gap-10-03 G8, G58, G59, sol G35, gap-rest G7
- spec §: 04-pipeline.md §5.4, 10-operations.md §7.5.3, §12.4, 01-positioning.md §7
- 種別: schema
- 統合要約: cost-ledgerのストア形式を旧「3 JSONL + lock」構成から `cost_ledger` / `batch_requests` / `schema_migrations` の3 SQLiteテーブル (WAL、各表に非負性・有限性・enum等のCHECK制約) へ全面移行する (2026-07-18廃止)。cost-ledger.sqliteはKioのtruth/cache二層モデルのどちらにも属さない第三分類 (再構築不可だがcacheでもない、deviceローカルの運用データ) と明示し、SQLite schema変更は「既定rebuild」の対象外で常にin-place migration (既存行保全必須) に従う。JSONL→SQLite移行は2相 (SQLite import + schema_migrationsマーカー行を同一Tx→旧JSONLをrename) の冪等プロトコルで行い、形状検出はsqlite_masterのCREATE文canonical比較 (列存在検査のみではCHECK制約差分を検出できない) で行う。全永続データの時刻はUTC ISO8601+Z固定という原則に対し、cost-ledger.sqliteの内部時刻列 (recorded_at/job_create_started_at/stale_after_at/completed_at/created_at/schema_migrations.applied_at) のみはUTC epochミリ秒INTEGERとする例外を新設する。

- **実装状態: [未実装]** cost-ledger は JSONL+lock 構成のまま (budget.rs: CostLedger/ReservationLedger は serde `append_monthly`/`append_event` で JSONL 追記)。"sqlite"/"rusqlite"/"schema_migrations" は budget.rs・task.rs に grep 0件
### U6 Online Batch 二重課金防止2相プロトコル本体 [P0]
- 出典: gap-04 G56, sol G36
- spec §: 04-pipeline.md §5.8
- 種別: 新規機能
- 統合要約: Batch型online Adapter呼出の二重課金防止プロトコルを新規定義する。相1 (intent記録: batch_requests行INSERT/UPDATE、新規UUIDv7のintent_token、submission_seqをMAX+1採番) → 相2a (upload直前にprovider_scope_id記録、成功直後にupload_id記録) → 相2b (job作成直前にjob_create_started_atを単独小Txで記録、成功後にbatch_job_idとstate=1) → 相3 (collect: 出力persist直前にtombstone再検査、確定課金記帳+state=2+completed_atを同一Tx、upload削除は404=成功扱いで冪等再試行、全削除完了でintent_tokenをNULL化) の順序を固定する。外部に副作用を起こす前に意図を耐久記録する原則が核心であり、旧token照合・掃除完了後にのみ次の相1を開始する。

- **実装状態: [未実装]** intent_token/batch_job_id/provider_scope_id/upload_id/submission_seq は crates全体で grep 0件。2相プロトコルの型・状態機械が存在しない
### U7 cost_ledger記帳の冪等性・outcome enum・billable_units事前検証 [P0]
- 出典: gap-04 G57, G58, G59
- spec §: 04-pipeline.md §5.4, §5.8
- 種別: schema / 挙動
- 統合要約: cost_ledgerへの記帳は `INSERT ... ON CONFLICT DO NOTHING` を必須とし、記帳済み判別は同一タスクキー×`batch_job_id IN (発見job id, 当該intent_token)` の既存行で行う。job id不明の記帳 (期限超・abandon) はsubmission_seqを+1へUPDATEしてから新値でestimated行を記帳する (旧seqのままだと次の正規closeがUNIQUE衝突でDO NOTHINGに吸収されるため)。`cost_ledger.outcome` 列に閉enum (`succeeded`/`contract_violation`/`expired`/`abandoned`/`submit_rejected`/`purged`/`unknown_settled`/`fallback_to_full`) を新設し各終端TxのINSERTで明示必須とする。Adapter報告値 (usd/billable_units) のINSERT前検証規則 (1要素以上・count有限非負整数・kind閉enum内かつ一意・単価解決可能) を新設し、違反時はprovider報告値を使わずestimated_usdでestimated=1記帳し同一Txでterminal化する。

- **実装状態: [未実装]** cost_ledger.outcome 閉enum・`ON CONFLICT DO NOTHING` 冪等記帳・billable_units事前検証は該当SQLテーブル自体が不在のため無し (U5と同根)
### U8 Batch照合不能時の回復手順 (found/confirmed-absent/unknown) [P0]
- 出典: gap-04 G60, sol G37 (回復部分)
- spec §: 04-pipeline.md §5.8
- 種別: 新規機能
- 統合要約: 書き込み系batchコマンド冒頭で行う回復手順を新規定義する。found (job一覧でtoken一致、追跡続行し相3へ) / confirmed-absent (記録scopeの全ページ走査済み一覧に不在確認+可視化猶予10分経過) / unknown (照会不能、回復期限48h超でestimated記帳) / 恒久unknown (`kio status`にstalled表示、`kio batch abandon`が唯一の脱出路、intent_tokenは残骸掃除完了までNULL化しない) の4状態に分類し、残骸掃除完了後にのみ新しい相1を開始する順序規範を定める。

- **実装状態: [未実装]** found/confirmed-absent/unknown の回復状態、`kio batch abandon` ともに grep 0件
### U9 sync online呼出の縮退2相プロトコル参加 [P0]
- 出典: gap-04 G50, gap-05 G4, sol G38
- spec §: 04-pipeline.md §5.4, 05-runtime.md §1.1
- 種別: 新規機能
- 統合要約: 従来2相プロトコル (§5.8) の対象はBatch型呼出のみだったが、sync (非Batch) online呼出もbatch_requests行 (`request_kind='sync'`) を用いた「縮退2相」(upload/job相なし、相1のみ+終端) に参加するよう拡張する。呼出後の終端記帳・state=2/3は同一Txで行い、cost_ledgerへは終端の確定行のみ追記し、複数external callを行うタスクはrequestを直列化する。query embedding (vector|hybrid検索page1) の課金もこの縮退2相に載せ、`scope_id='device'` のsync requestとして記帳しfolder cap対象外・device cap/per_adapterは通常合算とする。

- **実装状態: [未実装]** batch_requests(request_kind='sync') の縮退2相、query embeddingのdevice課金記帳は不在 (batch_requestsテーブル自体が無い)
### U10 query embedding のdevice行claim機構 (stale_after_at/sweep/pruning) [P0]
- 出典: gap-04 G51, G52, G53, G54, sol G39
- spec §: 04-pipeline.md §5.4
- 種別: 新規機能
- 統合要約: vector|hybrid検索page1のquery embedding requestを `scope_id='device'` (予約値) のsync行として扱う機構を新設する。sync行専用の `stale_after_at` (相1で耐久保存する回収期限、実効timeout+60秒マージン下限600秒) はRetry-After受信時に自tokenのCAS UPDATEで単調延長し (`max(現行値,...)`)、延長UPDATEが0行なら claim喪失として以後の処理を全て中止する。`scope_id='device'` 行のstale回収・剪定は1回の実行あたり合計256行を上限とするbounded処理とし、(1) 自keyのstale行を上限枠外で最優先回収、(2) 剪定に最低128行を保証、(3) 残余枠を一般stale回収に充てる。terminal device行 (state IN (2,3) ∧ intent_token IS NULL ∧ contract_violation_count=0 ∧ completed_atが前月以前) は成功終端も含めDELETEしてよい。

- **実装状態: [未実装]** stale_after_at・scope_id='device'行・256件bounded sweepは grep 0件
### U11 LLM API idempotency要求の二段階化 [P1]
- 出典: gap-04 G63
- spec §: 04-pipeline.md §5.5
- 種別: 挙動
- 統合要約: 二重課金防止の手段を、旧「Adapter層にidempotency_keyを一律要求」から「sync呼出はproviderがidempotency keyを提供する場合にそれを要求し、Batch投入は§5.8の2相プロトコルを正本とする」という条件付き二段構えへ変更する。Batchではjob作成時にidempotency keyを持たないproviderが現実的に存在するための対応。

- **実装状態: [未実装]** task.rs:910 `idempotency_key(input_hash, tool_profile_hash)` はタスク重複排除用の別概念で、LLM API呼出へのidempotency二段階要求 (provider提供時のみ要求/Batchは§5.8正本) とは無関係
### U12 cost-ledgerのバックアップ・復元後reconcile [P1]
- 出典: gap-10-03 G56, G57
- spec §: 10-operations.md §7.5.2
- 種別: 新規機能
- 統合要約: デバイスグローバルな `cost-ledger.sqlite` は `.kio` コピーに含まれないため `sqlite3 ... .backup` による別バックアップ手順が必要と規定し、復元後は `PRAGMA integrity_check` + 両表存在確認、§5.8の回復 (reconcile) 完了まで新規Batch投入禁止とする。復元DBが投入記録を欠く場合、provider_scope全走査でbatch_requestsに対応行の無いjob/uploadを検出しtask key4組で帰属判定、ローカル構成scopeに一致するjobはorphan候補として報告 (結果取得・削除を案内)、一致しないjobはunknownとして報告のみ (自動再投入・自動削除はしない) とする。

- **実装状態: [未実装]** cost-ledger.sqlite自体が無い (U5) ため backup/reconcile手順 (`.backup`, `integrity_check`, orphan job判定) も crates 内 grep 0件 (docs/10-operations.mdに文言のみ)
## B. tombstone / erase receipt lifecycle (05 §3.5 / 10 §7.5.1)

### U13 tombstone の events[] lifecycle スキーマ化 (v1→v2) [P0]
- 出典: gap-05 G63, gap-10-03 G51 (tombstone側), sol G4 (schema部分)
- spec §: 05-runtime.md §3.5, 10-operations.md §7.5.1
- 種別: schema
- 統合要約: tombstoneのデータ構造を旧spec の平坦JSON (`purged_at`/`purged_reason`/`purged_in_commit`) から、raw_hashをキーとするappend-onlyの `events[]` 配列 (kind=`purged`/`retired`の2種、active判定=末尾eventが`purged`であること) へ変更する。旧flat形式は「purged event 1件」として読み、次のmutation時に一回だけevents形式へ変換する後方互換規則を持つ (5値enum外のreasonは`other`+`legacy_reason`で保全)。2026-07-19以降のeventはepoch (purged/erased)・reason (5値enum、erased必須)・lifecycle_epoch (全種必須) を必須field化し、event列の遷移文法 (purged開始でpurged/retired交互) を検証する。

- **実装状態: [未実装]** TombstoneRecord は旧flat形式のまま (purge.rs:107-111 `purged_at`/`purged_reason`/`purged_in_commit`)。`events`配列・kind enum(purged/retired)は grep 0件
### U14 erase receipt の events[]化と保持方針の反転 [P0]
- 出典: gap-05 G64, G65, gap-10-03 G51 (erase receipt側)
- spec §: 05-runtime.md §3.5, 10-operations.md §7.5.1
- 種別: schema / 挙動 (破壊的変更)
- 統合要約: erase receiptを`schema_version: 1`の平坦形式 (`purged_in_commit`/`erased_at`) から`schema_version: 2`のevents[]形式 (kind=`erased`/`retired`、reason/epoch/lifecycle_epoch付き) へ変更する。v1形式は「erased event 1件」として読み、次mutationでv2へlocked変換する (v1にreasonが無いため`reason:"other"`を合成)。旧spec は「raw objectの再publication成功後にreceiptを除去し、crash時はverified rawを優先してstale receiptを除去する」だったが、新spec は「re-publication成功時もreceiptを除去せず`retired` eventをappendする」に反転する (除去すると旧commitが参照するmanifest欠落の説明が消え、corruption誤判定を生むため)。

- **実装状態: [未実装]** EraseReceipt も `schema_version: 1` flat形式のまま (purge.rs:141-145)。`retire_erase_receipt` (purge.rs:523-530) は再publication時に receipt を `quarantine_then_unlink` で物理削除する旧挙動そのもの (呼出元 scope.rs:554-555)。`retired` event追記の実装は無い
### U15 lifecycle-epoch 単調カウンタと巻き戻り検出 [P0]
- 出典: gap-05 G53
- spec §: 05-runtime.md §3.5
- 種別: 新規機能
- 統合要約: `.kio/tombstones/lifecycle-epoch` を、event append (retire・再purge・legacy変換) ごとに同一lock下で+1する単調カウンタとして新設し、`index_metadata.last_lifecycle_epoch` へ回転済み反映値を記録する。巻き戻り検出は「counter < max(last_lifecycle_epoch, 全event記録lifecycle_epoch最大値)」の機械条件のみで行い、検出時はmax+1で再作成し無条件でindex_generationを1回転する。読取系は冒頭検査でcounterとlast_lifecycle_epochの不一致 (>も<も) をKIO-E-INDEX-REBUILDING-001相当のretryable (exit 3) として返す。

- **実装状態: [未実装]** `lifecycle_epoch`/`last_lifecycle_epoch`/`lifecycle-epoch` は crates全体で grep 0件
### U16 marker validity検証の意味論的検証全面刷新 [P0]
- 出典: gap-10-03 G51, sol G4 (検証部分)
- spec §: 10-operations.md §7.5.1
- 種別: schema / 挙動
- 統合要約: erase receipt/tombstoneのvalidationをschema_versionで分岐する構造へ全面刷新する。v2 (events[]) はkind別必須field (purged=at/in_commit/reason/actor、erased=at/in_commit/actor、retired=at/in_commit/actor/resurrection_commit) を検査し、遷移文法検証 (tombstoneはpurged開始でpurged/retired交互)、terminal retiredのresurrection_commitがref-reachableかつ直前purge/erased eventのin_commitのancestorであることを必須化する。v1 flatは1件のerased eventに正規化してから同一validatorに通し、検証失敗markerは説明能力なしとしてcorruption扱いとする。

- **実装状態: [未実装]** TombstoneRecord/EraseReceipt の `validate()` は hash/timestamp形式検査のみ (purge.rs:133-134,165-170)。schema_version分岐・kind別必須field・遷移文法検証は無い
### U17 fsckのpurge整合判定刷新 (説明範囲限定・purged/retired両対応) [P0]
- 出典: gap-10-03 G49
- spec §: 10-operations.md §7.5.1
- 種別: 挙動
- 統合要約: tombstoneが説明する正常dead terminalの判定を「purgedのみ」から「purged/retiredのいずれでも」に拡張する (retireはeventを削除せず監査を残すため)。derived scopeにmanifest objectを追加し、新規に「説明範囲の限定」規則を設ける: tombstone/erase receiptが説明できるのは当該purge eventのin_commit**以前**の commitが参照するclosureに限り、retire後に再作成・再公開されたobjectの欠落はcorruptionとする (古い退役eventが新規破損を隠さないため)。tree欠落は`.kio/gc/shallowed/<commit64>` receiptが説明する場合のみ正常。

- **実装状態: [未実装]** fsckのtombstone判定は「purgedのみ正常」固定 (verify_objects.rs:697-706)。retired対応・`shallowed`・説明範囲(in_commit以前限定)は grep 0件 ("shallowed" 0件)
### U18 verified raw と marker 共存の修復ロジック全面刷新 (receipt非除去) [P0]
- 出典: gap-10-03 G50
- spec §: 10-operations.md §7.5.1
- 種別: 挙動 (破壊的変更)
- 統合要約: 旧spec の「verified rawとstale receiptが共存する場合はrawを正としてlocked repair完了時にreceiptを除去する」という単純規則を、canonical final event (events[]の末尾) を基準にする詳細ロジックへ全面置換する。(1) canonical final eventが`retired`なら共存は正常 (resurrection)。(2) `erased`のままverified rawがあり再publication commitが存在するなら`retired`をappendして整合。(3) `purged`(tombstone)のままverified rawがあり再publication commitが存在するなら同様にappend、存在しなければincomplete purgeとしてexit 3で報告しappendしない (回復は`kio purge --raw-hash`の再実行)。**receiptは除去しない**(旧spec と反対の方針転換)。commit未存在時は「未finalizeの進行状態」としてincomplete扱いとする。

- **実装状態: [未実装]** tombstone+receipt共存はfindingとして検出するのみ (verify_objects.rs:687-691 "tombstone and erase receipt coexist")。canonical final event基準の詳細repairロジックは無く、receiptは旧来どおり除去対象 (retire_erase_receipt)
### U19 tombstone retire (resurrection) の基本フローと補完規則 [P0]
- 出典: gap-05 G52, G54, gap-rest G30, sol G4 (挙動部分)
- spec §: 05-runtime.md §3.5
- 種別: 新規機能
- 統合要約: 同一raw_hashのraw objectが再publicationされた場合、その publicationと同一のlocked mutation内でactive tombstoneをretire (events[]へ`retired`をappend) させる基本フローを新設する。耐久順序として、retire appendは再publicationのsnapshot finalize (chunks.jsonl→SQLite→commit/ref publish) の完了後に行い、間でcrashした場合はtombstoneがactiveのまま残る (安全側、解決はtombstoned)。次回のlocked mutationまたはfsckが「canonical final eventがpurgedのままのtombstone×verified raw (content hash検証済み) の存在×同一rawのref到達可能な再publication commit」を検出したらretired eventを補完し、`resurrection_commit`を記録する (raw欠落・破損のままの補完は不可)。この因果条件を満たす再publication commitが無い共存はincomplete purge (exit 3) として補完しない。復活後に解決される本文は再生成instanceのものであり、purge前とbyte同一である保証はない (normalized_hash不採用の帰結)。

- **実装状態: [未実装]** (突合者注記 = 矛盾: 現行はむしろ逆方向の実装) 既存 tombstone の raw_hash への再 publication は `KIO-E-PURGE-TOMBSTONED-001` で永久ブロックする (scope.rs:2937-2944, main.rs:2043-2045 "Public tombstones permanently reject identical-byte re-ingest")。resurrection/`retired` 化フローが無く、新規則と正反対の挙動

### U20 canonical final event 判定ロジックの二用途分離 [P1]
- 出典: gap-05 G55
- spec §: 05-runtime.md §3.5
- 種別: 挙動
- 統合要約: search/open/evidence verify等のresolver系は08§3.1手順5のcanonical final event判定 (全marker集約による正本化) を共有する一方、fsck・再purge (marker自身のlifecycle管理) は各markerの末尾event規則を独自に使う、という使い分けを新規則化する。raw不変条件・修復の判定だけはcanonicalを基準にする。

- **実装状態: [未実装]** events[]自体が無い (U13) ため、resolver向けcanonical final event判定とfsck向け独自末尾event判定という2用途分離の概念が成立しない
### U21 erase receipt の用途範囲の明示列挙による限定 [P2]
- 出典: gap-05 G50, gap-rest G29, G46
- spec §: 05-runtime.md §3.5, 08-evidence-pointer-spec.md §4.2, 09-mvp-scope.md §5.3
- 種別: 挙動
- 統合要約: `--erase-tombstone`のerase receiptの用途を、旧spec の「fsck専用」という曖昧な記述から、「fsckの欠落説明・08§3.1手順5 (ii)〜(iii)のnot_found分類・手順6bの欠落説明・resurrection link・同一marker自身のlifecycle管理 (retired/再erasedのappend) にのみ使用可」という明示列挙に限定し、この列挙が用途の正本であると宣言する。完全削除の実装手段が`--erase-tombstone` (public tombstoneなしのNOT-FOUND化) であると明記し、これがtree/commitの再結線やfilename秘匿を伴う履歴書き換えを含まないこと (それらは引き続きv2+/Phase 4+) も明確化する。

- **実装状態: [判定不能]** `read_erase_receipt`呼出箇所は fsck(verify_objects.rs)・ingest gate(scope.rs:2945, main.rs:2063)・restore(restore.rs:1716) に限定され、列挙方針と大枠矛盾しないが、08§3.1手順5/6bとの厳密な用途一致はコード読解のみでは確定できない (evidence verify経路での明示的な呼出は未確認)
## C. open / 一時展開 cache (06 §1.1 / 05 §3.5 の cache 面)

### U22 kio open の解決手順全面改訂 (object URI type=image限定・tombstone最優先判定) [P0]
- 出典: gap-07-06 G42, gap-rest G19, sol G56
- spec §: 06-cli-spec.md §1.1, 08-evidence-pointer-spec.md §2.3, 10-operations.md §7.5.1
- 種別: 新規機能 / schema
- 統合要約: `kio open` の解決手順を全面改訂する。新設の手順1aとして object URI (`kio://<scope_id>/object/image/<image_hash>`) の解決処理を追加し、MVPで発行・受理されるのはtype=imageのみ (他typeは受理側でも拒否、新type追加は06§1.1でopen semanticsを定義してから) と限定する。scope_id不一致でも自storeに同一hashがあれば解決してよく (fork複製由来のURIも自storeで解決)、image objectは `~/.cache/kio/open/image/<image_hash digest64>/` という型分離されたdir (raw系と平坦namespaceでは digest衝突し得るため) に配置する。手順2としてtombstone判定 (canonical final eventが`purged`ならexit 4) を最優先の独立手順として明確化する。

- **実装状態: [部分]** object URI解決 (`parse_object_uri`, main.rs:6779-6813) は raw/image/chunk/normalized/prepared の5型を受理しており、type=image限定という新規則に反する (main.rs:6797 `VALID_TYPES`)。tombstone判定は `enforce_purge_read_barrier`/journal barrier経由で存在するが新設「最優先の独立手順」としての構造化はない。image cacheは型分離なしの平坦namespace (`open_cache_path`, main.rs:6259-6264 `cache_home()/kio/open/<hash>/...`)
### U23 raw/image 一時展開の耐久publish+起動直前3点検査 [P0]
- 出典: gap-07-06 G43, gap-05 G61
- spec §: 06-cli-spec.md §1.1, 05-runtime.md §3.5
- 種別: 新規機能 / 挙動
- 統合要約: raw/image objectの一時展開処理を、旧「単純に read-only 展開してOS既定アプリで開く」から「private temp書き込み→cache pathへno-replace publish→起動直前の3点最終検査 (journal/epoch/lifecycle counter)」という手順へ全面改訂する。publish競合 (EEXIST) 時は既存cacheの内容sha256を再計算照合し、不一致は改変・破損の残骸として `KIO-E-STORE-CORRUPT-001` (exit 4) でfail-closedに終端する。OSアプリ起動の直前 (一時展開のcache publish後) に再検査するのは起動後が取消不能なためであり、拒否時は当該一時展開 (publish済みcacheを含む) をdev/inode対照の上で除去して終端する。

- **実装状態: [部分]** `write_open_cache_atomic` (main.rs:6272-6312) はtemp+fsync+rename の耐久publishを実施済みだが、cache hit時は既存ファイルをsha256再照合せず無条件再利用 (main.rs:6128-6141、コメント "does NOT re-verify bytes")。EEXIST時のcorruption検出・fail-closed (`KIO-E-STORE-CORRUPT-001`)は無い。3点起動前検査(journal/epoch/lifecycle counter)はepoch/lifecycle_epoch自体が不在 (U15)のため不成立
### U24 open cache の purge/prune-orphans 時冪等削除 (raw/image 型分離) [P1]
- 出典: gap-05 G45, gap-10-03 G53
- spec §: 05-runtime.md §3.5, 10-operations.md §7.5.1
- 種別: 新規機能
- 統合要約: purge対象に `~/.cache/kio/open/<raw_hash digest64>/` の一時展開dirの冪等削除を追加する。物理削除対象となったimage (live参照0) の一時展開dir `~/.cache/kio/open/image/<image_hash digest64>/` も `image/` のtype segmentでraw系dirと分離した上で同様に冪等削除する (live参照が残る共有imageのcache dirは削除しない)。`kio repair --verify-objects --prune-orphans` はcanonical final eventがpurged/erasedのraw_hashについて同cache残存を検査し削除対象に含め、image cacheも同様に対応削除する (open publish後・起動直前検査前のcrash窓で残る平文cacheの回収経路)。

- **実装状態: [部分]** `evict_open_cache` (purge.rs:1000-1014) は既に image/prepared含む cache_hashes を削除対象化している (purge.rs:623-630、`removable_prepared`/`removable_images` は live参照0のみ、purge.rs:576-608) が `image/` 型分離は無く flat namespace。`--prune-orphans` フラグは crates全体で grep 0件 (verify_objects.rsに同機能なし)
## D. restore (05 §4 / 06 §5)

### U25 restore 宛先の安全検査 (scope root配下拒否 + dirfd containment) [P0]
- 出典: gap-05 G66, G67, gap-07-06 G33
- spec §: 05-runtime.md §4.1, 06-cli-spec.md §5
- 種別: エラー分類 / 新規機能
- 統合要約: `--to` のcanonical解決先が当該scope root配下 (`.kio` 含む) の場合、`KIO-E-CONFIG-USAGE-001` (exit 2) で拒否する新規則を追加する (`--to .` による禁止の迂回を許さない)。canonical解決は§1.8のcanonical root_path算出規則 (絶対化→lexical解決→末尾separator除去→realpath) と同一を適用する。restore展開は検証済み`--to`ディレクトリのdirfd配下でno-follow (symlink不追跡) に行い、`--to`をO_DIRECTORYでopenしfstat (dev/inode) をcanonical解決先のlstat (containment判定時取得値) と対照して同一実体を確認してから以後のtemp作成・renameを同一dirfd配下に限定する。対照不一致は同じくKIO-E-CONFIG-USAGE-001 (exit 2)。絶対path・".."を含む復元エントリは拒否する。

- **実装状態: [部分]** scope root/.kio配下拒否は既存 (`validate_destination`, restore.rs:537-556) だがエラーコードは `KIO-E-COMMIT-RESTORE-UNSAFE-001`/`ExitCode::Failure` (新規則は `KIO-E-CONFIG-USAGE-001`/exit 2、restore.rs:961-968)。dirfd containmentは cap-std の `open_dir_nofollow`/ambient authority (restore.rs:716-803) で類似機構が既存だが、dev/inode fstat対照までは未確認
### U26 restore の退避・隔離・no-replace publish protocol [P0]
- 出典: gap-05 G58, G59, gap-07-06 G33, sol G57
- spec §: 05-runtime.md §3.5, §4.1, 06-cli-spec.md §5
- 種別: 新規機能
- 統合要約: 出力名・上書き対象名が `.kio-restore-bak`/`.kio-restore-quarantine` で終わる場合はmutation前に明示拒否する (退避・隔離名前空間の予約)。既存の同名残存があれば `--force` 有無・宛先存否に関わらず先行restoreの未完残存として拒否+回復案内する。`--force` 上書き時は旧ファイルを退避名 `<basename>.kio-restore-bak` へno-replaceで保全してから publish し、publishのrenameは非`--force`・`--force`とも no-replace相当 (RENAME_NOREPLACE等) で行い競合検出時は無変更で失敗する。restoreはrename完了後に3点再検査 (journal/epoch/lifecycle counter) を行い、対象raw closureを含むactive journal検出時は終端、purge完遂検出時は巻き戻す。巻き戻しはpublish済みファイルをunlinkせず同一directory内の決定的隔離名 `<basename>.kio-restore-quarantine` へno-replace renameで隔離し、renameした実体をfstatのdev/inode対照で自らのpublishと検証する方式 (対照→削除の2操作では窓が残るため) を用いる。復帰後はpreflightと同一応答 (purged→tombstone、erased→KIO-E-PURGE-NOT-FOUND-001) で終端する。

- **実装状態: [未実装]** `.kio-restore-bak`/`.kio-restore-quarantine` 予約名前空間・退避publish・隔離rename方式は grep 0件。`--force`上書きは既存ファイルの `symlink_metadata` 検査後に直接上書きする様子 (restore.rs:387-398)
### U27 restore競合のエラー分類統一 (KIO-E-COMMIT-RESTORE-CONFLICT-001) [P0]
- 出典: gap-05 G60, gap-07-06 G33
- spec §: 05-runtime.md §3.5, §4.1, 06-cli-spec.md §5
- 種別: エラー分類
- 統合要約: restoreの競合終端を全て `KIO-E-COMMIT-RESTORE-CONFLICT-001` (retryable exit 3) に統一し、contextに閉enum `conflict_kind` (publish_race/quarantine_rename_race/quarantine_mismatch/backup_mismatch/restore_rename_race/stale_backup/stale_quarantine) と `retry_disposition` (transient=publish_raceのみ、他はmanual_action) を持たせる。

- **実装状態: [部分]** `KIO-E-COMMIT-RESTORE-CONFLICT-001` は既存 (restore.rs:392) だが「宛先ファイル既存+`--force`無し」の単一caseのみに使用 (restore.rs:387-397)。`conflict_kind`/`retry_disposition` enumは grep 0件
## E. purge closure / journal / epoch (05 §3.5 の purge 本体)

### U28 purge CLI構文の確定 (path|--raw-hash・reason 5値閉enum・--yes) [P0]
- 出典: gap-05 G40, G41, gap-rest G9, G10, G11
- spec §: 05-runtime.md §3, 02-philosophy.md §2.4, §6.1, 06-cli-spec.md §6
- 種別: schema (破壊的変更)
- 統合要約: purge CLIの構文を `kio purge <path|raw_hash> --reason <legal|privacy|misingest|copyright|...>` から `kio purge <path|--raw-hash <h>> --reason <legal|privacy|misingest|copyright|other>` に変更する。raw_hash指定は位置引数から `--raw-hash` フラグへ、reasonの自由記述可能な `...` は閉enum `other` に変更し、misingest (誤取り込みの是正) の適用範囲が秘匿文書に限らないことも追加する。確認は対話プロンプト必須に加え、非対話実行向けの `--yes` (確認プロンプトスキップ) を新設する。

- **実装状態: [適合済みの可能性]** `PurgeArgs` (purge.rs:49-68) は `path: Option<PathBuf>` / `--raw-hash` / `reason`(閉enum) / `--yes` を完全に持つ。`PURGE_REASONS` (purge.rs:38) = ["legal","privacy","misingest","copyright","other"] で新規則と正確に一致
### U29 purgeの保証範囲反転 (snapshot DAG非書換) と実行順序の確定 [P0]
- 出典: gap-10-03 G42, gap-rest G8, G12 (順序部分)
- spec §: 10-operations.md §7, 02-philosophy.md §2.4, §6.1
- 種別: 挙動 (破壊的変更)
- 統合要約: 旧spec は「purgeはsnapshot DAG (tree/commit) から対象ファイル由来の情報を削除する操作」としていたが、新spec は明確に反転する: snapshot DAG (commit/tree object) は書き換えない — tree entryのメタデータ (path, raw_hash) は履歴に残る。削除事実の記録 (tombstone) を物理削除より先に耐久化する順序を明示し (クラッシュ時に「消えたのに痕跡が無い」状態を防ぐため)、UI推奨文言も「Kio管理下の履歴から完全削除」から「Kio管理下の本文と派生物を全履歴から削除 (ファイル名と存在の記録は履歴に残ります)」へ変更しこの挙動反転を反映する。

- **実装状態: [適合済みの可能性]** `purged_snapshot` (scope.rs:931-967) は `excluded_paths` 空でtree/commitのentryを書き換えず (working tree再scan方式)、`PurgedCommitCreated`相 (purge.rs:264-268) が `ContentDeleted`相 (purge.rs:274-278) より先行しterminal record(tombstone)を先に耐久publish済み — DAG非書換・削除前記録の両方が既に成立
### U30 purge削除対象の拡大 (prepared/image追加・manifest object・共有派生live参照0条件) [P0]
- 出典: gap-05 G44, gap-10-03 G44, gap-rest G12 (範囲部分), sol G5
- spec §: 05-runtime.md §3.5, 10-operations.md §7, 02-philosophy.md §6.1
- 種別: 挙動
- 統合要約: purgeの物理削除対象リストを旧「raw/normalized/chunk/embedding/evidence/index」から「raw/prepared/image/normalized/chunk/embedding」(manifest object含む) へ変更する。共有されうる派生 (prepared/image/embedding) は無条件削除せず、purge対象外のlive参照が0の場合のみ物理削除する (無条件削除は非対象文書の検索・再構築を破壊するため)。manifest objectは当該(raw_hash, tool_profile_hash)の全gen・全確定版が対象に含まれる。

- **実装状態: [適合済みの可能性]** `delete_derived_surfaces` (purge.rs:517-631) は既に raw/prepared/image/normalized/chunk/embeddingとmanifestを対象化し (purge.rs:589-619)、`shared_prepared`/`shared_images` (live参照>0、purge.rs:576-587) を削除除外している
### U31 SQLite / chunks.jsonl の purge範囲の具体化 [P0]
- 出典: gap-05 G47, G48
- spec §: 05-runtime.md §3.5
- 種別: schema
- 統合要約: purge対象のSQLite行に `chunk_config_generations`/`chunk_publications` を追加する。`chunk_vec` は対象chunk_idの行に限定し、`embeddings` 行はobject側と同じくlive参照0の場合のみ削除する (共有text_hashの行を無条件に消すと非対象文書のvector検索がrebuildまで欠けるため)。`target_type='query_cache'` のembeddings行は削除候補から除外する。chunks.jsonlのpurge範囲は「対象chunk_idを参照するcreation行・publication event行の全部」と規定する (append-onlyの例外としてpurgeは法務要件の明示例外で行を落とす)。

- **実装状態: [部分]** `chunk_vec`は対象chunk_id限定、`embeddings`はtarget_type='chunk'かつ他chunk非参照時のみ削除でquery_cache行は自然除外、`chunk_config_generations`も対象 (すべてfts.rs:245-306の`purge_raw`) だが `chunk_publications` テーブル自体が crates全体で grep 0件
### U32 staging の purge範囲拡大と帰属列挙方式の変更 [P1]
- 出典: gap-05 G49
- spec §: 05-runtime.md §3.5
- 種別: 挙動
- 統合要約: 対象raw_hashに帰属するtaskのstagingを、task状態を問わず (retryable failedの保全stagingを含む) purge対象とする新規則を追加する。帰属列挙の正本は `.kio/staging/` の耐久descriptor全走査でありtasks.jsonl非依存とし、task記録喪失後も削除対象を列挙できるようにする。

- **実装状態: [未実装]** `delete_target_tasks` (purge.rs:852-905) はtasks.jsonl全件を状態問わず対象にする点は新規則と一致するが、正本は引き続き TaskStore(tasks.jsonl) であり `.kio/staging/` descriptor全走査への移行は無い。staging実ファイル自体の削除処理も purge.rs に grep 0件 ("staging"はコメント1件のみ)
### U33 purgeのログscrub範囲をscope_id単位に限定 [P1]
- 出典: gap-10-03 G43
- spec §: 10-operations.md §7, §12.6
- 種別: 挙動
- 統合要約: purgeのログscrub対象を旧spec の「対象のraw_hash/path/queryを含む行」から新spec の「当該scopeのscope_idを持ち対象のraw_hash/path/queryを含む行」に変更する。device-global logの別scopeの同一raw_hash行には触れないようにし、scope由来の行はscope_idを必須fieldとする規約を追加する。

- **実装状態: [未実装]** `scrub_logs` (purge.rs:1016-1064) はdevice-global logをscope_id条件無しでraw_hash/pathのみ照合 (purge.rs:1027-1032 `identifiers`にscope_idを含まない)。scope_id限定フィルタは無い
### U34 working tree残存原本の警告義務化 [P1]
- 出典: gap-05 G51
- spec §: 05-runtime.md §3.5
- 種別: 新規機能
- 統合要約: purgeのpreview/完了表示は、対象raw_hashと同一bytesの原本がworking treeに残存する場合に必ず警告する新規則を追加する。残存原本は次回`kio index`の自動scanで再取り込みされ既存pointerが再びaliveになるため、恒久的除外には原本削除または `.kioignore` 追加が必要と案内する。

- **実装状態: [未実装]** working tree残存原本への警告文言・フィールドは purge.rs に grep 0件
### U35 purge journal 機構本体 (record構造・phase順序・crash回復) [P0]
- 出典: gap-05 G56, sol G58 (journal部分)
- spec §: 05-runtime.md §3.5
- 種別: 新規機能
- 統合要約: purgeが複数ストアを跨ぐ破壊操作であることに対し、mutation前に `.kio/purge/journal` へ対象closure・phaseを耐久記録し (fsync+atomic rename)、各phaseを冪等に再開できる機構を新設する。journal record構造 (purge_id/raw_hash群/reason/actor/target_epoch/closure/planned_commit等)、phase順序 prepared→tombstoned→deleted→committed→done (doneはepoch更新→journal除去の順序固定、逆順はABA窓を生むため禁止) を定義する。journal active中のfsckはincomplete (exit 3) として扱う。

- **実装状態: [部分]** `PurgeJournal` (purge.rs:178-189) は耐久journal+phase機構 (`Prepared→BarrierPublished→PurgedCommitCreated→ContentDeleted→DerivedDeleted→LogsScrubbed`, purge.rs:77-84) を持ち、fsync+atomic rename・冪等再開(`BeginOutcome::Resumed`)は既存だが、新規phase名(prepared/tombstoned/deleted/committed/done)や `purge_id`/`actor`/`target_epoch`フィールドは無い
### U36 読み取り系コマンドのpurge journal/epoch 2点検査とfail-closed回復 [P0]
- 出典: gap-05 G57, sol G58 (read barrier部分)
- spec §: 05-runtime.md §3.5
- 種別: 新規機能 / エラー分類
- 統合要約: 読み取り系コマンド (search/log/view/inspect/evidence verify/restore/diff/open) は冒頭と「本文・存在情報を返す直前」の2点で「active journal不在かつpurge/epoch不変」を検査し、違反なら `KIO-E-PURGE-JOURNAL-ACTIVE-001` (retryable exit 3) で拒否する (2点目検出時は取得済み結果を破棄)。epoch fileの欠落・不正値も同様にfail-closedで拒否し、journal/全lifecycle event記録epochの最大値+1から単調性を回復して再作成する。`kio status` のみ拒否せずactive journal状態を表示する。

- **実装状態: [部分]** `enforce_purge_read_barrier` (main.rs:6639-6647) はraw_hash単位の `journal.blocks()` 検査を持つが (purge.rs:417-422)、`KIO-E-PURGE-JOURNAL-ACTIVE-001` は grep 0件、epoch不変検査も epoch自体不在 (U15) のため無い。冒頭/直前の2点検査かは未確認
### U37 purge時のin-flight外部実行タスクとの整合 [P0]
- 出典: gap-05 G62
- spec §: 05-runtime.md §3.5
- 種別: 新規機能
- 統合要約: purge prepared相で、当該scopeの対象raw_hashを入力とするpending/running外部実行タスク (batch_requests state 0/1、batch/sync両方) をabandon相当でterminal化しprovider上の対応uploadを掃除する新規則を追加する (scope_id条件が無いと別scopeの実行中requestまで掃除してしまうため)。対象raw_hashのterminalだがintent_token残存 (残骸掃除未完) の行のprovider残骸掃除も同prepared相で完遂する。

- **実装状態: [未実装]** purge prepared相でのbatch_requests state0/1 abandon整合はbatch_requests自体が不在のため無し (U6と同根)
### U38 二重purge (再purge) の挙動確定 [P1]
- 出典: gap-rest G45
- spec §: 09-mvp-scope.md §5.3
- 種別: 挙動
- 統合要約: 旧仕様では「tombstone自体をpurgeする操作 (二重purge) の有無」が残未決だったが、既に purge済みのraw_hashを再度purgeすると、同一raw_hashのlifecycle `events[]` へ新たな`purged` eventを追加appendすると確定する。tombstoneの「active」判定は「末尾eventがpurged」であり、marker の存在だけでは dead と判定しない (解決は08§3.1手順5のcanonical final event正本化を経て評価する)。

- **実装状態: [未実装]** `state.begin()` (purge.rs:296-347) は同一reasonの再purgeを `BeginOutcome::AlreadyComplete` として素通りし (purge.rs:333-335)、reason相違時は拒否する (purge.rs:325-328、"an existing tombstone has a different purge reason")。events[]自体が無い (U13) ため新規`purged` eventのappendという経路もない
## F. fsck / repair / prune (10 §7.5)

### U39 --verify-objects 検証対象の拡大 + embedding vector 検証 [P0]
- 出典: gap-10-03 G45
- spec §: 10-operations.md §7.5.1
- 種別: 挙動
- 統合要約: `kio repair --verify-objects` の検証対象を旧「raw/chunk/tree/commit」から新「raw/prepared/image/chunk/embedding/manifest/toollock/tree/commit」に拡大する。embeddingは新規にvector長・有限値・vector digestも検証対象になる。

- **実装状態: [部分]** verify_objects.rs は raw/chunk/tree/commit/prepared/image を検証 (297-652行、normalized instance の manifest.units 経由で prepared/image を辿る) が、embedding vector 検証・toollock 検証は grep 0件 ("embed|dimension|finite|tool.lock" いずれも verify_objects.rs に無し) — 対象拡大は道半ば。
### U40 manifest object の再hash検証と未finalize進行状態の区別 [P0]
- 出典: gap-10-03 G46
- spec §: 10-operations.md §7.5.1
- 種別: 挙動
- 統合要約: manifest object (objects/manifests/) を再hash検証対象とし、各tree entryのnormalize.manifest_hashが実在manifest objectを指し、かつ当該manifestの(raw_hash, tool_profile_hash, gen)がentry側と一致することを検査する (purge済みrawのentryは除外)。HEAD tree entryについては作業コピーmanifest.jsonのcanonical JCS hashとの一致も検査し、不一致は破損ではなく「未finalizeの進行状態」としてincomplete (exit 3) に分類する新規区別を導入する。

- **実装状態: [未実装]** `normalize.manifest_hash` フィールドが存在しない。NormalizeRef (kio-core/src/dag.rs:16-20) は tool_profile_hash + gen のみ。"objects/manifests/" という CAS 種別も cas.rs に0件。manifest 再hash検証の前提スキーマが無い。
### U41 tag canonical ref + names.jsonl の全行検証を fsck に追加 [P0]
- 出典: gap-10-03 G47
- spec §: 10-operations.md §7.5.1
- 種別: 挙動
- 統合要約: `refs/tags-v1/tag-*` とnames.jsonlの全行検証をfsckに新規追加する。各行のschema、digest64↔logical_name対応 (digest再計算)、torn tail処理、canonical ref↔最終有効行対応を検査し、対応行の無いcanonical refはcorruption、refの無いnames行はtag削除後の残存として正常とする。

- **実装状態: [部分]** refs/tags-v1/tag-<digest64> の canonical leaf 検証 + refs/tags との一致検査は既にある (verify_objects.rs:1368-1429)。ただし names.jsonl は repo 全体で grep 0件 — 現行は portable_tag_leaf() という純関数エンコード方式で、digest64↔logical_name の追記ログという新機構自体が無い。
### U42 normalized unit done object 欠落の復旧禁止と legacy 警告の exit 非影響化 [P1]
- 出典: gap-10-03 G48
- spec §: 10-operations.md §7.5.1
- 種別: 挙動
- 統合要約: normalized unitのdone宣言object欠落について、同gen再生成を禁止する (unit objectはimmutableであり非決定的な再生成は過去commitの内容差し替えになるため)。復元手段はbackup restoreまたは明示の新gen (`kio reindex --force`) のみとする。また「legacy警告 (path/reason) はexitに影響しない — 破損とは別に種別ごとの件数を表示する」というexit codeとlegacy警告カウントの分離規則を新規追加する。

- **実装状態: [未実装]** manifest_hash 不在 (U40) につき「done宣言object」概念が無い。verify_objects.rs/markdownize.rs の "legacy" はいずれも canonical/legacy 格納パスの話で、legacy警告のexit非影響化とは別概念。同gen再生成禁止ロジックも無し。
### U43 --prune-orphans 新設 (orphan prepared/image・staging root削除) [P0]
- 出典: gap-10-03 G52, gap-05 G46
- spec §: 10-operations.md §7.5.1, 05-runtime.md §3.5 (新設)
- 種別: 新規機能
- 統合要約: `kio repair --verify-objects --prune-orphans` を新規追加する。manifest参照の無いorphan prepared/image、descriptor無し/path不整合/terminal task残骸のstaging rootを列挙しlocked repairとして削除する (確認プロンプト必須)。拒否条件 (fail-closed): 当該scopeにstate 0/1の外部実行・pending/running task・非terminal taskに対応するstaging・未finalizeのmanifest進行状態・active なpurge journalのいずれかが存在すればexit 3で拒否する。特定不能の退出経路として、descriptor下の全normalized instanceが全unit terminalかつ同key のstate 0/1行が無い場合は削除可能とする条件も新規規定する。どのmanifestからも参照されないorphan prepared/image (公開前crashの残骸) はpurgeの解決経路に乗らずGCの「未参照中間object」として回収される対象だが、MVPではGCが無いためこの`--prune-orphans`が唯一の削除手段であるとpurge完了表示にも注記する。

- **実装状態: [未実装]** "prune-orphans"/"prune_orphans" は crates/ 全体で grep 0件。parse_repair_args (main.rs:919-977) は --rebuild-db / --verify-objects の2値のみ受理。
### U44 embeddings query_cache行のSQLite rebuild時例外 [P2]
- 出典: gap-10-03 G54
- spec §: 10-operations.md §7.5.1, §7.5.2, 03-data-model.md §4.1
- 種別: 挙動
- 統合要約: SQLite index (sqlite.db) は `--rebuild-db` で再構築可能なため検証対象外という原則に対し、例外として「embeddingsのtarget_type='query_cache'行のみ復元されず破棄される」ことを明記する。影響はquery cursorの拒否のみ (04-pipeline.md §4.3)。cost-ledger.sqliteの3表化 (A領域 U5) とは別の、sqlite.db側の再構築不可データという位置づけ。

- **実装状態: [適合済みの可能性]** snapshot_chunk_embeddings (kio-index/src/embedding_store.rs:308,324) は `WHERE target_type = 'chunk'` で明示的に絞っており、rebuild時にquery_cache行は構造的に既に破棄される — 新規則と実質一致。
### U45 SQLite schema 変更規約 (既定rebuild、cost-ledgerのみin-place migration例外) [P0]
- 出典: gap-10-03 G58
- spec §: 10-operations.md §7.5.3
- 種別: 新規機能
- 統合要約: SQLite schema変更のデフォルト経路を「migrationを書かず再構築する」(sqlite.dbは`kio repair --rebuild-db`、registryは各`.kio`のrescan) と明記する新規節を新設する。`cost-ledger.sqlite`はこのデフォルトの対象外で、常にin-place migration (既存行保全必須) に従う (詳細はA領域 U5 参照)。

- **実装状態: [未実装]** fts.rs:594-657 の migrate_legacy_chunk_config_column が sqlite.db に対し ALTER TABLE ベースの in-place migration を実行しており、「schema変更は既定rebuild、cost-ledgerのみ例外」という新方針と逆の実装が現存する。
### U46 registry live 重複の fail-closed 処理 + kio repair --registry-prune [P0]
- 出典: gap-10-03 G11, gap-07-06 G31, gap-rest G20, sol G61
- spec §: 10-operations.md §3, §12.1, 06-cli-spec.md コマンド一覧, 08-evidence-pointer-spec.md §3.1 手順1
- 種別: 新規機能 / エラー分類
- 統合要約: 同一scope_idの複数live path (clone併存) を新規にfail-closedで扱う: 横断検索は当該scope_idをskipしexcluded_scopesに`KIO-E-REGISTRY-DUP-001`で記録、pointer解決 (08§3.1手順1) は候補一覧errorとする (旧仕様の「last_seen_at最新を優先」する自動選択を廃止、purge状態の異なるcloneへ黙って解決すると判定を取り違えるため)。手順1a (scope_path直接一致) でも候補が2件以上なら同様に選択せず同じerrorとする。書き込み系コマンドとonline task起動 (相1) も同codeでfail-closedとする。真に到達不能なstale行のみ `kio repair --registry-prune` (確認プロンプト付き新規CLI、`kio repair` は`(--rebuild-db [--online|--offline] | --verify-objects [--prune-orphans] | --registry-prune)` のexactly-one必須構文に拡張) で退役可能とし、エラーnamespaceにREGISTRY domainを新設する。

- **実装状態: [部分]** resolve_scope_id_in_registry (main.rs:5995-6038) は last_seen_at 同値タイのみ ambiguous 扱い (KIO-E-EVIDENCE-SCOPE-AMBIGUOUS-001)、タイでなければ従来通り最新優先で自動選択 — fail-closed化は未達。`--registry-prune`・KIO-E-REGISTRY-DUP-001・REGISTRY error domain は grep 0件。
### U47 バックアップ最低保全集合の拡大 (truth区分全行) [P1]
- 出典: gap-10-03 G55
- spec §: 10-operations.md §7.5.2
- 種別: 挙動
- 統合要約: 旧spec の「最悪 objects/ と refs/ が保全されていれば復旧できる」から、新spec の「最低保全集合は objects/ と refs/ ではなく、§4.1 の truth区分の全行 (scope.json/config/tool-lock/tombstones+erase receipts/chunks.jsonl/access.jsonlを含む)」に変更する。旧spec 通りobjects/+refs/のみをバックアップ対象とすると、新spec 下では復旧不能なデータを喪失する。

- **実装状態: [判定不能]** Kio に backup サブコマンド自体が無い (purge.rs:1472 は「external backups and Time Machine」というユーザー向け注記のみ)。実装面のドキュメントのみの規範でgrep対象が無い。
### U144 rebuild-db の index_metadata 初期化と publication/introduction 再導出アルゴリズム [P1]
- 出典: gap-04 G61, G62
- spec §: 04-pipeline.md §5.7
- 種別: 挙動
- 統合要約: `kio repair --rebuild-db`の再構築完了時にindex_metadataへ新しいindex_generation ULIDを採番し、同じ完了Txでlast_lifecycle_epochを現在のlifecycle-epoch counter値に初期化する手順を新規追加する (DEFAULT 0のままだと全lifecycle recordが回転未了と誤検出され全走査と不要回転が走るため)。chunk_publications/chunk_config_generationsのintroduction再導出アルゴリズムを新規定義する: chunks.jsonlのpublication event行を正本として復元し (treeのchunk_set_hashは照合のみに使用)、event行を欠く旧storeは全commitを親先行topological orderで走査するフォールバックを使う (既採用introductionのいずれの子孫でもないcommitのみ追加、ancestor-minimal集合)。publication event行のbackfillは行わない。dangling event行 (creation行/chunk object欠如、またはintroduction commit object欠如) は無視するが、refから到達不能でもcommit objectが存在する行は無視しない。

- **実装状態: [未実装]** "index_metadata"/"index_generation"/"lifecycle_epoch" いずれも crates/ 全体で grep 0件。chunk_publications の introduction イベントモデルも存在せず、chunks は単一列 first_seen_commit のみ (kio-index/src/rows.rs:20)。
## G. evidence pointer / verify / retarget (08)

### U48 schema_version の wire 表現統一 (MAJOR整数) と未知MAJOR拒否の一律化 [P0]
- 出典: gap-rest G16, G37, sol G51
- spec §: 08-evidence-pointer-spec.md §2.1, §2.3, §8
- 種別: schema
- 統合要約: `schema_version` の説明に「wire上はURIの`sv`と同じくMAJORのみの整数」という制約を新規追加する (semverのMINOR/PATCHは載せない。optional フィールド追加はsv不変で、未知フィールド無視則が前方互換を担う)。readerが自身の対応MAJORより新しい`schema_version`を受け取った場合、URIの`sv`パラメータ経由でもinline/batch JSONの`schema_version` field経由でも同一に`KIO-E-CONFIG-SCHEMA`系error (exit 2) で拒否する統一規則を新設し、未知フィールド無視による前方互換は「既知MAJOR内のMINOR追加」にのみ適用されるとスコープを明確化する。

- **実装状態: [適合済みの可能性]** URI sv= 不一致 (kio-search/src/evidence.rs:257-261) と inline JSON schema_version 不一致 (evidence.rs:170-174) はいずれも SearchError::Evidence → KioError::schema() (main.rs:6992 / kio-core/src/error.rs:34-41) を経由し、既に統一的に KIO-E-CONFIG-SCHEMA-001 exit 2 になる。未知フィールドも許容 (deny_unknown_fields 無し)。
### U49 表示用フィールドのcanonical値優先とURI opaque/authority大文字小文字保存 [P0]
- 出典: gap-rest G17, G18, sol G51
- spec §: 08-evidence-pointer-spec.md §2.2, §2.3, §5
- 種別: 挙動 / schema
- 統合要約: 解決成功時、`path_at_commit`/`heading_path`等の表示用フィールドはtree/chunk object由来のcanonical値を優先表示し、pointer入力値と相違すれば入力値を無視する規則を新設する (偽の表示metadataを付けたpointerがaliveのまま人間向け引用に使われることを防ぐ)。shallow解決ではcanonical `path_at_commit`が得られないためpointer入力値で代替せず「path unavailable (commit_shallow)」等の欠落表示にする。retarget (§5) の旧heading/section/span照合にも同じ規則を適用し、旧pointerを解決したcanonical値のみを使う。Evidence Pointer URIに対して一般的なURI正規化 (authorityの小文字化) を適用してはならない規則も新設し、scope_id (ULID) は大文字表記が正でregistryのTEXTキー照合はcase-sensitiveで行う。

- **実装状態: [未実装]** PointerResolution (main.rs:5616-5621) や open/view の出力 (main.rs:3505-3546) はそもそも path_at_commit/heading_path を含まず、canonical値優先という規則を適用する表示面が無い。retarget コマンドも無い (U59参照)。
### U50 object URI (type=image限定) の pointer schema 定義 [P1]
- 出典: gap-rest G19
- spec §: 08-evidence-pointer-spec.md §2.3
- 種別: 挙動
- 統合要約: `kio://<scope_id>/object/<type>/<hash>` 形式のobject URIについて、MVPで発行・受理されるのは`type=image`のみと明記し、他typeは受理側でも拒否する (新type追加は06§1.1でopen semanticsを定義してから)。`kio import --as-new-scope`で複製したscope内に残る旧scope_idを含むobject URIは、自storeに同一hashのobjectがあればhashをidentityとして自storeで解決する規則を新設する (open command側の消費はC領域 U22参照)。

- **実装状態: [部分]** object URI 解決 (main.rs:6779-6852) は raw/image/chunk/prepared を受理・解決しており、MVPでtype=image限定という新制約より広い。`kio import --as-new-scope` は grep 0件で、複製scope内object URI解決規則の前提が無い。
### U51 shallow commit (手順2a) 適用ステップの厳密固定 [P1]
- 出典: gap-rest G21
- spec §: 08-evidence-pointer-spec.md §3.1 手順2a
- 種別: 挙動
- 統合要約: 旧仕様は「手順3-4を省略し手順5以降を直接行う」という緩い記述だったが、新仕様は適用可能な手順を「手順5→chunk_hash→chunk object→gen→手順7→手順8」に厳密固定し、tree/entryを要する手順3-4・6・6a・6bは対象外と明記する。`--strict` verifyはshallow解決をunverifiable (exit 3) として返す。

- **実装状態: [部分]** resolve_pointer_for_cli の shallow経路 (main.rs:5860-5903) は既にtree entry参照とgen bindingをスキップしており手順5-8相当に近いが、evidence verify --strict (verify_objects.rs:38-42) は status!="alive" のみを見ており、shallow解決は status="alive" のまま返るためunverifiable降格が無い。
### U52 手順4: 同一raw_hash複数entryの決定的選択とショートサーキット [P1]
- 出典: gap-rest G22, sol G52
- spec §: 08-evidence-pointer-spec.md §3.1 手順4, 10-operations.md §3
- 種別: 挙動
- 統合要約: 同一commit内に同一raw_hashが複数pathへ配置されている場合のtree entry選択規則を新設する。pointerのtool_profile_hashと一致するbindingのentryを選び、同一bindingのentryが複数残ればpathのUTF-8 byte順最小のentryを決定的に選ぶ。一致entryが無ければ手順5-7を実行せず`KIO-E-STORE-CORRUPT-001` (not_found扱い) へ短絡する。

- **実装状態: [未実装]** resolve_pointer_for_cli は `tree.entries.iter().find(|entry| entry.raw_hash == pointer.raw_hash)` (main.rs:5870-5873) で raw_hash一致の最初の1件を採用するのみ。tool_profile_hash一致による選択・path byte順tie-breakは無い。
### U53 canonical final event 正本化アルゴリズムと4分岐・status改称 (purged→tombstoned) [P0]
- 出典: gap-05 G42, gap-rest G23, G24, G28, G43, sol G53
- spec §: 08-evidence-pointer-spec.md §3.1 手順5, §3.2, 05-runtime.md §3.3, 09-mvp-scope.md §4
- 種別: 挙動 / エラー分類 / schema
- 統合要約: raw_hashの生死判定を根本的に書き換える。旧仕様は個別tombstoneの有無で判定していたが、新仕様はraw_hashに存在する全marker (tombstone/erase receipt) の最終eventを集約し、`lifecycle_epoch`が最大のeventをcanonical final eventとして正本化する (legacyのepoch欠落は0、同値はtombstone側を優先する決定的tie-break)。この正本化に参加できるのはevent検証 (kind別必須field・遷移文法・in_commit/purged_raws membership・atの妥当性) を通過したmarkerのみで、検証失敗のmarkerは`KIO-E-STORE-CORRUPT-001`で終端し正本化に参加しない。判定結果は4分岐する: (i) `purged` → tombstoneを返す (レスポンスのstatus値も`"purged"`から`"tombstoned"`に改称、purgeの事実は別途`purged_*`フィールドで表す)。(ii) `erased`かつraw不在 → not_found (`KIO-E-PURGE-NOT-FOUND-001`)。(iii) `retired` → tombstone扱いしないが手順6進行前にraw存在を必須検査 (resurrection対応)、不在ならnot_foundだが`KIO-E-STORE-CORRUPT-001` (corruption側)。(iv) markerが全く無いのにraw不在 → `KIO-E-STORE-CORRUPT-001`。検索結果からの除外はこのcanonical final event=purgedによるchunk行の物理削除が根拠であり、commit_type=purgedはその監査痕跡に過ぎないという整理も新設する (tombstone応答はrestore/verify/openにpointerを与えた場合の挙動として分離)。

- **実装状態: [未実装]** TombstoneRecord (kio-core/src/purge.rs:107-136) に lifecycle_epoch 無し、"retired" モードも無い (TombstoneMode::Default/Eraseのみ)。open/view側 tombstone_error は status="purged" のまま (main.rs:6651-6654) だが evidence verify側は既に status="tombstoned" (verify_objects.rs:193) — 改称が部分的にしか伝播していない不整合あり。
### U54 手順6a新設: v2/v3 tree の時点帰属検証 [P0]
- 出典: gap-rest G25, sol G54
- spec §: 08-evidence-pointer-spec.md §3.1 手順6a
- 種別: 新規機能
- 統合要約: 新しい検証ステップとして、tree entryの`normalize.manifest_hash`が指すmanifestで該当unit_keyが`status=done`であることの検証、およびv2/v3 treeではさらにchunkのpublicationとconfig associationのintroductionがpointerのcommitのancestor-or-equalであることの検証を追加する (config associationは対象treeのchunking_config_hashに限定)。association不在はcorruptionではなくnot_found (rebuild後に再評価可能)。sqlite.db自体が不在・再構築中はこの検証を実行できず、not_foundではなく`KIO-E-INDEX-REBUILDING-001`を返す。v1 tree (manifest_hash欠落) はこの検証を丸ごとスキップし、legacy解決として`--strict` verifyはunverifiable (reason=tree_v1、恒久、exit 4) に降格する。

- **実装状態: [未実装]** normalize.manifest_hash 不在 (U40) に依存する手順のため前提を欠く。unit_key の status=done 検査は存在しない。
### U55 手順6b新設: manifest欠落の説明範囲限定・降格・resurrection link解決 [P0]
- 出典: gap-rest G26, sol G54
- spec §: 08-evidence-pointer-spec.md §3.1 手順6b
- 種別: 新規機能
- 統合要約: manifest objectがpurgeで欠落している場合の扱いを新設する。説明範囲はfsckと同一に限定 (purged/erased eventの`in_commit`以前のcommitが参照するclosureのみ)。範囲外なら`KIO-E-STORE-CORRUPT-001`。範囲内なら手順2aと同様に直接解決へ降格し`manifest_missing: true`を付すが、手順4で取得済みのtree entry照合 (手順8相当) は実施する。retired eventに`resurrection_commit`リンクがあれば、そのリンク先commitのpublicationを基準に本文を解決しaliveを返してよい。`--strict` verifyはunverifiable (reason=manifest_missing、恒久、exit 4)。`commit_shallow`と`manifest_missing`は相互排他。

- **実装状態: [未実装]** 同じく manifest_hash 不在に依存。manifest_missing status も resurrection_commit フィールドも grep 0件。
### U56 手順8新設: defense-in-depth の整合再検証 [P0]
- 出典: gap-rest G27, sol G52
- spec §: 08-evidence-pointer-spec.md §3.1 手順8
- 種別: 新規機能
- 統合要約: 解決の最終段に新しい検証ステップを追加する。chunk objectのraw_hash/tool_profile_hashがpointer値と一致することに加え、手順4-6を経た場合はtree entryの`normalize.tool_profile_hash`がpointerのtool_profile_hashと再度一致し、かつchunk objectのgenがtree entryのgenと一致することを検証する。これは手順4の選択ロジックが破損/改変されたstore上で迂回された場合の防御であり、不一致は`KIO-E-STORE-CORRUPT-001`。shallow経路 (2a) はtree membershipを検証できないため`--strict` verifyはshallow解決をalive でなくunverifiable (exit 3) として返す。

- **実装状態: [部分]** resolve_pointer_for_cli は chunk.raw_hash/tool_profile_hash/gen とpointerの一致を単一の統合チェックとして実施済み (main.rs:5944-5957) だが、これは唯一のチェックであり手順4-6選択 (U52で不在確認済み) の後段に置かれた冗長防御としては構成されていない。
### U57 evidence verify status の6値union化 [P0]
- 出典: gap-05 G43, gap-rest G31, sol G50
- spec §: 05-runtime.md §3.3, 08-evidence-pointer-spec.md §4.3
- 種別: schema
- 統合要約: `kio evidence verify`の`status`unionを`alive|tombstoned|not_found`の3値から`alive|tombstoned|not_found|scope_unreachable|unverifiable|registry_duplicate`の6値に拡張する。`unverifiable`はさらに`details.reason`で`commit_shallow` (回復可能、exit 3) / `tree_v1`/`manifest_missing` (いずれも恒久、exit 4) に分岐する。`--strict`は旧仕様ではtombstoned/not_foundのみをerror扱いしexit 4一律だったが、新仕様は`scope_unreachable`もerror化しつつexit 3 (retryable) としてtombstoned/not_foundのexit 4 (permanent) と区別する。sqlite.db不在時はstatusではなくcommand-levelの`KIO-E-INDEX-REBUILDING-001` (exit 3) を`--strict`無しでも返す。

- **実装状態: [部分]** verify_pointer_for_cli は alive/tombstoned/not_found の3値のみ返す (verify_objects.rs:175,193,201)。scope_unreachable/unverifiable/registry_duplicate は crates/ 全体でgrep 0件。
### U58 purge journal 進行中の evidence verify 拒否 [P1]
- 出典: gap-rest G32
- spec §: 08-evidence-pointer-spec.md §4.3
- 種別: 新規機能
- 統合要約: active なpurge journal (marker耐久化後・削除完了前の窓) の間にverifyが呼ばれた場合、評価を行わず`KIO-E-PURGE`系retryable error (exit 3) を返す新規則を追加する (削除対象を「alive」と誤答することを防ぐ)。E領域のpurge journal 2点検査 (U36) のevidence verifyにおける具体的適用にあたる。

- **実装状態: [未実装]** enforce_purge_read_barrier/barrier_blocks (kio-core/src/purge.rs:417-422) は該当raw_hash単位のバリアであり、「active journal中は無条件でverify拒否」ではない。しかも該当時の応答は exit 4 permanent (KIO-E-PURGE-TOMBSTONED/NOT-FOUND-001) で、新規則が求めるexit 3 retryableのKIO-E-PURGE系ではない。
### U59 retarget の fail-closed 強化とレスポンス配置変更 [P1]
- 出典: gap-rest G33, G34, G35, G44 (retargeted_from配置), sol G55
- spec §: 08-evidence-pointer-spec.md §5, 09-mvp-scope.md §5.2
- 種別: エラー分類 / 挙動 / schema
- 統合要約: `heading_path_exact`による完全一致が複数chunkに成立する場合、旧仕様では暗黙に先勝ちで選ばれ得たが、新仕様は一意に定まらないとして`KIO-E-EVIDENCE-RETARGET-AMBIG-001`でfail-closedにする。span重なり率によるfuzzy対応付けは、新旧normalized text間でtext alignmentが成立した領域内でのみ用いる制約を新設し (異なるtool_profileのunit-local byte offsetは共通座標を持たないため直接比較しない)、alignment不成立時は対応なし (ambiguous, fail-closed) とする。retargetが実行可能であるための前提条件として「旧chunk/tree objectがCASに存在すること」を新規に明記し、不在の場合はnot_found/unverifiable側に降着する。旧文言「新pointer (retargeted_fromを保持) を返す」は`retargeted_from`が新pointerオブジェクト内部に含まれるように読めたが、新文言は`retargeted_from`がresponse直下 (pointer外) のトップレベルフィールドであると明記する。

- **実装状態: [未実装]** retarget コマンド実体が存在しない。「retarget required」を伝えるエラー信号 KIO-E-EVIDENCE-RETARGET-REQUIRED-001 (main.rs:5927、test: step3_p0_contract.rs:1860) のみで、実際にretargetを行う手段は無い。
### U60 match_method 拡張の互換性分類 (MINOR相当) [P2]
- 出典: gap-rest G36
- spec §: 08-evidence-pointer-spec.md §5, 09-mvp-scope.md §5.2
- 種別: schema
- 統合要約: 意味ベース対応付け (semantic_fingerprint) をPhase 4+で導入する際の互換性分類を明確化する。match_methodはretarget response限りのfieldでresolver入力ではないため、旧実装は未知フィールド無視則と同様に未知値を無視でき、pointer schema本体へのMAJOR相当のfield追加ではなくMINOR相当として扱ってよいと初めて明記する。

- **実装状態: [未実装]** match_method/semantic_fingerprint は grep 0件 (spec自体がPhase 4+スコープと明記)。
### U61 kio evidence verify --batch フラグ新設 [P1]
- 出典: gap-07-06 G38
- spec §: 06-cli-spec.md コマンド一覧
- 種別: 新規機能
- 統合要約: `kio evidence verify --batch <pointers.jsonl> [--strict]` を新設する (Phase 4+)。`<pointer>`と`--batch`は相互排他とする。

- **実装状態: [未実装]** evidence verify --batch は "outside the MVP" として明示的に拒否 (verify_objects.rs:67-71) — spec自身のPhase 4+スコープ規定と整合した意図的未実装。
### U62 path_at_commit の legacy tree 例外 [P1]
- 出典: gap-rest G15
- spec §: 08-evidence-pointer-spec.md §2 (導入部)
- 種別: schema
- 統合要約: `path_at_commit`は「パス区切りを含まない」という不変条件に例外を追加する。03§3のforward規則制定以前に作られた検証済みlegacy tree由来のentryに限り、区切り等を含む旧pathをそのまま保持してよい。ただし表示専用であり resolver入力には使わない。

- **実装状態: [未実装]** TreeEntry::validate() (kio-core/src/dag.rs:44-71) は無条件に is_logical_direct_child を要求しており、legacy tree例外の分岐が無い。なお表示面自体が無い (U49) ため適用対象も無い。
## H. 検索 / gate / mode / exit (05 §1-2 / 06 の search 面)

### U63 search auto-resolve順序の拡張とquery embedding consent gate [P0]
- 出典: gap-05 G1, G2, G3, G5, gap-07-06 G45, G47, G48
- spec §: 05-runtime.md §1.1, §1.2, 06-cli-spec.md §3
- 種別: 挙動 / 新規機能
- 統合要約: `auto`の解決順を「両方利用可能→hybrid / vectorのみNG→text / 両方不可→error」の3行から、`--offline`指定・embedding未承認・同一query in-flight・query embedding応答のcontract violationの4条件をtext fallbackとして追加した7行構成に拡張し、複数条件同時成立時は先に列挙された行を採用する (profile不一致がUNAUTHORIZEDに先行)。vector|hybridのpage 1が行うquery embedding (sync呼出) を新規送信として扱い、送信可否を「参加scopeの1つ以上にactiveなapprovals[]行があり、かつ実効allow_networkがtrue」と定義し、この可否は相1 claim Tx内でapprovals[]/booleanを再読して最終検証する。`embedding_not_authorized`と`offline`によるtext fallbackは`fail_behavior`設定の対象外 (常にtext fallback/errorに固定) である一方、`embedding_in_flight`と`embedding_contract_violation`は技術的過渡失敗として`fail_behavior`の対象とする。`kio search`に`[--online|--offline]`フラグ、`[search].default_mode`設定 (既定auto=hybrid→text fallback) を新設する。

- **実装状態: [部分]** [search].default_mode/fail_behavior 設定と embedding_opt_in gate は既存 (main.rs:1300, 1406-1417) だが、`kio search [--online|--offline]` は grep 0件、embedding_in_flight/embedding_contract_violationのfallback理由も0件。opt-in判定は一度きりのprecheckで、compute_query_embedding (main.rs:8731-8752) 内で送信直前の再検証は無い (claim Tx内再読という規則は未達)。
### U64 短語LIKE fallbackとMATCH式の決定的生成 [P1]
- 出典: gap-05 G6, G7
- spec §: 05-runtime.md §1.3
- 種別: 新規機能 / 挙動 / エラー分類
- 統合要約: query全tokenが3文字未満でtrigram tokenizerのMATCHが成立しない場合、`chunks.text`へのbounded LIKEスキャン (上限=candidate_depth、instrベース) にfallbackする新規則を追加する。3文字以上のtokenが混在する場合はMATCH式には3文字以上のtokenのみを渡し、3文字未満のtokenは同一bounded query内のinstr条件としてLIMIT前にAND適用し、この短語instr条件はtext/vector両バックエンド共通のeligibility述語として候補確定前に適用する。user queryをFTS5構文として解釈せず、token列を各々二重引用符で囲んだphrase/termの並びとして機械生成する規則を新設し (FTS5演算子の直接指定は非対応)、tokenizationはNFC正規化後Unicode空白分割で決定的に固定、token 0個のqueryはKIO-E-CONFIG-USAGE-001 (exit 2) とする。

- **実装状態: [未実装]** build_fts_tiers (main.rs:3357-3420) は keyword_groups/CJK trigram の tiered OR/AND を順次実行する現行独自方式で、新spec の「token個別quote・機械的単一MATCH生成」とは別アーキテクチャ。instr()によるLIKE fallbackは grep 0件。
### U65 candidate_depth の実装規則 (内側サブクエリ限定) [P1]
- 出典: gap-05 G8
- spec §: 05-runtime.md §1.3
- 種別: 挙動
- 統合要約: candidate_depthの上限はrank計算の入力になる内側段 (サブクエリ) で効かせる実装規則を新設する。外側LIMITで適用すると全マッチ行がrank計算に入り実行コストが数十倍に膨張する (旧research実測: VM step 1,074→70,374が出典)。vector側もvec0の`k=`構文等、述語適用前に内部top-kを確定させる形は用いない。

- **実装状態: [未実装]** execute_fts_tier は `LIMIT 200` をSQL内に直書き (main.rs:2670) しており設定candidate_depthを無視。vector_scope_search はvec0のk=を`total.min(4096)`で使う (main.rs:2483-2484、まさに禁止されているvec0内部top-k方式)。実際のcandidate_depthはrrf.rs:46,57のマージ段でのみ適用される。
### U66 MMR選択則の初手tie-breakと適用除外条件の拡大 [P1]
- 出典: gap-05 G9, G10
- spec §: 05-runtime.md §1.4
- 種別: 挙動
- 統合要約: MMR選択則でselected=∅の初手はsimilarity項を0として扱う (=relevance最高の候補を既定tie-break順で選ぶ) 規則を新設し、実装間で初手が揺れないようにする。旧spec は「embeddingが無い場合(text-only)のみMMR非適用」だったが、新spec は「hybridの候補プールにembedding未付与、またはprofile非互換でcosine計算不能なchunkが1件でも混在する場合」もMMR非適用 (dedupのみ適用しRRF順で返す) に適用除外条件を拡大する。

- **実装状態: [適合済みの可能性]** mmr.rs は候補に1件でもembedding無しがあれば全体でMMR非適用 (mmr.rs:64-69、旧来のtext-onlyモード限定より広い)。初手のtie-breakも `selected.iter().fold(0.0, f64::max)` が空集合で0.0を返す構造上、既にsimilarity=0相当になっている (mmr.rs:110-118)。
### U67 cursor機構の拡張 (index_generation・chunking_config_hash定義変更・query vector再利用) [P0]
- 出典: gap-05 G11, G12, G13
- spec §: 05-runtime.md §1.5, §1.6, 04-pipeline.md §4.3
- 種別: schema / 新規機能
- 統合要約: scopeごとのsub-cursor構造に`index_generation`フィールドを追加する。rebuild・purge・embedding enrichment finalize・index/batch finalizeによるchunk_fts内容変化・tombstone lifecycle更新・GCのshallow化実行のいずれでも新規採番するULID (index_metadata表に保持) とし、回転はそれを引き起こしたSQLite書込と同一Txで行う。cursorのchunking_config_hashを「current value」から「page 1で検索対象にしたtreeのconfig (デフォルト=当該scopeのHEAD tree値、時点指定=対象tree値)」に定義変更し、page 2ではcurrentではなく対象時点の値との比較でquery hash mismatchを判定する。vector/hybridのreplayはpage 1のquery vectorを再利用し再embeddingしない新規則を追加し、正規化済みquery vectorは各scopeのembeddings表 (target_type='query_cache') に保持、そのdigest (query_vector_digest) をtokenの独立fieldとして保持しquery_hash構成要素にも含める。読み出した行はvector BLOBのsha256をtarget_idと再照合し、不一致はcorruptionとして削除しCURSOR-001とする。

- **実装状態: [部分]** ScopeCursor (kio-search/src/cursor.rs:29-38) は max_association_rowid・chunking_config_hash を既に保持するが index_generation フィールドが無い。chunking_config_hash は常に「現在値」から読まれ (main.rs:2281-2296、read_chunking_config(&repo))、「page1で検索したtreeの値」への定義変更は未達。query vector再利用も未実装 (QueryCache はembedding_store.rs:585で定義のみで未使用)。
### U68 --offset の vector|hybrid 単一実行内限定と終端判定の変更 [P1]
- 出典: gap-05 G14
- spec §: 05-runtime.md §1.5
- 種別: 挙動
- 統合要約: `--offset`はvector|hybridの場合「当該実行が取得したquery vectorに対する確定順序」の単一実行内sliceに限定する (CLI呼び出し跨ぎの継続はcursorが正)。終端判定も「候補プール末尾」から「alias展開後のfinal result streamの末尾」に変更する (`--all-history`/`--since`で候補プール末尾を終端にすると最後のalias groupを取り残すため)。

- **実装状態: [適合済みの可能性]** total_skip/slice_start/slice_end は既にcross-scope merge後のalias展開済みstream `expanded` に対して計算されており (main.rs:1840-1851)、next_cursor発行判定も `slice_end < expanded.len()` (main.rs:1867) — 新方式の「global final stream」終端判定と一致。--offsetはcursor不在時のみ適用され単一実行内に自然に閉じている。
### U69 --at --vector明示時のerror化と共通フィルタの対象tree化 [P1]
- 出典: gap-05 G15, G16, gap-04 G37
- spec §: 05-runtime.md §1.6, 04-pipeline.md §4.6
- 種別: エラー分類 / 挙動
- 統合要約: `--at --vector`で非互換の場合、旧spec は「fail_behavior=fallbackでtextに落ちる」だったが、新spec は「--vector明示時はfail_behaviorに依らずerror (§1.2と同じ)。textへのfallbackはauto/--hybridのみ」に変更する。共通フィルタを「現行chunking_config_hash」から「対象treeのchunking_config_hash (デフォルト=HEAD、--atは対象tree、--all-history/--include-deletedは各binding treeの値)」に変更し、config未記録のv1 treeは対象commitのancestor-or-equalなintroductionを持つassociationに限定した上でchunking_config_hashのbyte順最小を決定的に代用する規則を新設する。

- **実装状態: [部分]** `--vector` 明示時は fail_behavior に関わらず既に無条件error (main.rs:1155-1170、Auto/Hybrid分岐と構造的に分離済み) — この部分は一致。ただし共通フィルタのchunking_config_hashはU67と同じく常に「現在値」で対象tree値ではなく、v1 tree用byte順最小代用ロジックもgrep 0件。
### U70 HEAD不在scopeの検索時取り扱い [P0]
- 出典: gap-05 G17, gap-rest G13
- spec §: 05-runtime.md §1.6, 02-philosophy.md §11
- 種別: 新規機能 / エラー分類
- 統合要約: HEAD不在 (初回auto snapshot前・snapshot finalize未完) のscopeを「index未完了」として扱う新規則を追加する。検索は当該scopeをKIO-E-INDEX-REBUILDING-001でexcluded_scopesに計上し (単独scopeならexit 3)、cursorは発行しない。SQLiteに反映済みでも未公開の行は返さない。この扱いはbare (--atなし) のHEAD依存解決経路に限り、明示commit・Evidence Pointer指定はHEAD非依存に解決する。MVPの**default**検索対象はfolder-local`.kio`のactiveなartifactのみとし、`--at`/`--all-history`/`--include-deleted`の履歴系flagは対応するsnapshot bindingを検索対象にするというdefault/overrideの分離も明記する。

- **実装状態: [未実装]** HEAD不在scopeは reason="not_indexed" で除外される (main.rs:2159) が、これはコメント上も明示的に汎用all-failed経路 (KIO-E-SEARCH-SCOPE-ALL-FAILED-001, exit 4、main.rs:1658-1660) に分類されており、新規則が求めるKIO-E-INDEX-REBUILDING-001/exit 3ではない。
### U71 検索の時点条件の正式化 (introduction ancestor-or-equal・correlated EXISTS) [P0]
- 出典: gap-05 G18, G21, sol G47
- spec §: 05-runtime.md §1.6
- 種別: 挙動
- 統合要約: デフォルト/`--at`の検索対象を「chunk_publicationsのいずれかのintroduction_commitが対象commitのancestor-or-equalであるchunkに限る」と正式化する (単一のfirst_seen_commitでは複数導入=merge側枝・独立importを表現できないため)。config associationにも同条件を適用し、`--include-deleted`/`--all-history`にも同判定を適用する。この時点条件はcorrelated EXISTS (ancestry判定とassociation_rowid <= cursor.max_association_rowidを副問い合わせ内に含む) で評価する実装規範とし、素のJOINで結合すると同一(chunk_id,config)の複数introduction行で同一chunkが重複hitするため、候補集合はranking前に(scope_id, chunk_id)で一意化する。

- **実装状態: [未実装]** 複数introduction (chunk_publications) モデルが無い (U67/U144と同根)。chunksテーブルは単一列first_seen_commitのみ (kio-index/src/rows.rs:20) のため、「同一chunkが複数introduction行で重複ヒットする」事象自体が現行スキーマでは起こり得ず、(scope_id,chunk_id)一意化ロジックも無い。
### U72 shallow化commitのwalk skip可視化 (shallow_skipped) [P1]
- 出典: gap-05 G19
- spec §: 05-runtime.md §1.6
- 種別: 新規機能
- 統合要約: `--all-history`等のhistory walk中にshallow化済みcommit (tree破棄済み) に遭遇した場合、黙って欠落させずskipした上でレスポンスに`shallow_skipped`件数を可視化しpartial (exit 3) として報告する新規則を追加する。

- **実装状態: [未実装]** "shallow_skipped" は grep 0件。ScopeSearchError::Shallow (main.rs:2028,2149,2193,2197,2210) は現状、遭遇したcommitをskipして続行するのではなくscope全体を除外/失敗させる。
### U73 --scope 単独指定の完全一致化と canonical root_path 算出規則 [P0]
- 出典: gap-05 G23, gap-07-06 G46
- spec §: 05-runtime.md §1.8, 06-cli-spec.md §3
- 種別: 挙動 (破壊的変更)
- 統合要約: `--scope <path>`単独指定を旧spec の「root_pathの前方一致」から「canonical root_pathの完全一致 (当該scopeのみ)」に変更する。`--descendants`併用時はself+「root_path+'/'を前置に持つscope」をpath-component境界で判定する (単純な文字列前方一致は`/work/a`が`/work/ab`に一致するため不使用)。canonical root_pathは絶対化→lexical解決→末尾separator除去→symlink解決(realpath)の順で正規化しbyte単位比較する。

- **実装状態: [適合済みの可能性]** Rust std の Path::starts_with は元々path-component単位の比較のため、registry_targets_under (main.rs:5084-5090) は `/work/a` vs `/work/ab` を混同しない。root.canonicalize() (main.rs:5016) も絶対化+解決+symlink解決を一括で行っており、新方式の意図とほぼ一致する挙動に既になっている。
### U74 multi-scope 実効値の解決方針 (device層user config採用) [P1]
- 出典: gap-05 G24
- spec §: 05-runtime.md §1.8
- 種別: 挙動
- 統合要約: multi-scope検索の`[search]`実効値 (default_mode/rrf/diversify/candidate_depth/fail_behavior) はuser config (device層) を用いる新規則を追加する (folder値は`--scope`単一指定時のみ適用、scope間で異なるfolder値の統合は未定義)。ただしfail_behaviorは挙動方針でありbind/query_hash preimageの対象外とする。

- **実装状態: [未実装]** effective_search_tuning/effective_search_config (main.rs:4857-4986, 4950-4986) は常に `scope設定.or(user設定)` の順で folder値優先 — single --scope時のみfolder値適用という新方針とは無関係にmulti-scopeでも folder値が使われ得る。
### U75 vector横断条件の変更と全scope失敗時のexit分割統合規則 [P0]
- 出典: gap-05 G22, G25
- spec §: 05-runtime.md §1.6, §1.8
- 種別: エラー分類 / 挙動
- 統合要約: embedding profile不一致時、旧spec は横断部分をtext統合するのみだったが新spec は「--vector明示時はfallbackせず、profile不一致scopeをKIO-E-SEARCH-VEC-INCOMPAT-001のexcluded_scopesとして除外、全scope除外ならerror」に変更する。kio_format_versionが新しいscopeも同様除外 (KIO-E-STORE-VERSION-001、当該scopeへの書込は一切行わない)。全scopeがSTORE-VERSION除外ならexit 8。全scope除外理由が同一codeなら当該codeの単独時exitを返す一般規則を新設し (VERSION→8、REBUILDING→3、INCOMPAT→8、journal→3、DUP→3)、理由混在時はretryable理由を含めばexit 3・全てpermanentならexit 4に分割する。この昇格・分割規則は`--all-history`/`--since`のscope数上限超過 (KIO-E-COMMIT-HISTORY-LIMIT-001) 等multi-scope history-limit失敗にも同様に適用する。embedding承認gate自体は送信gateでありper-scope除外条件ではない。

- **実装状態: [部分]** resolve_vector_availability (main.rs:1075-1115) は全exec_scopesに対し単一のVectorAvailabilityを集約算出しており、1scopeでも非互換ならmulti-scope全体がtext/errorに倒れる (per-scope除外ではない)。KIO-E-STORE-VERSION-001は grep 0件。一方「全scope同一reason除外→特定exit」という骨格 (main.rs:1642-1678、index_rebuilding→exit3、index_missing/corrupt→exit1) は既存し拡張の土台にはなる。
### U76 ページング継続処理を global final stream skip 方式へ変更 [P0]
- 出典: gap-05 G28
- spec §: 05-runtime.md §1.8
- 種別: 挙動
- 統合要約: 2ページ目以降のマージ処理を、旧spec の「各scopeをsnapshot_commitに固定して再クエリしconsumed件をskipしてマージ継続」から「cross-scope merge→global MMR→alias展開まで再計算した最終stream上でscopeごとのconsumed件をskip」に変更する (per-scope事前skipはglobal選択を変えるため不使用)。

- **実装状態: [適合済みの可能性]** U68と同根 — 現行実装は既にper-scope事前skipではなくcross-scope merge/MMR/alias展開後の最終streamに対してconsumedをskipしている。
### U77 kio search --at の multi-scope 制約新設 (--scope 単一指定必須) [P0]
- 出典: gap-07-06 G49
- spec §: 06-cli-spec.md §3
- 種別: 挙動
- 統合要約: `kio search --at <commit>` に `--scope` 単一指定必須の制約を新設する (独立DAGのmulti-scopeには単一commitが適用不能)。旧仕様は`--at <commit>`単独で許容されていた。

- **実装状態: [未実装]** `--at` と `--scope` 単一指定を紐付けるバリデーションが無い。multi-scope + `--at` はscope毎に独立してcommit解決を試みるだけでusageエラーにならない。
### U145 chunking config 変更時の再chunk/再embedding対象を HEAD参照instanceに限定 [P1]
- 出典: gap-04 G38
- spec §: 04-pipeline.md §4.6
- 種別: 挙動
- 統合要約: chunking config変更検出時の再chunk/再embeddingタスク対象を、旧spec「全normalized instance (履歴分含む)」から新spec「HEAD (現行tree) が参照するnormalized instanceのみ」へ縮小する。履歴instanceは時点指定検索で旧configのまま参照されるため (H領域 U69/U71)、新configでの履歴再chunkはどのtreeからも到達不能なchunkと embedding課金を生むだけになる。

- **実装状態: [未実装]** retained_history_instances (kio-cli/src/historical_reindex.rs:97-101) は `HistoryReader::new(kio_dir).all_parents(head)` で全祖先履歴を辿っており、HEAD tree参照分のみへの限定は行われていない。
## I. adapter 契約 (07)

### U78 AdapterRun/AdapterProfile 応答schemaの拡張 (error分類・usage・pricing) [P0]
- 出典: gap-07-06 G1, G10, G11, G22, sol G40, gap-10-03 G1
- spec §: 07-adapter-spec.md §2, §4, §7, 10-operations.md (コスト概算節), §12.3
- 種別: schema
- 統合要約: Adapter→coreのartifact descriptorのフィールドを単一の`error_kind`から機械判定用`error_code`とリトライ分類用`error_category`の2フィールドに分離する。AdapterRunに`error_category`(transient|permanent|rate_limitの新規分類、04§5.3のretry分類の入力)・`retry_after_ms`(optional)・`usage`(one-of usd|billable_units、request単位の課金報告) を追加し、billableな terminal応答ではusageを必須とする。billableを宣言するAdapterには`billable_kinds`(billable_units.kindの閉集合宣言)と`reject_billing`("billable"|"nonbillable"の閉enum)を必須フィールドとして追加し、宣言集合外のkind報告はestimated縮退+warningとする。コスト概算の単価参照先を旧「tool-lock.jsonのonline Adapter単価」から新「tools.tomlの`[pricing]`単価表」に変更し、billable宣言Adapterは AdapterProfileのbillable_kindsがpricingに被覆されることを送信前に検査する (欠落はconfig error)。`max_input_bytes`は「AdapterRun 1回の入力 (prepared inputのcanonical bytes合計)」に適用し、task全体の総量上限ではないと確定する (超過は送信前に当該taskをterminal failed・invalid_input・非再試行とし送信しない)。

- **実装状態: [未実装]** AdapterRunは`error_kind: Option<String>`のみ (crates/kio-adapter/src/types.rs:49-55)。error_category/retry_after_ms/usage/billable_kinds/reject_billing/pricingテーブル、全て0件。
### U79 online opt-in の AND ゲート成立条件と承認記録schema確定 [P0]
- 出典: gap-07-06 G3, G6, G7, sol G41, gap-10-03 G4
- spec §: 07-adapter-spec.md §3, 10-operations.md §12.3
- 種別: schema / 挙動
- 統合要約: opt-in成立条件を「(a)初回スキャン承認 または (b)config.tomlのallow_network=true」のORから、「approvals[]行のmaterializeと同一操作でのallow_network=true設定の両方 (AND)」へ変更する。config boolean単独の手編集では送信gateを満たさなくなり、例外的に`approvals_initialized` markerが無い初回に限り最初の1 toolのみ自動materializeされる。送信gateの判定条件を「allow_networkの実効設定がtrue」かつ「行のscope_idが一致し、現在のexecution_mode/tool_profile_hashに一致するstatus=active行が存在する」の両立と確定し、scope_id不一致の行 (fork複製由来) はgateに使わない。承認記録の保存先を`.kio/scope.json`の`approvals[]`配列に確定し、必須フィールドをscope_id/tool_id/execution_mode/tool_profile_hash/approved_at/approval_method/status(active|revoked)に確定する (status=revokedの行はrevoked_atも必須、statusを持たないlegacy行はactiveとして読む後方互換規則も新設)。scope.schema.jsonにも`approvals[]`各要素の必須field・`approval_pending`(単一object)の必須field・`approvals_initialized`(消費済みmarker boolean)を新規定義し、status欠落のlegacy approvals[]行やapproved_at/approval_method欠落のlegacy pendingはschema errorにせず次回locked mutationで自動補完・除去する。

- **実装状態: [未実装]** scope.schema.jsonに"approvals"プロパティ自体が無い (additionalProperties:false、scope_id/kio_format_version/scope_pathのみ)。allow_networkはconfig.tomlの裸boolのみ (main.rs:12687)。approvals_initialized/approval_pending 0件。
### U80 承認失効条件の拡張と単一Adapter revoke機構・crash-safe publish順序 [P0]
- 出典: gap-07-06 G4, G5, G29, gap-10-03 G4 (後方互換自己修復部分), sol G42
- spec §: 07-adapter-spec.md §3, 06-cli-spec.md コマンド一覧, 10-operations.md §12.3
- 種別: 新規機能 / 挙動
- 統合要約: 承認の失効条件を「tool_idまたはexecution_modeが変わった場合」から「tool_id・execution_mode・tool_profile_hashのいずれかが変わった場合」に拡張する (bbox_annotation等profileに畳み込まれる設定変更も失効対象)。scope全体のkill switch (allow_network=false) のみだった revoke に、単一Adapter単位の`kio adapter revoke <tool_id> | --all`を新設する: approvals[]行のstatus=revoked更新、同一(scope_id, tool_id)のapproval_pending除去 (execution_mode/tool_profile_hash不問)、approvals_initialized marker管理、対象なし時の冪等成功、publish直前のCAS再検証と不一致時の新規エラー`KIO-E-ADAPTER-APPROVAL-CONFLICT-001` (exit 5) を追加する。承認操作 (対話/`--approve`の行publish)・approval self-heal・`kio adapter revoke`はいずれも`.kio/.lock`下のlocked mutationとして直列化し、承認publish自体は4組+監査値の`approval_pending`→config→行+`approvals_initialized`の順でpublishし、完全一致だけself-healする。

- **実装状態: [未実装]** Commands enumに"adapter revoke"が無い。KIO-E-ADAPTER-APPROVAL-CONFLICT-001 0件。
### U81 --online/--offline の適用範囲拡大と優先順位確定 [P1]
- 出典: gap-07-06 G8, G9, G27, G28 (該当部分), sol G43 (I部分)
- spec §: 07-adapter-spec.md §3, 06-cli-spec.md コマンド一覧
- 種別: 挙動
- 統合要約: `--online`/`--offline`一時上書きの適用対象コマンドを列挙し、`kio search` (vector|hybridのpage1 query embedding) を新たに含める。既存in-flight requestの照会・出力取得・upload掃除は新規送信に当たらずopt-in不要と明記し、`--offline`は未送信タスクをpendingのまま送信しない逆向き上書きとして新設する。CLI優先順位 (CLI>scope config>user config) について、`--online`が上書きできるのは「opt-in未成立 (allow_network未設定) の既定閉鎖」のみに限定され、明示revoke (allow_network=falseの明示設定) は`--online`より優先するkill switchとして確定する。`kio batch resume`/`kio batch retry`にも`--online`/`--offline`を新設する (`kio batch abandon`は含まない)。

- **実装状態: [部分]** --online/--offlineは`kio index`のみ配線済み (main.rs:244-246 IndexArgs)。searchのParsedSearch/run_search_innerに0件、BatchCommand::Retryは無引数unit variant (main.rs:264-274)。
### U82 --reset-violations 機能新設 (batch retry) [P1]
- 出典: gap-07-06 G28 (該当部分)
- spec §: 06-cli-spec.md コマンド一覧
- 種別: 新規機能
- 統合要約: `kio batch retry`に`--reset-violations <selector>`を新設する。検証済みAdapter更新後にcontract_violation_countを0へ戻す機能で、selectorはintent_tokenまたは4組タスクキー、確認プロンプト必須、監査はcost-ledgerのoutcome列に残る。

- **実装状態: [未実装]** BatchCommand::Retryは無引数 (main.rs:267)。--reset-violations/contract_violation_count 0件。
### U83 bbox_annotation設定確定とadapter_kind enum変更 (prepare追加) [P0]
- 出典: gap-07-06 G14, gap-10-03 G66, G67 (bbox部分), sol G16 (該当部分)
- spec §: 07-adapter-spec.md §5.2, 03-data-model.md §5.1, 10-operations.md §12.3
- 種別: schema / 挙動
- 統合要約: bbox_annotationの制御方法を「.kio/config.tomlで無効化可」という曖昧な記述から`[markdownize] bbox_annotation = true` (既定) という正式なfolder-config schema keyに確定する。値が出力に影響するためtool_profile_hashに畳み込み、切替が世代判定に乗ることを明記する。capability hash計算対象の`adapter_kind`列挙値を「"markdownize"|"embedding"|"ocr"|...」から「"prepare"|"markdownize"|"embedding"|...」に変更し (OCRはadapter_kindでなくcapability区分へ移動)、新規hash入力fieldとして`render_params` (prepare専用: renderer_name/renderer_version/dpi/color_space/output_format) を追加する。

- **実装状態: [部分]** AdapterKind::Prepareは既存 (kio-adapter/src/types.rs:11)。`[markdownize] bbox_annotation`も既存・配線済み (config.schema.json:121, main.rs:5475-5514)。ただしrender_params (renderer_name/version/dpi等) hash入力fieldは0件。
### U84 tool_lock_hash の計算対象確定 [P0]
- 出典: gap-07-06 G20, sol G16 (該当部分)
- spec §: 07-adapter-spec.md §6, 03-data-model.md §5.2
- 種別: schema
- 統合要約: `tool_lock_hash`の計算対象を「tool-lock.json全体をJCS畳み込み」から「03-data-model.md §5.2のcanonical入力 (spec_version + 各roleのtool_id/profile_hash等) をJCS畳み込み」に確定し、`kind`/`capabilities`/`mode`はidentityに含めない表示用fieldと明記する。`profile_hash`のpreimage (model pin・Adapter定義本体) はデバイスローカルtools.toml側にあり、hashからの逆算・内容復元は保証しないことも新規明記する。

- **実装状態: [適合済みの可能性]** tool_lock_hashは既に選択的canonical値 (各roleのtool_id+profile_hashのみ、canonical_simple_entry, kio-adapter/src/tool_lock.rs:70-104) から算出— 全体JCS畳み込みではなく新仕様と一致。
### U85 Markdownize 入出力契約の変更と受入検査の拡張 (failed_units・unit_ref衝突) [P0]
- 出典: gap-04 G12, G13, G14, G16, gap-07-06 G12, G13, sol G28
- spec §: 04-pipeline.md §3, §3.2, 07-adapter-spec.md §5.2
- 種別: schema / 挙動
- 統合要約: incremental時のhints構造体のフィールド名を`added`/`removed`から`added_unit_keys`/`removed_unit_keys`に変更する。Adapter出力から`evidence_pointers`フィールドを削除し、部分失敗を表す`failed_units [{unit_key, error_kind}]`を新設する (Evidence Pointerの発行主体はAdapterではなくKio core、chunkingとsnapshotの後)。旧spec は「persistする前に検証する」とだけ規定していたが、新spec は「manifest/objectsへ確定persist (publish) する前に検証する」に精緻化し、受け入れ検査前のstagingへの耐久persistは禁止対象ではないと明記する。V1 (被覆・排他) がfailed_unitsを含む4集合の和=N・互いに素へ拡張され、同一配列内のunit_key重複も違反と規定する (各配列の要素数=distinct unit_key数を検査)。failed_units⊆hints.changed∪added、unchanged_unit_keysは§2.2の候補集合と完全一致という制約も新設。V5 (形式検査) にNormalized Markdown v1規約への機械検証可能な適合検査が追加され、違反unitを含む応答はrejectする。異なるunit_keyが同一unit_ref (`base16(sha256(unit_key))[0:16]`) へ写像される「衝突」を検査する規則を新設し、対象はpersist前に確定する合成後の最終unit集合、衝突があれば当該応答をwhole-response rejectする。

- **実装状態: [部分]** added_unit_keys/removed_unit_keys は既にリネーム済み (kio-pipeline/src/prepare.rs:71-72)。failed_units 0件 (未追加)。evidence_pointersフィールドはAdapterResponseに残存 (kio-adapter/src/types.rs:200、削除予定と矛盾)。
### U86 Normalized Markdown v1 形式の新設と Kio 側検証 [P0]
- 出典: gap-04 G15, gap-07-06 G2, G15, sol G26
- spec §: 04-pipeline.md §3.2, 07-adapter-spec.md §2.1, §5.2.1
- 種別: schema
- 統合要約: 全Markdownize Adapter出力が従うべき「Normalized Markdown v1」形式を新設する: UTF-8(BOM禁止)・NFC正規化・LF改行のみ・trailing space禁止・ATX見出しのみ(Setext禁止)・GFM table・画像参照形式固定・生HTML/autolink禁止 (escape規約)・code fence内でもエンコーディング/改行規約適用、をv1として凍結し、Kio側受け入れ検査の構造検証対象とする。同梱deterministic Adapterの出力仕様も「passthrough + fence正規化」から「Normalized Markdown v1への決定的正規化」に変更し、Setext見出し→ATX変換・生HTML blockのfenced text化・改行/空白/fence正規化を必須化する。

- **実装状態: [未実装]** "Normalized Markdown"/NFC/BOM等の検証 0件。validate_unit_shapes (markdownize.rs:1397-1417) はmarkdown非空とunit_key/type一致のみ検査、書式検証なし。
### U87 fallback_to_full 制御応答と contract_violation retry の分離 [P1]
- 出典: gap-04 G17, G18, gap-07-06 G23, G24, gap-10-03 G74, sol G29
- spec §: 04-pipeline.md §3.2, §5.3, 07-adapter-spec.md §8.1, 10-operations.md §12.5
- 種別: 新規機能 / 挙動 / エラー分類
- 統合要約: `fallback_to_full=true`の応答をV1〜V6に先立つ「制御応答」として評価する規則を新設する: unit配列・unchanged/removedは空必須、Kioは成功/失敗どちらの終端にもせず同一taskをmode=fullで再発行 (§3.1条件は再評価しない)。終端の単位はrequestであり、正常な制御応答は当該requestの終端 (taskは非終端) として`outcome='fallback_to_full'`で記帳・state=3とし、続けてmode=fullの新requestを相1として開始する。full応答でこのflagが立った場合はcontract violationとする。contract_violationの扱いを「failed permanent, max_attempts=0 (full fallbackを1回自動投入)」から「retryable, max_attempts=1 (同一modeで1回のみ再試行、再違反はfailed permanent)」へ変更し、full への自動フォールバックは廃止 (fallbackはincremental capability非互換の場合のみ)。spec_version不一致時のエラーコードを`KIO-E-ADAPTER-SPECVER-001`に確定し (max_attempts 0のinvalid_input分類)、full fallbackが有効なのはincremental capabilityのみが非互換な場合に限り、spec_version自体が非互換な場合は当該online Adapterのtaskをfailed permanentとする (full再試行しても同じ拒否を再生するため)。

- **実装状態: [未実装]** fallback_to_full=trueは常に即contract_violation (markdownize.rs:341-342、mode不問、制御応答パス無し)。ContractViolationのretry_policyは`retryable:false, max_attempts:Some(0)`のまま (kio-pipeline/src/task.rs:890-897、旧仕様のまま)。KIO-E-ADAPTER-SPECVER-001 0件。
### U88 Embedding 応答の受入検査新設 [P1]
- 出典: gap-07-06 G16
- spec §: 07-adapter-spec.md §5.3
- 種別: 新規機能 / 挙動
- 統合要約: Embedding応答の受入検査を新設する: `vectors[].id`は入力id集合との全単射、dimensionsのprofile一致、有限値かつ非ゼロ、float32変換+L2正規化はcore側実施、metadata (embedding_profile_hash/modality/distance) の一致を検査し、違反はall-or-nothingでrejectする (failed_units相当の部分失敗fieldは意図的に持たない)。

- **実装状態: [部分]** 共通validate_cosine_vector (kio-adapter/src/types.rs:246-268) が次元一致+有限+非ゼロnormを検査しgemini_embeddingが使用。id全単射検査・embedding_profile_hash/modality/distanceメタデータ照合は0件。
### U89 Vertex embedding の並列実行規約変更 [P1]
- 出典: gap-07-06 G17
- spec §: 07-adapter-spec.md §5.3
- 種別: 挙動
- 統合要約: Vertex embeddingの並列方針を「client側で並列+429 backoff」から「client側の並列はタスク間 (別batch_requests行) で行い、単一タスク内の複数requestは直列」に変更する。

- **実装状態: [判定不能]** send_embed_batch (main.rs:9601) はtask内全chunkを1回のrun_embedding_adapter呼び出しに集約 (複数requestの直列/並列という枠組み自体が現状と一致しない)。task間並列も0件 (spawn/par_iter無し)。挙動trace要。
### U90 embeddings/chunk_vec SQL定義の正本移動 [P2]
- 出典: gap-07-06 G18
- spec §: 07-adapter-spec.md §5.3
- 種別: schema
- 統合要約: `embeddings`テーブルのCREATE TABLE定義をこの節から削除し、`embeddings`/`chunk_vec`両テーブルのSQLite schema正本が04-pipeline.md §4.3であると明記する。

- **実装状態: [適合済みの可能性]** embeddings/chunk_vec DDLは既にkio-index (fts.rs) のみに存在、kio-adapter側に重複無し — 正本一本化は既に実態と一致。
### U91 Batch実行契約とプロバイダ採用条件の新設 [P0]
- 出典: gap-07-06 G19, sol G37 (該当部分)
- spec §: 07-adapter-spec.md §5.7
- 種別: 新規機能
- 統合要約: 「Batch実行契約とプロバイダ採用条件」を全面新設する。upload/create_job/get_job/list_jobs/list_uploads/delete_upload/fetch_output/provider_scope_idのtrait契約、transient/rate_limit/permanentのエラー分類契約、request単位の課金報告契約に加え、採用可否を決めるプロバイダ条件7項目 (list_uploads可視化・可視化遅延上限・保持期間・intent_token埋込・安定識別子 `custom_id (= unit_key)`・投入拒否課金の宣言・job id恒久非再利用) を新設する。job id/provider request idの恒久非再利用要件はsyncも免除しない。

- **実装状態: [未実装]** upload/create_job/get_job/list_jobs/list_uploads/delete_upload/fetch_output/provider_scope_id、kio-adapter/src/traits.rsに0件。Batch実行契約trait自体が存在しない。
### U92 ログ記録フィールドの拡張と adapter_id=tool_id 規約 [P2]
- 出典: gap-07-06 G21
- spec §: 07-adapter-spec.md §7
- 種別: schema
- 統合要約: ログに残してよいフィールドをexecution_mode/scope_id/error_code/error_category/retry_after_ms/network_consent/adapter_kind/input_hash/intent_token/submission_seq/usage_validation/billing_source等へ大幅拡張する。`adapter_id`はtools.tomlの`tool_id`と同一値である規約も新設する。

- **実装状態: [部分]** adapter_id=tool_id規約は既にtestで確認済み (catalog.rs:729)。network_consent/submission_seq/usage_validation/billing_source等の新規ログfieldは0件。
### U93 ストリーミング処理の全面改訂 (staging確定・失敗保全・cleanup・retry合成) [P0]
- 出典: gap-07-06 G25
- spec §: 07-adapter-spec.md §8.3
- 種別: 挙動
- 統合要約: ストリーミング処理を全面改訂する。旧は「応答完了後に受け入れ検査を通過した時点でmanifestへ一括確定、失敗時は完了済みunitのみ確定・未完了はpendingで再開可能」だったが、新は検査を「全体集合」に対して行い通過するまで一切公開せず、失敗時は完了済みunitを保全するがtask自体をfailed(retryable)にする (manifestにpending状態は存在しない)。task終端時のstaging cleanup順序規約、同一root名残存時の`.kio/.lock`内前置回復、no-replace公開、retry応答の合成規則 (transport中断のみ凍結保全対象、受け入れ検査reject起因は破棄)、staging物理喪失時の全再取得を新設する。

- **実装状態: [未実装]** ".kio/staging/"ディレクトリ概念が無い (genericな"staging"という単語のみ、専用layout無し)。全体集合検査→一括publish再設計も未確認。
### U94 [markdownize.incremental] include_neighbors 設定キーの削除 [P2]
- 出典: gap-10-03 G68
- spec §: 10-operations.md (adapter config例)
- 種別: 削除
- 統合要約: config例から`include_neighbors = 1`が削除された。付随する説明文は無いが、`[markdownize.incremental]`セクションの設定キー一覧からの除外であり、schema上もこのキーが不採用になった可能性がある (削除理由の記述なし)。

- **実装状態: [判定不能]** config.schema.jsonはinclude_neighborsキーを保持 (config.schema.json:117) しつつコード側は値1以外を強制拒否 (scope.rs:2266-2277、test済み)。schema key自体を削除すべきかは統合要約自身も断定していない。
### U143 incremental 発動条件の精密化 (file_id廃止・rename非追跡・連続カウンタ更新規則) [P1]
- 出典: gap-04 G10, G11, sol G27
- spec §: 04-pipeline.md §3.1
- 種別: 挙動
- 統合要約: incremental発動条件1を「同一file_idに対する既存done normalization_run」から「同一ファイル (=scope内の同一path binding。file_idは廃止済み) に対する既存done normalization_run」へ変更し、renameを跨いだ同一性は追跡しない (rename+編集はfull強制) ことを明記する。発動条件5 (直前N回連続incrementalならfull強制) のカウンタ更新規則を新規定義する: accepted incremental応答のfinalizeで+1、accepted full応答のfinalizeで0へreset、正常な制御応答 (fallback_to_full) とrejectされた応答はどちらにも数えない。カウンタ喪失時は§5.7の安全側規定 (full強制) に従う。

- **実装状態: [適合済みの可能性]** previous_instance_for_pathは既にpath binding基準 (main.rs:11184、file_id不使用)。consecutive_incremental_countはtasks.jsonlをpath別に走査しIncremental Doneを連続カウント・非Incrementalで打切り (main.rs:11944-11960) — reject/fallback応答は非Doneのため自然に数えない、新規則と機能的に一致。
## J. schema / path / CAS / 正本表 (03)

### U95 truth file 耐久書込 primitive (fsync規律の本体) [P0]
- 出典: gap-04 G1, G2, G3, G4, G5, sol G23 (ingest部分), G24
- spec §: 04-pipeline.md §1.1
- 種別: 挙動
- 統合要約: ingest時のraw_hash計算とCAS保存bytesは同一のopen・同一のストリームから得ることを要求する新規則を追加する (hash用と保存用に2回openすると間の書き換えで「hash Aの名前に内容B」が保存されCASが破壊され得るため)。読み取りの前後でstat (size, mtime) が同一であることを確認し、変化していたら当該ファイルはこの実行では取り込まず次回へ回す。「statが前回と同じなら再hashを省略する」最適化を実装する場合、mtimeが前回判定時刻と同一秒以降なら適用してはならない (mtime秒粒度によるGit indexと同型の罠)。`.kio`配下のtruth (CAS object・HEAD/refs・chunks.jsonl等) の作成・書換手順を新規定義する: (1) 同一filesystemのprivate tempへ完書き→(2) 内容検証→(3) file fsync→(4) atomic rename (immutable なCAS objectはno-replace、mutableなtruthは置換rename、直列化は`.kio/.lock`) →(5) 親directory fsync。新規中間directory (fan-out shard等) はmkdir→親directory fsyncを耐久済みdirectoryに到達するまで連鎖してから当該subtreeのpublishを行い、削除操作 (unlink/rmdir、purgeのdeleted相等) も各削除後に包含directoryをfsyncしてからjournal phase/postconditionを前進させる。

- **実装状態: [適合済みの可能性]** stage_scope_fileは単一read loopでhasher更新とstaged.write_allを同時実行 (scope.rs:2716-2757、同一open・同一streamで一致)、読後サイズstat照合、staged.sync_all()、親dir fsync (cas.rs:318-319,1635-1636)、open_regular_nofollowのdev/inode照合 (cas.rs:1779-1816) が既存。mtime同一秒回避は該当最適化自体が無く該当なし。
### U96 unit識別・diff schema の精密化 [P0]
- 出典: gap-04 G6, G7, G8, G9, sol G25
- spec §: 04-pipeline.md §2, §2.2
- 種別: schema / 挙動
- 統合要約: DOCXのunit種別を「heading section/page」から「page (prepareの変換PDF経由。heading単位の分割はchunk (Step 3) の責務であり unitでは行わない)」に変更する。画像は unit_kind "image" から "doc:1" へ、Markdownは「heading section」単位から「doc:1」(単一unit) へ、codeは「file/symbol」単位から「doc:1」へ変更し、heading/symbol単位の分割はunit段階ではなくchunk (Step 3) の責務に移す。XLSXのsheet unit_key生成規則に、元シート名に含まれる`#`を`##`へエスケープしてから重複連番"#2"等を付す規則を追加する (可逆・決定的)。exact対応 (unchanged) のLCS計算で同スコアの対応が複数ありうることを認め、tie-breakとして対応ペア列を (旧index列, 新index列) の辞書順で最小になるものを選ぶ完全順序を新規定義する。

- **実装状態: [部分]** File/HeadingSection/Symbol→"doc:1"は既に統一済み (prepare.rs:231)。ImageのみunitKeyが"image:{index}"のまま (prepare.rs:230、doc:1化未実施)。XLSXシート名/##エスケープは0件 (prepare.rs:169固定"Sheet1")。LCS tie-break (lcs_fingerprint_pairs, prepare.rs:447-474) は決定的だが辞書順最小規則との一致は未検証。
### U97 chunk span を byte_start/byte_end (UTF-8バイトオフセット) へ全面改称 [P0]
- 出典: gap-04 G22, gap-05 G26, gap-10-03 G27, gap-rest G14, sol G18
- spec §: 03-data-model.md §2.1, §5.3, §8.1, §8, 04-pipeline.md §4.1, 05-runtime.md §1 (レスポンス例), 08-evidence-pointer-spec.md §2.1, §2.2, §2.3, §3.1 手順7
- 種別: schema (破壊的変更)
- 統合要約: chunk境界のフィールド名と意味論を、旧「char_start/char_end (文字単位オフセット、nullable INTEGER)」から新「byte_start/byte_end (UTF-8 byte span、unit-local・0-based half-open、NOT NULL)」へ全面変更する。chunks表DDL・chunk identityタプル・chunk_hash算出式・全文view組み立て規則・検索結果レスポンスJSON・Evidence Pointer JSON (必須/optionalフィールドおよびURI optionalフィールド一覧・§3.1手順7の本文取り出し) の全てに波及する破壊的変更であり、旧仕様のまま文字単位オフセットとして実装すると新仕様と不整合になる。

- **実装状態: [未実装]** char_start/char_end (nullable INTEGER) が全域で現役 (chunking.rs, fts.rs:512-513, embedding_store.rs:691-692)。byte_start/byte_end 0件。
### U98 chunks 表 DDL の精密化 (NOT NULL明示・heading_path・gen・objects再構築例外) [P0]
- 出典: gap-04 G19, G20, G21, G23
- spec §: 04-pipeline.md §4, §4.1
- 種別: schema
- 統合要約: 「真実はobjects/、SQLiteは再構築可能」という不変式に、embeddingsの`target_type='query_cache'`行はobjectsに由来せず復元されないという明示的な例外を追加する。`chunks.chunk_id`・`embeddings.id`・`schema_migrations.name`の3列で`TEXT PRIMARY KEY`から`TEXT NOT NULL PRIMARY KEY`へDDLを変更する (SQLiteのrowid表ではTEXT PRIMARY KEYがNOT NULLを含意しないため)。`heading_path`列を`TEXT`(nullable)から`TEXT NOT NULL`へ変更し、見出し未出現の場合は空 ([]相当) で表現しNULLは許可しないと明記する。`gen INTEGER NOT NULL DEFAULT 0`から`gen INTEGER NOT NULL`へ変更し、chunkは常にnormalized instance由来のためDEFAULTを持たないと明記する (挿入時に明示指定が必須)。

- **実装状態: [部分]** 本番chunks DDL (fts.rs:503-518) は既にheading_path TEXT NOT NULL・gen INTEGER NOT NULL(DEFAULT無し)で新仕様と一致。ただしchunk_id/embeddings.idは依然"TEXT PRIMARY KEY"(NOT NULL明示無し、fts.rs:504,529)。char_start/char_endはU97同様未改称。
### U99 chunk_publications / index_metadata / chunks.jsonl publication event schema [P0]
- 出典: gap-04 G24, G25, G26, G27, gap-05 G20, gap-10-03 G33, sol G9 (chunks.jsonl部分), G30 (schema部分)
- spec §: 04-pipeline.md §4.1, §4.5, 03-data-model.md §2, §8.1
- 種別: schema
- 統合要約: `(chunk_id, introduction_commit)`の多対多relationを持つ`chunk_publications`表を新設する (単一の`first_seen_commit`ではmergeの側枝等incomparableな複数導入を表現できないため)。単一行の`index_metadata`表 (id=1固定、index_generation ULID、last_lifecycle_epoch) を新設し、index_generationはrebuild/purge/enrichment finalize/FTS内容変化/tombstone lifecycle更新のたびに更新する。`chunk_config_generations`表に`introduction_commit TEXT NOT NULL`列を追加しUNIQUE制約を`(chunk_id, chunking_config_hash)`の2列から`(chunk_id, chunking_config_hash, introduction_commit)`の3列に変更する。`chunks.first_seen_commit`のコメントを「この chunkを含む最初のcommit」から「最初のpublication commit (便宜列。時点条件の正本はchunk_publications)」へ変更し、時点指定検索の正本としての地位をchunk_publicationsに譲る。`.kio/chunks.jsonl`のcreation行schema`{chunk_id, chunking_config_hash, created_at, first_seen_commit, path}`に加え、新規「publication event行」`{event:"publication", chunk_id, chunking_config_hash, introduction_commit}`を定義する (incomparableな別枝での後発公開の記録)。auto snapshot作成時、新規chunk行への`first_seen_commit`刻印に加え`chunk_publications`への追記と、初回以外の追加introductionはchunks.jsonlへpublication event行として同時appendする。検索での時点条件の消費 (ancestor-or-equal判定) はH領域 U71 を参照。

- **実装状態: [未実装]** chunk_publications/index_metadata/introduction_commit、0件。chunks.first_seen_commitは単一nullable列のまま (fts.rs:516)。
### U100 chunk境界の正準規則精密化 (UCD Script slug化・scalar value単位・unicode_version) [P0]
- 出典: gap-04 G28, G29, gap-10-03 G65, sol G17
- spec §: 04-pipeline.md §4.1 (chunk境界の正準規則), 03-data-model.md §5.3, §11, 10-operations.md §12.3
- 種別: schema / 挙動
- 統合要約: section_id生成のslug化における「日本語文字」の定義を、非形式的な「ひらがな/カタカナ/漢字」からUCDのScript property (Script_Extensionsは不使用) によるHiragana/Katakana/Han+長音記号U+30FC・々U+3005への厳密な固定に変更する。使用するUCD版はchunking configの`unicode_version`としてhash入力に含めることを必須化し、版変更はchunking_config_hashの変更として扱う。段落境界での貪欲分割アルゴリズムを精密化する: 片の境界となる空行列は分割片のspanに含めないが同一片へ取り込んだ段落間の空行は含める、貪欲判定は片span全体のscalar数で行う。max_charsと「文字位置」の計数単位をUnicode scalar value (code point) と明示し、機械分割はscalar境界でのみ行いUTF-8 byte途中やgrapheme cluster単位では切らない。`unicode_version`はfolder-config.schema.jsonでもrequired化し (既定17.0.0)、欠く旧configは実装同梱版として読み次回locked mutationで補完書込みする後方互換規則を新設する。config例には「max_charsの計数単位=Unicode scalar value」というコメントも追記する。

- **実装状態: [部分]** is_japanese()はハードコードUnicode範囲判定 (chunking.rs:362-367、平仮名/片仮名/CJK統合漢字ブロック) でUCD Script property不使用、々(U+3005)も範囲外で漏れ。unicode_version hash入力/config key 0件。
### U101 embeddings / chunk_vec / chunk_fts DDL の精密化と query_cache 機構 [P0]
- 出典: gap-04 G30, G31, G32, G33, G34, gap-10-03 G64
- spec §: 04-pipeline.md §4.2, §4.3
- 種別: schema / 新規機能
- 統合要約: FTS5仮想表`chunk_fts`から`chunk_id UNINDEXED`列を削除し (「2026-07-14実装準拠へ更新」)、`tokenize='trigram'`をDDLに明示的に埋め込み、3つのトリガー (chunks_ai/ad/au) もchunk_idを含まないINSERT/VALUESへ変更する (hitのrowidでchunksとjoinしchunk_idはchunks側から取得)。`chunk_vec`の`embedding`列定義を`FLOAT[<dim>]`から`float[768] distance_metric=cosine`という具体的な固定値へ変更する。`embeddings(target_type)`への新規indexを追加する (query_cache行の256行剪定・列挙がcorpus全embeddingsをSCANしないための性能対策)。`chunk_vec`のrebuild-db導出手順を新規定義する: `chunks.text_hash`と`embeddings.target_id`の結合は`target_type='chunk'`の行のみを対象とし、現行tool-lockのembedding profileに一致する行のみに限定、chunkごとの候補は0件 (pending) または1件のみが正常で2件以上はcorruptionとしてrebuild停止する。vector|hybrid検索cursor page1が使うquery vectorを`embeddings`表の`target_type='query_cache'`行としてキャッシュする機構を新設する: `target_id`はquery_vector_digest (vector BLOBのsha256)、idは冪等 (target_type="query_cache", target_hash=query_vector_digestの同一id導出式を通常embeddingと共有し`ON CONFLICT(id) DO NOTHING`で冪等)、INSERTと256行/scopeの剪定はcursor返却前に同一Txで完了、query本文/text_hashは保存しない、rebuild-dbでは復元せず破棄、purgeのスコープ外、chunk_vecへは展開しない。

- **実装状態: [部分]** chunk_fts は既にchunk_id列を持たない (fts.rs:556、トリガーもrowid/text/heading_pathのみ — 既に新仕様と一致)。chunk_vecはCHUNK_VEC_DIMENSIONS定数で768/cosine固定済み (fts.rs:586-588,718)。ただしtokenizerはconfig選択式でDDL固定文字列ではない (fts.rs:549-552)。query_cacheはenum variant1件のみ (embedding_store.rs:585) で検索cursorフローに未配線。embeddings(target_type)専用index 0件。rebuild_chunk_vec (embedding_store.rs:242-266) はprofile_hashフィルタ・2件以上corruption検知が無い。
### U102 embedding object 保存bytesのバイナリformat確定 [P0]
- 出典: gap-10-03 G63, sol G19 (該当部分)
- spec §: 03-data-model.md §8.1
- 種別: schema
- 統合要約: embedding objectの保存bytesを『JCS(identity fields) + LF + base64(vector, float32 little-endian) + LF + lower_hex64(sha256(vector bytes))』に固定する (旧spec には保存byte形式の規定が無かった)。fsckはidentity hash再計算に加え、vector長 (dimensions×4 bytes)・有限値 (NaN/Inf拒否)・vector digest一致 (bit flip検出) を検査する (F領域 U39 の検証対象拡大と対応)。

- **実装状態: [未実装]** embedding object保存bytesのbase64/LE float32/digest footer形式、構築コード0件。
### U103 旧SQLiteテーブル (files/normalization_runs/prepared_units) の廃止 [P0]
- 出典: gap-04 G35, G39, gap-10-03 G60, G61, G62, sol G15
- spec §: 04-pipeline.md §4.4, §4.7, 03-data-model.md §4.1, §8
- 種別: schema / 削除
- 統合要約: 「その他のテーブルの正本」一覧を再編し、`files`/`normalization_runs`が「SQLiteテーブル非採用。正本は`.kio/manifest.json`」、`prepared_units`が「SQLiteテーブル非採用。決定論的に再導出する論理台帳」と明示する。旧spec の`CREATE TABLE files (file_id, path, raw_hash, size_bytes, mtime, kind, first_seen_at, last_seen_at, status)`と`CREATE TABLE normalization_runs (...)`の定義を廃止し、working stateの実体は`.kio/manifest.json`の`files`配列 (`manifest.schema.json`で検証) になる (`file_id`/`size_bytes`/`mtime`/`kind`/`first_seen_at`/`last_seen_at`列は新schemaに持ち込まれず削除、`status`は`new|modified|deleted|unchanged`の固定enumに整理)。run状態は独立永続化せずmanifest+unit objectの存在から導出する (`parent_run_id`チェーンは永続化せず喪失許容の運用データ)。`prepared_units`のCREATE TABLE定義も完全に削除し「未実装のまま廃止」と明記、prepare結果の台帳はkio-pipelineのin-memory構造として持てば足りる。永続ストア一覧§4.1を新設し、SQLiteを使うのはindex/sqlite.db・scope-registry.sqlite・cost-ledger.sqliteの3ファイル (計12テーブル) に確定する。

- **実装状態: [適合済みの可能性]** manifest.schema.jsonは既にfiles[]={path,raw_hash,status(new|modified|deleted|unchanged)}のみでadditionalProperties:false (file_id/size_bytes/mtime/kind/first_seen_at/last_seen_at無し)。本番SQLiteテーブル一覧 (chunks/chunk_config_generations/embeddings/tree_entries) にfiles/normalization_runs/prepared_unitsは元々存在しない。
### U104 tree schema v2/v3 の新設 (manifest_hash・chunking_config_hash・chunk_set_hash) [P0]
- 出典: gap-04 G36, gap-10-03 G37, gap-07-06 G32, sol G20
- spec §: 03-data-model.md §8, 04-pipeline.md §4.5, 05-runtime.md §4.2, §8.1, 06-cli-spec.md §1, 10-operations.md §12.5
- 種別: schema
- 統合要約: tree object schemaに3つの新規fieldを追加する。v2: `entry.normalize.manifest_hash` (対応manifest objectのhash — unitのfailed→done遷移で変わるため derived成果の変化がtree_hashを変える) と`tree.chunking_config_hash`。v3: `tree.chunk_set_hash` (公開chunk集合のdigest — UTF-8バイト列昇順ソート+LF連結+末尾LFのsha256、存在ベースで部分集合も許容)。いずれも「実装・store公開前のschema確定でありMAJOR bumpではない」と明記し、v1/v2 treeはlegacyとして読取可、新規commitはv3で書く。`tree_entries`表にも`manifest_hash TEXT`列を追加する (v1 treeはNULL legacy)。`kio diff`はtree schema v2/v3が生むderived-onlyの変化 (normalize_manifest_changed/chunking_config_changed/chunk_set_changed/tool_lock_changed/resurrection_published) を差分として表示する義務を負い、derived-only commitを「差分なし」と表示してはならない (片側が旧版treeの場合はderived差分を`unknown`と表示)。

- **実装状態: [未実装]** TreeEntry/NormalizeRef (dag.rs:15-30) はtool_profile_hash+genのみ。manifest_hash/chunk_set_hash/tree.chunking_config_hash、0件。tree schemaはv1相当のまま。
### U105 世代 (gen) 作成の第二経路と provenance lineage (parent_instance新設) [P0]
- 出典: gap-07-06 G26, gap-10-03 G35, G36, gap-rest G48, sol G11
- spec §: 03-data-model.md §2.1, §8, 06-cli-spec.md §1, 09-mvp-scope.md §5.1
- 種別: schema / 挙動
- 統合要約: 同一(raw_hash, tool_profile_hash)からのgen+1新instance作成トリガーを、旧「`kio reindex --force`のみ許可」から「`kio reindex --force`、またはprepare profile/renderer変更によるprepared_hash変化が駆動する再Markdownize (例外)」の2経路に拡張する (自動gen+1はオンライン課金を伴うため確認プロンプト+budget guardrailの対象)。manifest schemaに新規field`parent_instance` (`{raw_hash, tool_profile_hash, gen}`) を追加し、incrementalで親のrawが異なる場合 (raw更新をまたぐ通常incremental) は必須で記録する (`parent_gen`は同一raw内の局所番号であり整数だけでは親instanceを一意に復元できないため、full実行ではnull)。provenance chainの担い手も変わり、旧`parent_run_id`はtask cacheの揮発情報 (永続provenanceではない) に格下げされ、`kio reindex`の上書きチェーンの永続記録先は「parent_run_id」から「manifestのparent_gen (同一raw内)/parent_instance (raw跨ぎincrementalの三つ組、fullではnull)」に変更する。`--force`も「唯一の上書き経路」から自動gen+1の存在を認める「明示経路」に変わる。

- **実装状態: [部分]** parent_genは既存 (markdownize.rs:147)。parent_instance (raw_hash/tool_profile_hash/genの3つ組) は0件。
### U106 up_to_date 判定 state machine の全面改訂 [P0]
- 出典: gap-10-03 G34, sol G12
- spec §: 03-data-model.md §6
- 種別: 挙動
- 統合要約: 判定アルゴリズムを全面改訂する。新規: (a) `not inst.units` (空unit集合) を`up_to_date`として最優先判定する — 後続の`all(u.status=="failed")`が空虚真でfailedに誤分類されるバグを防ぐ。(b) 全unit失敗時を`settled` (全て permanent、terminal) と`failed` (retryable含む) に新規分岐する。(c) `missing_output`判定を`partial`判定より前に移動する — done宣言unitのobject欠落をfailed unitとの併存時にも見逃さない (旧順序では`any failed`が先に真になり到達できなかった)。ファイル状態分類に`settled`を新規追加する (A領域のtask settled化 U3 と対)。

- **実装状態: [未実装]** "up_to_date"/"settled"という状態機械ラベル・§6型の判定関数が見当たらない。空unit集合優先判定・missing_output前倒し順序も未確認。
### U107 no-op snapshot 判定の例外拡張と auto snapshot 契機の拡大・耐久順序確定 [P0]
- 出典: gap-04 G55, gap-05 G75, G76, G77, sol G2
- spec §: 04-pipeline.md §5.4, 05-runtime.md §8.1
- 種別: 新規機能 / 挙動
- 統合要約: MVPでのsnapshot生成契機を、旧2つ (明示的commit、`kio index`成功完了時のauto snapshot) から3つに拡張し、`kio batch resume`/`kio batch retry`/`kio reindex --force`がオンライン成果 (normalized/chunk) をfinalizeした成功完了時も同様にauto snapshotを作る (derived成果の変化はtree entryのmanifest_hash/treeのchunking_config_hash/chunk_set_hashを変えるためtree_hashが実際に変わりno-op規則がそのまま成立する)。no-op規則 (tree_hash一致ならcommitを作らない) に2つの例外を新設する: (a) resurrection finalize (erase/purge済みrawの再ingest) は同一bytes再現でtree_hash・chunk_set_hashがHEAD一致でもpublication commitを作る (retire eventとintroductionを刻むcommitが無いと復活chunkを検索対象化できないため)。(b) no-op判定はtree_hashに加えcommitのtool_lock_hashも比較する (embedding profile更新のみでもlockが変われば commitを作る)。snapshot finalizeの耐久順序を「(1) chunks.jsonlへcreation/publication event行をappend+fsync→(2) SQLite反映→(3) commit/ref publish」と規定し、(1)と(3)の間のcrashで残ったdangling event行はrebuildが無視し (commit objectが存在するがref不達の行=orphan/disconnectedは無視しない)、次回finalizeが同内容を冪等に再appendする。chunks.jsonl末尾のtorn tailは切り詰めて無視する。

- **実装状態: [部分]** auto_snapshot_with_bound_normalizeは`kio index`・`kio reindex --force`から既に呼ばれる (main.rs:723,3665) が、batch resume/retryのrun_batchには呼び出しが無い (3トリガー中2つのみ)。no-op判定はtree_hash一致のみ (scope.rs:1078)、tool_lock_hash比較・resurrection例外は未確認。
### U108 commit_type の検証機構訂正・値域永久固定・purged_raws 必須field [P0]
- 出典: gap-05 G29, gap-10-03 G39, G40, G41, gap-rest G4, sol G21, G60 (該当部分)
- spec §: 03-data-model.md §8, 05-runtime.md §2.1, 10-operations.md §8
- 種別: schema / 挙動
- 統合要約: commit_typeの値域固定機構の記述を「SQLite CHECK制約で固定」から「commit objectのschema検証 (publication時のloader) で固定 — commitはCAS JSON objectでありSQLiteにcommit表は無い」に訂正する (旧spec 通りにSQLite commitsテーブル+CHECK制約を実装すると誤りになる)。旧spec は「将来、既存互換性を壊さないmigration planを明記する」としていたが、新spec は「commit_typeの値域は永久固定であり、新しい区別が必要に見える場合も値域は変更せず既存type+metadataで表現する (migrationは行わない)」と将来のmigration経路自体を撤回する。`commit_type=purged`のcommit objectに新規必須field`purged_raws` (当該purge対象raw_hashの昇順配列) を追加し、marker検証 (tombstone/erase receipt) がこのfieldと対照して他rawの正当なpurge commitを`in_commit`に流用した偽markerを検出可能にする (本fieldはstore format初版から必須でありlegacy許容なし)。

- **実装状態: [部分]** commit_type検証は既にschema/loaderレベル (dag.rs:342、SQLite commits表自体が存在しないため記述訂正と整合)。purged_rawsフィールドは0件。
### U109 manifest / toollock の immutable CAS object 化 [P0]
- 出典: gap-10-03 G20, sol G6
- spec §: 03-data-model.md §1, §2, §2.1, §5.2, §8.1
- 種別: schema
- 統合要約: Object種別に`manifest` (normalized instance manifestの確定版、canonical JCS bytes) と`toollock` (tool-lock.jsonの確定版) を新規追加する。manifestはfinalize (初回確定+partial retryのfailed→done反映) のたびに`objects/manifests/ab/cd/<manifest64>`へcontent-addressedで書込み、toollockはmaterialize時に`objects/toollocks/ab/cd/<toollock64>`へ書込む。tree entryの`normalize.manifest_hash`とcommitの`tool_lock_hash`がそれぞれのobjectを指し、作業コピー (manifest.json/tool-lock.json) は最新版のみで過去版の解決はCAS object経由となる。

- **実装状態: [未実装]** ObjectKindはRaw/Tree/Commitのみ (cas.rs:153-157)。Manifest/Toollock種別、objects/manifests//objects/toollocks/、0件。
### U110 staging/ ディレクトリの新設 (外部実行streaming staging) [P0]
- 出典: gap-10-03 G23, sol G7
- spec §: 03-data-model.md §2
- 種別: schema / 新規機能
- 統合要約: `.kio/staging/<raw64>.<tool64>.<adapter_kind>/`を外部実行のstreaming staging領域として新設する。各root直下に耐久descriptor.json (scope_id/raw_hash/tool_profile_hash/adapter_kind) を持ち、公開は「private temp directoryにdescriptorごと完書き→fsync→root名へatomic rename (no-replace) →親directory fsync」の順で行い、payload書込みはdescriptor公開後にのみ行う。purge/status/prune-orphansの帰属列挙はdescriptorの全走査が正本 (tasks.jsonl非依存)。ストリーミング処理での消費はI領域 U93 を参照。

- **実装状態: [未実装]** ".kio/staging/<raw64>.<tool64>.<adapter_kind>/"layout、0件 (U93と同一根拠)。
### U111 tag canonicalization (simple case folding) と names.jsonl 論理名台帳 [P0]
- 出典: gap-07-06 G41, gap-10-03 G24, G25, sol G8
- spec §: 03-data-model.md §2, 06-cli-spec.md §1, 本文 (kio tag), 10-operations.md §7.5.1
- 種別: schema / エラー分類
- 統合要約: canonical tag refのdigest算出を「NFC正規化+Unicode lowercase」から「NFC正規化+Unicode simple case folding (locale非依存)」かつ「論理tag名のUTF-8バイト列」に対するsha256へ変更する (正規化規則自体の改訂はdigestの非互換変更でありkio_format_versionのmigration経路で再導出)。実装同梱UCD版で未割当のcode pointを含むtag名は新規エラー`KIO-E-CONFIG-USAGE-001`で拒否する。collision判定アルゴリズムも同じくsimple case foldingに変更する。新規append-onlyファイル`refs/tags-v1/names.jsonl`を論理tag名のtruthとして新設し、`{digest64, logical_name, recorded_at}`を追記する。書込順序は「names行append (fsync) →ref作成」に固定し (逆順はcrashで名前なしrefを生む)、`kio tag --delete <name>`はcanonical refのみをatomicに除去しnames.jsonlの行は残す (監査保全)。

- **実装状態: [部分]** canonicalize相当はNFC+Rust標準char::to_lowercase (portable.rs:22) — full Unicode lowercaseでsimple case foldingではない。names.jsonl 0件。
### U112 文字列 preimage の UTF-8 バイト列 hash 計算の共通規則化 [P1]
- 出典: gap-10-03 G26
- spec §: 03-data-model.md §2, §5.1, §8.1
- 種別: schema
- 統合要約: `unit_ref = base16(sha256(unit_key))[0:16]`等の文字列preimageハッシュについて、エンコーディングが未規定だった旧spec に対し、「規定の正規化を適用した後のUTF-8バイト列に対してsha256を計算する」共通規則を新設する。unit_key・tag正規化済み論理名・prompt_template_hashの正規化結果等すべてに適用され、UTF-16等の実装差を明示的に禁止する。§5.1の手順5も「UTF-8バイト列に対しsha256」に変更する。

- **実装状態: [適合済みの可能性]** unit_refはunit_key.as_bytes()を直接ハッシュ (prepare.rs:219-222) — Rust &strは常にUTF-8保証のため該当箇所は構造的に既に規則を満たす。
### U113 objects/images/ → objects/image/ ディレクトリ名変更 [P0]
- 出典: gap-10-03 G22
- spec §: 03-data-model.md §2
- 種別: schema (破壊的変更)
- 統合要約: 物理レイアウトのimage object格納先を`objects/images/ab/cd/<image64>` (複数形) から`objects/image/ab/cd/<image64>` (単数形) に変更する (dir名は§1の`objects/<type>/`公式どおりtype名(単数形)と一致させる)。パス互換性を壊す変更。

- **実装状態: [未実装]** ObjectKind::Imageのディレクトリ名は依然複数形"images" (cas.rs:32) — 単数形"image"へ未移行。
### U114 正規化view の order 一意性制約・comment-safe encoding・Source field 非再生成 [P1]
- 出典: gap-10-03 G28, G29, sol G13
- spec §: 03-data-model.md §2.1, §8
- 種別: schema / エラー分類 / 挙動
- 統合要約: 全文view組み立て規則に新規制約を追加する。manifest.units[]の`order`はunit間で一意でなければならず、重複は`KIO-E-STORE-CORRUPT-001`のcorruptionとする。`<!-- KIO-MISSING-UNIT unit_key error_kind -->`およびSourceヘッダのfilename挿入は`--`を含む値をpercent-encodeするcomment-safe規則を新設する (生値挿入はcomment構造を破壊するため)。全文viewヘッダのSource値は生成時点のfilenameの記録であり、同一(raw_hash, tool_profile_hash)を別path・別名で再配置してもviewを再生成しないと明確化する (view喪失後の`kio repair`再生成では再生成時点のfilenameを用いてよく、Source行はidentityを持たないinformational field)。

- **実装状態: [未実装]** KIO-MISSING-UNITマーカーはunit_key/error_kindを無エスケープで直接埋め込み (markdownize.rs:1359-1362、"--"のpercent-encode無し)。manifest.units内order重複検知も未確認。
### U115 scope_id 不変の例外 (kio import --as-new-scope の fork 複製は新 ULID 採番) [P2]
- 出典: gap-10-03 G30, gap-07-06 G34 (該当部分), gap-rest G30(sol), sol G64 (該当部分)
- spec §: 03-data-model.md §2, 06-cli-spec.md §10
- 種別: schema
- 統合要約: `scope_id`は「init時採番のULID、以後不変・export/importでも保持」が原則だが、例外として`kio import --as-new-scope`のfork複製は新ULIDを採番すると明記する (import自体はPhase 4+のため現時点の実装影響は小さい)。fork複製内に残る旧scope_idを含むobject URIの解決規則はG領域 U50 を参照。

- **実装状態: [未実装]** "kio import"コマンド自体が存在しない (Commands enumに無し、Phase 4+相当で影響小という統合要約の注記と整合)。
### U116 kio_format_version の保存場所・判定タイミング確定 [P0]
- 出典: gap-10-03 G13, sol G10
- spec §: 03-data-model.md §2, 10-operations.md §12.5
- 種別: schema / 挙動
- 統合要約: `kio_format_version`の保存場所を新規に明記する: 保存場所=`.kio/scope.json`の`kio_format_version`フィールド。互換判定はscope.jsonのschema validationより先に評価する原則を新設する。自己の対応上限より新しいstoreへの挙動を具体化する: 書き込み系は即時拒否 (`KIO-E-STORE-VERSION-001`・exit 8)、multi-scope searchは当該scopeをexcluded_scopesへ (H領域 U75)、単独scope読み取り系は書込ゼロのbest-effort動作 (query_cache書込不可のためcursor replay非保証)。

- **実装状態: [部分]** kio_format_versionはscope.jsonに保存済み (scope.rs:249、保存場所は新仕様一致)。だがvalidated_scope_id()はvalidate_json_schema(Scope)を先に実行しkio_format_version照合が後 (scope.rs:1536が1546-1550より先) — 新仕様が要求する順序と逆。KIO-E-STORE-VERSION-001/exit 8、0件。
### U117 scope_registry.scopes テーブルの SQL schema 確定と運用規約 [P0]
- 出典: gap-10-03 G9, G10
- spec §: 10-operations.md §3
- 種別: schema / 挙動
- 統合要約: scope_registryの保存情報を旧spec の平文フィールド列挙から、正式な`CREATE TABLE scopes`定義に変える。新規列`indexed` (sqlite.db構築済みフラグ) を追加し、PRIMARY KEYは`(scope_id, kio_path)`の複合キーとする。`approved_at`/`effective_ignore_hash`/`permission_status`はPhase 4+予約としてMVP schemaから除外する。運用規約として、WALモード+busy_timeout 5000msでの直列化、upsertは`(scope_id, kio_path)`キーで`indexed`は単調 (MAX) 更新のみ、root_path/kio_pathはcanonical形保存、同一kio_pathで異なるscope_id観測時は旧行削除 (再init対応)、同一scope_idを新kio_pathで観測した場合も旧path行削除だが「旧pathがなお到達可能 (存在し有効な`.kio`) な場合はmoveと認定せず削除しない」という新規判定を追加する。

- **実装状態: [適合済みの可能性]** scopesテーブルDDLが新仕様と厳密一致: 複合PK(scope_id,kio_path)、indexed INTEGER NOT NULL DEFAULT 0、WAL+busy_timeout(5000ms) (registry.rs:77-85)。approved_at/effective_ignore_hash/permission_statusは元々列挙されず。
### U118 device data dir 実体の XDG_DATA_HOME 解決表記規約と owner-only 制限 [P1]
- 出典: gap-10-03 G15, G14
- spec §: 03-data-model.md §4, 10-operations.md §3
- 種別: 挙動
- 統合要約: 「device data dirの実体は`${XDG_DATA_HOME:-$HOME/.local/share}/kio`であり、本仕様の`~/.local/share/kio/`表記は全てこの解決結果を指す表記規約とする」と明記する (バックアップ手順とruntimeが同じpath解決を共有する目的)。device data dir (`~/.local/share/kio/`) をowner-only (0700) に制限する規約も新規追加する (best-effort、非unixはno-op。registry/cost-ledger/logsが利用パターンとスコープ地図を含むための保護)。

- **実装状態: [未実装]** xdg.rsに0o700/owner-only制限、0件。XDG_DATA_HOME解決自体は正しい (data_home(), main.rs:13387-13398) が権限制限が無い。
### U119 path validation の拒否集合拡張 (forward-only、legacy許容) [P0]
- 出典: gap-10-03 G75, sol G14
- spec §: 03-data-model.md §3
- 種別: schema / エラー分類
- 統合要約: 旧spec は「`/`を含むpathを持つtree/pointerはschema violation (KIO-E-STORE-PATH-001) として拒否する」のみだったが、新spec は拒否対象を拡張する: `\`・単独の`.`/`..`・NUL・control文字を含むpath、および「well-formed UTF-8でないbyte列のpath」も拒否する。この拒否は新規ingest・新規tree作成時のforward規則であり、既存tree entryの該当pathはread/inspect/search可能・fsckはlegacy警告として報告する後方互換規定も新設する。

- **実装状態: [部分]** is_logical_direct_child (dag.rs:92-98) は"/"とNULのみ拒否 (加えて"."/".."); バックスラッシュ・制御文字の拒否拡張は未実装。UTF-8整形式チェックはRust &strの型保証により実質該当なし。
### U120 purge/epoch・tombstones/lifecycle-epoch の永続ファイル layout 新設 [P0]
- 出典: gap-10-03 G31
- spec §: 03-data-model.md §2, §4.1
- 種別: schema / 新規機能
- 統合要約: `.kio/purge/epoch` (purgeのABA barrier、単調カウンタ、欠落=読取fail-closed) と`.kio/tombstones/lifecycle-epoch` (lifecycle更新の単調カウンタ、event appendごとに+1) を物理レイアウトに新規追加する。欠落時の再作成規則 (前者はjournal/event最大値+1から回復、後者はmax(last_lifecycle_epoch, 全event lifecycle_epoch最大値)+1で再作成+無条件1回転) も新規定義する (behavioral consumptionはE領域 U36、B領域 U15 を参照)。tombstone記録自体も「purgeのtombstone記録」から「purgeのtombstone lifecycle記録 (raw_hashごとのappend-only events[])」へ再定義する。

- **実装状態: [未実装]** purge journal機構自体は充実 (purge.rs PurgeJournal等) だが、".kio/purge/epoch"単調カウンタ・".kio/tombstones/lifecycle-epoch"という独立した新規layoutファイルは0件。
## K. error code / exit / CLI 表示の横断 (06 §7-8 / 10 §12)

### U121 exit code 表の全面再定義 (新設8/9・3/4の意味論変更・dead pointer分離) [P0]
- 出典: gap-04 G64, gap-07-06 G50, gap-10-03 G69, G70, sol G49
- spec §: 04-pipeline.md §5.6, 06-cli-spec.md §6, 10-operations.md §12.2
- 種別: エラー分類
- 統合要約: exit code表に新規コード`8` (incompatible profile/format version) と`9` (confirm拒否、purge等の確認プロンプトでno) を追加する。exit 3/4の意味論を、旧「3=一部失敗(retryable残あり)/4=全失敗permanent」から新「3=retryableな失敗が残っている (部分成功・lock取得失敗のような全体retryableを含む) /4=permanentな失敗のみが残っている (全失敗permanent、およびsettled partial (部分成功+残り全permanent、04§5.2) を含む)」に変更する。dead pointer (tombstoned/not_found/scope_unreachable) の分類も、旧「一律exit 4」から新「tombstoned/not_foundはexit 4、scope_unreachableのみretryableのexit 3 (再接続・registry再登録で回復可能)」に再分類する。

- **実装状態: [部分]** ExitCode enumは既にIncompatibleProfile=8・ConfirmationRejected=9を保有 (exit_code.rs) — 新規コード追加は完了。ただしscope_unreachable_errorは依然ExitCode::PermanentFailure(4)のまま (main.rs:6721-6728) — 新exit 3への再分類は未適用。
### U122 error_code の機械判定原則の明確化 (成功応答内error_code・error_kind閉enum例外) [P1]
- 出典: gap-05 G27, gap-07-06 G52, gap-10-03 G72, sol G49
- spec §: 05-runtime.md §1 (レスポンス契約), 06-cli-spec.md §8, 10-operations.md §12.1, 03-data-model.md §2.1
- 種別: 挙動
- 統合要約: 「成功応答 (exit 0) のerror_codeは縮退原因の機械可読分類であり失敗判定には使わない — 失敗判定はexit code (非0) が正である」という重要な区別を新設する。「error_codeのみを機械判定に使い、error_kindはユーザー向け表示専用」という原則に対し、明示例外を追加する: manifest`units[]`/Adapter出力`failed_units`の`error_kind`は04-pipeline.md §5.3の閉enum (フリーテキストではない) であり、unit単位のretry可否の機械判定に使う。

- **実装状態: [適合済みの可能性]** 成功出力のerror_codeと終了コードは既に分離構造 (main.rsの__exit_codeマーカー経由、append_exit_override_errorが出力自身の"error_code"を独立に読む、main.rs:388-408) — 新原則と一致。failed_units自体が無いため当該例外節は現状該当なし。
### U123 evidence verify 系 exit code 規則の全面改訂 [P0]
- 出典: gap-07-06 G51
- spec §: 06-cli-spec.md §7
- 種別: エラー分類
- 統合要約: evidence verify系のexit code規則を全面改訂する。`--strict`でscope_unreachableのみの失敗はexit 3 (retryable) に分離し、unverifiableはreason別に分岐 (tree_v1/manifest_missingは4、commit_shallowのみ・registry_duplicateは3)。sqlite.db不在時の統一規則 (`KIO-E-INDEX-REBUILDING-001`・exit 3)、multi-scope searchのSCOPE-ALL-FAILED優先順位 (VERSION→journal→DUP→REBUILDING) を新設する。`kio open/view/restore`のdead pointer規則もscope_unreachableをexit 3に分離する (旧は一括exit 4)。G領域のverify status 6値union (U57) の具体的exit mapping にあたる。

- **実装状態: [部分]** scope_unreachable_error共有ヘルパーがU121と同じくexit 4のまま (main.rs:6721-6728、open/view/restore/verifyへ波及)。SCOPE-ALL-FAILED-001は明示的にExitCode::PermanentFailure固定 (main.rs:418、コメントに「docs frozen — no new code」とあり意図的据置)。KIO-E-INDEX-REBUILDING-001自体は既存 (main.rs:1648)。
### U124 エラー DOMAIN 一覧の拡張 (REGISTRY/EMBED) と新規エラーコード群 [P0]
- 出典: gap-07-06 G53, G54, gap-10-03 G71
- spec §: 06-cli-spec.md §8, 10-operations.md §12.1
- 種別: schema
- 統合要約: エラーコードのDOMAIN一覧に`REGISTRY` (scope registryのlive clone重複・退役) と`EMBED` (embedding profile/modality検証) の2ドメインを新設する。エラーコード例一覧に新規コードを多数追加する: `KIO-E-PURGE-JOURNAL-ACTIVE-001` (未完了purge journal/epoch不変違反、retryable exit 3)、`KIO-E-REGISTRY-DUP-001` (同一scope_idの複数live clone)、`KIO-E-SEARCH-VEC-UNAUTHORIZED-001` (query embeddingの承認なし)、`KIO-E-STORE-VERSION-001` (対応上限より新しいkio_format_versionのstore、exit 8)、`KIO-E-COMMIT-RESTORE-CONFLICT-001`、`KIO-E-ADAPTER-APPROVAL-CONFLICT-001`、`KIO-E-ADAPTER-SPECVER-001`。

- **実装状態: [部分]** KIO-E-COMMIT-RESTORE-CONFLICT-001 (restore.rs:392等) とKIO-E-EMBED-MODALITY-001 (tool_lock.rs:468) は既存。KIO-E-REGISTRY-DUP-001/KIO-E-SEARCH-VEC-UNAUTHORIZED-001/KIO-E-STORE-VERSION-001/KIO-E-PURGE-JOURNAL-ACTIVE-001/KIO-E-ADAPTER-APPROVAL-CONFLICT-001/KIO-E-ADAPTER-SPECVER-001、全て0件。
### U125 fallback_reason の自由語彙明記 [P2]
- 出典: gap-07-06 G55
- spec §: 06-cli-spec.md §9 (API保証)
- 種別: 挙動
- 統合要約: 検索応答の`fallback_reason`が自由語彙であり閉enumにしないこと、機械判定はerror_code側が正でありAgentは未知のfallback_reason値を無視してよいことを新規に明記する。

- **実装状態: [適合済みの可能性]** fallback_reasonは既にOption<String>自由記述 (main.rs:984ほか全域) — 閉enumではなく新仕様と一致。
### U126 KIO-E-CONFIG-SCHEMA-NNN プレースホルダの確定 [P2]
- 出典: gap-07-06 G57
- spec §: 06-cli-spec.md §11
- 種別: エラー分類
- 統合要約: config schema validation失敗時のエラーコードをプレースホルダー`KIO-E-CONFIG-SCHEMA-NNN`から具体値`KIO-E-CONFIG-SCHEMA-001`に確定する。

- **実装状態: [適合済みの可能性]** KIO-E-CONFIG-SCHEMA-001は既に全箇所で具体値使用 (tool_lock.rs/main.rs/evidence.rs/dag.rs) — NNNプレースホルダは残っていない。
### U127 全コマンド共通 preflight 優先順位 (0)-(4) の確定 [P0]
- 出典: gap-10-03 G12
- spec §: 10-operations.md §3
- 種別: 挙動
- 統合要約: 全コマンド共通のpreflight検査順序を (0) kio_format_version互換判定 → (1) purge journal/epoch検査 → (2) registry live重複 → (3) index可用性 (`KIO-E-INDEX-REBUILDING-001`、復旧・初期化コマンドは対象外) → (4) command固有検査、と確定する。同時成立時は先順のerrorを返す。読取系はこの順序を冒頭1回適用し、返却直前の再検査は開始値との不変比較 (purge journal不在/purge epoch/lifecycle counter) を固定順で行い、不一致ならexit 3で結果破棄する。

- **実装状態: [未実装]** (0)-(4)を束ねた単一preflight関数が見当たらない。個別要素も不揃い — registry live重複検査 (2) は存在せず、KIO-E-STORE-VERSION-001 (0) も無い一方、KIO-E-INDEX-REBUILDING-001 (3) は単独で存在。
### U128 config schema validation の実行順序確定 (kio_format_version判定より後) [P1]
- 出典: gap-10-03 G73
- spec §: 10-operations.md §12.3
- 種別: 挙動
- 統合要約: config schema validation (scope.schema.json含む) の実行順序を新規に規定する: kio_format_versionの互換判定より後に走る (J領域 U116)。新しいstoreはschema validationに入らずread-only+新版誘導で縮退する。scope.schema.jsonへのkey追加は必ずkio_format_version MINOR bumpを伴うgovernanceルールも新設する。

- **実装状態: [未実装]** validated_scope_id()はschema検証 (scope.rs:1536) をkio_format_version照合 (scope.rs:1546-1550) より先に実行 — 要求順序と正反対 (U116と同一箇所)。
## L. その他 (01/02/09/README、上記に入らないもの)

### U129 GC (Garbage Collection) 機構全体 [P1] (Phase 4 実装要件、MVPには含まれない)
- 出典: gap-05 G30, G32, G33, G34, G35, G36, G37, G38, G39, gap-rest G41, sol G59, G60 (該当部分)
- spec §: 05-runtime.md §2.2, §2.4, §2.5, §2.6, 09-mvp-scope.md §3.1, 10-operations.md §8, §10.5
- 種別: 新規機能 / 挙動
- 統合要約: shallow化実行時、`(commit_hash, tree_hash, gc_policy, shallowed_at)`を持つnon-content receipt (`.kio/gc/shallowed/<commit64>`) をtree破棄より先に耐久化する新規則を追加する (fsckはreceiptが説明するtree欠落を正常(shallow)として扱う)。GC未実行の理由を旧「auto snapshotがまだ無いため」から「定期auto snapshot・retention減衰がまだ無いため (取り込み完了時のauto snapshotはMVPに存在する)」に訂正する。`repaired` commit typeに`[gc.derived_retention]`に従うretentionを新設し、branchごとに最新keep_*_per_branch個のtreeを保持し超過分をshallow化する (ref tip除外、tiered retention(auto)とは別系統)。HEAD・branch・tagが指すcommitのtreeはretention満了でもshallow化対象にせず (ref tip除外)、物理削除の直前にもref tip非該当と「非shallow commitからの参照ゼロ」を同一exclusive critical sectionで再検証する。GC sweepは最初のtree物理削除に先立ちindex_generationを新規採番・耐久化し、sweep完了時にも再採番する (sweep前発行cursorと sweep中発行cursorはいずれもgeneration不一致として拒否される)。sweep実行中 (in_progressマーカー存在) は新規cursorを発行しない。GCが削除してよいtree objectの条件に「同一tree hashを非shallowのcommitが参照している場合は削除しない」を追加する。SQLite index/FTSキャッシュ削除の例外として`target_type='query_cache'`のembeddings行は復元されず破棄され (J領域 U101 と対応)、index削除後再構築完了までは`KIO-E-INDEX-REBUILDING-001`を返す。GCが削除してはならないものにtoollock object (参照するcommit objectが存在する限り削除不可) とmanifest object (参照するtree objectが存在する限り削除不可、削除の唯一の経路はpurge) を追加する。`kio gc`のモード列挙を「on-demand/shallow/full」から「on-demand/shallow/prune-unreachable」に変更する。

- **実装状態: [未実装]** Gc(UnsupportedArgs)は明示的に"Phase 4+ command placeholder"とコメントされる (main.rs:173)。shallowed/gc.derived_retention/index_generation/prune-unreachable、0件。項目自身がPhase 4要件・MVP対象外と明記しており想定通り。
### U130 kio view の構文訂正と unit 完成状態判定基準 [P1]
- 出典: gap-05 G31, G68
- spec §: 05-runtime.md §2.2, §4.2
- 種別: 挙動
- 統合要約: shallow後commitの表示コマンド例を`kio view <commit>`から`kio view <path> --at <commit>`に訂正し、文法の正本は06-cli-spec.md §1、commit metadataの表示は`kio log`/`kio inspect`系が担うと明記する。unitの完成状態・列挙は、当該commitのtree entry`normalize.manifest_hash`が指すmanifest object (J領域 U109) で確定する新規則を追加する (same-gen partial retryで作業コピーmanifest.jsonが進んでいても、表示はcommit時点のmanifestに従う)。

- **実装状態: [未実装]** 依存先のmanifest_hash機構 (U109) 自体が存在しないため、「tree entryのnormalize.manifest_hashが指すmanifest objectでunit完成状態を確定する」という新規則は成立しえない。kio view構文自体の現状は未確認。
### U131 排他lockインフラの対象コマンド拡大と複合lock順序の変更 [P0]
- 出典: gap-05 G69, G71, G74
- spec §: 05-runtime.md §5, §6
- 種別: 挙動
- 統合要約: `.kio/.lock`を要する書き込み系コマンド一覧に`kio batch resume`/`kio batch retry`/`kio batch abandon`/`kio reindex`/`kio adapter revoke`を追加する (batch系とreindexは外部副作用とbatch_requestsの状態遷移を伴うためlock必須)。`.kio/.lock`を取得しない読み取り系コマンド一覧に`open`を追加し、例外として`kio search`はvector|hybridのpage 1に限りcost-ledger.sqliteのdevice行への相1/stale回収・剪定の書込を行うがこれも`.kio/.lock`の対象外 (直列化はcost-ledger側の`BEGIN IMMEDIATE` Txが担う) と新規定する。複合lock順序を「scope store→reservation/cost ledger→device observability→scope access」から「scope store→cost-ledger.sqlite (Tx) →device observability→scope access」に変更する (逆順取得禁止は維持)。読取系が対象path/query/raw_hashを含む行をscope由来logへappendする場合、当該appendはscrub lock保持のままpurge journal/epoch 3点検査の最終検査と同一critical sectionで行う新規則も追加する (拒否時の記録には対象path/query/raw_hashを含めない)。

- **実装状態: [部分]** lock_store()は既にindex(653)/repair(850)/reindex(3559)/batch(7005)全てで取得済み — batch resume/retry/reindexへのlock拡大は実質達成済み。adapter revoke自体が無い(U80)ため対象外。複合lock順序・openのcost-ledger Tx例外の詳細は未検証。
### U132 scope-registry再構築の入力範囲明確化と XDG_DATA_HOME 展開バグ修正 [P0]
- 出典: gap-05 G72, G73
- spec §: 05-runtime.md §6
- 種別: 挙動 / schema (バグ修正)
- 統合要約: scope-registry.sqlite破損時の再構築は「ユーザーが知る探索root」を入力とする (registry喪失後は`.kio`所在一覧も失われるため各rootでの`kio index`再実行が再登録を兼ねる。全ディスク走査はしない) と明記する。device logsのscrub lock pathを`$XDG_DATA_HOME/kio/logs/scrub.lock` (環境変数未設定時に不正パスとなるバグ) から`${XDG_DATA_HOME:-$HOME/.local/share}/kio/logs/scrub.lock` (XDG仕様準拠のデフォルト値付き) に修正する。

- **実装状態: [部分]** XDG_DATA_HOME展開は元々data_home() (main.rs:13387-13398) 経由でPathBuf joinしており文字列バグ自体が存在しない (scrub.lock関連もdevice_root.join()、purge.rs:1022-1078) — 「バグ修正」は事実上該当なし。registryの「既知root入力での再構築 (全ディスク走査なし)」は--registry-prune等の機能自体が0件のため未実装。
### U133 VCS リポジトリ配下の既定検索除外 (index_vcs_repos opt-in) [P0]
- 出典: gap-10-03 G17, gap-rest G6, gap-07-06 G39, sol G3
- spec §: 03-data-model.md §3, 10-operations.md §4, 01-positioning.md §8, 06-cli-spec.md 本文 (kio init)
- 種別: 新規機能 (破壊的変更)
- 統合要約: `kio index`はVCSリポジトリroot (`.git`等を持つフォルダ) とその配下に既定では子`.kio`を生成しない (skip+status表示) という新規則を追加する。旧文言は「リポジトリ群を含む親フォルダに`.kio`で横断検索」とだけ書いており親スコープがgitリポジトリ内部まで検索するように読めたが、新文言は「リポジトリ内のコードは既定では検索対象外」と明記する。`[scope] index_vcs_repos = true`の明示opt-inで対象化できる。本既定導入以前に生成済みの既存子`.kio`はgrandfatheredとして引き続き有効なscopeのまま残る (skipは新規生成の判断のみに適用)。

- **実装状態: [未実装]** index_vcs_repos/.git検出/VCSリポジトリskip、crates全域で0件。
### U134 kio import --as-new-scope の fork 機構全体 [P0]
- 出典: gap-07-06 G34, sol G64
- spec §: 06-cli-spec.md §10, 03-data-model.md §2
- 種別: 新規機能
- 統合要約: `kio import`に`--as-new-scope`を新設する。bundleのscope_idがregistryにlive登録済みなら通常はKIO-E-REGISTRY-DUP-001で拒否されるが、複製取り込みには`--as-new-scope`で新scope_idを採番するfork操作が必要になる。forkは旧scopeのapprovals[]・scan_approval・allow_networkを引き継がず、`.kio/logs/`も継承しない。atomic postconditionとしてscope.json新規生成・config reset・旧root_path除去をprivate directoryでsanitizeした上でatomic publishし、bundleはtruth一式+機微metadataを含む形式とする。

- **実装状態: [未実装]** "kio import"・--as-new-scope、0件 (Commands enumに無し、Phase 4+相当)。
### U135 .kioz bundle の機微 metadata 含有警告 [P1]
- 出典: gap-07-06 G56
- spec §: 06-cli-spec.md §10
- 種別: 挙動
- 統合要約: `.kioz`バンドルの性質説明を「.kio単位で公開可能」から「.kio単位で可搬」に変更し、bundleにはscope.jsonのapprovals[]・logs/の運用記録・登録path等の機微metadataが含まれるため共有は同一信頼境界内を想定し、第三者公開用sanitizeはPhase 4+のexport modeで扱うという安全上の警告を新設する (旧の「公開可能」のまま実装すると機微情報を含むbundleを不用意に第三者公開してしまう)。

- **実装状態: [未実装]** .kioz/bundle/export機構自体が0件 (U134と連動)。警告文以前に機能が存在しない。
### U136 Observability (ログ) schema拡張・rotation・retention_days・purge scrub [P0]
- 出典: gap-07-06 G59, gap-10-03 G67 (retention_days部分), sol G66
- spec §: 05-runtime.md §6, §7, 06-cli-spec.md §13, 07-adapter-spec.md §7, 10-operations.md §7, §12.3, §12.6
- 種別: schema
- 統合要約: scope-localの`.kio/logs/access.jsonl`自体も日次rotation+保持config (正規key`[observability] retention_days`、整数1〜3650、既定30) の対象であることを新規に明記する (旧は`~/.local/share/kio/logs/`側のみが明示対象で、config keyの具体名も不明瞭だった)。ログに残してよいcontextを必須化し、scope由来行にはscope_idを必須fieldとする (非機微message、Adapter consent/4組/submission/usage fields含む、I領域 U92 と対応)。device logsとscope-local access.jsonlの双方に`retention_days`を適用し、purgeのログscrub (E領域 U33) は対象scopeの全保持世代だけをscrubする。

- **実装状態: [部分]** retention_days rotation機構は充実 (scope.rs:1836-1993、device/scope両ログで再利用) だが、config schemaのセクション名は依然"logs"のまま (config.schema.json:101) で"observability"への改称は未適用。
### U137 走査境界の全面確定と system directory パターンの畳み込み [P0]
- 出典: gap-10-03 G16, G18, sol G23 (該当部分)
- spec §: 10-operations.md §4, §1.1
- 種別: 挙動
- 統合要約: 旧spec は「実装前に方針を明示すべき境界」として用語列挙のみ (symlink/hardlink/外部ドライブ/placeholder/権限のないフォルダ/hidden directory/system directory) だったが、新spec は各項目の具体挙動を確定する。symlinkは『lstat基準で検出し、追跡しない』に加え『判定とopenのTOCTOUも閉じる』ため、scope root dirfdからの相対open+O_NOFOLLOW相当+fstat検証 (regular file・同一device/inode) を新規規定する。system directoryはTier A相当のbuilt-in ignoreに新規追加し、OS別の対象パターンをbuilt-in templateに列挙してそのtemplateの版を`effective_ignore_hash`の入力に含める (パターン更新が承認記録の同一性判定に反映される)。

- **実装状態: [部分]** symlink TOCTOU対策 (lstat前後比較+O_NOFOLLOW相当、scope.rs:2610-2621, cas.rs:1779-1816) とeffective_ignore_hash (main.rs:13158) は既存。ただしOS別"system directory"組込みignoreパターン (/proc, /sys, Windows系等) は0件 — 既存Tier Aは秘密情報検知であり別概念。
### U138 エントリコマンド変更 (kio index --approve) と finalize 機構の明記 [P1]
- 出典: gap-rest G1
- spec §: README.md (最低体験ライン), 01-positioning.md §3
- 種別: 挙動
- 統合要約: 最低体験ラインの入口を`kio snapshot`から`kio index --approve`に変更する。`kio index`が取り込み+ベースラインindex構築の入口であり成功時にauto snapshotを自動生成する (明示`kio snapshot`は任意)。`kio open`も引数なしから`kio open <検索結果のpointer>`に変更する。batch/online Adapterの後着成果は`batch resume`/`retry`/`reindex`のfinalizeが実行されるまで検索対象化しない旨も新規に明記する。

- **実装状態: [適合済みの可能性]** `kio index --approve`は既に主要entry point (main.rs IndexArgs.approve、main.rs:674-678で非対話時--preview/--approve/--yesを要求) — 新仕様の記述と一致。
### U139 CAS/Evidence Pointer の恒久到達性に purge/erase 例外を明記 [P1]
- 出典: gap-rest G2
- spec §: README.md (Evidence Pointer 3本柱), 01-positioning.md §4.1
- 種別: 挙動
- 統合要約: 「ファイル移動・削除・上書きでも根拠は死なない」というEvidence Pointer/CASの恒久性の説明に、初めて明示的な例外「ユーザー明示のpurge/eraseを除く」を両ファイルに追記する。

- **実装状態: [適合済みの可能性]** 統合要約自身が「過剰抽出の疑い」と付記する文書注記のみの項目。purge/erase後に到達不能になる挙動はpurge.rs等の実装で既に確認済み — ドキュメント文言追加のみで実装影響なし。
### U140 Phase 4 の auto snapshot 定義変更 (定期auto snapshotに改称) [P1]
- 出典: gap-rest G3
- spec §: README.md §Phase Plan, 01-positioning.md §6
- 種別: 挙動
- 統合要約: 「Phase 4: 自動化/auto snapshot」を「定期auto snapshot」に改称し、取り込み完了時 (`kio index`完了時) のauto snapshotはPhase 4ではなくMVP (05-runtime.md §8.1) である旨を明記する (旧文言ではauto snapshot全般がPhase 4とだけ読めた)。

- **実装状態: [適合済みの可能性]** 同じく文書呼称整理の項目。取り込み完了時auto snapshotは既にMVPコード経路に存在 (main.rs:723 "kio index auto snapshot") — Phase区分の記載場所に関わらず挙動自体は既に一致。
### U141 MVP スコープから構造化 API を除外 (--json のみ) [P1]
- 出典: gap-rest G5, sol G1
- spec §: 01-positioning.md §2, 09-mvp-scope.md §2, §3.1
- 種別: 削除
- 統合要約: 旧「GUIもMVPでは持たない (CLI+構造化APIのみ)」から、「CLI+構造化出力`--json`のみ。外部Agent向けAPIはPhase 5」に変更する。MVPでは外部Agent向けの構造化APIサーフェスを持たず、`--json`フラグ出力のみで足りるとするスコープ縮小。

- **実装状態: [適合済みの可能性]** --json以外の構造化API面 (REST/GraphQL等) は0件 — CLI+--jsonのみが既に実態であり、MVPスコープ縮小後の記述とそのまま一致。
### U142 MVP Step 計画の更新群 (Step2納品範囲・tree hashing rework注記・Step割当表・Step gate厳格化・評価gate) [P1]
- 出典: gap-rest G38, G39, G40, G42, G47, sol G65
- spec §: 09-mvp-scope.md §1.1, §3, §3.1, §3.2, §4.2, §4.3, §5.5
- 種別: 挙動 / schema
- 統合要約: 旧仕様はStep 2で「同梱deterministic Adapterによるベースラインindex (キーなしで検索成立)」としていたが、新仕様はStep 2の納品を「ベースライン抽出 (normalizedまで)」に縮小し、実際に検索が成立するのはStep 3のchunk/FTS/search実装と合わせてからと明記する。tree schema v2/v3 (2026-07-18制定) により、Step 1-2で実装するtree hashingは`manifest_hash`/`chunking_config_hash`/`chunk_set_hash`に対応するreworkが必要という新規の注記を追加し、manifest object保存・`chunk_publications`/`index_metadata`表・config associationの`introduction_commit`列も同じ実装期間 (Step 1-2) の対象に含める。実装割当表に`kio adapter revoke`(Step 2)、`kio repair --registry-prune`(Step 3)、`kio repair --rebuild-db`(Step 3)、`--prune-orphans`(Step 4) を新規追加する。Step着手ゲートの機械的チェックに、期日cellに「〜を除き充足」等のbut書きが残る行はdecided扱いしないという規則を追加し、#5 (検索評価ハーネス) はM3-1のQ_hard一回限り増補完了時に件数とquery set digestを追記して注記を除去するまでStep 3着手条件を満たさない。`--all-history`シナリオ (M3-2) のRecall@10計算を、旧distinct射影`(raw_hash, section)`から新`(raw_hash, section, path_at_commit)`に変更し、リネーム前後を別要素として数える (golden-queries.jsonlのexpected要素formatにも`path_at_commit`フィールドを追加)。

- **実装状態: [部分]** --rebuild-dbは既存 (main.rs:922-972)。--prune-orphans/--registry-prune 0件 (後続Step割当と整合)。path_at_commitはsearch_history.rsで既に広く使用 (Recall@10射影変更の基盤あり)。tree hashing rework (U104) とchunk_publications/index_metadata (U99) は上記の通り未実装であり、実装関連内容は部分的にしか実現していない。
## 特記事項

### 1. 単独検出

以下は出典が単一ファイルのみの項目 (Sonnet領域別抽出5本のうち1本にしか現れず、かつSolにも対応する記述が見当たらないもの)。Sol側にしか無い項目は精査の結果 **0件** — Sol (extract-sol-full.md) が単独で検出した392件相当の内容は、grep範囲の都合等により全てSonnet側5本のいずれかとも重なった (Solは全docsを横断した独立クロスチェックのため、粒度は粗くとも同一機構は概ね捕捉していた)。一方、Sonnet側1本にしか無い項目は各ファイルが担当diffを分担している構造上、当然ながら相当数生じる。裁定者が原文確認する優先対象として以下に列挙する (領域順、Uで参照):

- **A**: U11 (gap-04のみ), U12 (gap-10-03のみ)
- **B**: U15, U17, U18, U20 (いずれもgap-05またはgap-10-03単独)
- **E**: U31, U32, U33, U34, U37, U38, U39, U40, U41, U42, U44, U45, U47
- **F**: (E区分と重複するG39-G47系。上記参照)
- **G**: U50, U51, U58, U60, U62
- **H**: U64, U65, U66, U67, U68, U72, U74, U75, U76, U77
- **I**: U61, U82, U88, U89, U90, U92, U93
- **J**: U98, U112, U113, U117, U118, U120
- **K**: U123, U125, U126, U127, U128
- **L**: U130, U131, U132, U135, U138, U139, U140
- **その他**: U3, U7, U18, U20, U94, U144, U145

合計 **64件**。特に集中しているのは gap-10-03 由来 (10-operations.md §3/§7.5.1 の運用的細部) と gap-05 由来 (05-runtime.md §1.3-1.8 の検索実装細部、§8.1 のsnapshot耐久順序) で、これは両ファイルが他ファイルより行数・件数が多く (gap-10-03: 75件、gap-05: 77件)、より細かい粒度まで抽出した結果とみられる。裁定時は特にU39-U47 (fsck検証対象の拡大) とU64-U77 (検索cursor/MMR/multi-scope実装規則) を優先確認することを推奨する — これらはP0/P1が多く実装順序の起点になりうるため。

### 2. 矛盾

Sonnet (gap-04/05/07-06/10-03/rest) とSol (sol-full) の記述を突合した限り、**同一対象について事実として食い違う記述は検出されなかった (0件)**。差異は全て「粒度 (Solは要約的、Sonnetは引用付きで詳細)」「着眼点 (同じ機構をどの角度から要約するか)」の違いであり、規範内容そのものの対立ではなかった。ただし以下2点は「解釈の重心」が資料間でわずかに異なり、統合時に裁定者の確認を要する:

- **U29 (purgeの保証範囲反転)**: gap-10-03は「10-operations.md §7の記述反転」として挙動変更寄りに記述する一方、gap-rest (02-philosophy.md側) は同じ変更をUI文言の修正という体裁で記述しており、どちらが一次情報かは原文突合が必要。
- **U108 (commit_type検証機構の訂正)**: gap-05は「強制点の変更」(アーキテクチャ変更として)、gap-10-03は「記述訂正」(誤りの修正として) と temperature が異なる書き方をしている。実装への影響は同じ (SQLite commitsテーブルを作らない) だが、旧spec が「誤り」だったのか「意図的変更」だったのかは原文で要確認。

### 3. 過剰抽出の疑い

「機構変更」として計上されているが、内容を見ると文言明確化・記述訂正・参照整理に近いと思われるもの (統合からは除外していない):

- **U21** (erase receipt用途範囲の明示列挙): 実装が変わるというより、既存の暗黙の運用範囲を文書化した可能性がある。
- **U29** (purgeの保証範囲反転): 「snapshot DAGを書き換えない」は旧実装が最初からそうだった可能性があり、旧spec 文言の不正確さを正しただけの可能性がある。
- **U60** (match_methodのMINOR相当分類): 定義上の整理であり、コード変更を要求しない。
- **U90** (embeddings/chunk_vec SQL定義正本移動): 「正本ドキュメントの所在」を移しただけで、DDL自体は04-pipeline.md §4.3に既存。
- **U108** (commit_type検証機構の記述訂正の一部): 上記「矛盾」項2と同じ理由でP1ながら実装差分が無い可能性がある。
- **U122** (成功応答内error_codeは失敗判定に使わないという明確化): 既存の暗黙の前提を明文化した可能性が高い。
- **U125** (fallback_reasonの自由語彙明記): 既存挙動の追認。
- **U126** (KIO-E-CONFIG-SCHEMA-NNN→001確定): プレースホルダの穴埋めであり機構変更ではない。
- **U130** (kio viewコマンド構文の訂正): 誤ったコマンド例の訂正であり、機構変更ではない。
- **U139** (CAS/Evidence Pointerの恒久到達性にpurge/erase例外を明記): ポジショニング文書への注記追加であり、purge/eraseで到達不能になること自体は元々の設計。
- **U140** (Phase4のauto snapshot定義変更、定期auto snapshotへの改称): 呼称整理に近く、MVP実装への直接影響は小さい。

### 4. 統合後件数のサマリ

| 領域 | P0 | P1 | P2 | 計 |
|---|---|---|---|---|
| A. cost-ledger / batch 2相プロトコル | 9 | 3 | 0 | 12 |
| B. tombstone / erase receipt lifecycle | 7 | 1 | 1 | 9 |
| C. open / 一時展開 cache | 2 | 1 | 0 | 3 |
| D. restore | 3 | 0 | 0 | 3 |
| E. purge closure / journal / epoch | 7 | 4 | 0 | 11 |
| F. fsck / repair / prune | 6 | 3 | 1 | 10 |
| G. evidence pointer / verify / retarget | 7 | 7 | 1 | 15 |
| H. 検索 / gate / mode / exit | 8 | 8 | 0 | 16 |
| I. adapter 契約 | 9 | 6 | 3 | 18 |
| J. schema / path / CAS / 正本表 | 22 | 3 | 1 | 26 |
| K. error code / exit / CLI 表示の横断 | 4 | 2 | 2 | 8 |
| L. その他 | 6 | 8 | 0 | 14 |
| **合計** | **90** | **46** | **9** | **145** |

入力生項目 392件 (gap-04: 64 / gap-05: 77 / gap-07-06: 59 / gap-10-03: 75 / gap-rest: 50 / sol-full: 67) を統合項目145件に集約した (平均統合率 約2.7件/統合項目)。単独検出64件・矛盾0件・過剰抽出疑い11件。
