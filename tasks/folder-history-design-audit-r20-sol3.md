不合格
target.md 全 3348 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第 1 部 — 回帰確認（C9）

A01〜V20 の全 494 項目を確認した。V01・V02・V09 を除く 491 項目は fixed または audit-prompt.md の対応表どおり superseded（対応先も fixed）。r16〜r19 の置換表も対応先で判定した。

| ID | 判定 | 根拠（§ + 短い引用。残存・欠落箇所） |
| --- | --- | --- |
| V01 | regression | §6 は「upload 済み入力（原本 — Office 文書は変換 PDF）」へ統一している一方、§9.1 相2a に「TTL まで機密原本が追跡不能で残る」が残る。Office 文書で実際に残るのは変換 PDF であり、upload 対象語が非伝播。 |
| V02 | regression | §9.1 batch_requests DDL は completed_at を「確定する全ての UPDATE で同時に書く」「reconcile / submit_rejected / … / abandoned も」と定義した直後に、「書込点は §10 collect」と限定する旧コメントが残る。 |
| V09 | partially-fixed | §20.5 は「scan_cache に syntax_fail_count / first_failure_at を記録」と規定するが、§9.1 の scan_cache DDL は verified_at までで両列が存在しない。SQLite 3.51.0 の in-memory DB で同 DDL後の INSERT は `table scan_cache has no column named syntax_fail_count` となった。 |

## 第 2 部 — 探索ログ（C12）

X1〜X78 を各1件以上、自由探索4件を加えた計82シナリオを実行した。

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
| ---: | --- | --- | --- |
| 1 | X1 | 未追跡名 → 同一 tick 前に作成・編集・削除 → 完全 walk と LWW 生存集合を照合 | 問題なし |
| 2 | X2 | `-->`、多重 `\`、偽 `obj:`、不在 image_hash を含む OCR 本文 → materialize → parse | 問題なし |
| 3 | X3 | NFD・case-insensitive 上の系列 → case-sensitive ボリュームへ移動 → resolver と再 walk | 問題なし |
| 4 | X4 | 時計後退中に同一 ms で複数変更 → created_at クランプ → commit_hash tie-break | 問題なし |
| 5 | X5 | 10万ファイル・100万 chunk → walk、fp、FTS cap、KNN refill、集約全置換を順に適用 | 問題なし |
| 6 | X6 | 日本語2文字検索・2^53超 size・異なる metric → LIKE fallback・文字列化・vec受理検証 | 問題なし |
| 7 | X7 | 旧版DBを新版が開く → tick.lock下 migration途中で電断 → 再起動 | 問題なし |
| 8 | X8 | `../`、絶対パス、symlink、他ユーザー可読DACL → register・scan・restore | 問題なし |
| 9 | X9 | object rename後、metadata Tx中、app Tx前の各位置でディスク満杯 → 次 tick | 問題なし |
| 10 | X10 | `.folder-history` 手動削除・部分同期・zip往復 → 照合、damaged、deep-scan | 問題なし |
| 11 | X11 | raw名fpとNFC論理名、FTS view trigger、floorとreconcileを同時に作動 | 問題なし |
| 12 | X12 | watch_root登録 → OCR → embed → replicate → 検索 → 原本解決 → restore | 問題なし |
| 13 | X13 | state=0 client／state=1 server に対して明示 abandon → 台帳・掃除・終端を追跡 | W06・W07を検出 |
| 14 | X14 | submit・collect・intent回復が429、Retry-Afterなし → backoffと次tick | 問題なし |
| 15 | X15 | 主張: floorが明示再生成を守る／試行: floor書込後・metadata更新前後でクラッシュ／破れず | 問題なし |
| 16 | X16 | 共有uploadを持つ複数target → 一部close → retry・cleanup | 問題なし |
| 17 | X17 | register途中クラッシュ → fork → restore → unregister → 再登録 | 問題なし |
| 18 | X18 | syntax validation 1回目失敗 → scan_cacheへ失敗回数を永続化 | W01を検出 |
| 19 | X19 | object・journal・repository-idのrename直後に電断 → fsync規範で再開 | 問題なし |
| 20 | X20 | 主張: server重複jobは最大1／試行: job作成後・相3前クラッシュ→一覧found／破れず（採用条件内） | 問題なし |
| 21 | X21 | profile切替中に相1・collect・floor再チャンク・vec再充填を交錯 | 問題なし |
| 22 | X22 | forkの全phaseでクラッシュし、対象フォルダを途中移動 | 問題なし |
| 23 | X23 | submit_rejectedでstate=3へ確定 → completed_atのDDLコメントだけで実装 | W03を検出 |
| 24 | X24 | 主張: vec差集合が部分充填を修復／試行: DROP後・半数INSERT後にクラッシュ／破れず | 問題なし |
| 25 | X25 | app.sqliteのみで横断query embed、watch_root解除後のfolders起点walk | 問題なし |
| 26 | X26 | attempts reset、submission_seq、ledger MAX継承を複数再投入で追跡 | 問題なし |
| 27 | X27 | journal作成から削除まで全境界でクラッシュ、app全損も挿入 | 問題なし |
| 28 | X28 | unregister由来detachedをstate 0/1/2/3別にcollect・掃除・再登録 | 問題なし |
| 29 | X29 | case-only rename後にvolume感度を反転し、保存論理名・FK・LWWを追跡 | 問題なし |
| 30 | X30 | 主張: seq継承・client上限・fork journal・保存名固定／代表クラッシュ列で反証／破れず | 問題なし |
| 31 | X31 | reconcile closeのfloor、記帳、token掃除とMAX継承を連続実行 | 問題なし |
| 32 | X32 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE × old/new/第三id | 問題なし |
| 33 | X33 | server/client × 成功・timeout・missing・invalid_output等の課金行列 | 問題なし |
| 34 | X34 | 掲載FTS SQL、inner fts_cap、LIKE差替え、最終tie-breakを空DBで静的実行 | 問題なし |
| 35 | X35 | 主張: 行削除後もseq衝突なし／試行: ledger MAX=5で再登録・再投入・close／破れず | 問題なし |
| 36 | X36 | profile A→B→Aで同一seqのterminal記帳とreconcile closeを再観測 | 問題なし |
| 37 | X37 | building P2でA/B完了、C missing→復帰、syncedとreadyを逐次評価 | 問題なし |
| 38 | X38 | fork途中移動、app全損、journal digest不整合を組み合わせる | 問題なし |
| 39 | X39 | register時一時EIO、同root別id、raw delete確認、detached再登録 | 問題なし |
| 40 | X40 | 主張: ready・一時読取・raw resolver・query hash gate／代表反例を投入／破れず | 問題なし |
| 41 | X41 | 全terminal理由 × collect/reconcile/detached/client再実行前記帳を総当り | 問題なし |
| 42 | X42 | damaged除外中にready成立 → folder復帰 → synced NULLから再複製 | 問題なし |
| 43 | X43 | NFD/NFC/両方/不在 × case感度 × delete/restore/fsck resolver | 問題なし |
| 44 | X44 | 登録済みpath一時EIO、standalone重複、step -1 regressedを同tickで処理 | 問題なし |
| 45 | X45 | 主張: unknown・期限超・ready・resolver・step -1の防御／境界クラッシュで反証／破れず | 問題なし |
| 46 | X46 | token推定記帳後にjob idが可視化 → IN述語・自己記述化・再駆動 | 問題なし |
| 47 | X47 | 期限超(i)〜(iv)の各DB書込境界でクラッシュ → 同一Tx再実行 | 問題なし |
| 48 | X48 | 未取り込みworking変更 → in-place restore → 保全commit → 次scan | 問題なし |
| 49 | X49 | 各§21操作の直前に未完forkを置き、回復不能journalも投入 | 問題なし |
| 50 | X50 | 主張: 無id記帳・decoder・restore保全・回復先行／操作列で反証／破れず | 問題なし |
| 51 | X51 | deadline・(b')・sweep・detachedのseq更新を1行で連続発生 | 問題なし |
| 52 | X52 | expired terminal → sweep → unregister → 明示retry → 新token | 問題なし |
| 53 | X53 | intent回復・detached・(b')・sweepのfound/absent/unknownを8要素比較 | 問題なし |
| 54 | X54 | journal有効/破損/無 × flag有無 × id old/new/第三/読取不能 | 問題なし |
| 55 | X55 | embedding混在中、tool同時刻tie、一括変換で旧toolのgenerated_at更新 | 問題なし |
| 56 | X56 | 非canonical `\![diagram](obj:see appendix)` を保存・parse・preview | 問題なし |
| 57 | X57 | found自己記述化直後にクラッシュ → dispatch・sweep・再投入 | 問題なし |
| 58 | X58 | detached terminalを掃除前に再登録 → state 2/3の遷移表を適用 | 問題なし |
| 59 | X59 | 課金される4xx providerでsubmit_rejected → 分岐内記帳 → sweep除外 | 問題なし |
| 60 | X60 | G・`\G`・`\\G`、不在hash、非canonical行をescape/un-escape | 問題なし |
| 61 | X61 | 主張: r15の1Tx・自己記述化・detached・decoder防御／全境界で反証／破れず | 問題なし |
| 62 | X62 | job_create_started_at記録後・呼出前クラッシュ → 同scope/別scopeで回復 | 問題なし |
| 63 | X63 | cancelled → token sweep → 再登録 → retry → 再cancel | 問題なし |
| 64 | X64 | token推定行後、同tokenの遅延jobをfound → IN(job,token)判定 | 問題なし |
| 65 | X65 | no-replace非対応、EEXIST、再lstat後の通常renameを分岐実行 | 問題なし |
| 66 | X66 | 規範・DDLコメント・要約を横断し、upload対象語とcompleted_atを比較 | W02・W03を検出 |
| 67 | X67 | state=3 token残存 → rotation guardがunknown → stalled → abandon | W06を検出 |
| 68 | X68 | cancelled行を明示retry後、再unregister・再cancel | 問題なし |
| 69 | X69 | FTS大量同点をfts_cap境界で切り、KNNとのRRFを反復 | 問題なし |
| 70 | X70 | Office converter更新・旧版消失・変換後oversize・convert_failed | 問題なし |
| 71 | X71 | state=0期限超requeueとclient dispatchでrotation guard非適用を検証 | 問題なし |
| 72 | X72 | abandon後に旧jobが可視化、続いて明示retry・新tokenを投入 | W06・W07を検出 |
| 73 | X73 | 旧toolのconvert_failed残置 → tool変更 → 新target_key投入 | 問題なし |
| 74 | X74 | 同一stat tupleの構文失敗、途中EIO、成功resetを3 tickで追跡 | W01を検出 |
| 75 | X75 | scope A記録後・API呼出前にcredentialをBへ変更、またstable scope ID無しproviderを使用 | W04・W05を検出 |
| 76 | X76 | state=0 client／state=1 server／state=3 token残存でabandonし、削除・再登録まで追跡 | W06・W07を検出 |
| 77 | X77 | 10万dir中の登録folderだけfork-journalをlstatし、fp一致skipを反復 | 問題なし |
| 78 | X78 | state=2・未掃除tokenへfloor設定とattempts reset → guard found → 新OCR投入 | W08を検出 |
| 79 | 自由 | scan_cache DDLをin-memory SQLiteへ作成 → syntax_fail_count付きINSERT | W01を検出 |
| 80 | 自由 | DOCXをPDF変換してupload → 相2a直後クラッシュ → 保持対象の文言を照合 | W02を検出 |
| 81 | 自由 | submit_rejected・cancelled・abandonedをcollect外で確定 → DDLコメントを二通りに実装 | W03を検出 |
| 82 | 自由 | state=1、J既知、seq=1の行をabandon → seq・ledger.batch_job_idを追跡 | W07を検出 |

## 第 3 部 — 新規検出（C1〜C8、C10〜C12）

| ID | 重大度 | 該当箇所（§ + 短い引用） | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
| --- | --- | --- | --- | --- | --- | --- |
| W01 | fatal | §9.1 scan_cache DDL は `verified_at` の次が主キー。§20.5 は「syntax_fail_count / first_failure_at を記録」 | 必須状態を保存する列がなく、有界構文スキップをSQLで実装不能。実行すると存在しない列エラーになる。 | 安定した破損DOCX → 構文検証失敗 → `syntax_fail_count=1` をUPSERT → `no column named syntax_fail_count` でtick失敗し、3回/24hの収束へ到達不能 | P16 / C2 / C4 / C9(V09) / C11 / X18 / X74 | scan_cache に `syntax_fail_count INTEGER NOT NULL DEFAULT 0` と nullable `first_failure_at INTEGER`、非負・対応関係CHECKを追加する。既存行は同一migration Txで0/NULLへbackfillする。 |
| W02 | minor | §6「upload 済み入力（原本 — Office 文書は変換 PDF）」対 §9.1「TTL まで機密原本が追跡不能で残る」 | Office文書では原本をuploadしないため、保持対象と機密残留の説明が矛盾する。 | DOCX → PDF変換物をupload → handle記録前クラッシュ → 実際はPDFが残るが文書は原本残留と説明し、監査・利用者通知が誤る | P6 / C6 / C9(V01) / C10 / X66 | 「機密入力（原本 — Office文書は変換PDF）」へ統一する。 |
| W03 | minor | §9.1 completed_at DDL「確定する全てのUPDATE」対直後の「書込点は §10 collect」 | 同一DDLコメントから、collect外のterminal更新でcompleted_atを書く実装と書かない実装が成立する。 | content 4xx → submit_rejectedでstate=3 → 後者の実装はcompleted_at=NULLのまま → terminal行が長期未完了として誤表示される | P9 / C3 / C6 / C7 / C9(V02) / C10 / C11 / X23 / X66 | 「書込点は §10 collect」を削除し、「stateを2/3へ確定する全INSERT/UPDATEでnow」と一本化する。 |
| W04 | fatal | §9.1 相2b「呼出の直前に…scope_idを単独の小Txで記録」および「同一scopeでの照会」 | 保存したscopeと、直後の外部job作成に実際に使うcredential/clientを同一スナップショットへ束縛する規範がない。記録と呼出の間のscope変更で、行が示すscopeとjobの実在scopeが分裂する。 | scope Aを記録 → 呼出前にcredentialがBへ切替 → Bでjob J_B作成後クラッシュ → 後にAで一覧を照会しconfirmed-absent → AへJ_Aを再投入 → J_A/J_Bの二重課金かつJ_B未追跡 | P9 / C7 / C11 / C12 / X75 | API client・credential・scopeを不変のrequest contextとして先に捕捉し、そのscope IDを小Txへ書き、同じcontextでjobを作る。呼出直前の再照合不一致は外部呼出せずunknownへ倒す。credential変更もtick.lockまたはgeneration tokenで直列化する。 |
| W05 | minor | §9.1 scope_id「provider account / workspace の canonical 識別子」および「NULL…常にunknown」 | provider名前空間、accountとworkspaceの連結形式、stable IDを提供しないproviderの値が未定義。安全側のNULLは毎回stalled、空文字等の代替は別scope衝突を起こし得る。 | stable scope IDを公開しないprovider → job開始済みだがscope_id=NULL → crash後の全照会がunknown → 自動回復不能で毎回abandonが必要 | P9 / C8 / C11 / C12 / X75 | `provider/adapter namespace + account immutable ID + workspace immutable ID` のcanonical record/hashを規定する。取得不能時はNULL・fail-closedと明記し、stable IDを自動回復対応providerの採用条件へ追加する。 |
| W06 | major | §6「JSONLのidは列に持たずfilenameのintent_tokenで発見」対 §9.1 abandon「intent_token NULL化。upload残骸は通常の後始末」 | abandonがtokenを消した後、通常のtoken sweepは当該行を選べない。upload_idに保存しないJSONLや未記録uploadを発見する規範上のキーが失われる。 | terminal行にtoken T、課金ledger J、T名のJSONL upload残骸 → scope喪失でguard unknown → abandonは既存Jを見て追加記帳せずTをNULL化 → upload_idの入力だけ削除され、JSONLはtoken sweep対象外となりTTLまで機密残留 | P6 / P9 / P10 / C7 / C11 / C12 / X67 / X72 / X76 | `cleanup_token` を別の耐久列・掃除tombstoneとして残し、token名残骸の削除成功後だけ消す。またはJSONLを含む全upload IDを正規化した子表へ保存する。ledger内tokenから掃除するなら、その選択・完了条件を明記する。 |
| W07 | major | §9.1 submission_seq「job作成/client実行のたびに+1」対 abandon「state不問…未記帳ならsubmission_seq +1、tokenキーで記帳」 | 既に相3またはclient前計上で数えたattemptにもabandonが再度seqを増やす。既知server job IDもtokenへ置換され、通算投入連番とjob突合規則が崩れる。 | client state=0、attempts=1、seq=1、batch_job_id=T → abandon → 外部実行なしでseq=2・token ledger作成 → 次の実jobがseq=3となり、2件の実行に対しhigh-watermarkは3。state=1 server JでもJではなくTで記帳される | P9 / C6 / C7 / C11 / C12 / X13 / X72 / X76 | attemptが既に計上済みかを分岐する。`batch_job_id!=NULL` またはstate=1/client前計上は現seq・既知IDで冪等記帳し、seqを増やさない。相2b後・相3前の未計上server state=0だけseq+1・token記帳とする。 |
| W08 | major | §5.3「floor設定とattempts=0を1Tx」対 §9.1「state IN (2,3)のrotation guard」とsweep foundの「attempts+1」 | 明示再生成がretry budgetをリセットした後、旧tokenのguardが旧attemptを新budgetへ加算する。操作順が時系列と逆で、明示resetが成立しない。 | state=0 serverでjob作成後・相3前クラッシュ → 別経路の成果でstate=2 close、token T・未記帳 → 明示再生成でfloor設定・attempts=0 → guard foundが旧Jを記帳しattempts=1 → 新OCRの相3でattempts=2 → 上限3なら新世代の再試行枠が1回早く尽きる | P5 / P9 / C7 / C10 / C11 / C12 / X78 | 明示再生成操作はrotation guardを先に完了し、その後の単一Txでfloor設定・attempts=0を行う。代案はretry generationを持ち、旧tokenの精算後かつ新相1直前にresetする。 |

## 第 4 部 — 確認済みの列挙

| 区分 | 確認済み・問題なし |
| --- | --- |
| 検査観点 | C5（料金 $2.5/1k、+25%、参考768次元、RRF k=60、8テーブル、各数値・事実の再掲整合） |
| 設計原則 | P1、P2、P3、P4、P7、P8、P11、P12、P13、P14、P15 |