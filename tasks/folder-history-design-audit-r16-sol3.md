# 判定: 不合格

前提条件は満たした。探索ログは **71 シナリオ**、X1〜X61 は全観点を実行済み。

不合格理由:

- C9: `R08` が regression、`R18`・`R20` が partially-fixed
- 新規検出: fatal 2 件、major 8 件
- 特に、遅い upload 後の intent 回復で未追跡 job が無制限に増え得る

## 第1部 — 回帰確認 C9

403 項目の内訳は fixed 304、superseded 96、非合格 3。

### fixed

```text
A02–A10, A12–A24
B01–B18
D01–D04, D06–D07, D09–D14
E01–E06
F01–F04, F06, F08–F09, F11, F13–F20, F22–F27
G01–G02
H01, H03, H05–H14, H16–H17, H19–H21, H23–H30
I01–I02, I07–I08, I10, I13, I18–I34, I36–I38
J01–J02, J05, J08–J09, J11–J12, J14–J15, J17–J20
K01, K03–K05, K07, K10, K15, K17–K18, K20, K22–K23, K25–K26
L01–L03, L05–L06, L08, L10–L19, L22–L25, L27
M02, M04, M07, M11, M15–M28
N01–N02, N05–N06, N08–N12, N14, N16–N27, N29–N33,
N35, N37–N38, N41–N45
O01, O06, O08, O10, O12, O14–O16, O20–O27, O29
Q01, Q07–Q08, Q11, Q15–Q37
R01–R07, R09–R17, R19, R21–R29
```

### superseded

項目全体または当該項目中の旧要件が、次の高優先項目へ置換されている。

```text
A01→K25
A11→I05/I06/I13/I14
D05→E04
D08→K20

F05→I14
F07→I15/K01
F10→H08
F12→I16/I17
F21→I03/I04

H02(衝突順)→I32
H04→I31
H15→I08/I11
H18→I16
H22→I15

I03/I04→J06/K02
I05/I06→J01/J02
I09/I11→J03/K10
I12→K04
I14→L03
I15→J04/K01
I16/I17→J05/J01
I35→J13–J16

J03→K10
J04→K01
J06→K02
J07→L09
J10→K09
J13→K16
J16→K13–K15

K02→L01
K06→L02
K08→N17
K09/K11→L03
K12/K13→L04
K14→L07
K16→L01/O14
K19→L13
K21→L20
K24→L09

L04/L21→M02
L07→N16
L09→M03
L20→M04
L26→N14
L28→M03/M09

M01→N09
M03→N16/R28
M05→N16
M06→N17
M08→N28/O13/R04
M09→N05/N06
M10→N10
M12→N38
M13→N30
M14→R22
M29→N15

N03→O05/O06/Q03/R05
N04→O02/O03/Q05/Q07/R06
N07→O12
N13→O21
N15→O04/O25
N28→O13/Q12/R04
N34→R11
N36→O16
N39→O14
N40→O28/Q01

O02/O03→Q05/Q07/R06
O04→Q06/R07
O05→Q04/R02
O07→Q09/R03
O09→Q11/Q12
O11→Q13/Q36
O13→Q12/R04
O17→Q02/R01
O18→Q23
O19→Q24
O28→Q01
O30→Q37

Q02→R01
Q03→R05
Q04→R02
Q05/Q06→R06/R07
Q09→R03
Q10→R14
Q12→R04
Q13/Q14→R15/R16
```

### 非合格項目

| ID | 判定 | 根拠 |
|---|---|---|
| R08 | regression | §21.2 に「client … は terminal 記帳後に削除」が残る。§9.1 の正しい規範は「state=3 + completed_at → 4.5 掃除・token NULL → 3条件で削除」であり、r15 修正前の即削除読みを再導入している。 |
| R18 | partially-fixed | §13 は external-content 照合を要求しながら、掲載 SQL は `INSERT INTO chunk_fts(chunk_fts) VALUES('integrity-check')`。FTS5 で外部 content と比較するには `rank=1` が必要である。[SQLite FTS5 公式仕様](https://www.sqlite.org/fts5.html#the_integrity_check_command)。 |
| R20 | partially-fixed | §11.2 の主説明には `c.text IS NOT NULL` があるが、後段の「掲載 SQL をこの形で差し替える」例は `WHERE c.text LIKE … OR c.heading_path LIKE …` のままで条件が脱落している。 |

## 第2部 — 探索ログ C12

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | `A=h1` が現在版 → tick 前に `h2` へ編集後削除 → 完全 walk 2回 | 問題なし。中間 `h2` は未観測、pending 後に delete commit。 |
| 2 | X2 | 本文に裸の grammar 行、`\G`、不正 hash、実在しない object → materialize → parse | 問題なし。escape/un-escape と厳密認識・実在検証が分離される。 |
| 3 | X3 | Windows の同一 NTFS volume 内で対象ディレクトリだけ case-sensitive → `A.txt` と `a.txt` | **S10** |
| 4 | X4 | 時計を24時間後退 → 更新 commit →再更新 | 問題なし。`latest+1` と commit_hash tie-break で前進。 |
| 5 | X5 | 10万ファイル・100万 chunk → 全量再チャンク・replicate | 正しさの破綻なし。負荷の再検討境界は§19にある。 |
| 6 | X6 | 相1 → 512MB upload が12分 → job作成成功・応答喪失 → 30秒の一覧遅延 | **S01** |
| 7 | X7 | 旧アプリが grammar v1 を作成 → decoder変更後の新アプリで再チャンク | **S08** |
| 8 | X8 | 改竄 DB の `file_name='../outside'` → restore | 問題なし。file_name 検証と dirfd 規律で拒否。 |
| 9 | X9 | objects保存後／metadata Tx後／app close前の各点でディスク満杯 | 問題なし。未参照 object、成果あり state=1 の再 close に収束。 |
| 10 | X10 | `.folder-history` 手動削除、metadata.sqlite 手動改変 | 問題なし。damaged または fsck 検出に倒れる。 |
| 11 | X11 | chunk 行は存在するが FTS posting だけ欠損 → 週次 fsck | **S04** |
| 12 | X12 | watch_root→commit→OCR→chunk→embed→replicate→search→restore | 問題なし。通常経路の受け渡しは追跡可能。 |
| 13 | X13 | 一括変換開始 → operation record を app_config に書く | **S03** |
| 14 | X14 | submit/collect が429、Retry-Afterあり → 次tick | 問題なし。`retry_not_before` が tick 間を跨ぐ。 |
| 15 | X15 | 主張「FTS posting破損はfsckが検出」→ posting欠損でplain integrity-check | **破れた: S04** |
| 16 | X16 | 1 repoのJSONLを複数jobに分割 → job単位token → 相3前クラッシュ | 問題なし。各tokenを独立にfound採用できる。 |
| 17 | X17 | register途中クラッシュ → 再実行 → fork → restore | 問題なし。通常のphase遷移では収束。 |
| 18 | X18 | 同一 profile_record bytes を tool/embedding の両方として投入 | **S09** |
| 19 | X19 | rename後、metadata COMMIT後、相2b後の各電断 | 問題なし。ただし遅いuploadとの組合せはS01。 |
| 20 | X20 | 主張「未追跡jobは最大1」→ token作成後12分かけてupload | **破れた: S01** |
| 21 | X21 | floor設定中に再チャンク → app floor更新後にクラッシュ | 問題なし。再OCR側へ倒れ、silent cancelしない。 |
| 22 | X22 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE各点で通常クラッシュ | 問題なし。journalが正常なら再開位置は一意。 |
| 23 | X23 | app_config、cost_ledger、pending_deletesを全読者へ接続 | operation recordだけ契約外。**S03** |
| 24 | X24 | 主張「vec差集合は任意の中断から収束」→ CREATE直後・半充填で停止 | **破れず**。次tickの差集合が埋める。 |
| 25 | X25 | フォルダ未接続でapp.sqliteだけ横断検索 → query embed失敗 | 問題なし。FTS-only + status。 |
| 26 | X26 | profile A投入→B変更→A復帰、submission_seqとsnapshotを追跡 | 問題なし。seq非リセットとsnapshot不変が効く。 |
| 27 | X27 | flag `{old=A,new=B}` + 破損journal → 明示解決 | **S02** |
| 28 | X28 | detached state=0 client、token/upload残存 → §21.2を局所実装 | **S05** |
| 29 | X29 | case-sensitive directoryの2系列をvolume属性で判定 | **S10** |
| 30 | X30 | 主張「forkは全クラッシュ境界から回復」→破損journal明示解決 | **破れた: S02** |
| 31 | X31 | row削除→旧ledgerあり→再登録→新規row | 問題なし。MAX(submission_seq)継承で衝突しない。 |
| 32 | X32 | phase×app全損を全数追跡 | 正常journalは問題なし。破損journal+flagで **S02**。 |
| 33 | X33 | server/client×成功/timeout/missing/profile_changed等を記帳 | 記載された非課金前提下では0/1行へ収束。 |
| 34 | X34 | `text=NULL` の画像chunk、heading=`会計`、2文字LIKE fallback | **S06** |
| 35 | X35 | 主張「detachedは課金・cleanupを落とさない」→§21.2 recapだけで実装 | **破れた: S05** |
| 36 | X36 | profile A→B→Aで同一seqを再観測 | 問題なし。ON CONFLICT DO NOTHINGがcloseを妨げない。 |
| 37 | X37 | A/B同期済み、C damaged中にready=P2 → C復旧 | 問題なし。部分性は明示された通常状態。 |
| 38 | X38 | fork中にフォルダ移動 → journal走査で発見 | 正常journalは問題なし。破損解決では **S02**。 |
| 39 | X39 | register時にmetadataが一時EIO | 問題なし。damagedにせず保留。 |
| 40 | X40 | 主張「ready/距離/query hashで誤KNNを防ぐ」→profile切替を各境界で実行 | **破れず**。read Txとready gateが機能。 |
| 41 | X41 | 全終端理由×collect/reconcile/detached/client再実行前を走査 | stated provider前提では記帳0/1行。 |
| 42 | X42 | 接続0→A復帰→C damaged復帰、synced/readyを追跡 | 問題なし。readyの意味が「設定時点被覆」に限定済み。 |
| 43 | X43 | NFD/NFC/両方/raw無し×case-sensitive/insensitive | 問題なし。resolverの採用規則で一意。 |
| 44 | X44 | registered read一時EIO、standalone read、z unreadable | 問題なし。4分類とstep -1保留が一致。 |
| 45 | X45 | 主張「unknownで二重jobなし」「raw resolverで二重実体なし」 | **破れず**。unknown保持・raw再解決が効く。 |
| 46 | X46 | token記帳→rotation→実job id記帳→sweep再訪 | 問題なし。述語キーと自己記述化で別attemptを区別。 |
| 47 | X47 | 期限超(i)〜(iv)の各DB書込点でクラッシュ | 問題なし。1 Txなら部分確定しない。 |
| 48 | X48 | working未取り込み変更あり → in-place restore | 問題なし。保全commit後に置換。 |
| 49 | X49 | 全§21操作の前に破損journal回復ゲート | 明示解決へ入ってもID接続が欠ける。**S02** |
| 50 | X50 | 主張「G/\\G/\\\\Gは可逆」→同版内と旧v1 upgradeを比較 | 同版内は破れず、upgradeで **S08**。 |
| 51 | X51 | 期限超seq+1→相3+1→found+1→row再作成MAX継承 | 問題なし。連番の衝突なし。 |
| 52 | X52 | expired terminal→sweep→明示retry | 問題なし。旧token記帳と新tokenが分離。 |
| 53 | X53 | 4照合点すべてで「token作成から12分後にjob作成」を適用 | 全点で同じ誤った時間起点。**S01** |
| 54 | X54 | journal有効/破損/無×flag有無×id old/new/第三 | 第三IDが明示解決自身から生じ得る。**S02** |
| 55 | X55 | embedding混在+tool同時刻tie+一括変換後 | 問題なし。KNN停止、FTSは決定論的toolを選択。 |
| 56 | X56 | `\![diagram](obj:see appendix)` を現行encoder/decoderで往復 | 現行同版では問題なし。 |
| 57 | X57 | found記帳でterminal行にbatch_job_idを書込→再投入 | 問題なし。相1がNULL化し、state=0 dispatchを誤らない。 |
| 58 | X58 | detached terminal→4.5→再登録 | §9.1本体は収束するが§21.2再掲が矛盾。**S05** |
| 59 | X59 | clientの課金される4xx拒否 → 明示された追加記帳を同Txで実施 | 問題なし。ただしprovider別分岐の実装が前提。 |
| 60 | X60 | escape/unescape/recognition全組合せ、旧v1も投入 | 現行全組合せは可逆。旧v1との混在で **S08**。 |
| 61 | X61 | 主張「(i)〜(iv)原子」「自己記述化」「detached非deadlock」「job 1個上限」 | 前3件は破れず。job上限は **S01**、再掲は **S05**。 |
| 62 | 自由 | app_config許可keyを列挙→一括変換開始 | **S03** |
| 63 | 自由 | in-memory FTS5でcontentのみ追加→plain/rank=1を比較 | plainは成功、rank=1は`SQLITE_CORRUPT_VTAB`。**S04** |
| 64 | 自由 | 過去版objectをbit-rot→backfill OCR→後で正しいobjectを復元 | **S07** |
| 65 | 自由 | 2文字headingのみを持つtext=NULL画像chunk | **S06** |
| 66 | 自由 | tool/embedding共通JCS recordを構成 | **S09** |
| 67 | 自由 | NTFS directory case flagをvolume既定と逆に設定 | **S10** |
| 68 | R01再掲対 | §9.3-zと§10 step -1を鏡写し照合 | 問題なし。 |
| 69 | R02再掲対 | 期限超DB書込と外部cleanup境界を追跡 | 問題なし。 |
| 70 | R03再掲対 | §9.3-dとfork step3の削除3条件 | 問題なし。 |
| 71 | R04再掲対 | §20.5と§21.4のrename直前lstat | 問題なし。 |

## 第3部 — 新規検出

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| S01 | **fatal** | §9.1「intent_token の時刻成分 = 相1実行時刻」「0 ≤ now − token時刻 ≤ 伝播猶予」 | 伝播猶予を job 作成時刻ではなく、upload前の相1時刻から測っている。したがって provider の一覧遅延が猶予以内でも、uploadが猶予より長ければ保護されない。 | `state=0, seq=0, attempts=0` → t=0 token T → uploadに12分 → job J作成成功、応答喪失 → 30秒だけ一覧に未反映 → token年齢は12分超なのでunknown扱いされず新tokenへrotation → J2作成。Jは未追跡・未記帳。within-expiry rotationはattempts/seqを消費せず反復可能。 | P6/P9、C7/C10/C11/C12、X6/X20/X53/X61 | 相2b直前に `job_create_started_at` をapp Txで永続化し、伝播猶予はその時刻から測る。全4照合点を同じ列へ統一する。 |
| S02 | **fatal** | §21.3「journal除去（flagは残す）→ §21.1手順2」／§21.1「repository-id (UUIDv7) を生成」 | flagの`new_id`と、再初期化で生成するIDの引渡しがない。明示解決自身が「第三のid」を作り、fork flagを永久に掃除不能にする。 | flag `{old=A,new=B}`、journal破損 → journal削除 → §21.1手順2がCを生成 → 実体id=C、flagはBのまま → 毎tickはCをold/new以外としてdamaged保留。再実行してもD、E…を生成する。 | P16、C7/C10/C11/C12、X27/X30/X32/X38/X49/X54 | flagがある解決では§21.1手順2へ`forced_repository_id=B`を渡す。別IDを選ぶなら、書込み前にflag.new_idを同一耐久手順で更新する。 |
| S03 | **major** | §7「app_configへ operation record」／§9.1「許可 key 集合」7種 | operation record用keyが許可集合にない。両規範を同時に実装できない。 | 一括フィルタ変換開始 → allowed-keyを守るとrecordを書けない → 中断後、部分変換をstatusで検出不能。任意keyを発明すると別実装が契約外として拒否する。 | P5/P9、C8/C10/C11/C12、X13/X23/自由62 | 8番目の固定key（例 `bulk_transform_in_progress`）とvalue schema、存在条件、上書き・排他規則を定義する。 |
| S04 | **major** | §13 `INSERT INTO chunk_fts(chunk_fts) VALUES('integrity-check')` | plain形式はFTS内部整合しか検査せず、external contentとの比較を行わない。文書が狙うposting単独欠損を検出できない。SQLite公式も外部content比較には`rank=1`を要求する。[公式仕様](https://www.sqlite.org/fts5.html#the_integrity_check_command) | chunksに`hello`行、FTS postingなし → plain checkは成功 → fsckはrebuildしない → `MATCH 'hello'`が恒久0件。実際のin-memory再現でもplain成功、rank=1が破損を検出した。 | P7/P13、C2/C4/C9/C12、X11/X15/自由63 | local/aggとも `INSERT INTO <fts>(<fts>, rank) VALUES('integrity-check', 1)` に修正する。 |
| S05 | **major** | §21.2「client … は terminal 記帳後に削除」 | §9.1の段階遷移と矛盾する。即削除ならtoken/uploadの再駆動キーを失い、3条件を守るとstate=0のままでsweepの全行終端条件に入らない。 | detached state=0 client、`batch_job_id=T,intent_token=T,upload_id=U` → §21.2局所実装で記帳後delete → U清掃不能。削除ガードを優先するとstate=0が残りtoken NULL化不能。 | P9、C7/C9/C10/C11/C12、X28/X35/X58 | §21.2を§9.1と同文にし、`state=3,error='detached',completed_at`を同Txで確定 → 4.5 → 3条件削除と明記する。 |
| S06 | **major** | §11.2 後段「`WHERE c.text LIKE … OR c.heading_path LIKE …`」 | 正しい説明で必須とした`c.text IS NOT NULL`が実装用差替え例から脱落。短語だけannotationなし画像を返し、FTS対象集合と不一致になる。 | eligibleな画像chunk `text=NULL, heading_path='["会計"]'` → 2文字query「会計」→後段例ではヒット、3文字以上のFTSでは対象外。 | P12、C4/C9/C10/C12、X34/自由65 | 差替えSQLを `WHERE c.text IS NOT NULL AND (c.text LIKE … OR c.heading_path LIKE …)` に統一する。 |
| S07 | **major** | §10 OCR/Embed submitはobjectを消費／§13はobject修復のみ | OCR・embedding投入直前のobject hash再照合がない。またfsckがobjectを修復しても、その破損bytesから既に生成されたmd/vectorを無効化しない。誤った派生が正しいcontent_hash配下に恒久固定される。 | 過去版object Hがbit-rotしてB' → backfill OCRがB'を送信 → `markdown_documents(content_hash=H)`にM'保存 → 後でbackupから正しいHを復元 → 行存在で再OCRされず、M'が検索正本として残る。 | P2/P8/P13、C7/C10/C11/C12、X9/自由64 | provider投入直前にbytesをhash照合する。fsckでobjectを置換した場合、当該contentの派生または当該image embeddingを無効化して再生成対象にする。 |
| S08 | **major** | §6「v:1」／§6新encoder／§7新しい緩いdecoder／§14 migration | escape/decoderの意味を変更したのにgrammar versionを上げていない。旧v1と新v1を区別できない。 | 旧v1 encoderが元本文 `\![diagram](obj:see appendix)` を未変更で保存 → 新アプリもv1として読む → 新decoderが先頭`\`を除去 → text_hash/FTS本文が原文と異なる。 | P5/P6/P14、C7/C10/C11/C12、X7/X50/X60 | 新しい対称escapeをgrammar v2にする。v1は旧decoder、v2は新decoderで読む。既存v1を無損失で変換できない場合は再OCRを明示する。 |
| S09 | **major** | §4.1 共通profile_record形／§5.7「必須フィールドが互いに排他」 | 排他的だと主張するが、tool/embedding別の必須・禁止フィールドが定義されていない。共通record bytesが両kindで有効になり得る。 | 同じmodel/annotation_schema/options recordを両kindに使用 → toolが`profiles(P,1)`をINSERT → embedding側`INSERT OR IGNORE(P,2)`は消える → embeddings参照はkind不一致 → fsckが恒久不一致。 | P2/P3、C2/C11/C12、X18/自由66 | profile hash入力へ`"kind":"tool"`/`"kind":"embedding"`を含めるか、排他的schemaを完全に列挙し書込境界で検証する。 |
| S10 | **major** | §20.5「case感度は走査時のボリューム属性で判定」 | Windows/NTFSではcase感度をディレクトリ単位で設定できるため、volume属性だけでは実際の名前同一性を判定できない。[Microsoft公式](https://learn.microsoft.com/en-us/windows/wsl/case-sensitivity) | volume既定はinsensitive、対象directoryだけsensitive → `A.txt`と`a.txt`が別実体として存在 → scannerはfoldして片方をcollision敗者にし、1系列しか履歴化しない。 | P16、C11/C12、X3/X29/自由67 | Windowsでは対象管理ディレクトリのper-directory case-sensitive flagを照会し、実効的なlookup semanticsを使用する。 |

補足: Mistralの公開APIはjob一覧とmetadata filterを定義する一方、少なくとも公開契約上は一覧可視化遅延の上限を示していない。[Mistral Batch API](https://docs.mistral.ai/api/endpoint/batch)。ただしS01は、それ以前に「遅延が30秒で10分以内」でも再現するため、provider保証だけでは修復できない。

## 第4部 — 確認済みの列挙

### C1〜C12

| 観点 | 結果 |
|---|---|
| C1 原則反映 | S03、S05〜S10あり |
| C2 SQL静的検証 | S04、S09あり |
| C3 相互参照整合 | **確認済み・問題なし** |
| C4 クエリ/スキーマ整合 | S04、S06あり |
| C5 数値・事実一貫性 | **確認済み・問題なし**。$2.5、+25%、RRF 60、768参考値、8表は一致。 |
| C6 用語・形式一貫性 | **確認済み・問題なし**。target_key、小文字hex、type/hashペアは一致。 |
| C7 状態機械 | S01、S02、S05、S07、S08あり |
| C8 欠落 | S03あり |
| C9 修正検証 | R08 regression、R18/R20 partially-fixed |
| C10 修正が開けた穴 | S01〜S09あり |
| C11 実装可能性 | S01〜S10あり |
| C12 探索型監査 | 71件実行、S01〜S10を検出 |

### P1〜P16

| 原則 | 結果 |
|---|---|
| P1 | **確認済み・問題なし** |
| P2 | S07、S09 |
| P3 | S09 |
| P4 | **確認済み・問題なし** |
| P5 | S03、S08 |
| P6 | S01、S08 |
| P7 | **確認済み・問題なし** |
| P8 | S01、S07 |
| P9 | S03、S05 |
| P10 | **確認済み・問題なし** |
| P11 | **確認済み・問題なし** |
| P12 | S06 |
| P13 | S04、S07 |
| P14 | S08 |
| P15 | **確認済み・問題なし** |
| P16 | S02、S10 |