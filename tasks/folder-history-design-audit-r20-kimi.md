不合格
target.md 全 3348 行を読了 — 最終 2 行: 『チャンク規則・フィルタ変更   : §7 / §8 (再チャンク — ローカル操作)』『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』

第 1 部 — 回帰確認 (C9)

fixed / superseded (ID 列挙のみ):
A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S29 / T01〜T18 / U01〜U06 / U08〜U24 / V01〜V08 / V10〜V20

not-fixed / partially-fixed:

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
|---|---|---|
| U07 | partially-fixed | §20.5 L2754-2762 に「同一 (size, mtime_ns, inode) のまま連続 3 回 (または 24 時間) 構文検証に失敗する実体は bytes のまま通常コミットする」と有界スキップ規範を記載するが、連続回数・24h 起点を tick 非常駐下で保持する仕組み (scan_cache 列) が §9.1 DDL に無いため、プロセス再起動でカウントがリセットされる |
| V09 | not-fixed | §20.5 L2758-2762 で「カウントの実体は scan_cache に永続化する」と明記するが、§9.1 L1443-1456 の scan_cache DDL に syntax_fail_count / first_failure_at 列が存在しない。V09 が要求する「DDL + reset 規則」の両側一致が成立しない。結果、構文検証スキップの有界化がメモリ依存となり、再起動ごとに初回化する |

第 2 部 — 探索ログ (C12)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 1 | X1 | 空フォルダ register → 1 ファイル追加 → 同 tick 内に rename → 次 tick で現在版 LWW が新名を指す | 問題なし |
| 2 | X1 | OCR in-flight 中に対象ファイルを delete → collect 時に output_missing として終端 | 問題なし |
| 3 | X1 | backfill ON で過去版に floor 設定 → 明示再生成 → floor 引き上げ順序を追跡 | 問題なし |
| 4 | X1 | フォルダ移動後の rebind → 旧 root_path の fp_cache 削除 → 次 tick スキャン | 問題なし |
| 5 | X1 | 2 台 PC でコピー後双方編集 → 片方を書き戻し → repository-id 照合で conflict | 問題なし |
| 6 | X2 | ファイル名に "obj:" と "<!-- img:" を含む → file_name 検証で name_invalid | 問題なし |
| 7 | X2 | 0 バイトファイル → content_hash 計算 → 通常コミット | 問題なし |
| 8 | X2 | シンボリックリンク → symlink 非追跡 → absent 扱い | 問題なし |
| 9 | X2 | annotation 値に "-->" を含む → §6 可逆エスケープ → チャンク text に反映 | 問題なし |
| 10 | X2 | 手書き偽造 obj: 参照 → §7 実在検証で phantom 防止 | 問題なし |
| 11 | X3 | case-insensitive → case-sensitive ボリューム移動 → 系列分裂 (create) | 問題なし |
| 12 | X3 | NFD 実体 (macOS) → NFC 論理名保存 → raw 解決で一貫 | 問題なし |
| 13 | X3 | 超長パス → name_invalid + status | 問題なし |
| 14 | X4 | 時計後退 → created_at = max(確定時刻, 最新+1) で単調維持 | 問題なし |
| 15 | X4 | 同一 ms 内複数コミット → commit_hash バイト昇順 tie-break | 問題なし |
| 16 | X4 | generated_at 更新 → max(now, 旧+1) で単調 | 問題なし |
| 17 | X5 | 10 万ファイル walk → fp_cache 段 0 で枝スキップ | 問題なし |
| 18 | X5 | 100 万 chunk 全置換 → §9.3-b 派生単位 DELETE→INSERT | 問題なし |
| 19 | X5 | SQLite bind 上限 → 差集合クエリで回避 | 問題なし |
| 20 | X6 | 2 文字語検索 → trigram 0 件 → LIKE fallback | 問題なし |
| 21 | X6 | sqlite-vec vec0 KNN + WHERE 混在 → 使用制限を確認 | 問題なし |
| 22 | X6 | JCS 数値 2^53 超 → size_bytes を 10 進文字列化 | 問題なし |
| 23 | X7 | schema_version user_version → 新旧アプリ混在 → fail-closed | 問題なし |
| 24 | X7 | grammar v 将来変更 → v+1 → 一括再 materialize | 問題なし |
| 25 | X8 | tmp/ 権限 0700 / objects 0600 → 他ユーザー読取防止 | 問題なし |
| 26 | X8 | file_name に ".." → name_invalid → path traversal 防止 | 問題なし |
| 27 | X8 | Batch 原本 filename に intent_token 埋込 → 追跡・掃除 | 問題なし |
| 28 | X9 | バックアップ中書き込み → tick.lock 下静止コピーで回避 | 問題なし |
| 29 | X9 | object 破損 → fsck hash 再照合 → 修復誘導 | 問題なし |
| 30 | X9 | metadata.sqlite だけ復元 → §9.3-z 後退検出 → wipe + resync | 問題なし |
| 31 | X10 | .folder-history 手動削除 → damaged → 再登録 | 問題なし |
| 32 | X10 | zip 往復で inode/mtime 全変化 → deep-scan で補正 | 問題なし |
| 33 | X11 | profile 変更 → kind=2 行の一括削除なし → 宣言的収束 | 問題なし |
| 34 | X11 | floor_generated_at と reconcile 0.5 の相互作用 → floor NULL 化 | 問題なし |
| 35 | X12 | watch_root 登録 → スキャン → コミット → OCR → チャンク → embed → replicate → 検索 → 原本解決 | 問題なし |
| 36 | X13 | 明示操作カタログ (register/unregister/fork/restore/drop) の手順定義を追跡 | 問題なし |
| 37 | X14 | 429 レート制限 → retry_not_before 永続化 → 次 tick まで抑制 | 問題なし |
| 38 | X14 | fp_cache 孤児 → 完全 walk 成功時 mark-and-sweep | 問題なし |
| 39 | X15 | 「重複課金は最悪 job 1 回分」を試行 → 4 照合点・期限判定・伝播猶予で破れず | 破れず |
| 40 | X16 | 2 相 submit と 1 job = 1 repository → intent_token job 単位 | 問題なし |
| 41 | X16 | reconcile 縮小後の state=1 job 消滅 → job_missing 時刻基準で脱出路 | 問題なし |
| 42 | X16 | cost_ledger 追記点 → 全 close 経路で冪等 ON CONFLICT | 問題なし |
| 43 | X17 | register 途中クラッシュ → damaged → 再実行 | 問題なし |
| 44 | X17 | fork 後 GC・agg の整合 → 旧履歴参照 object の回収 | 問題なし |
| 45 | X18 | profiles 孤児 → 能動削除なし → INSERT OR IGNORE | 問題なし |
| 46 | X18 | pending_deletes と walk 完全性 → 不完全 walk で停止 | 問題なし |
| 47 | X19 | migration 単一 Tx と journal_mode DELETE/WAL → 巻き戻り安全 | 問題なし |
| 48 | X19 | 相 1→相 2→相 3 各境界クラッシュ → submission_seq/attempts で収束 | 問題なし |
| 49 | X20 | 「cost_ledger は月跨ぎ retry を発生月へ配賦」を試行 → ts = 確定時刻で破れず | 破れず |
| 50 | X21 | 相 1 profile_hash / upload_cleaned リセット → intent 回復・collect 突合 | 問題なし |
| 51 | X21 | vec 差集合再充填 → §8-b 置換・§8-d 掃除の重複/取りこぼし | 問題なし |
| 52 | X22 | fork phase 機械 4 状態 × 全クラッシュ位置 → 再開一意 | 問題なし |
| 53 | X23 | app_config / cost_ledger / detached / name_collision の読み手一貫 | 問題なし |
| 54 | X24 | 「agg 毎 tick 検査は一度きり破棄を吸収」を試行 → 毎 tick 照合で破れず | 破れず |
| 55 | X25 | app.sqlite 単独で横断検索 → app_config から query_vector 生成 | 問題なし |
| 56 | X25 | restore 宛先検証 → in-place/export/content_hash 単独を追跡 | 問題なし |
| 57 | X26 | state=0 + batch_job_id 非 NULL → client 前計上済み dispatch | 問題なし |
| 58 | X26 | profile_record snapshot → 相 1/相 3/採用/§5.7 保存で一貫 | 問題なし |
| 59 | X27 | journal 全境界クラッシュ + 移動 → phase + id で再開 | 問題なし |
| 60 | X28 | detached 生成 → collect payload 破棄 → 記帳 → 掃除 → 削除 | 問題なし |
| 61 | X29 | 保存名固定 → restore 宛先・§11.1 PARTITION・FK 一貫 | 問題なし |
| 62 | X30 | 「ledger UNIQUE は正当な再課金を妨げない」を試行 → submission_seq で破れず | 破れず |
| 63 | X31 | submission_seq 継承 × 相 3 → 0 起点では UNIQUE 衝突を確認 | 問題なし |
| 64 | X31 | reconcile close 3 付随処理 → floor NULL/記帳/token 掃除 | 問題なし |
| 65 | X32 | fork phase 全数トレース → 削除順・id=old 分岐 | 問題なし |
| 66 | X33 | 課金記帳網羅行列 → 全 close 経路で 0/1 行 | 問題なし |
| 67 | X34 | §11.2 掲載 SQL → eligible 再 JOIN / ORDER BY 第 2 キー / ready 照合 | 問題なし |
| 68 | X35 | 「seq 継承で UNIQUE 衝突不可能」を試行 → MAX 継承で破れず | 破れず |
| 69 | X36 | 冪等記帳 × seq 継承 × detached 採用 → 別 attempt の課金が吸収されない | 問題なし |
| 70 | X37 | ready 母数 → missing/fork/damaged/一時読取不能除外 + 0 件非更新 | 問題なし |
| 71 | X38 | flag 掃除 id 一致 × 自動 rebind × 再発見除外 → 一意収束 | 問題なし |
| 72 | X39 | 一時読取不能保留・同 root_path 退役・delete 最終型判定 | 問題なし |
| 73 | X40 | 「query_profile_hash 固定で TOCTOU 不可能」を試行 → 同一 read Tx で破れず | 破れず |
| 74 | X41 | 記帳済み判別述語 × seq 連番 → token/job id 混在で一意 | 問題なし |
| 75 | X42 | ready 母数の動態 → damaged 復帰で ready 降下/再昇の系列 | 問題なし |
| 76 | X43 | 論理名→raw 解決 3 呼出点 × NFC/NFD/collision × case | 問題なし |
| 77 | X44 | scoped 規約 12 × 4 分類 × standalone 表示 → 分岐一意 | 問題なし |
| 78 | X45 | 「state=0 server 成果あり close は無記帳破棄しない」を試行 → (b') 自己記述化で破れず | 破れず |
| 79 | X46 | 述語キー × seq 連番 → 期限超 token → 載せ直し → 相 3 job id の 3 行正当性 | 問題なし |
| 80 | X47 | 期限超同一 Tx × token rotation × detached → 旧 token 記帳が新 token 述語に干渉しない | 問題なし |
| 81 | X48 | restore 保全 × §20.5 × resolver → 現内容 ≠ LWW 時のコミット上書き | 問題なし |
| 82 | X49 | 回復先行 × 全 §21 操作 → 回復不能時の挙動 | 問題なし |
| 83 | X50 | 「§6/§7 全段往復可逆」を試行 → G/\G/\\G test vector で破れず | 破れず |
| 84 | X51 | seq 行 UPDATE × 連番一貫 → 期限超/(b')/sweep/detached 交錯 | 問題なし |
| 85 | X52 | expired terminal × 遷移表 × sweep → token 残存と削除条件整合 | 問題なし |
| 86 | X53 | 4 照合点対称性 → intent 回復/detached/(b')/sweep で 8 要素比較 | 問題なし |
| 87 | X54 | 回復ゲート例外 × journal チェック × flag 掃除 → 全組合せ帰結一意 | 問題なし |
| 88 | X55 | :current_profile/:current_tool 組合せ → tool 混在時 FTS 継続 | 問題なし |
| 89 | X56 | §6/§7 エスケープ条件の非対称 → decoder 拡張で往復可逆 | 問題なし |
| 90 | X57 | 自己記述化 × dispatch/idx_batch_open/sweep → state=0 判定への影響 | 問題なし |
| 91 | X58 | detached terminal × 再登録 → 意図されたコスト注記と整合 | 問題なし |
| 92 | X59 | submit_rejected 除外 × 課金される拒否 → 分岐で同一 Tx 記帳 | 問題なし |
| 93 | X60 | decoder 拡張全数 → escape/un-escape/認識 3 述語の整合 | 問題なし |
| 94 | X61 | 「(i)〜(iv) 1 Tx で偽 expired は起きない」を試行 → (iii') 出口で破れず | 破れず |
| 95 | X62 | job_create_started_at 列導入後 lifecycle → NULL = 相 2b 未着手 | 問題なし |
| 96 | X63 | error='cancelled' × 遷移表 × 再登録 → 自動再投入の範囲 | 問題なし |
| 97 | X64 | found 判別 IN (job id, token) → 別 attempt の誤吸収 | 問題なし |
| 98 | X65 | no-replace rename 非対応環境 → fallback 規範 | 問題なし |
| 99 | X66 | 規範↔要約・SQL・DDL コメントの非伝播 → §9.1↔§21.2 等で両側確認 | 問題なし |
| 100 | X67 | rotation ガード × unknown 行 → stalled 可視化 | 問題なし |
| 101 | X68 | cancel × 明示 retry → 記帳が毎回正しく積まれる | 問題なし |
| 102 | X69 | fts_cap × RRF 再現率 → 内側段 LIMIT で決定論的打切 | 問題なし |
| 103 | X70 | 変換決定論 × コンバータ更新 → tool_profile 変更で再判定 | 問題なし |
| 104 | X71 | rotation ガード縮小 → state=0 載せ直し・client dispatch は対象外 | 問題なし |
| 105 | X72 | 明示 abandon × 後日 job 出現 → IN 判別で吸収 | 問題なし |
| 106 | X73 | convert_failed × tool_profile 変更 → 旧 terminal 行の独立性 | 問題なし |
| 107 | X74 | 有界スキップ × 一時 EIO → カウント分離 (U07/V09 の列欠落を除く) | 問題なし |
| 108 | X75 | scope_id: provider  workspace 概念なし → empty scope が異 account 間で同一と誤判定する可能性 | 問題なし (採用条件で scope 安定を運用前提としているため、設計選択の帰結) |
| 109 | X76 | abandoned × 遷移表・削除条件 → token NULL 化後の削除到達 | 問題なし |
| 110 | X77 | fp スキップ例外の検査コスト → 登録フォルダの journal 存在検査 | 問題なし |
| 111 | X78 | ガード拡張 × floor 明示再生成 → state=2 token 残存行への floor 設定 | 問題なし |

第 3 部 — 新規検出 (C1〜C8, C10, C11, C12)

新規検出 0 件。

第 4 部 — 確認済みの列挙

C1 (原則反映 P1〜P16): 各原則に対応する記述が存在し、弱められていないことを確認。
C2 (SQL 静的検証): 全 DDL が SQLite 文法として妥当、FTS5 external content は rowid テーブルを参照、FK/PK 整合、trigger ペア整合を確認。
C3 (相互参照整合): §参照は実在し、文脈と一致。
C4 (クエリとスキーマ整合): §11.2 等の SQL が DDL と整合。
C5 (数値・事実一貫性): $2.5/1k、768 参考値、RRF k=60、8 テーブル等が一致。
C6 (用語・形式一貫性): target_key、hex 小文字、chunk_type/target_type 対応等が一致。
C7 (状態機械完全性): クラッシュ位置ごとに次 tick が収束する記述を確認。
C8 (欠落): 上記 U07/V09 を除き、原則範囲内の欠落なし。
C10 (修正が開けた穴): 修正箇所間の新たな矛盾は検出されず (U07/V09 を除く)。
C11 (合理性): 追加設計判断なしで実装可能、規範同士が両立。
C12 (探索型監査): 上記 111 シナリオを実行、新たな破綻は検出されず。
P1〜P16: 各原則が文書に反映されていることを確認 (上記 U07/V09 は C9 項目で、P1〜P16 の原則自体の反映ではなく実装基盤の欠落)。
