# folder-history 設計書 r12 監査 — 裁定 (adjudication)

対象: `docs/research/folder-history-sqlite-design.md` (r11 適用済み・2,476 行)
裁定日: 2026-07-15
入力: 8 系統の r12 監査結果 (合格 2 / 条件付き合格 1 / 不合格 5)

## 系統の識別

| 略号 | 系統 | 判定 | 新規検出 |
|---|---|---|---|
| A | 45 シナリオ | 合格 | minor 2 / proposal 2 |
| B | 57 シナリオ | 不合格 | major 1 (damaged×ready) / minor 1 |
| C | 48 シナリオ | 合格 | minor 1 (5/6-key) |
| D | 42 シナリオ | 条件付き合格 | minor 3 / proposal 1 |
| E | Sonnet 68 シナリオ | 不合格 | major 4 / minor 5 |
| F | 53 シナリオ (SQL/FS fixture 実行) | 不合格 | C9 regression 1 + partially 5、fatal 3 / major 14 / minor 8 |
| G | 48 シナリオ | 不合格 | C9 partially 9、major 6 / minor 6 |
| H | 45 シナリオ | 不合格 | major 2 / minor 8 / proposal 1 |

集約判定: **不合格**。A/C の合格は過小検出 (F/G/E が独立検出した実欠陥を取り逃し)。C9 の fixed/superseded 判定は 8 系統中 6 系統一致 — F の「M01 regression」と F/G の partially-fixed 群は「r11 fix の周辺残存」として実文面照合の上で個別裁定 (下記)。

## 自己申告 2 件 (J04 と同じ透明性の原則)

1. **監査プロンプトの「5 種」は私の転記ミス** — r11 で app_config を 6 key に更新したのに、r12 プロンvotionの P9/M03 に「5 種」「5-key」と書いた (実 6 key)。A/C 系統が検出。文書側は無傷。→ プロンプト修正 (今回 fork_in_progress を追加するため最終的に 7 key)。
2. **r11 裁定の名寄せ落ち** — r11 の 6 系統 ~60 指摘の統合時に、A 系統の M02 (client 旧 seq 未記帳・fatal 判定)・M05 (retention)・M06 (共有 token guard)・M08 (lookup 429)・M09 (client API 分類)・M11 (§10 1job)・M12 (step0.5×detached)、B 系統の M14 (vec dim 元) を採用/却下いずれにも載せず落とした。r12 の F/G/H が同一実体を再検出 — 今回すべて裁定して回収する。

---

## MAJOR (採用 8)

### R1 — client 経路の中間クラッシュ attempt の旧 seq が台帳から永久欠落
- 検出: F-N01 (**fatal**), H-N01 (major)。r11 A-M02 (fatal、名寄せ落ち) の再検出
- 該当: §8(iii) L676–681 — 再実行は新前計上 (attempts+1・seq+1) だが、旧 seq の記帳は client_exhausted (上限到達) 分岐にしかない
- 事象: seq=1 で呼出中クラッシュ (provider 課金済み) → 再実行 seq=2 成功 → 記帳は seq=2 のみ。§9.1「実行された可能性のある課金を取りこぼさない」に違反
- **裁定: 採用 (major — F の fatal は降格**: ledger は「記録できた課金 = 下限」と明記済み・喪失は有界・クラッシュ確率に比例。ただし自らの規範との矛盾は実在)。修正: **再実行の前計上 Tx で、まず直前 attempt の submission_seq を NULL + estimated で冪等 terminal 記帳してから attempts+1・seq+1** (client_exhausted の記帳を毎回の再実行に一般化)

### R2 — server intent 回復の job 一覧照合が「照会失敗 = 不存在」に倒れ得る (二値)
- 検出: F-N04 (major)。r11 A-M08 (名寄せ落ち) の再検出
- 該当: §9.1 L901–905 —「見つかれば採用 / 見つからなければ載せ直す」の二値。detached (b) には「照合不能なら保持」があるのに attached 側に無い
- 事象: job 実在中に一覧照会が 429/断 → 不存在と解釈 → 載せ直しで二重 job = 二重課金。「最悪 1 job」の有界化は照会の信頼性に依存していた
- **裁定: 採用 (major)**。修正: found / confirmed-absent / **unknown (照会自体の失敗 = state=0 のまま保持・次 tick 再試行・Retry-After は retry_not_before)** の三値化 — detached (b) と同一規範

### R3 — 保持期限超の state=0 (相 2b 完了・相 3 前) が「未作成」と区別できない
- 検出: F-N02 (**fatal**)。r11 A-M05/D-M05 (名寄せ落ち) の再検出
- 該当: §9.1 L901–905 — 一覧に無い = 未作成の仮定。長期停止 (30 日+) で作成済み job が一覧から消えたケースを拾えない
- 事象: 旧 job の課金が無記帳のまま載せ直し (seq 未採番の attempt は記帳経路が無い)。相 3 前クラッシュ反復 × 保持期限超の組合せでは attempts も進まない
- **裁定: 採用 (major — fatal は降格**: 発生条件は「相 2b/相 3 窓のクラッシュ + 30 日級の停止」の重積で確率極小・1 事象 1 job に有界。ただし K08 と同型の時刻基準で安価に塞げる)。修正: **intent_token を UUIDv7 に固定し時刻成分 = 相 1 実行時刻とする** (列追加なし)。照合不一致かつ相 1 から (timeout_hours + 結果保持期限 + 猶予 1 日) 超は「未作成」と断定せず **submission_seq+1 + NULL + estimated の冪等記帳をしてから**載せ直す

### R4 — state=0 (server) の成果あり close が作成済み job の課金を落とす
- 検出: F-N03 (**fatal**)
- 該当: §9.1 L989–996 付随処理 (b) —「batch_job_id 非 NULL なら記帳」。相 2b 完了・相 3 前クラッシュの行は job 実在でも batch_job_id NULL
- 事象: kind=2 で profile A→B (再投入・相 2b 完了)→相 3 前クラッシュ→A へ戻す→reconcile が成果あり (embeddings=A=現行) で close → (b) は NULL で記帳せず、(c) が B-job を掃除 → 課金済み job が無記帳で破棄。単一デバイス・正規操作のみで再現可
- **裁定: 採用 (major — fatal は降格**: 記録喪失は 1 job 有界)。修正: state=0 (server・batch_job_id NULL) の成果あり close は、(c) の掃除で **token 照合により job 実在を確認したら、掃除前に小 Tx で submission_seq+1 + NULL + estimated を冪等記帳** (detached (b) と同型)

### R5 — ready 判定の母数から damaged が除外されていない
- 検出: B-N02 (major), H-N11 (proposal: 接続 0 件の空虚な真)
- 該当: §8-e L640 —「接続フォルダ (folders 行があり missing でも fork 中でもないもの)」。damaged (marker 消失・metadata 構造不正) は folders 行あり・root_path 現存 (missing でない)・fork 中でもない → 母数に残る → §9.3-c 永久未完了 → **ready 永久不成立 = 横断 KNN 全面停止** (missing を除外した理由がそのまま当てはまる)
- **裁定: 採用 (major)**。修正: 母数 = 「当該 tick に metadata を開けて §9.3 を実行できたフォルダ」(missing / fork 中 / damaged / 一時読取不能を除外)。**接続フォルダ 0 件の間は ready を更新しない** (空虚な真の防止 — H-N11 同時採用) + status

### R6 — profile 再訪 (P2→P3→P2) で陳腐化した synced_profile_hash が空 index の ready を騙る
- 検出: F-N08 (major)。隣接: G-N03 (ready 照合と KNN の同一スナップショット未規定)
- 該当: §8-e / §9.3-c — agg 破棄 Tx が sync_state.synced_profile_hash を触らない。P3 era が短いと全フォルダ synced=P2 のまま → building=P2 復帰と同時に全一致が即成立 → **wipe 直後の空 agg で ready=P2**
- **裁定: 採用 (major)**。修正: **破棄 (building 書込 + agg wipe) と同一 app Tx で sync_state.synced_profile_hash を全行 NULL に戻す**。付随: (i) §11.2 に「ready 照合と KNN は同一 read Tx (同一スナップショット) で実行」(G-N03、minor 相当)、(ii)「ready は設定時点の被覆宣言 — 以後の新規 content の embed 遅延による部分性は通常状態」の明確化 (G-M09 の誤読防止)

### R7 — 読み取り専用操作 (単独検索・履歴閲覧) が規約 12 の照合から漏れる
- 検出: E-N04 (major), F-N13 (major), G-N01 (major) — **3 系統収束**。r11 保留 A-M28 の再評価 (X40 指示どおり)
- 該当: §15 規約 12 L1866 頃 —「開いて書き込む・レプリケーションする全操作」に限定
- 事象: `.folder-history` を別 repo の実体に差し替え → 単独検索が警告なく別 repo の内容を当該フォルダとして返す (provenance 偽装が検出網から漏れる)
- 対立点: 全 open 照合 (fail-closed) にすると「フォルダ単体コピーを別マシンで検索」という層 1 自己完結 (§2) の正規利用が folders 行不在で不能になる
- **裁定: 採用 (major) — scoped 拡張**: (a) **対象パスが folders に登録済みの読み取りは照合必須** (不一致 = conflict、結果を返さない)、(b) **folders に行が無いパスの読み取り (未登録・持ち込みコピーの standalone 検索) は層 1 自己完結の正規利用として実行可 — ただし repository-id を provenance として表示する**

### R8 — 論理名 (NFC) → raw 物理名の逆解決が無い (restore / delete 最終確認 / fsck)
- 検出: E-N05 (minor), F-N11 (major), G-N06 (major) — **3 系統収束**。r11 保留 A-M18 の再評価
- 該当: §20.5 L2133 頃 (NFC 論理名) × §21.4 (in-place restore) × delete 最終確認 × fsck working copy 読取
- 事象: 正規化非依存 lookup の FS (NTFS / ext4) では、NFD 物理名の実体に NFC 名で書くと**別エントリを新規作成** — restore が二重実体 (name_collision、復元物が敗者になり得る) を作り、delete 最終確認は NFD 実体を「不在」と誤認し得る (macOS APFS は API が正規化非依存 lookup のため顕在化しない)
- **裁定: 採用 (major)**。修正: **共通の論理名→raw 解決規則**を §20.5 に定義 — 検証済み root の readdir 列挙から walk と同じ規則 (NFC + case 折り畳み + 採用規則) で raw エントリを解決して操作対象にする。対応エントリ無し: delete 確認 = absent / restore = 新規作成 (NFC で作成可) / fsck = 喪失報告。restore §21.4・delete 最終確認・fsck §13 から参照

---

## MINOR (採用 — 系統・実文面照合済み)

| # | 内容 | 検出 | 該当 | 修正 |
|---|---|---|---|---|
| m1 | cost_ledger DDL コメント「二重計上を構造的に排除」が M01 の禁句と同型で残存 (機構は全経路 ON CONFLICT 済み → **M01 = partially-fixed** と裁定) | F (regression 主張→降格), H-N09 | L793 | コメントを「同一 seq 1 行のみ — writer は必ず ON CONFLICT DO NOTHING (衝突 = 同一課金の再観測)」へ |
| m2 | §10 step 3 / step 5 の vec 照合が「次元」のみ (§8-c/e は次元+距離) | F-M10, G-M10 | §10 | 「次元・距離」へ統一 |
| m3 | §10「最悪でも job 1 回分に有界」が無限定 (§9.1 は server 限定明記) | F-N17, G-I07。r11 A-M11 落ち | L1387 | 「server-side batch 経路 — client は attempts 上限 (§8)」を付記 |
| m4 | §10 step 0.5「state IN (0,3) 全行」が detached 除外 (§9.1) を再掲しない | F-N05。r11 A-M12 落ち | §10 | 「folders 実在行のみ — detached は対象外 (§9.1)」を付記 |
| m5 | client 再実行が相 1 規則一式 (profile 不一致 attempts リセット等) を含むこと + 恒久 4xx = submit_rejected 同処置が未明記 | F-N06, B-N01。r11 A-M09 落ち | §8(ii)(iii) | 明記 (恒久 4xx は呼出未実行確定 = 記帳なしで terminal) |
| m6 | 相 2a (upload) の失敗分類が無い (相 2b のみ 2 分岐) | F-N07, F-L26 | §9.1 相 2a | 相 2b と同じ 2 分岐 + Retry-After を明記 |
| m7 | (c) token/job 掃除に共有 token の全行終端 guard が無い + 掃除失敗の再駆動が無い | F-M29。r11 A-M06 落ち | §9.1 | 掃除条件 = 同 token 全行終端 (4.5 の upload 条件と同型)。4.5 を token sweep に拡張 (成功で intent_token NULL 化 = 再駆動) |
| m8 | fork_in_progress の保存先・形式が未定義 | G-L07/M05 | §21.3 | app_config key 'fork_in_progress' (JSON {old_id, new_id, realpath}。fork 中のみ存在 — tick.lock 直列化で高々 1 件) |
| m9 | intent 採用の列挙に submitted_at が無い (「相 3 と同じ」とはあるが) | G-K08 | L901 | 列挙へ追加 (時刻基準 job_missing の入力) |
| m10 | fork 回復完了時の folders.root_path の値が未規定 (journal の凍結 realpath か発見パスか) + fork 手順 3 に同 root_path 別 id 退役が無い | E-N02, H-N08 (2 系統) + G-N05 | §21.3 手順 3 | root_path = **回復時に journal を発見した実パス** (journal.realpath は識別・flag 削除キー専用)。§21.1 M11 と同型の同 root_path 退役を手順 3 にも |
| m11 | 手順 4 の逆順理由文が M05 の flag 掃除規則と表面矛盾 | H-N06 | §21.3 | 「逆順は電断後の移動と重なると flag が掃除不能」へ精密化 |
| m12 | dirfd 適用列挙に fork 自身の書込 (journal・repository-id) が無い | E-N03 | §20.5 | 列挙へ追加 |
| m13 | agg_chunks に M17 の seq/span CHECK が未展開 | H-N10 | §9.2 | §5.4 と同一 CHECK を追加 |
| m14 | agg_vec 孤児 (E 無し V 有り) が再充填/コピーの INSERT と PK 衝突 → replicate 毎 tick abort | F-N09 | §9.3-c / §8-e | agg_vec への投入は DELETE→INSERT に統一 + fsck 検査を双方向差集合に |
| m15 | §21.6 注記 (a)「現在版なら」— backfill ON では過去版のみ参照でも自動再投入 (再課金) | A-N01, E-N06, F-N25, H-N05 (**4 系統**)。r11 保留 M-22 | §21.6 | 「現在版、または backfill ON では過去版参照でも」+ 回避 (backfill OFF / 先に unregister) |
| m16 | code fence の認識規則 (```/~~~・長さ・indent・EOF) が未定義 → チャンク境界の実装分岐 | E-N07, F-N18, G-N08, H-N07 (**4 系統**)。r11 保留 M-31 | §7 規則 1 | CommonMark fenced code block 規則に固定 + インデントコードブロックも対象と明記 |
| m17 | §2 の損失要約が規約 7-f と有界 2 種を欠く | E-N08, F-N15, G-N07, H-N03 (**4 系統**)。r11 保留 M-33 | §2 | (a)〜(f) + 2 種へ同期 (規約 7 を正と明記) |
| m18 | §21.5「watch_roots は…失われる (規約 7)」の参照先が不正確 (復元起点は規約 9) | F-N23 | L2428 | 規約 9 へ |
| m19 | §20.5 message「明示操作時のみ任意指定」だが手動 commit 操作が §21 に無い (到達不能) | F-N24 | L2198 | 「常に省略 — 手動 commit は未提供 (将来拡張 §19)」へ |
| m20 | delete 最終確認「構造的に防ぐ」の絶対表現 (確認〜commit の窓は残る) | F-N22 | §20.5 | 「実在ファイルへの偽 delete を防ぐ安価な最終防衛 — 確認直後の再作成は次 walk の create が是正する」へ軟化 |
| m21 | 非 UTF-8 名は fp の JCS string で表現不能 | F-N20 | §20.3 | fp 入力から除外 (管理対象外 — §20.4) と明記 |
| m22 | repository-id 検証失敗の分類 (一時 EIO / 構造不正 / 不一致 / 不在) が register (M13) 以外で未統一 | F-N21, G-M13 | 規約 12 / §20.4 | M13 の 4 分類を「フォルダ DB を開く全操作」に一般化 |
| m23 | app.sqlite のバックアップ手順が無い (WAL 中の main file 単独コピーは commit 済み ledger を失う) | F-N12 | §14 or 規約 7 | SQLite Online Backup / VACUUM INTO を規範化・raw copy 禁止 |
| m24 | img block 除去時の LF 処理が未定義 (text_hash 分岐) | F-N19 | §7 規則 4 | 「行全体 (行末 LF 含む) を除去・空行圧縮なし」+ test vector 言及 |
| m25 | missing 猶予中のフォルダの agg ヒットが解決不能 (「完全解決」主張と不整合) | F-N14 | §12 | 「missing フォルダのヒットは返してよいが解決不能 (missing) を status 表示 — 完全解決の主張は接続中に限る」 |
| m26 | phantom エスケープ (行頭 `\`) の un-escape がチャンク text 生成で未規定 → 原文と異なる text が恒久残留 | H-N04 | §7 | 「チャンク text 生成時、行頭 `\` + grammar 一致行は `\` を 1 つ除去 (可逆)」 |
| m27 | unregister→detached 終端→削除猶予窓での再登録が payload 破棄済み分を自動再投入 (再課金) — fork G と同族の未記載コスト | E-N01 | §21.2 / §9.1 | 意図されたコストとして 1 文注記 |
| m28 | §9.3-z が step 5 のため、バックアップ復元直後の最初の tick が巻き戻った LWW で step 1 の submit (課金) を先に実行し得る | E-N09 (major→降格: 有界・記帳される・restore+edge 条件) | §9.3-z / §10 | **z の判定を tick 冒頭 (step 0 前) にフォルダごと実行** — 検出フォルダは同 tick の step 0〜4 から除外し step 5 で wipe+resync |
| m29 | 一括再チャンクの中断後の再開駆動が未記載 | F-N10 (major→降格: 「規則版を行に持たない」は明示の設計選択) | §7 | 「中断後の再開は明示操作の再実行 (全量・冪等)。未完了は status」 |
| m30 | image_filter の「record とその hash」に対し app_config key は record のみ (hash key 未定義) | F-M12, G-M12 | §8 | record のみに整理 (比較は JCS bytes 一致 — hash key は持たない) |
| m31 | §5.3 の seq 継承適用点「register 後の全行作成」が誤読を招く (register は行を作らない) | D-N01 | §5.3/§9.1 | 「再登録後の初回投入 (相 1) を含む全 INSERT」へ言い換え |
| m32 | §10 step 3 の vec 作成・照合の「現行 profile」参照元が §5.7 (新規フォルダでは空) | D-N04。r11 B-M14 落ち | §10 step 3 | 参照元 = app_config の embedding_profile record と明記 (§5.7 は履歴保管庫) |
| m33 | :current_tool / :current_profile の bind 型 (raw BLOB32) が未明記 — hex TEXT bind は無音 0 件 | G-N09 | §11.2 契約 | at_hash と同じ BLOB bind 規則を明記 |
| m34 | §18.4「複数フォルダを 1 job に積む効率」が §10 の 1 job = 1 repository と矛盾 | G-N10 | §18.4 | 「1 repository 内の複数対象を 1 job に積む効率」へ |
| m35 | folders.last_seen_at の書込規則 (INSERT/再発見/rebind/fork) が未定義 | G-N11 | §9.1 DDL | 「INSERT・再発見・rebind で now」をコメントへ |
| m36 | case 感度「フォルダごとに固定」× ボリューム間移動の再判定が未定義 | G-N12。r11 保留 M-34 | §20.5 | 「判定は走査時のボリューム属性 (移動後は新属性で再判定・保存名は不変。sensitive 化で現れた case 違い実体は別系列 = create)」 |
| m37 | fsck profile repair の DELETE→INSERT が同一 Tx と未明記 | G-N04 (major→降格: 二重障害前提) | §13 | 「同一 Tx (BEGIN IMMEDIATE)」を明記 |
| m38 | 監査プロンプト P9/M03 の「5 種」「5-key」(実 6 key) — 私の転記ミス | A-N02, C-N01 | プロンプト | 修正 (fork_in_progress 追加後は 7 key として r13 で同期) |

## 却下 / 再却下 (理由付き)

| ID | 検出 | 裁定 | 理由 |
|---|---|---|---|
| unregister tombstone | F-N16 (major) | **再却下** | r11 で裁定済み・§21.2 に「意図されたトレードオフ (規約 7-f)」を明記済み。F の指摘は明記文の存在と両立する挙動記述 |
| upload handle 上書き | F-I08 (partially-fixed 主張)。r11 A-M07 | **却下 (明記済みの既知の残余)** | §9.1 相 1 が「削除は失敗しても続行 — 残骸はプロバイダ保持期限で自然消滅する既知の残余」と自己文書化済み |
| fsck の agg 次元不整合検査 | D-N02 | 却下 | §8-e の毎 tick 次元・距離照合が既に検出・破棄再構築する — fsck の重複検査は不要 |
| vec_hits の optimizer 依存 | D-N03 (proposal) | 却下 | vec0 の KNN は `MATCH + k=` 制約を vtab (xBestIndex) が処理する仕様 — SQL の結合順序ヒントの問題ではない |
| fsck 検出のみの明確化 | A-N03 (proposal) | 却下 (既対応) | §13 に「fsck が直接 DELETE / INSERT はせず検出のみ」と明記済み |
| ready の新規 chunk P→NULL | G-M09 (partially 主張) | 却下 (意味論明確化で対応) | ready は「空間一致 + 設定時点の被覆」の宣言。設定後の新規 content の embed 遅延は通常状態 (async) — R6 の付随明確化に含める |

## Severity 裁定メモ

- F 系統の fatal 3 (R1/R3/R4) はすべて **major へ降格**: いずれも「課金の記録喪失 (有界)」であり、クラッシュ/データ喪失/無限ループ/非有界課金ではない。ledger は「記録できた課金 = 下限」(§16) と明記済み。ただし §9.1 の「取りこぼさない」規範との内部矛盾は実在するため採用。
- F の「M01 = regression」は **partially-fixed へ降格**: 全 close 経路の本文は ON CONFLICT 済みで、残存は DDL コメント 1 行 (m1 で修正)。
- E-N09 (z 順序)・F-N10 (再チャンク再開)・G-N04 (fsck Tx) は major→minor 降格 (理由は各行)。

## 適用範囲の提案

- **必須**: R1〜R8 (major 8)
- **推奨**: m1〜m38 (minor — 全て実文面照合済み・局所修正)
- **却下・再却下**: 上表 6 件
