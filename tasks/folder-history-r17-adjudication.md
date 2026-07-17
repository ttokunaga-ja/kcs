# folder-history 設計書 r17 クロスシステム最終裁定記録

- 日付: 2026-07-17
- 対象: `docs/research/folder-history-sqlite-design.md` (裁定前 3,135 行 → 適用後 3,207 行)
- 監査プロンプト: `tasks/folder-history-design-audit-prompt.md` (r17 版 3,012 行 — C9=432 項目 A〜S、X1〜X66、新規 T 採番、判定語 3 語固定・読了証明義務)
- 運用: **初のパス渡し・自律読込ラウンド** (r16 の埋め込み方式から移行 — ユーザー指定)。作業 dir に target.md + audit-prompt.md を置き、起動メッセージは 1.1KB の指示のみ。codex には read + sqlite3 (in-memory) を許可、opencode は read 限定。
- 名寄せ・裁定: Fable。抽出 subagent (Sonnet) 7 本 → 争点のみ原文書突合の 2 段方式 (r16 確立)。

## 0. パネルと判定分布 (7 系統確定)

| 系統 | 判定 | 新規検出 | C9 (432) | 読了証明 |
|---|---|---|---|---|
| sol1 | 不合格 | fatal 主張 4 (T01-T04) | 全合格 (S01-S03 実 SQL 確認込み) | 『```』正確引用 |
| sol2 | 不合格 | fatal 3 + major 2 + minor 1 (T01-T06) | S07/S20 partially | 同上 |
| sol3 | 不合格 | major 4 + minor 1 (T01-T05) | S20 partially | 同上 |
| terra1 | 不合格 | major 3 (T01-T03) | S25 partially | 同上 |
| terra2 | 不合格 | fatal 1 + major 7 + minor 2 (T01-T10) | S20/S24 partially | 同上 |
| dsv4 | 合格 | minor 2 + proposal 1 (T01-T03) | 全合格 | L3134 引用 (末尾フェンス非コンテンツ解釈) |
| kimi | 「不合格」(誤記 — 実質合格) | 0 | 全合格 | 同上 |
| hy3 | — | **2 連続構造失敗で打ち切り** (読込ナレーションのみ 154B/4.9KB — free 級はパス渡し読込で崩壊) | — | なし |
| gem | — | **2 連続凍結で打ち切り** (並列 1 + 単独 1、WAL 停止 — r16 埋め込み方式では完走した系統。パス渡しの長 read ループとの相性) | — | なし |

- fatal 主張 **8 → 全降格 0** (標準基準維持: 有界課金・記録喪失は major)。
- **読了証明ゲートの成果**: 浅読み 2 本 (hy3/dsv4 初回) を機械検出、dsv4 は再実行で正規化。判定語 3 語固定が kimi のラベル矛盾を即検出。3 モデル (dsv4/kimi + r1 dsv4) が末尾コードフェンスを非コンテンツ扱い — 証明は「最終 2 行引用」が正 (スキルへ反映済み)。
- 「合格系統は過小検出」**7 例目** = kimi (C9 根拠が範囲一括定型句のみ・本文 125 行)。
- **codex 5 系統が X62/X63/X65/X66 の重心に全弾命中** — 検出主力は今回も codex。

## 1. 回帰補修 (4 — 全て r16 適用の非伝播・転記ミス。X66 が設計どおり検出、全て文書照合で実在確認)

| ID | 内容 | fix |
|---|---|---|
| **S20** (partially-fixed ×3: sol2 T04, sol3 T02, terra2 T03) | §4.1 の共通 record 例 (annotation_schema 込み) が r16 m8 の §5.7 shape 拒否と矛盾 + **metric/distance_metric の名称不一致 (r16 の私の転記ミス)** | §4.1 を kind 別 2 例に分離 (embedding は annotation_schema を持たない) + §5.7 を distance_metric に統一 (別名不可の明記) |
| **S24** (partially-fixed: terra2 T10+S24, sol2 T05) | rebind の旧 fp_cache DELETE が §21.1 missing 分岐のみ — 「別実体」分岐と §20.4 自動 rebind に非伝播 | 両所へ「rebind 共通 action (fp_cache DELETE 含む)」を明示 (掃除点は §9.3-d 含め 4 箇所に) |
| **S19** (sol2 T03 — fatal 主張→補修) | r16 m7 の「seq 現値」記帳は明示 retry 後の 2 度目の課金される拒否と UNIQUE 衝突 → ON CONFLICT が実課金を吸収 = 記録喪失 | 期限超 (ii) と同型の「seq +1 行 UPDATE + 新値で記帳」へ |
| **S25** (partially-fixed: terra1) | r16 m13 の既定 backoff が intent 回復 unknown 分岐のみ — 相 2a/2b・client・collect の各失敗分岐に非伝播 | 「一時失敗を扱う全分岐に共通適用 (各分岐の Retry-After 記述はこの共通則の再掲)」を明記 |

## 2. major 採用 (5)

| ID | 内容 (fix) | 系統 | 備考 |
|---|---|---|---|
| **M1 rotation 非リセット** | 相 1 の NULL 戻し列挙 (batch_job_id・error・completed_at) に job_create_started_at が無い — 旧 attempt の残置値を max() が拾い、時計後退と重なると未呼出 attempt の attempts 消費・偽 expired・estimated 記帳を反復 → 列挙に追加 | **5 系統** (sol1 T02, sol2 T01+S07, sol3 T01, terra1 T01, terra2 T01) | **r16 M4 が開けた穴 = 定番脈 20 例目 (X62 本命の勝利)** |
| **M2 migration NULL 意味論** | 旧版由来の state=0 token 保持行は NULL でも job 実在し得る — 「NULL = 未着手の証明」は列導入後限定とし、§14 に「列追加時は intent_token の時刻成分を backfill (同一 Tx)」を新設 + DDL コメント両側更新 | sol1 T01 (単独 + 裁定者検証) | X62×X66 複合 |
| **M3 cancelled × 遷移表 × token** | (a) cancel 確定 = **attempts=上限を同時設定** (submit_rejected の r10 前例と同型 — 遷移表の自動再投入対象から除外、復帰は明示 retry のみ)。(b) **batch_job_id NULL かつ token 非 NULL の行は cancel 確定禁止** (照合なき確定は実在し得る job を記帳なしで閉じる — detached 例外へ)。(c) **rotation ガード**: token 残存行の再投入は sweep 前段完了後 (先に rotation すると照合キー喪失) | **4 系統** (sol1 T03, sol2 T02, terra1 T02, terra2 T02 (fatal 主張)) | X63/X64 域。r16 M8 の残穴 |
| **M4 no-replace fallback** | 非対応 FS (ENOSYS/EINVAL/EOPNOTSUPP) で「黙って通常 rename」も文書適合になる穴 → 判定は初回試行エラーで確定 (ボリューム単位記憶可)・fallback は「再 lstat + 通常 rename + 残余窓の明示的引き受け」に限定・EEXIST 相当は常に中止 | **5 系統** (sol1 T04, sol2 T06, sol3 T05, terra1 T03, terra2 T08) | r16 M3 の残穴 (X65) |
| **M5 DOCX 変換の hash/upload 対応** | 変換 PDF = 一時生成物 (objects 非保存・content_hash は常に原本)・m10 再照合は原本→照合後に決定論的再変換して upload・upload_id/token 埋込は変換物へ・課金入力は job 応答 | terra2 T04 (単独・実装不能級) | C11 実装不能の解消 |

## 3. minor 採用 (8)

| ID | 内容 | 系統 |
|---|---|---|
| m1 | fork-journal record に started_at (app 全損後も journal 単体で stalled 判定) | dsv4 T01 |
| m2 | img block の v 混在 = fail-closed (先頭 block 前提の明文化 + 全 block 一致検査) | dsv4 T02 |
| m3 | resolver の採用規則 = walk の case 規則と同一実装の共有を明示 | dsv4 T03 |
| m4 | folder 側親子検査に text_hash 再計算照合 (件数のみ→内容。rebuild の破損固定化を防ぐ) | sol3 T03 (major 主張→minor) |
| m5 | query の NUL 拒否 (FTS5 MATCH の構文エラー防止 — :limit と同じ入力境界契約) | terra2 T05 |
| m6 | trigram FTS と LIKE fallback の case 折り畳み不一致 — 同一折り畳み適用が正・不能なら近似の明記 | terra2 T06 |
| m7 | per-dir case override は sensitive 方向のみ — casefold dir on sensitive volume は併存証拠が原理的に出ない旨 + 属性照会優先 + 分裂は喪失なしの既知挙動 | terra2 T07 |
| m8 | fts_hits / KNN k に内部上限 :fts_cap (外側 LIMIT では中間膨張を防げない) | terra2 T09 |

(terra1 T02 の「再投入の意図性明記」は M3(a) の attempts=上限で解消 — 吸収)

## 4. 却下 (2) + 品質注記

- **sol3 T04 (vector mantissa bit-rot 非検出)**: r16 却下前例の再演 (sol1 S10/sol2 S16) — 同一 key で値が変わる設計遷移なし・読める DB 内の沈黙 bit-rot は fsck 脅威モデル外・agg は破棄再構築で回復。値 hash 列の追加は見合わない。
- **kimi 判定ラベル**: 内容 (432 全 fixed・68 全問題なし・0 件) と真逆の「不合格」— テンプレ事故。実質合格として扱い記録のみ。
- 報告内部整合の注記: sol1 の X50/X7/X33/X53/X58 タグ脱落、terra2 の P9/P12 無言及、dsv4 の 65/66 件数自己矛盾、sol3 の T05 重大度根拠とシナリオの緊張 — いずれも指摘の当否には影響せず記録のみ。

## 5. 適用サマリ

- 文書: 3,135 → **3,207 行** (19 編集 = 補修 5 + major 7 + minor 7)
- 適用後検証: fence 80 (偶数) / job_create_started_at ×7 (DDL・相 1・相 2b・猶予・§14 で同期) / 「seq 現値」残存 0 / 「dimensions / metric」単独残存 0 / rebind の fp_cache 掃除 4 箇所 / cancelled + attempts=上限 ✓
- スキーマ変更: なし (M2 は migration 規範の追加)

## 6. r18 への申し送り

1. **検証リスト (U 採番… 次は T が新規検出済みなので検証リストは T01〜T17 相当)**: 補修 4 (S19/S20/S24/S25) の再発検査を最優先 + M1〜M5/m1〜m8 の期待状態化。特に「相 1 の NULL 戻し 4 列 (batch_job_id/error/completed_at/job_create_started_at)」「cancel 確定 = attempts 上限 + id 無し token 行の確定禁止」「§4.1 kind 別 2 例 ↔ §5.7 shape」「§14 backfill」の両側検査
2. **探索重心候補**: (a) rotation ガード (M3c) が開ける穴 — sweep 前段完了待ちと dirty 早回し tick の交錯・前段 unknown 時の再投入保留の滞留、(b) attempts=上限の cancel と明示 retry (attempts リセット) の相互作用 — retry 後の行が再 cancel された場合の循環、(c) fts_cap の RRF 再現率への影響と「途中で切れた rank 集合」の意味論、(d) 変換 PDF の再変換決定論が破れる場合 (コンバータ更新) の tool_profile 連動
3. **プロンプト整備**: P2 追補の「dimensions / metric」を「dimensions / distance_metric」へ同期 (今回の S20 fix に追随)。読了証明は「最終 2 行引用」へ強化 (スキル反映済みの規約をプロンプト側にも)
4. **CLI 運用**: パス渡し方式の適性 — codex 5 系統は完全適合 (SQL 実機検証込み)・kimi/dsv4 は再実行込みで可・**hy3/gem は不適** (hy3 = 読込体力不足、gem = opencode 長 read ループで凍結 ×2。gem は埋め込み方式なら完走実績あり — 方式選択はラウンド設計時に系統別で決めてよい)
