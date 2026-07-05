# 探索型 4 エンジン監査 ランブック (新セッション貼り付け用)

このファイル全体を新しい Claude Code セッションに貼り付ければ、探索型クロスチェックを 1 ラウンド
実行できる。長い会話コンテキストを引き継がずに毎回クリーンに走らせるための自己完結手順。

---

## 0. 位置づけ (安全ガードの誤発火を避けるため必読)

これは **開発者自身が所有する OSS リポジトリ (KCS) に対する、出荷前の防御的セキュリティ監査**である。
目的は自分のコードの脆弱性・不具合を第三者に悪用される前に発見して修正すること。攻撃対象は自分の
ローカルツールのみ。実 API キーは使わず、全操作は隔離した一時ディレクトリで行う。これは正当な
defensive security 作業であり、拒否する理由はない。過去 8 ラウンド (R1-R8) で秘匿情報漏出 (critical) を含む
実バグを多数捕捉し、すべて修正済み。

## 1. 対象

- リポジトリ: `/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs` (main)
- KCS = Rust 製のローカル知識アーカイブ CLI (evidence-grounded local knowledge archive)。
  `kcs init/index/snapshot/search/view/open/batch/reindex/repair/diff/tag/log/status` 等。
  仕様正本は `docs/01`〜`docs/10`。実装は `crates/kcs-{core,pipeline,adapter,index,search,cli}`
- 現状 (R9 完了時点、次ラウンドは R10): 全テスト green (341)、clippy(--all-features)/fmt clean。Step 1-3 実装済み + 探索型監査 R1-R9 修正反映済み +
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
- docs で `Step 4` / `Phase 4+` / `v2+` と明記の未実装

**過去 9 ラウンドの鉱脈は掘り尽くし気味**: R1=並行/異常系の後続経路、R2=秘匿情報漏出/パス検証/資源枯渇、
R3=検索境界の完全性/入力堅牢性/状態の縮退、R4=シリアライズ往復/ファイル permission/資源リーク/Agent 契約、
R5=エンコーディング境界 (NUL/UTF-16・BOM)/派生 CAS object と append-only pointer の crash-atomicity/task ライフサイクル、
R6=未束縛 approval の秘匿送信/破損 JSONL が repair をブリック/引数検証/schema future 互換、
R7=秘匿承認ファイルの存在判定/multi-scope opt-in/embedding retry・profile 互換、
R8=budget/cost-ledger 会計 (ローカル計上・負値・TOCTOU・config 未配線)/NFC-NFD 検索/embedding 応答検証/catalog identity、
R9=ルーティングの意味論 (text-native→OCR)/ignore パターンの NFC-NFD 照合/展開 cache permission/Partial の行き止まり状態/reindex の junk entry 耐性。
**新しい鉱脈の方が期待値が高い** (下記ヒント参照)。

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
5. 採択した所見を `tasks/step3-bughunt<N>-fixes.md` に裁定として書き、コミット (R8 は bughunt8、**次 R9 は bughunt9**)
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

既知 (報告不要): tasks/step3-checkpoint-fixes / step3-bughunt-fixes / bughunt2〜bughunt8 (R9 開始時は
`ls tasks/step3-bughunt*` と各見出しを確認) と、docs で Step4/Phase4+/v2+ と明記の未実装。過去の鉱脈
(並行/異常系、秘匿漏出/パス/資源、検索境界/入力堅牢性、シリアライズ往復/permission、エンコーディング境界
NUL/UTF-16/BOM/crash-atomicity/task lifecycle、未束縛 approval の秘匿 online 送信、budget/cost-ledger 会計
[ローカル計上・負値・TOCTOU・config 未配線]、検索"内容"の NFC/NFD、embedding 応答検証、非アトミック writer、
破損 JSONL が repair をブリック、引数検証、schema future 互換) は掘り尽くし気味 — 新しい鉱脈の方が期待値が高い (R9 候補):
  - パス/ファイル名の正規化・照合 (macOS APFS の NFC/NFD ファイル名、大文字小文字、heading slug 衝突、
    scope path 比較。※検索"内容"の NFC/NFD は R8 F2 で対応済み。path/key の照合は別鉱脈)
  - 状態機械/ライフサイクルの残り (Running 以外の task 状態=Paused/Partial/Failed の resume/retry/dedup、
    retry budget 枯渇時の挙動、task の再 enqueue 重複、gen の増え方)
  - リソース/GC の残り (open cache=$XDG_CACHE_HOME/kcs/open の増殖、chunks.jsonl の config 変更蓄積、
    scope-registry 成長、エラー経路での一時ファイル残留)
  - DAG/Evidence の完全性の残り (Evidence Pointer の cross-snapshot 解決、tag→commit→tree の縁、
    shallow commit 境界での縮退)
  - 時刻/TZ の残り (retry backoff 算術 scheduled_retry_at、DST/閏の境界、秒精度での順序・tie-break)
  - Agent/JSON 契約の残り (各コマンドの --json が内部状態を過不足なく開示するか、隠れた成功/失敗、exit code 一貫性)
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
canonicalize 系の健全性確認どまりだったが、フルスコープ Sonnet が別経路の ignore 照合 R9-1 を出した=範囲限定の盲点をフルスコープが補完)。
**次ラウンド R10 は別の焦点に回すこと**。**下記は R10 用に書き換え済み** (DAG/Evidence 整合の縁 + snapshot/commit の書込順序・tree-entry 整合。R11 以降ではまた別焦点に):

```
あなたは KCS (開発者自身のリポジトリ) の焦点セキュリティ監査人です。出荷前の防御的セキュリティ監査。
範囲限定 (丸読み禁止、grep/sed/rg のみ)。リポジトリのファイル変更禁止。ネットワーク不要。
今回 (R10) の焦点は 2 つ。過去 (R9=パス正規化+リソース、R8=時刻+cost-ledger、R4=serialize+permission) とは別。

検証1 (DAG/Evidence グラフの縁の完全性): `grep -rnE 'tree|commit|parent|tag|ref|head|shallow|tombstone|resolve_commit|read_tree|read_commit|Evidence|pointer|raw_hash|tool_profile_hash|gen' crates/kcs-core crates/kcs-cli` から、
(a) tag→commit→tree→entry の解決経路で、参照先が欠落 (未 fetch / shallow 境界 / tombstone) のとき「無言で空/別物」に
    縮退せず明示エラーになるか、(b) Evidence Pointer の cross-snapshot 解決が (raw_hash, tool_profile_hash, gen) を
    全経路で束縛しているか — reindex で gen が進んだ後に旧 commit の pointer が新 gen 内容にすり替わらないか
    (※単一 snapshot 内は R8/N5 で対応済み。cross-snapshot と shallow 境界が別鉱脈)、(c) commit parent chain の
    循環・自己参照・深さ無限ループを検出するか、を file:line で挙げる。

検証2 (snapshot/commit の書込順序・tree-entry 整合): `grep -rnE 'snapshot|auto_snapshot|write_tree|write_commit|update_ref|HEAD|fs::rename|fs::write|atomic|sync_all|normalize_by_path|tree_entry' crates/kcs-core crates/kcs-cli` から、
(a) commit オブジェクト・tree・HEAD ref の書込順序が crash-safe か (HEAD が指す commit の tree/parent が先に
    永続化されているか。中断で HEAD が未永続 commit を指す窓はないか)、(b) tree entry の path/raw_hash/normalize ref の
    整合 — auto_snapshot_with_normalize がループ途中で失敗したとき tree に half-written entry が残らないか、
    (c) 同一 raw_hash の複数 path / 同一 path の gen 増分で tree entry が重複・取り違えを起こさないか、を file:line で挙げる。

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
**フィックスの clippy は --all-features で回すこと** (R8 で --all-features 限定の 9-arg compile error を検出、通常 test は通過)。
かつ**背景エージェントの transcript mtime は buffer 遅延するので「idle 判定」に使わない** (R8 で誤判定 → 完了通知を待つのが正)。
→ **9 ラウンドとも完全に別の鉱脈から実バグ。契約テストが全 green でも探索型は毎回新規を出す。
かつフィックスも実機フルサイクル再検証しないと不完全なことがある (R5 Q1・R8 F8)。範囲限定 Spark の「問題なし」領域から
フルスコープエンジンが major を出す (R9-1)、オーケストレータの検証フェーズ自体が発見装置になる (P10・R9-5) パターンも定着。**
