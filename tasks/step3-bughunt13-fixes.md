# 探索型監査 第13ラウンド (R13) 裁定 — 新規 4 major + 2 minor

- 実施日: 2026-07-06、対象 HEAD: e0c3aa0 (397 テスト green)
- エンジン: Claude-Opus / Claude-Sonnet (フルスコープ実機) + GPT-5.5 (read-only 静的) +
  GPT-5.3-Codex-Spark (範囲限定: ログローテ実装有無 + JSONL/リソース無限成長)
- 収束状況: tools.toml 未配線に 3 エンジン (GPT-5.5/Sonnet/Opus が各別角度)、ログローテ未実装に
  3/4 (Spark/GPT-5.5/Sonnet、Opus は「doc gap」異見 → docs/09 で反証し採択)。
  Sonnet が incremental Markdownize 本番到達不能、Opus が空 HEAD の silent data loss を単独発見。
- 全 major はオーケストレータが実機再現 or file:line + docs 突合で確認済み
  (R13-4/R13-5/R13-6/R13-2(a)(e) は実機再現、R13-1/R13-2(b-d)/R13-3 は file:line + docs 検証)。

---

## R13-1 [major] Incremental Markdownize (docs/04 §3.1 の主経路) が本番 adapter では到達不能 — 改版のたび全文書を Full 再送・全額再課金

発見: Claude-Sonnet (実機再現つき)。オーケストレータが file:line + docs 検証で確定。

**事実**:
- `crates/kcs-adapter/src/mistral_ocr.rs:199-203` — 本番 Mistral OCR adapter の `capability_flags` は
  `["ocr","layout_detection","table_extraction"]` のみで **`incremental_update` を宣言しない**
  (docs/07:139 の例示 capability には `incremental_update` が並記されている)。
- `crates/kcs-pipeline/src/markdownize.rs:224-240` `choose_markdownize_mode` の条件 3 が
  capability を要求するため、常に `full("adapter_lacks_incremental_update")` に落ちる。
  R12-1 で配線した `[markdownize.incremental]` threshold/max_consecutive はゲート自体に到達せず実効ゼロ。
- `crates/kcs-adapter/src/catalog.rs:49-56` — online 実行経路の `StandardOnlineMarkdownizeRequest` に
  `mode`/`previous`/`hints` フィールドが**構造的に存在せず**、`run_standard_online_markdownize`
  (catalog.rs:66-78) が `mode: Full, previous: None, hints: None` をハードコード。
- 唯一の呼出元 `execute_online_markdownize_task` (main.rs:5610-5618) は unit_mapping
  (docs/04 §2.2 の fingerprint 一致 unchanged 再利用) を一切計算しない。
- Sonnet 実機 (mock seam): v2 改版の online task は `mode=full`、`previous_raw_hash` フィールド不存在。
  baseline 側 task は previous を正しく解決した上で `adapter_lacks_incremental_update` で Full 落ち。

**docs 契約**: docs/07:375「文書処理 API 系 (Mistral OCR 等、§5.2) は unit (page) fingerprint の
再利用により変更 unit のみを再処理する経路で incremental を実現する」(規範・現在形)。
docs/04:206 条件 3、:474-479 (mode/previous_raw_hash/parent_run_id/changed_unit_keys)、
docs/04 §3.2 受け入れ検査。MEMORY (incremental Markdownize 要件確定) とも整合。

**影響**: 軽微改版でも全ページを OCR API へ再送・全額再課金 (R11-6 の unit-scope 会計 fix が
守った経路の上流で、そもそも incremental が発火しない)。コスト直結。

**修正方針**:
1. `MistralOcrMarkdownizeAdapter::profile()` の capability_flags に `"incremental_update"` を追加。
   ※capability_flags は tool_profile_hash の計算入力 → hash が変わり既存 fixture/契約テストの
   期待値更新が必要 (pre-release につき許容。docs との整合を確認して更新すること)。
2. `StandardOnlineMarkdownizeRequest` に `mode`/`previous`/`hints` を追加し、enqueue 側で計算済みの
   unit_mapping/previous を task 経由で `execute_online_markdownize_task` →
   `run_standard_online_markdownize` まで伝播。mock seam (mock/partial) も incremental を模擬可能に。
3. 発火判定は既存 `choose_markdownize_mode` をそのまま使用 (R12-1 配線済み)。incremental 出力は
   docs/04 §3.2 の受け入れ検査 (既存実装) を通し、normalization_runs 記録に
   mode/previous_raw_hash/changed_unit_keys を記録 (docs/04:474-479)。
4. 回帰テスト: (a) mock seam で v1→v2 軽微改版時に online task が mode=incremental +
   changed_unit_keys を持つこと、(b) 変更 unit のみ処理され unchanged unit が前 run から再利用されること、
   (c) 条件不成立 (change_rate 超過等) では従来どおり Full、(d) 受け入れ検査 fail 時の Full fallback。

## R13-2 [major] tools.toml が auth 書式警備のみで documented サーフェス全体が dead — 宣言/auth 解決/model alias 不使用、schema 検証欠落、おまけに documented key の縁値で device brick

発見: GPT-5.5 (宣言 dead/env-only 活性化/schema 不在) + Claude-Sonnet (auth 解決不使用の実機
silent noop) + Claude-Opus (docs/06 §11 起動時検証欠落の実機 + blanket auth walk brick) の 3 角度収束。
オーケストレータが全サブ項目を実機 or file:line で確認。

**事実** (tools.toml を読むのは `validate_user_tools_config` main.rs:8471-8502 の 1 箇所のみ):
- (a) docs/06 §11 (313-316行) は起動時 schema-driven validation (`tools.toml` → `tools.schema.json`) を
  明記するが、`tools.schema.json` は不存在 (schemas/ は config/manifest/scope のみ)。検証は
  `validate_tools_toml_value` = `validate_auth_fields` (tool_lock.rs:106-108) の auth prefix walk だけ。
  実機: `[markdownize] totally_bogus_key="xyz"` + `cmd = 12345` (型違い) → 全コマンド exit 0 無言受理
  (config.toml の同型は exit 2)。
- (b) 宣言キー kind/cmd/model/capabilities/profile_hash (docs/03 §11、docs/07 §1/§6) は
  **全 crate で一切読まれない**。online adapter の採用は env key の存在だけ
  (catalog.rs:180-193 `GEMINI_API_KEY` → Real、`EnvMistralOcrClient`)。docs/07 §7.1(1)
  「実行されるのは ~/.config/kcs/tools.toml に設定した Adapter のみ」と drift
  (docs 全体で env key 単独運用はどこにも規定されていない。GEMINI_API_KEY の登場は
  docs/07:30 の `auth = "env:GEMINI_API_KEY"` 参照値のみ)。
- (c) auth 3 方式 (docs/07 §1: keychain:/env:/plain:) が認証解決に不使用。実クライアントは
  `std::env::var("MISTRAL_API_KEY")`/`("GEMINI_API_KEY")` 決め打ち (mistral_ocr.rs:70-72、
  gemini_embedding.rs:71-73)。keychain は実装ゼロ (`rg keyring|security-framework|keychain:` 0 hit)。
  Sonnet 実機: `auth = "env:MY_GEMINI_KEY"` + MY_GEMINI_KEY 設定済み → `embedding_tasks_executed:0`
  無警告 silent noop (どのログにも痕跡なし)。
- (d) model alias (docs/03 §11「config では可変 alias 可」) 不使用 — "mistral-ocr-latest"
  (catalog.rs:87,99) / "gemini-embedding-2" 定数決め打ち。
- (e) auth prefix walk が**キー名無関係に全文字列へ適用** (tool_lock.rs:242-255)。documented key の
  `url` に縁値 `"plain:"` を書くと全コマンド exit 2 `auth must start with keychain:, env:, or plain:`
  = 誤エラーメッセージ付き device brick (オーケストレータ実機確認)。

**修正方針** (1 つの typed loader 導入で (a)-(e) を一括解消):
1. tools.toml の typed 検証を追加 (JSON Schema `tools.schema.json` or 同等の typed parse)。
   **docs/03 §11 + docs/07 §1/§6 の documented key を全て掃引して受理** (R12-2 の教訓:
   docs のコピペが通ることを回帰テストで保証)。unknown key / 型違いは config.toml と対称の
   exit 2 (KCS-E-CONFIG-SCHEMA-001)。auth prefix 検証は **`auth` キーの値に限定** ((e) 解消)。
2. auth 解決関数を実装: `env:<NAME>` → `std::env::var(NAME)`、`plain:<key>` → 値そのまま、
   `keychain:<svc>` → **loud に KCS-E-NOT-IMPLEMENTED-001** (silent 不可。keyring 依存の追加は
   別途裁定、MVP は明示未実装が安全)。`EnvMistralOcrClient`/`EnvGeminiEmbeddingClient` の
   決め打ちを「宣言があれば宣言の auth を解決、なければ従来 env 変数」に置換。
3. model alias: 宣言があれば `resolve_model_pin` へ渡す。
4. 宣言なし env-only 活性化は当面維持しつつ、online adapter が未宣言で active になる際に
   errors.jsonl へ level=warn (undeclared-adapter) を 1 回記録 (docs/07 §7.1 との drift を可視化。
   完全な宣言ゲート化は外部 adapter 実行が入る Step 4+ で再裁定)。
5. 回帰テスト: (a) bogus key/型違い → exit 2、(b) docs/03 §11 と docs/07 §1 のコピペ → exit 0、
   (c) `url = "plain:"` → exit 0 (auth 限定の確認)、(d) `auth = "env:MY_KEY"` 宣言 + MY_KEY 設定で
   embedding が Real 経路に入る (seam で確認)、(e) `auth = "keychain:x"` → loud エラー、
   (f) 未宣言 env-only 活性化で warn 記録。

## R13-3 [major] docs/10 §12.6 / docs/06 §13 の「日次ローテ・保持 30 日 (config 上書き可)」が完全未実装 — JSONL 無限成長、かつ上書き config key が不存在で docs 通り設定すると device 全体ブリック

発見: Spark (焦点検証1、file:line 列挙) + GPT-5.5 (redact_logs=false 時の保持期限違反の角度) +
Claude-Sonnet (ローテ不発 + `[logs] retention_days=7` brick の実機) の 3/4 収束。
Opus は「docs/09 に phase 割当なし = doc gap」と異見 → **反証**: docs/09:110 (events/errors =
Step 1)・docs/09:124 (metrics/access = Step 3) が観測ログを MVP scope に割当済みで、その正本
docs/06 §13 (:355)「日次ローテーション、保持 30 日 (config 上書き可)」・docs/10 §12.6 (:706) に
ローテ文言が含まれる。Phase 4+ なのは tiered retention GC (snapshot DAG) であり logs とは別物。

**事実** (オーケストレータ自己検証済み):
- `rg 'rotat|retention' crates/` は実装 0 hit (テストコメント 1 件のみ)。events/errors
  (scope.rs:906-924 `append_observation`)、metrics/access (main.rs:3709-3779)、`append_jsonl`
  (cas.rs:205-225) は全て固定名 O_APPEND のみ。日付比較・サイズ上限・prune 皆無。
- config.schema.json に logs 系 key 不存在 + top-level `additionalProperties:false` →
  Sonnet 実機: user config に `[logs] retention_days = 7` を書くと**全コマンド exit 2**
  (KCS-E-CONFIG-SCHEMA-001、device 全体ブリック。R12-2 と同型)。
- Sonnet 実機: 1 年前 mtime の errors.jsonl にそのまま追記、ローテ発生せず。
- GPT-5.5 の角度: `redact_logs=false` 運用では query/path が記録されるため、保持 30 日の
  privacy 前提 (docs/10 §12.6) が「無期限保持」に格上げされ違反。

**修正方針**:
1. config.schema.json に `[logs] retention_days` (integer ≥1、default 30) を追加
   (docs は key 名を規定していないため schema 側で命名。docs 変更は不要)。
2. 共通 writer (device の events/errors/metrics + per-scope の access) に日次ローテを実装:
   append 時に現行ファイルの日付が変わっていたら `events-YYYY-MM-DD.jsonl` へ rename して
   固定名を新規作成 (docs の固定ファイル名を現役に保つ logrotate 方式)、retention_days 超の
   dated ファイルを prune。rename は原子的、rotation/prune の失敗は R12-5 の裁定に合わせ
  非致死 (warn、search 等の成功結果を殺さない)。並行 append の O_APPEND fd が rename 後の
   旧ファイルに書く分は許容 (行喪失なし)。
3. 回帰テスト: (a) 日付跨ぎ模擬で rotation 発生 + 固定名が新規化、(b) retention_days 超の
   dated ファイルが prune、(c) `[logs] retention_days = 7` が exit 0 で受理され実際に反映、
   (d) rotation 失敗 (dir 権限) でもコマンド本体は成功。

## R13-4 [major] 空/切詰め `.kcs/HEAD` (refs/heads/main 健全) で snapshot が全履歴を silent orphan 化 — exit 0 のままデータ喪失

発見: Claude-Opus。オーケストレータが実機で完全再現 (C1=9d9015... 健在 → HEAD 空化 →
log exit 0 出力ゼロ → `snapshot -m after` exit 0 "created" → refs/heads/main が parents 無しの
C2=9147d8... で上書き、C1 は log から消失・CLI 到達不能)。

**事実**:
- `head_commit_hash()` (scope.rs:577-588) が空 HEAD に `Ok(None)` を返し、**破損 HEAD と
  未出生ブランチ (init 直後の正当状態) を混同**。
- snapshot (scope.rs:397) が `parents=[]` の root commit を作り refs/heads/main を無条件上書き
  (scope.rs:415-418)。既知の限界コメント (scope.rs:409-417) は逆ケース (refs 先行) のみ扱う。
- **非対称が smoking gun**: 空 scope.json/manifest.json/tool-lock.json は全て exit 2 拒否、
  欠損/空 refs/heads/main は HEAD から安全回復 (Opus 健全性掃引で確認済みの鏡像)、
  なのに空 HEAD だけが素通りして喪失に至る。
- 判別子は clean: fresh-init = HEAD/refs 両方空。破損 = 空 HEAD + populated refs。

**修正方針**: HEAD が空/欠損かつ refs/heads/main が commit hash を保持する場合、
refs から HEAD を自己修復 (refs 欠損時の既存挙動と対称) し events.jsonl に warn 記録。
両方空のみ未出生扱い。回帰テスト: (a) 空 HEAD + 健全 refs → log が C1 を表示し snapshot が
C1 を親に持つ、(b) HEAD 欠損 + 健全 refs → 同様に回復、(c) 両方空 (init 直後) → 従来どおり
root commit、(d) 回復イベントが events.jsonl に載る。

## R13-5 [minor] 破損 store への再 `kcs init` が「already initialized」exit 0 — 検証も修復もせず、ユーザーの自然な回復手段を無効化

発見: Claude-Opus。オーケストレータ実機再現 (rm .kcs/HEAD → `kcs init .` exit 0
"already initialized"、HEAD 欠損のまま、直後の status exit 1 KCS-E-STORE-IO-001)。

- `Repository::init` (scope.rs:95-96) が `.kcs` 存在時に `open` へ短絡、main.rs:389-397 が
  無条件 "already initialized"。
- 修正方針: 再 init 時に core store ファイル (HEAD / refs/heads/main / scope.json /
  manifest.json / tool-lock.json) を検証し、R13-4 の自己修復と同じ経路で回復可能なものは
  idempotent に再生成して「repaired: <対象>」を報告、回復不能な破損は非ゼロ終了で
  `kcs repair` へ誘導。回帰テスト: HEAD 欠損 → re-init が修復し status exit 0 /
  scope.json 破壊 → re-init が exit 非 0 で破損を報告。

## R13-6 [minor] R12-6 の残穴 — XDG_* 未設定時の `HOME` 空/未設定/相対で device-global 状態が CWD 相対 `kcs/` に散乱

発見: Claude-Opus (自ら R12-6 既知との関係を明示した誠実な限定つき)。オーケストレータ実機再現
(`env -u HOME -u XDG_*` で `kcs init` → CWD 直下に `./kcs/scope-registry.sqlite` 生成。
cursor-key も同経路)。R12-6 fix は XDG_* 変数のみ検証し、HOME フォールバック
(scope.rs:1050-1054 ほか) は生の `var_os("HOME")` → 最終 `PathBuf::from(".")` で absolute 検証なし。

- 影響限定: 散乱先は CWD 相対 `kcs/` サブディレクトリ内であり、scope root 直下ファイルのみ
  索引する設計上アーカイブ混入はしない (R12-6 本体より弱い。隔離破壊 + registry/budget の
  CWD 依存分裂 = device-global cap の意図せぬ迂回)。
- 修正方針: HOME 由来パスにも R12-6 の absolute 検証ヘルパを適用し、絶対パスが導出できない
  場合は `"."` に落ちず loud にエラー (KCS-E-CONFIG-USAGE-001 系)。回帰テスト:
  `env -u HOME` / `HOME=""` / `HOME=rel/path` で全コマンドが CWD に書かず明示エラー。

---

## 却下 / 据え置き (理由つき、再報告防止)

1. **Spark 検証2: tasks.jsonl done 蓄積 / quarantine.jsonl / approvals.jsonl 件数 /
   cost-ledger.jsonl 月跨ぎの compaction 不在、open/view cache の eviction 不在** → 据え置き
   (Step 4 gc 設計と同時に裁定)。理由: docs にこれらの compaction/eviction 契約は存在しない
   (tasks.jsonl は docs に登場すらしない。cache は docs/06:61 で置き場所のみ規定)。
   tasks.jsonl の done 圧縮は `done_output_for` による CAS 冪等再利用 (M5) と衝突し
   誤実装すると再課金リスク。cost-ledger は監査台帳であり append-only が設計妥当。
   R11-5 で読み書きは線形化済みで成長の実害は disk のみ。**silent cap ではなく明示据え置き**。
   ログ系の無限成長のみ R13-3 で解消 (docs 契約があるのはログだけ)。
2. **Opus の「ログローテは doc gap であり bug でない」** → 不採択 (R13-3 で反証詳述:
   docs/09:110/124 の Step 1/3 割当 + docs/06:355 正本文言 + brick 実機)。
3. **GPT-5.5 の kcs_format_version 0.x future minor の曖昧さ** → エンジン自身が確定所見に
   しなかった観察。major>0 拒否は健全確認済み。0.x minor の前方互換規約は docs 側の
   明確化待ち (設計宿題に積むならユーザー裁定)。

## 健全と確認された領域 (今回の監査価値、再掘り不要の記録)

- R12-1 の rrf/mmr 新規コード: 退化 config (`max_per_raw_hash=0`→無制限、`w_text=w_vector=0`、
  all-zero embedding の NaN cosine) を安全処理 (Opus)。
- R12-3 reconcile: 全経路 `lock_store()` 配下で batch resume/retry と直列化、並行 race なし (Opus)。
  読解上も「live かつ既 embed 済み chunk のみ Done 化」に限定 (Sonnet)。
- R12-4 redaction: exit-override/clap 追記経路も配列再帰 + message パス masking 一貫 (Opus)。
- R12-7 パーサ: `--limit=0`/`--limit 0` 対称 exit 2、positional `=` 非分割、cursor 優先。
  残差 (`--` 非対応、空 `--scope=`) は benign (Opus)。
- 部分破損 .kcs 耐性: ~25 破損 × 13 コマンドで panic/hang ゼロ、空 JSON=exit 2 / 欠損=exit 1 /
  dangling ref=exit 4 / future major=exit 8 で一貫。trees/tool-lock 欠損は byte-identical
  self-heal、refs 欠損は HEAD から安全回復 (Opus。R13-4 はこの掃引が逆に浮かび上がらせた非対称)。
- init 冪等 (健全側): 初期化済み scope への再 init は exit 0 (Sonnet。破損時の挙動が R13-5)。
- multi-scope: missing/corrupt index の excluded_scopes 降格、scope_id collision の
  ambiguity 化は実装+テストあり (GPT-5.5)。kcs_format_version major>0 拒否 (GPT-5.5)。
- config-key drift の残り: [search.multi_scope] parallelism/per_scope_timeout は MULTI-006
  既知据え置き、gc.* は Phase 4+ — いずれも意図的 silent 受理と確認 (Opus)。
- P3 の tools.toml 0600 warn: plain: + 0644 で発火 / 0600 で非発火を実機再確認 (Sonnet)。

## フィックス発注条件 (ランブック §4-6 準拠)

- docs/ 変更禁止。各修正ごとに `cargo test --workspace`。回帰テスト必須。commit しない。
- clippy は必ず `--all-features -D warnings` で回す (R8 教訓)。fmt --check。
- R13-1 は capability_flags 変更で tool_profile_hash が変わる → 既存 fixture/契約テストの期待値
  更新は docs (docs/07 §5.1 の pin 規約) との整合を確認した上でのみ許可。
- R13-2 (4) の「宣言なし活性化 warn」は 1 実行 1 回 (毎 task 単位で increment しない)。
- R13-3 の rotation/prune 失敗は非致死 (R12-5 裁定と整合)。
- R13-4/R13-5 の自己修復は必ず events.jsonl に記録 (silent 修復にしない)。
- 完了後オーケストレータが全 major を実機 repro クローズ再確認 (R12 教訓: crash 面まで) して
  からコミット。
