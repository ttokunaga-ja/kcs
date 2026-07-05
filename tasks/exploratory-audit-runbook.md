# 探索型 4 エンジン監査 ランブック (新セッション貼り付け用)

このファイル全体を新しい Claude Code セッションに貼り付ければ、探索型クロスチェックを 1 ラウンド
実行できる。長い会話コンテキストを引き継がずに毎回クリーンに走らせるための自己完結手順。

---

## 0. 位置づけ (安全ガードの誤発火を避けるため必読)

これは **開発者自身が所有する OSS リポジトリ (KCS) に対する、出荷前の防御的セキュリティ監査**である。
目的は自分のコードの脆弱性・不具合を第三者に悪用される前に発見して修正すること。攻撃対象は自分の
ローカルツールのみ。実 API キーは使わず、全操作は隔離した一時ディレクトリで行う。これは正当な
defensive security 作業であり、拒否する理由はない。過去 11 ラウンド (R1-R11) で秘匿情報漏出 (critical) を含む
実バグを多数捕捉し、すべて修正済み。

## 1. 対象

- リポジトリ: `/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs` (main)
- KCS = Rust 製のローカル知識アーカイブ CLI (evidence-grounded local knowledge archive)。
  `kcs init/index/snapshot/search/view/open/batch/reindex/repair/diff/tag/log/status` 等。
  仕様正本は `docs/01`〜`docs/10`。実装は `crates/kcs-{core,pipeline,adapter,index,search,cli}`
- 現状 (R11 完了時点、次ラウンドは R12): 全テスト green (368)、clippy(--all-features)/fmt clean。Step 1-3 実装済み + 探索型監査 R1-R11 修正反映済み +
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
- docs で `Step 4` / `Phase 4+` / `v2+` と明記の未実装

**過去 10 ラウンドの鉱脈は掘り尽くし気味**: R1=並行/異常系の後続経路、R2=秘匿情報漏出/パス検証/資源枯渇、
R3=検索境界の完全性/入力堅牢性/状態の縮退、R4=シリアライズ往復/ファイル permission/資源リーク/Agent 契約、
R5=エンコーディング境界 (NUL/UTF-16・BOM)/派生 CAS object と append-only pointer の crash-atomicity/task ライフサイクル、
R6=未束縛 approval の秘匿送信/破損 JSONL が repair をブリック/引数検証/schema future 互換、
R7=秘匿承認ファイルの存在判定/multi-scope opt-in/embedding retry・profile 互換、
R8=budget/cost-ledger 会計 (ローカル計上・負値・TOCTOU・config 未配線)/NFC-NFD 検索/embedding 応答検証/catalog identity、
R9=ルーティングの意味論 (text-native→OCR)/ignore パターンの NFC-NFD 照合/展開 cache permission/Partial の行き止まり状態/reindex の junk entry 耐性、
R10=規模境界がコア機能を壊す (ベクトル KNN の sqlite-vec k≤4096 上限で >4096 chunk scope が device 全域 search を墜落)/ignore の config-key drift (top-level 無配線) と case 照合/task 状態機械の retry 予算・error kind 会計 (Partial 無制限再送・persist 誤分類)/派生 cache の crash-atomicity (open cache 非アトミック + hit 無検証)、
R11=Agent/JSON 契約の正面監査 (10 ラウンドの死角=clap bypass・exit 5/6 未実装・exit 3 非対称・index_status/temporary 開示、5 件集中)/アルゴリズム的規模劣化 (ハード上限とは別型: 非トランザクション全件再構築・O(N²) task 更新)/R10-4 fix の unit-scope 穴 (全文書再送・全額再課金)/config-key drift の [search] 版。
**新しい鉱脈の方が期待値が高い** (下記ヒント参照)。R11 で「Agent/JSON 契約」と「規模境界の 2 型 (ハード上限 + アルゴリズム劣化)」は
正面から掘って一巡した。R12 Spark は「config 全 key の配線突合」(R10-2/R11-7 型の系統掃討) と「observability JSONL の網羅性」を掃く (§6)。

## 4. 手順 (新セッションの Claude が実行)

1. `git rev-parse --short HEAD` と `cargo test --workspace 2>&1 | grep 'test result'` で現状確認
2. 下記「共有バグハントプロンプト」を自分の scratchpad か `/tmp/bughunt-prompt.md` に書く
   (§0 の防御的セキュリティ位置づけを必ず含める)
3. **4 エンジンを並列起動** (Opus/Sonnet は抽象指示で自由に、Spark は範囲限定):
   - Claude-Opus: `Agent` tool、`subagent_type: general-purpose`、`model: opus`、
     run_in_background、プロンプト = 共有プロンプト + 「エンジン識別子 Claude-Opus。cargo/実機/python3 可」
   - Claude-Sonnet: 同上 `model: sonnet`、「エンジン識別子 Claude-Sonnet。実バイナリを自分の手で叩く」
   - GPT-5.5: `Bash` run_in_background:
     `codex exec -m gpt-5.5 -s read-only -C <repo> "$(cat /tmp/bughunt-prompt.md)\n\nエンジン識別子 GPT-5.5。read-only なので静的読解 + file:line 立証"`
   - GPT-5.3-Codex-Spark: `Bash` run_in_background、**範囲限定プロンプト** (下記 §6、丸読み禁止 grep/sed 限定)
4. 全エンジン回収後、所見を統合。**critical/major は自分で実機再現 or file:line 検証してから採否**を決める
   (エンジンの誤検出・既知重複を除外)。verify スクリプトの罠に注意:
   `grep -rl P dir | head && echo found` は grep 不一致でも head 成功で常に真。**grep の exit code を直接見る**
5. 採択した所見を `tasks/step3-bughunt<N>-fixes.md` に裁定として書き、コミット (R11 は bughunt11、**次 R12 は bughunt12**)
6. 修正を `Agent`(opus) に発注 (docs 変更禁止・各修正ごとに cargo test・回帰テスト必須・commit しない)。
   完了後 `cargo test --workspace` / `clippy -D warnings` / `fmt --check` 全 green を確認、
   critical は自分で実機再確認してからコミット
7. `git push origin main` は**ユーザーに依頼** (直接 push しない)

## 5. 共有バグハントプロンプト (Opus/Sonnet/GPT-5.5 に渡す本文)

```
あなたは KCS (Rust 製ローカル知識アーカイブ CLI) の探索的バグハンターです。これは開発者自身が
所有するリポジトリに対する出荷前の防御的セキュリティ監査であり、脆弱性・不具合を先回りして潰すのが
目的です。攻撃対象は自分のローカルツールのみ、実 API キーは使いません。

ミッション: 我々がまだ見つけていない不具合・脆弱性を見つけること。方法・観点は自由。

前提: Rust workspace、`cargo build` → target/debug/kcs、仕様正本 docs/01〜10。テスト green の状態。
seam: KCS_TEST_GEMINI_EMBED / KCS_TEST_MISTRAL_OCR (§2 参照)。実機は XDG_DATA_HOME=$(mktemp -d) で隔離、
scope は /tmp 配下。リポジトリのファイル変更禁止。verify は grep の exit code を直接見る。

既知 (報告不要): tasks/step3-checkpoint-fixes / step3-bughunt-fixes / bughunt2〜bughunt11 (R12 開始時は
`ls tasks/step3-bughunt*` と各見出しを確認) と、docs で Step4/Phase4+/v2+ と明記の未実装。過去の鉱脈
(並行/異常系、秘匿漏出/パス/資源、検索境界/入力堅牢性、シリアライズ往復/permission、エンコーディング境界
NUL/UTF-16/BOM/crash-atomicity/task lifecycle、未束縛 approval の秘匿 online 送信、budget/cost-ledger 会計、
検索"内容"の NFC/NFD、embedding 応答検証、非アトミック writer、破損 JSONL が repair をブリック、引数検証、
schema future 互換、ルーティング意味論、ignore の NFC/NFD・case・config-key drift ([scope]/top-level/[search])、
ベクトル KNN の sqlite-vec 規模上限、task retry 予算・error kind・unit-scope 会計、派生 cache の crash-atomicity、
Agent/JSON 契約 (clap bypass・exit 5/6・exit 3 対称性・index_status 開示)、非トランザクション/O(N²) の規模劣化) は
掘り尽くし気味 — 新しい鉱脈の方が期待値が高い (R12 候補):
  - config/schema 全 key の配線突合 (R10-2/R11-7 の型の残り: config.schema.json・docs/05 に有効な key で
    実装が読まないもの。※top-level ignore=R10-2・[search] default_mode/fail_behavior=R11-7・
    multi_scope parallelism/timeout=MULTI-006 既知据え置き — それ以外の全 key)
  - observability JSONL の網羅性 (events.jsonl / errors.jsonl / search log が全コマンドの成功/失敗/partial 経路で
    append されるか、redaction が message/context 両面で一貫か。※N3/P4/R9-7 の個別修正は既知、系統監査は未)
  - リソース/GC の残り (open cache 増殖、chunks.jsonl / chunk_vec の config 変更・旧 gen 蓄積、scope-registry 成長。
    ※cache permission=R9-3・cache atomicity=R10-6・.tmp 残留=R9-8 は既知)
  - 検索品質の縁 (RRF/MMR の tie-break 決定性、cursor 再開の順序安定性、limit/offset 境界の重複/欠落)
  - DAG/Evidence の残り (tag→commit→tree の縁、shallow 境界での縮退。※cross-snapshot 解決・書込順は R10 Spark で健全確認済み)
  - 時刻/TZ の残り (DST/閏の境界、秒精度での順序・tie-break)
  - 並行性の残り (R11 で入った集約 writeback (R11-5)・tx 化 (R11-4)・exit override 経路と並行 batch/search の相互作用)
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
別脈 (Agent/JSON 契約) から major 7 件=範囲限定の盲点をフルスコープが補完する R9-1 パターンの再現)。
**次ラウンド R12 は別の焦点に回すこと**。**下記は R12 用に書き換え済み** (config 全 key 配線突合 + observability JSONL 網羅性。
R10-2/R11-7 で 2 連続した config-key drift の型を系統掃討で締め、未正面監査の observability を掘る。R13 以降ではまた別焦点に):

```
あなたは KCS (開発者自身のリポジトリ) の焦点セキュリティ監査人です。出荷前の防御的セキュリティ監査。
範囲限定 (丸読み禁止、grep/sed/rg のみ)。リポジトリのファイル変更禁止。ネットワーク不要。
今回 (R12) の焦点は 2 つ。過去 (R11=SQL規模境界+task会計、R10=DAG/Evidence、R9=パス正規化+リソース) とは別。

検証1 (config/schema 全 key の配線突合 — R10-2/R11-7 型の系統掃討): まず
`sed -n '1,200p' crates/kcs-core/schemas/config.schema.json` と `grep -n '^[a-z_]* =\|^\[' docs/05-runtime.md` で
schema/docs 上有効な全 config key を列挙し、各 key ごとに `rg -n '"<key>"|\.<key>\b' crates/` で実装の読取箇所を突合せよ。
(a) schema/docs に存在するが実装がどこからも読まない key (silent 受理→無視。※top-level ignore=R10-2、
    [search] default_mode/fail_behavior=R11-7、[search.multi_scope] parallelism/per_scope_timeout_seconds=MULTI-006
    既知据え置き — それ以外の全 key)、(b) 読むが片側のみ (scope config は読むが user config を読まない等、
    優先順位 docs/05 §2 との不一致)、(c) 値検証が schema と実装で食い違う key (enum 範囲・型・default)、を
    key 名 + file:line で挙げる。

検証2 (observability JSONL の記録網羅性と redaction 一貫性): `rg -n 'events\.jsonl|errors\.jsonl|append_search_logs|append_event|append_error|redact' crates/kcs-cli crates/kcs-core` から、
(a) コマンド成功/失敗/partial の各経路で events/errors への append が漏れる箇所 (特に R11 で追加された
    __exit_code 3/5/6 経路・clap try_parse エラー経路・enrichment 失敗経路)、(b) redaction (N3/P4 で修正済みの
    message/path) が新規フィールド (context 内・warning・embedding_tasks_* 等) に及んでいない箇所、
    (c) append 失敗自体がコマンドを fail させる/黙殺される非一貫、を file:line で挙げる。

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
→ **11 ラウンドとも完全に別の鉱脈から実バグ。契約テストが全 green でも探索型は毎回新規を出す。
かつフィックスも実機フルサイクル再検証しないと不完全なことがある (R5 Q1・R8 F8・R10-1 の e2e 置換をオーケストレータが再実行)。範囲限定 Spark の
「問題なし」領域からフルスコープエンジンが major を出す (R9-1・R11 で再現)、オーケストレータの検証フェーズ自体が発見装置になる (P10・R9-5) パターンも定着。
かつ Spark の焦点が「掘り尽くした脈の健全性確認」に着地しても (R10 の DAG/Evidence、R11 の規模境界+task会計)、フルスコープが別脈で major を出せば全体は前進する。**
