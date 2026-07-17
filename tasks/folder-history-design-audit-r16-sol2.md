# 判定: **不合格**

全 403 件の C9 と、X1〜X61 を含む 72 シナリオを確認しました。

不合格理由は次のとおりです。

- C9: `partially-fixed` 5 件。`not-fixed / regression` は 0 件
- 新規検出: **fatal 8 件 / major 12 件 / minor 3 件**
- 特に、未追跡 Batch job の二重作成、attempts 上限の超過、同一 job の二重記帳、fork 明示解決の脱出不能が再現可能です

---

## 第1部 — 回帰確認 C9

403/403 件を判定済みです。

| 系統 | fixed | superseded | partially-fixed |
|---|---|---|---|
| A | A02–A10, A12–A24 | A01→K25、A11→I05/I06/I13/I14 | — |
| B | B01–B18 | — | — |
| D | D01–D04, D06–D07, D09–D14 | D05→E04、D08→K20 | — |
| E | E01–E06 | — | — |
| F | F01–F04, F06, F08–F09, F11, F13–F20, F22–F27 | F05→I14、F07→I15、F10→H08、F12→I16/I17、F21→I03/I04 | — |
| G | G01–G02 | — | — |
| H | H01, H03, H05–H14, H16–H17, H19–H21, H23–H30 | H02→I32、H04→I31、H15→I08/I11、H18→I16、H22→I15 | — |
| I | I01–I02, I07–I08, I10, I13–I14, I18–I34, I36–I38 | I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I12→K04、I15→J04、I16/I17→J05/J01、I35→J13–J16 | — |
| J | J01–J02, J05, J08–J09, J11–J12, J14–J15, J17–J20 | J03→K10、J04→K01、J06→K02、J07→L09、J10→K09、J13→K16、J16→K13–K15 | — |
| K | K01, K03–K05, K07, K10, K15, K17–K18, K20, K22–K23, K25–K26 | K02→L01、K06→L02、K08→N17、K09/K11→L03、K12/K13→L04、K14→L07、K16 の seq 部分→L01、K19→L13、K21→L20、K24→L09 | — |
| L | L01–L03, L05–L06, L08, L10–L11, L13–L19, L22–L25, L27 | L04/L21→M02、L07→N16、L09→M03、L20→M04、L26→N14、L28→M03/M09 | **L12** |
| M | M04, M07, M11, M14–M28 | M01→N09、M03/M05→N16/R28、M06→N17、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15 | **M02** |
| N | N01–N02, N05–N06, N08–N12, N14, N16–N27, N29–N35, N37–N38, N41–N45 | N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28 | — |
| O | O01, O06, O08, O10, O12, O14–O16, O20–O27, O29 | O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37 | — |
| Q | Q01, Q07–Q08, Q11, Q15–Q37 | Q02→R01、Q03→R05、Q04→R02、Q05/Q06→R06/R07、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16 | — |
| R | R01–R07, R09–R17, R19, R21–R29 | — | **R08, R18, R20** |

### C9 の非 fixed 項目

| ID | 判定 | 根拠 |
|---|---|---|
| L12 | partially-fixed | §11.2 後段の差替え形が `WHERE c.text LIKE ... OR c.heading_path LIKE ...` で、完全形に必要な `c.text IS NOT NULL` を落としている。R20 と同じ残存。 |
| M02 | partially-fixed | §9.1 の詳細規範は terminal 化→4.5→3条件成立後の削除だが、§21.2 に `client ... terminal 記帳後に削除` が残る。 |
| R08 | partially-fixed | 上記 §21.2 の短縮記述が、「記帳して即削除」を排除する R08 の段階遷移と衝突する。 |
| R18 | partially-fixed | §13 は `INSERT INTO chunk_fts(chunk_fts) VALUES('integrity-check')` を掲載するが、これは external content との比較を実行しない。 |
| R20 | partially-fixed | §11.2 前半は `c.text IS NOT NULL AND (...)` を必須とする一方、後段の差替え SQL から条件が脱落している。 |

R01〜R04 の転記対は確認済みです。R01 の z 例外、R02 の `(i)〜(iv)` 同一 Tx、R03 の主要削除ゲート、R04 の restore 再 lstat 義務は両側に存在します。ただし R03 と並存する §21.2 の短縮記述が R08 を部分回帰させています。

---

## 第2部 — 探索ログ C12

略号: `BR=batch_requests`、`CL=cost_ledger`、`MD=markdown_documents`、`V=embedding_vec/agg_vec`。

| # | 観点 | 初期状態 → 操作列 → 結果 |
|---:|---|---|
| 1 | X1 | 現在版 H0→H1 編集→OCR `state=1`→原本削除→collect。H1 派生と ledger は保存され、2回・30秒 absent 後に delete。現在版検索からのみ消える。問題なし。 |
| 2 | X2 | 手書き `\![x](obj:see)`、偽 img block、制御文字名を materialize/chunk。loose escape と strict image 認識が分離され、phantom 化しない。問題なし。 |
| 3 | X3 | NFD 名を case-insensitive→sensitive volume へ移動→walk/restore。保存論理名と raw resolver で決定的に系列化。問題なし。 |
| 4 | X4 | 最新 commit 時刻100→時計90へ後退→編集。`created_at=101` となり LWW/cursor は後退しない。問題なし。 |
| 5 | X5 | 100万 chunk で一般語検索。正しさは維持するが全 FTS 候補 rank が高コスト。§19 の再考条件内。 |
| 6 | X6 | `text=NULL, heading_path=["会計"]` の image chunk→2文字検索。後段 LIKE SQLだけが当該行を返す。S03。 |
| 7 | X7 | migration 中 crash→DDL/user_version とも rollback→再実行。旧 writer は lock 後の版再確認で停止。問題なし。 |
| 8 | X8 | `../x`、絶対パス、NUL、`.folder-history` 含有名→scan/restore。`name_invalid` で拒否。問題なし。 |
| 9 | X9 | object rename/fsync 後、metadata Tx 前に ENOSPC→未参照 object のみ。metadata 後・app 前なら成果確認で close。問題なし。 |
| 10 | X10 | metadata 手編集、object 欠損、部分同期→fsck/register。構造破損は damaged、一時 EIO は保留。問題なし。 |
| 11 | X11 | OCR floor 設定→再チャンク→crash→collect。app floor 先行で silent cancel は起きない。問題なし。 |
| 12 | X12 | watch root→commit→OCR→chunk→embed→replicate→検索→hash照合→restore。通常経路は一気通貫。 |
| 13 | X13 | 画像フィルタ一括変更→operation record 保存。7-key allow-list に格納先がなく、途中 crash 後の未完了表示不能。S13。 |
| 14 | X14 | submit/collect 429 + Retry-After→`retry_not_before` 保存→期限前 tick は skip。問題なし。 |
| 15 | X15 | dir fsync、unknown保持、vec差集合、30秒delete、空母数readyの5主張を反証。通常境界では破れず。 |
| 16 | X16 | 1 repo の JSONL を複数 job に分割→job ごと token→phase 3 前 crash。token 粒度を保てる。問題なし。 |
| 17 | X17 | register途中 crash、restore後scan、unregister→再登録。健全 journal の通常列は収束。問題なし。 |
| 18 | X18 | tool/embedding に同一 profile JSON H→kind1 INSERT→kind2 INSERT OR IGNORE。kind2 record が失われる。S14。 |
| 19 | X19 | objects後、metadata後、phase2b後の各電断。通常列は未参照object、close漏れ、intent採用へ収束。 |
| 20 | X20 | 「1 job上限」「確認月配賦」「宣言的profile」等を反証。通常列は破れず、後述の時刻・一覧境界で破れる。 |
| 21 | X21 | profile A→Bとfloor・vec再充填・agg key更新を交錯。主経路は収束。問題なし。 |
| 22 | X22 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE 各点で crash。健全 journal なら phase+id で一意に再開。 |
| 23 | X23 | `image_filter` と一括変換 status を同時保存。operation key 不在で契約違反。S13。 |
| 24 | X24 | vec CREATE→一部充填→crash。次 tick の差集合が key 欠落を補完。問題なし。 |
| 25 | X25 | app 単独横断検索と standalone 検索。app_config/profiles の給源分離は機能。問題なし。 |
| 26 | X26 | BR削除、CLのMAX seq=n→再登録→新 phase1→phase3。n継承後 n+1 で close。問題なし。 |
| 27 | X27 | fork 中にフォルダ移動→bootstrap。健全 journal は再発見より先に処理される。問題なし。 |
| 28 | X28 | detached client `state=0,id=T,token=T`→§21.2短縮文を字義実装→記帳直後削除。token/upload追跡を失う。S01。 |
| 29 | X29 | case-only rename→sensitive→insensitive 移動。BINARY一致/UTF-8 tie-break で決定的。問題なし。 |
| 30 | X30 | seq継承、client上限、fork回復、保存名固定、delete最終確認を反証。通常列は破れず。 |
| 31 | X31 | phase1/client前計上/明示再生成/preflight の全 BR INSERT を削除後再作成。ledger MAX継承あり。問題なし。 |
| 32 | X32 | fork全phase×app全損。journalが健全なら層1だけで復旧。問題なし。 |
| 33 | X33 | server/client × terminal理由を全組合せ。課金される server 4xx の記帳手順だけ未定義。S11。 |
| 34 | X34 | LIKE差替え SQL を最小行で実行。`text=NULL` image chunk が heading のみで返る。S03。 |
| 35 | X35 | reconcile close、rejected、fork、detached、delete最終確認を反証。S01以外の主要主張は維持。 |
| 36 | X36 | profile A→B→A、同一 seq close を再実行。`ON CONFLICT DO NOTHING` で Tx abort しない。問題なし。 |
| 37 | X37 | building P2→P3→P2。wipe時の synced NULL 化により空 index ready は防止。問題なし。 |
| 38 | X38 | HISTORY_CLEARED 後に commits 非空→回復。手順1から全削除し直す。問題なし。 |
| 39 | X39 | register時の一時EIO/別id/対象外型/dirfd操作。4分類は整合。問題なし。 |
| 40 | X40 | ready母数、query TOCTOU、z unreadable、fork移動を反証。主要経路は破れず。 |
| 41 | X41 | terminal理由×server/client×closeのledger行列。chargeable rejectだけ欠落。S11。 |
| 42 | X42 | damaged C を除外して A/B ready→C復帰。readyは設定時被覆の宣言であり通常状態。 |
| 43 | X43 | NFC/NFD/raw無し/collision×case感度×resolver 3呼出点。通常分岐は一意。 |
| 44 | X44 | registered置換read、standalone、z unreadable、fork中read。規約12のscoped動作は整合。 |
| 45 | X45 | client中間課金、unknown、期限超、raw restore、zを反証。raw不在競合でS15。 |
| 46 | X46 | token Tでestimated記帳→後から実job Jをfound。ledger述語がT/Jで分裂し同一jobを2行記帳。S08。 |
| 47 | X47 | detached server `attempts=2,max=3,state=0`→期限超absence。ledger/terminal後も attempts=2。S09。 |
| 48 | X48 | restore開始時raw無し→tmp作成中に外部editorが同名作成→rename前比較。比較する保全tupleが存在しない。S15。 |
| 49 | X49 | flag `{old=O,new=N}` + 破損journal→journal除去→§21.1 step2。新ID N′となりflagを掃除不能。S04。 |
| 50 | X50 | FTS postingのみ削除→掲載integrity-check→成功、MATCHは0件。S02。 |
| 51 | X51 | token/real-job/clientのseqを連続採番。通常採番は整合するがtoken→job再同定でS08。 |
| 52 | X52 | expired/rejected/client_exhausted/tool_changed→sweep→retry。通常terminalは収束。 |
| 53 | X53 | job Jがlistの2ページ目→1ページ目200にtoken無し→confirmed-absent。J2を作成。S05。 |
| 54 | X54 | 破損journal解決の各crash位置。step2の新UUIDがflag.new_idと一致せず脱出不能。S04。 |
| 55 | X55 | embeddings一意、tool generated_at同時刻、空Markdownでstandalone検索。tie-break/FTS-only縮退は定義済み。 |
| 56 | X56 | G / `\G` / `\\G` / 非canonical行をescape→unescape。1個前置/1個除去で可逆。問題なし。 |
| 57 | X57 | b′ found→seq+1+ledger(J)+BR.job_id=J→crash→sweep。J→T方向の二重記帳は自己記述化で防止。 |
| 58 | X57 | 逆方向: deadlineでledger(T)→後でJ visible→sweepの述語はJのみ。ledger(T), ledger(J)が併存。S08。 |
| 59 | X58 | detached client state0→同Tx terminal化→4.5→token NULL→削除、という§9.1詳細経路。問題なし。 |
| 60 | X58 | detached server期限超→state3 expiredだがattempts不変→再登録でstate3/attempts<maxが再投入。S09。 |
| 61 | X59 | 非課金が契約確定したclient 4xx→id NULL→rejected除外→掃除。問題なし。 |
| 62 | X59 | 課金されるserver 4xx→submit_rejected→sweepが照会・記帳なしでtoken NULL。実課金がledgerから欠落。S11。 |
| 63 | X60 | canonical/object実在、canonical/object不在、手書きslash、非canonicalの全組合せ。strict認識とloose decoderは両立。 |
| 64 | X60 | grammar再materializeを2回。保存済みescaped本文を引継ぐためslash累積なし。問題なし。 |
| 65 | X61 | token時刻がnow+4分、job作成済み、一覧可視化遅延1分。future>5分でも過去側graceでもなく即再投入。S06。 |
| 66 | X61 | phase1 T→15分upload→job J作成→直後crash→一覧遅延1分。token年齢16分なので10分grace外。S07。 |
| 67 | X61 | Mistral list `page=0,page_size=100,total=101`、Jは101件目→先頭pageだけ正常完走。S05。 |
| 68 | X61 | jobが1分で完了→24h後一覧から消失→token年齢25h。72h相当閾値前なので「未作成」として再投入。S20。 |
| 69 | 自由 | Vの同一key・同次元のvector bytesだけV′へ変更。差集合・dim/metric・PRAGMAは全部通り誤順位が残る。S16。 |
| 70 | 自由 | MD→chunks 2行から1行を通常DELETEしFTS triggerも同期。MDはdoneのまま、fsckも通りchunkが永久欠落。S17。 |
| 71 | 自由 | `state=0,upload_id=U1`でjob未作成→confirmed-absent→requeue。terminal guardでU1を消せずU2が列を上書き。S12。 |
| 72 | 自由 | standalone folder `/A/F`→`/B/F`へrebind。新path cacheだけ削除され旧 `/A/F/*` がwalk域外で永久残留。S22。 |

---

## 第3部 — 検出事項

### Fatal

| ID | 根拠・再現 | 修正案 |
|---|---|---|
| S04 | §21.3: `journal 除去 ... §21.1 手順 2 ... flag ... id=new`。§21.1 step2は`repository-id (UUIDv7) を生成`。flagのNと生成ID N′が一致せず、N′はold/new以外としてdamagedのまま永久除外される。 | 破損journal解決ではflagの`new_id`を再利用する。別IDを使うならmarker書込前にflagを耐久的に同じIDへ更新する。 |
| S05 | §9.1: `一覧の正常応答に無い`をconfirmed-absentとするが、完全走査条件がない。Jが後続pageにあるとJ2を作る。Mistral list APIは`page/page_size`と`total`を持つため、先頭pageだけの200は不存在証明にならない。[Mistral Batch API](https://docs.mistral.ai/api/endpoint/batch) | metadata一致の完全server filter、または`total`を満たす全page走査完了だけをconfirmed-absentとする。部分応答・途中失敗はunknown。 |
| S06 | §9.1: future判定は`now + ... 5分より未来`のみ、伝播猶予は`0 ≤ now − token時刻`のみ。tokenがnow+4分なら両方から漏れ、作成直後の未可視jobを未作成扱いする。 | propagation windowを`-allowed_skew ≤ now-token ≤ grace`へ広げ、future側もgrace中はunknownにする。 |
| S07 | §9.1: token時刻は`相1実行時刻`、採用条件は`一覧の可視化遅延上限 ≤ 伝播猶予`。upload/job作成までの時間を含まないため、phase1から15分後に作成したjobは作成直後でもgrace外になる。 | 採用条件を「phase1→job acceptance最大時間 + 可視化遅延 ≤ grace」にするか、job作成直前の耐久時刻を別に保存する。 |
| S08 | §9.1の期限超記帳は`batch_job_id=intent_token`、後日のfound述語は`発見 job id`。Tで推定記帳済みでもJのledgerが無いため、sweepが同一jobをJでもう一度記帳する。 | ledgerに安定した`intent_token/attempt_id`列を持たせ、T→Jの同一attempt対応を保存する。append-onlyのままならalias表を追加する。 |
| S09 | detached期限超分岐は`submission_seq+1 + ... state=3 expired`だが、attached側の必須`attempts+1`がない。再登録すると`state=3 & attempts<上限`として自動再投入される。 | detached期限超でも同一Txでattempts+1し、上限到達を判定する。 |
| S10 | 通常found採用は`attempts+1 + submission_seq+1`だが、close b′/sweep foundはseqとledgerだけ。phase2で作ったjobをattemptsに数えない。 | b′/sweep foundの未記帳述語と同じTxでattempts+1する。既存ledgerの場合は再増分しない。 |
| S20 | §9.1は`timeout_hours + 結果保持期限 + 猶予1日`より前のabsenceを「未作成」とする。しかしjobが早期完了すれば、結果・一覧がその合計より早く消え得る。例: 1分完了→24h保持→25hでabsence→無記帳再投入。 | 結果保持期限とjob-list保持契約を分離する。最短消滅時点以後のabsenceは常に「作成済みかもしれない」と扱うか、providerの耐久idempotency keyを使う。 |

### Major

| ID | 根拠・再現 | 修正案 |
|---|---|---|
| S01 | §9.1は`state=3 + completed_at`→4.5→3条件後削除だが、§21.2に`client ... terminal記帳後に削除`が残る。字義実装するとtoken/upload追跡を失う。 | §21.2を「同Txでterminal化し、削除は4.5完了後のみ」に統一する。 |
| S02 | §13掲載の`INSERT INTO chunk_fts(chunk_fts) VALUES('integrity-check')`はindex内部だけを検査する。external content比較には`rank=1`が必要。[SQLite FTS5](https://www.sqlite.org/fts5.html#the_integrity_check_command) | `INSERT INTO chunk_fts(chunk_fts,rank) VALUES('integrity-check',1)`へ変更。agg側は親を特定できないため、全rebuildまたは全親/sync/readyを明示的に再駆動する。 |
| S03 | §11.2後段の差替えSQLが`c.text IS NOT NULL`を落とすため、FTSに存在しないannotation無しimage chunkが短語検索だけで返る。 | 完全CTEを掲載し、`WHERE c.text IS NOT NULL AND (...)`へ一本化する。 |
| S11 | §8は`拒否にも課金するproviderではこの分岐にも記帳`とする一方、§9.1 sweepは全`submit_rejected`を無条件で照会・記帳対象外にする。ID、seq、Tx境界も未定義。 | provider capabilityとしてreject課金有無を固定し、client/server双方のledger ID・seq・原子性を定義する。除外は非課金確定時だけ。 |
| S12 | §9.1相1の旧upload削除条件は`同uploadの全行が終端`だが、通常のconfirmed-absent requeue時はstate=0。U1を削除できないままU2が単一`upload_id`列を上書きする。 | 同一requeue cohortの全行がU1を放棄すると確定した場合も削除可とするか、旧uploadを複数保持できる残骸表を追加する。 |
| S13 | §7は`app_configへ operation record`、§9.1は7種の許可keyのみ。operation key、値schema、存在条件がない。 | `bulk_operation`等を8番目の許可keyとして定義し、JCS schema・変換中のみ存在・完了時削除を規定する。 |
| S14 | §4.1はtool/embedding共通の`{"v","model","annotation_schema","options"}`。§5.7の`必須フィールドが互いに排他`をschemaが実現していない。同一hashでは先着kindが後着を`INSERT OR IGNORE`で消す。 | recordに必須`kind`を含めるか、`tool\0`/`embedding\0`でhashをdomain separationする。 |
| S15 | §21.4はraw不在時に保全をskipする一方、rename前に`保全時の tuple`との比較を要求する。開始後に同名fileが作られた場合の比較基準がない。 | `expected_absent` sentinelを保存し、rename直前にも不在であることを必須確認する。 |
| S16 | §5.6は`embeddingsが正、embedding_vecは導出物`だが、§13はtarget_key差集合しか検査しない。同一key・同長のvector値破損は永久にKNN誤順位を出す。 | fsckでembeddings.vectorとvec payloadを比較するか、週次にvecを正本から全再構築する。local/agg双方に適用。 |
| S17 | §5.3の`MD行の存在=done`に対し、localのMD↔chunks内容/件数検査がない。chunkをtrigger付きで削除するとFTS検査も通り、OCRはdone短絡する。 | 保存Markdownを再解析したcanonical chunk集合と照合し、不一致ならlocal全置換+generated_at更新、agg ready/syncを再駆動する。 |
| S18 | §21.3はSHA-256 digestで`改竄`を検出すると主張するが、journalとdigestを同時に書ける主体はdigestも再計算できる。`was_tracked=false→true`で生存側repoを退役できる。 | digestは偶発破損検出と明記する。改竄防止が要件なら外部信頼根を持つMAC/署名、または回復時のapp状態照合とユーザー確認を要求する。 |
| S19 | profile_recordにprovider/adapter namespaceが必須でない。同名`embed-v1`、同次元・同metricの別providerへ切替えるとhashが不変で、旧indexへ新query vectorを当てる。 | provider/adapter ID、前処理version、API互換versionをJCS recordの必須入力にする。 |

### Minor

| ID | 根拠・再現 | 修正案 |
|---|---|---|
| S21 | §20.4は`statusを missing → retiredへ更新`するが、§9.3-dはfolders等を削除し、retired状態を保持する表・行がない。再起動後は未登録と区別不能。 | retired tombstoneを保持するか、statusは一回限りのイベントであると明記する。 |
| S22 | rebind時は`新 root_path配下のfp_cacheを無効化`するだけ。旧pathがwatch域外なら旧cacheは誰にもmark-and-sweepされない。 | rebind Txで旧・新root_path双方のfp_cacheを削除する。 |
| S23 | §9.1は`Retry-Afterが返る場合`だけ抑止時刻を保存する。header無し429ではdirty早回しtickがhot retryを繰り返せる。 | Retry-After無し用のprovider別fallback backoffを定義する。 |

---

## 第4部 — 確認済み・問題なし

### C1〜C12

| 観点 | 結果 |
|---|---|
| C1 原則反映 | 問題あり。主に P2/P3/P5/P8/P9/P12/P13/P16 に上記finding。 |
| C2 DDL静的検証 | **確認済み・問題なし**。基本構文、FK列数、rowid、WITHOUT ROWID、trigger対、CHECKを確認。S02はDDLではなくspecial commandの意味論。 |
| C3 相互参照 | 問題あり。§21.3破損解決→§21.1 step2のID意味が不整合。 |
| C4 クエリ整合 | 問題あり。LIKE差替え、FTS integrity command。 |
| C5 数値・事実 | **確認済み・問題なし**。$2.5/1k、+25%、50%、RRF 60、768参考値、8テーブルが一致。 |
| C6 用語・形式 | **確認済み・問題なし**。target_key、lower hex、chunk/target type、obj scheme、embed_hashは整合。 |
| C7 状態機械 | 問題あり。S01、S05〜S12、S20。 |
| C8 欠落 | 問題あり。operation key、provider/profile namespace、各fsck検査。 |
| C9 回帰 | partially-fixed 5件。not-fixed/regressionは0件。 |
| C10 修正が開けた穴 | 問題あり。特にS04、S06〜S12。 |
| C11 実装可能性 | 問題あり。追加判断なしに実装不能な分岐が複数。 |
| C12 探索 | 72シナリオ実行。fatal 8、major 12、minor 3。 |

### P1〜P16

- **確認済み・問題なし**: P1、P4、P6、P7、P11、P14、P15
- 問題あり:

  - P2/P3: profile kind衝突、provider namespace
  - P5: operation recordの格納契約
  - P8/P9/P10: Batch回復、attempts、ledger、upload、reject課金
  - P12: LIKE fallback
  - P13: FTS/fsck、vec payload、local派生整合
  - P16: fork破損解決、restore absent競合、rebind cache

X60 のdecoder拡張については、canonical/非canonical、object実在/不在、G・`\G`・`\\G`、再materializeを総当たりし、**問題なし**でした。R01/R02/R04 の転記対も問題ありません。