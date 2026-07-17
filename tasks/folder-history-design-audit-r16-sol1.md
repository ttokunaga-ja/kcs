判定は **不合格**です。

監査前提は満たしています。探索シナリオは **70 件**、X1〜X61 をすべて実行しました。結果は次のとおりです。

- C9: fixed 313 / superseded 89 / **not-fixed 1（R18）**
- 新規検出: **fatal 2 / major 8 / minor 0 / proposal 0**
- 不合格理由: R18 が not-fixed、かつ fatal / major が存在

## 第1部 — 回帰確認（C9、全403項目）

### fixed（313項目）

- A: A02–A10, A12–A24
- B: B01–B18
- D: D01–D07, D09–D14
- E: E01–E06
- F: F01–F04, F06, F08–F11, F13–F20, F22–F27
- G: G01–G02
- H: H01, H03, H05–H14, H16–H17, H19–H21, H23–H30
- I: I01–I02, I07–I08, I10, I13–I14, I18–I34, I36–I38
- J: J01–J02, J05, J08–J09, J11–J12, J14–J15, J17–J20
- K: K01, K03–K05, K07, K10, K15–K18, K20, K22–K23, K25–K26
- L: L01–L03, L05–L06, L08, L10–L19, L22–L25, L27
- M: M02–M04, M07, M11, M14–M28
- N: N01–N02, N05–N06, N08–N12, N14, N16–N27, N29–N35, N37–N38, N41–N45
- O: O01, O06, O08, O10, O12, O14–O16, O20–O27, O29
- Q: Q01, Q07–Q08, Q11, Q15–Q37
- R: R01–R17, R19–R29

### superseded（89項目）

- r7: F05→I14, F07→I15, F12→I16/I17, F21→I03/I04, H04→I31, H15→I08/I11, H18→I16, H22→I15, A11→I05/I06/I13/I14, H02→I32
- r8: I03/I04→J06, I05/I06→J01/J02, I09→J03, I11→J03, I15→J04, I16/I17→J05/J01, I35→J13–J16
- r9: J04→K01, J06→K02, J03→K10, J10→K09, J13→K16, J16→K13–K15, I12→K04, D08→K20, A01→K25
- r10: K02→L01, K12/K13→L04, K06→L02, K09→L03, K14→L07, J07/K24→L09, K11→reconcile close 記帳義務, K21→L20, K19→L13
- r11: L09→M03, L28→M03/M09, L20→M04, L04/L21→M02
- r12: M09→N05/N06, M10→N10, M12→N38, M29→N15, M06/K08→N17, L07/M05→N16, L26→N14, M01→N09, M08→N28, M13→N30
- r13: N03→O05/O06, N04→O02/O03, N13→O21, N15→O04/O25, N36→O16, N39→O14, N40→O28, N28→O13, N07→O12
- r14: O28→Q01, O17→Q02, O02/O03→Q05/Q07, O04→Q06, O05→Q04, O07→Q09, O09→Q11/Q12, O11→Q13/Q36, O18→Q23, O19→Q24, O13→Q12, O30→Q37
- r15: Q02→R01, Q04→R02, Q09→R03, Q12→R04, Q03→R05, Q05/Q06→R06, Q06→R07, Q10→R14, Q13/Q14→R15/R16

### fixed / superseded 以外

| ID | 判定 | 根拠 |
|---|---|---|
| R18 | **not-fixed** | [§13](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:2022) は external content 照合として `INSERT INTO chunk_fts(chunk_fts) VALUES('integrity-check')` を指定するが、この形は FTS 内部整合しか検査しない。外部 content との比較には `rank=1` が必要。SQLite 3.51.0 で、content 行だけを作って posting を欠落させた状態でも文書のコマンドは成功し、`INSERT INTO chunk_fts(chunk_fts,rank) VALUES('integrity-check',1)` は error 11 になった。[SQLite公式仕様](https://www.sqlite.org/fts5.html#the_integrity_check_command)とも一致する。 |

## 第2部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | 現在版 A → 1 tick 間に B を作成・編集・削除 → step 0 の最終 walk | イベントから phantom commit を作らず、最終観測だけを採用。問題なし |
| 2 | X2 | annotation 値に `-->`・`\`・grammar 類似行 → materialize → parse | 可逆 escape と厳密認識で閉じる。問題なし |
| 3 | X3 | NFD 物理名・NFC 論理名 → 別ボリュームへ移動 → restore | raw resolver が既存実体を選ぶ。問題なし |
| 4 | X4 | 時計を1日後退 → 同一ms帯で連続コミット | `latest+1` と commit_hash tie-break で LWW は決定的。問題なし |
| 5 | X5 | 10万ファイル・100万chunk → 一括再チャンク | 大量全置換になるが、§19 の再考境界内。正しさの破綻なし |
| 6 | X6 | external-content FTS の content 行だけ残し posting を欠落 → 文書の fsck | 検出せず成功。**S03** |
| 7 | X7 | 旧アプリが新 `user_version` DB を開く | fail-closed。migration も単一Tx。問題なし |
| 8 | X8 | 2 PDFを同一Batchへ → §9.1どおり「原本 upload」→ job作成 | Batch入力JSONLの file id が定義されず、literal 実装は失敗。**S07** |
| 9 | X9 | objects保存前・rename後・metadata後・app更新前の各位置で ENOSPC | tmp残骸、未参照object、閉じ忘れ行へ収束。問題なし |
| 10 | X10 | 正常な3 chunk派生 → 中央chunkを通常DELETE → triggerもFTS削除 | 全既存fsckがgreenのまま検索欠落が永続。**S06** |
| 11 | X11 | OCR in-flight 中に画像filter変更 → floor引上げ → local変換 → collect | app floor→metadata順で旧成果を誤採用しない。問題なし |
| 12 | X12 | watch_root→commit→OCR Batch のE2E | 「原本upload」からJSONL input fileへの受渡しで途切れる。**S07** |
| 13 | X13 | 一括変換開始 → mandatory operation recordを保存 | 7-key許可集合に格納先なし。**S04** |
| 14 | X14 | submit/collectが429 + Retry-After | `retry_not_before` がtick間抑止を維持。問題なし |
| 15 | X15 | 主張「FTS fsckがposting破損を検出」→ posting欠落を注入 | 文書のコマンドでは破れた。**S03** |
| 16 | X16 | 1 uploadを複数targetで共有 → 1行だけ先に終端 | 全行終端guardで早期削除を防ぐ。問題なし |
| 17 | X17 | register→OCR in-flight→fork→新repo scan | 旧jobはdetached、新repoは再投入。意図された有界コスト |
| 18 | X18 | 同一JCS recordをtool→embedding順でprofilesへ保存 | hash単独PKで後着kindが落ち、fsck不一致が収束不能。**S05** |
| 19 | X19 | object rename直後、metadata commit直後、app close直前で電断 | 次tickの差集合で収束。問題なし |
| 20 | X20 | 主張「server未追跡jobは最大1」→ list可視化が10分超遅延 | 無計数rotationを反復できる。**S09** |
| 21 | X21 | floor設定済み対象にlocal grammar変換と新OCR結果が競合 | floor同時引上げでsilent cancelを防止。問題なし |
| 22 | X22 | forkの各phase境界でクラッシュ、journalは正常 | phase+実idから一意に再開。問題なし |
| 23 | X23 | unregisterでguard行削除→同target再登録 | ledger MAXからsubmission_seq継承。問題なし |
| 24 | X24 | 主張「vec差集合が欠落を回復」→ vec行を1行DELETE | 次tickで再充填される。欠落キーについては問題なし |
| 25 | X25 | 全フォルダ一時切断中に横断検索 | app_configからquery vectorを作り、agg cacheで検索可能 |
| 26 | X26 | client呼出中に3回連続クラッシュ | 直前seqを記帳後に再前計上し、attempts上限で停止。問題なし |
| 27 | X27 | fork途中でapp.sqlite全損・フォルダ移動 | 層1 journal走査から復旧。問題なし |
| 28 | X28 | detached state 0/1/2/3 を順に処理 | terminal→sweep→3条件削除へ進む。問題なし |
| 29 | X29 | sensitive上でcase違い2系列→insensitiveへ移動 | BINARY一致優先・UTF-8 tie-breakで決定的。問題なし |
| 30 | X30 | 主張「ledger UNIQUEは正当再課金を妨げない」→削除・再登録・retry | MAX継承と非リセットseqで破れず |
| 31 | X31 | `(b')` found記帳→掃除前クラッシュ→job一覧から消滅 | `batch_job_id`自己記述化によりtoken記帳との二重化なし |
| 32 | X32 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE × old/new id | 正常journalでは全組合せが定義済み |
| 33 | X33 | invalid_output/profile_changed/client_exhaustedを再観測 | 同一seqのledger追記はON CONFLICTで吸収。問題なし |
| 34 | X34 | 日本語2文字・headingのみ一致・`%_\\`入力 | LIKE bind分離・両列検索・escapeで問題なし |
| 35 | X35 | 主張「delete最終確認で時計前進の偽deleteを防ぐ」→対象が再出現 | regular再確認で中止。破れず |
| 36 | X36 | embedding profile A→B→A、同じguard行を再利用 | attemptsだけリセット、submission_seq維持。問題なし |
| 37 | X37 | damaged folderを除外してready→後に復帰 | readyは設定時点の被覆、復帰分は部分状態としてstatus。文書内整合 |
| 38 | X38 | valid fork flag+journalを移動先で再発見 | root rebindより先にjournal回復。問題なし |
| 39 | X39 | journalが一時EIO | 破損扱いせず保留。問題なし |
| 40 | X40 | 主張「raw resolverでNFC/NFD二重実体を防ぐ」→NFD既存へrestore | raw名を選ぶため破れず |
| 41 | X41 | 期限超tokenを同じtickで二度処理 | ledger述語と同一Txによりseq増殖なし |
| 42 | X42 | 接続folder 0件でagg構築 | readyを更新せずstatus。空虚な真なし |
| 43 | X43 | raw absent / collision / case-fold複数をdelete・restore・fsckで比較 | resolver規則自体は一貫。restore commit raceはX48で別途破綻 |
| 44 | X44 | metadata一時EIO中にz判定 | scan/reconcile/submit/replicateを保留、既存collectのみ継続 |
| 45 | X45 | 主張「zが旧metadata復元を検出」→空DB復元後に新commit追加 | cursor commit不在条件で検出。破れず |
| 46 | X46 | found jobをclose後にtoken sweep再駆動 | ledger job-id述語と行の自己記述化で二重記帳なし |
| 47 | X47 | 期限超(i)〜(iv) Txのcommit直前/直後でクラッシュ | rollbackか完全rotationの二択。問題なし |
| 48 | X48 | restoreが宛先absent確認 → 外部editorが新規Bを作成 → rename(A,dst) | Bが名前ごと消え、次walkでも復旧不能。**S01** |
| 49 | X49 | corrupt journal、flag=(O,N)、実id=O → 明示解決 | 新規M生成後、M≠Nでflagが永久残留。**S02** |
| 50 | X50 | 主張「明示操作は未完forkに反転されない」→正常journal/破損journalで試行 | 正常系は破れず、破損解決系はS02で破れた |
| 51 | X51 | found自己記述化後に再登録・collect | 行stateとjob idが同Tx更新なら誤client-dispatchなし |
| 52 | X52 | detached client state=0 → terminal記帳 → sweep失敗→再試行 | state=3が出口となり、token条件が早期削除を防ぐ |
| 53 | X53 | intent回復・detached・(b')・sweepの4照合点でfound/unknown/absent | 文書上は共通期限・伝播猶予に統一済み |
| 54 | X54 | flag=(O,N) × 実id O/N/第三id × corrupt journal | Nのみ清掃可能、Oからの明示解決は第三idへ転落。**S02** |
| 55 | X55 | 異tool派生のgenerated_at同値 | tool hashバイト昇順で決定的 |
| 56 | X56 | `G` / `\G` / `\\G` と不正hashを保存→再parse | 1段ずつ可逆、画像認識は厳密なまま。問題なし |
| 57 | X57 | state=0 server成果あり→`(b')` found自己記述化→close | `state=2`化・ledger・job idが同一app Txなら、`state=0+id`窓なし |
| 58 | X58 | detached state=0 client→terminal化→再登録がsweepより先行 | attached state=3から再投入し得るが、文書が明記した有界再課金 |
| 59 | X59 | submit_rejected + job-list非対応client | sweep照合除外でtoken残留なし。拒否課金providerは別途記帳する前提 |
| 60 | X60 | 全段escape、厳密認識、grammar再materializeを連続実行 | slash累積なし。問題なし |
| 61 | X61 | 主張「伝播猶予採用条件を満たせば最悪1job」→固定Mistral契約を確認 | 可視化遅延上限が公開契約にない。**S09** |
| 62 | 自由/X57 | self-description Tx完了後、close再観測 | 同じjob idのledger述語で重複なし |
| 63 | 自由/X58 | detached terminal後、upload掃除だけ404 | 404を成功扱いしtoken NULL化へ進む |
| 64 | 自由/X59 | server/client submit_rejectedを比較 | 未作成確定の前提下では照合除外が正しい |
| 65 | 自由/X60 | grammar v1→v2再materializeを2回 | 保存済み本文へ再escapeしないため往復維持 |
| 66 | 自由/X6 | SQLiteでrank省略とrank=1を同じ破損DBへ実行 | 前者成功、後者`SQLITE_CORRUPT_VTAB`。**S03** |
| 67 | 自由/X5/X8 | 400MB PDFをbase64-in-JSONLへ直列化 | 約533MB超になり、512MB JSONL制限を超過。**S08** |
| 68 | 自由/X13 | 一括変換中クラッシュ→app_config key一覧で再開判定 | operation recordのkeyが定義不能。**S04** |
| 69 | 自由/X18 | tool/embedding両必須項目を含む同一recordを逆順でも投入 | 先着kindが反転するだけで、必ず片方が不整合。**S05** |
| 70 | 自由/X24 | vecの既存keyを維持してfinite floatだけ改変／同profileでV1→V2再生成 | key差集合が空のため誤順位・agg履歴依存が永続。**S10** |

## 第3部 — 新規検出

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| S01 | **fatal** | [§20.5](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:2581)「残余…次回walkが…収束」、[§21.4](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:2940)「raw不在…保全をスキップ…NFC新規作成」「tmp→…atomic rename」 | renameはatomicでもno-clobberではない。確認後に現れた実体を消せば、次walkが観測するもの自体がない。既存宛先でも最終lstat後の更新を同様に失う。 | dst absent → restoreがAをstage → editorがBをdstへfsync → restoreのrenameがBを除去 → dst=A、Bはobjectにも履歴にも無く復旧不能 | P16 / C7,C11,C12 / X43,X48,X50 | absentは原子的no-replace publishとし、EEXISTなら再保全。existingは置換時点の実体をatomic exchange/backupで耐久quarantineへ残す。サポート不能ならfail-closed。 |
| S02 | **fatal** | [§21.3](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:2900)「journal除去（flag残す）→§21.1手順2→id=newでflag回収」、[§21.1](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:2721)「UUIDv7を生成」 | flagの`new_id=N`と、通常registerが新規生成する`M`が一致しない。文書の第三id規則はflagを保持するだけなので、明示解決が復旧不能状態を生成する。 | flag=(O,N), corrupt journal, actual=O → journal除去 → §21.1がMを生成 → actual=M → M≠O,Nなので永久保留 | P16 / C7,C10,C11,C12 / X49,X50,X54 | corrupt recoveryは通常registerを呼ばず、必ずflag.new_id=Nで冪等初期化する。abort意味論なら、fresh M生成前にflagを耐久削除する。第三id既存状態の明示修復も定義する。 |
| S03 | **major** | [§13](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:2022)「external content照合つき…`VALUES('integrity-check')`」 | rank省略は外部contentと比較しないため、R18の防御が実在しない。agg側では、正しいrank=1もエラーだけで「当該folder/親」を特定しない点も未定義。 | content行あり・postingなし → 文書コマンド成功 → MATCHは恒久0件 | P7,P13 / C2,C4,C9,C11,C12 / X6,X15 | `INSERT INTO fts(fts,rank) VALUES('integrity-check',1)`へ修正。agg不一致時は全agg FTSを外部viewから同Tx rebuildするか、row-level診断を別途定義。[SQLite公式](https://www.sqlite.org/fts5.html#the_integrity_check_command) |
| S04 | **major** | [§7](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:649)「app_configへoperation record」、[§9.1](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:914)「許可key集合」7種 | mandatory operation recordに対応するkeyがない。新keyは許可集合違反、既存key流用はschema違反、保存しなければ§7違反。 | bulk rechunk開始 → `bulk_operation`を書こうとして拒否、または実装ごとに異なるkey → クラッシュ後の未完了表示が非互換 | P5,P9 / C8,C10,C11,C12 / X13 | 第8keyとpayload version・存在条件・排他・cleanupを規定するか、専用`app_operations`表を追加する。 |
| S05 | **major** | [§4.1](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:166) 共通record、[§5.7](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:431)「必須フィールドが互いに排他」 | 共通schemaはkind discriminator・kind別禁止フィールド・closed optionsを定義していないため、構造的排他の主張が成立しない。 | `annotation_schema`とOCR optionsに加え`dimensions/distance_metric/l2_normalized`も持つ同一R → toolが`profiles(H,1,R)` → embeddingの`INSERT OR IGNORE(H,2,R)`が落ちる → 一方のkind参照が恒久不一致 | P2,P3 / C10,C11,C12 / X18 | hashed recordへ必須`kind:"tool"|"embedding"`を含め、kind別closed schemaと書込時一致検証を定義する。 |
| S06 | **major** | [§5.3](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:244)「行の存在=生成完了」、[§13](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:2014) fsck列挙 | local `chunks`の期待集合を保存済みMarkdownから再構築・照合する検査がない。通常DELETEならFK/FTSも整合したまま欠落する。 | 3 chunk→中央をDELETE→triggerがposting削除→PRAGMA/FK/FTS/profile/object全検査pass→parent generated_at不変→再chunkもreplicate置換も起きない | P13 / C7,C8,C11,C12 / X10 | fsckでverified Markdownを決定論的に再parseし、ordered chunk digest/manifestと比較する。repairはchildren全面置換、FTS/vector/agg invalidationまで同Txで駆動する。 |
| S07 | **major** | [§6](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:450)「Batch API…JSONL」、[§9.1](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:1015)「原本 upload→Batch job作成」 | Mistral file batchingでjobへ渡すuploadは、OCR原本ではなく`purpose=batch`のJSONL。文書はJSONLの生成・upload idと原本uploadの関係を定義していない。別途原本をuploadする方式なら、原本N個＋JSONL 1個を単一`upload_id`で追跡できない。 | PDF A/Bを原本upload→そのidを`input_files`へ渡す、またはJSONL idが存在しない→4xx→terminal `submit_rejected`→OCR不能 | P6,P9 / C1,C8,C11,C12 / X8,X12 | base64-in-JSONLを唯一の方式として、JSONL生成、`purpose=batch` upload、共有`batch_input_file_id`、`endpoint=/v1/ocr`を規定する。別原本uploadを許すならupload関係表が必要。[Mistral Batch仕様](https://docs.mistral.ai/studio-api/batch-processing)、[公式OCR Batch例](https://docs.mistral.ai/resources/cookbooks/mistral-ocr-batch_ocr) |
| S08 | **major** | [§6](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:473)「1ファイル512MB」「JSONL自体にも上限」 | base64-in-JSONLを使うと原本サイズではなく約4/3倍のJSONLがupload上限対象になる。現在のpreflightは384〜512MB帯を対応対象と誤分類する。 | 400MB PDF→preflight通過→base64だけで約533MB→JSONL upload 4xx→`submit_rejected` terminal | P6 / C8,C11,C12 / X5,X6,X8 | serialized JSONL byte数でpreflight/packingし、単一request上限を約384MB−overheadにする。大きい原本をsigned URL方式へ逃がすならS07の複数artifact追跡を追加。[Mistral制限](https://docs.mistral.ai/resources/known-limitations) |
| S09 | **major** | [§9.1](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:1068)「可視化遅延上限≤伝播猶予の場合のみ」、[§10](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:1705)「最悪job 1回分」 | 固定採用するMistralについて、公開Batch契約にjob-list可視化遅延の上限が見当たらない。これは実際に10分超遅延するとの断定ではなく、設計が必要とする契約を確認できないという実装ブロッカー。§10の無条件な収束主張とも矛盾する。 | job J1作成成功→応答前クラッシュ→10分超でも正常listに未反映→未作成扱いでtoken rotation（attempts/seq不消費）→J2作成→反復し未追跡job/課金が非有界 | P6,P9,P10 / C7,C10,C11,C12 / X20,X61 | 可視化遅延SLAまたはidempotency keyを契約要件として取得する。無ければ正常listの不存在でもambiguous attemptをattempts/ledgerへ計上して上限停止、または手動確認までquarantineする。[Batch API](https://docs.mistral.ai/api/endpoint/batch) |
| S10 | **major** | [§8-c](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:693)「target_keyが無いものを再充填」、[§13](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:2041)「target_key差集合を双方向検査」 | vec修復はkey存在だけを比較し、同keyのvector値を検証しない。same-profileでlocal vectorがV1→V2になってもaggはprofile一致のV1を置換しない。 | vecのfinite float 1個を改変→次元・距離・長さ・keyは維持→tick/fsck全通過→KNN誤順位が永続。別ケースではlocal V2、agg V1のままready成立 | P8,P11,P13 / C4,C11,C12 / X24 | normal表とvec表のvector bytes/checksumを比較し、不一致もDELETE→INSERTする。cross-folderで同key値が異なる場合は、最小repository_id等の決定的contributorと再選出規則を定義する。checksumはidentityには使わない。 |

## 第4部 — 確認済みの列挙

### C1〜C12

| 観点 | 判定 |
|---|---|
| C1 原則反映 | S07/S08でP6のBatch入力・preflight実体が不完全 |
| C2 SQL静的検証 | **S03**以外のDDL・主要queryはSQLite smoke test通過。rowid/FK/trigger対応も問題なし |
| C3 相互参照整合 | **確認済み・問題なし**。元設計§15/§21と現行§15/§21の区別も明示済み |
| C4 query/schema整合 | **S03、S10** |
| C5 数値・事実の文書内一貫性 | **確認済み・問題なし**。$2.5、+25%、768は参考値、8テーブル、RRF 60は整合 |
| C6 用語・形式 | **確認済み・問題なし**。lower hex target_key、chunk_type/target_type、obj scheme、embed_hashは統一 |
| C7 状態機械 | **S01、S02、S09** |
| C8 欠落 | **S04、S06、S07、S08** |
| C9 回帰 | **R18 not-fixed** |
| C10 修正が開けた穴 | **S02、S04、S05、S09** |
| C11 実装可能性 | **S01〜S10** |
| C12 探索型監査 | 70件実行。**S01〜S10** |

### P1〜P16

| 原則 | 判定 |
|---|---|
| P1 三層構成 | **確認済み・問題なし** |
| P2 識別子規範 | S05 |
| P3 metadata 8テーブル | S05 |
| P4 chunks統一 | **確認済み・問題なし** |
| P5 チャンク分割 | S04 |
| P6 OCR | S07、S08、S09 |
| P7 FTS | S03 |
| P8 Embedding | S10 |
| P9 Batch/app.sqlite | S04、S07、S09 |
| P10 書込順序・冪等性 | S09 |
| P11 集約 | S10 |
| P12 検索 | **確認済み・問題なし** |
| P13 GC/fsck | S03、S06、S10 |
| P14 SQLite設定 | **確認済み・問題なし** |
| P15 不変部分 | **確認済み・問題なし** |
| P16 変更検知・明示操作 | S01、S02 |

最優先で直すべき順序は、不可逆喪失・復旧不能の **S01/S02**、次に false-green fsck の **S03/S06/S10**、その後に Batch 契約の **S07/S08/S09**、最後に app_config/profile schema の **S04/S05** です。