# 探索型監査 第 11 ラウンド (R11) — 裁定とフィックス指示

- 実施日: 2026-07-06、HEAD b7a4638 (352 テスト green) 起点
- エンジン: Claude-Opus / Claude-Sonnet (フルスコープ実機) + GPT-5.5 (静的読解) +
  GPT-5.3-Codex-Spark (範囲限定: SQL/バックエンド規模境界 + task 状態機械の遷移・retry/課金会計)
- 裁定: **採択 7 major + 4 minor (critical 0)**。却下/降格 3 (下記)。全採択項目は
  オーケストレータが実機再現 or file:line で独立検証済み
- 今回の鉱脈: **(a) Agent/JSON 契約の正面監査が 10 ラウンドの死角だった** (R11-1/2/3/8/9 の 5 件が
  一点集中)、**(b) 規模境界は「ハード上限で墜落」(R10-1 型) だけでなく「非トランザクション/O(N²) の
  アルゴリズム的劣化」の型で残っていた** (R11-4/5、いずれも R10-8/R10-4 の sibling)、
  **(c) R10-4 fix の unit-scope 側の穴** (R11-6)、**(d) R10-2 config-key drift の [search] 版** (R11-7)

---

## R11-1 [major] typed コマンドの clap usage エラーが `--json` 契約を完全 bypass (プレーンテキスト + exit 2)

- エンジン: Claude-Sonnet (critical 主張) → **major に降格採択** (エラー自体は loud で隠蔽なし。
  形式契約違反であり silent 状態変化を伴わないため)
- 根拠 file:line: `crates/kcs-cli/src/main.rs:223` `let cli = Cli::parse();` — clap の `Parser::parse()` は
  エラー時に内部で直接 `process::exit()` するため、`print_error` (JSON 整形) にも
  `command_captured_json_flag` にも到達しない。typed `#[derive(Args)]` 系 (index/batch/diff/tag/
  snapshot/log/inspect 等) がこの経路。手動パース系 (repair/search/open/view/reindex) は正しく JSON
- オーケストレータ再現: `kcs diff --json` → exit 2 / stdout 0 bytes / stderr プレーンテキスト。
  `kcs bogus --json` 同様。対照 `kcs repair --json --bogus-flag` → `{"error_code":"KCS-E-CONFIG-USAGE-001",...}`
- 期待 vs 実際: docs/06 §「すべての CLI は `--json` を持ち、エラーも `{error_code, message, context}` で返る」
  (docs/06-cli-spec.md:148,154)。実際は約半数のコマンドで入力ミスが JSON を一切出さない
- 修正方針: `Cli::parse()` を `try_parse()` に変え、Err 時は生 argv の `--json` 有無で
  JSON envelope (`KCS-E-CONFIG-USAGE-001` 相当) に包んで stderr へ出し、clap の exit code (2) を維持する
  薄いラッパーを main() 冒頭に追加。`--json` 無しは現行プレーンテキスト維持

## R11-2 [major] online enrichment の失敗/pause が exit code・JSON に不可視 — batch 系 exit 3/4/5/6 (docs/04 §5.6) 未実装、index/repair/reindex は ExecOutcome 破棄で常に exit 0 完全成功

- エンジン: **Claude-Sonnet + GPT-5.5 が独立収束** (Sonnet=index/repair/reindex 側 critical 主張・
  GPT-5.5=batch resume/retry 側 major)。→ 一括 **major** で採択 (silent success 偽装 = R9-4 と同 class)
- 根拠 file:line:
  - `crates/kcs-core/src/exit_code.rs:16-18` `AuthError=5` / `BudgetExceeded=6` 定義済みだが
    **全 crate で構築箇所ゼロ** (grep 検証済み)。`__exit_code` 機構の使用は search の 2 箇所 (exit 3) のみ
  - `crates/kcs-cli/src/main.rs:503` `generate_scope_embeddings(&repo, &args)?;` — 戻り値 `ExecOutcome` 破棄。
    同型が run_repair (:586) / run_reindex (:2356)。index の JSON (:507-522) に embedding 系フィールド皆無
  - `crates/kcs-cli/src/main.rs:4546` `ExecOutcome { executed, failed }` — paused カウンタ無し。
    batch resume/retry の JSON にも exit override にも paused/budget 情報無し
  - budget 超過 pause 分岐 (markdownize :4660 付近 / embedding :5240 付近) はカウンタに反映されない
  - `tasks/step2a-contract-tests.md` CT2-TASK-011 / CT2-BUDGET-005 が「Then: exit 6」を仕様化済みだが、
    実装テスト `ct2_budget_005_online_success_records_ledger_and_caps_next_task`
    (step2_p0_contract.rs:1343) は **Then 節を検証しない別内容に流用** (json_success = exit 0 前提)
- オーケストレータ再現:
  - `KCS_TEST_GEMINI_EMBED=auth_error kcs index --online --approve --json` → exit 0、
    `{"status":"indexed","failed_files":0,"paused_tasks":0}`、embedding 系キー無し。
    status では embedding 3 task が failed/auth_error/attempts=1
  - budget cap 0 (per_adapter markdown=0.0) で `batch resume --json` → **exit 0**、
    `{"status":"resumed","tasks_updated":0,...}` なのに task store は pending→**paused/budget_exceeded に変更済み**
    (JSON の tasks_updated:0 は嘘。docs/04 §5.6 は exit 6 を要求)
- 期待 vs 実際: 期待 = docs/04 §5.6 / docs/10 §12.2 の batch exit 規約 (3 一部 failed retryable /
  4 全 failed permanent / 5 auth_error / 6 budget paused) + docs/06 §7 のスクリプト連携
  (`kcs index && kcs search` を明示例示)。実際 = 常に exit 0、失敗発見には別途 status --json が必要
- 修正方針:
  1. `ExecOutcome` に paused (budget) を追加し、budget pause 分岐で加算。auth_error は failed の
     error kind から判定できるよう実行後の task store 状態 (この pass で触った task) を集計
  2. batch resume/retry: 実行後状態から `__exit_code` を設定 — 優先順位 5 (auth_error あり) >
     6 (budget paused あり) > 4 (全 failed permanent) > 3 (一部 failed retryable 残)。JSON に
     `tasks_paused` を追加し、pause への遷移も `tasks_updated` 相当で可視化
  3. index/repair/reindex (--online 系): `generate_scope_embeddings` 等の `ExecOutcome` を保持し、
     JSON に enrichment 結果 (例 `embedding_tasks_failed` / `paused_tasks` への合算) を開示。
     exit は docs/06 §7 の横断規約に従い auth→5 / budget pause→6 を `__exit_code` で返す
     (стdout に完全な結果 JSON を出したまま — search exit 3 と同じ「結果あり非ゼロ exit」パターン。
     ローカル索引自体の成功は JSON status で表現し、docs/05 の「enrichment 失敗は index を fail させない」
     とは「abort しない」の意で整合)
  4. CT2-BUDGET-005 の Then (exit 6) を実際に検証するテストを追加 (batch resume 側)。
     exit 5 / 3 / 4 の回帰テストも各 1 本

## R11-3 [major] 同じ exit 3 で index は「stderr の error envelope + stdout 空」、search は「stdout に結果本体」— partial 失敗の JSON 所在が非互換

- エンジン: Claude-Sonnet
- 根拠 file:line: `crates/kcs-cli/src/main.rs:523-532` (run_index の partial 経路が output 全体を
  `context.output` に包んで Err で返す → print_error → stderr) vs `:1297` / `:3238` (search は
  `__exit_code:3` を刺して Ok で返す → stdout)
- オーケストレータ再現: `KCS_TEST_MARKDOWNIZE_ADAPTER=reject_incremental_and_full kcs index --yes
  --offline --json` → exit 3 / stdout 0 bytes / stderr `KCS-E-INDEX-PARTIAL-001` +
  `context={failed_files, output}`。commit_hash/tree_hash が非公開スキーマ `context.output` の中に埋没
- 期待 vs 実際: 期待 = 同一 exit code なら結果の所在と envelope 有無が横断一貫。実際 = index の
  partial は成果 (commit_hash 等) が stdout から消える
- 修正方針: index の partial 経路を search と同じ「Ok + `__exit_code:3`」方式に統一し、
  `failed_files` / `error_code` を output 自体のフィールドとして stdout に返す (R11-2 の 3. と同時に実装)

## R11-4 [major] `build_sqlite_index_at` (index/reindex/repair 共通) が毎回コーパス全件を非トランザクションで再構築 — 変更ゼロの再 index も履歴全量のフルコスト (R10-8 の sibling)

- エンジン: Claude-Sonnet (実測 40k chunks=23s 線形、SQLite の per-statement autocommit プロファイル一致)
- 根拠 file:line: `crates/kcs-cli/src/main.rs:2804-2853` — read_stored_chunks 全件 index_chunk /
  tree_entries 全件 INSERT / preserved embeddings 全件 write の 3 ループとも transaction 無し。
  対照: R10-8 fix の `insert_snapshot_tree_entries` (:1827-1830) は `unchecked_transaction()` 済み。
  呼出元 rebuild_step3_index → run_index (:500) / run_repair (:586) / run_reindex (:2356) 共通
- オーケストレータ再現 (2000 chunks): index#1 1.09s / index#2 (変更ゼロ) 1.01s / #3 1.20s —
  noop 再 index が初回同コスト
- 期待 vs 実際: 期待 = 差分ゼロの再 index は軽量、規模時も tx バッチで高速。実際 = 常時フルコスト、
  かつ chunks.jsonl が append-only (docs/04:334、time-travel の実体) のため履歴増加とともに恒久増大
- 修正方針: 3 ループを `fts.connection().unchecked_transaction()` で包む (機能等価、回帰は既存
  rebuild 系テストで担保 + rebuild 後の検索結果不変を確認するテスト 1 本)。
  「差分 skip / 真の incremental rebuild」はより大きな設計変更のため今回は対象外
  (MULTI-007 100k-chunk perf fixture = Step 3 後半 の帯域で再訪) — 裁定として明示記録

## R11-5 [major] embedding enrichment の task 状態更新が 32 件バッチ毎に tasks.jsonl 全読み+全書き = O(N²) — 数千 chunk で index --online / batch resume が実用ハング化

- エンジン: Claude-Sonnet (1,500 chunks→13.3s / 4,500→102.6s = 3 倍入力で 7.7 倍)
- 根拠 file:line: `crates/kcs-pipeline/src/task.rs:111` all() / `:171` replace_all() /
  `:236-249` update_matching() が毎回セット実行 = 1 呼び出し O(T)。
  `crates/kcs-cli/src/main.rs:4993` EMBEDDING_BATCH_SIZE=32、`:5177` バッチループ、
  `:5194/:5243/:5249/:5258` complete/pause/fail_embedding_tasks がバッチ毎に update_matching。
  enqueue 済み T≈N のため合計 ≈ (N/32)×O(N) = O(N²/32)
- オーケストレータ再現: 800 chunks→4.7s / 1600→14.7s = 2 倍入力で 3.1 倍 (線形成分込み。
  超過分は 4 倍スケール = 二次項と整合、Sonnet の 3 倍→7.7 倍とも整合)
- 期待 vs 実際: 期待 = task 更新コストは線形。実際 = 二次で、1〜2 万 chunk の初回 embedding が
  数十分〜時間級に劣化
- 修正方針: バッチループ内は結果 (done/failed chunk 集合) をメモリに蓄積し、ループ終了時と
  break (pause) 経路で update_matching を 1 回に集約。クラッシュ時の安全性は §5.5 content ベース
  再利用 (text_hash 一致で API 非呼出・非課金) が担保する — 未記録の完了分は再駆動時に reuse に
  落ちるだけで二重課金しない。この根拠をコードコメントに残し、集約後も pause/fail の
  fallback_reason が失われない回帰テストを追加

## R11-6 [major] Partial online markdownize の retry が unit-scoped でなく毎回「全文書 Full 再送・全額再課金」— `unit_keys` は書くだけの死にフィールド、docs/04 §5.2「retry は失敗 unit のみ」「done unit 保全 (first-instance-wins)」の二重違反 (R10-4 fix の残穴)

- エンジン: Claude-Sonnet
- 既知との切り分け: R10-4 は「無制限再送・attempts 凍結」を修正 (attempts 増分 + max_attempts halt は
  実機で機能確認済み)。missing unit を `RetryErrorKind::NetworkError` 固定にするのは **R10-4 の意図的
  裁定でコメント記録済み** (main.rs:4926-4930) — この部分は既決として不採択。今回の新規は
  **再送スコープと課金スコープ** (R10-4 が触れなかった側)
- 根拠 file:line:
  - `crates/kcs-cli/src/main.rs:4472` `task.unit_keys = Some(retryable)` (reenqueue) / `:6380` (enqueue) の
    **書込 2 箇所のみで、読む箇所が全 crate にゼロ** (grep 検証済み)
  - `:4883` `prepared_unit_hints(&prepare.prepared_units)` — retry でも常に全 unit を送信、
    `:4897` `MarkdownizeMode::Full`
  - `:4892-4895` `normalized_units_from_response(..., None, ...)` — previous=None 固定で
    docs/04 §5.2「既に done の unit は保全し、失敗していた unit の出力のみ採用」を実装しない
  - `:4639-4644` 課金 estimate が毎回 `estimate_online_markdownize_cost(file_size)` (全文書)
- オーケストレータ再現 (3 ページ fake PDF、`KCS_TEST_MISTRAL_OCR=partial`): resume + retry×7 →
  task=partial / attempts=5 / **unit_keys=["page:3"]** (selective retry を装う) だが cost-ledger の
  markdown 行は **6 行全て同額 $0.0000353 (全文書分)**。100 ページ PDF で 1 ページだけ恒久失敗なら
  500 ページ分を無駄に再送・再課金する構図
- 期待 vs 実際: 期待 = retry は失敗 unit のみ送信・課金し、done unit の出力は保全 (Markdown 非決定性
  下で done unit の再生成は fingerprint 変動 → 再 embedding 課金と Evidence churn を招くため)。
  実際 = 全 unit 再送・全額課金・done unit 再生成
- 修正方針:
  1. `execute_online_markdownize_task` で `task.unit_keys` が Some の場合、prepared_unit_hints を
     該当 unit に絞り、直前 done instance を `previous` に渡して first-instance-wins でマージ
     (adapter へは失敗 unit のみ要求)
  2. 課金 estimate を送信対象 unit 数比で按分 (最低 1 unit 分)。ledger 行にはこれまで通り実 estimate
  3. 全要求 unit が応答から欠落した場合は ContractViolation でなく「Partial 継続 + attempts 増分」
     (現行 `units.is_empty() → ContractViolation` は unit-scoped retry では正しくない)
  4. 回帰テスト: partial seam で retry 後の ledger 金額が全文書額より小さいこと、done unit の
     normalized 出力 (generated_at/run_id 以外) が retry を跨いで不変であること

## R11-7 [major] `[search]` config セクション (default_mode / fail_behavior) が schema 有効 + docs 記載なのに完全未配線 — `fail_behavior="error"` 指定でも --hybrid/auto の vector 失敗が exit 0 の silent text fallback (R10-2 config-key drift の [search] 版)

- エンジン: Claude-Opus (実機再現・p0-matrix 既知記録との差分を正直開示)
- 既知との切り分け: `tasks/step3c-p0-matrix.md:252` は HYBRID-008 (fail_behavior 分岐) を「テスト不在
  P1」と記録するが、実態は**分岐そのものが不在** (fail_behavior の出現は main.rs:821 のコメント 1 箇所のみ、
  grep 検証済み) で記録より悪い。`default_mode` はどの既知ファイルにも無い完全新規
- 根拠 file:line: `crates/kcs-core/schemas/config.schema.json:31,35` (schema 定義) /
  `docs/05-runtime.md:21-22,40,126` `docs/06-cli-spec.md:128` (仕様) /
  `crates/kcs-cli/src/main.rs:2857` requested_mode は CLI フラグのみ /
  `:811-828` resolve_search_mode は fallback ハードコード (config 引数なし)
- オーケストレータ再現: config に `[search] default_mode="vector"` `fail_behavior="error"` →
  status exit 0 (受理)、search --json は requested_mode="auto" (無視)、--hybrid exit 0 text fallback
  (error 無視)、--vector exit 1 (ハードコード)
- 期待 vs 実際: 期待 = 受理した config は効く (R10-2 の裁定思想)。実際 = ベクトル検索を要求し
  「失敗なら error」と明示したユーザーが、無警告 exit 0 で字句 text 結果を受け取る
- 修正方針:
  1. parse_search_args で CLI フラグ未指定時に `[search].default_mode` を requested_mode 初期値に採用
  2. resolve_search_mode に fail_behavior を渡し、auto/--hybrid の vector 失敗時に
     error→`KCS-E-SEARCH-VEC-UNAVAIL-001` エラー (既存 --vector 経路と同型) / warn→fallback +
     応答に警告フィールド / fallback→現行維持
  3. 回帰テスト: default_mode=vector が requested_mode に効く / fail_behavior=error で --hybrid が
     非 0 exit / warn で fallback + 警告
  - **裁定記録**: `[search.multi_scope] parallelism / per_scope_timeout_seconds` (docs/05:222,234-235) も
    未配線だが、MULTI-006 として p0-matrix 記録済み + multi_scope module は dead scaffold として削除済み +
    実装は並列実行/クエリ中断の大物のため **今回は据え置き** (MULTI-007 perf 帯域で Step 3 後半に再裁定)。
    「1 つの遅い scope が横断検索を無期限ブロックする」露出は残存する — 既知として明示継続

## R11-8 [minor] `compute_index_status` が retryable な Failed enrichment task を pending に数えず、`ratio<1.0 / pending=0 / not-paused` の行き詰まり表示 (R9-4 の対)

- エンジン: Claude-Opus
- 根拠 file:line: `crates/kcs-cli/src/main.rs:2013` `TaskStatus::Failed => {}` — retryable Failed
  (rate_limit 等、next_retry_at 保持、batch retry で回復可能) が残作業ゲージから消える
- オーケストレータ再現: rate_limit で embedding failed (attempts=1, retry_at set) →
  search index_status = `{enriched_ratio:0.5, pending_enrichment_tasks:0, budget_paused:false}` —
  Agent は batch retry が必要と判断できない
- 修正方針: `TaskStatus::Failed if task_retry_allowed(task) => pending += 1` (非 retryable Failed は
  現行どおり除外 = 恒久ギャップとして ratio にのみ現れる)。回帰テスト 1 本

## R11-9 [minor] `kcs view --json` に `kcs open --json` が持つ `temporary` フィールドが無い

- エンジン: Claude-Sonnet
- 根拠 file:line: `crates/kcs-cli/src/main.rs:2272-2279` (open は `"temporary": resolved.temporary`) vs
  `:2292-2300` (view は同じ resolved を使いながら不掲載)
- 修正方針: run_view の json! に `"temporary": resolved.temporary` を追加 + 既存 view テストに assert 追加

## R11-10 [minor] FTS keyword OR 群に cap が無い (CJK trigram は 64 cap 済み) — 非対称の hardening。「長大 query で fatal abort」という major 主張は実測 3 本で反証

- エンジン: GPT-5.5 (major 主張) + Claude-Sonnet (minor 実測) → **minor に降格して採択**
- 反証記録: Opus = 5 万 OR-term + 3 万字 CJK が exit 0 完走 / オーケストレータ = 2 万 keyword
  (160KB query) exit 0 / Sonnet = 15 万語は ARG_MAX (OS) 側で先に遮断。SQLite FTS5 は現実的規模の
  flat OR に耐え、Fatal 化する入力規模は実在しない
- 残る事実: `main.rs:2175` MAX_TRIGRAMS=64 は trigram のみ、`:2182` keyword_groups は無制限 →
  数万語で検索 1 回数秒の線形コスト
- 修正方針: keyword_groups にも MAX_TRIGRAMS 相当の cap (dedup 後先頭 64) を適用。1 行 + テスト 1 本

## R11-11 [minor] `ensure_snapshot_tree_entries` の存在 probe が `SELECT COUNT(*)` — EXISTS/LIMIT 1 で足りる (Spark 検証1(c))

- エンジン: GPT-5.3-Codex-Spark
- 根拠 file:line: `crates/kcs-cli/src/main.rs:1767-1772` — `existing > 0` 判定のためだけに
  commit の全 tree_entries を数える (PK prefix scan、大 commit で無駄)
- 修正方針: `SELECT EXISTS(SELECT 1 FROM tree_entries WHERE commit_hash=?1)` に変更。機能等価

---

## 却下 / 不採択 (理由つき)

1. **GPT-5.5 #2「FTS MATCH 無制限 keyword で検索全体 fatal abort」(major 主張)** — 実測 3 本
   (Opus 5 万 term / オーケストレータ 2 万 term / Sonnet ARG_MAX 分析) で fatal 不成立。
   cap 非対称のみ R11-10 minor として採択。なお「FTS runtime error → KcsError::schema → 全 scope abort」
   という経路自体は静的には存在する (main.rs:1722→1095) が、probe 通過後の部分テーブル破損という
   非現実的前提が必要 (Opus 健全性確認) — 入力起因で到達する証拠なし
2. **Spark 検証1(c)-1「chunk_vec_count の COUNT(*) が毎クエリ O(N)」** — R10-1 の k サイジングに
   必要な設計 (KNN over-fetch 上限)。MVP 規模 (数千〜数万 chunk) で実害なし。MULTI-007 (100k perf、
   Step 3 後半明示 defer) の帯域で再訪 — 採択せず記録のみ
3. **Sonnet-5 のうち「missing unit の error_kind が NetworkError 固定」** — R10-4 の意図的裁定
   (main.rs:4926-4930 コメントに根拠記録済み: 応答に per-unit エラー情報が無く、健全 adapter は
   unit を返す前提で transient 扱い + max_attempts で bound)。R11-6 の unit-scoped 化で再送単価が
   下がるため据え置き。severity 降格 2 件 (R11-1: critical→major、R11-2: critical→major) は各項に記載

## 健全と確認された領域 (今回の監査価値、再掘り不要の記録)

- R10-1 KNN k cap / IN(?) の k 追随 / vector 容量エラーの per-scope 降格 (Spark + Opus 再確認)
- R10-4 attempts halt / R10-5 persist retryable / reclaim_orphaned_running / budget 二層 min 合成 /
  F3 負値拒否 / F8 reserve-before-send (Spark + Opus)
- cursor scope 交差 / stale registry 再確認 / evidence URI 検証 / tombstone guard (GPT-5.5)
- config/scope.json 破損の Excluded 隔離 (exit 3) / 時刻 UTC 秒精度一貫 / heading slug 衝突は
  chunk_hash identity で無害 / NOT-IMPLEMENTED exit 一貫 / panic ゼロ fuzz (Opus)
- scan 非再帰 + symlink 不追従 (設計どおり) / chunks.jsonl append-only は time-travel の実体で意図的 /
  embedding reuse の incremental 判定は正 / index_status は恒久 Partial を偽装しない (Sonnet)

## フィックス発注条件 (ランブック §4-6 準拠)

- docs/ 変更禁止。各修正ごとに cargo test。回帰テスト必須。commit しない (オーケストレータが実施)
- 完了後: `cargo test --workspace` / `cargo clippy --workspace --all-targets --all-features -- -D warnings` /
  `cargo fmt --check` 全 green
- major (R11-1〜7) はオーケストレータが実機フルサイクル再検証してからコミット
- 実装順推奨: R11-4 (1 行) → R11-9/11 (1 行級) → R11-1 → R11-3 → R11-2 (3 と同時設計) →
  R11-8 → R11-10 → R11-5 → R11-6 (最大)。R11-2/3 は exit code 表面で相互依存のため同一人格で連続実装
