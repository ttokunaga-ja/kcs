# 探索型監査 第21ラウンド (R21) — 裁定と修正計画

7 エンジン (Claude-Opus / Sonnet-A / Sonnet-B / Sonnet-C / Sonnet-D / GPT-5.5 / GPT-5.3-Codex-Spark)。
HEAD `914e569`、全 478 テスト green・clippy(--all-features)/fmt clean の状態から開始。

**結果: 1 critical + 5 major + 1 minor。却下 0 (R9・R16・R19・R20 に次ぐ 5 回目)。据え置き 1 (flate 展開)。**

本ラウンドは 2 つの脈が同時に噴出:

1. **file-type ルーティングの継続採掘 (R20-4/5/6 クラスタの縁 + Step 2 以来の未掘)** — R20 が新設した
   file-routing クラスタは 3 ファイル 340 行の過去最大級新配線だったが、その受け手 (executor precondition) と
   判定粒度 (document-level `all()`) と MIME ゲート (3 canonical MIME 限定) の 3 面に穴が残っていた:
   - **R21-3** [major]: R20-5 が enqueue 側だけ直し、送信側 `online_markdownize_precondition_ok` の
     「prepared_units 非空=有効」前提が未更新 → スキャン PDF/画像/OOXML/binary は R20 後も一度も OCR に到達せず
     churn (4 エンジン収束 Sonnet-A/B + GPT-5.5 + オーケストレータ)。
   - **R21-4** [major]: octet-stream/大文字拡張子の**テキスト**ファイル (`.yaml/.json/.sh/Dockerfile`/`README.MD`) が
     R9-2 ゲート (3 MIME 限定) をすり抜け online OCR 送信+課金 (Opus + GPT-5.5 + オーケストレータ、pre-existing)。
   - **R21-5** [major]: R20-4 の real-text 判定が document 全体 `all()` 粒度のため、実テキスト 1 ページ + ゴミページ
     混在 PDF がゴミを証拠化 (Sonnet-C/D + オーケストレータ収束)。

2. **content-addressed identity × 秘匿/会計 (R20-1/R20-2 の縁)** — R20-1 の `te.path` 変更を辿ると、その SELECT が
   乗っている **JOIN が 1 chunk_id を live path ごとに fan-out する**という空間軸の前提が未検証だった:
   - **R21-1** [critical]: byte-identical な非秘匿双子があると Tier B 秘匿ホールドが完全バイパス、
     `--send-secrets` 無しで本文が online 送信+課金 (Sonnet-C control、JOIN fan-out + `embeddable_task_state`)。
   - **R21-2** [major]: 同 JOIN fan-out の非秘匿版 — 同一 output_ref の embedding タスク重複生成で二重送信・二重課金、
     R20-2 の「output_ref 1 つにつきタスク 1 本」不変条件が別ソースで破れる (Opus + GPT-5.5 + オーケストレータ)。

加えて **R21-6** [major] — R20-3 が AuthError の**非 live 化 reclaim** だけを塞ぎ、「live 不変ファイルが auth_error で
失敗した」経路を 5 ラウンド (R16-7→R19-2→R20-3) 一度も検討していなかった (Sonnet-B control)。
**R21-7** [minor] — R20-2 の revive パターンが姉妹関数 `hold_secret_embedding_tasks` に横展開されず (Sonnet-D)。

全 critical/major はオーケストレータが `/tmp` 隔離 `XDG_DATA_HOME` 下で control 付き実機再現・会計値実測済み。

---

## 所見一覧 (severity 降順)

### R21-1 [critical] byte-identical な非秘匿双子ファイルが 1 つ存在するだけで Tier B embedding 秘匿ホールドが完全バイパスされ、`--send-secrets` 無しで秘匿ファイルの本文が online 埋め込み API へ送信・課金される — 監査ログは "hold" を主張し続ける

**エンジン**: Claude-Sonnet-C (control 実機) + オーケストレータ独立 control。**脈/型**: R20-1 の `te.path` 変更を辿って露出した「同一 chunk_id が複数 live path を持つ」空間軸の前提未検証 (fix が開ける穴 11 例目の一角)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:7727-7748` (`live_chunks_without_embedding`) — `chunks c JOIN tree_entries te ON te.raw_hash=c.raw_hash AND te.tool_profile_hash=c.tool_profile_hash AND te.gen=c.gen` に **path 制約も `DISTINCT` も無い**。`chunk_id` は content-addressed (`crates/kio-index/src/chunking.rs:60-77`、path を含まない) なので、同一内容が N 個の live path に存在すると 1 chunk_id が **N 行に fan-out** (各行 `te.path` のみ相違)。
- `crates/kio-cli/src/main.rs:7183-7189` — fan-out した同一 chunk_id の各インスタンスを `raw_path` (=各 te.path) 基準で `held`/`sendable` に**独立に**振り分ける。秘匿名インスタンス→`held`、非秘匿名インスタンス→`sendable`。
- `crates/kio-cli/src/main.rs:7947-7953` (`hold_secret_embedding_tasks`) が output_ref=`embedding:<chunk_id>` の Paused `secrets_tier_b_hold` タスクを作成。
- `crates/kio-cli/src/main.rs:7662-7674` (`embeddable_task_state`) — **真因**。`TaskStatus::Paused => override_budget || task.fallback_reason.as_deref() != Some("budget_exceeded")`。`secrets_tier_b_hold` は `"budget_exceeded"` ではないので **常に `true`** (「budget 起因以外の Paused は再送安全」というコメントが秘匿ホールドにまで誤適用)。`filter_embeddable_by_task_state` (`7637-7658`) が sendable インスタンスをこの判定に通し、送信ループが output_ref 一致で **held タスクそのものを Paused→Done に書き換えて送信**。

**期待 vs 実際 (control 付き実機、`--send-secrets` は一度も未使用)**:
```
[CONTROL] password_backup.md 単体            → embedding task ×2 とも paused/secrets_tier_b_hold、課金 0
[EXP] notes.md + password_backup.md (同一バイト) → embedding task done/embedding_adapter_done、
      cost-ledger embedding 2.4e-6 課金 (= 送信済)、secrets-approved.jsonl 不在、
      quarantine.jsonl は approval_method="hold" のまま (矛盾する監査記録)
```
期待 = Tier B ファイルは `--send-secrets` 無しでは何が起きても embedding API に送信されない。実際 = 内容が byte-identical な非秘匿ファイルが 1 つ存在するだけで hold タスクが同一コマンド内で Done に書き換えられ本文が送信される。

**なぜ critical か**: 発火に秘匿固有の操作 (`--send-secrets`・`!pattern` 等) が一切不要。「秘匿ファイルのバックアップコピー・テンプレート複製・vendored な同一 LICENSE を別ディレクトリに置く」という日常操作だけで踏む。R19-1 裁定注記の「秘匿特有の操作ゼロで送信=critical」に該当。

**修正案 (2 層)**:
1. **root**: `live_chunks_without_embedding` の収集ループで `chunk_id` を一意化 (`BTreeSet` dedup)、chunk_id ごとに 1 `EmbeddableChunk` を返す。dedup 時のパス選択 tiebreak は「いずれかのパスが `classify_secret().is_some()` なら秘匿パスを採用」(保守側=hold へ倒す)。これで fan-out 自体が消え R21-2 の二重課金も同時に解消。
2. **defense-in-depth**: `embeddable_task_state` (`7666-7668`) の Paused 判定を「`budget_exceeded` 以外は安全」という減算リストから、`secrets_tier_b_hold` (および将来の secrets hold reason) を明示除外する allowlist へ反転。root 修正後も同種 output_ref 衝突で hold タスクが再送されないことを構造的に保証。

---

### R21-2 [major] 同一バイト内容が複数 live path に存在すると `live_chunks_without_embedding` の JOIN が chunk_id を fan-out し、同一 `output_ref` の embedding タスクが重複生成 → content-addressed reuse (§5.5) を無視して同一内容を online 埋め込み API へ 2 回送信・2 回課金。R20-2 の「output_ref 1 つにつきタスク 1 本」不変条件が別ソースで破れる

**エンジン**: Claude-Opus + GPT-5.5 (独立、file:line) + オーケストレータ (会計値実測)。**脈/型**: R20-2 の適用範囲の絞り漏れ — R20-2 は「retired_non_live revive が重複 output_ref を生む」1 経路だけを塞いだが「同一内容が複数 path」という別ソースは未対処。R21-1 と共通 root (JOIN fan-out)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:7727-7748` — R21-1 と同じ path 無制約 JOIN。
- `crates/kio-cli/src/main.rs:7991-8004, 8024-8055` (`enqueue_embedding_tasks`) — `existing` 集合はループ前スナップショットで append ループ中に更新されない。`pending` 内の重複 chunk_id が各々 `task_store.append` → **同一 output_ref のタスク N 本**。送信ループの `plan_embed_batch` は同一バッチ内で embeddings 未書込みのため両方を send 判定 → N 回送信・N 回課金。

**期待 vs 実際 (control 実機、会計値実測)**:
```
[単一 a.md]                       → embedding task 1 本、課金 1.95e-6
[a.md + b.md 同一内容 同一 index] → embedding task 2 本 (output_ref 同一)、各 reserved 1.95e-6、課金 3.9e-6 (2×)
[pre-R20 build でも同一挙動]      → JOIN fan-out は R20 regression ではなく content-addressing の必然の未検証前提
```
期待 = content-addressed 同一性 (§5.5) 通り内容 1 種につき送信・課金 1 回 (別 run では reuse が正常動作)。実際 = 同一 pass 内の重複が reuse を bypass し copy 数だけ倍化。vendored コピー・複数ディレクトリ配置の `LICENSE`/`config` 等で発火、gross を膨らませ cap を圧迫し正規タスクを早期 Pause。非 live 化時は R20-2 が塞いだ二重 reclaim を別ソースで再現しうる。

**修正案**: R21-1 の root 修正 (JOIN の chunk_id dedup) がそのまま本件も解消する。R21-1 と一体で設計。

---

### R21-3 [major] R20-5 が新設した「非 text-native 文書の online OCR 経路」が送信側 `online_markdownize_precondition_ok` の未更新前提で全滅 — スキャン PDF/画像/OOXML/binary は R20 後も一度も OCR に到達せず、index のたび再生成→即死の churn。R20-7 が enriched_ratio=1.0 で完全に隠蔽

**エンジン**: Claude-Sonnet-A + Claude-Sonnet-B + GPT-5.5 + オーケストレータ (4 エンジン収束)。**脈/型**: R20-5 の適用範囲の絞り漏れ (fix が開ける穴、dead-end を別関数に温存)。R20-5 が名指しで塞いだ dead-end が同一ラウンド内の別関数に残存。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:6412-6441` (`online_markdownize_precondition_ok`) — 最終行 `!prepare.prepared_units.is_empty()` (6441) が非空を要求。R20 以前は「テキストレイヤ有り PDF の AI 強化」限定で prepared_units は常に非空だった前提のまま。
- `crates/kio-cli/src/main.rs:8701-8726` (R20-5 `enqueue_online_placeholder_task` 合流) — `prepare.prepared_units.is_empty()` が**まさに**このタスクを enqueue するトリガー (スキャン PDF/画像/OOXML/binary はローカルで絶対に非空にならない)。
- `crates/kio-cli/src/main.rs:6003-6020` (`execute_pending_markdownize_tasks`) — precondition 失敗で adapter を一度も呼ばず `retire_online_task_reclaiming` で即 `RETIRED_NON_LIVE`・non-retryable 固定。第二ゲート `execute_online_markdownize_task` (`6493-6497`) も同前提未修正 (ゲート1で先に死ぬため現状未到達だがゲート1だけ直すとここで再死)。
- `crates/kio-cli/src/main.rs:2436-2444` (R20-7) — `retired_non_live` を `compute_index_status` 分母から除外するため、この恒久失敗が `enriched_ratio` に一切反映されず `enriched_ratio:1.0`/`pending_enrichment_tasks:0` の偽の健全性を報告 (完全な沈黙型)。

**期待 vs 実際 (control 実機、mock/auth_error 両シナリオで adapter 未到達を確認)**:
```
scan.pdf (BT無しスキャン PDF) / photo.png / DOCX を index --online → pending ready_for_online_adapter
batch resume (KIO_TEST_MISTRAL_OCR=mock) → exit 4, tasks_executed:0, status=failed/retired_non_live, attempts=1
index --online → batch resume を 3 サイクル → online task 行が毎回再生成 (計 6 行)、adapter は一度も呼ばれず
search → index_status: enriched_ratio=1.0, pending_enrichment_tasks=0 (偽の "完全 enrich 済")
```
期待 = R20-5/R20-6 設計および `docs/07-adapter-spec.md` §2.1 のとおり「非 text-native は online OCR で AI 強化」。実際 = enqueue 側の穴 (R20-4/5/6) は直ったが送信側 precondition が未更新で全タスクを初回試行で永久死。スキャン PDF/画像/OOXML は Step 2 以来一度も OCR に到達せず、R20 の 340 行後もなお到達しない。`KIO_TEST_MISTRAL_OCR` を実駆動するテストがリポジトリに 1 つも無い (`rg KIO_TEST_MISTRAL_OCR --type rust` = catalog.rs の定数宣言のみ) ことが 20 ラウンド素通りの理由。

**修正案**: `online_markdownize_precondition_ok` (6441) と `execute_online_markdownize_task` (6493) の「prepared_units 空=無効」判定を、task の output_ref が online placeholder (`online:{adapter_id}`) の場合は**除外** (空は正常な「全文書 OCR 送信」シグナル)。既存の text-native チェック (6429) と hash 一致チェック (6418) で stale 検出は維持。docs 変更禁止・既存エラーコードのみ。

---

### R21-4 [major] octet-stream / 大文字拡張子の**テキスト**ファイル (`.yaml/.json/.toml/.sh/.html/Dockerfile`/`README.MD`/`NOTE.TXT`) が R9-2 の text-native ゲート (3 canonical MIME 限定) をすり抜け、ローカル索引済みにも関わらず online OCR タスクを重複生成し `--online` で生バイトを外部 API へ送信・課金。offline では恒久 phantom pending で enriched_ratio 劣化

**エンジン**: Claude-Opus (`.yaml/.json/Dockerfile` 送信+課金 control) + GPT-5.5 (大文字拡張子) + オーケストレータ (`README.MD` 送信+課金 5.4e-6 実測)。**脈/型**: R9-2 (text-native→OCR=routing 違反) の適用範囲の絞り漏れ。pre-existing (pre-R20 build でも同一挙動) だが R1-R20 で未報告の新規。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:8260-8262` (`is_text_native_media`) — `text/markdown|text/plain|text/x-code` の **3 MIME のみ**判定。大文字拡張子 (`media_type_for_path`/`media_type_for_cli_path` が `ext` を lowercase せず match、`.MD`/`.TXT`/`.RS` → octet-stream) や content-sniff でテキスト判定された `.yaml/.json` (application/octet-stream) は全て false。
- `crates/kio-cli/src/main.rs:9575` (`enqueue_online_placeholder_task`) — online OCR enqueue のゲートが `is_text_native_media(&candidate.media_type)` なので上記テキストを skip しない。
- `crates/kio-cli/src/main.rs:8986` — ローカル markdownize 成功 (prepared_units 非空) 後、無条件に `enqueue_online_placeholder_task` を呼ぶ。octet-stream テキストは prepared_units 非空 → R21-3 の precondition を**通過して実際に送信される** (R21-3 の binary 経路=空 prepared_units とは別)。

**期待 vs 実際 (control 実機)**:
```
config.yaml / data.json / Dockerfile / README.MD を index --online → 各々 local markdownize done かつ
  online:mistral_ocr_markdownize pending "ready_for_online_adapter"
batch resume (mock) → tasks_executed, cost-ledger adapter_kind="markdown" に課金 (README.MD=5.4e-6 実測)
[offline] index --yes のみ → 上記が online pending "network_opt_in_required" (恒久)、
  index_status pending_enrichment_tasks 増・enriched_ratio 劣化 (.md/code は R9-2 で正しく除外)
```
期待 = R9-2 と同一 (text file を OCR に送るのは privacy 漏出 + 課金 + deterministic pass の二重処理)。content-sniff でテキスト判定した octet-stream も `.md`/code 同様ローカル完結すべき。実際 = 開発者リポジトリの大半 (`.yaml/.yml/.json/.toml/.sh/.sql/.xml/.html/.css/.ini/.cfg` + 拡張子無し `Dockerfile/Makefile/LICENSE` + 大文字拡張子) が対象。Tier A は ingest 除外・Tier B は hold されるため、**名前が秘匿パターン非該当のテキストファイル**が送信対象。

**なぜ major か**: 実際の外部送信・課金には `--online` (明示 opt-in) が要るため critical ではなく明示操作を要する漏出 + cap 消費 = major (R9-2 と同 class)。

**修正案**: online OCR タスクは真の非 text-native media (PDF text-layer 強化 / image / OOXML) のみが対象なので、`enqueue_online_placeholder_task` を「ローカルで File-unit passthrough された octet-stream テキスト」でも早期 return させる (呼び出し側から「local passthrough as text」を示すシグナルを渡す、または prepared_units が単一 File unit かつ media_type==octet-stream なら skip)。加えて MIME 判定前に `ext.to_ascii_lowercase()` して大文字拡張子を正規化し scan/CLI の 2 重実装を統合 (R20-6 が既に触った 2 関数)。空 prepared_units 経由 (真の binary) のみが octet-stream の online 経路を持つべき。

---

### R21-5 [major] R20-4 の `is_probably_real_text` ゲートが文書全体 (`pages.iter().all(...)`) 粒度のため、実テキストページとスキャン(ゴミ)ページが混在する多ページ PDF ではゴミページがそのまま markdown/chunk として永続化・検索露出する

**エンジン**: Claude-Sonnet-C (リポジトリ同梱 fixture) + Claude-Sonnet-D (自作 fixture) + オーケストレータ (mixed.pdf control)。**脈/型**: R20-4 の適用範囲の絞り漏れ (「相似形の粒度違い」— document-level `all()` vs page-level)。

**根本原因 (file:line)**:
- `crates/kio-pipeline/src/prepare.rs:110` — `if pages.iter().all(|page| !is_probably_real_text(page)) { ...empty(OCR送り)... }`。判定が「全ページが非テキストか」の document 全体 AND ゲート。1 ページでも `is_probably_real_text` を通れば残り全ページ (ゴミ込み) がそのまま `prepared_units` に採用される。
- `crates/kio-pipeline/src/prepare.rs:282-293` (`is_probably_real_text`) 自体はページ単位の printable 比率判定だが、結果が個々ページの採否ではなく document 二値判定にしか使われていない。

**期待 vs 実際 (control 実機、offline で再現可)**:
```
mixed.pdf (実テキスト page:1 + ランダムバイト圧縮ストリーム page:2) を index --yes
→ markdownize done, unit_keys=["page:1","page:2"]
→ chunks テーブル: page:1=65 バイトの実テキスト, page:2=2226 バイト (replacement char 975 個) のゴミ ← FTS 索引・検索可能
```
期待 = ページ単位でゴミページのみ「テキストレイヤ無し」判定し OCR (R20-5 経路) へ、実テキストページのみ persist。実際 = 両方 persist。実テキストの表紙/目次 + スキャン画像本文 (またはその逆) は単独スキャン PDF より現実的に高頻度な文書形態で、R20-4 が閉じたはずの「ゴミが証拠として索引される」経路が粒度違いでそのまま残る。

**修正案**: `prepare.rs:102-117` のフィルタを document 全体 `all()` から**ページ単位**に変更。各ページを個別に `is_probably_real_text` で判定し、非テキストページは空文字列に置換 (または prepared_units から除外)、真にテキストが無いページのみ OCR 経路 (R20-5) へ委ねる。

---

### R21-6 [major] `AuthError` (401/403) で失敗した embedding タスクが live 不変ファイルのまま永久固着 — 資格情報を修正しても `index`/`batch retry`/`batch resume`/`repair` のいずれも再開させず、非課金 phantom 予約が当月 cap を永久に食い潰す。reclaim 系列 (R16-7→R19-2→R20-3) は「非 live 化」経路だけを塞ぎ「live 不変」経路を 5 ラウンド一度も検討していない

**エンジン**: Claude-Sonnet-B (control 実機、4 コマンド網羅) + オーケストレータ (control 実機)。**脈/型**: R20-3 の適用範囲の絞り漏れ — R20-3 は非 live 化 AuthError の reclaim を足したが、live のまま詰まる AuthError は未対処。

**根本原因 (file:line)**:
- `crates/kio-pipeline/src/task.rs:338-345` — `retry_policy(AuthError)` = `retryable:false, max_attempts:Some(0)`。
- `crates/kio-cli/src/main.rs:8118-8126` (`task_retry_allowed`) — `policy.retryable` を要求するため `batch retry` から永久に対象外。
- `crates/kio-cli/src/main.rs:7637-7658` (`filter_embeddable_by_task_state`) → `embeddable_task_state` (`7671`) — Failed は `task_retry_due && task_retry_allowed` で `index --online` からも除外。
- `crates/kio-cli/src/main.rs:7991-8004` (`enqueue_embedding_tasks`) — auth_error タスクの output_ref が `existing` に含まれ、`revivable` は `RETIRED_NON_LIVE` 限定なので新規 enqueue も revive も対象外。
- reclaim: task が **live のまま Failed** なので R20-3 の非 live 化 reclaim (`reconcile_committed_embedding_tasks`/supersede/sweep) に一切触れられず、`reserved_usd` が当月 cap を永久消費。

**期待 vs 実際 (control 実機、file 一切未編集)**:
```
index --online (KIO_TEST_GEMINI_EMBED=auth_error) → embedding task failed/auth_error, reserved_usd=2.1375e-6, attempts=1
[資格情報修正 = mock 成功] index --online / batch retry / batch resume / repair --rebuild-db を全て試行
  → 4 通りとも task 変化なし (failed/auth_error のまま)、reserved_usd 据置、reclaim ledger 0 行
唯一 reindex --force (破壊的全再チャンク=chunk_id 変更で非 live 化強制) だけが回復
```
docs/04-pipeline.md:529 は `auth_error user action required max_attempts=0` と明記 — 「資格情報を直せば解決」を暗示するが、実際は直しても定型コマンドで再開しない (機能不全) + phantom 予約が cap を食い続ける (cap drain)。認証エラー (キー誤設定・失効という頻出シナリオ) 後の通常操作で踏む。

**修正案**: `enqueue_embedding_tasks` の revive 対象 (`revivable`) と markdownize の retire 条件に、`retry_kind_from_reason == AuthError` かつ現在 chunk が再び live で `pending` に現れた (=再挑戦価値がある) タスクを含める — R20-2 の in-place revive 機構を流用 (Failed→Pending, `reserved_*`/attempts クリア)。これにより資格情報修正後の再 index が embedding を再開し、非課金 phantom も revive 時に落ちる。RateLimit/Quota は既に batch retry/非 live reclaim で回復するため AuthError 固有の穴。

---

### R21-7 [minor] `hold_secret_embedding_tasks` の `existing` 集合が `RETIRED_NON_LIVE` フィルタを持たず (姉妹関数 `enqueue_embedding_tasks` は持つ)、retired_non_live 化した chunk が Tier B 名で live 再出現しても新規 hold タスクが作られない — held 状態が index_status から見えず (R20-7 が除外) quarantine の "hold" 行だけが手掛かり

**エンジン**: Claude-Sonnet-D (control 実機) + オーケストレータ (control 実機)。**脈/型**: R20-2 revive パターンの横展開漏れ (sendable 分岐にのみ実装、held 分岐に未展開)。

**根本原因 (file:line)**: `crates/kio-cli/src/main.rs:7947-7953` (`hold_secret_embedding_tasks`) — `existing` は status を問わず全 embedding task の output_ref を集める (`fallback_reason` フィルタなし)。対照: `enqueue_embedding_tasks` (`7995-8002`) は R19-3/R20-2 で `RETIRED_NON_LIVE` を `existing` から除外 + in-place revive を実装。この救済が sendable 分岐にしか無いため、retired_non_live 化した chunk が Tier B 名で live 復活すると、古い retired タスクが `existing` に居るせいで新規 hold タスクが作られない。

**期待 vs 実際 (control 実機)**: retired_non_live 化 (rate_limit 失敗→編集で非 live) 後、元バイト列を Tier B 名で復活 → 該当 chunk の embedding task は `failed/retired_non_live` のまま更新されず、Paused hold タスクは作られない。`index_status` は R20-7 の除外で `enriched_ratio:1.0`/`pending:0` (chunk が完全に不可視)、quarantine.jsonl の "hold" 行だけが手掛かり。秘匿送信は起きない (fail-safe) が、`kio status` で held と可視化されるべき chunk が消える observability 欠陥。`--send-secrets` を明示すれば sendable 分岐の revive で回復するため minor。

**修正案**: `hold_secret_embedding_tasks` の `existing` を `enqueue_embedding_tasks` と同じ `.filter(|t| t.fallback_reason.as_deref() != Some(RETIRED_NON_LIVE))` でフィルタし、revivable な RETIRED_NON_LIVE タスクを Paused/`secrets_tier_b_hold` へ in-place revive する (R20-2 の revive を held 分岐へ横展開)。R21-1 の root 修正 (JOIN dedup) 後も held 分岐で独立に必要。

---

## 修正の相互作用 (fix phase の設計協調)

- **R21-1 / R21-2** は一体: root は `live_chunks_without_embedding` の chunk_id dedup (fan-out 根絶) — これで秘匿バイパスと二重課金の両方が消える。R21-1 は加えて `embeddable_task_state` の secrets-hold 明示除外を defense-in-depth として入れる。dedup の path tiebreak は「秘匿パス優先」で R20-1 (現在パス秘匿判定) の趣旨と整合。
- **R21-3 / R21-4 / R21-5** は file-routing の一体クラスタ: R21-3 (executor precondition の空許容) が効くと真に text-layer 無しの PDF/画像/OOXML が OCR に到達する。R21-4 (octet-stream テキストの online skip) がテキスト設定ファイルを local に留める。R21-5 (page 単位 real-text 判定) が混在 PDF のゴミページのみ OCR へ回す。**3 者を順に設計 (R21-4 → R21-5 → R21-3)**、docs 変更禁止・既存エラーコードのみ。
- **R21-6 / R21-7** は R20-2 revive 機構の横展開: R21-6 は AuthError の live-stuck を revive 対象に、R21-7 は held 分岐に revive を展開。両者とも R20-2 の in-place revive を再利用するため一体で設計。
- **注意**: R21-1 の JOIN dedup が R21-7 の held 分岐にも影響 (fan-out 消滅で 1 chunk=1 パス)。R21-7 の held 分岐 revive は dedup 後も独立に必要 (retired_non_live→hold 遷移は fan-out と無関係)。

**推奨実装分担**: R21-1/R21-2 (JOIN dedup + embeddable_task_state、秘匿・会計 delicate) と R21-6/R21-7 (revive 横展開) はオーケストレータ or 単一 Agent が context 保持。R21-3/R21-4/R21-5 (file-routing) は別 Agent。各 fix ごとにターゲット絞りテスト + critical/major は control 付き実機 repro クローズ。

---

## 探索したが問題なしと確認した領域 (multi-engine 健全確認)

- **R20-2 in-place revive の会計整合性**: revive 時 `attempts=0`/`reserved_*=None` にリセット、reclaim は revive 前の `retire_online_task_reclaiming` で stamp クリア後に先行実行 (Opus/Sonnet-A/B/C/D 独立確認)。「reclaim すべき予約を握り潰す」逆行破れは無し (R21-1/R21-2 の重複は revive 由来ではなく JOIN fan-out という別ソース)。
- **R20-1 `te.path` の他 consumer**: `EmbeddableChunk.raw_path` は secret gate (7188) と task input_path (7963/8038) のみに流れ現在パス化が正。表示/Evidence は DB `chunks.raw_path` (append-only) を別途読むため無影響 (Opus/Sonnet-A/B 確認)。ただし同 JOIN の fan-out が R21-1/R21-2 の根。
- **R20-1 markdownize 版リネーム攻撃**: `execute_online_markdownize_task` は送信直前にディスク再読込 + content-hash 照合するためリネームで旧パス消失は `InvalidInput` で安全失敗、漏洩なし (Sonnet-B 確認)。
- **R20-3 AuthError reclaim allowlist**: `reclaim_entry_for` (9524) / `is_reservation_bearing_send_failure` (8146) 双方に AuthError が入り整合 (逆方向の live-stuck が R21-6)。
- **R20-4 CJK 誤検知**: `is_probably_real_text` は CJK/日本語を `is_control()==false` で printable 扱い、85% 閾値通過 → 日本語テキストレイヤ PDF が OCR に落ちる false-negative は無し。空文字列でゼロ除算なし (`total==0 → false`) (Sonnet-A/C/D + GPT-5.5 + Spark 確認)。
- **R20-9 quarantine latest-per-path / R20-10 held chunk 除外 self-heal / R20-11 fail-closed 閾値**: いずれも健全 (Sonnet-A/B/C/D 確認)。R20-10 は `--send-secrets` 後 `release_secret_holds`→`rebuild_chunk_vec` の順で held 解除 chunk が再リンク。R20-11 の `-1e-9` 閾値は f64 誤差で誤発火せず。
- **Spark 検証2 (a)(b)(d) / R20-1 shallow tree_entries**: `ensure_snapshot_tree_entries` は R20-1 以前から JOIN が tree_entries 依存 (R20-1 は SELECT 列変更のみで JOIN 構造不変)、shallow 時 0 件は pre-existing・comment (7150-7152) で説明済み・handled。R20 regression ではない。

## 据え置き (1 件)

- **FlateDecode/zlib 展開の不在** (Sonnet-C): `pdf_stream_text_pages`/`pdf_literal_strings` はいずれも `String::from_utf8_lossy(生バイト)` を読み、`rg 'flate|inflate|deflate|zlib' crates/kio-{adapter,pipeline}` = 0 件。Word/ブラウザ印刷/LaTeX 生成 PDF は content stream をほぼ FlateDecode 圧縮するため、docs/07:71 の「ローカル PDF text layer 抽出」が実運用 PDF の大多数で機能せず OCR 経路 (R21-3 修正後は正しく OCR、offline は永久 pending) へ落ちる。**correctness の主部は R21-3 (OCR 到達) で解消**、残る「ローカル無料抽出すべき」はコスト最適化/機能拡張であり R20 regression ではない (pre-existing・design)。flate 展開実装は Step 4 or 別途 enhancement として据え置き、docs 凍結解除時に「圧縮 PDF は OCR 必須」を開示検討。

## 却下 (0 件)

なし。全エンジンの採択所見が実機 or file:line で立証 (R9・R16・R19・R20 に次ぐ 5 回目の却下 0)。多エンジン非重複 (critical 1 + major 5 が複数方向: JOIN fan-out 秘匿 [Sonnet-C] / JOIN fan-out 会計 [Opus+GPT-5.5] / OCR dead-end [Sonnet-A/B+GPT-5.5 4 収束] / octet-stream routing [Opus+GPT-5.5] / mixed-page garbage [Sonnet-C/D] / AuthError live-stuck [Sonnet-B])。
