合格
target.md 全 3207 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

# 第 1 部 — 回帰確認 (C9)

## 圧縮報告
A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S29 / T01〜T18 — すべて fixed。

not-fixed / regression / partially-fixed の項目は検出されなかった。

### 代表項目の両側一致確認（抜粋）
| ID | 規範側（audit-prompt.md） | 対象側（target.md） | 判定 |
|---|---|---|---|
| T01 | §4.1 record 例を kind 別 2 形に分離、必須フィールド名 distance_metric | §4.1 lines 166-172: tool 用は annotation_schema あり、embedding 用は annotation_schema なし。options 内 dimensions / distance_metric と明記 | fixed |
| T05 | 相 1 の NULL 戻し = batch_job_id / error / completed_at / job_create_started_at の 4 列 | §9.1 lines 1027-1033: 4 列を NULL へ戻すと列挙 | fixed |
| T07 | cancel 確定 = state=3 (error='cancelled') + attempts=上限 + completed_at + 冪等記帳 | §21.2 lines 2878-2889: 同一内容 | fixed |
| T08 | rotation ガード：token 残存行の再投入は sweep 前段完了後 | §9.1 lines 1034-1037: 同一内容 | fixed |
| T10 | 変換 PDF は一時生成物、content_hash / 照合対象は原本 bytes、upload_id と filename token は変換物に適用 | §6 lines 476-480: 同一内容 | fixed |
| T12 | img block の v 混在 = fail-closed | §6 lines 557-562: 同一内容 | fixed |
| Q01 | 全参照点で現行 profile の参照元 = app_config の embedding_profile record | §8 lines 685-688 / §8-c lines 709-710 / §10 step 3 lines 1732-1734: 統一 | fixed |
| Q02 | step -1 の例外：step 2/4 の in-flight collect と detached 処理は除外しない | §10 step -1 lines 1665-1675: 同一内容 | fixed |
| R06 | (b')・sweep found 記帳 = seq 行 UPDATE + 新値で記帳 + 同じ小 Tx で batch_job_id へ発見 job id を書く | §9.1 lines 1339-1343 / §9.1 token sweep lines 1255-1258: 同一内容 | fixed |
| R08 | detached state=0 (a) = terminal 記帳 + state=3 (error='detached') + completed_at、削除は段階遷移 | §9.1 detached lines 1289-1292: 同一内容 | fixed |
| S07 | job_create_started_at 列 + 相 2b 直前小 Tx + 伝播猶予起点 = max(token 時刻, 同列) + NULL = 相 2b 未着手 | §9.1 DDL lines 859-865 / §9.1 intent 回復 lines 1116-1120: 同一内容 | fixed |
| S10 | sweep found 未記帳判別 = batch_job_id IN (発見 job id, 当該 intent_token) | §9.1 token sweep lines 1252-1253: 同一内容 | fixed |

# 第 2 部 — 探索ログ (C12)

| # | 観点 (X# / 自由) | シナリオ（初期状態 → 操作列） | 結果 |
|---|------------------|------------------------------|------|
| 1 | X1 | 空フォルダ登録 → 1 ファイル追加 → 同一 tick 内に編集 → 次 tick: コミット 1 件に両変更が含まれる | 問題なし |
| 2 | X1 | OCR in-flight 中に対象ファイルを改名 → collect 時に旧 content_hash で結果を回収 → 新しいファイル名は次 tick のスキャンで update コミット | 問題なし |
| 3 | X1 | backfill ON → 過去版 content に対して明示再生成 (floor) を実行 → §5.3 により backfill 設定に関わらず再投入 | 問題なし |
| 4 | X1 | フォルダ A をコピーしてフォルダ B を作成 → 両方を登録 → conflict 検出 → 片方を fork | 問題なし |
| 5 | X2 | ファイル名に改行・"obj:"・"<!-- img:" を含むファイルを追加 → file_name 検証で name_invalid | 問題なし |
| 6 | X2 | annotation 値に `-->` を含む画像 → §6 の可逆エスケープでコメント脱出を防止 | 問題なし |
| 7 | X2 | 0 バイトファイル → content_hash は空ファイルの SHA-256 → コミット・OCR 非対象 terminal 行 | 問題なし |
| 8 | X2 | シンボリックリンク → §20.4 で regular file のみ管理 → absent 扱い | 問題なし |
| 9 | X3 | case-insensitive (APFS) 上で "Report.pdf" → "report.pdf" rename → 保存論理名は初出表記固定 | 問題なし |
| 10 | X3 | NFC 論理名で NFD 実体を参照 → resolver で raw エントリ解決 → 二重実体防止 | 問題なし |
| 11 | X4 | 時計後退 → created_at = max(スキャン確定時刻, 最新コミット + 1) で単調性維持 | 問題なし |
| 12 | X4 | 同一 ms 内に 2 コミット → commit_hash バイト昇順 tie-break | 問題なし |
| 13 | X5 | 10 万ファイル walk → 段 0 fp で dir_fp 一致枝をスキップ → 段 1 の SQLite 行比較 | 問題なし |
| 14 | X5 | 100 万 chunk で FTS 再構築 → §5.5 trigger + rebuild | 問題なし |
| 15 | X6 | 2 文字語「検索」で trigram 沈黙 → LIKE fallback へ差し替え | 問題なし |
| 16 | X6 | vec0 distance_metric = cosine から euclidean へ変更 → §8-c で DROP → CREATE | 問題なし |
| 17 | X7 | metadata.sqlite スキーマ v1 → v2 への migration → BEGIN IMMEDIATE → user_version 再確認 → DDL → version 更新の単一 Tx | 問題なし |
| 18 | X8 | objects/ と tmp/ の権限 0700/0600 → Windows では DACL 継承遮断 | 問題なし |
| 19 | X8 | file_name に ".." を含むファイル → name_invalid で path traversal 防止 | 問題なし |
| 20 | X9 | objects/1 ファイル欠損 → §12 解決時に hash 再照合で不一致 → fsck 誘導 | 問題なし |
| 21 | X9 | metadata.sqlite だけ復元 → §9.3-z 後退検出 → wipe + full resync | 問題なし |
| 22 | X10 | .folder-history 手動削除 → damaged ステータス → 新規再登録 | 問題なし |
| 23 | X10 | zip 化→解凍で mtime/inode 全変化 → scan_cache 行比較で hash 再計算 | 問題なし |
| 24 | X11 | profile 変更後の旧 profile embeddings 行 → §8-a で成果なし → 再投入 | 問題なし |
| 25 | X12 | watch_root 登録 → スキャン → コミット → OCR → チャンク → embed → replicate → 横断検索 → 原本復元 | 問題なし |
| 26 | X13 | 明示再生成 (§5.3): app 1 Tx で floor 設定 + attempts=0 → 次 tick で再 OCR | 問題なし |
| 27 | X14 | 429 レート制限 → retry_not_before に永続化 → 期限まで submit 抑制 | 問題なし |
| 28 | X15 | 「重複課金は最悪 job 1 回分」→ server-side batch 経路限定、provider 採用条件あり → 破れず | 主張保持 |
| 29 | X16 | state=1 照会失敗 (429) → 行不変・attempts 不消費 → 次 tick 再照会 | 問題なし |
| 30 | X17 | register 途中クラッシュ → 不完全 .folder-history → damaged → 再実行 | 問題なし |
| 31 | X17 | fork 後の旧履歴だけが参照する object → 次 GC で回収 | 問題なし |
| 32 | X18 | profiles 行の record_json 改竄 → fsck で SHA-256 不一致検出 → 現行 record で DELETE → INSERT | 問題なし |
| 33 | X19 | 相 1 直後クラッシュ → state=0 + intent_token → 次 tick intent 回復で job 一覧照合 | 問題なし |
| 34 | X19 | metadata.sqlite 書込後・app 更新前クラッシュ → collect 冒頭で成果既存を検出 → 冪等クローズ | 問題なし |
| 35 | X20 | 「delete は pending_deletes で見逃さない」→ 1 回目 absent → pending 行 → 2 回目 absent + 30 秒で確定 | 主張保持 |
| 36 | X21 | floor 引き上げと §5.3 明示再生成の交錯 → app (floor) → metadata (generated_at) の順 | 問題なし |
| 37 | X22 | fork journal の PREPARED → HISTORY_CLEARED → ID_WRITTEN → APP_DONE を各境界でクラッシュ → 再開位置一意 | 問題なし |
| 38 | X23 | app_config 単一 key 残存 → target.md は building/ready 2 key → 該当せず | 問題なし |
| 39 | X24 | vec 差集合再充填：CREATE 済み・充填途中クラッシュ → 次 tick で差集合検出 → 残りを埋める | 問題なし |
| 40 | X25 | app.sqlite 単独で横断検索 → app_config の embedding_profile record から query_vector 生成 | 問題なし |
| 41 | X26 | submission_seq + attempts + ledger: 行削除→再登録→MAX 継承 → 旧 ledger と UNIQUE 衝突防止 | 問題なし |
| 42 | X27 | fork 中にフォルダ移動 → journal 走査で移動先を発見 → 回復 | 問題なし |
| 43 | X28 | detached 行を再登録 → folders 復帰 → attached 化 → state=2 の成果なし → 投入対象 | 問題なし |
| 44 | X29 | case-only rename → 保存論理名固定 → 複合 FK / PARTITION が BINARY 一致 | 問題なし |
| 45 | X30 | 「保存名固定により case-only rename の FK 違反は構造的に不可能」→ 固定表記により FK 参照成功 | 主張保持 |
| 46 | X31 | reconcile close の付随処理 (b') → 行 UPDATE + 発見 job id 記帳 → 二重記帳防止 | 問題なし |
| 47 | X32 | fork phase 状態機械：HISTORY_CLEARED で commits 非空 → 手順 1 から再開 | 問題なし |
| 48 | X33 | 課金記帳網羅行列：server/client × success/expired/timeout/missing/profile_changed/submit_rejected/tool_changed/client_exhausted → 各セル 0/1 行 | 問題なし |
| 49 | X34 | §11.2 の掲載 SQL を実際に組み立て → eligible × agg_chunks 再 JOIN / agg_ready 照合 / at_hash=FF | 問題なし |
| 50 | X35 | 「fork は id=old からでも journal で正しく再開する」→ phase + 実体 id で一意に決まる | 主張保持 |
| 51 | X36 | ON CONFLICT DO NOTHING × detached 採用 seq+1: 別 attempt の課金を落とさない | 問題なし |
| 52 | X37 | ready 母数：接続フォルダ (missing/fork/damaged/一時読取不能を除外) → 0 件なら ready 非更新 | 問題なし |
| 53 | X38 | flag 掃除：journal 無 + 実体現存 + marker id = new_id → flag 掃除 | 問題なし |
| 54 | X39 | 一時読取不能保留 × damaged 誘導の境界 → 存在と可読性を分離 | 問題なし |
| 55 | X40 | 「query_profile_hash 固定で embed 中 profile 変更の TOCTOU は不可能」→ 生成時 hash に固定 | 主張保持 |
| 56 | X41 | 全終端理由 × 全 close 経路の記帳行列 → seq で一意 | 問題なし |
| 57 | X42 | ready 母数の変動：C damaged の間に A/B で ready=P2 成立 → C 復旧で synced=NULL → ready は P2 のまま？ → 母数復帰で再判定 | 問題なし |
| 58 | X43 | resolver 行列：NFD 実体のみ / NFC 実体のみ / 両方存在 / raw 無し × delete 確認 / restore / fsck | 問題なし |
| 59 | X44 | step -1 除外：scan/reconcile/submit/replicate を除外、step 2/4 in-flight collect は除外しない | 問題なし |
| 60 | X45 | 「ready は damaged・空母数・synced 陳腐化に騙されない」→ 毎 tick 宣言的検査 | 主張保持 |
| 61 | X46 | 記帳済み判別述語：期限超 token 記帳 → 載せ直し → 相 3 job id 記帳 → ledger 3 行が正当な別 attempt | 問題なし |
| 62 | X47 | 期限超同一 Tx × token rotation: (i)〜(iv) を 1 Tx → 旧 token 記帳行が新 token 述語に干渉しない | 問題なし |
| 63 | X48 | restore 保全：現内容 ≠ LWW → 先にコミット → 上書き → 次 tick scan | 問題なし |
| 64 | X49 | 全 §21 操作前の fork 回復先行 → 操作は回復後の状態を入力に進む | 問題なし |
| 65 | X50 | 「明示操作は未完 fork に反転されない」→ 回復先行 | 主張保持 |
| 66 | X51 | seq 行 UPDATE の連番一貫：期限超 (ii) → (iv) 相 1 → 相 3 で同一 attempt が二重加算されない | 問題なし |
| 67 | X52 | expired terminal → 遷移表 → sweep → 明示 retry: token 残存と削除ガードの整合 | 問題なし |
| 68 | X53 | 4 照合点の期限判定対称性：intent 回復・detached (b)・(b')・token sweep 前段で 8 要素比較 | 問題なし |
| 69 | X54 | 破損 journal の明示解決：journal 除去 (flag 残置) → 新規採番せず new_id 採用 → flag 掃除 | 問題なし |
| 70 | X55 | 単独検索の 2 決定規則：:current_profile = embeddings 一意 / :current_tool = markdown_documents 最新 generated_at | 問題なし |
| 71 | X56 | §6/§7 エスケープ条件の非対称：un-escape は §6 と同一緩いパターン、認識は厳密一致 + 実在検証 | 問題なし |
| 72 | X57 | 自己記述化 (batch_job_id ← 発見 job id) × dispatch: state=0 の client 判定には terminal 行のみ影響 | 問題なし |
| 73 | X58 | detached terminal 化 × 遷移表 × 再登録：error='detached'/'expired' 行は再登録後に投入対象化 | 問題なし |
| 74 | X59 | submit_rejected 除外 × 課金される拒否：provider 前提注記あり、拒否にも課金する provider では分岐に記帳 | 問題なし |
| 75 | X60 | decoder 拡張の往復全数：G / \G / \\G の往復可逆性 | 問題なし |
| 76 | X61 | 伝播猶予の採用条件：可視化遅延上限 ≤ 猶予、保持期間 ≥ timeout_hours + 結果保持期限 + 猶予 1 日 | 問題なし |
| 77 | X62 | job_create_started_at が開ける穴：相 2b 呼出直前小 Tx、NULL = 未着手、backfill 規範 | 問題なし |
| 78 | X63 | error='cancelled' × 遷移表 × 再登録：attempts=上限で自動再投入対象外 | 問題なし |
| 79 | X64 | found 判別 IN (発見 job id, 当該 intent_token) の過吸収：token 記帳 → crash → 遅延可視化 found で二重計上防止 | 問題なし |
| 80 | X65 | no-replace rename 非対応環境：初回試行エラーで判定、fallback は再 lstat + 通常 rename + 残余窓引き受け | 問題なし |
| 81 | X66 | 規範↔要約・掲載 SQL・DDL コメントの非伝播：§9.1 ↔ §21.2/§21.3、§11.2、§13、§7 ↔ §9.1、§10 ↔ §9.1 を両側確認 | 問題なし |
| 82 | X67 | rotation ガード：token 残存行の再投入は sweep 前段完了後、unknown 滞留は retry_not_before + status | 問題なし |
| 83 | X68 | cancel × 明示 retry の循環：cancel 後 attempts=上限、明示 retry で attempts=0、再 cancel で上限 | 問題なし |
| 84 | X69 | fts_cap × RRF 再現率：cap 到達時の欠落は決定論的、外側 :limit は fusion 後 | 問題なし |
| 85 | X70 | 変換決定論 × コンバータ更新：コンバータ版更新 = tool_profile 変更 → target_key 変化で再判定 | 問題なし |
| 86 | 自由 | app.sqlite WAL raw コピー → commit 済み ledger 喪失 → §13 で Online Backup API / VACUUM INTO を規範 | 問題なし |
| 87 | 自由 | agg_ready_profile_hash を building 単一 key に戻した場合 → 部分 index が ready を騙る → target.md は 2 key で防止 | 問題なし |
| 88 | 自由 | floor 引き上げを metadata → app の順にした場合 → generated_at > floor になり明示再生成が silent cancel → target.md は app → metadata | 問題なし |
| 89 | 自由 | chunks 表に commit_hash 列を追加した場合 → 同一内容のコミットごとに chunk 複製 → §18.1 で不採用 | 問題なし |
| 90 | 自由 | image フィルタ OFF → ON 切替 → 旧 image チャンクは §7 再チャンクで削除、filter record は app_config へ | 問題なし |

# 第 3 部 — 新規検出 (C1〜C8, C10, C11, C12)

新規検出は 0 件。

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| （なし） | — | — | — | — | — | — |

# 第 4 部 — 確認済みの列挙

- P1 三層構成（層 1 truth、層 2 運用層、層 3 集約層）— 確認済み
- P2 識別子規範（content_hash、commit_hash、tool/embedding profile hash、JCS 直列化）— 確認済み
- P3 metadata.sqlite 8 テーブル（profiles 含む）— 確認済み
- P4 chunks 統一テーブル— 確認済み
- P5 チャンク分割規則— 確認済み
- P6 OCR（Mistral OCR 4 Batch、canonical img block、preflight）— 確認済み
- P7 FTS external content + view + trigger— 確認済み
- P8 Embedding 必須・単一 multimodal profile・宣言的収束— 確認済み
- P9 batch_requests + cost_ledger 状態機械— 確認済み
- P10 書き込み順序と冪等性— 確認済み
- P11 集約レプリケーション— 確認済み
- P12 検索（eligible、RRF、KNN、単独/横断）— 確認済み
- P13 GC + fsck— 確認済み
- P14 SQLite 設定（journal_mode、migration、PRAGMA 初期化）— 確認済み
- P15 元設計から不変の部分— 確認済み
- P16 変更検知（層 A/B/C、fp_cache、scan_cache、pending_deletes）— 確認済み
- C1 原則反映— 確認済み
- C2 SQL 静的検証— 確認済み
- C3 相互参照整合— 確認済み
- C4 クエリとスキーマの整合— 確認済み
- C5 数値・事実の一貫性— 確認済み
- C6 用語・形式の一貫性— 確認済み
- C7 状態機械の完全性— 確認済み
- C8 欠落— 確認済み
- C10 修正が開けた穴— 確認済み
- C11 合理性— 確認済み
- C12 探索型監査— 90 シナリオ実行済み
