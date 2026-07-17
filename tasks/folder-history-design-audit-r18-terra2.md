不合格
target.md 全 3207 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

第1部 — 回帰確認（C9）

全450項目を判定した。fixed: A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S29 / T01〜T18 のうち、下記 superseded 項目および J09・T10・T16 を除く全ID。

superseded（→）: F05→I14、F07→I15、F12→I16/I17、F21→I03/I04、H04→I31、H15→I08/I11、H18→I16、H22→I15、A11（遷移詳細）→I05/I06/I13/I14、H02→I32。I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I15→J04、I16/I17→J01/J05、I35→J13〜J16。J04→K01、J06→K02、J03→K10、J10→K09、J13→K16、J16→K13〜K15、I12→K04、D08→K20、A01→K25。K02→L01、K06→L02、K09→L03、K12/K13→L04、K14→L07、J07/K24→L09、K19→L13、K21→L20。L09/L28→M03/M09、L20→M04、L04/L21→M02。M01→N09、M05/L07→N16、M06/K08→N17、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15。N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28。O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09/O13→Q11/Q12、O11→Q13/Q36、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37。Q02→R01、Q03→R05、Q04→R02、Q05/Q06→R06、Q06→R07、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16。R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06。S06→T09、S07→T05/T06、S11→T07、S19→T03、S20→T01、S23→T18、S24→T02、S25→T04。

| ID | 判定 | 根拠（§ + 短い引用。残存・欠落箇所） |
|---|---|---|
| J09 | not-fixed | §9.1 のDDLコメントは `completed_at` を「collect が state=2/3 へ閉じた時刻」とする。一方、通常 collect は成功を「state=2 に UPDATE」、profile_changed・item/job failure・job_missing・result_expired・output_missing・invalid_output も state/error 更新として列挙するだけで `completed_at` 書込みがない。§10 の OCR/Embed collect 再掲にも書込みがなく、detached close だけは明示的に `completed_at` を書く。 |
| T10 | partially-fixed | §6 は「原本は upload しない」「実際に upload した bytes（変換物）に適用」と規定する。しかし §9.1 相2a は「原本 upload」、§6 のJSONL規定も「upload済み原本の file id」とする。Office変換物を upload する規範が submit/JSONL の再掲へ伝播していない。 |
| T16 | partially-fixed | §11.2 は「fts_hits（および KNN の k）には内部上限（`LIMIT :fts_cap`）を置く」と規定する。しかし掲載完全SQLの `fts_hits` は `WHERE agg_chunk_fts MATCH :query` の直後で閉じ、`LIMIT :fts_cap` がない。§19 には別名 `:k_fts` を「導入」とする旧記述も残る。 |

第2部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | 現在版A → 1 tick内に作成・編集・削除 → scan/LWW/commit | 問題なし |
| 2 | X2 | MarkdownがXを参照し、既存画像Yあり → image chunk の image_hash だけYへ改竄 → fsck | U08 |
| 3 | X3 | NFD名のファイル → case-sensitive volumeへ移動 → NFC resolver と初出表記固定で再scan | 問題なし |
| 4 | X4 | 同一msの複数commitと壁時計後退 → `(created_at, commit_hash)` 比較・generated_at floor | 問題なし |
| 5 | X5 | eligible 100万行、`:limit=10` → FTS一致後の順位化・融合 | U06 |
| 6 | X6 | 日本語2文字 query → trigram沈黙後のLIKE fallback、vec0 KNN併用 | 問題なし |
| 7 | X7 | v2 grammarが画像参照形式を変更 → v1が未知v文書に対してGC | U07 |
| 8 | X8 | `..`・絶対パス・制御文字を含む宛先 → restore/exportの宛先検証 | 問題なし |
| 9 | X9 | object `H` が破損、working copyは正しいbytes `B`（hash=H） → scan → 元ファイルを削除 | U01 |
| 10 | X10 | `.folder-history` の image chunk を既存別objectへ手編集 → 週次fsck → 検索 | U08 |
| 11 | X11 | DOCXを固定版でPDF化 → 相2a upload → JSONLのfile id生成 | U02 |
| 12 | X12 | OCR collectでローカル chunks確定 → step 5前に停止 → 横断FTS | U10 |
| 13 | X13 | 有効DOCX、固定コンバータ欠落 → preflight → submit状態決定 | U05 |
| 14 | X14 | upload/job作成/collectで429（Retry-After有無） → retry_not_before と再試行 | 問題なし |
| 15 | X15 | 主張①本文escape往復、②server側重複課金有界、③profile収束、④upload掃除再駆動、⑤rotation guardが再実行を妨げない。試行: 各主張のクラッシュ境界を順に通過。破れたか: ⑤が破れた（U03）、①〜④は問題なし。 | U03 |
| 16 | X16 | 1 repositoryのOCR対象がJSONL上限超 → 相1 token付与後にJ1/J2へ分割 | U04 |
| 17 | X17 | state=1 job → unregister/cancel → token sweep・upload掃除 → 同フォルダを再登録 | U11 |
| 18 | X18 | profile record改竄・欠落・kind不一致 → profile fsck/repair → 再embed | 問題なし |
| 19 | X19 | tmp書込み・rename・dir fsync・metadata Txの各境界で電源断 → 次tick | 問題なし |
| 20 | X20 | 主張①dir fsyncで存在保証、②fsckのcurrent copy修復、③既存objectならtmp破棄安全、④tick.lockでGC競合なし、⑤LWW再scan収束。試行: object破損を既存扱いのままscan。破れたか: ③が破れた（U01）、他は問題なし。 | U01 |
| 21 | X21 | profile切替中の相1 snapshot・attempt reset・upload_cleaned reset → intent回復 | 問題なし |
| 22 | X22 | fork journalの各phaseでクラッシュ → bootstrap/recovery → 再同期 | 問題なし |
| 23 | X23 | 通常collect成功・timeout・profile_changed → `state=2/3` → status監視 | U09 |
| 24 | X24 | 主張①vec差集合再充填、②agg差集合再充填、③readyは空indexで立たない、④clientはstate=1を跨がない、⑤profile snapshotが保存される。試行: 各中断点を再実行。破れたか: 問題なし。 | 問題なし |
| 25 | X25 | app.sqliteのみで単独検索 → profile/tool決定 → restore宛先検証 | 問題なし |
| 26 | X26 | server/clientのsubmission_seq・attempts・ledgerを各close経路で照合 | 問題なし |
| 27 | X27 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE のfork journalを各境界で復帰 | 問題なし |
| 28 | X28 | detached terminalのtoken/upload掃除 → 行削除 → 再登録 | U11 |
| 29 | X29 | case-only rename・NFC衝突 → raw名resolver → restore/status | 問題なし |
| 30 | X30 | 主張①seq継承でUNIQUE衝突なし、②client課金は上限内、③fork時in-flight課金は追跡、④detached記帳、⑤rotation後の再実行可。試行: retry/cancel/再登録を循環。破れたか: ⑤が破れた（U03）。 | U03 |
| 31 | X31 | 行削除→再作成→MAX(seq)継承 → ledger UNIQUE | 問題なし |
| 32 | X32 | fork各phase × app全損/journal破損 → recovery位置判定 | 問題なし |
| 33 | X33 | server/client × 各終端理由 × crash位置 → ledger行列 | 問題なし |
| 34 | X34 | §11.2掲載SQLをそのまま組立て → FTS/KNN/RRF → 中間候補数を測定 | U06 |
| 35 | X35 | 主張①seq衝突不可、②reconcile記帳欠落なし、③submit_rejected非再投入、④期限判定、⑤最終statで偽deleteなし。試行: 各反例を構成。破れたか: 問題なし。 | 問題なし |
| 36 | X36 | ON CONFLICT記帳 × seq継承 × detached採用 → 全close経路 | 問題なし |
| 37 | X37 | missing/fork/damagedの出入り → synced_profile_hash/ready更新 | 問題なし |
| 38 | X38 | fork中移動・journal残骸・rebind → normal walk復帰 | 問題なし |
| 39 | X39 | active watch_root内でunregister → drop-derivation → 次tick walk | U13 |
| 40 | X40 | 主張①close Tx原子性、②ready部分index拒否、③fork中通常運用遮断、④cancel遷移、⑤case移動の無喪失。試行: 各境界を反証。破れたか: ④の削除後再登録が破れた（U11）。 | U11 |
| 41 | X41 | server/client × 終端理由 × token/job id → 月次ledger配賦 | 問題なし |
| 42 | X42 | damaged・read不能・missing復帰を含むready母数変動 → KNN gate | 問題なし |
| 43 | X43 | NFC/NFD/collision/raw無しの各resolver呼出点 → delete/restore/fsck | 問題なし |
| 44 | X44 | 規約12照合のread失敗4分類 → standalone/registered検索 | 問題なし |
| 45 | X45 | 主張①client中間attempt記帳、②unknownで二重jobなし、③expired記帳、④state=0回復、⑤復元直後誤課金なし。試行: 各境界クラッシュ。破れたか: 問題なし。 | 問題なし |
| 46 | X46 | token記帳→発見job記帳→seq更新 → 重複判別述語 | 問題なし |
| 47 | X47 | result expired→記帳→attempt+1→token rotation → crash再開 | 問題なし |
| 48 | X48 | in-place restore前の保全commit → rename前raw再lstat → scan | 問題なし |
| 49 | X49 | register/unregister/fork/restore/dropの直前にfork recovery → 操作継続 | 問題なし |
| 50 | X50 | 主張①無id記帳のNOT NULL充足、②推定行非増殖、③sweep回収、④detached課金、⑤fork後ready。試行: 各クラッシュ位置。破れたか: 問題なし。 | 問題なし |
| 51 | X51 | expired/(b')/sweep前段のseq UPDATE → 連番とledger一致 | 問題なし |
| 52 | X52 | expired terminal→遷移表→sweep→明示retry → token/error整合 | 問題なし |
| 53 | X53 | intent/detached/(b')/sweepの4期限判定点 → skew/猶予/unknown | 問題なし |
| 54 | X54 | journal破損の明示解決 → flag掃除 → register | 問題なし |
| 55 | X55 | embedding混在・tool混在 → 単独検索のKNN/FTS現行決定 | 問題なし |
| 56 | X56 | `\`付き擬似img block → materialize/un-escape/chunk化 | 問題なし |
| 57 | X57 | found job idをbatch_job_idへ自己記述化 → dispatch/照会/cleanup | 問題なし |
| 58 | X58 | detached terminalを再登録 → state=3/attempts/token/uploadの扱い | 問題なし |
| 59 | X59 | 課金される4xx provider → submit_rejected記帳 → 明示retry再拒否 | 問題なし |
| 60 | X60 | G・`\G`・`\\G`・非canonical行 → escape/un-escape/実在検証 | 問題なし |
| 61 | X61 | 主張①可視化遅延≤猶予、②保持期間≥timeout+結果保持+猶予、③未来skewはunknown、④全頁一覧のみabsent、⑤期限超は記帳。試行: 契約値を満たすproviderの境界値。破れたか: 文書内矛盾なし。 | 問題なし |
| 62 | X62 | job_create_started_at記録後・呼出前に反復クラッシュ → 期限起点 | 問題なし |
| 63 | X63 | cancelled terminal→upload/token掃除→行削除→再登録 | U11 |
| 64 | X64 | rotation後J2と旧token記帳が共存 → found判別IN述語 | 問題なし |
| 65 | X65 | renameat2非対応FS → 再lstat＋通常rename fallback | 問題なし |
| 66 | X66 | 規範文・要約・SQL・DDLコメントを横断比較 → conversion/FTS/completed_at | U02、U06、U09 |
| 67 | X67 | client前計上済み `state=0,batch_job_id=T,intent_token=T` → API中クラッシュ → 次tick再実行 | U03 |
| 68 | X68 | cancel→明示retry→unregister→cancel→掃除→再登録の循環 | U11 |
| 69 | X69 | FTS/KNN cap到達・外側`:limit`・RRF tie-break → 掲載SQLとの一致確認 | U06 |
| 70 | X70 | コンバータ版更新および旧版コンバータ欠落 → 再変換・upload・状態遷移 | U02、U05 |

第3部 — 新規検出

| ID | 重大度 | 該当箇所（§ + 短い引用） | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| U01 | fatal | §20.5「同一 content_hash の実体が既に存在すれば再保存しない（tmp は破棄）」 | 既存objectのhashを検証せず正しいtmpを捨てるため、破損したobjectを参照する履歴を不可逆に作れる。 | object Hは破損、working copy Bは正しくhash=H → scanがBをtmpへ保存後、Hの存在だけでtmp破棄 → metadataがHをcommit → fsck前にBを編集/削除 → Hを復元できず履歴版も失う。 | P10/P13、C1/C12、X9/X20 | tmp破棄前に既存objectのSHA-256を照合し、不一致ならtmpから原子的に置換する。置換不能ならmetadata commitを中止する。 |
| U02 | major | §6「原本は upload しない」「実際に upload した bytes（変換物）」／§9.1「原本 upload」 | Office変換物と原本のどちらをupload・upload_id記録・JSONL参照するかが両立しない。 | DOCX HをPDF Pへ変換 → 相2aを文字どおり実装してHをupload → JSONLは「原本file id」を参照 → OCR入力・cleanup対象がPでなくH、またはfile idが不整合。 | P6、C1/C6/C10/C12、C9 T10、X11/X66/X70 | 相2a・JSONLを「実際にuploadするbytesのfile id（OfficeはPDF）」へ統一し、raw原本hashは照合・履歴専用として分離する。 |
| U03 | major | §8「再実行は相1の規則一式」／§9.1「sweep前段…完了してから相1」「同 token 全行終端」 | client前計上済み行がrotation guardにより永久滞留する。 | `state=0,batch_job_id=T,intent_token=T,attempts<上限`で同期API中にクラッシュ → 次tickはclient再実行で相1必須 → sweepには同token全行終端が必要だが当該行はstate=0 → tokenをNULL化できず再実行不能。 | C7/C10/C12、X15/X30/X67 | client回復では旧attemptを明示terminal化・記帳してからsweepする遷移を定義するか、旧tokenを失わない専用回復順序を設ける。 |
| U04 | major | §6「JSONL…複数 job へ分割してよい」／§9.1「job単位のintent_token」 | JSONL分割とtoken付与の順序・job↔行対応が未定義で、1 tokenに複数jobが対応し得る。 | 上限超の1 repositoryを相1でtoken Tにした後、J1/J2へ分割 → 各行は単一 `batch_job_id` しか持てず、intent回復・採用・cleanup・記帳の対象jobが一意でない。 | P6、C11/C12、X16 | 相1前にdeterministicなjob subsetへpartitionし、subsetごとに固有intent_tokenを付与する。 |
| U05 | major | §6はOffice成功変換とunsupported_formatのみを定義 | 有効なOffice文書のコンバータ欠落・変換失敗に対するstate/error/retry/statusがない。 | 有効DOCX、固定コンバータが消失または失敗 → magic-byte上は対象形式 → terminal化・一時retry・復旧後再利用のいずれも文書から決まらず、state=0滞留または永続閉鎖が実装依存。 | P6、C8/C11/C12、X13/X70 | `conversion_failed` を導入し、一時失敗・恒久失敗・tool profile変更後の再判定を明示する。 |
| U06 | major | §11.2「内部上限（`LIMIT :fts_cap`）を置く」／掲載SQLのfts_hitsにLIMITなし／§19「`:k_fts`導入」 | 規範化された中間候補capが実行可能な掲載SQLにない。 | 100万件FTS一致、`:limit=10` → 掲載SQLは全hitをrank/fuse/sort後に外側LIMIT → メモリ・一時領域を無制限に消費する。 | P12、C4/C9/C12、T16、X5/X34/X66/X69 | fts_hitsに `LIMIT :fts_cap` を実装し、KNNのcap・bind名・§19の導入時期を同一契約へ統一する。 |
| U07 | fatal | §6「grammarを将来変更する場合はvを+1」／§13「grammarが固定形のため正規表現で `obj:` 参照を抽出」 | v更新を許す一方、GCは未知vをfail-closedにせず旧固定regexで画像rootを集める。 | v2が `obj:` 以外の画像参照形式へ移行 → v1がhash正常なv2 Markdownに対しfsck→GC → regexは画像Xをrootに含めず、24時間後Xを削除 → v2 Markdownだけ残り画像を失う。 | P5/P6/P13、C1/C12、X7 | GCをgrammar version別parserへdispatchし、未知v・混在v・未対応形式を検出したら削除全体をfail-closedにする。 |
| U08 | major | §7「image_hash…Markdownから決定論的に再構築」／§13「件数 + 各text chunkのSHA-256(text)」 | fsckがtype=2 chunkのimage_hash/media_type/image_metaとMarkdownの乖離を検出しない。 | Markdownは画像Xを参照、別画像Yも存在 → image chunkだけXからYへ改竄（text=NULL、件数不変） → fsckは通過 → folder検索/次のembedがYを扱い、Markdown・aggとの内容整合が崩れる。 | P5/P13、C1/C12、X2/X9/X10 | Markdownから全chunkを決定論的に再構築し、type=2のhash・media type・meta・seq/spanを比較して不一致時に再解析する。 |
| U09 | minor | §9.1「completed_at…collect が state=2/3へ閉じた時刻」／通常collectはstate更新のみ | 通常collectのterminal遷移が `completed_at` 不変条件を満たさない。 | 成功・profile_changed・timeout等でcollect → stateは2/3になるがcompleted_atはNULLのまま → terminal時刻の意味と監視/監査値が崩れる。 | C7/C9/C12、J09、X23/X66 | 通常collectおよびreconcile closeの全terminal更新へ `completed_at=now` を同一Txで加える。 |
| U10 | minor | §10「FTSはステップ2完了時点から有効」／§11.2は `agg_chunk_fts` を検索／§10 step5でReplicate | 横断FTSがstep2から有効であるかのように読めるが、集約FTSはstep5後まで存在しない。 | OCR collectがstep2でlocal chunksを確定 → step5前に停止 → 単独FTSは可能だが横断FTSは0件。 | P12、C11/C12、X12 | 「local FTSはstep2、横断FTSはReplicate後」と限定して記述する。 |
| U11 | fatal | §21.2「後の再登録があっても自動再課金せず、復帰は明示retryのみ」／同節「条件を満たすbatch_requestsは削除」／§9.1「成果なし・行なし→投入対象」 | cancelの再投入抑止がdetached掃除で消え、再登録時に明示retryなしで再課金される。 | state=1をcancelし `state=3,error=cancelled,attempts=上限` → token/upload掃除後に行削除 → 同フォルダを再登録 → 成果なし・行なしとして新jobを自動作成。 | C7/C12、X17/X28/X40/X63/X68 | cancelled抑止を再登録まで保持するか、再登録を明示retryと定義して利用者に明示する。 |
| U12 | fatal | §21.4 はin-placeだけ「未取り込み編集を…履歴化してから上書き」／exportは「管理フォルダ内の別名は次tickでcreate」 | 管理フォルダ内exportが既存宛先の未取り込み編集を無保全でatomic rename上書きできる。 | `draft.pdf`にscan後の編集B → 別履歴Hを宛先`draft.pdf`へexport → export分岐には既存宛先拒否・保全・再lstatがない → HがBを置換し、次tickはHをcreate記録、Bは消失。 | P1/P10/P16、C10/C12、X8/X10/X17 | export先は不在必須＋no-replaceにするか、既存先にはin-placeと同等の保全・再検証を適用する。 |
| U13 | fatal | §21.6「再課金を望まない場合は…unregister」／§21.2「active watch_root…再発見・再登録」／§21.6「drop後…自動的に再投入」 | active watch_root内では、文書どおりunregisterしてdropしても直後に再登録され、再課金回避策が成立しない。 | watch_root配下の現在版C → unregister → drop-derivation(C) → 次tickがmarkerを再発見・再登録 → 派生不在のCを自動OCR投入。 | P1、C11/C12、X17/X39 | watch_root外へ移動してからunregisterすることを必須化するか、drop前の再投入抑止を永続化する。 |

第4部 — 確認済みの列挙

検出0件として確認済み: C2（SQLite in-memoryでコアDDL・生成列・FK・external-content FTS trigger・cascade/integrityを確認）、C3、C5。

検出0件として確認済み: P2、P3、P4、P7、P8、P11、P14、P15。