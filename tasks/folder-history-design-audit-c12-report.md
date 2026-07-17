# folder-history 設計書 C12 探索型監査報告

## 判定

**不合格**。

- 対象文書: `docs/research/folder-history-sqlite-design.md`（2,657 行、r13 修正適用済み版）
- 探索シナリオ: **50 件**（X1〜X45 を各 1 件以上、自由探索 5 件）
- 新規検出: **fatal 7 件・major 5 件・minor 2 件**（O01〜O13）
- fatal/major が存在するため、合格基準を満たさない

指摘は文書内の規範と状態遷移だけを根拠にしている。一般的ベストプラクティスや §18/§19 で決着済みの設計選択そのものは監査対象外とする。

---

## 第 1 部 — 探索ログ（C12）— 50 シナリオ

重心は X41〜X45（r12 修正の相互作用・記帳経路の網羅行列・ready 母数と synced の動態・raw 解決の全数・scoped 規約 12 と step -1）と、それらが開けた周辺領域である。

| # | 観点 (X# / 自由) | シナリオ（初期状態 → 操作列 → 各ステップの状態変化） | 結果 |
|---:|---|---|---|
| 1 | X1 | 初期: current=H1 の a.pdf が OCR state=1。操作: 1 tick 内に H2 へ編集 → 次 tick 前に削除 → 完全 walk を 2 回。変化: 1 回目 walk は absent → `pending_deletes` 挿入; OCR collect は H1 派生を着地; 30 秒後 2 回目 walk で delete commit (`commits`/`file_versions` 挿入)、`scan_cache`/`pending_deletes` 削除。 | 問題なし |
| 2 | X2 | 初期: OCR 本文に偽 `![x](obj:<hash>)` 行と annotation 値に `-->` 風文字列。操作: §6 materialize → §7 解析。変化: 行頭 `\` エスケープ + `obj:<hash64>` の厳密一致 + 画像実在検証により偽参照は image chunk 化されない。 | 問題なし |
| 3 | X3 | 初期: APFS で NFD 物理名のファイルを追跡。操作: ext4 へ移動・rebind → walk → restore/fsck。変化: §20.5 の論理名→raw 解決により NFC 論理名から NFD 実体へ一貫して解決。 | 問題なし |
| 4 | X4 | 初期: 壁時計を未来に進めた状態。操作: UUIDv7 intent T で相 1 → job 作成 → 相 3 前 crash → プロバイダ失効 → 時計を現在に戻す → confirmed-absent。変化: UUIDv7 時刻成分で年齢が負になり、失効済み attempt が期限内扱いされ、再投入または無記帳。 | **O06 を検出** |
| 5 | X5 | 初期: 100 万 chunk。操作: 画像フィルタ変更で全再チャンク → replicate 中に ENOSPC。変化: 各 Tx rollback、`markdown_documents.generated_at` 差集合で次 tick が再駆動。 | 問題なし |
| 6 | X6 | 初期: 日本語 2 文字 query「検索」。操作: 検索実行。変化: trigram は 3 文字未満で沈黙 → §11.2 の LIKE fallback（`:like_pattern` 分離・`instr(lower(...))` 両列）へ決定論的に落下。 | 問題なし |
| 7 | X7 | 初期: schema v1 DB。操作: v2 migration の DDL 後、user_version 更新前に crash。変化: `BEGIN IMMEDIATE` 内なので DDL と version が同時 rollback、再試行可能。 | 問題なし |
| 8 | X8 | 初期: 復元対象に `../../secret`。操作: in-place restore。変化: `file_name` 検証（`name_invalid`）+ root_path 正規化 join + `O_NOFOLLOW` で外部脱出を拒否。 | 問題なし |
| 9 | X9 | 初期: 通常運転中。操作: objects 書込 / metadata Tx / app Tx の各点で ENOSPC/crash を発生させる。変化: 未参照 object、未コミット Tx rollback、成果短絡で次 tick が差集合から収束。 | 問題なし |
| 10 | X10 | 初期: `.folder-history` のみ手動削除、fp は一致。操作: 次 walk。変化: marker 不在を fp skip 対象外の規約 12 発見で検知 → `damaged` 扱い、自動初期化しない。 | 問題なし |
| 11 | X11 | 初期: OCR 本文にリテラル `\\![x](obj:<hex64>)`。操作: §6 materialize → §7 解析。変化: 行頭が `\\` のため materialize はエスケープせず、parser の un-escape で `\` を 1 つ除去し、`\![x]...` から `\![x]...` ではなく `![x]...` へ改変。 | **O13 を検出** |
| 12 | X12 | 初期: 空フォルダ。操作: register→scan→OCR→chunk→embed→replicate→横断検索→§12 解決→restore。変化: 受渡し ID と各段の入力が §6→§7→§8→§9.3→§11→§12→§21.4 で一貫。 | 問題なし |
| 13 | X13 | 初期: active watch_root 内のフォルダ R。操作: unregister → folders 削除 → 次 walk。変化: `.folder-history` marker が残るため次 walk で再発見・再登録。文書はこれを規約 7-f のトレードオフとして明記。 | 問題なし（意図された挙動） |
| 14 | X14 | 初期: submit / collect 両方で 429。操作: 複数 tick。変化: `retry_not_before` (provider・kind 別) へ永続化、`attempts` は消費しない。 | 問題なし |
| 15 | X15 | 主張=「意図回復・単調時刻・escape・bounded refill・短 query が各事故を防ぐ」。試行=job 作成直後 crash、時計後退、偽 obj、部分 vec、2 文字 query。破れた？ いいえ。 | 破れず |
| 16 | X16 | 初期: upload U1 が未清掃。操作: U1 削除が 429 → 規範どおり「続行」→ U2 を同一 `upload_id` 列へ上書き。変化: U1 handle が `batch_requests.upload_id` 列から失われ、TTL まで追跡不能。 | **O07 を検出** |
| 17 | X17 | 初期: 未登録フォルダ。操作: register 手順 2 途中 crash。変化: 不完全 `.folder-history` → `damaged` → 原本非接触のため再実行は安全。 | 問題なし |
| 18 | X18 | 初期: `profiles` 行が改竄。操作: fsck 実行。変化: hash/参照整合検出 → 同一 metadata Tx で DELETE→INSERT 置換。 | 問題なし |
| 19 | X19 | 初期: 通常運転。操作: dir fsync 適用点を網羅（objects prefix/tmp/fork journal/repository-id 書換え）。変化: 各書込点で dir fsync が規定されている。 | 問題なし |
| 20 | X20 | 主張=「server 経路の重複課金 ≤ job 1 回分」。試行=相 2b 直後・相 3 直前の crash を反復。破れた？ いいえ。 | 破れず（server 限定） |
| 21 | X21 | 初期: state=0 の in-flight 行。操作: 相 1 → crash → intent 回復。変化: `profile_hash`/`profile_record` snapshot は不変、`upload_cleaned=0` リセット。 | 問題なし |
| 22 | X22 | 初期: fork phase=ID_WRITTEN 後。操作: crash → 次 tick 前にユーザーが `unregister(old)` を実行 → 次 tick 回復。変化: 回復ルーチンが新 folders 行を再 INSERT し、後発の unregister を反転。 | **O14 を検出** |
| 23 | X23 | 初期: ledger MAX=7、detached 行あり。操作: 行削除→再登録→再投入。変化: `submission_seq` は ledger から継承され 8 へ、UNIQUE 衝突なし。 | 問題なし |
| 24 | X24 | 主張=「vec 差集合再充填はどの crash 位置でも欠落を埋める」。試行=CREATE 後 A のみ vec 書込後 crash。破れた？ いいえ。 | 破れず |
| 25 | X25 | 初期: app.sqlite のみ（フォルダ未接続）で agg/embeddings 行あり。操作: 横断 query。変化: `app_config.embedding_profile` から query vector を構成、`content_hash` 単独 restore は宛先要請で拒否。 | 問題なし |
| 26 | X26 | 初期: server 経路 state=0、`batch_job_id=NULL`。操作: 保持期限超 → confirmed-absent → terminal 記帳。変化: `cost_ledger.batch_job_id` は DDL 上 `NOT NULL` だが、規範は `NULL+estimated` と要求 → `NOT NULL constraint failed`。 | **O01 を検出** |
| 27 | X27 | 初期: fork journal phase=PREPARED〜APP_DONE。操作: 各境界で crash → 再開。変化: journal phase + 実体 repository-id から再開位置が一意に定まり、全 DELETE は冪等。 | 問題なし |
| 28 | X28 | 初期: 相 2b 後 crash → unregister で detached state=0 (server, `batch_job_id=NULL`)。操作: 長期停止 → confirmed-absent。変化: detached には UUIDv7 期限判定がなく、作成済み job の失効を未作成と断定して削除。 | **O04 を検出** |
| 29 | X29 | 初期: case-insensitive volume で `Report.pdf`。操作: case-sensitive volume へ rebind。変化: `report.pdf` も追加され系列分裂、文書はこれを「意図された挙動」と明記。 | 問題なし |
| 30 | X30 | 主張=「ledger UNIQUE は正当な再課金を妨げない」。試行=ledger seq=7 の旧行を残し target を再登録。破れた？ いいえ。 | 破れず |
| 31 | X31 | 初期: terminal seq=8。操作: profile 変更し再投入。変化: `attempts` は profile 内で reset、`seq` は維持され次 attempt=9。 | 問題なし |
| 32 | X32 | 初期: client 前計上済み state=0。操作: 恒久 4xx → `submit_rejected` → backup から state=0 復元 → 成果あり → reconcile close。変化: `batch_job_id` 非 NULL なので (b) が estimated 記帳 → 未実行 attempt が課金化。 | **O05 を検出** |
| 33 | X33 | 初期: 大容量 repo。操作: Batch JSONL 行数上限到達。変化: 1 job = 1 repository により `custom_id` 衝突回避。 | 問題なし |
| 34 | X34 | 初期: §11.2 の完全 SQL。操作: LIKE fallback・ready 不一致・`at_hash=FF`・limit 境界を実行。変化: SQLite で構文成功、FTS+vec 融合の RRF も決定論的。 | 問題なし |
| 35 | X35 | 主張=「seq 継承・reconcile 記帳・submit_rejected・fork・detached・delete stat が規範どおり」。試行=通常系列 + reject 境界。破れた？ いいえ。 | 破れず |
| 36 | X36 | 初期: profile A→B→A。操作: collect profile_changed 記帳 → reconcile close。変化: 同一 seq に `INSERT ... ON CONFLICT DO NOTHING` が衝突を吸収、close Tx abort しない。 | 問題なし |
| 37 | X37 | 初期: A/B/C が ready=P、C が damaged。操作: P2→P3→P2。変化: agg 破棄 Tx が `synced_profile_hash` を全行 NULL 化し、damaged 復帰後の古い値が ready を誤らせない。 | 問題なし |
| 38 | X38 | 初期: fork phase=HISTORY_CLEARED、id=old、commits 非空。操作: フォルダ移動 → 次 tick で journal 発見。変化: commits 非空を検出 → 手順 1 から冪等に再実行。 | 問題なし |
| 39 | X39 | 初期: register EIO / 同 root 別 id / symlink 置換 / detached 再登録。操作: 各ケースを tick。変化: 4 分類・型判定・PK 共有が通常系列で収束。 | 問題なし |
| 40 | X40 | 主張=「close・ready・fork 移動・EIO・query hash・metric 変更が安全」。試行= billing 系 + profile 照合。破れた？ X41〜X45 で詳細。 | 一部破れ（O02/O03 参照） |
| 41 | X41 | 初期: server state=1 で success/expired/timeout/missing/invalid/item failure/profile_changed。操作: 各 close 再実行 + 期限超 confirmed-absent を反復。変化: 同一 seq は 1 行だが、期限超の「記帳してから載せ直し」は原子的でなく、crash 間に seq が増殖。 | **O02・O03 を検出** |
| 42 | X42 | 初期: client seq=n で呼出中 crash。操作: 再実行前に旧 seq を terminal 記帳 → seq=n+1 で再実行 → 上限到達。変化: 中間 attempt は各 1 行、client_exhausted 時点で未記帳は直前 seq のみ。 | 問題なし |
| 43 | X43 | 初期: server 相 2b 後 crash。操作: job 一覧で found。変化: `attempts`/`seq`/`submitted_at` を更新後に回収。 | 問題なし |
| 44 | X44 | 初期: server state=0。操作: job 一覧が 429/断。変化: `unknown` で state=0 保持、載せ直しは発生しない。 | 問題なし |
| 45 | X45 | 主張=「client 中間記帳・unknown・期限超・b'・ready・raw・scoped read・step -1 が安全」。試行=8 主張を反証。破れた？ ready は破れず; 期限超/b' は O01〜O04; raw/scoped/step-1 は O10〜O12。 | 一部破れ |
| 46 | 自由 F1 | 初期: LWW=A、前 tick 直後に working=B。操作: 旧版 C を in-place restore。変化: restore は working B を保存せず C で上書き; 次 tick は C を検出し B は objects・履歴両方から消失。 | **O08 を検出** |
| 47 | 自由 F2 | 初期: 過去版のみ H、backfill OFF。操作: drop-derivation → 明示再生成。変化: `markdown_documents` 行消失後は `floor_generated_at` の基準となる `generated_at` がなく、backfill OFF では候補にならない。 | **O09 を検出** |
| 48 | 自由 F3 | 初期: NFC 論理名 `Report.pdf` の過去版を ext4 へ in-place restore、対象 raw エントリなし。操作: resolver 判定後・rename 前に外部プロセスが NFD 実体を作成。変化: restore は古い判定で NFC エントリを作成 → NFC/NFD 二重実体 → name_collision。 | **O10 を検出** |
| 49 | 自由 F4 | 初期: fork ID_WRITTEN 完了（repository-id=new、folders=old_id のまま）。操作: tick 外の「フォルダ単独検索」が発火。変化: §15 規約 12 は `folders(old_id)` と実測 `new_id` を素朴に照合 → fork_in_progress ガードを参照しない実装では conflict 誤表示。 | **O11 を検出** |
| 50 | 自由 F5 | 初期: agg cursor=C2、metadata.sqlite が C1 に復元済み。操作: step -1 実行時に metadata が一時 EIO → 直後復旧。変化: step -1 は z 判定のみだが一時読取不能時の分類が未定義 → そのまま step 1 が C1 LWW で OCR submit → 後で regression 検出。 | **O12 を検出** |

---

## 第 2 部 — 新規検出（C1〜C8、C10〜C12）

| ID | 重大度 | 該当箇所（§ + 短い引用） | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| O01 | fatal | §9.1 `cost_ledger` DDL L829 「`batch_job_id TEXT NOT NULL`」 / 同節 L973-974 「`submission_seq+1 の上で NULL + estimated の冪等 terminal 記帳`」 | server 経路 state=0 (`batch_job_id=NULL`) が期限超 confirmed-absent になると、規範は `NULL+estimated` 記帳を要求するが、DDL は `NOT NULL` を要求する。 | state0 server / token T → 相 2b 後 crash → 保持期限超 → `confirmed-absent` → `INSERT (..., batch_job_id=NULL, ...)` → `NOT NULL constraint failed`。state=0 が滞留するか、課金履歴が喪失する。 | C2 / C4 / C7 / C12 / X26 | `cost_ledger.batch_job_id` を `NULL` 許容にするか、`confirmed-absent` 記帳時に `intent:<token>` 形式の規範的 surrogate を非 NULL で定義する。 |
| O02 | fatal | §9.1 L970-976 「`submission_seq+1 の上で NULL + estimated の冪等 terminal 記帳を行ってから載せ直す`」 | 期限超の「記帳 → 新 intent_token での相 1」が同一 Tx でない。同じ job 候補を別 seq で無限に記帳でき、attempts も消費しない。 | seq=n / token T → 期限超 → seq=n+1 記帳 → 新相 1 実行前 crash → 次 tick で再び confirmed-absent → seq=n+2 記帳を反復。cost_ledger に架空台帳が増殖し、attempt 上限が無効化。 | C7 / C10 / C11 / C12 / X41 / X45 | 期限超判定・seq/attempts 増分・ledger 記帳・token rotation を単一 app Tx で確定させ、上限到達時は terminal とする。 |
| O03 | fatal | §9.1 (b') L1093-1101 「state=0 server … token 照合で job 実在を確認し、実在すれば掃除前に小 Tx で … 冪等記帳」 / L1045-1049 token sweep | (b') 記帳を token sweep が再駆動しない。main close 後の (b') 未記帳を sweep が掃除まで進めると課金欠落。 | profile A→B→A: A 成果あり → B job 作成後 crash → A へ戻す → state0 server 成果あり close 直後 crash → token sweep が job/token を掃除 → (b') 記帳が行われない。 | C7 / C10 / C11 / C12 / X40 / X41 | `unknown` 時は close しない。`found` / 成果あり判定時には `state2+seq+ledger+floor` を同一 Tx で確定させ、(b') は sweep ではなく collect/reconcile の同一 close Tx に含めるか、immutable token で accounting 済みを判別できるようにする。 |
| O04 | fatal | §9.1 detached 規範 L1060-1069 「state=0 server … 不存在を確認できたら … 削除」 | detached state=0 server には UUIDv7 期限判定がない。作成済み job が失効している状態を「未作成」と断定して削除でき、課金を回復不能にする。 | 相 2b 後 crash → unregister / missing で detached state=0 → 長期停止 → job 失効 → confirmed-absent → 行/token 削除、記帳なし。 | C7 / C10 / C11 / C12 / X28 / X45 | detached server state=0 も attached と同じ期限判定・推定記帳を適用し、O01 の surrogate 参照を使う。 |
| O05 | major | §8(ii) L708-711 「恒久 4xx … 記帳なし」 / §9.1 reconcile (b) L1089-1092 「batch_job_id 非 NULL なら cost_ledger へ NULL+estimated で冪等記帳」 | client は実行前に `batch_job_id=intent_token` を設定するため、`submit_rejected` 後の state=3/0 行も `batch_job_id` 非 NULL。後から成果ありになると reconcile が未実行 attempt を誤課金する。 | client 前計上 → 4xx `submit_rejected` → backup から state=0 (`batch_job_id` 非 NULL) 復元 → 成果復帰 → reconcile close → estimated ledger 1 行。 | C5 / C7 / C10 / C11 / C12 / X32 | `submit_rejected` 確定時に `batch_job_id` を NULL へ戻すか、reconcile (b) から `error='submit_rejected'` を除外する。 |
| O06 | fatal | §9.1 L911 「新規 UUIDv7 — 時刻成分 = 相 1 の実行時刻」 / L970-971 「intent_token (UUIDv7) の時刻成分から … 超えている場合」 | 期限判定が wall clock と UUIDv7 時刻成分の比較のみ。wall clock の前進/後退で、未作成 job を期限超扱いしたり、失効済み job を期限内扱いにしたりできる。 | 未来時計で T 作成 → job 課金 → 失効 → 時計修正 → age<0 → 無記帳のまま再投入。 | C7 / C11 / C12 / X4 / X45 | 許容 skew 外は `age=unknown` とし副作用を保留するか、安全側に推定記帳へ倒す。単調時計の補助情報を耐久保存する。 |
| O07 | major | §9.1 L924-927 「旧 attempt の upload_id … 削除は失敗しても続行」 / L929-931 「upload 成功直後に小さな app Tx で upload_id を行へ記録」 | 旧 upload 削除失敗後に新 `upload_id` を同一列へ上書きするため、旧 upload handle が失われ、プロバイダ側に TTL まで機密残留。 | U1 未清掃 → delete 429 → 続行 → U2 成功 → `upload_id=U2` 上書き → U1 が追跡不能。 | P6 / P9 / C3 / C10 / C11 / C12 / X16 | 旧 upload 削除成功まで新 upload を停止するか、世代別 cleanup handle を別表に耐久保存する。 |
| O08 | fatal | §21.4 L2570-2583 restore in-place 手順 | restore は「現在版=LWW」とは独立に working ツリーの未コミット変更を確認しない。in-place 上書きで未履歴化の working 変更を消失させる。 | LWW=A の直後、次 tick 前に working=B → 旧版 C を in-place restore → 次 tick は C を検出し B は objects・履歴・working からすべて消失。 | C7 / C8 / C11 / C12 / F1 | restore 前に対象を安定 scan して B を commit するか、working hash ≠ LWW なら拒否/明示 force/別名 export にする。 |
| O09 | major | §5.3 L253-263 明示再生成は「`floor_generated_at = 現在の generated_at`」 / §21.6 L2638-2644 backfill OFF では過去版のみの drop は再投入されない | drop で `markdown_documents` 行が消失後、明示再生成に `generated_at` の基準がなく、backfill OFF では候補にならない。 | 過去版のみの content H、backfill OFF → drop-derivation → 明示再生成 → floor 値なし → 永久に成果なしのまま。 | P13 / C3 / C8 / C10 / C11 / C12 / F2 | md 不在用の force intent / sentinel floor を定義し、backfill OFF でも明示対象だけを候補化する。 |
| O10 | minor | §20.5 L2265-2269 delete 最終確認の「残余の窓は自己修復」 / L2285-2294 / §21.4 L2578-2581 restore の resolver 使用 | raw 解決の readdir スナップショットから実操作実行までの narrow TOCTOU 窓について、delete 以外の restore/fsck では軟化文言が明記されていない。 | NFC 論理名の過去版を ext4 へ restore、resolver が raw エントリなしと判定 → 外部プロセスが NFD 実体を作成 → restore が NFC エントリを作成 → 二重実体・name_collision。 | C3 / C11 / C12 / F3 | §20.5 の resolver 定義に「3 呼出点すべてに共通の narrow TOCTOU 窓があり、次回 walk が name_collision として検出・収束する」を一箇所に明記する。 |
| O11 | minor | §15 規約 12 L1934-1943 「読み取り専用の操作も…同じ照合を行い」 / §21.3 L2481-2486 fork_in_progress による規約 12 抑止 | 規約 12 自身に `fork_in_progress` 考慮が記載されておらず、tick 外の standalone read 実装が素朴に照合すると fork 中に誤 conflict を返す。 | fork ID_WRITTEN 完了（`repository-id=new`、`folders=old_id`） → tick 外の単独検索が folders 行と実測 ID を素朴照合 → old_id≠new_id で conflict。 | C3 / C11 / C12 / F4 | §15 規約 12 に「fork_in_progress 対象は照合対象から除外」と明記するか、§21.3 に「この抑止は規約 12 のすべての呼出元に適用される共有ガード」と記す。 |
| O12 | major | §10 L1387-1390 step -1 / §9.3-z L1297-1301 / §15 L1940-1943 読取失敗の 4 分類 | step -1 は「安価な読取のみ」とされるが、metadata.sqlite が一時読取不能な場合の分類・除外規範がない。復元直後 tick が誤って OCR 課金を先行できる。 | agg cursor=C2、metadata=C1 に復元済み → step -1 実行時に metadata が一時 EIO → 直後復旧 → step 1 が C1 LWW を OCR submit → step 5 で regression 検出（後追い）。 | P10 / C7 / C8 / C10 / C11 / C12 / F5 | step -1 の結果を `verified` / `regressed` / `unreadable` の三値以上に固定し、`verified` のみ step 0〜4 へ進める。 |
| O13 | major | §6 L532-535 既存本文のエスケープ / §7 L579-582 un-escape | 元本文が `\\![x](obj:<hash>)`（行頭が `\\`）の場合、materialize はエスケープしないが、parser は行頭の `\\` を 1 つ除去して text を改変する。 | OCR 本文 `\\![x](obj:H)` → §6 不変 → §7 un-escape → `\![x](obj:H)` ではなく `![x](obj:H)` へ。`text_hash`・FTS・preview が原文と異なる。 | P5 / C1 / C10 / C11 / C12 / X11 | materialize は「0 個以上の先行 backslash + grammar 形」に対し必ず marker を 1 個追加し、parser は正確に 1 個だけ除去する。test vector を追加する。 |

---

## 第 3 部 — 確認済みの列挙（検出 0 件）

以下の観点・原則については、文書記述と状態遷移を追跡した上で問題を検出しなかった。

- **C2**: 標準 SQLite DDL・FK・CHECK・GENERATED 列・FTS5 external content view / trigger・vec0 テンプレートは静的に整合。
- **C3**: §21.7・§9.3-d・§18.4 など主要な相互参照は解決可能。
- **C4**: §11.2 完全 SQL・§9.3 カーソル SQL・GC 差集合は列名・型・join キーで整合。
- **C5**: `$2.5/1k`・`+25%`・768 参考値・RRF k=60・8 テーブル・30 日猶予・k_max=4096 は全出現で一致。
- **C6**: `target_key` 連結形式・`chunk_type`↔`target_type`・`obj:<hash>`・`embed_hash` の再掲は一致。
- **C7**: `batch_requests` の状態遷移は、本報告の O01〜O13 を除き到達不能・脱出不能分岐なし。
- **C8**: 欠落章は検出されなかった。
- **C10**: r13 修正どうしの直接的な矛盾は、O10〜O12 のような「修正隣接領域の完全性 gap」を除き検出されなかった。
- **P2, P3, P4, P7, P8, P12, P15, P16**: 原則と文書が一致（ただし P5/P6/P9/P10/P13/P14 に関連して O11/O13/O01〜O07/O12 が検出された）。
