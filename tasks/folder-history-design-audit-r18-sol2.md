不合格
target.md 全 3207 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第1部 — 回帰確認（C9）

全450項目の内訳: fixed 339件、superseded 105件、partially-fixed 6件。

fixed: 下記superseded 105件および詳細表の6件を除く全ID。

superseded:

- A01→K25、A11→I05/I06/I13/I14
- D08→K20
- F05→I14、F07→I15、F12→I16/I17、F21→I03/I04
- H02→I32、H04→I31、H15→I08/I11、H18→I16、H22→I15
- I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I12→K04、I15→J04、I16/I17→J05/J01、I35→J13〜J16
- J03→K10、J04→K01、J06→K02、J07→L09、J10→K09、J13→K16、J16→K13〜K15
- K02→L01、K06→L02、K08→N17、K09→L03、K11→terminal/reconcile close記帳規範、K12/K13→L04、K14→L07、K19→L13、K21→L20、K24→L09
- L04/L21→M02、L07→N16、L09→M03、L20→M04、L26→N14、L28→M03/M09
- M01→N09、M05→N16、M06→N17、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15
- N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28
- O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37
- Q02→R01、Q03→R05、Q04→R02、Q05/Q06→R06、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16
- R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06
- S06→T09、S07→T05/T06、S11→T07、S19→T03、S20→T01、S23→T18、S24→T02、S25→T04

| ID | 判定 | 根拠（規範側／残存側） |
|---|---|---|
| I31 | partially-fixed | §20.4は「skipped は読み取りの一時失敗に限る」とする一方、§20.5は「Word / PDF 等として構文的に開けるか…壊れた中間状態はスキップ」とし、安定した破損・暗号化・非対応文書を終端化する規則がない。 |
| T03 | partially-fixed | §9.1は課金される拒否について「submission_seq を +1へ行UPDATEし、その新値で…記帳」と正しい。一方、§8(ii)は「この分岐にも記帳を足す」としか書かず、seq更新を欠く。 |
| T08 | partially-fixed | §9.1相1は旧tokenの「照合・記帳・残骸掃除・NULL化」を完了してからrotationする規範。一方、同じ相1の旧token残骸処理は「削除は失敗しても続行する」とし、未完了のまま新tokenで上書きできる。 |
| T10 | partially-fixed | §6はOffice原本をuploadせず、「実際にuploadしたbytes（変換物）」へupload_id/tokenを対応させる。一方、§9.1相2aは「原本 upload」「機密原本」、§6のJSONL説明も「upload済み原本」と再掲する。 |
| T11 | partially-fixed | §21.3 journal recordにはstarted_atが入り「app.sqlite全損後もjournal単体でstalled判定可能」とするが、滞留判定は依然として「fork_in_progress の started_at」だけを参照する。 |
| T16 | partially-fixed | §11.2規範は「fts_hitsおよびKNNのkに内部上限 LIMIT :fts_cap」とするが、「実行可能な完全形」のfts_hitsとLIKE差替えSQLにはLIMITがない。§19も将来導入の`:k_fts`と記す。 |

## 第2部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | 正常PDF v1を履歴化 → 安定した破損PDF v2へ置換 → 構文検査で毎回skip → v2を削除 | U03を検出 |
| 2 | X2 | `# 会計課`を含む文書 → heading_pathをUTF-8直書き実装と`\u` escape実装で生成 → 同じ語を検索 | U14を検出 |
| 3 | X3 | watch_rootの子へ祖先を指すbind mount／junctionを作成 → 再帰walk | U21を検出 |
| 4 | X4 | 20GBファイルのmtimeを2099年へ設定 → periodic/dirty tickを反復 | U20を検出 |
| 5 | X5 | 100万FTS一致と大量DELETE後のfreelistを用意 → 検索、週次vacuum | U17、U26を検出 |
| 6 | X6 | 同じ整数1を`"1"`と`"01"`でJCS recordへ格納 → commit/profile hashを再計算 | U13を検出 |
| 7 | X7 | 新アプリがgrammar v2を保存 → 旧アプリがreparseを停止 → 週次GC | U02を検出 |
| 8 | X8 | Office原本を変換 → §9.1の「原本upload」を実装 → providerへ送信・掃除 | U09を検出 |
| 9 | X9 | `chunks.text=A, text_hash=h(A)` → textのみBへ破損 → embed → fsckでAへ修復 | U12、U19を検出 |
| 10 | X10 | 正常chunkのchar_endだけ有効範囲内で改変 → fsck → preview | U18を検出 |
| 11 | X11 | client前計上state=0で呼出中crash → T08 guardとterminal-only sweepを順に適用 | U06を検出 |
| 12 | X12 | watch登録 → 日本語見出し文書 → OCR/chunk/replicate/search → 別JSON encoderで再構築 | U14を検出 |
| 13 | X13 | terminal行に旧token残存 → provider資格情報を永久失効 → profile変更と明示retry | U07を検出 |
| 14 | X14 | 未来mtime・大量freelistを同時発生 → tick.lock下のscan/fsckを反復 | U20、U26を検出 |
| 15 | X15 | 主張: job重複有界、GC fail-closed、fsck整合検出、profile収束、pending delete保全。試行: scope変更、v2 grammar、論理chunk破損、profile中断、2回不在。破れたか: 前3件中job/GC/fsckが破れ、後2件は破れず | U01、U02、U18を検出 |
| 16 | X16 | 同一repositoryのJSONLを複数jobへ分割 → 各tokenを相1〜3、collectまで追跡 | 問題なし |
| 17 | X17 | active watch_root内の現在版をunregister → drop-derivation → 次walk | U04を検出 |
| 18 | X18 | profile孤児、partial walk、ledgerを組合せ → fsck、deep-scan、月次集計 | 問題なし |
| 19 | X19 | fork明示解決でflagなし → 破損journal削除直後に電源断 | U22を検出 |
| 20 | X20 | 主張: job最悪1件、月次配賦、profile収束、fork回復、delete保全、dir fsync保証。試行: credential scope変更、月跨ぎretry、各crash境界。破れたか: job有界とfork回復が破れ、他は破れず | U01、U23を検出 |
| 21 | X21 | profile Pのagg_vec値だけ同長別vectorへ改変 → 差集合再充填とready判定 | U19を検出 |
| 22 | X22 | fork各phaseでcrashし、flag欠損・old_id復元・app全損を組合せて再開 | U22、U23、U24を検出 |
| 23 | X23 | converter実体を削除 → DOCX batch rowをstate=0へ → submit | U10を検出 |
| 24 | X24 | 主張: vec差集合は欠落を修復、agg検査は中断収束、clientは安全に再実行。試行: same-key vector改変、state=0 crash。破れたか: vector内容とclient再実行が破れた | U06、U19を検出 |
| 25 | X25 | app.sqliteのみで横断検索 → profile埋込 → missing folder結果 → watch_root解除後のfolders起点walk | 問題なし |
| 26 | X26 | client pre-account済みstate=0 → crash → dispatch → phase1 guard → sweep選択 | U06を検出 |
| 27 | X27 | journal作成、各phase更新、破損明示解決、APP_DONEでold_id復元を各境界で実行 | U22、U23を検出 |
| 28 | X28 | unregister由来detachedをstate 0/1/2/3別にcollect・掃除・再登録 | 問題なし |
| 29 | X29 | case-insensitiveで初出表記固定 → sensitive volumeへ移動 → case違い実体を追加 | 問題なし |
| 30 | X30 | 主張: seq UNIQUE安全、client有界、fork全境界回復、case FK安全、30秒delete安全、detached記帳。試行: paid reject反復、late-phase old_id、通常境界。破れたか: seq記帳とforkが破れた | U05、U23を検出 |
| 31 | X31 | server paid submit_rejected → 明示retry → 再度paid reject → generic §8記帳を適用 | U05を検出 |
| 32 | X32 | ID_WRITTEN/APP_DONE journalへold_id実体を組合せ → 表どおり再開 | U23を検出 |
| 33 | X33 | server/client × 全終端理由 × collect/reconcile/detachedの課金行列を追跡 | U01、U05を検出 |
| 34 | X34 | 掲載SQLを100万一致データへ適用 → `:fts_cap`をbind → outer limitまで実行 | U17を検出 |
| 35 | X35 | 主張: seq継承、reconcile記帳、reject非再投入、old_id fork回復、detached記帳、最終stat安全。試行: paid reject2回、late-phase old_id、通常close。破れたか: seqとforkが破れ、他は破れず | U05、U23を検出 |
| 36 | X36 | paid rejectionを通常closeと同じseqで記帳 → explicit retry → ON CONFLICT | U05を検出 |
| 37 | X37 | ready=P、同一keyのagg_vecだけ改変 → Replicate/fsck/検索 | U19を検出 |
| 38 | X38 | app.sqlite全損後、journalのみ残して恒久I/O障害 → 30日経過 | U24を検出 |
| 39 | X39 | 一時読取不能register、同root別id退役、detached再登録、対象外型deleteを連続実行 | 問題なし |
| 40 | X40 | 主張: close非abort、readyは破損を通さない、fork移動安全、一時失敗保全、距離変更再構築。試行: same-key vector改変ほか。破れたか: ready/破損検出のみ破れ、他は破れず | U19を検出 |
| 41 | X41 | 全終端理由のledger行列にpaid rejectとcredential scope変更を追加 | U01、U05を検出 |
| 42 | X42 | damaged/missing/fork folderを母数から出し入れ → synced NULL化 → ready再設定 | 問題なし |
| 43 | X43 | NFD/NFC/case collisionのraw resolverをdelete/restore/fsckの3点で照合 | 問題なし |
| 44 | X44 | registered path一時EIO、conflict standalone検索、step -1 regressed処理を同tickで追跡 | 問題なし |
| 45 | X45 | 主張: client課金不漏、unknownで二重jobなし、残骸記帳、ready安全、raw restore安全、登録照合安全。試行: account scope切替と永久unknown。破れたか: job有界性と再投入可能性が破れた | U01、U07を検出 |
| 46 | X46 | token記帳→job-id記帳→rotation→collectを連続し、述語とseqを全境界で照合 | 問題なし |
| 47 | X47 | 期限超記帳後、旧token残骸削除が失敗 → 「続行」で新tokenへrotation | U08を検出 |
| 48 | X48 | 未履歴working変更を保全commit → restore → 次tickでupdate、raw collisionも併試 | 問題なし |
| 49 | X49 | 破損journal・flagなしでregister前明示解決 → journal削除直後crash | U22を検出 |
| 50 | X50 | 主張: 無id記帳、推定非増殖、sweep回収、detached記帳、未来token、escape往復、restore保全、明示操作安全。試行: flagなし破損journalを解決。破れたか: 明示操作安全のみ破れた | U22を検出 |
| 51 | X51 | paid reject分岐でseq更新を省略 → retry・次closeと連番を比較 | U05を検出 |
| 52 | X52 | expired terminal → sweep unknown → explicit retry/profile変更 | U07、U08を検出 |
| 53 | X53 | 4照合点でprovider accountをAからBへ変更 → Bの全ページ空応答 | U01を検出 |
| 54 | X54 | journal有効/破損/無 × flag有/無 × id old/new/他を総当り | U22、U23、U24を検出 |
| 55 | X55 | embedding profile混在・tool同時刻tie・空markdown・backfill OFFで単独検索 | 問題なし |
| 56 | X56 | 非canonical `obj:`行をencoder/decoderに通し、旧指摘の再発を確認 | 問題なし |
| 57 | X57 | sweep foundでbatch_job_idを自己記述化 → 再訪・再投入・job_missing | 問題なし |
| 58 | X58 | detached terminal → token掃除 → 再登録 → explicit retry | 問題なし |
| 59 | X59 | server paid submit_rejectedを2回発生させ、§8と§9.1の記帳を比較 | U05を検出 |
| 60 | X60 | G、`\G`、`\\G`、object不在、非canonical行をescape→parse→unescape | 問題なし |
| 61 | X61 | 主張: 1Txで偽expiredなし、自己記述化で二重記帳なし、detached非deadlock、reject token残留なし、escape可逆、tool決定的。試行: 永久unknownとpaid reject反復。破れたか: detached/retryとreject記帳が破れ、他は破れず | U05、U07を検出 |
| 62 | X62 | job_create_started_at記録後・呼出前crash、時計補正、requeueを反復 | 問題なし |
| 63 | X63 | cancel確定 → token掃除失敗 → 明示retry → 再cancel | U08を検出 |
| 64 | X64 | token推定行の後、別attemptのjobをfound → IN述語・自己記述化を追跡 | 問題なし |
| 65 | X65 | no-replace非対応FSでEINVAL/EEXISTを発生 → 再lstat fallback | 問題なし |
| 66 | X66 | 規範と§8/§9.1/§10/§11/§13/§19/§21の再掲を横断比較 | U05、U09、U15、U16、U17、U24、U25を検出 |
| 67 | X67 | client state=0旧token、永久unknown、account切替、残骸削除失敗を別々にrotation guardへ投入 | U01、U06、U07、U08を検出 |
| 68 | X68 | cancel上限 → retryリセット → 再unregister、旧token掃除失敗を反復 | U08を検出 |
| 69 | X69 | `fts_cap=128, k_max=4096`で最初のeligible KNNをrank 200に配置、100万FTS一致も投入 | U17を検出 |
| 70 | X70 | DOCX 400MB → converter欠損／600MB PDF生成／raw-upload解釈を各々実行 | U09、U10、U11を検出 |
| 71 | 自由 | 非ASCII headingと大整数を独立実装でcanonical化 → hash/FTS結果を比較 | U13、U14を検出 |
| 72 | 自由 | v2 grammar、chunk span破損、same-key vector破損、大量freelistを同一週次fsck→GCへ投入 | U02、U18、U19、U26を検出 |

## 第3部 — 新規検出

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| U01 | fatal | §9.1「一覧の正常応答は全ページ」、provider条件は可視化遅延・保持期間のみ | job一覧のaccount/project/tenant scopeがsnapshotされず、別scopeの正常な空一覧をconfirmed-absentにできる。 | account Aでjob J作成後、相3前crash → 資格情報をaccount Bへ切替 → Bの全ページ空応答 → 未作成扱いでJ2投入 → JとJ2が課金され、Jは未記帳。 | P9/C7/C8/C10/C11/C12/X15/X20/X45/X53/X67 | batch rowへimmutableなprovider scope IDを保存し、同scopeだけを照合する。旧scopeへ到達不能ならunknownまたは明示的abandonに限定する。 |
| U02 | fatal | §6「未知のv…読み取り専用」、§13参照抽出「obj:<image_hash64>」、GC中止条件は欠損・読取失敗・hash不一致のみ | 未知grammarをreparseではfail-closeするが、GCではfail-closeしない。 | 新アプリがv2で画像参照encodingを変更 → 旧アプリはparse停止 → hash一致Markdownから旧`obj:`が0件 → GCが画像objectを削除 → 新アプリへ戻しても画像喪失。 | P5/P13/C8/C10/C11/C12/X7/X9 | GC前に全blockのversion/grammarを検証し、未知・混在・不正なら削除を中止するか、object参照形式を全version不変の契約にする。 |
| U03 | fatal | §20.4「skippedは読み取りの一時失敗に限る」対§20.5「構文的に開けるか…スキップ」 | 安定して読めるが壊れた・暗号化されたWord/PDFの保存遷移がなく、その版を永久に履歴化しない。 | v1 PDFをcommit → 安定した異常bytes v2へ置換 → 毎scanでsyntax skip → 後日v2を削除 → object/file_versionsがなく復元不能。 | P1/P16/C1/C7/C10/C11/C12/X1/X9 | 安定して読めたbytesは先に履歴化し、OCR suitabilityは後段preflightのterminal marker/statusとして扱う。 |
| U04 | fatal | §21.6「再課金を望まない場合は対象を先にunregister」対§21.2「active watch_root配下は次walkで再登録」 | 再課金回避手順が自動再登録規範により逆に再投入を発生させる。 | active root内でunregister → 現在版派生をdrop → 次walkがmarkerで再登録 → 成果なし差集合がOCRを再投入し課金。 | P9/P16/C3/C10/C11/C12/X17 | 対象を全active roots外へ移す、またはroot解除後にunregisterしてからdropする順序へ修正する。 |
| U05 | fatal | §8「拒否にも課金するprovider…記帳を足す」対§9.1「submission_seqを+1へ行UPDATEし、その新値で記帳」 | server側paid rejection実装が§8の省略形を採用すると、正当な別課金を同一seqの再観測として捨てる。 | seq=nでpaid rejectを記帳 → explicit retry → 相3前に再paid reject → seq=nのINSERTがUNIQUE衝突 → 実課金が台帳から欠落。 | P9/C7/C9-T03/C10/C11/C12/X31/X33/X59 | §8にも行UPDATE＋新seqによる記帳を明記し、server/client両分岐を同じ手順へ参照させる。 |
| U06 | major | §8「再実行は相1の規則一式」、§9.1相1「token sweep完了後」、sweepは「同token全行終端」 | clientの非終端state=0行はretry前にsweepを要求される一方、sweep対象になれず永久停止する。 | state=0、token=T、batch_job_id=T、attempts=1で呼出中crash → retry dispatch → T08 guard → 非終端のためsweep不可 → attemptsも進まない。 | P8/P9/C7/C10/C11/C12/X11/X24/X26/X67 | client旧lifecycleを記帳・終端・group-safe掃除・NULL化してから新lifecycleへ移る原子的遷移を定義する。 |
| U07 | major | §9.1「unknownなら掃除もNULL化もせず保持」＋T08 guard | 旧providerへの照会が永久unknownになった場合のabandon/statusがなく、profile変更や明示retryも永久に不能。 | terminal行にtoken T → 旧資格情報を失効 → lookupは永久unknown → profile変更・retry → rotation拒否が継続。 | P9/C7/C8/C11/C12/X13/X45/X52/X67 | `rotation_blocked`を永続表示し、ユーザー確認付きestimated記帳・残骸リスク記録・token放棄経路を定義する。 |
| U08 | major | §9.1相1「残骸掃除・NULL化を完了」対「削除は失敗しても続行する」 | 旧tokenによる残骸探索が失敗したまま新tokenで上書きされ、再駆動キーを失う。 | terminal Tの残骸削除がEIO → 処理続行 → 相1がT2を書込 → T名入りuploadが追跡不能のままTTLまで残留。 | P9/C7/C9-T08/C10/C11/C12/X47/X52/X63/X68 | cleanup成功または明示的な残余記録までrotationを禁止し、失敗時は旧tokenを保持してbackoffする。 |
| U09 | major | §6「原本はuploadしない」「実際にuploadしたbytes」対§9.1「原本upload」、§6「upload済み原本」 | Officeでraw原本と変換PDFのどちらをupload_id、filename token、JSONL file idへ結ぶかが章間で矛盾する。 | DOCXをPDFへ変換 → §9.1を実装した経路はraw DOCXをupload → provider拒否または原本を外部保存 → §6経路と異なる。 | P6/C6/C9-T10/C10/C11/C12/X8/X66/X70 | 全再掲を「uploaded input artifact」に統一し、Officeでは変換PDFのfile idだけを使用すると明記する。 |
| U10 | major | §6はconverter固定を要求するが、失敗分岐はunsupported/oversize/provider HTTPのみ | converter欠損、非zero終了、disk full、暗号化入力などupload前のローカル失敗に状態遷移がない。 | valid DOCXをstate=0へ → 固定版converterが消失 → HTTP結果なし → hot-loop、誤terminal、無backoffのいずれかを実装者が選ぶ必要。 | P6/C7/C8/C11/C12/X23/X70 | transient converter failureはstate=0＋永続backoff、決定的変換不能は`conversion_failed` terminal、版変更はprofile変更と定義する。 |
| U11 | major | §6「1ファイル512MB（provider上限）」、Officeは「実際にuploadしたbytes=変換物」だが説明は原本サイズ基準 | 変換後artifactに512MB上限を再適用する規則がない。 | 400MB DOCX → 600MB PDF → 原本検査はpass → upload時4xxとなり、本来のpreflight no-upload規範を破る。 | P6/C8/C11/C12/X70 | 原本取込上限と実upload artifact上限を分け、変換直後・upload前に後者を検査する。 |
| U12 | major | §6はOCR前hash再照合、§7はMarkdown再解析時の再hashなし、§8はstored hashでtext/imageをembed | 派生入力bytesとその識別hashが同一読取に束縛されず、修復後も誤vectorが残る。 | text A、hash h(A) → textだけBへ破損 → vector(B)をhで保存 → fsckでAへ戻す → current-profile embedding行があるため再embedせず、aggも同keyを更新しない。 | P5/P8/P11/C7/C8/C10/C11/C12/X9/X19 | 全派生でverified-readを共有し、同一bytesを処理へ渡す。修復時はlocal vec→embeddingとagg ready/rowもinvalidateする。 |
| U13 | major | §4.1「size_bytesは10進文字列」、大整数profile optionも同規則 | 10進文字列のcanonical lexical formが定義されていない。 | 実装Aが`"1"`、実装Bが`"01"`を生成 → JCSは別文字列として保持 → 同じcommit/profileのhashが分裂しfsckが偽破損を報告。 | P2/C6/C8/C11/C12/X6 | ASCII unsignedの`0`または`[1-9][0-9]*`に固定し、符号・先頭zeroを禁止する。 |
| U14 | major | §5.4「heading_path…JSON配列」、§5.5はそのraw TEXTをFTS索引 | JSONのescape・空白・UTF-8表現がcanonical化されていない。 | `会計課`をliteral UTF-8と`\u4f1a...`で保存 → 両方valid JSON → 後者は日本語trigramに一致せず、同一Markdownで検索結果が分岐。 | P2/P5/P12/C6/C8/C11/C12/X2/X12 | heading_pathをJCS UTF-8等の一形式に固定し、optional whitespace/ASCII escapeを禁止する。 |
| U15 | major | §10 OCR collectは「foldersに現存するrepositoryの行に限る」、Embed step 4は「detached処理→各item」 | Embedの鏡写し要約だけattached限定が欠落する。 | detached state=1のprepassが一時失敗 → 続く「各item」へ入る実装 → 存在しないfolder metadataへ書込み、tick全体がabort。 | P10/C1/C7/C10/C11/C12/X66 | step 4にも通常item処理はfolders現存行のみと明記し、detached prepass失敗時はそのitemを除外する。 |
| U16 | minor | §8-e「agg_embeddingsは行DELETE、agg_vecのみDROP→CREATE」対§10 step 5「agg_embeddings / agg_vecを破棄→再作成」 | 通常表agg_embeddingsまでschema dropするよう読める非伝播。 | step 5だけを実装 → 両表DROP → 通常表のFK/index/schema再生成判断が必要となり、途中crashで表欠損。 | P8/C6/C10/C11/C12/X66 | step 5を「agg_embeddings全行DELETE、agg_vecのみDROP→CREATE」と逐語的に統一する。 |
| U17 | major | §11.2「完全形」のfts_hitsにLIMITなし、規範は`:fts_cap`、§19は`:k_fts`、KNNは別に`k_max=4096` | capの掲載SQLへの欠落に加え、同level LIMITではwindowが全件rankし得る。KNNの`:fts_cap`と`k_max`の優先順位も未定義。 | 100万FTS一致、fts_cap=100 → 掲載SQLが全件rank。KNNはfts_cap=128、k_max=4096、最初のeligible=rank200 → 実装により0件または1件。 | P12/C4/C5/C6/C9-T16/C10/C11/C12/X5/X34/X69 | 決定的にORDER BY＋LIMITするcandidate CTEをwindow前に置き、KNNのeffective capを一つに定義する。 |
| U18 | major | §13 chunk fsckは「件数＋各textチャンクのSHA-256(text)=text_hash」 | deterministic Markdownとの完全一致でなく自己整合しか見ず、seq、type、heading、span、image metadataの正値性を検査しない。 | char_endを別の有効整数へ変更 → CHECK/FK/text hash/FTS integrityは成功 → previewが恒久的に誤範囲を示す。 | P5/P13/C8/C11/C12/X9/X10/X18 | verified Markdownからcanonical chunk projectionを再生成し、全列を比較して不一致を置換する。 |
| U19 | major | §13 agg検査は「agg_embeddingsとagg_vecのtarget_key差集合を双方向」 | 同じkeyを保持したvector内容破損を検出しない。 | agg_vec[key]=Vを同長Wへ変更 → key差集合は空 → Replicate/fsckとも成功 → KNN順位だけ永久に誤る。 | P8/P11/P13/C8/C11/C12/X9/X18/X24 | folder embeddingとのvector bytes比較、checksum、またはderived vec表の再構築を行い、finite float32も検査する。 |
| U20 | major | §20.3は`mtime >= verified_at`をracyとしてfp確定せず、scanはtick.lock下 | 未来mtimeが到来するまで全量再読込を毎tick繰り返す。 | 20GBファイルをmtime=2099へ → 毎tick hash＋tmp書込 → global tick.lockがcollect/replicate/明示操作を継続的に飢餓化。 | P16/C7/C8/C11/C12/X4/X5/X14 | future-mtime anomalyをstatus化し、1回のverified hash後は有界backoff/deep-scanへ移す。 |
| U21 | major | §20.3は再帰walk、§20.4はsymlinkのみ非追跡 | bind mount、Windows junction、reparse point等のdirectory alias cycleを防ぐphysical identity集合がない。 | watch_rootを子へbind mount、またはjunctionで祖先へ接続 → 再帰が祖先を再訪 → tick.lockが永久解放されない。 | P16/C8/C11/C12/X2/X3/X14 | walkごとにdevice+inode／Windows File IDを記録し、mount/reparse方針とdepth/entry上限を定義する。 |
| U22 | major | §21.3破損journal解決は「journal除去→初期化」、flag不在時は新規採番可 | flag不在分岐ではjournal削除後crashを再駆動する耐久記録がゼロになる。 | flagなし・破損journal・id=old → journal削除 → crash → 通常起動はfork意図を知らずold id／中間履歴で運用再開。 | P16/C7/C10/C11/C12/X19/X27/X49/X54 | journalを消す前に新idとrecovery intentを別の耐久recordへ確定し、完了後に旧journalを消す。 |
| U23 | major | §21.3再開表はID_WRITTEN→手順3、APP_DONE→手順4で、old_idとの不可能組合せを拒否しない | late phaseなのにid=oldでも処理を進め、markerとapp identityを分裂させる。 | ID_WRITTEN journal＋old markerへ部分restore → 手順3がnew folders行を作るがmarkerはold → APP_DONEならflag/journalまで削除され回復根拠喪失。 | P16/C7/C10/C11/C12/X20/X22/X27/X32/X54 | phase/id validity matrixを定義し、ID_WRITTEN/APP_DONEでoldはdamaged停止または安全な手順1/2へ巻き戻す。 |
| U24 | minor | journalにstarted_atを二重化する一方、滞留判定は「fork_in_progressのstarted_at」 | app.sqlite全損後、journal単体で回復が失敗し続けても30日stalledへ格上げできない。 | app全損＋journal有効＋恒久storage障害 → 毎tick回復失敗 → flagなしのため経過起点を参照できず通常の「進行中」表示に留まる。 | P16/C3/C9-T11/C10/C11/C12/X22/X38/X54 | flag不在時はjournal.started_atを規範的なfallbackとして使用する。 |
| U25 | minor | §11.1「旧tool派生は§9.3-b逆差集合でaggから消え」対§11.2「明示dropまで残る」 | tool変更後の旧派生保持期間について説明が矛盾する。 | tool A→B → drop未実行 → §9.3-b実行 → 詳細規範ではA派生が残るが§11.1の説明では消える。 | P11/C3/C6/C10/C11/C12/X66 | §11.1を「検索eligibleから外れるが、行は明示dropまで残る」に修正する。 |
| U26 | major | §14「週次でPRAGMA incremental_vacuum」引数なし | 引数省略は回収可能な全freelist pageを対象にし、全量VACUUM回避という有界lockの趣旨を満たさない。 | 数十万行DELETE → 巨大freelist → 週次fsckで引数なしvacuum → 長時間DB処理となりwriterがbusy_timeoutを超える。 | P14/C8/C11/C12/X5/X14 | `incremental_vacuum(N)`へページ／時間budgetを設定し、残量をstatus表示して複数cycleで回収する。 |

## 第4部 — 確認済みの列挙

検出0件の検査観点:

- C2確認済み。標準SQLite部分のDDL、複合FK、generated列、FTS5 external-content view、INSERT/DELETE trigger、cascadeをin-memory DBで検証し、構文・参照列・trigger対称性に不備なし。vec0の`<dim>/<metric>`部分はtemplateとして静的整合を確認。
- C1、C3〜C12は第1部または第3部に少なくとも1件の検出があるため、検出0件には該当しない。

検出0件の原則:

- P1確認済み: 三層構成、真実層とcache層、六つの損失分類、二種類の有界損失の記述に欠落なし。
- P3確認済み: metadata.sqliteの8表、責務、親子関係、WITHOUT ROWIDの適用範囲は一貫。
- P4確認済み: unified chunks表のtype制約、generated embed_hash、span整数制約、複合一意性に不備なし。
- P7確認済み: rowidを持つ`chunks_fts_src` viewをexternal contentに用い、条件付きINSERT/DELETE triggerとrebuild/integrity-checkの構造は整合。
- P15確認済み: legacy commits/file_versions DDL、event型、鎖、LWW前提に意図しない変更なし。
- P2、P5、P6、P8〜P14、P16は第3部に少なくとも1件の検出があるため、検出0件には該当しない。