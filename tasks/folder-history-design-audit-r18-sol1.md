不合格
target.md 全 3207 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第1部 — 回帰確認（C9）

全450項目を判定した。C9のsuperseded対応表に列挙された旧項目・旧部分項目は、すべて指定どおり `superseded (→対応先)`。それ以外は、下記2件を除く448件が `fixed` または `superseded` である。

| ID | 判定 | 根拠（両側の記述） |
|---|---|---|
| T10 | partially-fixed | §6のOffice変換規範は「upload_id列・filenameへのintent_token埋込は『実際にuploadしたbytes』（変換物）」「原本はuploadしない」と修正済み。しかし同節のBatch入力は「JSONLの各行はupload済み原本のfile idを参照する」と再掲し、Office文書では存在しない原本upload IDを要求している。 |
| T16 | partially-fixed | §11.2の入力契約には「fts_hits…内部上限（`LIMIT :fts_cap`）」がある一方、掲載された完全SQLの`fts_hits`は `WHERE agg_chunk_fts MATCH :query` の直後にCTEを閉じ、上限を適用していない。§19ではさらに未導入の将来策として別名`:k_fts`を記載している。 |

## 第2部 — 探索ログ（C12）

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | 現在版H0 → tick間に編集・削除 → 2回の完全walkと30秒経過 → deleteコミット | 問題なし |
| 2 | X2 | 本文に`G`、`\G`、不正hashの`obj:`、実体なし画像参照 → materialize → parse | 可逆un-escapeされ、phantom画像は生成されない。問題なし |
| 3 | X3 | NFD物理名をNFC論理名で履歴化 → case-insensitiveからsensitive volumeへ移動 → 再walk | resolver・case再判定・系列分裂が決定的。問題なし |
| 4 | X4 | 最新commit時刻より時計を後退 → 同一msで複数変更 → commit作成 | `latest+1`とcommit_hash tie-breakでLWWが決まる。問題なし |
| 5 | X5 | 100万chunkが同じ語に一致 → `:limit=20`、`:fts_cap=1000`で掲載SQLを実行 | 上限がSQLに無く全件rank対象。U02 |
| 6 | X6 | SQLite 3.51のin-memory DBへmetadata/app/aggの通常DDLを適用 → trigger・cascade・FK・FTS integrity-checkを実行 | FTS hit=1、cascade後子行=0、FK違反=0。DDL部分は問題なし |
| 7 | X7 | 旧版の`state=0, intent_token≠NULL`行 → `job_create_started_at`追加migration → 起動 | token時刻backfillと同一Txのversion更新で収束。問題なし |
| 8 | X8 | `../x`、NUL、`.folder-history`を含む論理名 → restore要求、権限逸脱も発生 | name_invalid拒否、DACL/mode修復までfail-closed。問題なし |
| 9 | X9 | object保存、metadata Tx、app closeの各直前でディスク満杯 | tmp残骸・未参照object・state未closeへ限定され、次tick/fsckで回収。問題なし |
| 10 | X10 | `.folder-history`手動削除、metadataのみ旧版復元、同期中の部分コピー | damagedまたはstep -1 regressedとなり、無言利用されない。問題なし |
| 11 | X11 | NFC変換、FTS view化、floor付き再チャンクを連続実行 | app floor先行とDELETE→INSERTにより成果短絡・FTSが整合。問題なし |
| 12 | X12 | watch_root追加 → register → commit → OCR → chunk → embed → replicate → search → restore | 各出力が次段入力へ接続し、通常経路は完走。問題なし |
| 13 | X13 | 対応Office文書の決定論的変換だけが失敗 → status/error遷移を全文から探索 | 変換失敗の分類・遷移が未定義。U04 |
| 14 | X14 | submit/collect/intent照会がRetry-Afterなし429を反復 → cache行も増減 | 共通backoffとM&S/incremental vacuumで有界。問題なし |
| 15 | X15 | 主張5件（二相収束、GC安全、ready完全性、偽delete防止、FTS候補上限）をクラッシュ・破損・大量hitで反証 | 前4件は破れず。FTS候補上限は掲載SQLで破れた。U02 |
| 16 | X16 | 1 repository内JSONL分割 → 相1/2/3各境界で中断 → reconcileとfloorを交錯 | tokenをjob単位にすれば既存規範で収束。問題なし |
| 17 | X17 | register途中クラッシュ → fork → unregister → 再登録 → restore | tick.lockと操作カタログにより順序が一意。問題なし |
| 18 | X18 | profile行改変、pending_deletes喪失、cost_ledger保持のままapp再構築 | fsck修復、delete再計数、ledger下限性が保たれる。問題なし |
| 19 | X19 | object rename後、metadata commit後、相2b後、fork各phase後に電源断 | fsync・二相回復・journal phaseで収束。問題なし |
| 20 | X20 | 主張「server未追跡job≤1」を相1直後・job作成直後・相3直前の反復で反証 | 採用条件を満たすproviderでは破れず。問題なし |
| 21 | X21 | profile A→B、floor設定中の再チャンク、vec部分充填クラッシュ | profile成果判定、floor引上げ、差集合再充填で収束。問題なし |
| 22 | X22 | forkのPREPAREDからAPP_DONEまで各phaseでクラッシュし、途中でフォルダ移動 | journal発見パスとphase/id表で一意に再開。問題なし |
| 23 | X23 | cost_ledger NULL額、detached、name_collision、name_invalidを各readerへ入力 | 各状態の表示・削除条件が定義済み。問題なし |
| 24 | X24 | 主張「vec差集合」「agg毎tick検査」「client attempts有界」を部分充填・次元変更・呼出中断で反証 | いずれも破れず。問題なし |
| 25 | X25 | app.sqliteだけで横断検索 → delete版/content_hash単独restore → watch_root解除 | query profileと宛先規則、folders起点walkが定義済み。問題なし |
| 26 | X26 | submission_seq、attempts、snapshotをserver/client/detached経路で交錯 | seq非リセット、snapshot不変、MAX継承が整合。問題なし |
| 27 | X27 | fork journal書込から削除まで全境界で停止し、app全損も挿入 | 層1 journalのみで再開可能。問題なし |
| 28 | X28 | detachedをstate 0/1/2/3別に生成 → collect → cleanup → 再登録 | payload破棄、記帳、段階削除、再投入が定義済み。問題なし |
| 29 | X29 | case-only rename、NFC衝突、sensitive→insensitive移動 | 初出表記固定とBINARY優先tie-breakで決定的。問題なし |
| 30 | X30 | 主張6件（seq継承、client有界、fork再開、case固定、30秒delete、detached記帳）を反証 | いずれも破れず。問題なし |
| 31 | X31 | batch行削除後にledger MAXから再生成 → reconcile closeを再実行 | seq衝突せず、ON CONFLICTは同一課金だけを吸収。問題なし |
| 32 | X32 | 4 fork phase × 通常クラッシュ/app全損/journal破損を全組合せ | 第三ID・読取不能を含め帰結が定義済み。問題なし |
| 33 | X33 | server/client × 成功・失効・timeout・missing・invalid・profile変更等をclose | 各実行済みattemptが0または1 ledger行へ着地。問題なし |
| 34 | X34 | selected_files現在版SQLとFTS部分をin-memory実行し、`:fts_cap=2`相当で5 hitを投入 | 掲載CTEは5件すべてを返しcapを無視。U02 |
| 35 | X35 | 主張「seq再作成衝突なし」「reconcile記帳」「reject自動再投入なし」「fork再開」等を反証 | 破れず。問題なし |
| 36 | X36 | profile A→B→Aで同一seqをterminal/reconcileが再観測 | ON CONFLICT DO NOTHINGでcloseが継続。問題なし |
| 37 | X37 | connected/missing/damaged各folderのsynced値をP2→P3→P2で追跡 | wipe時NULL化と接続母数で空readyを防ぐ。問題なし |
| 38 | X38 | HISTORY_CLEARED中に移動・旧IDでcommit追加 → bootstrap | commits非空検査で手順1へ戻る。問題なし |
| 39 | X39 | register対象が一時EIO、旧rootが別ID、delete対象がFIFO | 保留・rebind・absentの分類が一致。問題なし |
| 40 | X40 | 主張7件（冪等close、ready、fork移動、一時読取、型置換、query TOCTOU、距離変更）を反証 | いずれも破れず。問題なし |
| 41 | X41 | 全終端理由をcollect/reconcile/detached/client再実行前記帳へ投入 | ledger値規則とseqが一意。問題なし |
| 42 | X42 | damaged Cを除外してA/Bでready → C復帰 → 次Replicate | Cの未完了は通常の部分性としてstatus化され、差集合で追随。問題なし |
| 43 | X43 | resolver3呼出点 × NFD/NFC/衝突/不在 × case感度を追跡 | raw採用規則が共通。問題なし |
| 44 | X44 | 登録済みpath差替え、standalone copy、step -1 unreadableを実行 | conflict/provenance/保留が分離。問題なし |
| 45 | X45 | 主張8件（client記帳、unknown二重化、期限超、ready、resolver、scoped read、step -1等）を反証 | 破れず。問題なし |
| 46 | X46 | token記帳→job ID発見→sweep再訪→行削除→MAX継承 | IN述語と自己記述化で二重記帳しない。問題なし |
| 47 | X47 | `state=0, token=T, job_create_started_at=NULL` → confirmed-absent → atomic rotationを試行 | T08ガードと終端限定sweepが循環。U01 |
| 48 | X48 | 未取込working変更を持つin-place restore → 外部編集をrename直前に挿入 | 保全commitと再lstatで中止。問題なし |
| 49 | X49 | 各§21操作の直前に未完forkを置き、journal破損も試す | 回復先行または唯一の明示解決例外へ着地。問題なし |
| 50 | X50 | 主張8件（無ID記帳、述語、sweep回収、detached期限、未来token、escape、restore、回復先行）を反証 | いずれも破れず。問題なし |
| 51 | X51 | no-ID、found、detached、clientの各seq+1を同一行で連続実行 | 通算seqが単調でMAX継承も整合。問題なし |
| 52 | X52 | expired terminal → unregister → sweep → 再登録 → 明示retry | attempts上限とtoken NULL条件により段階遷移。問題なし |
| 53 | X53 | intent、detached、b'、sweepの4照合点をfound/unknown/absent別に比較 | 照合規則自体は対称。ただしstate=0からのrotation出口はU01 |
| 54 | X54 | journal有効/破損/無 × flag有無 × ID old/new/第三/読取不能 | 全組合せに回復・保留・damagedが割り当て済み。問題なし |
| 55 | X55 | embeddings混在、tool生成時刻tie、一括変換後の旧tool最新化 | KNN停止と決定的FTS選択の非対称が明示済み。問題なし |
| 56 | X56 | 非canonical `![diagram](obj:see appendix)` をescape→un-escape | 緩いdecoderで原文へ戻る。問題なし |
| 57 | X57 | b' found記帳後、一覧からjob消滅 → sweep再訪 | batch_job_id自己記述化によりtoken側で再記帳しない。問題なし |
| 58 | X58 | detached terminal化直後に同repositoryを再登録 | state=2/3の成果なし再投入は意図されたコストとして追跡。問題なし |
| 59 | X59 | 課金するproviderでsubmit_rejectedを2回、間に明示retry | 各拒否でseq+1され、2行とも記録。問題なし |
| 60 | X60 | G、`\G`、`\\G`、不正hash、object不在の全組合せを往復 | 可逆性・phantom防止・厳密認識が両立。問題なし |
| 61 | X61 | 主張6件（1Tx期限処理、自己記述化、detached、reject掃除、escape、current_tool）を反証 | 各主張は破れず。provider採用条件も明示。問題なし |
| 62 | X62 | 相2b直前記録後クラッシュ、rotation、時計後退、migration旧行を追跡 | phase1 NULL戻しとmigration backfillで旧時刻汚染を防ぐ。問題なし |
| 63 | X63 | cancel確定 → 再登録 → retry → 再unregisterを反復 | attempts=max、seq単調、ledger各attempt1行。問題なし |
| 64 | X64 | token推定記帳後に遅延可視化された同一jobをsweep found | `IN(job id, token)`で重複を吸収。別attemptは別token/seq。問題なし |
| 65 | X65 | no-replaceがEINVAL、次にEEXIST、最後に通常rename fallback | 非対応判定、再lstat、中止条件が一意。問題なし |
| 66 | X66 | 規範、要約、完全SQL、DDLコメントの再掲を横断比較 | Office upload ID矛盾U03、FTS cap非伝播U02を検出 |
| 67 | X67 | 相2a一時失敗で`state=0,T` → 次tick confirmed-absent → 再投入 | rotationガードが終端限定sweepを要求して永久停止。U01 |
| 68 | X68 | cancel→明示retry→再cancelを2周期実行し、各回cleanupを挿入 | token NULL後に新seqへ進み、二重記帳なし。問題なし |
| 69 | X69 | 共通語5件、`:limit=1`、`:fts_cap=2`で完全SQLとRRF入力集合を確認 | capがSQLに無く5件rank。別名`:k_fts`も残る。U02 |
| 70 | X70 | Office原本→変換PDF→upload→JSONL作成、および暗号化文書の変換失敗 | upload ID矛盾U03、失敗遷移欠落U04 |
| 71 | 自由 | in-memory FTSへ5 hit → 掲載`fts_hits`を実行 → 明示cap版と比較 | 掲載版5件、cap版2件。U02を再現 |
| 72 | 自由 | in-memoryで`state=0, token=T`を1行作成 → 「全行終端」sweep候補を算出 | sweep候補0、rotationガード対象1。U01を再現 |

## 第3部 — 新規検出（C1〜C8、C10〜C12）

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| U01 | major | §9.1相1「intent_tokenが非NULLの行…token sweep…完了してから相1」、同節sweep「intent_token非NULLかつ同token全行終端」 | rotationガードが現在処理中の`state=0` intentにも適用されるが、sweepは終端行だけを対象とするため自己循環する。相2a失敗・相2b前クラッシュから再投入不能になる。 | 成果なし・行なし → 相1で`state=0,T`、`job_create_started_at=NULL` → 相2a一時失敗 → 次tickの一覧はconfirmed-absent → 新tokenで相1へ戻ろうとする → Tのsweepを要求 → 当該行がstate=0なので全行終端を満たさず永久停止 | P9 / C7 / C10 / C11 / C12 / X47 / X53 / X67 | stale tokenガードを閉じたlifecycle（state 2/3等）に限定する。現在のstate=0 intentは既存の三値・期限判定から直接、同一Txのrotationへ進める。処理を`recover_current_intent`と`retire_stale_token`に分離する。 |
| U02 | major | §11.2完全SQLの`fts_hits`、同節「内部上限（LIMIT :fts_cap）」、§19「上限（:k_fts）導入」 | 規範上のcapが実行可能SQLに無く、`:fts_cap`をbindしても全FTS hitをrank・sortする。大量一致で一時領域・メモリ枯渇を起こし得る。さらに将来策として別名`:k_fts`が残り、実装契約が分裂している。 | 100万eligible chunkが共通語に一致 → `limit=20, fts_cap=1000` → 掲載SQLを実行 → 100万行をROW_NUMBER/RRF入力へ展開 → resource exhaustionまたは著しい遅延 | P12 / C4 / C5 / C6 / C11 / C12 / X5 / X15 / X34 / X66 / X69 | 完全SQLに決定的な候補CTEを追加し、`ORDER BY bm25(...), chunk_uid LIMIT :fts_cap`で切ってからROW_NUMBERを付ける。bind名を`:fts_cap`へ統一し、cap到達時の部分結果statusも定義する。 |
| U03 | major | §6「変換物をupload・原本はuploadしない」と「JSONLの各行はupload済み原本のfile idを参照」 | Office文書ではupload済み原本IDが存在しない。同一節の二規範を同時に実装できず、job作成不能または変換前Office原本の誤投入になる。 | DOCX原本D → converterでPDF P生成 → PだけuploadしてID U取得 → JSONL生成規範が「原本Dのupload ID」を要求 → ID不存在でjobを作れない、またはDを追加uploadしてT10違反 | P6 / C1 / C6 / C10 / C11 / C12 / X66 / X70 | 「JSONLは実際にuploadしたOCR入力のfile idを参照。PDF/画像は原本、Officeは変換物」と統一し、upload_idとtoken filenameも同じ実体を指すと明記する。 |
| U04 | major | §6 Office変換規範、preflightの`unsupported_format`/`oversize`、§9.1相2aのupload失敗分岐 | 対応Office形式の変換処理が失敗した場合の分類、batch_requests状態、attempts、backoffが未定義。変換はupload前なので相2a失敗規則も適用できず、実装者ごとにterminal化・無限retry・黙殺へ分岐する。 | magic上は対応DOCX、512MB以下 → パスワード保護またはconverter欠落でPDF生成失敗 → unsupportedでもoversizeでもupload失敗でもない → 次状態が定まらず、毎tick再試行または無表示停止 | P6 / C1 / C7 / C8 / C11 / C12 / X13 / X70 | 永続的内容エラーは`conversion_failed` terminal marker＋attempts上限、converter不在・I/O等の一時失敗はstatus＋retry_not_beforeと定義する。tool profile適用前に固定converter版の利用可能性も検証する。 |

## 第4部 — 確認済みの列挙

- C1〜C12:

  - C2: metadata/app/aggの通常DDL、GENERATED列、WITHOUT ROWID、FK列数、FTS view・trigger、rank=1 integrity-checkを確認済み・問題なし。
  - C3: 文書内の§参照を確認済み・問題なし。
  - C1: P6、P9/P10、P12にU01〜U04あり。
  - C4: U02あり。
  - C5: U02のcap導入時期・名称不一致あり。料金、+25%、768参考値、RRF 60、8テーブルは確認済み・問題なし。
  - C6: U02、U03あり。その他のtarget_key、chunk_type/target_type、obj、embed_hashは確認済み・問題なし。
  - C7: U01、U04あり。
  - C8: U04あり。
  - C9: T10、T16がpartially-fixed。
  - C10: U01、U03あり。
  - C11: U01〜U04あり。
  - C12: X1〜X70をすべて実行し、U01〜U04を検出。

- P1〜P16:

  - P1〜P5: 確認済み・問題なし。
  - P6: U03、U04あり。
  - P7〜P8: 確認済み・問題なし。
  - P9〜P10: U01あり。
  - P11: 確認済み・問題なし。
  - P12: U02あり。
  - P13〜P16: 確認済み・問題なし。