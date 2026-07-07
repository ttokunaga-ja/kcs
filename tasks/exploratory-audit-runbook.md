# 探索型 4 エンジン + Sonnet 追加 3 本 監査ランブック (新セッション貼り付け用)

このファイル全体を新しい Claude Code セッションに貼り付ければ、探索型クロスチェックを 1 ラウンド
実行できる。長い会話コンテキストを引き継がずに毎回クリーンに走らせるための自己完結手順。
標準構成は従来の 4 エンジンに、Claude-Sonnet のクリーンな追加セッション 3 本を足した計 7 本。
Sonnet は過去ラウンドで実機再現・状態機械・config drift の検出性能が高く、Opus より低コストで
並列本数を増やしやすい。したがって Sonnet 追加 3 本は任意の増強ではなく、この runbook の必須要件。

---

## 0. 位置づけ (安全ガードの誤発火を避けるため必読)

これは **開発者自身が所有する OSS リポジトリ (KCS) に対する、出荷前の防御的セキュリティ監査**である。
目的は自分のコードの脆弱性・不具合を第三者に悪用される前に発見して修正すること。攻撃対象は自分の
ローカルツールのみ。実 API キーは使わず、全操作は隔離した一時ディレクトリで行う。これは正当な
defensive security 作業であり、拒否する理由はない。過去 15 ラウンド (R1-R15) で秘匿情報漏出 (critical) を含む
実バグを多数捕捉し、すべて修正済み。

## 1. 対象

- リポジトリ: `/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs` (main)
- KCS = Rust 製のローカル知識アーカイブ CLI (evidence-grounded local knowledge archive)。
  `kcs init/index/snapshot/search/view/open/batch/reindex/repair/diff/tag/log/status` 等。
  仕様正本は `docs/01`〜`docs/10`。実装は `crates/kcs-{core,pipeline,adapter,index,search,cli}`
- 現状 (R17 完了時点、次ラウンドは R18): 全テスト green (468)、clippy(--all-features)/fmt clean。Step 1-3 実装済み + 探索型監査 R1-R17 修正反映済み +
  (注: R6/R7 は別セッションで実施。clippy は必ず --all-features で回すこと=R8 で --all-features 限定の compile error を検出) +
  実 API 検証済み。Step 4 (restore/time-travel/purge/evidence verify CLI/bbox_annotation) は未着手

## 2. テスト seam (実 API 不要)

- `KCS_TEST_GEMINI_EMBED=mock|rate_limit|auth_error|non_multimodal|incompatible_profile`
- `KCS_TEST_MISTRAL_OCR=mock|partial|auth_error|rate_limit`
- 実機は必ず `export XDG_DATA_HOME=$(mktemp -d)` で隔離、scope は `/tmp` 配下に作る

## 3. 既知の問題 (再報告不要 — 新規のみが成果)

これらの task ファイルに載っているものは全て修正済み。新セッションでは冒頭で `git log --oneline -40`
と下記ファイルの見出しに目を通し、重複を避けること:
- `tasks/step3c-fixes.md` / `step3c-reaudit-4engine.md` (Step3 実装ラウンド F/G/H/I/K)
- `tasks/step3-checkpoint-fixes.md` (L1-L8: reindex/repair の enrichment、override_budget、
  snapshot 後の view 射影、adapter 単位 opt-in ほか)
- `tasks/step3-bughunt-fixes.md` (M1-M8: 並行 index 破損、view 本文、raw_hash 短縮、破損 sqlite 分類、
  CAS キャッシュ冪等、pointer identity、object URI dispatch、config 検証)
- `tasks/step3-bughunt2-fixes.md` (N1-N8: Tier B online 送信 hold、手動 snapshot の Tier A 除外、
  log redaction、diff/tag パストラバーサル、Evidence gen 束縛、チャンク O(N²)、--online embedding、短 query)
- `tasks/step3-bughunt3-fixes.md` (O1-O7: cursor の scope 迂回 + 署名、query embedding 送信境界、
  batch lock、PDF char 境界 panic、0 chunk index 固着、短 sha256 panic、cursor scope 曖昧)
- `tasks/step3-bughunt4-fixes.md` (P1-P10: tasks.jsonl input_path の scope 逸脱 → 外部送信、
  .kcs world-readable + CAS 秘匿露出、tools.toml 0600 warn 未実装、redact_logs の message 漏出、
  非アトミック sqlite 再構築 → 並行 search 偽陰性、registry WAL 欠落、approvals 増殖、cursor-key TOCTOU、
  open cache 位置、reindex の HEAD-vs-sqlite 窓)
- `tasks/step3-bughunt5-fixes.md` (Q1-Q6: chunks.jsonl torn 末尾行が index/reindex/repair を恒久ブリック
  [3 エンジン収束・skip だけでは不完全で torn tail の物理 truncate が必要]、prepared/image の非アトミック書込
  + 無検証 serve、online task の Running 恒久固着 [heartbeat_at 未配線]、NUL/UTF-16 が index 成功なのに検索不可、
  先頭 BOM が見出し無効化、tasks.jsonl input_hash 未検証 → slice panic)
- `tasks/step3-bughunt6-fixes.md` (R6-1〜R6-8、別セッション実施: approvals.jsonl の scope_id 未束縛で別 scope/空ファイルの
  opt-in が online 送信を許す[critical]、normalized_units 破損が repair/reindex を止め writer も非アトミック、
  participates_in_global_search=false が registry 未反映、view/open 余剰引数と reindex --at 黙殺、
  inline Evidence Pointer schema_version 未検証、tool-lock future spec_version 黙認、CONFIG-SCHEMA 丸め、非アトミック fs::write)
- `tasks/step3-bughunt7-fixes.md` (R7-1〜R7-5、別セッション実施: Tier B --send-secrets が secrets-approved.jsonl の
  存在だけで成立し candidate secret を online 送信[critical]、multi-scope search の query embedding opt-in が呼出元 scope のみ、
  embedding 失敗が retry policy 未永続化で即時 retry ループ、repair --rebuild-db の unknown flag 黙殺、
  embedding profile 変化後の非自己修復)
- `tasks/step3-bughunt8-fixes.md` (F1-F8: ローカル baseline が cloud budget cap を消費[仕様違反]、NFC/NFD 非対称で
  NFD 内容が NFC クエリで検索不可[4 エンジン収束]、cost-ledger 負値 usd で cap fail-open、tag HEAD/hash で dead ref、
  budget config warn_at_percent/hard_stop 配線、embedding 応答の次元未検証で永久 KNN 除外、cost-ledger check-then-append
  TOCTOU で並行 cap 超過。F6=online markdownize 成果物の HEAD/search 昇格は Step 4 保留)
- `tasks/step3-bughunt9-fixes.md` (R9-1〜R9-8: .kcsignore の NFC/NFD 不一致で除外 silent 失敗→索引/online 送信/検索露出[major]、
  text-native (md/txt/code) に online Mistral OCR task を enqueue・実送信・課金 (routing 違反)[major]、open/view 展開 cache が
  world-readable (dir755/file444)[major]、Partial task が retry/resume/再index 全滅で回復不能かつ index_status が完了偽装[major]、
  gen dir の余剰 entry 1個 (crash 残留 .tmp/.DS_Store) で reindex が STORE-CORRUPT 恒久失敗[major]、NOT-IMPLEMENTED の exit 1/2 不一致、
  batch retry/resume が裏で駆動・失敗させても {0,0}、temp writer 5箇所のエラー経路 .tmp 残留)
- `tasks/step3-bughunt10-fixes.md` (R10-1〜R10-8: ベクトル KNN が unbounded k を sqlite-vec に渡し >4096 chunk scope が
  device 全域 search を誤 CONFIG-SCHEMA で墜落[major・isolation 契約違反]、top-level `ignore` が schema 有効なのに scanner が
  `[scope].ignore` しか読まず silent 無視→秘匿露出[major]、ignore 照合が case-sensitive で APFS 上 case 違いファイル除外失敗[major]、
  Partial markdownize batch retry が恒久失敗 unit を無制限再送・再課金し attempts 凍結 (§5.2 permanent-kind gate 未実装)[major]、
  persist 失敗を非 retryable InvalidInput 誤分類→課金済み成果物喪失・恒久固着[major]、open/view cache が非アトミック書込 + hit 時
  hash 無検証で torn cache を真正 Evidence 提供 (Q2 の cache 版)[major]、index --online --yes の markdownize dead-end[minor]、
  ensure_snapshot_tree_entries の lazy insert 非トランザクション[minor]。却下 5=Spark の log-cycle 到達不能/cross-snapshot-gen 既知/
  raw_hash-path-fold 設計・GPT-5.5 の registry 秒精度 tie 意図的安全)
- `tasks/step3-bughunt11-fixes.md` (R11-1〜R11-11: typed コマンドの clap usage エラーが --json 契約 bypass[major]、
  enrichment 失敗/pause が exit・JSON 不可視 — batch exit 3/4/5/6 (docs/04 §5.6) 未実装・index/repair/reindex の
  ExecOutcome 破棄で auth_error/budget pause も exit 0 完全成功・CT2-BUDGET-005 実装テストが Then(exit 6) を検証しない流用
  [major・Sonnet+GPT-5.5 収束]、index と search で exit 3 の JSON 所在が非互換 (stderr envelope vs stdout 本体)[major]、
  build_sqlite_index_at 非トランザクション全件再構築で noop 再index が初回同コスト (R10-8 sibling)[major]、
  embedding task 更新が 32 件バッチ毎 tasks.jsonl 全読み書き O(N²)[major]、Partial retry が unit_keys を読まず全文書
  Full 再送・全額再課金 + previous=None で first-instance-wins 未実装 (R10-4 fix の unit-scope 側の穴)[major]、
  [search].default_mode/fail_behavior が schema 有効+docs 記載で完全未配線 — fail_behavior=error が silent text fallback
  (R10-2 の [search] 版)[major]、index_status が retryable Failed を pending 未計上/view --json に temporary 欠落/
  keyword cap 非対称/COUNT(*) 存在 probe[minor]。却下 3=GPT-5.5 の FTS fatal 主張 (実測 3 本で反証・minor 降格)/
  Spark chunk_vec COUNT (R10-1 設計上必要)/NetworkError 固定 (R10-4 既決・コードコメントに rationale 記録済みが決め手)。
  multi_scope parallelism/per_scope_timeout 未配線は MULTI-006 既知として据え置き継続)
- `tasks/step3-bughunt12-fixes.md` (R12-1〜R12-7: [search.rrf]/[search.diversify]/[markdownize.incremental] が
  docs 記載+schema 素通りで完全未配線 — strategy=off も極端値もバイト単位不変[major・4/4 全エンジン収束]、
  [adapter.policy] documented 8 key 中 7 key を schema が拒否 — docs/07 §7 のコピペで scope/device 全体ブリック・
  redact_logs 設定不能 (silent ignore の逆向き新型 drift)[major]、R11-5 集約 write-back の crash 窓 — kill -9 で
  embedding task が Pending 恒久迷子・index/batch resume/retry/repair 全滅・index_status 虚偽 (実 SIGKILL 再現、
  fix=enrichment 駆動部の reconcile)[major]、exit 3/5/6 override 経路+clap エラーが errors.jsonl 素通り・失敗 search
  の metrics 欠落 (auth 失敗が観測ログに痕跡ゼロ)[major]、metrics.jsonl 書込不能で search が成功結果ごと exit 1[minor]、
  XDG_* 空文字/相対パスで cursor-key 秘密鍵含む device 状態が CWD 相対散乱→アーカイブ混入可能 (XDG 仕様違反 7 箇所)[minor]、
  手書きパーサが --flag=value を unknown flag 誤報 + --limit 0 無言クランプ[minor]。却下=gc.*/[snapshot.auto] は
  Phase 4+ 明記、markdownize 素通し object 自体は docs に利用者 key なし)
- `tasks/step3-bughunt13-fixes.md` (R13-1〜R13-6: incremental Markdownize が本番 adapter 両方で到達不能 —
  capability 宣言漏れ + online 経路に mode/previous/hints 構造ごと欠落で改版のたび全ページ再送・全額再課金
  (fix=宣言 + task 伝播 + 変更ページのみ送信 + unchanged 再利用。※cost-ledger は full 予約のまま意図的残置=R14 候補)[major]、
  tools.toml が auth 書式警備のみで documented サーフェス全体 dead — tools.schema.json 不存在・宣言 key 全 crate 不読・
  auth 3 方式不使用 (env:NAME 宣言が silent noop、keychain 実装ゼロ)・model alias 決め打ち・blanket auth walk で
  url="plain:" が device brick (fix=typed loader + auth 解決 + keychain loud + 未宣言 warn)[major・3 エンジン別角度収束]、
  docs/10 §12.6 / 06 §13 の日次ローテ・30 日保持が完全未実装 + [logs] key 不在で docs 通り設定すると device brick
  (fix=logrotate 方式 + retention_days key + prune 非致死)[major・3/4 収束]、空/欠損 HEAD (refs 健全) で snapshot が
  全履歴 silent orphan — 破損と未出生の混同で exit 0 データ喪失 (fix=refs から自己修復 + events 記録)[major]、
  破損 store への再 init が already initialized exit 0 (fix=検証 + repaired 報告)[minor]、R12-6 残穴=HOME 空/未設定/
  相対で device 状態 CWD 散乱 (fix=起動ガード exit 2)[minor]。据え置き=tasks.jsonl done 蓄積/cost-ledger 月跨ぎ/
  quarantine/open cache eviction の無限成長 (docs 契約なし + done_output_for 冪等と衝突リスク → Step 4 gc 設計で裁定))
- `tasks/step3-bughunt14-fixes.md` (R14-1〜R14-6、焦点=R13 fix が開ける新配線の穴が的中: R13-1 incremental online と
  R13-4 self-heal から噴出。previous 正規化インスタンスの unit ファイル 1 個部分破損が Full 降格を迂回し online
  markdownize を恒久ブリック (offline は index 全体巻き添え)・回復コマンドなし=load_previous_instance の非対称エラー
  (unit 読込だけ hard Err) [major・Sonnet 4 本収束]、遅延 online task が現ファイルを enqueue 時の stale input_hash 下に
  保存=content-addressing 不変条件破壊 + 誤課金 + incremental baseline 汚染 (sticky・CAS 冪等で自己修復不能。fix=送信前に
  hash 検証し supersede) [major・Opus]、R13-4 self-heal が read-only + 破損 HEAD で純読み取り (status/log/search/inspect) まで
  KCS-E-STORE-IO-001 恒久失敗=open() で無条件 lock+write (fix=self_heal_head を best-effort 非致死化、writable の orphan 防止は温存) [major・Sonnet 4 本 + Opus]、
  incremental が実 Mistral 経路で差分ページでなく全文送信・全ページ再課金=mock seam が隠蔽・comment も虚偽 (fix=pages パラメータ +
  comment 訂正。実 API 課金削減はユーザー gate) [major・GPT-5.5 静的]、batch resume/retry が errors.jsonl に search 専用/
  未収載コードで誤記録 (fix=batch 自前 error_code) [minor]、incremental の tool_profile_hash 判定が OCR 送信後で pin 変更時に
  無駄送信 (fix=送信前 gate) [minor]。却下=未来日付 mtime のローテ無効化 (mtime は次 append で補正・1 サイクルのみ=Sonnet-A/C/D + Opus 反証)。
  据え置き=incremental cost-ledger 按分は R14-4 の送信修正後に再検討 (full 予約は cap-safe)、embedding model alias は設計上 pin 固定=意図的)
- `tasks/step3-bughunt15-fixes.md` (R15-1〜R15-8、焦点=R14 が開いた 2 脈 (遅延実行×identity / mock seam) + self-heal 非致死化の縁。3 つの独立多エンジン収束:
  空 HEAD + self-heal 延期下で snapshot が実履歴を orphan 化=head_commit_hash が empty_head_recovery_hash に fallback せず・snapshot_with_type が再 heal しない
  (silent history loss exit 0、R14-3 コメントの「orphan しない」保証を実機反証) + 同根で read-only 空 HEAD の read 誤報 [major・Sonnet-B/C 収束]、
  supersede/陳腐化 markdownize task が送信ゼロなのに満額 charge=charge が execute の前 (R11-6 実行前 charge と R14-2 実行前 supersede の合流) →
  二重課金 + cap 枯渇で正規タスク誤 Paused、R14-2 裁定の「誤課金も消滅」を反証 (fix=charge 前に network-free 事前条件 gate + enqueue で stale supersede) [major・Sonnet-A/C/Opus 3収束]、
  .kcs 削除→同一パス再 init で registry 旧 scope_id 行残置 (PK (scope_id,kcs_path)・DELETE 皆無) → search 重複 + 旧側 evidence_uri が dead pointer=
  検索列挙は scope_id 盲信・Evidence 解決は実 .kcs 検証の非対称 (fix=同一 kcs_path 旧 scope_id 退役 + 列挙で scope_id 実 .kcs 一致検証) [major・GPT-5.5/Sonnet-B 収束]、
  HEAD tree object 欠落 (shallow 相当) で status/index/snapshot/reindex/repair 全滅・回復コマンドゼロ=read_tree の無条件 ? 伝播 (docs/05:340 の shallow 契約違反、
  ensure_snapshot_tree_entries に吸収パターンあるのに未適用。fix=status degrade exit 0 + write は KCS-E-COMMIT-SHALLOW-001) [major・Sonnet-D・Opus は「loud fail」異見]、
  unit-scoped retry (Partial 再送) が実クライアントで全文送信 (mode=Full→request_pages None) する一方 ledger は按分 → cap silent bypass=
  R11-6 retry 按分と R14-4 incremental pages の未接続 (fix=restrict_to_hint_pages で失敗ページに絞る)・mock 隠蔽で GPT-5.5/Spark のみ検出 [major・Spark 静的]、
  incremental が「変更0 unit」でも発動し 0 ページ要求のまま全文送信=R14-4 の空 hint 境界・choose_markdownize_mode が change_rate==0 素通り +
  is_empty ガード欠如 (fix=空なら adapter 呼ばず全 unit reused) [major・Sonnet-D 静的+mock]、
  削除/再チャンク済み chunk の embedding task が永久 Pending で index_status 汚染 (fix=reconcile で終端化) [minor]、
  offline index の scan-hash vs 再読込 TOCTOU=R14-2 の offline 対称化 (窓狭・自己修復。fix=不一致は skip) [minor]。
  却下=Spark 検証1 全「該当なし」(R14-2 hash 検証で遅延経路保護済みを健全確認)・Opus の snapshot orphan「問題なし」判定 (実機再現で反証=R13 の Opus doc-gap 型)・
  query embedding 非計測 (MVP 明示裁定)。据え置き継続=tasks.jsonl/cost-ledger/open cache 無限成長 (Step 4 gc))
- `tasks/step3-bughunt16-fixes.md` (R16-1〜R16-7、焦点=store corruption robustness 契約突合 + R15/R12 fix が開けた穴が的中。却下 0:
  commit object 欠落 (tree の 1 行隣) が read/write/repair/Evidence 解決を全面素通り=`read_commit` 無条件 `?` の系統穴 (9 call site) で
  status/log/search/view 全滅・唯一の回復コマンドも道連れ・docs/05:345 の Evidence 保証破れ (fix=is_store_not_found 吸収の系統適用、
  read は degrade [log は truncated 明示・resolve_pointer は best-effort 化で chunk 直接解決]、write は COMMIT-SHALLOW) [major・4/4 Sonnet 収束=史上最強]、
  multi-scope search の store 破損 Fatal 増幅で健全 scope 巻き添え exit 4=05 §1.8 違反・R10-1(a) の未全称化 (fix=store 破損クラスのみ
  Excluded("store_corrupt") 降格、Fatal 全般は fail-fast 維持) [major・Sonnet-A+D 対照]、fresh search が shallow (tree 欠落+cache 行なし) で
  silent 空 exit 0=cursor 経路だけ loud・index_is_rebuilding も 0 行では不発 (fix=SnapshotTreeEntries tri-state + Excluded("snapshot_shallow")、
  cache 行あり shallow は継続=読み degrade) [major・GPT-5.5 静的単独]、repair --rebuild-db が shallow で生 STORE-NOT-FOUND・normalized unit
  1 個欠落で scope 全体 abort=R15-4 が名指しした問題が fix/テスト適用範囲から漏れ (fix=共有 read_head_tree_for_rebuild で index/reindex/repair
  一括 COMMIT-SHALLOW + unit 欠落は skip 続行 + skipped_units/guidance 報告・exit 0) [major・Spark+A+D 収束]、diff の shallow 生エラー
  =docs/05:341「明示」契約乖離 (fix=COMMIT-SHALLOW + side a/b 明示) [minor・Spark+A+D+Opus 4 エンジン]、手書きパーサ 3 本の no-value flag が
  `--force=false --yes=false` を true 化し確認ゲート bypass 実行=R12-7 の split_flag_value が開けた穴 7 例目 (fix=inline 値一律拒否
  KCS-E-CONFIG-USAGE-001) [major・GPT-5.5]、retry 可能失敗 (RateLimit=無制限リトライ) が送信試行ごと満額再予約=phantom charge 無制限累積で
  device 月次 cap 枯渇→他の正規タスク誤 Paused (fix=直前失敗が RateLimit/QuotaExceeded [429 系=課金され得ない] なら charge skip、
  NetworkError は従来通り試行ごと予約=F8/R15-5 の cap-safe 不変条件維持。Opus 提案の「生涯 1 予約」は NetworkError 二重課金の
  cap silent bypass を開けるため不採用) [major・Opus 単独・cap 枯渇→誤 Paused まで control 付き実機]。
  据え置き=registry is_live false 行の無言 drop (excluded 理由未記録・severity 不足)、embedding の triple-fault 残余
  (RateLimit 失敗→retry 送信が server 課金後 commit 前に crash した 1 chunk の有界 under-charge — 塞ぐには per-chunk 永続 marker が必要で
  R11-5 の O(N²) を再導入するため見送り、R17 で再評価))
- `tasks/step3-bughunt17-fixes.md` (R17-1〜R17-7、焦点=R16 fix が開ける穴が本命的中 + Sonnet-A の別脈 3 連発。却下 1/据え置き 1:
  resolve_pointer_for_cli の R16-1 best-effort が捏造 (一度も実在しない) commit hash を「真の shallow」と同一視し N5 gen 束縛 +
  tree 所属チェックを両方迂回=evidence-grounded 中核 (view/open) の identity 検証が commit 偽造だけで無力化 (fix=best-effort を
  「read_commit 成功 + read_tree STORE-NOT-FOUND=真の shallow」に限定・commit 欠落は EVIDENCE-POINTER-INVALID 分離・status/log/search
  degrade は維持) [major・Sonnet-B/C/D+GPT-5.5 の 4 エンジン独立収束・Opus healthy 誤判定を実機反証]、reindex --force の正規化ループが
  単一破損 unit で scope 全体停止=R16-4 の skip-continue が run_reindex に未移植の兄弟穴・repair の guidance が壊れた reindex --force を案内
  (fix=copy_normalized_instance_gen を is_rebuild_skippable_unit_error で捕捉+前世代維持+skipped_units) [major・Sonnet-A]、
  rate_limit で Failed になった online markdownize task の F8 phantom 予約が編集 supersede で reclaim されず per-adapter cap 枯渇→正規タスク
  誤 Paused=R15-2 (Pending/Paused のみ退役) × R16-7 (rate_limit=非課金) の合流点 (fix=supersede に retryable-Failed 追加+非課金種別の予約を
  sibling ledger で reclaim [F3 負値禁止維持]・NetworkError は cap-safe のため据え置き) [major・Opus 単独・control 実機]、store 破損クラス
  (store_corrupt/snapshot_shallow) の全 scope 除外が exit 4 誘導なし=index_missing (exit 1+repair 誘導) と非対称 (fix=既存 SCOPE-ALL-FAILED
  コード維持のまま class 別回復ガイダンスを message+context.recovery に付与・新コードは docs 契約違反で不採用) [minor・Sonnet-A]、
  resolve_commit/tag の read_commit 3 箇所が R16-1/R16-5 の COMMIT-SHALLOW 変換漏れ=hash リテラル/tag/暗黙 HEAD 経由の shallow commit が
  生 STORE-NOT-FOUND (fix=is_store_not_found 捕捉で COMMIT-SHALLOW) [minor・Sonnet-B+Opus 2 収束]、repair/reindex の skipped_units が
  chunks.jsonl 生存 chunk で検索可能な文書まで「要 reindex --force」誤警告 (fix=生存 chunk 突合で searchable/stale 区別) [minor・Sonnet-A]、
  R16-7 embedding charge gate コメントの triple-fault 誤主張=「crash before final write は reuse で安全」は send_embed_batch 完了後に限り
  内部の課金後・commit 前 crash は据え置き triple-fault (fix=コメント訂正のみ・穴を塞ぐ markdownize 対称化は R11-5 の O(N²) 再導入で不採用)
  [minor・GPT-5.5+Opus 2 収束]。却下=Spark の enqueue TOCTOU (cap 読みは task 初期分類のみ・権威は lock 下 charge の再読)。
  据え置き=month がループ前 1 回計算で月跨ぎ pass の翌月分が前月に記帳 (Sonnet-C=minor/Opus=保守側 healthy で割れ・charge 総額は正・
  有界稀=cost-ledger 月次会計マターとして Step 4 送り))
- docs で `Step 4` / `Phase 4+` / `v2+` と明記の未実装

**過去 15 ラウンドの鉱脈は掘り尽くし気味**: R1=並行/異常系の後続経路、R2=秘匿情報漏出/パス検証/資源枯渇、
R3=検索境界の完全性/入力堅牢性/状態の縮退、R4=シリアライズ往復/ファイル permission/資源リーク/Agent 契約、
R5=エンコーディング境界 (NUL/UTF-16・BOM)/派生 CAS object と append-only pointer の crash-atomicity/task ライフサイクル、
R6=未束縛 approval の秘匿送信/破損 JSONL が repair をブリック/引数検証/schema future 互換、
R7=秘匿承認ファイルの存在判定/multi-scope opt-in/embedding retry・profile 互換、
R8=budget/cost-ledger 会計 (ローカル計上・負値・TOCTOU・config 未配線)/NFC-NFD 検索/embedding 応答検証/catalog identity、
R9=ルーティングの意味論 (text-native→OCR)/ignore パターンの NFC-NFD 照合/展開 cache permission/Partial の行き止まり状態/reindex の junk entry 耐性、
R10=規模境界がコア機能を壊す (ベクトル KNN の sqlite-vec k≤4096 上限で >4096 chunk scope が device 全域 search を墜落)/ignore の config-key drift (top-level 無配線) と case 照合/task 状態機械の retry 予算・error kind 会計 (Partial 無制限再送・persist 誤分類)/派生 cache の crash-atomicity (open cache 非アトミック + hit 無検証)、
R11=Agent/JSON 契約の正面監査 (10 ラウンドの死角=clap bypass・exit 5/6 未実装・exit 3 非対称・index_status/temporary 開示、5 件集中)/アルゴリズム的規模劣化 (ハード上限とは別型: 非トランザクション全件再構築・O(N²) task 更新)/R10-4 fix の unit-scope 穴 (全文書再送・全額再課金)/config-key drift の [search] 版、
R12=config-key drift の系統掃討で完結 (silent ignore 型=[search.rrf]/[search.diversify]/[markdownize.incremental] と、
逆向きの schema 拒否ブリック型=[adapter.policy]。config.toml の突合はこれで一巡)/R11-5 fix が開けた crash 窓 (集約 write-back の task 迷子=「fix が開ける穴」の 2 例目)/observability の失敗系素通り (exit override・clap・失敗 search)/XDG 空文字・相対パス、
R13=documented-unimplemented の大物 2 面 (tools.toml 全面未配線・ログローテ/保持) + 要件確定事項の実装未達 (incremental Markdownize 本番不達=正実装が未配線という step3c r1 型の再来) + store 破損処理の非対称 (空 HEAD の silent orphan=部分破損掃引が浮かび上がらせた)、
R14=「fix が開ける穴」脈が R13-1/R13-4 で的中 (R9-4→R10-4、R11-5→R12-3 に続く 4/5 例目) — 4 本の穴が共通して「正常系 (Ok(None)/フォールバック) のすぐ隣で異常系だけ `?` でハード伝播する非対称」(previous unit 部分破損の恒久ブリック・遅延 online task の stale hash 保存・self-heal の read-only 致死化) + mock seam が実挙動を隠す型 (incremental 実 Mistral 全文送信=mock でしか差分に見えない・step3c r1/R13-1 と同型で GPT-5.5 静的のみ検出可)、
R15=「fix が開ける穴」脈が 5/6 例目 (R15-1=R13-4/R14-3 self-heal 合流の snapshot orphan、R15-2=R11-6 実行前 charge と R14-2 実行前 supersede 合流の phantom charge、R15-5=R11-6 retry 按分と R14-4 incremental pages の未接続、R15-6=R14-4 空 hint 境界) — 3 つの独立多エンジン収束 (snapshot orphan=Sonnet-B/C、phantom charge=Sonnet-A/C/Opus、registry stale=GPT-5.5/Sonnet-B) + store 破損 robustness の第 2 面 (R13-4 空 HEAD・R15-4 tree 欠落=HEAD/tree の 2 破損を掘った・docs/05 shallow 契約と実装の非対称) + mock seam 隠蔽型が R15-5/R15-6 で 2 本 (静的エンジンのみ検出=GPT-5.5/Spark 枠が必須)。オーケストレータの「charge/execute 非対称」統合裁定 (supersede=過剰・retry=過少の両方向) と Opus の「問題なし」誤判定を実機で反証。
R16=store corruption robustness 契約突合が本命的中 — R13-4/R15-4 が `read_tree` にだけ吸収を適用し**同じ関数・隣接行の `read_commit` を全箇所素通し**にした構造穴 (4/4 Sonnet 独立収束=史上最強。「fix が適用範囲を絞った際の相似形の隣」も掃く対象という新しい学び) + そこから multi-scope Fatal 増幅 (05 §1.8)・repair の部分回復力ゼロ・diff 契約乖離が芋づる + R12-7 の split_flag_value が開けた確認ゲート bypass (7 例目・GPT-5.5) + fresh search の shallow silent 空 (GPT-5.5 静的単独=silent 型は静的枠) + retry phantom charge 無制限累積 (Opus 単独・cost-ledger 脈の残りが直撃)。
R17=「R16 fix が開ける穴」が本命的中 (定番脈 7 例目) — R16-1 が resolve_pointer_for_cli に適用した best-effort が docs/08 §3.2「commit object 存在=解決前提」を破り、捏造 commit hash で N5 gen 束縛 + tree 所属を両方迂回 (4 エンジン独立収束=R16-1 に次ぐ強収束・Opus の「真正 chunk で問題なし」healthy 誤判定を N5 実機バイパスで反証=R13/R15 の Opus doc-gap 型 3 例目) + Sonnet-A の別脈 (repair/reindex 破損耐性) が R16-4 の skip-continue 未移植 (reindex --force 単一破損で全 scope 停止・repair guidance が壊れた reindex を案内)・store 破損 exit 非対称・skipped_units 誤警告の 3 連発 (R9-1 パターン 6 回目) + cost-ledger phantom charge (R15-2 の Pending/Paused 退役 × R16-7 の rate_limit 非課金の合流点=Failed(rate_limit) 予約が編集で reclaim されず cap 枯渇、Opus 単独 control 実機) + R16-1/R16-5 隣接漏れ (resolve_commit/tag) と R16-7 コメントの triple-fault 誤主張。**「fix が開ける穴」の新しい変種**: R16-1 の best-effort は「適用範囲の絞り漏れ」(R16 の read_commit 素通し) ではなく**「適用範囲の広げ過ぎ」** (commit 欠落を真の shallow と同一視=docs 前提の無断拡張) が穴を開けた=fix の過剰適用も掃く対象。
**新しい鉱脈の方が期待値が高い** (下記ヒント参照)。R17 で「R16 fix の新配線 + repair/reindex 破損耐性 + cost-ledger phantom の残り」は掘って修正済み。
R18 Spark は別焦点へ (§6 は R18 用に書き換え済み: R17 fix が開ける穴の新配線網羅=resolve_pointer の best-effort 分離が真の shallow degrade と commit 欠落拒否の境界で新穴を開けないか・reclaim ledger (cost-ledger-reclaimed.jsonl) の新配線が二重 reclaim/reclaim×charge 並行窓/月跨ぎで穴を開けないか・reindex skip-continue が snapshot/index 整合を壊さないか + cost-ledger 会計の残余=reclaim ledger の effective_spent 整合・month 月跨ぎ据え置きの再評価。いずれも静的読解が効く)。

## 4. 手順 (新セッションの Claude が実行)

1. `git rev-parse --short HEAD` と `cargo test --workspace 2>&1 | grep 'test result'` で現状確認
2. 下記「共有バグハントプロンプト」を自分の scratchpad か `/tmp/bughunt-prompt.md` に書く
   (§0 の防御的セキュリティ位置づけを必ず含める)
3. **4 エンジン + Sonnet 追加 3 本を並列起動** (最低 7 セッション。Opus/Sonnet 群は抽象指示で自由に、
   Spark は範囲限定):
   - Claude-Opus: `Agent` tool、`subagent_type: general-purpose`、`model: opus`、
     run_in_background、プロンプト = 共有プロンプト + 「エンジン識別子 Claude-Opus。cargo/実機/python3 可」
   - Claude-Sonnet-A: 同上 `model: sonnet`、「エンジン識別子 Claude-Sonnet-A。実バイナリを自分の手で叩く」
   - Claude-Sonnet-B (追加 1): 新規 `Agent` invocation / `model: sonnet` / run_in_background。
     プロンプト = 共有プロンプト + 「エンジン識別子 Claude-Sonnet-B。完全に独立したクリーンセッション。
     他 Sonnet の仮説を読まず、自分の再現または file:line だけで立証」
   - Claude-Sonnet-C (追加 2): 新規 `Agent` invocation / `model: sonnet` / run_in_background。
     プロンプト = 共有プロンプト + 「エンジン識別子 Claude-Sonnet-C。完全に独立したクリーンセッション。
     観点は自由、既知重複を避け、実機再現を優先」
   - Claude-Sonnet-D (追加 3): 新規 `Agent` invocation / `model: sonnet` / run_in_background。
     プロンプト = 共有プロンプト + 「エンジン識別子 Claude-Sonnet-D。完全に独立したクリーンセッション。
     静的読解と実機のどちらも可、憶測を書かない」
   - GPT-5.5: `Bash` run_in_background:
     `codex exec -m gpt-5.5 -s read-only -C <repo> "$(cat /tmp/bughunt-prompt.md)\n\nエンジン識別子 GPT-5.5。read-only なので静的読解 + file:line 立証"`
   - GPT-5.3-Codex-Spark: `Bash` run_in_background、**範囲限定プロンプト** (下記 §6、丸読み禁止 grep/sed 限定)
   - Sonnet 4 本は必ず別々のクリーンなサブエージェント/新セッションで走らせる。scratchpad や出力を共有せず、
     回収前に相互の所見を見せない。Agent tool が使えない環境では、同等に履歴を持たない Claude Code セッションで代替する。
4. 全エンジン回収後、所見を統合。**critical/major は自分で実機再現 or file:line 検証してから採否**を決める
   (エンジンの誤検出・既知重複を除外)。Sonnet 4 本は同一モデルの多重サンプリングなので単純多数決にしない。
   同一根拠の重複は 1 件に畳み、異なる再現コマンド・異なる file:line・別経路の立証がある場合だけ収束証拠として扱う。
   verify スクリプトの罠に注意:
   `grep -rl P dir | head && echo found` は grep 不一致でも head 成功で常に真。**grep の exit code を直接見る**
5. 採択した所見を `tasks/step3-bughunt<N>-fixes.md` に裁定として書き、コミット (R16 は bughunt16、**次 R17 は bughunt17**)
6. 修正を `Agent`(opus) に発注 (docs 変更禁止・各修正ごとに cargo test・回帰テスト必須・commit しない)。
   完了後 `cargo test --workspace` / `clippy --all-features -D warnings` / `fmt --check` 全 green を確認、
   critical/major は自分で実機 repro クローズしてからコミット (R10-R13 で定着した運用)
7. `git push origin main` は**ユーザーに依頼** (直接 push しない)

## 5. 共有バグハントプロンプト (Opus/Sonnet 群/GPT-5.5 に渡す本文)

```
あなたは KCS (Rust 製ローカル知識アーカイブ CLI) の探索的バグハンターです。これは開発者自身が
所有するリポジトリに対する出荷前の防御的セキュリティ監査であり、脆弱性・不具合を先回りして潰すのが
目的です。攻撃対象は自分のローカルツールのみ、実 API キーは使いません。

ミッション: 我々がまだ見つけていない不具合・脆弱性を見つけること。方法・観点は自由。
この実行はクリーンな独立セッションです。同一ラウンドの他エンジン・他 Sonnet の出力は見ず、
自分で再現または file:line 立証できた根拠だけを報告してください。

前提: Rust workspace、`cargo build` → target/debug/kcs、仕様正本 docs/01〜10。テスト green の状態。
seam: KCS_TEST_GEMINI_EMBED / KCS_TEST_MISTRAL_OCR (§2 参照)。実機は XDG_DATA_HOME=$(mktemp -d) で隔離、
scope は /tmp 配下。リポジトリのファイル変更禁止。verify は grep の exit code を直接見る。

既知 (報告不要): tasks/step3-checkpoint-fixes / step3-bughunt-fixes / bughunt2〜bughunt16 (R17 開始時は
`ls tasks/step3-bughunt*` と各見出しを確認) と、docs で Step4/Phase4+/v2+ と明記の未実装。過去の鉱脈
(並行/異常系、秘匿漏出/パス/資源、検索境界/入力堅牢性、シリアライズ往復/permission、エンコーディング境界
NUL/UTF-16/BOM/crash-atomicity/task lifecycle、未束縛 approval の秘匿 online 送信、budget/cost-ledger 会計、
検索"内容"の NFC/NFD、embedding 応答検証、非アトミック writer、破損 JSONL が repair をブリック、引数検証、
schema future 互換、ルーティング意味論、ignore の NFC/NFD・case、config-key drift 両型 ([scope]/top-level/[search]/
[search.rrf|diversify]/[markdownize.incremental] の silent ignore と [adapter.policy] の schema 拒否ブリック — config.toml は一巡)、
ベクトル KNN の sqlite-vec 規模上限、task retry 予算・error kind・unit-scope 会計・集約 write-back の crash 窓、
派生 cache の crash-atomicity、Agent/JSON 契約 (clap bypass・exit 5/6・exit 3 対称性・index_status 開示)、
非トランザクション/O(N²) の規模劣化、observability の失敗系素通り (exit override・clap・失敗 search の metrics)、
XDG 空文字/相対、tools.toml 全面配線 (typed loader/auth 解決/model alias/keychain loud=R13-2)、ログ日次ローテ +
retention_days (R13-3)、incremental Markdownize の本番配線 (R13-1)、空 HEAD/再 init の自己修復 (R13-4/5)、
HOME フォールバック検証 (R13-6)、previous instance の unit 部分破損→Full 降格 (R14-1)、遅延 online task の
stale input_hash 検証 (R14-2)、self-heal の read-only 非致死化 (R14-3)、incremental 実 Mistral の pages 送信 (R14-4)、
batch の自前 error_code (R14-5)、incremental profile 判定の送信前 gate (R14-6)、
空 HEAD + self-heal 延期の snapshot orphan と read 誤報 (R15-1/1b、head_commit_hash が empty_head_recovery_hash に fallback)、
supersede/陳腐化 markdownize task の phantom charge (R15-2、charge 前 network-free gate + enqueue stale supersede)、
再 init の registry 旧 scope_id 退役 + 検索列挙の scope_id 検証 (R15-3)、HEAD tree 欠落の shallow degrade/error (R15-4)、
unit-scoped retry の pages 絞り (R15-5、restrict_to_hint_pages)、0-change incremental の adapter 非呼出 (R15-6)、
削除 chunk の embedding task 終端化 (R15-7)、offline scan-hash 突合 (R15-8)、
commit object 欠落の read degrade/write 拒否の系統適用 (R16-1、read_commit の is_store_not_found 吸収・log truncated・
resolve_pointer best-effort)、multi-scope search の store 破損 Fatal→Excluded("store_corrupt") 降格 (R16-2)、
fresh search shallow の tri-state (R16-3、SnapshotTreeEntries + Excluded("snapshot_shallow"))、repair の COMMIT-SHALLOW +
skipped_units 部分回復 (R16-4)、diff の COMMIT-SHALLOW + side 明示 (R16-5)、手書きパーサの inline 値一律拒否 (R16-6)、
retry 再送の error-kind-aware charge gate (R16-7、RateLimit/Quota は skip・NetworkError は従来通り)、
resolve_pointer_for_cli の捏造/欠落 commit 拒否 (R17-1、best-effort を真の shallow に限定・N5 gen 束縛/tree 所属の迂回封鎖・
commit 欠落は EVIDENCE-POINTER-INVALID・status/log/search degrade は維持)、reindex --force 正規化ループの skip-continue
(R17-2、R16-4 の兄弟穴)、rate_limit/quota Failed task の phantom 予約 reclaim (R17-3、sibling ledger cost-ledger-reclaimed.jsonl・
F3 負値禁止維持・NetworkError は据え置き)、store 破損クラス全 scope 除外の回復ガイダンス (R17-4、既存 SCOPE-ALL-FAILED コード維持)、
resolve_commit/tag の COMMIT-SHALLOW 変換 (R17-5)、repair skipped_units の searchable/stale 区別 (R17-6)、
embedding charge gate コメント訂正 (R17-7、triple-fault 据え置き明記)、
tasks.jsonl・cost-ledger・open cache の無限成長は据え置き裁定済み (Step 4 gc 設計マター)) は掘り尽くし気味 —
新しい鉱脈の方が期待値が高い (R18 候補):
  - **R17 fix が開ける穴** (定番脈 8 例目候補): (a) R17-1 resolve_pointer best-effort 分離の境界 — 真の shallow
    (commit 実在・tree GC) の view/open degrade が壊れていないか、status/log/search の R16-1 degrade が resolve_pointer の
    厳格化に巻き込まれて loud 化していないか、EVIDENCE-POINTER-INVALID 分離が tombstone/retarget と衝突しないか、
    (b) R17-3 reclaim ledger (cost-ledger-reclaimed.jsonl) の新配線 — 二重 reclaim・reclaim×charge 並行窓・reserved_month の
    月跨ぎ・effective_spent が負や cap-unsafe にならないか、reserved_usd/reserved_month stamp なし古 task の挙動、
    (c) R17-2 reindex skip-continue が前世代 normalize ref 維持で snapshot/tree_entries/sqlite と整合するか (古 gen chunk の
    検索混入)、merge_reindex_skips の dedup、(d) R17-6 searchable/stale 区別の突合精度
  - **cost-ledger reclaim/会計の残り**: reclaim という新会計軸 (R17-3 が初) の整合 — reclaim ledger 専用 lock か・並行 reclaim の
    二重計上・month 月跨ぎ (R17 据え置き=ループ前 1 回計算) の再評価・baseline 行 (usd 0.0)・embedding 経路の orphan 予約
    (reclaim 非対応=enqueue-time retirement hook なし)
  - **Tier B / approval 周辺の再掃** (R6/R7 以来正面から触っていない脈: R15-3/R16/R17-3 で registry・scope_id・reclaim が
    動いた後の secrets-approved 束縛・approval と再 init の相互作用)
  - multi-scope 並列の縁 (継続: per-scope 降格理由の網羅 — R16-2 store_corrupt / R17-4 回復ガイダンス追加後の一貫性)
  - 時刻/TZ の残り (DST/閏の境界、rotation の日付判定と UTC/local の縁、R17 で浮上した month 月跨ぎの charge/reclaim)
だが直感を優先せよ。

品質バー: 報告する所見は必ず自分で再現 or file:line で立証。憶測不可。既知重複ゼロ。
各所見: [critical|major|minor] / 再現コマンド列 or 根拠 file:line / 期待 vs 実際 / 1 行修正案。
量より質 (確実な 2 件 > 怪しい 8 件)。

出力: ## 所見一覧 (severity 降順) / ## 探索したが問題なしと確認した領域 / ## 総合所感 + エンジン識別子
```

## 6. Spark 用 範囲限定プロンプト (ラウンドごとに焦点を変える)

Spark は context window が小さいので**必ず範囲を絞り、丸読み禁止・grep/sed 限定**にする。
過去の焦点: R1=exit/error code 一貫性、R2=JSONL append 網羅性 + search schema、R3=算術安全 + JCS 決定性、
R4=シリアライズ往復 + permission、R5=エンコーディング/正規化境界 + crash 時 write 順序 (Spark が chunks.jsonl の
fsync 欠如を指摘 → Q1 の遠因)、R8=時刻演算 + cost-ledger 会計 (Spark が check-then-append の無ロックを指摘 → F8 の裏付け。
ただし Spark の created_at tie-break/並行 append 破損は偽陽性 = stable sort/M1(b) で反証済み)、
R9=パス/ファイル名の正規化照合 + リソース/クリーンアップ漏れ (Spark の temp 残留 5 箇所 → R9-8 で採用。検証1 は
canonicalize 系の健全性確認どまりだったが、フルスコープ Sonnet が別経路の ignore 照合 R9-1 を出した=範囲限定の盲点をフルスコープが補完)、
R10=DAG/Evidence 整合の縁 + snapshot/commit 書込順序 (既存ガード M6/N5/L3・tree→commit→refs 順・CAS hash 検証が正しく成立と確認=実質 0 新規。
Spark の log-cycle 無限ループは content-addressing で到達不能、cross-snapshot-gen 欠落は L3/N5 既知として却下)、
R11=SQL/バックエンド規模境界 + task 状態機械会計 (R10-1 の k cap・per-scope 降格・R10-4/5 の attempts/error-kind/charge が
成立と確認=2 ラウンド連続の健全性確認着地。新規は COUNT(*) 存在 probe → R11-11 minor 採用。同ラウンドでフルスコープ勢が
別脈 (Agent/JSON 契約) から major 7 件=範囲限定の盲点をフルスコープが補完する R9-1 パターンの再現)、
R12=config 全 key 配線突合 + observability JSONL 網羅性 (検証1 が [search.rrf]/[search.diversify] 未配線を
file:line で特定=R12-1 の初動立証、検証2 が exit override/clap の errors.jsonl 素通りと append 失敗の
let _ vs ? 非対称を特定=R12-4/R12-5 の骨格。焦点が 4/4 収束所見と系統 major に直結した最収穫ラウンド —
範囲限定の当たり外れはフルスコープ 2 本と焦点の噛み合わせ次第)、
R13=ログローテ実装有無 + JSONL/リソース無限成長 (検証1 がローテ未実装 + config key 不在を file:line 網羅=
R13-3 の骨格立証で 3/4 収束の一角。検証2 の tasks.jsonl/cost-ledger/open cache 成長は docs 契約なしで据え置き裁定=
範囲限定が「据え置き判断の材料」を揃えた例。同ラウンドでフルスコープ 3 本が tools.toml/incremental/空 HEAD から
major 4 本=R9-1 パターン 3 回目)、
R14=R13 fix の新配線の網羅性 (rotating writer 呼出網羅/prune 誤爆 + tools.toml typed loader) — 検証1/2 とも
「取り残し/誤爆/drift なし」の健全性確認に着地 (Spark 0 新規)。だが同ラウンドでフルスコープ勢が incremental online
(previous 破損ブリック・遅延 stale hash・実 Mistral 全文送信) と self-heal read-only から major 4 本=R9-1 パターン 4 回目
(Spark の焦点が既修正脈の健全確認でもフルスコープが別脈で major=全体前進、R10/R11 と同型)、
R15=遅延実行 × identity 突合 + mock seam 乖離の網羅 (R14-2/R14-4 が開いた 2 脈) — 検証1 (遅延経路の hash 再検証) は
全「該当なし」の健全確認 (R14-2 が execute_online_markdownize_task 入口で保護済みを file:line で確認)、検証2 で
**unit-scoped retry が mode=Full で request_pages None → 実クライアント全文送信・按分課金と乖離を静的に特定=R15-5 の骨格立証**
(mock は失敗ユニットのみページ合成で隠蔽=Spark/GPT-5.5 のみ検出可能な型)。同ラウンドでフルスコープ勢が snapshot orphan・
phantom charge・registry stale・tree 欠落から major 5 本 (3 つが多エンジン収束)=Spark の焦点が「健全確認 + 1 骨格」でも
フルスコープが別脈で大量 major=R9-1 パターン 5 回目、かつ mock 隠蔽型 (R15-5/R15-6) は静的枠の独自価値を再確認。
R16=R15 fix の新配線網羅 + store 破損契約突合 (検証1 (a)(b) は「該当なし」の健全確認、(c) で **diff の read_tree raw 透過を
docs/05:341 対照付きで特定=R16-5 の初動立証**。検証2 で **repair --rebuild-db の read_tree 未変換を reindex L2608 の
対照付きで特定=R16-4 の骨格立証**。フルスコープ 2 本 (Sonnet-A/D) と収束した R12 型の噛み合いラウンド。同ラウンドで
フルスコープ勢が commit object 欠落 (4/4 Sonnet)・Fatal 増幅・parser bypass・phantom retry charge から major 6 本)。
**次ラウンド R18 は別の焦点に回すこと**。**下記は R18 用に書き換え済み** (R17 fix が開ける穴の新配線網羅=
resolve_pointer best-effort 分離の境界 (真の shallow degrade vs commit 欠落拒否)・reclaim ledger の新配線 (二重 reclaim/
reclaim×charge 並行窓/月跨ぎ)・reindex skip-continue の snapshot 整合 + cost-ledger 会計の残余=reclaim ledger の
effective_spent 整合・month 月跨ぎ据え置き再評価。いずれも静的読解が効く。R19 以降ではまた別焦点に):

```
あなたは KCS (開発者自身のリポジトリ) の焦点セキュリティ監査人です。出荷前の防御的セキュリティ監査。
範囲限定 (丸読み禁止、grep/sed/rg のみ)。リポジトリのファイル変更禁止。ネットワーク不要。
今回 (R18) の焦点は 2 つ。過去 (R17=R16 fix 網羅+cost-ledger 残余、R16=R15 fix 網羅+store 破損契約、R15=遅延実行×identity/mock 乖離)
とは別で、R17 fix が開ける穴 (定番脈 8 例目候補) と cost-ledger reclaim/会計の残余を静的に掃討する。

検証1 (R17 fix の新配線が開ける穴): R17 で 7 件の fix が入った。その新配線が別の穴を開けていないか。
`rg -n 'unresolvable_commit_pointer|resolve_commit_shallow|is_store_not_found|is_rebuild_skippable_unit_error|reserved_usd|reserved_month|reclaim_ledger|reclaim|skipped_units|searchable|effective_spent|task_retry_allowed' crates/kcs-core/src crates/kcs-cli/src --type rust` で
(a) R17-1: resolve_pointer_for_cli の best-effort が「read_commit 成功 + read_tree STORE-NOT-FOUND=真の shallow」に
    限定され commit 欠落は EVIDENCE-POINTER-INVALID に分離された。その境界で (i) 真の shallow (commit 実在・tree GC) の
    view/open degrade が壊れていないか、(ii) status/log/search の R16-1 commit 欠落 degrade が resolve_pointer の厳格化に
    巻き込まれて誤って loud 化されていないか、(iii) EVIDENCE-POINTER-INVALID 分離が tombstone/retarget 等の他の正当な
    解決失敗経路と衝突しないか、
(b) R17-2: run_reindex の copy_normalized_instance_gen skip-continue が (i) skip した文書の前世代 normalize ref を維持する
    ことで snapshot/tree_entries と sqlite が整合するか (skip 文書が古い gen の chunk を指し続けて検索に混入しないか)、
    (ii) rebuild 側 (R16-4) の skipped_units と reindex 側の skip が merge_reindex_skips で正しく dedup されるか、
(c) R17-3: reclaim ledger (cost-ledger-reclaimed.jsonl) の新配線で (i) 二重 reclaim (同一 task の supersede が複数回発火)
    が stamp クリア + non-retryable 化で防がれるか、(ii) reclaim append と charge append の並行窓 (device-global lock の範囲)、
    (iii) reserved_month と現在 month の月跨ぎで reclaim が誤った month の集計から引かれないか、(iv) effective_spent =
    charges − reclaimed が負にならず cap-safe (実支出 ≤ 予約) を保つか、
を file:line で挙げる。

検証2 (cost-ledger 会計の残余): reclaim という新しい会計軸が R17-3 で入った。charge 側は F8/R11-6/R15-2/R16-7 で 4 巡、
reclaim 側は R17-3 が初。残る非対称を突合する。
`rg -n 'reclaim_ledger|reserved_usd|reserved_month|effective_spent|charge_cost_ledger_under_lock|budget_remaining_for_adapter|utc_month' crates/kcs-cli/src crates/kcs-core/src --type rust` で
(a) reclaim ledger の読み (budget_remaining_for_adapter) と charge/reclaim の書きが device-global lock で整合するか
    (reclaim 専用 lock か cost-ledger lock か・並行 reclaim の二重計上)、
(b) month 月跨ぎ (R17 据え置き=execute_pending_markdownize_tasks/run_embedding_enrichment の month がループ前 1 回計算) の
    再評価 — charge/reclaim の month 決定が一貫し、翌月分の前月記帳が cap 判定に与える実害の範囲、
(c) reserved_usd/reserved_month stamp が付かない古い task (fix 前の Failed task) の reclaim 挙動・baseline 行 (usd 0.0)・
    embedding 経路 (reclaim 非対応=enqueue-time retirement hook なし) の orphan 予約、
を file:line で挙げる。

出力: 検証1 (a)(b)(c) + 検証2 (a)(b)(c) の該当箇所を file:line + なぜ問題か で列挙 +
エンジン識別子「GPT-5.3-Codex-Spark」。確実なものだけ。憶測は書かない。ファイル変更禁止。
```

## 7. 過去実績 (参考)

R1 (M1-M8): 1 critical + 7 major。並行 index で device-global ledger 破損 → 全 scope 巻き添え等。
R2 (N1-N8): 1 critical + 6 major + 1 minor。Tier B 秘匿候補の無確認オンライン送信等。
R3 (O1-O7): 2 critical + 3 major + 2 minor。cursor の scope 迂回 + 偽造、query embedding の送信境界等。
R4 (P1-P10): 1 critical + 4 major + 5 minor。tasks.jsonl input_path の scope 逸脱 → 外部 API 送信、
非アトミック sqlite 再構築 → 並行 search の沈黙偽陰性 (docs の並行契約違反)、.kcs world-readable での CAS 秘匿露出、
redact_logs の message 経由パス漏出 (N3 の不完全修正) 等。P10 は P5 修正の実機再確認中に派生発見。
R5 (Q1-Q6): 0 critical + 4 major + 2 minor。chunks.jsonl torn 末尾行が index/reindex/repair を恒久ブリック
(3 エンジン独立収束・復旧コマンド repair 自身が道連れ死)、prepared/image の非アトミック書込 + 無検証 serve、
online task の Running 恒久固着、NUL/UTF-16 が index 成功なのに検索不可。**Q1 は修正発注後の実機再検証で
「skip だけでは append がマージ行を作り再ブリック」と判明 → torn tail の物理 truncate で完全自己修復に是正**
(オーケストレータの再現検証がフィックスの穴を捕捉した好例)。GPT-5.5 #1 (chunking_config 沈黙欠落) は実機反証で却下。
R6 (R6-1〜R6-8、別セッション): 1 critical + 3 major + 4 minor。approvals.jsonl の scope_id 未束縛で秘匿 online 送信、
normalized_units 破損が repair/reindex を止める (Q1/Q2 の類型を別経路に拡張)等。
R7 (R7-1〜R7-5、別セッション): 1 critical + 4 major。secrets-approved.jsonl の存在だけで Tier B 秘匿送信、embedding retry/profile 互換等。
R8 (F1-F8): 0 critical + 6 major + 2 minor + design 1。budget/cost-ledger 会計が最も濃く未監査 (ローカル baseline が cloud cap を
消費[仕様違反]、負値 usd で cap fail-open、check-then-append TOCTOU、config 未配線)、NFC/NFD 検索欠落 (4 エンジン収束)、
embedding 応答の次元未検証で永久 KNN 除外。**F8 の fix は reserve-before-send で失敗/再試行も課金する cap-safe トレードオフ**
(代替=lock を送信中保持し device 直列化)。F6 (online markdownize 昇格) は Step 4 保留。GPT-5.5 #1 (chunking_config) 系の偽陽性は却下。
(R9 は上のブロックに詳述。)
R9 (R9-1〜R9-8): 0 critical + 5 major + 3 minor。今回はいずれも「ユーザー意図と実際の乖離」層 — .kcsignore の NFC/NFD
不一致で除外が silent 失敗し索引/online 送信/検索露出 (Sonnet、R8 F2 検索"内容"の対になる照合側=別鉱脈)、text-native
(md/txt/code) に online Mistral OCR task を enqueue・実送信・課金 (Opus、routing の意味論=8 ラウンドの死角)、open/view 展開
cache が world-readable (GPT-5.5、P2 の 0700 化が cache 側未達)、Partial task が retry/resume/再index 全滅で回復不能かつ
index_status 完了偽装 (GPT-5.5、docs/04 §5.2 の partial→done 契約違反)、gen dir の余剰 entry 1個 (crash 残留 .tmp/.DS_Store)
で reindex が恒久ブリック (オーケストレータが Spark の temp 所見からエスカレーション=P10 型派生発見)。**4 エンジンが 4 方向に
散り重複ゼロ**。**却下ゼロ** (ただし GPT-5.5 の「resume は Paused のみ」は不正確=Pending も駆動される、が R9-7 の根拠に転用)。
R10 (R10-1〜R10-8): 0 critical + 6 major + 2 minor。3 脈に分散 — (a) 規模境界がコア機能を壊す (Opus、ベクトル KNN が unbounded k を
sqlite-vec に渡し >4096 chunk scope が device 全域 search を誤 CONFIG-SCHEMA で墜落、per-scope isolation 契約違反=9 ラウンドの死角、
数百文書で普通に到達)、(b) ユーザー意図の除外/予算/回復が静かに破綻 (GPT-5.5 top-level ignore の config-key drift、Sonnet ignore の
case 照合=R9-1 の case 版、Sonnet Partial retry の無制限再送=R9-4 fix が開けた穴、Opus persist 誤分類の課金喪失)、(c) 派生 cache の
crash-atomicity (GPT-5.5 open cache 非アトミック + hit 無検証=Q2 の cache 版)。**Spark の範囲限定 DAG/Evidence 探索は既存ガード
(M6/N5/L3・tree→commit→refs 順・CAS hash 検証) が正しく成立と確認し実質 0 新規=掘り尽くした脈の「健全性再確認」も監査価値**。
却下 5 (log-cycle 到達不能・cross-snapshot-gen 既知・raw_hash-path-fold 設計・registry 秒精度 tie 安全・open-cache 12桁衝突 単独未実証)。
**フィックス実機再検証で全 major を repro クローズ確認** (R10-1 は agent が遅い e2e を単体テストに置換→オーケストレータが実 index→search
全モードで再検証、R10-4 は attempts が max_attempts で halt し cost-ledger plateau を実測=R5 Q1 型の再検証)。**Opus/Sonnet の 2 件が
task-lifecycle の両側 (無制限再送 R10-4 と恒久固着 R10-5) を別々に捕捉**=状態機械の会計は sibling が残る脈 (R11 Spark 焦点に転用)。
**フィックスの clippy は --all-features で回すこと** (R8 で --all-features 限定の 9-arg compile error を検出、通常 test は通過)。
かつ**背景エージェントの transcript mtime は buffer 遅延するので「idle 判定」に使わない** (R8 で誤判定 → 完了通知を待つのが正)。
R11 (R11-1〜R11-11): 0 critical + 7 major + 4 minor (major 数は R1 と並ぶ最多)。3 脈 — (a) **Agent/JSON 契約の正面監査が
10 ラウンドの死角**で 5 件集中 (Sonnet clap `Cli::parse()` が --json を bypass、Sonnet+GPT-5.5 が独立収束した
「enrichment 失敗/pause が exit 0 完全成功」= ExitCode::AuthError/BudgetExceeded がデッド定義・CT2-BUDGET-005 実装テストが
Then(exit 6) を検証しない流用と判明、exit 3 の stdout/stderr 非対称、index_status の retryable Failed 不可視、view の
temporary 欠落)、(b) **規模劣化の第 2 型=アルゴリズム的** (Sonnet: 非トランザクション全件再構築で noop 再index が初回同コスト
[R10-8 sibling、fix 後 1.01s→0.34s]、32 件バッチ毎の tasks.jsonl 全読み書き O(N²) [fix 後 14.7s→3.6s・線形化])、
(c) **R10-4 fix の unit-scope 側の穴** (Sonnet: unit_keys が全 crate で読まれない死にフィールド、retry が全文書 Full 再送・
全額再課金 [fix 後 retry 課金 1/3 按分を実測]、previous=None で first-instance-wins 未実装) + **config-key drift の [search] 版**
(Opus: default_mode/fail_behavior 完全未配線、fail_behavior=error が silent text fallback)。
**Sonnet が単独セッション内でエージェント委任の分業を自発再現し c2+M4+m2 の最大収穫** (critical 2 はオーケストレータが
major に降格採択: loud だが形式違反 / silent success 偽装は R9-4 と同 class の major が先例)。**却下 3 の学び**:
GPT-5.5 の「FTS 無制限 keyword で fatal」は Opus 5 万 term + オーケストレータ 2 万 term の実測で反証 (静的 only エンジンの
規模主張は必ず実測で裁定)、「NetworkError 固定」は R10-4 fix がコードコメントに rationale を記録していたことで既決と即断
(**fix 時に裁定理由をコードコメントへ残すと後続ラウンドの却下が高速化する**)。オーケストレータ側の新罠 2 つ:
**検証スクリプトのリダイレクト先を scope 内に作ると索引対象になり偽異常を生む** (idx.json/idx.err で 2 回発生 → 出力は
/tmp 直下か scope 外へ)、**XDG_DATA_HOME を複数 scope で共有すると search の横断集計が「規模異常」に見える** (正しい動作。
1 検証 1 XDG が正)。フィックス再検証は全 major 8/8 repro クローズ (exit 5/6/3 実機、性能 2 件は数値で確認、ct3_l2 の
期待値変更 [index budget pause→exit 6] は docs/06 §7 のスクリプト連携意図と整合を確認して受理)。
R12 (R12-1〜R12-7): 0 critical + 4 major + 3 minor。3 脈 — (a) **config-key drift の系統掃討が完結し両型が出揃った**
([search.rrf]/[search.diversify]/[markdownize.incremental] の silent ignore は **4/4 全エンジン収束** (R8 F2 以来)・
Sonnet の極端値 k=1/w_text=0/w_vector=1000 でバイト単位不変が決定打・Opus が max_per_raw_hash のページ跨ぎ適用による
「8 セクション文書の 5 chunk が恒久到達不能」まで定量化、[adapter.policy] は逆向きの **schema 拒否ブリック型** =
docs/07 §7 のコピペで scope 全コマンド exit 2・user config なら device 全体ブリック・redact_logs は実装が読む場所でも
検証が先に殺すため設定不能)、(b) **R11-5 fix が開けた crash 窓** (Sonnet 単独発見 → オーケストレータが実 SIGKILL で確定:
embeddings=64 時点 kill → task 1200 全 pending → 2 回目 index は欠落分のみ再駆動し 64 task 恒久迷子・
batch resume/retry/repair 全滅・index_status 虚偽。「fix が開ける穴」は R9-4→R10-4、R10-4→R11-6 に続く 3 例目 —
**前ラウンド fix の実機再検証は crash 面まで**が教訓)、(c) **observability の失敗系素通り** (exit 3/5/6 override +
clap + 失敗 search metrics。エンジン各自は断片を minor 評価 → オーケストレータが「auth 失敗が観測ログに痕跡ゼロ
(errors.jsonl ファイルすら未生成)」の系統性で major 統合裁定)。オーケストレータ事故→所見の 3 例目 = R12-6
(XDG_DATA_HOME 空文字で cursor-key が scope 内に落ちるのを検証事故で発見、P10/R9-5 型)。**オーケストレータ側の新罠 3 つ**:
Bash 呼び出しは毎回新シェルで export が持ち越されない (XDG 隔離は**コマンドごとに env で明示**)、zsh はグロブ失敗でも
export が空値で成立し得る (空 XDG=相対パス書込の引き金)、**chunk_vec は sqlite-vec 仮想テーブルで素の sqlite3 CLI から
読めない** (実機ポーリングは通常テーブル embeddings で行う)。kill -9 実再現の手法確立 (embeddings 件数ポーリング →
64 以上で SIGKILL、1200 chunk で窓は十分)。フィックス再検証は 7/7 repro クローズ (R12-3 は同一 kill 条件で ratio 1.0 +
レガシー固着 scope の自己治癒も確認、mmr Off 意味論の既存テスト期待値変更は docs/05 §1.4 と diversify summary の
off 報告との整合で受理)。
R13 (R13-1〜R13-6): 0 critical + 4 major + 2 minor。3 脈 — (a) **documented-unimplemented の大物 2 面が同時に落ちた**:
tools.toml 全面未配線は **3 エンジン別角度収束** (GPT-5.5=宣言 dead + env-only 活性化が docs/07 §7.1 と drift、
Sonnet=auth 3 方式が解決に不使用で `auth="env:MY_KEY"` 宣言が実機 silent noop・keychain 実装ゼロ、Opus=docs/06 §11 の
起動時 schema validation 欠落の実機 + blanket auth walk で documented key `url` の縁値 "plain:" が device brick)、
ログ日次ローテ/30 日保持は 3/4 収束で **Opus の「docs/09 に phase 割当なし=doc gap」異見を docs/09:110/124
(観測ログ=Step 1/3 割当) で反証して採択 — エンジンの不採択判断も裁定対象**、(b) **要件確定事項の実装未達**
(Sonnet 単独): incremental Markdownize が本番 adapter 両方で到達不能 — capability 宣言漏れ + online 経路に
mode/previous/hints が構造ごと欠落の二重欠陥で、R12-1 が配線した gate に本番が到達せず改版のたび全額再課金
(正実装が未配線という step3c r1 型の再来。**docs の規範だけでなく「要件確定メモ (MEMORY)」も監査の照合先になる**)、
(c) **新脈=store 破損処理の非対称** (Opus 単独): 空 HEAD + 健全 refs で snapshot が全履歴 silent orphan・exit 0
データ喪失 — 他の空ファイルは exit 2 拒否・refs 欠損は安全回復するのに HEAD だけ素通り (**Opus の部分破損網羅掃引
~25 破損 × 13 コマンドが「非対称」を浮かび上がらせた=網羅健全性確認の副産物として major が出る型**)。
フィックス側の学び 3 つ: **裁定の波及予測は fix 実地で訂正されうる** (capability_flags は identity::PROFILE_FIELDS 外で
tool_profile_hash 不変 → 予告した fixture 更新は不要だった)、incremental の cost-ledger は **full 見積予約のまま意図的残置**
(cap-safe 側の R8 F8 型トレードオフ。R14 裁定候補として記録済み)、keychain auth は **exit 0 + JSON 開示 +
errors.jsonl 記録の意図的裁定** (search 耐性優先、fix メモに rationale あり)。オーケストレータ側の新罠 2 つ:
**`cmd; echo; echo exit=$?` は $? が直前の echo を拾う** (exit 捕捉はコマンド直後に行う)、**KCS_TEST_GEMINI_EMBED=''
(空文字) は「未知値=不活性」であり未設定と別物** (seam を外すなら env -u で)。検証事故が防御の健全性を逆確認した例 1 つ
(scope config への allow_network 誤追記を R12-2 型 validation が正しく exit 2 で弾いた)。据え置き 1 群を初導入
(tasks.jsonl done 蓄積/cost-ledger 月跨ぎ/quarantine/open cache eviction=docs 契約なし + done_output_for 冪等との
衝突リスクで Step 4 gc 設計へ明示送り。**「据え置き」は silent cap ではなく裁定ファイルに理由つき記録**)。
フィックス再検証は 6/6 repro クローズ (incremental は v1→v2 実機で changed=page:2 のみ送信 + 4 unit reused_from、
空 HEAD は C1 温存 + 無変更 snapshot の正当 noop + 修復イベントまで確認)。
R14 (R14-1〜R14-6): 0 critical + 4 major + 2 minor。7 エンジン (Opus/Sonnet-A/B/C/D + GPT-5.5 + Spark)。全て「R13 fix が
開ける穴」脈 (R9-4→R10-4、R11-5→R12-3 に続く 4/5 例目)。3 脈 — (a) **同型の非対称エラー伝播が 3 本**: previous 正規化
インスタンスの unit ファイル 1 個部分破損が Full 降格を迂回し online markdownize を恒久ブリック=`load_previous_instance` が
manifest 欠損は `Ok(None)` なのに unit 読込だけ hard Err (**Sonnet-A/B/C/D の 4 本独立収束**・Sonnet-C が offline 経路の
index 全体巻き添えまで拡張)、遅延 online task が現ファイルを enqueue 時 stale input_hash 下に保存する content-addressing
不変条件破壊 (**Opus 単独**・オーケストレータが prepared_hash 突合で v1 raw_hash 下に v2 内容を確認)、R13-4 self-heal が
read-only + 破損 HEAD で純読み取りまで恒久失敗 (**Sonnet 4 本 major + Opus minor**、severity は 4/5 の major を採り
read-only アーカイブ用途の実害で裁定)、(b) **mock seam が実挙動を隠す型** (GPT-5.5 静的のみ検出可): incremental が実
Mistral 経路で全文送信・全ページ再課金=mock は hint からページ合成し差分に見せるが実クライアントは `std::fs::read` で全文を
`pages` パラメータなしで送信 (step3c r1/R13-1 と同型=正実装が mock でしか効かない)、(c) minor 2 (batch の search 系
error_code 僭称・incremental の profile 判定が送信後)。**Spark 検証1/2 は R13 fix 網羅性の健全確認に着地 (0 新規) だが
同ラウンドでフルスコープが別脈で major 4 本=R9-1 パターン 4 回目**。却下=未来日付 mtime のローテ無効化 (Sonnet-B、mtime は
次 append で補正され 1 サイクルのみ=Sonnet-A/C/D + Opus + オーケストレータが反証。**単一エンジンの「恒久」主張は
自己修正機構を見落とし得る=多エンジン反証が効く型**)。フィックス側の学び: **R14-2 の supersede は task 状態機械に
superseded 非エラー状態が無いため InvalidInput を採用** (回復は再 index の fresh task で担保、R14-1 の Full 降格経路とは独立)、
R14-4 の実 API 課金削減はユーザー gate (pages 送信のコード fix + comment 訂正のみ、実 Mistral 検証は保留)、R14-1 の Full 降格は
control 付き再現 (破損 unit 1 個の有無だけで success↔恒久失敗が反転)。フィックス再検証は 4 major を control 付き実機 repro
クローズ (R14-1 破損→Full 降格 done、R14-2 supersede で v1 identity 下に v2 内容が入らない、R14-3 read-only で status/log
exit 0・健全 HEAD read-only で search 動作、R14-4/R14-6 は unit test)。**mock seam が実挙動を隠す型は実機エンジンが
原理的に検出不能=静的読解エンジン (GPT-5.5) の独自価値**。
R15 (R15-1〜R15-8): 0 critical + 6 major + 2 minor。7 エンジン。**3 つの独立多エンジン収束** (snapshot orphan=Sonnet-B/C、
phantom charge=Sonnet-A/C/Opus、registry stale=GPT-5.5/Sonnet-B)。3 脈 — (a) **「fix が開ける穴」が 5/6 例目で 3 本**:
空 HEAD + self-heal 延期下で snapshot が実履歴 orphan 化 (R13-4/R14-3 の合流=head_commit_hash が empty_head_recovery_hash に
fallback せず・snapshot_with_type が再 heal しない。R14-3 コメントの「orphan しない」保証をオーケストレータが seam/自然 lock で
実機反証)、supersede/陳腐化 task の phantom charge (R11-6 実行前 charge と R14-2 実行前 supersede の合流=charge が execute の前・
R14-2 裁定の「誤課金も消滅」を反証)、unit-scoped retry が実クライアント全文送信で按分課金と乖離 (R11-6 retry 按分と R14-4
incremental pages の未接続=mock 隠蔽で Spark/GPT-5.5 のみ検出)、(b) **store corruption robustness の第 2 面** (Sonnet-D):
HEAD tree object 欠落で status/index/repair 全滅・回復コマンドゼロ (R13-4 空 HEAD に続く HEAD/tree 2 破損目・docs/05 shallow 契約違反。
Opus は「loud fail・GC 未実装で通常到達不能」と異見したが status 純読と repair 回復の robustness で major 裁定)、(c) **mock seam
隠蔽型が 2 本** (R15-5 retry 全文送信・R15-6 0-change incremental 全文送信=choose_markdownize_mode の change_rate==0 素通り +
is_empty ガード欠如)。**オーケストレータの統合裁定**: charge/execute の非対称を supersede (過剰課金) と retry (過少課金) の
両方向で捕捉し R15-2/R15-5 に整理、Opus の snapshot orphan「問題なし」判定を実機再現で反証 (R13 の Opus doc-gap 型=
エンジンの不採択判断も裁定対象)。**フィックス側の学び**: R15-1 は head_commit_hash 一箇所の fallback で orphan (write) と
read 誤報の両方を解消 (unborn は refs 空で従来通り None)、R15-4 は KcsError::commit_shallow + HeadTreeState tri-state で
status degrade (FileStatus.status を Option 化) / write を KCS-E-COMMIT-SHALLOW-001、R15-5 は MarkdownizeRequest に
restrict_to_hint_pages シグナルを足し fresh full (pages なし) と retry (pages 絞り) を区別、R15-6 は mock が隠すため専用 seam
no_change_no_send を pin_changed に倣って追加。**オーケストレータ側の学び 2 つ**: 修正 Agent は 8 件順次で watchdog
ストールし得る (full-workspace テスト繰り返しが一因 → ターゲット絞りテストを指示・partial 実装は作業ツリーに残るので
git diff で回収し 2nd agent に引き継ぐ)、shallow write 拒否の repro はファイルを**編集**して tree 読込を強制しないと
index が sqlite cache 経由 noop で短絡して穴が見えない (未編集だと index が tree を再生成し自己修復に見える)。
フィックス再検証は 4 major を control 付き実機 repro クローズ (R15-1 orphan せず履歴保持、R15-2 supersede で markdown 課金 0 行、
R15-3 再 init で search 1 件・registry 1 行、R15-4 status exit 0 degrade + index/snapshot/reindex が SHALLOW エラー)、
R15-5/R15-6 は discriminator テスト (fix 無効化で fail)。
R16 (R16-1〜R16-7): 0 critical + 6 major + 1 minor。7 エンジン。**却下 0 の 2 回目 (R9 以来)、うち自己取り下げ 1**
(Sonnet-C がハーネス artifact を自分で切り分け不採用=品質バーの内面化)。**commit object 欠落に 4/4 Sonnet が完全独立収束
(史上最強)** — R13-4/R15-4 が `read_tree` にだけ吸収を適用し同じ関数・隣接行の `read_commit` を素通しにした構造穴。
R15-4 の fix は run_reindex では「10 行差で tree は処理・commit は素通し」という極端な非対称だった=**「fix が適用範囲を
絞った際の相似形の隣」も掃く対象** (「fix が開ける穴」の変種)。3 脈 — (a) store 破損掃討の本命 (R16-1 の read/write/
Evidence 全滅 [Sonnet-C が docs/05:345 の Evidence 保証破れ=中核価値直撃を特定・Sonnet-B が履歴奥 log 全滅・Sonnet-D が
sqlite 欠落は正しく part-failure する対照実験で一意切り分け]、R16-2 の multi-scope Fatal 増幅 [Sonnet-A 単独・05 §1.8 違反・
R10-1(a) が 1 エラーコード限定で塞いだ穴の未全称化]、R16-4 の repair 部分回復力ゼロ [R15-4 裁定文が名指しした repair が
fix/テスト適用範囲から漏れた=fix 網羅性の穴・Spark が reindex 対照で骨格立証]、R16-5 の diff 契約乖離 [4 エンジン収束で
severity は 2:1 で minor])、(b) silent 型 2 本は GPT-5.5 静的単独 (R16-3 fresh search の shallow silent 空=cursor だけ loud で
fresh が Ok(false) 黙殺・index_is_rebuilding も 0 行不発、R16-6 の `--force=false` 確認ゲート bypass=R12-7 の
split_flag_value が開けた穴 7 例目) — **3 ラウンド連続で「silent/mock 隠蔽型は静的枠のみ検出」**、(c) cost-ledger 脈の
残りに Opus 単独 major (R16-7 retry phantom charge 無制限累積=RateLimit max_attempts None × 試行ごと満額再予約で cap 枯渇→
他 scope 正規タスク誤 Paused。**F8「失敗でも予約維持」の既知トレードオフとの境界を裁定で明文化** — 429 系は課金され得ない
から skip・NetworkError は二重課金があり得るから従来通り、Opus 提案の「生涯 1 予約」は cap silent bypass を開けるため不採用
=fix 設計の却下理由もコードコメントに残す)。**フィックス側の学び**: 7 件を 2 エージェント分割 (クラスタ 5 + 独立 2) で
順次発注し R15 の watchdog ストールを回避 (1 本目が 4.6 秒 0 tool で異常終了 → git status で無傷確認して再発注=空振り
検知の手順化)。R16-3 の commit 欠落マッピングは fix 実地で「cache 行の有無で分岐」に訂正 (裁定の単純 Excluded 案は R16-1 の
read degrade と矛盾했)、R16-4 の skipped_units は exit 0 + JSON 開示 (partial exit 3 案は error code 新設/借用の
両難で回避=R14-5 の教訓)。**オーケストレータ側の学び 3 つ**: 実験台 scope を pre-fix/post-fix で使い回すと
index_rebuilding 等の正直な遷移状態が偽 regression に見える (repro クローズは使い回し scope でなくクリーン scope で)、
restore 時に tree/commit の hash を取り違えると junk object を作る (backup は `shasum -a 256` で実 hash からパス再導出)、
`cmd | head; echo exit=$?` は head の 0 を拾う (R13 の変種・exit はパイプなし別実行で取る)。フィックス再検証は全 7 件
repro クローズ (R16-1 read 4 コマンド exit 0 degrade + write 拒否 + 復元、R16-2 破損 exit 3 + 健全結果保持 + 欠落は cache
継続、R16-3 excluded snapshot_shallow 明示、R16-4 COMMIT-SHALLOW + skipped_units 部分回復、R16-5 side 明示、
R16-6 全パターン exit 2 + bare control 正常、R16-7 rate_limit×3 で charge 1 行のまま attempts 3)。
R17 (R17-1〜R17-7): 0 critical + 3 major + 4 minor。7 エンジン。**「R16 fix が開ける穴」が本命的中 (定番脈 7 例目)**。
3 脈 — (a) **resolve_pointer_for_cli の best-effort 過剰適用** (R17-1) に **4 エンジン独立収束** (Sonnet-B/C/D + GPT-5.5、
R16-1 に次ぐ強収束): R16-1 が `read_commit` 欠落を「真の shallow」と同一視したことで捏造 commit hash で N5 gen 束縛 +
tree 所属チェックを両方迂回でき、evidence-grounded 中核 (view/open) の identity 検証が commit 偽造だけで無力化。
**Opus は「返す chunk は identity を通った真正 chunk なので検証弱化なし」と healthy 誤判定 → オーケストレータが N5 gen 束縛の
実機バイパス (Attack A 実在旧 commit+gen1 chunk=exit4 / Attack B 捏造 commit+gen1 chunk=exit0) で反証** (R13 doc-gap /
R15 snapshot orphan の Opus「問題なし」誤判定を実機で覆す型 3 例目)。**「fix が開ける穴」の新変種**: R16-1 の best-effort は
「適用範囲の絞り漏れ」(R16 の read_commit 素通し) ではなく**「適用範囲の広げ過ぎ」**(commit 欠落を真の shallow と同一視=
docs/08 §3.2「commit object 存在=解決前提」の無断拡張) が穴を開けた。(b) **Sonnet-A の別脈 (repair/reindex 破損耐性) が 3 連発**
(R9-1 パターン 6 回目): reindex --force 正規化ループが単一破損 unit で全 scope 停止 (R17-2、R16-4 の skip-continue が run_reindex に
未移植の兄弟穴・repair guidance が壊れた reindex を案内)、store 破損クラスの exit 非対称 (R17-4)、skipped_units の false alarm
(R17-6)。(c) **cost-ledger phantom charge の残り** (R17-3、Opus 単独 major・control 実機): R15-2 (supersede が Pending/Paused のみ
退役) × R16-7 (rate_limit=非課金) の合流点で Failed(rate_limit) の F8 予約が編集後 reclaim されず per-adapter cap 枯渇→正規タスク
誤 Paused (crash 不要・rate_limit+編集の通常操作)。+ R16-1/R16-5 隣接漏れ (R17-5、resolve_commit/tag、Sonnet-B+Opus 2 収束)、
R16-7 コメントの triple-fault 誤主張 (R17-7、GPT-5.5+Opus 2 収束)。**却下 1** (Spark の enqueue TOCTOU=cap 読みは task 初期分類
のみ・権威は lock 下 charge の再読で cap-safe)。**据え置き 1** (month 月跨ぎ誤記帳=Sonnet-C minor vs Opus 保守側 healthy で割れ・
charge 総額は正で有界稀=Step 4 送り)。**フィックス側の学び**: R17-1 の commit 欠落分離は R16-1 の裁定 (view degrade) を部分訂正し
r16_1 テストの view 部分を変更 (status/log/search degrade は温存)。R17-3 の phantom reclaim は F3 (負値禁止) と両立させるため
sibling ledger (cost-ledger-reclaimed.jsonl) に正値の reclaim 行を append し budget_remaining が effective_spent=charges−reclaimed で
差し引く (charge ledger には phantom 行が残る=F3 維持)。**R17-4 は修正 Agent が新コード KCS-E-SEARCH-STORE-CORRUPT-001 を導入したが
docs のエラーコード一覧 (06 §8/10 §7.5) に不在=docs 契約違反をオーケストレータが検出し既存 SCOPE-ALL-FAILED + context.recovery に
訂正** (**新コード導入は docs 凍結下では避ける**=新しい学び)。**オーケストレータ側の学び**: fmt --check の exit code は `| head` で
拾うと 0 になる罠 (R13/R16 の変種・パイプなしで直接取る)、相対パス KCS を cd 後に使うと exit 127 (絶対パスで)。フィックス再検証は
3 major を control 付き実機 repro クローズ (R17-1 捏造 commit exit4 + N5 対照両方 exit4 + 真 shallow 継続、R17-2 corrupt skip +
healthy 再正規化、R17-3 exp9 phantom が control と一致=v2 pending)。
→ **17 ラウンドとも完全に別の鉱脈から実バグ。契約テストが全 green でも探索型は毎回新規を出す。
かつフィックスも実機フルサイクル再検証しないと不完全なことがある (R5 Q1・R8 F8・R10-1 の e2e 置換をオーケストレータが再実行、R11-5 → R12-3 は crash 面の再検証漏れが翌ラウンドの major)。範囲限定 Spark の
「問題なし」領域からフルスコープエンジンが major を出す (R9-1・R11・R13・R14・R15 で再現)、オーケストレータの検証フェーズ自体が発見装置になる (P10・R9-5・R12-6) パターンも定着。
かつ Spark の焦点が「掘り尽くした脈の健全性確認」に着地しても (R10 の DAG/Evidence、R11 の規模境界+task会計、R14 の R13 fix 網羅性)、フルスコープが別脈で major を出せば全体は前進する (R12 は焦点がフルスコープと噛み合い 4/4 収束、R13 は焦点立証 + フルスコープ 3 本、R14 は健全確認着地でもフルスコープ 4 major の二毛作、R15 は Spark が検証2 で R15-5 の骨格を出しつつフルスコープが別脈で major 5 本、R16 は焦点が R16-4/R16-5 の初動立証でフルスコープと噛み合い)。
かつ「fix が開ける穴」は R9-4→R10-4、R11-5→R12-3、R13-1/R13-4→R14、R11-6/R13-4/R14-2/R14-3/R14-4→R15、R15-4/R12-7→R16、R16-1/R16-4/R15-2×R16-7→R17 と定番化 (7/7 例目) — 前ラウンド fix の新配線を必ず次ラウンドで掃く。しかも R15 では複数の過去 fix の**合流点** (R11-6+R14-2、R13-4+R14-3、R17 では R15-2+R16-7 の phantom charge)、R16 では「fix が適用範囲を絞った際の**相似形の隣**」(read_tree だけ吸収し read_commit 素通し)、R17 では「fix の**適用範囲の広げ過ぎ**」(R16-1 が commit 欠落を真の shallow と同一視=docs 前提の無断拡張) が新しい非対称を生んだ=単一 fix・fix の組み合わせ・「同型コードの隣」に加え「fix の過剰適用 (docs 前提を越えた degrade)」も掃く対象。かつ mock seam/silent 型 (R14-4・R15-5・R15-6・R16-3・R16-6) は静的エンジンだけが捕捉できる=7 エンジン構成の GPT-5.5/Spark 枠は必須。かつ多エンジン収束 (R15 で 3 件、R16 は 4/4 Sonnet の史上最強収束、R17 は resolve_pointer に 4 エンジン=Sonnet-B/C/D+GPT-5.5) は同一 fix 領域を別角度で立証し severity 裁定を固める。かつ Opus の「問題なし」誤判定を実機で反証する型 (R13 doc-gap・R15 snapshot orphan・R17 resolve_pointer の N5 バイパス) は 3 例目=エンジンの不採択判断も裁定対象。**
