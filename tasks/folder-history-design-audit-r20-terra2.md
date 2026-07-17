不合格
target.md 全 3348 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

第 1 部 — 回帰確認 (C9)

対象 494 項目のうち、下記の superseded 対応および V09・V15 を除く全項目は fixed。

superseded（監査プロンプトの対応表どおり）: F05→I14、F07→I15、F12→I16/I17、F21→I03/I04、H04→I31、H15→I08/I11、H18→I16、H22→I15、A11（遷移詳細）→I05/I06/I13/I14、H02（衝突順）→I32。I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I15→J04、I16/I17→J05/J01、I35→J13〜J16。J04→K01、J06→K02、J03→K10、J10→K09、J13→K16、J16→K13〜K15、I12→K04、D08→K20、A01→K25。K02→L01、K06→L02、K09/K11→L03、K12/K13→L04、K14→L07、J07/K24→L09、K19→L13、K21→L20。L04/L21→M02、L09/L28→M03/M09、L20→M04。M01→N09、M05/L07→N16、M06/K08→N17、M08→N28、M09→N05/N06、M10→N10、M12→N38、M13→N30、M29→N15、L26→N14。N03→O05/O06、N04→O02/O03、N07→O12、N13→O21、N15→O04/O25、N28→O13、N36→O16、N39→O14、N40→O28。O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O13→Q12、O17→Q02、O18→Q23、O19→Q24、O28→Q01、O30→Q37。Q02→R01、Q03→R05、Q04→R02、Q05/Q06→R06、Q06→R07、Q09→R03、Q10→R14、Q12→R04、Q13/Q14→R15/R16。R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06。S06→T09、S07→T05/T06、S11→T07、S19→T03、S20→T01、S23→T18、S24→T02、S25→T04。T03→U04、T08→U03、T10→U01、T11→U05、T16→U02。N23→V05、U01→V01、U03→V07、U06→V02、U11→V04、U24→V03。

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
|---|---|---|
| V09 | not-fixed | §9.1 の `scan_cache` DDL は `verified_at INTEGER NOT NULL` の直後に `PRIMARY KEY` となり、`syntax_fail_count` / `first_failure_at` が無い。一方 §20.5 は「**カウントの実体は scan_cache に永続化**」「`syntax_fail_count / first_failure_at` を記録し (列追加)」と要求する。新規 DB 作成 DDL・migration と規範が不整合。 |
| V15 | partially-fixed | §5.6 は「`text_hash` が変わらなかった chunk はそのまま再利用」と限定済み。しかし §1 に「Markdown は再生成可能 **(99% 一致で可)**」、§5.3 に「旧派生は保持しない (**99% 要件**)」が残る。無条件の 99% 表現が残存している。 |

第 2 部 — 探索ログ (C12)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---:|---|---|---|
| 1 | X1 | 空の登録フォルダ → A を作成・編集・削除して次 tick で scan → LWW と pending_deletes を追跡 | delete は確認後に 1 回だけ確定。問題なし |
| 2 | X2 | `obj:`、偽 img block、制御文字名、symlink を含むフォルダ → scan・chunk 化 | grammar は行全体一致、名前・型は fail-closed。問題なし |
| 3 | X3 | NFD 名のファイルを case-insensitive と case-sensitive ボリューム間で移動 → rebind・walk | NFC と初出表記固定、感度再判定で系列が一意。問題なし |
| 4 | X4 | 同一 ms の複数コミットと時計後退 → created_at clamp・LWW・カーソル同期 | commit_hash tie-break と単調値で収束。問題なし |
| 5 | X5 | 10 万ファイル、100 万 FTS hit → fp・scan_cache・:fts_cap・:k_fetch を適用 | 中間候補は内部上限で抑制。問題なし |
| 6 | X6 | 2 文字クエリ、巨大 size、vec metric 変更 → LIKE fallback・JCS・vec 再作成 | 短語 fallback と文字列化・次元距離照合が定義済み。問題なし |
| 7 | X7 | 旧 DB を新アプリで開く → migration 中クラッシュ → 再起動 | user_version と単一 Tx で再実行可能。問題なし |
| 8 | X8 | path traversal 名、root swap、tmp 残骸 → restore・scan | name 検証、dirfd 相対操作、O_NOFOLLOW が防御。問題なし |
| 9 | X9 | metadata のみを旧バックアップから復元 → tick | step -1 の後退検出、cache 無効化、full resync。問題なし |
| 10 | X10 | `.folder-history` の手動削除・途中同期コピー → register/walk | damaged・conflict・fork 回復への分岐が定義済み。問題なし |
| 11 | X11 | floor 設定中に再チャンク、tool/profile 変更を交錯 → collect | app→metadata の floor 順と profile snapshot で収束。問題なし |
| 12 | X12 | register→scan→OCR→chunk→embed→replicate→検索→restore を通し実行 | 各段の入出力・ロック・復元経路が接続。問題なし |
| 13 | X13 | abandon、drop-derivation、明示 retry、damaged 解決を起動 | 入力・効果・失敗時の動作がカタログ化済み。問題なし |
| 14 | X14 | submit/collect で Retry-After 無し 429 → dirty tick を連続起動 | retry_not_before の既定 backoff が適用。問題なし |
| 15 | X15 | 主張「server 経路の未追跡 job は最大 1」→ 相2b後・相3前クラッシュを反復 | provider 採用条件下で token 照合が既存 job を採用。破れず |
| 16 | X16 | 2 相 submit と共有 upload、reconcile close を交錯 | 全行終端 guard と close の冪等記帳が整合。問題なし |
| 17 | X17 | fork の各 phase でクラッシュ → restore・unregister と競合 | journal と回復先行で操作が反転しない。問題なし |
| 18 | X18 | profiles/pending_deletes/cost_ledger の孤児・喪失を作る | profile fsck、pending 再観測、ledger 不削除が整合。問題なし |
| 19 | X19 | objects 保存後、metadata Tx 後、app 更新前にそれぞれ電断 | objects→metadata→app と collect 冪等吸収で収束。問題なし |
| 20 | X20 | 主張「宣言的 profile 変更はクラッシュ位置を問わず収束」→ vec 再充填途中で停止 | 差集合再充填と毎 tick agg 検査で復帰。破れず |
| 21 | X21 | image_filter 変更と in-flight embed collect を交錯 | chunks 除去後の embedding 孤児掃除で回収。問題なし |
| 22 | X22 | PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE ごとに app 全損 | journal phase と実 id で再開位置が一意。問題なし |
| 23 | X23 | name_collision、invalid_output、detached を status 表示・再登録 | 状態分類と読取側の扱いが定義済み。問題なし |
| 24 | X24 | agg_vec 作成後・再充填途中で停止 → 次 tick | profile 一致でも差集合充填するため欠落を回収。破れず |
| 25 | X25 | app.sqlite のみで横断検索、in-place/export restore、watch_root 解除 | app_config 給源、宛先規則、fp_cache DELETE が揃う。問題なし |
| 26 | X26 | attempts reset、submission_seq 継承、profile snapshot を再投入で交錯 | seq と attempts が分離され、snapshot は相1で保持。問題なし |
| 27 | X27 | fork-journal を持つフォルダを移動し、bootstrap で発見 | journal 走査が再発見より先行。問題なし |
| 28 | X28 | detached の state 0/1/2/3 を再登録前後で追跡 | terminal→掃除→token NULL→削除の段階遷移。問題なし |
| 29 | X29 | case-only rename と NFC 衝突 → restore と LWW を実行 | 初出名固定と raw resolver が同一採用規則を使う。問題なし |
| 30 | X30 | 主張「ledger UNIQUE は正当な再課金を妨げない」→ 行削除後の再登録 | ledger MAX 継承と submission_seq で衝突しない。破れず |
| 31 | X31 | reconcile close、submit_rejected、client_exhausted を順に発生 | floor・記帳・terminal 化の各付随処理が整合。問題なし |
| 32 | X32 | fork phase × journal 破損 × app 全損を全組合せで追跡 | old/new/第三 id・一時読取不能が fail-closed。問題なし |
| 33 | X33 | server/client × 成功/失敗 × attached/detached の記帳行列 | seq と ON CONFLICT により 0 または 1 行。問題なし |
| 34 | X34 | §11.2 SQL、短語 fallback、ready 不一致を組立て | CTE・bind・FTS-only 縮退が整合。問題なし |
| 35 | X35 | 主張「submit_rejected は自動再投入しない」→ retry 後に再拒否 | attempts 上限と明示 retryで循環が有界。破れず |
| 36 | X36 | profile A→B→A と detached 採用を同一 target で実行 | submission_seq と冪等 close が別 attempt を保持。問題なし |
| 37 | X37 | missing/fork/damaged の出入り中に ready を判定 | 接続母数・synced NULL 化・被覆条件が整合。問題なし |
| 38 | X38 | fork 中移動、journal digest 不一致、app 全損を交錯 | journal と flag の役割分担で安全停止。問題なし |
| 39 | X39 | 一時読取不能、別 id root、対象外型を同 tick に観測 | 保留・rebind・absent の境界が一意。問題なし |
| 40 | X40 | 主張「ready は部分 index を通さない」→ P2→P3→P2 を反復 | wipe Tx の synced NULL 化で空 index を通さない。破れず |
| 41 | X41 | 全 terminal 理由 × close 経路で ledger を追跡 | batch_job_id と seq の記帳規則が網羅。問題なし |
| 42 | X42 | damaged フォルダ復帰時に ready 値を追跡 | 接続母数復帰後の再同期が必要になり、部分 index を正常扱いしない。問題なし |
| 43 | X43 | NFC/NFD/collision/raw 無し × restore/delete/fsck を実行 | resolver の採用と raw 無し分岐が一貫。問題なし |
| 44 | X44 | registered/standalone read と step -1 unreadable を実行 | scoped read と regressed/unreadable の分岐が整合。問題なし |
| 45 | X45 | 主張「unknown が二重 job を作らない」→ 一覧 API 429・遅延を注入 | unknown 保持と伝播猶予で載せ直さない。破れず |
| 46 | X46 | token 記帳後に job id を発見 → sweep を再実行 | IN 判別と自己記述化で二重記帳しない。問題なし |
| 47 | X47 | 期限超記帳 Tx の各境界で電断 → retry | 記帳・attempts・rotation が同一 Tx で再実行可能。問題なし |
| 48 | X48 | restore 前に working copy を編集 → 安定確認・保全・上書き | 未取り込み内容は先に通常コミット。問題なし |
| 49 | X49 | 各 §21 操作の直前に未完 fork を残す | 回復先行と破損 journal の例外が一意。問題なし |
| 50 | X50 | 主張「sweep が課金を取りこぼさない」→ b' 前にクラッシュ | sweep 前段が発見・記帳を回収。破れず |
| 51 | X51 | b'・期限超・client・detached で同一行の seq を進める | 行 UPDATE と ledger MAX 継承が整合。問題なし |
| 52 | X52 | expired terminal の token 残存中に unregister と明示 retry | 削除 guard と sweep・retry の順が整合。問題なし |
| 53 | X53 | 4 照合点に found/unknown/confirmed-absent を与える | 期限・猶予・記帳・掃除の共通規則を確認。問題なし |
| 54 | X54 | journal 有効/破損/無 × flag 有無 × old/new/第三 id | 明示解決以外は安全に保留または damaged。問題なし |
| 55 | X55 | tool 混在、embedding 混在、全行未来 generated_at を作る | tool tie-break、KNN 停止、未来値 fallback が定義済み。問題なし |
| 56 | X56 | `G`、`\G`、`\\G`、非 canonical grammar を materialize→parse | escape/un-escape と厳密認識が可逆。問題なし |
| 57 | X57 | b' found 記帳後、batch_job_id 更新前にクラッシュを仮定 | 記帳済み判別と同一 Tx 自己記述化で再駆動可能。問題なし |
| 58 | X58 | detached terminal 行を token sweep 前に再登録 | state・attempts・意図された再課金の記述が整合。問題なし |
| 59 | X59 | 課金する submit_rejected provider と client provider を比較 | 分岐内 seq+1 記帳と sweep 除外が整合。問題なし |
| 60 | X60 | 手書きのエスケープ行・object 不在 hash を全組合せで再解析 | phantom 防止と text 復元を両立。問題なし |
| 61 | X61 | 主張「provider 条件下で偽 expired はない」→ 遅延・保持期限境界を与える | 可視化遅延・保持期間の採用条件で限定済み。破れず |
| 62 | X62 | job_create_started_at 記録後・job 呼出前でクラッシュ | max 起点・相1 NULL 戻し・旧行 migration が整合。問題なし |
| 63 | X63 | cancelled を明示 retry後に再度 unregister | attempts 上限、token sweep、削除条件が整合。問題なし |
| 64 | X64 | token 推定記帳後に別 attempt の job を found | 新 token と発見 job id の述語が別 attempt を吸収しない。問題なし |
| 65 | X65 | no-replace 非対応 FS と EEXIST を使う restore | 再 lstat＋通常 rename の限定 fallback。問題なし |
| 66 | X66 | §9.1/§10/§21.2/DDL/SQL の再掲を突合 | V01〜V20 を除き制約の非伝播なし。問題なし |
| 67 | X67 | terminal token の sweep が恒久 unknown → retry を試す | stalled 表示と abandon が脱出路。問題なし |
| 68 | X68 | cancel→token 残存→明示 retry→再 cancel を反復 | 記帳・掃除・再登録の順が有界。問題なし |
| 69 | X69 | :fts_cap 到達、KNN refill 上限到達で同一 query を再実行 | 打切りと順位が決定論的。問題なし |
| 70 | X70 | Office converter 更新・変換失敗・変換後 oversize を与える | tool profile 分離、convert_failed、入力照合が整合。問題なし |
| 71 | X71 | state=0 載せ直しと client dispatch の token を追跡 | 各経路自身が旧 token の照合・記帳を完了。問題なし |
| 72 | X72 | abandon 後に旧 job が可視化 → 明示 retry | token/job id の IN 判別が二重記帳を防止。問題なし |
| 73 | X73 | convert_failed 後に tool profile を変更 | 別 target_key で独立し、旧 terminal と衝突しない。問題なし |
| 74 | X74 | 新規 app DB を §9.1 の `scan_cache` DDL で作成 → 同一 stat tuple の構文失敗を 3 回記録 | `syntax_fail_count` / `first_failure_at` が存在せず永続化 SQL が失敗。W01 |
| 75 | X75 | 相2b直前の scope A 記録後に認証を scope B へ変更 → intent 回復 | scope 不一致は unknown 保持、恒久時は abandon。問題なし |
| 76 | X76 | abandoned 行を detached→再登録→明示 retry と通す | terminal・token NULL・ledger 記帳が整合。問題なし |
| 77 | X77 | fp 一致の登録フォルダに fork-journal だけを追加 | fp skip 前の journal 検査で回復へ進む。問題なし |
| 78 | X78 | floor 設定済み state=2 token 残存行 → 再投入・中断 | state 2 を含む rotation guard と app→metadata 順で収束。問題なし |
| 79 | 自由 | 同一 `(content_hash, tool_profile_hash)` を手動再生成し、Markdown が大きく変動する応答を得る | 「99% 一致」の測定・閾値未達時の分岐が無い。W02 |

第 3 部 — 新規検出 (C1〜C8, C10, C11, C12)

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 (P#/C#/X#) | 修正案 |
|---|---|---|---|---|---|---|
| W01 | major | §9.1 `scan_cache` は `verified_at` の後に `PRIMARY KEY`。§20.5 は「`syntax_fail_count / first_failure_at` を記録し (列追加)」 | 初期 DDL に必要な永続カウンタ列が無く、構文検証失敗を 3 回/24h で有界化する規範を実装できない。 | 新規 app.sqlite → §9.1 DDL で scan_cache 作成 → 同じ stat tuple の構文失敗を記録 → `syntax_fail_count` 更新/参照 SQL が不存在列で失敗 → 再起動ごとにカウントを失い、永続有界化が壊れる。 | P16 / C2 / C8 / C11 / C12-X74 / V09 | `scan_cache` の初期 DDL と migration に両列を追加し、tuple変更・検証成功時の reset と、一時読取失敗・安定確認失敗を非計数とする規則を同じ節で明記する。 |
| W02 | minor | §1「Markdown は再生成可能 **(99% 一致で可)**」、§5.3「旧派生は保持しない (**99% 要件**)」。§5.6 は「text_hash が変わらなかった chunk はそのまま再利用」 | 無条件の 99% 表現に比較尺度・閾値未達時の動作が無く、現在の内容 hash に基づく限定的な再利用規範と混在している。 | 同一原本・同一 tool を明示再生成 → 有効だが旧 Markdown と 70% しか一致しない LLM 応答 → §5.3 は無条件置換を要求する一方、§1 の 99% 要件をどう判定・処理するかが未定義。 | P13 / C1 / C5 / C11 / C12-自由 / V15 | §1・§5.3 の 99% 表現を削除し、再利用効果は「text_hash が変わらなかった chunk のみ再利用」と統一する。品質閾値を要件化するなら測定法と未達時の遷移を別途定義する。 |

第 4 部 — 確認済みの列挙

C3、C4、C6、C7、C10 は確認済み・問題なし。

P1〜P12、P14、P15 は確認済み・問題なし。