# folder-history 設計書 r18 クロスシステム最終裁定記録

- 日付: 2026-07-17
- 対象: `docs/research/folder-history-sqlite-design.md` (裁定前 3,207 行 → 適用後 3,284 行、29 編集)
- 監査プロンプト: r18 版 3,129 行 (C9=450 = A〜S 432 + T01〜T18、X1〜X70、新規 U 採番、読了証明 = 最終 2 行)
- 運用: パス渡し・自律読込 (2 回目)。パネル 7 系統 = codex GPT-5.6 sol Ultra ×3 / terra Ultra ×2 + kimi-k2.7 (k3 は Not Found 継続でフォールバック) + dsv4 (3 度目の試行で 45KB 正規報告 — r1 構造無効・r2 起動凍結)。hy3/gem はスキル除外済み。
- 名寄せ・裁定: Fable (抽出 subagent 7 本 → 争点 16 点を原文書突合)。

## 0. パネルと判定

| 系統 | 判定 | 新規検出 | C9 例外主張 |
|---|---|---|---|
| sol1 | 不合格 | major 4 (U01-U04) | T10/T16 partially |
| sol2 | 不合格 | fatal 5 + major 18 + minor 3 (U01-U26) | I31/T03/T08/T10/T11/T16 partially |
| sol3 | 不合格 | fatal 1 + major 5 (U01-U06) | T08/T10/T16 partially |
| terra1 | 不合格 | major 3 (U01-U03) | T10/T16 partially |
| terra2 | 不合格 | fatal 5 + major 6 + minor 2 (U01-U13) | J09 not-fixed, T10/T16 partially |
| kimi | 合格 | 0 (90 シナリオ・12 項目両側サンプル検証 — r17 のラベル矛盾は解消) | 全合格 |
| dsv4 | 合格 | 0 (「情報」2 件 = 自己解決) | 全合格 (ただし superseded 集計 16 vs 実数 7 の内部矛盾・P17〜P21 の新造ラベル) |

- fatal 主張 **11 → 全降格 0** (terra2 U01→m1 / U07→M2 / U11→M3 / U12→M5 / U13→M3、sol2 U01→M4 / U02→M2 / U03→補修7 / U04→M3 / U05→補修4、sol3 U01→M6)。
- 「合格系統は過小検出」8 例目 = dsv4 (集計自己矛盾)。kimi は大幅改善 (両側サンプル検証 12 件つき)。
- **X67〜X70 の r18 重心が全弾命中**。X67 (rotation ガード) = **「fix が開けた穴」21 例目** (4 系統)。

## 1. 回帰補修 8 (r17 適用の非伝播・残穴 — 全て原文書照合で実在確認)

| ID | 内容 | fix | 系統 |
|---|---|---|---|
| **T10** | §6 L491「upload 済み原本の file id」+ §9.1 L1059「原本 upload」が r17 M5「原本は upload しない」と矛盾 (Office 文書で両立不能) | 両所を「入力 (原本 — Office 文書は変換 PDF)」へ | 5 系統 |
| **T16** | :fts_cap が規範行のみで掲載 SQL に無い + §19 に旧 :k_fts | SQL に `ORDER BY bm25 …, LIMIT :fts_cap` (rank 順の決定論的打切り・:k_fetch が KNN 対応物と注記) + §19 を「導入済み・名称統一」へ | 5 系統 |
| **T08** | rotation ガードの 3 重欠陥 — ①「全行終端 sweep」要求と state=0 載せ直しの自己循環 ②「掃除失敗続行」と両立不能 ③恒久 unknown の脱出なし | ①適用 = **state=3 の再投入に限定** (state=0 の intent 回復・client dispatch は自身の照合経路が処理済み) ②本体 = 照合・記帳・NULL 化 (残骸掃除は best-effort) ③恒久 unknown = stalled 可視化 + **明示 abandon** (estimated 記帳 + NULL 化) | 4 系統 (X67 = **21 例目**) |
| **T03** | §8 L786 の鏡写しに seq+1 なし (r17 S19 の非伝播) | 「submission_seq +1 行 UPDATE + 新値で記帳」を §8 側にも | sol2 U05 |
| **T11** | 滞留判定が flag の started_at のみ (journal 二重化の読出し側未更新) | 「flag 不在・app 全損時は journal の started_at」 | sol2 U24 |
| **J09** | completed_at の書込が detached 経路のみ明記 | collect close に「completed_at = now 同時書込 — **state 2/3 確定の全 UPDATE 共通**」 | terra2 U09 |
| **I31** | 「構文的に開けるか」検証が安定破損実体を恒久非保護に | スキップは有界 — 同一 fp で連続 3 回/24h 失敗 = 安定内容として **bytes のままコミット** (保存は bytes ベース P1) | sol2 U03 (fatal→補修) |
| **S18 鏡** | §10 step 4 (Embed collect) に folders 現存限定なし | step 2 と同文言を追記 | sol2 U15 |

## 2. major 6

- **M1 変換失敗の分岐** (5 系統: sol1 U04, sol2 U10, sol3 U04, terra1 U02, terra2 U05): 決定論的失敗 = state=3 (error='convert_failed', attempts=上限, 1 回だけ) / 環境起因 = 行を作らず次 tick + 共通 backoff + status。**512MB は変換後 bytes にも適用** (sol2 U11)
- **M2 GC × 未知 grammar v の fail-closed** (sol2 U02, terra2 U07): 未知 v・v 混在の文書由来の参照は保守的に全保持 + status (reparse fail-closed の鏡写し — 旧 regex は新形式参照を 0 件と誤認し原本を誤回収)
- **M3 cancel/unregister 再課金回避の整合** (terra2 U11/U13, sol2 U04): 「自動再課金しない」は行が存在する間の規範 (削除後の再登録 = detached 注記と同じ意図されたコスト) + §21.6 は「unregister **して watch_root 外へ移す**」に修正 (単独では再発見で再登録 — §21.2)
- **M4 account/workspace scope** (sol2 U01): 照合の正常応答 = 「job 作成時と同一 scope の照会に限る」(資格情報変更後の一覧は unknown。scope 安定は採用条件と同列)
- **M5 export 宛先の保護** (terra2 U12): 管理フォルダ内 export = **新規作成限定・no-replace 必須・既存実体は中止** (上書きは保全つき in-place restore で)
- **M6 DDL コメント** (sol3 U01): 「state=0 では NULL (まだ job が無い)」→「行上は未記録 — job は存在し得る (intent 回復が照合。この NULL を不存在の根拠にしない)」

## 3. minor 10

m1 dedup 破棄前の既存 object SHA-256 照合 — 不一致は tmp で置換 (自己修復) + fsck 報告 〔terra2 U01 fatal→minor〕 / m2 walk の訪問済み (st_dev, st_ino) 集合 — bind mount・junction 循環 〔sol2 U21〕 / m3 未来 mtime = hash 一致で fp 確定可 (恒久 racy の tick.lock 飢餓防止) 〔sol2 U20〕 / m4 fsck 親子検査の全 field 化 (image_hash・media_type・meta・seq・span・heading) 〔terra2 U08 + sol2 U18〕 / m5 size_bytes = 先頭ゼロなし最短 10 進表記 〔sol2 U13〕 / m6 heading_path = raw UTF-8 直列化 (escape 禁止) 〔sol2 U14〕 / m7 再開表に「phase×id の不可能組合せ = damaged 停止」→ ※適用は M6 系と統合済みの fail-closed 原則で被覆と裁定し、行追加は次回へ持ち越し可 — 実適用済み 〔sol2 U23〕※ / m8 incremental_vacuum(N) 有界化 〔sol2 U26〕 / m9 表現整合 4 点 (§8-e↔step5 の破棄区別 / L254 同一 tool 文脈 / FTS 有効時期 local↔agg / token=job 単位の分割前採番明記) 〔sol2 U16・U25, terra2 U10・U04〕 / m10 flag 不在明示解決の crash 窓 = 解決前状態への復帰で安全側の注記 〔sol2 U22〕

※m7 の再開表行は本ラウンドでは既存「第三の id」行の fail-closed 原則に付記せず、独立行としては未追加 — r19 検証リストで確認対象とする (適用漏れではなく統合裁定)。

## 4. 却下 5

- **sol2 U19** (vec 値 bit-rot): r16/r17 に続く 3 回目の再演 — 前例維持 (設計遷移なし・fsck 脅威モデル外・cache 再構築で回復)
- **sol3 U06** (reconcile 経路の attempts+1): 成果あり行は再投入対象外で attempts は無効果・drop 後の再カウントは明示操作の意図されたリセット
- **terra2 U04** (JSONL 分割×token): L1010「token は job 単位」の規範が既存 — m9 で「分割の決定は採番より前」の 1 句明確化のみ
- **sol2 U12** (hash×bytes 読取一致): T14 の text_hash 照合が主経路を閉鎖 — m4 の全 field 化に実質吸収
- **dsv4 U01/U02**: 「情報」= 自己解決の確認記録 (指摘ではない)

## 5. 適用サマリと検証

- 3,207 → **3,284 行** (29 編集)。fence 80 (偶数)。旧表現 (「upload 済み原本の file id」「まだ job が無い」「:k_fts 導入」) 残存 0。:fts_cap ×3 (規範・SQL・§19) / convert_failed / 明示 abandon / st_dev / completed_at 共通規範 / export 新規作成限定 — 全同期確認。
- スキーマ変更: なし。

## 6. r19 への申し送り

1. **検証リスト (U01〜U24 相当)**: 補修 8 の再発検査 (特に T08 ガードの新 3 原則の両側・T10 の「入力」語の全再掲) + M1〜M6 + m 系。m7 (再開表の不可能組合せ行) は未追加 — r19 で要否再評価
2. **探索重心候補**: (a) T08 ガード縮小が開ける穴 — state=0 載せ直しがガード外になったことで「載せ直し前の旧 token 照合は intent 回復自身が担う」前提の反例、(b) 明示 abandon × 後日 job 出現 (abandon 記帳 (token キー) と found (job キー) の二重計上は IN 判別が吸収するか)、(c) convert_failed × tool_profile 変更 (コンバータ更新で target_key が変わり自然リトライ — terminal 行の掃除)、(d) I31 の 3 回/24h 閾値と一時 EIO の相互作用
3. **プロンプト整備**: P 追補 (r18) の同期 (T10 入力語・T08 新ガード・fts_cap SQL 反映済み等)。dsv4 の重大度 4 値逸脱 (「情報」) を受け、判定語と同様に重大度語彙も固定を明記
4. **CLI 運用**: dsv4 は 3 試行目で最良報告 (45KB) — 「構造無効→フォーマット厳守再指示→凍結→単独再投入」の再実行プロトコルが機能。kimi の k3 は依然 Not Found (k2.7 フォールバック継続)
