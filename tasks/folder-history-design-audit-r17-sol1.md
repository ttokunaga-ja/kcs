不合格
target.md 全 3135 行を読了 — 最終行: 『```』

# 第1部　判定

致命的欠陥を4件検出したため、不合格と判定する。

- T01: `job_create_started_at` 追加時の既存行・復元行が `NULL` となり、実在するジョブを「相2b未着手」と誤認できる。
- T02: 新しい `intent_token` 発行時に `job_create_started_at` を消去しないため、時計巻戻しとの組合せで未実行API呼出しを課金済み扱いできる。
- T03: `state=0`・ジョブID未記録のキャンセル経路で、再登録が未精算トークンを上書きし、課金追跡不能または重複投入を生じ得る。
- T04: 排他的no-replace renameを提供しないファイルシステムでの復元がfail-closedになっておらず、競合生成された未保存ファイルを上書きし得る。

# 第2部　監査結果

## 2.1 C1〜C8

| 観点 | 結果 |
|---|---|
| C1 | P1〜P16の反映を確認。相互作用上の欠陥はT01〜T04として分離した。 |
| C2 | in-memory SQLiteでnative側DDL、外部キー、生成列、CHECK、FTS5トリガ、`integrity-check`の`rank=1`、rebuild、cascade deleteを検証し、成立を確認。agg側も同様。vec0は拡張依存のためDDLテンプレートを静的検証した。 |
| C3 | 定義語、状態値、所有DB、永続化境界に新規不整合なし。 |
| C4 | 通常経路のクラッシュ整合性、トランザクション境界、再試行の収束性に新規不整合なし。 |
| C5 | 履歴、検索、復元、fork、pending deleteの通常経路に新規不整合なし。 |
| C6 | セキュリティ境界、パストラバーサル、symlink、権限、スコープ制約に新規不整合なし。 |
| C7 | T01、T02、T03を検出。 |
| C8 | 性能・運用境界の記述に新規致命的不整合なし。 |

## 2.2 C9：既往432項目の再監査

判定は432/432項目が`fixed`または`superseded`であり、`partially fixed`、`not fixed`、`regression`は0件。

- `superseded`：97項目  
  A01, A11, D08, F05, F07, F12, F21, H02, H04, H15, H18, H22, I03, I04, I05, I06, I09, I11, I12, I15, I16, I17, I35, J03, J04, J06, J07, J10, J13, J16, K02, K06, K08, K09, K11, K12, K13, K14, K19, K21, K24, L04, L07, L09, L20, L21, L26, L28, M01, M05, M06, M08, M09, M10, M12, M13, M29, N03, N04, N07, N13, N15, N28, N36, N39, N40, O02, O03, O04, O05, O07, O09, O11, O13, O17, O18, O19, O28, O30, Q02, Q03, Q04, Q05, Q06, Q09, Q10, Q12, Q13, Q14, R06, R07, R08, R13, R18, R20, R23, R25。部分置換IDについては置換対象サブ要件のみ`superseded`、残余サブ要件は`fixed`。
- `fixed`：上記以外の335項目。

r16の重点3項目も次のとおり成立している。

- S01：§9.1の「同一Txで`state=3, error='detached', completed_at=now`」「即削除ではなく」、および§21.2の削除3条件と段階遷移の双方を確認。
- S02：native側の`INSERT INTO chunk_fts(chunk_fts, rank) VALUES('integrity-check', 1)`、agg側の同一形式、失敗時の同一Tx内rebuildを確認。SQLite実行でも成立。
- S03：§11.2の規範条件と置換SQLの双方に`c.text IS NOT NULL`が存在することを確認。

## 2.3 C12：反証探索ログ

全78シナリオを実施し、X1〜X66をすべて1回以上検査した。

| No. | 観点 | 反証シナリオ | 結果 |
|---:|---|---|---|
| 1 | X1 | 監視tick間に作成・編集・削除を連続させ、イベント欠落を仮定。 | final walkとpending処理で収束。 |
| 2 | X2 | 文法境界、予約名、区切り文字、escapeを含むファイル名を投入。 | invalid/escape/object検査で閉じる。 |
| 3 | X3 | case-insensitive・NFC/NFDボリューム間で名称衝突を発生。 | ボリューム再判定とtie処理で閉じる。 |
| 4 | X4 | commit時刻を巻き戻し、単調性を破壊。 | commit時刻のclampは成立。ジョブ開始時刻との相互作用はNo.63でT02。 |
| 5 | X5 | 10万ファイル・100万chunk相当の境界を論理トレース。 | §19の上限、分割、vacuum方針に正しさ上の破綻なし。 |
| 6 | X6 | 1〜2文字の日本語検索をFTS対象外として試行。 | `LIKE`フォールバックで検索可能。 |
| 7 | X7 | 旧schema、未知の`user_version`、途中migrationを仮定。 | 未知版はfail-closed。新列移行の意味論はNo.62でT01。 |
| 8 | X8 | `..`、symlink、権限変更、root外参照を試行。 | canonicalizationと権限検査で拒否。 |
| 9 | X9 | object書込、metadata Tx、app Txそれぞれで容量枯渇。 | temp/orphan/retry経路で収束。 |
| 10 | X10 | `.folder-history`削除、部分コピー、metadataのみ残存。 | damaged/conflictとして顕在化。黙示的正常化なし。 |
| 11 | X11 | app floor、profile、local transformを同時変更。 | app floorを先に適用する順序で一意。 |
| 12 | X12 | scan→commit→search→restore→deleteの全handoffを追跡。 | 所有DBと引渡し条件が定義済み。 |
| 13 | X13 | status中に明示的scan、restore、fsckを並行要求。 | catalog解決とrecovery gateで直列化。 |
| 14 | X14 | provider 429を継続させ、cacheとledgerを増大。 | backoff、M&S、vacuum、上限制御を確認。 |
| 15 | X15 | 主張：intent一意性、floor fence、vec refill、削除直前確認、scoped read。試行：各境界直前でクラッシュ・競合・権限変更。 | 前提内ではいずれも崩壊せず。 |
| 16 | X16 | 複数targetが同じtokenを共有し、各phaseでクラッシュ。 | 全行guardとtoken単位回復で収束。 |
| 17 | X17 | register直後クラッシュ、fork、DB復元、unregisterを連続。 | 通常経路はjournalとrecoveryで収束。 |
| 18 | X18 | profiles、pending、ledgerを含むapp DBのみ消失。 | fsck/bootstrapで再構成可能な範囲が明示される。 |
| 19 | X19 | fsync前後および各phase Tx前後で電源断。 | durable boundaryに従い再試行可能。 |
| 20 | X20 | 主張：server一ジョブ、月次ledger意味論、profile収束、fork安全、delete安全、dir fsync。各commit境界で反証試行。 | 明示されたprovider・app-loss境界内では崩壊せず。 |
| 21 | X21 | state2中にprofile変更し、旧snapshotと新floorを競合。 | 既存snapshot固定、新規分のみ新profileとなる。 |
| 22 | X22 | forkの各phase直後にクラッシュ。 | journalのphase遷移で再開可能。 |
| 23 | X23 | 新規tableの行を残してstatus・unregisterを実施。 | ownerと掃除条件があり、通常経路で孤児化しない。 |
| 24 | X24 | 主張：vec再構築、agg整合、client batch回復。欠落・重複・再実行を注入。 | 規定された再構築経路では崩壊せず。 |
| 25 | X25 | app DBのみでcross-root search、restore、watch-root解決。 | root catalogから解決され、黙示的越境なし。 |
| 26 | X26 | seq、attempt、profile snapshotの更新順を入替え。 | 同一Tx要件により観測不能。 |
| 27 | X27 | journal存在中にapp DB消失、root移動、再登録。 | filesystem identityによる回復経路がある。 |
| 28 | X28 | detachedのstate0/1/2/3を再登録。 | 通常経路は規定済み。state0キャンセルとの交差はNo.67でT03。 |
| 29 | X29 | case-first spellingを変更後、case-sensitive volumeへ移動。 | raw/canonical双方の保持で解決。 |
| 30 | X30 | 主張：seq非衝突、client上限、fork、name safety、delete safety、detached回復。競合を同時注入。 | 通常経路では崩壊せず。 |
| 31 | X31 | `MAX(seq)`読取後に別writerが採番し、reconcile/rejectを競合。 | Tx内採番とconstraintで衝突を拒否。 |
| 32 | X32 | batchの4phaseそれぞれでAPI応答前後にクラッシュ。 | 通常のrecord-before-callとadoptionで収束。 |
| 33 | X33 | server/clientとterminal reasonの課金行列を全組合せ追跡。 | 通常経路は一意。state0キャンセルのみNo.67で破綻。 |
| 34 | X34 | current、point-in-time、all-history検索と短語`LIKE`をSQLiteで実行。 | native FTS/LIKE SQLは成立。 |
| 35 | X35 | 主張：seq、reconcile、rejected、fork、detached、delete。Tx境界を1つずつ外す反証を試行。 | 文書どおり実装する限り崩壊せず。 |
| 36 | X36 | `ON CONFLICT`とseqのA→B→A再出現を競合。 | version identityとseq規則で区別される。 |
| 37 | X37 | ready object欠損・破損、P2→P3→P2の復帰を試行。 | readinessを過大申告しない。 |
| 38 | X38 | flag、journal、move、digestの更新途中で停止。 | journal優先順位で再開可能。 |
| 39 | X39 | register時EIO、rebind、型変更、最終確認直前の差替え。 | dirfd/final checkによりfail-closed。 |
| 40 | X40 | 主張：課金冪等、ready、fork move、EIO、delete型、query TOCTOU、metric。各境界を保持したまま競合注入。 | 通常条件では崩壊せず。 |
| 41 | X41 | server/clientの成功・失敗・拒否・期限切れterminalを全走査。 | ledger predicateは通常行列で一意。 |
| 42 | X42 | motherを0→A/B→Cと変更し、各時点をrestore。 | 各commitのready状態に応じた部分復元となる。 |
| 43 | X43 | resolverへNFD/NFC、case collision、raw不在を入力。 | 決定不能時は競合として停止。no-replace非対応はNo.72。 |
| 44 | X44 | scoped readでstep-1のverified/regressed/unreadableを切替え。 | 規範条件に従い過去データを誤採用しない。 |
| 45 | X45 | 主張：client attempts、unknown、expiry、b'、ready、resolver、scoped read、step-1。各否定例を構成。 | 通常経路では崩壊せず。 |
| 46 | X46 | ledgerのtoken/job/seq predicateを交差させ同じ試行を二重検出。 | `IN(J,T)`等で同一試行を吸収。別試行はNo.70でも確認。 |
| 47 | X47 | expiry判定Txの直前・途中・直後でクラッシュ。 | 単調な時計条件では冪等。 |
| 48 | X48 | no-replace対応FSで、復元直前に第三者が同名ファイルを生成。 | `EEXIST`で中止し保存データを上書きしない。 |
| 49 | X49 | 6種の明示操作をrecovery中に起動。 | recovery gateにより拒否または待機。 |
| 50 | X50 | 主張：NOT NULL、ledger predicate、sweep、detached expiry、future token、escape、restore、recovery gate。反証入力を個別注入。 | 通常経路は成立。新列と復元FSの交差はT01、T02、T04。 |
| 51 | X51 | seqを増やす全経路について欠番・二重増分を追跡。 | 欠番は許容、一意性は維持。 |
| 52 | X52 | expired terminalをsweepと明示retryが同時処理。 | guard付きTxで一方のみ成立。 |
| 53 | X53 | 4か所のtoken lookupについてfound/absent/unknown等8要素を比較。 | 共通規則を参照し通常経路は対称。キャンセル側の不足はT03。 |
| 54 | X54 | journal有無×flag有無×identity一致不一致を全組合せ化。 | 不一致時に自動上書きしない。 |
| 55 | X55 | current profileとtool versionを混在させ検索。 | snapshot条件で決定論的な部分集合となる。 |
| 56 | X56 | legacy escapeを新旧decoderで往復。 | canonical表現へ収束し非対称性なし。 |
| 57 | X57 | self-description、dispatch、sweepを順不同で再実行。 | 冪等条件により通常は収束。 |
| 58 | X58 | detached terminal後に結果未取得のまま再登録。 | attempts上限内での再投入は仕様どおり。未精算token交差はT03。 |
| 59 | X59 | `submit_rejected`をcharged/non-charged双方で返却。 | 分岐ledgerとsweep除外条件が一致。 |
| 60 | X60 | `G`、`\G`、`\\G`、非canonical escape、object欠損を入力。 | 可逆に解釈されphantom objectを作らない。 |
| 61 | X61 | 主張：(i)〜(iv)同一Tx、self-description、detached、submit-reject、escape、current_tool、provider契約。応答欠落を各段階で注入。 | 通常のadoption条件では崩壊せず。 |
| 62 | X62 | 旧版で相2b成功後・相3前に停止した`state=0/job_id=NULL`行へ新列を追加。 | `job_create_started_at=NULL`となりT01。 |
| 63 | X62 | 旧試行の開始時刻を残したまま時計を巻き戻し、新token発行直後・相2b前にクラッシュ。 | 未実行呼出しをfuture-skew課金扱いでき、T02。 |
| 64 | X62 | 新規行で開始時刻記録後・API呼出し前にクラッシュし、一覧が不在を返す。 | grace経過後に未作成扱いとなり、通常経路は成立。 |
| 65 | X62 | app DBバックアップを、実在ジョブ生成前の`NULL`状態へ巻き戻す。 | migration時と同じ誤証明を生じT01を補強。 |
| 66 | X63 | `state=1/job_id!=NULL`を通常キャンセルし、ledger terminal後に再登録。 | 既存job-idにより重複課金を防止。 |
| 67 | X63 | 相2b成功後・相3前の`state=0/job_id=NULL/token=T`をキャンセルし、sweep前に再登録。 | tokenが新tokenで上書きされ、T03。 |
| 68 | X63 | 完全精算・token消去済みのcancelled行をattempts上限内で再登録。 | 結果再生成として仕様どおり。 |
| 69 | X64 | token Tによる推定ledger後、同じジョブJをfoundとして採用。 | `IN(J,T)`で同一試行を二重計上しない。 |
| 70 | X64 | T1期限切れ後にT2/J2を投入し、J2のterminalを記録。 | T1 predicateはJ2を吸収せず、別試行として計上。 |
| 71 | X65 | `RENAME_NOREPLACE`等が利用可能なFSで、再lstat後に競合生成。 | 排他的renameが`EEXIST`となり安全。 |
| 72 | X65 | 排他的rename非対応FSで、再lstat後・通常rename前に競合生成。 | 競合ファイルを置換でき、T04。 |
| 73 | X65 | no-replace操作が`ENOTSUP`、`EINVAL`、`ENOTEMPTY`を返す場合を比較。 | エラー分類とfail-closed要件が未定義でT04。 |
| 74 | X66 | S01について§9.1と§21.2を相互照合。 | detached terminal化と削除3条件の両側が一致。 |
| 75 | X66 | S02のrank=1/rebuildとS03の規範SQL/置換SQLを相互照合。 | 双方一致し、SQLiteでもS02成立。 |
| 76 | X66 | 新列DDL、phase1、migration、absence判定を相互照合。 | 初期化・消去条件が不足しT01、T02。 |
| 77 | X66 | §9.1の再投入規則と§21.2のstate0キャンセルを相互照合。 | 未精算tokenを保護するguardがなくT03。 |
| 78 | 自由探索 | native/agg DDL、FTS trigger、integrity-check、rebuild、cascadeをin-memory実行。 | SQL自体の新規欠陥なし。 |

# 第3部　新規指摘

| ID | 重大度 | 箇所・引用 | 問題 | 再現シナリオ | 判定根拠 | 必須修正 |
|---|---|---|---|---|---|---|
| T01 | 致命的 | §7・846〜848行「`job_create_started_at INTEGER`」「`NULL = 相 2b 未着手`」、§9.1・1089〜1093行、§14・2184〜2191行の汎用`ADD COLUMN` | 新列追加前から存在する行、および古いapp DBを復元した行では、新列が自動的に`NULL`になる。ところが`NULL`を「API呼出しは開始されていない」という証明として使用している。旧版で相2b成功後・相3前に停止した行には、provider上にジョブが実在し得るため、この証明は成立しない。 | 旧版でtoken Tを保存→providerがJを生成→相3前にクラッシュ→新版へmigration→新列はNULL→providerの許容可視化遅延中に一覧がconfirmed-absent→未作成扱いで新token/J2を投入。JとJ2が併存する。 | C7、C10、C11、C12/X62、X66。重複ジョブと追加課金を生じ、後からJを識別できない場合がある。 | migration時、legacyの`state=0 AND batch_job_id IS NULL`を「未知」として保守的にbackfillする。UUIDv7時刻等から開始時刻を設定するか、明示的な`legacy_unknown`状態を追加する。`NULL=未着手`は新版が同一ライフサイクル内で生成したことを証明できる行に限定する。バックアップ復元・schema rollbackにも同じ扱いを適用する。 |
| T02 | 致命的 | §9.1・1010〜1024行のphase1更新項目、1043〜1046行「相2b直前に設定」、846〜848行「再試行では上書き」、1086〜1093行のfuture-skew判定 | 新しい`intent_token`を発行するphase1が、前試行の`job_create_started_at`を消去しない。通常は新token時刻が後なので隠れるが、時計巻戻し後には旧開始時刻が`max(token時刻, started_at)`に残り、新しいAPI呼出しをまだ実行していないのにfuture-skew分岐へ入れる。 | 試行1でS1を記録→時計をS1より5分超巻き戻す→試行2のtoken T2を発行→相2b前にクラッシュ→一覧confirmed-absent→旧S1が採用され、未実行の試行2を推定課金・attempt消費扱い。繰返すと偽ledgerを追加して上限到達する。 | C7、C10、C11、C12/X4、X62、X66。実際には行っていないAPI呼出しへの課金記録と回復不能なterminal化を生じ得る。 | 新しい`intent_token`を書き込むすべてのTxで`job_create_started_at=NULL`を同時設定する。retry、rotation、requeue、profile再投入を含める。値は相2b直前にのみ設定し、tokenと開始時刻の世代一致をconstraintまたはgeneration IDで検証する。 |
| T03 | 致命的 | §9.1・985〜996行の`state=3 && attempts<limit`再投入、1256〜1268行の「state0でも実ジョブが存在し得る」、§21.2・2820〜2841行のキャンセル・ledger・detached規則 | `state=0/job_id=NULL`だがprovider上にジョブがあるケースについて、キャンセル時の3値token lookup、job-id採用、seq/attempt、ledgerを一体化する規則がない。キャンセル済みのstate3を再登録すると、phase1が旧tokenを新tokenで上書きでき、旧ジョブの唯一の検索キーと課金証跡を失う。 | 相2bでJ生成→相3前にクラッシュし`state=0, job_id=NULL, token=T`→unregisterがT経由でJのキャンセルを確認するがjob-id/ledgerを保存せずstate3化→step 4.5 sweep前に再登録→state3再投入がTをT2へ置換→旧Jを精算不能のままJ2を投入。 | C7、C10、C11、C12/X63、X66。課金漏れ、重複投入、provider側ジョブとの恒久的不整合が発生し得る。実装判断に委ねられており一意に実装できない。 | `state=0/server/job_id=NULL`のキャンセル前に共通3値token lookupを必須化する。foundならjob-id採用、self-description、必要なseq/attempt更新、キャンセル、terminal ledgerを一つの規定Tx系列で行う。unknownはdetachedのまま保持し、confirmed-absentは開始時刻規則へ送る。未精算`intent_token`が残る間はphase1のtoken rotationと再投入を禁止する。 |
| T04 | 致命的 | §21.4・3038〜3052行「可能なプラットフォームでは`RENAME_NOREPLACE`/EXCL/MoveFileEx」「残る窓は既知かつ不可避」 | raw path不在時の安全性が、排他的no-replace renameを提供する環境にしか成立しない。非対応FSで通常の置換renameへfallbackすることを禁止しておらず、再lstat後に作成された第三者ファイルを上書きできる。エラーコード別の必須動作も未定義。 | raw不在を確認→mandatory re-lstatでも不在→別プロセスが未保存ファイルXを作成→対象FSがno-replaceを`ENOTSUP`/`EINVAL`で拒否→通常renameへfallback→Xを置換。 | C10、C11、C12/X65。コミットされていないユーザーデータを不可逆に失うため致命的。競合窓を既知と記すだけでは安全要件にならない。 | raw不在のin-place restoreは、排他的no-replace意味論を保証できないFSでは必ずfail-closedとする。`EEXIST`/`ENOTEMPTY`は競合、`ENOTSUP`/`EINVAL`は機能非対応として復元を中止し、通常renameへfallbackしない。代替を認める場合は`O_CREAT|O_EXCL`等を用いた同等の排他プロトコルを規範化する。 |

# 第4部　検出観点の総括

- 検出0：C1、C2、C3、C4、C5、C6、C8。
- C9：既往432項目について`partially fixed`、`not fixed`、`regression`はいずれも0。
- 検出あり：C7＝T01〜T03、C10＝T01〜T04、C11＝T01〜T04、C12＝T01〜T04。
- P1〜P8、P10〜P15：原則反映を確認し、独立した欠陥は検出しなかった。
- P9：原則の記述自体は反映されているが、ジョブ生成時刻・キャンセル・token rotationの交差でT01〜T03を検出した。
- P16：原則の記述自体は反映されているが、no-replace非対応FSの復元でT04を検出した。