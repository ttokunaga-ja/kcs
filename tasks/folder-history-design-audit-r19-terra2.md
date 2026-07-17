不合格
target.md 全 3284 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第1部 — 回帰確認（C9）

A01〜A24、B01〜B18、D01〜D14、E01〜E06、F01〜F27、G01〜G02、H01〜H30、I01〜I38、J01〜J20、K01〜K26、L01〜L28、M01〜M29、N01〜N45、O01〜O30、Q01〜Q37、R01〜R29、S01〜S29、T01〜T18、U01〜U23は fixed または指定対応表どおり superseded。

superseded（→後続項目）: F05→I14、F07→I15、F12→I16/I17、F21→I03/I04、H04→I31、H15→I08/I11、H18→I16、H22→I15、A11（遷移詳細）→I05/I06/I13/I14、H02（衝突順）→I32；I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I15→J04、I16/I17→J05/J01、I35→J13〜J16；J04→K01、J06→K02、J03→K10、J10→K09、J13→K16、J16→K13〜K15、I12→K04、D08→K20、A01→K25；K02→L01、K06→L02、K09→L03、K12/K13→L04、K14→L07、J07/K24→L09、K19→L13、K21→L20；L09/L28→M03、L20→M04、L04/L21→M02；M09→N05/N06、M10→N10、M12→N38、M29→N15、M06/K08→N17、L07/M05→N16、L26→N14、M01→N09、M08→N28、M13→N30；N03→O05/O06、N04→O02/O03、N13→O21、N15→O04/O25、N36→O16、N39→O14、N40→O28、N28→O13、N07→O12；O28→Q01、O17→Q02、O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O18→Q23、O19→Q24、O13→Q12、O30→Q37；Q02→R01、Q04→R02、Q09→R03、Q12→R04、Q03→R05、Q05/Q06→R06、Q06（sweep除外）→R07、Q10→R14、Q13/Q14→R15/R16；R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06；S06→T09、S07→T05/T06、S11→T07、S19→T03、S20→T01、S23→T18、S24→T02、S25→T04；T03→U04、T08→U03、T10→U01、T11→U05、T16→U02。

| ID | 判定 | 根拠（§ + 短い引用） |
|---|---|---|
| U24 | partially-fixed | §21.3 の再開表は「`phase = ID_WRITTEN : 手順 3 から`」「`phase = APP_DONE : 手順 4`」と marker の実 ID を照合せず通過させる。一方、fail-closed は「`実体の id が old / new のいずれでもない`」だけであり、`ID_WRITTEN + id=old`、`APP_DONE + id=old`、`PREPARED + id=new` を捕捉しない。 |

## 第2部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---|---|---|---|
| 1 | X1 | 初期: 現在版A → 同一 tick 内で作成・更新・削除 → LWW と pending delete を追跡 | 問題なし |
| 2 | X2 | 初期: 偽 img block、制御文字名、0 byte → canonical parser・name 検証へ投入 | 問題なし |
| 3 | X3 | 初期: NFD 名・case-insensitive volume → sensitive volume へ移動 → resolver と系列を追跡 | 問題なし |
| 4 | X4 | 初期: 時計後退・同一 ms の複数 commit → created_at clamp と hash tie-break を適用 | 問題なし |
| 5 | X5 | 初期: 大量 chunks・候補集合 → FTS cap、KNN refill、差集合同期を適用 | 問題なし |
| 6 | X6 | 初期: 大きい size、profile 変更、Batch 分割 → JCS・target_key・vec template を追跡 | 問題なし |
| 7 | X7 | 初期: 旧 schema／旧 img grammar → migration・v 判定・全量再 materialize を実行 | 問題なし |
| 8 | X8 | 初期: traversal 名・symlink・他者可読 tmp → root dirfd・O_NOFOLLOW・権限規範を適用 | 問題なし |
| 9 | X9 | 初期: object 欠損・metadata 単独復元 → fsck・z 判定・backup 規範を追跡 | 問題なし |
| 10 | X10 | 初期: 手動削除・同期途中コピー → damaged/conflict と fail-closed 分岐を追跡 | 問題なし |
| 11 | X11 | 初期: floor 設定済み派生 → filter 変更・再チャンク → app→metadata 順を確認 | 問題なし |
| 12 | X12 | 初期: watch_root 登録 → OCR → embed → replicate → 検索 → restore | 問題なし |
| 13 | X13 | 初期: terminal、damaged、conflict、drop 対象 → §21 の明示操作参照を追跡 | 問題なし |
| 14 | X14 | 初期: 429・fp_cache 孤児 → retry_not_before と M&S を適用 | 問題なし |
| 15 | X15 | 主張: phantom block を防ぐ → 偽 grammar 行・object 不在を投入 | 問題なし（破れず） |
| 16 | X16 | 初期: upload 成功後 job 作成失敗 → 相2a記録・cleanup・intent 回復を追跡 | 問題なし |
| 17 | X17 | 初期: register 中断・fork 後・restore → lock と回復順を追跡 | 問題なし |
| 18 | X18 | 初期: profile 行破損・pending delete → fsck repair と状態掃除を追跡 | 問題なし |
| 19 | X19 | 初期: objects / metadata / app の各書込境界で電断 → 次 tick を追跡 | 問題なし |
| 20 | X20 | 主張: server 重複課金は有界 → 相1〜相3境界を反復クラッシュ | 問題なし（破れず） |
| 21 | X21 | 初期: profile 変更と floor → requeue・generated_at・agg 再構築を追跡 | 問題なし |
| 22 | X22 | 初期: fork phase ごとの crash → journal・flag・規約12抑止を追跡 | U24を検出 |
| 23 | X23 | 初期: cost_ledger、detached、name_collision → 各 reader の状態分岐を追跡 | 問題なし |
| 24 | X24 | 主張: vec 差集合で部分充填を回復 → CREATE 後クラッシュ → 次 tick | 問題なし（破れず） |
| 25 | X25 | 初期: app.sqlite 単独検索・restore 宛先・watch_root 解除 → 入出力を追跡 | 問題なし |
| 26 | X26 | 初期: 行削除後の再登録 → seq 継承・close 記帳・snapshot を追跡 | 問題なし |
| 27 | X27 | 初期: fork journal 各 phase → app 全損・移動・再発見を追跡 | U24を検出 |
| 28 | X28 | 初期: detached の state 0/1/2/3 → collect・sweep・削除を追跡 | 問題なし |
| 29 | X29 | 初期: case-only rename と volume 移動 → 保存名固定・resolver を追跡 | 問題なし |
| 30 | X30 | 主張: seq 継承と detached は安全 → 再登録・終端・再投入を追跡 | 問題なし（破れず） |
| 31 | X31 | 初期: reconcile close と client 再実行 → seq・floor・ledger を追跡 | 問題なし |
| 32 | X32 | 初期: journal=`ID_WRITTEN`、marker=old_id → 回復表に従い step 3 → flag/journal を削除 | U24を検出 |
| 33 | X33 | 初期: server/client × 終端理由 → ledger 行数と seq を照合 | 問題なし |
| 34 | X34 | 初期: current/過去/時点検索 → eligible、LIKE、RRF、KNN gate を追跡 | 問題なし |
| 35 | X35 | 主張: fork は任意 crash から再開 → `APP_DONE + old_id` を与える | U24を検出 |
| 36 | X36 | 初期: profile A→B→A、detached 採用 → ON CONFLICT と seq を追跡 | 問題なし |
| 37 | X37 | 初期: missing/damaged/fork の出入り → synced/ready を追跡 | 問題なし |
| 38 | X38 | 初期: HISTORY_CLEARED 後の移動 → journal 回復と実 ID を追跡 | U24を検出 |
| 39 | X39 | 初期: 一時読取不能・別 id root → register/rebind/delete 判定を追跡 | 問題なし |
| 40 | X40 | 主張: ready と raw resolver は安全 → 破損・同名衝突を投入 | 問題なし（破れず） |
| 41 | X41 | 初期: server/client の全終端 → 記帳済み判別と seq を照合 | 問題なし |
| 42 | X42 | 初期: 接続母数が 0→1、damaged 復旧 → ready 遷移を追跡 | 問題なし |
| 43 | X43 | 初期: NFC/NFD/raw 無し/collision → 3 resolver 呼出点を追跡 | 問題なし |
| 44 | X44 | 初期: registered/standalone read と z unreadable → status 分岐を追跡 | 問題なし |
| 45 | X45 | 主張: unknown は二重 job を作らない → 一覧失敗・再照会を反復 | 問題なし（破れず） |
| 46 | X46 | 初期: token 記帳→found→sweep 再訪 → 述語と seq を追跡 | 問題なし |
| 47 | X47 | 初期: 期限超 token → 記帳・attempt 消費・rotation → retry | 問題なし |
| 48 | X48 | 初期: in-place restore 前に未取込変更 → 保全 commit・再 lstat を追跡 | 問題なし |
| 49 | X49 | 初期: 未完 fork のまま unregister/restore → 回復先行を追跡 | U24を検出 |
| 50 | X50 | 主張: token 記帳と restore 保全は安全 → close crash・上書きを試行 | 問題なし（破れず） |
| 51 | X51 | 初期: 無 id 記帳・found・client 前計上が交錯 → seq を追跡 | 問題なし |
| 52 | X52 | 初期: expired token、sweep 未完、明示 retry → 削除ガードを追跡 | 問題なし |
| 53 | X53 | 初期: 4 照合点の found/unknown/absent → 時刻・記帳・掃除を比較 | 問題なし |
| 54 | X54 | 初期: 有効 journal と `ID_WRITTEN + old_id` → 回復表を実行 | U24を検出 |
| 55 | X55 | 初期: tool/profile 混在 → 単独検索の current 決定を追跡 | 問題なし |
| 56 | X56 | 初期: G、`\G`、`\\G` → escape/un-escape/認識を順に適用 | 問題なし |
| 57 | X57 | 初期: found 記帳後にクラッシュ → dispatch・sweep・自己記述化を追跡 | 問題なし |
| 58 | X58 | 初期: detached terminal 後に再登録 → token cleanup と再投入を追跡 | 問題なし |
| 59 | X59 | 初期: 課金される submit_rejected → seq+1 記帳・sweep 除外を追跡 | 問題なし |
| 60 | X60 | 初期: 非 canonical 行・object 不在 → decoder と厳密認識を比較 | 問題なし |
| 61 | X61 | 主張: provider 条件下で期限超は安全 → delay/retention 境界を試行 | 問題なし（破れず） |
| 62 | X62 | 初期: 長い upload 後に job 呼出 crash → job_create_started_at 起点を追跡 | 問題なし |
| 63 | X63 | 初期: cancel→retry→再 cancel → attempts、ledger、token を追跡 | 問題なし |
| 64 | X64 | 初期: token 推定記帳後に found → `IN(job_id, token)` 判別を追跡 | 問題なし |
| 65 | X65 | 初期: no-replace 非対応 volume → 再 lstat + fallback rename を追跡 | 問題なし |
| 66 | X66 | 初期: 規範・DDLコメント・SQL・要約を横断比較 → 制約伝播を確認 | 問題なし |
| 67 | X67 | 初期: state=3 token 残存 → sweep unknown→abandon/retry を追跡 | 問題なし |
| 68 | X68 | 初期: cancel 済み行を再登録・再 cancel → 記帳と削除条件を追跡 | 問題なし |
| 69 | X69 | 初期: FTS/KNN が cap 到達 → rank 打切りと結果決定性を追跡 | 問題なし |
| 70 | X70 | 初期: converter 更新・変換失敗・512MB超過 → tool key と preflight を追跡 | 問題なし |
| 71 | X71 | 初期: state=0 載せ直しと client dispatch → 旧 token の照合後 rotation を追跡 | 問題なし |
| 72 | X72 | 初期: explicit abandon 後に旧 job が可視化 → estimated 記帳と新 retry を追跡 | 問題なし |
| 73 | X73 | 初期: convert_failed 後に tool profile 変更 → 旧/new target_key を追跡 | 問題なし |
| 74 | X74 | 初期: 安定した構文不正ファイル → tick ごとの検証失敗・プロセス再起動・後の削除 | V01を検出 |

## 第3部 — 新規検出（C1〜C8、C10〜C12）

| ID | 重大度 | 該当箇所（§ + 短い引用） | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| V01 | fatal | §20.5「`同一 (size, mtime_ns, inode) のまま連続 3 回 (または 24 時間) 構文検証に失敗`」／§9.1 `scan_cache` は `content_hash` と `verified_at` まで | 有界スキップに必要な失敗回数・初回失敗時刻・stat tuple の永続的保持先、更新、リセット規則が無い。tick は非常駐なので、再起動を跨いで「3回または24時間」を実装できない。 | 初期: 安定したが構文検証に失敗する managed file。→ tick 1 でスキップ後にプロセス終了、同じ stat のまま tick を再実行。→ 回数は復元不能で、実装は無期限スキップまたは任意時点の commit に分岐する。無期限側で原本が削除されると objects / file_versions に一度も保存されず、復旧不能。 | P16 / C11 / C12 / X74 | scan_cache に stat tuple ごとの構文検証失敗回数・初回時刻を永続化し、成功・stat 変更・一時 I/O 失敗での reset 規則を明記する。一時読取失敗はカウントせず、閾値到達時のみ bytes を commit する。 |

## 第4部 — 確認済みの列挙

確認済み・問題なし: C2（SQLite DDL、FK、GENERATED 列、FTS5 external content / trigger）、C3、C4、C5、C6、C7、C8、C10。

確認済み・問題なし: P1〜P15。

検出あり: C1 の P16、C9（U24）、C11、C12。