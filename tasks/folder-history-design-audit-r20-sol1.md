不合格
target.md 全 3348 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第1部 — 修正・追記の回帰確認（C9）

全 494 件の内訳は fixed 375、superseded 117、regression 1、partially-fixed 1。

| 系列 | fixed | superseded |
|---|---|---|
| A | A02–A24 | A01→K25 |
| B | B01–B18 | — |
| D | D01–D07, D09–D14 | D08→K20 |
| E | E01–E06 | — |
| F | F01–F04, F06, F08–F11, F13–F20, F22–F27 | F05→I14, F07→I15, F12→I16/I17, F21→I03/I04 |
| G | G01–G02 | — |
| H | H01–H03, H05–H14, H16–H17, H19–H21, H23–H30 | H04→I31, H15→I08/I11, H18→I16, H22→I15 |
| I | I01–I02, I07–I08, I10, I13, I18–I34, I36–I38 | I03–I06, I09, I11–I12, I14–I17, I35 |
| J | J01–J02, J05, J08–J09, J11–J12, J14–J15, J17–J20 | J03–J04, J06–J07, J10, J13, J16 |
| K | K01, K03–K05, K07, K10, K15, K17–K18, K20, K22–K23, K25–K26 | K02, K06, K08–K09, K11–K14, K16, K19, K21, K24 |
| L | L01–L03, L05–L06, L08, L10–L19, L22–L25, L27 | L04, L07, L09, L20–L21, L26, L28 |
| M | M02, M04, M07, M11, M14–M28 | M01, M03, M05–M06, M08–M10, M12–M13, M29 |
| N | N01–N02, N05–N06, N08–N12, N14, N16–N22, N24–N27, N29–N35, N37–N38, N41–N45 | N03→O05/O06, N04→O02/O03, N07→O12, N13→O21, N15→O04/O25, N23→V05, N28→O13, N36→O16, N39→O14, N40→O28 |
| O | O01, O06, O08, O10, O12, O14–O16, O20–O27, O29 | O02/O03→Q05/Q07, O04→Q06, O05→Q04, O07→Q09, O09→Q11/Q12, O11→Q13/Q36, O13→Q12, O17→Q02, O18→Q23, O19→Q24, O28→Q01, O30→Q37 |
| Q | Q01, Q07–Q08, Q11, Q15–Q37 | Q02→R01, Q03→R05, Q04→R02, Q05→R06, Q06→R06/R07, Q09→R03, Q10→R14, Q12→R04, Q13/Q14→R15/R16 |
| R | R01–R05, R09–R12, R14–R17, R19, R21–R22, R24, R26–R29 | R06→S10/S15, R07→S19/S28, R08→S01, R13→S02, R18→S02, R20→S03, R23→S04, R25→S06 |
| S | S01–S05, S08–S10, S12–S18, S21–S22, S26–S29 | S06→T09, S07→T05/T06, S11→T07, S19→T03, S20→T01, S23→T18, S24→T02, S25→T04 |
| T | T01–T02, T04–T07, T09, T12–T15, T17–T18 | T03→U04, T08→U03, T10→U01, T11→U05, T16→U02 |
| U | U02, U04–U05, U07–U10, U12–U23 | U01→V01, U03→V07, U06→V02, U11→V04, U24→V03 |
| V | V01, V03–V08, V10–V20 | — |

A11 は中核を fixed、遷移詳細を I05/I06/I13/I14 に継承。H02 は中核を fixed、衝突順序の詳細を I32 に継承。

| ID | 状態 | 再確認結果 |
|---|---|---|
| V02 | regression | 基準は「completed_at の DDL コメント＝state が 2/3 へ確定する全ての UPDATE で同時に書く」「collect 限定の残存＝regression」。target.md L912–916 は「**確定する全ての UPDATE で同時に書く**」「reconcile / submit_rejected / client_exhausted / expired / cancelled / detached / abandoned も」と正しく規定し、L1247–1249 も「**state を 2/3 へ確定する全ての UPDATE に共通の規範**」と再掲する。しかし同じ DDL の L917 に「**書込点は §10 collect**」が残り、非 collect 終端で completed_at を書かない実装を許す。 |
| V09 | partially-fixed | 基準は scan_cache の `syntax_fail_count / first_failure_at`、reset、一時 EIO 除外、24h 起点の DDL・規範両面一致。§20.5 L2758–2762 は「**カウントの実体は scan_cache に永続化する**」「`syntax_fail_count / first_failure_at` を記録し（列追加）」と規定するが、§9.1 L1443–1456 の `CREATE TABLE scan_cache` は `verified_at` の直後が `PRIMARY KEY` で両列がない。掲載 DDLを SQLite in-memory DB に作成後、`SELECT syntax_fail_count, first_failure_at FROM scan_cache` は `no such column: syntax_fail_count` となった。 |

V01、V03–V06 の補修再発検査は fixed。V01 は upload 対象が「入力（原本 — Office 文書は変換 PDF）」へ統一、V03 は不可能 phase/id 組合せを damaged 停止、V04 は派生保持時だけ再課金なし、V05 は退避と backfill OFF の併用、V06 は「§1 の原則」参照を確認した。

## 第2部 — 探索型監査（C12）

| # | 観点 | 初期状態 → 操作列 | 結果 |
|---:|---|---|---|
| 1 | X1 | 追跡中の `a.pdf` を同一 tick 間に作成→編集→削除し、旧 OCR job も終端させる。walk、pending delete、collect を順に適用。 | スナップショット外の一過性内容は履歴化しない設計どおり。旧 job は成果を保存せず記帳・終端化。問題なし。 |
| 2 | X2 | `../x\n<!-- img:`、巨大 img block、0 byte、symlink、hardlink を管理フォルダへ配置して scan・restore・parse。 | name_invalid、厳密 grammar、O_NOFOLLOW、型検査で拒否または保留。問題なし。 |
| 3 | X3 | NFD 名のフォルダを case-sensitive から case-insensitive FS へ移動し、NFC 同値名と case-only 名を併存。 | raw resolver と name_collision に収束し、勝者を推測しない。問題なし。 |
| 4 | X4 | 時計を後退させ、同一 ms に複数 commit、未来 UUIDv7 token、generated_at 置換を実行。 | 単調値、tie-break、future-skew 規則が適用される。問題なし。 |
| 5 | X5 | 10万ファイル、100万 chunk、長い IN 条件で walk、replicate、FTS/KNN を実行。 | fp、差集合、cap、分割 bind により実装可能。問題なし。 |
| 6 | X6 | 2文字日本語検索、vec0 部分充填、2^53 超の mtime_ns を JCS fingerprint に投入。 | LIKE fallback、ready gate、10進文字列化が定義済み。問題なし。 |
| 7 | X7 | 旧 scan_cache へ r19 の構文失敗カウンタを保存する migration を実行。 | 必須列が掲載 DDL に存在せず V09 を検出。 |
| 8 | X8 | app.sqlite を別ユーザーが読める環境で、絶対パスや `..` を含む復元先を指定。 | 権限規範、照合済み dirfd、resolver により管理外書込みを拒否。問題なし。 |
| 9 | X9 | objects rename 後、metadata Tx 前、app 更新前の各位置で ENOSPC・電源断。 | orphan object、未 app 反映、再 scan の各安全側状態から回収可能。問題なし。 |
| 10 | X10 | `.folder-history` を手動削除・部分同期し、zip 解凍で inode/mtime を全変更。 | missing/damaged/re-register と全量 hash scan へ倒れる。問題なし。 |
| 11 | X11 | OCR floor 設定中に profile を変更し、reconcile と collect を交互に再実行。 | snapshot、floor 比較、kind 分岐で旧成果を現行扱いしない。問題なし。 |
| 12 | X12 | watch_root 登録→発見→commit→OCR→chunk→embed→replicate→検索→open→履歴→restore を通し実行。 | 各出力から次段の入力を追跡可能。問題なし。 |
| 13 | X13 | stalled、damaged、conflict、abandoned、明示 retry、明示解決を UI/CLI 操作として追跡。 | 入力・効果・失敗時状態は定義済み。ただし abandon 後の遅延 job は X76/W02。 |
| 14 | X14 | upload、job create、collect が Retry-After なし 429 を返し、消失ディレクトリを大量生成。 | 共通 backoff と fp_cache mark-and-sweep が適用される。問題なし。 |
| 15 | X15 | 主張①object rename 後 crash でも喪失しない→metadata 前 crash、②偽 delete を防ぐ→1回だけ不在、③profile は収束→破棄 Tx 中断、④重複 job は有界→相2b/相3間 crash、⑤restore は working 変更を守る→未取込変更上へ restore、の各操作列を試行。 | 5 主張とも規定された回収・保留・保全で破れず。 |
| 16 | X16 | 1 repository の JSONL を3 jobへ分割し、2番目だけ相2b後に crash。 | job ごとの token、行 snapshot、intent 回復で独立収束。問題なし。 |
| 17 | X17 | register 中断→fork→restore→unregister→再登録を各 Tx 境界で中断。 | tick.lock、journal、全量再同期により回復。問題なし。 |
| 18 | X18 | profile record 改竄、pending delete 中の部分 walk、cost_ledger だけ残した app 復旧を実行。 | fail-closed、fp 非確定、課金下限の表示に収束。問題なし。 |
| 19 | X19 | object、metadata、app、fork phase の各 fsync/rename 境界で電源断を反復。 | 耐久順序と次 tick の再駆動を確認。問題なし。 |
| 20 | X20 | 主張「重複課金は有界」「月跨ぎ retry は発生月へ配賦」「profile 変更は収束」「fork は phase 再開」「delete は pending で回収」「rename 後 fsync で存在保証」を、それぞれ相2境界・月境界・破棄境界・fork各phase・連続不在・rename直後 crash で試行。 | 同一実装内の操作列では全主張とも破れず。journal 表現の異なる実装間は X27/W06。 |
| 21 | X21 | profile A の相1後に Bへ変更し、vec再充填・agg ready・job_missing を同 tick で実行。 | snapshot と building/ready key が旧成果混入を防止。問題なし。 |
| 22 | X22 | fork の PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE で中断し、並行 unregister を試行。 | 回復先行ゲートで操作が直列化される。問題なし。 |
| 23 | X23 | NULL/estimated ledger、detached、name_collision、name_invalid を検索・GC・status へ流す。 | 各読み手の除外・表示が定義済み。問題なし。 |
| 24 | X24 | 主張①vec差集合は欠落を埋める→半分充填で中断、②agg毎tick検査は破棄喪失を吸収→wipe後crash、③client queueはstate=1を跨がない→dispatch中断、を試行。 | 3主張とも再実行で破れず。 |
| 25 | X25 | フォルダ未接続の app.sqlite だけで横断検索し、watch_root 解除後も既知 folder を検索。 | app_config と folders 情報から一意に処理可能。問題なし。 |
| 26 | X26 | 行削除→再登録→client前計上→server found→profile A/B 切替を連続実行。 | ledger MAX 継承、seq+1、snapshot で衝突しない。問題なし。 |
| 27 | X27 | 実装Aが `JCS(record)||raw digest`、実装Bが `JCS(record)||LF||hex digest||LF` と解釈。AがPREPARED後crashしBが回復。 | 両方とも「末尾に SHA-256 digest」を満たすが、Bが正常 journal を damaged 化する W06 を検出。 |
| 28 | X28 | detached を state 0/1/2/3 で生成し、collect→記帳→upload掃除→再登録。 | payload破棄と段階削除が定義済み。問題なし。 |
| 29 | X29 | case-only rename 後、case-sensitive FS へ移し大小2実体を作る。 | 保存名固定、BINARY partition、collision が一貫。問題なし。 |
| 30 | X30 | 主張「ledger UNIQUE は正当な再課金を妨げない」「client重複は有界」「forkはjournalで一意再開」「case-only FK違反なし」「偽deleteなし」「detached記帳漏れなし」を試行。fork は異なる適合実装で journal を受け渡す操作も追加。 | 前5系統は破れず。fork の一意再開主張は digest framing 未定義により破れた（W06）。 |
| 31 | X31 | ledger MAX=k の削除済み行を再作成し、reconcile close と submit_rejected retry を実行。 | k継承後のk+1記帳に収束。問題なし。 |
| 32 | X32 | 4 phase×通常crash/app全損/id old/new/不可能組合せを総当り。 | 同じ journal decoder 内では再開位置が一意。不可能組合せは damaged。問題なし。 |
| 33 | X33 | server/client×成功・expired・missing・profile_changed・rejected×通常/reconcile/detached の記帳行列を実行。 | 各 attempt が0または1行の規定どおり。問題なし。 |
| 34 | X34 | 掲載 FTS、LIKE fallback、eligible再JOIN、RRF、replication SQLを SQLite in-memory DB で実行。 | scan_cache のV09以外は列・join・trigger・FTS rank=1を確認。vec0固有部分は静的整合を確認。 |
| 35 | X35 | 主張「seq継承でUNIQUE衝突なし」「reconcile記帳漏れなし」「rejected自動再投入なし」「id=oldからfork再開」「detached記帳漏れなし」「最終statで偽deleteなし」を対応境界で試行。 | 全主張とも破れず。 |
| 36 | X36 | 同一seqのcloseを再実行し、detached採用とprofile A→B→Aを重ねる。 | `ON CONFLICT DO NOTHING` は同一事実だけを吸収。問題なし。 |
| 37 | X37 | missing/damaged folderを除外してP2 ready後、旧P1のfolderを復帰。 | 母数復帰でready判定が再評価される。問題なし。 |
| 38 | X38 | fork中にフォルダを移動し、flagのみ、journalのみ、digest不整合を作る。 | 有効journalは移動先回復、破損はdamaged。表現問題はW06。 |
| 39 | X39 | 一時EIO、旧path別実体、対象外型置換、再登録を組み合わせる。 | 破壊的推測をせず保留・rebind・terminal化へ収束。問題なし。 |
| 40 | X40 | 主張「close Tx abortなし」「readyは部分indexを通さない」「未完forkは通常復帰しない」「EIOで履歴破壊なし」「対象外型を見逃さない」「query profile TOCTOUなし」「距離変更は再CREATE」を各境界で試行。 | 同一decoder前提では全主張とも破れず。 |
| 41 | X41 | cost ledger の server/client・NULL/actual・terminal/detached 全組合せを作成。 | 値規則とUNIQUEが一致。問題なし。 |
| 42 | X42 | 接続0→1、damaged復帰、synced全NULL化、agg wipe/refillを同tickで実行。 | ready母数と更新順序が安全側。問題なし。 |
| 43 | X43 | resolver 3呼出点×NFD/NFC/両方/無し×case感度を実行。 | 両方存在時はcollisionで書込み拒否。問題なし。 |
| 44 | X44 | 登録path一時EIO、同id conflict、step -1 z判定失敗、fork中rebindを実行。 | read/replicate/submitを保留し、誤detached化しない。問題なし。 |
| 45 | X45 | 主張「client中間課金は漏れない」「unknownで二重jobなし」「期限超残骸も記帳」「server成果closeは記帳」「readyはdamagedに騙されない」「raw resolverは二重実体を作らない」「登録path差替え検知」「step -1誤課金なし」を各境界で試行。 | 8主張とも破れず。 |
| 46 | X46 | token記帳→job-id記帳→sweep再訪→正規closeを同一行で連続実行。 | seqとbatch_job_id述語が別attemptだけを記帳。問題なし。 |
| 47 | X47 | 期限超Txを各文の途中で中断し、detached削除→再登録→MAX継承。 | 単一Txとseq継承により重複しない。問題なし。 |
| 48 | X48 | 未取込working変更へin-place restoreし、安定確認失敗・同hash・collisionを試す。 | 変更を先にcommitし、不安定・collisionは中止。問題なし。 |
| 49 | X49 | 未完fork状態でregister/unregister/restore/watch_root/dropを呼ぶ。 | recovery gateが先行し、damaged時は明示解決以外を拒否。問題なし。 |
| 50 | X50 | 主張「無id記帳はNOT NULLを満たす」「推定行は増殖しない」「sweepが(b')欠落を回収」「detachedは記帳後削除」「未来tokenを無記帳再投入しない」「escape往復可逆」「restoreはworkingを消さない」「明示操作はforkに反転されない」を試行。 | 8主張とも同一decoder前提では破れず。 |
| 51 | X51 | 無id記帳、found、detached、client前計上を一行で順次実行し、行削除後に再作成。 | submission_seqは単調継承。問題なし。 |
| 52 | X52 | expired terminalをunregisterし、sweep前に明示retry、再登録を実行。 | token guardと削除条件が旧tokenを保護。問題なし。 |
| 53 | X53 | intent回復、detached(b)、(b')、sweepの4照合点でunknown/absent/future/期限超を総当り。 | scope問題を除き三値・猶予・記帳規則は対称。scope問題はX75/W01。 |
| 54 | X54 | journal有効/破損/無×flag有/無×id old/new/他/EIOを組み合わせる。 | 同一decoderでは回復・保留・damagedが一意。問題なし。 |
| 55 | X55 | embedding混在中にtoolも混在、generated_at同時刻、markdown空、backfill OFFを試す。 | tie-breakと0件/statusが定義済み。問題なし。 |
| 56 | X56 | `![diagram](obj:see appendix)` 等の非canonical行をescape→materialize→検索。 | r15 decoder拡張によりphantom防止と往復性を維持。問題なし。 |
| 57 | X57 | found自己記述化後にcrashし、state2行を再投入。 | ledger述語が再観測を吸収し、相1がjob idを初期化。問題なし。 |
| 58 | X58 | detached/expired terminalを再登録してattachedへ戻し、明示retry。 | attempts resetを伴う明示操作だけが再投入する。問題なし。 |
| 59 | X59 | 課金されるsubmit_rejectedと課金なしprovider、client_exhaustedを実行。 | 拒否分岐でのseq+1記帳とsweep除外が両立。問題なし。 |
| 60 | X60 | 0個以上の`\`、canonical/noncanonical、object有/無をescape/unescape/recognizeで総当り。 | 厳密認識と実在確認で往復・phantom防止・text_hashが一致。問題なし。 |
| 61 | X61 | 主張「1Txで偽expiredなし」「自己記述化で二重記帳なし」「detachedは削除guardとdeadlockしない」「rejected token残留なし」「全行escape往復可逆」「一括変換後tool決定論」を、猶予境界・再訪・掃除失敗・混在入力で試行。 | 6主張とも破れず。 |
| 62 | X62 | job_create_started_at記録後・呼出前、呼出後・相3前でcrashし、NTP後退も加える。 | NULL/非NULLとfuture-skewで安全側。問題なし。 |
| 63 | X63 | cancel確定→再登録→明示retry→再unregisterを反復。 | attempts上限、自動再投入禁止、冪等記帳に収束。問題なし。 |
| 64 | X64 | token推定記帳後に別attempt J2を作り、found IN判定を実行。 | rotation前の旧token清算により世代が混在しない。問題なし。 |
| 65 | X65 | RENAME_NOREPLACE非対応FSでEINVAL、EEXIST、ENOTEMPTYを返す。 | 初回エラー判定、再lstat、既存時中止が定義済み。問題なし。 |
| 66 | X66 | completed_at の規範文、DDLコメント、§10 collect再掲を横断比較。 | 「全terminal UPDATE」と「書込点はcollect」が矛盾する V02 を検出。 |
| 67 | X67 | state3 token残存行でguardがunknownを返し続け、dirty tickとretry_not_beforeを実行。 | stalled表示とabandon脱出はある。abandon後の後日jobはW02。 |
| 68 | X68 | cancel→retry→cancelを繰り返し、各回upload掃除前に中断。 | 各世代のledgerとtoken guardが分離。問題なし。 |
| 69 | X69 | FTS cap同点境界、KNN k非対称、外側limitを組み合わせる。 | tie-breakとcap表示により決定的。問題なし。 |
| 70 | X70 | converter更新、旧converter消失、変換失敗、unsupported formatを実行。 | tool_profile変更とconvert_failed terminalが分離。問題なし。 |
| 71 | X71 | state0載せ直しTxを各境界で中断し、client dispatchを再実行。 | state0自身の期限判定・記帳経路が旧tokenを処理。問題なし。 |
| 72 | X72 | 不可視job Tをabandonし、ledger(T)記帳・token NULL後にjob Jを可視化。 | 行がsweep対象から消え、後日found経路が到達不能となる W02 を検出。 |
| 73 | X73 | old toolのconvert_failed後にtool_profileを変更し、新target_keyで再処理。 | attemptsと課金なしterminalはキー単位で独立。問題なし。 |
| 74 | X74 | stat tuple S1で構文失敗1回を永続化し、EIOを挟み、同じS1を再走査。 | DDL列欠落のV09に加え、stage1がpending failureをstage2へ送らないW05を検出。 |
| 75 | X75 | scope Aの完了行を資格情報Bで明示再生成。相1後・相2b前にcrashし、Bの一覧を照会。 | scope Aが残ってscope不一致unknownとなり、相2bへ進めない W01 を検出。 |
| 76 | X76 | state0不可視jobをabandonし、upload cleanup後に行を削除、後日jobを可視化。 | tokenと行がなくjobの帰属・cleanup不能となる W02 を再確認。 |
| 77 | X77 | fp一致済みの非登録conflict copy BでPREPARED journalを書き、flag前にcrash。 | `.folder-history`がfp外かつ登録folder限定probeのためjournalが隠れる W03 を検出。 |
| 78 | X78 | state2・旧token残存行へfloor明示再生成を実行し、その後guardが旧jobをfound。 | reset直後のattemptsが旧job清算で+1される W04 を検出。 |
| 79 | X75 | scope Aとstarted_atを記録後、同じAの全ページ一覧からjobをfound。 | scope一致時の採用は正常。問題なし。 |
| 80 | X76 | abandon行に既知upload_idがあり、provider deleteが404を返す。 | 404を成功扱いとしてupload_cleanedへ進む。問題なし。 |
| 81 | X77 | 10万の登録フォルダをfp一致状態にし、journal存在probeだけを実行。 | per-folder存在検査コストは生じるが、規定された検出保証と両立。問題なし。 |
| 82 | X78 | floor設定後、旧tokenのledgerが既に存在するguardを再実行。 | 再記帳・attempts増加をせずtokenを清算できる。問題なし。 |

## 第3部 — 新規指摘

| ID | severity | 根拠箇所・引用 | 問題 | 再現 | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| W01 | major | §9.1 L886–889「scope_id…相2b直前」、L1062–1070「batch_job_id…error / completed_at / job_create_started_atもNULLへ戻す」、L1197–1203「行のscope_idと現照会scopeの比較」 | 相1が旧scope_idを消さない。新token世代が相2b未着手でも、旧世代のscopeに拘束されてunknownから脱出できない。 | scope=Aのterminal行→資格情報をBへ変更→floor再生成の相1でtoken更新・started_at=NULL、scope=A残存→相2b前crash→B一覧はscope不一致→unknown継続→scope=Bを書ける相2bへ到達不能。abandonすると外部呼出前なのにestimated記帳まで発生する。 | P9、C7、C8、C10、C11、C12、X53、X75 | 相1で `scope_id=NULL` も同時に行う。併せて `job_create_started_at IS NULL` は一覧照合せず相2b未着手として扱い、stale scopeを参照しないことを明記する。 |
| W02 | major | §9.1 L1085–1092「(iv) intent_token NULL化」「後日jobが可視化されてもsweep foundのIN判別」、L1303–1304「intent_token非NULL…token sweep」、L1315–1327 found処理 | abandonがtokenを消した直後、後日foundを担うsweepの選択条件から行が外れる。文書が保証する後日照合・cleanupは到達不能。 | 不可視job T→abandonでledger(T)、state=3、token=NULL→upload掃除後に行削除→job Jが遅延可視化→T/Jを探索する行もtokenもなく、帰属・cleanup不能。 | P9、C3、C7、C10、C11、C12、X13、X67、X72、X76 | abandoned tokenを保持期限まで持つdurable tombstoneへ移し、ledger起点のsweepで後日found・cleanupを行う。active行のtokenはtombstoneの耐久化後にだけNULL化する。 |
| W03 | major | §20.3 L2595–2597「`.folder-history/`はfpの入力から除外」、L2607–2611「例外—登録フォルダは…fork-journal…検査」、§21.3 L3139–3141「毎tickのwalk…fork-journalを持つフォルダを検出」 | fp一致前のjournal probeが「登録フォルダ」だけで、folders行を持たないconflict copyの未完forkを検出できない。§21.3の毎tick回復保証と矛盾する。 | 非登録conflict copy Bのfpをcache→BのforkがPREPARED journalを耐久化→app flag前crash→通常ファイルfp不変→Bは登録folderでないためprobeなしでskip→journal回復が永久に駆動されない。 | P16、C3、C7、C8、C10、C11、C12、X27、X40、X77 | 「登録フォルダ」をfolders行ではなく `.folder-history` markerを持つ全候補へ拡張し、fp skip前にjournalを検査する。一時読取不能は枝を確定せずstatus・再試行とする。 |
| W04 | major | §5.3 L258–262「floor…attempts=0にリセット」、§9.1 L1071–1075 state2を含むrotation guard、L1319–1321 found時「attemptsを+1」、L1047–1049 attempts上限 | 明示再生成が新しい試行予算を0へ戻した後、旧tokenの清算がその予算を消費する。新 lifecycle が規定より少ない回数でterminal化する。 | state=2、attempts上限、旧token T残存→明示再生成Txでattempts=0→guardが旧Tのjobをfoundしattempts=1→新jobは上限まで残り2回しか投入できない。 | P9、P10、C7、C10、C11、C12、X47、X71、X78 | 旧tokenの照合・記帳をfloor/attempts resetより先に行うか、guard完了後・新相1直前に新 lifecycle 用 `attempts=0` を原子的に再適用する。 |
| W05 | major | §20.3 L2632–2642「stat tupleのどれかが違えば段2」「racyなら段2」、§20.5 L2753–2762「連続3回（または24時間）」「scan_cacheに永続化」 | 構文失敗保留中の行を段2へ再投入する条件が段1にない。V09の列だけ追加しても、同一tupleの2回目以降がskipされ、3回/24h判定へ到達できない。 | cache=S0→mtimeを古く保ったままinode/sizeだけS1へ変更した壊れた文書→1回目はtuple差で段2、failure_count=1をS1へ保存→次tickはtuple一致かつmtime<verified_atで非racy→段1skip→countが1のまま。旧tupleを残す実装ではS1ごとのcounterを保持できない。 | P16、C7、C8、C10、C11、C12、X74 | 段1に「同一tupleで `syntax_fail_count>0` または24h判定待ちなら段2」を追加する。失敗tuple、content_hash、verified_atの更新関係も一意に定義する。 |
| W06 | major | §21.3 L3063「recordをJCS直列化し、末尾にSHA-256 digestを付す」、L3175「digest不整合・構文不正のjournalはdamaged」 | digestの表現、区切り、対象byte範囲、終端LFが未定義。異なる適合実装・バージョン間で正常journalを破損扱いできる。 | A=`UTF8(JCS)||raw32`、B=`UTF8(JCS)||LF||lower_hex64||LF`→AがPREPARED後crash→Bが開く→Bは構文不正またはdigest不一致としてdamaged停止。 | P16、C2(e)、C8、C10、C11、C12、X7、X20、X27、X30、X32 | 例として `UTF8(JCS(record)) || LF || lower_hex(SHA256(UTF8(JCS(record)))) || LF` に固定し、digest対象、hex大小、区切り、BOM禁止、終端LFまで規定する。 |

## 第4部 — 観点・原則の確認状況

| 観点 | 確認結果 |
|---|---|
| C1 | 確認済み。P9、P10、P16に検出あり。参照先はV02、V09、W01–W06。 |
| C2 | 確認済み。V09とW06を検出。その他の通常SQLite DDL、FK、CHECK、trigger、FTS external-content定義は問題なし。 |
| C3 | 確認済み。V02、W02、W03を検出。その他の§参照は問題なし。 |
| C4 | 確認済み。V09を検出。その他の掲載SQL、CTE列、join key、FTS trigger/rebuildは問題なし。 |
| C5 | 確認済み・検出0件。 |
| C6 | 確認済み・検出0件。 |
| C7 | 確認済み。W01、W02、W04、W05を検出。 |
| C8 | 確認済み。W01、W03、W05、W06を検出。 |
| C9 | 確認済み。V02=regression、V09=partially-fixed。 |
| C10 | 確認済み。W01–W05は修正相互作用、W06はjournal補修の実装契約不足。 |
| C11 | 確認済み。W01–W06を検出。 |
| C12 | 82シナリオを実行済み。W01–W06を検出。 |

| 原則 | 確認結果 |
|---|---|
| P1 | 確認済み・検出0件。 |
| P2 | 確認済み・検出0件。 |
| P3 | 確認済み・検出0件。 |
| P4 | 確認済み・検出0件。 |
| P5 | 確認済み・検出0件。 |
| P6 | 確認済み・検出0件。 |
| P7 | 確認済み・検出0件。 |
| P8 | 確認済み・検出0件。 |
| P9 | 確認済み。V02、W01、W02、W04を検出。 |
| P10 | 確認済み。W04を検出。 |
| P11 | 確認済み・検出0件。 |
| P12 | 確認済み・検出0件。 |
| P13 | 確認済み・検出0件。 |
| P14 | 確認済み・検出0件。 |
| P15 | 確認済み・検出0件。 |
| P16 | 確認済み。V09、W03、W05、W06を検出。 |