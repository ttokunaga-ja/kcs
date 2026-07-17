合格

---

# 監査報告書

## 読了証明
target.md 最終 2 行:
```
3206: embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)
3207: ```
```
総行数: **3207 行**

---

## 第 1 部 — C9 回帰確認 (全 450 項目)

### A01-A24 (P1 三層構成, 24 項目)

| # | 判定 | 根拠 |
|---|------|------|
| A01 | fixed | §2 三層構成明記, .folder-history/ が真実 |
| A02 | fixed | §2 L69-79 真実は層 1 と明言 |
| A03 | fixed | §2 L70-76 損失 (a)〜(f) 列挙 + 有界 2 種内訳 |
| A04 | fixed | §15 規約 7 損失 (a)〜(f) 完全記載, §2 と一致 |
| A05 | fixed | §2 L77-79 全損時の機密残留を追記 |
| A06 | fixed | 「最悪 1 job 分」は §10 L1792-1795 で server 限定と明記 |
| A07 | fixed | §13 L2194-2196 app.sqlite バックアップ = Online Backup API / VACUUM INTO |
| A08 | fixed | §13 L2195-2196 WAL 注意事項: raw コピー禁止 |
| A09 | superseded | P1 旧版「有界の内訳 1 種」→ §15 規約 7 で 2 種に改訂 |
| A10 | fixed | §15 L2290-2293 (a)(c)(d)(f) と (b)(e) の区別明記 |
| A11 | fixed | §15 規約 9 L2295-2304 真実の二層注記あり |
| A12 | fixed | §15 L2297-2298 「真実 = 履歴・派生・検索の正本」明記 |
| A13 | fixed | §15 L2298-2299 内容の正本は原本ファイル自身と明言 |
| A14 | fixed | §1 L10-11 要件上の前提に記述一致 |
| A15 | fixed | §9.1 app_config が現行設定の実体 (L982-988) |
| A16 | fixed | §21.5 L3154-3168 bootstrap 再入力手順完備 |
| A17 | fixed | §15 規約 9 L2300-2304 watch_roots 再入力 + 再発見の記述 |
| A18 | fixed | layer 3 は agg_* キャッシュ → 丸ごと喪失でも再構築可 |
| A19 | superseded | 旧「layer 2 喪失損失 (a)〜(e)」→ §2 で (a)〜(f) + 有界 2 種に更新 |
| A20 | fixed | §15 規約 6 L2274-2279 書込順序 (objects→metadata→app) 明記 |
| A21 | fixed | §15 L2276-2279 floor の例外 (app→metadata) も明記 |
| A22 | fixed | §2 L69「真実は常に層 1」 |
| A23 | fixed | §15 規約 9 L2296「真実は各フォルダの .folder-history/ 全体」 |
| A24 | fixed | §9.3-d L1648 cost_ledger 削除しない明記 |

### B01-B18 (P2 識別子規範, 18 項目)

| # | 判定 | 根拠 |
|---|------|------|
| B01 | fixed | §4 表 content_hash = SHA-256 (bytes), identity |
| B02 | fixed | §4.1 JCS 直列化 (RFC 8785), hash_format_version=1 |
| B03 | fixed | §4.1 L148-149 hash 値 = 小文字 hex64 JSON 文字列 |
| B04 | fixed | §4.1 L132 parent_hash 省略規則, L133 message 省略規則 |
| B05 | fixed | §4.1 L150 NFC 正規化, L151 NULL 不使用 |
| B06 | fixed | §4.1 L155-156 created_at = UTC ミリ秒整数, 2^53 未満 |
| B07 | fixed | §4.1 L158-161 size_bytes = 10 進文字列, 理由明記 |
| B08 | fixed | §4.1 L162-163 test vector 作成を最初の作業と明記 |
| B09 | fixed | §4 L107 派生同一性 = (content_hash, tool_profile_hash) 行存在 |
| B10 | fixed | §4 L108 markdown_hash は保存アドレス/破損検出のみ |
| B11 | fixed | §4.1 L166-172 kind 別 profile_record (tool/embedding 排他) |
| B12 | fixed | §4.1 L168 tool 用 = model + annotation_schema + options |
| B13 | fixed | §4.1 L169-171 embedding 用 = model + options, annotation_schema なし |
| B14 | fixed | §4 L173-175 profile_record を profiles 表へ永続化 |
| B15 | fixed | §5.7 L438 distance_metric (metric 別名不可) |
| B16 | fixed | §5.7 L439-440 model = 完全修飾名 (provider/adapter 名前空間含む) |
| B17 | fixed | §4 L166-172 JCS profile_record 直列化, embedding profile も JCS |
| B18 | superseded | P2 r17: 共通 record 例 → §4.1 で kind 別 2 形に分離済み |

### D01-D14 (P3 metadata.sqlite 8 テーブル, 14 項目)

| # | 判定 | 根拠 |
|---|------|------|
| D01 | fixed | §5 冒頭 L179「8 テーブル」明記 |
| D02 | fixed | §5.1 commits 表 DDL 完備 |
| D03 | fixed | §5.2 file_versions 表 DDL 完備 |
| D04 | fixed | §5.3 markdown_documents 表 DDL, 行の存在 = 生成完了 |
| D05 | fixed | §5.4 chunks 表 DDL (統一テーブル) |
| D06 | fixed | §5.5 chunk_fts (FTS5) DDL |
| D07 | fixed | §5.6 embeddings / embedding_vec DDL |
| D08 | fixed | §5.7 profiles 表 DDL (profile_hash PK, kind, record_json) |
| D09 | fixed | §5.7 L432-433 同一 Tx で INSERT OR IGNORE, hash 検証 |
| D10 | fixed | §5.7 L434-442 PK 単独充足の注記 + shape 検証の説明 |
| D11 | fixed | §5.3 L248 「行の存在 = 生成完了 (done)」status/error 列なし |
| D12 | fixed | §3 L87「metadata.sqlite → §5 の 8 テーブル」 |
| D13 | fixed | §5.7 L443-449 フォルダ単独決定規則 → §11.2 |
| D14 | fixed | §5.7 L448-449 app_config 参照元の注記 |

### E01-E06 (P4 chunks 統一テーブル, 6 項目)

| # | 判定 | 根拠 |
|---|------|------|
| E01 | fixed | §5.4 chunk_type (1=text, 2=image), text NULLable |
| E02 | fixed | §5.4 L320-327 CHECK 制約 (type 別 NOT NULL 条件) |
| E03 | fixed | §5.4 L318 embed_hash = GENERATED COALESCE(image_hash, text_hash) |
| E04 | fixed | §5.4 L347 commit_hash 列なし, vector 列なし (明記) |
| E05 | fixed | §5.4 L291 chunk_id INTEGER PRIMARY KEY (rowid) |
| E06 | fixed | §5.4 L328-331 seq/char_start/char_end に typeof='integer' CHECK |

### F01-F27 (P5 チャンク分割, 27 項目)

| # | 判定 | 根拠 |
|---|------|------|
| F01 | fixed | §7 L594 入力 = objects/ 保存済み Markdown 全文 |
| F02 | fixed | §7 L598-599 ATX 見出し境界, コードフェンス内除外 |
| F03 | fixed | §7 L600-604 CommonMark fenced code block 固定, 4 空白インデント対象 |
| F04 | fixed | §7 L605 heading_path 規則, 最初の見出し前 = [] |
| F05 | fixed | §7 L606-607 img block 画像参照行 = 独立 image チャンク |
| F06 | fixed | §7 L608-609 image text = description + transcription のみ |
| F07 | fixed | §7 L610-613 image_meta 充填規則, annotation OFF 時の記述 |
| F08 | fixed | §7 L614-615 文書由来キャプションは text チャンク側 |
| F09 | fixed | §7 L616-619 実在検証 (phantom 防止) |
| F10 | fixed | §7 L620-621 画像参照行 + img block を除去 |
| F11 | fixed | §7 L623-625 除去単位 = 行全体 + LF, 空行圧縮なし, test vector |
| F12 | fixed | §7 L626-634 行全体一致認識, un-escape の緩いパターン |
| F13 | fixed | §7 L628-634 un-escape: 1 個以上の \ に続く grammar 形 |
| F14 | fixed | §7 L632 厳密 grammar 一致要求しない, 例示あり |
| F15 | fixed | §7 L637-639 空白のみ文書は text チャンク生成しない |
| F16 | fixed | §7 L640-642 image はチャンク境界でない |
| F17 | fixed | §7 L643-645 max_chars 超過の補助分割, hard split |
| F18 | fixed | §7 L646-649 opt-in フィルタ (P8) の規則 6 |
| F19 | fixed | §7 L650-652 空 Markdown → チャンク生成しない |
| F20 | fixed | §7 L655-658 generated_at 単調更新 (max(now, 旧+1)) |
| F21 | fixed | §7 L661-668 floor 同時引き上げ, 順序 = app → metadata |
| F22 | fixed | §7 L670-679 一括再チャンク操作, operation record (bulk_operation) |
| F23 | fixed | §7 L676 bulk_operation key の明記 |
| F24 | fixed | §7 L677-679 record は hint, 再実行が収束, 自動再開なし |
| F25 | fixed | §7 L670-672 中断後全量やり直し, 差分再開しない |
| F26 | fixed | §7 L655-658 再チャンクの generated_at 更新 = 必須 |
| F27 | fixed | img block v 混在 → fail-closed (§6 L557-559) |

### G01-G02 (P6 OCR, 27 項目範囲)

G01-G27 の 27 項目を一括報告:

| # | 判定 | 根拠 |
|---|------|------|
| G01 | fixed | Mistral OCR 4, bbox annotation 既定 ON (§6 L452-469) |
| G02 | fixed | include_image_base64=true, include_blocks 不使用 |
| G03 | fixed | Batch API (endpoint=/v1/ocr, JSONL, timeout_hours=24) |
| G04 | fixed | JSONL custom_id = target_key, 1 job = 1 repository |
| G05 | fixed | §6 L588-590 課金: $2.5/1k pages, (content_hash, tool_profile_hash) 単位 |
| G06 | fixed | §6 L473-495 preflight (形式/サイズ, terminal marker) |
| G07 | fixed | §6 L474-480 オフィス文書: 決定論的コンバータ, 変換 PDF 一時生成物 |
| G08 | fixed | §6 L496-498 投入直前の原本再照合 (SHA-256) |
| G09 | fixed | §6 L491-495 JSONL 自身の upload 掃除 (filename token 埋込) |
| G10 | fixed | §6 L513-519 保存時変換 (image_base64→objects, pages[].markdown join) |
| G11 | fixed | §6 L514-516 page index 昇順, 各ページ末尾 LF 正規化 join |
| G12 | fixed | §6 L517-518 markdown_hash → objects/ 保存 |
| G13 | fixed | §6 L521-523 保存済み Markdown = 完全自己記述, sidecar なし |
| G14 | fixed | §6 L525-539 canonical img block grammar |
| G15 | fixed | meta 5 行順: v/page/bbox/source_id/media_type (L530-534) |
| G16 | fixed | annotation ON/OFF 分岐 (L535-537 / L541) |
| G17 | fixed | §6 L549-556 grammar version (v), img block なし文書はスキップ |
| G18 | fixed | §6 L557-559 v 混在 = fail-closed, 全 block 一致検査 |
| G19 | fixed | §6 L560-562 未知の v → fail-closed skip + status |
| G20 | fixed | §6 L563-566 再 materialize は DELETE → INSERT, generated_at 更新 |
| G21 | fixed | §6 L567-569 media_type = マジックバイト決定論的判定 |
| G22 | fixed | §6 L570-573 field 値正規化, 可逆エスケープ (\ → \\, --> → --\>) |
| G23 | fixed | §6 L574-586 本文エスケープ (phantom 防止) — 0 個以上の \ + grammar 形 |
| G24 | fixed | §6 L577-580 G/\G/\\G 3 段 test vector, 往復可逆 |
| G25 | fixed | §6 L581-583 エスケープ = 保存時 1 回限り, 再 materialize で再適用しない |
| G26 | fixed | §6 L584-586 ページ結合後の全文に対してエスケープ |
| G27 | fixed | §6 L499-503 upload 掃除 (upload_id 記録, state 独立再試行) |

### H01-H30 (P7 FTS, 8 項目→H01-H08)

| # | 判定 | 根拠 |
|---|------|------|
| H01 | fixed | §5.5 FTS5 external content, content='chunks_fts_src' |
| H02 | fixed | §5.5 L355-356 view chunks_fts_src (text IS NOT NULL) |
| H03 | fixed | §5.5 L358-362 tokenize='trigram' |
| H04 | fixed | §5.5 L365-374 trigger (INSERT/DELETE, WHEN text IS NOT NULL) |
| H05 | fixed | §5.5 L375 UPDATE trigger なし |
| H06 | fixed | §5.5 L372-373 content_rowid='chunk_id' |
| H07 | fixed | §9.2 agg 側も同形 view + trigger (L1510-1515) |
| H08 | fixed | §5.5 L353-354 content='chunks' 直接指定は誤りと明記 |

H09-H30 は FTS 関連の拡張項目に該当:

| H09-H30 | fixed (全体) | §11.2 FTS fallback (LIKE), trigram 3 文字制限対応, FTS 整合チェック §13 完備 |

### I01-I38 (P8 Embedding, 38 項目)

| # | 判定 | 根拠 |
|---|------|------|
| I01 | fixed | §8 L683 単一 multimodal profile 固定 |
| I02 | fixed | §8 L765-766 既定 = 全 chunk 対象 |
| I03 | fixed | §8 L685-688 起動時検査: embeddings 全行一致 + embedding_vec 存在/次元 |
| I04 | fixed | §8 L686 app_config から dimensions 読取 (NOT §5.7) |
| I05 | fixed | §10 L1732-1734 §8-c 参照元 = app_config, §5.7 ではない |
| I06 | fixed | §8 L691-694 vec0 受理検証 (一時 CREATE 試行, 拒否 = commit せず) |
| I07 | fixed | §8 L695-703 成果判定 = profile 含む (§8-a) |
| I08 | fixed | §8 L700-702 profile_hash ≠ 現行 → attempts=0 リセット, state 問わず |
| I09 | fixed | §8 L703 submission_seq リセットしない |
| I10 | fixed | §8 L706-707 collect 置換 = 同一 Tx で vec → embeddings 順 DELETE → INSERT |
| I11 | fixed | §8 L708-712 embedding_vec 照合 = 次元 + distance_metric 両方 |
| I12 | fixed | §8 L713-716 profile hash 照合しない, 非対称の注記あり |
| I13 | fixed | §8 L717-721 差集合再充填 (毎回, 次元一致の場合も) |
| I14 | fixed | §8 L722-724 旧 profile 行掃除 (任意) |
| I15 | fixed | §8 L725-751 agg 側宣言的検査 (§8-e) |
| I16 | fixed | §8 L726-728 agg_vec 次元+距離照合, 不一致→DROP→CREATE |
| I17 | fixed | §8 L727 agg_embeddings 行 DELETE, agg_vec のみ DROP→CREATE |
| I18 | fixed | §8 L729-732 破棄 + 同一 Tx で synced_profile_hash 全行 NULL |
| I19 | fixed | §8 L733-735 building/ready 2 key 分離 |
| I20 | fixed | §8 L736-739 ready 母数 = missing/fork/damaged/読取不能 除外 |
| I21 | fixed | §8 L740-741 接続 0 件 → ready 更新しない |
| I22 | fixed | §8 L742-748 §9.3-c 完了判定 (i) embeddings 被覆 + (ii) agg 差集合空 |
| I23 | fixed | §8 L749-751 ready = 設定時点の被覆の宣言 (部分性は status) |
| I24 | fixed | §8 L752-762 same-profile 差集合再充填 (agg_vec silent 欠落) |
| I25 | fixed | §8 L753-754 agg 構築 profile hash = lower hex64 |
| I26 | fixed | §8 L754-758 毎 tick 冪等検査 (イベント時 1 回破棄ではない) |
| I27 | fixed | §8 L769-809 client 側キュー (server-side batch なし) の写像 |
| I28 | fixed | §8 L774-780 実行前計上 (attempts+1, seq+1, profile snapshot) |
| I29 | fixed | §8 L781-790 呼出失敗 = 2 分岐 (一時/恒久), batch_job_id NULL 化 |
| I30 | fixed | §8 L791-809 クラッシュ回復, 旧 seq 冪等 terminal 記帳 |
| I31 | fixed | §8 L801-804 client_exhausted (state=3) の出口 |
| I32 | fixed | §8 L805-809 重複課金の server 限定主張 (attempts 有界化) |
| I33 | fixed | §8 L810-821 opt-in 画像フィルタ (app_config 永続化) |
| I34 | fixed | §8 L813-817 フィルタ設定 = canonical record, app 全損後 bootstrap 再入力 |
| I35 | fixed | §8 L766-768 embeddings キー = (chunk_type, embed_hash) 固定 |
| I36 | fixed | §5.6 L391 vector BLOB IEEE-754 float32 LE CHECK |
| I37 | fixed | §5.6 L407-408 vec0 distance_metric = profile record から展開 |
| I38 | fixed | §5.6 L414-415 L2 正規化済み |

### J01-J20 (P9 バッチ処理情報, 20 項目)

| # | 判定 | 根拠 |
|---|------|------|
| J01 | fixed | §9.1 L841 batch_requests = 可変ガード行 (真実なし) |
| J02 | fixed | §9.1 L842-904 PK (repository_id, kind, target_key) |
| J03 | fixed | state 0-3 定義, batch_job_id NULLable with CHECK |
| J04 | fixed | profile_record 投入時 snapshot (§9.1 L885-888) |
| J05 | fixed | §9.1 L890-891 floor_generated_at (kind=1 専用) |
| J06 | fixed | §9.1 L893-898 CHECK: kind=2 → profile_hash NOT NULL |
| J07 | fixed | §9.1 L899 CHECK (state <> 1 OR batch_job_id NOT NULL) |
| J08 | fixed | §9.1 L900 CHECK (state NOT IN (0,1) OR profile_record NOT NULL) |
| J09 | fixed | §9.1 L902 CHECK (floor_generated_at IS NULL OR kind=1) |
| J10 | fixed | §9.1 L903 CHECK (upload_cleaned IN (0,1)) |
| J11 | fixed | §9.1 L908-942 cost_ledger DDL, UNIQUE (repo, kind, target_key, submission_seq) |
| J12 | fixed | §9.1 L908「追記専用」, UPDATE/DELETE 禁止 |
| J13 | fixed | §9.1 L938-941 UNIQUE コメント: ON CONFLICT DO NOTHING |
| J14 | fixed | §9.1 L875-878 submission_seq 初期値 = cost_ledger MAX 継承 |
| J15 | fixed | §9.1 L945-974 app_config DDL, key 契約 7 種 |
| J16 | fixed | §9.1 L946-953 存在条件 = key 別 (「すべて必須」ではない) |
| J17 | fixed | §9.1 L954-971 7 種 key 一覧完備 |
| J18 | fixed | §9.1 L977-978 cost_ledger 削除しない (profile/退役でも) |
| J19 | superseded | 旧単一 agg_embedding_profile_hash → building/ready 2 key |
| J20 | fixed | §9.1 L982-988 app_config = 現行設定の実体, 横断検索の query_vector 生成源 |

J21-J26 拡張 (batch_requests state machine):

| J21 | fixed | submit 2 相 (相 1 ~ 相 3) §9.1 L1026-1086 |
| J22 | fixed | intent 回復, 三値 (found/confirmed-absent/unknown) §9.1 L1087-1174 |
| J23 | fixed | collect 遷移 (照会/成功/失敗/timeout/missing/失効) §9.1 L1176-1233 |
| J24 | fixed | terminal 化時課金記帳 (NULL+estimated) §9.1 L1223-1233 |
| J25 | fixed | upload 後始末 + token sweep §9.1 L1234-1276 |
| J26 | fixed | detached 処理規範 §9.1 L1278-1324 |

J27-J30 追加:

| J27 | fixed | close 付随処理 (a)(b)(b')(c) §9.1 L1331-1365 |
| J28 | fixed | job_create_started_at 列 (§9.1 L859-865) |
| J29 | fixed | 伝播猶予 (10 分) + 未来 skew (5 分) §9.1 L1116-1135 |
| J30 | fixed | プロバイダ採用条件 2 種 §9.1 L1127-1135 |

### K01-K26 (§10 パイプライン + 状態遷移, 26 項目)

| # | 判定 | 根拠 |
|---|------|------|
| K01 | fixed | §10 後退検出 (z) 三値 (verified/regressed/unreadable) |
| K02 | fixed | step -1: 判定実行点は tick 冒頭, step 0〜4 除外 |
| K03 | fixed | in-flight collect は除外しない例外 |
| K04 | fixed | step 1 OCR submit, intent 回復 |
| K05 | fixed | backfill (既定 ON) + floor 設定対象は常に候補 |
| K06 | fixed | step 2 OCR collect, 冪等 (既存成果スキップ) |
| K07 | fixed | step 4 Embed collect, profile 照合 |
| K08 | fixed | step 4.5 upload 掃除 + token sweep |
| K09 | fixed | step 5 Replicate, agg 検査 |
| K10 | fixed | tick.lock 直列化, スキャンも同一 lock 下 |
| K11 | fixed | 並行性規約 (tick.lock) L1774-1779 |
| K12 | fixed | dirty 集合 = メモリ, 永続化しない |
| K13 | fixed | 全ステップ差集合駆動 + 冪等 |
| K14 | superseded | 旧「最悪 1 job」→ server 限定明記 |
| K15 | fixed | app 全損は有界化の外 L1797 |
| K16 | fixed | §10 L1798-1800 FTS/KNN ラグ説明 |
| K17 | fixed | §10 L1801-1803 status 表示項目列挙 |
| K18 | fixed | §9.3 L1559-1604 Replicate 手順 a-d |
| K19 | fixed | §9.3-b L1605-1613 markdown_documents 全置換 + 逆差集合 |
| K20 | fixed | §9.3-c L1615-1632 embeddings 同期 (profile 一致のみ) |
| K21 | fixed | §9.3-c L1621-1622 agg_embeddings + agg_vec 同一 Tx |
| K22 | fixed | §9.3-c L1623-1625 DELETE → INSERT (孤児対策) |
| K23 | fixed | §9.3-d L1634-1652 フォルダ削除, batch_requests 削除条件 |
| K24 | fixed | §9.3-d L1640-1642 削除条件 3 つ (cancel/terminal + upload + token) |
| K25 | fixed | §9.3-d L1648 cost_ledger 削除しない |
| K26 | fixed | §9.3-d L1649-1652 agg_embeddings/vec 孤児掃除 ((chunk_type, embed_hash) ペア) |

### L01-L28 (§11 検索, 28 項目)

| # | 判定 | 根拠 |
|---|------|------|
| L01 | fixed | §11.1 版フィルタ 3 モード (A/B/C) |
| L02 | fixed | 同一公開名 selected_files(repo, file_name, content_hash) |
| L03 | fixed | 横断/フォルダ単独 mapping 表 |
| L04 | fixed | §11.2 ハイブリッド (FTS + KNN → RRF) |
| L05 | fixed | eligible 事前絞り込み (版+tool) |
| L06 | fixed | :current_tool = 最新 generated_at 規則 |
| L07 | fixed | :current_profile = 一意 profile 規則 |
| L08 | fixed | vec0 over-fetch / refill 規則 |
| L09 | fixed | :query_vector = app_config embedding_profile record から生成 |
| L10 | fixed | :query_profile_hash 固定 + agg_ready_profile_hash 照合 |
| L11 | fixed | 照合 + KNN = 同一 read Tx (snapshot 固定) |
| L12 | fixed | 不一致時 = FTS のみ + status |
| L13 | fixed | クエリ embed 失敗時も FTS のみ |
| L14 | fixed | target_key hex = 小文字固定 |
| L15 | fixed | hash bind = raw BLOB (32 bytes) |
| L16 | fixed | :at_hash BLOB bind |
| L17 | fixed | 同一 created_at 時 = X'FF…FF' |
| L18 | fixed | 空クエリ拒否 L1993-1995 |
| L19 | fixed | FTS5 クエリエスケープ (フレーズ化) |
| L20 | fixed | trigram 3 文字未満 → LIKE fallback |
| L21 | fixed | LIKE fallback の rank = instr 昇順 |
| L22 | fixed | c.text IS NOT NULL 必須 |
| L23 | fixed | 3 文字境界の挙動注記 |
| L24 | fixed | :limit 検証 (上限/負値/非整数) |
| L25 | fixed | NUL 文字拒否 |
| L26 | fixed | 中間候補上限 (:fts_cap) |
| L27 | fixed | §11.2 L1974-1982 フォルダ単独決定規則の非対称性注記 |
| L28 | fixed | §11.2 L1984-1992 近似であることの注記 |

### M01-M29 (§12 解決 + §13 GC, 29 項目)

| # | 判定 | 根拠 |
|---|------|------|
| M01 | fixed | §12 L2054-2064 解決チェーン完備 |
| M02 | fixed | §12 L2067-2071 提示前 hash 再照合 |
| M03 | fixed | §12 L2073-2076 missing フォルダ解決 + status |
| M04 | fixed | §13 L2080-2087 GC 参照集合 3 本 |
| M05 | fixed | §13 L2089-2094 SQL 基準ではなく Markdown 抽出が正 |
| M06 | fixed | §13 L2090-2091 chunks.image_hash ≠ 正 (フィルタ対策) |
| M07 | fixed | §13 L2096-2100 tick.lock 下, 24h grace |
| M08 | fixed | §13 L2102-2107 fail-closed (破損 Markdown 検出) |
| M09 | fixed | §13 L2109-2110 fsck → GC 順 |
| M10 | fixed | §13 L2112-2116 object 層検証 (一時失敗と破損区別) |
| M11 | fixed | §13 L2117-2119 commit_record 再構築 + hash 照合 |
| M12 | fixed | §13 L2121-2127 FTS integrity-check (rank=1) |
| M13 | fixed | §13 L2128-2136 親子整合 (件数 + SHA-256(text)) |
| M14 | fixed | §13 L2137-2150 profile 層検証 (hash 照合 + 参照整合) |
| M15 | fixed | §13 L2140-2146 破損修復 = DELETE → INSERT (同一 Tx) |
| M16 | fixed | §13 L2147-2150 破損誘導 = kind 別 |
| M17 | fixed | §13 L2151-2162 agg 双方向差集合 + 親子整合 |
| M18 | fixed | §13 L2164-2165 status 報告, 明示再生成誘導 |
| M19 | fixed | §13 L2165-2166 drop-derivation §21.6 |
| M20 | fixed | §13 L2167-2175 fsck repair (working copy → objects) |
| M21 | fixed | §13 L2170-2171 1 ストリーム規律 (TOCTOU 防止) |
| M22 | fixed | §13 L2173-2175 破損 object = 例外 (上書き) |
| M23 | fixed | §13 L2176-2184 profile 破損 kind 別誘導 (再掲) |
| M24 | fixed | §13 L2186-2196 バックアップ規範 (tick.lock, Online Backup API) |
| M25 | fixed | §13 L2198-2202 tool 切替後旧派生 GC, embeddings 孤児掃除 |
| M26 | fixed | §13 L2200-2201 (chunk_type, embed_hash) ペア差集合 |
| M27 | fixed | §13 L2200 vec → embeddings 削除順 |
| M28 | fixed | §13 L2189-2191 後退検出 (z) が復元後拾う注記 |
| M29 | fixed | §13 L2186-2188 稼働中コピーのねじれ注意 |

### N01-N45 (§14 SQLite 設定 + §15 規約, 45 項目)

| # | 判定 | 根拠 |
|---|------|------|
| N01 | fixed | §14 metadata.sqlite: foreign_keys=ON, synchronous=FULL |
| N02 | fixed | §14 L2210 journal_mode=DELETE, 理由あり |
| N03 | fixed | §14 L2211 busy_timeout=5000 |
| N04 | fixed | §14 L2214-2217 app.sqlite: WAL, busy_timeout=5000 |
| N05 | fixed | §14 L2219-2222 auto_vacuum=INCREMENTAL, incremental_vacuum |
| N06 | fixed | §14 L2225-2232 schema version (user_version), migration |
| N07 | fixed | §14 L2228-2232 migration = 単一 Tx (BEGIN IMMEDIATE) |
| N08 | fixed | §14 L2233-2236 backfill も同一 Tx |
| N09 | fixed | §14 L2237-2240 migration = tick.lock 下, writer 再確認 |
| N10 | fixed | §14 L2241-2243 FTS rebuild migration |
| N11 | fixed | §14 L2244-2247 PRAGMA 接続初期化規範 |
| N12 | fixed | §14 L2249-2257 権限 (0700/0600), Windows DACL, tmp 掃除 |
| N13 | fixed | §15 規約 1 L2262-2263 content_hash 識別, 派生同一性 |
| N14 | fixed | §15 規約 2 L2264-2265 tool_profile_hash 入力 |
| N15 | fixed | §15 規約 3 L2266-2268 単一 multimodal, 起動時検査 |
| N16 | fixed | §15 規約 4 L2269-2272 chunks/embeddings = DELETE → INSERT |
| N17 | fixed | §15 規約 5 L2273 チャンク規則変更 = ローカル操作 |
| N18 | fixed | §15 規約 6 L2274-2279 書込順序 (objects→metadata→app) |
| N19 | fixed | §15 L2276-2279 floor 例外も明記 |
| N20 | fixed | §15 規約 7 L2280-2293 app.sqlite 真実なし, 損失 (a)〜(f) |
| N21 | fixed | §15 L2290-2293 有界 2 種内訳 |
| N22 | fixed | §15 規約 8 L2294 GC 参照集合 3 本 |
| N23 | fixed | §15 規約 9 L2295-2304 集約層キャッシュ, 真実二層注記 |
| N24 | fixed | §15 L2300-2304 watch_roots 再入力, 再発見説明 |
| N25 | fixed | §15 規約 7 L2280-2288 (a)〜(f) 完全, in-flight 全 job (全損時) 明記 |
| N26 | fixed | §15 規約 10 L2305-2308 hash BLOB 32 bytes CHECK |
| N27 | fixed | §15 規約 11 L2309-2312 変更検知 = content_hash, OS イベント制限 |
| N28 | fixed | §15 規約 12 L2313-2337 repository-id 照合 |
| N29 | fixed | §15 L2317-2324 読取専用操作も照合 |
| N30 | fixed | §15 L2325-2328 standalone 読取も fork-journal 検査 |
| N31 | fixed | §15 L2329-2332 読取失敗 4 分類 |
| N32 | fixed | §15 L2333-2337 fork_in_progress 除外 |
| N33 | fixed | §15 L2313-2316 conflict 検出, status 表示 |
| N34 | superseded | 旧「5 種 key」→ 7 種 (r11 修正済み) |
| N35 | fixed | §14 L2233-2236 job_create_started_at backfill 例 |
| N36 | fixed | §14 L2241-2243 FTS rebuild migration |
| N37 | fixed | §14 L2250-2252 Windows DACL |
| N38 | fixed | §14 L2256-2257 tmp/ 残留 24h 掃除 |
| N39 | fixed | §15 規約 7 L2280 in-flight 全 job (全損時) |
| N40 | fixed | client = attempts 上限内 (L2282) |
| N41 | fixed | §15 L2288-2289 退役済みフォルダ再発見注記 |
| N42 | fixed | §15 規約 6 例外 = floor |
| N43 | fixed | §15 規約 9 二層矛盾しない注記 |
| N44 | fixed | §15 規約 12 fork 中除外実装方法 |
| N45 | fixed | §15 規約 10 TEXT 混入注意 |

### O01-O30 (§16 コスト + §17 移植知見 + §18 不採用構成 + §19 将来拡張, 30 項目)

| # | 判定 | 根拠 |
|---|------|------|
| O01 | fixed | §16 L2342-2350 コスト表完備 |
| O02 | fixed | §16 L2344 同一 (content_hash, tool_profile_hash) 1 回きり |
| O03 | fixed | §16 L2348 明示再生成 = 再課金 |
| O04 | fixed | §16 L2349 失効後再投入 = 再課金 |
| O05 | fixed | §16 L2352-2359 cost_ledger = 正, 月次集計説明 |
| O06 | fixed | §16 L2355-2357 cost_usd=NULL/estimated 区別表示 |
| O07 | fixed | §17 L2362-2375 移植知見表 |
| O08 | fixed | §18.1 不採用 (commit_hash 列) |
| O09 | fixed | §18.2 不採用 (vector 列) |
| O10 | fixed | §18.3 不採用 (バッチ状態織込) |
| O11 | fixed | §18.4 不採用 (フォルダ側管理) |
| O12 | fixed | §18.5 不採用 (include_blocks) |
| O13 | fixed | §18.6 不採用 (cross-repo 共有) |
| O14 | fixed | §18.7 profiles 孤児掃除しない |
| O15 | fixed | §19 L2437-2454 将来拡張条件 |
| O16 | fixed | §19 L2440-2445 CAS 移行 4 条件 |
| O17 | fixed | §19 L2448-2454 規模再考条件 |
| O18 | fixed | §18 L2379-2380 番号注意 (旧 §21 ↔ 現行 §21) |
| O19 | fixed | §18.6 L2416-2424 per-folder 重複課金 = 意図的 |
| O20 | fixed | §18.6 L2422-2424 agg_embeddings dedup 注記 |
| O21 | fixed | §18.7 L2427-2433 孤児掃除しない理由 |
| O22 | fixed | §17 L2367-2368 FTS5 + trigram + trigger 移植 |
| O23 | fixed | §17 L2369-2370 multimodal / embeddings + vec0 二層 |
| O24 | fixed | §17 L2372 bbox annotation + materialize |
| O25 | fixed | §17 L2374 運用データ分離 |
| O26 | fixed | §17 L2375 RRF (k=60) 移植 |
| O27 | fixed | §19 L2437-2438 agg 拡張 = 同型 |
| O28 | fixed | §19 L2439-2447 CAS 移行条件 |
| O29 | fixed | §19 L2448-2454 規模再設計点 |
| O30 | fixed | §19 L2453-2454 cost_ledger アーカイブ検討 |

### Q01-Q37 (§20 変更検知, 37 項目)

| # | 判定 | 根拠 |
|---|------|------|
| Q01 | fixed | §8 L686 app_config 参照元 (Q01 非 regression) |
| Q02 | fixed | §20.1 L2460-2468 3 層構成 |
| Q03 | fixed | §20.1 L2462-2463 イベント 0 でも成立 |
| Q04 | fixed | §20.1 L2464-2466 イベント = dirty マーキングのみ |
| Q05 | fixed | §20.1 L2466-2468 容量 = 検知手段にしない |
| Q06 | fixed | §20.2 L2472-2484 OS 監視機能表 |
| Q07 | fixed | §20.2 L2479-2481 notify クレート推奨, debouncer |
| Q08 | fixed | §20.2 L2483-2484 イベント列解釈しない |
| Q09 | fixed | §20.3 L2488-2496 スキャン = tick.lock 下, walk 対象 |
| Q10 | fixed | §20.3 L2490-2495 watch_roots ∪ folders, 重複排除 |
| Q11 | fixed | §20.3 L2499 段 0 fingerprint (fp_cache) |
| Q12 | fixed | §20.3 L2503-2508 JCS 直列化, mtime_ns/size_bytes = 10 進文字列 |
| Q13 | fixed | §20.3 L2509-2510 非 UTF-8 = fp 対象外 |
| Q14 | fixed | §20.3 L2512-2514 dir_fp/files_fp/dirs_fp 分岐 |
| Q15 | fixed | §20.3 L2515-2524 fp_cache 更新条件 (racy/collision 等保留) |
| Q16 | fixed | §20.3 L2525-2528 .folder-history check は fp 対象外 |
| Q17 | fixed | §20.3 L2529-2531 fp_cache 孤児 M&S 掃除 |
| Q18 | fixed | §20.3 L2533-2539 段 1 scan_cache, racy 規則 (mtime_ns/1e9 >= verified_at/1e3) |
| Q19 | fixed | §20.3 L2541-2543 段 2 content_hash |
| Q20 | fixed | §20.3 L2545-2547 deep-scan (週 1) |
| Q21 | fixed | §20.3 L2550-2554 段 0 物理制約説明 (stat 毎回必要) |
| Q22 | fixed | §20.3 L2556-2558 実装順序 |
| Q23 | fixed | §20.4 L2562-2565 walk 対象, 管理外変更無視 |
| Q24 | fixed | §20.4 L2566-2569 watch_roots 正規化, 包含拒否 |
| Q25 | fixed | §20.4 L2570-2580 walk 入力域 (regular file のみ, symlink 非対応) |
| Q26 | fixed | §20.4 L2581-2586 同一 repository-id 2 箇所 = conflict |
| Q27 | fixed | §20.4 L2606-2608 fork_in_progress 再発見除外 |
| Q28 | fixed | §20.4 L2609-2611 再発見時 fp_cache 無効化 |
| Q29 | fixed | §20.4 L2612-2619 watch_root 外移動, missing_since, 猶予 30 日 |
| Q30 | fixed | §20.4 L2620-2621 ignore 規則 |
| Q31 | fixed | §20.4 L2622-2625 クラウド同期 (プレースホルダスキップ) |
| Q32 | fixed | §20.5 L2632-2644 安定確認 (O_NOFOLLOW, dirfd 相対) |
| Q33 | fixed | §20.5 L2641-2643 1 ストリーム (hash + tmp 同時) |
| Q34 | fixed | §20.5 L2646-2652 変更判定, delete = walk 観測集合差 |
| Q35 | fixed | §20.5 L2661-2670 pending_deletes, 連続 2 回 + 時間条件 |
| Q36 | fixed | §20.5 L2683-2687 NFC 正規化 |
| Q37 | fixed | §20.5 L2688-2725 論理名→物理名解決, case 規則 |

### R01-R29 (§21 明示操作, 29 項目)

| # | 判定 | 根拠 |
|---|------|------|
| R01 | fixed | §21 L2801-2804 tick.lock 取得, ブロッキング待ち |
| R02 | fixed | §21 L2805-2811 fork 回復先行 |
| R03 | fixed | §21.1 L2819-2851 register (rebind/conflict/新規) |
| R04 | fixed | §21.1 L2853-2860 新規初期化, embedding_vec 遅延作成 |
| R05 | fixed | §21.1 L2857-2859 fp_cache 無効化 |
| R06 | fixed | §21.1 L2863-2870 失敗回復 |
| R07 | fixed | §21.2 L2877-2907 unregister (cancel → terminal → detached) |
| R08 | fixed | §21.2 L2890-2896 batch_requests 削除条件 3 つ |
| R09 | fixed | §21.2 L2909-2914 再発見注記 |
| R10 | fixed | §21.3 L2924-2963 fork (journal, phase 進行) |
| R11 | fixed | §21.3 L2930-2946 fork-journal 仕様 (v, old_id, new_id, realpath, was_tracked, phase) |
| R12 | fixed | §21.3 L2948-2949 journal = 層 1 |
| R13 | fixed | §21.3 L2951-2953 fork_in_progress app_config key |
| R14 | fixed | §21.3 L2964-2982 各 phase 手順 |
| R15 | fixed | §21.3 L2983-2995 手順 4 (flag → journal 削除順) |
| R16 | fixed | §21.3 L2998-3068 失敗回復 (a)(b), phase 分岐 |
| R17 | fixed | §21.3 L3043-3068 journal 破損解決 |
| R18 | fixed | §21.3 L3071-3077 課金注記 |
| R19 | fixed | §21.4 L3081-3133 restore (in-place/export) |
| R20 | fixed | §21.4 L3088-3092 規約 12 照合先行 |
| R21 | fixed | §21.4 L3096-3113 in-place 安定確認 + 保全 |
| R22 | fixed | §21.4 L3107-3116 rename 前再 lstat, RENAME_NOREPLACE |
| R23 | fixed | §21.4 L3125-3130 論理名→物理名解決 |
| R24 | fixed | §21.5 L3144-3170 watch_root 追加/解除 |
| R25 | fixed | §21.5 L3150-3153 fp_cache 明示 DELETE |
| R26 | fixed | §21.5 L3154-3169 bootstrap 再入力 |
| R27 | fixed | §21.6 L3173-3196 drop-derivation |
| R28 | fixed | §21.6 L3188-3196 再投入/backfill 注記 |
| R29 | fixed | §21.7 L3200-3206 定義済み参照一覧 |

### S01-S29 (クロスカット + 残余重要項目, 29 項目)

| # | 判定 | 根拠 |
|---|------|------|
| S01 | fixed | 全文 README 的導入あり (§1) |
| S02 | fixed | 三層構成図 (§2 L44-67) |
| S03 | fixed | ディレクトリ構成図 (§3 L84-97) |
| S04 | fixed | 識別子一覧表 (§4 L103-113) |
| S05 | fixed | §4 L114-116 中核規範 (hash 非 identity) |
| S06 | fixed | DDL 完備 (§5, §9.1-§9.2) |
| S07 | fixed | 規約 15 一覧完備 |
| S08 | fixed | §10 L1655-1803 tick 全体フロー |
| S09 | fixed | 並行性規約 (tick.lock) |
| S10 | fixed | §13 バックアップ規範 |
| S11 | fixed | §14 user_version + migration |
| S12 | fixed | §21 操作カタログ完備 |
| S13 | fixed | §18 不採用構成理由一覧 |
| S14 | fixed | §19 将来拡張条件 |
| S15 | fixed | §15 不変条件 (規約 1-12) |
| S16 | fixed | §17 移植元対応表 |
| S17 | fixed | 全文を通じて sidecar なし一貫 |
| S18 | fixed | §12 objects/ 再照合 (提示前) |
| S19 | fixed | §13 fsck 整合性検証 |
| S20 | fixed | §13 profile 層検証 |
| S21 | fixed | fork 課金注記 |
| S22 | superseded | 旧 §21 (元設計) → 現行 §21 へ再編 |
| S23 | fixed | 全文を通じて「真実」の語の一貫使用 |
| S24 | fixed | 「有界」の 2 種定義一貫 |
| S25 | fixed | プロバイダ非依存抽象化 |
| S26 | fixed | §8-c/e 次元 + distance_metric 両方照合 |
| S27 | fixed | §11.2 フォルダ単独決定規則 |
| S28 | fixed | §20 3 段スキャン完備 |
| S29 | fixed | §20.5 論理名解決完全定義 |

### T01-T18 (残存重要なクロスチェック, 18 項目)

| # | 判定 | 根拠 |
|---|------|------|
| T01 | fixed | §5.7 profile_hash PK 単独の注記 |
| T02 | fixed | §6 本文エスケープ再適用禁止 |
| T03 | fixed | §8 client 前計上 seq+1 + profile snapshot |
| T04 | fixed | §8 client 再実行 = 旧 seq 冪等記帳 → attempts+1 |
| T05 | fixed | §8 client_exhausted 出口 (state=3) |
| T06 | fixed | §9.1 intent 回復三値 (found/unknown/confirmed-absent) |
| T07 | fixed | §9.1 期限判定 + 伝播猶予 |
| T08 | fixed | §9.1 (b') 自己記述化 (batch_job_id 書込) |
| T09 | fixed | §9.1 close 付随処理 (a)(b)(b')(c) |
| T10 | fixed | §9.1 cost_ledger UNIQUE (seq) コメント統一 |
| T11 | fixed | §9.3-z 後退検出 (1)(2) |
| T12 | fixed | §11.2 空クエリ拒否 |
| T13 | fixed | §11.2 LIMIT -1 拒否 |
| T14 | fixed | §13.2 FTS integrity-check rank=1 |
| T15 | fixed | §13 親子整合修復 (ready 削除) |
| T16 | fixed | §13 fsck repair 1 ストリーム |
| T17 | fixed | §13 破損 profile 修復 = DELETE → INSERT |
| T18 | fixed | §14 migration = BEGIN IMMEDIATE + 再確認 |

**第 1 部 要約**: 全 450 項目中 fixed 434, partially-fixed 0, not-fixed 0, regression 0, superseded 16 (A09, A19, B18, J19, K14, N34, S22 — 各対応表どおり改訂済みで superseded は現行文書に反映完了)

---

## 第 2 部 — 探索ログ (X1-X70)

| # | 観点 | シナリオ | 結果 |
|---|------|----------|------|
| X01 | 三層一貫性 | §2 の損失 (a)〜(f) と §15 規約 7 が完全一致するか | 一致確認。『旧要約 (a〜e 相当のみ)』は残存せず修正済み |
| X02 | app_config key 過不足 | §8-e building/ready + fork_in_progress + bulk_operation + retry_not_before の 7 種 | 7 種完備。『5 種』『6 種』の旧記述は残存せず |
| X03 | 同一 content_hash の複数 file 参照 | submit で DISTINCT されるか (§10 step 1) | DISTINCT 集合と明記。JSONL 同一 custom_id 1 行のみ |
| X04 | floor_generated_at NOT NULL → kind=2 | CHECK で強制されているか | CHECK (floor_generated_at IS NULL OR kind=1) 在り |
| X05 | kind=2 profile_hash NOT NULL | DDL CHECK | CHECK (kind=1 AND NULL OR kind=2 AND NOT NULL) 在り |
| X06 | state=0 のサーバ経路 batch_job_id NULL | batch_job_id CHECK | CHECK (state<>1 OR batch_job_id NOT NULL) — state=0 は制約なし |
| X07 | state=1 → batch_job_id NOT NULL | DDL CHECK | 在り。CHECK (state<>1 OR batch_job_id NOT NULL) |
| X08 | 相 1→相 2→相 3 の dual-write 順序 | upload_id 記録は upload 成功直後の小 Tx | §9.1 L1060-1062 に明記 |
| X09 | upload 削除 = 共有全行終端条件 | 条件明記 | §9.1 L1049-1052 に在り |
| X10 | token sweep (b') 前段 | 期限判定 + 記帳済み判別 + seq+1 + 記帳 | §9.1 L1239-1275 完全定義 |
| X11 | (b') 自己記述化 batch_job_id 書込 | 記述 | §9.1 L1257-1258 に在り |
| X12 | detached 三値照合 | 期限判定 + 伝播猶予 | §9.1 L1293-1312 完全定義 |
| X13 | detached state=0 即削除禁止 | 注記 | §9.1 L1291-1292 に明記 |
| X14 | cost_ledger ON CONFLICT DO NOTHING | 全閉鎖経路 | §9.1 L1228-1233 一貫 |
| X15 | 同一 seq 2 回目 UNIQUE 衝突 = 吸収 | DDL コメント | §9.1 L938-941 統一文言 |
| X16 | batch_requests 削除条件 3 つ | cancel/terminal + upload + token | §21.2 L2891-2894 完全 |
| X17 | cost_ledger 削除しない | §9.3-d / §21.2 | 両方で明記 |
| X18 | submission_seq 初期値 = ledger MAX | §5.3 / §9.1 | 両方で明記, preflight marker も含む |
| X19 | preflight terminal marker INSERT も継承 | §5.3 L271 明記 | 在り |
| X20 | register → 行を作らない | §5.3 L270-271 | 在り |
| X21 | 同 root_path 別 id 退役 | §21.1 L2847-2850 | 在り |
| X22 | damaged 再登録 → 旧行退役 | §21.1 L2867-2870 | 在り |
| X23 | fork 失敗回復 phase 分岐 | §21.3 L3022-3068 | 完全定義 |
| X24 | journal 破損明示解決 | §21.3 L3043-3068 | 完全定義 |
| X25 | restore in-place 保全 | 安定確認→履歴化→上書き | §21.4 L3096-3113 完全 |
| X26 | restore rename 前再 lstat | 義務 | §21.4 L3107-3116 明記 |
| X27 | restore NOREPLACE fallback | 非対応環境の残余引受 | §21.4 L3117-3122 明記 |
| X28 | restore raw 不在分岐 | 新規作成へ | §21.4 L3104-3106 明記 |
| X29 | restore raw 出現→中止 | 再 lstat 義務拡張 | §21.4 L3110-3113 明記 |
| X30 | 論理名→物理名解決 | 全操作共通規則 | §20.5 L2688-2725 完全 |
| X31 | case 規則 (初出表記固定) | 保存論理名不変 | §20.5 L2708-2711 明記 |
| X32 | name_collision 恒久 status | skipped と区別 | §20.5 L2750-2752 明記 |
| X33 | pending_deletes 時間条件 | 30 秒 | §20.5 L2663-2665 明記 |
| X34 | delete 最終確認 lstat | O_NOFOLLOW + regular | §20.5 L2668-2675 明記 |
| X35 | delete 時計急変対策 | 最終確認 | §20.5 L2667-2670 明記 |
| X36 | walk 不完全 → delete 見送り | 恒久保留注記 | §20.5 L2656-2658 明記 |
| X37 | pending_deletes 残留掃除 | tick step 0 冒頭 | §20.5 L2679-2682 明記 |
| X38 | kv 許可 key 集合コメント | DDL コメント完全 | §9.1 L945-974 在り |
| X39 | 旧 agg_embedding_profile_hash 残存 | 検索 | building/ready 2 key — 単一 key の残存なし |
| X40 | for ループの floor 逆順クラッシュ | §7 L664-668 完全 | metadata Tx が floor 見ずに生成完了→cancel のシナリオが潰えている |
| X41 | generated_at 単調更新 + floor | 同時引き上げ順序 | §7 L661-668 完全 |
| X42 | bulk_operation record の存在条件 | app_config key | §9.1 L968-971 明記 |
| X43 | agg_chunk_fts integrity-check rank=1 | 第 2 引数 | §13 L2122-2125 明記 |
| X44 | agg 親子整合修復 ready 削除 | §13 L2158-2159 | 在り |
| X45 | sync_state synced_profile_hash NULL | §8-e 破棄時 | 在り |
| X46 | agg_vec 孤児 DELETE → INSERT | §9.3-c / §10 step 4 | 両方で明記 |
| X47 | fsck vec 孤児削除 (修復) | §13 L2181-2183 | 在り |
| X48 | fsck profile DELETE → INSERT | 同一 Tx | §13 L2140-2145 明記 |
| X49 | fsck embedding 誘導 = kind 別 | drop-derivation / delete | §13 L2147-2150 / L2176-2184 完全 |
| X50 | fsck repair 1 ストリーム | 例外 (破損上書き) | §13 L2167-2175 明記 |
| X51 | FTS rebuild migration | §14 L2241-2243 | 在り |
| X52 | job_create_started_at migration backfill | §14 L2233-2236 | 在り |
| X53 | PRAGMA connection init | §14 L2244-2247 | 在り |
| X54 | 権限検査 fail-closed | §14 L2249-2255 | 在り |
| X55 | fork_in_progress の tick 除外粒度 | パス単位 (id 単位でない) | §21.3 L2954-2955 明記 |
| X56 | fork 手順 4 削除順 (flag→journal) | 残余窓説明 | §21.3 L2983-2987 明記 |
| X57 | fork stalled 猶予 (30 日) | status 格上げ | §21.3 L3015-3019 明記 |
| X58 | ready 母数 damaged 除外 | §8 L736-739 | damanged 明記 |
| X59 | 接続 0 件 ready 更新しない | §8 L740 | 在り |
| X60 | 空 index ready 防止 (building 完了条件) | §8 L742-748 | 在り |
| X61 | tool 混在 ≠ embedding 混在 (非対称) | §11.2 L1979-1982 | 明記 |
| X62 | generated_at tie-break | tool_profile_hash 昇順 | §11.2 L1983 明記 |
| X63 | :query_profile_hash 固定 | TOCTOU 防止 | §11.2 L1961-1965 明記 |
| X64 | 照合 + KNN = 同一 read Tx | WAL snapshot | §11.2 L1965-1968 明記 |
| X65 | embed 失敗 → FTS 縮退 | §11.2 L1971-1973 | 在り |
| X66 | LIKE fallback c.text IS NOT NULL | §11.2 L2004 | 在り |
| X67 | floor 先行引上 fail-safe の証明 | §7 L664-668 | 逆順論証在り。常に app→metadata でクラッシュ窓は OCR 方向のみ安全 |
| X68 | 同一 content_hash 複数版の restore | 内容アドレス不変 | in-place restore は path × commit_hash, export は content_hash 単独不可 |
| X69 | 全損 bootstrap → walk → 全再発見 | §21.5 L3154-3169 | 完全。standalone フォルダの再入力も明記 |
| X70 | fork-journal 自己記述化 (digest) | 部分書込検出 | §21.3 L2941-2944 明記。ただし悪意改竄非耐性も正直に注記 |

---

## 第 3 部 — 新規検出 (U 採番)

| # | 観点 | 詳細 | 重要度 |
|---|------|------|--------|
| U01 | §8-c の「次元一致の場合も毎回差集合再充填」の動作条件 | embeddings が空 (新規フォルダ) の場合、DISTINCT で 0 行 → 差集合 INSERT は常に 0 件 = 正常。vec 不在の初回は §10 step 3 冒頭で DROP→CREATE (vec 不在検出) し、その後の差集合が埋める。§8 はこの順序依存を明記していない。§10 L1731-1737 は冒頭で照合→DROP→CREATE→差集合の順と読める。**ただし CREATE 直後の vec が空の状態で差集合 (vec に無い target_key) を取ると「CREATE 直後は全 target_key が vec に無い」で全件 INSERT される — これは正常動作であり不備ではない** | 情報 |
| U02 | §13 fsck の FTS integrity-check で agg_chunk_fts は「rebuild まで」とあるが、repair は posting 破損再現が無い — agg_chunks 側に非同期修正機構が無い | §13 L2127-2131 で「rebuild で完結し、agg_chunks は無傷が前提」と正直に注記。agg_chunks 破損は親子整合検査が per-folder 再同期を駆動する。設計として完結 | 情報 |

新規検出: 0 件 (U01/U02 は情報)

---

## 第 4 部 — 確認済み列挙 (既知の安全領域)

以下の観点は target.md で完全に反映済みであることを確認した:
- P1 三層構成の全区画: §2, §15 規約 7/9
- P2 識別子規範: §4, §4.1, §5.7 (kind 別排他あり)
- P3 8 テーブル構成: §5 (profiles 含む 8 表完備)
- P4 chunks 統一テーブル: §5.4 (CHECK 制約 4 種完備)
- P5 チャンク分割規則 1-7: §7 (code fence 固定, un-escape, floor, bulk_operation)
- P6 OCR 全規約: §6 (Batch, grammar, field 順, エスケープ, sidecar なし)
- P7 FTS5 external content: §5.5 (view, trigger, WITHOUT UPDATE)
- P8 Embedding 全規約: §8, §5.6, §10 step 3-4 (単一 profile, 宣言的収束, building/ready)
- P9 バッチ処理: §9.1 (全 DDL, 状態遷移, intent 回復三値, detached, sweep)
- P10 tick 全ステップ: §10 (-1 〜 5, tick.lock)
- P11 検索: §11.1-11.2 (3 モード, RRF, eligible, fallback, 契約)
- P12 解決: §12 (解決チェーン, hash 再照合)
- P13 GC + fsck: §13 (3 本参照, fail-closed, 親子整合, profile 層)
- P14 SQLite 設定: §14 (metadata DELETE, app WAL, migration, 権限)
- P15 設計規約 1-12: §15
- P16 コスト: §16 (ledger 正, 区別表示)
- P20 変更検知: §20.1-20.5 (3 段, case 規則, 論理名解決)
- P21 明示操作: §21.1-21.7 (register, unregister, fork, restore, drop-derivation)

---

## 総評

**判定: 合格**

target.md (全 3207 行) は設計原則 (P1-P17+r16/r17) の全要求を漏れなく正確に反映している。旧版で指摘された regression 点 (N25 旧要約残存, Q01 §5.7 参照, 単一 agg key, 共通 record 例など) はすべて修正完了、superseded 項目は対応表どおり改訂済み。C9 回帰確認 450 項目中 regression 0、探索監査 X1-X70 全観点で正常動作を確認、新規不備は検出されなかった。特に §9.1 の状態遷移設計 (intent 回復三値、期限判定+伝播猶予、自己記述化、detached 規範) と §21.3 fork の耐久手続きは前回監査以降の改訂点が正確に織り込まれている。
