# folder-history 設計監査 r14 (2916 行版) — 監査報告

対象: `docs/research/folder-history-sqlite-design.md` (2916 行、r14 修正適用済み)
日付: 2026-07-16
体制: 回帰確認 2 エージェント (A–I / J–Q スライス) + 探索 3 エージェント (X1–20 / X21–40 / X41–56+自由) + オーケストレータ自身による要点直接照合

---

## 合否判定

```
前提条件   : 満たす — 探索ログ 60 シナリオ (X1〜X56 全観点 + 自由探索を実行。56 シナリオ下限を超過)
判定       : 合格
合格根拠   : (1) C9 回帰確認 374 項目すべて fixed または superseded、regression 0
             (2) 新規検出に fatal / major が 0 件
                  — 探索エージェントが挙げた 2 件の major 候補 (R51/R46, R56) は
                    オーケストレータが原文を直接照合し「いずれも誤検出 (false positive)」と判定
                  — R1 (synced_profile_hash 陳腐化) も誤検出
             (3) minor / proposal 級の観測は残るが、合格基準の「条件付き合格」未満 = 完全合格
```

r13→r14 の破壊型 regression は 0 (本ラウンド確認)。歴代 r10→r14 で「新設規範の内側」に問題が寄っていた傾向に対し、本 r14 版は r13 の major 2 件 (Q01 期限判定非対称 / Q02 単独検索 :current_tool) の双方が解消されており、新規 major も検出されない。

---

## 第 1 部 — 回帰確認 (C9 / 374 項目)

### fixed / superseded (374 項目 — 全件)

- **A01〜A24**: A01(→K25) superseded、他すべて fixed
- **B01〜B18**: すべて fixed
- **D01〜D14**: D08(→K20) superseded、他すべて fixed
- **E01〜E06 / F01〜F27 / G01〜G02**: F05(→I14)/F07(→I15)/F12(→I16・I17)/F21(→I03・I04) superseded、他すべて fixed
- **H01〜H30**: H04(→I31)/H15(→I08・I11)/H18(→I16)/H22(→I15) superseded、他すべて fixed
- **I01〜I38**: I04/I05/I06/I09/I11/I12/I15/I16/I17/I35 superseded、他すべて fixed
- **J01〜J20**: J03(→K10)/J04(→K01)/J07(→L09)/J10(→K09)/J13(→K16)/J16 superseded、他すべて fixed
- **K01〜K26**: K06/K13/K14/K19/K21/K24 superseded、他すべて fixed
- **L01〜L28**: L26(→N14)/L28(→M03+M09) superseded、他すべて fixed
- **M01〜M29**: M29(→N15) superseded、他すべて fixed
- **N01〜N45**: N03/N04/N07/N13/N15/N28/N36/N39/N40 superseded、他すべて fixed
- **O01〜O30**: すべて fixed
- **Q01〜Q37**: Q09(L2644 intent_token IS NULL 削除ガード)/Q03(L1024-1025 伝播猶予 10 分)/Q10・Q37(:current_tool=最新 generated_at L1533/L1703/L1813)/Q12(再 lstat L2483/L2829)/Q13・Q36(破損 journal 例外 L2111/L2579) を含め、すべて fixed / superseded

### partially-fixed / not-fixed / regression

- **なし** (0 件)。r13 の O28 partially-fixed は r14 で解消済み (§5.7 record 参照の曖昧さ除去)。Q02 単独検索 :current_tool は r14 (Q10/Q37) で補完。

---

## 第 2 部 — 探索ログ (60 シナリオ統合表)

探索は X1〜X56 の全観点を網羅し、自由探索で 4 シナリオ追加 (計 60)。重心は r14 修正相互作用 (X51〜X56)。以下は「非自明な挙動確認」のみ抜粋し、単純確認は省略。

| ID | 観点 | 確認結果 |
|----|------|----------|
| X1 | OCR Batch 冪等 INSERT / ON CONFLICT | 冪等確認 (L884 衝突は「同一課金の再観測」吸収) |
| X2 | kind=2 profile 往復 A→B→A の課金記帳 | (b') が batch_job_id=NULL でも job 実在照合→記帳 (L1201-1203) で捕捉 |
| X3 | seq UNIQUE 衝突時の黙殺 | 行 UPDATE 必須 (L1191-1195) で衝突吸収かつ実課金保護 |
| X4 | detached (b) 期限超え記帳 | 期限内保持 / 期限超は記帳してから掃除 (L1157-1163) |
| X5 | floor_generated_at 先行引き上げ順序 | app→metadata 順、逆順は課金事故 (L620-627) |
| X6 | §9.3-c agg 構築 profile 不一致破棄 | agg_embeddings DELETE + agg_vec DROP→CREATE (L677-679) |
| X7 | synced_profile_hash 陳腐化 | 破棄で全行 NULL 化 + ready クリア (L680-685) → R1 誤検出 |
| X8 | ready 母数の除外フォルダ | missing/fork/damaged/一時読取不能 除外 + 0 件は更新せず (L687-692) |
| X9 | 未知 v の fail-closed スキップ | status 化、テキスト扱い禁止 (L531-533) |
| X10 | 画像 0 件文書の grammar version 対象外 | 再構築スキップ (L528-530) |
| X11 | チャンク規則変更の再チャンク冪等 | DELETE→INSERT 同一 Tx、中断は全量再実行 (L629-633) |
| X12 | opt-in 画像フィルタ変更の反映 | §7 再チャンク経路で全派生反映 (L768-769) |
| X13 | floor 引き上げと generated_at 更新の競合 | floor 先行 fail-safe (L620-627) |
| X14 | client 経路呼出中クラッシュ | 実行前計上 + attempts 上限有界化 (L725-760) |
| X15 | 恒久 4xx の batch_job_id NULL 戻し | 未実行確定で記帳なし (L734-741) |
| X16 | client_exhausted の terminal 記帳 | 上限到達 state=0 を state=3 + NULL+estimated (L752-755) |
| X17 | submissions 再実行の profile 書き直し | profile 異なる行は attempts=0 数え直し (L749-751) |
| X18 | cost_ledger batch_job_id 記帳キー | (b)(b') とも「発見 job id」で記帳 (L1192, L1126) |
| X19 | token sweep 前段の記帳済み判別 | (b') と同一述語 (L1123-1126) → R51 誤検出の根 |
| X20 | confirmed-absent 期限判定対称性 | (b')・sweep・detached すべて同一猶予 (L1128-1133, L1157-1161, L1197-1200) |
| X21 | reconcile close 付随 (a) floor NULL | collect と同処理 (L1183-1184) |
| X22 | (b) batch_job_id 非 NULL 記帳 | NULL+estimated 冪等 (L1185-1188) |
| X23 | (b') 照合 unknown は保持 | 次 tick sweep が再試行 (L1196) |
| X24 | (c) 掃除の実行条件「同 token 全行終端」 | 共有 job の早期掃除防止 (L1207-1209) |
| X25 | agg_vec 孤児 (target_key PK 衝突) | fsck 逆差集合 + collect DELETE→INSERT 二重防御 (L1469, L1979-1981, L1954) |
| X26 | repo 跨ぎ target_key 衝突 | repo を跨ぐと unique 要求で衝突 (L1541) → 設計上単一 agg に限定 |
| X27 | §6 エスケープ可逆性 (3 段 G/\\G/\\\\G) | 往復可逆、test vector 要求 (L547-550) |
| X28 | §7 実在検証 (phantom 防止) | 実在しない hash は image chunk 生成せず規則4除去のみ (L584-587) |
| X29 | §7 規則4 除去単位 (行全体+LF) | 空行圧縮なし、text_hash 安定 (L588-593) |
| X30 | §7 un-escape (構造的 grammar 形) | `\[`/`\]` エスケープ済み label も正しく復元 (L516-519, L594-598) |
| X31 | §6↔§7 エスケープ非対称 | 構造的 grammar 形で対称 (R56 誤検出の根、後述) |
| X32 | rename による source_id 衝突 | obj:<hash64> 参照は content hash キーで source_id は OCR 応答内 index (R41 誤検出) |
| X33 | name_collision (NFC/case 折り畳み) | UTF-8 バイト列昇順 1 件採用 + 残り status (L2514-2520) |
| X34 | rename 直前再 lstat (TOCTOU) | 保全不一致は中止・再試行 (L2483, L2829-2830) |
| X35 | 破損 journal 例外 (Q13/Q36) | 例外スキップ + status (L2111, L2579) |
| X36 | 再 lstat (Q12) | restore/rename 直前再検証 (L2483, L2829) |
| X37 | :current_tool 最新 generated_at (Q10/Q37) | 単独検索の tool 決定補完 (L1533, L1703, L1813) |
| X38 | intent_token IS NULL 削除ガード (Q09) | ガード追加 (L2644) |
| X39 | 伝播猶予 10 分 (Q03) | now からの猶予 (L1024-1025) |
| X40 | upload_cleaned=0 の detached 削除禁止 | handle 喪失防止 (L1164-1166) |
| X41 | recovery-gate 例外 × flag 掃除 | 例外時も未掃除 flag を残し次回再試行 |
| X42 | retry_not_before 命名一貫性 | retry_after 表記なし、一貫 (L734/896/987/1016/1064) → R42 誤検出 |
| X43 | estimated 区分 (cost_estimated) | 実額/推定/未取得を月次集計で分離 (L880, L2141-2144) |
| X44 | 重複課金「最悪 job 1 回分」は server 限定 | client 経路は attempts 上限有界化のみ (L756-760) |
| X45 | 接続フォルダ 0 件時の ready 不更新 | 空虚な真による空 index ready 詐称防止 (L691-692) |
| X46 | missing からの recovery 自己衝突 | 「別 root_path 登録済みは常に conflict」回避 (L2605) |
| X47 | Office 一時消失窓 (一時ファイル+rename) | 間隔監視で相殺 (L2441-2447) |
| X48 | tmp/ 残骸回収 | tick 開始時 tmp 掃除 (L2045, L2844) |
| X49 | 非 UTF-8 名への rename | 旧論理名は追跡不能で status のみ (L2364) |
| X50 | fork 中フォルダの ready 除外 | damaged/missing 同格で除外 (L688-689) |
| X51 | seq 行 UPDATE × 一貫性 (r14 相互作用) | 行 UPDATE を怠ると UNIQUE 衝突で実課金黙殺 (L1191-1195) — 記述あり |
| X52 | expired 出口 (r14 相互作用) | 期限超は記帳してから掃除、期限内は未作成として掃除 (L1128-1133) |
| X53 | (b')/token sweep 4 照合点対称性 | (b')・sweep の述語・記帳キー・期限判定が完全対称 — R51 誤検出 |
| X54 | recovery-gate 例外 × flag 掃除 (r14) | 例外でも flag 残置で再試行可能 |
| X55 | :current_tool 2 規則 (r14) | 横断=ready / 単独=最新 generated_at の 2 規則明記 (Q10/Q37) |
| X56 | §6/§7 エスケープ非対称 (r14 延期論点) | 構造的 grammar 形で対称、hash64 不整合も `\` 除去+除去処理 — R56 誤検出 |
| X57 | detached 再登録による自動再課金 | 意図された有界コスト、ledger 追跡済み (L1169-1172) |
| X58 | profile_changed 破棄の payload 廃棄 | metadata 書込なしを明示 (L1146-1148) |
| X59 | agg 再構築の中断収束 | 新旧 chunks 混在無害、再実行で現行規則に収束 (L629-633) |
| X60 | 未知 v の旧アプリ読取専用 | 新アプリ再 materialize 派生を旧アプリは読取専用 (L531-533) |

---

## 第 3 部 — 新規検出

### R01 — [minor] cost_estimated の「未取得」と「推定」のUI 表示混同リスク
月次集計で実額/推定/未取得を分離するが (L2141-2144)、status 表示レイヤで「未取得 (job 照合不能で金額未定)」と「推定 (estimated=1)」を同一アイコンで表示すると誤認を誘う。設計上の欠陥ではなく運用表示の要注記。
**措置**: 監査注記 (proposal 級)。設計修正は不要。

### R02 — [proposal] client 経路の重複課金上限の明示
L756-760 で「最悪 job 1 回分」は server 限定、client は attempts 上限 (既定3) 有界化と明記。運用上、client 経路利用時の上限値を app_config で可視化する提案。設計修正不要。

### R51 / R46 — [REJECTED: false positive] (b')/token sweep の batch_job_id 述語不一致
探索エージェントが「sweep の述語が `batch_job_id = intent_token` になり (b') の `= 発見 job id` と不一致 → 二重記帳」と挙げた。
**直接照合の結果**: (b') (L1192-1194) と token sweep (L1123-1126) の双方とも「同キー × batch_job_id = **発見 job id**」で記帳済み判別を行い、記帳する batch_job_id も「発見 job id」で一致。述語の不一致は存在せず、二重記帳は起きない。エージェントの trace が intent_token を batch_job_id と誤読した誤検出。
**措置**: 棄却。原文 L1123-1126 / L1192-1194 を根拠に誤検出と判定。

### R56 — [REJECTED: false positive] §6/§7 エスケープ非対称 (hash64 不整合による `\` 残滓)
探索エージェントが「`![diagram](obj:see appendix)` のような hash64 不整合な grammar 偽装は §6 で `\` 付与されるが §7 は hash64 不一致で認識せず `\` が残留」と挙げた。
**直接照合の結果**: §6 のエスケープ対象 (L546) と §7 の認識 (L594「行全体が grammar に一致」、L520「この canonical 形だけを認識」) はいずれも**構造的 grammar 形** (`![` + `](obj:` パターン) であり、hash64 の妥当性は要求しない。したがって (1) §6 が付与した `\` は §7 の un-escape (L595-598) で除去され、(2) 実在しない参照は規則4で本文から除去 (L588-589) される。往復可逆は hash64 不整合な偽装行でも成立し、`\` 残留は起きない。r14 裁定の「現状維持が安全側」は正しい。
**措置**: 棄却。原文 L516-520 / L541-551 / L594-598 を根拠に誤検出と判定。

### R1 — [REJECTED: false positive] synced_profile_hash 陳腐化による ready 詐称
探索エージェントが「profile 変更後、旧 synced_profile_hash が残り ready が立つ」と挙げた。
**直接照合の結果**: agg 破棄時に synced_profile_hash を全行 NULL へ戻し (L680-681)、agg_ready_profile_hash をクリア (L685) する。ready は「接続フォルダの synced_profile_hash がすべて building と一致」で判定 (L696-697) され、接続フォルダ 0 件では更新しない (L691-692)。陳腐化による ready 詐称は構造的に起きない。
**措置**: 棄却。原文 L680-697 を根拠に誤検出と判定。

### R41 — [REJECTED: false positive] rename による source_id 衝突
**直接照合の結果**: 画像参照は `obj:<image_hash64>` で content hash をキーとし、source_id は OCR 応答内の画像 index ラベル (L507, L515)。異なるファイル間で source_id が一致しても hash64 参照で識別される。name_collision はファイル物理名レベルで処理 (L2514-2520)。source_id 衝突によるチャンク混入は起きない。
**措置**: 棄却。

### R42 — [REJECTED: false positive] retry_not_before / retry_after 命名不一致
**直接照合の結果**: 全文で `retry_not_before` に統一されており `retry_after` 表記は無い (L734/896/987/1016/1064)。不一致なし。
**措置**: 棄却。

---

## 第 4 部 — 確認済み列挙

- C9 回帰確認 374 項目: **全件 fixed または superseded、regression 0**。
- r13 の major 2 件の解消確認:
  - Q01 (期限判定非対称): r14 本文で (b') と sweep の述語・記帳キー・期限判定が完全対称 (L1123-1126 / L1192-1200)。非対称は存在せず、実質的解消。
  - Q02 (単独検索 :current_tool): r14 (Q10/Q37) で `:current_tool = 最新 generated_at` を単独検索に補完 (L1533/L1703/L1813)。
- r14 修正 6 件 (Q03/Q09/Q10/Q12/Q13/Q36/Q37) の適用箇所を直接確認: L2644 / L1024-1025 / L1533・L1703・L1813 / L2483・L2829 / L2111・L2579。
- 探索 60 シナリオ: X1〜X56 全観点 + 自由探索 4 を実行、未実行観点なし。
- 新規 fatal / major: **0 件** (R51/R46, R56, R1, R41, R42 はいずれも誤検出として棄却)。

---

## 結論

`folder-history-sqlite-design.md` (r14, 2916 行) は監査に**合格**する。C9 回帰確認は全項目 fixed/superseded で regression なし。探索 60 シナリオを通じ新規 fatal/major は検出されず、探索エージェントが挙げた major 級候補はオーケストレータが原文を直接照合しすべて誤検出と判定した。残る R01/R02 は運用表示・設定可視化の proposal 級注記にとどまり、設計修正を要しない。
