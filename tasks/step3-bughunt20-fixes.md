# 探索型監査 第20ラウンド (R20) — 裁定と修正計画

7 エンジン (Claude-Opus / Sonnet-A / Sonnet-B / Sonnet-C / Sonnet-D / GPT-5.5 / GPT-5.3-Codex-Spark)。
HEAD `64d8cab`、全 478 テスト green・clippy(--all-features)/fmt clean の状態から開始。

**結果: 1 critical + 5 major + 5 minor。却下 0 (R9・R16・R19 に次ぐ 4 回目)。**

本ラウンドは 2 つの脈が同時に噴出した稀なラウンド:

1. **R19 fix が開ける穴 (定番脈 10 例目・本命焦点)** — R19-3 の可逆化 (`retired_non_live`) と reclaim 系列が
   **cost-ledger の両方向の穴**を開けた: **過剰 reclaim** (R20-2、Opus、cap fail-open) と、系列が扱わない
   error-kind の **未 reclaim** (R20-3、Sonnet-B、AuthError phantom で cap 枯渇)。前者は「重複 output_ref タスク ×
   output_ref 単位一括更新」という、全エンジンが健全確認した「単一タスク二重 reclaim」とは**別経路**。

2. **file-type ルーティングの未掘鉱脈 (新脈・「直感を優先」の成果)** — Sonnet-C が「reclaim 領域より、スキャン文書の
   OCR 経路が実際に機能するか」を実機で最初から辿り直し、**Step 2 (2026-07-03) 以来 19 ラウンド素通りしてきた**
   3 つの major を発見 (R20-4/R20-5/R20-6)。Sonnet-B が R20-5 に独立収束。いずれも `status:done`/`exit 0`/`kio status`
   健全表示の**完全な沈黙型**で、"Evidence-grounded" の中核 (docs/02) に反しバイナリのゴミが「証拠」として索引される。

加えて **critical 1 本** — R19-1 が「どの Tier をゲートするか」を統一した隣で、**「ゲートに渡す path 自体が
陳腐化しうる」**という直交した前提が未検証だった (R20-1、Sonnet-A)。リネームだけで Tier A/B hold が無効化される。

全 critical/major はオーケストレータが `/tmp` 隔離 `XDG_DATA_HOME` 下で control 付き実機再現済み。

---

## 所見一覧 (severity 降順)

### R20-1 [critical] embedding の秘匿オンライン送信ホールドが chunk の `raw_path` 陳腐化 (rename/move) で無条件にすり抜ける — `--send-secrets` 無しで held ファイルの本文が実際に外部 API へ送信される

**エンジン**: Claude-Sonnet-A (control 実機)。**脈/型**: R19-1 fix が開ける穴 — 「どの Tier をゲートするか」は統一したが「ゲートに渡す path 自体が陳腐化しうる」という直交前提が未検証。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:7628-7639` (`live_chunks_without_embedding`) — liveness 判定には `tree_entries` (現 HEAD tree、**正しいパス**を持つ) を JOIN しているのに、`SELECT c.chunk_id, c.text, c.text_hash, c.raw_path` の **SELECT 節は `chunks` 側の陳腐化 `raw_path`** (chunk 生成時点の初出パス) を返す。
- `crates/kio-cli/src/main.rs:7098` (embedding hold gate、R19-1) — `!secrets_approved && classify_secret(&chunk.raw_path).is_some()` がこの**陳腐化 path** を直接読む。同じ陳腐化が `main.rs:7864` (`hold_secret_embedding_tasks`)・`main.rs:7921` (`enqueue_embedding_tasks`) の `task.input_path` にも伝播。
- **docs 契約違反**: `docs/04-pipeline.md:301` は明示的に「`raw_path` は chunk 生成時点の path (**表示用**)。**現在 path は tree_entries join で得る**」と規定。secret gate が `chunks.raw_path` を現在パス判定に使うのは自らの docs 契約に反する。

**期待 vs 実際 (control 付き実機再現、`--send-secrets` は一度も未使用)**:
```
notes.md (非秘匿名・平凡な本文) を offline index → chunk raw_path="notes.md", embedding task Pending
mv notes.md notes_password_reset.md   (同一バイト列、Tier B "password" にマッチするリネームのみ)
index --approve --online (mock embed)
→ embedding task: status=done, fallback_reason="embedding_adapter_done", reserved_usd 課金, embeddings=1 (送信済)
→ quarantine.jsonl: approval_method="hold" (偽の監査記録)
→ secrets-approved.jsonl: 不在 (承認は一度も無い)
```
期待 = リネーム後の現在名が Tier B なら `secrets_tier_b_hold` で Paused、送信されない。実際 = 陳腐化 `raw_path="notes.md"` (非秘匿) を読むため hold されず、本文が実際に埋め込み API へ送信され `done`。監査記録は "hold" と主張し続けるためインシデント調査でも見抜けない。

**なぜ critical か**: 発火に秘匿固有の操作 (`!pattern`・`--send-secrets` 等) が一切不要。「まだ埋め込み未完了のファイルを普通の理由でリネームする」だけで踏む。R19-1 裁定注記の基準 (「秘匿特有の操作ゼロで送信」= critical / `!pattern` 等の明示操作を要する = major) の前者に該当。Tier B 判定語 ("password"/"token"/"secret"/"credentials"/"apikey") は自然な英単語でファイル名に出現しうる。

**1 行修正案**: `main.rs:7630` の SELECT を `SELECT c.chunk_id, c.text, c.text_hash, te.path` に変更 (`te` は同一クエリで既に JOIN 済み)。`chunks.raw_path` (表示/time-travel 用の初出パス) は append-only のまま残し、`EmbeddableChunk.raw_path` だけを「常に tree_entries 由来の現在パス」にすれば 7098/7864/7921 の 3 消費箇所が一括で直る。

---

### R20-2 [major] embedding reclaim の二重計上 — `retired_non_live` 復活 (R19-3) が生む同一 output_ref 重複タスクが `apply_embedding_transitions` に二重スタンプされ、reconcile が 1 課金に 2 回 reclaim → device/adapter 月次 cap の silent 過小計上 (fail-open)

**エンジン**: Claude-Opus (control 実機、会計値実測)。**脈/型**: R19 focus (b) 二重 reclaim だが、全エンジンが健全確認した「reconcile の live-embedded 分岐 vs 非 live 分岐 (単一タスク)」とは**別経路**。R19-3 の可逆化 fix が開けた穴 (定番脈 10 例目)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:7888-7940` (`enqueue_embedding_tasks`) — `existing` dedup 集合が `fallback_reason == RETIRED_NON_LIVE` を除外 (`7904`)。revert で chunk_id が復活すると**同一 `output_ref` (`embedding:<chunk_id>`) の新規タスクを append** (旧 retired タスクは削除されず重複)。
- `crates/kio-cli/src/main.rs:7394-7423` (`apply_embedding_transitions`) — `update_matching` が `transitions.get(&task.output_ref)` で照合し (`7415`)、**同一 output_ref の全タスク**に transition と `reserved` スタンプを適用。fresh 送信が rate_limit 失敗すると旧 retired タスク (reserved=None) まで `Failed(rate_limit) reserved=X` に**再スタンプ**され `RETIRED_NON_LIVE` を上書き。
- `crates/kio-cli/src/main.rs:7706-7758` (reconcile 第 1 pass) — Failed+reserved の**各タスク独立に** `retire_online_task_reclaiming` で reclaim entry を push → 重複 2 タスクで **reclaim 2 本**。
- 対照: markdownize executor は `task_id` 一致で更新するため再スタンプが起きず、本バグは embedding 固有。

**期待 vs 実際 (control 実機、会計値実測)**:
```
step1 index --online rate_limit          → E1 Failed(rate_limit) charged 2.8875e-6
step2 edit + index --online mock          → reconcile: E1→retired_non_live+reclaim 2.8875e-6 (正); 新body embed
step3 revert EXACT + index --online rate_limit → 同一 output_ref 2 タスク (grep 実測), 両方 Failed(rate_limit) reserved
step4 edit + index --online mock          → reconcile が両タスク reclaim → reclaim ledger 3 行
```
gross charges = 11.7e-6、reclaimed = 8.6625e-6 (**3 本**、うち step4 が 2 本)、**net = 3.0375e-6**。正しい net (mock 成功 2 body の実支出) = 5.925e-6。**1 embed 分 (2.8875e-6) 過小計上** → `budget_remaining_for_adapter` (R18-3 net) が過大 remaining を返し月次 cap を silent bypass。revert サイクルごとに累積。exit 0・警告なし。R15-5/R17-3 が守った「予約 ≥ 実支出」不変条件の reclaim 側での破れ。

**1 行修正案**: `enqueue_embedding_tasks` で `RETIRED_NON_LIVE` タスクを新規 append する代わりに**その場で revive** (Failed→Pending・`fallback_reason` クリア・`reserved_*` は None のまま) し `existing` に残す — 同一 output_ref の重複タスクを構造的に作らせない。(R20-11 の fail-closed netting は独立の安全網として併せて入れる。)

---

### R20-3 [major] `AuthError` (401/403) で失敗した online markdownize/embedding タスクの F8 phantom 予約が唯一 reclaim されず、月次予算を永久に食い潰す — reclaim 系列 (R16-7→R19-2) が RateLimit/Quota/Network だけを扱い AuthError を 5 ラウンド一度も検討していない

**エンジン**: Claude-Sonnet-B (control 実機、rate_limit 対照付き)。**脈/型**: reclaim-dichotomy-incomplete (R18-1 embedding 欠落・R19-2 quota 欠落に続く欠落種別の 3 例目)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:9345-9365` (`reclaim_entry_for`) — allowlist は `RateLimit | QuotaExceeded` のみ (`9352`)。
- `crates/kio-cli/src/main.rs:7995-8000` (`is_reservation_bearing_send_failure`) — allowlist は `RateLimit | QuotaExceeded | NetworkError` のみ (`7998`)。どちらも `AuthError` を含まない。
- `crates/kio-pipeline/src/task.rs:338-341` — `retry_policy(AuthError)` = `retryable:false, max_attempts:Some(0)` → `batch retry` からも永久に触れない。
- 結果: markdownize は supersede/sweep (is_reservation_bearing_send_failure ゲート) が AuthError を退役対象にせず、embedding は reconcile 非 live 退役はするが `reclaim_entry_for` が None を返すため、いずれも phantom 予約が cost-ledger に残留し reclaim されない。

**docs/コードの自己整合性**: R16-7 は「429 はバックエンドで処理前に拒否され課金され得ない」を reclaim 根拠に据えた。401/403 の認証拒否は通常レート制限より**さらに手前**で拒否される (非課金性は RateLimit と同等以上) にもかかわらず、R16-7→R17-3→R18-1→R18-2→R19-2 の 5 ラウンドで AuthError は一度も検討対象に入っていない。

**期待 vs 実際 (control 実機、embedding 経路で discriminator)**:
```
[rate_limit 対照]: index --online rate_limit → 編集で非live化 + index --online mock → reclaim ledger 1 行 (reclaim 済)
[auth_error 本件]: index --online auth_error → 編集で非live化 + index --online mock → reclaim ledger 0 行 (phantom 残留)
```
auth_error タスクは reconcile で `retired_non_live` に退役するが reclaim されず、phantom 課金が月次 cap を食い続け、いずれ無関係な正規タスクを `budget_exceeded` で誤 Pause (R17-3/R19-2 が他種別で防いだのと同じ害)。認証エラー (キー誤設定・失効という頻出シナリオ) 後にファイルを編集/削除する通常操作で踏む。

**1 行修正案**: `reclaim_entry_for` (`9352`) と `is_reservation_bearing_send_failure` (`7998`) の allowlist に `RetryErrorKind::AuthError` を追加。AuthError は 401/403 = 非課金確定なので RateLimit/Quota と同列 (NetworkError の「課金され得る」保守扱いとは別)。

---

### R20-4 [major] `pdf_has_text_layer` が生バイト列への 2 バイト `BT` 部分一致で判定するため、スキャン画像 PDF (圧縮ストリームの偶然一致) が「テキスト抽出成功」と誤判定され、バイナリのゴミがそのまま markdown/chunk として永続化・検索露出する

**エンジン**: Claude-Sonnet-C (control 実機)。**脈/型**: file-type ルーティング新脈 (Step 2 以来未掃)。

**根本原因 (file:line)**:
- `crates/kio-pipeline/src/prepare.rs:247-249` — `fn pdf_has_text_layer(bytes) -> bool { !bytes.starts_with(b"%PDF") || bytes.windows(2).any(|w| w == b"BT") }`。テキストレイヤ判定が「生バイト列全体に `BT` (0x42 0x54) が 1 箇所でもあるか」のみ。スキャン PDF の JPEG/Flate 圧縮画像ストリームは事実上ランダムで、期待出現回数 ≈ N/65536 → 数百 KB で偶然一致がほぼ確実。
- `crates/kio-pipeline/src/prepare.rs:252-278` (`pdf_text_pages`) — 誤判定後、stream/literal 抽出が空だと `pdf_text_fallback` (`297-303` = `String::from_utf8_lossy(bytes)` の非 %-行) に落ち、**生バイナリのロッシー UTF-8 デコード** をページ本文として返す。

**期待 vs 実際 (control 実機再現)**:
```
200KB ランダムバイト列 (+%PDF ヘッダ) → raw BT matches=2 → index --yes
→ markdownize task status=done, unit_keys=["page:1"]
→ chunks テーブル: raw_path=scan.pdf, text=(67 バイトの制御文字/replacement char のゴミ)  ← 索引・検索可能
```
期待 = テキストレイヤ無し画像 PDF は pending 化して AI 強化 (OCR) 待ちへ (`docs/07-adapter-spec.md` §2.1)。実際 = 現実的サイズのスキャン PDF はほぼ確実にこの誤検知を踏み、`status:done`・`kio status` は健全表示、エラー・警告ゼロで完全なノイズが「正しく抽出された証拠」として索引される。

**修正案**: 生バイト列全体への部分文字列マッチを廃し、`kio_adapter::deterministic::pdf_stream_text_pages` が抽出した content-stream (`stream`...`endstream` の中身) テキストに対して `BT`/`ET` 演算子を判定する。抽出テキストが空なら「テキストレイヤ無し」= R20-5 の pending 経路へ正しく落とす。

---

### R20-5 [major] テキストレイヤ無し PDF (`prepared_units` 空) の Pending task が (a) idempotency ガードを持たず idle re-index のたび重複生成、(b) 実行不能な固定 output_ref を持ち恒久停止 (スキャン PDF が OCR へ到達しない)

**エンジン**: Claude-Sonnet-B + Claude-Sonnet-C (独立収束、両者 control 実機)。**脈/型**: file-type ルーティング新脈。04 §5.5 idempotency 契約違反。

**根本原因 (file:line)**:
- 生成側: `crates/kio-cli/src/main.rs:8545-8560` — `prepare.prepared_units.is_empty()` 時に `output_ref="pending:scanned_pdf_without_text_layer"` で `task_store.append` (**idempotency チェック皆無**)。直後の兄弟パス (`8562` `done_output_for` チェック、`8576` `enqueue_online_placeholder_task` の `(input_path,input_hash)` dedup) が持つガードがこの分岐だけに無い。
- 唯一の実行系: `crates/kio-cli/src/main.rs:5883-5890` (`execute_pending_markdownize_tasks`) — フィルタは `task.output_ref == online_output_ref(adapter_id)` (= `"online:{adapter_id}"`)。上記固定文字列と**構造上一致し得ない** → `batch resume`/`index --online` を何度実行しても `tasks_attempted:0`。

**期待 vs 実際 (control 実機)**:
```
テキストレイヤ無し PDF (BT count 0) を idle index ×3 (無変更)
→ tasks.jsonl 3 行、distinct input_hash=1、distinct task_id=3、output_ref すべて "pending:scanned_pdf_without_text_layer"
→ KIO_TEST_MISTRAL_OCR=mock で batch resume / index --online → tasks_attempted:0 (永久 pending、OCR 未到達)
```
期待 = `docs/07-adapter-spec.md` §2.1 のとおり file を pending (AI 強化待ち) とし、online OCR へ遷移。実際 = 重複が無限累積し `compute_index_status` の分母を肥大化させ scope 全体の `enriched_ratio` を単調に 0 へ劣化 + スキャン PDF は OCR に一度も到達しない (Step 2 以来 dead-end)。

**修正案**: この分岐を `enqueue_online_placeholder_task` 相当のヘルパー (もしくは `online_output_ref(&online_markdownize_profile().adapter_id)` を使う task) へ合流させ、既存の実行系・idempotency・online OCR 経路をそのまま継承させる。

---

### R20-6 [major] DOCX/PPTX/XLSX 等の拡張子が media_type 検出テーブルに無く `application/octet-stream` に丸められ、ローカル passthrough が生 ZIP バイナリを「成功」として証拠化・検索露出する

**エンジン**: Claude-Sonnet-C (control 実機)。**脈/型**: file-type ルーティング新脈 (config-key drift の media_type 版)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:8081-8095` (`media_type_for_cli_path`) と `crates/kio-pipeline/src/scan.rs:418-432` (`media_type_for_path`) — **完全同一内容の 2 重実装**。両者とも `md/markdown/txt/rs/py/js/ts/go/java/c/h/cpp/pdf/png/jpg/jpeg` のみ判定し、他は全て `_ => "application/octet-stream"`。
- 対照的に `crates/kio-pipeline/src/prepare.rs:233-245` (`unit_type_for_media_type`) は OOXML MIME (`...spreadsheetml.sheet`/`...presentationml.presentation`)・`image/webp`・`image/gif` を Sheet/Slide/Image に正しく振り分ける論理を**既に持つ**が、上記 2 関数がその MIME 文字列を一度も生成しないため到達不能。

**期待 vs 実際 (control 実機)**:
```
report.docx (PK ZIP マジック + <w:t> 本文) を index
→ media_type="application/octet-stream" (preview 実測)
→ task status=done, unit_keys=["doc:1"]
→ search "ACME quarterly" → evidence_pointer char_start:0 char_end:64、生 ZIP+XML バイト列が索引化
```
`docs/07-adapter-spec.md:195` は「非 text-native PDF/DOCX/PPTX/画像の Markdownize 第一候補は Mistral OCR」、docs/07:71 は同梱ローカル Adapter を「plain text/Markdown/コード passthrough + PDF text layer 抽出」に限定 (DOCX/PPTX はローカルで扱わない契約)。実際は拡張子未認識で octet-stream に落ち、ローカル passthrough が「1 ファイル 1 オペーク unit」として生バイト列を markdown 化・`status:done`・検索索引化。オフライン専用ユーザにはこれが恒久的な唯一の内容になる。

**修正案**: `media_type_for_path`/`media_type_for_cli_path` の両テーブルに docx/pptx/xlsx (+ webp/gif) の正しい MIME 文字列を追加し 2 重実装を 1 箇所に統合。これにより OOXML は非 text-native → `prepared_units` 空 → R20-5 の (修正後の) online OCR 経路へ正しく落ちる (R20-5 と一体で設計)。

---

### R20-7 [minor] `retired_non_live` タスクが `index_status.enriched_ratio` の分母に残り、削除/退役済み chunk が恒久的な未 enrichment と誤表示される

**エンジン**: GPT-5.5 (静的 file:line、オーケストレータ code 確認)。**脈**: R19-3 の観測系未対応。

**根本原因 (file:line)**: `crates/kio-cli/src/main.rs:2391-2459` (`compute_index_status`) — 全 Markdownize/Embedding タスクを `total += 1` (`2407`) で分母算入後、non-retryable Failed は `TaskStatus::Failed => {}` (`2429`) で done/pending どちらにも入れない。R11-8 は**現在 live** の permanent gap を意図的に分母残置するが、`retired_non_live` は chunk が**非 live** (削除/再チャンク/supersede) なので現行 corpus の enrichment 比率に算入すべきでない → `enriched_ratio < 1.0` かつ `pending_enrichment_tasks = 0` の矛盾する行き止まり表示が恒久化。

**修正案**: `2407` の `total += 1` 前に `if task.fallback_reason.as_deref() == Some(RETIRED_NON_LIVE) { continue; }` を追加 (`retired_non_live` のみ除外・真の permanent gap = invalid_input/contract は R11-8 通り残置)。

---

### R20-8 [minor] `store_corruption_recovery_hint` の R19-6 拡張が per-entry のみに効き、`index_unusable` 集約と異種混在全滅ではトップレベル `context.recovery` が依然ゼロ — R19-6 コメントが「解決した」と述べたパターンが未解決

**エンジン**: GPT-5.3-Codex-Spark + Claude-Sonnet-D (独立収束)。**脈/型**: 「fix が自らの完了条件を追い越さない」(R19-6 コメントの前提が実装未達)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs:2479-2505` — R19-6 は `store_corruption_recovery_hint` に `index_missing`/`index_corrupt` arm を追加したが、per-entry 添付 (`1379-1382` Excluded arm) にしか効かない。
- `crates/kio-cli/src/main.rs:1445-1452` (`index_unusable` 集約 → `KIO-E-SEARCH-VEC-UNAVAIL-001`) — メッセージにハードコードした repair 文言はあるが**トップレベル `context.recovery` が無い** (per-entry `excluded_scopes[].recovery` のみ)。`store_corruption` 集約 (`1469-1501`) は `context.recovery` を持つのと非対称。
- `crates/kio-cli/src/main.rs:1502-1505` (異種混在全滅、例: index_corrupt + store_corrupt) — 両同種集約に該当せず `scope_all_failed_error` の "all searched scopes failed" 固定文言 (トップレベル recovery 無し) にフォールバック。
- R19-6 コメント (`2489-2493`) は「異種混在 all-failed がヒントゼロに落ちる」ことを問題として明記し「index_unusable 集約もこの関数を経由するよう揃える」としたが、実 diff (`34bcede`) は match arm 追加のみ。

**修正案**: `store_corruption` 専用集約 (`1469-1501`) を一般化し、「`excluded` 全エントリが何らかの recovery hint を持つ」場合に per-entry hint から重複排除した `context.recovery` 配列と `message` プレフィックスを組み立てる (2 パターン限定 `matches!` を撤廃)。エラーコードは既存のまま (docs 凍結・新コード不可、R17-4 の教訓)。

---

### R20-9 [minor] R19-7 の quarantine reader が「path ごと最新行採用」を実装しておらず、`kio status` が同一ファイルに `hold` と `send_approved` の矛盾 2 行を表示

**エンジン**: Claude-Opus (control 実機、Sonnet-A も reader 非 dedup を観測)。**脈/型**: fix コメントの前提が実在しない (R19-7 半修正)。

**根本原因 (file:line)**:
- `crates/kio-cli/src/main.rs` `read_quarantine_records` — 全行を verbatim で返すのみ。R19-7 の fix コメント (`~9964-9968`) の「The reader takes the latest row per path」は**実在しない**。
- `kio status` はこの結果をそのまま `quarantine` フィールドへ。回帰テスト `r19_7` (step3_p0_contract.rs) は `send_approved` の**存在のみ** assert し hold 行の解消を検証しないため素通り。

**期待 vs 実際 (control 実機)**: Tier B ファイルを `index --yes` (hold 記録) → `index --yes --send-secrets` 後、`quarantine.jsonl` に `approval_method:"hold"` と `"send_approved"` の**両行**が出現 (2 行実測)。R19-7 が是正しようとした「承認済ファイルを未承認と誤報」が逆に矛盾 2 disposition の同時提示になり audit 整合が崩れる。送信ゲート自体は `secrets_send_approved` 依拠で正 (漏洩なし) のため minor。

**修正案**: `read_quarantine_records` を path ごと最新 (最終行) 1 件に畳む、または `kio status` 提示前に `(path)` で最新採用 dedup する (R19-7 fix コメントが前提とした reader 挙動を実装)。

---

### R20-10 [minor] secrets hold 中の embedding chunk が、content-hash 再利用 (`rebuild_chunk_vec`) 経由で非秘匿双子ファイルのベクトルを継承し `chunk_vec` に載る — held ファイルの共有 chunk がベクトル検索に露出 (defense-in-depth)

**エンジン**: Claude-Sonnet-D (実機再現、オーケストレータが影響範囲を切り分け)。**脈/型**: R19-4 が「良い」方向で使う「data-level 完成 vs task-level 完成の乖離」が secrets 文脈で逆に働く機能横断の盲点。

**根本原因 (file:line)**:
- `crates/kio-index/src/embedding_store.rs:152-171` (`rebuild_chunk_vec`) — `chunks c JOIN embeddings e ON e.target_id = c.text_hash` の **content-hash のみ**の JOIN。対象 chunk の embedding task が Paused/held かを一切見ない。
- `crates/kio-cli/src/main.rs:647` — `rebuild_step3_index` が embedding enrichment (`652`) より前に無条件で呼ばれ、非秘匿双子が送信済みなら held ファイルの共有 chunk_id が同じベクトルへ紐付く。

**影響範囲の切り分け (オーケストレータ実機確認)**: 露出するのは**非秘匿双子と byte-identical な共有 chunk のみ** (chunks 実測: 秘匿ファイルの UNIQUE chunk `UNIQUESECRET` は双子が無く embeddings に載らず = ベクトル化されない)。かつ Tier B は設計上ローカル FTS 検索可能 (docs/10 §1.1) なので path/snippet は元々ローカル露出する。したがって実害は「共有 (= 非秘匿) 内容がベクトル/意味検索でも見つかる」marginal な増分。ただし held ファイルの内容 (共有部) が online 送信由来のベクトルに載る点は hold の趣旨に反するため defense-in-depth として minor 採用。

**修正案**: `rebuild_chunk_vec` (またはその直後) で、現在 Paused な secrets hold (`secrets_tier_b_hold`) を持つ embedding task の chunk_id を `chunk_vec` から除外し、`release_secret_holds` が Pending に戻すまで再リンクしない。R19-4 の Failed(retryable) 収束は温存 (hold 除外のみ、Failed は対象外)。

---

### R20-11 [minor] `net_monthly_spent` が `reclaimed > gross` を 0 に clamp するだけで fail-close しない — reclaim ledger の異常 (R20-2 の過剰 reclaim や破損) を silent に cap fail-open へ変換する

**エンジン**: GPT-5.5 (静的 file:line)。**脈/型**: F1/F3 が charge ledger に与えた fail-closed 姿勢が新設 reclaim チャネル (R17-3+) に未継承。

**根本原因 (file:line)**: `crates/kio-cli/src/main.rs:9603-9617` (`net_monthly_spent`) — `Ok((gross - reclaimed).max(0.0))`。`reclaimed > gross` は正常運用では起きない (各 reclaim は kept charge に対応・stamp クリアで二重防止) が、R20-2 の過剰 reclaim や reclaim ledger 破損で成立すると net が 0 に clamp され cap が silent に fail-open。F1 (R8) は charge ledger の異常値 fail-open を major 修正した先例だが、reclaim netting は clamp のみで異常を隠す。

**期待 vs 実際**: 期待 = 異常な reclaim は fail-closed (F1 姿勢)。実際 = silent clamp で cap fail-open。**R20-2 の過剰 reclaim を loud に捕捉する安全網**でもある (R20-2 の root fix と併せて入れると多層防御)。

**修正案**: `net_monthly_spent` で `reclaimed > gross + ε` の場合に `KIO-E-STORE-CORRUPT-001` 系で fail-closed (既存コード使用・新コード不可)。R20-2 の root fix 後は正常運用で発火しないため無回帰。

---

## 修正の相互作用 (fix phase の設計協調)

- **R20-1** は単一 SELECT 変更で独立。ただし `EmbeddableChunk.raw_path` の意味が「初出パス」→「現在パス」に変わるため、他の `chunk.raw_path` 消費箇所 (表示・Evidence) が「現在パス期待」で問題ないか確認 (secret gate/task input_path は現在パス化が正)。
- **R20-2 / R20-11** は一体: R20-2 (重複タスク根絶) が root、R20-11 (fail-closed netting) が安全網。R20-2 修正後に R20-11 が正常運用で発火しないことを確認。
- **R20-3** は allowlist 2 箇所への AuthError 追加。R20-2 とは独立だが両方 reclaim 会計を触るため、AuthError reclaim が R20-2 の重複タスク問題と交差しないことを回帰テストで確認。
- **R20-4 / R20-5 / R20-6** は file-type ルーティングの一体クラスタ: R20-4 (BT 判定を抽出テキストベースに) が正しく効くと、真にテキストレイヤ無しの PDF が R20-5 (修正後の online OCR 経路) へ落ち、R20-6 (OOXML の media_type 認識) も同経路へ合流する。3 者を順に設計 (R20-6 → R20-5 → R20-4)。**docs 変更は禁止**、既存エラーコードのみ使用。

**推奨実装分担**: R20-2/R20-3/R20-11 (cost-ledger 会計、delicate) はオーケストレータ自身 or 単一 Agent が context 保持して実装。R20-4/5/6 (file-routing) は別 Agent。R20-1 (secret、1 行だが影響確認要) と minor 群は慎重に。各 fix ごとにターゲット絞りテスト + critical/major は control 付き実機 repro クローズ。

---

## 探索したが問題なしと確認した領域 (multi-engine 健全確認)

- **R19-2/R19-3/R19-4 の三位一体設計**: `reconcile_committed_embedding_tasks` の live-embedded 分岐 vs 非 live 分岐は相互排他 (**単一タスク**二重 reclaim は無い — Spark/Sonnet-A/C/D/Opus/GPT-5.5 が独立確認)。R20-2 は**重複タスク**という別経路。
- **`reclaim_entry_for`/`retire_online_task_reclaiming` 分離**: 全呼出で durable retire → reclaim append の順、stamp クリアで単一タスク二重防止、NetworkError は reclaim 非対象で stamp 保持 (R16-7 非対称維持)。
- **`is_reservation_bearing_send_failure` の過剰包含なし**: `RateLimit|QuotaExceeded|NetworkError` 限定で auth/invalid/contract を sweep しない (退役過剰なし)。※逆方向の**過少包含** (AuthError 欠落) が R20-3。
- **`RETIRED_NON_LIVE` vs genuine `invalid_input`**: enqueue idempotency は生文字列 `RETIRED_NON_LIVE` 直接比較で kind 畳み込みと無関係、genuinely-invalid を誤って再 enqueue しない。
- **classify_secret 統一ゲート + release**: markdownize enqueue (8501)/send-time (5897)/embedding (7098) の 3 面統一、lifted Tier A の hold reason 流用でも `release_secret_holds` が正しく解放。※R20-1 は「ゲートに渡す path が陳腐化」の直交問題。
- **R19-8 oversize 送信時再検査 / R19-6 per-entry recovery / 時刻・TZ 演算 (ローテ/prune/month)** — 健全確認。

## 却下 (0 件)

なし。全エンジンの所見が採択 (R9・R16・R19 に次ぐ 4 回目の却下 0)。多エンジン非重複 (critical 1 + major 5 が 4 方向: secret 陳腐化 [Sonnet-A] / reclaim 会計両方向 [Opus 過剰 + Sonnet-B 過少] / file-routing 3 [Sonnet-C、R20-5 は Sonnet-B 収束])。

## 据え置き継続 (Step 4 gc 設計マター)

tasks.jsonl (retired_non_live/done 蓄積を含む) / cost-ledger / open cache の無限成長、month 月跨ぎの charge/reclaim 記帳 (reserved_month で対称のため会計上は正)。R20 でも新規理由なし。
