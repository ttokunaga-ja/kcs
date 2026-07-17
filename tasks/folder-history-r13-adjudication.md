# folder-history 設計書 r13 監査 — 裁定 (adjudication)

対象: `docs/research/folder-history-sqlite-design.md` (r12 適用済み・2,657 行)
裁定日: 2026-07-15
入力: 8 系統 + 追走 1 (合格 2 / 条件付き合格 3 / 不合格 4)

## 系統の識別

| 略号 | 系統 | 判定 | 新規検出 |
|---|---|---|---|
| A | Sonnet 73 シナリオ (SQLite fixture 併用) | 条件付き合格 | minor 2 |
| B | 45 シナリオ | 条件付き合格 | minor 2 / proposal 1 |
| C | 49 シナリオ | 不合格 | major 2 / minor 1 |
| D | 45 シナリオ | 不合格 | fatal 4 / major 8 / minor 1 |
| E | 52 シナリオ (中文・重複貼付 = 1 系統) | 条件付き合格 | minor 2 / proposal 1 |
| F | 48 シナリオ | 合格 | 0 |
| G | 50 シナリオ | 不合格 | fatal 6 / major 9 / minor 5 / proposal 1 |
| BG | 61 シナリオ (C9 partially 4 主張) | 不合格 | fatal 6 / major 10 / minor 2 |
| H | 追走 64 シナリオ (自称 r14) | 合格 | 0 (proposal 2) |

集約判定: **不合格**。F/H の合格は過小検出。C9 は 8/9 系統が 307 全 fixed/superseded — BG の partially-fixed 4 件 (N03/N04/N13/N15) は「r12 新設規範の周辺の穴」であり、実文面照合の上で新規検出側 (下記クラスタ) に統合して裁定した (N 項目自体の記述は文書に実在するため fixed 維持が正確)。

**芯**: fatal + 上位 major はすべて **r12 が新設した「無 id 課金の記帳」ファミリー** (期限超 confirmed-absent・(b')・token sweep) に集中 — X41 の狙いどおりで、「fix が開ける穴」定番脈 13 例目。破壊型 regression は 3 ラウンド連続 0。

---

## 全指摘 ID 対応表 (r13 宣言 — 全系統の全指摘を採用/却下/降格に対応付ける)

| 系統-ID | 重大度(主張) | 裁定 | クラスタ |
|---|---|---|---|
| A-O01 | minor | 採用 | R12 (規約12×fork 除外) |
| A-O02 | minor | 採用 | R13 (TOCTOU 軟化一般化) |
| B-O01 | minor | 採用 | m-B1 (mapping 表の bind 給源注記) |
| B-O02 | minor | **却下 (既記載)** | — detached 採用は「profile snapshot は相 1 のまま不変」を明記済み (L1065) |
| B-O03 | proposal | 却下 | :limit の文脈別上限は実装裁量 (契約は正整数+上限のみ) |
| C-O01 | major | 採用 (fatal 昇格) | **R1** |
| C-O02 | major | 採用 | **R2** |
| C-O03 | minor | 採用 | m-C1 (preflight marker を seq 継承列挙へ) |
| D-O01 | major | 採用 | **R6** (§6/§7 un-escape) |
| D-O02 | major | 採用 (minor 降格) | m-D1 (§13 embedding 修復の vec 順序) |
| D-O03 | fatal | 採用 | **R1** |
| D-O04 | fatal | 採用 (major 降格) | **R3** |
| D-O05 | fatal | 採用 (major 降格) | **R4** |
| D-O06 | major | 採用 | **R2** (unknown 分岐を含む) |
| D-O07 | fatal | 採用 (major 降格) | **R5** |
| D-O08 | major | 採用 (minor 降格) | m-D2 (step -1 三値) |
| D-O09 | major | 採用 (minor 降格・注記対応) | m-D3 (z 後の in-flight collect 残骸は不可視・§21.6 で破棄可の注記) |
| D-O10 | major | 採用 (minor 降格) | R13 に統合 (rename 直前の再確認は任意の狭窄化として記載) |
| D-O11 | major | 採用 (minor 降格) | m-D4 (flag 掃除に marker id = new/old 一致要件) |
| D-O12 | major | 採用 (minor 降格) | m-D5 (自動 rebind 条件の明確化) |
| D-O13 | minor | 採用 | m-D6 (sync_state 初回行 + hex↔BLOB 変換契約) |
| E-O01 | minor | 採用 | R12 |
| E-O02 | minor | 採用 | R13 |
| E-O03 | proposal | 採用 | **R2** に統合 |
| G-O01 | fatal | 採用 | **R1** |
| G-O02 | fatal | 採用 (major 降格) | **R3** |
| G-O03 | fatal | 採用 (major 降格) | **R2** |
| G-O04 | fatal | 採用 (major 降格) | **R4** |
| G-O05 | fatal | 採用 (major 降格) | **R5** |
| G-O06 | fatal | 採用 (major 降格) | **R7** (restore の working 保護) |
| G-O07 | major | 採用 (minor 降格) | m-G1 (submit_rejected の batch_job_id NULL 戻し) |
| G-O08 | major | **再却下** | upload handle 上書き — §9.1 相 1 が「既知の残余」と自己文書化済み (r11 A-M07・r12 F-I08 と同一。3 回目) |
| G-O09 | major | 採用 | **R8** (§5.3 md 不在 sentinel floor) |
| G-O10 | major | 採用 (minor 降格) | m-D2 |
| G-O11 | major | 採用 | **R6** |
| G-O12 | major | 採用 | **R9** (§21 操作前の fork 回復先行) |
| G-O13 | major | 採用 (minor 降格) | m-G2 (profile_record の state 連動 CHECK) |
| G-O14 | major | **却下** | kind=1 の target_key と embedding_vec の target_key は別表・別キー空間で、各定義箇所に形式が明記済み — C6 で 5 系統が一貫と判定。改名は churn のみ |
| G-O15 | major | 採用 (minor 降格) | m-G3 (§10 step 2/4 冒頭に detached 処理を再掲) |
| G-O16 | minor | 採用 | R13 |
| G-O17 | minor | 採用 | R12 |
| G-O18 | minor | 採用 | m-G4 (floor_generated_at の kind CHECK) |
| G-O19 | minor | 採用 | m-G5 (upload_cleaned IN (0,1) CHECK) |
| G-O20 | minor | **却下** | SQL 3 値論理で TRUE OR UNKNOWN = TRUE — :cursor_at IS NULL が真なら行値比較の UNKNOWN は結果に影響しない。cursor_at 非 NULL 時は hash も非 NULL (対で設定) |
| G-O21 | proposal | 却下 | 規模閾値は §19 の再検討境界が既に受け皿。外部 API と tick.lock は §21 前文 + M29/Tx 外規範の範囲 |
| BG-N03 (partially) | — | 採用 | **R1**+**R3** に統合 (N03 自体は fixed — 周辺の穴として新規側で扱う) |
| BG-N04 (partially) | — | 採用 | **R2** に統合 |
| BG-N13 (partially) | — | 採用 | m-G1 に統合 |
| BG-N15 (partially) | — | 採用 | m-BG1 (§10 4.5 の doc 側 token sweep 列挙 — **私の r12 転記漏れ**: プロンプト P10 は更新済み・doc §10 の行が未更新) |
| BG-O01 | fatal | 採用 | **R1** |
| BG-O02 | fatal | 採用 (major 降格) | **R3** |
| BG-O03 | fatal | 採用 (major 降格) | **R2** |
| BG-O04 | fatal | 採用 (major 降格) | **R4** |
| BG-O05 | major | 採用 (minor 降格) | m-G1 |
| BG-O06 | fatal | 採用 (major 降格) | **R5** |
| BG-O07 | major | **再却下** | = G-O08 (既知の残余) |
| BG-O08 | major | 採用 (minor 降格) | m-BG1 |
| BG-O09 | major | **再々却下** | unregister tombstone — r11 降格・r12 再却下・§21.2 に意図されたトレードオフとして明記済み (3 回目) |
| BG-O10 | major | 採用 (minor 降格) | m-BG2 (規約 7(a) の server/client 限定) |
| BG-O11 | major | 採用 | **R6** |
| BG-O12 | major | 採用 | **R9** |
| BG-O13 | fatal | 採用 (major 降格) | **R7** |
| BG-O14 | major | 採用 | **R9** に統合 |
| BG-O15 | major | 採用 (minor 降格) | m-BG3 (migration の tick.lock + writer の user_version 再確認) |
| BG-O16 | major | 採用 | **R8** |
| BG-O17 | minor | 採用 | m-BG4 (§8 冒頭の §5.7 参照残存 — N40 の §8 側) |
| BG-O18 | minor | 採用 | m-BG5 (watch_root 解除 Tx で配下 fp_cache DELETE) |
| F / H | — | 検出 0 | — |

降格の一般根拠: 課金の**記録喪失** (有界・ledger は「記録できた課金 = 下限」と明記) は r11 以来一貫して major。fatal は「恒久停止・復旧不能・SQL 不動作」に限定 — R1 のみ該当 (記帳 INSERT が制約違反で intent 回復が恒久停止)。

---

## FATAL (採用 1)

### R1 — 無 id 記帳の batch_job_id NOT NULL 違反 (期限超 confirmed-absent)
- 検出: C-O01, D-O03, G-O01, BG-O01 (**4 系統**、うち 2 系統が SQLite 実再現)
- 該当: §9.1 L829 `batch_job_id TEXT NOT NULL` × 期限超記帳「submission_seq+1 + NULL + estimated」(server state=0 は batch_job_id NULL — 入れる値が存在しない)
- 事象: 規定どおり実装すると INSERT が NOT NULL 違反 → **intent 回復が当該行で恒久停止** (r12 の私の新設規範が ledger スキーマと突合されていなかった)
- **裁定: 採用 (fatal)**。修正: **無 id 記帳の batch_job_id = intent_token** (client 経路 §8(i) の流用規則を一般化 — job id 不明の記帳の突合キー)。(b') は照合で発見した実 job id を使う。cost_ledger コメントに「batch_job_id = job id / client 実行 id / intent_token (無 id 記帳)」を明記

## MAJOR (採用 8)

### R2 — (b') 記帳の再駆動と「記帳済み判別」が無い
- 検出: C-O02, G-O03, BG-O03/N04, D-O06, E-O03 (**5 系統**)
- 事象: (b') は close Tx の外 — close commit 直後の電断 / 照合 unknown / 共有 token の繰延べで記帳が飛ぶと、以後は 4.5 token sweep しか token を再訪せず、**sweep の仕様は掃除 + NULL 化のみ** → 課金済み job を無記帳で掃除。さらに再駆動させても「(b') 済みか」を seq では判別できない (seq+1 は非冪等 — 再実行のたび別 seq で推定行が増殖)
- **裁定: 採用 (major)**。修正 (3 点セット):
  (i) **記帳済み判別の述語**: 無 id / (b') 記帳の前に「同 (repository_id, kind, target_key) で batch_job_id = 当該 intent_token (または発見 job id) の ledger 行の有無」を確認し、既存なら記帳しない (seq+1 もしない) — R1 の token 記帳がこの述語の突合キーを兼ねる。
  (ii) **token sweep に (b') と同一の前段を義務化**: batch_job_id NULL × intent_token 残存の終端行は「token 照合 → 実在かつ未記帳なら小 Tx で seq+1 + NULL+estimated → 掃除 → 成功で NULL 化」。
  (iii) **unknown は掃除も NULL 化もせず保持** (次 tick sweep 再試行 — detached (b) の三値と同一規範)

### R3 — 期限超記帳の非原子性 + attempts 不消費
- 検出: D-O04, G-O02, BG-O02/N03 (**3 系統**)
- 事象: 記帳 (seq+1) と載せ直し (新 token 相 1) が別 Tx だと、間のクラッシュ反復で毎回 seq+1 の推定行が増殖。また 相 2b 完了済み (job 作成 = 課金) の attempt を attempts に数えないため、上限が実行回数を制約しない
- **裁定: 採用 (major)**。修正: 期限超の「記帳 + attempts+1 + 載せ直し相 1 (新 intent_token 書込)」を**同一 app Tx** に固定。R2-(i) の述語 (旧 token での既記帳確認) が Tx 前クラッシュの再試行増殖も止める

### R4 — detached state=0 server に期限超判定・記帳が無い
- 検出: D-O05, G-O04, BG-O04 (**3 系統**)
- 事象: attached 側は r12 で期限超記帳を得たが、detached (b) は「不存在を確認できたら掃除して削除」のみ — 保持期限で一覧から消えた課金済み job を無記帳で削除
- **裁定: 採用 (major)**。修正: detached (b) に attached と同一の期限判定を適用 — confirmed-absent かつ期限超は R1/R2 の規則で記帳してから削除、期限内は削除、unknown は保持 (既存)

### R5 — UUIDv7 期限判定 × wall clock 急変
- 検出: D-O07, G-O05, BG-O06 (**3 系統**)
- 事象: 未来時計で作られた token は時計修正後に age が負 → 恒久に「期限内」→ 課金済み job を無記帳で載せ直す (逆方向の後退は期限超の過剰記帳 — R2-(i) の述語と冪等で無害)
- **裁定: 採用 (major)**。修正: 「token 時刻成分が now + 許容 skew (既定 5 分) より未来、または解釈不能な場合は期限超と同様に扱う (安全側 = 記帳してから載せ直し — 過剰記帳は述語と estimated 区分が吸収)」

### R6 — §6/§7 un-escape の非対称 (原文 `\`+grammar 行の変質)
- 検出: D-O01, G-O11, BG-O11 (**3 系統**) — **私の r12 修正のバグ**: §7 の un-escape 括弧書きは「元から `\`+grammar 形の行は §6 で `\\` になる」と主張するが、§6 のエスケープ条件 (L533) は裸の grammar 形のみで `\` 前置行を対象にしない → 原文 `\![x](obj:H)` が §6 素通り → §7 が `\` を 1 個除去 → チャンク text が原文と不一致
- **裁定: 採用 (major)**。修正: §6 の対象を「**0 個以上の `\` に続いて grammar 形が現れる行**」に拡張 (常に `\` を 1 個前置: G→\G、\G→\\G) — §7 の 1 個除去と往復可逆になる。test vector に 3 段 (G / \G / \\G) を明記

### R7 — in-place restore が未取り込みの working 変更を消す
- 検出: G-O06, BG-O13 (**2 系統**、いずれも fatal 主張)
- 事象: 最終 scan 後に編集された working 内容 B (未コミット) の上へ旧版 C を restore → B はどこにも残らない (履歴化前のデータ喪失 — 履歴ツール自身の操作で起きる)
- **裁定: 採用 (major)**。修正: 「in-place restore は書込前に対象ファイルを安定確認し、現内容が LWW と異なれば**先に通常のコミット (§20.5 手順) で履歴化してから**上書きする (tick.lock 下で競合なし。エクスポートは対象外)」

### R8 — §5.3 明示再生成が md 行不在で floor を作れない
- 検出: G-O09, BG-O16 (**2 系統**)
- 事象: drop-derivation 後 (md 行なし)・過去版のみ・backfill OFF — §5.3 の INSERT 分岐の floor 値の基準 (現在の generated_at) が存在せず、floor 未設定だと backfill OFF での候補化経路が無い → §21.6→§5.3 の文書化された回復連鎖が実装不能
- **裁定: 採用 (major)**。修正: §5.3 の INSERT 分岐は **floor_generated_at = 0 (sentinel — 派生不在・任意の新結果が成果)** を設定する、と明記 (floor 設定済み = backfill 無関係候補の既存規則で機能する)

### R9 — §21 明示操作が pending fork の回復より先に実行され得る
- 検出: G-O12, BG-O12/O14 (**2 系統**)
- 事象: fork クラッシュ (ID_WRITTEN) → 次 tick 前にユーザーが unregister(old) → 次 tick の回復が手順 3 で folders(new) を再 INSERT → **unregister の意図が取り消される**。別 fork の起動も単一 flag を上書きし得る
- **裁定: 採用 (major)**。修正: §21 前文に「**各操作は tick.lock 取得直後に、まず §21.3 の回復 (flag/journal 走査) を完了してから本体を実行する**」を追加 — 未完 fork を跨いだ操作の反転と flag 上書きを構造的に排除

## MINOR (採用 16)

| # | 内容 | 検出 | 修正 |
|---|---|---|---|
| m-C1 | seq 継承の適用点列挙に **§6 preflight marker INSERT** が無い (第 4 の INSERT 経路) | C-O03 | 列挙へ追加 (MAX 継承で統一 — 無例外化) |
| m-D1 | §13 embedding 修復誘導が vec の削除順を再掲しない (embeddings だけ消すと vec 孤児 → collect INSERT が PK 衝突) | D-O02 | 「同一 Tx で embedding_vec → embeddings の順」を誘導文に再掲 + fsck のローカル逆差集合 (vec 孤児) 検出を明記 |
| m-D2 | step -1 の z 判定が読取不能のフォルダの扱い未規定 | D-O08, G-O10, BG(X44) | z = verified / regressed / **unreadable (= 未検証 — step 0〜4 から除外・保留)** の三値に固定 |
| m-D3 | z 検出後も旧 in-flight job の collect が巻き戻った履歴に無い content の派生を作る | D-O09 | 注記: 「z 後の collect は通常どおり実行してよい — 巻き戻り後の履歴に無い content の派生は eligible に現れず (§11 版フィルタ)、不要なら §21.6 で破棄」(fence 機構は作らない — 課金済み結果の破棄はしない) |
| m-D4 | fork flag 掃除が marker の中身を確認しない (旧パスが別 repo に再利用されると誤掃除) | D-O11 | 掃除条件に「marker の repository-id が journal の old/new と一致する場合のみ」を追加 (不一致・読取不能は保持) |
| m-D5 | 旧 root_path が別実体で再利用された場合の自動 rebind 条件が「無ければ」限定 | D-O12 | 「walk が folders の root_path と異なる位置で同一 id を発見し、旧位置が当該 repo の実体でない (marker 無し/別 id) 場合も rebind (§21.1 の判定の自動化。同一 id が 2 箇所実在する場合のみ conflict)」 |
| m-D6 | sync_state 初回行の作成規則と synced_profile_hash (BLOB) × app_config (lower hex TEXT) の変換契約が無い | D-O13 | 「初回 Replicate で INSERT (カーソル NULL・synced_at=now)。building との比較は hex を BLOB へ復号して行う (§11.2 の BLOB bind 契約と同一)」 |
| m-G1 | client の submit_rejected 後も batch_job_id (=token) が残存 → 後日の成果あり close (b) が未実行 attempt を誤記帳 | G-O07, BG-O05/N13 | 「client の submit_rejected は同 Tx で batch_job_id を NULL へ戻す (実行 id ではなくなった — 残すと (b) が未実行を誤記帳)」 |
| m-G2 | profile_record が DDL 上 NULL 許容 (本文は相 1/前計上で必須) | G-O13 | `CHECK (state NOT IN (0,1) OR profile_record IS NOT NULL)` を追加 (preflight marker 等の terminal 行は対象外のまま) |
| m-G3 | §10 step 2/4 が detached 処理 (冒頭実行 — §9.1) を再掲しない | G-O15 | step 2/4 の行に「冒頭で §9.1 detached 処理」を追記 |
| m-G4 | floor_generated_at に kind CHECK が無い | G-O18 | `CHECK (floor_generated_at IS NULL OR kind = 1)` |
| m-G5 | upload_cleaned に 0/1 CHECK が無い | G-O19 | `CHECK (upload_cleaned IN (0, 1))` |
| m-BG1 | §10 の 4.5 行に token sweep が無い — **私の r12 転記漏れ** (プロンプト P10 のみ更新・doc 未更新) | BG-O08/N15 | 4.5 行を「Upload 掃除 + token sweep」に更新 (§9.1 参照) |
| m-BG2 | 規約 7(a)「再投入 1 回分」が無限定 (client は attempts 上限) | BG-O10 | 「(a) 未回収 job の再投入 (server = 未追跡 1 job / client = attempts 上限内 — §8/§10 と同一の限定)」 |
| m-BG3 | migration の tick.lock と常駐 writer の user_version 再確認が未規定 | BG-O15 | §14 に「migration は tick.lock 下で実行。全 writer は lock 取得後・Tx 開始時に user_version を再確認」 |
| m-BG4 | §8 冒頭の起動時検査が「§5.7 の record から読む」のまま (N40 の §8 側残存) | BG-O17 | 「app_config の embedding_profile record から読む (§5.7 は履歴保管庫 — 単独フォルダの検査は §11.2 の一意 profile 規則)」へ |
| m-BG5 | watch_root 解除後の配下 fp_cache は M&S の walk 主体が消えて掃除されない (§21.5 の主張と矛盾) | BG-O18 | 「解除 Tx で、残存 watch_roots / folders の walk 範囲外になる配下 fp_cache 行を明示 DELETE」へ差し替え |
| m-B1 | §11.2 の単独検索 mapping 表に bind 給源の変更 (app_config → §5.7/一意 profile) の注記が無い | B-O01 | mapping 表に 1 行注記 |
| — | R13 (TOCTOU 軟化の 3 呼出点一般化 + restore の rename 直前再確認は任意) | A-O02, E-O02, G-O16, D-O10 (**4 系統**) | resolver 定義に「解決〜実操作の狭い窓は 3 呼出点共通の残余 — 次回 walk が name_collision / update として収束。restore は rename 直前の再 lstat で窓を狭めてよい (任意)」 |
| — | R12 (規約 12 × fork_in_progress の相互参照) | A-O01, E-O01, G-O17 (**3 系統**) | 規約 12 に「fork_in_progress の対象 (old_id, realpath) は呼出元を問わず照合の適用対象から除外 (§21.3 — 共有ガード)。fork 中の読取は conflict ではなく『fork 進行中』status を返す」 |

## 却下 / 再却下 (8)

| ID | 裁定 | 理由 |
|---|---|---|
| BG-O09 | **再々却下** | unregister tombstone — r11/r12 で裁定済み・§21.2 に意図されたトレードオフとして明記済み |
| G-O08 / BG-O07 | **再却下** | upload handle 上書き — §9.1 相 1 が「既知の残余 (プロバイダ保持期限で自然消滅)」と自己文書化済み (r11/r12 に続き 3 回目) |
| G-O14 | 却下 | kind=1 key と vec target_key は別表・別空間で各定義箇所に形式明記済み — C6 を 5 系統が一貫と判定 |
| G-O20 | 却下 | SQL 3 値論理: TRUE OR UNKNOWN = TRUE — cursor_at IS NULL が真なら行値比較の UNKNOWN は無害。非 NULL 時は hash も対で非 NULL |
| B-O02 | 却下 (既記載) | detached 採用に「profile snapshot は相 1 のまま不変」が実在 (L1065) |
| B-O03 | 却下 | :limit の文脈別上限は実装裁量 |
| G-O21 | 却下 | 規模閾値は §19 の再検討境界が受け皿。lock 外 API は M29/(c) 規範の範囲 |
| D-O09 (機構部分) | 降格採用 | fence 機構は却下 (課金済み結果を破棄しない) — 残骸の不可視性と §21.6 破棄可能性の注記のみ採用 (m-D3) |

## 適用範囲の提案

- **必須**: R1 (fatal) + R2〜R9 (major 8)
- **推奨**: minor 16 + R12/R13 (全て実文面照合済み・局所修正)
- **却下・再却下**: 上表 8 件
