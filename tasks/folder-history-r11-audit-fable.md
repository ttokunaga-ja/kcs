# folder-history 設計書 r11 監査報告 (Claude Fable 5 系統)

対象: `docs/research/folder-history-sqlite-design.md` (ディスク実体・r10 適用済み・2,320 行、2026-07-15 実行)。
プロンプト掲載文書とディスク実体の同一性を r10 修正マーカー 14 語 (client_exhausted / agg_ready_profile_hash /
fork-journal / submission_seq / retry_not_before / missing_since ほか) の出現数で照合済み。
引用は全件ディスク実体と grep 照合済み。SQL 検証は SQLite 3.51.0 の実機実行 (DDL 全 12 表 + FTS5 +
trigger + §11.1/§11.2/§9.3-a クエリ + M01 再現) に基づく。

## 判定: **不合格**

- 前提条件: **充足** — 探索ログ 52 シナリオ、X1〜X35 に未実行観点なし
- C9 回帰: 233 項目中 232 が fixed / superseded、**L28 のみ partially-fixed**
- 新規検出: **fatal 1 (M01)・major 2 (M02・M03)**・minor 6 (M04〜M09)・proposal 0
- 不合格事由: partially-fixed 1 件 + fatal/major の新規検出

r11 の重心どおり、fatal は **r9/r10 修正どうしの相互作用** (M01 = terminal 化時の課金記帳 (K11) ×
reconcile close の記帳義務 (L03) × ledger UNIQUE (K02/L01) の三つ巴) で開いた。発生源は §9.1 状態
機械の本体からさらに外周 (close 経路の課金記帳の冪等性) へ移っており、「fix が開ける穴」の定番脈
12 例目。major 2 件も fork phase 機械 (L07) と building/ready 2 key (L09) という r10 fix の縁で出た。

---

## 第 1 部 — 回帰確認 (C9)

**A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 /
J01〜J20 / K01〜K26 / L01〜L27: すべて fixed または superseded (対応表どおり)。**

主要スポット確認 (抜粋): L01 = §5.3 L120–128 + §9.1 L688–694 の MAX 継承 (COALESCE 式実在、実機で
動作確認)。L02 = §9.1 L880「UNIQUE(repository_id, kind, target_key, submission_seq) が…防ぐ」(旧
attempt 表記なし)。L03 = §9.1 L942–951 の付随処理 (a)(b)(c) + 解消宣言。L05 = L839–845 の同 Tx
attempts=上限。L06 = L849–851 dispatch + client_exhausted。L07/L08 = §21.3 phase 機械・削除順・
id=old 分岐。L09 = §8-e L617–623 + §11.2 L1464。L10 = tool_changed ガード実在 (所在は §9.1 intent
回復 — 検証リスト側の「§11.2」は表記ずれ、内容で判定)。L14/L15/L16/L17/L18/L19/L20/L21/L23/L24/
L25/L26/L27 いずれも該当文言実在。regression マーカー (「7 テーブル」「:current_tool_profile_hash」
「一度だけ破棄」「常に手順 3〜4」「判定だけ折り畳み・保存は readdir 表記」「attempt キー UNIQUE」)
はすべて否定文脈のみ、残存 0。

例外 1 件:

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
|---|---|---|
| L28 | partially-fixed | 4 要素中 2 要素は実在 — register の vec 非作成 (§21.1 手順 2)・folders.missing_since (§9.1 DDL L673)。**残存**: (1) app_config の DDL コメント (L761–763) が「'agg_embedding_profile_hash' = agg_vec 構築時の…(§8-e の宣言的検査の基準)」と**旧・単一 key のまま** — §8-e (L617–619) の agg_building_profile_hash / agg_ready_profile_hash の 2 key 制、および L26 の retry_not_before が DDL コメントに未反映 (詳細は M09)。(2)「fsck の agg 側 vec も対象」に対応する記述が §13 に無い (§8-e は逆に「agg_vec の欠落は同期では検出しない — 規約 9 の破棄・再構築で扱う」— 別解に置換されたなら L28 の期待側の整理が要る) |

プロンプト側の注記 (判定に影響なし): superseded 対応表の「K06→L02」「K09→L03」は内容上それぞれ
**L05** (submit_rejected の attempts=上限)・**L06** (client_exhausted 出口) を指す番号ずれ。判定は
新項目側で直接行った。

---

## 第 2 部 — 探索ログ (C12) — 52 シナリオ

[実機] = SQLite 3.51.0 での実行再現。他は文書規範のみによる手動ステップ実行。

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 1 | X1 | 1 tick 窓内で create→編集→delete → walk は最終状態 (absent・未追跡) のみ観測、履歴行ゼロ。tick が編集後に挟まると create→pending→30 秒+2 walk 後 delete | 問題なし |
| 2 | X1 | OCR in-flight 中に原本ファイル削除 → 派生は content-addressed で着地、file_versions の過去版参照が GC から守る | 問題なし |
| 3 | X1 | backfill OFF + 過去版のみの content へ明示再生成 → floor 設定行は「backfill 設定に関わらず候補」(§10 step 1) で再投入経路が保証される | 問題なし |
| 4 | X1 | フォルダを PC2 へコピー→双方編集→PC2 版を PC1 へ書き戻し → PC1 の post-copy コミット喪失は z(2) カーソル commit 不在で検出、wipe + full resync + regressed 通知 | 問題なし (§2 の非対応明記どおり) |
| 5 | X2 | 原本 PDF の本文に `![x](obj:...)` 行 + 巨大 `<!-- img:` 偽装 → §6 のページ結合後・行頭 `\` エスケープ + §7 実在検証の二層で phantom チャンク不成立 | 問題なし |
| 6 | X2 | annotation 値に `-->` と `\` を含む → `\→\\` の後 `-->→--\>`、un-escape 逆順で往復可逆 (`--\>` 原文は `--\\>` 保存) | 問題なし |
| 7 | X2 | 0 バイトファイル → commit は通常作成、preflight がマジックバイト判定不能 → unsupported_format terminal marker を 1 回だけ作成 | 問題なし |
| 8 | X2 | ハードリンク 2 名 (同 inode) → 2 論理系列・objects/ は content_hash dedup・片方経由の編集は両系列の update として観測 | 問題なし |
| 9 | X3 | macOS NFD readdir → NFC 論理名で単一系列 (§20.5)、fp_cache は raw name (§20.3 明記) — 変換点は walk 照合の入口 1 箇所で一意 | 問題なし |
| 10 | X3 | case-insensitive で "Report.pdf" 固定済みの系列を case-sensitive ボリュームへ移動、"report.pdf" を追加 → ボリューム属性判定で折り畳み停止、別系列 create。既存系列は保存名 BINARY 一致で継続 | 問題なし |
| 11 | X4 | 時計後退 (NTP) 中に編集 → created_at = max(now, latest+1) クランプで LWW 前進、§9.3-a カーソルからも脱落しない | 問題なし |
| 12 | X4 | 未来時刻 (年単位) で汚染後に時計修正 → now < latest−72h の警告 + latest+1 続行、修復は再初期化のみ (明記) | 問題なし |
| 13 | X5 | 10 万ファイル walk → stat は毎回必要 (物理制約明記)、fp は walk 後の省略のみ。reconcile の走査は idx_batch_active 部分 index + §19 再考条件 | 問題なし |
| 14 | X6 | 2 文字クエリ「wi」→ trigram 沈黙 → LIKE fallback 完全形 (eligible × agg_chunks 再 JOIN + ESCAPE + instr(lower,lower)) を実行 [実機] | 問題なし |
| 15 | X6 | 700MB PDF 1 本 + JSONL 行数上限超の対象群 → 512MB 超は oversize terminal marker、残りは複数 job 分割 (1 job = 1 repo 維持、token は job 単位) | 問題なし |
| 16 | X7 | 新版アプリで migration 済み DB を旧版アプリで開く → user_version gate で fail-closed。migration は単一 Tx + FTS 後付けは同 Tx 'rebuild' [実機で rebuild 動作確認] | 問題なし |
| 17 | X8 | 共有された細工 `.folder-history` の file_versions に `../escape` → 保存側 name_invalid + restore 側宛先検証の二重防御で working 外へ書かない | 問題なし |
| 18 | X9 | metadata.sqlite のみ旧版へ復元 (objects は現行) → fsck は通過するが z(2) が「カーソル commit 不在」で検出 → wipe + resync + regressed 通知 | 問題なし |
| 19 | X9 | ディスク満杯を objects 書込点/metadata Tx/app Tx の各点で発生 → 規約 6 の順序により後続参照は常に存在保証、次 tick の差集合が再収束 | 問題なし |
| 20 | X10 | zip 化→解凍往復 (mtime/inode 全変化) → 段 1 全行不一致 → hash 再計算 → 内容同一なら履歴行ゼロ (scan_cache だけ更新) | 問題なし |
| 21 | X11 | fp の raw name 層と NFC 論理名層の変換点 → §20.3「正規化はしない」と §20.5「全層共通の論理名」が walk 照合入口で一意に接続 | 問題なし |
| 22 | X12 | watch_root 追加→register→scan→commit→OCR→chunks→embed→replicate→横断検索→§12 解決→restore→再 scan の一気通貫 — 各受け渡しの入力元 § を全て特定できた | 問題なし |
| 23 | X13 | 「明示操作」「status 表示」全列挙 → §21.1〜21.7 + §5.3/§8/§13 で入力・手順・失敗回復が閉じる (UI 形は実装裁量と明示) | 問題なし |
| 24 | X14 | submit 429 (Retry-After 3600s) → app_config retry_not_before 永続化で非常駐 tick を跨ぎ抑制 / collect 429 → 同 tick 打ち切り・行不変 | 問題なし |
| 25 | X15 | 主張「クラッシュ残骸は次 tick が収束させる」→ M01 の行 (state=3・成果あり・同 seq 記帳済み) だけは収束せず毎 tick 失敗 | **M01 を検出** |
| 26 | X15 | 主張「フォルダ単体からクエリ embedding の作り方を復元できる (§5.7)」→ コピー先で profiles 全行一致→record 復元→KNN 成立。破れず | 問題なし |
| 27 | X16 | JSONL 分割で 2 job 化 → intent_token は job 単位で別値、相 2b 途中クラッシュは job ごとに照合・採用/載せ直し | 問題なし |
| 28 | X17 | register 手順 2 途中クラッシュ (不完全 .folder-history) → damaged 扱い → tmp 掃除後やり直し。原本無傷・再実行安全 | 問題なし |
| 29 | X18 | 部分 walk 失敗 (stat 1 件エラー) × pending_deletes → 不完全 walk は UPSERT も 2 回目カウントもしない、fp 未確定で持ち越し | 問題なし |
| 30 | X19 | 相 2a 完了 (upload_id 記録済み)・相 2b 前の電断を 3 回反復 → 残骸 upload は token/upload_id で追跡・掃除、job 二重作成なし、attempts 不消費 | 問題なし |
| 31 | X20 | 主張「月跨ぎ retry は発生月へ配賦」→ ledger.ts = collect 確定時刻の attempt 単位追記で成立。破れず | 問題なし |
| 32 | X21 | floor 引き上げ (app 先行) → metadata 更新前クラッシュ → 成果なし範囲が広がるだけ (再 OCR 方向 fail-safe、文書自認)。§9.3-b 伝播も generated_at 比較で追随 | 問題なし |
| 33 | X22 | fork 実行中に unregister を起動 → §21 前文の tick.lock ブロッキング取得で直列化、交錯不能 | 問題なし |
| 34 | X23 | name_collision の敗者を削除 → 採用実体の交替で同一論理名へ update 1 回 (意図された遷移と明記)。readdir 順非依存 | 問題なし |
| 35 | X24 | vec DROP→CREATE→再充填の各位置でクラッシュ → 次 tick の差集合再充填 (次元一致でも毎回) が残りを埋める。破れず | 問題なし |
| 36 | X25 | restore の 4 入力 (in-place 三組 / delete 版 / content_hash 単独 / 管理外宛先) → delete 版拒否・単独は明示宛先必須・すべて一意 | 問題なし |
| 37 | X26 | submission_seq の書込点 3 経路 (相 3 / intent 採用 / client 前計上) は排他、載せ直しの相 1 再通過は seq 不変 → 相 3 で +1 のみ。二重加算なし | 問題なし |
| 38 | X27 | fork 全 phase × 通常クラッシュ / app 全損 → journal (phase + 実 id) で再開位置一意。id=old は手順 1 から。was_tracked は journal 固定値 | 問題なし (移動が絡む場合のみ M02) |
| 39 | X28 | detached (state=1) のまま同 repo を再登録 → folders 復帰で通常行化、submit は「成果なし・state=1 = 回収待ち」で二重投入せず、collect が成果書込 + 記帳 | 問題なし |
| 40 | X29 | 初出表記固定 × §11.1 PARTITION BY file_name × 複合 FK → 保存名が BINARY 一致で単一系列、FK 参照先も常在 | 問題なし |
| 41 | X30 | 主張「保存名固定により case-only rename の FK 違反は構造的に不可能」→ rename は履歴に取り込まれず違反経路なし。破れず | 問題なし |
| 42 | X31 | **profile A(成果あり)→B へ変更→再投入 (seq=2)→job 完了前に A へ戻す→collect が profile_changed で state=3 + 記帳 (seq=2)→次 tick reconcile が成果あり (embeddings=A=現行) を検出して close + 記帳 (seq=2)** → UNIQUE 衝突で close Tx 恒久失敗 [実機] | **M01 を検出** |
| 43 | X31 | submit_rejected (attempts=上限・同 Tx) → 明示 retry (attempts=0) → 再 rejected → 再 terminal。profile 変更での数え直しは新内容への正当な再試行 | 問題なし |
| 44 | X31 | reconcile close の kind 分岐 — (a) floor NULL 化は「kind=1 は」と明記され kind=2 へ誤適用されない。(b) は kind 共通で正しい | 問題なし |
| 45 | X32 | **fork 中断 (HISTORY_CLEARED)→フォルダごと別パスへ移動→次 tick: flag の realpath に journal 無し→「手順 4 の中間」と誤認して flag 掃除→再発見が old_id の root_path を新パスへ更新→空履歴 + old_id で新規コミット量産→後日 bootstrap が journal 検出→手順 2 から (手順 1 を再実行しない)→old_id 時代のコミットが new_id 配下に残存** → fsck 全 commit 偽破損 | **M02 を検出** |
| 46 | X32 | flag→journal 削除順の逆転残骸 (flag 残 + journal 無) → 回復 (a) の防御規定が flag を掃除。順序遵守なら発生せず、発生しても無害 | 問題なし |
| 47 | X33 | 課金記帳の網羅行列 (server/client × 9 終端 × 3 close 経路) を総当り → item 失敗セルだけ記帳列挙の外 (M06)、client 再実行の旧 seq 未記帳 (M08)。他セルは 0 or 1 行 | **M06・M08 を検出** |
| 48 | X33 | detached state=0 client → terminal 記帳→行削除→再登録→再投入 → seq は ledger MAX 継承で衝突なし [実機: COALESCE(MAX)=2 継承を確認] | 問題なし |
| 49 | X34 | §11.2 完全 SQL を実データで組み立て実行 — eligible の EXISTS が旧版 chunk (vec 距離最小) を正しく排除、alias なし FTS + bm25 + ROW_NUMBER 第 2 キー + RRF + 最終 ORDER BY 全て動作 [実機] | 問題なし |
| 50 | X34 | ready 未更新窓の横断検索 → KNN 停止 + FTS のみ + status「index 再構築中」。単独検索は embeddings 全行一致 + 未 embed 残数 status (完全性非主張) | 問題なし (窓の長さは M03) |
| 51 | X35 | 主張「seq 継承で行削除→再作成の UNIQUE 衝突は不可能」→ その経路は塞がったが、**同一行・同一 seq の二重記帳**という別経路が同じ UNIQUE を撃つ (M01)。「detached は課金を取りこぼさない」→ server state=0 の一覧消滅 edge (M05) | **M01・M05 に帰着** |
| 52 | 自由 | (a) FK CASCADE が AFTER DELETE trigger を発火し FTS 整合が保たれるか [実機: integrity-check 通過・MATCH 0 件]。(b) fork 手順 1 の defer_foreign_keys [実機: 即時検査でも成功する版 = 文書の「防御的指定」説明と一致]。(c) 空 Markdown (規則 7) → chunk 0 件・md 行 done・embed 対象なしで収束。(d) §16 の「既知の残余」参照 (M04)。(e) app_config DDL コメント (M09)。(f) reconcile close (c) の Tx 文言 (M07)。(g) agg_ready の「全フォルダ」× missing (M03)。(h) server intent 回復 × job 一覧の保持期限 (M05) | (a)(b)(c) 問題なし / **M03・M04・M05・M07・M09 を検出** |

---

## 第 3 部 — 新規検出

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| M01 | **fatal** | §9.1 L906「**terminal 化時の課金記帳**: …profile_changed…も cost_ledger へ記帳」+ L942–947「reconcile / submit が state=0\|3 を成果ありで閉じる際の付随処理 (同一 app Tx): …(b) batch_job_id 非 NULL…なら cost_ledger へ NULL + estimated で記帳」+ L755 UNIQUE + L879–881「UNIQUE(…submission_seq) が ledger の二重計上を構造的に防ぐ」 | 2 つの記帳義務が**同一 (repo, kind, target_key, submission_seq) への 2 回目の素朴 INSERT** を規定しており、UNIQUE と衝突する。「防ぐ」の実体は SQLITE_CONSTRAINT で、close Tx (state 更新 + 記帳が同一 Tx) が **abort → 毎 tick 再試行 → 恒久失敗**。行は state=3・成果ありのまま脱出不能 (submit は成果ありで投入せず、reconcile close は毎回衝突)。文書のどこにも記帳の冪等化 (OR IGNORE / 存在チェック) の規定が無い | 初期: profile A 現行、target T の embeddings(A) 行あり・state=2・ledger seq=1。→ ① profile を B へ変更 ② submit が成果なし (A≠B) で再投入 (相 1: profile_hash=B → 相 3: state=1, seq=2) ③ job 完了前に profile を A へ戻す ④ collect: item 成功だが行 profile_hash=B ≠ 現行 A → 破棄 + state=3 (profile_changed) + **記帳 (seq=2)** ⑤ 次 tick reconcile: 成果判定 = embeddings(T) が A = 現行 → **成果あり** → close + 付随処理 (b) で **再記帳 (seq=2)** → UNIQUE 衝突 → close Tx abort → 恒久ループ [SQLite 再現済み]。同型: client_exhausted の旧 seq 記帳 (L850) 後に成果あり化した場合 | P9 / K11 / L03 / C7 / C10-bb / X31 / X33 / X35 | close 経路の課金記帳 (collect 成功 / terminal 化 / reconcile・submit close / client_exhausted / detached) を**すべて「同 (repository_id, kind, target_key, submission_seq) の行が既に在れば追記しない」冪等追記 (INSERT OR IGNORE)** と明文化する。追記専用の意味論と矛盾しない (同一 seq = 同一課金事実の再観測)。併せて L879–881 の「防ぐ」を「衝突は再観測として黙って吸収する」に書き換える |
| M02 | **major** | §21.3 L2211–2212「毎 tick 冒頭に fork_in_progress の realpath の journal を確認 (…journal 無 = 手順 4 の中間 → fork_in_progress を掃除)」+ §20.4「再発見のたびに root_path を更新」+ 回復表「HISTORY_CLEARED: id = old → 手順 2 から」 | flag 掃除の判定が「journal がそこに無い」と「フォルダごと移動された」を区別できず、fork 中断中のフォルダ移動で (1) flag が誤掃除され中途 fork (履歴消失済み・id=old) が通常運用に復帰、(2) 再発見が fork 中 repo の root_path を更新して除外が外れ、old_id で新規コミットが量産され、(3) 後日の bootstrap 回復が HISTORY_CLEARED + id=old を「手順 2 から」再開して**移動中の old_id コミットを消さないまま id を new へ書換** → fsck の commit_record 再構築が全滅 (偽破損) + 実データの履歴が復旧不能 | 初期: tracked フォルダ F の fork が HISTORY_CLEARED で電断。→ ① ユーザーが F を同 watch_root 配下の別パスへ移動 (journal も同行) ② 次 tick: flag の旧 realpath に journal 無し → flag 掃除 ③ walk が旧 root_path 不在 → repository-id (=old) で再発見 → root_path 更新・通常 scan 復帰 ④ 空履歴に old_id で新規コミット多数 ⑤ 後日 bootstrap: journal 検出 → phase=HISTORY_CLEARED・id=old → 手順 2 から → id=new 書換・手順 3 (旧行退役 + 新 folders は journal の旧 realpath で INSERT) → ⑥ new_id 配下に old_id 時代の commits が残存 → fsck 全 commit hash 不一致 | C10-cc / L07 / X32 | (1) flag 掃除は「journal 不在」に加えて **flag の realpath に .folder-history 実体が現存すること**を確認して行い、実体ごと不在なら missing 同様に保留。(2) §20.4 の再発見 (root_path 更新) は **fork_in_progress の old_id / new_id を対象外**とする。(3) 回復の再開位置は phase に加えて実状態を確認 — **commits が空でなければ手順 1 から** (手順 1 は冪等なので常に 1 起点でも安全) |
| M03 | **major** | §8-e L617–619「破棄時に agg_building_profile_hash = 現行を書き ready を消す → **全フォルダの §9.3-c が完了した時点で** agg_ready_profile_hash = 現行へ更新」+ §11.2 L1464 (ready 照合、不一致中は KNN 停止) + §20.4 (missing 猶予 30 日) | 「全フォルダ」の集合定義 (missing / 一時読取不能 / fork 中除外を含むか) と「完了」の追跡方法 (sync_state に profile 列は無い) が未定義。missing フォルダが 1 つあると §9.3-c が実行不能のまま ready が更新されず、**横断 KNN が再接続または猶予満了 (最大 30 日) まで全面停止**する。実装者は集合と追跡の両方で追加の設計判断を迫られる | 初期: フォルダ A, B, C 登録済み、C は外付けドライブ上。→ ① C のドライブを取り外す (missing、猶予 30 日) ② embedding profile を変更 → Replicate 冒頭で agg 破棄 + building 書込 ③ A, B は同 tick で §9.3-c 完了、C は root_path 不在で実行不能 ④「全フォルダ完了」が不成立 → ready 未更新 → §11.2 が KNN を実行しない ⑤ C 再接続まで (最悪 30 日 + §9.3-d 退役まで) 横断検索が FTS のみ | C11-a / P8-e / L09 / X31 / 自由 | ready 更新条件を「**folders のうち missing / fork 中でない全行**が building profile で §9.3-c を完了」に限定し、完了追跡は sync_state に synced_profile_hash (または synced_at >= 破棄時刻) を持たせて宣言的に判定する。agg の意味論を「接続中フォルダの和」と明記 — missing フォルダの復帰分は §9.3-c の差集合が埋める |
| M04 | minor | §16 L1717「ledger は『記録できた課金』— 突合には batch_job_id を使う (**§9.1 の既知の残余**)」 | 参照先の §9.1 は L950 で「旧『既知の残余 (失効窓の課金行は記録できない)』は**解消される**」と宣言済み — 解消済みの旧概念名への参照が残り、読者を §9.1 に探しに行かせて空振りさせる (L03 の regression 条件そのものではないが参照の陳腐化) | 初期: 実装者が §16 を読む → ①「§9.1 の既知の残余」を §9.1 に探す ② 該当概念は「解消される」の否定文脈にしか無い → 参照解決不能 | C3 / X13 | §16 の括弧を「(§9.1 — ledger は記録できた課金であり、請求の最終的な正はプロバイダ側)」等の現行表現へ差し替える |
| M05 | minor | §9.1 L858「見つからなければ同 token の upload 残骸を削除してから、行を今回の投入対象へ載せ直す (新 intent_token で相 1 から)」 | server 経路の intent 回復が「job 一覧に無い = 未作成」を仮定しており、**job 作成済みだが provider 側の保持期限で一覧から消えた** (回復が長期遅延した場合) を区別できない。旧 job の課金が記帳されず (seq は載せ直しで進むため台帳に空番)、「未追跡 job は最悪 1 個」の有界化の外で二重課金が起きる。state=1 用の時刻基準 (job_missing、K08) と同型の規則が state=0 回復側に無い | 初期: 相 2b 完了 (job 作成済み)・相 3 前に電断 → 端末を 30 日停止。→ ① 再開 tick の intent 回復: token 照合 → 一覧に無い (保持期限切れ) ② 未作成と判定して残骸掃除 + 載せ直し (新 job = 再課金) ③ 旧 job の課金は ledger に載らない | X33 / X35 / P9 | intent 回復にも時刻基準を置く: 相 1 で intent 発行時刻を記録し、「発行から (timeout_hours + 保持期限 + 猶予) を超えた state=0 の照合不一致」は未作成と断定せず NULL + estimated の terminal 記帳を先に行ってから載せ直す (K08 と同じ枠組み)。adapter 契約に job 一覧の保持期間を明記する |
| M06 | minor | §9.1 L887「item 失敗 → UPDATE state=3 + error」と L906 の記帳列挙「(result_expired / job_timeout / output_missing / job_missing / profile_changed)」 | terminal 化時の課金記帳の列挙に **item 失敗 (一般 error) が含まれない**。provider が失敗 item に課金しない前提が暗黙で、課金するプロバイダでは台帳から漏れる。「実行された可能性のある課金を取りこぼさない」(同節) との整合が読み取れない | 初期: kind=1 job 実行、1 item が provider 側エラーで失敗。→ ① collect: state=3 + error (batch_job_id 非 NULL) ② 記帳列挙に該当せず ledger 行なし ③ 当該 provider が失敗 item にも課金する場合、台帳に載らない | X33 / C11-a | 列挙に item 失敗を加えて NULL + estimated で記帳する (M01 の冪等追記と併用)。または「provider が失敗 item に課金しない場合に限り省略できる (既定は記帳)」と前提を明文化する |
| M07 | minor | §9.1 L942「付随処理 (**同一 app Tx**): …(c) intent_token が残る行は upload / job 残骸の掃除を試みる」 | (c) は外部 API 呼び出し (upload 削除・job cancel) であり、相 1 の「外部 upload 削除は app Tx の外で行う」(L825) と同じ扱いのはずだが、「同一 app Tx」の列挙内に置かれ、実装者が Tx 内で外部呼び出しする読みを許す (Tx 長時間化・失敗時の close 巻き添え) | 初期: reconcile close 対象行に intent_token 残存。→ ① 実装者が (a)(b)(c) を 1 Tx に実装 ② (c) の外部削除が 429 で 30 秒ブロック ③ app.sqlite の書込 Tx が保持されたまま → 他処理が busy_timeout 超過 | C10-bb / X31 | (c) を「同一 Tx の対象は (a)(b) のみ。(c) は close 後に app Tx の外で試行し、失敗は次 tick 再試行 (相 1 の旧 upload 掃除と同じ規律)」と明記する |
| M08 | minor | §8 (iii) L643–646「前計上済み…の行は『実行された可能性がある』として扱い、遷移表の再投入判定 (attempts 上限) に従って再実行する」 | client の呼出中クラッシュ→再実行 (attempts < 上限) で、**旧 seq の課金が記帳されないまま新 seq へ進む** (課金 2 回・記帳 1 回になり得る)。client_exhausted (上限到達) のみ旧 seq を terminal 記帳する非対称。台帳の下限性 (§16) の枠内ではあるが、「実行された可能性のある課金を取りこぼさない」(§9.1) と一貫しない | 初期: client 前計上 (seq=1)・API 呼出中に電断 (provider は課金済み)。→ ① 回復: dispatch → attempts < 上限 → 再実行 (前計上 seq=2) → 成功 → 記帳 (seq=2) ② seq=1 の課金は永久に台帳外 | X33 / P9 (K11 規範との一貫性) | client の再実行時、新たな前計上 Tx の中で**旧 seq を NULL + estimated で terminal 記帳してから** seq+1 する (client_exhausted の扱いを毎回の再実行に一般化。M01 の冪等追記と併用) |
| M09 | minor | §9.1 L761–763 app_config DDL コメント「'agg_embedding_profile_hash' = agg_vec 構築時の embedding_profile_hash (§8-e の宣言的検査の基準)」 | §8-e (L617–619) は基準 key を **agg_building_profile_hash / agg_ready_profile_hash の 2 本**に再定義済みで、DDL コメントの単一 key 名はもう書き手が存在しない。§11.2 も ready を照合する。retry_not_before (L26) も key 列挙に無い。DDL コメントだけを読んだ実装者が旧 1 key 構成を作ると、§11.2 の ready 照合が永久不一致 = KNN 恒久停止 (幸い fail-closed 側)。コメントが §8-e を指しているため解決は可能 — minor | 初期: 実装者が §9.1 の DDL から app_config を実装。→ ① コメントどおり 'agg_embedding_profile_hash' 1 key を採用 ② §8-e/§11.2 の building/ready の書込・照合先が存在しない ③ 横断 KNN が恒久に「index 再構築中」 | C3 / C4 / L28 / X31 | DDL コメントの key 列挙を 'tool_profile' / 'embedding_profile' / 'agg_building_profile_hash' / 'agg_ready_profile_hash' / 'retry_not_before' に更新する (L28 の残存解消と同一の修正) |

---

## 第 4 部 — 確認済みの列挙

検出 0 件で確認済みの観点:

- **C1 (原則反映)**: P1〜P16 の全項目について対応記述の存在と一致を確認 — P1 (三層 + 規約 7 の 6 点
  + 有界 2 種 + 規約 9 二層注記) / P2 (JCS・識別子規範・768 参考値の非断定) / P3 (8 テーブル +
  行の存在 = 完了) / P4 (chunks 統一・CHECK・GENERATED — 実機通過) / P5 (分割 7 規則 + floor 同時
  引き上げ + 全量やり直し) / P6 (grammar v・meta 5 行・ページ結合後エスケープ・preflight terminal
  marker・課金単位ペア) / P7 (view content — 実機で rebuild / integrity-check / CASCADE→trigger
  発火を確認) / P8 (a〜e + client 前計上 + 実行前計上の有界化限定) / P9 (状態遷移・detached 規範・
  seq 継承・2 相 + 相 2a/2b) / P10 (書込順序・tick 構成・冪等) / P11 (カーソル JOIN・NULL 明示・
  逆差集合・z 2 条件・削除規則) / P12 (3 モード同名 CTE・eligible EXISTS・over-fetch/refill・
  小文字 hex・LIKE 分離 bind・FF 固定・chunk 単位 1 行) / P13 (GC 3 本目 Markdown 抽出・fail-closed
  hash 一致・fsck 3 層 + kind 別誘導 + 1 ストリーム repair) / P14 (DELETE journal・単一 Tx
  migration・rebuild・接続初期化・DACL) / P15 (commits / file_versions 不変) / P16 (3 層検知・
  三値・pending_deletes・最小不在時間・最終 stat・保存名固定・fail-closed 検証)
- **C2 (SQL 静的検証)**: metadata 8 表 + app 8 表 + agg 6 表 + FTS 2 基 + trigger 4 本の DDL を
  SQLite 3.51.0 で全通過。FTS5 external content の content には view (rowid を持つ chunks/agg_chunks
  由来) を指定 — WITHOUT ROWID 表の直接指定なし。FK 参照先・列数一致。trigger の INSERT/DELETE
  ペア整合 (CASCADE 経由の発火も実機確認)。「同形」省略 (agg_chunk_fts) は view 名・rowid 名の
  読み替えが明示され一意に再現可能
- **C4 (クエリとスキーマの整合)**: §11.1 (A)(B)(C)・§11.2 完全形・LIKE fallback 完全形・§9.3-a
  (NULL カーソル含む)・§5.3 の COALESCE(MAX) を実データで実行し、列・join キー・意味論とも一致
  (eligible が旧版 chunk を排除することも確認)
- **C5 (数値・事実の一貫性)**: $2.5/1k・$5 (+25%)・50% 割引・768 = 参考値 (3 箇所とも非断定)・
  RRF k=60・8 テーブル (2 箇所)・512MB・timeout 24h・保持 ~24h・猶予 30 日・最小不在 30 秒・
  時計閾値 72h・k_max 4,096・max_chars 2,000・attempts 既定 3 — 全出現一致
- **C6 (用語・形式)**: target_key の 2 形式 (§5.6 / §9.1 / §11.2 で小文字 hex 固定が一致)・
  chunk_type ↔ target_type 対応・obj:<hash64> スキーム・embed_hash = COALESCE の再掲一致
- **C8 (欠落)**: P1〜P16 の範囲で章として欠けている事項なし

検出ありの観点 (該当 ID): C3 → M04・M09 / C7 → M01 / C9 → L28 partially-fixed / C10 → M01・M02・
M07・M09 / C11 → M03 / C12 → M01・M02・M03・M05・M06・M08。

原則 P1〜P16 はすべて「反映確認済み」— M01〜M03 は原則の**未反映ではなく**、反映済み規範どうしの
相互作用が開けた新規の穴である。
