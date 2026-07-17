不合格
target.md 全 3135 行を読了 — 最終行: 『```』

## 第 1 部 — 回帰確認 (C9)

対応表で置換済みの旧項目はすべて `superseded (→対応表記載の現行 ID)` と判定した。対応表で現行判定対象となる項目は、下記を除き fixed。

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
| --- | --- | --- |
| S25 | partially-fixed | §9.1 の intent 回復には「`Retry-After が無い 429 / 5xx にも既定の抑止`」「`submit / collect の照会共通`」がある。一方、相 2a の upload 失敗、相 2b の job 作成失敗、state=1 collect の失敗は、いずれも「Retry-After は retry_not_before へ」としか書かず、ヘッダ無し 429/5xx の既定 backoff を規定していない。特に upload/job 作成失敗後は retry_not_before が未設定のまま dirty 起因 tick で即時再試行され得る。 |

fixed: A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S24・S26〜S29（各 superseded 対応を除く）。

superseded は監査プロンプトの対応表どおり。主な最終置換先は、A11→I05/I06/I13/I14、F05/F07/F12/F21/H04/H15/H18/H22→I 系、I 系→J/K 系、J/K 系→L 系、L/M 系→N 系、N/O 系→Q 系、Q 系→R 系、R06/R07/R08/R13/R18/R20/R23/R25→S01〜S19・S28 の現行項目で判定した。

## 第 2 部 — 探索ログ (C12)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
| --- | --- | --- | --- |
| 1 | X1 | 現在版 A を同一 tick 前に編集→削除→次 walk を完全成功させる。 | pending_deletes と最終確認を経るため問題なし。 |
| 2 | X2 | `obj:`・改行・制御文字を含む名前、偽 img block、巨大 annotation を入力する。 | name_invalid、行全体 grammar、escape/実在検証で問題なし。 |
| 3 | X3 | NFD 名のフォルダを case-insensitive と case-sensitive の間で移動する。 | NFC 論理名・保存名固定・再判定規則で問題なし。 |
| 4 | X4 | 時計後退中に同一 ms の複数 commit と再チャンクを行う。 | commit/generated_at の単調規則と tie-break で問題なし。 |
| 5 | X5 | 10 万ファイル・100 万 chunk を想定し、KNN over-fetch と `:limit` 上限を追う。 | k_max、refill、入力上限の規範で問題なし。 |
| 6 | X6 | 2 文字検索、vec0 次元不一致、JCS 大整数を入力する。 | LIKE fallback、vec 再作成、10進文字列規則で問題なし。 |
| 7 | X7 | 旧アプリ writer が migration 中の DB を開く。 | tick.lock 下の user_version 再確認で問題なし。 |
| 8 | X8 | path traversal 名・root swap・外部 symlink を restore/scan に競合させる。 | name 検証、dirfd 相対操作、O_NOFOLLOW で問題なし。 |
| 9 | X9 | objects 保存、metadata Tx、app 更新の各点で容量不足を発生させる。 | 順序、fsck、未参照 object の回収で問題なし。 |
| 10 | X10 | `.folder-history` の手動削除・部分同期・破損 journal を与える。 | damaged/保留/明示解決の分岐で問題なし。 |
| 11 | X11 | profile 変更中に cost_ledger と旧 embedding を残す。 | 台帳不削除、宣言的置換、agg 再構築で問題なし。 |
| 12 | X12 | watch_root 登録→OCR→embed→replicate→検索→解決→履歴表示を通す。 | 入出力の受渡しが定義されており問題なし。 |
| 13 | X13 | register/unregister/fork/restore/drop の入力・失敗時分岐を列挙する。 | X65 の restore fallback を除き問題なし。 |
| 14 | X14 | 429、fp_cache 肥大、削除済みディレクトリを連続観測する。 | retry_not_before、M&S、status 規範はあるが S25 を検出。 |
| 15 | X15 | 主張「intent 回復で server job は最悪 1 回」を採用条件内で反証する。 | 可視化遅延・保持期間の採用条件下では破れず。 |
| 16 | X16 | 2 相 submit、reconcile、profile 切替、upload 掃除を交錯させる。 | 問題なし。 |
| 17 | X17 | register 中断、fork、restore、unregister を tick と競合させる。 | fork 回復先行と lock 規範で問題なし。 |
| 18 | X18 | profiles 欠損、pending delete、app 全損後の ledger を追う。 | fsck・再構築規範で問題なし。 |
| 19 | X19 | 相1直後、相2a直後、相2b直後、相3直前で電断する。 | intent 回復・台帳規範で問題なし。 |
| 20 | X20 | 主張「profile 変更は宣言的収束」を部分 vec/agg 喪失と組み合わせて反証する。 | 差集合再充填・ready gate により破れず。 |
| 21 | X21 | floor、profile、job_missing、app_config 更新を交錯させる。 | 問題なし。 |
| 22 | X22 | fork の各 phase で電断し、別操作を直列実行する。 | journal/flag/recovery で問題なし。 |
| 23 | X23 | cost_ledger、app_config、detached、name_collision を読み手別に追う。 | 問題なし。 |
| 24 | X24 | vec 作成途中 crash、agg wipe 中 crash、client 呼出 crash を再実行する。 | 問題なし。 |
| 25 | X25 | app.sqlite 単独検索、restore 宛先、watch_root 解除後を追う。 | 問題なし。 |
| 26 | X26 | submission_seq、snapshot、client 前計上、floor を総当りする。 | 問題なし。 |
| 27 | X27 | journal 作成から削除まで各境界で fork を再開する。 | 問題なし。 |
| 28 | X28 | unregister/退役/fork から detached を state 0〜3 で処理する。 | cancelled を除き問題なし。 |
| 29 | X29 | case-only rename、NFC 衝突、volume 移動を追う。 | 保存名固定と tie-break で問題なし。 |
| 30 | X30 | 台帳 UNIQUE、client 上限、fork、最小不在時間の主張を反証する。 | 前提内では破れず。 |
| 31 | X31 | 行削除→再作成、reconcile close、submit_rejected を組み合わせる。 | seq 継承・close 規範で問題なし。 |
| 32 | X32 | fork の全 phase × app 全損 × journal 破損を追う。 | 問題なし。 |
| 33 | X33 | server/client × 全 terminal 理由 × detached を台帳行数で追う。 | cancelled を除き 0 または 1 行に収束。 |
| 34 | X34 | selected_files、eligible、LIKE fallback、ready 照合を SQL 形で追う。 | 問題なし。 |
| 35 | X35 | seq 継承、reconcile close、submit_rejected、detached を反証する。 | cancelled を除き破れず。 |
| 36 | X36 | profile A→B→A、detached 採用、item 失敗を同一 seq で追う。 | ON CONFLICT と seq 増分で問題なし。 |
| 37 | X37 | missing/fork/damaged の ready 母数と synced の更新を追う。 | 問題なし。 |
| 38 | X38 | fork 中移動、journal digest、app 全損を組み合わせる。 | 問題なし。 |
| 39 | X39 | 一時読取不能、rebind、対象外型、dirfd 操作を交錯させる。 | 問題なし。 |
| 40 | X40 | ready、距離変更、raw resolver、drop-derivation の主張を反証する。 | 問題なし。 |
| 41 | X41 | 全 close 理由×server/client×記帳経路を追う。 | cancelled を除き問題なし。 |
| 42 | X42 | damaged フォルダ復帰、接続 0→1、building 再変更を追う。 | 問題なし。 |
| 43 | X43 | resolver を NFC/NFD/衝突/不在×case 感度で実行する。 | 問題なし。 |
| 44 | X44 | scoped read、一時 EIO、conflict、step -1 を交錯させる。 | 問題なし。 |
| 45 | X45 | client 中間課金、unknown、期限超、ready、restore の主張を反証する。 | 問題なし。 |
| 46 | X46 | token 記帳→rotation→found/close を seq と batch_job_id で追う。 | 現行 token に対する predicate は問題なし。 |
| 47 | X47 | 期限超 Tx の各境界 crash と detached 化を追う。 | 問題なし。 |
| 48 | X48 | restore 保全 commit、raw resolver、エクスポートを追う。 | 既存 raw の保全は問題なし。 |
| 49 | X49 | 全 §21 操作の前に未完 fork を置く。 | 回復先行規範で問題なし。 |
| 50 | X50 | 無 id 記帳、(b')、detached、escape、restore の主張を反証する。 | X62/X63/X65 以外は破れず。 |
| 51 | X51 | seq 行 UPDATE と phase3/client/detached 採用を交錯させる。 | 問題なし。 |
| 52 | X52 | expired、submit_rejected、client_exhausted、tool_changed を retry/sweep と交錯させる。 | 問題なし。 |
| 53 | X53 | 4 照合点の三値・期限・猶予・記帳・掃除を比較する。 | 問題なし。 |
| 54 | X54 | journal 有無×flag 有無×old/new/第三 ID を総当りする。 | 問題なし。 |
| 55 | X55 | 単独検索で embedding 混在と tool 混在を同時に起こす。 | 問題なし。 |
| 56 | X56 | `G` / `\G` / `\\G`、非 canonical 行、object 不在を往復する。 | 問題なし。 |
| 57 | X57 | 自己記述化済み terminal 行を再投入・sweep・idx_batch_open に通す。 | 問題なし。 |
| 58 | X58 | detached terminal を再登録前後で追う。 | `cancelled` 以外の detached 遷移は問題なし。 |
| 59 | X59 | submit_rejected と拒否課金 provider を組み合わせる。 | 分岐内記帳の規範があり問題なし。 |
| 60 | X60 | encoder/decoder/厳密認識を全組合せで追う。 | 問題なし。 |
| 61 | X61 | provider 採用条件を満たす/満たさない場合を反証する。 | 満たさない provider は採用不可と明記され、内部矛盾なし。 |
| 62 | X62 | 旧 token の job_create_started_at を記録→時計後退→新 token へ rotation→相2b前に crash→回復する。 | T01 を検出。 |
| 63 | X63 | state=1・attempts<上限→unregister の cancel 確定→token 掃除前に再登録→tick を実行する。 | T02 を検出。 |
| 64 | X64 | token 推定記帳後に遅延可視化 job を token sweep で発見する。 | `IN (job id, token)` と自己記述化により二重記帳なし。 |
| 65 | X65 | raw 不在 restore の再 lstat 後、no-replace 非対応 FS で外部プロセスが宛先を新規作成する。 | T03 を検出。 |
| 66 | X66 | 規範・相2a/2b・collect の retry 規則を横断比較する。 | S25 の部分修正を検出。 |

## 第 3 部 — 新規検出 (C1〜C8, C10, C11, C12)

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 | 修正案 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | major | §9.1 DDL: 「`job_create_started_at`…`NULL = 相2b 未着手`」。相1: 「新規 UUIDv7」「batch_job_id は NULL へ戻し」だが job_create_started_at を NULL 化しない。回復: 「起点 = `max(intent_token… job_create_started_at)`」。 | 新 intent_token への rotation 時に前 attempt の job_create_started_at が残る。列の意味が token 世代と対応せず、古い時刻が新 token の伝播猶予・未来 skew 判定を支配する。 | T1 の相2b開始時刻を記録→時計を過去へ補正→T1 が confirmed-absent となり新 token T2 を相1で書く→T2 の相2b前に crash→回復時、残存した T1 時刻を max が採用→未来扱いの estimated 記帳・attempts 消費・rotation を、T2 の job 未作成のまま反復→偽 ledger 行と terminal 化。 | P9 / C10 / C11 / C12-X62 | 相1で新 intent_token を書く全経路（期限超 rotation、通常再投入、明示 retry、profile 数え直し）で job_create_started_at を NULL に戻す。さらに列を token 世代に結び付ける不変条件を明記する。 |
| T02 | major | §9.1 遷移表: 「state=3・attempts < 上限 → 投入対象」「terminal failed = attempts >= 上限」。§21.2: cancel 確定は「state=3 (error='cancelled') + completed_at で terminal 化」。 | `cancelled` を terminal と呼ぶ一方、attempts を上限へ上げないため、再登録前に行が削除されなければ state=3・attempts<上限として自動再投入される。意図された再課金か、明示 retry 必須かが矛盾・未定義。 | state=1、attempts=1/上限3 の OCR job→unregister→cancel 確定で state=3/error=cancelled→token sweep・行削除前に同 repo を register→成果なしの state=3 を submit が通常候補として再投入→cancel で部分課金済みだった job に加え再課金。 | P9 / C7 / C11 / C12-X63 | cancel 確定時に attempts を上限へ設定し明示 retry に限定する、または cancelled を再登録時に自動再投入する明示的な非 terminal 状態として再定義し、台帳・コスト注記・遷移表を一致させる。 |
| T03 | major | §21.4: 「可能なプラットフォームでは…RENAME_NOREPLACE…を用い」とする一方、非対応 FS の検出・安全な fallback・abort 条件を規定しない。直後に「残余窓は…原子的には塞げない」とする。 | no-replace rename 非対応の FS で raw 不在 restore をどう実装するかが一意でない。通常 rename を採れば、再 lstat 後に出現した外部ファイルを履歴化せず上書きできる。 | raw エントリ不在→restore が不在を再 lstat で確認→no-replace 非対応の FS で外部プロセスが同名ファイルを作成→通常の atomic rename が置換→外部ファイルが working copy と履歴の双方から失われる。abort 実装を選ぶ場合も、仕様にその動作がない。 | P16 / C11 / C12-X65 | 対応可否の判定方法と fallback を固定する。安全な no-replace を提供できない FS では restore を拒否して status とし、通常 rename を fallback にしない。対応可能な代替 primitive を使う場合は、その失敗コードと再試行規則を明記する。 |

## 第 4 部 — 確認済みの列挙

確認済み・問題なし:

- C2（標準 SQLite DDL、FK、CHECK、FTS5 external content / trigger / rank=1 integrity-check、主要 CTE の静的整合）
- C3
- C4
- C5
- C6
- C8
- P1〜P8
- P10〜P15