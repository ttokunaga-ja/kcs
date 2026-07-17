不合格
target.md 全 3135 行を読了 — 最終行: 『```』

# 第1部 — 回帰確認（C9）

A01〜A24、B01〜B18、D01〜D14、E01〜E06、F01〜F27、G01〜G02、H01〜H30、I01〜I38、J01〜J20、K01〜K26、L01〜L28、M01〜M29、N01〜N45、O01〜O30、Q01〜Q37、R01〜R29、S01〜S29 のうち、下記 superseded 項目および S07・S20 を除く項目はすべて fixed。

superseded: F05→I14、F07→I15、F12→I16/I17、F21→I03/I04、H04→I31、H15→I08/I11、H18→I16、H22→I15、A11→I05/I06/I13/I14、H02→I32、I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I15→J04、I16/I17→J05/J01、I35→J13〜J16、J04→K01、J06→K02、J03→K10、J10→K09、J13→K16、J16→K13〜K15、I12→K04、D08→K20、A01→K25、K02→L01、K12/K13→L04、K06→L02、K09→L03、K14→L07、J07/K24→L09、K11→L03、K21→L20、K19→L13、L09→M03、L28→M03/M09、L20→M04、L04/L21→M02、M09→N05/N06、M10→N10、M12→N38、M29→N15、M06/K08→N17、L07/M05→N16、L26→N14、M01→N09、M08→N28、M13→N30、N03→O05/O06、N04→O02/O03、N13→O21、N15→O04/O25、N36→O16、N39→O14、N40→O28、N28→O13、N07→O12、O28→Q01、O17→Q02、O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O18→Q23、O19→Q24、O13→Q12、O30→Q37、Q02→R01、Q04→R02、Q09→R03、Q12→R04、Q03→R05、Q05/Q06→R06/R07、Q10→R14、Q13/Q14→R15/R16、R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06。

| ID | 判定 | 根拠（両側） |
| --- | --- | --- |
| S07 | partially-fixed | §9.1 DDL は `job_create_started_at`、相2b直前の小Tx、猶予起点、NULL時の未着手判定を備える。一方、§9.1 相1の新 intent 書込は「`batch_job_id` は NULL」「`error / completed_at` も NULL」と列挙するだけで、旧 `job_create_started_at` を NULL に戻さない。新 lifecycle で「NULL = 相2b未着手」の不変条件が成立しない（T01）。 |
| S20 | partially-fixed | §5.7 は「tool は `annotation_schema` 必須、embedding は `dimensions / metric` 必須、他 kind の必須フィールドを持つ record は拒否」とする。一方、§4.1 は tool/embedding 共通の `profile_record` を `{"v", "model", "annotation_schema", "options"}` と定義しており、embedding record も tool 必須フィールドを持つ形になっている（T04）。 |

# 第2部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
| ---: | --- | --- | --- |
| 1 | X1 | 履歴なし → 1 tick 間に作成・編集・削除 → 次 walk | 問題なし。観測時点で存在しない中間状態はコミットされない。 |
| 2 | X2 | 本文に `\![x](obj:…)`、偽 img block、symlink、hardlink → OCR保存・再解析 | 問題なし。緩い escape/un-escape と厳密画像認識、regular-file 判定が分担。 |
| 3 | X3 | NFD 名を持つフォルダを insensitive FS から sensitive FS へ移動 → 再発見 | 問題なし。NFC 論理名、raw resolver、移動先感度再判定が収束。 |
| 4 | X4 | 時計後退中に連続コミット、同一msの並行コミット → LWW/カーソル評価 | 問題なし。`latest+1` と commit_hash tie-break が機能。 |
| 5 | X5 | 10万ファイル・100万chunk → 定期walk・再チャンク・複製 | 問題なし。正しさは維持され、規模超過時の再検討境界も明示。 |
| 6 | X6 | 日本語2文字検索、JCS大整数、vec0次元変更 → 検索・再構築 | 問題なし。LIKE fallback、10進文字列、dim/metric検査が適用。 |
| 7 | X7 | 新版DBを旧アプリで開く、未知grammar vを再解析 | 問題なし。user_version fail-closed、未知v skip。 |
| 8 | X8 | `../x`・絶対パスの履歴行、緩いACL → restore/open | 問題なし。name_invalid と権限 fail-closed。 |
| 9 | X9 | object保存・metadata commit・app close の各直前でディスク満杯 | 問題なし。未参照objectまたは未close行に留まり、次tickが収束。 |
| 10 | X10 | `.folder-history` 手動削除、metadata部分置換、zip往復 | 問題なし。damaged/regressed/再hashへ分岐。 |
| 11 | X11 | NFC名、非正規化fp名、FTS view、preflight、floorを同時変更 | 問題なし。層間の変換点は分離済み。 |
| 12 | X12 | watch_root→commit→OCR→chunk→embed→replicate→検索→restore | 問題なし。各出力から次入力への受渡しを追跡可能。 |
| 13 | X13 | 「status」「明示retry」「明示再生成」「damaged解決」を全列挙 | 問題なし。§21と各参照先で入力・効果・失敗分岐を確認。 |
| 14 | X14 | Retry-Afterなし429、fp_cache肥大、DB空きページ増大 | 問題なし。既定backoff、M&S、incremental_vacuumが存在。 |
| 15 | X15 | 主張「objects→metadata順で参照欠損を防ぐ」→ object rename後、metadata前に電断 | 破れず。未参照objectだけが残る。 |
| 16 | X16 | 1 repoのJSONLを複数jobへ分割 → token回復・custom_id照合 | 問題なし。job単位tokenとrepo境界を維持。 |
| 17 | X17 | register途中クラッシュ→fork→restore→unregister→再登録 | 問題なし。journal、tick.lock、全量再同期で追跡可能。 |
| 18 | X18 | profile行改竄、pending_deletes途中喪失、app全損 | 問題なし。fsck修復、再カウント、bootstrap損失説明が一致。 |
| 19 | X19 | object rename、submit相1/2/3、fork各phaseで電断 | 問題なし。各耐久境界の再開先を確認。 |
| 20 | X20 | 主張「server未追跡jobは最大1」→ 5xx後に一覧可視化遅延 | 採用条件内では破れず。可視化上限・保持期間を満たさないproviderは明示的に対象外。 |
| 21 | X21 | profile Aのstate=2/attempts=2 → Bへ変更 → 相1クラッシュ | 問題なし。state非依存のattempts再計数とsnapshot更新が機能。 |
| 22 | X22 | fork PREPARED〜APP_DONE各境界でtick/unregisterを開始 | 問題なし。回復先行ゲートが後続操作を止める。 |
| 23 | X23 | app_config欠落、name_collision、detached、ledger NULL cost | 問題なし。読み手とstatusの分岐を確認。 |
| 24 | X24 | 主張「vec差集合は部分充填を収束」→ CREATE後半分でクラッシュ | 破れず。次tickの差集合が残りを補填。 |
| 25 | X25 | フォルダ未接続で横断検索、content_hash単独restore、watch解除 | 問題なし。FTS縮退、宛先必須、folders起点walkが定義済み。 |
| 26 | X26 | 相3・intent採用・client前計上を同じtargetで順次実行 | 問題なし。各外部実行にseqが一度だけ進む。 |
| 27 | X27 | journal各phase × app全損 × フォルダ移動 | 問題なし。phase/id/発見パスで再開可能。 |
| 28 | X28 | detached state 0/1/2/3 → collect・掃除 → 削除前に再登録 | 問題なし。再登録時の再課金は明示された意図的コスト。 |
| 29 | X29 | case-only rename、NFC衝突、sensitive→insensitive移動 | 問題なし。保存名固定と系列tie-breakが決定的。 |
| 30 | X30 | 主張「seq継承で再登録後もUNIQUE衝突しない」→ 行削除・再作成 | 破れず。ledger MAXから継承。 |
| 31 | X31 | reconcile close、client_exhausted、marker INSERT後に行削除・再作成 | 問題なし。high-watermarkと付随処理が整合。 |
| 32 | X32 | fork 4 phase × 通常クラッシュ/app全損/journal破損 | 問題なし。第三ID・読取不能も停止分岐あり。 |
| 33 | X33 | 課金行列に「課金されるserver submit_rejected」を追加し、明示retryを2回 | T03を検出。2回目の実課金が同じseqに衝突。 |
| 34 | X34 | 版CTE、FTS、LIKE差替え、ready不一致を実SQL形へ展開 | 問題なし。列・bind・join・ORDER BYは整合。 |
| 35 | X35 | 主張「seq継承・reconcile close・detachedで課金欠落なし」を通常成功/失効で反証 | 対象経路では破れず。submit_rejected課金はT03へ分離。 |
| 36 | X36 | profile A→B→Aで同一seqのterminal/reconcile closeを再観測 | 問題なし。ON CONFLICTは同一課金の再観測だけを吸収。 |
| 37 | X37 | profile変更中にmissing/damaged/復帰フォルダを出入りさせる | 問題なし。readyは設定時点被覆として一意。 |
| 38 | X38 | fork中移動、HISTORY_CLEARED後にold-id commit追加、digest不一致 | 問題なし。手順1再開またはdamaged停止。 |
| 39 | X39 | register対象を一時EIO、旧pathを別repoが再利用、root swap | 問題なし。一時失敗保留、rebind、dirfd相対操作。 |
| 40 | X40 | 主張「query hash固定・step -1・raw resolverで誤検索/上書きを防ぐ」を反証 | 破れず。既知のno-replace非対応差はX65で別検査。 |
| 41 | X41 | server/client × 全終端理由 × close経路の課金行列 | T03を再検出。課金されるserver拒否だけseqを新規採番しない。 |
| 42 | X42 | damaged除外中にready成立 → 旧profileのフォルダ復帰 | 問題なし。ready維持と復帰分の部分性は明示された通常状態。 |
| 43 | X43 | NFD/NFC/衝突/rawなし × case感度 × resolver 3呼出点 | 問題なし。採用規則とrawなし分岐が一致。 |
| 44 | X44 | 登録済みpath差替え、standalone copy、step -1 unreadable | 問題なし。scoped照合と保留分岐が整合。 |
| 45 | X45 | 主張「unknown・期限超・ready・resolver・step -1が二重課金/誤検索を防ぐ」を反証 | 採用条件内では破れず。 |
| 46 | X46 | token推定記帳→遅延found→sweep再駆動 | 問題なし。同一attemptでは `IN(job id, token)` が二重計上を抑止。 |
| 47 | X47 | 期限超の(i)〜(iv)各DB書込点でクラッシュ | 問題なし。1 Txのため中間状態は露出しない。 |
| 48 | X48 | 未取り込みworking編集中にin-place restore、rawなし後に新規出現 | 問題なし。保全・再lstat・no-replace対応時は防止。 |
| 49 | X49 | 未完forkを跨いでregister/unregister/restore/dropを順次要求 | 問題なし。回復不能journalだけ明示例外。 |
| 50 | X50 | 主張「無id記帳・decoder・restore・回復先行が収束」を反証 | 破れず。T01/T03は別の新規fix相互作用。 |
| 51 | X51 | 期限超seq更新→rotation→相3、found自己記述化→collect | 問題なし。通常系列ではseqは単調。 |
| 52 | X52 | expired terminal→sweep→明示retry→再投入 | 問題なし。上限出口とtoken削除ガードが整合。 |
| 53 | X53 | intent回復・detached・close(b')・sweepの三値/期限/猶予を比較 | 問題なし。4照合点の共通則を確認。 |
| 54 | X54 | journal有効/破損/なし × flag有無 × id old/new/第三/読取不能 | 問題なし。各組合せに停止・回復先がある。 |
| 55 | X55 | embedding混在、tool同時刻tie、md空、backfill OFFを単独検索 | 問題なし。KNN停止とFTS世代選択が定義済み。 |
| 56 | X56 | 非canonical `![diagram](obj:see appendix)` の往復 | 問題なし。拡張decoderで元のバックスラッシュへ戻る。 |
| 57 | X57 | found記帳後にsweep、再投入、state=0 dispatchを実行 | 問題なし。自己記述化はterminal行に閉じ、再投入相1がNULL化。 |
| 58 | X58 | detached terminal化→4.5→削除前再登録 | 問題なし。意図された再投入コストと一致。 |
| 59 | X59 | 課金されるsubmit_rejectedを明示retryで反復 | T03を検出。sweep除外側の記帳実体はあるがseqが進まない。 |
| 60 | X60 | G / `\G` / `\\G`、hash不正、object不在をescape→parse | 問題なし。可逆性とphantom防止が両立。 |
| 61 | X61 | 主張「伝播猶予で未追跡jobを有界化」→最大遅延・保持境界で試行 | 採用条件内では破れず。条件外は設計自身が非対応と明示。 |
| 62 | X62 | 旧attemptの開始時刻残置 → 新tokenへrotation → phase2b前クラッシュ → 長期停止 | T01を検出。未呼出の新attemptを期限超課金候補として数える。 |
| 63 | X63 | unregisterでcancel確定 → terminal Tx後、folders削除Tx前にクラッシュ | T02を検出。次tickがcancel済みtargetを自動再投入。 |
| 64 | X64 | token推定記帳後、同tokenのjobが遅延found | 問題なし。同tokenは同一lifecycleでありIN判別は同一課金を吸収。rotation後はtokenが変わる。 |
| 65 | X65 | no-replace非対応NFS/SMBでEOPNOTSUPP、再lstat後に宛先出現 | T06を検出。中止と通常rename fallbackのどちらも文書上選べる。 |
| 66 | X66 | 共通profile schema対shape検証、manual/automatic rebindの再掲を横断比較 | T04・T05を検出。規範更新が共通schemaと自動rebind側へ伝播していない。 |
| 67 | 自由/S01 | detached client state=0 → terminal化 → sweep → 3条件成立後削除 | 問題なし。即削除への回帰なし。 |
| 68 | 自由/S02 | FTS postingを欠損させrank=1 integrity-check → local/agg rebuild | 問題なし。in-memory FTS5でも検出・再構築形を確認。 |
| 69 | 自由/S03 | text=NULL画像chunkのheadingに2文字語 → LIKE差替え | 問題なし。規範・掲載差替えSQLとも `c.text IS NOT NULL`。 |
| 70 | 自由/SQL | core DDL、FK、GENERATED列、FTS view/trigger/delete/integrity-checkをin-memory SQLiteで実行 | 問題なし。vec0は `<dim>/<metric>` 展開前提として静的確認。 |
| 71 | 自由/課金 | seq=0で課金拒否T1を記帳 → retry T2もseq=0で記帳 | T03をSQLite再現。ledgerはT1の1行だけになった。 |
| 72 | 自由/rebind | watch_root外のAからwatch_root内Bへ自動rebindを反復 | T05を検出。A側fp_cacheがどのwalkのM&Sにも入らない。 |

# 第3部 — 新規検出（C1〜C8、C10〜C12）

| ID | 重大度 | 該当箇所（§ + 引用） | 問題 | 再現シナリオ | 根拠 | 修正案 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | fatal | §9.1 DDL「`job_create_started_at`…NULL = 相2b未着手」、相1「新規 UUIDv7…`batch_job_id` は NULL…`error / completed_at` も NULL」 | 新 intent を作る相1が旧 `job_create_started_at` を消さない。未呼出attemptが「job作成開始済み」に見え、永久な推定ledger行・attempts消費・偽expiredを生む。 | attempts=2、旧開始時刻あり → confirmed-absentから新tokenへrotation → phase2b前クラッシュ → 期限超後に再開 → 未呼出なのにseq/attemptsを進め、attempts=3でexpired。 | P9 / C7 / C10 / C12 / X62 | 新 intent を書くすべての相1（通常、期限内/期限超rotation、明示retry、profile変更）で、同一Tx内に `job_create_started_at=NULL` を必須化する。 |
| T02 | fatal | §21.2「cancelが確定した行は `state=3 (error='cancelled')`」／§9.1「成果なし・state=3・attempts<上限 → 投入対象」 | cancel Txとfolders退役Txの間にクラッシュすると、cancel済み行がattachedのまま自動再投入される。cancelled時にattemptsをterminal値へしないため、ユーザーの退役要求に反して新たな課金jobを作る。 | state=1・attempts=1 → unregisterでcancel確定、state=3 → step2前クラッシュ → 次tickはfoldersあり・成果なし・attempts<3 → OCR/Embedを再submit。 | P9 / C7 / C10 / C12 / X63 | cancel確定Txで `attempts=上限` も設定するか、耐久な unregister intent を同Txで立て、完了までsubmit対象外にする。再登録時の再投入は明示resetとして定義する。 |
| T03 | fatal | §9.1 token sweep注記「拒否にも課金する provider…`submission_seq 現値`…記帳」／相3「`submission_seq+1`」 | server側の課金される恒久拒否は相3前なのでseqが進まない。明示retry後の別拒否も同じseqとなり、`ON CONFLICT DO NOTHING` が別の実課金を同一課金の再観測として捨てる。 | seq=0 → token T1の拒否で課金・ledger(seq0) → retryでT2、seqは0のまま → 2回目も課金 → ledger UNIQUEが衝突しT2の課金が永久欠落。 | P9 / C7 / C10 / C12 / X33/X41/X59 | 課金される拒否分岐では、同一Txで `submission_seq=old+1` に更新して新値で記帳する。tokenによる既記帳判定も付け、同一拒否の再観測だけを吸収する。 |
| T04 | major | §4.1「tool_profile_hash / embedding_profile_hash…`profile_record={"v","model","annotation_schema","options"}`」／§5.7「他 kind の必須フィールドを持つ record は拒否」 | embeddingの正規recordがtool必須フィールド `annotation_schema` を持つ一方、shape検証はそのrecordを拒否する。どちらを優先しても、embedding profileが作れないか実装間で異なるhashになる。 | §4.1どおりembedding recordを生成 → §5.7 adapter検証 → tool必須フィールド所持として拒否 → 必須embeddingの設定・vec作成が開始不能。 | P2 / C1 / C6 / C8 / C10 / C11 / C12 / X66 | tool用とembedding用の完全な別schemaを§4.1に掲載する。embeddingでは `annotation_schema` を禁止し、`options.dimensions / distance_metric / l2_normalized` を必須化。両kindのtest vectorも固定する。 |
| T05 | major | §20.4 自動rebind「新 root_path 配下の fp_cache を無効化」／§21.1 rebind「旧 root_path 配下の fp_cache 行を DELETE」 | 旧path掃除が手動register側だけにあり、定期walkの自動rebindへ伝播していない。旧pathがwalk範囲外ならM&Sされず、移動のたびに絶対パスcacheが残る。 | watch_root外Aを追跡 → watch_root内Bへ移動し自動rebind → 新Bだけ無効化 → Aはfolders/watch_rootsのどちらにも含まれずfp_cacheが永久残留 → 移動反復で単調増加。 | P16 / C1 / C8 / C10 / C11 / C12 / X66 | rebindを共通app Txとして定義し、旧path配下DELETE、新path配下無効化、root_path/missing_since/last_seen更新を全呼出点で同一実装にする。 |
| T06 | minor | §21.4「可能なプラットフォームでは…RENAME_NOREPLACE…EEXISTは中止」 | syscallは存在するがFSがflagを拒否する場合の ENOSYS/EINVAL/EOPNOTSUPP 分岐がない。安全な恒久中止と、通常renameへのfallbackのどちらも読み取れ、後者は競合ファイルを消し得る。 | NFSでno-replaceがEOPNOTSUPP → 再lstat後に外部プロセスが宛先作成 → 実装が通常renameへfallback → 未履歴内容を上書き。別実装はrestoreを恒久拒否。 | C11 / C12 / X65 | unsupported errorを明示分類し、通常の置換renameへはfallbackしない。fail-closed status、または同一FSでのlink/O_EXCL等の原子的no-replace代替を規定する。 |

# 第4部 — 確認済みの列挙

- C2（SQL静的検証）: 確認済み・問題なし。core DDL、GENERATED列、WITHOUT ROWID/PK、FK列数、CHECK、FTS5 external-content view、INSERT/DELETE trigger、rank=1 integrity-checkを検証した。
- C3（相互参照整合）: 確認済み・問題なし。本文内の§参照は実在し、参照文脈と一致した。
- C4（クエリとスキーマの整合）: 確認済み・問題なし。版CTE、eligible、FTS/KNN、LIKE差替え、GC・差集合の列・型・キーは整合した。
- C5（数値・事実の一貫性）: 確認済み・問題なし。$2.5/1,000、+25%、768参考値、RRF 60、metadata 8表は全出現箇所で一致した。
- P1、P3、P4、P5、P6、P7、P8、P10、P11、P12、P13、P14、P15: 確認済み・問題なし。
- P2はT04、P9はT01〜T03、P16はT05・T06のため「問題なし」には該当しない。
- C1/C6/C8/C10/C11/C12はT01〜T06、C7はT01〜T03、C9はS07・S20の partially-fixed があるため「検出0件」には該当しない。