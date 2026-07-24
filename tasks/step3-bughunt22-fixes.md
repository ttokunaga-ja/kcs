# 探索型監査 第22ラウンド (R22) — 裁定と修正計画

7 エンジン (Claude-Opus / Sonnet-A / Sonnet-B / Sonnet-C / Sonnet-D / GPT-5.6-Sol-Ultra / GPT-5.3-Codex-Spark)。
HEAD `5d0b926`、全 485 テスト green・clippy(--all-features)/fmt clean の状態から開始。
※本ラウンドから静的枠の主力を GPT-5.5 → **GPT-5.6-Sol-Ultra** (`model_reasoning_effort=ultra`, multi_agent) に交代。

**結果: 0 critical + 6 major + 2 minor。却下 4。据え置き 2 (継続)。**

本ラウンドは「R21 fix が開ける穴」(定番脈 **11 例目**) が本命的中し、**2 つのクラスタ**に集約された:

1. **embedding task 状態が「現在の秘匿分類 × liveness」に一度も再収束しない** (R22-1/2/3)。
   R21-1 は `live_chunks_without_embedding` の JOIN fan-out を dedup し、`embeddable_task_state` に
   「`secrets_tier_b_hold` は絶対に再駆動しない」defense-in-depth を入れた。R21-7 は held 分岐に
   `RETIRED_NON_LIVE` revive を横展開した。しかしこれらはすべて **task を「作る」方向**の修正で、
   **「作られた task を現在の事実に合わせて直す」経路が存在しない**。結果、同一根から 3 方向の恒久固着が噴出:
   - **R22-1**: 秘匿 → 非秘匿 (rename-out / 秘匿双子の削除) で hold が**解除されない** (Opus + Spark + オーケストレータ)
   - **R22-2**: 非秘匿 → 秘匿 (rename-in) で既存 task が hold へ**降格されない** (Sonnet-A + Sonnet-B + オーケストレータ)
   - **R22-3**: hold されたまま chunk が非 live 化しても**退役されない** (Sonnet-C + Sol + オーケストレータ)
   `held`/`sendable` の partition は毎回 `te.path` (R20-1) で正しく再計算されるのに、その結論が
   **task store へ一度も書き戻らない**のが真因。3 面すべて「送信は起きない (fail-safe)」が、
   ベクタ検索からの恒久脱落・`index_status` の恒久汚染・`--send-secrets` (セキュリティ姿勢の恒久引き下げ)
   以外に回復手段が無いという実害を持つ。

2. **R21-4 の file-routing ガードが「新規 enqueue だけ」を直し、既存状態と受け皿を放置** (R22-4/5)。
   - **R22-4**: `!= "application/octet-stream"` ガードが未認識拡張子の**実バイナリ文書**を無音消失させる
     (task 皆無・event log 皆無・`enriched_ratio` 偽 1.0)。**pre-R21 では pending task として可視だった回帰**
     (Sonnet-B が `6288584` を別ビルドして実証)。
   - **R22-5**: 旧 build が enqueue 済みの online task を退役させないため、**upgrade 後の `batch resume` が
     `.yaml/.json/Dockerfile` の生バイトを Mistral へ送信・課金**する。R21-4 は enqueue 側だけを直し、
     executor の text-native 判定は 3 canonical MIME のままだった。

加えて **R22-6** [major] — R21-6 の AuthError live-stuck revive が (a) markdownize へ横展開されず、
(b) `reserved_usd` stamp の有無に依存するため legacy task を救えない (Sol 静的 + オーケストレータ control 実機 ×2)。

**R22-1〜R22-6 は全てオーケストレータが `/tmp` 隔離 `XDG_DATA_HOME` 下で control 付き実機再現・会計値実測済み。**

---

## 所見一覧 (severity 降順)

### R22-1 [major] 秘匿名から非秘匿名へのリネーム (または秘匿双子の削除) 後、embedding タスクが `Paused/secrets_tier_b_hold` に恒久固着し、`index`/`batch retry`/`batch resume`/`repair --rebuild-db`/`reindex --force --yes` のいずれでも解除されない — 現存する非秘匿ファイルの本文がベクタ検索から恒久脱落し、回復手段は意味的に誤った `--send-secrets` (scope 全体の秘匿送信を**永続承認**する) のみ

**エンジン**: Claude-Opus (control 実機・全回復コマンド網羅) + GPT-5.3-Codex-Spark (検証1(a) を file:line で静的特定) + オーケストレータ (独立 control 実機)。
**脈/型**: 「fix が開ける穴」11 例目・**適用範囲の広げ過ぎ** (R17-1 と同型)。R21-1 の root fix (JOIN dedup) は正しく穴を塞いだが、
併せて入れた defense-in-depth (`embeddable_task_state` の `SECRETS_TIER_B_HOLD => false`) が
**「hold の解除」という正当な遷移まで恒久的に禁止**した。R20-1 が捕捉した「非秘匿→秘匿」方向の**対**が未実装。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:7219-7226` — `pending` を `held`/`sendable` に partition。`hold_secret_embedding_tasks(held)` で
  新規 hold を作る一方、**チャンクが `held` → `sendable` に転じたときに hold を解除する対称処理が存在しない**。
- `crates/kio-cli/src/main.rs:8136-8145` (`enqueue_embedding_tasks` の `existing`) — `RETIRED_NON_LIVE` のみ除外。
  Paused/`secrets_tier_b_hold` は `existing` に含まれるため `continue` され、新規 Pending task も作られない。
- `crates/kio-cli/src/main.rs:7709` (`embeddable_task_state`) — `Some(SECRETS_TIER_B_HOLD) => false` (R21-1 の防御) により、
  仮にフィルタへ到達しても held task は決して再駆動されない。
- `crates/kio-cli/src/main.rs:10291-10306` (`release_secret_holds`) — Paused/hold → Pending へ戻す唯一の関数。
  呼出しは `main.rs:615-617` の `if args.send_secrets` のみ。再 index 時の解除経路が皆無。

**期待 vs 実際 (control 付き実機、`KIO_TEST_GEMINI_EMBED=mock`、回復コマンドを個別のクリーン scope で網羅)**:
```
[CONTROL] notes.md のみ                          → embedding task done、embeddings=1
[EXP-A] password_notes.md を index --online      → paused/secrets_tier_b_hold、embeddings=0
        → mv password_notes.md notes.md (非秘匿)
        → index / batch retry / batch resume / repair --rebuild-db / reindex --force --yes を個別に試行
        → 5 通りとも paused/secrets_tier_b_hold のまま、embeddings=0
        → index --online --send-secrets  ← これだけが done/embedding_adapter_done へ解放
[EXP-B] password_backup.md + notes.md (byte-identical) を index → dedup で秘匿側が生存し held
        → rm password_backup.md (秘匿双子を削除)、全回復コマンド試行 → embeddings=0 のまま
[observability] kio status は**存在しないパス** password_notes.md の approval_method="hold" を報告し続け、
                notes.md は files[].status="unchanged" とだけ出る (脱落の手掛かりゼロ)
```
期待 = 現在パスが非秘匿なら R20-1 と対称に hold を解除して通常 embed。実際 = 永久 held。

**なぜ major か**: Tier B は名前ヒューリスティック (`credentials|secret|token|apikey|password` を含む) なので
`password_reset_flow.md` / `token_bucket.md` / `oauth_credentials_guide.md` のような**誤検知が常態**。
それを非秘匿名にリネームする、あるいは秘匿バックアップコピーを消すという日常操作だけで踏む。
かつ唯一の回復手段 `--send-secrets` は `secrets-approved.jsonl` に scope 束縛の承認行を append し
(`main.rs:10269-10286`)、以後 `secrets_send_approved` が恒久的に true を返す (`main.rs:10252-10265`) ため、
**非秘匿ファイル 1 個を救うために scope 全体の Tier B 送信を永久承認させられる**。漏出は起きない (fail-safe) が、
機能の恒久喪失 + セキュリティ姿勢の恒久引き下げの強制であり critical ではなく major。

**エンジン判断の裁定**: Claude-Sonnet-D は本件を「`release_secret_holds` が存在するので恒久固着の主張は成立しない
(自己修正機構あり)」として**健全と誤判定**した。しかし `release_secret_holds` の呼出しは `--send-secrets` 経路のみで、
上記 control 実機のとおり通常回復コマンドは 5 通りとも無力。**R13/R15/R17/R18 の Opus doc-gap 型の 5 例目**
(今回は Sonnet-D)。エンジンの不採択判断も裁定対象という原則を再確認。

**修正案**: `enqueue_embedding_tasks` (sendable 分岐) の `revivable` に「Paused かつ `secrets_tier_b_hold`」を追加し、
R20-2 の in-place revive を流用して Paused → Pending (`fallback_reason = reason`) へ戻す。`input_path` も現在パスへ更新する。
`sendable` に到達している事実そのものが「現在 live なパスのどれも秘匿でない (dedup は秘匿優先なので、
秘匿パスが 1 つでも live なら生存者は秘匿側)」ないし「`--send-secrets` 承認済み」を意味するので、
R21-1 の不変条件 (hold は非秘匿双子に再駆動されない) を壊さずに解除できる。`embeddable_task_state` の
defense-in-depth はそのまま維持する。

---

### R22-2 [major] 既に非 hold な embedding タスク (Pending/Failed/Done) を持つチャンクは、現在パスが後から Tier B 秘匿名になっても `Paused/secrets_tier_b_hold` へ**降格されない** — `hold_secret_embedding_tasks` の idempotency ガードが降格自体を永久に妨げ、`kio status` のタスク一覧と `quarantine.jsonl` の "hold" 記録が恒久的に矛盾する

**エンジン**: Claude-Sonnet-A (control 実機・4 コマンド網羅) + Claude-Sonnet-B (独立 control 実機・AuthError/RateLimit 経由でも再現) + オーケストレータ (独立 control 実機)。
**脈/型**: R21-7 の**適用範囲の絞り漏れ**。R21-7 は `existing` から `RETIRED_NON_LIVE` だけを特例除外したが、
「既存タスクがあれば無条件 skip」という根本設計は不変のまま。R22-1 の**逆方向**。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:8055-8060` (`hold_secret_embedding_tasks` の `existing`) — `task_type == Embedding &&
  fallback_reason != RETIRED_NON_LIVE` のみでフィルタ。既存タスクの `status` も現在の held 該当性も一切見ない。
- `crates/kio-cli/src/main.rs:8069-8072` — `existing.contains(&output_ref)` なら**無条件 `continue`**。
  よって `held` に落ちたチャンクの既存タスクは Paused へ昇格されず、`sendable` にも入らないので送信もされない
  (完全に浮遊した状態)。
- R21-6 の revive (`main.rs:7900-7929`) が `fallback_reason = None` にクリアした task も、
  `RETIRED_NON_LIVE` ではないため `existing` に含まれ、同じく降格されない (Sonnet-B の経路)。

**期待 vs 実際 (control 付き実機)**:
```
plain.md を offline index          → embedding task pending/network_opt_in_required
mv plain.md credentials_backup.md  → quarantine.jsonl に approval_method="hold" が記録される
index / index --online / batch resume / batch retry / repair --rebuild-db を全試行
  → task は pending/network_opt_in_required のまま (paused/secrets_tier_b_hold にならない)
  → embeddings=0 (送信はされない = fail-safe。R21-1 dedup + partition が送信側を守っている)
```
期待 = チャンクの現在パスが秘匿名になった時点で、既存タスクの状態に関わらず `Paused/secrets_tier_b_hold` に収束し
`kio status` に held として可視化される (N1a / R19-1 の開示契約)。実際 = `fallback_reason` が無関係な値
(`network_opt_in_required` / `null`) のまま張り付き、「オンライン承認すれば直る」と利用者を誤誘導する一方、
quarantine は "hold" を主張し続ける。恒久 pending として `index_status` も汚染する。

**なぜ major か**: 実送信は起きない (R21-1 の partition が毎回コンテンツベースで再計算されるため) ので漏出は無いが、
**秘匿ホールドの開示契約 (N1a) が破れ**、標準の回復コマンドが 4 通りとも無力な恒久停滞である点で R21-6 と同格。

**修正案**: `hold_secret_embedding_tasks` の `existing` を「`status == Paused` かつ `fallback_reason == SECRETS_TIER_B_HOLD`」
に絞り、それ以外の非 `RETIRED_NON_LIVE` な既存タスク (Pending/Failed) は in-place で
`Paused`/`secrets_tier_b_hold` へ**降格**する。`Done` は既にベクタが存在する (実支出済み) ため降格せず、
R20-10 の `rebuild_chunk_vec` 除外に委ねる (`Done` を Paused に戻すと会計が壊れる)。

---

### R22-3 [major] `Paused` タスク (`secrets_tier_b_hold` / `budget_exceeded`) は chunk が非 live 化しても `retired_non_live` へ退役されず、編集のたびに孤児が**無制限に累積**して `index_status` を恒久汚染する — R15-7/R19-3/R21-6 が Pending/Running/Failed に用意した自己修復から `Paused` だけが漏れている

**エンジン**: Claude-Sonnet-C (control 実機・4 回編集で孤児 4 本を実測) + GPT-5.6-Sol-Ultra (R22-8 として静的特定) + オーケストレータ (独立 control 実機)。
**脈/型**: 「fix が適用範囲を絞った際の**相似形の隣**」(R16-1 と同型)。reconcile の 2 つの sweep がどちらも
`Paused` を状態集合から落としている。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:7876-7886` (reclaim sweep) — `matches!(task.status, Pending | Running | Failed)` で `Paused` を除外。
- `crates/kio-cli/src/main.rs:7967-7972` (retire-non-live sweep) — `if !matches!(task.status, Pending | Running) { continue; }`
  で `Paused` を除外。
- 結果、hold されたまま編集/削除された chunk の task は永久に `Paused` のまま `compute_index_status`
  (`main.rs:2446-2458`) に pending として数えられる。

**期待 vs 実際 (control 付き実機)**:
```
secret_notes.md を index --online → paused/secrets_tier_b_hold ×1
同ファイルを 3 回編集して都度 index --online
  → paused/secrets_tier_b_hold ×4 (旧 chunk の 3 本は非 live なのに退役しない)
batch resume / repair --rebuild-db → 無変化
search index_status → {enriched_ratio: 0.5, pending_enrichment_tasks: 4, budget_paused: true}
```
期待 = 非 live 化した chunk の task は `retired_non_live` へ落ち、`enriched_ratio` は現行コーパスのみを分母にする
(R20-7 の趣旨)。実際 = Tier B ファイルを普通に編集し続けるだけで孤児が線形に増え、`enriched_ratio` が単調劣化する。

**修正案**: reconcile の retire-non-live sweep (7967-7972) の状態集合に `TaskStatus::Paused` を追加する。
`secrets_tier_b_hold` の hold は `reserved_usd` を持たない (`main.rs:8088`) ので reclaim は無害な no-op、
`budget_exceeded` の Paused は stamp を持ち得るため既存の `retire_online_task_reclaiming` の error-kind 判定に委ねる
(R16-7 の NetworkError 保守は維持)。退役の reason は R19-3 の可逆 `retired_non_live` を使うので、
同一バイト列が復活した際は R21-7 の revive で hold に戻る (相互作用は下記参照)。

---

### R22-4 [major] R21-4 が新設した `!= "application/octet-stream"` ガードにより、拡張子が MIME テーブルに無い**実バイナリ文書** (`.bmp/.tiff/.heic/.avif/.doc/.xls/.ppt/.odt/.epub/.rtf` 等) が索引パイプラインから完全に無音消失する — タスク皆無・event log 皆無・カウンタ皆無で `enriched_ratio` は偽の 1.0 を報告し、全回復コマンドが無力。**pre-R21 では pending task として可視だった回帰**

**エンジン**: Claude-Sonnet-B (control 実機 + `6288584` を別ビルドして pre/post 比較=**回帰であることを実証**) +
Claude-Sonnet-D (独立 control 実機・全回復コマンド網羅) + オーケストレータ (独立 control 実機)。
**脈/型**: 「fix が開ける穴」— **除外ロジックの過剰適用** (genuine binary と unrecognized-extension document の同一視)
+ 「observability の失敗系素通り」脈との合流。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:8847` — `if prepare.prepared_units.is_empty() {`
- `crates/kio-cli/src/main.rs:8858-8862` — R21-4 の新規ガード `if candidate.media_type != "application/octet-stream" {
  enqueue_online_placeholder_task(...)?; }`
- `crates/kio-cli/src/main.rs:8879` — `continue;` (`result.failed_files` / `skipped_*` 増分も `append_event_log` も無い)
- **対比**: 同一ループの oversized 処理 (`main.rs:8787-8798`) は `result.skipped_oversized_files += 1` +
  `append_event_log("KIO-I-INDEX-INPUT-OVERSIZED-001", ...)` を必ず伴う。R21-4 の新ガードだけがこのパターンを踏襲していない。
- `media_type_for_cli_path` (`main.rs:8370-8397`) / `media_type_for_path` (`scan.rs:418-445`) は
  png/jpg/jpeg/webp/gif と docx/xlsx/pptx のみ実 MIME を割り当て、それ以外は全て `application/octet-stream` に丸める。

**期待 vs 実際 (control 付き実機、offline)**:
```
photo.bmp (BM ヘッダ + ランダム 2000 B) と ok.md を index --yes
→ {"status":"indexed","normalized_files":1,"failed_files":0,"pending_online_tasks":0,"skipped_oversized_files":0}
→ tasks.jsonl に photo.bmp を含む行 0 件 (grep exit=1)、logs/*.jsonl に photo.bmp の言及なし
→ search の index_status = {enriched_ratio: 1.0, pending_enrichment_tasks: 0}   ← 偽の「完全 enrich 済」
→ batch retry / batch resume / reindex --force --yes / repair --rebuild-db を全試行 → 一切タスク化されない
[pre-R21 (6288584) の同一 .bmp] → pending_online_tasks: 1、status --json に markdownize/pending/ready_for_online_adapter
```
期待 = 索引対象と判定されたファイルは「enrich 済」か「pending/failed として可視」かのいずれかになる (oversized の前例)。
実際 = HEIC (iPhone 既定) や legacy `.doc/.xls/.ppt` など実世界で頻出する形式が痕跡ゼロで消える。

**なぜ major か**: R9-4 / R20-4 と同じ **silent data gap クラス** (exit 0 + `enriched_ratio` 偽 1.0)。
証拠アーカイブの中核価値 (「索引したはずのファイルが実は無い」) を直撃する。

**修正案**: R21-4 のガードは撤回せず (撤回すると R21-3 の AwaitOcr で永久 pending になり churn 懸念が戻る)、
oversized と同じ可視化パターンを与える: `IndexPipelineResult` に `skipped_unrecognized_binary_files` カウンタを追加し、
既存の event log 機構で `KIO-I-INDEX-*` 系の **INFO イベント**を 1 行記録する
(docs 凍結下なので `KIO-E-*` エラーコード新設は行わない = R17-4/R18-4/R19-6 の教訓)。
`kio status` / `index --json` の双方から可視化する。

---

### R22-5 [major] R21-4 は **fresh enqueue だけ**を PDF 限定にし、旧 build が生成済みの `online:mistral_ocr_markdownize` タスクを退役させない — upgrade 後の `batch resume` が `.yaml/.json/.toml/Dockerfile` 等 octet-stream テキストの生バイトを Mistral OCR へ送信し課金する。executor 側 precondition の text-native 判定は 3 canonical MIME のままで素通しする

**エンジン**: GPT-5.6-Sol-Ultra (R22-1 として静的に呼出経路まで特定) + オーケストレータ (control 実機で送信・課金を実測)。
**脈/型**: **「fix の適用範囲が新規状態だけで、既存状態のマイグレーションが無い」** — taxonomy の新変種。
R21-4 は「これから作る task」を直したが、「すでに tasks.jsonl に存在する task」を放置した。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:8896` — R21-4 の fresh enqueue ガード (新規 task のみ抑止)。
- `crates/kio-cli/src/main.rs:6463` (`classify_online_markdownize_precondition`) — `is_text_native_media(&media_type)` は
  `text/markdown|text/plain|text/x-code` の 3 MIME のみ。`.yaml/.json/Dockerfile` は `application/octet-stream` なので **false**。
- `crates/kio-pipeline/src/prepare.rs:90` — octet-stream でも `bytes_are_text()` が true なら `prepared_units` は非空。
  よって precondition は **`Send`** を返す。
- `crates/kio-cli/src/main.rs:6484, 6513-6517` (`execute_online_markdownize_task`) — 同じ 3 MIME 判定なので
  第二ゲートも素通しし、生バイトを adapter に渡す。

**期待 vs 実際 (control 付き実機、旧 build 相当の legacy task を tasks.jsonl に注入して upgrade を再現)**:
```
config.yaml を R21 適用済み build で index --yes → online task は作られない (R21-4 の enqueue ガードは正しく効く)
旧 build 相当の legacy task (output_ref=online:mistral_ocr_markdownize, input_path=config.yaml) を注入
index --online --approve --yes; batch resume (KIO_TEST_MISTRAL_OCR=mock)
→ {"status":"resumed","tasks_attempted":1,"tasks_executed":1,"tasks_failed":0}
→ legacy task = done/online_adapter_done、cost-ledger の adapter_kind="markdown" に課金行 1 件
```
期待 = R21-4 後は octet-stream テキストがローカル完結する (R9-2 の routing 契約)。
実際 = R21 以前に `--online` で索引した既存 scope をそのまま upgrade すると、次の `batch resume` で
設定ファイル・スクリプト・Dockerfile の中身が外部 API へ送られ課金される。

**なぜ major か**: 実送信・課金が起きるが `--online` + 永続 opt-in という明示操作を要するため critical ではなく
R9-2 / R21-4 と同 class の major。開発者リポジトリの `.yaml/.json/.toml/.sh/.sql/Dockerfile` が対象。

**修正案**: precondition (`classify_online_markdownize_precondition`) と executor
(`execute_online_markdownize_task`) の双方で、**「`application/octet-stream` かつローカルで text として
passthrough された (= `prepared_units` が単一 File unit)」タスクを `Retire` / 非 retryable `InvalidInput` にする**。
これは R21-4 の enqueue ガードの送信側ミラーであり、legacy task を安全に退役させる (R9-2 の
「defense in depth」コメントが宣言している役割を実際に果たさせる)。

---

### R22-6 [major] R21-6 の AuthError live-stuck revive が (a) markdownize パイプラインへ横展開されず、(b) `reserved_usd` stamp の有無に依存するため stamp 無し legacy embedding タスクを救えない — 資格情報を修正しても恒久固着し、markdownize 側は phantom 予約 (実測 1.523e-4) が当月 cap を食い続ける

**エンジン**: GPT-5.6-Sol-Ultra (R22-2 として静的に両欠落を特定) + オーケストレータ (control 実機 ×2 で実証)。
**脈/型**: **「fix の横展開漏れ」** (R18-1 と同型・2 例目) + **「revive の前提条件が広すぎる guard に阻まれる」**。
R21 の裁定文自身が markdownize への展開を要求していた (`tasks/step3-bughunt21-fixes.md:173`) が、実装は embedding のみ。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:7901-7929` — R21-6 の revive は `reconcile_committed_embedding_tasks` の中、
  つまり **embedding 専用**。markdownize の live AuthError task を扱う対応物が存在しない。
- `crates/kio-cli/src/main.rs:7877-7882` — 同関数の先頭 guard が `task.reserved_usd.is_none()` を `return false` で弾く。
  `reserved_*` は R18-1 以降に導入された optional フィールド (`crates/kio-pipeline/src/task.rs:61`) なので、
  **それ以前に作られた AuthError タスクは revive に到達しない**。
- `crates/kio-pipeline/src/task.rs:338-345` — `retry_policy(AuthError)` = `retryable:false, max_attempts:Some(0)` により
  `batch retry` からも `filter_embeddable_by_task_state` からも永久に除外される。

**期待 vs 実際 (control 付き実機)**:
```
[markdownize] mixed.pdf を index --online --approve; batch resume (KIO_TEST_MISTRAL_OCR=auth_error)
  → exit=5、online task = failed/auth_error、reserved_usd=1.523e-4
  → 資格情報修復 (mock) 後、index --online / batch retry / batch resume / repair --rebuild-db を全試行
  → failed/auth_error、reserved_usd=1.523e-4 のまま (4 通りとも無変化。phantom が cap を食い続ける)
[embedding legacy] auth_error で失敗させた後、reserved_usd/reserved_month を null に落とす (旧 build 相当)
  → mock で index --online / batch retry / batch resume → failed/auth_error のまま、embeddings=0
```
期待 = 資格情報を直せば定型コマンドで再開する (docs/04-pipeline.md:529 の `auth_error user action required` の含意)。
実際 = markdownize は恒久固着 + phantom cap drain、legacy embedding は恒久固着。

**修正案**: (a) markdownize の実行ループにも「live かつ Failed(AuthError) なら revive (Failed→Pending,
`attempts=0`, 予約は `reclaim_entry_for` で回収してから clear)」を追加する。既存の共有ヘルパー
`retire_online_task_reclaiming` と同じ error-kind 判定 (AuthError は非課金なので reclaim 可、
NetworkError は保守的に据え置き=R16-7) を再利用する。
(b) reconcile 先頭 guard の `reserved_usd.is_none()` 早期 return をやめ、**状態 revive は stamp の有無に依存させず、
reclaim だけを stamp 有無で分岐**させる (stamp が無ければ reclaim は no-op)。

---

### R22-7 [minor] `compute_index_status` があらゆる `Paused` を `budget_paused=true` に写像するため、予算残 $50 でも Tier B 秘匿ホールドを 1 件持つだけで「予算により一時停止中」と誤報告する (docs/05-runtime.md:200 の人間向け翻訳契約に違反)

**エンジン**: Claude-Opus (minor) + Claude-Sonnet-C (major)。**severity は minor で裁定** (下記)。
**脈/型**: Agent 契約フィールドの誤ラベル。N1a (秘匿ホールド) 導入以来の pre-existing だが全 21 ラウンド未報告・非重複
(R11-8 は Failed を pending に数えない**偽陰性**で別物・別行)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:2455-2458` — `TaskStatus::Paused => { pending += 1; budget_paused = true; }` が
  `fallback_reason` を一切見ない。
- Paused の `fallback_reason` は 2 種のみ (`budget_exceeded` = `main.rs:7470-7476`/`6130-6131`、
  `secrets_tier_b_hold` = `main.rs:8093`/`8110`)。後者は予算と完全に無関係。
- `docs/05-runtime.md:200` — 「人間向け表示では『AI 強化 42% (**budget により一時停止中**)』のような 1 行警告に翻訳する」。

**期待 vs 実際 (control 実機、リネーム不要・Tier B ファイルが 1 つ live なだけ)**:
```
password_reset_flow.md (Tier B 誤検知だが実体は非秘匿ドキュメント) を index --online
kio status → budget: device_remaining_usd=50.0, device_spent_usd=0.0, warned=false  (予算は無傷)
kio search  → index_status: {budget_paused: true, enriched_ratio: 0.5, pending_enrichment_tasks: 1}
```
期待 = `budget_paused` は予算枯渇 (`device/folder_remaining <= 0`) または `budget_exceeded` Paused のみ真。
実際 = 秘匿ホールドで真になり、Agent は「予算を上げれば解決」と誤誘導される (正しい対処は `--send-secrets`)。
R22-1 と合わさると、リネームで固着したファイルが以後**永久に** `budget_paused=true` を出し続ける。

**severity 裁定**: Sonnet-C は major を主張したが、(i) データ喪失も漏出も無い、(ii) `kio status` の
`tasks[].fallback_reason` と `quarantine[]` から正しい理由は判別可能、(iii) 実装側コメント
(`main.rs:2418-2419`) は「`budget_paused` is any paused task」と自己記述しており内部的には一貫している、
の 3 点から **minor** (Opus の裁定) を採る。docs 側の文言が実装より狭いという drift。

**修正案**: `main.rs:2455` の Paused アームを `fallback_reason` で分岐し、`budget_exceeded` のときだけ
`budget_paused = true` にする (`secrets_tier_b_hold` は `pending += 1` のみ)。
`budget_paused` の意味を docs/05:200 の文言に合わせる方向で、docs は変更しない。

---

### R22-8 [minor] 日次ログローテーションの check-then-rename が無ロックのため、日跨ぎ後の最初の並行 append 2 本で前日ログ全体を失う

**エンジン**: GPT-5.6-Sol-Ultra (R22-6 として静的特定・interleaving を提示)。
**脈/型**: R13-3 が導入したローテ機構の TOCTOU。「非アトミック writer」脈の残り。

**根本原因 (file:line)**:
- `crates/kio-core/src/scope.rs:1224-1228` (`append_jsonl_rotating`) — `rotate → prune → append` に排他が無い。
- `crates/kio-core/src/scope.rs:1247-1250` (`rotate_stale_log`) — `if !dated.exists() { fs::rename(path, &dated)?; }`。

**成立する interleaving**: P1/P2 が同じ stale live file を stat し、どちらも `dated.exists() == false` を観測する
→ P1 が旧 live を `dated` へ rename し (前日分を保存)、新 live に 1 行 append する
→ P2 が **その新 live** を同じ `dated` 名へ rename する。POSIX/macOS の `rename(2)` は既存 destination を
置換するため、P1 が保存した前日履歴が unlink される。

**期待 vs 実際**: 期待 = 並行 append でも全行保存される (関数 doc-comment が「rename は atomic で行を失わない」と主張)。
実際 = 日跨ぎ直後 (または数日 idle 後) の並行初回操作で `events/errors/metrics/access` の前日履歴を丸ごと失い得る。

**severity 裁定**: 窓が「日跨ぎ後の最初の 2 本が同時」に限られ、失われるのは観測ログのみ (Evidence/index は無傷)、
ローテ失敗は既に非致死と裁定済み (R12-5/R13-3) のため **minor**。

**修正案**: ローテ + prune + append の全体を、対象ログごとの排他ロック下で行う
(既存の device lock ヘルパーを流用し、`.kio/logs/<stem>.lock` を取る)。
`dated.exists()` の再チェックをロック内で行えば TOCTOU が閉じる。

---

## 修正の相互作用 (fix phase の設計協調)

- **R22-1 / R22-2 / R22-3 は一体設計**。三者は「embedding task を現在の事実 (現在パスの秘匿分類 × chunk の liveness) に
  再収束させる」という単一の欠落の 3 面。実装は 1 箇所に集約するのが安全:
  1. `hold_secret_embedding_tasks` の `existing` を「Paused かつ `secrets_tier_b_hold`」に絞り、
     非 hold な既存タスク (Pending/Failed) は **hold へ降格** (R22-2)。`Done` は降格しない (会計・既存ベクタを壊す)。
  2. `enqueue_embedding_tasks` の `revivable` に「Paused かつ `secrets_tier_b_hold`」を追加し、
     sendable に転じたチャンクの hold を **Pending へ解除** (R22-1)。`input_path` も現在パスへ更新。
  3. reconcile の retire-non-live sweep に `Paused` を加え、非 live 化した hold を `retired_non_live` へ **退役** (R22-3)。
  - **順序の不変条件**: reconcile (退役) → partition (held/sendable) → hold 降格 → enqueue/解除、の順で、
    1 パス内に「降格した直後に解除する」振動が起きないこと。partition は `te.path` 由来なので、
    同一パスで held かつ sendable になることは無い (dedup が秘匿優先で 1 インスタンスに畳むため)。
  - **R21-1 の不変条件は不変**: `embeddable_task_state` の `SECRETS_TIER_B_HOLD => false` は**維持する**。
    解除は必ず「sendable に到達した」という partition の結論を経由し、`embeddable_task_state` を迂回しない。
  - **R19-3 との整合**: R22-3 の退役は可逆 `retired_non_live` を使うので、同一バイト列が Tier B 名で復活したら
    R21-7 の revive が hold に戻し、非秘匿名で復活したら R22-1 の解除経路が Pending にする。閉じている。
- **R22-4 / R22-5 は R21-4 の両側**。R22-4 は「enqueue しない代わりに可視化する」(受け皿)、
  R22-5 は「既に enqueue されてしまったものを送信前に退役させる」(マイグレーション)。
  R22-5 の precondition/executor 修正は R21-3 の `AwaitOcr` 分類を壊さないこと
  (octet-stream **binary** = `prepared_units` 空 は R21-4 の enqueue ガードで到達しない。
  今回 `Retire` にするのは octet-stream **text** = `prepared_units` 非空の単一 File unit のみ)。
- **R22-6 (b)** の guard 緩和は R18-1 の「Done の stamp は実支出」不変条件を壊さないこと
  (revive 対象は Failed(AuthError) のみ・Done は従来通り除外)。
- **R22-7** は R22-3 の fix 後も独立に必要 (live な hold は正当に Paused のまま残るため)。

**推奨実装分担**: R22-1/2/3 (秘匿 × liveness の状態収束・delicate) はオーケストレータ or 単一 Agent が context 保持。
R22-4/R22-5 (file-routing) と R22-6 (AuthError 横展開) は別 Agent。R22-7/R22-8 は独立。
各 fix ごとにターゲット絞りテスト + critical/major は control 付き実機 repro クローズ。
**docs 変更禁止・新エラーコード新設禁止** (R17-4/R18-4/R19-6 の教訓。R22-4 の可視化は既存 `KIO-I-*` INFO 系で行う)。

---

## 探索したが問題なしと確認した領域 (multi-engine 健全確認)

- **R21-1 の JOIN dedup 単体**: 3 インスタンス以上 (秘匿複数 + 非秘匿) でも「一度でも秘匿パスが選ばれたら
  非秘匿に戻らない」単調性が走査順序に依らず成立 (Sonnet-B/C/D 独立確認)。Opus は byte-identical 双子で
  実機再現し「embedding task 1 本のみ held・input=秘匿パス・課金 0」を確認 — R21-1 の root fix は健全。
- **R21-1 の送信バイパス耐性**: `sendable`→`embeddable` は毎回コンテンツベースで再計算されるため、
  R22-2 のようなラベル不整合があっても実送信バイパスには至らない (Sonnet-B が複数パターンで実機確認、
  `embedding_tasks_executed` は 0 のまま)。
- **R21-1 の `override_budget` バイパス**: `Paused` + `secrets_tier_b_hold` は `--override-budget` を渡しても
  再送不可 (Sonnet-D)。
- **R21-3 `AwaitOcr` の冪等性と二段ゲート整合**: `execute_online_markdownize_task` の呼出は `main.rs:6171` の 1 箇所のみで、
  必ず `classify_online_markdownize_precondition` (6003) を通る。判定がすり替わる余地なし (Sonnet-C + オーケストレータ)。
  画像を index/batch resume 交互に 5 回回しても online task は常に 1 本・churn 無し・phantom charge 無し (Opus)。
- **R21-5 のページ単位 suppress**: `prepare::pdf_text_pages` と `deterministic::extract_pdf_text_pages` は
  mixed ケースで共に `normalize_pdf_page_count(pdf_stream_text_pages, pdf_page_count_in_text().max(1))` に帰着し完全一致 —
  ページ index 齟齬による誤抑制は無い (Opus)。ゴミバイトは FTS に露出せず、unit_key/ページ番号も保持される。
  かつ mixed PDF では online enhancement task が必ず併走し `index_status` は `enriched_ratio 0.5 /
  pending_enrichment_tasks 1` を正直に報告する (Sonnet-D + オーケストレータ独立確認) — 「suppress したページの
  証拠喪失」は**健全**。
- **R21-6 revive の会計整合性**: auth_error を 3 サイクル反復しても device_spent は 1×(2.4375e-6) で不変、
  reserved/attempts も一定。revive 前に reclaim が先行する順序も正しく、二重計上・二重 reclaim・cap drain は無し
  (Opus + Sonnet-A + Sonnet-D 独立確認)。
- **R21-4 の拡張子 lowercase 化**: `scan.rs:418` と `main.rs:8370` の 2 実装はバイト単位で一致、drift 無し
  (Sonnet-B + Opus + Spark 検証2(b))。既存 index の identity (tool_profile_hash) も不変。
- **online markdownize の秘匿リネーム経路**: 送信直前に `task.input_path` を読むためリネーム後は `fs::read` 失敗
  → `Retire` で安全失敗、漏洩なし (Opus)。
- **時刻/TZ ユーティリティ**: `civil_from_days`/`days_from_civil` (Howard Hinnant)、`format/parse_utc_seconds`、
  `retry_backoff_seconds` (saturating + clamp)、`date_of_system_time`/`prune_rotated_logs` は
  `div_euclid`/`rem_euclid` で負値・境界を正しく処理。DST/閏 (2024 閏日・2100 非閏年) に破綻なし
  (Opus + Sol 独立確認)。※R22-8 はローテの並行性であり日付演算とは別。
- **`--online --yes` の embedding/markdownize 非対称** (embedding は one-shot 送信、markdownize は persistent opt-in 必須):
  `main.rs:6322-6327`/`9889-9895` のコメントで N7 precedence として**意図的**と明記 (Opus)。
- **Spark 検証1(b)(c) / 検証2(a)(b)(c)(d)**: R21-7 revive の `attempts`/`reserved_*` クリア、
  reconcile の非 live 判定が `pending` 由来でなく DB (`live_chunk_ids`) 由来であること、
  `AwaitOcr` が charge 前に `continue` すること、AuthError revive が 1 pass 内で有限回収束することを file:line で確認 —
  いずれも健全。

## 却下 (4 件)

- **GPT-5.6-Sol-Ultra R22-3 (PDF の画像変更が fingerprint に反映されず旧 OCR を新 raw_hash に誤束縛)**:
  `docs/04-pipeline.md:112` が「perceptual hash = **MVP では prepared unit バイト列の sha256 で代替**
  (= 完全一致のみ)」と明記しており、実装 (`prepare.rs:193` `fingerprint_for_bytes`) は仕様通り。
  PDF 内画像の抽出自体が Step 4 (`bbox_annotation`) 未着手で `image_object_hashes` は常に空。
  **docs 明示の MVP 制約**であり新規バグではない (FlateDecode 据え置きと同じ扱い)。
- **GPT-5.6-Sol-Ultra R22-4 (vector opt-in preflight が per-scope 隔離より先に stale scope を読み健全 scope も全滅)**:
  実機で 3 変種すべて反証 — scope ディレクトリ削除 / `scope.json` 破損 / `.kio` を `chmod 000` (permission error) の
  いずれでも `exit 3` + `excluded_scopes:[{reason:"unreachable"}]` + **健全 scope の結果を保持** (results=6)。
  静的読解のみのエンジンによる規模・伝播主張は実測で裁定する原則 (R11 の FTS fatal 却下と同型)。
- **GPT-5.6-Sol-Ultra R22-5 (partial search が失敗 scope を cursor に混ぜ次ページを自己破壊)**:
  cursor payload に `{"consumed":0,"max_rowid":0,"snapshot_commit":""}` が実際に混入することは確認したが
  (Sol の静的指摘は**データレベルでは正しい**)、page 2 は `exit 3` + 健全結果 2 件 + 正しい `excluded_scopes`
  (`index_missing` の recovery hint 付き) を返す。到達可能かつ失敗した scope (index db 削除) でも同様に成立。
  失敗 scope は空 snapshot を使う前に除外されるため、混入エントリは**不活性**。実害なしで却下。
- **GPT-5.6-Sol-Ultra R22-7 (R20-10 の held 除外が作成順依存で「既存 vector → 新規 secret」の逆順を防げない)**:
  前提が content-addressing と矛盾。byte-identical な秘匿双子は **同一 `chunk_id` に畳まれる** ため
  「新規 secret chunk」は存在しない (実機: 双子追加後も `chunks` テーブルは 1 行、`raw_path` は先見の非秘匿パスのみ)。
  ベクタは非秘匿ファイルの内容と完全同一で、秘匿パスが Evidence として露出することもない。

**オーケストレータ自身の仮説も 1 件自己却下**: R21-5 の placeholder コメント
(`<!-- KIO deterministic baseline page:2 sha256:... -->`) が FTS に載り検索結果に返る件は、
空 unit のプレースホルダとして **R21-5 以前から存在する既存パターン** (Sonnet-B の判定を採用)。
mixed PDF では online enhancement が併走するため証拠喪失も無く、新規バグとしては報告しない。

## 据え置き (2 件・継続)

- **FlateDecode/zlib 展開の不在** (R21 から継続): 圧縮 PDF はローカル text 抽出できず OCR 経路へ落ちる。
  pre-existing・design。docs 凍結解除時に「圧縮 PDF は OCR 必須」を開示検討。
- **cost-ledger の month 月跨ぎ** (R17 から継続): `month` がループ前 1 回計算のため月末開始 pass の翌月分が
  前月に記帳され得る。charge 総額は正・有界稀。Step 4 の gc/会計設計で裁定。

---

## 総括: 「fix が開ける穴」11 例目の 3 変種

R22 は前ラウンド fix の新配線から、taxonomy 上**異なる 3 変種**が同時に出た:

1. **適用範囲の広げ過ぎ** (R22-1): R21-1 の defense-in-depth が「hold の解除」という正当な遷移まで禁止した
   (R17-1 の `resolve_pointer` best-effort と同型)。
2. **適用範囲の絞り漏れ / 相似形の隣** (R22-2/R22-3/R22-6): R21-7 は `existing` から `RETIRED_NON_LIVE` だけを
   特例除外し、reconcile の 2 sweep は `Paused` だけを状態集合から落とし、R21-6 は embedding にだけ revive を配線した
   (R16-1 の `read_tree`/`read_commit`、R18-1 の embedding 横展開漏れと同型)。
3. **新規状態だけを直し既存状態のマイグレーションが無い** (R22-4/R22-5) — **新変種**。
   R21-4 は「これから作る task」の enqueue を直したが、「すでに存在する task」の送信も、
   「enqueue しなくなったファイル」の可視化も用意しなかった。**fix が状態機械の入口だけを守り、
   在庫と出口を放置する**型は今後も掃く対象。

多エンジン収束: R22-1 に 3 (Opus/Spark/オーケストレータ)、R22-2 に 3 (Sonnet-A/B/オーケストレータ)、
R22-3 に 3 (Sonnet-C/Sol/オーケストレータ)、R22-4 に 3 (Sonnet-B/D/オーケストレータ)、
R22-7 に 2 (Opus/Sonnet-C)。かつ **1 つの根 (task 状態の非収束) を 3 エンジンが 3 方向から独立に突いた**のが本ラウンドの特徴
(R19 の「収束でなく網羅」の逆で、今回は「網羅が収束を証明した」)。

エンジンの誤判定 1 件: **Sonnet-D が R22-1 を「`release_secret_holds` があるので恒久固着ではない」と健全誤判定** →
オーケストレータが「呼出しは `--send-secrets` 経路のみ」を file:line で示し、5 回復コマンドの control 実機で反証。
Opus doc-gap 型 (R13/R15/R17/R18) の 5 例目だが、今回は Opus 自身が R22-1 を control 実機で単独発見しており、
**役割は固定的でない** (R19 と同じ教訓)。

## オーケストレータ側の新しい罠 (次ラウンドへの申し送り)

- **並列エンジンが共有 scratchpad で衝突する** (Sonnet-C 報告): `/private/tmp/claude-501/<session>/scratchpad/` を
  複数エンジンが同時に使い、書いたファイルが他エンジンに上書き/削除された。**エンジンごとに一意な作業ディレクトリ**
  (`mktemp -d /tmp/kio-<engine>-XXXX`) を指示すること。
- **`kio search` に `--mode` フラグは存在しない** (複数エンジンが誤用)。mode は config / `--text` 等で決まる。
  cursor は `paging.next_cursor` の下にある (トップレベルではない)。
- **`codex exec -m gpt-5.3-codex-spark` は `model_reasoning_effort="max"` を 400 で拒否する**
  (`none|minimal|low|medium|high|xhigh` のみ)。Spark には `xhigh` を明示すること。
- **1 検証 1 XDG** (R11 の再確認): index した scope を新しい `XDG_DATA_HOME` から検索すると
  registry が空で 0 件になる。同一 Bash 呼び出し内で `export` を通すこと。
