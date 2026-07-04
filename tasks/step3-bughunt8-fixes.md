# 探索型 4 エンジン監査 (第 8 ラウンド) の裁定 (2026-07-05、main = cfe55ce)

4 エンジン (Claude-Opus / Claude-Sonnet / GPT-5.5 / GPT-5.3-Codex-Spark) + オーケストレータ自身の
独立検証で探索。R6/R7 は別セッションで実施済み (bughunt6/7)、本ラウンドは HEAD=cfe55ce・**全 311 テスト green**
に対して実施。焦点は「新規 catalog.rs adapter identity / 時刻演算 / cost-ledger 会計 / NFC-NFD 正規化 /
DAG-Evidence 解決」。新規 **8 件** (6 major + 2 minor) + design 判断待ち 1 件。既知 (M/N/O/P/Q/R6/R7、
docs で Step4/Phase4+/v2+ 明記) との重複はゼロを確認。

**本ラウンドの鉱脈**: budget/cost-ledger 会計 (F1/F3/F5/F8) が最も濃く未監査、次いで embedding 応答検証 (F7)、
NFC/NFD 検索 (F2、**4 エンジン収束**)。catalog.rs の adapter identity 決定性は 2 エンジンが健全性を確認 (問題なし)。

エンジン別の主な貢献:
- **Claude-Opus**: F1 (ローカル baseline が cloud budget cap を消費、対照実験で再現)、F2/F4、F5
- **Claude-Sonnet**: F7 (embedding wrong-length を無検証 → 永久 KNN 除外、stub server で再現)、F8 (cost-ledger TOCTOU)、F2
- **GPT-5.5**: F3 (負値 usd → cap fail-open)、F4、F6 (online markdownize orphan)、F2
- **Spark / 自己検証**: F2 の完全再現・fix 確定、Spark 会計所見のトリアージ (2a/2d は反証/既知)

**却下**:
- Spark 1c (created_at tie-break 非決定) = 偽陽性。task_store.all() は BTreeMap(task_id 順)、Rust sort_by は stable。
- Spark 2a (再実行二重課金) = Opus が反証: content-addressed reuse で再課金されない。
- Spark 2d (cost-ledger 並行 append 破損) = 非問題。O_APPEND + 単一 write_all (M1(b))・append-only-delta。
  ※ ただし「破損」でなく「check-then-act の cap 超過」は別問題として F8 で採用。
- catalog.rs / identity.rs の tool_profile_hash drift = 健全 (2 エンジン確認)。PROFILE_FIELDS に adapter_id 非含有・
  dimensions 含有、version は非含有、profile() は env 非依存で決定的。builtin_prepare_profile の adapter_id 上書きは hash 非影響。

---

## 必須修正 F1-F5, F7-F8 (F6 は design 判断待ち、別途)

### F1 [major] オフラインのローカル baseline コストが device USD budget cap を消費し、有料 enrichment を silent に停止 (仕様違反)
発見: Claude-Opus / 完全再現: オーケストレータ

- **根本**: offline/deterministic markdownize が毎ファイル `deterministic_baseline usd=estimate_local_baseline_cost(size)`
  を device-global ledger に記帳 (`crates/kcs-cli/src/main.rs:5908-5915`)。`budget_remaining_for_adapter` の
  `device_spent = monthly_total(month, None)` (`main.rs:6508`) は**全 adapter_kind を合算**するため
  deterministic_baseline も cap に効く。docs/04:568「ローカル LLM 利用時は単価 0 として記録 (= cap に効かない)」に違反。
- **再現** (隔離 tmp): cap $0.0005、`index --offline --yes` (API 非送信) → ledger `deterministic_baseline usd=0.002`
  → `status.budget`: `device_spent_usd=0.002`, **`device_remaining_usd=-0.0015`** (無料作業で負・cap 超過)
  → 以降 paid markdownize/embedding が `paused`。対照 ($50 cap) では embedding 課金行が出る (= 送信される)。
- **期待 vs 実際**: 期待 = ローカル deterministic は単価 0 で cap 非計上。実際 = $0.01/MB を cap に計上し、無料の
  ローカル索引が有料 enrichment を silent に停止 + `status` の spent を水増し。
- **修正**: `main.rs:5913` を `usd: 0.0` にする (04 §5.4 準拠。記帳自体は残すなら device_spent 集計から
  deterministic_baseline を除外でも可だが、spec は「単価 0 として記録」なので usd:0.0 が素直)。

### F2 [major] NFC/NFD 正規化不一致で検索が silent false negative (NFD 内容が NFC クエリでヒットしない)
発見: **4 エンジン独立収束** (オーケストレータ / GPT-5.5 / Opus / Sonnet)

- **根本**: FTS 索引テキストは chunk 本文の生スライスで NFC 正規化しない (`crates/kcs-index/src/fts.rs:66` は NUL 除去のみ、
  正規化するのは `chunking.rs:80 slugify_heading` の見出し slug だけ)。CLI の FTS クエリ経路
  (`build_fts_tiers`/`query_units`、`main.rs:2058`/`1957`) も生クエリ。tokenizer は Trigram (Unicode 非正規化)。
  `kcs-search/src/query.rs:85` の `.nfc()` は cursor の query_hash 専用で MATCH 構築に繋がっていない (= 存在するのに未配線)。
- **再現** (隔離 tmp): 本文に NFD の "café"/"がぎぐげご" を含む doc を index → `search <NFC 形>` = **0 件**、
  `search <NFD 形>` = 1 件。ASCII 対照は正常。macOS/APFS・一部 IME・OCR/PDF 抽出由来で NFD は頻出。exit 0 で沈黙空。
- **期待 vs 実際**: 期待 = Unicode 正準等価 (NFC/NFD) はどちらの入力形でも同一内容を検索できる。実際 = NFD 内容が NFC
  クエリで 0 件。既修正の NUL/UTF-16/BOM (Q4/R5) と同系統の silent 索引欠落。
- **修正**: 索引投影とクエリを同一正規形 (NFC) に統一。(1) `fts.rs:66` を
  `let indexed_text = row.text.nfc().collect::<String>().replace('\u{0}', "");` (NFC → NUL 除去、derived index
  projection のみ、identity/evidence の char offset は原文のまま不変。snippet は `c.text.chars().take(200)` で
  offset 非依存・視覚的に同一)。(2) `run_search` で `build_fts_tiers`/`compute_query_embedding` へ渡す前に
  `parsed.query` を `.nfc()` 化。両方 NFC で NFD 内容↔任意正規化クエリが一致。

### F7 [major] Gemini embedding が要求次元と異なる長さのベクトルを返しても無検証で永続化 → chunk が永久に KNN 検索から除外、課金済み・自己修復不能
発見: Claude-Sonnet / stub server で再現

- **根本**: `parse_embeddings` (`crates/kcs-adapter/src/gemini_embedding.rs:146-171`) は `embeddings.len() == items.len()`
  (件数) のみ検証、各 `values.len() == dimensions` (次元) を一切チェックしない。`write_chunk_embedding`
  (`crates/kcs-index/src/embedding_store.rs:91-123`) は呼出元の `dimensions` (=ハードコード 768) をそのまま書き、
  実 vector バイト長と突き合わせない。`link_chunk_vec` (`embedding_store.rs:128-136`) は
  `vector.len() != CHUNK_VEC_DIMENSIONS*4` なら `Ok(())` で無言スキップ (chunk_vec に入らない) が、呼出元
  `send_embed_batch` (`main.rs:4875-4916`) はこれを成功として課金・done 化。
- **再現** (実 API 不要、stub HTTP が 768 要求に 5 要素返す): `index --approve --online` → embedding task "done"、
  `SELECT dimensions,length(vector) FROM embeddings` = `768 | 20` (5 float)。`chunk_vec` は空 → KNN から永久除外。
  `repair --rebuild-db` 後も回復しない。エラー・警告なし。
- **期待 vs 実際**: 期待 = 応答が要求次元と食い違えば contract violation で弾き再試行/報告。実際 = dimensions と実長が
  矛盾したまま永続化・課金済み・KNN 永久除外・どの経路でも自己修復せず・無通知。
- **修正**: `parse_embeddings` に expected dimension を渡し、各 `values.len() == dimensions` を検証、不一致は
  `AdapterError::ContractViolation`。

### F3 [major] cost-ledger の負値/非有限 usd が無検証で、budget remaining を増やし cap を fail-open させる
発見: GPT-5.5 / 実機確認: オーケストレータ

- **根本**: `append_monthly` (`crates/kcs-pipeline/src/budget.rs:83-99`) と `monthly_total_for_adapter`
  (`budget.rs:101-140` の `total += entry.usd`) が `usd` の `is_finite() && >= 0` を検証しない。JSON として読める
  負値行がそのまま合算され、`remaining = cap - spent` の spent が減って device/folder cap 超過を隠せる。
- **実機**: ledger に `usd:5.0` と `usd:-1000.0` を注入 → status 受理・corrupt 化せず、monthly_total が負に。
- **precondition**: ledger 書込 (device-global、owner-write。共有/同期/クローンされた ledger、または将来のバグ)。
  = Q6/R6-1/R7-1 と同型の「読めるが意味的に不正な永続レコード」検証欠落。cap は実 API spend を抑える safety なので fail-open は重い。
- **期待 vs 実際**: 期待 = ledger の usd は finite かつ >= 0、違反行は budget 判定から除外 or corrupt 扱い。
  実際 = 負値をそのまま計上し cap を無効化。
- **修正**: read (`monthly_total_for_adapter`) と append (`append_monthly`) の両方で `usd.is_finite() && usd >= 0.0`
  を必須にし、違反は `KCS-E-STORE-CORRUPT-001` 相当に分類 (または集計から除外)。

### F8 [major] device-global cost-ledger の budget check-then-append に跨り排他制御が無く、複数 scope の並行 index が月次 cap を超過できる (TOCTOU)
発見: Claude-Sonnet / 2 scope 並行で再現

- **根本**: budget 判定 → API 送信 → `append_monthly` の一連 (`main.rs:4772-4805` embedding、markdownize も同型) が
  read-then-act。`StoreLock` は scope 単位 (`.kcs/.lock`、`scope.rs:1141`/`main.rs:421`) で、cost-ledger は
  device-global (`main.rs:7056-7058` `$XDG_DATA_HOME/kcs/cost-ledger.jsonl`、全 scope 共有・ロック対象外)。
  scope A と B が互いの直前消費を見ずに許可判定 → 合算で cap 超過。
- **再現** (隔離 tmp、per_adapter embedding cap 0.00006、mock): 2 scope 同時 `index --approve --online` →
  ledger 合算 0.0000756 (cap の 126%)、両 task "done"・無警告。窓は ledger サイズに依存せず常時存在。
- **期待 vs 実際**: 期待 = device/folder/per_adapter cap を月内で絶対に超過しない。実際 = 並行 online index が合算で超過。
- **修正**: cost-ledger の read-check-append を device-global な単一ファイルロック
  (`$XDG_DATA_HOME/kcs/cost-ledger.lock`) で囲み、budget 判定〜append を直列化する。lock は check の直前に取得し
  append 後に解放 (API 送信を跨ぐと device 全体を直列化するため、送信は lock 外・append 直前に lock 下で再判定でも可。
  最小実装は「lock → 再 read → cap 判定 → append → unlock」を charge のたびに)。

### F4 [minor] `kcs tag` が到達不能な ref (name=`HEAD` / `sha256:<64hex>`) を「成功」として作成する
発見: GPT-5.5 / Opus (2 エンジン) / 実機確認

- **根本**: `Repository::tag()` (`crates/kcs-core/src/scope.rs:499`) は `validate_ref_operand`
  (`scope.rs:1049`) 通過後に `refs/tags/<name>` を書くが、同 validator は `HEAD` と `sha256:<64hex>` 形を弾かない。
  `resolve_commit()` (`scope.rs:523`) は `value=="HEAD"` (:530) と `is_hash(value)` (:535) を**タグ探索より先**に
  解釈するため、その名のタグは永久に shadow (dead ref)。
- **再現**: `kcs tag HEAD` → exit 0・`refs/tags/HEAD` 生成。`kcs tag sha256:aaaa…(64)` → exit 0 だが
  `kcs diff sha256:aaaa… HEAD` → `KCS-E-STORE-NOT-FOUND-001` (tag は無視されハッシュ解決される)。
- **期待 vs 実際**: 期待 = 解決不能な名前の tag 作成は拒否。実際 = 成功 JSON を返し dead ref を残す。
- **修正**: `validate_ref_operand` (`scope.rs:1049`) に `value == "HEAD" || is_hash(value)` を拒否条件へ追加。

### F5 [minor] documented budget config `warn_at_percent` / `hard_stop` が黙殺される (doc-vs-impl 乖離)
発見: Claude-Opus (確度 中)

- **根本**: docs/04:550-551 が両キーを config 例に掲載し `BudgetConfig` (`crates/kcs-pipeline/src/budget.rs:18-19`)
  にフィールドもあるが、`read_budget_config`/`ParsedBudgetConfig` (`budget.rs:227-292`) は `monthly_usd_cap` と
  `per_adapter` のみ抽出し両キーを参照しない。80% 警告は未実装、`hard_stop=false` も効かず常に hard pause。
- **期待 vs 実際**: 期待 = doc 通り 80% 警告 / soft-stop。実際 = 無視。
- **修正 (design 判断)**: (a) 両キーを parse して budget 判定に反映する (機能実装) か、(b) doc/struct から削除して
  仕様と実装を一致させる (doc-sync)。Phase 後回し候補でもあるため**ユーザー判断を仰ぐ** (下記 §design)。

---

## §design 判断待ち (auto-fix しない)

### F6 [major?] online Markdownize の完了成果物が HEAD/search に昇格せず task-only orphan (課金される OCR が永久に検索不可)
発見: GPT-5.5 / 実機確認: オーケストレータ

- **確認した挙動** (隔離 tmp、mock): `index --approve --online` → markdownize task pending → `batch resume` で
  tasks_executed=1・`objects/normalized_units` に 4 ファイル生成 (= 課金される online 成果物) だが
  `search "mock ocr"` (online 内容) = **0 件**、`reindex --force` 後も 0、`tree_entries.tool_profile_hash` は
  offline (76c01950) のまま。= online OCR 結果が commit tree/検索へ昇格せず永久に unsearchable。
- **論点**: `execute_pending_markdownize_tasks` は task の output_ref 更新のみで、`run_index_pipeline`/`reindex` は
  offline profile を使い online artifact を `normalize_by_path` に採用しない。加えて `standard_online_markdownize_profile()`
  は placeholder hash、実行時 resolved model hash なので provenance もずれる (Opus は adapter_id 安定なので観測破綻なしと評価)。
- **なぜ design 判断か**: docs は online markdownize の tree 昇格を Step 3 要件と明記していない (07:208 は Markdownize
  *fallback* を Step 4 と明記、本件=main path の promotion 時期は曖昧)。修正は「Done 時に resolved profile の
  normalized ref を tree commit へ昇格 + SQLite rebuild + tool-lock に resolved profile 記録」= 非自明な
  アーキ変更。「そもそも online markdownize task を Step 3 で走らせるべきか (課金するのに使えない)」も含め設計判断。
- **選択肢**: (A) 昇格ロジックを実装 (online 成果物を検索可能に)、(B) 昇格が Step 4 なら Step 3 では online
  markdownize task を作らない/走らせない (無駄な課金を止める)、(C) 既知の Step 4 保留として明文化し今回は非対応。

---

## 探索したが問題なしと確認した領域 (複数エンジン収束)
- **catalog.rs / adapter identity**: tool_profile_hash 決定性 SOUND (Opus + Sonnet)。JCS 正準化、PROFILE_FIELDS に
  adapter_id 非含有・dimensions 含有、CARGO_PKG_VERSION 非含有、profile() は env 非依存で決定的、mutable alias 拒否。
- **時刻/単調時計**: `duration_since(...).unwrap_or_default()` で逆行クロック吸収 (panic なし)、`is_valid_created_at`/
  `parse_utc_seconds` は閏年・桁・区切りを厳密検証 (Opus + Spark)。cost-ledger の月キー生成/比較も健全 (Spark)。
- **DAG 循環 / dangling parent / Evidence 解決**: commit は自ハッシュに parents を含む CAS 構造で循環構築不能、
  dangling parent は not_found で panic せず、Evidence は pointer 自身の commit tree を解決 (Sonnet + Opus)。
- **tag/log/diff の TOCTOU/traversal**: StoreLock 直列化、重複 tag はエラー、traversal 拒否 (Sonnet)。※ F4 は reserved-name 別問題。
- **cost-ledger append 原子性**: O_APPEND + 単一 write_all (M1(b))、append-only-delta で破損/lost-update なし。※ F8 は check-then-act 別問題。

## 総合所感
R6/R7 が非アトミック writer/破損 JSONL/秘匿承認/引数検証を掘った後、R8 は budget/cost-ledger 会計 (F1/F3/F5/F8)、
embedding 応答検証 (F7)、NFC/NFD 検索 (F2、4 エンジン収束) という別鉱脈から 6 major。共通するのは
「正常応答・成功ステータス・課金済みなのにユーザーに一切知らされない」silent な信頼性劣化 (検索網羅性・コスト保証・
データ整合性)。新規 catalog.rs の identity 決定性・時刻演算・DAG/CAS 検証は複数エンジンが堅牢と確認。
8 ラウンド連続で別鉱脈から実バグ。フィックスは実機フルサイクル再検証必須 (R5 Q1 の教訓)。
