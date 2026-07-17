## 監査判定

**FAIL（監査自体は有効）**です。  
対象は [設計書](/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs/docs/research/folder-history-sqlite-design.md:1) です。

- C12 は **65 件**の手動シナリオを実行し、**X1〜X61 を全て被覆**しました。
- C9 は 403 件中 **312 fixed / 89 superseded / 2 partially-fixed** です。
- 外部コンテンツ FTS の実行検証を含め、**major 11 件**を確認しました。
- よって、指定された pass 条件（C9 および C1〜C11 に major/fatal がないこと）を満たしません。

## 新規・残存指摘

| ID | 深刻度 | 文書引用 | 再現シナリオ（初期状態 → 操作 → 壊れる状態） | 根拠 | 修正 |
|---|---|---|---|---|---|
| S01 | major | §7「`app_config へ operation record`」／§9.1「`許可 key 集合`」は 7 key のみ列挙 | 通常の 7 key 状態 → 一括再チャンク開始 → operation record を保存しようとすると、許可 key 契約に存在しない。8 個目を勝手に追加すれば §9.1 違反、追加しなければクラッシュ後の未完了 status を出せない。 | P5, P9, C1, C8, C11, X13/X23, R23/R28 | `bulk_operation` 等を許可 key として明記し、値形式・存在条件・完了時削除を key 契約に追加する。 |
| S02 | major | §9.1 b′ は「`小 Tx で…batch_job_id へ発見 job id`」、一方 intent 回復は「`batch_job_id 非 NULL の state=0 は client 前計上済み`」 | server 行 `{state=0, batch_job_id=NULL, token=T}` に既存成果あり → b′ が `J` を見つけ、ledger と `batch_job_id=J` を小 Tx で書く → state=2 更新前にクラッシュ → 次回は `{state=0, J}` を client 経路として再実行し、server job を誤分類する。 | P9, C7, C11, X57, R06 | b′ の自己記述化・ledger・`state=2` を同一 Tx に固定する。加えて `state=0 AND batch_job_id IS NOT NULL` は client id（`intent_token`）だけ、という不変条件を明記・検査する。 |
| S03 | major | §8 は「`拒否にも課金する provider … この分岐にも記帳を足す`」。しかし §9.1 は server 4xx を `submit_rejected` にするだけで、4.5 は「`照合・記帳とも行わず`」 | 課金される content 4xx の provider → submit が `state=3,error=submit_rejected` → token sweep が照会・記帳なしで token を消す → 実課金が `cost_ledger` に永久に残らない。client でも ledger と terminal 化の原子性が規定されない。 | P8, P9, C7, C11, X33/X41/X59, R07 | server/client とも「拒否が非課金である」ことを採用条件にするか、課金され得る拒否は terminal 化・token 保持・ledger を同一 Tx で行う。 |
| S04 | major | §21.2「`cancel が確定した行は削除対象`」。一方 §9.1 の sweep は「`同 token 全行終端`」が前提 | `{state=1, token=T}` の job を cancel 成功 → state=3 への遷移、課金扱い、token の後始末が未定義 → 削除条件の `intent_token IS NULL` を満たせず、state=1 のため sweep も開始できず、detached 行が恒久残留する。 | P9, C7, C11, X58 | cancel 確定時の `state=3,error='cancelled'`、課金方針、4.5 への引渡しを明記する。削除は terminal → cleanup → token NULL 後に限定する。 |
| S05 | major | §9.1 は future を `token_time > now+5分` の場合だけ期限超扱いにし、猶予は「`0 ≤ now − token 時刻 ≤ 猶予`」「`未来側は対象外`」 | 送信端末時計が +4 分 → server job `J` 作成後、相3前にクラッシュ → 現端末では token は未来 4 分で、future-skew 判定にも past-side 猶予にも入らない → 一覧遅延中の confirmed-absent を「期限内」として `J2` を再投入し二重課金。provider が 10 分以内の可視化保証を満たしていても起こる。 | P9, C7, C11, X61, R05 | token が未来なら少なくとも token 時刻到達まで保持し、その後 past-side 猶予を適用する。許容 skew 内の未来を通常の載せ直しへ落とさない。 |
| S06 | major | §13 は external-content 照合として `INSERT INTO chunk_fts(chunk_fts) VALUES('integrity-check')` を指定 | `chunks` に row 1 を残して FTS posting だけ削除 → 指定 SQL は成功し、`MATCH` は 0 件のまま → 週次 fsck が欠落 posting を検出・rebuild できない。SQLite 3.51 で再現済み。 | P7, P13, C2, C4, C11, X18/X34/X62, R18 | `INSERT INTO chunk_fts(chunk_fts, rank) VALUES('integrity-check', 1)` を local / agg とも使用する。 |
| S07 | major | §13 は agg FTS 不一致時に「`当該フォルダの…該当親行 DELETE`」を要求 | repo A/B を集約済み → B の posting だけ破損 → external-content integrity-check は generic な corruption エラーしか返さず、repository / parent を返さない → 文書どおりには B を特定して修復できない。 | P13, C2, C11, X18/X63 | parent/repository を特定する明示差分検査を追加する。特定不能なら agg FTS 全体を rebuild し、全 `synced_profile_hash` を NULL 化する。 |
| S08 | major | §9.3-a は cursor より新しい履歴のみ INSERT。§13 の集約検査は vectors と markdown/chunks 親子のみ | source/agg に C1,C2、cursor=C2 → agg の C1 `agg_file_versions` だけを削除 → FK/PRAGMA は通過、次 replicate は `> C2` だけなので C1 を永遠に復元しない → 現在版・過去版検索が静かに欠落する。 | P11, P13, C4, C8, C11, X18/X64 | repo ごとに `agg_commits` / `agg_file_versions` の mirror 整合を検査し、不一致なら当該 repo の agg 履歴を wipe して cursor を NULL に戻す。 |
| S09 | major | §11.2 は必須条件として `c.text IS NOT NULL AND (...)` と書くが、後段の「完全形」は `WHERE c.text LIKE ... OR c.heading_path LIKE ...` | annotation 無し image chunk `{text=NULL, heading_path='会計課'}` → 2 文字 query で LIKE fallback 実行 → 後段 SQL は heading に一致して image chunk を返す → 3 文字以上の FTS では view の `text IS NOT NULL` により返らず、検索対象集合が境界で変わる。 | P12, C4, C11, X34, R20 | 後段の完全 SQL を `WHERE c.text IS NOT NULL AND (c.text LIKE ... OR c.heading_path LIKE ...)` に置換する。 |
| S10 | major | §9.1 は detached を「`フォルダへの書込は一切行わない`」、§10 step 2 は detached 処理の直後に「`次に state=1 の job`」を通常の metadata 書込みへ送る | detached server 行 `{state=0, token=T}` → 冒頭 detached 処理が provider job を found して state=1 へ採用 → 同一 tick の次段が採用後の state=1 を通常 collect 対象に含める実装では、存在しない metadata.sqlite へ b/c を実行する。候補集合をいつ固定するか・folders join をするか未定義。 | P9, P10, C7, C11, X58/X65 | 通常 collect を `folders` に join して attached 行だけに限定する、または detached handler で採用した行は次 tick まで通常 collect から除外する。 |
| S11 | major | §9.1 は猶予を detached を含む「`全照合点`」へ共通適用するが、detached (b) は「`期限内の不存在確認も state=3`」と書く | detached server 行、token は 2 分前、provider job は可視化遅延中 → 共通則なら unknown 保持、個別則を文字通り読めば `state=3(detached)` → 再登録後に成果なし terminal として再投入され、元 job と二重化する。 | P9, C7, C11, X53 | detached の順序を明記する。future skew → past-side propagation grace は保持 → grace 後かつ期限内の confirmed-absent だけ terminal 化、と統一する。 |

SQLite 実行検証では、FTS posting を削除した後に文書指定の `integrity-check` は成功して `MATCH` が 0 件、`rank=1` 付きだけが `database disk image is malformed` を返しました。

## C9 回帰確認（403 件）

| 判定 | 件数 | 対象 |
|---|---:|---|
| fixed | 312 | superseded と R18/R20 以外の全 C9 ID |
| superseded | 89 | 下記の正規対応表どおり |
| partially-fixed | 2 | R18, R20 |
| not-fixed / regression | 0 | なし |

`partially-fixed` の根拠:

- **R18**: §13 は external-content 照合を明記するものの、指定 SQL に `rank=1` がなく、実際には照合しません（S06）。
- **R20**: 必須条件自体は記載される一方、後段の「完全形」SQL が `c.text IS NOT NULL` を落とします（S09）。

superseded は監査プロンプトの正式対応表を適用しました。圧縮表記は次のとおりです。

- A01→K25、A11→I05/I06/I13/I14、D08→K20
- F05→I14、F07→I15、F12→I16/I17、F21→I03/I04
- H02→I32、H04→I31、H15→I08/I11、H18→I16、H22→I15
- I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I12→K04、I15→J04、I16/I17→J05/J01、I35→J13〜J16
- J03→K10、J04→K01、J06→K02、J07→L09、J10→K09、J13→K16、J16→K13〜K15
- K02→L01、K06→L02、K08→N17、K09→L03、K11→reconcile close、K12/K13→L04、K14→L07、K19→L13、K21→L20、K24→L09
- L04/L21→M02、L07→N16、L09/L28→M03/M09、L20→M04、L26→N14
- M01→N09、M05→N16、M06→N17、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15
- N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28
- O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37
- Q02→R01、Q03→R05、Q04→R02、Q05/Q06→R06、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16

## C1〜C12 と P1〜P16

| 観点 | 結果 |
|---|---|
| C1 原則反映 | 要修正。P5/P7〜P13 の一部に S01〜S11。 |
| C2 SQL 静的検証 | 要修正。FTS external-content integrity-check の指定と agg 修復手順が不成立（S06/S07）。 |
| C3 相互参照整合 | **確認済み・問題なし**。§1〜§21 の内部参照は実在し、§22・KCS 文書参照は外部・旧設計参照として明示されています。 |
| C4 クエリとスキーマ | 要修正。LIKE fallback（S09）と forward-only aggregate mirror（S08）。 |
| C5 数値・事実 | **確認済み・問題なし**。$2.5/1k、+25%、768 は参考値、RRF=60、8 tables の記述は整合。 |
| C6 用語・形式 | **確認済み・問題なし**。target_key、lower hex、chunk/embed key、obj スキームは一貫。 |
| C7 状態機械 | 要修正。S02〜S05、S10、S11。 |
| C8 欠落 | 要修正。operation key 契約、aggregate history mirror 検査、cancel 終端遷移。 |
| C9 回帰 | partially-fixed: R18/R20。 |
| C10 修正が開けた穴 | 検出あり。S01〜S11 は主に r15/r16 相互作用。 |
| C11 実装可能性 | 要修正。状態・修復・設定の分岐が追加設計判断なしに一意にならない箇所がある。 |
| C12 探索型監査 | **有効に実施**。65 シナリオ、X1〜X61 全被覆。S01〜S11 を検出。 |

問題なしとして確認した原則は **P1, P2, P3, P4, P6, P14, P15, P16** です。

影響あり:

- P5: S01
- P7: S06
- P8: S03
- P9: S02〜S05, S10, S11
- P10: S10
- P11: S08
- P12: S09
- P13: S06〜S08

## C12 探索ログ

各行は「初期状態 → 操作 → 結果」です。`問題なし` は、そのシナリオで破綻を構成できなかったことを示します。

| 観点 | 手動シナリオと結果 |
|---|---|
| X1 | 現在版 A、未観測の編集 B→削除 → 完全 walk を 30 秒以上隔てて 2 回 → pending 後に delete のみ記録。未観測中間版を履歴化しないことは設計範囲であり、問題なし。 |
| X2 | 改行・`obj:`・コメント形を含む名前と Markdown → name_invalid / strict image grammar / escape を適用 → path 脱出・phantom image は発生せず、問題なし。 |
| X3 | NFD 名を case-insensitive volume で登録後、case-sensitive volume へ移動 → 保存名固定・raw resolver・新系列 create → 二重参照や FK 不整合なし。 |
| X4 | 時計後退と同一 ms の複数 commit → created_at clamp と commit_hash tie-break → LWW と cursor は決定的。問題なし。 |
| X5 | 10 万ファイル・100 万 chunk を想定 → walk は必要、§19 の再検討境界に到達 → 正しさの破綻でなく運用境界として明記済み。 |
| X6 | 2 文字 query を text chunk に実行 → trigram を避け LIKE fallback → RRF へ参加。通常 text 行では問題なし。 |
| X7 | migration 前から生存する writer と schema 更新 → tick.lock 後に user_version 再確認 → 旧 writer は書込み前に遮断。問題なし。 |
| X8 | `../x`、symlink 差替え、他ユーザー可読 directory → name 検証、dirfd/O_NOFOLLOW、権限 fail-closed → 問題なし。 |
| X9 | 静止 backup、object 欠損、working copy 一致 → fsck の 1 stream repair → metadata と object の整合を回復。問題なし。 |
| X10 | `.folder-history` を手動削除 → damaged status、勝手な再初期化なし → 原本を破壊しない。問題なし。 |
| X11 | grammar/フィルタ変更と floor 付き再生成 → app floor を先に上げて metadata 更新 → silent cancel は起きない。問題なし。 |
| X12 | register→scan→OCR→chunk→embed→replicate→search→restore → 各入出力は接続済み。通常経路の未定義なし。 |
| X13 | 一括変換の crash status を確認 → operation record の保存 key が未定義 → **S01**。 |
| X14 | submit/collect で 429 と Retry-After → app_config 抑止期限を跨いで再試行 → 問題なし。 |
| X15 | 主張「objects→metadata の耐久順序」へ電断を各境界で挿入 → metadata 前は未参照 object、metadata 後は dir fsync 済み object → **反証できず**。 |
| X16 | 共有 upload を持つ複数 target の一方だけ terminal → 全行 terminal 前には削除しない → 回収不能・再課金を防止。問題なし。 |
| X17 | register 中断、damaged、fork 後 GC、unregister→再登録 → 規定手順では復帰する。問題なし。 |
| X18 | profiles / agg FTS / agg 履歴を部分破損 → **S06/S07/S08**。 |
| X19 | object rename 前後、metadata Tx 前後で電断 → tmp 残骸または参照済み object に収束。問題なし。 |
| X20 | 主張「server intent recovery は最大 1 job」へ過去側 2 分 token + list absent → propagation grace で保持 → **通常時は反証できず**。X61 で future-skew 反例を検出。 |
| X21 | profile A→B、attempts reset、seq 継続 → 次の ledger は新しい seq → 問題なし。 |
| X22 | fork の PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE で中断 → phase と id により再開点が一意。問題なし。 |
| X23 | app_config 7 key から bulk transform 開始 → operation record の場所がない → **S01**。 |
| X24 | local `embedding_vec` の一部だけ削除 → submit 冒頭の差集合充填 → 欠落 vec を再作成。**反証できず**。 |
| X25 | app.sqlite 全損・フォルダ未接続 → standalone FTS は可能、横断 KNN は bootstrap profile 再入力まで停止 → 問題なし。 |
| X26 | attempts / submission_seq / ledger を profile reset と retry で交差 → attempts だけ reset、seq は継承 → 問題なし。 |
| X27 | journal 作成・各 phase・削除境界で電断 → journal/flag の順序で再開 → 問題なし。 |
| X28 | detached state=1 の job 完了 → payload 破棄、ledger、cleanup、token NULL、削除 → 問題なし。 |
| X29 | `Report.pdf` / `report.pdf` の移動と restore → 保存表記固定・採用 tie-break → 問題なし。 |
| X30 | 主張「seq 継承で再登録後も UNIQUE 衝突しない」へ ledger max=7、行再作成、再投入 → seq=8 で close → **反証できず**。 |
| X31 | ledger max=7、batch row 不在 → 新規 INSERT は 7 を継承、相3で8 → 問題なし。 |
| X32 | terminal profile=A, current=B → attempts=0、seq は 7 のまま → B の初回は seq=8。問題なし。 |
| X33 | server/client × terminal 理由の課金行列 → billable `submit_rejected` の ledger 経路が欠落 → **S03**。 |
| X34 | §11.2 SQL を組立て、NULL text image の 2 文字 heading query → fallback だけが対象を広げる → **S09**。 |
| X35 | 主張「submit_rejected は自動再投入されない」へ非課金 4xx、attempts=上限 → submit 対象外 → **反証できず**。課金記帳は S03。 |
| X36 | profile A→B→A で同 seq の close を再観測 → `ON CONFLICT DO NOTHING` と state close → 問題なし。 |
| X37 | damaged/missing/fork を ready 母数から除外 → 0 接続時は ready 更新なし → 問題なし。 |
| X38 | fork 中移動、journal 発見、flag 単独 → old/third/unreadable は掃除しない → 問題なし。 |
| X39 | rebind、対象外型への置換、root dirfd → delete 保全と resolver が両立 → 問題なし。 |
| X40 | 主張「query profile hash 固定で TOCTOU を防ぐ」へ embed 後 profile 切替 → 同 read Tx で一致、別 snapshot では FTS-only → **反証できず**。 |
| X41 | close 経路の全端末理由を確認 → billable rejection のみ記帳規範が非原子的 → **S03**。 |
| X42 | damaged folder 復帰、synced NULL、ready 再構築 → 部分 index を ready にしない → 問題なし。 |
| X43 | NFD/NFC/collision/raw 不在 × delete/restore/fsck → raw resolver の帰結が一意 → 問題なし。 |
| X44 | 登録済み path の read、marker 差替え、一時 EIO、standalone copy → 4 分類と provenance 表示 → 問題なし。 |
| X45 | 主張「unknown では二重 job を作らない」へ 429/5xx → state=0 保持、token 回転なし → **反証できず**。 |
| X46 | token 記帳→rotation→found 採用→collect の連番 → 通常の seq 述語では重複なし。問題なし。 |
| X47 | 期限超の (i)〜(iv) Tx の各境界で中断 → ledger/attempt/rotation は同一 Tx → 問題なし。 |
| X48 | restore 前に working copy が LWW と異なる → 先に commit、安定失敗なら中止 → 問題なし。 |
| X49 | 全 §21 操作の前に fork recovery を走らせる → 未完 fork を反転しない → 問題なし。 |
| X50 | 主張「無 id ledger は NOT NULL と衝突しない」へ token 記帳・found 記帳・3 段 escape → 値規則と往復は通常ケースで成立、反証なし。 |
| X51 | b′ / sweep / expiry の seq UPDATE と再登録 high-watermark → 通常の全経路で連番衝突なし。問題なし。 |
| X52 | expired terminal→sweep→explicit retry→new phase1 → token 世代と seq が分離。問題なし。 |
| X53 | 4 照合点を比較 → detached 個別規定が propagation grace と衝突 → **S11**。 |
| X54 | journal 有効/破損/読取不能 × flag/id の組合せ → 明示解決だけが gate bypass → 問題なし。 |
| X55 | embeddings の一意 profile と Markdown generated_at tie → byte-order tie-break、混在時 FTS-only → 問題なし。 |
| X56 | `\![diagram](obj:see appendix)` を保存・再解析 → broad unescape、strict recognition → 問題なし。 |
| X57 | b′ found 記帳直後に crash → `state=0,batch_job_id=server J` が client dispatch と衝突 → **S02**。 |
| X58 | unregister で cancel 成功した state=1 → terminal 遷移なしで token cleanup 不能 → **S04**。 |
| X59 | 課金される permanent reject → `submit_rejected` sweep 除外で ledger なし → **S03**。 |
| X60 | G / `\G` / `\\G`、noncanonical、object 不在を全組合せで往復 → 可逆性・phantom 防止・text_hash 安定は成立。問題なし。 |
| X61 | Mistral 相当の可視化遅延が猶予内でも、token が未来 4 分 → grace 外で再投入 → **S05**。 |
| X62 | SQLite 3.51 で source row を残して FTS posting を削除 → 文書指定 check は成功、`rank=1` は corruption → **S06**。 |
| X63 | repo A/B の agg FTS で B だけ破損 → check は row/repo を返さず、当該 parent を選べない → **S07**。 |
| X64 | cursor=C2 の agg から C1 file_version を削除 → replicate は `>C2` のみ、C1 が永久欠落 → **S08**。 |
| X65 | detached handler が state=0 を state=1 に採用した同 tick → 後続の無限定 state=1 collect が metadata 書込みへ進み得る → **S10**。 |

X61 の補足として、Mistral の公式資料では Batch job と metadata/filtering は確認できましたが、可視化遅延の上限は確認できませんでした。したがって、この設計書が置く「採用条件」を満たす provider として自動的には扱えません。[Mistral Batch API](https://docs.mistral.ai/api/endpoint/batch)

## Proposal（指摘ではない改善候補）

- active な `batch_requests` 行に `intent_token IS NOT NULL` をスキーマでも強制する。
- provider の「job 一覧」は pagination / status scope を完全走査できない限り `confirmed-absent` にしない、と明記する。
- `cost_ledger` の append-only を DB 境界にも要求するなら、UPDATE / DELETE を abort する trigger を追加する。