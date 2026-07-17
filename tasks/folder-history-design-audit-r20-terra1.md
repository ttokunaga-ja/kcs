不合格
target.md 全 3348 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

第 1 部 — 回帰確認 (C9)

対象: A01〜A24、B01〜B18、D01〜D14、E01〜E06、F01〜F27、G01〜G02、H01〜H30、I01〜I38、J01〜J20、K01〜K26、L01〜L28、M01〜M29、N01〜N45、O01〜O30、Q01〜Q37、R01〜R29、S01〜S29、T01〜T18、U01〜U24、V01〜V20（全 494 項目）。

fixed: 下記 superseded 項目および V09 を除く全 ID。

superseded:
- A01→K25、A11→I05/I06/I13/I14、D08→K20
- F05→I14、F07→I15、F12→I16/I17、F21→I03/I04
- H02→I32、H04→I31、H15→I08/I11、H18→I16、H22→I15
- I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I12→K04、I15→J04、I16/I17→J05/J01、I35→J13〜J16
- J03→K10、J04→K01、J06→K02、J07→L09、J10→K09、J13→K16、J16→K13〜K15
- K02→L01、K06→L02、K08→N17、K09/K11→L03、K12/K13→L04、K14→L07、K19→L13、K21→L20、K24→L09
- L04/L21→M02、L07/M05→N16、L09/L28→M03、L20→M04、L26→N14
- M01→N09、M06→N17、M08→N28、M09→N05、M10→N10、M12→N38、M13→N30、M29→N15
- N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N23→V05、N28→O13、N36→O16、N39→O14、N40→O28
- O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37
- Q02→R01、Q03→R05、Q04→R02、Q05/Q06→R06、Q06→R07、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16
- R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06
- S06→T09、S07→T05/T06、S11→T07、S19→T03、S20→T01、S23→T18、S24→T02、S25→T04
- T03→U04、T08→U03、T10→U01、T11→U05、T16→U02
- U01→V01、U03→V07、U06→V02、U11→V04、U24→V03

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
|---|---|---|
| V09 | not-fixed | §9.1 の `scan_cache` DDL は `verified_at` の直後に `PRIMARY KEY` となっており、`syntax_fail_count` と `first_failure_at` が無い。一方 §20.5 は「**scan_cache に永続化する**」「`syntax_fail_count / first_failure_at` を記録」と規定する。DDL と規範が両側で不一致。 |

第 2 部 — 探索ログ (C12)

| # | 観点 | シナリオ | 結果 |
|---:|---|---|---|
| 1 | X1 | 作成→編集→削除を 1 tick 内で実施→LWW 生存集合から delete を確定 | 問題なし |
| 2 | X2 | 本文に偽 img grammar・制御的な名前を投入→行頭 escape、厳密認識、name_invalid を適用 | 問題なし |
| 3 | X3 | NFD 名・case-only 名を別ボリュームへ移動→NFC resolver と保存名固定で照合 | 問題なし |
| 4 | X4 | 時計後退・同一 ms の複数 commit→created_at clamp と hash tie-break を適用 | 問題なし |
| 5 | X5 | 10 万ファイル・100 万 chunk を仮定→fp、fts_cap、k_fetch 上限で経路を追跡 | 問題なし |
| 6 | X6 | 2 文字 query・vec profile 変更・巨大整数を入力→LIKE fallback、template、文字列表現を確認 | 問題なし |
| 7 | X7 | migration 中に旧 writer が起動→tick.lock 後の user_version 再確認で遮断 | 問題なし |
| 8 | X8 | `../`・symlink・root swap を含む restore を試行→name 検証と dirfd 相対操作を適用 | 問題なし |
| 9 | X9 | objects 保存後、metadata Tx 後、app 更新前に順次クラッシュ→次 tick の収束を追跡 | 問題なし |
| 10 | X10 | `.folder-history` 手動削除・コピー衝突を発生→damaged/conflict 分岐を追跡 | 問題なし |
| 11 | X11 | floor 設定中に profile 変更・再チャンク・reconcile を交錯→floor の app→metadata 順を確認 | 問題なし |
| 12 | X12 | watch_root→scan→commit→OCR→chunk→embed→replicate→検索→restore を通し実行 | 問題なし |
| 13 | X13 | status、明示 retry、abandon、drop-derivation を列挙→入力・失敗時帰結を確認 | 問題なし |
| 14 | X14 | submit/collect の 429、cache 増加、fp 孤児を発生→backoff と M&S を追跡 | 問題なし |
| 15 | X15 | 主張「intent 回復で未追跡 job は有界」→相 2b 後・相 3 前クラッシュ→token 照合 | 問題なし |
| 16 | X16 | 2 相 submit 中の profile 切替、upload 残骸、reconcile を交錯 | 問題なし |
| 17 | X17 | register・fork・restore・unregister の各途中クラッシュから再実行 | 問題なし |
| 18 | X18 | profiles 欠損、pending delete、app 全損後 ledger の各読取を追跡 | 問題なし |
| 19 | X19 | tmp、objects、migration、submit 各境界で電断 | 問題なし |
| 20 | X20 | 主張「宣言的 profile 変更は収束」→vec 作成途中で中断→差集合再充填 | 問題なし |
| 21 | X21 | 相 1 snapshot、floor、agg ready の更新を同一 tick で交錯 | 問題なし |
| 22 | X22 | fork の journal/flag/old-new ID を各 phase で再開 | 問題なし |
| 23 | X23 | detached、name_collision、app_config、ledger の各 status を読取側へ伝播 | 問題なし |
| 24 | X24 | 主張「vec 差集合が半端な作成を回復」→CREATE 後に中断→次 tick を実行 | 問題なし |
| 25 | X25 | app.sqlite 単独横断検索、restore 宛先、watch_root 解除後の walk を追跡 | 問題なし |
| 26 | X26 | attempts/submission_seq/ledger と client 前計上を反復 | 問題なし |
| 27 | X27 | fork journal を PREPARED〜APP_DONE の境界で破損・移動 | 問題なし |
| 28 | X28 | detached の state 0/1/2/3 と再登録を全て追跡 | 問題なし |
| 29 | X29 | case-sensitive→insensitive 移動と保存名固定を追跡 | 問題なし |
| 30 | X30 | 主張「seq 継承で UNIQUE 衝突なし」→削除・再登録・再投入を実行 | 問題なし |
| 31 | X31 | submission_seq 継承、reconcile close、submit_rejected を交錯 | 問題なし |
| 32 | X32 | fork phase × app 全損 × journal 破損を全数分岐 | 問題なし |
| 33 | X33 | server/client × 終端理由 × close 経路の ledger 行数を追跡 | 問題なし |
| 34 | X34 | selected_files、eligible、RRF、ready 不一致時 FTS-only を追跡 | 問題なし |
| 35 | X35 | 主張「detached は記帳を失わない」→取消・期限超・再登録を実行 | 問題なし |
| 36 | X36 | profile A→B→A と ON CONFLICT DO NOTHING を交錯 | 問題なし |
| 37 | X37 | missing/fork/damaged の出入り中に ready 母数を再計算 | 問題なし |
| 38 | X38 | journal 移動、flag 残留、HISTORY_CLEARED の非空 commits を追跡 | 問題なし |
| 39 | X39 | 一時 EIO、別 id 再利用、raw resolver、unregister を交錯 | 問題なし |
| 40 | X40 | 主張「query hash 固定で TOCTOU 回避」→embed 中の profile 更新を実行 | 問題なし |
| 41 | X41 | 全 terminal 理由の ledger 記帳を server/client で照合 | 問題なし |
| 42 | X42 | damaged 復帰・接続 0→1 の ready 更新を追跡 | 問題なし |
| 43 | X43 | NFC/NFD・collision・raw 不在を delete/restore/fsck で比較 | 問題なし |
| 44 | X44 | standalone read、conflict、step -1 unreadable を追跡 | 問題なし |
| 45 | X45 | 主張「raw resolver は二重実体を作らない」→NFD 実体への restore を実行 | 問題なし |
| 46 | X46 | token 記帳と job-id 記帳を同一 lifecycle で再観測 | 問題なし |
| 47 | X47 | 期限超 Tx の各境界でクラッシュ→rotation と attempts を追跡 | 問題なし |
| 48 | X48 | restore 保全 commit 後、外部編集と rename 前照合を交錯 | 問題なし |
| 49 | X49 | 全 §21 操作の前に fork 回復を実施→入力状態を確認 | 問題なし |
| 50 | X50 | 主張「sweep が (b') を回収」→close 後クラッシュ→sweep 再実行 | 問題なし |
| 51 | X51 | seq 行 UPDATE、found 記帳、client 前計上を連続実行 | 問題なし |
| 52 | X52 | expired 行の retry、token sweep、unregister を交錯 | 問題なし |
| 53 | X53 | intent 回復・detached・(b')・sweep の 4 照合点を比較 | 問題なし |
| 54 | X54 | journal 有無×flag 有無×実体 ID の全分岐を追跡 | 問題なし |
| 55 | X55 | 単独検索で embedding 混在と tool 混在を同時発生 | 問題なし |
| 56 | X56 | `\![...](obj:...)` の非 canonical 行を escape/un-escape | 問題なし |
| 57 | X57 | found 記帳後の自己記述化と sweep 再訪を追跡 | 問題なし |
| 58 | X58 | detached terminal 化後に同 repository を再登録 | 問題なし |
| 59 | X59 | 課金される submit_rejected と token sweep 除外を追跡 | 問題なし |
| 60 | X60 | G / `\G` / `\\G`、実在・非実在 object を往復 | 問題なし |
| 61 | X61 | 主張「伝播猶予で二重 job 回避」→遅延可視化を模擬 | 問題なし |
| 62 | X62 | job_create_started_at 記録後・呼出前クラッシュを反復 | 問題なし |
| 63 | X63 | cancelled 行の明示 retry→再 cancel→cleanup を追跡 | 問題なし |
| 64 | X64 | token 推定記帳後に別 attempt の job を found として観測 | 問題なし |
| 65 | X65 | no-replace 非対応 FS、EEXIST、fallback の順序を追跡 | 問題なし |
| 66 | X66 | 規範・要約・SQL・DDL コメントの detached/FTS/key 再掲を照合 | 問題なし |
| 67 | X67 | token 残存 terminal 行を再投入し、sweep unknown を継続 | 問題なし |
| 68 | X68 | cancel→retry→cancel と token/upload cleanup を交錯 | 問題なし |
| 69 | X69 | fts_cap/k_fetch 到達時の RRF 順位と不足返却を追跡 | 問題なし |
| 70 | X70 | Office 変換失敗、tool 変更、変換後 oversize を追跡 | 問題なし |
| 71 | X71 | state=0 載せ直しと client dispatch の token 処理を追跡 | 問題なし |
| 72 | X72 | abandon 後に遅延 job が found、次 retry を実行 | 問題なし |
| 73 | X73 | convert_failed の旧 tool 行と新 tool target_key を分離 | 問題なし |
| 74 | X74 | 同一 stat tuple の構文検証失敗を 3 回/24h 記録→`scan_cache` へ必須列を書込 | W01 を検出 |
| 75 | X75 | scope_id 記録後の workspace 変更・NULL legacy 行を照合 | 問題なし |
| 76 | X76 | abandoned 行の削除・再登録・後日 found を順に追跡 | 問題なし |
| 77 | X77 | fp 一致の登録フォルダへ fork-journal だけを作成 | 問題なし |
| 78 | X78 | state=2・token 残存行へ floor を設定して guard を通過 | 問題なし |
| 79 | 自由 | app.sqlite 全損→profiles/filter/watch_root を再入力→再発見・再集約 | 問題なし |

第 3 部 — 新規検出 (C1〜C8, C10, C11, C12)

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| W01 | major | §9.1 `scan_cache` DDL は `verified_at` 後に `PRIMARY KEY`。§20.5 は「**scan_cache に永続化する**」「`syntax_fail_count / first_failure_at` を記録」。 | 有界な構文検証スキップの永続化に必要な列がスキーマに無く、規範を実装できない。 | 初期状態: 掲載 DDL で app.sqlite を作成。→ 同一 `(size,mtime_ns,inode)` のファイルが構文検証に失敗。→ 規範どおり失敗回数と初回時刻を保存しようとすると列不存在で失敗し、保存を省略すると再起動ごとに回数が戻り、3 回/24h の上限が成立しない。 | P16 / C1 / C2 / C4 / C8 / C11 / C12-X74 | `scan_cache` に `syntax_fail_count` と `first_failure_at` を追加し、初期値・reset・既存 DB migration を §9.1 と §14 に同時に明記する。 |

第 4 部 — 確認済みの列挙

検出 0 件: C3、C5、C6、C7、C10。

確認済み: P1、P2、P3、P4、P5、P6、P7、P8、P9、P10、P11、P12、P13、P14、P15。