# Step4b 契約テスト仕様書: 検索 / gate / mode / cursor / multi-scope / exit (P2-C)

> 本書は **実装より先にテストを固定する** ためのケース仕様。Rust 実装コードは含まない。
> 正本 spec は `docs/05-runtime.md` **§1 全体 (1.1〜1.8)** と **§2.1〜§2.6** (shallow/GC の検索面参照のみ)、
> `docs/06-cli-spec.md` **§3 (Search)** と **§7 (Exit Code)** / §8 (Error Code Namespace の横断参照)、
> `docs/07-adapter-spec.md` **§3 (ネットワーク送信原則と opt-in — gate 正本)**。期待値はすべてこれらの
> 節の規範文から導く (1 文引用付き)。系譜は `tasks/step4b-contract-tests-{ledger,lifecycle}.md` と同じ
> `### PC<連番> ... - 正本 / 前提 / 操作 / 期待` 形式 (自己完結)。

**対象 U 項目**: `tasks/step4b-spec-gap.md` の **U63〜U77, U145** (H 領域 = 検索 / gate / mode / exit)。
Phase 割当は spec-gap 全体表の「Phase 2」。

**実装状態の再確認 (指示書 手順1)**: 「適合済みの可能性」4 件 (U66, U68, U73, U76) は本書作成にあたり
実装を直接精査した。**U66・U68・U76 は真に適合** — 現状固定の確認契約に圧縮 (PC18, PC28-29)。
**U73 は部分的に適合**(`--scope` 単独指定は登録簿の前方一致を経由せず直接 open するため「完全一致」が
構造的に成立、`--descendants` の path-component 境界判定も `Path::starts_with` により健全) —
1 本の確認契約に圧縮 (PC48)。

**対象外 (他グループ・Phase 3 送り — 混同注意)**:
- `kcs restore` / `kcs view` (05 §4) — D 領域 (restore) 担当
- purge の機構本体 (05 §3, §3.5) — E 領域担当。本書は `purge_blocks_raw` 等の**検索側フィルタ適用点**を
  前提として参照するのみ (Phase 1 で実装済み、再契約しない)
- Evidence Pointer の解決手順・6a/6b/verify (08) — G 領域担当。05 §1.7 のレスポンス内
  `evidence_pointer` 構築・`canonical_introduction` (response 用の pointer.commit 選択アルゴリズム) は
  読解のみ行い、本書では再契約しない (U71 が扱うのは §1.6 の**検索対象 chunk 集合の時点条件**であり
  §1.7 の pointer 表示アルゴリズムとは別の関心事)
- `07-adapter-spec.md` §3 のうち、承認 publish / revoke CLI・self-heal・pending 4 組一致等の**発行系**
  プロトコルそのもの — I 領域 (adapter 契約) 担当。本書が §3 から引くのは**検索が新規送信として満たす
  べき gate 条件の定義**のみ
- cost-ledger の device 行 (sync 縮退 2 相・stale_after_at・sweep・剪定) — 既に
  `tasks/step4b-contract-tests-ledger.md` §H (CL48-CL55) が契約化済み。本書は
  `compute_query_embedding_page1` を「device 行に正しく配線されている」前提で扱い、その中身は再契約
  しない
- GC 実行系 (tiered retention / on_idle / prune 本体、05 §2.2-§2.6) は Phase 4+ 実装。本書が触れるのは
  「shallow 化が**起こった後**の検索の反応」(§1.6 末尾・§2.2) のみ

## 実装対象ファイルの見込み (契約の対象であり実装方針を指図するものではない — 現状把握の記録)

- `crates/kcs-cli/src/main.rs` — 本書が扱う挙動のほぼ全てがこのファイルに集中する:
  `resolve_vector_availability`/`resolve_search_mode` (mode 解決, L1167-1309)、
  `embedding_opt_in_for_scopes`/`persistent_network_allowed_for_kcs_dir` (gate, L8512-8544)、
  `compute_query_embedding_page1` (L9444-9525)、`query_units`/`build_fts_tiers`/`fts_keyword_group`
  (MATCH 生成, L3427-3608)、`execute_fts_tier`/`vector_scope_search`/`fetch_live_meta`
  (candidate_depth, L2651-2886)、`search_one_scope_inner` (chunking_config_hash・shallow・HEAD 不在,
  L2277-2606)、`history_plan_error`/`ScopeSearchError` (shallow 伝播, L2121-2190)、
  `enumerate_scope_targets`/`registry_targets_under`/`scope_target` (canonical root_path,
  L5317-5494)、`effective_search_config`/`effective_search_tuning` (multi-scope 実効値,
  L5169-5298)、`parse_search_args` (`--at`+`--scope`/`--online`/`--offline` 欠落, L5012-5141)、
  run_search_inner 内の exit 分割集計 (L1748-1891)
- `crates/kcs-search/src/cursor.rs` — `ScopeCursor`/`CursorToken` (L29-61): `index_generation` フィールド
  なし、`query_vector_digest` フィールドなし
- `crates/kcs-search/src/query.rs` — `QueryHashInput` (L102-114): `query_vector_digest` なし
- `crates/kcs-search/src/mmr.rs` — 確認済み適合 (変更不要)
- `crates/kcs-search/src/rrf.rs` — `fuse_rrf` の `candidate_depth` 適用はマージ段のみ (確認済み、SQL 側の
  変更が本体)
- `crates/kcs-index/src/fts.rs` / `crates/kcs-index/src/rows.rs` — `chunks.first_seen_commit` は単一列
  (rows.rs:20)。`chunk_publications` 表は存在しない (grep 0 件)。`chunk_config_generations` に
  `introduction_commit` 列なし (fts.rs:521-527)
- `crates/kcs-index/src/embedding_store.rs` — `EmbeddingTargetType::QueryCache` (L585) は文字列変換の
  1 箇所のみで書込・読出経路が存在しない
- `crates/kcs-cli/src/historical_reindex.rs` — `retained_history_instances` (L97-207) は
  `all_parents(head)` で全履歴を対象化 (HEAD 限定なし)
- `crates/kcs-cli/src/search_history.rs` / `search_time.rs` — 確認済み適合 (時点セレクタ・cursor 継承の
  基礎は健全。§1.6 の ancestor-or-equal 判定は tree walk による binding 存在確認のみで、chunk 自体の
  introduction 時点は見ていない — J 節参照)
- `crates/kcs-cli/src/multi_scope.rs` — `[search.multi_scope]` (parallelism/timeout) の解決のみを担当。
  U74 が扱う `[search]` (default_mode 等) の実効値解決とは**別の設定名前空間**であり対象外

---

## 0. ID 体系と優先度

| 接頭辞範囲 | 対象契約領域 | 主根拠 | 対応 U |
| --- | --- | --- | --- |
| PC1-PC3 (§A) | auto 解決順・fail_behavior 適用範囲 | 05 §1.1 | U63 |
| PC4-PC7 (§B) | embedding consent gate (07 §3 正本) | 07 §3 / 05 §1.1 | U63 |
| PC8-PC14 (§C) | 短語 LIKE fallback・決定的 MATCH 生成 | 05 §1.3 | U64 |
| PC15-PC17 (§D) | candidate_depth の内側段適用 | 05 §1.3 | U65 |
| PC18 (§E) | MMR 初手 tie-break・適用除外拡大 [確認済み] | 05 §1.4 | U66 |
| PC19-PC27 (§F) | cursor 拡張 (index_generation・tree 別 config・query vector 再利用) | 05 §1.5 | U67 |
| PC28-PC29 (§G) | --offset 単一実行内限定・ページング継続 [確認済み] | 05 §1.5 | U68, U76 |
| PC30-PC33 (§H) | --at --vector error 化・共通フィルタ対象 tree 化 | 05 §1.6 | U69 |
| PC34-PC36 (§I) | HEAD 不在 scope の取り扱い | 05 §1.6 / 02 §11 | U70 |
| PC37-PC44 (§J) | 検索の時点条件正式化 (introduction ancestor-or-equal) | 05 §1.6 | U71 |
| PC45-PC47 (§K) | shallow 化 commit の walk skip 可視化 | 05 §1.6 / §2.2 | U72 |
| PC48 (§L) | --scope 単独指定・canonical root_path [確認済み] | 05 §1.8 | U73 |
| PC49-PC51 (§M) | multi-scope 実効値解決 (device 層) | 05 §1.8 | U74 |
| PC52-PC58 (§N) | vector 横断条件・全 scope 失敗 exit 分割 | 05 §1.6 / §1.8 / 06 §7-8 | U75 |
| PC59-PC60 (§O) | `--at` の multi-scope 制約新設 | 06 §3 | U77 |
| PC61-PC63 (§P) | chunking config 変更時の再 chunk/再 embedding 対象限定 | 04 §4.6 | U145 |

**優先度**: **P0** = このロットの完了条件 (正しさ・セキュリティ・exit code 契約に直結)。**P1** = 推奨
(堅牢性・観測性・確認固定)。**P2** = 参考 (軽微・相互参照・境界確認)。

P0/P1/P2 集計は末尾「集計」節。

---

## A. auto 解決順・fail_behavior 適用範囲 (U63 の一部)

### PC1 auto/--hybrid の 7 行解決順と判定順序 (先勝ち) [P0]
- 正本: 05 §1.1 L25-36 (『--offline 指定 → text fallback ... embedding profile_hash 不一致 →
  text fallback (KCS-E-SEARCH-VEC-INCOMPAT-001) ... embedding 承認なし → text fallback
  (KCS-E-SEARCH-VEC-UNAUTHORIZED-001) ... 同一 query が in-flight → text fallback
  (embedding_in_flight) ... query embedding 応答が... contract violation → text fallback
  (embedding_contract_violation) ... 上記のいずれにも該当せず vector のみ利用不能 → text ... 両方利用可能
  → hybrid ... 両方不可 → error』) / L38-39 (『解決順の列挙は判定順序でもある — 複数条件が同時に成立
  する場合は先に列挙された行の fallback_reason / error code を採用する (profile 不一致 (INCOMPAT) が
  承認なし (UNAUTHORIZED) に先行)』)
- 前提: 単一 scope、`auto` モード。7 通りの条件単独ケースに加え、(h) `--offline` 指定 **かつ** embedding
  profile 不一致が同時に真であるケース。
- 操作: 各条件を単独発生させて `kcs search --json` を実行。(h) は両条件を同時に満たす環境で実行。
- 期待: (a)-(f) の 6 通りは対応する `fallback_reason`/`error_code` で `resolved_mode="text"`,
  `fallback=true`, exit 0。(g) 両方利用可能は `resolved_mode="hybrid"`。両方不可は
  `KCS-E-SEARCH-VEC-UNAVAIL-001` で `--hybrid` 時は fail_behavior 次第 (PC2 参照)、auto は常に text。
  (h) は `fallback_reason="offline"` を採用する (offline が最初に列挙されているため、profile 不一致より
  優先)。**現状**: `resolve_search_mode`/`VectorAvailability` (main.rs L1097-1309) は
  `embedding_endpoint_not_configured → embedding_index_missing → embedding_opt_in_required →
  query_embedding_unavailable` の 4 段のみを判定順序として実装しており、新 7 行のうち
  `offline`・`embedding_in_flight`・`embedding_contract_violation` の 3 条件が判定順序に組み込まれて
  いない (offline は CLI flag 自体が存在しない — PC5)。

### PC2 fail_behavior の適用対象は技術的過渡失敗のみ (offline/unauthorized は対象外) [P0]
- 正本: 05 §1.1 L56-59 (『ユーザー意思由来の text fallback は fail_behavior の対象外である —
  fail_behavior は技術的失敗 (INCOMPAT / UNAVAIL 等) への応答方針であり、embedding_not_authorized
  (承認なし) と offline (--offline 指定) には適用しない (設定値に関わらず auto / --hybrid は常に
  text fallback、--vector のみ error』) / L60-63 (『embedding_in_flight... と
  embedding_contract_violation... は技術的な過渡失敗であり fail_behavior の対象: auto は text
  fallback、--hybrid は fail_behavior に従い、--vector 明示は... error』)
- 前提: `[search].fail_behavior = "error"`。(a) 承認なし (embedding_not_authorized) で `--hybrid`。
  (b) `--offline` で `--hybrid`。(c) embedding_in_flight で `--hybrid`。(d) embedding_contract_violation
  で `--hybrid`。
- 操作: 各ケースで `kcs search --hybrid` を実行 (fail_behavior=error のまま)。
- 期待: (a)(b) は `fail_behavior=error` にもかかわらず **text fallback (exit 0)** のまま —
  ユーザー意思由来の縮退は設定で error 化できない。(c)(d) は `fail_behavior=error` に従って
  **hard error** (exit 1、`KCS-E-SEARCH-VEC-UNAVAIL-001`) になる。**現状**: `resolve_search_mode`
  (main.rs L1263-1307) は `VectorAvailability::Unavailable`/`Incompatible` の 2 種類しか区別せず、
  fail_behavior は無条件に両方へ適用される — 「ユーザー意思 vs 技術的過渡失敗」の分岐自体が
  存在しない (7 行モデル自体が未実装のため、この分岐点も構造的に欠落)。

### PC3 [確認済み] fail_behavior=warn は fallback と同一結果+warning field、exit も同一 [P1]
- 正本: 05 §1.1 L40-42 (『fail_behavior = "warn" の挙動は fallback と同じ結果 (text fallback +
  fallback_reason) に加えて構造化 warning を stderr / --json の warnings[] へ出す — exit code も
  fallback と同じ (error にしない)』)
- 前提: `[search].fail_behavior = "warn"`、vector 技術的過渡不可 (index 未構築等) で auto/--hybrid。
- 操作: `kcs search --hybrid --json` を実行。
- 期待: `resolved_mode="text"`, `fallback=true`, exit 0、`warning` フィールドが非 null。**現状**:
  `SearchFailBehavior::Warn` (main.rs L1282-1295) は既にこの挙動を実装済み — ただし応答スキーマは
  単一の `"warning"` 文字列 field であり、spec 文言の `warnings[]` (配列) とは形が異なる。
  **[解釈割れ]** 単数 `warning` と配列 `warnings[]` のどちらが正本かは §Q note-1 参照。単数
  field の存在自体は fail_behavior=warn の効果として適合するため本契約は「確認済み」区分とするが、
  スキーマの数/複数は据え置く。

---

## B. embedding consent gate (07-adapter-spec.md §3 正本)

### PC4 送信可否は「参加 scope の 1 つ以上」の OR — 現状は全 scope 一致の AND [P0]
- 正本: 05 §1.1 L46-48 (『送信可否 = 参加 scope の 1 つ以上に当該 embedding Adapter の active な
  approvals[] 行があり、かつ当該 scope の実効 allow_network が true であること』) / 07 §3 L224-226
  (『送信可否 = 参加 scope の 1 つ以上に当該 embedding Adapter の active 承認 + 当該 scope の実効
  allow_network = true (§3 の gate と同一規範)』)
- 前提: multi-scope 検索 (scope S1, S2 が参加)。S1 は embedding adapter への active 承認 + 実効
  `allow_network=true`。S2 は未承認 (allow_network 未設定)。query は 2 文字以上、auto モード。
- 操作: `kcs search "query text" --json` を実行 (S1, S2 双方が参加する検索)。
- 期待: 少なくとも 1 scope (S1) が gate を満たすため、query embedding は**送信される** (vector/hybrid
  が候補になり得る — profile 互換なら S1 の vector 検索が有効、S2 は未承認でも送信された query vector
  を用いた vector 検索に参加してよい (07 §3 「送信は 1 回であり scope 別の再送信は発生しない」に相当する
  05 §1.8 L390 の規定)。**現状**: `embedding_opt_in_for_scopes` (main.rs L8537-8544) は
  `for exec in exec_scopes { if !persistent_network_allowed_for_kcs_dir(...) { return Ok(false) } }`
  — **1 つでも未承認 scope があれば全体が false になる AND 集約**。上記シナリオでは
  `embedding_opt_in=false` となり、`resolve_vector_availability` が `embedding_opt_in_required` で
  text fallback してしまう (S1 が承認済みでも送信されない) — spec の OR 定義と正反対の縮退。

### PC5 `kcs search [--online|--offline]` フラグが存在しない [P0]
- 正本: 05 §1.2 L78 (『`kcs search "..." [--online|--offline]` — query embedding の一時 opt-in /
  当該実行の新規送信禁止 (§1.1 consent gate)』) / 07 §3 L214-219 (『CLI フラグ --online は... 一時
  opt-in で... 永続的な承認状態を作らない... --offline は逆向きの一時上書きで、当該実行の新規送信を
  禁止する』)
- 前提: なし。
- 操作: `kcs search "query" --online` および `kcs search "query" --offline` を実行。
- 期待: `--online` は未承認 scope の gate を当該実行に限り一時的に開く (approvals[] 行は作らない、07
  §7 の log に `cli_online` として記録)。`--offline` は承認の有無に関わらず当該実行の query embedding
  送信を禁止し、auto/--hybrid は `fallback_reason="offline"` の text fallback、`--vector` 明示は
  `KCS-E-SEARCH-VEC-UNAVAIL-001` で error (PC1 参照)。**現状**: `parse_search_args`
  (main.rs L5012-5141) にこの 2 フラグの分岐が無く、`grep -c '"--online"\|"--offline"'` は
  main.rs 全体で **0 件** — 未知フラグとして `KCS-E-CONFIG-USAGE-001` (invalid usage) になる
  (フラグ自体が構文レベルで拒否される)。

### PC6 送信可否の最終検証は相 1 claim Tx 内 (BEGIN IMMEDIATE 保持下) での再読 [P0]
- 正本: 05 §1.1 L50-53 (『この可否は相 1 claim Tx 内 (BEGIN IMMEDIATE 保持下) で approvals[] /
  boolean を再読して最終検証する (読み取り開始時の値を使い回さない — 検証後に revoke が完了した
  場合の当該送信は in-flight として許容...)』) / 07 §3 L144-146 (『発行停止の境界 = 相 1 claim Tx 内
  (BEGIN IMMEDIATE 保持下) の最終再読... 再読後に完了した revoke の当該送信は in-flight として許容』)
- 前提: 検索実行開始時点では embedding 承認が有効。`compute_query_embedding_page1` の
  `device_claim` (相 1、`BEGIN IMMEDIATE` Tx) 開始 **直前**に、別プロセスが
  `kcs adapter revoke <embedding_tool_id>` を完了させる。
- 操作: 上記タイミングで `kcs search --hybrid` を実行する (revoke が gate 判定より後、claim Tx より
  前に完了するよう制御する結合テスト、または再読ロジックの単体テストとして「Tx 開始後に approvals[] を
  再読して boolean/行の現在値を評価する」ことを直接検証する)。
- 期待: 相 1 claim Tx 内で approvals[]/allow_network boolean を**再読**し、revoke 後の現在値
  (未承認) に基づいて送信を **拒否** (text fallback、`fallback_reason="embedding_not_authorized"`)
  — 検索開始時点の古い判定を使い回さない。逆に、Tx 内の再読時点ではまだ承認済みで、Tx 完了 (再読) の
  **後**に revoke が完了した場合は、既に送信が in-flight として許容される (取り消されない)。**現状**:
  `embedding_opt_in` (main.rs L1501-1504) は `run_search_inner` の先頭で一度だけ計算される
  precheck であり、`compute_query_embedding_page1` (main.rs L9444-9525) 内の
  `with_immediate_transaction` (L9466, L9480) は **cost-ledger の sweep/claim にのみ用いられ**、
  approvals[]/allow_network の再読は行わない — 「claim Tx 内での最終検証」という規則自体が
  未実装 (precheck が唯一かつ最終の判定)。

### PC7 embedding_contract_violation の fallback_reason 分類が存在しない [P1]
- 正本: 05 §1.1 L32 (『query embedding 応答が受入検査 (07-adapter-spec.md §5.3) で contract
  violation → text fallback (fallback_reason="embedding_contract_violation")』) / L60-63 (前掲、
  fail_behavior の対象)
- 前提: query embedding の応答が 07 §5.3 の受入検査 (次元数不一致等の contract violation) に
  違反する。
- 操作: `kcs search --hybrid --json` を実行。
- 期待: `fallback_reason="embedding_contract_violation"` で text fallback (auto) または
  fail_behavior 準拠 (`--hybrid`)。**現状**: `grep -n "embedding_contract_violation"` は
  main.rs 全体で 0 件 — `run_embedding_adapter` (main.rs L9368-9386 付近) の失敗は
  `compute_query_embedding_page1` の `Err(_) => { ...settle_task_charge_unknown...; Ok(None) }`
  (L9519-9523) に一括吸収され、`QueryEmbeddingOutcome::InFlight` 以外の失敗要因を区別する経路が
  無い — profile 不一致・adapter 障害・contract violation が全て同じ「query_embedding_unavailable」
  相当に潰れる。

---

## C. 短語 LIKE fallback・決定的 MATCH 生成 (05 §1.3)

### PC8 MATCH 式は token を個別に二重引用符で囲んだ並びとして機械生成する (現行アーキテクチャの置換) [P0]
- 正本: 05 §1.3 L110-113 (『user query を FTS5 構文として解釈しない — token 列を各々二重引用符で
  囲んだ phrase / term の並びとして MATCH 式を機械生成する (token 内の " は "" へ escape。C++ 等の
  記号語が fts5 syntax error にならない)。FTS5 演算子... の直接指定は MVP では提供しない』)
- 前提: query = `"C++ token"` (2 token: `C++`, `token`)。
- 操作: MATCH 式生成ルーチンを呼び出す。
- 期待: 生成される MATCH 式は各 token を個別 quote した並び (`"C++" OR "token"` 相当、結合演算子は
  §1.3 の他規則 — PC9/PC12 参照) であり、**query 由来でない追加語を含まない**。**現状**:
  `build_fts_tiers`/`fts_keyword_group`/`fts_keyword_expansions` (main.rs L3481-3608) は (1) 純数値
  token (4桁以上) にカンマ区切り異形を注入する `thousands_separated` 展開、(2) `chunk`/`token`/
  `pipeline` 等の固定バイリンガル辞書展開 (`チャンク`/`トークン`/`パイプライン` を追加注入)、
  (3) tier1 (strict AND/OR) と tier2 (relaxed OR、全 unit の OR) の 2 段構成、という**新 spec が
  規定しない 3 種の追加処理**を含む独自アーキテクチャであり、「token 列をそのまま個別 quote」という
  単純な機械生成とは別物。

### PC9 tokenization は NFC 正規化後 Unicode 空白分割で決定的に固定する [P0]
- 正本: 05 §1.3 L113-114 (『tokenization は決定的に固定する: NFC 正規化後の query を Unicode 空白で
  分割した各非空片が token (長さの単位 = Unicode scalar 数。記号のみの token も phrase として
  投入可)』)
- 前提: query = `"café  ﾃｽﾄ"` (未正規化の合成文字 + 半角カナ + 連続空白)。
- 操作: tokenizer を呼び出す。
- 期待: query 全体を NFC 正規化した後、Unicode 空白 (連続空白は 1 区切りとして扱う) で分割し、
  非空片をそのまま token とする (記号のみの `"++"` のような片も 1 token として許可)。**現状**:
  `query_units` (main.rs L3427-3468) は CJK ラン (3 文字未満は完全破棄) と「英数字 + `.`/`-`/`_`」の
  word ラン (3 文字未満は破棄、それ以外の記号は全て読み飛ばし) という**独自の文字クラス分類**を行い、
  NFC 正規化を一切行わず、Unicode 空白分割によるシンプルな token 化ではない (記号のみの token は
  `is_word`/`is_cjk` どちらにも該当せず消失する)。

### PC10 token 0 個の query は KCS-E-CONFIG-USAGE-001 (exit 2) — 現状は空結果 exit 0 [P0]
- 正本: 05 §1.3 L115 (『token が 0 個の query は KCS-E-CONFIG-USAGE-001 (exit 2)』)
- 前提: query = `"   "` (空白のみ、3 文字)。
- 操作: `kcs search "   "` を実行。
- 期待: 起動時に `KCS-E-CONFIG-USAGE-001` (exit 2) で拒否する (index/registry へのアクセス前)。
  **現状**: `parsed.query.chars().count() < 2` (main.rs L1929) の早期 return は文字数 3 の空白
  query を通過させ、`query_units` が `(vec![], vec![])` を返した結果 `build_fts_tiers` が空 tiers を
  返し、`fts_scope_search` が黙って空候補を返す — **exit 0 の空結果**になり usage error にならない
  (0-token 検知ルーチン自体が存在しない)。

### PC11 全 token が 3 文字未満 → bounded LIKE (instr) fallback — 現状は即時空結果 [P0]
- 正本: 05 §1.3 L95-97 (『query の全 token が 3 文字未満で trigram tokenizer の MATCH が成立しない
  場合 (例: 1〜2 文字の日本語 query — MATCH は 0 件になる)、text バックエンドは chunks.text への
  bounded LIKE スキャン (上限 = candidate_depth、instr ベースの部分一致) へ fallback する』)
- 前提: query = `"認証"` (2 文字、CJK)。同一 scope に `"...認証仕様..."` を含む chunk が存在する。
- 操作: `kcs search "認証" --text` を実行。
- 期待: FTS5 MATCH が 0 件になるため `chunks.text` への bounded LIKE (instr) スキャンへ fallback し、
  上限 candidate_depth 件を返す (該当 chunk がヒットする)。**現状**: `parsed.query.chars().count() < 2`
  は 2 文字の `"認証"` を通過させる (`count()==2`) が、`query_units` の CJK 分岐は `run.len() >= 3`
  を要求する (main.rs L3442) ため 2 文字の CJK ランは **1 個も trigram を生成しない** —
  `build_fts_tiers` は空 tiers を返し、instr ベース LIKE fallback ルーチン自体が存在しない
  (grep `"instr("` = main.rs 全体で 0 件) ため、spec が明示する例 (「1〜2 文字の日本語 query」) が
  そのまま無条件の空結果になる。

### PC12 混在 query: 3 文字以上 token は MATCH、3 文字未満 token は同一 bounded query 内の AND instr 条件 [P0]
- 正本: 05 §1.3 L97-101 (『3 文字以上の token が 1 つでもあれば FTS MATCH を使う — ただし MATCH 式に
  渡すのは 3 文字以上の token のみとし、3 文字未満の token は同一 bounded query 内の instr 条件として
  LIMIT 前に AND 適用する』)
- 前提: query = `"AI 認証"` (token: `AI` (2 文字, ASCII), `認証` (2 文字, CJK) — 双方 3 文字未満だが
  トークン化上は別種)。比較のため query = `"authentication AI"` (token: `authentication` (14 文字),
  `AI` (2 文字)) も用意する。
- 操作: それぞれ `kcs search "<query>" --text` を実行。
- 期待: 後者は `authentication` を MATCH 式に渡し、`AI` は同一 bounded query 内で
  `instr(chunks.text, 'AI') > 0` 相当の AND 条件として LIMIT 前に適用する (`AI` は MATCH 式に
  含まれない)。前者 (両 token とも 3 文字未満) は PC11 の全短語 fallback に該当する。**現状**:
  `query_units`/`build_fts_tiers` に長さによる MATCH/instr の振り分け構造が無く (3 文字未満 token は
  MATCH からも instr からも単に脱落する)、混在ケースの `AI` は完全に無視される。

### PC13 短語 instr 条件は text/vector 両バックエンド共通の eligibility 述語として候補確定前に適用 [P0]
- 正本: 05 §1.3 L101-106 (『短語 instr 条件は text / vector 両バックエンド共通の eligibility 述語であり、
  各バックエンドの候補確定 (candidate_depth 充足前) に適用する — 和集合・RRF に短語欠落候補を
  入れない... vector 側の適用形: chunk_vec を chunks へ JOIN して instr 述語を適用した母集合に対し
  distance 順で LIMIT candidate_depth を確定する (brute-force KNN)』)
- 前提: query = `"authentication AI"` (PC12 と同一)、hybrid モード。vector 側の候補プールに `AI` を
  含まない chunk が上位に多数存在する。
- 操作: `kcs search "authentication AI" --hybrid` を実行。
- 期待: vector 側も `AI` の instr 述語を JOIN 済み母集合 (brute-force KNN、distance 順 LIMIT
  candidate_depth) に適用してから候補を確定する — `AI` を含まない chunk は vector 候補プールにも
  入らない。**現状**: 短語 instr 条件の実装自体が存在しない (PC11/PC12) ため、vector 側の適用点も
  当然存在しない。`vector_scope_search` (main.rs L2651-2705) は述語なしの brute-force KNN のみ。

### PC14 LIKE fallback の順序は instr 昇順→chunk_id 昇順、LIMIT は ORDER BY 確定後に適用 [P1]
- 正本: 05 §1.3 L107-109 (『LIKE fallback の順位も決定的に定める: 最初の一致位置 (instr) 昇順、
  同点は chunk_id 昇順。SQL は ORDER BY 確定後に LIMIT candidate_depth を適用する (LIMIT 先行で
  候補集合が非決定になる形は禁止)』)
- 前提: PC11 と同一環境、複数 chunk が同一短語を異なる位置で含む。
- 操作: LIKE fallback ルーチンを実行し、生成 SQL の `ORDER BY`/`LIMIT` 節を検査する。
- 期待: `ORDER BY instr(text, ?) ASC, chunk_id ASC LIMIT candidate_depth` の形 (ORDER BY が LIMIT より
  文法上先行し、SQLite の実行計画が LIMIT 先行の非決定パスを取らないことを `EXPLAIN QUERY PLAN` で
  確認する)。**現状**: 未実装 (PC11 と同根)。

---

## D. candidate_depth の内側段適用 (05 §1.3 実装規則)

### PC15 text backend: candidate_depth は rank 計算の内側段 (サブクエリ) で効かせる — 外側 LIMIT 禁止 [P0]
- 正本: 05 §1.3 L119-121 (『実装規則: candidate_depth の上限は rank 計算 (window 関数等) の入力に
  なる内側段 (サブクエリ) で効かせる。外側の LIMIT では全マッチ行が rank 計算の入力に入り、大ヒット数
  クエリで実行コストが数十倍に膨張する (VM step 1,074 → 70,374)』)
- 前提: `[search.rrf] candidate_depth = 500` (デフォルト 200 から変更)。大ヒット数 (1000+ 一致行) の
  query。
- 操作: `kcs search "<高頻度語>" --text` を、candidate_depth=200 (デフォルト) と 500 の 2 通りの設定で
  実行し、`EXPLAIN QUERY PLAN` の VM step 数、および実際に返る候補件数 (RRF 入力前の text_ranks 長) を
  比較する。
- 期待: candidate_depth=500 設定時、text_ranks は最大 500 件まで返り得る (200 に固定されない)。
  VM step 数は candidate_depth にほぼ比例し、全マッチ行数には比例しない。**現状**: `execute_fts_tier`
  (main.rs L2828-2858) は SQL 内に `LIMIT 200` を**リテラル直書き**しており、関数シグネチャに
  `candidate_depth` パラメータ自体が無い — `[search.rrf].candidate_depth` を 200 超に設定しても
  SQL レベルでは常に 200 件で頭打ちになる (`rrf.rs::fuse_rrf` の `.take(candidate_depth)` は
  この 200 件を上限として更に絞るだけで、200 を超えて増やす経路が存在しない)。

### PC16 vector backend: 述語 (eligibility) 適用前に vec0 の内部 top-k を確定させない [P0]
- 正本: 05 §1.3 L104-106 (『vec0 の k = 構文等、述語適用前に内部 top-k を確定させる形は用いない —
  述語後の候補が痩せて candidate_depth を満たせなくなるため』)
- 前提: scope の embedding index に 5000 chunk。うち eligibility 述語 (時点条件 + config association
  + 短語 instr、PC13) を満たすのは 150 件のみで、それらの distance 順位は全体の下位 (5000 件中
  4000 位以降) に偏っている。`[search.rrf] candidate_depth = 200`。
- 操作: `kcs search "<query>" --vector` を実行する。
- 期待: 述語適用**後**の母集合 (150 件) に対して distance 順 LIMIT candidate_depth (200) を確定する
  ため、150 件全てが候補になり得る。**現状**: `vector_scope_search` (main.rs L2651-2705) は
  `let k = total.min(VECTOR_KNN_MAX_K)` (`VECTOR_KNN_MAX_K = 4096`、L2612) を**述語適用前**に
  `knn_chunk_distances(conn, &query_bytes, k)` へ渡し (vec0 の内部 top-k を先に確定)、その後
  `fetch_live_meta` で eligibility を判定して `filter(|(id,_)| meta.contains_key(id))` — 5000 件中
  4000 位以降に偏る上記シナリオでは、vec0 が返す上位 k 件(実質上位 4096 = ほぼ全件だが、より狭い
  scope では容易に「述語後の候補が candidate_depth を満たせなくなる」条件を再現できる) の中から事後
  filter するため、**述語適用前に内部 top-k を確定させる禁止パターンそのもの**。さらに
  `kept.truncate(200)` (L2695) も `candidate_depth` パラメータではなくリテラル `200`。

### PC17 candidate_depth 設定値の反映を通しで検証する回帰契約 [P1]
- 正本: 05 §1.3 L83-84 (『候補取得: text / vector 各バックエンドから検索対象集合内の上位
  candidate_depth 件... を... 取得し、和集合を候補プールとする』) — PC15/PC16 の結合確認。
- 前提: `[search.rrf] candidate_depth = 300`。text 側に 250 件、vector 側に 250 件の eligible
  候補 (重複なし) が存在する hybrid 検索。
- 操作: `kcs search "<query>" --hybrid --json` を実行し、RRF 融合前の各バックエンド候補件数を計測する
  (内部計測 API またはログ経由)。
- 期待: text 側・vector 側とも最大 300 件まで取得される (PC15/PC16 実装後の結合的帰結)。**現状**:
  PC15/PC16 が未実装のため、text は 200 件、vector も (述語後件数次第で) 200 件で頭打ちになり得る。

---

## E. MMR 初手 tie-break・適用除外拡大 (05 §1.4) [確認済み — 現状固定]

### PC18 [確認済み] MMR 初手は similarity=0 相当・embedding 欠落 1 件でも hybrid 全体で MMR 非適用 [P1]
- 正本: 05 §1.4 L149-150 (『selected = ∅ の初手は similarity 項を 0 とする (= relevance 最高の候補を
  既定 tie-break 順で選ぶ — 実装間で初手が揺れない)』) / L156 (『hybrid の候補プールに embedding
  未付与、または profile 非互換で cosine を計算できない chunk が 1 件でも混在する場合... も MMR は
  適用しない — pairwise similarity が全対で計算できないため。dedup のみ適用し RRF 順で返す』)
- 前提: (a) hybrid 検索、候補 4 件全て embedding あり (通常 MMR 適用ケース)。(b) 同じ 4 件のうち
  1 件だけ embedding が無い (部分 enrichment シナリオ)。
- 操作: `diversify_candidates` (kcs-search/src/mmr.rs) を両ケースで実行する。
- 期待: (a) 初回選択は `selected` 空集合のため diversity_penalty=0 として relevance 最高 (かつ
  同点なら候補順) を選ぶ。(b) 1 件でも `embedding=None` があれば MMR 自体を適用せず、
  `max_per_raw_hash` dedup のみ RRF 順に適用する。**確認**: `mmr.rs::diversify_candidates`
  (L64-73) の `candidates.iter().any(|c| c.embedding.is_none())` 判定と、`mmr_order`
  (L104-131) の `selected` 空時 `fold(0.0, f64::max)` が空 iterator に対して初期値 0.0 を返す
  構造により、両条件とも実装済み (既存テスト `ct3_mmr_005_text_only_keeps_rrf_order` が変更なく
  通ることを回帰の下限として維持する)。

---

## F. cursor 拡張 — index_generation・chunking_config_hash 定義変更・query vector 再利用 (05 §1.5)

### PC19 ScopeCursor へ index_generation (ULID) フィールドを追加する (schema) [P0]
- 正本: 05 §1.5 L178-180 (『scope ごとの sub-cursor は {scope_id, snapshot_commit,
  index_generation, max_rowid, max_association_rowid, chunking_config_hash, consumed}』)
- 前提: `ScopeCursor` (`crates/kcs-search/src/cursor.rs` L29-38) の現行フィールド集合。
- 操作: cursor 発行ルーチンで page 1 の `ScopeCursor` を構築する。
- 期待: `index_generation: String` (ULID 文字列) フィールドを含む。`CursorToken::validate_contract`
  (cursor.rs L72-149) が当該フィールドの必須性・非空性を検証する。**現状**: `ScopeCursor` struct
  (cursor.rs L29-38) に `index_generation` フィールドが存在しない (`#[serde(deny_unknown_fields)]`
  のため追加なしにこの field を含む cursor JSON は decode エラーになる — 純粋な追加が必要)。

### PC20 index_generation は列挙された 6 契機のいずれでも新規採番し、同一 SQLite Tx で回転する [P0]
- 正本: 05 §1.5 L180-184 (『rebuild (kcs repair --rebuild-db)・purge・embedding enrichment の
  finalize・index / batch finalize で chunk_fts の内容が変化した場合・tombstone lifecycle の更新...・
  および GC の shallow 化実行... の、いずれでも新規採番する ULID』) / L188 (『回転はそれを引き起こした
  SQLite 書込... と同一の SQLite Tx で行う』)
- 前提: `index_metadata` 表 (04 §4.1) に既存の `index_generation` 値が記録されている scope。
- 操作: パラメタ化: (a) `kcs repair --rebuild-db`、(b) `kcs purge --raw-hash X`、(c) embedding
  enrichment のバッチ finalize、(d) `kcs index` の chunk_fts 変化を伴う再インデックス、(e) tombstone
  の retire (lifecycle event append)、(f) GC の shallow 化実行 (Phase 4+ 実装後) — の 6 通りをそれぞれ
  単独発生させる。
- 期待: (a)-(f) いずれの後も `index_metadata.index_generation` が新しい ULID に変わっている
  (単調カウンタではなく ULID であることも確認 — 値の形式検証)。当該書込を行う SQLite Tx がコミットする
  のと**同一 Tx** で回転していること (Tx 途中で kill してロールバックされた場合、旧 generation の
  ままであることを別途確認)。**現状**: `index_generation` という概念自体が `index_metadata` 表
  (kcs-index/src/fts.rs) に存在しない。近い機構として `last_lifecycle_epoch` (tombstone lifecycle
  専用、main.rs L2358-2367 で比較・除外にのみ使用) はあるが、rebuild/purge/embedding
  finalize/GC-shallow の 4 契機には一切連動しない。

### PC21 index_generation 不一致の cursor replay は KCS-E-SEARCH-CURSOR-001 で拒否する [P0]
- 正本: 05 §1.5 L188-191 (『replay 時に現在値と不一致なら KCS-E-SEARCH-CURSOR-001 で拒否する
  (再検索が正) — rebuild は rowid を再採番し、purge は append-only 前提を破って行を削除し、後発
  embedding は hybrid の候補集合・順位を変えるため、いずれも旧 cursor の max_rowid / consumed の
  意味を失わせる』)
- 前提: page 1 発行後、cursor に埋め込まれた `index_generation` と異なる値になるイベント (PC20 の
  いずれか) が発生した状態で page 2 を replay する。
- 操作: `kcs search "<query>" --cursor <token>` を実行する。
- 期待: `KCS-E-SEARCH-CURSOR-001` (exit 2) で拒否し、`context.reason` に不一致の事実を示す
  (例 `"index_generation_mismatch"`)。**現状**: フィールド自体が無い (PC19) ため、この検査経路も
  存在しない。

### PC22 chunking_config_hash の cursor 定義変更: 現在値 → page 1 で検索対象にした tree の値 [P0]
- 正本: 05 §1.5 L200 (『chunking_config_hash: page 1 で検索対象にした tree の config (デフォルト =
  当該 scope の HEAD tree の値... 、時点指定 = 対象 tree の値 — §1.6)。replay 時の対象値と不一致なら
  拒否する』)
- 前提: page 1 を `--at Ca` (過去 commit、chunking_config_hash = `H_old`) で実行した後、HEAD の
  現在の chunking config を `H_new` (`H_new != H_old`) へ変更する (`.kcs/config.toml` の
  `[chunking]` を書き換えて `kcs index` を再実行)。
- 操作: page 1 発行後、`--cursor <token>` (selector は自動継承で `--at Ca` のまま) で page 2 を
  replay する。
- 期待: page 2 の比較対象は「`--at Ca` という対象 tree の config 値 `H_old`」であり、HEAD の現在値
  `H_new` とは無関係 — 一致するため cursor は正常に continue する。**現状**:
  `search_one_scope_inner` (main.rs L2465-2467) は選択セレクタに関わらず常に
  `read_chunking_config(&repo)` (= config.toml から都度読む「現在値」) を使う — `--at` 時にも
  対象 tree の config ではなく HEAD 現在の config.toml 値を使うため、上記シナリオでは page 2 の
  比較値が `H_new` になり、page 1 発行時の (誤って現在値ベースで記録された) `H_old` と食い違って
  誤って cursor 拒否になる、または偶然両方とも現在値ベースで一致してしまい `--at` の tree 分離
  という設計意図自体が反映されない (どちらの経路でも「page 1 で検索対象にした tree の config」を
  読んでいないという構造的な誤りは同一)。

### PC23 page 2 以降の比較は「対象時点の値」の再計算であり「current との比較」ではない [P0]
- 正本: 05 §1.8 L463-465 (『chunking_config_hash は page 1 の当該 scope の対象 config
  (デフォルト = 当該 scope の HEAD tree の値... 、時点指定 = 対象 tree の値... )、consumed は
  当該 scope から既に返した件数。page 2 で対象 config の mapping (保存値と再計算値の比較 —
  current ではなく対象時点の値) が 1 件でも違えば query hash mismatch として cursor を拒否する』)
- 前提: PC22 と同一シナリオ (`--at Ca`)。
- 操作: page 2 replay 時の `query_hash` 再計算ルーチンを直接検証する (`chunking_configs` 配列の
  値を追跡する)。
- 期待: 再計算に使う値は「`Ca` という対象 tree の chunking_config_hash」であり、HEAD の現在値では
  ない。**現状**: PC22 と同根 — `read_chunking_config(repo)` は tree 引数を取らず常に現在値を返す
  (main.rs L4335 付近)、`--at` 用の tree 別解決経路が存在しない。

### PC24 query_vector_digest を cursor token の独立フィールドとして保持し query_hash 構成要素にも含める [P0]
- 正本: 05 §1.5 L207 (『そのdigest (= query_vector_digest) を token の独立 field として保持し、
  かつ §1.8 の query_hash 構成要素にも含める (query_hash は一方向 hash であり、replay が読み出す行の
  鍵は token field 側から得る。vector|hybrid のみ — text mode では field 省略)』) / §1.8 L454
  (query_hash 構成要素の列挙内 `query_vector_digest: <実効 mode が vector|hybrid のときのみ...>`)
- 前提: vector|hybrid モードの page 1 検索。
- 操作: 発行される cursor token の JSON 構造、および `QueryHashInput` の構成フィールドを検査する。
- 期待: `CursorToken` に `query_vector_digest: Option<String>` 相当のトップレベルフィールドが
  vector|hybrid のとき非 null で存在する (text mode では省略)。`QueryHashInput` の
  `query_vector_digest` も同様に vector|hybrid のときのみ hash 入力に含まれる。**現状**:
  `CursorToken` (cursor.rs L49-61) にこのフィールドが無く、`QueryHashInput`
  (kcs-search/src/query.rs L102-114) にも同様に無い — grep `"query_vector_digest"` は
  リポジトリ全体で 0 件。

### PC25 vector|hybrid の replay は page 1 の query vector を再利用し再 embedding しない [P0]
- 正本: 05 §1.5 L207 (『vector / hybrid の replay は page 1 の query vector を再利用する — query の
  再 embedding は行わない (provider の非決定性で候補・順位が変わり、consumed の skip が重複・欠落を
  生む)。page 1 の正規化済み query vector は参加各 scope の embeddings 表 (target_type='query_cache'
  ... 。query 本文は保存しない) に保持し、その digest... を... 保持する』)
- 前提: vector|hybrid の page 1 を実行済み (query vector が `embeddings` 表に `query_cache` として
  保持されている想定)。embedding adapter を「毎回異なるベクトルを返すモック」に差し替える (provider
  非決定性を模擬)。
- 操作: `--cursor <token>` で page 2 を replay する。
- 期待: page 2 は embedding adapter を**呼び出さない** (モックが 2 回目に呼ばれないことを確認)。
  page 1 で保存済みの query vector を `embeddings(target_type='query_cache')` から読み出して
  vector 検索に使う。**現状**: `EmbeddingTargetType::QueryCache` (kcs-index/src/embedding_store.rs
  L585) は文字列変換の実装が 1 箇所あるのみで、書込・読出のいずれの経路も存在しない (grep
  `"QueryCache"` = リポジトリ全体で 1 件のみ)。`compute_query_embedding` (main.rs L9535-)
  はカーソル replay (page 2+) でも**毎回無条件に再 embedding を呼ぶ**
  (コメント L9530-9534 が「cursor-driven page 2+ replay... does not participate in the device row
  protocol」と明言しており、re-embedding 自体を行っている設計であることが確認できる)。

### PC26 読み出した query vector 行は sha256 を target_id と再照合し、不一致は削除 + CURSOR-001 [P1]
- 正本: 05 §1.5 L207 (『読み出した行は vector BLOB の sha256 を target_id (= query_vector_digest) と
  再照合する — 不一致は corruption として当該行を削除し、同じく KCS-E-SEARCH-CURSOR-001... ただし
  kcs_format_version が自己の対応上限より新しい scope では削除を行わず CURSOR-001 へ短絡する
  (書込ゼロ規範)』)
- 前提: (a) `query_cache` 行の vector BLOB が破損 (sha256 が target_id と不一致)。(b) 同じ破損だが
  当該 scope の `kcs_format_version` が自己の対応上限より新しい。
- 操作: PC25 の replay 経路でこの行を読み出す。
- 期待: (a) 行を削除した上で `KCS-E-SEARCH-CURSOR-001` を返す。(b) 行を**削除せず** (書込ゼロ)
  `KCS-E-SEARCH-CURSOR-001` へ短絡する。**現状**: PC25 が未実装のため読み出し自体が発生せず、
  この検証・削除ロジックも存在しない。

### PC27 text mode では query_vector_digest フィールドを省略する [P2]
- 正本: 05 §1.5 L207 (『vector|hybrid のみ — text mode では field 省略』)
- 前提: text モード (`--text` または auto が text へ解決済み) の page 1。
- 操作: 発行される cursor token を検査する。
- 期待: `query_vector_digest` フィールドがトップレベル JSON に存在しない (null ではなく key 自体が
  無い — `#[serde(skip_serializing_if = "Option::is_none")]` 相当)。**現状**: フィールド自体が
  存在しないため型上は「常に省略」だが、PC24 実装後に text mode で誤って出力しないことを回帰として
  固定する契約。

---

## G. --offset 単一実行内限定・ページング継続 (05 §1.5) [確認済み — 現状固定]

### PC28 [確認済み] --offset は vector|hybrid で単一実行内 slice、終端判定は alias 展開後 final stream 末尾 [P1]
- 正本: 05 §1.5 L209 (『--offset は cursor の糖衣であり、同じ再現規則で確定順序の offset 位置から
  limit 件を返す。vector|hybrid の --offset は単一実行内の slice である... 終端判定は alias 展開後の
  final result stream の末尾 — それを超えたら next_cursor: null (--all-history / --since で候補
  プール末尾を終端にすると最後の alias group を取り残す)』)
- 前提: `--all-history` + `--offset` で、末尾が 1 つの alias group (複数 path を持つ chunk) に
  かかる件数を指定する。
- 操作: `kcs search "<query>" --all-history --offset <N> --limit <M> --json` を実行し、
  `next_cursor` の有無を確認する。
- 期待: `next_cursor` の有無判定は `slice_end < expanded.len()` (alias 展開後の final stream 長)
  であり、alias group の途中で打ち切られない。**確認**: main.rs L1972-1984
  (`total_skip`/`slice_start`/`slice_end` は `expanded` = alias 展開後の最終 stream に対して計算)、
  L2000 (`next_cursor` 判定 `slice_end < expanded.len()`) が spec 要求と一致することを既存実装で
  確認済み。回帰確認のみを目的とした契約として固定する。

### PC29 [確認済み] page 2 以降は global merge/MMR/alias 展開後の最終 stream 上で scope ごと consumed を skip [P1]
- 正本: 05 §1.8 L478 (『次ページは各 scope を snapshot_commit に固定して再クエリし、cross-scope
  merge → global MMR → alias 展開まで再計算した最終 stream 上で scope ごとの consumed 件を skip して
  継続する (per-scope の事前 skip は global 選択を変えるため行わない)』)
- 前提: multi-scope (S1, S2) の page 1 発行済み cursor で page 2 を replay する。S1 の consumed=3,
  S2 の consumed=5。
- 操作: `kcs search "<query>" --cursor <token>` を実行する。
- 期待: 各 scope を再クエリした後、cross-scope merge → diversify → alias 展開までを再計算した
  **最終 stream** に対して、S1 由来 hit を 3 件、S2 由来 hit を 5 件 skip してから limit 件を返す
  (scope ごとの事前 SQL LIMIT OFFSET ではない)。**確認**: main.rs L1972-2040 の
  `total_skip = cursor.scopes.iter().map(consumed).sum()` は per-scope 値を合算した上で
  `expanded` (最終 stream) に対して 1 回だけ slice する構造であり、per-scope 事前 skip ではない
  ことを確認済み。回帰確認のみを目的とした契約として固定する。

---

## H. `--at --vector` の error 化・共通フィルタの対象 tree 化 (05 §1.6)

### PC30 [確認済み] --vector 明示 + 非互換は fail_behavior に依らず error [P1]
- 正本: 05 §1.6 L215-218 (『--at <commit> --vector: 指定時点の embedding profile が現在と互換なら
  OK、非互換なら KCS-E-SEARCH-VEC-INCOMPAT-001 (--vector 明示時は fail_behavior に依らず error —
  §1.2 と同じ。text への fallback は auto / --hybrid のみ)』)
- 前提: `[search].fail_behavior = "fallback"` (デフォルト)。`--at <commit> --vector` で対象時点の
  embedding profile が現在と非互換。
- 操作: `kcs search "<query>" --at <commit> --vector` を実行する。
- 期待: fail_behavior 設定に関わらず `KCS-E-SEARCH-VEC-INCOMPAT-001` で error (exit 1)。**確認**:
  `resolve_search_mode` (main.rs L1247-1262) の `SearchMode::Vector` 分岐は fail_behavior を
  一切参照せず、非互換なら常に `vector_unavailable_error()` を返す構造であることを確認済み — この
  部分は新旧 spec で変わらず適合。回帰確認のみを目的とした契約として固定する。

### PC31 共通フィルタの chunking_config_hash を「対象 tree の値」に変更する (現状=常に現在値) [P0]
- 正本: 05 §1.6 L237-239 (『共通フィルタ: chunk_config_generations に対象 tree の
  chunking_config_hash の association がある chunk のみ (デフォルト = HEAD tree = 現行値。--at は
  対象 tree の値、--all-history / --include-deleted は各 binding tree の値で判定する』)
- 前提: PC22 と同一シナリオの単純版 — `--at Ca` (config = `H_old`) 検索、現在の config.toml は
  `H_new`。
- 操作: `kcs search "<query>" --at Ca --text` を実行する。
- 期待: `chunk_config_generations.chunking_config_hash = H_old` の association を持つ chunk のみを
  対象とする (現在値 `H_new` との照合ではない)。**現状**: `search_one_scope_inner` L2465-2467/L2492
  (fts_scope_search 呼出時の `chunking_config_hash` 引数) が常に `read_chunking_config(&repo)`
  (現在値) を渡す — PC22 の cursor 面と同じ根本原因が bare 検索本体の対象 chunk 集合そのものを
  誤らせている (これは cursor の整合性問題ではなく、`--at` 検索が過去 config で chunk 化された
  chunk を正しく返せているかどうかの**検索結果そのものの正しさ**の問題)。

### PC32 config 未記録 v1 tree は ancestor-or-equal introduction の byte 順最小を決定的に代用する [P0]
- 正本: 05 §1.6 L239 (『v1 tree は config 未記録のため現行値で代替し結果に注記 (現行値の association
  が無い場合は、対象 commit の ancestor-or-equal な introduction を持つ association (cursor 継続時は
  max_association_rowid 以下も条件) に限定した上で chunking_config_hash の byte 順最小を決定的に
  代用する — 後発 association で代用値が時間変動しない。候補 0 件は注記つき空集合。HEAD 限定再 chunk
  後の履歴 instance を --at で全脱落させない）』)
- 前提: `--at Cv1` (config association が一切無い v1 tree 由来 commit)。当該 chunk には
  `chunking_config_hash = Hx` (introduction_commit = Ca, ancestor of Cv1) と `Hy`
  (introduction_commit = Cb, ancestor of Cv1) の 2 association があり、`Hx < Hy` (byte 順)。
- 操作: `kcs search "<query>" --at Cv1 --text` を実行する。
- 期待: `Hx` (byte 順最小) を決定的に代用して対象とする。association が 0 件の場合は空集合を返し、
  応答に注記 (`fallback_reason` 相当のフィールド) を付す。**現状**: v1 tree 用の代用ロジックは
  grep 0 件 — 未実装 (U69 のこの部分は「部分」ではなく実質「未実装」)。

### PC33 --all-history / --include-deleted は各 binding tree ごとの config 値で判定する [P0]
- 正本: 05 §1.6 L238 (『--all-history / --include-deleted は各 binding tree の値で判定する』)
- 前提: `--all-history` 検索で、binding A (commit Ca, config `Hx`) と binding B (commit Cb, config
  `Hy`, `Hx != Hy`) が同一検索に含まれる。
- 操作: `kcs search "<query>" --all-history --text` を実行する。
- 期待: binding A は `Hx` で、binding B は `Hy` でそれぞれ独立に config フィルタを適用する (単一の
  グローバル値ではない)。**現状**: `fts_scope_search`/`vector_scope_search` は呼出全体で単一の
  `chunking_config_hash: &str` パラメータしか受け取らない構造 (main.rs L2797-2800,
  L2651-2657) であり、binding 単位での config 値切替えという概念が存在しない (PC31 と同根の
  「単一 scope 呼出=単一 config 値」という設計前提そのものが新方針と整合しない)。

---

## I. HEAD 不在 scope の取り扱い (05 §1.6 / 02-philosophy.md §11)

### PC34 単独 scope + HEAD 不在 (bare モード) は KCS-E-INDEX-REBUILDING-001 / exit 3、cursor 発行なし [P0]
- 正本: 05 §1.6 L241 (『HEAD 不在 (初回 auto snapshot 前・snapshot finalize 未完) の scope は index
  未完了として扱う — 検索は当該 scope を KCS-E-INDEX-REBUILDING-001 で excluded_scopes に計上し
  (単独 scope なら exit 3)、cursor は発行しない』)
- 前提: `.kcs init` 直後、`kcs index` 未実行 (HEAD ref 不在) の単独 scope。`--scope .` で
  bare (--at なし) 検索。
- 操作: `kcs search "<query>" --scope .` を実行する。
- 期待: `KCS-E-INDEX-REBUILDING-001` (exit 3)、`next_cursor` は発行されない。**現状**:
  `search_one_scope_inner` L2316-2319 は HEAD 不在を `ScopeSearchError::Excluded("not_indexed")`
  として返し、この理由は `history_plan_error`/exit 分割ロジック (main.rs L1748-1891) のどの
  特別分岐にも該当せず、汎用 `scope_all_failed_error` (`KCS-E-SEARCH-SCOPE-ALL-FAILED-001`,
  **exit 4**) に落ちる (L1887-1890) — spec が要求する exit 3 / INDEX-REBUILDING-001 とは
  code・exit 両方が異なる。

### PC35 明示 commit・Evidence Pointer 指定・単一 scope の `--at` は HEAD 非依存に解決する [P1]
- 正本: 05 §1.6 L241 (『この扱いは bare (--at なし) の現在状態検索など HEAD 依存の解決経路に限る —
  明示 commit・Evidence Pointer 指定の読取・検証 (単一 scope の search --at <commit> を含む) は
  HEAD 非依存に解決する』)
- 前提: PC34 と同一 scope (HEAD 不在) だが、当該 scope に手動 commit `Ca` が存在する
  (HEAD ref だけが未設定、または壊れている状態を人工的に作る)。
- 操作: `kcs search "<query>" --at Ca --scope .` を実行する。
- 期待: HEAD 不在でも `Ca` を対象に検索が成立する (`not_indexed`/`INDEX-REBUILDING` 除外の対象に
  ならない)。**現状**: `search_one_scope_inner` L2303-2321 は `time.selector.at()` が `Some` の
  場合 `repo.resolve_commit(operand)` を直接呼び、HEAD 参照 (`head_commit_hash()`) を経由しない
  構造になっている — この部分は**既に**「HEAD 非依存」という設計と一致しているため、本契約は
  「確認済み・回帰させない」を目的とする (PC34 の修正 (not_indexed → INDEX-REBUILDING) が、この
  `--at` 分岐の独立性を壊さないことを結合テストとして固定する)。

### PC36 multi-scope 中の一部 scope のみ HEAD 不在: 健全 scope の結果を返し正しい理由で partial (exit 3) [P0]
- 正本: 05 §1.6 L241 (前掲) + 05 §1.8 部分失敗表 (L404-408、『一部 scope 失敗... 結果を返し
  excluded_scopes に記録 exit 3』)
- 前提: multi-scope 検索 (S1: HEAD あり・indexed、S2: HEAD 不在)。
- 操作: `kcs search "<query>"` (デフォルト全 scope) を実行する。
- 期待: S1 の結果を返し、`excluded_scopes` に `{scope_id: S2, reason: "index_rebuilding"}`
  (またはそれに相当する専用 reason) を記録、exit 3。**現状**: `not_indexed` reason
  (main.rs L2319) は `store_corruption_recovery_hint`/`index_unusable`/`store_corruption` の
  いずれの特別分類にも該当しないため partial 時は単に `excluded_scopes` に
  `reason: "not_indexed"` として記録されるのみ (exit 3 自体は一部成功なので現状でも 3 になる可能性が
  高いが、reason の分類語が spec の要求する "index_rebuilding" 系ではなく、全 scope 失敗時の昇格判定
  (PC55/PC56) にも組み込まれていない — PC34 が単独ケースの exit を直接破っているのに対し、
  こちらは reason の分類とレスポンス表現の正確性の問題)。

---

## J. 検索の時点条件正式化 — introduction ancestor-or-equal・correlated EXISTS (05 §1.6)

### PC37 chunk_publications 表を新設し、初回を含む全 introduction を追記する [P0]
- 正本: 05 §1.6 L265 (『auto snapshot 作成時に新規 chunk 行へ first_seen_commit を刻み、
  chunk_publications へ (chunk_id, introduction_commit = 当該 commit) を追記する (既存
  publication のいずれの子孫でもない tree に同一 chunk が現れた場合も、新しい introduction として
  追記 — 04-pipeline.md §4.1)。新規の config association も同じ commit を introduction_commit として
  刻む』)
- 前提: 新規 chunk (raw_hash=Ra) が auto snapshot 作成時に commit `Ca` で初めて公開される。
- 操作: `kcs index` (auto snapshot 経路) を実行する。
- 期待: `chunks` 行に `first_seen_commit=Ca` が刻まれると同時に、`chunk_publications` へ
  `(chunk_id, introduction_commit=Ca)` の行が追記される。**現状**: `chunk_publications` 表は
  DDL・grep 双方で 0 件 (`chunks.first_seen_commit` (kcs-index/src/rows.rs L20) が単一列として
  唯一の記録)。

### PC38 デフォルト/--at の対象は「chunk_publications のいずれかの introduction_commit が対象 commit の
ancestor-or-equal である chunk」に限る — 現状は publish 済みなら時点非依存で無条件ヒット [P0]
- 正本: 05 §1.6 L266 (『時点条件 (正式化): デフォルト / --at の対象は、上記 join に加えて
  chunk_publications のいずれかの introduction_commit が対象 commit の ancestor-or-equal である
  chunk に限る (単一の first_seen_commit では incomparable な複数導入... を表現できないため...)』)
- 前提: raw_hash=Ra が commit `Ca` (root) の tree に存在するが、実際に chunk 化・公開されたのは
  その子孫 commit `Cb` (`Ca` → `Cb`) の auto snapshot 時点 (`chunk_publications.introduction_commit
  = Cb` のみ、`Ca` 時点ではまだ chunk 化されていなかった、という同一 raw_hash が commit 間で
  chunking 未完了だった実運用シナリオを模擬)。
- 操作: `kcs search "<query>" --at Ca --text` を実行する (`Ca` は `Cb` の祖先で、`Cb` 自身は
  対象外)。
- 期待: 当該 chunk は `--at Ca` の結果に**含まれない** (`introduction_commit=Cb` は `Ca` の
  ancestor-or-equal ではない — `Cb` は `Ca` の子孫)。**現状**: `fetch_live_meta`/`execute_fts_tier`
  (main.rs L2726, L2842) の条件は `c.first_seen_commit IS NOT NULL` のみであり、`--at` の対象
  commit との ancestor 関係を一切見ない — `kcs_eligible_identity` 一時表 (PC39 参照) が
  `(raw_hash, tool_profile_hash, gen)` の**存在**のみで判定するため、上記シナリオでは誤って
  ヒットする。

### PC39 回帰実証: 子孫 commit でのみ introduce された chunk が祖先 --at 検索に漏れ出る現状バグ [P0]
- 正本: PC38 と同一 (05 §1.6 L266)。本契約は「現状の具体的な誤挙動」を機械検証可能な形で固定する
  回帰実証契約。
- 前提: PC38 と同一シナリオ。加えて `Ca` の tree_entries には該当 raw_hash のエントリが
  `normalize` 済みで存在する (`search_history.rs::plan_search_history` の `TimeSelector::At`
  分岐が `entry.normalize.is_some()` のみを条件に `SearchContentKey` を作る、main.rs L216-224
  相当のロジック)。
- 操作: `kcs search "<content-specific-token>" --at Ca --text --json` を実行する。
- 期待 (PC38 実装後): `results` は空 (0 件)。**現状の実測期待 (回帰の可視化)**: `results` に該当
  chunk が**含まれてしまう** — `install_eligible_identities` (search_history.rs L169-196) が
  tree の `normalize` 存在のみを鍵に `kcs_eligible_identity` を構築し、`fetch_live_meta` 等が
  `first_seen_commit IS NOT NULL` の bare 条件と AND するだけなので、`Cb` 時点で公開された chunk が
  `Ca` 時点の検索にも紛れ込む。本契約は PC38 の fix 前後で assert を反転させる形で保持し、fix の
  「開けた穴」再発防止 (根拠 grep 必須の教訓) に用いる。

### PC40 chunk_config_generations へ introduction_commit 列を追加し、同条件を適用する [P0]
- 正本: 05 §1.6 L266 (『config association にも同条件を適用する — chunk_config_generations の
  introduction_commit が対象 commit の ancestor-or-equal であること (再 chunk 完了前の時点へ後発
  association が遡及出現することを防ぐ)』)
- 前提: chunk `chunk_a` の config association が commit `Cc` (`introduction_commit=Cc`) で追加された
  (chunking config 変更後の再 chunk による後発 association)。`Cc` の祖先 `Ca` で検索する。
- 操作: `kcs search "<query>" --at Ca --text` を実行する。
- 期待: この config association は `Ca` の時点ではまだ存在しない (`Cc` は `Ca` の子孫) ため、
  当該 association 経由での chunk ヒットは成立しない。**現状**: `chunk_config_generations`
  DDL (kcs-index/src/fts.rs L521-527, L725-731) の列は `association_rowid, chunk_id,
  chunking_config_hash, created_at` の 4 列のみ — `introduction_commit` 列が存在しない
  (`association_rowid <= max_association_rowid` という rowid 順序による近似はあるが、これは
  「cursor 発行後に増えた行を除く」ための境界であり、「commit 祖先関係」とは別軸)。

### PC41 実装規範: correlated EXISTS で評価する (素の JOIN 禁止) [P0]
- 正本: 05 §1.6 L243-246 (『実装規範: publication / association の時点条件は correlated EXISTS
  (ancestry 判定と association_rowid <= cursor.max_association_rowid を副問い合わせ内に含む) で
  評価する — 同一 (chunk_id, config) の複数 introduction 行を素の JOIN で結合すると同一 chunk が
  重複 hit し、candidate / rank / cursor を歪める』)
- 前提: chunk `chunk_a` が 2 つの独立 introduction (`introduction_commit=Cleft` と `=Cright`、
  ともに merge commit `Cm` の祖先) を持つ (PC43 のマージシナリオ)。
- 操作: `--at Cm` で検索した際に生成される SQL を検査する (`EXPLAIN QUERY PLAN` および実行結果の
  重複有無)。
- 期待: `chunk_a` は結果に**1 回だけ**現れる (correlated EXISTS による判定であり、2 introduction
  行との JOIN によるファンアウトが起きない)。**現状**: `chunk_publications` 自体が存在しないため
  (PC37)、この重複パターンは現在発生し得ない (単一 first_seen_commit だから) が、それは
  「多重introductionをそもそも表現できていない」ことの裏返しであり、PC37-40 実装後に素の JOIN で
  実装すると新たにこの重複バグが生じ得る — 実装時に本契約で明示的に固定する。

### PC42 候補集合は ranking 前に (scope_id, chunk_id) で一意化する [P0]
- 正本: 05 §1.6 L246 (『候補集合は ranking 前に (scope_id, chunk_id) で一意にする』)
- 前提: PC41 と同一の多重 introduction シナリオ。
- 操作: RRF 融合前の候補リスト (`fts_scope_search`/`vector_scope_search` の戻り値) を検査する。
- 期待: 同一 `(scope_id, chunk_id)` の重複が RRF 入力に渡らない (PC41 の EXISTS 実装が正しくても、
  防御的な一意化ステップとして明示的に存在する)。**現状**: 同上 (PC37 未実装のため重複の入力元が
  無く、対応する一意化ステップも存在しない)。

### PC43 merge 側枝の独立 import: 複数 incomparable introduction のいずれかが ancestor-or-equal なら適格 [P0]
- 正本: 05 §1.6 L266 (『単一の first_seen_commit では incomparable な複数導入 — merge の側枝・独立
  import — を表現できない』引用は PC38 と同一パラグラフ。具体シナリオは 05 §1.7 L346-348 の
  introduction 定義 (『「その commit に binding が存在し、利用可能な全 parent に存在しない」commit』)
  と対応する構造)
- 前提: root commit `C0` → 左枝 `Cleft`・右枝 `Cright` (共通祖先 `C0`) → merge `Cm`。同一 raw_hash
  の chunk が `Cleft` と `Cright` の双方で**独立に** (互いに祖先子孫関係なく) 導入されている
  (`chunk_publications` に `introduction_commit=Cleft` と `=Cright` の 2 行)。
- 操作: (a) `--at Cleft` で検索。(b) `--at Cright` で検索。(c) `--at Cm` で検索。
- 期待: (a) は `introduction_commit=Cleft` が ancestor-or-equal (自分自身) のため適格。(b) は
  `=Cright` が適格。(c) は 2 introduction のうち**いずれか**が `Cm` の ancestor-or-equal であれば
  (両方とも該当する) 適格 — chunk は 1 回だけヒットする (PC42 の一意化)。**現状**: 多重
  introduction のモデル自体が無いため、この枝分かれシナリオを表現できない (PC37 と同根)。

### PC44 --include-deleted の補完 binding にも同条件を適用する [P1]
- 正本: 05 §1.6 L266 (『--include-deleted の補完 binding にも同条件を適用する (introduction が
  当該 binding commit の ancestor-or-equal であること — 削除後に完了した後着 chunk の遡及混入を
  排除)』)
- 前提: `--include-deleted` の補完 binding (削除済みファイルの最終版、pointer_commit=`Cdel`) が
  指す chunk の `introduction_commit` が `Cdel` の**子孫** (削除後に完了した非同期 chunk 化) である
  シナリオ。
- 操作: `kcs search "<query>" --include-deleted --text` を実行する。
- 期待: 当該 chunk は `--include-deleted` の補完結果に**含まれない** (introduction が binding
  commit の祖先でも自分自身でもないため)。**現状**: PC37-38 と同根で未実装。

---

## K. shallow 化 commit の walk skip 可視化 (05 §1.6 / §2.2)

### PC45 --all-history 等の walk 中に shallow 祖先へ遭遇 → skip して継続 + shallow_skipped 計上 + partial (exit 3) — 現状は command 全体を即時 hard-fail [P0]
- 正本: 05 §1.6 L263-264 (『walk 中の shallow 化済み commit (tree 破棄済み) は skip し、レスポンスに
  shallow_skipped 件数を可視化して partial (exit 3) とする — 黙って欠落させない』)
- 前提: multi-scope 検索 (S1, S2)。S1 の `--all-history` walk 対象 DAG の一部祖先 commit が
  shallow 化済み (tree 破棄) だが、S1 の walk 対象には**到達可能な非 shallow commit も存在する**
  (walk 全体が shallow なわけではない)。S2 は健全。
- 操作: `kcs search "<query>" --all-history` を実行する。
- 期待: S1 の walk は shallow 祖先を skip して継続し、到達可能な非 shallow 部分の結果は返る。
  応答全体は S1・S2 双方の結果を含み、`shallow_skipped` (S1 分) を可視化した上で **exit 3**
  (S1 が完全ではないため partial)。**現状**: `HistoryReader::read_required`
  (kcs-core/src/history.rs L507-520) は shallow/missing object に遭遇した瞬間
  `history_shallow_error` (`KCS-E-COMMIT-SHALLOW-001`) を `Err` として即座に伝播し、
  `history_plan_error` (main.rs L2182-2190) がこれを無条件に `ScopeSearchError::Shallow` へ
  写像する。呼出元ループ (main.rs L1679-1689) は `ScopeSearchError::Shallow` を受け取ると
  **`run_search_inner` 関数全体を即座に `return Err(...)` で終了させる** — S1 だけでなく **S2 の
  既に計算済みの健全な結果も含め、multi-scope 検索コマンド全体**が
  `KCS-E-COMMIT-SHALLOW-001` (exit 1) で失敗する。コメント (main.rs L1680-1682) は「Only
  reachable on the cursor path」と主張するが、`TimeSelector::AllHistory` 等のフレッシュ
  (非 cursor) 経路 (main.rs L2402-2405, `history_plan_error(error, exec.from_cursor)` の
  `from_cursor` 引数は SHALLOW 分岐では使われない) からも到達することを PC47 で確認する — 影響範囲は
  spec-gap の記述 (「scope 全体を除外/失敗させる」) よりも広く、**multi-scope 検索コマンド全体**が
  巻き込まれる。

### PC46 shallow_skipped 件数のレスポンス可視化 [P1]
- 正本: PC45 と同一引用 (05 §1.6 L263-264)。
- 前提: PC45 の fix 後の状態。S1 の walk で 2 件の shallow 祖先を skip した。
- 操作: `kcs search "<query>" --all-history --json` を実行する。
- 期待: レスポンス JSON に `shallow_skipped` (数値、または `searched_scopes[]`/
  `excluded_scopes[]` 相当の per-scope 内訳を持つ構造) が S1 について `2` を示す。
  **[解釈割れ]** 集計の置き場所 (トップレベル合算 か per-scope 内訳か) は §Q note-3 参照。
  **現状**: フィールド自体が grep 0 件 (未実装)。

### PC47 [確認済み境界] cursor replay で snapshot_commit 自体が shallow の場合は引き続き command 全体を hard-fail する [P1]
- 正本: 05 §2.2 L541-542 (『kcs search --at <shallow-commit> と、shallow 化 commit を snapshot と
  する cursor の再計算も KCS-E-COMMIT-SHALLOW-001 で失敗する (tree 全体を要するため)』) / 05 §1.8
  L479 (『cursor 中の snapshot_commit が shallow 化済み... の場合、cursor の再計算は
  KCS-E-COMMIT-SHALLOW-001 で失敗する... cursor なしの再検索を案内する』)
- 前提: page 1 発行済み cursor の `snapshot_commit` 自体が (page 1 発行後に) shallow 化された。
- 操作: `--cursor <token>` で page 2 を replay する。
- 期待: **command 全体**が `KCS-E-COMMIT-SHALLOW-001` (exit 1) で hard-fail する (PC45 の
  「skip して継続」規則の対象外 — snapshot_commit そのものが shallow の場合は tree 全体が必要な
  ため代替不能)。**現状**: main.rs L1679-1689 のこの経路は spec と一致 (確認済み)。PC45 の
  fix がこの cursor 経路の hard-fail を壊さないことを結合テストとして固定する (PC45 が「fresh
  --all-history walk の途中祖先」のみを skip-continue に変え、「snapshot_commit 自身の shallow」
  はこの契約の hard-fail のまま残ることの境界確認)。

---

## L. --scope 単独指定・canonical root_path (05 §1.8) [確認済み — 現状固定]

### PC48 [確認済み] --scope 単独指定は完全一致 (registry 前方一致を経由しない直接 open)、--descendants は path-component 境界 [P1]
- 正本: 05 §1.8 L375 (『--scope <path> 単独指定は canonical root_path の完全一致 (当該 scope のみ)。
  --descendants 併用時は self + root_path + '/' を前置に持つ scope を対象とする (path-component
  境界で判定 — 単純な文字列前方一致は /work/a が /work/ab に一致するため用いない)。canonical
  root_path の算出規則: CLI 入力を (1) 絶対化 (cwd 基準)、(2) . / .. の lexical 解決、(3) 末尾
  separator 除去、(4) symlink 解決 (realpath) の順で正規化する。比較は byte 単位』)
- 前提: (a) `--scope /work/a` (単独、`--descendants` なし)。(b) `--scope /work/a --descendants`
  で registry に `/work/a` と `/work/ab` の 2 scope が存在する。
- 操作: (a)(b) それぞれで `kcs search "<query>"` を実行する。
- 期待: (a) `/work/a` の scope のみが対象になる (前方一致で `/work/ab` 等を誤って含めない)。(b)
  `/work/a` (self) と `/work/a/...` 配下のみが対象になり、`/work/ab` は対象外。**確認**: (a) は
  `enumerate_scope_targets` の非 `--descendants` 分岐 (main.rs L5333) が `scope_target(&root)`
  経由で `Repository::open_for_search` (kcs-core/src/scope.rs L315-328) を直接呼び、内部で
  `path.canonicalize()` (絶対化+lexical解決+symlink解決を realpath として一括実行) してから
  当該パス**そのもの**の `.kcs` を開く構造のため、registry 上の前方一致を経由する余地が構造的に
  無く「完全一致」が自明に成立する。(b) は `registry_targets_under`
  (main.rs L5396-5403) が Rust 標準 `Path::starts_with` (path-component 単位の比較で
  `/work/a` と `/work/ab` を混同しない) を用いており適合。回帰確認のみを目的とした契約として
  固定する。

---

## M. multi-scope 実効値解決 (05 §1.8)

### PC49 multi-scope (デフォルト/--all-scopes/--descendants) は `[search]` 実効値に user (device) 層のみを用いる — 現状は常に CWD の folder 値優先 [P0]
- 正本: 05 §1.8 L384-387 (『diversify... は統合後の候補列に対して適用する。multi-scope 検索の
  [search] 実効値 (default_mode / rrf / diversify / candidate_depth / fail_behavior) は user
  config (device 層) を用いる — folder 値は --scope 単一指定時のみ適用する (scope 間で異なる
  folder 値の統合は定義しない』)
- 前提: カレントディレクトリの scope `S_cwd` の `.kcs/config.toml` に
  `[search] default_mode = "text"` が明示設定されている。`~/.config/kcs/config.toml`
  (user/device 層) には `[search] default_mode = "hybrid"`。デフォルト (`--scope` 省略、全 scope
  対象) で検索する。
- 操作: `kcs search "<query>" --json` (CWD = `S_cwd`、`--scope` 省略) を実行する。
- 期待: multi-scope (全 scope 対象) のため、実効 `default_mode` は **user 層の `"hybrid"`**
  (`S_cwd` の folder 値 `"text"` は使われない)。**現状**: `effective_search_config`/
  `effective_search_tuning` (main.rs L5169-5298) は `run_search_inner` の先頭
  (L1395, L1401 — scope 列挙 `enumerate_scope_targets` より**前**) で
  `&repo` (= CWD の `Repository`、つまり `S_cwd` の config.toml) を対象に一度だけ呼ばれ、
  常に `scope値.or(user値)` (folder 優先) で解決する — multi-scope か単一 scope かの分岐が
  一切存在せず、**常に CWD の folder 値が (存在すれば) 最優先**になる。上記シナリオでは
  誤って `"text"` が使われる。

### PC50 単独 `--scope .` (当該 1 scope のみ) は folder 値を適用してよい [P1]
- 正本: PC49 と同一引用 (『folder 値は --scope 単一指定時のみ適用する』)。
- 前提: PC49 と同一 config だが、`--scope .` (単独、`--descendants` なし) を明示する。
- 操作: `kcs search "<query>" --scope . --json` を実行する。
- 期待: `S_cwd` の folder 値 `"text"` が適用される (単独 scope 指定なので folder 値を使ってよい)。
  **現状**: 単独 scope の場合、結果的に `effective_search_config(&repo)` が対象とする scope
  (`S_cwd`) と実行対象 scope が一致するため、**この特定ケースに限っては現状のロジックでも
  正しい値になる** — ただし PC49 のとおり「multi-scope でも同じ folder 値が使われてしまう」という
  一般的な誤りの**部分的な偶然の一致**に過ぎず、`--scope` が他 scope を指す場合
  (`--scope /work/other`) は CWD (`S_cwd`) の folder 値が誤って適用される追加ケースがある
  (`enumerate_scope_targets` が対象 scope を変えても `effective_search_config(&repo)` の
  `repo` は常に CWD のままであるため)。本契約は「`--scope .` で CWD 自身を指す場合」の正しい
  挙動を固定し、`--scope /work/other` (CWD と異なる単独 scope) のケースは PC49 の fix と
  同一の実装変更 (実効値解決の呼出対象を「実行対象 scope」ベースへ切替える) で同時に解消される
  ことを設計メモとして付す。

### PC51 [確認済み] fail_behavior は query_hash / cursor bind の対象外 [P2]
- 正本: 05 §1.8 L388-389 (『ただし fail_behavior は挙動方針であり確定順序に影響しないため
  bind / query_hash preimage の対象外』)
- 前提: 同一 query・同一 scope 集合で `fail_behavior` のみを `"fallback"` → `"warn"` に変更する。
- 操作: 両設定でそれぞれ page 1 を発行し、`query_hash` を比較する。
- 期待: `query_hash` は不変 (fail_behavior の変更だけでは cursor が invalid にならない)。
  **確認**: `QueryHashInput` (kcs-search/src/query.rs L102-114) のフィールド集合に
  `fail_behavior` が含まれないことを確認済み — 回帰確認のみを目的とした契約として固定する。

---

## N. vector 横断条件・全 scope 失敗 exit 分割 (05 §1.6 / §1.8, 06 §7-8)

### PC52 --vector 明示時、一部 scope が profile 非互換なら当該 scope のみ excluded_scopes へ除外する (fallback しない) [P0]
- 正本: 05 §1.8 L390 (『--vector 明示時は fallback しない — profile 不一致の scope を
  KCS-E-SEARCH-VEC-INCOMPAT-001 の excluded_scopes として除外し、全 scope 除外なら error — §1.2 の
  「失敗時は error」と同じ』)
- 前提: multi-scope (S1: profile 互換、S2: profile 非互換)。
- 操作: `kcs search "<query>" --vector` を実行する。
- 期待: S2 のみ `excluded_scopes` (`reason` に `KCS-E-SEARCH-VEC-INCOMPAT-001` 相当を記録) に
  除外し、S1 の vector 結果を返す (exit 3、partial)。**現状**: `resolve_vector_availability`
  (main.rs L1167-1207) は `exec_scopes` 全体を単一ループで走査して**1 つの**
  `VectorAvailability` を返す構造 (`any_incompatible || (any_compatible && any_absent)` の
  時点で全体が `Incompatible` — L1188-1189) — S2 が非互換なら S1 も含めた**検索全体**が
  incompatible 扱いになり、`--vector` 明示時は (PC1 の error 分岐を通って) **検索全体が
  error** になる。per-scope 除外という概念がこの関数の粒度に存在しない (scope 単位でなく
  「検索全体」単位の判定)。

### PC53 kcs_format_version が対応上限より新しい scope は KCS-E-STORE-VERSION-001 で除外し書込ゼロ [P0]
- 正本: 05 §1.8 L390 (『kcs_format_version が自己の対応上限より新しい scope も同様に
  excluded_scopes として除外する (KCS-E-STORE-VERSION-001 を fallback_reason に記録・当該 scope
  へは query_cache を含む一切の書込を行わない — 10-operations.md §12.5)』)
- 前提: multi-scope (S1: 通常, S2: `kcs_format_version` が自己の対応上限より新しい)。
- 操作: `kcs search "<query>" --hybrid` を実行する (S2 は vector page 1 の query_cache 書込対象に
  なり得る状況)。
- 期待: S2 は `KCS-E-STORE-VERSION-001` で `excluded_scopes` へ除外され、S2 の `.kcs` へは
  (query_cache を含め) 一切の書込が発生しない。S1 の結果は返る (exit 3)。**現状**: grep
  `"KCS-E-STORE-VERSION-001"` はリポジトリ全体で 0 件 — `kcs_format_version` の対応上限チェック
  自体が検索経路に存在しない。

### PC54 全 scope が STORE-VERSION 除外なら exit 8 (SCOPE-ALL-FAILED より優先) [P0]
- 正本: 05 §1.8 L390-391 (『全 scope が STORE-VERSION 除外なら command は
  KCS-E-STORE-VERSION-001 / exit 8 を返す (SCOPE-ALL-FAILED (3/4) より優先 — REBUILDING と同型の
  昇格）』) / 06 §7 L330 (`8 incompatible profile / format version`)
- 前提: multi-scope (S1, S2 とも `kcs_format_version` が対応上限より新しい)。
- 操作: `kcs search "<query>"` を実行する。
- 期待: `KCS-E-STORE-VERSION-001` (exit 8) — 汎用 `KCS-E-SEARCH-SCOPE-ALL-FAILED-001` (exit 3/4)
  にならない。**現状**: PC53 が未実装のため、この昇格分岐も存在しない (main.rs L1748-1891 の
  昇格チェック列 `all_purge_journal_active`/`all_rebuilding`/`index_unusable`/
  `store_corruption` のいずれにも STORE-VERSION 相当が無い)。

### PC55 全 scope 同一理由除外の一般昇格規則 (VERSION→8・REBUILDING→3・INCOMPAT→8・journal→3・DUP→3) [P0]
- 正本: 05 §1.8 L391-392 (『全 scope の除外理由が同一 code の場合、command は当該 code とその単独
  実行時の exit を返す (一般規則) — VERSION → exit 8・REBUILDING → exit 3・INCOMPAT → exit 8・
  journal (KCS-E-PURGE-JOURNAL-ACTIVE-001) → exit 3・DUP → exit 3 (ユーザーの dedupe 後に回復可能
  — 08-evidence-pointer-spec.md §4.3 の registry_duplicate = 3 と同一分類)』)
- 前提: パラメタ化。全 scope (S1, S2) が同一理由で除外される 5 パターン: (a) VERSION, (b)
  REBUILDING (既存 `all_rebuilding` 分岐で確認済み — 回帰境界として含める), (c) INCOMPAT
  (`--vector` 明示、全 scope 非互換), (d) journal (`KCS-E-PURGE-JOURNAL-ACTIVE-001`、既存
  `all_purge_journal_active` 分岐で確認済み), (e) DUP (`KCS-E-REGISTRY-DUP-001` 相当、同一
  scope_id の重複 live clone)。
- 操作: 各パターンで `kcs search "<query>"` (該当モード) を実行する。
- 期待: (a)→exit 8, (b)→exit 3 [確認済み], (c)→exit 8, (d)→exit 3 [確認済み], (e)→exit 3。
  **現状**: (b)(d) は main.rs L1756-1786 に既存実装があり適合 (確認済み・回帰対象として含める)。
  (a)(c)(e) は対応する除外理由・昇格分岐が存在しない (PC53, PC52, および DUP 除外自体が検索経路に
  無い — grep `"KCS-E-REGISTRY-DUP-001"` は main.rs で 0 件)。

### PC56 混在理由の優先順位: VERSION → journal → DUP → REBUILDING [P1]
- 正本: 06 §7 L364 (『優先順位は VERSION → journal → DUP → REBUILDING (10 §3)。05 §2.6・08 §3.1』)
- 前提: multi-scope (S1: VERSION 除外理由, S2: REBUILDING 除外理由) — 異なる 2 理由が混在するが、
  優先順位表に載る 2 者。
- 操作: `kcs search "<query>"` を実行する。
- 期待: 優先順位表の並びに従い、**VERSION が REBUILDING より優先**するため、この混在は「同一理由
  昇格」ではなく通常は PC57 の「混在時分割」則が適用されるはずだが、優先順位表の存在は「昇格判定
  そのものを行う前に、複数の同時該当し得る特別理由がある場合にどちらの特別分類を先に評価するか」を
  規定すると解釈する。**[解釈割れ]** VERSION と REBUILDING が異なる scope に混在する場合、
  「優先順位」がどちらの特別 exit (8 or 3) を採用するかを指すのか、それとも判定ロジックの
  評価順序 (どちらのチェックを先に実行するか) だけを指すのかは 06 §7 の文言のみからは断定できない
  — §Q note-4 参照。本契約は「判定順序」解釈を採用し、除外理由が全て VERSION/journal/DUP のいずれか
  (REBUILDING を含まない) の集合について、この優先順位でチェックすることを固定する。**現状**:
  該当する順序判定ロジック自体が存在しない (PC53-55 が前提として未実装)。

### PC57 理由混在の全滅は retryable 系を 1 つでも含めば exit 3、全て permanent なら exit 4 [P0]
- 正本: 05 §1.8 L392 (『理由が混在して全 scope 除外となった場合は通常の SCOPE-ALL-FAILED とし、
  exit は除外理由の retryability で分割する — 単独時 exit 3 の code (REBUILDING・journal・DUP・
  timeout 等の retryable 系) を 1 つでも含めば exit 3、全て permanent 系なら exit 4』) / 06 §7
  L362-363 (『混在は SCOPE-ALL-FAILED — retryable 理由を含めば exit 3・全て permanent なら
  exit 4』)
- 前提: multi-scope 3 scope。(a) S1=REBUILDING (retryable), S2=store_corrupt (permanent),
  S3=timeout (retryable) の混在。(b) S1=store_corrupt, S2=snapshot_shallow の全 permanent 混在
  (既存 `store_corruption` 分岐で確認済みの境界)。
- 操作: 各パターンで `kcs search "<query>"` を実行する。
- 期待: (a) retryable (REBUILDING, timeout) を含むため **exit 3**。(b) 全 permanent のため
  **exit 4** [確認済み — main.rs L1828-1834 の `store_corruption` 集約が該当]。**現状**: (a)
  のような「retryable と permanent が混在」する場合の明示的な分割ロジックが
  `run_search_inner` (main.rs L1748-1891) に存在せず、どの特別集約 (`all_rebuilding`,
  `index_unusable`, `store_corruption`) にも該当しないため最終フォールバックの
  `scope_all_failed_error` (`KCS-E-SEARCH-SCOPE-ALL-FAILED-001`) に落ちるが、その関数
  (main.rs L3335 付近) が retryable/permanent を判別して exit 3/4 を分割しているかは
  未確認 — 少なくとも VERSION/DUP を交えた混在ケースは対応する除外理由自体が無い (PC53, 55(e))
  ため機械的に検証不能。

### PC58 [確認済み] embedding 承認 gate は per-scope 除外条件ではない (承認ゼロ→全体 text fallback、excluded_scopes 不計上) [P1]
- 正本: 05 §1.8 L390 (『embedding 承認の consent gate (§1.1) は送信 gate であり per-scope の除外
  条件ではない — 承認ゼロなら検索全体が text fallback (excluded_scopes には計上しない)』)
- 前提: multi-scope (S1, S2 とも embedding 承認ゼロ)。
- 操作: `kcs search "<query>"` (auto) を実行する。
- 期待: 検索全体が text fallback (`fallback_reason="embedding_not_authorized"`) になり、
  `excluded_scopes` は空 (S1, S2 のどちらも除外理由として計上されない — 両 scope の text 結果は
  通常どおり返る)。**確認**: `embedding_opt_in` (main.rs L1501-1504) は `resolve_vector_availability`
  の入力としてのみ使われ、`excluded_scopes` を構築する per-scope ループ (L1667 以降) には一切
  関与しない構造であることを確認済み — この点は PC4 (OR-vs-AND) の fix 後も変わらず維持される
  べき境界として固定する。

---

## O. `kcs search --at` の multi-scope 制約新設 (06-cli-spec.md §3)

### PC59 `--at` は `--scope` 単一指定を必須とする — `--scope` 省略 (デフォルト全 scope) はエラー [P0]
- 正本: 06 §3 L226-227 (『`kcs search "..." --at <commit> --scope <path>` — --at は --scope
  単一指定を必須とする (独立 DAG の multi-scope に単一 commit は適用不能 — 05 §1.6)』) / 05 §1.6
  統合要約 (spec-gap U77: 『kcs search --at <commit> に --scope 単一指定必須の制約を新設する』)
- 前提: registry に複数 scope が登録されている。
- 操作: `kcs search "<query>" --at <commit>` (`--scope` 省略) を実行する。
- 期待: `KCS-E-CONFIG-USAGE-001` (exit 2、invalid usage) — 「`--at` は `--scope` 単一指定を要する」
  旨のメッセージ。**現状**: `parse_search_args` (main.rs L5012-5141) に `--at` と `scope`/
  `descendants`/`all_scopes` を関連付ける検証が無く、`enumerate_scope_targets` は `--scope` 省略時
  そのまま全 scope を列挙し (main.rs L5340-5346)、各 scope が `--at` の commit をそれぞれ独立に
  解決しようとするだけで usage error にならない (spec-gap の記述どおり)。

### PC60 `--at` + `--scope --descendants` (複数 scope化) もエラー、`--scope` 単一 (descendants なし) のみ許容 [P0]
- 正本: PC59 と同一引用。「単一 commit は独立 DAG の multi-scope に適用不能」という理由は
  `--descendants` で複数 scope になる場合も同じく適用される。
- 前提: (a) `--at <commit> --scope /work/a --descendants` (`/work/a` 配下に複数 scope)。(b)
  `--at <commit> --scope /work/a` (`--descendants` なし、単一 scope)。
- 操作: (a)(b) それぞれ実行する。
- 期待: (a) は `KCS-E-CONFIG-USAGE-001` (exit 2)。(b) は正常に単一 scope へ解決される (PC30 等
  既存の `--at` 単体契約と整合)。**現状**: (a) も (b) と同様に usage error にならず、
  `--descendants` で複数解決された各 scope に対して `--at` がそれぞれ独立に適用される
  (バリデーション自体が存在しないため)。

---

## P. chunking config 変更時の再 chunk/再 embedding 対象を HEAD 参照 instance に限定 (04-pipeline.md §4.6)

### PC61 rebuild の再 chunk/再 association 対象を HEAD tree が参照する normalized instance のみに限定する [P1]
- 正本: `tasks/step4b-spec-gap.md` U145 統合要約 (04 §4.6 由来): 『chunking config 変更検出時の
  再 chunk/再 embedding タスク対象を、旧 spec「全 normalized instance (履歴分含む)」から新 spec
  「HEAD (現行 tree) が参照する normalized instance のみ」へ縮小する。履歴 instance は時点指定検索で
  旧 config のまま参照されるため (H 領域 U69/U71)、新 config での履歴再 chunk はどの tree からも
  到達不能な chunk と embedding 課金を生むだけになる』
- 前提: HEAD tree に `path_a` (raw_hash=Ra) が存在する。過去 commit `Cold` (HEAD の祖先、現在の
  HEAD tree には存在しない) にのみ `path_b` (raw_hash=Rb, 別内容) が存在した。chunking config を
  変更し `kcs index` (rebuild 経路) を実行する。
- 操作: rebuild 後、新 chunking_config_hash に対する `chunk_config_generations` association が
  `Ra` 由来 chunk と `Rb` 由来 chunk のそれぞれに作られたかを検査する。
- 期待: `Ra` (HEAD 参照) には新 config の association が作られる。`Rb` (HEAD 非参照、過去 commit
  のみ) には作られない。**現状**: `retained_history_instances` (historical_reindex.rs L97-207) は
  `HistoryReader::new(kcs_dir).all_parents(head)` (main.rs L3937, L9771 から呼出) で
  **全履歴**の normalized instance を対象化しており、HEAD tree 限定のフィルタが存在しない —
  `Rb` にも新 config の association が作られ、到達不能な embedding タスクが生成される。

### PC62 履歴 (非 HEAD) instance は旧 chunking_config_hash association のまま放置し、新規 embedding タスクを生まない [P1]
- 正本: PC61 と同一引用。
- 前提: PC61 と同一シナリオ。
- 操作: rebuild 完了後の `TaskStore` (embedding task) を検査する。
- 期待: `Rb` (履歴限定 instance) に対する新規 embedding task が **enqueue されない** (課金が
  発生しない)。**現状**: PC61 と同根 — `retained_history_instances` が `Rb` を含めて返すため、
  後続の embedding task 生成ロジック (`enqueue_embedding_tasks` 等) が到達不能な instance にも
  タスクを積む。

### PC63 [相互参照] --at 時点検索は新 config を要求せず、U69 の byte 順最小代用規則で解決される [P2]
- 正本: PC61 と同一引用 (『履歴 instance は時点指定検索で旧 config のまま参照されるため
  (H 領域 U69/U71)』) — U145 と U69 (PC32) の整合性確認。
- 前提: PC61 実装後 (`Rb` に新 config association が作られない状態)。`Rb` を含む過去 commit
  `Cold` に対し `--at Cold` で検索する。
- 操作: `kcs search "<query>" --at Cold --text` を実行する。
- 期待: `Rb` は新 config の association を持たないため、PC32 の「config 未記録扱い→
  ancestor-or-equal introduction の byte 順最小代用」規則で解決される (search が空振りにならない
  — U145 による再 chunk 対象縮小が、U69 の代用規則と組み合わさって初めて「履歴 instance も検索
  可能」という北極星要件を満たすことの結合確認)。**現状**: PC32 も PC61 も未実装のため、現状の
  `--at Cold` は「常に現在値の chunking_config_hash」(PC31 の未実装) を使うため、たまたま
  `Rb` が rebuild 時に (HEAD 限定なしで) 新 config で再 chunk される現行実装では**偶然**
  ヒットするが、PC61 の fix を先に適用し PC32/PC69 の fix を伴わずに単独適用すると `Rb` が
  検索から完全に脱落する回帰を生む — 実装順序上、**PC61/62 と PC31/32 は同時に適用する必要がある**
  ことを設計上の注意として本契約に記録する。

---

## Q. 解釈が割れうる点 (spec の文言からは一意に決まらない — 勝手に決めない)

1. **PC3 / fail_behavior=warn の warning 表現**: 05 §1.1 L41 は「構造化 warning を stderr /
   --json の `warnings[]` へ出す」と複数形の配列フィールドを述べるが、現行実装 (main.rs
   `ResolvedMode.warning: Option<String>`, L1079) は単数の `"warning"` 文字列フィールドである。
   `warnings[]` (複数・配列、将来複数の警告が同時発生する余地を残す設計) と `warning`
   (単数・文字列、実装の現実) のどちらを正本として固定すべきかは、この 1 文のみからは判断できない
   (05 §1.7 のレスポンス例 JSON にも `warnings[]` は登場しない ため、例示との整合も取れていない)。
   本書は「fail_behavior=warn が text fallback + 非 null warning 表現を伴う」という効果自体は
   PC3 で固定するが、フィールド名・型 (単数 or 複数) の確定は見送る。

2. **PC20 / index_generation の 6 契機と既存 last_lifecycle_epoch 機構の関係**: 05 §1.5 L182 は
   tombstone lifecycle 更新による回転の理由を「(canonical final event が) 検索の可視集合を
   変えるため、purge の回転と対称」と説明し、既存実装には `index_metadata.last_lifecycle_epoch`
   という**類似目的の別カウンタ**が既に存在する (main.rs L2358-2367、tombstone lifecycle の
   世代不一致を `INDEX-REBUILDING-001` 除外として検出する専用機構)。新設する `index_generation`
   (ULID、rebuild/purge/embedding finalize/index-batch finalize/tombstone lifecycle/GC shallow の
   6 契機で回転) が、この既存の `last_lifecycle_epoch` チェックを**完全に置き換える**のか、
   それとも tombstone lifecycle 由来の検出は既存機構のまま残し `index_generation` は残り 5 契機
   専用として**併存**するのかは、05 §1.5 の文言のみからは一意に決まらない (両者は「検索の可視集合を
   変える」という同じ動機を持つため統合が自然に見える一方、`last_lifecycle_epoch` は
   `index_metadata` 表を経由しない独立の crash-safe 補完規則 (§3.5) を既に持っており、単純な
   ULID 回転に統合すると当該補完規則の再検証が必要になる)。実装時に確定を要する。

3. **PC46 / shallow_skipped の集計粒度**: 05 §1.6 L263-264 は「レスポンスに shallow_skipped 件数を
   可視化」とのみ述べ、multi-scope 検索でこれが (a) `searched_scopes[]` の各要素に per-scope
   フィールドとして付くのか、(b) `excluded_scopes[]` の該当 scope のエントリに付くのか (ただし
   PC45 のとおり shallow skip は「部分的な skip」であって scope 自体を除外するわけではないため
   この置き場所は馴染まない)、(c) レスポンス直下のトップレベル合算値 (全 scope 合計) なのかは、
   この 1 文からは判別できない。05 §1.7 のレスポンス例 JSON にも `shallow_skipped` は登場しない。

4. **PC56 / 06 §7 L364 の「優先順位」が指す対象**: 06 §7 L364 は「優先順位は VERSION → journal →
   DUP → REBUILDING」とのみ述べる。この優先順位が (a) 複数の特別除外理由が**異なる scope 間で
   混在**した場合にどの exit を採用するかの順位を指すのか、(b) 実装が各 scope の除外理由を
   判定する際に複数の候補理由 (例: ある scope が同時に VERSION 相当でも REBUILDING 相当でもあり
   得る場合) のうちどちらを採用するかの判定順序を指すのか、文言のみからは一意に決まらない。
   本書 PC56 は (b) 寄りの「判定順序」解釈を暫定採用したが、(a) 解釈 (混在時にどちらの特別 exit を
   採用するか) も文法上排除できない。また INCOMPAT がこの 4 項目の優先順位リストに明示的に
   含まれていない点 (05 §1.8 L390-391 では VERSION と同じ exit 8 に分類されるが、06 §7 L364 の
   リストには登場しない) も未確定要素として残る。

## R. 裁定 (§Q の解釈割れ — 実装用、2026-07-22 オーケストレータ裁定)

1. **PC3**: **`warnings[]` (複数・配列) を正とする** — 05 §1.1 の規範文が配列形を明記。単数 `warning` フィールドは廃止し、複数警告の同時発生 (STORE-VERSION 除外 + gate fallback 等) を表現可能にする。MVP 前のため --json 互換の破壊は可。
2. **PC20**: **併存が正 (統合しない)** — index_generation (6 契機の cursor 無効化版) と last_lifecycle_epoch (tombstone lifecycle 単調性の crash-safe 検証・§3.5 の独立補完規則付き) は目的が異なる。tombstone lifecycle 更新時は両方が動く (lifecycle-epoch +1 と generation 回転) — Phase 1c-2 の実装方向を追認。
3. **PC46**: **searched_scopes[] の各要素に per-scope の `shallow_skipped` (件数・0 は省略)** — どの scope の履歴が浅いかという行動可能情報を保つ。トップレベル合算・excluded_scopes への配置はしない。
4. **PC56**: **(b) 判定順序を正とする** — 05 §1.8 が「理由混在の全 scope 除外 = SCOPE-ALL-FAILED (retryability 分割)」を明文化しているため、(a) の「混在時の特別 exit 選択」は発生しない。単一 scope が複数理由に同時該当する場合の分類順 = **VERSION → INCOMPAT → journal → DUP → REBUILDING** (INCOMPAT は spec のリスト外だが VERSION と同じ exit 8 系のため隣接に置く — 本裁定で確定)。

---

## 集計 (報告用)

- **契約総数**: 63 (PC1-PC63、番号連番に欠番・重複なし)
- **領域別内訳**: §A 3 / §B 4 / §C 7 / §D 3 / §E 1 / §F 9 / §G 2 / §H 4 / §I 3 / §J 8 / §K 3 /
  §L 1 / §M 3 / §N 7 / §O 2 / §P 3 (合計 3+4+7+3+1+9+2+4+3+8+3+1+3+7+2+3 = 63)
- **優先度内訳**: P0 = 41 / P1 = 19 / P2 = 3
- **確認済み (現状固定・回帰防止のみ)**: PC3, PC18, PC28, PC29, PC30, PC35, PC47, PC48, PC50 (部分),
  PC51, PC58 = 11 件 (「適合済みの可能性」4 件 U66/U68/U73/U76 の指示書再精査により、U66→PC18,
  U68→PC28, U73→PC48, U76→PC29 として契約 1-2 本ずつに圧縮する方針を確定)
- **解釈が割れうる点**: 4 件 (§Q note-1〜4)。いずれも実装判断で暫定固定せず、実装時の確定待ちとして
  記録するに留めた (裁定は行っていない)
- **対象外として明示的に切り出した項目**: `kcs restore`/`kcs view` (D 領域)、purge 機構本体 (E 領域)、
  Evidence Pointer 解決手順・§1.7 のレスポンス pointer 構築アルゴリズム (G 領域)、07-adapter-spec.md
  §3 の承認 publish/revoke CLI 本体 (I 領域)、cost-ledger device 行の sweep/剪定機構
  (`step4b-contract-tests-ledger.md` §H で契約済み)、GC 実行系本体 (Phase 4+)
