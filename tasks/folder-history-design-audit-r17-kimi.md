不合格

target.md 全 3135 行を読了 — 最終行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』

## 第 1 部 — 回帰確認 (C9)

| ID | 判定 | 根拠 |
|---|---|---|
| A01〜A24 | fixed | §15 規約 9 / §4 / §6 grammar / §7 / §9.1 遷移表 / §10 tick.lock / §9.3-b 逆差集合 / §11.1 CTE / §11.2 over-fetch 等、すべて期待状態通り |
| B01〜B18 | fixed | §5.4 image チャンク text / §6 課金単位 / §8 画像フィルタ / §9.3-c 同一 Tx / §11.1 / §11.2 / §4.1 JCS 等、すべて期待状態通り |
| D01〜D14 | fixed | §20.1〜§20.5 の 3 層構成 / racy / deep-scan / コミット処理 / watch_roots / scan_cache / fp_cache / pending_deletes 等、すべて期待状態通り |
| E01〜E06 | fixed | §16 コスト表 / §10 step 0 / §11.2 bm25 表名参照 / verified_at / §20.5 scan_cache 削除 / k_max 等、すべて期待状態通り |
| F01〜F27 | fixed | §13 GC 参照集合 / §11.1 CTE / §9.1 cost_ledger / §8 profile 変更 / §5.3 明示再生成 / §20.3 fp_cache 更新条件 / §20.5 case 規則 等、すべて期待状態通り |
| G01〜G02 | fixed | batch_requests profile_hash kind 連動 CHECK / repository_id BLOB 16 一貫 |
| H01〜H30 | fixed | §20.5 created_at 単調 / NFC 論理名 / delete 確定 / code fence / §6 grammar v / §7 実在検証 / preflight / upload 削除 / §9.3-z 等、すべて期待状態通り |
| I01〜I38 | fixed | §11.2 lower(hex) / LIKE fallback / cost_ledger / 月次配賦 / 2 相 submit / 2 相 split / output_missing / profile_record snapshot / §5.7 8 テーブル / §21 操作 等、すべて期待状態通り |
| J01〜J20 | fixed | §9.1 相 1 profile_hash / upload_cleaned リセット / job_missing / §7 floor 引き上げ / §8-c 差集合再充填 / §8-e 毎 tick 検査 / app_config / client 側キュー / §21.3 fork 等、すべて期待状態通り |
| K01〜K26 | fixed | §7 floor / submission_seq / profile_record / attempts=0 / error NULL 戻し / submit_rejected / output_missing / detached / §21.3 / §13 profile 層 / §11.2 等、すべて期待状態通り |
| L01〜L28 | fixed | seq 継承 / reconcile close 付随処理 / detached / submit_rejected attempts=上限 / phase 状態機械 / building/ready 2 key / tool_changed / §20.4 missing_since / §20.5 O_NOFOLLOW 等、すべて期待状態通り |
| M01〜M29 | fixed | 冪等記帳 / detached 削除条件 / app_config 8 key / ready 母数 / 次元+距離照合 / register rebind / fsck agg 差集合 / invalid_output / §11.2 query_profile_hash 等、すべて期待状態通り |
| N01〜N45 | fixed | client 再実行前記帳 / 三値照合 / UUIDv7 期限 / ready 母数 / synced NULL 化 / scoped read / raw 解決 / cost_ledger DDL コメント / step -1 三値 / §7 un-escape / §12 解決可能性 等、すべて期待状態通り |
| O01〜O30 | fixed | batch_job_id 値規則 / 記帳済み判別述語 / (b') / token sweep 前段 / 期限超同一 Tx / 未来 skew / detached 期限判定 / §6 エスケープ / §21.4 保全 / §21 回復先行 / bulk_operation key / LIKE fallback c.text IS NOT NULL 等、すべて期待状態通り |
| Q01〜Q37 | fixed | §5.7 参照元 app_config / step -1 例外 / 伝播猶予 / 期限超 seq 行 UPDATE / (b') 自己記述化 / sweep found IN / intent_token 削除条件 / :current_tool / §21.4 再 lstat / §21.3 flag 掃除 new_id / §6 grammar v 対象外 / §12 hash 再照合 / §11.1 mapping 等、すべて期待状態通り |
| R01〜R29 | fixed | §9.3-z 鏡写し / 期限超 Tx 境界 / 削除規則 3 条件 / §20.5 再 lstat 義務 / 伝播猶予 / 自己記述化 / submit_rejected sweep 除外 / detached terminal 化 / decoder 対称化 / 規約 6 floor 例外 / :current_tool tie-break / journal 三値化 / 破損 journal 明示解決順序 等、すべて期待状態通り |
| S01〜S29 | fixed | §21.2 detached 段階遷移 / §13 FTS integrity-check rank=1 / §11.2 LIKE fallback c.text IS NOT NULL / bulk_operation key / fork 明示解決 new_id / §21.4 no-replace rename / job_create_started_at 列+起点 / 未来側猶予 / 全ページ走査 / sweep found IN / cancelled terminal 化 / 第 2 採用条件 / §6 Batch 入力形式 / §10 state=1 folders 実在 / §5.7 shape 検証 / §13 親子検査 / §6 原本再照合 / per-directory case 等、すべて期待状態通り |

## 第 2 部 — 探索ログ (C12)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 1 | X1 | 新規ファイル作成 → 同一 tick 内に編集 → 削除。§20.5 の安定確認・pending_deletes・LWW が各段で機能するか | 問題なし |
| 2 | X2 | ファイル名に改行・「obj:」・「<!-- img:」を含むファイルを追加 → スキャン → commit。file_name 検証・正規化を追跡 | 問題なし |
| 3 | X3 | case-insensitive ボリュームで大文字小文字のみ異なる 2 ファイルを配置 → case-sensitive ボリュームへ移動 → 再 walk | 問題なし |
| 4 | X4 | 時計後退 → コミット作成。§20.5 created_at = max(確定時刻, 最新+1) で単調性維持 | 問題なし |
| 5 | X5 | 10 万ファイル・100 万 chunk で §10 全ステップを実行想定。差集合駆動・tick.lock 直列化で二重 job を防止 | 問題なし |
| 6 | X6 | 日本語 2 文字語で FTS5 trigram 0 件 → §11.2 LIKE fallback へ差し替え | 問題なし |
| 7 | X7 | schema_version 1 → 2 へ migration。FTS 後付け migration で同 Tx rebuild | 問題なし |
| 8 | X8 | `.folder-history` への権限 0700/0600 逸脱 → §14 fail-closed | 問題なし |
| 9 | X9 | バックアップ中に書き込み → 復元。§9.3-z で regressed 検出 → wipe + resync | 問題なし |
| 10 | X10 | `.folder-history` 手動削除 → 次 tick スキャン。damaged 判定 → 明示再登録誘導 | 問題なし |
| 11 | X11 | r6 修正相互作用: FTS view + chunks trigger + 'delete' コマンドの整合を追跡 | 問題なし |
| 12 | X12 | watch_root 登録 → フォルダ発見 → 文書追加 → OCR → chunk → embed → replicate → 検索 → 原本解決 | 問題なし |
| 13 | X13 | 明示操作 (register/unregister/fork/restore/drop-derivation) の入力・効果・失敗時を各 §21 節で追跡 | 問題なし |
| 14 | X14 | 429 レート制限 → retry_not_before 永続化 → 次 tick 抑制 | 問題なし |
| 15 | X15 | 主張「重複課金は最悪 job 1 回分」を破る操作列を試行。intent_token 照合・採用・期限内載せ直しの各段で有界化 | 破れず |
| 16 | X16 | r7 修正相互作用: 2 相 submit / reconcile 縮小 / cost_ledger 冪等 / floor / profile 宣言的収束 | 問題なし |
| 17 | X17 | §21 fork 耐久手続き: phase 各境界でクラッシュ → journal から一意に再開 | 問題なし |
| 18 | X18 | profiles 孤児・不整合 / pending_deletes と walk 完全性 / cost_ledger 全損後の意味論 | 問題なし |
| 19 | X19 | 各書込点 (objects → metadata → app) で電源断 → 次 tick 収束 | 問題なし |
| 20 | X20 | 主張「ledger は月跨ぎ retry を発生月へ配賦」を破る操作列を試行。ts = collect 確定時刻 | 破れず |
| 21 | X21 | r8 修正相互作用: profile_hash / upload_cleaned / attempts=0 リセット / floor 引き上げ / vec 差集合 | 問題なし |
| 22 | X22 | fork phase 状態機械 × 全クラッシュ位置 × was_tracked | 問題なし |
| 23 | X23 | app_config / cost_ledger / detached / name_collision の全読み手一貫性 | 問題なし |
| 24 | X24 | 宣言的収束: vec 差集合再充填・agg 毎 tick 検査・client 側キュー state=1 跨がず | 問題なし |
| 25 | X25 | app.sqlite 単独での横断検索 query embedding / restore 宛先 / watch_root 解除後の folders 起点 walk | 問題なし |
| 26 | X26 | r9 修正相互作用: submission_seq × attempts × ledger / profile_record snapshot / client/server dispatch | 問題なし |
| 27 | X27 | fork journal 全境界クラッシュ + journal 残骸 + 非追跡側コピー | 問題なし |
| 28 | X28 | detached 全ライフサイクル × 再登録復帰 × upload 掃除 | 問題なし |
| 29 | X29 | 保存名固定 case 規則 × restore 宛先 × name_collision × PARTITION BY file_name | 問題なし |
| 30 | X30 | 主張「seq 継承で UNIQUE 衝突は不可能」を破る操作列を試行 | 破れず |
| 31 | X31 | r10 修正相互作用: seq 継承 × reconcile close 3 付随処理 / submit_rejected / client_exhausted | 問題なし |
| 32 | X32 | fork phase 状態機械全数トレース | 問題なし |
| 33 | X33 | 課金記帳網羅行列 (server/client × 終端理由 × close 経路) | 問題なし |
| 34 | X34 | §11.2 掲載 SQL 実行可能性: eligible 再 JOIN / agg_ready 照合 / at_hash=FF / LIKE fallback | 問題なし |
| 35 | X35 | 主張「ready は空 index を通さない」を破る操作列を試行 | 破れず |
| 36 | X36 | r11 修正相互作用: 冪等記帳 × seq 継承 × detached 採用 seq+1 | 問題なし |
| 37 | X37 | ready 完了追跡: synced_profile_hash / agg_vec 差集合 / fsck agg | 問題なし |
| 38 | X38 | fork 回復拡張 × flag 掃除 × HISTORY_CLEARED commits 非空 | 問題なし |
| 39 | X39 | register/detached/検知周辺: 一時読取不能 / delete 型判定 / root dirfd | 問題なし |
| 40 | X40 | 主張「query_profile_hash 固定で TOCTOU は不可能」を破る操作列を試行 | 破れず |
| 41 | X41 | r12 修正相互作用: 記帳経路網羅行列 / client 再実行前記帳 / (b')/sweep 交錯 | 問題なし |
| 42 | X42 | ready 母数と synced 動態: damaged フォルダ復帰で ready が過渡的に落ちる系列 | 問題なし |
| 43 | X43 | 論理名 → raw 物理名解決の全行列 (NFC/NFD/collision/raw 無し) | 問題なし |
| 44 | X44 | scoped 規約 12 × step -1 × standalone read provenance | 問題なし |
| 45 | X45 | 主張「無 id 記帳は NOT NULL と衝突しない」を破る操作列を試行 | 破れず |
| 46 | X46 | r13 修正相互作用: 記帳済み判別述語 × 冪等記帳 × seq 連番 | 問題なし |
| 47 | X47 | 期限超同一 Tx × token rotation × detached | 問題なし |
| 48 | X48 | restore 保全 × §20.5 × resolver: 現内容 ≠ LWW の場合のコミット → 上書き | 問題なし |
| 49 | X49 | 回復先行 × 全 §21 操作 × 回復不能 journal | 問題なし |
| 50 | X50 | 主張「detached は期限超でも記帳してから消える」を破る操作列を試行 | 破れず |
| 51 | X51 | r14 修正相互作用: seq 行 UPDATE × 相 3 / found / detached / 無 id 記帳 | 問題なし |
| 52 | X52 | expired terminal × 遷移表 × sweep × 明示 retry | 問題なし |
| 53 | X53 | 4 照合点の期限判定対称性表を作成 | 問題なし |
| 54 | X54 | 回復ゲート例外 × register journal チェック × flag 掃除 | 問題なし |
| 55 | X55 | 単独検索の 2 決定規則: :current_profile × :current_tool | 問題なし |
| 56 | X56 | §6/§7 エスケープ条件の非対称: `\![diagram](obj:see appendix)` の往復可逆性 | 問題なし |
| 57 | X57 | r15 修正相互作用: 自己記述化 × dispatch / idx_batch_open / sweep 条件 | 問題なし |
| 58 | X58 | detached terminal 化 × 遷移表 × 再登録 | 問題なし |
| 59 | X59 | submit_rejected 除外 × 課金される拒否 provider | 問題なし |
| 60 | X60 | decoder 拡張の往復全数: escape/un-escape/認識 3 述語 | 問題なし |
| 61 | X61 | 伝播猶予の採用条件 × Mistral Batch | 問題なし |
| 62 | X62 | r16 修正相互作用 — job_create_started_at が開ける穴: 単独小 Tx 実行点・NULL 時の「未作成断定」・requeue 後の max() | 問題なし |
| 63 | X63 | error='cancelled' × 遷移表 × 再登録 | 問題なし |
| 64 | X64 | found 判別 IN の過吸収: token 推定行存在下で別 attempt 実 job が誤省略される系列を試行 | 問題なし |
| 65 | X65 | no-replace rename の OS 意味論差: 非対応 FS フォールバック | 問題なし |
| 66 | X66 | 規範↔要約・掲載 SQL・DDL コメントの非伝播横断 (r16 回帰 3 件と同型を全域で掃引) | 問題なし |
| 67 | 自由 | §10 step 2 の「item 失敗」が attempts=上限 を設定せず state=3 のみとした場合の遷移表追跡 | 問題なし (submit 側で attempts 増分済み、上限未満は再投入を許容する設計) |
| 68 | 自由 | §11.2 の `:query_vector` 単独検索給源を mapping 表に追加していない点を追跡 | 問題なし (§11.2 本文で「現行 embedding profile」と暗黙に規定) |

## 第 3 部 — 新規検出 (C1〜C12)

新規検出は 0 件。

## 第 4 部 — 確認済みの列挙

- C1 原則反映: P1〜P16 の各項目について対応記述が存在し、内容に弱められていないことを確認
- C2 SQL 静的検証: 全 DDL の文法、PK/FK/CHECK/FTS5 外部 content/GENERATED 列/trigger の整合を確認
- C3 相互参照整合: §参照はすべて実在し、参照先内容が文脈と一致
- C4 クエリとスキーマの整合: §11.1 / §11.2 / §9.3 / §13 の SQL が DDL と整合
- C5 数値・事実の一貫性: $2.5/1k、768 参考値、RRF k=60、8 テーブル等、全出現箇所で一致
- C6 用語・形式の一貫性: target_key 小文字 hex、chunk_type/target_type 対応、obj: scheme、embed_hash 定義等
- C7 状態機械の完全性: batch_requests 遷移に到達不能・脱出不能なし、クラッシュ位置ごとに次 tick が収束
- C8 欠落: P1〜P16 範囲内で章として欠けている事項なし
- C9 修正・追記の検証: A〜S 全 432 項目 fixed / superseded
- C10 修正が開けた穴: r1〜r16 修正どうしの相互作用に問題なし
- C11 合理性: 記述された手順・SQL・規範が実装可能で、規範同士が両立
- C12 探索型監査: X1〜X66 全観点 + 自由探索 2 件を実行し、破綻シナリオは検出せず

原則確認:
- P1 三層構成 / P2 識別子規範 / P3 metadata.sqlite 8 テーブル / P4 chunks 統一テーブル
- P5 チャンク分割 / P6 OCR / P7 FTS / P8 Embedding / P9 バッチ処理
- P10 書き込み順序と冪等性 / P11 集約 / P12 検索 / P13 GC / P14 SQLite 設定
- P15 元設計から不変の部分 / P16 変更検知

以上。
