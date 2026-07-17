判定: **不合格**

前提条件は充足しています。X1〜X61 を各 1 件以上、自由探索を含め **63 シナリオ**追跡しました。  
不合格理由は、回帰確認で `M02` / `R08` / `R20` が partially-fixed、かつ新規検出に fatal 3 件・major 4 件があるためです。

## 第1部 — 回帰確認（C9）

以下は全 403 項目の圧縮判定です。`superseded` は指定された優先対応表に従いました。

| 系統 | fixed | superseded |
|---|---|---|
| A | A02–A10, A12–A24 | A01→K25、A11→I05/I06/I13/I14 |
| B | B01–B18 | — |
| D | D01–D04, D06–D07, D09–D14 | D05→E04、D08→K20 |
| E | E01–E06 | — |
| F | F01–F04, F06, F08–F09, F11, F13–F20, F22–F27 | F05→I14、F07→I15、F10→H08、F12→I16/I17、F21→I03/I04 |
| G | G01–G02 | — |
| H | H01, H03, H05–H14, H16–H17, H19–H21, H23–H30 | H02→I32、H04→I31、H15→I08/I11、H18→I16、H22→I15 |
| I | I01–I02, I07–I08, I10, I13–I14, I18–I34, I36–I38 | I03–I04→J06、I05–I06→J01/J02、I09/I11→J03、I12→K04、I15→J04、I16/I17→J05/J01、I35→J13–J16 |
| J | J01–J02, J05, J08–J09, J11–J12, J14–J15, J17–J20 | J03→K10、J04→K01、J06→K02、J07→L09、J10→K09、J13→K16、J16→K13–K15 |
| K | K01, K03–K05, K07–K08, K10, K15, K17–K18, K20, K22–K23, K25–K26 | K02/K16→L01、K06→L02、K09/K11→L03、K12/K13→L04、K14→L07、K19→L13、K21→L20、K24→L09 |
| L | L01–L03, L05–L06, L08, L10–L19, L22–L25, L27 | L04/L21→M02、L07→N16、L09→M03、L20→M04、L26→N14、L28→M03/M09 |
| M | M04, M07, M11, M14–M28 | M01→N09、M03/M05→N16、M06→N17、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15 |
| N | N01–N02, N05–N06, N08–N12, N14, N16–N27, N29–N35, N37–N38, N41–N45 | N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28 |
| O | O01, O06, O08, O10, O12, O14–O16, O20–O27, O29 | O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37 |
| Q | Q01, Q07–Q08, Q11, Q15–Q37 | Q02→R01、Q03→R05、Q04→R02、Q05/Q06→R06、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16 |
| R | R01–R07, R09–R19, R21–R29 | — |

| ID | 判定 | 根拠 |
|---|---|---|
| M02 | partially-fixed | §9.1 は detached client 行を「`state=3 (error='detached') + completed_at`」へ遷移させ 4.5 に委ねる一方、§21.2 は client 行を「**terminal 記帳後に削除**」と要約している。後者は token/upload の削除ガードを落とす。 |
| R08 | partially-fixed | §9.1 の段階遷移は正しいが、§21.2 の上記残存文が「記帳して即削除」を再導入している。 |
| R20 | partially-fixed | §11.2 前半は `c.text IS NOT NULL AND (...)` を必須とするが、後半の差替え SQL は `WHERE c.text LIKE ... OR c.heading_path LIKE ...` として `c.text IS NOT NULL` を落としている。 |

## 第2部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | 現在版 `h0` → 1 tick 中に編集・削除 → 完全 walk を2回実施 | pending_deletes 経由でのみ delete。問題なし |
| 2 | X2 | 手書き `\![x](obj:see)`、偽 img block、制御文字名 → materialize・chunk | 厳密認識と loose un-escape が分離され、phantom 化しない。問題なし |
| 3 | X3 | NFD 名のフォルダを case-insensitive から sensitive volume へ移動 → walk/restore | 保存論理名固定と raw resolver により系列は決定的。問題なし |
| 4 | X4 | 最新 commit 時刻 100 → 時計後退して scan 時刻 90 → 新 commit | `max(now, latest+1)` により 101。LWW/cursor は後退しない。問題なし |
| 5 | X5 | 10万ファイル・大量 chunk → selected_files / eligible / replicate を追跡 | 巨大 `IN` に依存せず EXISTS・差集合で進む。問題なし |
| 6 | X6 | image chunk: `text=NULL`, `heading_path=["図"]` → 2文字検索 `図` | 後段 LIKE SQL が image-only 行を返す。**S06** |
| 7 | X7 | 旧 writer が待機中 → migration が user_version を更新 → writer 再開 | tick.lock 後の user_version 再確認で旧 writer を遮断。問題なし |
| 8 | X8 | `../x`、絶対パス、NUL 相当の論理名 → scan/restore | name_invalid で管理外。問題なし |
| 9 | X9 | objects 保存後・metadata 前、metadata 後・app 前でそれぞれ容量枯渇 | 参照順序と collect の成果確認で次 tick 収束。問題なし |
| 10 | X10 | `.folder-history` の部分同期、metadata 手編集、object 欠損 → fsck/register | damaged/conflict/fail-closed に分岐。問題なし |
| 11 | X11 | floor 設定済み明示再生成 → 再チャンク → crash → collect | app 側 floor 先行引上げで silent cancel は起きない。問題なし |
| 12 | X12 | watch_root 登録 → OCR → embed → replicate → 検索 → restore | 各段の入出力は定義済み。問題なし |
| 13 | X13 | グローバル画像フィルタ変更 → operation record を app_config へ書込 → crash | 許可 key 集合に記録先がない。**S01** |
| 14 | X14 | submit/collect が 429 + Retry-After → 次 tick | retry_not_before が永続化され、期限前再試行しない。問題なし |
| 15 | X15 | 主張5件（dir fsync、unknown 保持、vec 差集合、30秒 delete、空母数 ready）を各クラッシュ境界で反証 | 5件とも破れず |
| 16 | X16 | 1 repo の JSONL を複数 job に分割 → 各行へ別 token → crash/recovery | token は job 単位に保てる。問題なし |
| 17 | X17 | register 途中 crash、restore 後 scan、unregister→再登録 | 通常 journal が健全なら各操作は収束。問題なし |
| 18 | X18 | tool/embedding が同じ JCS record/hash を持つ → tool INSERT → embedding INSERT OR IGNORE | profiles.kind が片方に固定される。**S05** |
| 19 | X19 | objects→metadata→app の各耐久境界で電断 | 未参照 object / close漏れだけが残り、回収経路あり。問題なし |
| 20 | X20 | 「1 job 上限」「月次確定月」「宣言的 profile」等5主張をクラッシュ込みで反証 | 文書化済み経路では破れず |
| 21 | X21 | profile 変更と floor、vec 再充填、agg key 更新を交錯 | floor/vec/ready の主経路は矛盾なし |
| 22 | X22 | fork の各 phase で crash、app 全損なし、journal 健全 | phase + id で再開位置が一意。問題なし |
| 23 | X23 | app_config の current filter と一括変換 status を同時に保持 | operation record の key 未定義。**S01** |
| 24 | X24 | vec CREATE 後・一部充填で crash → 次 tick | 差集合再充填で欠落を埋める。問題なし |
| 25 | X25 | app.sqlite 単独横断検索、standalone 単独検索 → query embed | app_config / profiles の給源分離が機能。問題なし |
| 26 | X26 | 行削除→再登録→新投入→ledger close | submission_seq high-watermark 継承で衝突しない。問題なし |
| 27 | X27 | fork 中に移動、journal と flag が健全 → bootstrap/walk 回復 | journal 走査が再発見より先に働く。問題なし |
| 28 | X28 | detached client `state=0, batch_job_id=T` → unregister → §21.2 を字義実装 | terminal後即 delete で token sweep を失う。**S02** |
| 29 | X29 | case-only rename、衝突後の sensitive→insensitive 移動 | tie-break と保存名固定で安定。問題なし |
| 30 | X30 | high-watermark、client上限、fork再開、delete最終確認、detached追跡の反証 | 通常経路では破れず |
| 31 | X31 | 相1 / client前計上 / 明示再生成 / preflight の全 INSERT を再作成 | いずれも ledger MAX 継承を要求しており整合。問題なし |
| 32 | X32 | PREPARED〜APP_DONE × app全損・通常 crash | journal が健全なら復旧分岐は一意。問題なし |
| 33 | X33 | server/client × submit_rejected を含む terminal 行列 | 課金される server-side 4xx の記帳分岐がない。**S07** |
| 34 | X34 | §11.2 の LIKE 差替え SQL を SQLite で最小実行 | 文書末尾の条件では `chunk_uid=17` が返る。**S06** |
| 35 | X35 | seq継承・reconcile close・rejected・fork・detached・delete最終確認を反証 | S02以外の主張は破れず |
| 36 | X36 | profile A→B→A、同一 seq の close 再実行 | `ON CONFLICT DO NOTHING` で close は abort しない。問題なし |
| 37 | X37 | building P2→P3→P2、sync_state NULL 化、ready 判定 | 破棄時 NULL 化で空 index ready は防止。問題なし |
| 38 | X38 | fork中移動、HISTORY_CLEARED の commits 非空、journal digest 正常 | 手順1から再開し旧 id 履歴を残さない。問題なし |
| 39 | X39 | register の一時 EIO、別 id root、対象外型、dirfd 操作 | 4分類・raw resolver の分岐が整合。問題なし |
| 40 | X40 | close idempotence、ready母数、fork移動、一時読取不能、query TOCTOU を反証 | S02以外は破れず |
| 41 | X41 | 終端理由×server/client×close 経路の ledger 行列 | 課金される reject provider の server 分岐が欠落。**S07** |
| 42 | X42 | damaged C を除外して A/B が ready → C 復帰 | ready は設定時被覆の宣言として許容される。問題なし |
| 43 | X43 | NFC/NFD/raw無し/collision × case感度 × resolver 3呼出点 | raw resolver の帰結は一意。問題なし |
| 44 | X44 | registered read の置換、standalone read、z unreadable、fork中 read | scoped 規約12と step -1 は矛盾なし |
| 45 | X45 | client中間課金、unknown、期限超、ready、raw restore、z を反証 | S02以外の防御は破れず |
| 46 | X46 | token記帳→載せ直し→job id記帳、b' 後 sweep | 自己記述化と述語で同一 job の再記帳なし。問題なし |
| 47 | X47 | 期限超 Tx の各境界 crash → rotation → detached | 同一 Tx 規範に従えば seq/attempt は整合。問題なし |
| 48 | X48 | in-place restore 前に working が LWW と異なる → 保全 commit → rename | 安定確認/再 lstat により未取込内容を保全。問題なし |
| 49 | X49 | 破損 journal + fork_in_progress あり → 明示解決 → register step2 | flag の new_id と新規 UUID が食い違う。**S03** |
| 50 | X50 | 無id ledger、b' sweep、未来 token、decoder、restore、回復先行を反証 | S03以外は破れず |
| 51 | X51 | 無id記帳、found記帳、client前計上、再作成を同一 target で連続実施 | seq 行 UPDATE / ledger MAX は整合。問題なし |
| 52 | X52 | expired / rejected / client_exhausted / tool_changed → sweep → 明示 retry | terminal と token cleanup の主経路は整合。問題なし |
| 53 | X53 | state=0 server の job が job-list の後続 page にのみ存在 → 先頭 page の正常 200 | `confirmed-absent` に誤分類可能。**S04** |
| 54 | X54 | journal破損、flag有、実体 id=old → 明示解決の各 crash | §21.1 が新 UUID を生成するため flag を解消できない。**S03** |
| 55 | X55 | embeddings 一意・tool generated_at 同時刻・空 markdown を単独検索 | tie-break と FTS-only 縮退が定義済み。問題なし |
| 56 | X56 | G / `\G` / `\\G` / noncanonical 行 → escape→unescape→strict認識 | 一回だけ escape と loose decoder で可逆。問題なし |
| 57 | X57 | b' found 記帳後、ledger commit 前/後で crash → intent dispatch/sweep | terminal 行への自己記述化は state=0 client dispatch と衝突しない。問題なし |
| 58 | X58 | detached client state=0 → terminal化 → 再登録前後の sweep | §21.2 の「記帳後に削除」だけが段階遷移を破る。**S02** |
| 59 | X59 | server-side provider が job creation 4xx にも課金 → submit_rejected → token sweep | sweep が照会・記帳なしで token を消す。**S07** |
| 60 | X60 | strict canonical / object不在 / 手書き slash 全組合せ → chunk | strict認識と loose un-escape の分離は維持。問題なし |
| 61 | X61 | Mistral list の page/page_size、遅延上限未証明 → intent recovery | 完全照会・採用条件が実装不能。**S04** |
| 62 | 自由 | filter変更の operation record を別 key として永続化しようとする | 7-key 契約外。**S01** |
| 63 | 自由 | 同一 profile JSON が tool→embedding の順で到着 | INSERT OR IGNORE が後者 kind を失う。**S05** |

## 第3部 — 新規検出

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| S01 | major | §7「`app_config へ operation record`」／§9.1「**許可 key 集合**」 | app_config の許可 key は7種だけで、operation record の key・値 schema・存在条件がない。任意 key を使えば契約違反、使わなければ crash 後の未完了一括変換を status 判定できない。 | filter変更開始 → 現行 `image_filter` は保存済み → `operation` を保存しようとする → 許可集合外。保存しないまま途中 crash → 次回に未完了を識別できない。 | C8/C11/C12 X13・X23、R23/R28 | `bulk_operation` など単一の明示 key を許可集合に追加し、JCS schema・存在条件（変換中のみ）・消去条件を定義する。 |
| S02 | fatal | §21.2「client … **terminal 記帳後に削除**」／§9.1 detached 削除条件 | §21.2 の短縮記述が、§9.1 の「terminal化 → 4.5 sweep → `intent_token IS NULL` 後に削除」を破っている。 | client 前計上済み `state=0, batch_job_id=T, intent_token=T` → unregister、cancel未確定 → terminal記帳直後に削除 → token sweep が実行できず upload/job 残骸を追えない → 再登録で同一対象を再投入し重複課金。 | P9/P10、C7/C9/C10/C12 X28・X58、M02/R08 | §21.2 を「同一 Tx で terminal化・completed_at 設定、削除は §9.1 の3条件を満たした後だけ」と明記し、即削除表現を削除する。 |
| S03 | fatal | §21.3 破損 journal 解決「journal除去→§21.1 手順2→flag掃除」／§21.1 手順2「UUIDv7 を生成」 | 破損 journal の flag が持つ `new_id` と、§21.1 手順2が新たに生成する ID の対応が定義されていない。flag 掃除は旧 `new_id` 一致だけなので、回復操作が自身で恒久 flag を作る。 | flag=`{old_id=O,new_id=N}`、journal破損 → journalだけ削除 → §21.1手順2が `N'` を生成 → tick は id=`N'` を old/new 以外として保持 → path が fork中のまま永久除外。 | P16、C3/C11/C12 X49・X54、R16 | 明示解決では flag の `new_id` を必ず再利用する、と定義する。新 ID を使うなら flag の `new_id` 更新と marker 書込を耐久的に一手順として定義する。 |
| S04 | fatal | §9.1「job 一覧から metadata の intent_token 一致を探す」「正常応答に無い = confirmed-absent」 | `confirmed-absent` に至る照会が、metadata の完全一致 server filter なのか、全 page の走査なのかを定義していない。Mistral Batch の list API は pagination を持つため、正常な先頭 page だけを読む実装で既存 job を未作成扱いできる。 | job J 作成後・相3前 crash → `state=0,T`。J は list の後続 page → 先頭 page の正常200に Tなし → 期限内 confirmed-absent → 新 token で J2 作成 → J/J2 が双方実行・課金。 | P9/P10、C7/C11/C12 X53・X61。Mistral の list は `page` / `page_size` と metadata filter を公開している。[Mistral Batch API](https://docs.mistral.ai/api/endpoint/batch) | `found/confirmed-absent` を「完全一致 metadata filter の完全な結果」または「全 page/cursor 完走後」に限定する。完走不能・部分応答は必ず unknown。 |
| S05 | major | §4.1「tool/embedding とも同じ profile_record」／§5.7「必須フィールドが互いに排他」 | 排他性を主張するだけで、kind 固有の必須フィールドや hash domain separation が規格化されていない。現在の共通 record 形では同じ JSON/hash が両 kind に合法的に現れ得る。 | tool record H を `profiles(H,kind=1)` で保存 → 同じ record H を embedding として保存 → `INSERT OR IGNORE` で kind=2 が失われる → embeddings は kind=1 profile を指し fsck 不一致、どちらを修復しても他方を壊す。 | P2/P3、C11/C12 X18 | record に必須の `kind` を含めて hash 化する、または `SHA-256("tool\\0" \|\| JCS(...))` のように domain separate する。 |
| S06 | major | §11.2 の後段 LIKE 差替え SQL | 必須と宣言した `c.text IS NOT NULL` が差替え SQL から脱落している。短語 fallback の対象集合が FTS と異なり、annotation のない画像が heading_path だけで出る。 | `agg_chunks(17, text=NULL, heading_path='["図"]')`、eligible に17 → `図` を検索 → 文書後段の `WHERE c.text LIKE ... OR c.heading_path LIKE ...` は17を返す。前段で規定した条件付き SQL は返さない。 | P12、C4/C9/C12 X6・X34、R20 | 差替え SQL を `WHERE c.text IS NOT NULL AND (c.text LIKE :p ESCAPE '\' OR c.heading_path LIKE :p ESCAPE '\')` に統一し、完全な fallback CTE を掲載する。 |
| S07 | major | §8(ii) の「拒否にも課金する provider では記帳」／§9.1 token sweep の `submit_rejected` 無条件除外 | 課金される拒否を client だけ例外扱いし、server-side の job creation/upload 4xx は `submit_rejected` なら無条件に照会・記帳せず token を消す。許可された provider 契約で ledger が欠落する。 | server-side embedding provider が入力検査4xxにも料金を課す → state=3 `submit_rejected` → sweep は照会/記帳なしで掃除・token NULL → 実課金を突合不能。 | P8/P9、C7/C11/C12 X33・X41・X59 | `submit_rejected` 除外を「拒否が非課金と契約上確認済み」に限定する。課金され得る provider は intent_token を batch_job_id とした estimated ledger 行を追記する。 |

## 第4部 — 確認済み・問題なし

以下は今回の監査で検出 0 件でした。

- C2: SQLite DDL の基本文法、FK 列数、rowid を要する FTS external-content 構成、INSERT/DELETE trigger 対。
- C5: OCR 単価・25%・50%・$2.5/1k、768 の参考値扱い、RRF `k=60`、8テーブル表記。
- P1: 三層の真実・全損時損失の6分類と有界性の二分。
- P4: chunks 統一表、CHECK、rowid、embed_hash、commit/vector 非保持。
- P6: OCR 保存変換、canonical img block、preflight、失効処理。
- P7: FTS external-content view、trigger、UPDATE禁止。
- P11: append-only 集約、cursor、逆差集合、sync_state、孤児掃除。
- P13: GC 3集合、fsck、バックアップ、object repair。
- P14: SQLite PRAGMA、migration、権限、auto_vacuum。
- P15: commits/file_versions 不変部分と不採用構成。