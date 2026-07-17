# folder-history 設計書 r19 クロスシステム最終裁定記録

- 日付: 2026-07-18
- 対象: `docs/research/folder-history-sqlite-design.md` (裁定前 3,284 行 → 適用後 3,348 行、28 編集)
- 監査プロンプト: r19 版 3,259 行 (C9=474 = +U01〜U24、X71〜X74、新規 V 採番、重大度 4 語固定)
- パネル: **6 系統** = codex GPT-5.6 sol Ultra ×3 / terra Ultra ×2 + kimi-k2.7。**dsv4 は 3 連続失敗で打ち切り** (r1/r3 = DSML ツール呼び出しがテキスト漏出する deepseek 側の直列化バグを今回の入力サイズで再現的に踏む・r2 = 起動凍結 259,592B シグネチャ)。k3 は probe ハングで今回もスキップ。
- 名寄せ・裁定: Fable (抽出 subagent 6 本 → 争点 14 点を原文書突合)。

## 0. 判定と降格

| 系統 | 判定 | 新規検出 | C9 例外主張 |
|---|---|---|---|
| sol1 | 不合格 | fatal 3 + major 5 + minor 2 (V01-V10) | U01 regression / U06 / U24 |
| sol2 | 不合格 | 18 件 (実質新規 13 — 5 件は C9 重複) | N23 / U01 / U06 / U11 / U24 |
| sol3 | 不合格 | major 8 + minor 1 (V01-V09) | U01 / U06 / U18 / U24 |
| terra1 | 不合格 | major 1 (V01 = fp×journal) | U01 / U06 |
| terra2 | 不合格 | fatal 1 (V01 = 有界スキップ) | U24 |
| kimi | 合格 | 0 (80 シナリオ・過小検出継続。作業ログ混入 + 証明 1 行ズレ) | 全合格 |

- fatal 主張 **9 → 全降格 0** (sol1 V01→M1 / V02→M2 / V08→M3、sol2 V01→M1 / V02→M2 / V03→M4 / V04→M3 / V05→補修5、terra2 V01→M3)。
- **X71/X72/X74/X27 が命中 — 「fix が開けた穴」22〜24 例目** (M3 = r18 I31 の永続化不在 (4 系統)、M1 = r18 ガードの state=2 穴 (2 系統)、M2 = r18 M4 の scope 保存基盤不在 (2 系統))。

## 1. 回帰補修 6 (全て原文書照合で確認)

1. **U01 regression** (4 系統): §6「列は原本用」「upload 原本の削除」「upload する objects/」+ §10「原本を投入」の 4 箇所 → 入力/変換物語へ統一 (再照合のみ「原本」を明示維持)
2. **U06** (4 系統): completed_at の DDL コメントを「確定する全 UPDATE で書く (全終端 error 列挙つき)」へ
3. **U24** (4 系統): 再開表に「ID_WRITTEN/APP_DONE なのに id=old = 不可能組合せ → damaged 停止」行を新設 (r18 の統合裁定を撤回 — 第三 id 条件では素通りが確定)
4. **U11** (sol2): §21.2「再 OCR/re-embed は発生せず」→「完成済み派生が保持されている場合」に限定 + detached/cancel 行の再課金明記
5. **N23** (sol2 V05): §21.6 の「原本を退避」回避策に「backfill ON では退避だけでは止まらない — backfill OFF と併用」の注記
6. **(P1) 宙吊り参照** (2 系統): 「保存は bytes ベース (P1)」→「(§1 の原則)」 (r18 の私の混入ミス)

## 2. major 5

- **M1 ガード state=2 穴** (sol1 V01, sol2 V01 — X71 = **23 例目**): rotation ガードを state IN (2,3) へ拡張 + 再投入経路に floor 明示再生成を明記 (sweep 終端定義との一致)
- **M2 scope snapshot** (sol1 V02, sol2 V02 — **24 例目**): batch_requests に **scope_id 列** (相 2b 直前の小 Tx で job_create_started_at と同時記録) + 照合の同一 scope 判定 = 行の scope_id と現照会の比較・NULL は unknown
- **M3 有界スキップの永続化** (4 系統 — X74 = **22 例目**): scan_cache に stat tuple 別 syntax_fail_count / first_failure_at (列追加) + reset 規則 (stat 変化・成功で reset、一時 EIO・安定確認失敗はカウント外)・24h 起点 = first_failure_at
- **M4 abandon の操作実体** (3 系統 — X72): 対象 = token 非 NULL (state 不問・state=0 恒久 unknown 含む)。単一 Tx: IN 判別 → seq+1 + token キー estimated 記帳 → state=3 (error='abandoned') + attempts=上限 + completed_at → token NULL 化。後日可視化は IN 判別が吸収
- **M5 fp スキップ × fork-journal** (terra1 V01 — X27): fp 入力から .folder-history 除外を明記 + **fp 一致スキップの例外に fork-journal 存在検査** (怠ると §21.3 (b) の検出が恒久に殺される)

## 3. minor 9

m1 未来 generated_at (now+skew 超) は :current_tool 候補から除外 + status 〔sol3 V04〕 / m2 (st_dev,st_ino) 不能 FS は watch_root を fail-closed 〔sol2 V12〕 / m3 alt の escape は「1 行正規化 + label 置換一度だけ」 (二重適用禁止) 〔sol2 V14〕 / m4 「99%」断定 → 効果上限の限定表現 〔sol2 V15〕 / m5 明示操作の N = 既定 30 秒・設定値・再試行可能エラー 〔sol2 V17〕 / m6 §18.2/18.3 の要約を (chunk_type, embed_hash) に統一 〔sol2 V18〕 / m7 fts_cap を**サブクエリ内側段**へ (window 入力の制限 — VM step 実測 1,074→70,374 の膨張を防ぐ) 〔sol1 V07〕 / m8 チャンク規則・フィルタは device-local — コピー再登録の規則差は明示一括再チャンクで収束の明記 〔sol1 V04〕 / m9 §13 に GC 実行点 (tick step 5 以降 — §21.3 と同一) の明記 〔sol1 V10〕

## 4. 却下 6

- agg 内容照合 (sol1 V06, sol3 V05) + agg_commits 部分喪失 (sol2 V09): cache scope 前例 (r17 terra1 S08 以来 3 度目) — 回復 = 破棄・再構築
- vec payload 改変 (sol2 V10): 4 度目の再演
- 時計 jump × 30 日退役 (sol3 V07): r13 S6-Q13 却下前例 — 再発見で可逆・detached 再課金は意図されたコスト
- sync_state 片側削除 (sol1 V05): §9.3-d は agg 4 表 + sync_state を 1 Tx で削除 = 原子的。片側喪失は手改変 scope
- resolver 規則併存 (sol3 V09): L2785 の単一規則 (BINARY 一致優先 + 昇順 tie-break) が正 — name_collision の敗者決定は別文脈で矛盾しない

## 5. 適用サマリと検証

- 3,284 → **3,348 行** (28 編集)。fence 80。旧表現 (「列は原本用」「upload 原本の削除」「(P1)」「state=3 (terminal) …再投入」) 残存 0。scope_id ×4・abandoned・syntax_fail_count・スキップ例外・不可能組合せ行・fts_cap ×3 同期確認。
- スキーマ変更: batch_requests に **scope_id TEXT** / scan_cache に **syntax_fail_count・first_failure_at** (M3)。

## 6. r20 への申し送り

1. 検証リスト (V01〜V20 相当): 補修 6 の再発検査 (U01 は 4 箇所全て + 「入力」語の全再掲) + M1〜M5 + m1〜m9。特に M2 scope_id と M3 カウンタ列の DDL↔規範↔照合点の 3 面一致
2. 探索重心候補: (a) scope_id が開ける穴 (記録前クラッシュ・provider の scope 概念差・resolver での canonical 化)、(b) abandon (error='abandoned') × 遷移表・削除条件・再登録、(c) fp スキップ例外の journal 検査コスト×大規模ツリー、(d) M1 ガード拡張後の state=2 floor 再生成×sweep の順序
3. dsv4 は DSML 漏出が入力サイズ依存で再現 — 再採用は入力縮小 (プロンプト分割) か opencode 側修正待ち。k3 は probe ハング — 次回も k2.7
4. kimi の作業ログ混入が再発 (2 回目) — 起動メッセージの禁止文言を「## Objective 等のセクション見出しの出力自体を禁止」と具体化
