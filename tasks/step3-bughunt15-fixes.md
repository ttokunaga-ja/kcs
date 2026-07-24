# 探索型監査 第15ラウンド (R15) 裁定

7 エンジン構成 (Claude-Opus / Claude-Sonnet-A/B/C/D / GPT-5.5 / GPT-5.3-Codex-Spark)。
焦点 = R14 が開いた 2 脈の掃討: (1) 派生 CAS object の遅延実行 × identity 突合 (R14-2 が開いた脈)、
(2) mock seam が実挙動を隠す型の網羅 (R14-4 が開いた脈)、加えて R14-3 self-heal 非致死化の縁。

結果: **6 major + 2 minor**。3 つの独立多エンジン収束 (R15-1 snapshot orphan = Sonnet-B/C、
R15-2 phantom charge = Sonnet-A/C/Opus、R15-3 registry stale = GPT-5.5/Sonnet-B)。
全 major はオーケストレータが control 付き実機再現 (R15-1〜R15-4, R15-7) または静的立証 (R15-5, R15-6) でクローズ。

「fix が開ける穴」脈が R15 でも的中 (R9-4→R10-4、R11-5→R12-3、R13→R14 に続く 5/6 例目):
R15-1 は R13-4/R14-3 の合流、R15-2 は R11-6 (実行前 charge) と R14-2 (実行前 supersede) の合流、
R15-5 は R11-6 (unit-scoped retry 按分) と R14-4 (incremental pages) の未接続、R15-6 は R14-4 の空 hint 境界。
mock seam が実挙動を隠す型 (R15-5, R15-6) は静的エンジンのみ検出可 = GPT-5.5/Spark 枠の価値を再確認。

---

## R15-1 [major] 空 HEAD + self-heal 延期下で `kio snapshot` が実履歴を orphan root で握り潰し refs を付け替える (silent history loss, exit 0)

**収束**: Claude-Sonnet-B (所見1) + Claude-Sonnet-C (所見1) が独立再現 (seam / 自然 .lock)。Opus は「同 lock で保護」と
問題なし判定したが、**オーケストレータが実機再現で反証** (2 つの acquire は別呼出で間に窓がある = R13 の Opus doc-gap 異見と同型)。

**根拠 (file:line)**:
- `crates/kio-core/src/scope.rs:604-628` `self_heal_head()` — `StoreLock::acquire` が **live concurrent holder** との競合で失敗すると
  `Ok(None)` で延期し HEAD は空のまま (R14-3 の best-effort 化)。コメント 616-617 自身が「a live concurrent holder」を延期理由に挙げている。
- `crates/kio-core/src/scope.rs:618-620` R14-3 コメントが「a writable scope still heals here — before any snapshot advances HEAD —
  so no snapshot can orphan history under a fresh parents=[] root」と明記するが、**この保証は競合下で成立しない**。
- `crates/kio-core/src/scope.rs:350-368` `snapshot_with_type()` — 359 で**自前の** lock を acquire 後、360 の seam / 実ディスク走査を挟んで
  368 で `head_commit_hash()` を**素の再読込**。`self_heal_head()` を再試行せず、`empty_head_recovery_hash` へのフォールバックもない。
- `crates/kio-core/src/scope.rs:582-593` `head_commit_hash()` — 空 HEAD で無条件 `Ok(None)` (fallback なし)。
- `StoreLock::acquire` (scope.rs:1506-1555) は **non-blocking** (live holder が持つと即 `locked`、reclaim は stale PID のみ)。
  よって窓 = holder が self_heal の acquire 時に保持し snapshot_with_type の acquire 前に解放。

**再現 (オーケストレータ, 決定的 seam 版)**: init → snapshot×2 (log 2 commit, C2=HEAD) → `KIO_TEST_HOLD_LOCK_MS=2000 kio snapshot &`
が自 lock 取得後 sleep 中に `: > .kio/HEAD` → holder が空 HEAD を読み `parents:[] status:created` の orphan root 作成。
log は orphan 1 件のみ (C2 消失)、refs/heads/main が orphan を指す、C2 は `inspect` でのみ到達可 (物理残存・通常操作で発見不能)。
Sonnet-C の自然 .lock 版 (live PID を 44-48ms 保持 + padding で走査窓拡大) は seam なしで同一 orphan を再現し、
競合を外すと self_heal が fast path で修復 = competition の有無だけが分岐点 (control)。

**期待 vs 実際**: 期待 (R13-4/R14-3) = writable scope では HEAD 破損はどのタイミングでも修復されてから snapshot が進む。
実際 = self_heal が競合で延期された直後、その競合が晴れて snapshot_with_type の lock が成功すると、空 HEAD を unborn と誤認し
実履歴を orphan 化。crash で空 HEAD になった scope を並行利用しただけで到達 (read-only 権限操作不要)。

**修正方針**: `head_commit_hash()` 自体を、raw HEAD が空のとき副作用なしの `empty_head_recovery_hash(&self.kio_dir)` に
フォールバックさせる (lock 保持中でも安全に呼べ、snapshot orphan と後述 R15-1b の読取り誤報の両方を一箇所で解消)。
併せて `snapshot_with_type` が自 lock 取得後・HEAD 読込前に `self_heal_head()` を再試行してもよい (lock 保持中なので今度は成功)。

### R15-1b [major・R15-1 と同根] 空 HEAD + read-only で純読取りが exit 0 のまま嘘を返す + warn も書けず完全沈黙
**収束**: Claude-Sonnet-B (所見2)。R15-1 と root cause 共通 (`head_commit_hash` の fallback 欠如)。
- `crates/kio-cli/src/main.rs:1602-1605` `search_one_scope()` — `head_commit_hash()` が None なら無条件 `"not_indexed"` 分類。
- 再現: 索引済み scope で `: > .kio/HEAD; chmod -R a-w .kio` → `log` が `{"commits":[]}` exit 0、
  `search` が exit 4 `not_indexed` (実際は索引済み)、`status` が files=new と tasks=done の自己矛盾、
  warn ログ (`KIO-W-STORE-HEAD-HEAL-DEFERRED-001`) も read-only で書けず完全沈黙。R14-3 が守ろうとした read-only アーカイブ用途で
  「動く」が「空/誤データを exit 0」にすり替わる。
- **修正**: R15-1 の `head_commit_hash()` フォールバック一本化で同時解消 (副作用なしの `empty_head_recovery_hash` は read-only でも呼べる)。

---

## R15-2 [major] supersede/陳腐化した online markdownize task が「送信ゼロ」なのに満額 charge され、二重課金 + budget cap 枯渇で正規タスクを誤停止

**収束**: Claude-Sonnet-A + Claude-Sonnet-C (所見2) + Claude-Opus (所見1) の **3 エンジン独立収束**。オーケストレータも control 付き再現。

**根拠 (file:line)**:
- `crates/kio-cli/src/main.rs:5363-5368` `execute_pending_markdownize_tasks` — `file_size` に**現在ディスクサイズ**を読む (enqueue 時ではない)。
- `crates/kio-cli/src/main.rs:5374` `prorated_markdownize_cost(...)` → `5387` `charge_cost_ledger_under_lock(...)` で
  **実行の前に** cost-ledger に charge を確定 (F8 の reserve-before-send、失敗しても戻さない)。
- `crates/kio-cli/src/main.rs:5423` `execute_online_markdownize_task(...)` を呼ぶ → その内側 5678-5687 の R14-2 supersede ガード
  (現在 bytes hash ≠ input_hash) が `InvalidInput` (非 retryable) で即 return = **adapter 呼び出しゼロ**。charge は残る。
- `enqueue_online_placeholder_task` (main.rs:8309-8349) の idempotency は `(input_path, input_hash)` 完全一致のみ →
  ファイルが変わると新タスクを作る一方、**旧 (path 一致・hash 不一致) Pending task を supersede しない** → tasks.jsonl に陳腐化タスクが蓄積。
- **R14-2 裁定 (`tasks/step3-bughunt14-fixes.md:100`) が「会計整合: stale task を実行しないので誤課金も消滅」と明記しているが未達** (Opus 指摘)。

**F8 既知裁定との区別**: F8 の「reserve は失敗でも残す = cap-safe」は**送信失敗** (バックエンドで実課金が発生し得る) が対象。
supersede は adapter を 1 度も呼ばない**送信前失敗**で実課金の可能性ゼロ = cap-safety の論拠が当たらない純粋な false positive (Opus)。

**再現 (オーケストレータ, control 付き)**: v1(132B/500,035B) index → 再 index せず v2 に編集 → `batch resume`(mock) が
`executed 0 / failed 1` (supersede 正常) なのに cost-ledger に `markdown usd=0.0500035` (=現在サイズ基準)。
Sonnet-C 拡張: 「編集→index→編集→index」で v1/v2 の 2 Pending task → resume で markdown 課金 2 行 (実 OCR は v2 の 1 回のみ)。
`[budget.per_adapter] markdown` を絞ると v1 陳腐化タスクが cap を食い潰し **v2 (正規・未送信) が budget_exceeded で Paused (exit 6)**。
control: 編集 1 回のみ (陳腐化タスクなし) なら executed 1/paused 0 exit 0 = 陳腐化タスクの存在が原因と一意切り分け。

**修正方針**: `execute_pending_markdownize_tasks` のループで `charge_cost_ledger_under_lock` の**前**に
「現在 bytes hash == task.input_hash」等の network-free 事前条件 (R9-2 text-native 拒否・prepare 失敗・空 prepared_units も含む)
を検査し、不一致なら charge せず直接 `Failed(invalid_input)` へ遷移し continue。あわせて `enqueue_online_placeholder_task` で
同一 `input_path` の旧 input_hash Pending/Paused task を supersede すれば陳腐化タスクの蓄積自体を防げる。

---

## R15-3 [major] `.kio` 削除→同一パス再 init で scope registry が旧 scope_id 行を退役させず、multi-scope search が重複返却 + 旧 scope_id 側 evidence_uri が解決不能 (dead pointer)

**収束**: GPT-5.5 (#1) + Claude-Sonnet-B (所見3) の **2 エンジン独立収束**。オーケストレータも control 付き再現。

**根拠 (file:line)**:
- `crates/kio-index/src/registry.rs:73-81` — `PRIMARY KEY (scope_id, kio_path)`。ファイル全体に `DELETE` 文なし。
- `crates/kio-index/src/registry.rs:90-111` `upsert()` — `ON CONFLICT (scope_id, kio_path) DO UPDATE`。新 scope_id は複合キー不一致で旧行が永久残置。
- `crates/kio-cli/src/main.rs:3528-3534` `registry_entry_target()` — `entry.scope_id` を**検証なしで** `ScopeTarget` 化。
- `crates/kio-cli/src/main.rs:3486-3497` `registry_all_targets()` — `participates_in_global_search(kio_dir)` はチェックするが
  scope_id の実 `.kio` 一致は未検証。
- 対照: Evidence 解決側 `resolve_scope_id_in_registry` (main.rs:4293/4313) は実 `.kio` を open して scope_id 一致を検証する**非対称**。

**再現 (オーケストレータ, control 付き)**: `init && index --yes` → scope A、`rm -rf .kio && init && index --yes` → scope B。
registry に (A,path) (B,path) 両方 indexed=1。`search --all-scopes` が**同一 1 文書に 2 件** (stale A + current B)。
stale-A の evidence_uri を `kio view` → **`KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001` (dead pointer)**、current-B は本文を返す (control 健全)。

**期待 vs 実際**: registry はコード自身のコメント通り「検索キャッシュに過ぎず失っても各 .kio 再走査で回復可能」であるべき (docs/03:179)。
削除+再 init は普通の作り直し操作。実際は再 init だけで search 結果が恒久重複し、片方は "evidence-grounded" の中核保証を破る解決不能 URI。

**修正方針**: `register_scope`/`upsert` 実行前に `DELETE FROM scopes WHERE kio_path = ?1 AND scope_id != ?2` で同一パスの旧 scope_id 行を退役。
併せて `registry_all_targets`/`registry_entry_target` で `scope_target(&entry.root_path).scope_id == entry.scope_id` を検証し不一致行を除外
(検索列挙と Evidence 解決の非対称を解消する二重防御)。

---

## R15-4 [major] HEAD commit の tree object 欠落 (shallow 相当) で `status`/`index`/`snapshot`/`reindex`/`repair --rebuild-db` が全滅・回復コマンドゼロ

**収束**: Claude-Sonnet-D (所見1)。オーケストレータが control 付き再現。
**Opus 異見あり** (「genuine corruption への loud fail、gc 未実装で通常到達不能」): severity は下記の限定核で major と裁定。

**根拠 (file:line)**:
- `crates/kio-core/src/scope.rs:657-664` `head_tree()` — `read_tree(&commit.tree)` の Err を無条件 `?`/`transpose()` 伝播 (fallback なし)。
- `crates/kio-core/src/scope.rs:264-269` `status()` / `369-379` `snapshot_with_type` (`prior_tree` + `stats_against_head`) /
  `crates/kio-cli/src/main.rs:2602` `run_reindex` — いずれも同型の無条件 `read_tree`。
- 対照: `crates/kio-cli/src/main.rs:2041-2044` `ensure_snapshot_tree_entries` は同じ `KIO-E-STORE-NOT-FOUND-001` を
  `Err(error) if error.error_code() == "KIO-E-STORE-NOT-FOUND-001" => return Ok(false)` で正しく吸収 = 吸収パターンは既存だが未適用。
- 契約: `docs/05-runtime.md:333/340-345` は shallow (tree 破棄・commit 残す) を設計状態とし、失敗すべき操作を
  restore / 2-commit diff / --at / cursor 再計算に**限定列挙** (status/index/snapshot/repair は含まれない)。`view` は "shallow: tree discarded" 表示すべき。
- `kio repair --verify-objects` は `KIO-E-CONFIG-NOT-IMPLEMENTED-001` で未実装 = CLI 経由の回復手段ゼロ。

**再現 (オーケストレータ, control 付き)**: index 後に HEAD commit の tree object 1 個を削除 →
`status`/`index --yes`/`repair --rebuild-db` が全て `KIO-E-STORE-NOT-FOUND-001` (context.hash = 削除した tree の hash で原因一意)。
`log`/`search` は健全 (control: commit 一覧 / sqlite cache 経由)。`repair --verify-objects` は NOT-IMPLEMENTED。

**限定核 (severity 根拠)**: (a) `status` は純読取りなのに生 STORE-NOT-FOUND で死ぬ (R14-3 の read 耐性原則違反)、
(b) 唯一実装済みの回復コマンド `repair --rebuild-db` が「回復すべき破損そのもの」で死ぬ + `repair --verify-objects` 未実装 = 回復不能。
現状は corruption/manual 削除経由のみ到達 (GC shallow は Phase 4+) だが、上記 2 点は corruption robustness の実害。R13-4 (空 HEAD orphan) の先例に連なる。

**修正方針**: `head_tree()`/`stats_against_head()` と `run_reindex` (main.rs:2602) の `read_tree` を
`ensure_snapshot_tree_entries` と同じ `KIO-E-STORE-NOT-FOUND-001` 捕捉パターンで shallow 扱いに倒す。
最低限、`status` (純読) は tree 由来フィールドを省略して exit 0、`index`/`snapshot`/`reindex` は生 STORE-NOT-FOUND ではなく
`KIO-E-COMMIT-SHALLOW-001` 相当の明確なエラー + 回復案内へ差し替える。

---

## R15-5 [major] unit-scoped retry (Partial task 再送) が実クライアントで全文送信・全ページ課金する一方、cost-ledger は失敗サブセット按分 → 実支出 > 予約で budget cap を silent bypass。mock が隠蔽 (R14-4 の retry 版)

**収束**: GPT-5.3-Codex-Spark (検証2a)。静的立証 (mock seam では原理的に見えない = 静的エンジンのみ検出可)。

**根拠 (file:line)**:
- `crates/kio-cli/src/main.rs:5713-5716` コメント「re-OCR + re-bill just the failed subset, **not the whole document**」と明言。
- `crates/kio-cli/src/main.rs:5739-5760` unit-scoped retry は `request_units` に失敗ユニットのみを渡すが `mode: AdapterMarkdownizeMode::Full` で呼ぶ。
- `crates/kio-adapter/src/mistral_ocr.rs:308-311` `request_pages()` は **`mode == Incremental` のときだけ** hint からページを絞り、
  それ以外 (Full) は `None` を返す → `ocr_request_body` (335-350) が "pages" キーを省略 → 実 Mistral は**全文書 OCR・全ページ課金**。
- `crates/kio-cli/src/main.rs:5629-5638` `prorated_markdownize_cost` は `full × (failed/total)` を予約 (コメント 5372-5373 が
  「1-page retry of a 500-page PDF re-billed all 500 pages」を按分で防ぐと明言)。
- mock (`MockStandardOnlineMarkdownizeClient`, catalog.rs:186〜) は `prepared_unit_hints` からページ合成 → 失敗ユニットのみに見える = **mock seam が隠蔽**。

**期待 vs 実際**: 期待 = retry は失敗サブセットのみ再送・按分課金 (コメントと proration の設計意図)。
実際 = 実クライアントは Full 送信で全文課金。ローカル ledger は按分予約のみ → 実支出が予約の `total/failed` 倍 (500ページ中1ページで 500倍)、
device budget cap を silent bypass (F8 予約が過少)。R11-6 (retry 按分) と R14-4 (incremental pages) の**交差点が未接続**。

**修正方針**: unit-scoped retry (`retry_units.is_some()`) 時に失敗ユニットの 0-based order を `pages` に載せて送る
(R14-4 の pages 機構を retry 経路にも適用)。実 API 課金削減の実測はユーザー gate (R14-4 と同様)、コード fix は
「実送信範囲を按分課金・コメントの約束と一致させる」ことで definite。

---

## R15-6 [major] incremental Markdownize が「変更 0・追加 0 unit」でも発動し、0 ページ要求のまま全文書を送信 (R14-4 の空 hint 境界・mock 隠蔽)

**収束**: Claude-Sonnet-D (所見2)。静的立証 + KIO 側決定木の mock 実証。

**根拠 (file:line)**:
- `crates/kio-pipeline/src/markdownize.rs:242-251` `choose_markdownize_mode` — `change_rate >= threshold` のみ Full に落とす。
  `change_rate == 0.0` (全 unit unchanged) は素通りして `Incremental` を返す (既定 threshold 0.30)。
- `crates/kio-cli/src/main.rs:5933-5964` `try_online_incremental_markdownize` — `requested` = changed ∪ added を
  `is_empty()` ガードなしで `run_standard_online_markdownize(mode: Incremental, prepared_unit_hints: [], ...)` に渡す。
- `crates/kio-adapter/src/mistral_ocr.rs:308-321` `request_pages` — Incremental + 空 hint で `Some(vec![])` (None にならない)。
- `crates/kio-adapter/src/mistral_ocr.rs:335-350` `ocr_request_body` — `pages: []` を挿入するが `document_payload` (287-301) は
  `std::fs::read` した**全文書バイト**を無条件 base64 埋め込み → 「0 ページ処理」と言いつつ全文書アップロード。
- 契約: `docs/04-pipeline.md:236-237` 「fingerprint_exact で unchanged な unit は Adapter に渡さない」。全 unit unchanged なら通信不要のはず。

**再現 (Sonnet-D, mock)**: v2 PDF (先頭コメントのみ変更・ページ本文 byte 不変) → `mode:"incremental", changed_unit_keys:[], status:"done"`
= KIO 側決定木がこの分岐へ確実に到達。既存 R14-4 テスト (`r14_4_incremental_scopes_pages_to_changed_units`) は非空 hint のみ検証 = 空 hint 境界未網羅。

**期待 vs 実際**: 期待 = 変化率 0 なら 100% 再利用で adapter 呼び出しゼロ。実際 = incremental 発動 + 実クライアントで全文アップロード
(metadata-only 変更 = PDF 再保存等の現実シナリオで発動)。空 `pages` を実 API が拒否すれば task 恒久再失敗ループの恐れも (未検証)。

**修正方針**: `try_online_incremental_markdownize` で `requested.is_empty()` の場合は adapter を一切呼ばず、`mapping.unchanged` を
全件 `reused_from` として直接 done な `OnlineExecutionOutcome` を返す (0 ページ送信自体を回避)。空 hint 境界の回帰テスト追加。

---

## R15-7 [minor] 削除/再チャンク済み chunk の embedding task が永久 Pending で `index_status`/`status.tasks` を汚染

**収束**: GPT-5.5 (#2)。オーケストレータ再現。
- `crates/kio-cli/src/main.rs:6844` `reconcile_committed_embedding_tasks` (コメント 6868) が stale/deleted chunk の task を意図放置。
- `crates/kio-cli/src/main.rs:2238/2255` `compute_index_status` が liveness 未確認で Pending/Running を計上。
- 再現: offline index (embedding mock) で Pending embedding task 生成 → 元ファイル削除 + 再 index → 削除 chunk の
  `embedding:sha256:...` task が pending のまま tasks.jsonl / status.tasks に残存。非 live なので駆動・再課金はされない (observability のみ)。
- **修正**: `reconcile_committed_embedding_tasks` で `!live_ids.contains(chunk_id)` の Pending/Running embedding task を
  終端状態 (Superseded 相当 / 非 retryable Failed(invalid_input)) へ、または `compute_index_status` で live chunk 以外を集計対象外に。

---

## R15-8 [minor] offline index 経路が scan 時 raw_hash と正規化再読込を突合せず (R14-2 が online で閉じた identity 破壊の offline 側・窓は狭い)

**収束**: Claude-Opus (所見2)。file:line 立証のみ (lock 窓内の外部編集タイミング再現は非現実的 = 未再現)。
- `crates/kio-cli/src/main.rs:7495-7535` offline 正規化ループ — `bytes = fs::read` (7496) で現在バイトを読むが、
  `raw_hash = candidate.raw_hash.unwrap_or_else(...)` (7498-7501) で**scan 時**の raw_hash を優先採用し現在バイトと一致検証しない。
  normalized instance は scan hash 下に persist、snapshot は `build_working_tree_with_normalize` で再読込し tree entry の raw_hash を
  現在バイトから計算 → scan とこれら再読込の間に外部編集があると tree entry と normalized instance の identity が乖離。
- R14-2 は online (別コマンド間・大きな窓) の同型を hash 再検証で閉じたが offline は未検証。窓は単一 `kio index` (store lock 保持) 内 +
  外部編集が必要で狭く、次の clean index で自己修復 → minor。
- **修正**: 7498 の後に `if candidate.raw_hash.is_some() && hash_bytes(&bytes) != raw_hash { skip/Full 再スキャン }` を追加し online (R14-2) と対称化。

---

## 却下・据え置き

- **Spark 検証1 (a)(b)(c) 全て「該当なし」**: R14-2 の execute_online_markdownize_task 入口 hash 検証で遅延経路が保護済みを確認 (健全性確認着地)。
  embedding task 再実行 (`live_chunks_without_embedding` が HEAD の DB row から都度再導出・content-addressed)、reindex/repair の
  normalize 世代コピー (committed CAS を辿るのみ・live file 再読込なし) も stale-identity 不成立を複数エンジンが確認 (R15 焦点1 の健全性確認)。
- **Spark 検証2(c) / Gemini live HTTP mock 依存**: decision #28 で既知の意図的スコープ (Gemini live HTTP は hermetic テスト非exercise・
  text-only MVP)。mock/実クライアント乖離は Mistral (R15-5/R15-6) に限定、Gemini adapter には R14-4 型乖離なし (複数エンジン確認)。
- **Opus の snapshot orphan「問題なし」判定**: 反証済み (R15-1、実機再現)。エンジンの不採択判断も裁定対象 (R13 の Opus doc-gap 型)。
- **query embedding が budget 非計測** (Sonnet-A): main.rs:6224-6226 で "not metered in the MVP (negligible)" と明示裁定済み = 既知トレードオフ。
- **未来日付 mtime のローテ無効化・二重 heal・DAG cycle 等**: 複数エンジンが健全確認 (R14 と同じく自己修正機構・content-addressing で不成立)。
- **tasks.jsonl done 蓄積 / cost-ledger 月跨ぎ / open cache eviction の無限成長**: R13 で Step 4 gc 設計送りと裁定済み (据え置き継続)。
