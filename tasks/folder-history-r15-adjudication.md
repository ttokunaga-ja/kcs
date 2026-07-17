# folder-history 設計監査 r15 — 名寄せ裁定記録

日付: 2026-07-17
対象: `docs/research/folder-history-sqlite-design.md` (裁定前 2,916 行 → 適用後 3,039 行)
入力: 7 系統 (監査プロンプト準拠 6 + 独立レビュー 1)
ユーザー合意: 全部適用 (fatal 主張 6 件は全降格、回帰 3+1 は自己申告)

| 系統 | 概要 | 判定 | fatal/major 主張 |
| --- | --- | --- | --- |
| S1 | 独立レビュー (プロンプト非準拠、R1-R20) | — | 致命的 1 + 重大 4 |
| S2 | 条件付き合格 (R01 minor + R02 proposal) | 条件付き合格 | 0 |
| S3 | 条件付き合格 (60 シナリオ、minor 2 + proposal 4) | 条件付き合格 | 0 |
| S4 | 合格 (→ `folder-history-design-audit-r15-s4.md` へ改名) | 合格 | 0 (候補 5 件を自己棄却) |
| S5 | 不合格 (`audit-report-r15.md`、60 シナリオ、SQLite 再現) | 不合格 | fatal 3 + major 8 |
| S6 | 不合格 (57 シナリオ) | 不合格 | fatal 1 + major 5 |
| S7 | 不合格 (58 シナリオ、SQLite + sqlite-vec 実行検証) | 不合格 | fatal 2 + major 15 |

**集約判定: 不合格 → 全採用項目を適用済み。** fatal 0 (6 件の fatal 主張は全降格 — 基準:
恒久停止・データ喪失・SQL 非機能のみ。過大記帳・contract 前提・文書内矛盾は major/minor/補修)。
**S2/S3/S4 の合格系判定は過小検出** (回帰 3 件を素通し — 「合格系統は過小検出」の傾向 4 回目)。

---

## 自己申告 (r14 適用の転記漏れ — 回帰補修 4 件)

r14 で私が適用した修正の伝播漏れ・列挙ミス。S5/S6/S7 が独立検出した。

| ID | 系統 | 内容 | 補修 |
| --- | --- | --- | --- |
| Q02 | S6/S7 (fatal 主張含む) | §10 step -1 に除外例外を書いたが **§9.3-z 側 (L1413) の「step 0〜4 の対象から除外」を直し忘れ** — 文書内矛盾が残存 | §9.3-z に §10 と同一の例外 (step 2/4 の collect・detached は除外しない) を鏡写し |
| Q04 | S5/S6/S7 | 期限超の結びを「以上 **(i)〜(iii')** を 1 Tx」と書いた — (iii') 挿入時に (iv) を列挙から落とし、「すべて同一 Tx」宣言と自己矛盾。(iv) Tx 外読みだと記帳確定後・rotation 前クラッシュ反復が**載せ直しゼロ回のまま attempts を再消費して偽 expired** (S5 の派生指摘) | 「**(i)〜(iv) の DB 書込を 1 Tx** ((iv) の外部 upload 削除の呼出だけ Tx 外)」へ正確化 + 偽 expired の理由文を追加 |
| Q09 | S5 | §9.3-d と fork 手順 3 の「§21.2 と同一」**パラフレーズが upload/token ガード 2 条件を落としている** — 局所記述に従う実装が再駆動キーを道連れに削除 | 両箇所を完全な 3 条件 (cancel/terminal + upload 清掃 + intent_token IS NULL) へ |
| Q12 | S5/S6/S7 (fatal 主張含む) | §21.4 は再 lstat を義務化したが **§20.5 側 (L2484) の「任意の強化 — 義務ではない」が残存** | §20.5 を「in-place restore では義務 (§21.4)・delete 確認/fsck では任意」へ |

## major 採用 — 8 件

| ID | 系統 (元 severity) | 内容 | 適用 |
| --- | --- | --- | --- |
| **N1** | S5-R01 (fatal, SQLite 再現) + S7-R17 | **found 記帳 (発見 job id) → 掃除前クラッシュ → job が一覧から消滅 → 期限超記帳 (token) が「未記帳」と誤認**し同一 job を 2 行計上 — 述語キーの時間差分裂 (r14 M1/M2 の照合点追加が生んだ穴) | (b')・sweep の found 記帳の小 Tx に**行の batch_job_id = 発見 job id の UPDATE を含める** — 行の自己記述化で以後の sweep 前段 (batch_job_id NULL 対象) から構造的に外れる |
| **N2** | S5-R02 (fatal) | 伝播猶予 10 分を**超える正常な stale 一覧**では、作成済み job の「未作成」誤認載せ直しが attempts/seq/記帳の消費なしに反復 — 未追跡 job が理論上無制限 | **プロバイダ採用条件を明文化**: 「job 一覧の可視化遅延上限 ≤ 伝播猶予」を必須契約とし (猶予は provider 別設定可)、保証できない provider では有界化が成立しないと明記 |
| **N4** | S3-R03/R04 + S5-R04 + S7-R08 (4 系統) | **detached state=0 の「記帳してから削除」が削除ガード (intent_token IS NULL) とデッドロック** — state=0 のまま sweep の「全行終端」条件に入れず token を NULL 化する経路が無い。**r14 M4 が開けた穴 = 定番脈 16 例目** | detached (a)/(b) の記帳 Tx で **state=3 (error='detached'/'expired') + completed_at を確定** → 4.5 の掃除・NULL 化 → 削除条件成立で削除、の段階遷移へ統一 |
| **N5** | S5-R05 + S6-R06 + S7-R07 (3 系統) | **client submit_rejected の token 永久残留** (batch_job_id NULL 戻し (r13) で sweep 照合対象に入るが client に job 一覧が無く恒久 unknown → 削除ガードで削除不能) + server 側の未作成確定行への期限超 phantom 記帳 | sweep 前段の照合対象から **error='submit_rejected' (未作成/未実行の確定) を除外し、照合・記帳なしで残骸掃除 → NULL 化** |
| **N7** | S2-R02 + S5-R08 + S6-R02 + S7-R12 (4 系統) | :current_tool の **generated_at 同時刻 tie 未規定** + **一括ローカル変換が旧 tool 派生の generated_at も進めて世代選択が逆転** (r14 M5 の穴) | tie-break (tool_profile_hash バイト昇順) を規範化 + 「最後に触れられた世代の決定論的選択 — 厳密な『最後の OCR 生成 tool』復元は層 1 の目的外」の近似注記 |
| **N10** | S2-R01 + S5-R10 + S7-R10 (3 系統) | **journal の一時読取不能と digest 不整合を区別せず履歴破棄 (明示解決) へ誘導** — 規約 12 の「読めない ≠ 壊れている」と矛盾 (r14 M8 の穴) | §21.1 手順 1・§21.3 の両方で三値化: 破損 = 読めたが digest 不整合のみ / 一時読取不能 = 無変更保留 + status |
| **N16** | S6-R07 (fatal) + S7-R05 (2 系統) | **相 1 の旧 upload 削除が「同 upload 共有の全行終端」ガードを迂回** — 再投入する行が state=1 の同輩と共有する upload を先に消して回収不能 = 二重課金 | 相 1 の削除条件に「同 upload を共有する全行が終端 (2/3) している場合のみ (4.5 と同条件)」を追加 |
| **N-esc** | S5-R09 + S6-R03 + S7-R15 (3 系統) | **§6 エスケープ (緩いパターン) と §7 un-escape (「`\` + grammar 一致形」= 厳密読み) の非対称**で `\![diagram](obj:see appendix)` 型の `\` が残留 + **grammar 再 materialize の再エスケープで `\` が累積**。r14 の m14 見送りを **X56 の再評価が正当に覆した** (見送り時に検討しなかった第三の修正方向) | **decoder (un-escape) の条件を §6 と同一の緩いパターンへ拡張** (画像チャンクの認識は行全体厳密一致 + 実在検証のままで phantom 防止は不変) + 「再 materialize は本文を再エスケープしない (保存時 1 回限りの変換)」 |

## minor 採用 — 17 件

| # | 系統 | 内容 → 適用 |
| --- | --- | --- |
| N3 | S5-R03 (fatal→minor) | 規約 6 に floor 引き上げ (app→metadata) の例外併記 — 本規約は参照の存在保証の順序で fence 系意図書込には適用しない (§7 の順序規範が優先) |
| N6 | S5-R06/S7-R09 (major→minor) | 相 1 に「旧 intent_token 非 NULL の再投入時は token ベースの未記録 upload 残骸の削除を先に試みる」(rotation の探索キー喪失対策) |
| N8 | S6-R05 (major→minor) | fsck に FTS の external content 照合つき integrity-check — 不一致は local = rebuild / agg = synced NULL + 親 DELETE で全置換駆動 |
| N9 | S6-R10/S7-R14 | LIKE fallback に `c.text IS NOT NULL` — fallback が FTS の対象集合を広げない (text=NULL 画像チャンクの 3 文字境界非対称の解消) |
| N11 | S5-R11/S7-R11 (major→minor) | 破損 journal 明示解決の順序規定 — journal 除去 (flag 残置) → 手順 2 → flag は既存 (a) 規則が回収。途中クラッシュが既存機構で冪等収束 |
| N12 | S7-R04 (major→minor) | profiles PK 単独充足の前提 (tool/embedding record の構造的排他) を注記 — record 仕様変更時は kind 判別フィールドで分離 |
| N13 | S7-R13 (major→minor) | fsck の親子/FTS 修復 Tx で agg_ready_profile_hash も削除 (修復中の部分 index が ready を騙らない) |
| N14 | S7-R18 (major→minor) | fork 回復表に「実体 id が old/new 以外 = damaged 停止 / 一時読取不能 = 保留」の行を追加 |
| N15 | S5-R07 (major→minor) | 「非課金 provider では ON CONFLICT で無害に skip」の事実誤認修正 — ON CONFLICT は同一 seq の再観測のみ吸収。非課金確定 provider は記帳省略可 |
| N17 | S6-R09/S7-R06 (major→minor) | 一括変換の operation record (app_config、hint) — クラッシュ後の「未完了の可能性」status を可能に (正しさは再実行の全量置換が担う) |
| N18 | S6-R04 | 除去・un-escape 後の本文が空白のみの文書は text チャンク非生成 |
| N19 | S6-R08 | profile 未設定時の skip を reconcile/collect 成果判定・§8-c vec 検査・§8-e/Replicate へ拡張 (state=1 は保留 — 再入力後の collect が記帳) |
| N20 | S5-R12 | §21.4 に raw 不在 = 保全対象なし (安定確認失敗と区別) として新規作成、を明記 |
| N21 | S7-R16 | profile 設定の適用前に vec0 受理検証 (一時 CREATE 試行) — 不支持設定は commit せず status |
| N22 | S6-R01 (major→minor) | 伝播猶予は過去側のみ (0 ≤ now−token ≤ 猶予) と定義し、未来 skew 判定が常に優先と明記 |
| N23 | S6-R11 | app_config「すべて必須」を key 別の存在条件 (profile 系 = bootstrap 後必須 / fork_in_progress = fork 中のみ 等) へ |
| N24 | S1-R20 (致命的→minor) | §14 に auto_vacuum = INCREMENTAL + fsck 週次での incremental_vacuum 注記 (DB 単調肥大の防止) |

## 却下・見送り

| 指摘 | 理由 |
| --- | --- |
| S4 の「合格」判定 | 不採用 — found 枝どうしの比較のみで「述語対称」と結論し、S5 が SQLite 再現した found→期限超の**時間差**分裂 (N1) を見落とし。回帰 3 件 (Q02/Q04/Q12) も素通し。自己棄却 5 件のうち R56 (escape) の棄却も誤り (実文書の un-escape 条件は厳密読みが自然 → N-esc で解消)。R1 (synced)・R41・R42 の棄却は正当 |
| S1-R2 (sync_state 孤児) | **精読不足** — §9.3-d が sync_state を削除対象に明記済み |
| S1-R9 | 「規約 13」は存在せず誤引用 |
| S1-R1/R3/R5/R6/R8/R10/R11/R16/R19 | 既決 (tick.lock 直列化 / ts 確定月 (r14 m3) / 残余窓明記 / GC は tick 内 + r14 注記 / §21.6 注記 (r13) / §20.4 明記 / §8-a / estimated 区分 / 静止バックアップは明記された設計) |
| S1-R7/R12/R13/R14/R15/R17/R18 | スコープ外・見送り (record 肥大 / error 体系は規範列挙済み / objects 圧縮 / access control (単一ユーザーローカル) / テスト戦略 / ATTACH (自己 DB) / プロバイダ冗長 (§1/§19 の確定範囲)) |
| S7-R05 の upload_id 上書き部分 | 既知の残余 — **5 回目却下** (共有ガード部分のみ N16 で採用) |
| S3 proposal ×4 / S2-R02 の proposal 部分 / S4-R01/R02 | 見送り (テスト計画・UI 文言・図示・共通ルーチン集約・表示層) — N 系 fix が実質対応 |

## 全指摘 ID 対応表

| 系統 | ID → 対応 |
| --- | --- |
| S1 | R1 却下 / R2 却下 (精読不足) / R3 既決 / R4 対応済 (r14 m22 + N19) / R5 既決 / R6 却下 / R7 見送り / R8 既決 / R9 却下 (誤引用) / R10 既決 / R11 既決 / R12 却下 / R13 見送り / R14 見送り / R15 見送り / R16 却下 / R17 見送り / R18 既決 / R19 却下 / R20 → **N24** |
| S2 | R01 → **N10** / R02 → **N7** |
| S3 | R01 見送り / R02 見送り / R03 → **N4** / R04 → **N4** / R05 見送り / R06 見送り |
| S4 | 判定不採用 / R01 見送り / R02 見送り / (自己棄却 R51/R46 → N1 が実体、R56 → N-esc が実体、R1/R41/R42 の棄却は正当) |
| S5 | Q04/Q09/Q12 → 補修 / R01 → **N1** / R02 → **N2** / R03 → N3 / R04 → **N4** / R05 → **N5** / R06 → N6 / R07 → N15 / R08 → **N7** / R09 → **N-esc** / R10 → **N10** / R11 → N11 / R12 → N20 |
| S6 | Q02/Q04/Q12 → 補修 / R01 → N22 / R02 → **N7** / R03 → **N-esc** / R04 → N18 / R05 → N8 / R06 → **N5** / R07 → **N16** / R08 → N19 / R09 → N17 / R10 → N9 / R11 → N23 |
| S7 | R01 → Q02 補修 / R02 → Q04 補修 / R03 → Q12 補修 / R04 → N12 / R05 → **N16** (一部 5 回目却下) / R06 → N17 / R07 → **N5** / R08 → **N4** / R09 → N6 / R10 → **N10** / R11 → N11 / R12 → **N7** / R13 → N13 / R14 → N9 / R15 → **N-esc** / R16 → N21 / R17 → **N1** / R18 → N14 |

## 適用後の検証

- 残存禁止パターン 0: 「以上 (i)〜(iii') を」「任意の強化 — 義務ではない」「(すべて必須 — DDL」
  「してから削除 / (b)」「非課金 provider では ON CONFLICT で無害に skip される」
- 新規パターン出現確認: (i)〜(iv) の DB 書込 / プロバイダ採用条件 / 行の batch_job_id へ発見 job id ×2 /
  submit_rejected 除外 / error='detached' ×2 / 共有全行終端ガード / §9.3-z 例外 / un-escape 対象判定 /
  再エスケープ禁止 / operation record / tie-break / c.text IS NOT NULL / FTS integrity-check ×3 /
  auto_vacuum / kind 判別 / vec0 受理検証 / 一時読取不能 ×5 / 第三の id / raw 不在区別 / 猶予の過去側定義
- 行数: 2,916 → 3,039 (+123)

## 次ラウンド (r16) の要点

- 検証リスト: 補修 4 (Q02/Q04/Q09/Q12 の再確認 — **転記漏れの再発検査を最優先**) + N1〜N24/N-esc を
  R 採番で追加。重点: (a) N1 の batch_job_id 自己記述化が collect/照会経路 (idx_batch_open・
  job_missing 時刻基準) と衝突しないか、(b) N4 の error='detached'/'expired' terminal と遷移表・
  再登録 (detached→attached 復帰) の整合、(c) N5 の submit_rejected 除外が「実は課金された拒否」を
  取りこぼす面 (Q18 の provider 前提とセット)、(d) N-esc の decoder 拡張の往復検証 (手書き
  `\`+パターン行の意味論)、(e) N2 の採用条件と Mistral 実仕様の突合
- 新規検出は S 採番 (R は r15 使用済み)
- 見送り論点: なし (m14 は N-esc で解消)
