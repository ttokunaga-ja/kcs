不合格
target.md 全 3284 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第1部 — 回帰確認（C9）

全474項目を判定した。内訳は fixed 360件、superseded 110件、regression 1件、partially-fixed 3件。

### fixed

- A02–A10、A12–A24
- B01–B18
- D01–D07、D09–D14
- E01–E06
- F01–F04、F06、F08–F11、F13–F20、F22–F27
- G01–G02
- H01、H03、H05–H14、H16–H17、H19–H21、H23–H30
- I01–I02、I07–I08、I10、I13–I14、I18–I34、I36–I38
- J01–J02、J05、J08–J09、J11–J12、J14–J15、J17–J20
- K01、K03–K05、K07、K10、K15–K18、K20、K22–K23、K25–K26
- L01–L03、L05–L06、L08、L10–L19、L22–L25、L27
- M02–M04、M07、M11、M14–M28
- N01–N02、N05–N06、N08–N12、N14、N16–N27、N29–N35、N37–N38、N41–N45
- O01、O06、O08、O10、O12、O14–O16、O20–O27、O29
- Q01、Q07–Q08、Q11、Q15–Q37
- R01–R05、R09–R12、R14–R17、R19、R21–R22、R24、R26–R29
- S01–S05、S08–S10、S12–S18、S21–S22、S26–S29
- T01–T02、T04–T07、T09、T12–T15、T17–T18
- U02–U05、U07–U17、U19–U23

### superseded

- A01→K25、A11→I05/I06/I13/I14
- D08→K20
- F05→I14、F07→I15、F12→I16/I17、F21→I03/I04
- H02→I32、H04→I31、H15→I08/I11、H18→I16、H22→I15
- I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I12→K04、I15→J04、I16/I17→J05/J01、I35→J13–J16
- J03→K10、J04→K01、J06→K02、J07→L09、J10→K09、J13→K16、J16→K13–K15
- K02→L01、K06→L02、K08→N17、K09→L03、K11→reconcile-close、K12/K13→L04、K14→L07、K19→L13、K21→L20、K24→L09
- L04/L21→M02、L07→N16、L09→M03、L20→M04、L26→N14、L28→M03/M09
- M01→N09、M05→N16、M06→N17、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15
- N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28
- O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37
- Q02→R01、Q03→R05、Q04→R02、Q05→R06、Q06→R06/R07、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16
- R06→S10/S15、R07→S19/S28、R08→S01、R13→S02、R18→S02、R20→S03、R23→S04、R25→S06
- S06→T09、S07→T05/T06、S11→T07、S19→T03→U04、S20→T01、S23→T18、S24→T02、S25→T04
- T03→U04、T08→U03、T10→U01、T11→U05、T16→U02

### fixed / superseded 以外

| ID | 判定 | 根拠（§＋短い引用。両側） |
|---|---|---|
| U01 | regression | §6の規範側は「upload_id 列・filename への intent_token 埋込は『実際に upload した bytes』(変換物) に適用する — 原本は upload しない」。一方、同節の再掲には「JSONL の id は upload_id 列に持たず (列は原本用)」、さらに「upload 原本の削除」が残る。Office入力では実際のupload対象が変換PDFであるため、列の対象が相互に矛盾する。 |
| U06 | partially-fixed | §9.1の規範側は「completed_at=now」は「state を2/3へ確定する全ての UPDATEに共通」。一方DDLコメントは「collect が state=2/3 へ閉じた時刻」「書込点は §10 collect」と限定したままで、submit_rejected・reconcile等を落としている。 |
| U18 | partially-fixed | §13のfolder側は「件数 + 全 field 照合」。一方agg側は「agg_markdown_documents ... agg_chunks 子行の対応 (件数)」のみで、image_meta・page・bbox・seq等の同件数改竄を検出できない。 |
| U24 | partially-fixed | §21.3には「id が old/new のいずれでもない」場合のfail-closedがある一方、回復表は「phase=ID_WRITTEN: 手順3から」「phase=APP_DONE: 手順4のみ」とだけ規定する。phaseとold/newの不可能な組合せを拒否していない。 |

## 第2部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | 追跡中のa.txt=A → 同一tick中にBへ更新後削除 → 完全walk、pending確定、履歴・派生処理を順次実行 | 問題なし |
| 2 | X2 | 改行・制御文字・`obj:`・偽img blockを含む名前/本文 → scan、materialize、restore → invalid-name処理とescapeを確認 | 問題なし |
| 3 | X3 | NFD名だけを持つフォルダ → NFC論理名として登録 → case-sensitive/insensitive間を移動して再scan | 問題なし |
| 4 | X4 | Aの派生時に時計が2100年へ進む → 時計を2026年へ戻す → Bを新規派生して単独検索 | V04を検出 |
| 5 | X5 | 10万file・100万chunk → walk、差集合、FTS/KNN、agg再同期 → bind分割とcap境界を確認 | 問題なし |
| 6 | X6 | 日本語2文字query → trigram候補0件 → LIKE fallbackとKNNを実行 | 問題なし |
| 7 | X7 | 旧schemaを持つDB → 新版起動・migration中断・再起動 → version gateと単一Tx再実行を確認 | 問題なし |
| 8 | X8 | metadataのfile_nameを`../outside`に改竄 → in-place restore → root dirfdとresolverの境界検証 | 問題なし |
| 9 | X9 | objectsの参照中blobを1個削除 → fsck → damaged表示、派生停止、履歴を維持して修復待ち | 問題なし |
| 10 | X10 | `.folder-history`を手動削除 → 次tickで登録済みpathを照合 → 自動再初期化せずdamagedへ移行 | 問題なし |
| 11 | X11 | embedding profile Aで課金済み → Bへ変更しkind=2派生を削除 → cost_ledger保持と再生成 | 問題なし |
| 12 | X12 | watch_root登録 → 発見 → commit → OCR → chunk/embed → agg → 検索 → 原本表示 → restore | 問題なし |
| 13 | X13 | state=3、token残存、照会が恒久unknown → ユーザーが明示abandon → 途中クラッシュを各境界に挿入 | V02を検出 |
| 14 | X14 | submit/collectが429 → retry-after反映 → retry_not_before前後のtickを反復 | 問題なし |
| 15 | X15 | 主張: pendingでdeleteを見逃さない、readyは部分indexを通さない、restoreはworking変更を保存、unknown中は二重jobを作らない、forkはjournalで再開する → 各境界にクラッシュ・dirty tick・一時EIOを挿入 → この5主張は破れず | 問題なし |
| 16 | X16 | 分割JSONL、server/client両経路 → 相1直後・相2途中・相3直前でクラッシュ → token/job対応を回復 | 問題なし |
| 17 | X17 | register途中クラッシュ → 回復 → fork → restore → unregister・再登録 | 問題なし |
| 18 | X18 | folder側と件数が同じagg_chunksのimage_meta/page/bboxだけを改竄 → agg fsck → 再同期判定 | V05を検出 |
| 19 | X19 | object rename、metadata commit、app更新、submit各境界で電源断 → fsync後に再起動 | 問題なし |
| 20 | X20 | 主張: forkは全境界から一意に再開する → ID_WRITTEN後にrepository-idだけoldへ復元 → journal回復 | V06を検出（主張が破れた） |
| 21 | X21 | profile A投入中 → Bへ変更 → floor引上げ、vec部分充填、再起動、ready判定 | 問題なし |
| 22 | X22 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONEの正常なphase/id組合せ → 各手順後クラッシュ | 問題なし |
| 23 | X23 | NULL/estimated ledger、detached、name_collision各行を生成 → status・GC・検索・再試行 | 問題なし |
| 24 | X24 | 主張: vec差集合再充填は任意のクラッシュから収束する → 次元変更中に部分INSERT・中断・再実行 → 欠落集合が空になるまで反復 | 問題なし（主張は破れず） |
| 25 | X25 | folder未接続でapp.sqliteのみ存在 → app_configからquery embeddingを生成して横断検索 | 問題なし |
| 26 | X26 | server/client/detachedが同一targetで順に失敗・再投入 → submission_seq、attempts、ledgerを追跡 | 問題なし |
| 27 | X27 | fork journal書込から削除まで全境界でクラッシュ → 同じjournalで再開 | 問題なし |
| 28 | X28 | unregisterでdetached化 → job完了 → payload破棄・記帳・upload掃除 → 同じrepoを再登録 | 問題なし |
| 29 | X29 | case-only rename → case-sensitive媒体へ移動 → 大小文字違いの新規実体を追加 | 問題なし |
| 30 | X30 | 主張: ledger UNIQUEは正当な再課金を妨げない → token推定行seq=k、job close seq=k+1、retry seq=k+2を記帳 | 問題なし（主張は破れず） |
| 31 | X31 | batch_requests行削除 → ledger MAXからseq継承 → 同tickで複数targetを再作成 | 問題なし |
| 32 | X32 | phase=ID_WRITTEN・id=old、およびphase=APP_DONE・id=oldを作成 → bootstrap回復 | V06を検出 |
| 33 | X33 | server/client × 全終端理由 × normal/reconcile/detached closeの行列 → ledger件数を照合 | 問題なし |
| 34 | X34 | 掲載FTS/KNN/LIKE/eligible/agg再JOIN SQLをDDL上で構成 → 空・部分・ready各状態で実行 | 問題なし |
| 35 | X35 | 主張: forkはid=oldからも正しく再開する → ID_WRITTEN後にidのみoldへ戻して回復 | V06を検出（主張が破れた） |
| 36 | X36 | close Txを同じseqで再実行 → ON CONFLICT吸収 → 次の正当attemptをseq+1でclose | 問題なし |
| 37 | X37 | profile P2構築中に1folder missing → 復帰・差集合充填 → synced/readyを更新 | 問題なし |
| 38 | X38 | HISTORY_CLEARED中にfolderを移動 → journal探索・flag除外・bootstrap回復 | 問題なし |
| 39 | X39 | 登録済みrootを一時EIO → detached猶予中に復帰 → rebind・conflict判定 | 問題なし |
| 40 | X40 | 主張: 単独検索のcurrent_toolは次回生成で現行toolへ回復する → Aを未来時刻で生成、時計復旧後Bを生成 | V04を検出（主張が破れた） |
| 41 | X41 | server/client全終端経路を通常・reconcile・detachedで閉じる → seqとledgerを比較 | 問題なし |
| 42 | X42 | ready母数0→1→一部missing→復帰 → synced=NULL化、agg wipe、再構築を順次実行 | 問題なし |
| 43 | X43 | NFC実体とNFD実体を同時配置 → walkでcollision winner決定 → restore/delete resolverを呼出 | V09を検出 |
| 44 | X44 | 同一repository-idを2pathに配置 → standalone readと通常tick → conflict解消後に再実行 | 問題なし |
| 45 | X45 | 主張: provider照会unknown中は二重jobを作らない → unknownを連続させ、dirty tick・再起動・期限境界を通す | 問題なし（明示abandonを行わない限り主張は破れず） |
| 46 | X46 | token推定記帳 → job発見記帳 → retry → collect記帳 → 各batch_job_id述語を再実行 | 問題なし |
| 47 | X47 | 期限超記帳・attempts+1・token rotationの1 Tx → 各SQL境界でクラッシュして再駆動 | 問題なし |
| 48 | X48 | working copyを履歴外編集 → 過去版restore → 保全commit後に上書き → 次tick scan | 問題なし |
| 49 | X49 | 未完forkを残す → register/unregister/restore/watch_root/dropを順に要求 | 問題なし |
| 50 | X50 | 主張: 無id記帳でもbatch_job_id NOT NULLに衝突しない → 期限超・found・sweep・client前計上の全経路を実行 | 問題なし（主張は破れず） |
| 51 | X51 | 期限超、found、sweep、detached、client経路で順にseq+1 → 行削除・再作成 | 問題なし |
| 52 | X52 | expired terminal → unregister → sweepでtoken掃除 → 再登録・明示retry | 問題なし |
| 53 | X53 | intent回復・detached・found・sweepの4照合点 → unknown/absent/found/期限超/未来skewを全適用 | 問題なし |
| 54 | X54 | journal有効/破損/無 × flag有無 × id=old/new/第三値 → 回復・明示解決 | 問題なし |
| 55 | X55 | 通常時刻で異なるtoolの派生を生成 → current_profile/current_tool、空文書、同時刻tieを検索 | 問題なし |
| 56 | X56 | 手書き`\![...](obj:...)`・非canonical行 → materialize/unescapeを往復 | 問題なし |
| 57 | X57 | found記帳後、batch_job_id自己記述化の直前でクラッシュ → sweep・再投入 | 問題なし |
| 58 | X58 | detached/cancelled/expired terminal → token掃除 → 同repo再登録 | 問題なし |
| 59 | X59 | 課金しないsubmit拒否契約 → submit_rejected → sweep除外・明示retry | 問題なし |
| 60 | X60 | 0個以上の`\`＋canonical/非canonical img行＋object有無を全組合せで往復 | 問題なし |
| 61 | X61 | 主張: 伝播遅延上限が設定猶予以下なら偽expiredは起きない → 上限直前/直後にjobを可視化し4照合点を実行 | 問題なし（記載された契約前提では主張は破れず） |
| 62 | X62 | job_create_started_at記録直後・API呼出前/中/直後でクラッシュ → 再起動・期限判定 | 問題なし |
| 63 | X63 | cancel確定 → token sweep → 再登録 → 自動再投入・再cancel | 問題なし |
| 64 | X64 | 旧token推定行を残して新attempt J2を発見 → IN(job id, token)述語で記帳 | 問題なし |
| 65 | X65 | no-replace非対応を初回エラーで検出 → fallback、EEXIST、再lstatを実行 | 問題なし |
| 66 | X66 | §6/§9.1/§21再掲とDDLコメントを規範側と突合 → Office変換uploadとcompleted_at全close経路を追跡 | V01・V08を検出 |
| 67 | X67 | state=3・旧token残存・照会unknown継続 → rotation guardで保留 → 明示abandonを選択 | V02を検出 |
| 68 | X68 | cancelでattempts上限 → 明示retryで0へ戻す → 再unregister・cancel → ledger比較 | 問題なし |
| 69 | X69 | 同順位を含むFTS候補がfts_cap超、KNN候補がk超 → RRF融合を反復 | 問題なし |
| 70 | X70 | converter v1でconvert_failed → tool_profileをv2へ変更 → 新target_keyで変換・投入 | 問題なし |
| 71 | X71 | state=0載せ直しTxの各境界でクラッシュ、client dispatchを再実行 → 旧token記帳とrotationを追跡 | 問題なし |
| 72 | X72 | unknown行を明示abandon → estimated記帳後にprovider jobが可視化 → sweep found → 明示retry | V02を検出 |
| 73 | X73 | tool Aでconvert_failed terminal → tool Bへ変更 → 新target投入、旧行掃除、attempts独立性を確認 | 問題なし |
| 74 | X74 | 同一fingerprintの構文不正file → syntax failure、プロセス再起動、一時EIOを挟み24時間超反復 | V03を検出 |
| 75 | 自由 | 外付けroot切断でmissing_since設定 → 壁時計を31日進める → 次tickで猶予判定 → 時計復旧・再接続 | V07を検出 |

## 第3部 — 新規検出

| ID | 重大度 | 該当箇所（§＋短い引用） | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| V01 | major | §6「upload_id 列・filename への intent_token 埋込は『実際に upload した bytes』(変換物) に適用する」／同節「JSONL の id は upload_id 列に持たず (列は原本用)」／§9.1「入力 upload (原本 — Office 文書は変換 PDF、§6)」 | Office入力についてupload_idが原本用なのか実際のupload bytes用なのか矛盾する。変換PDFのfile idを保持・削除しない実装が成立する。 | DOCX原本O → PDF Pへ変換 → Pのみupload → 「列は原本用」に従いPのidを保存しない → terminal後にPをID指定削除できずprovider上へ残留 | P6、C1、C3、C6、C10、C11、C12、X66、U01 | 全記述を「実際にuploadした入力bytes」に統一し、Officeでは変換PDFのidをupload_idへ保存すると明記する。「原本削除」等の見出しも「upload済み入力削除」へ改める。 |
| V02 | major | §9.1「照合が恒久 unknown ... 明示 abandon (ユーザー確認で estimated 記帳 + intent_token NULL 化)」／DDL `UNIQUE(repository_id, kind, target_key, submission_seq)`、`batch_job_id NOT NULL` | 明示abandonについて、記帳・seq更新・batch_job_id値・state/attempts・token消去の順序とTx境界が未定義。クラッシュによる無記帳、または同一seq競合による記帳欠落が可能。後日jobが見つかった場合の帰属も一意でない。 | state=3、token=T、seq=n、照会unknown → 実装がTをNULL化 → ledger INSERT前にクラッシュ → sweepでTを回収不能 → retryでT2を作成 → 後日Tのjobが現れ、旧attemptの課金が欠落 | P9、C7、C8、C11、C12、X13、X67、X72 | §21に専用操作を追加し、記帳済み判定、seq=n+1更新、`batch_job_id=T`のestimated INSERT、state/attempts処理、token消去を同一app Txで行う。後日job発見時の照合・差額処理も規定する。 |
| V03 | major | §20.5「同一 (size, mtime_ns, inode) で連続 3 回/24h syntax failures → bytesをcommit」／同節は常駐tickでないためmemory countでは不足すると認識 | 連続失敗回数・初回時刻を永続化する列または表がDDLにない。プロセス再起動で回数が消え、構文不正fileを無期限skipできる。一時EIOをsyntax failureへ含めるかも未定義。 | 安定した破損PDF → 各cron実行でsyntax failure後に終了 → 間にEIOを1回挿入 → 24時間経過しても回数が保持されない、またはEIO込みで誤ってbytes commit → archive欠落または不安定bytes保存 | P16、C7、C8、C11、C12、X74 | repository/file/fingerprint別の永続表を追加し、count、first_failure_at、last_failure_at、failure_classを保存する。fingerprint変更時にresetし、syntax failureとEIO・racy readを分離する。 |
| V04 | major | §5.3「generated_at = max(now, 旧値+1)」／§11.2は単独検索のcurrent_toolを最新generated_atで決定し「次の新しいtool生成で回復」とする | 単調化が同一派生行内だけで、repository全体の未来時刻を越えない。時計が一度未来へ進むと、別文書の現行tool派生が永続的にcurrent_toolになれない。 | tool Aの文書を時計2100年で生成 → 時計を2026年へ修正 → tool Bの別文書を生成 → MAX(generated_at)はA → BのFTS候補が将来まで除外 | P12、C5、C6、C11、C12、X4、X40 | repository単位のgenerated_at high-water markを持ち、`max(now, repository全派生のMAX+1)`を採番する。異常な未来値の検出・再基準化も規定する。 |
| V05 | major | §13 folder側「件数 + 全 field 照合」／agg側「agg_markdown_documents ... agg_chunks 子行の対応 (件数)」／§9.3-bは「missingまたはgenerated_at差」で再copy | agg側の同件数semantic corruptionを検出できない。親generated_atが同じなら再copyも起動せず、誤ったpreview・provenance・画像位置が残る。 | agg_chunksのimage_meta/page/bboxだけを改竄し件数を維持 → fsckは件数一致 → 親generated_atも一致 → FTS rebuildが壊れたaggを正本として再構築 | P13、C1、C8、C10、C11、C12、X18、U18 | agg親子もfolder sourceとの全field照合にする。不一致時は既存の親DELETE、synced_profile_hash=NULL、ready解除経路へ送る。 |
| V06 | major | §21.3「phase=ID_WRITTEN: 手順3から」「phase=APP_DONE: 手順4のみ」／一般guardは「id が old/new のいずれでもない」場合のみfail-closed | phaseとrepository-idの整合行列がないため、`ID_WRITTEN/APP_DONE + old`という不可能状態を正常状態として処理する。registryのnewとmarkerのoldを残してjournalを削除できる。 | ID_WRITTEN・id=newまで進行 → repository-idだけold版へ復元 → bootstrap → 手順3から実行しfolders[new]を作成 → journal/flag削除 → marker oldとregistry newが恒久衝突 | P16、C7、C10、C11、C12、X20、X32、X35、U24 | phase×idの全行列を規定する。ID_WRITTEN/APP_DONEはid=newを必須とし、oldならfail-closed、または安全に手順2から再実行する。 |
| V07 | major | §20.4「外付けドライブの一時切断を削除と誤検知しない」／退役条件「now − missing_since >= 30日」 | missing猶予を壁時計差だけで判定するため、NTP・手動設定による未来jumpで数分の切断を30日不在と誤認できる。in-flightをdetached化し、成果を破棄・再課金する。 | 外付けrootを5分切断 → missing_since=t → 時計を31日進める → 次tickで退役・detached化 → 時計復旧後に再接続 → 同じ入力を再処理 | P16、C5、C7、C11、C12、自由探索75 | 大幅な時計jumpを検出したら退役判定を保留し、正常時計での後続観測またはユーザー確認を要求する。monotonic経過時間を利用できる実行期間では併用する。 |
| V08 | minor | §9.1「completed_at=now ... state を2/3へ確定する全ての UPDATEに共通」／DDLコメント「collect が state=2/3 へ閉じた時刻」「書込点は §10 collect」 | DDLコメントがcompleted_atの適用範囲をcollectだけに狭めている。コメントを実装根拠にするとsubmit_rejected・reconcile等でNULLが残る。 | submit_rejectedでstate=3へclose → DDLコメントに従いcompleted_atを更新しない → status上の完了時刻が欠落 | P9、C3、C6、C10、C11、C12、X66、U06 | コメントを「stateを2/3へ確定する全遷移の時刻」へ修正し、非collect closeの各SQLにも更新を明記する。 |
| V09 | major | §20.5 resolver「初出表記固定・BINARY一致優先・UTF-8バイト列昇順 tie-break」／collision規則「物理名のUTF-8バイト列昇順で最初の1件」 | walkはraw物理名のbyte順でwinnerを選ぶ一方、resolverは保存済み論理名へのBINARY一致を優先できる。NFC/NFD両実体でscanとrestore/deleteが異なる実体を選ぶ。 | NFC `é.txt` とNFD `e◌́.txt`を同時配置 → walkはraw byte順でNFDを採用 → 保存論理名NFCでrestore → resolverはNFC実体をBINARY優先 → scan対象と書込対象が分裂 | P16、C6、C7、C11、C12、X43 | 論理系列の選択とraw実体winnerを分離して定義し、resolverの3呼出点すべてがwalkと同じraw winner関数を使うよう規定する。 |

## 第4部 — 確認済みの列挙

### 検査観点

| 観点 | 確認結果 |
|---|---|
| C1 原則反映 | 確認済み。V01–V09を第3部に記載。 |
| C2 SQL静的検証 | 確認済み、検出0件。core SQLiteの全DDL・trigger・view・generated column・FTS関連SQLは構文整合。 |
| C3 相互参照整合 | 確認済み。V01、V08を第3部に記載。 |
| C4 クエリとスキーマの整合 | 確認済み、検出0件。掲載列、JOIN、FK、FTS source rowidの不一致なし。 |
| C5 数値・事実の一貫性 | 確認済み。V04、V07を第3部に記載。 |
| C6 用語・形式の一貫性 | 確認済み。V01、V04、V09を第3部に記載。 |
| C7 状態機械の完全性 | 確認済み。V02、V03、V06、V07、V09を第3部に記載。 |
| C8 欠落 | 確認済み。V02、V03、V05を第3部に記載。 |
| C9 修正・追記の検証 | 全474件確認済み。U01 regression、U06/U18/U24 partially-fixed。 |
| C10 修正が開けた穴 | 確認済み。V01、V05、V06、V08を第3部に記載。 |
| C11 合理性 | 確認済み。V01–V09を第3部に記載。 |
| C12 探索型監査 | X1–X74および自由探索1件を確認済み。V01–V09を第3部に記載。 |

### 原則

| 原則 | 確認結果 |
|---|---|
| P1 三層構成 | 確認済み、検出0件。 |
| P2 識別子規範 | 確認済み、検出0件。 |
| P3 metadata.sqlite 8テーブル | 確認済み、検出0件。 |
| P4 chunks統一テーブル | 確認済み、検出0件。 |
| P5 チャンク分割 | 確認済み、検出0件。 |
| P6 OCR | 確認済み。V01を第3部に記載。 |
| P7 FTS | 確認済み、検出0件。 |
| P8 Embedding | 確認済み、検出0件。 |
| P9 バッチ処理・課金台帳 | 確認済み。V02、V08を第3部に記載。 |
| P10 書込順序・冪等性 | 確認済み、検出0件。 |
| P11 集約 | 確認済み、検出0件。 |
| P12 検索 | 確認済み。V04を第3部に記載。 |
| P13 GC・fsck | 確認済み。V05を第3部に記載。 |
| P14 SQLite設定 | 確認済み、検出0件。 |
| P15 元設計から不変の部分 | 確認済み、検出0件。 |
| P16 変更検知・耐久操作 | 確認済み。V03、V06、V07、V09を第3部に記載。 |