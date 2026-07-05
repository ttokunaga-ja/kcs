# 探索型監査 第12ラウンド (R12) 裁定 — 必須修正 R12-1〜R12-7

日付: 2026-07-06。対象 HEAD: 29f3a3a (テスト 368 green)。
エンジン: Claude-Opus / Claude-Sonnet (フルスコープ実機) + GPT-5.5 (read-only 静的) +
GPT-5.3-Codex-Spark (範囲限定: config 全 key 配線突合 + observability JSONL 網羅性)。
オーケストレータが critical/major 全件を実機再現 or file:line 検証済み。

今回の柱は 3 つ: (a) **config-key drift の系統掃討が完結** (R10-2/R11-7 の型を Spark 焦点で総ざらい —
新規 2 系統 R12-1/R12-2。R12-2 は「silent ignore」ではなく逆向きの「documented key を schema が拒否して
ブリック」という新型)、(b) **R11-5 集約 write-back が開けた crash 窓** (R12-3、ランブックの R12 焦点候補
ど真ん中を Sonnet が実機で捕捉、オーケストレータが実 SIGKILL で再現)、(c) **observability の系統監査**
(R12-4/R12-5、Spark 焦点 — 全 partial/pause 経路が errors.jsonl を素通り)。

採択 7 件 = major 4 + minor 3。却下 (Phase 4+ 明記の gc/snapshot.auto、MULTI-006 据え置き) は末尾。

---

## R12-1 [major] `[search.rrf]` / `[search.diversify]` / `[markdownize.incremental]` が docs 記載 + schema 素通りなのに完全未配線 — documented チューニング手段が全て死に機能

**4/4 エンジン全収束** (Spark 検証1(a) / GPT-5.5 #2 / Opus 所見2 / Sonnet 所見2。R8 F2 以来の全員一致)。

- docs/05-runtime.md §1.3 (59-63) / §1.4 (71-76, 94-96) が `[search.rrf]` (k / w_text / w_vector /
  candidate_depth) と `[search.diversify]` (enabled / strategy "mmr"|"group_by_raw_hash"|"off" /
  mmr_lambda / max_per_raw_hash / mmr_depth) を設定可能 TOML として明記。
  docs/05:280 は cursor の query_hash 正準構成に「[search.rrf]/[search.diversify] の**実効値**」を
  含めることを要求 — 仕様自体が config 読取を前提にしている
- schema は `search` だけ `additionalProperties: true` (config.schema.json:40) → 素通り受理
- 実装は全呼出が固定値リテラル: main.rs:1170-1173 (query_hash)、1595-1603 (fuse_rrf の
  RrfConfig{k:60,w:1/1,depth:200})、2063 + 3433-3439 (diversify_merged / default_diversify_request の
  Mmr/0.7/3/100)。read_search_config (main.rs:3144-3159) は default_mode/fail_behavior のみ (R11-7 配線)
- **実測 (オーケストレータ r12d)**: 同一 raw_hash 5 chunk の scope で `strategy = "off"` → exit 0 のまま
  3 件 (wired なら 5)、`max_per_raw_hash = 1` → exit 0 のまま 3 件 (wired なら 1)
- **実測 (Sonnet)**: `k=1, w_text=0.0, w_vector=1000.0, candidate_depth=1` の極端値でも hybrid 出力が
  **バイト単位で完全一致**。scope config / user config 双方で不変
- **影響 (Opus)**: max_per_raw_hash はページング跨ぎ適用 (docs/05 §1.4) なので、8 セクション文書の
  5 chunk が検索から**恒久到達不能**。documented な逃げ道 `strategy="off"` が no-op
- **同型 (Opus 発見)**: `[markdownize.incremental]` の threshold / max_consecutive も docs/10:533-541 +
  docs/03:595-599 が `.kcs/config.toml` の「設定上書き例」として明記するのに main.rs:6721 (`threshold: 0.30`) /
  6726 (`max_consecutive_incremental: 5`) がハードコード。schema は `markdownize: {type:"object"}` 素通し

**修正方向**:
1. read_search_config と同型のヘルパで `[search.rrf]` / `[search.diversify]` を読み (scope → user の
   優先順位は R11-7 と同じ)、main.rs:1170/1595/2063/3433 の固定値を実効値に差し替える。query_hash
   (docs/05:280) にも実効値を反映 (config 変更で cursor が正しく無効化される)
2. `[markdownize.incremental]` の enabled / threshold / max_consecutive を同様に配線 (mode_decision へ)。
   `include_neighbors` は実装概念が存在しないため、**非デフォルト値は KCS-E-NOT-IMPLEMENTED 系で loud に
   拒否** (R9-6 慣例。silent ignore の再生産禁止)
3. schema: `[search]` 配下に rrf / diversify / multi_scope の typed properties を定義した上で
   `additionalProperties: false` に締める (typo 検出)。multi_scope (parallelism /
   per_scope_timeout_seconds) は **typed で受理し未配線のまま** (MULTI-006 既知据え置きを維持 —
   ここで拒否に倒すと R12-2 型のブリックを新造するので不可)。`markdownize` も incremental の typed
   properties を定義
4. 回帰テスト: strategy=off で dedup 無効 / max_per_raw_hash=1 で 1 件 / rrf 重み変更で順位変化 /
   query_hash が config 依存 / incremental threshold 配線 / 未知 key exit 2

## R12-2 [major] `[adapter.policy]` の documented 8 key 中 7 key が schema 拒否 — docs 通りの config で scope 全体/device 全体がブリック、redact_logs は事実上設定不能

GPT-5.5 #1 + Opus 所見1 (独立収束)。オーケストレータ実証 r12a / r12i。

- docs/07-adapter-spec.md §7 (314-324) が 8 key の policy ブロックを config 例として明記
  (allow_network / allowed_scope / max_input_bytes / timeout_seconds / redact_logs /
  store_request_body / store_response_body / require_command_confirmation)。docs/07:97 は
  `.kcs/config.toml` を明示。docs/10:706-707 (§12.6) は redact_logs を「false への変更は明示設定のみで
  行える」と現行機能として明記。docs/07 §7.1 で Phase 4+ とされるのは OS sandbox 強制のみで、
  KCS 側入力制御 + 事後監査は MVP 契約
- schema は `adapter.policy` に allow_network のみ + `additionalProperties: false`
  (config.schema.json:73-81)
- **実証 (r12a)**: scope config に `[adapter.policy] allow_network=false / redact_logs=true` (docs の例の
  部分集合) → `kcs status` が exit 2 KCS-E-CONFIG-SCHEMA-001。**scope の全コマンドがブリック**
- **実証 (r12i)**: user config (`~/.config/kcs/config.toml`) に redact_logs → **無関係 scope の
  `kcs status` も exit 2** (run() 冒頭 main.rs:332 の user config validate) = **device 全体ブリック**
- redact_logs を読む唯一の実装 (scope.rs:996-1007、user config を raw toml read) には検証で先に死ぬため
  **決して到達しない** — redaction トグルは恒久デフォルト固定。他 6 key は実装参照 0 件 (GPT-5.5 rg)
- config-key drift の新型: R10-2/R11-7 は「受理して無視」、これは「docs 通りに書くと即死」。
  ユーザーが docs の例をコピペした瞬間に tool が使用不能になる

**修正方向** (docs 変更禁止なので実装を docs に合わせる):
1. schema に documented 8 key を typed で追加 (bool/string/integer、docs/07 §7 のデフォルトに整合)
2. redact_logs を実際に配線: user config (現行) に加え **scope config も読む** (docs/07:97 の帰属先。
   device-global logs は user、scope-local access.jsonl は scope 優先 — 優先順位はコードコメントに明記)
3. 未実装 enforcement の非デフォルト値は **KCS-E-NOT-IMPLEMENTED 系で loud に拒否** (R9-6 慣例):
   allowed_scope != "." / store_request_body=true / store_response_body=true /
   require_command_confirmation=false。デフォルト値は無害受理 (現行動作と一致: scope 封じ込め=P1、
   本文非保存、確認フロー既存)
4. max_input_bytes は入力ゲートとして実配線 (prepare/enqueue 前のサイズ検査 — docs/07 §7.1.2 の
   「KCS 側の入力制御」は MVP 契約)。timeout_seconds は実配線が小さく収まるなら配線、
   大工事になるなら非デフォルト値を NOT-IMPLEMENTED で loud 拒否 (silent 受理だけは不可)
5. 回帰テスト: docs/07 §7 ブロック全文を scope config に貼って全コマンド exit 0 (非デフォルト
   enforcement 値を含む場合はその key だけ loud エラー) / user config redact_logs=false が
   errors.jsonl の redaction に実際に効く / allowed_scope="sub" が loud 拒否

## R12-3 [major] R11-5 の集約 write-back に crash 窓 — embedding task が Pending のまま恒久迷子、全回復コマンド (index / batch resume / batch retry / repair --rebuild-db) 無効、index_status が虚偽を報告し続ける

Sonnet 所見1 (単独発見、状態シミュレーションで立証)。**オーケストレータが実 SIGKILL で再現し確定**
(r12k: シミュレーションではなく本物の crash で到達可能なことを証明)。

- 構造 (file:line 検証済み): 埋め込みループは per-batch で sqlite (embeddings + chunk_vec) に即コミット
  (send_embed_batch / link_reused_chunks) しつつ、task 遷移は **メモリ上の BTreeMap に蓄積するだけ**
  (main.rs:5638 transitions)。apply_embedding_transitions は**ループ完走後に 1 回だけ** (main.rs:5745)。
  R11-5 コメント (5627-5637) は「crash 後は content-addressed reuse で re-drive されるので二重課金しない」
  と主張するが、**task レコードの収束には触れていない**
- re-drive の入口 live_chunks_without_embedding (main.rs:6012-6062) は **chunk_vec/content_vector の
  SQL 存在確認のみ**で TaskStore と突合しない → コミット済み batch の chunk は再駆動対象外
- batch resume は Paused 専用 / batch retry は Failed 専用 (docs/06:19-21) — **Pending を回収する経路が
  仕様上も実装上も存在しない**。compute_index_status (main.rs:2153) は Pending を無条件 pending 計上
  (R11-8 の救済は Failed のみ)
- **実 crash 再現 (r12k)**: 1200 chunk scope で `KCS_TEST_GEMINI_EMBED=mock kcs index --approve` を
  embeddings=64 の時点で kill -9 →
  - tasks.jsonl: embedding 1200 件**全て pending** (遷移は全損)、sqlite: embeddings 64
  - 2 回目 index: exit 0、embedding_tasks_executed:1136 (欠落分のみ再駆動)、embeddings 1200 に到達。
    しかし**コミット済みだった 64 task は pending のまま残置**
  - batch resume → tasks_attempted:0 / batch retry → tasks_attempted:0 / repair --rebuild-db →
    rebuilt だが task 不変
  - `search --hybrid --json` → `index_status: {enriched_ratio: 0.973, pending_enrichment_tasks: 64}`
    を**恒久報告** (tasks.jsonl 手編集以外に回復手段なし)
- 深刻度整理: 検索・embedding データ自体は健全 (二重課金なしの主張は真)。壊れるのは task 会計と
  Agent 契約 (index_status) — R9-4 (Partial 回復不能 + 完了偽装) / R10-5 (恒久固着) と同じ class の major。
  R11-5 fix の実機フルサイクル再検証を crash 面までやらなかった穴 (R5 Q1 / R8 F8 と同じ教訓)

**修正方向**: 埋め込み enrichment 駆動部 (index / batch resume / batch retry が共通で通る経路) に
**reconcile ステップ**を追加 — Pending/Running の embedding task のうち、対応 chunk が既に
chunk_vec + content_vector を持つものは apply_embedding_transitions 相当で Done に是正してから
通常の pending 判定に進む (per-batch flush への回帰は O(N²) 再発 = R11-5 の逆戻りなので不可)。
回帰テスト: 「chunk_vec あり + task pending」状態を構築 → index (または resume) 1 回で task が done に
収束し、embeddings 件数が不変 (再送なし)、index_status の pending が 0 になること。

## R12-4 [major] exit 3/5/6 の `__exit_code` override 経路と clap エラーが errors.jsonl を素通り、失敗 search は metrics.jsonl の per-search 行も欠落 — 失敗系がまるごと観測ログの死角

Spark 検証2(a) + GPT-5.5 #3 + Opus 所見3 (3 エンジン収束、各自は断片を minor 評価 —
系統性と docs 明文契約違反を重く見て統合 major 裁定)。オーケストレータ実証 r12g。

- 構造: main() の Err 分岐 (main.rs:238) だけが append_error_log を呼ぶ。Ok + take_exit_override
  (229-235) の exit 3/4/5/6 は**素通り**。exit_from_clap_error も append なし
- docs 契約: docs/05:573 + docs/10:692「errors.jsonl = error_code 付きの**全エラー**」。
  docs/05:578「`kcs search` は 1 回の実行ごとに metrics.jsonl へ 1 行」(per-search latency の一次データ)
- **実証 (r12g)**: `KCS_TEST_GEMINI_EMBED=auth_error kcs index --online --yes` → exit 5、JSON に
  embedding_tasks_failed:1。だが **errors.jsonl はファイルすら生成されず**、events.jsonl にも
  auth/pause 記録ゼロ — 認証失敗が device 観測ログに一切残らない
- **実証 (Opus)**: 2 scope 中 1 scope の sqlite を破損させた multi-scope search → exit 3、
  excluded_scopes は JSON に出るが errors.jsonl は +0 行 (単一 scope の hard error は +1 行になる対照実験
  済み) — 「scope が黙って検索から消えた」ことの監査痕跡が無い
- **静的 (GPT-5.5)**: append_search_logs (main.rs:3498) の呼出は成功応答 (1434) と short-query (3489)
  のみ。cursor mismatch / all-scope-failed は手前で Err → 失敗 search が latency 母集団 (北極星 §4.1 の
  p50/p95/p99) から系統的に欠落
- モニタリング (errors.jsonl tail) が auth 失効・budget 停止・scope 縮退という「監視が存在する理由」の
  イベントを全て見逃す。R11-2 (exit/JSON 不可視) の observability ログ版

**修正方向**:
1. `__exit_code` override を生成する各所 (index/repair/reindex/batch の 5/6、index partial 3、
   search partial 3) で、その理由の error_code を redaction 適用の上 errors.jsonl に append
   (中央 Ok アームでの一括 fallback でも可 — 出力 JSON から error_code/excluded_scopes を再構成)
2. 失敗 search too metrics 1 行 (result_count:0 + error_code、redact_logs 準拠)
3. clap usage エラーも device-global errors.jsonl に append (scope 不要、append_error_log は data_home
   直書きなので既に可能)
4. 回帰テスト: r12g シナリオで errors.jsonl に auth 行 / Opus シナリオで exclusion 行 /
   bad-cursor search で metrics 行 + errors 行 / clap エラーで errors 行

## R12-5 [minor] metrics.jsonl が書込不能だと search 全体が exit 1 で死に、成功した検索結果ごと破棄 — ログ append 失敗ポリシーの非対称

Spark 検証2(c)。オーケストレータ実証 r12f。

- append_search_logs は `?` で伝播 (main.rs:3498-3543 → 呼出元 1434)、errors.jsonl 側は
  `let _ =` 黙殺 (main.rs:238) — 同じ観測ログで正反対のポリシー
- **実証 (r12f)**: `chmod 444 metrics.jsonl` → `kcs search` が exit 1 KCS-E-STORE-IO-001、
  結果 JSON なし (検索自体は成功していた)。device-global ファイルなので **disk full 時は全 scope の
  search が停止**する構造
- 修正方向: append_search_logs (access.jsonl 含む) の失敗は stderr warn に降格し結果は返す
  (observability は結果を壊さない)。回帰テスト: metrics 444 で search exit 0 + 結果あり + stderr warn

## R12-6 [minor] XDG_DATA_HOME/XDG_CONFIG_HOME/XDG_CACHE_HOME の空文字/相対パスを有効値として使い、device-global 状態 (cursor-key 秘密鍵含む) が CWD 相対 `kcs/` に散乱 — scope 内なら次の index で秘密材料がアーカイブに混入

オーケストレータ発見 (r12c の検証事故から派生 — P10/R9-5 型「検証フェーズ自体が発見装置」)。

- XDG Base Directory 仕様: 空 = unset 扱い、相対パス = invalid として無視、が要求。実装は 7 箇所全てで
  `var_os("XDG_*")` を PathBuf::from に直渡し: registry.rs:37 / scope.rs:1047, 1085 /
  main.rs:8105, 8112, 8121, 8134
- **実証 (r12c)**: `XDG_DATA_HOME=""` で kcs init/index/search → scope 直下に `kcs/` が生成され
  scope-registry.sqlite / cost-ledger.jsonl / logs / **cursor-key (0600 の HMAC 署名鍵 = O1 fix の
  秘密材料)** が配置された。CWD が scope なら次の `kcs index` がこれらを CAS/履歴に取り込む
  (secret material の archive 混入)。CWD 依存で registry が分裂し「no indexed scopes」の偽症状も出す
- 修正方向: 空/相対 XDG_* を unset 扱いにフォールバックする共通ヘルパを 1 つ作り 7 箇所を統一。
  回帰テスト: 空文字/相対値で HOME 既定にフォールバックすること (ヘルパ単体テストで可)

## R12-7 [minor] 手書き引数パーサ (search/repair/open/view/reindex) が `--flag=value` 構文を認識せず「unknown flag」と誤報、`--limit 0` は無言で 1 にクランプ

Sonnet 所見3。

- clap derive 系コマンド (index/batch/diff/tag/...) は `--flag=value` を受理するのに、手書きパーサ系は
  完全一致 match (parse_search_args main.rs:3043-3138、parse_reindex_args 2550-2579) のため
  `--limit=5` が「unknown search flag: --limit=5」exit 2 — フラグは存在するのに「存在しない」と誤報
  (R11-1 の clap bypass とは逆方向の、typed/手書きの非対称)
- `--limit 0` は `.clamp(1,100)` (main.rs:3090-3093) で無言で 1 件返す (0 は無意味値なのに成功を装う)
- 修正方向: 手書きパーサの match 前に `arg.split_once('=')` を試して flag/value に分解して同一処理へ。
  `--limit 0` は KCS-E-CONFIG-USAGE の usage エラーに (上限 100 clamp は現状維持 — docs 未記載のため
  docs 変更なしで挙動を変えない)。回帰テスト: `--limit=5` / `--offset=20` / `--scope=.` が
  スペース区切りと同値、`--limit 0` が exit 2

---

## 却下 / 不採択 (理由つき、再報告防止)

- **gc.\* / [snapshot.auto] 未配線** (Spark 検証1(a)): docs が明示的に Phase 4+ (docs/05:316, 354-361,
  607 の「# Phase 4」コメント)。ランブック既知除外に該当。schema の gc keys は docs/05:316 が
  「schema のみ Step 1 から契約遵守」と明記する意図的設計
- **[search.multi_scope] parallelism / per_scope_timeout_seconds** (Spark): MULTI-006 既知据え置き
  (プロンプトで除外済み。R12-1 の schema 締めでも typed 受理を維持すること)
- **markdownize が schema 素通し object であること自体**: docs に `[markdownize]` 直下の利用者向け key は
  なく、実害は `[markdownize.incremental]` (R12-1 に統合) のみ
- **Spark 検証2(b) redaction 新規フィールド**: 該当なし (context 赤化 key の限定列挙は現状の field
  集合に対して十分) — 健全確認として記録

## 健全と確認された領域 (今回の監査価値、再掘り不要の記録)

- scope config の schema 検証カバレッジ (Opus が「user のみ」仮説を実測で棄却 — scope.rs:626-670 が
  Config/Scope/Manifest 全てを検証)
- budget 配線 (per_adapter/hard_stop/warn_at_percent — F5 定着を実適用箇所まで確認)
- cursor/offset ページング (Opus: limit 3 × 8 ページ巡回が ground-truth 24 件と完全一致。
  Sonnet: 再 index 後も cursor が旧 snapshot に凍結され 1 バイト不変)、HMAC 署名 + constant-time 比較
- RRF tie-break 決定性 (score 降順 → chunk_hash 昇順、rrf.rs:79-83)
- scope-registry 冪等 upsert (PRIMARY KEY + WAL/busy_timeout、無限成長なし)
- 時刻演算 (civil_from_days の Hinnant アルゴリズム + div_euclid、負値/閏正常。parse_utc_seconds 固定幅
  厳格検証)
- 25 コマンド × 異常入力 smoke で panic (exit 101) ゼロ (Opus)
- corrupt index の exit 分類 / text-only 時の常時 fallback 表示は docs/05 明記の意図的動作
- FTS keyword cap (R11-10) / open-view cache hardening (R9-3/R10-6) / O1/O7 系 cursor 再発なし (GPT-5.5)

## フィックス発注条件 (ランブック §4-6 準拠)

- docs/ 変更禁止 (実装と schema を docs に合わせる方向のみ)
- 各修正ごとに `cargo test --workspace` green、修正ごとに回帰テストを追加
- 完了後 `cargo clippy --workspace --all-features -- -D warnings` / `cargo fmt --check` green
  (R8 教訓: --all-features 必須)
- コミットはオーケストレータが実機再検証後に行う (fix agent は commit しない)
- R12-3 は再現手順 (kill -9 相当の状態) での実機再検証必須、R12-1/R12-2 は実 config での
  観測可能変化 (off で 5 件、docs/07 ブロックで exit 0) を確認してからクローズ
