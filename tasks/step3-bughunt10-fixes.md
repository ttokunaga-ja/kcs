# 探索型 4 エンジン監査 第 10 ラウンド (R10) 裁定

- 対象 HEAD: `148b9c2` (main、全テスト green 341、clippy --all-features / fmt clean)
- エンジン: Claude-Opus / Claude-Sonnet (フルスコープ実機) + GPT-5.5 (read-only 静的) + GPT-5.3-Codex-Spark (範囲限定: DAG/Evidence 整合 + snapshot/commit 書込順)
- 成果: **新規 6 major + 2 minor**。うち 5 件はオーケストレータが実バイナリ (target/debug/kcs, 148b9c2) で決定的に再現。却下 5 件 (下記)。
- 鉱脈: 4 エンジンが 4 方向に分散。今回の主脈は **(a) 規模境界がコア機能を壊す** (R10-1 KNN 4096) と
  **(b) 「ユーザー意図の除外/予算/回復が静かに破綻」** (R10-2/3/4/5、R9 の意味論ギャップ脈の延長) と
  **(c) 派生 artifact の crash-atomicity** (R10-6、Q2/R9-3 の別経路)。Spark の DAG/Evidence 探索は
  **既存ガード (M6/N5/L3、tree→commit→refs 書込順、CAS hash 検証) が正しく成立していることを確認** (実質 0 新規)。

## 位置づけ
開発者自身が所有する OSS (KCS) の出荷前防御的セキュリティ監査。全再現は隔離 tmp (`XDG_DATA_HOME=$(mktemp -d)`、
scope は /tmp 配下) で実施、実 API キー不使用、リポジトリ無変更 (git clean を維持)。

---

## R10-1 [major] ベクトル KNN の over-fetch が sqlite-vec の k≤4096 上限を超え、>4096 chunk を埋め込んだ scope が**既定 `kcs search` を device 全域で exit 2 墜落**させる (誤 CONFIG-SCHEMA)

- エンジン: Claude-Opus (実機再現) / オーケストレータ再現・device 全域波及を追加立証
- 根拠 file:line:
  - `crates/kcs-cli/src/main.rs:1503` `let total = embedding_store::chunk_vec_count(conn)…` — 無制限の全行 COUNT
  - `crates/kcs-cli/src/main.rs:1508-1509` `knn_chunk_distances(conn, &query_bytes, total)` — `total` をそのまま `k` に渡す (`.min(4096)` 無し)
  - `crates/kcs-index/src/embedding_store.rs:239-243` `… WHERE embedding MATCH ?1 ORDER BY distance LIMIT ?2` (`?2 = k`)。sqlite-vec は `k>4096` を拒否
  - `crates/kcs-cli/src/main.rs:1523` `kept.truncate(200)` — 結局 candidate_depth=200 しか使わない (FTS 側 `LIMIT 200` @1662 と対称)。**200 しか使わないのに全件 fetch している**のが二重の誤り
  - 波及経路: `vector_scope_search(...).map_err(ScopeSearchError::Fatal)?` (`main.rs:1431`) → multi-scope ループの `Err(Fatal) => return Err(error)` (`main.rs:1095`) で**全 scope abort**。既定 search は multi-scope (全登録 scope を走査、K3) なので 1 scope の破綻が device 全域を巻き添え。error 写像は `index_to_kcs`→`KcsError::schema`=`KCS-E-CONFIG-SCHEMA-001` (exit 2 Fatal) で、実体 (容量上限) と無関係に「設定不正」と誤誘導
  - 悪化要因: `embedding_store::link_chunk_vec` は `DELETE … WHERE chunk_id=?1` のみで旧 gen の chunk_id を消さず、`chunk_vec` が live 集合超に膨張しうる
- 再現 (オーケストレータ実機、device 全域波及込み):
  ```
  export XDG_DATA_HOME=$(mktemp -d) XDG_CACHE_HOME=$(mktemp -d)
  BIG=$(mktemp -d)/big; mkdir -p $BIG; cd $BIG
  python3 -c "open('big.md','w').write(''.join(f'# Section {i} token\n\nbody {i} token\n\n' for i in range(4200)))"
  kcs init .; KCS_TEST_GEMINI_EMBED=mock kcs index --online --approve
  KCS_TEST_GEMINI_EMBED=mock kcs search token   # exit 2:
  #   KCS-E-CONFIG-SCHEMA-001 "index sqlite error: k value in knn query too large, provided 4200 and the limit is 4096"
  # 別の健全 small scope に cd して既定 search → 同じ exit 2 (device 全域が墜落) ← 実測確認
  ```
- 期待 vs 実際: 期待=数百文書規模でも既定 search が返る。1 scope の問題は当該 scope の除外に留まる (docs/05 §1.8 per-scope isolation)。
  実際=`chunk_vec` 行数>4096 で既定 search (auto→hybrid) と `--vector` が exit 2 で全滅、`--text` のみ生存。誤 CONFIG-SCHEMA で誤誘導。既存テストは最大 2 行の chunk_vec しか通らず未捕捉。
- 修正方針:
  1. **(必須)** `main.rs:1508` を `let k = total.min(4096);` にキャップ (candidate_depth=200 なので理想は `min(total, 200)` だが、旧 gen bloat で非 live 行が上位を占める場合の recall 低下を避けるため上限 4096 が安全。恒久策はページング)。
  2. **(推奨)** sqlite-vec の容量系エラー (k 上限・変数上限) は `ScopeSearchError::Fatal` でなく **当該 scope の degradation (Excluded / text fallback)** に写像し、isolation 契約 (docs/05 §1.8) を守る。誤 `CONFIG-SCHEMA` を避ける。
  3. **(推奨/別項の遠因)** `link_chunk_vec` は旧 gen の chunk_vec 行を削除し `chunk_vec ≒ live 集合` を保つ (bloat 抑制。下記 latent の変数上限も同時に遠ざかる)。
- 回帰: >4096 chunk の scope で既定/`--vector`/`--text` search が全て成功すること、および健全 scope の search が別 scope の巨大化に巻き込まれないことを検証するテストを追加。

## R10-2 [major] top-level `ignore = [...]` が schema 有効なのに**無言で無視され**、除外予定ファイルが索引・commit・検索・online 送信に露出

- エンジン: GPT-5.5 (静的) / オーケストレータ実機再現
- 根拠 file:line:
  - `crates/kcs-core/schemas/config.schema.json:9-12` が top-level `ignore` (array) を定義。top-level `additionalProperties:false` (:88)
  - `crates/kcs-cli/tests/contract_cli.rs` `n3_config_ignore_array_validates` が top-level `ignore=["*.tmp","secret.pdf"]` を **valid** と assert (コメント "03 §11")
  - しかし `crates/kcs-pipeline/src/scan.rs` `load_config_ignore` は `value.get("scope").and_then(scope.get("ignore"))` = **`[scope].ignore` のみ**読む。top-level `ignore` は一切参照されない
  - 仕様正本 docs/03 §11 の config.toml 例 (585-604) は `[scope]` 配下、§11.1 (621) も「config (`[scope] ignore`)」。**top-level `ignore` は仕様のどこにも無い** → schema+test が stale
- 再現 (オーケストレータ実機):
  ```
  # CASE A: top-level ignore=["secret.txt"]  → secret.txt: ignored=False  ← 除外失敗
  # CASE B: [scope] ignore=["secret.txt"]     → secret.txt: ignored=True   ← 正常
  # かつ CASE A の config は `kcs status --json` が success = schema が valid と受理
  ```
- 期待 vs 実際: 期待=受理する config key は除外に効く、または未対応なら schema で拒否 (loud)。
  実際=`ignore=["secret.txt"]` は validation 成功だが除外ゼロ → CAS 取り込み + 検索露出 + online opt-in 下で cloud API 送信。R9-1 (silent 除外→露出) と同型・別根 (config-key drift)。
- 修正方針 (**採用=(A) 仕様準拠の拒否**): `config.schema.json` から top-level `ignore` (9-12 行) を削除 → top-level `additionalProperties:false` により明示 schema error (exit 2) で loud に落ちる。stale test `n3_config_ignore_array_validates` を「top-level `ignore` は拒否・`[scope] ignore` が正」に更新。
  - 代替 (B) fail-safe: `load_config_ignore` で top-level `ignore` も `[scope].ignore` と union する (無言露出は消えるが、仕様に無い機構を追加=非推奨)。**セキュリティ判断が絡むため、ユーザーが (B) を選好する場合は push 前レビューで上書き可**。
  - KCS の「silent 欠落の禁止」(docs/04 §5.2 の思想) と schema strictness (随所の additionalProperties:false) に照らし (A) を既定採用。

## R10-3 [major] ignore パターン照合が**大文字小文字を区別**し、case-insensitive FS (APFS 既定) では case 違いの実ファイルを除外できず露出

- エンジン: Claude-Sonnet (実機 A/B 対照) / オーケストレータ再現
- 根拠 file:line:
  - `crates/kcs-pipeline/src/scan.rs:273-298` `matches_ignore_pattern` — R9-1 で `.nfc()` は追加 (280-281) されたが **case 畳み込みは無い**。`wildcard_match_bytes` (305) はバイト完全一致
  - `crates/kcs-pipeline/src/scan.rs:214-254` `classify_secret` は `to_ascii_lowercase()` (217-218) で **組み込み Tier A/B 判定は case-insensitive** → ユーザー ignore パターンだけ case-sensitive の非対称
  - docs/03:610「gitignore 互換サブセット」。実 git は case-insensitive volume で `core.ignorecase=true` により `.gitignore` も case-insensitive
- 再現 (オーケストレータ実機、APFS 確認済):
  ```
  # file "CaseFixture.md" + .kcsignore "casefixture.md" (小文字) → ignored=False  ← 除外失敗
  # 対照: .kcsignore "CaseFixture.md" (exact) → ignored=True
  # `cat casefixture.md` が同一ファイルを開く = この FS 上で両名は同一ファイル
  ```
- 期待 vs 実際: 期待=gitignore 互換を謳う以上、case-insensitive FS では case 違いでも除外が効く。
  実際=case が一致しないと除外が無言で無効化 → コミット木取り込み + 検索スニペット全文露出 + online 送信。R9-1 (NFC/NFD) と同関数・同影響形・別軸 (case)。R10 ヒント「APFS の…大文字小文字」の脈。
- 修正方針: `matches_ignore_pattern` (と negation 経路 270) を **FS-aware case fold** にする。scope volume の case-insensitivity を git `core.ignorecase` 相当でプローブ (例: `.kcs` 内に probe ファイルを作り case-variant で存在確認、結果を scan 単位でキャッシュ) し、insensitive のときのみ `.nfc()` 後に (Unicode-aware) 小文字化して比較。case-sensitive volume では畳まない (別ファイルの誤除外=別種の silent データ欠落を防ぐ)。

## R10-4 [major] Partial online markdownize task の `batch retry`/`resume` が**恒久失敗 unit を無制限に再送・再課金**し、retry 予算と docs/04 §5.2 permanent-kind ゲートを完全 bypass

- エンジン: Claude-Sonnet (実機再現) / オーケストレータ再現
- 根拠 file:line:
  - `crates/kcs-cli/src/main.rs:4300-4332` `reenqueue_partial_markdownize_tasks` — Partial task の失敗 unit を無条件に Pending へ戻し、retry gate をクリア。`attempts`/`max_attempts`/`retry_policy` を一切参照せず、`attempts` を増分しない
  - `crates/kcs-cli/src/main.rs:4338-4351` `failed_unit_keys_from_instance` — unit を `status != Done` だけで選別、`error_kind` を読まない
  - `crates/kcs-cli/src/main.rs:6675-6676` — manifest 生成時、失敗 unit の `error_kind` は固定文字列 `"missing_output"` (実 `RetryErrorKind` ですらない) → 実 kind が manifest 時点で破壊され、§5.2 ゲートが下流で実装不能
  - `crates/kcs-pipeline/src/task.rs:336-351` `retry_policy(InvalidInput/ContractViolation)` = `retryable:false, max_attempts:0` — Partial 経路で完全 bypass
  - docs/04 §5.2 (~518): 「error_kind が permanent (invalid_input 等) の unit は**再投入せず** partial のまま `kcs status` に表示し続ける」— **未実装**
  - partial mock (`crates/kcs-adapter/src/catalog.rs:154` `pages.pop()`) は最終 unit を決定的に失敗 = permanent
- 再現 (オーケストレータ実機、2-page fake PDF, `KCS_TEST_MISTRAL_OCR=partial`):
  ```
  index → 1 unit Done / 1 unit Failed / task=pending
  各 batch retry → task=partial のまま、attempts=0 で凍結、cost-ledger の markdown 行が +1 (1→2→3→4)
  ```
- 期待 vs 実際: 期待=permanent unit は再投入されず static 表示、transient も max_attempts で頭打ち。
  実際=error_kind を区別せず attempts も増えないため、恒久失敗 unit が retry のたび online API へ再送・再課金。歯止めは月次 device budget cap のみ (月替りで復活)。`attempts` 凍結で orchestrator/agent が再送回数を検知不能 (Agent/JSON 契約の不透明)。R9-4 (Partial を回復可能化) が開けた穴。
- 修正方針:
  1. manifest の失敗 unit に**実 `RetryErrorKind`** を記録 (`"missing_output"` 固定を廃止)。
  2. `reenqueue_partial_markdownize_tasks`/`failed_unit_keys_from_instance` を unit ごとに `retry_policy(kind).retryable` で門番: 非 retryable unit は再投入しない (全失敗 unit が非 retryable なら task を Partial のまま据え置き)。
  3. 再投入のたび task 側 `attempts` を増分し `max_attempts` 到達で最終停止 (Partial 表示継続)。

## R10-5 [major] OCR 成功後の `persist_normalized_instance` 失敗を**非 retryable の `InvalidInput` に誤分類** → 課金済み成果物喪失 + タスク恒久固着 (batch retry も再 index も救えない)

- エンジン: Claude-Opus (静的確定 + 固着機序を実機実証)
- 根拠 file:line:
  - `crates/kcs-cli/src/main.rs:4740-4744` `persist_normalized_instance(...).map_err(|_| TaskExecutionFailure { retry_kind: RetryErrorKind::InvalidInput })` — OCR 成功 + 課金予約 (F8) 後の**書込 I/O 失敗**を一律 `InvalidInput` 化
  - 対照 `crates/kcs-cli/src/main.rs:4775` `AdapterError::Io { .. } => RetryErrorKind::NetworkError` (retryable)。同じ I/O 失敗で分類が非対称
  - 恒久化機序: `InvalidInput` = `retryable:false, max_attempts:0` (task.rs:336-343) → `batch retry` は `task_retry_allowed` で除外 → 再 index は Failed task を dedup (`main.rs:6739`、コメント 6722-6725「Failed は batch retry が所有」) で再 enqueue せず。**どの経路でも再駆動不能**。auth_error / contract_violation / retry 予算枯渇の Failed 全般に同機序が及ぶ (dedup の前提「batch retry が所有」が非 retryable では不成立)
- 再現 (オーケストレータ実機、固着機序を auth_error で実証):
  ```
  index --online --approve (mock) → md task pending
  batch resume (auth_error) → task failed (非 retryable)
  batch retry (mock=good key) → tasks_updated=0 / task still failed  ← 鍵を直しても回復不能
  index --online --approve (mock) → task still failed  ← dedup で再 enqueue されず
  ```
  (persist I/O 失敗自体は注入困難だが 4740-4744 の分類は静的に確実。上記は「非 retryable Failed は救済不能」機序の実証)
- 期待 vs 実際: 期待=OCR 後の一時 I/O 失敗 (ENOSPC/EIO/権限/中断 fsync) は retryable として batch retry で復旧。実際=非 retryable `InvalidInput`+再 index dedup で恒久固着、課金済み正規化成果物が喪失、error 種別も誤り (input は正常)。
- 修正方針:
  1. **(必須)** `main.rs:4742` を `RetryErrorKind::NetworkError` (retryable I/O 相当) に変更。→ persist 一時失敗が batch retry で復旧可能に。
  2. **(推奨)** 「原因解消後に非 retryable Failed を再駆動する経路」を用意 (例: 再 `index --online` が Failed markdownize task を再 enqueue する、または `batch retry --force`/reset)。最低限、Agent が Failed の恒久性を検知できるよう status に反映。

## R10-6 [major] open/view 展開 cache の**非アトミック書込 + cache-hit 時の hash 無検証**で、torn/改ざん cache を真正 Evidence として提供 (Q2 の cache 版)

- エンジン: GPT-5.5 (静的) / オーケストレータが torn-write 角度で確証
- 根拠 file:line:
  - `crates/kcs-cli/src/main.rs:3753-3766` cache 書込は `OpenOptions create+truncate` → `write_all` を**最終パスへ直書き** (temp+rename 無し)。crash/ENOSPC/SIGKILL で write_all 中断時、最終パスに partial ファイルが残り、エラー経路の掃除も無い
  - `crates/kcs-cli/src/main.rs:3707-3720` cache-hit は permission 補正後に**bytes hash を再検証せず即返却**。コメント 3728-3729 は「初回 materialization で検証、以降は as-is で再利用 (M5)」と明記 = torn 前提が崩れる
  - 対照: cache-miss 経路は `hash_bytes(&bytes) != hash` を検証 (3732、Q2)。つまり Q2 の verify-on-read は CAS object にだけ適用され、cache 再利用に未適用
  - 副次: cache key が `hash[0:12]` (48bit) + basename で full-hash より弱く、prefix+basename 衝突で別 object 混入 (低確率)
- 期待 vs 実際: 期待=派生 cache も CAS 同様アトミックに書かれ、提供 bytes が raw_hash と一致 (docs/08 raw object identity)。
  実際=torn cache が以後の open で無検証提供され、破損 bytes が真正 Evidence として返る。KCS 全体のアトミック書込規律 (`atomic_write`/`atomic_overwrite` が随所) に反する唯一の直書き。
- 修正方針: cache 書込を**アトミック化** (同一ディレクトリの temp ファイルへ書き→`fs::rename` で最終パスへ、R9-3 の 0600→0400 permission 規律は temp 側で維持)。torn partial が最終パスに残らなくなり cache-hit 信頼が回復。加えて cache dir を full-hash に広げ 12桁衝突も封じる (per-hit 再 hash は不要)。

## R10-7 [minor] `kcs index --online --yes` が online markdownize を**どの batch でも送れない dead-end**として enqueue (embedding は inline 送信されるのに markdownize だけ取り残る非対称)

- エンジン: Claude-Opus (実機再現)
- 根拠 file:line:
  - `crates/kcs-cli/src/main.rs:462` 永続 opt-in `network_opt_in = args.approve` のみ (`--yes` は false)
  - `crates/kcs-cli/src/main.rs:6977` `network_allowed`: `--online && (args.yes || args.approve)` → true、task は `ready_for_online_adapter`、index JSON は `network_allowed:true`
  - しかし online markdownize は index inline で送られず (`run_index` に execute_pending_markdownize なし)、batch 経由のみ。`batch` の門番は `persistent_network_allowed(repo)` (`main.rs:4388`) = `--yes` では false。`batch resume` に `--online` は無い (ResumeArgs は `--override-budget` のみ)。embedding は別門番 (`embedding_online_allowed(…, online=args.online)`) で `--online --yes` 送信成功 (N7) = 非対称
- 再現 (オーケストレータ実機):
  ```
  index --online --yes (mock) → status=indexed, network_allowed=True
  batch resume (mock) → executed=0 (恒久 pending の dead-end)
  対照 --online --approve → batch resume executed=1
  ```
- 期待 vs 実際: 期待=`--online --yes` (one-shot 送信) は embedding 同様 markdownize も送れる、または送れないなら honest に示す。
  実際=`network_allowed:true` と矛盾する silent dead-end。実害は現状 F6 (online markdownize 成果物の HEAD/search 昇格が Step 4 保留) で減殺されるが、F6 配線時に顕在化する潜在 major、かつ Agent/JSON 契約として不誠実。
- 修正方針 (F6 保留を踏まえ最小): per-invocation `network_allowed` が true でも markdownize を駆動できないなら、**状態を honest にする** (`ready_for_online_adapter`/`network_allowed:true` を偽らず、非永続 opt-in では `network_opt_in_required` として示す)。将来の inline 送信対称化 (embedding と揃える) は F6 配線とセットで。

## R10-8 [minor] `ensure_snapshot_tree_entries` の lazy insert が**非トランザクション**で、crash 中断時に partial 行集合が `existing>0` 短絡で再補完されない

- エンジン: GPT-5.3-Codex-Spark (静的) / オーケストレータが自己修復性を確認し severity を minor に確定
- 根拠 file:line:
  - `crates/kcs-cli/src/main.rs:1727-1747` `for entry in &tree.entries { conn.execute(INSERT …) }` — 明示トランザクション無し (SQLite autocommit で 1 行ずつ確定)
  - `crates/kcs-cli/src/main.rs:1715` `if existing > 0 { return tree_object_present(...) }` — 1 行でも在れば短絡し、欠損行を補完しない
  - 影響限定: `rebuild_step3_index`→`rebuild_sqlite_index` (`main.rs:2639`) は temp DB + atomic rename (P5) で**全 DB を差し替える**ため、通常の `reindex`/`repair` で自己修復する。恒久ブリックではない (R5 Q1・R9-5 より弱い)
- 期待 vs 実際: 期待=歴史 commit の tree_entries 射影は all-or-nothing。実際=read 経路 (search/cursor/short-hash) の lazy 補完が crash 中断すると、その commit の一部 path が次回以降 (reindex/repair 前) 解決不能。
- 修正方針: 1727-1747 の insert ループを 1 トランザクション (`conn.unchecked_transaction()` + commit) で包む。中断は全 rollback され `existing=0` を保つので短絡が partial を見なくなる。

---

## Latent / 未確定 (今回はフィックス発注しない)

- **[latent] fetch_live_meta の SQLite 変数上限**: `main.rs:1548-1567` は KNN 全行を `chunk_id IN (?,?,…)` の 1 変数/id で束ねるため id 数>32766 で変数上限超→同じ CONFIG-SCHEMA→Fatal。**R10-1 で k≤4096 にキャップされる間は到達不能**。R10-1 修正時にバッチ化を併せて検討 (defense-in-depth)。
- **[latent/未実証] object-stream PDF のページ取りこぼし → Done 偽装**: `prepare_units` が 1 unit しか出さない一方 OCR が N ページ返す場合、`mistral_ocr.rs:~235-255` が hints 超のページを無言破棄し `manifest_from_units`/`execute_online_markdownize_task` (`main.rs:4703-4728`) が prepared 集合基準で Done 判定 → 「N ページ課金・1 ページ保存・Done 偽装」の恐れ。**mock seam は pages を hints から導くため再現不可**、実 API + 実 object-stream PDF (PDF 1.5+) が要る。Opus 自身が「確定扱いしない」。実 API 検証フェーズで要確認 (ユーザー待ち)。

## 却下した所見 (再報告防止のため記録)

- **Spark 1(c) `log()` の親チェーン無限ループ** (scope.rs:435): content-addressing が「自己/子孫を親参照する commit」の構築を不可能にし、`cas.rs:88` の read_by_hash が content==hash を検証するため改ざん cycle も不成立 → **到達不能**。防御的 visited ガードは任意 (今回不要)。
- **Spark 1(b) cross-snapshot gen 束縛の欠落** (main.rs:3476-3484): `entry.normalize=None` で gen 検査が抜けるのは **L3 + N5 で文書化済みの許容挙動** (コメント 3471-3475)。到達する pointer 経路は index auto-commit (normalize 付き) を指すため gen ガードが効く。既知。
- **Spark 2(c) raw_hash→path fold** (main.rs:3051-3080): 同一内容 (同 raw_hash) の複数 path が最後の path に畳まれるのは **content-addressed identity の設計上の帰結** (project_kcs_artifact_dedup_policy)。pointer の `path_at_commit` は pointer 自身が保持し解決 correctness に影響せず。
- **GPT-5.5 registry `last_seen_at` 秒精度で spurious ambiguous**: 同一 scope_id を持つ 2 つの `.kcs` の tie を ambiguous にするのは **O7 の意図した安全挙動** (copy が乖離しうる以上 wrong-copy silent 解決より安全)。細粒度時刻は wrong-copy を無言化するだけで悪化。working-as-intended。
- **GPT-5.5 open cache 12桁 prefix 衝突 (単独)**: 48bit 衝突は実証不能。ただし R10-6 の torn-write が本質で、その修正 (full-hash cache dir) で衝突面も封じる。

---

## フィックス制約 (発注時に厳守)

- **docs/ は変更しない**。ただし `config.schema.json` と `crates/*/tests/*` は code 扱いで修正可 (R10-2 の schema/test 更新は必須)。
- 各修正ごとに関連 `cargo test` を回し、回帰テスト (>4096 chunk search / top-level ignore 拒否 / case-insensitive ignore / partial retry budget / persist retryable / open cache atomic) を**追加**する。
- 完了後 `cargo test --workspace` 全 green、`cargo clippy --all-features -- -D warnings` clean (R8 教訓: 必ず `--all-features`)、`cargo fmt --check` clean。
- **commit しない** (オーケストレータが majors を実機再確認してから commit)。リポジトリの他ファイルを汚さない。
