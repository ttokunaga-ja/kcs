不合格
target.md 全 3284 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第 1 部 — 回帰確認（C9）

対象 474 項目: A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S29 / T01〜T18 / U01〜U24。

下記 superseded と例外を除く全要求は fixed。

superseded: F05 (→I14); F07 (→I15); F12 (→I16/I17); F21 (→I03/I04); H04 (→I31); H15 (→I08/I11); H18 (→I16); H22 (→I15); A11 遷移詳細 (→I05/I06/I13/I14); H02 衝突順 (→I32)。  
I03/I04 (→J06); I05/I06 (→J01/J02); I09/I11 (→J03); I15 (→J04); I16/I17 (→J05/J01); I35 (→J13〜J16)。  
J04 (→K01); J06 の UNIQUE 要求 (→K02); J03 (→K10); J10 (→K09); J13 (→K16); J16 (→K13〜K15); I12 (→K04); D08 (→K20); A01 (→K25)。  
K02 叙事文 (→L01); K12/K13 (→L04); K06 (→L02); K09 (→L03); K14 (→L07); J07/K24 (→L09); K21 (→L20); K19 (→L13)。  
L09 (→M03); L28 (→M03/M09); L20 (→M04); L04/L21 (→M02)。  
M09 (→N05/N06); M10 (→N10); M12 (→N38); M29 (→N15); M06/K08 (→N17); L07/M05 (→N16); L26 (→N14); M01 (→N09); M08 (→N28); M13 (→N30)。  
N03 (→O05/O06); N04 (→O02/O03); N13 (→O21); N15 (→O04/O25); N36 (→O16); N39 (→O14); N40 (→O28); N28 (→O13); N07 (→O12)。  
O28 (→Q01); O17 (→Q02); O02/O03 (→Q05/Q07); O04 (→Q06); O05 (→Q04); O07 (→Q09); O09 (→Q11/Q12); O11 (→Q13/Q36); O18 (→Q23); O19 (→Q24); O13 (→Q12); O30 (→Q37)。  
Q02 (→R01); Q04 (→R02); Q09 (→R03); Q12 (→R04); Q03 (→R05); Q05/Q06 (→R06); Q06 前段 (→R07); Q10 (→R14); Q13/Q14 (→R15/R16)。  
R06 (→S10/S15); R07 (→S19/S28); R08 (→S01); R13/R18 (→S02); R20 (→S03); R23 (→S04); R25 (→S06)。  
S06 (→T09); S07 (→T05/T06); S11 (→T07); S19 (→T03); S20 (→T01); S23 (→T18); S24 (→T02); S25 (→T04)。  
T03 (→U04); T08 (→U03); T10 (→U01); T11 (→U05); T16 (→U02)。

| ID | 判定 | 根拠（§ + 短い引用） |
|---|---|---|
| U01 | regression | §6 は Office 文書について「`upload_id` 列・filename への intent_token 埋込は『実際に upload した bytes（変換物）』に適用」とする。一方、同節の Batch 入力は「`upload_id` 列に持たず（列は原本用）」、続く見出しも「upload 原本の削除」と残る。DOCX→変換 PDF の場合、後者に従うと PDF の file id を追跡・掃除できず、変換 PDF が残留する。 |
| U06 | partially-fixed | §9.1 collect は「state を 2/3 へ確定する**全ての UPDATE**に共通」と `completed_at = now` を要求するが、DDL コメントは「**collect が** state=2/3 へ閉じた時刻」「書込点は §10 collect」と限定する。`state=0 → 相2a upload の恒久 4xx → state=3` は collect ではないため、後者どおりの実装では completed_at が欠落する。 |

## 第 2 部 — 探索ログ（C12、74 シナリオ）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | 追跡済み文書・OCR in-flight → 編集、削除、collect、次 tick | 問題なし |
| 2 | X2 | 制御文字名・symlink・偽 obj: 行 → walk、正規化、解析 | 問題なし |
| 3 | X3 | NFD 名のフォルダを case-sensitive volume へ移動 → walk、resolver | 問題なし |
| 4 | X4 | 壁時計後退後の再 materialize → generated_at、LWW、cursor 比較 | 問題なし |
| 5 | X5 | 10万ファイル・100万 chunk 想定 → fp、FTS、差集合処理を追跡 | 問題なし |
| 6 | X6 | 2文字検索語と 3文字検索語 → LIKE fallback、FTS5 trigram | 問題なし |
| 7 | X7 | 旧 writer と新 migration → tick.lock 下の schema 更新、再確認 | 問題なし |
| 8 | X8 | `..` を含む論理名 → raw resolver、restore 宛先検証 | 問題なし |
| 9 | X9 | object 破損・metadata 単独復元 → fsck、fail-closed、再構築 | 問題なし |
| 10 | X10 | `.folder-history` 手動削除と部分同期 → repository-id 照合、damaged 分岐 | 問題なし |
| 11 | X11 | NFC 論理名と非正規化 fp 名 → scan_cache、resolver、commit | 問題なし |
| 12 | X12 | watch root 登録 → OCR → embed → replicate → 検索 → restore | 問題なし |
| 13 | X13 | status・明示再登録・明示解決の入力と失敗分岐を総点検 | 問題なし |
| 14 | X14 | submit/collect の 429 と fp_cache 孤児 → backoff、M&S | 問題なし |
| 15 | X15 | 主張: ledger、pending delete、profile、restore、fsync の5防御; 試行: 各クラッシュ列; 破れず | 問題なし |
| 16 | X16 | 複数 JSONL job → token 分割、相1、intent 回復、upload 掃除 | 問題なし |
| 17 | X17 | register 中断 → damaged → 再実行、unregister → 再登録 | 問題なし |
| 18 | X18 | profile 孤児、pending delete、app 全損 → fsck、deep-scan、再入力 | 問題なし |
| 19 | X19 | objects 書込後・metadata 前・app 前の各電断 → 次 tick 回復 | 問題なし |
| 20 | X20 | 主張: job 有界化、月跨ぎ ledger、profile 収束、delete、dir fsync; 試行: 境界クラッシュ; 破れず | 問題なし |
| 21 | X21 | profile 変更中の相1・collect・floor → snapshot、差集合、伝播 | 問題なし |
| 22 | X22 | flag 記録済み fork の各 phase で中断 → tick 冒頭 recovery | 問題なし |
| 23 | X23 | cost_ledger、detached、name status → 検索・GC・walk の読手を追跡 | 問題なし |
| 24 | X24 | 主張: vec 差集合、agg 検査、client queue; 試行: 次元変更・部分充填・中断; 破れず | 問題なし |
| 25 | X25 | app.sqlite 単独横断検索、restore 各入力、watch_root 解除 → 実行経路 | 問題なし |
| 26 | X26 | submission_seq・attempts・ledger → 相3、intent 採用、client 前計上 | 問題なし |
| 27 | X27 | fp_cache 済み fork 対象 → PREPARED journal 書込後・flag 前にクラッシュ → 次 tick walk | V01 を検出 |
| 28 | X28 | detached の state 0/1/2/3 → collect、ledger、掃除、再登録 | 問題なし |
| 29 | X29 | case-only rename と NFC 衝突 → 保存名、restore、LWW を追跡 | 問題なし |
| 30 | X30 | 主張: seq UNIQUE、client 有界化、保存名、pending delete、detached; 試行: 各反例列; 破れず | 問題なし |
| 31 | X31 | 行削除→再作成→相3 → ledger MAX 継承、close、明示 retry | 問題なし |
| 32 | X32 | 各 fork phase・flag 存在・app 全損 → phase と実 id による再開 | 問題なし |
| 33 | X33 | server/client × 終端理由 × 通常/reconcile/detached close → ledger 行数 | 問題なし |
| 34 | X34 | eligible、LIKE、KNN、at_hash、ready 未更新 → SQL 実行経路 | 問題なし |
| 35 | X35 | 主張: seq 継承、reconcile、rejected、detached、最終 stat; 試行: 反例列; 破れず | 問題なし |
| 36 | X36 | ON CONFLICT、seq 継承、detached 採用 → 全 close 経路を追跡 | 問題なし |
| 37 | X37 | missing/fork 出入りと profile P2→P3 → ready、sync、agg_vec | 問題なし |
| 38 | X38 | flag 記録済み fork を移動 → journal 走査、再発見、回復 | 問題なし |
| 39 | X39 | 一時読取不能、rebind、対象外型、dirfd → register/detached/scan | 問題なし |
| 40 | X40 | 主張: close 冪等、ready、EIO、TOCTOU、metric; 試行: 各反例列; 破れず | 問題なし |
| 41 | X41 | server/client × 全終端理由 → ledger、seq、profile 数え直し | 問題なし |
| 42 | X42 | damaged/read不能/missing の母数変化 → building、ready、再充填 | 問題なし |
| 43 | X43 | NFC/NFD/collision/raw 不在 × volume 種別 → resolver 3 呼出点 | 問題なし |
| 44 | X44 | registered/standalone/conflict read → 規約12、step -1、fork 除外 | 問題なし |
| 45 | X45 | 主張: client 記帳、unknown、期限超、ready、raw resolver; 試行: 反例列; 破れず | 問題なし |
| 46 | X46 | token 記帳→rotation→job id 記帳→collect → 述語と seq を比較 | 問題なし |
| 47 | X47 | 期限超 Tx の各クラッシュ → 記帳、attempt 消費、rotation、detached | 問題なし |
| 48 | X48 | restore 前の未取り込み変更 → 保全 commit、rename、次 tick scan | 問題なし |
| 49 | X49 | 各 §21 操作前に有効 journal → recovery 完了後に操作 | 問題なし |
| 50 | X50 | 主張: 無 id 記帳、sweep、future token、escape、restore; 試行: 反例列; 破れず | 問題なし |
| 51 | X51 | 期限超/(b')/sweep の seq UPDATE → retry、close、再作成 | 問題なし |
| 52 | X52 | expired terminal → sweep → 明示 retry → 再投入 | 問題なし |
| 53 | X53 | 4 照合点で三値、期限、skew、猶予、述語、seq を比較 | 問題なし |
| 54 | X54 | journal 有効/破損/無 × flag × old/new/第三 id → register/解決 | 問題なし |
| 55 | X55 | 単独検索で profile 混在と tool 混在 → current 規則、FTS-only | 問題なし |
| 56 | X56 | 手書き非 canonical grammar 行 → escape、un-escape、FTS | 問題なし |
| 57 | X57 | found 自己記述化後の再投入 → dispatch、sweep、job_missing | 問題なし |
| 58 | X58 | detached terminal → sweep → 同 repository 再登録 | 問題なし |
| 59 | X59 | 課金される submit_rejected → 倒す分岐、sweep、明示 retry | 問題なし |
| 60 | X60 | `G` / `\G` / `\\G` と object 不在 → escape、認識、再 materialize | 問題なし |
| 61 | X61 | 主張: 伝播猶予採用条件と1 Tx、自己記述化、decoder; 試行: 契約境界; 破れず | 問題なし |
| 62 | X62 | job_create_started_at 記録後・呼出前に中断 → 再試行、期限判定 | 問題なし |
| 63 | X63 | cancelled terminal → token sweep → 再登録、明示 retry | 問題なし |
| 64 | X64 | token 推定行後に別 attempt job 発見 → IN 述語、自己記述化 | 問題なし |
| 65 | X65 | no-replace 非対応 FS → EINVAL、再 lstat、通常 rename | 問題なし |
| 66 | X66 | 規範文・DDL コメント・要約・SQL の横断照合 → Office upload / completed_at | U01/U06 を検出（第1部） |
| 67 | X67 | unknown が継続する token 残存行 → stalled、abandon、再投入 | 問題なし |
| 68 | X68 | cancel→明示 retry→再 cancel→再登録 → ledger、token、upload | 問題なし |
| 69 | X69 | fts_cap/k 上限到達 → RRF、tie-break、limit、status | 問題なし |
| 70 | X70 | DOCX→変換 PDF→upload→cleanup、converter 更新 → tool_profile 変更 | U01 を検出（第1部） |
| 71 | X71 | state=0 載せ直しの Tx 境界 → 旧 token 記帳、新 token、再開 | 問題なし |
| 72 | X72 | abandon 後に旧 job が可視化 → IN 述語、明示 retry、新 token | 問題なし |
| 73 | X73 | convert_failed 後の converter 更新 → 旧 terminal と新 target_key | 問題なし |
| 74 | X74 | 一時 EIO と構文失敗を交互に発生 → count、fp 非確定、bytes commit | 問題なし |

## 第 3 部 — 新規検出

| ID | 重大度 | 該当箇所（§ + 短い引用） | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| V01 | major | §20.3「`dir_fp 一致 → D 以下を丸ごとスキップ（DB 照会・後続処理ゼロ）」「このチェックだけは常に行う」; §21.3「fork journal を層1に書く」後に「app 側には fork_in_progress…を記録」、「毎 tick の walk が…fork-journal を持つフォルダを検出したら…回復」 | fp スキップの例外は `.folder-history` の存在・repository-id 照合だけで、同じ fp 入力から除外される fork-journal の検査・回復を含まない。§21.3 の毎 tick 回復規範と両立しない。 | fp_cache 済み登録フォルダ → PREPARED journal を耐久書込み → flag 記録前にクラッシュ → 原本と repository-id は不変 → 次 tick は同じ dir_fp で skip し journal を見ない → old_id の通常 scan/commit が再開し、未完 fork が残留する。 | P16 / C1 / C10 / C11 / C12 X27 | fp skip の例外に fork-journal の存在・完全性検査と回復を加え、通常 scan より先に実施する。 |

## 第 4 部 — 確認済みの列挙

検出 0 件: C2、C3、C4、C5、C6、C7、C8。  
確認済み: P1〜P5、P7〜P8、P10〜P15。