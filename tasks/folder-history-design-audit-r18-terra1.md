不合格
target.md 全 3207 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

# 第 1 部 — 回帰確認 (C9)

fixed: A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S29 / T01〜T18 のうち、下記 superseded 項目および T10・T16 を除く全項目。

superseded: A01→K25、A11（遷移詳細）→I05/I06/I13/I14、D08→K20、F05→I14、F07→I15、F12→I16/I17、F21→I03/I04、H02→I32、H04→I31、H15→I08/I11、H18→I16、H22→I15、I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I12→K04、I15→J04、I16/I17→J05/J01、I35→J13〜J16、J03→K10、J04→K01、J06（attempt UNIQUE）→K02、J07/K24→L09、J10→K09、J13→K16、J16→K13〜K15、K02（叙事文）→L01、K06→L02、K09→L03、K11→L03、K12/K13→L04、K14→L07、K19→L13、L04/L21→M02、L09/L28→M03/M09、L20→M04、L26→N14、L07/M05→N16、M01→N09、M06/K08→N17、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15、N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28、§21.5 の旧 M&S 記述→O29、O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37、Q02→R01、Q03→R05、Q04→R02、Q05/Q06（found）→R06、Q06（submit_rejected 除外）→R07、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16、R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06、S06→T09、S07→T05/T06、S11→T07、S19→T03、S20→T01、S23→T18、S24→T02、S25→T04。

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
|---|---|---|
| T10 | partially-fixed | §6 の Office 変換規範は「`upload_id 列・filename への intent_token 埋込は「実際に upload した bytes」(変換物)に適用する — 原本は upload しない`」とする一方、同じ §6 の Batch 入力規範は「`JSONL の各行は upload 済み原本の file id を参照`」「`upload_id 列は原本用`」とする。Office 文書では原本と upload 物が異なるため、両側を同時に満たせない。 |
| T16 | partially-fixed | §11.2 の掲載完全 SQL の `fts_hits` は `WHERE agg_chunk_fts MATCH :query` で終わり `LIMIT :fts_cap` がなく、`vec_hits` も `k = :k_fetch` のみである。一方、同節後段は「`fts_hits (および KNN の k)には内部上限 (LIMIT :fts_cap)`」を必須とする。さらに §19 は FTS 上限を ``:k_fts`` と再掲し、bind 名も一致しない。 |

# 第 2 部 — 探索ログ (C12)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 1 | X1 | 現在版 A → 1 tick 内に B 作成・編集・削除 → step 0 の完全 walk | 問題なし |
| 2 | X2 | `../x`、NUL、偽 `obj:`、コメント脱出値を含む入力 → scan / materialize | 問題なし |
| 3 | X3 | NFD 名を持つフォルダを case-insensitive から sensitive volume へ移動 → walk / resolver | 問題なし |
| 4 | X4 | 時計後退と同一 ms の複数 commit → LWW / cursor / generated_at を評価 | 問題なし |
| 5 | X5 | 10 万 file・100 万 chunk を仮定 → scan・RRF 中間集合を追跡 | X69 の上限欠落を除き問題なし |
| 6 | X6 | float32 little-endian、JCS 整数、vec0 の次元・距離を確認 | 問題なし |
| 7 | X7 | `job_create_started_at` 導入前 state=0 行 → migration backfill → intent 回復 | 問題なし |
| 8 | X8 | path traversal 名・root swap・他ユーザー可読 DB → openat / 権限規範 | 問題なし |
| 9 | X9 | WAL 中 app.sqlite の raw コピー、metadata のみ復元、object 破損 → 回復 | 問題なし |
| 10 | X10 | `.folder-history` の手動削除・編集・同期競合コピー → walk | 問題なし |
| 11 | X11 | profile 変更、floor、FTS view、preflight を同 tick で交錯 | 問題なし |
| 12 | X12 | register → OCR → chunk → embed → replicate → search → restore の PDF 経路 | 問題なし |
| 13 | X13 | register / fork / restore / drop / bootstrap の入力・失敗分岐を総点検 | 問題なし |
| 14 | X14 | submit / collect の 429、fp_cache 蓄積、objects 容量増大 | 問題なし |
| 15 | X15 | 主張「intent 回復で server 側未追跡 job は有界」→作成後クラッシュ→照合 | 破れず |
| 16 | X16 | 2 相 submit、reconcile、floor、upload cleanup をクラッシュ境界ごとに追跡 | 問題なし |
| 17 | X17 | unregister → detached → 再登録、および restore 後 scan | 問題なし |
| 18 | X18 | profiles 破損・pending_deletes 喪失・app 全損 → fsck / bootstrap | 問題なし |
| 19 | X19 | objects 書込み、metadata Tx、app Tx、migration 各境界で電源断 | 問題なし |
| 20 | X20 | 主張「profile 変更は宣言的に収束」→次元・距離変更中断→再 tick | 破れず |
| 21 | X21 | 相 1 reset、floor 引上げ、vec 差集合、app_config 更新を交錯 | 問題なし |
| 22 | X22 | fork の各 phase で crash → journal / flag から回復 | 問題なし |
| 23 | X23 | cost_ledger、detached、name_collision、name_invalid の読取側を確認 | 問題なし |
| 24 | X24 | vec 再充填の途中 crash、same-profile agg 欠落、client 前計上 | 破れず |
| 25 | X25 | app.sqlite だけの横断検索、restore 宛先、watch_root 解除後 | 問題なし |
| 26 | X26 | attempts / submission_seq / profile_record snapshot の全書込点を追跡 | 問題なし |
| 27 | X27 | fork journal 作成〜削除、移動、app 全損、再発見を交錯 | 問題なし |
| 28 | X28 | detached の state 0/1/2/3 → collect → sweep → 削除 → 再登録 | 問題なし |
| 29 | X29 | 保存名固定、case-only rename、NFC 衝突、restore 宛先を追跡 | 問題なし |
| 30 | X30 | 主張「seq 継承で再登録後 UNIQUE 衝突なし」→削除→再登録→close | 破れず |
| 31 | X31 | seq 継承、reconcile close、submit_rejected、client_exhausted | 問題なし |
| 32 | X32 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE × app 全損 | 問題なし |
| 33 | X33 | server/client × 終端理由 × close 経路の ledger 行数を追跡 | 問題なし |
| 34 | X34 | §11.2 の eligible、LIKE fallback、ready gate、folder-only mapping | X69 の cap 実装欠落を除き問題なし |
| 35 | X35 | 主張「submit_rejected は自動再投入しない」→retry→terminal を追跡 | 破れず |
| 36 | X36 | ON CONFLICT、seq 継承、detached 採用の課金記帳を交錯 | 問題なし |
| 37 | X37 | damaged / missing / fork の出入りと ready 母数、synced NULL 化 | 問題なし |
| 38 | X38 | journal digest、移動、HISTORY_CLEARED の commits 非空を追跡 | 問題なし |
| 39 | X39 | register の一時読取不能、別 id rebind、delete 最終確認 | 問題なし |
| 40 | X40 | 主張「ready は部分 index を通さない」→P2→P3→P2 を試行 | 破れず |
| 41 | X41 | 全終端理由 × server/client × ledger 記帳を確認 | 問題なし |
| 42 | X42 | ready 母数が 0→1、damaged 復帰、agg wipe を交錯 | 問題なし |
| 43 | X43 | raw resolver を NFC/NFD・case 衝突・raw 不在で全呼出点に適用 | 問題なし |
| 44 | X44 | standalone read、registered conflict、step -1 unreadable を追跡 | 問題なし |
| 45 | X45 | 主張「unknown で二重 job なし」→一覧遅延→伝播猶予を試行 | 破れず |
| 46 | X46 | token 記帳、found job 記帳、seq 更新、再観測を交錯 | 問題なし |
| 47 | X47 | 期限超記帳→rotation→detach→再登録の crash 境界を追跡 | 問題なし |
| 48 | X48 | restore 保全→LWW commit→rename、raw collision を追跡 | 問題なし |
| 49 | X49 | 全 §21 操作の fork 回復先行と破損 journal 例外を追跡 | 問題なし |
| 50 | X50 | 主張「無 id 記帳は NOT NULL と衝突しない」→期限超 sweep を試行 | 破れず |
| 51 | X51 | seq 行 UPDATE、found、client、detached を同一 lifecycle で交錯 | 問題なし |
| 52 | X52 | expired terminal→sweep→明示 retry→unregister を追跡 | 問題なし |
| 53 | X53 | 4 照合点で三値・期限・猶予・記帳・掃除を比較 | 問題なし |
| 54 | X54 | journal 有効/破損/無 × flag 有無 × old/new/第三 id | 問題なし |
| 55 | X55 | folder-only の profile 一意性と current_tool tie を交錯 | 問題なし |
| 56 | X56 | G / `\G` / `\\G` の escape・un-escape・厳密認識を実行 | 問題なし |
| 57 | X57 | 自己記述化済み terminal 行を再投入し、dispatch/sweep を追跡 | 問題なし |
| 58 | X58 | detached terminal→4.5→再登録で state=3 行を再利用 | 問題なし |
| 59 | X59 | 課金される submit_rejected→seq 更新→sweep 除外を追跡 | 問題なし |
| 60 | X60 | 偽 grammar 行、object 不在、再 materialize を含む往復 | 問題なし |
| 61 | X61 | 主張「伝播猶予で誤載せ直しなし」→一覧遅延・未来 skew を試行 | 破れず |
| 62 | X62 | job_create_started_at 記録後・呼出前 crash、rotation 後を追跡 | 問題なし |
| 63 | X63 | cancel→attempts 上限→明示 retry→再 cancel を追跡 | 問題なし |
| 64 | X64 | token 記帳済み後の遅延 found を IN 判定で追跡 | 問題なし |
| 65 | X65 | no-replace 非対応 FS、EEXIST、fallback rename を追跡 | 問題なし |
| 66 | X66 | 規範文・要約・DDL コメント・SQL の再掲を横断比較 | U01・U03 を検出 |
| 67 | X67 | token 残存 terminal→明示 retry→sweep 完了後に相 1 を実行 | 問題なし |
| 68 | X68 | cancel 済み行→明示 retry→再 unregister→ledger / token cleanup | 問題なし |
| 69 | X69 | eligible 100 万件、`:limit=10`、FTS/KNN 上限を適用して RRF | U03 を検出 |
| 70 | X70 | DOCX→変換 PDF→upload/JSONL、次にコンバータ失敗を発生 | U01・U02 を検出 |

# 第 3 部 — 新規検出 (C1〜C8, C10, C11, C12)

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 (P#/C#/X#) | 修正案 |
|---|---|---|---|---|---|---|
| U01 | major | §6 は Office について「`実際に upload した bytes` (変換物)」「`原本は upload しない`」とする。他方で同節は「`JSONL の各行は upload 済み原本の file id`」「`upload_id 列は原本用`」とする。 | Office 入力の JSONL 参照先・`upload_id` の意味が相互矛盾する。 | DOCX を入力 → PDF へ変換して PDF を upload → JSONL を「原本 Word の id」で作れば未 upload の id を参照し、PDF id で作れば「原本用」列の規範に反する → 実装者が追加判断なしに正しい投入・cleanup を実装できない。 | P6 / C1 / C3 / C6 / C11 / C12 X70 / T10 | 「upload済み原本」を「実際に upload した入力（原本または変換物）」へ統一し、`upload_id` も常にその bytes の id と明記する。 |
| U02 | major | §6 は Office 文書を「`決定論的コンバータで PDF へ変換してから投入`」とするが、terminal marker は `unsupported_format` / `oversize` のみ。§9.1 の失敗分岐も upload・job 作成後の外部失敗しか定義しない。 | コンバータ失敗の状態遷移、再試行、terminal 化、課金なしの扱いが未定義である。 | 対応するが壊れた DOCX → preflight は対象形式として通過 → PDF 変換が失敗し upload 前で停止 → state=0 の intent 回復は job 未作成として載せ直す一方、恒久失敗・一時失敗のどちらへ遷移すべきか未定義 → 無限再試行または実装依存の terminal 化となる。 | P6 / C7 / C8 / C11 / C12 X70 | 変換失敗を preflight の明示分岐に追加する。恒久的な入力不正は terminal marker、環境・一時 I/O は `retry_not_before` を伴う非課金 retry とし、converter/profile 更新時の再判定条件も定義する。 |
| U03 | major | §11.2 の掲載 SQL は `fts_hits` に `LIMIT :fts_cap` がなく、KNN は `k = :k_fetch` のみ。同節後段は「`fts_hits (および KNN の k)には内部上限 (LIMIT :fts_cap)`」、§19 は ``:k_fts`` と再掲する。 | 中間候補上限が実行可能な完全 SQL に反映されず、bind 名も分裂している。 | eligible 100 万件、`:limit=10` の検索 → 掲載 SQL は全 FTS hit を rank 化・RRF 集約してから外側 LIMIT を適用 → 一時領域・メモリを無制限に消費し得る。実装者が cap を補う場合も `:fts_cap` と `:k_fts` のどちらを契約にするか定まらない。 | P12 / C4 / C6 / C10 / C11 / C12 X69 / T16 | `:fts_cap` を唯一の契約名に統一し、掲載 `fts_hits` SQL に順位決定後の `LIMIT :fts_cap` を明記する。KNN も `k_fetch` を同じ上限以下に導出する完全 SQL へ更新する。 |

# 第 4 部 — 確認済みの列挙

確認済み・問題なし:

- C2: DDL、FK、FTS5 external content、INSERT/DELETE trigger の整合。FTS 部分は in-memory SQLite で external-content integrity-check、INSERT、DELETE を検証済み。
- C5: OCR 単価、+25%、Batch 50% 割引、768 の参考値、RRF k=60、8 テーブル表記に矛盾なし。
- P1〜P5、P7〜P11、P13〜P16。