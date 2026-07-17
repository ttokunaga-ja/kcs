不合格
target.md 全 3284 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第1部 — 回帰確認（C9）

全474項目を判定した。471項目は fixed または superseded、2項目は partially-fixed、1項目は regression。

| 範囲 | 判定 |
|---|---|
| A01–A24 / B01–B18 / D01–D14 / E01–E06 / F01–F27 / G01–G02 / H01–H30 / I01–I38 / J01–J20 / K01–K26 | すべて fixed または superseded |
| L01–L28 | L07 は後発 M05 で精密化、それ以外は fixed または superseded |
| M01–M29 / N01–N45 / O01–O30 / Q01–Q37 / R01–R29 / S01–S29 / T01–T18 | すべて fixed または superseded |
| U01–U24 | U02–U05、U07–U23 は fixed。U01、U06、U24 は下表 |

| ID | 状態 | 重大度 | 期待状態 | target.md の現状 | 判定根拠 |
|---|---|---:|---|---|---|
| U01 | regression | major | Batch 入力・`upload_id` は実際に upload した入力を指し、Office 文書では変換 PDF を指す。「原本 upload」の残存は禁止 | §6:482–485、503–505 と §9.1:1090–1093 は修正済みだが、§6:508 に「列は原本用」、513 に「upload 原本の削除」、§10:1735 に「原本を…submit」が残る | DOCX について変換 PDF の handle を保存しない、または非対応の原本を upload する実装が成立し、provider 上の残骸を追跡不能にする |
| U06 | partially-fixed | major | `state` を 2/3 へ確定する全 UPDATE が `completed_at=now` を同時書込み | §9.1:1219–1221 は共通規範を明記する一方、DDL コメント §9.1:901–902 は「collect が閉じた時刻」「書込点は §10 collect」と限定 | reconcile、submit rejection、client exhausted 等が `completed_at=NULL` になり得て、滞留判定・状態表示が実装箇所により分裂する |
| U24 | partially-fixed | major | 不可能な fork phase × marker ID は回復証跡を保持して damaged 停止 | §21.3:3099–3101 は `ID_WRITTEN` と `APP_DONE` を ID 無条件で進め、3102–3106 の停止条件は「old/new 以外」に限る | `ID_WRITTEN + old_id` は手順3、`APP_DONE + old_id` は手順4へ進み、marker が old のまま flag/journal を消せる。`folders(new)` との恒久 conflict を残す |

## 第2部 — P1〜P16 回帰監査

SQLite 3.51.0 の in-memory DB で通常表、FK、FTS5 view/trigger、`rank=1` integrity-check/rebuild、検索 SQL を検証した。通常 DDL は `integrity_check=ok`、FK は整合した。sqlite-vec の `<dim>/<metric>` テンプレートは拡張未搭載のため静的検査とした。

| 原則 | 判定 | 根拠・該当指摘 |
|---|---|---|
| P1 | 不適合 | V08。安定した暗号化・破損ファイルを履歴化する有界条件に永続状態がなく、一度も保護されない経路がある |
| P2 | 適合 | UUIDv7、JCS、hash、最短10進表現、raw UTF-8 heading、profile 分離は整合 |
| P3 | 適合 | 8表、FK、external-content FTS、vec テンプレート、profile 表は整合 |
| P4 | 適合 | unified chunks、型別 CHECK、`embed_hash`、画像注釈の全-field 規範は整合 |
| P5 | 不適合 | V04。適用済み chunk/filter 規則を識別できず、コピー・再登録後に現行規則へ収束しない |
| P6 | 不適合 | C9-U01。Office 変換物と原本 upload の表現が残存 |
| P7 | 適合 | filtered view、INSERT/DELETE trigger、UPDATE trigger 不使用、rebuild は整合 |
| P8 | 不適合 | V04。device-global image filter と folder 側派生の適用状態を比較できない |
| P9 | 不適合 | V01、V02、V03、C9-U06。token rotation、provider scope、abandon、terminal timestamp に欠陥 |
| P10 | 不適合 | V01、V02、C9-U06。submit-before-sweep と wrong-scope 404、close 要約が不整合 |
| P11 | 不適合 | V05。`sync_state` と append-only mirror の部分喪失が自己修復しない |
| P12 | 不適合 | V07。掲載 SQL の `fts_cap` が window rank/temp 処理を有界化しない |
| P13 | 不適合 | V06、V10。agg 子内容破損が count-only 検査を通過し、GC 実行点の参照も不正確 |
| P14 | 適合 | WAL、FK、busy timeout、migration、version 再確認、有界 vacuum、権限規範は整合 |
| P15 | 適合 | immutable base schema、LWW、同時 commit 保持、Repository ID、旧構造禁止は整合 |
| P16 | 不適合 | C9-U24、V08、V09、V10。fork 不可能状態と有界スキップ、参照表現に欠陥 |

## 第3部 — 新規指摘と C12 シナリオ監査

### 新規指摘

| ID | 重大度 | 箇所 | 問題 | 再現シナリオ | 根拠 | 修正方針 |
|---|---|---|---|---|---|---|
| V01 | fatal | §9.1:1030、1056–1063、1275、1362–1385、§10:1801–1806 | rotation guard が accounting-incomplete な `state=2` を除外する | profile B の job J/token T 作成後に相3前クラッシュ → profile A の既存成果で reconcile が `state=2` に閉じる → token 照合429で T保持 → Bへ戻す → submit が sweep より先に Tを新tokenで上書き → Jの記帳キー消失＋新job投入 | token sweep は state 2/3 を終端とする一方、rotation guard は terminal を state=3 と同一視している | 旧tokenを自身で処理済みの state=0 requeue/client dispatch 以外、少なくとも `state IN (2,3)` の全token上書き前に照合・記帳・NULL化を必須化 |
| V02 | fatal | §9.1:857–924、1047–1074、1172–1175、1239–1249 | job 作成時 account/workspace scope を永続化できず、wrong-scope 応答を判別不能 | workspace A で job 作成 → crash/資格情報をBへ変更 → Bの空一覧または404 → confirmed-absent/job_missing として再投入 → A/B双方で課金 | 同一scopeだけを正常応答とする規範があるが、`batch_requests`、profile snapshot、`app_config` に作成時scopeがない。collect は account変更404を恒久消滅として扱う | provider と account/workspace の安定IDをattemptごとに保存し、照会前に比較。不一致は unknown/stalled とし再投入禁止 |
| V03 | major | §9.1:939–948、1065–1068、§21全体 | 明示 abandon の Tx、seq、ledger key、状態遷移、再開規則が未定義 | seq=n に旧ledgerあり、次attemptが token T のままunknown → 現seqでestimated記帳すると UNIQUE が吸収 → TをNULL化 → 後日jobが現れても追跡不能。NULL化先行クラッシュでも記帳キーを失う | 唯一の記述は「estimated 記帳 + intent_token NULL化」。§21操作カタログに存在せず、`batch_job_id=token`、`submission_seq+1`、同一Txの指定もない | §21へ操作を追加し、入力・対象state・ユーザー確認・既存ledger述語・必要なseq更新・`batch_job_id=token`・ledger INSERT・token NULL化を単一Txで規定。late-found の扱いも固定 |
| V04 | major | §2:50、§7:684–693、§8:826–835、§21.1:2897–2926 | コピー・再登録した folder が現行 chunk/filter 規則へ宣言的に収束しない | device Aで画像filter OFFの派生を作成 → folderをBへコピー → Bは既にfilter ON → register → 設定変更イベントも適用済みhashもなく、logo chunkがFTS/KNN対象として恒久残留 | 設定は app 側の現行値だけで、行・folderに適用規則版がない。register は `fp_cache` 無効化のみ。`bulk_operation` は一時hintで全損し得る | folder側に適用済みrule/filter recordまたはhashを保存し毎tick比較するか、import/register/bootstrap時に全派生の再chunkを必須化 |
| V05 | major | §9.2:1573–1590、§9.3:1599–1640、§13:2202–2213 | `sync_state` と agg append-only mirror の双方向不変条件を検査しない | agg行を残して `sync_state` だけ削除 → NULL cursor の plain INSERT が既存PKに衝突し毎tick abort。逆にagg行だけ削除しcursorを残すと `> cursor` が欠損を永久に再コピーしない | z はfolder側maxとcursorだけを検査し、fsckもmirror coverageを検査しない | cursorまでのsource/mirror key・fieldを双方向検査。不一致、またはcursor欠損＋agg残留時はrepo単位でagg4表とcursorをwipeしてfull resync |
| V06 | major | §9.3:1641–1646、§13:2179–2186、2205–2212 | agg chunk の意味的破損を件数だけで検査する | aggの子1行のtext/image_hash等を同一key・同一件数のまま改変 → FTS rebuildが破損行を正として索引 → parent `generated_at` 一致でReplicateも再コピーしない | 2179–2180 は内容破損を親子検査で直すと主張するが、実際のagg検査は「件数」のみ。folder側では件数のみでは不十分と自ら説明している | folder側 chunks と全決定的fieldを照合し、不一致時は既存のparent削除、synced NULL、ready削除、再同期経路を実行 |
| V07 | major | §11.2:1950–1959、2089–2091 | `fts_cap` がwindow rankingと一時sort入力を制限しない | 10,000件が同一語に一致、cap=10で掲載SQLを実行 → 出力10行だが10,000行をwindow/sort処理 | SQLite 3.51.0で `rows=10000` のFTS scan・eligibility probe・temp B-treeを確認。VM stepは100件時1,074から10,000件時70,374へ増加 | `ORDER BY score, chunk_uid LIMIT :fts_cap` を MATERIALIZED CTEで先に確定し、その集合だけへ `ROW_NUMBER()` を適用 |
| V08 | fatal | §9.1:965–993、1415–1447、§10:1691–1694、§20.5:2704–2708 | 構文検証の「3回または24時間」判定を永続化する場所がない | 安定した暗号化/破損PDFをcron tickごとに検証 → 毎回別processで初回扱い → 永久skip → 後日削除 → bytesが一度もobjects/historyへ保存されず喪失 | `scan_cache`、`pending_deletes`、`fp_cache`、許可app_config keyに回数・初回失敗時刻がない。EIOとの区別・reset条件も未定義 | fingerprint、失敗回数、`first_failed_at`、失敗種別を永続化。安定read後のsyntax failureだけを加算し、EIOは加算せず、fingerprint変更・成功・commitでreset |
| V09 | minor | §20.5:2707 | 文書内に定義のない監査原則参照 `(P1)` が残る | 実装者が文書内P1を探索 → 該当節なし | 周辺はbytes保存原則で意味を推定できるが、standalone設計の参照として無効 | 文書内の正式な節番号・規約番号へ置換 |
| V10 | minor | §21.3:3060–3063、§13:2145–2149、§10:1807–1812 | GCをstep 5以後に実行する規範の参照先§13に、その実行点がない | 実装者が§13または§10のpipelineからGC実行点を構成 → 見つからない | §21.3本文の規則自体は明確だが、参照先はlock/cadence/graceのみ | §10と§13へ実行点を明記するか、参照を正しい箇所へ変更 |

### C12 実行ログ（X1〜X74）

| ID | 初期状態 → 操作列 → 到達状態 | 結果 |
|---|---|---|
| X1 | 新規folder → register、追加、scan、OCR、embed、replicate、検索 → 全層が同一content/profileへ収束 | 問題なし |
| X2 | 改行・制御文字・`obj:`・img block風文字を含む名前 → validate/JCS/escape → 名前は拒否または安全に直列化 | 問題なし |
| X3 | case-sensitive上のcase違い2名 → insensitive環境へコピーしwalk/resolver →規定tie-breakで一方を採用しcollision表示 | 問題なし |
| X4 | created_at採番中に時計後退・同一ms commit → `max(now,last+1)` とhash tie-break → LWW順序維持 | 問題なし |
| X5 | 100万級FTS一致 → `fts_cap=10` の掲載SQL → window/temp処理は全一致行を消費 | V07 |
| X6 | 日本語2文字query → trigram MATCHゼロ → escaped LIKE fallback →仕様どおり短語検索 | 問題なし |
| X7 | 旧reader接続中にwriter migration → version再確認・Tx migration・FTS rebuild →旧writerは拒否 | 問題なし |
| X8 | `../`、絶対path、symlink swap → file_name検証＋root dirfd相対操作 → folder外参照拒否 | 問題なし |
| X9 | object 1件欠損 → fsck、working bytes照合、backup restore → hash一致時のみ復旧 | 問題なし |
| X10 | filter OFFのfolderをzip/展開してfilter ON端末へregister →適用規則を比較不能 →旧画像chunk残留 | V04 |
| X11 | filter一括変換の途中でapp.sqlite全損 → `bulk_operation`消失・folder派生は混在 →未完了を検出不能 | V04 |
| X12 | watch_root登録から横断検索まで通し実行 → dirty、scan、submit、collect、replicateの順で収束 | 問題なし |
| X13 | state3/token unknown → 文書中の「明示abandon」を探索・実行 → Tx・seq・状態規範がない | V03 |
| X14 | b' close時に429 → state2/token保持 → 次tick前に成果失効 → submitがtokenを上書き | V01 |
| X15 | 主張「旧tokenの発見・記帳経路を失わない」→ state2 accounting-incomplete行を再投入 → token消失 | 主張は反証成立、V01 |
| X16 | profile A→B→A、相3前crash、資格情報変更 → recovery/list照会 →作成時scopeを判別不能 | V02 |
| X17 | 他端末で作られた既存store → §21.1 register → fp無効化のみでfilter/chunk規則は未収束 | V04 |
| X18 | profile record改変・孤児profile・vec片側欠損 → fsck/DELETE→INSERT/refill →整合回復 | 問題なし |
| X19 | abandonでledger書込み直前・直後に電断 → 再開位置と原子性が未定義 →欠落または重複推定 | V03 |
| X20 | 主張「server重複課金は最悪job 1回分」→ account A→B→Cで404再投入を反復 → attempts上限まで複数job | 主張は反証成立、V02 |
| X21 | app.sqlite全損、folder metadata維持 → tool/embed profile再入力・bootstrap →通常派生は再発見 | 問題なし |
| X22 | fork `ID_WRITTEN`後にmarkerだけoldへ復元 → recovery → step3/4が進み証跡削除 | C9-U24 |
| X23 | account Aのstate0/token行 → appの資格情報をBへ変更 →空一覧 → scope snapshot不在 | V02 |
| X24 | 主張「vec差集合再充填は任意crash後に収束」→ vec作成/半充填/再tick →差集合が欠損を補充 | 主張の反証なし |
| X25 | folder未接続でagg検索 → repository provenanceとmissing statusを返す →folder書込みなし | 問題なし |
| X26 | abandon対象に旧seq ledgerあり →現seq記帳またはseq増分を選択 →どちらが規範か決定不能 | V03 |
| X27 | fork `APP_DONE` journalとold markerの組合せ → recovery →手順4のみでjournal/flag消失 | C9-U24 |
| X28 | unregisterでdetached state0/state1生成 → collect冒頭処理、ledger、sweep、段階削除 →追跡維持 | 問題なし |
| X29 | NFC同一・raw表記違いのrename/restore →共有resolver →二重実体を作らず規定名を採用 | 問題なし |
| X30 | 主張「ledger UNIQUEは正当な別attemptを吸収しない」→定義済み全closeをseq別で再実行 →各attempt 1行 | 主張の反証なし |
| X31 | b' unknownでstate2/token残存 → profile再変更 → state2再投入が旧tokenを上書き | V01 |
| X32 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE × old/newを全数化 →後二phase＋oldが素通り | C9-U24 |
| X33 | account Aのstate1 jobをB資格情報でGET →404をjob_missing化 →Bで再投入 | V02 |
| X34 | eligible 10,000件＋共通語 →完全hybrid SQL、cap=10 →出力のみ10、rank/tempは10,000 | V07 |
| X35 | 主張「forkはid=oldから正しく再開」→ `ID_WRITTEN + old` を入力 →新app行とold markerが分裂 | 主張は反証成立、C9-U24 |
| X36 | estimated abandon記帳後・token NULL前にcrash →再実行 →記帳済み述語/seq規範なし | V03 |
| X37 | ready構築中にmissing/damaged folder混在 →実行可能folderだけを母数化、0件はready非更新 | 問題なし |
| X38 | fork途中でfolder移動、valid journal保持 →walk/registerが移動先journalを先に回復 | 問題なし |
| X39 | 現行filter ON端末へfilter OFFのfolderを再発見 →register/rebind →旧派生を識別不能 | V04 |
| X40 | 主張「readyは不完全・不正indexを通さない」→ agg childを同件数のまま改変 →ready維持・再同期なし | 主張は反証成立、V06 |
| X41 | server/client全終端理由をwrong-scope 404込みで列挙 →旧jobと新jobが別scopeで実行 | V02 |
| X42 | ready profile一致後にagg textをbit-rot →FTS rebuild＋count検査 →破損内容が固定化 | V06 |
| X43 | delete/restore/fsckでcase違いraw名を解決 →同一共有resolver →呼出点間で採用名一致 | 問題なし |
| X44 | 登録pathのrepository-idを別IDへ交換 →scoped read/step -1 →conflictでread/write停止 | 問題なし |
| X45 | 主張「照会失敗はattemptsを消費しない」→ wrong-account 404 →job_missing化し再投入 | 主張は反証成立、V02 |
| X46 | token推定ledgerが既存のabandon →既存判別とseq更新を適用しようとする →規範なし | V03 |
| X47 | state2/token残存中にprofile変更 →submitがstep4.5より先行 →旧job照合キー消失 | V01 |
| X48 | restore in-place前にworking≠LWW →保全commit、上書き、次tick →履歴とworkingが収束 | 問題なし |
| X49 | register等の回復先行gateからabandonを探索 →§21に操作がなくgate・lock・失敗回復を適用不能 | V03 |
| X50 | 主張「無ID記帳は常にNOT NULL値を持つ」→ abandon ledgerを構成 →`batch_job_id`値規則にabandonなし | 主張は反証成立、V03 |
| X51 | seq行UPDATEを全無ID経路で確認 → abandonだけ増分・新値利用が未定義 | V03 |
| X52 | `expired` state3/token残存 →明示retry →state3 rotation guardが照合・記帳を先行 | 問題なし |
| X53 | intent/reconcile/detached/sweepをscope変更下で実行 →作成時scopeを保存しておらず対称判定不能 | V02 |
| X54 | digest不一致journal →明示解決例外 →journal除去、再初期化、flag後回収の順で収束 | 問題なし |
| X55 | standalone folderに複数旧profile行 →現行embed/tool決定規則 →一意でなければstatus/制限 | 問題なし |
| X56 | altに `\\](` 等を含むimg block →escape/unescape/reparse →元値へ一意に復元 | 問題なし |
| X57 | found記帳でbatch_job_id自己記述化済み行とstate2未記帳行を比較 →後者だけguard対象外 | V01 |
| X58 | detached terminal行をrepo再登録でattached化 →成果なしなら規定の有界再投入・ledger保持 | 問題なし |
| X59 | 拒否にも課金するprovider →submit_rejected分岐でseq+1とestimated記帳 →sweep除外と整合 | 問題なし |
| X60 | block escape 0本以上のbackslashと各patternを往復 →decoderが規定順で復元 | 問題なし |
| X61 | 主張「伝播猶予と保持期限の契約でfound/absent/unknownを安全に分離」→契約を満たすproviderで境界時刻を試行 →猶予中はunknown、期限後はestimated | 主張の反証なし |
| X62 | 正常aggからrepoの`sync_state` 1行だけ削除 →初回full INSERT扱い →既存PK衝突を毎tick反復 | V05 |
| X63 | cancelled terminal行を再登録後に明示retry →attempts reset、seq継承、state3 guard →有界再投入 | 問題なし |
| X64 | token key推定ledger後に実job IDが可視化 →`IN(job id, token)`述語 →二重記帳を抑止 | 問題なし |
| X65 | no-replace非対応FS →再lstat、不在確認、通常rename →出現時は中止 | 問題なし |
| X66 | 規範とDDL/要約を横断比較 →Office uploadとcompleted_atに旧表現残存 | C9-U01、C9-U06 |
| X67 | state0 confirmed-absent requeueへ旧全行guardを適用する反例を試行 →現行U03はstate0を除外し循環回避 | 問題なし |
| X68 | cancelled行を明示retryし再度cancel →attempts上限とseq通算により自動無限循環なし | 問題なし |
| X69 | 共通語大量一致に小さな`fts_cap` →RRF候補は打切るがwindow/temp処理は全件 | V07 |
| X70 | converter版更新で旧`convert_failed`行あり →新tool keyを生成 →新行として正常判定 | 問題なし |
| X71 | state0/token/job作成crash →成果ありclose＋unknownでstate2/token保持 →成果失効後に再投入 | V01 |
| X72 | unknown tokenを明示abandon →estimated記帳後にjobが可視化 →seq/key/late-found規範がなく一意に処理不能 | V03 |
| X73 | 旧toolの`convert_failed` terminal →converter更新 →旧行と新target keyは独立 | 問題なし |
| X74 | 安定した暗号化DOCX＋tick毎process再起動 →構文検証失敗を反復 →3回/24hを永続判定できず未保護 | V08 |

## 第4部 — 指摘ゼロカテゴリ

### C1〜C12

| 基準 | 指摘状況 |
|---|---|
| C1 | 指摘あり: V04、V06 |
| C2 | 指摘あり: V07 |
| C3 | 指摘あり: C9-U01、C9-U06、V09、V10 |
| C4 | 指摘あり: C9-U06、V02、V03、V05 |
| C5 | 0件 |
| C6 | 0件 |
| C7 | 指摘あり: C9-U24、V01、V02、V03 |
| C8 | 指摘あり: V02、V03、V08 |
| C9 | 指摘あり: U01、U06、U24 |
| C10 | 指摘あり: V01、V04 |
| C11 | 指摘あり: V03、V05、V06、V07、V08 |
| C12 | 指摘あり: C9-U24、V01〜V08 |

C基準の指摘ゼロカテゴリは C5、C6。

### P1〜P16

| 原則 | 指摘状況 |
|---|---|
| P1 | 指摘あり: V08 |
| P2 | 0件 |
| P3 | 0件 |
| P4 | 0件 |
| P5 | 指摘あり: V04 |
| P6 | 指摘あり: C9-U01 |
| P7 | 0件 |
| P8 | 指摘あり: V04 |
| P9 | 指摘あり: C9-U06、V01、V02、V03 |
| P10 | 指摘あり: C9-U06、V01、V02 |
| P11 | 指摘あり: V05 |
| P12 | 指摘あり: V07 |
| P13 | 指摘あり: V06、V10 |
| P14 | 0件 |
| P15 | 0件 |
| P16 | 指摘あり: C9-U24、V08、V09、V10 |

P原則の指摘ゼロカテゴリは P2、P3、P4、P7、P14、P15。