不合格
target.md 全 3284 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第1部 — 回帰確認（C9）

全474項目を判定した。下記の superseded 項目および N23・U01・U06・U11・U24 を除く全項目は fixed。

superseded: A01→K25、A11（遷移詳細）→I05/I06/I13/I14、D08→K20、F05→I14、F07→I15、F12→I16/I17、F21→I03/I04、H02（衝突順）→I32、H04→I31、H15→I08/I11、H18→I16、H22→I15、I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I12→K04、I15→J04、I16/I17→J01/J05、I35→J13〜J16、J03→K10、J04→K01、J06→K02、J07→L09、J10→K09、J13→K16、J16→K13〜K15、K02→L01、K06→L02、K08→N17、K09→L03、K11→L03、K12/K13→L04、K14→L07、K19→L13、K21→L20、K24→L09、L04/L21→M02、L07/M05→N16、L09→M03、L20→M04、L26→N14、L28→M03/M09、M01→N09、M06→N17、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15、N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28、O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37、Q02→R01、Q03→R05、Q04→R02、Q05/Q06→R06/R07、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16、R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06、S06→T09、S07→T05/T06、S11→T07、S19→T03、S20→T01、S23→T18、S24→T02、S25→T04、T03→U04、T08→U03、T10→U01、T11→U05、T16→U02。

| ID | 判定 | 根拠（両側） |
|---|---|---|
| N23 | partially-fixed | §21.6 は「backfill…既定 ON…過去版のみから参照される場合も…自動的に再投入」と正しく記す一方、回避策に「原本を退避する（現在版）」を残す。現在版を移動しても、削除コミット後は旧内容が過去版として backfill 対象になる。 |
| U01 | regression | §6 冒頭は「upload_id 列・filename…は『実際に upload した bytes』（変換物）に適用」「原本は upload しない」と正しい。一方、同節後半に「JSONL の id は…持たず（列は原本用）」「upload する objects/\<content_hash> の bytes」「upload 原本の削除」が残る。 |
| U06 | partially-fixed | §9.1 本文は「completed_at = now…state を 2/3 へ確定する全ての UPDATE に共通」と正しいが、DDL コメントは「collect が state=2/3 へ閉じた時刻」「書込点は §10 collect」と限定している。 |
| U11 | partially-fixed | §21.2 前半は、行削除後の再登録を「有界・ledger 追跡済みの意図されたコスト」として通常投入へ戻す。一方、後半は無条件に「ただし再 OCR / re-embed は派生保持・content-addressed のため発生せず」と断定する。 |
| U24 | partially-fixed | §21.3 の再開表は `ID_WRITTEN : 手順3から`、`APP_DONE : 手順4のみ`とし、停止条件を「id が old / new のいずれでもない」に限定する。`ID_WRITTEN + old`、`APP_DONE + old` が damaged 停止せず素通りする読みが成立する。 |

## 第2部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | 現在版 H に派生あり → drop-derivation → 現在の原本だけ退避 → backfill ON の tick | V05 を検出 |
| 2 | X2 | `short_description=C:\tmp[1]` → img block と alt を materialize → Markdown 表示・逆変換 | V14 を検出 |
| 3 | X3 | 安定した device/inode を返さない FS → junction 循環を含む watch root を walk | V12 を検出 |
| 4 | X4 | 時計後退と同一 ms の複数コミット → LWW・カーソル・generated_at 更新 | 問題なし |
| 5 | X5 | 10万ファイル・100万 chunk → walk、FTS/KNN cap、差分 replicate、incremental vacuum | 問題なし |
| 6 | X6 | 日本語2文字検索、2^53超サイズ、vec0 の次元・距離テンプレートを各境界値で評価 | 問題なし |
| 7 | X7 | 旧 schema を開く → job_create_started_at backfill、FTS追加 migration、途中クラッシュ | 問題なし |
| 8 | X8 | `../x`・絶対パス・制御文字を file_name に混入 → restore、権限、upload を試行 | 問題なし |
| 9 | X9 | 正常な集約を作る → カーソル以前の agg 履歴行を削除、vec payload のみ改変 → tick/fsck | V09・V10 を検出 |
| 10 | X10 | metadata の部分復元・手動編集 → step -1、fsck、再同期 | 問題なし |
| 11 | X11 | profile 変更中に再チャンクと floor 引上げ → collect、replicate | 問題なし |
| 12 | X12 | workspace A で job 作成 → 相3前クラッシュ → credentials を workspace B に変更 → E2E 再開 | V02 を検出 |
| 13 | X13 | 恒久 unknown の明示 abandon と、値未定義の「最大 N 秒」lock wait を実装手順へ落とす | V03・V17 を検出 |
| 14 | X14 | submit・collect・intent 回復で Retry-After 無しの 429/5xx を反復 | 問題なし |
| 15 | X15 | 主張「vec 不整合は再構築」「再生成で99%不変」／試行: 同一 key・次元の payload 改変と全章言換え OCR／破れた | V10・V15 を検出 |
| 16 | X16 | 1 repository の JSONL を複数 job に分割 → 各相境界でクラッシュ → token 回復 | 問題なし |
| 17 | X17 | OCR in-flight 中に unregister → detached payload 破棄 → 行削除前後で再登録 | V11 を検出 |
| 18 | X18 | profiles・集約ミラーを正常構築 → agg_commits/file_versions の一部だけ削除 → fsck | V09 を検出 |
| 19 | X19 | objects rename、metadata commit、app close、fork 各境界で電断 | 問題なし |
| 20 | X20 | 主張「server の未追跡 job は最悪1件」／試行: embedding A→B job→A→B と相3前クラッシュ／破れた | V01 を検出 |
| 21 | X21 | P2→P3 profile 変更、部分 vec 充填、floor 付き再生成を同時進行 | 問題なし |
| 22 | X22 | fork の正常な phase/id 組合せで全クラッシュ境界を再開 | 問題なし |
| 23 | X23 | reconcile、submit_rejected、client_exhausted、detached の各終端を DDL コメントから実装 | V13 を検出 |
| 24 | X24 | 主張「vec 差集合再充填はどの欠落も埋める」／試行: keyを残して payload のみ改変／破れた | V10 を検出 |
| 25 | X25 | app.sqlite 単独検索、restore 宛先判定、watch_root 解除後の folders 起点 walk | 問題なし |
| 26 | X26 | server/client の seq・attempts・ledger を retry、profile 変更、行再作成まで追跡 | 問題なし |
| 27 | X27 | fork が ID_WRITTEN に到達 → repository-id のみ old へ部分復元 → recovery | V07 を検出 |
| 28 | X28 | detached collect が payload を捨て state=2 → 同 repository を再登録 | V11 を検出 |
| 29 | X29 | case-insensitive で作成 → sensitive FS へ移動 → case-only rename と collision | 問題なし |
| 30 | X30 | 主張「fork は全境界から一意に再開」／試行: ID_WRITTEN 後に marker のみ old へ復元／破れた | V07 を検出 |
| 31 | X31 | batch_requests 削除・再作成 → ledger MAX 継承 → reconcile と collect を反復 | 問題なし |
| 32 | X32 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE と old/new の全組合せを実行 | V07 を検出 |
| 33 | X33 | server/client × 全終端理由 × collect/reconcile/detached の課金行列を追跡 | 問題なし |
| 34 | X34 | 完全検索 SQL を2文字 fallback、ready 不一致、上限値、同点で in-memory 実行 | 問題なし |
| 35 | X35 | 主張「fork は id=old から正しく再開」／試行: phase が ID_WRITTEN/APP_DONE のまま id のみ old／破れた | V07 を検出 |
| 36 | X36 | seq 継承、detached 採用、ON CONFLICT close、A→B→A profile 往復 | 問題なし |
| 37 | X37 | damaged/missing/fork の出入り、0フォルダ、同 profile vec 欠落で ready を追跡 | 問題なし |
| 38 | X38 | fork 中に移動・app 全損・journal 再発見 → phase/id 回復を全数実行 | V07 を検出 |
| 39 | X39 | register 時 EIO、同 root の stale 行、対象外型への置換、detached 再登録 | 問題なし |
| 40 | X40 | 主張「drop 後の不要な再 OCR を回避可能」／試行: 現在原本だけ退避して backfill ON のまま drop／破れた | V05 を検出 |
| 41 | X41 | 全終端理由について通常・reconcile・detached の記帳数と seq を全数比較 | 問題なし |
| 42 | X42 | ready 母数から damaged folder を除外 → ready 成立 → folder 復帰・再同期 | 問題なし |
| 43 | X43 | NFD/NFC/case collision/raw 不在を resolver の3呼出点で全数実行 | 問題なし |
| 44 | X44 | 登録済み read の一時 EIO、standalone provenance、step -1 regressed と collect 例外 | 問題なし |
| 45 | X45 | 主張「unknown で二重 job は作られない」／試行: workspace 変更と A→B→A profile 往復／破れた | V01・V02 を検出 |
| 46 | X46 | token 推定記帳、実 job id 記帳、sweep 再訪を同一 lifecycle で反復 | 問題なし |
| 47 | X47 | 期限超の記帳・attempts・rotation 同一 Tx を全境界でクラッシュ | 問題なし |
| 48 | X48 | working 変更を保全 → collision を raw 解決 → no-replace restore → scan | 問題なし |
| 49 | X49 | 未完 fork 後に register/unregister/restore/watch_root/drop を順に要求 | 問題なし |
| 50 | X50 | 主張「§6/§7 の往復は全段可逆」／試行: alt に `C:\tmp` を与え field と label の二重 escape／破れた | V14 を検出 |
| 51 | X51 | 無 id 記帳、found 記帳、detached 採用、行再作成の seq を連続実行 | 問題なし |
| 52 | X52 | expired terminal → sweep → unregister → 明示 retry → 新 token | 問題なし |
| 53 | X53 | intent 回復・detached・close・sweep の4照合点を credential scope 変更下で比較 | V02 を検出 |
| 54 | X54 | journal/flag/id の全行列で ID_WRITTEN+old、APP_DONE+old を実行 | V07 を検出 |
| 55 | X55 | standalone で embedding profile 混在、tool 同時刻、空 markdown を検索 | 問題なし |
| 56 | X56 | 非canonical `![...](obj:...)` と複数先頭 backslash の escape/un-escape | 問題なし |
| 57 | X57 | found 記帳で batch_job_id 自己記述化 → sweep → 成果消失後の再投入 | 問題なし |
| 58 | X58 | detached terminal 化 → payload 無しのまま再登録 → 遷移表の自動投入 | V11 を検出 |
| 59 | X59 | 課金される submit_rejected → terminal 記帳 → token sweep → 明示 retry | 問題なし |
| 60 | X60 | 本文の G、`\G`、`\\G`、非canonical 行、object 不在行を materialize/reparse | 問題なし |
| 61 | X61 | 主張「正常一覧で不在を安全に確定」／試行: job 作成後に account/workspace を切替えて空一覧取得／破れた | V02 を検出 |
| 62 | X62 | job_create_started_at 記録前後のクラッシュ、時計補正、requeue を反復 | 問題なし |
| 63 | X63 | cancel 確定 → 再登録 → 明示 retry → 再 cancel と ledger 追記 | 問題なし |
| 64 | X64 | token 推定行が存在する状態で別 attempt の実 job を found として採用 | 問題なし |
| 65 | X65 | RENAME_NOREPLACE 非対応・EEXIST・EINVAL・再 lstat の各分岐 | 問題なし |
| 66 | X66 | 規範本文と DDLコメント・要約・見出しを横断比較 | V08・V13 を検出 |
| 67 | X67 | state=0 の intent 照合が資格情報喪失で恒久 unknown → retry/操作を継続 | V06 を検出 |
| 68 | X68 | cancel 後の削除条件到達前に再登録・retry・再unregister | V11 を検出 |
| 69 | X69 | fts_cap 境界で同点を大量生成し、FTS/KNN/RRF の再現性を反復確認 | 問題なし |
| 70 | X70 | Office converter 更新 → 旧 convert_failed 行を保持 → 新 tool target を投入 | 問題なし |
| 71 | X71 | A embedding あり → B job J/token T 作成後に相3前クラッシュ → Aへ戻して state=2 close → Bへ戻して再投入 | V01 を検出 |
| 72 | X72 | 恒久 unknown → abandon で token NULL を先に確定 → ledger 前クラッシュ → 後日 job 可視化 | V03 を検出 |
| 73 | X73 | 旧 converter の convert_failed terminal → converter/profile 更新 → 新 target_key を投入 | 問題なし |
| 74 | X74 | stat tuple が不変の暗号化PDF → 構文失敗ごとにプロセス再起動 → 24時間後に削除 | V04 を検出 |

## 第3部 — 新規検出

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| V01 | fatal | §9.1「成果なし・state=2 → 投入対象」「適用は state=3 の再投入に限る」「unknown…記帳も掃除もせず保持」 | 未解決 token を持つ state=2 が rotation guard を迂回し、課金済み job の唯一の照合キーを上書きできる。 | A成果あり → B job J/T を作成し相3前クラッシュ → Aへ戻して state=2 close、照合 unknown → Bへ戻して再投入 → TをT2で上書きしJを未記帳のまま喪失、別jobを作成。 | P9 / C7 / C11 / C12 / X20 / X45 / X71 | 未解決 token を持つ `state IN (2,3)` の再投入に照合・記帳・NULL化 guard を適用する。unknown 中は state=2 を再投入不可にする。 |
| V02 | fatal | §9.1「job 作成時と同一の account / workspace scope」；batch_requests DDLには scope snapshot がない | 同一 scope 判定に必要な過去値が耐久保存されず、規範を実装できない。 | workspace A で J 作成 → 相3前クラッシュ → credentials を B に変更 → B の空一覧を取得 → A/B比較材料がなく confirmed-absent と誤認し、AのJを未追跡のままBで再投入。 | P9 / C8 / C11 / C12 / X12 / X45 / X53 / X61 | 相2b直前に canonical provider/account/workspace scope ID を行へ保存し、全4照合点で比較する。既存行の未知 scope は stalled とする。 |
| V03 | fatal | §9.1「明示 abandon（ユーザー確認で estimated 記帳 + intent_token NULL 化）」 | 記帳・seq・冪等述語・token NULL化を同一 Tx にする規範がなく、途中クラッシュで相関キーと課金記録を同時に失える。 | unknown 行 → token NULL を先に commit → ledger INSERT 前クラッシュ → 後日 job が可視化 → 照合キーも記帳もなく、retry で追加課金。 | P9 / C7 / C11 / C12 / X13 / X72 | old token を ledger の batch_job_id とする記帳、seq更新、terminal化、token NULL化を単一 app Tx に固定し、再実行述語を定義する。 |
| V04 | fatal | §20.5「同一 (size, mtime_ns, inode) のまま連続3回（または24時間）構文検証に失敗…bytes のまま通常コミット」；scan_cache は回数・起点を持たない | 非常駐 tick を跨ぐ回数・24時間起点を保存できず、有界化が実装不能。未コミットの原本を削除すると履歴から復旧できない。 | 安定した暗号化PDF → 毎回構文失敗後に再起動 → 永続カウンタがなく毎回初回扱い → 24時間超でも未コミット → 原本削除で内容喪失。 | P16 / C1 / C8 / C11 / C12 / X74 | stat tuple、failure_count、first_failure_at を運用表へ保存し、tuple変更・成功時のresetと、EIO/安定確認失敗を数えない規則を定義する。 |
| V05 | fatal | §21.6「backfill…過去版のみ…自動的に再投入」対「再課金を望まない場合…原本を退避する（現在版）」 | 現在原本の退避は backfill を止めず、再課金回避策として誤っている。 | 現在版を退避 → 削除コミット → 同 content が過去版に残る → backfill ON で drop 後に再 OCR・再課金。drop が先なら削除scan前の現在版として同じく再投入される。 | P13 / C7 / C10 / C11 / C12 / X1 / X40 | 「原本を退避する」を単独の回避策から削除し、repository 全体を watch_root 外へ移して unregister、または過去版化後に backfill OFF とする。 |
| V06 | major | §9.1 intent 回復「unknown…state=0 のまま保持」；明示 abandon は state=3 rotation guard の段落にのみ存在 | state=0 の照合が恒久 unknown になった場合の到達可能な終端・明示解決がない。 | state=0/T で job 作成境界クラッシュ → 資格情報を恒久喪失 → 全 tick が unknown 保持 → submit、collect、retryのいずれにも進めず対象が恒久未生成。 | P9 / C7 / C11 / C12 / X67 | state=0 unknown にも明示 abandon を定義し、旧tokenの課金・後日可視化・残骸追跡を耐久記録した上で terminal 化する。 |
| V07 | major | §21.3「phase = ID_WRITTEN : 手順3から」「phase = APP_DONE : 手順4のみ」；停止は「id が old / new のいずれでもない」場合だけ | phase と実体 id の不可能組合せが fail-closed にならない。 | ID_WRITTEN/APP_DONE 後に marker のみ old へ部分復元 → recovery が手順3/4を実行し journal を削除 → folders[new] と marker[old] が不一致のまま回復キーを喪失。 | P16 / C7 / C11 / C12 / X27 / X30 / X32 / X35 / X38 / X54 | 完全な phase×id 行列を定義し、ID_WRITTEN/APP_DONE は `id=new` のみ許可、それ以外を damaged 停止する。 |
| V08 | major | §6「原本は upload しない」対「列は原本用」「upload する objects/\<content_hash>」「upload 原本の削除」 | Office 文書で、upload_id・再照合対象・削除対象が原本 O と変換PDF Pのどちらか一意でない。 | DOCX O をPへ変換してPだけ upload → 後半記述どおり upload_id をO用として実装 → Pのhandle記録・掃除が欠落し、provider TTLまで残留。 | P6 / C6 / C10 / C12 / X66 | 全再掲を「upload入力」「実際にuploadした変換物」に統一し、hash再照合だけが原本Oを読むと明記する。 |
| V09 | major | §9.3-a はカーソルより後だけをコピー；§13 集約fsckは vec差集合と markdown/chunks件数のみ | カーソル以前の agg_commits / agg_file_versions の部分喪失を検出・再同期する経路がない。 | C1,C2を複製しcursor=C2 → aggのC2履歴行だけ削除 → folder maxとcursorは一致、cursor commitもfolderに存在 → 以後差分0で過去版検索が恒久欠落。 | P1 / P11 / C11 / C12 / X9 / X18 | folder正本との双方向差集合・全field照合をfsckへ追加し、不一致repoは agg4表とcursorをwipeしてfull resyncする。 |
| V10 | major | §5.6「embeddings が正、embedding_vec は…導出物」；§8-c/e は次元・距離・target_key欠落だけを検査 | 同一 key・次元の vec payload 改変を検出せず、誤ったKNN順位を正常扱いする。agg_vecも同様。 | canonical vector V と vec V → vec payloadだけWへ改変 → key・次元・metricは一致 → 差集合空で修復されず、検索が永久にWを使用。 | P8 / C11 / C12 / X9 / X15 / X24 | canonical BLOBとの内容照合を行うか、週次fsckでvec表を全再構築する。 |
| V11 | major | §21.2「削除後の再登録…意図されたコスト」対「ただし再 OCR / re-embed は…発生せず」 | detached が成果を捨てた場合も再処理なしと読める矛盾がある。 | in-flight中にunregister → cancel未確定 → detached collectがpayload破棄しstate=2 → 再登録 → 成果なしのため自動再投入・再課金。 | P9 / C3 / C6 / C7 / C10 / C11 / C12 / X17 / X28 / X58 / X68 | 後者を「完成済み派生が保持されている場合」に限定し、detached/cancel/no-result は再投入・再課金され得ると明記する。 |
| V12 | major | §20.4「訪問済み (st_dev, st_ino) 集合」；§9.1 は inode を「取得できる環境のみ」とする | 安定した directory identity が得られない環境の代替規則がない。 | ID欠落を同一sentinelにする → 別directoryを再訪扱いで欠落。visited setを無効にする → junction/bind cycleでtick.lockを保持したまま無限walk。 | P16 / C11 / C12 / X3 | platform-equivalentなvolume/file IDを定義し、それも取得不能なら当該rootをstatus付きでfail-closedにする。 |
| V13 | minor | batch_requests DDL「collect が state=2/3へ閉じた時刻」「書込点は§10 collect」 | 本文の全終端UPDATE規範がDDLコメントへ伝播していない。 | DDLコメント準拠でreconcile、submit_rejected、client_exhaustedを実装 → completed_at=NULLが残り滞留statusを誤る。 | P9 / C6 / C11 / X23 / X66 | DDLコメントを「stateを2/3へ確定する全UPDATEで同時書込」に統一する。 |
| V14 | minor | §6「altにも…field値と同一…エスケープ」「さらに値中の `\` `[` `]` を…置換」 | backslashをfield層とMarkdown label層で二重escapeし、保存Markdownの表示値が原値と一致しない。 | alt=`C:\tmp` → field層で`\\` → label層で`\\\\` → Markdown表示が二本のbackslashになる。 | P6 / C6 / C12 / X2 / X50 | alt用処理をcomment field処理から分離し、1行正規化後にMarkdown label escapeを一度だけ適用する。 |
| V15 | minor | §5.6「再生成で99%の chunk は text_hash が変わらない」 | 非決定的OCRについて99%を保証・測定条件なしで断定している。 | 同一profileで全節が言い換えられるOCR再生成 → 全text_hashが変わり、全embeddingが課金対象になる。 | C5 / C11 / C12 / X15 | 数値を削除し、「hashが変わらないchunkだけ再利用される」と効果の上限を限定する。 |
| V16 | minor | §20.5「保存は bytes ベース (P1)」 | target.md 内に P1 という参照先がなく、監査プロンプトの原則番号が独立設計書へ漏れている。 | 実装者がP1を参照 → 文書内検索で定義を発見できず、どのbytes規範か一意に特定できない。 | C3 / C6 / C11 | §1または§15規約9へ置換するか、規範をその場で完結させる。 |
| V17 | minor | §21「明示操作は最大 N 秒ブロッキングで待つ」 | N の既定値・設定場所・単位以外の境界契約がない。 | 二実装がN=0とN=300を選択 → 同一競合で即時失敗と長時間待機に分岐し、status/UI挙動が一致しない。 | C8 / C11 / X13 | Nの既定値、設定key、上限、timeout時の結果を定義する。 |
| V18 | minor | §5.6の正本キーは `(chunk_type, embed_hash)`；§18.2/18.3は「内容単位 (embed_hash)」「処理単位…embed_hash」と省略 | text/imageの型を落とした要約が正本キーと矛盾する。 | UTF-8としても同一bytesになる画像とtextを用意 → §18要約どおりhashだけで共有 → 異なる入力型を同一vectorとして扱う。 | P8 / C6 / C11 | §18.2/18.3も一貫して `(chunk_type, embed_hash)` と記す。 |

## 第4部 — 確認済みの列挙

検出0件として確認済みの検査観点:

- C2 — metadata/app/agg の通常DDL、FTS5 external-content view・trigger、INSERT/DELETE、`integrity-check` の構文・制約を確認済み。
- C4 — 掲載SQLの列名、CTE、JOINキー、bind、FTS/KNN/GC/差集合と各schemaの整合を確認済み。

検出0件として確認済みの原則:

- P2、P3、P4、P5、P7、P10、P12、P14、P15。