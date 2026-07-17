# folder-history 設計書 r15 探索型監査シナリオログ

対象文書: `docs/research/folder-history-sqlite-design.md` (r14 修正適用済み版)
監査プロンプト: `tasks/folder-history-design-audit-prompt.md` (C12 / X1〜X56 + 自由探索)
作成目的: 日本語監査報告用の探索型監査シナリオ記録

## 凡例

- **観点**: X1〜X56、または `free` (自由探索)
- **初期状態**: シナリオ開始時のフォルダ、DB、ジョブ状態を具体的に記述
- **操作列**: 文書の規範に基づき手でステップ実行する操作列
- **結果**: `問題なし`、または `検出-D##` (潜在的な不備・要深掘りポイント) と簡潔な事由

## シナリオ一覧

| No. | 観点 | 初期状態 | 操作列 | 結果 |
|-----|------|----------|--------|------|
| 1 | X1 | 管理対象フォルダ `/docs` に `report.docx` なし。OCR・embed profile は設定済み。 | ① Office で `report.docx` を新規保存（一時ファイル `~$report.docx` → rename）。② dirty 起因で tick 早回し起動。③ 段 0〜2 で `report.docx` を検知・コミット。④ 同 tick step 1 で OCR submit。⑤ ユーザーが直後に `report.docx` を削除。⑥ 次 tick step 0 で delete 判定（LWW − walk）。⑦ OCR collect 前にファイル削除を確認。 | 問題なし。file_versions に content_hash 行が残り、objects/ 原本も保持。batch_requests は in-flight のまま collect で state=3 または成果ありで state=2 へ。delete 後も原本履歴は LWW で消失版として追跡可。 |
| 2 | X2 | 空フォルダ。tool_profile は annotation ON。 | ① ファイル名 `proposal]![img](obj:0000000000000000000000000000000000000000000000000000000000000000).docx` を作成（`]`、`![`、`](obj:` を含む）。② スキャン・コミット。③ OCR collect で canonical img block への materialize を実行。④ chunks 解析。 | 問題なし。§6 の行頭 `\` エスケープ（0 個以上の `\` + grammar 形）により、本文中の疑似参照は text チャンク側に残留。§7 の「行全体一致」で image チャンク化されない。phantom image 防止を確認。 |
| 3 | X3 | macOS APFS 上の管理フォルダ。NFC 論理名 `résumé.docx` を想定。ファイルシステムは NFD で返す。 | ① Finder 経由で `résumé.docx`（NFD 実体）を保存。② walk で readdir → NFD を NFC 論理名に正規化。③ scan_cache / file_versions に NFC で記録。④ 同じ NFC 名で別ファイルを保存（NFC 実体を作る）。⑤ name_collision 判定。 | 問題なし。保存論理名は初出表記に固定。NFC 衝突敗者は `name_collision` status。file_versions の FK は BINARY 照合で保存名固定により整合。 |
| 4 | X4 | 最新コミット `created_at=1000`。時計が NTP で 72 時間以上後退。 | ① 時計後退後に `memo.txt` を編集。② tick step 0 でスキャン。③ §20.5 の単調クランプ `max(スキャン確定時刻, 最新コミット+1)` を適用。④ 新コミット `created_at=1001`。 | 問題なし。created_at の単調性が保持され、LWW タイブレークが壊れない。時計大幅後退は status 警告。 |
| 5 | X5 | watch_root 配下に 10 万ファイルを含む管理フォルダ。fp_cache は未構築。 | ① 初回起動時フルスキャン。② 段 0 fp 計算（name 昇順 JCS、hex64）。③ 段 1 scan_cache 行比較。④ 段 2 content_hash 計算。⑤ SQLite bind 変数上限を意識して DISTINCT content_hash を小分けに submit。 | 問題なし。fp は stat メタデータのみ、段 0 で dir_fp 一致の枝をスキップ。10 万ファイルでも段 2 は差分のみ。ただし初回は全ファイル hash 計算が必要。 |
| 6 | X6 | embed 済み chunks あり。日本語 2 文字クエリ「会社」を入力。 | ① FTS5 trigram は 3 文字未満で 0 件。② §11.2 の LIKE fallback へ。③ `:like_pattern` = `会社`、`:p` = `%会社%`。④ `c.text LIKE :p ESCAPE '\' OR c.heading_path LIKE :p ESCAPE '\'` を eligible × agg_chunks 再 JOIN で実行。⑤ rank = `instr(lower(...), lower('会社'))` の非 0 最小 → chunk_uid。 | 問題なし。2 文字語も LIKE fallback で検索可能。ただし RRF への参加は FTS 経路として扱われる。 |
| 7 | X7 | 旧アプリで作成したフォルダ。img block grammar version = 1。新アプリが grammar v=2 を導入。 | ① 新アプリで一括再 materialize（§6：v +1、画像 bytes と旧 block から復元）。② markdown_documents 全走査で先頭 img block の `v:` 行を判定。③ v=1 の派生を DELETE → INSERT 置換。④ v=2 未知の block を含む古いアプリが開く。 | 問題なし。未知の v は fail-closed でスキップ + status。画像 0 件の文書は grammar version 対象外。 |
| 8 | X8 | 管理フォルダに `../../../etc/passwd` という名前のファイルを置く。 | ① walk の file_name 検証。② name_invalid として管理対象外。③ restore 操作で同様に file_name 検証。 | 問題なし。path traversal は保存側・restore 側で fail-closed。name_invalid status。 |
| 9 | X9 | `objects/<content_hash>` の 1 ファイルが破損（SHA-256 不一致）。working copy は健全。 | ① 週次 fsck 実行。② object 層で hash 不一致を検出。③ working copy を §20.5 と同じ 1 ストリームで読み取り、hash 一致なら tmp → rename で修復。④ 同一 content_hash の実体があっても原子置換。 | 問題なし。fsck の repair 経路で原本復元。読取一時失敗は破損と区別。 |
| 10 | X10 | 管理フォルダを zip → 解凍。mtime・inode が全変化。 | ① 解凍後のフォルダを watch_root 下に戻す。② rebind または再発見。③ scan_cache 行比較で (mtime_ns, size, inode) のいずれかが変化 → 段 2 へ。④ content_hash が同一なら「変更なし」、異なれば新コミット。 | 問題なし。content_hash ベースなので mtime/inode 変化は無害。deep-scan で racy 見逃しも補正。 |
| 11 | X11 | embedding profile A が現行。kind=2 batch_requests に profile A の state=2 行あり。profile B へ変更。 | ① app_config.embedding_profile を B に UPDATE（宣言的操作のみ）。② §8-a：成果判定で profile_hash ≠ 現行は成果なし。③ attempts=0 リセット。④ 旧 profile A の embeddings 行は置換対象。⑤ cost_ledger は削除されない。 | 問題なし。profile 変更は 1 操作で宣言的収束。cost_ledger は追記専用で履歴保全。 |
| 12 | X12 | app 未 bootstrap。watch_root 未登録。 | ① §21.5 bootstrap：watch_roots 登録、tool/embedding profile・image_filter 再入力。② walk で `.folder-history` 発見 → register。③ 文書追加 → スキャン → コミット → OCR submit → collect → チャンク → embed → replicate → 横断検索 → §12 解決 → 履歴表示 → restore。 | 問題なし。E2E の入力・出力が各 § で定義されている。ただし UI/CLI 操作カタログの細部は実装依存。 |
| 13 | X13 | GC が fail-closed で停止（原本・派生同時喪失）。 | ① §21.6 drop-derivation を明示実行。② markdown_documents 行を対象フォルダ単位で削除（CASCADE で chunks/FTS も削除）。③ GC が参照集合を再構築可能に。④ backfill ON の場合、現在版・過去版の再 OCR が自動投入。 | 問題なし。drop-derivation は明示操作として定義。backfill ON の過去版再投入も文書化済み。 |
| 14 | X14 | OCR submit で provider から 429 応答。 | ① 一時失敗として state=0 のまま。② Retry-After を `app_config.retry_not_before` に永続化。③ 次 tick 以降、期限まで submit/collect を skip。④ fp_cache / scan_cache の肥大は mark-and-sweep 掃除。 | 問題なし。レート制限は一時失敗扱い。fp_cache 孤児は完全 walk 成功時に掃除。 |
| 15 | X15 | 文書「delete は pending_deletes で見逃さない」を反証。 | ① ファイル `a.txt` を作成・コミット。② 30 秒以内に 2 回の tick 早回しで `a.txt` を一時的に absent（Office 保存の一時消失）。③ pending_deletes に first_absent_at が記録。④ 30 秒以上経過前にファイルが readable regular に復帰。⑤ delete 最終確認で lstat+regular 判定。 | 問題なし。時間差 + 最終確認により偽 delete を防止。時計急変下でも「存在すれば中止」ではなく対象外型置換を防ぐ。 |
| 16 | X16 | state=1 の OCR job が provider 側で恒久消滅（404）。 | ① collect で job_missing (404) を検出。② state=3 (error='job_missing') へ。③ 次 tick reconcile で成果ありなら state=2、成果なしなら attempts 上限内で再投入。 | 問題なし。state=1 の閉じ漏れを防ぐ。reconcile は state IN (0,3) のみ、collect が state=1 を閉じる分担が機能。 |
| 17 | X17 | register 実行中に app クラッシュ（`.folder-history` 作成直後）。 | ① 次回起動で対象フォルダを発見。② `.folder-history` 存在＋可読性を分離。③ 一時読取不能なら保留、構造破損なら damaged。④ 同じ root_path に別 id が登録済みなら旧行を先に退役。⑤ 再登録後、全量再同期。 | 問題なし。register のクラッシュ回復は §21.1 で規定。rebind / conflict / damaged の分岐が一意。 |
| 18 | X18 | profiles 表の 1 行が改竄され `SHA-256(record_json) ≠ profile_hash`。 | ① fsck profile 層で (a) hash 照合失敗を検出。② (b) 参照整合（md / embeddings の profile_hash 行存在・kind 一致）も検査。③ 現行 profile / batch_requests snapshot と一致すれば同一 Tx DELETE → INSERT 修復。 | 問題なし。profiles 破損は fsck で修復。修復不能な旧 profile は kind 別誘導。 |
| 19 | X19 | OCR collect で metadata.sqlite 1 Tx 確定後、app.sqlite state 更新前に電源断。 | ① 次 tick step 2 collect 冒頭でフォルダ側成果が既存 → metadata 処理スキップ。② app 行を state=2 + cost_ledger 追記。③ ON CONFLICT DO NOTHING で冪等クローズ。 | 問題なし。collect 冒頭の冪等スキップで回復。 |
| 20 | X20 | app.sqlite 全損。server-side batch に in-flight job が 1 件。 | ① app 全損後、in-flight job は追跡不能。② プロバイダ側で結果保持期限超過。③ 新 app 構築後、同 content_hash は新規 submit。④ 同一 content_hash でも folder-history は per-folder 課金。 | 問題なし（設計通りの限界）。app 全損時の重複課金は server-side batch の「最悪 1 回分」の有界化の外。規約 7 (a) に記載。 |
| 21 | X21 | 明示再生成を要求された content に floor_generated_at 設定。 | ① §5.3：batch_requests 行に floor = 旧 generated_at を設定。② backfill OFF でも floor 設定済みなら候補。③ OCR collect で新 md 行を INSERT（generated_at = max(now, 旧+1)）。④ 同 Tx で floor を NULL へ戻す。⑤ §7 で再チャンク時も floor を引き上げ。 | 問題なし。floor 方式は backfill 設定に関わらず機能。順序は app (floor) → metadata (generated_at)。 |
| 22 | X22 | fork 操作で phase=HISTORY_CLEARED まで完了後クラッシュ。 | ① 毎 tick 冒頭で fork-journal 走査。② phase + 実 id から再開位置を一意に決定。③ commits 非空なら手順 1 から。④ flag → journal の削除順を維持。 | 検出-D01：fork phase 機械の E2E は単体テストで全境界（PREPARED/ID_WRITTEN/APP_DONE × app 全損/journal 破損/flag 逆転）を網羅する必要あり。文面上は一意だが、実装での phase 判定と再開位置の網羅テストが必要。 |
| 23 | X23 | client 側キューで embedding 同期 API 呼出し失敗（恒久 4xx）。 | ① 実行前計上：attempts+1、seq+1、batch_job_id=intent_token。② 恒久拒否 → state=3 (submit_rejected) + attempts=上限。③ 同 Tx で batch_job_id を NULL へ戻す。④ cost_ledger 記帳なし（内容起因 4xx = 課金なしのプロバイダ前提）。 | 問題なし。client 経路の失敗分岐は §8(ii) で規定。記帳なしと未実行の境界は明確化済み。 |
| 24 | X24 | embedding_vec の DROP → CREATE 後、再充填途中にクラッシュ。 | ① 次 tick step 3 冒頭で vec 次元・距離を照合。② 次元一致でも embeddings の現行 profile 行のうち vec に無い target_key を差集合で冪等再充填。③ 中断前に充填済みの行はスキップ、残りを埋める。 | 問題なし。差集合再充填によりどのクラッシュ位置でも欠落を埋める。 |
| 25 | X25 | app.sqlite だけあり、folders 行が 0（フォルダ未接続）。 | ① 横断検索を実行。② `:query_vector` は app_config.embedding_profile record から生成。③ `agg_ready_profile_hash` と `:query_profile_hash` を同一 read Tx で照合。④ 不一致なら FTS のみ + status「index 再構築中」。 | 問題なし。横断検索は app_config だけで完結。ready 不一致時は KNN を沈黙させない。 |
| 26 | X26 | state=0 の batch_requests 行に batch_job_id 非 NULL（client 前計上済み）。 | ① submit 冒頭 dispatch：batch_job_id 非 NULL → client 再実行経路。② attempts < 上限なら旧 seq を NULL+estimated で冪等記帳してから attempts+1、seq+1。③ attempts >= 上限なら client_exhausted。 | 問題なし。submission_seq、attempts、ledger の三者整合は §9.1 で規定。ただし client 再実行の旧 seq 記帳が毎回行われることを実装で確認要。 |
| 27 | X27 | fork 中に app 全損。fork-journal は層 1 に残存。 | ① 新 app bootstrap で journal 走査。② journal は {old_id, new_id, realpath, was_tracked, phase} + digest。③ 発見パスで回復。④ 中断中フォルダ移動でも realpath と id 照合で追跡。 | 問題なし。fork-journal を層 1 に置くことで app 全損を跨いで回復。flag 保存先は app_config。 |
| 28 | X28 | unregister 実行時に in-flight OCR job あり。 | ① folders 行を削除。② batch_requests 行は detached 化。③ collect で payload 破棄、state=2/3 + cost_ledger 記帳。④ upload 掃除完了・intent_token NULL 化後に行削除。⑤ 削除前に再登録されると自動再投入（意図されたコスト）。 | 問題なし。detached は課金追跡専用。再登録による再課金は有界・ledger 追跡済み。 |
| 29 | X29 | case-insensitive ボリュームで `Report.docx` を作成後、`report.docx` に改名。 | ① 初出表記 `Report.docx` を保存論理名に固定。② 大小文字違いは同一系列。③ PARTITION BY file_name (BINARY) で単一系列。④ restore 宛先も保存論理名を使用。 | 問題なし。保存名固定により FK 違反を防止。case 感度は走査時ボリューム属性で判定。 |
| 30 | X30 | attempts 上限到達後、明示 retry で attempts=0 にリセット。 | ① terminal failed 行を明示 retry。② 同じ (content_hash, tool_profile_hash) で再投入。③ cost_ledger の UNIQUE (repo, kind, target_key, submission_seq) は attempts ではないため、新 seq で正当な再課金を記帳。 | 問題なし。submission_seq はリセットしない通算値。attempts リセット後の再課金は UNIQUE を妨害しない。 |
| 31 | X31 | unregister → 再登録の繰り返し。 | ① unregister で batch_requests 行を一部 detached/一部削除。② cost_ledger は残す。③ 再登録で batch_requests 行を新規 INSERT。④ seq 初期値 = cost_ledger の同キー MAX から継承。⑤ 0 起点でないことを確認。 | 問題なし。seq 継承により旧 ledger との UNIQUE 衝突を回避。 |
| 32 | X32 | fork journal の digest が不一致（改竄または破損）。 | ① §21.1 手順 1 で journal チェック。② digest 不一致 → damaged。③ 唯一の回復ゲート例外：破損 journal の明示解決（ユーザー確認の上で journal/flag 除去 → 新 id 再登録）。④ 回復先行ゲートは bypass される。 | 検出-D02：破損 journal の明示解決経路が唯一のゲート例外であることを UI/CLI で明確に提示する必要あり。誤って「回復不能な fork」を通常運用へ戻さない設計要確認。 |
| 33 | X33 | server 経路で OCR 成功。 | ① 相 3 で state=1 + batch_job_id + seq+1。② collect 成功：metadata 1 Tx → app 1 Tx。③ cost_ledger へ (seq, batch_job_id, pages, cost_usd) を追記。④ 冪等：同一 seq の再観測は ON CONFLICT DO NOTHING。 | 問題なし。server 成功の課金記帳は一意。 |
| 34 | X34 | agg_ready_profile_hash = P1、`:query_profile_hash` = P2。 | ① 横断検索開始。② 同一 read Tx で ready ≠ query。③ KNN を実行せず FTS のみ + status「index 再構築中」。④ ready が P2 に更新されるまで待機。 | 問題なし。query_profile_hash 固定により embed 中の profile 変更 TOCTOU を防止。 |
| 35 | X35 | batch_requests 行削除後、同キーで新規 INSERT。 | ① ledger に seq=3 の行あり。② 行削除後、新規 INSERT で seq 初期値 = MAX=3。③ 相 3 で seq=4。④ 新しい課金を seq=4 で記帳。⑤ 旧 seq=3 の記帳行は残る。 | 問題なし。seq 継承により新しい attempt が旧 seq と衝突しない。 |
| 36 | X36 | detached 行を state=0 server から採用（job 実在）。 | ① intent_token で job 一覧照合 → found。② 相 3 と同じ UPDATE：state=1 + batch_job_id + attempts+1 + **seq+1** + submitted_at。③ collect 成功で seq 値を cost_ledger へ記帳。 | 検出-D03：detached 採用時の seq+1 がなければ、以後の close 記帳が旧 lifecycle の同一 seq と衝突し課金が消える。文書では seq+1 が要求されているが、実装での網羅要確認。 |
| 37 | X37 | フォルダ A/B/C を接続。C が damaged。 | ① ready 判定の母数 = 当該 tick で §9.3 を実行できたフォルダ（A/B のみ）。② C は除外。③ A/B の synced_profile_hash = building で ready 更新。④ C 復旧後、旧 profile の embeddings のままなら synced=NULL → ready は再び落ちる。 | 問題なし。母数定義により damaged フォルダが空 index ready を騙さない。 |
| 38 | X38 | fork 中に watch_root 外へフォルダを移動。 | ① 中断中フォルダ移動で journal を発見できず。② flag 掃除は「realpath に .folder-history 実体現存」かつ marker id = new_id 一致。③ id=old または id=他 → 掃除せず damaged/保留。④ bootstrap/walk の journal 走査で移動先を発見。 | 問題なし。flag 掃除の id 一致要件により未完 fork を誤って通常運用へ復帰させない。 |
| 39 | X39 | register 対象フォルダが一時的に EIO（ディスク接続不良）。 | ① 存在と可読性を分離。② 一時読取不能 → 保留 status（damaged 誘導せず）。③ 接続回復後に再試行。④ 一時失敗を conflict/damaged に倒さない。 | 問題なし。register の 4 分類が §21.1 に規定。 |
| 40 | X40 | profile 変更後、全フォルダの re-embed 完了前に ready が更新されないことを反証。 | ① profile A→B 変更。② agg_vec を DROP → CREATE、synced 全 NULL。③ 一部フォルダのみ B embeddings 複製済み。④ ready 判定：接続フォルダすべてが synced=B。⑤ 未完フォルダがある間は ready 更新しない。 | 問題なし。ready は「設定時点の被覆」宣言。0 行コピー・部分 index を通さない。 |
| 41 | X41 | client 経路で複数回再実行。 | ① 呼出中クラッシュ → state=0 のまま。② 再実行：旧 seq を NULL+estimated で冪等記帳 → attempts+1, seq+1。③ 上限到達 → client_exhausted。④ 各 attempt が cost_ledger に 1 行ずつ記録される。 | 問題なし。client の中間 attempt の課金が台帳から漏れない。 |
| 42 | X42 | folders 行が 0 件 → 1 件復帰。 | ① 接続 0 件中は ready を更新しない。② 1 件目復帰後、§9.3-c で synced 更新。③ ready 判定の母数が変化。④ synced 全 NULL 化（破棄 Tx）と §9.3-c の UPDATE が競合しないよう tick.lock 下。 | 問題なし。母数の変動を考慮した ready 判定。 |
| 43 | X43 | restore in-place で論理名 `résumé.docx`、実体は NFD。 | ① 検証済み root の readdir 列挙から raw エントリを解決。② NFC 名をそのまま path に使わず、raw エントリへ上書き。③ NTFS/ext4 で別エントリ作成を防止。④ rename 直前に解決先 raw を再 lstat。 | 問題なし。raw 解決により二重実体を防止。in-place では再 lstat が義務。 |
| 44 | X44 | 登録済みフォルダの repository-id を別 repo に差し替え。 | ① 単独検索時に folders 行と repository-id を照合。② 不一致 → conflict、結果を返さない。③ 一時読取不能 → 保留。④ fork_in_progress の対象は照合・conflict 判定から除外。 | 問題なし。規約 12 の scoped read 拡張が読み取り専用操作にも適用。 |
| 45 | X45 | raw 解決で collision 時の採用規則を反証。 | ① NFC/NFD 両方存在。② 採用 = 物理名 UTF-8 バイト昇順の先頭 1 件。③ 非採用系列は通常の delete 確認へ。④ restore 書込先も同じ採用系列を使用。 | 問題なし。採用規則が walk・restore・delete 確認で一貫。 |
| 46 | X46 | 期限超 confirmed-absent で intent_token 記帳後、載せ直し → 相 3 成功。 | ① 期限超：述語 → seq+1 (行 UPDATE) → NULL+estimated 記帳 (batch_job_id=intent_token)。② 載せ直し：新 intent_token。③ 相 3：batch_job_id=job_id、seq+1。④ collect 成功：さらに seq+1 の実額記帳。⑤ ledger に token 記帳・job_id 記帳の混在。 | 検出-D04：同一 lifecycle で token 記帳と job_id 記帳が混在する系列で、記帳済み判別述語（batch_job_id 一致）が正しく機能することを実装で検証要。文書上は規定されているが、系列追跡が複雑。 |
| 47 | X47 | 期限超処理を同一 app Tx で完結。 | ① (i) 記帳済み判別 → (ii) seq+1 UPDATE → (iii) attempts+1 → (iii') expired 出口 → (iv) 載せ直し相 1。② Tx 境界でクラッシュ → 次 tick は (i) の述語で旧 token 記帳を検出。 | 問題なし。記帳と rotation を同一 Tx にすることで、別 token 世代の生成を防止。 |
| 48 | X48 | restore in-place で現内容が LWW と異なる。 | ① 安定確認。② 現内容 ≠ LWW なら先に §20.5 手順でコミット（保全）。③ 上書き。④ 次 tick スキャン。⑤ 安定確認失敗なら restore 中止。 | 問題なし。restore は未取り込みの working 変更を消さない。 |
| 49 | X49 | register 実行直前に未完 fork の journal が有効。 | ① §21 前文：lock 取得直後に fork 回復を先行。② 有効 journal → 回復完了。③ 破損 journal → 明示解決のみを提示。④ 回復後の状態を入力に register を実行。 | 問題なし。回復先行により操作が回復後の状態に反転されない。 |
| 50 | X50 | state=0 server の成果あり close（metadata 行あり、floor 以下）。 | ① reconcile / submit close で (b') 前段：token 照合 → job 実在なら seq+1 + NULL+estimated 記帳。② unknown なら保持。③ confirmed-absent 期限内なら記帳なしで掃除。④ 期限超なら記帳してから掃除。 | 問題なし。state=0 server の成果あり close も課金済み job を無記帳で破棄しない。 |
| 51 | X51 | 期限超 (ii) で行 UPDATE 後、相 1 → 相 3 で再び +1。 | ① 期限超：seq 5 → 6 (UPDATE)、NULL+estimated 記帳 (seq=6)。② 載せ直し相 1：seq は 6 のまま。③ 相 3：seq 6 → 7。④ collect 成功：seq=7 で実額記帳。⑤ 同一 attempt が二重加算されていないか確認。 | 検出-D05：期限超の行 UPDATE は「作成済みであり得た attempt」の記帳用であり、その後の相 3 / collect 成功では別 attempt として +1 する。設計上は正しいが、実装で「seq=6 の行 UPDATE 後に相 3 でも +1」が二重カウントに見えないよう、コメント・テストで検証要。 |
| 52 | X52 | expired 行が state=3 (attempts=上限)、intent_token 残存。 | ① 遷移表：state=3・attempts >= 上限 → 投入しない。② unregister 時：intent_token IS NULL でないため削除しない（detached 保持）。③ token sweep で intent_token NULL 化後に削除可。④ 明示 retry で attempts=0 リセット。 | 問題なし。expired は terminal 4 種の一貫した扱い。 |
| 53 | X53 | 4 照合点（intent 回復・detached(b)・(b')・token sweep 前段）を比較。 | ① 各点で (a) 三値 (b) 期限超 (c) 未来 skew (d) 伝播猶予 (e) 記帳済み判別 (f) seq 行 UPDATE (g) batch_job_id 値 (h) 後続動作 を比較。② 期限内 confirmed-absent は記帳なしで掃除/載せ直し。③ 期限超は記帳してから掃除/削除。 | 検出-D06：4 照合点の記述が §9.1 の各節に分散しているため、実装者が「共通適用」を漏らさないよう、共通関数化またはチェックリストが必要。文書上は対称だが、分散記述は実装漏れのリスク。 |
| 54 | X54 | journal × flag × 実体 id の全組合せ。 | ① 有効 journal + flag あり + id=new → 回復。② 破損 journal + flag あり → 明示解決。③ journal なし + flag あり + id=old → damaged/明示解決待ち。④ journal なし + flag なし → 通常運用。 | 問題なし。全組合せが §21.3 / §21.1 で一意に帰結。ただし UI で damaged / fork 進行中 / missing の優先表示を検証要。 |
| 55 | X55 | embedding 混在（KNN 停止）中に tool も混在。 | ① `:current_profile` = embeddings の一意 profile。複数 profile 混在 → KNN 停止・FTS のみ。② `:current_tool` = markdown_documents の最新 generated_at。tool 混在 → 最新 tool で eligible を絞り、FTS は継続。③ 同一フォルダで横断（app_config tool）と単独（最新 generated_at）が異なる tool を選ぶ可能性。 | 問題なし。tool 混在は非対称で意図的。FTS は tool gate 内で全量。被覆非保証は status に明示。 |
| 56 | X56 | 本文に `![diagram](obj:see appendix)`（hash64 不一致）を含む Markdown。 | ① §6 のエスケープ対象は「0 個以上の `\` + 行頭 `![` + `](obj:` を含む grammar 形」。② 上記行はエスケープされる。③ §7 の un-escape は「行全体が hash64 込みの grammar に一致」する場合のみ。④ 上記行は un-escape されず `\` が残留。 | 検出-D07：r14 見送り論点。エスケープ条件が un-escape 認識形の上位集合であるため、`![diagram](obj:see appendix)` のような行は `\` が残留し、FTS/preview に影響する可能性。phantom 防止とのトレードオフであり、現状維持が安全側と裁定されているが、監査報告で再評価の証拠として記録すべき。 |
| 57 | free | 複数デバイスで同一フォルダをライブ同時編集。 | ① 本設計は §2 / §19 でライブ同時編集 + 汎用同期を非対応。② 複数デバイスでコミットを並行作成 → 片方をコピーして書き戻す → conflicted copy の履歴は黙って失われる。 | 問題なし（設計通りの非対応）。§19 の再検討条件 1 を満たす場合は不変オブジェクト正本への移行を検討。 |
| 58 | free | cross-volume へフォルダを移動（case-insensitive → case-sensitive）。 | ① 旧ボリュームで `Report.docx` の系列を保存。② case-sensitive ボリュームへ移動。③ 大小文字違いの `report.docx` を新規作成。④ case 感度は新ボリューム属性で再判定。⑤ 既存系列 `Report.docx` と新規系列 `report.docx` は別系列（系列分裂）。 | 問題なし。保存名は不変。insensitive→sensitive 移動での系列分裂はデータ喪失ではないと明記。 |
| 59 | free | code fence 内の `#` が見出しと誤認識されない。 | ① Markdown に `` ``` `` で囲まれたコードブロック内に `# コメント` を含む。② §7 規則 1：CommonMark の fenced code block 内の # は見出しでない。③ 4 空白インデントのコードブロックも同様。④ text_hash が実装間で分岐しない。 | 問題なし。code fence 規則が CommonMark に固定。 |
| 60 | free | upload 掃除で 404 = 削除成功。 | ① upload_cleaned=0 で全行終端の upload_id をプロバイダから削除。② プロバイダ側で既に削除済み → 404。③ 404 を削除成功として upload_cleaned=1。④ 失敗扱いにしない（恒久再試行を防止）。 | 問題なし。404 は削除成功。 |

## 検出事項サマリー

| 検出 ID | 該当シナリオ | 内容 | 重大度 | 備考 |
|---------|--------------|------|--------|------|
| D01 | No.22 | fork phase 機械の全境界網羅テストが必要 | minor | 文面は一意だが、実装テスト網羅要。 |
| D02 | No.32 | 破損 journal の明示解決経路を UI/CLI で誤操作防止 | minor | 回復ゲート唯一の例外、ユーザー確認必須。 |
| D03 | No.36 | detached 採用時の seq+1 の実装網羅要 | minor | 文書上は要求されているが、テストで確認。 |
| D04 | No.46 | token 記帳と job_id 記帳混在系列の記帳済み判別の実装検証要 | minor | 文面は規定済み、系列追跡が複雑。 |
| D05 | No.51 | 期限超 seq UPDATE と後続相 3 の +1 が二重カウントに見えないようテスト要 | minor | 設計上は正しいが、可読性・テスト観点。 |
| D06 | No.53 | 4 照合点の共通適用を分散記述から漏れさせない実装対策要 | minor | 共通関数化またはチェックリスト推奨。 |
| D07 | No.56 | §6/§7 エスケープ条件の非対称による `\` 残留の再評価 | minor | r14 見送り論点。phantom 防止とのトレードオフ。 |

## 総括

- 全 56 観点（X1〜X56）について 1 シナリオずつ、加えて自由探索 4 シナリオ、合計 60 シナリオを構成。
- 各シナリオは文書の規範（§4.1、§5.3、§6、§7、§8、§9.1、§9.3、§10、§11.2、§13、§20、§21 など）に基づき、具体的な初期状態・操作列を記述。
- 結果は「問題なし」が原則。潜在リスク・実装検証ポイントを 7 件の検出 ID として抽出（いずれも minor。設計上の不備ではなく、実装・テスト網羅の観点）。
