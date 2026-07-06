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
defensive security 作業であり、拒否する理由はない。過去 14 ラウンド (R1-R14) で秘匿情報漏出 (critical) を含む
実バグを多数捕捉し、すべて修正済み。

## 1. 対象

- リポジトリ: `/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs` (main)
- KCS = Rust 製のローカル知識アーカイブ CLI (evidence-grounded local knowledge archive)。
  `kcs init/index/snapshot/search/view/open/batch/reindex/repair/diff/tag/log/status` 等。
  仕様正本は `docs/01`〜`docs/10`。実装は `crates/kcs-{core,pipeline,adapter,index,search,cli}`
- 現状 (R14 完了時点、次ラウンドは R15): 全テスト green (440)、clippy(--all-features)/fmt clean。Step 1-3 実装済み + 探索型監査 R1-R14 修正反映済み +
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
- docs で `Step 4` / `Phase 4+` / `v2+` と明記の未実装

**過去 14 ラウンドの鉱脈は掘り尽くし気味**: R1=並行/異常系の後続経路、R2=秘匿情報漏出/パス検証/資源枯渇、
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
R14=「fix が開ける穴」脈が R13-1/R13-4 で的中 (R9-4→R10-4、R11-5→R12-3 に続く 4/5 例目) — 4 本の穴が共通して「正常系 (Ok(None)/フォールバック) のすぐ隣で異常系だけ `?` でハード伝播する非対称」(previous unit 部分破損の恒久ブリック・遅延 online task の stale hash 保存・self-heal の read-only 致死化) + mock seam が実挙動を隠す型 (incremental 実 Mistral 全文送信=mock でしか差分に見えない・step3c r1/R13-1 と同型で GPT-5.5 静的のみ検出可)。
**新しい鉱脈の方が期待値が高い** (下記ヒント参照)。R14 で「R13 fix の新配線 (incremental online の previous/hash/送信・self-heal の read-only)」は掘って修正済み。
R15 Spark は別焦点へ (§6 は R15 用に書き換え済み: 派生 CAS object の遅延実行と identity の突合=遅延タスクが読む「現在」と保存する「過去 hash」の乖離を index/reindex/repair/batch の全遅延経路で静的掃討 + mock seam が実挙動を隠す箇所の網羅)。

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
5. 採択した所見を `tasks/step3-bughunt<N>-fixes.md` に裁定として書き、コミット (R14 は bughunt14、**次 R15 は bughunt15**)
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

既知 (報告不要): tasks/step3-checkpoint-fixes / step3-bughunt-fixes / bughunt2〜bughunt14 (R15 開始時は
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
batch の自前 error_code (R14-5)、incremental profile 判定の送信前 gate (R14-6)、tasks.jsonl・cost-ledger・open cache の
無限成長は据え置き裁定済み (Step 4 gc 設計マター)) は掘り尽くし気味 — 新しい鉱脈の方が期待値が高い (R15 候補):
  - **派生 CAS object の遅延実行 × identity 突合** (R14-2 が開いた脈): online markdownize は enqueue と実行が別 pass
    (遅延)。R14-2 は execute_online_markdownize_task に hash 検証を入れたが、他の遅延経路 (embedding task の再実行、
    reindex/repair が読む prepared/normalized、batch resume が拾う Pending) が「現在の入力」と「保存する過去 identity」を
    突合しているか。R14-1/R14-2 fix の相互作用面 (supersede と Full 降格が同時発火する縁、supersede 後の再 index race)
  - **mock seam が実挙動を隠す型の網羅** (R14-4 が開いた脈): mock と実クライアントで送信内容/課金/permission が乖離する箇所を
    全 adapter (Mistral OCR・Gemini embedding) で洗う。実クライアントだけが持つ副作用 (全文送信・全 bytes upload・
    実 HTTP header) が仕様/comment と drift していないか (静的読解が効く=GPT-5.5 向き)
  - R14-3 self-heal 非致死化の縁 (best-effort 化で開く穴: read-only で heal 失敗→unborn 扱いのまま snapshot が
    走れる書込 race・修復 warn の記録漏れ・並行 open での二重 heal)
  - multi-scope 並列の縁 (MULTI-006 周辺: per-scope 降格・除外理由の一貫性、registry と実 .kcs の乖離時挙動)
  - 時刻/TZ の残り (DST/閏の境界、rotation の日付判定と UTC/local の縁)
  - DAG/Evidence の残り (tag→commit→tree の縁、shallow 境界での縮退。※空 HEAD は R13-4 で閉鎖済み)
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
(Spark の焦点が既修正脈の健全確認でもフルスコープが別脈で major=全体前進、R10/R11 と同型)。
**次ラウンド R15 は別の焦点に回すこと**。**下記は R15 用に書き換え済み** (派生 CAS object の遅延実行 × identity 突合=
R14-2 が開いた脈を全遅延経路へ + mock seam が実挙動を隠す箇所の網羅=R14-4 が開いた脈。いずれも静的読解が効く。
R16 以降ではまた別焦点に):

```
あなたは KCS (開発者自身のリポジトリ) の焦点セキュリティ監査人です。出荷前の防御的セキュリティ監査。
範囲限定 (丸読み禁止、grep/sed/rg のみ)。リポジトリのファイル変更禁止。ネットワーク不要。
今回 (R15) の焦点は 2 つ。過去 (R14=R13 fix 網羅性、R13=ログローテ、R12=config配線) とは別で、
R14 が開いた 2 脈を静的に掃討する (fix が開ける穴 + mock が隠す実挙動)。

検証1 (遅延タスク実行 × content-addressing identity の突合網羅性): R14-2 で execute_online_markdownize_task
(crates/kcs-cli/src/main.rs) に「現在ファイルの hash が task.input_hash と一致するか」の検証が入った。
online markdownize は enqueue と実行が別 pass (遅延)。同じ「保存時に過去の identity を使うが入力は現在読む」
構造が他の遅延経路に残っていないか。
`rg -n 'task.input_hash|input_hash|normalized_output_ref|hash_bytes|fs::read|prepare_units' crates/kcs-cli/src crates/kcs-pipeline/src --type rust` で
(a) 遅延実行タスク (embedding 再実行・reindex/repair が読む prepared/normalized・batch resume が拾う Pending) が
    「現在の入力バイト」を読みつつ「enqueue 時/過去 gen の raw_hash・tool_profile_hash」下に保存する経路で、
    R14-2 型の hash 再検証が欠けている箇所、
(b) `normalized_output_ref`/`prepared_output_ref` 等の出力 ref を過去 hash で組む呼出で、入力が変わり得る窓、
(c) R14-1 の load_previous_instance / R14-2 の supersede と、reindex/repair の再読込が衝突する縁、
を file:line で挙げる。

検証2 (mock seam と実クライアントの挙動乖離の網羅): R14-4 で mock が hint からページ合成する一方
実 Mistral client (mistral_ocr.rs) が全文送信していた乖離が判明。同型 (mock では見えない実クライアント固有の
送信内容/課金/permission/HTTP 副作用) を全 adapter で洗う。
`rg -n 'KCS_TEST_|Mock|std::fs::read|document_payload|send_json|reqwest|ureq|base64' crates/kcs-adapter/src --type rust` で
(a) mock client と実 client (EnvMistralOcrClient/EnvGeminiEmbeddingClient) で「API へ渡す入力の範囲」が
    異なる箇所 (mock は hint/部分・実は全文/全 bytes 等)、
(b) 実クライアントだけが持つ副作用 (全 bytes upload・header・include_image_base64 等) が docs/コード comment の
    規範と drift している箇所、
(c) mock seam でしか通らないテストが「実挙動の保証」を騙っている契約テスト、
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
→ **14 ラウンドとも完全に別の鉱脈から実バグ。契約テストが全 green でも探索型は毎回新規を出す。
かつフィックスも実機フルサイクル再検証しないと不完全なことがある (R5 Q1・R8 F8・R10-1 の e2e 置換をオーケストレータが再実行、R11-5 → R12-3 は crash 面の再検証漏れが翌ラウンドの major)。範囲限定 Spark の
「問題なし」領域からフルスコープエンジンが major を出す (R9-1・R11・R13・R14 で再現)、オーケストレータの検証フェーズ自体が発見装置になる (P10・R9-5・R12-6) パターンも定着。
かつ Spark の焦点が「掘り尽くした脈の健全性確認」に着地しても (R10 の DAG/Evidence、R11 の規模境界+task会計、R14 の R13 fix 網羅性)、フルスコープが別脈で major を出せば全体は前進する (R12 は焦点がフルスコープと噛み合い 4/4 収束、R13 は焦点立証 + フルスコープ 3 本、R14 は健全確認着地でもフルスコープ 4 major の二毛作)。
かつ「fix が開ける穴」は R9-4→R10-4、R11-5→R12-3、R13-1/R13-4→R14 と定番化 — 前ラウンド fix の新配線を必ず次ラウンドで掃く。かつ mock seam が実挙動を隠す型 (R14-4) は静的エンジンだけが捕捉できる=7 エンジン構成の GPT-5.5 枠は必須。**
