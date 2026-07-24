# 探索型監査 第14ラウンド (R14) 裁定 — 新規 4 major + 2 minor

- 実施日: 2026-07-06、対象 HEAD: c221095 (428 テスト green)
- エンジン: Claude-Opus / Claude-Sonnet-A/B/C/D (フルスコープ実機) + GPT-5.5 (read-only 静的) +
  GPT-5.3-Codex-Spark (範囲限定: R13 fix 新配線の網羅性 = ログローテ writer 呼出網羅 + tools.toml typed loader)
- 焦点: 「R13 fix が開ける新配線の穴」(R9-4→R10-4、R11-5→R12-3 に続く定番脈)。R14 は的中し、
  R13-1 (incremental online) と R13-4 (HEAD 自己修復) の新配線から実バグが噴出。
- 収束状況:
  - **prev-instance 部分破損ブリック**: Sonnet-A/B/C/D の 4 本が独立再現収束 (online 経路 + Sonnet-C は
    offline 経路の scope 全体ブリックまで拡張)。オーケストレータが control 付き実機再現。
  - **R13-4 self-heal read-only ブリック**: Sonnet-A/B/C/D の 4 本 (major) + Opus (minor) の 5 本収束。
    オーケストレータが control 付き実機再現。
  - **遅延 online task の stale input_hash**: Opus 単独発見。オーケストレータが prepared_hash 突合で
    content-addressing 不変条件破壊を独立再現。
  - **incremental 実 Mistral 全文送信**: GPT-5.5 単独 (静的)。オーケストレータが file:line + mock/実クライアント
    差分で確認。mock seam を使う Sonnet 群は原理的に検出不能 (mock が hint からページ合成し実挙動を隠す)。
- 却下: 未来日付 mtime によるローテ無効化 (Sonnet-B) は Sonnet-A/C/D + Opus + オーケストレータが
  「次 append で mtime が実時刻へ補正され 1 サイクルのみ、無限成長に至らず」で反証 (§却下1)。

---

## R14-1 [major] 前回 online 正規化インスタンスの unit ファイル部分破損が Full フォールバックを迂回し、対象文書の online markdownize を恒久ブリック (offline 経路では index 全体を巻き添え) — 回復コマンドなし

発見: Claude-Sonnet-A/B/C/D の 4 本独立収束。オーケストレータが control 付き実機再現。

**事実** (`load_previous_instance` の非対称エラー処理が根):
- `crates/kio-cli/src/main.rs:7955-7957` — manifest.json 自体が読めない場合は `Ok(None)` に優雅降格
  (= previous なし → Full 再送で自己修復)。
- `crates/kio-cli/src/main.rs:7965-7967` — 一方、manifest が `status:done` と主張する unit の
  `<unit_ref>.json` が読めない場合だけ `fs::read(&unit_path).map_err(|err| KioError::io(...))?` の
  **hard Err**。同一関数内で唯一の非対称。
- 伝播 2 経路:
  - **online**: `latest_online_instance_for_path` (main.rs:6006) が `load_previous_instance(...)?` で
    Err をそのまま伝播 (より古い健全候補を試さない) → `try_online_incremental_markdownize`
    (main.rs:5841-5845) が `.map_err(|_| invalid())?` で `RetryErrorKind::InvalidInput` (恒久非 retry、
    task.rs:336-343 で `retryable:false, max_attempts:Some(0)`) に格上げ → `execute_online_markdownize_task`
    (5677-5685 の `?`) が直後 (5689-5709) の正常な Full 再送コードへの到達を潰す。
  - **offline** (Sonnet-C、ブラスト半径大): `previous_instance_for_path` (main.rs:7942) →
    `run_index_pipeline` の `for candidate in preview.candidates` ループ (7506-7507) が Err を伝播し
    **`kio index` 全体を中断**。破損 unit を持つファイルよりアルファベット順で後のファイルは
    silent に未処理 (エラーメッセージにも言及なし)。
- **決定打**: `latest_online_instance_for_path` の呼出は change_rate 判定 (5851) より**前**にあるため、
  文書を 100% 書き換えても毎回同じ破損 previous を踏む (Sonnet-D)。破損 v(N) が「latest done online instance」
  から二度と外れない (新規 online-done が成立しない) ため恒久。`batch retry`=tasks_attempted:0、
  `repair --rebuild-db`/再 index いずれも無効。

**オーケストレータ実機再現** (control 付き、19 ページ OCR fixture):
- Control (破損なし): v2 resume → `tasks_executed:1, tasks_failed:0` (正常)。
- 破損 (unit json 1 個 rm、manifest 無傷): v2 resume → `tasks_failed:1`、failed task =
  `status:failed, attempts:1, fallback_reason:invalid_input`。`batch retry`=tasks_attempted:0、
  `repair --rebuild-db` 無効、v3 で同一失敗再現 (恒久)。offline baseline は毎回 done (影響は online OCR/layout enrichment のみ)。
- **唯一の差は削除した 1 unit ファイル** = 正常 success を恒久非 retry 失敗に反転させる。

**docs 契約**: docs/04 §3.2 の受入検査は「incremental 不成立/失敗 → Full 降格」を規定。「previous が読めない」は
その一種であるべき (実際 manifest 欠損はそう扱う)。

**修正方針**:
1. `load_previous_instance` の unit 読込失敗を manifest 欠損と同じ `Ok(None)` に揃える
   (`let Ok(bytes) = fs::read(&unit_path) else { return Ok(None); };`。破損/欠損 previous は
   「使えない previous」= Full 降格)。JSON パース失敗も同様に `Ok(None)`。
2. 防御多重化 (任意だが推奨): `run_index_pipeline` のループで 1 候補の前処理 Err が他候補を巻き込まない
   よう候補単位で握って continue (offline のブラスト半径を candidate に限定)。
3. 回帰テスト: (a) online — previous の unit 1 個欠損 → Full 降格で done、(b) offline — 破損ファイルと
   同 scope の後続ファイルが正常 index、(c) manifest 欠損の既存 `Ok(None)` は不変、(d) 破損 previous でも
   `batch retry`/再 index が回復する。

## R14-2 [major] 遅延実行される online markdownize task が「現在のファイル内容」を処理しつつ enqueue 時の stale `input_hash` 下に成果物を保存 — content-addressing 不変条件破壊 + 誤課金 + R13-1 incremental のベースライン汚染 (sticky・自己修復不能)

発見: Claude-Opus。オーケストレータが prepared_hash 突合で独立再現。

**事実**:
- `crates/kio-cli/src/main.rs:5636-5661` `execute_online_markdownize_task` は `repo.root().join(&task.input_path)`
  で**現在の**ファイルを読み `prepare_units(PrepareStageRequest { raw_hash: task.input_hash.clone(), .. })` を
  呼ぶが、`hash_bytes(current_file) == task.input_hash` の検証が一切ない。成果物は
  `normalized_output_ref(repo, &task.input_hash, ..)` (5810/5976) = enqueue 時の**古い** raw_hash 下に保存。
- online markdownize は enqueue した pass では実行されず後続 `batch resume`/`index --online` に必ず遅延される
  (実機確認)。よって「enqueue と実行の間にファイルが編集される」窓が常に存在。offline (deterministic) 経路は
  同期実行なので免疫。
- CAS 冪等 (M5): 一度汚染インスタンスが raw=H(v1) 下に出来ると、ファイルを v1 に戻して再 index しても
  再 OCR されず汚染が sticky に残る (自己修復不能)。cost-ledger は v2 内容の OCR 課金を v1 identity 下に記録。
- R13-1 相互作用: `latest_online_instance_for_path` が汚染インスタンスを previous として読むため、続く
  incremental が「変更ありの文書なのに changed_unit_keys=[]」で全 unit を reused_from 化する provenance 破壊。

**オーケストレータ実機再現** (2 ページ text-layer PDF、page2 のテキストのみ差替):
- v1 offline baseline: page2 prepared_hash `fbf7bdae`。v2 offline baseline: page2 `1cf1457e`。
- enqueue online@v1 → page2 を v2 へ編集 → `batch resume`: ONLINE インスタンス (tool 24bd) は
  **raw=`86bf7d0b` (= v1 の raw_hash)** かつ page2 prepared_hash **`1cf1457e` (= v2 の内容)**。
  同 scope の OFFLINE インスタンス (tool 76c0) は raw=v1・phash=v1 (正)。
  → **v1 identity が v2 内容を保持** = 不変条件破壊を確定。

**docs 契約**: identity = (raw_hash, tool_profile_hash) (MEMORY「KIO の hash と fingerprint の分離」・
docs/03 §8)。raw_hash X 下の normalized instance の内容は raw X 由来であること。

**修正方針**:
1. `execute_online_markdownize_task` 冒頭 (path 決定後、prepare の前) で
   `if hash_bytes(&fs::read(&path)?) != task.input_hash { ... }` を検証。不一致 = ファイルが変わった stale task
   → 実行せず supersede 扱い (現在内容は次の index が自前の task を enqueue する)。retry_kind は
   `InvalidInput` (恒久非 retry) が最小実装だが、可能なら「superseded/skipped」の非エラー扱いにして
   `batch` の tasks_failed に計上しない方が UX が良い (task 状態機械が許せば)。
2. 会計整合: stale task を実行しないので誤課金も消滅。
3. 回帰テスト: (a) enqueue 後にファイル改変 → task が supersede され v1 identity 下に v2 内容が入らない、
   (b) 改変なし (hash 一致) → 従来どおり正常実行、(c) supersede 後に再 index → 現在内容の正しい task が
   done、(d) 汚染が発生しないため incremental baseline も汚染されない。
   ※fix 実地で「supersede vs InvalidInput」の最終挙動を確定し、R14-1 fix (Full 降格) と衝突しないこと
   (R14-1 は previous 読めない→降格、R14-2 は current がタスクと不一致→supersede、独立)。

## R14-3 [major] R13-4 の HEAD 自己修復が `Repository::open()` で無条件に lock+write を試みるため、read-only `.kio` + 破損 (空) HEAD で純読み取りコマンド (status/log/search/view/inspect/open) まで恒久失敗 — R13-4 由来の退行

発見: Claude-Sonnet-A/B/C/D (major) + Claude-Opus (minor)。severity は 4/5 の major を採り、read-only
アーカイブ/フォレンジック用途で scope の全読み取りが不能になる実害を重く見て **major** 裁定
(Opus の「multi-scope search は Excluded に降格し健全 scope を守る=ブラスト半径は直 scope の読み取り」観察は
正しく、緩和材料として記録)。オーケストレータが control 付き実機再現。

**事実**:
- `crates/kio-core/src/scope.rs:163` — `Repository::open()` が全コマンド共通入口で `repo.self_heal_head()?;` を
  無条件実行。
- `crates/kio-core/src/scope.rs:604-623` `self_heal_head` — 修復不要なら no-lock fast path (606-608) で無害だが、
  修復が必要と判定した瞬間 `StoreLock::acquire(&self.kio_dir)?` (612) と `atomic_overwrite(HEAD)` (616) を
  read-only か否かを問わず試み、失敗を `?` で `open()` まで伝播。
- `crates/kio-core/src/scope.rs:1501` `StoreLock::acquire_path` — `.lock` は Drop で削除されるため次回は
  `OpenOptions::write(true).create_new(true)` で新規作成が要り、read-only dir では `AlreadyExists` でなく
  `PermissionDenied` → 汎用 `KIO-E-STORE-IO-001` としてコマンド全体を落とす (lock 競合の
  `KIO-E-STORE-LOCKED-001` 分岐に載らない)。

**オーケストレータ実機再現** (control 付き):
- Control A (健全 HEAD + read-only `.kio`): `status`/`log` とも exit 0 (read-only 自体は無害)。
- 破損 HEAD (空) + read-only: `status`/`log`/`search` すべて exit 1 =
  `{"error_code":"KIO-E-STORE-IO-001","message":"Permission denied (os error 13)","context":{"path":".../.kio/.lock"}}`。
- 対照で原因を self-heal の書込試行に一意切り分け。R13-4 以前 (self-heal 導入前) は書込を試みず、この
  precondition では純読み取りが動いていた = R13-4 由来の退行。

**修正方針**:
1. `self_heal_head` の lock 取得/HEAD 書込/event 記録の失敗を R12-5/R13-3 と同じ「観測/修復書込は非致死」
   思想で best-effort 化 (lock 取得不可・書込 permission エラーは `Ok(None)` + warn を返し `?` で
   `open()` を殺さない)。成功した修復は従来どおり events.jsonl に記録 (silent 修復にしない)。
2. R13-4 の保証は温存: writable scope では self-heal が成功し HEAD 修復 (snapshot の orphan 防止は
   snapshot が writable scope で open→heal 成功を必ず経るため不変)。read-only scope は heal を諦めても
   純読み取りが動く。
3. 回帰テスト: (a) 破損 HEAD + read-only で `status`/`log`/`inspect <hash>` が exit 0、(b) 破損 HEAD +
   writable では従来どおり heal 成功 + events 記録、(c) 健全 HEAD + read-only は不変 (exit 0)、
   (d) writable scope の snapshot は空 HEAD からの orphan を起こさない (R13-4 回帰不変)。

## R14-4 [major] incremental Markdownize が実 Mistral 経路では差分ページのみでなく全文書を送信・全ページ再課金 — R13-1 のコスト/秘匿削減が mock seam でしか成立しない (comment も虚偽)

発見: GPT-5.5 (静的)。オーケストレータが file:line + mock/実クライアント差分で確認。mock seam を使う
実機エンジン (Sonnet 群) は原理的に検出不能。

**事実**:
- `crates/kio-adapter/src/catalog.rs:57-61` の comment は「mode=Incremental のとき prepared_unit_hints は
  changed+added のみを載せ、それらのページだけが再送/再課金される」と主張。
- しかし実クライアント `EnvMistralOcrClient::ocr_markdown` (mistral_ocr.rs:117) は
  `std::fs::read(path)` で**全文 bytes** を読み、`document_payload(&media_type, &bytes)` (121) を
  `{"model", "document", "include_image_base64"}` (125-129) として POST。**`pages` パラメータ不使用**
  (`pages` は 300 行の**応答**パース側にのみ登場、リクエストにない)。`prepared_unit_hint` は
  `markdownize()` の後処理 (232-248、返却ページの unit_key 対応付け) にしか使われない。
- mock `MockStandardOnlineMarkdownizeClient::ocr_markdown` (catalog.rs:138-195) は
  `prepared_unit_hint` からページを合成するため、テストでは「差分送信」に見えるが実挙動を隠す。
- 帰結: 実運用の軽微改版でも全ページが OCR API に送られ全ページ課金 = R13-1 の唯一の目的
  (差分課金) が本番未達。R13 の既知残置「incremental の cost-ledger が full 予約 (過大予約で cap-safe)」の
  前提 (送信は incremental) 自体が誤りだったことも判明。

**docs 契約**: docs/07 §8「文書処理系ルートは unchanged unit を KIO 側で再利用」。catalog.rs comment の
「changed のみ再送/再課金」はこの規範の実装意図。

**修正方針** (real-API 検証はユーザー gate、コード側は testable に):
1. `ocr_markdown` で `request.mode == Incremental` のとき、`request.prepared_unit_hint` の各 unit の
   0-index (prepare.rs の `order`) から `"pages": [..]` を組み立てリクエストに含める (Mistral OCR の
   `pages` パラメータ = 指定ページのみ処理・課金)。Full 送信 (mode=Full) は従来どおり `pages` なし (全処理)。
2. catalog.rs:57-61 の虚偽 comment を実挙動に合わせて訂正 (「changed+added のページ index を `pages` で
   指定して該当ページのみ処理させる」)。docs 変更は不要。
3. リクエスト body 構築を純関数 (`fn ocr_request_body(media_type, bytes, model_pin, pages: Option<&[usize]>) -> Value`)
   に切り出し、incremental で `pages` が hint と一致する unit test を追加 (実 HTTP は叩かない)。
4. 秘匿面 (全文 bytes のアップロード自体) は Mistral API 上ページ抽出に文書全体が要る性質 + unchanged
   ページは v1 で既に送信済みのため delta 極小。真のページ隔離 (事前抽出) は heavier で Step 4+ 候補として
   記録 (本 fix は cost = 差分課金の回復に絞る)。
5. **注記**: `pages` パラメータが実 Mistral 課金を実際に削減するかの最終確認は実 API 検証待ち
   (過去の実 Mistral/Gemini 検証と同じくユーザー gate)。コード側の defect (hint 無視・虚偽 comment) は確定。

## R14-5 [minor] `batch resume`/`retry` の exit 3/4 が errors.jsonl に search 専用/カタログ未収載のエラーコードで誤記録

発見: Claude-Sonnet-A。オーケストレータが file:line + grep で確認。

**事実**:
- `crates/kio-cli/src/main.rs:354-355` `exit_override_error_code` — `PartialFailure → "KIO-E-SEARCH-PARTIAL-001"`
  (docs/crates 全体で grep しても main.rs:354 以外に出現しないカタログ未収載コード)、
  `PermanentFailure → "KIO-E-SEARCH-SCOPE-ALL-FAILED-001"` (docs/05:244・docs/06:254 で multi-scope search の
  全 scope 失敗専用と明記されたコード)。
- `batch_exit_override` (main.rs:5227-5239) — batch resume/retry だけが Partial(3)/Permanent(4) を自前の
  error_code なしで発生させこの override に載る (index は 676 行で `KIO-E-INDEX-PARTIAL-001` を自前設定済み)。
- exit code 自体 (真の machine contract) は正しいため severity minor。errors.jsonl の `code` フィールドが
  観測情報として誤分類 (無関係な search コードを僭称・存在しない文字列を出力)。

**修正方針**: index (676) と同様に batch にも自前 error_code を持たせる
(例 `KIO-E-BATCH-TASK-FAILED-001` / `-PARTIAL-001`。カタログ整合は docs/06 §8 の命名規約に沿う。docs 変更は
不要=schema 側命名で可)。回帰テスト: batch permanent/partial 失敗時の errors.jsonl code が batch 系になる。

## R14-6 [minor] incremental の `tool_profile_hash` 不一致判定が OCR 送信の**後**にあるため、model pin 変更時に incremental を 1 回無駄送信してから Full 再送 (R14-4 と重なると全文 2 回送信)

発見: GPT-5.5 (静的)。オーケストレータが file:line で確認。発火は「実行間で resolve 済み pin が変わった」
狭い窓のみ (通常運用では pin 安定=incremental 成功、無駄送信なし) のため minor。

**事実**:
- `crates/kio-cli/src/main.rs:5889` — `run_standard_online_markdownize(..., mode:Incremental)` を先に実行 (送信)。
- `crates/kio-cli/src/main.rs:5903-5907` — 実行後に初めて `profile.tool_profile_hash !=
  previous.manifest.tool_profile_hash` を検査し `Ok(None)` で Full fallback。
- docs/04:201 の incremental 発火条件 2 は `tool_profile_hash` 不変が前提 → 変更時は incremental を送らず
  Full 1 回だけであるべき。実際は incremental 送信 → mismatch 検知 → Full 再送。R14-4 と重なると
  全文が 2 回送信・2 回課金。

**修正方針**: pin 解決 (`resolve_model_pin`、network だが OCR 送信は伴わない) を incremental リクエスト構築の
**前**に行い、resolved `tool_profile_hash` を previous と比較して不一致なら incremental を送らず即 `Ok(None)`
(Full へ)。`try_online_incremental_markdownize` 内で `online_markdownize_profile()` ではなく解決済み profile を
使って decision 前に gate。回帰テスト: pin 変更を模した seam で incremental 送信が 0 回・Full 1 回。

---

## 却下 / 据え置き (理由つき、再報告防止)

1. **未来日付 mtime によるログローテ無効化 (Sonnet-B minor)** → 却下。`rotate_stale_log` (scope.rs:1036)
   の `file_date >= today` スキップは「同日 or backwards clock」を許容する意図的分岐。未来 mtime は
   **次の append で OS が mtime を実時刻へ再設定する**ため影響は最大 1 サイクルのローテ遅延に留まり、
   無限成長には至らない (Sonnet-A/C/D + Opus + オーケストレータが独立に反証)。Sonnet-B の「恒久無効化」は
   mtime が append で上書きされる点を見落とした誤り。
2. **embedding の model alias が宣言を無視し `ADOPTED_MODEL_PIN` 固定 (Opus が観察、非報告)** → 据え置き
   (意図的と判断)。embedding profile は設計上 gemini-embedding-2 (768 MRL/cosine) に pin 固定
   (MEMORY「Step 3 進行状況」・docs/03 §7 の modality 検証)。R13-2 の model alias 配線は markdown role
   には効くが embedding role は profile pin 固定が正 (alias 可変にすると別ベクトル空間の混入リスク)。
   将来 embedding adapter を差し替え可能にする際に再裁定。
3. **incremental 時の cost-ledger full 予約** → 既知の意図的残置 (R13 裁定済み) だが、R14-4 で
   「送信自体が full」と判明したため前提が変化。R14-4 fix (`pages` で差分課金) 後に cost-ledger の按分
   (enqueue 側移行 + R11-6 prorated 流用) を再検討する。本ラウンドでは R14-4 の送信修正を優先し
   ledger 按分は次段 (fix 実地で R14-4 の実効を見てから)。

## 健全と確認された領域 (今回の監査価値、再掘り不要の記録)

- **ログ日次ローテ/prune/retention (R13-3)**: Spark + Opus + Sonnet 群が境界悉皆確認し全て正
  (events/errors/metrics/access の 4 本すべて `append_jsonl_rotating` 経由・台帳系は logs/ 外で prune 誤爆なし・
  retention_days=1 境界・default 30・scope/user config の一貫性・未来 mtime 無害)。config.toml 由来の
  R12-2 型 drift なし。
- **tools.toml typed loader (R13-2)**: Spark + Opus + Sonnet 群が docs/03 §11・docs/07 §1/§6 の documented key を
  loader と突合し受理漏れ/過剰制約なし。`resolve_auth` の env:/plain:/keychain:-loud、prefix 検証の auth 限定、
  `valid_auth_value` の空値/prefix 単体拒否、`resolve_role_api_key` の markdown/embedding 配線、
  `warn_undeclared_adapter_once` の process 単位 dedup、`DECLARED_ADAPTERS` OnceLock の 1 プロセス 1 コマンド
  性は一貫 (multi-scope 持ち越しリスク実質なし)。宣言外 env 直読みの残置は意図的 legacy fallback のみ。
- **incremental online の kill -9 中断 (R14 焦点筆頭)**: Sonnet-A が 300 ページ incremental に 8 段階 SIGKILL。
  stale lock (PID 生存チェック) + 孤立 Running task (Q3 機構) を次回 `batch resume` が正しく回収し
  `status:done, mode:incremental` で完了。incremental の**自己書込**は crash-safe (R14-1/R14-2 は「他タスクが
  過去に完成させた成果物が後から壊れる/古い hash 下に保存される」別クラス)。
- **incremental 受入検査 (R13-1)**: `try_online_incremental_markdownize` の mapping 後検査 (全 prepared unit
  被覆・profile 一致・fallback_to_full・mapping エラー時 Full 降格) は多重で堅牢 (Opus/Sonnet-C)。
- **persist_normalized_instance の crash-atomicity**: tmp dir → fsync → rename、`dir.exists()` 時の
  remove_dir_all→rename の非アトミック区間も「dir 全体消失」= `load_previous_instance` の `Ok(None)` 経路に
  落ちる無害形 (Sonnet-C/A)。
- **HEAD self-heal ロジック (R13-4/5)**: `empty_head_recovery_hash` は refs が実 Commit を指す時のみ復旧・
  未出生 (両空) は None・lock 下二重チェックで並行 open/snapshot 安全 (Opus。writable scope では正しく自己修復)。
- **multi-scope search 除外の一貫性**: 壊れた remote scope は Fatal でなく Excluded
  (unreachable/index_missing/index_corrupt/rebuilding) に降格し健全 scope の結果を守る (Opus/GPT-5.5)。
- **gen prune**: 旧世代 dir を削除する GC は未実装 (`remove_dir_all` は tmp rollback と同世代上書きのみ)。
  R14 候補「gen prune 後の reused_from」に対応する実コードパスなし (Sonnet-D)。

## フィックス発注条件 (ランブック §4-6 準拠)

- docs/ 変更禁止。各修正ごとに `cargo test --workspace`。回帰テスト必須。commit しない。
- clippy は必ず `--all-features -D warnings` で回す (R8 教訓)。fmt --check。
- R14-1 と R14-2 は独立: R14-1 = previous が読めない→Full 降格、R14-2 = current がタスク hash と不一致→
  supersede。両 fix が衝突しないこと (R14-2 の supersede が R14-1 の降格経路を潰さない)。
- R14-3 の self-heal 非致死化は writable scope の R13-4 保証 (orphan 防止) を温存し、必ず成功修復は
  events.jsonl 記録を維持 (silent 修復にしない)。
- R14-4 は real-API 検証がユーザー gate。コード side の fix (`pages` 送信 + comment 訂正 + request body 純関数化 +
  unit test) のみ実施し、実 Mistral 課金削減の最終確認は保留と fix メモに明記。cost-ledger 按分は本ラウンド対象外
  (R14-4 の送信修正後に次段で再検討)。
- R14-2 の「supersede vs InvalidInput」最終挙動は fix 実地で確定 (task 状態機械が superseded 非エラーを
  許すならそちら、無理なら InvalidInput)。
- 完了後オーケストレータが全 major を実機 repro クローズ再確認 (R12 教訓: crash 面まで)。特に R14-1 (control 付き)・
  R14-2 (prepared_hash 突合)・R14-3 (read-only control) は本裁定と同手順で再検証してからコミット。
