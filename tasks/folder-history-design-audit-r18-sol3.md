不合格
target.md 全 3207 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第 1 部 — 回帰確認（C9）

全 450 項目を判定した。

- superseded:
  - r7: F05→I14、F07→I15、F12→I16/I17、F21→I03/I04、H04→I31、H15→I08/I11、H18→I16、H22→I15、A11（遷移詳細）→I05/I06/I13/I14、H02（衝突順）→I32。
  - r8: I03/I04（cost）→J06、I05/I06→J01/J02、I09/I11→J03、I15→J04、I16/I17→J05/J01、I35→J13〜J16。
  - r9: J04→K01、J06（UNIQUE）→K02、J03→K10、J10→K09、J13→K16、J16→K13〜K15、I12→K04、D08→K20、A01→K25。
  - r10: K02→L01、K12/K13→L04、K06→L02、K09→L03、K14→L07、J07/K24→L09、K11（旧残余）→reconcile close、K21→L20、K19→L13。
  - r11: L09→M03、L28→M03/M09、L20→M04、L04/L21→M02。
  - r12: M09→N05/N06、M10→N10、M12→N38、M29→N15、M06/K08→N17、L07/M05→N16、L26→N14、M01→N09、M08→N28、M13→N30。
  - r13: N03→O05/O06、N04→O02/O03、N13→O21、N15→O04/O25、N36→O16、N39→O14、N40→O28、N28→O13、N07→O12、§21.5旧M&S記述→O29。
  - r14: O28→Q01、O17→Q02、O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O18→Q23、O19→Q24、O13→Q12、O30→Q37。
  - r15: Q02→R01、Q04→R02、Q09→R03、Q12→R04、Q03→R05、Q05/Q06→R06、Q06（sweep前段）→R07、Q10→R14、Q13/Q14→R15/R16。
  - r16: R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06。
  - r17: S06→T09、S07→T05/T06、S11→T07、S19→T03、S20→T01、S23→T18、S24→T02、S25→T04。
- fixed: 上記 superseded の旧期待部分および T08/T10/T16 を除く、A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S29 / T01〜T18 の全項目。

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
|---|---|---|
| T08 | partially-fixed | §9.1 は「残骸掃除・NULL 化…完了してから相1」を要求する一方、同じ相1で「外部 upload 削除は app Tx の外」「削除は失敗しても続行する」とする。token sweep は「成功した行の intent_token を NULL」とするため、削除失敗時にガード完了とrotation続行を同時に満たせない。 |
| T10 | partially-fixed | §6 は「実際に upload した bytes（変換物）」「原本は upload しない」とするが、同節は「upload 済み原本の file id」、§9.1相2aは「原本 upload」と再掲する。Office文書では参照すべき原本file idが存在しない。 |
| T16 | partially-fixed | §11.2は「fts_hits（およびKNNのk）には内部上限（LIMIT :fts_cap）を置く」とするが、「実行可能な完全形」の `fts_hits` は `MATCH :query` の直後に閉じ、上限も決定的な打切り順もない。§19は別名 `:k_fts` の導入を将来課題としている。 |

## 第 2 部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | 既存コミット後、同一tick間にファイル作成→編集→削除。walk、fp_cache、pending_deletes、最終stat、commit生成を順に追跡。 | 問題なし。最終観測状態だけが履歴へ反映される。 |
| 2 | X2 | 改行・制御文字・`obj:`・画像コメント風文字列・`..`・絶対パス・symlinkを含む入力をscan→materialize→restore。 | 問題なし。名前検証、escape、object実在検査、dirfd拘束で拒否または安全に保持。 |
| 3 | X3 | NFD名を持つcase-insensitiveボリュームからcase-sensitiveボリュームへ移動し、case違い実体を追加。 | 問題なし。NFC論理名、raw resolver、BINARY優先、sensitive方向overrideで収束。 |
| 4 | X4 | 壁時計を後退させ、同一msで連続コミット・派生置換を実行。 | 問題なし。`max(now, old+1)`とhash tie-breakで単調性を維持。 |
| 5 | X5 | eligible 100万chunkを同一語に一致させ、`:limit=20`、`:fts_cap=1000`で掲載SQLを追跡。 | U05を検出。全ヒットがrank・RRF・sortへ流れる。 |
| 6 | X6 | 日本語2文字query、vec0 KNN、float32 BLOB、JCS数値、UUIDv7未来時刻を各境界へ投入。 | 問題なし。短語fallback、形式検査、未来skew規則で閉じる。 |
| 7 | X7 | 旧schema DBを新アプリで開き、migration途中クラッシュ後に旧アプリでも開く。 | 問題なし。version/migration gateとfail-closedで混在書込みを防止。 |
| 8 | X8 | 別ユーザー権限のtmp/objects、`../`復元先、絶対パス、外部symlinkを使用。 | 問題なし。権限、論理名検証、root dirfd、scoped readで逸脱しない。 |
| 9 | X9 | objects書込み、metadata Tx、app Tx、restore renameの各直前でディスク満杯にする。 | 問題なし。順序・fsync・次tick再駆動により未参照objectか未完状態へ限定。 |
| 10 | X10 | `.folder-history`を手動削除・部分編集し、同期ソフトの競合コピーを混入。 | 問題なし。missing/damaged/conflict分類とfsck・bootstrap導線が機能。 |
| 11 | X11 | profile変更、FTS view trigger、floor、画像filter変更を同一tickで交錯。 | 問題なし。派生削除、再チャンク、差集合充填、台帳保持が分離される。 |
| 12 | X12 | watch登録→DOCX追加→commit→OCR submit→JSONL生成→collect→検索→restoreを通しで追跡。 | U03を検出。JSONLが要求する「upload済み原本」のfile idで途切れる。 |
| 13 | X13 | 対応Office原本に対し固定版コンバータを削除し、明示再生成を実行。 | U04を検出。失敗時の状態・retry・terminal操作が未定義。 |
| 14 | X14 | upload・job作成・collectを順に429（Retry-Afterなし）へ倒す。 | 問題なし。既定backoffが `retry_not_before` に永続化される。 |
| 15 | X15 | 「成果優先」「intentで二重job防止」「readyは空を通さない」「restoreはworking変更を保全」「内部capで中間膨張防止」の5主張を反証試行。 | 前4主張は破れず。内部cap主張はU05で破れた。 |
| 16 | X16 | server相2b成功→相3前クラッシュ→state=0/id=NULLをDDLコメントとintent回復の双方で解釈。 | U01を検出。さらに成果既存化後のcloseでU06を検出。 |
| 17 | X17 | register各境界クラッシュ→fork→restore→unregister→再登録し、tick.lockとの排他を追跡。 | 問題なし。journalと回復先行で一意に再開。 |
| 18 | X18 | orphan profile、部分walk失敗中のpending_deletes、app全損後のcost_ledgerを追跡。 | 問題なし。破損検出、walk完全性条件、台帳下限性が明示される。 |
| 19 | X19 | prefix object fsync、migration Tx、submit相1/2/3、fork各phaseで電源断を反復。 | 問題なし。各境界に再実行可能な耐久状態が残る。 |
| 20 | X20 | 重複job有界化、月次配賦、profile収束、fork整合、delete見逃し防止、rename耐久の6主張を反証試行。 | 後5主張は破れず。重複job主張はDDLコメントとの不整合U01を検出。 |
| 21 | X21 | profile A→B、相1後クラッシュ、vec部分充填、agg building/ready更新を同時進行。 | 問題なし。snapshot、差集合、ready gateで旧空間混入を防ぐ。 |
| 22 | X22 | forkの全phaseでクラッシュし、app全損、フォルダ移動、並行registerを組み合わせる。 | 問題なし。journal・flag・repository-idにより再開点が一意。 |
| 23 | X23 | app_config任意key、NULL cost、detached行、name_collision/name_invalidを各readerへ入力。 | 問題なし。存在条件、status、削除gateが一致。 |
| 24 | X24 | 「vec差集合は中断後も充填」「毎tick agg検査は破棄喪失を吸収」「client queueはintent回復不要」を次元変更中に反証試行。 | いずれも破れず。 |
| 25 | X25 | app.sqlite単独横断検索、in-place/export restore、watch_root解除後の登録folder walkを実行。 | 問題なし。app_config、宛先別規範、folders起点が入力を供給。 |
| 26 | X26 | server job作成後・相3前クラッシュ→別経路で成果既存化→reconcile close→成果drop。 | U06を検出。物理jobがattemptsへ加算されない。 |
| 27 | X27 | journal書込みから削除まで全境界でクラッシュし、削除失敗・破損・bootstrapを組み合わせる。 | 問題なし。phaseとdigestにより通常履歴へ誤復帰しない。 |
| 28 | X28 | detached生成3経路をstate 0〜3で処理し、途中で同じrepositoryを再登録。 | 問題なし。payload破棄、記帳、掃除、再投入の意図されたコストへ収束。 |
| 29 | X29 | case-only rename、NFC衝突、sensitive移動後の大小2実体を検索・restoreへ渡す。 | 問題なし。固定保存名とresolver tie-breakが一致。 |
| 30 | X30 | ledger UNIQUE、client上限、fork再開、case-only FK、30秒delete、detached記帳の6主張を反証試行。 | いずれも破れず。 |
| 31 | X31 | reconcile found close、client前計上、detached採用、submit_rejected retryを同一行で順次実行。 | U06を検出。reconcile foundだけattemptsが増えない。 |
| 32 | X32 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE各phaseに通常クラッシュ、app全損、第三idを投入。 | 問題なし。damaged停止を含め帰結が一意。 |
| 33 | X33 | server/client × 全終端理由 × collect/reconcile/detachedの課金行列を追跡。 | U06を検出。reconcile found/期限超のattempt計数セルだけ欠落。 |
| 34 | X34 | §11.2完全SQLをeligible、ready gate、LIKE fallback、FF時点指定と結合して実行。 | U05を検出。`:fts_cap`が掲載SQLに存在しない。 |
| 35 | X35 | seq継承、reconcile close、submit_rejected、fork、detached、delete最終statの6主張を反証試行。 | いずれも破れず。 |
| 36 | X36 | profile A→B→A、相2b成功→相3前クラッシュ→A成果でB行close→再度Bへ変更。 | U06を検出。Bの未計数jobに加え上限回数を再投入できる。 |
| 37 | X37 | damaged/missing/forkを母数から出入りさせ、P2→P3→P2とready/syncedを追跡。 | 問題なし。0件非更新とNULL化で空・旧readyを防ぐ。 |
| 38 | X38 | fork中にフォルダ移動、app全損、journal digest不一致を同時発生。 | 問題なし。未完forkをdamagedとして停止。 |
| 39 | X39 | 一時読取不能、別repository-id、対象外型への置換、rebind、再登録を交錯。 | 問題なし。4分類とfp_cache削除が一貫。 |
| 40 | X40 | close Tx、ready、fork移動、一時読取不能、profile TOCTOU、距離変更の6主張とstandalone/NFC/code-fenceを反証試行。 | いずれも破れず。 |
| 41 | X41 | 全終端理由をserver/client・全close経路で走査し、state=0 server成果ありcloseを重点追跡。 | U01とU06を検出。 |
| 42 | X42 | damaged中にA/Bだけでready成立→C復旧→Cのsynced NULL→再複製。 | 問題なし。readyは構築時宣言として維持され、未embed数をstatus化。 |
| 43 | X43 | resolver 3呼出点 × NFD/NFC/両方/不在 × case感度の全組合せを追跡。 | 問題なし。collision、中止、新規作成が同じ規則に従う。 |
| 44 | X44 | 登録済みreadの一時EIO、standalone read、conflict複製、step -1 unreadableを実行。 | 問題なし。status/provenanceと書込み抑止が一意。 |
| 45 | X45 | client中間記帳、unknown保持、期限超記帳、state=0 close、ready、resolver、scoped read、step -1の8主張を反証試行。 | 7主張は破れず。「state=0 server」の説明はU01で破れた。 |
| 46 | X46 | token推定記帳→job発見→相3→collectをseqとledger突合キーごとに追跡。 | U06を検出。reconcile期限超のseqは進むがattemptsが進まない。 |
| 47 | X47 | 期限超記帳後、旧token upload削除を429にし、明示retryでrotationを試行。 | U02を検出。完了待ちと失敗続行が両立しない。 |
| 48 | X48 | working内容を保全commit→rename直前に変更→restore中止→再試行。 | 問題なし。再lstat/no-replaceと次tick scanで喪失しない。 |
| 49 | X49 | 未完forkを残してregister/unregister/fork/restore/watch/dropを各々開始。 | 問題なし。回復不能時は後続操作を開始しない。 |
| 50 | X50 | NOT NULL記帳、推定行冪等性、sweep回収、未来token、escape往復、restore保全、fork回復の8主張を反証試行。 | いずれも破れず。 |
| 51 | X51 | found採用、期限超、detached、client前計上、行削除再作成のseq連番を追跡。 | U06を検出。seq更新に対応するattempts更新が2経路で欠落。 |
| 52 | X52 | expired terminal→sweep→削除前に明示retryし、旧upload削除を失敗させる。 | U02を検出。rotationの可否が一意でない。 |
| 53 | X53 | intent回復・detached・reconcile・sweepの4照合点を三値、期限、猶予、seq、attemptsで比較。 | U06を検出。reconcileとsweep期限超だけattempts要素が欠落。 |
| 54 | X54 | journal有効/破損/無 × flag有無 × id old/new/第三/読取不能を全組合せ追跡。 | 問題なし。回復、保留、damaged、明示解決が一意。 |
| 55 | X55 | embedding混在・tool混在、同時刻派生、空文書、backfill OFFで単独/横断検索。 | 問題なし。current profile/tool決定と縮退statusが明示される。 |
| 56 | X56 | canonicalでない画像風行をescape→解析→materializeし、FTSとpreviewを比較。 | 問題なし。拡張decoderにより安全側かつ可逆。 |
| 57 | X57 | found自己記述化後のstate 0/2/3、dispatch、idx_batch_open、sweepを追跡。 | 問題なし。自己記述行も掃除/NULL化対象に残る。 |
| 58 | X58 | detached terminal後に同repositoryを再登録し、state 2/3を再投入。 | 問題なし。意図された有界再課金として台帳に残る。 |
| 59 | X59 | 課金する4xx providerでsubmit_rejected→sweep→明示retry→再拒否。 | 問題なし。拒否分岐内のseq更新・記帳で二重/欠落なし。 |
| 60 | X60 | 0個以上のbackslash、canonical/非canonical/object不在をescape・decode・再materialize。 | 問題なし。可逆性、phantom防止、text_hash安定が同時成立。 |
| 61 | X61 | 「偽expiredなし」「二重記帳なし」「detached非deadlock」「拒否token非残留」「往復可逆」「tool決定的」を反証試行。 | 後5主張は破れず。rotationを伴う非deadlock性はU02で破れた。 |
| 62 | X62 | job_create_started_at記録前後・呼出前後でクラッシュし、時計後退とrequeueを反復。 | 問題なし。相1の4列NULL戻しとbackfillで旧時刻を継承しない。 |
| 63 | X63 | cancel確定→再登録→明示retry→再unregister→再cancel。 | 問題なし。上限、ledger、token sweepが各cycleを分離。 |
| 64 | X64 | token推定行がある状態で別attemptのjobをfoundし、IN述語と自己記述化を追跡。 | 問題なし。provider採用条件下では別attemptを過吸収しない。 |
| 65 | X65 | no-replace非対応をEINVALで検出後、再lstat→通常rename、EEXISTも発生。 | 問題なし。非対応fallbackと競合中止が一意。 |
| 66 | X66 | 規範をDDLコメント・SQL・§間要約と横断比較。 | U01、U03、U05を検出。state説明、Office投入物、検索capが非伝播。 |
| 67 | X67 | terminal旧tokenの残骸削除を429にし、同tickで明示retry相1へ進める。 | U02を検出。guardなら保留、相1規則なら続行となる。 |
| 68 | X68 | cancelでattempts上限→retryで0→再cancelし、掃除失敗中にもretry。 | U02を検出。通常cycleは有界だが掃除失敗時のrotationだけ未定義。 |
| 69 | X69 | FTS/KNN各100万候補、同点多数、cap=1000、limit=20でRRF境界を反復。 | U05を検出。cap自体と決定的打切り順が掲載SQLにない。 |
| 70 | X70 | converter v1でDOCX投入後、v2へ更新しv1を削除。再生成時に変換失敗も発生。 | U03、U04を検出。参照file idが矛盾し、変換失敗分岐もない。 |
| 71 | 自由 | attempts=0のserver jobを相2bで作成→相3前クラッシュ→既存成果でreconcile→成果drop→3回再投入。 | U06を検出。物理jobは計4回となり既定上限3を超える。 |
| 72 | 自由 | 掲載DDLをin-memory SQLiteで生成し、FTS5 external-content view/trigger、insert/delete、`integrity-check`を実行。 | 問題なし。vec0固有DDLを除くSQLite構文・制約・FTS連携は成立。 |

## 第 3 部 — 新規検出

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| U01 | fatal | §9.1 DDLコメント「server 経路の state=0 では NULL（まだ job が無い）」／intent回復「batch_job_id NULL の state=0…intent_token 一致を探す」「found = 採用」 | `state=0`かつid=NULLでも相2b完了・相3前クラッシュならjobが実在する。DDLコメントを実装契約として使うと未作成扱いで再投入し、二重課金する。 | 相1→相2bでjob J作成→相3前クラッシュ→行はstate=0/id=NULL→コメントに従いJを照合せず再投入→J2作成。 | P9/C1/C7/C12/X16/X20/X41/X45/X66 | コメントを「jobは未作成、または作成済みだが未採用」に修正し、server state=0は必ず三値intent回復へ送る。 |
| U02 | major | §9.1「残骸掃除・NULL化…完了してから相1」／同節「外部 upload 削除は app Tx の外」「削除は失敗しても続行する」 | 旧token掃除失敗時、rotationを待つ規範と続行する規範が両立しない。続行すると旧token/upload_idを上書きし、未記録uploadの探索キーをTTLまで失う。 | terminal行token=T・残骸U→明示retry→U削除が429→続行して相1でTをT2へ上書き→Uを再駆動できない。 | P9/C10/C11/C12/X47/X52/X61/X67/X68/T08 | 「照合・記帳完了」と「外部残骸掃除」を分離する。掃除失敗時は旧token/uploadを別の耐久行へ保持してからrotationするか、相1を保留する。 |
| U03 | major | §6「実際に upload した bytes（変換物）」「原本は upload しない」／同節「upload 済み原本の file id」／§9.1「原本 upload」 | Office文書では変換PDFだけがuploadされるため、JSONLが要求する原本file idが存在しない。原本もuploadすれば前段規範に違反する。 | DOCX D→一時PDF P→Pだけupload→JSONL生成時にDのfile idを要求され停止。 | P6/C1/C6/C10/C11/C12/X12/X66/X70/T10 | 全再掲を「upload済み投入物のfile id（PDF/画像は原本、Officeは変換PDF）」へ統一し、`upload_id`も同じ定義にする。 |
| U04 | major | §6「版付き決定論的コンバータ…PDFへ変換してから投入」／失敗終端は `unsupported_format` と `oversize` のみ | 固定版コンバータの不在・起動失敗・決定論的変換エラーについて、一時失敗、terminal、retryのいずれにするか未定義で、追加設計なしに実装できない。 | 対応DOCX・512MB未満→固定版converter不在→upload前に失敗→相2a/2bの失敗規則も適用できず行状態が定まらない。 | P6/C8/C11/C12/X13/X70 | converter失敗を一時/恒久に分類し、error値、attempts、retry_not_before、profile変更後の再判定を規定する。 |
| U05 | major | §11.2「実行可能な完全形」の `fts_hits` は `MATCH :query` 直後に終了／後段「LIMIT :fts_capを置く」／§19「:k_fts導入」 | 掲載SQLが`:fts_cap`を参照せず、100万件級ヒットを全件rank・fusion・sortする。単にLIMITを足しても打切り前のORDER BYが未定義で再現性を保証できず、KNN側のbind名・上限とも不一致。 | eligible 100万件、`:limit=20`、`:fts_cap=1000`→掲載SQLは100万件を処理し、cap到達時の候補集合も定まらない。 | P12/C1/C4/C6/C8/C10/C11/C12/X5/X15/X34/X66/X69/T16 | 完全SQLに決定的なFTS事前cap CTEとKNN clampを実装し、tie-break・cap到達status・bind名を`:fts_cap`へ統一する。 |
| U06 | major | §9.1 reconcile (b') found「submission_seqを+1…記帳し…batch_job_idへ発見job id」／同期限超「submission_seq+1…記帳」／token sweep期限超も同じ。一方、intent回復・detached・sweep foundは「attempts+1」を明記 | reconcile found、reconcile期限超、token sweep期限超の3経路だけ、作成済みまたは作成済みであり得た物理attemptを再試行guardへ加算しない。同一profileで設定上限を超えるjobを作成できる。 | attempts=0→相2bでJ作成→相3前クラッシュ→別経路で同profile成果を既存化→reconcileがJをfoundしてstate=2/ledger記帳するがattempts=0→成果drop→既定上限3回を追加投入し、物理jobは計4回。 | P8/P9/C7/C10/C12/X16/X26/X31/X33/X36/X41/X46/X51/X53/自由71 | 3経路とも、未記帳時のseq更新・ledger追記と同一Txで`attempts=attempts+1`を行う。上限到達時のterminal化もintent回復と対称に規定する。 |

## 第 4 部 — 確認済みの列挙

- 検出0件の検査観点: C2（全DDL、CHECK/PK/FK、FTS5 external-content rowid、trigger対称性、省略DDL）、C3（全§参照）、C5（価格・次元・RRF・件数等の数値）。
- 検出0件の原則: P1、P2、P3、P4、P5、P7、P10、P11、P13、P14、P15、P16。