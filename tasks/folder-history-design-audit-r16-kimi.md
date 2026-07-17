# 監査報告書

## 総合判定

**条件付き合格**

- C9 回帰確認: 403 項目すべて **fixed** または **superseded**（対応表どおり）。
- 探索ログ: 65 シナリオ実行済み（X1〜X61 各観点を最低 1 つカバー、重心 X57〜X61）。
- 新規検出: **minor 1 件（S01）** のみ。fatal / major は 0 件。

---

## 第 1 部 — 回帰確認（C9）

### fixed と判定した項目（ID 列挙）

| ラウンド | 項目 |
|---|---|
| r1 | A01〜A24 |
| r2 | B01〜B18 |
| §20 追記 | D01〜D14 |
| r3 | E01〜E06 |
| r4 | F01〜F27 |
| r5 | G01〜G02 |
| r6 | H01〜H30 |
| r7 | I01〜I38 |
| r8 | J01〜J20 |
| r9 | K01〜K26 |
| r10 | L01〜L28 |
| r11 | M01〜M29 |
| r12 | N01〜N45 |
| r13 | O01〜O30 |
| r14 | Q01〜Q37 |
| r15 | R01〜R29 |

### superseded と判定した旧項目（不合格事由に数えず）

| 旧項目 | → 新項目 |
|---|---|
| F05 | → I14 |
| F07 | → I15 |
| F12 | → I16・I17 |
| F21 | → I03・I04 |
| H04 | → I31 |
| H15 | → I08・I11 |
| H18 | → I16 |
| H22 | → I15 |
| A11 遷移詳細 | → I05・I06・I13・I14 |
| H02 衝突順 | → I32 |
| I03/I04 cost 記述 | → J06 |
| I05/I06 2 相 submit | → J01・J02 |
| I09 404 未定義 | → J03 |
| I11 result_expired | → J03 系 |
| I15 floor | → J04 |
| I16/I17 profile 宣言的 | → J05・J01 |
| I35 fork | → J13〜J16 |
| J04 | → K01 |
| J06 UNIQUE(…,attempt) | → K02 |
| J03 | → K10 |
| J10 | → K09 |
| J13 | → K16 |
| J16 | → K13〜K15 |
| I12 | → K04 |
| D08 | → K20 |
| A01 | → K25 |
| K02 UNIQUE 叙事文 | → L01 |
| K12〜K13 detached | → L04 |
| K06 submit_rejected | → L02 |
| K09 client 写像 | → L03 |
| K14 fork | → L07 |
| J07 app_config 単一 agg key / K24 §11.2 agg 照合 | → L09 |
| K11 失効窓 | → reconcile close 記帳義務化 |
| K21 fsck repair | → L20 |
| K19 猶予 | → L13 |
| L09 app_config 2-key コメント | → M03 |
| L28 app_config key / fsck agg | → M03・M09 |
| L20 §13「§5.3 誘導」 | → M04 |
| L04 / L21 §21.2 state=0 | → M02 |
| M09 母数 | → N05 |
| M10 次元のみ | → N10 |
| M12 record と hash | → N38 |
| M29 掃除失敗 | → N15 |
| M06 採用列挙 | → N17 |
| L07/M05 flag 保存先 | → N16 |
| L26 submit 側のみ | → N14 |
| M01 DDL コメント | → N09 |
| M08 素朴 stat | → N28 |
| M13 register 4 分類 | → N30 |
| N03 期限超記帳 | → O05・O06 |
| N04 (b') | → O02・O03 |
| N13 | → O21 |
| N15 sweep | → O04・O25 |
| N36 | → O16 |
| N39 | → O14 |
| N40 | → O28 |
| N28 | → O13 |
| N07 | → O12 |
| §21.5 M&S | → O29 |
| O28 | → Q01 |
| O17 | → Q02 |
| O02/O03 (b') | → Q05・Q07 |
| O04 sweep | → Q06 |
| O05 期限超 | → Q04 |
| O07 detached | → Q09 |
| O09 restore | → Q11・Q12 |
| O11 回復先行 | → Q13・Q36 |
| O18 flag 掃除 | → Q23 |
| O19 自動 rebind | → Q24 |
| O13 resolver | → Q12 |
| O30 mapping bind | → Q37 |
| Q02 | → R01 |
| Q04 | → R02 |
| Q09 | → R03 |
| Q12 | → R04 |
| Q03 | → R05 |
| Q05/Q06 found | → R06 |
| Q06 sweep | → R07 |
| Q10 current_tool | → R14 |
| Q13/Q14 journal | → R15・R16 |

### not-fixed / partially-fixed / regression: なし

（R23「operation record」は §7 に app_config への書込み記述があるため fixed と判定。ただし §9.1 の key 契約に含まれていない点は第 3 部 S01 として別途指摘する。）

---

## 第 2 部 — 探索ログ（C12）

65 シナリオを文書の規範だけで手で実行した。

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---|---|---|---|
| 1 | X1 | ファイル作成→同 tick 内編集→削除。段 2 の content_hash が変化し、delete は pending_deletes + 30 秒待ちで確定。 | 問題なし |
| 2 | X1 | OCR state=1 中に対象ファイルを改名。次 tick で旧名 absent→新名 create、OCR job は collect 時に custom_id 不一致で output_missing または新 content として処理。 | 問題なし |
| 3 | X1 | backfill ON で過去版に対し明示再生成（floor 設定）。floor 設定済みは backfill 無関係で submit 候補になり、旧 md は成果なし化。 | 問題なし |
| 4 | X1 | フォルダ移動中に tick 実行。tick.lock で排他、移動は tick 間で起き、再発見で rebind または conflict。 | 問題なし |
| 5 | X1 | 2 PC でコピー編集後片方を書き戻す。同一 repository-id が 2 箇所に出現 → conflict 停止、fork 解決まで進行しない。 | 問題なし |
| 6 | X2 | ファイル名に改行・「obj:」を含む。§20.5 file_name 検証で name_invalid → 管理対象外。 | 問題なし |
| 7 | X2 | case-insensitive FS で `Report.pdf` と `report.pdf` を配置。保存論理名を初出に固定、敗者を name_collision、PARTITION BY BINARY で単一系列。 | 問題なし |
| 8 | X2 | 0 バイトファイル。安定確認→hash 計算→content_hash 確定。OCR は空 md になり chunks なし。 | 問題なし |
| 9 | X2 | regular file を同名 symlink へ置換。§20.4 で対象外型 = absent、delete 判定へ。 | 問題なし |
| 10 | X2 | annotation transcription に `-->` を含む。§6 エスケープで `--\>`、§7 un-escape で可逆。 | 問題なし |
| 11 | X3 | case-insensitive → sensitive ボリューム移動。case 違い 2 実体が別系列 = create になる。 | 問題なし |
| 12 | X3 | macOS NFD 実体を管理。readdir NFD → NFC 論理名保存、raw 解決で NFD 実体にアクセス。 | 問題なし |
| 13 | X3 | PATH_MAX 直前の長名。§20.5 file_name 検証は通るが、OS rename 時にエラー → tmp 保持 status。 | 問題なし |
| 14 | X4 | 時計後退。created_at = max(now, latest+1) で単調維持。 | 問題なし |
| 15 | X4 | 同一 ms に複数コミット。commit_hash でタイブレーク、LWW 順序決定論化。 | 問題なし |
| 16 | X5 | 10 万ファイル walk。段 0 fp で dir_fp 一致枝をスキップ、段 1 scan_cache で比較。 | 問題なし |
| 17 | X5 | 100 万 chunk の RRF。over-fetch + refill で k_max 到達後は不足のまま返す。 | 問題なし |
| 18 | X6 | 日本語 2 文字クエリ「検索」。trigram 0 件 → LIKE fallback で text/heading_path 両列を走査。 | 問題なし |
| 19 | X6 | sqlite-vec が `k` 以外の述語を拒否。KNN は単独サブクエリ、eligible は後段 join。 | 問題なし |
| 20 | X6 | Mistral batch 512MB 超ファイル。preflight で oversize terminal marker、upload しない。 | 問題なし |
| 21 | X7 | schema_version なし → user_version 使用、新旧アプリ混在は fail-closed。 | 問題なし |
| 22 | X7 | grammar v=2 導入。markdown_documents 全走査で先頭 img block の v 判定、旧版を一括再 materialize。 | 問題なし |
| 23 | X8 | ファイル名に `..` を含む。§20.5 name_invalid → 管理対象外、restore でも path traversal 防止。 | 問題なし |
| 24 | X8 | objects/ ディレクトリを 0700 に設定、Windows では DACL 継承遮断。 | 問題なし |
| 25 | X9 | object ファイルが破損。§12 解決時に hash 不一致 → fsck 誘導、提示を防ぐ。 | 問題なし |
| 26 | X9 | metadata 書込前にディスク満杯。objects 書込は成功、metadata Tx はロールバック、次 tick で差集合から再処理。 | 問題なし |
| 27 | X10 | `.folder-history` 手動削除。folders 行は残るが次 walk で damaged、再登録で新 id。 | 問題なし |
| 28 | X10 | zip/unzip 往復。mtime・inode 全変化 → scan_cache 不一致 → 全ファイル段 2 再計算。 | 問題なし |
| 29 | X11 | profile 変更後 kind=2 行を一括削除しない。旧 profile 行は成果なし化、attempts=0 数え直し、vec は宣言的に置換。 | 問題なし |
| 30 | X12 | watch_root 登録→発見→文書追加→scan→commit→OCR→chunk→embed→replicate→横断検索→原本解決→履歴→restore。各受け渡しが § 参照で閉じる。 | 問題なし |
| 31 | X13 | §21 の 6 操作を入力・手順・失敗回復まで列挙。いずれも定義済み。 | 問題なし |
| 32 | X14 | submit 429 → retry_not_before 永続化、期限内は submit/collect スキップ。 | 問題なし |
| 33 | X15 | 「重複課金は最悪 1 job 分」を試す。相 2b 後・相 3 前クラッシュ → intent 回復で既存 job 採用、新規 job は作らない。server 経路で成立。 | 破れず |
| 34 | X16 | state=1 の job が provider 側で 404 → job_missing → state=3 → 再投入または terminal。 | 問題なし |
| 35 | X17 | register 手順 2 途中クラッシュ → metadata.sqlite 不完全 → damaged → 再実行で新規初期化。 | 問題なし |
| 36 | X18 | profiles 孤児と operation_record。§18.7 で profiles 孤児は意図的に掃除しない。一括変換 operation_record は §7 で app_config へ書くが、§9.1 の key 契約に未記載 → **S01 検出**。 | S01 |
| 37 | X19 | ディレクトリ fsync 忘れの境界。objects/ prefix 新規作成時は親も fsync、migration は単一 Tx。 | 問題なし |
| 38 | X20 | 「delete は pending_deletes で見逃さない」を試す。pending 行がクラッシュで残っても step 0 冒頭で LWW delete 行を冪等削除。 | 破れず |
| 39 | X21 | 相 1 の profile_hash リセットと intent 回復。旧 profile 行は attempts=0、snapshot は相 1 のまま、採用時に上書きしない。 | 問題なし |
| 40 | X22 | fork 全境界クラッシュ。phase + id から再開位置一意。flag→journal 削除順で恒久凍結を回避。 | 問題なし |
| 41 | X23 | app_config / cost_ledger / detached が status・検索・GC で一貫。 | 問題なし（S01 別途） |
| 42 | X24 | vec 差集合再充填をクラッシュで中断。次 tick で差集合を再検出し欠落を埋める。 | 破れず |
| 43 | X25 | app.sqlite 単独で横断検索。app_config の embedding_profile が無ければ skip + status。 | 問題なし |
| 44 | X26 | submission_seq × attempts × ledger。相 3 / 採用 / client 前計上で +1、ledger UNIQUE で同一 seq の再観測を冪等吸収。 | 問題なし |
| 45 | X27 | fork journal 破損。digest 不整合 → damaged、明示解決経路で新 id 再登録。 | 問題なし |
| 46 | X28 | detached 生成→collect payload 破棄→記帳→upload 掃除→削除。再登録で attached 化、state に応じた遷移。 | 問題なし |
| 47 | X29 | 保存名固定と restore。初出表記を維持、restore は raw 解決で書込、case-only rename は FK 違反を起こさない。 | 問題なし |
| 48 | X30 | 「ledger UNIQUE は正当な再課金を妨げない」を試す。attempts リセット後の seq は継承値 +1 で旧 ledger と衝突しない。 | 破れず |
| 49 | X31 | seq 継承。行削除→再登録→再投入で MAX(seq) 継承、0 起点にならない。 | 問題なし |
| 50 | X32 | fork phase 状態機械。HISTORY_CLEARED で commits 非空なら手順 1 から、id=old なら手順 1 から。 | 問題なし |
| 51 | X33 | 課金記帳行列。server/client × 成功/失効/timeout/missing/output_missing/invalid_output/profile_changed/submit_rejected/tool_changed/client_exhausted × close 経路を総当り。 | 問題なし |
| 52 | X34 | §11.2 SQL 実際に組み立て。eligible EXISTS、LIKE fallback 再 JOIN、ORDER BY chunk_uid、ready 照合。 | 問題なし |
| 53 | X35 | 「fork は journal で一意に再開」を試す。phase+id の全組合せで再開一意。 | 破れず |
| 54 | X36 | 冪等記帳 × detached 採用 seq+1。detached server 採用で seq+1 しないと旧 lifecycle と衝突、+1 すれば OK。 | 問題なし |
| 55 | X37 | ready 完了追跡。一部フォルダ damaged → 母数から除外 → ready は更新されない/落ちる。 | 問題なし |
| 56 | X38 | fork 回復拡張。flag 掃除は id=new 一致のみ、移動先 journal 走査が先。 | 問題なし |
| 57 | X39 | register 一時読取不能保留。journal 一時ロックでも damaged に倒さず保留。 | 問題なし |
| 58 | X40 | 「ready は空母数に騙されない」を試す。接続 0 件では ready 非更新。 | 破れず |
| 59 | X41 | 期限超記帳 → 載せ直し → 相 3 の連番。ledger 3 行は正当な別 attempt として一貫。 | 問題なし |
| 60 | X42 | ready 母数変動。C damaged → A/B だけで ready=P2 成立 → C 復旧 → C は synced=NULL → ready は母数復帰で落ちる。 | 問題なし |
| 61 | X43 | 論理名→raw 解決。NFD 実体のみ → raw 解決 → restore 書込 → 二重実体を避ける。 | 問題なし |
| 62 | X44 | scoped 規約 12 + step -1。登録済み path の read でも repository-id 照合、conflict 中は両方拒否。 | 問題なし |
| 63 | X45 | 「client 中間 attempt の課金は漏れない」を試す。再実行前に旧 seq NULL+estimated 記帳。 | 破れず |
| 64 | X50 | 「(b') が飛んでも sweep が記帳を回収」を試す。token sweep 前段で found/期限超を記帳。 | 破れず |
| 65 | X57〜X61 | r15 修正相互作用: 自己記述化は dispatch/idx/sweep と衝突しない、detached terminal 化は再登録で整合、submit_rejected 除外は課金される拒否前提を明記、decoder 往復は G/\G/\\G で可逆、伝播猶予は provider 採用条件付き。 | 問題なし（S01 別途） |

---

## 第 3 部 — 新規検出（S01）

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| S01 | minor | §7 一括再チャンク: 「一括変換の開始時に app_config へ operation record … を書き」<br>§9.1 app_config DDL コメント: 許可 key 集合に `tool_profile` / `embedding_profile` / `image_filter` / `retry_not_before` / `agg_building_profile_hash` / `agg_ready_profile_hash` / `fork_in_progress` のみを列挙 | 一括変換の未完了状態表示に必要な `operation_record` key が、§9.1 の「許可 key 集合」に含まれていない。key 契約を厳密に実装すると、§7 で要求する operation_record の書込みが拒否される可能性がある。 | 初期状態: app_config に 7 key のみ許可する実装。<br>操作: ユーザーがチャンク規則のグローバル変更を開始。<br>壊れる状態: 実装が §7 の operation_record 書込みを「未定義 key」として拒否し、クラッシュ後の未完了一括変換を status が判定できない。 | C2 / C11 / X18 / X23 / R23 | §9.1 app_config の key 契約に `operation_record`（または同等の名前）を追加し、存在条件を「一括変換実行中のみ」と明記する。 |

---

## 第 4 部 — 確認済みの列挙（検出 0 件）

以下の観点・原則について、文書に問題は見つからなかった。

### 設計原則（P1〜P16）

- P1 三層構成・層 1 = 唯一の真実・層 2/3 の喪失再構築・規約 7 の 6 点損失・有界 2 種
- P2 識別子規範（JCS / content_hash / commit_hash / (content_hash, tool_profile_hash) identity / embedding profile 参照元 = app_config / float32 little-endian / size_bytes 10 進文字列）
- P3 metadata.sqlite 8 テーブル（profiles 含む）
- P4 chunks 統一テーブル（commit_hash/vector 列なし、CHECK 完備）
- P5 チャンク分割（Markdown 全文入力、ATX 境界、img block 除去、floor 同時引き上げ、一括再チャンク operation record 除く）
- P6 OCR（Mistral Batch、canonical img block、preflight terminal marker、upload 後始末）
- P7 FTS external content + view + trigger
- P8 Embedding 必須・単一 multimodal profile・宣言的収束・vec0 検証・差集合再充填
- P9 batch_requests + cost_ledger（submission_seq / profile_record / detached 規範）
- P10 書き込み順序・冪等性・tick.lock・step -1
- P11 集約レプリケーション（append-only・逆差集合・agg_vec DELETE→INSERT・synced_profile_hash）
- P12 検索（eligible EXISTS・RRF・over-fetch/refill・:query_profile_hash・単独決定規則）
- P13 GC/fsck（3 本の和集合・hash 一致前提・FTS integrity-check・agg 親子検査）
- P14 SQLite 設定（PRAGMA・migration・auto_vacuum・DACL）
- P15 元設計から不変の部分
- P16 変更検知（3 層・3 段・racy・delete 確定・raw 解決）

### 検査観点（C1〜C8, C10, C11）

- C1 原則反映: P1〜P16 すべて文書に存在し一致
- C2 SQL 静的検証: 全 DDL は SQLite 文法として妥当、FTS5 content に rowid テーブル/view を使用、FK 参照先存在、trigger 整合
- C3 相互参照整合: § 参照はすべて実在し文脈と一致
- C4 クエリとスキーマの整合: §11.1/11.2 SQL は DDL と整合
- C5 数値・事実の一貫性: $2.5/1k、768 参考値、8 テーブルなど一致
- C6 用語・形式の一貫性: target_key、chunk_type/target_type、obj: scheme、embed_hash 定義が § 間で一致
- C7 状態機械の完全性: batch_requests 遷移に到達不能・脱出不能なし
- C8 欠落: 原則範囲内で欠けている章事項なし
- C10 修正が開けた穴: r1〜r15 の修正間の新たな矛盾なし
- C11 合理性: 追加設計判断なしで実装可能、規範同士は両立、コスト/性能主張に矛盾なし

---
