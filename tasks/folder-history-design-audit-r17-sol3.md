不合格
target.md 全 3135 行を読了 — 最終行: 『```』

## 第 1 部 — 回帰確認（C9）

A01〜A24、B01〜B18、D01〜D14、E01〜E06、F01〜F27、G01〜G02、H01〜H30、I01〜I38、J01〜J20、K01〜K26、L01〜L28、M01〜M29、N01〜N45、O01〜O30、Q01〜Q37、R01〜R29、S01〜S29 の全 432 項目を判定した。

監査プロンプトの対応表に従う superseded 項目:

- A11→I05/I06/I13/I14、F05→I14、F07→I15、F12→I16/I17、F21→I03/I04、H02→I32、H04→I31、H15→I08/I11、H18→I16、H22→I15
- I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I15→J04、I16/I17→J05/J01、I35→J13〜J16
- A01→K25、D08→K20、I12→K04、J03→K10、J04→K01、J06→K02、J10→K09、J13→K16、J16→K13〜K15
- J07/K24→L09、K02→L01、K06→L02、K09/K11→L03、K12/K13→L04、K14→L07、K19→L13、K21→L20
- L04/L21→M02、L09→M03、L20→M04、L28→M03/M09
- K08/M06→N17、L07/M05→N16、L26→N14、M01→N09、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15
- N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28
- O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37
- Q02→R01、Q03→R05、Q04→R02、Q05/Q06→R06/R07、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16
- R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06

上記 superseded 項目と次表の S20 を除く全項目は fixed。

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
| --- | --- | --- |
| S20 | partially-fixed | §5.7 は「kind=tool の record は annotation_schema を必須」「他 kind の必須フィールドを持つ record は拒否」と修正済み。一方、正本形式を示す §4.1 は tool / embedding 共通の例として `{"v":1,…,"annotation_schema":{…},"options":{…}}` をなお掲載しており、embedding record に tool 必須フィールドを入れる指示が残る。 |

## 第 2 部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
| ---: | --- | --- | --- |
| 1 | X1 | `a.pdf` の OCR が state=1 → 同内容で `b.pdf` へ rename → scan が delete/create を記録 → OCR collect | 問題なし。content_hash 経由で新しい名前から派生を解決 |
| 2 | X2 | 本文に `\![diagram](obj:see appendix)` と object 不在の canonical 風行 → materialize → parse | 問題なし。緩い un-escape 後も厳密認識・実在検証で phantom chunk なし |
| 3 | X3 | NFD 物理名を持つフォルダを正規化非依存 FS へコピー → NFC 論理名で restore | 問題なし。readdir resolver が raw 名を選択 |
| 4 | X4 | 時計を 1 時間後退 → 同一 ms 帯で連続 commit・再チャンク | 問題なし。created_at/generated_at の単調クランプと hash tie-break が作動 |
| 5 | X5 | 10 万 chunk の profile 切替 → vec 再充填途中で中断 → 次 tick | 問題なし。差集合再充填と ready gate で部分 index を正常扱いしない |
| 6 | X6 | 日本語 2 文字クエリ「検索」→ trigram FTS 実行不能 → fallback | 問題なし。text/heading_path の LIKE、escape、limit が定義済み |
| 7 | X7 | 新版が grammar v=2・DB user_version=2 を保存 → 旧版が開く | 問題なし。未知 v と新 DB 版はいずれも fail-closed |
| 8 | X8 | 細工された file_name `../outside` を持つ履歴から in-place restore | 問題なし。name_invalid と root 脱出検査で拒否 |
| 9 | X9 | 原本 object 欠損、working copy は同一 hash → fsck repair → GC | 問題なし。1 ストリーム原子置換後に GC |
| 10 | X10 | `.folder-history` の一時 EIO → register と standalone read | 問題なし。破損扱いせず保留し、破壊的初期化へ進まない |
| 11 | X11 | OCR 明示再生成中に画像フィルタ一括変更 → generated_at 更新地点でクラッシュ | 問題なし。app floor 先行引上げにより明示 intent は消えない |
| 12 | X12 | watch_root 登録 → scan → OCR → chunk → embed → replicate → 検索 → restore | 問題なし。各段の入力・出力と解決キーが接続している |
| 13 | X13 | profile 未設定、fork stalled、damaged、明示 retry の各 status から操作を追跡 | 問題なし。入力・効果・回復先が本文内に存在 |
| 14 | X14 | submit/collect が Retry-After 無し 429 を反復 | 問題なし。既定 backoff が app_config に永続化される |
| 15 | X15 | 主張「P2→P3→P2 でも空 index が ready を騙らない」→ profile 往復中に wipe 直後クラッシュ | 問題なし（主張は破れず）。synced_profile_hash 全 NULL 化が効く |
| 16 | X16 | 複数 item の server job を相2b後・相3前でクラッシュ → 一覧照合 | 問題なし。三値照合と found 採用で同一 job を回収 |
| 17 | X17 | register 手順2途中で電断 → 不完全 metadata → 再実行 | 問題なし。構造破損と一時不可読を分離して回復 |
| 18 | X18 | profiles 参照行だけ欠損 → fsck → batch snapshot から修復 | 問題なし。LEFT JOIN 検査と同一 Tx DELETE→INSERT が作動 |
| 19 | X19 | object rename 後・metadata commit 前に電断 | 問題なし。rename 後の directory fsync と次 tick 差集合で収束 |
| 20 | X20 | 主張「未追跡 server job は最大1」→ 作成直後の一覧遅延中に dirty tick | 問題なし（主張は破れず）。採用条件内では伝播猶予が再投入を止める |
| 21 | X21 | embedding A の job 中に現行を B へ変更 → A 結果 collect → B submit | 問題なし。A は破棄・記帳、B は attempts を数え直す |
| 22 | X22 | fork の ID_WRITTEN 直後にクラッシュ → 次 tick | 問題なし。journal phase と実 id から手順3へ一意に再開 |
| 23 | X23 | client API 呼出中クラッシュを2回反復 | 問題なし。各再実行前に旧 seq を estimated 記帳し attempts 上限で停止 |
| 24 | X24 | 主張「同 profile の vec 部分欠落は自己修復」→再充填途中で毎境界クラッシュ | 問題なし（主張は破れず）。毎 tick 差集合が残りを埋める |
| 25 | X25 | フォルダ切断中に app.sqlite だけで横断検索 | 問題なし。app_config から query embedding を生成し missing status を返す |
| 26 | X26 | batch 行削除時 ledger MAX=7 → 同 repo 再登録 → 再投入 | 問題なし。seq=7 を継承し、相3で8となる |
| 27 | X27 | fork journal の digest 破損、flag は new_id を保持 → 明示解決 | 問題なし。flag の new_id で初期化し、第三 id を作らない |
| 28 | X28 | detached state=0 server 行で job found →採用→完了 | 問題なし。payload 破棄、ledger、sweep、行削除の順に収束 |
| 29 | X29 | case-insensitive FS で `Report.pdf`→`report.pdf` | 問題なし。初出論理名を維持し FK 系列は分裂しない |
| 30 | X30 | 主張「行削除後の正当な再課金は ledger UNIQUE と衝突しない」→再登録・再投入 | 問題なし（主張は破れず）。MAX 継承が機能 |
| 31 | X31 | client metadata Tx 完了後・app close 前クラッシュ → reconcile | 問題なし。成果あり close が ledger と floor を同一 Tx で処理 |
| 32 | X32 | HISTORY_CLEARED 中に移動され old_id で新 commit が追加 | 問題なし。commits 非空判定により手順1から再開 |
| 33 | X33 | invalid_output、profile_changed、job_missing、item失敗を順に terminal 化 | 問題なし。各 seq に ledger は最大1行 |
| 34 | X34 | agg 再構築中に検索 → ready 不一致 | 問題なし。KNN を止め FTS-only で応答 |
| 35 | X35 | 主張「submit_rejected は自動再投入されない」→次 tick | 問題なし（主張は破れず）。attempts=上限 |
| 36 | X36 | profile A→B→A、同 seq に profile_changed と reconcile close が到来 | 問題なし。ON CONFLICT DO NOTHING が同一課金の再観測だけを吸収 |
| 37 | X37 | C が damaged の間に A/B で ready=P2 → C 復帰 | 問題なし。C の復帰分は通常の部分性として差集合が埋める |
| 38 | X38 | journal 無、flag 有、実 id=old/new/第三 id を各々評価 | 問題なし。new のみ掃除、old/第三 id は damaged 停止 |
| 39 | X39 | 既存 store が register 中だけ EIO | 問題なし。新規初期化・damaged 復旧へ進まない |
| 40 | X40 | 主張「raw resolver で NFD 実体隣への二重作成を防ぐ」→NFD 宛先へ restore | 問題なし（主張は破れず）。raw 解決と直前 lstat が作動 |
| 41 | X41 | 期限超 token を estimated 記帳→rotation→新 job 成功 | 問題なし。seq は推定 attempt と実 job で別々に進む |
| 42 | X42 | 接続0件→1件復帰→同期完了 | 問題なし。0件では ready を更新せず、復帰後に設定 |
| 43 | X43 | NFC/NFD 両実体、case-sensitive/insensitive の組合せで resolver 実行 | 問題なし。採用規則と collision status が決定論的 |
| 44 | X44 | 登録済み root_path を別 repository に差替え → read | 問題なし。scoped 規約12が conflict で結果を止める |
| 45 | X45 | 主張「復元直後の誤課金を step -1 が防ぐ」→metadata を旧版へ復元して tick | 問題なし（主張は破れず）。submit 前に regressed 判定 |
| 46 | X46 | token キーの期限超推定行作成後、同 attempt の job が遅延可視化 | 問題なし。sweep の `IN(job id, token)` が二重記帳を防ぐ |
| 47 | X47 | 期限超処理を (i)〜(iv) の各論理境界でクラッシュ | 問題なし。DB 書込が単一 Tx のため中間確定しない |
| 48 | X48 | 未 scan の working 編集あり → 過去版を in-place restore | 問題なし。現内容を先に履歴化し、直前 lstat で再確認 |
| 49 | X49 | ID_WRITTEN 中断中に unregister を実行 | 問題なし。fork 回復が先行し、新 id の状態へ unregister を適用 |
| 50 | X50 | 主張「G / `\\G` / `\\\\G` が往復可逆」→保存・再 materialize・再解析 | 問題なし（主張は破れず）。再エスケープせず1個だけ除去 |
| 51 | X51 | (b') found 小 Tx 後にクラッシュ → sweep 再訪 | 問題なし。seq更新・ledger・batch_job_id自己記述化が同一 Tx |
| 52 | X52 | 期限超で attempts 上限到達 → expired → sweep →明示 retry | 問題なし。terminal、token清掃、新 token の順で復帰 |
| 53 | X53 | intent回復・detached・(b')・sweepで found/unknown/absent を比較 | 問題なし。三値、期限、猶予、記帳値が共通化されている |
| 54 | X54 | journal の有効/破損/不可読 × flag 有無 × id old/new/第三を追跡 | 問題なし。各組合せに保留・回復・明示解決が定義済み |
| 55 | X55 | tool generated_at 同値かつ embeddings profile 混在 | 問題なし。tool は byte tie-break、KNN は停止して FTS-only |
| 56 | X56 | `\![diagram](obj:see appendix)` を保存・解析 | 問題なし。decoder 拡張により余分な `\` は残らない |
| 57 | X57 | sweep found で自己記述化した terminal 行を再訪 | 問題なし。照合から外れるが残骸掃除・token NULL 化には残る |
| 58 | X58 | detached payload 破棄後、行削除前に同 repo を再登録 | 問題なし。成果なし state=2/3 は有界に再投入され ledger 追跡される |
| 59 | X59 | 拒否にも課金する provider で submit_rejected | 問題なし。拒否分岐自身で記帳してから sweep 除外 |
| 60 | X60 | canonical、非canonical、object不在の各行を escape/un-escape/認識 | 問題なし。可逆性と厳密な画像認識が両立 |
| 61 | X61 | 主張「provider 採用条件下で intent 回復は有界」→最大可視化遅延・最短保持期間の境界で照合 | 問題なし（主張は破れず）。条件を満たさない provider は採用対象外と明記 |
| 62 | X62 | 旧 attempt の job_create_started_at が残る行 → 時計後退後に新 intent → 相2b前クラッシュ | T01 を検出 |
| 63 | X63 | state=0/1 を cancel confirmed → unregister → token sweep →再登録 | 問題なし。採用条件内では記帳・清掃後に再生成へ収束 |
| 64 | X64 | token 推定行を持つ attempt の delayed found と、rotation 後の別 attempt を比較 | 問題なし。同 attempt は IN で吸収、別 attempt は新 token のため過吸収しない |
| 65 | X65 | no-replace 非対応 FS で API が EINVAL/ENOTSUP、直前に宛先が出現 | T05 を検出 |
| 66 | X66 | §4.1 の共通 profile 例で embedding record を生成 → §5.7 shape 検証 | T02 を検出 |
| 67 | 自由探索 | chunks.text の同一長・同件数 bit-rot → fsck の FTS rebuild と親子件数検査 | T03 を検出 |
| 68 | 自由探索 | embeddings.vector の有限値 mantissa だけ bit-flip → vec 再構築 → fsck | T04 を検出 |

## 第 3 部 — 新規検出

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | major | §9.1 DDL「job_create_started_at…NULL = 相2b未着手 = job は存在し得ない」／相1は新 intent_token、batch_job_id、error、completed_at、upload_cleaned を更新するが同列を初期化しない／期限判定「起点=max(intent_token時刻, job_create_started_at)」 | batch_requests 行の再利用時に旧 attempt の開始時刻が残り、「NULL/非NULLは現在の intent の相2b実行有無」という不変条件が成立しない。時計後退と組み合わさると、未実行 job に estimated ledger・attempts 消費・偽 expired を作る。 | 旧 attempt の開始時刻=12:00、行は終端 → 時計を11:00へ補正 →明示 retry の相1が新 token を書くが12:00を残す →相2b前にクラッシュ→一覧は confirmed-absent →起点12:00が now+5分超として期限超扱い→外部 job が無いのに seq/attempts と推定課金が増え、反復で expired | P9 / C7 / C10 / C11 / C12-X62 | 新 intent_token を書く相1・期限超rotation・明示retryの同一 Txで `job_create_started_at=NULL` にする。必要なら「開始時刻が現在の intent に属する」ことを token 世代で検証する。 |
| T02 | major | §4.1「tool_profile_hash / embedding_profile_hash…profile_record=`{…annotation_schema…options…}`」／§5.7「tool は annotation_schema 必須」「他 kind の必須フィールドを持つ record は拒否」 | embedding record の正本形式が相互矛盾する。§4.1どおりなら annotation_schema を持つため§5.7が拒否し、§5.7どおりなら§4.1の共通形式に反する。必須 embedding を追加判断なしに実装できない。 | §4.1 の例から annotation_schema 付き embedding profile を生成 → adapter が embedding record に tool 必須フィールドありとして拒否 → app_config embedding_profile が設定できず、submit・vec検査・KNNが恒久 skip | P2 / P3 / C1 / C6 / C9-S20 / C10 / C11 / C12-X66 | §4.1 に tool/embedding の排他的な canonical record を別々の完全例で定義する。embedding 例から annotation_schema を除き、両方に完全修飾 model と test vector を付ける。 |
| T03 | major | §13「FTS不一致は同 Txで rebuild」／「folder側の親子整合…対応（件数）」／§4「text_hash=SHA-256(chunk text UTF-8 bytes)」 | fsck は chunks の件数しか Markdown の決定論的再解析結果と比較せず、text_hash・span・heading_path・image_meta 等の内容整合を検証しない。FTS rebuild は破損 chunks を正として索引し直すため、破損を固定化する。 | 正常 text=`abc`、text_hash=H、FTSも正常 → SQLite payload の1 byteが有限・構造有効な `xbc` に変化（件数不変、H不変）→PRAGMA検査は通過、FTS integrity-checkだけ不一致→規範どおり rebuild→FTSが`xbc`を索引、親子件数も一致→FTS本文とHに紐づくKNN vectorが異なる内容を表し続ける | C11 / C12-自由探索（X9/X10系） | fsckで text_hash 再計算、image object・span・seq・heading・metadata を検証し、保存済みMarkdownを§7で再解析した完全な期待行集合と比較する。不一致時は chunks を再解析置換してからFTS rebuildする。 |
| T04 | major | §5.6 vector CHECK は「typeof='blob' AND length=4×dimensions」だけ／§13 集約検査は「agg_embeddings と agg_vec の target_key 差集合を双方向に検査」 | 長さを変えない vector の silent bit-rotを検出できない。embeddingsを正としてvecを再構築すると、破損vectorが正規化され、キー差集合も空になるため誤順位が恒久化する。 | 正常float32 vectorを保存 → mantissaの1 bitだけ反転し有限値・長さ・dimensions・profile hashを維持 → embedding_vecを再構築 → local/aggのキー集合は一致しfsck通過 → KNNが黙って異なる順位を返す | C11 / C12-自由探索 | embeddingsに identity用途ではない `vector_hash` を追加し、書込時・fsck時にSHA-256を検証する。非有限値・次元・L2 normも再検査し、不一致はvec→embeddings削除後のre-embedを駆動する。aggは検証済みfolder行から再同期する。 |
| T05 | minor | §21.4「可能なプラットフォームでは…RENAME_NOREPLACE…EEXIST相当は中止」 | no-replace API/FS非対応時の EINVAL、ENOSYS、ENOTSUP、ENOTEMPTY 等の分類と安全なfallbackが未定義。安全側に中止できるため minor だが、実装ごとに「restore不能」と「通常renameへfallbackして上書き」の二択に分岐する。 | raw不在を確認 → SMB/FAT等でno-replaceが非対応 →確認後に外部プロセスが同名ファイルを作成→APIはEEXISTでなく unsupported error →通常renameへfallbackした実装は新内容を履歴化せず上書き、常時中止する実装は当該FSでrestore不能 | P16 / C8 / C11 / C12-X65 | capability判定、全エラー分類、非対応時の規範を固定する。安全な代替がない場合は「raw不在へのin-place restoreを中止しstatus」と明記し、通常renameへの暗黙fallbackを禁止する。 |

## 第 4 部 — 確認済みの列挙

検査観点:

- 確認済み・問題なし: C2、C3、C4、C5。
  - C2 は metadata/app/agg のDDL、GENERATED列、CHECK、FK、rowid、FTS external-content view、INSERT/DELETE trigger、rank=1 integrity-check/rebuildを確認した。主要DDLとFTS操作はインメモリSQLiteでも実行可能だった。
  - C3 は本文内参照先の実在と文脈を確認した。
  - C4 は版CTE、ハイブリッド検索、差集合、GC、レプリケーションSQLとスキーマの列・型・キー整合を確認した。
  - C5 は `$2.5/1,000`、`+25%`、768の参考値扱い、RRF k=60、8テーブルの全出現を確認した。
- 検出あり: C1=T02、C6=T02、C7=T01、C8=T05、C9=S20、C10=T01/T02、C11=T01〜T05、C12=T01〜T05。

設計原則:

- 確認済み・問題なし: P1、P4、P5、P6、P7、P8、P10、P11、P12、P14、P15。
- 検出あり: P2/P3=T02、P9=T01、P13=T03/T04、P16=T05。